"""Council models for ambiguous relation adjudication."""
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class CouncilAutoDecision(str, Enum):
    AUTO_APPROVE = "AUTO_APPROVE"
    AUTO_REJECT = "AUTO_REJECT"
    SEND_TO_COUNCIL = "SEND_TO_COUNCIL"


class CandidateStatus(str, Enum):
    CREATED = "CREATED"
    AUTO_EVALUATED = "AUTO_EVALUATED"
    AUTO_APPROVED = "AUTO_APPROVED"
    AUTO_REJECTED = "AUTO_REJECTED"
    COUNCIL_PENDING = "COUNCIL_PENDING"
    COUNCIL_APPROVED = "COUNCIL_APPROVED"
    COUNCIL_REJECTED = "COUNCIL_REJECTED"
    COUNCIL_DEFERRED = "COUNCIL_DEFERRED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


class BaselineConflict(str, Enum):
    NONE = "NONE"
    TYPE_CONFLICT = "TYPE_CONFLICT"
    POLARITY_CONFLICT = "POLARITY_CONFLICT"
    STRENGTH_CONFLICT = "STRENGTH_CONFLICT"
    TIME_SCOPE_CONFLICT = "TIME_SCOPE_CONFLICT"


class CouncilTriggerReason(str, Enum):
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    TYPE_AMBIGUITY = "TYPE_AMBIGUITY"
    POLARITY_AMBIGUITY = "POLARITY_AMBIGUITY"
    BASELINE_CONTRADICTION = "BASELINE_CONTRADICTION"
    MULTI_SOURCE_DISAGREEMENT = "MULTI_SOURCE_DISAGREEMENT"
    TEMPORAL_UNCERTAINTY = "TEMPORAL_UNCERTAINTY"
    HIGH_IMPACT_RELATION = "HIGH_IMPACT_RELATION"
    NEW_PATTERN = "NEW_PATTERN"


class CouncilRole(str, Enum):
    PROPOSER = "proposer"
    CHALLENGER = "challenger"
    EVIDENCE_AUDITOR = "evidence_auditor"
    CONSTRAINT_AUDITOR = "constraint_auditor"
    NEUTRAL_VOTER = "neutral_voter"
    ADJUDICATOR = "adjudicator"


class CouncilDecision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    DEFER = "DEFER"


class CouncilCaseStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class CitationSpan(BaseModel):
    text: str = ""
    start_char: Optional[int] = None
    end_char: Optional[int] = None


class CandidateEntityRef(BaseModel):
    entity_id: str
    canonical_name: str
    entity_type: Optional[str] = None
    entity_subtype: Optional[str] = None
    normalization_confidence: Optional[float] = None


class RelationTypeScore(BaseModel):
    type: str
    score: float = Field(default=0.0, ge=0.0, le=1.0)


class CouncilTurn(BaseModel):
    turn: int
    role: CouncilRole
    agent_id: str
    claim: str
    decision: Optional[CouncilDecision] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    evidence: Optional[str] = None
    risk: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class CouncilVote(BaseModel):
    agent_id: str
    decision: CouncilDecision
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""
    created_at: datetime = Field(default_factory=datetime.now)


class RelationCandidate(BaseModel):
    candidate_id: str = Field(default_factory=lambda: generate_id("rc"))
    version: int = 1
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    source_document_id: str
    chunk_id: str
    source_type: str = "research_note"
    source_metadata: Dict[str, Any] = Field(default_factory=dict)
    citation_span: CitationSpan = Field(default_factory=CitationSpan)

    head_entity: CandidateEntityRef
    tail_entity: CandidateEntityRef
    entity_pair_key: str

    relation_type_candidate: str
    relation_type_alternatives: List[RelationTypeScore] = Field(default_factory=list)
    polarity_candidate: str = "unknown"
    strength_candidate: float = Field(default=0.0, ge=0.0, le=1.0)
    time_scope_candidate: str = "unknown"
    conditionality: Optional[str] = None

    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    validation_score: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    auto_decision: CouncilAutoDecision = CouncilAutoDecision.SEND_TO_COUNCIL
    auto_decision_reason: str = ""

    baseline_relation_exists: bool = False
    baseline_relation_type: Optional[str] = None
    baseline_polarity: Optional[str] = None
    baseline_conflict: BaselineConflict = BaselineConflict.NONE
    novelty_score: float = Field(default=0.0, ge=0.0, le=1.0)

    council_required: bool = False
    council_trigger_reasons: List[CouncilTriggerReason] = Field(default_factory=list)
    council_case_id: Optional[str] = None
    council_turns: List[CouncilTurn] = Field(default_factory=list)
    council_votes: List[CouncilVote] = Field(default_factory=list)
    council_summary: Optional[str] = None

    status: CandidateStatus = CandidateStatus.CREATED
    final_relation_type: Optional[str] = None
    final_polarity: Optional[str] = None
    final_strength: Optional[float] = None
    final_confidence: Optional[float] = None
    decision_reason: Optional[str] = None
    decision_trace_id: Optional[str] = None


class CouncilCase(BaseModel):
    case_id: str = Field(default_factory=lambda: generate_id("case"))
    candidate_id: str
    trigger_reasons: List[CouncilTriggerReason] = Field(default_factory=list)
    status: CouncilCaseStatus = CouncilCaseStatus.OPEN
    defer_count: int = 0
    turns: List[CouncilTurn] = Field(default_factory=list)
    votes: List[CouncilVote] = Field(default_factory=list)
    final_decision: Optional[CouncilDecision] = None
    summary: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
