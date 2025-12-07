# API Routes Package
"""
API 라우트 정의
각 라우트는 서비스 레이어만 호출하며, 비즈니스 로직을 직접 포함하지 않음
"""
from fastapi import APIRouter

# 메인 라우터 생성
api_router = APIRouter()

# 하위 라우터 import 및 등록
from src.api.routes.graph_routes import router as graph_router
from src.api.routes.market_routes import router as market_router
from src.api.routes.scenario_routes import router as scenario_router
from src.api.routes.pair_routes import router as pair_router

api_router.include_router(graph_router, prefix="/graph", tags=["Graph"])
api_router.include_router(market_router, prefix="/market", tags=["Market Data"])
api_router.include_router(scenario_router, prefix="/scenario", tags=["Scenario"])
api_router.include_router(pair_router, prefix="/pair", tags=["Pair Trading"])

__all__ = ["api_router"]
