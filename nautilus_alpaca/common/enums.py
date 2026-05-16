from enum import StrEnum


class AlpacaEnvironment(StrEnum):
    LIVE = "live"
    PAPER = "paper"

    @property
    def is_paper(self) -> bool:
        return self == AlpacaEnvironment.PAPER


class AlpacaAssetClass(StrEnum):
    US_EQUITY = "us_equity"
    US_OPTION = "us_option"
    CRYPTO = "crypto"


class AlpacaOrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class AlpacaOrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class AlpacaTimeInForce(StrEnum):
    DAY = "day"
    GTC = "gtc"
    OPG = "opg"
    CLS = "cls"
    IOC = "ioc"
    FOK = "fok"


class AlpacaOrderStatus(StrEnum):
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REPLACED = "replaced"
    REJECTED = "rejected"
    PENDING_CANCEL = "pending_cancel"
    PENDING_REPLACE = "pending_replace"
    ACCEPTED = "accepted"
    PENDING_NEW = "pending_new"
    ACCEPTED_FOR_BIDDING = "accepted_for_bidding"
    STOPPED = "stopped"
    SUSPENDED = "suspended"
    CALCULATED = "calculated"
    DONE_FOR_DAY = "done_for_day"


class AlpacaWsEventType(StrEnum):
    NEW = "new"
    FILL = "fill"
    PARTIAL_FILL = "partial_fill"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REPLACED = "replaced"
    REJECTED = "rejected"
    PENDING_NEW = "pending_new"
    PENDING_CANCEL = "pending_cancel"
    PENDING_REPLACE = "pending_replace"
    CALCULATED = "calculated"
    DONE_FOR_DAY = "done_for_day"
    STOPPED = "stopped"
    SUSPENDED = "suspended"
    ORDER_CANCEL_REJECTED = "order_cancel_rejected"
    ORDER_REPLACE_REJECTED = "order_replace_rejected"
