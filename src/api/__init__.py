"""
DEPRECATED: 이 파일은 하위 호환성을 위해 유지됩니다.
새 코드는 src.api.routes 패키지를 사용하세요.

from src.api.routes import api_router
"""
# Backward compatibility
from src.api.routes import api_router
from src.api.market_data import MarketDataProvider

# 기존 코드와의 호환성을 위한 전역 변수
global_market = MarketDataProvider()

# 기존 모듈을 import하던 코드를 위한 re-export
__all__ = ["api_router", "global_market"]
