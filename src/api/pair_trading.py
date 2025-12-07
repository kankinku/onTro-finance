"""
Pair Trading Analysis Module
섹터 내 상관계수 기반 종목쌍 분석, 펀더멘털/모멘텀 스프레드, 백테스트
"""

import pandas as pd
import numpy as np
import yfinance as yf
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import json
import os
from src.core.logger import logger

# ==================== 유니버스 정의 ====================

DEFAULT_UNIVERSE = pd.DataFrame([
    # Semiconductor
    {"ticker": "NVDA", "sector": "Semiconductor", "name": "NVIDIA"},
    {"ticker": "AMD", "sector": "Semiconductor", "name": "AMD"},
    {"ticker": "AVGO", "sector": "Semiconductor", "name": "Broadcom"},
    {"ticker": "QCOM", "sector": "Semiconductor", "name": "Qualcomm"},
    {"ticker": "KLAC", "sector": "Semiconductor", "name": "KLA Corp"},
    {"ticker": "LRCX", "sector": "Semiconductor", "name": "Lam Research"},
    {"ticker": "AMAT", "sector": "Semiconductor", "name": "Applied Materials"},
    {"ticker": "INTC", "sector": "Semiconductor", "name": "Intel"},
    {"ticker": "MU", "sector": "Semiconductor", "name": "Micron"},
    {"ticker": "TXN", "sector": "Semiconductor", "name": "Texas Instruments"},
    # Cloud/SaaS
    {"ticker": "SNOW", "sector": "Cloud", "name": "Snowflake"},
    {"ticker": "DDOG", "sector": "Cloud", "name": "Datadog"},
    {"ticker": "MDB", "sector": "Cloud", "name": "MongoDB"},
    {"ticker": "NOW", "sector": "Cloud", "name": "ServiceNow"},
    {"ticker": "CRM", "sector": "Cloud", "name": "Salesforce"},
    {"ticker": "WDAY", "sector": "Cloud", "name": "Workday"},
    {"ticker": "ZS", "sector": "Cloud", "name": "Zscaler"},
    {"ticker": "NET", "sector": "Cloud", "name": "Cloudflare"},
    # Big Tech
    {"ticker": "AAPL", "sector": "BigTech", "name": "Apple"},
    {"ticker": "MSFT", "sector": "BigTech", "name": "Microsoft"},
    {"ticker": "GOOGL", "sector": "BigTech", "name": "Alphabet"},
    {"ticker": "META", "sector": "BigTech", "name": "Meta"},
    {"ticker": "AMZN", "sector": "BigTech", "name": "Amazon"},
    # E-Commerce & Consumer
    {"ticker": "BABA", "sector": "ECommerce", "name": "Alibaba"},
    {"ticker": "JD", "sector": "ECommerce", "name": "JD.com"},
    {"ticker": "PDD", "sector": "ECommerce", "name": "PDD Holdings"},
    {"ticker": "EBAY", "sector": "ECommerce", "name": "eBay"},
    {"ticker": "ETSY", "sector": "ECommerce", "name": "Etsy"},
    # Fintech
    {"ticker": "V", "sector": "Fintech", "name": "Visa"},
    {"ticker": "MA", "sector": "Fintech", "name": "Mastercard"},
    {"ticker": "PYPL", "sector": "Fintech", "name": "PayPal"},
    {"ticker": "AFRM", "sector": "Fintech", "name": "Affirm"},
    {"ticker": "COIN", "sector": "Fintech", "name": "Coinbase"},
])


class PairTradingAnalyzer:
    """페어 트레이딩 분석 클래스"""
    
    CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "pair_cache")
    
    def __init__(self, universe: pd.DataFrame = None):
        self.universe = universe if universe is not None else DEFAULT_UNIVERSE
        self.price_data: Optional[pd.DataFrame] = None
        self.returns: Optional[pd.DataFrame] = None
        self.fundamentals: Optional[pd.DataFrame] = None
        self._ensure_cache_dir()
        
    def _ensure_cache_dir(self):
        if not os.path.exists(self.CACHE_DIR):
            os.makedirs(self.CACHE_DIR)
    
    def _get_cache_path(self, name: str) -> str:
        return os.path.join(self.CACHE_DIR, f"{name}.json")
    
    def _load_cache(self, name: str, max_age_hours: int = 6) -> Optional[Dict]:
        """캐시 로드 (max_age_hours 이내의 데이터만)"""
        path = self._get_cache_path(name)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                cached_time = datetime.fromisoformat(data.get('cached_at', '2000-01-01'))
                if datetime.now() - cached_time < timedelta(hours=max_age_hours):
                    return data.get('payload')
            except Exception as e:
                logger.warning(f"Cache load error: {e}")
        return None
    
    def _save_cache(self, name: str, payload: Any):
        """캐시 저장"""
        path = self._get_cache_path(name)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({
                    'cached_at': datetime.now().isoformat(),
                    'payload': payload
                }, f, ensure_ascii=False, default=str)
        except Exception as e:
            logger.warning(f"Cache save error: {e}")
    
    def load_price_data(self, start_date: str = "2020-01-01") -> pd.DataFrame:
        """가격 데이터 로드 (yfinance)"""
        tickers = self.universe["ticker"].unique().tolist()
        logger.info(f"[PairTrading] Loading price data for {len(tickers)} tickers...")
        
        try:
            # auto_adjust=True가 기본값이므로 Close 사용
            data = yf.download(tickers, start=start_date, progress=False, auto_adjust=True, threads=True)
            
            logger.info(f"[PairTrading] Downloaded data shape: {data.shape}, columns: {list(data.columns)[:5]}")
            
            # 데이터 형식 확인 및 처리
            if data.empty:
                logger.warning("[PairTrading] Downloaded data is empty!")
                self.price_data = pd.DataFrame()
                self.returns = pd.DataFrame()
                return self.price_data
            
            # MultiIndex 처리 (여러 티커일 때)
            if isinstance(data.columns, pd.MultiIndex):
                # (Price Type, Ticker) 형태
                if "Close" in data.columns.get_level_values(0):
                    self.price_data = data["Close"]
                elif "Adj Close" in data.columns.get_level_values(0):
                    self.price_data = data["Adj Close"]
                else:
                    # 첫번째 레벨 사용
                    first_level = data.columns.get_level_values(0)[0]
                    self.price_data = data[first_level]
                    logger.info(f"[PairTrading] Using first level: {first_level}")
            else:
                # 단일 티커
                self.price_data = data[["Close"]] if "Close" in data.columns else data
            
            # 결측치 처리
            self.price_data = self.price_data.dropna(how="all")
            self.price_data = self.price_data.ffill()  # Forward fill
            
            if len(self.price_data) > 0:
                self.returns = np.log(self.price_data / self.price_data.shift(1)).dropna()
            else:
                self.returns = pd.DataFrame()
            
            logger.info(f"[PairTrading] Loaded {len(self.price_data)} days of data, {len(self.price_data.columns)} tickers")
            return self.price_data
        except Exception as e:
            logger.error(f"[PairTrading] Price data load error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
    def get_sector_pairs(
        self, 
        sector: str, 
        corr_threshold: float = 0.7, 
        window: int = 120
    ) -> List[Dict]:
        """섹터 내 상관계수 기반 종목쌍 추출"""
        if self.returns is None:
            self.load_price_data()
        
        sector_tickers = self.universe[self.universe["sector"] == sector]["ticker"].tolist()
        available_tickers = [t for t in sector_tickers if t in self.returns.columns]
        
        if len(available_tickers) < 2:
            return []
        
        sector_rets = self.returns[available_tickers].dropna()
        pairs = []
        
        for i, t1 in enumerate(available_tickers):
            for t2 in available_tickers[i+1:]:
                try:
                    rolling_corr = sector_rets[t1].rolling(window).corr(sector_rets[t2])
                    mean_corr = rolling_corr.dropna().mean()
                    
                    if pd.notna(mean_corr) and mean_corr >= corr_threshold:
                        name1 = self.universe[self.universe["ticker"] == t1]["name"].values[0]
                        name2 = self.universe[self.universe["ticker"] == t2]["name"].values[0]
                        pairs.append({
                            "sector": sector,
                            "ticker1": t1,
                            "ticker2": t2,
                            "name1": name1,
                            "name2": name2,
                            "mean_corr": round(float(mean_corr), 4)
                        })
                except Exception as e:
                    logger.warning(f"Correlation calc error for {t1}-{t2}: {e}")
        
        return sorted(pairs, key=lambda x: x["mean_corr"], reverse=True)
    
    def get_all_pairs(self, corr_threshold: float = 0.7, window: int = 120) -> List[Dict]:
        """전체 섹터에서 상관계수 기준 종목쌍 추출"""
        cache = self._load_cache("all_pairs")
        if cache:
            logger.info("[PairTrading] Using cached pairs data")
            return cache
        
        all_pairs = []
        for sector in self.universe["sector"].unique():
            pairs = self.get_sector_pairs(sector, corr_threshold, window)
            all_pairs.extend(pairs)
        
        self._save_cache("all_pairs", all_pairs)
        return all_pairs
    
    def get_fundamentals(self, tickers: List[str] = None) -> pd.DataFrame:
        """펀더멘털 데이터 수집"""
        if tickers is None:
            tickers = self.universe["ticker"].unique().tolist()
        
        cache = self._load_cache("fundamentals", max_age_hours=24)
        if cache:
            logger.info("[PairTrading] Using cached fundamentals")
            return pd.DataFrame(cache)
        
        logger.info(f"[PairTrading] Fetching fundamentals for {len(tickers)} tickers...")
        fund_list = []
        
        for ticker in tickers:
            try:
                tk = yf.Ticker(ticker)
                info = tk.info
                fund_list.append({
                    "ticker": ticker,
                    "pe": info.get("trailingPE"),
                    "pb": info.get("priceToBook"),
                    "market_cap": info.get("marketCap"),
                    "beta": info.get("beta"),
                    "forward_pe": info.get("forwardPE"),
                    "ps": info.get("priceToSalesTrailing12Months"),
                    "dividend_yield": info.get("dividendYield"),
                    "roe": info.get("returnOnEquity"),
                })
            except Exception as e:
                logger.warning(f"Fundamentals error for {ticker}: {e}")
                fund_list.append({"ticker": ticker})
        
        self.fundamentals = pd.DataFrame(fund_list)
        self._save_cache("fundamentals", fund_list)
        return self.fundamentals
    
    def calc_momentum(self, window: int = 126) -> pd.DataFrame:
        """모멘텀(누적 수익률) 계산"""
        if self.returns is None:
            self.load_price_data()
        
        cum_log_ret = self.returns.iloc[-window:].sum()
        momentum = np.exp(cum_log_ret) - 1
        return momentum
    
    def get_momentum_data(self) -> Dict[str, Dict]:
        """1M/3M/6M 모멘텀 데이터"""
        cache = self._load_cache("momentum", max_age_hours=6)
        if cache:
            return cache
        
        mom_1m = self.calc_momentum(21)
        mom_3m = self.calc_momentum(63)
        mom_6m = self.calc_momentum(126)
        
        result = {}
        for ticker in self.universe["ticker"].unique():
            if ticker in mom_1m.index:
                result[ticker] = {
                    "mom_1m": round(float(mom_1m.get(ticker, 0)), 4),
                    "mom_3m": round(float(mom_3m.get(ticker, 0)), 4),
                    "mom_6m": round(float(mom_6m.get(ticker, 0)), 4),
                }
        
        self._save_cache("momentum", result)
        return result
    
    def enrich_pairs(self, pairs: List[Dict]) -> List[Dict]:
        """종목쌍에 펀더멘털 + 가격 스프레드 + 모멘텀 스프레드 추가"""
        fund_df = self.get_fundamentals()
        fund = fund_df.set_index("ticker")
        momentum = self.get_momentum_data()
        
        # 현재 가격 스프레드 계산을 위해 가격 데이터 확보
        if self.price_data is None:
            self.load_price_data()
        
        enriched = []
        for pair in pairs:
            t1, t2 = pair["ticker1"], pair["ticker2"]
            
            try:
                f1 = fund.loc[t1] if t1 in fund.index else {}
                f2 = fund.loc[t2] if t2 in fund.index else {}
                m1 = momentum.get(t1, {})
                m2 = momentum.get(t2, {})
                
                pe1, pe2 = f1.get("pe"), f2.get("pe")
                pb1, pb2 = f1.get("pb"), f2.get("pb")
                
                # 가격 스프레드 (Price Ratio) 계산
                price_spread_info = self._calc_current_price_spread(t1, t2)
                
                enriched.append({
                    **pair,
                    # 현재 가격 정보
                    "price1": price_spread_info.get("price1"),
                    "price2": price_spread_info.get("price2"),
                    "price_ratio": price_spread_info.get("price_ratio"),
                    "price_spread_zscore": price_spread_info.get("z_score"),
                    "spread_signal": price_spread_info.get("signal"),
                    # Fundamentals
                    "pe1": round(float(pe1), 2) if pd.notna(pe1) else None,
                    "pe2": round(float(pe2), 2) if pd.notna(pe2) else None,
                    "pb1": round(float(pb1), 2) if pd.notna(pb1) else None,
                    "pb2": round(float(pb2), 2) if pd.notna(pb2) else None,
                    "pe_spread": round(float(pe1 - pe2), 2) if pd.notna(pe1) and pd.notna(pe2) else None,
                    "pb_spread": round(float(pb1 - pb2), 2) if pd.notna(pb1) and pd.notna(pb2) else None,
                    # Momentum
                    "mom1_1": m1.get("mom_1m"),
                    "mom1_2": m2.get("mom_1m"),
                    "mom3_1": m1.get("mom_3m"),
                    "mom3_2": m2.get("mom_3m"),
                    "mom6_1": m1.get("mom_6m"),
                    "mom6_2": m2.get("mom_6m"),
                    "mom1_spread": round(m1.get("mom_1m", 0) - m2.get("mom_1m", 0), 4),
                    "mom3_spread": round(m1.get("mom_3m", 0) - m2.get("mom_3m", 0), 4),
                    "mom6_spread": round(m1.get("mom_6m", 0) - m2.get("mom_6m", 0), 4),
                })
            except Exception as e:
                logger.warning(f"Enrichment error for {t1}-{t2}: {e}")
                enriched.append(pair)
        
        return enriched
    
    def _calc_current_price_spread(self, t1: str, t2: str, lookback: int = 63) -> Dict:
        """현재 가격 스프레드(로그 비율)와 Z-Score 계산"""
        try:
            if t1 not in self.price_data.columns or t2 not in self.price_data.columns:
                return {}
            
            prices = self.price_data[[t1, t2]].dropna()
            if len(prices) < lookback:
                return {}
            
            # 로그 가격 비율 = log(P1/P2)
            log_ratio = np.log(prices[t1] / prices[t2])
            
            # 롤링 평균/표준편차로 Z-Score 계산
            roll_mean = log_ratio.rolling(lookback).mean()
            roll_std = log_ratio.rolling(lookback).std()
            z_score = (log_ratio - roll_mean) / roll_std
            
            current_z = float(z_score.iloc[-1])
            current_price1 = float(prices[t1].iloc[-1])
            current_price2 = float(prices[t2].iloc[-1])
            current_ratio = float(prices[t1].iloc[-1] / prices[t2].iloc[-1])
            
            # 시그널 결정
            if current_z > 1.5:
                signal = "Short Spread"  # t1 Short, t2 Long
            elif current_z < -1.5:
                signal = "Long Spread"   # t1 Long, t2 Short
            elif current_z > 1.0:
                signal = "Weak Short"
            elif current_z < -1.0:
                signal = "Weak Long"
            else:
                signal = "Neutral"
            
            return {
                "price1": round(current_price1, 2),
                "price2": round(current_price2, 2),
                "price_ratio": round(current_ratio, 4),
                "z_score": round(current_z, 2),
                "signal": signal
            }
        except Exception as e:
            logger.warning(f"Price spread calc error for {t1}-{t2}: {e}")
            return {}
    
    def get_spread_timeseries(self, t1: str, t2: str, window: int = 63) -> Dict:
        """
        특정 쌍의 가격 스프레드(Price Ratio) 타임시리즈
        롱숏 전략을 위한 가격 비율 기반 스프레드와 Z-Score
        """
        if self.price_data is None:
            self.load_price_data()
        
        if t1 not in self.price_data.columns or t2 not in self.price_data.columns:
            return {"error": "Ticker not found"}
        
        prices = self.price_data[[t1, t2]].dropna()
        
        # 가격 비율 스프레드: log(P1/P2)
        log_ratio = np.log(prices[t1] / prices[t2])
        
        # 롤링 평균/표준편차
        roll_mean = log_ratio.rolling(window).mean()
        roll_std = log_ratio.rolling(window).std()
        z_score = (log_ratio - roll_mean) / roll_std
        z_score = z_score.dropna()
        
        # 최근 252일 (1년)만 반환
        recent = z_score.tail(252)
        recent_ratio = log_ratio.tail(252)
        
        # 현재 가격
        current_price1 = float(prices[t1].iloc[-1])
        current_price2 = float(prices[t2].iloc[-1])
        
        return {
            "ticker1": t1,
            "ticker2": t2,
            "window": window,
            "type": "price_ratio",
            "dates": [d.strftime("%Y-%m-%d") for d in recent.index],
            "spread": [round(float(v), 4) for v in recent_ratio.values],  # 로그 비율
            "z_score_series": [round(float(v), 4) for v in recent.values],  # Z-Score 시리즈
            "current_price1": round(current_price1, 2),
            "current_price2": round(current_price2, 2),
            "current_ratio": round(float(prices[t1].iloc[-1] / prices[t2].iloc[-1]), 4),
            "current_z": round(float(recent.iloc[-1]), 2) if len(recent) > 0 else 0,
            "mean": round(float(log_ratio.mean()), 4),
            "std": round(float(log_ratio.std()), 4),
            "upper_band": round(float(roll_mean.iloc[-1] + roll_std.iloc[-1]), 4) if len(roll_mean) > 0 else 0,
            "lower_band": round(float(roll_mean.iloc[-1] - roll_std.iloc[-1]), 4) if len(roll_mean) > 0 else 0
        }
    
    def backtest_pair(
        self,
        t1: str,
        t2: str,
        entry_z: float = 1.5,
        exit_z: float = 0.0,
        lookback: int = 63,
        max_holding_days: int = 60
    ) -> Dict:
        """
        가격 스프레드 기반 페어 트레이딩 백테스트
        - 가격 비율 log(P1/P2)의 Z-Score 기반 진입/청산
        - Long Spread: t1 Long + t2 Short (스프레드가 평균 대비 너무 낮을 때)
        - Short Spread: t1 Short + t2 Long (스프레드가 평균 대비 너무 높을 때)
        """
        if self.price_data is None:
            self.load_price_data()
        
        if t1 not in self.price_data.columns or t2 not in self.price_data.columns:
            return {"error": "Ticker not found"}
        
        prices = self.price_data[[t1, t2]].dropna()
        returns = self.returns[[t1, t2]].dropna()
        
        # 가격 비율 스프레드: log(P1/P2)
        log_ratio = np.log(prices[t1] / prices[t2])
        
        # 롤링 평균/표준편차로 Z-Score 계산
        roll_mean = log_ratio.rolling(lookback).mean()
        roll_std = log_ratio.rolling(lookback).std()
        zscore = (log_ratio - roll_mean) / roll_std
        
        position = 0  # 0: flat, 1: long spread (long t1, short t2), -1: short spread
        holding_days = 0
        equity = 0.0
        equity_curve = []
        trades = []
        trade_entry = None
        entry_prices = None
        
        for date in prices.index:
            if pd.isna(zscore.loc[date]):
                equity_curve.append({"date": date.strftime("%Y-%m-%d"), "equity": round(equity, 4), "z": None})
                continue
            
            z = zscore.loc[date]
            p1 = prices.loc[date, t1]
            p2 = prices.loc[date, t2]
            
            # 일간 수익률 (로그 수익률)
            r1 = returns.loc[date, t1] if date in returns.index else 0
            r2 = returns.loc[date, t2] if date in returns.index else 0
            
            # Entry
            if position == 0:
                if z > entry_z:
                    # 스프레드가 너무 높음 -> 수렴 예상 -> Short Spread (t1 short, t2 long)
                    position = -1
                    holding_days = 0
                    entry_prices = (p1, p2)
                    trade_entry = {
                        "date": date.strftime("%Y-%m-%d"),
                        "type": "Short Spread",
                        "action": f"Short {t1} @ ${p1:.2f}, Long {t2} @ ${p2:.2f}",
                        "z": round(float(z), 2),
                        "entry_ratio": round(float(p1/p2), 4)
                    }
                elif z < -entry_z:
                    # 스프레드가 너무 낮음 -> 확대 예상 -> Long Spread (t1 long, t2 short)
                    position = 1
                    holding_days = 0
                    entry_prices = (p1, p2)
                    trade_entry = {
                        "date": date.strftime("%Y-%m-%d"),
                        "type": "Long Spread",
                        "action": f"Long {t1} @ ${p1:.2f}, Short {t2} @ ${p2:.2f}",
                        "z": round(float(z), 2),
                        "entry_ratio": round(float(p1/p2), 4)
                    }
            else:
                holding_days += 1
                # Exit 조건
                should_exit = False
                exit_reason = ""
                
                if position == 1 and z >= exit_z:  # Long spread, z가 0 이상으로 회귀
                    should_exit = True
                    exit_reason = "Mean Reversion"
                elif position == -1 and z <= exit_z:  # Short spread, z가 0 이하로 회귀
                    should_exit = True
                    exit_reason = "Mean Reversion"
                elif holding_days >= max_holding_days:
                    should_exit = True
                    exit_reason = "Max Holding"
                
                if should_exit and trade_entry:
                    # 트레이드 PnL 계산 (가격 기준)
                    if entry_prices:
                        if position == 1:  # Long spread: long t1, short t2
                            trade_pnl = (p1 - entry_prices[0]) / entry_prices[0] - (p2 - entry_prices[1]) / entry_prices[1]
                        else:  # Short spread: short t1, long t2
                            trade_pnl = -(p1 - entry_prices[0]) / entry_prices[0] + (p2 - entry_prices[1]) / entry_prices[1]
                    else:
                        trade_pnl = 0
                    
                    trades.append({
                        **trade_entry,
                        "exit_date": date.strftime("%Y-%m-%d"),
                        "exit_z": round(float(z), 2),
                        "exit_ratio": round(float(p1/p2), 4),
                        "holding_days": holding_days,
                        "exit_reason": exit_reason,
                        "pnl_pct": round(trade_pnl * 100, 2)
                    })
                    position = 0
                    holding_days = 0
                    trade_entry = None
                    entry_prices = None
            
            # Daily PnL (로그 수익률 기반)
            if position == 1:  # Long spread
                equity += r1 - r2
            elif position == -1:  # Short spread
                equity += -r1 + r2
            
            equity_curve.append({
                "date": date.strftime("%Y-%m-%d"),
                "equity": round(equity, 4),
                "z": round(float(z), 2)
            })
        
        # Performance metrics
        equity_series = pd.Series([e["equity"] for e in equity_curve])
        
        if len(equity_series) > 0 and equity_series.diff().std() > 0:
            final_return = float(equity_series.iloc[-1])
            max_dd = float((equity_series - equity_series.cummax()).min())
            sharpe = float(equity_series.diff().mean() / equity_series.diff().std() * np.sqrt(252))
            
            # Win/Loss 계산
            winning_trades = [t for t in trades if t.get("pnl_pct", 0) > 0]
            win_rate = len(winning_trades) / max(len(trades), 1) * 100
        else:
            final_return = 0
            max_dd = 0
            sharpe = 0
            win_rate = 0
        
        return {
            "ticker1": t1,
            "ticker2": t2,
            "strategy": "Price Ratio Mean Reversion",
            "params": {
                "entry_z": entry_z,
                "exit_z": exit_z,
                "lookback": lookback,
                "max_holding_days": max_holding_days
            },
            "performance": {
                "total_return": round(final_return * 100, 2),  # %
                "max_drawdown": round(max_dd * 100, 2),  # %
                "sharpe_ratio": round(sharpe, 2),
                "num_trades": len(trades),
                "win_rate": round(win_rate, 1),
                "avg_holding_days": round(sum(t.get("holding_days", 0) for t in trades) / max(len(trades), 1), 1)
            },
            "trades": trades[-10:],  # 최근 10개 트레이드만
            "equity_curve": equity_curve[-252:]  # 최근 1년만
        }
    
    def get_scatter_data(self, pairs: List[Dict]) -> List[Dict]:
        """
        롱숏 기회 산점도 데이터
        X축: 펀더멘털 스코어 (P/E Gap) - 양수면 ticker1이 고평가
        Y축: 가격 스프레드 Z-Score - 양수면 ticker1이 상대적 고가
        
        롱숏 기회:
        - 3사분면: 펀더멘털 좋고 가격도 저렴 → Long ticker1
        - 1사분면: 펀더멘털 나쁘고 가격도 비쌈 → Short ticker1
        """
        data = []
        for p in pairs:
            pe_spread = p.get("pe_spread")
            z_score = p.get("price_spread_zscore")
            
            if pe_spread is not None and z_score is not None:
                # 시그널 결정
                # 펀더멘털 좋고(PE 낮음) + 가격 저렴(Z-Score 낮음) = Strong Long T1
                # 펀더멘털 나쁘고(PE 높음) + 가격 비쌈(Z-Score 높음) = Strong Short T1
                if pe_spread > 5 and z_score > 1:
                    signal = "Short T1"
                    opportunity = "high"
                elif pe_spread < -5 and z_score < -1:
                    signal = "Long T1"
                    opportunity = "high"
                elif pe_spread > 0 and z_score > 0:
                    signal = "Weak Short T1"
                    opportunity = "medium"
                elif pe_spread < 0 and z_score < 0:
                    signal = "Weak Long T1"
                    opportunity = "medium"
                else:
                    signal = "Mixed Signal"
                    opportunity = "low"
                
                data.append({
                    "label": f"{p['ticker1']}/{p['ticker2']}",
                    "x": pe_spread,  # 펀더멘털 스프레드
                    "y": z_score,    # 가격 스프레드 Z-Score
                    "sector": p["sector"],
                    "corr": p["mean_corr"],
                    "signal": signal,
                    "opportunity": opportunity,
                    "price1": p.get("price1"),
                    "price2": p.get("price2")
                })
        return data
    
    def calc_risk_metrics(self, t1: str, t2: str, lookback: int = 63) -> Dict:
        """
        롱숏 쌍의 리스크 지표 계산
        - 개별 변동성
        - 스프레드 변동성
        - Half-Life (평균 회귀 속도)
        - 베타 비율
        """
        if self.price_data is None or self.price_data.empty:
            self.load_price_data()
        
        if t1 not in self.price_data.columns or t2 not in self.price_data.columns:
            return {"error": "Ticker not found"}
        
        prices = self.price_data[[t1, t2]].dropna()
        returns = self.returns[[t1, t2]].dropna() if self.returns is not None else None
        
        if returns is None or len(returns) < lookback:
            return {"error": "Not enough data"}
        
        # 개별 변동성 (연간화)
        vol1 = float(returns[t1].std() * np.sqrt(252))
        vol2 = float(returns[t2].std() * np.sqrt(252))
        
        # 로그 가격 비율 스프레드
        log_ratio = np.log(prices[t1] / prices[t2])
        spread_returns = log_ratio.diff().dropna()
        spread_vol = float(spread_returns.std() * np.sqrt(252))
        
        # Half-Life 계산 (Ornstein-Uhlenbeck 모델 기반)
        # ΔS = θ(μ - S) + ε → Half-Life = ln(2) / θ
        try:
            spread = log_ratio - log_ratio.rolling(lookback).mean()
            spread = spread.dropna()
            lag_spread = spread.shift(1).dropna()
            current_spread = spread.iloc[1:]
            
            if len(lag_spread) > 10:
                # 회귀: ΔS = α + β*S(-1)
                delta = current_spread.values - lag_spread.values[:len(current_spread)]
                X = lag_spread.values[:len(delta)]
                
                # OLS 회귀
                beta = np.cov(delta, X)[0, 1] / np.var(X)
                
                if beta < 0:
                    half_life = -np.log(2) / beta
                    half_life = min(max(half_life, 1), 252)  # 1일 ~ 1년 범위로 제한
                else:
                    half_life = None  # Mean-reversion 없음 (발산)
            else:
                half_life = None
        except Exception as e:
            logger.warning(f"Half-life calculation error: {e}")
            half_life = None
        
        # 베타 조정 비율 (변동성 기반)
        # 동일 리스크 기여를 위한 비율
        if vol1 > 0 and vol2 > 0:
            beta_ratio = vol2 / vol1  # t1에 1달러, t2에 beta_ratio 달러
        else:
            beta_ratio = 1.0
        
        # 상관계수
        correlation = float(returns[t1].rolling(lookback).corr(returns[t2]).iloc[-1])
        
        # 현재 가격
        current_price1 = float(prices[t1].iloc[-1])
        current_price2 = float(prices[t2].iloc[-1])
        
        return {
            "ticker1": t1,
            "ticker2": t2,
            "volatility": {
                "ticker1_annual": round(vol1 * 100, 2),  # %
                "ticker2_annual": round(vol2 * 100, 2),
                "spread_annual": round(spread_vol * 100, 2)
            },
            "half_life": round(half_life, 1) if half_life else None,
            "half_life_interpretation": f"{round(half_life, 0)}일 후 스프레드가 50% 평균 회귀" if half_life else "Mean-Reversion 불확실",
            "beta_ratio": round(beta_ratio, 3),
            "beta_interpretation": f"${t1} $1당 {t2} ${beta_ratio:.2f} 비율로 헤지",
            "correlation": round(correlation, 3),
            "current_prices": {
                "ticker1": round(current_price1, 2),
                "ticker2": round(current_price2, 2),
                "ratio": round(current_price1 / current_price2, 4)
            }
        }
    
    def backtest_fundamental_longshort(
        self,
        t1: str,
        t2: str,
        entry_days_ago: int = 42,  # 2개월 전 (42 거래일)
        exit_days_ago: int = 0,   # 오늘 (0 = 현재)
        fundamental_metric: str = "pe"  # "pe", "pb", "combined"
    ) -> Dict:
        """
        펀더멘털 기반 롱숏 백테스트
        - 펀더멘털이 좋은 종목(낮은 P/E, P/B) → Long
        - 펀더멘털이 나쁜 종목(높은 P/E, P/B) → Short
        - 설정된 날짜에 진입하여 현재까지 보유
        """
        if self.price_data is None or self.price_data.empty:
            self.load_price_data()
        
        if t1 not in self.price_data.columns or t2 not in self.price_data.columns:
            return {"error": f"Ticker not found: {t1} or {t2}"}
        
        # 펀더멘털 데이터 가져오기
        fund_df = self.get_fundamentals([t1, t2])
        fund = fund_df.set_index("ticker")
        
        if t1 not in fund.index or t2 not in fund.index:
            return {"error": "Fundamentals data not available"}
        
        f1, f2 = fund.loc[t1], fund.loc[t2]
        
        # 펀더멘털 점수 계산 (낮을수록 좋음)
        def get_fundamental_score(f, metric):
            if metric == "pe":
                return f.get("pe", float('inf'))
            elif metric == "pb":
                return f.get("pb", float('inf'))
            elif metric == "combined":
                pe = f.get("pe", 50) or 50
                pb = f.get("pb", 5) or 5
                return pe * 0.7 + pb * 3  # 가중 평균
            return float('inf')
        
        score1 = get_fundamental_score(f1, fundamental_metric)
        score2 = get_fundamental_score(f2, fundamental_metric)
        
        if pd.isna(score1) or pd.isna(score2):
            return {"error": "Cannot compare fundamentals (missing data)"}
        
        # 롱/숏 결정 (점수가 낮을수록 펀더멘털이 좋음)
        if score1 < score2:
            long_ticker, short_ticker = t1, t2
            long_score, short_score = score1, score2
        else:
            long_ticker, short_ticker = t2, t1
            long_score, short_score = score2, score1
        
        prices = self.price_data[[t1, t2]].dropna()
        
        if len(prices) < entry_days_ago + 1:
            return {"error": f"Not enough price data (need at least {entry_days_ago + 1} days)"}
        
        # 진입/청산 인덱스 계산
        entry_idx = -entry_days_ago - 1 if entry_days_ago > 0 else -1
        exit_idx = -exit_days_ago - 1 if exit_days_ago > 0 else None  # None = 최신
        
        entry_date = prices.index[entry_idx]
        exit_date = prices.index[exit_idx] if exit_idx else prices.index[-1]
        
        # 진입 가격
        entry_long_price = float(prices.loc[entry_date, long_ticker])
        entry_short_price = float(prices.loc[entry_date, short_ticker])
        
        # 청산 가격
        exit_long_price = float(prices.loc[exit_date, long_ticker])
        exit_short_price = float(prices.loc[exit_date, short_ticker])
        
        # 수익률 계산
        long_return = (exit_long_price - entry_long_price) / entry_long_price
        short_return = -(exit_short_price - entry_short_price) / entry_short_price  # 숏은 음수 수익
        total_return = long_return + short_return
        
        # 일별 수익 곡선 계산
        period_prices = prices.loc[entry_date:exit_date]
        equity_curve = []
        cumulative_return = 0.0
        
        for date in period_prices.index:
            long_p = period_prices.loc[date, long_ticker]
            short_p = period_prices.loc[date, short_ticker]
            
            # 일별 누적 수익률
            long_ret = (long_p - entry_long_price) / entry_long_price
            short_ret = -(short_p - entry_short_price) / entry_short_price
            daily_total = long_ret + short_ret
            
            equity_curve.append({
                "date": date.strftime("%Y-%m-%d"),
                "equity": round(float(daily_total) * 100, 2),  # %
                "long_ret": round(float(long_ret) * 100, 2),
                "short_ret": round(float(short_ret) * 100, 2)
            })
        
        # 최대 낙폭 계산
        equity_values = [e["equity"] for e in equity_curve]
        equity_series = pd.Series(equity_values)
        max_dd = float((equity_series - equity_series.cummax()).min()) if len(equity_series) > 0 else 0
        
        # 펀더멘털 상세 정보
        fund_details = {
            "long": {
                "ticker": long_ticker,
                "pe": round(float(f1.get("pe") if long_ticker == t1 else f2.get("pe")), 2) if pd.notna(f1.get("pe") if long_ticker == t1 else f2.get("pe")) else None,
                "pb": round(float(f1.get("pb") if long_ticker == t1 else f2.get("pb")), 2) if pd.notna(f1.get("pb") if long_ticker == t1 else f2.get("pb")) else None,
                "score": round(float(long_score), 2)
            },
            "short": {
                "ticker": short_ticker,
                "pe": round(float(f2.get("pe") if short_ticker == t2 else f1.get("pe")), 2) if pd.notna(f2.get("pe") if short_ticker == t2 else f1.get("pe")) else None,
                "pb": round(float(f2.get("pb") if short_ticker == t2 else f1.get("pb")), 2) if pd.notna(f2.get("pb") if short_ticker == t2 else f1.get("pb")) else None,
                "score": round(float(short_score), 2)
            }
        }
        
        # 리스크 메트릭 계산
        risk_metrics = self.calc_risk_metrics(t1, t2)
        
        return {
            "strategy": "Fundamental Long-Short",
            "fundamental_metric": fundamental_metric,
            "ticker1": t1,
            "ticker2": t2,
            # ⚠️ Look-Ahead Bias 경고
            "warnings": [
                "⚠️ Look-Ahead Bias: 현재 펀더멘털 데이터로 과거 진입 시점을 시뮬레이션합니다.",
                "실제 거래에서는 진입 시점의 펀더멘털 데이터를 사용해야 합니다.",
                "이 백테스트는 '현재 펀더멘털 기준 전략'의 참고용입니다."
            ],
            "position": {
                "long": long_ticker,
                "short": short_ticker,
                "reasoning": f"{long_ticker}의 {fundamental_metric.upper()} ({long_score:.2f})가 {short_ticker} ({short_score:.2f})보다 낮음 (더 저평가)"
            },
            "fundamentals": fund_details,
            "risk": {
                "volatility": risk_metrics.get("volatility", {}),
                "half_life": risk_metrics.get("half_life"),
                "half_life_note": risk_metrics.get("half_life_interpretation"),
                "beta_ratio": risk_metrics.get("beta_ratio"),
                "beta_note": risk_metrics.get("beta_interpretation"),
                "correlation": risk_metrics.get("correlation")
            },
            "trade": {
                "entry_date": entry_date.strftime("%Y-%m-%d"),
                "exit_date": exit_date.strftime("%Y-%m-%d"),
                "holding_days": len(period_prices),
                "entry_prices": {
                    "long": round(entry_long_price, 2),
                    "short": round(entry_short_price, 2)
                },
                "exit_prices": {
                    "long": round(exit_long_price, 2),
                    "short": round(exit_short_price, 2)
                }
            },
            "performance": {
                "total_return": round(total_return * 100, 2),  # %
                "long_return": round(long_return * 100, 2),
                "short_return": round(short_return * 100, 2),
                "max_drawdown": round(max_dd, 2)
            },
            "equity_curve": equity_curve
        }


# Global Instance
pair_analyzer = PairTradingAnalyzer()
