"""IC-weighted signal combination with shrinkage, a turnover penalty and a shrunk
mean-variance step (PLAN.md item 5.1), and split-conformal intervals on the combined
forecast (item 5.3).

The rules desk combines its evidence with hand-set numbers: the facilitator's analyst role
weights, the technical analyst's 0.30 / 0.20 / 0.15 / 0.15 component weights, the trader's
2x tilt on the consensus score and the portfolio manager's 25 / 50 / 25 blend of the risk
stances. None of them was estimated. This module replaces all four with one estimated
pipeline, switched on by ``config["combination"]["method"] = "ic"`` (default ``"rules"``):

1. **Signals.** Every alpha in the library (``alpha.compute_alphas``) plus the two technical
   trend components the library does not already hold (price against the 50-day average,
   50-day against 200-day), each turned into a trailing z-score clipped at +-3.
2. **IC per signal, trailing only.** The rank IC of each signal against its ``horizon``-bar
   forward return, estimated with ``leakage.ic_purged`` on the last ``window`` bars whose
   forward return has fully happened by the as-of bar. Nothing at or after the as-of bar
   enters an estimate.
3. **Shrinkage toward zero.** Each IC is multiplied by the positive-part James-Stein factor
   ``max(0, 1 - (t_crit / t)^2)``, where ``t`` is the purged fold t-statistic and ``t_crit``
   the two-sided 5% Student-t bar for its fold count. A signal whose t does not clear the
   bar gets exactly zero weight; one far past it keeps nearly all of its IC. On noise the
   combined tilt is therefore zero most of the time, which is the pre-registered expectation.
4. **Expected return** ``mu = sigma_h * sum_i IC_i * z_i`` (Grinold's "alpha = IC x vol x
   score", summed over signals; this treats the signals as uncorrelated and so overstates
   ``mu`` when several correlated signals survive the shrinkage).
5. **Shrunk mean-variance.** The tilt is ``mu / (risk_aversion * sigma_h^2)`` for one name,
   or ``Sigma^-1 mu / risk_aversion`` with a Ledoit-Wolf shrunk covariance for a book
   (``ledoit_wolf``, ``mean_variance``).
6. **Turnover penalty.** The target solves ``max_w mu w - (gamma/2) sigma^2 w^2 -
   kappa |w - w_prev|`` exactly: the position moves to the mean-variance weight less a
   no-trade margin ``kappa / (gamma sigma^2)``, and stays put inside it.

Only ``window`` is a registered research parameter (``evaluation.TRIALS``); ``horizon``,
``risk_aversion`` and ``turnover_penalty`` are fixed in ``config.DEFAULT_CONFIG`` before any
trial was run and are not tuned.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .alpha import compute_alphas, forward_returns
from .instruments import Instrument
from .leakage import PurgedIC, ic_purged

# ------------------------------------------------------------------ signals


def signal_panel(df: pd.DataFrame, instrument: Instrument, carry: np.ndarray | None = None) -> pd.DataFrame:
    """The signals the IC combination weighs, one column per signal, aligned with ``df``.

    The alpha library's columns plus ``sma50_side`` (sign of close against its 50-day mean)
    and ``sma_cross`` (sign of the 50-day mean against the 200-day mean), the technical
    analyst's two trend components that the library does not already carry; its MACD,
    20-day momentum and RSI components are the library's ``macd_norm``, ``mom_20_vol`` and
    ``rsi_contrarian``. Every value at bar ``i`` uses bars ``<= i`` only.
    """
    out = compute_alphas(df, instrument, None, carry)
    close = df["Close"].astype(float)
    sma50, sma200 = close.rolling(50).mean(), close.rolling(200).mean()
    out["sma50_side"] = np.sign(close - sma50).where(sma50.notna())
    out["sma_cross"] = np.sign(sma50 - sma200).where(sma200.notna())
    return out


def james_stein_factor(pic: PurgedIC) -> float:
    """Positive-part James-Stein shrinkage ``max(0, 1 - (t_crit / t)^2)`` for one IC; zero
    when the statistic is undefined or does not clear its Student-t bar."""
    if not pic.significant:
        return 0.0
    return max(0.0, 1.0 - (pic.t_crit / pic.t) ** 2)


def trailing_ics(signals: pd.DataFrame, close: np.ndarray, horizon: int, window: int,
                 end: int | None = None, rows: np.ndarray | None = None) -> dict[str, tuple[float, PurgedIC]]:
    """Shrunk IC per signal, estimated on the ``window`` bars before position ``end``.

    ``end`` is the as-of position (default: the last bar). Only bars ``i`` with
    ``i + horizon <= end`` are used, so every forward return in the estimate is known at
    ``end``. ``rows`` optionally restricts the estimate further (a boolean mask over all
    positions, e.g. the bars in the current regime); positions outside it are set to NaN
    before the purged IC, so the fold layout does not change. Returns ``name -> (shrunk IC,
    PurgedIC)``.
    """
    n = len(close)
    end = n - 1 if end is None else int(end)
    last = end - horizon                    # last sample whose label ends at or before ``end``
    lo = max(0, last - window + 1)
    fwd = forward_returns(close, horizon)
    out: dict[str, tuple[float, PurgedIC]] = {}
    if last < lo:
        return out
    y = fwd[lo:last + 1].copy()
    if rows is not None:
        y[~np.asarray(rows, bool)[lo:last + 1]] = np.nan
    for name in signals.columns:
        x = signals[name].to_numpy(float)[lo:last + 1]
        pic = ic_purged(x, y, horizon)
        ic = pic.ic * james_stein_factor(pic) if math.isfinite(pic.ic) else 0.0
        out[name] = (float(ic), pic)
    return out


def standardised(signals: pd.DataFrame, window: int, cap: float = 3.0) -> pd.DataFrame:
    """Trailing z-score of each signal: ``(s - mean) / sd`` over the ``window`` bars up to and
    including ``i``, clipped to ``[-cap, cap]`` so a signal that is nearly constant (a sign
    stuck at +1) cannot produce an unbounded score the day it flips."""
    roll = signals.rolling(window, min_periods=max(20, window // 4))
    sd = roll.std()
    return ((signals - roll.mean()) / sd.where(sd > 0)).clip(-cap, cap)


# ------------------------------------------------------------------ portfolio step


def ledoit_wolf(returns: np.ndarray) -> tuple[np.ndarray, float]:
    """Ledoit-Wolf (2004) shrinkage of the sample covariance toward a scaled identity.

    ``returns`` is ``T x N`` with no NaN. Returns ``(Sigma, delta)`` where ``Sigma =
    delta * mu I + (1 - delta) S``, ``mu = trace(S) / N`` and ``delta`` is the
    estimated optimal intensity in ``[0, 1]`` (Ledoit and Wolf, "A well-conditioned
    estimator for large-dimensional covariance matrices", J. Multivariate Anal. 88, 2004).
    """
    x = np.asarray(returns, float)
    if x.ndim != 2 or x.shape[0] < 2:
        raise ValueError("returns must be T x N with T >= 2")
    if not np.isfinite(x).all():
        raise ValueError("returns must not contain NaN")
    t, n = x.shape
    x = x - x.mean(axis=0)
    s = x.T @ x / t
    mu = float(np.trace(s)) / n
    d2 = float(((s - mu * np.eye(n)) ** 2).sum()) / n
    b2 = sum(float(((np.outer(r, r) - s) ** 2).sum()) for r in x) / (n * t * t)
    b2 = min(b2, d2)
    delta = b2 / d2 if d2 > 0 else 1.0
    return delta * mu * np.eye(n) + (1.0 - delta) * s, delta


def mean_variance(mu: np.ndarray, cov: np.ndarray, risk_aversion: float) -> np.ndarray:
    """Unconstrained mean-variance weights ``cov^-1 mu / risk_aversion``."""
    if risk_aversion <= 0:
        raise ValueError("risk_aversion must be positive")
    return np.linalg.solve(np.asarray(cov, float), np.asarray(mu, float)) / risk_aversion


def turnover_penalised(w_target: float, w_prev: float, variance: float, risk_aversion: float,
                       kappa: float) -> float:
    """Exact maximiser of ``mu w - (g/2) v w^2 - kappa |w - w_prev|`` given the unpenalised
    optimum ``w_target = mu / (g v)``: move to ``w_target`` less the margin
    ``kappa / (g v)``, or stay at ``w_prev`` when the target lies inside the margin."""
    if kappa <= 0 or variance <= 0:
        return w_target
    margin = kappa / (risk_aversion * variance)
    if abs(w_target - w_prev) <= margin:
        return w_prev
    return w_target - math.copysign(margin, w_target - w_prev)


# ------------------------------------------------------------------ the desk forecast


@dataclass
class Forecast:
    """The combined forecast for one name at one as-of bar.

    ``mu`` is the expected ``horizon``-bar return, ``sigma`` the ``horizon``-bar volatility
    it is scaled by, ``tilt`` the mean-variance position before the turnover penalty and the
    firm limits, ``weights`` the shrunk IC per signal (zero for every signal that did not
    clear its bar) and ``interval`` the split-conformal half-width when conformal sizing is on
    (``inf`` when the calibration set was too small, which sizes the tilt to zero).
    """
    mu: float
    sigma: float
    tilt: float
    weights: dict[str, float] = field(default_factory=dict)
    t_stats: dict[str, float] = field(default_factory=dict)
    interval: float | None = None
    regime: int | None = None
    neutral: float = 0.0        # the strategic weight the tilt sits on (set by the trader)

    @property
    def active(self) -> list[str]:
        return [k for k, v in self.weights.items() if v != 0.0]

    def size_scale(self) -> float:
        """Interval-width sizing: ``min(1, |mu| / half-width)``. A forecast whose interval
        straddles zero by a wide margin is scaled toward nothing; one that excludes zero
        keeps its full size. 1.0 when no interval was computed."""
        if self.interval is None or self.interval <= 0:
            return 1.0
        return min(1.0, abs(self.mu) / self.interval)

    def facts(self) -> dict[str, Any]:
        return {"ic_forecast_mu": self.mu, "ic_forecast_sigma": self.sigma, "ic_tilt": self.tilt,
                "ic_active_signals": self.active, "ic_interval": self.interval}


def _mu_series(z: pd.DataFrame, weights: dict[str, float], sigma: np.ndarray) -> np.ndarray:
    cols = [c for c, w in weights.items() if w != 0.0]
    if not cols:
        return np.zeros(len(z))
    w = np.array([weights[c] for c in cols])
    return sigma * (np.nan_to_num(z[cols].to_numpy(float)) @ w)


def horizon_vol(close: np.ndarray, horizon: int, vol_window: int = 60) -> np.ndarray:
    """Trailing ``horizon``-bar volatility at every bar, from ``vol_window`` daily returns
    ending at that bar."""
    r = pd.Series(close).pct_change()
    return (r.rolling(vol_window, min_periods=20).std() * math.sqrt(horizon)).to_numpy(float)


def conformal_halfwidth(residuals: np.ndarray, alpha: float) -> float | None:
    """Split-conformal half-width: the ``ceil((n + 1)(1 - alpha))``-th smallest absolute
    residual of the calibration set (Lei et al., "Distribution-free predictive inference
    for regression", JASA 2018). ``None`` when the set is too small for that rank."""
    r = np.abs(np.asarray(residuals, float))
    r = np.sort(r[np.isfinite(r)])
    k = math.ceil((r.size + 1) * (1.0 - alpha))
    if r.size == 0 or k > r.size:
        return None
    return float(r[k - 1])


def desk_forecast(df: pd.DataFrame, instrument: Instrument, cfg: dict[str, Any],
                  carry: np.ndarray | None = None, regimes: np.ndarray | None = None) -> Forecast:
    """The IC-combination forecast at the last bar of ``df`` (the as-of bar).

    ``cfg`` is ``config["combination"]`` plus, when conformal sizing is on, the keys of
    ``config["conformal"]`` under ``"conformal"``. ``regimes`` (one integer label per bar of
    ``df``, filtered: each label uses bars up to its own) conditions the estimate on the
    current regime: ICs come only from bars in the last bar's regime, and ``sigma`` from
    their returns.

    With conformal sizing the window is split in time: the ICs are estimated on its first
    ``1 - calibration_share`` and the calibration residuals ``r_t - mu_t`` come from the
    rest, ``horizon`` bars after the estimation part ends (the purge) and only for ``t``
    whose return is known at the as-of bar, so the calibration set lies strictly before the
    forecast and was not used to fit the weights it calibrates.
    """
    horizon, window = int(cfg["horizon"]), int(cfg["window"])
    close = df["Close"].to_numpy(float)
    end = len(close) - 1
    sig = signal_panel(df, instrument, carry)
    z = standardised(sig, window)
    vol = horizon_vol(close, horizon)
    rows = None
    regime = None
    if regimes is not None:
        regime = int(regimes[-1])
        rows = np.asarray(regimes) == regime
    conf = cfg.get("conformal") or {}
    split = bool(conf.get("enabled"))
    fit_end = end
    if split:
        share = float(conf.get("calibration_share", 0.4))
        fit_end = end - int(round(share * window))
    est = trailing_ics(sig, close, horizon, window if not split else window - (end - fit_end), fit_end, rows)
    weights = {k: v[0] for k, v in est.items()}
    t_stats = {k: v[1].t for k, v in est.items()}
    sigma = float(vol[-1])
    if rows is not None:
        r = pd.Series(close).pct_change().to_numpy(float)
        inr = r[max(1, end - window + 1):end + 1][rows[max(1, end - window + 1):end + 1]]
        inr = inr[np.isfinite(inr)]
        if inr.size >= 20:
            sigma = float(inr.std(ddof=1) * math.sqrt(horizon))
    if not math.isfinite(sigma) or sigma <= 0:
        return Forecast(0.0, float("nan"), 0.0, weights, t_stats, regime=regime)
    zl = np.nan_to_num(z.iloc[-1].to_numpy(float))
    mu = sigma * float(sum(weights[c] * zl[i] for i, c in enumerate(z.columns)))
    tilt = float(mean_variance(np.array([mu]), np.array([[sigma ** 2]]), float(cfg["risk_aversion"]))[0])
    interval = None
    if split:
        cal = np.arange(fit_end + horizon, end - horizon + 1)
        if cal.size:
            mus = _mu_series(z, weights, vol)[cal]
            fwd = forward_returns(close, horizon)[cal]
            interval = conformal_halfwidth(fwd - mus, float(conf.get("alpha", 0.2)))
        if interval is None:            # too few calibration points: an unbounded interval sizes to zero
            interval = math.inf
    return Forecast(mu, sigma, tilt, weights, t_stats, interval, regime)
