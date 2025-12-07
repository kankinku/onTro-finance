"""
Market Routes
시장 데이터 관련 API 엔드포인트
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from src.api.market_data import MarketDataProvider
from src.core.logger import logger

router = APIRouter()

# 전역 Market Data Provider
_market_provider: Optional[MarketDataProvider] = None


def get_market_provider() -> MarketDataProvider:
    """Market Provider 싱글톤 접근"""
    global _market_provider
    if _market_provider is None:
        _market_provider = MarketDataProvider()
    return _market_provider


def initialize_market_provider():
    """서버 시작 시 Market Provider 초기화"""
    provider = get_market_provider()
    try:
        provider.initialize_data()
    except Exception as e:
        logger.error(f"[Market] Initialization failed: {e}")


@router.get("/dashboard")
async def get_market_dashboard():
    """
    대시보드용 시장 요약 데이터 반환
    
    Returns:
        { "insight": "...", "cards": [...] }
    """
    try:
        provider = get_market_provider()
        return provider.get_dashboard_summary()
    except Exception as e:
        logger.error(f"[Market] Dashboard fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{source}/{ticker}")
async def get_market_history(source: str, ticker: str):
    """
    특정 지표의 히스토리 데이터 반환
    
    Args:
        source: 데이터 소스 (fred, yfinance)
        ticker: 티커 심볼
    """
    try:
        provider = get_market_provider()
        data = provider.get_metric_history(source, ticker)
        return {"source": source, "ticker": ticker, "history": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze/{source}/{ticker}")
async def analyze_market_metric(
    source: str, 
    ticker: str, 
    title: str = Query(..., description="Metric title for analysis")
):
    """
    특정 지표에 대한 LLM 심층 분석 트리거
    """
    try:
        provider = get_market_provider()
        analysis = provider.analyze_metric_detail(source, ticker, title)
        return {"ticker": ticker, "analysis": analysis}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/index/{index_key}")
async def get_market_index(index_key: str):
    """
    주요 시장 지수 데이터 조회 (NASDAQ, SNP500, GOLD, BTC)
    """
    from src.api.market_indices import market_indices
    
    if index_key not in market_indices:
        raise HTTPException(
            status_code=404, 
            detail=f"Index '{index_key}' not found. Available: {list(market_indices.keys())}"
        )
    
    return market_indices[index_key]
