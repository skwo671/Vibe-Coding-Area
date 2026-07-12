from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from pathlib import Path

import numpy as np
import pandas as pd

from .asset_display import AssetDisplayInfo, add_logo_to_axes, configure_cjk_font, format_chart_title
from .market_scanner import estimate_buy_zone, normalize_history

EMA_FAST = 20
EMA_MID = 50
EMA_SLOW = 200
RSI_LENGTH = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
BB_LENGTH = 20
BB_STD = 2.0
OBV_EMA_LENGTH = 21
BB_SQUEEZE_LOOKBACK = 120
BB_SQUEEZE_PERCENTILE = 0.20


@dataclass(frozen=True)
class CryptoAlert:
    symbol: str
    alert_type: str
    message: str
    triggered_at: str
    value: float


@dataclass(frozen=True)
class CryptoChartSummary:
    symbol: str
    latest_price: float
    ema20: float
    ema50: float
    buy_zone_low: float
    buy_zone_high: float
    stop_reference: float
    name_zh: str = ""
    name_en: str = ""
    chart_path: str = ""


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.astype(float).ewm(span=length, adjust=False).mean()


def rsi(series: pd.Series, length: int = RSI_LENGTH) -> pd.Series:
    delta = series.astype(float).diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    relative_strength = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + relative_strength))


def bollinger_bands(series: pd.Series, length: int = BB_LENGTH, std_dev: float = BB_STD) -> tuple[pd.Series, pd.Series, pd.Series]:
    middle = series.astype(float).rolling(length).mean()
    deviation = series.astype(float).rolling(length).std()
    upper = middle + std_dev * deviation
    lower = middle - std_dev * deviation
    return middle, upper, lower


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.astype(float).diff().fillna(0.0))
    signed_volume = direction * volume.astype(float).fillna(0.0)
    return signed_volume.cumsum()


def bollinger_bandwidth(upper: pd.Series, lower: pd.Series, middle: pd.Series) -> pd.Series:
    return (upper - lower) / middle.replace(0, np.nan)


def enrich_crypto_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    chart = normalize_history(frame).copy()
    if chart.empty or "close" not in chart:
        return chart
    if "volume" not in chart:
        chart["volume"] = 0.0

    close = chart["close"].astype(float)
    chart["ema20"] = ema(close, EMA_FAST)
    chart["ema50"] = ema(close, EMA_MID)
    chart["ema200"] = ema(close, EMA_SLOW)
    chart["rsi14"] = rsi(close, RSI_LENGTH)
    bb_middle, bb_upper, bb_lower = bollinger_bands(close, BB_LENGTH, BB_STD)
    chart["bb_middle"] = bb_middle
    chart["bb_upper"] = bb_upper
    chart["bb_lower"] = bb_lower
    chart["bb_bandwidth"] = bollinger_bandwidth(bb_upper, bb_lower, bb_middle)
    chart["obv"] = obv(close, chart["volume"])
    chart["obv_ema21"] = ema(chart["obv"], OBV_EMA_LENGTH)
    return chart


def compute_crypto_buy_zone(chart: pd.DataFrame) -> tuple[float, float, float, float, float, float] | None:
    if chart.empty or len(chart) < EMA_MID:
        return None
    latest_row = chart.iloc[-1]
    if any(pd.isna(latest_row[column]) for column in ("close", "ema20", "ema50")):
        return None
    latest = float(latest_row["close"])
    ema20 = float(latest_row["ema20"])
    ema50 = float(latest_row["ema50"])
    buy_low, buy_high, stop_reference = estimate_buy_zone(latest, ema20, ema20, ema50)
    return latest, ema20, ema50, buy_low, buy_high, stop_reference


def _latest_timestamp(index: pd.Index) -> str:
    if len(index) == 0:
        return ""
    return pd.Timestamp(index[-1]).isoformat()


def detect_crypto_alerts(symbol: str, chart: pd.DataFrame) -> list[CryptoAlert]:
    if len(chart) < max(BB_LENGTH, EMA_SLOW, RSI_LENGTH) + 2:
        return []

    alerts: list[CryptoAlert] = []
    triggered_at = _latest_timestamp(chart.index)
    latest = chart.iloc[-1]
    previous = chart.iloc[-2]

    if pd.notna(latest["ema20"]) and pd.notna(latest["ema50"]) and pd.notna(previous["ema20"]) and pd.notna(previous["ema50"]):
        if previous["ema20"] <= previous["ema50"] and latest["ema20"] > latest["ema50"]:
            alerts.append(
                CryptoAlert(
                    symbol=symbol,
                    alert_type="ema_cross_bullish",
                    message="EMA 20 crossed above EMA 50",
                    triggered_at=triggered_at,
                    value=float(latest["ema20"] - latest["ema50"]),
                )
            )
        elif previous["ema20"] >= previous["ema50"] and latest["ema20"] < latest["ema50"]:
            alerts.append(
                CryptoAlert(
                    symbol=symbol,
                    alert_type="ema_cross_bearish",
                    message="EMA 20 crossed below EMA 50",
                    triggered_at=triggered_at,
                    value=float(latest["ema20"] - latest["ema50"]),
                )
            )

    bandwidth = chart["bb_bandwidth"].dropna()
    if not bandwidth.empty:
        current = float(bandwidth.iloc[-1])
        history = bandwidth.tail(BB_SQUEEZE_LOOKBACK)
        threshold = float(history.quantile(BB_SQUEEZE_PERCENTILE))
        if current <= threshold:
            alerts.append(
                CryptoAlert(
                    symbol=symbol,
                    alert_type="bb_squeeze",
                    message="Bollinger Band squeeze detected",
                    triggered_at=triggered_at,
                    value=current,
                )
            )

    if pd.notna(latest["rsi14"]):
        current_rsi = float(latest["rsi14"])
        previous_rsi = float(previous["rsi14"]) if pd.notna(previous["rsi14"]) else current_rsi
        if previous_rsi < RSI_OVERBOUGHT <= current_rsi:
            alerts.append(
                CryptoAlert(
                    symbol=symbol,
                    alert_type="rsi_overbought",
                    message="RSI entered overbought zone (>= 70)",
                    triggered_at=triggered_at,
                    value=current_rsi,
                )
            )
        if previous_rsi > RSI_OVERSOLD >= current_rsi:
            alerts.append(
                CryptoAlert(
                    symbol=symbol,
                    alert_type="rsi_oversold",
                    message="RSI entered oversold zone (<= 30)",
                    triggered_at=triggered_at,
                    value=current_rsi,
                )
            )

    return alerts


def plot_crypto_technical_chart(
    symbol: str,
    daily_history: pd.DataFrame,
    output_dir: Path,
    display: AssetDisplayInfo | None = None,
) -> CryptoChartSummary | None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    configure_cjk_font()
    output_dir.mkdir(parents=True, exist_ok=True)
    chart = enrich_crypto_indicators(daily_history).tail(180)
    if chart.empty or "close" not in chart:
        return None

    buy_zone = compute_crypto_buy_zone(chart)
    if buy_zone is None:
        return None
    latest, ema20, ema50, buy_low, buy_high, stop_reference = buy_zone

    name_zh = display.name_zh if display else symbol
    name_en = display.name_en if display else symbol
    logo_url = display.logo_url if display else ""

    fig, axes = plt.subplots(3, 1, figsize=(13, 11), sharex=True, gridspec_kw={"height_ratios": [3, 1.2, 1.2]})
    price_ax, rsi_ax, obv_ax = axes

    add_logo_to_axes(price_ax, logo_url)
    price_ax.plot(chart.index, chart["close"], label="Close", color="black", linewidth=1.5)
    price_ax.plot(chart.index, chart["ema20"], label="EMA 20", color="green", linewidth=1.2)
    price_ax.plot(chart.index, chart["ema50"], label="EMA 50", color="orange", linewidth=1.2)
    price_ax.plot(chart.index, chart["ema200"], label="EMA 200", color="red", linewidth=2.2)
    price_ax.plot(chart.index, chart["bb_middle"], label="BB Middle", color="steelblue", linewidth=1.0, alpha=0.8)
    price_ax.plot(chart.index, chart["bb_upper"], label="BB Upper", color="steelblue", linewidth=0.9, linestyle="--")
    price_ax.plot(chart.index, chart["bb_lower"], label="BB Lower", color="steelblue", linewidth=0.9, linestyle="--")
    price_ax.fill_between(chart.index, chart["bb_lower"], chart["bb_upper"], color="steelblue", alpha=0.12)
    price_ax.axhspan(buy_low, buy_high, color="tab:green", alpha=0.18, label="potential buy zone")
    price_ax.axhline(stop_reference, color="tab:red", linestyle=":", linewidth=1.2, label="stop reference")

    overbought_hits = chart.index[chart["rsi14"] >= RSI_OVERBOUGHT]
    oversold_hits = chart.index[chart["rsi14"] <= RSI_OVERSOLD]
    if len(overbought_hits):
        price_ax.scatter(overbought_hits, chart.loc[overbought_hits, "close"], color="red", marker="v", s=36, label="RSI overbought")
    if len(oversold_hits):
        price_ax.scatter(oversold_hits, chart.loc[oversold_hits, "close"], color="green", marker="^", s=36, label="RSI oversold")

    price_ax.set_title(format_chart_title(symbol, name_zh, name_en, "加密貨幣日線技術分析"))
    price_ax.set_ylabel("Price")
    price_ax.grid(True, alpha=0.25)
    price_ax.legend(loc="upper right", fontsize=8)
    price_ax.text(
        0.01,
        0.02,
        f"Buy zone: {buy_low:.6f} - {buy_high:.6f}\n"
        f"Latest: {latest:.6f} | Stop ref: {stop_reference:.6f}",
        transform=price_ax.transAxes,
        bbox={"facecolor": "white", "alpha": 0.82, "edgecolor": "none"},
        fontsize=9,
    )

    rsi_ax.plot(chart.index, chart["rsi14"], label="RSI 14", color="purple", linewidth=1.2)
    rsi_ax.axhline(RSI_OVERBOUGHT, color="red", linestyle="--", linewidth=1)
    rsi_ax.axhline(RSI_OVERSOLD, color="green", linestyle="--", linewidth=1)
    rsi_ax.fill_between(chart.index, RSI_OVERBOUGHT, 100, color="red", alpha=0.08)
    rsi_ax.fill_between(chart.index, 0, RSI_OVERSOLD, color="green", alpha=0.08)
    rsi_ax.set_ylim(0, 100)
    rsi_ax.set_ylabel("RSI")
    rsi_ax.grid(True, alpha=0.25)

    obv_ax.plot(chart.index, chart["obv"], label="OBV", color="tab:blue", linewidth=1.2)
    obv_ax.plot(chart.index, chart["obv_ema21"], label="OBV EMA 21", color="darkorange", linewidth=1.1)
    obv_ax.set_ylabel("OBV")
    obv_ax.grid(True, alpha=0.25)
    obv_ax.legend(loc="upper right", fontsize=8)

    alerts = detect_crypto_alerts(symbol, chart)
    if alerts:
        alert_text = " | ".join(alert.message for alert in alerts[-3:])
        fig.text(0.01, 0.01, f"Alerts: {alert_text}", fontsize=9)

    fig.autofmt_xdate()
    fig.tight_layout()
    safe_symbol = symbol.replace("-", "_").replace(".", "_")
    path = output_dir / f"{safe_symbol}_technical.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return CryptoChartSummary(
        symbol=symbol,
        name_zh=name_zh,
        name_en=name_en,
        latest_price=round(latest, 6),
        ema20=round(ema20, 6),
        ema50=round(ema50, 6),
        buy_zone_low=round(buy_low, 6),
        buy_zone_high=round(buy_high, 6),
        stop_reference=round(stop_reference, 6),
        chart_path=str(path),
    )


def write_crypto_chart_summary_csv(summaries: list[CryptoChartSummary], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = [field.name for field in fields(CryptoChartSummary)]
    rows = [asdict(summary) for summary in summaries]
    pd.DataFrame(rows, columns=columns).to_csv(output_path, index=False)
    return output_path


def write_crypto_alerts_csv(alerts: list[CryptoAlert], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = [field.name for field in fields(CryptoAlert)]
    rows = [asdict(alert) for alert in alerts]
    pd.DataFrame(rows, columns=columns).to_csv(output_path, index=False)
    return output_path
