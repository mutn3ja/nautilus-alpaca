"""
AlpacaExecutionClient — handles order submission, cancellation, modification,
and reconciliation via the Alpaca Trading REST API, plus real-time order status
updates via the Alpaca trading WebSocket (user/trade_updates stream).
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from uuid import UUID

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.execution.messages import (
    CancelAllOrders,
    CancelOrder,
    GenerateFillReports,
    GenerateOrderStatusReport,
    GenerateOrderStatusReports,
    GeneratePositionStatusReports,
    ModifyOrder,
    SubmitOrder,
)
from nautilus_trader.execution.reports import (
    FillReport,
    OrderStatusReport,
    PositionStatusReport,
)
from nautilus_trader.live.execution_client import LiveExecutionClient
from nautilus_trader.model.enums import (
    AccountType,
    LiquiditySide,
    OmsType,
    OrderSide,
    OrderType,
    PositionSide,
    TimeInForce,
    TrailingOffsetType,
    TriggerType,
)
from nautilus_trader.model.identifiers import (
    AccountId,
    ClientId,
    ClientOrderId,
    InstrumentId,
    TradeId,
    VenueOrderId,
)
from nautilus_trader.model.objects import (
    AccountBalance,
    Currency,
    Money,
    Price,
    Quantity,
)
from nautilus_trader.model.orders import (
    LimitOrder,
    MarketOrder,
    Order,
    StopLimitOrder,
    StopMarketOrder,
    TrailingStopMarketOrder,
)

from nautilus_alpaca.common.constants import ALPACA_VENUE
from nautilus_alpaca.common.enums import AlpacaEnvironment
from nautilus_alpaca.common.parsing import (
    alpaca_order_status_to_nautilus,
    alpaca_symbol_to_instrument_id,
    nautilus_order_side_to_alpaca,
    nautilus_order_type_to_alpaca,
)
from nautilus_alpaca.config import AlpacaExecClientConfig
from nautilus_alpaca.providers import AlpacaInstrumentProvider


class AlpacaExecutionClient(LiveExecutionClient):
    """
    Execution client for Alpaca Markets.

    Handles order submission, cancellation, modification, and reconciliation
    via the Alpaca Trading REST API, and processes real-time order status
    updates via the Alpaca TradingStream WebSocket.

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
    config : AlpacaExecClientConfig
        The configuration for the client.
    api_key : str
        The Alpaca API public key.
    api_secret : str
        The Alpaca API secret key.
    environment : AlpacaEnvironment
        The Alpaca environment (LIVE or PAPER).
    name : str, optional
        The custom client ID.

    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
        instrument_provider: AlpacaInstrumentProvider,
        config: AlpacaExecClientConfig,
        api_key: str,
        api_secret: str,
        environment: AlpacaEnvironment,
        name: str | None = None,
    ) -> None:
        super().__init__(
            loop=loop,
            client_id=ClientId(name or "ALPACA"),
            venue=ALPACA_VENUE,
            oms_type=OmsType.NETTING,
            account_type=AccountType.CASH,
            base_currency=None,
            instrument_provider=instrument_provider,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
        )

        self._config = config
        self._api_key = api_key
        self._api_secret = api_secret
        self._environment = environment

        from alpaca.trading.client import TradingClient

        self._client = TradingClient(
            api_key=api_key,
            secret_key=api_secret,
            paper=environment.is_paper,
        )
        self._stream = None
        self._stream_task = None
        self._update_account_task: asyncio.Task[None] | None = None

        # Set account ID
        self._set_account_id(AccountId(f"{name or 'ALPACA'}-{environment.value}-001"))

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    async def _connect(self) -> None:
        """Connect to Alpaca: load instruments, fetch account state, start stream."""
        self._log.info("Connecting to Alpaca...")

        # Load instruments into the provider
        await self._instrument_provider.initialize()

        # Fetch account and update account state
        account = await asyncio.to_thread(self._client.get_account)
        self._update_account_state(account)
        await self._await_account_registered()

        # Initialize TradingStream and start as background task
        from alpaca.trading.stream import TradingStream

        self._stream = TradingStream(
            api_key=self._api_key,
            secret_key=self._api_secret,
            paper=self._environment.is_paper,
        )
        self._stream.subscribe_trade_updates(self._handle_trade_update)
        # Use _run_forever() — the public run() calls asyncio.run() which cannot be used
        # inside an already-running event loop.
        self._stream_task = self.create_task(self._stream._run_forever())

        # Periodic account-state refresh
        interval = self._config.account_polling_interval_mins
        if interval:
            self._update_account_task = self.create_task(
                self._update_account_state_periodic(interval),
            )

        self._log.info("Alpaca ExecutionClient connected.")

    async def _disconnect(self) -> None:
        """Disconnect from Alpaca: stop stream and cancel background tasks."""
        self._log.info("Disconnecting from Alpaca...")

        if self._update_account_task is not None:
            self._update_account_task.cancel()
            try:
                await self._update_account_task
            except asyncio.CancelledError:
                pass
            self._update_account_task = None

        if self._stream is not None:
            try:
                await self._stream.stop_ws()
            except Exception as e:
                self._log.warning(f"Error stopping TradingStream: {e}")

        if self._stream_task is not None:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
            self._stream_task = None

        self._stream = None
        self._log.info("Alpaca ExecutionClient disconnected.")

    # -------------------------------------------------------------------------
    # Account helpers
    # -------------------------------------------------------------------------

    def _update_account_state(self, account) -> None:
        """Build AccountBalance from the Alpaca account object and publish state."""
        try:
            cash = Decimal(str(account.cash))
            buying_power = Decimal(str(account.buying_power))
        except Exception as e:
            self._log.error(f"Failed to parse account balances: {e}")
            return

        currency = Currency.from_str("USD")

        # AccountBalance: total, locked, free
        # For a cash account:
        #   total = equity (or cash + long_market_value)
        #   free  = buying_power (available to trade)
        #   locked = total - free (used by open positions / margin)
        try:
            total = Decimal(str(account.equity))
        except Exception:
            total = cash

        locked = total - buying_power if total >= buying_power else Decimal("0")

        balance = AccountBalance(
            total=Money(total, currency),
            locked=Money(locked, currency),
            free=Money(buying_power, currency),
        )

        self.generate_account_state(
            balances=[balance],
            margins=[],
            reported=True,
            ts_event=self._clock.timestamp_ns(),
        )

    async def _refresh_account_state(self) -> None:
        """Fetch the latest account snapshot from Alpaca and publish it."""
        try:
            account = await asyncio.to_thread(self._client.get_account)
            self._update_account_state(account)
        except Exception as e:
            self._log.warning(f"Failed to refresh account state: {e}")

    async def _update_account_state_periodic(self, interval_mins: int) -> None:
        """Periodically poll the Alpaca account for an updated balance snapshot."""
        while True:
            try:
                await asyncio.sleep(interval_mins * 60)
                await self._refresh_account_state()
            except asyncio.CancelledError:
                self._log.debug("Canceled task 'update_account_state'")
                return
            except Exception as e:
                self._log.error(f"Error in periodic account-state update: {e}")

    # -------------------------------------------------------------------------
    # Retry helper
    # -------------------------------------------------------------------------

    async def _request_with_retry(self, func, *args, **kwargs):
        """
        Run a synchronous Alpaca REST call off the event loop with retries.

        Uses ``max_retries``, ``retry_delay_initial_ms`` and ``retry_delay_max_ms``
        from the client configuration with exponential backoff. Order submission
        is idempotent on ``client_order_id`` (Alpaca rejects duplicates), so
        retrying a submit cannot create a second order.
        """
        max_retries = self._config.max_retries or 0
        delay_ms = self._config.retry_delay_initial_ms or 1_000
        max_delay_ms = self._config.retry_delay_max_ms or 10_000

        attempt = 0
        while True:
            try:
                return await asyncio.to_thread(func, *args, **kwargs)
            except Exception as e:
                if attempt >= max_retries:
                    raise
                attempt += 1
                wait_ms = min(delay_ms, max_delay_ms)
                self._log.warning(
                    f"Retrying {getattr(func, '__name__', func)!r} "
                    f"(attempt {attempt}/{max_retries}) in {wait_ms} ms after error: {e}"
                )
                await asyncio.sleep(wait_ms / 1_000)
                delay_ms = min(delay_ms * 2, max_delay_ms)

    # -------------------------------------------------------------------------
    # Order command handlers
    # -------------------------------------------------------------------------

    async def _submit_order(self, command: SubmitOrder) -> None:
        """Submit an order to Alpaca."""
        order = command.order

        if order.is_closed:
            self._log.warning(f"Cannot submit already closed order {order}")
            return

        # Generate submitted event immediately (before REST call)
        self.generate_order_submitted(
            strategy_id=order.strategy_id,
            instrument_id=order.instrument_id,
            client_order_id=order.client_order_id,
            ts_event=self._clock.timestamp_ns(),
        )

        try:
            request = self._build_order_request(order)
            response = await self._request_with_retry(self._client.submit_order, request)

            venue_order_id = VenueOrderId(str(response.id))  # type: ignore[union-attr]

            self.generate_order_accepted(
                strategy_id=order.strategy_id,
                instrument_id=order.instrument_id,
                client_order_id=order.client_order_id,
                venue_order_id=venue_order_id,
                ts_event=self._clock.timestamp_ns(),
            )

        except Exception as e:
            self._log.error(
                f"Failed to submit order {order.client_order_id}: {e}",
            )
            self.generate_order_rejected(
                strategy_id=order.strategy_id,
                instrument_id=order.instrument_id,
                client_order_id=order.client_order_id,
                reason=str(e),
                ts_event=self._clock.timestamp_ns(),
            )

    def _build_order_request(self, order: Order):
        """Build an alpaca-py order request from a nautilus Order."""
        from alpaca.trading.enums import OrderSide as AlpacaOrderSide
        from alpaca.trading.enums import TimeInForce as AlpacaTIF
        from alpaca.trading.requests import (
            LimitOrderRequest,
            MarketOrderRequest,
            StopLimitOrderRequest,
            StopOrderRequest,
            TrailingStopOrderRequest,
        )

        symbol = order.instrument_id.symbol.value
        side_str = nautilus_order_side_to_alpaca(order.side)
        alpaca_side = AlpacaOrderSide.BUY if side_str == "buy" else AlpacaOrderSide.SELL

        # Determine TIF
        _order_type_str, tif_str = nautilus_order_type_to_alpaca(
            order.order_type, order.time_in_force
        )
        tif_map = {
            "day": AlpacaTIF.DAY,
            "gtc": AlpacaTIF.GTC,
            "ioc": AlpacaTIF.IOC,
            "fok": AlpacaTIF.FOK,
            "opg": AlpacaTIF.OPG,
            "cls": AlpacaTIF.CLS,
        }
        alpaca_tif = tif_map.get(tif_str, AlpacaTIF.DAY)

        # Determine quantity — use int for whole shares, fractional as str
        qty_decimal = Decimal(str(order.quantity))
        if qty_decimal == qty_decimal.to_integral_value():
            qty = int(qty_decimal)
        else:
            qty = float(qty_decimal)

        if isinstance(order, MarketOrder):
            return MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=alpaca_side,
                time_in_force=alpaca_tif,
                client_order_id=order.client_order_id.value,
            )

        elif isinstance(order, LimitOrder):
            return LimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=alpaca_side,
                time_in_force=alpaca_tif,
                limit_price=float(order.price),
                client_order_id=order.client_order_id.value,
            )

        elif isinstance(order, StopMarketOrder):
            return StopOrderRequest(
                symbol=symbol,
                qty=qty,
                side=alpaca_side,
                time_in_force=alpaca_tif,
                stop_price=float(order.trigger_price),
                client_order_id=order.client_order_id.value,
            )

        elif isinstance(order, StopLimitOrder):
            return StopLimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=alpaca_side,
                time_in_force=alpaca_tif,
                stop_price=float(order.trigger_price),
                limit_price=float(order.price),
                client_order_id=order.client_order_id.value,
            )

        elif isinstance(order, TrailingStopMarketOrder):
            # Alpaca trailing stop: use trail_price or trail_percent
            trail_price = float(order.trailing_offset) if order.trailing_offset else None
            return TrailingStopOrderRequest(
                symbol=symbol,
                qty=qty,
                side=alpaca_side,
                time_in_force=alpaca_tif,
                trail_price=trail_price,
                client_order_id=order.client_order_id.value,
            )

        else:
            raise ValueError(f"Unsupported order type for Alpaca: {order.order_type}")

    async def _cancel_order(self, command: CancelOrder) -> None:
        """Cancel a single order by venue_order_id."""
        cached_order = self._cache.order(command.client_order_id)

        venue_order_id = command.venue_order_id
        if venue_order_id is None and cached_order is not None:
            venue_order_id = cached_order.venue_order_id

        if venue_order_id is None:
            self._log.error(
                f"Cannot cancel order {command.client_order_id}: no venue_order_id found"
            )
            return

        if cached_order is not None and cached_order.is_closed:
            self._log.warning(
                f"CancelOrder command for {command.client_order_id!r} when order already "
                f"{cached_order.status_string()} (will not send to exchange)"
            )
            return

        try:
            await self._request_with_retry(
                self._client.cancel_order_by_id, UUID(venue_order_id.value)
            )
            self._log.debug(f"Cancel sent for order {venue_order_id}")
            # The WebSocket "canceled" event will generate the OrderCanceled event
        except Exception as e:
            self._log.error(f"Failed to cancel order {venue_order_id}: {e}")
            self.generate_order_cancel_rejected(
                strategy_id=command.strategy_id,
                instrument_id=command.instrument_id,
                client_order_id=command.client_order_id,
                venue_order_id=venue_order_id,
                reason=str(e),
                ts_event=self._clock.timestamp_ns(),
            )

    async def _cancel_all_orders(self, command: CancelAllOrders) -> None:
        """Cancel all open orders, optionally filtered by instrument_id."""
        if command.instrument_id is not None:
            # Cancel only orders for a specific symbol
            symbol = command.instrument_id.symbol.value
            try:
                from alpaca.trading.requests import GetOrdersRequest
                from alpaca.trading.enums import QueryOrderStatus

                open_orders = await asyncio.to_thread(
                    self._client.get_orders,
                    GetOrdersRequest(
                        status=QueryOrderStatus.OPEN,
                        symbols=[symbol],
                    ),
                )
                for alpaca_order in open_orders:
                    try:
                        await asyncio.to_thread(
                            self._client.cancel_order_by_id, alpaca_order.id  # type: ignore[union-attr]
                        )
                    except Exception as e:
                        self._log.warning(
                            f"Failed to cancel order {alpaca_order.id} for {symbol}: {e}"  # type: ignore[union-attr]
                        )
            except Exception as e:
                self._log.error(f"Failed to fetch/cancel orders for {symbol}: {e}")
        else:
            # Cancel all open orders
            try:
                cancel_responses = await asyncio.to_thread(self._client.cancel_orders)
                self._log.info(
                    f"Canceled {len(cancel_responses) if cancel_responses else 0} open orders"
                )
            except Exception as e:
                self._log.error(f"Failed to cancel all orders: {e}")

    async def _modify_order(self, command: ModifyOrder) -> None:
        """Modify (replace) an existing limit order."""
        from alpaca.trading.requests import ReplaceOrderRequest

        cached_order = self._cache.order(command.client_order_id)
        venue_order_id = command.venue_order_id
        if venue_order_id is None and cached_order is not None:
            venue_order_id = cached_order.venue_order_id

        if venue_order_id is None:
            reason = "no venue_order_id found to modify"
            self._log.error(f"Cannot modify order {command.client_order_id}: {reason}")
            self.generate_order_modify_rejected(
                strategy_id=command.strategy_id,
                instrument_id=command.instrument_id,
                client_order_id=command.client_order_id,
                venue_order_id=command.venue_order_id,
                reason=reason,
                ts_event=self._clock.timestamp_ns(),
            )
            return

        try:
            qty = (
                str(command.quantity)
                if command.quantity
                else None
            )
            limit_price = (
                str(command.price.as_double())
                if command.price
                else None
            )
            req = ReplaceOrderRequest(qty=qty, limit_price=limit_price)  # type: ignore[arg-type]
            await self._request_with_retry(
                self._client.replace_order_by_id, UUID(venue_order_id.value), req
            )
            self._log.debug(f"Modify sent for order {venue_order_id}")
            # The WebSocket "replaced" event will generate the OrderUpdated event
        except Exception as e:
            self._log.error(f"Failed to modify order {venue_order_id}: {e}")
            self.generate_order_modify_rejected(
                strategy_id=command.strategy_id,
                instrument_id=command.instrument_id,
                client_order_id=command.client_order_id,
                venue_order_id=venue_order_id,
                reason=str(e),
                ts_event=self._clock.timestamp_ns(),
            )

    # -------------------------------------------------------------------------
    # WebSocket trade update handler
    # -------------------------------------------------------------------------

    async def _handle_trade_update(self, update) -> None:
        """
        Handle a real-time trade update from the Alpaca TradingStream.

        ``update.event`` is a string describing the event type.
        ``update.order`` is an alpaca-py Order object.
        """
        try:
            event = update.event
            alpaca_order = update.order

            client_order_id_str = getattr(alpaca_order, "client_order_id", None)
            venue_order_id_str = str(alpaca_order.id)

            client_order_id = (
                ClientOrderId(client_order_id_str) if client_order_id_str else None
            )
            venue_order_id = VenueOrderId(venue_order_id_str)

            instrument_id = alpaca_symbol_to_instrument_id(alpaca_order.symbol)
            ts_event = self._clock.timestamp_ns()

            # Resolve strategy_id from the cache
            strategy_id = None
            if client_order_id is not None:
                strategy_id = self._cache.strategy_id_for_order(client_order_id)

            if strategy_id is None:
                # Order not tracked in cache — emit an order status report
                self._log.debug(
                    f"Received trade update for untracked order {venue_order_id}: event={event}"
                )
                return

            if event in ("new", "accepted"):
                # Already handled via REST in _submit_order; skip to avoid duplicate
                pass

            elif event in ("fill", "partial_fill"):
                # Resolve instrument for currency info
                instrument = self._instrument_provider.find(instrument_id=instrument_id)

                side_str = getattr(alpaca_order, "side", None)
                if side_str is not None:
                    order_side = (
                        OrderSide.BUY if str(side_str).lower() == "buy" else OrderSide.SELL
                    )
                else:
                    order_side = OrderSide.BUY

                # Use the per-event fill qty/price from the trade update. Do NOT
                # fall back to the order's cumulative filled_qty / average
                # filled_avg_price — on a partial fill that would over-report the
                # size and report an average rather than this fill's price.
                fill_qty_str = getattr(update, "qty", None)
                fill_price_str = getattr(update, "price", None)

                if fill_qty_str is None or fill_price_str is None:
                    self._log.warning(
                        f"Cannot generate fill for {venue_order_id}: "
                        f"missing per-event qty={fill_qty_str}, price={fill_price_str}"
                    )
                    return

                last_qty = Quantity.from_str(str(fill_qty_str))
                last_px = Price.from_str(str(fill_price_str))

                quote_currency = (
                    instrument.quote_currency
                    if instrument is not None
                    else Currency.from_str("USD")
                )

                execution_id = getattr(update, "execution_id", None)
                trade_id = TradeId(str(execution_id) if execution_id else venue_order_id_str)

                order_type_str = str(getattr(alpaca_order, "type", "market")).lower()
                _ALPACA_ORDER_TYPE_MAP = {
                    "market": OrderType.MARKET,
                    "limit": OrderType.LIMIT,
                    "stop": OrderType.STOP_MARKET,
                    "stop_limit": OrderType.STOP_LIMIT,
                    "trailing_stop": OrderType.TRAILING_STOP_MARKET,
                }
                order_type = _ALPACA_ORDER_TYPE_MAP.get(order_type_str, OrderType.MARKET)

                self.generate_order_filled(
                    strategy_id=strategy_id,
                    instrument_id=instrument_id,
                    client_order_id=client_order_id,
                    venue_order_id=venue_order_id,
                    venue_position_id=None,  # NETTING accounts
                    trade_id=trade_id,
                    order_side=order_side,
                    order_type=order_type,
                    last_qty=last_qty,
                    last_px=last_px,
                    quote_currency=quote_currency,
                    commission=Money(0, quote_currency),
                    liquidity_side=LiquiditySide.NO_LIQUIDITY_SIDE,
                    ts_event=ts_event,
                )

                # A fill changes cash/buying-power — refresh account snapshot.
                self.create_task(self._refresh_account_state())

            elif event == "canceled":
                self.generate_order_canceled(
                    strategy_id=strategy_id,
                    instrument_id=instrument_id,
                    client_order_id=client_order_id,
                    venue_order_id=venue_order_id,
                    ts_event=ts_event,
                )

            elif event == "rejected":
                self.generate_order_rejected(
                    strategy_id=strategy_id,
                    instrument_id=instrument_id,
                    client_order_id=client_order_id,
                    reason="Order rejected by Alpaca",
                    ts_event=ts_event,
                )

            elif event in ("expired", "done_for_day"):
                self.generate_order_expired(
                    strategy_id=strategy_id,
                    instrument_id=instrument_id,
                    client_order_id=client_order_id,
                    venue_order_id=venue_order_id,
                    ts_event=ts_event,
                )

            elif event == "replaced":
                # Modification was accepted — update with new venue_order_id if available
                cached_order = self._cache.order(client_order_id)
                if cached_order is not None:
                    new_qty = (
                        Quantity.from_str(str(alpaca_order.qty))
                        if alpaca_order.qty
                        else cached_order.quantity
                    )
                    new_price = (
                        Price.from_str(str(alpaca_order.limit_price))
                        if getattr(alpaca_order, "limit_price", None)
                        else (cached_order.price if cached_order.has_price else None)
                    )
                    trigger_price = (
                        Price.from_str(str(alpaca_order.stop_price))
                        if getattr(alpaca_order, "stop_price", None)
                        else (
                            cached_order.trigger_price
                            if cached_order.has_trigger_price
                            else None
                        )
                    )
                    self.generate_order_updated(
                        strategy_id=strategy_id,
                        instrument_id=instrument_id,
                        client_order_id=client_order_id,
                        venue_order_id=venue_order_id,
                        quantity=new_qty,
                        price=new_price,
                        trigger_price=trigger_price,
                        ts_event=ts_event,
                    )

            elif event in (
                "pending_new",
                "pending_cancel",
                "pending_replace",
                "calculated",
                "stopped",
                "suspended",
                "order_cancel_rejected",
                "order_replace_rejected",
            ):
                # These are informational — log and skip
                self._log.debug(
                    f"Received trade update event {event!r} for {venue_order_id} (no action)"
                )

            else:
                self._log.warning(
                    f"Received unhandled trade update event {event!r} for {venue_order_id}"
                )

        except Exception as e:
            self._log.error(f"Error handling trade update: {e}")

    # -------------------------------------------------------------------------
    # Reconciliation reports
    # -------------------------------------------------------------------------

    async def _fetch_all_orders(self, status, symbols: list[str] | None = None) -> list:
        """
        Fetch every order matching ``status`` by walking Alpaca's paginated
        orders endpoint.

        Alpaca caps a single ``get_orders`` response (max 500) and requires
        paging via the ``until`` timestamp. Without this, reconciliation would
        silently drop orders (and their fills) on busy accounts.
        """
        from alpaca.trading.requests import GetOrdersRequest

        page_size = 500
        all_orders: list = []
        seen: set[str] = set()
        until = None

        while True:
            req_kwargs: dict[str, Any] = {"status": status, "limit": page_size}
            if symbols:
                req_kwargs["symbols"] = symbols
            if until is not None:
                req_kwargs["until"] = until

            page = await asyncio.to_thread(
                self._client.get_orders, GetOrdersRequest(**req_kwargs)
            )
            if not page:
                break

            new_orders = [o for o in page if str(o.id) not in seen]
            if not new_orders:
                # Page boundary returned only already-seen orders — stop.
                break
            for o in new_orders:
                seen.add(str(o.id))
            all_orders.extend(new_orders)

            if len(page) < page_size:
                break

            # Page backwards using the oldest created_at in this page.
            oldest = min(
                (o.created_at for o in page if getattr(o, "created_at", None) is not None),
                default=None,
            )
            if oldest is None:
                break
            until = oldest

        return all_orders

    async def generate_order_status_report(
        self,
        command: GenerateOrderStatusReport,
    ) -> OrderStatusReport | None:
        """Generate a single OrderStatusReport for the given order."""
        self._log.debug(
            f"Generating OrderStatusReport for "
            f"{command.client_order_id!r} {command.venue_order_id!r}"
        )

        try:
            if command.venue_order_id is not None:
                alpaca_order = await asyncio.to_thread(
                    self._client.get_order_by_id, command.venue_order_id.value
                )
            elif command.client_order_id is not None:
                alpaca_order = await asyncio.to_thread(
                    self._client.get_order_by_client_id, command.client_order_id.value
                )
            else:
                self._log.error(
                    "Cannot generate OrderStatusReport: both client_order_id and venue_order_id are None"
                )
                return None
        except Exception as e:
            self._log.warning(
                f"Cannot generate OrderStatusReport for "
                f"{command.client_order_id!r}: {e}"
            )
            return None

        if alpaca_order is None:
            return None

        return self._build_order_status_report(alpaca_order, command.instrument_id)

    async def generate_order_status_reports(
        self,
        command: GenerateOrderStatusReports,
    ) -> list[OrderStatusReport]:
        """Generate OrderStatusReports for all orders."""
        self._log.debug("Requesting OrderStatusReports...")

        try:
            from alpaca.trading.enums import QueryOrderStatus

            status = (
                QueryOrderStatus.OPEN if command.open_only else QueryOrderStatus.ALL
            )
            symbols = (
                [command.instrument_id.symbol.value]
                if command.instrument_id is not None
                else None
            )
            orders = await self._fetch_all_orders(status, symbols)
        except Exception as e:
            self._log.error(f"Cannot generate OrderStatusReports: {e}")
            return []

        reports: list[OrderStatusReport] = []
        for alpaca_order in orders:
            instrument_id = alpaca_symbol_to_instrument_id(alpaca_order.symbol)  # type: ignore[arg-type, union-attr]
            # Filter by start/end if specified
            if command.start is not None or command.end is not None:
                created_at = getattr(alpaca_order, "created_at", None)
                if created_at is not None:
                    try:
                        import datetime

                        if isinstance(created_at, str):
                            ts = datetime.datetime.fromisoformat(
                                created_at.replace("Z", "+00:00")
                            )
                        else:
                            ts = created_at
                        # Make ts tz-aware if needed
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=datetime.timezone.utc)
                        if command.start is not None and ts < command.start:
                            continue
                        if command.end is not None and ts > command.end:
                            continue
                    except Exception:
                        pass

            report = self._build_order_status_report(alpaca_order, instrument_id)
            if report is not None:
                reports.append(report)

        self._log.info(f"Generated {len(reports)} OrderStatusReports")
        return reports

    @staticmethod
    def _ts_to_ns(value) -> int | None:
        """Convert an Alpaca datetime/ISO-8601 string to nautilus nanoseconds."""
        if value is None:
            return None
        try:
            import datetime as _dt

            if isinstance(value, str):
                ts = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            else:
                ts = value
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=_dt.timezone.utc)
            return int(ts.timestamp()) * 1_000_000_000 + ts.microsecond * 1_000
        except Exception:
            return None

    async def _fetch_fill_activities(self, after=None) -> list:
        """
        Fetch FILL account activities, paginating via ``page_token``.

        The account-activities endpoint reports one entry per execution (unique
        id, per-fill qty/price and transaction time), unlike the orders endpoint
        which only exposes cumulative ``filled_qty`` / average ``filled_avg_price``.
        """
        from alpaca.trading.requests import GetAccountActivitiesRequest
        from alpaca.trading.enums import ActivityType

        page_size = 100
        activities: list = []
        page_token = None

        while True:
            req_kwargs: dict[str, Any] = {
                "activity_types": [ActivityType.FILL],
                "page_size": page_size,
            }
            if after is not None:
                req_kwargs["after"] = after
            if page_token is not None:
                req_kwargs["page_token"] = page_token

            page = await asyncio.to_thread(
                self._client.get_account_activities,
                GetAccountActivitiesRequest(**req_kwargs),
            )
            if not page:
                break
            activities.extend(page)
            if len(page) < page_size:
                break
            page_token = str(getattr(page[-1], "id", "")) or None
            if page_token is None:
                break

        return activities

    async def generate_fill_reports(
        self,
        command: GenerateFillReports,
    ) -> list[FillReport]:
        """
        Generate FillReports from Alpaca account activities.

        Each FILL activity is a single execution with its own id, quantity,
        price and timestamp, so partial fills are represented individually and
        each ``trade_id`` is unique per fill. (The orders endpoint only exposes
        cumulative figures, which collapsed every fill of an order into one.)
        """
        self._log.debug("Requesting FillReports...")

        try:
            activities = await self._fetch_fill_activities(after=command.start)
        except Exception as e:
            self._log.error(f"Cannot generate FillReports: {e}")
            return []

        symbol_filter = (
            command.instrument_id.symbol.value
            if command.instrument_id is not None
            else None
        )

        reports: list[FillReport] = []
        now = self._clock.timestamp_ns()

        for act in activities:
            symbol = getattr(act, "symbol", None)
            if symbol is None:
                continue
            if symbol_filter is not None and symbol != symbol_filter:
                continue

            qty_raw = getattr(act, "qty", None)
            price_raw = getattr(act, "price", None)
            if qty_raw is None or price_raw is None:
                continue
            try:
                qty = Decimal(str(qty_raw))
                px = Decimal(str(price_raw))
            except Exception:
                continue
            if qty <= 0:
                continue

            instrument_id = alpaca_symbol_to_instrument_id(symbol)
            instrument = self._instrument_provider.find(instrument_id=instrument_id)
            quote_currency = (
                instrument.quote_currency
                if instrument is not None
                else Currency.from_str("USD")
            )

            side_str = str(getattr(act, "side", "buy")).lower()
            order_side = OrderSide.BUY if "buy" in side_str else OrderSide.SELL

            order_id = getattr(act, "order_id", None)
            exec_id = getattr(act, "id", None) or order_id
            venue_order_id = (
                VenueOrderId(str(order_id)) if order_id else VenueOrderId(str(exec_id))
            )

            ts_event = self._ts_to_ns(getattr(act, "transaction_time", None)) or now

            report = FillReport(
                account_id=self.account_id,
                instrument_id=instrument_id,
                venue_order_id=venue_order_id,
                venue_position_id=None,
                # Per-execution id keeps partial fills distinct. Alpaca is
                # commission-free for equities; crypto fees are not exposed
                # per fill, so commission is reported as zero.
                trade_id=TradeId(str(exec_id)),
                order_side=order_side,
                last_qty=Quantity.from_str(str(qty)),
                last_px=Price.from_str(str(px)),
                commission=Money(0, quote_currency),
                liquidity_side=LiquiditySide.NO_LIQUIDITY_SIDE,
                report_id=UUID4(),
                ts_event=ts_event,
                ts_init=now,
            )
            reports.append(report)

        self._log.info(f"Generated {len(reports)} FillReports")
        return reports

    async def generate_position_status_reports(
        self,
        command: GeneratePositionStatusReports,
    ) -> list[PositionStatusReport]:
        """Generate PositionStatusReports from all open Alpaca positions."""
        self._log.debug("Requesting PositionStatusReports...")

        try:
            if command.instrument_id is not None:
                symbol = command.instrument_id.symbol.value
                positions = [await asyncio.to_thread(self._client.get_open_position, symbol)]
            else:
                positions = await asyncio.to_thread(self._client.get_all_positions)
        except Exception as e:
            # If position not found, return flat for specific instrument
            if command.instrument_id is not None:
                self._log.info(
                    f"No position found for {command.instrument_id}: returning FLAT"
                )
                now = self._clock.timestamp_ns()
                return [
                    PositionStatusReport(
                        account_id=self.account_id,
                        instrument_id=command.instrument_id,
                        position_side=PositionSide.FLAT,
                        quantity=Quantity.zero(),
                        report_id=UUID4(),
                        ts_last=now,
                        ts_init=now,
                    )
                ]
            self._log.error(f"Cannot generate PositionStatusReports: {e}")
            return []

        reports: list[PositionStatusReport] = []
        now = self._clock.timestamp_ns()

        for pos in positions:
            if pos is None:
                continue
            instrument_id = alpaca_symbol_to_instrument_id(pos.symbol)  # type: ignore[union-attr]
            side_str = getattr(pos, "side", "long")
            position_side = (
                PositionSide.LONG if str(side_str).lower() == "long" else PositionSide.SHORT
            )

            try:
                qty = Quantity.from_str(str(abs(Decimal(str(pos.qty)))))  # type: ignore[union-attr]
            except Exception:
                qty = Quantity.zero()

            report = PositionStatusReport(
                account_id=self.account_id,
                instrument_id=instrument_id,
                position_side=position_side,
                quantity=qty,
                report_id=UUID4(),
                ts_last=now,
                ts_init=now,
            )
            reports.append(report)

        self._log.info(f"Generated {len(reports)} PositionStatusReports")
        return reports

    async def generate_mass_status(
        self,
        lookback_mins: int | None = None,
    ):
        """Generate ExecutionMassStatus by delegating to the base class."""
        return await super().generate_mass_status(lookback_mins)

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _build_order_status_report(
        self,
        alpaca_order,
        instrument_id: InstrumentId,
    ) -> OrderStatusReport | None:
        """Convert an alpaca-py Order object into a nautilus OrderStatusReport."""
        try:
            venue_order_id = VenueOrderId(str(alpaca_order.id))
            client_order_id_str = getattr(alpaca_order, "client_order_id", None)
            client_order_id = (
                ClientOrderId(client_order_id_str) if client_order_id_str else None
            )

            side_str = str(getattr(alpaca_order, "side", "buy")).lower()
            order_side = OrderSide.BUY if side_str == "buy" else OrderSide.SELL

            status_str = str(getattr(alpaca_order, "status", "new")).lower()
            order_status = alpaca_order_status_to_nautilus(status_str)

            type_str = str(getattr(alpaca_order, "type", "market")).lower()
            order_type_map = {
                "market": OrderType.MARKET,
                "limit": OrderType.LIMIT,
                "stop": OrderType.STOP_MARKET,
                "stop_limit": OrderType.STOP_LIMIT,
                "trailing_stop": OrderType.TRAILING_STOP_MARKET,
            }
            order_type = order_type_map.get(type_str, OrderType.MARKET)

            tif_str = str(getattr(alpaca_order, "time_in_force", "day")).lower()
            tif_map = {
                "day": TimeInForce.DAY,
                "gtc": TimeInForce.GTC,
                "ioc": TimeInForce.IOC,
                "fok": TimeInForce.FOK,
                "opg": TimeInForce.AT_THE_OPEN,
                "cls": TimeInForce.AT_THE_CLOSE,
            }
            time_in_force = tif_map.get(tif_str, TimeInForce.DAY)

            qty_str = getattr(alpaca_order, "qty", None)
            quantity = Quantity.from_str(str(qty_str)) if qty_str else Quantity.zero()

            filled_qty_str = getattr(alpaca_order, "filled_qty", None) or "0"
            filled_qty = Quantity.from_str(str(filled_qty_str))

            limit_price_str = getattr(alpaca_order, "limit_price", None)
            price = Price.from_str(str(limit_price_str)) if limit_price_str else None

            stop_price_str = getattr(alpaca_order, "stop_price", None)
            trigger_price = (
                Price.from_str(str(stop_price_str)) if stop_price_str else None
            )

            filled_avg_price_str = getattr(alpaca_order, "filled_avg_price", None)
            avg_px = (
                Decimal(str(filled_avg_price_str)) if filled_avg_price_str else None
            )

            now = self._clock.timestamp_ns()

            return OrderStatusReport(
                account_id=self.account_id,
                instrument_id=instrument_id,
                client_order_id=client_order_id,
                venue_order_id=venue_order_id,
                order_side=order_side,
                order_type=order_type,
                time_in_force=time_in_force,
                order_status=order_status,
                price=price,
                trigger_price=trigger_price,
                trigger_type=TriggerType.DEFAULT,
                trailing_offset=None,
                trailing_offset_type=TrailingOffsetType.NO_TRAILING_OFFSET,
                quantity=quantity,
                filled_qty=filled_qty,
                display_qty=None,
                avg_px=avg_px,
                post_only=False,
                reduce_only=False,
                report_id=UUID4(),
                ts_accepted=now,
                ts_last=now,
                ts_init=now,
            )
        except Exception as e:
            self._log.error(
                f"Failed to build OrderStatusReport for order {getattr(alpaca_order, 'id', '?')}: {e}"
            )
            return None
