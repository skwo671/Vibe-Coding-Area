from __future__ import annotations

import argparse
import logging
import os
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import pandas as pd
import requests

from .crypto_indicators import CryptoAlert, detect_crypto_alerts, enrich_crypto_indicators, plot_crypto_technical_chart, write_crypto_alerts_csv
from .market_scanner import (
    DEFAULT_MARKET_CAP_MIN,
    estimate_buy_zone,
    moving_average_snapshot,
    normalize_history,
    recent_52_week_high,
    weekly_turnover_rate,
)

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
FINNHUB_BASE = "https://finnhub.io/api/v1"
DEFAULT_CRYPTO_UNIVERSE_SIZE = 500
DEFAULT_STOCK_UNIVERSE_SIZE = 500
DEFAULT_CRYPTO_DEEP_SCAN_LIMIT = 40
REQUEST_PAUSE_SECONDS = 2.5
MAX_REQUEST_RETRIES = 4


@dataclass(frozen=True)
class UniverseAsset:
    symbol: str
    name: str
    asset_type: str
    platform: str
    market_cap: int
    external_id: str = ""
    volume_24h_usd: float = 0.0


@dataclass(frozen=True)
class PlatformCandidate:
    symbol: str
    name: str
    asset_type: str
    platform: str
    data_source: str
    timeframe: str
    latest_price: float
    market_cap: int
    weekly_turnover_pct: float
    high_52w: float
    high_52w_date: str
    ma20: float
    ma50: float
    buy_zone_low: float
    buy_zone_high: float
    stop_reference: float
    external_id: str = ""
    chart_path: str = ""


def rough_weekly_turnover_pct(market_cap: int, volume_24h_usd: float) -> float:
    if market_cap <= 0:
        return 0.0
    return (volume_24h_usd * 7 / market_cap) * 100


def ohlc_rows_to_frame(rows: list[list[float]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close"])
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    frame = frame.set_index("timestamp")
    frame["volume"] = 0.0
    return frame


def market_chart_to_daily_frame(prices: list[list[float]], volumes: list[list[float]]) -> pd.DataFrame:
    if not prices:
        return pd.DataFrame()
    frame = pd.DataFrame(prices, columns=["timestamp", "close"])
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    frame = frame.set_index("timestamp")
    if volumes:
        volume_frame = pd.DataFrame(volumes, columns=["timestamp", "volume"])
        volume_frame["timestamp"] = pd.to_datetime(volume_frame["timestamp"], unit="ms", utc=True)
        frame = frame.join(volume_frame.set_index("timestamp"), how="left")
    else:
        frame["volume"] = 0.0
    frame["open"] = frame["close"]
    frame["high"] = frame["close"]
    frame["low"] = frame["close"]
    return frame[["open", "high", "low", "close", "volume"]]


class CoinGeckoClient:
    def __init__(self, pause_seconds: float = REQUEST_PAUSE_SECONDS) -> None:
        self.pause_seconds = pause_seconds
        self.log = logging.getLogger("coingecko")
        self._market_cache: list[UniverseAsset] | None = None

    def _get(self, path: str, params: dict | None = None) -> object:
        last_error: Exception | None = None
        for attempt in range(MAX_REQUEST_RETRIES):
            time.sleep(self.pause_seconds * (attempt + 1))
            try:
                response = requests.get(f"{COINGECKO_BASE}{path}", params=params or {}, timeout=30)
                if response.status_code == 429:
                    last_error = requests.HTTPError("429 Too Many Requests", response=response)
                    continue
                response.raise_for_status()
                return response.json()
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"CoinGecko request failed for {path}")

    def fetch_top_markets(self, limit: int = DEFAULT_CRYPTO_UNIVERSE_SIZE) -> list[UniverseAsset]:
        if self._market_cache is not None and len(self._market_cache) >= limit:
            return self._market_cache[:limit]

        assets: list[UniverseAsset] = []
        pages = (limit + 249) // 250
        for page in range(1, pages + 1):
            per_page = min(250, limit - len(assets))
            if per_page <= 0:
                break
            payload = self._get(
                "/coins/markets",
                {
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": per_page,
                    "page": page,
                    "sparkline": "false",
                },
            )
            for item in payload:
                market_cap = int(item.get("market_cap") or 0)
                if market_cap <= 0:
                    continue
                assets.append(
                    UniverseAsset(
                        symbol=str(item["symbol"]).upper(),
                        name=str(item.get("name") or item["symbol"]),
                        asset_type="crypto",
                        platform="coingecko",
                        market_cap=market_cap,
                        external_id=str(item["id"]),
                        volume_24h_usd=float(item.get("total_volume") or 0.0),
                    )
                )
        self._market_cache = assets
        return assets[:limit]

    def fetch_daily_history(self, asset: UniverseAsset) -> pd.DataFrame:
        if not asset.external_id:
            return pd.DataFrame()
        try:
            ohlc = self._get(f"/coins/{asset.external_id}/ohlc", {"vs_currency": "usd", "days": 365})
            frame = ohlc_rows_to_frame(ohlc)
            if frame.empty:
                return pd.DataFrame()
            chart = self._get(
                f"/coins/{asset.external_id}/market_chart",
                {"vs_currency": "usd", "days": 30, "interval": "daily"},
            )
            volume_frame = market_chart_to_daily_frame(chart.get("prices", []), chart.get("total_volumes", []))
            if "volume" in frame.columns:
                frame = frame.drop(columns=["volume"])
            merged = frame.join(volume_frame[["volume"]], how="left")
            merged["volume"] = merged["volume"].fillna(0.0)
            return merged
        except Exception as exc:
            self.log.warning("CoinGecko history failed for %s: %s", asset.symbol, exc)
            return pd.DataFrame()


class FinnhubClient:
    def __init__(self, api_key: str, pause_seconds: float = 0.2) -> None:
        self.api_key = api_key
        self.pause_seconds = pause_seconds
        self.log = logging.getLogger("finnhub")

    def _get(self, path: str, params: dict | None = None) -> object:
        time.sleep(self.pause_seconds)
        query = {"token": self.api_key, **(params or {})}
        response = requests.get(f"{FINNHUB_BASE}{path}", params=query, timeout=30)
        response.raise_for_status()
        return response.json()

    def fetch_us_universe(self, market_cap_min: int, limit: int = DEFAULT_STOCK_UNIVERSE_SIZE) -> list[UniverseAsset]:
        payload = self._get(
            "/stock/screener",
            {
                "exchange": "US",
                "marketCapMoreThan": market_cap_min,
            },
        )
        assets: list[UniverseAsset] = []
        for item in payload:
            market_cap = int(float(item.get("marketCapitalization", 0)) * 1_000_000)
            symbol = str(item.get("symbol") or "").upper()
            if not symbol or market_cap <= market_cap_min:
                continue
            assets.append(
                UniverseAsset(
                    symbol=symbol,
                    name=str(item.get("description") or symbol),
                    asset_type="stock",
                    platform="finnhub",
                    market_cap=market_cap,
                    external_id=symbol,
                )
            )
            if len(assets) >= limit:
                break
        return assets

    def fetch_daily_history(self, asset: UniverseAsset) -> pd.DataFrame:
        now = int(time.time())
        start = now - 365 * 24 * 60 * 60
        try:
            payload = self._get(
                "/stock/candle",
                {
                    "symbol": asset.symbol,
                    "resolution": "D",
                    "from": start,
                    "to": now,
                },
            )
            if payload.get("s") != "ok":
                return pd.DataFrame()
            frame = pd.DataFrame(
                {
                    "timestamp": payload["t"],
                    "open": payload["o"],
                    "high": payload["h"],
                    "low": payload["l"],
                    "close": payload["c"],
                    "volume": payload["v"],
                }
            )
            frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="s", utc=True)
            return frame.set_index("timestamp")
        except Exception as exc:
            self.log.warning("Finnhub history failed for %s: %s", asset.symbol, exc)
            return pd.DataFrame()


class YahooFallbackStockClient:
    def __init__(self) -> None:
        import yfinance as yf

        self._yf = yf
        self.log = logging.getLogger("yahoo-fallback")

    def fetch_us_universe(self, market_cap_min: int, limit: int = DEFAULT_STOCK_UNIVERSE_SIZE) -> list[UniverseAsset]:
        symbols = self._load_sp500_symbols()
        if not symbols:
            from .market_scanner import DEFAULT_US_STOCK_SYMBOLS

            symbols = list(DEFAULT_US_STOCK_SYMBOLS)
            self.log.warning("Using built-in US stock fallback list (%s symbols).", len(symbols))

        assets: list[UniverseAsset] = []
        for symbol in symbols[:limit]:
            market_cap = self.market_cap(symbol)
            if market_cap is None or market_cap <= market_cap_min:
                continue
            assets.append(
                UniverseAsset(
                    symbol=symbol,
                    name=symbol,
                    asset_type="stock",
                    platform="yahoo",
                    market_cap=market_cap,
                    external_id=symbol,
                )
            )
        return assets

    def _load_sp500_symbols(self) -> list[str]:
        try:
            headers = {"User-Agent": "VibeCodingMarketScanner/1.0 (contact: local)"}
            response = requests.get(
                "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            tables = pd.read_html(response.text)
            return [str(symbol).replace(".", "-") for symbol in tables[0]["Symbol"].tolist()]
        except Exception as exc:
            self.log.warning("Failed to load S&P 500 list: %s", exc)
            return []

    def market_cap(self, symbol: str) -> int | None:
        ticker = self._yf.Ticker(symbol)
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

    def fetch_daily_history(self, asset: UniverseAsset) -> pd.DataFrame:
        try:
            history = self._yf.Ticker(asset.symbol).history(period="1y", interval="1d", auto_adjust=False, actions=False)
            return normalize_history(history)
        except Exception as exc:
            self.log.warning("Yahoo history failed for %s: %s", asset.symbol, exc)
            return pd.DataFrame()


def evaluate_daily_candidate(
    asset: UniverseAsset,
    daily_history: pd.DataFrame,
    data_source: str,
    market_cap_min: int = DEFAULT_MARKET_CAP_MIN,
    weekly_turnover_min: float = 0.03,
) -> PlatformCandidate | None:
    market_cap = asset.market_cap
    if market_cap <= market_cap_min:
        return None

    turnover = weekly_turnover_rate(daily_history, market_cap, asset.asset_type)
    if turnover is None or turnover < weekly_turnover_min:
        return None

    has_recent_high, high_52w, high_date = recent_52_week_high(daily_history)
    if not has_recent_high or high_date is None:
        return None

    above_mas, latest, ma10, ma20, ma50 = moving_average_snapshot(daily_history)
    if not above_mas:
        return None

    buy_low, buy_high, stop_reference = estimate_buy_zone(latest, ma10, ma20, ma50)
    return PlatformCandidate(
        symbol=asset.symbol,
        name=asset.name,
        asset_type=asset.asset_type,
        platform=asset.platform,
        data_source=data_source,
        timeframe="1d",
        latest_price=round(latest, 4),
        market_cap=int(market_cap),
        weekly_turnover_pct=round(turnover * 100, 4),
        high_52w=round(high_52w, 4),
        high_52w_date=high_date.date().isoformat(),
        ma20=round(ma20, 4),
        ma50=round(ma50, 4),
        buy_zone_low=round(buy_low, 4),
        buy_zone_high=round(buy_high, 4),
        stop_reference=round(stop_reference, 4),
        external_id=asset.external_id,
    )


def scan_crypto_platform(
    client: CoinGeckoClient,
    market_cap_min: int = DEFAULT_MARKET_CAP_MIN,
    weekly_turnover_min: float = 0.03,
    universe_size: int = DEFAULT_CRYPTO_UNIVERSE_SIZE,
    deep_scan_limit: int = DEFAULT_CRYPTO_DEEP_SCAN_LIMIT,
    chart_dir: Path | None = None,
) -> tuple[list[PlatformCandidate], list[CryptoAlert]]:
    log = logging.getLogger("platform.crypto")
    universe = client.fetch_top_markets(universe_size)
    prefiltered = [
        asset
        for asset in universe
        if asset.market_cap > market_cap_min and rough_weekly_turnover_pct(asset.market_cap, asset.volume_24h_usd) >= weekly_turnover_min * 100
    ]
    prefiltered.sort(key=lambda asset: rough_weekly_turnover_pct(asset.market_cap, asset.volume_24h_usd), reverse=True)
    scan_list = prefiltered[:deep_scan_limit]
    log.info("CoinGecko deep-scan list: %s/%s symbols (from %s universe)", len(scan_list), len(prefiltered), len(universe))

    candidates: list[PlatformCandidate] = []
    alerts = []
    for index, asset in enumerate(scan_list, start=1):
        daily = client.fetch_daily_history(asset)
        if daily.empty:
            continue

        chart_path = ""
        if chart_dir is not None:
            chart_path = plot_crypto_technical_chart(asset.symbol, daily, chart_dir)
            indicator_frame = enrich_crypto_indicators(daily)
            alerts.extend(detect_crypto_alerts(asset.symbol, indicator_frame))

        candidate = evaluate_daily_candidate(
            asset,
            daily,
            data_source="coingecko",
            market_cap_min=market_cap_min,
            weekly_turnover_min=weekly_turnover_min,
        )
        if candidate is None:
            continue
        candidates.append(PlatformCandidate(**{**asdict(candidate), "chart_path": chart_path}))
        log.info("Crypto match %s (%s/%s)", asset.symbol, index, len(scan_list))
    return candidates, alerts


def scan_us_stocks_platform(
    finnhub_client: FinnhubClient | None,
    yahoo_client: YahooFallbackStockClient,
    market_cap_min: int = DEFAULT_MARKET_CAP_MIN,
    weekly_turnover_min: float = 0.03,
    universe_size: int = DEFAULT_STOCK_UNIVERSE_SIZE,
    chart_dir: Path | None = None,
) -> tuple[list[PlatformCandidate], str]:
    log = logging.getLogger("platform.stocks")
    if finnhub_client is not None:
        universe = finnhub_client.fetch_us_universe(market_cap_min, universe_size)
        data_source = "finnhub"
        history_client = finnhub_client
        platform_name = "finnhub"
    else:
        universe = yahoo_client.fetch_us_universe(market_cap_min, universe_size)
        data_source = "yahoo"
        history_client = yahoo_client
        platform_name = "yahoo"
        log.warning("FINNHUB_API_KEY not set; using Yahoo Finance fallback for US stocks.")

    log.info("US stock universe from %s: %s symbols", platform_name, len(universe))
    candidates: list[PlatformCandidate] = []
    for index, asset in enumerate(universe, start=1):
        daily = history_client.fetch_daily_history(asset)
        candidate = evaluate_daily_candidate(
            asset,
            daily,
            data_source=data_source,
            market_cap_min=market_cap_min,
            weekly_turnover_min=weekly_turnover_min,
        )
        if candidate is None:
            continue
        chart_path = ""
        if chart_dir is not None:
            chart_path = plot_daily_candidate(candidate, daily, chart_dir)
        candidates.append(PlatformCandidate(**{**asdict(candidate), "chart_path": chart_path}))
        log.info("Stock match %s (%s/%s)", asset.symbol, index, len(universe))
    return candidates, platform_name


def plot_daily_candidate(candidate: PlatformCandidate, daily_history: pd.DataFrame, output_dir: Path) -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)
    chart = normalize_history(daily_history).tail(180).copy()
    if chart.empty or "close" not in chart:
        return ""

    chart["ma20"] = chart["close"].rolling(20).mean()
    chart["ma50"] = chart["close"].rolling(50).mean()

    fig, ax = plt.subplots(figsize=(12, 7))
    ax.plot(chart.index, chart["close"], label="Daily close", linewidth=1.8)
    ax.plot(chart.index, chart["ma20"], label="MA20", linewidth=1.1)
    ax.plot(chart.index, chart["ma50"], label="MA50", linewidth=1.1)
    ax.axhline(candidate.high_52w, color="tab:purple", linestyle="--", linewidth=1, label="52-week high")
    ax.axhspan(candidate.buy_zone_low, candidate.buy_zone_high, color="tab:green", alpha=0.16, label="potential buy zone")
    ax.axhline(candidate.stop_reference, color="tab:red", linestyle=":", linewidth=1, label="stop reference")
    ax.set_title(f"{candidate.symbol} daily setup via {candidate.platform}")
    ax.set_ylabel("Price")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.25)
    ax.text(
        0.01,
        0.02,
        f"Buy zone: {candidate.buy_zone_low:.4f} - {candidate.buy_zone_high:.4f}\n"
        f"Latest: {candidate.latest_price:.4f} | Turnover: {candidate.weekly_turnover_pct:.2f}%",
        transform=ax.transAxes,
        bbox={"facecolor": "white", "alpha": 0.78, "edgecolor": "none"},
    )
    fig.autofmt_xdate()
    fig.tight_layout()

    safe_symbol = candidate.symbol.replace("-", "_").replace(".", "_")
    path = output_dir / f"{safe_symbol}_daily.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return str(path)


def write_platform_csv(candidates: list[PlatformCandidate], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = [field.name for field in fields(PlatformCandidate)]
    rows = [asdict(candidate) for candidate in candidates]
    pd.DataFrame(rows, columns=columns).to_csv(output_path, index=False)
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan crypto via CoinGecko and US stocks via Finnhub/Yahoo on daily candles.")
    parser.add_argument("--output-dir", default="platform_output", help="Directory for split CSVs and charts.")
    parser.add_argument("--market-cap-min", type=int, default=DEFAULT_MARKET_CAP_MIN)
    parser.add_argument("--weekly-turnover-min", type=float, default=0.03)
    parser.add_argument("--crypto-universe-size", type=int, default=DEFAULT_CRYPTO_UNIVERSE_SIZE)
    parser.add_argument("--crypto-deep-scan-limit", type=int, default=DEFAULT_CRYPTO_DEEP_SCAN_LIMIT)
    parser.add_argument("--stock-universe-size", type=int, default=DEFAULT_STOCK_UNIVERSE_SIZE)
    parser.add_argument("--no-plots", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")
    output_dir = Path(args.output_dir)
    crypto_csv = output_dir / "crypto_candidates.csv"
    stock_csv = output_dir / "us_stocks_candidates.csv"
    crypto_chart_dir = None if args.no_plots else output_dir / "crypto_charts"
    stock_chart_dir = None if args.no_plots else output_dir / "us_stock_charts"

    coingecko = CoinGeckoClient()
    yahoo = YahooFallbackStockClient()
    finnhub_key = os.getenv("FINNHUB_API_KEY", "").strip()
    finnhub = FinnhubClient(finnhub_key) if finnhub_key else None

    crypto_candidates, crypto_alerts = scan_crypto_platform(
        coingecko,
        market_cap_min=args.market_cap_min,
        weekly_turnover_min=args.weekly_turnover_min,
        universe_size=args.crypto_universe_size,
        deep_scan_limit=args.crypto_deep_scan_limit,
        chart_dir=crypto_chart_dir,
    )
    stock_candidates, stock_platform = scan_us_stocks_platform(
        finnhub,
        yahoo,
        market_cap_min=args.market_cap_min,
        weekly_turnover_min=args.weekly_turnover_min,
        universe_size=args.stock_universe_size,
        chart_dir=stock_chart_dir,
    )

    write_platform_csv(crypto_candidates, crypto_csv)
    write_platform_csv(stock_candidates, stock_csv)
    write_crypto_alerts_csv(crypto_alerts, output_dir / "crypto_alerts.csv")

    settings_path = output_dir / "scan_settings.txt"
    settings_path.write_text(
        "\n".join(
            [
                f"Crypto platform: coingecko",
                f"US stock platform: {stock_platform}",
                f"Timeframe: daily (1d)",
                f"Market cap minimum: {args.market_cap_min:,} USD",
                f"Weekly turnover minimum: {args.weekly_turnover_min * 100:.1f}%",
                f"Crypto universe size: {args.crypto_universe_size}",
                f"Crypto deep-scan limit: {args.crypto_deep_scan_limit}",
                f"US stock universe size: {args.stock_universe_size}",
                f"Crypto candidates: {len(crypto_candidates)}",
                f"Crypto alerts: {len(crypto_alerts)}",
                f"US stock candidates: {len(stock_candidates)}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Crypto candidates: {len(crypto_candidates)} -> {crypto_csv}")
    for candidate in crypto_candidates:
        print(
            f"  {candidate.symbol} latest={candidate.latest_price} turnover={candidate.weekly_turnover_pct}% "
            f"buy_zone={candidate.buy_zone_low}-{candidate.buy_zone_high}"
        )
    print(f"Crypto alerts: {len(crypto_alerts)} -> {output_dir / 'crypto_alerts.csv'}")
    for alert in crypto_alerts:
        print(f"  {alert.symbol} {alert.alert_type}: {alert.message} ({alert.value:.4f})")
    print(f"US stock candidates: {len(stock_candidates)} -> {stock_csv} (platform={stock_platform})")
    for candidate in stock_candidates:
        print(
            f"  {candidate.symbol} latest={candidate.latest_price} turnover={candidate.weekly_turnover_pct}% "
            f"buy_zone={candidate.buy_zone_low}-{candidate.buy_zone_high}"
        )
    print("Not financial advice. Use this as a watchlist generator and validate risk before trading.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
