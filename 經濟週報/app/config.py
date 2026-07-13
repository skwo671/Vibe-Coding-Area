from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from typing import List


@dataclass
class AppConfig:
    market_tickers: List[str] = field(
        default_factory=lambda: [
            "^NDX",  # NASDAQ 100
            "SMH",   # Semiconductors ETF
            "XLK",   # Technology ETF
        ]
    )
    ai_watchlist: List[str] = field(
        default_factory=lambda: [
            "NVDA",
            "AMD",
            "TSM",
            "AVGO",
            "MSFT",
            "GOOGL",
            "META",
            "AMZN",
            "AAPL",
            "ASML",
            "MU",
            "PLTR",
        ]
    )
    rss_queries: List[str] = field(
        default_factory=lambda: [
            "AI stocks",
            "semiconductor industry",
            "NVIDIA AI",
            "TSMC AI",
            "Microsoft AI",
        ]
    )
    report_dir: str = "reports"
    scheduler_day_of_week: str = "mon"
    scheduler_time: time = time(hour=8, minute=0)
    timezone: str = "Asia/Taipei"


CONFIG = AppConfig()



