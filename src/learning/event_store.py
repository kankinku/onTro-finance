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

    def counts(self) -> Dict[str, int]:
        return {
            "validation": self.count("validation"),
            "council_candidate": self.count("council_candidate"),
            "council_final": self.count("council_final"),
            "query": self.count("query"),
        }

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

    def _event_path(self, event_type: str) -> Path:
        return self.events_path / f"{event_type}.jsonl"


def dump_json(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return path


def load_json(path: Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)
