"""
Schema Validator
"엣지가 최소한 구조적으로 말이 되는가를 확인하는 1차 필터"

검증 조건:
1. 필수 필드 존재 여부
2. relation_type이 Schema에 존재하는가
3. 엔티티 타입 조합이 허용되는가
4. self-loop 금지
"""
import logging
from typing import List, Dict, Any, Optional, Set, Tuple

from src.shared.models import RawEdge, ResolvedEntity
from src.validation.models import SchemaValidationResult
from config.settings import get_settings

logger = logging.getLogger(__name__)


class SchemaValidator:
    """
    Schema Validator
    구조적·형식적 타당성 검사
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._validation_schema = self._load_validation_schema()
        self._relation_types = self._load_relation_types()
        self._allowed_combinations = self._build_allowed_set()
        self._forbidden_combinations = self._build_forbidden_set()
    
    def _load_validation_schema(self) -> Dict[str, Any]:
        """Validation Schema 로드"""
        try:
            return self.settings.load_yaml_config("validation_schema")
        except FileNotFoundError:
            logger.warning("Validation schema not found, using permissive mode")
            return {"validation_rules": {}}
    
    def _load_relation_types(self) -> Set[str]:
        """허용된 Relation Types 로드"""
        try:
            data = self.settings.load_yaml_config("relation_types")
            return set(data.get("relation_types", {}).keys())
        except FileNotFoundError:
            return {"Affect", "Cause", "DependOn", "TemporalBefore", "TemporalAfter", "CorrelateWith", "PartOf"}
    
    def _build_allowed_set(self) -> Set[Tuple[str, str, str]]:
        """허용 조합 세트 생성: (head_type, tail_type, relation)"""
        allowed = set()
        rules = self._validation_schema.get("validation_rules", {})
        
        for combo in rules.get("allowed_combinations", []):
            head_type = combo.get("head_type")
            tail_type = combo.get("tail_type")
            for rel in combo.get("relations", []):
                allowed.add((head_type, tail_type, rel))
        
        return allowed
    
    def _build_forbidden_set(self) -> Dict[Tuple[str, str, str], str]:
        """금지 조합 세트 생성: (head_type, tail_type, relation) -> reason"""
        forbidden = {}
        rules = self._validation_schema.get("validation_rules", {})
        
        for combo in rules.get("forbidden_combinations", []):
            head_type = combo.get("head_type")
            tail_type = combo.get("tail_type")
            reason = combo.get("reason", "Forbidden combination")
            for rel in combo.get("relations", []):
                forbidden[(head_type, tail_type, rel)] = reason
        
        return forbidden
    
    def validate(
        self,
        edge: RawEdge,
        resolved_entities: List[ResolvedEntity],
    ) -> SchemaValidationResult:
        """
        Schema 검증 수행
        
        Args:
            edge: 검증할 Raw Edge
            resolved_entities: Resolved Entity 리스트
        
        Returns:
            SchemaValidationResult
        """
        errors = []
        
        # 엔티티 맵 생성
        entity_map = {e.entity_id: e for e in resolved_entities}
        
        # 조건 1: 필수 필드 존재 확인
        has_required = self._check_required_fields(edge)
        if not has_required:
            errors.append("missing_required_fields")
        
        # 조건 2: relation_type 유효성
        relation_valid = edge.relation_type in self._relation_types
        if not relation_valid:
            errors.append(f"invalid_relation_type:{edge.relation_type}")
        
        # 조건 3: 엔티티 타입 조합 확인
        entity_pair_valid = True
        head_entity = entity_map.get(edge.head_entity_id)
        tail_entity = entity_map.get(edge.tail_entity_id)
        
        if head_entity and tail_entity:
            head_type = head_entity.canonical_type
            tail_type = tail_entity.canonical_type
            
            if head_type and tail_type:
                combo = (head_type, tail_type, edge.relation_type)
                
                # 금지 조합 체크
                if combo in self._forbidden_combinations:
                    entity_pair_valid = False
                    reason = self._forbidden_combinations[combo]
                    errors.append(f"forbidden_entity_pair:{reason}")
                
                # 허용 조합 체크 (허용 리스트가 있는 경우에만)
                elif self._allowed_combinations and combo not in self._allowed_combinations:
                    # 허용 리스트에 없으면 경고 (엄격 모드에서는 에러)
                    logger.warning(f"Entity pair not in allowed list: {combo}")
                    # 여기서는 permissive하게 통과시킴
        else:
            # 엔티티를 찾을 수 없음
            if not head_entity:
                errors.append(f"head_entity_not_found:{edge.head_entity_id}")
            if not tail_entity:
                errors.append(f"tail_entity_not_found:{edge.tail_entity_id}")
            entity_pair_valid = False
        
        # 조건 4: self-loop 금지
        no_self_loop = edge.head_entity_id != edge.tail_entity_id
        if not no_self_loop:
            errors.append("self_loop_detected")
        
        # 최종 결과
        schema_valid = has_required and relation_valid and entity_pair_valid and no_self_loop
        
        result = SchemaValidationResult(
            edge_id=edge.raw_edge_id,
            schema_valid=schema_valid,
            schema_errors=errors,
            has_required_fields=has_required,
            relation_type_valid=relation_valid,
            entity_pair_valid=entity_pair_valid,
            no_self_loop=no_self_loop,
        )
        
        if not schema_valid:
            logger.info(f"Schema validation failed for {edge.raw_edge_id}: {errors}")
        
        return result
    
    def _check_required_fields(self, edge: RawEdge) -> bool:
        """필수 필드 존재 확인"""
        required_fields = [
            edge.head_entity_id,
            edge.tail_entity_id,
            edge.relation_type,
            edge.fragment_id,
        ]
        return all(f is not None and f != "" for f in required_fields)
