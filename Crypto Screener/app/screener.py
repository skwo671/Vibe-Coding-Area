from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

from .config import ScreenerConfig, DEFAULT_CONFIG
from .data import DataFetcher


@dataclass
class ScreenResult:
    symbol: str
    name: str
    binance_symbol: str
    price_usd: float
    market_cap_usd: float
    high_52w: float
    high_7d: float
    days_since_52w_high: int
    ma10: float
    ma20: float
    ma50: float
    pct_above_ma50: float
    score: float


def _days_since_high(daily: pd.DataFrame, target_high: float) -> int:
    hits = daily[daily["high"] >= target_high * 0.998]
    if hits.empty:
        return 999
    last_hit = hits.iloc[-1]["open_time"]
    last_day = daily.iloc[-1]["open_time"]
    return max(0, int((last_day - last_hit).total_seconds() // 86400))


def _hit_52w_high_in_last_n_days(daily: pd.DataFrame, config: ScreenerConfig) -> tuple[bool, float, float, int]:
    if len(daily) < config.recent_high_days + 20:
        return False, 0.0, 0.0, 999

    window = daily.tail(config.lookback_days_52w)
    recent = window.tail(config.recent_high_days)
    prior = window.iloc[: -config.recent_high_days]

    high_52w = float(window["high"].max())
    high_7d = float(recent["high"].max())
    if high_52w <= 0:
        return False, high_52w, high_7d, 999

    prior_max = float(prior["high"].max()) if not prior.empty else 0.0
    made_new_high = high_7d >= high_52w * config.high_tolerance
    is_breakout = high_7d > prior_max * config.high_tolerance if prior_max > 0 else made_new_high
    days_since = _days_since_high(window, high_52w)

    return made_new_high and is_breakout and days_since <= config.recent_high_days, high_52w, high_7d, days_since


def _price_above_mas(h4: pd.DataFrame, config: ScreenerConfig) -> tuple[bool, float, float, float, float]:
    max_window = max(config.ma_windows)
    if len(h4) < max_window:
        return False, 0.0, 0.0, 0.0, 0.0

    close = h4["close"]
    ma_values = {w: float(close.rolling(window=w).mean().iloc[-1]) for w in config.ma_windows}
    price = float(close.iloc[-1])

    above_all = all(price > ma_values[w] for w in config.ma_windows)
    pct_above_ma50 = ((price / ma_values[50]) - 1.0) * 100 if ma_values[50] > 0 else 0.0
    return above_all, ma_values[10], ma_values[20], ma_values[50], pct_above_ma50


def _score_result(
    pct_above_ma50: float,
    days_since_52w_high: int,
    market_cap_usd: float,
) -> float:
    recency = max(0.0, 7 - days_since_52w_high) / 7.0
    cap_factor = min(market_cap_usd / 1_000_000_000, 5.0)
    return pct_above_ma50 * 0.5 + recency * 30 + cap_factor * 2


class CryptoScreener:
    def __init__(self, fetcher: Optional[DataFetcher] = None, config: ScreenerConfig = DEFAULT_CONFIG) -> None:
        self.fetcher = fetcher or DataFetcher(config)
        self.config = config

    def screen(self) -> List[ScreenResult]:
        usdt_symbols = self.fetcher.get_binance_usdt_symbols()
        coins = self.fetcher.fetch_coins_by_market_cap()
        results: List[ScreenResult] = []

        for coin in coins:
            binance_symbol = self.fetcher.to_binance_symbol(coin.get("symbol", ""), usdt_symbols)
            if not binance_symbol:
                continue

            try:
                daily = self.fetcher.fetch_klines(
                    binance_symbol,
                    interval="1d",
                    limit=self.config.lookback_days_52w + 10,
                )
                h4 = self.fetcher.fetch_klines(
                    binance_symbol,
                    interval=self.config.kline_interval_4h,
                    limit=self.config.binance_kline_limit,
                )
            except Exception:
                continue

            hit_high, high_52w, high_7d, days_since = _hit_52w_high_in_last_n_days(daily, self.config)
            if not hit_high:
                continue

            above_mas, ma10, ma20, ma50, pct_above_ma50 = _price_above_mas(h4, self.config)
            if not above_mas:
                continue

            market_cap = float(coin.get("market_cap") or 0)
            price = float(coin.get("current_price") or h4["close"].iloc[-1])
            score = _score_result(pct_above_ma50, days_since, market_cap)

            results.append(
                ScreenResult(
                    symbol=coin.get("symbol", "").upper(),
                    name=coin.get("name", ""),
                    binance_symbol=binance_symbol,
                    price_usd=price,
                    market_cap_usd=market_cap,
                    high_52w=high_52w,
                    high_7d=high_7d,
                    days_since_52w_high=days_since,
                    ma10=ma10,
                    ma20=ma20,
                    ma50=ma50,
                    pct_above_ma50=pct_above_ma50,
                    score=score,
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results
