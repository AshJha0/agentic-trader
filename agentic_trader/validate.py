"""Edge-case validators: bars, session clocks, survivorship, short notional, ledger floats.

Every check here refuses with a reason a person can read rather than repairing quietly.
``data.base.clean_ohlcv`` is the repair step a provider runs on raw downloads; the bar
validator is the gate after it, run where history enters the graph, so a frame that a
provider (or a test double, or a future provider) hands over in a bad state stops there
with the reason instead of flowing into analysts, sizing and the backtest.

Session-clock convention (plan item 5.7; docs/quant/quant.md section 14)
--------------------------------------------------------------------------------
A daily bar is labelled with its New York trade date. An equity session on date D closes
at 16:00 America/New_York; the FX day labelled D closes at the 17:00 New York roll, one
hour later. Both clocks are New York wall time, so a US daylight-saving change moves both
by the same amount and the one-hour gap is constant in every season, while the UTC times
shift (21:00/22:00 UTC in winter, 20:00/21:00 UTC in summer). A European DST change that
does not coincide with the US one does not move either label. Sleeves are aligned on
trade dates; a date on which one sleeve has no bar (a US equity holiday on which FX
trades) is not a common date, so a multi-sleeve rebalance waits for the next date on
which every sleeve has a bar.
"""
from __future__ import annotations

import math
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

NEW_YORK = ZoneInfo("America/New_York")
EQUITY_CLOSE_NY = time(16, 0)
FX_ROLL_NY = time(17, 0)

# Largest calendar-day step between consecutive bars accepted per asset class. Equities:
# 7 days covers the longest US closure in the free-data era (11-17 September 2001, a Monday
# to the next Monday). FX: 5 days covers a holiday on a Friday or Monday next to a weekend.
MAX_GAP_DAYS: dict[str, int] = {"equity": 7, "fx": 5}

PRICE_COLUMNS = ("Open", "High", "Low", "Close")


class BarValidationError(ValueError):
    """A history frame failed validation; ``reasons`` lists every failed check."""

    def __init__(self, label: str, reasons: list[str]):
        self.reasons = reasons
        super().__init__(f"refusing {label}: " + "; ".join(reasons))


def bar_problems(df: pd.DataFrame, asset_class: str, max_gap_days: int | None = None) -> list[str]:
    """Every reason ``df`` is not a usable daily OHLCV history, or ``[]`` when it is.

    Checks, each reported once with the first offending date: a missing price column;
    a NaN, zero or negative price; High below Low; duplicate dates; dates out of order;
    a step between consecutive bars longer than ``max_gap_days`` (default
    ``MAX_GAP_DAYS[asset_class]``). The frame is not modified.
    """
    if asset_class not in MAX_GAP_DAYS:
        raise ValueError(f"unknown asset class {asset_class!r}; choose from {sorted(MAX_GAP_DAYS)}")
    limit = MAX_GAP_DAYS[asset_class] if max_gap_days is None else max_gap_days
    reasons: list[str] = []
    missing = [c for c in PRICE_COLUMNS if c not in df.columns]
    if missing:
        return [f"missing price columns {missing}"]
    idx = pd.DatetimeIndex(df.index)
    for col in PRICE_COLUMNS:
        v = pd.to_numeric(df[col], errors="coerce").to_numpy(float)
        for bad, what in ((np.isnan(v), "NaN"), (v <= 0, "zero or negative")):
            if bad.any():
                reasons.append(f"{what} {col} on {idx[int(np.argmax(bad))].date()}")
    inverted = (pd.to_numeric(df["High"], errors="coerce") < pd.to_numeric(df["Low"], errors="coerce")).to_numpy()
    if inverted.any():
        reasons.append(f"High below Low on {idx[int(np.argmax(inverted))].date()}")
    dup = idx.duplicated()
    if dup.any():
        reasons.append(f"duplicate date {idx[int(np.argmax(dup))].date()}")
    # Steps in seconds, independent of the index's datetime unit (ns, us, ...).
    steps = (idx[1:] - idx[:-1]).total_seconds().to_numpy() if len(idx) > 1 else np.array([])
    back = steps < 0
    if back.any():
        reasons.append(f"dates out of order at {idx[int(np.argmax(back)) + 1].date()}")
    elif len(steps):
        days = steps / 86_400.0
        wide = days > limit
        if wide.any():
            i = int(np.argmax(wide))
            reasons.append(f"gap of {days[i]:.0f} days from {idx[i].date()} to {idx[i + 1].date()} "
                           f"(limit {limit} for {asset_class})")
    return reasons


def require_valid_bars(df: pd.DataFrame, asset_class: str, label: str,
                       max_gap_days: int | None = None) -> pd.DataFrame:
    """Return ``df`` unchanged if ``bar_problems`` finds nothing, else raise ``BarValidationError``."""
    reasons = bar_problems(df, asset_class, max_gap_days)
    if reasons:
        raise BarValidationError(label, reasons)
    return df


def session_close_utc(trade_date: date, asset_class: str) -> datetime:
    """The UTC instant at which the daily bar labelled ``trade_date`` closes (module docstring)."""
    if asset_class not in MAX_GAP_DAYS:
        raise ValueError(f"unknown asset class {asset_class!r}")
    clock = FX_ROLL_NY if asset_class == "fx" else EQUITY_CLOSE_NY
    return datetime.combine(trade_date, clock, NEW_YORK).astimezone(ZoneInfo("UTC"))


def common_sessions(frames: dict[str, pd.DataFrame]) -> pd.DatetimeIndex:
    """Trade dates on which every sleeve has a bar: the dates a multi-sleeve book can rebalance."""
    if not frames:
        return pd.DatetimeIndex([])
    out = None
    for df in frames.values():
        idx = pd.DatetimeIndex(df.index).normalize()
        out = idx if out is None else out.intersection(idx)
    return out.sort_values()


def survivorship_statement(symbol: str, first_bar: date | None, design_start: date) -> str:
    """One table-row note on whether ``symbol`` existed when the design period began.

    A name whose first bar is after ``design_start`` was chosen with knowledge that it
    later listed and survived, so its row says so; a name with no bars at all is reported
    as absent rather than silently dropped.
    """
    if first_bar is None:
        return f"{symbol}: no bars from the provider; absent from the table, not evidence"
    if first_bar <= design_start:
        return f"{symbol}: trading at design start {design_start} (first bar {first_bar})"
    return (f"{symbol}: listed {first_bar}, after design start {design_start}; "
            f"chosen with hindsight, survivorship bias possible")


def cap_short_notional(weight: float, cap: float | None) -> float:
    """Clamp a signed weight so a short is never larger than ``cap`` of capital (None = no cap).

    Borrow availability and recall are not modelled; this cap is the documented limit on
    how much of the book can depend on borrow that may not exist.
    """
    if cap is None or weight >= 0:
        return weight
    if not math.isfinite(cap) or cap < 0:
        raise ValueError(f"short notional cap must be a finite non-negative number, got {cap}")
    return max(weight, -cap)


def write_ledger_csv(frame: pd.DataFrame, path: Path | str) -> None:
    """Write a ledger with every float as its shortest round-trip ``repr``, so read-back is exact."""
    frame.to_csv(path, float_format=lambda x: repr(float(x)))


def read_ledger_csv(path: Path | str) -> pd.DataFrame:
    """Read a ledger back bit for bit (pandas' default float parser can lose the last digit)."""
    return pd.read_csv(path, index_col=0, parse_dates=True, float_precision="round_trip")


def ledgers_match(a: pd.DataFrame, b: pd.DataFrame, tol: float = 1e-12) -> bool:
    """True when two ledgers have the same dates and columns and every cell agrees within ``tol``.

    NaN matches NaN. Compare with this, never with ``==``: a recomputation on another
    machine or backend may differ in the last bits.
    """
    if not a.index.equals(b.index) or list(a.columns) != list(b.columns):
        return False
    x, y = a.to_numpy(float), b.to_numpy(float)
    both_nan = np.isnan(x) & np.isnan(y)
    return bool(np.all(both_nan | (np.abs(x - y) <= tol)))
