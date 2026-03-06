"""Korean finance fallback regression tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.extraction.relation_extractor import RelationExtractor
from src.shared.models import Polarity, ResolvedEntity, ResolutionMode


def _entity(entity_id: str, canonical_id: str, canonical_name: str, surface_text: str, fragment_id: str):
    return ResolvedEntity(
        entity_id=entity_id,
        canonical_id=canonical_id,
        canonical_name=canonical_name,
        resolution_mode=ResolutionMode.DICTIONARY_MATCH,
        resolution_conf=0.95,
        surface_text=surface_text,
        fragment_id=fragment_id,
    )


def test_korean_pressure_sentence_gets_negative_polarity():
    extractor = RelationExtractor()
    edges = extractor.extract(
        fragment_text="금리가 성장주에 하방압력을 준다.",
        fragment_id="F200",
        resolved_entities=[
            _entity("E1", "Policy_Rate", "금리", "금리", "F200"),
            _entity("E2", "Growth_Stocks", "성장주", "성장주", "F200"),
        ],
        use_llm=False,
    )

    assert len(edges) == 1
    assert edges[0].relation_type == "pressures"
    assert edges[0].polarity_guess == Polarity.NEGATIVE


def test_korean_benefit_sentence_gets_positive_polarity():
    extractor = RelationExtractor()
    edges = extractor.extract(
        fragment_text="유가 하락은 항공주에 수혜를 준다.",
        fragment_id="F201",
        resolved_entities=[
            _entity("E1", "Crude_Oil", "유가", "유가", "F201"),
            _entity("E2", "Airlines_Sector", "항공주", "항공주", "F201"),
        ],
        use_llm=False,
    )

    assert len(edges) == 1
    assert edges[0].relation_type == "supports"
    assert edges[0].polarity_guess == Polarity.POSITIVE
