from __future__ import annotations

import sys
from datetime import datetime
from typing import Dict, List

import pandas as pd

from .config import CONFIG
from .data import compute_indicators, fetch_ticker_history
from .news import fetch_rss_for_queries
from .analysis import compute_trend_signals, make_recommendations, score_news_sentiment
from .report import render_markdown, render_html_from_markdown, write_reports
from .scheduler import run_weekly


def generate_once() -> None:
    now = datetime.now()

    market_hist = fetch_ticker_history(CONFIG.market_tickers)
    ai_hist = fetch_ticker_history(CONFIG.ai_watchlist)

    market_ind = {k: compute_indicators(v.history) for k, v in market_hist.items()}
    ai_ind = {k: compute_indicators(v.history) for k, v in ai_hist.items()}

    market_signals = compute_trend_signals(market_ind)
    ai_signals = compute_trend_signals(ai_ind)

    news_items = fetch_rss_for_queries(CONFIG.rss_queries, max_items_per_query=20)
    sentiment = score_news_sentiment([n.title + ". " + n.summary for n in news_items])

    recommendations = make_recommendations(market_signals, ai_signals, sentiment)

    md = render_markdown(now, market_signals, ai_signals, sentiment, recommendations)
    html = render_html_from_markdown(md)
    md_path, html_path = write_reports(CONFIG.report_dir, now, md, html)
    print(f"Report written: {md_path}\n{html_path}")


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("Usage: python -m app.main [run-once|schedule]")
        return 2
    cmd = argv[1]
    if cmd == "run-once":
        generate_once()
        return 0
    if cmd == "schedule":
        def job():
            try:
                generate_once()
            except Exception as e:
                print(f"Error during scheduled run: {e}")

        run_weekly(
            day_of_week=CONFIG.scheduler_day_of_week,
            hour=CONFIG.scheduler_time.hour,
            minute=CONFIG.scheduler_time.minute,
            timezone_name=CONFIG.timezone,
            job=job,
        )
        return 0
    print("Unknown command.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))





