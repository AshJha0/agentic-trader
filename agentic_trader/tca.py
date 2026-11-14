"""Predicted-versus-realised transaction cost per order (v0.17, review item C5).

Plain idea. A desk's first live-readiness number is slippage: what each order was expected
to cost and what it did cost. Here "expected" is the backtester's cost for the weight change
it intended (``|dw| * unit_cost + K * |dw| ** 1.5``, the same formula ``oms.fill_cost`` uses)
and "realised" is what the OMS shadow record booked: its fill cost plus the price difference
between fill and arrival, signed so that positive is worse for us.

Formal statement. For an order with side ``s`` (+1 buy, -1 sell), intended quantity ``Q``,
filled quantity ``q``, arrival price ``P0``, average fill price ``P`` and booked fees ``F``:

    realised = q * s * (P - P0) + F               (account currency)
    predicted = capital * (|dw| * u + K * |dw|^1.5) with dw = Q * P0 / capital
    slippage_bp = 1e4 * (realised - predicted * q / Q) / (q * P0)

so a partial fill is compared with the prediction for the part that filled; the unfilled part
is reported separately as ``fill_ratio``.

Worked example. Buy 100 at arrival 50, filled 100 at 50.02, fees 1.00, predicted 1.50:
realised ``100 * 0.02 + 1 = 3.00``; slippage ``1e4 * (3.00 - 1.50) / 5000 = 3 bp``.

Today the OMS fills at the reference close, so its price term is zero and the residual
measures only rounding and participation; once real (or more realistic) fills exist the same
report measures the model error. Evidence class: operational, simulated fills.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


def predicted_cost(notional: float, capital: float, unit_cost: float, impact_k: float | None = None) -> float:
    """The backtester's entry cost in account currency for a trade of ``notional``."""
    dw = abs(notional) / capital
    return capital * (dw * unit_cost + (impact_k or 0.0) * dw**1.5)


def tca_rows(orders: Iterable, arrival: dict[str, float], predicted: dict[str, float]) -> pd.DataFrame:
    """One row per order. ``orders`` are ``oms.Order`` objects (or anything with
    ``client_order_id, side, quantity, fills[ .quantity, .price, .cost ]``); ``arrival`` and
    ``predicted`` map ``client_order_id`` to the arrival price and the predicted cost of the full
    intended quantity. Orders with no fill are kept with NaN costs and fill ratio 0."""
    rows = []
    for o in orders:
        cid = o.client_order_id
        s = 1.0 if o.side == "buy" else -1.0
        q = float(sum(f.quantity for f in o.fills))
        p0 = float(arrival[cid])
        pred_full = float(predicted[cid])
        if q > 0:
            vwap = float(sum(f.quantity * f.price for f in o.fills)) / q
            fees = float(sum(f.cost for f in o.fills))
            realised = q * s * (vwap - p0) + fees
            pred = pred_full * q / float(o.quantity)
            slip = 1e4 * (realised - pred) / (q * p0)
        else:
            vwap = fees = realised = pred = slip = float("nan")
        rows.append(
            {
                "client_order_id": cid,
                "side": o.side,
                "quantity": float(o.quantity),
                "filled": q,
                "fill_ratio": q / float(o.quantity) if o.quantity else float("nan"),
                "arrival": p0,
                "avg_fill": vwap,
                "fees": fees,
                "realised_cost": realised,
                "predicted_cost": pred,
                "slippage_bp": slip,
            }
        )
    return pd.DataFrame(rows)


def tca_summary(rows: pd.DataFrame) -> dict[str, float]:
    """Notional-weighted mean slippage (bp), its mean absolute value, the share of orders worse
    than predicted, and the mean fill ratio."""
    f = rows.dropna(subset=["slippage_bp"])
    if f.empty:
        return {
            "orders": float(len(rows)),
            "filled": 0.0,
            "wmean_slippage_bp": float("nan"),
            "mean_abs_slippage_bp": float("nan"),
            "worse_than_predicted": float("nan"),
            "mean_fill_ratio": float(rows["fill_ratio"].mean()) if len(rows) else float("nan"),
        }
    w = f["filled"] * f["arrival"]
    return {
        "orders": float(len(rows)),
        "filled": float(len(f)),
        "wmean_slippage_bp": float(np.average(f["slippage_bp"], weights=w)),
        "mean_abs_slippage_bp": float(f["slippage_bp"].abs().mean()),
        "worse_than_predicted": float((f["slippage_bp"] > 1e-9).mean()),
        "mean_fill_ratio": float(rows["fill_ratio"].mean()),
    }
