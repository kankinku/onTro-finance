from src.extraction.entity_resolver import EntityResolver
from src.extraction.ner_student import NERStudent
from src.extraction.relation_extractor import RelationExtractor


def _extract_relations(text: str):
    fragment_id = "FIN_REG_001"
    ner = NERStudent()
    resolver = EntityResolver()
    relation_extractor = RelationExtractor()
    candidates = ner.extract(fragment_text=text, fragment_id=fragment_id, use_llm=False)
    resolved = resolver.resolve(candidates)
    return relation_extractor.extract(
        fragment_text=text,
        fragment_id=fragment_id,
        resolved_entities=resolved,
        use_llm=False,
    )


def test_policy_rates_pressure_growth_equities_regression():
    edges = _extract_relations(
        "Higher policy rates continue to pressure long-duration growth equities."
    )

    assert any(
        edge.relation_type == "pressures"
        and edge.head_canonical_name == "policy rate"
        and edge.tail_canonical_name == "growth stocks"
        for edge in edges
    )


def test_crude_oil_pressures_airlines_regression():
    edges = _extract_relations("Higher crude oil prices pressure airlines.")

    assert any(
        edge.relation_type == "pressures"
        and edge.head_canonical_name == "crude oil"
        and edge.tail_canonical_name == "airlines sector"
        for edge in edges
    )


def test_crude_oil_supports_producers_regression():
    edges = _extract_relations("Higher crude oil prices support oil producers.")

    assert any(
        edge.relation_type == "supports"
        and edge.head_canonical_name == "crude oil"
        and edge.tail_canonical_name == "energy sector"
        for edge in edges
    )


def test_real_yields_support_gold_regression():
    edges = _extract_relations("Lower real yields support gold.")

    assert any(
        edge.relation_type == "supports"
        and edge.head_canonical_name == "real yields"
        and edge.tail_canonical_name == "gold"
        for edge in edges
    )


def test_credit_spreads_signal_risk_aversion_regression():
    edges = _extract_relations("Wider credit spreads signal rising risk aversion.")

    assert any(
        edge.relation_type == "signals"
        and edge.head_canonical_name == "credit spreads"
        and edge.tail_canonical_name == "risk aversion"
        for edge in edges
    )


def test_rate_decline_supports_government_bonds_regression():
    edges = _extract_relations("Lower policy rates support government bonds.")

    assert any(
        edge.relation_type == "supports"
        and edge.head_canonical_name == "policy rate"
        and edge.tail_canonical_name == "government bonds"
        for edge in edges
    )


def test_korean_rate_pressure_growth_stocks_regression():
    edges = _extract_relations("금리 상승은 성장주에 부담이다.")

    assert any(
        edge.relation_type == "pressures"
        and edge.head_canonical_name == "policy rate"
        and edge.tail_canonical_name == "growth stocks"
        for edge in edges
    )


def test_dollar_pressures_commodities_regression():
    edges = _extract_relations("A stronger dollar pressures commodities.")

    assert any(
        edge.relation_type == "pressures"
        and edge.head_canonical_name == "us dollar"
        and edge.tail_canonical_name == "commodities"
        for edge in edges
    )


def test_korean_dollar_pressures_commodities_regression():
    edges = _extract_relations("달러 강세는 원자재에 부담이다.")

    assert any(
        edge.relation_type == "pressures"
        and edge.head_canonical_name == "us dollar"
        and edge.tail_canonical_name == "commodities"
        for edge in edges
    )
