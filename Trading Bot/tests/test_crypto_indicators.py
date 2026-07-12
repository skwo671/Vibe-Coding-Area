from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from app.crypto_indicators import (
    BB_SQUEEZE_PERCENTILE,
    RSI_OVERSOLD,
    bollinger_bandwidth,
    compute_crypto_buy_zone,
    detect_crypto_alerts,
    enrich_crypto_indicators,
    ema,
    obv,
    rsi,
)


def make_history(length: int = 260) -> pd.DataFrame:
    index = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=length, freq="D")
    close = np.linspace(100, 130, length)
    close[-1] = 140
    close[-2] = 128
    volume = np.linspace(1_000, 2_000, length)
    return pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99, "close": close, "volume": volume}, index=index)


class CryptoIndicatorTests(unittest.TestCase):
    def test_enrich_crypto_indicators_adds_expected_columns(self) -> None:
        chart = enrich_crypto_indicators(make_history())
        for column in ("ema20", "ema50", "ema200", "rsi14", "bb_upper", "bb_lower", "obv", "obv_ema21"):
            self.assertIn(column, chart.columns)

    def test_rsi_returns_bounded_values(self) -> None:
        values = rsi(pd.Series(np.linspace(100, 150, 50)))
        self.assertTrue(values.dropna().between(0, 100).all())

    def test_obv_changes_with_direction(self) -> None:
        close = pd.Series([1, 2, 2, 3])
        volume = pd.Series([10, 10, 10, 10])
        self.assertGreater(obv(close, volume).iloc[-1], obv(close, volume).iloc[0])

    def test_detect_ema_bullish_cross_alert(self) -> None:
        chart = enrich_crypto_indicators(make_history())
        chart.loc[chart.index[-2], ["ema20", "ema50"]] = [99, 100]
        chart.loc[chart.index[-1], ["ema20", "ema50"]] = [101, 100]
        alerts = detect_crypto_alerts("BTC", chart)
        self.assertTrue(any(alert.alert_type == "ema_cross_bullish" for alert in alerts))

    def test_detect_rsi_overbought_alert(self) -> None:
        chart = enrich_crypto_indicators(make_history())
        chart.loc[chart.index[-2], "rsi14"] = 68
        chart.loc[chart.index[-1], "rsi14"] = 72
        alerts = detect_crypto_alerts("BTC", chart)
        self.assertTrue(any(alert.alert_type == "rsi_overbought" for alert in alerts))

    def test_detect_bb_squeeze_alert(self) -> None:
        chart = enrich_crypto_indicators(make_history())
        threshold = chart["bb_bandwidth"].tail(120).quantile(BB_SQUEEZE_PERCENTILE)
        chart.loc[chart.index[-1], "bb_bandwidth"] = threshold * 0.5
        alerts = detect_crypto_alerts("BTC", chart)
        self.assertTrue(any(alert.alert_type == "bb_squeeze" for alert in alerts))

    def test_detect_rsi_oversold_alert(self) -> None:
        chart = enrich_crypto_indicators(make_history())
        chart.loc[chart.index[-2], "rsi14"] = 32
        chart.loc[chart.index[-1], "rsi14"] = RSI_OVERSOLD
        alerts = detect_crypto_alerts("BTC", chart)
        self.assertTrue(any(alert.alert_type == "rsi_oversold" for alert in alerts))

    def test_compute_crypto_buy_zone_uses_ema20_and_ema50(self) -> None:
        chart = enrich_crypto_indicators(make_history())
        result = compute_crypto_buy_zone(chart)
        self.assertIsNotNone(result)
        assert result is not None
        latest, ema20, ema50, buy_low, buy_high, stop = result
        self.assertGreater(latest, 0)
        self.assertLessEqual(buy_low, buy_high)
        self.assertLess(stop, ema50)

    def test_plot_crypto_technical_chart_returns_summary_with_names(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from app.asset_display import AssetDisplayInfo
        from app.crypto_indicators import plot_crypto_technical_chart

        display = AssetDisplayInfo(symbol="BTC", name_en="Bitcoin", name_zh="比特币", logo_url="")
        with TemporaryDirectory() as tmp:
            summary = plot_crypto_technical_chart("BTC", make_history(), Path(tmp), display=display)
            self.assertIsNotNone(summary)
            assert summary is not None
            self.assertEqual(summary.name_zh, "比特币")
            self.assertEqual(summary.name_en, "Bitcoin")
            self.assertTrue(Path(summary.chart_path).exists())

    def test_bollinger_bandwidth_positive(self) -> None:
        close = pd.Series(np.linspace(100, 120, 40))
        middle = close.rolling(20).mean()
        upper = middle + 2
        lower = middle - 2
        self.assertGreater(float(bollinger_bandwidth(upper, lower, middle).dropna().iloc[-1]), 0)


if __name__ == "__main__":
    unittest.main()
