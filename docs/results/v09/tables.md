### portfolio table, etf11_rp: 11 sleeves, risk_parity, 2016-01-04 -> 2021-12-31, provenance 9513d13 clean

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

### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): etf11_rp

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

### mean capital share per sleeve: etf11_rp

| index | SPY | EFA | EEM | IWM | TLT | IEF | LQD | HYG | GLD | DBC | VNQ |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| mean share | 0.060 | 0.056 | 0.040 | 0.047 | 0.099 | 0.246 | 0.134 | 0.128 | 0.078 | 0.063 | 0.050 |

### portfolio table, etf11_equal: 11 sleeves, equal, 2016-01-04 -> 2021-12-31, provenance 9513d13 clean

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

### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): etf11_equal

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

### portfolio table, fx15_rp: 15 sleeves, risk_parity, 2016-01-04 -> 2021-12-31, provenance 9513d13 clean

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

### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): fx15_rp

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

### mean capital share per sleeve: fx15_rp

| index | EURUSD | USDJPY | GBPUSD | AUDUSD | USDCAD | NZDUSD | USDCHF | EURGBP | EURJPY | GBPJPY | AUDJPY | EURCHF | AUDNZD | CADJPY | EURAUD |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| mean share | 0.049 | 0.038 | 0.066 | 0.053 | 0.137 | 0.075 | 0.133 | 0.086 | 0.023 | 0.025 | 0.023 | 0.043 | 0.102 | 0.036 | 0.111 |

### portfolio table, core15_rp: 15 sleeves, risk_parity, 2016-01-04 -> 2021-12-31, provenance 9513d13 clean

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

### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): core15_rp

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

### mean capital share per sleeve: core15_rp

| index | AAPL | NVDA | MSFT | META | GOOGL | AMZN | JPM | XOM | JNJ | SPY | EURUSD | USDJPY | GBPUSD | AUDUSD | USDCAD |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| mean share | 0.021 | 0.013 | 0.021 | 0.019 | 0.021 | 0.020 | 0.025 | 0.030 | 0.041 | 0.032 | 0.144 | 0.169 | 0.105 | 0.111 | 0.228 |

### portfolio table, all26_rp: 26 sleeves, risk_parity, class budgets {'equity': 0.6, 'fx': 0.4}, 2016-01-04 -> 2021-12-31, provenance 9513d13 clean

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

### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): all26_rp

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
| trend_fx | -0.44 | -1.09 | 3.59 | -1.59 | 12.14 | 1564 |
| carry | 0.13 | 0.32 | 1.27 | +0.17 | 2.39 | 1564 |

## correlation of daily excess returns

| | beta | trend_etf | trend_fx | carry |
|:--|--:|--:|--:|--:|
| beta | 1.00 | 0.89 | 0.00 | 0.06 |
| trend_etf | 0.89 | 1.00 | 0.04 | 0.04 |
| trend_fx | 0.00 | 0.04 | 1.00 | -0.26 |
| carry | 0.06 | 0.04 | -0.26 | 1.00 |

## books (risk parity across streams; block-bootstrap Sharpe difference vs the base)

| book | mean shares | Sharpe | vol % | MDD % | Sharpe − base [95% CI] p | with DD overlay: Sharpe / MDD % / days halved | overlay − base [95% CI] p |
|:--|:--|--:|--:|--:|:--|:--|:--|
| beta (base) | {'beta': 1.0} | 1.02 | 4.91 | 8.71 | +0.00 [+0.00, +0.00] p 1.000 | 1.02 / 8.71 / 0% | +0.00 [+0.00, +0.00] p 1.000 |
| beta + trend_etf | {'beta': 0.466, 'trend_etf': 0.534} | 0.78 | 4.47 | 8.22 | -0.24 [-0.42, -0.05] p 0.012 | 0.78 / 8.22 / 0% | -0.24 [-0.42, -0.05] p 0.012 |
| beta + carry | {'beta': 0.219, 'carry': 0.781} | 1.02 | 1.50 | 3.57 | +0.00 [-0.57, +0.55] p 1.000 | 1.02 / 3.57 / 0% | +0.00 [-0.57, +0.55] p 1.000 |
| beta + trend_etf + carry | {'beta': 0.145, 'trend_etf': 0.166, 'carry': 0.688} | 0.88 | 1.64 | 4.01 | -0.14 [-0.59, +0.33] p 0.564 | 0.88 / 4.01 / 0% | -0.14 [-0.59, +0.33] p 0.564 |
| all four | {'beta': 0.107, 'trend_etf': 0.123, 'trend_fx': 0.203, 'carry': 0.567} | 0.57 | 1.35 | 2.54 | -0.45 [-1.03, +0.12] p 0.118 | 0.57 / 2.54 / 0% | -0.45 [-1.03, +0.12] p 0.118 |
| trend + carry (no beta) | {'trend_etf': 0.174, 'trend_fx': 0.22, 'carry': 0.606} | 0.11 | 1.23 | 2.48 | -0.91 [-1.66, -0.16] p 0.016 | 0.11 / 2.48 / 0% | -0.91 [-1.66, -0.16] p 0.016 |

