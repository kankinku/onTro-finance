"""
Neo4j Graph Repository
프로덕션용 GraphDB 백엔드.
"""
from typing import Any, Dict, List, Optional
import logging

from src.storage.graph_repository import GraphRepository

logger = logging.getLogger(__name__)


class Neo4jGraphRepository(GraphRepository):
    """Neo4j 구현"""
    
    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j"):
        try:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(uri, auth=(user, password))
            self._database = database
            logger.info(f"Connected to Neo4j: {uri}")
        except ImportError:
            raise ImportError("neo4j package required. Install: pip install neo4j")
        except Exception as e:
            raise ConnectionError(f"Failed to connect Neo4j: {e}")
    
    def close(self) -> None:
        if self._driver:
            self._driver.close()
    
    def _run_query(self, query: str, **params) -> List[Dict]:
        with self._driver.session(database=self._database) as session:
            result = session.run(query, **params)
            return [dict(record) for record in result]
    
    def _run_write(self, query: str, **params) -> None:
        with self._driver.session(database=self._database) as session:
            session.run(query, **params)
    
    def upsert_entity(
        self,
        entity_id: str,
        labels: List[str],
        props: Dict[str, Any],
    ) -> None:
        label_str = ":".join(labels) if labels else "Entity"
        query = f"""
        MERGE (n:{label_str} {{id: $id}})
        SET n += $props
        """
        self._run_write(query, id=entity_id, props=props)
    
    def upsert_relation(
        self,
        src_id: str,
        rel_type: str,
        dst_id: str,
        props: Dict[str, Any],
    ) -> None:
        query = f"""
        MATCH (s {{id: $src_id}})
        MATCH (d {{id: $dst_id}})
        MERGE (s)-[r:{rel_type}]->(d)
        SET r += $props
        """
        self._run_write(query, src_id=src_id, dst_id=dst_id, props=props)
    
    def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        query = """
        MATCH (n {id: $id})
        RETURN n, labels(n) AS labels
        """
        results = self._run_query(query, id=entity_id)
        if not results:
            return None
        
        record = results[0]
        node = dict(record["n"])
        return {
            "id": entity_id,
            "labels": record["labels"],
            "props": {k: v for k, v in node.items() if k != "id"},
        }
    
    def get_relation(
        self,
        src_id: str,
        rel_type: str,
        dst_id: str,
    ) -> Optional[Dict[str, Any]]:
        query = f"""
        MATCH (s {{id: $src_id}})-[r:{rel_type}]->(d {{id: $dst_id}})
        RETURN r, type(r) AS rel_type
        """
        results = self._run_query(query, src_id=src_id, dst_id=dst_id)
        if not results:
            return None
        
        record = results[0]
        return {
            "src_id": src_id,
            "rel_type": rel_type,
            "dst_id": dst_id,
            "props": dict(record["r"]),
        }
    
    def get_neighbors(
        self,
        entity_id: str,
        rel_type: Optional[str] = None,
        direction: str = "out",
    ) -> List[Dict[str, Any]]:
        rel_filter = f":{rel_type}" if rel_type else ""
        
        if direction == "out":
            query = f"""
            MATCH (n {{id: $id}})-[r{rel_filter}]->(m)
            RETURN type(r) AS rel_type, m.id AS other_id, r AS props, 'out' AS direction
            """
        elif direction == "in":
            query = f"""
            MATCH (n {{id: $id}})<-[r{rel_filter}]-(m)
            RETURN type(r) AS rel_type, m.id AS other_id, r AS props, 'in' AS direction
            """
        else:  # both
            query = f"""
            MATCH (n {{id: $id}})-[r{rel_filter}]-(m)
            RETURN type(r) AS rel_type, m.id AS other_id, r AS props,
                   CASE WHEN startNode(r) = n THEN 'out' ELSE 'in' END AS direction
            """
        
        results = self._run_query(query, id=entity_id)
        return [
            {
                "rel_type": r["rel_type"],
                "other_id": r["other_id"],
                "direction": r["direction"],
                "props": dict(r["props"]) if r["props"] else {},
            }
            for r in results
        ]
    
    def get_all_entities(self) -> List[Dict[str, Any]]:
        query = """
        MATCH (n)
        WHERE n.id IS NOT NULL
        RETURN n.id AS id, labels(n) AS labels, n AS node
        """
        results = self._run_query(query)
        return [
            {
                "id": r["id"],
                "labels": r["labels"],
                "props": {k: v for k, v in dict(r["node"]).items() if k != "id"},
            }
            for r in results
        ]
    
    def get_all_relations(self) -> List[Dict[str, Any]]:
        query = """
        MATCH (s)-[r]->(d)
        WHERE s.id IS NOT NULL AND d.id IS NOT NULL
        RETURN s.id AS src_id, type(r) AS rel_type, d.id AS dst_id, r AS props
        """
        results = self._run_query(query)
        return [
            {
                "src_id": r["src_id"],
                "rel_type": r["rel_type"],
                "dst_id": r["dst_id"],
                "props": dict(r["props"]) if r["props"] else {},
            }
            for r in results
        ]
    
    def delete_entity(self, entity_id: str) -> bool:
        # 존재 확인
        check = self._run_query("MATCH (n {id: $id}) RETURN n", id=entity_id)
        if not check:
            return False
        
        # DETACH DELETE (연결된 관계도 함께 삭제)
        self._run_write("MATCH (n {id: $id}) DETACH DELETE n", id=entity_id)
        return True
    
    def delete_relation(
        self,
        src_id: str,
        rel_type: str,
        dst_id: str,
    ) -> bool:
        query = f"""
        MATCH (s {{id: $src_id}})-[r:{rel_type}]->(d {{id: $dst_id}})
        DELETE r
        RETURN count(r) AS deleted
        """
        results = self._run_query(query, src_id=src_id, dst_id=dst_id)
        return results[0]["deleted"] > 0 if results else False
    
    def clear(self) -> None:
        self._run_write("MATCH (n) DETACH DELETE n")
    
    def count_entities(self) -> int:
        results = self._run_query("MATCH (n) WHERE n.id IS NOT NULL RETURN count(n) AS cnt")
        return results[0]["cnt"] if results else 0
    
    def count_relations(self) -> int:
        results = self._run_query("MATCH ()-[r]->() RETURN count(r) AS cnt")
        return results[0]["cnt"] if results else 0
