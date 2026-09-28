# v0.9 research: a multi-asset base, trend and carry, and the forward test

This is the record of the v0.9 plan (chosen after the v0.8 attribution showed the desk's
active tilts add nothing over the vol-targeted control) and its outcome. Every number
below is copied from `results/v09/tables.md`, `results/v09/combine.md` and
`results/v09/holdout/*` by `scripts/render_v09_doc.py`; the pre-registration written
before the holdout run is [v09_preregistration.md](v09_preregistration.md).

**Outcome in one sentence: on the 2016–2021 design period none of the three candidate
streams beats its control and no combination beats the multi-asset base, so nothing is
adopted; the holdout report below is a report, not a choice; the forward paper-trading
record (`scripts/paper_trade_v09.py`, frozen 2026-09-29) is the test.**

Conventions: Sharpe on excess returns over the credited bill; `B&H vol-target` is the
mechanical control of every run; the paired block bootstrap over days (block 10, 5000
resamples) gives every difference its interval and two-sided p; risk parity re-estimates
capital shares every 5 bars from a 120-day covariance window with no look-ahead. The two
new streams are baselines in every sleeve since this branch: `TSMOM(12-1)` (sign of the
trailing 12-month return skipping the last month, at the vol-target size, long-only where
shorts are not allowed) and `Carry` (the FX carry premium at the desk's strategic size;
flat on equities, so its row is 0 in the ETF runs).

## Phase 0: attribution of the v0.8 desk (`scripts/attribution_v09.py`)

### design (n = 1564 days)

| series | Sharpe (excess) | vol % | corr with desk |
|:--|--:|--:|--:|
| desk | 1.40 | 7.37 | 1.00 |
| B&H vol-target | 1.43 | 7.53 | 0.94 |
| Buy&Hold | 1.28 | 14.25 | 0.95 |

| against | desk − control Sharpe [95% CI] p | tilt mean %/yr | tilt vol %/yr | tilt Sharpe [95% CI] p | alpha %/yr (t) | beta | R² | IR | residual vol %/yr |
|:--|:--|--:|--:|:--|:--|--:|--:|--:|--:|
| B&H vol-target | -0.03 [-0.28, +0.23] p 0.898 | -0.43 | 2.54 | -0.17 [-0.90, +0.56] p 0.652 | +0.41 (+0.40) | 0.92 | 0.89 | +0.17 | 2.47 |
| Buy&Hold | +0.12 [-0.16, +0.40] p 0.434 | -7.89 | 7.65 | -1.03 [-1.93, -0.25] p 0.007 | +1.40 (+1.45) | 0.49 | 0.90 | +0.59 | 2.36 |

| strategy | mean trades per sleeve | mean exposure % |
|:--|--:|--:|
| AgenticTrader | 91.7 | 63.3 |
| B&H vol-target | 760.0 | 80.5 |
| Buy&Hold | 1.0 | 99.1 |
| KDJ+RSI | 54.1 | 54.2 |
| MACD | 124.1 | 67.8 |
| SMA(20/50) | 32.2 | 78.8 |
| ZMR | 120.3 | 44.4 |

### holdout (n = 1167 days)

| series | Sharpe (excess) | vol % | corr with desk |
|:--|--:|--:|--:|
| desk | 0.80 | 6.71 | 1.00 |
| B&H vol-target | 0.99 | 7.01 | 0.93 |
| Buy&Hold | 0.86 | 14.08 | 0.93 |

| against | desk − control Sharpe [95% CI] p | tilt mean %/yr | tilt vol %/yr | tilt Sharpe [95% CI] p | alpha %/yr (t) | beta | R² | IR | residual vol %/yr |
|:--|:--|--:|--:|:--|:--|--:|--:|--:|--:|
| B&H vol-target | -0.19 [-0.53, +0.16] p 0.297 | -1.57 | 2.60 | -0.61 [-1.51, +0.29] p 0.190 | -0.80 (-0.68) | 0.89 | 0.86 | -0.32 | 2.48 |
| Buy&Hold | -0.06 [-0.41, +0.30] p 0.748 | -6.74 | 8.22 | -0.82 [-1.77, +0.12] p 0.087 | +0.01 (+0.00) | 0.44 | 0.86 | +0.00 | 2.47 |

| strategy | mean trades per sleeve | mean exposure % |
|:--|--:|--:|
| AgenticTrader | 69.9 | 60.5 |
| B&H vol-target | 654.4 | 73.7 |
| Buy&Hold | 1.0 | 97.4 |
| KDJ+RSI | 45.0 | 60.7 |
| MACD | 94.7 | 66.6 |
| SMA(20/50) | 26.2 | 73.0 |
| ZMR | 90.8 | 49.6 |

Reading: the tilt is the desk's daily excess return minus the control's on the same day; its Sharpe is what the signals add on top of holding the same sleeves mechanically. The regression gives the same thing as alpha (annualised intercept, with its t) and beta on the control; the information ratio is alpha per unit of residual risk. Intervals: circular block bootstrap over days (block 10, 5000 resamples).

## Phases 1–3 on the design period (2016-01-04 → 2021-12-31)

Runs: `etf11_rp` (SPY EFA EEM IWM TLT IEF LQD HYG GLD DBC VNQ, risk parity), `etf11_equal`
(1/N), `fx15_rp` (the 15 FX pairs), `core15_rp` (the v0.8 core universe under risk
parity; v0.8 used 1/N) and `all26_rp` (ETFs + FX with class budgets equity 0.6 / fx 0.4).

Measured 2026-09-28 21:43:50 at commit `9513d13` (clean tree), cpp backend, 391 s.

#### portfolio table, etf11_rp: 11 sleeves, risk_parity, 2016-01-04 -> 2021-12-31, provenance 9513d13 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 31.94 | 4.73 | 4.00 | 0.94 | 2.31 | 7.63 | 0.62 | 76.07 |
| Buy&Hold | 49.44 | 6.93 | 6.11 | 0.97 | 2.39 | 15.05 | 0.46 | 100.00 |
| B&H vol-target | 41.92 | 6.02 | 4.92 | 1.02 | 2.50 | 8.65 | 0.70 | 96.10 |
| SMA(20/50) | 47.44 | 6.69 | 4.30 | 1.31 | 3.21 | 5.88 | 1.14 | 65.80 |
| MACD | 25.75 | 3.90 | 3.47 | 0.85 | 2.08 | 5.18 | 0.75 | 50.39 |
| KDJ+RSI | 19.88 | 3.07 | 4.51 | 0.49 | 1.19 | 12.76 | 0.24 | 35.12 |
| ZMR | 13.01 | 2.06 | 4.67 | 0.26 | 0.63 | 12.78 | 0.16 | 29.73 |
| TSMOM(12-1) | 19.82 | 3.06 | 4.33 | 0.50 | 1.23 | 7.59 | 0.40 | 68.58 |
| Carry | 5.80 | 0.95 | 0.00 | 0.00 | 0.00 | 0.00 | 2646.36 | 0.00 |

#### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): etf11_rp

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | 0.94 | -0.08 [-0.30, +0.16] p=0.514 |
| Buy&Hold | 0.97 | -0.05 [-0.35, +0.27] p=0.920 |
| TSMOM(12-1) | 0.50 | -0.52 [-0.89, -0.15] p=0.007 |
| Carry | 0.00 | -1.02 [-1.92, -0.16] p=0.022 |
| SMA(20/50) | 1.31 | +0.29 [-0.19, +0.77] p=0.235 |
| MACD | 0.85 | -0.17 [-0.86, +0.51] p=0.590 |
| KDJ+RSI | 0.49 | -0.54 [-1.09, +0.20] p=0.167 |
| ZMR | 0.26 | -0.76 [-1.34, -0.06] p=0.035 |

#### portfolio table, etf11_equal: 11 sleeves, equal, 2016-01-04 -> 2021-12-31, provenance 9513d13 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 42.56 | 6.10 | 5.35 | 0.96 | 2.34 | 10.23 | 0.60 | 72.53 |
| Buy&Hold | 75.70 | 9.86 | 9.92 | 0.90 | 2.21 | 21.69 | 0.45 | 100.00 |
| B&H vol-target | 57.85 | 7.92 | 6.75 | 1.02 | 2.50 | 11.44 | 0.69 | 92.71 |
| SMA(20/50) | 62.61 | 8.45 | 5.85 | 1.26 | 3.07 | 4.81 | 1.76 | 65.92 |
| MACD | 37.39 | 5.44 | 5.46 | 0.83 | 2.02 | 6.91 | 0.79 | 51.22 |
| KDJ+RSI | 30.97 | 4.61 | 7.32 | 0.52 | 1.28 | 19.64 | 0.23 | 33.18 |
| ZMR | 18.74 | 2.91 | 7.69 | 0.29 | 0.71 | 19.68 | 0.15 | 29.42 |
| TSMOM(12-1) | 24.98 | 3.79 | 5.36 | 0.55 | 1.34 | 9.85 | 0.39 | 64.31 |
| Carry | 5.80 | 0.95 | 0.00 | 0.00 | 0.00 | 0.00 | 2646.36 | 0.00 |

#### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): etf11_equal

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | 0.96 | -0.07 [-0.29, +0.19] p=0.609 |
| Buy&Hold | 0.90 | -0.12 [-0.46, +0.24] p=0.687 |
| TSMOM(12-1) | 0.55 | -0.48 [-0.86, -0.08] p=0.022 |
| Carry | 0.00 | -1.02 [-1.90, -0.17] p=0.020 |
| SMA(20/50) | 1.26 | +0.23 [-0.29, +0.76] p=0.383 |
| MACD | 0.83 | -0.20 [-0.92, +0.51] p=0.581 |
| KDJ+RSI | 0.52 | -0.50 [-1.09, +0.38] p=0.307 |
| ZMR | 0.29 | -0.73 [-1.32, +0.02] p=0.054 |

#### portfolio table, fx15_rp: 15 sleeves, risk_parity, 2016-01-04 -> 2021-12-31, provenance 9513d13 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 4.12 | 0.67 | 2.19 | -0.11 | -0.28 | 3.15 | 0.21 | 63.24 |
| Buy&Hold | 6.53 | 1.06 | 1.73 | 0.07 | 0.18 | 3.33 | 0.32 | 96.72 |
| B&H vol-target | 6.64 | 1.07 | 1.74 | 0.08 | 0.20 | 3.26 | 0.33 | 97.77 |
| SMA(20/50) | -2.63 | -0.44 | 3.58 | -0.37 | -0.91 | 6.99 | -0.06 | 98.39 |
| MACD | 0.18 | 0.03 | 3.61 | -0.23 | -0.58 | 6.81 | 0.00 | 98.99 |
| KDJ+RSI | 26.87 | 4.04 | 3.38 | 0.91 | 2.23 | 5.57 | 0.72 | 100.92 |
| ZMR | 12.61 | 1.99 | 3.49 | 0.31 | 0.77 | 6.57 | 0.30 | 80.00 |
| TSMOM(12-1) | -4.21 | -0.71 | 3.59 | -0.44 | -1.09 | 7.22 | -0.10 | 98.34 |
| Carry | 6.85 | 1.11 | 1.27 | 0.13 | 0.32 | 2.33 | 0.48 | 29.89 |

#### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): fx15_rp

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | -0.11 | -0.19 [-1.20, +0.82] p=0.730 |
| Buy&Hold | 0.07 | -0.01 [-0.07, +0.05] p=0.779 |
| TSMOM(12-1) | -0.44 | -0.53 [-1.58, +0.57] p=0.350 |
| Carry | 0.13 | +0.05 [-0.98, +1.08] p=0.904 |
| SMA(20/50) | -0.37 | -0.45 [-1.48, +0.56] p=0.386 |
| MACD | -0.23 | -0.32 [-1.29, +0.73] p=0.558 |
| KDJ+RSI | 0.91 | +0.83 [-0.30, +1.97] p=0.140 |
| ZMR | 0.31 | +0.23 [-0.96, +1.39] p=0.698 |

#### portfolio table, core15_rp: 15 sleeves, risk_parity, 2016-01-04 -> 2021-12-31, provenance 9513d13 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 28.96 | 4.32 | 3.33 | 1.00 | 2.46 | 4.45 | 0.97 | 64.31 |
| Buy&Hold | 40.02 | 5.76 | 4.37 | 1.09 | 2.66 | 5.56 | 1.04 | 96.64 |
| B&H vol-target | 26.96 | 4.05 | 3.40 | 0.91 | 2.22 | 4.19 | 0.97 | 93.19 |
| SMA(20/50) | 34.54 | 5.06 | 4.38 | 0.93 | 2.29 | 4.37 | 1.16 | 90.95 |
| MACD | 8.94 | 1.43 | 4.04 | 0.14 | 0.34 | 8.29 | 0.17 | 86.85 |
| KDJ+RSI | 34.31 | 5.03 | 4.05 | 1.00 | 2.45 | 6.37 | 0.79 | 83.65 |
| ZMR | 26.02 | 3.92 | 4.02 | 0.74 | 1.82 | 8.19 | 0.48 | 65.67 |
| TSMOM(12-1) | 16.49 | 2.57 | 4.09 | 0.41 | 1.01 | 7.80 | 0.33 | 90.64 |
| Carry | 7.65 | 1.23 | 1.08 | 0.27 | 0.65 | 1.33 | 0.93 | 19.72 |

#### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): core15_rp

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | 1.00 | +0.10 [-0.64, +0.88] p=0.775 |
| Buy&Hold | 1.09 | +0.18 [-0.07, +0.42] p=0.148 |
| TSMOM(12-1) | 0.41 | -0.50 [-1.35, +0.35] p=0.256 |
| Carry | 0.27 | -0.64 [-1.75, +0.47] p=0.255 |
| SMA(20/50) | 0.93 | +0.03 [-0.79, +0.84] p=0.915 |
| MACD | 0.14 | -0.77 [-1.78, +0.22] p=0.125 |
| KDJ+RSI | 1.00 | +0.09 [-0.93, +1.12] p=0.857 |
| ZMR | 0.74 | -0.16 [-1.22, +0.89] p=0.766 |

#### portfolio table, all26_rp: 26 sleeves, risk_parity, class budgets {'equity': 0.6, 'fx': 0.4}, 2016-01-04 -> 2021-12-31, provenance 9513d13 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 11.62 | 1.84 | 1.98 | 0.46 | 1.12 | 3.31 | 0.56 | 66.46 |
| Buy&Hold | 16.05 | 2.51 | 2.13 | 0.73 | 1.79 | 3.19 | 0.79 | 96.54 |
| B&H vol-target | 14.82 | 2.32 | 1.94 | 0.71 | 1.73 | 2.54 | 0.91 | 96.34 |
| SMA(20/50) | 10.54 | 1.68 | 2.78 | 0.27 | 0.67 | 3.77 | 0.45 | 87.14 |
| MACD | 7.53 | 1.21 | 2.73 | 0.11 | 0.27 | 5.43 | 0.22 | 82.81 |
| KDJ+RSI | 23.85 | 3.62 | 2.76 | 0.96 | 2.36 | 6.73 | 0.54 | 79.62 |
| ZMR | 11.95 | 1.89 | 2.83 | 0.34 | 0.84 | 7.86 | 0.24 | 63.69 |
| TSMOM(12-1) | 1.88 | 0.31 | 2.87 | -0.21 | -0.51 | 5.75 | 0.05 | 88.01 |
| Carry | 6.71 | 1.08 | 0.87 | 0.16 | 0.39 | 1.71 | 0.63 | 19.96 |

#### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): all26_rp

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | 0.46 | -0.25 [-0.97, +0.49] p=0.510 |
| Buy&Hold | 0.73 | +0.02 [-0.19, +0.21] p=0.730 |
| TSMOM(12-1) | -0.21 | -0.91 [-1.83, -0.01] p=0.046 |
| Carry | 0.16 | -0.55 [-1.57, +0.47] p=0.290 |
| SMA(20/50) | 0.27 | -0.43 [-1.39, +0.51] p=0.362 |
| MACD | 0.11 | -0.60 [-1.67, +0.52] p=0.302 |
| KDJ+RSI | 0.96 | +0.25 [-0.70, +1.29] p=0.582 |
| ZMR | 0.34 | -0.36 [-1.36, +0.70] p=0.510 |

#### Stream combination (design)

#### streams (excess returns)

| stream | Sharpe | t | vol % | excess return %/yr | MDD % | n |
|:--|--:|--:|--:|--:|--:|--:|
| beta | 1.02 | 2.50 | 4.91 | +5.00 | 8.71 | 1564 |
| trend_etf | 0.50 | 1.22 | 4.32 | +2.16 | 8.61 | 1564 |
| trend_fx | -0.44 | -1.09 | 3.59 | -1.59 | 12.14 | 1564 |
| carry | 0.13 | 0.32 | 1.27 | +0.17 | 2.39 | 1564 |

#### correlation of daily excess returns

| | beta | trend_etf | trend_fx | carry |
|:--|--:|--:|--:|--:|
| beta | 1.00 | 0.89 | 0.00 | 0.06 |
| trend_etf | 0.89 | 1.00 | 0.04 | 0.04 |
| trend_fx | 0.00 | 0.04 | 1.00 | -0.26 |
| carry | 0.06 | 0.04 | -0.26 | 1.00 |

#### books (risk parity across streams; block-bootstrap Sharpe difference vs the base)

| book | mean shares | Sharpe | vol % | MDD % | Sharpe − base [95% CI] p | with DD overlay: Sharpe / MDD % / days halved | overlay − base [95% CI] p |
|:--|:--|--:|--:|--:|:--|:--|:--|
| beta (base) | {'beta': 1.0} | 1.02 | 4.91 | 8.71 | +0.00 [+0.00, +0.00] p 1.000 | 1.02 / 8.71 / 0% | +0.00 [+0.00, +0.00] p 1.000 |
| beta + trend_etf | {'beta': 0.466, 'trend_etf': 0.534} | 0.78 | 4.47 | 8.22 | -0.24 [-0.42, -0.05] p 0.012 | 0.78 / 8.22 / 0% | -0.24 [-0.42, -0.05] p 0.012 |
| beta + carry | {'beta': 0.219, 'carry': 0.781} | 1.02 | 1.50 | 3.57 | +0.00 [-0.57, +0.55] p 1.000 | 1.02 / 3.57 / 0% | +0.00 [-0.57, +0.55] p 1.000 |
| beta + trend_etf + carry | {'beta': 0.145, 'trend_etf': 0.166, 'carry': 0.688} | 0.88 | 1.64 | 4.01 | -0.14 [-0.59, +0.33] p 0.564 | 0.88 / 4.01 / 0% | -0.14 [-0.59, +0.33] p 0.564 |
| all four | {'beta': 0.107, 'trend_etf': 0.123, 'trend_fx': 0.203, 'carry': 0.567} | 0.57 | 1.35 | 2.54 | -0.45 [-1.03, +0.12] p 0.118 | 0.57 / 2.54 / 0% | -0.45 [-1.03, +0.12] p 0.118 |
| trend + carry (no beta) | {'trend_etf': 0.174, 'trend_fx': 0.22, 'carry': 0.606} | 0.11 | 1.23 | 2.48 | -0.91 [-1.66, -0.16] p 0.016 | 0.11 / 2.48 / 0% | -0.91 [-1.66, -0.16] p 0.016 |

## The pre-registered holdout report (2022-01-03 → 2026-06-30)

Reported once, after the design-period verdict and the pre-registration; not a basis for
any choice (see [v09_preregistration.md](v09_preregistration.md)).

Measured 2026-09-28 21:51:02 at commit `0ea08b1` (clean tree), cpp backend, 266 s.

#### portfolio table, etf11_rp: 11 sleeves, risk_parity, 2022-01-03 -> 2026-06-30, provenance 0ea08b1 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 18.45 | 3.87 | 5.22 | -0.01 | -0.02 | 5.91 | 0.65 | 67.61 |
| Buy&Hold | 18.31 | 3.84 | 8.79 | 0.02 | 0.04 | 19.22 | 0.20 | 100.00 |
| B&H vol-target | 14.62 | 3.10 | 7.63 | -0.08 | -0.18 | 16.96 | 0.18 | 93.10 |
| SMA(20/50) | 14.67 | 3.11 | 5.25 | -0.15 | -0.31 | 8.81 | 0.35 | 57.78 |
| MACD | 20.78 | 4.32 | 5.20 | 0.07 | 0.15 | 7.79 | 0.55 | 49.46 |
| KDJ+RSI | 23.19 | 4.78 | 5.92 | 0.15 | 0.31 | 13.11 | 0.36 | 43.97 |
| ZMR | 12.95 | 2.76 | 5.70 | -0.19 | -0.41 | 13.99 | 0.20 | 35.22 |
| TSMOM(12-1) | 23.08 | 4.76 | 4.92 | 0.16 | 0.34 | 4.92 | 0.97 | 61.00 |
| Carry | 19.47 | 4.07 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

#### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): etf11_rp

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | -0.01 | +0.07 [-0.26, +0.45] p=0.706 |
| Buy&Hold | 0.02 | +0.10 [-0.01, +0.22] p=0.070 |
| TSMOM(12-1) | 0.16 | +0.24 [-0.36, +0.87] p=0.420 |
| Carry | 0.00 | +0.08 [-0.83, +0.99] p=0.850 |
| SMA(20/50) | -0.15 | -0.07 [-0.70, +0.60] p=0.867 |
| MACD | 0.07 | +0.16 [-0.50, +0.77] p=0.654 |
| KDJ+RSI | 0.15 | +0.23 [-0.27, +0.73] p=0.375 |
| ZMR | -0.19 | -0.11 [-0.69, +0.47] p=0.729 |

#### portfolio table, etf11_equal: 11 sleeves, equal, 2022-01-03 -> 2026-06-30, provenance 0ea08b1 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 27.39 | 5.57 | 6.08 | 0.27 | 0.56 | 5.87 | 0.95 | 65.58 |
| Buy&Hold | 31.72 | 6.37 | 10.65 | 0.26 | 0.55 | 19.57 | 0.33 | 100.00 |
| B&H vol-target | 23.91 | 4.92 | 8.68 | 0.14 | 0.29 | 16.54 | 0.30 | 89.73 |
| SMA(20/50) | 19.53 | 4.08 | 6.42 | 0.03 | 0.07 | 9.80 | 0.42 | 57.90 |
| MACD | 26.12 | 5.34 | 6.27 | 0.23 | 0.48 | 9.09 | 0.59 | 50.28 |
| KDJ+RSI | 32.63 | 6.53 | 7.02 | 0.37 | 0.78 | 12.52 | 0.52 | 42.41 |
| ZMR | 16.57 | 3.49 | 6.89 | -0.05 | -0.10 | 13.73 | 0.25 | 34.42 |
| TSMOM(12-1) | 31.02 | 6.24 | 5.97 | 0.38 | 0.80 | 5.99 | 1.04 | 58.71 |
| Carry | 19.47 | 4.07 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

#### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): etf11_equal

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | 0.27 | +0.13 [-0.19, +0.50] p=0.474 |
| Buy&Hold | 0.26 | +0.12 [-0.02, +0.27] p=0.094 |
| TSMOM(12-1) | 0.38 | +0.24 [-0.32, +0.84] p=0.412 |
| Carry | 0.00 | -0.14 [-1.06, +0.78] p=0.774 |
| SMA(20/50) | 0.03 | -0.10 [-0.72, +0.55] p=0.778 |
| MACD | 0.23 | +0.09 [-0.58, +0.72] p=0.833 |
| KDJ+RSI | 0.37 | +0.23 [-0.31, +0.76] p=0.400 |
| ZMR | -0.05 | -0.18 [-0.77, +0.40] p=0.568 |

#### portfolio table, fx15_rp: 15 sleeves, risk_parity, 2022-01-03 -> 2026-06-30, provenance 0ea08b1 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 22.34 | 4.60 | 2.38 | 0.23 | 0.48 | 2.14 | 2.15 | 66.68 |
| Buy&Hold | 26.00 | 5.29 | 1.76 | 0.67 | 1.42 | 1.42 | 3.73 | 91.96 |
| B&H vol-target | 26.76 | 5.43 | 1.74 | 0.76 | 1.60 | 1.42 | 3.83 | 93.96 |
| SMA(20/50) | 8.97 | 1.93 | 3.81 | -0.52 | -1.11 | 4.93 | 0.39 | 98.50 |
| MACD | 17.26 | 3.61 | 3.74 | -0.10 | -0.21 | 3.28 | 1.10 | 99.07 |
| KDJ+RSI | 31.95 | 6.38 | 3.55 | 0.64 | 1.35 | 4.30 | 1.48 | 100.96 |
| ZMR | 25.79 | 5.25 | 3.69 | 0.33 | 0.69 | 3.58 | 1.47 | 81.72 |
| TSMOM(12-1) | 25.63 | 5.22 | 3.61 | 0.32 | 0.69 | 4.54 | 1.15 | 97.86 |
| Carry | 22.47 | 4.62 | 1.25 | 0.44 | 0.92 | 1.37 | 3.38 | 30.80 |

#### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): fx15_rp

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | 0.23 | -0.53 [-1.66, +0.60] p=0.372 |
| Buy&Hold | 0.67 | -0.08 [-0.33, +0.08] p=0.617 |
| TSMOM(12-1) | 0.32 | -0.43 [-1.58, +0.74] p=0.486 |
| Carry | 0.44 | -0.32 [-1.37, +0.79] p=0.593 |
| SMA(20/50) | -0.52 | -1.28 [-2.46, -0.07] p=0.036 |
| MACD | -0.10 | -0.85 [-2.19, +0.46] p=0.212 |
| KDJ+RSI | 0.64 | -0.12 [-1.30, +1.03] p=0.851 |
| ZMR | 0.33 | -0.43 [-1.66, +0.81] p=0.492 |

#### portfolio table, core15_rp: 15 sleeves, risk_parity, 2022-01-03 -> 2026-06-30, provenance 0ea08b1 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 30.23 | 6.06 | 3.66 | 0.54 | 1.14 | 4.12 | 1.47 | 64.65 |
| Buy&Hold | 46.77 | 8.92 | 3.62 | 1.28 | 2.71 | 4.04 | 2.21 | 93.05 |
| B&H vol-target | 39.28 | 7.66 | 2.60 | 1.32 | 2.80 | 2.49 | 3.07 | 88.55 |
| SMA(20/50) | 21.06 | 4.35 | 4.87 | 0.08 | 0.17 | 5.31 | 0.82 | 89.97 |
| MACD | 21.16 | 4.37 | 4.27 | 0.09 | 0.19 | 3.56 | 1.23 | 88.01 |
| KDJ+RSI | 35.36 | 6.98 | 4.68 | 0.61 | 1.30 | 8.31 | 0.84 | 87.91 |
| ZMR | 24.22 | 4.95 | 4.54 | 0.21 | 0.44 | 6.44 | 0.77 | 71.47 |
| TSMOM(12-1) | 34.07 | 6.75 | 4.72 | 0.56 | 1.19 | 5.73 | 1.18 | 88.42 |
| Carry | 23.57 | 4.83 | 1.78 | 0.42 | 0.89 | 2.30 | 2.10 | 24.68 |

#### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): core15_rp

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | 0.54 | -0.78 [-1.90, +0.29] p=0.169 |
| Buy&Hold | 1.28 | -0.04 [-0.31, +0.22] p=0.744 |
| TSMOM(12-1) | 0.56 | -0.76 [-1.96, +0.45] p=0.223 |
| Carry | 0.42 | -0.90 [-2.26, +0.52] p=0.214 |
| SMA(20/50) | 0.08 | -1.24 [-2.43, -0.09] p=0.037 |
| MACD | 0.09 | -1.23 [-2.47, -0.07] p=0.036 |
| KDJ+RSI | 0.61 | -0.71 [-1.76, +0.35] p=0.201 |
| ZMR | 0.21 | -1.11 [-2.18, -0.07] p=0.035 |

#### portfolio table, all26_rp: 26 sleeves, risk_parity, class budgets {'equity': 0.6, 'fx': 0.4}, 2022-01-03 -> 2026-06-30, provenance 0ea08b1 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 21.73 | 4.48 | 2.23 | 0.19 | 0.40 | 1.67 | 2.69 | 66.70 |
| Buy&Hold | 24.56 | 5.01 | 2.48 | 0.38 | 0.80 | 3.30 | 1.52 | 93.07 |
| B&H vol-target | 24.19 | 4.95 | 2.26 | 0.38 | 0.81 | 2.82 | 1.75 | 92.99 |
| SMA(20/50) | 10.75 | 2.30 | 3.18 | -0.52 | -1.11 | 4.72 | 0.49 | 88.47 |
| MACD | 17.50 | 3.66 | 3.03 | -0.11 | -0.24 | 2.95 | 1.24 | 86.59 |
| KDJ+RSI | 29.90 | 6.00 | 2.98 | 0.63 | 1.34 | 5.08 | 1.18 | 86.83 |
| ZMR | 22.82 | 4.69 | 3.08 | 0.21 | 0.44 | 4.65 | 1.01 | 70.14 |
| TSMOM(12-1) | 24.89 | 5.08 | 3.00 | 0.34 | 0.71 | 3.61 | 1.41 | 89.05 |
| Carry | 21.93 | 4.52 | 0.97 | 0.45 | 0.95 | 1.06 | 4.28 | 23.75 |

#### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): all26_rp

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | 0.19 | -0.20 [-1.14, +0.77] p=0.692 |
| Buy&Hold | 0.38 | -0.01 [-0.19, +0.15] p=1.000 |
| TSMOM(12-1) | 0.34 | -0.05 [-1.21, +1.15] p=0.966 |
| Carry | 0.45 | +0.06 [-1.18, +1.38] p=0.898 |
| SMA(20/50) | -0.52 | -0.91 [-2.03, +0.23] p=0.123 |
| MACD | -0.11 | -0.50 [-1.81, +0.79] p=0.440 |
| KDJ+RSI | 0.63 | +0.25 [-0.77, +1.25] p=0.634 |
| ZMR | 0.21 | -0.18 [-1.19, +0.89] p=0.747 |

#### Stream combination (holdout)

#### streams (excess returns)

| stream | Sharpe | t | vol % | excess return %/yr | MDD % | n |
|:--|--:|--:|--:|--:|--:|--:|
| beta | -0.09 | -0.18 | 7.61 | -0.66 | 19.38 | 1167 |
| trend_etf | 0.16 | 0.33 | 4.91 | +0.76 | 10.47 | 1167 |
| trend_fx | 0.32 | 0.68 | 3.61 | +1.16 | 5.95 | 1167 |
| carry | 0.43 | 0.92 | 1.25 | +0.54 | 2.38 | 1167 |

#### correlation of daily excess returns

| | beta | trend_etf | trend_fx | carry |
|:--|--:|--:|--:|--:|
| beta | 1.00 | 0.79 | -0.01 | 0.01 |
| trend_etf | 0.79 | 1.00 | 0.00 | 0.00 |
| trend_fx | -0.01 | 0.00 | 1.00 | 0.29 |
| carry | 0.01 | 0.00 | 0.29 | 1.00 |

#### books (risk parity across streams; block-bootstrap Sharpe difference vs the base)

| book | mean shares | Sharpe | vol % | MDD % | Sharpe − base [95% CI] p | with DD overlay: Sharpe / MDD % / days halved | overlay − base [95% CI] p |
|:--|:--|--:|--:|--:|:--|:--|:--|
| beta (base) | {'beta': 1.0} | -0.09 | 7.61 | 19.38 | +0.00 [+0.00, +0.00] p 1.000 | -0.17 / 21.50 / 1% | -0.08 [-0.19, +0.00] p 0.052 |
| beta + trend_etf | {'beta': 0.396, 'trend_etf': 0.604} | -0.01 | 5.51 | 14.97 | +0.08 [-0.33, +0.50] p 0.704 | -0.01 / 14.97 / 0% | +0.08 [-0.33, +0.50] p 0.704 |
| beta + carry | {'beta': 0.173, 'carry': 0.827} | -0.27 | 2.02 | 6.31 | -0.19 [-0.91, +0.59] p 0.651 | -0.27 / 6.31 / 0% | -0.19 [-0.91, +0.59] p 0.651 |
| beta + trend_etf + carry | {'beta': 0.111, 'trend_etf': 0.193, 'carry': 0.697} | -0.25 | 1.89 | 6.49 | -0.16 [-0.82, +0.55] p 0.671 | -0.25 / 6.49 / 0% | -0.16 [-0.82, +0.55] p 0.671 |
| all four | {'beta': 0.088, 'trend_etf': 0.162, 'trend_fx': 0.203, 'carry': 0.548} | -0.15 | 1.69 | 4.38 | -0.07 [-0.85, +0.75] p 0.898 | -0.15 / 4.38 / 0% | -0.07 [-0.85, +0.75] p 0.898 |
| trend + carry (no beta) | {'trend_etf': 0.209, 'trend_fx': 0.218, 'carry': 0.574} | 0.25 | 1.34 | 2.57 | +0.34 [-0.79, +1.57] p 0.560 | 0.25 / 2.57 / 0% | +0.34 [-0.79, +1.57] p 0.560 |

## The forward test

`scripts/paper_trade_v09.py` recomputes, from 2026-09-29 to the last complete session,
the fully costed returns of the frozen books — the v0.8 desk on the core 15 (equal
capital) with its `B&H vol-target` and `Buy&Hold` controls; the 11-ETF risk-parity base
with `TSMOM(12-1)`; the 15 FX pairs with `Carry` and `TSMOM(12-1)` — and writes
`results/paper/ledger.csv`, `summary.md` (intervals after 60 sessions) and `runs.jsonl`
(provenance and any revision of an earlier return). A candidate is adopted only when its
forward Sharpe minus its control's clears a block-bootstrap interval that excludes zero.
