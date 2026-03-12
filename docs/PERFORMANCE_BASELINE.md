# Performance Baseline

Use the lightweight load script against a running local or deployed instance:

```bash
make load-baseline
```

Or specify a custom endpoint:

```bash
python scripts/load_baseline.py --base-url http://localhost:8000 --iterations 10
```

## Baseline Metrics

Track these values before each release candidate:

- ingest `p50` / `p95`
- ask `p50` / `p95`
- max latency for both paths
- readiness and status availability during the run

## Initial Release Gate

Use these as the initial reference targets for a single-node deployment:

- `healthz` remains available during the run
- ingest `p95 < 1500ms`
- ask `p95 < 2500ms`
- no HTTP failures during the baseline loop

If the environment is slower, record the observed numbers in the release notes before publishing.

## Measured Local Baseline

Collected on 2026-03-12 against `docker compose up -d --wait` with `python scripts/load_baseline.py --iterations 10`.

| Path | p50 | p95 | max | mean |
| --- | ---: | ---: | ---: | ---: |
| ingest | 18.38ms | 135.16ms | 135.16ms | 29.98ms |
| ask | 13.66ms | 25.76ms | 25.76ms | 15.37ms |

Observed result:

- `healthz` stayed available during the run
- ingest and ask latencies were comfortably under the initial release gate
- no HTTP failures were observed in the baseline loop
