"""DomainPipeline transaction tests aligned to the finance baseline."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.bootstrap import reset_all, get_graph_repository
from src.domain.pipeline import DomainPipeline
from src.shared.models import RawEdge, ResolvedEntity, ResolutionMode, Polarity
from src.validation.models import ValidationResult, ValidationDestination


def create_validation_result(edge_id: str, combined_conf: float = 0.78) -> ValidationResult:
    return ValidationResult(
        edge_id=edge_id,
        validation_passed=True,
        destination=ValidationDestination.DOMAIN_CANDIDATE,
        combined_conf=combined_conf,
        student_conf=combined_conf,
        sign_score=combined_conf,
        semantic_conf=combined_conf,
    )


class TestDomainPipelineTransaction:

    def setup_method(self):
        reset_all()

    def teardown_method(self):
        reset_all()

    def test_process_batch_with_transaction(self):
        pipeline = DomainPipeline()
        repo = get_graph_repository()
        before_count = repo.count_relations()

        edges = [
            RawEdge(
                raw_edge_id="e1",
                head_entity_id="E_gold",
                tail_entity_id="E_inflation",
                relation_type="correlates_with",
                polarity_guess=Polarity.POSITIVE,
                fragment_id="f1",
                fragment_text="Gold often moves with inflation expectations over time.",
            ),
            RawEdge(
                raw_edge_id="e2",
                head_entity_id="E_rates",
                tail_entity_id="E_growth",
                relation_type="pressures",
                polarity_guess=Polarity.NEGATIVE,
                fragment_id="f1",
                fragment_text="Higher policy rates continue to pressure growth stocks.",
            ),
        ]

        resolved = [
            ResolvedEntity(
                entity_id="E_gold",
                canonical_id="Gold",
                canonical_name="Gold",
                canonical_type="AssetGroup",
                surface_text="gold",
                fragment_id="f1",
                resolution_mode=ResolutionMode.STATIC_DOMAIN,
            ),
            ResolvedEntity(
                entity_id="E_inflation",
                canonical_id="CPI",
                canonical_name="CPI",
                canonical_type="MacroIndicator",
                surface_text="inflation",
                fragment_id="f1",
                resolution_mode=ResolutionMode.STATIC_DOMAIN,
            ),
            ResolvedEntity(
                entity_id="E_rates",
                canonical_id="Policy_Rate",
                canonical_name="policy rate",
                canonical_type="MacroIndicator",
                surface_text="policy rate",
                fragment_id="f1",
                resolution_mode=ResolutionMode.STATIC_DOMAIN,
            ),
            ResolvedEntity(
                entity_id="E_growth",
                canonical_id="Growth_Stocks",
                canonical_name="growth stocks",
                canonical_type="AssetGroup",
                surface_text="growth stocks",
                fragment_id="f1",
                resolution_mode=ResolutionMode.STATIC_DOMAIN,
            ),
        ]

        validation_results = {
            "e1": create_validation_result("e1"),
            "e2": create_validation_result("e2"),
        }

        results = pipeline.process_batch(edges, validation_results, resolved)

        assert len(results) == 2
        assert pipeline._stats["domain_accepted"] == 2
        assert repo.count_relations() == before_count + 1

        rel1 = repo.get_relation("Gold", "domain:correlates_with", "CPI")
        assert rel1 is not None

        rel2 = repo.get_relation("Policy_Rate", "domain:pressures", "Growth_Stocks")
        assert rel2 is not None
        assert rel2["props"]["evidence_count"] >= 1

    def test_rollback_on_error(self):
        """A failed batch should not leave partial writes behind."""
        pipeline = DomainPipeline()
        repo = get_graph_repository()

        baseline_count = repo.count_relations()

        pipeline.process_batch(
            [
                RawEdge(
                    raw_edge_id="init",
                    head_entity_id="E_A",
                    tail_entity_id="E_B",
                    relation_type="supports",
                    polarity_guess=Polarity.POSITIVE,
                    fragment_id="f0",
                    fragment_text="Higher oil prices usually support the energy sector.",
                )
            ],
            {"init": create_validation_result("init")},
            [
                ResolvedEntity(
                    entity_id="E_A",
                    canonical_id="Crude_Oil",
                    canonical_name="crude oil",
                    canonical_type="Commodity",
                    surface_text="oil",
                    fragment_id="f0",
                    resolution_mode=ResolutionMode.STATIC_DOMAIN,
                ),
                ResolvedEntity(
                    entity_id="E_B",
                    canonical_id="Energy_Sector",
                    canonical_name="energy sector",
                    canonical_type="Sector",
                    surface_text="energy sector",
                    fragment_id="f0",
                    resolution_mode=ResolutionMode.STATIC_DOMAIN,
                ),
            ],
        )

        assert repo.count_relations() == baseline_count

        original_update = pipeline.dynamic_update.update
        existing_airlines_relation = repo.get_relation("Crude_Oil", "domain:pressures", "Airlines_Sector")
        existing_airlines_evidence = existing_airlines_relation["props"]["evidence_count"]

        def failing_update(*args, **kwargs):
            raise ValueError("Simulated DB Error")

        pipeline.dynamic_update.update = failing_update

        try:
            pipeline.process_batch(
                [
                    RawEdge(
                        raw_edge_id="e1",
                        head_entity_id="E_C",
                        tail_entity_id="E_D",
                        relation_type="pressures",
                        polarity_guess=Polarity.NEGATIVE,
                        fragment_id="f1",
                        fragment_text="Higher oil prices pressure airlines.",
                    )
                ],
                {"e1": create_validation_result("e1")},
                [
                    ResolvedEntity(
                        entity_id="E_C",
                        canonical_id="Crude_Oil",
                        canonical_name="crude oil",
                        canonical_type="Commodity",
                        surface_text="oil",
                        fragment_id="f1",
                        resolution_mode=ResolutionMode.STATIC_DOMAIN,
                    ),
                    ResolvedEntity(
                        entity_id="E_D",
                        canonical_id="Airlines_Sector",
                        canonical_name="airlines sector",
                        canonical_type="Sector",
                        surface_text="airlines",
                        fragment_id="f1",
                        resolution_mode=ResolutionMode.STATIC_DOMAIN,
                    ),
                ],
            )
        except ValueError:
            pass
        finally:
            pipeline.dynamic_update.update = original_update

        assert repo.count_relations() == baseline_count
        assert repo.get_relation("Crude_Oil", "domain:supports", "Energy_Sector") is not None
        rolled_back_airlines_relation = repo.get_relation("Crude_Oil", "domain:pressures", "Airlines_Sector")
        assert rolled_back_airlines_relation is not None
        assert rolled_back_airlines_relation["props"]["evidence_count"] == existing_airlines_evidence

    def test_ambiguous_high_impact_candidate_routes_to_council(self):
        pipeline = DomainPipeline()
        repo = get_graph_repository()
        before_relation = repo.get_relation("Policy_Rate", "domain:pressures", "Growth_Stocks")

        results = pipeline.process_batch(
            [
                RawEdge(
                    raw_edge_id="e3",
                    head_entity_id="E_rates",
                    tail_entity_id="E_growth",
                    relation_type="pressures",
                    polarity_guess=Polarity.NEGATIVE,
                    fragment_id="f3",
                    fragment_text="Higher policy rates pressure growth stocks.",
                )
            ],
            {"e3": create_validation_result("e3", combined_conf=0.68)},
            [
                ResolvedEntity(
                    entity_id="E_rates",
                    canonical_id="Policy_Rate",
                    canonical_name="policy rate",
                    canonical_type="MacroIndicator",
                    surface_text="policy rate",
                    fragment_id="f3",
                    resolution_mode=ResolutionMode.STATIC_DOMAIN,
                ),
                ResolvedEntity(
                    entity_id="E_growth",
                    canonical_id="Growth_Stocks",
                    canonical_name="growth stocks",
                    canonical_type="AssetGroup",
                    surface_text="growth stocks",
                    fragment_id="f3",
                    resolution_mode=ResolutionMode.STATIC_DOMAIN,
                ),
            ],
        )

        assert len(results) == 1
        assert results[0].final_destination == "council"
        assert pipeline.get_stats()["council_pending"] == 1
        after_relation = repo.get_relation("Policy_Rate", "domain:pressures", "Growth_Stocks")
        assert after_relation is not None
        assert after_relation["props"]["evidence_count"] == before_relation["props"]["evidence_count"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
