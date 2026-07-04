from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from app.market_scanner import (
    AssetRequest,
    MarketDataProvider,
    estimate_buy_zone,
    moving_average_snapshot,
    recent_52_week_high,
    scan_assets,
)


class FakeProvider(MarketDataProvider):
    def __init__(self, market_cap: int = 250_000_000) -> None:
        self._market_cap = market_cap

    def history(self, symbol: str, period: str, interval: str) -> pd.DataFrame:
        if interval == "1d":
            return make_daily_history(recent_high=True)
        if interval == "4h":
            return make_four_hour_history(above_mas=True)
        raise ValueError(interval)

    def market_cap(self, symbol: str) -> int | None:
        return self._market_cap


def make_daily_history(recent_high: bool) -> pd.DataFrame:
    now = pd.Timestamp("2026-07-04", tz="UTC")
    index = pd.date_range(end=now, periods=365, freq="D")
    close = np.linspace(100, 150, len(index))
    high = close * 1.01
    high[-3 if recent_high else -20] = high.max() * 1.05
    return pd.DataFrame({"High": high, "Close": close}, index=index)


def make_four_hour_history(above_mas: bool) -> pd.DataFrame:
    index = pd.date_range(end=pd.Timestamp("2026-07-04", tz="UTC"), periods=80, freq="4h")
    close = np.linspace(100, 150, len(index))
    if not above_mas:
        close[-1] = 95
    return pd.DataFrame({"Close": close}, index=index)


class MarketScannerTests(unittest.TestCase):
    def test_recent_52_week_high_accepts_high_inside_lookback(self) -> None:
        matched, high, high_date = recent_52_week_high(
            make_daily_history(recent_high=True),
            now=pd.Timestamp("2026-07-04", tz="UTC"),
        )

        self.assertTrue(matched)
        self.assertGreater(high, 0)
        self.assertEqual(high_date.date().isoformat(), "2026-07-02")

    def test_recent_52_week_high_rejects_stale_high(self) -> None:
        matched, _, _ = recent_52_week_high(
            make_daily_history(recent_high=False),
            now=pd.Timestamp("2026-07-04", tz="UTC"),
        )

        self.assertFalse(matched)

    def test_moving_average_snapshot_requires_price_above_all_mas(self) -> None:
        matched, latest, ma10, ma20, ma50 = moving_average_snapshot(make_four_hour_history(above_mas=True))

        self.assertTrue(matched)
        self.assertGreater(latest, ma10)
        self.assertGreater(latest, ma20)
        self.assertGreater(latest, ma50)

    def test_moving_average_snapshot_rejects_price_below_mas(self) -> None:
        matched, _, _, _, _ = moving_average_snapshot(make_four_hour_history(above_mas=False))

        self.assertFalse(matched)

    def test_estimate_buy_zone_uses_ma10_ma20_pullback_and_ma50_stop(self) -> None:
        low, high, stop = estimate_buy_zone(latest_price=120, ma10=112, ma20=108, ma50=100)

        self.assertEqual(low, 108)
        self.assertEqual(high, 112)
        self.assertEqual(stop, 98)

    def test_scan_assets_applies_market_cap_threshold(self) -> None:
        assets = [AssetRequest("BTC-USD", "crypto")]

        self.assertEqual(scan_assets(assets, FakeProvider(market_cap=99_000_000)), [])
        self.assertEqual(len(scan_assets(assets, FakeProvider(market_cap=101_000_000))), 1)


if __name__ == "__main__":
    unittest.main()
