# CLAUDE.md — nautilus-alpaca

## Project Overview

`nautilus-alpaca` is a standalone Python adapter package that connects [Alpaca Markets](https://alpaca.markets) to [nautilus-trader](https://nautilustrader.io), a high-performance algorithmic trading framework.

This package lives **outside** the nautilus-trader repo and depends on it as an external PyPI package. The pattern mirrors how Binance, Kraken, and Interactive Brokers adapters are structured inside nautilus-trader, but as a standalone installable package.

**Default to paper trading (`paper=True`) in all configs unless explicitly overridden.** Never hardcode credentials.

---

## Development Environment

**Virtual environment:** `.venv/` at the project root (Python 3.13.11, managed by `uv`).

All `python`, `pip`, and `pytest` commands must use the venv. In Bash tool calls use the full path:
```bash
.venv/bin/python -c "..."
.venv/bin/pytest tests/
```
Or activate first: `source .venv/bin/activate`. When spawning subagents, always instruct them to use `.venv/bin/python` for any Python invocations and to verify imports with it.

---

## Key References

### Alpaca Markets
- API overview: https://docs.alpaca.markets/
- Trading REST API: https://docs.alpaca.markets/reference/getallorders-1
- Assets API: https://docs.alpaca.markets/reference/getallassets-1
- Market Data REST: https://docs.alpaca.markets/reference/stocklatestquotes
- Real-time streaming: https://docs.alpaca.markets/docs/real-time-stock-pricing-data
- Crypto streaming: https://docs.alpaca.markets/docs/real-time-crypto-pricing-data
- Paper vs live endpoints: https://docs.alpaca.markets/docs/paper-trading
- Order types: https://docs.alpaca.markets/docs/orders-at-alpaca

### alpaca-py (official Python SDK)
- GitHub: https://github.com/alpacahq/alpaca-py
- Docs: https://alpaca.markets/sdks/python/

### nautilus-trader
- Docs: https://nautilustrader.io/docs/latest/
- Source (local): `/Users/preet/Developer/nautilus_trader/`
- Adapter template: `/Users/preet/Developer/nautilus_trader/nautilus_trader/adapters/_template/`
- **Gold-standard reference** — Binance adapter: `/Users/preet/Developer/nautilus_trader/nautilus_trader/adapters/binance/`

### nautilus-trader base classes (read these before implementing)
| Class | File |
|-------|------|
| `InstrumentProvider` | `nautilus_trader/common/providers.py` |
| `LiveMarketDataClient` | `nautilus_trader/live/data_client.py` |
| `LiveExecutionClient` | `nautilus_trader/live/execution_client.py` |
| `LiveDataClientFactory` | `nautilus_trader/live/factories.py` |
| `LiveExecClientFactory` | `nautilus_trader/live/factories.py` |
| `InstrumentProviderConfig` | `nautilus_trader/config/live.py` |
| `LiveDataClientConfig` | `nautilus_trader/config/live.py` |
| `LiveExecClientConfig` | `nautilus_trader/config/live.py` |

---

## Target Package Layout

```
nautilus_alpaca/
├── __init__.py          # public re-exports
├── config.py            # AlpacaInstrumentProviderConfig, AlpacaDataClientConfig, AlpacaExecClientConfig
├── factories.py         # AlpacaLiveDataClientFactory, AlpacaLiveExecClientFactory
├── providers.py         # AlpacaInstrumentProvider
├── data.py              # AlpacaDataClient (LiveMarketDataClient)
├── execution.py         # AlpacaExecutionClient (LiveExecutionClient)
└── common/
    ├── __init__.py
    ├── constants.py     # ALPACA_VENUE, URL constants
    ├── credentials.py   # env var helpers
    ├── enums.py         # AlpacaEnvironment, order/asset enums
    ├── parsing.py       # instrument + order conversion helpers
    └── schemas/
        ├── __init__.py
        ├── market.py    # msgspec Structs for market data (REST + WS)
        ├── account.py   # msgspec Structs for account, orders, positions
        └── ws.py        # msgspec Structs for WS control/auth messages
```

---

## Base Classes: Required vs Optional Methods

### `InstrumentProvider` — must implement
- `async load_all_async(filters: dict | None = None) -> None`

Optional (Alpaca supports per-symbol fetch):
- `async load_ids_async(instrument_ids, filters) -> None`

### `LiveMarketDataClient` — must implement
- `async _connect() -> None`
- `async _disconnect() -> None`

Optional (implement what Alpaca supports):
- `_subscribe_quote_ticks` / `_unsubscribe_quote_ticks`
- `_subscribe_trade_ticks` / `_unsubscribe_trade_ticks`
- `_subscribe_bars` / `_unsubscribe_bars`
- `_request_instruments`, `_request_quote_ticks`, `_request_trade_ticks`, `_request_bars`

### `LiveExecutionClient` — must implement
- `async _connect() -> None`
- `async _disconnect() -> None`
- `async _submit_order(command: SubmitOrder) -> None`
- `async _cancel_order(command: CancelOrder) -> None`
- `async _cancel_all_orders(command: CancelAllOrders) -> None`
- `async generate_order_status_report(command) -> OrderStatusReport | None`
- `async generate_order_status_reports(command) -> list[OrderStatusReport]`
- `async generate_fill_reports(command) -> list[FillReport]`
- `async generate_position_status_reports(command) -> list[PositionStatusReport]`
- `async generate_mass_status(lookback_mins) -> ExecutionMassStatus | None`

Optional:
- `async _modify_order(command: ModifyOrder) -> None`
- `async _submit_order_list(command: SubmitOrderList) -> None`
- `async _batch_cancel_orders(command: BatchCancelOrders) -> None`

---

## How Execution Clients Emit Events

Execution client methods (`_submit_order`, `_cancel_order`, etc.) do **not** return values. They generate events by calling inherited methods on `self`:

```python
self.generate_order_submitted(strategy_id, instrument_id, client_order_id, ts_event)
self.generate_order_accepted(strategy_id, instrument_id, client_order_id, venue_order_id, ts_event)
self.generate_order_rejected(strategy_id, instrument_id, client_order_id, reason, ts_event)
self.generate_order_filled(...)
self.generate_order_canceled(...)
self.generate_account_state(balances, margins, reported, ts_event)
```

Find all available `generate_*` methods in `nautilus_trader/execution/client.py`. Study `binance/execution.py` for usage examples.

---

## Instrument ID Convention

Alpaca symbols map to nautilus `InstrumentId` as:
- `AAPL` → `AAPL.ALPACA`
- `BTC/USD` → `BTC/USD.ALPACA`
- `MSFT251219C00450000` (option) → `MSFT251219C00450000.ALPACA`

---

## Alpaca API Notes

### Auth & endpoints
| Environment | Base URL | Env vars |
|-------------|----------|----------|
| Paper | `https://paper-api.alpaca.markets` | `ALPACA_PAPER_API_KEY`, `ALPACA_PAPER_API_SECRET` |
| Live | `https://api.alpaca.markets` | `ALPACA_API_KEY`, `ALPACA_API_SECRET` |
| Data | `https://data.alpaca.markets` | (same keys) |

Paper and live use different base URLs but the same API key format. Credentials helpers should try the environment-specific var first, then fall back to the generic one.

### Asset classes
| Alpaca `asset_class` | nautilus type | Notes |
|----------------------|---------------|-------|
| `us_equity` | `Equity` | stocks + ETFs |
| `crypto` | `CurrencyPair` | 24/7, no market hours |
| `us_option` | (skip for now) | return `None`, log warning |

### Market data feeds
- `iex` — free tier, ~15min delayed outside market hours; real-time during market hours
- `sip` — consolidated tape, requires paid subscription

### Order types
Market, Limit, Stop, Stop-Limit, Trailing Stop. Bracket orders (entry + TP + SL) are submitted as a single request with `order_class="bracket"`.

### Important limits
- Alpaca does not have a dedicated fills endpoint. Synthesize `FillReport` objects from order data (`filled_qty`, `filled_avg_price`).
- Extended hours: set `extended_hours=True` on order submission.
- Fractional shares: use `qty` as a fractional string (e.g. `"0.5"`) or use `notional` instead.

---

## alpaca-py Usage Patterns

```python
# REST clients
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient

trading = TradingClient(api_key, api_secret, paper=True)
account = trading.get_account()
assets = trading.get_all_assets()

# Real-time market data (callbacks)
from alpaca.data.live import StockDataStream, CryptoDataStream
stream = StockDataStream(api_key, api_secret)
stream.subscribe_quotes(async_quote_handler, "AAPL", "MSFT")
stream.subscribe_trades(async_trade_handler, "AAPL")
await stream.run()   # runs until stopped; call stream.stop() to exit

# Real-time order updates
from alpaca.trading.stream import TradingStream
ts = TradingStream(api_key, api_secret, paper=True)
ts.subscribe_trade_updates(async_trade_update_handler)
await ts.run()
```

Handlers registered with alpaca-py are called with parsed model objects (not raw dicts). The async handler signature is `async def handler(data) -> None`.

---

## Config Dataclasses Pattern

All config classes use `frozen=True` and inherit from the corresponding nautilus base:

```python
class AlpacaDataClientConfig(LiveDataClientConfig, frozen=True):
    api_key: str | None = None      # reads from env if None
    api_secret: str | None = None
    paper: bool = True
    feed: str = "iex"
    ...
```

Reference the Binance adapter source heavily — it is the most complete nautilus-trader adapter and covers every pattern you'll need.
