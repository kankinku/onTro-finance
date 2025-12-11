"""
Graph Retrieval Module
"Domain을 최우선으로, Personal을 보조로 가져와 reasoning에 필요한 관계들을 수집"

Domain KG → Personal KG 순서로 검색
"""
import logging
from typing import Optional, List, Dict, Set
from collections import deque

from src.reasoning.models import ParsedQuery, RetrievedPath, RetrievalResult
from src.domain.dynamic_update import DynamicDomainUpdate
from src.personal.pkg_update import PersonalKGUpdate

logger = logging.getLogger(__name__)


class GraphRetrieval:
    """
    Graph Retrieval Module
    Domain-first Retrieval
    """
    
    def __init__(
        self,
        domain: Optional[DynamicDomainUpdate] = None,
        personal: Optional[PersonalKGUpdate] = None,
        max_path_length: int = 4,
        max_paths: int = 10,
    ):
        self.domain = domain
        self.personal = personal
        self.max_path_length = max_path_length
        self.max_paths = max_paths
    
    def retrieve(self, parsed_query: ParsedQuery) -> RetrievalResult:
        """
        그래프에서 관련 경로 검색
        
        Args:
            parsed_query: 파싱된 질문
        
        Returns:
            RetrievalResult
        """
        direct_paths = []
        indirect_paths = []
        domain_count = 0
        personal_count = 0
        total_edges = 0
        
        head = parsed_query.head_entity
        tail = parsed_query.tail_entity
        
        if not head:
            return RetrievalResult(
                query_id=parsed_query.query_id,
                direct_paths=[],
                indirect_paths=[],
            )
        
        # Step 1: Direct Edges 검색 (Domain)
        if self.domain and head and tail:
            direct_edge = self.domain.get_relation_by_key(head, tail, "Affect")
            if not direct_edge:
                direct_edge = self.domain.get_relation_by_key(head, tail, "Cause")
            
            if direct_edge:
                path = RetrievedPath(
                    nodes=[head, tail],
                    node_names=[
                        parsed_query.entity_names.get(head, head),
                        parsed_query.entity_names.get(tail, tail),
                    ],
                    edges=[{
                        "relation_id": direct_edge.relation_id,
                        "head": head,
                        "tail": tail,
                        "sign": direct_edge.sign,
                        "domain_conf": direct_edge.domain_conf,
                        "evidence_count": direct_edge.evidence_count,
                        "source": "domain",
                    }],
                    source="domain",
                    path_length=1,
                )
                direct_paths.append(path)
                domain_count += 1
                total_edges += 1
        
        # Step 2: Multi-step Path 검색 (Domain)
        if self.domain and head and tail:
            multi_paths = self._find_paths_bfs(
                start=head,
                end=tail,
                graph=self._build_domain_graph(),
                entity_names=parsed_query.entity_names,
                source="domain",
            )
            for p in multi_paths:
                if p.path_length > 1:
                    indirect_paths.append(p)
                    domain_count += 1
                    total_edges += len(p.edges)
        
        # Step 3: Personal KG 검색 (보조)
        if self.personal and (len(direct_paths) + len(indirect_paths)) < 3:
            personal_paths = self._search_personal(
                head, tail, parsed_query.entity_names
            )
            for p in personal_paths:
                if p.path_length == 1:
                    direct_paths.append(p)
                else:
                    indirect_paths.append(p)
                personal_count += 1
                total_edges += len(p.edges)
        
        result = RetrievalResult(
            query_id=parsed_query.query_id,
            direct_paths=direct_paths,
            indirect_paths=indirect_paths[:self.max_paths],
            domain_paths_count=domain_count,
            personal_paths_count=personal_count,
            total_edges_retrieved=total_edges,
        )
        
        logger.info(
            f"Retrieved: {len(direct_paths)} direct, {len(indirect_paths)} indirect, "
            f"domain={domain_count}, personal={personal_count}"
        )
        
        return result
    
    def _build_domain_graph(self) -> Dict[str, List[Dict]]:
        """Domain 그래프 구조 생성"""
        graph = {}
        
        if not self.domain:
            return graph
        
        for rel in self.domain.get_all_relations().values():
            if rel.head_id not in graph:
                graph[rel.head_id] = []
            
            graph[rel.head_id].append({
                "tail": rel.tail_id,
                "relation_id": rel.relation_id,
                "sign": rel.sign,
                "domain_conf": rel.domain_conf,
                "evidence_count": rel.evidence_count,
                "relation_type": rel.relation_type,
            })
        
        return graph
    
    def _find_paths_bfs(
        self,
        start: str,
        end: str,
        graph: Dict[str, List[Dict]],
        entity_names: Dict[str, str],
        source: str,
    ) -> List[RetrievedPath]:
        """BFS로 경로 탐색"""
        if start == end:
            return []
        
        paths = []
        queue = deque([(start, [start], [])])  # (node, path, edges)
        visited_paths: Set[tuple] = set()
        
        while queue and len(paths) < self.max_paths:
            current, path, edges = queue.popleft()
            
            if len(path) > self.max_path_length:
                continue
            
            for edge_info in graph.get(current, []):
                next_node = edge_info["tail"]
                
                if next_node in path:  # 사이클 방지
                    continue
                
                new_path = path + [next_node]
                new_edges = edges + [{
                    "relation_id": edge_info["relation_id"],
                    "head": current,
                    "tail": next_node,
                    "sign": edge_info["sign"],
                    "domain_conf": edge_info["domain_conf"],
                    "evidence_count": edge_info.get("evidence_count", 1),
                    "source": source,
                }]
                
                if next_node == end:
                    path_key = tuple(new_path)
                    if path_key not in visited_paths:
                        visited_paths.add(path_key)
                        retrieved = RetrievedPath(
                            nodes=new_path,
                            node_names=[entity_names.get(n, n) for n in new_path],
                            edges=new_edges,
                            source=source,
                            path_length=len(new_path) - 1,
                        )
                        paths.append(retrieved)
                else:
                    queue.append((next_node, new_path, new_edges))
        
        return paths
    
    def _search_personal(
        self,
        head: Optional[str],
        tail: Optional[str],
        entity_names: Dict[str, str],
    ) -> List[RetrievedPath]:
        """Personal KG 검색"""
        paths = []
        
        if not self.personal or not head:
            return paths
        
        # Direct edge 검색
        if tail:
            for rel in self.personal.get_all_relations().values():
                if rel.head_id == head and rel.tail_id == tail:
                    path = RetrievedPath(
                        nodes=[head, tail],
                        node_names=[
                            entity_names.get(head, head),
                            entity_names.get(tail, tail),
                        ],
                        edges=[{
                            "relation_id": rel.relation_id,
                            "head": head,
                            "tail": tail,
                            "sign": rel.sign,
                            "pcs_score": rel.pcs_score,
                            "personal_weight": rel.personal_weight,
                            "source": "personal",
                        }],
                        source="personal",
                        path_length=1,
                    )
                    paths.append(path)
        
        return paths[:self.max_paths]
