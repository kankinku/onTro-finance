"""
Validation Pipeline
전체 Validation Sector 워크플로우를 통합
"""
import logging
import time
from typing import List, Optional, Dict, Any

from src.shared.models import RawEdge, ResolvedEntity
from src.validation.models import ValidationResult, ValidationDestination
from src.validation.schema_validator import SchemaValidator
from src.validation.sign_validator import SignValidator
from src.validation.semantic_validator import SemanticValidator
from src.validation.confidence_filter import ConfidenceFilter
from src.llm.ollama_client import OllamaClient

logger = logging.getLogger(__name__)


class ValidationPipeline:
    """
    Validation Sector 통합 파이프라인
    
    Raw Edge → Schema → Sign → Semantic → Confidence Filter
            → Domain/Personal Candidate 또는 Drop+Log
    """
    
    def __init__(
        self,
        llm_client: Optional[OllamaClient] = None,
        use_llm: bool = True,
        domain_kg: Optional[Dict[str, Any]] = None,
    ):
        self.use_llm = use_llm
        self.llm_client = llm_client
        self.domain_kg = domain_kg or {}
        
        # Validator 초기화
        self.schema_validator = SchemaValidator()
        self.sign_validator = SignValidator(llm_client=llm_client)
        self.semantic_validator = SemanticValidator(llm_client=llm_client)
        self.confidence_filter = ConfidenceFilter()
        
        # 통계
        self._stats = {
            "total": 0,
            "schema_passed": 0,
            "sign_passed": 0,
            "semantic_passed": 0,
            "domain_candidate": 0,
            "personal_candidate": 0,
            "dropped": 0,
        }
    
    def validate(
        self,
        edge: RawEdge,
        resolved_entities: List[ResolvedEntity],
        fragment_text: Optional[str] = None,
    ) -> ValidationResult:
        """
        단일 Edge 검증
        
        Args:
            edge: 검증할 Raw Edge
            resolved_entities: Resolved Entity 리스트
            fragment_text: 원본 fragment 텍스트
        
        Returns:
            ValidationResult
        """
        self._stats["total"] += 1
        fragment_text = fragment_text or edge.fragment_text or ""
        
        # Step 1: Schema Validation
        schema_result = self.schema_validator.validate(edge, resolved_entities)
        
        if not schema_result.schema_valid:
            self._stats["dropped"] += 1
            return ValidationResult(
                edge_id=edge.raw_edge_id,
                validation_passed=False,
                destination=ValidationDestination.DROP_LOG,
                schema_result=schema_result,
                rejection_reason="schema_invalid",
                rejection_details=schema_result.schema_errors,
            )
        
        self._stats["schema_passed"] += 1
        
        # Step 2: Sign Validation
        sign_result = self.sign_validator.validate(
            edge=edge,
            fragment_text=fragment_text,
            resolved_entities=resolved_entities,
            use_llm=self.use_llm,
        )
        
        self._stats["sign_passed"] += 1
        
        # Step 3: Semantic Validation
        semantic_result = self.semantic_validator.validate(
            edge=edge,
            fragment_text=fragment_text,
            resolved_entities=resolved_entities,
            domain_kg=self.domain_kg,
            use_llm=self.use_llm,
        )
        
        self._stats["semantic_passed"] += 1
        
        # Step 4: Confidence Filter
        final_result = self.confidence_filter.filter(
            edge=edge,
            schema_result=schema_result,
            sign_result=sign_result,
            semantic_result=semantic_result,
        )
        
        # 통계 업데이트
        if final_result.destination == ValidationDestination.DOMAIN_CANDIDATE:
            self._stats["domain_candidate"] += 1
        elif final_result.destination == ValidationDestination.PERSONAL_CANDIDATE:
            self._stats["personal_candidate"] += 1
        else:
            self._stats["dropped"] += 1
        
        return final_result
    
    def validate_batch(
        self,
        edges: List[RawEdge],
        resolved_entities: List[ResolvedEntity],
        fragment_texts: Optional[Dict[str, str]] = None,
    ) -> List[ValidationResult]:
        """
        배치 검증
        
        Args:
            edges: Raw Edge 리스트
            resolved_entities: Resolved Entity 리스트
            fragment_texts: fragment_id -> text 맵
        
        Returns:
            ValidationResult 리스트
        """
        fragment_texts = fragment_texts or {}
        results = []
        
        for edge in edges:
            text = fragment_texts.get(edge.fragment_id, edge.fragment_text or "")
            result = self.validate(
                edge=edge,
                resolved_entities=resolved_entities,
                fragment_text=text,
            )
            results.append(result)
        
        logger.info(f"Batch validation complete: {self._stats}")
        return results
    
    def get_stats(self) -> Dict[str, int]:
        """통계 반환"""
        return self._stats.copy()
    
    def reset_stats(self):
        """통계 초기화"""
        for key in self._stats:
            self._stats[key] = 0
