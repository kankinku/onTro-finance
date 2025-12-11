"""
Domain Drift Detector + QA Feedback Module
"Dynamic Domain이 시대 변화로 인해 틀렸을 가능성이 있는가?"

시간축: **Long-term drift** (장기 누적)
- 특정 relation에 장기간 반대 evidence가 누적될 때
- Regime shift / pattern 변화 가능성 탐지
- QA 요청으로 사람에게 확인 요청

Modified for Transaction support
"""
import logging
from typing import Optional, List, Dict

from src.domain.models import DynamicRelation, DriftDetectionResult
from src.domain.dynamic_update import DynamicDomainUpdate
from src.storage.transaction_manager import Transaction

logger = logging.getLogger(__name__)


class DomainDriftDetector:
    """
    Domain Drift Detector
    시대 변화로 인한 Domain 관계 변화 감지
    """
    
    def __init__(
        self,
        dynamic_domain: DynamicDomainUpdate,
        drift_threshold: float = 0.6,
        weights: Optional[Dict[str, float]] = None,
    ):
        self.dynamic_domain = dynamic_domain
        self.drift_threshold = drift_threshold
        
        self.weights = weights or {
            "conflict": 0.3,
            "opposite": 0.25,
            "decay": 0.25,
            "semantic": 0.2,
        }
        
        self._drift_candidates: Dict[str, DriftDetectionResult] = {}
    
    def detect(
        self, 
        relation: DynamicRelation,
        tx: Optional[Transaction] = None,
    ) -> DriftDetectionResult:
        """단일 관계의 drift 감지"""
        conflict_score = self._calculate_conflict_score(relation)
        opposite_rate = self._calculate_opposite_rate(relation)
        decay_score = self._calculate_decay_score(relation)
        semantic_score = self._calculate_semantic_score(relation)
        
        drift_signal = (
            self.weights["conflict"] * conflict_score +
            self.weights["opposite"] * opposite_rate +
            self.weights["decay"] * decay_score +
            self.weights["semantic"] * semantic_score
        )
        
        is_drift = drift_signal >= self.drift_threshold
        needs_qa = is_drift and drift_signal >= self.drift_threshold + 0.1
        
        result = DriftDetectionResult(
            relation_id=relation.relation_id,
            drift_signal=drift_signal,
            is_drift=is_drift,
            needs_qa=needs_qa,
            details={
                "conflict": conflict_score,
                "opposite": opposite_rate,
                "decay": decay_score,
                "semantic": semantic_score,
            }
        )
        
        if is_drift:
            relation.drift_flag = True
            self.dynamic_domain.kg_adapter.upsert_relation(relation, tx=tx)
            self._drift_candidates[relation.relation_id] = result
            logger.info(f"Drift detected for {relation.relation_id}: signal={drift_signal:.2f}")
            
        return result
    
    def _calculate_conflict_score(self, relation: DynamicRelation) -> float:
        total = relation.evidence_count + relation.conflict_count
        if total < 5:  # 충분한 데이터 없으면 낮게 평가
            return 0.0
        return relation.conflict_count / total
    
    def _calculate_opposite_rate(self, relation: DynamicRelation) -> float:
        # 반대 증거 비율 (Conflict count와 비슷하지만 다름)
        # 여기서는 단순화를 위해 conflict ratio 재사용하거나 별도 로직
        total = relation.evidence_count + relation.conflict_count
        if total == 0:
            return 0.0
        return relation.conflict_count / total
    
    def _calculate_decay_score(self, relation: DynamicRelation) -> float:
        # decay 적용 횟수나 마지막 업데이트 시간 고려
        if not relation.decay_applied:
            return 0.0
        # Decay 적용되었다면 점수 부여
        return 0.5
    
    def _calculate_semantic_score(self, relation: DynamicRelation) -> float:
        # 의미적 모호성이 높으면 점수 (semantic_tags 활용)
        if "sem_ambiguous" in relation.semantic_tags:
            return 0.8
        if "sem_weak" in relation.semantic_tags:
            return 0.5
        return 0.0

    def get_drift_candidates(self) -> Dict[str, DriftDetectionResult]:
        return self._drift_candidates.copy()
    
    def scan_all_relations(self) -> int:
        """전체 스캔 (배치용)"""
        relations = self.dynamic_domain.get_all_relations()
        count = 0
        
        # 전체 스캔은 트랜잭션 처리가 복잡하므로 여기서는 개별 처리 가정
        # 혹은 배치 처리 로직 구현 필요
        for rel in relations.values():
            res = self.detect(rel)
            if res.is_drift:
                count += 1
        return count
