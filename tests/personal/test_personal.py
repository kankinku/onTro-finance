"""
Personal Sector 테스트
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.shared.models import RawEdge, ResolvedEntity, ResolutionMode, Polarity
from src.validation.models import (
    ValidationResult, ValidationDestination, SignTag, SemanticTag,
    SchemaValidationResult, SignValidationResult, SemanticValidationResult
)
from src.domain.models import DomainCandidate, DomainProcessResult
from src.personal.models import (
    PersonalLabel, PersonalRelevanceType, SourceType
)
from src.personal.intake import PersonalCandidateIntake
from src.personal.pcs_classifier import PCSClassifier
from src.personal.pkg_update import PersonalKGUpdate
from src.personal.drift_promotion import PersonalDriftAnalyzer
from src.personal.pipeline import PersonalPipeline


def create_test_edge(
    edge_id="R001",
    head_id="E1", tail_id="E2",
    head_name="Test Head", tail_name="Test Tail",
    relation="Affect", polarity=Polarity.POSITIVE, conf=0.6,
    fragment_text="이것은 테스트 문장이다. 아마 상승할 것 같다.",
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
            entity_id="E1", canonical_id="Test_Head",
            canonical_name="Test Head", canonical_type="Concept",
            resolution_mode=ResolutionMode.NEW_ENTITY,
            resolution_conf=0.7, surface_text="테스트", fragment_id="F001",
        ),
        ResolvedEntity(
            entity_id="E2", canonical_id="Test_Tail",
            canonical_name="Test Tail", canonical_type="Concept",
            resolution_mode=ResolutionMode.NEW_ENTITY,
            resolution_conf=0.7, surface_text="대상", fragment_id="F001",
        ),
    ]


def create_personal_validation_result(edge_id="R001"):
    schema = SchemaValidationResult(edge_id=edge_id, schema_valid=True)
    sign = SignValidationResult(
        edge_id=edge_id, polarity_final="+",
        sign_tag=SignTag.AMBIGUOUS, sign_consistency_score=0.5
    )
    semantic = SemanticValidationResult(
        edge_id=edge_id, semantic_tag=SemanticTag.SEM_WEAK,
        semantic_confidence=0.45
    )
    return ValidationResult(
        edge_id=edge_id, validation_passed=True,
        destination=ValidationDestination.PERSONAL_CANDIDATE,
        combined_conf=0.45, student_conf=0.6, sign_score=0.5, semantic_conf=0.45,
        schema_result=schema, sign_result=sign, semantic_result=semantic,
    )


class TestPersonalCandidateIntake:
    """Personal Candidate Intake 테스트"""
    
    def test_intake_from_validation(self):
        """Validation에서 Personal 후보 생성"""
        intake = PersonalCandidateIntake(user_id="test_user")
        edge = create_test_edge()
        entities = create_test_entities()
        validation = create_personal_validation_result()
        
        candidate = intake.process_from_validation(edge, validation, entities)
        
        assert candidate is not None
        assert candidate.user_id == "test_user"
        assert candidate.personal_origin_flag == True
    
    def test_relevance_classification(self):
        """Relevance 분류 테스트"""
        intake = PersonalCandidateIntake()
        
        # 가설 패턴
        edge = create_test_edge(fragment_text="아마 상승할 것 같다")
        entities = create_test_entities()
        validation = create_personal_validation_result()
        
        candidate = intake.process_from_validation(edge, validation, entities)
        
        assert candidate.relevance_type == PersonalRelevanceType.HYPOTHESIS


class TestPCSClassifier:
    """PCS Classifier 테스트"""
    
    def test_pcs_calculation(self):
        """PCS 점수 계산 테스트"""
        pcs = PCSClassifier()
        
        from src.personal.models import PersonalCandidate
        candidate = PersonalCandidate(
            raw_edge_id="R001",
            head_canonical_id="A", head_canonical_name="A",
            tail_canonical_id="B", tail_canonical_name="B",
            relation_type="Affect", polarity="+",
            semantic_tag="sem_confident",
            student_conf=0.8, combined_conf=0.75,
            source_type=SourceType.USER_WRITTEN,
        )
        
        result = pcs.classify(candidate)
        
        assert result.pcs_score >= 0
        assert result.pcs_score <= 1
        assert result.personal_label in [
            PersonalLabel.STRONG_BELIEF,
            PersonalLabel.WEAK_BELIEF,
            PersonalLabel.NOISY_HYPOTHESIS,
        ]
    
    def test_semantic_strength(self):
        """Semantic strength 점수 테스트"""
        pcs = PCSClassifier()
        
        from src.personal.models import PersonalCandidate
        
        # sem_confident는 높은 점수
        candidate1 = PersonalCandidate(
            raw_edge_id="R001",
            head_canonical_id="A", head_canonical_name="A",
            tail_canonical_id="B", tail_canonical_name="B",
            relation_type="Affect", polarity="+",
            semantic_tag="sem_confident",
            student_conf=0.8, combined_conf=0.75,
        )
        result1 = pcs.classify(candidate1)
        
        # sem_wrong은 낮은 점수
        candidate2 = PersonalCandidate(
            raw_edge_id="R002",
            head_canonical_id="A", head_canonical_name="A",
            tail_canonical_id="C", tail_canonical_name="C",
            relation_type="Affect", polarity="+",
            semantic_tag="sem_wrong",
            student_conf=0.8, combined_conf=0.75,
        )
        result2 = pcs.classify(candidate2)
        
        assert result1.semantic_strength > result2.semantic_strength


class TestPersonalKGUpdate:
    """Personal KG Update 테스트"""
    
    def test_create_new_relation(self):
        """신규 관계 생성"""
        pkg = PersonalKGUpdate()
        
        from src.personal.models import PersonalCandidate, PCSResult
        
        candidate = PersonalCandidate(
            raw_edge_id="R001",
            head_canonical_id="A", head_canonical_name="A",
            tail_canonical_id="B", tail_canonical_name="B",
            relation_type="Affect", polarity="+",
            semantic_tag="sem_weak",
            student_conf=0.6, combined_conf=0.5,
        )
        
        pcs_result = PCSResult(
            candidate_id=candidate.candidate_id,
            pcs_score=0.5,
            personal_label=PersonalLabel.WEAK_BELIEF,
        )
        
        relation_id, is_new = pkg.update(candidate, pcs_result)
        
        assert is_new == True
        assert relation_id is not None
        
        relation = pkg.get_relation(relation_id)
        assert relation.occurrence_count == 1
    
    def test_update_existing_no_delete(self):
        """기존 관계 업데이트 (삭제 없이)"""
        pkg = PersonalKGUpdate()
        
        from src.personal.models import PersonalCandidate, PCSResult
        
        candidate = PersonalCandidate(
            raw_edge_id="R001",
            head_canonical_id="A", head_canonical_name="A",
            tail_canonical_id="B", tail_canonical_name="B",
            relation_type="Affect", polarity="+",
            semantic_tag="sem_weak",
            student_conf=0.6, combined_conf=0.5,
        )
        
        pcs_result = PCSResult(
            candidate_id=candidate.candidate_id,
            pcs_score=0.5,
            personal_label=PersonalLabel.WEAK_BELIEF,
        )
        
        # 첫 번째 추가
        rel_id1, is_new1 = pkg.update(candidate, pcs_result)
        
        # 같은 관계 다시 추가
        candidate2 = PersonalCandidate(
            raw_edge_id="R002",
            head_canonical_id="A", head_canonical_name="A",
            tail_canonical_id="B", tail_canonical_name="B",
            relation_type="Affect", polarity="+",
            semantic_tag="sem_confident",
            student_conf=0.8, combined_conf=0.7,
        )
        
        pcs_result2 = PCSResult(
            candidate_id=candidate2.candidate_id,
            pcs_score=0.7,
            personal_label=PersonalLabel.STRONG_BELIEF,
        )
        
        rel_id2, is_new2 = pkg.update(candidate2, pcs_result2)
        
        assert rel_id1 == rel_id2
        assert is_new2 == False
        
        relation = pkg.get_relation(rel_id1)
        assert relation.occurrence_count == 2
        assert len(relation.history) == 2  # 히스토리 유지


class TestPersonalDriftAnalyzer:
    """Personal Drift Analyzer 테스트"""
    
    def test_drift_analysis(self):
        """Drift 분석 테스트"""
        pkg = PersonalKGUpdate()
        analyzer = PersonalDriftAnalyzer(pkg)
        
        from src.personal.models import PersonalRelation
        
        relation = PersonalRelation(
            head_id="A", head_name="A",
            tail_id="B", tail_name="B",
            relation_type="Affect", sign="+",
            user_id="test",
            pcs_score=0.8,
            personal_weight=0.8,
            personal_label=PersonalLabel.STRONG_BELIEF,
            source_type=SourceType.USER_WRITTEN,
            occurrence_count=5,
        )
        
        result = analyzer.analyze(relation)
        
        assert result.drift_signal >= 0
        assert result.drift_signal <= 1


class TestPersonalPipeline:
    """Personal 파이프라인 테스트"""
    
    def test_full_pipeline(self):
        """전체 파이프라인 테스트"""
        pipeline = PersonalPipeline(user_id="test_user")
        edge = create_test_edge()
        entities = create_test_entities()
        validation = create_personal_validation_result()
        
        result = pipeline.process_from_validation(edge, validation, entities)
        
        assert result is not None
        assert result.stored_in_pkg == True
        assert result.personal_label in [
            PersonalLabel.STRONG_BELIEF,
            PersonalLabel.WEAK_BELIEF,
            PersonalLabel.NOISY_HYPOTHESIS,
        ]
    
    def test_stats_tracking(self):
        """통계 추적"""
        pipeline = PersonalPipeline()
        edge = create_test_edge()
        entities = create_test_entities()
        validation = create_personal_validation_result()
        
        pipeline.process_from_validation(edge, validation, entities)
        stats = pipeline.get_stats()
        
        assert stats["total"] >= 1
        assert stats["stored"] >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
