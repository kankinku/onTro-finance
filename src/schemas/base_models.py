from typing import List, Optional, Dict, Any, Union
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime

# --- Enums ---

class PredicateType(str, Enum):
    INCREASES = "P_INCREASES"
    DECREASES = "P_DECREASES"
    CAUSES = "P_CAUSES"
    PREVENTS = "P_PREVENTS"
    CORRELATES_POS = "P_CORR_POS"
    CORRELATES_NEG = "P_CORR_NEG"
    HAS_PART = "P_HAS_PART"
    IS_A = "P_IS_A"

class EvidenceType(str, Enum):
    TEXT = "text"
    GRAPH = "graph"
    STATISTICAL = "statistical"

# --- Core Entities ---

class Term(BaseModel):
    term_id: str = Field(..., description="Unique Identifier, e.g., TERM_SLR_RULE")
    label: str = Field(..., description="Human readable label")
    aliases: List[str] = Field(default_factory=list, description="Synonyms")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="Metadata like category, definitions")

class Mechanism(BaseModel):
    mech_id: str
    label: str
    description: Optional[str] = None
    parent_id: Optional[str] = None

# --- Pipeline Intermediate Objects ---

class Fragment(BaseModel):
    fragment_id: str
    text: str
    fact: str
    mechanism_text: str
    condition_text: Optional[str] = None
    outcome_text: str
    term_candidates: List[str] = []
    mechanism_candidates: List[str] = []
    predicate_candidate: Optional[str] = None

class ResolvedEntity(BaseModel):
    surface_form: str
    entity_id: str
    entity_type: str # TERM or MECH
    confidence: float

# --- Ontology Relations ---

class Evidence(BaseModel):
    evidence_type: EvidenceType
    source_id: str # doc_id or api_endpoint
    value: Union[str, float, Dict[str, Any]]
    score: float = 0.0

class Rationale(BaseModel):
    ran_id: str
    mechanisms: List[Dict[str, Union[str, float]]] # list of {mech_id, weight}
    evidence: List[Evidence]
    summary: List[str]
    strength: float = 0.0

class Relation(BaseModel):
    rel_id: str
    subject_id: str
    predicate: PredicateType
    object_id: str
    conditions: Dict[str, Any] = Field(default_factory=dict, description="Time, market state conditions")
    rationale_ids: List[str] = []
    
class Chain(BaseModel):
    chain_id: str
    steps: List[Relation]
    confidence: float

# --- System Request/Response ---

class ScenarioInput(BaseModel):
    text: str
    context_date: Optional[datetime] = None

class InferredOutcome(BaseModel):
    outcome_text: List[str]
    path: List[Relation]
    confidence: float
