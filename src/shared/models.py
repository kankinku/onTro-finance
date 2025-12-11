"""
데이터 모델 정의
원칙 1: One Source of Truth - 모든 데이터 구조는 여기서 단 한 번만 정의
"""
from enum import Enum
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


def generate_id(prefix: str) -> str:
    """고유 ID 생성"""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class QualityTag(str, Enum):
    """Fragment 품질 태그"""
    INFORMATIVE = "informative"      # 정보가 풍부한 조각
    NOISY = "noisy"                  # 노이즈 (감탄문 등)
    UNCLEAR = "unclear"              # 의미가 불명확
    EMOTIONAL = "emotional"          # 감정적 표현
    INCOMPLETE = "incomplete"        # 불완전한 문장


class ResolutionMode(str, Enum):
    """Entity Resolution 결과 모드"""
    DICTIONARY_MATCH = "dictionary_match"    # alias table에서 매칭
    STATIC_DOMAIN = "static_domain"          # Static Domain KG에서 매칭
    DYNAMIC_DOMAIN = "dynamic_domain"        # Dynamic Domain KG에서 매칭
    PERSONAL_ALIAS = "personal_alias"        # 개인 alias에서 매칭
    FUZZY_MATCH = "fuzzy_match"              # Embedding 유사도 매칭
    AMBIGUOUS = "ambiguous"                  # 모호함 (후보 다수)
    NEW_ENTITY = "new_entity"                # 새로운 엔티티 후보


class Polarity(str, Enum):
    """관계의 극성"""
    POSITIVE = "+"
    NEGATIVE = "-"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


# ============================================================
# Fragment Extraction Module 출력
# ============================================================
class Fragment(BaseModel):
    """
    의미 단위로 분할된 텍스트 조각
    Fragment Extraction Module의 출력
    """
    fragment_id: str = Field(default_factory=lambda: generate_id("F"))
    text: str = Field(..., description="fragment 텍스트")
    doc_id: str = Field(..., description="원본 문서 ID")
    timestamp: datetime = Field(default_factory=datetime.now)
    quality_tag: QualityTag = Field(default=QualityTag.INFORMATIVE)
    
    # 추적용 메타데이터
    source_start: Optional[int] = Field(default=None, description="원문에서의 시작 위치")
    source_end: Optional[int] = Field(default=None, description="원문에서의 끝 위치")
    
    class Config:
        use_enum_values = True


# ============================================================
# Student1 (NER) Module 출력
# ============================================================
class EntityCandidate(BaseModel):
    """
    NER로 추출된 엔티티 후보
    Student1 Module의 출력
    """
    entity_id: str = Field(default_factory=lambda: generate_id("E_temp"))
    surface_text: str = Field(..., description="원문에서 추출된 표현")
    type_guess: str = Field(..., description="추정된 엔티티 타입")
    normalized_name_guess: Optional[str] = Field(default=None, description="추정된 정규화 이름")
    
    # 위치 정보 (문맥 복원용)
    span_start: int = Field(..., description="fragment 내 시작 위치")
    span_end: int = Field(..., description="fragment 내 끝 위치")
    
    # 신뢰도
    student_conf: float = Field(default=0.0, ge=0.0, le=1.0)
    
    # 출처 추적
    fragment_id: str = Field(..., description="소속 fragment ID")


# ============================================================
# Entity Resolution Module 출력
# ============================================================
class ResolvedEntity(BaseModel):
    """
    Canonical 엔티티로 매핑된 결과
    Entity Resolution Module의 출력
    """
    entity_id: str = Field(..., description="원본 엔티티 ID (E_temp_xxx)")
    
    # 성공적 매핑
    canonical_id: Optional[str] = Field(default=None, description="Canonical 엔티티 ID")
    canonical_name: Optional[str] = Field(default=None, description="Canonical 이름")
    canonical_type: Optional[str] = Field(default=None, description="Canonical 타입")
    
    # Resolution 정보
    resolution_mode: ResolutionMode
    resolution_conf: float = Field(default=0.0, ge=0.0, le=1.0)
    
    # 모호한 경우 (ambiguous)
    candidate_ids: Optional[List[str]] = Field(default=None)
    candidate_confs: Optional[List[float]] = Field(default=None)
    
    # 신규 엔티티 후보
    is_new_entity_candidate: bool = Field(default=False)
    
    # 원본 정보 유지
    surface_text: str = Field(..., description="원문 표현 (추적용)")
    fragment_id: str = Field(..., description="소속 fragment ID")


# ============================================================
# Student2 (Relation Extraction) Module 출력
# ============================================================
class RawEdge(BaseModel):
    """
    추출된 원석 엣지 (검증 전)
    Student2 Module의 출력
    """
    raw_edge_id: str = Field(default_factory=lambda: generate_id("R"))
    
    # 관계 구성
    head_entity_id: str = Field(..., description="Head 엔티티 ID")
    head_canonical_name: Optional[str] = Field(default=None)
    tail_entity_id: str = Field(..., description="Tail 엔티티 ID")
    tail_canonical_name: Optional[str] = Field(default=None)
    
    # 관계 정보
    relation_type: str = Field(..., description="관계 타입 (Affect, Cause 등)")
    polarity_guess: Polarity = Field(default=Polarity.UNKNOWN)
    
    # 신뢰도
    student_conf: float = Field(default=0.0, ge=0.0, le=1.0)
    
    # 조건 (ConditionalOn 관계 등에서 사용)
    condition_text: Optional[str] = Field(default=None, description="조건 텍스트")
    
    # 출처 추적
    fragment_id: str = Field(..., description="소속 fragment ID")
    fragment_text: Optional[str] = Field(default=None, description="원문 (검증용)")
    
    # 생성 시간
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        use_enum_values = True


# ============================================================
# 파이프라인 전체 결과
# ============================================================
class ExtractionResult(BaseModel):
    """Extraction Sector 전체 파이프라인 결과"""
    doc_id: str
    fragments: List[Fragment]
    entity_candidates: List[EntityCandidate]
    resolved_entities: List[ResolvedEntity]
    raw_edges: List[RawEdge]
    
    # 통계
    processing_time_ms: float = Field(default=0.0)
    error_count: int = Field(default=0)
    warning_messages: List[str] = Field(default_factory=list)
