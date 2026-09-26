"""Cross-sectional alphas: rank the universe every day.

The time-series alpha library (``alpha.py``) asks "is *this* instrument likely to
go up?" and is evaluated per instrument. A cross-sectional alpha asks "which
instruments in the universe are likely to do *better than the others* today?".
The same raw signals are used, but every day each one is standardised across the
names in a group (equities with equities, FX with FX), so the signal is a
relative ranking, and it is evaluated the way a cross-sectional desk does:

* **per-date IC**: Spearman correlation across names between today's signal and
  the forward return (Fama-MacBeth style), summarised as the mean IC, its
  information ratio (mean / std, annualised), a t-statistic and the share of
  days with a positive IC;
* **quantile spread**: the return of an equal-weight long top-quantile /
  short bottom-quantile portfolio rebalanced every ``horizon`` bars;
* **breadth**: how many names had a signal on the average day.

Everything is point in time: a cross-sectional value at date t uses only bars
<= t of every instrument, and the forward return that scores it starts at t.
"""
from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import quant
from .alpha import ALPHAS, EQUITY_ALPHAS, FX_ALPHAS, compute_alphas
from .instruments import Instrument


# ------------------------------------------------------------- panels
def signal_panels(frames: dict[str, pd.DataFrame], instruments: dict[str, Instrument],
                  names: list[str] | None = None,
                  carry: dict[str, np.ndarray] | None = None) -> dict[str, pd.DataFrame]:
    """Time-series alpha values as panels: alpha name -> (dates x symbols) frame.

    ``frames`` maps symbol -> OHLCV history; ``carry`` maps FX symbol -> annual
    carry per bar (optional). Alphas an instrument cannot compute (carry for an
    equity) are NaN for that column.
    """
    if not frames:
        raise ValueError("signal_panels needs at least one instrument")
    per_symbol = {}
    for sym, df in frames.items():
        ins = instruments[sym]
        use = names or (FX_ALPHAS if ins.is_fx else EQUITY_ALPHAS)
        use = [n for n in use if n in ALPHAS and (n != "carry" or ins.is_fx)]
        per_symbol[sym] = compute_alphas(df, ins, use, None if carry is None else carry.get(sym))
    all_names = names or sorted({c for sig in per_symbol.values() for c in sig.columns})
    dates = sorted(set().union(*(sig.index for sig in per_symbol.values())))
    out = {}
    for n in all_names:
        cols = {sym: sig[n] for sym, sig in per_symbol.items() if n in sig.columns}
        out[n] = pd.DataFrame(cols).reindex(dates) if cols else pd.DataFrame(index=dates)
    return out


def forward_return_panel(closes: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Return from t to t+horizon per symbol (NaN where t+horizon is unavailable)."""
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    return closes.shift(-horizon) / closes - 1.0


def cs_zscore(panel: pd.DataFrame, groups: dict[str, str] | None = None, min_names: int = 3,
              clip: float = 3.0) -> pd.DataFrame:
    """Standardise each row across names (within ``groups`` when given).

    Rows with fewer than ``min_names`` finite values in a group get NaN for that
    group. Scores are clipped to +-``clip`` and scaled to [-1, 1].
    """
    if panel.empty:
        return panel.copy()
    groups = groups or {c: "all" for c in panel.columns}
    out = pd.DataFrame(np.nan, index=panel.index, columns=panel.columns)
    for g in sorted(set(groups.get(c, "all") for c in panel.columns)):
        cols = [c for c in panel.columns if groups.get(c, "all") == g]
        block = panel[cols].to_numpy(float)
        ok = np.isfinite(block)
        count = ok.sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)   # empty / single-name rows are NaN by design
            mean = np.nanmean(np.where(ok, block, np.nan), axis=1)
            std = np.nanstd(np.where(ok, block, np.nan), axis=1, ddof=1)
            z = (block - mean[:, None]) / std[:, None]
        z[(count < min_names)[:, None].repeat(len(cols), axis=1)] = np.nan
        z[~np.isfinite(z)] = np.nan
        out[cols] = np.clip(z, -clip, clip) / clip
    return out


def cs_rank(panel: pd.DataFrame, groups: dict[str, str] | None = None, min_names: int = 3) -> pd.DataFrame:
    """Rank each row across names (within groups), mapped uniformly to [-1, 1]."""
    if panel.empty:
        return panel.copy()
    groups = groups or {c: "all" for c in panel.columns}
    out = pd.DataFrame(np.nan, index=panel.index, columns=panel.columns)
    for g in sorted(set(groups.get(c, "all") for c in panel.columns)):
        cols = [c for c in panel.columns if groups.get(c, "all") == g]
        block = panel[cols]
        n = block.notna().sum(axis=1).to_numpy(float)
        r = block.rank(axis=1).to_numpy(float)
        with np.errstate(invalid="ignore", divide="ignore"):
            scaled = 2.0 * (r - 1.0) / np.where(n > 1, n - 1.0, np.nan)[:, None] - 1.0
        scaled[n < min_names] = np.nan
        out[cols] = scaled
    return out


# ------------------------------------------------------------ evaluation
def cross_sectional_ic(signal: pd.DataFrame, fwd: pd.DataFrame, min_names: int = 5) -> pd.Series:
    """Per-date Spearman IC across names (NaN on days with too few pairs)."""
    common = signal.index.intersection(fwd.index)
    cols = [c for c in signal.columns if c in fwd.columns]
    s, f = signal.loc[common, cols].to_numpy(float), fwd.loc[common, cols].to_numpy(float)
    out = np.full(len(common), np.nan)
    for i in range(len(common)):
        ok = np.isfinite(s[i]) & np.isfinite(f[i])
        if ok.sum() >= min_names:
            v = quant.spearman(s[i][ok], f[i][ok])
            out[i] = v if math.isfinite(v) else np.nan
    return pd.Series(out, index=common)


def ic_summary(ic: pd.Series, horizon: int, periods_per_year: float = 252.0) -> dict[str, float]:
    """Mean IC, its information ratio (annualised for non-overlapping horizons), t-stat, hit rate."""
    v = ic.dropna()
    n = int(v.size)
    if n < 3:
        return {"mean IC": float("nan"), "IC IR": float("nan"), "t(IC)": float("nan"),
                "IC>0%": float("nan"), "days": n}
    mean, sd = float(v.mean()), float(v.std(ddof=1))
    # Consecutive daily ICs of an h-day forward return overlap; only every h-th is independent.
    n_indep = max(1.0, n / horizon)
    return {"mean IC": mean, "IC IR": (mean / sd) * math.sqrt(periods_per_year / horizon) if sd > 0 else float("nan"),
            "t(IC)": (mean / sd) * math.sqrt(n_indep) if sd > 0 else float("nan"),
            "IC>0%": 100.0 * float((v > 0).mean()), "days": n}


def quantile_spread(signal: pd.DataFrame, fwd: pd.DataFrame, horizon: int, quantile: float = 0.2,
                    min_names: int = 5) -> pd.Series:
    """Equal-weight long top-quantile / short bottom-quantile return per rebalance date.

    Rebalances every ``horizon`` bars so consecutive holding periods do not overlap;
    each value is the spread return over the following ``horizon`` bars.
    """
    if not 0 < quantile <= 0.5:
        raise ValueError("quantile must be in (0, 0.5]")
    common = signal.index.intersection(fwd.index)
    cols = [c for c in signal.columns if c in fwd.columns]
    out = {}
    for d in common[::horizon]:
        s, f = signal.loc[d, cols].to_numpy(float), fwd.loc[d, cols].to_numpy(float)
        ok = np.isfinite(s) & np.isfinite(f)
        if ok.sum() < min_names:
            continue
        s, f = s[ok], f[ok]
        k = max(1, int(round(quantile * s.size)))
        order = np.argsort(s)
        out[d] = float(f[order[-k:]].mean() - f[order[:k]].mean())
    return pd.Series(out, dtype=float)


@dataclass
class XAlphaReport:
    horizon: int
    table: pd.DataFrame                 # one row per alpha (and "combined")
    decay: pd.DataFrame                 # mean IC by horizon
    correlations: pd.DataFrame          # alpha x alpha correlation of cross-sectional scores
    spreads: dict[str, pd.Series]       # top-minus-bottom quantile returns per alpha
    signals: dict[str, pd.DataFrame] = field(repr=False)   # cross-sectional scores
    groups: dict[str, str] = field(default_factory=dict)

    def best(self, k: int = 3) -> list[str]:
        t = self.table.drop(index="combined", errors="ignore")
        return list(t.sort_values("mean IC", ascending=False).index[:k])


def xalpha_report(frames: dict[str, pd.DataFrame], instruments: dict[str, Instrument], horizon: int = 10,
                  names: list[str] | None = None, carry: dict[str, np.ndarray] | None = None,
                  groups: dict[str, str] | None = None, decay_horizons: tuple[int, ...] = (1, 5, 10, 21, 42),
                  quantile: float = 0.2, min_names: int = 5, weights: dict[str, float] | None = None,
                  standardise: str = "zscore") -> XAlphaReport:
    """Evaluate every alpha cross-sectionally over a universe.

    ``groups`` maps symbol -> group for standardisation (default: asset class).
    ``standardise`` is ``"zscore"`` or ``"rank"``.
    """
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    if standardise not in ("zscore", "rank"):
        raise ValueError("standardise must be 'zscore' or 'rank'")
    groups = groups or {s: instruments[s].asset_class for s in frames}
    panels = signal_panels(frames, instruments, names, carry)
    closes = pd.DataFrame({s: df["Close"] for s, df in frames.items()}).sort_index()
    fwd = forward_return_panel(closes, horizon)
    std = cs_zscore if standardise == "zscore" else cs_rank
    scores = {n: std(p, groups, min_names=min(min_names, 3)) for n, p in panels.items()}
    combined = _combine_scores(scores, weights)
    scores["combined"] = combined
    ppy = float(np.mean([instruments[s].periods_per_year for s in frames]))
    rows, decay, spreads = {}, {}, {}
    for n, sc in scores.items():
        ic = cross_sectional_ic(sc, fwd, min_names)
        summary = ic_summary(ic, horizon, ppy)
        sp = quantile_spread(sc, fwd, horizon, quantile, min_names)
        spreads[n] = sp
        breadth = float(sc.notna().sum(axis=1).mean()) if not sc.empty else 0.0
        rows[n] = {**summary, "spread%/period": 100.0 * float(sp.mean()) if sp.size else float("nan"),
                   "spread t": float(sp.mean() / sp.std(ddof=1) * math.sqrt(sp.size))
                   if sp.size > 2 and sp.std(ddof=1) > 0 else float("nan"),
                   "breadth": breadth}
        decay[n] = {h: ic_summary(cross_sectional_ic(sc, forward_return_panel(closes, h), min_names), h, ppy)["mean IC"]
                    for h in decay_horizons}
    table = pd.DataFrame(rows).T.round(4)
    names_only = [n for n in scores if n != "combined"]
    stacked = pd.DataFrame({n: scores[n].stack(future_stack=True) for n in names_only})
    with np.errstate(invalid="ignore", divide="ignore"):
        corr = stacked.corr().round(3)
    return XAlphaReport(horizon, table, pd.DataFrame(decay).T.round(4), corr, spreads, scores, groups)


def _combine_scores(scores: dict[str, pd.DataFrame], weights: dict[str, float] | None) -> pd.DataFrame:
    """Weighted mean of the available scores per (date, symbol), NaN where none exists.

    Panels can have different column sets (``carry`` exists for FX only): each is
    reindexed onto the union first, because adding frames with different columns
    would turn every column missing from any one of them into NaN.
    """
    names = [n for n in scores if n != "combined"]
    if not names:
        return pd.DataFrame()
    cols = sorted(set().union(*(set(scores[n].columns) for n in names)))
    idx = scores[names[0]].index
    for n in names[1:]:
        idx = idx.union(scores[n].index)
    w = {n: float((weights or {}).get(n, 1.0)) for n in names}
    full = {n: scores[n].reindex(index=idx, columns=cols) for n in names}
    num = sum(full[n].fillna(0.0) * w[n] for n in names)
    den = sum(full[n].notna().astype(float) * abs(w[n]) for n in names)
    return (num / den.where(den > 0)).clip(-1.0, 1.0)


def xalpha_snapshot(frames: dict[str, pd.DataFrame], instruments: dict[str, Instrument],
                    names: list[str] | None = None, carry: dict[str, np.ndarray] | None = None,
                    groups: dict[str, str] | None = None, weights: dict[str, float] | None = None
                    ) -> dict[str, dict[str, float | None]]:
    """Latest cross-sectional score of every alpha (and the combined score) per symbol."""
    groups = groups or {s: instruments[s].asset_class for s in frames}
    panels = signal_panels(frames, instruments, names, carry)
    scores = {n: cs_zscore(p, groups, min_names=3) for n, p in panels.items()}
    scores["combined"] = _combine_scores(scores, weights)
    out: dict[str, dict[str, float | None]] = {s: {} for s in frames}
    for n, sc in scores.items():
        if sc.empty:
            continue
        last = sc.iloc[-1]
        for s in frames:
            v = last.get(s)
            out[s][n] = None if v is None or pd.isna(v) else float(v)
    return out
