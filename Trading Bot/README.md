### Quant Trading Bot with Futu OpenD

This is a minimal quantitative trading app using the Futu OpenD API. It runs a simple SMA crossover strategy and sends market orders when signals fire, with basic risk controls.

#### Prerequisites
- Install Futu OpenD and sign in to your Futu account.
- Start OpenD locally and keep it running while the bot runs.
- Use a simulated environment first.

#### Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your values.

#### Key Configuration
- FUTU_OPEND_HOST, FUTU_OPEND_PORT: Where OpenD runs.
- FUTU_TRADING_ENV: SIMULATE or REAL.
- FUTU_MARKET: US or HK.
- FUTU_ACCOUNT_ID: Your trading account id for the selected market.
- SYMBOL: Market-prefixed symbol, e.g. `US.AAPL` or `HK.00700`.

#### Run
```bash
python -m app.main
```

The bot subscribes to quotes, computes SMA fast/slow, and places market orders on crossovers, respecting max position and stop/take risk limits.

#### Notes
- Use at your own risk. Market orders can fill at unfavorable prices.
- Backtest thoroughly before going live. This sample is for education only.
