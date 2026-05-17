"""
Paper trading example: EMA crossover on AAPL 1-minute bars.

Connects to Alpaca's paper trading environment, subscribes to real-time
1-minute bars for AAPL, and runs the EmaCrossover strategy live.

Prerequisites:
    export ALPACA_PAPER_API_KEY=your_key
    export ALPACA_PAPER_API_SECRET=your_secret

Run:
    .venv/bin/python examples/paper_trading.py

Stop with Ctrl-C.
"""

from nautilus_trader.config import (
    InstrumentProviderConfig,
    LoggingConfig,
    TradingNodeConfig,
)
from nautilus_trader.live.node import TradingNode

from nautilus_alpaca import (
    AlpacaDataClientConfig,
    AlpacaExecClientConfig,
    AlpacaLiveDataClientFactory,
    AlpacaLiveExecClientFactory,
)
from examples.ema_crossover import EmaCrossover, EmaCrossoverConfig

SYMBOL = "AAPL"
VENUE = "ALPACA"
INSTRUMENT_ID = f"{SYMBOL}.{VENUE}"
BAR_TYPE_STR = f"{INSTRUMENT_ID}-1-MINUTE-LAST-EXTERNAL"


def build_node() -> TradingNode:
    config = TradingNodeConfig(
        trader_id="PAPER-001",
        logging=LoggingConfig(log_level="INFO"),
        data_clients={
            VENUE: AlpacaDataClientConfig(
                paper=True,
                feed="iex",
                instrument_provider=InstrumentProviderConfig(load_all=False),
            ),
        },
        exec_clients={
            VENUE: AlpacaExecClientConfig(paper=True),
        },
        strategies=[
            EmaCrossoverConfig(
                instrument_id=INSTRUMENT_ID,
                bar_type=BAR_TYPE_STR,
                fast_ema_period=10,
                slow_ema_period=20,
                trade_size="10",
            ),
        ],
    )

    node = TradingNode(config=config)
    node.add_data_client_factory(VENUE, AlpacaLiveDataClientFactory)
    node.add_exec_client_factory(VENUE, AlpacaLiveExecClientFactory)
    node.add_strategy(EmaCrossover)
    node.build()
    return node


if __name__ == "__main__":
    node = build_node()
    try:
        node.run()
    except KeyboardInterrupt:
        node.stop()
    finally:
        node.dispose()
