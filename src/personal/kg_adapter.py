"""
Personal KG Adapter
PersonalKGUpdate를 GraphRepository와 연결하는 어댑터.
"""
import logging
from typing import Dict, Optional, List
from datetime import datetime

from src.storage.graph_repository import GraphRepository
from src.storage.transaction_manager import KGTransactionManager, Transaction
from src.personal.models import PersonalRelation, PersonalLabel, SourceType

logger = logging.getLogger(__name__)


class PersonalKGAdapter:
    """
    Personal KG Adapter
    
    PersonalKGUpdate의 in-memory Dict를 GraphRepository로 대체.
    핵심 원칙: 삭제 없음.
    """
    
    ENTITY_LABEL = "PersonalEntity"
    RELATION_NS = "personal"
    
    def __init__(
        self,
        repository: GraphRepository,
        tx_manager: Optional[KGTransactionManager] = None,
    ):
        self._repo = repository
        self._tx_manager = tx_manager or KGTransactionManager(repository)
    
    def upsert_relation(
        self,
        relation: PersonalRelation,
        tx: Optional[Transaction] = None,
    ) -> None:
        """관계 저장/업데이트 (삭제 없음)"""
        head_props = {"name": relation.head_name, "type": "entity"}
        tail_props = {"name": relation.tail_name, "type": "entity"}
        
        rel_props = {
            "relation_id": relation.relation_id,
            "sign": relation.sign,
            "user_id": relation.user_id,
            "pcs_score": relation.pcs_score,
            "personal_weight": relation.personal_weight,
            "personal_label": relation.personal_label.value,
            "source_type": relation.source_type.value,
            "occurrence_count": relation.occurrence_count,
            "domain_conflict": relation.domain_conflict,
            "domain_conflict_count": relation.domain_conflict_count,
            "promotion_candidate": relation.promotion_candidate,
            "created_at": relation.created_at.isoformat(),
            "last_occurred_at": relation.last_occurred_at.isoformat(),
            "drift_flag": relation.drift_flag,
        }
        
        
        scoped_type = f"{self.RELATION_NS}:{relation.relation_type}"
        
        if tx:
            self._tx_manager.create_entity(
                tx, relation.head_id, [self.ENTITY_LABEL], head_props
            )
            self._tx_manager.create_entity(
                tx, relation.tail_id, [self.ENTITY_LABEL], tail_props
            )
            self._tx_manager.create_relation(
                tx, relation.head_id, scoped_type,
                relation.tail_id, rel_props
            )
        else:
            self._repo.upsert_entity(relation.head_id, [self.ENTITY_LABEL], head_props)
            self._repo.upsert_entity(relation.tail_id, [self.ENTITY_LABEL], tail_props)
            self._repo.upsert_relation(
                relation.head_id, scoped_type,
                relation.tail_id, rel_props
            )
        
        logger.debug(f"Upserted personal relation: {relation.relation_id}")
    
    def get_relation(
        self,
        head_id: str,
        tail_id: str,
        relation_type: str,
    ) -> Optional[PersonalRelation]:
        """관계 조회"""
        scoped_type = f"{self.RELATION_NS}:{relation_type}"
        rel = self._repo.get_relation(head_id, scoped_type, tail_id)
        if not rel:
            return None
        
        return self._props_to_relation(
            head_id, tail_id, relation_type, rel.get("props", {})
        )
    
    def get_all_relations(self) -> Dict[str, PersonalRelation]:
        """모든 관계 조회"""
        result = {}
        all_rels = self._repo.get_all_relations()
        prefix = f"{self.RELATION_NS}:"
        
        for rel in all_rels:
            if not rel["rel_type"].startswith(prefix):
                continue
            
            rtype = rel["rel_type"].split(":", 1)[1]
            props = rel.get("props", {})
            relation_id = props.get("relation_id")
            if relation_id:
                result[relation_id] = self._props_to_relation(
                    rel["src_id"], rel["dst_id"], rtype, props
                )
        
        return result
    
    def _props_to_relation(
        self,
        head_id: str,
        tail_id: str,
        relation_type: str,
        props: Dict,
    ) -> PersonalRelation:
        """props를 PersonalRelation으로 변환"""
        head_entity = self._repo.get_entity(head_id)
        tail_entity = self._repo.get_entity(tail_id)
        
        head_name = head_entity.get("props", {}).get("name", head_id) if head_entity else head_id
        tail_name = tail_entity.get("props", {}).get("name", tail_id) if tail_entity else tail_id
        
        try:
            personal_label = PersonalLabel(props.get("personal_label", "weak_belief"))
        except ValueError:
            personal_label = PersonalLabel.WEAK_BELIEF
        
        try:
            source_type = SourceType(props.get("source_type", "llm_inferred"))
        except ValueError:
            source_type = SourceType.LLM_INFERRED
        
        return PersonalRelation(
            relation_id=props.get("relation_id", ""),
            head_id=head_id,
            head_name=head_name,
            tail_id=tail_id,
            tail_name=tail_name,
            relation_type=relation_type,
            sign=props.get("sign", "+"),
            user_id=props.get("user_id", "default_user"),
            pcs_score=float(props.get("pcs_score", 0.5)),
            personal_weight=float(props.get("personal_weight", 0.5)),
            personal_label=personal_label,
            source_type=source_type,
            occurrence_count=int(props.get("occurrence_count", 1)),
            domain_conflict=bool(props.get("domain_conflict", False)),
            domain_conflict_count=int(props.get("domain_conflict_count", 0)),
            promotion_candidate=bool(props.get("promotion_candidate", False)),
            drift_flag=bool(props.get("drift_flag", False)),
        )
    
    def with_transaction(self):
        """트랜잭션 컨텍스트"""
        return self._tx_manager.transaction()
    
    def get_stats(self) -> Dict:
        """통계"""
        all_rels = self.get_all_relations()
        labels = {"strong": 0, "weak": 0, "noisy": 0}
        
        for rel in all_rels.values():
            if rel.personal_label == PersonalLabel.STRONG_BELIEF:
                labels["strong"] += 1
            elif rel.personal_label == PersonalLabel.WEAK_BELIEF:
                labels["weak"] += 1
            else:
                labels["noisy"] += 1
        
        return {
            "total_relations": len(all_rels),
            "labels": labels,
        }
