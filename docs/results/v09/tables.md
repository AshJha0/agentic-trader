> **FX re-run, 2026-11-13 (review D5 closed).** Every table on this page was re-measured from main
> 3f80a69, whose engine converts FX P&L to the USD account (the earlier tables booked a USD-base pair's
> return r where r / (1 + r) is due and left crosses unconverted). Source: `results/v09_fx_final/tables.md`. The re-run
> replaces the 2026-11-12 correction notice.

### portfolio table, etf11_rp: 11 sleeves, risk_parity, 2016-01-04 -> 2021-12-31, provenance 3f80a69 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 31.08 | 4.62 | 3.93 | 0.93 | 2.28 | 6.74 | 0.69 | 75.89 |
| Buy&Hold | 49.44 | 6.93 | 6.11 | 0.97 | 2.39 | 15.05 | 0.46 | 100.00 |
| B&H vol-target | 41.92 | 6.02 | 4.92 | 1.02 | 2.50 | 8.65 | 0.70 | 96.10 |
| SMA(20/50) | 47.44 | 6.69 | 4.30 | 1.31 | 3.21 | 5.88 | 1.14 | 65.80 |
| MACD | 25.75 | 3.90 | 3.47 | 0.85 | 2.08 | 5.18 | 0.75 | 50.39 |
| KDJ+RSI | 19.88 | 3.07 | 4.51 | 0.49 | 1.19 | 12.76 | 0.24 | 35.12 |
| ZMR | 13.01 | 2.06 | 4.67 | 0.26 | 0.63 | 12.78 | 0.16 | 29.73 |
| TSMOM(12-1) | 19.82 | 3.06 | 4.33 | 0.50 | 1.23 | 7.59 | 0.40 | 68.58 |
| TSMOM(L/S) | 12.22 | 1.94 | 3.66 | 0.29 | 0.70 | 4.28 | 0.45 | 64.79 |
| Carry | 5.80 | 0.95 | 0.00 | 0.00 | 0.00 | 0.00 | 2646.36 | 0.00 |

### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): etf11_rp

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | 0.93 | -0.09 [-0.32, +0.14] p=0.436 |
| Buy&Hold | 0.97 | -0.05 [-0.35, +0.27] p=0.810 |
| TSMOM(12-1) | 0.50 | -0.52 [-0.89, -0.15] p=0.009 |
| TSMOM(L/S) | 0.29 | -0.73 [-1.74, +0.28] p=0.152 |
| Carry | 0.00 | -1.02 [-1.92, -0.16] p=0.023 |
| SMA(20/50) | 1.31 | +0.29 [-0.19, +0.77] p=0.239 |
| MACD | 0.85 | -0.17 [-0.86, +0.51] p=0.621 |
| KDJ+RSI | 0.49 | -0.54 [-1.09, +0.20] p=0.112 |
| ZMR | 0.26 | -0.76 [-1.34, -0.06] p=0.023 |

### mean capital share per sleeve: etf11_rp

| index | SPY | EFA | EEM | IWM | TLT | IEF | LQD | HYG | GLD | DBC | VNQ |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| mean share | 0.060 | 0.056 | 0.040 | 0.047 | 0.099 | 0.246 | 0.134 | 0.128 | 0.078 | 0.063 | 0.050 |

### portfolio table, etf11_equal: 11 sleeves, equal, 2016-01-04 -> 2021-12-31, provenance 3f80a69 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 40.74 | 5.87 | 5.10 | 0.96 | 2.35 | 8.55 | 0.69 | 71.94 |
| Buy&Hold | 75.70 | 9.86 | 9.92 | 0.90 | 2.21 | 21.69 | 0.45 | 100.00 |
| B&H vol-target | 57.85 | 7.92 | 6.75 | 1.02 | 2.50 | 11.44 | 0.69 | 92.71 |
| SMA(20/50) | 62.61 | 8.45 | 5.85 | 1.26 | 3.07 | 4.81 | 1.76 | 65.92 |
| MACD | 37.39 | 5.44 | 5.46 | 0.83 | 2.02 | 6.91 | 0.79 | 51.22 |
| KDJ+RSI | 30.97 | 4.61 | 7.32 | 0.52 | 1.28 | 19.64 | 0.23 | 33.18 |
| ZMR | 18.74 | 2.91 | 7.69 | 0.29 | 0.71 | 19.68 | 0.15 | 29.42 |
| TSMOM(12-1) | 24.98 | 3.79 | 5.36 | 0.55 | 1.34 | 9.85 | 0.39 | 64.31 |
| TSMOM(L/S) | 11.31 | 1.80 | 4.51 | 0.21 | 0.51 | 6.04 | 0.30 | 62.87 |
| Carry | 5.80 | 0.95 | 0.00 | 0.00 | 0.00 | 0.00 | 2646.36 | 0.00 |

### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): etf11_equal

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | 0.96 | -0.06 [-0.30, +0.18] p=0.608 |
| Buy&Hold | 0.90 | -0.12 [-0.46, +0.24] p=0.566 |
| TSMOM(12-1) | 0.55 | -0.48 [-0.86, -0.08] p=0.020 |
| TSMOM(L/S) | 0.21 | -0.81 [-1.94, +0.31] p=0.159 |
| Carry | 0.00 | -1.02 [-1.90, -0.17] p=0.022 |
| SMA(20/50) | 1.26 | +0.23 [-0.29, +0.76] p=0.379 |
| MACD | 0.83 | -0.20 [-0.91, +0.51] p=0.599 |
| KDJ+RSI | 0.52 | -0.50 [-1.09, +0.38] p=0.201 |
| ZMR | 0.29 | -0.73 [-1.32, +0.02] p=0.033 |

### portfolio table, fx15_rp: 15 sleeves, risk_parity, 2016-01-04 -> 2021-12-31, provenance 3f80a69 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 4.27 | 0.70 | 2.22 | -0.10 | -0.25 | 3.06 | 0.23 | 64.27 |
| Buy&Hold | 5.52 | 0.90 | 1.83 | -0.02 | -0.04 | 3.74 | 0.24 | 99.40 |
| B&H vol-target | 4.84 | 0.79 | 1.77 | -0.08 | -0.20 | 3.58 | 0.22 | 99.08 |
| SMA(20/50) | -2.41 | -0.40 | 3.58 | -0.36 | -0.88 | 6.95 | -0.06 | 98.57 |
| MACD | 0.13 | 0.02 | 3.60 | -0.24 | -0.58 | 6.79 | 0.00 | 99.00 |
| KDJ+RSI | 26.70 | 4.01 | 3.38 | 0.90 | 2.21 | 5.43 | 0.74 | 101.24 |
| ZMR | 12.59 | 1.99 | 3.48 | 0.31 | 0.77 | 6.40 | 0.31 | 79.99 |
| TSMOM(12-1) | -4.30 | -0.73 | 3.60 | -0.45 | -1.10 | 7.14 | -0.10 | 98.59 |
| TSMOM(L/S) | -3.16 | -0.53 | 2.76 | -0.52 | -1.28 | 7.60 | -0.07 | 62.65 |
| Carry | 6.86 | 1.11 | 1.27 | 0.13 | 0.33 | 2.18 | 0.51 | 30.03 |

### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): fx15_rp

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | -0.10 | -0.02 [-1.01, +0.99] p=0.970 |
| Buy&Hold | -0.02 | +0.06 [-0.04, +0.17] p=0.246 |
| TSMOM(12-1) | -0.45 | -0.37 [-1.43, +0.73] p=0.502 |
| TSMOM(L/S) | -0.52 | -0.44 [-1.50, +0.69] p=0.408 |
| Carry | 0.13 | +0.21 [-0.78, +1.21] p=0.695 |
| SMA(20/50) | -0.36 | -0.28 [-1.33, +0.73] p=0.588 |
| MACD | -0.24 | -0.16 [-1.14, +0.90] p=0.766 |
| KDJ+RSI | 0.90 | +0.98 [-0.13, +2.10] p=0.082 |
| ZMR | 0.31 | +0.39 [-0.77, +1.55] p=0.501 |

### mean capital share per sleeve: fx15_rp

| index | EURUSD | USDJPY | GBPUSD | AUDUSD | USDCAD | NZDUSD | USDCHF | EURGBP | EURJPY | GBPJPY | AUDJPY | EURCHF | AUDNZD | CADJPY | EURAUD |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| mean share | 0.049 | 0.038 | 0.066 | 0.053 | 0.137 | 0.075 | 0.133 | 0.086 | 0.023 | 0.025 | 0.023 | 0.043 | 0.102 | 0.036 | 0.111 |

### portfolio table, core15_rp: 15 sleeves, risk_parity, 2016-01-04 -> 2021-12-31, provenance 3f80a69 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 27.49 | 4.12 | 3.25 | 0.97 | 2.38 | 4.08 | 1.01 | 64.45 |
| Buy&Hold | 39.17 | 5.65 | 4.40 | 1.06 | 2.59 | 5.56 | 1.02 | 100.07 |
| B&H vol-target | 25.69 | 3.87 | 3.42 | 0.85 | 2.09 | 4.52 | 0.86 | 93.97 |
| SMA(20/50) | 34.81 | 5.09 | 4.39 | 0.94 | 2.30 | 4.38 | 1.16 | 91.07 |
| MACD | 8.95 | 1.44 | 4.04 | 0.14 | 0.34 | 8.33 | 0.17 | 86.85 |
| KDJ+RSI | 34.04 | 4.99 | 4.05 | 0.99 | 2.43 | 6.27 | 0.80 | 83.77 |
| ZMR | 26.03 | 3.92 | 4.02 | 0.74 | 1.82 | 8.08 | 0.49 | 65.68 |
| TSMOM(12-1) | 16.69 | 2.60 | 4.11 | 0.42 | 1.02 | 7.77 | 0.33 | 90.83 |
| TSMOM(L/S) | 6.96 | 1.12 | 3.18 | 0.07 | 0.17 | 5.04 | 0.22 | 62.24 |
| Carry | 7.49 | 1.21 | 1.08 | 0.24 | 0.60 | 1.38 | 0.88 | 19.76 |

### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): core15_rp

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | 0.97 | +0.12 [-0.65, +0.92] p=0.762 |
| Buy&Hold | 1.06 | +0.20 [-0.04, +0.45] p=0.107 |
| TSMOM(12-1) | 0.42 | -0.44 [-1.29, +0.41] p=0.315 |
| TSMOM(L/S) | 0.07 | -0.78 [-1.75, +0.19] p=0.110 |
| Carry | 0.24 | -0.61 [-1.71, +0.50] p=0.275 |
| SMA(20/50) | 0.94 | +0.08 [-0.73, +0.90] p=0.832 |
| MACD | 0.14 | -0.71 [-1.71, +0.26] p=0.159 |
| KDJ+RSI | 0.99 | +0.14 [-0.88, +1.15] p=0.798 |
| ZMR | 0.74 | -0.11 [-1.17, +0.95] p=0.840 |

### mean capital share per sleeve: core15_rp

| index | AAPL | NVDA | MSFT | META | GOOGL | AMZN | JPM | XOM | JNJ | SPY | EURUSD | USDJPY | GBPUSD | AUDUSD | USDCAD |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| mean share | 0.021 | 0.013 | 0.021 | 0.019 | 0.021 | 0.020 | 0.025 | 0.030 | 0.041 | 0.032 | 0.144 | 0.169 | 0.105 | 0.111 | 0.228 |

### portfolio table, all26_rp: 26 sleeves, risk_parity, class budgets {'equity': 0.6, 'fx': 0.4}, 2016-01-04 -> 2021-12-31, provenance 3f80a69 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 11.66 | 1.85 | 1.99 | 0.46 | 1.12 | 3.22 | 0.57 | 67.17 |
| Buy&Hold | 15.30 | 2.39 | 2.16 | 0.67 | 1.64 | 3.45 | 0.69 | 98.38 |
| B&H vol-target | 13.44 | 2.12 | 1.95 | 0.60 | 1.47 | 2.51 | 0.84 | 97.18 |
| SMA(20/50) | 10.74 | 1.71 | 2.78 | 0.28 | 0.70 | 3.74 | 0.46 | 87.27 |
| MACD | 7.50 | 1.21 | 2.73 | 0.11 | 0.27 | 5.47 | 0.22 | 82.81 |
| KDJ+RSI | 23.70 | 3.60 | 2.75 | 0.96 | 2.34 | 6.61 | 0.54 | 79.86 |
| ZMR | 11.92 | 1.89 | 2.82 | 0.34 | 0.84 | 7.73 | 0.24 | 63.68 |
| TSMOM(12-1) | 1.81 | 0.30 | 2.88 | -0.21 | -0.52 | 5.71 | 0.05 | 88.20 |
| TSMOM(L/S) | 1.17 | 0.19 | 2.27 | -0.32 | -0.78 | 6.00 | 0.03 | 62.79 |
| Carry | 6.71 | 1.09 | 0.86 | 0.16 | 0.40 | 1.60 | 0.68 | 20.04 |

### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): all26_rp

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | 0.46 | -0.14 [-0.87, +0.59] p=0.690 |
| Buy&Hold | 0.67 | +0.07 [-0.16, +0.28] p=0.558 |
| TSMOM(12-1) | -0.21 | -0.81 [-1.72, +0.09] p=0.079 |
| TSMOM(L/S) | -0.32 | -0.92 [-2.11, +0.36] p=0.142 |
| Carry | 0.16 | -0.44 [-1.45, +0.55] p=0.394 |
| SMA(20/50) | 0.28 | -0.32 [-1.26, +0.63] p=0.517 |
| MACD | 0.11 | -0.49 [-1.56, +0.61] p=0.377 |
| KDJ+RSI | 0.96 | +0.35 [-0.58, +1.37] p=0.482 |
| ZMR | 0.34 | -0.26 [-1.25, +0.79] p=0.632 |

### mean capital share per sleeve: all26_rp

| index | SPY | EFA | EEM | IWM | TLT | IEF | LQD | HYG | GLD | DBC | VNQ | EURUSD | USDJPY | GBPUSD | AUDUSD | USDCAD | NZDUSD | USDCHF | EURGBP | EURJPY | GBPJPY | AUDJPY | EURCHF | AUDNZD | CADJPY | EURAUD |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| mean share | 0.020 | 0.018 | 0.013 | 0.016 | 0.031 | 0.076 | 0.044 | 0.041 | 0.025 | 0.020 | 0.016 | 0.035 | 0.027 | 0.044 | 0.036 | 0.094 | 0.048 | 0.086 | 0.059 | 0.017 | 0.019 | 0.016 | 0.032 | 0.069 | 0.025 | 0.075 |

# v0.9 phase 0: attribution of the desk's portfolio Sharpe (v0.8 files, 15 core sleeves, 260 periods/year)

## design (n = 1564 days)

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

## holdout (n = 1167 days)

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

# v0.9 phase 3: strategy combination, 2016-01-04 -> 2021-12-31, 260 periods/year

## streams (excess returns)

| stream | Sharpe | t | vol % | excess return %/yr | MDD % | n |
|:--|--:|--:|--:|--:|--:|--:|
| beta | 1.02 | 2.50 | 4.91 | +5.00 | 8.71 | 1564 |
| trend_etf | 0.50 | 1.22 | 4.32 | +2.16 | 8.61 | 1564 |
| trend_fx | -0.45 | -1.10 | 3.60 | -1.61 | 12.17 | 1564 |
| carry | 0.13 | 0.32 | 1.27 | +0.17 | 2.25 | 1564 |

## correlation of daily excess returns

| | beta | trend_etf | trend_fx | carry |
|:--|--:|--:|--:|--:|
| beta | 1.00 | 0.89 | 0.00 | 0.05 |
| trend_etf | 0.89 | 1.00 | 0.04 | 0.04 |
| trend_fx | 0.00 | 0.04 | 1.00 | -0.26 |
| carry | 0.05 | 0.04 | -0.26 | 1.00 |

## books (risk parity across streams; block-bootstrap Sharpe difference vs the base)

| book | mean shares | Sharpe | vol % | MDD % | Sharpe − base [95% CI] p | with DD overlay: Sharpe / MDD % / days halved | overlay − base [95% CI] p |
|:--|:--|--:|--:|--:|:--|:--|:--|
| beta (base) | {'beta': 1.0} | 1.02 | 4.91 | 8.71 | +0.00 [+0.00, +0.00] p 1.000 | 1.02 / 8.71 / 0% | +0.00 [+0.00, +0.00] p 1.000 |
| beta + trend_etf | {'beta': 0.466, 'trend_etf': 0.534} | 0.78 | 4.47 | 8.22 | -0.24 [-0.42, -0.05] p 0.012 | 0.78 / 8.22 / 0% | -0.24 [-0.42, -0.05] p 0.012 |
| beta + carry | {'beta': 0.22, 'carry': 0.78} | 1.02 | 1.50 | 3.44 | +0.00 [-0.57, +0.54] p 0.996 | 1.02 / 3.44 / 0% | +0.00 [-0.57, +0.54] p 0.996 |
| beta + trend_etf + carry | {'beta': 0.145, 'trend_etf': 0.167, 'carry': 0.688} | 0.88 | 1.64 | 3.89 | -0.14 [-0.59, +0.31] p 0.550 | 0.88 / 3.89 / 0% | -0.14 [-0.59, +0.31] p 0.550 |
| all four | {'beta': 0.107, 'trend_etf': 0.124, 'trend_fx': 0.203, 'carry': 0.566} | 0.56 | 1.35 | 2.61 | -0.45 [-1.04, +0.12] p 0.123 | 0.56 / 2.61 / 0% | -0.45 [-1.04, +0.12] p 0.123 |
| trend + carry (no beta) | {'trend_etf': 0.175, 'trend_fx': 0.22, 'carry': 0.605} | 0.10 | 1.24 | 2.56 | -0.91 [-1.67, -0.16] p 0.020 | 0.10 / 2.56 / 0% | -0.91 [-1.67, -0.16] p 0.020 |

