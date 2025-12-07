
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any

CACHE_FILE = "indices_cache.json"

class MarketIndices:
    """
    주요 시장 지수 (Nasdaq, S&P 500, Gold, Bitcoin) 데이터 제공자
    """
    
    # Ticker Mapping
    INDICES = {
        "NASDAQ": {"ticker": "QQQ", "name": "Nasdaq 100", "color": "#0091ea"}, # Blue
        "SNP500": {"ticker": "SPY", "name": "S&P 500", "color": "#ff3b30"},   # Red
        "GOLD": {"ticker": "GC=F", "name": "Gold", "color": "#f5a623"},       # Gold/Orange
        "BTC": {"ticker": "BTC-USD", "name": "Bitcoin", "color": "#f7931a"}    # Bitcoin Orange
    }

    def __init__(self):
        self.cache_dir = os.path.join(os.path.dirname(__file__), "..", "..", "cache")
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
        self.cache_path = os.path.join(self.cache_dir, CACHE_FILE)

    def _load_cache(self) -> Dict:
        if os.path.exists(self.cache_path):
            with open(self.cache_path, 'r') as f:
                return json.load(f)
        return {}

    def _save_cache(self, data: Dict):
        with open(self.cache_path, 'w') as f:
            json.dump(data, f)

    def get_index_data(self, key: str, period: str = "1y") -> Dict[str, Any]:
        """
        특정 지수의 데이터 반환 (캐싱 적용)
        """
        if key not in self.INDICES:
            return {"error": "Invalid index key"}
        
        meta = self.INDICES[key]
        ticker = meta["ticker"]
        
        # Cache Check
        cache = self._load_cache()
        cache_key = f"{key}_{period}"
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        if cache_key in cache:
            entry = cache[cache_key]
            if entry.get("date") == today_str:
                return entry["data"]

        # Fetch from yfinance
        try:
            df = yf.Ticker(ticker).history(period=period)
            if df.empty:
                return {"error": "No data found"}
            
            # Format Data for Chart.js
            # [{x: '2024-01-01', y: 150.23}, ...]
            chart_data = []
            current_price = 0
            prev_price = 0
            
            if not df.empty:
                current_price = float(df['Close'].iloc[-1])
                prev_price = float(df['Close'].iloc[-2])
                
                for date, row in df.iterrows():
                    chart_data.append({
                        "x": date.strftime("%Y-%m-%d"),
                        "y": round(float(row['Close']), 2)
                    })
            
            change = current_price - prev_price
            change_pct = (change / prev_price) * 100 if prev_price else 0
            
            result = {
                "meta": meta,
                "current_price": round(current_price, 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "history": chart_data
            }
            
            # Save to cache
            cache[cache_key] = {
                "date": today_str,
                "data": result
            }
            self._save_cache(cache)
            
            return result
            
        except Exception as e:
            return {"error": str(e)}

market_indices = MarketIndices()
