import sys
import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from src.core.config import settings
from src.core.logger import logger
from src.core.llm_setup import check_and_pull_ollama_model

# 1. Project Root Path 설정
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from contextlib import asynccontextmanager
from src.api.routes import api_router, global_market

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Check LLM
    check_and_pull_ollama_model()
    # Startup: Sync Market Data (Incremental update)
    if hasattr(global_market, 'initialize_data'):
        # Done synchronously here to ensure data is ready before serving requests,
        # or could be background task if too slow. 
        # Given "init check" requirement, synchronous is safer for prototype.
        try:
             global_market.initialize_data()
        except Exception as e:
             logger.error(f"Market Data Init Failed: {e}")
    yield
    # Shutdown: Clean up if needed

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        description="Ontology-based Financial Scenario Reasoning System (Ollama Integrated)",
        version="4.1.0",
        lifespan=lifespan
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api/v1")
    
    # Mount Static Files
    # main.py is in 'src/', so static is in 'src/static' (same dir)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    static_dir = os.path.join(current_dir, "static")
    
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    async def root():
        return FileResponse(os.path.join(static_dir, "index.html"))

    @app.get("/graph_view")
    async def graph_view():
        return FileResponse(os.path.join(static_dir, "graph.html"))

    @app.get("/detail_view")
    async def detail_view():
        return FileResponse(os.path.join(static_dir, "detail.html"))

    @app.get("/pair_trading")
    async def pair_trading_view():
        return FileResponse(os.path.join(static_dir, "pair_trading.html"))

    @app.get("/scenario")
    async def scenario_view():
        return FileResponse(os.path.join(static_dir, "scenario.html"))
        
    return app

app = create_app()

if __name__ == "__main__":
    logger.info(f">>> Starting {settings.APP_NAME} on port 8000...")
    uvicorn.run(app, host="127.0.0.1", port=8000)
