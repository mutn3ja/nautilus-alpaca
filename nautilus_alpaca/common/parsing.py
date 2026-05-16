"""
Conversion helpers between Alpaca wire types and nautilus-trader model objects.

All functions are pure (no I/O, no state). They are used by instrument providers,
data clients, and execution clients.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from nautilus_trader.model.enums import CurrencyType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import OrderStatus
from nautilus_trader.model.enums import OrderType
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.instruments.currency_pair import CurrencyPair
from nautilus_trader.model.instruments.equity import Equity
from nautilus_trader.model.objects import Currency
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity

from nautilus_alpaca.common.constants import ALPACA_VENUE
from nautilus_alpaca.common.schemas.market import AlpacaAsset


_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Symbol / InstrumentId helpers
# ---------------------------------------------------------------------------

def alpaca_symbol_to_instrument_id(symbol: str, venue: Venue = ALPACA_VENUE) -> InstrumentId:
    """
    Convert an Alpaca symbol string to a nautilus ``InstrumentId``.

    Examples
    --------
    - ``"AAPL"``    → ``InstrumentId("AAPL.ALPACA")``
    - ``"BTC/USD"`` → ``InstrumentId("BTC/USD.ALPACA")``
    """
    return InstrumentId(symbol=Symbol(symbol), venue=venue)


# ---------------------------------------------------------------------------
# Order-side mapping
# ---------------------------------------------------------------------------

_ORDER_SIDE_TO_ALPACA: dict[OrderSide, str] = {
    OrderSide.BUY: "buy",
    OrderSide.SELL: "sell",
}


def nautilus_order_side_to_alpaca(side: OrderSide) -> str:
    """Map nautilus ``OrderSide.BUY`` → ``"buy"``, ``SELL`` → ``"sell"``."""
    try:
        return _ORDER_SIDE_TO_ALPACA[side]
    except KeyError:
        raise ValueError(f"Unsupported OrderSide: {side}")


# ---------------------------------------------------------------------------
# Order-type / time-in-force mapping
# ---------------------------------------------------------------------------

_ORDER_TYPE_TO_ALPACA: dict[OrderType, str] = {
    OrderType.MARKET: "market",
    OrderType.LIMIT: "limit",
    OrderType.STOP_MARKET: "stop",
    OrderType.STOP_LIMIT: "stop_limit",
    OrderType.TRAILING_STOP_MARKET: "trailing_stop",
    OrderType.TRAILING_STOP_LIMIT: "trailing_stop",
    # Not directly supported by Alpaca — map to closest equivalent
    OrderType.MARKET_TO_LIMIT: "limit",
    OrderType.MARKET_IF_TOUCHED: "market",
    OrderType.LIMIT_IF_TOUCHED: "limit",
}

_TIF_TO_ALPACA: dict[TimeInForce, str] = {
    TimeInForce.GTC: "gtc",
    TimeInForce.IOC: "ioc",
    TimeInForce.FOK: "fok",
    TimeInForce.DAY: "day",
    TimeInForce.GTD: "gtc",           # Alpaca has no GTD; remap to GTC
    TimeInForce.AT_THE_OPEN: "opg",
    TimeInForce.AT_THE_CLOSE: "cls",
}


def nautilus_order_type_to_alpaca(
    order_type: OrderType,
    time_in_force: TimeInForce,
) -> tuple[str, str]:
    """
    Return ``(alpaca_order_type, alpaca_time_in_force)`` strings.

    Maps nautilus ``OrderType`` and ``TimeInForce`` enums to Alpaca API string
    values. ``MARKET_TO_LIMIT`` and ``MARKET_IF_TOUCHED``/``LIMIT_IF_TOUCHED``
    are approximated to the nearest Alpaca equivalent.
    """
    try:
        alpaca_order_type = _ORDER_TYPE_TO_ALPACA[order_type]
    except KeyError:
        raise ValueError(f"Unsupported OrderType: {order_type}")

    try:
        alpaca_tif = _TIF_TO_ALPACA[time_in_force]
    except KeyError:
        raise ValueError(f"Unsupported TimeInForce: {time_in_force}")

    return alpaca_order_type, alpaca_tif


# ---------------------------------------------------------------------------
# Order-status mapping
# ---------------------------------------------------------------------------

_ALPACA_STATUS_TO_NAUTILUS: dict[str, OrderStatus] = {
    "new": OrderStatus.ACCEPTED,
    "partially_filled": OrderStatus.PARTIALLY_FILLED,
    "filled": OrderStatus.FILLED,
    "canceled": OrderStatus.CANCELED,
    "expired": OrderStatus.EXPIRED,
    "replaced": OrderStatus.CANCELED,       # treat replaced as canceled in nautilus
    "rejected": OrderStatus.REJECTED,
    "pending_cancel": OrderStatus.PENDING_CANCEL,
    "pending_replace": OrderStatus.PENDING_UPDATE,
    "accepted": OrderStatus.ACCEPTED,
    "pending_new": OrderStatus.SUBMITTED,
    "accepted_for_bidding": OrderStatus.ACCEPTED,
    "stopped": OrderStatus.FILLED,
    "suspended": OrderStatus.ACCEPTED,
    "calculated": OrderStatus.FILLED,
    "done_for_day": OrderStatus.EXPIRED,
}


def alpaca_order_status_to_nautilus(status: str) -> OrderStatus:
    """
    Map an Alpaca order status string to a nautilus ``OrderStatus`` enum value.

    Raises ``ValueError`` for unknown status strings.
    """
    try:
        return _ALPACA_STATUS_TO_NAUTILUS[status]
    except KeyError:
        raise ValueError(f"Unknown Alpaca order status: {status!r}")


# ---------------------------------------------------------------------------
# Instrument parsing helpers
# ---------------------------------------------------------------------------

def _derive_price_precision(price_increment_str: str | None) -> tuple[int, Price]:
    """
    Return ``(price_precision, price_increment)`` from an Alpaca price_increment string.

    Falls back to precision=2 (i.e. $0.01 tick) when the string is absent or invalid.
    """
    if price_increment_str:
        try:
            price_precision = abs(int(Decimal(price_increment_str).as_tuple().exponent))
            price_increment = Price.from_str(price_increment_str)
            return price_precision, price_increment
        except Exception:
            pass
    # Default for equities
    price_precision = 2
    price_increment = Price(Decimal("0.01"), price_precision)
    return price_precision, price_increment


def _derive_size_precision(min_trade_increment_str: str | None) -> tuple[int, Quantity]:
    """
    Return ``(size_precision, size_increment)`` from an Alpaca min_trade_increment string.

    Falls back to precision=0 (whole shares) when the string is absent or invalid.
    """
    if min_trade_increment_str:
        try:
            size_precision = abs(int(Decimal(min_trade_increment_str).as_tuple().exponent))
            size_increment = Quantity.from_str(min_trade_increment_str)
            return size_precision, size_increment
        except Exception:
            pass
    # Default: whole shares only
    size_precision = 0
    size_increment = Quantity(1, 0)
    return size_precision, size_increment


def parse_equity(asset: AlpacaAsset, venue: Venue) -> Equity:
    """
    Convert an ``AlpacaAsset`` with ``asset_class="us_equity"`` to a nautilus ``Equity``.

    Uses ``asset.price_increment`` and ``asset.min_trade_increment`` when available,
    otherwise defaults to price_precision=2 and whole-share sizing.
    """
    instrument_id = alpaca_symbol_to_instrument_id(asset.symbol, venue)
    raw_symbol = Symbol(asset.symbol)
    currency = Currency.from_str("USD")

    price_precision, price_increment = _derive_price_precision(asset.price_increment)
    _size_precision, _size_increment = _derive_size_precision(asset.min_trade_increment)
    # Equity ignores size_precision / size_increment — the constructor fixes them to 0 / 1.
    lot_size = Quantity(1, 0)

    return Equity(
        instrument_id=instrument_id,
        raw_symbol=raw_symbol,
        currency=currency,
        price_precision=price_precision,
        price_increment=price_increment,
        lot_size=lot_size,
        margin_init=Decimal("0"),
        margin_maint=Decimal("0"),
        maker_fee=Decimal("0"),
        taker_fee=Decimal("0"),
        ts_event=0,
        ts_init=0,
    )


def parse_currency_pair(asset: AlpacaAsset, venue: Venue) -> CurrencyPair:
    """
    Convert an ``AlpacaAsset`` with ``asset_class="crypto"`` to a nautilus ``CurrencyPair``.

    Alpaca crypto symbols use the ``"BASE/QUOTE"`` format (e.g. ``"BTC/USD"``).
    Unknown currencies are registered as CRYPTO with 8 decimal precision.
    """
    parts = asset.symbol.split("/")
    if len(parts) != 2:
        raise ValueError(
            f"Unexpected crypto symbol format (expected BASE/QUOTE): {asset.symbol!r}"
        )
    base_code, quote_code = parts

    def _get_currency(code: str) -> Currency:
        try:
            return Currency.from_str(code)
        except Exception:
            return Currency(
                code,
                precision=8,
                iso4217=0,
                name=code,
                currency_type=CurrencyType.CRYPTO,
            )

    base_currency = _get_currency(base_code)
    quote_currency = _get_currency(quote_code)

    instrument_id = alpaca_symbol_to_instrument_id(asset.symbol, venue)
    raw_symbol = Symbol(asset.symbol)

    price_precision, price_increment = _derive_price_precision(asset.price_increment)
    size_precision, size_increment = _derive_size_precision(asset.min_trade_increment)

    return CurrencyPair(
        instrument_id=instrument_id,
        raw_symbol=raw_symbol,
        base_currency=base_currency,
        quote_currency=quote_currency,
        price_precision=price_precision,
        size_precision=size_precision,
        price_increment=price_increment,
        size_increment=size_increment,
        margin_init=Decimal("0"),
        margin_maint=Decimal("0"),
        maker_fee=Decimal("0"),
        taker_fee=Decimal("0"),
        ts_event=0,
        ts_init=0,
    )


def parse_instrument(
    asset: AlpacaAsset,
    venue: Venue = ALPACA_VENUE,
) -> Equity | CurrencyPair | None:
    """
    Dispatch on ``asset.asset_class`` and return the appropriate nautilus instrument.

    Returns ``None`` for:
    - Inactive assets (``asset.status != "active"``)
    - Options (``asset_class="us_option"`` — not yet supported)
    """
    if asset.status != "active":
        return None

    if asset.asset_class == "us_equity":
        return parse_equity(asset, venue)
    elif asset.asset_class == "crypto":
        return parse_currency_pair(asset, venue)
    elif asset.asset_class == "us_option":
        _log.warning(
            "Alpaca options instruments are not yet supported; "
            f"skipping {asset.symbol!r}."
        )
        return None
    else:
        _log.warning(
            f"Unknown Alpaca asset_class {asset.asset_class!r}; "
            f"skipping {asset.symbol!r}."
        )
        return None
