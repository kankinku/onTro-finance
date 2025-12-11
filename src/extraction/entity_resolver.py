"""
Entity Resolution Module
"Student1이 뽑은 엔티티를 실제 그래프의 canonical 엔티티로 정렬하는 단계"

매핑 우선순위 (절대적):
1. Domain Dictionary (alias → canonical) - 1순위, 가장 강력
2. Static Domain 매핑
3. Dynamic Domain 매핑
4. Personal Alias
5. Fuzzy match (embedding 유사도)
"""
import logging
from typing import List, Optional, Dict, Any, Tuple
from difflib import SequenceMatcher

from src.shared.models import EntityCandidate, ResolvedEntity, ResolutionMode
from src.shared.exceptions import EntityResolutionError
from config.settings import get_settings

logger = logging.getLogger(__name__)


class EntityResolver:
    """
    Entity Resolution Module
    
    엔티티 후보를 Canonical 엔티티로 매핑
    """
    
    def __init__(
        self,
        static_domain_kg: Optional[Dict[str, Any]] = None,
        dynamic_domain_kg: Optional[Dict[str, Any]] = None,
        personal_aliases: Optional[Dict[str, str]] = None,
    ):
        self.settings = get_settings()
        
        # 1순위: Domain Dictionary (alias table)
        self._alias_table = self._build_alias_table()
        
        # 2순위: Static Domain KG
        self._static_domain = static_domain_kg or {}
        
        # 3순위: Dynamic Domain KG
        self._dynamic_domain = dynamic_domain_kg or {}
        
        # 4순위: Personal Aliases
        self._personal_aliases = personal_aliases or {}
        
        # Resolution 통계
        self._stats = {
            "dictionary_match": 0,
            "static_domain": 0,
            "dynamic_domain": 0,
            "personal_alias": 0,
            "fuzzy_match": 0,
            "ambiguous": 0,
            "new_entity": 0,
        }
    
    def _build_alias_table(self) -> Dict[str, Dict[str, Any]]:
        """
        Alias Dictionary에서 lookup table 생성
        alias (lowercase) -> canonical info
        """
        alias_table = {}
        try:
            alias_data = self.settings.load_yaml_config("alias_dictionary")
            for entity_key, entity_info in alias_data.get("entities", {}).items():
                canonical_id = entity_key
                canonical_name = entity_info.get("canonical_name", entity_key)
                entity_type = entity_info.get("type", "Unknown")
                subtype = entity_info.get("subtype")
                
                for alias in entity_info.get("aliases", []):
                    alias_lower = alias.lower().strip()
                    alias_table[alias_lower] = {
                        "canonical_id": canonical_id,
                        "canonical_name": canonical_name,
                        "canonical_type": entity_type,
                        "canonical_subtype": subtype,
                    }
                
                # canonical name 자체도 등록
                alias_table[canonical_name.lower()] = {
                    "canonical_id": canonical_id,
                    "canonical_name": canonical_name,
                    "canonical_type": entity_type,
                    "canonical_subtype": subtype,
                }
                    
        except FileNotFoundError:
            logger.warning("Alias dictionary not found, resolution will be limited")
        
        logger.info(f"Built alias table with {len(alias_table)} entries")
        return alias_table
    
    def resolve(
        self,
        candidates: List[EntityCandidate],
    ) -> List[ResolvedEntity]:
        """
        엔티티 후보 리스트를 Canonical 엔티티로 매핑
        
        Args:
            candidates: EntityCandidate 리스트
        
        Returns:
            ResolvedEntity 리스트
        """
        resolved = []
        
        for candidate in candidates:
            try:
                resolved_entity = self._resolve_single(candidate)
                resolved.append(resolved_entity)
            except EntityResolutionError as e:
                logger.warning(f"Resolution failed for {candidate.surface_text}: {e}")
                # 실패해도 NEW_ENTITY로 처리하여 계속 진행
                resolved.append(ResolvedEntity(
                    entity_id=candidate.entity_id,
                    resolution_mode=ResolutionMode.NEW_ENTITY,
                    resolution_conf=0.0,
                    is_new_entity_candidate=True,
                    surface_text=candidate.surface_text,
                    fragment_id=candidate.fragment_id,
                ))
        
        logger.info(f"Resolved {len(resolved)} entities. Stats: {self._stats}")
        return resolved
    
    def _resolve_single(self, candidate: EntityCandidate) -> ResolvedEntity:
        """
        단일 엔티티 후보 Resolution
        
        우선순위:
        1. Dictionary Match
        2. Static Domain
        3. Dynamic Domain
        4. Personal Alias
        5. Fuzzy Match
        """
        surface_lower = candidate.surface_text.lower().strip()
        
        # Step 1: Dictionary Match (최우선)
        if surface_lower in self._alias_table:
            match = self._alias_table[surface_lower]
            self._stats["dictionary_match"] += 1
            return ResolvedEntity(
                entity_id=candidate.entity_id,
                canonical_id=match["canonical_id"],
                canonical_name=match["canonical_name"],
                canonical_type=match["canonical_type"],
                resolution_mode=ResolutionMode.DICTIONARY_MATCH,
                resolution_conf=0.95,
                surface_text=candidate.surface_text,
                fragment_id=candidate.fragment_id,
            )
        
        # Step 2: Static Domain KG
        static_match = self._match_in_domain(surface_lower, self._static_domain)
        if static_match:
            self._stats["static_domain"] += 1
            return ResolvedEntity(
                entity_id=candidate.entity_id,
                canonical_id=static_match["id"],
                canonical_name=static_match["name"],
                canonical_type=static_match.get("type"),
                resolution_mode=ResolutionMode.STATIC_DOMAIN,
                resolution_conf=0.9,
                surface_text=candidate.surface_text,
                fragment_id=candidate.fragment_id,
            )
        
        # Step 3: Dynamic Domain KG
        dynamic_match = self._match_in_domain(surface_lower, self._dynamic_domain)
        if dynamic_match:
            self._stats["dynamic_domain"] += 1
            return ResolvedEntity(
                entity_id=candidate.entity_id,
                canonical_id=dynamic_match["id"],
                canonical_name=dynamic_match["name"],
                canonical_type=dynamic_match.get("type"),
                resolution_mode=ResolutionMode.DYNAMIC_DOMAIN,
                resolution_conf=0.85,
                surface_text=candidate.surface_text,
                fragment_id=candidate.fragment_id,
            )
        
        # Step 4: Personal Alias
        if surface_lower in self._personal_aliases:
            canonical_name = self._personal_aliases[surface_lower]
            self._stats["personal_alias"] += 1
            return ResolvedEntity(
                entity_id=candidate.entity_id,
                canonical_id=f"PERSONAL_{canonical_name.replace(' ', '_')}",
                canonical_name=canonical_name,
                resolution_mode=ResolutionMode.PERSONAL_ALIAS,
                resolution_conf=0.8,
                surface_text=candidate.surface_text,
                fragment_id=candidate.fragment_id,
            )
        
        # Step 5: Fuzzy Match
        fuzzy_result = self._fuzzy_match(surface_lower)
        if fuzzy_result:
            if len(fuzzy_result) == 1:
                match, conf = fuzzy_result[0]
                self._stats["fuzzy_match"] += 1
                return ResolvedEntity(
                    entity_id=candidate.entity_id,
                    canonical_id=match["canonical_id"],
                    canonical_name=match["canonical_name"],
                    canonical_type=match.get("canonical_type"),
                    resolution_mode=ResolutionMode.FUZZY_MATCH,
                    resolution_conf=conf,
                    surface_text=candidate.surface_text,
                    fragment_id=candidate.fragment_id,
                )
            else:
                # 여러 후보 - Ambiguous
                self._stats["ambiguous"] += 1
                return ResolvedEntity(
                    entity_id=candidate.entity_id,
                    resolution_mode=ResolutionMode.AMBIGUOUS,
                    resolution_conf=0.5,
                    candidate_ids=[m["canonical_id"] for m, _ in fuzzy_result],
                    candidate_confs=[c for _, c in fuzzy_result],
                    surface_text=candidate.surface_text,
                    fragment_id=candidate.fragment_id,
                )
        
        # 매칭 실패 - New Entity 후보
        self._stats["new_entity"] += 1
        return ResolvedEntity(
            entity_id=candidate.entity_id,
            resolution_mode=ResolutionMode.NEW_ENTITY,
            resolution_conf=0.0,
            is_new_entity_candidate=True,
            surface_text=candidate.surface_text,
            fragment_id=candidate.fragment_id,
        )
    
    def _match_in_domain(
        self,
        surface: str,
        domain_kg: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Domain KG에서 매칭"""
        # 단순 구현: 이름 기반 lookup
        # 실제로는 Graph Store와 연동 필요
        for entity_id, entity_info in domain_kg.items():
            if isinstance(entity_info, dict):
                name = entity_info.get("name", "").lower()
                if surface == name:
                    return {"id": entity_id, "name": entity_info.get("name"), "type": entity_info.get("type")}
        return None
    
    def _fuzzy_match(
        self,
        surface: str,
    ) -> Optional[List[Tuple[Dict[str, Any], float]]]:
        """
        Fuzzy matching (유사도 기반)
        
        Returns:
            매칭 결과 리스트 [(match_info, confidence), ...] 또는 None
        """
        threshold = self.settings.extraction.fuzzy_match_threshold
        matches = []
        
        for alias, canonical_info in self._alias_table.items():
            similarity = SequenceMatcher(None, surface, alias).ratio()
            if similarity >= threshold:
                matches.append((canonical_info, similarity))
        
        if not matches:
            return None
        
        # 유사도 순 정렬
        matches.sort(key=lambda x: x[1], reverse=True)
        
        # 상위 결과만 반환
        top_conf = matches[0][1]
        # 최고 유사도와 0.05 이내인 것만 (동점 처리)
        close_matches = [(m, c) for m, c in matches if top_conf - c <= 0.05]
        
        return close_matches[:3]  # 최대 3개
    
    def add_personal_alias(self, alias: str, canonical_name: str):
        """개인 alias 추가"""
        self._personal_aliases[alias.lower().strip()] = canonical_name
        logger.info(f"Added personal alias: {alias} -> {canonical_name}")
    
    def get_stats(self) -> Dict[str, int]:
        """Resolution 통계 반환"""
        return self._stats.copy()
    
    def reset_stats(self):
        """통계 초기화"""
        for key in self._stats:
            self._stats[key] = 0
