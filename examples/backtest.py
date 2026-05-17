"""
Backtest example: EMA crossover on AAPL daily bars.

Fetches one year of AAPL daily bars from the Alpaca historical REST API,
loads them into a nautilus BacktestEngine, and runs the EmaCrossover strategy.

Prerequisites:
    export ALPACA_PAPER_API_KEY=your_key
    export ALPACA_PAPER_API_SECRET=your_secret

Run:
    .venv/bin/python examples/backtest.py
"""

from datetime import datetime, timezone
from decimal import Decimal

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import Bar, BarSpecification, BarType
from nautilus_trader.model.enums import (
    AccountType,
    AggregationSource,
    BarAggregation,
    OmsType,
    PriceType,
)
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Money, Price, Quantity

from nautilus_alpaca.common.credentials import get_api_key, get_api_secret
from examples.ema_crossover import EmaCrossover, EmaCrossoverConfig

SYMBOL = "AAPL"
VENUE = "ALPACA"
INSTRUMENT_ID = f"{SYMBOL}.{VENUE}"
BAR_TYPE_STR = f"{INSTRUMENT_ID}-1-DAY-LAST-EXTERNAL"
START = datetime(2024, 1, 1, tzinfo=timezone.utc)
END = datetime(2024, 12, 31, tzinfo=timezone.utc)


def fetch_daily_bars(api_key: str, api_secret: str) -> list[Bar]:
    client = StockHistoricalDataClient(api_key=api_key, secret_key=api_secret)
    request = StockBarsRequest(
        symbol_or_symbols=SYMBOL,
        timeframe=TimeFrame(1, TimeFrameUnit.Day),
        start=START,
        end=END,
    )
    response = client.get_stock_bars(request)

    instrument_id = InstrumentId.from_str(INSTRUMENT_ID)
    bar_type = BarType(
        instrument_id=instrument_id,
        bar_spec=BarSpecification(1, BarAggregation.DAY, PriceType.LAST),
        aggregation_source=AggregationSource.EXTERNAL,
    )

    bars: list[Bar] = []
    for raw in response[SYMBOL]:
        ts = int(raw.timestamp.timestamp() * 1e9)
        bars.append(
            Bar(
                bar_type=bar_type,
                open=Price(float(raw.open), 2),
                high=Price(float(raw.high), 2),
                low=Price(float(raw.low), 2),
                close=Price(float(raw.close), 2),
                volume=Quantity(float(raw.volume), 0),
                ts_event=ts,
                ts_init=ts,
            )
        )
    return sorted(bars, key=lambda b: b.ts_event)


def build_instrument() -> Equity:
    return Equity(
        instrument_id=InstrumentId.from_str(INSTRUMENT_ID),
        raw_symbol=Symbol(SYMBOL),
        currency=USD,
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        lot_size=Quantity.from_str("1"),
        ts_event=0,
        ts_init=0,
    )


def main() -> None:
    api_key = get_api_key(paper=True)
    api_secret = get_api_secret(paper=True)

    print(f"Fetching {SYMBOL} daily bars {START.date()} → {END.date()} ...")
    bars = fetch_daily_bars(api_key, api_secret)
    print(f"  {len(bars)} bars loaded.")

    engine = BacktestEngine(
        config=BacktestEngineConfig(
            trader_id="BACKTEST-001",
            logging=LoggingConfig(log_level="WARNING"),
        )
    )

    engine.add_venue(
        venue=Venue(VENUE),
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        starting_balances=[Money(100_000, USD)],
    )

    instrument = build_instrument()
    engine.add_instrument(instrument)
    engine.add_data(bars)

    strategy = EmaCrossover(
        EmaCrossoverConfig(
            instrument_id=INSTRUMENT_ID,
            bar_type=BAR_TYPE_STR,
            fast_ema_period=10,
            slow_ema_period=20,
            trade_size="100",
        )
    )
    engine.add_strategy(strategy)

    engine.run()

    stats = engine.get_result()
    print("\n--- Backtest result ---")
    for key, value in stats.stats_pnls.items():
        print(f"  {key}: {value}")
    for key, value in stats.stats_returns.items():
        print(f"  {key}: {value}")

    engine.dispose()


if __name__ == "__main__":
    main()
