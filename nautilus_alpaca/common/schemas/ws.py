from __future__ import annotations

from typing import Optional

import msgspec


class AlpacaWsAuthMsg(msgspec.Struct, frozen=True):
    """Outbound auth message: {"action": "auth", "key": "...", "secret": "..."}."""

    action: str
    key: str
    secret: str


class AlpacaWsSubscribeMsg(msgspec.Struct, frozen=True):
    """Outbound subscribe message."""

    action: str
    trades: list[str] = msgspec.field(default_factory=list)
    quotes: list[str] = msgspec.field(default_factory=list)
    bars: list[str] = msgspec.field(default_factory=list)


class AlpacaWsControlMsg(msgspec.Struct, frozen=True):
    """Inbound control message (connected/authenticated/error)."""

    T: str
    msg: str = ""
    code: Optional[int] = None
