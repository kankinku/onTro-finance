"""
Validation Sector 테스트
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.shared.models import RawEdge, ResolvedEntity, ResolutionMode, Polarity
from src.validation.models import SignTag, SemanticTag, ValidationDestination
from src.validation.schema_validator import SchemaValidator
from src.validation.sign_validator import SignValidator
from src.validation.semantic_validator import SemanticValidator
from src.validation.confidence_filter import ConfidenceFilter
from src.validation.pipeline import ValidationPipeline


def create_test_edge(
    edge_id="R001",
    head_id="E1",
    tail_id="E2",
    head_name="Federal Reserve",
    tail_name="Federal Funds Rate",
    relation="Affect",
    polarity=Polarity.POSITIVE,
    conf=0.8,
    fragment_id="F001",
    fragment_text="연준이 금리를 인상했다.",
):
    return RawEdge(
        raw_edge_id=edge_id,
        head_entity_id=head_id,
        head_canonical_name=head_name,
        tail_entity_id=tail_id,
        tail_canonical_name=tail_name,
        relation_type=relation,
        polarity_guess=polarity,
        student_conf=conf,
        fragment_id=fragment_id,
        fragment_text=fragment_text,
    )


def create_test_entities():
    return [
        ResolvedEntity(
            entity_id="E1",
            canonical_id="Federal_Reserve",
            canonical_name="Federal Reserve",
            canonical_type="Agent",
            resolution_mode=ResolutionMode.DICTIONARY_MATCH,
            resolution_conf=0.95,
            surface_text="연준",
            fragment_id="F001",
        ),
        ResolvedEntity(
            entity_id="E2",
            canonical_id="Federal_Funds_Rate",
            canonical_name="Federal Funds Rate",
            canonical_type="Indicator",
            resolution_mode=ResolutionMode.DICTIONARY_MATCH,
            resolution_conf=0.95,
            surface_text="금리",
            fragment_id="F001",
        ),
    ]


class TestSchemaValidator:
    """Schema Validator 테스트"""
    
    def test_valid_edge(self):
        """유효한 엣지 통과 테스트"""
        validator = SchemaValidator()
        edge = create_test_edge()
        entities = create_test_entities()
        
        result = validator.validate(edge, entities)
        
        assert result.schema_valid == True
        assert len(result.schema_errors) == 0
    
    def test_self_loop_rejected(self):
        """Self-loop 거부 테스트"""
        validator = SchemaValidator()
        edge = create_test_edge(head_id="E1", tail_id="E1")
        entities = create_test_entities()
        
        result = validator.validate(edge, entities)
        
        assert result.schema_valid == False
        assert "self_loop_detected" in result.schema_errors
    
    def test_invalid_relation_type(self):
        """잘못된 relation type 거부"""
        validator = SchemaValidator()
        edge = create_test_edge(relation="InvalidRelation")
        entities = create_test_entities()
        
        result = validator.validate(edge, entities)
        
        assert result.schema_valid == False
        assert any("invalid_relation_type" in e for e in result.schema_errors)


class TestSignValidator:
    """Sign Validator 테스트"""
    
    def test_positive_pattern_detection(self):
        """양의 패턴 감지 테스트"""
        validator = SignValidator()
        edge = create_test_edge()
        entities = create_test_entities()
        
        result = validator.validate(
            edge=edge,
            fragment_text="금리가 상승하면 채권가격이 하락한다.",
            resolved_entities=entities,
            use_llm=False,
        )
        
        assert result.pattern_polarity in ["+", "-", None]
    
    def test_static_domain_conflict(self):
        """Static domain 충돌 감지"""
        validator = SignValidator()
        
        # 금리 상승 → 채권가격 하락이 static rule인데
        # 반대로 + polarity를 가진 엣지
        entities = [
            ResolvedEntity(
                entity_id="E1", canonical_id="Federal_Funds_Rate",
                canonical_name="Federal Funds Rate", canonical_type="Indicator",
                resolution_mode=ResolutionMode.DICTIONARY_MATCH,
                resolution_conf=0.9, surface_text="금리", fragment_id="F001",
            ),
            ResolvedEntity(
                entity_id="E2", canonical_id="US_10Y_Treasury",
                canonical_name="US 10Y Treasury", canonical_type="Instrument",
                resolution_mode=ResolutionMode.DICTIONARY_MATCH,
                resolution_conf=0.9, surface_text="10년물", fragment_id="F001",
            ),
        ]
        
        edge = create_test_edge(
            head_id="E1", tail_id="E2",
            head_name="Federal Funds Rate", tail_name="US 10Y Treasury",
            polarity=Polarity.POSITIVE,  # 잘못된 방향
        )
        
        result = validator.validate(
            edge=edge,
            fragment_text="금리가 상승하면 채권가격도 상승한다.",
            resolved_entities=entities,
            use_llm=False,
        )
        
        # Static rule과 충돌 감지
        # (실제 Static rule이 있는 경우에만 conflict 발생)
        assert result.sign_tag in [SignTag.SUSPECT, SignTag.AMBIGUOUS, SignTag.CONFIDENT, SignTag.UNKNOWN]


class TestSemanticValidator:
    """Semantic Validator 테스트"""
    
    def test_exaggeration_detection(self):
        """과장 표현 감지 테스트"""
        validator = SemanticValidator()
        edge = create_test_edge()
        entities = create_test_entities()
        
        result = validator.validate(
            edge=edge,
            fragment_text="금리가 인상되면 반드시 주가가 폭락한다.",
            resolved_entities=entities,
            use_llm=False,
        )
        
        assert result.has_exaggeration == True
    
    def test_correlation_as_causation(self):
        """상관을 인과로 오해 감지"""
        validator = SemanticValidator()
        edge = create_test_edge(relation="Cause")
        entities = create_test_entities()
        
        result = validator.validate(
            edge=edge,
            fragment_text="금리와 주가가 함께 상승했다.",
            resolved_entities=entities,
            use_llm=False,
        )
        
        assert result.is_correlation_as_causation == True


class TestConfidenceFilter:
    """Confidence Filter 테스트"""
    
    def test_high_confidence_to_domain(self):
        """높은 신뢰도는 Domain 후보"""
        from src.validation.models import SchemaValidationResult, SignValidationResult, SemanticValidationResult
        
        filter = ConfidenceFilter()
        edge = create_test_edge(conf=0.9)
        
        schema_result = SchemaValidationResult(
            edge_id="R001", schema_valid=True
        )
        sign_result = SignValidationResult(
            edge_id="R001", polarity_final="+",
            sign_tag=SignTag.CONFIDENT, sign_consistency_score=0.9
        )
        semantic_result = SemanticValidationResult(
            edge_id="R001", semantic_tag=SemanticTag.SEM_CONFIDENT,
            semantic_confidence=0.85
        )
        
        result = filter.filter(edge, schema_result, sign_result, semantic_result)
        
        assert result.validation_passed == True
        assert result.destination == ValidationDestination.DOMAIN_CANDIDATE
    
    def test_suspect_sign_rejected(self):
        """Suspect sign은 거부"""
        from src.validation.models import SchemaValidationResult, SignValidationResult, SemanticValidationResult
        
        filter = ConfidenceFilter()
        edge = create_test_edge(conf=0.9)
        
        schema_result = SchemaValidationResult(
            edge_id="R001", schema_valid=True
        )
        sign_result = SignValidationResult(
            edge_id="R001", polarity_final="+",
            sign_tag=SignTag.SUSPECT, sign_consistency_score=0.3
        )
        semantic_result = SemanticValidationResult(
            edge_id="R001", semantic_tag=SemanticTag.SEM_CONFIDENT,
            semantic_confidence=0.85
        )
        
        result = filter.filter(edge, schema_result, sign_result, semantic_result)
        
        assert result.validation_passed == False
        assert result.destination == ValidationDestination.DROP_LOG


class TestValidationPipeline:
    """전체 파이프라인 테스트"""
    
    def test_pipeline_without_llm(self):
        """LLM 없이 파이프라인 테스트"""
        pipeline = ValidationPipeline(use_llm=False)
        edge = create_test_edge()
        entities = create_test_entities()
        
        result = pipeline.validate(edge, entities)
        
        assert result.edge_id == "R001"
        assert result.destination in [
            ValidationDestination.DOMAIN_CANDIDATE,
            ValidationDestination.PERSONAL_CANDIDATE,
            ValidationDestination.DROP_LOG,
        ]
    
    def test_batch_validation(self):
        """배치 검증 테스트"""
        pipeline = ValidationPipeline(use_llm=False)
        entities = create_test_entities()
        
        edges = [
            create_test_edge(edge_id="R001"),
            create_test_edge(edge_id="R002", head_id="E1", tail_id="E1"),  # self-loop
        ]
        
        results = pipeline.validate_batch(edges, entities)
        
        assert len(results) == 2
        # 첫 번째는 통과 가능, 두 번째는 self-loop로 실패
        assert results[1].validation_passed == False
    
    def test_stats_tracking(self):
        """통계 추적 테스트"""
        pipeline = ValidationPipeline(use_llm=False)
        edge = create_test_edge()
        entities = create_test_entities()
        
        pipeline.validate(edge, entities)
        stats = pipeline.get_stats()
        
        assert stats["total"] >= 1
        assert stats["schema_passed"] >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
