"""
Query parsing and entity localization for finance-oriented queries.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from src.reasoning.models import ParsedQuery, QueryType
from src.extraction.ner_student import NERStudent
from src.extraction.entity_resolver import EntityResolver

logger = logging.getLogger(__name__)


class QueryParser:
    """Extract query entities and determine a finance-friendly head/tail structure."""

    def __init__(
        self,
        ner_student: Optional[NERStudent] = None,
        entity_resolver: Optional[EntityResolver] = None,
        llm_client: Optional[Any] = None,
    ):
        self.ner = ner_student or NERStudent()
        self.resolver = entity_resolver or EntityResolver()
        self.llm_client = llm_client
        self._query_patterns = {
            QueryType.CONDITIONED: [
                "if",
                "when",
                "under",
                "경우",
                "하면",
                "오르면",
                "내리면",
                "상승하면",
                "하락하면",
            ],
            QueryType.CAUSAL: ["why", "원인", "cause", "drive", "왜", "이유"],
            QueryType.PREDICTIVE: [
                "what happens",
                "how will",
                "전망",
                "예측",
                "어떻게 될까",
                "어떻게 되나",
            ],
            QueryType.DIRECT_RELATION: ["impact", "relation", "affect", "영향", "관계", "민감"],
            QueryType.COMPARISON: ["vs", "compare", "비교"],
        }
        self._split_pattern = re.compile(
            r"\bif\b|\bwhen\b|경우|하면|오르면|내리면|상승하면|하락하면", re.IGNORECASE
        )

    def parse(self, query: str) -> ParsedQuery:
        fragments = self._fragment_query(query)
        entities, entity_names = self._extract_entities(query)
        query_type = self._classify_query_type(query)
        head_entity, tail_entity, conditions = self._identify_structure(
            query, entities, entity_names, query_type
        )

        parsed = ParsedQuery(
            original_query=query,
            query_entities=entities,
            entity_names=entity_names,
            query_type=query_type,
            head_entity=head_entity,
            tail_entity=tail_entity,
            condition_entities=conditions,
            fragments=fragments,
        )

        logger.info(
            "Query parsed: type=%s, entities=%s, head=%s, tail=%s",
            query_type.value,
            len(entities),
            head_entity,
            tail_entity,
        )
        return parsed

    def _fragment_query(self, query: str) -> List[str]:
        parts = [part.strip() for part in self._split_pattern.split(query) if part.strip()]
        return parts or [query]

    def _extract_entities(self, query: str) -> Tuple[List[str], Dict[str, str]]:
        try:
            candidates = self.ner.extract(
                fragment_text=query,
                fragment_id="QUERY",
                use_llm=bool(self.llm_client),
            )
            resolved_entities = self.resolver.resolve(candidates)
            entities: List[str] = []
            entity_names: Dict[str, str] = {}

            for resolved in resolved_entities:
                if resolved.canonical_id:
                    if resolved.canonical_id not in entities:
                        entities.append(resolved.canonical_id)
                        entity_names[resolved.canonical_id] = (
                            resolved.canonical_name or resolved.surface_text
                        )
                elif resolved.surface_text:
                    unknown_id = f"UNK_{resolved.surface_text}"
                    if unknown_id not in entities:
                        entities.append(unknown_id)
                        entity_names[unknown_id] = resolved.surface_text

            if not entities:
                return self._keyword_fallback(query)
            return entities, entity_names
        except Exception as exc:
            logger.warning(f"Entity extraction failed: {exc}")
            return self._keyword_fallback(query)

    def _classify_query_type(self, query: str) -> QueryType:
        lowered = query.lower()
        for query_type, patterns in self._query_patterns.items():
            if any(pattern in lowered for pattern in patterns):
                return query_type
        return QueryType.UNKNOWN

    def _identify_structure(
        self,
        query: str,
        entities: List[str],
        entity_names: Dict[str, str],
        query_type: QueryType,
    ) -> Tuple[Optional[str], Optional[str], List[str]]:
        if not entities:
            return None, None, []
        if len(entities) == 1:
            return entities[0], None, []

        positions = {
            entity: self._locate_entity(query, entity_names.get(entity, entity))
            for entity in entities
        }
        ordered = sorted(
            entities, key=lambda entity: positions[entity] if positions[entity] >= 0 else 10**9
        )

        head = ordered[0]
        tail = ordered[1]

        subject_entity = self._find_entity_with_particle(query, ordered, entity_names, {"이", "가"})
        object_entity = self._find_entity_with_particle(
            query, ordered, entity_names, {"을", "를", "에"}
        )
        topical_entity = self._find_entity_with_particle(query, ordered, entity_names, {"은", "는"})
        cause_entity = self._find_entity_with_cause_hint(query, ordered, entity_names)

        if subject_entity:
            head = subject_entity
        if object_entity and object_entity != head:
            tail = object_entity

        if (
            query_type in {QueryType.CONDITIONED, QueryType.DIRECT_RELATION}
            and "민감" in query.lower()
        ):
            if cause_entity and topical_entity and cause_entity != topical_entity:
                head = cause_entity
                tail = topical_entity
        elif cause_entity and cause_entity != tail and subject_entity is None:
            head = cause_entity

        if head == tail:
            for entity in ordered:
                if entity != head:
                    tail = entity
                    break

        conditions = [entity for entity in ordered if entity not in {head, tail}]
        return head, tail, conditions

    def _locate_entity(self, query: str, surface: str) -> int:
        surface = surface.lower().strip()
        if not surface:
            return -1

        candidates = [surface, surface.replace("_", " ")]
        for candidate in candidates:
            index = query.lower().find(candidate)
            if index >= 0:
                return index
        return -1

    def _find_entity_with_particle(
        self,
        query: str,
        entities: List[str],
        entity_names: Dict[str, str],
        particles: set[str],
    ) -> Optional[str]:
        lowered = query.lower()
        for entity in entities:
            surface = entity_names.get(entity, entity).lower().strip()
            index = lowered.find(surface)
            if index < 0:
                continue
            suffix = lowered[index + len(surface) :].lstrip()
            if suffix and any(suffix.startswith(particle) for particle in particles):
                return entity
        return None

    def _find_entity_with_cause_hint(
        self,
        query: str,
        entities: List[str],
        entity_names: Dict[str, str],
    ) -> Optional[str]:
        lowered = query.lower()
        hints = ["상승", "하락", "인상", "인하", "변화", "충격"]
        for entity in entities:
            surface = entity_names.get(entity, entity).lower().strip()
            if any(f"{surface} {hint}" in lowered for hint in hints):
                return entity
        return None

    def _keyword_fallback(self, query: str) -> Tuple[List[str], Dict[str, str]]:
        entities: List[str] = []
        entity_names: Dict[str, str] = {}
        lowered = query.lower()

        for alias, info in getattr(self.resolver, "_alias_table", {}).items():
            if alias in lowered:
                canonical_id = info["canonical_id"]
                if canonical_id not in entities:
                    entities.append(canonical_id)
                    entity_names[canonical_id] = info["canonical_name"]

        return entities, entity_names
