"""
Validation 관련 데이터 모델 추가
"""
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field


class SignTag(str, Enum):
    """Sign Validator 결과 태그"""
    CONFIDENT = "confident"      # 패턴·도메인·LLM 모두 일치
    AMBIGUOUS = "ambiguous"      # 어느 정도 근거 있으나 불확실
    SUSPECT = "suspect"          # 도메인 규칙과 충돌
    UNKNOWN = "unknown"          # 문장 자체가 방향성 없음


class SemanticTag(str, Enum):
    """Semantic Validator 결과 태그"""
    SEM_CONFIDENT = "sem_confident"    # 문맥·도메인·LLM 모두 OK
    SEM_WEAK = "sem_weak"              # 가능하지만 증거 부족
    SEM_SPURIOUS = "sem_spurious"      # 인과 과장/상관을 인과로 해석
    SEM_WRONG = "sem_wrong"            # 도메인과 정면 배치
    SEM_AMBIGUOUS = "sem_ambiguous"    # 여러 해석 가능


class ValidationDestination(str, Enum):
    """Validation 결과 목적지"""
    DOMAIN_CANDIDATE = "domain_candidate"
    PERSONAL_CANDIDATE = "personal_candidate"
    DROP_LOG = "drop_log"


# ============================================================
# Schema Validator 출력
# ============================================================
class SchemaValidationResult(BaseModel):
    """Schema Validator 결과"""
    edge_id: str
    schema_valid: bool
    schema_errors: List[str] = Field(default_factory=list)
    
    # 검증 상세
    has_required_fields: bool = True
    relation_type_valid: bool = True
    entity_pair_valid: bool = True
    no_self_loop: bool = True


# ============================================================
# Sign Validator 출력
# ============================================================
class SignValidationResult(BaseModel):
    """Sign Validator 결과"""
    edge_id: str
    polarity_final: str  # +, -, neutral, unknown
    sign_tag: SignTag
    sign_consistency_score: float = Field(default=0.0, ge=0.0, le=1.0)
    
    # 검증 상세
    pattern_polarity: Optional[str] = None
    domain_polarity: Optional[str] = None
    llm_polarity: Optional[str] = None
    conflict_with_static: bool = False


# ============================================================
# Semantic Validator 출력
# ============================================================
class SemanticValidationResult(BaseModel):
    """Semantic Validator 결과"""
    edge_id: str
    semantic_tag: SemanticTag
    semantic_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    
    # 검증 상세
    has_exaggeration: bool = False
    is_correlation_as_causation: bool = False
    has_weak_evidence: bool = False
    domain_conflict: bool = False
    llm_judgement: Optional[str] = None  # valid, weak, spurious, wrong, ambiguous


# ============================================================
# Confidence Filter 출력 (최종 결과)
# ============================================================
class ValidationResult(BaseModel):
    """
    Validation 최종 결과
    
    ⚠️ 책임 범위:
    - validation_passed: usable_edge vs drop_edge 구분 (Validation 책임)
    - destination: Domain/Personal 힌트 제공 (최종 결정은 Layer 3/4)
    """
    edge_id: str
    validation_passed: bool  # usable (True) vs drop (False)
    
    # destination은 "힌트"임 - 최종 결정은 Domain/Personal Layer
    destination: ValidationDestination  # 권장 목적지
    
    # 점수
    combined_conf: float = Field(default=0.0, ge=0.0, le=1.0)
    student_conf: float = 0.0
    sign_score: float = 0.0
    semantic_conf: float = 0.0
    
    # 각 Validator 결과
    schema_result: Optional[SchemaValidationResult] = None
    sign_result: Optional[SignValidationResult] = None
    semantic_result: Optional[SemanticValidationResult] = None
    
    # 실패 이유 (실패 시)
    rejection_reason: Optional[str] = None
    rejection_details: List[str] = Field(default_factory=list)
