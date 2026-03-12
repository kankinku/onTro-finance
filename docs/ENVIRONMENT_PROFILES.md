# Environment Profiles

## Profiles

- `starter/local`: use `.env.dev.example` or `.env.example`
- `single-node prod`: use `.env.single-node.example`
- `distributed`: use `.env.distributed.example`

## Starter / Local

- storage: `inmemory`
- council automation: off
- callbacks: off
- purpose: first-run UX, local analysis, frontend/API validation

Recommended env:

- `ONTRO_STORAGE_BACKEND=inmemory`
- `ONTRO_COUNCIL_AUTO_ENABLED=false`
- `ONTRO_LOAD_SAMPLE_DATA=false`
- `ONTRO_JSON_LOGS=false`

## Single-Node Production

- storage: Neo4j
- audit/json logs: on
- role-based API keys: required
- purpose: one app container + one Neo4j container via `docker-compose.yml`

Required env:

- `ONTRO_STORAGE_BACKEND=neo4j`
- `ONTRO_NEO4J_URI=bolt://neo4j:7687`
- `ONTRO_NEO4J_USER=neo4j`
- `ONTRO_NEO4J_PASSWORD=<secret>`
- `ONTRO_API_KEY_ADMIN=<secret>`
- `ONTRO_API_KEY_OPERATOR=<secret>`
- `ONTRO_API_KEY_VIEWER=<secret>`

Recommended env:

- `ONTRO_JSON_LOGS=true`
- `ONTRO_LOAD_SAMPLE_DATA=false`

Recommended compose command:

```bash
docker compose up -d --wait
```

## Distributed

- storage: Neo4j
- coordination: Redis via `ONTRO_REDIS_URL`
- purpose: multiple app instances sharing event-store locks and rate-limit coordination
- recommended compose command:

```bash
docker compose --profile distributed up -d
```

Required env additions:

- `ONTRO_REDIS_URL=redis://redis:6379/0`

Recommended verification:

- `curl -f http://localhost:8000/healthz`
- `curl -f http://localhost:8000/status`
- `docker compose --profile distributed exec -T redis redis-cli ping`

## Observability Add-On

Prometheus and Grafana are provided as an optional compose profile:

```bash
docker compose --profile observability up -d
```

Services:

- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`

Recommended verification:

- `curl -f http://localhost:8000/metrics`
- `curl -f http://localhost:9090/api/v1/targets`
- `curl -f http://localhost:3000/api/health`

## Profile Selection Guide

- choose `starter/local` for evaluation, frontend/API iteration, and smoke checks without Docker dependencies
- choose `single-node prod` for the default supported deployment path
- choose `distributed` only when Redis-backed coordination is required
- add `observability` when Prometheus/Grafana evidence is needed for release or incident work
