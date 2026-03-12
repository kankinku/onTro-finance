# Backup and Restore

## Volumes To Preserve

- `neo4j_data`
- `ontro_app_data`

## Pre-Flight

Before creating or restoring backups:

- confirm the target compose project is `ontro-finance`
- ensure enough free disk space exists for both `.tgz` archives
- stop write-heavy ingest activity before capturing release-candidate backups

## Create Backups

Create a local backup directory first:

```bash
mkdir -p backups
```

Backup Neo4j volume:

```bash
docker run --rm -v neo4j_data:/volume -v "$PWD/backups:/backup" busybox tar czf /backup/neo4j_data.tgz -C /volume .
```

Backup application data volume:

```bash
docker run --rm -v ontro_app_data:/volume -v "$PWD/backups:/backup" busybox tar czf /backup/ontro_app_data.tgz -C /volume .
```

## Restore Backups

Stop services before restoring:

```bash
docker compose down
```

Restore Neo4j volume:

```bash
docker run --rm -v neo4j_data:/volume -v "$PWD/backups:/backup" busybox sh -c "rm -rf /volume/* && tar xzf /backup/neo4j_data.tgz -C /volume"
```

Restore application data volume:

```bash
docker run --rm -v ontro_app_data:/volume -v "$PWD/backups:/backup" busybox sh -c "rm -rf /volume/* && tar xzf /backup/ontro_app_data.tgz -C /volume"
```

Restart and validate:

```bash
docker compose up -d
curl -f http://localhost:8000/healthz
curl -f http://localhost:8000/status
curl -f http://localhost:8000/metrics
```

Expected validation outcome:

- `/healthz` returns `{"status":"ok","ready":true,...}`
- `/status` returns `"storage_ok": true`
- `/metrics` includes `ontro_ready 1`

Recommended restore drill for release candidates:

1. `docker compose down`
2. restore both volumes
3. `docker compose up -d --wait`
4. verify `healthz`, `status`, and `metrics`
5. record the drill date in release notes or the operations checklist

## Retention Guidance

- keep at least one daily backup for 7 days
- keep one weekly backup for 4 weeks
- test restore before tagging a release candidate

## Scope Notes

- this document covers Docker volume backup for the supported compose deployment paths
- object-store, managed Neo4j, and cloud snapshot procedures are out of scope for the current `v0.x.y` baseline
