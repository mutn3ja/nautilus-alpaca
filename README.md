# nautilus-alpaca

A standalone Python adapter that connects [Alpaca Markets](https://alpaca.markets) to [nautilus-trader](https://nautilustrader.io), a high-performance algorithmic trading framework. The adapter mirrors the structure of the built-in Binance, Kraken, and Interactive Brokers adapters but lives outside the nautilus-trader repository as an independently installable package. It supports US equities, ETFs, and crypto pairs via Alpaca's REST and WebSocket APIs, using paper trading by default.

---

## Installation

For local development, install in editable mode:

```bash
pip install -e .
```

To install with test dependencies:

```bash
pip install -e ".[dev]"
```

---

## Quick Start

### 1. Set credentials

```bash
# Paper trading (default)
export ALPACA_PAPER_API_KEY=your_paper_key
export ALPACA_PAPER_API_SECRET=your_paper_secret

# Live trading (when paper=False)
export ALPACA_API_KEY=your_live_key
export ALPACA_API_SECRET=your_live_secret
```

### 2. Run the example

```bash
python main.py
```

The example builds a `TradingNode` wired with the Alpaca data and execution clients:

```python
from nautilus_trader.config import TradingNodeConfig, InstrumentProviderConfig
from nautilus_trader.live.node import TradingNode

from nautilus_alpaca import (
    AlpacaDataClientConfig,
    AlpacaExecClientConfig,
    AlpacaLiveDataClientFactory,
    AlpacaLiveExecClientFactory,
)

config = TradingNodeConfig(
    trader_id="ALPACA-001",
    data_clients={
        "ALPACA": AlpacaDataClientConfig(
            paper=True,
            feed="iex",
            instrument_provider=InstrumentProviderConfig(load_all=False),
        ),
    },
    exec_clients={
        "ALPACA": AlpacaExecClientConfig(paper=True),
    },
)
node = TradingNode(config=config)
node.add_data_client_factory("ALPACA", AlpacaLiveDataClientFactory)
node.add_exec_client_factory("ALPACA", AlpacaLiveExecClientFactory)
node.build()
# node.run()  # add strategies, then call run()
```

---

## Configuration Reference

### AlpacaDataClientConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `api_key` | `str \| None` | `None` | Alpaca API public key. Reads from env if `None`. |
| `api_secret` | `str \| None` | `None` | Alpaca API secret key. Reads from env if `None`. |
| `paper` | `bool` | `True` | Use paper trading endpoint. |
| `feed` | `str` | `"iex"` | Market data feed. `"iex"` is free; `"sip"` requires a paid plan. |
| `base_url_http` | `str \| None` | `None` | Override the HTTP base URL (e.g. for testing). |
| `base_url_ws` | `str \| None` | `None` | Override the WebSocket base URL. |
| `update_instruments_interval_mins` | `int \| None` | `60` | How often (minutes) to reload instruments from the venue. |

### AlpacaExecClientConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `api_key` | `str \| None` | `None` | Alpaca API public key. Reads from env if `None`. |
| `api_secret` | `str \| None` | `None` | Alpaca API secret key. Reads from env if `None`. |
| `paper` | `bool` | `True` | Use paper trading endpoint. |
| `base_url_http` | `str \| None` | `None` | Override the HTTP base URL. |
| `base_url_ws` | `str \| None` | `None` | Override the WebSocket base URL. |
| `max_retries` | `int \| None` | `3` | Max retries for order submit/cancel/modify. |
| `retry_delay_initial_ms` | `int \| None` | `1000` | Initial retry delay in milliseconds. |
| `retry_delay_max_ms` | `int \| None` | `10000` | Maximum retry delay in milliseconds. |

### AlpacaInstrumentProviderConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `asset_class` | `str \| None` | `None` | Filter by asset class: `"us_equity"`, `"crypto"`, or `None` for all. |
| `log_warnings` | `bool` | `True` | Log warnings for unsupported or unparseable instruments. |

### Instrument ID Convention

| Alpaca symbol | nautilus InstrumentId |
|---------------|----------------------|
| `AAPL` | `AAPL.ALPACA` |
| `BTC/USD` | `BTC/USD.ALPACA` |

---

## Running Tests

```bash
pytest tests/ -v
```

All tests are pure unit tests using mocks — no live Alpaca credentials required.

---

## References

- [Alpaca Markets API docs](https://docs.alpaca.markets/)
- [alpaca-py Python SDK](https://alpaca.markets/sdks/python/)
- [nautilus-trader docs](https://nautilustrader.io/docs/latest/)
- [nautilus-trader source](https://github.com/nautechsystems/nautilus_trader)
