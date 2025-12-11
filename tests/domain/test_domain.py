"""
Domain Sector 테스트
"""
import pytest
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.shared.models import RawEdge, ResolvedEntity, ResolutionMode, Polarity
from src.validation.models import ValidationResult, ValidationDestination, SignTag, SemanticTag
from src.validation.models import SchemaValidationResult, SignValidationResult, SemanticValidationResult
from src.domain.models import DomainAction, ConflictType, ConflictResolution
from src.domain.intake import DomainCandidateIntake
from src.domain.static_guard import StaticDomainGuard
from src.domain.dynamic_update import DynamicDomainUpdate
from src.domain.conflict_analyzer import ConflictAnalyzer
from src.domain.drift_detector import DomainDriftDetector
from src.domain.pipeline import DomainPipeline


def create_test_edge(
    edge_id="R001",
    head_id="E1", tail_id="E2",
    head_name="Federal Reserve", tail_name="Federal Funds Rate",
    relation="Affect", polarity=Polarity.POSITIVE, conf=0.8,
    fragment_text="연준이 금리를 인상했다.",
):
    return RawEdge(
        raw_edge_id=edge_id,
        head_entity_id=head_id, head_canonical_name=head_name,
        tail_entity_id=tail_id, tail_canonical_name=tail_name,
        relation_type=relation, polarity_guess=polarity,
        student_conf=conf, fragment_id="F001", fragment_text=fragment_text,
    )


def create_test_entities():
    return [
        ResolvedEntity(
            entity_id="E1", canonical_id="Federal_Reserve",
            canonical_name="Federal Reserve", canonical_type="Agent",
            resolution_mode=ResolutionMode.DICTIONARY_MATCH,
            resolution_conf=0.95, surface_text="연준", fragment_id="F001",
        ),
        ResolvedEntity(
            entity_id="E2", canonical_id="Federal_Funds_Rate",
            canonical_name="Federal Funds Rate", canonical_type="Indicator",
            resolution_mode=ResolutionMode.DICTIONARY_MATCH,
            resolution_conf=0.95, surface_text="금리", fragment_id="F001",
        ),
    ]


def create_validation_result(edge_id="R001", passed=True, dest=ValidationDestination.DOMAIN_CANDIDATE):
    schema = SchemaValidationResult(edge_id=edge_id, schema_valid=True)
    sign = SignValidationResult(
        edge_id=edge_id, polarity_final="+",
        sign_tag=SignTag.CONFIDENT, sign_consistency_score=0.85
    )
    semantic = SemanticValidationResult(
        edge_id=edge_id, semantic_tag=SemanticTag.SEM_CONFIDENT,
        semantic_confidence=0.8
    )
    return ValidationResult(
        edge_id=edge_id, validation_passed=passed, destination=dest,
        combined_conf=0.75, student_conf=0.8, sign_score=0.85, semantic_conf=0.8,
        schema_result=schema, sign_result=sign, semantic_result=semantic,
    )


class TestDomainCandidateIntake:
    """Domain Candidate Intake 테스트"""
    
    def test_domain_candidate_creation(self):
        """Domain Candidate 생성 테스트"""
        intake = DomainCandidateIntake()
        edge = create_test_edge()
        entities = create_test_entities()
        validation = create_validation_result()
        
        candidate = intake.process(edge, validation, entities)
        
        assert candidate is not None
        assert candidate.head_canonical_id == "Federal_Reserve"
        assert candidate.tail_canonical_id == "Federal_Funds_Rate"
    
    def test_non_domain_candidate_rejected(self):
        """Domain 외 후보 거부 테스트"""
        intake = DomainCandidateIntake()
        edge = create_test_edge()
        entities = create_test_entities()
        validation = create_validation_result(dest=ValidationDestination.PERSONAL_CANDIDATE)
        
        candidate = intake.process(edge, validation, entities)
        
        assert candidate is None


class TestStaticDomainGuard:
    """Static Domain Guard 테스트"""
    
    def test_no_static_rule_passes(self):
        """Static rule 없으면 통과"""
        guard = StaticDomainGuard()
        
        from src.domain.models import DomainCandidate
        candidate = DomainCandidate(
            raw_edge_id="R001",
            head_canonical_id="Unknown_Entity",
            head_canonical_name="Unknown",
            tail_canonical_id="Unknown_Entity2",
            tail_canonical_name="Unknown2",
            relation_type="Affect",
            polarity="+",
            semantic_tag="sem_confident",
            combined_conf=0.8,
            student_conf=0.8,
        )
        
        result = guard.check(candidate)
        
        assert result.static_pass == True
        assert result.static_conflict == False
    
    def test_static_conflict_detected(self):
        """Static 충돌 감지 테스트"""
        guard = StaticDomainGuard()
        
        from src.domain.models import DomainCandidate
        # 금리 ↗ → 채권가격 ↗ (잘못된 관계)
        candidate = DomainCandidate(
            raw_edge_id="R001",
            head_canonical_id="Federal_Funds_Rate",
            head_canonical_name="Federal Funds Rate",
            tail_canonical_id="US_10Y_Treasury",
            tail_canonical_name="US 10Y Treasury",
            relation_type="Affect",
            polarity="+",  # 잘못된 방향 (static은 -)
            semantic_tag="sem_confident",
            combined_conf=0.8,
            student_conf=0.8,
        )
        
        result = guard.check(candidate)
        
        # Static rule이 있다면 충돌 감지
        if guard.is_static_relation("Federal_Funds_Rate", "US_10Y_Treasury"):
            assert result.static_conflict == True


class TestDynamicDomainUpdate:
    """Dynamic Domain Update 테스트"""
    
    def test_new_relation_creation(self):
        """신규 관계 생성"""
        dynamic = DynamicDomainUpdate()
        
        from src.domain.models import DomainCandidate
        candidate = DomainCandidate(
            raw_edge_id="R001",
            head_canonical_id="Entity_A",
            head_canonical_name="Entity A",
            tail_canonical_id="Entity_B",
            tail_canonical_name="Entity B",
            relation_type="Affect",
            polarity="+",
            semantic_tag="sem_confident",
            combined_conf=0.8,
            student_conf=0.8,
        )
        
        result = dynamic.update(candidate)
        
        assert result.is_new == True
        assert result.domain_conf == 0.5  # 초기값
        assert result.evidence_count == 1
    
    def test_relation_strengthening(self):
        """관계 강화 테스트"""
        dynamic = DynamicDomainUpdate()
        
        from src.domain.models import DomainCandidate
        candidate1 = DomainCandidate(
            raw_edge_id="R001",
            head_canonical_id="Entity_A",
            head_canonical_name="Entity A",
            tail_canonical_id="Entity_B",
            tail_canonical_name="Entity B",
            relation_type="Affect", polarity="+",
            semantic_tag="sem_confident",
            combined_conf=0.8, student_conf=0.8,
        )
        
        # 첫 번째 추가
        result1 = dynamic.update(candidate1)
        
        # 같은 관계 다시 추가
        candidate2 = DomainCandidate(
            raw_edge_id="R002",
            head_canonical_id="Entity_A",
            head_canonical_name="Entity A",
            tail_canonical_id="Entity_B",
            tail_canonical_name="Entity B",
            relation_type="Affect", polarity="+",
            semantic_tag="sem_confident",
            combined_conf=0.8, student_conf=0.8,
        )
        
        result2 = dynamic.update(candidate2)
        
        assert result2.is_new == False
        assert result2.evidence_count == 2
        assert result2.domain_conf > result1.domain_conf


class TestConflictAnalyzer:
    """Conflict Analyzer 테스트"""
    
    def test_sign_conflict_detection(self):
        """Sign 충돌 감지"""
        dynamic = DynamicDomainUpdate()
        analyzer = ConflictAnalyzer(dynamic)
        
        from src.domain.models import DomainCandidate, DynamicRelation
        
        # 기존 관계 생성
        existing = DynamicRelation(
            head_id="E_A", head_name="A",
            tail_id="E_B", tail_name="B",
            relation_type="Affect", sign="+",
            evidence_count=10, domain_conf=0.7,
        )
        
        # 반대 sign 후보
        candidate = DomainCandidate(
            raw_edge_id="R001",
            head_canonical_id="E_A", head_canonical_name="A",
            tail_canonical_id="E_B", tail_canonical_name="B",
            relation_type="Affect", polarity="-",
            semantic_tag="sem_confident",
            combined_conf=0.8, student_conf=0.8,
        )
        
        result = analyzer.analyze(candidate, existing)
        
        assert result.has_conflict == True
        assert result.conflict_type == ConflictType.SIGN_CONFLICT


class TestDomainDriftDetector:
    """Domain Drift Detector 테스트"""
    
    def test_drift_detection(self):
        """Drift 감지 테스트"""
        dynamic = DynamicDomainUpdate()
        detector = DomainDriftDetector(dynamic)
        
        from src.domain.models import DynamicRelation
        
        # 충돌이 많은 관계
        relation = DynamicRelation(
            head_id="E_A", head_name="A",
            tail_id="E_B", tail_name="B",
            relation_type="Affect", sign="+",
            evidence_count=5, conflict_count=5,
            domain_conf=0.3,
            semantic_tags=["sem_weak", "sem_ambiguous"],
        )
        
        result = detector.detect(relation)
        
        assert result.drift_signal > 0
        # 충돌이 많으면 drift 후보일 가능성
        assert result.conflict_score > 0


class TestDomainPipeline:
    """Domain 파이프라인 테스트"""
    
    def test_full_pipeline(self):
        """전체 파이프라인 테스트"""
        pipeline = DomainPipeline()
        edge = create_test_edge()
        entities = create_test_entities()
        validation = create_validation_result()
        
        result = pipeline.process(edge, validation, entities)
        
        assert result.raw_edge_id == "R001"
        assert result.final_destination in ["domain", "personal", "log"]
    
    def test_stats_tracking(self):
        """통계 추적 테스트"""
        pipeline = DomainPipeline()
        edge = create_test_edge()
        entities = create_test_entities()
        validation = create_validation_result()
        
        pipeline.process(edge, validation, entities)
        stats = pipeline.get_stats()
        
        assert stats["total"] >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
