from __future__ import annotations

from pathlib import Path

import yaml

from tools.symphony_poc.models import SymphonyTask, TaskPriority, TaskStatus


class TaskStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, task_id: str) -> Path:
        return self.root / f"{task_id}.yaml"

    def load(self, task_id: str) -> SymphonyTask:
        path = self.path_for(task_id)
        if not path.exists():
            raise FileNotFoundError(f"Task file not found: {path}")
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return SymphonyTask.from_dict(payload)

    def save(self, task: SymphonyTask) -> Path:
        path = self.path_for(task.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(task.to_dict(), sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return path

    def list(self, status: TaskStatus | None = None) -> list[SymphonyTask]:
        items: list[SymphonyTask] = []
        for path in sorted(self.root.glob("*.yaml")):
            task = SymphonyTask.from_dict(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
            if status is not None and task.status is not status:
                continue
            items.append(task)
        priority_rank = {
            TaskPriority.HIGH.value: 0,
            TaskPriority.MEDIUM.value: 1,
            TaskPriority.LOW.value: 2,
        }
        return sorted(items, key=lambda item: (priority_rank[item.priority], item.created_at, item.id))
