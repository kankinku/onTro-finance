"""
Learning / Evolution Layer 데이터 모델
"""
from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class DataSource(str, Enum):
    """데이터 출처"""
    DOMAIN_STATIC = "domain_static"       # Static Domain 기반 (신뢰도 1.0)
    DOMAIN_DYNAMIC = "domain_dynamic"     # Dynamic Domain 기반 (0.7~0.9)
    PERSONAL = "personal"                 # Personal KG 기반 (0.4)
    VALIDATION_LOG = "validation_log"     # Validation 실패 로그 (0.6)
    DRIFT_LOG = "drift_log"               # Drift 로그 (0.6)
    USER_QA = "user_qa"                   # 사용자 직접 피드백 (0.9)
    TEACHER_LLM = "teacher_llm"           # Teacher LLM 라벨 (0.7)


class TaskType(str, Enum):
    """학습 태스크 유형"""
    NER = "ner"                           # Named Entity Recognition
    RELATION = "relation_extraction"       # Relation Extraction
    SIGN_VALIDATION = "sign_validation"   # Sign Validator
    SEMANTIC_VALIDATION = "semantic_validation"  # Semantic Validator
    POLICY = "policy"                     # Policy/Weight 학습


class RunStatus(str, Enum):
    """학습 Run 상태"""
    PROPOSED = "proposed"       # 학습 완료, 미적용
    REVIEWED = "reviewed"       # 리뷰 완료 (승인/거절)
    DEPLOYED = "deployed"       # 현재 운영 중
    ROLLED_BACK = "rolled_back"  # 롤백됨


# ============================================================
# L1. Training Dataset
# ============================================================
class TrainingSample(BaseModel):
    """개별 학습 샘플"""
    sample_id: str = Field(default_factory=lambda: generate_id("SAMP"))
    
    # 입력
    text: str
    fragment_id: Optional[str] = None
    
    # 라벨 (task별로 다름)
    task_type: TaskType
    labels: Dict[str, Any] = Field(default_factory=dict)
    
    # 메타데이터
    source: DataSource
    label_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=datetime.now)
    
    # 출처 상세
    source_edge_id: Optional[str] = None
    source_relation_id: Optional[str] = None


class DatasetSnapshot(BaseModel):
    """학습 데이터셋 스냅샷"""
    dataset_id: str = Field(default_factory=lambda: generate_id("DS"))
    version: str  # "2025-01-10_v1"
    
    # 태스크
    task_type: TaskType
    
    # 샘플
    samples: List[TrainingSample] = Field(default_factory=list)
    sample_count: int = 0
    
    # 통계
    source_distribution: Dict[str, int] = Field(default_factory=dict)
    avg_label_confidence: float = 0.0
    
    # 시간
    created_at: datetime = Field(default_factory=datetime.now)
    frozen: bool = False  # True면 수정 불가


# ============================================================
# L2. Teacher & Goldset
# ============================================================
class TeacherLabel(BaseModel):
    """Teacher LLM 라벨"""
    label_id: str = Field(default_factory=lambda: generate_id("TL"))
    
    sample_id: str
    task_type: TaskType
    
    # LLM 정보
    model_name: str
    prompt_version: str
    temperature: float
    
    # 라벨
    predicted_labels: Dict[str, Any]
    
    created_at: datetime = Field(default_factory=datetime.now)


class GoldSample(BaseModel):
    """Gold Set 샘플 (사람 검증)"""
    gold_id: str = Field(default_factory=lambda: generate_id("GOLD"))
    
    # 원본
    text: str
    task_type: TaskType
    
    # 정답 라벨 (사람이 검증)
    gold_labels: Dict[str, Any]
    
    # 메타
    reviewer: str = "human"
    reviewed_at: datetime = Field(default_factory=datetime.now)
    difficulty: str = "normal"  # easy, normal, hard
    domain_category: str = "general"


class GoldSet(BaseModel):
    """Gold Set 버전"""
    goldset_id: str = Field(default_factory=lambda: generate_id("GS"))
    version: str  # "gold_v1"
    
    task_type: TaskType
    samples: List[GoldSample] = Field(default_factory=list)
    
    # 통계
    sample_count: int = 0
    difficulty_distribution: Dict[str, int] = Field(default_factory=dict)
    domain_distribution: Dict[str, int] = Field(default_factory=dict)
    
    created_at: datetime = Field(default_factory=datetime.now)
    is_active: bool = True


# ============================================================
# L3. Training Run
# ============================================================
class TrainingMetrics(BaseModel):
    """학습 평가 메트릭"""
    # NER/RE
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1: Optional[float] = None
    
    # Classification
    accuracy: Optional[float] = None
    
    # 상세
    confusion_matrix: Optional[Dict[str, Dict[str, int]]] = None
    
    # 시스템 영향
    static_conflict_count: int = 0
    drift_detection_rate: float = 0.0


class TrainingRun(BaseModel):
    """학습 실행 기록"""
    run_id: str = Field(default_factory=lambda: generate_id("RUN"))
    
    # 학습 대상
    target: str  # student1, student2, sign_validator, semantic_validator
    
    # 사용한 데이터
    dataset_version: str
    goldset_version: str
    teacher_labels_version: Optional[str] = None
    
    # 하이퍼파라미터
    hyperparameters: Dict[str, Any] = Field(default_factory=dict)
    
    # 모델 버전
    base_model_version: str
    new_model_version: str
    
    # Before/After 메트릭
    metrics_before: Optional[TrainingMetrics] = None
    metrics_after: Optional[TrainingMetrics] = None
    
    # 상태
    status: RunStatus = RunStatus.PROPOSED
    
    # 시간
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    deployed_at: Optional[datetime] = None
    
    # 리뷰
    review_notes: Optional[str] = None
    reviewer: Optional[str] = None


# ============================================================
# L4. Policy Config
# ============================================================
class PolicyConfig(BaseModel):
    """정책 설정"""
    config_id: str = Field(default_factory=lambda: generate_id("POL"))
    version: str
    
    # EES 가중치
    ees_weights: Dict[str, float] = Field(default_factory=lambda: {
        "domain": 0.4,
        "personal": 0.2,
        "semantic": 0.15,
        "temporal": 0.1,
        "validation": 0.1,
        "graph": 0.05,
    })
    
    # PCS 가중치
    pcs_weights: Dict[str, float] = Field(default_factory=lambda: {
        "domain_proximity": 0.25,
        "semantic_strength": 0.3,
        "user_origin": 0.2,
        "consistency": 0.25,
    })
    
    # Thresholds
    thresholds: Dict[str, float] = Field(default_factory=lambda: {
        "domain_candidate": 0.55,
        "personal_candidate": 0.35,
        "drift_signal": 0.6,
        "promotion": 0.8,
    })
    
    # Path reasoning
    path_length_penalty: float = 0.1
    max_path_length: int = 4
    
    # 메타
    created_at: datetime = Field(default_factory=datetime.now)
    is_active: bool = False
    notes: str = ""


# ============================================================
# L5. Deployment
# ============================================================
class ConfigBundle(BaseModel):
    """전체 설정 번들"""
    bundle_id: str = Field(default_factory=lambda: generate_id("BUNDLE"))
    version: str  # config_bundle_v10
    
    # 각 컴포넌트 버전
    student1_version: str
    student2_version: str
    sign_validator_version: str
    semantic_validator_version: str
    policy_version: str
    schema_version: str
    
    # 상태
    status: RunStatus = RunStatus.PROPOSED
    
    # 시간
    created_at: datetime = Field(default_factory=datetime.now)
    deployed_at: Optional[datetime] = None
    
    # 리뷰
    review_notes: Optional[str] = None


# ============================================================
# Dashboard/Report 모델
# ============================================================
class QualityReport(BaseModel):
    """품질 리포트"""
    report_id: str = Field(default_factory=lambda: generate_id("RPT"))
    report_type: str  # domain, personal, reasoning
    
    generated_at: datetime = Field(default_factory=datetime.now)
    period_start: datetime
    period_end: datetime
    
    # 메트릭
    metrics: Dict[str, Any] = Field(default_factory=dict)
    
    # 주요 발견
    highlights: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
