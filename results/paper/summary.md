# Forward paper-trading record: 2026-09-29 -> 2026-11-23 (41 sessions, frozen 2026-09-29, rules v0.8.0)

| book / stream | cumulative return % | Sharpe (excess, 260/yr) | vs control: Sharpe difference [95% CI] p |
|:--|--:|--:|:--|
| core15/AgenticTrader | -1.32 | -1.95 | (interval after 60 sessions) |
| core15/B&H vol-target | -2.36 | -2.59 |  |
| core15/Buy&Hold | -4.59 | -2.06 |  |
| etf11/B&H vol-target | -1.10 | -1.86 |  |
| etf11/Buy&Hold | -1.72 | -2.13 |  |
| etf11/TSMOM(12-1) | -1.85 | -3.12 | (interval after 60 sessions) |
| fx15/B&H vol-target | -0.65 | -5.30 |  |
| fx15/Carry | +0.85 | 1.89 | (interval after 60 sessions) |
| fx15/TSMOM(12-1) | +0.48 | -0.40 | (interval after 60 sessions) |

No decision before session 3600 (pre-registered, docs/evaluation/v09_preregistration.md, amendment of 2026-09-29): intervals printed before it are descriptive. Sessions so far: 41.

The ledger is append-only: sessions are added from each run's recomputation and never rewritten; differences between a recomputation and the ledger are logged in revisions.csv and runs.jsonl.

**Same-day revision:** 3 cell(s) of 2026-11-19, the session the previous run recorded, moved in this run (columns: etf11/B&H vol-target, etf11/Buy&Hold, etf11/TSMOM(12-1)). The bar was probably not final when it was fetched; the ledger keeps the first value, see revisions.csv.
