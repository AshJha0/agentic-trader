# Forward paper-trading record: 2026-09-29 -> 2026-11-18 (38 sessions, frozen 2026-09-29, rules v0.8.0)

| book / stream | cumulative return % | Sharpe (excess, 260/yr) | vs control: Sharpe difference [95% CI] p |
|:--|--:|--:|:--|
| core15/AgenticTrader | -1.06 | -1.85 | (interval after 60 sessions) |
| core15/B&H vol-target | -1.79 | -2.59 |  |
| core15/Buy&Hold | -4.15 | -2.99 |  |
| etf11/B&H vol-target | -1.05 | -1.92 |  |
| etf11/Buy&Hold | -1.54 | -2.27 |  |
| etf11/TSMOM(12-1) | -1.34 | -2.75 | (interval after 60 sessions) |
| fx15/B&H vol-target | -0.55 | -4.93 |  |
| fx15/Carry | +0.97 | 3.90 | (interval after 60 sessions) |
| fx15/TSMOM(12-1) | +0.94 | 1.14 | (interval after 60 sessions) |

No decision before session 3600 (pre-registered, docs/evaluation/v09_preregistration.md, amendment of 2026-09-29): intervals printed before it are descriptive. Sessions so far: 38.

The ledger is append-only: sessions are added from each run's recomputation and never rewritten; differences between a recomputation and the ledger are logged in revisions.csv and runs.jsonl.

**Same-day revision:** 6 cell(s) of 2026-11-17, the session the previous run recorded, moved in this run (columns: core15/AgenticTrader, core15/B&H vol-target, core15/Buy&Hold, etf11/B&H vol-target, etf11/Buy&Hold, etf11/TSMOM(12-1)). The bar was probably not final when it was fetched; the ledger keeps the first value, see revisions.csv.
