"""Council service for ambiguous finance relation adjudication."""
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Any

from config.settings import get_settings
from src.shared.models import RawEdge, ResolvedEntity
from src.validation.models import ValidationResult, SignTag, SemanticTag, ValidationDestination
from src.council.models import (
    BaselineConflict,
    CandidateEntityRef,
    CandidateStatus,
    CitationSpan,
    CouncilAutoDecision,
    CouncilCase,
    CouncilCaseStatus,
    CouncilDecision,
    CouncilRole,
    CouncilTriggerReason,
    CouncilTurn,
    CouncilVote,
    RelationCandidate,
    RelationTypeScore,
)
from src.council.member_registry import CouncilMemberRegistry
from src.llm.provider_auth import HttpxConnectionTransport, ProviderConnectionResult
from src.domain.models import DynamicRelation

logger = logging.getLogger(__name__)


class CouncilService:
    """In-memory council queue and adjudication workflow."""

    def __init__(self, domain_adapter=None, member_registry: Optional[CouncilMemberRegistry] = None, event_store=None):
        if domain_adapter is None:
            from src.bootstrap import get_domain_kg_adapter

            domain_adapter = get_domain_kg_adapter()

        self.settings = get_settings()
        self.domain_adapter = domain_adapter
        self._config = self._load_config()
        self.member_registry = member_registry or self._load_member_registry()
        self.event_store = event_store
        self._member_statuses: Dict[str, ProviderConnectionResult] = {}
        self._candidates: Dict[str, RelationCandidate] = {}
        self._cases: Dict[str, CouncilCase] = {}
        self._queue: List[str] = []

    def _load_config(self) -> Dict[str, Any]:
        defaults = {
            "thresholds": {
                "auto_approve": 0.75,
                "auto_reject": 0.40,
                "council_min": 0.60,
            },
            "limits": {
                "max_turns": 7,
                "max_repeated_defers": 2,
            },
            "high_impact_entities": [],
            "default_source_type": "research_note",
        }
        try:
            config = self.settings.load_yaml_config("council")
            defaults.update(config)
            return defaults
        except FileNotFoundError:
            return defaults

    def _load_member_registry(self) -> CouncilMemberRegistry:
        registry = CouncilMemberRegistry()
        try:
            config = self.settings.load_yaml_config("council_members")
            registry.load_from_config(config)
        except FileNotFoundError:
            logger.info("Council member config not found; registry starts empty")
        return registry

    def _baseline_relations(self, head_id: str, tail_id: str) -> List[Any]:
        return [
            rel
            for rel in self.domain_adapter.get_all_relations().values()
            if rel.head_id == head_id and rel.tail_id == tail_id
        ]

    def _to_entity_ref(self, entity: Optional[ResolvedEntity], fallback_id: str, fallback_name: Optional[str]) -> CandidateEntityRef:
        if entity is None:
            return CandidateEntityRef(
                entity_id=fallback_id,
                canonical_name=fallback_name or fallback_id,
            )

        return CandidateEntityRef(
            entity_id=entity.canonical_id or entity.entity_id,
            canonical_name=entity.canonical_name or fallback_name or fallback_id,
            entity_type=entity.canonical_type,
            normalization_confidence=entity.resolution_conf,
        )

    def assess_candidate(
        self,
        edge: RawEdge,
        validation_result: ValidationResult,
        resolved_entities: List[ResolvedEntity],
        source_document_id: str,
        chunk_id: Optional[str] = None,
        source_type: Optional[str] = None,
        source_metadata: Optional[Dict[str, Any]] = None,
    ) -> RelationCandidate:
        """Build a relation candidate and decide whether council review is required."""
        entity_map = {entity.entity_id: entity for entity in resolved_entities}
        head = self._to_entity_ref(entity_map.get(edge.head_entity_id), edge.head_entity_id, edge.head_canonical_name)
        tail = self._to_entity_ref(entity_map.get(edge.tail_entity_id), edge.tail_entity_id, edge.tail_canonical_name)

        baseline_relations = self._baseline_relations(head.entity_id, tail.entity_id)
        baseline_conflict = BaselineConflict.NONE
        baseline_relation_type = None
        baseline_polarity = None

        if baseline_relations:
            baseline_relation_type = baseline_relations[0].relation_type
            baseline_polarity = self._normalize_polarity(baseline_relations[0].sign)

            same_type = next((rel for rel in baseline_relations if rel.relation_type == edge.relation_type), None)
            if same_type:
                if self._normalize_polarity(same_type.sign) != self._normalize_polarity(
                    validation_result.sign_result.polarity_final if validation_result.sign_result else edge.polarity_guess
                ):
                    baseline_conflict = BaselineConflict.POLARITY_CONFLICT
            else:
                baseline_conflict = BaselineConflict.TYPE_CONFLICT

        confidence = validation_result.combined_conf
        triggers: List[CouncilTriggerReason] = []

        if validation_result.validation_passed and validation_result.destination == ValidationDestination.DOMAIN_CANDIDATE:
            if confidence < self._config["thresholds"]["auto_approve"]:
                triggers.append(CouncilTriggerReason.LOW_CONFIDENCE)

            if baseline_conflict != BaselineConflict.NONE:
                triggers.append(CouncilTriggerReason.BASELINE_CONTRADICTION)

            if validation_result.sign_result and validation_result.sign_result.sign_tag == SignTag.AMBIGUOUS:
                triggers.append(CouncilTriggerReason.POLARITY_AMBIGUITY)

            if validation_result.semantic_result and validation_result.semantic_result.semantic_tag == SemanticTag.SEM_AMBIGUOUS:
                triggers.append(CouncilTriggerReason.TEMPORAL_UNCERTAINTY)

            high_impact_entities = set(self._config.get("high_impact_entities", []))
            if (
                (head.entity_id in high_impact_entities or tail.entity_id in high_impact_entities)
                and confidence < self._config["thresholds"]["auto_approve"]
            ):
                triggers.append(CouncilTriggerReason.HIGH_IMPACT_RELATION)

        if not validation_result.validation_passed or validation_result.destination != ValidationDestination.DOMAIN_CANDIDATE:
            auto_decision = CouncilAutoDecision.AUTO_REJECT
            status = CandidateStatus.AUTO_REJECTED
            decision_reason = validation_result.rejection_reason or "not_eligible_for_domain"
        elif triggers:
            auto_decision = CouncilAutoDecision.SEND_TO_COUNCIL
            status = CandidateStatus.COUNCIL_PENDING
            decision_reason = ",".join(trigger.value for trigger in triggers)
        else:
            auto_decision = CouncilAutoDecision.AUTO_APPROVE
            status = CandidateStatus.AUTO_APPROVED
            decision_reason = "high_confidence_and_no_conflict"

        polarity = self._normalize_polarity(
            validation_result.sign_result.polarity_final if validation_result.sign_result else edge.polarity_guess
        )

        candidate = RelationCandidate(
            source_document_id=source_document_id,
            chunk_id=chunk_id or edge.fragment_id,
            source_type=source_type or self._config.get("default_source_type", "research_note"),
            source_metadata=source_metadata or {},
            citation_span=CitationSpan(text=edge.fragment_text or ""),
            head_entity=head,
            tail_entity=tail,
            entity_pair_key=f"{head.entity_id}__{tail.entity_id}",
            relation_type_candidate=edge.relation_type,
            relation_type_alternatives=[RelationTypeScore(type=edge.relation_type, score=confidence)],
            polarity_candidate=polarity,
            strength_candidate=confidence,
            time_scope_candidate="unknown",
            confidence=confidence,
            extraction_confidence=edge.student_conf or 0.0,
            validation_score=confidence,
            evidence_quality_score=validation_result.semantic_conf,
            auto_decision=auto_decision,
            auto_decision_reason=decision_reason,
            baseline_relation_exists=bool(baseline_relations),
            baseline_relation_type=baseline_relation_type,
            baseline_polarity=baseline_polarity,
            baseline_conflict=baseline_conflict,
            novelty_score=0.0 if baseline_relations else 1.0,
            council_required=auto_decision == CouncilAutoDecision.SEND_TO_COUNCIL,
            council_trigger_reasons=triggers,
            status=status,
            final_relation_type=edge.relation_type if status == CandidateStatus.AUTO_APPROVED else None,
            final_polarity=polarity if status == CandidateStatus.AUTO_APPROVED else None,
            final_strength=confidence if status == CandidateStatus.AUTO_APPROVED else None,
            final_confidence=confidence if status == CandidateStatus.AUTO_APPROVED else None,
            decision_reason=decision_reason,
        )
        candidate.status = CandidateStatus.AUTO_EVALUATED if status in {CandidateStatus.AUTO_APPROVED, CandidateStatus.AUTO_REJECTED} else status
        if auto_decision == CouncilAutoDecision.AUTO_APPROVE:
            candidate.status = CandidateStatus.AUTO_APPROVED
        elif auto_decision == CouncilAutoDecision.AUTO_REJECT:
            candidate.status = CandidateStatus.AUTO_REJECTED

        return candidate

    def submit_candidate(
        self,
        edge: RawEdge,
        validation_result: ValidationResult,
        resolved_entities: List[ResolvedEntity],
        source_document_id: str,
        chunk_id: Optional[str] = None,
        source_type: Optional[str] = None,
        source_metadata: Optional[Dict[str, Any]] = None,
    ) -> RelationCandidate:
        candidate = self.assess_candidate(
            edge=edge,
            validation_result=validation_result,
            resolved_entities=resolved_entities,
            source_document_id=source_document_id,
            chunk_id=chunk_id,
            source_type=source_type,
            source_metadata=source_metadata,
        )
        self._candidates[candidate.candidate_id] = candidate

        if candidate.council_required:
            case = CouncilCase(
                candidate_id=candidate.candidate_id,
                trigger_reasons=list(candidate.council_trigger_reasons),
            )
            self._cases[case.case_id] = case
            self._queue.append(case.case_id)
            candidate.council_case_id = case.case_id
            candidate.updated_at = case.updated_at

        self._log_event("council_candidate", candidate.model_dump(mode="json"))
        return candidate

    def record_turn(
        self,
        case_id: str,
        role: CouncilRole,
        agent_id: str,
        claim: str,
        decision: Optional[CouncilDecision] = None,
        confidence: Optional[float] = None,
        evidence: Optional[str] = None,
        risk: Optional[str] = None,
    ) -> CouncilTurn:
        case = self._cases[case_id]
        if len(case.turns) >= self._config["limits"]["max_turns"]:
            raise ValueError("max council turns exceeded")

        turn = CouncilTurn(
            turn=len(case.turns) + 1,
            role=role,
            agent_id=agent_id,
            claim=claim,
            decision=decision,
            confidence=confidence,
            evidence=evidence,
            risk=risk,
        )
        case.turns.append(turn)
        case.updated_at = turn.created_at

        candidate = self._candidates[case.candidate_id]
        candidate.council_turns.append(turn)
        candidate.updated_at = turn.created_at
        return turn

    def cast_vote(
        self,
        case_id: str,
        agent_id: str,
        decision: CouncilDecision,
        confidence: float,
        rationale: str,
    ) -> CouncilVote:
        case = self._cases[case_id]
        vote = CouncilVote(
            agent_id=agent_id,
            decision=decision,
            confidence=confidence,
            rationale=rationale,
        )
        case.votes.append(vote)
        case.updated_at = vote.created_at

        candidate = self._candidates[case.candidate_id]
        candidate.council_votes.append(vote)
        candidate.updated_at = vote.created_at
        return vote

    def finalize_case(
        self,
        case_id: str,
        adjudicator_id: str = "adjudicator",
        apply_to_domain: bool = False,
    ) -> RelationCandidate:
        case = self._cases[case_id]
        candidate = self._candidates[case.candidate_id]

        decision_scores = defaultdict(float)
        for vote in case.votes:
            decision_scores[vote.decision] += vote.confidence

        if not decision_scores:
            final_decision = CouncilDecision.DEFER
        else:
            ranked = sorted(decision_scores.items(), key=lambda item: item[1], reverse=True)
            if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
                final_decision = CouncilDecision.DEFER
            else:
                final_decision = ranked[0][0]

        summary = f"{final_decision.value} after {len(case.votes)} vote(s)"
        case.final_decision = final_decision
        case.status = CouncilCaseStatus.CLOSED

        if final_decision == CouncilDecision.APPROVE:
            candidate.status = CandidateStatus.COUNCIL_APPROVED
            candidate.final_relation_type = candidate.relation_type_candidate
            candidate.final_polarity = candidate.polarity_candidate
            candidate.final_strength = candidate.strength_candidate
            candidate.final_confidence = max((vote.confidence for vote in case.votes), default=candidate.confidence)
        elif final_decision == CouncilDecision.REJECT:
            candidate.status = CandidateStatus.COUNCIL_REJECTED
            candidate.final_confidence = max((vote.confidence for vote in case.votes), default=candidate.confidence)
        else:
            case.defer_count += 1
            defer_limit = max(int(self._config["limits"].get("max_repeated_defers", 0)), 0)
            if defer_limit and case.defer_count >= defer_limit:
                candidate.status = CandidateStatus.HUMAN_REVIEW_REQUIRED
                summary = (
                    f"{final_decision.value} after {len(case.votes)} vote(s); "
                    f"escalated to human review after {case.defer_count} defers"
                )
            else:
                candidate.status = CandidateStatus.COUNCIL_DEFERRED
            candidate.final_confidence = max((vote.confidence for vote in case.votes), default=candidate.confidence)

        case.summary = summary
        candidate.council_summary = summary
        candidate.decision_reason = summary
        candidate.decision_trace_id = case.case_id
        candidate.updated_at = case.updated_at

        self.record_turn(
            case_id=case_id,
            role=CouncilRole.ADJUDICATOR,
            agent_id=adjudicator_id,
            claim=summary,
            decision=final_decision,
            confidence=candidate.final_confidence,
        )

        if case_id in self._queue:
            self._queue.remove(case_id)

        if apply_to_domain and candidate.status == CandidateStatus.COUNCIL_APPROVED:
            self.apply_candidate(candidate.candidate_id)

        self._log_event("council_final", candidate.model_dump(mode="json"))
        return candidate

    def get_candidate(self, candidate_id: str) -> Optional[RelationCandidate]:
        return self._candidates.get(candidate_id)

    def get_case(self, case_id: str) -> Optional[CouncilCase]:
        return self._cases.get(case_id)

    def list_pending_cases(self) -> List[CouncilCase]:
        return [self._cases[case_id] for case_id in self._queue]

    def list_cases(self, status: Optional[str] = None) -> List[CouncilCase]:
        cases = list(self._cases.values())
        if status == "pending":
            return [case for case in cases if case.status == CouncilCaseStatus.OPEN]
        if status == "closed":
            return [case for case in cases if case.status == CouncilCaseStatus.CLOSED]
        return cases

    def retry_case(self, case_id: str) -> CouncilCase:
        case = self._cases[case_id]
        defer_limit = max(int(self._config["limits"].get("max_repeated_defers", 0)), 0)
        if defer_limit and case.defer_count >= defer_limit:
            raise ValueError("max repeated defers exceeded; human review required")
        case.status = CouncilCaseStatus.OPEN
        case.final_decision = None
        case.summary = None
        case.votes = []
        case.updated_at = case.created_at
        candidate = self._candidates[case.candidate_id]
        candidate.status = CandidateStatus.COUNCIL_PENDING
        candidate.council_summary = None
        candidate.decision_reason = None
        if case_id not in self._queue:
            self._queue.append(case_id)
        return case

    def apply_candidate(self, candidate_id: str) -> RelationCandidate:
        candidate = self._candidates[candidate_id]
        if candidate.status != CandidateStatus.COUNCIL_APPROVED:
            return candidate

        relation = self.domain_adapter.get_relation(
            candidate.head_entity.entity_id,
            candidate.tail_entity.entity_id,
            candidate.final_relation_type or candidate.relation_type_candidate,
        )
        if relation is None:
            relation = DynamicRelation(
                head_id=candidate.head_entity.entity_id,
                head_name=candidate.head_entity.canonical_name,
                tail_id=candidate.tail_entity.entity_id,
                tail_name=candidate.tail_entity.canonical_name,
                relation_type=candidate.final_relation_type or candidate.relation_type_candidate,
                sign=self._denormalize_polarity(candidate.final_polarity),
                domain_conf=candidate.final_confidence or candidate.confidence,
                evidence_count=1,
                origin="council",
                semantic_tags=["council_reviewed"],
            )
        else:
            relation.sign = self._denormalize_polarity(candidate.final_polarity)
            relation.domain_conf = max(relation.domain_conf, candidate.final_confidence or candidate.confidence)
            relation.evidence_count += 1
            if "council_reviewed" not in relation.semantic_tags:
                relation.semantic_tags.append("council_reviewed")

        self.domain_adapter.upsert_relation(relation)
        return candidate

    def get_stats(self) -> Dict[str, int]:
        return {
            "candidates": len(self._candidates),
            "cases": len(self._cases),
            "pending_cases": len(self._queue),
            "closed_cases": len([case for case in self._cases.values() if case.status == CouncilCaseStatus.CLOSED]),
            "configured_members": len(self.member_registry.list_members(enabled_only=False)),
            "available_members": len(self.get_available_members()),
        }

    def refresh_member_availability(self, env: Optional[Dict[str, str]] = None, transport=None) -> Dict[str, ProviderConnectionResult]:
        connection_transport = transport or HttpxConnectionTransport()
        self._member_statuses = self.member_registry.test_all_connections(
            transport=connection_transport,
            env=env,
            enabled_only=True,
        )
        self.member_registry.assign_models(self._member_statuses, enabled_only=True)
        return self._member_statuses.copy()

    def get_member_statuses(self) -> Dict[str, ProviderConnectionResult]:
        return self._member_statuses.copy()

    def get_available_members(self) -> List[str]:
        return [
            member_id
            for member_id, result in self._member_statuses.items()
            if result.success
        ]

    def _log_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        if self.event_store is None:
            return
        self.event_store.append(event_type, payload)

    @staticmethod
    def _normalize_polarity(value: Any) -> str:
        if value in {"+", "positive"}:
            return "positive"
        if value in {"-", "negative"}:
            return "negative"
        if value == "neutral":
            return "neutral"
        return "unknown"

    @staticmethod
    def _denormalize_polarity(value: Any) -> str:
        if value == "positive":
            return "+"
        if value == "negative":
            return "-"
        if value == "neutral":
            return "neutral"
        return "unknown"
