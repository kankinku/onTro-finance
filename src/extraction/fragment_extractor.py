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
from dataclasses import dataclass
from typing import Any, List, Optional, cast
from datetime import datetime

from src.shared.models import Fragment, QualityTag
from src.shared.exceptions import FragmentExtractionError
from config.settings import get_settings

logger = logging.getLogger(__name__)


PAGE_MARKER_RE = re.compile(r"^\[PAGE\s+(\d+)\]$", re.IGNORECASE)
CHAPTER_HEADING_RE = re.compile(r"^(chapter\s+\d+|제\s*\d+장)\b.*", re.IGNORECASE)
SECTION_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)+|\d+\.)\s+.+|^(section\s+\d+)\b.*", re.IGNORECASE)


@dataclass
class _DocumentBlock:
    text: str
    start: int
    end: int
    page_number: Optional[int]
    chapter_title: Optional[str]
    section_title: Optional[str]
    block_type: str
    table_caption: Optional[str] = None
    table_rows: Optional[int] = None
    table_columns: Optional[int] = None


# 노이즈 패턴 (감탄문, 감정 표현 등)
NOISE_PATTERNS = [
    r"^(대박|미쳤다|헐|와|오|어머|세상에|진짜|마지막으로)",
    r"^(좋다|나쁘다|불안하다|걱정된다|기대된다)[\.\!\?]?$",
    r"^[ㅋㅎㅠㅜ]+$",
    r"^[\!\?\.]+$",
]

# 인과 구조 패턴 (분리 금지)
CAUSAL_PATTERNS = [
    r".+(하면|되면|시|때).+(한다|된다|이다|있다)",  # ~하면 ~한다
    r".+(때문에|인해|으로 인해).+",  # ~때문에
    r".+(영향으로|결과로).+",  # ~영향으로
    r".+(따라서|그러므로|결국).+",  # 결론 연결
]


class FragmentExtractor:
    """
    Fragment Extraction Module

    Raw text를 의미 단위의 fragment로 분할
    """

    def __init__(self, llm_client: Optional[Any] = None):
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
            llm_client = self.llm_client
            if llm_client is None:
                return self._extract_rule_based(raw_text, doc_id)

            result = llm_client.generate_json(
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
        fragments = []
        for block in self._extract_document_blocks(raw_text):
            sentences = self._split_sentences(block.text)
            block_pos = block.start

            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue

                start = raw_text.find(sentence, block_pos)
                if start >= 0:
                    block_pos = start + len(sentence)

                sub_fragments = self._split_multiple_relations(sentence)

                local_pos = start if start >= 0 else block.start
                for sub_text in sub_fragments:
                    sub_start = raw_text.find(sub_text, local_pos)
                    if sub_start >= 0:
                        local_pos = sub_start + len(sub_text)
                    fragment = Fragment(
                        text=sub_text,
                        doc_id=doc_id,
                        source_start=sub_start if sub_start >= 0 else None,
                        source_end=sub_start + len(sub_text) if sub_start >= 0 else None,
                        page_number=block.page_number,
                        chapter_title=block.chapter_title,
                        section_title=block.section_title,
                        block_type=block.block_type,
                        table_caption=block.table_caption,
                        table_rows=block.table_rows,
                        table_columns=block.table_columns,
                    )
                    fragments.append(fragment)

        return fragments

    def _extract_document_blocks(self, raw_text: str) -> List[_DocumentBlock]:
        lines = raw_text.splitlines(keepends=True)
        blocks: List[_DocumentBlock] = []
        current_page: Optional[int] = None
        current_chapter: Optional[str] = None
        current_section: Optional[str] = None
        buffer: List[str] = []
        buffer_start: Optional[int] = None
        offset = 0

        def flush_buffer(end_offset: int) -> None:
            nonlocal buffer, buffer_start
            text = "".join(buffer).strip()
            if text and buffer_start is not None:
                block_type, table_caption, table_rows, table_columns = self._classify_block(text)
                blocks.append(
                    _DocumentBlock(
                        text=text,
                        start=buffer_start,
                        end=end_offset,
                        page_number=current_page,
                        chapter_title=current_chapter,
                        section_title=current_section,
                        block_type=block_type,
                        table_caption=cast(Optional[str], table_caption),
                        table_rows=cast(Optional[int], table_rows),
                        table_columns=cast(Optional[int], table_columns),
                    )
                )
            buffer = []
            buffer_start = None

        for line in lines:
            stripped = line.strip()

            page_match = PAGE_MARKER_RE.match(stripped)
            if page_match:
                flush_buffer(offset)
                current_page = int(page_match.group(1))
                offset += len(line)
                continue

            if self._is_heading(stripped):
                flush_buffer(offset)
                if CHAPTER_HEADING_RE.match(stripped):
                    current_chapter = stripped
                    current_section = None
                else:
                    current_section = stripped
                offset += len(line)
                continue

            if not stripped:
                flush_buffer(offset)
                offset += len(line)
                continue

            if buffer_start is None:
                buffer_start = offset
            buffer.append(line)
            offset += len(line)

        flush_buffer(len(raw_text))
        if blocks:
            return blocks
        block_type, table_caption, table_rows, table_columns = self._classify_block(
            raw_text.strip()
        )
        return [
            _DocumentBlock(
                text=raw_text.strip(),
                start=0,
                end=len(raw_text),
                page_number=current_page,
                chapter_title=current_chapter,
                section_title=current_section,
                block_type=block_type,
                table_caption=cast(Optional[str], table_caption),
                table_rows=cast(Optional[int], table_rows),
                table_columns=cast(Optional[int], table_columns),
            )
        ]

    def _is_heading(self, text: str) -> bool:
        if not text:
            return False
        numeric_tokens = re.findall(r"\d+(?:\.\d+)?", text)
        alpha_tokens = re.findall(r"[A-Za-z가-힣]+", text)
        if len(numeric_tokens) >= 2 and len(alpha_tokens) <= 1:
            return False
        if CHAPTER_HEADING_RE.match(text) or SECTION_HEADING_RE.match(text):
            return True
        return len(text) < 120 and text == text.upper() and any(char.isalpha() for char in text)

    def _classify_block(self, text: str) -> tuple[str, Optional[str], Optional[int], Optional[int]]:
        raw_lines = [line for line in text.splitlines() if line.strip()]
        lines = [line.strip() for line in raw_lines]
        if len(lines) >= 2:
            numeric_cells = sum(1 for line in lines if re.search(r"\d", line))
            separator_cells = sum(1 for line in raw_lines if re.search(r"\s{2,}|\t|\|", line))
            if numeric_cells >= max(1, len(lines) // 2) and separator_cells >= max(
                1, len(lines) // 2
            ):
                caption = (
                    lines[0]
                    if len(lines[0]) < 80 and not re.search(r"\d\s{2,}\d", lines[0])
                    else None
                )
                data_lines = lines[1:] if caption else lines
                column_count = (
                    max(len(re.split(r"\s{2,}|\t|\|", line)) for line in data_lines)
                    if data_lines
                    else None
                )
                return ("table", caption, len(data_lines), column_count)
            if len(lines) >= 3 and numeric_cells >= 2:
                return ("table", lines[0] if len(lines[0]) < 80 else None, len(lines), None)
            header_like = len(re.split(r"\s{2,}|\t|\|", lines[0])) >= 2
            if (
                len(lines) >= 3
                and header_like
                and any(any(char.isdigit() for char in line) for line in lines[1:])
            ):
                return ("table", lines[0] if len(lines[0]) < 80 else None, len(lines), None)
        if len(text) < 120 and self._is_heading(text.strip()):
            return ("heading", None, None, None)
        return ("paragraph", None, None, None)

    def _split_sentences(self, text: str) -> List[str]:
        """문장 분할"""
        # 마침표, 물음표, 느낌표로 분할 (단, 숫자 뒤의 마침표는 제외)
        pattern = r"(?<![0-9])[\.\?\!]+(?=\s|$)"
        sentences = re.split(pattern, text)
        return [s.strip() for s in sentences if s.strip()]

    def _split_multiple_relations(self, sentence: str) -> List[str]:
        """
        여러 관계가 포함된 문장을 분할
        단, 인과 구조는 보존
        """
        # "~하고," / "~하며," 등으로 연결된 경우
        connectors = [", 그리고 ", "하고, ", "하며, ", "; "]

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
        if text.endswith("?") and "?" not in text[:-1]:
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
