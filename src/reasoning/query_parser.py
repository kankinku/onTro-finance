"""
Query Parsing & Entity Localization Module
"사용자의 질문에서 핵심 엔티티를 추출하고 온톨로지의 어디서부터 추론을 시작할지 결정"
"""
import re
import logging
from typing import Optional, List, Dict, Tuple

from src.reasoning.models import ParsedQuery, QueryType
from src.extraction.ner_student import NERStudent
from src.extraction.entity_resolver import EntityResolver
from src.llm.ollama_client import OllamaClient

logger = logging.getLogger(__name__)


class QueryParser:
    """
    Query Parsing & Entity Localization
    질문 분석 및 엔티티 추출
    """
    
    def __init__(
        self,
        ner_student: Optional[NERStudent] = None,
        entity_resolver: Optional[EntityResolver] = None,
        llm_client: Optional[OllamaClient] = None,
    ):
        self.ner = ner_student or NERStudent()
        self.resolver = entity_resolver or EntityResolver()
        self.llm_client = llm_client
        
        # Query type 패턴 (순서 중요: 더 구체적인 것 먼저)
        self._query_patterns = {
            QueryType.CONDITIONED: [
                r"오르면",
                r"상승하면",
                r"하락하면",
                r"증가하면",
                r"감소하면",
                r"(.+)(이|가)?\s*(오르|상승|증가|하락|감소).*(때|면|경우)",
                r"(.+)(일|할)\s*때\s*(.+)(은|는)",
            ],
            QueryType.CAUSAL: [
                r"^왜",
                r"왜\s*(.+)(이|가)?\s*(오|내|상승|하락)",
                r"(.+)의?\s*원인",
                r"어째서",
            ],
            QueryType.PREDICTIVE: [
                r"앞으로",
                r"어떻게\s*될",
                r"(.+)(이|가)?\s*어떻게\s*될",
                r"전망",
                r"예상",
            ],
            QueryType.DIRECT_RELATION: [
                r"(.+)가?\s*(.+)에?\s*(어떤|무슨)\s*(영향|관계)",
                r"(.+)와?\s*(.+)의?\s*관계",
                r"영향",
            ],
        }
    
    def parse(self, query: str) -> ParsedQuery:
        """
        질문 파싱
        
        Args:
            query: 사용자 질문
        
        Returns:
            ParsedQuery
        """
        # Step 1: Query fragmentation
        fragments = self._fragment_query(query)
        
        # Step 2: NER & Entity Resolution
        entities, entity_names = self._extract_entities(query)
        
        # Step 3: Query type classification
        query_type = self._classify_query_type(query)
        
        # Step 4: Head/Tail 결정
        head_entity, tail_entity, conditions = self._identify_structure(
            query, entities, query_type
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
            f"Query parsed: type={query_type.value}, "
            f"entities={len(entities)}, head={head_entity}, tail={tail_entity}"
        )
        
        return parsed
    
    def _fragment_query(self, query: str) -> List[str]:
        """질문 프래그먼트 분리"""
        # 조건절과 메인절 분리
        fragments = []
        
        # '때', '면', '경우' 등으로 분리
        parts = re.split(r'(때|면|경우|하면)', query)
        
        current = ""
        for part in parts:
            current += part
            if part in ['때', '면', '경우', '하면']:
                fragments.append(current.strip())
                current = ""
        
        if current.strip():
            fragments.append(current.strip())
        
        return fragments if fragments else [query]
    
    def _extract_entities(self, query: str) -> Tuple[List[str], Dict[str, str]]:
        """엔티티 추출 및 해결"""
        try:
            # NER 수행
            candidates = self.ner.extract(
                fragment_text=query,
                fragment_id="QUERY",
                use_llm=False,  # 빠른 처리를 위해 규칙 기반
            )
            
            # Entity Resolution
            entities = []
            entity_names = {}
            
            for candidate in candidates:
                resolved = self.resolver.resolve(candidate)
                
                if resolved and resolved.canonical_id:
                    if resolved.canonical_id not in entities:
                        entities.append(resolved.canonical_id)
                        entity_names[resolved.canonical_id] = resolved.canonical_name or candidate.surface_text
                elif candidate.surface_text:
                    # 해결 안 되면 surface text 사용
                    entity_id = f"UNK_{candidate.surface_text}"
                    if entity_id not in entities:
                        entities.append(entity_id)
                        entity_names[entity_id] = candidate.surface_text
            
            return entities, entity_names
            
        except Exception as e:
            logger.warning(f"Entity extraction failed: {e}")
            return [], {}
    
    def _classify_query_type(self, query: str) -> QueryType:
        """질문 유형 분류"""
        query_lower = query.lower()
        
        for q_type, patterns in self._query_patterns.items():
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    return q_type
        
        return QueryType.UNKNOWN
    
    def _identify_structure(
        self,
        query: str,
        entities: List[str],
        query_type: QueryType,
    ) -> Tuple[Optional[str], Optional[str], List[str]]:
        """Head/Tail/Condition 구조 식별"""
        if len(entities) == 0:
            return None, None, []
        
        if len(entities) == 1:
            # 단일 엔티티: 그것에 대한 질문
            return entities[0], None, []
        
        if len(entities) == 2:
            # 두 엔티티: 첫 번째가 head, 두 번째가 tail
            return entities[0], entities[1], []
        
        # 3개 이상: 첫 번째 head, 마지막 tail, 나머지 조건
        return entities[0], entities[-1], entities[1:-1]
