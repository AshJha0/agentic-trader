# v0.12: a longer design period, long/short trend across asset classes, and the vol-target core

Follows [v09_research.md](v09_research.md), [v010_overlay.md](v010_overlay.md) and
[v011_review.md](v011_review.md). This page is written by `scripts/render_v12_doc.py`; every
table is copied from `results/v12/` (kept under [docs/results/v12](../results/v12)). No number
on this page is typed.

**Outcome, stated first: nothing is adopted.** On the longer design period the long/short
multi-horizon trend stream does not beat the vol-target control on any run, no book built
from the streams beats the multi-asset base, and no size of the desk's tilt over the
vol-target core can be told apart from the control. For each of these candidates the
interval against the control includes zero. The tables are below so the reader can check that sentence.

## What was asked, and the rule set before measuring

The tier-2 review approved three steps, to be run in this order, on design data only:

1. **A longer design period.** `design_long` runs from 2008-07-01 to 2021-12-31, the earliest
   date at which the eleven ETFs of the multi-asset universe have a year of history. It ends
   where the old design period ends, so it contains no holdout or reserve day. It includes
   2008 and 2011, which the 2016 to 2021 period does not.
2. **Trend as the literature defines it.** `TSMOM(L/S)` is the average sign of the trailing
   1, 3 and 12 month return, long and short, at the vol-target size (Moskowitz, Ooi and
   Pedersen 2012). The v0.9 stream `TSMOM(12-1)` was long-only on equities and used one
   horizon. The signal is `quant.strat_tsmom`, in the C++ core with a numpy twin.
3. **The vol-target book as the core.** The desk's tilt is added at size `lam` over the
   control, `r(lam) = control + lam * (desk - control)`, on the longer period.

The adoption rule is the one the project has used since v0.9: a change is adopted only if
its design-period Sharpe difference against the run's own `B&H vol-target` control has a 95%
block-bootstrap interval above zero. The holdout and the reserve are spent and were not
consulted. Every variant printed here is registered in `evaluation.TRIALS` (version `v0.12`).

Two limits of this round. The 15-instrument core universe cannot be run from 2008 (one of
its stocks listed in 2012), so the overlay is measured on the ETF, FX and combined runs and
not on the core 15. And the desk's analysts see less before 2016: filings coverage is
thinner, so the desk's own rows on this period are not the v0.11 desk on its usual footing.

Conventions are those of [v09_research.md](v09_research.md): Sharpe on excess returns over
the credited bill, risk parity across sleeves from a 120-day covariance window with no
look-ahead, the paired circular block bootstrap over days (block 10, 5000 resamples). On the
ETF runs the `Carry` row is idle cash, not a carry measurement.


Provenance: `etf11_rp` at commit `4491e33` (clean tree), cpp backend; `etf11_equal` at commit `4491e33` (clean tree), cpp backend; `fx15_rp` at commit `4491e33` (clean tree), cpp backend; `all26_rp` at commit `4491e33` (clean tree), cpp backend.


## Step 1 and 2: the runs on the longer design period

#### portfolio table, etf11_rp: 11 sleeves, risk_parity, 2008-07-01 -> 2021-12-31, provenance 4491e33 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 62.13 | 3.65 | 4.07 | 0.78 | 2.86 | 7.49 | 0.49 | 72.33 |
| Buy&Hold | 114.18 | 5.81 | 6.61 | 0.81 | 2.98 | 15.71 | 0.37 | 100.00 |
| B&H vol-target | 94.97 | 5.07 | 5.26 | 0.87 | 3.21 | 9.84 | 0.52 | 93.96 |
| SMA(20/50) | 74.28 | 4.20 | 4.76 | 0.79 | 2.88 | 7.85 | 0.54 | 64.71 |
| MACD | 50.27 | 3.06 | 4.22 | 0.62 | 2.28 | 10.18 | 0.30 | 51.05 |
| KDJ+RSI | 47.60 | 2.93 | 4.93 | 0.51 | 1.87 | 12.76 | 0.23 | 37.50 |
| ZMR | 19.23 | 1.31 | 5.10 | 0.18 | 0.68 | 12.78 | 0.10 | 30.96 |
| TSMOM(12-1) | 65.63 | 3.81 | 4.64 | 0.72 | 2.65 | 7.59 | 0.50 | 70.19 |
| TSMOM(L/S) | 32.55 | 2.11 | 4.23 | 0.40 | 1.46 | 6.00 | 0.35 | 64.33 |
| Carry | 6.90 | 0.50 | 0.00 | 0.00 | 0.00 | 0.00 | 1387.79 | 0.00 |

#### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): etf11_rp

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | 0.78 | -0.10 [-0.26, +0.07] p=0.249 |
| Buy&Hold | 0.81 | -0.06 [-0.28, +0.15] p=0.633 |
| TSMOM(12-1) | 0.72 | -0.15 [-0.41, +0.12] p=0.260 |
| TSMOM(L/S) | 0.40 | -0.48 [-1.10, +0.13] p=0.129 |
| Carry | 0.00 | -0.87 [-1.45, -0.30] p=0.003 |
| SMA(20/50) | 0.79 | -0.09 [-0.44, +0.27] p=0.634 |
| MACD | 0.62 | -0.25 [-0.71, +0.19] p=0.259 |
| KDJ+RSI | 0.51 | -0.36 [-0.79, +0.07] p=0.100 |
| ZMR | 0.18 | -0.69 [-1.14, -0.24] p=0.003 |

#### portfolio table, etf11_equal: 11 sleeves, equal, 2008-07-01 -> 2021-12-31, provenance 4491e33 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 67.09 | 3.88 | 5.02 | 0.68 | 2.51 | 9.22 | 0.42 | 65.80 |
| Buy&Hold | 146.88 | 6.93 | 12.64 | 0.55 | 2.03 | 32.50 | 0.21 | 100.00 |
| B&H vol-target | 111.93 | 5.72 | 7.21 | 0.74 | 2.72 | 13.41 | 0.43 | 88.57 |
| SMA(20/50) | 91.47 | 4.93 | 7.01 | 0.65 | 2.39 | 12.78 | 0.39 | 62.81 |
| MACD | 61.85 | 3.63 | 7.54 | 0.45 | 1.64 | 20.13 | 0.18 | 51.55 |
| KDJ+RSI | 68.41 | 3.94 | 9.17 | 0.41 | 1.52 | 22.91 | 0.17 | 36.19 |
| ZMR | 37.15 | 2.37 | 9.54 | 0.24 | 0.89 | 22.53 | 0.11 | 31.63 |
| TSMOM(12-1) | 68.11 | 3.93 | 5.53 | 0.63 | 2.33 | 9.85 | 0.40 | 62.72 |
| TSMOM(L/S) | 22.16 | 1.49 | 5.02 | 0.22 | 0.82 | 6.56 | 0.23 | 60.41 |
| Carry | 6.90 | 0.50 | 0.00 | 0.00 | 0.00 | 0.00 | 1387.79 | 0.00 |

#### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): etf11_equal

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | 0.68 | -0.05 [-0.25, +0.14] p=0.576 |
| Buy&Hold | 0.55 | -0.19 [-0.44, +0.07] p=0.167 |
| TSMOM(12-1) | 0.63 | -0.10 [-0.40, +0.20] p=0.498 |
| TSMOM(L/S) | 0.22 | -0.52 [-1.20, +0.17] p=0.143 |
| Carry | 0.00 | -0.74 [-1.30, -0.20] p=0.007 |
| SMA(20/50) | 0.65 | -0.09 [-0.45, +0.28] p=0.648 |
| MACD | 0.45 | -0.29 [-0.77, +0.16] p=0.206 |
| KDJ+RSI | 0.41 | -0.33 [-0.74, +0.12] p=0.161 |
| ZMR | 0.24 | -0.50 [-0.92, -0.06] p=0.023 |

#### portfolio table, fx15_rp: 15 sleeves, risk_parity, 2008-07-01 -> 2021-12-31, provenance 4491e33 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | -2.95 | -0.22 | 2.98 | -0.22 | -0.83 | 11.46 | -0.02 | 62.64 |
| Buy&Hold | -2.16 | -0.16 | 2.75 | -0.22 | -0.83 | 12.27 | -0.01 | 97.24 |
| B&H vol-target | -3.26 | -0.24 | 2.64 | -0.27 | -0.98 | 14.08 | -0.02 | 96.94 |
| SMA(20/50) | 6.06 | 0.44 | 4.87 | 0.01 | 0.04 | 10.87 | 0.04 | 97.58 |
| MACD | -10.23 | -0.79 | 4.87 | -0.24 | -0.89 | 18.81 | -0.04 | 98.78 |
| KDJ+RSI | 44.25 | 2.74 | 4.76 | 0.49 | 1.80 | 9.66 | 0.28 | 101.34 |
| ZMR | 18.52 | 1.26 | 5.04 | 0.18 | 0.65 | 12.14 | 0.10 | 80.71 |
| TSMOM(12-1) | -10.47 | -0.81 | 4.43 | -0.27 | -1.01 | 19.47 | -0.04 | 96.86 |
| TSMOM(L/S) | -0.10 | -0.01 | 3.49 | -0.13 | -0.46 | 8.91 | -0.00 | 62.75 |
| Carry | 5.08 | 0.37 | 2.15 | -0.05 | -0.18 | 8.22 | 0.04 | 28.43 |

#### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): fx15_rp

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | -0.22 | +0.04 [-0.60, +0.64] p=0.914 |
| Buy&Hold | -0.22 | +0.04 [-0.10, +0.16] p=0.548 |
| TSMOM(12-1) | -0.27 | -0.01 [-0.76, +0.66] p=0.950 |
| TSMOM(L/S) | -0.13 | +0.14 [-0.60, +0.79] p=0.730 |
| Carry | -0.05 | +0.22 [-0.44, +0.85] p=0.524 |
| SMA(20/50) | 0.01 | +0.28 [-0.46, +0.92] p=0.457 |
| MACD | -0.24 | +0.03 [-0.71, +0.66] p=0.954 |
| KDJ+RSI | 0.49 | +0.75 [+0.03, +1.43] p=0.040 |
| ZMR | 0.18 | +0.44 [-0.28, +1.10] p=0.220 |

#### portfolio table, all26_rp: 26 sleeves, risk_parity, class budgets {'equity': 0.6, 'fx': 0.4}, 2008-07-01 -> 2021-12-31, provenance 4491e33 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 12.90 | 0.90 | 2.51 | 0.17 | 0.63 | 7.16 | 0.13 | 65.04 |
| Buy&Hold | 20.93 | 1.41 | 2.84 | 0.33 | 1.23 | 7.38 | 0.19 | 96.93 |
| B&H vol-target | 17.82 | 1.22 | 2.49 | 0.30 | 1.10 | 8.08 | 0.15 | 94.99 |
| SMA(20/50) | 25.37 | 1.68 | 3.78 | 0.33 | 1.21 | 7.02 | 0.24 | 86.14 |
| MACD | 6.22 | 0.45 | 3.71 | 0.01 | 0.02 | 9.55 | 0.05 | 82.59 |
| KDJ+RSI | 42.66 | 2.66 | 3.83 | 0.57 | 2.11 | 8.75 | 0.30 | 80.14 |
| ZMR | 16.05 | 1.10 | 4.10 | 0.17 | 0.62 | 11.25 | 0.10 | 64.13 |
| TSMOM(12-1) | 8.06 | 0.57 | 3.55 | 0.04 | 0.15 | 10.33 | 0.06 | 87.53 |
| TSMOM(L/S) | 10.54 | 0.74 | 2.98 | 0.10 | 0.36 | 6.02 | 0.12 | 62.58 |
| Carry | 5.94 | 0.43 | 1.44 | -0.04 | -0.15 | 5.36 | 0.08 | 18.87 |

#### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): all26_rp

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | 0.17 | -0.13 [-0.60, +0.31] p=0.564 |
| Buy&Hold | 0.33 | +0.03 [-0.19, +0.21] p=0.728 |
| TSMOM(12-1) | 0.04 | -0.26 [-0.97, +0.39] p=0.405 |
| TSMOM(L/S) | 0.10 | -0.20 [-0.99, +0.53] p=0.562 |
| Carry | -0.04 | -0.34 [-0.97, +0.24] p=0.265 |
| SMA(20/50) | 0.33 | +0.03 [-0.68, +0.70] p=0.987 |
| MACD | 0.01 | -0.29 [-1.09, +0.40] p=0.402 |
| KDJ+RSI | 0.57 | +0.27 [-0.44, +0.95] p=0.456 |
| ZMR | 0.17 | -0.13 [-0.83, +0.51] p=0.657 |


## Step 2: books built with the long/short trend stream

#### streams (excess returns)

| stream | Sharpe | t | vol % | excess return %/yr | MDD % | n |
|:--|--:|--:|--:|--:|--:|--:|
| beta | 0.87 | 3.21 | 5.25 | +4.57 | 9.89 | 3523 |
| trend_etf | 0.40 | 1.46 | 4.23 | +1.67 | 7.39 | 3523 |
| trend_fx | -0.13 | -0.47 | 3.49 | -0.44 | 14.43 | 3523 |
| carry | -0.05 | -0.18 | 2.15 | -0.11 | 8.57 | 3523 |

#### correlation of daily excess returns

| | beta | trend_etf | trend_fx | carry |
|:--|--:|--:|--:|--:|
| beta | 1.00 | 0.30 | 0.01 | 0.06 |
| trend_etf | 0.30 | 1.00 | 0.22 | -0.15 |
| trend_fx | 0.01 | 0.22 | 1.00 | -0.34 |
| carry | 0.06 | -0.15 | -0.34 | 1.00 |

#### books (risk parity across streams; block-bootstrap Sharpe difference vs the base)

| book | mean shares | Sharpe | vol % | MDD % | Sharpe − base [95% CI] p | with DD overlay: Sharpe / MDD % / days halved | overlay − base [95% CI] p |
|:--|:--|--:|--:|--:|:--|:--|:--|
| beta (base) | {'beta': 1.0} | 0.87 | 5.25 | 9.89 | +0.00 [+0.00, +0.00] p 1.000 | 0.87 / 9.89 / 0% | +0.00 [+0.00, +0.00] p 1.000 |
| beta + trend_etf | {'beta': 0.424, 'trend_etf': 0.576} | 0.81 | 3.71 | 5.94 | -0.06 [-0.38, +0.26] p 0.674 | 0.81 / 5.94 / 0% | -0.06 [-0.38, +0.26] p 0.674 |
| beta + carry | {'beta': 0.241, 'carry': 0.759} | 0.51 | 2.10 | 7.83 | -0.36 [-0.77, +0.06] p 0.094 | 0.51 / 7.83 / 0% | -0.36 [-0.77, +0.06] p 0.094 |
| beta + trend_etf + carry | {'beta': 0.167, 'trend_etf': 0.23, 'carry': 0.602} | 0.62 | 1.92 | 4.90 | -0.25 [-0.64, +0.15] p 0.225 | 0.62 / 4.90 / 0% | -0.25 [-0.64, +0.15] p 0.225 |
| all four | {'beta': 0.125, 'trend_etf': 0.168, 'trend_fx': 0.228, 'carry': 0.479} | 0.56 | 1.66 | 3.50 | -0.31 [-0.79, +0.16] p 0.195 | 0.56 / 3.50 / 0% | -0.31 [-0.79, +0.16] p 0.195 |
| trend + carry (no beta) | {'trend_etf': 0.206, 'trend_fx': 0.254, 'carry': 0.539} | 0.26 | 1.60 | 5.09 | -0.61 [-1.25, +0.03] p 0.062 | 0.26 / 5.09 / 0% | -0.61 [-1.25, +0.03] p 0.062 |


## Step 3: the vol-target core with the desk's tilt at size lam

r(lam) = control + lam * (desk - control); lam 0 is `B&H vol-target`, lam 1 the desk. Excess-return Sharpe, 260 periods/year, paired block bootstrap over days. Chosen on the design period only.

#### etf11_rp: 2008-07-01 -> 2021-12-31, a design period (no holdout is consulted), n = 3400 days

| lam | Sharpe | vol %/yr | cumulative return % | MDD % | Sharpe - control [95% CI] p | Sharpe - desk [95% CI] p |
|--:|--:|--:|--:|--:|:--|:--|
| 0.00 | 0.89 | 5.34 | 94.97 | 9.84 | +0.00 [+0.00, +0.00] p 1.000 | +0.10 [-0.07, +0.26] p 0.250 |
| 0.25 | 0.88 | 5.00 | 86.27 | 9.22 | -0.01 [-0.05, +0.02] p 0.474 | +0.08 [-0.05, +0.22] p 0.211 |
| 0.50 | 0.86 | 4.68 | 77.90 | 8.59 | -0.03 [-0.10, +0.04] p 0.397 | +0.07 [-0.03, +0.16] p 0.168 |
| 0.75 | 0.83 | 4.39 | 69.86 | 7.97 | -0.06 [-0.18, +0.06] p 0.324 | +0.04 [-0.01, +0.09] p 0.139 |
| 1.00 | 0.79 | 4.14 | 62.13 | 7.49 | -0.10 [-0.26, +0.07] p 0.250 | +0.00 [-0.00, +0.00] p 1.000 |

#### fx15_rp: 2008-07-01 -> 2021-12-31, a design period (no holdout is consulted), n = 3521 days

| lam | Sharpe | vol %/yr | cumulative return % | MDD % | Sharpe - control [95% CI] p | Sharpe - desk [95% CI] p |
|--:|--:|--:|--:|--:|:--|:--|
| 0.00 | -0.27 | 2.64 | -3.26 | 14.08 | +0.00 [+0.00, +0.00] p 1.000 | -0.04 [-0.64, +0.60] p 0.914 |
| 0.25 | -0.31 | 2.26 | -3.03 | 11.03 | -0.04 [-0.21, +0.13] p 0.645 | -0.08 [-0.54, +0.42] p 0.755 |
| 0.50 | -0.31 | 2.19 | -2.90 | 10.17 | -0.05 [-0.43, +0.33] p 0.808 | -0.09 [-0.37, +0.22] p 0.581 |
| 0.75 | -0.28 | 2.46 | -2.87 | 10.00 | -0.01 [-0.54, +0.50] p 0.969 | -0.05 [-0.17, +0.08] p 0.456 |
| 1.00 | -0.22 | 2.98 | -2.95 | 11.46 | +0.04 [-0.60, +0.64] p 0.914 | +0.00 [-0.00, +0.00] p 1.000 |

#### all26_rp: 2008-07-01 -> 2021-12-31, a design period (no holdout is consulted), n = 3523 days

| lam | Sharpe | vol %/yr | cumulative return % | MDD % | Sharpe - control [95% CI] p | Sharpe - desk [95% CI] p |
|--:|--:|--:|--:|--:|:--|:--|
| 0.00 | 0.30 | 2.49 | 17.82 | 8.08 | +0.00 [+0.00, +0.00] p 1.000 | +0.13 [-0.31, +0.60] p 0.564 |
| 0.25 | 0.29 | 2.27 | 16.65 | 7.38 | -0.01 [-0.12, +0.12] p 0.950 | +0.12 [-0.22, +0.51] p 0.472 |
| 0.50 | 0.27 | 2.20 | 15.44 | 6.95 | -0.03 [-0.28, +0.21] p 0.800 | +0.10 [-0.14, +0.36] p 0.397 |
| 0.75 | 0.22 | 2.28 | 14.19 | 6.98 | -0.08 [-0.45, +0.27] p 0.666 | +0.05 [-0.06, +0.18] p 0.348 |
| 1.00 | 0.17 | 2.51 | 12.90 | 7.16 | -0.13 [-0.60, +0.31] p 0.564 | +0.00 [-0.00, +0.00] p 1.000 |


## Reading

* **Trend.** Read the `TSMOM(L/S)` row of each difference table against the run's control,
  and beside the long-only `TSMOM(12-1)` row of the same table. Allowing shorts did not help
  on the ETF runs; on FX both trend rows sit near the control with wide intervals.
* **Books.** Adding the trend and carry streams to the base lowers volatility and drawdown
  and lowers the Sharpe ratio with them; no book's interval against the base is above zero.
* **Overlay.** Where the control earns something (the ETF run) the Sharpe falls as `lam`
  rises; on FX nothing earns. No size is distinguishable from the control.
* **One row that looks significant.** `KDJ+RSI` on the FX run has an interval above zero. It
  is an old baseline, not a candidate of this round, one of 36 difference rows on this page,
  and the same rule is below the control on the ETF runs. It is not adopted.
* **What this does not say.** It does not say trend following does not work. It says that
  these costed streams, on these 26 instruments and this period, did not beat a vol-targeted
  holding of the same instruments by more than the noise. A futures universe across more
  asset classes is the setting the literature reports, and the project does not have it.

The test that remains is the forward paper-trading record
([v09_preregistration.md](v09_preregistration.md)), which is the only unseen data.
