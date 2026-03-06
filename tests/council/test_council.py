"""Council adjudication tests."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.bootstrap import reset_all, get_domain_kg_adapter
from src.council.models import (
    CandidateStatus,
    CouncilDecision,
    CouncilRole,
    CouncilTriggerReason,
)
from src.council.service import CouncilService
from src.shared.models import RawEdge, ResolvedEntity, ResolutionMode, Polarity
from src.validation.models import (
    ValidationDestination,
    ValidationResult,
    SchemaValidationResult,
    SignTag,
    SignValidationResult,
    SemanticTag,
    SemanticValidationResult,
)


def create_validation_result(
    edge_id: str,
    combined_conf: float,
    destination: ValidationDestination = ValidationDestination.DOMAIN_CANDIDATE,
    sign_tag: SignTag = SignTag.CONFIDENT,
    semantic_tag: SemanticTag = SemanticTag.SEM_CONFIDENT,
    sign_polarity: str = "-",
) -> ValidationResult:
    return ValidationResult(
        edge_id=edge_id,
        validation_passed=True,
        destination=destination,
        combined_conf=combined_conf,
        student_conf=combined_conf,
        sign_score=combined_conf,
        semantic_conf=combined_conf,
        schema_result=SchemaValidationResult(edge_id=edge_id, schema_valid=True),
        sign_result=SignValidationResult(
            edge_id=edge_id,
            polarity_final=sign_polarity,
            sign_tag=sign_tag,
            sign_consistency_score=combined_conf,
        ),
        semantic_result=SemanticValidationResult(
            edge_id=edge_id,
            semantic_tag=semantic_tag,
            semantic_confidence=combined_conf,
        ),
    )


class TestCouncilService:
    def setup_method(self):
        reset_all()

    def teardown_method(self):
        reset_all()

    def test_auto_approve_clear_non_high_impact_candidate(self):
        service = CouncilService(domain_adapter=get_domain_kg_adapter())
        edge = RawEdge(
            raw_edge_id="R100",
            head_entity_id="E1",
            tail_entity_id="E2",
            relation_type="affects",
            polarity_guess=Polarity.NEGATIVE,
            student_conf=0.88,
            fragment_id="frag-1",
            fragment_text="Custom factor affects custom asset pricing.",
        )
        resolved = [
            ResolvedEntity(
                entity_id="E1",
                canonical_id="Custom_Factor",
                canonical_name="custom factor",
                canonical_type="MacroIndicator",
                resolution_mode=ResolutionMode.NEW_ENTITY,
                resolution_conf=0.9,
                surface_text="custom factor",
                fragment_id="frag-1",
            ),
            ResolvedEntity(
                entity_id="E2",
                canonical_id="Custom_Asset",
                canonical_name="custom asset",
                canonical_type="AssetGroup",
                resolution_mode=ResolutionMode.NEW_ENTITY,
                resolution_conf=0.9,
                surface_text="custom asset",
                fragment_id="frag-1",
            ),
        ]

        candidate = service.submit_candidate(
            edge=edge,
            validation_result=create_validation_result("R100", 0.88),
            resolved_entities=resolved,
            source_document_id="doc_custom_001",
        )

        assert candidate.status == CandidateStatus.AUTO_APPROVED
        assert candidate.council_required is False
        assert candidate.final_relation_type == "affects"

    def test_send_to_council_for_high_impact_mid_confidence(self):
        service = CouncilService(domain_adapter=get_domain_kg_adapter())
        edge = RawEdge(
            raw_edge_id="R101",
            head_entity_id="E1",
            tail_entity_id="E2",
            relation_type="pressures",
            polarity_guess=Polarity.NEGATIVE,
            student_conf=0.68,
            fragment_id="frag-2",
            fragment_text="Higher policy rates pressure growth stocks.",
        )
        resolved = [
            ResolvedEntity(
                entity_id="E1",
                canonical_id="Policy_Rate",
                canonical_name="policy rate",
                canonical_type="MacroIndicator",
                resolution_mode=ResolutionMode.DICTIONARY_MATCH,
                resolution_conf=0.95,
                surface_text="policy rate",
                fragment_id="frag-2",
            ),
            ResolvedEntity(
                entity_id="E2",
                canonical_id="Growth_Stocks",
                canonical_name="growth stocks",
                canonical_type="AssetGroup",
                resolution_mode=ResolutionMode.DICTIONARY_MATCH,
                resolution_conf=0.95,
                surface_text="growth stocks",
                fragment_id="frag-2",
            ),
        ]

        candidate = service.submit_candidate(
            edge=edge,
            validation_result=create_validation_result("R101", 0.68),
            resolved_entities=resolved,
            source_document_id="doc_macro_001",
        )

        assert candidate.status == CandidateStatus.COUNCIL_PENDING
        assert candidate.council_case_id is not None
        assert CouncilTriggerReason.LOW_CONFIDENCE in candidate.council_trigger_reasons
        assert CouncilTriggerReason.HIGH_IMPACT_RELATION in candidate.council_trigger_reasons
        assert len(service.list_pending_cases()) == 1

    def test_send_to_council_for_baseline_contradiction(self):
        service = CouncilService(domain_adapter=get_domain_kg_adapter())
        edge = RawEdge(
            raw_edge_id="R102",
            head_entity_id="E1",
            tail_entity_id="E2",
            relation_type="supports",
            polarity_guess=Polarity.POSITIVE,
            student_conf=0.86,
            fragment_id="frag-3",
            fragment_text="Higher policy rates support growth stocks.",
        )
        resolved = [
            ResolvedEntity(
                entity_id="E1",
                canonical_id="Policy_Rate",
                canonical_name="policy rate",
                canonical_type="MacroIndicator",
                resolution_mode=ResolutionMode.DICTIONARY_MATCH,
                resolution_conf=0.95,
                surface_text="policy rate",
                fragment_id="frag-3",
            ),
            ResolvedEntity(
                entity_id="E2",
                canonical_id="Growth_Stocks",
                canonical_name="growth stocks",
                canonical_type="AssetGroup",
                resolution_mode=ResolutionMode.DICTIONARY_MATCH,
                resolution_conf=0.95,
                surface_text="growth stocks",
                fragment_id="frag-3",
            ),
        ]

        candidate = service.submit_candidate(
            edge=edge,
            validation_result=create_validation_result("R102", 0.86, sign_polarity="+"),
            resolved_entities=resolved,
            source_document_id="doc_macro_002",
        )

        assert candidate.status == CandidateStatus.COUNCIL_PENDING
        assert CouncilTriggerReason.BASELINE_CONTRADICTION in candidate.council_trigger_reasons

    def test_finalize_case_from_votes(self):
        service = CouncilService(domain_adapter=get_domain_kg_adapter())
        edge = RawEdge(
            raw_edge_id="R103",
            head_entity_id="E1",
            tail_entity_id="E2",
            relation_type="pressures",
            polarity_guess=Polarity.NEGATIVE,
            student_conf=0.68,
            fragment_id="frag-4",
            fragment_text="Higher policy rates pressure growth stocks.",
        )
        resolved = [
            ResolvedEntity(
                entity_id="E1",
                canonical_id="Policy_Rate",
                canonical_name="policy rate",
                canonical_type="MacroIndicator",
                resolution_mode=ResolutionMode.DICTIONARY_MATCH,
                resolution_conf=0.95,
                surface_text="policy rate",
                fragment_id="frag-4",
            ),
            ResolvedEntity(
                entity_id="E2",
                canonical_id="Growth_Stocks",
                canonical_name="growth stocks",
                canonical_type="AssetGroup",
                resolution_mode=ResolutionMode.DICTIONARY_MATCH,
                resolution_conf=0.95,
                surface_text="growth stocks",
                fragment_id="frag-4",
            ),
        ]

        candidate = service.submit_candidate(
            edge=edge,
            validation_result=create_validation_result("R103", 0.68),
            resolved_entities=resolved,
            source_document_id="doc_macro_003",
        )

        service.record_turn(
            candidate.council_case_id,
            role=CouncilRole.PROPOSER,
            agent_id="proposer_01",
            claim="This relation aligns with the finance baseline but remains high impact.",
            decision=CouncilDecision.APPROVE,
            confidence=0.70,
        )
        service.cast_vote(candidate.council_case_id, "neutral_01", CouncilDecision.APPROVE, 0.72, "Baseline-aligned.")
        service.cast_vote(candidate.council_case_id, "neutral_02", CouncilDecision.APPROVE, 0.66, "Evidence is direct.")
        service.cast_vote(candidate.council_case_id, "neutral_03", CouncilDecision.REJECT, 0.40, "Confidence is modest.")

        finalized = service.finalize_case(candidate.council_case_id)

        assert finalized.status == CandidateStatus.COUNCIL_APPROVED
        assert finalized.final_relation_type == "pressures"
        assert finalized.council_summary is not None

    def test_repeated_defers_escalate_to_human_review(self):
        service = CouncilService(domain_adapter=get_domain_kg_adapter())
        edge = RawEdge(
            raw_edge_id="R104",
            head_entity_id="E1",
            tail_entity_id="E2",
            relation_type="pressures",
            polarity_guess=Polarity.NEGATIVE,
            student_conf=0.61,
            fragment_id="frag-5",
            fragment_text="Higher policy rates pressure growth stocks.",
        )
        resolved = [
            ResolvedEntity(
                entity_id="E1",
                canonical_id="Policy_Rate",
                canonical_name="policy rate",
                canonical_type="MacroIndicator",
                resolution_mode=ResolutionMode.DICTIONARY_MATCH,
                resolution_conf=0.95,
                surface_text="policy rate",
                fragment_id="frag-5",
            ),
            ResolvedEntity(
                entity_id="E2",
                canonical_id="Growth_Stocks",
                canonical_name="growth stocks",
                canonical_type="AssetGroup",
                resolution_mode=ResolutionMode.DICTIONARY_MATCH,
                resolution_conf=0.95,
                surface_text="growth stocks",
                fragment_id="frag-5",
            ),
        ]

        candidate = service.submit_candidate(
            edge=edge,
            validation_result=create_validation_result("R104", 0.61),
            resolved_entities=resolved,
            source_document_id="doc_macro_004",
        )

        service.cast_vote(candidate.council_case_id, "neutral_01", CouncilDecision.DEFER, 0.60, "Need more evidence.")
        first = service.finalize_case(candidate.council_case_id)
        assert first.status == CandidateStatus.COUNCIL_DEFERRED

        service.retry_case(candidate.council_case_id)
        service.cast_vote(candidate.council_case_id, "neutral_01", CouncilDecision.DEFER, 0.62, "Still ambiguous.")
        second = service.finalize_case(candidate.council_case_id)

        assert second.status == CandidateStatus.HUMAN_REVIEW_REQUIRED
        with pytest.raises(ValueError, match="human review required"):
            service.retry_case(candidate.council_case_id)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
