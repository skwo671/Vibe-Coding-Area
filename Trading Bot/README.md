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

#### Crypto and US Stock Opportunity Scanner
Use the scanner to build a watchlist of crypto and US stocks that match all of these conditions:
- A 52-week high occurred within the last 7 days.
- The latest 4-hour close is above MA20 and MA50.
- Market cap is greater than 100M USD.
- The trailing 7-day turnover rate is at least 5%.

```bash
python -m app.market_scanner
```

Useful options:
```bash
python -m app.market_scanner --crypto BTC-USD,ETH-USD,SOL-USD --stocks NVDA,MSFT,AAPL
python -m app.market_scanner --weekly-turnover-min 0.05
python -m app.market_scanner --output-dir scanner_output
python -m app.market_scanner --sample-data
```

The scanner writes `scanner_output/candidates.csv`. For crypto candidates, it also writes a chart showing the 4-hour close, MA10/MA20/MA50, the latest 52-week high, an approximate buy zone near the MA20-MA50 pullback area, and a stop reference below MA50.

Market data is fetched from Yahoo Finance via `yfinance` (daily OHLCV, 4-hour OHLCV, and market cap). This is convenient for a watchlist scan, but Yahoo does not provide a single API to screen the entire market at once, so the scanner works from a symbol list you provide or from the built-in defaults.

This scanner is for watchlist generation only and is not financial advice.

#### Platform Scanner (CoinGecko + Finnhub/Yahoo, daily candles)
For broader market coverage with separate crypto and US stock outputs:

```bash
python -m app.platform_scanner --output-dir platform_output
```

- Crypto universe: CoinGecko top market-cap coins (default 500)
- US stock universe: Finnhub screener when `FINNHUB_API_KEY` is set, otherwise S&P 500 via Yahoo Finance
- Timeframe: daily (1d) candles with MA20/MA50, 52-week high, and 7-day turnover filters
- Outputs:
  - `platform_output/crypto_candidates.csv`
  - `platform_output/us_stocks_candidates.csv`
  - `platform_output/crypto_charts/`
  - `platform_output/us_stock_charts/`

Set your Finnhub key in `.env`:

```bash
FINNHUB_API_KEY=your_key_here
```

#### Notes
- Use at your own risk. Market orders can fill at unfavorable prices.
- Backtest thoroughly before going live. This sample is for education only.
