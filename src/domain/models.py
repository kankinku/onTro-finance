"""
Domain Sector 데이터 모델
"""
from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class DomainAction(str, Enum):
    """Domain 처리 액션"""
    STRENGTHEN_STATIC = "strengthen_static_evidence"
    REJECT_TO_PERSONAL = "reject_to_personal"
    REJECT_TO_LOG = "reject_to_log"
    CREATE_NEW = "create_new_relation"
    UPDATE_EXISTING = "update_existing"
    TRIGGER_CONFLICT = "trigger_conflict_resolution"
    MARK_DRIFT = "mark_drift_candidate"


class ConflictType(str, Enum):
    """충돌 유형"""
    SIGN_CONFLICT = "sign_conflict"               # +/- 충돌
    TYPE_CONFLICT = "relation_type_conflict"      # Affect vs Cause 등
    CONDITIONAL_CONFLICT = "conditional_conflict"  # 조건부 충돌
    PATH_CONFLICT = "path_conflict"               # 경로 기반 충돌


class ConflictResolution(str, Enum):
    """충돌 해결 결과"""
    KEEP_EXISTING = "keep_existing"       # 기존 유지
    REPLACE = "replace"                   # 새 것으로 교체
    MERGE = "merge"                       # 병합
    TO_PERSONAL = "to_personal"           # Personal로 이동
    TO_DRIFT = "to_drift_candidate"       # Drift 후보


# ============================================================
# Domain Candidate (Intake 출력)
# ============================================================
class DomainCandidate(BaseModel):
    """Domain 평가용 정규화된 엣지"""
    candidate_id: str = Field(default_factory=lambda: generate_id("DC"))
    
    # 원본 정보
    raw_edge_id: str
    head_canonical_id: str
    head_canonical_name: str
    tail_canonical_id: str
    tail_canonical_name: str
    
    # 확정된 관계 정보
    relation_type: str
    polarity: str  # +, -, neutral
    
    # Validation 결과 유지
    semantic_tag: str
    combined_conf: float
    student_conf: float
    
    # Domain 메타데이터
    timestamp: datetime = Field(default_factory=datetime.now)
    freq_count: int = Field(default=1)
    evidence_source: str = Field(default="student")  # student, user, llm, teacher
    
    # 원문 (추적용)
    fragment_text: Optional[str] = None


# ============================================================
# Static Guard 출력
# ============================================================
class StaticGuardResult(BaseModel):
    """Static Domain Guard 결과"""
    candidate_id: str
    static_pass: bool
    static_conflict: bool = False
    action: DomainAction
    
    # 충돌 상세
    conflict_rule_id: Optional[str] = None
    expected_polarity: Optional[str] = None
    actual_polarity: Optional[str] = None
    conflict_reason: Optional[str] = None


# ============================================================
# Dynamic Domain 관계 (저장 단위)
# ============================================================
class DynamicRelation(BaseModel):
    """Dynamic Domain에 저장되는 관계"""
    relation_id: str = Field(default_factory=lambda: generate_id("DYN"))
    
    # 관계 정보
    head_id: str
    head_name: str
    tail_id: str
    tail_name: str
    relation_type: str
    sign: str  # +, -, neutral
    
    # 신뢰도 및 증거
    domain_conf: float = Field(default=0.5)
    evidence_count: int = Field(default=1)
    conflict_count: int = Field(default=0)
    
    # 시간 정보
    created_at: datetime = Field(default_factory=datetime.now)
    last_update: datetime = Field(default_factory=datetime.now)
    
    # 메타데이터
    origin: str = Field(default="student")
    semantic_tags: List[str] = Field(default_factory=list)
    
    # Decay 관련
    decay_applied: bool = Field(default=False)
    
    # Drift 관련
    drift_flag: bool = Field(default=False)
    need_conflict_resolution: bool = Field(default=False)


# ============================================================
# Dynamic Update 출력
# ============================================================
class DynamicUpdateResult(BaseModel):
    """Dynamic Domain Update 결과"""
    candidate_id: str
    relation_id: str
    action: DomainAction
    
    # 업데이트 상세
    domain_conf: float
    evidence_count: int
    decayed: bool = False
    conflict_pending: bool = False
    is_new: bool = False
    
    # 이전 값 (업데이트 시)
    previous_conf: Optional[float] = None
    previous_evidence_count: Optional[int] = None


# ============================================================
# Conflict Analysis 출력
# ============================================================
class ConflictAnalysisResult(BaseModel):
    """Conflict Analyzer 결과"""
    candidate_id: str
    relation_id: str
    
    # 충돌 정보
    has_conflict: bool
    conflict_type: Optional[ConflictType] = None
    resolution: ConflictResolution
    
    # 상세
    existing_sign: Optional[str] = None
    new_sign: Optional[str] = None
    existing_evidence: int = 0
    new_evidence: int = 0
    
    # Path consistency (있는 경우)
    path_consistent: bool = True
    inconsistent_path: Optional[List[str]] = None


# ============================================================
# Drift Detection 출력
# ============================================================
class DriftDetectionResult(BaseModel):
    """Domain Drift Detector 결과"""
    relation_id: str
    
    # Drift 신호
    drift_signal: float = Field(default=0.0, ge=0.0, le=1.0)
    is_drift_candidate: bool = False
    
    # 구성 요소
    conflict_score: float = 0.0
    opposite_rate: float = 0.0
    decay_score: float = 0.0
    semantic_score: float = 0.0
    
    # QA 필요 여부
    needs_qa: bool = False
    suggested_question: Optional[str] = None


# ============================================================
# Domain Pipeline 최종 결과
# ============================================================
class DomainProcessResult(BaseModel):
    """Domain Sector 전체 처리 결과"""
    candidate_id: str
    raw_edge_id: str
    
    # 최종 결정
    final_destination: str  # "domain", "personal", "log"
    
    # 각 단계 결과
    intake_result: Optional[DomainCandidate] = None
    static_result: Optional[StaticGuardResult] = None
    dynamic_result: Optional[DynamicUpdateResult] = None
    conflict_result: Optional[ConflictAnalysisResult] = None
    drift_result: Optional[DriftDetectionResult] = None
    
    # 최종 관계 ID (Domain에 저장된 경우)
    domain_relation_id: Optional[str] = None
