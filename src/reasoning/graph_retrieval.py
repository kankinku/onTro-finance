"""
Graph retrieval that preserves configured relation types.
"""
import logging
from collections import deque
from typing import Dict, List, Optional, Set

from src.reasoning.models import ParsedQuery, RetrievedPath, RetrievalResult
from src.domain.dynamic_update import DynamicDomainUpdate
from src.personal.pkg_update import PersonalKGUpdate

logger = logging.getLogger(__name__)


class GraphRetrieval:
    """Retrieve direct and indirect domain/personal paths without hardcoded relation labels."""

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
        direct_paths: List[RetrievedPath] = []
        indirect_paths: List[RetrievedPath] = []
        domain_count = 0
        personal_count = 0
        total_edges = 0

        head = parsed_query.head_entity
        tail = parsed_query.tail_entity
        if not head:
            return RetrievalResult(query_id=parsed_query.query_id, direct_paths=[], indirect_paths=[])

        if self.domain and head and tail:
            direct_domain_paths = self._collect_direct_domain_paths(head, tail, parsed_query.entity_names)
            direct_paths.extend(direct_domain_paths)
            domain_count += len(direct_domain_paths)
            total_edges += len(direct_domain_paths)

            multi_paths = self._find_paths_bfs(
                start=head,
                end=tail,
                graph=self._build_domain_graph(),
                entity_names=parsed_query.entity_names,
                source="domain",
            )
            for path in multi_paths:
                if path.path_length > 1:
                    indirect_paths.append(path)
                    domain_count += 1
                    total_edges += len(path.edges)

        if self.personal and (len(direct_paths) + len(indirect_paths)) < 3:
            personal_paths = self._search_personal(head, tail, parsed_query.entity_names)
            for path in personal_paths:
                if path.path_length == 1:
                    direct_paths.append(path)
                else:
                    indirect_paths.append(path)
                personal_count += 1
                total_edges += len(path.edges)

        result = RetrievalResult(
            query_id=parsed_query.query_id,
            direct_paths=direct_paths,
            indirect_paths=indirect_paths[: self.max_paths],
            domain_paths_count=domain_count,
            personal_paths_count=personal_count,
            total_edges_retrieved=total_edges,
        )
        logger.info(
            "Retrieved: %s direct, %s indirect, domain=%s, personal=%s",
            len(direct_paths),
            len(indirect_paths),
            domain_count,
            personal_count,
        )
        return result

    def _collect_direct_domain_paths(
        self,
        head: str,
        tail: str,
        entity_names: Dict[str, str],
    ) -> List[RetrievedPath]:
        paths: List[RetrievedPath] = []
        if not self.domain:
            return paths

        for relation in self.domain.get_all_relations().values():
            if relation.head_id != head or relation.tail_id != tail:
                continue
            paths.append(
                RetrievedPath(
                    nodes=[head, tail],
                    node_names=[entity_names.get(head, head), entity_names.get(tail, tail)],
                    edges=[
                        {
                            "relation_id": relation.relation_id,
                            "head": head,
                            "tail": tail,
                            "sign": relation.sign,
                            "domain_conf": relation.domain_conf,
                            "evidence_count": relation.evidence_count,
                            "relation_type": relation.relation_type,
                            "source": "domain",
                        }
                    ],
                    source="domain",
                    path_length=1,
                )
            )
        return paths

    def _build_domain_graph(self) -> Dict[str, List[Dict]]:
        graph: Dict[str, List[Dict]] = {}
        if not self.domain:
            return graph

        for relation in self.domain.get_all_relations().values():
            graph.setdefault(relation.head_id, []).append(
                {
                    "tail": relation.tail_id,
                    "relation_id": relation.relation_id,
                    "sign": relation.sign,
                    "domain_conf": relation.domain_conf,
                    "evidence_count": relation.evidence_count,
                    "relation_type": relation.relation_type,
                }
            )
        return graph

    def _find_paths_bfs(
        self,
        start: str,
        end: str,
        graph: Dict[str, List[Dict]],
        entity_names: Dict[str, str],
        source: str,
    ) -> List[RetrievedPath]:
        if start == end:
            return []

        paths: List[RetrievedPath] = []
        queue = deque([(start, [start], [])])
        visited_paths: Set[tuple] = set()

        while queue and len(paths) < self.max_paths:
            current, node_path, edge_path = queue.popleft()
            if len(node_path) > self.max_path_length:
                continue

            for edge_info in graph.get(current, []):
                next_node = edge_info["tail"]
                if next_node in node_path:
                    continue

                new_nodes = node_path + [next_node]
                new_edges = edge_path + [
                    {
                        "relation_id": edge_info["relation_id"],
                        "head": current,
                        "tail": next_node,
                        "sign": edge_info["sign"],
                        "domain_conf": edge_info["domain_conf"],
                        "evidence_count": edge_info.get("evidence_count", 1),
                        "relation_type": edge_info.get("relation_type", "affects"),
                        "source": source,
                    }
                ]

                if next_node == end:
                    path_key = tuple(new_nodes)
                    if path_key in visited_paths:
                        continue
                    visited_paths.add(path_key)
                    paths.append(
                        RetrievedPath(
                            nodes=new_nodes,
                            node_names=[entity_names.get(node, node) for node in new_nodes],
                            edges=new_edges,
                            source=source,
                            path_length=len(new_nodes) - 1,
                        )
                    )
                else:
                    queue.append((next_node, new_nodes, new_edges))

        return paths

    def _search_personal(
        self,
        head: Optional[str],
        tail: Optional[str],
        entity_names: Dict[str, str],
    ) -> List[RetrievedPath]:
        paths: List[RetrievedPath] = []
        if not self.personal or not head:
            return paths

        if tail:
            for relation in self.personal.get_all_relations().values():
                if relation.head_id == head and relation.tail_id == tail:
                    paths.append(
                        RetrievedPath(
                            nodes=[head, tail],
                            node_names=[entity_names.get(head, head), entity_names.get(tail, tail)],
                            edges=[
                                {
                                    "relation_id": relation.relation_id,
                                    "head": head,
                                    "tail": tail,
                                    "sign": relation.sign,
                                    "pcs_score": relation.pcs_score,
                                    "personal_weight": relation.personal_weight,
                                    "relation_type": relation.relation_type,
                                    "source": "personal",
                                }
                            ],
                            source="personal",
                            path_length=1,
                        )
                    )

        return paths[: self.max_paths]
