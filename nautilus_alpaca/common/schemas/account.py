from __future__ import annotations

from typing import Optional

import msgspec


class AlpacaAccount(msgspec.Struct, frozen=True):
    """Response from GET /v2/account."""

    id: str
    account_number: str
    status: str
    currency: str
    buying_power: str
    cash: str
    portfolio_value: str
    equity: str
    pattern_day_trader: bool
    trading_blocked: bool
    shorting_enabled: bool
    daytrade_count: int
    multiplier: str = "1"
    long_market_value: Optional[str] = None
    short_market_value: Optional[str] = None
    last_equity: Optional[str] = None
    initial_margin: Optional[str] = None
    maintenance_margin: Optional[str] = None
    last_maintenance_margin: Optional[str] = None
    sma: Optional[str] = None
    non_marginable_buying_power: Optional[str] = None
    daytrading_buying_power: Optional[str] = None
    regt_buying_power: Optional[str] = None
    created_at: Optional[str] = None


class AlpacaPosition(msgspec.Struct, frozen=True):
    """Entry from GET /v2/positions."""

    asset_id: str
    symbol: str
    asset_class: str
    side: str                          # "long" or "short"
    qty: str
    qty_available: str
    avg_entry_price: str
    market_value: Optional[str] = None
    cost_basis: Optional[str] = None
    unrealized_pl: Optional[str] = None
    current_price: Optional[str] = None
    exchange: Optional[str] = None
    asset_marginable: Optional[bool] = None
    unrealized_plpc: Optional[str] = None
    unrealized_intraday_pl: Optional[str] = None
    unrealized_intraday_plpc: Optional[str] = None
    lastday_price: Optional[str] = None
    change_today: Optional[str] = None


class AlpacaOrder(msgspec.Struct, frozen=True):
    """Order object from GET /v2/orders and trading WebSocket."""

    id: str
    client_order_id: str
    symbol: str
    asset_class: str
    side: str
    type: str
    time_in_force: str
    status: str
    qty: Optional[str] = None
    notional: Optional[str] = None
    filled_qty: Optional[str] = None
    filled_avg_price: Optional[str] = None
    limit_price: Optional[str] = None
    stop_price: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    submitted_at: Optional[str] = None
    filled_at: Optional[str] = None
    expired_at: Optional[str] = None
    canceled_at: Optional[str] = None
    failed_at: Optional[str] = None
    replaced_at: Optional[str] = None
    replaced_by: Optional[str] = None
    replaces: Optional[str] = None
    order_class: Optional[str] = None
    order_type: Optional[str] = None
    extended_hours: bool = False
    legs: Optional[list[AlpacaOrder]] = None
    trail_percent: Optional[str] = None
    trail_price: Optional[str] = None
    hwm: Optional[str] = None


class AlpacaTradeUpdate(msgspec.Struct, frozen=True):
    """Trade update event from trading WebSocket."""

    event: str
    order: AlpacaOrder
    timestamp: Optional[str] = None
    position_qty: Optional[str] = None
    price: Optional[str] = None
    qty: Optional[str] = None
    execution_id: Optional[str] = None
