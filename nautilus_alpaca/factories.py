import asyncio
from functools import lru_cache

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.live.factories import LiveDataClientFactory, LiveExecClientFactory

from nautilus_alpaca.common.credentials import get_api_key, get_api_secret
from nautilus_alpaca.common.enums import AlpacaEnvironment
from nautilus_alpaca.config import (
    AlpacaDataClientConfig,
    AlpacaExecClientConfig,
    AlpacaInstrumentProviderConfig,
)
from nautilus_alpaca.data import AlpacaDataClient
from nautilus_alpaca.execution import AlpacaExecutionClient
from nautilus_alpaca.providers import AlpacaInstrumentProvider


@lru_cache(maxsize=4)
def get_cached_alpaca_instrument_provider(
    clock: LiveClock,
    api_key: str,
    api_secret: str,
    environment: AlpacaEnvironment,
    base_url_http: str | None,
    config: AlpacaInstrumentProviderConfig,
) -> AlpacaInstrumentProvider:
    """
    Cache and return an ``AlpacaInstrumentProvider`` with the given parameters.

    If a cached provider with matching parameters already exists, the cached
    provider will be returned. This ensures the data and execution clients
    share a single provider instance and instruments are only loaded once.

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
        The HTTP base URL override.
    config : AlpacaInstrumentProviderConfig
        The configuration for the provider.

    Returns
    -------
    AlpacaInstrumentProvider

    """
    return AlpacaInstrumentProvider(
        clock=clock,
        api_key=api_key,
        api_secret=api_secret,
        environment=environment,
        base_url_http=base_url_http,
        config=config,
    )


class AlpacaLiveDataClientFactory(LiveDataClientFactory):
    """
    Provides an Alpaca live data client factory.
    """

    @staticmethod
    def create(  # type: ignore[override]
        loop: asyncio.AbstractEventLoop,
        name: str,
        config: AlpacaDataClientConfig,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
    ) -> AlpacaDataClient:
        """
        Create a new Alpaca data client.

        Parameters
        ----------
        loop : asyncio.AbstractEventLoop
            The event loop for the client.
        name : str
            The custom client ID.
        config : AlpacaDataClientConfig
            The client configuration.
        msgbus : MessageBus
            The message bus for the client.
        cache : Cache
            The cache for the client.
        clock : LiveClock
            The clock for the client.

        Returns
        -------
        AlpacaDataClient

        """
        environment = AlpacaEnvironment.PAPER if config.paper else AlpacaEnvironment.LIVE
        api_key = get_api_key(config.api_key, paper=config.paper)
        api_secret = get_api_secret(config.api_secret, paper=config.paper)

        # Ensure the instrument_provider config is an AlpacaInstrumentProviderConfig
        ip_config = config.instrument_provider
        if not isinstance(ip_config, AlpacaInstrumentProviderConfig):
            ip_config = AlpacaInstrumentProviderConfig()

        provider = get_cached_alpaca_instrument_provider(
            clock=clock,
            api_key=api_key,
            api_secret=api_secret,
            environment=environment,
            base_url_http=config.base_url_http,
            config=ip_config,
        )

        return AlpacaDataClient(
            loop=loop,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=provider,
            config=config,
            api_key=api_key,
            api_secret=api_secret,
            environment=environment,
            name=name,
        )


class AlpacaLiveExecClientFactory(LiveExecClientFactory):
    """
    Provides an Alpaca live execution client factory.
    """

    @staticmethod
    def create(  # type: ignore[override]
        loop: asyncio.AbstractEventLoop,
        name: str,
        config: AlpacaExecClientConfig,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
    ) -> AlpacaExecutionClient:
        """
        Create a new Alpaca execution client.

        Parameters
        ----------
        loop : asyncio.AbstractEventLoop
            The event loop for the client.
        name : str
            The custom client ID.
        config : AlpacaExecClientConfig
            The client configuration.
        msgbus : MessageBus
            The message bus for the client.
        cache : Cache
            The cache for the client.
        clock : LiveClock
            The clock for the client.

        Returns
        -------
        AlpacaExecutionClient

        """
        environment = AlpacaEnvironment.PAPER if config.paper else AlpacaEnvironment.LIVE
        api_key = get_api_key(config.api_key, paper=config.paper)
        api_secret = get_api_secret(config.api_secret, paper=config.paper)

        # Ensure the instrument_provider config is an AlpacaInstrumentProviderConfig
        ip_config = config.instrument_provider
        if not isinstance(ip_config, AlpacaInstrumentProviderConfig):
            ip_config = AlpacaInstrumentProviderConfig()

        provider = get_cached_alpaca_instrument_provider(
            clock=clock,
            api_key=api_key,
            api_secret=api_secret,
            environment=environment,
            base_url_http=config.base_url_http,
            config=ip_config,
        )

        return AlpacaExecutionClient(
            loop=loop,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=provider,
            config=config,
            api_key=api_key,
            api_secret=api_secret,
            environment=environment,
            name=name,
        )
