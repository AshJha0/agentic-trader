"""AgenticTrader: a multi-agent LLM trading framework for equities and FX.

Inspired by the TradingAgents paper (Xiao et al., 2024); implemented from scratch
with a C++ quant core (indicators, backtester, risk) exposed via pybind11.
"""
from .backtest import ComparisonReport, PortfolioReport, run_agent_backtest, run_portfolio_backtest
from .config import DEFAULT_CONFIG, RULES_V02, make_config
from .evaluation import EvaluationResult, evaluate
from .graph import TradingGraph
from .instruments import Instrument
from .state import Action, FinalDecision, TradingState

__version__ = "0.3.0"

__all__ = ["TradingGraph", "run_agent_backtest", "run_portfolio_backtest", "ComparisonReport",
           "PortfolioReport", "evaluate", "EvaluationResult", "DEFAULT_CONFIG", "RULES_V02",
           "make_config", "Instrument", "Action", "FinalDecision", "TradingState"]
