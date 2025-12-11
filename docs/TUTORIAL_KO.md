# 🚀 온톨로지 시스템 시작하기 (Getting Started)

이 문서는 온톨로지 시스템을 처음부터 설정하고 실행하는 방법을 단계별로 설명합니다.

---

## 1. 환경 설정 (Installation)

### 필수 요구 사항
- Python 3.9 이상
- (선택) Ollama (LLM 기능을 사용하기 위해 필요)

### 설치
프로젝트 루트 디렉토리에서 의존성을 설치합니다.

```bash
# 가상환경 생성 (선택)
python -m venv venv
# Windows
.\venv\Scripts\activate
# Mac/Linux
source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt
```

---

## 2. 도메인 데이터 준비 (Domain Setup)

**중요**: 이 시스템은 **Domain Data(불변의 뼈대)** 와 **Personal Data(가변의 살)** 를 엄격히 구분합니다.
시스템을 실행하기 전에, 핵심이 되는 경제 지식(Domain Ontology)을 먼저 정의해야 합니다.

### 데이터 위치
- `data/domain/entities.json`: 핵심 개념 정의
- `data/domain/relations.json`: 핵심 인과관계 정의

> **참고**: 이미 예제 파일이 생성되어 있습니다. 필요시 수정하여 사용하세요.

#### 예시: entities.json
```json
[
    { "id": "interest_rate", "props": { "name": "금리", "type": "indicator" } },
    { "id": "growth_stock", "props": { "name": "성장주", "type": "asset" } }
]
```

#### 예시: relations.json
```json
[
    {
        "head_id": "interest_rate",
        "tail_id": "growth_stock",
        "type": "affect",
        "props": { "sign": "-", "domain_conf": 0.9 }
    }
]
```
(해석: 금리가 오르면 성장주는 하락한다)

---

## 3. 문서 수집 (Ingestion)

이제 시스템에 새로운 정보(뉴스, 리포트 등)를 주입합니다. 이 데이터는 **Personal Layer**에 저장되며, 절대 Domain을 덮어쓰지 않습니다.

### 방법 1: `main.py` 실행 (기본)
`main.py`는 `data/samples/sample_documents.json`에 있는 예제 문서를 읽어 파이프라인을 돌립니다.

```bash
python main.py
```

### 실행 과정
1. **Bootstrap**: `data/domain/`의 데이터를 로드하여 지식 그래프의 뼈대를 만듭니다.
2. **Phase 1 (Collection)**: 문서를 읽고 지식을 추출합니다.
   - 추출된 지식이 Domain과 일치하면 -> 확인(Confirm)
   - 새로운 지식이거나 충돌하면 -> **Personal KG**에 저장 (Evidence)
3. **Phase 2 (Reasoning)**: 질문에 대해 Domain 지식과 Personal 증거를 합쳐 추론합니다.

---

## 4. 데이터 확인 (Verification)

시스템이 실행되면 로그를 통해 데이터가 어디에 저장되었는지 확인할 수 있습니다.

### 로그 해석
- `loaded 4 domain entities...`: 초기 도메인 데이터 로드 성공
- `Upserted personal relation`: 문서에서 추출된 새로운 지식이 Personal Layer에 저장됨
- `Blocked attempt to modify Domain KG`: (안전장치) 문서 데이터가 감히 Domain을 수정하려다 차단됨 (정상)

### 저장소 위치
- `data/graph.db`: (현재 InMemory/Pickle) 전체 지식 그래프 저장소
- `data/personal/`: 추출된 Fragment 및 메타데이터

---

## 5. 질문 및 추론 (Reasoning)

`main.py` 하단부에서 추론 예제를 볼 수 있습니다.

```python
test_queries = [
    "금리가 오르면 성장주는 어떻게 되나요?"
]
```

### 추론 로직
1. **Domain First**: 금리 -> 성장주 관계가 Domain에 있는지 먼저 확인합니다. (정답: -)
2. **Personal Supplement**: 최근 뉴스에서 "금리 인상에도 성장주가 올랐다"는 증거가 있다면, 이를 Personal Layer에서 가져옵니다.
3. **Fusion**: 두 정보를 합쳐 최종 결론을 내립니다. ("원래는 하락하는게 맞지만, 최근엔 다를 수 있음" 등)

---

## 6. 개발 가이드

- **새로운 로직 추가**: `src/` 폴더 내 각 레이어(extraction, domain, personal, reasoning)를 수정하세요.
- **설정 변경**: `config/settings.py`에서 임계값이나 경로를 수정하세요.
- **데이터 초기화**: `data/graph.db`를 삭제하면 초기화됩니다. (Domain 데이터는 json 파일이 원본이므로 안전합니다)
