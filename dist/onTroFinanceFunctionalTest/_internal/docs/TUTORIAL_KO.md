# onTro-Finance 시작 가이드

이 문서는 현재 코드 기준으로 로컬 실행, Neo4j 준비, council 자동 심의, offline learning, 테스트 재현 방법을 설명합니다.

## 1. 환경 준비

권장 기준:

- Python 3.11 이상
- 별도 가상환경 사용
- 로컬 또는 원격 Neo4j 준비

```powershell
python -m venv "$env:TEMP\ontro-finance-venv"
& "$env:TEMP\ontro-finance-venv\Scripts\python.exe" -m pip install -r requirements.txt
```

### `.env` 파일 하나로 관리

프로젝트 루트에서 `.env.example`을 복사해 `.env`를 만들고 여기에 모든 환경변수를 모아두면 된다.

```powershell
Copy-Item .env.example .env
```

예시:

```dotenv
ONTRO_STORAGE_BACKEND=neo4j
ONTRO_NEO4J_URI=bolt://localhost:7687
ONTRO_NEO4J_USER=neo4j
ONTRO_NEO4J_PASSWORD=password
ONTRO_NEO4J_DATABASE=neo4j
ONTRO_LOAD_SAMPLE_DATA=false
ONTRO_COUNCIL_AUTO_ENABLED=true
ONTRO_COUNCIL_POLL_SECONDS=5
ONTRO_ENABLE_CALLBACKS=false
ONTRO_CALLBACK_ALLOWED_HOSTS=example.com,api.example.com
ONTRO_CALLBACK_ALLOWED_SCHEMES=https
OPENAI_API_KEY=
GITHUB_COPILOT_ACCESS_TOKEN=
GITHUB_COPILOT_CLIENT_ID=
GITHUB_COPILOT_CLIENT_SECRET=
```

애플리케이션과 스크립트는 시작 시 `.env`를 자동으로 읽는다. 이미 셸에 같은 이름의 환경변수가 있으면 셸 값이 우선한다.

## 2. Neo4j 준비

기본 백엔드는 `neo4j`입니다. 접속 정보가 없거나 health check가 실패하면 서버는 startup에서 실패합니다.

환경 변수 예시:

```powershell
$env:ONTRO_STORAGE_BACKEND = "neo4j"
$env:ONTRO_NEO4J_URI = "bolt://localhost:7687"
$env:ONTRO_NEO4J_USER = "neo4j"
$env:ONTRO_NEO4J_PASSWORD = "password"
```

`ONTRO_NEO4J_USERNAME`은 deprecated alias입니다. 새 설정은 `ONTRO_NEO4J_USER`만 사용하세요.

Docker 예시:

```powershell
docker run --name ontro-neo4j `
  -p 7474:7474 -p 7687:7687 `
  -e NEO4J_AUTH=neo4j/password `
  -d neo4j:5
```

테스트나 일시 디버그에서만 메모리 백엔드를 쓰려면:

```powershell
$env:ONTRO_STORAGE_BACKEND = "inmemory"
```

## 3. 서버 실행

```powershell
& "$env:TEMP\ontro-finance-venv\Scripts\python.exe" main.py
```

기본 startup 동작:

- baseline ontology 로드
- graph repository health check
- council member availability refresh
- `ONTRO_COUNCIL_AUTO_ENABLED=true`일 때 council auto worker 시작
- sample seed는 기본 비활성화

## 4. 샘플 seed

샘플 문서를 startup 시 적재하려면 명시적으로 켭니다.

```powershell
$env:ONTRO_LOAD_SAMPLE_DATA = "true"
& "$env:TEMP\ontro-finance-venv\Scripts\python.exe" main.py
```

## 5. callback 보안

`callback_url`은 기본 비활성화입니다. 사용하려면 아래 값을 함께 설정합니다.

```powershell
$env:ONTRO_ENABLE_CALLBACKS = "true"
$env:ONTRO_CALLBACK_ALLOWED_HOSTS = "example.com,api.example.com"
```

적용 규칙:

- 기본 허용 scheme은 `https`
- allowlist 밖의 host는 거부
- loopback, private IP, 내부망 해석 주소는 거부
- URL 내 사용자명과 비밀번호는 거부

## 6. ingest와 council

공식 ingest API:

- `POST /api/text/add-to-vectordb`
- `POST /api/pdf/extract-and-embed`

질의 API:

- `POST /api/ask`

council 운영 API:

- `GET /api/council/cases`
- `GET /api/council/cases/{case_id}`
- `POST /api/council/cases/{case_id}/retry`
- `POST /api/council/process-pending`

ingest 응답의 공식 카운터:

- `edge_count`

호환용 alias:

- `chunks_created`
- `total_chunks`

council 관련 확인 키:

- `destinations.council`
- `council_case_ids`

## 7. 상태 확인

`/status`는 아래 공식 카운터를 제공합니다.

- `edge_count`
- `pdf_doc_count`

호환용 alias도 한 릴리스 동안 함께 제공합니다.

- `vector_count`
- `total_chunks`
- `pdf_docs`
- `total_pdfs`

추가로 아래 정보를 제공합니다.

- entity/relation 수
- domain/personal relation 수
- council pending/closed 수
- configured/available member 수
- storage health
- transaction commit/rollback 수
- council worker 상태
- learning event backlog

`/healthz`는 readiness와 함께 storage, council worker 준비 상태를 반환합니다.

## 8. Council provider 설정

`config/council_members.yaml` 기준 지원 범위:

- `ollama`: `/api/generate`
- non-ollama provider: OpenAI-compatible `/chat/completions`

즉 `healthcheck_path=/models`가 통과해도 실제 추론 응답이 OpenAI-compatible 형식이 아니면 council worker 추론은 실패합니다.

## 9. Offline learning

```powershell
& "$env:TEMP\ontro-finance-venv\Scripts\python.exe" -m src.learning.offline_runner export-dataset
& "$env:TEMP\ontro-finance-venv\Scripts\python.exe" -m src.learning.offline_runner evaluate --snapshot <snapshot.json> --goldset <goldset.json>
& "$env:TEMP\ontro-finance-venv\Scripts\python.exe" -m src.learning.offline_runner create-bundle --student1 s1 --student2 s2 --sign-validator sv --semantic-validator sem --policy pol
```

offline runner는 adapter를 붙일 수 없는 예상 가능한 오류만 degrade 처리하고, 그 외 예외는 그대로 드러냅니다.

## 10. 테스트 재현

```powershell
python -m venv "$env:TEMP\ontro-finance-venv"
& "$env:TEMP\ontro-finance-venv\Scripts\python.exe" -m pip install -r requirements.txt
& "$env:TEMP\ontro-finance-venv\Scripts\python.exe" -m pytest tests -q
```

기본 테스트 경로에서는 `tests/conftest.py`가 다음 값을 강제합니다.

- `ONTRO_STORAGE_BACKEND=inmemory`
- `ONTRO_COUNCIL_AUTO_ENABLED=false`

즉 운영 기본값은 `neo4j + council auto worker on`이지만, 테스트 기본값은 별도 외부 저장소 없이 재현되도록 분리되어 있습니다.
