"""Background worker for automatic council adjudication."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime
from typing import Dict, Mapping, Optional

from src.council.models import CouncilDecision, CouncilRole
from src.llm.provider_inference import (
    HttpxInferenceTransport,
    InferenceTransport,
    ProviderInferenceManager,
    ProviderInferenceRequest,
)

logger = logging.getLogger(__name__)


class CouncilAutomationWorker:
    """Poll pending council cases and adjudicate them with available model members."""

    def __init__(self, service, poll_interval_seconds: float = 5.0, inference_manager: Optional[ProviderInferenceManager] = None):
        self.service = service
        self.poll_interval_seconds = poll_interval_seconds
        self.inference_manager = inference_manager or ProviderInferenceManager()
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.last_run_at: Optional[str] = None
        self.last_error: Optional[str] = None

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.is_running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="council-automation-worker")

    async def stop(self) -> None:
        self._running = False
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def process_pending_once(self, env: Optional[Mapping[str, str]] = None, transport: Optional[InferenceTransport] = None) -> Dict[str, int]:
        processed = 0
        finalized = 0
        for case in self.service.list_pending_cases():
            result = self.process_case(case.case_id, env=env, transport=transport)
            processed += 1
            if result:
                finalized += 1
        self.last_run_at = datetime.utcnow().isoformat() + "Z"
        return {"processed": processed, "finalized": finalized}

    def process_case(self, case_id: str, env: Optional[Mapping[str, str]] = None, transport: Optional[InferenceTransport] = None):
        case = self.service.get_case(case_id)
        if case is None:
            return None

        candidate = self.service.get_candidate(case.candidate_id)
        if candidate is None:
            return None

        available_members = self._select_available_members()
        if not available_members:
            self.last_error = "no_available_council_members"
            logger.warning("Council worker skipped case %s: no available members", case_id)
            return None

        transport = transport or HttpxInferenceTransport()
        votes_cast = 0
        for member_id, member in available_members.items():
            model_name = member.effective_model_name
            if not model_name:
                logger.warning("Council worker skipped member %s: no model assigned", member_id)
                continue

            role = member.role
            prompt = self._build_prompt(role=role.value, candidate=candidate.model_dump())
            response = self.inference_manager.infer(
                config=member.auth,
                request=ProviderInferenceRequest(
                    model_name=model_name,
                    system_prompt=prompt["system"],
                    user_prompt=prompt["user"],
                ),
                transport=transport,
                env=env,
            )
            payload = self.inference_manager.parse_json_content(response)
            decision = CouncilDecision(payload.get("decision", "DEFER"))
            confidence = float(payload.get("confidence", 0.5))
            claim = payload.get("claim") or payload.get("rationale") or "No claim provided"
            rationale = payload.get("rationale") or claim

            self.service.record_turn(
                case_id=case_id,
                role=role,
                agent_id=member_id,
                claim=claim,
                decision=decision,
                confidence=confidence,
                evidence=payload.get("evidence"),
                risk=payload.get("risk"),
            )
            self.service.cast_vote(
                case_id=case_id,
                agent_id=member_id,
                decision=decision,
                confidence=confidence,
                rationale=rationale,
            )
            votes_cast += 1

        if votes_cast == 0:
            self.last_error = "no_assigned_models"
            logger.warning("Council worker skipped case %s: no members had an assigned model", case_id)
            return None

        return self.service.finalize_case(case_id=case_id, adjudicator_id="auto-adjudicator", apply_to_domain=True)

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self.process_pending_once()
                self.last_error = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - exercised in live runtime
                self.last_error = str(exc)
                logger.warning("Council worker iteration failed: %s", exc)
            await asyncio.sleep(self.poll_interval_seconds)

    def _select_available_members(self) -> Dict[str, object]:
        available = set(self.service.get_available_members())
        selected: Dict[str, object] = {}
        preferred_roles = {
            CouncilRole.PROPOSER,
            CouncilRole.CHALLENGER,
            CouncilRole.EVIDENCE_AUDITOR,
        }
        for member in self.service.member_registry.list_members(enabled_only=True):
            if member.member_id not in available:
                continue
            if member.role in preferred_roles and member.role not in {item.role for item in selected.values()}:
                selected[member.member_id] = member
        return selected

    @staticmethod
    def _build_prompt(role: str, candidate: Dict[str, object]) -> Dict[str, str]:
        system = (
            "You are a finance ontology council member. "
            "Return strict JSON with keys: claim, decision, confidence, rationale, evidence, risk. "
            "Decision must be one of APPROVE, REJECT, DEFER."
        )
        user = (
            f"Role: {role}\n"
            "Review the following finance relation candidate and produce a vote.\n"
            f"Candidate: {candidate}\n"
            "Focus on finance plausibility, conflict with baseline, and evidence quality."
        )
        return {"system": system, "user": user}
