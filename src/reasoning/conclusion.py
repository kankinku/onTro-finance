"""
Conclusion Synthesizer
"Reasoning 결과를 해석 가능한 자연어 형태로 재구성"

LLM은 오직 표현에만 사용 - 계산은 그래프 기반으로 수행
"""
import logging
from typing import Optional

from src.reasoning.models import (
    ParsedQuery, ReasoningResult, ReasoningConclusion, ReasoningDirection
)
from src.llm.llm_client import LLMClient, LLMRequest

logger = logging.getLogger(__name__)


class ConclusionSynthesizer:
    """
    Conclusion Synthesizer
    추론 결과를 자연어로 변환
    """
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client
    
    def synthesize(
        self,
        parsed_query: ParsedQuery,
        reasoning_result: ReasoningResult,
    ) -> ReasoningConclusion:
        """
        추론 결과를 자연어 결론으로 변환
        
        Args:
            parsed_query: 파싱된 질문
            reasoning_result: 추론 결과
        
        Returns:
            ReasoningConclusion
        """
        # 기본 구조화된 결론 생성
        conclusion_text = self._generate_conclusion_text(parsed_query, reasoning_result)
        explanation_text = self._generate_explanation(parsed_query, reasoning_result)
        strongest_path_desc = self._describe_strongest_path(reasoning_result)
        evidence_summary = self._summarize_evidence(reasoning_result)
        
        # LLM으로 자연스럽게 다듬기 (선택적)
        if self.llm_client:
            conclusion_text = self._polish_with_llm(
                conclusion_text, parsed_query.original_query
            )
        
        return ReasoningConclusion(
            query_id=parsed_query.query_id,
            original_query=parsed_query.original_query,
            conclusion_text=conclusion_text,
            explanation_text=explanation_text,
            direction=reasoning_result.direction,
            confidence=reasoning_result.confidence,
            strongest_path_description=strongest_path_desc,
            evidence_summary=evidence_summary,
            reasoning_result=reasoning_result,
        )
    
    def _generate_conclusion_text(
        self,
        query: ParsedQuery,
        result: ReasoningResult,
    ) -> str:
        """결론 텍스트 생성"""
        head_name = query.entity_names.get(query.head_entity, query.head_entity or "")
        tail_name = query.entity_names.get(query.tail_entity, query.tail_entity or "")
        
        direction = result.direction
        confidence = result.confidence
        
        if direction == ReasoningDirection.POSITIVE:
            dir_text = "양의 영향(상승)"
        elif direction == ReasoningDirection.NEGATIVE:
            dir_text = "음의 영향(하락)"
        elif direction == ReasoningDirection.NEUTRAL:
            dir_text = "중립적 영향"
        else:
            dir_text = "불확실"
        
        conf_text = self._confidence_text(confidence)
        
        if not tail_name:
            return f"{head_name}에 대한 분석 결과: {dir_text} 방향이 {conf_text} 예상됩니다."
        
        return f"{head_name}이(가) {tail_name}에 {dir_text}을 미칩니다. (신뢰도: {conf_text})"
    
    def _confidence_text(self, confidence: float) -> str:
        """신뢰도를 텍스트로"""
        if confidence >= 0.8:
            return "매우 높음"
        elif confidence >= 0.6:
            return "높음"
        elif confidence >= 0.4:
            return "중간"
        elif confidence >= 0.2:
            return "낮음"
        else:
            return "매우 낮음"
    
    def _generate_explanation(
        self,
        query: ParsedQuery,
        result: ReasoningResult,
    ) -> str:
        """설명 생성"""
        lines = []
        
        # 경로 수
        lines.append(f"분석에 사용된 경로: {len(result.paths_used)}개")
        
        # 증거 요약
        lines.append(
            f"양의 증거: {result.positive_evidence:.3f}, "
            f"음의 증거: {result.negative_evidence:.3f}"
        )
        
        if result.conflicting_paths > 0:
            lines.append(f"주의: {result.conflicting_paths}개의 상충되는 경로 발견")
        
        return "\n".join(lines)
    
    def _describe_strongest_path(self, result: ReasoningResult) -> str:
        """가장 강한 경로 설명"""
        if not result.strongest_path:
            return "경로 없음"
        
        path = result.strongest_path
        arrows = []
        
        for i, node in enumerate(path.node_names):
            if i < len(path.edge_signs):
                sign = "↑" if path.edge_signs[i] == "+" else "↓"
                arrows.append(f"{node} {sign}")
            else:
                arrows.append(node)
        
        return " → ".join(arrows)
    
    def _summarize_evidence(self, result: ReasoningResult) -> str:
        """증거 요약"""
        total = result.positive_evidence + result.negative_evidence
        if total == 0:
            return "사용 가능한 증거 없음"
        
        pos_ratio = result.positive_evidence / total * 100
        neg_ratio = result.negative_evidence / total * 100
        
        return f"양의 증거 {pos_ratio:.1f}%, 음의 증거 {neg_ratio:.1f}%"
    
    def _polish_with_llm(self, text: str, original_query: str) -> str:
        """LLM으로 자연스럽게 다듬기"""
        try:
            prompt = f"""다음 분석 결과를 자연스러운 한국어로 다듬어주세요.
원래 질문: {original_query}
분석 결과: {text}

규칙:
1. 핵심 의미는 절대 변경하지 마세요
2. 수치나 방향성을 왜곡하지 마세요
3. 간결하게 2-3문장으로 작성하세요
"""
            request = LLMRequest(prompt=prompt, temperature=0.3)
            response = self.llm_client.generate(request)
            return response.content.strip() or text
        except Exception as e:
            logger.warning(f"LLM polish failed: {e}")
            return text
