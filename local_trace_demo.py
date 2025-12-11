"""
Local trace demo for the ontology chatbot pipeline.

Runs the full 5-sector pipeline on sample data, then asks a few questions
and prints the retrieval/weighting/reasoning traces used to answer.
"""
import argparse
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config.settings import get_settings
from src.bootstrap import build_llm_client
from src.domain import DomainPipeline
from src.extraction import ExtractionPipeline
from src.personal import PersonalPipeline
from src.reasoning import ReasoningPipeline
from src.validation import ValidationPipeline
from src.validation.models import ValidationDestination


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("local_trace_demo")


def load_documents(limit: Optional[int] = None) -> List[Dict]:
    """Load sample documents for ingestion."""
    sample_path = Path(__file__).parent / "data" / "samples" / "sample_documents.json"

    if sample_path.exists():
        with open(sample_path, "r", encoding="utf-8") as f:
            docs = json.load(f)
    else:
        # Minimal fallback if the sample file is missing
        docs = [
            {
                "doc_id": "FALLBACK_001",
                "text": "세종 BRT는 출퇴근 시간대 교통 혼잡을 줄인다.",
                "source": "fallback",
            },
            {
                "doc_id": "FALLBACK_002",
                "text": "폭우가 오면 버스 배차가 지연되고 도로가 미끄러워진다.",
                "source": "fallback",
            },
        ]

    return docs[:limit] if limit else docs


def bootstrap_pipelines() -> Tuple[Dict[str, object], bool]:
    """Create all pipelines and return whether LLM mode is active."""
    settings = get_settings()

    llm_client = build_llm_client()
    use_llm = False
    if llm_client:
        try:
            use_llm = llm_client.health_check()
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM health check failed: %s", exc)
            llm_client = None

    if use_llm:
        logger.info("[OK] Ollama connected: %s", settings.ollama.model_name)
    else:
        logger.info("[Rule-based] Ollama not available, proceeding without LLM")

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

    return (
        {
            "llm": llm_client,
            "extraction": extraction,
            "validation": validation,
            "domain": domain,
            "personal": personal,
            "reasoning": reasoning,
        },
        use_llm,
    )


def ingest_documents(docs: List[Dict], pipelines: Dict[str, object]) -> Dict[str, int]:
    """Run Extraction -> Validation -> Domain/Personal ingestion."""
    extraction: ExtractionPipeline = pipelines["extraction"]  # type: ignore[assignment]
    validation: ValidationPipeline = pipelines["validation"]  # type: ignore[assignment]
    domain: DomainPipeline = pipelines["domain"]  # type: ignore[assignment]
    personal: PersonalPipeline = pipelines["personal"]  # type: ignore[assignment]

    stats = {"docs": 0, "raw_edges": 0, "domain_relations": 0, "personal_relations": 0}

    for doc in docs:
        doc_id = doc.get("doc_id") or f"doc_{stats['docs'] + 1}"
        text = doc.get("text", "")
        if not text.strip():
            continue

        ext = extraction.process(raw_text=text, doc_id=doc_id)
        stats["docs"] += 1
        stats["raw_edges"] += len(ext.raw_edges)

        if not ext.raw_edges:
            continue

        vals = validation.validate_batch(
            edges=ext.raw_edges,
            resolved_entities=ext.resolved_entities,
        )
        val_map = {v.edge_id: v for v in vals}

        for edge in ext.raw_edges:
            v = val_map.get(edge.raw_edge_id)
            if not v or not v.validation_passed:
                continue

            if v.destination == ValidationDestination.DOMAIN_CANDIDATE:
                dom_result = domain.process(edge, v, ext.resolved_entities)
                if dom_result.final_destination != "domain" and dom_result.intake_result:
                    personal.process_from_domain_rejection(
                        dom_result.intake_result, dom_result
                    )
            elif v.destination == ValidationDestination.PERSONAL_CANDIDATE:
                personal.process_from_validation(edge, v, ext.resolved_entities)

    stats["domain_relations"] = len(domain.get_dynamic_domain().get_all_relations())
    stats["personal_relations"] = len(personal.get_pkg().get_all_relations())
    return stats


def build_default_questions(domain: DomainPipeline, personal: PersonalPipeline) -> List[str]:
    """Derive a couple of questions from the ingested graph so traces never come back empty."""
    questions: List[str] = []

    domain_rels = list(domain.get_dynamic_domain().get_all_relations().values())
    if domain_rels:
        rel = domain_rels[0]
        questions.append(f"{rel.head_name}이 {rel.tail_name}에 영향을 주나요?")
        if len(domain_rels) > 1:
            rel2 = domain_rels[-1]
            questions.append(f"{rel2.head_name}과 {rel2.tail_name} 사이의 관계 방향은 무엇인가요?")

    personal_rels = list(personal.get_pkg().get_all_relations().values())
    if personal_rels:
        rel = personal_rels[0]
        questions.append(f"{rel.head_name}과 {rel.tail_name}의 개인적 연관성이 있나요?")

    if not questions:
        questions = [
            "세종 BRT가 교통 혼잡을 줄였나요?",
            "폭우가 올 때 버스 운행이 지연되나요?",
        ]

    return questions


def run_reasoning_with_trace(
    question: str, pipelines: Dict[str, object]
) -> Dict[str, object]:
    """Run the full reasoning pipeline and expose intermediate artifacts."""
    reasoning: ReasoningPipeline = pipelines["reasoning"]  # type: ignore[assignment]

    parsed = reasoning.query_parser.parse(question)
    retrieval = reasoning.graph_retrieval.retrieve(parsed)

    all_paths = retrieval.direct_paths + retrieval.indirect_paths
    fused_paths = reasoning.edge_fusion.fuse_multiple_paths(all_paths)
    reasoning_result = reasoning.path_reasoning.reason(fused_paths, parsed.query_id)
    conclusion = reasoning.conclusion.synthesize(parsed, reasoning_result)

    return {
        "parsed": parsed,
        "retrieval": retrieval,
        "fused_paths": fused_paths,
        "reasoning": reasoning_result,
        "conclusion": conclusion,
    }


def format_path_trace(
    retrieval_path,
    fused_path_lookup: Dict[str, object],
    entity_names: Dict[str, str],
) -> str:
    """Build a single-line ASCII trace for a path."""
    names = retrieval_path.node_names or retrieval_path.nodes
    arrows: List[str] = []

    for idx, edge in enumerate(retrieval_path.edges):
        head = names[idx] if idx < len(names) else edge.get("head")
        tail = names[idx + 1] if (idx + 1) < len(names) else edge.get("tail")
        rel_type = edge.get("relation_type", "rel")
        sign = edge.get("sign", "+")
        source = edge.get("source", "domain")
        weight = edge.get("domain_conf", edge.get("pcs_score"))

        weight_txt = f"{weight:.2f}" if isinstance(weight, (int, float)) else "?"
        arrows.append(f"{head} -[{rel_type} {sign} {source}, w={weight_txt}]-> {tail}")

    fused = fused_path_lookup.get(retrieval_path.path_id)
    fused_weight = ""
    if fused:
        fused_weight = f" | fused_weight={fused.path_weight:.4f}, sign={fused.path_sign}"

    for idx, node in enumerate(names):
        if node in entity_names:
            names[idx] = entity_names[node]

    path_text = " ".join(arrows) if arrows else "no edges"
    return f"{path_text}{fused_weight}"


def print_graph_snapshot(domain: DomainPipeline, personal: PersonalPipeline, limit: int = 5) -> None:
    """Print a short snapshot of the knowledge graphs."""
    dyn = domain.get_dynamic_domain()
    pkg = personal.get_pkg()

    domain_rels = list(dyn.get_all_relations().values())
    personal_rels = list(pkg.get_all_relations().values())

    print("\n[KG Snapshot]")
    if domain_rels:
        print("  Domain KG:")
        for rel in domain_rels[:limit]:
            print(
                f"   - {rel.head_name} --[{rel.relation_type} {rel.sign}, "
                f"conf={rel.domain_conf:.2f}, ev={rel.evidence_count}]--> {rel.tail_name}"
            )
    else:
        print("  Domain KG: (empty)")

    if personal_rels:
        print("  Personal KG:")
        for rel in personal_rels[:limit]:
            print(
                f"   - {rel.head_name} --[{rel.relation_type} {rel.sign}, "
                f"pcs={rel.pcs_score:.2f}, weight={rel.personal_weight:.2f}]--> {rel.tail_name}"
            )
    else:
        print("  Personal KG: (empty)")


def print_reasoning_trace(question: str, trace: Dict[str, object]) -> None:
    """Nicely render the reasoning trace for one question."""
    parsed = trace["parsed"]
    retrieval = trace["retrieval"]
    fused_paths = trace["fused_paths"]
    reasoning_result = trace["reasoning"]
    conclusion = trace["conclusion"]

    fused_lookup = {fp.path_id: fp for fp in fused_paths}
    path_lookup = {
        p.path_id: p for p in retrieval.direct_paths + retrieval.indirect_paths
    }

    print(f"\n[Q] {question}")
    if parsed.entity_names:
        entities = ", ".join(parsed.entity_names.values())
    else:
        entities = "-"
    print(f"  Parsed entities: {entities}")
    print(
        f"  Retrieval: direct={len(retrieval.direct_paths)}, "
        f"indirect={len(retrieval.indirect_paths)}, "
        f"domain_paths={retrieval.domain_paths_count}, personal_paths={retrieval.personal_paths_count}"
    )

    if reasoning_result.paths_used:
        print("  Paths considered:")
        for idx, path_res in enumerate(reasoning_result.paths_used, start=1):
            base_path = path_lookup.get(path_res.path_id)
            if not base_path:
                continue
            path_text = format_path_trace(
                base_path, fused_lookup, parsed.entity_names
            )
            print(
                f"   {idx}. sign={path_res.combined_sign}, "
                f"strength={path_res.path_strength:.4f}: {path_text}"
            )
    else:
        print("  Paths considered: none")

    print(f"  Conclusion: {conclusion.conclusion_text}")
    print(
        f"  Direction={conclusion.direction.value}, "
        f"confidence={conclusion.confidence:.3f}"
    )
    if conclusion.strongest_path_description:
        print(f"  Strongest path: {conclusion.strongest_path_description}")
    if conclusion.evidence_summary:
        print(f"  Evidence: {conclusion.evidence_summary}")


def main():
    parser = argparse.ArgumentParser(
        description="Run a local end-to-end trace of the ontology chatbot pipeline."
    )
    parser.add_argument(
        "-q",
        "--question",
        action="append",
        help="Add a question to run (can be repeated). Defaults are auto-generated from ingested relations.",
    )
    parser.add_argument(
        "--limit-docs",
        type=int,
        default=3,
        help="How many sample documents to ingest (default: 3).",
    )
    args = parser.parse_args()

    pipelines, use_llm = bootstrap_pipelines()
    docs = load_documents(limit=args.limit_docs)

    print(f"\n{'=' * 70}")
    print("ONTOLOGY SYSTEM v11 - LOCAL TRACE DEMO")
    print(f"{'=' * 70}")
    print(f"Sample docs loaded: {len(docs)} (ingesting up to {args.limit_docs})")
    print(f"LLM mode: {'Ollama' if use_llm else 'Rule-based'}")

    ingest_stats = ingest_documents(docs, pipelines)
    print(
        f"\n[INGEST] docs={ingest_stats['docs']}, "
        f"raw_edges={ingest_stats['raw_edges']}, "
        f"domain_relations={ingest_stats['domain_relations']}, "
        f"personal_relations={ingest_stats['personal_relations']}"
    )

    print_graph_snapshot(pipelines["domain"], pipelines["personal"])

    questions = args.question or build_default_questions(
        pipelines["domain"], pipelines["personal"]
    )
    for q in questions:
        trace = run_reasoning_with_trace(q, pipelines)
        print_reasoning_trace(q, trace)

    if pipelines["llm"]:
        pipelines["llm"].close()


if __name__ == "__main__":
    main()
