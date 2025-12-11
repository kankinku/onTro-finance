"""
Reasoning Pipeline
전체 Reasoning Sector 워크플로우를 통합
"""
import logging
from typing import Optional, Dict

from src.reasoning.models import (
    ParsedQuery, RetrievalResult, ReasoningResult, ReasoningConclusion
)
from src.reasoning.query_parser import QueryParser
from src.reasoning.graph_retrieval import GraphRetrieval
from src.reasoning.edge_fusion import EdgeWeightFusion
from src.reasoning.path_reasoning import PathReasoningEngine
from src.reasoning.conclusion import ConclusionSynthesizer

from src.extraction.ner_student import NERStudent
from src.extraction.entity_resolver import EntityResolver
from src.domain.dynamic_update import DynamicDomainUpdate
from src.personal.pkg_update import PersonalKGUpdate
from src.llm.ollama_client import OllamaClient

logger = logging.getLogger(__name__)


class ReasoningPipeline:
    """
    Reasoning Sector 통합 파이프라인
    
    Query
      → Query Parsing & Entity Localization
      → Graph Retrieval (Domain-first)
      → Edge Weight Fusion Engine (EES)
      → Path Reasoning Engine
      → Conclusion Synthesizer
      → Final Answer
    """
    
    def __init__(
        self,
        domain: Optional[DynamicDomainUpdate] = None,
        personal: Optional[PersonalKGUpdate] = None,
        llm_client: Optional[OllamaClient] = None,
        ner: Optional[NERStudent] = None,
        resolver: Optional[EntityResolver] = None,
    ):
        # 모듈 초기화
        self.query_parser = QueryParser(
            ner_student=ner,
            entity_resolver=resolver,
            llm_client=llm_client,
        )
        self.graph_retrieval = GraphRetrieval(
            domain=domain,
            personal=personal,
        )
        self.edge_fusion = EdgeWeightFusion()
        self.path_reasoning = PathReasoningEngine()
        self.conclusion = ConclusionSynthesizer(llm_client=llm_client)
        
        # 외부 연결
        self.domain = domain
        self.personal = personal
        self.llm_client = llm_client
        
        # 통계
        self._stats = {
            "queries_processed": 0,
            "avg_paths_used": 0.0,
            "avg_confidence": 0.0,
        }
    
    def reason(self, query: str) -> ReasoningConclusion:
        """
        질문에 대한 추론 수행
        
        Args:
            query: 사용자 질문
        
        Returns:
            ReasoningConclusion
        """
        self._stats["queries_processed"] += 1
        
        # Step 1: Query Parsing
        parsed_query = self.query_parser.parse(query)
        logger.info(f"Query parsed: {parsed_query.query_type.value}")
        
        # Step 2: Graph Retrieval
        retrieval_result = self.graph_retrieval.retrieve(parsed_query)
        logger.info(
            f"Retrieved: {len(retrieval_result.direct_paths)} direct, "
            f"{len(retrieval_result.indirect_paths)} indirect"
        )
        
        # 모든 경로 수집
        all_paths = retrieval_result.direct_paths + retrieval_result.indirect_paths
        
        # Step 3: Edge Weight Fusion
        fused_paths = self.edge_fusion.fuse_multiple_paths(all_paths)
        logger.info(f"Fused {len(fused_paths)} paths")
        
        # Step 4: Path Reasoning
        reasoning_result = self.path_reasoning.reason(
            fused_paths, parsed_query.query_id
        )
        logger.info(
            f"Reasoning: direction={reasoning_result.direction.value}, "
            f"confidence={reasoning_result.confidence:.3f}"
        )
        
        # 통계 업데이트
        self._update_stats(reasoning_result)
        
        # Step 5: Conclusion Synthesis
        conclusion = self.conclusion.synthesize(parsed_query, reasoning_result)
        
        return conclusion
    
    def reason_detailed(self, query: str) -> Dict:
        """상세 추론 결과 반환"""
        parsed = self.query_parser.parse(query)
        retrieval = self.graph_retrieval.retrieve(parsed)
        
        all_paths = retrieval.direct_paths + retrieval.indirect_paths
        fused = self.edge_fusion.fuse_multiple_paths(all_paths)
        reasoning = self.path_reasoning.reason(fused, parsed.query_id)
        conclusion = self.conclusion.synthesize(parsed, reasoning)
        
        return {
            "query": query,
            "parsed": {
                "entities": parsed.query_entities,
                "type": parsed.query_type.value,
                "head": parsed.head_entity,
                "tail": parsed.tail_entity,
            },
            "retrieval": {
                "direct_paths": len(retrieval.direct_paths),
                "indirect_paths": len(retrieval.indirect_paths),
                "domain_count": retrieval.domain_paths_count,
                "personal_count": retrieval.personal_paths_count,
            },
            "reasoning": {
                "direction": reasoning.direction.value,
                "confidence": reasoning.confidence,
                "positive_evidence": reasoning.positive_evidence,
                "negative_evidence": reasoning.negative_evidence,
                "paths_used": len(reasoning.paths_used),
                "conflicting": reasoning.conflicting_paths,
            },
            "conclusion": {
                "text": conclusion.conclusion_text,
                "explanation": conclusion.explanation_text,
                "strongest_path": conclusion.strongest_path_description,
            },
        }
    
    def _update_stats(self, result: ReasoningResult):
        """통계 업데이트"""
        n = self._stats["queries_processed"]
        
        # 이동 평균
        old_avg_paths = self._stats["avg_paths_used"]
        new_paths = len(result.paths_used)
        self._stats["avg_paths_used"] = (old_avg_paths * (n-1) + new_paths) / n
        
        old_avg_conf = self._stats["avg_confidence"]
        self._stats["avg_confidence"] = (old_avg_conf * (n-1) + result.confidence) / n
    
    def get_stats(self) -> Dict:
        """통계 반환"""
        return self._stats.copy()
    
    def reset_stats(self):
        """통계 초기화"""
        self._stats = {
            "queries_processed": 0,
            "avg_paths_used": 0.0,
            "avg_confidence": 0.0,
        }
