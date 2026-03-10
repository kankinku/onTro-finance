"""Read models for the internal operations console."""

from __future__ import annotations

from collections import deque
from pathlib import Path
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


def _node_payload(
    entity: Dict[str, Any], relation_types: Optional[List[str]] = None
) -> Dict[str, Any]:
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


def build_dashboard_summary(
    status_payload: Dict[str, Any], event_store: Optional[LearningEventStore]
) -> Dict[str, Any]:
    recent_ingests = list_ingests(event_store=event_store, limit=5)["items"]
    recent_documents = list_documents(event_store=event_store, limit=5)["items"]
    trust_summary = build_trust_summary(event_store)
    learning_products = list_learning_products(event_store, limit=5)
    audit_events = list_audit_events(event_store, limit=5)
    return {
        "status": status_payload["status"],
        "ready": status_payload["ready"],
        "totals": {
            "entities": status_payload["entity_count"],
            "relations": status_payload["relation_count"],
            "ingests": event_store.count("ingest") if event_store else 0,
            "documents": event_store.document_count() if event_store else 0,
            "edges": status_payload["edge_count"],
            "domain_relations": status_payload["domain_relation_count"],
            "personal_relations": status_payload["personal_relation_count"],
            "council_pending": status_payload["council_pending"],
            "council_closed": status_payload["council_closed"],
        },
        "council": {
            "pending": status_payload["council_pending"],
            "closed": status_payload["council_closed"],
            "available_members": status_payload["available_members"],
        },
        "trust": trust_summary,
        "learning": learning_products,
        "audit": audit_events,
        "system": {
            "storage_backend": status_payload["storage_backend"],
            "storage_ok": status_payload["storage_ok"],
            "llm_available": status_payload["llm_available"],
            "council_worker_active": status_payload["council_worker_active"],
            "last_council_run": status_payload["last_council_run"],
            "council_last_error": status_payload["council_last_error"],
        },
        "recent_ingests": recent_ingests,
        "recent_documents": recent_documents,
        "event_backlog": status_payload.get("learning_event_backlog", {}),
    }


def list_audit_events(
    event_store: Optional[LearningEventStore], limit: int = 20, action: Optional[str] = None
) -> Dict[str, Any]:
    if event_store is None:
        return {"items": [], "count": 0}

    rows = event_store.list_audit(limit=None)
    if action:
        action_value = action.strip().lower()
        rows = [row for row in rows if str(row.get("action") or "").lower() == action_value]
    items = rows[: max(limit, 1)]
    return {"items": items, "count": len(items)}


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


def get_ingest_detail(
    event_store: Optional[LearningEventStore], doc_id: str
) -> Optional[Dict[str, Any]]:
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


def list_documents(event_store: Optional[LearningEventStore], limit: int = 20) -> Dict[str, Any]:
    return search_documents(event_store, limit=limit)


def search_documents(
    event_store: Optional[LearningEventStore],
    *,
    q: Optional[str] = None,
    source_type: Optional[str] = None,
    institution: Optional[str] = None,
    region: Optional[str] = None,
    asset_scope: Optional[str] = None,
    document_quality_tier: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    if event_store is None:
        return {"items": [], "count": 0}

    rows = event_store.list_documents(limit=None)
    filtered = _filter_document_rows(
        rows,
        q=q,
        source_type=source_type,
        institution=institution,
        region=region,
        asset_scope=asset_scope,
        document_quality_tier=document_quality_tier,
    )[: max(limit, 1)]
    items = [
        {
            "doc_id": row.get("doc_id"),
            "title": row.get("title"),
            "author": row.get("author"),
            "institution": row.get("institution"),
            "source_type": row.get("source_type"),
            "published_at": row.get("published_at"),
            "language": row.get("language"),
            "region": row.get("region"),
            "asset_scope": row.get("asset_scope"),
            "document_quality_tier": row.get("document_quality_tier"),
            "input_type": row.get("input_type"),
            "edge_count": row.get("edge_count", 0),
            "destinations": row.get("destinations", {}),
            "metadata": row.get("metadata", {}),
            "updated_at": row.get("updated_at"),
        }
        for row in filtered
    ]
    return {"items": items, "count": len(items)}


def get_document_detail(
    event_store: Optional[LearningEventStore], doc_id: str
) -> Optional[Dict[str, Any]]:
    if event_store is None:
        return None

    row = event_store.get_document(doc_id)
    if row is None:
        return None

    validation_events = _document_validation_events(event_store, doc_id)
    council_events = _document_council_events(event_store, doc_id)
    related_relations = _summarize_document_relations(validation_events, council_events)

    return {
        "doc_id": row.get("doc_id"),
        "title": row.get("title"),
        "author": row.get("author"),
        "institution": row.get("institution"),
        "source_type": row.get("source_type"),
        "published_at": row.get("published_at"),
        "language": row.get("language"),
        "region": row.get("region"),
        "asset_scope": row.get("asset_scope"),
        "document_quality_tier": row.get("document_quality_tier"),
        "input_type": row.get("input_type"),
        "filename": row.get("filename"),
        "edge_count": row.get("edge_count", 0),
        "destinations": row.get("destinations", {}),
        "council_case_ids": row.get("council_case_ids", []),
        "text_preview": row.get("text_preview"),
        "metadata": row.get("metadata", {}),
        "consolidated_relations": row.get("consolidated_relations", []),
        "related_relations": related_relations,
        "evidence": {
            "validation_events": validation_events,
            "council_events": council_events,
            "counts": {
                "validation": len(validation_events),
                "council": len(council_events),
                "unique_relations": len(related_relations),
            },
        },
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def get_document_structure(
    event_store: Optional[LearningEventStore], doc_id: str
) -> Optional[Dict[str, Any]]:
    if event_store is None:
        return None
    row = event_store.get_document(doc_id)
    if row is None:
        return None

    metadata = dict(row.get("metadata", {}))
    pdf_blocks = (
        metadata.get("pdf_blocks", []) if isinstance(metadata.get("pdf_blocks"), list) else []
    )
    structured_sections = (
        metadata.get("structured_sections", [])
        if isinstance(metadata.get("structured_sections"), list)
        else []
    )
    ocr_needed_pages = [
        block.get("page_number")
        for block in pdf_blocks
        if isinstance(block, dict) and block.get("ocr_required")
    ]
    table_blocks = [
        {
            "page_number": block.get("page_number"),
            "caption": block.get("table_caption"),
            "rows": block.get("table_rows"),
            "columns": block.get("table_columns"),
        }
        for block in pdf_blocks
        if isinstance(block, dict) and block.get("block_type") == "table"
    ]
    return {
        "doc_id": doc_id,
        "structured_sections": structured_sections,
        "pdf_blocks": pdf_blocks,
        "ocr_needed_pages": [page for page in ocr_needed_pages if page is not None],
        "table_blocks": table_blocks,
        "consolidated_relations": row.get("consolidated_relations", []),
    }


def get_document_graph(
    repository: GraphRepository, event_store: Optional[LearningEventStore], doc_id: str
) -> Dict[str, Any]:
    detail = get_document_detail(event_store, doc_id)
    if detail is None:
        return {"nodes": [], "edges": []}

    node_map: Dict[str, Dict[str, Any]] = {}
    edge_map: Dict[str, Dict[str, Any]] = {}

    for relation in detail.get("related_relations", []):
        head_id = str(relation.get("head_entity_id") or "")
        tail_id = str(relation.get("tail_entity_id") or "")
        relation_type = str(relation.get("relation_type") or "")
        if not head_id or not tail_id or not relation_type:
            continue

        for entity_id in (head_id, tail_id):
            entity = repository.get_entity(entity_id)
            if entity is not None:
                node_map[entity_id] = _node_payload(entity)
            elif entity_id not in node_map:
                node_map[entity_id] = {
                    "id": entity_id,
                    "label": entity_id,
                    "kind": "document",
                    "meta": {"missing_from_graph": True},
                }

        raw_rel_type = relation_type if ":" in relation_type else f"domain:{relation_type}"
        graph_relation = repository.get_relation(head_id, raw_rel_type, tail_id)
        edge_id = f"{head_id}|{raw_rel_type}|{tail_id}"
        if graph_relation is not None:
            edge_map[edge_id] = _edge_payload(
                edge_id=edge_id,
                source_id=head_id,
                target_id=tail_id,
                rel_type=raw_rel_type,
                props=dict(graph_relation.get("props", {})),
            )
        else:
            edge_map[edge_id] = {
                "id": edge_id,
                "source": head_id,
                "target": tail_id,
                "type": relation_type,
                "sign": None,
                "confidence": relation.get("max_confidence"),
                "origin": "document_summary",
                "meta": {
                    "page_numbers": relation.get("page_numbers", []),
                    "chapter_titles": relation.get("chapter_titles", []),
                    "section_titles": relation.get("section_titles", []),
                    "evidence_count": relation.get("evidence_count", 0),
                },
            }

    return {"nodes": list(node_map.values()), "edges": list(edge_map.values())}


def _document_validation_events(
    event_store: LearningEventStore, doc_id: str
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for row in event_store.read("validation"):
        if row.get("source_document_id") != doc_id:
            continue
        items.append(
            {
                "edge_id": row.get("edge_id"),
                "fragment_id": row.get("fragment_id"),
                "fragment_text": row.get("fragment_text"),
                "citation_page_number": row.get("citation_page_number"),
                "citation_chapter_title": row.get("citation_chapter_title"),
                "citation_section_title": row.get("citation_section_title"),
                "head_entity_id": row.get("head_entity_id"),
                "tail_entity_id": row.get("tail_entity_id"),
                "relation_type": row.get("relation_type"),
                "destination": row.get("destination"),
                "combined_conf": row.get("combined_conf"),
                "polarity_guess": row.get("polarity_guess"),
                "semantic_tag": row.get("semantic_tag"),
                "time_scope": row.get("time_scope"),
                "published_at": row.get("published_at"),
                "logged_at": row.get("logged_at"),
            }
        )
    return list(reversed(items))


def _document_council_events(event_store: LearningEventStore, doc_id: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for event_type in ("council_candidate", "council_final"):
        for row in event_store.read(event_type):
            if row.get("source_document_id") != doc_id:
                continue
            raw_head_entity = row.get("head_entity")
            head_entity: Dict[str, Any] = (
                raw_head_entity if isinstance(raw_head_entity, dict) else {}
            )
            raw_tail_entity = row.get("tail_entity")
            tail_entity: Dict[str, Any] = (
                raw_tail_entity if isinstance(raw_tail_entity, dict) else {}
            )
            raw_citation_span = row.get("citation_span")
            citation_span: Dict[str, Any] = (
                raw_citation_span if isinstance(raw_citation_span, dict) else {}
            )
            items.append(
                {
                    "event_type": event_type,
                    "candidate_id": row.get("candidate_id"),
                    "council_case_id": row.get("council_case_id"),
                    "status": row.get("status"),
                    "head_entity_id": head_entity.get("canonical_id"),
                    "tail_entity_id": tail_entity.get("canonical_id"),
                    "relation_type": row.get("final_relation_type")
                    or row.get("relation_type_candidate"),
                    "confidence": row.get("final_confidence") or row.get("confidence"),
                    "time_scope": row.get("time_scope_candidate"),
                    "citation_page_number": row.get("source_metadata", {}).get("page_number")
                    if isinstance(row.get("source_metadata"), dict)
                    else None,
                    "citation_chapter_title": row.get("source_metadata", {}).get("chapter_title")
                    if isinstance(row.get("source_metadata"), dict)
                    else None,
                    "citation_section_title": row.get("source_metadata", {}).get("section_title")
                    if isinstance(row.get("source_metadata"), dict)
                    else None,
                    "trigger_reasons": row.get("council_trigger_reasons", []),
                    "citation_text": citation_span.get("text"),
                    "logged_at": row.get("updated_at")
                    or row.get("created_at")
                    or row.get("logged_at"),
                }
            )
    return list(reversed(items))


def _summarize_document_relations(
    validation_events: List[Dict[str, Any]], council_events: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    summary: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

    for row in validation_events:
        key = (
            str(row.get("head_entity_id") or ""),
            str(row.get("relation_type") or ""),
            str(row.get("tail_entity_id") or ""),
        )
        item = summary.setdefault(
            key,
            {
                "head_entity_id": row.get("head_entity_id"),
                "relation_type": row.get("relation_type"),
                "tail_entity_id": row.get("tail_entity_id"),
                "destinations": set(),
                "evidence_count": 0,
                "max_confidence": 0.0,
                "time_scopes": set(),
                "page_numbers": set(),
                "chapter_titles": set(),
                "section_titles": set(),
                "semantic_tags": set(),
                "council_case_ids": set(),
            },
        )
        item["evidence_count"] += 1
        if row.get("destination"):
            item["destinations"].add(str(row["destination"]))
        if row.get("time_scope"):
            item["time_scopes"].add(str(row["time_scope"]))
        if row.get("citation_page_number") is not None:
            item["page_numbers"].add(int(row["citation_page_number"]))
        if row.get("citation_chapter_title"):
            item["chapter_titles"].add(str(row["citation_chapter_title"]))
        if row.get("citation_section_title"):
            item["section_titles"].add(str(row["citation_section_title"]))
        if row.get("semantic_tag"):
            item["semantic_tags"].add(str(row["semantic_tag"]))
        item["max_confidence"] = max(
            float(item["max_confidence"]), float(row.get("combined_conf") or 0.0)
        )

    for row in council_events:
        key = (
            str(row.get("head_entity_id") or ""),
            str(row.get("relation_type") or ""),
            str(row.get("tail_entity_id") or ""),
        )
        item = summary.setdefault(
            key,
            {
                "head_entity_id": row.get("head_entity_id"),
                "relation_type": row.get("relation_type"),
                "tail_entity_id": row.get("tail_entity_id"),
                "destinations": set(),
                "evidence_count": 0,
                "max_confidence": 0.0,
                "time_scopes": set(),
                "page_numbers": set(),
                "chapter_titles": set(),
                "section_titles": set(),
                "semantic_tags": set(),
                "council_case_ids": set(),
            },
        )
        item["evidence_count"] += 1
        item["destinations"].add("council")
        if row.get("time_scope"):
            item["time_scopes"].add(str(row["time_scope"]))
        if row.get("citation_page_number") is not None:
            item["page_numbers"].add(int(row["citation_page_number"]))
        if row.get("citation_chapter_title"):
            item["chapter_titles"].add(str(row["citation_chapter_title"]))
        if row.get("citation_section_title"):
            item["section_titles"].add(str(row["citation_section_title"]))
        if row.get("council_case_id"):
            item["council_case_ids"].add(str(row["council_case_id"]))
        item["max_confidence"] = max(
            float(item["max_confidence"]), float(row.get("confidence") or 0.0)
        )

    items: List[Dict[str, Any]] = []
    for value in summary.values():
        items.append(
            {
                "head_entity_id": value["head_entity_id"],
                "relation_type": value["relation_type"],
                "tail_entity_id": value["tail_entity_id"],
                "destinations": sorted(value["destinations"]),
                "evidence_count": value["evidence_count"],
                "max_confidence": value["max_confidence"],
                "time_scopes": sorted(value["time_scopes"]),
                "page_numbers": sorted(value["page_numbers"]),
                "chapter_titles": sorted(value["chapter_titles"]),
                "section_titles": sorted(value["section_titles"]),
                "semantic_tags": sorted(value["semantic_tags"]),
                "council_case_ids": sorted(value["council_case_ids"]),
            }
        )

    items.sort(
        key=lambda item: (
            -int(item["evidence_count"]),
            str(item["relation_type"]),
            str(item["head_entity_id"]),
        )
    )
    return items


def build_trust_summary(event_store: Optional[LearningEventStore]) -> Dict[str, Any]:
    if event_store is None:
        return {
            "candidate_status_counts": {},
            "trigger_reason_counts": {},
            "validation_destination_counts": {},
            "confidence_bands": {},
        }

    candidate_status_counts: Dict[str, int] = {}
    trigger_reason_counts: Dict[str, int] = {}
    validation_destination_counts: Dict[str, int] = {}
    confidence_bands = {"low": 0, "medium": 0, "high": 0}

    for row in event_store.read("validation"):
        destination = str(row.get("destination") or "unknown")
        validation_destination_counts[destination] = (
            validation_destination_counts.get(destination, 0) + 1
        )
        confidence = float(row.get("combined_conf") or 0.0)
        if confidence < 0.5:
            confidence_bands["low"] += 1
        elif confidence < 0.8:
            confidence_bands["medium"] += 1
        else:
            confidence_bands["high"] += 1

    for row in event_store.read("council_candidate"):
        status = str(row.get("status") or "unknown")
        candidate_status_counts[status] = candidate_status_counts.get(status, 0) + 1
        for trigger in row.get("council_trigger_reasons", []):
            trigger_label = str(trigger)
            trigger_reason_counts[trigger_label] = trigger_reason_counts.get(trigger_label, 0) + 1

    for row in event_store.read("council_final"):
        status = str(row.get("status") or "unknown")
        candidate_status_counts[status] = candidate_status_counts.get(status, 0) + 1

    return {
        "candidate_status_counts": candidate_status_counts,
        "trigger_reason_counts": trigger_reason_counts,
        "validation_destination_counts": validation_destination_counts,
        "confidence_bands": confidence_bands,
    }


def list_learning_products(
    event_store: Optional[LearningEventStore], limit: int = 20
) -> Dict[str, Any]:
    if event_store is None:
        return {
            "counts": {"snapshots": 0, "evaluations": 0, "bundles": 0, "goldsets": 0},
            "items": [],
        }

    snapshot_dir = event_store.snapshot_path("placeholder").parent
    goldset_dir = event_store.goldset_path("placeholder").parent
    bundle_dir = event_store.bundle_path("placeholder").parent

    snapshot_items = _load_learning_products(snapshot_dir, "snapshot")
    evaluation_items = [item for item in snapshot_items if item.get("kind") == "evaluation"]
    dataset_items = [item for item in snapshot_items if item.get("kind") == "snapshot"]
    goldset_items = _load_learning_products(goldset_dir, "goldset")
    bundle_items = _load_learning_products(bundle_dir, "bundle")

    all_items = sorted(
        dataset_items + evaluation_items + goldset_items + bundle_items,
        key=lambda item: str(
            item.get("updated_at") or item.get("created_at") or item.get("file_name")
        ),
        reverse=True,
    )[: max(limit, 1)]

    return {
        "counts": {
            "snapshots": len(dataset_items),
            "evaluations": len(evaluation_items),
            "bundles": len(bundle_items),
            "goldsets": len(goldset_items),
        },
        "items": all_items,
    }


def _load_learning_products(directory: Path, default_kind: str) -> List[Dict[str, Any]]:
    if not directory.exists():
        return []

    items: List[Dict[str, Any]] = []
    for path in directory.glob("*.json"):
        try:
            payload = _load_json(path)
        except Exception:
            payload = {}

        kind = default_kind
        if default_kind == "snapshot" and path.name.startswith("evaluation-"):
            kind = "evaluation"

        item = {
            "kind": kind,
            "file_name": path.name,
            "path": str(path),
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
        }
        if kind == "snapshot":
            item.update(
                {
                    "version": payload.get("version"),
                    "task_type": payload.get("task_type"),
                    "sample_count": payload.get("sample_count"),
                    "dataset_id": payload.get("dataset_id"),
                }
            )
        elif kind == "evaluation":
            item.update(
                {
                    "dataset_version": payload.get("dataset_version"),
                    "goldset_version": payload.get("goldset_version"),
                    "f1": payload.get("metrics", {}).get("f1")
                    if isinstance(payload.get("metrics"), dict)
                    else None,
                    "accuracy": payload.get("metrics", {}).get("accuracy")
                    if isinstance(payload.get("metrics"), dict)
                    else None,
                }
            )
        elif kind == "goldset":
            item.update(
                {
                    "version": payload.get("version"),
                    "task_type": payload.get("task_type"),
                    "sample_count": payload.get("sample_count"),
                    "goldset_id": payload.get("goldset_id"),
                }
            )
        elif kind == "bundle":
            item.update(
                {
                    "version": payload.get("version"),
                    "status": payload.get("status"),
                    "student1_version": payload.get("student1_version"),
                    "student2_version": payload.get("student2_version"),
                    "policy_version": payload.get("policy_version"),
                    "deployed_at": payload.get("deployed_at"),
                }
            )
        items.append(item)
    return items


def _load_json(path: Path) -> Dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _filter_document_rows(
    rows: List[Dict[str, Any]],
    *,
    q: Optional[str],
    source_type: Optional[str],
    institution: Optional[str],
    region: Optional[str],
    asset_scope: Optional[str],
    document_quality_tier: Optional[str],
) -> List[Dict[str, Any]]:
    query = (q or "").strip().lower()
    source_type_filter = (source_type or "").strip().lower()
    institution_filter = (institution or "").strip().lower()
    region_filter = (region or "").strip().lower()
    asset_scope_filter = (asset_scope or "").strip().lower()
    quality_filter = (document_quality_tier or "").strip().lower()

    filtered: List[Dict[str, Any]] = []
    for row in rows:
        searchable = " ".join(
            [
                str(row.get("doc_id") or ""),
                str(row.get("title") or ""),
                str(row.get("author") or ""),
                str(row.get("institution") or ""),
                str(row.get("source_type") or ""),
            ]
        ).lower()
        if query and query not in searchable:
            continue
        if source_type_filter and source_type_filter != str(row.get("source_type") or "").lower():
            continue
        if (
            institution_filter
            and institution_filter not in str(row.get("institution") or "").lower()
        ):
            continue
        if region_filter and region_filter != str(row.get("region") or "").lower():
            continue
        if asset_scope_filter and asset_scope_filter != str(row.get("asset_scope") or "").lower():
            continue
        if quality_filter and quality_filter != str(row.get("document_quality_tier") or "").lower():
            continue
        filtered.append(row)
    return filtered


def list_entities(
    repository: GraphRepository,
    q: Optional[str] = None,
    entity_type: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
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
                "confidence": props.get(
                    "domain_conf", props.get("pcs_score", props.get("personal_weight"))
                ),
                "origin": props.get("origin", namespace),
                "meta": props,
            }
        )

    return {
        "entity": _node_payload(entity, relation_types=relation_types),
        "neighbors": neighbor_items,
    }


def get_graph(
    repository: GraphRepository, root_entity_id: str, depth: int = 1, limit: int = 50
) -> Dict[str, Any]:
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
