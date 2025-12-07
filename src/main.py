"""
OntoFin System - FastAPI Entry Point
온톨로지 기반 금융 시나리오 학습/추론 시스템
"""
import sys
import os
from pathlib import Path
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# 프로젝트 루트를 sys.path에 추가 (모듈 import를 위해)
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings
from src.core.logger import logger
from src.services.llm_service import llm_service
from src.api.routes import api_router
from src.api.routes.market_routes import initialize_market_provider


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application Lifespan Handler
    - Startup: LLM 체크, Market Data 초기화
    - Shutdown: 정리 작업
    """
    # === Startup ===
    logger.info(f"[Startup] Initializing {settings.APP_NAME}...")
    
    # 1. LLM 모델 체크
    llm_service.check_and_pull_model()
    
    # 2. Market Data 동기화
    try:
        initialize_market_provider()
        logger.info("[Startup] Market data initialized.")
    except Exception as e:
        logger.error(f"[Startup] Market Data Init Failed: {e}")
    
    yield
    
    # === Shutdown ===
    logger.info("[Shutdown] Application shutting down...")


def create_app() -> FastAPI:
    """
    FastAPI 앱 팩토리
    모든 라우터와 미들웨어 설정
    """
    app = FastAPI(
        title=settings.APP_NAME,
        description="Ontology-based Financial Scenario Reasoning System",
        version="5.0.0",  # 구조 리팩토링 버전
        lifespan=lifespan
    )
    
    # CORS 미들웨어
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API 라우터 등록
    app.include_router(api_router, prefix="/api/v1")
    
    # Static 파일 서빙
    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # === Page Routes ===
    @app.get("/")
    async def root():
        """메인 대시보드"""
        return FileResponse(static_dir / "index.html")

    @app.get("/graph_view")
    async def graph_view():
        """Knowledge Graph 시각화"""
        return FileResponse(static_dir / "graph.html")

    @app.get("/detail_view")
    async def detail_view():
        """상세 분석 뷰"""
        return FileResponse(static_dir / "detail.html")

    @app.get("/pair_trading")
    async def pair_trading_view():
        """페어 트레이딩 분석"""
        return FileResponse(static_dir / "pair_trading.html")

    @app.get("/scenario")
    async def scenario_view():
        """시나리오 분석"""
        return FileResponse(static_dir / "scenario.html")
        
    return app


# 앱 인스턴스 생성
app = create_app()


if __name__ == "__main__":
    logger.info(f">>> Starting {settings.APP_NAME} on port 8000...")
    uvicorn.run(app, host="127.0.0.1", port=8000)
