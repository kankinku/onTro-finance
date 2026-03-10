"""Persistent JSONL event logging for the offline learning loop."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


class LearningEventStore:
    """Append-only event storage for validation, council, and query outcomes."""

    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)
        self.events_path = self.base_path / "events"
        self.events_path.mkdir(parents=True, exist_ok=True)

    def append(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "event_type": event_type,
            "logged_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            **payload,
        }
        path = self._event_path(event_type)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def read(self, event_type: str) -> List[Dict[str, Any]]:
        path = self._event_path(event_type)
        if not path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        return rows

    def count(self, event_type: str) -> int:
        return len(self.read(event_type))

    def replace(self, event_type: str, records: Iterable[Dict[str, Any]]) -> None:
        path = self._event_path(event_type)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def clear(self, event_type: str) -> None:
        self.replace(event_type, [])

    def counts(self) -> Dict[str, int]:
        return {
            "ingest": self.count("ingest"),
            "validation": self.count("validation"),
            "council_candidate": self.count("council_candidate"),
            "council_final": self.count("council_final"),
            "query": self.count("query"),
            "documents": self.document_count(),
            "audit": self.audit_count(),
        }

    def upsert_document(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        doc_id = str(payload.get("doc_id") or "").strip()
        if not doc_id:
            raise ValueError("Document record requires doc_id")

        record = {
            "doc_id": doc_id,
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            **payload,
        }

        records = self.read_documents()
        replaced = False
        for index, existing in enumerate(records):
            if existing.get("doc_id") != doc_id:
                continue
            created_at = existing.get("created_at") or record["updated_at"]
            record["created_at"] = created_at
            records[index] = {**existing, **record}
            replaced = True
            break

        if not replaced:
            record["created_at"] = record["updated_at"]
            records.append(record)

        self.replace_documents(records)
        return self.get_document(doc_id) or record

    def read_documents(self) -> List[Dict[str, Any]]:
        path = self._documents_path()
        if not path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        return rows

    def replace_documents(self, records: Iterable[Dict[str, Any]]) -> None:
        path = self._documents_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        for row in self.read_documents():
            if row.get("doc_id") == doc_id:
                return row
        return None

    def list_documents(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        rows = list(reversed(self.read_documents()))
        if limit is None:
            return rows
        return rows[: max(limit, 1)]

    def delete_document(self, doc_id: str) -> bool:
        rows = self.read_documents()
        filtered = [row for row in rows if row.get("doc_id") != doc_id]
        if len(filtered) == len(rows):
            return False
        self.replace_documents(filtered)
        return True

    def clear_documents(self) -> None:
        self.replace_documents([])

    def document_count(self) -> int:
        return len(self.read_documents())

    def append_audit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.append("audit", payload)

    def list_audit(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        rows = list(reversed(self.read("audit")))
        if limit is None:
            return rows
        return rows[: max(limit, 1)]

    def audit_count(self) -> int:
        return self.count("audit")

    def snapshot_path(self, name: str) -> Path:
        path = self.base_path / "snapshots"
        path.mkdir(parents=True, exist_ok=True)
        return path / name

    def goldset_path(self, name: str) -> Path:
        path = self.base_path / "goldsets"
        path.mkdir(parents=True, exist_ok=True)
        return path / name

    def bundle_path(self, name: str) -> Path:
        path = self.base_path / "bundles"
        path.mkdir(parents=True, exist_ok=True)
        return path / name

    def documents_path(self) -> Path:
        return self._documents_path()

    def _event_path(self, event_type: str) -> Path:
        return self.events_path / f"{event_type}.jsonl"

    def _documents_path(self) -> Path:
        return self.base_path / "documents.jsonl"


def dump_json(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return path


def load_json(path: Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)
