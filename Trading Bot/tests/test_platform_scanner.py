from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from app.platform_scanner import (
    UniverseAsset,
    evaluate_daily_candidate,
    market_chart_to_daily_frame,
    ohlc_rows_to_frame,
    rough_weekly_turnover_pct,
    write_platform_csv,
)


def make_daily_history(recent_high: bool, daily_volume: int = 50_000_000) -> pd.DataFrame:
    now = pd.Timestamp.now(tz="UTC").normalize()
    index = pd.date_range(end=now, periods=365, freq="D")
    close = np.linspace(100, 150, len(index))
    high = close * 1.01
    high[-3 if recent_high else -20] = high.max() * 1.05
    volume = np.full(len(index), daily_volume)
    return pd.DataFrame({"open": close, "high": high, "low": close * 0.98, "close": close, "volume": volume}, index=index)


class PlatformScannerTests(unittest.TestCase):
    def test_rough_weekly_turnover_pct(self) -> None:
        self.assertGreater(rough_weekly_turnover_pct(100_000_000, 1_000_000), 3.0)

    def test_ohlc_rows_to_frame(self) -> None:
        frame = ohlc_rows_to_frame([[1700000000000, 1, 2, 0.5, 1.5]])
        self.assertEqual(frame.iloc[0]["close"], 1.5)

    def test_market_chart_to_daily_frame(self) -> None:
        frame = market_chart_to_daily_frame([[1700000000000, 10.0]], [[1700000000000, 1000.0]])
        self.assertEqual(frame.iloc[0]["volume"], 1000.0)

    def test_evaluate_daily_candidate_accepts_valid_asset(self) -> None:
        asset = UniverseAsset("BTC", "Bitcoin", "crypto", "coingecko", 101_000_000, "bitcoin")
        candidate = evaluate_daily_candidate(
            asset,
            make_daily_history(recent_high=True, daily_volume=5_000_000),
            "coingecko",
            weekly_turnover_min=0.03,
        )
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.timeframe, "1d")

    def test_write_platform_csv_keeps_headers_when_empty(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            path = write_platform_csv([], Path(tmp) / "crypto_candidates.csv")
            self.assertIn("weekly_turnover_pct", path.read_text())


if __name__ == "__main__":
    unittest.main()
