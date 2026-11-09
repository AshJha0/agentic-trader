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
from .leakage import gate_family_bh, ic_purged_series, passes_gate, scored_mask


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


def rolling_beta_panel(closes: pd.DataFrame, groups: dict[str, str] | None = None,
                       window: int = 252, min_obs: int = 60) -> pd.DataFrame:
    """Point-in-time beta of each name to its group's equal-weight daily return, from the
    trailing ``window`` returns up to and including bar t (no later bar enters)."""
    groups = groups or {c: "all" for c in closes.columns}
    rets = closes.pct_change(fill_method=None)
    out = pd.DataFrame(np.nan, index=closes.index, columns=closes.columns)
    for g in sorted(set(groups.get(c, "all") for c in closes.columns)):
        cols = [c for c in closes.columns if groups.get(c, "all") == g]
        mkt = rets[cols].mean(axis=1)
        var = mkt.rolling(window, min_periods=min_obs).var()
        for c in cols:
            out[c] = rets[c].rolling(window, min_periods=min_obs).cov(mkt) / var
    return out


def beta_neutralise(panel: pd.DataFrame, betas: pd.DataFrame, groups: dict[str, str] | None = None,
                    min_names: int = 3) -> pd.DataFrame:
    """Residual of a per-date cross-sectional OLS of ``panel`` on ``[1, beta]`` within each
    group: the part of the score not explained by market exposure. Rows with fewer than
    ``min_names + 1`` finite pairs in a group are NaN (two parameters are fitted)."""
    groups = groups or {c: "all" for c in panel.columns}
    out = pd.DataFrame(np.nan, index=panel.index, columns=panel.columns)
    b_all = betas.reindex(index=panel.index, columns=panel.columns)
    for g in sorted(set(groups.get(c, "all") for c in panel.columns)):
        cols = [c for c in panel.columns if groups.get(c, "all") == g]
        y, x = panel[cols].to_numpy(float), b_all[cols].to_numpy(float)
        res = np.full_like(y, np.nan)
        for i in range(y.shape[0]):
            ok = np.isfinite(y[i]) & np.isfinite(x[i])
            if ok.sum() < min_names + 1 or np.std(x[i][ok]) == 0:
                continue
            X = np.column_stack([np.ones(int(ok.sum())), x[i][ok]])
            coef, *_ = np.linalg.lstsq(X, y[i][ok], rcond=None)
            res[i, ok] = y[i][ok] - X @ coef
        out[cols] = res
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


def grouped_cross_sectional_ic(signal: pd.DataFrame, fwd: pd.DataFrame, groups: dict[str, str],
                               min_names: int = 5) -> pd.Series:
    """Per-date IC computed *within* each group (asset class) and averaged over the groups
    that have ``min_names`` pairs that day, weighted by their pair count. Ranking equities
    against FX pairs mixes two return scales; this keeps the comparison inside a class, as
    the scores are standardised and as the analyst trades (v0.17 N4)."""
    gs = sorted(set(groups.get(c, "all") for c in signal.columns))
    if len(gs) <= 1:
        return cross_sectional_ic(signal, fwd, min_names)
    common = signal.index.intersection(fwd.index)
    num = pd.Series(0.0, index=common)
    den = pd.Series(0.0, index=common)
    for g in gs:
        cols = [c for c in signal.columns if groups.get(c, "all") == g and c in fwd.columns]
        if not cols:
            continue
        ic = cross_sectional_ic(signal[cols], fwd[cols], min_names)
        w = (signal.loc[common, cols].notna() & fwd.loc[common, cols].notna()).sum(axis=1).astype(float)
        w = w.where(ic.notna(), 0.0)
        num = num + ic.fillna(0.0) * w
        den = den + w
    return (num / den.where(den > 0)).astype(float)


def ic_summary(ic: pd.Series, horizon: int, periods_per_year: float = 252.0) -> dict[str, float]:
    """Summary of a per-date cross-sectional IC series.

    ``mean IC``, ``t(IC)`` and ``days`` come from blocked walk-forward folds
    (``leakage.ic_blocked_folds_series``; nothing is fitted, so nothing is purged): the fold-mean IC, a t-statistic from the dispersion of
    non-overlapping fold ICs, and the dates scored. ``t_NW`` is the Newey-West t on every
    scored date and ``MDE_IC`` the smallest mean IC detectable at 5% / 80% power. ``IC IR`` (annualised for
    non-overlapping horizons) and ``IC>0%`` are measured on the same scored dates, so
    ``days`` counts the sample behind every column.
    """
    pic = ic_purged_series(ic, horizon)
    v = ic[scored_mask(len(ic), horizon)].dropna()
    if v.size < 3 or not math.isfinite(pic.ic):
        return {"mean IC": float("nan"), "IC IR": float("nan"), "t(IC)": float("nan"),
                "t_crit": float("nan"), "t_NW": pic.t_nw, "MDE_IC": pic.mde_ic, "IC>0%": float("nan"),
                "days": pic.n}
    mean, sd = float(v.mean()), float(v.std(ddof=1))
    return {"mean IC": pic.ic, "IC IR": (mean / sd) * math.sqrt(periods_per_year / horizon) if sd > 0 else float("nan"),
            "t(IC)": pic.t, "t_crit": pic.t_crit, "t_NW": pic.t_nw, "MDE_IC": pic.mde_ic, "IC>0%": 100.0 * float((v > 0).mean()), "days": pic.n}


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


def grouped_quantile_spread(signal: pd.DataFrame, fwd: pd.DataFrame, horizon: int, groups: dict[str, str],
                            quantile: float = 0.2, min_names: int = 5) -> pd.Series:
    """``quantile_spread`` within each group, averaged across the groups present on a date."""
    gs = sorted(set(groups.get(c, "all") for c in signal.columns))
    if len(gs) <= 1:
        return quantile_spread(signal, fwd, horizon, quantile, min_names)
    parts = []
    for g in gs:
        cols = [c for c in signal.columns if groups.get(c, "all") == g and c in fwd.columns]
        if cols:
            parts.append(quantile_spread(signal[cols], fwd[cols], horizon, quantile, min_names))
    parts = [x for x in parts if x.size]
    if not parts:
        return pd.Series(dtype=float)
    return pd.concat(parts, axis=1).mean(axis=1)


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
        """Top ``k`` alphas by full-sample mean IC. An in-sample ranking: a diagnostic, not a
        selection a backtest may use; the gated row is always excluded (v0.17 N6)."""
        t = self.table.drop(index=["combined", "significance_gated"], errors="ignore")
        return list(t.sort_values("mean IC", ascending=False).index[:k])


def xalpha_report(frames: dict[str, pd.DataFrame], instruments: dict[str, Instrument], horizon: int = 10,
                  names: list[str] | None = None, carry: dict[str, np.ndarray] | None = None,
                  groups: dict[str, str] | None = None, decay_horizons: tuple[int, ...] = (1, 5, 10, 21, 42),
                  quantile: float = 0.2, min_names: int = 5, weights: dict[str, float] | None = None,
                  standardise: str = "zscore", neutralise: str = "none",
                  family_q: float = 0.05) -> XAlphaReport:
    """Evaluate every alpha cross-sectionally over a universe.

    ``groups`` maps symbol -> group for standardisation (default: asset class).
    ``standardise`` is ``"zscore"`` or ``"rank"``. Since v0.17 the IC and the quantile spread
    are computed within each group and averaged (``grouped_cross_sectional_ic``); the pooled
    mixed-class IC is kept as the labelled extra column ``mean IC (pooled)``.
    ``neutralise="beta"`` removes each raw signal's exposure to point-in-time group beta
    before standardising (``beta_neutralise``); the default ``"none"`` keeps earlier results
    reproducible. ``breadth`` (mean names scored per date), ``min breadth`` and ``names/side``
    are printed on every row. ``family_q`` is the BH level for the gate family (the alphas of
    this report at this horizon, Newey-West p; ``leakage.GATE_FAMILIES``).
    """
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    if standardise not in ("zscore", "rank"):
        raise ValueError("standardise must be 'zscore' or 'rank'")
    if neutralise not in ("none", "beta"):
        raise ValueError("neutralise must be 'none' or 'beta'")
    groups = groups or {s: instruments[s].asset_class for s in frames}
    panels = signal_panels(frames, instruments, names, carry)
    closes = pd.DataFrame({s: df["Close"] for s, df in frames.items()}).sort_index()
    if neutralise == "beta":
        betas = rolling_beta_panel(closes, groups)
        panels = {n: beta_neutralise(p, betas, groups) for n, p in panels.items()}
    fwd = forward_return_panel(closes, horizon)
    std = cs_zscore if standardise == "zscore" else cs_rank
    scores = {n: std(p, groups, min_names=min(min_names, 3)) for n, p in panels.items()}
    combined = _combine_scores(scores, weights)
    scores["combined"] = combined
    ppy = float(np.mean([instruments[s].periods_per_year for s in frames]))
    rows, decay, spreads = {}, {}, {}

    def row_for(n: str, sc: pd.DataFrame) -> dict:
        ic = grouped_cross_sectional_ic(sc, fwd, groups, min_names)
        summary = ic_summary(ic, horizon, ppy)
        pooled = ic_summary(cross_sectional_ic(sc, fwd, min_names), horizon, ppy)["mean IC"]
        sp = grouped_quantile_spread(sc, fwd, horizon, groups, quantile, min_names)
        spreads[n] = sp
        counts = sc.notna().sum(axis=1) if not sc.empty else pd.Series(dtype=float)
        counts = counts[counts > 0]
        breadth = float(counts.mean()) if counts.size else 0.0
        sizes = [sum(1 for c in sc.columns if groups.get(c, "all") == g)
                 for g in set(groups.get(c, "all") for c in sc.columns)]
        per_side = min((max(1, int(round(quantile * k))) for k in sizes if k >= min_names), default=0)
        decay[n] = {h: ic_summary(grouped_cross_sectional_ic(sc, forward_return_panel(closes, h), groups, min_names),
                                  h, ppy)["mean IC"]
                    for h in decay_horizons}
        return {**summary, "mean IC (pooled)": pooled,
                "min breadth": float(counts.min()) if counts.size else 0.0, "names/side": per_side, "spread%/period": 100.0 * float(sp.mean()) if sp.size else float("nan"),
                "spread t": float(sp.mean() / sp.std(ddof=1) * math.sqrt(sp.size))
                if sp.size > 2 and sp.std(ddof=1) > 0 else float("nan"),
                "breadth": breadth}

    for n, sc in scores.items():
        rows[n] = row_for(n, sc)
    # The row nobody was measuring: the significance-gated combination is what XAlphaAnalyst
    # actually trades (agents.analysts.significant_alpha_signal, on this same ic/n shape),
    # not "combined" above, which is an equal-weighted diagnostic over every alpha regardless
    # of measured quality. A full-sample diagnostic, not a walk-forward backtest -- see
    # alpha.significance_gated_series, which this mirrors for cross-sectional scores.
    ic_for_gate = {n: gate_entry(v) for n, v in rows.items() if n != "combined"}
    scores["significance_gated"] = significance_gated_scores(scores, ic_for_gate, family_q=family_q)
    rows["significance_gated"] = row_for("significance_gated", scores["significance_gated"])
    for n in rows:
        # v0.17 N6: the gated row picks alphas on the full-sample IC and is scored on the same
        # sample, so it is an in-sample diagnostic; flagged here and excluded from best().
        rows[n]["in-sample selection"] = 1.0 if n == "significance_gated" else 0.0
    table = pd.DataFrame(rows).T.round(4)
    names_only = [n for n in scores if n not in ("combined", "significance_gated")]
    stacked = pd.DataFrame({n: scores[n].stack(future_stack=True) for n in names_only})
    with np.errstate(invalid="ignore", divide="ignore"):
        corr = stacked.corr().round(3)
    return XAlphaReport(horizon, table, pd.DataFrame(decay).T.round(4), corr, spreads, scores, groups)


def gate_entry(row: dict) -> dict:
    """The gate shape (``leakage.passes_gate`` / ``gate_family_bh``) of one ``xalpha_report``
    row: IC, blocked-fold t with its Student-t bar and df, Newey-West t, days."""
    from .leakage import student_t_crit
    tc = row.get("t_crit", float("nan"))
    df = 0
    if tc is not None and tc == tc:
        # t_crit is the 5% two-sided Student value at k - 1 df; recover k - 1 from it.
        df = next((d for d in range(1, 60) if abs(student_t_crit(d) - float(tc)) < 1e-6), 0)
    return {"IC": row.get("mean IC"), "t(IC)": row.get("t(IC)"), "t_crit": tc,
            "n": row.get("days"), "t_NW": row.get("t_NW"), "MDE_IC": row.get("MDE_IC"), "df": df}


def significance_gated_scores(scores: dict[str, pd.DataFrame], ic: dict[str, dict],
                              min_tstat: float | None = None, min_n: int = 30,
                              family_q: float | None = 0.05) -> pd.DataFrame:
    """The cross-sectional analogue of ``alpha.significance_gated_series``: only the alphas
    whose cross-sectional IC clears ``min_tstat``/``min_n`` in ``ic`` (the same
    ``{"IC", "t(IC)", "n"}`` shape ``agents.analysts.significant_alpha_signal`` reads)
    contribute, IC-magnitude-weighted, exactly like ``XAlphaAnalyst`` actually trades.

    Reuses ``_combine_scores``'s formula (signed weight in the numerator, ``abs(weight)`` in
    the denominator -- already the same convention ``significant_alpha_signal`` uses) by
    setting every non-passing alpha's weight to 0, which contributes nothing to either side.

    One gate (v0.17 N7): an entry is held to its own ``t_crit`` (2.776 at 4 df); with no
    ``t_crit`` the fallback is ``min_tstat`` and, by default (``None``), nothing passes -- the
    old fixed 2.0 bar is gone. With ``family_q`` set, an alpha must also survive
    Benjamini-Hochberg at that level over the family of alphas in ``ic`` on the Newey-West
    p-values (``leakage.gate_family_bh(use="nw")``).
    """
    names = [n for n in scores if n not in ("combined", "significance_gated")]
    weights = {n: 0.0 for n in names}
    fallback = math.inf if min_tstat is None else float(min_tstat)
    fam = {n: ic[n] for n in names if isinstance(ic.get(n), dict)}
    bh_ok = {n: True for n in fam}
    if family_q is not None and fam:
        bh_ok = {n: r["bh"] for n, r in gate_family_bh(fam, family_q, use="nw", min_n=min_n).items()}
    for n in names:
        v = ic.get(n)
        if v is not None and passes_gate(v, min_n, fallback) and bh_ok.get(n, False):
            weights[n] = float(v["IC"])
    return _combine_scores(scores, weights)


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
