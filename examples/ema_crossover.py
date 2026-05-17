"""
EMA Crossover strategy — shared by backtest.py and paper_trading.py.

Goes long when the fast EMA crosses above the slow EMA; closes the position
when the fast EMA crosses back below.  Works with any bar type.
"""

from nautilus_trader.config import StrategyConfig
from nautilus_trader.indicators import ExponentialMovingAverage
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy


class EmaCrossoverConfig(StrategyConfig, frozen=True):
    instrument_id: str          # e.g. "AAPL.ALPACA"
    bar_type: str               # e.g. "AAPL.ALPACA-1-DAY-LAST-EXTERNAL"
    fast_ema_period: int = 10
    slow_ema_period: int = 20
    trade_size: str = "100"     # whole shares; str for msgspec compatibility


class EmaCrossover(Strategy):

    def __init__(self, config: EmaCrossoverConfig) -> None:
        super().__init__(config)
        self.instrument_id = InstrumentId.from_str(config.instrument_id)
        self.bar_type = BarType.from_str(config.bar_type)
        self.fast_ema = ExponentialMovingAverage(config.fast_ema_period)
        self.slow_ema = ExponentialMovingAverage(config.slow_ema_period)
        self.trade_size = Quantity.from_str(config.trade_size)

    def on_start(self) -> None:
        self.register_indicator_for_bars(self.bar_type, self.fast_ema)
        self.register_indicator_for_bars(self.bar_type, self.slow_ema)
        self.subscribe_bars(self.bar_type)

    def on_bar(self, bar: Bar) -> None:
        if not self.fast_ema.initialized or not self.slow_ema.initialized:
            return

        open_positions = self.cache.positions_open(instrument_id=self.instrument_id)
        is_flat = len(open_positions) == 0
        is_long = any(p.is_long for p in open_positions)

        if self.fast_ema.value > self.slow_ema.value and is_flat:
            self._buy()
        elif self.fast_ema.value < self.slow_ema.value and is_long:
            self.close_all_positions(self.instrument_id)

    def _buy(self) -> None:
        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=OrderSide.BUY,
            quantity=self.trade_size,
        )
        self.submit_order(order)

    def on_stop(self) -> None:
        self.cancel_all_orders(self.instrument_id)
        self.close_all_positions(self.instrument_id)
