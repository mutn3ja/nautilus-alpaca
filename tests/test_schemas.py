"""
Decode tests for the msgspec Struct schemas used at runtime.

Only ``AlpacaAsset`` is consumed by the adapter (the data/execution clients use
alpaca-py model objects directly), so that is all that is covered here.
"""
import msgspec

from nautilus_alpaca.common.schemas.market import AlpacaAsset


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
