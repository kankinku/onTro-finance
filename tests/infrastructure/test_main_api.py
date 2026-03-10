"""Main API runtime and policy tests."""

import asyncio
import base64
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import main as app_main
from config.settings import get_settings
from src.integrations.news_bridge import NewsImpactPayload
from src.learning.event_store import LearningEventStore
from src.storage.inmemory_repository import InMemoryGraphRepository


class _DummyCouncil:
    def refresh_member_availability(self, env=None):
        return {}

    def get_stats(self):
        return {
            "pending_cases": 1,
            "closed_cases": 2,
            "configured_members": 3,
            "available_members": 2,
        }

    def list_cases(self, status=None):
        case = SimpleNamespace(
            model_dump=lambda mode="json": {
                "case_id": "case_1",
                "status": status or "OPEN",
                "candidate_id": "rc_1",
            }
        )
        return [case]

    def get_case(self, case_id):
        return SimpleNamespace(
            model_dump=lambda mode="json": {"case_id": case_id, "candidate_id": "rc_1"}
        )

    def get_candidate(self, candidate_id):
        return SimpleNamespace(
            model_dump=lambda mode="json": {
                "candidate_id": candidate_id,
                "status": "COUNCIL_PENDING",
            }
        )

    def retry_case(self, case_id):
        return SimpleNamespace(
            model_dump=lambda mode="json": {"case_id": case_id, "status": "OPEN"}
        )


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

        assert (
            app_main.validate_callback_url("https://api.example.com/hook")
            == "https://api.example.com/hook"
        )

    def test_guard_request_rejects_invalid_api_key(self, monkeypatch):
        monkeypatch.setenv("ONTRO_API_KEY", "secret")
        request = SimpleNamespace(
            headers={"x-api-key": "wrong"},
            client=SimpleNamespace(host="127.0.0.1"),
            method="POST",
            url=SimpleNamespace(path="/api/test"),
        )
        with pytest.raises(app_main.HTTPException) as exc_info:
            app_main._guard_request(request)
        assert exc_info.value.status_code == 401

    def test_guard_request_enforces_role_based_authorization(self, monkeypatch):
        monkeypatch.setenv("ONTRO_API_KEY_VIEWER", "viewer-key")
        viewer_request = SimpleNamespace(
            headers={"x-api-key": "viewer-key"},
            client=SimpleNamespace(host="127.0.0.1"),
            method="POST",
            url=SimpleNamespace(path="/api/learning/evaluations/run"),
            state=SimpleNamespace(),
        )
        with pytest.raises(app_main.HTTPException) as exc_info:
            app_main._guard_request(viewer_request)
        assert exc_info.value.status_code == 403

        operator_request = SimpleNamespace(
            headers={"x-api-key": "operator-key"},
            client=SimpleNamespace(host="127.0.0.1"),
            method="POST",
            url=SimpleNamespace(path="/api/learning/evaluations/run"),
            state=SimpleNamespace(),
        )
        monkeypatch.setenv("ONTRO_API_KEY_OPERATOR", "operator-key")
        app_main._guard_request(operator_request)
        assert operator_request.state.api_role == "operator"

        admin_request = SimpleNamespace(
            headers={"x-api-key": "admin-key"},
            client=SimpleNamespace(host="127.0.0.1"),
            method="POST",
            url=SimpleNamespace(path="/api/council/process-pending"),
            state=SimpleNamespace(),
        )
        monkeypatch.setenv("ONTRO_API_KEY_ADMIN", "admin-key")
        app_main._guard_request(admin_request)
        assert admin_request.state.api_role == "admin"

    def test_viewer_role_can_access_read_only_document_paths(self, monkeypatch):
        monkeypatch.setenv("ONTRO_API_KEY_VIEWER", "viewer-key")
        viewer_request = SimpleNamespace(
            headers={"x-api-key": "viewer-key"},
            client=SimpleNamespace(host="127.0.0.1"),
            method="GET",
            url=SimpleNamespace(path="/api/documents/doc_001/graph"),
            state=SimpleNamespace(),
        )

        app_main._guard_request(viewer_request)

        assert viewer_request.state.api_role == "viewer"

    def test_guard_request_enforces_rate_limit(self, monkeypatch):
        monkeypatch.setenv("ONTRO_RATE_LIMIT_PER_MINUTE", "1")
        request = SimpleNamespace(
            headers={},
            client=SimpleNamespace(host="127.0.0.1"),
            method="POST",
            url=SimpleNamespace(path="/api/test"),
        )
        app_main._guard_request(request)
        with pytest.raises(app_main.HTTPException) as exc_info:
            app_main._guard_request(request)
        assert exc_info.value.status_code == 429

    def test_audit_log_endpoint_returns_persisted_events(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ONTRO_AUDIT_LOG", "true")
        store = LearningEventStore(tmp_path)
        app_main.app_state.learning_event_store = store
        request = SimpleNamespace(
            headers={},
            client=SimpleNamespace(host="127.0.0.1"),
            method="POST",
            url=SimpleNamespace(path="/api/learning/evaluations/run"),
        )

        app_main._guard_request(request)
        result = asyncio.run(app_main.get_audit_logs(limit=10, action=None))

        assert result["count"] == 1
        assert result["items"][0]["path"] == "/api/learning/evaluations/run"

    def test_metrics_endpoint_returns_prometheus_text(self):
        app_main.app_state.ready = True
        app_main.app_state.ingested_docs = 3
        app_main.app_state.ingested_edge_count = 9
        app_main.app_state.ingested_pdf_doc_count = 1
        app_main.app_state.storage_health = {"ok": True}
        app_main.app_state.request_totals = {"/api/documents": 4}
        app_main.app_state.request_errors = {"/api/learning/evaluations/run": 1}
        app_main.app_state.learning_event_store = SimpleNamespace(audit_count=lambda: 2)

        response = asyncio.run(app_main.metrics())

        assert response.media_type == "text/plain; version=0.0.4"
        body = response.body.decode("utf-8")
        assert "ontro_ready 1" in body
        assert "ontro_ingested_documents_total 3" in body
        assert 'ontro_requests_total{path="/api/documents"' in body


class TestStartupBehavior:
    def test_lifespan_skips_sample_loading_by_default(self, monkeypatch):
        calls = []

        monkeypatch.delenv("ONTRO_LOAD_SAMPLE_DATA", raising=False)
        monkeypatch.setattr(
            app_main,
            "_refresh_ai_runtime_status",
            lambda: {"provider": "ollama", "model_name": "llama3.2:latest", "connected": False},
        )
        monkeypatch.setattr(app_main, "build_llm_client", lambda: None)
        monkeypatch.setattr(app_main, "get_council_service", lambda: _DummyCouncil())
        monkeypatch.setattr(
            app_main,
            "load_sample_data",
            lambda: calls.append("seed") or {"docs_loaded": 0, "chunks_loaded": 0},
        )

        with TestClient(app_main.app):
            assert app_main.app_state["ready"] is True

        assert calls == []

    def test_lifespan_loads_sample_data_when_flag_enabled(self, monkeypatch):
        calls = []

        monkeypatch.setenv("ONTRO_LOAD_SAMPLE_DATA", "true")
        monkeypatch.setattr(
            app_main,
            "_refresh_ai_runtime_status",
            lambda: {"provider": "ollama", "model_name": "llama3.2:latest", "connected": False},
        )
        monkeypatch.setattr(app_main, "build_llm_client", lambda: None)
        monkeypatch.setattr(app_main, "get_council_service", lambda: _DummyCouncil())
        monkeypatch.setattr(
            app_main,
            "load_sample_data",
            lambda: calls.append("seed") or {"docs_loaded": 0, "chunks_loaded": 0},
        )

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
        monkeypatch.setattr(
            app_main,
            "_refresh_ai_runtime_status",
            lambda: {"provider": "ollama", "model_name": "llama3.2:latest", "connected": False},
        )
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
        monkeypatch.setattr(
            app_main,
            "_refresh_ai_runtime_status",
            lambda: {"provider": "ollama", "model_name": "llama3.2:latest", "connected": False},
        )
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
            lambda repo: {
                "ok": False,
                "backend": "Neo4jGraphRepository",
                "error": "connection refused",
            },
        )

        with pytest.raises(RuntimeError, match="Storage backend unavailable"):
            with TestClient(app_main.app):
                pass

    def test_lifespan_wires_personal_pipeline_to_persistent_storage(self, monkeypatch, tmp_path):
        captured = {}

        class DummyDomainPipeline:
            def __init__(self):
                self.static_guard = object()
                self.dynamic_update = object()

        class DummyPersonalPipeline:
            def __init__(self, **kwargs):
                captured.update(kwargs)

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

            async def stop(self):
                self.is_running = False

        monkeypatch.setenv("ONTRO_APP_HOME", str(tmp_path))
        monkeypatch.setattr(
            app_main,
            "_refresh_ai_runtime_status",
            lambda: {"provider": "ollama", "model_name": "llama3.2:latest", "connected": False},
        )
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
            lambda repo: {"ok": True, "backend": "SimpleNamespace"},
        )

        with TestClient(app_main.app):
            assert app_main.app_state["ready"] is True

        expected_path = tmp_path / "data" / "personal" / "default_user.json"
        assert captured["storage_path"] == expected_path


class TestStatusAndFallback:
    def test_delete_selected_ingests_replays_only_retained_records(self, monkeypatch, tmp_path):
        store = LearningEventStore(tmp_path)
        store.upsert_document({"doc_id": "doc_keep", "title": "Keep"})
        store.upsert_document({"doc_id": "doc_delete", "title": "Delete"})
        store.append(
            "ingest",
            {
                "doc_id": "doc_keep",
                "input_type": "text",
                "metadata": {"source": "ui"},
                "edge_count": 2,
                "destinations": {"domain": 1, "personal": 1, "council": 0},
                "council_case_ids": [],
                "replay_text": "retain this record",
            },
        )
        store.append(
            "ingest",
            {
                "doc_id": "doc_delete",
                "input_type": "text",
                "metadata": {"source": "ui"},
                "edge_count": 1,
                "destinations": {"domain": 1, "personal": 0, "council": 0},
                "council_case_ids": [],
                "replay_text": "delete this record",
            },
        )
        monkeypatch.setitem(app_main.app_state, "ready", True)
        monkeypatch.setitem(app_main.app_state, "learning_event_store", store)

        replayed = {}

        async def fake_replay(rows):
            replayed["doc_ids"] = [row["doc_id"] for row in rows]

        monkeypatch.setattr(app_main, "_replay_retained_ingests", fake_replay)

        result = asyncio.run(app_main.delete_selected_ingests(["doc_delete"]))

        assert result["status"] == "success"
        assert result["deleted_doc_ids"] == ["doc_delete"]
        assert result["remaining_ingests"] == 1
        assert replayed["doc_ids"] == ["doc_keep"]
        assert store.document_count() == 2

    def test_delete_selected_ingests_rejects_legacy_records_without_replay_text(
        self, monkeypatch, tmp_path
    ):
        store = LearningEventStore(tmp_path)
        store.append(
            "ingest",
            {
                "doc_id": "doc_keep",
                "input_type": "text",
                "metadata": {"source": "legacy"},
                "edge_count": 2,
                "destinations": {"domain": 1, "personal": 1, "council": 0},
                "council_case_ids": [],
            },
        )
        store.append(
            "ingest",
            {
                "doc_id": "doc_delete",
                "input_type": "text",
                "metadata": {"source": "ui"},
                "edge_count": 1,
                "destinations": {"domain": 1, "personal": 0, "council": 0},
                "council_case_ids": [],
                "replay_text": "delete this record",
            },
        )
        monkeypatch.setitem(app_main.app_state, "ready", True)
        monkeypatch.setitem(app_main.app_state, "learning_event_store", store)

        with pytest.raises(RuntimeError, match="cannot be replayed"):
            asyncio.run(app_main.delete_selected_ingests(["doc_delete"]))

    def test_status_reports_runtime_and_council_metrics(self, monkeypatch):
        monkeypatch.setitem(
            app_main.app_state,
            "domain",
            SimpleNamespace(get_dynamic_domain=lambda: _DummyDynamicDomain(4)),
        )
        monkeypatch.setitem(
            app_main.app_state, "personal", SimpleNamespace(get_pkg=lambda: _DummyPersonalGraph(2))
        )
        monkeypatch.setitem(app_main.app_state, "council", _DummyCouncil())
        monkeypatch.setitem(app_main.app_state, "council_worker", _DummyWorker())
        monkeypatch.setitem(
            app_main.app_state,
            "learning_event_store",
            SimpleNamespace(counts=lambda: {"validation": 3}),
        )
        monkeypatch.setitem(app_main.app_state, "ready", True)
        monkeypatch.setitem(app_main.app_state, "llm_client", object())
        monkeypatch.setitem(app_main.app_state, "ingested_docs", 7)
        monkeypatch.setitem(app_main.app_state, "ingested_edge_count", 15)
        monkeypatch.setitem(app_main.app_state, "ingested_pdf_doc_count", 3)
        monkeypatch.setitem(
            app_main.app_state,
            "ai_runtime",
            {
                "provider": "ollama",
                "model_name": "llama3.2:latest",
                "connected": True,
                "attempts": 2,
            },
        )
        monkeypatch.setitem(
            app_main.app_state, "storage_health", {"ok": True, "backend": "SimpleNamespace"}
        )
        monkeypatch.setattr(
            app_main,
            "get_graph_repository",
            lambda: SimpleNamespace(count_entities=lambda: 9, count_relations=lambda: 12),
        )
        monkeypatch.setattr(
            app_main,
            "get_transaction_manager",
            lambda: SimpleNamespace(
                get_stats=lambda: {
                    "total_committed": 2,
                    "total_rolled_back": 1,
                    "active_transactions": 0,
                }
            ),
        )
        monkeypatch.setattr(
            app_main,
            "check_graph_repository_health",
            lambda repo: {"ok": True, "backend": "SimpleNamespace"},
        )

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
        ai_runtime = cast(dict[str, object], result["ai_runtime"])
        assert ai_runtime["connected"] is True
        assert result["pdf_docs"] == 3
        assert result["total_pdfs"] == 3
        deprecated_aliases = cast(dict[str, str], result["deprecated_metric_aliases"])
        assert deprecated_aliases["vector_count"] == "edge_count"
        assert result["council_worker_active"] is True
        assert result["learning_event_backlog"] == {"validation": 3}

    def test_status_fails_soft_when_storage_backend_is_unavailable(self, monkeypatch):
        monkeypatch.setitem(app_main.app_state, "ready", False)
        monkeypatch.setitem(
            app_main.app_state, "storage_health", {"ok": False, "backend": "Neo4jGraphRepository"}
        )
        monkeypatch.setattr(
            app_main,
            "get_graph_repository",
            lambda: (_ for _ in ()).throw(ConnectionError("neo4j offline")),
        )

        result = asyncio.run(app_main.status())

        assert result["storage_backend"] == "Neo4jGraphRepository"
        assert result["storage_ok"] is False
        storage_error = cast(str, result["storage_error"])
        assert "neo4j offline" in storage_error
        assert result["entity_count"] == 0
        assert result["relation_count"] == 0
        assert result["tx_committed"] == 0
        assert result["tx_rolled_back"] == 0
        assert result["tx_active"] == 0

    def test_status_is_degraded_when_app_is_ready_but_storage_is_not(self, monkeypatch):
        monkeypatch.setitem(app_main.app_state, "ready", True)
        monkeypatch.setitem(
            app_main.app_state, "storage_health", {"ok": True, "backend": "Neo4jGraphRepository"}
        )
        monkeypatch.setattr(
            app_main,
            "get_graph_repository",
            lambda: (_ for _ in ()).throw(ConnectionError("neo4j offline")),
        )

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
        candidate_payload = cast(dict[str, str], case_payload["candidate"])
        assert candidate_payload["candidate_id"] == "rc_1"

        retry_payload = asyncio.run(app_main.retry_council_case("case_1"))
        assert retry_payload["result"]["finalized"] == 1

    def test_dashboard_summary_exposes_recent_ingests(self, monkeypatch, tmp_path):
        store = LearningEventStore(tmp_path)
        store.upsert_document(
            {
                "doc_id": "doc_001",
                "title": "Macro note",
                "source_type": "research_note",
                "edge_count": 3,
            }
        )
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
        monkeypatch.setitem(
            app_main.app_state,
            "domain",
            SimpleNamespace(get_dynamic_domain=lambda: _DummyDynamicDomain(4)),
        )
        monkeypatch.setitem(
            app_main.app_state, "personal", SimpleNamespace(get_pkg=lambda: _DummyPersonalGraph(2))
        )
        monkeypatch.setitem(app_main.app_state, "council", _DummyCouncil())
        monkeypatch.setitem(app_main.app_state, "council_worker", _DummyWorker())
        monkeypatch.setitem(app_main.app_state, "learning_event_store", store)
        monkeypatch.setitem(app_main.app_state, "ready", True)
        monkeypatch.setitem(app_main.app_state, "llm_client", object())
        monkeypatch.setitem(app_main.app_state, "ingested_docs", 7)
        monkeypatch.setitem(app_main.app_state, "ingested_edge_count", 15)
        monkeypatch.setitem(app_main.app_state, "ingested_pdf_doc_count", 3)
        monkeypatch.setitem(
            app_main.app_state,
            "ai_runtime",
            {
                "provider": "ollama",
                "model_name": "llama3.2:latest",
                "connected": True,
                "attempts": 1,
            },
        )
        monkeypatch.setattr(
            app_main,
            "get_graph_repository",
            lambda: SimpleNamespace(count_entities=lambda: 9, count_relations=lambda: 12),
        )
        monkeypatch.setattr(
            app_main,
            "get_transaction_manager",
            lambda: SimpleNamespace(
                get_stats=lambda: {
                    "total_committed": 2,
                    "total_rolled_back": 1,
                    "active_transactions": 0,
                }
            ),
        )
        monkeypatch.setattr(
            app_main,
            "check_graph_repository_health",
            lambda repo: {"ok": True, "backend": "SimpleNamespace"},
        )

        result = asyncio.run(app_main.dashboard_summary())

        assert result["totals"]["entities"] == 9
        assert result["totals"]["ingests"] == 1
        assert result["totals"]["documents"] == 1
        assert result["council"] == {"pending": 1, "closed": 2, "available_members": 2}
        assert result["recent_ingests"][0]["doc_id"] == "doc_001"
        assert result["recent_ingests"][0]["council_case_ids"] == ["case_1"]
        assert result["recent_documents"][0]["title"] == "Macro note"

    def test_ai_runtime_endpoints_return_cached_and_refreshed_status(self, monkeypatch):
        monkeypatch.setitem(
            app_main.app_state,
            "ai_runtime",
            {"provider": "ollama", "model_name": "cached-model", "connected": False, "attempts": 1},
        )

        cached = asyncio.run(app_main.get_ai_runtime())
        assert cached["model_name"] == "cached-model"

        monkeypatch.setattr(
            app_main,
            "_refresh_ai_runtime_status",
            lambda: {
                "provider": "ollama",
                "model_name": "fresh-model",
                "connected": True,
                "attempts": 2,
            },
        )

        refreshed = asyncio.run(app_main.check_ai_runtime())
        assert refreshed["model_name"] == "fresh-model"
        assert refreshed["connected"] is True

    def test_ingest_history_endpoints_return_list_and_detail(self, monkeypatch, tmp_path):
        store = LearningEventStore(tmp_path)
        store.upsert_document(
            {
                "doc_id": "doc_001",
                "title": "Macro note",
                "author": "Analyst",
                "source_type": "research_note",
                "edge_count": 2,
                "destinations": {"domain": 1, "personal": 0, "council": 1},
                "metadata": {"source": "ui", "doc_title": "Macro note"},
            }
        )
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
        store.append(
            "validation",
            {
                "source_document_id": "doc_001",
                "edge_id": "edge_1",
                "fragment_id": "frag_1",
                "fragment_text": "Higher rates pressure growth stocks.",
                "citation_page_number": 4,
                "citation_chapter_title": "Chapter 2 Macro",
                "citation_section_title": "2.3 Rates and Equity Style",
                "head_entity_id": "Policy_Rate",
                "tail_entity_id": "Growth_Stocks",
                "relation_type": "pressures",
                "destination": "domain",
                "combined_conf": 0.84,
                "semantic_tag": "macro_impact",
                "time_scope": "short_term",
            },
        )
        store.append(
            "council_final",
            {
                "source_document_id": "doc_001",
                "candidate_id": "rc_001",
                "council_case_id": "case_1",
                "status": "COUNCIL_APPROVED",
                "source_metadata": {
                    "page_number": 4,
                    "chapter_title": "Chapter 2 Macro",
                    "section_title": "2.3 Rates and Equity Style",
                },
                "head_entity": {"canonical_id": "Policy_Rate"},
                "tail_entity": {"canonical_id": "Growth_Stocks"},
                "final_relation_type": "pressures",
                "final_confidence": 0.93,
                "time_scope_candidate": "short_term",
                "citation_span": {"text": "Higher rates pressure growth stocks."},
            },
        )
        monkeypatch.setitem(app_main.app_state, "learning_event_store", store)

        listing = asyncio.run(app_main.list_ingests())
        detail = asyncio.run(app_main.get_ingest_detail("doc_001"))
        documents = asyncio.run(app_main.list_documents())
        document_detail = asyncio.run(app_main.get_document_detail("doc_001"))

        assert listing["items"][0]["doc_id"] == "doc_001"
        assert detail["doc_id"] == "doc_001"
        assert detail["metadata"]["doc_title"] == "Macro note"
        assert detail["destinations"]["council"] == 1
        assert documents["items"][0]["title"] == "Macro note"
        assert document_detail["author"] == "Analyst"
        assert document_detail["evidence"]["counts"]["validation"] == 1
        assert document_detail["evidence"]["counts"]["council"] == 1
        assert document_detail["related_relations"][0]["relation_type"] == "pressures"
        assert document_detail["related_relations"][0]["evidence_count"] == 2
        assert document_detail["related_relations"][0]["council_case_ids"] == ["case_1"]
        assert document_detail["related_relations"][0]["page_numbers"] == [4]
        assert document_detail["related_relations"][0]["chapter_titles"] == ["Chapter 2 Macro"]
        assert (
            document_detail["evidence"]["validation_events"][0]["citation_section_title"]
            == "2.3 Rates and Equity Style"
        )

    def test_documents_endpoint_supports_source_filters(self, monkeypatch, tmp_path):
        store = LearningEventStore(tmp_path)
        store.upsert_document(
            {
                "doc_id": "doc_001",
                "title": "Macro note",
                "institution": "Macro Lab",
                "source_type": "research_note",
                "region": "us",
                "asset_scope": "equities",
                "document_quality_tier": "A",
                "edge_count": 2,
            }
        )
        store.upsert_document(
            {
                "doc_id": "doc_002",
                "title": "Credit memo",
                "institution": "Credit Desk",
                "source_type": "internal_memo",
                "region": "eu",
                "asset_scope": "credit",
                "document_quality_tier": "B",
                "edge_count": 1,
            }
        )
        monkeypatch.setitem(app_main.app_state, "learning_event_store", store)

        filtered = asyncio.run(
            app_main.list_documents(
                q="macro",
                source_type="research_note",
                institution=None,
                region=None,
                asset_scope=None,
                document_quality_tier=None,
                limit=20,
            )
        )

        assert filtered["count"] == 1
        assert filtered["items"][0]["doc_id"] == "doc_001"

    def test_trust_and_learning_product_endpoints_return_operational_summaries(
        self, monkeypatch, tmp_path
    ):
        store = LearningEventStore(tmp_path)
        store.append(
            "validation",
            {
                "source_document_id": "doc_001",
                "destination": "domain",
                "combined_conf": 0.87,
            },
        )
        store.append(
            "validation",
            {
                "source_document_id": "doc_002",
                "destination": "council",
                "combined_conf": 0.42,
            },
        )
        store.append(
            "council_candidate",
            {
                "candidate_id": "rc_001",
                "status": "COUNCIL_PENDING",
                "council_trigger_reasons": ["LOW_CONFIDENCE", "HIGH_IMPACT_RELATION"],
            },
        )
        store.append(
            "council_final",
            {
                "candidate_id": "rc_001",
                "status": "COUNCIL_APPROVED",
            },
        )

        snapshot_path = store.snapshot_path("dataset-test.json")
        snapshot_path.write_text(
            json.dumps(
                {
                    "version": "ds_v1",
                    "task_type": "relation",
                    "sample_count": 4,
                    "dataset_id": "ds_001",
                }
            ),
            encoding="utf-8",
        )
        evaluation_path = store.snapshot_path("evaluation-test.json")
        evaluation_path.write_text(
            json.dumps(
                {
                    "dataset_version": "ds_v1",
                    "goldset_version": "gold_v1",
                    "metrics": {"f1": 0.81, "accuracy": 0.75},
                }
            ),
            encoding="utf-8",
        )
        goldset_path = store.goldset_path("gold-test.json")
        goldset_path.write_text(
            json.dumps(
                {
                    "version": "gold_v1",
                    "task_type": "relation",
                    "sample_count": 2,
                    "goldset_id": "gold_001",
                }
            ),
            encoding="utf-8",
        )
        bundle_path = store.bundle_path("bundle-test.json")
        bundle_path.write_text(
            json.dumps(
                {
                    "version": "bundle_v1",
                    "status": "deployed",
                    "student1_version": "s1_v1",
                    "student2_version": "s2_v1",
                    "policy_version": "pol_v1",
                }
            ),
            encoding="utf-8",
        )

        monkeypatch.setitem(app_main.app_state, "learning_event_store", store)

        trust = asyncio.run(app_main.get_trust_summary())
        learning = asyncio.run(app_main.get_learning_products(limit=10))

        assert trust["validation_destination_counts"]["domain"] == 1
        assert trust["confidence_bands"]["high"] == 1
        assert trust["trigger_reason_counts"]["LOW_CONFIDENCE"] == 1
        assert learning["counts"]["snapshots"] == 1
        assert learning["counts"]["evaluations"] == 1
        assert learning["counts"]["goldsets"] == 1
        assert learning["counts"]["bundles"] == 1

    def test_document_graph_and_structure_endpoints(self, monkeypatch, tmp_path):
        store = LearningEventStore(tmp_path)
        store.upsert_document(
            {
                "doc_id": "doc_graph_001",
                "title": "Macro note",
                "source_type": "pdf_upload",
                "metadata": {
                    "pdf_blocks": [
                        {
                            "page_number": 1,
                            "block_type": "table",
                            "table_caption": "Scenario Table",
                            "table_rows": 3,
                            "table_columns": 3,
                        },
                        {"page_number": 2, "block_type": "ocr_needed", "ocr_required": True},
                    ],
                    "structured_sections": [
                        {"chapter_title": "Chapter 1", "section_title": "1.1 Rates"}
                    ],
                },
                "consolidated_relations": [
                    {
                        "head_entity_id": "Policy_Rate",
                        "relation_type": "pressures",
                        "tail_entity_id": "Growth_Stocks",
                    }
                ],
            }
        )
        store.append(
            "validation",
            {
                "source_document_id": "doc_graph_001",
                "head_entity_id": "Policy_Rate",
                "tail_entity_id": "Growth_Stocks",
                "relation_type": "pressures",
                "destination": "domain",
                "combined_conf": 0.8,
            },
        )
        repo = InMemoryGraphRepository()
        repo.upsert_entity(
            "Policy_Rate", ["DomainEntity"], {"name": "policy rate", "type": "MacroIndicator"}
        )
        repo.upsert_entity(
            "Growth_Stocks", ["DomainEntity"], {"name": "growth stocks", "type": "AssetGroup"}
        )
        repo.upsert_relation(
            "Policy_Rate", "domain:pressures", "Growth_Stocks", {"domain_conf": 0.8}
        )
        monkeypatch.setitem(app_main.app_state, "learning_event_store", store)
        monkeypatch.setattr(app_main, "get_graph_repository", lambda: repo)

        graph = asyncio.run(app_main.get_document_graph("doc_graph_001"))
        structure = asyncio.run(app_main.get_document_structure("doc_graph_001"))

        assert len(graph["nodes"]) == 2
        assert graph["edges"][0]["type"] == "pressures"
        assert structure["table_blocks"][0]["caption"] == "Scenario Table"
        assert structure["ocr_needed_pages"] == [2]

    def test_learning_action_endpoints_run_evaluation_and_promote_bundle(
        self, monkeypatch, tmp_path
    ):
        store = LearningEventStore(tmp_path)
        snapshot_path = store.snapshot_path("snapshot.json")
        snapshot_path.write_text(
            json.dumps(
                {
                    "version": "ds_v1",
                    "task_type": "relation",
                    "sample_count": 0,
                    "dataset_id": "ds_001",
                    "samples": [],
                }
            ),
            encoding="utf-8",
        )
        goldset_path = store.goldset_path("gold.json")
        goldset_path.write_text(
            json.dumps(
                {
                    "version": "gold_v1",
                    "task_type": "relation",
                    "sample_count": 0,
                    "samples": [],
                    "goldset_id": "gold_001",
                }
            ),
            encoding="utf-8",
        )
        bundle_path = store.bundle_path("bundle.json")
        bundle_path.write_text(
            json.dumps({"version": "bundle_v1", "status": "PROPOSED"}), encoding="utf-8"
        )
        monkeypatch.setitem(app_main.app_state, "learning_event_store", store)
        output_path = store.snapshot_path("evaluation-output.json")
        output_path.write_text(
            json.dumps(
                {"metrics": {"f1": 0.8}, "dataset_version": "ds_v1", "goldset_version": "gold_v1"}
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(app_main, "evaluate_dataset", lambda snapshot, goldset: output_path)

        evaluation = asyncio.run(
            app_main.run_learning_evaluation(
                app_main.LearningEvaluationRunRequest(
                    snapshot_filename="snapshot.json", goldset_filename="gold.json"
                )
            )
        )
        promoted = asyncio.run(
            app_main.promote_learning_bundle(
                app_main.LearningBundlePromoteRequest(
                    bundle_filename="bundle.json", approved=True, deploy=True, notes="ship it"
                )
            )
        )

        assert evaluation["evaluation_filename"] == "evaluation-output.json"
        metrics = cast(dict[str, float], evaluation["metrics"])
        assert metrics["f1"] == 0.8
        assert promoted["status"] == "DEPLOYED"
        assert promoted["review_notes"] == "ship it"

    def test_council_decision_endpoint_records_manual_adjudication(self, monkeypatch):
        case = SimpleNamespace(
            case_id="case_1",
            candidate_id="rc_1",
            model_dump=lambda mode=None: {
                "case_id": "case_1",
                "candidate_id": "rc_1",
                "status": "CLOSED",
            },
        )
        candidate = SimpleNamespace(
            model_dump=lambda mode=None: {"candidate_id": "rc_1", "status": "COUNCIL_APPROVED"}
        )

        class _DummyCouncil:
            def __init__(self):
                self.recorded = []

            def get_case(self, case_id):
                return case if case_id == "case_1" else None

            def record_turn(self, **kwargs):
                self.recorded.append(("turn", kwargs))

            def cast_vote(self, **kwargs):
                self.recorded.append(("vote", kwargs))

            def finalize_case(self, **kwargs):
                self.recorded.append(("finalize", kwargs))
                return candidate

        council = _DummyCouncil()
        monkeypatch.setitem(app_main.app_state, "council", council)

        result = asyncio.run(
            app_main.decide_council_case(
                "case_1",
                app_main.CouncilDecisionRequest(
                    decision="approve", confidence=0.91, rationale="Looks good"
                ),
            )
        )

        candidate_payload = result["candidate"]
        assert candidate_payload is not None
        assert candidate_payload["status"] == "COUNCIL_APPROVED"
        assert any(kind == "vote" for kind, _ in council.recorded)

    def test_news_bridge_ingests_evaluated_news_and_creates_review_case(
        self, monkeypatch, tmp_path
    ):
        store = LearningEventStore(tmp_path)

        class _DummyCouncil:
            def submit_candidate(self, **kwargs):
                return SimpleNamespace(candidate_id="rc_news_001", council_case_id="case_news_001")

        monkeypatch.setattr(
            app_main,
            "ingest_text_into_ontology",
            lambda text, doc_id, metadata=None: {
                "doc_id": doc_id,
                "edge_count": 2,
                "chunks_created": 2,
                "total_chunks": 2,
                "domain_relations": 1,
                "personal_relations": 0,
                "council_relations": 0,
                "council_case_ids": [],
            },
        )
        monkeypatch.setitem(app_main.app_state, "learning_event_store", store)
        monkeypatch.setitem(app_main.app_state, "council", _DummyCouncil())
        monkeypatch.setitem(app_main.app_state, "ready", True)

        payload = app_main.NewsEvaluatePayload(
            headline="Oil slump supports airlines while pressuring energy producers",
            source="Reuters",
            novelty="new",
            overall_assessment="mixed",
            categories=["commodities", "equities"],
            entities=["oil", "airlines", "energy_producers"],
            impact_count=2,
            impacts=[
                NewsImpactPayload(
                    driver="oil",
                    target="airlines",
                    direction="positive",
                    confidence=0.72,
                    signal="supports",
                    sentence="Lower oil prices support airlines.",
                    rationale="Fuel costs fall for airlines.",
                )
            ],
            summary="Lower oil prices help airlines and hurt producers.",
            requires_manual_review=True,
            stored=False,
            evaluated_at=datetime.now(),
            body="Lower oil prices support airlines and pressure energy producers.",
        )

        result = asyncio.run(app_main.ingest_evaluated_news(payload))

        assert result.doc_id is not None
        assert result.doc_id.startswith("news_")
        assert result.destinations["domain"] == 1
        assert result.destinations["council"] == 1
        assert result.council_case_ids == ["case_news_001"]

        document = store.get_document(result.doc_id)
        assert document is not None
        assert document["source_type"] == "news_eval"
        assert document["metadata"]["impact_count"] == 2
        assert document["council_case_ids"] == ["case_news_001"]

    def test_ingest_text_persists_source_document_record(self, monkeypatch, tmp_path):
        store = LearningEventStore(tmp_path)

        class _DummyExtraction:
            def process(self, raw_text, doc_id, source_document=None):
                return SimpleNamespace(raw_edges=[], resolved_entities=[])

        app_main.app_state.extraction = _DummyExtraction()
        app_main.app_state.validation = object()
        app_main.app_state.domain = object()
        app_main.app_state.personal = object()
        app_main.app_state.learning_event_store = store
        app_main.app_state.ready = True

        asyncio.run(
            app_main.add_text_to_ontology(
                app_main.TextIngestRequest(
                    text="Higher policy rates pressure growth stocks.",
                    metadata={
                        "doc_id": "doc_002",
                        "title": "Policy Shock Note",
                        "institution": "Macro Lab",
                        "source_type": "research_note",
                    },
                ),
                background_tasks=BackgroundTasks(),
            )
        )

        document = store.get_document("doc_002")
        assert document is not None
        assert document["title"] == "Policy Shock Note"
        assert document["institution"] == "Macro Lab"
        assert document["input_type"] == "text"

    def test_structured_document_ingest_builds_marked_text_and_persists_sections(
        self, monkeypatch, tmp_path
    ):
        store = LearningEventStore(tmp_path)
        captured = {}

        def _fake_ingest(text, doc_id, metadata=None):
            captured["text"] = text
            captured["doc_id"] = doc_id
            captured["metadata"] = metadata or {}
            return {
                "doc_id": doc_id,
                "edge_count": 3,
                "chunks_created": 3,
                "total_chunks": 3,
                "domain_relations": 2,
                "personal_relations": 0,
                "council_relations": 1,
                "council_case_ids": ["case_struct_001"],
                "consolidated_relations": [
                    {
                        "head_entity_id": "Policy_Rate",
                        "relation_type": "pressures",
                        "tail_entity_id": "Growth_Stocks",
                        "fragment_count": 2,
                    }
                ],
            }

        monkeypatch.setattr(app_main, "ingest_text_into_ontology", _fake_ingest)
        monkeypatch.setitem(app_main.app_state, "learning_event_store", store)
        monkeypatch.setitem(app_main.app_state, "ready", True)

        request = app_main.StructuredDocumentIngestRequest(
            title="Macro Playbook",
            metadata={"institution": "Desk Research"},
            sections=[
                app_main.StructuredSectionRequest(
                    chapter_title="Chapter 1 Macro",
                    section_title="1.1 Rates",
                    text="Higher policy rates pressure growth stocks.",
                    page_number=1,
                ),
                app_main.StructuredSectionRequest(
                    chapter_title="Chapter 1 Macro",
                    section_title="1.2 Credit",
                    text="Wider spreads support bank margins.",
                    page_number=2,
                ),
            ],
        )

        result = asyncio.run(
            app_main.ingest_structured_document(request, background_tasks=BackgroundTasks())
        )

        assert result.doc_id is not None
        assert result.doc_id.startswith("structured_")
        assert "[PAGE 1]" in captured["text"]
        assert "Chapter 1 Macro" in captured["text"]
        assert captured["metadata"]["structured_sections"][0]["section_title"] == "1.1 Rates"
        document = store.get_document(result.doc_id)
        assert document is not None
        assert document["input_type"] == "structured_document"
        assert document["consolidated_relations"][0]["relation_type"] == "pressures"

    def test_extract_pdf_blocks_marks_table_and_ocr_need(self, monkeypatch):
        class _FakePage:
            def __init__(self, text):
                self._text = text

            def extract_text(self):
                return self._text

        class _FakeReader:
            def __init__(self, _stream):
                self.pages = [
                    _FakePage("Scenario Table\nRate  EPS  Banks\n5.0  2.1  1.4\n5.5  1.8  1.7"),
                    _FakePage(""),
                ]

        fake_module = SimpleNamespace(PdfReader=_FakeReader)
        monkeypatch.setitem(sys.modules, "pypdf", fake_module)

        payload = base64.b64encode(b"fake-pdf").decode("ascii")
        blocks = app_main.extract_pdf_blocks_from_base64(payload)

        assert blocks[0]["block_type"] == "table"
        assert blocks[1]["ocr_required"] is True

    def test_entity_and_graph_endpoints_return_console_shapes(self, monkeypatch):
        repo = InMemoryGraphRepository()
        repo.upsert_entity(
            "Policy_Rate", ["DomainEntity"], {"name": "policy rate", "type": "MacroIndicator"}
        )
        repo.upsert_entity(
            "Growth_Stocks", ["DomainEntity"], {"name": "growth stocks", "type": "AssetGroup"}
        )
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

        response = asyncio.run(
            app_main.ask(app_main.AskRequest(question="금리와 성장주의 관계는?"))
        )

        assert response.reasoning_used is False
        assert "[AI 답변]" in response.answer
        assert llm.last_prompt is not None
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
            first = client.post(
                "/api/text/add-to-vectordb", json={"text": "policy rates pressure growth stocks"}
            )
            second = client.post(
                "/api/text/add-to-vectordb", json={"text": "policy rates pressure growth stocks"}
            )

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["doc_id"] != second.json()["doc_id"]

    def test_ingest_text_passes_source_document_metadata_to_extraction(self):
        recorded = {}

        class _DummyExtraction:
            def process(self, raw_text, doc_id, source_document=None):
                recorded["raw_text"] = raw_text
                recorded["doc_id"] = doc_id
                recorded["source_document"] = source_document
                return SimpleNamespace(raw_edges=[], resolved_entities=[])

        app_main.app_state.extraction = _DummyExtraction()
        app_main.app_state.validation = object()
        app_main.app_state.domain = object()
        app_main.app_state.personal = object()

        result = app_main.ingest_text_into_ontology(
            text="Higher policy rates pressure growth stocks.",
            doc_id="doc_meta_001",
            metadata={
                "title": "Policy Shock Note",
                "author": "Analyst",
                "institution": "Macro Lab",
                "source_type": "research_note",
                "region": "us",
                "asset_scope": "equities",
                "language": "en",
                "document_quality_tier": "A",
            },
        )

        assert result["doc_id"] == "doc_meta_001"
        assert recorded["source_document"].doc_id == "doc_meta_001"
        assert recorded["source_document"].title == "Policy Shock Note"
        assert recorded["source_document"].institution == "Macro Lab"
        assert recorded["source_document"].document_quality_tier == "A"
