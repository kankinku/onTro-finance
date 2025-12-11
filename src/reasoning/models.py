"""
Reasoning Sector 데이터 모델
"""
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import uuid


def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class QueryType(str, Enum):
    """질문 유형"""
    DIRECT_RELATION = "direct_relation"      # A가 B에 어떤 영향?
    CONDITIONED = "conditioned"              # A일 때 B는?
    CAUSAL = "causal"                        # 왜 B가 떨어졌는가?
    PREDICTIVE = "predictive"                # 앞으로 B는?
    COMPARISON = "comparison"                # A vs B?
    UNKNOWN = "unknown"


class ReasoningDirection(str, Enum):
    """추론 결과 방향"""
    POSITIVE = "+"
    NEGATIVE = "-"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


# ============================================================
# Query Parsing 출력
# ============================================================
class ParsedQuery(BaseModel):
    """Query Parsing 결과"""
    query_id: str = Field(default_factory=lambda: generate_id("Q"))
    original_query: str
    
    # 추출된 엔티티
    query_entities: List[str] = Field(default_factory=list)  # canonical IDs
    entity_names: Dict[str, str] = Field(default_factory=dict)  # id -> name
    
    # 질문 유형
    query_type: QueryType = QueryType.UNKNOWN
    
    # 파싱된 구조
    head_entity: Optional[str] = None  # 주체
    tail_entity: Optional[str] = None  # 대상
    condition_entities: List[str] = Field(default_factory=list)  # 조건
    
    # 프래그먼트
    fragments: List[str] = Field(default_factory=list)


# ============================================================
# Graph Retrieval 출력
# ============================================================
class RetrievedPath(BaseModel):
    """검색된 경로"""
    path_id: str = Field(default_factory=lambda: generate_id("PATH"))
    
    # 경로 노드들
    nodes: List[str]  # entity IDs
    node_names: List[str]  # entity names
    
    # 경로 상 엣지들
    edges: List[Dict[str, Any]] = Field(default_factory=list)
    
    # 출처
    source: str = "domain"  # domain, personal, mixed
    
    # 경로 메타
    path_length: int = 0
    has_conflict: bool = False


class RetrievalResult(BaseModel):
    """Graph Retrieval 결과"""
    query_id: str
    
    # 검색된 경로들
    direct_paths: List[RetrievedPath] = Field(default_factory=list)
    indirect_paths: List[RetrievedPath] = Field(default_factory=list)
    
    # Domain vs Personal
    domain_paths_count: int = 0
    personal_paths_count: int = 0
    
    # 검색 통계
    total_edges_retrieved: int = 0


# ============================================================
# Edge Weight Fusion 출력
# ============================================================
class FusedEdge(BaseModel):
    """융합된 엣지 가중치"""
    edge_id: str
    head_id: str
    tail_id: str
    relation_type: str
    sign: str
    
    # 가중치
    domain_weight: float = 0.0
    personal_weight: float = 0.0
    final_weight: float = 0.0
    
    # 구성 요소
    domain_conf: float = 0.0
    decay_factor: float = 0.0
    semantic_score: float = 0.0
    pcs_score: float = 0.0
    
    # 충돌 여부
    has_personal_conflict: bool = False


class FusedPath(BaseModel):
    """융합된 경로"""
    path_id: str
    nodes: List[str]
    
    # 융합된 엣지들
    fused_edges: List[FusedEdge] = Field(default_factory=list)
    
    # 경로 전체 가중치
    path_weight: float = 0.0
    path_sign: str = "+"


# ============================================================
# Path Reasoning 출력
# ============================================================
class PathReasoningResult(BaseModel):
    """단일 경로 추론 결과"""
    path_id: str
    nodes: List[str]
    node_names: List[str]
    
    # 추론 결과
    combined_sign: str  # +, -, neutral
    path_strength: float  # 0~1
    
    # 각 edge의 sign
    edge_signs: List[str] = Field(default_factory=list)
    edge_weights: List[float] = Field(default_factory=list)


class ReasoningResult(BaseModel):
    """전체 추론 결과"""
    query_id: str
    
    # 최종 결과
    direction: ReasoningDirection
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    
    # 사용된 경로들
    paths_used: List[PathReasoningResult] = Field(default_factory=list)
    strongest_path: Optional[PathReasoningResult] = None
    
    # 집계 정보
    positive_evidence: float = 0.0
    negative_evidence: float = 0.0
    
    # 충돌 정보
    conflicting_paths: int = 0


# ============================================================
# Conclusion Synthesizer 출력
# ============================================================
class ReasoningConclusion(BaseModel):
    """최종 결론"""
    query_id: str
    original_query: str
    
    # 자연어 결론
    conclusion_text: str
    explanation_text: str
    
    # 구조화된 결과
    direction: ReasoningDirection
    confidence: float
    
    # 설명 가능성
    strongest_path_description: str
    evidence_summary: str
    
    # 원본 추론 결과
    reasoning_result: Optional[ReasoningResult] = None
