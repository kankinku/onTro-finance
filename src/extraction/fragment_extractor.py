"""
Fragment Extraction Module
"문장을 의미 단위로 잘라서 분석 가능한 최소 조각 만들기"

원칙:
- 조건 A: 의미 단위 유지 (관계가 독립적으로 추출 가능한 단위)
- 조건 B: 결합된 인과 구조 보존 (~하면 ~한다 / ~때문에 등)
- 조건 C: 노이즈 제거 (감탄문, 가치판단 등)
"""
import re
import logging
from typing import List, Optional
from datetime import datetime

from src.shared.models import Fragment, QualityTag
from src.shared.exceptions import FragmentExtractionError
from src.llm.ollama_client import OllamaClient
from config.settings import get_settings

logger = logging.getLogger(__name__)


# 노이즈 패턴 (감탄문, 감정 표현 등)
NOISE_PATTERNS = [
    r'^(대박|미쳤다|헐|와|오|어머|세상에|진짜|마지막으로)',
    r'^(좋다|나쁘다|불안하다|걱정된다|기대된다)[\.\!\?]?$',
    r'^[ㅋㅎㅠㅜ]+$',
    r'^[\!\?\.]+$',
]

# 인과 구조 패턴 (분리 금지)
CAUSAL_PATTERNS = [
    r'.+(하면|되면|시|때).+(한다|된다|이다|있다)',  # ~하면 ~한다
    r'.+(때문에|인해|으로 인해).+',  # ~때문에
    r'.+(영향으로|결과로).+',  # ~영향으로
    r'.+(따라서|그러므로|결국).+',  # 결론 연결
]


class FragmentExtractor:
    """
    Fragment Extraction Module
    
    Raw text를 의미 단위의 fragment로 분할
    """
    
    def __init__(self, llm_client: Optional[OllamaClient] = None):
        self.settings = get_settings().extraction
        self.llm_client = llm_client
        self._noise_regex = [re.compile(p, re.IGNORECASE) for p in NOISE_PATTERNS]
        self._causal_regex = [re.compile(p) for p in CAUSAL_PATTERNS]
    
    def extract(
        self,
        raw_text: str,
        doc_id: str,
        use_llm: bool = True,
    ) -> List[Fragment]:
        """
        Raw text에서 fragments 추출
        
        Args:
            raw_text: 원본 텍스트
            doc_id: 문서 ID
            use_llm: LLM 기반 분할 사용 여부
        
        Returns:
            Fragment 리스트
        
        Raises:
            FragmentExtractionError: 추출 실패 시
        """
        if not raw_text or not raw_text.strip():
            raise FragmentExtractionError(
                message="Empty raw text provided",
                doc_id=doc_id,
                recoverable=False,
            )
        
        try:
            if use_llm and self.llm_client:
                fragments = self._extract_with_llm(raw_text, doc_id)
            else:
                fragments = self._extract_rule_based(raw_text, doc_id)
            
            # 품질 태깅
            fragments = [self._tag_quality(f) for f in fragments]
            
            # 길이 필터링
            fragments = self._filter_by_length(fragments)
            
            logger.info(f"Extracted {len(fragments)} fragments from doc {doc_id}")
            return fragments
            
        except FragmentExtractionError:
            raise
        except Exception as e:
            raise FragmentExtractionError(
                message=f"Fragment extraction failed: {str(e)}",
                doc_id=doc_id,
                raw_text_preview=raw_text,
                recoverable=True,
            )
    
    def _extract_with_llm(self, raw_text: str, doc_id: str) -> List[Fragment]:
        """LLM 기반 fragment 추출"""
        system_prompt = """당신은 금융/경제 텍스트를 분석하는 전문가입니다.
주어진 텍스트를 의미 단위로 분할해주세요.

규칙:
1. 각 fragment는 하나의 관계(인과, 영향 등)를 포함해야 합니다.
2. "~하면 ~한다", "~때문에" 같은 인과 구조는 절대 나누지 마세요.
3. 감탄문, 감정 표현은 별도로 분리하세요.
4. 각 fragment는 독립적으로 해석 가능해야 합니다.

JSON 형식으로 응답:
{
  "fragments": [
    {"text": "fragment 1 텍스트", "quality": "informative"},
    {"text": "fragment 2 텍스트", "quality": "noisy"}
  ]
}

quality 값: informative, noisy, unclear, emotional, incomplete"""

        prompt = f"""다음 텍스트를 의미 단위 fragment로 분할해주세요:

{raw_text}"""

        try:
            result = self.llm_client.generate_json(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.1,
            )
            
            fragments = []
            for i, frag_data in enumerate(result.get("fragments", [])):
                text = frag_data.get("text", "").strip()
                if not text:
                    continue
                
                # 원문에서 위치 찾기
                start = raw_text.find(text)
                end = start + len(text) if start >= 0 else None
                
                quality_str = frag_data.get("quality", "informative")
                try:
                    quality = QualityTag(quality_str)
                except ValueError:
                    quality = QualityTag.INFORMATIVE
                
                fragment = Fragment(
                    text=text,
                    doc_id=doc_id,
                    quality_tag=quality,
                    source_start=start if start >= 0 else None,
                    source_end=end,
                )
                fragments.append(fragment)
            
            return fragments
            
        except Exception as e:
            logger.warning(f"LLM extraction failed, falling back to rule-based: {e}")
            return self._extract_rule_based(raw_text, doc_id)
    
    def _extract_rule_based(self, raw_text: str, doc_id: str) -> List[Fragment]:
        """규칙 기반 fragment 추출 (fallback)"""
        # 기본 분할: 문장 단위
        sentences = self._split_sentences(raw_text)
        
        fragments = []
        current_pos = 0
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            
            # 원문 위치 찾기
            start = raw_text.find(sentence, current_pos)
            if start >= 0:
                current_pos = start + len(sentence)
            
            # 인과 구조 체크 - 여러 관계가 있으면 분할
            sub_fragments = self._split_multiple_relations(sentence)
            
            for sub_text in sub_fragments:
                fragment = Fragment(
                    text=sub_text,
                    doc_id=doc_id,
                    source_start=start if start >= 0 else None,
                    source_end=start + len(sub_text) if start >= 0 else None,
                )
                fragments.append(fragment)
        
        return fragments
    
    def _split_sentences(self, text: str) -> List[str]:
        """문장 분할"""
        # 마침표, 물음표, 느낌표로 분할 (단, 숫자 뒤의 마침표는 제외)
        pattern = r'(?<![0-9])[\.\?\!]+(?=\s|$)'
        sentences = re.split(pattern, text)
        return [s.strip() for s in sentences if s.strip()]
    
    def _split_multiple_relations(self, sentence: str) -> List[str]:
        """
        여러 관계가 포함된 문장을 분할
        단, 인과 구조는 보존
        """
        # "~하고," / "~하며," 등으로 연결된 경우
        connectors = [', 그리고 ', '하고, ', '하며, ', '; ']
        
        # 인과 구조가 있으면 분할하지 않음
        for pattern in self._causal_regex:
            if pattern.match(sentence):
                return [sentence]
        
        # 연결어로 분할 시도
        for conn in connectors:
            if conn in sentence:
                parts = sentence.split(conn)
                if len(parts) == 2 and all(len(p.strip()) > 10 for p in parts):
                    return [p.strip() for p in parts]
        
        return [sentence]
    
    def _tag_quality(self, fragment: Fragment) -> Fragment:
        """Fragment 품질 태깅"""
        text = fragment.text.strip()
        
        # 노이즈 체크
        for pattern in self._noise_regex:
            if pattern.match(text):
                fragment.quality_tag = QualityTag.NOISY
                return fragment
        
        # 너무 짧으면 불완전
        if len(text) < self.settings.min_fragment_length:
            fragment.quality_tag = QualityTag.INCOMPLETE
        
        # 물음표만 있으면 불명확
        if text.endswith('?') and '?' not in text[:-1]:
            fragment.quality_tag = QualityTag.UNCLEAR
        
        return fragment
    
    def _filter_by_length(self, fragments: List[Fragment]) -> List[Fragment]:
        """길이 기반 필터링"""
        filtered = []
        for f in fragments:
            text_len = len(f.text.strip())
            if text_len < self.settings.min_fragment_length:
                logger.debug(f"Fragment too short, skipping: {f.text[:30]}...")
                continue
            if text_len > self.settings.max_fragment_length:
                logger.warning(f"Fragment too long: {f.text[:50]}...")
                # 너무 긴 건 일단 포함하되 warning
            filtered.append(f)
        return filtered
