"""Main API runtime and policy tests."""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import main as app_main
from config.settings import get_settings
from src.learning.event_store import LearningEventStore
from src.storage.inmemory_repository import InMemoryGraphRepository


class _DummyCouncil:
    def refresh_member_availability(self, env=None):
        return {}

    def get_stats(self):
        return {"pending_cases": 1, "closed_cases": 2, "configured_members": 3, "available_members": 2}

    def list_cases(self, status=None):
        case = SimpleNamespace(model_dump=lambda mode="json": {"case_id": "case_1", "status": status or "OPEN", "candidate_id": "rc_1"})
        return [case]

    def get_case(self, case_id):
        return SimpleNamespace(model_dump=lambda mode="json": {"case_id": case_id, "candidate_id": "rc_1"})

    def get_candidate(self, candidate_id):
        return SimpleNamespace(model_dump=lambda mode="json": {"candidate_id": candidate_id, "status": "COUNCIL_PENDING"})

    def retry_case(self, case_id):
        return SimpleNamespace(model_dump=lambda mode="json": {"case_id": case_id, "status": "OPEN"})


class _DummyWorker:
    is_running = True
    last_run_at = "2026-03-06T00:00:00Z"
    last_error = None

    async def process_pending_once(self, env=None):
        return {"processed": 1, "finalized": 1}


class _DummyDynamicDomain:
    def __init__(self, relation_count: int):
        self._relations = {f"r{index}": object() for index in range(relation_count)}

    def get_all_relations(self):
        return self._relations


class _DummyPersonalGraph:
    def __init__(self, relation_count: int):
        self._relations = {f"p{index}": object() for index in range(relation_count)}

    def get_all_relations(self):
        return self._relations


class _DummyReasoning:
    def __init__(self, conclusion):
        self._conclusion = conclusion

    def reason(self, question: str):
        return self._conclusion

    def get_stats(self):
        return {"paths": 1}


class _DummyLLM:
    def __init__(self):
        self.last_prompt = None

    def generate(self, request):
        self.last_prompt = request.prompt
        return SimpleNamespace(content="fallback ok")


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    app_main.reset_app_state()
    yield
    app_main.reset_app_state()
    get_settings.cache_clear()


class TestCallbackValidation:
    def test_callback_rejected_when_disabled(self, monkeypatch):
        monkeypatch.delenv("ONTRO_ENABLE_CALLBACKS", raising=False)
        with pytest.raises(ValueError, match="disabled"):
            app_main.validate_callback_url("https://callback.example.com/hook")

    def test_callback_rejected_when_resolved_ip_is_private(self, monkeypatch):
        monkeypatch.setenv("ONTRO_ENABLE_CALLBACKS", "true")
        monkeypatch.setenv("ONTRO_CALLBACK_ALLOWED_HOSTS", "example.com")
        monkeypatch.setattr(app_main, "_resolved_host_ips", lambda hostname: ["127.0.0.1"])

        with pytest.raises(ValueError, match="private or loopback"):
            app_main.validate_callback_url("https://api.example.com/hook")

    def test_callback_allowed_for_allowlisted_public_host(self, monkeypatch):
        monkeypatch.setenv("ONTRO_ENABLE_CALLBACKS", "true")
        monkeypatch.setenv("ONTRO_CALLBACK_ALLOWED_HOSTS", "example.com")
        monkeypatch.setattr(app_main, "_resolved_host_ips", lambda hostname: ["93.184.216.34"])

        assert app_main.validate_callback_url("https://api.example.com/hook") == "https://api.example.com/hook"


class TestStartupBehavior:
    def test_lifespan_skips_sample_loading_by_default(self, monkeypatch):
        calls = []

        monkeypatch.delenv("ONTRO_LOAD_SAMPLE_DATA", raising=False)
        monkeypatch.setattr(app_main, "build_llm_client", lambda: None)
        monkeypatch.setattr(app_main, "get_council_service", lambda: _DummyCouncil())
        monkeypatch.setattr(app_main, "load_sample_data", lambda: calls.append("seed") or {"docs_loaded": 0, "chunks_loaded": 0})

        with TestClient(app_main.app):
            assert app_main.app_state["ready"] is True

        assert calls == []

    def test_lifespan_loads_sample_data_when_flag_enabled(self, monkeypatch):
        calls = []

        monkeypatch.setenv("ONTRO_LOAD_SAMPLE_DATA", "true")
        monkeypatch.setattr(app_main, "build_llm_client", lambda: None)
        monkeypatch.setattr(app_main, "get_council_service", lambda: _DummyCouncil())
        monkeypatch.setattr(app_main, "load_sample_data", lambda: calls.append("seed") or {"docs_loaded": 0, "chunks_loaded": 0})

        with TestClient(app_main.app):
            assert app_main.app_state["ready"] is True

        assert calls == ["seed"]

    def test_lifespan_starts_council_worker_for_documented_default_path(self, monkeypatch):
        events = []

        class DummyDomainPipeline:
            def __init__(self):
                self.static_guard = object()
                self.dynamic_update = object()

        class DummyPersonalPipeline:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def get_pkg(self):
                return SimpleNamespace(get_all_relations=lambda: {})

        class DummyReasoningPipeline:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class DummyRuntimeWorker:
            def __init__(self, service, poll_interval_seconds):
                self.service = service
                self.poll_interval_seconds = poll_interval_seconds
                self.is_running = False
                self.last_run_at = None
                self.last_error = None

            async def start(self):
                self.is_running = True
                events.append("start")

            async def stop(self):
                self.is_running = False
                events.append("stop")

        monkeypatch.setenv("ONTRO_STORAGE_BACKEND", "neo4j")
        monkeypatch.setenv("ONTRO_COUNCIL_AUTO_ENABLED", "true")
        monkeypatch.setattr(app_main, "CouncilAutomationWorker", DummyRuntimeWorker)
        monkeypatch.setattr(app_main, "build_llm_client", lambda: None)
        monkeypatch.setattr(app_main, "get_council_service", lambda: _DummyCouncil())
        monkeypatch.setattr(app_main, "DomainPipeline", DummyDomainPipeline)
        monkeypatch.setattr(app_main, "PersonalPipeline", DummyPersonalPipeline)
        monkeypatch.setattr(app_main, "ReasoningPipeline", DummyReasoningPipeline)
        monkeypatch.setattr(
            app_main,
            "get_graph_repository",
            lambda: SimpleNamespace(count_entities=lambda: 0, count_relations=lambda: 0),
        )
        monkeypatch.setattr(
            app_main,
            "check_graph_repository_health",
            lambda repo: {"ok": True, "backend": "Neo4jGraphRepository"},
        )

        with TestClient(app_main.app):
            assert app_main.app_state["ready"] is True
            assert app_main.app_state["storage_health"]["backend"] == "Neo4jGraphRepository"

        assert events == ["start", "stop"]

    def test_lifespan_fails_fast_when_storage_healthcheck_fails(self, monkeypatch):
        monkeypatch.setenv("ONTRO_STORAGE_BACKEND", "neo4j")
        monkeypatch.setattr(app_main, "build_llm_client", lambda: None)
        monkeypatch.setattr(app_main, "get_council_service", lambda: _DummyCouncil())
        monkeypatch.setattr(
            app_main,
            "get_graph_repository",
            lambda: SimpleNamespace(count_entities=lambda: 0, count_relations=lambda: 0),
        )
        monkeypatch.setattr(
            app_main,
            "check_graph_repository_health",
            lambda repo: {"ok": False, "backend": "Neo4jGraphRepository", "error": "connection refused"},
        )

        with pytest.raises(RuntimeError, match="Storage backend unavailable"):
            with TestClient(app_main.app):
                pass


class TestStatusAndFallback:
    def test_status_reports_runtime_and_council_metrics(self, monkeypatch):
        monkeypatch.setitem(app_main.app_state, "domain", SimpleNamespace(get_dynamic_domain=lambda: _DummyDynamicDomain(4)))
        monkeypatch.setitem(app_main.app_state, "personal", SimpleNamespace(get_pkg=lambda: _DummyPersonalGraph(2)))
        monkeypatch.setitem(app_main.app_state, "council", _DummyCouncil())
        monkeypatch.setitem(app_main.app_state, "council_worker", _DummyWorker())
        monkeypatch.setitem(app_main.app_state, "learning_event_store", SimpleNamespace(counts=lambda: {"validation": 3}))
        monkeypatch.setitem(app_main.app_state, "ready", True)
        monkeypatch.setitem(app_main.app_state, "llm_client", object())
        monkeypatch.setitem(app_main.app_state, "ingested_docs", 7)
        monkeypatch.setitem(app_main.app_state, "ingested_edge_count", 15)
        monkeypatch.setitem(app_main.app_state, "ingested_pdf_doc_count", 3)
        monkeypatch.setitem(app_main.app_state, "storage_health", {"ok": True, "backend": "SimpleNamespace"})
        monkeypatch.setattr(
            app_main,
            "get_graph_repository",
            lambda: SimpleNamespace(count_entities=lambda: 9, count_relations=lambda: 12),
        )
        monkeypatch.setattr(app_main, "get_transaction_manager", lambda: SimpleNamespace(get_stats=lambda: {"total_committed": 2, "total_rolled_back": 1, "active_transactions": 0}))
        monkeypatch.setattr(app_main, "check_graph_repository_health", lambda repo: {"ok": True, "backend": "SimpleNamespace"})

        result = asyncio.run(app_main.status())

        assert result["storage_backend"] == "SimpleNamespace"
        assert result["metrics_schema_version"] == 2
        assert result["entity_count"] == 9
        assert result["relation_count"] == 12
        assert result["domain_relation_count"] == 4
        assert result["personal_relation_count"] == 2
        assert result["edge_count"] == 15
        assert result["pdf_doc_count"] == 3
        assert result["council_pending"] == 1
        assert result["council_closed"] == 2
        assert result["available_members"] == 2
        assert result["ingested_docs"] == 7
        assert result["pdf_docs"] == 3
        assert result["total_pdfs"] == 3
        assert result["deprecated_metric_aliases"]["vector_count"] == "edge_count"
        assert result["council_worker_active"] is True
        assert result["learning_event_backlog"] == {"validation": 3}

    def test_status_fails_soft_when_storage_backend_is_unavailable(self, monkeypatch):
        monkeypatch.setitem(app_main.app_state, "ready", False)
        monkeypatch.setitem(app_main.app_state, "storage_health", {"ok": False, "backend": "Neo4jGraphRepository"})
        monkeypatch.setattr(app_main, "get_graph_repository", lambda: (_ for _ in ()).throw(ConnectionError("neo4j offline")))

        result = asyncio.run(app_main.status())

        assert result["storage_backend"] == "Neo4jGraphRepository"
        assert result["storage_ok"] is False
        assert "neo4j offline" in result["storage_error"]
        assert result["entity_count"] == 0
        assert result["relation_count"] == 0
        assert result["tx_committed"] == 0
        assert result["tx_rolled_back"] == 0
        assert result["tx_active"] == 0

    def test_status_is_degraded_when_app_is_ready_but_storage_is_not(self, monkeypatch):
        monkeypatch.setitem(app_main.app_state, "ready", True)
        monkeypatch.setitem(app_main.app_state, "storage_health", {"ok": True, "backend": "Neo4jGraphRepository"})
        monkeypatch.setattr(app_main, "get_graph_repository", lambda: (_ for _ in ()).throw(ConnectionError("neo4j offline")))

        result = asyncio.run(app_main.status())

        assert result["ready"] is True
        assert result["storage_ok"] is False
        assert result["status"] == "degraded"

    def test_council_admin_endpoints(self, monkeypatch):
        monkeypatch.setitem(app_main.app_state, "council", _DummyCouncil())
        monkeypatch.setitem(app_main.app_state, "council_worker", _DummyWorker())

        list_payload = asyncio.run(app_main.list_council_cases("pending"))
        assert list_payload["cases"][0]["case_id"] == "case_1"

        case_payload = asyncio.run(app_main.get_council_case("case_1"))
        assert case_payload["candidate"]["candidate_id"] == "rc_1"

        retry_payload = asyncio.run(app_main.retry_council_case("case_1"))
        assert retry_payload["result"]["finalized"] == 1

    def test_dashboard_summary_exposes_recent_ingests(self, monkeypatch, tmp_path):
        store = LearningEventStore(tmp_path)
        store.append(
            "ingest",
            {
                "doc_id": "doc_001",
                "input_type": "text",
                "metadata": {"source": "ui"},
                "edge_count": 3,
                "destinations": {"domain": 1, "personal": 1, "council": 1},
                "council_case_ids": ["case_1"],
            },
        )
        monkeypatch.setitem(app_main.app_state, "domain", SimpleNamespace(get_dynamic_domain=lambda: _DummyDynamicDomain(4)))
        monkeypatch.setitem(app_main.app_state, "personal", SimpleNamespace(get_pkg=lambda: _DummyPersonalGraph(2)))
        monkeypatch.setitem(app_main.app_state, "council", _DummyCouncil())
        monkeypatch.setitem(app_main.app_state, "council_worker", _DummyWorker())
        monkeypatch.setitem(app_main.app_state, "learning_event_store", store)
        monkeypatch.setitem(app_main.app_state, "ready", True)
        monkeypatch.setitem(app_main.app_state, "llm_client", object())
        monkeypatch.setitem(app_main.app_state, "ingested_docs", 7)
        monkeypatch.setitem(app_main.app_state, "ingested_edge_count", 15)
        monkeypatch.setitem(app_main.app_state, "ingested_pdf_doc_count", 3)
        monkeypatch.setattr(
            app_main,
            "get_graph_repository",
            lambda: SimpleNamespace(count_entities=lambda: 9, count_relations=lambda: 12),
        )
        monkeypatch.setattr(app_main, "get_transaction_manager", lambda: SimpleNamespace(get_stats=lambda: {"total_committed": 2, "total_rolled_back": 1, "active_transactions": 0}))
        monkeypatch.setattr(app_main, "check_graph_repository_health", lambda repo: {"ok": True, "backend": "SimpleNamespace"})

        result = asyncio.run(app_main.dashboard_summary())

        assert result["totals"]["entities"] == 9
        assert result["totals"]["ingests"] == 1
        assert result["recent_ingests"][0]["doc_id"] == "doc_001"
        assert result["recent_ingests"][0]["council_case_ids"] == ["case_1"]

    def test_ingest_history_endpoints_return_list_and_detail(self, monkeypatch, tmp_path):
        store = LearningEventStore(tmp_path)
        store.append(
            "ingest",
            {
                "doc_id": "doc_001",
                "input_type": "text",
                "metadata": {"source": "ui", "doc_title": "Macro note"},
                "edge_count": 2,
                "destinations": {"domain": 1, "personal": 0, "council": 1},
                "council_case_ids": ["case_1"],
            },
        )
        monkeypatch.setitem(app_main.app_state, "learning_event_store", store)

        listing = asyncio.run(app_main.list_ingests())
        detail = asyncio.run(app_main.get_ingest_detail("doc_001"))

        assert listing["items"][0]["doc_id"] == "doc_001"
        assert detail["doc_id"] == "doc_001"
        assert detail["metadata"]["doc_title"] == "Macro note"
        assert detail["destinations"]["council"] == 1

    def test_entity_and_graph_endpoints_return_console_shapes(self, monkeypatch):
        repo = InMemoryGraphRepository()
        repo.upsert_entity("Policy_Rate", ["DomainEntity"], {"name": "policy rate", "type": "MacroIndicator"})
        repo.upsert_entity("Growth_Stocks", ["DomainEntity"], {"name": "growth stocks", "type": "AssetGroup"})
        repo.upsert_relation(
            "Policy_Rate",
            "domain:pressures",
            "Growth_Stocks",
            {"relation_id": "rel_1", "sign": "-", "domain_conf": 0.82, "origin": "council"},
        )
        monkeypatch.setattr(app_main, "get_graph_repository", lambda: repo)

        entities = asyncio.run(app_main.list_entities(q="policy", entity_type=None, limit=10))
        entity_detail = asyncio.run(app_main.get_entity_detail("Policy_Rate"))
        graph = asyncio.run(app_main.get_graph(root_entity_id="Policy_Rate", depth=1, limit=20))

        assert entities["items"][0]["id"] == "Policy_Rate"
        assert entities["items"][0]["label"] == "policy rate"
        assert entity_detail["entity"]["id"] == "Policy_Rate"
        assert entity_detail["neighbors"][0]["relation_type"] == "pressures"
        assert graph["nodes"][0]["id"] == "Policy_Rate"
        assert graph["edges"][0]["type"] == "pressures"
        assert graph["edges"][0]["sign"] == "-"

    def test_console_routes_fallback_to_built_spa(self, monkeypatch, tmp_path):
        dist_dir = tmp_path / "dist"
        assets_dir = dist_dir / "assets"
        assets_dir.mkdir(parents=True)
        index_path = dist_dir / "index.html"
        asset_path = assets_dir / "app.js"
        index_path.write_text("<html>ops console</html>", encoding="utf-8")
        asset_path.write_text("console.log('ok')", encoding="utf-8")
        monkeypatch.setenv("ONTRO_CONSOLE_DIST_DIR", str(dist_dir))

        root_response = asyncio.run(app_main.serve_console_root())
        route_response = asyncio.run(app_main.serve_console("graph/explorer"))
        asset_response = asyncio.run(app_main.serve_console("assets/app.js"))

        assert Path(root_response.path) == index_path
        assert Path(route_response.path) == index_path
        assert Path(asset_response.path) == asset_path

    def test_ask_fallback_uses_finance_prompt(self, monkeypatch):
        llm = _DummyLLM()
        conclusion = SimpleNamespace(
            confidence=0.1,
            conclusion_text="unknown",
            evidence_summary=None,
            strongest_path_description=None,
        )

        monkeypatch.setitem(app_main.app_state, "ready", True)
        monkeypatch.setitem(app_main.app_state, "llm_client", llm)
        monkeypatch.setitem(app_main.app_state, "reasoning", _DummyReasoning(conclusion))

        response = asyncio.run(app_main.ask(app_main.AskRequest(question="금리와 성장주의 관계는?")))

        assert response.reasoning_used is False
        assert "[AI 답변]" in response.answer
        assert "금융 문서와 관계형 지식 그래프" in llm.last_prompt

    def test_text_ingest_generates_unique_doc_ids(self, monkeypatch):
        monkeypatch.setitem(app_main.app_state, "ready", True)
        monkeypatch.setattr(
            app_main,
            "ingest_text_into_ontology",
            lambda text, doc_id, metadata=None: {
                "doc_id": doc_id,
                "edge_count": 0,
                "chunks_created": 0,
                "total_chunks": 0,
                "domain_relations": 0,
                "personal_relations": 0,
                "council_relations": 0,
                "council_case_ids": [],
            },
        )

        with TestClient(app_main.app) as client:
            first = client.post("/api/text/add-to-vectordb", json={"text": "policy rates pressure growth stocks"})
            second = client.post("/api/text/add-to-vectordb", json={"text": "policy rates pressure growth stocks"})

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["doc_id"] != second.json()["doc_id"]
