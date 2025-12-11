"""
Domain Candidate Intake Module
"Validation을 통과한 raw edge를 Domain 평가 가능한 형태로 변환"

역할:
- 엣지 기본 정보 정제
- Domain Metadata 추가
- Domain relevance 테스트
"""
import logging
from typing import Optional, List
from datetime import datetime

from src.shared.models import RawEdge, ResolvedEntity
from src.validation.models import ValidationResult, ValidationDestination
from src.domain.models import DomainCandidate

logger = logging.getLogger(__name__)


class DomainCandidateIntake:
    """
    Domain Candidate Intake Module
    Validation 통과 엣지를 Domain 평가용으로 정규화
    """
    
    def __init__(self):
        # Domain relevance 필터링 패턴
        self._irrelevant_patterns = [
            "개인적으로",
            "내 생각에",
            "추측하건대",
            "감상",
        ]
    
    def process(
        self,
        edge: RawEdge,
        validation_result: ValidationResult,
        resolved_entities: List[ResolvedEntity],
    ) -> Optional[DomainCandidate]:
        """
        Raw Edge를 Domain Candidate로 변환
        
        Args:
            edge: 원본 Raw Edge
            validation_result: Validation 결과
            resolved_entities: Resolved Entity 리스트
        
        Returns:
            DomainCandidate 또는 None (Domain 대상이 아닌 경우)
        """
        # Domain Candidate가 아니면 처리하지 않음
        if validation_result.destination != ValidationDestination.DOMAIN_CANDIDATE:
            logger.debug(f"Edge {edge.raw_edge_id} is not a domain candidate")
            return None
        
        # 엔티티 맵
        entity_map = {e.entity_id: e for e in resolved_entities}
        head_entity = entity_map.get(edge.head_entity_id)
        tail_entity = entity_map.get(edge.tail_entity_id)
        
        if not head_entity or not tail_entity:
            logger.warning(f"Missing entities for edge {edge.raw_edge_id}")
            return None
        
        # Domain relevance 테스트
        if not self._is_domain_relevant(edge):
            logger.info(f"Edge {edge.raw_edge_id} is not domain relevant")
            return None
        
        # Polarity 확정
        polarity = self._normalize_polarity(edge, validation_result)
        
        # Semantic tag 추출
        semantic_tag = "unknown"
        if validation_result.semantic_result:
            semantic_tag = validation_result.semantic_result.semantic_tag.value
        
        # Domain Candidate 생성
        candidate = DomainCandidate(
            raw_edge_id=edge.raw_edge_id,
            head_canonical_id=head_entity.canonical_id or head_entity.entity_id,
            head_canonical_name=head_entity.canonical_name or edge.head_canonical_name or "",
            tail_canonical_id=tail_entity.canonical_id or tail_entity.entity_id,
            tail_canonical_name=tail_entity.canonical_name or edge.tail_canonical_name or "",
            relation_type=edge.relation_type,
            polarity=polarity,
            semantic_tag=semantic_tag,
            combined_conf=validation_result.combined_conf,
            student_conf=edge.student_conf or 0.0,
            timestamp=datetime.now(),
            freq_count=1,
            evidence_source="student",
            fragment_text=edge.fragment_text,
        )
        
        logger.info(f"Created domain candidate: {candidate.candidate_id}")
        return candidate
    
    def _is_domain_relevant(self, edge: RawEdge) -> bool:
        """Domain relevance 테스트"""
        text = edge.fragment_text or ""
        text_lower = text.lower()
        
        # 개인적 감상/의견은 제외
        for pattern in self._irrelevant_patterns:
            if pattern in text_lower:
                return False
        
        # 최소 길이 체크
        if len(text) < 10:
            return False
        
        return True
    
    def _normalize_polarity(
        self,
        edge: RawEdge,
        validation_result: ValidationResult,
    ) -> str:
        """Polarity 확정"""
        # Sign Validator 결과 우선
        if validation_result.sign_result:
            return validation_result.sign_result.polarity_final
        
        # Student 추정 사용
        polarity = edge.polarity_guess
        if hasattr(polarity, 'value'):
            polarity = polarity.value
        
        if polarity in ["+", "-", "neutral"]:
            return polarity
        
        return "unknown"
