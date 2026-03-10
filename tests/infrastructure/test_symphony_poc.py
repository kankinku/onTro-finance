from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.symphony_poc.controller import SymphonyController
from tools.symphony_poc.models import CommandResult, SymphonyTask, TaskStatus
from tools.symphony_poc.policy import EvaluationPolicy
from tools.symphony_poc.queue import create_task_from_evaluation
from tools.symphony_poc.store import TaskStore


class FakeCommandRunner:
    def __init__(self, worktree_path: Path, dirty: bool = False):
        self.worktree_path = worktree_path
        self.dirty = dirty
        self.commands: list[tuple[list[str], Path | None]] = []

    def __call__(self, command: list[str], cwd: Path | None = None) -> CommandResult:
        self.commands.append((command, cwd))

        if command[:4] == ["git", "rev-parse", "--verify", "HEAD"]:
            return CommandResult(command=command, returncode=0, stdout="abc123\n", stderr="")
        if command[:3] == ["git", "status", "--porcelain"]:
            return CommandResult(command=command, returncode=0, stdout=" M main.py\n" if self.dirty else "", stderr="")
        if command[:3] == ["git", "rev-parse", "--verify"]:
            return CommandResult(command=command, returncode=0, stdout="abc123\n", stderr="")
        if command[:3] == ["git", "worktree", "add"]:
            self.worktree_path.mkdir(parents=True, exist_ok=True)
            return CommandResult(command=command, returncode=0, stdout="", stderr="")
        if command[:3] == ["codex", "app-server", "generate-json-schema"]:
            return CommandResult(command=command, returncode=0, stdout='{"title":"AppServer"}\n', stderr="")
        if command[:2] == ["git", "diff"]:
            return CommandResult(command=command, returncode=0, stdout="", stderr="")
        raise AssertionError(f"Unexpected command: {command}")


def _write_yaml(path: Path, payload: dict) -> None:
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def test_task_store_rejects_missing_required_field(tmp_path: Path):
    task_path = tmp_path / "ops" / "symphony" / "tasks" / "broken.yaml"
    _write_yaml(
        task_path,
        {
            "id": "broken",
            "title": "Broken task",
            "kind": "manual",
            "priority": "medium",
            "source": "manual",
            "base_ref": "HEAD",
            "prompt": "missing branch",
            "success_criteria": ["one"],
            "verification": ["backend"],
            "status": "queued",
            "created_at": "2026-03-09T00:00:00Z",
            "context": {},
        },
    )

    store = TaskStore(tmp_path / "ops" / "symphony" / "tasks")

    with pytest.raises(ValueError, match="branch"):
        store.load("broken")


def test_controller_creates_run_artifacts_and_marks_task_for_review(tmp_path: Path):
    repo_root = tmp_path
    task_store = TaskStore(repo_root / "ops" / "symphony" / "tasks")
    task = SymphonyTask(
        id="manual-doc-check",
        title="Manual documentation check",
        kind="manual",
        priority="medium",
        source="manual",
        base_ref="HEAD",
        branch="codex/symphony/manual-doc-check",
        prompt="Audit the README wording.",
        success_criteria=["Document the issue clearly."],
        verification=["backend"],
        status=TaskStatus.QUEUED,
        created_at="2026-03-09T00:00:00Z",
        context={"owner": "operator"},
    )
    task_store.save(task)

    worktree_path = tmp_path / "worktrees" / task.id
    controller = SymphonyController(
        repo_root=repo_root,
        task_store=task_store,
        runs_root=repo_root / "ops" / "symphony" / "runs",
        worktree_root=tmp_path / "worktrees",
        command_runner=FakeCommandRunner(worktree_path=worktree_path),
    )

    summary = controller.run_task(task.id)

    saved_task = task_store.load(task.id)
    assert saved_task.status is TaskStatus.NEEDS_REVIEW
    assert summary["status"] == "needs_review"
    assert Path(summary["worktree_path"]) == worktree_path
    assert (Path(summary["run_dir"]) / "summary.json").exists()
    assert (Path(summary["run_dir"]) / "checks.json").exists()
    assert (Path(summary["run_dir"]) / "agent.log").exists()
    assert (Path(summary["run_dir"]) / "patch.diff").exists()
    assert (Path(summary["run_dir"]) / "result.md").exists()
    assert "git worktree remove" in (Path(summary["run_dir"]) / "result.md").read_text(encoding="utf-8")


def test_controller_rejects_dirty_base_ref_when_task_targets_head(tmp_path: Path):
    repo_root = tmp_path
    task_store = TaskStore(repo_root / "ops" / "symphony" / "tasks")
    task_store.save(
        SymphonyTask(
            id="dirty-head",
            title="Dirty head task",
            kind="manual",
            priority="high",
            source="manual",
            base_ref="HEAD",
            branch="codex/symphony/dirty-head",
            prompt="Should not run.",
            success_criteria=["No-op"],
            verification=["backend"],
            status=TaskStatus.QUEUED,
            created_at="2026-03-09T00:00:00Z",
            context={},
        )
    )

    controller = SymphonyController(
        repo_root=repo_root,
        task_store=task_store,
        runs_root=repo_root / "ops" / "symphony" / "runs",
        worktree_root=tmp_path / "worktrees",
        command_runner=FakeCommandRunner(worktree_path=tmp_path / "worktrees" / "dirty-head", dirty=True),
    )

    with pytest.raises(RuntimeError, match="dirty"):
        controller.run_task("dirty-head")

    assert task_store.load("dirty-head").status is TaskStatus.FAILED


def test_evaluation_threshold_violation_creates_task(tmp_path: Path):
    repo_root = tmp_path
    tasks_root = repo_root / "ops" / "symphony" / "tasks"
    policy_path = repo_root / "ops" / "symphony" / "policies" / "evaluation.yaml"
    evaluation_path = repo_root / "evaluation.json"
    status_path = repo_root / "status.json"

    _write_yaml(
        policy_path,
        {
            "task_defaults": {
                "kind": "evaluation_regression",
                "priority": "high",
                "source": "offline_evaluation",
                "verification": ["backend", "frontend"],
            },
            "thresholds": {
                "evaluation": {
                    "f1": 0.85,
                    "precision": 0.8,
                    "recall": 0.8,
                    "accuracy": 0.8,
                },
                "status": {
                    "council_pending_max": 3,
                    "storage_ok": True,
                },
            },
        },
    )
    evaluation_path.write_text(
        json.dumps(
            {
                "dataset_id": "DS_1",
                "dataset_version": "20260309",
                "goldset_id": "GS_1",
                "goldset_version": "gold_v1",
                "metrics": {
                    "f1": 0.61,
                    "precision": 0.7,
                    "recall": 0.79,
                    "accuracy": 0.95,
                },
            }
        ),
        encoding="utf-8",
    )
    status_path.write_text(
        json.dumps(
            {
                "storage_ok": False,
                "council_pending": 7,
            }
        ),
        encoding="utf-8",
    )

    created = create_task_from_evaluation(
        evaluation_path=evaluation_path,
        task_store=TaskStore(tasks_root),
        policy=EvaluationPolicy.load(policy_path),
        status_path=status_path,
    )

    assert created is not None
    created_task = TaskStore(tasks_root).load(created.stem)
    assert created_task.status is TaskStatus.QUEUED
    assert created_task.kind == "evaluation_regression"
    assert "f1" in created_task.prompt
    assert "storage_ok" in json.dumps(created_task.context)


def test_workflow_and_policy_contract_files_exist():
    project_root = Path(__file__).resolve().parents[2]
    workflow = (project_root / "WORKFLOW.md").read_text(encoding="utf-8")
    policy = (project_root / "ops" / "symphony" / "policies" / "evaluation.yaml").read_text(encoding="utf-8")

    assert "codex app-server" in workflow
    assert "needs_review" in workflow
    assert "git worktree remove" in workflow
    assert "f1" in policy
    assert "council_pending_max" in policy
