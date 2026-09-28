"""AgenticTrader: a multi-agent LLM trading framework for equities and FX.

A trading desk of specialised agents (analysts, researchers, trader, risk team,
portfolio manager) under a policy-gated, evidence-backed agentic harness, with a
C++ quant core (indicators, backtester, risk, alphas, execution) exposed via pybind11.
"""
from .backtest import ComparisonReport, PortfolioReport, run_agent_backtest, run_portfolio_backtest
from .config import DEFAULT_CONFIG, RULES_V02, RULES_V03, make_config
from .evaluation import EvaluationResult, evaluate
from .graph import TradingGraph
from .instruments import Instrument
from .provenance import package_version
from .state import Action, FinalDecision, TradingState

__version__ = package_version()

__all__ = ["TradingGraph", "run_agent_backtest", "run_portfolio_backtest", "ComparisonReport",
           "PortfolioReport", "evaluate", "EvaluationResult", "DEFAULT_CONFIG", "RULES_V02", "RULES_V03",
           "make_config", "Instrument", "Action", "FinalDecision", "TradingState", "__version__"]
