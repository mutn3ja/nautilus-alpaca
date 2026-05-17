"""
AlpacaDataClient — LiveMarketDataClient implementation for Alpaca Markets.

Connects to Alpaca's WebSocket streams for real-time quotes, trades, and 1-minute bars,
and serves historical bar requests via the alpaca-py REST API.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.data.messages import (
    RequestBars,
    RequestInstrument,
    RequestInstruments,
    SubscribeBars,
    SubscribeInstrument,
    SubscribeInstruments,
    SubscribeQuoteTicks,
    SubscribeTradeTicks,
    UnsubscribeBars,
    UnsubscribeInstrument,
    UnsubscribeInstruments,
    UnsubscribeQuoteTicks,
    UnsubscribeTradeTicks,
)
from nautilus_trader.live.data_client import LiveMarketDataClient
from nautilus_trader.model.data import Bar, BarSpecification, BarType, QuoteTick, TradeTick
from nautilus_trader.model.enums import (
    AggregationSource,
    AggressorSide,
    BarAggregation,
    PriceType,
)
from nautilus_trader.model.identifiers import ClientId, InstrumentId, Symbol, TradeId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Price, Quantity

from nautilus_alpaca.common.constants import ALPACA_CLIENT_ID, ALPACA_VENUE
from nautilus_alpaca.common.enums import AlpacaEnvironment
from nautilus_alpaca.config import AlpacaDataClientConfig
from nautilus_alpaca.providers import AlpacaInstrumentProvider


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def _ts_ns(dt: datetime | str | None) -> int:
    """Convert an Alpaca timestamp to nautilus nanoseconds (int)."""
    if dt is None:
        return 0
    if isinstance(dt, str):
        # RFC 3339 / ISO 8601 string
        dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1e9)


# ---------------------------------------------------------------------------
# TimeFrame mapping
# ---------------------------------------------------------------------------

def _bar_aggregation_to_alpaca_timeframe(aggregation: BarAggregation):
    """Map a nautilus BarAggregation to an alpaca-py TimeFrame."""
    # Import lazily to avoid hard import at module level failing if alpaca-py is absent
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit  # noqa: PLC0415

    _MAP = {
        BarAggregation.MINUTE: TimeFrame(1, TimeFrameUnit.Minute),  # type: ignore[arg-type]
        BarAggregation.HOUR: TimeFrame(1, TimeFrameUnit.Hour),  # type: ignore[arg-type]
        BarAggregation.DAY: TimeFrame(1, TimeFrameUnit.Day),  # type: ignore[arg-type]
        BarAggregation.WEEK: TimeFrame(1, TimeFrameUnit.Week),  # type: ignore[arg-type]
        BarAggregation.MONTH: TimeFrame(1, TimeFrameUnit.Month),  # type: ignore[arg-type]
    }
    return _MAP.get(aggregation)


class AlpacaDataClient(LiveMarketDataClient):
    """
    Provides a live market data client for the Alpaca exchange.

    Connects to Alpaca's WebSocket streams (stocks and crypto) for real-time
    quotes, trades, and 1-minute bars. Serves historical bar requests via
    the Alpaca REST API (alpaca-py).

    Parameters
    ----------
    loop : asyncio.AbstractEventLoop
        The event loop for the client.
    msgbus : MessageBus
        The message bus for the client.
    cache : Cache
        The cache for the client.
    clock : LiveClock
        The clock for the client.
    instrument_provider : AlpacaInstrumentProvider
        The instrument provider.
    config : AlpacaDataClientConfig
        The configuration for the client.
    api_key : str
        The Alpaca API public key.
    api_secret : str
        The Alpaca API secret key.
    environment : AlpacaEnvironment
        The Alpaca environment (LIVE or PAPER).
    name : str, optional
        A custom client ID name (defaults to "ALPACA").

    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
        instrument_provider: AlpacaInstrumentProvider,
        config: AlpacaDataClientConfig,
        api_key: str,
        api_secret: str,
        environment: AlpacaEnvironment,
        name: str | None = None,
    ) -> None:
        super().__init__(
            loop=loop,
            client_id=ClientId(name or ALPACA_CLIENT_ID.value),
            venue=config.venue if hasattr(config, "venue") else ALPACA_VENUE,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=instrument_provider,
        )

        self._config = config
        self._api_key = api_key
        self._api_secret = api_secret
        self._environment = environment

        # alpaca-py streaming clients (created lazily in _connect)
        self._stock_stream = None
        self._crypto_stream = None

        # Background tasks
        self._stock_stream_task: asyncio.Task[None] | None = None
        self._crypto_stream_task: asyncio.Task[None] | None = None
        self._update_instruments_task: asyncio.Task[None] | None = None

        # Hot caches
        self._instrument_ids: dict[str, InstrumentId] = {}
        # Track bar_types by symbol so WS bar handler can look them up
        self._subscribed_bar_types: dict[str, BarType] = {}

    # -------------------------------------------------------------------------
    # Connection lifecycle
    # -------------------------------------------------------------------------

    async def _connect(self) -> None:
        self._log.info("Connecting AlpacaDataClient...")

        # Load instruments (idempotent — skips if already loaded)
        await self._instrument_provider.initialize()
        self._send_all_instruments_to_data_engine()

        # Create alpaca-py streaming clients
        from alpaca.data.enums import DataFeed  # noqa: PLC0415
        from alpaca.data.live import CryptoDataStream, StockDataStream  # noqa: PLC0415

        feed = DataFeed.IEX if self._config.feed == "iex" else DataFeed.SIP

        self._stock_stream = StockDataStream(
            api_key=self._api_key,
            secret_key=self._api_secret,
            feed=feed,
        )
        self._crypto_stream = CryptoDataStream(
            api_key=self._api_key,
            secret_key=self._api_secret,
        )

        self._log.info(f"Feed: {self._config.feed.upper()}")

        # Periodic instrument refresh
        if self._config.update_instruments_interval_mins:
            self._update_instruments_task = self.create_task(
                self._update_instruments(self._config.update_instruments_interval_mins),
            )

        self._log.info("AlpacaDataClient connected.")

    async def _disconnect(self) -> None:
        self._log.info("Disconnecting AlpacaDataClient...")

        # Cancel periodic update task
        if self._update_instruments_task:
            self._update_instruments_task.cancel()
            try:
                await self._update_instruments_task
            except asyncio.CancelledError:
                pass
            self._update_instruments_task = None

        # Stop stock stream
        if self._stock_stream_task:
            self._stock_stream_task.cancel()
            try:
                await self._stock_stream_task
            except asyncio.CancelledError:
                pass
            self._stock_stream_task = None

        if self._stock_stream is not None:
            try:
                await self._stock_stream.stop_ws()
            except Exception as e:
                self._log.warning(f"Error stopping stock stream: {e}")
            self._stock_stream = None

        # Stop crypto stream
        if self._crypto_stream_task:
            self._crypto_stream_task.cancel()
            try:
                await self._crypto_stream_task
            except asyncio.CancelledError:
                pass
            self._crypto_stream_task = None

        if self._crypto_stream is not None:
            try:
                await self._crypto_stream.stop_ws()
            except Exception as e:
                self._log.warning(f"Error stopping crypto stream: {e}")
            self._crypto_stream = None

        self._log.info("AlpacaDataClient disconnected.")

    # -------------------------------------------------------------------------
    # Instrument dispatch helpers
    # -------------------------------------------------------------------------

    def _send_all_instruments_to_data_engine(self) -> None:
        for instrument in self._instrument_provider.get_all().values():
            self._handle_data(instrument)

        for currency in self._instrument_provider.currencies().values():
            self._cache.add_currency(currency)

    async def _update_instruments(self, interval_mins: int) -> None:
        """Periodically reload instruments from the Alpaca Assets API."""
        while True:
            try:
                self._log.debug(
                    f"Scheduled task 'update_instruments' to run in {interval_mins} minutes",
                )
                await asyncio.sleep(interval_mins * 60)
                await self._instrument_provider.initialize(reload=True)
                self._send_all_instruments_to_data_engine()
            except asyncio.CancelledError:
                self._log.debug("Canceled task 'update_instruments'")
                return
            except Exception as e:
                self._log.error(f"Error updating instruments: {e}")

    # -------------------------------------------------------------------------
    # Symbol / InstrumentId helpers
    # -------------------------------------------------------------------------

    def _get_instrument_id(self, symbol: str) -> InstrumentId:
        """Return a cached InstrumentId for the given Alpaca symbol."""
        instrument_id = self._instrument_ids.get(symbol)
        if instrument_id is None:
            instrument_id = InstrumentId(Symbol(symbol), self.venue)
            self._instrument_ids[symbol] = instrument_id
        return instrument_id

    def _is_crypto_symbol(self, symbol: str) -> bool:
        """Return True if the symbol looks like a crypto pair (contains '/')."""
        return "/" in symbol

    def _ensure_stock_stream_running(self) -> None:
        """Start the stock stream background task if not already running."""
        if self._stock_stream is not None and self._stock_stream_task is None:
            self._stock_stream_task = self.create_task(self._stock_stream._run_forever())
            self._log.info("Stock WebSocket stream started.")

    def _ensure_crypto_stream_running(self) -> None:
        """Start the crypto stream background task if not already running."""
        if self._crypto_stream is not None and self._crypto_stream_task is None:
            self._crypto_stream_task = self.create_task(self._crypto_stream._run_forever())
            self._log.info("Crypto WebSocket stream started.")

    # -------------------------------------------------------------------------
    # Subscriptions — quote ticks
    # -------------------------------------------------------------------------

    async def _subscribe_quote_ticks(self, command: SubscribeQuoteTicks) -> None:
        symbol = command.instrument_id.symbol.value
        self._log.info(f"Subscribing to quote ticks for {symbol}")

        if self._is_crypto_symbol(symbol):
            if self._crypto_stream is None:
                self._log.error("Crypto stream not initialised — call _connect first")
                return
            self._crypto_stream.subscribe_quotes(self._handle_ws_quote, symbol)
            self._ensure_crypto_stream_running()
        else:
            if self._stock_stream is None:
                self._log.error("Stock stream not initialised — call _connect first")
                return
            self._stock_stream.subscribe_quotes(self._handle_ws_quote, symbol)
            self._ensure_stock_stream_running()

    async def _unsubscribe_quote_ticks(self, command: UnsubscribeQuoteTicks) -> None:
        symbol = command.instrument_id.symbol.value
        self._log.info(f"Unsubscribing from quote ticks for {symbol}")

        if self._is_crypto_symbol(symbol):
            if self._crypto_stream is not None:
                self._crypto_stream.unsubscribe_quotes(symbol)
        else:
            if self._stock_stream is not None:
                self._stock_stream.unsubscribe_quotes(symbol)

    # -------------------------------------------------------------------------
    # Subscriptions — trade ticks
    # -------------------------------------------------------------------------

    async def _subscribe_trade_ticks(self, command: SubscribeTradeTicks) -> None:
        symbol = command.instrument_id.symbol.value
        self._log.info(f"Subscribing to trade ticks for {symbol}")

        if self._is_crypto_symbol(symbol):
            if self._crypto_stream is None:
                self._log.error("Crypto stream not initialised — call _connect first")
                return
            self._crypto_stream.subscribe_trades(self._handle_ws_trade, symbol)
            self._ensure_crypto_stream_running()
        else:
            if self._stock_stream is None:
                self._log.error("Stock stream not initialised — call _connect first")
                return
            self._stock_stream.subscribe_trades(self._handle_ws_trade, symbol)
            self._ensure_stock_stream_running()

    async def _unsubscribe_trade_ticks(self, command: UnsubscribeTradeTicks) -> None:
        symbol = command.instrument_id.symbol.value
        self._log.info(f"Unsubscribing from trade ticks for {symbol}")

        if self._is_crypto_symbol(symbol):
            if self._crypto_stream is not None:
                self._crypto_stream.unsubscribe_trades(symbol)
        else:
            if self._stock_stream is not None:
                self._stock_stream.unsubscribe_trades(symbol)

    # -------------------------------------------------------------------------
    # Subscriptions — bars
    # -------------------------------------------------------------------------

    async def _subscribe_bars(self, command: SubscribeBars) -> None:
        bar_type = command.bar_type
        instrument_id = bar_type.instrument_id
        symbol = instrument_id.symbol.value

        # Alpaca WS only provides 1-minute bars
        if (
            bar_type.spec.aggregation != BarAggregation.MINUTE
            or bar_type.spec.step != 1
        ):
            self._log.warning(
                f"Alpaca WebSocket only supports 1-MINUTE bars; "
                f"ignoring bar subscription for {bar_type}. "
                "Use _request_bars for other resolutions.",
            )
            return

        self._log.info(f"Subscribing to 1-MINUTE bars for {symbol}")
        self._subscribed_bar_types[symbol] = bar_type

        if self._is_crypto_symbol(symbol):
            if self._crypto_stream is None:
                self._log.error("Crypto stream not initialised — call _connect first")
                return
            self._crypto_stream.subscribe_bars(self._handle_ws_bar, symbol)
            self._ensure_crypto_stream_running()
        else:
            if self._stock_stream is None:
                self._log.error("Stock stream not initialised — call _connect first")
                return
            self._stock_stream.subscribe_bars(self._handle_ws_bar, symbol)
            self._ensure_stock_stream_running()

    async def _unsubscribe_bars(self, command: UnsubscribeBars) -> None:
        bar_type = command.bar_type
        symbol = bar_type.instrument_id.symbol.value
        self._subscribed_bar_types.pop(symbol, None)

        self._log.info(f"Unsubscribing from bars for {symbol}")

        if self._is_crypto_symbol(symbol):
            if self._crypto_stream is not None:
                self._crypto_stream.unsubscribe_bars(symbol)
        else:
            if self._stock_stream is not None:
                self._stock_stream.unsubscribe_bars(symbol)

    # -------------------------------------------------------------------------
    # Subscriptions — instruments (no-op: handled by provider)
    # -------------------------------------------------------------------------

    async def _subscribe_instruments(self, command: SubscribeInstruments) -> None:
        pass  # Instruments are loaded on connect; no streaming feed needed

    async def _unsubscribe_instruments(self, command: UnsubscribeInstruments) -> None:
        pass

    async def _subscribe_instrument(self, command: SubscribeInstrument) -> None:
        pass

    async def _unsubscribe_instrument(self, command: UnsubscribeInstrument) -> None:
        pass

    # -------------------------------------------------------------------------
    # WebSocket handlers (called by alpaca-py with parsed model objects)
    # -------------------------------------------------------------------------

    async def _handle_ws_quote(self, data) -> None:
        """Handle a real-time quote from the alpaca-py streaming client."""
        try:
            symbol: str = data.symbol
            instrument_id = self._get_instrument_id(symbol)
            instrument: Instrument | None = self._cache.instrument(instrument_id)

            price_precision = instrument.price_precision if instrument else 2
            size_precision = instrument.size_precision if instrument else 0

            ts_event = _ts_ns(data.timestamp)
            ts_init = self._clock.timestamp_ns()

            bid_price_raw = float(data.bid_price) if data.bid_price is not None else 0.0
            ask_price_raw = float(data.ask_price) if data.ask_price is not None else 0.0
            bid_size_raw = float(data.bid_size) if data.bid_size is not None else 0.0
            ask_size_raw = float(data.ask_size) if data.ask_size is not None else 0.0

            tick = QuoteTick(
                instrument_id=instrument_id,
                bid_price=Price(bid_price_raw, price_precision),
                ask_price=Price(ask_price_raw, price_precision),
                bid_size=Quantity(bid_size_raw, size_precision),
                ask_size=Quantity(ask_size_raw, size_precision),
                ts_event=ts_event,
                ts_init=ts_init,
            )
            self._handle_data(tick)
        except Exception as e:
            self._log.exception(f"Error handling WS quote: {e}", e)

    async def _handle_ws_trade(self, data) -> None:
        """Handle a real-time trade from the alpaca-py streaming client."""
        try:
            symbol: str = data.symbol
            instrument_id = self._get_instrument_id(symbol)
            instrument: Instrument | None = self._cache.instrument(instrument_id)

            price_precision = instrument.price_precision if instrument else 2
            size_precision = instrument.size_precision if instrument else 0

            ts_event = _ts_ns(data.timestamp)
            ts_init = self._clock.timestamp_ns()

            trade_id_raw = getattr(data, "id", None) or getattr(data, "trade_id", None)
            trade_id = TradeId(str(trade_id_raw) if trade_id_raw is not None else "0")

            tick = TradeTick(
                instrument_id=instrument_id,
                price=Price(float(data.price), price_precision),
                size=Quantity(float(data.size), size_precision),
                aggressor_side=AggressorSide.NO_AGGRESSOR,
                trade_id=trade_id,
                ts_event=ts_event,
                ts_init=ts_init,
            )
            self._handle_data(tick)
        except Exception as e:
            self._log.exception(f"Error handling WS trade: {e}", e)

    async def _handle_ws_bar(self, data) -> None:
        """Handle a real-time 1-minute bar from the alpaca-py streaming client."""
        try:
            symbol: str = data.symbol
            instrument_id = self._get_instrument_id(symbol)
            instrument: Instrument | None = self._cache.instrument(instrument_id)

            price_precision = instrument.price_precision if instrument else 2
            size_precision = instrument.size_precision if instrument else 0

            # Look up the subscribed bar_type for this symbol; default to EXTERNAL 1-MINUTE
            bar_type = self._subscribed_bar_types.get(symbol)
            if bar_type is None:
                bar_type = BarType(
                    instrument_id=instrument_id,
                    bar_spec=BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
                    aggregation_source=AggregationSource.EXTERNAL,
                )

            ts_event = _ts_ns(data.timestamp)
            ts_init = self._clock.timestamp_ns()

            bar = Bar(
                bar_type=bar_type,
                open=Price(float(data.open), price_precision),
                high=Price(float(data.high), price_precision),
                low=Price(float(data.low), price_precision),
                close=Price(float(data.close), price_precision),
                volume=Quantity(float(data.volume), size_precision),
                ts_event=ts_event,
                ts_init=ts_init,
            )
            self._handle_data(bar)
        except Exception as e:
            self._log.exception(f"Error handling WS bar: {e}", e)

    # -------------------------------------------------------------------------
    # Requests
    # -------------------------------------------------------------------------

    async def _request_instrument(self, request: RequestInstrument) -> None:
        instrument: Instrument | None = self._instrument_provider.find(request.instrument_id)
        if instrument is None:
            self._log.error(f"Cannot find instrument for {request.instrument_id}")
            return
        self._handle_instrument(instrument, request.id, request.start, request.end, request.params)

    async def _request_instruments(self, request: RequestInstruments) -> None:
        await self._instrument_provider.load_all_async()
        instruments = list(self._instrument_provider.get_all().values())
        for instrument in instruments:
            self._handle_data(instrument)

    async def _request_bars(self, request: RequestBars) -> None:
        """Fetch historical bars from the Alpaca REST API."""
        bar_type = request.bar_type
        instrument_id = bar_type.instrument_id
        symbol = instrument_id.symbol.value

        # Map aggregation to alpaca TimeFrame
        alpaca_tf = _bar_aggregation_to_alpaca_timeframe(bar_type.spec.aggregation)
        if alpaca_tf is None:
            self._log.error(
                f"Cannot request {bar_type} bars: "
                f"unsupported BarAggregation '{bar_type.spec.aggregation}' for Alpaca REST API. "
                "Supported: MINUTE, HOUR, DAY, WEEK, MONTH.",
            )
            return

        self._log.info(
            f"Requesting historical bars: {bar_type} "
            f"start={request.start} end={request.end} limit={request.limit}",
        )

        try:
            instrument: Instrument | None = self._instrument_provider.find(instrument_id)
            price_precision = instrument.price_precision if instrument else 2
            size_precision = instrument.size_precision if instrument else 0

            if self._is_crypto_symbol(symbol):
                await self._request_crypto_bars(
                    request=request,
                    symbol=symbol,
                    alpaca_tf=alpaca_tf,
                    price_precision=price_precision,
                    size_precision=size_precision,
                )
            else:
                await self._request_stock_bars(
                    request=request,
                    symbol=symbol,
                    alpaca_tf=alpaca_tf,
                    price_precision=price_precision,
                    size_precision=size_precision,
                )
        except Exception as e:
            self._log.exception(f"Error requesting bars for {bar_type}: {e}", e)

    async def _request_stock_bars(
        self,
        request: RequestBars,
        symbol: str,
        alpaca_tf,
        price_precision: int,
        size_precision: int,
    ) -> None:
        from alpaca.data.historical import StockHistoricalDataClient  # noqa: PLC0415
        from alpaca.data.requests import StockBarsRequest  # noqa: PLC0415

        client = StockHistoricalDataClient(
            api_key=self._api_key,
            secret_key=self._api_secret,
        )

        req_kwargs: dict[str, Any] = {
            "symbol_or_symbols": symbol,
            "timeframe": alpaca_tf,
        }
        if request.start is not None:
            req_kwargs["start"] = request.start
        if request.end is not None:
            req_kwargs["end"] = request.end
        if request.limit and request.limit > 0:
            req_kwargs["limit"] = request.limit

        bars_response = client.get_stock_bars(StockBarsRequest(**req_kwargs))
        bars = self._parse_bars_response(
            bars_response=bars_response,
            symbol=symbol,
            bar_type=request.bar_type,
            price_precision=price_precision,
            size_precision=size_precision,
        )

        if not bars:
            self._log.warning(f"No stock bars returned for {request.bar_type}")
            return

        self._handle_bars(
            request.bar_type,
            bars,
            request.id,
            request.start,
            request.end,
            request.params,
        )

    async def _request_crypto_bars(
        self,
        request: RequestBars,
        symbol: str,
        alpaca_tf,
        price_precision: int,
        size_precision: int,
    ) -> None:
        from alpaca.data.historical import CryptoHistoricalDataClient  # noqa: PLC0415
        from alpaca.data.requests import CryptoBarsRequest  # noqa: PLC0415

        client = CryptoHistoricalDataClient(
            api_key=self._api_key,
            secret_key=self._api_secret,
        )

        req_kwargs: dict[str, Any] = {
            "symbol_or_symbols": symbol,
            "timeframe": alpaca_tf,
        }
        if request.start is not None:
            req_kwargs["start"] = request.start
        if request.end is not None:
            req_kwargs["end"] = request.end
        if request.limit and request.limit > 0:
            req_kwargs["limit"] = request.limit

        bars_response = client.get_crypto_bars(CryptoBarsRequest(**req_kwargs))
        bars = self._parse_bars_response(
            bars_response=bars_response,
            symbol=symbol,
            bar_type=request.bar_type,
            price_precision=price_precision,
            size_precision=size_precision,
        )

        if not bars:
            self._log.warning(f"No crypto bars returned for {request.bar_type}")
            return

        self._handle_bars(
            request.bar_type,
            bars,
            request.id,
            request.start,
            request.end,
            request.params,
        )

    def _parse_bars_response(
        self,
        bars_response,
        symbol: str,
        bar_type: BarType,
        price_precision: int,
        size_precision: int,
    ) -> list[Bar]:
        """Convert alpaca-py bar results to a list of nautilus Bar objects."""
        bars: list[Bar] = []
        ts_init = self._clock.timestamp_ns()

        try:
            # bars_response is a BarDataset; access per-symbol data via []
            raw_bars = bars_response[symbol]
        except (KeyError, TypeError):
            # Some versions return the bars directly as an iterable
            try:
                raw_bars = list(bars_response)
            except Exception:
                self._log.warning(f"Could not parse bars response for {symbol}")
                return bars

        for raw_bar in raw_bars:
            try:
                ts_event = _ts_ns(raw_bar.timestamp)
                bar = Bar(
                    bar_type=bar_type,
                    open=Price(float(raw_bar.open), price_precision),
                    high=Price(float(raw_bar.high), price_precision),
                    low=Price(float(raw_bar.low), price_precision),
                    close=Price(float(raw_bar.close), price_precision),
                    volume=Quantity(float(raw_bar.volume), size_precision),
                    ts_event=ts_event,
                    ts_init=ts_init,
                )
                bars.append(bar)
            except Exception as e:
                self._log.warning(f"Failed to parse bar {raw_bar}: {e}")

        return bars
