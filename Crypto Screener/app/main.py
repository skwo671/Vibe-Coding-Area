from __future__ import annotations

import argparse
import sys
from typing import List

from dotenv import load_dotenv
from tabulate import tabulate

from .config import ScreenerConfig
from .email_notify import send_report
from .screener import CryptoScreener, ScreenResult


def _format_market_cap(value: float) -> str:
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    return f"${value / 1_000_000:.0f}M"


def _results_table(results: List[ScreenResult]) -> str:
    rows = [
        [
            i + 1,
            r.symbol,
            r.name,
            f"${r.price_usd:,.4f}",
            _format_market_cap(r.market_cap_usd),
            f"{r.days_since_52w_high}d",
            f"{r.pct_above_ma50:.1f}%",
            f"${r.ma10:,.4f}",
            f"${r.ma20:,.4f}",
            f"${r.ma50:,.4f}",
            f"{r.score:.1f}",
        ]
        for i, r in enumerate(results)
    ]
    headers = [
        "#",
        "Symbol",
        "Name",
        "Price",
        "Market Cap",
        "52W High",
        "Above MA50",
        "MA10",
        "MA20",
        "MA50",
        "Score",
    ]
    return tabulate(rows, headers=headers, tablefmt="simple")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Screen cryptocurrencies with 52-week high breakout + 4H MA trend + market cap filter.",
    )
    parser.add_argument(
        "--min-market-cap",
        type=float,
        default=100_000_000,
        help="Minimum market cap in USD (default: 100M)",
    )
    parser.add_argument(
        "--recent-days",
        type=int,
        default=7,
        help="Days to check for 52-week high (default: 7)",
    )
    parser.add_argument(
        "--email",
        type=str,
        default=None,
        help="Send report to this email address (requires SMTP_* in .env)",
    )
    args = parser.parse_args(argv)
    load_dotenv()

    config = ScreenerConfig(
        min_market_cap_usd=args.min_market_cap,
        recent_high_days=args.recent_days,
    )
    screener = CryptoScreener(config=config)

    print("Scanning cryptocurrencies...")
    print(f"  - 52-week high within last {config.recent_high_days} days")
    print("  - 4H price above MA10, MA20, MA50")
    print(f"  - Market cap > {_format_market_cap(config.min_market_cap_usd)}")
    print()

    try:
        results = screener.screen()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    criteria_lines = [
        f"52-week high within last {config.recent_high_days} days",
        "4H price above MA10, MA20, MA50",
        f"Market cap > {_format_market_cap(config.min_market_cap_usd)}",
    ]

    if not results:
        print("No coins matched all criteria.")
    else:
        print(f"Found {len(results)} coin(s):\n")
        print(_results_table(results))

    if args.email:
        try:
            send_report(args.email, results, criteria_lines)
            print(f"\nReport emailed to {args.email}")
        except Exception as exc:
            print(f"Email failed: {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
