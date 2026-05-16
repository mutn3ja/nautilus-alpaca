from typing import Final

from nautilus_trader.model.identifiers import ClientId, Venue


ALPACA: Final[str] = "ALPACA"
ALPACA_VENUE: Final[Venue] = Venue(ALPACA)
ALPACA_CLIENT_ID: Final[ClientId] = ClientId(ALPACA)

# REST base URLs
ALPACA_LIVE_BASE_URL_HTTP: Final[str] = "https://api.alpaca.markets"
ALPACA_PAPER_BASE_URL_HTTP: Final[str] = "https://paper-api.alpaca.markets"
ALPACA_DATA_BASE_URL_HTTP: Final[str] = "https://data.alpaca.markets"

# WebSocket URLs
ALPACA_LIVE_BASE_URL_WS: Final[str] = "wss://stream.data.alpaca.markets"
ALPACA_PAPER_BASE_URL_WS: Final[str] = "wss://stream.data.alpaca.markets"
ALPACA_LIVE_TRADING_WS_URL: Final[str] = "wss://api.alpaca.markets/stream"
ALPACA_PAPER_TRADING_WS_URL: Final[str] = "wss://paper-api.alpaca.markets/stream"

# WebSocket stream paths (appended to base WS URL)
ALPACA_WS_STOCKS_PATH: Final[str] = "/v2/iex"          # free tier
ALPACA_WS_STOCKS_SIP_PATH: Final[str] = "/v2/sip"      # paid tier
ALPACA_WS_CRYPTO_PATH: Final[str] = "/v1beta3/crypto/us"
ALPACA_WS_OPTIONS_PATH: Final[str] = "/v1beta1/indicative"
