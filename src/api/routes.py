from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from typing import List, Optional
from src.schemas.base_models import ScenarioInput, InferredOutcome, Fragment
from src.api.market_data import MarketDataProvider
from src.api.pair_trading import pair_analyzer, DEFAULT_UNIVERSE
from src.pipeline.m1_analyzer import InputAnalyzer
from src.pipeline.m2_entity_resolver import EntityResolver
from src.pipeline.m3_relation import RelationConstructor
from src.reasoning.simulator import ScenarioSimulator
from src.core.knowledge_graph import KnowledgeGraph
from src.core.database import db
from src.core.logger import logger
from networkx.readwrite import json_graph

api_router = APIRouter()

# Initialize Global Graph (will load from disk on validity)
global_kg = KnowledgeGraph()
# Initialize Global Market Data Provider
global_market = MarketDataProvider()

@api_router.get("/graph")
async def get_graph_data():
    """
    Returns the entire Knowledge Graph structure for visualization.
    Format: { "nodes": [...], "links": [...] }
    """
    logger.info("[API] /graph request received.")
    data = json_graph.node_link_data(global_kg.graph)
    return data

@api_router.get("/market/dashboard")
async def get_market_dashboard():
    """
    Returns summary cards for top-level dashboard (TGA, Reserves, etc.)
    """
    # Use global Singleton
    return global_market.get_dashboard_summary()

@api_router.get("/market/history")
async def get_market_history(source: str, ticker: str):
    """
    Returns historical data for a specific ticker provided by MarketDataProvider.
    """
    history = global_market.get_metric_history(source, ticker)
    if not history:
        return []
    return history

@api_router.get("/market/analyze-metric")
async def analyze_market_metric(source: str, ticker: str, title: str):
    """
    Triggers an on-demand LLM analysis for a specific metric.
    """
    logger.info(f"[API] Analyzing metric: {title} ({ticker})")
    report = global_market.analyze_metric_detail(source, ticker, title)
    return {"report": report}

@api_router.post("/learn", response_model=List[Fragment])
async def learn_scenario(input_data: ScenarioInput, background_tasks: BackgroundTasks):
    logger.info(f"[API] /learn request received. Length: {len(input_data.text)}")
    
    # 1. M1 Analysis (Ollama)
    analyzer = InputAnalyzer()
    fragments = analyzer.analyze(input_data.text)
    
    if not fragments:
        logger.warning("[API] No fragments extracted.")
        return []

    # 2. M2 Resolution
    resolver = EntityResolver()
    resolution_map = resolver.resolve(fragments)
    
    # 3. M3 Relation Construction
    constructor = RelationConstructor()
    relations = constructor.construct(fragments, resolution_map)
    
    # 4. Save
    background_tasks.add_task(_save_to_knowledge_base, resolution_map, relations)
    
    # 5. [New] Auto-Discover Data Sources (If keywords found)
    background_tasks.add_task(_auto_discover_data_sources, input_data.text)
    
    return fragments

@api_router.post("/infer", response_model=InferredOutcome)
async def infer_scenario(target_term_id: str):
    logger.info(f"[API] /infer request for {target_term_id}")
    
    simulator = ScenarioSimulator(global_kg)
    result = simulator.simulate([target_term_id])
    
    return result

def _save_to_knowledge_base(resolution_map, relations):
    from src.schemas.base_models import Term
    
    try:
        for surface, res in resolution_map.items():
            term_obj = Term(term_id=res.entity_id, label=surface, aliases=[surface])
            # db.merge_term(term_obj) # Disabled (Mock)
            global_kg.add_term(term_obj)

        for rel in relations:
            # db.create_relation(rel) # Disabled (Mock)
            global_kg.add_relation(rel)
            
        logger.info(f"[Worker] Saved {len(relations)} relations to Graph.")
    except Exception as e:
        logger.error(f"[Worker] Failed to save: {e}")

def _auto_discover_data_sources(text: str):
    """
    Analyzes input text for potential economic indicators or assets.
    If found, tries to find them in FRED and register them.
    """
    logger.info("[Auto-Discovery] Scanning text for data sources...")
    import requests
    from src.core.config import settings

    # 1. Ask LLM to extract potential assets
    prompt = f"""
    Extract any financial asset names or economic indicators from the text.
    Return ONLY a JSON list of strings (English preferred for search).
    If none, return [].
    
    Text: "{text}"
    
    Example Output: ["Bitcoin", "Unemployment Rate", "Gold"]
    """
    
    try:
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": settings.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.0}
            },
            timeout=10
        )
        if resp.status_code == 200:
            import json
            res_json = resp.json().get("response", "[]")
            keywords = json.loads(res_json)
            
            if isinstance(keywords, dict) and "assets" in keywords: # Handle potential { "assets": [...] } format
                 keywords = keywords["assets"]
            
            logger.info(f"[Auto-Discovery] Extracted keywords: {keywords}")
            
            for kw in keywords:
                # Try to register
                if isinstance(kw, str) and len(kw) > 2:
                    global_market.search_and_register_ticker(kw)
        else:
            logger.warning("Ollama failed for discovery.")
            
    except Exception as e:
        logger.error(f"[Auto-Discovery] Error: {e}")


# ==================== Pair Trading API ====================

@api_router.get("/pairs/universe")
async def get_pair_universe():
    """유니버스 정보 반환 (섹터별 종목 리스트)"""
    logger.info("[API] /pairs/universe request received.")
    sectors = {}
    for _, row in DEFAULT_UNIVERSE.iterrows():
        sector = row["sector"]
        if sector not in sectors:
            sectors[sector] = []
        sectors[sector].append({
            "ticker": row["ticker"],
            "name": row["name"]
        })
    return {"sectors": sectors, "total_tickers": len(DEFAULT_UNIVERSE)}


@api_router.get("/pairs/list")
async def get_pair_list(
    sector: Optional[str] = Query(None, description="Filter by sector"),
    corr_threshold: float = Query(0.7, description="Minimum correlation threshold"),
    window: int = Query(120, description="Rolling window for correlation")
):
    """상관계수 기반 종목쌍 리스트 반환"""
    logger.info(f"[API] /pairs/list request - sector={sector}, corr={corr_threshold}")
    
    try:
        if sector:
            pairs = pair_analyzer.get_sector_pairs(sector, corr_threshold, window)
        else:
            pairs = pair_analyzer.get_all_pairs(corr_threshold, window)
        
        enriched = pair_analyzer.enrich_pairs(pairs)
        return {"pairs": enriched, "count": len(enriched)}
    except Exception as e:
        logger.error(f"[API] Pairs list error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/pairs/scatter")
async def get_scatter_data(
    corr_threshold: float = Query(0.7, description="Minimum correlation threshold")
):
    """PE Spread vs Momentum Spread 산점도 데이터"""
    logger.info("[API] /pairs/scatter request received.")
    
    try:
        pairs = pair_analyzer.get_all_pairs(corr_threshold)
        enriched = pair_analyzer.enrich_pairs(pairs)
        scatter = pair_analyzer.get_scatter_data(enriched)
        return {"data": scatter}
    except Exception as e:
        logger.error(f"[API] Scatter data error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/pairs/spread")
async def get_spread_timeseries(
    ticker1: str = Query(..., description="First ticker"),
    ticker2: str = Query(..., description="Second ticker"),
    window: int = Query(63, description="Rolling window for spread calculation")
):
    """특정 쌍의 모멘텀 스프레드 타임시리즈"""
    logger.info(f"[API] /pairs/spread request - {ticker1}/{ticker2}")
    
    try:
        result = pair_analyzer.get_spread_timeseries(ticker1, ticker2, window)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Spread timeseries error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/pairs/backtest")
async def run_pair_backtest(
    ticker1: str = Query(..., description="First ticker"),
    ticker2: str = Query(..., description="Second ticker"),
    entry_z: float = Query(1.0, description="Entry z-score threshold"),
    exit_z: float = Query(0.0, description="Exit z-score threshold"),
    lookback: int = Query(63, description="Lookback period for z-score"),
    max_holding_days: int = Query(60, description="Maximum holding period")
):
    """페어 트레이딩 백테스트 실행"""
    logger.info(f"[API] /pairs/backtest request - {ticker1}/{ticker2}")
    
    try:
        result = pair_analyzer.backtest_pair(
            t1=ticker1,
            t2=ticker2,
            entry_z=entry_z,
            exit_z=exit_z,
            lookback=lookback,
            max_holding_days=max_holding_days
        )
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Backtest error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/pairs/momentum")
async def get_momentum_overview():
    """전체 종목의 모멘텀 데이터 반환"""
    logger.info("[API] /pairs/momentum request received.")
    
    try:
        momentum = pair_analyzer.get_momentum_data()
        return {"data": momentum}
    except Exception as e:
        logger.error(f"[API] Momentum data error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/pairs/backtest-fundamental")
async def run_fundamental_backtest(
    ticker1: str = Query(..., description="First ticker"),
    ticker2: str = Query(..., description="Second ticker"),
    entry_days_ago: int = Query(42, description="Entry date (trading days ago, e.g., 42 = 2 months)"),
    exit_days_ago: int = Query(0, description="Exit date (trading days ago, 0 = today)"),
    metric: str = Query("pe", description="Fundamental metric: pe, pb, or combined")
):
    """
    펀더멘털 기반 롱숏 백테스트
    - 펀더멘털이 좋은 종목(낮은 P/E, P/B) → Long
    - 펀더멘털이 나쁜 종목(높은 P/E, P/B) → Short
    """
    logger.info(f"[API] /pairs/backtest-fundamental request - {ticker1}/{ticker2}, days_ago={entry_days_ago}")
    
    try:
        result = pair_analyzer.backtest_fundamental_longshort(
            t1=ticker1,
            t2=ticker2,
            entry_days_ago=entry_days_ago,
            exit_days_ago=exit_days_ago,
            fundamental_metric=metric
        )
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Fundamental backtest error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/pairs/risk")
async def get_pair_risk_metrics(
    ticker1: str = Query(..., description="First ticker"),
    ticker2: str = Query(..., description="Second ticker")
):
    """
    종목쌍의 리스크 메트릭 조회
    - 변동성 (개별 및 스프레드)
    - Half-Life (평균 회귀 속도)
    - 베타 비율 (헤지 비율)
    - 상관계수
    """
    logger.info(f"[API] /pairs/risk request - {ticker1}/{ticker2}")
    
    try:
        result = pair_analyzer.calc_risk_metrics(ticker1, ticker2)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Risk metrics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Market Indices API ====================
from src.api.market_indices import market_indices

@api_router.get("/market/index/{index_key}")
async def get_market_index(index_key: str):
    """
    주요 시장 지수 데이터 조회 (NASDAQ, SNP500, GOLD, BTC)
    """
    data = market_indices.get_index_data(index_key.upper())
    if "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])
    return data

