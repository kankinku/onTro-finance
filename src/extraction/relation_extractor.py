"""
Student2 (Relation Extraction) Module
"canonical 엔티티 쌍에서 원석 엣지를 생성하는 단계"
"""
import logging
from typing import List, Optional, Dict, Any, Tuple

from src.shared.models import ResolvedEntity, RawEdge, Polarity, ResolutionMode
from src.shared.exceptions import RelationExtractionError
from src.llm.ollama_client import OllamaClient
from config.settings import get_settings

logger = logging.getLogger(__name__)

POLARITY_PATTERNS = {
    "positive": ["상승", "증가", "강세", "호조", "개선", "확대"],
    "negative": ["하락", "감소", "약세", "부진", "악화", "축소"],
    "inverse": ["반대로", "역으로", "반비례", "역상관"],
}


class RelationExtractor:
    """Student2: Relation Extraction"""
    
    def __init__(self, llm_client: Optional[OllamaClient] = None):
        self.settings = get_settings()
        self.llm_client = llm_client
        self._relation_types = self._load_relation_types()
    
    def _load_relation_types(self) -> Dict[str, Any]:
        try:
            return self.settings.load_yaml_config("relation_types")
        except FileNotFoundError:
            return {"relation_types": {"Affect": {}, "Cause": {}, "DependOn": {}}}
    
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
            e for e in resolved_entities
            if e.resolution_mode != ResolutionMode.NEW_ENTITY and e.canonical_id
        ]
        
        if len(valid_entities) < 2:
            return []
        
        try:
            if use_llm and self.llm_client:
                return self._extract_with_llm(fragment_text, fragment_id, valid_entities)
            return self._extract_rule_based(fragment_text, fragment_id, valid_entities)
        except Exception as e:
            raise RelationExtractionError(message=str(e), fragment_id=fragment_id)
    
    def _extract_with_llm(self, text: str, frag_id: str, entities: List[ResolvedEntity]) -> List[RawEdge]:
        rel_types = list(self._relation_types.get("relation_types", {}).keys())
        entity_info = [{"id": e.entity_id, "name": e.canonical_name, "surface": e.surface_text} for e in entities]
        
        system_prompt = f"""교통/날씨/세종시 도메인 텍스트에서 엔티티 간 관계 추출. 관계 타입: {rel_types}.
JSON: {{"relations": [{{"head_id": "id", "tail_id": "id", "type": "type", "polarity": "+/-/neutral", "confidence": 0.8}}]}}"""
        
        prompt = f'텍스트: "{text}"\n엔티티: {entity_info}'
        
        try:
            result = self.llm_client.generate_json(prompt=prompt, system_prompt=system_prompt)
            edges = []
            entity_map = {e.entity_id: e for e in entities}
            
            for rel in result.get("relations", []):
                head_id, tail_id = rel.get("head_id"), rel.get("tail_id")
                if head_id not in entity_map or tail_id not in entity_map:
                    continue
                
                head, tail = entity_map[head_id], entity_map[tail_id]
                pol = Polarity(rel.get("polarity", "neutral")) if rel.get("polarity") in ["+", "-", "neutral"] else Polarity.UNKNOWN
                
                edges.append(RawEdge(
                    head_entity_id=head_id, head_canonical_name=head.canonical_name,
                    tail_entity_id=tail_id, tail_canonical_name=tail.canonical_name,
                    relation_type=rel.get("type", "Affect"), polarity_guess=pol,
                    student_conf=float(rel.get("confidence", 0.5)),
                    fragment_id=frag_id, fragment_text=text,
                ))
            return edges
        except Exception as e:
            logger.warning(f"LLM failed: {e}")
            return self._extract_rule_based(text, frag_id, entities)
    
    def _extract_rule_based(self, text: str, frag_id: str, entities: List[ResolvedEntity]) -> List[RawEdge]:
        if len(entities) < 2:
            return []
        
        head, tail = entities[0], entities[-1]
        polarity = self._determine_polarity(text)
        rel_type = self._determine_relation_type(text)
        
        return [RawEdge(
            head_entity_id=head.entity_id, head_canonical_name=head.canonical_name,
            tail_entity_id=tail.entity_id, tail_canonical_name=tail.canonical_name,
            relation_type=rel_type, polarity_guess=polarity, student_conf=0.5,
            fragment_id=frag_id, fragment_text=text,
        )]
    
    def _determine_polarity(self, text: str) -> Polarity:
        t = text.lower()
        if any(p in t for p in POLARITY_PATTERNS["inverse"]):
            return Polarity.NEGATIVE
        if any(p in t for p in POLARITY_PATTERNS["positive"]):
            return Polarity.POSITIVE
        if any(p in t for p in POLARITY_PATTERNS["negative"]):
            return Polarity.NEGATIVE
        return Polarity.UNKNOWN
    
    def _determine_relation_type(self, text: str) -> str:
        t = text.lower()
        if any(p in t for p in ["때문에", "으로 인해", "영향으로"]):
            return "Cause"
        if any(p in t for p in ["의존", "민감"]):
            return "DependOn"
        return "Affect"
