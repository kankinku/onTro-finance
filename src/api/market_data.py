import os
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import yfinance as yf
from fredapi import Fred
import numpy as np
from config.settings import settings
from src.core.logger import logger

# 캐시 파일 경로는 settings에서 관리
CACHE_DIR = settings.CACHE_DIR
CACHE_FILE = str(settings.market_cache_path)
CUSTOM_MAPPING_FILE = str(CACHE_DIR / "custom_market_mapping.json")


class MarketDataProvider:
    """
    [Data Layer]
    Fetches market data from YFinance and FRED.
    Implements local JSON caching and Dynamic Source Discovery.
    """
    
    def __init__(self):
        self.fred = None
        if settings.FRED_API_KEY:
            try:
                self.fred = Fred(api_key=settings.FRED_API_KEY)
            except Exception as e:
                logger.error(f"Failed to initialize FRED API: {e}")
        
        # 1. Base Mapping (Hardcoded)
        self.base_mapping = {
            "TERM_BASE_RATE": {"source": "fred", "ticker": "DFF", "name": "Effective Federal Funds Rate"},
            "TERM_INFLATION": {"source": "fred", "ticker": "T10YIE", "name": "10-Year Breakeven Inflation Rate"},
            "TERM_EXCHANGE_RATE": {"source": "yf", "ticker": "KRW=X", "name": "USD/KRW Exchange Rate"},
            "TERM_TREASURY_YIELD": {"source": "yf", "ticker": "^TNX", "name": "Treasury Yield 10 Years"},
            "TERM_UST": {"source": "yf", "ticker": "^TNX", "name": "Treasury Yield 10 Years"}, 
            "TERM_LIQUIDITY": {"source": "fred", "ticker": "RRPONTSYD", "name": "Overnight Reverse Repurchase Agreements"},
            "TERM_ASSET_PRICE": {"source": "yf", "ticker": "^GSPC", "name": "S&P 500"},
            "TERM_CORP_BOND": {"source": "yf", "ticker": "LQD", "name": "iShares iBoxx $ Inv Grade Corporate Bond ETF"},
            "TERM_CREDIT_SPREAD": {"source": "fred", "ticker": "BAMLC0A0CM", "name": "ICE BofA US Corp Master Option-Adjusted Spread"},
            "TERM_TREASURY_DEMAND": {"source": "yf", "ticker": "^TNX", "name": "Treasury Yield (Inverse Proxy)"},
        }

        # 2. Load Custom Mapping (Dynamic)
        self.custom_mapping = self._load_custom_mapping()
        
        # 3. Merge Mappings (Priority: Custom > Base)
        self.mapping = {**self.base_mapping, **self.custom_mapping}

        # Dashboard targets config
        self.dashboard_targets = [
            {"id": "TGA", "source": "fred", "ticker": "WTREGEN", "title": "재무부 일반계정 (TGA)", "desc": "미국 정부의 비상금 통장 잔고입니다.", "interpret_up": "시중 유동성 흡수 (부정적)", "interpret_down": "시중 유동성 방출 (긍정적)"},
            {"id": "RESERVES", "source": "fred", "ticker": "TOTRESNS", "title": "지급준비금 (Reserves)", "desc": "시중 은행들이 연준에 예치해둔 현금 총액입니다.", "interpret_up": "은행 대출여력 증가 (긍정적)", "interpret_down": "은행 대출여력 감소 (부정적)"},
            {"id": "RRP", "source": "fred", "ticker": "RRPONTSYD", "title": "역레포 (ON RRP)", "desc": "단기 자금이 머무는 파킹 통장 잔고입니다.","interpret_up": "시장 자금 경색 가능성", "interpret_down": "시장으로 자금 이동 (긍정적)"},
            {"id": "YIELD_10Y", "source": "yf", "ticker": "^TNX", "title": "미국채 10년물 금리", "desc": "전 세계 자산 가격의 기준이 되는 금리입니다.", "interpret_up": "자산 가치 하락 압력", "interpret_down": "자산 가치 상승 요인"},
            {"id": "DFF", "source": "fred", "ticker": "DFF", "title": "연준 기준금리 (FFR)", "desc": "미국 중앙은행의 정책 금리입니다.", "interpret_up": "긴축 정책 (유동성 축소)", "interpret_down": "완화 정책 (유동성 공급)"},
        ]
        
        # Load Cache
        self.cache = self._load_cache()

    def _load_cache(self) -> Dict[str, Any]:
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load cache: {e}")
        return {}

    def _save_cache(self):
        try:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

    def _load_custom_mapping(self) -> Dict[str, Any]:
        if os.path.exists(CUSTOM_MAPPING_FILE):
            try:
                with open(CUSTOM_MAPPING_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load custom mapping: {e}")
        return {}

    def _save_custom_mapping(self):
        try:
            with open(CUSTOM_MAPPING_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.custom_mapping, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save custom mapping: {e}")

    def search_and_register_ticker(self, keyword: str) -> Optional[str]:
        """
        Searches API (FRED priority) for the keyword.
        If found, registers it to custom_mapping and fetches data.
        Returns the registered Term ID or None.
        """
        if not self.fred:
            logger.warning("FRED API not available for discovery.")
            return None
        
        logger.info(f"🔎 Auto-Discovering Data for keyword: '{keyword}'...")
        
        try:
            # 1. Search FRED
            search_results = self.fred.search(keyword, limit=5, order_by='popularity', sort_order='desc')
            if search_results is None or search_results.empty:
                logger.info(f"No results found in FRED for {keyword}")
                return None
            
            # Pick the top result
            top_result = search_results.iloc[0]
            series_id = top_result.name # FRED returns Series ID as index (usually) or 'id' column
            title = top_result['title']
            
            # Generate a Term ID
            clean_key = keyword.upper().replace(" ", "_")
            term_id = f"TERM_{clean_key}"
            
            # Register
            new_entry = {
                "source": "fred",
                "ticker": series_id,
                "name": title
            }
            
            self.custom_mapping[term_id] = new_entry
            self.mapping[term_id] = new_entry # Update current runtime mapping
            
            self._save_custom_mapping()
            logger.info(f"✅ Registered New Source: {term_id} -> {title} ({series_id})")
            
            # Trigger Fetch immediately for this one
            self.initialize_data(specific_ticker=series_id) 
            
            return term_id
            
        except Exception as e:
            logger.error(f"Discovery Failed: {e}")
            return None

    def initialize_data(self, specific_ticker=None):
        """
        [Sync Process]
        Checks local cache for missing data up to today.
        Fetches only missing periods from APIs.
        Finally, runs LLM analysis on the fresh data (unless specific_ticker is set).
        """
        logger.info(f"Initializing market data... (Target: {specific_ticker if specific_ticker else 'ALL'})")
        
        # Check all tickers used in mapping and dashboard
        all_tickers = []
        
        # Add Dashboard Tickers
        for t in self.dashboard_targets:
            all_tickers.append(t)
            
        # Add Method 2 tickers (Mapping)
        for key, val in self.mapping.items():
            # Check if already added
            found = False
            for existing in all_tickers:
                if existing['ticker'] == val['ticker']:
                    found = True
                    break
            if not found:
                all_tickers.append({"id": key, "source": val["source"], "ticker": val["ticker"]})

        # Filter if specific ticker requested
        if specific_ticker:
            all_tickers = [t for t in all_tickers if t['ticker'] == specific_ticker]
            if not all_tickers:
                logger.warning(f"Ticker {specific_ticker} not found in configuration.")
                return

        today = datetime.now().date()
        
        for item in all_tickers:
            ticker = item['ticker']
            source = item['source']
            
            # Cache Key
            cache_key = f"{source}:{ticker}"
            
            # Get last update date from cache
            if cache_key not in self.cache:
                self.cache[cache_key] = {"last_updated": "2023-01-01", "history": {}}
            
            last_dt_str = self.cache[cache_key]["last_updated"]
            last_dt = datetime.strptime(last_dt_str, "%Y-%m-%d").date()
            
            # Calculate days gap
            # Don't fetch if updated today
            if last_dt >= today:
                continue
                
            start_date = last_dt + timedelta(days=1)
            
            # Fetch
            logger.info(f"Fetching {ticker} from {start_date} to {today}...")
            try:
                df = None
                if source == "yf":
                    # Yfinance
                    df = yf.Ticker(ticker).history(start=start_date.strftime("%Y-%m-%d"), end=today.strftime("%Y-%m-%d") )
                    if df.empty:
                        # Fallback for generic 'recent' fetch if specific date fails
                         df = yf.Ticker(ticker).history(period="5d")
                    else:
                         df = df[['Close']]

                elif source == "fred":
                    if self.fred:
                        s = self.fred.get_series(ticker, observation_start=start_date.strftime("%Y-%m-%d"))
                        if not s.empty:
                            df = s.to_frame(name='Close')

                if df is not None and not df.empty:
                    # Merge into cache
                    history = self.cache[cache_key]["history"]
                    for idx, row in df.iterrows():
                        # idx is Timestamp
                        date_str = idx.strftime("%Y-%m-%d")
                        val = float(row['Close'])
                        if not np.isnan(val):
                            history[date_str] = val
                    
                    # Update metadata
                    sorted_dates = sorted(history.keys())
                    if sorted_dates:
                        self.cache[cache_key]["last_updated"] = sorted_dates[-1]
                        
            except Exception as e:
                logger.error(f"Error updating {ticker}: {e}")
        
        self._save_cache()
        logger.info("Market data synchronization complete.")
        
        # Trigger LLM Analysis ONLY when doing full init
        if not specific_ticker:
            self.analyze_market_with_llm()

    def analyze_market_with_llm(self):
        """
        Summarize market conditions using Ollama (local LLM).
        Follows a strict 'Cynical & Structural' analysis persona.
        """
        logger.info("Running LLM Market Analysis...")
        import requests

        # 1. Gather Summary Data
        data_snapshot = []
        for t in self.dashboard_targets:
            res = self._get_cached_metric(t["source"], t["ticker"], t["title"])
            if res:
                data_snapshot.append(f"- {t['title']}: {res['value']:.2f} (Weekly Change: {res['change_1w']:+.2f}%)")
        
        data_text = "\n".join(data_snapshot)
        
        prompt = f"""
        당신은 냉철한 거시경제 분석가입니다. 아래 시장 데이터를 보고 유동성 관점에서 한국어로 3줄 요약을 작성하십시오.
        
        [제약 사항]
        1. 언어: 한국어만 사용할 것 (필요 시 영어 금융 용어 병기 가능). 그 외 언어 절대 금지.
        2. 형식: 마크다운(Markdown), 볼드체(**), 이모지 사용 금지. 오로지 평문 텍스트로만 작성할 것.
        3. 어조: 감정적 미사여구 배제. 냉정하고 단호하게 (~함. ~임. 체로 종결).

        [현재 시장 데이터]
        {data_text}
        
        [작성 가이드]
        - 내용: TGA, 지준금(Reservs), 금리를 종합하여 실제 시장 유동성이 늘었는지 줄었는지 판단할 것.
        - 핵심: 단순 수치 나열이 아니라 '의미'를 해석할 것.
        
        [출력 예시]
        1. TGA 증가와 QT 지속으로 실질 유동성은 감소함.
        2. 국채 금리 상승은 안전 자산 선호 심리가 약화되었음을 시사.
        3. 단기적 반등이 있더라도 구조적 유동성 환경은 여전히 긴축적임.
        """

        try:
            resp = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": settings.OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2}
                },
                timeout=20
            )
            if resp.status_code == 200:
                result = resp.json().get("response", "").strip()
                self.cache["market_insight"] = result
                self._save_cache()
                logger.info("LLM Analysis Complete & Cached.")
            else:
                logger.error(f"Ollama Error: {resp.text}")
        except Exception as e:
            logger.error(f"Failed to run LLM analysis: {e}")

    def get_market_indicator(self, term_id: str) -> Optional[Dict[str, Any]]:
        if term_id not in self.mapping:
            return None
        config = self.mapping[term_id]
        return self._get_cached_metric(config["source"], config["ticker"], config["name"])

    def get_metric_history(self, source: str, ticker: str) -> List[Dict[str, Any]]:
        """
        Returns historical data for charting.
        Sorted by date ascending.
        """
        cache_key = f"{source}:{ticker}"
        if cache_key not in self.cache:
            return []
        
        history = self.cache[cache_key].get("history", {})
        # Sort by date
        sorted_items = sorted(history.items())
        
        # Convert to list of dicts
        return [{"date": k, "value": v} for k, v in sorted_items]

    def analyze_metric_detail(self, source: str, ticker: str, title: str) -> str:
        """
        Generates a deep-dive report for a specific metric using LLM.
        """
        import requests
        
        # Get recent history (last 30 days) to show trend context
        history = self.get_metric_history(source, ticker)
        recent_data = history[-30:] if history else []
        
        if not recent_data:
            return "데이터가 부족하여 분석할 수 없습니다."

        start_val = recent_data[0]['value']
        end_val = recent_data[-1]['value']
        change_pct = ((end_val - start_val) / start_val) * 100 if start_val != 0 else 0
        
        prompt = f"""
        금융 전문가로서 다음 지표({title})를 분석하여 보고해.

        [강력한 제약 사항]
        1. 제목/소제목(제1장, AI 리포트 등) 절대 금지. 바로 본문 시작할 것.
        2. 볼드체(**), 이모지, 마크다운 헤더(#) 절대 사용 금지.
        3. 오로지 평문 텍스트와 하나의 '마크다운 표'로만 구성할 것.
        4. 언어: 한국어만 사용 (영어 단어 최소화).

        [분석 대상]
        - 지표: {title}
        - 현재값: {end_val:,.2f}
        - 변동: {change_pct:+.2f}%
        - 추이: {recent_data[-5:]}

        [출력 순서 및 가이드]
        1. 최근 데이터 5개를 '날짜 | 값' 형태의 마크다운 표로 작성.
        2. 이어서 바로 분석 내용 작성 (3줄 내외).
        3. 연관 자산 파급 효과를 2줄로 요약.
        """
        
        try:
            resp = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": settings.OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3}
                },
                timeout=25
            )
            if resp.status_code == 200:
                return resp.json().get("response", "분석 실패").strip()
            return f"LLM 오류: {resp.status_code}"
        except Exception as e:
            return f"분석 중 오류 발생: {e}"

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """
        Returns structured dashboard data:
        {
            "insight": "LLM Analysis Text...",
            "cards": [ ... ]
        }
        """
        cards = []
        for t in self.dashboard_targets:
            data = self._get_cached_metric(t["source"], t["ticker"], t["title"])
            if not data:
                continue
            
            # Calculate Interpretation
            change_val = data['change_1w'] # Use 1W for robust trend
            
            interpretation = t["interpret_up"] if change_val >= 0 else t["interpret_down"]
            is_good = (t["id"] in ["RESERVES", "DFF"] and change_val > 0) or (t["id"] not in ["RESERVES", "DFF"] and change_val < 0)

            cards.append({
                "id": t["id"], # Add ID for frontend mapping
                "title": t["title"],
                "value": f"{data['value']:,.2f}",
                "change": f"{data['change_1w']:+.2f}%", 
                "desc": t["desc"],
                "interpretation": f"변동 의미: {interpretation}",
                "is_positive": bool(is_good),
                "source": t["source"],
                "ticker": t["ticker"]
            })
            
        insight = self.cache.get("market_insight", "시장 분석 데이터가 충분하지 않습니다.")
        
        return {
            "insight": insight,
            "cards": cards
        }

    def _get_cached_metric(self, source, ticker, name) -> Optional[Dict[str, Any]]:
        cache_key = f"{source}:{ticker}"
        if cache_key not in self.cache:
            return None
        
        hist = self.cache[cache_key].get("history", {})
        if not hist:
            return None
            
        # Sort dates
        dates = sorted(hist.keys())
        latest_date = dates[-1]
        latest_val = hist[latest_date]
        
        # Helper for % change
        def get_pct_change(days_ago):
            target_dt = datetime.strptime(latest_date, "%Y-%m-%d") - timedelta(days=days_ago)
            # Find closest date <= target_dt
            target_str = target_dt.strftime("%Y-%m-%d")
            
            found_val = None
            # Iterate backwards from latest
            for d in reversed(dates):
                if d <= target_str:
                    found_val = hist[d]
                    break
            
            if found_val is None:
                found_val = hist[dates[0]] # Oldest available
            
            if found_val == 0: return 0.0
            return ((latest_val - found_val) / found_val) * 100.0

        change_1d = get_pct_change(1)
        change_1w = get_pct_change(7)
        change_1m = get_pct_change(30)
        
        trend = "STABLE"
        if change_1w > 0.5: trend = "UP"
        elif change_1w < -0.5: trend = "DOWN"

        return {
            "indicator": name,
            "value": float(latest_val),
            "unit": "",
            "change_1d": float(change_1d),
            "change_1w": float(change_1w),
            "change_1m": float(change_1m),
            "trend": trend,
            "data_source": f"{source.upper()}:{ticker}",
            "timestamp": latest_date
        }

    def check_trend_alignment(self, term_id: str, expected_direction: str) -> float:
        data = self.get_market_indicator(term_id)
        if not data:
            return 0.5

        trend = data['trend']
        
        # Inversion logic
        if term_id == "TERM_TREASURY_DEMAND" and "TNX" in data['data_source']:
             if trend == "UP": trend = "DOWN"
             elif trend == "DOWN": trend = "UP"

        if expected_direction == "INCREASE":
            return 1.0 if trend == "UP" else (0.0 if trend == "DOWN" else 0.5)
        elif expected_direction == "DECREASE":
            return 1.0 if trend == "DOWN" else (0.0 if trend == "UP" else 0.5)
            
        return 0.5
