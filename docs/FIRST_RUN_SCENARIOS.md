# First Run Scenarios

## 10-Minute Local Validation

Recommended path:

```bash
make starter
```

Then verify:

```bash
curl -f http://127.0.0.1:8000/healthz
curl -f http://127.0.0.1:8000/status
```

## Sample Finance Scenario

Run the built-in sample scenario without external infrastructure:

```bash
make demo-data
```

The demo scenario:

- boots the FastAPI app in `inmemory` mode
- ingests sample documents from `data/samples/sample_documents.json`
- asks two representative finance questions
- prints readiness, document count, edge count, and answer confidence

Representative questions:

- `How do higher policy rates affect growth stocks?`
- `What do higher oil prices mean for airlines?`

## Full Contributor Smoke

```bash
make test
make functional-test
```

## Deeper Local Reasoning Trace

```bash
make trace-demo
```

Use this path when you want to inspect graph retrieval and reasoning traces instead of only API behavior.
