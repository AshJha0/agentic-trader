"""Reproduce the paper's evaluation layout (Q1 2024) for equities and FX.

The window (2024-01-02 -> 2024-03-28) matches docs/evaluation/evaluation.md.

Offline by default (synthetic prices, rule-based agents) so it runs in seconds.
Pass --live to use Claude + Yahoo Finance; that makes one full agent run per
rebalance date per symbol, so check your API budget first.
"""
import sys

from agentic_trader import make_config, run_agent_backtest

live = "--live" in sys.argv
config = make_config(
    llm_provider="anthropic" if live else "offline",
    data_provider="yahoo" if live else "synthetic",
    memory_path=None,
)
for symbol in ["AAPL", "NVDA", "MSFT", "META", "GOOGL", "EURUSD", "USDJPY", "GBPUSD"]:
    rep = run_agent_backtest(symbol, "2024-01-02", "2024-03-28", config, rebalance_every=5)
    print(f"\n=== {rep.instrument.display} ({rep.instrument.asset_class}) ===")
    print(rep.table()[["CR%", "AR%", "Sharpe", "MDD%", "Trades"]].to_string())
