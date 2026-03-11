import base64
import ipaddress
import json
import logging
import os
import shutil
import socket
import subprocess
import tempfile
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from config.required_env_validator import summarize_runtime_env, validate_required_runtime_env
from config.settings import get_settings
from src.auth import external_identity_enabled, validate_bearer_role
from src.bootstrap import (
    build_llm_client,
    check_graph_repository_health,
    get_council_service,
    get_graph_repository,
    get_transaction_manager,
    load_config,
    reset_all,
)
from src.council.worker import CouncilAutomationWorker
from src.council.models import CouncilDecision, CouncilRole
from src.domain import DomainPipeline
from src.extraction import ExtractionPipeline
from src.integrations import (
    NewsEvaluatePayload,
    build_news_doc_id,
    build_news_ingest_text,
    build_news_metadata,
    impact_to_relation_fields,
    strongest_impact,
)
from src.infrastructure import distributed_coordination_enabled, get_coordination_provider
from src.learning.event_store import LearningEventStore, dump_json, load_json
from src.learning.offline_runner import evaluate_dataset, export_dataset
from src.learning.models import TaskType
from src.llm.provider_auth import (
    AuthType,
    HttpxConnectionTransport,
    ProviderAuthConfig,
    ProviderAuthManager,
    ProviderKind,
)
from src.personal import PersonalPipeline
from src.reasoning import ReasoningPipeline
from src.shared.models import RawEdge, ResolutionMode, ResolvedEntity, SourceDocument
from src.validation import ValidationPipeline
from src.validation.models import ValidationDestination, ValidationResult
from src.web.console_assets import resolve_console_asset_path
from src.web.operations_console import (
    build_dashboard_summary,
)
from src.web.operations_console import (
    list_audit_events as build_audit_listing,
)
from src.web.operations_console import (
    get_audit_event_detail as build_audit_detail,
)
from src.web.operations_console import (
    build_trust_summary,
)
from src.web.operations_console import (
    get_document_detail as build_document_detail,
)
from src.web.operations_console import (
    get_document_graph as build_document_graph,
)
from src.web.operations_console import (
    get_document_structure as build_document_structure,
)
from src.web.operations_console import (
    get_entity_detail as build_entity_detail,
)
from src.web.operations_console import (
    get_graph as build_graph_response,
)
from src.web.operations_console import (
    get_ingest_detail as build_ingest_detail,
)
from src.web.operations_console import (
    list_learning_products as build_learning_products,
)
from src.web.operations_console import (
    get_learning_product_detail as build_learning_product_detail,
)
from src.web.operations_console import (
    list_documents as build_document_listing,
)
from src.web.operations_console import (
    list_entities as build_entity_listing,
)
from src.web.operations_console import (
    search_documents as build_document_search,
)
from src.web.operations_console import (
    list_ingests as build_ingest_listing,
)


# Logging setup
class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra_payload = getattr(record, "structured", None)
        if isinstance(extra_payload, dict):
            payload.update(extra_payload)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _configure_logging() -> None:
    json_logs = os.environ.get("ONTRO_JSON_LOGS", "false").lower() in {"1", "true", "yes", "on"}
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        handler = logging.StreamHandler()
        root_logger.addHandler(handler)
    for handler in root_logger.handlers:
        handler.setFormatter(
            JsonLogFormatter()
            if json_logs
            else logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
    root_logger.setLevel(logging.INFO)


_configure_logging()
logger = logging.getLogger(__name__)


def log_event(level: int, event: str, **fields: Any) -> None:
    logger.log(level, event, extra={"structured": {"event": event, **fields}})


@dataclass
class AppState:
    llm_client: Any = None
    extraction: Any = None
    validation: Any = None
    domain: Any = None
    personal: Any = None
    council: Any = None
    reasoning: Any = None
    council_worker: Any = None
    learning_event_store: Any = None
    ai_runtime: dict[str, Any] = field(default_factory=dict)
    ai_connection_attempts: int = 0
    ready: bool = False
    storage_health: dict[str, Any] = field(
        default_factory=lambda: {"ok": False, "backend": "unknown"}
    )
    ingested_docs: int = 0
    ingested_edge_count: int = 0
    ingested_pdf_doc_count: int = 0
    request_counters: dict[str, list[float]] = field(default_factory=dict)
    request_totals: dict[str, int] = field(default_factory=dict)
    request_errors: dict[str, int] = field(default_factory=dict)
    # Deprecated aliases kept for one release while callers migrate.
    ingested_chunks: int = 0
    ingested_pdf_docs: int = 0

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)


# Global state
app_state = AppState()


def reset_app_state() -> None:
    global app_state
    app_state = AppState()


def _metric_value(primary_key: str, legacy_key: str | None = None) -> int:
    value = app_state.get(primary_key)
    if value is None and legacy_key:
        value = app_state.get(legacy_key)
    return int(value or 0)


def _increment_ingest_counters(*, docs: int = 0, edges: int = 0, pdf_docs: int = 0) -> None:
    app_state.ingested_docs = _metric_value("ingested_docs") + docs
    app_state.ingested_edge_count = _metric_value("ingested_edge_count", "ingested_chunks") + edges
    app_state.ingested_pdf_doc_count = (
        _metric_value("ingested_pdf_doc_count", "ingested_pdf_docs") + pdf_docs
    )
    # Deprecated aliases kept for one release while callers migrate to the clearer keys.
    app_state.ingested_chunks = app_state.ingested_edge_count
    app_state.ingested_pdf_docs = app_state.ingested_pdf_doc_count


def _generate_doc_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _api_security_enabled() -> bool:
    return external_identity_enabled() or any(
        os.environ.get(name, "").strip()
        for name in (
            "ONTRO_API_KEY",
            "ONTRO_API_KEY_ADMIN",
            "ONTRO_API_KEY_OPERATOR",
            "ONTRO_API_KEY_VIEWER",
        )
    )


def _resolve_api_key_role(request: Any) -> str | None:
    provided = (
        request.headers.get("x-api-key")
        or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    )
    if not provided:
        return None
    role_to_key = {
        "admin": os.environ.get("ONTRO_API_KEY_ADMIN", "").strip(),
        "operator": os.environ.get("ONTRO_API_KEY_OPERATOR", "").strip(),
        "viewer": os.environ.get("ONTRO_API_KEY_VIEWER", "").strip(),
    }
    if os.environ.get("ONTRO_API_KEY", "").strip():
        role_to_key["admin"] = os.environ.get("ONTRO_API_KEY", "").strip()
    for role, expected in role_to_key.items():
        if expected and provided == expected:
            return role
    return None


def _resolve_request_role(request: Any) -> str | None:
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer ") and external_identity_enabled():
        token = auth_header.split(" ", 1)[1].strip()
        return validate_bearer_role(token)
    return _resolve_api_key_role(request)


def _enforce_api_key(request: Any) -> None:
    if not _api_security_enabled():
        return
    if not hasattr(request, "state"):
        request.state = SimpleNamespace()
    try:
        role = _resolve_request_role(request)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if role is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    request.state.api_role = role


def _authorize_request(request: Any) -> None:
    if not hasattr(request, "state"):
        request.state = SimpleNamespace()
    role = getattr(request.state, "api_role", None)
    if role is None:
        return
    path = request.url.path
    method = request.method.upper()
    admin_only = {
        "/api/ingests/delete",
        "/api/council/process-pending",
        "/api/learning/bundles/promote",
    }
    operator_or_admin_prefixes = (
        "/api/text/",
        "/api/news/",
        "/api/pdf/",
        "/api/documents/ingest-structured",
        "/api/learning/evaluations/run",
    )
    if path in admin_only or path.startswith("/api/council/cases/") and path.endswith("/decision"):
        if role != "admin":
            raise HTTPException(status_code=403, detail="Admin role required")
    elif (
        path.startswith(operator_or_admin_prefixes)
        or path.startswith("/api/council/cases/")
        and path.endswith("/retry")
    ):
        if role not in {"admin", "operator"}:
            raise HTTPException(status_code=403, detail="Operator role required")
    elif path.startswith("/api/audit/"):
        if role not in {"admin", "operator"}:
            raise HTTPException(status_code=403, detail="Operator role required")


def _rate_limit_request(request: Any) -> None:
    limit_raw = os.environ.get("ONTRO_RATE_LIMIT_PER_MINUTE", "0").strip()
    if not limit_raw or limit_raw == "0":
        return
    limit = max(int(limit_raw), 1)
    client_key = request.client.host if request.client else "unknown"
    if distributed_coordination_enabled():
        provider = get_coordination_provider()
        if provider is None or not provider.rate_limit(
            key=f"ontro:rate:{client_key}:{request.url.path}", limit=limit, window_seconds=60
        ):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
    else:
        now_ts = datetime.now().timestamp()
        bucket = app_state.request_counters.setdefault(client_key, [])
        bucket[:] = [ts for ts in bucket if now_ts - ts < 60.0]
        if len(bucket) >= limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        bucket.append(now_ts)
    app_state.request_totals[request.url.path] = (
        app_state.request_totals.get(request.url.path, 0) + 1
    )


def _audit_log_request(request: Any) -> None:
    if os.environ.get("ONTRO_AUDIT_LOG", "false").lower() not in {"1", "true", "yes", "on"}:
        return
    event_store = app_state.learning_event_store
    if event_store is not None:
        event_store.append_audit(
            {
                "action": request.method.lower(),
                "path": request.url.path,
                "client": request.client.host if request.client else "unknown",
                "role": getattr(request.state, "api_role", None),
            }
        )
    log_event(
        logging.INFO,
        "audit_request",
        method=request.method,
        path=request.url.path,
        client=request.client.host if request.client else "unknown",
        role=getattr(request.state, "api_role", None),
    )


def _guard_request(request: Any) -> None:
    if not hasattr(request, "state"):
        request.state = SimpleNamespace()
    _enforce_api_key(request)
    _authorize_request(request)
    _rate_limit_request(request)
    _audit_log_request(request)


def _maybe_guard_request(request: Any | None) -> None:
    if request is None:
        return
    _guard_request(request)


def _build_ai_provider_config() -> ProviderAuthConfig:
    settings = get_settings()
    return ProviderAuthConfig(
        provider=ProviderKind.OLLAMA,
        auth_type=AuthType.NONE,
        base_url=settings.ollama.base_url,
        healthcheck_path="/api/tags",
        timeout_seconds=min(float(settings.ollama.timeout), 5.0),
    )


def _provider_label(provider: ProviderKind) -> str:
    labels = {
        ProviderKind.OLLAMA: "Ollama",
        ProviderKind.OPENAI_GPT_SDK: "OpenAI GPT SDK",
        ProviderKind.GITHUB_COPILOT_OAUTH_APP: "GitHub Copilot OAuth App",
    }
    return labels.get(provider, provider.value)


def _refresh_ai_runtime_status() -> dict[str, Any]:
    settings = get_settings()
    auth_manager = ProviderAuthManager()
    config = _build_ai_provider_config()

    app_state.ai_connection_attempts += 1
    result = auth_manager.test_connection(
        config=config,
        transport=HttpxConnectionTransport(),
        env=os.environ,
    )

    model_name = settings.ollama.model_name
    llm_client = app_state.get("llm_client")
    if llm_client and hasattr(llm_client, "get_model_name"):
        try:
            model_name = llm_client.get_model_name()
        except Exception:
            model_name = settings.ollama.model_name

    payload = {
        "provider": config.provider.value,
        "provider_label": _provider_label(config.provider),
        "model_name": model_name,
        "base_url": config.base_url,
        "auth_type": config.auth_type.value,
        "auth_required": config.auth_type != AuthType.NONE,
        "auth_configured": not bool(result.missing_env),
        "connected": result.success,
        "status": "connected" if result.success else "disconnected",
        "message": result.message or ("ok" if result.success else "Connection check failed"),
        "checked_url": result.checked_url,
        "available_models": result.available_models,
        "missing_env": result.missing_env,
        "last_checked_at": datetime.now().isoformat(),
        "attempts": app_state.ai_connection_attempts,
        "members": [],
    }

    council = app_state.get("council")
    if council is not None:
        try:
            member_statuses = council.refresh_member_availability(env=os.environ)
        except Exception as exc:
            logger.warning(
                "Council member availability refresh failed during AI runtime check", exc_info=exc
            )
            member_statuses = council.get_member_statuses()

        member_payloads: list[dict[str, Any]] = []
        for member in council.member_registry.list_members(enabled_only=False):
            member_result = member_statuses.get(member.member_id)
            missing_env = council.member_registry.auth_manager.missing_env_vars(
                member.auth, os.environ
            )
            member_payloads.append(
                {
                    "member_id": member.member_id,
                    "role": member.role.value,
                    "provider": member.provider.value,
                    "provider_label": _provider_label(member.provider),
                    "model_name": member.effective_model_name or member.model_name or "-",
                    "base_url": member.auth.base_url,
                    "auth_type": member.auth.auth_type.value,
                    "auth_required": member.auth.auth_type != AuthType.NONE,
                    "auth_configured": not bool(missing_env),
                    "connected": bool(member_result and member_result.success),
                    "status": "connected"
                    if member_result and member_result.success
                    else "disconnected",
                    "message": (
                        member_result.message
                        if member_result is not None
                        else "Connection has not been checked yet"
                    ),
                    "checked_url": (
                        member_result.checked_url
                        if member_result is not None
                        else f"{member.auth.base_url.rstrip('/')}/{member.auth.healthcheck_path.lstrip('/')}"
                    ),
                    "available_models": member_result.available_models
                    if member_result is not None
                    else [],
                    "missing_env": missing_env,
                    "attempts": app_state.ai_connection_attempts,
                }
            )

        payload["members"] = member_payloads

    app_state.ai_runtime = payload
    return payload


def load_sample_data() -> dict[str, int]:
    loaded_docs = 0
    loaded_chunks = 0
    try:
        sample_path = Path(__file__).parent / "data" / "samples" / "sample_documents.json"
        if not sample_path.exists():
            logger.warning("Sample data not found. Skipping initial load.")
            return {"docs_loaded": 0, "chunks_loaded": 0}

        with open(sample_path, encoding="utf-8") as f:
            documents = json.load(f)

        logger.info(f"Loading {len(documents)} sample documents...")

        for doc in documents:
            doc_id = doc.get("doc_id")
            text = doc.get("text", "")
            metadata = dict(doc.get("metadata", {}))
            metadata.setdefault("source", "sample_seed")

            # PDF Processing Support
            if text.lower().endswith(".pdf"):
                metadata["document_format"] = "pdf"
                pdf_path = Path(__file__).parent / "data" / "pdfs" / text
                try:
                    import pypdf

                    if pdf_path.exists():
                        logger.info(f"Processing PDF: {text}")
                        reader = pypdf.PdfReader(pdf_path)
                        extracted_text = ""
                        for page in reader.pages:
                            extracted_text += page.extract_text() + "\n"
                        text = extracted_text
                        logger.info(f"Extracted {len(text)} chars from PDF")
                    else:
                        logger.warning(f"PDF file not found: {pdf_path}")
                        continue
                except ImportError:
                    logger.error("pypdf not installed. Skipping PDF processing.")
                    continue
                except Exception as e:
                    logger.error(f"Error processing PDF {text}: {e}")
                    continue

            result = ingest_text_into_ontology(text=text, doc_id=doc_id, metadata=metadata)
            loaded_docs += 1
            loaded_chunks += result["edge_count"]

        logger.info(f"Sample data loaded: docs={loaded_docs}, chunks={loaded_chunks}")
        return {"docs_loaded": loaded_docs, "chunks_loaded": loaded_chunks}

    except Exception as e:
        logger.error(f"Error loading sample data: {e}")
        return {"docs_loaded": loaded_docs, "chunks_loaded": loaded_chunks}


def _normalized_allowed_hosts() -> list[str]:
    settings = get_settings()
    return [
        host.strip().lower().rstrip(".")
        for host in settings.callbacks.allowed_hosts
        if host.strip()
    ]


def _resolved_host_ips(hostname: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"Callback host could not be resolved: {hostname}") from exc

    ips = sorted({str(info[4][0]) for info in infos if info[4]})
    if not ips:
        raise ValueError(f"Callback host resolved to no addresses: {hostname}")
    return ips


def _is_forbidden_callback_ip(raw_ip: str) -> bool:
    ip = ipaddress.ip_address(raw_ip)
    return any(
        [
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
        ]
    )


def validate_callback_url(callback_url: str) -> str:
    settings = get_settings()
    allowed_hosts = _normalized_allowed_hosts()

    if not settings.callbacks.enabled:
        raise ValueError("Callback delivery is disabled")

    parsed = urlparse(callback_url)
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower().rstrip(".")

    if scheme not in settings.callbacks.allowed_schemes:
        raise ValueError(f"Callback scheme '{scheme}' is not allowed")
    if not hostname:
        raise ValueError("Callback host is required")
    if parsed.username or parsed.password:
        raise ValueError("Callback credentials in URL are not allowed")
    if not allowed_hosts:
        raise ValueError("Callback allowlist is not configured")
    if hostname == "localhost":
        raise ValueError("Callback host must not target localhost")

    host_allowed = any(
        hostname == allowed or hostname.endswith(f".{allowed}") for allowed in allowed_hosts
    )
    if not host_allowed:
        raise ValueError(f"Callback host '{hostname}' is not allowlisted")

    try:
        resolved_ips = [str(ipaddress.ip_address(hostname))]
    except ValueError:
        resolved_ips = _resolved_host_ips(hostname)

    if any(_is_forbidden_callback_ip(ip) for ip in resolved_ips):
        raise ValueError("Callback host resolves to a private or loopback address")

    return callback_url


def extract_pdf_blocks_from_base64(pdf_base64: str) -> list[dict[str, Any]]:
    try:
        import pypdf

        pdf_bytes = base64.b64decode(pdf_base64)
        reader = pypdf.PdfReader(BytesIO(pdf_bytes))
        blocks: list[dict[str, Any]] = []
        for index, page in enumerate(reader.pages, start=1):
            page_text = (page.extract_text() or "").strip()
            if not page_text:
                ocr_text, ocr_error = _ocr_page_images(page)
                if ocr_text:
                    for raw_block in [
                        block.strip() for block in ocr_text.split("\n\n") if block.strip()
                    ]:
                        block_type = "table" if _looks_like_table_block(raw_block) else "paragraph"
                        blocks.append(
                            {
                                "page_number": index,
                                "text": raw_block,
                                "block_type": block_type,
                                "ocr_required": False,
                                "ocr_applied": True,
                                "ocr_engine": _ocr_command(),
                            }
                        )
                    continue
                blocks.append(
                    {
                        "page_number": index,
                        "text": "",
                        "block_type": "ocr_needed",
                        "ocr_required": True,
                        "ocr_applied": False,
                        "ocr_engine": _ocr_command() if _ocr_enabled() else None,
                        "ocr_error": ocr_error,
                    }
                )
                continue
            for raw_block in [block.strip() for block in page_text.split("\n\n") if block.strip()]:
                block_type = "table" if _looks_like_table_block(raw_block) else "paragraph"
                blocks.append(
                    {
                        "page_number": index,
                        "text": raw_block,
                        "block_type": block_type,
                        "ocr_required": False,
                        "ocr_applied": False,
                        "ocr_engine": None,
                    }
                )
        if not blocks:
            raise ValueError("No text content extracted from PDF")
        return blocks
    except Exception as e:
        raise ValueError(f"Failed to parse PDF: {e}")


def _looks_like_table_block(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    numeric_lines = sum(1 for line in lines if any(char.isdigit() for char in line))
    separated_lines = sum(1 for line in lines if "|" in line or "\t" in line or "  " in line)
    return numeric_lines >= max(1, len(lines) // 2) and separated_lines >= max(1, len(lines) // 2)


def _ocr_enabled() -> bool:
    return os.environ.get("ONTRO_OCR_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


def _ocr_command() -> str:
    return os.environ.get("ONTRO_OCR_COMMAND", "tesseract").strip() or "tesseract"


def _ocr_page_images(page: Any) -> tuple[str, str | None]:
    if not _ocr_enabled():
        return "", None
    images = list(getattr(page, "images", []) or [])
    if not images:
        return "", "no_page_images"

    outputs: list[str] = []
    for index, image in enumerate(images, start=1):
        image_data = getattr(image, "data", None)
        if not image_data:
            continue
        image_name = getattr(image, "name", f"page-image-{index}.png")
        suffix = Path(str(image_name)).suffix or ".png"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(image_data)
            temp_path = Path(handle.name)
        try:
            result = subprocess.run(
                [_ocr_command(), str(temp_path), "stdout", "--psm", "6"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                outputs.append(result.stdout.strip())
        except FileNotFoundError:
            return "", "tesseract_not_installed"
        except subprocess.TimeoutExpired:
            return "", "tesseract_timeout"
        finally:
            temp_path.unlink(missing_ok=True)

    if not outputs:
        return "", "no_ocr_output"
    return "\n\n".join(outputs), None


def extract_pdf_text_from_base64(pdf_base64: str) -> str:
    blocks = extract_pdf_blocks_from_base64(pdf_base64)
    parts = []
    for block in blocks:
        header = f"[PAGE {block['page_number']}]"
        if block.get("block_type") == "table":
            header += "\n[TABLE]"
        if block.get("ocr_required"):
            header += "\n[OCR_REQUIRED]"
        parts.append(f"{header}\n{block['text']}")
    text = "\n\n".join(parts).strip()
    if not text:
        raise ValueError("No text content extracted from PDF")
    return text


def _log_validation_event(edge, validation_result) -> None:
    event_store = app_state.get("learning_event_store")
    if event_store is None:
        return

    event_store.append(
        "validation",
        {
            "edge_id": edge.raw_edge_id,
            "fragment_id": edge.fragment_id,
            "fragment_text": edge.fragment_text,
            "source_document_id": edge.source_document_id,
            "source_type": edge.source_type,
            "published_at": edge.published_at.isoformat() if edge.published_at else None,
            "time_scope": edge.time_scope,
            "citation_page_number": edge.citation_page_number,
            "citation_chapter_title": edge.citation_chapter_title,
            "citation_section_title": edge.citation_section_title,
            "head_entity_id": edge.head_entity_id,
            "tail_entity_id": edge.tail_entity_id,
            "relation_type": edge.relation_type,
            "polarity_guess": edge.polarity_guess,
            "validation_passed": validation_result.validation_passed,
            "destination": validation_result.destination.value,
            "combined_conf": validation_result.combined_conf,
            "semantic_tag": validation_result.semantic_result.semantic_tag
            if validation_result.semantic_result
            else None,
            "rejection_reason": validation_result.rejection_reason,
        },
    )


def _log_query_event(question: str, conclusion=None, error: str | None = None) -> None:
    event_store = app_state.get("learning_event_store")
    if event_store is None:
        return

    payload = {
        "question": question,
        "error": error,
    }
    if conclusion is not None:
        payload.update(
            {
                "confidence": getattr(conclusion, "confidence", None),
                "answer": getattr(conclusion, "conclusion_text", None),
                "evidence_summary": getattr(conclusion, "evidence_summary", None),
            }
        )
    event_store.append("query", payload)


def _log_ingest_event(
    *,
    doc_id: str,
    input_type: str,
    metadata: dict[str, Any] | None,
    edge_count: int,
    destinations: dict[str, int],
    council_case_ids: list[str],
    filename: str | None = None,
    text_preview: str | None = None,
    replay_text: str | None = None,
) -> None:
    event_store = app_state.get("learning_event_store")
    if event_store is None:
        return

    event_store.append(
        "ingest",
        {
            "doc_id": doc_id,
            "input_type": input_type,
            "filename": filename,
            "metadata": metadata or {},
            "edge_count": edge_count,
            "destinations": destinations,
            "council_case_ids": council_case_ids,
            "text_preview": text_preview,
            "replay_text": replay_text,
        },
    )


def _build_destination_counts(result: dict[str, Any]) -> dict[str, int]:
    return {
        "domain": result["domain_relations"],
        "personal": result["personal_relations"],
        "council": result["council_relations"],
    }


def _normalize_datetime_value(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _sync_source_document_record(
    *,
    doc_id: str,
    input_type: str,
    metadata: dict[str, Any] | None,
    edge_count: int,
    destinations: dict[str, int],
    council_case_ids: list[str],
    filename: str | None = None,
    text_preview: str | None = None,
    consolidated_relations: list[dict[str, Any]] | None = None,
) -> None:
    event_store = app_state.get("learning_event_store")
    if event_store is None:
        return

    metadata = metadata or {}
    event_store.upsert_document(
        {
            "doc_id": doc_id,
            "title": metadata.get("title") or metadata.get("doc_title"),
            "author": metadata.get("author"),
            "institution": metadata.get("institution"),
            "published_at": _normalize_datetime_value(metadata.get("published_at")),
            "source_type": str(metadata.get("source_type") or metadata.get("source") or input_type),
            "region": metadata.get("region"),
            "asset_scope": metadata.get("asset_scope"),
            "language": metadata.get("language"),
            "document_quality_tier": metadata.get("document_quality_tier"),
            "input_type": input_type,
            "filename": filename,
            "edge_count": edge_count,
            "destinations": destinations,
            "council_case_ids": council_case_ids,
            "text_preview": text_preview,
            "consolidated_relations": consolidated_relations or [],
            "metadata": metadata,
        }
    )


def _append_document_council_case(doc_id: str, case_id: str) -> None:
    event_store = app_state.get("learning_event_store")
    if event_store is None:
        return
    record = event_store.get_document(doc_id)
    if record is None:
        return
    existing_case_ids = [str(item) for item in record.get("council_case_ids", [])]
    if case_id not in existing_case_ids:
        existing_case_ids.append(case_id)
    record["council_case_ids"] = existing_case_ids
    destinations = dict(record.get("destinations") or {})
    destinations["council"] = max(int(destinations.get("council", 0)), len(existing_case_ids))
    record["destinations"] = destinations
    event_store.upsert_document(record)


def _submit_news_review_candidate(payload: NewsEvaluatePayload, doc_id: str) -> list[str]:
    strongest = strongest_impact(payload)
    if strongest is None:
        return []

    council = app_state.get("council")
    if council is None:
        return []

    relation_type, polarity = impact_to_relation_fields(strongest)
    edge = RawEdge(
        head_entity_id=strongest.driver,
        head_canonical_name=strongest.driver,
        tail_entity_id=strongest.target,
        tail_canonical_name=strongest.target,
        relation_type=relation_type,
        polarity_guess=polarity,
        student_conf=strongest.confidence,
        fragment_id=f"news_bridge_{doc_id}",
        fragment_text=strongest.sentence,
        source_document_id=doc_id,
        source_type="news_eval",
        published_at=payload.published_at,
        source_metadata={
            "headline": payload.headline,
            "summary": payload.summary,
            "signal": strongest.signal,
            "rationale": strongest.rationale,
            "requires_manual_review": payload.requires_manual_review,
            "overall_assessment": payload.overall_assessment,
        },
    )
    resolved_entities = [
        ResolvedEntity(
            entity_id=strongest.driver,
            canonical_id=strongest.driver,
            canonical_name=strongest.driver,
            resolution_mode=ResolutionMode.NEW_ENTITY,
            resolution_conf=1.0,
            surface_text=strongest.driver,
            fragment_id=edge.fragment_id,
        ),
        ResolvedEntity(
            entity_id=strongest.target,
            canonical_id=strongest.target,
            canonical_name=strongest.target,
            resolution_mode=ResolutionMode.NEW_ENTITY,
            resolution_conf=1.0,
            surface_text=strongest.target,
            fragment_id=edge.fragment_id,
        ),
    ]
    validation_result = ValidationResult(
        edge_id=edge.raw_edge_id,
        validation_passed=True,
        destination=ValidationDestination.DOMAIN_CANDIDATE,
        combined_conf=min(strongest.confidence, 0.69),
        student_conf=strongest.confidence,
        semantic_conf=strongest.confidence,
    )
    candidate = council.submit_candidate(
        edge=edge,
        validation_result=validation_result,
        resolved_entities=resolved_entities,
        source_document_id=doc_id,
        chunk_id=edge.fragment_id,
        source_type="news_eval",
        source_metadata={
            "headline": payload.headline,
            "summary": payload.summary,
            "impact_count": payload.impact_count,
            "categories": payload.categories,
            "entities": payload.entities,
            "news_impacts": [impact.model_dump(mode="json") for impact in payload.impacts],
        },
    )
    if candidate.council_case_id:
        _append_document_council_case(doc_id, candidate.council_case_id)
        return [candidate.council_case_id]
    return []


def _build_structured_document_text(sections: list[Any]) -> str:
    parts: list[str] = []
    for section in sections:
        if section.page_number is not None:
            parts.append(f"[PAGE {section.page_number}]")
        if section.chapter_title:
            parts.append(section.chapter_title)
        if section.section_title:
            parts.append(section.section_title)
        parts.append(section.text)
        parts.append("")
    return "\n".join(parts).strip()


def _learning_store() -> LearningEventStore:
    event_store = app_state.get("learning_event_store")
    if event_store is None:
        raise RuntimeError("Learning event store is not available")
    return event_store


def _bundle_file_path(bundle_filename: str) -> Path:
    return _learning_store().bundle_path(bundle_filename)


def _snapshot_file_path(snapshot_filename: str) -> Path:
    return _learning_store().snapshot_path(snapshot_filename)


def _goldset_file_path(goldset_filename: str) -> Path:
    return _learning_store().goldset_path(goldset_filename)


def _promote_bundle_file(
    bundle_filename: str, approved: bool, deploy: bool, notes: str, reviewer: str
) -> dict[str, Any]:
    path = _bundle_file_path(bundle_filename)
    if not path.exists():
        raise FileNotFoundError(bundle_filename)
    payload = load_json(path)
    payload["reviewed_by"] = reviewer
    payload["review_notes"] = notes
    payload["reviewed_at"] = datetime.now().isoformat()
    payload["status"] = (
        "DEPLOYED" if approved and deploy else ("REVIEWED" if approved else "ROLLED_BACK")
    )
    if deploy:
        payload["deployed_at"] = datetime.now().isoformat()
    dump_json(path, payload)
    return payload


def ingest_text_into_ontology(
    text: str,
    doc_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not text or not text.strip():
        raise ValueError("No text provided for ingestion")

    extraction = app_state.extraction
    validation = app_state.validation
    domain = app_state.domain
    personal = app_state.personal

    if not all([extraction, validation, domain, personal]):
        raise RuntimeError("Ontology pipelines are not ready")

    metadata = metadata or {}
    logger.info(f"Ingesting document {doc_id} (source={metadata.get('source', 'external')})")

    source_document = SourceDocument(
        doc_id=doc_id,
        title=metadata.get("title"),
        author=metadata.get("author"),
        institution=metadata.get("institution"),
        published_at=metadata.get("published_at"),
        source_type=str(metadata.get("source_type") or metadata.get("source") or "research_note"),
        region=metadata.get("region"),
        asset_scope=metadata.get("asset_scope"),
        language=metadata.get("language"),
        document_quality_tier=metadata.get("document_quality_tier"),
        metadata=metadata,
    )

    ext = extraction.process(raw_text=text, doc_id=doc_id, source_document=source_document)
    edge_count = len(ext.raw_edges)
    consolidated_relations = list(getattr(ext, "consolidated_relations", []))
    _increment_ingest_counters(
        docs=1,
        edges=edge_count,
        pdf_docs=1 if metadata.get("document_format") == "pdf" else 0,
    )

    if not ext.raw_edges:
        return {
            "doc_id": doc_id,
            "edge_count": 0,
            "chunks_created": 0,
            "total_chunks": 0,
            "domain_relations": 0,
            "personal_relations": 0,
            "council_relations": 0,
            "council_case_ids": [],
            "consolidated_relations": consolidated_relations,
        }

    vals = validation.validate_batch(
        edges=ext.raw_edges,
        resolved_entities=ext.resolved_entities,
    )
    val_map = {v.edge_id: v for v in vals}
    for edge in ext.raw_edges:
        validation_result = val_map.get(edge.raw_edge_id)
        if validation_result:
            _log_validation_event(edge, validation_result)

    domain_results = []
    personal_results = []
    council_case_ids: list[str] = []

    domain_edges = [
        edge
        for edge in ext.raw_edges
        if (val_map.get(edge.raw_edge_id) and val_map[edge.raw_edge_id].validation_passed)
        and val_map[edge.raw_edge_id].destination == ValidationDestination.DOMAIN_CANDIDATE
    ]

    if domain_edges:
        domain_results = domain.process_batch(domain_edges, val_map, ext.resolved_entities)
        for dom_result in domain_results:
            if dom_result.final_destination == "personal" and dom_result.intake_result:
                personal_result = personal.process_from_domain_rejection(
                    dom_result.intake_result, dom_result
                )
                if personal_result:
                    personal_results.append(personal_result)
            elif dom_result.final_destination == "council" and dom_result.council_case_id:
                council_case_ids.append(dom_result.council_case_id)

    for edge in ext.raw_edges:
        v = val_map.get(edge.raw_edge_id)
        if not v or not v.validation_passed:
            continue

        if v.destination == ValidationDestination.PERSONAL_CANDIDATE:
            personal_result = personal.process_from_validation(edge, v, ext.resolved_entities)
            if personal_result:
                personal_results.append(personal_result)

    return {
        "doc_id": doc_id,
        "edge_count": edge_count,
        "chunks_created": edge_count,
        "total_chunks": edge_count,
        "domain_relations": len(
            [result for result in domain_results if result.final_destination == "domain"]
        ),
        "personal_relations": len(personal_results),
        "council_relations": len(council_case_ids),
        "council_case_ids": council_case_ids,
        "consolidated_relations": consolidated_relations,
    }


def queue_callback(background_tasks: BackgroundTasks, callback_url: str, payload: dict[str, Any]):
    def _dispatch():
        try:
            httpx.post(callback_url, json=payload, timeout=10)
        except Exception as e:
            logger.warning(f"Callback to {callback_url} failed: {e}")

    background_tasks.add_task(_dispatch)


async def _shutdown_runtime(*, reset_state: bool) -> None:
    worker = app_state.council_worker
    if worker:
        await worker.stop()

    llm_client = app_state.llm_client
    if llm_client and hasattr(llm_client, "close"):
        llm_client.close()

    if reset_state:
        reset_app_state()


async def _initialize_runtime(*, load_sample_data_override: bool | None = None) -> None:
    logger.info("Initializing Ontology System v11...")
    reset_app_state()
    settings = get_settings()
    bootstrap_config = load_config()
    validate_required_runtime_env(bootstrap_config)
    if os.environ.get("ONTRO_NEO4J_USERNAME") and not os.environ.get("ONTRO_NEO4J_USER"):
        logger.warning("ONTRO_NEO4J_USERNAME is deprecated; use ONTRO_NEO4J_USER")
    runtime_summary = summarize_runtime_env(bootstrap_config)
    logger.info(
        "Startup configuration: backend=%s council_auto=%s sample_data=%s callbacks=%s env=%s",
        runtime_summary["storage_backend"],
        runtime_summary["council_auto_enabled"],
        runtime_summary["load_sample_data"],
        runtime_summary["callbacks_enabled"],
        ",".join(runtime_summary["loaded_env_names"]),
    )
    repo = get_graph_repository()
    storage_health = check_graph_repository_health(repo)
    if not storage_health["ok"]:
        raise RuntimeError(f"Storage backend unavailable: {storage_health}")
    app_state.storage_health = storage_health
    event_store = LearningEventStore(settings.store.learning_data_path)

    llm_client = build_llm_client()
    use_llm = False
    try:
        if llm_client:
            use_llm = llm_client.health_check()
    except Exception as e:
        logger.error("LLM health check failed", exc_info=e)

    if use_llm:
        logger.info(f"[OK] Ollama connected: {settings.ollama.model_name}")
    else:
        logger.warning("[FAIL] Ollama not available, using rule-based mode")
        llm_client = None

    app_state.llm_client = llm_client

    extraction = ExtractionPipeline(llm_client=llm_client, use_llm=use_llm)
    validation = ValidationPipeline(llm_client=llm_client, use_llm=use_llm)
    domain = DomainPipeline()
    personal_storage_path = settings.store.personal_data_path / "default_user.json"
    personal = PersonalPipeline(
        user_id="default_user",
        static_guard=domain.static_guard,
        dynamic_domain=domain.dynamic_update,
        storage_path=personal_storage_path,
    )
    reasoning = ReasoningPipeline(
        domain=domain.dynamic_update,
        personal=personal.get_pkg(),
        llm_client=llm_client,
        ner=extraction.ner_student,
        resolver=extraction.entity_resolver,
    )

    app_state.extraction = extraction
    app_state.validation = validation
    app_state.domain = domain
    app_state.personal = personal
    app_state.reasoning = reasoning
    app_state.council = get_council_service()
    app_state.learning_event_store = event_store
    app_state.council.event_store = event_store

    try:
        app_state.council.refresh_member_availability(env=os.environ)
    except Exception as exc:
        logger.warning("Council member availability refresh failed", exc_info=exc)

    _refresh_ai_runtime_status()

    council_worker = CouncilAutomationWorker(
        service=app_state.council,
        poll_interval_seconds=settings.council_runtime.poll_interval_seconds,
    )
    app_state.council_worker = council_worker
    if settings.council_runtime.auto_process_enabled:
        await council_worker.start()

    should_load_sample_data = (
        settings.runtime.load_sample_data_on_startup
        if load_sample_data_override is None
        else load_sample_data_override
    )
    if should_load_sample_data:
        load_sample_data()
    else:
        logger.info(
            "Startup sample ingestion disabled. Set ONTRO_LOAD_SAMPLE_DATA=true to enable it."
        )

    app_state.ready = True
    logger.info("Ontology System v11 initialized successfully.")


def _reset_personal_storage() -> None:
    personal_root = get_settings().store.personal_data_path
    if personal_root.exists():
        shutil.rmtree(personal_root)
    personal_root.mkdir(parents=True, exist_ok=True)


async def _replay_retained_ingests(retained_rows: list[dict[str, Any]]) -> None:
    repo = get_graph_repository()

    await _shutdown_runtime(reset_state=False)
    repo.clear()
    close_repo = getattr(repo, "close", None)
    if callable(close_repo):
        close_repo()

    _reset_personal_storage()
    reset_all()
    await _initialize_runtime(load_sample_data_override=False)

    event_store = app_state.get("learning_event_store")
    if event_store is None:
        raise RuntimeError("Learning event store is not available")

    for event_type in ("ingest", "validation", "council_candidate", "council_final", "query"):
        event_store.clear(event_type)
    event_store.clear_documents()

    for row in retained_rows:
        replay_text = str(row.get("replay_text") or "")
        metadata = dict(row.get("metadata") or {})
        result = ingest_text_into_ontology(
            text=replay_text,
            doc_id=row["doc_id"],
            metadata=metadata,
        )
        destinations = _build_destination_counts(result)
        _log_ingest_event(
            doc_id=row["doc_id"],
            input_type=row.get("input_type", "text"),
            metadata=metadata,
            edge_count=result["edge_count"],
            destinations=destinations,
            council_case_ids=result["council_case_ids"],
            filename=row.get("filename"),
            text_preview=row.get("text_preview") or (replay_text[:200] if replay_text else None),
            replay_text=replay_text,
        )
        _sync_source_document_record(
            doc_id=row["doc_id"],
            input_type=row.get("input_type", "text"),
            metadata=metadata,
            edge_count=int(result["edge_count"]),
            destinations=destinations,
            council_case_ids=result["council_case_ids"],
            filename=row.get("filename"),
            text_preview=row.get("text_preview") or (replay_text[:200] if replay_text else None),
            consolidated_relations=result.get("consolidated_relations", []),
        )


async def delete_selected_ingests(doc_ids: list[str]) -> dict[str, Any]:
    if not app_state.ready:
        raise RuntimeError("System not ready")

    selected_doc_ids = sorted({doc_id.strip() for doc_id in doc_ids if doc_id and doc_id.strip()})
    if not selected_doc_ids:
        raise ValueError("At least one document must be selected for deletion")

    event_store = app_state.get("learning_event_store")
    if event_store is None:
        raise RuntimeError("Learning event store is not available")

    existing_rows = event_store.read("ingest")
    matched_rows = [row for row in existing_rows if row.get("doc_id") in selected_doc_ids]
    if not matched_rows:
        raise LookupError("Selected ingest records were not found")

    retained_rows = [row for row in existing_rows if row.get("doc_id") not in selected_doc_ids]
    missing_replay_doc_ids = [
        row.get("doc_id", "unknown") for row in retained_rows if not row.get("replay_text")
    ]
    if missing_replay_doc_ids:
        raise RuntimeError(
            "Selective deletion is blocked because some retained records cannot be replayed: "
            + ", ".join(missing_replay_doc_ids)
        )

    await _replay_retained_ingests(retained_rows)
    return {
        "status": "success",
        "deleted_doc_ids": [row["doc_id"] for row in matched_rows],
        "remaining_ingests": len(retained_rows),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _initialize_runtime()

    yield

    await _shutdown_runtime(reset_state=True)
    logger.info("Ontology System v11 shutdown.")


app = FastAPI(title="Ontology System v11", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def guard_api_requests(request: Request, call_next):
    guarded_paths = (
        "/api/text/",
        "/api/news/",
        "/api/documents/",
        "/api/learning/",
        "/api/ingests/delete",
        "/api/council/",
    )
    try:
        if request.url.path.startswith(guarded_paths):
            _guard_request(request)
        response = await call_next(request)
        return response
    except HTTPException:
        app_state.request_errors[request.url.path] = (
            app_state.request_errors.get(request.url.path, 0) + 1
        )
        raise
    except Exception:
        app_state.request_errors[request.url.path] = (
            app_state.request_errors.get(request.url.path, 0) + 1
        )
        raise


# Models
class TextIngestRequest(BaseModel):
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    callback_url: str | None = None


class PDFIngestRequest(BaseModel):
    pdf_data: str
    filename: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    callback_url: str | None = None


class PDFNotifyRequest(BaseModel):
    filename: str
    file_path: str | None = None
    timestamp: str | None = None
    source: str | None = None


class DeleteIngestsRequest(BaseModel):
    doc_ids: list[str] = Field(default_factory=list)


class IngestResponse(BaseModel):
    status: str
    message: str
    edge_count: int = 0
    chunks_created: int = 0
    total_chunks: int = 0
    doc_id: str | None = None
    destinations: dict[str, int] = Field(default_factory=dict)
    council_case_ids: list[str] = Field(default_factory=list)


class NewsBridgeResponse(IngestResponse):
    headline: str
    impact_count: int = 0
    requires_manual_review: bool = False


class StructuredSectionRequest(BaseModel):
    chapter_title: str | None = None
    section_title: str | None = None
    text: str
    page_number: int | None = None


class StructuredDocumentIngestRequest(BaseModel):
    title: str
    sections: list[StructuredSectionRequest] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    callback_url: str | None = None


class CouncilDecisionRequest(BaseModel):
    decision: str
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    rationale: str = ""
    agent_id: str = "human_reviewer"
    apply_to_domain: bool = True


class LearningEvaluationRunRequest(BaseModel):
    task_type: str = TaskType.RELATION.value
    goldset_filename: str
    snapshot_filename: str | None = None


class LearningBundlePromoteRequest(BaseModel):
    bundle_filename: str
    approved: bool = True
    deploy: bool = False
    notes: str = ""
    reviewer: str = "human"


class AskRequest(BaseModel):
    question: str
    mode: str = "accuracy"
    k: str = "auto"


class AskResponse(BaseModel):
    answer: str
    confidence: float
    sources: list[dict[str, Any]] = []
    reasoning_used: bool = False
    reasoning_trace: list[str] = []
    action_suggested: str | None = None
    metrics: dict[str, Any] = {}
    timestamp: str


class BatchRequest(BaseModel):
    items: list[dict[str, Any]]
    mode: str = "accuracy"


class BatchResponse(BaseModel):
    results: list[dict[str, Any]]
    config_hash: str = "default"


@app.post("/api/text/add-to-vectordb", response_model=IngestResponse)
async def add_text_to_ontology(
    request: TextIngestRequest,
    background_tasks: BackgroundTasks,
):
    if not app_state.ready:
        raise HTTPException(status_code=503, detail="System not ready")

    doc_id = request.metadata.get("doc_id") or _generate_doc_id("text")

    try:
        result = ingest_text_into_ontology(
            text=request.text,
            doc_id=doc_id,
            metadata=request.metadata,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    edge_count = int(result["edge_count"])
    chunks_created = int(result["chunks_created"])
    total_chunks = int(result["total_chunks"])
    destinations = {
        "domain": int(result["domain_relations"]),
        "personal": int(result["personal_relations"]),
        "council": int(result["council_relations"]),
    }
    council_case_ids = [str(case_id) for case_id in result["council_case_ids"]]
    payload: dict[str, Any] = {
        "status": "success",
        "message": "Text ingested into ontology graph",
        "edge_count": edge_count,
        "chunks_created": chunks_created,
        "total_chunks": total_chunks,
        "doc_id": doc_id,
        "destinations": destinations,
        "council_case_ids": council_case_ids,
    }

    if request.callback_url:
        try:
            callback_url = validate_callback_url(request.callback_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        queue_callback(background_tasks, callback_url, payload)

    _log_ingest_event(
        doc_id=doc_id,
        input_type="text",
        metadata=request.metadata,
        edge_count=edge_count,
        destinations=destinations,
        council_case_ids=council_case_ids,
        text_preview=request.text[:200],
        replay_text=request.text,
    )
    _sync_source_document_record(
        doc_id=doc_id,
        input_type="text",
        metadata=request.metadata,
        edge_count=edge_count,
        destinations=destinations,
        council_case_ids=council_case_ids,
        text_preview=request.text[:200],
        consolidated_relations=result.get("consolidated_relations", []),
    )

    return IngestResponse(
        status="success",
        message="Text ingested into ontology graph",
        edge_count=edge_count,
        chunks_created=chunks_created,
        total_chunks=total_chunks,
        doc_id=doc_id,
        destinations=destinations,
        council_case_ids=council_case_ids,
    )


@app.post("/api/news/ingest-evaluated", response_model=NewsBridgeResponse)
async def ingest_evaluated_news(request: NewsEvaluatePayload):
    if not app_state.ready:
        raise HTTPException(status_code=503, detail="System not ready")

    doc_id = build_news_doc_id(request)
    metadata = build_news_metadata(request, doc_id)
    ingest_text = build_news_ingest_text(request)

    try:
        result = ingest_text_into_ontology(text=ingest_text, doc_id=doc_id, metadata=metadata)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    council_case_ids = [str(case_id) for case_id in result["council_case_ids"]]
    if request.requires_manual_review or request.impact_count >= 3:
        extra_case_ids = _submit_news_review_candidate(request, doc_id)
        for case_id in extra_case_ids:
            if case_id not in council_case_ids:
                council_case_ids.append(case_id)

    destinations = _build_destination_counts(result)
    destinations["council"] = max(destinations.get("council", 0), len(council_case_ids))

    _log_ingest_event(
        doc_id=doc_id,
        input_type="news_eval",
        metadata=metadata,
        edge_count=int(result["edge_count"]),
        destinations=destinations,
        council_case_ids=council_case_ids,
        text_preview=request.summary,
        replay_text=ingest_text,
    )
    _sync_source_document_record(
        doc_id=doc_id,
        input_type="news_eval",
        metadata=metadata,
        edge_count=int(result["edge_count"]),
        destinations=destinations,
        council_case_ids=council_case_ids,
        text_preview=request.summary,
        consolidated_relations=result.get("consolidated_relations", []),
    )

    return NewsBridgeResponse(
        status="success",
        message="Evaluated news ingested into ontology graph",
        edge_count=int(result["edge_count"]),
        chunks_created=int(result["chunks_created"]),
        total_chunks=int(result["total_chunks"]),
        doc_id=doc_id,
        destinations=destinations,
        council_case_ids=council_case_ids,
        headline=request.headline,
        impact_count=request.impact_count,
        requires_manual_review=request.requires_manual_review,
    )


@app.post("/api/documents/ingest-structured", response_model=IngestResponse)
async def ingest_structured_document(
    request: StructuredDocumentIngestRequest,
    background_tasks: BackgroundTasks,
):
    if not app_state.ready:
        raise HTTPException(status_code=503, detail="System not ready")
    if not request.sections:
        raise HTTPException(
            status_code=400, detail="Structured document requires at least one section"
        )

    doc_id = request.metadata.get("doc_id") or _generate_doc_id("structured")
    metadata = dict(request.metadata)
    metadata.setdefault("title", request.title)
    metadata.setdefault("source_type", "structured_document")
    metadata.setdefault(
        "structured_sections",
        [
            {
                "chapter_title": section.chapter_title,
                "section_title": section.section_title,
                "page_number": section.page_number,
                "text_length": len(section.text),
            }
            for section in request.sections
        ],
    )
    ingest_text = _build_structured_document_text(request.sections)

    try:
        result = ingest_text_into_ontology(text=ingest_text, doc_id=doc_id, metadata=metadata)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    edge_count = int(result["edge_count"])
    chunks_created = int(result["chunks_created"])
    total_chunks = int(result["total_chunks"])
    destinations = {
        "domain": int(result["domain_relations"]),
        "personal": int(result["personal_relations"]),
        "council": int(result["council_relations"]),
    }
    council_case_ids = [str(case_id) for case_id in result["council_case_ids"]]
    payload = {
        "status": "success",
        "message": "Structured document ingested into ontology graph",
        "edge_count": edge_count,
        "chunks_created": chunks_created,
        "total_chunks": total_chunks,
        "doc_id": doc_id,
        "destinations": destinations,
        "council_case_ids": council_case_ids,
    }

    if request.callback_url:
        try:
            callback_url = validate_callback_url(request.callback_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        queue_callback(background_tasks, callback_url, payload)

    _log_ingest_event(
        doc_id=doc_id,
        input_type="structured_document",
        metadata=metadata,
        edge_count=edge_count,
        destinations=destinations,
        council_case_ids=council_case_ids,
        text_preview=ingest_text[:200],
        replay_text=ingest_text,
    )
    _sync_source_document_record(
        doc_id=doc_id,
        input_type="structured_document",
        metadata=metadata,
        edge_count=edge_count,
        destinations=destinations,
        council_case_ids=council_case_ids,
        text_preview=ingest_text[:200],
        consolidated_relations=result.get("consolidated_relations", []),
    )

    return IngestResponse(
        status="success",
        message="Structured document ingested into ontology graph",
        edge_count=edge_count,
        chunks_created=chunks_created,
        total_chunks=total_chunks,
        doc_id=doc_id,
        destinations=destinations,
        council_case_ids=council_case_ids,
    )


@app.post("/api/pdf/extract-and-embed", response_model=IngestResponse)
async def extract_and_embed_pdf(
    request: PDFIngestRequest,
    background_tasks: BackgroundTasks,
):
    if not app_state.ready:
        raise HTTPException(status_code=503, detail="System not ready")

    try:
        pdf_blocks = extract_pdf_blocks_from_base64(request.pdf_data)
        text = extract_pdf_text_from_base64(request.pdf_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    doc_id = request.metadata.get("doc_id") or request.filename or _generate_doc_id("pdf")
    meta = dict(request.metadata)
    meta.setdefault("source", "pdf_upload")
    if request.filename:
        meta.setdefault("filename", request.filename)
    meta.setdefault("document_format", "pdf")
    meta.setdefault("pdf_blocks", pdf_blocks)

    result = ingest_text_into_ontology(
        text=text,
        doc_id=doc_id,
        metadata=meta,
    )

    edge_count = int(result["edge_count"])
    chunks_created = int(result["chunks_created"])
    total_chunks = int(result["total_chunks"])
    destinations = {
        "domain": int(result["domain_relations"]),
        "personal": int(result["personal_relations"]),
        "council": int(result["council_relations"]),
    }
    council_case_ids = [str(case_id) for case_id in result["council_case_ids"]]
    payload: dict[str, Any] = {
        "status": "success",
        "message": "PDF ingested into ontology graph",
        "edge_count": edge_count,
        "chunks_created": chunks_created,
        "total_chunks": total_chunks,
        "doc_id": doc_id,
        "destinations": destinations,
        "council_case_ids": council_case_ids,
    }

    if request.callback_url:
        try:
            callback_url = validate_callback_url(request.callback_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        queue_callback(background_tasks, callback_url, payload)

    _log_ingest_event(
        doc_id=doc_id,
        input_type="pdf",
        metadata=meta,
        edge_count=edge_count,
        destinations=destinations,
        council_case_ids=council_case_ids,
        filename=request.filename,
        text_preview=text[:200] if text else None,
        replay_text=text,
    )
    _sync_source_document_record(
        doc_id=doc_id,
        input_type="pdf",
        metadata=meta,
        edge_count=edge_count,
        destinations=destinations,
        council_case_ids=council_case_ids,
        filename=request.filename,
        text_preview=text[:200] if text else None,
        consolidated_relations=result.get("consolidated_relations", []),
    )

    return IngestResponse(
        status="success",
        message="PDF ingested into ontology graph",
        edge_count=edge_count,
        chunks_created=chunks_created,
        total_chunks=total_chunks,
        doc_id=doc_id,
        destinations=destinations,
        council_case_ids=council_case_ids,
    )


@app.post("/api/pdf/notify-upload")
async def notify_pdf_upload(request: PDFNotifyRequest):
    logger.info(f"PDF upload notification received: {request.filename} from {request.source}")
    return {
        "status": "success",
        "message": "Notification received",
        "filename": request.filename,
        "file_path": request.file_path,
    }


@app.get("/healthz")
async def healthz():
    storage_health = app_state.get("storage_health", {"ok": False})
    council_worker = app_state.get("council_worker")
    if app_state.ready and storage_health.get("ok"):
        return {
            "status": "ok",
            "ready": True,
            "storage_ready": True,
            "council_worker_ready": bool(council_worker and council_worker.is_running),
        }
    return {
        "status": "initializing",
        "ready": False,
        "storage_ready": storage_health.get("ok", False),
        "council_worker_ready": bool(council_worker and council_worker.is_running),
    }


@app.get("/status")
async def status():
    domain = app_state.domain
    personal = app_state.personal
    council = app_state.council
    council_worker = app_state.council_worker
    event_store = app_state.learning_event_store
    repo = None
    storage_health = app_state.storage_health
    storage_backend = storage_health.get("backend", "unknown")
    entity_count = 0
    relation_count = 0
    tx_stats = {"total_committed": 0, "total_rolled_back": 0, "active_transactions": 0}

    try:
        repo = get_graph_repository()
        storage_backend = repo.__class__.__name__
        storage_health = check_graph_repository_health(repo)
        if storage_health.get("ok"):
            entity_count = repo.count_entities()
            relation_count = repo.count_relations()
            tx_stats = get_transaction_manager().get_stats()
    except Exception as exc:
        storage_health = {
            "ok": False,
            "backend": storage_backend,
            "error": str(exc),
        }

    app_state.storage_health = storage_health

    domain_relation_count = 0
    personal_relation_count = 0

    if domain:
        dyn = domain.get_dynamic_domain()
        domain_relation_count = len(dyn.get_all_relations())

    if personal:
        pkg = personal.get_pkg()
        personal_relation_count = len(pkg.get_all_relations())

    council_stats = council.get_stats() if council else {}
    edge_count = _metric_value("ingested_edge_count", "ingested_chunks")
    pdf_doc_count = _metric_value("ingested_pdf_doc_count", "ingested_pdf_docs")

    return {
        "status": "healthy"
        if app_state.ready and storage_health.get("ok")
        else ("degraded" if app_state.ready else "initializing"),
        "ready": app_state.ready,
        "version": "11.0.0",
        "metrics_schema_version": 2,
        "storage_backend": storage_health.get("backend", storage_backend),
        "storage_ok": storage_health.get("ok", False),
        "storage_error": storage_health.get("error"),
        "entity_count": entity_count,
        "relation_count": relation_count,
        "domain_relation_count": domain_relation_count,
        "personal_relation_count": personal_relation_count,
        "edge_count": edge_count,
        "pdf_doc_count": pdf_doc_count,
        "vector_count": edge_count,
        "llm_available": app_state.llm_client is not None,
        "reasoning_enabled": True,
        "action_enabled": True,
        "callback_delivery_enabled": get_settings().callbacks.enabled,
        "ingested_docs": app_state.ingested_docs,
        "pdf_docs": pdf_doc_count,
        "total_pdfs": pdf_doc_count,
        "total_chunks": edge_count,
        "deprecated_metric_aliases": {
            "vector_count": "edge_count",
            "total_chunks": "edge_count",
            "pdf_docs": "pdf_doc_count",
            "total_pdfs": "pdf_doc_count",
        },
        "council_pending": council_stats.get("pending_cases", 0),
        "council_closed": council_stats.get("closed_cases", 0),
        "configured_members": council_stats.get("configured_members", 0),
        "available_members": council_stats.get("available_members", 0),
        "council_worker_active": bool(council_worker and council_worker.is_running),
        "last_council_run": council_worker.last_run_at if council_worker else None,
        "council_last_error": council_worker.last_error if council_worker else None,
        "ai_runtime": app_state.ai_runtime,
        "tx_committed": tx_stats.get("total_committed", 0),
        "tx_rolled_back": tx_stats.get("total_rolled_back", 0),
        "tx_active": tx_stats.get("active_transactions", 0),
        "learning_event_backlog": event_store.counts() if event_store else {},
    }


@app.get("/api/dashboard/summary")
async def dashboard_summary():
    status_payload = await status()
    return build_dashboard_summary(status_payload, app_state.get("learning_event_store"))


@app.get("/api/system/ai-runtime")
async def get_ai_runtime():
    if not app_state.ai_runtime:
        return _refresh_ai_runtime_status()
    return app_state.ai_runtime


@app.post("/api/system/ai-runtime/check")
async def check_ai_runtime():
    return _refresh_ai_runtime_status()


@app.get("/api/ingests")
async def list_ingests(limit: int = 20):
    return build_ingest_listing(app_state.get("learning_event_store"), limit=limit)


@app.get("/api/ingests/{doc_id}")
async def get_ingest_detail(doc_id: str):
    detail = build_ingest_detail(app_state.get("learning_event_store"), doc_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Ingest record not found")
    return detail


@app.get("/api/documents")
async def list_documents(
    limit: int = 20,
    q: str | None = None,
    source_type: str | None = None,
    institution: str | None = None,
    region: str | None = None,
    asset_scope: str | None = None,
    document_quality_tier: str | None = None,
):
    return build_document_search(
        app_state.get("learning_event_store"),
        limit=limit,
        q=q,
        source_type=source_type,
        institution=institution,
        region=region,
        asset_scope=asset_scope,
        document_quality_tier=document_quality_tier,
    )


@app.get("/api/documents/{doc_id}")
async def get_document_detail(doc_id: str):
    detail = build_document_detail(app_state.get("learning_event_store"), doc_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Document record not found")
    return detail


@app.get("/api/documents/{doc_id}/graph")
async def get_document_graph(doc_id: str):
    graph = build_document_graph(
        get_graph_repository(), app_state.get("learning_event_store"), doc_id
    )
    if not graph["nodes"]:
        raise HTTPException(status_code=404, detail="Document graph not found")
    return graph


@app.get("/api/documents/{doc_id}/structure")
async def get_document_structure(doc_id: str):
    structure = build_document_structure(app_state.get("learning_event_store"), doc_id)
    if structure is None:
        raise HTTPException(status_code=404, detail="Document structure not found")
    return structure


@app.get("/api/trust/summary")
async def get_trust_summary():
    return build_trust_summary(app_state.get("learning_event_store"))


@app.get("/api/learning/products")
async def get_learning_products(limit: int = 20):
    return build_learning_products(app_state.get("learning_event_store"), limit=limit)


@app.get("/api/learning/products/{kind}/{file_name}")
async def get_learning_product_detail(kind: str, file_name: str):
    detail = build_learning_product_detail(app_state.get("learning_event_store"), kind, file_name)
    if detail is None:
        raise HTTPException(status_code=404, detail="Learning product not found")
    return detail


@app.get("/api/audit/logs")
async def get_audit_logs(limit: int = 20, action: str | None = None):
    return build_audit_listing(app_state.get("learning_event_store"), limit=limit, action=action)


@app.get("/api/audit/logs/{event_id}")
async def get_audit_log_detail(event_id: str):
    detail = build_audit_detail(app_state.get("learning_event_store"), event_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Audit event not found")
    return detail


@app.post("/api/learning/evaluations/run")
async def run_learning_evaluation(
    request: LearningEvaluationRunRequest,
):
    try:
        snapshot_path = (
            _snapshot_file_path(request.snapshot_filename)
            if request.snapshot_filename
            else export_dataset(TaskType(request.task_type), None)
        )
        if not snapshot_path.exists():
            raise FileNotFoundError(snapshot_path.name)
        goldset_path = _goldset_file_path(request.goldset_filename)
        if not goldset_path.exists():
            raise FileNotFoundError(goldset_path.name)
        evaluation_path = evaluate_dataset(str(snapshot_path), str(goldset_path))
        payload = load_json(evaluation_path)
        return {
            "snapshot_filename": snapshot_path.name,
            "goldset_filename": goldset_path.name,
            "evaluation_filename": evaluation_path.name,
            "metrics": payload.get("metrics", {}),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Learning artifact not found: {exc}") from exc


@app.post("/api/learning/bundles/promote")
async def promote_learning_bundle(
    request: LearningBundlePromoteRequest,
):
    try:
        payload = _promote_bundle_file(
            bundle_filename=request.bundle_filename,
            approved=request.approved,
            deploy=request.deploy,
            notes=request.notes,
            reviewer=request.reviewer,
        )
        return payload
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Bundle not found: {exc}") from exc


@app.post("/api/ingests/delete")
async def delete_ingests(request: DeleteIngestsRequest):
    try:
        return await delete_selected_ingests(request.doc_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        detail = str(exc)
        status_code = 409 if "cannot be replayed" in detail else 503
        raise HTTPException(status_code=status_code, detail=detail) from exc


@app.get("/api/entities")
async def list_entities(q: str | None = None, entity_type: str | None = None, limit: int = 20):
    return build_entity_listing(get_graph_repository(), q=q, entity_type=entity_type, limit=limit)


@app.get("/api/entities/{entity_id}")
async def get_entity_detail(entity_id: str):
    detail = build_entity_detail(get_graph_repository(), entity_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return detail


@app.get("/api/graph")
async def get_graph(root_entity_id: str, depth: int = 1, limit: int = 50):
    graph = build_graph_response(
        get_graph_repository(), root_entity_id=root_entity_id, depth=depth, limit=limit
    )
    if not graph["nodes"]:
        raise HTTPException(status_code=404, detail="Root entity not found")
    return graph


@app.get("/api/council/cases")
async def list_council_cases(status: str | None = None):
    council = app_state.council
    if not council:
        raise HTTPException(status_code=503, detail="Council service not ready")
    cases = council.list_cases(status=status)
    return {"cases": [case.model_dump(mode="json") for case in cases]}


@app.get("/api/council/cases/{case_id}")
async def get_council_case(case_id: str):
    council = app_state.council
    if not council:
        raise HTTPException(status_code=503, detail="Council service not ready")
    case = council.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Council case not found")
    case_payload = case.model_dump(mode="json")
    candidate_id = getattr(case, "candidate_id", case_payload.get("candidate_id"))
    candidate = council.get_candidate(candidate_id) if candidate_id else None
    return {
        "case": case_payload,
        "candidate": candidate.model_dump(mode="json") if candidate else None,
    }


@app.post("/api/council/cases/{case_id}/retry")
async def retry_council_case(case_id: str):
    council = app_state.council
    worker = app_state.council_worker
    if not council or not worker:
        raise HTTPException(status_code=503, detail="Council automation not ready")
    case = council.retry_case(case_id)
    result = await worker.process_pending_once(env=os.environ)
    return {"case": case.model_dump(mode="json"), "result": result}


@app.post("/api/council/cases/{case_id}/decision")
async def decide_council_case(case_id: str, request: CouncilDecisionRequest):
    council = app_state.council
    if not council:
        raise HTTPException(status_code=503, detail="Council service not ready")
    case = council.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Council case not found")

    try:
        decision = CouncilDecision(request.decision.upper())
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid decision: {request.decision}"
        ) from exc

    council.record_turn(
        case_id=case_id,
        role=CouncilRole.ADJUDICATOR,
        agent_id=request.agent_id,
        claim=request.rationale or decision.value,
        decision=decision,
        confidence=request.confidence,
        evidence="manual operator decision",
    )
    council.cast_vote(
        case_id=case_id,
        agent_id=request.agent_id,
        decision=decision,
        confidence=request.confidence,
        rationale=request.rationale or decision.value,
    )
    candidate = council.finalize_case(
        case_id=case_id,
        adjudicator_id=request.agent_id,
        apply_to_domain=request.apply_to_domain,
    )
    updated_case = council.get_case(case_id)
    return {
        "case": updated_case.model_dump(mode="json") if updated_case else None,
        "candidate": candidate.model_dump(mode="json"),
    }


@app.post("/api/council/process-pending")
async def process_pending_council_cases():
    worker = app_state.council_worker
    if not worker:
        raise HTTPException(status_code=503, detail="Council automation worker not ready")
    return await worker.process_pending_once(env=os.environ)


@app.post("/api/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    if not app_state.ready:
        raise HTTPException(status_code=503, detail="System not ready")

    reasoning = app_state.reasoning

    try:
        conclusion = reasoning.reason(request.question)

        # Fallback: If reasoning fails (low confidence or no path) and LLM is available, use LLM
        if (
            conclusion.confidence < 0.2 or "unknown" in conclusion.conclusion_text.lower()
        ) and app_state.llm_client:
            llm_client = app_state.llm_client
            try:
                from src.llm.llm_client import LLMRequest

                prompt = f"""당신은 금융 문서와 관계형 지식 그래프를 보조하는 AI 분석가입니다.

사용자의 질문: "{request.question}"

[답변 지침]
1. 금융 변수, 자산, 섹터, 정책, 거시지표 간 관계를 중심으로 답변하세요.
2. 인과가 불확실하면 단정하지 말고 조건부 표현을 사용하세요.
3. 추론 근거가 부족하면 금융적으로 보수적인 설명을 우선하세요.
4. 한국어로 간결하고 예의 바르게 답변하세요.

답변:"""
                response = llm_client.generate(LLMRequest(prompt=prompt))
                _log_query_event(request.question, error="graph_reasoning_low_confidence_fallback")
                return AskResponse(
                    answer=f"[AI 답변] {response.content}",
                    confidence=0.5,  # LLM fallback default confidence
                    sources=[
                        {
                            "entity_name": "LLM Knowledge",
                            "text": "Reasoning failed, used LLM fallback",
                        }
                    ],
                    reasoning_used=False,
                    reasoning_trace=["Graph reasoning confidence too low, fell back to LLM"],
                    action_suggested=None,
                    metrics=reasoning.get_stats(),
                    timestamp=datetime.now().isoformat(),
                )
            except Exception as llm_e:
                logger.error(f"LLM fallback failed: {llm_e}")
                # If LLM also fails, return the original low confidence reasoning result

        sources = []
        if conclusion.evidence_summary:
            sources.append(
                {
                    "entity_name": "Evidence",
                    "text": conclusion.evidence_summary,
                    "confidence": conclusion.confidence,
                }
            )

        trace = []
        if conclusion.strongest_path_description:
            trace.append(f"Strongest Path: {conclusion.strongest_path_description}")

        _log_query_event(request.question, conclusion=conclusion)
        return AskResponse(
            answer=conclusion.conclusion_text,
            confidence=conclusion.confidence,
            sources=sources,
            reasoning_used=True,
            reasoning_trace=trace,
            action_suggested=None,
            metrics=reasoning.get_stats(),
            timestamp=datetime.now().isoformat(),
        )
    except Exception as e:
        logger.error(f"Error processing query: {e}")

        # Last Resort Fallback: Direct LLM call if reasoning crashes
        if app_state.llm_client:
            try:
                llm_client = app_state.llm_client
                from src.llm.llm_client import LLMRequest

                prompt = f"""금융 온톨로지 보조 분석가로서 다음 질문에 답변해주세요.
질문: {request.question}

시스템 오류로 인해 온톨로지 추론을 수행할 수 없어 직접 질의합니다.
금융 관계와 해석 범위를 벗어나면 모른다고 답하고 과도한 추정을 하지 마세요.
답변:"""
                response = llm_client.generate(LLMRequest(prompt=prompt))
                _log_query_event(request.question, error=f"reasoning_error:{str(e)}")
                return AskResponse(
                    answer=f"[AI 답변 (시스템 오류)] {response.content}",
                    confidence=0.1,
                    sources=[],
                    reasoning_used=False,
                    reasoning_trace=[f"System error: {str(e)}", "Fallback to LLM"],
                    metrics={},
                    timestamp=datetime.now().isoformat(),
                )
            except Exception as llm_e:
                logger.error(f"Last resort LLM fallback failed: {llm_e}")

        _log_query_event(request.question, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/qa/batch", response_model=BatchResponse)
async def batch_ask(request: BatchRequest):
    results = []
    reasoning = app_state.reasoning

    for item in request.items:
        q = item.get("question")
        if not q:
            results.append({"error": "No question provided"})
            continue

        try:
            conclusion = reasoning.reason(q)
            results.append(
                {
                    "question": q,
                    "answer": conclusion.conclusion_text,
                    "confidence": conclusion.confidence,
                    "sources": [{"text": conclusion.evidence_summary}],
                }
            )
        except Exception as e:
            results.append({"question": q, "error": str(e)})

    return BatchResponse(results=results)


@app.get("/metrics")
async def metrics():
    storage_health = app_state.storage_health
    lines = [
        "# HELP ontro_ready App readiness state",
        "# TYPE ontro_ready gauge",
        f"ontro_ready {1 if app_state.ready else 0}",
        "# HELP ontro_ingested_documents_total Total ingested documents",
        "# TYPE ontro_ingested_documents_total counter",
        f"ontro_ingested_documents_total {app_state.ingested_docs}",
        "# HELP ontro_ingested_edges_total Total extracted edges",
        "# TYPE ontro_ingested_edges_total counter",
        f"ontro_ingested_edges_total {app_state.ingested_edge_count}",
        "# HELP ontro_ingested_pdf_documents_total Total ingested pdf documents",
        "# TYPE ontro_ingested_pdf_documents_total counter",
        f"ontro_ingested_pdf_documents_total {app_state.ingested_pdf_doc_count}",
        "# HELP ontro_storage_ok Storage health status",
        "# TYPE ontro_storage_ok gauge",
        f"ontro_storage_ok {1 if storage_health.get('ok') else 0}",
        "# HELP ontro_audit_events_total Total audit events",
        "# TYPE ontro_audit_events_total counter",
        f"ontro_audit_events_total {app_state.learning_event_store.audit_count() if app_state.learning_event_store else 0}",
    ]
    for path, count in sorted(app_state.request_totals.items()):
        sanitized = path.strip("/").replace("/", "_").replace("-", "_") or "root"
        lines.append(f'ontro_requests_total{{path="{path}",path_key="{sanitized}"}} {count}')
    for path, count in sorted(app_state.request_errors.items()):
        sanitized = path.strip("/").replace("/", "_").replace("-", "_") or "root"
        lines.append(f'ontro_request_errors_total{{path="{path}",path_key="{sanitized}"}} {count}')
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


_RESERVED_NON_CONSOLE_PREFIXES = (
    "api/",
    "docs",
    "redoc",
    "openapi.json",
    "healthz",
    "status",
    "metrics",
)


def _serve_console_path(request_path: str) -> FileResponse:
    resolved_path = resolve_console_asset_path(request_path, get_settings().project_root)
    if resolved_path is None:
        raise HTTPException(status_code=404, detail="Operations console bundle not found")
    return FileResponse(resolved_path)


@app.get("/", include_in_schema=False)
async def serve_console_root():
    return _serve_console_path("")


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_console(full_path: str):
    normalized_path = full_path.strip("/")
    if any(
        normalized_path == prefix or normalized_path.startswith(prefix)
        for prefix in _RESERVED_NON_CONSOLE_PREFIXES
    ):
        raise HTTPException(status_code=404, detail="Not found")

    try:
        return _serve_console_path(normalized_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
