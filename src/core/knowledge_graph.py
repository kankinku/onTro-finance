import networkx as nx
import json
import os
from typing import List, Optional
from networkx.readwrite import json_graph
from src.schemas.base_models import Relation, Term, PredicateType
from src.core.config import settings
from src.core.logger import logger

class KnowledgeGraph:
    """
    In-memory wrapper for the Ontology Graph with Persistence.
    """
    
    def __init__(self):
        self.graph = nx.DiGraph()
        self.persistence_path = settings.PERSISTENCE_FILE
        self._load_from_disk()

    def add_term(self, term: Term):
        self.graph.add_node(term.term_id, **term.model_dump())

    def add_relation(self, relation: Relation):
        self.graph.add_edge(
            relation.subject_id,
            relation.object_id,
            relation_id=relation.rel_id,
            predicate=relation.predicate,
            conditions=relation.conditions,
            weight=getattr(relation, 'strength', 1.0),
            relation_object=relation.model_dump() # Store as dict for JSON serialization
        )
        # Auto-save on update (Simple strategy for prototype)
        self.save_to_disk()

    def get_downstream_flow(self, start_node_id: str, max_depth: int = 3) -> List[Relation]:
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
                conditions=edge_data.get('conditions', {})
            )
            path_relations.append(rel)
        return path_relations
        
    def save_to_disk(self):
        try:
            data = json_graph.node_link_data(self.graph)
            with open(self.persistence_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"[Graph] Saved {len(self.graph.nodes)} nodes to {self.persistence_path}")
        except Exception as e:
            logger.error(f"[Graph] Save failed: {e}")

    def _load_from_disk(self):
        if os.path.exists(self.persistence_path):
            try:
                with open(self.persistence_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.graph = json_graph.node_link_graph(data, edges="links")
                logger.info(f"[Graph] Loaded {len(self.graph.nodes)} nodes from {self.persistence_path}")
            except Exception as e:
                logger.error(f"[Graph] Load failed: {e}")
                self.graph = nx.DiGraph()
