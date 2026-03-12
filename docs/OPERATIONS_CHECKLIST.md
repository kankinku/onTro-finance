# Operations Checklist

Use this checklist to execute the remaining release-readiness phases with explicit pass/fail evidence.

## Phase 2 - GitHub Actions Validation

### Prerequisites

- `gh` authenticated for `https://github.com/kankinku/onTro-finance`
- repository write access for workflow dispatch and release inspection

### Commands

```bash
gh auth status
gh workflow list
gh run list --limit 10
```

If the workflows need a fresh run:

```bash
gh workflow run ci.yml
gh workflow run security.yml
gh workflow run release.yml
```

Inspect results:

```bash
gh run list --workflow ci.yml --limit 5
gh run list --workflow security.yml --limit 5
gh run list --workflow release.yml --limit 5
gh run view <run-id> --log
```

### Pass Criteria

- `ci.yml` completes with `backend`, `frontend`, `starter-smoke`, and `docker-build` green
- `security.yml` completes and any failures are reflected in `docs/SECURITY_TRIAGE.md`
- `release.yml` proves image metadata for `vX.Y.Z`, `latest`, and SHA tags
- no workflow failure is left unexplained

### Failure Triage Order

1. fix repo-local workflow assumptions first
2. fix dependency issues second
3. only document accepted risk after proving it is not a runtime issue

## Phase 3 - Docker Runtime Validation

### Prerequisites

- Docker daemon running
- local ports `3000`, `6379`, `7474`, `7687`, `8000`, and `9090` available

### Config Validation

```bash
docker compose config
docker compose --profile observability config
docker compose --profile distributed config
```

### Single-Node Validation

```bash
docker compose up -d
docker compose ps
curl -f http://localhost:8000/healthz
curl -f http://localhost:8000/status
curl -f http://localhost:8000/metrics
docker compose down
```

### Observability Validation

```bash
docker compose --profile observability up -d
docker compose ps
curl -f http://localhost:8000/healthz
curl -f http://localhost:8000/status
curl -f http://localhost:8000/metrics
curl -f http://localhost:9090/api/v1/targets
curl -f http://localhost:3000/api/health
docker compose --profile observability down
```

Expected wiring:

- Prometheus scrapes `app:8000/metrics` from `ops/prometheus/prometheus.yml`
- Grafana datasource points at `http://prometheus:9090` from `ops/grafana/provisioning/datasources/prometheus.yml`

### Distributed Validation

```bash
docker compose --profile distributed up -d
docker compose ps
curl -f http://localhost:8000/healthz
curl -f http://localhost:8000/status
curl -f http://localhost:8000/metrics
docker compose exec redis redis-cli ping
docker compose --profile distributed down
```

### Pass Criteria

- all selected services reach healthy or started state without restart loops
- `/healthz`, `/status`, and `/metrics` return successfully in each profile
- observability profile exposes live Prometheus targets and Grafana health
- distributed profile brings up Redis without app startup regression

## Release Gate Summary

Before tagging `v0.x.y`:

- `CHANGELOG.md` updated
- `docs/RELEASE_NOTES_TEMPLATE.md` populated for the release
- `docs/SECURITY_TRIAGE.md` refreshed from current audit output
- GitHub workflow evidence captured
- Docker runtime evidence captured
