"""Alpha library and alpha evaluation.

An alpha is a scale-free signal in [-1, 1] computed from data available at each
bar's close. The library covers the classic time-series signals for a single
instrument; ``alpha_report`` measures each one the way a research desk would:

* **IC**: Spearman correlation between the signal and the forward return over
  the horizon, with its t-statistic;
* **decay**: IC across horizons;
* **hit rate** and **tercile spread**: does the sign predict, and by how much;
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


def information_coefficient(signal, fwd) -> tuple[float, float, int]:
    """Spearman IC, its t-statistic and the number of pairs used."""
    s, f = np.asarray(signal, float), np.asarray(fwd, float)
    ok = np.isfinite(s) & np.isfinite(f)
    n = int(ok.sum())
    if n < 3:
        return float("nan"), float("nan"), n
    ic = quant.spearman(s[ok], f[ok])
    if not math.isfinite(ic):
        return float("nan"), float("nan"), n
    return ic, ic * math.sqrt(n), n


@dataclass
class AlphaReport:
    instrument: Instrument
    horizon: int
    table: pd.DataFrame            # one row per alpha (and "combined")
    decay: pd.DataFrame            # IC by horizon, one row per alpha
    correlations: pd.DataFrame     # alpha x alpha correlation of signals
    signals: pd.DataFrame = field(repr=False)

    def best(self, k: int = 3) -> list[str]:
        t = self.table.drop(index="combined", errors="ignore")
        return list(t.sort_values("IC", ascending=False).index[:k])


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
        ic, t, n = information_coefficient(s, fwd)
        ok = np.isfinite(s) & np.isfinite(fwd)
        hit = float(np.mean(np.sign(s[ok]) == np.sign(fwd[ok]))) if n else float("nan")
        spread = float("nan")
        if n >= 30:
            lo, hi = np.quantile(s[ok], [1 / 3, 2 / 3])
            top, bot = fwd[ok][s[ok] >= hi], fwd[ok][s[ok] <= lo]
            if top.size and bot.size:
                spread = float(top.mean() - bot.mean())
        valid = s[np.isfinite(s)]
        ac = float("nan")
        if valid.size > 10 and valid[:-1].std() > 0 and valid[1:].std() > 0:
            ac = float(np.corrcoef(valid[:-1], valid[1:])[0, 1])
        rows[name] = {"IC": ic, "t(IC)": t, "n": n, "hit%": 100 * hit, "tercile spread%": 100 * spread,
                      "autocorr": ac, "coverage%": 100 * np.isfinite(s).mean()}
        decay[name] = {h: information_coefficient(s, forward_returns(close, h))[0] for h in decay_horizons}
    table = pd.DataFrame(rows).T.round(4)
    with np.errstate(invalid="ignore", divide="ignore"):  # a constant or empty column has no correlation
        corr = sig.drop(columns="combined").corr().round(3)
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
