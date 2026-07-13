from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScreenerConfig:
    min_market_cap_usd: float = 100_000_000
    lookback_days_52w: int = 365
    recent_high_days: int = 7
    high_tolerance: float = 0.998
    ma_windows: tuple[int, ...] = (10, 20, 50)
    kline_interval_4h: str = "4h"
    coingecko_page_size: int = 250
    coingecko_max_pages: int = 8
    request_timeout: int = 15
    binance_kline_limit: int = 200


DEFAULT_CONFIG = ScreenerConfig()
