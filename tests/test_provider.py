import pytest
from unittest.mock import MagicMock, patch
from nautilus_alpaca.providers import AlpacaInstrumentProvider
from nautilus_alpaca.config import AlpacaInstrumentProviderConfig
from nautilus_alpaca.common.enums import AlpacaEnvironment
from nautilus_trader.common.component import LiveClock
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Equity


def make_mock_asset(symbol="AAPL", asset_class="us_equity", status="active"):
    asset = MagicMock()
    asset.id = "test-id"
    asset.asset_class = MagicMock()
    asset.asset_class.value = asset_class
    asset.exchange = "NASDAQ"
    asset.symbol = symbol
    asset.name = symbol
    asset.status = MagicMock()
    asset.status.value = status
    asset.tradable = True
    asset.marginable = True
    asset.shortable = True
    asset.easy_to_borrow = True
    asset.fractionable = True
    asset.min_order_size = None
    asset.min_trade_increment = None
    asset.price_increment = None
    return asset


@pytest.mark.asyncio
async def test_load_all_async_populates_instruments():
    mock_assets = [make_mock_asset("AAPL"), make_mock_asset("MSFT")]

    with patch("nautilus_alpaca.providers.TradingClient") as MockClient:
        instance = MockClient.return_value
        instance.get_all_assets.return_value = mock_assets

        provider = AlpacaInstrumentProvider(
            clock=LiveClock(),
            api_key="test_key",
            api_secret="test_secret",
            environment=AlpacaEnvironment.PAPER,
            config=AlpacaInstrumentProviderConfig(),
        )

        await provider.load_all_async()

        assert provider.count > 0
        aapl = provider.find(InstrumentId.from_str("AAPL.ALPACA"))
        assert aapl is not None
        assert isinstance(aapl, Equity)
