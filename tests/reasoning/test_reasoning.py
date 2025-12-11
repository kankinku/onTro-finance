"""
Reasoning Sector 테스트
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.reasoning.models import QueryType, ReasoningDirection
from src.reasoning.query_parser import QueryParser
from src.reasoning.graph_retrieval import GraphRetrieval
from src.reasoning.edge_fusion import EdgeWeightFusion
from src.reasoning.path_reasoning import PathReasoningEngine
from src.reasoning.conclusion import ConclusionSynthesizer
from src.reasoning.pipeline import ReasoningPipeline
from src.domain.dynamic_update import DynamicDomainUpdate
from src.domain.models import DomainCandidate


class TestQueryParser:
    """Query Parser 테스트"""
    
    def test_parse_basic_query(self):
        """기본 질문 파싱"""
        parser = QueryParser()
        result = parser.parse("금리가 오르면 주가는 어떻게 되나요?")
        
        assert result.original_query == "금리가 오르면 주가는 어떻게 되나요?"
        assert len(result.fragments) >= 1
    
    def test_query_type_classification(self):
        """질문 유형 분류"""
        parser = QueryParser()
        
        # 조건부 질문
        result = parser.parse("금리가 오르면 성장주는 어떻게 돼?")
        assert result.query_type == QueryType.CONDITIONED
        
        # 인과 질문
        result = parser.parse("왜 주가가 떨어졌나요?")
        assert result.query_type == QueryType.CAUSAL
        
        # 예측 질문
        result = parser.parse("앞으로 금리는 어떻게 될까요?")
        assert result.query_type == QueryType.PREDICTIVE


class TestGraphRetrieval:
    """Graph Retrieval 테스트"""
    
    def test_retrieval_empty_domain(self):
        """빈 Domain에서 검색"""
        retrieval = GraphRetrieval(domain=None, personal=None)
        
        from src.reasoning.models import ParsedQuery
        query = ParsedQuery(
            original_query="테스트",
            query_entities=["A", "B"],
            head_entity="A",
            tail_entity="B",
        )
        
        result = retrieval.retrieve(query)
        
        assert result.domain_paths_count == 0
        assert result.personal_paths_count == 0
    
    def test_retrieval_with_domain(self):
        """Domain에서 검색"""
        domain = DynamicDomainUpdate()
        
        # 샘플 관계 추가
        candidate = DomainCandidate(
            raw_edge_id="R1",
            head_canonical_id="A",
            head_canonical_name="Entity A",
            tail_canonical_id="B",
            tail_canonical_name="Entity B",
            relation_type="Affect",
            polarity="+",
            semantic_tag="sem_confident",
            combined_conf=0.8,
            student_conf=0.8,
        )
        domain.update(candidate)
        
        retrieval = GraphRetrieval(domain=domain)
        
        from src.reasoning.models import ParsedQuery
        query = ParsedQuery(
            original_query="A가 B에 미치는 영향",
            query_entities=["A", "B"],
            entity_names={"A": "Entity A", "B": "Entity B"},
            head_entity="A",
            tail_entity="B",
        )
        
        result = retrieval.retrieve(query)
        
        assert result.domain_paths_count >= 1


class TestEdgeWeightFusion:
    """Edge Weight Fusion 테스트"""
    
    def test_domain_weight_calculation(self):
        """Domain weight 계산"""
        fusion = EdgeWeightFusion()
        
        from src.reasoning.models import RetrievedPath
        path = RetrievedPath(
            nodes=["A", "B"],
            node_names=["A", "B"],
            edges=[{
                "relation_id": "R1",
                "head": "A",
                "tail": "B",
                "sign": "+",
                "domain_conf": 0.8,
                "decay_factor": 0.0,
                "semantic_tag": "sem_confident",
                "source": "domain",
            }],
            source="domain",
            path_length=1,
        )
        
        fused = fusion.fuse_path(path)
        
        assert len(fused.fused_edges) == 1
        assert fused.fused_edges[0].final_weight > 0
        assert fused.path_sign == "+"
    
    def test_sign_propagation(self):
        """Sign propagation"""
        fusion = EdgeWeightFusion()
        
        from src.reasoning.models import RetrievedPath
        path = RetrievedPath(
            nodes=["A", "B", "C"],
            node_names=["A", "B", "C"],
            edges=[
                {"relation_id": "R1", "head": "A", "tail": "B", "sign": "+",
                 "domain_conf": 0.8, "source": "domain"},
                {"relation_id": "R2", "head": "B", "tail": "C", "sign": "-",
                 "domain_conf": 0.8, "source": "domain"},
            ],
            source="domain",
            path_length=2,
        )
        
        fused = fusion.fuse_path(path)
        
        # + × - = -
        assert fused.path_sign == "-"


class TestPathReasoningEngine:
    """Path Reasoning Engine 테스트"""
    
    def test_single_path_reasoning(self):
        """단일 경로 추론"""
        engine = PathReasoningEngine()
        
        from src.reasoning.models import FusedPath, FusedEdge
        path = FusedPath(
            path_id="P1",
            nodes=["A", "B"],
            fused_edges=[
                FusedEdge(
                    edge_id="R1", head_id="A", tail_id="B",
                    relation_type="Affect", sign="-",
                    final_weight=0.8,
                ),
            ],
            path_weight=0.8,
            path_sign="-",
        )
        
        result = engine.reason([path], "Q1")
        
        assert result.direction == ReasoningDirection.NEGATIVE
        assert result.confidence > 0
    
    def test_multiple_path_aggregation(self):
        """다중 경로 집계"""
        engine = PathReasoningEngine()
        
        from src.reasoning.models import FusedPath, FusedEdge
        
        paths = [
            FusedPath(
                path_id="P1", nodes=["A", "B"],
                fused_edges=[FusedEdge(
                    edge_id="R1", head_id="A", tail_id="B",
                    relation_type="Affect", sign="+", final_weight=0.8
                )],
                path_weight=0.8, path_sign="+",
            ),
            FusedPath(
                path_id="P2", nodes=["A", "C", "B"],
                fused_edges=[
                    FusedEdge(edge_id="R2", head_id="A", tail_id="C",
                              relation_type="Affect", sign="+", final_weight=0.6),
                    FusedEdge(edge_id="R3", head_id="C", tail_id="B",
                              relation_type="Affect", sign="+", final_weight=0.6),
                ],
                path_weight=0.36, path_sign="+",
            ),
        ]
        
        result = engine.reason(paths, "Q1")
        
        # 두 경로 모두 +이므로 양의 방향
        assert result.direction == ReasoningDirection.POSITIVE
        assert result.positive_evidence > 0


class TestConclusionSynthesizer:
    """Conclusion Synthesizer 테스트"""
    
    def test_generate_conclusion(self):
        """결론 생성"""
        synthesizer = ConclusionSynthesizer()
        
        from src.reasoning.models import ParsedQuery, ReasoningResult, PathReasoningResult
        
        parsed = ParsedQuery(
            original_query="금리가 주가에 미치는 영향은?",
            head_entity="Rate",
            tail_entity="Stock",
            entity_names={"Rate": "금리", "Stock": "주가"},
        )
        
        path_result = PathReasoningResult(
            path_id="P1",
            nodes=["Rate", "Stock"],
            node_names=["금리", "주가"],
            combined_sign="-",
            path_strength=0.8,
            edge_signs=["-"],
            edge_weights=[0.8],
        )
        
        reasoning = ReasoningResult(
            query_id="Q1",
            direction=ReasoningDirection.NEGATIVE,
            confidence=0.8,
            paths_used=[path_result],
            strongest_path=path_result,
            positive_evidence=0.0,
            negative_evidence=0.8,
        )
        
        conclusion = synthesizer.synthesize(parsed, reasoning)
        
        assert "금리" in conclusion.conclusion_text
        assert conclusion.direction == ReasoningDirection.NEGATIVE


class TestReasoningPipeline:
    """전체 파이프라인 테스트"""
    
    def test_full_pipeline(self):
        """전체 파이프라인"""
        # Domain 준비
        domain = DynamicDomainUpdate()
        
        candidate = DomainCandidate(
            raw_edge_id="R1",
            head_canonical_id="Federal_Funds_Rate",
            head_canonical_name="금리",
            tail_canonical_id="Stock",
            tail_canonical_name="주가",
            relation_type="Affect",
            polarity="-",
            semantic_tag="sem_confident",
            combined_conf=0.8,
            student_conf=0.8,
        )
        domain.update(candidate)
        
        pipeline = ReasoningPipeline(domain=domain)
        
        result = pipeline.reason("금리가 주가에 미치는 영향은?")
        
        assert result.original_query == "금리가 주가에 미치는 영향은?"
        assert result.conclusion_text is not None
    
    def test_stats_tracking(self):
        """통계 추적"""
        pipeline = ReasoningPipeline()
        
        pipeline.reason("테스트 질문")
        stats = pipeline.get_stats()
        
        assert stats["queries_processed"] >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
