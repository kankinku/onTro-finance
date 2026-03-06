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

- Python 3.11 이상
- 별도 가상환경
- Neo4j 접속 정보 설정

```powershell
python -m venv "$env:TEMP\ontro-finance-venv"
& "$env:TEMP\ontro-finance-venv\Scripts\python.exe" -m pip install -r requirements.txt
```

필수 Neo4j 환경 변수 예시:

```powershell
$env:ONTRO_STORAGE_BACKEND = "neo4j"
$env:ONTRO_NEO4J_URI = "bolt://localhost:7687"
$env:ONTRO_NEO4J_USER = "neo4j"
$env:ONTRO_NEO4J_PASSWORD = "password"
```

`ONTRO_NEO4J_USERNAME`은 하위호환 alias로만 유지되며 deprecated입니다. 새 설정은 `ONTRO_NEO4J_USER`를 사용해야 합니다.

서버 실행:

```powershell
& "$env:TEMP\ontro-finance-venv\Scripts\python.exe" main.py
```

## 로컬 Neo4j 예시

```powershell
docker run --name ontro-neo4j `
  -p 7474:7474 -p 7687:7687 `
  -e NEO4J_AUTH=neo4j/password `
  -d neo4j:5
```

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

즉 `config/council_members.yaml`에서 `ollama`가 아닌 provider를 쓰려면 `/models` health check뿐 아니라 실제 추론 시 `/chat/completions` 응답 형식을 제공해야 합니다.

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

2026-03-06 기준 최근 검증 결과:

```text
112 passed, 2 skipped
```

## 문서

- 시스템 명세: `docs/SYSTEM_SPECIFICATION.md`
- 시작 가이드: `docs/TUTORIAL_KO.md`
