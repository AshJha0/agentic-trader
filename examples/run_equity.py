"""Run the agent firm on an equity for one date.

    python examples/run_equity.py                 # offline, synthetic data
    python examples/run_equity.py --live          # Claude + Yahoo Finance
"""
import sys

from agentic_trader import TradingGraph, make_config

live = "--live" in sys.argv
config = make_config(
    llm_provider="anthropic" if live else "offline",
    data_provider="yahoo" if live else "synthetic",
    max_debate_rounds=2,
    memory_path=None,
)
graph = TradingGraph(config, on_event=lambda stage, msg: print(f"[{stage}] {msg}"))
state, decision = graph.propagate("NVDA", "2024-03-01")
print()
print(state.to_markdown())
print("\nDecision:", decision.to_dict())
