# AGENTS.md

## Cursor Cloud specific instructions

### Project layout
- The application lives in the `Trading Bot/` subfolder (note the space). All commands below run from there.
- It is a Python (3.12) quant trading bot for the Futu OpenD API: `app/config.py` (settings), `app/strategy.py` (SMA crossover), `app/risk.py` (stop-loss/take-profit), `app/execution.py` (order manager), `app/futu_client.py` (Futu SDK wrapper), `app/main.py` (loop entrypoint).

### Environment
- A Python venv is kept at `Trading Bot/.venv`. Activate with `source ".venv/bin/activate"` (from inside `Trading Bot/`) before running anything.
- Dependencies come from `Trading Bot/requirements.txt` via `pip install -r requirements.txt` (the startup update script already does this).
- `config.py` is written for the pydantic **v1** API (`from pydantic import BaseSettings`, `Field(env=...)`, `class Config`), so `requirements.txt` pins `pydantic==1.10.18`. Do not bump pydantic to v2 without migrating `config.py`.

### Running / testing
- There is no test suite and no lint config in the repo. For a quick syntax/build check use `python -m py_compile app/*.py`.
- To run the entrypoint: from inside `Trading Bot/`, `python -m app.main` (it auto-loads a `.env` if present; there is no `.env.example` in the repo despite the README).
- The core decision logic (`app.config`, `app.strategy`, `app.risk`) imports and runs without any external service — good for exercising signal/risk logic on in-memory `pandas` DataFrames.

### Known blockers (durable, non-obvious)
- `futu_client.py` / `execution.py` / `main.py` import `OpenUSTradeContext` and `OpenHKTradeContext`, which no longer exist in the installable `futu-api` on Python 3.12 (the SDK now uses `OpenSecTradeContext`). Importing these modules — and therefore `python -m app.main` — fails until the code is migrated to the current Futu SDK API. This is a code change, not an environment issue.
- Even after that migration, running the bot end-to-end requires the **Futu OpenD** desktop gateway running locally (default `127.0.0.1:11111`) and a signed-in Futu brokerage account. Neither is available in the cloud VM, so full end-to-end runs cannot be exercised here.
