# Forward paper-trading record: 2026-09-29 -> 2026-11-17 (37 sessions, frozen 2026-09-29, rules v0.8.0)

| book / stream | cumulative return % | Sharpe (excess, 260/yr) | vs control: Sharpe difference [95% CI] p |
|:--|--:|--:|:--|
| core15/AgenticTrader | -0.89 | -1.66 | (interval after 60 sessions) |
| core15/B&H vol-target | -1.59 | -2.38 |  |
| core15/Buy&Hold | -3.76 | -2.77 |  |
| etf11/B&H vol-target | -0.88 | -1.72 |  |
| etf11/Buy&Hold | -1.22 | -1.94 |  |
| etf11/TSMOM(12-1) | -1.00 | -2.30 | (interval after 60 sessions) |
| fx15/B&H vol-target | -0.58 | -5.03 |  |
| fx15/Carry | +0.93 | 3.65 | (interval after 60 sessions) |
| fx15/TSMOM(12-1) | +0.85 | 0.91 | (interval after 60 sessions) |

No decision before session 3600 (pre-registered, docs/evaluation/v09_preregistration.md, amendment of 2026-09-29): intervals printed before it are descriptive. Sessions so far: 37.

The ledger is append-only: sessions are added from each run's recomputation and never rewritten; differences between a recomputation and the ledger are logged in revisions.csv and runs.jsonl.

**Same-day revision:** 4 cell(s) of 2026-11-16, the session the previous run recorded, moved in this run (columns: core15/AgenticTrader, etf11/B&H vol-target, etf11/Buy&Hold, etf11/TSMOM(12-1)). The bar was probably not final when it was fetched; the ledger keeps the first value, see revisions.csv.
