# OntoFin System v5.0 - 아키텍처 및 코드 설계서

## 📋 변경 이력
- **v5.0.0** (2025-12-07): 원칙 기반 코드 리팩토링 완료
- **v4.1.0** (2025-12-06): Strong Ontology 구현
- **v4.0.0** (2025-12-05): 초기 프로토타입

---

## 1. 프로젝트 개요

본 프로젝트는 금융 텍스트를 구조화된 온톨로지(Ontology) 형태로 변환하여 학습하고, 
이를 기반으로 시장 시나리오를 추론 자동화하는 시스템입니다.

## 2. 기술 스택 (Tech Stack)

| 분류 | 기술 |
|------|------|
| Language | Python 3.10+ |
| Web Framework | FastAPI (비동기 처리 및 API 제공) |
| Data Model | Pydantic v2 (엄격한 타입 검증) |
| Graph Database | NetworkX (In-memory) / Neo4j (향후) |
| LLM | Ollama (Local LLM) |
| Task Queue | Python asyncio (Background Tasks) |

## 3. 디렉토리 구조 (v5.0 Refactored)

```
onTro-finance/
├── .env                          # 환경 변수 (민감 정보)
├── requirements.txt              # Python 의존성
├── start_server.bat              # 서버 시작 스크립트
│
├── config/                       # [NEW] 설정 중앙화
│   ├── __init__.py
│   ├── settings.py               # Pydantic 기반 환경 설정
│   └── constants.py              # 상수/매직넘버 집중 관리
│
├── data/                         # [NEW] 데이터 파일 통합
│   ├── cache/                    # 모든 캐시 파일 (market, pairs 등)
│   └── graphs/                   # 그래프 영속성 데이터
│
├── docs/                         # [NEW] 문서
│   ├── ARCHITECTURE.md
│   └── IMPROVEMENT_PLAN.md
│
├── src/
│   ├── main.py                   # FastAPI 진입점
│   │
│   ├── api/                      # [REFACTORED] API 레이어
│   │   ├── __init__.py           # Backward compatibility
│   │   ├── routes/               # [NEW] 라우트 분리
│   │   │   ├── __init__.py       # 라우터 통합
│   │   │   ├── graph_routes.py   # 그래프 API
│   │   │   ├── market_routes.py  # 시장 데이터 API
│   │   │   ├── pair_routes.py    # 페어 트레이딩 API
│   │   │   └── scenario_routes.py # 시나리오 학습/추론 API
│   │   ├── market_data.py        # Market 데이터 프로바이더
│   │   ├── market_indices.py     # 지수 데이터
│   │   └── pair_trading.py       # 페어 트레이딩 분석기
│   │
│   ├── services/                 # [NEW] 비즈니스 로직 레이어
│   │   ├── __init__.py
│   │   ├── llm_service.py        # LLM 호출 서비스
│   │   └── kg_service.py         # Knowledge Graph 서비스
│   │
│   ├── core/                     # 공유 유틸리티
│   │   ├── config.py             # DEPRECATED → config.settings 사용
│   │   ├── logger.py             # 로깅 설정
│   │   ├── database.py           # Neo4j 커넥터 (Mock)
│   │   ├── knowledge_graph.py    # NetworkX 그래프 래퍼
│   │   └── llm_setup.py          # DEPRECATED → services.llm_service 사용
│   │
│   ├── pipeline/                 # 학습 파이프라인
│   │   ├── m1_analyzer.py        # 텍스트 분석 (LLM)
│   │   ├── m2_entity_resolver.py # 엔티티 해결
│   │   └── m3_relation.py        # 관계 구축
│   │
│   ├── reasoning/                # 추론 엔진
│   │   ├── simulator.py          # 시나리오 시뮬레이션
│   │   └── temporal_integrator.py
│   │
│   ├── schemas/                  # Pydantic 데이터 모델
│   │   ├── base_models.py        # 핵심 엔티티 (Term, Relation 등)
│   │   └── ontology.py           # 온톨로지 스키마
│   │
│   ├── scripts/                  # 유틸리티 스크립트
│   │   └── init_db.py
│   │
│   └── static/                   # 프론트엔드 HTML
│       ├── index.html
│       ├── graph.html
│       ├── detail.html
│       ├── pair_trading.html
│       └── scenario.html
│
└── tests/                        # 테스트
    └── test_strong_ontology.py
```

## 4. 적용된 설계 원칙

### ✅ One Source of Truth
- 모든 캐시 파일이 `data/cache/`에 통합
- 그래프 데이터는 `data/graphs/`에 집중

### ✅ Configuration Separation
- 모든 설정값은 `config/settings.py`에서 관리
- 하드코딩된 상수는 `config/constants.py`로 이동

### ✅ Single Responsibility Principle (SRP)
- `api/routes/`: 라우트만 담당 (비즈니스 로직 없음)
- `services/`: 비즈니스 로직 담당
- `core/`: 공통 유틸리티

### ✅ Shared Layer 규칙
- 공통 유틸리티만 `core/`에 위치
- 재사용되지 않는 로직은 해당 도메인 모듈에 유지

## 5. API 엔드포인트 구조

| Prefix | Router | 설명 |
|--------|--------|------|
| `/api/v1/graph` | graph_routes | 지식 그래프 조회 |
| `/api/v1/market` | market_routes | 시장 데이터 |
| `/api/v1/scenario` | scenario_routes | 학습/추론 |
| `/api/v1/pair` | pair_routes | 페어 트레이딩 |

## 6. 향후 개선 사항

1. **Neo4j 실제 연동**: Mock DB → Production DB
2. **Vector Search**: Entity Resolution에 FAISS/ChromaDB 도입
3. **테스트 커버리지**: pytest 기반 단위/통합 테스트 확대
4. **프론트엔드**: React/Vue 기반 SPA로 마이그레이션

---
**작성일**: 2025-12-07  
**버전**: v5.0.0  
**작성자**: Antigravity Assistant
