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

Timing convention: a decision is taken with information up to the close of the
as-of day, so the order is *sized* at that close and *executed* on the next
session (``plan_execution`` sizes; the callers build the bars from the following
daily bar and pass them to ``simulate_execution``).
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

import numpy as np
import pandas as pd

from . import quant
from .instruments import Instrument
from .state import FinalDecision

Side = Literal["buy", "sell"]
Algo = Literal["twap", "vwap", "pov", "ac"]
ALGOS = ("twap", "vwap", "pov", "ac")


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
    """Trade ``participation`` of each slice's volume (capped) until done. The schedule
    holds only what can be filled; pass the parent quantity to ``simulate_execution``
    as ``requested`` so the unexecuted remainder is reported."""
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
    price units; only their ratio matters. ``ExecutionPlan.schedule`` does not use
    this: it takes the dimensionless urgency ``kappa`` directly so the schedule
    cannot depend on the price level.
    """
    if eta <= 0 or sigma_session < 0 or risk_aversion < 0:
        raise ValueError("eta must be positive; sigma and risk aversion non-negative")
    kappa = math.sqrt(risk_aversion * sigma_session ** 2 / eta)
    return quant.almgren_chriss(total, n, kappa)


# ------------------------------------------------------ cost model by algorithm
def algo_cost_ratio(algo: str, n: int, kind: str, kappa: float = 3.0) -> float:
    """Square-root-law impact cost of executing one order under ``algo``, relative to VWAP.

    ``simulate_execution`` charges each slice ``impact_coeff * daily_vol * sqrt(q_i / V_i)`` of
    temporary impact, with ``V_i`` the slice's own volume (the bar's volume; for FX the notional
    ADV spread flat over the session), so a schedule's total cost (for a fixed total quantity)
    is proportional to ``sum(q_i^1.5 / sqrt(V_i))``. VWAP trades ``q_i`` proportional to the
    expected volume ``V_i``, which makes every slice's participation rate ``q_i / V_i``
    identical and, by the convexity of ``sqrt``, minimises this sum -- so its cost ratio is
    exactly 1.0 by construction, for any volume curve, and its total equals the single-shot
    law ``daily_vol * sqrt(Q / ADV)`` that ``backtest.impact_coefficients`` applies (one shot
    at the account's ADV participation). The simulator, the backtester and this ratio are
    therefore one model: for TWAP and Almgren-Chriss the simulator's impact equals VWAP's
    times this ratio (exactly on a flat-price session, to the price-weighting otherwise).

    * **TWAP** ignores the volume curve and trades equal amounts per slice; against
      equities' U-shaped intraday curve (heavy at the open and close, light at midday) this
      over-trades the illiquid middle of the session, so its ratio is >= 1.0 (== 1.0 only for
      a flat curve, i.e. FX).
    * **Almgren-Chriss** (``kappa``, urgency: 0 = TWAP, larger = more front-loaded) trades a
      fixed *time* profile regardless of the volume curve. A small kappa can align with an
      opening volume spike and cost slightly less than TWAP; kappa large enough to front-load
      past the opening spike costs more, monotonically, as it increasingly concentrates size
      into a shrinking window.
    * **POV** is excluded here: unlike the other three it need not complete the order within
      one session (it trades a fixed participation of *realized* volume and stops if the
      volume never arrives), which is a fill-risk question this same-session, always-fills
      cost model does not represent -- ``simulate_execution`` reports POV's completion and
      the opportunity cost of what it left unfilled.

    ``n`` and ``kind`` should match the session slicing used elsewhere for the instrument
    (``plan_execution`` uses 78 equity / 288 FX slices); the ratio is dimensionless and does
    not depend on the order's size, ``ADV`` or volatility, only on how it is spread across
    the session relative to where the volume is.
    """
    if algo not in ("twap", "vwap", "ac"):
        raise ValueError(f"algo_cost_ratio: unsupported algo {algo!r} (twap, vwap or ac)")
    profile = volume_profile(kind, n)
    if algo == "twap":
        q = twap_schedule(1.0, n)
    elif algo == "vwap":
        q = vwap_schedule(1.0, profile)
    else:
        q = quant.almgren_chriss(1.0, n, kappa)
    return float(np.sum(q ** 1.5 / np.sqrt(profile)))


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
    requested: float       # the parent order, not the schedule's sum
    executed: float
    arrival: float         # first bar's open
    close: float           # session close: the mark for whatever was left unfilled
    avg_price: float
    session_vwap: float
    is_bps: float          # implementation shortfall on the requested quantity vs arrival (positive = cost):
                           # the executed leg plus the opportunity cost of the unfilled remainder (Perold)
    opportunity_cost_bps: float  # the unfilled remainder marked at the close vs arrival, per requested notional
    vs_vwap_bps: float     # slippage of the fills vs session VWAP (positive = worse than VWAP)
    spread_cost_bps: float
    impact_cost_bps: float
    max_participation: float
    fills: list[Fill] = field(default_factory=list)

    @property
    def unfilled(self) -> float:
        return max(self.requested - self.executed, 0.0)

    @property
    def completion(self) -> float:
        return self.executed / self.requested if self.requested > 0 else 1.0

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "fills"}
        d["unfilled"] = self.unfilled
        d["completion"] = round(self.completion, 4)
        return d


def simulate_execution(schedule: np.ndarray, bars: pd.DataFrame, side: Side, algo: str = "custom",
                       spread_bps: float = 2.0, impact_coeff: float = 1.0,
                       daily_vol: float = 0.02, adv: float | None = None,
                       requested: float | None = None) -> ExecutionReport:
    """Fill a schedule against intraday bars.

    Each slice fills at the bar's VWAP, plus half the spread against the trader, plus
    temporary impact ``impact_coeff * daily_vol * sqrt(q_i / V_i)`` (the square-root law
    at the slice's own participation): ``V_i`` is the bar's volume, or, for bars without
    volume (FX), ``adv / n`` when a notional ``adv`` in the schedule's units is given,
    else no impact. A VWAP schedule therefore reproduces the single-shot law
    ``daily_vol * sqrt(Q / ADV)`` exactly, whatever the slice count, and TWAP /
    Almgren-Chriss reproduce ``algo_cost_ratio``. Slices larger than the bar's volume are
    cut to it; a bar with no volume fills nothing.

    ``requested`` is the parent order; it defaults to the schedule's total but must be
    passed for POV (whose schedule already omits what it cannot fill). Completion is
    ``executed / requested`` and ``is_bps`` charges the unfilled remainder at the session
    close against arrival (reported separately as ``opportunity_cost_bps``).
    """
    q = np.asarray(schedule, float)
    if q.size != len(bars):
        raise ValueError("schedule and bars must have the same length")
    if (q < 0).any():
        raise ValueError("schedule quantities must be non-negative")
    total = float(q.sum())
    requested = total if requested is None else float(requested)
    if requested < total * (1 - 1e-9) or requested < 0:
        raise ValueError("requested must be at least the schedule's total")
    sign = 1.0 if side == "buy" else -1.0
    arrival = float(bars["Open"].iloc[0])
    close = float(bars["Close"].iloc[-1])
    vols = bars["Volume"].to_numpy(float)
    has_volume = vols.sum() > 0
    n = len(bars)
    fills, spread_cost, impact_cost, ref_notional = [], 0.0, 0.0, 0.0
    for i, (qty, vwap, vol) in enumerate(zip(q, bars["VWAP"].to_numpy(float), vols)):
        if qty <= 0:
            continue
        if has_volume:
            if vol <= 0:
                continue
            qty = min(qty, vol)   # cannot trade more than the bar's volume
            slice_volume, part = vol, qty / vol
        else:
            slice_volume, part = (adv / n if adv and adv > 0 else 0.0), float("nan")
        impact = impact_coeff * daily_vol * math.sqrt(qty / slice_volume) if slice_volume > 0 else 0.0
        px = vwap * (1.0 + sign * (spread_bps / 2e4 + impact))
        fills.append(Fill(i, qty, px, part))
        spread_cost += qty * vwap * spread_bps / 2e4
        impact_cost += qty * vwap * impact
        ref_notional += qty * vwap    # costs are quoted against the unperturbed (VWAP) notional
    executed = float(sum(f.quantity for f in fills))
    unfilled_share = (requested - executed) / requested if requested > 0 else 0.0
    opportunity_bps = float(sign * (close / arrival - 1.0) * unfilled_share * 1e4)
    if executed <= 0:
        return ExecutionReport(side, algo, requested, 0.0, arrival, close, float("nan"), float("nan"),
                               opportunity_bps, opportunity_bps, float("nan"), 0.0, 0.0, float("nan"), [])
    avg = float(sum(f.quantity * f.price for f in fills) / executed)
    if has_volume:
        session_vwap = float((bars["VWAP"] * bars["Volume"]).sum() / vols.sum())
    else:
        session_vwap = float(bars["VWAP"].mean())
    parts = [float(f.participation) for f in fills if math.isfinite(f.participation)]
    executed_bps = float(sign * (avg / arrival - 1.0) * (1.0 - unfilled_share) * 1e4)
    return ExecutionReport(
        side, algo, requested, executed, arrival, close, avg, session_vwap,
        is_bps=executed_bps + opportunity_bps,
        opportunity_cost_bps=opportunity_bps,
        vs_vwap_bps=float(sign * (avg / session_vwap - 1.0) * 1e4),
        spread_cost_bps=float(spread_cost / ref_notional * 1e4),
        impact_cost_bps=float(impact_cost / ref_notional * 1e4),
        max_participation=max(parts) if parts else float("nan"), fills=fills)


# ------------------------------------------------------- decision -> plan
def plan_reference(symbol: str, side: str, quantity: float, quantity_unit: str, notional: float,
                   notional_currency: str, price: float) -> str:
    """The plan id: a checksum over the ticket fields a plan fixes. ``submit_order`` recomputes
    it, so a ticket whose numbers were not produced together by ``plan_execution`` (or were
    edited afterwards) does not match its own reference."""
    key = json.dumps([Instrument.parse(symbol).symbol, str(side), repr(float(quantity)), str(quantity_unit),
                      repr(float(notional)), str(notional_currency).upper(), repr(float(price))])
    return "PLAN-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def trade_intent(current_weight: float, target_weight: float, tol: float = 1e-9) -> str:
    """What the weight change does to the position: open/add/reduce/close a long or a short,
    cover, or reverse. A ticket carries it so a sell to reduce is never read as a short sale."""
    c, t = current_weight, target_weight
    flat_c, flat_t = abs(c) <= tol, abs(t) <= tol
    if t > c + tol:
        if c < -tol:
            return "buy_to_cover" if flat_t else ("reduce_short" if t < -tol else "reverse_to_long")
        return "open_long" if flat_c else "add_long"
    if t < c - tol:
        if c > tol:
            return "sell_to_close" if flat_t else ("sell_to_reduce" if t > tol else "reverse_to_short")
        return "sell_short" if flat_c else "add_short"
    return "none"


@dataclass
class ExecutionPlan:
    instrument: Instrument
    side: Side
    quantity: float          # whole shares (equity) or whole lots of the base currency (FX): rounded at plan time
    quantity_unit: str       # "shares" or the base currency code
    notional: float          # of the rounded quantity, in notional_currency
    notional_currency: str   # the account currency
    price: float             # reference price the order was sized at (the as-of close)
    algo: Algo
    slices: int
    reason: str
    current_weight: float
    target_weight: float     # the effective target, after any long-only truncation
    intent: str
    adv: float | None = None
    participation_of_adv: float | None = None
    ac_kappa: float = 3.0
    lot_size: float = 1.0

    @property
    def id(self) -> str:
        return plan_reference(self.instrument.symbol, self.side, self.quantity, self.quantity_unit,
                              self.notional, self.notional_currency, self.price)

    def schedule(self, bars: pd.DataFrame, participation: float = 0.10, kappa: float | None = None) -> np.ndarray:
        """Slice quantities per bar. ``kappa`` (Almgren-Chriss urgency, dimensionless: 0 = TWAP,
        larger = more front-loaded) defaults to the plan's ``ac_kappa``; it never depends on the
        bars' price level or path."""
        n = len(bars)
        if self.algo == "twap":
            return twap_schedule(self.quantity, n)
        if self.algo == "vwap":
            return vwap_schedule(self.quantity, bars["Volume"].to_numpy(float) if bars["Volume"].sum() > 0
                                 else volume_profile("fx", n))
        if self.algo == "pov":
            return pov_schedule(self.quantity, bars["Volume"].to_numpy(float), participation)
        return quant.almgren_chriss(self.quantity, n, self.ac_kappa if kappa is None else float(kappa))

    def to_dict(self) -> dict:
        return {"plan_id": self.id, "symbol": self.instrument.symbol, "side": self.side, "intent": self.intent,
                "quantity": self.quantity, "quantity_unit": self.quantity_unit, "notional": self.notional,
                "notional_currency": self.notional_currency, "price": self.price, "algo": self.algo,
                "slices": self.slices, "reason": self.reason, "current_weight": self.current_weight,
                "target_weight": self.target_weight, "adv": self.adv,
                "participation_of_adv": self.participation_of_adv, "ac_kappa": self.ac_kappa,
                "lot_size": self.lot_size}


def base_to_account_rate(provider, base: str, account: str, as_of: date) -> float:
    """Price of one unit of ``base`` in ``account`` at the close of ``as_of``, read from the
    provider's history of the direct pair (``base/account``) or the inverse. Raises
    ``ValueError`` when neither is available rather than guessing."""
    base, account = base.upper(), account.upper()
    if base == account:
        return 1.0
    last_error = ""
    for pair, invert in ((base + account, False), (account + base, True)):
        try:
            ins = Instrument.parse(pair, "fx")
            df = provider.history(ins, as_of - timedelta(days=14), as_of)
        except Exception as e:  # an unknown pair or a failed download: try the other quote, then refuse
            last_error = f"{pair}: {e}"
            continue
        df = df[df.index <= pd.Timestamp(as_of)] if len(df) else df
        if len(df) and float(df["Close"].iloc[-1]) > 0:
            px = float(df["Close"].iloc[-1])
            return 1.0 / px if invert else px
    raise ValueError(f"no {base}{account} or {account}{base} rate available as of {as_of}"
                     + (f" ({last_error})" if last_error else "") + "; cannot convert the "
                     f"{account} notional into {base}")


def plan_execution(decision: FinalDecision, instrument: Instrument, current_weight: float,
                   capital: float, last_price: float, adv: float | None = None,
                   algo: Algo | None = None, slices: int | None = None,
                   max_adv_participation: float = 0.10, *, account_currency: str = "USD",
                   base_to_account: float | None = None, allow_short: bool | None = None,
                   lot_size: float | None = None, ac_kappa: float = 3.0) -> ExecutionPlan | None:
    """Turn a weight change into a parent order. ``None`` when nothing needs trading.

    Sizing: ``notional = |target - current| * capital`` in the account currency; the quantity
    is that notional divided by the price of one unit in the account currency and rounded
    *down* once, here, to whole shares (equity) or to ``lot_size`` base-currency units (FX,
    default one unit). The notional reported is that of the rounded quantity. Equities are
    assumed quoted in the account currency. For FX the unit is the base currency: when the
    base is the account currency the quantity equals the notional (USDJPY on a USD account);
    when the quote is, it is ``notional / last_price`` (EURUSD); for a cross the caller
    supplies ``base_to_account`` (the EURUSD rate for EURGBP or EURJPY on a USD account,
    ``base_to_account_rate`` reads it from a provider) and without it this raises.

    ``allow_short`` (default: FX yes, equities no -- the desk's default policy) truncates a
    negative target to flat, so a long-only book only ever reduces; the plan's ``reason`` and
    ``intent`` say so. ``ac_kappa`` is the dimensionless Almgren-Chriss urgency the schedule
    uses (0 = TWAP; ``costs.ac_kappa`` in config).

    Algorithm choice: FX defaults to TWAP; equities default to VWAP, or POV when
    the order exceeds ``max_adv_participation`` of average daily volume.
    """
    if capital <= 0 or last_price <= 0:
        raise ValueError("capital and last_price must be positive")
    if algo is not None and algo not in ALGOS:
        raise ValueError(f"unknown execution algo {algo!r} (twap, vwap, pov or ac)")
    if ac_kappa < 0:
        raise ValueError("ac_kappa must be >= 0")
    if allow_short is None:
        allow_short = instrument.is_fx
    target = float(decision.target_weight)
    effective = target if (allow_short or target >= 0) else 0.0
    delta = effective - current_weight
    if abs(delta) < 1e-9:
        return None
    account = account_currency.upper()
    if instrument.is_fx:
        unit = str(instrument.base)
        if instrument.base == account:
            unit_price = 1.0
        elif instrument.quote == account:
            unit_price = last_price
        elif base_to_account is not None and base_to_account > 0:
            unit_price = float(base_to_account)
        else:
            raise ValueError(f"{instrument.display}: sizing a {account} notional in {unit} needs the {unit}{account} "
                             f"rate (base_to_account); none was given")
        lot = float(lot_size) if lot_size else 1.0
    else:
        unit, unit_price, lot = "shares", last_price, 1.0
    if lot <= 0:
        raise ValueError("lot_size must be positive")
    raw = abs(delta) * capital / unit_price
    qty = math.floor(raw / lot + 1e-9) * lot
    if qty <= 0:
        raise ValueError(f"{instrument.display}: an order of {raw:.4g} {unit} is below one lot of {lot:g}; "
                         "nothing to ticket")
    notional = qty * unit_price
    side: Side = "buy" if delta > 0 else "sell"
    part = qty / adv if adv else None
    reason = f"weight {current_weight:+.2f} -> {effective:+.2f}"
    if effective != target:
        reason += f" (target {target:+.2f} truncated to flat: shorting {instrument.display} is not allowed)"
    if algo is None:
        if instrument.is_fx:
            algo = "twap"
        elif part is not None and part > max_adv_participation:
            algo, reason = "pov", reason + f"; {part:.1%} of ADV exceeds {max_adv_participation:.0%} -> POV"
        else:
            algo = "vwap"
    n = slices or (288 if instrument.is_fx else 78)  # 5-minute slices: 24h FX, 6.5h equity session
    return ExecutionPlan(instrument, side, float(qty), unit, float(notional), account, float(last_price), algo, n,
                         reason, float(current_weight), effective, trade_intent(current_weight, effective),
                         adv, part, float(ac_kappa), lot)
