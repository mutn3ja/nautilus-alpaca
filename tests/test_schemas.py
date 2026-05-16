"""
Comprehensive decode tests for all msgspec Struct schemas.

Covers: required fields, optional fields, defaults, type correctness,
nanosecond timestamps, nested structs (AlpacaOrder legs, AlpacaTradeUpdate),
and round-trip decode of realistic Alpaca API payloads.
"""
import msgspec
from nautilus_alpaca.common.schemas.market import (
    AlpacaAsset,
    AlpacaWsBar,
    AlpacaWsErrorMsg,
    AlpacaWsQuote,
    AlpacaWsSubscriptionMsg,
    AlpacaWsTrade,
)
from nautilus_alpaca.common.schemas.account import (
    AlpacaAccount,
    AlpacaOrder,
    AlpacaPosition,
    AlpacaTradeUpdate,
)


# ---------------------------------------------------------------------------
# AlpacaAsset
# ---------------------------------------------------------------------------

def test_alpaca_asset_decode_required_only():
    raw = (
        b'{"id":"b0b6dd9d-8b9b-48a9-ba46-b9d54906e415","asset_class":"us_equity",'
        b'"exchange":"NASDAQ","symbol":"AAPL","name":"Apple Inc.","status":"active",'
        b'"tradable":true,"marginable":true,"shortable":true,"easy_to_borrow":true,'
        b'"fractionable":true}'
    )
    asset = msgspec.json.decode(raw, type=AlpacaAsset)
    assert asset.symbol == "AAPL"
    assert asset.status == "active"
    assert asset.asset_class == "us_equity"
    assert asset.tradable is True
    assert asset.marginable is True
    # All optional fields default to None
    assert asset.min_order_size is None
    assert asset.min_trade_increment is None
    assert asset.price_increment is None
    assert asset.attributes is None


def test_alpaca_asset_decode_with_all_optional_fields():
    raw = (
        b'{"id":"abc","asset_class":"crypto","exchange":"CRYPTO","symbol":"BTC/USD",'
        b'"name":"Bitcoin","status":"active","tradable":true,"marginable":false,'
        b'"shortable":false,"easy_to_borrow":false,"fractionable":true,'
        b'"min_order_size":"0.0001","min_trade_increment":"0.0001",'
        b'"price_increment":"0.01","attributes":["fractional_eh"]}'
    )
    asset = msgspec.json.decode(raw, type=AlpacaAsset)
    assert asset.symbol == "BTC/USD"
    assert asset.min_order_size == "0.0001"
    assert asset.min_trade_increment == "0.0001"
    assert asset.price_increment == "0.01"
    assert asset.attributes == ["fractional_eh"]
    assert asset.fractionable is True


def test_alpaca_asset_inactive():
    raw = (
        b'{"id":"x","asset_class":"us_equity","exchange":"NYSE","symbol":"DEFUNCT",'
        b'"name":"Old Co","status":"inactive","tradable":false,"marginable":false,'
        b'"shortable":false,"easy_to_borrow":false,"fractionable":false}'
    )
    asset = msgspec.json.decode(raw, type=AlpacaAsset)
    assert asset.status == "inactive"
    assert asset.tradable is False
    assert asset.marginable is False


def test_alpaca_asset_maintenance_margin_field():
    raw = (
        b'{"id":"x","asset_class":"us_equity","exchange":"NASDAQ","symbol":"SPY",'
        b'"name":"SPDR S&P 500","status":"active","tradable":true,"marginable":true,'
        b'"shortable":true,"easy_to_borrow":true,"fractionable":true,'
        b'"maintenance_margin_requirement":"30"}'
    )
    asset = msgspec.json.decode(raw, type=AlpacaAsset)
    assert asset.maintenance_margin_requirement == "30"


# ---------------------------------------------------------------------------
# AlpacaOrder
# ---------------------------------------------------------------------------

def test_alpaca_order_decode_minimal():
    raw = (
        b'{"id":"abc123","client_order_id":"cid1","symbol":"AAPL","asset_class":"us_equity",'
        b'"side":"buy","type":"market","time_in_force":"day","status":"filled",'
        b'"qty":"10","filled_qty":"10","filled_avg_price":"150.00"}'
    )
    order = msgspec.json.decode(raw, type=AlpacaOrder)
    assert order.symbol == "AAPL"
    assert order.status == "filled"
    assert order.filled_avg_price == "150.00"
    assert order.filled_qty == "10"
    assert float(order.filled_qty) == 10.0
    assert float(order.filled_avg_price) == 150.0
    # Unset optionals are None
    assert order.limit_price is None
    assert order.stop_price is None
    assert order.legs is None
    assert order.created_at is None


def test_alpaca_order_decode_with_timestamps():
    raw = (
        b'{"id":"abc123","client_order_id":"cid1","symbol":"AAPL","asset_class":"us_equity",'
        b'"side":"buy","type":"limit","time_in_force":"day","status":"accepted",'
        b'"qty":"5","limit_price":"100.00","filled_qty":"0",'
        b'"created_at":"2024-01-15T14:30:00.123456789Z",'
        b'"submitted_at":"2024-01-15T14:30:00.200000000Z"}'
    )
    order = msgspec.json.decode(raw, type=AlpacaOrder)
    assert order.limit_price == "100.00"
    assert order.created_at == "2024-01-15T14:30:00.123456789Z"
    assert order.submitted_at == "2024-01-15T14:30:00.200000000Z"
    assert order.filled_qty == "0"
    assert order.filled_at is None
    assert order.canceled_at is None


def test_alpaca_order_decode_canceled_with_timestamp():
    raw = (
        b'{"id":"abc","client_order_id":"cid","symbol":"MSFT","asset_class":"us_equity",'
        b'"side":"sell","type":"limit","time_in_force":"gtc","status":"canceled",'
        b'"qty":"2","limit_price":"999.00","filled_qty":"0",'
        b'"created_at":"2024-01-15T09:00:00Z","canceled_at":"2024-01-15T15:30:00Z"}'
    )
    order = msgspec.json.decode(raw, type=AlpacaOrder)
    assert order.status == "canceled"
    assert order.canceled_at == "2024-01-15T15:30:00Z"
    assert order.filled_qty == "0"


def test_alpaca_order_decode_with_legs():
    raw = (
        b'{"id":"parent","client_order_id":"cid1","symbol":"AAPL","asset_class":"us_equity",'
        b'"side":"buy","type":"market","time_in_force":"day","status":"new","qty":"10",'
        b'"order_class":"bracket","legs":['
        b'{"id":"tp","client_order_id":"tp-cid","symbol":"AAPL","asset_class":"us_equity",'
        b'"side":"sell","type":"limit","time_in_force":"gtc","status":"held","qty":"10",'
        b'"limit_price":"160.00"},'
        b'{"id":"sl","client_order_id":"sl-cid","symbol":"AAPL","asset_class":"us_equity",'
        b'"side":"sell","type":"stop","time_in_force":"gtc","status":"held","qty":"10",'
        b'"stop_price":"135.00"}'
        b']}'
    )
    order = msgspec.json.decode(raw, type=AlpacaOrder)
    assert order.order_class == "bracket"
    assert order.legs is not None
    assert len(order.legs) == 2
    tp, sl = order.legs
    assert tp.limit_price == "160.00"
    assert sl.stop_price == "135.00"


def test_alpaca_order_extended_hours_defaults_false():
    raw = (
        b'{"id":"x","client_order_id":"y","symbol":"AAPL","asset_class":"us_equity",'
        b'"side":"buy","type":"market","time_in_force":"day","status":"new"}'
    )
    order = msgspec.json.decode(raw, type=AlpacaOrder)
    assert order.extended_hours is False


def test_alpaca_order_extended_hours_true():
    raw = (
        b'{"id":"x","client_order_id":"y","symbol":"AAPL","asset_class":"us_equity",'
        b'"side":"buy","type":"market","time_in_force":"day","status":"new",'
        b'"extended_hours":true}'
    )
    order = msgspec.json.decode(raw, type=AlpacaOrder)
    assert order.extended_hours is True


def test_alpaca_order_trail_fields():
    raw = (
        b'{"id":"trail1","client_order_id":"cid","symbol":"TSLA","asset_class":"us_equity",'
        b'"side":"buy","type":"trailing_stop","time_in_force":"gtc","status":"new",'
        b'"qty":"1","trail_percent":"5.0","hwm":"250.00"}'
    )
    order = msgspec.json.decode(raw, type=AlpacaOrder)
    assert order.trail_percent == "5.0"
    assert order.hwm == "250.00"
    assert order.trail_price is None


# ---------------------------------------------------------------------------
# AlpacaAccount
# ---------------------------------------------------------------------------

def test_alpaca_account_decode_required():
    raw = (
        b'{"id":"acc1","account_number":"123456789","status":"ACTIVE","currency":"USD",'
        b'"buying_power":"100000","cash":"50000","portfolio_value":"150000","equity":"150000",'
        b'"pattern_day_trader":false,"trading_blocked":false,"shorting_enabled":true,'
        b'"daytrade_count":0}'
    )
    account = msgspec.json.decode(raw, type=AlpacaAccount)
    assert account.currency == "USD"
    assert account.pattern_day_trader is False
    assert account.trading_blocked is False
    assert account.shorting_enabled is True
    assert account.daytrade_count == 0
    assert isinstance(account.daytrade_count, int)
    # Financial fields are strings parseable as float
    assert float(account.buying_power) == 100000.0
    assert float(account.cash) == 50000.0
    assert float(account.portfolio_value) == 150000.0
    assert float(account.equity) == 150000.0


def test_alpaca_account_multiplier_default():
    raw = (
        b'{"id":"acc1","account_number":"123","status":"ACTIVE","currency":"USD",'
        b'"buying_power":"0","cash":"0","portfolio_value":"0","equity":"0",'
        b'"pattern_day_trader":false,"trading_blocked":false,"shorting_enabled":false,'
        b'"daytrade_count":0}'
    )
    account = msgspec.json.decode(raw, type=AlpacaAccount)
    assert account.multiplier == "1"


def test_alpaca_account_with_optional_margin_fields():
    raw = (
        b'{"id":"acc1","account_number":"123","status":"ACTIVE","currency":"USD",'
        b'"buying_power":"200000","cash":"100000","portfolio_value":"150000","equity":"150000",'
        b'"pattern_day_trader":false,"trading_blocked":false,"shorting_enabled":true,'
        b'"daytrade_count":1,"multiplier":"2","long_market_value":"50000",'
        b'"daytrading_buying_power":"400000","regt_buying_power":"200000",'
        b'"initial_margin":"25000","maintenance_margin":"12500",'
        b'"created_at":"2023-01-01T00:00:00Z"}'
    )
    account = msgspec.json.decode(raw, type=AlpacaAccount)
    assert account.long_market_value == "50000"
    assert account.daytrading_buying_power == "400000"
    assert account.multiplier == "2"
    assert account.daytrade_count == 1
    assert account.created_at == "2023-01-01T00:00:00Z"
    assert float(account.initial_margin) == 25000.0
    assert float(account.maintenance_margin) == 12500.0


# ---------------------------------------------------------------------------
# AlpacaPosition
# ---------------------------------------------------------------------------

def test_alpaca_position_decode_full():
    raw = (
        b'{"asset_id":"abc","symbol":"AAPL","asset_class":"us_equity","side":"long",'
        b'"qty":"10","qty_available":"10","avg_entry_price":"145.00",'
        b'"market_value":"1500.00","cost_basis":"1450.00","unrealized_pl":"50.00",'
        b'"current_price":"150.00","exchange":"NASDAQ","asset_marginable":true}'
    )
    pos = msgspec.json.decode(raw, type=AlpacaPosition)
    assert pos.symbol == "AAPL"
    assert pos.side == "long"
    assert pos.qty == "10"
    assert float(pos.qty) == 10.0
    assert float(pos.avg_entry_price) == 145.0
    assert float(pos.current_price) == 150.0
    assert float(pos.unrealized_pl) == 50.0
    assert pos.asset_marginable is True


def test_alpaca_position_fractional_qty():
    raw = (
        b'{"asset_id":"abc","symbol":"AAPL","asset_class":"us_equity","side":"long",'
        b'"qty":"0.5","qty_available":"0.5","avg_entry_price":"145.00"}'
    )
    pos = msgspec.json.decode(raw, type=AlpacaPosition)
    assert float(pos.qty) == 0.5


def test_alpaca_position_short_side():
    raw = (
        b'{"asset_id":"abc","symbol":"AAPL","asset_class":"us_equity","side":"short",'
        b'"qty":"5","qty_available":"5","avg_entry_price":"155.00"}'
    )
    pos = msgspec.json.decode(raw, type=AlpacaPosition)
    assert pos.side == "short"


def test_alpaca_position_optional_fields_default_none():
    raw = (
        b'{"asset_id":"x","symbol":"TEST","asset_class":"us_equity","side":"long",'
        b'"qty":"1","qty_available":"1","avg_entry_price":"10.00"}'
    )
    pos = msgspec.json.decode(raw, type=AlpacaPosition)
    assert pos.market_value is None
    assert pos.cost_basis is None
    assert pos.unrealized_pl is None
    assert pos.current_price is None
    assert pos.exchange is None
    assert pos.asset_marginable is None


# ---------------------------------------------------------------------------
# AlpacaTradeUpdate
# ---------------------------------------------------------------------------

def test_alpaca_trade_update_fill():
    raw = (
        b'{"event":"fill","order":{"id":"ord1","client_order_id":"cid1","symbol":"AAPL",'
        b'"asset_class":"us_equity","side":"buy","type":"market","time_in_force":"day",'
        b'"status":"filled","qty":"10","filled_qty":"10","filled_avg_price":"150.00"},'
        b'"timestamp":"2024-01-15T14:30:01.123Z","price":"150.00","qty":"10",'
        b'"execution_id":"exec-abc"}'
    )
    update = msgspec.json.decode(raw, type=AlpacaTradeUpdate)
    assert update.event == "fill"
    assert update.order.symbol == "AAPL"
    assert update.order.status == "filled"
    assert update.price == "150.00"
    assert update.qty == "10"
    assert update.execution_id == "exec-abc"
    assert update.timestamp == "2024-01-15T14:30:01.123Z"


def test_alpaca_trade_update_new_order():
    raw = (
        b'{"event":"new","order":{"id":"ord2","client_order_id":"cid2","symbol":"MSFT",'
        b'"asset_class":"us_equity","side":"sell","type":"limit","time_in_force":"gtc",'
        b'"status":"new","qty":"5","limit_price":"300.00"}}'
    )
    update = msgspec.json.decode(raw, type=AlpacaTradeUpdate)
    assert update.event == "new"
    assert update.order.symbol == "MSFT"
    assert update.price is None
    assert update.qty is None
    assert update.execution_id is None


# ---------------------------------------------------------------------------
# AlpacaWsQuote
# ---------------------------------------------------------------------------

def test_alpaca_ws_quote_decode():
    raw = (
        b'{"T":"q","S":"AAPL","ax":"C","ap":150.10,"as":100,'
        b'"bx":"C","bp":150.00,"bs":200,"t":"2024-01-01T10:00:00Z"}'
    )
    quote = msgspec.json.decode(raw, type=AlpacaWsQuote)
    assert quote.T == "q"
    assert quote.S == "AAPL"
    assert quote.ap == 150.10
    assert quote.as_ == 100
    assert quote.bp == 150.00
    assert quote.bs == 200
    assert isinstance(quote.ap, float)
    assert isinstance(quote.bp, float)
    assert isinstance(quote.as_, int)
    assert isinstance(quote.bs, int)


def test_alpaca_ws_quote_ask_bid_spread():
    """Ask price must not be below bid price in valid data."""
    raw = (
        b'{"T":"q","S":"AAPL","ax":"C","ap":150.10,"as":100,'
        b'"bx":"C","bp":150.00,"bs":200,"t":"2024-01-01T10:00:00Z"}'
    )
    quote = msgspec.json.decode(raw, type=AlpacaWsQuote)
    assert quote.ap >= quote.bp


def test_alpaca_ws_quote_nanosecond_timestamp():
    """Alpaca sends nanosecond-precision RFC3339 timestamps."""
    raw = (
        b'{"T":"q","S":"AAPL","ax":"C","ap":150.10,"as":100,'
        b'"bx":"C","bp":150.00,"bs":200,"t":"2024-01-15T14:30:00.123456789Z"}'
    )
    quote = msgspec.json.decode(raw, type=AlpacaWsQuote)
    assert quote.t == "2024-01-15T14:30:00.123456789Z"


def test_alpaca_ws_quote_with_conditions_and_tape():
    raw = (
        b'{"T":"q","S":"MSFT","ax":"Q","ap":200.50,"as":50,'
        b'"c":["R"],"z":"C","t":"2024-01-01T10:00:00Z"}'
    )
    quote = msgspec.json.decode(raw, type=AlpacaWsQuote)
    assert quote.c == ["R"]
    assert quote.z == "C"
    # bid fields default to zero when absent
    assert quote.bp == 0.0
    assert quote.bs == 0
    assert quote.bx == ""


# ---------------------------------------------------------------------------
# AlpacaWsTrade
# ---------------------------------------------------------------------------

def test_alpaca_ws_trade_decode():
    raw = (
        b'{"T":"t","S":"AAPL","i":12345,"x":"C","p":150.05,"s":50,'
        b'"t":"2024-01-01T10:00:01Z"}'
    )
    trade = msgspec.json.decode(raw, type=AlpacaWsTrade)
    assert trade.T == "t"
    assert trade.S == "AAPL"
    assert trade.p == 150.05
    assert trade.s == 50
    assert isinstance(trade.p, float)
    assert isinstance(trade.s, int)
    assert trade.p > 0
    assert trade.s > 0


def test_alpaca_ws_trade_nanosecond_timestamp():
    raw = (
        b'{"T":"t","S":"AAPL","i":99999,"x":"C","p":150.05,"s":50,'
        b'"t":"2024-01-15T14:30:00.987654321Z"}'
    )
    trade = msgspec.json.decode(raw, type=AlpacaWsTrade)
    assert trade.t == "2024-01-15T14:30:00.987654321Z"


def test_alpaca_ws_trade_with_conditions():
    raw = (
        b'{"T":"t","S":"AAPL","i":1,"x":"C","p":150.0,"s":10,'
        b'"c":["@","T"],"z":"C","t":"2024-01-01T10:00:00Z"}'
    )
    trade = msgspec.json.decode(raw, type=AlpacaWsTrade)
    assert trade.c == ["@", "T"]
    assert trade.z == "C"


def test_alpaca_ws_trade_defaults_when_optional_absent():
    raw = b'{"T":"t","S":"AAPL"}'
    trade = msgspec.json.decode(raw, type=AlpacaWsTrade)
    assert trade.i == 0
    assert trade.x == ""
    assert trade.p == 0.0
    assert trade.s == 0
    assert trade.c is None
    assert trade.t == ""


# ---------------------------------------------------------------------------
# AlpacaWsBar
# ---------------------------------------------------------------------------

def test_alpaca_ws_bar_decode():
    raw = (
        b'{"T":"b","S":"AAPL","o":150.0,"h":151.0,"l":149.5,"c":150.5,'
        b'"v":100000,"t":"2024-01-01T10:00:00Z"}'
    )
    bar = msgspec.json.decode(raw, type=AlpacaWsBar)
    assert bar.T == "b"
    assert bar.S == "AAPL"
    assert bar.o == 150.0
    assert bar.h == 151.0
    assert bar.low == 149.5
    assert bar.c == 150.5
    assert bar.v == 100000.0
    assert isinstance(bar.o, float)
    assert isinstance(bar.v, float)
    # Optional fields absent → None
    assert bar.vw is None
    assert bar.n is None


def test_alpaca_ws_bar_with_vwap_and_trade_count():
    raw = (
        b'{"T":"b","S":"AAPL","o":150.0,"h":151.0,"l":149.5,"c":150.5,'
        b'"v":100000,"vw":150.3,"n":523,"t":"2024-01-01T10:00:00Z"}'
    )
    bar = msgspec.json.decode(raw, type=AlpacaWsBar)
    assert bar.vw == 150.3
    assert bar.n == 523
    assert isinstance(bar.vw, float)
    assert isinstance(bar.n, int)


def test_alpaca_ws_bar_ohlc_invariants():
    """High must be max(o, c); low must be min(o, c)."""
    raw = (
        b'{"T":"b","S":"AAPL","o":150.0,"h":151.0,"l":149.5,"c":150.5,'
        b'"v":100000,"t":"2024-01-01T10:00:00Z"}'
    )
    bar = msgspec.json.decode(raw, type=AlpacaWsBar)
    assert bar.h >= bar.o
    assert bar.h >= bar.c
    assert bar.low <= bar.o
    assert bar.low <= bar.c


def test_alpaca_ws_bar_low_field_name_alias():
    """The 'l' JSON field must map to the .low attribute (not conflict with Python builtin)."""
    raw = (
        b'{"T":"b","S":"TEST","o":10.0,"h":12.0,"l":9.0,"c":11.0,'
        b'"v":500,"t":"2024-01-01T10:00:00Z"}'
    )
    bar = msgspec.json.decode(raw, type=AlpacaWsBar)
    assert bar.low == 9.0


def test_alpaca_ws_bar_crypto():
    """Crypto bar with vwap and trade count — structure identical to equity."""
    raw = (
        b'{"T":"b","S":"BTC/USD","o":42000.0,"h":42500.0,"l":41800.0,"c":42200.0,'
        b'"v":15.5,"vw":42150.0,"n":312,"t":"2024-01-01T10:00:00Z"}'
    )
    bar = msgspec.json.decode(raw, type=AlpacaWsBar)
    assert bar.S == "BTC/USD"
    assert bar.vw == 42150.0
    assert bar.n == 312
    assert bar.h >= bar.o
    assert bar.h >= bar.c
    assert bar.low <= bar.o
    assert bar.low <= bar.c


# ---------------------------------------------------------------------------
# AlpacaWsSubscriptionMsg
# ---------------------------------------------------------------------------

def test_alpaca_ws_subscription_msg_full():
    raw = (
        b'{"T":"subscription","trades":["AAPL"],'
        b'"quotes":["AAPL","MSFT"],"bars":["TSLA"]}'
    )
    msg = msgspec.json.decode(raw, type=AlpacaWsSubscriptionMsg)
    assert msg.T == "subscription"
    assert "AAPL" in msg.trades
    assert "MSFT" in msg.quotes
    assert "TSLA" in msg.bars


def test_alpaca_ws_subscription_msg_empty_lists():
    raw = b'{"T":"subscription","trades":[],"quotes":[],"bars":[]}'
    msg = msgspec.json.decode(raw, type=AlpacaWsSubscriptionMsg)
    assert msg.trades == []
    assert msg.quotes == []
    assert msg.bars == []


def test_alpaca_ws_subscription_msg_defaults_when_absent():
    raw = b'{"T":"subscription"}'
    msg = msgspec.json.decode(raw, type=AlpacaWsSubscriptionMsg)
    assert msg.trades == []
    assert msg.quotes == []
    assert msg.bars == []


# ---------------------------------------------------------------------------
# AlpacaWsErrorMsg
# ---------------------------------------------------------------------------

def test_alpaca_ws_error_msg_full():
    raw = b'{"T":"error","code":406,"msg":"connection limit exceeded"}'
    err = msgspec.json.decode(raw, type=AlpacaWsErrorMsg)
    assert err.T == "error"
    assert err.code == 406
    assert err.msg == "connection limit exceeded"


def test_alpaca_ws_error_msg_auth_failure():
    raw = b'{"T":"error","code":401,"msg":"not authenticated"}'
    err = msgspec.json.decode(raw, type=AlpacaWsErrorMsg)
    assert err.code == 401


def test_alpaca_ws_error_msg_defaults():
    raw = b'{"T":"error"}'
    err = msgspec.json.decode(raw, type=AlpacaWsErrorMsg)
    assert err.code == 0
    assert err.msg == ""
