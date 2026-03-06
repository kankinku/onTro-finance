import logging
import asyncio
import base64
import ipaddress
import os
import socket
from io import BytesIO
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager
from pathlib import Path
import json
from datetime import datetime
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from src.extraction import ExtractionPipeline
from src.validation import ValidationPipeline
from src.validation.models import ValidationDestination
from src.domain import DomainPipeline
from src.personal import PersonalPipeline
from src.reasoning import ReasoningPipeline
from src.bootstrap import (
    build_llm_client,
    check_graph_repository_health,
    get_council_service,
    get_graph_repository,
    get_transaction_manager,
)
from src.council.worker import CouncilAutomationWorker
from src.learning.event_store import LearningEventStore
from config.settings import get_settings

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global state
app_state = {
    "llm_client": None,
    "extraction": None,
    "validation": None,
    "domain": None,
    "personal": None,
    "council": None,
    "reasoning": None,
    "council_worker": None,
    "learning_event_store": None,
    "ready": False,
    "storage_health": {"ok": False, "backend": "unknown"},
    "ingested_docs": 0,
    "ingested_edge_count": 0,
    "ingested_pdf_doc_count": 0,
    "ingested_chunks": 0,
    "ingested_pdf_docs": 0,
}

def reset_app_state() -> None:
    app_state.update(
        {
            "llm_client": None,
            "extraction": None,
            "validation": None,
            "domain": None,
            "personal": None,
            "council": None,
            "reasoning": None,
            "council_worker": None,
            "learning_event_store": None,
            "ready": False,
            "storage_health": {"ok": False, "backend": "unknown"},
            "ingested_docs": 0,
            "ingested_edge_count": 0,
            "ingested_pdf_doc_count": 0,
            "ingested_chunks": 0,
            "ingested_pdf_docs": 0,
        }
    )


def _metric_value(primary_key: str, legacy_key: Optional[str] = None) -> int:
    value = app_state.get(primary_key)
    if value is None and legacy_key:
        value = app_state.get(legacy_key)
    return int(value or 0)


def _increment_ingest_counters(*, docs: int = 0, edges: int = 0, pdf_docs: int = 0) -> None:
    app_state["ingested_docs"] = _metric_value("ingested_docs") + docs
    app_state["ingested_edge_count"] = _metric_value("ingested_edge_count", "ingested_chunks") + edges
    app_state["ingested_pdf_doc_count"] = _metric_value("ingested_pdf_doc_count", "ingested_pdf_docs") + pdf_docs
    # Deprecated aliases kept for one release while callers migrate to the clearer keys.
    app_state["ingested_chunks"] = app_state["ingested_edge_count"]
    app_state["ingested_pdf_docs"] = app_state["ingested_pdf_doc_count"]


def load_sample_data() -> Dict[str, int]:
    loaded_docs = 0
    loaded_chunks = 0
    try:
        sample_path = Path(__file__).parent / "data" / "samples" / "sample_documents.json"
        if not sample_path.exists():
            logger.warning("Sample data not found. Skipping initial load.")
            return {"docs_loaded": 0, "chunks_loaded": 0}

        with open(sample_path, "r", encoding="utf-8") as f:
            documents = json.load(f)
        
        logger.info(f"Loading {len(documents)} sample documents...")

        for doc in documents:
            doc_id = doc.get("doc_id")
            text = doc.get("text", "")
            metadata = dict(doc.get("metadata", {}))
            metadata.setdefault("source", "sample_seed")
            
            # PDF Processing Support
            if text.lower().endswith('.pdf'):
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


def _normalized_allowed_hosts() -> List[str]:
    settings = get_settings()
    return [host.strip().lower().rstrip(".") for host in settings.callbacks.allowed_hosts if host.strip()]


def _resolved_host_ips(hostname: str) -> List[str]:
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"Callback host could not be resolved: {hostname}") from exc

    ips = sorted({info[4][0] for info in infos if info[4]})
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

    host_allowed = any(hostname == allowed or hostname.endswith(f".{allowed}") for allowed in allowed_hosts)
    if not host_allowed:
        raise ValueError(f"Callback host '{hostname}' is not allowlisted")

    try:
        resolved_ips = [str(ipaddress.ip_address(hostname))]
    except ValueError:
        resolved_ips = _resolved_host_ips(hostname)

    if any(_is_forbidden_callback_ip(ip) for ip in resolved_ips):
        raise ValueError("Callback host resolves to a private or loopback address")

    return callback_url


def extract_pdf_text_from_base64(pdf_base64: str) -> str:
    try:
        import pypdf
        pdf_bytes = base64.b64decode(pdf_base64)
        reader = pypdf.PdfReader(BytesIO(pdf_bytes))
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        text = "\n".join(parts).strip()
        if not text:
            raise ValueError("No text content extracted from PDF")
        return text
    except Exception as e:
        raise ValueError(f"Failed to parse PDF: {e}")


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
            "head_entity_id": edge.head_entity_id,
            "tail_entity_id": edge.tail_entity_id,
            "relation_type": edge.relation_type,
            "polarity_guess": edge.polarity_guess,
            "validation_passed": validation_result.validation_passed,
            "destination": validation_result.destination.value,
            "combined_conf": validation_result.combined_conf,
            "semantic_tag": validation_result.semantic_result.semantic_tag if validation_result.semantic_result else None,
            "rejection_reason": validation_result.rejection_reason,
        },
    )


def _log_query_event(question: str, conclusion=None, error: Optional[str] = None) -> None:
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


def ingest_text_into_ontology(
    text: str,
    doc_id: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not text or not text.strip():
        raise ValueError("No text provided for ingestion")

    extraction = app_state["extraction"]
    validation = app_state["validation"]
    domain = app_state["domain"]
    personal = app_state["personal"]

    if not all([extraction, validation, domain, personal]):
        raise RuntimeError("Ontology pipelines are not ready")

    metadata = metadata or {}
    logger.info(f"Ingesting document {doc_id} (source={metadata.get('source', 'external')})")

    ext = extraction.process(raw_text=text, doc_id=doc_id)
    edge_count = len(ext.raw_edges)
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
    council_case_ids: List[str] = []

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
        "domain_relations": len([result for result in domain_results if result.final_destination == "domain"]),
        "personal_relations": len(personal_results),
        "council_relations": len(council_case_ids),
        "council_case_ids": council_case_ids,
    }


def queue_callback(background_tasks: BackgroundTasks, callback_url: str, payload: Dict[str, Any]):
    def _dispatch():
        try:
            httpx.post(callback_url, json=payload, timeout=10)
        except Exception as e:
            logger.warning(f"Callback to {callback_url} failed: {e}")

    background_tasks.add_task(_dispatch)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing Ontology System v11...")
    reset_app_state()
    settings = get_settings()
    repo = get_graph_repository()
    storage_health = check_graph_repository_health(repo)
    if not storage_health["ok"]:
        raise RuntimeError(f"Storage backend unavailable: {storage_health}")
    app_state["storage_health"] = storage_health
    event_store = LearningEventStore(settings.store.learning_data_path)
    
    # Initialize LLM
    llm_client = build_llm_client()
    use_llm = False
    try:
        if llm_client:
            use_llm = llm_client.health_check()
    except Exception as e:
        logger.error(f"LLM health check failed: {e}")

    if use_llm:
        logger.info(f"[OK] Ollama connected: {settings.ollama.model_name}")
    else:
        logger.warning("[FAIL] Ollama not available, using rule-based mode")
        llm_client = None

    app_state["llm_client"] = llm_client

    # Initialize Pipelines
    extraction = ExtractionPipeline(llm_client=llm_client, use_llm=use_llm)
    validation = ValidationPipeline(llm_client=llm_client, use_llm=use_llm)
    domain = DomainPipeline()
    personal = PersonalPipeline(
        user_id="default_user",
        static_guard=domain.static_guard,
        dynamic_domain=domain.dynamic_update,
    )
    reasoning = ReasoningPipeline(
        domain=domain.dynamic_update,
        personal=personal.get_pkg(),
        llm_client=llm_client,
        ner=extraction.ner_student,
        resolver=extraction.entity_resolver,
    )

    app_state["extraction"] = extraction
    app_state["validation"] = validation
    app_state["domain"] = domain
    app_state["personal"] = personal
    app_state["reasoning"] = reasoning
    app_state["council"] = get_council_service()
    app_state["learning_event_store"] = event_store
    app_state["council"].event_store = event_store

    try:
        app_state["council"].refresh_member_availability(env=os.environ)
    except Exception as exc:
        logger.warning(f"Council member availability refresh failed: {exc}")

    council_worker = CouncilAutomationWorker(
        service=app_state["council"],
        poll_interval_seconds=settings.council_runtime.poll_interval_seconds,
    )
    app_state["council_worker"] = council_worker
    if settings.council_runtime.auto_process_enabled:
        await council_worker.start()

    if settings.runtime.load_sample_data_on_startup:
        load_sample_data()
    else:
        logger.info("Startup sample ingestion disabled. Set ONTRO_LOAD_SAMPLE_DATA=true to enable it.")

    app_state["ready"] = True
    logger.info("Ontology System v11 initialized successfully.")
    
    yield
    
    # Shutdown
    if app_state.get("council_worker"):
        await app_state["council_worker"].stop()
    if app_state["llm_client"]:
        if hasattr(app_state["llm_client"], 'close'):
            app_state["llm_client"].close()
    reset_app_state()
    logger.info("Ontology System v11 shutdown.")

app = FastAPI(title="Ontology System v11", lifespan=lifespan)

# Models
class TextIngestRequest(BaseModel):
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    callback_url: Optional[str] = None


class PDFIngestRequest(BaseModel):
    pdf_data: str
    filename: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    callback_url: Optional[str] = None


class PDFNotifyRequest(BaseModel):
    filename: str
    file_path: Optional[str] = None
    timestamp: Optional[str] = None
    source: Optional[str] = None


class IngestResponse(BaseModel):
    status: str
    message: str
    edge_count: int = 0
    chunks_created: int = 0
    total_chunks: int = 0
    doc_id: Optional[str] = None
    destinations: Dict[str, int] = Field(default_factory=dict)
    council_case_ids: List[str] = Field(default_factory=list)


class AskRequest(BaseModel):
    question: str
    mode: str = "accuracy"
    k: str = "auto"

class AskResponse(BaseModel):
    answer: str
    confidence: float
    sources: List[Dict[str, Any]] = []
    reasoning_used: bool = False
    reasoning_trace: List[str] = []
    action_suggested: Optional[str] = None
    metrics: Dict[str, Any] = {}
    timestamp: str

class BatchRequest(BaseModel):
    items: List[Dict[str, Any]]
    mode: str = "accuracy"

class BatchResponse(BaseModel):
    results: List[Dict[str, Any]]
    config_hash: str = "default"

@app.post("/api/text/add-to-vectordb", response_model=IngestResponse)
async def add_text_to_ontology(request: TextIngestRequest, background_tasks: BackgroundTasks):
    if not app_state["ready"]:
        raise HTTPException(status_code=503, detail="System not ready")

    doc_id = request.metadata.get("doc_id") or f"text_{int(datetime.now().timestamp())}"

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

    payload = {
        "status": "success",
        "message": "Text ingested into ontology graph",
        "edge_count": result["edge_count"],
        "chunks_created": result["chunks_created"],
        "total_chunks": result["total_chunks"],
        "doc_id": doc_id,
        "destinations": {
            "domain": result["domain_relations"],
            "personal": result["personal_relations"],
            "council": result["council_relations"],
        },
        "council_case_ids": result["council_case_ids"],
    }

    if request.callback_url:
        try:
            callback_url = validate_callback_url(request.callback_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        queue_callback(background_tasks, callback_url, payload)

    return IngestResponse(**payload)


@app.post("/api/pdf/extract-and-embed", response_model=IngestResponse)
async def extract_and_embed_pdf(request: PDFIngestRequest, background_tasks: BackgroundTasks):
    if not app_state["ready"]:
        raise HTTPException(status_code=503, detail="System not ready")

    try:
        text = extract_pdf_text_from_base64(request.pdf_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    doc_id = request.metadata.get("doc_id") or request.filename or f"pdf_{int(datetime.now().timestamp())}"
    meta = dict(request.metadata)
    meta.setdefault("source", "pdf_upload")
    if request.filename:
        meta.setdefault("filename", request.filename)
    meta.setdefault("document_format", "pdf")

    result = ingest_text_into_ontology(
        text=text,
        doc_id=doc_id,
        metadata=meta,
    )

    payload = {
        "status": "success",
        "message": "PDF ingested into ontology graph",
        "edge_count": result["edge_count"],
        "chunks_created": result["chunks_created"],
        "total_chunks": result["total_chunks"],
        "doc_id": doc_id,
        "destinations": {
            "domain": result["domain_relations"],
            "personal": result["personal_relations"],
            "council": result["council_relations"],
        },
        "council_case_ids": result["council_case_ids"],
    }

    if request.callback_url:
        try:
            callback_url = validate_callback_url(request.callback_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        queue_callback(background_tasks, callback_url, payload)

    return IngestResponse(**payload)


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
    if app_state["ready"] and storage_health.get("ok"):
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
    domain = app_state["domain"]
    personal = app_state["personal"]
    council = app_state["council"]
    council_worker = app_state.get("council_worker")
    event_store = app_state.get("learning_event_store")
    repo = get_graph_repository()
    tx_stats = get_transaction_manager().get_stats()
    storage_health = check_graph_repository_health(repo)
    app_state["storage_health"] = storage_health

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
        "status": "healthy" if app_state["ready"] else "initializing",
        "ready": app_state["ready"],
        "version": "11.0.0",
        "metrics_schema_version": 2,
        "storage_backend": repo.__class__.__name__,
        "storage_ok": storage_health.get("ok", False),
        "storage_error": storage_health.get("error"),
        "entity_count": repo.count_entities(),
        "relation_count": repo.count_relations(),
        "domain_relation_count": domain_relation_count,
        "personal_relation_count": personal_relation_count,
        "edge_count": edge_count,
        "pdf_doc_count": pdf_doc_count,
        "vector_count": edge_count,
        "llm_available": app_state["llm_client"] is not None,
        "reasoning_enabled": True,
        "action_enabled": True,
        "callback_delivery_enabled": get_settings().callbacks.enabled,
        "ingested_docs": app_state.get("ingested_docs", 0),
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
        "tx_committed": tx_stats.get("total_committed", 0),
        "tx_rolled_back": tx_stats.get("total_rolled_back", 0),
        "tx_active": tx_stats.get("active_transactions", 0),
        "learning_event_backlog": event_store.counts() if event_store else {},
    }


@app.get("/api/council/cases")
async def list_council_cases(status: Optional[str] = None):
    council = app_state["council"]
    if not council:
        raise HTTPException(status_code=503, detail="Council service not ready")
    cases = council.list_cases(status=status)
    return {"cases": [case.model_dump(mode="json") for case in cases]}


@app.get("/api/council/cases/{case_id}")
async def get_council_case(case_id: str):
    council = app_state["council"]
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
    council = app_state["council"]
    worker = app_state.get("council_worker")
    if not council or not worker:
        raise HTTPException(status_code=503, detail="Council automation not ready")
    case = council.retry_case(case_id)
    result = await worker.process_pending_once(env=os.environ)
    return {"case": case.model_dump(mode="json"), "result": result}


@app.post("/api/council/process-pending")
async def process_pending_council_cases():
    worker = app_state.get("council_worker")
    if not worker:
        raise HTTPException(status_code=503, detail="Council automation worker not ready")
    return await worker.process_pending_once(env=os.environ)

@app.post("/api/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    if not app_state["ready"]:
        raise HTTPException(status_code=503, detail="System not ready")
        
    reasoning = app_state["reasoning"]
    
    try:
        conclusion = reasoning.reason(request.question)
        
        # Fallback: If reasoning fails (low confidence or no path) and LLM is available, use LLM
        if (conclusion.confidence < 0.2 or "unknown" in conclusion.conclusion_text.lower()) and app_state["llm_client"]:
            llm_client = app_state["llm_client"]
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
                    confidence=0.5, # LLM fallback default confidence
                    sources=[{"entity_name": "LLM Knowledge", "text": "Reasoning failed, used LLM fallback"}],
                    reasoning_used=False,
                    reasoning_trace=["Graph reasoning confidence too low, fell back to LLM"],
                    action_suggested=None,
                    metrics=reasoning.get_stats(),
                    timestamp=datetime.now().isoformat()
                )
            except Exception as llm_e:
                logger.error(f"LLM fallback failed: {llm_e}")
                # If LLM also fails, return the original low confidence reasoning result
        
        sources = []
        if conclusion.evidence_summary:
             sources.append({
                 "entity_name": "Evidence", 
                 "text": conclusion.evidence_summary, 
                 "confidence": conclusion.confidence
             })
        
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
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        
        # Last Resort Fallback: Direct LLM call if reasoning crashes
        if app_state["llm_client"]:
            try:
                llm_client = app_state["llm_client"]
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
                    timestamp=datetime.now().isoformat()
                )
            except Exception as llm_e:
                logger.error(f"Last resort LLM fallback failed: {llm_e}")
        
        _log_query_event(request.question, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/qa/batch", response_model=BatchResponse)
async def batch_ask(request: BatchRequest):
    results = []
    reasoning = app_state["reasoning"]
    
    for item in request.items:
        q = item.get("question")
        if not q: 
            results.append({"error": "No question provided"})
            continue
            
        try:
            conclusion = reasoning.reason(q)
            results.append({
                "question": q,
                "answer": conclusion.conclusion_text,
                "confidence": conclusion.confidence,
                "sources": [{"text": conclusion.evidence_summary}]
            })
        except Exception as e:
            results.append({"question": q, "error": str(e)})
            
    return BatchResponse(results=results)

@app.get("/metrics")
async def metrics():
    reasoning = app_state["reasoning"]
    if reasoning:
        return {"metrics": str(reasoning.get_stats())}
    return {"metrics": ""}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
