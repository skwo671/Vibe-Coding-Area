from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Tuple

import pandas as pd
from futu import (
    OpenQuoteContext,
    OpenUSTradeContext,
    OpenHKTradeContext,
    TrdEnv,
    TrdOrderType,
    TrdSide,
    RET_OK,
)


@dataclass
class FutuContexts:
    quote: OpenQuoteContext
    trade: OpenUSTradeContext | OpenHKTradeContext


class FutuClient:
    def __init__(self, host: str, port: int, market: str, env: str, account_id: str) -> None:
        self.host = host
        self.port = port
        self.market = market.upper()
        self.env = TrdEnv.SIMULATE if env.upper() == "SIMULATE" else TrdEnv.REAL
        self.account_id = account_id
        self.ctxs: Optional[FutuContexts] = None

    def connect(self) -> None:
        quote = OpenQuoteContext(host=self.host, port=self.port)
        if self.market == "US":
            trade = OpenUSTradeContext(host=self.host, port=self.port, security_firm=0)
        elif self.market == "HK":
            trade = OpenHKTradeContext(host=self.host, port=self.port, security_firm=0)
        else:
            quote.close()
            raise ValueError(f"Unsupported market: {self.market}")
        self.ctxs = FutuContexts(quote=quote, trade=trade)

    def close(self) -> None:
        if self.ctxs is not None:
            try:
                self.ctxs.trade.close()
            finally:
                self.ctxs.quote.close()
            self.ctxs = None

    def __enter__(self) -> "FutuClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def fetch_klines(self, symbol: str, ktype: str = "K_1M", count: int = 200) -> pd.DataFrame:
        if self.ctxs is None:
            raise RuntimeError("Not connected")
        ret, data = self.ctxs.quote.get_cur_kline(symbol, num=count, ktype=ktype)
        if ret != RET_OK:
            raise RuntimeError(f"get_cur_kline failed: {data}")
        return data

    def get_last_price(self, symbol: str) -> float:
        if self.ctxs is None:
            raise RuntimeError("Not connected")
        ret, data = self.ctxs.quote.get_market_snapshot([symbol])
        if ret != RET_OK:
            raise RuntimeError(f"get_market_snapshot failed: {data}")
        return float(data.iloc[0]["last_price"])  # type: ignore[index]

    def get_position_qty(self, symbol: str) -> int:
        if self.ctxs is None:
            raise RuntimeError("Not connected")
        ret, data = self.ctxs.trade.position_list_query(trd_env=self.env)
        if ret != RET_OK:
            raise RuntimeError(f"position_list_query failed: {data}")
        rows = data[data["code"] == symbol]
        if rows.empty:
            return 0
        return int(rows.iloc[0]["qty"])

    def place_market_order(self, symbol: str, qty: int, side: str) -> Tuple[bool, str]:
        if self.ctxs is None:
            raise RuntimeError("Not connected")
        futu_side = TrdSide.BUY if side.upper() == "BUY" else TrdSide.SELL
        # Market order: price=0, order type MARKET
        ret, data = self.ctxs.trade.place_order(
            trd_env=self.env,
            order_type=TrdOrderType.MARKET,
            code=symbol,
            qty=qty,
            price=0,
            trd_side=futu_side,
            acc_id=self.account_id if self.account_id else None,
        )
        if ret != RET_OK:
            return False, str(data)
        order_id = str(data["order_id"][0])
        return True, order_id

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)
