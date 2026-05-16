from __future__ import annotations

from typing import Optional

import msgspec


class AlpacaAsset(msgspec.Struct, frozen=True):
    """Response from GET /v2/assets and /v2/assets/{symbol}."""

    id: str
    asset_class: str          # "us_equity", "crypto", "us_option"
    exchange: str
    symbol: str
    name: str
    status: str               # "active" or "inactive"
    tradable: bool
    marginable: bool
    shortable: bool
    easy_to_borrow: bool
    fractionable: bool
    min_order_size: Optional[str] = None
    min_trade_increment: Optional[str] = None
    price_increment: Optional[str] = None
    maintenance_margin_requirement: Optional[str] = None
    attributes: Optional[list[str]] = None


class AlpacaWsQuote(msgspec.Struct, frozen=True):
    """Quote message from stock/crypto WebSocket stream (T = "q")."""

    T: str                              # message type = "q"
    S: str                              # symbol
    ax: str                             # ask exchange
    ap: float                           # ask price
    as_: int = msgspec.field(name="as") # ask size ("as" is a Python keyword)
    bx: str = ""                        # bid exchange
    bp: float = 0.0                     # bid price
    bs: int = 0                         # bid size
    c: Optional[list[str]] = None       # conditions
    t: str = ""                         # timestamp (RFC3339)
    z: Optional[str] = None             # tape


class AlpacaWsTrade(msgspec.Struct, frozen=True):
    """Trade tick message from WebSocket stream (T = "t")."""

    T: str                        # message type = "t"
    S: str                        # symbol
    i: int = 0                    # trade id
    x: str = ""                   # exchange
    p: float = 0.0                # price
    s: int = 0                    # size
    c: Optional[list[str]] = None # conditions
    t: str = ""                   # timestamp (RFC3339)
    z: Optional[str] = None       # tape


class AlpacaWsBar(msgspec.Struct, frozen=True):
    """Bar/candle message from WebSocket stream (T = "b")."""

    T: str                       # message type = "b"
    S: str                       # symbol
    o: float = 0.0               # open
    h: float = 0.0               # high
    low: float = msgspec.field(name="l", default=0.0)  # low
    c: float = 0.0               # close
    v: float = 0.0               # volume
    t: str = ""                  # bar open timestamp (RFC3339)
    vw: Optional[float] = None   # VWAP
    n: Optional[int] = None      # number of trades in the bar


class AlpacaWsSubscriptionMsg(msgspec.Struct, frozen=True):
    """Subscription confirmation from WebSocket (T = "subscription")."""

    T: str
    trades: list[str] = msgspec.field(default_factory=list)
    quotes: list[str] = msgspec.field(default_factory=list)
    bars: list[str] = msgspec.field(default_factory=list)


class AlpacaWsErrorMsg(msgspec.Struct, frozen=True):
    """Error message from WebSocket stream (T = "error")."""

    T: str
    code: int = 0
    msg: str = ""
