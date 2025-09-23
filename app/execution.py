from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .futu_client import FutuClient


@dataclass
class PositionState:
    qty: int = 0
    entry_price: float = 0.0


class ExecutionManager:
    def __init__(self, client: FutuClient, symbol: str, order_size: int, max_position: int) -> None:
        self.client = client
        self.symbol = symbol
        self.order_size = order_size
        self.max_position = max_position
        self.position = PositionState()

    def refresh_position(self) -> None:
        self.position.qty = self.client.get_position_qty(self.symbol)

    def on_signal(self, signal: Optional[str]) -> Optional[str]:
        if signal is None:
            return None
        if signal == "BUY":
            if self.position.qty + self.order_size > self.max_position:
                return "SKIP_BUY_MAX_POS"
            ok, oid = self.client.place_market_order(self.symbol, self.order_size, side="BUY")
            if ok:
                last_price = self.client.get_last_price(self.symbol)
                self.position.qty += self.order_size
                if self.position.entry_price == 0:
                    self.position.entry_price = last_price
                return f"BUY_OK:{oid}"
            return f"BUY_FAIL:{oid}"
        if signal == "SELL":
            sell_qty = min(self.order_size, self.position.qty)
            if sell_qty <= 0:
                return "SKIP_SELL_NO_POS"
            ok, oid = self.client.place_market_order(self.symbol, sell_qty, side="SELL")
            if ok:
                self.position.qty -= sell_qty
                if self.position.qty == 0:
                    self.position.entry_price = 0.0
                return f"SELL_OK:{oid}"
            return f"SELL_FAIL:{oid}"
        return None
