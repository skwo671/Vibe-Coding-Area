from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskConfig:
    stop_loss_pct: float
    take_profit_pct: float


class RiskManager:
    def __init__(self, stop_loss_pct: float, take_profit_pct: float) -> None:
        self.config = RiskConfig(stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct)

    def check_exit(self, entry_price: float, last_price: float, side: str) -> str | None:
        if entry_price <= 0:
            return None
        change = (last_price - entry_price) / entry_price
        if side.upper() == "LONG":
            if change <= -self.config.stop_loss_pct:
                return "STOP_LOSS"
            if change >= self.config.take_profit_pct:
                return "TAKE_PROFIT"
        # Short logic can be added later
        return None
