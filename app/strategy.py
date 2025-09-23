from __future__ import annotations

import pandas as pd


class SmaCrossover:
    def __init__(self, fast: int, slow: int) -> None:
        if fast >= slow:
            raise ValueError("fast SMA must be less than slow SMA")
        self.fast = fast
        self.slow = slow
        self.last_signal: str | None = None

    def compute_signal(self, klines: pd.DataFrame) -> str | None:
        if klines is None or len(klines) < self.slow + 2:
            return None
        df = klines.copy()
        close = df["close"]
        sma_fast = close.rolling(self.fast).mean()
        sma_slow = close.rolling(self.slow).mean()
        prev_fast, prev_slow = sma_fast.iloc[-2], sma_slow.iloc[-2]
        curr_fast, curr_slow = sma_fast.iloc[-1], sma_slow.iloc[-1]

        if pd.isna(prev_fast) or pd.isna(prev_slow) or pd.isna(curr_fast) or pd.isna(curr_slow):
            return None

        if prev_fast <= prev_slow and curr_fast > curr_slow:
            return "BUY"
        if prev_fast >= prev_slow and curr_fast < curr_slow:
            return "SELL"
        return None
