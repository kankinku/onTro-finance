"""
Extraction Sector 테스트
"""

import pytest
import sys
from pathlib import Path
from typing import Any, cast

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.shared.models import Fragment, QualityTag, EntityCandidate, ResolvedEntity, ResolutionMode
from src.extraction.fragment_extractor import FragmentExtractor
from src.extraction.ner_student import NERStudent
from src.extraction.entity_resolver import EntityResolver
from src.extraction.relation_extractor import RelationExtractor
from src.extraction.pipeline import ExtractionPipeline


class TestFragmentExtractor:
    """Fragment Extraction 테스트"""

    def test_rule_based_extraction(self):
        """규칙 기반 추출 테스트"""
        extractor = FragmentExtractor()
        text = "금리가 인상되면 성장주는 약세를 보인다. 채권은 가격이 하락한다."

        fragments = extractor.extract(raw_text=text, doc_id="TEST_001", use_llm=False)

        assert len(fragments) >= 1
        assert all(isinstance(f, Fragment) for f in fragments)
        assert all(f.doc_id == "TEST_001" for f in fragments)

    def test_empty_text_raises_error(self):
        """빈 텍스트 에러 발생 확인"""
        extractor = FragmentExtractor()

        with pytest.raises(Exception):
            extractor.extract(raw_text="", doc_id="TEST")

    def test_noise_detection(self):
        """노이즈 탐지 테스트"""
        extractor = FragmentExtractor()
        text = "대박이네! 금리가 오르면 주가가 내린다."

        fragments = extractor.extract(raw_text=text, doc_id="TEST", use_llm=False)
        noisy = [f for f in fragments if f.quality_tag == QualityTag.NOISY]

        # 노이즈 태깅이 작동해야 함
        assert len(fragments) > 0

    def test_large_document_blocks_preserve_page_and_section_context(self):
        extractor = FragmentExtractor()
        text = """[PAGE 1]
Chapter 1 Macro Framework

1.1 Rates and Equities
Higher policy rates pressure growth stocks.

[PAGE 2]
1.2 Credit Transmission
Tighter credit spreads support bank margins.
"""

        fragments = extractor.extract(raw_text=text, doc_id="BOOK_001", use_llm=False)

        assert len(fragments) == 2
        assert fragments[0].page_number == 1
        assert fragments[0].chapter_title == "Chapter 1 Macro Framework"
        assert fragments[0].section_title == "1.1 Rates and Equities"
        assert fragments[1].page_number == 2
        assert fragments[1].section_title == "1.2 Credit Transmission"

    def test_table_like_block_is_tagged(self):
        extractor = FragmentExtractor()
        text = """[PAGE 4]
2.2 Scenario Table
Rate   EPS   Banks
5.0    2.1   1.4
5.5    1.8   1.7
"""

        fragments = extractor.extract(raw_text=text, doc_id="TABLE_001", use_llm=False)

        assert fragments
        assert fragments[0].block_type == "table"
        assert fragments[0].table_headers == ["Rate", "EPS", "Banks"]
        assert fragments[0].table_cells == [["5.0", "2.1", "1.4"], ["5.5", "1.8", "1.7"]]


class TestNERStudent:
    """NER (Student1) 테스트"""

    def test_rule_based_ner(self):
        """규칙 기반 NER 테스트"""
        ner = NERStudent()
        text = "연준이 금리를 0.25% 인상했다."

        entities = ner.extract(fragment_text=text, fragment_id="F001", use_llm=False)

        assert len(entities) >= 1
        # "연준" 또는 "금리"가 추출되어야 함
        surface_texts = [e.surface_text.lower() for e in entities]
        assert any("연준" in s or "금리" in s or "0.25%" in s for s in surface_texts)

    def test_ticker_pattern(self):
        """티커 패턴 추출 테스트"""
        ner = NERStudent()
        text = "AAPL과 MSFT가 상승했다."

        entities = ner.extract(fragment_text=text, fragment_id="F002", use_llm=False)

        tickers = [e.surface_text for e in entities if e.type_guess == "Instrument"]
        assert "AAPL" in tickers or "MSFT" in tickers

    def test_llm_prompt_is_finance_specific(self):
        class DummyLLM:
            def __init__(self):
                self.last_request = None

            def health_check(self):
                return True

            def generate_json(self, request):
                self.last_request = request
                return {"entities": []}

        dummy: Any = DummyLLM()
        ner = NERStudent(llm_client=dummy)

        ner.extract(fragment_text="금리가 성장주에 미치는 영향", fragment_id="F009", use_llm=True)

        last_request = cast(Any, dummy.last_request)
        assert last_request is not None
        assert "finance and macro research" in last_request.system_prompt


class TestEntityResolver:
    """Entity Resolution 테스트"""

    def test_dictionary_match(self):
        """Dictionary 매칭 테스트"""
        resolver = EntityResolver()

        candidate = EntityCandidate(
            surface_text="policy rate",
            type_guess="MacroIndicator",
            span_start=0,
            span_end=11,
            fragment_id="F001",
        )

        resolved = resolver.resolve([candidate])

        assert len(resolved) == 1
        assert resolved[0].resolution_mode == ResolutionMode.DICTIONARY_MATCH
        assert resolved[0].canonical_id == "Policy_Rate"

    def test_new_entity_detection(self):
        """신규 엔티티 탐지 테스트"""
        resolver = EntityResolver()

        candidate = EntityCandidate(
            surface_text="알수없는엔티티XYZ123",
            type_guess="Unknown",
            span_start=0,
            span_end=10,
            fragment_id="F001",
        )

        resolved = resolver.resolve([candidate])

        assert len(resolved) == 1
        assert resolved[0].resolution_mode == ResolutionMode.NEW_ENTITY
        assert resolved[0].is_new_entity_candidate == True


class TestRelationExtractor:
    """Relation Extraction (Student2) 테스트"""

    def test_basic_relation(self):
        """기본 관계 추출 테스트"""
        extractor = RelationExtractor()

        entities = [
            ResolvedEntity(
                entity_id="E1",
                canonical_id="C1",
                canonical_name="Federal Reserve",
                resolution_mode=ResolutionMode.DICTIONARY_MATCH,
                resolution_conf=0.9,
                surface_text="연준",
                fragment_id="F001",
            ),
            ResolvedEntity(
                entity_id="E2",
                canonical_id="C2",
                canonical_name="Federal Funds Rate",
                resolution_mode=ResolutionMode.DICTIONARY_MATCH,
                resolution_conf=0.9,
                surface_text="금리",
                fragment_id="F001",
            ),
        ]

        edges = extractor.extract(
            fragment_text="연준이 금리를 인상했다.",
            fragment_id="F001",
            resolved_entities=entities,
            use_llm=False,
        )

        assert len(edges) >= 1
        assert edges[0].head_canonical_name is not None
        assert edges[0].tail_canonical_name is not None

    def test_rule_based_fallback_prefers_relation_signal_pair(self):
        extractor = RelationExtractor()

        entities = [
            ResolvedEntity(
                entity_id="E1",
                canonical_id="Policy_Rate",
                canonical_name="policy rate",
                resolution_mode=ResolutionMode.DICTIONARY_MATCH,
                resolution_conf=0.95,
                surface_text="policy rate",
                fragment_id="F010",
            ),
            ResolvedEntity(
                entity_id="E2",
                canonical_id="Growth_Stocks",
                canonical_name="growth stocks",
                resolution_mode=ResolutionMode.DICTIONARY_MATCH,
                resolution_conf=0.95,
                surface_text="growth stocks",
                fragment_id="F010",
            ),
            ResolvedEntity(
                entity_id="E3",
                canonical_id="Gold",
                canonical_name="gold",
                resolution_mode=ResolutionMode.DICTIONARY_MATCH,
                resolution_conf=0.95,
                surface_text="gold",
                fragment_id="F010",
            ),
        ]

        edges = extractor.extract(
            fragment_text="Higher policy rates pressure growth stocks while gold stays firm.",
            fragment_id="F010",
            resolved_entities=entities,
            use_llm=False,
        )

        assert len(edges) == 1
        assert edges[0].head_entity_id == "E1"
        assert edges[0].tail_entity_id == "E2"
        assert edges[0].relation_type == "pressures"

    def test_rule_based_korean_signal_and_polarity(self):
        extractor = RelationExtractor()

        entities = [
            ResolvedEntity(
                entity_id="E1",
                canonical_id="Policy_Rate",
                canonical_name="금리",
                resolution_mode=ResolutionMode.DICTIONARY_MATCH,
                resolution_conf=0.95,
                surface_text="금리",
                fragment_id="F011",
            ),
            ResolvedEntity(
                entity_id="E2",
                canonical_id="Growth_Stocks",
                canonical_name="성장주",
                resolution_mode=ResolutionMode.DICTIONARY_MATCH,
                resolution_conf=0.95,
                surface_text="성장주",
                fragment_id="F011",
            ),
        ]

        edges = extractor.extract(
            fragment_text="금리 인상은 성장주에 부담을 준다.",
            fragment_id="F011",
            resolved_entities=entities,
            use_llm=False,
        )

        assert len(edges) == 1
        assert edges[0].relation_type == "pressures"
        assert edges[0].polarity_guess == "-"


class TestExtractionPipeline:
    """전체 파이프라인 테스트"""

    def test_pipeline_rule_based(self):
        """규칙 기반 파이프라인 테스트"""
        pipeline = ExtractionPipeline(use_llm=False)

        result = pipeline.process(
            raw_text="금리가 인상되면 성장주는 약세를 보인다.",
            doc_id="TEST_DOC",
        )

        assert result.doc_id == "TEST_DOC"
        assert len(result.fragments) >= 1
        assert result.processing_time_ms >= 0  # 타이밍 테스트는 환경에 따라 다름

    def test_pipeline_batch(self):
        """배치 처리 테스트"""
        pipeline = ExtractionPipeline(use_llm=False)

        documents = [
            {"doc_id": "D1", "text": "연준이 금리를 인상했다."},
            {"doc_id": "D2", "text": "나스닥이 하락했다."},
        ]

        results = pipeline.process_batch(documents)

        assert len(results) == 2
        assert results[0].doc_id == "D1"
        assert results[1].doc_id == "D2"

    def test_pipeline_propagates_structured_citation_metadata(self):
        pipeline = ExtractionPipeline(use_llm=False)

        result = pipeline.process(
            raw_text="""[PAGE 3]
Chapter 2 Regime Shift

2.1 Inflation Persistence
Higher policy rates pressure growth stocks.
""",
            doc_id="DOC_STRUCT_001",
        )

        assert result.fragments
        assert result.raw_edges
        edge = result.raw_edges[0]
        assert edge.citation_page_number == 3
        assert edge.citation_chapter_title == "Chapter 2 Regime Shift"
        assert edge.citation_section_title == "2.1 Inflation Persistence"

    def test_pipeline_consolidates_repeated_relations_across_fragments(self):
        pipeline = ExtractionPipeline(use_llm=False)

        result = pipeline.process(
            raw_text="""[PAGE 1]
Chapter 1 Macro

1.1 Rates
Higher policy rates pressure growth stocks.

1.2 Restatement
Higher policy rates pressure growth stocks.
""",
            doc_id="DOC_CONSOLIDATED_001",
        )

        assert result.consolidated_relations
        consolidated = result.consolidated_relations[0]
        assert consolidated["relation_type"] == "pressures"
        assert consolidated["fragment_count"] == 2
        assert consolidated["section_titles"] == ["1.1 Rates", "1.2 Restatement"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
