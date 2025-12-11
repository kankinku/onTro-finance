"""
Domain KG Adapter
DynamicDomainUpdate를 GraphRepository와 연결하는 어댑터.
기존 인터페이스 유지하면서 영속성 레이어 추가.
"""
import json
import logging
from typing import Dict, Optional, List
from datetime import datetime
from pathlib import Path

from config.settings import get_settings
from src.storage.graph_repository import GraphRepository
from src.storage.transaction_manager import KGTransactionManager, Transaction
from src.domain.models import DynamicRelation, DomainCandidate

logger = logging.getLogger(__name__)


class DomainKGAdapter:
    """
    Domain KG Adapter (Read-Only Runtime)
    
    - Domain Data는 'data/domain/'의 정적 파일(entities.json, relations.json)에서 로드됨.
    - 런타임에는 원칙적으로 Read-Only.
    - 예외: Offline Learning 파이프라인이 update를 호출할 때 force=True 사용.
    """
    
    # Neo4j 라벨
    ENTITY_LABEL = "DomainEntity"
    RELATION_NS = "domain"
    
    def __init__(
        self,
        repository: GraphRepository,
        tx_manager: Optional[KGTransactionManager] = None,
        read_only: bool = True,
    ):
        self._repo = repository
        self._tx_manager = tx_manager or KGTransactionManager(repository)
        self._settings = get_settings()
        self._read_only = read_only
        
    def load_domain_data(self) -> None:
        """
        시스템 시작 시 Domain Data 로드 (Bootstrap)
        data/domain/entities.json, relations.json 읽어서 Graph에 적재
        """
        domain_path = self._settings.store.domain_data_path
        entities_file = domain_path / "entities.json"
        relations_file = domain_path / "relations.json"
        
        if not domain_path.exists():
            logger.warning(f"Domain data directory not found: {domain_path}")
            return

        # 1. Load Entities
        if entities_file.exists():
            try:
                with open(entities_file, 'r', encoding='utf-8') as f:
                    entities = json.load(f)
                    count = 0
                    for ent in entities:
                        # ent structure: {"id": "...", "props": {...}}
                        eid = ent.get("id")
                        props = ent.get("props", {})
                        if eid:
                            self._repo.upsert_entity(eid, [self.ENTITY_LABEL], props)
                            count += 1
                    logger.info(f"Loaded {count} domain entities from {entities_file}")
            except Exception as e:
                logger.error(f"Failed to load entities from {entities_file}: {e}")
        else:
            logger.warning(f"Domain entities file not found: {entities_file}")

        # 2. Load Relations
        if relations_file.exists():
            try:
                with open(relations_file, 'r', encoding='utf-8') as f:
                    relations = json.load(f)
                    count = 0
                    for rel in relations:
                        # rel structure: {"head_id": "...", "tail_id": "...", "type": "...", "props": {...}}
                        src = rel.get("head_id")
                        dst = rel.get("tail_id")
                        rtype = rel.get("type")
                        props = rel.get("props", {})
                        
                        # Add required internal props if missing
                        if "relation_id" not in props:
                            props["relation_id"] = f"{src}_{rtype}_{dst}"
                        
                        if src and dst and rtype:
                            # Scope relation type
                            scoped_type = f"{self.RELATION_NS}:{rtype}"
                            self._repo.upsert_relation(src, scoped_type, dst, props)
                            count += 1
                    logger.info(f"Loaded {count} domain relations from {relations_file}")
            except Exception as e:
                logger.error(f"Failed to load relations from {relations_file}: {e}")
        else:
            logger.warning(f"Domain relations file not found: {relations_file}")

    
    def upsert_relation(
        self,
        relation: DynamicRelation,
        tx: Optional[Transaction] = None,
        force: bool = False,
    ) -> None:
        """관계 저장/업데이트. (Runtime Read-Only Check)"""
        
        if self._read_only and not force:
            logger.warning(f"Blocked attempt to modify Domain KG (Read-Only): {relation.relation_id}")
            return

        # 엔티티 먼저 upsert
        head_props = {"name": relation.head_name, "type": "entity"}
        tail_props = {"name": relation.tail_name, "type": "entity"}
        
        # 관계 props
        rel_props = {
            "relation_id": relation.relation_id,
            "sign": relation.sign,
            "domain_conf": relation.domain_conf,
            "evidence_count": relation.evidence_count,
            "conflict_count": relation.conflict_count,
            "origin": relation.origin,
            "created_at": relation.created_at.isoformat(),
            "last_update": relation.last_update.isoformat(),
            "drift_flag": relation.drift_flag,
            "semantic_tags": ",".join(relation.semantic_tags),
        }
        
        scoped_type = f"{self.RELATION_NS}:{relation.relation_type}"

        if tx:
            # 트랜잭션 내에서
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
            # 직접 저장
            self._repo.upsert_entity(relation.head_id, [self.ENTITY_LABEL], head_props)
            self._repo.upsert_entity(relation.tail_id, [self.ENTITY_LABEL], tail_props)
            self._repo.upsert_relation(
                relation.head_id, scoped_type,
                relation.tail_id, rel_props
            )
        
        logger.debug(f"Upserted domain relation: {relation.relation_id}")
    
    def get_relation(
        self,
        head_id: str,
        tail_id: str,
        relation_type: str,
    ) -> Optional[DynamicRelation]:
        """관계 조회"""
        scoped_type = f"{self.RELATION_NS}:{relation_type}"
        rel = self._repo.get_relation(head_id, scoped_type, tail_id)
        if not rel:
            return None
        
        return self._props_to_relation(
            head_id, tail_id, relation_type, rel.get("props", {})
        )
    
    def get_relation_by_id(self, relation_id: str) -> Optional[DynamicRelation]:
        """ID로 관계 조회"""
        # 모든 관계에서 검색 (비효율적, 인덱스 필요)
        all_rels = self._repo.get_all_relations()
        for rel in all_rels:
            # Filter for domain relations
            if not rel["rel_type"].startswith(f"{self.RELATION_NS}:"):
                continue
                
            if rel.get("props", {}).get("relation_id") == relation_id:
                # Unscope type
                rtype = rel["rel_type"].split(":", 1)[1]
                return self._props_to_relation(
                    rel["src_id"], rel["dst_id"], rtype,
                    rel.get("props", {})
                )
        return None
    
    def get_all_relations(self) -> Dict[str, DynamicRelation]:
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
    
    def get_neighbors(self, entity_id: str, direction: str = "out") -> List[Dict]:
        """이웃 조회 (Wrapper needed to filter or unscope types?)"""
        # Repo returns raw types. We should filter?
        # For now, return raw, but maybe consuming service expects scoped?
        # Let's clean up types if they match domain
        neighbors = self._repo.get_neighbors(entity_id, direction=direction)
        prefix = f"{self.RELATION_NS}:"
        filtered = []
        for n in neighbors:
            if n["rel_type"].startswith(prefix):
                n["rel_type"] = n["rel_type"].split(":", 1)[1]
                filtered.append(n)
        return filtered
    
    def delete_relation(
        self,
        head_id: str,
        tail_id: str,
        relation_type: str,
        tx: Optional[Transaction] = None,
        force: bool = False,
    ) -> bool:
        """관계 삭제 (Read-Only Check)"""
        if self._read_only and not force:
            logger.warning(f"Blocked attempt to delete Domain relation (Read-Only)")
            return False

        scoped_type = f"{self.RELATION_NS}:{relation_type}"
        if tx:
            return self._tx_manager.delete_relation(tx, head_id, scoped_type, tail_id)
        return self._repo.delete_relation(head_id, scoped_type, tail_id)
    
    def _props_to_relation(
        self,
        head_id: str,
        tail_id: str,
        relation_type: str,
        props: Dict,
    ) -> DynamicRelation:
        """props를 DynamicRelation으로 변환"""
        # 엔티티 이름 조회
        head_entity = self._repo.get_entity(head_id)
        tail_entity = self._repo.get_entity(tail_id)
        
        head_name = head_entity.get("props", {}).get("name", head_id) if head_entity else head_id
        tail_name = tail_entity.get("props", {}).get("name", tail_id) if tail_entity else tail_id
        
        semantic_tags = props.get("semantic_tags", "")
        if isinstance(semantic_tags, str):
            semantic_tags = semantic_tags.split(",") if semantic_tags else []
        
        return DynamicRelation(
            relation_id=props.get("relation_id", ""),
            head_id=head_id,
            head_name=head_name,
            tail_id=tail_id,
            tail_name=tail_name,
            relation_type=relation_type,
            sign=props.get("sign", "+"),
            domain_conf=float(props.get("domain_conf", 0.5)),
            evidence_count=int(props.get("evidence_count", 1)),
            conflict_count=int(props.get("conflict_count", 0)),
            origin=props.get("origin", "unknown"),
            drift_flag=bool(props.get("drift_flag", False)),
            semantic_tags=semantic_tags,
        )
    
    def with_transaction(self):
        """트랜잭션 컨텍스트"""
        return self._tx_manager.transaction()
    
    def get_stats(self) -> Dict:
        """통계"""
        return {
            "total_relations": self._repo.count_relations(),
            "total_entities": self._repo.count_entities(),
        }
