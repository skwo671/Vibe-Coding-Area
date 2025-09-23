from pydantic import BaseSettings, Field
from typing import Literal


class Settings(BaseSettings):
    opend_host: str = Field(default="127.0.0.1", env="FUTU_OPEND_HOST")
    opend_port: int = Field(default=11111, env="FUTU_OPEND_PORT")

    trading_env: Literal["SIMULATE", "REAL"] = Field(default="SIMULATE", env="FUTU_TRADING_ENV")
    market: Literal["US", "HK"] = Field(default="US", env="FUTU_MARKET")
    account_id: str = Field(default="", env="FUTU_ACCOUNT_ID")

    symbol: str = Field(default="US.AAPL", env="SYMBOL")

    sma_fast: int = Field(default=10, env="SMA_FAST")
    sma_slow: int = Field(default=30, env="SMA_SLOW")

    order_size: int = Field(default=1, env="ORDER_SIZE")
    max_position: int = Field(default=10, env="MAX_POSITION")

    stop_loss_pct: float = Field(default=0.05, env="STOP_LOSS_PCT")
    take_profit_pct: float = Field(default=0.10, env="TAKE_PROFIT_PCT")

    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    class Config:
        env_file = ".env"
        case_sensitive = False


def get_settings() -> Settings:
    return Settings()
