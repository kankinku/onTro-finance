from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.symphony_poc.models import CommandResult, SymphonyTask, TaskStatus
from tools.symphony_poc.paths import (
    default_worktree_root,
    project_root,
    tasks_root,
)
from tools.symphony_poc.paths import (
    runs_root as default_runs_root,
)
from tools.symphony_poc.store import TaskStore

CommandRunner = Callable[[list[str], Path | None], CommandResult]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _timestamp() -> str:
    return _utc_now().strftime("%Y%m%dT%H%M%SZ")


def _default_runner(command: list[str], cwd: Path | None = None) -> CommandResult:
    completed = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )
    return CommandResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


class SymphonyController:
    def __init__(
        self,
        repo_root: Path | None = None,
        task_store: TaskStore | None = None,
        runs_root: Path | None = None,
        worktree_root: Path | None = None,
        command_runner: CommandRunner | None = None,
    ):
        self.repo_root = Path(repo_root or project_root())
        self.task_store = task_store or TaskStore(tasks_root(self.repo_root))
        self.runs_root = Path(runs_root or default_runs_root(self.repo_root))
        self.worktree_root = Path(worktree_root or default_worktree_root(self.repo_root))
        self.command_runner = command_runner or _default_runner

    def poll_once(self) -> dict[str, Any] | None:
        queued = self.task_store.list(status=TaskStatus.QUEUED)
        if not queued:
            return None
        return self.run_task(queued[0].id)

    def run_task(self, task_id: str) -> dict[str, Any]:
        task = self.task_store.load(task_id)
        run_id = f"{_timestamp()}-{task.id}"
        run_dir = self.runs_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        agent_log_path = run_dir / "agent.log"

        self._transition(task, TaskStatus.RUNNING)
        self._append_log(agent_log_path, f"[{_timestamp()}] starting task {task.id}")

        try:
            base_sha = self._command(["git", "rev-parse", "--verify", task.base_ref], run_dir, agent_log_path).stdout.strip()
            head_sha = self._command(["git", "rev-parse", "--verify", "HEAD"], run_dir, agent_log_path).stdout.strip()
            dirty_output = self._command(["git", "status", "--porcelain"], run_dir, agent_log_path).stdout.strip()
            if dirty_output and base_sha == head_sha:
                raise RuntimeError(
                    "Refusing to use a dirty base ref that resolves to HEAD. Create a snapshot ref first."
                )

            worktree_path = self.worktree_root / task.id
            if not worktree_path.exists():
                self._command(
                    ["git", "worktree", "add", str(worktree_path), "-B", task.branch, task.base_ref],
                    run_dir,
                    agent_log_path,
                )
            worktree_path.mkdir(parents=True, exist_ok=True)

            driver_check = self._command(
                ["codex", "app-server", "generate-json-schema"],
                worktree_path,
                agent_log_path,
            )
            diff_result = self._command(["git", "diff", "--binary"], worktree_path, agent_log_path, check=False)

            rollback_commands = [
                f'git worktree remove "{worktree_path}" --force',
                f"git branch -D {task.branch}",
            ]
            checks = [
                {
                    "name": "driver_probe",
                    "command": "codex app-server generate-json-schema",
                    "exit_code": driver_check.returncode,
                    "stdout_preview": driver_check.stdout[:200],
                }
            ]

            (run_dir / "patch.diff").write_text(diff_result.stdout, encoding="utf-8")
            (run_dir / "checks.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")

            summary = {
                "run_id": run_id,
                "task_id": task.id,
                "status": TaskStatus.NEEDS_REVIEW.value,
                "branch": task.branch,
                "base_ref": task.base_ref,
                "run_dir": str(run_dir),
                "worktree_path": str(worktree_path),
                "rollback_commands": rollback_commands,
                "started_at": task.created_at,
                "completed_at": _utc_now().isoformat().replace("+00:00", "Z"),
            }
            (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            (run_dir / "result.md").write_text(
                self._result_markdown(task=task, worktree_path=worktree_path, rollback_commands=rollback_commands),
                encoding="utf-8",
            )

            self._transition(task, TaskStatus.NEEDS_REVIEW)
            self._append_log(agent_log_path, f"[{_timestamp()}] task {task.id} moved to needs_review")
            return summary
        except Exception as exc:
            self._transition(task, TaskStatus.FAILED)
            failure_summary = {
                "run_id": run_id,
                "task_id": task.id,
                "status": TaskStatus.FAILED.value,
                "error": str(exc),
                "run_dir": str(run_dir),
            }
            (run_dir / "summary.json").write_text(json.dumps(failure_summary, indent=2), encoding="utf-8")
            self._append_log(agent_log_path, f"[{_timestamp()}] task {task.id} failed: {exc}")
            raise

    def _transition(self, task: SymphonyTask, status: TaskStatus) -> None:
        task.status = status
        self.task_store.save(task)

    def _command(
        self,
        command: list[str],
        cwd: Path | None,
        agent_log_path: Path,
        check: bool = True,
    ) -> CommandResult:
        result = self.command_runner(command, cwd)
        self._append_log(
            agent_log_path,
            f"$ {' '.join(command)}\nexit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}",
        )
        if check and result.returncode != 0:
            raise RuntimeError(
                f"Command failed with exit code {result.returncode}: {' '.join(command)}\n{result.stderr.strip()}"
            )
        return result

    @staticmethod
    def _append_log(path: Path, message: str) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\n")

    @staticmethod
    def _result_markdown(task: SymphonyTask, worktree_path: Path, rollback_commands: list[str]) -> str:
        success_lines = "\n".join(f"- {item}" for item in task.success_criteria)
        verification_lines = "\n".join(f"- {item}" for item in task.verification)
        rollback_lines = "\n".join(f"- `{item}`" for item in rollback_commands)
        return f"""# Symphony PoC Run Result

## Task
- id: `{task.id}`
- title: {task.title}
- branch: `{task.branch}`
- worktree: `{worktree_path}`

## Prompt
{task.prompt}

## Success Criteria
{success_lines}

## Verification
{verification_lines}

## Review Gate
- This PoC never auto-merges, auto-pushes, or auto-deploys.
- Every run stops at `needs_review`.

## Rollback
{rollback_lines}
"""
