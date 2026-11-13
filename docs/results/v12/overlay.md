> **FX re-run, 2026-11-13 (review D5 closed).** Every table on this page was re-measured from main
> 3f80a69, whose engine converts FX P&L to the USD account (the earlier tables booked a USD-base pair's
> return r where r / (1 + r) is due and left crosses unconverted). Source: `results/v12_fx_final_2009/overlay/overlay.md`. The re-run
> replaces the 2026-11-12 correction notice.
> The v0.12 period now starts 2009-10-01, not 2008-07-01: the bar check refuses the 2008 EUR/USD data gap inside the 400-day lookback, so the first scorable day moves forward. core15 is not on this page (it fails the bar check on META in 2012; it was not on the earlier page either).

# v0.12: the vol-targeted book as the core, the desk's tilt at size lam, on the longer design period

r(lam) = control + lam * (desk - control); lam 0 is `B&H vol-target`, lam 1 the desk. Excess-return Sharpe, 260 periods/year, paired block bootstrap over days. Chosen on the design period only.

## etf11_rp: 2009-10-01 -> 2021-12-31, a design period (no holdout is consulted), n = 3084 days

| lam | Sharpe | vol %/yr | cumulative return % | MDD % | Sharpe - control [95% CI] p | Sharpe - desk [95% CI] p |
|--:|--:|--:|--:|--:|:--|:--|
| 0.00 | 0.95 | 5.11 | 85.59 | 9.93 | +0.00 [+0.00, +0.00] p 1.000 | +0.03 [-0.13, +0.21] p 0.690 |
| 0.25 | 0.95 | 4.77 | 79.05 | 9.40 | -0.00 [-0.03, +0.03] p 0.994 | +0.03 [-0.10, +0.17] p 0.616 |
| 0.50 | 0.94 | 4.46 | 72.70 | 8.87 | -0.00 [-0.08, +0.07] p 0.909 | +0.03 [-0.07, +0.13] p 0.542 |
| 0.75 | 0.93 | 4.17 | 66.53 | 8.35 | -0.02 [-0.13, +0.10] p 0.805 | +0.02 [-0.03, +0.07] p 0.460 |
| 1.00 | 0.91 | 3.91 | 60.55 | 7.84 | -0.03 [-0.21, +0.13] p 0.690 | +0.00 [-0.00, +0.00] p 1.000 |

## fx15_rp: 2009-10-01 -> 2021-12-31, a design period (no holdout is consulted), n = 3195 days

| lam | Sharpe | vol %/yr | cumulative return % | MDD % | Sharpe - control [95% CI] p | Sharpe - desk [95% CI] p |
|--:|--:|--:|--:|--:|:--|:--|
| 0.00 | -0.44 | 2.68 | -8.37 | 15.36 | +0.00 [+0.00, +0.00] p 1.000 | -0.29 [-0.91, +0.32] p 0.322 |
| 0.25 | -0.42 | 2.33 | -6.16 | 12.80 | +0.01 [-0.15, +0.18] p 0.857 | -0.28 [-0.76, +0.19] p 0.234 |
| 0.50 | -0.36 | 2.25 | -3.98 | 10.39 | +0.08 [-0.27, +0.46] p 0.622 | -0.21 [-0.50, +0.08] p 0.152 |
| 0.75 | -0.25 | 2.48 | -1.84 | 10.24 | +0.19 [-0.32, +0.73] p 0.436 | -0.10 [-0.22, +0.03] p 0.101 |
| 1.00 | -0.15 | 2.94 | 0.26 | 11.07 | +0.29 [-0.32, +0.91] p 0.322 | +0.00 [-0.00, +0.00] p 1.000 |

## all26_rp: 2009-10-01 -> 2021-12-31, a design period (no holdout is consulted), n = 3196 days

| lam | Sharpe | vol %/yr | cumulative return % | MDD % | Sharpe - control [95% CI] p | Sharpe - desk [95% CI] p |
|--:|--:|--:|--:|--:|:--|:--|
| 0.00 | 0.19 | 2.48 | 12.26 | 8.86 | +0.00 [+0.00, +0.00] p 1.000 | -0.08 [-0.52, +0.39] p 0.731 |
| 0.25 | 0.23 | 2.27 | 12.98 | 7.94 | +0.04 [-0.07, +0.17] p 0.495 | -0.04 [-0.38, +0.35] p 0.837 |
| 0.50 | 0.26 | 2.19 | 13.67 | 7.61 | +0.07 [-0.17, +0.32] p 0.559 | -0.01 [-0.24, +0.26] p 0.948 |
| 0.75 | 0.27 | 2.26 | 14.31 | 7.53 | +0.08 [-0.28, +0.44] p 0.647 | +0.00 [-0.11, +0.14] p 0.959 |
| 1.00 | 0.27 | 2.46 | 14.91 | 7.52 | +0.08 [-0.39, +0.52] p 0.731 | +0.00 [-0.00, +0.00] p 1.000 |

