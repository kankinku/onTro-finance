"""
Ontology System - 5 Sectors Pipeline
Extraction → Validation → Domain → Personal → Reasoning

Main entry point
"""
import json
import logging
from pathlib import Path

from src.extraction import ExtractionPipeline
from src.validation import ValidationPipeline
from src.validation.models import ValidationDestination
from src.domain import DomainPipeline
from src.personal import PersonalPipeline
from src.reasoning import ReasoningPipeline
from src.bootstrap import build_llm_client
from config.settings import get_settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """메인 실행 함수"""
    settings = get_settings()
    
    # 빠른 로컬 테스트: LLM 비활성화하여 HTTP 호출 없이 규칙 기반 실행
    llm_client = None
    use_llm = False
    logger.info("[RULE-ONLY] LLM 비활성화, 규칙 기반 파이프라인으로 실행")
    
    # 5개 파이프라인 초기화
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
    
    # 샘플 데이터 로드
    sample_path = Path(__file__).parent / "data" / "samples" / "sample_documents.json"
    
    if not sample_path.exists():
        print("Sample data not found. Running minimal test.")
        test_text = "세종 BRT는 출퇴근 시간대 교통 혼잡을 줄인다."
        result = extraction.process(raw_text=test_text, doc_id="TEST")
        print(f"Test: {len(result.fragments)} fragments")
        if llm_client:
            llm_client.close()
        return
    
    with open(sample_path, "r", encoding="utf-8") as f:
        documents = json.load(f)
    
    print(f"\n{'='*70}")
    print("== ONTOLOGY SYSTEM - 5 SECTOR PIPELINE")
    print(f"{'='*70}")
    print(f"Documents: {len(documents)}")
    print(f"LLM Mode: {'Ollama' if use_llm else 'Rule-based'}")
    
    # Phase 1: 지식 수집 (Extraction → Validation → Domain/Personal)
    print(f"\n{'─'*70}")
    print("[PHASE 1]: Knowledge Collection")
    print(f"{'─'*70}")
    
    for doc in documents:  # 모든 샘플 처리
        doc_id = doc.get("doc_id")
        text = doc.get("text", "")
        
        print(f"\n[DOC] {doc_id}: {text[:40]}...")
        
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
                
                if dom_result.final_destination == "domain":
                    print(f"   [DOMAIN] {edge.head_canonical_name} → {edge.tail_canonical_name}")
                else:
                    if dom_result.intake_result:
                        personal.process_from_domain_rejection(
                            dom_result.intake_result, dom_result
                        )
            
            elif v.destination == ValidationDestination.PERSONAL_CANDIDATE:
                personal.process_from_validation(edge, v, ext.resolved_entities)
    
    # Knowledge 통계
    dyn = domain.get_dynamic_domain()
    pkg = personal.get_pkg()
    
    print(f"\n[STATS] Knowledge Collected:")
    print(f"   Domain KG: {len(dyn.get_all_relations())} relations")
    print(f"   Personal KG: {len(pkg.get_all_relations())} relations")
    
    # Phase 2: 추론 (Reasoning)
    print(f"\n{'─'*70}")
    print("[PHASE 2]: Reasoning")
    print(f"{'─'*70}")
    
    # 테스트 질문들
    test_queries = [
        "세종 BRT가 출퇴근 교통 혼잡을 줄였나요?",
        "폭우가 오면 버스 배차나 이동 시간이 어떻게 변하나요?",
        "도로 공사 구간에서는 통행 시간과 교통 속도가 어떻게 달라지나요?",
    ]
    
    for query in test_queries:
        print(f"\n[Q]: {query}")
        
        conclusion = reasoning.reason(query)
        
        print(f"   [A]: {conclusion.conclusion_text}")
        print(f"   [DIR] Direction: {conclusion.direction.value}, Confidence: {conclusion.confidence:.2f}")
        print(f"   [PATH] Path: {conclusion.strongest_path_description}")
    
    # 최종 통계
    print(f"\n{'='*70}")
    print("[STATS] FINAL STATISTICS")
    print(f"{'='*70}")
    
    print(f"\n[DOMAIN KG]:")
    for rel in list(dyn.get_all_relations().values())[:3]:
        print(f"   - {rel.head_name} --[{rel.relation_type}({rel.sign})]--> {rel.tail_name}")
    
    print(f"\n[PERSONAL KG]:")
    pkg_stats = pkg.get_stats()
    print(f"   Total: {pkg_stats['total_relations']}, "
          f"Strong: {pkg_stats['labels']['strong']}, "
          f"Weak: {pkg_stats['labels']['weak']}")
    
    print(f"\n[REASONING]:")
    r_stats = reasoning.get_stats()
    print(f"   Queries: {r_stats['queries_processed']}, "
          f"Avg Confidence: {r_stats['avg_confidence']:.2f}")
    
    if llm_client:
        llm_client.close()


if __name__ == "__main__":
    main()
