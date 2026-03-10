# Symphony PoC Workflow

## Purpose
- Use Symphony-style orchestration outside the product runtime.
- Operate only through isolated git worktrees.
- Stop every task at `needs_review`.

## Required Driver
- Probe availability with `codex app-server generate-json-schema`.
- The PoC reserves `codex app-server` as the driver contract for future expansion.

## Task Contract
- Tasks live in `ops/symphony/tasks/*.yaml`.
- Required fields: `id`, `title`, `kind`, `priority`, `source`, `base_ref`, `branch`, `prompt`, `success_criteria`, `verification`, `status`, `created_at`, `context`.
- Allowed statuses: `queued`, `running`, `needs_review`, `done`, `failed`, `canceled`.
- Branches must start with `codex/`.

## Safety Rules
- Never use a dirty `HEAD` as the base ref for a new run.
- If the latest uncommitted state must be preserved, create a snapshot branch or commit first and use that ref.
- Never auto-merge, auto-push, or auto-deploy.
- Keep product runtime APIs unchanged during the PoC.

## Verification Baseline
- Backend: `pytest tests -q`
- Backend lint: `ruff check .`
- Frontend: `npm test -- --run`
- Frontend build: `npm run build`
- Frontend typecheck: `npm run typecheck`

## Run Artifacts
- Save run output under `ops/symphony/runs/<run-id>/`.
- Required files: `summary.json`, `checks.json`, `agent.log`, `patch.diff`, `result.md`.

## Rollback
- Remove a worktree:
  - `git worktree remove "<worktree-path>" --force`
- Remove its branch:
  - `git branch -D <branch-name>`
