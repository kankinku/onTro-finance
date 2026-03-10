from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from tools.symphony_poc.models import SymphonyTask, TaskStatus
from tools.symphony_poc.paths import policies_root, project_root, tasks_root
from tools.symphony_poc.policy import EvaluationPolicy
from tools.symphony_poc.store import TaskStore


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _load_json(path: Path | None) -> dict:
    if path is None:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def create_task_from_evaluation(
    evaluation_path: Path,
    task_store: TaskStore,
    policy: EvaluationPolicy,
    status_path: Path | None = None,
) -> Path | None:
    evaluation = _load_json(evaluation_path)
    status_payload = _load_json(status_path) if status_path else None
    metrics = dict(evaluation.get("metrics", {}))
    violations = policy.evaluate(metrics=metrics, status_payload=status_payload)
    if not violations:
        return None

    task_id = f"eval-{_timestamp().lower()}"
    title = f"Investigate evaluation regression for {evaluation.get('dataset_version', 'unknown-dataset')}"
    context = {
        "evaluation_path": str(Path(evaluation_path).resolve()),
        "status_path": str(Path(status_path).resolve()) if status_path else None,
        "evaluation": evaluation,
        "status_snapshot": status_payload,
        "violations": violations,
    }
    prompt = (
        "Investigate the regression recorded in the offline evaluation output.\n"
        f"Evaluation file: {Path(evaluation_path).resolve()}\n"
        f"Violations: {', '.join(violations)}\n"
        "Work in the isolated worktree, capture findings, apply the smallest safe fix, "
        "and stop in needs_review after collecting verification evidence."
    )
    task = SymphonyTask(
        id=task_id,
        title=title,
        kind=policy.task_kind,
        priority=policy.task_priority,
        source=policy.task_source,
        base_ref="HEAD",
        branch=f"codex/symphony/{task_id}",
        prompt=prompt,
        success_criteria=[
            "Identify the regression source with concrete evidence.",
            "Apply the smallest safe fix in the isolated worktree.",
            "Collect verification evidence and stop in needs_review.",
        ],
        verification=policy.verification,
        status=TaskStatus.QUEUED,
        created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        context=context,
    )
    return task_store.save(task)


def main() -> int:
    parser = argparse.ArgumentParser(description="Symphony PoC task queue helpers")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create-from-eval")
    create_parser.add_argument("--evaluation", required=True)
    create_parser.add_argument("--status-json", default=None)
    create_parser.add_argument("--policy", default=str(policies_root(project_root()) / "evaluation.yaml"))

    args = parser.parse_args()

    if args.command == "create-from-eval":
        created = create_task_from_evaluation(
            evaluation_path=Path(args.evaluation),
            status_path=Path(args.status_json) if args.status_json else None,
            policy=EvaluationPolicy.load(Path(args.policy)),
            task_store=TaskStore(tasks_root(project_root())),
        )
        if created is None:
            print("No task created; thresholds satisfied.")
            return 0
        print(created)
        return 0

    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
