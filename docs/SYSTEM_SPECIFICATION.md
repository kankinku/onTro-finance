# Ontology System - 설계 명세서 v2.0

## 시스템 개요

| 항목 | 값 |
|------|-----|
| Layer 수 | 6개 |
| Core Logic Modules | 22개 |
| Pipeline Orchestrators | 6개 |
| 테스트 | 58개 |

---

## 모듈 유형 분리

### Core Logic Modules (22개)
- 비즈니스 로직을 담당
- Unit Test 대상 (입력 -> 출력 검증)

### Pipeline Orchestrators (6개)
- Core 모듈 조합 + 순서 제어 + 에러 핸들링
- Integration Test 대상 (flow, fallback 등)
- **비즈니스 로직 없음**

---

## Data Architecture (데이터 분리 원칙)

### 1. Domain Data (불변 · 뼈대)
- **성격**: 시스템의 "기본 지식 (Baseline Ontology)". 경제 개념, 고정된 정의. Read-only.
- **저장 위치**: `data/domain/` (`entities.json`, `relations.json`)
- **Node Label**: `:DomainEntity`, `domain` namespace
- **규칙**:
  - 절대로 raw PDF ingest가 Domain 구조를 직접 수정하거나 덮어쓰지 않음.
  - 시스템 시작 시 로드되며, 런타임에는 변경되지 않음 (학습은 별도 Offline Process).

### 2. Personal/Ingest Data (가변 · 살)
- **성격**: 실시간 사건 데이터, 증거 (Evidence). Noisy, Time-sensitive.
- **저장 위치**:
  - Raw: `data/raw/` (PDF 원본)
  - Extract: `data/personal/` (Fragments, Chunks, Personal KG)
- **Node Label**: `:PersonalEntity`, `personal` namespace
- **규칙**:
  - 모든 Ingest 데이터는 이곳에 저장됨.
  - 삭제되지 않으며(No Delete), Domain 위에서 보완적 증거로 활용됨.

### 3. Reasoning 시 Merge
- **Reasoning**: Domain KG(불변) + Personal KG(가변) = **Fused Graph**
- **Domain First**: 충돌 시 Domain 정의가 우선하지만, Personal Evidence는 맥락으로 제공됨.

---


## Layer 1: Extraction

**목적**: 원본 텍스트에서 엔티티와 관계 추출

### Core Modules (4개)

#### 1.1 FragmentExtractor
- **파일**: `src/extraction/fragment_extractor.py`
- **입력**: 원본 텍스트
- **처리**: 문장 분할 + Noise 필터 + Quality 태깅
- **출력**: `Fragment[]`

#### 1.2 NERStudent (Student1)
- **파일**: `src/extraction/ner_student.py`
- **입력**: Fragment
- **처리**: 
  - **Rule 기반**: 패턴매칭 + 정규식 + 키워드 (Recall 우선)
  - **(선택) NER Student 모델**: Distillation 결과
  - 초기에는 Rule-only, 이후 모델로 확장 가능
- **출력**: `EntityCandidate[]`

#### 1.3 EntityResolver
- **파일**: `src/extraction/entity_resolver.py`
- **입력**: EntityCandidate
- **처리**: 5단계 우선순위 (Dict->Static->Dynamic->Personal->Fuzzy)
- **출력**: `ResolvedEntity`

#### 1.4 RelationExtractor (Student2)
- **파일**: `src/extraction/relation_extractor.py`
- **입력**: Fragment + Entity[]
- **처리**:
  - **Rule 기반**: 관계 패턴 인식 (safety net)
  - **(선택) Student2 모델**: 관계/Polarity 추론 (표현력)
  - Rule + Model 병렬 사용 구조
- **출력**: `RawEdge[]`

### Pipeline Orchestrator (1개)

#### 1.5 ExtractionPipeline
- Core 4개 모듈 순차 실행
- 에러 시 partial result 반환

---

## Layer 2: Validation

**목적**: RawEdge의 타당성 검증
**책임 범위**: `usable_edge` vs `drop_edge` 구분만 수행
**[NOTE] Domain/Personal 분기는 Layer 3/4의 책임**

### Core Modules (4개)

#### 2.1 SchemaValidator
- **파일**: `src/validation/schema_validator.py`
- **처리**: 필수필드/형식/타입 검증
- **출력**: `SchemaValidationResult`

#### 2.2 SignValidator
- **파일**: `src/validation/sign_validator.py`
- **처리**: 정적규칙 + KG일관성 + 부호태그
- **출력**: `SignValidationResult`

#### 2.3 SemanticValidator
- **파일**: `src/validation/semantic_validator.py`
- **처리**: 도메인적합성 + 타입호환 + 시간논리
- **출력**: `SemanticValidationResult`

#### 2.4 ConfidenceFilter
- **파일**: `src/validation/confidence_filter.py`
- **처리**: 
  - Combined Confidence 계산
  - **usable_edge (통과) vs drop_edge (폐기) 구분만 수행**
  - [NOTE] Domain/Personal 힌트는 제공하되, 최종 분기는 상위 Layer
- **출력**: `ValidationResult` (validation_passed, combined_conf, destination_hint)

### Pipeline Orchestrator (1개)

#### 2.5 ValidationPipeline
- Core 4개 모듈 순차 실행
- **입력**: RawEdge (Extraction에서)
- **출력**: ValidationResult (usable 여부 + 힌트)

---

## Layer 3: Domain (The Baseline)

**목적**: 보편적/불변 지식 (Baseline Ontology) 관리
**성격**: **Read-Only** (런타임 Ingest에 의해 수정되지 않음)
**입력 조건**: Validation을 통과한 usable_edge
**책임**: 입력된 Edge가 Domain 지식과 일치하는지 확인 (Confirmation)

### Core Modules (5개)

#### 3.1 DomainCandidateIntake
- **파일**: `src/domain/intake.py`
- **처리**: 입력 Edge가 기존 Domain Ontology에 존재하는지 확인.
- **출력**: `DomainMatchResult` (Match/Unknown/Conflict)

#### 3.2 StaticDomainGuard
- **파일**: `src/domain/static_guard.py`
- **처리**: 절대 규칙 충돌 검사
- **출력**: `StaticGuardResult`
- **Config**: `config/static_domain.yaml`

#### 3.3 (Legacy) DynamicDomainUpdate -> Offline Learner로 이동
- **[변경]**: 런타임에 Domain KG를 직접 업데이트하지 않음.
- **처리**: Domain과 일치하는 Evidence가 들어오면, **Personal Layer**에 "Domain Confirmation" 태그와 함께 저장하거나, 별도 로그로 남겨 Offline 학습에 활용.

#### 3.4 ConflictAnalyzer
- **파일**: `src/domain/conflict_analyzer.py`
- **처리**: Domain 지식과 상충하는지 확인.
- **출력**: Conflict 리포트 (Personal Layer 저장용)

#### 3.5 DomainDriftDetector
- **파일**: `src/domain/drift_detector.py`
- **처리**: (장기) Domain과 다른 패턴의 빈도 분석 -> Learning Layer로 신호 전달

### Pipeline Orchestrator (1개)

#### 3.6 DomainPipeline
- **순서**: Validated Edge -> Static Check -> Domain Match Check -> **All passed to Personal Layer** (with tags)
- **핵심**: Domain Layer는 "저장"하지 않고 "검증/태깅"만 수행. 실제 저장은 Personal Layer (또는 오프라인 학습) 가 담당.

---

## Layer 4: Personal (The Flesh)

**목적**: 개인 가설, 실시간 Evidence, Ingest 데이터 저장
**성격**: **Mutable & Append-Only** (삭제 없음, 구조 위 살 붙이기)
**입력 조건**: 모든 Validated Edge (Domain 일치 여부와 무관하게 증거로서 저장 가능)

### Core Modules (4개)

#### 4.1 PersonalCandidateIntake
- **파일**: `src/personal/intake.py`
- **처리**: 메타데이터 + Relevance 분류
- **출력**: `PersonalCandidate`

#### 4.2 PCSClassifier
- **파일**: `src/personal/pcs_classifier.py`
- **처리**: 
  - P1 (Domain Proximity)
  - P2 (Semantic Strength)
  - P3 (User Origin)
  - P4 (Consistency)
  - `PCS = w1*P1 + w2*P2 + w3*P3 + w4*P4`
- **출력**: `PCSResult` (STRONG/WEAK/NOISY)

#### 4.3 PersonalKGUpdate
- **파일**: `src/personal/pkg_update.py`
- **처리**:
  - **절대 삭제 없음** (핵심 원칙)
  - 동일 relation에 대해:
    - `occurrence_count++`
    - `last_occurred_at` 갱신
    - **PCS 히스토리 저장** (time-series)
    - **Domain conflict 여부 tag 추가**
  - DriftAnalyzer를 위한 히스토리 관리
- **출력**: `PersonalRelation` (with full history)

#### 4.4 PersonalDriftAnalyzer
- **파일**: `src/personal/drift_promotion.py`
- **처리**: 
  - PKGUpdate의 히스토리 기반 분석
  - drift_signal 계산 + Static충돌검사
  - Domain 승격 후보 판단
- **출력**: `PersonalDriftResult`

### Pipeline Orchestrator (1개)

#### 4.5 PersonalPipeline
- Core 4개 모듈 순차 실행

---

## Layer 5: Reasoning

**목적**: 그래프 기반 인과 추론

### Core Modules (5개)

#### 5.1 QueryParser
- **파일**: `src/reasoning/query_parser.py`
- **처리**: Fragment분리 + NER/ER 재사용 + QueryType분류
- **출력**: `ParsedQuery`

#### 5.2 GraphRetrieval
- **파일**: `src/reasoning/graph_retrieval.py`
- **처리**: 
  - **Domain-first** 원칙 구현
  - Direct검색 + BFS Multi-hop
- **출력**: `RetrievalResult`

#### 5.3 EdgeWeightFusion (EES)
- **파일**: `src/reasoning/edge_fusion.py`
- **처리**: 
  ```
  W_D = domain_conf * (1 - decay) * semantic_score
  W_P = PCS * personal_weight 
        (Domain 존재 시 * 0.3 감쇠)
  
  추가 반영 요소:
  - evidence_count 가중
  - gold_flag 보너스
  
  최종: W = W_D + W_P
  (Domain-Personal sign 충돌 시 -> Personal 무시)
  ```
- **출력**: `FusedPath`

#### 5.4 PathReasoningEngine
- **파일**: `src/reasoning/path_reasoning.py`
- **처리**: Sign곱셈 + 강도곱셈 + Multi-path집계
- **출력**: `ReasoningResult`

#### 5.5 ConclusionSynthesizer
- **파일**: `src/reasoning/conclusion.py`
- **처리**: 구조화결론 + 경로설명 + LLM다듬기
- **출력**: `ReasoningConclusion`

### Pipeline Orchestrator (1개)

#### 5.6 ReasoningPipeline
- Core 5개 모듈 순차 실행

---

## Layer 6: Learning/Evolution

**목적**: 시스템 자동/반자동 개선 (투명하게)

### L1. TrainingDatasetBuilder
- **파일**: `src/learning/dataset_builder.py`
- **처리**: 로그수집 + Task별분리 + 출처별신뢰도 + 스냅샷
- **출력**: `DatasetSnapshot` (버전 관리, frozen)

### L2. TeacherGoldsetManager
- **파일**: `src/learning/goldset_manager.py`
- **처리**: Teacher라벨(LLM) + GoldSet(사람) + 버전관리
- **출력**: `GoldSet` (append only)

### L3. StudentValidatorTrainer
- **파일**: `src/learning/trainer.py`
- **처리**: Run단위관리 + Before/After메트릭
- **출력**: `TrainingRun`
- **[NOTE] 필수 포함 정보**:
  - `dataset_version_id`
  - `goldset_version_id`
  - `policy_config_version_id`
  - `base_model_version`
  - `metrics_before`, `metrics_after`

### L4. PolicyWeightLearner
- **파일**: `src/learning/policy_learner.py`
- **처리**: EES/PCS/Threshold 조정 + Variant버전관리
- **출력**: `PolicyConfig`
- **Config**: `config/policy/` 디렉토리 (별도 관리)

### L5. ReviewDeploymentManager (**Write 전용**)
- **파일**: `src/learning/deployment.py`
- **역할**: ConfigBundle 상태 전이 담당
- **처리**:
  - PROPOSED -> REVIEWED -> DEPLOYED / ROLLED_BACK
  - DB에 상태 쓰기
- **출력**: `ConfigBundle`
  - 필수 포함: `(student1_v, student2_v, validator_v, policy_v)`

### L6. LearningDashboard (**Read Only**)
- **파일**: `src/learning/dashboard.py`
- **역할**: 조회만, **상태 변경 없음**
- **출력**:
  - Version Dashboard
  - Training Registry
  - Quality Reports

---

## Config 파일 분리

### 환경 설정 (settings)
| 파일 | 용도 |
|------|------|
| `config/settings.py` | 경로/리소스/운영 환경 |

### 스키마 정의
| 파일 | 용도 |
|------|------|
| `config/entity_types.yaml` | 엔티티 타입 |
| `config/relation_types.yaml` | 관계 타입 |
| `config/alias_dictionary.yaml` | 별칭 사전 |
| `config/validation_schema.yaml` | 검증 규칙 |
| `config/static_domain.yaml` | 절대 불변 규칙 |

### 정책 설정 (버전 관리)
| 파일 | 용도 |
|------|------|
| `config/policy/policy_v1.yaml` | EES/PCS weight, threshold |
| `config/policy/policy_v2.yaml` | (학습으로 갱신) |

---

## 핵심 원칙 -> 구현 매핑

| 원칙 | 구현 책임 모듈 |
|------|--------------|
| **Domain First** | `Reasoning.GraphRetrieval`, `EdgeFusion(EES)` |
| **No Delete in Personal** | `Personal.PKGUpdate` |
| **Transparent Learning** | `Learning.DatasetBuilder`, `Trainer`, `Dashboard` |
| **Human in the Loop** | `Learning.Deployment` (REVIEWED 상태 필수) |
| **One Source of Truth** | Config 구조 + DomainKG schema |

---

## 테스트 분류

### Unit Tests (Core Modules)
| Layer | 대상 | 테스트 수 |
|-------|------|----------|
| Extraction | 4 Core | 8 |
| Validation | 4 Core | 10 |
| Domain | 5 Core | 8 |
| Personal | 4 Core | 7 |
| Reasoning | 5 Core | 9 |
| Learning | 5 Core | 5 |
| **소계** | **27** | **47** |

### Integration Tests (Pipelines)
| Layer | 대상 | 테스트 수 |
|-------|------|----------|
| Extraction | Pipeline | 2 |
| Validation | Pipeline | 2 |
| Domain | Pipeline | 2 |
| Personal | Pipeline | 2 |
| Reasoning | Pipeline | 2 |
| Learning | Dashboard | 1 |
| **소계** | **6** | **11** |

**총합: 58개**

---

## Layer 간 책임 경계

```
Layer 1 (Extraction)
  -> RawEdge 생성
       |
Layer 2 (Validation)
  -> usable vs drop 구분만
       |
       +-> drop -> 로그
       |
       +-> usable + hint
            |
            +-> Layer 3 (Domain)
            |     -> Domain 저장 or Personal 전달
            |
            +-> Layer 4 (Personal)
                  -> 삭제 없이 저장 + 히스토리
                       |
Layer 5 (Reasoning)
  -> Domain-first로 검색 + 추론
       |
Layer 6 (Learning)
  -> 로그 수집 -> 학습 -> 리뷰 -> 배포
```

---

**Core Modules: 22개 | Orchestrators: 6개 | Tests: 58개 | Layers: 6개**
