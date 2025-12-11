"""
Personal Candidate Intake Module
"Validation을 통과했지만 Domain에 들어가지 못한 지식을 Personal 후보로 변환"

입력 소스:
- Validation pass + Domain rejection
- Static conflict로 reject된 edge
- Dynamic Domain conflict에서 밀려난 edge
- semantic_tag = weak/spurious/ambiguous
- polarity 불확실한 edge
"""
import logging
from typing import Optional, List
from datetime import datetime

from src.shared.models import RawEdge, ResolvedEntity
from src.validation.models import ValidationResult, ValidationDestination
from src.domain.models import DomainCandidate, DomainProcessResult
from src.personal.models import (
    PersonalCandidate, PersonalRelevanceType, SourceType
)

logger = logging.getLogger(__name__)


class PersonalCandidateIntake:
    """
    Personal Candidate Intake Module
    Domain에 못 들어간 지식을 Personal 후보로 변환
    """
    
    def __init__(self, user_id: str = "default_user"):
        self.user_id = user_id
        
        # Relevance 분류 패턴
        self._emotional_patterns = ["느낌", "기분", "걱정", "불안", "기대"]
        self._hypothesis_patterns = ["것 같다", "아마", "추측", "예상"]
        self._opinion_patterns = ["생각", "의견", "판단", "보인다"]
    
    def process_from_validation(
        self,
        edge: RawEdge,
        validation_result: ValidationResult,
        resolved_entities: List[ResolvedEntity],
    ) -> Optional[PersonalCandidate]:
        """
        Validation 결과에서 Personal 후보 생성
        (Personal Candidate로 분류된 경우)
        """
        if validation_result.destination != ValidationDestination.PERSONAL_CANDIDATE:
            return None
        
        return self._create_candidate(
            edge=edge,
            resolved_entities=resolved_entities,
            semantic_tag=validation_result.semantic_result.semantic_tag.value if validation_result.semantic_result else "unknown",
            sign_tag=validation_result.sign_result.sign_tag.value if validation_result.sign_result else None,
            student_conf=edge.student_conf or 0.0,
            combined_conf=validation_result.combined_conf,
            source_type=SourceType.LLM_INFERRED,
            rejection_reason="validation_personal_candidate",
        )
    
    def process_from_domain_rejection(
        self,
        domain_candidate: DomainCandidate,
        domain_result: DomainProcessResult,
        source_type: SourceType = SourceType.DOMAIN_REJECTED,
    ) -> PersonalCandidate:
        """
        Domain 거부 결과에서 Personal 후보 생성
        """
        rejection_reason = None
        if domain_result.static_result and domain_result.static_result.static_conflict:
            rejection_reason = "static_conflict"
        elif domain_result.conflict_result:
            rejection_reason = f"domain_conflict:{domain_result.conflict_result.resolution.value}"
        else:
            rejection_reason = "domain_rejection"
        
        # Relevance 타입 분류
        relevance_type = self._classify_relevance(domain_candidate.fragment_text or "")
        
        candidate = PersonalCandidate(
            raw_edge_id=domain_candidate.raw_edge_id,
            head_canonical_id=domain_candidate.head_canonical_id,
            head_canonical_name=domain_candidate.head_canonical_name,
            tail_canonical_id=domain_candidate.tail_canonical_id,
            tail_canonical_name=domain_candidate.tail_canonical_name,
            relation_type=domain_candidate.relation_type,
            polarity=domain_candidate.polarity,
            semantic_tag=domain_candidate.semantic_tag,
            student_conf=domain_candidate.student_conf,
            combined_conf=domain_candidate.combined_conf,
            user_id=self.user_id,
            source_type=source_type,
            relevance_type=relevance_type,
            fragment_text=domain_candidate.fragment_text,
            rejection_reason=rejection_reason,
        )
        
        logger.info(f"Created personal candidate from domain rejection: {candidate.candidate_id}")
        return candidate
    
    def _create_candidate(
        self,
        edge: RawEdge,
        resolved_entities: List[ResolvedEntity],
        semantic_tag: str,
        sign_tag: Optional[str],
        student_conf: float,
        combined_conf: float,
        source_type: SourceType,
        rejection_reason: Optional[str],
    ) -> PersonalCandidate:
        """Personal 후보 생성"""
        entity_map = {e.entity_id: e for e in resolved_entities}
        head = entity_map.get(edge.head_entity_id)
        tail = entity_map.get(edge.tail_entity_id)
        
        # Polarity 정규화
        polarity = edge.polarity_guess
        if hasattr(polarity, 'value'):
            polarity = polarity.value
        polarity = str(polarity) if polarity else "unknown"
        
        # Relevance 분류
        relevance_type = self._classify_relevance(edge.fragment_text or "")
        
        return PersonalCandidate(
            raw_edge_id=edge.raw_edge_id,
            head_canonical_id=head.canonical_id if head else edge.head_entity_id,
            head_canonical_name=head.canonical_name if head else edge.head_canonical_name or "",
            tail_canonical_id=tail.canonical_id if tail else edge.tail_entity_id,
            tail_canonical_name=tail.canonical_name if tail else edge.tail_canonical_name or "",
            relation_type=edge.relation_type,
            polarity=polarity,
            semantic_tag=semantic_tag,
            sign_tag=sign_tag,
            student_conf=student_conf,
            combined_conf=combined_conf,
            user_id=self.user_id,
            source_type=source_type,
            relevance_type=relevance_type,
            fragment_text=edge.fragment_text,
            rejection_reason=rejection_reason,
        )
    
    def _classify_relevance(self, text: str) -> PersonalRelevanceType:
        """Personal relevance 분류"""
        text_lower = text.lower()
        
        # 감정적 표현
        if any(p in text_lower for p in self._emotional_patterns):
            return PersonalRelevanceType.EMOTIONAL
        
        # 가설적 표현
        if any(p in text_lower for p in self._hypothesis_patterns):
            return PersonalRelevanceType.HYPOTHESIS
        
        # 의견 표현
        if any(p in text_lower for p in self._opinion_patterns):
            return PersonalRelevanceType.OPINION
        
        # 기본값: 추론
        return PersonalRelevanceType.INFERENCE
