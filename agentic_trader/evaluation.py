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
import math
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from .backtest import AGENT, run_agent_backtest
from .config import make_config
from .data import MarketDataProvider, get_provider
from .instruments import Instrument
from .llm import LLM, get_llm, llm_usage
from .provenance import provenance

# The core universe: the 15 instruments every rule choice through v0.4 was made on.
CORE_UNIVERSE: dict[str, list[str]] = {
    # Large-cap technology names plus other sectors (financials, energy, healthcare) and the index.
    "equity": ["AAPL", "NVDA", "MSFT", "META", "GOOGL", "AMZN", "JPM", "XOM", "JNJ", "SPY"],
    "fx": ["EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDCAD"],
}

# The extended universe (v0.5): 45 instruments (26 equities, 9 macro ETFs, 10 FX crosses) that
# no rule choice was made on. They judged the v0.5.1 carry rule and the v0.6 EDGAR and
# cross-sectional decisions and v0.8 re-measured them, so they are no longer unseen. Both lists
# were chosen in 2025 with hindsight (survivors; see the evaluation's limitations).
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


@dataclass(frozen=True)
class Trial:
    """One variant judged on the design period: what it was called, which release judged it,
    the config overrides that reproduce it under the current engine (``None`` when it is not
    reproducible from config alone -- it still counts as a trial) and the design-period mean
    Sharpe recorded at the time (v0.3 engine, for the historical record only)."""
    name: str
    version: str
    overrides: dict | None
    recorded_mean_sharpe: float | None = None
    # v0.11: the design-period portfolio Sharpe the variant was judged on when it is a book or
    # a return-level trial (v0.9 runs and books, v0.10 overlay sizes); the deflated Sharpe is
    # computed on this statistic for every trial (measured for reproducible ones).
    recorded_portfolio_sharpe: float | None = None


_CTRL_RULES = {"tsmom": False, "trend_filtered_reversal": False, "abstain_without_data": False,
               "fx_carry_neutral": False}
_CTRL_RISK = {"rebalance_band": 0.0, "neutral_weight": {"equity": 0.0, "fx": 0.0}}
_SIGNALS = {"tsmom": True, "trend_filtered_reversal": True, "abstain_without_data": True}


def _v03_trial(rules: dict | None = None, risk: dict | None = None, stops: bool = False) -> dict:
    """A v0.3 ablation variant: the v0.2 control plus the named changes (FX carry rule off, as then)."""
    return {"rules": {**_CTRL_RULES, **(rules or {})}, "risk": {**_CTRL_RISK, **(risk or {})},
            "backtest": {"use_stops": stops}}


def _eq(w: float) -> dict:
    return {"neutral_weight": {"equity": w, "fx": 0.0}}


# Every variant ever judged on the design period, in the order it was tried. The deflated
# Sharpe's trial count is the length of this registry (docs/evaluation "Selection statistics"),
# and scripts/measure_v08.py re-measures every reproducible one under the current engine.
TRIALS: tuple[Trial, ...] = (
    Trial("v0.2 (control)", "v0.3", _v03_trial(), 0.50),
    Trial("+ 12-1 month time-series momentum", "v0.3", _v03_trial(rules={"tsmom": True}), 0.47),
    Trial("+ trend-filtered reversal", "v0.3", _v03_trial(rules={"trend_filtered_reversal": True}), 0.48),
    Trial("+ abstain without data", "v0.3", _v03_trial(rules={"abstain_without_data": True}), 0.51),
    Trial("+ no-trade band 0.10", "v0.3", _v03_trial(risk={"rebalance_band": 0.10}), 0.50),
    Trial("+ intraday stops", "v0.3", _v03_trial(stops=True), 0.47),
    Trial("signal changes (momentum + filter + abstain)", "v0.3", _v03_trial(rules=_SIGNALS), 0.51),
    Trial("signal changes + band", "v0.3", _v03_trial(rules=_SIGNALS, risk={"rebalance_band": 0.10}), 0.51),
    Trial("all five", "v0.3", _v03_trial(rules=_SIGNALS, risk={"rebalance_band": 0.10}, stops=True), 0.50),
    Trial("strategic equity weight 0.25", "v0.3", _v03_trial(risk=_eq(0.25)), 0.54),
    Trial("strategic equity weight 0.50", "v0.3", _v03_trial(risk=_eq(0.50)), 0.58),
    Trial("strategic equity weight 1.00", "v0.3", _v03_trial(risk=_eq(1.00)), 0.66),
    Trial("strategic 0.50 + band", "v0.3", _v03_trial(risk={**_eq(0.50), "rebalance_band": 0.10}), 0.58),
    Trial("strategic 0.50 + signal changes + band", "v0.3",
          _v03_trial(rules=_SIGNALS, risk={**_eq(0.50), "rebalance_band": 0.10}), 0.58),
    Trial("strategic 0.50 + abstain + band", "v0.3",
          _v03_trial(rules={"abstain_without_data": True}, risk={**_eq(0.50), "rebalance_band": 0.10}), 0.56),
    Trial("frozen v0.3: strategic 1.00 + band", "v0.3", _v03_trial(risk={**_eq(1.00), "rebalance_band": 0.10}), 0.65),
    Trial("+ alpha analyst (IC-weighted, all signals)", "v0.4", None, 0.60),
    Trial("+ alpha analyst (significance-gated, 400-day window)", "v0.4", None, 0.58),
    Trial("+ alpha analyst (significance-gated, 900-day window)", "v0.5",
          {"analysts": ["technical", "sentiment", "macro", "fundamentals", "news", "alpha"]}, 0.65),
    Trial("FX carry / 4, cap 0.5", "v0.5.1",
          {"rules": {"fx_carry_neutral": True}, "risk": {"fx_carry_neutral_scale": 4.0, "fx_carry_neutral_cap": 0.5}}),
    Trial("FX carry / 2, cap 0.5 (adopted)", "v0.5.1",
          {"rules": {"fx_carry_neutral": True}, "risk": {"fx_carry_neutral_scale": 2.0, "fx_carry_neutral_cap": 0.5}}),
    Trial("FX carry / 4, cap 1.0", "v0.5.1",
          {"rules": {"fx_carry_neutral": True}, "risk": {"fx_carry_neutral_scale": 4.0, "fx_carry_neutral_cap": 1.0}}),
    Trial("FX carry / 8, cap 0.25", "v0.5.1",
          {"rules": {"fx_carry_neutral": True}, "risk": {"fx_carry_neutral_scale": 8.0, "fx_carry_neutral_cap": 0.25}}),
    Trial("+ cross-sectional alpha analyst", "v0.6",
          {"analysts": ["technical", "fundamentals", "news", "sentiment", "xalpha"], "xalpha_universe": UNIVERSES["all"]}),
    Trial("EDGAR filings off", "v0.6", {"edgar": False}),
    Trial("track-record size cut off", "v0.8", {"rules": {"track_record_cut": False}}),
    # v0.9 (docs/evaluation/v09_research.md): five risk-parity runs (the B&H vol-target row is
    # the candidate base) and six return-level books, judged on the design-period portfolio
    # Sharpe against the run's own control; nothing adopted. Not reproducible from config.
    Trial("v0.9 run etf11_rp (multi-asset base)", "v0.9", None, recorded_portfolio_sharpe=1.02),
    Trial("v0.9 run etf11_equal", "v0.9", None, recorded_portfolio_sharpe=1.02),
    Trial("v0.9 run fx15_rp", "v0.9", None, recorded_portfolio_sharpe=0.08),
    Trial("v0.9 run core15_rp", "v0.9", None, recorded_portfolio_sharpe=0.91),
    Trial("v0.9 run all26_rp", "v0.9", None, recorded_portfolio_sharpe=0.71),
    Trial("v0.9 book beta + trend_etf", "v0.9", None, recorded_portfolio_sharpe=0.78),
    Trial("v0.9 book beta + carry", "v0.9", None, recorded_portfolio_sharpe=1.02),
    Trial("v0.9 book beta + trend_etf + carry", "v0.9", None, recorded_portfolio_sharpe=0.88),
    Trial("v0.9 book all four", "v0.9", None, recorded_portfolio_sharpe=0.57),
    Trial("v0.9 book trend + carry (no beta)", "v0.9", None, recorded_portfolio_sharpe=0.11),
    # v0.10 (docs/evaluation/v010_overlay.md): the desk tilt at size lam over the vol-target core.
    Trial("v0.10 overlay lam 0.00", "v0.10", None, recorded_portfolio_sharpe=1.43),
    Trial("v0.10 overlay lam 0.25", "v0.10", None, recorded_portfolio_sharpe=1.44),
    Trial("v0.10 overlay lam 0.50", "v0.10", None, recorded_portfolio_sharpe=1.43),
    Trial("v0.10 overlay lam 0.75", "v0.10", None, recorded_portfolio_sharpe=1.42),
    Trial("v0.10 overlay lam 1.00", "v0.10", None, recorded_portfolio_sharpe=1.40),
    # v0.11 (tier-2 review): the v0.8 sizing and news rules kept as trials against the new defaults,
    # and a symmetric equity tilt (strategic weight below the cap).
    Trial("aggressive stance at the cap (v0.8 rule)", "v0.11", {"risk": {"aggressive_vol_scaled": False}}),
    Trial("news confidence by count (v0.8 rule)", "v0.11", {"rules": {"news_tone_mass": False}}),
    Trial("strategic equity weight 0.8 (symmetric tilt)", "v0.11", {"risk": {"neutral_weight": {"equity": 0.8, "fx": 0.0}}}),
)


def reproducible_trials() -> list[Trial]:
    return [t for t in TRIALS if t.overrides is not None]


def trial_slug(name: str) -> str:
    s = "".join(ch if ch.isalnum() else "_" for ch in name.lower())
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


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
        if "run" in df and df["run"].nunique() > 1:
            # Repeated runs: one value per instrument (its mean over runs), so n counts
            # instruments for every strategy and matches paired().
            df = df.groupby(["period", "strategy", "symbol"], as_index=False)[METRIC_COLS].mean()
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

    def paired(self, baseline: str = "Buy&Hold", metric: str = "Sharpe", period: str | None = None,
               universe: str | None = None, strategy: str = AGENT, n_boot: int = 10_000, seed: int = 0,
               cluster: bool = True):
        """Cross-instrument bootstrap of ``strategy - baseline`` on one metric (see ``stats.paired_bootstrap``).

        With repeated agent runs, each instrument contributes its mean over runs.
        ``cluster`` (default on) hands the (asset class, universe) label of every instrument
        to ``paired_bootstrap`` as its group: the extended universe mixes clusters of
        correlated instruments (nine rate/credit/commodity ETFs that mostly move together,
        next to unrelated equities), and resampling whole clusters is what carries their
        shared shock into the interval. The cluster scheme only engages with at least
        ``stats.MIN_CLUSTER_GROUPS`` distinct labels among the paired instruments (the core
        universe has two, ``--universe all`` five); below that the plain instrument bootstrap
        is used and the result's ``scheme``/``n_groups`` say so. Pass ``cluster=False`` for
        the plain scheme regardless (the v0.6 numbers).
        """
        from .stats import paired_bootstrap
        rows = self.rows
        if period is not None:
            rows = rows[rows.period == period]
        if universe is not None and "universe" in rows:
            rows = rows[rows.universe == universe]
        piv = rows.pivot_table(index="symbol", columns="strategy", values=metric, aggfunc="mean")
        if strategy not in piv or baseline not in piv:
            raise ValueError(f"need both {strategy!r} and {baseline!r} in the rows")
        both = piv[[strategy, baseline]].dropna()
        groups = None
        if cluster and {"asset_class", "universe"} <= set(rows.columns):
            key = rows.drop_duplicates("symbol").set_index("symbol")
            key = (key["asset_class"].astype(str) + ":" + key["universe"].astype(str))
            aligned = key.reindex(both.index)
            if aligned.notna().all():
                groups = aligned.to_numpy()
        return paired_bootstrap(both[strategy].to_numpy(), both[baseline].to_numpy(), n_boot=n_boot, seed=seed,
                                groups=groups)

    def paired_table(self, metric: str = "Sharpe", universe: str | None = None, strategy: str = AGENT,
                     fdr_q: float = 0.05, cluster: bool = True,
                     baselines: tuple[str, ...] | None = None) -> pd.DataFrame:
        """Per period and baseline: mean paired difference, 95% CI and two-sided p across
        instruments, which resampling ``scheme`` produced them over how many ``groups``, plus
        ``significant`` corrected for the number of tested rows in *this table*
        (Benjamini-Hochberg false discovery rate at ``fdr_q``). Printing many paired tests side
        by side is a multiple-comparisons problem exactly like choosing among rule variants;
        the raw per-row ``p`` is still reported, but ``significant`` is the one to read when
        the table has more than a couple of rows. BH runs on the unrounded p-values; a row
        with fewer than three paired instruments was never tested, shows ``p`` as NaN and
        neither counts towards nor can win a share of the false-discovery budget. ``baselines``
        restricts the table to those baselines *before* the correction, so a table that only
        shows the two controls is corrected over the rows it prints (v0.8 printed flags decided
        over all six baselines and then dropped four rows).
        """
        out, p_raw = [], []
        rows = self.rows if universe is None or "universe" not in self.rows else self.rows[self.rows.universe == universe]
        for period in sorted(rows.period.unique()):
            for base in sorted(rows.strategy.unique()):
                if base == strategy or (baselines is not None and base not in baselines):
                    continue
                try:
                    pb = self.paired(base, metric, period=period, universe=universe, strategy=strategy,
                                     cluster=cluster)
                except ValueError:
                    continue
                p = pb.p_value if math.isfinite(pb.ci_low) else float("nan")
                p_raw.append(p)
                out.append({"period": period, "baseline": base, "n": pb.n, f"mean {metric} diff": round(pb.mean_diff, 3),
                            "ci95 low": round(pb.ci_low, 3), "ci95 high": round(pb.ci_high, 3),
                            "p": round(p, 3), "wins": pb.wins, "scheme": pb.scheme, "groups": pb.n_groups})
        df = pd.DataFrame(out)
        if len(df):
            from .stats import benjamini_hochberg
            df["significant"] = benjamini_hochberg(np.asarray(p_raw), fdr_q)
        return df

    def run_dispersion(self, metric: str = "Sharpe", strategy: str = AGENT) -> pd.DataFrame:
        """With repeated runs: per period, the mean over instruments of the across-run std of ``metric``."""
        rows = self.rows[self.rows.strategy == strategy]
        if "run" not in rows or rows.run.nunique() < 2:
            return pd.DataFrame()
        g = rows.groupby(["period", "symbol"])[metric]
        per = pd.DataFrame({"runs": g.size(), "std": g.std(ddof=1), "range": g.max() - g.min()})
        return per.groupby("period").agg(runs=("runs", "max"), instruments=("std", "size"),
                                         mean_std=("std", "mean"), mean_range=("range", "mean")).round(3)

    def slowest(self, n: int = 10) -> pd.DataFrame:
        """The ``n`` slowest (period, symbol, run) jobs, from ``meta["timings"]``.

        A full sweep (``evaluate --universe all --periods design,holdout,q1_2024,reserve``)
        has no other way to tell which symbol or period is the slow one -- an EDGAR
        fiscal-calendar edge case, a data provider hiccup, or an unusually long LLM debate --
        without profiling ad hoc; this is exactly that, read from the run that just happened
        rather than a separate profiling pass.
        """
        timings = self.meta.get("timings")
        if not timings:
            return pd.DataFrame(columns=["period", "symbol", "run", "seconds", "error"])
        return pd.DataFrame(timings).sort_values("seconds", ascending=False).head(n).reset_index(drop=True)

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
             llm: LLM | None = None, workers: int = 1, repeats: int = 1) -> EvaluationResult:
    """Run the agent and baselines for every (period, symbol). Failures are recorded, not raised.

    ``workers > 1`` runs backtests in parallel threads (useful with an LLM, whose
    calls dominate the run time). All runs share one provider, one LLM client and
    one call budget. ``repeats > 1`` runs the agent that many times per (period,
    symbol) -- the baselines once -- and tags every row with ``run``, so the model's
    own variance can be measured (``run_dispersion``); offline the rules are
    deterministic and the repeats are identical.
    """
    cfg = make_config(config)
    symbols = symbols or UNIVERSES["all"]
    periods = periods or {p: PERIODS[p] for p in DEFAULT_PERIODS}
    provider = provider or get_provider(cfg)
    macro_sources = getattr(provider, "macro_sources", None)
    if isinstance(macro_sources, dict):
        macro_sources.clear()   # this run's tally only: the provider may be shared across runs
    llm = llm if llm is not None else get_llm(cfg)
    if workers < 1:
        raise ValueError("workers must be >= 1")
    if repeats < 1:
        raise ValueError("repeats must be >= 1")
    jobs = [(p, s, k) for p in periods for s in symbols for k in range(repeats)]
    t0 = time.perf_counter()

    if workers > 1:
        # Download data up front, one symbol at a time: data libraries are not
        # reliably thread-safe, and later calls then hit the provider's cache. The alpha
        # analysts look further back, and the cross-sectional one asks for its peers too.
        analysts = set(cfg.get("analysts") or [])
        lookback = cfg["lookback_days"]
        if analysts & {"alpha", "xalpha"}:
            lookback = max(lookback, int(cfg.get("alpha_lookback_days", 900)))
        warm: list[tuple[str, str]] = [(p, s) for p, s, _ in jobs]
        if "xalpha" in analysts:
            peers = cfg.get("xalpha_universe") or CORE_UNIVERSE["equity"] + CORE_UNIVERSE["fx"]
            warm += [(p, s) for p in periods for s in peers]
        seen: set[tuple[str, str]] = set()
        for pname, sym in warm:
            if (pname, sym) in seen:
                continue
            seen.add((pname, sym))
            start, end = (date.fromisoformat(x) for x in periods[pname])
            try:
                provider.history(Instrument.parse(sym), start - timedelta(days=lookback), end)
            except Exception:
                pass  # the backtest below records the error

    def run(job):
        pname, sym, k = job
        start, end = periods[pname]
        t0j = time.perf_counter()
        try:
            rep = run_agent_backtest(sym, start, end, cfg, rebalance_every, provider, llm)
        except Exception as e:
            elapsed = time.perf_counter() - t0j
            if progress:
                progress(f"{pname:<8} {sym:<7} ERROR {e} ({elapsed:.1f}s)")
            return job, None, str(e), elapsed
        elapsed = time.perf_counter() - t0j
        if progress:
            t = rep.table()
            a = t.loc[AGENT] if AGENT in t.index else None
            src = rep.agent_sources
            share = f"  [llm {src.get('llm', 0)}/{sum(src.values())}]" if llm is not None and src else ""
            progress(f"{pname:<8} {sym:<7} " + (f"run {k} " if repeats > 1 else "") + (
                f"agent Sharpe {a['Sharpe']:+.2f} vs B&H {t.loc['Buy&Hold', 'Sharpe']:+.2f}{share}"
                if a is not None else "baselines only") + f"  ({elapsed:.1f}s)")
        return job, rep, None, elapsed

    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            outcomes = list(pool.map(run, jobs))
    else:
        outcomes = [run(j) for j in jobs]

    rows, errors, sources, timings = [], [], {"llm": 0, "rules": 0}, []
    baselines_done: set[tuple[str, str]] = set()
    for (pname, sym, k), rep, err, elapsed in outcomes:  # job order: deterministic regardless of workers
        timings.append({"period": pname, "symbol": sym, "run": k, "seconds": round(elapsed, 3),
                        "error": err is not None})
        if err is not None:
            errors.append({"period": pname, "symbol": sym, "run": k, "error": err})
            continue
        for name, v in rep.agent_sources.items():
            sources[name] = sources.get(name, 0) + v
        for strat, r in rep.table(decimals=None).iterrows():   # full precision: aggregates and bootstraps run on these
            if strat != AGENT:   # baselines are deterministic: one row each, from the first run that succeeded
                if (pname, sym) in baselines_done:
                    continue
            rows.append({"period": pname, "symbol": rep.instrument.symbol,
                         "asset_class": rep.instrument.asset_class,
                         "universe": universe_group(rep.instrument.symbol), "strategy": strat,
                         "run": 0 if strat != AGENT else k,
                         **{c: float(r[c]) for c in METRIC_COLS}})
        baselines_done.add((pname, sym))
    from .prompts import prompt_registry
    meta = {"periods": periods, "symbols": symbols, "rebalance_every": rebalance_every, "repeats": repeats,
            "prompts": prompt_registry(cfg),
            "lookback_days": cfg["lookback_days"], "alpha_lookback_days": cfg.get("alpha_lookback_days"),
            "edgar": getattr(provider, "edgar", None) is not None,   # a configured, contactable EDGAR client
            "data_provider": cfg["data_provider"], "llm_provider": cfg["llm_provider"],
            "impact_coeff": cfg["costs"].get("impact_coeff", 0.0), "initial_capital": cfg["initial_capital"],
            "fred_vintages": bool(cfg.get("fred_vintages")),
            "rules": cfg.get("rules"), "rebalance_band": cfg["risk"].get("rebalance_band"),
            "neutral_weight": cfg["risk"].get("neutral_weight"),
            "use_stops": cfg.get("backtest", {}).get("use_stops"),
            "errors": errors, "seconds": round(time.perf_counter() - t0, 1),
            "agent_sources": sources,
            "macro_sources": dict(macro_sources) if isinstance(macro_sources, dict) else {},
            "timings": timings, "provenance": provenance()}
    if llm is not None:
        meta.update(models={"deep": cfg["deep_think_llm"], "quick": cfg["quick_think_llm"]},
                    effort={"deep": cfg["deep_effort"], "quick": cfg["quick_effort"]},
                    debate_rounds=cfg["max_debate_rounds"], anonymized=bool(cfg.get("llm_anonymize")),
                    max_llm_calls=cfg.get("max_llm_calls"), max_llm_cost_usd=cfg.get("max_llm_cost_usd"),
                    usage=llm_usage(llm),
                    budget_refused=getattr(llm, "refused", 0))
    return EvaluationResult(pd.DataFrame(rows), meta)
