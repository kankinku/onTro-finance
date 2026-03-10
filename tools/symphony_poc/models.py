from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    NEEDS_REVIEW = "needs_review"
    DONE = "done"
    FAILED = "failed"
    CANCELED = "canceled"


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(slots=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


@dataclass(slots=True)
class SymphonyTask:
    id: str
    title: str
    kind: str
    priority: str
    source: str
    base_ref: str
    branch: str
    prompt: str
    success_criteria: list[str]
    verification: list[str]
    status: TaskStatus
    created_at: str
    context: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SymphonyTask:
        required_fields = (
            "id",
            "title",
            "kind",
            "priority",
            "source",
            "base_ref",
            "branch",
            "prompt",
            "success_criteria",
            "verification",
            "status",
            "created_at",
            "context",
        )
        missing = [field_name for field_name in required_fields if field_name not in payload]
        if missing:
            raise ValueError(f"Missing required task fields: {', '.join(missing)}")

        if not str(payload["id"]).strip():
            raise ValueError("Task id must not be empty")
        if not str(payload["branch"]).strip():
            raise ValueError("Task branch must not be empty")
        if not str(payload["branch"]).startswith("codex/"):
            raise ValueError("Task branch must start with 'codex/'")

        priority = str(payload["priority"]).strip().lower()
        if priority not in {item.value for item in TaskPriority}:
            raise ValueError(f"Unsupported task priority: {payload['priority']}")

        try:
            status = TaskStatus(str(payload["status"]).strip().lower())
        except ValueError as exc:
            raise ValueError(f"Unsupported task status: {payload['status']}") from exc

        success_criteria = list(payload["success_criteria"] or [])
        verification = list(payload["verification"] or [])
        if not success_criteria:
            raise ValueError("Task success_criteria must not be empty")
        if not verification:
            raise ValueError("Task verification must not be empty")
        if not isinstance(payload["context"], dict):
            raise ValueError("Task context must be a mapping")

        return cls(
            id=str(payload["id"]).strip(),
            title=str(payload["title"]).strip(),
            kind=str(payload["kind"]).strip(),
            priority=priority,
            source=str(payload["source"]).strip(),
            base_ref=str(payload["base_ref"]).strip(),
            branch=str(payload["branch"]).strip(),
            prompt=str(payload["prompt"]).strip(),
            success_criteria=[str(item).strip() for item in success_criteria],
            verification=[str(item).strip() for item in verification],
            status=status,
            created_at=str(payload["created_at"]).strip(),
            context=dict(payload["context"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind,
            "priority": self.priority,
            "source": self.source,
            "base_ref": self.base_ref,
            "branch": self.branch,
            "prompt": self.prompt,
            "success_criteria": list(self.success_criteria),
            "verification": list(self.verification),
            "status": self.status.value,
            "created_at": self.created_at,
            "context": dict(self.context),
        }
