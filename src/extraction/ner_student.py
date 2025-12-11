"""
Student1 (NER) Module
"fragment 안에서 엔티티 후보를 뽑는 모듈"

핵심 원칙:
- Recall > Precision: 놓치지 않는 것이 최우선
- False Positive는 나중에 걸러짐
- False Negative는 치명적 (관계 전체가 사라짐)
"""
import re
import logging
from typing import List, Optional, Dict, Any

from src.shared.models import EntityCandidate
from src.shared.error_framework import ExtractionError, ErrorSeverity
from src.llm.llm_client import LLMClient, LLMRequest
from src.bootstrap import get_llm_gateway
from config.settings import get_settings

logger = logging.getLogger(__name__)


class NERStudent:
    """
    Student1: Named Entity Recognition
    
    Fragment에서 엔티티 후보를 최대한 많이 추출
    """
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.settings = get_settings()
        # 주입받지 않으면 싱글톤 Gateway 사용
        self.llm_client = llm_client or get_llm_gateway()
        self._entity_types = self._load_entity_types()
        self._alias_hints = self._load_alias_hints()
    
    def _load_entity_types(self) -> Dict[str, Any]:
        """Entity Types 설정 로드"""
        try:
            return self.settings.load_yaml_config("entity_types")
        except FileNotFoundError:
            logger.warning("Entity types config not found, using defaults")
            return {"entity_types": {}}
    
    def _load_alias_hints(self) -> Dict[str, str]:
        """
        Alias dictionary에서 surface -> type 힌트 생성
        NER 정확도 향상용
        """
        hints = {}
        try:
            alias_config = self.settings.load_yaml_config("alias_dictionary")
            for entry in alias_config.get("aliases", []):
                entity_type = entry.get("type", "Unknown")
                for alias in entry.get("synonyms", []):
                    hints[alias.lower()] = entity_type
        except FileNotFoundError:
            logger.warning("Alias dictionary not found")
        return hints
    
    def extract(self, fragment_text: str, fragment_id: str, use_llm: bool = True) -> List[EntityCandidate]:
        """
        엔티티 추출 메인 메서드
        
        Args:
            fragment_text: Fragment 텍스트
            fragment_id: Fragment ID
            use_llm: LLM 사용 여부
            
        Returns:
            EntityCandidate 리스트
        """
        if not fragment_text.strip():
            return []
            
        # 1. LLM 사용 가능 시 시도
        if use_llm and self.llm_client and self.llm_client.health_check():
            try:
                candidates = self._extract_with_llm(fragment_text, fragment_id)
                if candidates:
                    return candidates
            except Exception as e:
                logger.warning(f"LLM extraction failed, falling back to rules: {e}")
        
        # 2. 실패하거나 LLM 없으면 Rule-based
        return self._extract_rule_based(fragment_text, fragment_id)
    
    def _extract_with_llm(
        self,
        fragment_text: str,
        fragment_id: str
    ) -> List[EntityCandidate]:
        """LLM을 이용한 NER"""
        type_list = ", ".join(self._entity_types.get("entity_types", {}).keys())
        
        system_prompt = (
            "You are an expert Named Entity Recognition system for financial domain. "
            f"Extract entities of types: {type_list}. "
            "Output strictly in JSON format: "
            "{'entities': [{'surface_text': '...', 'type': '...', 'normalized_name': '...', 'confidence': 0.0-1.0}]}"
        )
        
        prompt = f"Text: {fragment_text}"
        
        try:
            request = LLMRequest(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.1,
                json_mode=True,
            )
            
            result = self.llm_client.generate_json(request)
            
            entities = []
            for ent_data in result.get("entities", []):
                surface_text = ent_data.get("surface_text", "")
                if not surface_text:
                    continue
                
                # span 찾기 (단순 검색)
                span_start = fragment_text.find(surface_text)
                span_end = span_start + len(surface_text) if span_start != -1 else 0
                
                if span_start == -1:
                    continue
                
                entities.append(EntityCandidate(
                    surface_text=surface_text,
                    type_guess=ent_data.get("type", "Unknown"),
                    normalized_name_guess=ent_data.get("normalized_name"),
                    span_start=span_start,
                    span_end=span_end,
                    student_conf=float(ent_data.get("confidence", 0.5)),
                    fragment_id=fragment_id,
                ))
            
            return entities
            
        except Exception as e:
            # 상위로 전파하여 fallback 유도
            raise ExtractionError(
                message=f"LLM extraction failed: {str(e)}",
                extractor="NERStudent",
                text_preview=fragment_text,
                severity=ErrorSeverity.MEDIUM
            )

    def _extract_rule_based(
        self,
        fragment_text: str,
        fragment_id: str,
    ) -> List[EntityCandidate]:
        """규칙 기반 NER (fallback)"""
        entities = []
        text_lower = fragment_text.lower()
        
        # 1. Alias dictionary에서 매칭
        for alias, entity_type in self._alias_hints.items():
            if alias in text_lower:
                pattern = re.compile(re.escape(alias), re.IGNORECASE)
                for match in pattern.finditer(fragment_text):
                    entities.append(EntityCandidate(
                        surface_text=match.group(),
                        type_guess=entity_type,
                        normalized_name_guess=None,
                        span_start=match.start(),
                        span_end=match.end(),
                        student_conf=0.8,
                        fragment_id=fragment_id,
                    ))
        
        # 2. 패턴 기반 추출
        entities.extend(self._extract_by_patterns(fragment_text, fragment_id))
        
        return entities
    
    def _extract_by_patterns(
        self,
        fragment_text: str,
        fragment_id: str,
    ) -> List[EntityCandidate]:
        """패턴 기반 추출"""
        entities = []
        
        # Percent
        for match in re.finditer(r'\d+\.?\d*%p?', fragment_text):
            entities.append(EntityCandidate(
                surface_text=match.group(),
                type_guess="Quantity",
                span_start=match.start(),
                span_end=match.end(),
                student_conf=0.9,
                fragment_id=fragment_id,
            ))
            
        # Ticker (간단화)
        for match in re.finditer(r'(?<![A-Za-z])[A-Z]{2,5}(?![A-Za-z])', fragment_text):
            entities.append(EntityCandidate(
                surface_text=match.group(),
                type_guess="Instrument",
                span_start=match.start(),
                span_end=match.end(),
                student_conf=0.6,
                fragment_id=fragment_id,
            ))
            
        return entities
