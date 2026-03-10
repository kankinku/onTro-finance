"""Bridge evaluated news payloads into source documents and trust signals."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha1
from typing import Any, Tuple

from pydantic import BaseModel, Field

from src.shared.models import Polarity


class NewsImpactPayload(BaseModel):
    driver: str
    target: str
    direction: str
    confidence: float = Field(ge=0.0, le=1.0)
    signal: str
    sentence: str
    rationale: str


class NewsEvaluatePayload(BaseModel):
    headline: str
    source: str | None = None
    published_at: datetime | None = None
    novelty: str
    overall_assessment: str
    categories: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    impact_count: int = 0
    impacts: list[NewsImpactPayload] = Field(default_factory=list)
    summary: str
    requires_manual_review: bool
    stored: bool = False
    evaluated_at: datetime
    body: str = ""


def build_news_doc_id(payload: NewsEvaluatePayload) -> str:
    raw = "|".join(
        [
            payload.headline.strip(),
            payload.source or "unknown-source",
            payload.published_at.isoformat() if payload.published_at else "unknown-published-at",
        ]
    )
    return f"news_{sha1(raw.encode('utf-8')).hexdigest()[:12]}"


def build_news_ingest_text(payload: NewsEvaluatePayload) -> str:
    impact_lines = []
    for impact in payload.impacts:
        relation_text = "supports" if impact.direction == "positive" else "pressures"
        impact_lines.append(
            f"{impact.driver} {relation_text} {impact.target}. Signal: {impact.signal}. Evidence: {impact.sentence}"
        )

    sections = [
        f"Headline: {payload.headline}",
        f"Summary: {payload.summary}",
        f"Assessment: {payload.overall_assessment}",
        f"Novelty: {payload.novelty}",
    ]
    if payload.body:
        sections.append(f"Body: {payload.body}")
    if impact_lines:
        sections.append("Impacts:\n" + "\n".join(impact_lines))
    return "\n\n".join(sections)


def build_news_metadata(payload: NewsEvaluatePayload, doc_id: str) -> dict[str, Any]:
    return {
        "doc_id": doc_id,
        "title": payload.headline,
        "source": payload.source,
        "source_type": "news_eval",
        "published_at": payload.published_at.isoformat() if payload.published_at else None,
        "language": "en",
        "document_quality_tier": "B" if payload.requires_manual_review else "A",
        "categories": payload.categories,
        "entities": payload.entities,
        "impact_count": payload.impact_count,
        "overall_assessment": payload.overall_assessment,
        "novelty": payload.novelty,
        "requires_manual_review": payload.requires_manual_review,
        "evaluated_at": payload.evaluated_at.isoformat(),
        "news_impacts": [impact.model_dump(mode="json") for impact in payload.impacts],
    }


def strongest_impact(payload: NewsEvaluatePayload) -> NewsImpactPayload | None:
    if not payload.impacts:
        return None
    return max(payload.impacts, key=lambda impact: impact.confidence)


def impact_to_relation_fields(impact: NewsImpactPayload) -> Tuple[str, Polarity]:
    relation_type = "supports" if impact.direction == "positive" else "pressures"
    polarity = Polarity.POSITIVE if impact.direction == "positive" else Polarity.NEGATIVE
    return relation_type, polarity
