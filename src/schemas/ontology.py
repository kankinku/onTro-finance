from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# --- Enums ---

class EntityType(str, Enum):
    INDICATOR = "INDICATOR"       # 금리, 환율, 지수 등 (수치형)
    POLICY_EVENT = "POLICY_EVENT" # 금리 인상, 양적 완화 등
    MARKET_EVENT = "MARKET_EVENT" # 어닝 쇼크, 전쟁 등
    STRUCTURAL = "STRUCTURAL"     # 추상적 개념 (유동성, 리스크 선호)
    UNKNOWN = "UNKNOWN"

class RelationKind(str, Enum):
    CAUSAL = "CAUSAL"             # A가 B를 유발 (인과)
    PROPORTIONAL = "PROPORTIONAL" # A와 B는 비례/반비례 (함수 관계)
    CORRELATED = "CORRELATED"     # 단순 상관 (인과 불명)
    STRUCTURAL = "STRUCTURAL"     # 구성 요소 (A는 B의 일부)

# --- Value Models ---

class QuantitativeEffect(BaseModel):
    """
    정량적 효과 모델
    sign: +1 (양의 관계/증가), -1 (음의 관계/감소)
    strength: 0.0 ~ 1.0 (연결 강도/확신도)
    lag_days: 효과가 나타나기까지의 지연 시간 (일 단위, 없으면 0)
    """
    sign: int = Field(..., description="1 for positive correlation/increase, -1 for negative/decrease")
    strength: float = Field(default=1.0, ge=0.0, le=1.0)
    lag_days: Optional[int] = Field(default=0)

# --- Core Ontology Models ---

class OntologyNode(BaseModel):
    """
    Graph Node (Entity)
    """
    id: str = Field(..., description="Unique ID (e.g., ENT_RATE_HIKE)")
    name: str = Field(..., description="Human readable name (e.g., 금리 인상)")
    type: EntityType = Field(default=EntityType.UNKNOWN)
    description: Optional[str] = None
    
    # Optional metadata (synonyms, ticker, etc.)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class OntologyRelation(BaseModel):
    """
    Graph Edge (Relation)
    """
    id: str
    from_id: str
    to_id: str
    kind: RelationKind
    effect: QuantitativeEffect
    
    # Conditional logic (e.g., "Only valid when VIX > 30")
    condition: Optional[str] = None
    
    # Source trace (Which document/fragment generated this)
    source_fragment_id: Optional[str] = None

# --- Pipeline Transfer Objects ---

class ResolvedRelationCandidate(BaseModel):
    """
    M2 Result -> M3 Input
    """
    subject_node: OntologyNode
    object_node: OntologyNode
    kind: RelationKind
    effect: QuantitativeEffect
    condition: Optional[str] = None
