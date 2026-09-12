import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

class MarketData:
    TIMEFRAME_MAP = {
        "5m": ("5d", "5m"),
        "15m": ("1mo", "15m"),
        "1h": ("3mo", "60m"),
        "4h": ("6mo", "1h"),
        "1d": ("2y", "1d"),
    }
    
    @staticmethod
    def get_ohlc(symbol: str, timeframe: str = "1h", limit: int = 500) -> pd.DataFrame:
        if timeframe not in MarketData.TIMEFRAME_MAP:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        period, interval = MarketData.TIMEFRAME_MAP[timeframe]
        df = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=False)
        if df.empty:
            raise ValueError(f"No data for {symbol}")
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.rename(columns=str.lower)
        df = df[["open", "high", "low", "close", "volume"]].dropna()
        if timeframe == "4h":
            df = df.resample("4H").agg({
                "open": "first", "high": "max",
                "low": "min", "close": "last", "volume": "sum"
            }).dropna()
        return df.tail(limit)
