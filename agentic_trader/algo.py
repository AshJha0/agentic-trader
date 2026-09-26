"""Execution algorithms and an intraday execution simulator.

A decision is a target weight; execution turns the weight change into a parent
order and slices it over the session:

* **TWAP**            equal slices over time (default for FX, which has no volume curve);
* **VWAP**            slices follow the expected intraday volume profile (equities);
* **POV**             a fixed participation of each slice's volume, capped;
* **Almgren-Chriss**  front-loaded schedule trading impact against timing risk.

The simulator fills each slice on synthetic intraday bars built from the day's
OHLCV (a Brownian bridge from open to close that respects the high and the low),
charging half the spread and square-root temporary impact. It reports
implementation shortfall against the arrival price and slippage against the
session VWAP, both in basis points. It is a model, not a venue: it exists to make
the cost of a decision visible and to compare algorithms on equal terms.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from . import quant
from .instruments import Instrument
from .state import FinalDecision

Side = Literal["buy", "sell"]
Algo = Literal["twap", "vwap", "pov", "ac"]


# ------------------------------------------------------------- profiles
def volume_profile(kind: str, n: int) -> np.ndarray:
    """Expected share of the session's volume in each of ``n`` slices.

    Equities: the familiar U shape (heavy open and close). FX: flat.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    if kind == "fx":
        return np.full(n, 1.0 / n)
    t = (np.arange(n) + 0.5) / n
    u = 1.0 + 2.5 * (t - 0.5) ** 2 * 4  # 1 at midday, 3.5 at the edges
    return u / u.sum()


def synthetic_intraday_bars(day: pd.Series, n: int, kind: str = "equity", seed: int = 0) -> pd.DataFrame:
    """``n`` intraday bars consistent with one daily OHLCV bar.

    Prices follow a Brownian bridge from the open to the close. Excursions above
    the open/close are stretched to reach the day's high and excursions below to
    reach the low, so the path never leaves [low, high] and touches both whenever
    the bridge wanders past the open and close. Volume follows the profile.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    o, h, l, c = (float(day[k]) for k in ("Open", "High", "Low", "Close"))
    if not (l <= min(o, c) and h >= max(o, c)):
        raise ValueError("daily bar must contain its open and close")
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 1, n + 1)
    w = np.concatenate([[0.0], np.cumsum(rng.standard_normal(n)) / math.sqrt(n)])
    bridge = w - t * w[-1]
    path = o + (c - o) * t + bridge * (h - l) * 0.5
    # Stretch so the path spans exactly [low, high], keeping the open and the close.
    lo, hi = path.min(), path.max()
    if hi > lo:
        inner = path[1:-1]
        if inner.size:
            up = np.where(inner > max(o, c), (inner - max(o, c)) / max(hi - max(o, c), 1e-12) * (h - max(o, c)) + max(o, c), inner)
            down = np.where(inner < min(o, c), min(o, c) - (min(o, c) - inner) / max(min(o, c) - lo, 1e-12) * (min(o, c) - l), up)
            path = np.concatenate([[o], down, [c]])
    vol = float(day.get("Volume", 0.0)) * volume_profile(kind, n)
    bars = pd.DataFrame({
        "Open": path[:-1], "Close": path[1:],
        "High": np.maximum(path[:-1], path[1:]), "Low": np.minimum(path[:-1], path[1:]),
        "Volume": vol,
    })
    bars["VWAP"] = (bars["Open"] + bars["Close"] + bars["High"] + bars["Low"]) / 4.0
    return bars


# ------------------------------------------------------------ schedules
def twap_schedule(total: float, n: int) -> np.ndarray:
    if n <= 0:
        raise ValueError("n must be positive")
    return np.full(n, total / n)


def vwap_schedule(total: float, profile: np.ndarray) -> np.ndarray:
    p = np.asarray(profile, float)
    if p.ndim != 1 or p.size == 0 or (p < 0).any() or p.sum() <= 0:
        raise ValueError("profile must be a non-negative vector with positive sum")
    return total * p / p.sum()


def pov_schedule(total: float, volumes: np.ndarray, participation: float, cap: float = 0.20) -> np.ndarray:
    """Trade ``participation`` of each slice's volume (capped) until done; any
    remainder is left unexecuted and reported by the simulator."""
    if not 0 < participation <= cap:
        raise ValueError(f"participation must be in (0, {cap}]")
    v = np.asarray(volumes, float)
    out = np.zeros(v.size)
    remaining = total
    for i, vol in enumerate(v):
        q = min(remaining, participation * max(vol, 0.0))
        out[i] = q
        remaining -= q
        if remaining <= 1e-12:
            break
    return out


def almgren_chriss_schedule(total: float, n: int, sigma_session: float, eta: float,
                            risk_aversion: float) -> np.ndarray:
    """Slice quantities with kappa = sqrt(risk_aversion * sigma^2 / eta).

    ``sigma_session`` is the price volatility over the session, ``eta`` the
    temporary impact coefficient (price move per unit of trading rate). Both in
    price units; only their ratio matters.
    """
    if eta <= 0 or sigma_session < 0 or risk_aversion < 0:
        raise ValueError("eta must be positive; sigma and risk aversion non-negative")
    kappa = math.sqrt(risk_aversion * sigma_session ** 2 / eta)
    return quant.almgren_chriss(total, n, kappa)


# ------------------------------------------------------------- simulator
@dataclass
class Fill:
    slice: int
    quantity: float
    price: float
    participation: float  # slice qty / slice volume (NaN for FX)


@dataclass
class ExecutionReport:
    side: Side
    algo: str
    requested: float
    executed: float
    arrival: float
    avg_price: float
    session_vwap: float
    is_bps: float          # implementation shortfall vs arrival (positive = cost)
    vs_vwap_bps: float     # slippage vs session VWAP (positive = worse than VWAP)
    spread_cost_bps: float
    impact_cost_bps: float
    max_participation: float
    fills: list[Fill] = field(default_factory=list)

    @property
    def completion(self) -> float:
        return self.executed / self.requested if self.requested else 1.0

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "fills"}
        d["completion"] = round(self.completion, 4)
        return d


def simulate_execution(schedule: np.ndarray, bars: pd.DataFrame, side: Side, algo: str = "custom",
                       spread_bps: float = 2.0, impact_coeff: float = 1.0,
                       daily_vol: float = 0.02, adv: float | None = None) -> ExecutionReport:
    """Fill a schedule against intraday bars.

    Each slice fills at the bar's VWAP, plus half the spread against the trader,
    plus temporary impact ``impact_coeff * daily_vol * sqrt(q / ADV)`` (the
    square-root law) when ADV is known. Slices larger than the bar's volume are
    cut to it for equities; the shortfall is reported.
    """
    q = np.asarray(schedule, float)
    if q.size != len(bars):
        raise ValueError("schedule and bars must have the same length")
    if (q < 0).any():
        raise ValueError("schedule quantities must be non-negative")
    sign = 1.0 if side == "buy" else -1.0
    arrival = float(bars["Open"].iloc[0])
    vols = bars["Volume"].to_numpy(float)
    has_volume = vols.sum() > 0
    fills, spread_cost, impact_cost, ref_notional = [], 0.0, 0.0, 0.0
    for i, (qty, vwap, vol) in enumerate(zip(q, bars["VWAP"].to_numpy(float), vols)):
        if qty <= 0:
            continue
        if has_volume and vol > 0:
            qty = min(qty, vol)   # cannot trade more than the bar's volume
        part = qty / vol if has_volume and vol > 0 else float("nan")
        impact = impact_coeff * daily_vol * math.sqrt(qty / adv) if adv and adv > 0 else 0.0
        px = vwap * (1.0 + sign * (spread_bps / 2e4 + impact))
        fills.append(Fill(i, qty, px, part))
        spread_cost += qty * vwap * spread_bps / 2e4
        impact_cost += qty * vwap * impact
        ref_notional += qty * vwap    # costs are quoted against the unperturbed (VWAP) notional
    executed = float(sum(f.quantity for f in fills))
    if executed <= 0:
        return ExecutionReport(side, algo, float(q.sum()), 0.0, arrival, float("nan"), float("nan"),
                               float("nan"), float("nan"), 0.0, 0.0, float("nan"), [])
    avg = float(sum(f.quantity * f.price for f in fills) / executed)
    if has_volume:
        session_vwap = float((bars["VWAP"] * bars["Volume"]).sum() / vols.sum())
    else:
        session_vwap = float(bars["VWAP"].mean())
    parts = [float(f.participation) for f in fills if math.isfinite(f.participation)]
    return ExecutionReport(
        side, algo, float(q.sum()), executed, arrival, avg, session_vwap,
        is_bps=float(sign * (avg / arrival - 1.0) * 1e4),
        vs_vwap_bps=float(sign * (avg / session_vwap - 1.0) * 1e4),
        spread_cost_bps=float(spread_cost / ref_notional * 1e4),
        impact_cost_bps=float(impact_cost / ref_notional * 1e4),
        max_participation=max(parts) if parts else float("nan"), fills=fills)


# ------------------------------------------------------- decision -> plan
@dataclass
class ExecutionPlan:
    instrument: Instrument
    side: Side
    quantity: float          # shares (equity) or base-currency notional (FX)
    notional: float          # in quote / account currency
    algo: Algo
    slices: int
    reason: str
    adv: float | None = None
    participation_of_adv: float | None = None

    def schedule(self, bars: pd.DataFrame, participation: float = 0.10,
                 sigma_session: float | None = None, eta: float | None = None,
                 risk_aversion: float = 1e-6) -> np.ndarray:
        n = len(bars)
        if self.algo == "twap":
            return twap_schedule(self.quantity, n)
        if self.algo == "vwap":
            return vwap_schedule(self.quantity, bars["Volume"].to_numpy(float) if bars["Volume"].sum() > 0
                                 else volume_profile("fx", n))
        if self.algo == "pov":
            return pov_schedule(self.quantity, bars["Volume"].to_numpy(float), participation)
        sigma = sigma_session if sigma_session is not None else float(bars["Close"].std() or 1e-6)
        return almgren_chriss_schedule(self.quantity, n, sigma, eta if eta is not None else sigma * 1e-6 + 1e-9,
                                       risk_aversion)


def plan_execution(decision: FinalDecision, instrument: Instrument, current_weight: float,
                   capital: float, last_price: float, adv: float | None = None,
                   algo: Algo | None = None, slices: int | None = None,
                   max_adv_participation: float = 0.10) -> ExecutionPlan | None:
    """Turn a weight change into a parent order. ``None`` when nothing needs trading.

    Algorithm choice: FX defaults to TWAP; equities default to VWAP, or POV when
    the order exceeds ``max_adv_participation`` of average daily volume.
    """
    if capital <= 0 or last_price <= 0:
        raise ValueError("capital and last_price must be positive")
    delta = decision.target_weight - current_weight
    if abs(delta) < 1e-9:
        return None
    notional = abs(delta) * capital
    side: Side = "buy" if delta > 0 else "sell"
    qty = notional / last_price   # shares, or base-currency units for FX
    part = qty / adv if adv else None
    reason = f"weight {current_weight:+.2f} -> {decision.target_weight:+.2f}"
    if algo is None:
        if instrument.is_fx:
            algo = "twap"
        elif part is not None and part > max_adv_participation:
            algo, reason = "pov", reason + f"; {part:.1%} of ADV exceeds {max_adv_participation:.0%} -> POV"
        else:
            algo = "vwap"
    n = slices or (288 if instrument.is_fx else 78)  # 5-minute slices: 24h FX, 6.5h equity session
    return ExecutionPlan(instrument, side, qty, notional, algo, n, reason, adv, part)
