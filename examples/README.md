# Examples

Toy strategies demonstrating the nautilus-alpaca adapter.

## Files

| File | Description |
|------|-------------|
| `ema_crossover.py` | Shared strategy: goes long on fast/slow EMA crossover, exits on reversal |
| `backtest.py` | Runs the strategy on one year of AAPL daily bars via Alpaca historical REST API |
| `paper_trading.py` | Runs the strategy live on AAPL 1-minute bars via Alpaca paper account |

## Setup

```bash
export ALPACA_PAPER_API_KEY=your_key
export ALPACA_PAPER_API_SECRET=your_secret
```

## Running with Docker (recommended)

The Docker image uses a Linux Python 3.13 base, which avoids the macOS SSL
certificate validation issue present in Homebrew Python 3.13.

```bash
# Build once
docker compose build

# Backtest
docker compose run --rm backtest

# Paper trading (stop with Ctrl-C)
docker compose run --rm paper-trading
```

## Running locally

> **macOS + Python 3.13 note:** Homebrew's Python 3.13 rejects CA certs that
> lack the `keyUsage` extension. Alpaca's intermediate CA triggers this. Use
> Docker above, or run the `Install Certificates.command` that ships with the
> official Python.org installer.

```bash
.venv/bin/python -m examples.backtest
.venv/bin/python -m examples.paper_trading
```

## Backtest

Fetches AAPL daily OHLCV bars for 2024 from Alpaca and runs the EMA crossover
strategy with a $100,000 starting balance.

## Paper trading

Connects to Alpaca's paper trading WebSocket, subscribes to AAPL 1-minute
bars, and trades in real time. Run during US market hours (9:30–16:00 ET)
for live bar data; bars continue to arrive outside hours on the IEX feed.

Stop with `Ctrl-C`.

## Customising the strategy

Both runners share the same `EmaCrossover` strategy. Tweak the config at the
top of each script:

- `fast_ema_period` / `slow_ema_period` — EMA window lengths
- `trade_size` — number of shares per order (as a string, e.g. `"50"`)
- `SYMBOL` — swap out AAPL for any US equity or crypto pair (e.g. `"BTC/USD"`)
