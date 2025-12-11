"""
Sign Validator
"Student가 추정한 +, - 방향이 문맥과 도메인에서 타당한가?"

검증 단계:
1. 문장 패턴 기반 sign 추정
2. Static Domain 기반 논리 체크
3. LLM 보조 판단 (필요 시)
"""
import re
import logging
from typing import Optional, Dict, Any, List

from src.shared.models import RawEdge, ResolvedEntity, Polarity
from src.validation.models import SignValidationResult, SignTag
from src.llm.ollama_client import OllamaClient
from config.settings import get_settings

logger = logging.getLogger(__name__)


class SignValidator:
    """
    Sign Validator
    관계 방향성(+, -)의 논리적 타당성 검사
    """
    
    def __init__(self, llm_client: Optional[OllamaClient] = None):
        self.settings = get_settings()
        self.llm_client = llm_client
        self._static_domain = self._load_static_domain()
        self._sign_patterns = self._load_sign_patterns()
        
        # Static rules를 빠르게 조회할 수 있는 맵
        self._static_rules_map = self._build_static_rules_map()
    
    def _load_static_domain(self) -> Dict[str, Any]:
        try:
            return self.settings.load_yaml_config("static_domain")
        except FileNotFoundError:
            logger.warning("Static domain not found")
            return {}
    
    def _load_sign_patterns(self) -> Dict[str, List[str]]:
        patterns = self._static_domain.get("sign_patterns", {})
        return {
            "positive": patterns.get("positive", []),
            "negative": patterns.get("negative", []),
            "inverse": patterns.get("inverse", []),
        }
    
    def _build_static_rules_map(self) -> Dict[tuple, Dict[str, Any]]:
        """(head_canonical, tail_canonical) -> rule 맵 생성"""
        rules_map = {}
        for rule in self._static_domain.get("static_rules", []):
            key = (rule.get("head"), rule.get("tail"))
            rules_map[key] = rule
        return rules_map
    
    def validate(
        self,
        edge: RawEdge,
        fragment_text: str,
        resolved_entities: List[ResolvedEntity],
        use_llm: bool = True,
    ) -> SignValidationResult:
        """
        Sign 검증 수행
        
        Args:
            edge: 검증할 Edge
            fragment_text: 원본 fragment 텍스트
            resolved_entities: Resolved Entity 리스트
        
        Returns:
            SignValidationResult
        """
        entity_map = {e.entity_id: e for e in resolved_entities}
        head_entity = entity_map.get(edge.head_entity_id)
        tail_entity = entity_map.get(edge.tail_entity_id)
        
        # Step 1: 문장 패턴 기반 sign 추정
        pattern_polarity = self._estimate_from_patterns(fragment_text)
        
        # Step 2: Static Domain 기반 논리 체크
        domain_polarity = None
        conflict_with_static = False
        static_certainty = 0.0
        
        if head_entity and tail_entity:
            head_canonical = head_entity.canonical_id
            tail_canonical = tail_entity.canonical_id
            
            if head_canonical and tail_canonical:
                static_rule = self._static_rules_map.get((head_canonical, tail_canonical))
                if static_rule:
                    domain_polarity = static_rule.get("polarity")
                    static_certainty = static_rule.get("certainty", 0.8)
                    
                    # Student의 추정과 Static 규칙 비교
                    student_pol = self._normalize_polarity(edge.polarity_guess)
                    if domain_polarity and student_pol:
                        if student_pol != domain_polarity and student_pol != "unknown":
                            conflict_with_static = True
                            logger.warning(
                                f"Static domain conflict: {edge.raw_edge_id}, "
                                f"student={student_pol}, domain={domain_polarity}"
                            )
        
        # Step 3: LLM 보조 판단 (애매한 경우)
        llm_polarity = None
        if use_llm and self.llm_client and pattern_polarity is None:
            llm_polarity = self._get_llm_polarity(fragment_text, edge)
        
        # 최종 polarity 결정
        polarity_final, sign_tag, consistency_score = self._determine_final_sign(
            student_polarity=self._normalize_polarity(edge.polarity_guess),
            pattern_polarity=pattern_polarity,
            domain_polarity=domain_polarity,
            llm_polarity=llm_polarity,
            conflict_with_static=conflict_with_static,
            static_certainty=static_certainty,
        )
        
        return SignValidationResult(
            edge_id=edge.raw_edge_id,
            polarity_final=polarity_final,
            sign_tag=sign_tag,
            sign_consistency_score=consistency_score,
            pattern_polarity=pattern_polarity,
            domain_polarity=domain_polarity,
            llm_polarity=llm_polarity,
            conflict_with_static=conflict_with_static,
        )
    
    def _normalize_polarity(self, polarity) -> Optional[str]:
        """Polarity를 문자열로 정규화"""
        if polarity is None:
            return None
        if isinstance(polarity, Polarity):
            if polarity == Polarity.POSITIVE:
                return "+"
            elif polarity == Polarity.NEGATIVE:
                return "-"
            elif polarity == Polarity.NEUTRAL:
                return "neutral"
            else:
                return "unknown"
        return str(polarity)
    
    def _estimate_from_patterns(self, text: str) -> Optional[str]:
        """문장 패턴에서 sign 추정"""
        text_lower = text.lower()
        
        # 역관계 패턴 먼저 체크
        for pattern in self._sign_patterns.get("inverse", []):
            if pattern in text_lower:
                return "-"
        
        pos_count = sum(1 for p in self._sign_patterns.get("positive", []) if p in text_lower)
        neg_count = sum(1 for p in self._sign_patterns.get("negative", []) if p in text_lower)
        
        if pos_count > 0 and neg_count == 0:
            return "+"
        elif neg_count > 0 and pos_count == 0:
            return "-"
        elif pos_count > 0 and neg_count > 0:
            # 둘 다 있으면 None (애매함)
            return None
        
        return None
    
    def _get_llm_polarity(self, text: str, edge: RawEdge) -> Optional[str]:
        """LLM에게 polarity 판단 요청"""
        prompt = f"""다음 문장에서 "{edge.head_canonical_name}"이 "{edge.tail_canonical_name}"에 미치는 영향의 방향성을 판단하세요.

문장: "{text}"

응답 형식 (JSON):
{{"polarity": "+", "confidence": 0.8}}

polarity 값:
- "+": 양의 영향 (상승, 증가, 강세 등)
- "-": 음의 영향 (하락, 감소, 약세 등)
- "neutral": 중립적 또는 방향성 없음
- "unknown": 판단 불가"""

        try:
            result = self.llm_client.generate_json(prompt=prompt, temperature=0.1)
            return result.get("polarity")
        except Exception as e:
            logger.warning(f"LLM polarity check failed: {e}")
            return None
    
    def _determine_final_sign(
        self,
        student_polarity: Optional[str],
        pattern_polarity: Optional[str],
        domain_polarity: Optional[str],
        llm_polarity: Optional[str],
        conflict_with_static: bool,
        static_certainty: float,
    ) -> tuple:
        """최종 sign 결정"""
        
        # Static domain과 충돌하면 suspect
        if conflict_with_static and static_certainty >= 0.9:
            return domain_polarity or "unknown", SignTag.SUSPECT, 0.3
        
        # 모든 소스 수집
        sources = [p for p in [student_polarity, pattern_polarity, domain_polarity, llm_polarity] if p and p != "unknown"]
        
        if not sources:
            return "unknown", SignTag.UNKNOWN, 0.0
        
        # 모두 일치하면 confident
        if len(set(sources)) == 1:
            return sources[0], SignTag.CONFIDENT, 0.9
        
        # Domain이 있으면 domain 우선
        if domain_polarity:
            # domain과 일치하는 소스 개수
            matching = sum(1 for s in sources if s == domain_polarity)
            if matching >= len(sources) / 2:
                return domain_polarity, SignTag.CONFIDENT, 0.8
            else:
                return domain_polarity, SignTag.AMBIGUOUS, 0.6
        
        # 다수결
        from collections import Counter
        counter = Counter(sources)
        most_common = counter.most_common(1)[0]
        
        if most_common[1] > len(sources) / 2:
            return most_common[0], SignTag.AMBIGUOUS, 0.5
        
        return student_polarity or "unknown", SignTag.AMBIGUOUS, 0.4
