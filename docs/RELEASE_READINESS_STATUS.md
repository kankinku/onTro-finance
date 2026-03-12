# Release Readiness Status

Last updated: 2026-03-12

## Completed Locally

- baseline hygiene aligned across docs, ignore rules, and runtime packaging
- Docker runtime validated for:
  - single-node compose
  - observability profile
  - distributed profile
- release documentation added:
  - `CHANGELOG.md`
  - `docs/RELEASE_NOTES_TEMPLATE.md`
  - `docs/OPERATIONS_CHECKLIST.md`
- security triage documented in `docs/SECURITY_TRIAGE.md`
- performance baseline recorded in `docs/PERFORMANCE_BASELINE.md`
- extraction regression suite expanded for rates, bonds, growth stocks, dollar, and commodities
- demo scenario strengthened to verify ingest -> ask -> status -> metrics

## Verified Evidence

- `python -m pytest tests/extraction/test_finance_regressions.py -q` -> passed
- `python -m pytest tests/infrastructure/test_demo_scenario.py tests/extraction/test_finance_regressions.py -q` -> passed
- `python scripts/demo_scenario.py --sample-limit 4 --json` -> healthy ingest and metrics output
- `docker compose up -d --wait` -> passed
- `docker compose --profile observability up -d --wait` -> passed
- `docker compose --profile distributed up -d --wait` -> passed
- `/healthz`, `/status`, `/metrics` verified across runtime profiles
- Prometheus target API and Grafana health verified in observability mode
- Redis `PONG` verified in distributed mode

## Remote GitHub State

Public GitHub API evidence shows the public `main` branch is still behind the local baseline:

- remote `CI` exists and is failing in the `Install dependencies` step
- remote `docker-build` is skipped because `CI` fails first
- remote `main` does not yet reflect the local multi-workflow baseline and runtime fixes

## Remaining Blocker

The remaining release-readiness blocker is remote execution, not local implementation.

To fully close release readiness:

1. push the current local baseline to the remote branch
2. rerun GitHub Actions against the updated workflow files
3. confirm remote `CI`, `Security`, and `Release` outcomes are green or explicitly triaged
4. tag the first `v0.x.y` release and verify image publication

## Ready-To-Run Next Step

- create a baseline commit for the current local changes
- push the branch
- inspect the next remote workflow run and fix only log-proven failures
