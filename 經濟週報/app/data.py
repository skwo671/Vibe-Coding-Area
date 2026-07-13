from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import pandas as pd
import yfinance as yf


@dataclass
class TickerSeries:
    symbol: str
    history: pd.DataFrame  # columns: [Open, High, Low, Close, ...]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def fetch_ticker_history(symbols: List[str], days: int = 180) -> Dict[str, TickerSeries]:
    end_dt = _utc_now()
    start_dt = end_dt - timedelta(days=days)
    result: Dict[str, TickerSeries] = {}
    for s in symbols:
        try:
            data = yf.download(s, start=start_dt.date(), end=end_dt.date(), progress=False)
            if not isinstance(data, pd.DataFrame) or data.empty:
                continue
            data = data.rename(columns=str.title)
            result[s] = TickerSeries(symbol=s, history=data)
        except Exception:
            continue
    return result


def compute_indicators(price_df: pd.DataFrame) -> pd.DataFrame:
    df = price_df.copy()
    if df.empty:
        return df
    df["SMA20"] = df["Close"].rolling(window=20, min_periods=5).mean()
    df["SMA50"] = df["Close"].rolling(window=50, min_periods=10).mean()
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["Mom10"] = df["Close"].pct_change(10)
    df["Ret1W"] = df["Close"].pct_change(5)
    df["Ret4W"] = df["Close"].pct_change(20)
    return df



