import logging
import asyncio
import base64
from io import BytesIO
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager
from pathlib import Path
import json
from datetime import datetime

import httpx
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from src.extraction import ExtractionPipeline
from src.validation import ValidationPipeline
from src.validation.models import ValidationDestination
from src.domain import DomainPipeline
from src.personal import PersonalPipeline
from src.reasoning import ReasoningPipeline
from src.bootstrap import build_llm_client
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
    "reasoning": None,
    "ready": False,
    "ingested_docs": 0,
    "ingested_chunks": 0
}

def load_sample_data():
    try:
        sample_path = Path(__file__).parent / "data" / "samples" / "sample_documents.json"
        if not sample_path.exists():
            logger.warning("Sample data not found. Skipping initial load.")
            return

        with open(sample_path, "r", encoding="utf-8") as f:
            documents = json.load(f)
        
        logger.info(f"Loading {len(documents)} sample documents...")
        
        extraction = app_state["extraction"]
        validation = app_state["validation"]
        domain = app_state["domain"]
        personal = app_state["personal"]

        for doc in documents:
            doc_id = doc.get("doc_id")
            text = doc.get("text", "")
            
            # PDF Processing Support
            if text.lower().endswith('.pdf'):
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
            
            # Extraction
            ext = extraction.process(raw_text=text, doc_id=doc_id)
            if not ext.raw_edges:
                continue
            
            # Validation
            vals = validation.validate_batch(
                edges=ext.raw_edges,
                resolved_entities=ext.resolved_entities,
            )
            val_map = {v.edge_id: v for v in vals}
            
            # Domain & Personal
            for edge in ext.raw_edges:
                v = val_map.get(edge.raw_edge_id)
                if not v or not v.validation_passed:
                    continue
                
                if v.destination == ValidationDestination.DOMAIN_CANDIDATE:
                    dom_result = domain.process(edge, v, ext.resolved_entities)
                    if dom_result.final_destination != "domain":
                        if dom_result.intake_result:
                            personal.process_from_domain_rejection(
                                dom_result.intake_result, dom_result
                            )
                elif v.destination == ValidationDestination.PERSONAL_CANDIDATE:
                    personal.process_from_validation(edge, v, ext.resolved_entities)

        logger.info("Sample data loaded.")
        
    except Exception as e:
        logger.error(f"Error loading sample data: {e}")


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
    app_state["ingested_docs"] += 1
    app_state["ingested_chunks"] += len(ext.raw_edges)

    if not ext.raw_edges:
        return {
            "doc_id": doc_id,
            "chunks_created": 0,
            "total_chunks": 0,
            "domain_relations": 0,
            "personal_relations": 0,
        }

    vals = validation.validate_batch(
        edges=ext.raw_edges,
        resolved_entities=ext.resolved_entities,
    )
    val_map = {v.edge_id: v for v in vals}

    domain_results = []
    personal_results = []

    for edge in ext.raw_edges:
        v = val_map.get(edge.raw_edge_id)
        if not v or not v.validation_passed:
            continue

        if v.destination == ValidationDestination.DOMAIN_CANDIDATE:
            dom_result = domain.process(edge, v, ext.resolved_entities)
            domain_results.append(dom_result)

            if dom_result.final_destination != "domain" and dom_result.intake_result:
                personal_result = personal.process_from_domain_rejection(
                    dom_result.intake_result, dom_result
                )
                if personal_result:
                    personal_results.append(personal_result)
        elif v.destination == ValidationDestination.PERSONAL_CANDIDATE:
            personal_result = personal.process_from_validation(edge, v, ext.resolved_entities)
            if personal_result:
                personal_results.append(personal_result)

    return {
        "doc_id": doc_id,
        "chunks_created": len(ext.raw_edges),
        "total_chunks": len(ext.raw_edges),
        "domain_relations": len(domain_results),
        "personal_relations": len(personal_results),
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
    settings = get_settings()
    
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
    
    # Load sample data
    load_sample_data()

    app_state["ready"] = True
    logger.info("Ontology System v11 initialized successfully.")
    
    yield
    
    # Shutdown
    if app_state["llm_client"]:
        if hasattr(app_state["llm_client"], 'close'):
            app_state["llm_client"].close()
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
    chunks_created: int = 0
    total_chunks: int = 0
    doc_id: Optional[str] = None
    destinations: Dict[str, int] = Field(default_factory=dict)


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
        "chunks_created": result["chunks_created"],
        "total_chunks": result["total_chunks"],
        "doc_id": doc_id,
        "destinations": {
            "domain": result["domain_relations"],
            "personal": result["personal_relations"],
        },
    }

    if request.callback_url:
        queue_callback(background_tasks, request.callback_url, payload)

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

    result = ingest_text_into_ontology(
        text=text,
        doc_id=doc_id,
        metadata=meta,
    )

    payload = {
        "status": "success",
        "message": "PDF ingested into ontology graph",
        "chunks_created": result["chunks_created"],
        "total_chunks": result["total_chunks"],
        "doc_id": doc_id,
        "destinations": {
            "domain": result["domain_relations"],
            "personal": result["personal_relations"],
        },
    }

    if request.callback_url:
        queue_callback(background_tasks, request.callback_url, payload)

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
    if app_state["ready"]:
        return {"status": "ok", "ready": True}
    return {"status": "initializing", "ready": False}

@app.get("/status")
async def status():
    domain = app_state["domain"]
    personal = app_state["personal"]
    
    relation_count = 0
    
    if domain:
        dyn = domain.get_dynamic_domain()
        relation_count += len(dyn.get_all_relations())
        
    if personal:
        pkg = personal.get_pkg()
        relation_count += len(pkg.get_all_relations())

    return {
        "status": "healthy" if app_state["ready"] else "initializing",
        "ready": app_state["ready"],
        "version": "11.0.0",
        "entity_count": 0,
        "relation_count": relation_count,
        "vector_count": app_state.get("ingested_chunks", 0),
        "llm_available": app_state["llm_client"] is not None,
        "reasoning_enabled": True,
        "action_enabled": True,
        "total_pdfs": app_state.get("ingested_docs", 0),
        "total_chunks": app_state.get("ingested_chunks", 0)
    }

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
                prompt = f"""당신은 세종시 교통/날씨 정보를 안내하는 AI 비서입니다.

사용자의 질문: "{request.question}"

[답변 지침]
1. 교통, 날씨, 도로 상황, 세종시 관련 질문이라면: 도메인 전문가로서 구체적이고 도움이 되는 정보를 제공하세요.
2. 단순 인사, 일상 대화, 혹은 도메인과 무관한 일반 질문이라면: 친절하고 자연스럽게 대화에 응답하세요. 굳이 교통 정보를 언급할 필요는 없습니다.
3. 한국어로 간결하고 예의 바르게 답변하세요.

답변:"""
                response = llm_client.generate(LLMRequest(prompt=prompt))
                
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
                prompt = f"""교통/날씨 도메인 전문가로서 다음 질문에 답변해주세요.
질문: {request.question}

시스템 오류로 인해 온톨로지 추론을 수행할 수 없어 당신에게 직접 묻습니다.
답변:"""
                response = llm_client.generate(LLMRequest(prompt=prompt))
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
