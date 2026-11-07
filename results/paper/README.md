# Forward paper-trading record

Published 2026-11-07. Written by `scripts/paper_trade_v09.py`, run daily at 07:30 UK time on the owner's machine. Paper only: no orders, no capital.

| File | What it holds |
|---|---|
| `ledger.csv` | Daily returns of each frozen book (rules v0.8.0, frozen 2026-09-29), fully costed as in the walk-forward. Append-only: a session is added once and never rewritten. |
| `revisions.csv` | Every value where a later recomputation differs from the ledger: run time, as-of date, session, column, old and new value. |
| `runs.jsonl` | One line per run (the local Python path in `executable` is masked for publication): run time, as-of date, sessions appended, data source and the largest revision per column. |
| `ledger_recomputed.csv` | The latest full recomputation, for comparison with the ledger. |
| `exposure.csv` | Per book/stream and session: gross exposure held (sum of abs weight x allocation), turnover traded, and trading cost charged (turnover x the sleeve's cost_bps + slippage_bps), all as fractions of book capital. Append-only like the ledger. |
| `summary.md` | Cumulative return and Sharpe per book; intervals start at 60 sessions. |

**Data vintage.** Prices come from Yahoo Finance and are revised after the fact, so a recomputation can differ from the ledger. By 2026-11-07 `revisions.csv` held 1,232 logged differences across all runs, 6 of them a session that went missing in a recomputation. The largest numeric revision is 0.08 percentage points of one day's return. The latest run differed from the ledger in 141 cells and one dropped session.

**Gap.** The job failed from about 2026-10-31 to 2026-11-06 because its Python environment pointed at a missing install. It was rebuilt on 2026-11-07, and that run appended 10 sessions (2026-10-26 to 2026-11-06) recomputed from data available on 2026-11-07, not recorded on their own days (`runs.jsonl`, `appended: 10`).

**Exposure and cost.** Recorded in `exposure.csv` from 2026-11-07. Its first write covers every session from 2026-09-29, recomputed on 2026-11-07, so those rows were not recorded on their own days. Cost is the linear charge the backtest applies (commission plus slippage, in basis points of turnover); market impact is off in the paper configuration (impact_coeff 0). Borrow on shorts (1% a year for equities) and FX carry are charged in the returns but are not in this cost column. The file has one row fewer than the ledger, because the latest recompute dropped one session the ledger keeps.

**Reading it.** No decision before session 3600 (docs/evaluation/v09_preregistration.md). 30 sessions say nothing about edge.
