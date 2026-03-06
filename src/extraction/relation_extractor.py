"""
Relation extraction for finance-oriented relation candidates.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from config.settings import get_settings
from src.llm.ollama_client import OllamaClient
from src.shared.exceptions import RelationExtractionError
from src.shared.models import Polarity, RawEdge, ResolvedEntity, ResolutionMode

logger = logging.getLogger(__name__)


POSITIVE_POLARITY_PATTERNS = [
    "rise",
    "higher",
    "increase",
    "boost",
    "support",
    "benefit",
    "stronger",
    "wider",
    "tailwind",
    "recover",
    "recovery",
    "improve",
    "상승",
    "인상",
    "강세",
    "지지",
    "수혜",
    "개선",
    "회복",
    "확대",
    "우호",
    "호재",
    "도움",
]

NEGATIVE_POLARITY_PATTERNS = [
    "fall",
    "lower",
    "decline",
    "pressure",
    "pressures",
    "drag",
    "weigh",
    "weaker",
    "compress",
    "headwind",
    "slowdown",
    "downside",
    "하락",
    "약세",
    "부담",
    "압박",
    "압력",
    "역풍",
    "하방압력",
    "둔화",
    "축소",
    "악화",
    "부정",
]

RELATION_PATTERNS = {
    "leads_to": [
        "lead to",
        "leads to",
        "result in",
        "results in",
        "drive",
        "drives",
        "cause",
        "causes",
        "이어지",
        "초래",
        "유발",
        "만들",
        "끌어올리",
        "낳",
    ],
    "pressures": [
        "pressure",
        "pressures",
        "drag on",
        "weigh on",
        "headwind",
        "압박",
        "부담",
        "역풍",
        "하방압력",
        "압력",
    ],
    "supports": [
        "support",
        "supports",
        "benefit",
        "benefits",
        "tailwind",
        "지지",
        "수혜",
        "도움",
        "우호적",
        "호재",
        "회복",
    ],
    "priced_in": ["priced in", "already priced", "fully reflected"],
    "reprices": ["reprice", "reprices", "repricing", "재평가", "리프라이싱"],
    "signals": ["signal", "signals", "indicate", "indicates", "point to", "points to", "시사", "의미"],
    "hedges": ["hedge", "hedges", "protect against"],
    "offsets": ["offset", "offsets", "cushion", "상쇄", "완충"],
    "correlates_with": [
        "correlate",
        "correlates",
        "moves with",
        "linked with",
        "associated with",
        "동행",
        "연동",
    ],
    "depends_on": ["depends on", "dependent on", "sensitive to", "민감", "좌우"],
    "exposed_to": ["exposed to", "exposure to", "노출"],
}


class RelationExtractor:
    """Student2: relation extraction with finance-friendly defaults."""

    def __init__(self, llm_client: Optional[OllamaClient] = None):
        self.settings = get_settings()
        self.llm_client = llm_client
        self._relation_types = self._load_relation_types()

    def _load_relation_types(self) -> Dict[str, Any]:
        try:
            return self.settings.load_yaml_config("relation_types")
        except FileNotFoundError:
            return {"relation_types": {"affects": {}, "leads_to": {}, "depends_on": {}}}

    def extract(
        self,
        fragment_text: str,
        fragment_id: str,
        resolved_entities: List[ResolvedEntity],
        use_llm: bool = True,
    ) -> List[RawEdge]:
        if not fragment_text:
            raise RelationExtractionError(message="Empty fragment", fragment_id=fragment_id)

        valid_entities = [
            entity
            for entity in resolved_entities
            if entity.resolution_mode != ResolutionMode.NEW_ENTITY and entity.canonical_id
        ]

        if len(valid_entities) < 2:
            return []

        try:
            if use_llm and self.llm_client:
                return self._extract_with_llm(fragment_text, fragment_id, valid_entities)
            return self._extract_rule_based(fragment_text, fragment_id, valid_entities)
        except RelationExtractionError:
            raise
        except Exception as exc:
            raise RelationExtractionError(message=str(exc), fragment_id=fragment_id) from exc

    def _extract_with_llm(self, text: str, fragment_id: str, entities: List[ResolvedEntity]) -> List[RawEdge]:
        relation_types = list(self._relation_types.get("relation_types", {}).keys())
        entity_info = [
            {"id": entity.entity_id, "name": entity.canonical_name, "surface": entity.surface_text}
            for entity in entities
        ]

        system_prompt = (
            "You extract structured finance relations from text. "
            f"Allowed relation types: {relation_types}. "
            "Return JSON in the form "
            "{\"relations\": [{\"head_id\": \"...\", \"tail_id\": \"...\", "
            "\"type\": \"...\", \"polarity\": \"+|-|neutral|unknown\", \"confidence\": 0.0}]}"
        )
        prompt = f"Text: {text}\nEntities: {entity_info}"

        try:
            result = self.llm_client.generate_json(prompt=prompt, system_prompt=system_prompt)
            entity_map = {entity.entity_id: entity for entity in entities}
            edges: List[RawEdge] = []

            for relation in result.get("relations", []):
                head_id = relation.get("head_id")
                tail_id = relation.get("tail_id")
                if head_id not in entity_map or tail_id not in entity_map:
                    continue

                head = entity_map[head_id]
                tail = entity_map[tail_id]
                polarity_raw = relation.get("polarity", "unknown")
                polarity = (
                    Polarity(polarity_raw)
                    if polarity_raw in {"+", "-", "neutral", "unknown"}
                    else Polarity.UNKNOWN
                )

                edges.append(
                    RawEdge(
                        head_entity_id=head_id,
                        head_canonical_name=head.canonical_name,
                        tail_entity_id=tail_id,
                        tail_canonical_name=tail.canonical_name,
                        relation_type=relation.get("type", "affects"),
                        polarity_guess=polarity,
                        student_conf=float(relation.get("confidence", 0.5)),
                        fragment_id=fragment_id,
                        fragment_text=text,
                    )
                )

            return edges
        except Exception as exc:
            logger.warning("LLM relation extraction failed: %s", exc)
            return self._extract_rule_based(text, fragment_id, entities)

    def _extract_rule_based(
        self,
        text: str,
        fragment_id: str,
        entities: List[ResolvedEntity],
    ) -> List[RawEdge]:
        if len(entities) < 2:
            return []

        lower_text = text.lower()
        polarity, polarity_strength = self._determine_polarity(lower_text)
        relation_type, signal_start, signal_end = self._determine_relation_signal(lower_text)
        if polarity == Polarity.UNKNOWN and relation_type == "pressures":
            polarity = Polarity.NEGATIVE
            polarity_strength = max(polarity_strength, 0.05)
        elif polarity == Polarity.UNKNOWN and relation_type == "supports":
            polarity = Polarity.POSITIVE
            polarity_strength = max(polarity_strength, 0.05)
        ranked_pairs = self._rank_entity_pairs(lower_text, entities, signal_start, signal_end)
        selected_pairs = ranked_pairs[:1] if ranked_pairs else []

        if not selected_pairs:
            selected_pairs = [(entities[0], entities[1], 0.35)]

        return [
            RawEdge(
                head_entity_id=head.entity_id,
                head_canonical_name=head.canonical_name,
                tail_entity_id=tail.entity_id,
                tail_canonical_name=tail.canonical_name,
                relation_type=relation_type,
                polarity_guess=polarity,
                student_conf=min(max(score + polarity_strength, 0.35), 0.75),
                fragment_id=fragment_id,
                fragment_text=text,
            )
            for head, tail, score in selected_pairs
        ]

    def _determine_polarity(self, text: str) -> Tuple[Polarity, float]:
        negative_score = sum(1 for pattern in NEGATIVE_POLARITY_PATTERNS if pattern in text)
        positive_score = sum(1 for pattern in POSITIVE_POLARITY_PATTERNS if pattern in text)

        if "하방압력" in text or "역풍" in text:
            negative_score += 2
        if "수혜" in text or "호재" in text:
            positive_score += 2

        if negative_score > positive_score:
            return Polarity.NEGATIVE, min(negative_score * 0.03, 0.1)
        if positive_score > negative_score:
            return Polarity.POSITIVE, min(positive_score * 0.03, 0.1)
        return Polarity.UNKNOWN, 0.0

    def _determine_relation_signal(self, text: str) -> Tuple[str, int, int]:
        for relation_type, patterns in RELATION_PATTERNS.items():
            for pattern in patterns:
                index = text.find(pattern)
                if index >= 0:
                    return relation_type, index, index + len(pattern)
        return "affects", -1, -1

    def _entity_span(self, text: str, entity: ResolvedEntity) -> Tuple[int, int]:
        candidates = [
            entity.surface_text,
            entity.canonical_name,
            (entity.canonical_id or "").replace("_", " "),
        ]
        for candidate in candidates:
            candidate = (candidate or "").strip().lower()
            if not candidate:
                continue
            index = text.find(candidate)
            if index >= 0:
                return index, index + len(candidate)
        return -1, -1

    def _rank_entity_pairs(
        self,
        text: str,
        entities: List[ResolvedEntity],
        signal_start: int,
        signal_end: int,
    ) -> List[Tuple[ResolvedEntity, ResolvedEntity, float]]:
        ranked: List[Tuple[ResolvedEntity, ResolvedEntity, float]] = []

        for idx, head in enumerate(entities[:-1]):
            head_start, head_end = self._entity_span(text, head)
            for tail in entities[idx + 1:]:
                tail_start, tail_end = self._entity_span(text, tail)
                if head_start < 0 or tail_start < 0 or head_start >= tail_start:
                    continue

                span_distance = tail_start - head_end
                score = 0.35

                if 0 <= span_distance <= 120:
                    score += 0.10
                if signal_start >= 0 and head_end <= signal_start <= tail_start:
                    score += 0.20
                if signal_end >= 0 and head_start <= signal_end <= tail_end + 80:
                    score += 0.10
                if signal_start >= 0 and tail_start - head_start <= 180:
                    score += 0.05

                ranked.append((head, tail, score))

        ranked.sort(key=lambda item: item[2], reverse=True)
        return ranked
