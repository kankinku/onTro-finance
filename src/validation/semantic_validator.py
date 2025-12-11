"""
Semantic Validator
"형식도 맞고 방향도 맞아 보여도, 그 관계 자체가 실제로 말이 되는가를 체크"

검증 단계:
1. Local pattern heuristic (과장, spurious 탐지)
2. Domain consistency probe
3. LLM contextual judgement
"""
import logging
from typing import Optional, Dict, Any, List

from src.shared.models import RawEdge, ResolvedEntity
from src.validation.models import SemanticValidationResult, SemanticTag
from src.llm.ollama_client import OllamaClient
from config.settings import get_settings

logger = logging.getLogger(__name__)


class SemanticValidator:
    """
    Semantic Validator
    문맥·도메인 기반 의미 타당성 검사
    """
    
    def __init__(self, llm_client: Optional[OllamaClient] = None):
        self.settings = get_settings()
        self.llm_client = llm_client
        self._semantic_patterns = self._load_semantic_patterns()
    
    def _load_semantic_patterns(self) -> Dict[str, List[str]]:
        try:
            data = self.settings.load_yaml_config("static_domain")
            return data.get("semantic_patterns", {})
        except FileNotFoundError:
            return {
                "exaggeration": ["항상", "절대", "반드시"],
                "correlation_as_causation": ["동반", "함께", "같이"],
                "weak_evidence": ["아마", "것 같다", "추측"],
            }
    
    def validate(
        self,
        edge: RawEdge,
        fragment_text: str,
        resolved_entities: List[ResolvedEntity],
        domain_kg: Optional[Dict[str, Any]] = None,
        use_llm: bool = True,
    ) -> SemanticValidationResult:
        """
        Semantic 검증 수행
        
        Args:
            edge: 검증할 Edge
            fragment_text: 원본 fragment 텍스트
            resolved_entities: Resolved Entity 리스트
            domain_kg: Domain KG의 관련 서브그래프
        
        Returns:
            SemanticValidationResult
        """
        # Step 1: Local pattern heuristic
        has_exaggeration = self._check_exaggeration(fragment_text)
        is_correlation = self._check_correlation_as_causation(fragment_text, edge)
        has_weak = self._check_weak_evidence(fragment_text)
        
        # Step 2: Domain consistency probe
        domain_conflict = False
        if domain_kg:
            domain_conflict = self._check_domain_conflict(edge, domain_kg)
        
        # Step 3: LLM contextual judgement
        llm_judgement = None
        if use_llm and self.llm_client:
            llm_judgement = self._get_llm_judgement(edge, fragment_text)
        
        # 최종 태그 및 신뢰도 결정
        semantic_tag, semantic_conf = self._determine_semantic_tag(
            has_exaggeration=has_exaggeration,
            is_correlation=is_correlation,
            has_weak=has_weak,
            domain_conflict=domain_conflict,
            llm_judgement=llm_judgement,
        )
        
        return SemanticValidationResult(
            edge_id=edge.raw_edge_id,
            semantic_tag=semantic_tag,
            semantic_confidence=semantic_conf,
            has_exaggeration=has_exaggeration,
            is_correlation_as_causation=is_correlation,
            has_weak_evidence=has_weak,
            domain_conflict=domain_conflict,
            llm_judgement=llm_judgement,
        )
    
    def _check_exaggeration(self, text: str) -> bool:
        """과장 표현 체크"""
        patterns = self._semantic_patterns.get("exaggeration", [])
        return any(p in text for p in patterns)
    
    def _check_correlation_as_causation(self, text: str, edge: RawEdge) -> bool:
        """상관을 인과로 오해하는지 체크"""
        # Cause 관계인데 상관 패턴이 있으면 spurious 가능성
        if edge.relation_type != "Cause":
            return False
        
        patterns = self._semantic_patterns.get("correlation_as_causation", [])
        return any(p in text for p in patterns)
    
    def _check_weak_evidence(self, text: str) -> bool:
        """약한 증거 체크"""
        patterns = self._semantic_patterns.get("weak_evidence", [])
        return any(p in text for p in patterns)
    
    def _check_domain_conflict(self, edge: RawEdge, domain_kg: Dict[str, Any]) -> bool:
        """Domain KG와 충돌 체크"""
        # 간단한 구현: 동일 head-tail에 반대 sign이 있는지 확인
        existing = domain_kg.get("edges", {})
        
        for edge_id, edge_info in existing.items():
            if (edge_info.get("head") == edge.head_canonical_name and
                edge_info.get("tail") == edge.tail_canonical_name):
                
                existing_polarity = edge_info.get("polarity")
                new_polarity = str(edge.polarity_guess) if edge.polarity_guess else None
                
                if existing_polarity and new_polarity:
                    if existing_polarity != new_polarity:
                        return True
        
        return False
    
    def _get_llm_judgement(self, edge: RawEdge, text: str) -> Optional[str]:
        """LLM 의미 판단 요청"""
        prompt = f"""다음 관계가 문맥상 타당한지 평가하세요.

문장: "{text}"
관계: {edge.head_canonical_name} --[{edge.relation_type}]--> {edge.tail_canonical_name}

다음 중 하나로 판단하세요:
- valid: 문맥상 타당한 관계
- weak: 가능하지만 증거 부족
- spurious: 인과 과장 또는 상관을 인과로 오해
- wrong: 명백히 잘못된 관계
- ambiguous: 여러 해석 가능

응답 형식 (JSON):
{{"judgement": "valid", "reason": "이유"}}"""

        try:
            result = self.llm_client.generate_json(prompt=prompt, temperature=0.1)
            return result.get("judgement")
        except Exception as e:
            logger.warning(f"LLM semantic judgement failed: {e}")
            return None
    
    def _determine_semantic_tag(
        self,
        has_exaggeration: bool,
        is_correlation: bool,
        has_weak: bool,
        domain_conflict: bool,
        llm_judgement: Optional[str],
    ) -> tuple:
        """최종 semantic tag 결정"""
        
        # Domain conflict는 최우선
        if domain_conflict:
            return SemanticTag.SEM_WRONG, 0.2
        
        # LLM이 wrong이라고 판단
        if llm_judgement == "wrong":
            return SemanticTag.SEM_WRONG, 0.25
        
        # Spurious 판단
        if is_correlation or llm_judgement == "spurious":
            return SemanticTag.SEM_SPURIOUS, 0.35
        
        # LLM이 valid라고 하면 confident (단, 다른 flag 없을 때)
        if llm_judgement == "valid" and not has_exaggeration and not has_weak:
            return SemanticTag.SEM_CONFIDENT, 0.85
        
        # 과장 표현 있으면 weak
        if has_exaggeration:
            return SemanticTag.SEM_WEAK, 0.5
        
        # 약한 증거
        if has_weak:
            return SemanticTag.SEM_WEAK, 0.45
        
        # LLM 판단 기반
        if llm_judgement == "weak":
            return SemanticTag.SEM_WEAK, 0.5
        
        if llm_judgement == "ambiguous":
            return SemanticTag.SEM_AMBIGUOUS, 0.55
        
        # 기본값
        if llm_judgement == "valid":
            return SemanticTag.SEM_CONFIDENT, 0.75
        
        return SemanticTag.SEM_AMBIGUOUS, 0.5
