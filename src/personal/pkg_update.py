"""
Personal Knowledge Graph Update Module
"PCS 점수에 따라 개인 온톨로지(PKG)에 저장하는 단계"

Personal KG는 삭제 개념이 없다 - 모든 히스토리 유지
"""
import logging
from typing import Dict, Optional, List
from datetime import datetime

from src.personal.models import (
    PersonalCandidate, PCSResult, PersonalRelation, PersonalLabel
)

logger = logging.getLogger(__name__)


class PersonalKGUpdate:
    """
    Personal Knowledge Graph Update Module
    개인 온톨로지 관리 (삭제 없음)
    """
    
    def __init__(self):
        # Personal KG 저장소 (In-memory)
        self._relations: Dict[str, PersonalRelation] = {}
        
        # (head, tail, relation_type) -> relation_id 인덱스
        self._relation_index: Dict[tuple, str] = {}
        
        # 사용자별 관계 인덱스
        self._user_index: Dict[str, List[str]] = {}
    
    def update(
        self,
        candidate: PersonalCandidate,
        pcs_result: PCSResult,
    ) -> tuple:
        """
        PKG 업데이트
        
        Args:
            candidate: Personal 후보
            pcs_result: PCS 결과
        
        Returns:
            (relation_id, is_new)
        """
        key = (
            candidate.head_canonical_id,
            candidate.tail_canonical_id,
            candidate.relation_type,
        )
        
        existing_id = self._relation_index.get(key)
        
        if existing_id is None:
            return self._create_new_relation(candidate, pcs_result), True
        else:
            return self._update_existing_relation(existing_id, candidate, pcs_result), False
    
    def _create_new_relation(
        self,
        candidate: PersonalCandidate,
        pcs_result: PCSResult,
    ) -> str:
        """신규 관계 생성"""
        # Personal weight 계산
        personal_weight = self._calculate_weight(pcs_result)
        
        relation = PersonalRelation(
            head_id=candidate.head_canonical_id,
            head_name=candidate.head_canonical_name,
            tail_id=candidate.tail_canonical_id,
            tail_name=candidate.tail_canonical_name,
            relation_type=candidate.relation_type,
            sign=candidate.polarity,
            user_id=candidate.user_id,
            pcs_score=pcs_result.pcs_score,
            personal_weight=personal_weight,
            personal_label=pcs_result.personal_label,
            source_type=candidate.source_type,
            relevance_types=[candidate.relevance_type.value] if candidate.relevance_type else [],
            history=[{
                "timestamp": datetime.now().isoformat(),
                "action": "created",
                "pcs_score": pcs_result.pcs_score,
                "fragment": candidate.fragment_text[:100] if candidate.fragment_text else None,
            }],
        )
        
        # 저장
        self._relations[relation.relation_id] = relation
        key = (relation.head_id, relation.tail_id, relation.relation_type)
        self._relation_index[key] = relation.relation_id
        
        # 사용자 인덱스 업데이트
        if relation.user_id not in self._user_index:
            self._user_index[relation.user_id] = []
        self._user_index[relation.user_id].append(relation.relation_id)
        
        logger.info(f"Created new PKG relation: {relation.relation_id}")
        return relation.relation_id
    
    def _update_existing_relation(
        self,
        relation_id: str,
        candidate: PersonalCandidate,
        pcs_result: PCSResult,
    ) -> str:
        """기존 관계 업데이트 (삭제 없이 히스토리 추가)"""
        relation = self._relations.get(relation_id)
        if not relation:
            return self._create_new_relation(candidate, pcs_result)
        
        # Occurrence 증가
        relation.occurrence_count += 1
        relation.last_occurred_at = datetime.now()
        
        # PCS/Weight 업데이트 (가중 평균)
        old_weight = relation.personal_weight
        new_weight = self._calculate_weight(pcs_result)
        relation.personal_weight = (old_weight * 0.7) + (new_weight * 0.3)
        relation.pcs_score = (relation.pcs_score * 0.7) + (pcs_result.pcs_score * 0.3)
        
        # Label 업데이트
        if pcs_result.pcs_score >= 0.7:
            relation.personal_label = PersonalLabel.STRONG_BELIEF
        elif pcs_result.pcs_score >= 0.4:
            relation.personal_label = PersonalLabel.WEAK_BELIEF
        else:
            relation.personal_label = PersonalLabel.NOISY_HYPOTHESIS
        
        # Relevance type 추가
        if candidate.relevance_type and candidate.relevance_type.value not in relation.relevance_types:
            relation.relevance_types.append(candidate.relevance_type.value)
        
        # 히스토리 추가 (절대 삭제 안함)
        relation.history.append({
            "timestamp": datetime.now().isoformat(),
            "action": "updated",
            "pcs_score": pcs_result.pcs_score,
            "occurrence": relation.occurrence_count,
            "fragment": candidate.fragment_text[:100] if candidate.fragment_text else None,
        })
        
        logger.info(
            f"Updated PKG relation: {relation_id}, "
            f"occurrences={relation.occurrence_count}"
        )
        
        return relation_id
    
    def _calculate_weight(self, pcs_result: PCSResult) -> float:
        """Personal weight 계산"""
        if pcs_result.personal_label == PersonalLabel.STRONG_BELIEF:
            return pcs_result.pcs_score
        elif pcs_result.personal_label == PersonalLabel.WEAK_BELIEF:
            return pcs_result.pcs_score * 0.5
        else:
            return pcs_result.pcs_score * 0.1
    
    def get_relation(self, relation_id: str) -> Optional[PersonalRelation]:
        """관계 조회"""
        return self._relations.get(relation_id)
    
    def get_relation_by_key(
        self,
        head_id: str,
        tail_id: str,
        relation_type: str,
    ) -> Optional[PersonalRelation]:
        """키로 관계 조회"""
        key = (head_id, tail_id, relation_type)
        relation_id = self._relation_index.get(key)
        return self._relations.get(relation_id) if relation_id else None
    
    def get_all_relations(self) -> Dict[str, PersonalRelation]:
        """모든 관계 반환"""
        return self._relations.copy()
    
    def get_user_relations(self, user_id: str) -> List[PersonalRelation]:
        """사용자별 관계 반환"""
        rel_ids = self._user_index.get(user_id, [])
        return [self._relations[rid] for rid in rel_ids if rid in self._relations]
    
    def get_strong_beliefs(self) -> List[PersonalRelation]:
        """Strong belief 관계만 반환"""
        return [
            r for r in self._relations.values()
            if r.personal_label == PersonalLabel.STRONG_BELIEF
        ]
    
    def get_stats(self) -> Dict:
        """통계 반환"""
        labels = {"strong": 0, "weak": 0, "noisy": 0}
        for r in self._relations.values():
            if r.personal_label == PersonalLabel.STRONG_BELIEF:
                labels["strong"] += 1
            elif r.personal_label == PersonalLabel.WEAK_BELIEF:
                labels["weak"] += 1
            else:
                labels["noisy"] += 1
        
        return {
            "total_relations": len(self._relations),
            "labels": labels,
            "users": len(self._user_index),
        }
