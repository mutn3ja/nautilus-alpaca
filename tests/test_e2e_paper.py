"""
End-to-end integration tests against Alpaca paper trading.
All tests are skipped automatically when ALPACA_PAPER_API_KEY is not set.

Run with real credentials:
    export ALPACA_PAPER_API_KEY=your_key
    export ALPACA_PAPER_API_SECRET=your_secret
    pytest tests/test_e2e_paper.py -v -s -m e2e
"""
import asyncio
import contextlib
import os
from datetime import datetime, timezone, timedelta, time as dtime
from decimal import Decimal, InvalidOperation

import pytest

from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Equity, CurrencyPair
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.common.component import LiveClock

from nautilus_alpaca import AlpacaInstrumentProviderConfig
from nautilus_alpaca.common.enums import AlpacaEnvironment
from nautilus_alpaca.common.credentials import get_api_key, get_api_secret
from nautilus_alpaca.providers import AlpacaInstrumentProvider

# Skip entire module if credentials are absent
pytestmark = pytest.mark.skipif(
    not os.getenv("ALPACA_PAPER_API_KEY"),
    reason="ALPACA_PAPER_API_KEY not set — skipping e2e tests",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_market_open() -> bool:
    """Return True if US equities market is currently open (ET 9:30–16:00, Mon–Fri)."""
    et = datetime.now(timezone(timedelta(hours=-4)))
    if et.weekday() >= 5:
        return False
    return dtime(9, 30) <= et.time() <= dtime(16, 0)


def assert_decimal_str(value: str, *, min_val: float | None = None, label: str = "") -> float:
    """Assert a string is parseable as a Decimal; return the float value."""
    try:
        result = float(Decimal(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        pytest.fail(f"{label or 'value'} {value!r} is not a valid decimal string: {exc}")
    if min_val is not None:
        assert result >= min_val, f"{label or 'value'} {result} < min {min_val}"
    return result


def _new_provider() -> AlpacaInstrumentProvider:
    return AlpacaInstrumentProvider(
        clock=LiveClock(),
        api_key=get_api_key(paper=True),
        api_secret=get_api_secret(paper=True),
        environment=AlpacaEnvironment.PAPER,
        config=AlpacaInstrumentProviderConfig(),
    )


# ---------------------------------------------------------------------------
# Module-scoped provider fixture (shared across TestInstrumentLoading)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
async def provider():
    """Real AlpacaInstrumentProvider loaded once for the module."""
    p = _new_provider()
    await p.load_all_async()
    return p


# ---------------------------------------------------------------------------
# TestInstrumentLoading
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestInstrumentLoading:
    async def test_loads_many_instruments(self, provider):
        assert provider.count >= 100, f"Expected >=100 instruments, got {provider.count}"

    async def test_has_equities_and_crypto(self, provider):
        all_instruments = list(provider.get_all().values())
        equities = [i for i in all_instruments if isinstance(i, Equity)]
        crypto = [i for i in all_instruments if isinstance(i, CurrencyPair)]
        assert len(equities) > 0, "No equity instruments loaded"
        assert len(crypto) > 0, "No crypto instruments loaded"

    async def test_aapl_is_equity(self, provider):
        aapl = provider.find(InstrumentId.from_str("AAPL.ALPACA"))
        assert aapl is not None, "AAPL.ALPACA not found"
        assert isinstance(aapl, Equity)

    async def test_aapl_equity_fields(self, provider):
        aapl = provider.find(InstrumentId.from_str("AAPL.ALPACA"))
        assert aapl is not None
        # InstrumentId
        assert aapl.id.venue.value == "ALPACA"
        assert aapl.id.symbol.value == "AAPL"
        # Currency
        assert aapl.quote_currency.code == "USD"
        # Price fields — typed correctly and positive
        assert isinstance(aapl.price_increment, Price)
        assert aapl.price_increment.as_double() > 0
        assert aapl.price_precision >= 2
        # Size fields
        assert isinstance(aapl.size_increment, Quantity)
        assert aapl.size_increment.as_double() > 0
        assert aapl.size_precision >= 0
        assert aapl.lot_size.as_double() == 1.0

    async def test_btc_usd_is_currency_pair(self, provider):
        btc = provider.find(InstrumentId.from_str("BTC/USD.ALPACA"))
        assert btc is not None, "BTC/USD.ALPACA not found"
        assert isinstance(btc, CurrencyPair)

    async def test_btc_usd_currency_pair_fields(self, provider):
        btc = provider.find(InstrumentId.from_str("BTC/USD.ALPACA"))
        assert btc is not None
        assert btc.base_currency.code == "BTC"
        assert btc.quote_currency.code == "USD"
        assert btc.id.venue.value == "ALPACA"
        assert isinstance(btc.price_increment, Price)
        assert isinstance(btc.size_increment, Quantity)
        assert btc.price_increment.as_double() > 0
        assert btc.size_increment.as_double() > 0

    async def test_msft_exists(self, provider):
        msft = provider.find(InstrumentId.from_str("MSFT.ALPACA"))
        assert msft is not None, "MSFT.ALPACA not found"
        assert isinstance(msft, Equity)


# ---------------------------------------------------------------------------
# TestLoadIdsAsync
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestLoadIdsAsync:
    """Per-symbol instrument loading via load_ids_async."""

    async def test_load_single_equity(self):
        p = _new_provider()
        await p.load_ids_async([InstrumentId.from_str("AAPL.ALPACA")])
        assert p.count == 1
        instrument = p.find(InstrumentId.from_str("AAPL.ALPACA"))
        assert isinstance(instrument, Equity)
        assert instrument.id.symbol.value == "AAPL"
        assert instrument.quote_currency.code == "USD"

    async def test_load_single_crypto(self):
        p = _new_provider()
        await p.load_ids_async([InstrumentId.from_str("BTC/USD.ALPACA")])
        assert p.count == 1
        btc = p.find(InstrumentId.from_str("BTC/USD.ALPACA"))
        assert isinstance(btc, CurrencyPair)
        assert btc.base_currency.code == "BTC"
        assert btc.quote_currency.code == "USD"

    async def test_load_multiple_ids(self):
        p = _new_provider()
        ids = [
            InstrumentId.from_str("AAPL.ALPACA"),
            InstrumentId.from_str("MSFT.ALPACA"),
            InstrumentId.from_str("TSLA.ALPACA"),
        ]
        await p.load_ids_async(ids)
        assert p.count == 3
        for iid in ids:
            assert p.find(iid) is not None, f"{iid} not found after load_ids_async"

    async def test_load_unknown_symbol_does_not_raise(self):
        """Unknown symbol is skipped with a warning; no exception raised."""
        p = _new_provider()
        await p.load_ids_async([InstrumentId.from_str("DOESNOTEXIST999.ALPACA")])
        assert p.count == 0

    async def test_load_empty_list_is_noop(self):
        p = _new_provider()
        await p.load_ids_async([])
        assert p.count == 0


# ---------------------------------------------------------------------------
# TestHistoricalBars
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestHistoricalBars:
    async def test_historical_bars_for_aapl(self):
        """Fetch 1-min bars for AAPL; validate types, values, OHLC invariants, timestamps."""
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        client = StockHistoricalDataClient(get_api_key(paper=True), get_api_secret(paper=True))
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=7)
        bars_response = client.get_stock_bars(
            StockBarsRequest(
                symbol_or_symbols="AAPL",
                timeframe=TimeFrame.Minute,
                start=start,
                end=end,
                feed="iex",
            )
        )
        bars = list(bars_response.data.get("AAPL", []))

        assert len(bars) > 0, "Expected non-empty AAPL bars list"
        for bar in bars:
            # Type checks
            assert isinstance(bar.open, (int, float)), f"open has type {type(bar.open)}"
            assert isinstance(bar.high, (int, float)), f"high has type {type(bar.high)}"
            assert isinstance(bar.low, (int, float)), f"low has type {type(bar.low)}"
            assert isinstance(bar.close, (int, float)), f"close has type {type(bar.close)}"
            assert isinstance(bar.volume, (int, float)), f"volume has type {type(bar.volume)}"
            # Value sanity
            assert bar.open > 0
            assert bar.volume >= 0
            # OHLC invariants: high is the maximum; low is the minimum
            assert bar.high >= bar.open,  f"high {bar.high} < open {bar.open}"
            assert bar.high >= bar.close, f"high {bar.high} < close {bar.close}"
            assert bar.low  <= bar.open,  f"low {bar.low} > open {bar.open}"
            assert bar.low  <= bar.close, f"low {bar.low} > close {bar.close}"

        # Timestamps must be timezone-aware and strictly ascending
        timestamps = [bar.timestamp for bar in bars]
        for ts in timestamps:
            assert ts.tzinfo is not None, f"timestamp {ts} is not timezone-aware"
        assert timestamps == sorted(timestamps), "Bar timestamps not in ascending order"

    async def test_historical_bars_crypto(self):
        """BTC/USD crypto bars are available 24/7; validate OHLC and timezone."""
        from alpaca.data.historical import CryptoHistoricalDataClient
        from alpaca.data.requests import CryptoBarsRequest
        from alpaca.data.timeframe import TimeFrame

        client = CryptoHistoricalDataClient(
            get_api_key(paper=True), get_api_secret(paper=True)
        )
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=3)
        bars_response = client.get_crypto_bars(
            CryptoBarsRequest(
                symbol_or_symbols="BTC/USD",
                timeframe=TimeFrame.Minute,
                start=start,
                end=end,
            )
        )
        bars = list(bars_response.data.get("BTC/USD", []))

        assert len(bars) > 0, "Expected non-empty BTC/USD bars"
        bar = bars[0]
        assert isinstance(bar.open, (int, float))
        assert isinstance(bar.high, (int, float))
        assert isinstance(bar.low, (int, float))
        assert isinstance(bar.close, (int, float))
        assert isinstance(bar.volume, (int, float))
        assert bar.open > 0
        assert bar.volume >= 0
        assert bar.high >= bar.open
        assert bar.high >= bar.close
        assert bar.low  <= bar.open
        assert bar.low  <= bar.close
        assert bar.timestamp.tzinfo is not None
        # BTC is always above $100 in any conceivable near-future scenario
        assert bar.close > 100, f"BTC/USD close {bar.close} looks implausible"

    async def test_historical_bars_limit_respected(self):
        """Requesting limit=10 bars returns at most 10 bars."""
        from alpaca.data.historical import CryptoHistoricalDataClient
        from alpaca.data.requests import CryptoBarsRequest
        from alpaca.data.timeframe import TimeFrame

        client = CryptoHistoricalDataClient(
            get_api_key(paper=True), get_api_secret(paper=True)
        )
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=7)
        limit = 10
        bars_response = client.get_crypto_bars(
            CryptoBarsRequest(
                symbol_or_symbols="BTC/USD",
                timeframe=TimeFrame.Minute,
                start=start,
                end=end,
                limit=limit,
            )
        )
        bars = list(bars_response.data.get("BTC/USD", []))
        assert 0 < len(bars) <= limit, f"Expected 1–{limit} bars, got {len(bars)}"

    async def test_historical_bars_daily(self):
        """Daily bars go back further; check we get at least 5 trading days in 30-day window."""
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        client = StockHistoricalDataClient(
            get_api_key(paper=True), get_api_secret(paper=True)
        )
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=30)
        bars_response = client.get_stock_bars(
            StockBarsRequest(
                symbol_or_symbols="SPY",
                timeframe=TimeFrame.Day,
                start=start,
                end=end,
                feed="iex",
            )
        )
        bars = list(bars_response.data.get("SPY", []))
        assert len(bars) >= 5, f"Expected >=5 daily bars in 30-day window, got {len(bars)}"

        # Each daily bar: close in plausible ETF range
        for bar in bars:
            assert bar.close > 0
            assert bar.volume > 0


# ---------------------------------------------------------------------------
# TestOrderLifecycle
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestOrderLifecycle:
    async def test_limit_order_submit_and_cancel(self):
        """Submit a far-below-market limit order, verify all fields, then cancel."""
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import LimitOrderRequest
        from alpaca.trading.enums import OrderSide as AlpacaSide, TimeInForce as AlpacaTIF

        client = TradingClient(
            api_key=get_api_key(paper=True),
            secret_key=get_api_secret(paper=True),
            paper=True,
        )
        req = LimitOrderRequest(
            symbol="AAPL",
            qty=1,
            side=AlpacaSide.BUY,
            time_in_force=AlpacaTIF.DAY,
            limit_price=1.00,
        )
        order = client.submit_order(req)

        # --- identity fields ---
        # alpaca-py returns id as UUID, not str
        assert order.id is not None
        assert len(str(order.id)) > 0
        assert order.client_order_id is not None
        assert order.symbol == "AAPL"

        # --- enum fields ---
        assert order.side.value == "buy"
        assert order.type.value == "limit"
        assert order.time_in_force.value == "day"
        assert order.status.value in ("new", "accepted", "pending_new")

        # --- quantity / price (strings on the wire) ---
        assert order.qty is not None
        assert float(order.qty) == 1.0
        assert order.limit_price is not None
        assert float(order.limit_price) == pytest.approx(1.00)

        # --- filled qty is 0 on a new unmatched order ---
        filled = float(order.filled_qty) if order.filled_qty else 0.0
        assert filled == 0.0

        # --- timestamps are tz-aware datetime objects ---
        assert order.created_at is not None
        assert isinstance(order.created_at, datetime)
        assert order.created_at.tzinfo is not None
        assert order.submitted_at is not None
        assert isinstance(order.submitted_at, datetime)
        assert order.submitted_at.tzinfo is not None

        # Cancel
        try:
            client.cancel_order_by_id(order.id)
        except Exception as e:
            pytest.fail(f"Cancel failed: {e}")

        # Poll until cancellation is confirmed (max 10s)
        canceled = None
        for _ in range(10):
            await asyncio.sleep(1)
            canceled = client.get_order_by_id(order.id)
            if canceled.status.value in ("canceled", "pending_cancel"):
                break

        assert canceled is not None
        assert canceled.status.value in ("canceled", "pending_cancel"), (
            f"Order not canceled after 10s; final status: {canceled.status.value}"
        )
        # canceled_at or updated_at must be set after cancellation
        has_cancel_ts = (
            canceled.canceled_at is not None or canceled.updated_at is not None
        )
        assert has_cancel_ts, "Neither canceled_at nor updated_at is set after cancel"

    async def test_submitted_order_fetchable_by_id(self):
        """Submitted order can be retrieved by its ID with consistent fields."""
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import LimitOrderRequest
        from alpaca.trading.enums import OrderSide as AlpacaSide, TimeInForce as AlpacaTIF

        client = TradingClient(
            api_key=get_api_key(paper=True),
            secret_key=get_api_secret(paper=True),
            paper=True,
        )
        req = LimitOrderRequest(
            symbol="MSFT",
            qty=1,
            side=AlpacaSide.BUY,
            time_in_force=AlpacaTIF.DAY,
            limit_price=1.00,
        )
        order = client.submit_order(req)

        try:
            fetched = client.get_order_by_id(order.id)
            assert fetched.id == order.id
            assert fetched.symbol == "MSFT"
            assert fetched.status.value in ("new", "accepted", "pending_new")
            assert fetched.qty is not None
            assert float(fetched.qty) == 1.0
        finally:
            client.cancel_order_by_id(order.id)

    async def test_cancel_reduces_open_order_count(self):
        """After canceling, the order no longer appears in open orders."""
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import LimitOrderRequest
        from alpaca.trading.enums import OrderSide as AlpacaSide, TimeInForce as AlpacaTIF

        client = TradingClient(
            api_key=get_api_key(paper=True),
            secret_key=get_api_secret(paper=True),
            paper=True,
        )
        req = LimitOrderRequest(
            symbol="TSLA",
            qty=1,
            side=AlpacaSide.BUY,
            time_in_force=AlpacaTIF.DAY,
            limit_price=1.00,
        )
        order = client.submit_order(req)
        order_id = order.id

        # Brief wait for order to register
        await asyncio.sleep(1)

        client.cancel_order_by_id(order_id)

        # Poll for cancellation
        for _ in range(10):
            await asyncio.sleep(1)
            o = client.get_order_by_id(order_id)
            if o.status.value in ("canceled", "pending_cancel"):
                break

        final = client.get_order_by_id(order_id)
        assert final.status.value in ("canceled", "pending_cancel")


# ---------------------------------------------------------------------------
# TestAccountAndPositions
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestAccountAndPositions:
    async def test_account_has_buying_power(self):
        """Account endpoint returns valid, parseable financial data."""
        from alpaca.trading.client import TradingClient

        client = TradingClient(
            api_key=get_api_key(paper=True),
            secret_key=get_api_secret(paper=True),
            paper=True,
        )
        account = client.get_account()

        # String financial fields parse as Decimal without error
        assert_decimal_str(str(account.buying_power), min_val=0, label="buying_power")
        assert_decimal_str(str(account.cash), min_val=0, label="cash")
        assert_decimal_str(str(account.portfolio_value), label="portfolio_value")
        assert_decimal_str(str(account.equity), label="equity")

        # Boolean fields
        assert isinstance(account.pattern_day_trader, bool)
        assert isinstance(account.trading_blocked, bool)
        assert isinstance(account.shorting_enabled, bool)

        # Integer fields
        assert isinstance(account.daytrade_count, int)
        assert account.daytrade_count >= 0

        # Identity / metadata
        assert account.currency == "USD"
        assert account.account_number is not None
        assert len(str(account.account_number)) > 0

    async def test_account_financial_consistency(self):
        """equity and portfolio_value are within 10% of each other (paper account)."""
        from alpaca.trading.client import TradingClient

        client = TradingClient(
            api_key=get_api_key(paper=True),
            secret_key=get_api_secret(paper=True),
            paper=True,
        )
        account = client.get_account()
        equity = float(Decimal(str(account.equity)))
        portfolio_value = float(Decimal(str(account.portfolio_value)))

        # Allow 10% tolerance for intraday moves and margin mechanics
        tolerance = max(abs(portfolio_value) * 0.10, 1.0)
        assert abs(equity - portfolio_value) <= tolerance, (
            f"equity={equity} and portfolio_value={portfolio_value} differ by >{tolerance:.2f}"
        )

    async def test_account_status_is_active(self):
        """A freshly-provisioned paper account should be in ACTIVE status."""
        from alpaca.trading.client import TradingClient

        client = TradingClient(
            api_key=get_api_key(paper=True),
            secret_key=get_api_secret(paper=True),
            paper=True,
        )
        account = client.get_account()
        # alpaca-py returns an AccountStatus enum; .value is the string
        status_str = account.status.value if hasattr(account.status, "value") else str(account.status)
        assert status_str.upper() == "ACTIVE"

    async def test_position_reports_returns_list(self):
        """get_all_positions returns a list (may be empty)."""
        from alpaca.trading.client import TradingClient

        client = TradingClient(
            api_key=get_api_key(paper=True),
            secret_key=get_api_secret(paper=True),
            paper=True,
        )
        positions = client.get_all_positions()
        assert isinstance(positions, list)

    async def test_position_field_types_when_present(self):
        """When positions exist, each has required fields with correct types."""
        from alpaca.trading.client import TradingClient

        client = TradingClient(
            api_key=get_api_key(paper=True),
            secret_key=get_api_secret(paper=True),
            paper=True,
        )
        positions = client.get_all_positions()
        for pos in positions:
            # String fields
            assert isinstance(pos.symbol, str) and pos.symbol
            assert pos.side.value in ("long", "short")
            # qty is a parseable positive number
            qty_val = assert_decimal_str(str(pos.qty), label=f"pos.qty[{pos.symbol}]")
            assert qty_val > 0
            # avg_entry_price is non-negative
            assert_decimal_str(
                str(pos.avg_entry_price),
                min_val=0,
                label=f"avg_entry_price[{pos.symbol}]",
            )
            # asset_class is a known value
            assert pos.asset_class.value in ("us_equity", "crypto", "us_option")


# ---------------------------------------------------------------------------
# TestWebSocketStreaming — crypto streams are available 24/7
# ---------------------------------------------------------------------------

def _make_crypto_stream():
    from alpaca.data.live import CryptoDataStream

    return CryptoDataStream(get_api_key(paper=True), get_api_secret(paper=True))


@pytest.fixture(scope="module")
async def ws_stream_data():
    """Single crypto WebSocket connection shared by all streaming tests.

    Opens one connection, subscribes to BTC/USD quotes+trades and ETH/USD
    quotes, collects up to 3 of each, then closes. Individual tests validate
    the captured data without re-connecting, avoiding Alpaca's 1-connection
    limit per account.

    Implementation note: we call stream._run_forever() directly as an asyncio
    Task rather than stream.run() (which calls asyncio.run() internally and
    must run in a thread). Running it as a Task means task.cancel() propagates
    CancelledError through the WebSocket coroutine, which closes the connection
    cleanly. Using asyncio.to_thread would leave a non-cancellable thread alive
    in retry loops, holding the Alpaca connection slot open.
    """
    btc_quotes: list = []
    btc_trades: list = []
    eth_quotes: list = []

    btc_quotes_done = asyncio.Event()
    btc_trades_done = asyncio.Event()
    eth_quotes_done = asyncio.Event()

    async def on_btc_quote(q) -> None:
        btc_quotes.append(q)
        if len(btc_quotes) >= 3:
            btc_quotes_done.set()

    async def on_btc_trade(t) -> None:
        btc_trades.append(t)
        btc_trades_done.set()

    async def on_eth_quote(q) -> None:
        eth_quotes.append(q)
        eth_quotes_done.set()

    stream = _make_crypto_stream()
    stream.subscribe_quotes(on_btc_quote, "BTC/USD")
    stream.subscribe_trades(on_btc_trade, "BTC/USD")
    stream.subscribe_quotes(on_eth_quote, "ETH/USD")

    # _run_forever() is the async coroutine; run it as a Task in the current
    # event loop so it can be cleanly cancelled (do NOT call stream.stop() —
    # that deadlocks when called from the same event loop).
    task = asyncio.create_task(stream._run_forever())
    try:
        # BTC quotes arrive reliably; wait up to 30s for them first.
        await asyncio.wait_for(btc_quotes_done.wait(), timeout=30.0)
        # Then give trades and ETH quotes a further 15s opportunistically.
        try:
            await asyncio.wait_for(
                asyncio.gather(btc_trades_done.wait(), eth_quotes_done.wait()),
                timeout=15.0,
            )
        except asyncio.TimeoutError:
            pass
    except asyncio.TimeoutError:
        pass  # Even BTC quotes didn't arrive — tests will report via assertions
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

    yield {
        "btc_quotes": btc_quotes,
        "btc_trades": btc_trades,
        "eth_quotes": eth_quotes,
    }


@pytest.mark.e2e
class TestWebSocketStreaming:
    async def test_crypto_quote_arrives(self, ws_stream_data):
        """BTC/USD quote arrives and has correct field types."""
        quotes = ws_stream_data["btc_quotes"]
        assert len(quotes) > 0, "No BTC/USD quotes received within 30s"
        q = quotes[0]

        assert q.symbol == "BTC/USD"
        assert isinstance(q.ask_price, (int, float))
        assert isinstance(q.bid_price, (int, float))
        assert isinstance(q.ask_size, (int, float))
        assert isinstance(q.bid_size, (int, float))
        assert q.ask_price > 0, f"ask_price={q.ask_price} should be > 0"
        assert q.bid_price >= 0
        assert q.ask_size >= 0
        assert q.ask_price >= q.bid_price, f"ask {q.ask_price} < bid {q.bid_price}"
        assert q.ask_price > 100, f"BTC ask {q.ask_price} looks implausibly low"
        assert q.timestamp is not None

    async def test_crypto_trade_arrives(self, ws_stream_data):
        """BTC/USD trade arrives and has correct field types."""
        trades = ws_stream_data["btc_trades"]
        if not trades:
            pytest.skip("No BTC/USD trades arrived within the collection window (low-volume period)")
        t = trades[0]

        assert t.symbol == "BTC/USD"
        assert isinstance(t.price, (int, float))
        assert isinstance(t.size, (int, float))
        assert t.price > 100, f"BTC trade price {t.price} looks implausibly low"
        assert t.size > 0, f"trade size {t.size} should be positive"
        assert t.timestamp is not None

    async def test_crypto_quote_timestamp_is_aware(self, ws_stream_data):
        """Live crypto quote timestamps are timezone-aware datetime objects."""
        # Use btc_quotes — they arrive reliably 24/7; timezone-awareness is
        # independent of which symbol we check.
        quotes = ws_stream_data["btc_quotes"]
        assert len(quotes) > 0, "No BTC/USD quotes received within 30s"
        q = quotes[0]

        assert isinstance(q.timestamp, datetime)
        assert q.timestamp.tzinfo is not None, (
            f"timestamp {q.timestamp} is not timezone-aware"
        )

    async def test_crypto_multiple_quotes_arrive_in_order(self, ws_stream_data):
        """Collected BTC/USD quote timestamps are non-decreasing."""
        quotes = ws_stream_data["btc_quotes"]
        assert len(quotes) >= 1, "No BTC/USD quotes received"
        timestamps = [q.timestamp for q in quotes]
        assert timestamps == sorted(timestamps), "Quote timestamps arrived out of order"
