# Deploy and Rollback Runbook

## Scope

Single-VM Docker Compose deployment for `onTro-finance`.

## Required environment

- `ONTRO_STORAGE_BACKEND`
- `ONTRO_NEO4J_URI`
- `ONTRO_NEO4J_USER`
- `ONTRO_NEO4J_PASSWORD`
- `ONTRO_API_KEY_ADMIN`
- `ONTRO_API_KEY_OPERATOR`
- `ONTRO_API_KEY_VIEWER`
- `ONTRO_JSON_LOGS=true`
- `ONTRO_AUDIT_LOG=true`

## Deploy

```bash
docker compose build
docker compose up -d
curl -f http://localhost:8000/healthz
curl -f http://localhost:8000/status
curl -f http://localhost:8000/metrics
curl -f -H "x-api-key: ${ONTRO_API_KEY_OPERATOR}" http://localhost:8000/api/audit/logs
```

## Post-deploy checks

### 5 minutes

```bash
curl -f http://localhost:8000/healthz
curl -f http://localhost:8000/status
docker compose logs app --tail=100
```

### 15 minutes

```bash
curl -f -H "x-api-key: ${ONTRO_API_KEY_OPERATOR}" http://localhost:8000/api/documents?limit=5
curl -f -H "x-api-key: ${ONTRO_API_KEY_OPERATOR}" http://localhost:8000/api/learning/products
curl -f -H "x-api-key: ${ONTRO_API_KEY_OPERATOR}" http://localhost:8000/api/audit/logs?limit=10
```

### 1 hour

```bash
curl -f http://localhost:8000/metrics
docker compose logs app --tail=200
docker compose ps
```

## Rollback

```bash
docker compose down
docker image ls | grep ontro-finance
# choose previous known-good tag
docker compose up -d
curl -f http://localhost:8000/healthz
curl -f http://localhost:8000/status
```

## Notes

- `neo4j_data` and `ontro_app_data` volumes must be preserved across rollback.
- Do not delete named volumes during routine rollback.
- OCR and table parser enhancements are tracked separately and do not block deployability.
