from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class EvaluationPolicy:
    task_kind: str
    task_priority: str
    task_source: str
    verification: list[str]
    evaluation_thresholds: dict[str, float]
    council_pending_max: int
    storage_ok_required: bool

    @classmethod
    def load(cls, path: Path) -> EvaluationPolicy:
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        defaults = payload.get("task_defaults", {})
        thresholds = payload.get("thresholds", {})
        evaluation = thresholds.get("evaluation", {})
        status = thresholds.get("status", {})

        return cls(
            task_kind=str(defaults.get("kind", "evaluation_regression")),
            task_priority=str(defaults.get("priority", "high")),
            task_source=str(defaults.get("source", "offline_evaluation")),
            verification=[str(item) for item in defaults.get("verification", ["backend", "frontend"])],
            evaluation_thresholds={str(key): float(value) for key, value in evaluation.items()},
            council_pending_max=int(status.get("council_pending_max", 0)),
            storage_ok_required=bool(status.get("storage_ok", False)),
        )

    def evaluate(self, metrics: dict[str, Any], status_payload: dict[str, Any] | None = None) -> list[str]:
        violations: list[str] = []

        for metric_name, minimum in self.evaluation_thresholds.items():
            value = metrics.get(metric_name)
            if value is None:
                violations.append(f"{metric_name} missing")
                continue
            if float(value) < minimum:
                violations.append(f"{metric_name}={value} < {minimum}")

        if status_payload is not None:
            council_pending = int(status_payload.get("council_pending", 0))
            if self.council_pending_max and council_pending > self.council_pending_max:
                violations.append(
                    f"council_pending={council_pending} > {self.council_pending_max}"
                )
            if self.storage_ok_required and not bool(status_payload.get("storage_ok", False)):
                violations.append("storage_ok=false")

        return violations
