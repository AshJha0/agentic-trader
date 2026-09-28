"""Alpha library and alpha evaluation.

An alpha is a scale-free signal in [-1, 1] computed from data available at each
bar's close. The library covers the classic time-series signals for a single
instrument; ``alpha_report`` measures each one the way a research desk would:

* **IC**: Spearman correlation between the signal and the forward return over
  the horizon, with an overlap-aware t-statistic (consecutive h-bar forward
  returns share h-1 bars, so only n/h of the daily pairs are independent);
* **decay**: IC across horizons;
* **hit rate** next to the **base rate** (share of up-moves), and the
  **tercile spread** on rank-assigned, disjoint terciles: does the sign predict
  beyond the drift, and by how much;
* **autocorrelation**: how fast the signal changes (turnover);
* **correlations** between alphas, and a **combined** alpha.

All signals are computed with the C++ core (or its numpy twin) and are
point-in-time by construction: every value at bar t uses bars <= t only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from . import quant
from .instruments import Instrument

Signal = Callable[["AlphaInputs"], np.ndarray]


@dataclass
class AlphaInputs:
    close: np.ndarray
    high: np.ndarray
    low: np.ndarray
    volume: np.ndarray
    periods_per_year: float
    carry: np.ndarray | None = None  # annual carry per bar (FX)

    @classmethod
    def from_frame(cls, df: pd.DataFrame, instrument: Instrument, carry: np.ndarray | None = None) -> "AlphaInputs":
        return cls(df["Close"].to_numpy(float), df["High"].to_numpy(float), df["Low"].to_numpy(float),
                   df["Volume"].to_numpy(float) if "Volume" in df else np.zeros(len(df)),
                   instrument.periods_per_year, carry)


def _tanh(x: np.ndarray) -> np.ndarray:
    with np.errstate(invalid="ignore"):
        return np.tanh(x)


def _ret(c: np.ndarray, n: int, skip: int = 0) -> np.ndarray:
    out = np.full(len(c), np.nan)
    if len(c) > n:
        out[n:] = c[n - skip: len(c) - skip] / c[: len(c) - n] - 1.0 if skip else c[n:] / c[:-n] - 1.0
    return out


# ------------------------------------------------------------- signals
def tsmom_12_1(x: AlphaInputs) -> np.ndarray:
    """12-month return skipping the last month, scaled by 1-year volatility."""
    r = _ret(x.close, 252, skip=21)
    vol = quant.realized_vol(x.close, 252, x.periods_per_year)
    return _tanh(r / np.where(vol > 0, vol, np.nan))


def mom_20_vol(x: AlphaInputs) -> np.ndarray:
    """20-day return in units of its own volatility."""
    r = _ret(x.close, 20)
    vol = quant.realized_vol(x.close, 20, x.periods_per_year) * math.sqrt(20 / x.periods_per_year)
    return _tanh(r / np.where(vol > 0, vol, np.nan))


def reversal_5(x: AlphaInputs) -> np.ndarray:
    """Short-term reversal: fade the last week's move."""
    r = _ret(x.close, 5)
    vol = quant.realized_vol(x.close, 20, x.periods_per_year) * math.sqrt(5 / x.periods_per_year)
    return -_tanh(r / np.where(vol > 0, vol, np.nan))


def high_52w(x: AlphaInputs) -> np.ndarray:
    """Proximity to the 52-week high: +1 at the high, -1 when 20% or more below."""
    hi = quant.rolling_max(x.close, 252)
    drawdown = 1.0 - x.close / hi
    return np.clip(1.0 - drawdown / 0.10, -1.0, 1.0)


def donchian_20(x: AlphaInputs) -> np.ndarray:
    """Position inside the 20-day high/low channel, -1 (at the low) to +1 (at the high)."""
    hi, lo = quant.rolling_max(x.high, 20), quant.rolling_min(x.low, 20)
    width = hi - lo
    with np.errstate(invalid="ignore", divide="ignore"):
        pos = np.where(width > 0, (x.close - lo) / width, 0.5)
    pos[np.isnan(hi)] = np.nan
    return 2.0 * pos - 1.0


def macd_norm(x: AlphaInputs) -> np.ndarray:
    """MACD histogram in ATR units."""
    _, _, hist = quant.macd(x.close)
    atr = quant.atr(x.high, x.low, x.close, 14)
    return _tanh(hist / np.where(atr > 0, atr, np.nan))


def rsi_contrarian(x: AlphaInputs) -> np.ndarray:
    """Oversold is bullish: (50 - RSI) / 50."""
    return (50.0 - quant.rsi(x.close, 14)) / 50.0


def low_vol(x: AlphaInputs) -> np.ndarray:
    """Calm markets are bullish: negative z-score of 20-day vol against its last six months."""
    vol = quant.realized_vol(x.close, 20, x.periods_per_year)
    z = quant.zscore(np.where(np.isnan(vol), np.nan, vol), 126)
    return -_tanh(z)


def carry(x: AlphaInputs) -> np.ndarray:
    """FX carry: the rate differential, 3% p.a. maps to about +0.76."""
    if x.carry is None:
        return np.full(len(x.close), np.nan)
    return _tanh(np.asarray(x.carry, float) / 0.03)


ALPHAS: dict[str, Signal] = {
    "tsmom_12_1": tsmom_12_1, "mom_20_vol": mom_20_vol, "reversal_5": reversal_5,
    "high_52w": high_52w, "donchian_20": donchian_20, "macd_norm": macd_norm,
    "rsi_contrarian": rsi_contrarian, "low_vol": low_vol, "carry": carry,
}
EQUITY_ALPHAS = ["tsmom_12_1", "mom_20_vol", "reversal_5", "high_52w", "donchian_20",
                 "macd_norm", "rsi_contrarian", "low_vol"]
FX_ALPHAS = EQUITY_ALPHAS + ["carry"]


def compute_alphas(df: pd.DataFrame, instrument: Instrument, names: list[str] | None = None,
                   carry_series: np.ndarray | None = None) -> pd.DataFrame:
    """One column per alpha, aligned with ``df.index``; values in [-1, 1] or NaN."""
    names = names or (FX_ALPHAS if instrument.is_fx else EQUITY_ALPHAS)
    unknown = [n for n in names if n not in ALPHAS]
    if unknown:
        raise ValueError(f"unknown alphas {unknown}; choose from {sorted(ALPHAS)}")
    x = AlphaInputs.from_frame(df, instrument, carry_series)
    out = {n: np.clip(ALPHAS[n](x), -1.0, 1.0) for n in names}
    return pd.DataFrame(out, index=df.index)


def combine(signals: pd.DataFrame, weights: dict[str, float] | None = None) -> pd.Series:
    """Weighted mean of the available alphas at each bar (NaNs ignored)."""
    w = pd.Series({c: (weights or {}).get(c, 1.0) for c in signals.columns}, dtype=float)
    valid = signals.notna()
    num = (signals.fillna(0.0) * w).sum(axis=1)
    den = (valid * w).sum(axis=1)
    return (num / den.where(den > 0)).clip(-1.0, 1.0)


# ------------------------------------------------------------ evaluation
def forward_returns(close, horizon: int) -> np.ndarray:
    c = np.asarray(close, float)
    out = np.full(len(c), np.nan)
    if horizon > 0 and len(c) > horizon:
        out[:-horizon] = c[horizon:] / c[:-horizon] - 1.0
    return out


IC_T_METHODS = ("n_eff", "newey_west")


def _newey_west_t(s: np.ndarray, f: np.ndarray, lag: int) -> float:
    """HAC t-statistic of the Spearman IC: the slope of standardised rank(f) on standardised
    rank(s) (which equals the IC) with a Bartlett-kernel variance over ``lag`` lags of the
    time-ordered score series."""
    x = pd.Series(s).rank().to_numpy(float)
    y = pd.Series(f).rank().to_numpy(float)
    sx, sy = x.std(), y.std()
    if sx <= 0 or sy <= 0:
        return float("nan")
    x, y = (x - x.mean()) / sx, (y - y.mean()) / sy
    n = x.size
    beta = float(x @ y) / n
    u = x * (y - beta * x)
    var = float(u @ u) / n
    for k in range(1, min(lag, n - 1) + 1):
        var += 2.0 * (1.0 - k / (lag + 1)) * float(u[k:] @ u[:-k]) / n
    return beta / math.sqrt(var / n) if var > 0 else float("nan")


def information_coefficient(signal, fwd, horizon: int = 1, method: str = "n_eff") -> tuple[float, float, int]:
    """Spearman IC, its t-statistic and the number of (signal, forward-return) pairs used.

    ``fwd`` is assumed to be the ``horizon``-bar forward return sampled every bar, so
    consecutive pairs overlap and only about ``n / horizon`` of them are independent. The
    t-statistic corrects for that in one of two ways:

    * ``"n_eff"`` (default): ``IC * sqrt(n / horizon)`` -- the same effective-sample rule
      ``xalpha.ic_summary`` applies, so the time-series and cross-sectional analysts' gates
      are the same test;
    * ``"newey_west"``: a Bartlett/Newey-West HAC t-statistic with ``horizon - 1`` lags on the
      rank-transformed pairs. Its window covers the return overlap only: on the library's
      slow signals (autocorrelation ~0.99) it leaves a null SD of ~1.2-1.7, so it is offered
      for comparison, not as the gate.

    ``n`` is the raw pair count either way (the gate's ``min_n`` floor reads it as such). The
    ``n / horizon`` rule over-corrects a short-memory signal such as ``reversal_5`` (its
    measured null SD is ~0.7 at horizon 10), which errs on the conservative side of the gate.
    """
    if horizon < 1:
        raise ValueError("horizon must be a positive number of bars")
    if method not in IC_T_METHODS:
        raise ValueError(f"unknown IC t-stat method {method!r}; choose from {IC_T_METHODS}")
    s, f = np.asarray(signal, float), np.asarray(fwd, float)
    ok = np.isfinite(s) & np.isfinite(f)
    n = int(ok.sum())
    if n < 3:
        return float("nan"), float("nan"), n
    ic = quant.spearman(s[ok], f[ok])
    if not math.isfinite(ic):
        return float("nan"), float("nan"), n
    if method == "newey_west":
        return ic, _newey_west_t(s[ok], f[ok], int(horizon) - 1), n
    return ic, ic * math.sqrt(max(1.0, n / horizon)), n


@dataclass
class AlphaReport:
    instrument: Instrument
    horizon: int
    table: pd.DataFrame            # one row per alpha, plus "combined" and "significance_gated"
    decay: pd.DataFrame            # IC by horizon, one row per alpha
    correlations: pd.DataFrame     # alpha x alpha correlation of signals
    signals: pd.DataFrame = field(repr=False)

    def best(self, k: int = 3) -> list[str]:
        t = self.table.drop(index=["combined", "significance_gated"], errors="ignore")
        return list(t.sort_values("IC", ascending=False).index[:k])


def significance_gated_series(sig: pd.DataFrame, ic: dict[str, dict], min_tstat: float = 2.0,
                              min_n: int = 30) -> pd.Series:
    """The full time series of what ``significant_alpha_signal`` would return at every bar,
    given a *fixed* (full-sample) significance gate: IC-magnitude-weighted mean of the alphas
    whose measured IC clears ``min_tstat``/``min_n`` in ``ic``, using the same "skip a missing
    value from both the numerator and denominator" rule as that function -- reproduced here as
    a vectorised series rather than the single-bar computation ``significant_alpha_signal``
    does live, so a report can show what the analyst's *actual* combination rule would have
    looked like over history, not just the equal-weighted ``combine()`` diagnostic.

    This is a full-sample diagnostic, not a walk-forward backtest: the gate is decided once
    from the whole sample's IC, the same way every other column in ``alpha_report`` measures
    IC from the whole sample. The walk-forward version -- the gate re-decided at each date from
    only prior data -- is what ``AlphaAnalyst``/``XAlphaAnalyst`` actually do live, and what
    ``run_agent_backtest``/``evaluate`` measure; this series is for reading how the *rule*, not
    the point-in-time procedure, would have behaved.
    """
    weights = {name: v["IC"] for name, v in (ic or {}).items()
              if name not in ("combined", "significance_gated") and isinstance(v, dict)
              and v.get("IC") is not None and v["IC"] == v["IC"]
              and abs(v.get("t(IC)") or 0.0) >= min_tstat and (v.get("n") or 0) >= min_n}
    if not weights:
        return pd.Series(np.nan, index=sig.index)
    cols = [c for c in weights if c in sig.columns]
    w = pd.Series({c: weights[c] for c in cols}, dtype=float)
    valid = sig[cols].notna()
    num = (sig[cols].fillna(0.0) * w).sum(axis=1)
    den = (valid * w.abs()).sum(axis=1)
    return (num / den.where(den > 0)).clip(-1.0, 1.0)


def tercile_spread(s: np.ndarray, fwd: np.ndarray) -> float:
    """Mean forward return of the top signal tercile minus the bottom one, with terciles
    assigned by rank so the two groups are disjoint and each holds n/3 bars whatever the
    signal's tie structure. Bars tied at a tercile boundary share the boundary's remaining
    mass equally (fractional weights), so a signal that sits at exactly -1 on most bars
    still has a proper top group and the result does not depend on bar order."""
    s, f = np.asarray(s, float), np.asarray(fwd, float)
    ok = np.isfinite(s) & np.isfinite(f)
    s, f = s[ok], f[ok]
    n = s.size
    k = n // 3
    if k < 1:
        return float("nan")
    srt = np.sort(s)
    lo_val, hi_val = srt[k - 1], srt[n - k]

    def group_mean(inside: np.ndarray, boundary: np.ndarray) -> float:
        w = inside.astype(float)
        need = k - w.sum()
        tied = boundary.sum()
        if need > 0 and tied > 0:
            w[boundary] = need / tied
        return float((w * f).sum() / w.sum())

    bot = group_mean(s < lo_val, s == lo_val)
    top = group_mean(s > hi_val, s == hi_val)
    return top - bot


def _alpha_diagnostics(s: np.ndarray, fwd: np.ndarray, horizon: int = 1) -> dict[str, float]:
    """IC (with the overlap-aware t-statistic for ``horizon``), hit rate and the base rate to
    read it against, tercile spread, autocorrelation and coverage of one signal series against
    forward returns -- the row every column of ``alpha_report``'s table gets, factored out so
    ``significance_gated`` gets exactly the same measurement as every individual alpha and
    ``combined``, not a different one. ``up%`` is the share of positive forward returns on the
    same pairs: a signal stuck at +1 through a rally scores ``hit% == up%`` with zero skill."""
    ic, t, n = information_coefficient(s, fwd, horizon)
    ok = np.isfinite(s) & np.isfinite(fwd)
    hit = float(np.mean(np.sign(s[ok]) == np.sign(fwd[ok]))) if n else float("nan")
    up = float(np.mean(fwd[ok] > 0)) if n else float("nan")
    spread = tercile_spread(s, fwd) if n >= 30 else float("nan")
    valid = s[np.isfinite(s)]
    ac = float("nan")
    if valid.size > 10 and valid[:-1].std() > 0 and valid[1:].std() > 0:
        ac = float(np.corrcoef(valid[:-1], valid[1:])[0, 1])
    return {"IC": ic, "t(IC)": t, "n": n, "hit%": 100 * hit, "up%": 100 * up,
            "tercile spread%": 100 * spread, "autocorr": ac, "coverage%": 100 * np.isfinite(s).mean()}


def alpha_report(df: pd.DataFrame, instrument: Instrument, horizon: int = 10,
                 names: list[str] | None = None, carry_series: np.ndarray | None = None,
                 decay_horizons: tuple[int, ...] = (1, 5, 10, 21, 42),
                 weights: dict[str, float] | None = None) -> AlphaReport:
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    sig = compute_alphas(df, instrument, names, carry_series)
    sig["combined"] = combine(sig, weights)
    close = df["Close"].to_numpy(float)
    fwd = forward_returns(close, horizon)
    rows, decay = {}, {}
    for name in sig.columns:
        s = sig[name].to_numpy()
        rows[name] = _alpha_diagnostics(s, fwd, horizon)
        decay[name] = {h: information_coefficient(s, forward_returns(close, h), h)[0] for h in decay_horizons}
    # The row nobody was measuring: the significance-gated combination is what the alpha
    # analysts actually trade (agents.analysts.significant_alpha_signal), not "combined"
    # above, which is an equal-weighted diagnostic over every alpha regardless of quality.
    sig["significance_gated"] = significance_gated_series(sig.drop(columns=["combined"]), rows)
    s = sig["significance_gated"].to_numpy()
    rows["significance_gated"] = _alpha_diagnostics(s, fwd, horizon)
    decay["significance_gated"] = {h: information_coefficient(s, forward_returns(close, h), h)[0] for h in decay_horizons}
    table = pd.DataFrame(rows).T.round(4)
    with np.errstate(invalid="ignore", divide="ignore"):  # a constant or empty column has no correlation
        corr = sig.drop(columns=["combined", "significance_gated"]).corr().round(3)
    return AlphaReport(instrument, horizon, table, pd.DataFrame(decay).T.round(4), corr, sig)


def alpha_snapshot(df: pd.DataFrame, instrument: Instrument, carry_series: np.ndarray | None = None,
                   weights: dict[str, float] | None = None) -> dict[str, float | None]:
    """Latest value of every alpha plus the combined signal (for the alpha analyst)."""
    sig = compute_alphas(df, instrument, None, carry_series)
    last = sig.iloc[-1]
    out = {k: (None if pd.isna(v) else float(v)) for k, v in last.items()}
    comb = combine(sig, weights).iloc[-1]
    out["combined"] = None if pd.isna(comb) else float(comb)
    return out


def significant_alpha_signal(latest: dict[str, float | None], ic: dict[str, dict],
                             min_tstat: float = 2.0, min_n: int = 30
                             ) -> tuple[float | None, list[str]]:
    """Recombine an alpha snapshot using only alphas whose measured IC is significant.

    ``latest`` is a name -> value snapshot (as returned by ``alpha_snapshot``); ``ic`` is a
    name -> {"IC", "t(IC)", "n"} table (as returned by ``alpha_report`` or computed inline),
    whose ``t(IC)`` must be the overlap-aware statistic ``information_coefficient`` returns for
    the forward horizon actually used -- the ``min_tstat`` bar is calibrated as a per-alpha
    two-sided test at roughly the 5% level, and the raw ``IC * sqrt(n)`` on overlapping
    10-bar returns is ~2.5-3x too large under the null.
    Both ``AlphaAnalyst`` and the ``quant.alpha`` tool produce this shape, so this one
    function is the single source of truth for what "the alpha analyst's view" means: it is
    used whether the analyst computes its own snapshot or reuses one already fetched as a
    harness tool call, so the two paths cannot silently disagree on the significance gate.

    Returns ``(None, [])`` when no alpha clears the significance bar. Otherwise returns the
    IC-magnitude-weighted mean of the significant alphas' latest values, clipped to
    [-1, 1], and their names ordered by |IC| descending.
    """
    weights: dict[str, float] = {}
    for name, v in (ic or {}).items():
        if name in ("combined", "significance_gated") or not isinstance(v, dict):
            continue
        icv, t, n = v.get("IC"), v.get("t(IC)"), v.get("n")
        if icv is not None and icv == icv and abs(t or 0.0) >= min_tstat and (n or 0) >= min_n:
            weights[name] = float(icv)
    if not weights:
        return None, []
    num = den = 0.0
    for name, w in weights.items():
        val = (latest or {}).get(name)
        if val is None:
            continue
        num += w * val
        den += abs(w)
    if den <= 0:
        return None, []
    names = sorted(weights, key=lambda k: -abs(weights[k]))
    return max(-1.0, min(1.0, num / den)), names
