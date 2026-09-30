# Change 1: the vol-targeted book as the core, the desk's tilt as a sized overlay

Follows [v09_research.md](v09_research.md). Every number below is copied from
`results/v09/overlay.md`, written by `scripts/overlay_v09.py` from the v0.8 portfolio return
files (provenance in `results/v09/overlay.json`).

**Verdict, stated before any adoption: the design period cannot tell the sizes apart, so
nothing is adopted.** Every size from 0 (the mechanical control) to 1 (the desk) lies within a
few hundredths of a Sharpe point of the others, with intervals that straddle zero. The holdout,
printed as a report and not as a basis for the choice, ranks the sizes monotonically in favour
of the smaller tilt, which is what the attribution (no alpha, negative on the holdout) predicts;
that is consistent evidence, not selection evidence, because the holdout was spent in v0.8.

The blend takes the daily returns of two fully costed streams, so trades that would net between
the control and the desk are costed twice: the blend's costs are an upper bound and its Sharpe
conservative. The grid has five sizes and all count as trials.

The decision between a large and a small tilt is therefore made by the forward record, which
already records both endpoints (`core15/AgenticTrader` and `core15/B&H vol-target` in
`results/paper/ledger.csv`); any size in between is computed from those two columns with the same
blend, with no new machinery and no new data.


r(lam) = control + lam * (desk - control); lam 0 is `B&H vol-target`, lam 1 the desk. Excess-return Sharpe, 260 periods/year, paired block bootstrap over days. Chosen on the design period only.

### design: design (the choice basis), n = 1564 days

| lam | Sharpe | vol %/yr | cumulative return % | MDD % | Sharpe - control [95% CI] p | Sharpe - desk [95% CI] p |
|--:|--:|--:|--:|--:|:--|:--|
| 0.00 | 1.43 | 7.53 | 98.58 | 9.45 | +0.00 [+0.00, +0.00] p 1.000 | +0.03 [-0.23, +0.28] p 0.898 |
| 0.25 | 1.44 | 7.41 | 97.40 | 9.36 | +0.01 [-0.05, +0.07] p 0.726 | +0.04 [-0.16, +0.22] p 0.774 |
| 0.50 | 1.43 | 7.34 | 96.19 | 9.34 | +0.01 [-0.11, +0.13] p 0.852 | +0.03 [-0.10, +0.16] p 0.656 |
| 0.75 | 1.42 | 7.33 | 94.94 | 9.69 | -0.00 [-0.19, +0.19] p 1.000 | +0.02 [-0.05, +0.09] p 0.549 |
| 1.00 | 1.40 | 7.37 | 93.64 | 10.17 | -0.03 [-0.28, +0.23] p 0.898 | +0.00 [-0.00, +0.00] p 1.000 |

### holdout: holdout (a report, not a basis for the choice), n = 1167 days

| lam | Sharpe | vol %/yr | cumulative return % | MDD % | Sharpe - control [95% CI] p | Sharpe - desk [95% CI] p |
|--:|--:|--:|--:|--:|:--|:--|
| 0.00 | 0.99 | 7.01 | 61.48 | 9.17 | +0.00 [+0.00, +0.00] p 1.000 | +0.19 [-0.16, +0.53] p 0.297 |
| 0.25 | 0.96 | 6.85 | 58.74 | 8.26 | -0.03 [-0.11, +0.05] p 0.425 | +0.16 [-0.11, +0.42] p 0.258 |
| 0.50 | 0.91 | 6.74 | 56.01 | 7.48 | -0.08 [-0.24, +0.09] p 0.375 | +0.11 [-0.07, +0.29] p 0.229 |
| 0.75 | 0.86 | 6.69 | 53.30 | 7.61 | -0.13 [-0.38, +0.13] p 0.332 | +0.06 [-0.03, +0.15] p 0.204 |
| 1.00 | 0.80 | 6.71 | 50.62 | 7.80 | -0.19 [-0.53, +0.16] p 0.297 | +0.00 [-0.00, +0.00] p 1.000 |

