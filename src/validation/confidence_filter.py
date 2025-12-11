"""
Confidence Filter
Validation의 최종 단계: Edge를 다음 섹터로 넘길지 결정

조건:
A. schema_valid = true
B. sign_tag ∈ {confident, ambiguous}
C. semantic_tag ∈ {sem_confident, sem_weak, sem_ambiguous}
D. combined_conf >= threshold
"""
import logging
from typing import Optional

from src.shared.models import RawEdge
from src.validation.models import (
    SchemaValidationResult,
    SignValidationResult,
    SemanticValidationResult,
    ValidationResult,
    ValidationDestination,
    SignTag,
    SemanticTag,
)
from config.settings import get_settings

logger = logging.getLogger(__name__)


class ConfidenceFilter:
    """
    Confidence Filter
    최종적으로 Domain/Personal 후보로 보낼지, Drop+Log할지 결정
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._thresholds = self._load_thresholds()
        self._weights = self._load_weights()
    
    def _load_thresholds(self) -> dict:
        try:
            data = self.settings.load_yaml_config("validation_schema")
            rules = data.get("validation_rules", {})
            return rules.get("confidence_thresholds", {
                "domain_candidate": 0.55,
                "personal_candidate": 0.35,
            })
        except FileNotFoundError:
            return {"domain_candidate": 0.55, "personal_candidate": 0.35}
    
    def _load_weights(self) -> dict:
        try:
            data = self.settings.load_yaml_config("validation_schema")
            rules = data.get("validation_rules", {})
            return rules.get("confidence_weights", {
                "student_conf": 0.4,
                "sign_score": 0.3,
                "semantic_conf": 0.3,
            })
        except FileNotFoundError:
            return {"student_conf": 0.4, "sign_score": 0.3, "semantic_conf": 0.3}
    
    def filter(
        self,
        edge: RawEdge,
        schema_result: SchemaValidationResult,
        sign_result: SignValidationResult,
        semantic_result: SemanticValidationResult,
    ) -> ValidationResult:
        """
        최종 필터링 수행
        
        Args:
            edge: 원본 Edge
            schema_result: Schema 검증 결과
            sign_result: Sign 검증 결과
            semantic_result: Semantic 검증 결과
        
        Returns:
            ValidationResult
        """
        rejection_reasons = []
        
        # Condition A: schema_valid = true
        if not schema_result.schema_valid:
            rejection_reasons.append("schema_invalid")
        
        # Condition B: sign_tag ∈ {confident, ambiguous}
        allowed_sign_tags = {SignTag.CONFIDENT, SignTag.AMBIGUOUS}
        if sign_result.sign_tag not in allowed_sign_tags:
            rejection_reasons.append(f"sign_tag:{sign_result.sign_tag.value}")
        
        # Condition C: semantic_tag ∈ {sem_confident, sem_weak, sem_ambiguous}
        allowed_semantic_tags = {
            SemanticTag.SEM_CONFIDENT,
            SemanticTag.SEM_WEAK,
            SemanticTag.SEM_AMBIGUOUS,
        }
        if semantic_result.semantic_tag not in allowed_semantic_tags:
            rejection_reasons.append(f"semantic_tag:{semantic_result.semantic_tag.value}")
        
        # 점수 계산
        student_conf = edge.student_conf if edge.student_conf else 0.0
        sign_score = sign_result.sign_consistency_score
        semantic_conf = semantic_result.semantic_confidence
        
        combined_conf = (
            self._weights["student_conf"] * student_conf +
            self._weights["sign_score"] * sign_score +
            self._weights["semantic_conf"] * semantic_conf
        )
        
        # Condition D: combined_conf >= threshold
        domain_threshold = self._thresholds["domain_candidate"]
        personal_threshold = self._thresholds["personal_candidate"]
        
        # 최종 결정
        if rejection_reasons:
            return ValidationResult(
                edge_id=edge.raw_edge_id,
                validation_passed=False,
                destination=ValidationDestination.DROP_LOG,
                combined_conf=combined_conf,
                student_conf=student_conf,
                sign_score=sign_score,
                semantic_conf=semantic_conf,
                schema_result=schema_result,
                sign_result=sign_result,
                semantic_result=semantic_result,
                rejection_reason=rejection_reasons[0],
                rejection_details=rejection_reasons,
            )
        
        # 점수 기반 목적지 결정
        if combined_conf >= domain_threshold:
            destination = ValidationDestination.DOMAIN_CANDIDATE
        elif combined_conf >= personal_threshold:
            destination = ValidationDestination.PERSONAL_CANDIDATE
        else:
            return ValidationResult(
                edge_id=edge.raw_edge_id,
                validation_passed=False,
                destination=ValidationDestination.DROP_LOG,
                combined_conf=combined_conf,
                student_conf=student_conf,
                sign_score=sign_score,
                semantic_conf=semantic_conf,
                schema_result=schema_result,
                sign_result=sign_result,
                semantic_result=semantic_result,
                rejection_reason="low_confidence",
                rejection_details=[f"combined_conf:{combined_conf:.3f} < {personal_threshold}"],
            )
        
        logger.info(
            f"Edge {edge.raw_edge_id} passed validation -> {destination.value} "
            f"(conf={combined_conf:.3f})"
        )
        
        return ValidationResult(
            edge_id=edge.raw_edge_id,
            validation_passed=True,
            destination=destination,
            combined_conf=combined_conf,
            student_conf=student_conf,
            sign_score=sign_score,
            semantic_conf=semantic_conf,
            schema_result=schema_result,
            sign_result=sign_result,
            semantic_result=semantic_result,
        )
