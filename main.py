"""
Minimal example: Alpaca adapter with nautilus-trader TradingNode.
Uses paper trading by default.

Prerequisites:
    export ALPACA_PAPER_API_KEY=your_key
    export ALPACA_PAPER_API_SECRET=your_secret

Run:
    python main.py
"""
from nautilus_trader.config import TradingNodeConfig, InstrumentProviderConfig
from nautilus_trader.live.node import TradingNode

from nautilus_alpaca import (
    AlpacaDataClientConfig,
    AlpacaExecClientConfig,
    AlpacaLiveDataClientFactory,
    AlpacaLiveExecClientFactory,
)


def build_node() -> TradingNode:
    config = TradingNodeConfig(
        trader_id="ALPACA-001",
        data_clients={
            "ALPACA": AlpacaDataClientConfig(
                paper=True,
                feed="iex",
                instrument_provider=InstrumentProviderConfig(load_all=False),
            ),
        },
        exec_clients={
            "ALPACA": AlpacaExecClientConfig(paper=True),
        },
    )
    node = TradingNode(config=config)
    node.add_data_client_factory("ALPACA", AlpacaLiveDataClientFactory)
    node.add_exec_client_factory("ALPACA", AlpacaLiveExecClientFactory)
    node.build()
    return node


if __name__ == "__main__":
    node = build_node()
    print("Node built successfully. Add strategies and call node.run() to trade.")
