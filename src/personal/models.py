"""
Personal Sector 데이터 모델
"""
from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class PersonalRelevanceType(str, Enum):
    """Personal 관련성 타입"""
    EMOTIONAL = "emotional"      # 단순 감정
    HYPOTHESIS = "hypothesis"    # 가설
    INFERENCE = "inference"      # 추론
    OPINION = "opinion"          # 의견
    OBSERVATION = "observation"  # 관찰


class PersonalLabel(str, Enum):
    """PCS 기반 개인 지식 라벨"""
    STRONG_BELIEF = "strong_belief"    # PCS >= 0.7
    WEAK_BELIEF = "weak_belief"        # 0.4 <= PCS < 0.7
    NOISY_HYPOTHESIS = "noisy_hypothesis"  # PCS < 0.4


class SourceType(str, Enum):
    """지식 출처 타입"""
    USER_WRITTEN = "user_written"      # 사용자 직접 작성
    TEXT_REPORT = "text_report"        # 리포트에서 추출
    LLM_INFERRED = "llm_inferred"      # LLM 추론
    DOMAIN_REJECTED = "domain_rejected"  # Domain에서 거부됨


# ============================================================
# Personal Candidate (Intake 출력)
# ============================================================
class PersonalCandidate(BaseModel):
    """Personal 평가용 후보"""
    candidate_id: str = Field(default_factory=lambda: generate_id("PC"))
    
    # 원본 정보
    raw_edge_id: str
    head_canonical_id: str
    head_canonical_name: str
    tail_canonical_id: str
    tail_canonical_name: str
    
    # 관계 정보
    relation_type: str
    polarity: str
    
    # Validation/Domain 결과
    semantic_tag: str
    sign_tag: Optional[str] = None
    student_conf: float
    combined_conf: float
    
    # Personal 메타데이터
    user_id: str = Field(default="default_user")
    timestamp: datetime = Field(default_factory=datetime.now)
    source_type: SourceType = Field(default=SourceType.LLM_INFERRED)
    personal_origin_flag: bool = Field(default=True)
    
    # Relevance 분류
    relevance_type: Optional[PersonalRelevanceType] = None
    
    # 원문
    fragment_text: Optional[str] = None
    
    # 거부 이유 (Domain에서 온 경우)
    rejection_reason: Optional[str] = None


# ============================================================
# PCS Classifier 출력
# ============================================================
class PCSResult(BaseModel):
    """PCS Classifier 결과"""
    candidate_id: str
    
    # PCS 점수
    pcs_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    personal_label: PersonalLabel
    
    # 구성 요소
    domain_proximity: float = 0.0      # P1
    semantic_strength: float = 0.0     # P2
    user_origin_weight: float = 0.0    # P3
    consistency_score: float = 0.0     # P4
    
    # 가중치 적용 상세
    weighted_scores: Dict[str, float] = Field(default_factory=dict)


# ============================================================
# Personal KG 관계 (저장 단위)
# ============================================================
class PersonalRelation(BaseModel):
    """
    Personal KG에 저장되는 관계
    
    ⚠️ 핵심 원칙: 절대 삭제 없음
    - 모든 발생 이력을 히스토리로 유지
    - DriftAnalyzer를 위한 time-series 데이터 관리
    """
    relation_id: str = Field(default_factory=lambda: generate_id("PKG"))
    
    # 관계 정보
    head_id: str
    head_name: str
    tail_id: str
    tail_name: str
    relation_type: str
    sign: str
    
    # Personal 메타
    user_id: str
    pcs_score: float           # 최신 PCS
    personal_weight: float
    personal_label: PersonalLabel
    
    # 출처 및 시간
    source_type: SourceType
    created_at: datetime = Field(default_factory=datetime.now)
    last_occurred_at: datetime = Field(default_factory=datetime.now)  # 마지막 발생
    
    # 패턴 추적
    occurrence_count: int = Field(default=1)
    relevance_types: List[str] = Field(default_factory=list)
    
    # Domain 관련
    domain_conflict: bool = Field(default=False)         # Domain과 충돌 여부
    domain_conflict_count: int = Field(default=0)        # 충돌 횟수
    promotion_candidate: bool = Field(default=False)
    
    # PCS 히스토리 (time-series for DriftAnalyzer)
    pcs_history: List[Dict[str, Any]] = Field(default_factory=list)
    # 구조: [{"timestamp": datetime, "pcs": float, "label": str}, ...]
    
    # 전체 히스토리 (삭제 없이 추적)
    history: List[Dict[str, Any]] = Field(default_factory=list)
    # 구조: [{"timestamp": datetime, "source": str, "pcs": float, "conflict": bool}, ...]
    
    # Drift 플래그
    drift_flag: bool = Field(default=False)


# ============================================================
# Personal Drift/Promotion 출력
# ============================================================
class PersonalDriftResult(BaseModel):
    """Personal Drift Analyzer 결과"""
    relation_id: str
    
    # Drift 신호
    drift_signal: float = Field(default=0.0, ge=0.0, le=1.0)
    is_promotion_candidate: bool = False
    
    # 구성 요소
    pcs_factor: float = 0.0
    consistency_factor: float = 0.0
    domain_gap_factor: float = 0.0
    time_factor: float = 0.0
    
    # Static Domain 충돌 여부
    static_conflict: bool = False
    
    # 프로모션 상태
    can_promote: bool = False
    promotion_reason: Optional[str] = None


# ============================================================
# Personal Pipeline 최종 결과
# ============================================================
class PersonalProcessResult(BaseModel):
    """Personal Sector 전체 처리 결과"""
    candidate_id: str
    raw_edge_id: str
    
    # 최종 결정
    stored_in_pkg: bool
    personal_weight: float
    personal_label: PersonalLabel
    
    # 각 단계 결과
    intake_result: Optional[PersonalCandidate] = None
    pcs_result: Optional[PCSResult] = None
    pkg_relation_id: Optional[str] = None
    drift_result: Optional[PersonalDriftResult] = None
    
    # 프로모션 상태
    promotion_pending: bool = False
