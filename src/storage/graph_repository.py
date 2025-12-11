"""
Graph Repository - 추상 인터페이스
KnowledgeGraph가 의존해야 하는 최소 기능 집합.
도메인 로직 없음. 오로지 노드/엣지 CRUD + 간단 질의만.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class GraphRepository(ABC):
    """KnowledgeGraph 저장소 추상 인터페이스"""
    
    @abstractmethod
    def upsert_entity(
        self,
        entity_id: str,
        labels: List[str],
        props: Dict[str, Any],
    ) -> None:
        """엔티티 생성 또는 업데이트"""
        ...
    
    @abstractmethod
    def upsert_relation(
        self,
        src_id: str,
        rel_type: str,
        dst_id: str,
        props: Dict[str, Any],
    ) -> None:
        """관계 생성 또는 업데이트"""
        ...
    
    @abstractmethod
    def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """엔티티 조회"""
        ...
    
    @abstractmethod
    def get_relation(
        self,
        src_id: str,
        rel_type: str,
        dst_id: str,
    ) -> Optional[Dict[str, Any]]:
        """특정 관계 조회"""
        ...
    
    @abstractmethod
    def get_neighbors(
        self,
        entity_id: str,
        rel_type: Optional[str] = None,
        direction: str = "out",
    ) -> List[Dict[str, Any]]:
        """이웃 조회 (out/in/both)"""
        ...
    
    @abstractmethod
    def get_all_entities(self) -> List[Dict[str, Any]]:
        """모든 엔티티 조회"""
        ...
    
    @abstractmethod
    def get_all_relations(self) -> List[Dict[str, Any]]:
        """모든 관계 조회"""
        ...
    
    @abstractmethod
    def delete_entity(self, entity_id: str) -> bool:
        """엔티티 삭제 (연결된 관계도)"""
        ...
    
    @abstractmethod
    def delete_relation(
        self,
        src_id: str,
        rel_type: str,
        dst_id: str,
    ) -> bool:
        """관계 삭제"""
        ...
    
    @abstractmethod
    def clear(self) -> None:
        """전체 초기화"""
        ...
    
    @abstractmethod
    def count_entities(self) -> int:
        """엔티티 수"""
        ...
    
    @abstractmethod
    def count_relations(self) -> int:
        """관계 수"""
        ...
