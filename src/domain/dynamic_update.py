"""
Dynamic Domain Update Module
"Static에 속하지 않지만, 시대/환경에 따라 달라질 수 있는 관계를 업데이트"

시간축: **Short-term update** (단일/소수 evidence 단위)
- 단일 evidence가 들어올 때마다 conf/evidence/decay 업데이트
- 즉시 반영, 누적 효과

Modified: GraphRepository 기반으로 영속성 관리
"""
import logging
import math
from typing import Dict, Optional, List
from datetime import datetime, timedelta

from src.bootstrap import get_domain_kg_adapter
from src.domain.kg_adapter import DomainKGAdapter
from src.domain.models import (
    DomainCandidate, DynamicRelation, DynamicUpdateResult, DomainAction
)
from src.storage.transaction_manager import Transaction

logger = logging.getLogger(__name__)


class DynamicDomainUpdate:
    """
    Dynamic Domain Update Module
    영속성 레이어(DomainKGAdapter)를 통해 상태 관리
    """
    
    def __init__(
        self,
        kg_adapter: Optional[DomainKGAdapter] = None,
        initial_conf: float = 0.5,
        conf_increase_rate: float = 0.05,
        conf_decrease_rate: float = 0.08,
        decay_rate: float = 0.98,
        decay_days: int = 30,
    ):
        self.kg_adapter = kg_adapter or get_domain_kg_adapter()
        self.initial_conf = initial_conf
        self.conf_increase_rate = conf_increase_rate
        self.conf_decrease_rate = conf_decrease_rate
        self.decay_rate = decay_rate
        self.decay_days = decay_days
    
    def update(
        self,
        candidate: DomainCandidate,
        tx: Optional[Transaction] = None,
    ) -> DynamicUpdateResult:
        """Dynamic Domain 업데이트"""
        # 1. Adapter에서 조회
        relation = self.kg_adapter.get_relation(
            candidate.head_canonical_id,
            candidate.tail_canonical_id,
            candidate.relation_type,
        )
        
        if relation is None:
            return self._create_new_relation(candidate, tx)
        else:
            return self._update_existing_relation(relation, candidate, tx)
    
    def _create_new_relation(
        self,
        candidate: DomainCandidate,
        tx: Optional[Transaction],
    ) -> DynamicUpdateResult:
        """신규 관계 생성"""
        relation = DynamicRelation(
            head_id=candidate.head_canonical_id,
            head_name=candidate.head_canonical_name,
            tail_id=candidate.tail_canonical_id,
            tail_name=candidate.tail_canonical_name,
            relation_type=candidate.relation_type,
            sign=candidate.polarity,
            domain_conf=self.initial_conf,
            evidence_count=1,
            origin=candidate.evidence_source,
            semantic_tags=[candidate.semantic_tag],
        )
        
        # 저장
        self.kg_adapter.upsert_relation(relation, tx=tx)
        
        logger.info(f"Created new dynamic relation: {relation.relation_id}")
        
        return DynamicUpdateResult(
            candidate_id=candidate.candidate_id,
            relation_id=relation.relation_id,
            action=DomainAction.CREATE_NEW,
            domain_conf=relation.domain_conf,
            evidence_count=relation.evidence_count,
            is_new=True,
        )
    
    def _update_existing_relation(
        self,
        relation: DynamicRelation,
        candidate: DomainCandidate,
        tx: Optional[Transaction],
    ) -> DynamicUpdateResult:
        """기존 관계 업데이트"""
        previous_conf = relation.domain_conf
        previous_evidence = relation.evidence_count
        
        decayed = self._apply_decay(relation)
        
        if candidate.polarity == relation.sign or candidate.polarity == "unknown":
            relation = self._strengthen_relation(relation, candidate)
            conflict_pending = False
        else:
            relation = self._weaken_relation(relation, candidate)
            conflict_pending = True
        
        if candidate.semantic_tag not in relation.semantic_tags:
            relation.semantic_tags.append(candidate.semantic_tag)
        
        # 저장
        self.kg_adapter.upsert_relation(relation, tx=tx)
        
        action = DomainAction.TRIGGER_CONFLICT if conflict_pending else DomainAction.UPDATE_EXISTING
        
        logger.info(
            f"Updated dynamic relation: {relation.relation_id}, "
            f"conf: {previous_conf:.3f} -> {relation.domain_conf:.3f}"
        )
        
        return DynamicUpdateResult(
            candidate_id=candidate.candidate_id,
            relation_id=relation.relation_id,
            action=action,
            domain_conf=relation.domain_conf,
            evidence_count=relation.evidence_count,
            decayed=decayed,
            conflict_pending=conflict_pending,
            previous_conf=previous_conf,
            previous_evidence_count=previous_evidence,
        )
    
    def _apply_decay(self, relation: DynamicRelation) -> bool:
        """시간 기반 decay 적용"""
        now = datetime.now()
        days_elapsed = (now - relation.last_update).days
        
        if days_elapsed < self.decay_days:
            return False
        
        decay_periods = days_elapsed // self.decay_days
        decay_factor = self.decay_rate ** decay_periods
        
        relation.domain_conf *= decay_factor
        relation.decay_applied = True
        
        logger.debug(f"Applied decay to {relation.relation_id}: factor={decay_factor:.4f}")
        return True
    
    def _strengthen_relation(
        self,
        relation: DynamicRelation,
        candidate: DomainCandidate,
    ) -> DynamicRelation:
        """관계 강화 (동일 sign)"""
        relation.evidence_count += 1
        relation.last_update = datetime.now()
        
        increase = self.conf_increase_rate / math.sqrt(relation.evidence_count)
        relation.domain_conf = min(0.95, relation.domain_conf + increase)
        
        return relation
    
    def _weaken_relation(
        self,
        relation: DynamicRelation,
        candidate: DomainCandidate,
    ) -> DynamicRelation:
        """관계 약화 (반대 sign)"""
        relation.conflict_count += 1
        relation.last_update = datetime.now()
        relation.need_conflict_resolution = True
        
        relation.domain_conf = max(0.1, relation.domain_conf - self.conf_decrease_rate)
        
        return relation
    
    def get_relation(self, relation_id: str) -> Optional[DynamicRelation]:
        """ID로 관계 조회"""
        return self.kg_adapter.get_relation_by_id(relation_id)
    
    def get_relation_by_key(
        self,
        head_id: str,
        tail_id: str,
        relation_type: str,
    ) -> Optional[DynamicRelation]:
        """키로 관계 조회"""
        return self.kg_adapter.get_relation(head_id, tail_id, relation_type)
    
    def get_all_relations(self) -> Dict[str, DynamicRelation]:
        """모든 관계 반환"""
        return self.kg_adapter.get_all_relations()
    
    def get_relations_for_entity(self, entity_id: str) -> list:
        """특정 엔티티와 관련된 모든 관계"""
        # 임시: Adapter가 이 기능을 직접 제공하지 않으면 전체 스캔 혹은 추후 get_neighbors 활용
        # 여기서는 get_neighbors 활용이 더 효율적
        neighbors = self.kg_adapter.get_neighbors(entity_id)
        # neighbors는 Dict 리스트이므로 DynamicRelation으로 변환 필요하지만
        # 현재는 단순히 get_all_relations 필터링으로 구현 (정확성 위해)
        all_rels = self.kg_adapter.get_all_relations()
        return [
            rel for rel in all_rels.values()
            if rel.head_id == entity_id or rel.tail_id == entity_id
        ]
