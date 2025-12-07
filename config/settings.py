"""
Application Settings
모든 환경 변수 기반 설정을 중앙 관리
"""
import os
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """
    Application Configuration
    환경 변수(.env)에서 값을 읽어오며, 기본값 제공
    """
    # ========== App ==========
    APP_NAME: str = "OntoFin System"
    ENV: str = "dev"
    DEBUG: bool = True
    
    # ========== Paths (Project Root 기준) ==========
    PROJECT_ROOT: Path = Path(__file__).parent.parent
    DATA_DIR: Path = PROJECT_ROOT / "data"
    CACHE_DIR: Path = DATA_DIR / "cache"
    GRAPH_DIR: Path = DATA_DIR / "graphs"
    
    # ========== LLM (Ollama) ==========
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2"
    OLLAMA_TIMEOUT: int = 30
    
    # ========== Database (Neo4j) ==========
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"
    USE_MOCK_DB: bool = True  # True면 Neo4j 대신 NetworkX 사용
    
    # ========== Persistence ==========
    PERSISTENCE_FILE: str = "ontofin_graph.json"
    
    @property
    def persistence_path(self) -> Path:
        return self.GRAPH_DIR / self.PERSISTENCE_FILE
    
    # ========== External APIs ==========
    FRED_API_KEY: str = ""
    
    # ========== Cache Settings ==========
    CACHE_MAX_AGE_HOURS: int = 6
    MARKET_CACHE_FILE: str = "market_cache.json"
    
    @property
    def market_cache_path(self) -> Path:
        return self.CACHE_DIR / self.MARKET_CACHE_FILE
    
    class Config:
        env_file = ".env"
        extra = "ignore"


# Singleton Instance
settings = Settings()
