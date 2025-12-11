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
        logger.info(f"DEBUG_QUERY: {query}")
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
        """엔티티 추출 및 해석"""
        try:
            candidates = self.ner.extract(
                fragment_text=query,
                fragment_id="QUERY",
                use_llm=bool(self.llm_client),
            )
            entities: List[str] = []
            entity_names: Dict[str, str] = {}
            for candidate in candidates:
                if not hasattr(candidate, "surface_text"):
                    continue
                resolved = self.resolver.resolve(candidate)
                if resolved and resolved.canonical_id:
                    if resolved.canonical_id not in entities:
                        entities.append(resolved.canonical_id)
                        entity_names[resolved.canonical_id] = resolved.canonical_name or candidate.surface_text
                elif getattr(candidate, "surface_text", None):
                    entity_id = f"UNK_{candidate.surface_text}"
                    if entity_id not in entities:
                        entities.append(entity_id)
                        entity_names[entity_id] = candidate.surface_text
            if not entities:
                return self._keyword_fallback(query)
            return entities, entity_names
        except Exception as e:
            logger.warning(f"Entity extraction failed: {e}")
            return self._keyword_fallback(query)

    def _classify_query_type(self, query: str) -> QueryType:
        """질문 타입 분류"""
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
        """Head/Tail/Condition ??"""
        if len(entities) == 0:
            return None, None, []

        # ????? head ??
        head_order = [
            "Heavy_Rain", "Heavy_Snow", "Road_Construction", "BRT", "Rush_Hour",
        ]
        tail_order = [
            "Traffic_Congestion", "Travel_Time", "Bus_Headway", "Traffic_Speed",
        ]

        head = None
        tail = None

        for hid in head_order:
            if hid in entities:
                head = hid
                break
        if head is None:
            head = entities[0]

        for tid in tail_order:
            if tid in entities and tid != head:
                tail = tid
                break
        if tail is None:
            # fallback: ??? ?? ???? tail?
            for ent in entities:
                if ent != head:
                    tail = ent
                    break

        # ?? ???? ???
        conditions = [e for e in entities if e not in {head, tail}]
        return head, tail, conditions

    def _keyword_fallback(self, query: str) -> Tuple[List[str], Dict[str, str]]:
        """키워드 기반 간단 매핑"""
        keyword_map = {
            "brt": ("BRT", "BRT"),
            "혼잡": ("Traffic_Congestion", "교통 혼잡"),
            "교통 혼잡": ("Traffic_Congestion", "교통 혼잡"),
            "통행 시간": ("Travel_Time", "통행 시간"),
            "이동 시간": ("Travel_Time", "이동 시간"),
            "배차": ("Bus_Headway", "배차간격"),
            "배차간격": ("Bus_Headway", "배차간격"),
            "폭우": ("Heavy_Rain", "폭우"),
            "폭설": ("Heavy_Snow", "폭설"),
            "공사": ("Road_Construction", "도로 공사"),
            "도로 공사": ("Road_Construction", "도로 공사"),
            "속도": ("Traffic_Speed", "교통 속도"),
            "교통 속도": ("Traffic_Speed", "교통 속도"),
            "출퇴근": ("Rush_Hour", "출퇴근 시간"),
        }
        entities: List[str] = []
        entity_names: Dict[str, str] = {}
        lower_q = query.lower()
        for key, (eid, name) in keyword_map.items():
            if key.lower() in lower_q or key in query:
                if eid not in entities:
                    entities.append(eid)
                    entity_names[eid] = name
        return entities, entity_names
