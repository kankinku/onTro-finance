"""Infrastructure Layer 테스트"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.storage.inmemory_repository import InMemoryGraphRepository
from src.storage.transaction_manager import KGTransactionManager, TransactionState
from src.llm.llm_client import LLMRequest
from src.llm.ollama_adapter import MockLLMClient
from src.llm.gateway import LLMGateway, LLMGatewayError
from src.shared.error_framework import (
    OntologyError, StorageError, LLMServiceError, ErrorCategory, ErrorSeverity,
    ErrorRegistry, get_error_registry,
)


class TestInMemoryRepository:
    def test_upsert_entity(self):
        repo = InMemoryGraphRepository()
        repo.upsert_entity("E1", ["Entity"], {"name": "Test"})
        
        entity = repo.get_entity("E1")
        assert entity is not None
        assert entity["props"]["name"] == "Test"
    
    def test_upsert_relation(self):
        repo = InMemoryGraphRepository()
        repo.upsert_entity("E1", ["Entity"], {})
        repo.upsert_entity("E2", ["Entity"], {})
        repo.upsert_relation("E1", "LINKS_TO", "E2", {"weight": 0.5})
        
        rel = repo.get_relation("E1", "LINKS_TO", "E2")
        assert rel is not None
        assert rel["props"]["weight"] == 0.5
    
    def test_get_neighbors(self):
        repo = InMemoryGraphRepository()
        repo.upsert_entity("A", ["Node"], {})
        repo.upsert_entity("B", ["Node"], {})
        repo.upsert_entity("C", ["Node"], {})
        repo.upsert_relation("A", "TO", "B", {})
        repo.upsert_relation("A", "TO", "C", {})
        
        neighbors = repo.get_neighbors("A", direction="out")
        assert len(neighbors) == 2
    
    def test_delete_entity(self):
        repo = InMemoryGraphRepository()
        repo.upsert_entity("E1", ["Entity"], {})
        assert repo.count_entities() == 1
        
        repo.delete_entity("E1")
        assert repo.count_entities() == 0


class TestTransactionManager:
    def test_commit(self):
        repo = InMemoryGraphRepository()
        tx_mgr = KGTransactionManager(repo)
        
        with tx_mgr.transaction() as tx:
            tx_mgr.create_entity(tx, "E1", ["Entity"], {"name": "Test"})
        
        assert repo.count_entities() == 1
        assert tx.state == TransactionState.COMMITTED
    
    def test_rollback_on_error(self):
        repo = InMemoryGraphRepository()
        tx_mgr = KGTransactionManager(repo)
        
        try:
            with tx_mgr.transaction() as tx:
                tx_mgr.create_entity(tx, "E1", ["Entity"], {"name": "Test"})
                raise ValueError("Simulated error")
        except ValueError:
            pass
        
        # 롤백되어야 함
        assert repo.count_entities() == 0
        assert tx.state == TransactionState.ROLLED_BACK


class TestMockLLMClient:
    def test_generate(self):
        client = MockLLMClient("Hello World")
        request = LLMRequest(prompt="Test")
        
        response = client.generate(request)
        assert response.content == "Hello World"
        assert client.call_count == 1
    
    def test_set_responses(self):
        client = MockLLMClient()
        client.set_responses(["First", "Second"])
        
        r1 = client.generate(LLMRequest(prompt="1"))
        r2 = client.generate(LLMRequest(prompt="2"))
        
        assert r1.content == "First"
        assert r2.content == "Second"


class TestLLMGateway:
    def test_generate(self):
        client = MockLLMClient("Gateway response")
        gateway = LLMGateway(client)
        
        response = gateway.generate("Test prompt")
        assert response.content == "Gateway response"
        assert gateway.get_stats()["primary_success"] == 1
    
    def test_fallback(self):
        primary = MockLLMClient("Primary")
        fallback = MockLLMClient("Fallback")
        
        # Primary가 실패하도록 설정
        def failing_generate(request):
            raise ConnectionError("Connection failed")
        primary.generate = failing_generate
        
        gateway = LLMGateway(primary, fallback_client=fallback, max_retries=1)
        response = gateway.generate("Test")
        
        assert response.content == "Fallback"
        assert gateway.get_stats()["fallback_success"] == 1


class TestErrorFramework:
    def test_storage_error(self):
        error = StorageError(
            "Connection failed",
            operation="connect",
            entity_id="E1",
        )
        
        assert error.category == ErrorCategory.STORAGE
        assert error.retryable == True
        
        d = error.to_dict()
        assert d["category"] == "storage"
    
    def test_error_registry(self):
        registry = ErrorRegistry()
        
        error = StorageError("Test error", operation="test")
        registry.record(error)
        
        assert len(registry.get_recent(10)) == 1
        assert registry.get_stats()["total"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
