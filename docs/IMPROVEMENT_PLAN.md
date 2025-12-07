# 온톨로지 금융 시스템 (OntoFin) 개선 제안서 (Audit Report)

현재 구현된 v4.0 프로토타입 코드를 정밀 분석하여, 상용화(Production) 수준으로 가기 위해 필요한 개선 사항을 정리했습니다.

---

## 🟥 1. Critical (핵심 기능 정상화)

### 1) LLM 연동 실체화 (M1 Analyzer)
- **현상**: `src/pipeline/m1_analyzer.py`가 하드코딩된 `_mock_llm_response`를 반환합니다.
- **문제**: 입력 텍스트가 바뀌어도 항상 "SLR/바젤3" 결과만 나옵니다.
- **개선안**:
  - `openai` 또는 `langchain` 라이브러리를 설치하여 실제 GPT-4 호출 코드로 교체해야 합니다.
  - API Key 관리를 위한 설정 파일(`config/.env`)이 필요합니다.

### 2) Entity Resolver의 벡터(Vector) 도입 (M2)
- **현상**: 단순 문자열 일치(`if surface in self.kb_terms`) 방식입니다.
- **문제**: "미 국채"와 "미국 국채", "Treasury"가 모두 다른 용어로 인식됩니다.
- **개선안**:
  - `SentenceTransformers` + `FAISS` (또는 로컬 ChromaDB)를 도입하여 의미적 유사도 검색(Semantic Search)을 구현해야 합니다.

### 3) DB Persistence (영속성 확보)
- **현상**: Neo4j 드라이버가 Mock 상태이며, 실제 데이터는 `global_kg` (RAM)에만 존재합니다. 서버 재시작 시 데이터가 날아갑니다.
- **개선안**:
  - Neo4j가 없을 때를 대비해 **SQLite** 또는 **JSON 파일** 기반의 로컬 저장소를 백업 옵션으로 추가해야 합니다.

---

## 🟨 2. Architecture & Code Quality

### 1) Configuration Management (설정 중앙화)
- **현상**: DB 접속 정보, Mock 데이터 스위치 등이 코드 곳곳에 산재 (`bolt://localhost...`).
- **개선안**: 
  - `pydantic-settings`를 사용하여 환경 변수(.env)로 설정을 중앙 관리해야 합니다.

### 2) Logging System
- **현상**: 모든 로그가 `print()`로 출력되어, 실제 운영 시 추적(Traceability)이 불가능합니다.
- **개선안**:
  - Python 표준 `logging` 모듈을 적용하고, 로그 레벨(INFO/DEBUG/ERROR)을 체계화해야 합니다.

### 3) Concurrency Safety
- **현상**: `global_kg`는 Thread-safe하지 않은 `networkx` 객체입니다. 여러 사용자가 동시 요청 시 충돌 가능성이 있습니다.
- **개선안**:
  - `threading.Lock`을 걸거나, 그래프 상태 관리를 DB에 전적으로 위임해야 합니다.

---

## 🟩 3. reasoning Engine Enhancement (추론 고도화)

### 1) Inverse Correlation Logic
- **현상**: `DATA_TREASURY_RATE_10Y`가 UP일 때 "DECREASE" 예측과 단순 비교하여 불일치 판정.
- **문제**: 금융에서는 "금리 상승 = 국채 가격 하락(매수 매력 하락? 혹은 가격 하락으로 인한 수요?)" 등 해석이 복잡합니다.
- **개선안**:
  - Knowledge Graph 엣지에 `correlation_type` (Positive/Negative) 속성을 추가하여, 데이터 검증 로직을 정교화해야 합니다.

### 2) 텍스트 증거(Evidence) 수집
- **현상**: 정량 데이터(API)만 확인하고 있음.
- **개선안**:
  - Google Search API 등을 연동하여, 관련 뉴스 기사 제목을 가져와 텍스트 증거(`EvidenceType.TEXT`)로 첨부하는 기능이 필요합니다.

---

## 🚀 우선순위 추천

가장 먼저 **"1. 설정 중앙화(Config)"** 와 **"2. 로깅(Logging)"** 을 적용하여 시스템의 기초 체력을 다지는 것을 추천합니다. 그 다음 **"LLM 연동"**을 해야 실제 다양한 입력 테스트가 가능합니다.
