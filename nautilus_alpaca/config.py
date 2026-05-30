from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.config import LiveDataClientConfig
from nautilus_trader.config import LiveExecClientConfig
from nautilus_trader.config import PositiveInt

from nautilus_alpaca.common.constants import ALPACA_VENUE
from nautilus_trader.model.identifiers import Venue


class AlpacaInstrumentProviderConfig(InstrumentProviderConfig, frozen=True):
    """
    Configuration for ``AlpacaInstrumentProvider`` instances.

    Parameters
    ----------
    asset_class : str, optional
        The Alpaca asset class to filter instruments by.
        One of "us_equity", "crypto", or None to load all.
    log_warnings : bool, default True
        If parser warnings should be logged.

    """

    asset_class: str | None = None  # "us_equity" | "crypto" | None (all)
    log_warnings: bool = True


class AlpacaDataClientConfig(LiveDataClientConfig, frozen=True):
    """
    Configuration for ``AlpacaDataClient`` instances.

    Parameters
    ----------
    venue : Venue, default ALPACA_VENUE
        The venue for the client.
    api_key : str, optional
        The Alpaca API public key.
        If ``None``, the client will read from environment variables.
    api_secret : str, optional
        The Alpaca API secret key.
        If ``None``, the client will read from environment variables.
    paper : bool, default True
        If the client should connect to the Alpaca paper trading environment.
    feed : str, default "iex"
        The market data feed. Use "iex" (free, slightly delayed) or "sip" (paid, consolidated).
    base_url_http : str, optional
        The HTTP client custom endpoint override.
    base_url_ws : str, optional
        The WebSocket client custom endpoint override.
    update_instruments_interval_mins : PositiveInt or None, default 60
        The interval (minutes) between reloading instruments from the venue.

    """

    venue: Venue = ALPACA_VENUE
    api_key: str | None = None
    api_secret: str | None = None
    paper: bool = True
    feed: str = "iex"
    base_url_http: str | None = None
    base_url_ws: str | None = None
    update_instruments_interval_mins: PositiveInt | None = 60


class AlpacaExecClientConfig(LiveExecClientConfig, frozen=True):
    """
    Configuration for ``AlpacaExecutionClient`` instances.

    Parameters
    ----------
    venue : Venue, default ALPACA_VENUE
        The venue for the client.
    api_key : str, optional
        The Alpaca API public key.
        If ``None``, the client will read from environment variables.
    api_secret : str, optional
        The Alpaca API secret key.
        If ``None``, the client will read from environment variables.
    paper : bool, default True
        If the client should connect to the Alpaca paper trading environment.
    base_url_http : str, optional
        The HTTP client custom endpoint override.
    base_url_ws : str, optional
        The WebSocket client custom endpoint override.
    max_retries : PositiveInt or None, default 3
        The maximum number of times a submit, cancel or modify order request will be retried.
    retry_delay_initial_ms : PositiveInt or None, default 1000
        The initial delay (milliseconds) between retries.
    retry_delay_max_ms : PositiveInt or None, default 10000
        The maximum delay (milliseconds) between retries.
    account_polling_interval_mins : PositiveInt or None, default 60
        The interval (minutes) between polling the Alpaca account for an updated
        balance/buying-power snapshot. Set to ``None`` to disable periodic polling
        (account state is still refreshed on fills).

    """

    venue: Venue = ALPACA_VENUE
    api_key: str | None = None
    api_secret: str | None = None
    paper: bool = True
    base_url_http: str | None = None
    base_url_ws: str | None = None
    max_retries: PositiveInt | None = 3
    retry_delay_initial_ms: PositiveInt | None = 1_000
    retry_delay_max_ms: PositiveInt | None = 10_000
    account_polling_interval_mins: PositiveInt | None = 60
