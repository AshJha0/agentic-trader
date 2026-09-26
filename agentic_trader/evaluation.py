"""Multi-instrument, multi-period evaluation with a design / holdout split.

Protocol (docs/evaluation/evaluation.md):

* ``design`` period: the only data used to choose rule changes and defaults.
* ``holdout`` period: run once with frozen rules; never used for choices.
* ``q1_2024`` period: a short reference window inside the holdout.

For every (period, instrument) the agent and all baselines run on the same bars,
costs and carry. ``summary()`` aggregates per strategy: median Sharpe, mean
return, mean drawdown, mean exposure, and how often the agent beats plain and
volatility-targeted buy & hold on Sharpe.

With an LLM, one client and one call budget are shared by every backtest, runs
can go in parallel (``workers``), and ``meta`` records the token usage, the real
cost, and how many agent outputs came from the model rather than the rules.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import pandas as pd

from .backtest import AGENT, run_agent_backtest
from .config import make_config
from .data import MarketDataProvider, get_provider
from .instruments import Instrument
from .llm import LLM, get_llm, llm_usage

# The core universe: the 15 instruments every rule choice through v0.4 was made on.
CORE_UNIVERSE: dict[str, list[str]] = {
    # Large-cap technology names plus other sectors (financials, energy, healthcare) and the index.
    "equity": ["AAPL", "NVDA", "MSFT", "META", "GOOGL", "AMZN", "JPM", "XOM", "JNJ", "SPY"],
    "fx": ["EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDCAD"],
}

# The extended universe (v0.5): 42 instruments that no rule choice has ever consulted, so
# they are an out-of-sample test set across *every* period, including the design period.
# Equities span sectors and styles; the "macro ETF" group adds rates, credit, commodities
# and real estate exposure through exchange-traded funds (priced and traded as equities);
# the FX pairs are crosses and dollar pairs whose both legs have FRED policy-rate series.
EXTENDED_UNIVERSE: dict[str, list[str]] = {
    "equity": ["UNH", "V", "MA", "PG", "HD", "COST", "WMT", "KO", "PEP", "CVX", "LLY", "ABBV", "MRK",
               "BAC", "GS", "CAT", "BA", "BRK-B", "QQQ", "IWM", "XLF", "XLE", "XLV", "XLU", "EEM", "EFA"],
    "macro_etf": ["TLT", "IEF", "LQD", "HYG", "GLD", "SLV", "USO", "DBC", "VNQ"],
    "fx": ["NZDUSD", "USDCHF", "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "EURCHF", "AUDNZD", "CADJPY",
           "EURAUD"],
}

# Backwards-compatible view: asset class -> every symbol (macro ETFs are equities to the desk).
DEFAULT_UNIVERSE: dict[str, list[str]] = {
    "equity": CORE_UNIVERSE["equity"] + EXTENDED_UNIVERSE["equity"] + EXTENDED_UNIVERSE["macro_etf"],
    "fx": CORE_UNIVERSE["fx"] + EXTENDED_UNIVERSE["fx"],
}

UNIVERSES: dict[str, list[str]] = {
    "core": CORE_UNIVERSE["equity"] + CORE_UNIVERSE["fx"],
    "extended": EXTENDED_UNIVERSE["equity"] + EXTENDED_UNIVERSE["macro_etf"] + EXTENDED_UNIVERSE["fx"],
}
UNIVERSES["all"] = UNIVERSES["core"] + UNIVERSES["extended"]


def universe_group(symbol: str) -> str:
    """``core`` / ``extended`` / ``extended-macro`` membership of a symbol (``other`` if not listed)."""
    s = symbol.upper().replace("/", "").replace("=X", "")
    if s in UNIVERSES["core"]:
        return "core"
    if s in EXTENDED_UNIVERSE["macro_etf"]:
        return "extended-macro"
    if s in UNIVERSES["extended"]:
        return "extended"
    return "other"


PERIODS: dict[str, tuple[str, str]] = {
    "design": ("2016-01-04", "2021-12-31"),
    "holdout": ("2022-01-03", "2026-06-30"),
    "q1_2024": ("2024-01-02", "2024-03-28"),
    # Untouched by every choice and every published number through v0.5. It grows with
    # time; together with the extended universe it is the fresh holdout for the next rule change.
    "reserve": ("2026-07-01", "2026-09-25"),
}
# The periods a plain `evaluate()` runs; `reserve` is opt-in because three months is a weak test.
DEFAULT_PERIODS: tuple[str, ...] = ("design", "holdout", "q1_2024")

METRIC_COLS = ["CR%", "AR%", "Vol%", "Sharpe", "t(SR)", "MDD%", "Calmar", "Exp%", "Trades", "Stops",
               "Impact%"]


@dataclass
class EvaluationResult:
    rows: pd.DataFrame  # period, symbol, asset_class, strategy + METRIC_COLS
    meta: dict = field(default_factory=dict)

    def summary(self, period: str | None = None, universe: str | None = None) -> pd.DataFrame:
        """Per (period, strategy): n, median Sharpe and mean CR / MDD / Vol / exposure.

        ``universe`` restricts to ``core``, ``extended`` or ``extended-macro`` symbols.
        """
        df = self.rows if period is None else self.rows[self.rows.period == period]
        if universe is not None and "universe" in df:
            df = df[df.universe == universe]
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

    def head_to_head(self, universe: str | None = None) -> pd.DataFrame:
        """Per period: on how many instruments the agent's Sharpe beats each baseline."""
        out = []
        rows = self.rows
        if universe is not None and "universe" in rows:
            rows = rows[rows.universe == universe]
        for period, df in rows.groupby("period"):
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
             progress: Callable[[str], None] | None = None,
             llm: LLM | None = None, workers: int = 1) -> EvaluationResult:
    """Run the agent and baselines for every (period, symbol). Failures are recorded, not raised.

    ``workers > 1`` runs backtests in parallel threads (useful with an LLM, whose
    calls dominate the run time). All runs share one provider, one LLM client and
    one call budget.
    """
    cfg = make_config(config)
    symbols = symbols or UNIVERSES["all"]
    periods = periods or {p: PERIODS[p] for p in DEFAULT_PERIODS}
    provider = provider or get_provider(cfg)
    llm = llm if llm is not None else get_llm(cfg)
    if workers < 1:
        raise ValueError("workers must be >= 1")
    jobs = [(p, s) for p in periods for s in symbols]
    t0 = time.perf_counter()

    if workers > 1:
        # Download data up front, one symbol at a time: data libraries are not
        # reliably thread-safe, and later calls then hit the provider's cache.
        for pname, sym in jobs:
            start, end = (date.fromisoformat(x) for x in periods[pname])
            try:
                provider.history(Instrument.parse(sym), start - timedelta(days=cfg["lookback_days"]), end)
            except Exception:
                pass  # the backtest below records the error

    def run(job):
        pname, sym = job
        start, end = periods[pname]
        try:
            rep = run_agent_backtest(sym, start, end, cfg, rebalance_every, provider, llm)
        except Exception as e:
            if progress:
                progress(f"{pname:<8} {sym:<7} ERROR {e}")
            return job, None, str(e)
        if progress:
            t = rep.table()
            a = t.loc[AGENT] if AGENT in t.index else None
            src = rep.agent_sources
            share = f"  [llm {src.get('llm', 0)}/{sum(src.values())}]" if llm is not None and src else ""
            progress(f"{pname:<8} {sym:<7} " + (
                f"agent Sharpe {a['Sharpe']:+.2f} vs B&H {t.loc['Buy&Hold', 'Sharpe']:+.2f}{share}"
                if a is not None else "baselines only"))
        return job, rep, None

    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            outcomes = list(pool.map(run, jobs))
    else:
        outcomes = [run(j) for j in jobs]

    rows, errors, sources = [], [], {"llm": 0, "rules": 0}
    for (pname, sym), rep, err in outcomes:  # job order: deterministic regardless of workers
        if err is not None:
            errors.append({"period": pname, "symbol": sym, "error": err})
            continue
        for k, v in rep.agent_sources.items():
            sources[k] = sources.get(k, 0) + v
        for strat, r in rep.table().iterrows():
            rows.append({"period": pname, "symbol": rep.instrument.symbol,
                         "asset_class": rep.instrument.asset_class,
                         "universe": universe_group(rep.instrument.symbol), "strategy": strat,
                         **{c: float(r[c]) for c in METRIC_COLS}})
    meta = {"periods": periods, "symbols": symbols, "rebalance_every": rebalance_every,
            "data_provider": cfg["data_provider"], "llm_provider": cfg["llm_provider"],
            "impact_coeff": cfg["costs"].get("impact_coeff", 0.0), "initial_capital": cfg["initial_capital"],
            "fred_vintages": bool(cfg.get("fred_vintages")),
            "rules": cfg.get("rules"), "rebalance_band": cfg["risk"].get("rebalance_band"),
            "neutral_weight": cfg["risk"].get("neutral_weight"),
            "use_stops": cfg.get("backtest", {}).get("use_stops"),
            "errors": errors, "seconds": round(time.perf_counter() - t0, 1),
            "agent_sources": sources}
    if llm is not None:
        meta.update(models={"deep": cfg["deep_think_llm"], "quick": cfg["quick_think_llm"]},
                    effort={"deep": cfg["deep_effort"], "quick": cfg["quick_effort"]},
                    debate_rounds=cfg["max_debate_rounds"], anonymized=bool(cfg.get("llm_anonymize")),
                    max_llm_calls=cfg.get("max_llm_calls"), max_llm_cost_usd=cfg.get("max_llm_cost_usd"),
                    usage=llm_usage(llm),
                    budget_refused=getattr(llm, "refused", 0))
    return EvaluationResult(pd.DataFrame(rows), meta)
