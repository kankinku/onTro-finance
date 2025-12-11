"""
PCS Classifier (Personal Confidence Scoring)
"이 개인 지식을 얼마나 신뢰할 수 있는가를 정량화한다"

PCS = w1*P1(domain_proximity) + w2*P2(semantic) + w3*P3(user_origin) + w4*P4(consistency)
"""
import logging
from typing import Optional, Dict, Any

from src.personal.models import (
    PersonalCandidate, PCSResult, PersonalLabel, SourceType
)
from src.domain.dynamic_update import DynamicDomainUpdate

logger = logging.getLogger(__name__)


# Semantic tag 점수 매핑
SEMANTIC_SCORES = {
    "sem_confident": 0.9,
    "sem_weak": 0.5,
    "sem_ambiguous": 0.2,
    "sem_spurious": -0.4,
    "sem_wrong": -1.0,
}

# Source type 가중치
SOURCE_WEIGHTS = {
    SourceType.USER_WRITTEN: 0.3,
    SourceType.TEXT_REPORT: 0.1,
    SourceType.LLM_INFERRED: 0.0,
    SourceType.DOMAIN_REJECTED: 0.05,
}


class PCSClassifier:
    """
    PCS Classifier
    Personal Confidence Scoring - 개인 지식 신뢰도 정량화
    """
    
    def __init__(
        self,
        domain: Optional[DynamicDomainUpdate] = None,
        weights: Optional[Dict[str, float]] = None,
    ):
        self.domain = domain
        
        # PCS 가중치
        self.weights = weights or {
            "domain_proximity": 0.25,
            "semantic_strength": 0.3,
            "user_origin": 0.2,
            "consistency": 0.25,
        }
        
        # 패턴 히스토리 (consistency 계산용)
        self._pattern_history: Dict[tuple, int] = {}
        self._total_patterns: int = 0
    
    def classify(
        self,
        candidate: PersonalCandidate,
    ) -> PCSResult:
        """
        PCS 계산 및 분류
        
        Args:
            candidate: Personal 후보
        
        Returns:
            PCSResult
        """
        # Factor 1: Domain proximity
        p1 = self._calculate_domain_proximity(candidate)
        
        # Factor 2: Semantic strength
        p2 = self._calculate_semantic_strength(candidate)
        
        # Factor 3: User origin weight
        p3 = self._calculate_user_origin_weight(candidate)
        
        # Factor 4: Consistency over time
        p4 = self._calculate_consistency(candidate)
        
        # PCS 종합 점수
        pcs_score = (
            self.weights["domain_proximity"] * p1 +
            self.weights["semantic_strength"] * p2 +
            self.weights["user_origin"] * p3 +
            self.weights["consistency"] * p4
        )
        
        # -1 ~ 1 범위를 0 ~ 1로 정규화
        pcs_normalized = (pcs_score + 1) / 2
        
        # 라벨 결정
        if pcs_normalized >= 0.7:
            label = PersonalLabel.STRONG_BELIEF
        elif pcs_normalized >= 0.4:
            label = PersonalLabel.WEAK_BELIEF
        else:
            label = PersonalLabel.NOISY_HYPOTHESIS
        
        # 패턴 히스토리 업데이트
        self._update_pattern_history(candidate)
        
        result = PCSResult(
            candidate_id=candidate.candidate_id,
            pcs_score=pcs_normalized,
            personal_label=label,
            domain_proximity=p1,
            semantic_strength=p2,
            user_origin_weight=p3,
            consistency_score=p4,
            weighted_scores={
                "domain_proximity": self.weights["domain_proximity"] * p1,
                "semantic_strength": self.weights["semantic_strength"] * p2,
                "user_origin": self.weights["user_origin"] * p3,
                "consistency": self.weights["consistency"] * p4,
            },
        )
        
        logger.info(
            f"PCS classified: {candidate.candidate_id} -> "
            f"{label.value} (score={pcs_normalized:.3f})"
        )
        
        return result
    
    def _calculate_domain_proximity(self, candidate: PersonalCandidate) -> float:
        """
        Factor 1: Domain proximity (도메인 근접도)
        Domain과 얼마나 일치하는가?
        """
        if not self.domain:
            return 0.0
        
        # Domain에서 동일 관계 조회
        domain_rel = self.domain.get_relation_by_key(
            candidate.head_canonical_id,
            candidate.tail_canonical_id,
            candidate.relation_type,
        )
        
        if domain_rel is None:
            # Domain에 없음 → 중간 점수
            return 0.0
        
        # Sign 비교
        if candidate.polarity == domain_rel.sign:
            # 일치 → 높은 점수
            return 0.8 * domain_rel.domain_conf
        elif candidate.polarity == "unknown":
            return 0.3 * domain_rel.domain_conf
        else:
            # 반대 → 감점
            return -0.6 * domain_rel.domain_conf
    
    def _calculate_semantic_strength(self, candidate: PersonalCandidate) -> float:
        """
        Factor 2: Semantic strength
        """
        return SEMANTIC_SCORES.get(candidate.semantic_tag, 0.0)
    
    def _calculate_user_origin_weight(self, candidate: PersonalCandidate) -> float:
        """
        Factor 3: User origin weight
        사용자가 직접 표현한 지식이면 높은 점수
        """
        return SOURCE_WEIGHTS.get(candidate.source_type, 0.0)
    
    def _calculate_consistency(self, candidate: PersonalCandidate) -> float:
        """
        Factor 4: Consistency over time
        같은 패턴이 반복되면 점수 상승
        """
        pattern_key = (
            candidate.head_canonical_id,
            candidate.tail_canonical_id,
            candidate.relation_type,
            candidate.polarity,
        )
        
        same_pattern_count = self._pattern_history.get(pattern_key, 0)
        
        if self._total_patterns == 0:
            return 0.0
        
        # 패턴 일관성 = 같은 패턴 / 전체 패턴
        consistency = same_pattern_count / max(self._total_patterns, 1)
        
        # 최대 0.8로 제한
        return min(0.8, consistency * 2)
    
    def _update_pattern_history(self, candidate: PersonalCandidate):
        """패턴 히스토리 업데이트"""
        pattern_key = (
            candidate.head_canonical_id,
            candidate.tail_canonical_id,
            candidate.relation_type,
            candidate.polarity,
        )
        
        self._pattern_history[pattern_key] = self._pattern_history.get(pattern_key, 0) + 1
        self._total_patterns += 1
    
    def get_pattern_stats(self) -> Dict[str, Any]:
        """패턴 통계 반환"""
        return {
            "total_patterns": self._total_patterns,
            "unique_patterns": len(self._pattern_history),
            "top_patterns": sorted(
                self._pattern_history.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5],
        }
