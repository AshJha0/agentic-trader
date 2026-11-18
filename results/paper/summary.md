# Forward paper-trading record: 2026-09-29 -> 2026-11-16 (36 sessions, frozen 2026-09-29, rules v0.8.0)

| book / stream | cumulative return % | Sharpe (excess, 260/yr) | vs control: Sharpe difference [95% CI] p |
|:--|--:|--:|:--|
| core15/AgenticTrader | -0.69 | -1.43 | (interval after 60 sessions) |
| core15/B&H vol-target | -1.22 | -1.99 |  |
| core15/Buy&Hold | -3.06 | -2.35 |  |
| etf11/B&H vol-target | -0.66 | -1.46 |  |
| etf11/Buy&Hold | -0.90 | -1.59 |  |
| etf11/TSMOM(12-1) | -0.75 | -1.94 | (interval after 60 sessions) |
| fx15/B&H vol-target | -0.51 | -4.74 |  |
| fx15/Carry | +0.95 | 4.14 | (interval after 60 sessions) |
| fx15/TSMOM(12-1) | +0.96 | 1.36 | (interval after 60 sessions) |

No decision before session 3600 (pre-registered, docs/evaluation/v09_preregistration.md, amendment of 2026-09-29): intervals printed before it are descriptive. Sessions so far: 36.

The ledger is append-only: sessions are added from each run's recomputation and never rewritten; differences between a recomputation and the ledger are logged in revisions.csv and runs.jsonl.

**Same-day revision:** 3 cell(s) of 2026-11-13, the session the previous run recorded, moved in this run (columns: etf11/B&H vol-target, etf11/Buy&Hold, etf11/TSMOM(12-1)). The bar was probably not final when it was fetched; the ledger keeps the first value, see revisions.csv.
