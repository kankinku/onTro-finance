"""DomainPipeline Transaction Test"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.bootstrap import reset_all, get_graph_repository
from src.domain.pipeline import DomainPipeline
from src.shared.models import RawEdge, ResolvedEntity
from src.validation.models import ValidationResult, ValidationDestination

class TestDomainPipelineTransaction:
    
    def setup_method(self):
        reset_all()
    
    def teardown_method(self):
        reset_all()
    
    def test_process_batch_with_transaction(self):
        pipeline = DomainPipeline()
        repo = get_graph_repository()
        
        from src.shared.models import ResolutionMode
        
        edges = [
            RawEdge(
                raw_edge_id="e1", 
                head_entity_id="E_gold", target_entity_id="E_inflation",
                tail_entity_id="E_inflation", # tail_entity_id가 맞음
                relation_type="Corr",
                fragment_id="f1",
                fragment_text="Gold rises with inflation"
            ),
            RawEdge(
                raw_edge_id="e2", 
                head_entity_id="E_rates", 
                tail_entity_id="E_inflation",
                relation_type="Corr",
                fragment_id="f1",
                fragment_text="Rates fall when inflation rises"
            ),
        ]
        
        # Mock Resolved Entities
        resolved = [
            ResolvedEntity(entity_id="E_gold", canonical_id="gold", canonical_name="Gold", canonical_type="Asset", surface_text="Gold", fragment_id="f1", resolution_mode=ResolutionMode.STATIC_DOMAIN),
            ResolvedEntity(entity_id="E_inflation", canonical_id="inflation", canonical_name="Inflation", canonical_type="Concept", surface_text="Inflation", fragment_id="f1", resolution_mode=ResolutionMode.STATIC_DOMAIN),
            ResolvedEntity(entity_id="E_rates", canonical_id="rates", canonical_name="Interest Rates", canonical_type="Indicator", surface_text="Rates", fragment_id="f1", resolution_mode=ResolutionMode.STATIC_DOMAIN),
        ]
        
        # Mock Validation Results
        validation_results = {
            "e1": ValidationResult(
                raw_edge_id="e1", validation_passed=True, destination=ValidationDestination.DOMAIN_CANDIDATE,
                head_entity="gold", tail_entity="inflation", relation_type="Corr", is_domain_relation=True
            ),
            "e2": ValidationResult(
                raw_edge_id="e2", validation_passed=True, destination=ValidationDestination.DOMAIN_CANDIDATE,
                head_entity="rates", tail_entity="inflation", relation_type="Corr", is_domain_relation=True
            ),
        }
        
        # Run Batch
        results = pipeline.process_batch(edges, validation_results, resolved)
        
        assert len(results) == 2
        assert pipeline._stats["domain_accepted"] == 2
        
        # Check Repository
        assert repo.count_relations() == 2
        
        rel1 = repo.get_relation("gold", "Corr", "inflation")
        assert rel1 is not None
        
        rel2 = repo.get_relation("rates", "Corr", "inflation")
        assert rel2 is not None

    def test_rollback_on_error(self):
        """배치 처리 중 에러 발생 시 롤백 확인"""
        pipeline = DomainPipeline()
        repo = get_graph_repository()
        from src.shared.models import ResolutionMode
        
        # 1. 정상적으로 하나 추가해둠
        pipeline.process_batch([
            RawEdge(
                raw_edge_id="init",
                head_entity_id="E_A", tail_entity_id="E_B",
                relation_type="R", fragment_id="f0"
            )
        ], {
            "init": ValidationResult(
                raw_edge_id="init", validation_passed=True, destination=ValidationDestination.DOMAIN_CANDIDATE,
                head_entity="A", tail_entity="B", relation_type="R", is_domain_relation=True
            )
        }, [
            ResolvedEntity(entity_id="E_A", canonical_id="A", canonical_name="A", canonical_type="T", surface_text="A", fragment_id="f0", resolution_mode=ResolutionMode.NEW_ENTITY),
            ResolvedEntity(entity_id="E_B", canonical_id="B", canonical_name="B", canonical_type="T", surface_text="B", fragment_id="f0", resolution_mode=ResolutionMode.NEW_ENTITY),
        ])
        
        assert repo.count_relations() == 1
        
        # 2. 배치 중 에러 발생 시뮬레이션
        original_update = pipeline.dynamic_update.update
        def failing_update(*args, **kwargs):
            raise ValueError("Simulated DB Error")
        pipeline.dynamic_update.update = failing_update
        
        try:
            pipeline.process_batch([
                RawEdge(
                    raw_edge_id="e1",
                    head_entity_id="E_C", tail_entity_id="E_D",
                    relation_type="R", fragment_id="f1"
                )
            ], {
                "e1": ValidationResult(
                    raw_edge_id="e1", validation_passed=True, destination=ValidationDestination.DOMAIN_CANDIDATE,
                    head_entity="C", tail_entity="D", relation_type="R", is_domain_relation=True
                )
            }, [
                ResolvedEntity(entity_id="E_C", canonical_id="C", canonical_name="C", canonical_type="T", surface_text="C", fragment_id="f1", resolution_mode=ResolutionMode.NEW_ENTITY),
                ResolvedEntity(entity_id="E_D", canonical_id="D", canonical_name="D", canonical_type="T", surface_text="D", fragment_id="f1", resolution_mode=ResolutionMode.NEW_ENTITY),
            ])
        except ValueError:
            pass

        
        # 3. 롤백 확인 -> C->D, R 관계가 없어야 함
        # 그리고 처음에 넣었던 A->B는 남아있어야 함 (별도 트랜잭션이었으므로)
        assert repo.count_relations() == 1
        assert repo.get_relation("A", "R", "B") is not None
        assert repo.get_relation("C", "R", "D") is None

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
