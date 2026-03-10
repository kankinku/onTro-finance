"""Read models for the internal operations console."""
from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional, Tuple

from src.learning.event_store import LearningEventStore
from src.storage.graph_repository import GraphRepository


def _entity_kind(labels: List[str], relation_types: Optional[List[str]] = None) -> str:
    if "DomainEntity" in labels:
        return "domain"
    if "PersonalEntity" in labels:
        return "personal"
    if relation_types:
        if any(item.startswith("domain:") for item in relation_types):
            return "domain"
        if any(item.startswith("personal:") for item in relation_types):
            return "personal"
    return "graph"


def _relation_type_name(raw_type: str) -> Tuple[str, str]:
    if ":" not in raw_type:
        return ("graph", raw_type)
    namespace, relation_type = raw_type.split(":", 1)
    return (namespace, relation_type)


def _node_payload(entity: Dict[str, Any], relation_types: Optional[List[str]] = None) -> Dict[str, Any]:
    labels = list(entity.get("labels", []))
    props = dict(entity.get("props", {}))
    return {
        "id": entity["id"],
        "label": props.get("name") or entity["id"],
        "kind": _entity_kind(labels, relation_types=relation_types),
        "meta": {
            "labels": labels,
            "type": props.get("type"),
            **props,
        },
    }


def _edge_payload(
    edge_id: str,
    source_id: str,
    target_id: str,
    rel_type: str,
    props: Dict[str, Any],
) -> Dict[str, Any]:
    namespace, relation_type = _relation_type_name(rel_type)
    confidence = props.get("domain_conf", props.get("pcs_score", props.get("personal_weight")))
    return {
        "id": edge_id,
        "source": source_id,
        "target": target_id,
        "type": relation_type,
        "sign": props.get("sign", "unknown"),
        "confidence": confidence,
        "origin": props.get("origin", namespace),
        "meta": {
            "namespace": namespace,
            **props,
        },
    }


def build_dashboard_summary(status_payload: Dict[str, Any], event_store: Optional[LearningEventStore]) -> Dict[str, Any]:
    recent_ingests = list_ingests(event_store=event_store, limit=5)["items"]
    return {
        "status": status_payload["status"],
        "ready": status_payload["ready"],
        "totals": {
            "entities": status_payload["entity_count"],
            "relations": status_payload["relation_count"],
            "ingests": event_store.count("ingest") if event_store else 0,
            "edges": status_payload["edge_count"],
            "domain_relations": status_payload["domain_relation_count"],
            "personal_relations": status_payload["personal_relation_count"],
            "council_pending": status_payload["council_pending"],
            "council_closed": status_payload["council_closed"],
        },
        "system": {
            "storage_backend": status_payload["storage_backend"],
            "storage_ok": status_payload["storage_ok"],
            "llm_available": status_payload["llm_available"],
            "council_worker_active": status_payload["council_worker_active"],
            "last_council_run": status_payload["last_council_run"],
            "council_last_error": status_payload["council_last_error"],
        },
        "recent_ingests": recent_ingests,
        "event_backlog": status_payload.get("learning_event_backlog", {}),
    }


def list_ingests(event_store: Optional[LearningEventStore], limit: int = 20) -> Dict[str, Any]:
    if event_store is None:
        return {"items": [], "count": 0}

    rows = list(reversed(event_store.read("ingest")))[: max(limit, 1)]
    items = [
        {
            "doc_id": row.get("doc_id"),
            "input_type": row.get("input_type"),
            "filename": row.get("filename"),
            "logged_at": row.get("logged_at"),
            "edge_count": row.get("edge_count", 0),
            "destinations": row.get("destinations", {}),
            "council_case_ids": row.get("council_case_ids", []),
            "metadata": row.get("metadata", {}),
            "text_preview": row.get("text_preview"),
        }
        for row in rows
    ]
    return {"items": items, "count": len(items)}


def get_ingest_detail(event_store: Optional[LearningEventStore], doc_id: str) -> Optional[Dict[str, Any]]:
    if event_store is None:
        return None

    for row in reversed(event_store.read("ingest")):
        if row.get("doc_id") != doc_id:
            continue
        return {
            "doc_id": row.get("doc_id"),
            "input_type": row.get("input_type"),
            "filename": row.get("filename"),
            "logged_at": row.get("logged_at"),
            "metadata": row.get("metadata", {}),
            "edge_count": row.get("edge_count", 0),
            "destinations": row.get("destinations", {}),
            "council_case_ids": row.get("council_case_ids", []),
            "text_preview": row.get("text_preview"),
        }
    return None


def list_entities(repository: GraphRepository, q: Optional[str] = None, entity_type: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
    query = (q or "").strip().lower()
    entity_type_filter = (entity_type or "").strip().lower()
    items: List[Dict[str, Any]] = []

    for entity in repository.get_all_entities():
        props = dict(entity.get("props", {}))
        label = props.get("name") or entity["id"]
        labels = list(entity.get("labels", []))
        prop_type = str(props.get("type") or "").lower()

        if query and query not in entity["id"].lower() and query not in label.lower():
            continue
        if entity_type_filter and entity_type_filter != prop_type:
            continue

        items.append(
            {
                "id": entity["id"],
                "label": label,
                "kind": _entity_kind(labels),
                "entity_type": props.get("type"),
                "meta": {
                    "labels": labels,
                    **props,
                },
            }
        )

    items.sort(key=lambda item: item["label"].lower())
    return {"items": items[: max(limit, 1)], "count": len(items)}


def get_entity_detail(repository: GraphRepository, entity_id: str) -> Optional[Dict[str, Any]]:
    entity = repository.get_entity(entity_id)
    if entity is None:
        return None

    neighbors_raw = repository.get_neighbors(entity_id, direction="both")
    relation_types = [item["rel_type"] for item in neighbors_raw]
    neighbor_items = []
    for item in neighbors_raw:
        other_entity = repository.get_entity(item["other_id"])
        other_label = item["other_id"]
        other_kind = "graph"
        if other_entity is not None:
            other_label = other_entity.get("props", {}).get("name") or item["other_id"]
            other_kind = _entity_kind(list(other_entity.get("labels", [])))

        namespace, relation_type = _relation_type_name(item["rel_type"])
        props = dict(item.get("props", {}))
        neighbor_items.append(
            {
                "other_id": item["other_id"],
                "other_label": other_label,
                "other_kind": other_kind,
                "direction": item["direction"],
                "relation_type": relation_type,
                "sign": props.get("sign", "unknown"),
                "confidence": props.get("domain_conf", props.get("pcs_score", props.get("personal_weight"))),
                "origin": props.get("origin", namespace),
                "meta": props,
            }
        )

    return {
        "entity": _node_payload(entity, relation_types=relation_types),
        "neighbors": neighbor_items,
    }


def get_graph(repository: GraphRepository, root_entity_id: str, depth: int = 1, limit: int = 50) -> Dict[str, Any]:
    root_entity = repository.get_entity(root_entity_id)
    if root_entity is None:
        return {"nodes": [], "edges": []}

    visited_nodes = {root_entity_id}
    node_map = {root_entity_id: _node_payload(root_entity)}
    edge_map: Dict[str, Dict[str, Any]] = {}
    queue = deque([(root_entity_id, 0)])

    while queue and len(edge_map) < limit:
        current_id, level = queue.popleft()
        if level >= max(depth, 0):
            continue

        neighbors = repository.get_neighbors(current_id, direction="both")
        for neighbor in neighbors:
            if len(edge_map) >= limit:
                break

            other_id = neighbor["other_id"]
            other_entity = repository.get_entity(other_id)
            if other_entity is None:
                continue

            if other_id not in node_map:
                node_map[other_id] = _node_payload(other_entity)

            if neighbor["direction"] == "out":
                source_id = current_id
                target_id = other_id
            else:
                source_id = other_id
                target_id = current_id

            raw_type = neighbor["rel_type"]
            edge_id = f"{source_id}|{raw_type}|{target_id}"
            if edge_id not in edge_map:
                edge_map[edge_id] = _edge_payload(
                    edge_id=edge_id,
                    source_id=source_id,
                    target_id=target_id,
                    rel_type=raw_type,
                    props=dict(neighbor.get("props", {})),
                )

            if other_id not in visited_nodes:
                visited_nodes.add(other_id)
                queue.append((other_id, level + 1))

    return {
        "nodes": list(node_map.values()),
        "edges": list(edge_map.values()),
    }
