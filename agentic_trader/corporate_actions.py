"""Ex-date-aware corporate actions for a share-quantity book (v0.17, review item C3).

Plain idea. The paper OMS holds positions in shares. On a split's ex-date a holder of 10
shares of a 4-for-1 split owns 40 shares at a quarter of the price; on a dividend's ex-date
the holder of record is owed cash (a short owes it). If the book ignores this, the day after
a split reconciliation shows a break of 30 shares and a fake 75 % loss.

Formal statement. For each symbol, actions with ex-date ``d`` in ``(after, through]`` apply
in date order: a split of ratio ``k`` maps ``q -> q * k`` (fractional remainders, from reverse
splits, are paid out as cash in lieu at the given price when ``whole_shares``); a cash
dividend ``D`` per share books ``q * D`` to cash, payable on the pay date (taken equal to the
ex-date here; the record/pay lag is a settlement detail, not a P&L one).

Worked example. 10 shares, split 4.0 on 2024-06-10, dividend 0.25 on 2024-06-12: after both,
40 shares and cash +10.00 (``40 * 0.25``; the dividend applies to the post-split count
because its ex-date is later).

Hook. ``oms.OMS`` keeps ``positions`` (shares) and ``cash_flows``; the session runner applies
``apply_actions`` to ``oms.positions`` before submitting the session's orders and appends
``cash_flow_rows`` to ``oms.cash_flows``. That call sits in the paper-session code, which is
another lane's file in v0.17; the one-line hook is in docs/review/v017_notes/L8_quant_rest.md.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class ActionEvent:
    symbol: str
    ex_date: date
    kind: str          # "split" | "dividend" | "cash_in_lieu"
    before: float      # shares before
    after: float       # shares after
    cash: float        # cash booked (account currency, positive = received)


def _actions_in(actions: pd.DataFrame, after: date | None, through: date) -> pd.DataFrame:
    idx = pd.to_datetime(actions.index)
    keep = idx <= pd.Timestamp(through)
    if after is not None:
        keep &= idx > pd.Timestamp(after)
    return actions.loc[keep].sort_index()


def apply_actions(positions: dict[str, float], actions: dict[str, pd.DataFrame], through: date,
                  after: date | None = None, prices: dict[str, float] | None = None,
                  whole_shares: bool = True) -> tuple[dict[str, float], float, list[ActionEvent]]:
    """Apply every action with ex-date in ``(after, through]`` to ``positions`` (shares).

    ``actions[sym]`` is indexed by ex-date with optional columns ``Split`` (ratio; 0 or 1 = no
    split; 4.0 = 4-for-1, 0.1 = 1-for-10) and ``Dividend`` (cash per share). ``prices[sym]``
    (the post-action price) values any fractional remainder paid as cash in lieu; without it
    a fractional remainder is refused rather than silently dropped.

    Returns new positions, the cash total and an event list (the audit trail)."""
    out = dict(positions)
    cash = 0.0
    events: list[ActionEvent] = []
    for sym, qty in positions.items():
        tbl = actions.get(sym)
        if tbl is None or tbl.empty or qty == 0:
            continue
        q = float(qty)
        sub = _actions_in(tbl, after, through)
        for ts, row in zip(pd.to_datetime(sub.index), sub.to_dict("records")):
            d = pd.Timestamp(ts).date()
            k = float(row.get("Split", 0.0) or 0.0)
            if k > 0 and k != 1.0:
                if not math.isfinite(k):
                    raise ValueError(f"{sym}: split ratio {k} on {d} is not finite")
                new = q * k
                if whole_shares:
                    whole = float(math.trunc(round(new, 9)))
                    frac = new - whole
                    if abs(frac) > 1e-9:
                        px = (prices or {}).get(sym)
                        if px is None:
                            raise ValueError(f"{sym}: split on {d} leaves {frac:g} fractional shares "
                                             "and no price for cash in lieu")
                        cash += frac * px
                        events.append(ActionEvent(sym, d, "cash_in_lieu", new, whole, frac * px))
                    new = whole
                events.append(ActionEvent(sym, d, "split", q, new, 0.0))
                q = new
            div = float(row.get("Dividend", 0.0) or 0.0)
            if div != 0.0 and math.isfinite(div):
                amt = q * div
                cash += amt
                events.append(ActionEvent(sym, d, "dividend", q, q, amt))
        out[sym] = q
    return out, cash, events


def cash_flow_rows(events: list[ActionEvent], currency: str = "USD") -> list[dict]:
    """``oms.OMS.cash_flows``-shaped rows for the cash an action list booked."""
    return [{"currency": currency, "amount": e.cash, "settle_date": e.ex_date,
             "client_order_id": f"corp-{e.kind}-{e.symbol}-{e.ex_date.isoformat()}"}
            for e in events if e.cash != 0.0]
