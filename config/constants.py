"""
Application Constants
변경되지 않는 상수값들을 중앙 관리
코드 내 하드코딩 방지
"""
from dataclasses import dataclass
from pathlib import Path
from config.settings import settings


@dataclass(frozen=True)
class CachePaths:
    """캐시 파일 경로 상수"""
    MARKET_CACHE: Path = settings.CACHE_DIR / "market_cache.json"
    CUSTOM_MAPPING: Path = settings.CACHE_DIR / "custom_market_mapping.json"
    ALL_PAIRS: Path = settings.CACHE_DIR / "all_pairs.json"
    FUNDAMENTALS: Path = settings.CACHE_DIR / "fundamentals.json"
    MOMENTUM: Path = settings.CACHE_DIR / "momentum.json"
    PRICE_DATA: Path = settings.CACHE_DIR / "price_data.json"


@dataclass(frozen=True)
class APIEndpoints:
    """외부 API 엔드포인트"""
    OLLAMA_GENERATE: str = "/api/generate"
    OLLAMA_TAGS: str = "/api/tags"


@dataclass(frozen=True)
class DefaultParams:
    """기본 파라미터 값"""
    # Pair Trading
    CORRELATION_THRESHOLD: float = 0.7
    ROLLING_WINDOW: int = 120
    MOMENTUM_WINDOW: int = 126
    BACKTEST_LOOKBACK: int = 63
    MAX_HOLDING_DAYS: int = 60
    ENTRY_Z_SCORE: float = 1.5
    EXIT_Z_SCORE: float = 0.0
    
    # Simulation
    MAX_PROPAGATION_DEPTH: int = 3
    DECAY_FACTOR: float = 0.9
    MIN_IMPACT_THRESHOLD: float = 0.1
    
    # Market Data
    DEFAULT_START_DATE: str = "2020-01-01"
    CACHE_EXPIRY_HOURS: int = 6


@dataclass(frozen=True)
class LogMessages:
    """표준화된 로그 메시지 포맷"""
    # System
    STARTUP = "[System] {} started on port {}"
    SHUTDOWN = "[System] {} shutting down"
    
    # Pipeline
    M1_INIT = "[M1] Initialized with Ollama model: {} at {}"
    M1_SUCCESS = "[M1] Successfully extracted {} fragments"
    M1_FALLBACK = "[M1] Using Mock Fallback"
    
    # Graph
    GRAPH_SAVED = "[Graph] Saved {} nodes to {}"
    GRAPH_LOADED = "[Graph] Loaded {} nodes from {}"
    
    # Market Data
    MARKET_INIT = "[Market] Initializing data sync..."
    MARKET_CACHE_HIT = "[Market] Cache hit for {}"
    MARKET_FETCH = "[Market] Fetching {} from API"
