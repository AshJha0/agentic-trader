"""Execution realism helpers (v0.17, review item C1).

Three gaps the review found in the backtester's fills, each closed here by a plain function
that a run can apply without touching the engine loop (owned by another lane in v0.17):

1. **Stop slippage beyond the gap at the open.** ``pycore._exit_fill`` fills an intrabar stop
   exactly at the stop level. A real stop is a market order that triggers there and fills
   worse: you cross the spread, and on a fast bar you chase the move. ``stop_fill_with_slippage``
   fills a long stop at ``stop - half_spread - range_frac * (stop - low)``, never below the
   low (mirror for shorts); a gap through the stop fills at the open less the half spread.
2. **Participation cap.** The OMS caps a fill at ``participation_cap`` of ADV; the backtester
   does not. ``cap_participation`` turns a target weight path into the path a capped trader
   could actually hold: each bar's weight change is limited to ``cap * ADV_t * price_t /
   capital`` and the remainder carries to later bars.
3. **A $0 impact-coefficient calibration.** ``config.costs.impact_coeff`` (the ``Y`` in
   ``cost = Y * sigma * sqrt(q / ADV)``) is not calibrated. Free daily OHLC carries a
   spread estimate (Corwin and Schultz, 2012; Abdi and Ranaldo, 2017). ``spread_consistent_y``
   picks the ``Y`` at which the square-root law charges exactly the estimated half spread at a
   reference participation (1 % of ADV by default). That is an anchoring assumption, not a
   fit to fills (fills against arrival from our own simulated OMS would be circular); its
   evidence class is "model-implied from public OHLC".

Worked example (spread to Y). A name with a 4 bp estimated spread and 1.5 % daily volatility:
half spread 2 bp; at q/ADV = 1 % the square-root term is ``0.015 * 0.1 = 15`` bp, so
``Y = 2 / 15 = 0.13``, inside the 0.1-0.3 band the review quotes from the literature.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

_CS_K = 3.0 - 2.0 * math.sqrt(2.0)


# ---------------------------------------------------------------- stop slippage
def stop_fill_with_slippage(
    w: float, stop: float, o: float, h: float, low: float, half_spread: float = 0.0, range_frac: float = 0.0
) -> float:
    """Fill price of a protective stop on a bar with open ``o``, high ``h`` and low ``low``,
    or NaN when the stop does not trade. ``half_spread`` is a price fraction (5e-4 = 5 bp);
    ``range_frac`` in [0, 1] is the share of the distance from the stop to the bar's extreme
    lost while the market order works. With both 0 this is ``pycore._exit_fill``'s stop rule.
    """
    if not 0.0 <= range_frac <= 1.0 or half_spread < 0:
        raise ValueError("range_frac must be in [0, 1] and half_spread non-negative")
    if np.isnan(stop) or w == 0.0:
        return float("nan")
    if w > 0:
        if o <= stop:  # gapped through: market order at the open
            return max(low, o * (1.0 - half_spread))
        if low <= stop:
            px = stop * (1.0 - half_spread) - range_frac * (stop - low)
            return max(low, px)
    else:
        if o >= stop:
            return min(h, o * (1.0 + half_spread))
        if h >= stop:
            px = stop * (1.0 + half_spread) + range_frac * (h - stop)
            return min(h, px)
    return float("nan")


def stop_slippage_frac(
    w: float, stop: float, o: float, h: float, low: float, half_spread: float = 0.0, range_frac: float = 0.0
) -> float:
    """Extra loss (fraction of the position's notional at the stop) of the slipped fill over
    the engine's fill (stop level, or open on a gap). 0 when the stop does not trade."""
    if np.isnan(stop) or w == 0.0:
        return 0.0
    gapped = (o <= stop) if w > 0 else (o >= stop)
    base = o if gapped else stop
    hit = (low <= stop) if w > 0 else (h >= stop)
    if not (gapped or hit):
        return 0.0
    px = stop_fill_with_slippage(w, stop, o, h, low, half_spread, range_frac)
    return float(np.sign(w) * (base - px) / base)


# ---------------------------------------------------------------- participation cap
def cap_participation(target_weights, prices, adv, capital: float, cap: float = 0.10, equity=None) -> np.ndarray:
    """The weight path a trader limited to ``cap`` of ADV per bar can hold, chasing
    ``target_weights``. ``adv`` is average daily volume in shares (NaN or <= 0: uncapped bar);
    ``equity`` (optional, per bar) replaces the constant ``capital``. Price drift of the held
    weight between bars is ignored (the engine rebalances to the returned weights), so this is a
    constraint on the decision path, applied before the engine, not an engine change.
    NaN targets mean "hold"; the first bar starts flat."""
    if cap <= 0 or capital <= 0:
        raise ValueError("cap and capital must be positive")
    w = np.asarray(target_weights, dtype=float)
    p = np.asarray(prices, dtype=float)
    a = np.asarray(adv, dtype=float)
    if not (w.shape == p.shape == a.shape):
        raise ValueError("target_weights, prices and adv must have the same length")
    eq = np.full(w.size, float(capital)) if equity is None else np.asarray(equity, dtype=float)
    out = np.zeros(w.size)
    held = 0.0
    for t in range(w.size):
        tgt = held if np.isnan(w[t]) else float(w[t])
        dw = tgt - held
        if np.isfinite(a[t]) and a[t] > 0 and np.isfinite(p[t]) and eq[t] > 0:
            lim = cap * a[t] * p[t] / eq[t]
            dw = max(-lim, min(lim, dw))
        held += dw
        out[t] = held
    return out


def participation_shortfall(target_weights, capped) -> dict[str, float]:
    """How far the capped path lags the target: mean and max absolute weight gap, and the share
    of bars with a gap above 1e-9."""
    t = np.nan_to_num(np.asarray(target_weights, float), nan=0.0)
    gap = np.abs(t - np.asarray(capped, float))
    return {
        "mean_gap": float(gap.mean()) if gap.size else 0.0,
        "max_gap": float(gap.max()) if gap.size else 0.0,
        "bars_lagging": float((gap > 1e-9).mean()) if gap.size else 0.0,
    }


# ---------------------------------------------------------------- spread estimators
def corwin_schultz(high, low, close=None, floor: bool = True) -> np.ndarray:
    """Corwin-Schultz (2012) two-day high-low spread estimate, one value per pair of days
    (aligned to the second day; element 0 is NaN), as a fraction of price. Negative two-day
    estimates are set to 0 when ``floor`` (the paper's daily rule); ``floor=False`` keeps them,
    which removes the upward bias of flooring noise when the result is averaged. With ``close`` the paper's overnight adjustment
    is applied: day t+1's range is shifted by any gap that opens outside day t's close."""
    h = np.asarray(high, dtype=float).copy()
    lo = np.asarray(low, dtype=float).copy()
    n = h.size
    out = np.full(n, np.nan)
    if close is not None:
        c = np.asarray(close, dtype=float)
        for t in range(n - 1):
            if lo[t + 1] > c[t]:
                d = lo[t + 1] - c[t]
                h[t + 1] -= d
                lo[t + 1] -= d
            elif h[t + 1] < c[t]:
                d = c[t] - h[t + 1]
                h[t + 1] += d
                lo[t + 1] += d
    with np.errstate(divide="ignore", invalid="ignore"):
        hl = np.log(h / lo) ** 2
        beta = hl[:-1] + hl[1:]
        gamma = np.log(np.maximum(h[:-1], h[1:]) / np.minimum(lo[:-1], lo[1:])) ** 2
        alpha = (np.sqrt(2.0 * beta) - np.sqrt(beta)) / _CS_K - np.sqrt(gamma / _CS_K)
        s = 2.0 * (np.exp(alpha) - 1.0) / (1.0 + np.exp(alpha))
    out[1:] = np.maximum(s, 0.0) if floor else s
    return out


def abdi_ranaldo(high, low, close) -> float:
    """Abdi-Ranaldo (2017) close-high-low spread estimate over the whole sample (a price
    fraction): ``S^2 = 4 E[(c_t - eta_t)(c_t - eta_{t+1})]`` with ``eta`` the log mid-range and
    ``c`` the log close; a negative moment gives 0."""
    h, lo, c = (np.log(np.asarray(x, dtype=float)) for x in (high, low, close))
    eta = 0.5 * (h + lo)
    m = (c[:-1] - eta[:-1]) * (c[:-1] - eta[1:])
    m = m[np.isfinite(m)]
    if m.size == 0:
        return float("nan")
    return float(math.sqrt(max(4.0 * float(m.mean()), 0.0)))


def spread_estimates(df: pd.DataFrame) -> dict[str, float]:
    """Both estimators on an OHLC frame (columns High, Low, Close): the Corwin-Schultz two-day
    estimates averaged unfloored and then floored at 0 (``corwin_schultz``), the paper's
    floored-daily mean (``corwin_schultz_floored``, biased up when the spread is small next to
    volatility), and the full-sample Abdi-Ranaldo estimate."""
    raw = corwin_schultz(df["High"], df["Low"], df["Close"], floor=False)
    ok = np.isfinite(raw).any()
    return {
        "corwin_schultz": max(float(np.nanmean(raw)), 0.0) if ok else float("nan"),
        "corwin_schultz_floored": float(np.nanmean(np.maximum(raw, 0.0))) if ok else float("nan"),
        "abdi_ranaldo": abdi_ranaldo(df["High"], df["Low"], df["Close"]),
    }


# ---------------------------------------------------------------- impact calibration
def spread_consistent_y(spread: float, daily_vol: float, ref_participation: float = 0.01) -> float:
    """The square-root-law coefficient ``Y`` at which ``Y * daily_vol * sqrt(ref_participation)``
    equals half of ``spread``: the impact model then agrees with the quoted cost of a small
    (reference-sized) order and grows as sqrt above it. NaN when inputs are not usable."""
    if not (spread >= 0 and daily_vol > 0 and 0 < ref_participation <= 1):
        return float("nan")
    return 0.5 * spread / (daily_vol * math.sqrt(ref_participation))


def calibrate_impact(frames: dict[str, pd.DataFrame], ref_participation: float = 0.01, vol_window: int = 250) -> pd.DataFrame:
    """One row per symbol: both spread estimates (bp), trailing daily volatility, and the
    spread-consistent ``Y`` from each estimator. ``frames`` are OHLC(V) frames."""
    rows = []
    for sym, df in frames.items():
        est = spread_estimates(df)
        r = np.diff(np.log(df["Close"].to_numpy(float)))
        r = r[np.isfinite(r)][-vol_window:]
        vol = float(r.std(ddof=1)) if r.size > 2 else float("nan")
        rows.append(
            {
                "symbol": sym,
                "days": len(df),
                "cs_spread_bp": 1e4 * est["corwin_schultz"],
                "ar_spread_bp": 1e4 * est["abdi_ranaldo"],
                "daily_vol_pct": 100 * vol,
                "Y_cs": spread_consistent_y(est["corwin_schultz"], vol, ref_participation),
                "Y_ar": spread_consistent_y(est["abdi_ranaldo"], vol, ref_participation),
            }
        )
    return pd.DataFrame(rows).set_index("symbol") if rows else pd.DataFrame()


def simulate_ohlc(
    n_days: int, spread: float, daily_vol: float = 0.01, steps: int = 100, seed: int = 0, start: float = 100.0
) -> pd.DataFrame:
    """Synthetic OHLC with a known effective spread, for validating the estimators: an
    efficient log price follows a random walk observed ``steps`` times a day; every observed
    trade is at the efficient price times ``1 +/- spread / 2`` (random side). High, Low and
    Close are taken from the observed trades, Open from the first."""
    rng = np.random.default_rng(seed)
    sd = daily_vol / math.sqrt(steps)
    logp = math.log(start) + np.cumsum(rng.normal(0.0, sd, n_days * steps))
    side = rng.choice([-1.0, 1.0], n_days * steps)
    px = np.exp(logp) * (1.0 + side * spread / 2.0)
    px = px.reshape(n_days, steps)
    idx = pd.bdate_range("2000-01-03", periods=n_days)
    return pd.DataFrame(
        {"Open": px[:, 0], "High": px.max(axis=1), "Low": px.min(axis=1), "Close": px[:, -1], "Volume": np.full(n_days, 1e6)},
        index=idx,
    )
