# onTro-Finance

금융 문서에서 관계 후보를 추출하고, 검증과 council 심의를 거쳐 그래프에 반영하는 FastAPI 기반 파이프라인입니다.

## 현재 운영 기준

- 기본 저장소 백엔드는 `neo4j`입니다.
- `ONTRO_STORAGE_BACKEND=inmemory`는 테스트 또는 로컬 디버그용 override입니다.
- 기본 실행 경로는 `neo4j + startup health check + council auto worker`입니다.
- 저장소 health check가 실패하면 서버는 startup 단계에서 실패합니다.
- 샘플 데이터 적재는 기본 비활성화이며 `ONTRO_LOAD_SAMPLE_DATA=true`일 때만 동작합니다.
- 테스트 기본 경로는 운영 기본값과 다릅니다.
  - `tests/conftest.py`가 `ONTRO_STORAGE_BACKEND=inmemory`
  - `tests/conftest.py`가 `ONTRO_COUNCIL_AUTO_ENABLED=false`

## 빠른 시작

권장 환경:

- Python 3.11 또는 3.12
- Python 3.14는 현재 고정된 백엔드 의존성(`pydantic==2.7.4`) 때문에 지원하지 않음
- 별도 가상환경
- 로컬 체험은 Neo4j 없이도 가능

## `.env`로 한 번에 관리

환경변수는 개별 `$env:` 명령으로 넣지 말고 프로젝트 루트의 `.env` 파일 하나로 관리하면 된다.

```powershell
Copy-Item .env.example .env
```

가장 쉬운 로컬 시작용 예시:

```dotenv
ONTRO_STORAGE_BACKEND=inmemory
ONTRO_COUNCIL_AUTO_ENABLED=false
ONTRO_ENABLE_CALLBACKS=false
OPENAI_API_KEY=
GITHUB_COPILOT_ACCESS_TOKEN=
GITHUB_COPILOT_CLIENT_ID=
GITHUB_COPILOT_CLIENT_SECRET=
```

Neo4j 기반 운영 경로 예시:

```dotenv
ONTRO_STORAGE_BACKEND=neo4j
ONTRO_NEO4J_URI=bolt://localhost:7687
ONTRO_NEO4J_USER=neo4j
ONTRO_NEO4J_PASSWORD=password
ONTRO_NEO4J_DATABASE=neo4j
ONTRO_LOAD_SAMPLE_DATA=false
ONTRO_COUNCIL_AUTO_ENABLED=true
ONTRO_ENABLE_CALLBACKS=false
OPENAI_API_KEY=
GITHUB_COPILOT_ACCESS_TOKEN=
GITHUB_COPILOT_CLIENT_ID=
GITHUB_COPILOT_CLIENT_SECRET=
```

애플리케이션은 시작 시 `.env`를 자동 로드한다. 운영체제 환경변수에 이미 값이 있으면 그 값이 우선한다.

운영 경로에서는 startup 단계에서 필수 환경변수 검증을 수행한다.

- `ONTRO_STORAGE_BACKEND=neo4j` 이면 `ONTRO_NEO4J_URI`, `ONTRO_NEO4J_USER`, `ONTRO_NEO4J_PASSWORD`가 없을 경우 서버가 즉시 실패한다.
- `inmemory` 경로는 외부 저장소 자격 증명 없이도 시작 가능하다.

```powershell
python -m venv "$env:TEMP\ontro-finance-venv"
& "$env:TEMP\ontro-finance-venv\Scripts\python.exe" -m pip install -r requirements.txt
```

권장 로컬 시작:

```powershell
& "$env:TEMP\ontro-finance-venv\Scripts\python.exe" onTroFinanceStarter.py
```

`onTroFinanceStarter.py`는 다음을 자동으로 처리합니다.

- `ONTRO_STORAGE_BACKEND=inmemory` 기본 적용
- FastAPI와 operations console을 한 프로세스에서 실행
- `frontend/dist`가 있으면 같은 서버에서 SPA 제공
- 브라우저 자동 오픈

Neo4j 기반 `main.py` 경로를 쓰려면 아래 환경 변수가 필요합니다.

```powershell
$env:ONTRO_STORAGE_BACKEND = "neo4j"
$env:ONTRO_NEO4J_URI = "bolt://localhost:7687"
$env:ONTRO_NEO4J_USER = "neo4j"
$env:ONTRO_NEO4J_PASSWORD = "password"
```

`ONTRO_NEO4J_USERNAME`은 하위호환 alias로만 유지되며 deprecated입니다. 새 설정은 `ONTRO_NEO4J_USER`를 사용해야 합니다.

Neo4j 기반 서버 실행:

```powershell
& "$env:TEMP\ontro-finance-venv\Scripts\python.exe" main.py
```

starter 전용 실행 방법과 EXE 빌드는 `docs/OPS_CONSOLE_STARTER.md`를 참고하면 됩니다.

## 로컬 Neo4j 예시

```powershell
docker run --name ontro-neo4j `
  -p 7474:7474 -p 7687:7687 `
  -e NEO4J_AUTH=neo4j/password `
  -d neo4j:5
```

## Docker Compose 운영 기본값

`docker-compose.yml`은 단일 VM 기준 운영 경로를 위한 기본 persistence 구성을 포함합니다.

- `neo4j_data`: Neo4j 그래프 저장소 유지
- `ontro_app_data`: `/app/data` 아래 runtime 데이터 유지
  - audit/event logs
  - learning snapshots / goldsets / bundles
  - personal/raw runtime data

기본 smoke 절차:

```powershell
docker compose up -d
curl -f http://localhost:8000/healthz
curl -f http://localhost:8000/status
docker compose restart app
curl -f http://localhost:8000/healthz
```

이 경로에서는 컨테이너 재시작 후에도 `ontro_app_data`와 `neo4j_data` 볼륨에 저장된 데이터가 유지되어야 합니다.

## 공식 API

- `POST /api/text/add-to-vectordb`
- `POST /api/pdf/extract-and-embed`
- `POST /api/ask`
- `GET /status`
- `GET /healthz`
- `GET /api/council/cases`
- `GET /api/council/cases/{case_id}`
- `POST /api/council/cases/{case_id}/retry`
- `POST /api/council/process-pending`

## Role-based API keys

Protected operations support three roles.

- `ONTRO_API_KEY_ADMIN`: full access including council decisions, replay/delete, bundle promotion
- `ONTRO_API_KEY_OPERATOR`: ingest, learning evaluation, audit/document operational reads
- `ONTRO_API_KEY_VIEWER`: read-only document/graph/trust/product inspection

If legacy `ONTRO_API_KEY` is set, it is treated as an admin key for backward compatibility.

## External identity (OIDC/JWT bearer)

External bearer token validation can be enabled without removing API key support.

- `ONTRO_JWKS_URI`: provider JWKS endpoint
- `ONTRO_JWT_AUDIENCE`: expected `aud` claim (optional)
- `ONTRO_JWT_ISSUER`: expected `iss` claim (optional)
- `ONTRO_JWT_ROLE_CLAIM`: role claim path, default `roles`
- `ONTRO_JWT_ROLE_MAPPING`: JSON map from provider roles to `admin` / `operator` / `viewer`

When `ONTRO_JWKS_URI` is configured, `Authorization: Bearer <token>` requests are validated first. If no bearer token is supplied, the service falls back to API key auth.

## Distributed coordination (optional)

For multi-instance deployment, Redis-backed coordination can be enabled.

- `ONTRO_REDIS_URL=redis://host:6379/0`

When configured, the service uses Redis for:

- distributed request rate limiting
- distributed event-store locking

If unset, the service falls back to in-process counters and local file locks.

## OCR support

Scanned PDF pages can be OCR-processed when the following flags are enabled.

- `ONTRO_OCR_ENABLED=true`
- `ONTRO_OCR_COMMAND=tesseract` (default)

Current OCR path only runs for pages where `pypdf` extracted no text layer and embedded page images are available.

ingest 응답은 다음 카운터를 제공합니다.

- `edge_count`: 현재 문서에서 처리된 raw edge 수
- `chunks_created`, `total_chunks`: 이전 응답 키와의 호환용 deprecated alias
- `destinations.council`, `council_case_ids`: council 보류 항목 확인용

`/status`의 공식 카운터는 아래 키를 사용합니다.

- `edge_count`
- `pdf_doc_count`

아래 키는 한 릴리스 동안 호환용으로 함께 유지됩니다.

- `vector_count -> edge_count`
- `total_chunks -> edge_count`
- `pdf_docs -> pdf_doc_count`
- `total_pdfs -> pdf_doc_count`

## Council provider 가정

council member provider는 현재 두 계열만 지원합니다.

- `ollama`: `/api/generate`
- 그 외 provider: OpenAI-compatible `/chat/completions`

각 council member는 `config/council_members.yaml`의 `model_name`으로 사용할 모델을 직접 지정할 수 있습니다.
`model_name`을 비워두거나 생략하면 `/models` 또는 `/api/tags` 응답에서 찾은 목록으로 provider별 중복을 최소화하도록 자동 배정합니다.

즉 `config/council_members.yaml`에서 `ollama`가 아닌 provider를 쓰려면 `/models` health check뿐 아니라 실제 추론 시 `/chat/completions` 응답 형식을 제공해야 합니다.

운영 확인용 CLI:

```powershell
python -m src.council.cli --help
python -m src.council.cli members
python -m src.council.cli health
python -m src.council.cli models --json
```

## Offline learning 명령

```powershell
& "$env:TEMP\ontro-finance-venv\Scripts\python.exe" -m src.learning.offline_runner export-dataset
& "$env:TEMP\ontro-finance-venv\Scripts\python.exe" -m src.learning.offline_runner evaluate --snapshot <snapshot.json> --goldset <goldset.json>
& "$env:TEMP\ontro-finance-venv\Scripts\python.exe" -m src.learning.offline_runner create-bundle --student1 s1 --student2 s2 --sign-validator sv --semantic-validator sem --policy pol
```

## 테스트

```powershell
& "$env:TEMP\ontro-finance-venv\Scripts\python.exe" -m pytest tests -q
```

2026-03-07 기준 최근 검증 결과:

```text
140 passed, 2 skipped
```

## 문서

- 시스템 명세: `docs/SYSTEM_SPECIFICATION.md`
- 시작 가이드: `docs/TUTORIAL_KO.md`
- 배포/롤백 runbook: `docs/DEPLOY_RUNBOOK.md`
- OCR/table parser feature track: `docs/OCR_TABLE_TRACK.md`
