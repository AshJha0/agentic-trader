"""AgenticTrader: a multi-agent LLM trading framework for equities and FX.

Inspired by the TradingAgents paper (Xiao et al., 2024); implemented from scratch
with a C++ quant core (indicators, backtester, risk) exposed via pybind11.
"""
from .backtest import ComparisonReport, run_agent_backtest
from .config import DEFAULT_CONFIG, make_config
from .graph import TradingGraph
from .instruments import Instrument
from .state import Action, FinalDecision, TradingState

__version__ = "0.2.0"

__all__ = ["TradingGraph", "run_agent_backtest", "ComparisonReport", "DEFAULT_CONFIG",
           "make_config", "Instrument", "Action", "FinalDecision", "TradingState"]
