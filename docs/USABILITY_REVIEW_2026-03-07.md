# onTro-Finance Usability Review

Date: 2026-03-07
Reviewer: Codex
Scope: `onTro-finance`
Review lens: "Can someone use this project successfully right now?"

## Assumptions

- Primary product entry point is the FastAPI app in `main.py`.
- `onTroFinanceStarter.py` is the intended no-Neo4j local starter for non-technical or first-run use.
- Review priority is first-run usability over architecture purity.

## Verification Performed

- Created a fresh temporary virtual environment with Python 3.14.
- Installed `requirements.txt`.
- Ran `python -m pytest tests -q`.
  - Result: `140 passed, 2 skipped`
- Smoke-tested FastAPI with two modes:
  - default config path
  - `ONTRO_STORAGE_BACKEND=inmemory` and `ONTRO_COUNCIL_AUTO_ENABLED=false`

## Current Verdict

- Developer quality is decent: the test suite is healthy.
- Current first-run usability is mixed:
  - `main.py` default path is not usable unless Neo4j is already running.
  - `onTroFinanceStarter.py` is usable and boots without Neo4j.
  - Rule-based extraction is only partially usable out of the box because entity coverage is narrow.

## Findings

### 1. Main quick-start path still points users to the Neo4j-required route

- Evidence:
  - `README.md` still sets `ONTRO_STORAGE_BACKEND=neo4j` and tells users to run `main.py`.
  - `docs/TUTORIAL_KO.md` does the same.
  - `onTroFinanceStarter.py` already provides the actually usable first-run path by forcing `inmemory`.
- Impact:
  - A first-time user following the main docs will hit a non-working startup unless Neo4j is already installed and running.
  - The project has a usable starter, but it is not the primary documented path.
- Priority: High
- References:
  - `README.md:35`
  - `README.md:70`
  - `docs/TUTORIAL_KO.md:29`
  - `docs/TUTORIAL_KO.md:81`
  - `onTroFinanceStarter.py:30`

### 2. `/status` can crash instead of reporting degraded storage health

- Evidence:
  - In `lifespan`, startup resolves the graph repository immediately.
  - In `/status`, the handler calls `get_graph_repository()` and `check_graph_repository_health(repo)` with no exception boundary.
  - With default config and no Neo4j running, `/healthz` returned `200` with `initializing`, but `/status` raised a connection error.
- Impact:
  - Operations UI and any status polling can fail hard instead of showing a clear degraded state.
  - This makes troubleshooting worse exactly when the system is least healthy.
- Priority: High
- References:
  - `main.py:431`
  - `main.py:436`
  - `main.py:437`
  - `main.py:728`
  - `src/bootstrap.py:61`
  - `src/bootstrap.py:84`
  - `src/bootstrap.py:99`

### 3. Auto-generated `doc_id` values collide for requests in the same second

- Evidence:
  - Text and PDF ingest both generate IDs from `int(datetime.now().timestamp())`.
  - Multiple ingest requests made within the same second produced the same `doc_id`.
- Impact:
  - Ingest history becomes ambiguous.
  - Detail lookup by `doc_id` can point to the wrong run or the last matching record only.
  - This is likely to show up in UI use, not only in synthetic load tests.
- Priority: Medium
- References:
  - `main.py:592`
  - `main.py:650`
  - `src/learning/event_store.py:13`
  - `src/web/operations_console.py:108`

### 4. Out-of-the-box extraction only works for a narrow vocabulary slice

- Evidence:
  - In `inmemory` mode, `Higher policy rates pressure growth stocks.` produced one edge.
  - `Oil prices support airline margins.` produced zero edges.
  - `Federal Reserve raises interest rates.` produced zero edges.
  - Rule-based NER depends mostly on direct alias hits plus very small pattern rules.
  - Alias coverage includes some finance entities, but not enough variants for common phrasing.
- Impact:
  - A user can think ingestion is broken when the real issue is limited vocabulary coverage.
  - This weakens confidence in the product during the first five minutes.
- Priority: Medium
- References:
  - `src/extraction/ner_student.py:170`
  - `config/alias_dictionary.yaml:4`
  - `config/alias_dictionary.yaml:88`
  - `config/alias_dictionary.yaml:132`

## Recommended Improvement Order

1. Make `onTroFinanceStarter.py` the primary documented local start path in `README.md` and `docs/TUTORIAL_KO.md`.
2. Make `/status` fail soft:
   - catch repository connection errors
   - return `storage_ok=false` and `storage_error`
   - keep the response shape stable for the frontend
3. Replace timestamp-based ingest IDs with collision-safe IDs.
   - example: `uuid4`, ULID, or timestamp plus random suffix
4. Expand rule-based NER alias coverage for the most common first-run phrases.
   - examples: `federal reserve`, `interest rates`, `airline`, `oil prices`
5. Add a tiny "starter smoke" test that verifies:
   - starter boots with `inmemory`
   - `/healthz` and `/status` respond
   - one simple ingest succeeds without Neo4j or Ollama

## Useful Framing

- If the goal is "works for contributors with infra ready", the project is in decent shape.
- If the goal is "someone clones it and tries it today", the primary blocker is not code quality. It is entry-path design and degraded-mode behavior.
