from __future__ import annotations

import argparse
import logging
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Iterable, Protocol

import numpy as np
import pandas as pd


DEFAULT_CRYPTO_SYMBOLS = (
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "BNB-USD",
    "XRP-USD",
    "ADA-USD",
    "DOGE-USD",
    "AVAX-USD",
    "LINK-USD",
    "LTC-USD",
)
DEFAULT_US_STOCK_SYMBOLS = (
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "GOOGL",
    "AVGO",
    "TSLA",
    "AMD",
    "NFLX",
    "COST",
    "JPM",
    "V",
    "MA",
    "LLY",
)
DEFAULT_MARKET_CAP_MIN = 100_000_000
DEFAULT_WEEKLY_TURNOVER_MIN = 0.05


@dataclass(frozen=True)
class AssetRequest:
    symbol: str
    asset_type: str


@dataclass(frozen=True)
class Candidate:
    symbol: str
    asset_type: str
    latest_price: float
    market_cap: int
    weekly_turnover_pct: float
    high_52w: float
    high_52w_date: str
    ma10_4h: float
    ma20_4h: float
    ma50_4h: float
    buy_zone_low: float
    buy_zone_high: float
    stop_reference: float
    chart_path: str = ""


class MarketDataProvider(Protocol):
    def history(self, symbol: str, period: str, interval: str) -> pd.DataFrame:
        ...

    def market_cap(self, symbol: str) -> int | None:
        ...


class YahooFinanceProvider:
    def __init__(self) -> None:
        import yfinance as yf

        self._yf = yf
        self._tickers: dict[str, object] = {}

    def _ticker(self, symbol: str):
        if symbol not in self._tickers:
            self._tickers[symbol] = self._yf.Ticker(symbol)
        return self._tickers[symbol]

    def history(self, symbol: str, period: str, interval: str) -> pd.DataFrame:
        ticker = self._ticker(symbol)
        return ticker.history(period=period, interval=interval, auto_adjust=False, actions=False)

    def market_cap(self, symbol: str) -> int | None:
        ticker = self._ticker(symbol)
        fast_info = getattr(ticker, "fast_info", None)
        for key in ("market_cap", "marketCap"):
            try:
                value = fast_info.get(key) if fast_info is not None else None
            except Exception:
                value = None
            if value:
                return int(value)

        try:
            info = ticker.get_info()
        except Exception:
            return None
        value = info.get("marketCap") or info.get("market_cap")
        return int(value) if value else None


class SampleMarketDataProvider:
    """Deterministic data source for local smoke tests and demos."""

    _passing_symbols = {"BTC-USD", "SOL-USD", "NVDA", "MSFT"}

    def history(self, symbol: str, period: str, interval: str) -> pd.DataFrame:
        if interval == "1d":
            return self._daily_history(symbol)
        if interval == "4h":
            return self._four_hour_history(symbol)
        raise ValueError(f"Unsupported sample interval: {interval}")

    def market_cap(self, symbol: str) -> int | None:
        if symbol in self._passing_symbols:
            return 250_000_000_000 if symbol.endswith("-USD") else 2_500_000_000_000
        return 80_000_000

    def _daily_history(self, symbol: str) -> pd.DataFrame:
        now = pd.Timestamp.now(tz="UTC").normalize()
        index = pd.date_range(end=now, periods=365, freq="D")
        base = 100 + (sum(ord(c) for c in symbol) % 30)
        close = np.linspace(base, base * 1.8, len(index))
        high = close * 1.01
        if symbol in self._passing_symbols:
            high[-3] = high.max() * 1.05
            volume = np.full(len(index), 2_000_000_000 if symbol.endswith("-USD") else 150_000_000)
        else:
            high[-30] = high.max() * 1.05
            volume = np.full(len(index), 1_000_000)
        return pd.DataFrame({"Open": close * 0.99, "High": high, "Low": close * 0.98, "Close": close, "Volume": volume}, index=index)

    def _four_hour_history(self, symbol: str) -> pd.DataFrame:
        now = pd.Timestamp.now(tz="UTC").floor("4h")
        index = pd.date_range(end=now, periods=90, freq="4h")
        base = 100 + (sum(ord(c) for c in symbol) % 30)
        close = np.linspace(base, base * 1.35, len(index))
        if symbol not in self._passing_symbols:
            close[-1] = close[-50:].mean() * 0.95
        high = close * 1.01
        low = close * 0.99
        return pd.DataFrame({"Open": close * 0.995, "High": high, "Low": low, "Close": close}, index=index)


def normalize_history(history: pd.DataFrame) -> pd.DataFrame:
    if history is None or history.empty:
        return pd.DataFrame()
    df = history.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [str(col[-1]).lower() for col in df.columns]
    else:
        df.columns = [str(col).strip().lower().replace(" ", "_") for col in df.columns]
    return df


def _as_utc_timestamp(value: object) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def recent_52_week_high(
    daily_history: pd.DataFrame,
    lookback_days: int = 7,
    now: pd.Timestamp | None = None,
) -> tuple[bool, float, pd.Timestamp | None]:
    df = normalize_history(daily_history)
    if "high" not in df or df["high"].dropna().empty:
        return False, float("nan"), None

    highs = df["high"].dropna()
    high_52w = float(highs.max())
    high_dates = highs[highs == high_52w].index
    high_date = max(_as_utc_timestamp(value) for value in high_dates)
    current_time = now if now is not None else pd.Timestamp.now(tz="UTC")
    if current_time.tzinfo is None:
        current_time = current_time.tz_localize("UTC")
    cutoff = current_time.tz_convert("UTC") - pd.Timedelta(days=lookback_days)
    return high_date >= cutoff, high_52w, high_date


def moving_average_snapshot(four_hour_history: pd.DataFrame) -> tuple[bool, float, float, float, float]:
    df = normalize_history(four_hour_history)
    if "close" not in df or len(df) < 50:
        return False, float("nan"), float("nan"), float("nan"), float("nan")

    close = df["close"].astype(float)
    ma10 = close.rolling(10).mean().iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    ma50 = close.rolling(50).mean().iloc[-1]
    latest = close.iloc[-1]
    values = (latest, ma10, ma20, ma50)
    if any(pd.isna(value) for value in values):
        return False, float(latest), float(ma10), float(ma20), float(ma50)
    return latest > ma10 and latest > ma20 and latest > ma50, float(latest), float(ma10), float(ma20), float(ma50)


def weekly_turnover_rate(daily_history: pd.DataFrame, market_cap: int, asset_type: str) -> float | None:
    df = normalize_history(daily_history)
    if market_cap <= 0 or "volume" not in df or "close" not in df:
        return None

    recent = df[["volume", "close"]].dropna().tail(7)
    if len(recent) < 5:
        return None

    if asset_type == "crypto":
        traded_value = recent["volume"].astype(float).sum()
    else:
        traded_value = (recent["volume"].astype(float) * recent["close"].astype(float)).sum()
    return float(traded_value / market_cap)


def estimate_buy_zone(latest_price: float, ma10: float, ma20: float, ma50: float) -> tuple[float, float, float]:
    upper = min(latest_price * 0.995, max(ma10, ma20))
    lower = min(ma10, ma20)
    if upper < lower:
        lower, upper = upper, lower
    stop_reference = ma50 * 0.98
    return float(lower), float(upper), float(stop_reference)


def scan_assets(
    assets: Iterable[AssetRequest],
    provider: MarketDataProvider,
    market_cap_min: int = DEFAULT_MARKET_CAP_MIN,
    weekly_turnover_min: float = DEFAULT_WEEKLY_TURNOVER_MIN,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for asset in assets:
        market_cap = provider.market_cap(asset.symbol)
        if market_cap is None or market_cap <= market_cap_min:
            continue

        daily = provider.history(asset.symbol, period="1y", interval="1d")
        turnover = weekly_turnover_rate(daily, market_cap, asset.asset_type)
        if turnover is None or turnover < weekly_turnover_min:
            continue

        has_recent_high, high_52w, high_date = recent_52_week_high(daily)
        if not has_recent_high or high_date is None:
            continue

        four_hour = provider.history(asset.symbol, period="90d", interval="4h")
        above_mas, latest, ma10, ma20, ma50 = moving_average_snapshot(four_hour)
        if not above_mas:
            continue

        buy_low, buy_high, stop_reference = estimate_buy_zone(latest, ma10, ma20, ma50)
        candidates.append(
            Candidate(
                symbol=asset.symbol,
                asset_type=asset.asset_type,
                latest_price=round(latest, 4),
                market_cap=int(market_cap),
                weekly_turnover_pct=round(turnover * 100, 4),
                high_52w=round(high_52w, 4),
                high_52w_date=high_date.date().isoformat(),
                ma10_4h=round(ma10, 4),
                ma20_4h=round(ma20, 4),
                ma50_4h=round(ma50, 4),
                buy_zone_low=round(buy_low, 4),
                buy_zone_high=round(buy_high, 4),
                stop_reference=round(stop_reference, 4),
            )
        )
    return candidates


def plot_crypto_candidate(
    candidate: Candidate,
    provider: MarketDataProvider,
    output_dir: Path,
) -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)
    df = normalize_history(provider.history(candidate.symbol, period="90d", interval="4h"))
    if "close" not in df:
        return ""
    chart = df.tail(140).copy()
    chart["ma10"] = chart["close"].rolling(10).mean()
    chart["ma20"] = chart["close"].rolling(20).mean()
    chart["ma50"] = chart["close"].rolling(50).mean()

    fig, ax = plt.subplots(figsize=(12, 7))
    ax.plot(chart.index, chart["close"], label="4h close", linewidth=1.8)
    ax.plot(chart.index, chart["ma10"], label="MA10", linewidth=1.1)
    ax.plot(chart.index, chart["ma20"], label="MA20", linewidth=1.1)
    ax.plot(chart.index, chart["ma50"], label="MA50", linewidth=1.1)
    ax.axhline(candidate.high_52w, color="tab:purple", linestyle="--", linewidth=1, label="52-week high")
    ax.axhspan(candidate.buy_zone_low, candidate.buy_zone_high, color="tab:green", alpha=0.16, label="potential buy zone")
    ax.axhline(candidate.stop_reference, color="tab:red", linestyle=":", linewidth=1, label="stop reference")
    ax.set_title(f"{candidate.symbol} 4h setup: price above MA10/MA20/MA50")
    ax.set_ylabel("Price")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.25)
    ax.text(
        0.01,
        0.02,
        f"Approx. buy zone: {candidate.buy_zone_low:.4f} - {candidate.buy_zone_high:.4f}\n"
        f"Latest: {candidate.latest_price:.4f} | 52w high date: {candidate.high_52w_date}",
        transform=ax.transAxes,
        bbox={"facecolor": "white", "alpha": 0.78, "edgecolor": "none"},
    )
    fig.autofmt_xdate()
    fig.tight_layout()

    path = output_dir / f"{candidate.symbol.replace('-', '_').replace('.', '_')}_setup.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return str(path)


def write_candidates_csv(candidates: list[Candidate], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "candidates.csv"
    rows = [asdict(candidate) for candidate in candidates]
    columns = [field.name for field in fields(Candidate)]
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)
    return path


def parse_symbols(value: str, defaults: tuple[str, ...]) -> list[str]:
    if not value:
        return list(defaults)
    return [symbol.strip().upper() for symbol in value.split(",") if symbol.strip()]


def build_assets(crypto_symbols: Iterable[str], stock_symbols: Iterable[str]) -> list[AssetRequest]:
    return [*(AssetRequest(symbol, "crypto") for symbol in crypto_symbols), *(AssetRequest(symbol, "stock") for symbol in stock_symbols)]


def print_summary(candidates: list[Candidate], csv_path: Path) -> None:
    if not candidates:
        print(f"No candidates matched. Empty CSV written to {csv_path}")
        return
    print(f"Candidates written to {csv_path}")
    for candidate in candidates:
        chart_note = f", chart={candidate.chart_path}" if candidate.chart_path else ""
        print(
            f"{candidate.symbol} ({candidate.asset_type}) latest={candidate.latest_price} "
            f"buy_zone={candidate.buy_zone_low}-{candidate.buy_zone_high} "
            f"weekly_turnover={candidate.weekly_turnover_pct}% "
            f"market_cap={candidate.market_cap}{chart_note}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan crypto and US stocks for recent 52-week highs and 4h MA strength.")
    parser.add_argument("--crypto", default=",".join(DEFAULT_CRYPTO_SYMBOLS), help="Comma-separated Yahoo Finance crypto symbols.")
    parser.add_argument("--stocks", default=",".join(DEFAULT_US_STOCK_SYMBOLS), help="Comma-separated Yahoo Finance US stock symbols.")
    parser.add_argument("--market-cap-min", type=int, default=DEFAULT_MARKET_CAP_MIN, help="Minimum market cap in USD.")
    parser.add_argument("--weekly-turnover-min", type=float, default=DEFAULT_WEEKLY_TURNOVER_MIN, help="Minimum 7-day turnover rate as a decimal, e.g. 0.05 for 5%.")
    parser.add_argument("--output-dir", default="scanner_output", help="Directory for CSV and crypto charts.")
    parser.add_argument("--sample-data", action="store_true", help="Use deterministic sample data instead of live Yahoo Finance data.")
    parser.add_argument("--no-plots", action="store_true", help="Skip crypto chart generation.")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")

    crypto_symbols = parse_symbols(args.crypto, DEFAULT_CRYPTO_SYMBOLS)
    stock_symbols = parse_symbols(args.stocks, DEFAULT_US_STOCK_SYMBOLS)
    provider: MarketDataProvider = SampleMarketDataProvider() if args.sample_data else YahooFinanceProvider()
    output_dir = Path(args.output_dir)

    candidates = scan_assets(
        build_assets(crypto_symbols, stock_symbols),
        provider,
        market_cap_min=args.market_cap_min,
        weekly_turnover_min=args.weekly_turnover_min,
    )
    if not args.no_plots:
        updated: list[Candidate] = []
        for candidate in candidates:
            if candidate.asset_type != "crypto":
                updated.append(candidate)
                continue
            chart_path = plot_crypto_candidate(candidate, provider, output_dir)
            updated.append(Candidate(**{**asdict(candidate), "chart_path": chart_path}))
        candidates = updated

    csv_path = write_candidates_csv(candidates, output_dir)
    print_summary(candidates, csv_path)
    print("Not financial advice. Use this as a watchlist generator and validate risk before trading.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
