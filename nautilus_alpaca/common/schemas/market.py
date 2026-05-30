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
