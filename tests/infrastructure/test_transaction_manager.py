"""Transaction manager regression tests for rollback safety."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.storage.inmemory_repository import InMemoryGraphRepository
from src.storage.transaction_manager import KGTransactionManager


class TestKGTransactionManager:
    def test_rollback_preserves_existing_records_when_upserted_via_create_methods(self):
        repo = InMemoryGraphRepository()
        tx_manager = KGTransactionManager(repo)

        repo.upsert_entity("Policy_Rate", ["DomainEntity"], {"name": "policy rate"})
        repo.upsert_entity("Growth_Stocks", ["DomainEntity"], {"name": "growth stocks"})
        repo.upsert_relation(
            "Policy_Rate",
            "domain:pressures",
            "Growth_Stocks",
            {"relation_id": "baseline", "evidence_count": 1},
        )

        with pytest.raises(RuntimeError):
            with tx_manager.transaction() as tx:
                tx_manager.create_entity(
                    tx,
                    "Policy_Rate",
                    ["DomainEntity"],
                    {"name": "policy rate", "updated": True},
                )
                tx_manager.create_relation(
                    tx,
                    "Policy_Rate",
                    "domain:pressures",
                    "Growth_Stocks",
                    {"relation_id": "baseline", "evidence_count": 5},
                )
                raise RuntimeError("force rollback")

        entity = repo.get_entity("Policy_Rate")
        relation = repo.get_relation("Policy_Rate", "domain:pressures", "Growth_Stocks")

        assert entity is not None
        assert entity["props"].get("updated") is None
        assert relation is not None
        assert relation["props"]["evidence_count"] == 1

    def test_rollback_removes_new_records(self):
        repo = InMemoryGraphRepository()
        tx_manager = KGTransactionManager(repo)

        with pytest.raises(RuntimeError):
            with tx_manager.transaction() as tx:
                tx_manager.create_entity(
                    tx,
                    "Gold",
                    ["DomainEntity"],
                    {"name": "gold"},
                )
                tx_manager.create_entity(
                    tx,
                    "CPI",
                    ["DomainEntity"],
                    {"name": "inflation"},
                )
                tx_manager.create_relation(
                    tx,
                    "Gold",
                    "domain:correlates_with",
                    "CPI",
                    {"relation_id": "new_rel", "evidence_count": 1},
                )
                raise RuntimeError("force rollback")

        assert repo.get_entity("Gold") is None
        assert repo.get_entity("CPI") is None
        assert repo.get_relation("Gold", "domain:correlates_with", "CPI") is None

    def test_rollback_restores_relations_deleted_with_entity(self):
        repo = InMemoryGraphRepository()
        tx_manager = KGTransactionManager(repo)

        repo.upsert_entity("Policy_Rate", ["DomainEntity"], {"name": "policy rate"})
        repo.upsert_entity("Growth_Stocks", ["DomainEntity"], {"name": "growth stocks"})
        repo.upsert_entity("Dollar", ["DomainEntity"], {"name": "dollar"})
        repo.upsert_relation(
            "Policy_Rate",
            "domain:pressures",
            "Growth_Stocks",
            {"relation_id": "rel_1", "evidence_count": 1},
        )
        repo.upsert_relation(
            "Dollar",
            "domain:supports",
            "Policy_Rate",
            {"relation_id": "rel_2", "evidence_count": 2},
        )

        with pytest.raises(RuntimeError):
            with tx_manager.transaction() as tx:
                tx_manager.delete_entity(tx, "Policy_Rate")
                raise RuntimeError("force rollback")

        assert repo.get_entity("Policy_Rate") is not None
        assert repo.get_relation("Policy_Rate", "domain:pressures", "Growth_Stocks") is not None
        assert repo.get_relation("Dollar", "domain:supports", "Policy_Rate") is not None
