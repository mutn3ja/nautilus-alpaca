"""
AlpacaInstrumentProvider — loads tradable instruments from the Alpaca Assets REST API
and converts them into nautilus-trader ``Instrument`` objects.
"""

from __future__ import annotations

from typing import Any

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetClass, AssetStatus
from alpaca.trading.requests import GetAssetsRequest

from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.providers import InstrumentProvider
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.model.instruments import Instrument

from nautilus_alpaca.common.constants import ALPACA_VENUE
from nautilus_alpaca.common.enums import AlpacaEnvironment
from nautilus_alpaca.common.parsing import parse_instrument
from nautilus_alpaca.common.schemas.market import AlpacaAsset
from nautilus_alpaca.config import AlpacaInstrumentProviderConfig


# Mapping from config string values to alpaca-py AssetClass enum values
_ASSET_CLASS_MAP: dict[str, AssetClass] = {
    "us_equity": AssetClass.US_EQUITY,
    "crypto": AssetClass.CRYPTO,
    "us_option": AssetClass.US_OPTION,
}


class AlpacaInstrumentProvider(InstrumentProvider):
    """
    Provides a means of loading instruments from the Alpaca Assets REST API.

    Parameters
    ----------
    clock : LiveClock
        The clock for the provider.
    api_key : str
        The Alpaca API public key.
    api_secret : str
        The Alpaca API secret key.
    environment : AlpacaEnvironment
        The Alpaca environment (LIVE or PAPER).
    base_url_http : str, optional
        Override for the Alpaca HTTP base URL (useful for testing).
    config : AlpacaInstrumentProviderConfig, optional
        The configuration for the provider.
    venue : Venue, default ALPACA_VENUE
        The nautilus venue identifier.

    """

    def __init__(
        self,
        clock: LiveClock,
        api_key: str,
        api_secret: str,
        environment: AlpacaEnvironment,
        base_url_http: str | None = None,
        config: AlpacaInstrumentProviderConfig | None = None,
        venue: Venue = ALPACA_VENUE,
    ) -> None:
        self._alpaca_config: AlpacaInstrumentProviderConfig = config or AlpacaInstrumentProviderConfig()
        super().__init__(config=self._alpaca_config)

        self._clock = clock
        self._venue = venue
        self._environment = environment

        self._client = TradingClient(
            api_key=api_key,
            secret_key=api_secret,
            paper=environment.is_paper,
            url_override=base_url_http,
        )

        self._log_warnings: bool = self._alpaca_config.log_warnings

    async def load_all_async(self, filters: dict[str, Any] | None = None) -> None:
        """
        Load all active instruments from the Alpaca Assets API.

        Optionally filters by ``config.asset_class`` when set.

        Parameters
        ----------
        filters : dict, optional
            Unused by this implementation (reserved for future use).

        """
        filters_str = "..." if not filters else f" with filters {filters}..."
        self._log.info(f"Loading all instruments{filters_str}")

        asset_class_filter: AssetClass | None = None
        if self._alpaca_config.asset_class:
            asset_class_filter = _ASSET_CLASS_MAP.get(self._alpaca_config.asset_class)
            if asset_class_filter is None:
                self._log.warning(
                    f"Unknown asset_class filter {self._alpaca_config.asset_class!r}; "
                    "loading all asset classes instead."
                )

        req = GetAssetsRequest(
            status=AssetStatus.ACTIVE,
            asset_class=asset_class_filter,
        )
        assets = self._client.get_all_assets(req)

        count = 0
        for asset in assets:
            instrument = self._parse_asset(asset)
            if instrument is not None:
                self.add(instrument)
                count += 1
                self._log.debug(f"Added instrument {instrument.id}")

        self._log.info(f"Loaded {count} instruments from Alpaca")

    async def load_ids_async(
        self,
        instrument_ids: list[InstrumentId],
        filters: dict[str, Any] | None = None,
    ) -> None:
        """
        Load specific instruments by symbol using per-symbol Alpaca API calls.

        Alpaca supports per-symbol asset fetching, so this is more efficient than
        fetching the full asset list when only a few instruments are needed.

        Parameters
        ----------
        instrument_ids : list[InstrumentId]
            The instrument IDs to load.
        filters : dict, optional
            Unused by this implementation (reserved for future use).

        """
        if not instrument_ids:
            self._log.info("No instrument IDs given for loading.")
            return

        self._log.info(f"Loading {len(instrument_ids)} instruments by ID")

        for instrument_id in instrument_ids:
            # instrument_id.symbol.value is already just the symbol (e.g. "AAPL"),
            # without the venue suffix — nautilus splits on the dot automatically.
            symbol = instrument_id.symbol.value
            try:
                raw_asset = self._client.get_asset(symbol)
                instrument = self._parse_asset(raw_asset)
                if instrument is not None:
                    self.add(instrument)
                    self._log.debug(f"Added instrument {instrument.id}")
                else:
                    self._log.debug(
                        f"Instrument {symbol!r} was skipped during parsing "
                        "(inactive or unsupported asset class)."
                    )
            except Exception as e:
                self._log.warning(f"Failed to load instrument {symbol!r}: {e}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_asset(self, raw_asset) -> Instrument | None:
        """
        Convert an alpaca-py ``Asset`` model object to a nautilus ``Instrument``.

        Maps alpaca-py model fields to the ``AlpacaAsset`` msgspec struct used by
        ``parse_instrument``, then delegates parsing.

        Parameters
        ----------
        raw_asset : alpaca.trading.models.Asset
            The raw alpaca-py asset model returned by the TradingClient.

        Returns
        -------
        Instrument or None
            Returns ``None`` for inactive assets, options, or on parse errors.

        """
        try:
            schema_asset = AlpacaAsset(
                id=str(raw_asset.id),
                asset_class=(
                    raw_asset.asset_class.value
                    if hasattr(raw_asset.asset_class, "value")
                    else str(raw_asset.asset_class)
                ),
                exchange=raw_asset.exchange or "",
                symbol=raw_asset.symbol,
                name=raw_asset.name or raw_asset.symbol,
                status=(
                    raw_asset.status.value
                    if hasattr(raw_asset.status, "value")
                    else str(raw_asset.status)
                ),
                tradable=bool(raw_asset.tradable),
                marginable=bool(raw_asset.marginable),
                shortable=bool(raw_asset.shortable),
                easy_to_borrow=bool(raw_asset.easy_to_borrow),
                fractionable=bool(raw_asset.fractionable),
                min_order_size=(
                    str(raw_asset.min_order_size)
                    if raw_asset.min_order_size is not None
                    else None
                ),
                min_trade_increment=(
                    str(raw_asset.min_trade_increment)
                    if raw_asset.min_trade_increment is not None
                    else None
                ),
                price_increment=(
                    str(raw_asset.price_increment)
                    if raw_asset.price_increment is not None
                    else None
                ),
            )
            return parse_instrument(schema_asset, self._venue)
        except Exception as e:
            if self._log_warnings:
                self._log.warning(
                    f"Failed to parse asset {getattr(raw_asset, 'symbol', '?')!r}: {e}"
                )
            return None
