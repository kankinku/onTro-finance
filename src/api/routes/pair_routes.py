"""
Pair Trading Routes
페어 트레이딩 분석 관련 API 엔드포인트
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from src.api.pair_trading import PairTradingAnalyzer
from src.core.logger import logger

router = APIRouter()

# 전역 Pair Trading Analyzer
_pair_analyzer: Optional[PairTradingAnalyzer] = None


def get_pair_analyzer() -> PairTradingAnalyzer:
    """Pair Analyzer 싱글톤 접근"""
    global _pair_analyzer
    if _pair_analyzer is None:
        _pair_analyzer = PairTradingAnalyzer()
        _pair_analyzer.load_price_data()
    return _pair_analyzer


@router.get("/universe")
async def get_pair_universe():
    """유니버스 정보 반환 (섹터별 종목 리스트)"""
    try:
        analyzer = get_pair_analyzer()
        sectors = analyzer.universe.groupby("sector")["ticker"].apply(list).to_dict()
        return {
            "sectors": sectors,
            "total_stocks": len(analyzer.universe)
        }
    except Exception as e:
        logger.error(f"[Pair] Universe fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def get_pair_list(
    sector: Optional[str] = Query(None, description="Filter by sector"),
    corr_threshold: float = Query(0.7, description="Minimum correlation threshold"),
    window: int = Query(120, description="Rolling window for correlation")
):
    """상관계수 기반 종목쌍 리스트 반환"""
    try:
        analyzer = get_pair_analyzer()
        
        if sector:
            pairs = analyzer.get_sector_pairs(sector, corr_threshold, window)
        else:
            pairs = analyzer.get_all_pairs(corr_threshold, window)
        
        enriched = analyzer.enrich_pairs(pairs)
        return {"pairs": enriched, "count": len(enriched)}
        
    except Exception as e:
        logger.error(f"[Pair] List fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scatter")
async def get_scatter_data(
    corr_threshold: float = Query(0.7, description="Minimum correlation threshold")
):
    """PE Spread vs Momentum Spread 산점도 데이터"""
    try:
        analyzer = get_pair_analyzer()
        pairs = analyzer.get_all_pairs(corr_threshold)
        scatter = analyzer.get_scatter_data(pairs)
        return {"data": scatter}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/spread")
async def get_spread_timeseries(
    ticker1: str = Query(..., description="First ticker"),
    ticker2: str = Query(..., description="Second ticker"),
    window: int = Query(63, description="Rolling window for spread calculation")
):
    """특정 쌍의 가격 스프레드 타임시리즈"""
    try:
        analyzer = get_pair_analyzer()
        spread_data = analyzer.get_spread_timeseries(ticker1, ticker2, window)
        return spread_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/backtest")
async def run_pair_backtest(
    ticker1: str = Query(..., description="First ticker"),
    ticker2: str = Query(..., description="Second ticker"),
    entry_z: float = Query(1.0, description="Entry z-score threshold"),
    exit_z: float = Query(0.0, description="Exit z-score threshold"),
    lookback: int = Query(63, description="Lookback period for z-score"),
    max_holding_days: int = Query(60, description="Maximum holding period")
):
    """페어 트레이딩 백테스트 실행"""
    try:
        analyzer = get_pair_analyzer()
        result = analyzer.backtest_pair(
            ticker1, ticker2, 
            entry_z, exit_z, 
            lookback, max_holding_days
        )
        return result
    except Exception as e:
        logger.error(f"[Pair] Backtest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/momentum")
async def get_momentum_overview():
    """전체 종목의 모멘텀 데이터 반환"""
    try:
        analyzer = get_pair_analyzer()
        momentum_data = analyzer.get_momentum_data()
        return {"data": momentum_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fundamental-backtest")
async def run_fundamental_backtest(
    entry_days_ago: int = Query(42, description="Entry date (trading days ago)"),
    exit_days_ago: int = Query(0, description="Exit date (trading days ago, 0 = today)"),
    metric: str = Query("pe", description="Fundamental metric: pe, pb, or combined")
):
    """펀더멘털 기반 롱숏 백테스트"""
    try:
        analyzer = get_pair_analyzer()
        result = analyzer.backtest_fundamental_longshort(
            entry_days_ago=entry_days_ago,
            exit_days_ago=exit_days_ago,
            fundamental_metric=metric
        )
        return result
    except Exception as e:
        logger.error(f"[Pair] Fundamental backtest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/risk")
async def get_pair_risk_metrics(
    ticker1: str = Query(..., description="First ticker"),
    ticker2: str = Query(..., description="Second ticker")
):
    """종목쌍의 리스크 메트릭 조회"""
    try:
        analyzer = get_pair_analyzer()
        risk = analyzer.calc_risk_metrics(ticker1, ticker2)
        return risk
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
