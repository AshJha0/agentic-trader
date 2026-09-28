"""v0.9 phase 3: combine the return streams with risk budgets, at the return level.

Reads the per-strategy daily portfolio returns written by ``scripts/measure_v09.py`` and
builds books from fully costed streams (each stream is a risk-parity portfolio of sleeves
running one strategy):

* ``beta``       ``etf11_rp``: ``B&H vol-target``  (the multi-asset base)
* ``trend_etf``  ``etf11_rp``: ``TSMOM(12-1)``
* ``trend_fx``   ``fx15_rp``:  ``TSMOM(12-1)``
* ``carry``      ``fx15_rp``:  ``Carry``

A book is ``sum_i a_i * r_i`` with capital shares ``a`` (sum 1, each >= 0) from risk parity
over the streams' trailing ``window``-day covariance, re-estimated every ``every`` days
from returns up to the previous day (no look-ahead) and held in between; the first
``window`` days use equal shares. Excess returns over the credited ``rf`` are what the
Sharpe is taken on, so the comparison is leverage-neutral (idle capital earns the bill).
The optional drawdown overlay halves every share while the book's trailing peak-to-trough
drawdown over the last ``dd_window`` days exceeds ``dd_limit``.

Streams on different calendars (FX trades on some US holidays) are aligned on the union of
dates; a stream with no bar that day contributes 0. Annualisation is 260 periods per year,
the portfolio convention when FX is present. Every book is compared with the base
(``beta``) by the paired circular block bootstrap over days (block 10, 5000 resamples).

Writes ``results/v09/combine.{md,json}``.

    .venv\\Scripts\\python.exe scripts/combine_v09.py [--in results/v09]
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentic_trader.portfolio import estimate_cov, risk_parity_weights  # noqa: E402
from agentic_trader.provenance import provenance  # noqa: E402
from agentic_trader.stats import paired_sharpe_block_bootstrap, sharpe_stats  # noqa: E402

PPY = 260.0
STREAMS = {"beta": ("etf11_rp", "B&H vol-target"), "trend_etf": ("etf11_rp", "TSMOM(12-1)"),
           "trend_fx": ("fx15_rp", "TSMOM(12-1)"), "carry": ("fx15_rp", "Carry")}
BOOKS = {
    "beta (base)": ["beta"],
    "beta + trend_etf": ["beta", "trend_etf"],
    "beta + carry": ["beta", "carry"],
    "beta + trend_etf + carry": ["beta", "trend_etf", "carry"],
    "all four": ["beta", "trend_etf", "trend_fx", "carry"],
    "trend + carry (no beta)": ["trend_etf", "trend_fx", "carry"],
}


def load_streams(inp: Path) -> tuple[pd.DataFrame, pd.Series]:
    frames, rfs = {}, []
    for name, (run, col) in STREAMS.items():
        f = pd.read_csv(inp / f"{run}.csv", index_col=0, parse_dates=True)
        frames[name] = f[col]
        rfs.append(f["rf"])
    streams = pd.DataFrame(frames).sort_index()
    rf = pd.concat(rfs, axis=1, sort=True).max(axis=1).reindex(streams.index).ffill()   # one bill rate
    return streams.fillna(0.0), rf


def excess(r: pd.DataFrame | pd.Series, rf: pd.Series) -> np.ndarray:
    x = np.asarray(r, dtype=float)[1:]
    f = np.nan_to_num(rf.to_numpy(float)[:-1]) / PPY
    return x - (f[:, None] if x.ndim == 2 else f)


def risk_parity_shares(ex: np.ndarray, window: int, every: int) -> np.ndarray:
    """Capital shares per day (T, k): risk parity on the trailing window of excess returns,
    re-estimated every ``every`` days from data up to the previous day, equal until ``window``."""
    T, k = ex.shape
    shares = np.full((T, k), 1.0 / k)
    current = np.full(k, 1.0 / k)
    for t in range(T):
        if t >= window and (t - window) % every == 0:
            hist = ex[t - window:t]
            try:
                w = risk_parity_weights(estimate_cov(hist))
                if np.all(np.isfinite(w)) and w.sum() > 0:
                    current = w / w.sum()
            except ValueError:
                pass
        shares[t] = current
    return shares


def drawdown_overlay(book: np.ndarray, dd_window: int, dd_limit: float) -> np.ndarray:
    """1 or 0.5 per day: half size after the trailing drawdown (known at the previous close)
    exceeded ``dd_limit`` inside the last ``dd_window`` days."""
    scale = np.ones_like(book)
    eq = np.cumprod(1.0 + book)
    for t in range(1, book.size):
        lo = max(0, t - dd_window)
        seg = eq[lo:t]
        dd = 1.0 - seg[-1] / seg.max()
        scale[t] = 0.5 if dd > dd_limit else 1.0
    return scale


def metrics(ex: np.ndarray) -> dict:
    s = sharpe_stats(ex, PPY)
    eq = np.cumprod(1.0 + ex)
    mdd = float((1.0 - eq / np.maximum.accumulate(eq)).max())
    return {"sharpe": s.sharpe_annual, "t": s.t_stat, "vol_pct": s.std * np.sqrt(PPY) * 100,
            "excess_return_annual_pct": s.mean * PPY * 100, "mdd_pct": mdd * 100, "n": s.n}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--in", dest="inp", default=str(ROOT / "results" / "v09"))
    ap.add_argument("--window", type=int, default=120)
    ap.add_argument("--every", type=int, default=5)
    ap.add_argument("--dd-window", type=int, default=60)
    ap.add_argument("--dd-limit", type=float, default=0.10)
    a = ap.parse_args(argv)
    inp = Path(a.inp)
    streams, rf = load_streams(inp)
    ex = excess(streams, rf)                                       # (T-1, k) excess returns
    names = list(streams.columns)
    base = ex[:, names.index("beta")]
    out = {"streams": {n: metrics(ex[:, i]) for i, n in enumerate(names)},
           "correlation": pd.DataFrame(np.corrcoef(ex.T), index=names, columns=names).round(3).to_dict(),
           "books": {}, "settings": vars(a) | {"ppy": PPY}, "provenance": provenance()}
    for book, members in BOOKS.items():
        cols = [names.index(m) for m in members]
        sub = ex[:, cols]
        shares = risk_parity_shares(sub, a.window, a.every) if len(cols) > 1 else np.ones((sub.shape[0], 1))
        r = (sub * shares).sum(axis=1)
        entry = {"members": members, "mean_shares": dict(zip(members, shares.mean(axis=0).round(3).tolist())),
                 "metrics": metrics(r), "vs_base": asdict(paired_sharpe_block_bootstrap(r, base, PPY, block=10, n_boot=5000))}
        sc = drawdown_overlay(r, a.dd_window, a.dd_limit)
        ro = r * sc
        entry["with_drawdown_overlay"] = {"metrics": metrics(ro), "share_of_days_halved": float((sc < 1).mean()),
                                          "vs_base": asdict(paired_sharpe_block_bootstrap(ro, base, PPY, block=10, n_boot=5000))}
        out["books"][book] = entry
    (inp / "combine.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    period = f"{streams.index[0].date()} -> {streams.index[-1].date()}"
    lines = [f"# v0.9 phase 3: strategy combination, {period}, 260 periods/year\n",
             "## streams (excess returns)\n", "| stream | Sharpe | t | vol % | excess return %/yr | MDD % | n |", "|:--|--:|--:|--:|--:|--:|--:|"]
    for n, m in out["streams"].items():
        lines.append(f"| {n} | {m['sharpe']:.2f} | {m['t']:.2f} | {m['vol_pct']:.2f} | {m['excess_return_annual_pct']:+.2f} | {m['mdd_pct']:.2f} | {m['n']} |")
    lines += ["", "## correlation of daily excess returns\n", "| | " + " | ".join(names) + " |", "|:--|" + "--:|" * len(names)]
    for n in names:
        lines.append(f"| {n} | " + " | ".join(f"{out['correlation'][m][n]:.2f}" for m in names) + " |")
    lines += ["", "## books (risk parity across streams; block-bootstrap Sharpe difference vs the base)\n",
              "| book | mean shares | Sharpe | vol % | MDD % | Sharpe − base [95% CI] p | with DD overlay: Sharpe / MDD % / days halved | overlay − base [95% CI] p |",
              "|:--|:--|--:|--:|--:|:--|:--|:--|"]
    for book, e in out["books"].items():
        m, d, o, od = e["metrics"], e["vs_base"], e["with_drawdown_overlay"]["metrics"], e["with_drawdown_overlay"]["vs_base"]
        lines.append(f"| {book} | {e['mean_shares']} | {m['sharpe']:.2f} | {m['vol_pct']:.2f} | {m['mdd_pct']:.2f} "
                     f"| {d['diff']:+.2f} [{d['ci_low']:+.2f}, {d['ci_high']:+.2f}] p {d['p_value']:.3f} "
                     f"| {o['sharpe']:.2f} / {o['mdd_pct']:.2f} / {e['with_drawdown_overlay']['share_of_days_halved']:.0%} "
                     f"| {od['diff']:+.2f} [{od['ci_low']:+.2f}, {od['ci_high']:+.2f}] p {od['p_value']:.3f} |")
    lines.append("")
    text = "\n".join(lines) + "\n"
    (inp / "combine.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
