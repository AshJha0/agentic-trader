"""Run the agent firm on a currency pair for one date.

    python examples/run_fx.py                     # offline, synthetic data
    python examples/run_fx.py --live              # Claude + Yahoo Finance + FRED rates
"""
import sys

from agentic_trader import TradingGraph, make_config

live = "--live" in sys.argv
config = make_config(
    llm_provider="anthropic" if live else "offline",
    data_provider="yahoo" if live else "synthetic",
    fx_macro_source="fred" if live else "static",
    memory_path=None,
)
graph = TradingGraph(config, on_event=lambda stage, msg: print(f"[{stage}] {msg}"))
state, decision = graph.propagate("USDJPY", "2024-03-01")
print()
print(state.to_markdown())
