"""Leakage rigour: purged walk-forward folds, a future-leak canary and a point-in-time
feature table (PLAN.md item 5.8).

Three separate guards, each against a different way the future reaches a backtest.

1. **Overlapping labels.** A ``horizon``-bar forward return at bar ``i`` is built from bars
   ``i+1 .. i+horizon``. Scored on one long pooled sample, neighbouring labels share almost
   all of their bars, and a statistic fitted on bars just before a test block has seen the
   returns the test block is scored on. ``purged_walk_forward`` splits the bars into
   contiguous test folds, trains each fold only on earlier bars whose label ends before the
   fold starts (the purge) and drops the bars just after every earlier test fold (the
   embargo), after Lopez de Prado, *Advances in Financial Machine Learning* (2018), ch. 7.
   The purge and the embargo only matter when something is *fitted* on the training side
   (IC-weight combination, regime model, conformal calibration). ``ic_blocked_folds`` and
   ``ic_blocked_folds_series`` (old names ``ic_purged`` / ``ic_purged_series``, kept as
   aliases) score a *fixed* signal: no training set is used, so for them this is not purged
   cross-validation but a blocked-fold IC -- contiguous test blocks, a fold-mean IC and a t
   on ``k - 1`` degrees of freedom (2.776 bar at five folds). That test has little power, so
   since v0.17 every result also carries a Newey-West (HAC) t on all scored pairs (lag
   ``max(NW-1994 rule, horizon)``) and the minimum detectable IC at 5% / 80% power; a null
   then reads "cannot detect |IC| below x", not "no edge".

2. **Code that reads past the as-of date.** ``future_leak_canary`` runs the whole offline
   desk twice, once on the data and once on a copy carrying a large shock from date ``T``,
   and requires every output for an as-of date before ``T`` -- analyst reports, debate,
   proposal, risk views, decision, alpha values and every prompt built -- to be
   byte-identical. Any difference is a read of data the desk could not have had.

3. **Features published after the date they describe.** ``PointInTimeStore`` keeps each
   feature value with the date it became public (``visible_from``) and refuses any read
   that would return a value not yet public at the reading date.
"""
from __future__ import annotations

import functools
import json
import math
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import pandas as pd

from . import quant
from .stats import benjamini_hochberg, min_detectable_ic, newey_west_t, rank_ic_newey_west
from .data.base import MarketDataProvider, NewsItem
from .instruments import Instrument

# ------------------------------------------------------------------ purged walk-forward CV


@dataclass(frozen=True)
class Fold:
    """One walk-forward fold over sample positions ``0 .. n-1``.

    ``test`` is a contiguous block. ``train`` holds only positions before the block whose
    label window ends before the block starts, minus the embargo after every earlier test
    block; it is empty for the first fold. ``scored`` is ``test`` without its last
    ``horizon`` positions, whose labels run into the next fold: scoring only ``scored``
    keeps any two folds from sharing a return.
    """
    index: int
    train: np.ndarray
    test: np.ndarray
    scored: np.ndarray


def purged_walk_forward(n_samples: int, horizon: int, n_folds: int = 5,
                        embargo: int | None = None) -> list[Fold]:
    """Purged, embargoed, expanding-window walk-forward folds.

    Sample ``i`` carries a label over bars ``i+1 .. i+horizon``. For test block
    ``[a, b)``: a training sample ``i < a`` is purged when ``i + horizon >= a`` (its label
    overlaps the block), and samples in ``[b_k, b_k + embargo)`` after every earlier block
    ``k`` are embargoed, so serial correlation just past a test block cannot leak back into
    the next fit. ``embargo`` defaults to ``horizon``. Blocks are as equal as integer
    division allows; ``n_folds`` must leave each block longer than ``horizon``.
    """
    if horizon < 1:
        raise ValueError("horizon must be a positive number of bars")
    if n_folds < 2:
        raise ValueError("n_folds must be at least 2")
    emb = horizon if embargo is None else int(embargo)
    if emb < 0:
        raise ValueError("embargo must be non-negative")
    if n_samples < n_folds * (horizon + 1):
        raise ValueError(f"{n_samples} samples cannot hold {n_folds} folds longer than horizon {horizon}")
    edges = np.linspace(0, n_samples, n_folds + 1).astype(int)
    keep = np.ones(n_samples, bool)          # positions not embargoed by an earlier block
    folds = []
    for j in range(n_folds):
        a, b = int(edges[j]), int(edges[j + 1])
        train = np.flatnonzero(keep[: max(0, a - horizon)])
        test = np.arange(a, b)
        folds.append(Fold(j, train, test, test[: max(0, test.size - horizon)]))
        keep[b: b + emb] = False
    return folds


def scored_mask(n_samples: int, horizon: int, n_folds: int = 5, embargo: int | None = None) -> np.ndarray:
    """Boolean mask of the positions ``ic_purged`` scores (the union of every fold's
    ``scored`` block), so a diagnostic reported beside a purged IC can be measured on the
    same sample and the same ``n``. All False when the series is too short for the folds."""
    mask = np.zeros(n_samples, bool)
    try:
        folds = purged_walk_forward(n_samples, horizon, n_folds, embargo)
    except ValueError:
        if horizon < 1:
            raise
        return mask
    for fold in folds:
        mask[fold.scored] = True
    return mask


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the regularised incomplete beta function (modified Lentz),
    after Press et al., *Numerical Recipes* (3rd ed., 2007), section 6.4."""
    tiny, eps = 1e-300, 3e-16
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 400):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def _betainc(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta ``I_x(a, b)`` for ``0 <= x <= 1``."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(lbt) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lbt) * _betacf(b, a, 1.0 - x) / b


def student_t_sf(t: float, df: float) -> float:
    """Upper-tail probability ``P(T > t)`` of Student's t with ``df`` degrees of freedom."""
    if df <= 0:
        raise ValueError("df must be positive")
    tail = 0.5 * _betainc(df / 2.0, 0.5, df / (df + t * t))
    return tail if t >= 0 else 1.0 - tail


@functools.lru_cache(maxsize=256)
def student_t_crit(df: float, alpha: float = 0.05) -> float:
    """Two-sided critical value: the ``t`` with ``P(|T| >= t) = alpha`` at ``df`` degrees of
    freedom (2.776 at 4 df and 5%), by bisection on ``student_t_sf``. scipy is not a
    dependency, so the quantile is computed here."""
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must lie in (0, 1)")
    target = alpha / 2.0
    lo, hi = 0.0, 1.0
    while student_t_sf(hi, df) > target:
        hi *= 2.0
    while hi - lo > 1e-12:
        mid = 0.5 * (lo + hi)
        if student_t_sf(mid, df) > target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


@dataclass(frozen=True)
class PurgedIC:
    """Fold-by-fold rank IC and its summary.

    ``ic`` is the mean of the finite fold ICs; ``t`` is ``mean / (sd / sqrt(k))`` over
    those ``k`` folds (NaN with fewer than three), a t-statistic with ``k - 1`` degrees of
    freedom whose observations do not overlap; ``n`` counts the pairs (or dates) scored.
    With five folds that is 4 degrees of freedom, where the two-sided 5% bar is 2.776, not
    the normal 1.96 or a round 2: ``t_crit`` carries that bar and ``significant`` applies it.
    """
    ic: float
    t: float
    n: int
    folds: tuple[float, ...]
    t_nw: float = float("nan")      # Newey-West HAC t on every scored pair / date (v0.17)
    nw_lag: int = 0                 # Bartlett lag behind t_nw
    mde_ic: float = float("nan")    # min detectable |IC|, 5% two-sided, 80% power (HAC se)
    method: str = "blocked folds, fixed signal (no fit, purge inactive)"

    @property
    def k(self) -> int:
        """Number of finite fold ICs behind ``t``."""
        return sum(1 for x in self.folds if math.isfinite(x))

    @property
    def t_crit(self) -> float:
        """Two-sided 5% Student-t critical value at ``k - 1`` degrees of freedom; NaN when
        ``t`` is undefined (fewer than three finite folds)."""
        return student_t_crit(self.k - 1) if self.k >= 3 else float("nan")

    @property
    def significant(self) -> bool:
        """``|t| >= t_crit``; False whenever either is NaN."""
        return math.isfinite(self.t) and math.isfinite(self.t_crit) and abs(self.t) >= self.t_crit

    def as_gate(self) -> dict[str, float | int]:
        """The ``{"IC", "t(IC)", "n", "t_crit"}`` shape ``alpha.significant_alpha_signal``
        reads."""
        return {"IC": self.ic, "t(IC)": self.t, "n": self.n, "t_crit": self.t_crit,
                "t_NW": self.t_nw, "MDE_IC": self.mde_ic, "df": self.k - 1 if self.k >= 3 else 0}


FoldIC = PurgedIC   # v0.17 name: for a fixed signal nothing is purged


def gate_threshold(entry: dict, fallback: float = 2.0) -> float:
    """The |t(IC)| bar for one gate-table entry: its own ``t_crit`` (the Student-t value for
    its fold count) when it carries one, else ``fallback`` for a hand-built table with no
    fold count. A NaN ``t_crit`` means the statistic is undefined, so nothing passes."""
    tc = entry.get("t_crit")
    if tc is None:
        return fallback
    tc = float(tc)
    return tc if math.isfinite(tc) else math.inf


def passes_gate(entry: Any, min_n: int = 30, fallback_tstat: float = 2.0) -> bool:
    """Whether one ``{"IC", "t(IC)", "n"[, "t_crit"]}`` entry clears the significance gate:
    a finite IC, ``|t(IC)| >= gate_threshold(entry)`` and ``n >= min_n``. Every gate in the
    package (``alpha.significant_alpha_signal``, ``alpha.significance_gated_series``,
    ``xalpha.significance_gated_scores``) goes through this function."""
    if not isinstance(entry, dict):
        return False
    icv, t, n = entry.get("IC"), entry.get("t(IC)"), entry.get("n")
    if icv is None or icv != icv or t is None or t != t:
        return False
    return abs(float(t)) >= gate_threshold(entry, fallback_tstat) and (n or 0) >= min_n


def _summarise(fold_ics: list[float], n: int, nw: Any = None) -> PurgedIC:
    extra: dict[str, Any] = {}
    if nw is not None:
        extra = {"t_nw": nw.t, "nw_lag": nw.lag,
                 "mde_ic": min_detectable_ic(nw.n, se=nw.se) if math.isfinite(nw.se) else float("nan")}
    v = np.array([x for x in fold_ics if math.isfinite(x)])
    if v.size == 0:
        return PurgedIC(float("nan"), float("nan"), n, tuple(fold_ics), **extra)
    mean = float(v.mean())
    t = float("nan")
    if v.size >= 3:
        sd = float(v.std(ddof=1))
        t = mean / (sd / math.sqrt(v.size)) if sd > 0 else float("nan")
    return PurgedIC(mean, t, n, tuple(fold_ics), **extra)


def ic_blocked_folds(signal: Any, fwd_returns: Any, horizon: int, n_folds: int = 5,
                     embargo: int | None = None, min_pairs: int = 10) -> PurgedIC:
    """Spearman IC of one fixed signal series against its ``horizon``-bar forward returns,
    estimated fold by fold on the test blocks of ``purged_walk_forward`` (blocked folds: the
    training side is unused, so this is not purged CV). ``t_nw`` is the HAC t of the rank IC
    on every scored pair (``stats.rank_ic_newey_west``), ``mde_ic`` the IC it could detect.

    Each fold's IC uses only its ``scored`` positions with finite pairs (NaN for a fold with
    fewer than ``min_pairs``). A fixed signal is fitted on nothing, so the training sets are
    not used here; what the split buys is independent folds and a t-statistic that does not
    count overlapping pairs as separate evidence. A series too short for ``n_folds`` folds
    returns NaN with ``n = 0``.
    """
    s, f = np.asarray(signal, float), np.asarray(fwd_returns, float)
    if s.shape != f.shape or s.ndim != 1:
        raise ValueError("signal and fwd_returns must be 1-D and of equal length")
    try:
        folds = purged_walk_forward(s.size, horizon, n_folds, embargo)
    except ValueError:
        if horizon < 1:
            raise
        return PurgedIC(float("nan"), float("nan"), 0, ())
    ics, n = [], 0
    mask = np.zeros(s.size, dtype=bool)
    for fold in folds:
        mask[fold.scored] = True
        x, y = s[fold.scored], f[fold.scored]
        ok = np.isfinite(x) & np.isfinite(y)
        k = int(ok.sum())
        n += k
        v = quant.spearman(x[ok], y[ok]) if k >= min_pairs else float("nan")
        ics.append(float(v) if math.isfinite(v) else float("nan"))
    return _summarise(ics, n, rank_ic_newey_west(s[mask], f[mask], horizon))


def ic_blocked_folds_series(daily_ic: pd.Series, horizon: int, n_folds: int = 5,
                            embargo: int | None = None, min_dates: int = 5) -> PurgedIC:
    """The cross-sectional counterpart of ``ic_blocked_folds`` (``t_nw``: HAC t of the
    scored daily ICs): ``daily_ic`` is a per-date IC
    (``xalpha.cross_sectional_ic``) whose date ``i`` scores the ``horizon``-bar return from
    ``i``; each fold's IC is the mean over its ``scored`` dates (NaN with fewer than
    ``min_dates`` finite values), and ``n`` counts the dates used."""
    v = np.asarray(daily_ic, float)
    try:
        folds = purged_walk_forward(v.size, horizon, n_folds, embargo)
    except ValueError:
        if horizon < 1:
            raise
        return PurgedIC(float("nan"), float("nan"), 0, ())
    ics, n = [], 0
    mask = np.zeros(v.size, dtype=bool)
    for fold in folds:
        mask[fold.scored] = True
        x = v[fold.scored]
        x = x[np.isfinite(x)]
        n += int(x.size)
        ics.append(float(x.mean()) if x.size >= min_dates else float("nan"))
    return _summarise(ics, n, newey_west_t(v[mask], horizon=horizon))


# Pre-v0.17 names, kept so callers and stored reports keep working.
ic_purged = ic_blocked_folds
ic_purged_series = ic_blocked_folds_series


# ------------------------------------------------------------------ gate family (v0.17 R1.3)
# The test families BH runs over, stated once. A family is every test whose verdicts are read
# together to decide one thing; BH uses the Newey-West p (every scored pair, overlap-aware),
# while the per-entry nominal gate stays the blocked-fold t against its own t_crit.
GATE_FAMILIES: dict[str, str] = {
    "time_series": "alphas x names x horizons of one alpha-report run (alpha.alpha_report over "
                   "the universe; 9 alphas x 15 names x 3 horizons = 405 tests on the core set)",
    "cross_sectional": "alphas of one xalpha_report (one universe, one horizon); the gate that "
                       "builds the significance_gated row (xalpha.significance_gated_scores)",
}


def gate_p_value(entry: dict, use: str = "nw") -> float:
    """Two-sided p of one gate entry. ``use="fold"`` reads ``t(IC)`` against Student t on
    ``df`` (k - 1) degrees of freedom; ``use="nw"`` reads ``t_NW`` against the normal. NaN when
    the statistic is missing or undefined (such entries do not count in BH's ``m``)."""
    if use == "fold":
        t, df = entry.get("t(IC)"), entry.get("df")
        if t is None or t != t or not df or df <= 0:
            return float("nan")
        return min(1.0, 2.0 * student_t_sf(abs(float(t)), float(df)))
    if use == "nw":
        t = entry.get("t_NW")
        if t is None or t != t:
            return float("nan")
        return math.erfc(abs(float(t)) / math.sqrt(2.0))
    raise ValueError("use must be 'fold' or 'nw'")


def gate_family_bh(entries: dict[Any, dict], q: float = 0.05, use: str = "nw",
                   min_n: int = 30) -> dict[Any, dict[str, Any]]:
    """Benjamini-Hochberg over a whole gate family.

    ``entries`` maps a key such as ``(alpha, symbol, horizon)`` to an ``as_gate`` dict. Each
    entry is judged alone by ``passes_gate`` (``nominal``); the family's p-values
    (``gate_p_value``) then go through ``stats.benjamini_hochberg`` at ``q`` (``bh``). An entry
    passes the family gate only when both hold. With 9 alphas x 15 names x 3 horizons = 405
    tests, about 20 nominal passes are expected at 5% under a global null; BH is what stops
    one of them being read as a discovery.
    """
    keys = list(entries)
    p = np.array([gate_p_value(entries[k], use) for k in keys], dtype=float)
    bh = benjamini_hochberg(p, q)
    out = {}
    for i, k in enumerate(keys):
        nominal = passes_gate(entries[k], min_n=min_n)
        out[k] = {"p": float(p[i]), "nominal": nominal, "bh": bool(bh[i]),
                  "passes": bool(nominal and bh[i])}
    return out


def format_gate_family(entries: dict[Any, dict], q: float = 0.05, use: str = "nw") -> str:
    """Markdown gate table: IC, blocked-fold t, HAC t, minimum detectable IC, p, nominal and
    family (BH) verdicts, with a footer naming the family size so no row is read alone."""
    res = gate_family_bh(entries, q, use)

    def f(x: Any, d: int = 3) -> str:
        return "n/a" if x is None or x != x else f"{float(x):.{d}f}"
    lines = ["| test | IC | t (blocked folds) | t (Newey-West) | min detectable IC | p | nominal | family (BH) |",
             "|---|---:|---:|---:|---:|---:|---|---|"]
    for k, e in entries.items():
        r = res[k]
        name = " / ".join(map(str, k)) if isinstance(k, tuple) else str(k)
        lines.append(f"| {name} | {f(e.get('IC'), 4)} | {f(e.get('t(IC)'), 2)} | {f(e.get('t_NW'), 2)} | "
                     f"{f(e.get('MDE_IC'), 4)} | {f(r['p'], 4)} | {'yes' if r['nominal'] else 'no'} | "
                     f"{'yes' if r['passes'] else 'no'} |")
    m = sum(1 for r in res.values() if r["p"] == r["p"])
    basis = "blocked-fold" if use == "fold" else "Newey-West"
    lines += ["", f"Family: {len(entries)} tests ({m} with a defined p), BH at q = {q} on the {basis} p; "
                  f"{sum(r['passes'] for r in res.values())} pass."]
    return "\n".join(lines)


# ------------------------------------------------------------------ future-leak canary


class ShockedProvider(MarketDataProvider):
    """A copy of ``base``'s data with a shock from ``shock_date`` on, for one symbol.

    Every OHLC price of ``symbol`` dated on or after ``shock_date`` is multiplied by
    ``factor``, and the news and social feeds gain one item dated ``shock_date`` (seen only
    by a query whose window reaches it). Everything else is delegated untouched, and the
    provider reports ``base``'s name and realness, so an output that differs from the
    unshocked run can only come from data dated on or after ``shock_date``.
    """

    def __init__(self, base: MarketDataProvider, symbol: str, shock_date: date, factor: float = 3.0):
        super().__init__(base.config)
        self.base, self.symbol, self.shock_date, self.factor = base, symbol, shock_date, float(factor)
        self.name, self.real_world = base.name, base.real_world

    def reconfigured(self, config: dict) -> MarketDataProvider:
        return ShockedProvider(self.base.reconfigured(config), self.symbol, self.shock_date, self.factor)

    def _hit(self, instrument: Instrument) -> bool:
        return instrument.symbol == self.symbol

    def history(self, instrument: Instrument, start: date, end: date) -> pd.DataFrame:
        df = self.base.history(instrument, start, end)
        if not self._hit(instrument):
            return df
        df = df.copy()
        after = df.index >= pd.Timestamp(self.shock_date)
        cols = [c for c in ("Open", "High", "Low", "Close") if c in df.columns]
        df.loc[after, cols] = df.loc[after, cols] * self.factor
        return df

    def _with_shock_item(self, items: list[NewsItem], instrument: Instrument, as_of: date,
                         lookback_days: int) -> list[NewsItem]:
        if self._hit(instrument) and as_of - timedelta(days=lookback_days) <= self.shock_date <= as_of:
            return [*items, NewsItem(self.shock_date, f"{instrument.display} shares soar on takeover bid",
                                     source="CanaryWire")]
        return items

    def news(self, instrument: Instrument, as_of: date, lookback_days: int) -> list[NewsItem]:
        return self._with_shock_item(self.base.news(instrument, as_of, lookback_days), instrument, as_of,
                                     lookback_days)

    def social(self, instrument: Instrument, as_of: date, lookback_days: int) -> list[NewsItem]:
        return self._with_shock_item(self.base.social(instrument, as_of, lookback_days), instrument, as_of,
                                     lookback_days)

    def fundamentals(self, instrument: Instrument, as_of: date) -> dict[str, Any]:
        return self.base.fundamentals(instrument, as_of)

    def macro(self, instrument: Instrument, as_of: date) -> dict[str, Any]:
        return self.base.macro(instrument, as_of)

    def carry_series(self, instrument: Instrument, dates: pd.Index) -> np.ndarray:
        return self.base.carry_series(instrument, dates)

    def as_traded_closes(self, instrument: Instrument, dates: pd.DatetimeIndex) -> np.ndarray | None:
        return self.base.as_traded_closes(instrument, dates)

    def risk_free_series(self, dates: pd.Index) -> np.ndarray:
        return self.base.risk_free_series(dates)


class PromptRecorder:
    """An LLM backend that records every (system, prompt) it is sent and answers ``None``,
    so each agent builds its prompt and then falls back to its rules."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, system: str, prompt: str, *, deep: bool) -> str | None:
        self.prompts.append(f"[{'deep' if deep else 'quick'}]\n{system}\n---\n{prompt}")
        return None


def _canonical(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _canonical(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): _canonical(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_canonical(v) for v in obj]
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (date, pd.Timestamp)):
        return obj.isoformat()
    if isinstance(obj, (np.floating, float)):
        return repr(float(obj))           # repr keeps every bit; NaN compares equal as text
    if isinstance(obj, np.integer):
        return int(obj)
    return obj


def _dump(obj: Any) -> bytes:
    return json.dumps(_canonical(obj), sort_keys=True, ensure_ascii=False).encode("utf-8")


def desk_outputs(graph: Any, symbol: str, as_of: date, provider: MarketDataProvider,
                 alpha_lookback_days: int = 900) -> dict[str, bytes]:
    """Serialised outputs of one offline desk run for ``symbol`` at ``as_of``: each analyst
    report, the debate, the proposal, the risk views, the decision, the markdown report, the
    v0.14 IC forecast and regime label when their switches are on, the
    prompts sent (when ``graph.llm`` is a ``PromptRecorder``) and the alpha library's
    values on the same point-in-time history. Memory is not consulted (a fresh in-memory
    store), so two runs differ only through the data."""
    from .alpha import compute_alphas
    from .memory import DecisionMemory
    graph.provider, graph.memory = provider, DecisionMemory(None)
    recorder = graph.llm if isinstance(graph.llm, PromptRecorder) else None
    if recorder is not None:
        recorder.prompts.clear()
    state = graph.prepare(symbol, as_of)
    for name in graph.analyst_names(state.instrument):
        graph.run_analyst(state, name)
    graph.run_debate(state)
    graph.run_trader(state)
    graph.run_risk(state)
    out = {f"report:{k}": _dump(v) for k, v in state.reports.items()}
    out.update({"debate": _dump(state.debate), "proposal": _dump(state.proposal),
                "risk_views": _dump(state.risk_views), "decision": _dump(state.decision),
                "markdown": state.to_markdown().encode("utf-8")})
    if state.forecast is not None:
        out["forecast"] = _dump(state.forecast)
    if state.regime:
        out["regime"] = _dump(state.regime)
    if recorder is not None:
        out["prompts"] = _dump(recorder.prompts)
    ins = state.instrument
    hist = provider.history(ins, as_of - timedelta(days=alpha_lookback_days), as_of)
    hist = hist[hist.index <= pd.Timestamp(as_of)]
    carry = provider.carry_series(ins, hist.index) if ins.is_fx else None
    out["alphas"] = compute_alphas(hist, ins, None, carry).to_csv(float_format="%.17g").encode("utf-8")
    return out


@dataclass
class CanaryResult:
    """What the canary saw. ``leaks`` maps an as-of date before the shock to the output
    keys that differed (the failure); ``reacted`` lists the post-shock dates on which at
    least one output changed, the evidence that the shock reached the desk at all."""
    symbol: str
    shock_date: date
    leaks: dict[date, list[str]] = field(default_factory=dict)
    reacted: list[date] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.leaks


def future_leak_canary(config: dict, provider: MarketDataProvider, symbol: str, shock_date: date,
                       before: list[date], after: list[date], factor: float = 3.0,
                       record_prompts: bool = True) -> CanaryResult:
    """Run the offline desk on ``provider`` and on a ``ShockedProvider`` copy for every date
    in ``before`` (each must precede ``shock_date``) and ``after``, and compare outputs.

    ``config`` is the desk configuration (``TradingGraph`` with no model, so rules decide).
    With ``record_prompts`` the desk runs with a ``PromptRecorder`` backend: every agent
    builds its prompt, the recorder answers ``None`` and the rules decide, so the prompts
    are compared along with the outputs in a single pass.
    """
    from .graph import TradingGraph
    if any(d >= shock_date for d in before):
        raise ValueError("every 'before' date must precede the shock date")
    shocked = ShockedProvider(provider, symbol, shock_date, factor)
    llm = PromptRecorder() if record_prompts else None
    graph = TradingGraph({**config, "llm_provider": "offline"}, provider=provider, llm=llm,
                         on_event=lambda stage, msg: None)
    res = CanaryResult(symbol, shock_date)
    for d in [*before, *after]:
        clean = desk_outputs(graph, symbol, d, provider, int(graph.config.get("alpha_lookback_days", 900)))
        dirty = desk_outputs(graph, symbol, d, shocked, int(graph.config.get("alpha_lookback_days", 900)))
        diff = sorted(k for k in clean.keys() | dirty.keys() if clean.get(k) != dirty.get(k))
        if d < shock_date and diff:
            res.leaks[d] = diff
        elif d >= shock_date and diff:
            res.reacted.append(d)
    return res


# ------------------------------------------------------------------ point-in-time features


class LookaheadError(ValueError):
    """A read asked for a feature value that was not yet public at the reading date."""


@dataclass(frozen=True)
class FeatureRecord:
    """One feature value with its provenance.

    ``as_of`` is the date the value describes (a quarter end, a filing's period);
    ``visible_from`` the first date it could have been known (the filing's acceptance
    date, not the period end); ``source`` names the feed and ``source_accession`` the
    document (an EDGAR accession number), so a revision is a new record, never an edit.
    """
    feature: str
    entity: str
    as_of: date
    visible_from: date
    value: float | str | None
    source: str
    source_accession: str

    def __post_init__(self) -> None:
        if self.visible_from < self.as_of:
            raise ValueError(f"{self.feature}/{self.entity}: visible_from {self.visible_from} precedes "
                             f"the date it describes ({self.as_of})")

    def to_json(self) -> str:
        d = asdict(self)
        d["as_of"], d["visible_from"] = self.as_of.isoformat(), self.visible_from.isoformat()
        return json.dumps(d, sort_keys=True)

    @classmethod
    def from_json(cls, line: str) -> "FeatureRecord":
        d = json.loads(line)
        d["as_of"], d["visible_from"] = date.fromisoformat(d["as_of"]), date.fromisoformat(d["visible_from"])
        return cls(**d)


def check_read(record: FeatureRecord, as_of: date) -> FeatureRecord:
    """Return ``record`` if it was public at ``as_of``; raise ``LookaheadError`` if not."""
    if record.visible_from > as_of:
        raise LookaheadError(f"{record.feature}/{record.entity} ({record.source_accession}) is visible from "
                             f"{record.visible_from}, after the read date {as_of}")
    return record


class PointInTimeStore:
    """Append-only feature table, in memory or backed by a JSONL file.

    Records are never edited or removed; appending a record whose
    ``(feature, entity, as_of, source_accession)`` already exists with a different value is
    refused, so a restatement must arrive under its own accession. Every read goes through
    ``check_read``.
    """

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self._records: list[FeatureRecord] = []
        self._keys: dict[tuple[str, str, date, str], FeatureRecord] = {}
        if self.path and self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self._add(FeatureRecord.from_json(line))

    def _add(self, rec: FeatureRecord) -> bool:
        key = (rec.feature, rec.entity, rec.as_of, rec.source_accession)
        old = self._keys.get(key)
        if old is not None:
            if old != rec:
                raise ValueError(f"{key} already recorded with a different value; append a new accession")
            return False
        self._keys[key] = rec
        self._records.append(rec)
        return True

    def append(self, rec: FeatureRecord) -> None:
        """Add ``rec``; an exact duplicate is a no-op, a conflicting one raises."""
        if self._add(rec) and self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(rec.to_json() + "\n")

    def __len__(self) -> int:
        return len(self._records)

    def __iter__(self) -> Iterator[FeatureRecord]:
        return iter(self._records)

    def read(self, rec: FeatureRecord, as_of: date) -> FeatureRecord:
        """Read one known record at ``as_of``; raises ``LookaheadError`` if not yet public."""
        return check_read(rec, as_of)

    def latest(self, feature: str, entity: str, as_of: date) -> FeatureRecord | None:
        """The value of ``feature`` for ``entity`` a reader at ``as_of`` would have had: among
        records public by ``as_of``, the one describing the latest date, and of those the
        most recently published (a restatement supersedes the original once public)."""
        known = [r for r in self._records
                 if r.feature == feature and r.entity == entity and r.visible_from <= as_of]
        if not known:
            return None
        return check_read(max(known, key=lambda r: (r.as_of, r.visible_from)), as_of)
