"""
Comprehensive unit tests for nautilus_alpaca.common.parsing.

Covers: instrument dispatch, equity/crypto field values, precision derivation,
symbol/InstrumentId conversion, all order-side/type/TIF/status mappings,
and error paths for unsupported values.
"""
import pytest
from decimal import Decimal

from nautilus_trader.model.enums import OrderSide, OrderStatus, OrderType, TimeInForce
from nautilus_trader.model.instruments import Equity, CurrencyPair
from nautilus_trader.model.objects import Price, Quantity

from nautilus_alpaca.common.constants import ALPACA_VENUE
from nautilus_alpaca.common.schemas.market import AlpacaAsset
from nautilus_alpaca.common.parsing import (
    _ALPACA_STATUS_TO_NAUTILUS,
    _ORDER_TYPE_TO_ALPACA,
    _TIF_TO_ALPACA,
    alpaca_order_status_to_nautilus,
    alpaca_symbol_to_instrument_id,
    nautilus_order_side_to_alpaca,
    nautilus_order_type_to_alpaca,
    parse_currency_pair,
    parse_equity,
    parse_instrument,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_equity_asset(**kwargs) -> AlpacaAsset:
    defaults = dict(
        id="test-id", asset_class="us_equity", exchange="NASDAQ",
        symbol="AAPL", name="Apple Inc.", status="active",
        tradable=True, marginable=True, shortable=True,
        easy_to_borrow=True, fractionable=True,
    )
    defaults.update(kwargs)
    return AlpacaAsset(**defaults)


def make_crypto_asset(**kwargs) -> AlpacaAsset:
    defaults = dict(
        id="test-id-2", asset_class="crypto", exchange="CRYPTO",
        symbol="BTC/USD", name="Bitcoin", status="active",
        tradable=True, marginable=False, shortable=False,
        easy_to_borrow=False, fractionable=True,
    )
    defaults.update(kwargs)
    return AlpacaAsset(**defaults)


# ---------------------------------------------------------------------------
# parse_instrument — dispatch
# ---------------------------------------------------------------------------

def test_parse_instrument_equity():
    result = parse_instrument(make_equity_asset())
    assert isinstance(result, Equity)
    assert result.id.symbol.value == "AAPL"


def test_parse_instrument_crypto():
    result = parse_instrument(make_crypto_asset())
    assert isinstance(result, CurrencyPair)


def test_parse_instrument_option_returns_none():
    result = parse_instrument(
        make_equity_asset(asset_class="us_option", symbol="AAPL251219C00450000")
    )
    assert result is None


def test_parse_instrument_inactive_returns_none():
    result = parse_instrument(make_equity_asset(status="inactive"))
    assert result is None


def test_parse_instrument_unknown_asset_class_returns_none():
    result = parse_instrument(make_equity_asset(asset_class="futures"))
    assert result is None


# ---------------------------------------------------------------------------
# parse_equity — field values
# ---------------------------------------------------------------------------

def test_parse_equity_instrument_id():
    eq = parse_equity(make_equity_asset(), ALPACA_VENUE)
    assert eq.id.symbol.value == "AAPL"
    assert eq.id.venue.value == "ALPACA"


def test_parse_equity_currency_is_usd():
    eq = parse_equity(make_equity_asset(), ALPACA_VENUE)
    assert eq.quote_currency.code == "USD"


def test_parse_equity_lot_size_is_one():
    eq = parse_equity(make_equity_asset(), ALPACA_VENUE)
    assert eq.lot_size.as_double() == 1.0


def test_parse_equity_price_precision_default_when_none():
    """Absent price_increment → precision=2 ($0.01 tick)."""
    eq = parse_equity(make_equity_asset(price_increment=None), ALPACA_VENUE)
    assert eq.price_precision == 2
    assert eq.price_increment.as_double() == pytest.approx(0.01)


def test_parse_equity_price_precision_penny():
    eq = parse_equity(make_equity_asset(price_increment="0.01"), ALPACA_VENUE)
    assert eq.price_precision == 2
    assert eq.price_increment.as_double() == pytest.approx(0.01)


def test_parse_equity_price_precision_sub_penny():
    eq = parse_equity(make_equity_asset(price_increment="0.001"), ALPACA_VENUE)
    assert eq.price_precision == 3
    assert eq.price_increment.as_double() == pytest.approx(0.001)


def test_parse_equity_price_precision_whole_dollar():
    eq = parse_equity(make_equity_asset(price_increment="1"), ALPACA_VENUE)
    assert eq.price_precision == 0
    assert eq.price_increment.as_double() == pytest.approx(1.0)


def test_parse_equity_price_increment_is_price_object():
    eq = parse_equity(make_equity_asset(price_increment="0.01"), ALPACA_VENUE)
    assert isinstance(eq.price_increment, Price)


def test_parse_equity_size_increment_is_quantity_object():
    eq = parse_equity(make_equity_asset(), ALPACA_VENUE)
    assert isinstance(eq.size_increment, Quantity)


def test_parse_equity_fees_are_zero():
    eq = parse_equity(make_equity_asset(), ALPACA_VENUE)
    assert eq.maker_fee == Decimal("0")
    assert eq.taker_fee == Decimal("0")
    assert eq.margin_init == Decimal("0")
    assert eq.margin_maint == Decimal("0")


# ---------------------------------------------------------------------------
# parse_currency_pair — field values
# ---------------------------------------------------------------------------

def test_parse_currency_pair_base_quote_btc_usd():
    cp = parse_currency_pair(make_crypto_asset(), ALPACA_VENUE)
    assert cp.base_currency.code == "BTC"
    assert cp.quote_currency.code == "USD"


def test_parse_currency_pair_instrument_id():
    cp = parse_currency_pair(make_crypto_asset(), ALPACA_VENUE)
    assert str(cp.id) == "BTC/USD.ALPACA"


def test_parse_currency_pair_eth_usd():
    asset = make_crypto_asset(symbol="ETH/USD", name="Ethereum")
    cp = parse_currency_pair(asset, ALPACA_VENUE)
    assert cp.base_currency.code == "ETH"
    assert cp.quote_currency.code == "USD"


def test_parse_currency_pair_explicit_price_increment():
    asset = make_crypto_asset(price_increment="0.01", min_trade_increment="0.0001")
    cp = parse_currency_pair(asset, ALPACA_VENUE)
    assert cp.price_precision == 2
    assert cp.price_increment.as_double() == pytest.approx(0.01)
    assert cp.size_precision == 4
    assert cp.size_increment.as_double() == pytest.approx(0.0001)


def test_parse_currency_pair_default_precision_when_none():
    asset = make_crypto_asset(price_increment=None, min_trade_increment=None)
    cp = parse_currency_pair(asset, ALPACA_VENUE)
    assert cp.price_precision == 2
    assert cp.size_precision == 0


def test_parse_currency_pair_unknown_base_registered_as_crypto():
    """Symbols like SHIB that aren't in the currency registry should not raise."""
    asset = make_crypto_asset(symbol="SHIB/USD", name="Shiba Inu")
    cp = parse_currency_pair(asset, ALPACA_VENUE)
    assert cp.base_currency.code == "SHIB"


def test_parse_currency_pair_bad_symbol_raises():
    """Symbol without '/' must raise ValueError."""
    asset = make_crypto_asset(symbol="BTCUSD")
    with pytest.raises(ValueError, match="BASE/QUOTE"):
        parse_currency_pair(asset, ALPACA_VENUE)


def test_parse_currency_pair_price_increment_is_price_object():
    asset = make_crypto_asset(price_increment="0.50")
    cp = parse_currency_pair(asset, ALPACA_VENUE)
    assert isinstance(cp.price_increment, Price)


def test_parse_currency_pair_size_increment_is_quantity_object():
    asset = make_crypto_asset(min_trade_increment="0.001")
    cp = parse_currency_pair(asset, ALPACA_VENUE)
    assert isinstance(cp.size_increment, Quantity)


# ---------------------------------------------------------------------------
# alpaca_symbol_to_instrument_id
# ---------------------------------------------------------------------------

def test_symbol_to_instrument_id_equity():
    iid = alpaca_symbol_to_instrument_id("AAPL")
    assert str(iid) == "AAPL.ALPACA"


def test_symbol_to_instrument_id_crypto():
    iid = alpaca_symbol_to_instrument_id("BTC/USD")
    assert str(iid) == "BTC/USD.ALPACA"


def test_symbol_to_instrument_id_etf():
    iid = alpaca_symbol_to_instrument_id("SPY")
    assert str(iid) == "SPY.ALPACA"


# ---------------------------------------------------------------------------
# nautilus_order_side_to_alpaca
# ---------------------------------------------------------------------------

def test_order_side_buy():
    assert nautilus_order_side_to_alpaca(OrderSide.BUY) == "buy"


def test_order_side_sell():
    assert nautilus_order_side_to_alpaca(OrderSide.SELL) == "sell"


# ---------------------------------------------------------------------------
# alpaca_order_status_to_nautilus — full mapping coverage
# ---------------------------------------------------------------------------

def test_order_status_filled():
    assert alpaca_order_status_to_nautilus("filled") == OrderStatus.FILLED


def test_order_status_canceled():
    assert alpaca_order_status_to_nautilus("canceled") == OrderStatus.CANCELED


def test_order_status_rejected():
    assert alpaca_order_status_to_nautilus("rejected") == OrderStatus.REJECTED


def test_order_status_partially_filled():
    assert alpaca_order_status_to_nautilus("partially_filled") == OrderStatus.PARTIALLY_FILLED


def test_order_status_expired():
    assert alpaca_order_status_to_nautilus("expired") == OrderStatus.EXPIRED


def test_order_status_pending_cancel():
    assert alpaca_order_status_to_nautilus("pending_cancel") == OrderStatus.PENDING_CANCEL


def test_order_status_new_maps_to_accepted():
    assert alpaca_order_status_to_nautilus("new") == OrderStatus.ACCEPTED


def test_order_status_pending_new_maps_to_submitted():
    assert alpaca_order_status_to_nautilus("pending_new") == OrderStatus.SUBMITTED


@pytest.mark.parametrize("status,expected", list(_ALPACA_STATUS_TO_NAUTILUS.items()))
def test_order_status_all_known_mappings(status, expected):
    """Every entry in the internal mapping resolves without error."""
    assert alpaca_order_status_to_nautilus(status) == expected


def test_order_status_unknown_raises():
    with pytest.raises(ValueError, match="Unknown Alpaca order status"):
        alpaca_order_status_to_nautilus("not_a_real_status")


def test_order_status_empty_string_raises():
    with pytest.raises(ValueError, match="Unknown Alpaca order status"):
        alpaca_order_status_to_nautilus("")


# ---------------------------------------------------------------------------
# nautilus_order_type_to_alpaca — order type mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("order_type,expected_alpaca_type", [
    (OrderType.MARKET, "market"),
    (OrderType.LIMIT, "limit"),
    (OrderType.STOP_MARKET, "stop"),
    (OrderType.STOP_LIMIT, "stop_limit"),
    (OrderType.TRAILING_STOP_MARKET, "trailing_stop"),
    (OrderType.TRAILING_STOP_LIMIT, "trailing_stop"),
    (OrderType.MARKET_TO_LIMIT, "limit"),
    (OrderType.MARKET_IF_TOUCHED, "market"),
    (OrderType.LIMIT_IF_TOUCHED, "limit"),
])
def test_order_type_all_known(order_type, expected_alpaca_type):
    alpaca_type, _ = nautilus_order_type_to_alpaca(order_type, TimeInForce.DAY)
    assert alpaca_type == expected_alpaca_type


@pytest.mark.parametrize("order_type", list(_ORDER_TYPE_TO_ALPACA.keys()))
def test_order_type_all_in_map_resolve(order_type):
    """Every entry in the internal mapping returns a (type, tif) pair."""
    result = nautilus_order_type_to_alpaca(order_type, TimeInForce.DAY)
    assert isinstance(result, tuple) and len(result) == 2


# ---------------------------------------------------------------------------
# nautilus_order_type_to_alpaca — TIF mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tif,expected_alpaca_tif", [
    (TimeInForce.DAY, "day"),
    (TimeInForce.GTC, "gtc"),
    (TimeInForce.IOC, "ioc"),
    (TimeInForce.FOK, "fok"),
    (TimeInForce.AT_THE_OPEN, "opg"),
    (TimeInForce.AT_THE_CLOSE, "cls"),
    (TimeInForce.GTD, "gtc"),   # GTD remapped to GTC — no native Alpaca support
])
def test_tif_all_known(tif, expected_alpaca_tif):
    _, alpaca_tif = nautilus_order_type_to_alpaca(OrderType.LIMIT, tif)
    assert alpaca_tif == expected_alpaca_tif


def test_tif_gtd_remaps_to_gtc():
    """GTD has no direct Alpaca equivalent — must remap to GTC."""
    _, alpaca_tif = nautilus_order_type_to_alpaca(OrderType.LIMIT, TimeInForce.GTD)
    assert alpaca_tif == "gtc"


@pytest.mark.parametrize("tif", list(_TIF_TO_ALPACA.keys()))
def test_tif_all_in_map_resolve(tif):
    result = nautilus_order_type_to_alpaca(OrderType.MARKET, tif)
    assert isinstance(result, tuple) and len(result) == 2
