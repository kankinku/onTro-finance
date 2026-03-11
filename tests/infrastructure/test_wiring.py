"""Wiring Integration 테스트 - 인프라와 도메인 연결 검증"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.required_env_validator import summarize_runtime_env, validate_required_runtime_env
from config.settings import Settings, StoreSettings, load_project_env
from src.bootstrap import (
    build_graph_repository,
    build_llm_client,
    get_domain_kg_adapter,
    get_graph_repository,
    get_llm_gateway,
    get_personal_kg_adapter,
    get_transaction_manager,
    reset_all,
)
from src.domain.models import DynamicRelation
from src.personal.models import PersonalLabel, PersonalRelation, SourceType


class TestBootstrapWiring:
    """Bootstrap이 모든 컴포넌트를 올바르게 연결하는지 확인"""

    def setup_method(self):
        reset_all()

    def teardown_method(self):
        reset_all()

    def test_get_graph_repository(self):
        repo = get_graph_repository()
        assert repo is not None
        # 싱글톤 확인
        assert get_graph_repository() is repo

    def test_storage_backend_can_be_overridden_by_env(self, monkeypatch):
        monkeypatch.setenv("ONTRO_STORAGE_BACKEND", "inmemory")

        repo = build_graph_repository({"storage": {"backend": "neo4j"}})

        assert repo.__class__.__name__ == "InMemoryGraphRepository"

    def test_neo4j_user_deprecated_alias_is_still_supported(self, monkeypatch):
        captured = {}

        class DummyNeo4jRepository:
            def __init__(self, uri: str, user: str, password: str, database: str = "neo4j"):
                captured.update(
                    {
                        "uri": uri,
                        "user": user,
                        "password": password,
                        "database": database,
                    }
                )

        monkeypatch.setenv("ONTRO_STORAGE_BACKEND", "neo4j")
        monkeypatch.delenv("ONTRO_NEO4J_USER", raising=False)
        monkeypatch.setenv("ONTRO_NEO4J_USERNAME", "legacy-user")
        monkeypatch.setenv("ONTRO_NEO4J_PASSWORD", "secret")
        monkeypatch.setattr(
            "src.storage.neo4j_repository.Neo4jGraphRepository", DummyNeo4jRepository
        )

        build_graph_repository(
            {
                "storage": {
                    "backend": "neo4j",
                    "neo4j": {
                        "uri": "bolt://example:7687",
                        "database": "neo4j",
                    },
                }
            }
        )

        assert captured["user"] == "legacy-user"

    def test_dotenv_file_can_supply_runtime_env(self, monkeypatch, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "\n".join(
                [
                    "ONTRO_STORAGE_BACKEND=inmemory",
                    "ONTRO_NEO4J_URI=bolt://from-env:7687",
                ]
            ),
            encoding="utf-8",
        )

        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("ONTRO_STORAGE_BACKEND", raising=False)
        monkeypatch.delenv("ONTRO_NEO4J_URI", raising=False)

        loaded = load_project_env(force=True)

        assert loaded == env_file.resolve()
        assert os.environ["ONTRO_NEO4J_URI"] == "bolt://from-env:7687"
        assert (
            build_graph_repository({"storage": {"backend": "neo4j"}}).__class__.__name__
            == "InMemoryGraphRepository"
        )

    def test_dotenv_does_not_override_existing_shell_env(self, monkeypatch, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("ONTRO_STORAGE_BACKEND=neo4j\n", encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ONTRO_STORAGE_BACKEND", "inmemory")

        load_project_env(force=True)

        assert os.environ["ONTRO_STORAGE_BACKEND"] == "inmemory"

    def test_runtime_env_validation_requires_neo4j_credentials(self, monkeypatch):
        monkeypatch.setenv("ONTRO_STORAGE_BACKEND", "neo4j")
        monkeypatch.delenv("ONTRO_NEO4J_URI", raising=False)
        monkeypatch.delenv("ONTRO_NEO4J_USER", raising=False)
        monkeypatch.delenv("ONTRO_NEO4J_USERNAME", raising=False)
        monkeypatch.delenv("ONTRO_NEO4J_PASSWORD", raising=False)

        with pytest.raises(ValueError, match="Missing required runtime environment variables"):
            validate_required_runtime_env({"storage": {"backend": "neo4j", "neo4j": {}}})

    def test_runtime_env_validation_allows_inmemory_without_external_credentials(self, monkeypatch):
        monkeypatch.setenv("ONTRO_STORAGE_BACKEND", "inmemory")
        monkeypatch.delenv("ONTRO_NEO4J_URI", raising=False)
        monkeypatch.delenv("ONTRO_NEO4J_USER", raising=False)
        monkeypatch.delenv("ONTRO_NEO4J_PASSWORD", raising=False)

        validate_required_runtime_env({"storage": {"backend": "inmemory"}})

    def test_runtime_env_validation_requires_openai_credentials_when_backend_selected(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            validate_required_runtime_env(
                {
                    "storage": {"backend": "inmemory"},
                    "llm": {
                        "backend": "openai",
                        "openai": {
                            "auth": {
                                "auth_type": "api_key",
                                "api_key_env": "OPENAI_API_KEY",
                            }
                        },
                    },
                }
            )

    def test_runtime_env_summary_reports_loaded_switches(self, monkeypatch):
        monkeypatch.setenv("ONTRO_STORAGE_BACKEND", "inmemory")
        monkeypatch.setenv("ONTRO_COUNCIL_AUTO_ENABLED", "false")
        summary = summarize_runtime_env({"storage": {"backend": "inmemory"}})

        assert summary["storage_backend"] == "inmemory"
        assert "ONTRO_STORAGE_BACKEND" in summary["loaded_env_names"]

    def test_packaged_runtime_keeps_read_only_domain_data_under_resource_root(self):
        settings = Settings(
            project_root=Path("/bundle/resources"),
            app_home=Path("/bundle/runtime"),
            store=StoreSettings(
                graph_db_path="data/graph.db",
                document_db_path="data/documents.db",
                vector_db_path="data/vectors",
                domain_data_path=Path("data/domain"),
                raw_data_path=Path("data/raw"),
                personal_data_path=Path("data/personal"),
                learning_data_path=Path("data/learning"),
            ),
        ).normalize_paths()

        assert settings.store.domain_data_path == Path("/bundle/resources/data/domain")
        assert settings.store.raw_data_path == Path("/bundle/runtime/data/raw")
        assert settings.store.personal_data_path == Path("/bundle/runtime/data/personal")
        assert settings.store.learning_data_path == Path("/bundle/runtime/data/learning")

    def test_get_transaction_manager(self):
        tx_mgr = get_transaction_manager()
        assert tx_mgr is not None
        # repo 공유 확인
        assert tx_mgr._repo is get_graph_repository()

    def test_get_llm_gateway(self):
        gateway = get_llm_gateway()
        assert gateway is not None
        # 싱글톤 확인
        assert get_llm_gateway() is gateway

    def test_build_llm_client_supports_openai_backend_with_env_ref(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        client = build_llm_client(
            {
                "llm": {
                    "backend": "openai",
                    "openai": {
                        "base_url": "https://api.openai.com/v1",
                        "model": "gpt-4o-mini",
                        "timeout": 45,
                        "auth": {
                            "auth_type": "api_key",
                            "api_key_env": "OPENAI_API_KEY",
                            "healthcheck_path": "/models",
                        },
                    },
                }
            }
        )

        assert client.__class__.__name__ == "OpenAICompatibleLLMClient"
        assert client.get_model_name() == "gpt-4o-mini"
        assert client.auth_config.base_url == "https://api.openai.com/v1"

    def test_build_llm_client_openai_backend_rejects_missing_credentials(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with pytest.raises(ValueError, match="OpenAI backend requires credentials"):
            build_llm_client(
                {
                    "llm": {
                        "backend": "openai",
                        "openai": {
                            "model": "gpt-4o-mini",
                            "auth": {
                                "auth_type": "api_key",
                                "api_key_env": "OPENAI_API_KEY",
                            },
                        },
                    }
                }
            )

    def test_get_domain_kg_adapter(self):
        adapter = get_domain_kg_adapter()
        assert adapter is not None
        # repo 공유 확인
        assert adapter._repo is get_graph_repository()


class TestDomainKGAdapter:
    """Domain KG Adapter가 GraphRepository를 통해 올바르게 동작하는지 확인"""

    def setup_method(self):
        reset_all()

    def teardown_method(self):
        reset_all()

    def test_upsert_and_get_relation(self):
        adapter = get_domain_kg_adapter()

        relation = DynamicRelation(
            head_id="gold",
            head_name="Gold",
            tail_id="inflation",
            tail_name="Inflation",
            relation_type="Affect",
            sign="+",
            domain_conf=0.8,
            evidence_count=5,
        )

        adapter.upsert_relation(relation)

        # 조회
        fetched = adapter.get_relation("gold", "inflation", "Affect")
        assert fetched is not None
        assert fetched.sign == "+"
        assert fetched.domain_conf == 0.8

    def test_get_all_relations(self):
        adapter = get_domain_kg_adapter()
        before_count = len(adapter.get_all_relations())

        r1 = DynamicRelation(
            head_id="A",
            head_name="A",
            tail_id="B",
            tail_name="B",
            relation_type="supports",
            sign="+",
        )
        r2 = DynamicRelation(
            head_id="C",
            head_name="C",
            tail_id="D",
            tail_name="D",
            relation_type="pressures",
            sign="-",
        )

        adapter.upsert_relation(r1)
        adapter.upsert_relation(r2)

        all_rels = adapter.get_all_relations()
        assert len(all_rels) == before_count + 2
        assert any(rel.head_id == "A" and rel.tail_id == "B" for rel in all_rels.values())
        assert any(rel.head_id == "C" and rel.tail_id == "D" for rel in all_rels.values())

    def test_with_transaction(self):
        adapter = get_domain_kg_adapter()
        tx_mgr = get_transaction_manager()

        # 트랜잭션 내에서 저장
        with tx_mgr.transaction() as tx:
            relation = DynamicRelation(
                head_id="X",
                head_name="X",
                tail_id="Y",
                tail_name="Y",
                relation_type="Affect",
                sign="+",
            )
            adapter.upsert_relation(relation, tx=tx)

        # 커밋 후 조회 가능
        fetched = adapter.get_relation("X", "Y", "Affect")
        assert fetched is not None


class TestPersonalKGAdapter:
    """Personal KG Adapter 테스트"""

    def setup_method(self):
        reset_all()

    def teardown_method(self):
        reset_all()

    def test_upsert_and_get_relation(self):
        adapter = get_personal_kg_adapter()

        relation = PersonalRelation(
            head_id="user_pref",
            head_name="UserPref",
            tail_id="gold",
            tail_name="Gold",
            relation_type="Prefer",
            sign="+",
            user_id="test_user",
            pcs_score=0.7,
            personal_weight=0.6,
            personal_label=PersonalLabel.STRONG_BELIEF,
            source_type=SourceType.USER_WRITTEN,
        )

        adapter.upsert_relation(relation)

        fetched = adapter.get_relation("user_pref", "gold", "Prefer")
        assert fetched is not None
        assert fetched.pcs_score == 0.7
        assert fetched.personal_label == PersonalLabel.STRONG_BELIEF

    def test_get_stats(self):
        adapter = get_personal_kg_adapter()

        r1 = PersonalRelation(
            head_id="A",
            head_name="A",
            tail_id="B",
            tail_name="B",
            relation_type="R1",
            sign="+",
            user_id="u1",
            pcs_score=0.8,
            personal_weight=0.5,
            personal_label=PersonalLabel.STRONG_BELIEF,
            source_type=SourceType.LLM_INFERRED,
        )
        r2 = PersonalRelation(
            head_id="C",
            head_name="C",
            tail_id="D",
            tail_name="D",
            relation_type="R2",
            sign="-",
            user_id="u1",
            pcs_score=0.4,
            personal_weight=0.3,
            personal_label=PersonalLabel.WEAK_BELIEF,
            source_type=SourceType.LLM_INFERRED,
        )

        adapter.upsert_relation(r1)
        adapter.upsert_relation(r2)

        stats = adapter.get_stats()
        assert stats["total_relations"] == 2
        assert stats["labels"]["strong"] == 1
        assert stats["labels"]["weak"] == 1


class TestLLMGatewayIntegration:
    """LLM Gateway 통합 테스트 (Mock 사용)"""

    def setup_method(self):
        reset_all()

    def test_generate_with_mock(self):
        from src.llm.gateway import LLMGateway
        from src.llm.ollama_adapter import MockLLMClient

        mock = MockLLMClient("Test response")
        gateway = LLMGateway(mock)

        response = gateway.generate("Test prompt")
        assert response.content == "Test response"

        stats = gateway.get_stats()
        assert stats["total_requests"] == 1
        assert stats["primary_success"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
