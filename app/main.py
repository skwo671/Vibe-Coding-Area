from __future__ import annotations

import logging
import signal
import sys
from contextlib import contextmanager

import pandas as pd
from dotenv import load_dotenv

from .config import get_settings
from .futu_client import FutuClient
from .strategy import SmaCrossover
from .execution import ExecutionManager
from .risk import RiskManager


STOP = False


def _handle_sigint(sig, frame):
    global STOP
    STOP = True


signal.signal(signal.SIGINT, _handle_sigint)


@contextmanager
def run_client(settings):
    client = FutuClient(
        host=settings.opend_host,
        port=settings.opend_port,
        market=settings.market,
        env=settings.trading_env,
        account_id=settings.account_id,
    )
    try:
        client.connect()
        yield client
    finally:
        client.close()


def main() -> int:
    load_dotenv()
    settings = get_settings()

    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("bot")

    strategy = SmaCrossover(fast=settings.sma_fast, slow=settings.sma_slow)

    with run_client(settings) as client:
        exec_mgr = ExecutionManager(
            client=client,
            symbol=settings.symbol,
            order_size=settings.order_size,
            max_position=settings.max_position,
        )
        risk_mgr = RiskManager(
            stop_loss_pct=settings.stop_loss_pct,
            take_profit_pct=settings.take_profit_pct,
        )

        log.info("Starting loop for %s", settings.symbol)
        while not STOP:
            try:
                kl = client.fetch_klines(settings.symbol, ktype="K_1M", count=max(200, settings.sma_slow + 5))
                signal_ = strategy.compute_signal(kl)
                exec_mgr.refresh_position()

                last_price = float(kl.iloc[-1]["close"]) if isinstance(kl, pd.DataFrame) and not kl.empty else client.get_last_price(settings.symbol)

                # Risk check for long-only position
                if exec_mgr.position.qty > 0:
                    exit_reason = risk_mgr.check_exit(exec_mgr.position.entry_price, last_price, side="LONG")
                    if exit_reason is not None:
                        res = exec_mgr.on_signal("SELL")
                        log.info("Risk exit %s, action=%s", exit_reason, res)

                if signal_ is not None:
                    res = exec_mgr.on_signal(signal_)
                    log.info("Signal %s -> %s", signal_, res)

            except Exception as e:
                log.exception("Loop error: %s", e)

            client.wait(5)

    log.info("Stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
