from __future__ import annotations

import time
from typing import Dict, List, Optional, Set

import pandas as pd
import requests

from .config import ScreenerConfig, DEFAULT_CONFIG

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
BINANCE_BASE = "https://api.binance.com/api/v3"


class DataFetcher:
    def __init__(self, config: ScreenerConfig = DEFAULT_CONFIG) -> None:
        self.config = config
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})
        self._binance_usdt_symbols: Optional[Set[str]] = None

    def _get_json(self, url: str, params: Optional[dict] = None) -> object:
        resp = self._session.get(url, params=params, timeout=self.config.request_timeout)
        resp.raise_for_status()
        return resp.json()

    def get_binance_usdt_symbols(self) -> Set[str]:
        if self._binance_usdt_symbols is not None:
            return self._binance_usdt_symbols

        data = self._get_json(f"{BINANCE_BASE}/exchangeInfo")
        symbols: Set[str] = set()
        for item in data.get("symbols", []):
            if item.get("status") != "TRADING":
                continue
            if item.get("quoteAsset") != "USDT":
                continue
            if item.get("isSpotTradingAllowed") is False:
                continue
            symbols.add(item["symbol"])
        self._binance_usdt_symbols = symbols
        return symbols

    def fetch_coins_by_market_cap(self) -> List[dict]:
        coins: List[dict] = []
        for page in range(1, self.config.coingecko_max_pages + 1):
            batch = self._get_json(
                f"{COINGECKO_BASE}/coins/markets",
                params={
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": self.config.coingecko_page_size,
                    "page": page,
                    "sparkline": "false",
                },
            )
            if not batch:
                break

            for coin in batch:
                market_cap = coin.get("market_cap") or 0
                if market_cap < self.config.min_market_cap_usd:
                    return coins
                coins.append(coin)

            if len(batch) < self.config.coingecko_page_size:
                break
            time.sleep(1.2)

        return coins

    def to_binance_symbol(self, coin_symbol: str, usdt_symbols: Set[str]) -> Optional[str]:
        symbol = coin_symbol.upper()
        candidates = [f"{symbol}USDT"]
        if symbol == "BTC":
            candidates.insert(0, "BTCUSDT")
        for candidate in candidates:
            if candidate in usdt_symbols:
                return candidate
        return None

    def fetch_klines(self, symbol: str, interval: str, limit: int) -> pd.DataFrame:
        raw = self._get_json(
            f"{BINANCE_BASE}/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(
            raw,
            columns=[
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_volume",
                "trades",
                "taker_buy_base",
                "taker_buy_quote",
                "ignore",
            ],
        )
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        return df.dropna(subset=["close", "high"])
