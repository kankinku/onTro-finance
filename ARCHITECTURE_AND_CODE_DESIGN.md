# 온톨로지 기반 금융 시나리오 학습·추론 시스템 (OntoFin) - 구현 설계서

## 1. 프로젝트 개요
본 프로젝트는 금융 텍스트를 구조화된 온톨로지(Ontology) 형태로 변환하여 학습하고, 이를 기반으로 시장 시나리오를 추론 자동화하는 시스템입니다.

## 2. 기술 스택 (Tech Stack)
- **Language**: Python 3.10+
- **Web Framework**: FastAPI (비동기 처리 및 API 제공)
- **Data Model**: Pydantic v2 (엄격한 타입 검증 및 JSON Schema 변환)
- **Graph Database**: Neo4j (Graph storage) / NetworkX (In-memory analysis)
- **LLM Integration**: LangChain 또는 OpenAI SDK, Google Generative AI SDK (Custom implementation)
- **Task Queue**: Celery or Python asyncio (for parallel pipeline processing M1~M8)

## 3. 디렉토리 구조 (Directory Structure)

```
ontofin_system/
├── config/                 # 설정 파일 (DB, API Keys)
├── docs/                   # 설계 문서
├── src/
│   ├── main.py             # FastAPI 진입점
│   ├── schemas/            # 공통 데이터 모델 (TERM, MECH, REL 등)
│   ├── core/               # 공통 유틸리티 (Graph Wrapper, Logger)
│   ├── pipeline/           # 학습 파이프라인 (M1~M8 Orchestrator)
│   │   ├── m1_analyzer.py
│   │   ├── m2_entity_resolver.py
│   │   ├── m3_relation.py
│   │   ├── m4_evidence.py
│   │   ├── m5_rationale.py
│   │   ├── m6_integrator.py
│   │   ├── m7_consistency.py
│   │   └── m8_validation.py
│   ├── reasoning/          # 추론 엔진 v4
│   │   ├── scenario_parser.py
│   │   ├── path_assembler.py
│   │   ├── temporal_integrator.py
│   │   └── simulator.py
│   └── api/                # External Data Connectors (FRED, Bloomberg mock)
└── tests/                  # 유닛 테스트
```

## 4. 데이터 스키마 설계 (Python Pydantic)

### 4.1 핵심 엔티티
- **FactFragment**: 문장에서 추출된 Fact/Mech/Cond/Outcome
- **Term**: 금융 용어 객체 (ID, Surface, Aliases)
- **Mechanism**: 인과 메커니즘 (ID, Description, Category)
- **Relation (REL)**: Subject -> Predicate -> Object (with conditions)
- **Rationale (RAN)**: 관계의 근거, 가중치, 증거 목록

## 5. 모듈별 상세 구현 계획

### [M1] Input Analyzer
- **Role**: 텍스트 전처리 및 LLM 기반 IE(Information Extraction).
- **Strategy**: Few-shot 프롬프트를 사용하여 JSON 포맷 강제 출력.

### [M2] Entity Resolver
- **Role**: 추출된 텍스트(Surface Form)를 정규화된 ID로 변환.
- **Strategy**: Vector Search (Embedding) + Fuzzy Matching.

### [Reasoning Engine]
- **Role**: 저장된 지식 그래프를 기반으로 새로운 시나리오의 파급 효과 시뮬레이션.
- **Flow**: Fragment Parsing -> Path Finding -> Temporal Merging -> Outcome Generation.

---
**작성일**: 2025-12-06
**작성자**: Antigravity Assistant
