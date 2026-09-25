"""Multi-instrument, multi-period evaluation with a design / holdout split.

Protocol (docs/evaluation/evaluation.md):

* ``design`` period: the only data used to choose rule changes and defaults.
* ``holdout`` period: run once with frozen rules; never used for choices.
* ``paper`` period: Q1 2024, the TradingAgents paper's window (inside holdout).

For every (period, instrument) the agent and all baselines run on the same bars,
costs and carry. ``summary()`` aggregates per strategy: median Sharpe, mean
return, mean drawdown, mean exposure, and how often the agent beats plain and
volatility-targeted buy & hold on Sharpe.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pandas as pd

from .backtest import AGENT, run_agent_backtest
from .config import make_config
from .data import MarketDataProvider, get_provider

DEFAULT_UNIVERSE: dict[str, list[str]] = {
    # The paper's names plus other sectors (financials, energy, healthcare) and the index.
    "equity": ["AAPL", "NVDA", "MSFT", "META", "GOOGL", "AMZN", "JPM", "XOM", "JNJ", "SPY"],
    "fx": ["EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDCAD"],
}

PERIODS: dict[str, tuple[str, str]] = {
    "design": ("2016-01-04", "2021-12-31"),
    "holdout": ("2022-01-03", "2026-06-30"),
    "paper": ("2024-01-02", "2024-03-28"),
}

METRIC_COLS = ["CR%", "AR%", "Vol%", "Sharpe", "t(SR)", "MDD%", "Calmar", "Exp%", "Trades", "Stops"]


@dataclass
class EvaluationResult:
    rows: pd.DataFrame  # period, symbol, asset_class, strategy + METRIC_COLS
    meta: dict = field(default_factory=dict)

    def summary(self, period: str | None = None) -> pd.DataFrame:
        df = self.rows if period is None else self.rows[self.rows.period == period]
        g = df.groupby(["period", "strategy"])
        out = pd.DataFrame({
            "n": g.size(),
            "median Sharpe": g["Sharpe"].median(),
            "mean CR%": g["CR%"].mean(),
            "mean MDD%": g["MDD%"].mean(),
            "mean Vol%": g["Vol%"].mean(),
            "mean Exp%": g["Exp%"].mean(),
        })
        return out.round(2)

    def head_to_head(self) -> pd.DataFrame:
        """Per period: on how many instruments the agent's Sharpe beats each baseline."""
        out = []
        for period, df in self.rows.groupby("period"):
            piv = df.pivot_table(index="symbol", columns="strategy", values="Sharpe")
            if AGENT not in piv:
                continue
            for base in piv.columns:
                if base == AGENT:
                    continue
                wins = int((piv[AGENT] > piv[base]).sum())
                out.append({"period": period, "baseline": base, "agent wins": wins,
                            "instruments": int(piv[base].notna().sum()),
                            "median Sharpe diff": round(float((piv[AGENT] - piv[base]).median()), 3)})
        return pd.DataFrame(out)

    def to_json(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps({"meta": self.meta,
                                          "rows": self.rows.to_dict(orient="records")},
                                         indent=1, default=str), encoding="utf-8")

    @classmethod
    def from_json(cls, path: str | Path) -> "EvaluationResult":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(pd.DataFrame(d["rows"]), d.get("meta", {}))


def evaluate(symbols: list[str] | None = None, periods: dict[str, tuple[str, str]] | None = None,
             config: dict | None = None, rebalance_every: int = 5,
             provider: MarketDataProvider | None = None,
             progress: Callable[[str], None] | None = None) -> EvaluationResult:
    """Run the agent and baselines for every (period, symbol). Failures are recorded, not raised."""
    cfg = make_config(config)
    symbols = symbols or DEFAULT_UNIVERSE["equity"] + DEFAULT_UNIVERSE["fx"]
    periods = periods or PERIODS
    provider = provider or get_provider(cfg)
    rows, errors = [], []
    t0 = time.perf_counter()
    for pname, (start, end) in periods.items():
        for sym in symbols:
            try:
                rep = run_agent_backtest(sym, start, end, cfg, rebalance_every, provider)
            except Exception as e:
                errors.append({"period": pname, "symbol": sym, "error": str(e)})
                if progress:
                    progress(f"{pname:<8} {sym:<7} ERROR {e}")
                continue
            t = rep.table()
            for strat, r in t.iterrows():
                rows.append({"period": pname, "symbol": rep.instrument.symbol,
                             "asset_class": rep.instrument.asset_class, "strategy": strat,
                             **{c: float(r[c]) for c in METRIC_COLS}})
            if progress:
                a = t.loc[AGENT] if AGENT in t.index else None
                progress(f"{pname:<8} {sym:<7} " + (
                    f"agent Sharpe {a['Sharpe']:+.2f} vs B&H {t.loc['Buy&Hold', 'Sharpe']:+.2f}"
                    if a is not None else "baselines only"))
    meta = {"periods": periods, "symbols": symbols, "rebalance_every": rebalance_every,
            "data_provider": cfg["data_provider"], "rules": cfg.get("rules"),
            "rebalance_band": cfg["risk"].get("rebalance_band"),
            "use_stops": cfg.get("backtest", {}).get("use_stops"),
            "errors": errors, "seconds": round(time.perf_counter() - t0, 1)}
    return EvaluationResult(pd.DataFrame(rows), meta)
