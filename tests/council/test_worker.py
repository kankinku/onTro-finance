import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.bootstrap import get_domain_kg_adapter, reset_all
from src.council.member_registry import CouncilMemberDefinition, CouncilMemberRegistry
from src.council.models import CandidateStatus, CouncilRole
from src.council.service import CouncilService
from src.council.worker import CouncilAutomationWorker
from src.llm.provider_auth import AuthType, ProviderAuthConfig, ProviderConnectionResult, ProviderKind
from src.shared.models import Polarity, RawEdge, ResolvedEntity, ResolutionMode
from src.validation.models import (
    SchemaValidationResult,
    SemanticTag,
    SemanticValidationResult,
    SignTag,
    SignValidationResult,
    ValidationDestination,
    ValidationResult,
)


class _FakeInferenceManager:
    def __init__(self):
        self.requests = []

    def infer(self, config, request, transport=None, env=None):
        self.requests.append(request)
        payload = {
            "claim": f"{request.model_name} approves the candidate",
            "decision": "APPROVE",
            "confidence": 0.81,
            "rationale": "Evidence is direct and finance-plausible.",
            "evidence": "Macro text supports the relation.",
            "risk": "limited",
        }
        return type("Response", (), {"content": json.dumps(payload), "raw_response": payload})()

    @staticmethod
    def parse_json_content(response):
        return json.loads(response.content)


def _validation_result(edge_id: str, combined_conf: float = 0.68) -> ValidationResult:
    return ValidationResult(
        edge_id=edge_id,
        validation_passed=True,
        destination=ValidationDestination.DOMAIN_CANDIDATE,
        combined_conf=combined_conf,
        student_conf=combined_conf,
        sign_score=combined_conf,
        semantic_conf=combined_conf,
        schema_result=SchemaValidationResult(edge_id=edge_id, schema_valid=True),
        sign_result=SignValidationResult(
            edge_id=edge_id,
            polarity_final="-",
            sign_tag=SignTag.CONFIDENT,
            sign_consistency_score=combined_conf,
        ),
        semantic_result=SemanticValidationResult(
            edge_id=edge_id,
            semantic_tag=SemanticTag.SEM_CONFIDENT,
            semantic_confidence=combined_conf,
        ),
    )


class TestCouncilAutomationWorker:
    def setup_method(self):
        reset_all()

    def teardown_method(self):
        reset_all()

    def test_worker_processes_pending_case_and_applies_relation(self):
        registry = CouncilMemberRegistry()
        for member_id, role in [
            ("proposer-openai", CouncilRole.PROPOSER),
            ("challenger-copilot", CouncilRole.CHALLENGER),
            ("auditor-local", CouncilRole.EVIDENCE_AUDITOR),
        ]:
            registry.register(
                CouncilMemberDefinition(
                    member_id=member_id,
                    role=role,
                    provider=ProviderKind.OLLAMA,
                    auth=ProviderAuthConfig(
                        provider=ProviderKind.OLLAMA,
                        auth_type=AuthType.NONE,
                        base_url="http://localhost:11434",
                    ),
                )
            )

        service = CouncilService(domain_adapter=get_domain_kg_adapter(), member_registry=registry)
        service._member_statuses = {
            member.member_id: ProviderConnectionResult(
                provider=member.provider,
                success=True,
                message="ok",
                available_models=["llama3.2", "qwen2.5", "mistral-nemo"],
            )
            for member in registry.list_members(enabled_only=True)
        }
        registry.assign_models(service._member_statuses)

        candidate = service.submit_candidate(
            edge=RawEdge(
                raw_edge_id="R200",
                head_entity_id="E1",
                tail_entity_id="E2",
                relation_type="pressures",
                polarity_guess=Polarity.NEGATIVE,
                student_conf=0.68,
                fragment_id="frag-200",
                fragment_text="Higher policy rates pressure growth stocks.",
            ),
            validation_result=_validation_result("R200"),
            resolved_entities=[
                ResolvedEntity(
                    entity_id="E1",
                    canonical_id="Policy_Rate",
                    canonical_name="policy rate",
                    canonical_type="MacroIndicator",
                    resolution_mode=ResolutionMode.DICTIONARY_MATCH,
                    resolution_conf=0.99,
                    surface_text="policy rate",
                    fragment_id="frag-200",
                ),
                ResolvedEntity(
                    entity_id="E2",
                    canonical_id="Growth_Stocks",
                    canonical_name="growth stocks",
                    canonical_type="AssetGroup",
                    resolution_mode=ResolutionMode.DICTIONARY_MATCH,
                    resolution_conf=0.99,
                    surface_text="growth stocks",
                    fragment_id="frag-200",
                ),
            ],
            source_document_id="doc-200",
        )

        inference_manager = _FakeInferenceManager()
        worker = CouncilAutomationWorker(service=service, inference_manager=inference_manager)
        result = worker.process_case(candidate.council_case_id, env={})

        assert result.status == CandidateStatus.COUNCIL_APPROVED
        assert [request.model_name for request in inference_manager.requests] == ["llama3.2", "qwen2.5", "mistral-nemo"]
        relation = service.domain_adapter.get_relation("Policy_Rate", "Growth_Stocks", "pressures")
        assert relation is not None
        assert relation.evidence_count >= 1
