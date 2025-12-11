"""
Personal Drift Analyzer & Domain Promotion Module
"Personal KG에서 반복적으로 나타나는 관계가 Domain에 의해 '새로운 패턴'일 수 있는지 판단"

Personal → Domain 승격의 다리 역할
"""
import logging
from typing import Optional, List, Dict
from datetime import datetime, timedelta

from src.personal.models import PersonalRelation, PersonalDriftResult, PersonalLabel
from src.personal.pkg_update import PersonalKGUpdate
from src.domain.static_guard import StaticDomainGuard
from src.domain.dynamic_update import DynamicDomainUpdate

logger = logging.getLogger(__name__)


class PersonalDriftAnalyzer:
    """
    Personal Drift Analyzer & Domain Promotion
    개인 지식의 Domain 승격 가능성 분석
    """
    
    def __init__(
        self,
        pkg: PersonalKGUpdate,
        static_guard: Optional[StaticDomainGuard] = None,
        dynamic_domain: Optional[DynamicDomainUpdate] = None,
        promotion_threshold: float = 0.8,
        min_occurrences: int = 3,
        min_days_span: int = 7,
    ):
        self.pkg = pkg
        self.static_guard = static_guard
        self.dynamic_domain = dynamic_domain
        
        self.promotion_threshold = promotion_threshold
        self.min_occurrences = min_occurrences
        self.min_days_span = min_days_span
        
        # 가중치
        self.weights = {
            "pcs": 0.3,
            "consistency": 0.3,
            "domain_gap": 0.2,
            "time": 0.2,
        }
        
        # Promotion 후보
        self._promotion_candidates: List[str] = []
    
    def analyze(self, relation: PersonalRelation) -> PersonalDriftResult:
        """
        단일 관계의 drift/promotion 가능성 분석
        
        Args:
            relation: Personal KG 관계
        
        Returns:
            PersonalDriftResult
        """
        # Factor 계산
        pcs_factor = self._calculate_pcs_factor(relation)
        consistency_factor = self._calculate_consistency_factor(relation)
        domain_gap_factor = self._calculate_domain_gap_factor(relation)
        time_factor = self._calculate_time_factor(relation)
        
        # Drift signal
        drift_signal = (
            self.weights["pcs"] * pcs_factor +
            self.weights["consistency"] * consistency_factor +
            self.weights["domain_gap"] * domain_gap_factor +
            self.weights["time"] * time_factor
        )
        
        # Static Domain 충돌 체크
        static_conflict = self._check_static_conflict(relation)
        
        # Promotion 가능 여부
        is_promotion_candidate = (
            drift_signal >= self.promotion_threshold and
            not static_conflict and
            relation.occurrence_count >= self.min_occurrences
        )
        
        can_promote = is_promotion_candidate
        promotion_reason = None
        
        if is_promotion_candidate:
            self._promotion_candidates.append(relation.relation_id)
            promotion_reason = f"drift_signal={drift_signal:.3f}, occurrences={relation.occurrence_count}"
            logger.info(f"Promotion candidate: {relation.relation_id}, {promotion_reason}")
        elif static_conflict:
            promotion_reason = "static_domain_conflict"
        
        return PersonalDriftResult(
            relation_id=relation.relation_id,
            drift_signal=drift_signal,
            is_promotion_candidate=is_promotion_candidate,
            pcs_factor=pcs_factor,
            consistency_factor=consistency_factor,
            domain_gap_factor=domain_gap_factor,
            time_factor=time_factor,
            static_conflict=static_conflict,
            can_promote=can_promote,
            promotion_reason=promotion_reason,
        )
    
    def _calculate_pcs_factor(self, relation: PersonalRelation) -> float:
        """PCS 기반 factor"""
        if relation.personal_label == PersonalLabel.STRONG_BELIEF:
            return relation.pcs_score
        elif relation.personal_label == PersonalLabel.WEAK_BELIEF:
            return relation.pcs_score * 0.5
        else:
            return 0.1
    
    def _calculate_consistency_factor(self, relation: PersonalRelation) -> float:
        """일관성 factor - 같은 패턴이 반복되는지"""
        # occurrence_count 기반
        if relation.occurrence_count >= 10:
            return 1.0
        elif relation.occurrence_count >= 5:
            return 0.7
        elif relation.occurrence_count >= 3:
            return 0.5
        else:
            return 0.2
    
    def _calculate_domain_gap_factor(self, relation: PersonalRelation) -> float:
        """Domain과의 gap factor"""
        if not self.dynamic_domain:
            return 0.5
        
        # Domain에 해당 관계가 없으면 높은 점수 (새로운 발견 가능)
        domain_rel = self.dynamic_domain.get_relation_by_key(
            relation.head_id, relation.tail_id, relation.relation_type
        )
        
        if domain_rel is None:
            return 0.8  # Domain에 없음 → 새로운 지식일 가능성
        
        # Domain에 있지만 sign이 다름
        if relation.sign != domain_rel.sign:
            # 충돌 → Domain drift 가능성
            if domain_rel.domain_conf < 0.5:
                return 0.7  # Domain도 약함 → 변화 가능
            else:
                return 0.2  # Domain이 강함 → 승격 어려움
        
        # Domain과 일치
        return 0.4
    
    def _calculate_time_factor(self, relation: PersonalRelation) -> float:
        """시간 기반 factor - 오래 지속된 패턴인지"""
        if not relation.history or len(relation.history) < 2:
            return 0.2
        
        try:
            first_ts = datetime.fromisoformat(relation.history[0]["timestamp"])
            last_ts = datetime.fromisoformat(relation.history[-1]["timestamp"])
            days_span = (last_ts - first_ts).days
            
            if days_span >= 30:
                return 1.0
            elif days_span >= self.min_days_span:
                return 0.6
            else:
                return 0.3
        except (KeyError, ValueError):
            return 0.2
    
    def _check_static_conflict(self, relation: PersonalRelation) -> bool:
        """Static Domain과 충돌 여부"""
        if not self.static_guard:
            return False
        
        return self.static_guard.is_static_relation(
            relation.head_id, relation.tail_id
        )
    
    def scan_all_relations(self) -> List[PersonalDriftResult]:
        """모든 PKG 관계 스캔"""
        results = []
        for relation in self.pkg.get_all_relations().values():
            result = self.analyze(relation)
            results.append(result)
        
        promotion_count = sum(1 for r in results if r.is_promotion_candidate)
        logger.info(f"Personal drift scan: {promotion_count}/{len(results)} promotion candidates")
        
        return results
    
    def get_promotion_candidates(self) -> List[PersonalRelation]:
        """Promotion 후보 관계 반환"""
        return [
            self.pkg.get_relation(rid)
            for rid in self._promotion_candidates
            if self.pkg.get_relation(rid)
        ]
    
    def promote_to_domain(
        self,
        relation_id: str,
        dynamic_domain: DynamicDomainUpdate,
    ) -> bool:
        """
        Personal에서 Domain으로 승격
        
        Args:
            relation_id: 승격할 관계 ID
            dynamic_domain: Dynamic Domain
        
        Returns:
            성공 여부
        """
        relation = self.pkg.get_relation(relation_id)
        if not relation:
            return False
        
        # Static 충돌 최종 확인
        if self._check_static_conflict(relation):
            logger.warning(f"Cannot promote {relation_id}: static conflict")
            return False
        
        # Domain Candidate 형태로 변환
        from src.domain.models import DomainCandidate
        
        candidate = DomainCandidate(
            raw_edge_id=f"PROMOTED_{relation_id}",
            head_canonical_id=relation.head_id,
            head_canonical_name=relation.head_name,
            tail_canonical_id=relation.tail_id,
            tail_canonical_name=relation.tail_name,
            relation_type=relation.relation_type,
            polarity=relation.sign,
            semantic_tag="sem_confident",
            combined_conf=relation.pcs_score,
            student_conf=relation.pcs_score,
            evidence_source="personal_promotion",
        )
        
        # Dynamic Domain에 추가
        result = dynamic_domain.update(candidate)
        
        # Personal 관계에 승격 표시
        relation.promotion_candidate = True
        relation.history.append({
            "timestamp": datetime.now().isoformat(),
            "action": "promoted_to_domain",
            "domain_relation_id": result.relation_id,
        })
        
        # 후보 목록에서 제거
        if relation_id in self._promotion_candidates:
            self._promotion_candidates.remove(relation_id)
        
        logger.info(f"Promoted {relation_id} to domain: {result.relation_id}")
        return True
