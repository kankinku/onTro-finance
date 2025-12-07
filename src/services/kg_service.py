"""
Knowledge Graph Service
지식 그래프 관리를 담당하는 서비스 레이어
"""
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
import networkx as nx
from networkx.readwrite import json_graph

from config.settings import settings
from src.core.logger import logger
from src.schemas.base_models import Relation, Term, PredicateType


class KnowledgeGraphService:
    """
    지식 그래프 관리 서비스
    - NetworkX 기반 In-memory 그래프
    - JSON 파일 기반 영속성
    - Thread-safe 접근 (향후 Lock 추가 가능)
    """
    
    def __init__(self, persistence_path: Optional[Path] = None):
        self.graph = nx.DiGraph()
        self.persistence_path = persistence_path or settings.persistence_path
        self._ensure_dirs()
        self._load_from_disk()
        
    def _ensure_dirs(self) -> None:
        """저장 디렉토리 생성"""
        self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
    
    def add_term(self, term: Term) -> None:
        """노드 추가"""
        self.graph.add_node(term.term_id, **term.model_dump())
        
    def add_relation(self, relation: Relation) -> None:
        """엣지 추가 및 자동 저장"""
        self.graph.add_edge(
            relation.subject_id,
            relation.object_id,
            relation_id=relation.rel_id,
            predicate=relation.predicate,
            conditions=relation.conditions,
            weight=relation.strength,
            sign=relation.sign,
            lag_days=relation.lag_days,
            relation_object=relation.model_dump()
        )
        self.save_to_disk()
        
    def get_downstream_flow(
        self, 
        start_node_id: str, 
        max_depth: int = 3
    ) -> List[Relation]:
        """
        시작 노드에서 하류로 연결된 모든 관계 반환
        BFS 기반 탐색
        """
        if start_node_id not in self.graph:
            return []
            
        edges = list(nx.bfs_edges(self.graph, start_node_id, depth_limit=max_depth))
        path_relations = []
        
        for u, v in edges:
            edge_data = self.graph.get_edge_data(u, v)
            rel = Relation(
                rel_id=edge_data.get('relation_id', 'unknown'),
                subject_id=u,
                object_id=v,
                predicate=edge_data.get('predicate', PredicateType.CAUSES),
                conditions=edge_data.get('conditions', {}),
                sign=edge_data.get('sign', 1),
                strength=edge_data.get('weight', 1.0),
                lag_days=edge_data.get('lag_days', 0)
            )
            path_relations.append(rel)
            
        return path_relations
    
    def get_graph_data(self) -> Dict[str, Any]:
        """
        전체 그래프를 시각화용 JSON 형태로 반환
        
        Returns:
            {"nodes": [...], "links": [...]}
        """
        data = json_graph.node_link_data(self.graph)
        return data
    
    def get_node_count(self) -> int:
        return len(self.graph.nodes)
    
    def get_edge_count(self) -> int:
        return len(self.graph.edges)
    
    def save_to_disk(self) -> bool:
        """그래프를 JSON 파일로 저장"""
        try:
            data = json_graph.node_link_data(self.graph)
            with open(self.persistence_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            logger.info(f"[Graph] Saved {len(self.graph.nodes)} nodes to {self.persistence_path}")
            return True
        except Exception as e:
            logger.error(f"[Graph] Save failed: {e}")
            return False
    
    def _load_from_disk(self) -> None:
        """JSON 파일에서 그래프 로드"""
        if not self.persistence_path.exists():
            logger.info("[Graph] No persistence file found. Starting fresh.")
            return
            
        try:
            with open(self.persistence_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.graph = json_graph.node_link_graph(data, edges="links")
            logger.info(f"[Graph] Loaded {len(self.graph.nodes)} nodes from {self.persistence_path}")
        except Exception as e:
            logger.error(f"[Graph] Load failed: {e}")
            self.graph = nx.DiGraph()


# Singleton Instance
kg_service = KnowledgeGraphService()
