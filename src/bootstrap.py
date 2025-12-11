"""
Bootstrap / Dependency Injection
설정 기반으로 구현체를 주입하는 팩토리.
"""
import os
import yaml
import logging
from typing import Optional
from pathlib import Path

from src.storage.graph_repository import GraphRepository
from src.storage.inmemory_repository import InMemoryGraphRepository
from src.storage.transaction_manager import KGTransactionManager

logger = logging.getLogger(__name__)


def load_config(config_path: Optional[str] = None) -> dict:
    """설정 파일 로드"""
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config" / "infrastructure.yaml"
    
    if not os.path.exists(config_path):
        logger.warning(f"Config not found: {config_path}, using defaults")
        return {"storage": {"backend": "inmemory"}, "llm": {"backend": "ollama"}}
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    # 환경변수 치환
    config = _substitute_env_vars(config)
    return config


def _substitute_env_vars(config: dict) -> dict:
    """${VAR} 형태의 환경변수 치환"""
    if isinstance(config, dict):
        return {k: _substitute_env_vars(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [_substitute_env_vars(v) for v in config]
    elif isinstance(config, str) and config.startswith("${") and config.endswith("}"):
        var_name = config[2:-1]
        return os.environ.get(var_name, "")
    return config


# ==============================================================================
# GraphRepository
# ==============================================================================

def build_graph_repository(config: Optional[dict] = None) -> GraphRepository:
    """GraphRepository 인스턴스 생성"""
    if config is None:
        config = load_config()
    
    storage_config = config.get("storage", {})
    backend = storage_config.get("backend", "inmemory")
    
    if backend == "inmemory":
        logger.info("Using InMemory GraphRepository")
        return InMemoryGraphRepository()
    
    elif backend == "neo4j":
        from src.storage.neo4j_repository import Neo4jGraphRepository
        neo4j_conf = storage_config.get("neo4j", {})
        logger.info(f"Using Neo4j GraphRepository: {neo4j_conf.get('uri')}")
        return Neo4jGraphRepository(
            uri=neo4j_conf.get("uri", "bolt://localhost:7687"),
            user=neo4j_conf.get("user", "neo4j"),
            password=neo4j_conf.get("password", ""),
            database=neo4j_conf.get("database", "neo4j"),
        )
    
    else:
        raise ValueError(f"Unknown storage backend: {backend}")


_graph_repo: Optional[GraphRepository] = None
_tx_manager: Optional[KGTransactionManager] = None


def get_graph_repository() -> GraphRepository:
    """싱글톤 GraphRepository 반환"""
    global _graph_repo
    if _graph_repo is None:
        _graph_repo = build_graph_repository()
    return _graph_repo


def get_transaction_manager() -> KGTransactionManager:
    """싱글톤 TransactionManager 반환"""
    global _tx_manager
    if _tx_manager is None:
        _tx_manager = KGTransactionManager(get_graph_repository())
    return _tx_manager


# ==============================================================================
# LLM Gateway
# ==============================================================================

from src.llm.llm_client import LLMClient
from src.llm.gateway import LLMGateway


def build_llm_client(config: Optional[dict] = None) -> LLMClient:
    """LLMClient 인스턴스 생성"""
    if config is None:
        config = load_config()
    
    llm_config = config.get("llm", {})
    backend = llm_config.get("backend", "ollama")
    
    if backend == "ollama":
        from src.llm.ollama_adapter import OllamaLLMClient
        ollama_conf = llm_config.get("ollama", {})
        logger.info(f"Using Ollama LLM: {ollama_conf.get('model', 'llama3.2')}")
        return OllamaLLMClient(
            base_url=ollama_conf.get("base_url", "http://localhost:11434"),
            model=ollama_conf.get("model", "llama3.2"),
            timeout=ollama_conf.get("timeout", 30.0),
        )
    
    elif backend == "mock":
        from src.llm.ollama_adapter import MockLLMClient
        logger.info("Using Mock LLM")
        return MockLLMClient()
    
    else:
        raise ValueError(f"Unknown LLM backend: {backend}")


def build_llm_gateway(config: Optional[dict] = None) -> LLMGateway:
    """LLMGateway 인스턴스 생성"""
    primary = build_llm_client(config)
    return LLMGateway(
        primary_client=primary,
        max_retries=3,
        enable_cache=True,
    )


_llm_gateway: Optional[LLMGateway] = None


def get_llm_gateway() -> LLMGateway:
    """싱글톤 LLMGateway 반환"""
    global _llm_gateway
    if _llm_gateway is None:
        _llm_gateway = build_llm_gateway()
    return _llm_gateway


# ==============================================================================
# KG Adapters
# ==============================================================================

# TYPE_CHECKING을 위해 문자열 forward reference 사용하거나 
# 런타임에만 import 하도록 함.
# from src.domain.kg_adapter import DomainKGAdapter
# from src.personal.kg_adapter import PersonalKGAdapter

_domain_adapter = None
_personal_adapter = None


def get_domain_kg_adapter():
    """싱글톤 Domain KG Adapter 반환"""
    global _domain_adapter
    if _domain_adapter is None:
        from src.domain.kg_adapter import DomainKGAdapter
        _domain_adapter = DomainKGAdapter(
            repository=get_graph_repository(),
            tx_manager=get_transaction_manager(),
        )
        # Load initial domain data (Bootstrap)
        _domain_adapter.load_domain_data()
    return _domain_adapter


def get_personal_kg_adapter():
    """싱글톤 Personal KG Adapter 반환"""
    global _personal_adapter
    if _personal_adapter is None:
        from src.personal.kg_adapter import PersonalKGAdapter
        _personal_adapter = PersonalKGAdapter(
            repository=get_graph_repository(),
            tx_manager=get_transaction_manager(),
        )
    return _personal_adapter



# ==============================================================================
# Reset (테스트용)
# ==============================================================================

def reset_all() -> None:
    """모든 싱글톤 리셋"""
    global _graph_repo, _tx_manager, _llm_gateway, _domain_adapter, _personal_adapter
    _graph_repo = None
    _tx_manager = None
    _llm_gateway = None
    _domain_adapter = None
    _personal_adapter = None


def reset_graph_repository() -> None:
    """테스트용 리셋 (하위호환)"""
    reset_all()

