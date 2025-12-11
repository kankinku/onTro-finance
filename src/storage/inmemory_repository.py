"""
In-Memory Graph Repository
기존 Dict 기반 구현을 인터페이스에 맞춰 감싼 것.
테스트/개발용.
"""
from typing import Any, Dict, List, Optional
from collections import defaultdict

from src.storage.graph_repository import GraphRepository


class InMemoryGraphRepository(GraphRepository):
    """In-Memory 구현 (Dict 기반)"""
    
    def __init__(self) -> None:
        # entity_id -> {labels: [], props: {}}
        self._entities: Dict[str, Dict[str, Any]] = {}
        
        # (src_id, rel_type, dst_id) -> props
        self._relations: Dict[tuple, Dict[str, Any]] = {}
        
        # 인덱스: src_id -> [(rel_type, dst_id)]
        self._edges_out: Dict[str, List[tuple]] = defaultdict(list)
        
        # 인덱스: dst_id -> [(rel_type, src_id)]
        self._edges_in: Dict[str, List[tuple]] = defaultdict(list)
    
    def upsert_entity(
        self,
        entity_id: str,
        labels: List[str],
        props: Dict[str, Any],
    ) -> None:
        if entity_id in self._entities:
            # 기존 props 병합
            existing = self._entities[entity_id]
            existing["labels"] = labels
            existing["props"].update(props)
        else:
            self._entities[entity_id] = {
                "id": entity_id,
                "labels": labels,
                "props": props.copy(),
            }
    
    def upsert_relation(
        self,
        src_id: str,
        rel_type: str,
        dst_id: str,
        props: Dict[str, Any],
    ) -> None:
        key = (src_id, rel_type, dst_id)
        
        if key in self._relations:
            # 기존 props 병합
            self._relations[key].update(props)
        else:
            self._relations[key] = props.copy()
            self._edges_out[src_id].append((rel_type, dst_id))
            self._edges_in[dst_id].append((rel_type, src_id))
    
    def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        return self._entities.get(entity_id)
    
    def get_relation(
        self,
        src_id: str,
        rel_type: str,
        dst_id: str,
    ) -> Optional[Dict[str, Any]]:
        key = (src_id, rel_type, dst_id)
        props = self._relations.get(key)
        if props is None:
            return None
        return {
            "src_id": src_id,
            "rel_type": rel_type,
            "dst_id": dst_id,
            "props": props,
        }
    
    def get_neighbors(
        self,
        entity_id: str,
        rel_type: Optional[str] = None,
        direction: str = "out",
    ) -> List[Dict[str, Any]]:
        results = []
        
        if direction in ("out", "both"):
            for r_type, dst_id in self._edges_out.get(entity_id, []):
                if rel_type is not None and rel_type != r_type:
                    continue
                key = (entity_id, r_type, dst_id)
                results.append({
                    "rel_type": r_type,
                    "other_id": dst_id,
                    "direction": "out",
                    "props": self._relations.get(key, {}),
                })
        
        if direction in ("in", "both"):
            for r_type, src_id in self._edges_in.get(entity_id, []):
                if rel_type is not None and rel_type != r_type:
                    continue
                key = (src_id, r_type, entity_id)
                results.append({
                    "rel_type": r_type,
                    "other_id": src_id,
                    "direction": "in",
                    "props": self._relations.get(key, {}),
                })
        
        return results
    
    def get_all_entities(self) -> List[Dict[str, Any]]:
        return list(self._entities.values())
    
    def get_all_relations(self) -> List[Dict[str, Any]]:
        results = []
        for (src_id, rel_type, dst_id), props in self._relations.items():
            results.append({
                "src_id": src_id,
                "rel_type": rel_type,
                "dst_id": dst_id,
                "props": props,
            })
        return results
    
    def delete_entity(self, entity_id: str) -> bool:
        if entity_id not in self._entities:
            return False
        
        # 연결된 관계 삭제
        to_remove = []
        for key in self._relations:
            if key[0] == entity_id or key[2] == entity_id:
                to_remove.append(key)
        
        for key in to_remove:
            del self._relations[key]
        
        # 인덱스 정리
        if entity_id in self._edges_out:
            del self._edges_out[entity_id]
        if entity_id in self._edges_in:
            del self._edges_in[entity_id]
        
        # 다른 엔티티의 인덱스에서도 제거
        for eid in list(self._edges_out.keys()):
            self._edges_out[eid] = [
                (r, d) for r, d in self._edges_out[eid] if d != entity_id
            ]
        for eid in list(self._edges_in.keys()):
            self._edges_in[eid] = [
                (r, s) for r, s in self._edges_in[eid] if s != entity_id
            ]
        
        del self._entities[entity_id]
        return True
    
    def delete_relation(
        self,
        src_id: str,
        rel_type: str,
        dst_id: str,
    ) -> bool:
        key = (src_id, rel_type, dst_id)
        if key not in self._relations:
            return False
        
        del self._relations[key]
        
        # 인덱스 정리
        self._edges_out[src_id] = [
            (r, d) for r, d in self._edges_out[src_id]
            if not (r == rel_type and d == dst_id)
        ]
        self._edges_in[dst_id] = [
            (r, s) for r, s in self._edges_in[dst_id]
            if not (r == rel_type and s == src_id)
        ]
        
        return True
    
    def clear(self) -> None:
        self._entities.clear()
        self._relations.clear()
        self._edges_out.clear()
        self._edges_in.clear()
    
    def count_entities(self) -> int:
        return len(self._entities)
    
    def count_relations(self) -> int:
        return len(self._relations)
