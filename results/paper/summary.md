# Forward paper-trading record: 2026-09-29 -> 2026-11-25 (43 sessions, frozen 2026-09-29, rules v0.8.0)

| book / stream | cumulative return % | Sharpe (excess, 260/yr) | vs control: Sharpe difference [95% CI] p |
|:--|--:|--:|:--|
| core15/AgenticTrader | -1.39 | -2.00 | (interval after 60 sessions) |
| core15/B&H vol-target | -2.40 | -2.58 |  |
| core15/Buy&Hold | -5.36 | -2.33 |  |
| etf11/B&H vol-target | -0.76 | -1.46 |  |
| etf11/Buy&Hold | -1.39 | -1.78 |  |
| etf11/TSMOM(12-1) | -1.67 | -2.84 | (interval after 60 sessions) |
| fx15/B&H vol-target | -0.74 | -5.57 |  |
| fx15/Carry | +0.85 | 1.53 | (interval after 60 sessions) |
| fx15/TSMOM(12-1) | +0.49 | -0.44 | (interval after 60 sessions) |

No decision before session 3600 (pre-registered, docs/evaluation/v09_preregistration.md, amendment of 2026-09-29): intervals printed before it are descriptive. Sessions so far: 43.

The ledger is append-only: sessions are added from each run's recomputation and never rewritten; differences between a recomputation and the ledger are logged in revisions.csv and runs.jsonl.

**Same-day revision:** 3 cell(s) of 2026-11-24, the session the previous run recorded, moved in this run (columns: etf11/B&H vol-target, etf11/Buy&Hold, etf11/TSMOM(12-1)). The bar was probably not final when it was fetched; the ledger keeps the first value, see revisions.csv.
