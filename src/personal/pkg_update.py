"""
Personal Knowledge Graph Update Module.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.personal.models import (
    PCSResult,
    PersonalCandidate,
    PersonalLabel,
    PersonalRelation,
)

logger = logging.getLogger(__name__)


class PersonalKGUpdate:
    """
    Manage personal graph relations and persist them to a dedicated store.
    """

    def __init__(self, storage_path: Optional[str | Path] = None):
        self._storage_path = Path(storage_path) if storage_path else None
        self._relations: Dict[str, PersonalRelation] = {}
        self._relation_index: Dict[tuple[str, str, str], str] = {}
        self._user_index: Dict[str, List[str]] = {}
        self._load()

    def update(
        self,
        candidate: PersonalCandidate,
        pcs_result: PCSResult,
    ) -> tuple[str, bool]:
        key = (
            candidate.head_canonical_id,
            candidate.tail_canonical_id,
            candidate.relation_type,
        )
        existing_id = self._relation_index.get(key)

        if existing_id is None:
            return self._create_new_relation(candidate, pcs_result), True
        return self._update_existing_relation(existing_id, candidate, pcs_result), False

    def _create_new_relation(
        self,
        candidate: PersonalCandidate,
        pcs_result: PCSResult,
    ) -> str:
        relation = PersonalRelation(
            head_id=candidate.head_canonical_id,
            head_name=candidate.head_canonical_name,
            tail_id=candidate.tail_canonical_id,
            tail_name=candidate.tail_canonical_name,
            relation_type=candidate.relation_type,
            sign=candidate.polarity,
            user_id=candidate.user_id,
            pcs_score=pcs_result.pcs_score,
            personal_weight=self._calculate_weight(pcs_result),
            personal_label=pcs_result.personal_label,
            source_type=candidate.source_type,
            relevance_types=[candidate.relevance_type.value] if candidate.relevance_type else [],
            history=[
                {
                    "timestamp": datetime.now().isoformat(),
                    "action": "created",
                    "pcs_score": pcs_result.pcs_score,
                    "fragment": candidate.fragment_text[:100] if candidate.fragment_text else None,
                }
            ],
        )

        self._relations[relation.relation_id] = relation
        self._rebuild_indexes()
        self._persist()
        logger.info("Created new PKG relation: %s", relation.relation_id)
        return relation.relation_id

    def _update_existing_relation(
        self,
        relation_id: str,
        candidate: PersonalCandidate,
        pcs_result: PCSResult,
    ) -> str:
        relation = self._relations.get(relation_id)
        if relation is None:
            return self._create_new_relation(candidate, pcs_result)

        relation.occurrence_count += 1
        relation.last_occurred_at = datetime.now()

        old_weight = relation.personal_weight
        new_weight = self._calculate_weight(pcs_result)
        relation.personal_weight = (old_weight * 0.7) + (new_weight * 0.3)
        relation.pcs_score = (relation.pcs_score * 0.7) + (pcs_result.pcs_score * 0.3)

        if pcs_result.pcs_score >= 0.7:
            relation.personal_label = PersonalLabel.STRONG_BELIEF
        elif pcs_result.pcs_score >= 0.4:
            relation.personal_label = PersonalLabel.WEAK_BELIEF
        else:
            relation.personal_label = PersonalLabel.NOISY_HYPOTHESIS

        if candidate.relevance_type and candidate.relevance_type.value not in relation.relevance_types:
            relation.relevance_types.append(candidate.relevance_type.value)

        relation.history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "action": "updated",
                "pcs_score": pcs_result.pcs_score,
                "occurrence": relation.occurrence_count,
                "fragment": candidate.fragment_text[:100] if candidate.fragment_text else None,
            }
        )

        self._persist()
        logger.info(
            "Updated PKG relation: %s, occurrences=%s",
            relation_id,
            relation.occurrence_count,
        )
        return relation_id

    def _calculate_weight(self, pcs_result: PCSResult) -> float:
        if pcs_result.personal_label == PersonalLabel.STRONG_BELIEF:
            return pcs_result.pcs_score
        if pcs_result.personal_label == PersonalLabel.WEAK_BELIEF:
            return pcs_result.pcs_score * 0.5
        return pcs_result.pcs_score * 0.1

    def get_relation(self, relation_id: str) -> Optional[PersonalRelation]:
        return self._relations.get(relation_id)

    def get_relation_by_key(
        self,
        head_id: str,
        tail_id: str,
        relation_type: str,
    ) -> Optional[PersonalRelation]:
        key = (head_id, tail_id, relation_type)
        relation_id = self._relation_index.get(key)
        return self._relations.get(relation_id) if relation_id else None

    def get_all_relations(self) -> Dict[str, PersonalRelation]:
        return self._relations.copy()

    def get_user_relations(self, user_id: str) -> List[PersonalRelation]:
        relation_ids = self._user_index.get(user_id, [])
        return [self._relations[relation_id] for relation_id in relation_ids if relation_id in self._relations]

    def get_strong_beliefs(self) -> List[PersonalRelation]:
        return [
            relation
            for relation in self._relations.values()
            if relation.personal_label == PersonalLabel.STRONG_BELIEF
        ]

    def get_stats(self) -> Dict:
        labels = {"strong": 0, "weak": 0, "noisy": 0}
        for relation in self._relations.values():
            if relation.personal_label == PersonalLabel.STRONG_BELIEF:
                labels["strong"] += 1
            elif relation.personal_label == PersonalLabel.WEAK_BELIEF:
                labels["weak"] += 1
            else:
                labels["noisy"] += 1

        return {
            "total_relations": len(self._relations),
            "labels": labels,
            "users": len(self._user_index),
        }

    def flush(self) -> None:
        self._persist()

    def clear(self) -> None:
        self._relations.clear()
        self._rebuild_indexes()
        self._persist()

    def _load(self) -> None:
        if self._storage_path is None or not self._storage_path.exists():
            return

        try:
            payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load personal KG store from %s", self._storage_path, exc_info=exc)
            return

        records = payload.get("relations", []) if isinstance(payload, dict) else []
        self._relations = {}
        for record in records:
            relation = PersonalRelation.model_validate(record)
            self._relations[relation.relation_id] = relation

        self._rebuild_indexes()

    def _persist(self) -> None:
        if self._storage_path is None:
            return

        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "relations": [
                relation.model_dump(mode="json")
                for relation in self._relations.values()
            ]
        }
        self._storage_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _rebuild_indexes(self) -> None:
        self._relation_index.clear()
        self._user_index.clear()

        for relation in self._relations.values():
            key = (relation.head_id, relation.tail_id, relation.relation_type)
            self._relation_index[key] = relation.relation_id
            self._user_index.setdefault(relation.user_id, []).append(relation.relation_id)
