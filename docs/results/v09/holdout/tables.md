> **FX re-run, 2026-11-13 (review D5 closed).** Every table on this page was re-measured from main
> 3f80a69, whose engine converts FX P&L to the USD account (the earlier tables booked a USD-base pair's
> return r where r / (1 + r) is due and left crosses unconverted). Source: `results/v09_fx_final/holdout/tables.md`. The re-run
> replaces the 2026-11-12 correction notice.

### portfolio table, etf11_rp: 11 sleeves, risk_parity, 2022-01-03 -> 2026-06-30, provenance 3f80a69 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 18.35 | 3.85 | 5.15 | -0.02 | -0.03 | 5.76 | 0.67 | 67.16 |
| Buy&Hold | 18.31 | 3.84 | 8.79 | 0.02 | 0.04 | 19.22 | 0.20 | 100.00 |
| B&H vol-target | 14.62 | 3.10 | 7.63 | -0.08 | -0.18 | 16.96 | 0.18 | 93.10 |
| SMA(20/50) | 14.67 | 3.11 | 5.25 | -0.15 | -0.31 | 8.81 | 0.35 | 57.78 |
| MACD | 20.81 | 4.33 | 5.20 | 0.07 | 0.16 | 7.79 | 0.56 | 49.48 |
| KDJ+RSI | 23.19 | 4.78 | 5.92 | 0.15 | 0.31 | 13.11 | 0.36 | 43.97 |
| ZMR | 12.95 | 2.76 | 5.70 | -0.19 | -0.41 | 13.99 | 0.20 | 35.22 |
| TSMOM(12-1) | 23.08 | 4.76 | 4.92 | 0.16 | 0.34 | 4.92 | 0.97 | 61.00 |
| TSMOM(L/S) | 8.75 | 1.90 | 4.63 | -0.43 | -0.91 | 8.94 | 0.21 | 65.14 |
| Carry | 19.47 | 4.07 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): etf11_rp

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | -0.02 | +0.07 [-0.27, +0.45] p=0.711 |
| Buy&Hold | 0.02 | +0.10 [-0.01, +0.22] p=0.076 |
| TSMOM(12-1) | 0.16 | +0.24 [-0.36, +0.87] p=0.430 |
| TSMOM(L/S) | -0.43 | -0.35 [-1.68, +1.03] p=0.612 |
| Carry | 0.00 | +0.08 [-0.83, +0.99] p=0.859 |
| SMA(20/50) | -0.15 | -0.07 [-0.70, +0.60] p=0.837 |
| MACD | 0.07 | +0.16 [-0.50, +0.77] p=0.632 |
| KDJ+RSI | 0.15 | +0.23 [-0.27, +0.73] p=0.384 |
| ZMR | -0.19 | -0.11 [-0.69, +0.47] p=0.714 |

### mean capital share per sleeve: etf11_rp

| index | SPY | EFA | EEM | IWM | TLT | IEF | LQD | HYG | GLD | DBC | VNQ |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| mean share | 0.068 | 0.063 | 0.060 | 0.047 | 0.084 | 0.170 | 0.120 | 0.146 | 0.087 | 0.099 | 0.057 |

### portfolio table, etf11_equal: 11 sleeves, equal, 2022-01-03 -> 2026-06-30, provenance 3f80a69 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 26.93 | 5.49 | 5.95 | 0.26 | 0.55 | 5.79 | 0.95 | 64.74 |
| Buy&Hold | 31.72 | 6.37 | 10.65 | 0.26 | 0.55 | 19.57 | 0.33 | 100.00 |
| B&H vol-target | 23.91 | 4.92 | 8.68 | 0.14 | 0.29 | 16.54 | 0.30 | 89.73 |
| SMA(20/50) | 19.53 | 4.08 | 6.42 | 0.03 | 0.07 | 9.80 | 0.42 | 57.90 |
| MACD | 26.14 | 5.34 | 6.27 | 0.23 | 0.48 | 9.09 | 0.59 | 50.29 |
| KDJ+RSI | 32.63 | 6.53 | 7.02 | 0.37 | 0.78 | 12.52 | 0.52 | 42.41 |
| ZMR | 16.57 | 3.49 | 6.89 | -0.05 | -0.10 | 13.73 | 0.25 | 34.42 |
| TSMOM(12-1) | 31.02 | 6.24 | 5.97 | 0.38 | 0.80 | 5.99 | 1.04 | 58.71 |
| TSMOM(L/S) | 12.96 | 2.77 | 5.24 | -0.21 | -0.45 | 8.76 | 0.32 | 62.10 |
| Carry | 19.47 | 4.07 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): etf11_equal

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | 0.26 | +0.12 [-0.21, +0.50] p=0.508 |
| Buy&Hold | 0.26 | +0.12 [-0.02, +0.27] p=0.098 |
| TSMOM(12-1) | 0.38 | +0.24 [-0.32, +0.84] p=0.415 |
| TSMOM(L/S) | -0.21 | -0.35 [-1.60, +0.94] p=0.592 |
| Carry | 0.00 | -0.14 [-1.06, +0.78] p=0.769 |
| SMA(20/50) | 0.03 | -0.10 [-0.72, +0.55] p=0.743 |
| MACD | 0.23 | +0.09 [-0.58, +0.72] p=0.805 |
| KDJ+RSI | 0.37 | +0.23 [-0.31, +0.76] p=0.413 |
| ZMR | -0.05 | -0.18 [-0.77, +0.40] p=0.553 |

### portfolio table, fx15_rp: 15 sleeves, risk_parity, 2022-01-03 -> 2026-06-30, provenance 3f80a69 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 22.13 | 4.56 | 2.41 | 0.21 | 0.44 | 2.14 | 2.13 | 67.42 |
| Buy&Hold | 23.73 | 4.86 | 1.63 | 0.48 | 1.01 | 1.42 | 3.41 | 87.57 |
| B&H vol-target | 24.28 | 4.97 | 1.69 | 0.52 | 1.10 | 1.42 | 3.49 | 91.83 |
| SMA(20/50) | 8.88 | 1.91 | 3.79 | -0.53 | -1.13 | 4.98 | 0.38 | 98.30 |
| MACD | 17.17 | 3.60 | 3.73 | -0.10 | -0.22 | 3.27 | 1.10 | 99.00 |
| KDJ+RSI | 32.20 | 6.42 | 3.54 | 0.65 | 1.38 | 4.17 | 1.54 | 100.82 |
| ZMR | 25.82 | 5.25 | 3.69 | 0.33 | 0.69 | 3.51 | 1.50 | 81.67 |
| TSMOM(12-1) | 25.23 | 5.14 | 3.59 | 0.31 | 0.65 | 4.49 | 1.15 | 97.28 |
| TSMOM(L/S) | 17.02 | 3.57 | 2.95 | -0.15 | -0.31 | 2.62 | 1.36 | 64.77 |
| Carry | 22.29 | 4.59 | 1.24 | 0.41 | 0.87 | 1.37 | 3.34 | 30.68 |

### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): fx15_rp

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | 0.21 | -0.31 [-1.46, +0.85] p=0.588 |
| Buy&Hold | 0.48 | -0.04 [-0.26, +0.12] p=0.677 |
| TSMOM(12-1) | 0.31 | -0.21 [-1.40, +1.00] p=0.724 |
| TSMOM(L/S) | -0.15 | -0.67 [-1.86, +0.50] p=0.263 |
| Carry | 0.41 | -0.11 [-1.21, +1.02] p=0.853 |
| SMA(20/50) | -0.53 | -1.05 [-2.27, +0.18] p=0.085 |
| MACD | -0.10 | -0.62 [-1.97, +0.68] p=0.359 |
| KDJ+RSI | 0.65 | +0.13 [-1.03, +1.28] p=0.827 |
| ZMR | 0.33 | -0.19 [-1.40, +1.01] p=0.759 |

### mean capital share per sleeve: fx15_rp

| index | EURUSD | USDJPY | GBPUSD | AUDUSD | USDCAD | NZDUSD | USDCHF | EURGBP | EURJPY | GBPJPY | AUDJPY | EURCHF | AUDNZD | CADJPY | EURAUD |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| mean share | 0.046 | 0.029 | 0.067 | 0.055 | 0.180 | 0.083 | 0.099 | 0.089 | 0.019 | 0.022 | 0.020 | 0.037 | 0.118 | 0.031 | 0.106 |

### portfolio table, core15_rp: 15 sleeves, risk_parity, 2022-01-03 -> 2026-06-30, provenance 3f80a69 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 28.78 | 5.80 | 3.58 | 0.48 | 1.01 | 4.09 | 1.42 | 64.27 |
| Buy&Hold | 44.45 | 8.54 | 3.62 | 1.18 | 2.50 | 4.03 | 2.12 | 89.69 |
| B&H vol-target | 37.42 | 7.34 | 2.58 | 1.21 | 2.57 | 2.50 | 2.94 | 86.12 |
| SMA(20/50) | 20.73 | 4.29 | 4.85 | 0.07 | 0.14 | 5.21 | 0.82 | 89.63 |
| MACD | 21.10 | 4.36 | 4.27 | 0.09 | 0.18 | 3.61 | 1.21 | 87.94 |
| KDJ+RSI | 36.19 | 7.12 | 4.65 | 0.65 | 1.37 | 7.95 | 0.90 | 87.45 |
| ZMR | 24.52 | 5.01 | 4.53 | 0.22 | 0.47 | 6.27 | 0.80 | 71.31 |
| TSMOM(12-1) | 33.09 | 6.58 | 4.66 | 0.53 | 1.13 | 5.68 | 1.16 | 87.89 |
| TSMOM(L/S) | 22.77 | 4.68 | 3.54 | 0.18 | 0.39 | 2.83 | 1.65 | 62.22 |
| Carry | 23.07 | 4.73 | 1.75 | 0.37 | 0.79 | 2.29 | 2.06 | 24.37 |

### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): core15_rp

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | 0.48 | -0.73 [-1.92, +0.41] p=0.228 |
| Buy&Hold | 1.18 | -0.03 [-0.29, +0.23] p=0.814 |
| TSMOM(12-1) | 0.53 | -0.68 [-1.90, +0.55] p=0.283 |
| TSMOM(L/S) | 0.18 | -1.03 [-2.38, +0.30] p=0.128 |
| Carry | 0.37 | -0.84 [-2.23, +0.63] p=0.265 |
| SMA(20/50) | 0.07 | -1.14 [-2.34, +0.02] p=0.059 |
| MACD | 0.09 | -1.12 [-2.35, +0.04] p=0.067 |
| KDJ+RSI | 0.65 | -0.56 [-1.61, +0.48] p=0.305 |
| ZMR | 0.22 | -0.99 [-2.03, +0.05] p=0.064 |

### mean capital share per sleeve: core15_rp

| index | AAPL | NVDA | MSFT | META | GOOGL | AMZN | JPM | XOM | JNJ | SPY | EURUSD | USDJPY | GBPUSD | AUDUSD | USDCAD |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| mean share | 0.018 | 0.011 | 0.018 | 0.012 | 0.015 | 0.013 | 0.022 | 0.031 | 0.050 | 0.024 | 0.126 | 0.128 | 0.117 | 0.112 | 0.302 |

### portfolio table, all26_rp: 26 sleeves, risk_parity, class budgets {'equity': 0.6, 'fx': 0.4}, 2022-01-03 -> 2026-06-30, provenance 3f80a69 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 21.49 | 4.43 | 2.24 | 0.17 | 0.36 | 1.67 | 2.66 | 67.16 |
| Buy&Hold | 22.83 | 4.69 | 2.42 | 0.26 | 0.55 | 3.56 | 1.32 | 89.64 |
| B&H vol-target | 22.33 | 4.59 | 2.23 | 0.24 | 0.50 | 3.13 | 1.47 | 91.37 |
| SMA(20/50) | 10.66 | 2.28 | 3.17 | -0.53 | -1.12 | 4.76 | 0.48 | 88.30 |
| MACD | 17.45 | 3.65 | 3.03 | -0.12 | -0.25 | 2.94 | 1.24 | 86.54 |
| KDJ+RSI | 30.11 | 6.04 | 2.97 | 0.65 | 1.37 | 4.90 | 1.23 | 86.71 |
| ZMR | 22.84 | 4.69 | 3.07 | 0.21 | 0.44 | 4.56 | 1.03 | 70.10 |
| TSMOM(12-1) | 24.58 | 5.02 | 2.98 | 0.32 | 0.68 | 3.56 | 1.41 | 88.57 |
| TSMOM(L/S) | 14.93 | 3.15 | 2.44 | -0.35 | -0.74 | 3.26 | 0.97 | 64.39 |
| Carry | 21.77 | 4.49 | 0.96 | 0.42 | 0.90 | 1.04 | 4.30 | 23.64 |

### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): all26_rp

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | 0.17 | -0.07 [-1.05, +0.93] p=0.894 |
| Buy&Hold | 0.26 | +0.02 [-0.15, +0.18] p=0.808 |
| TSMOM(12-1) | 0.32 | +0.08 [-1.11, +1.30] p=0.898 |
| TSMOM(L/S) | -0.35 | -0.59 [-2.04, +0.83] p=0.427 |
| Carry | 0.42 | +0.19 [-1.09, +1.53] p=0.783 |
| SMA(20/50) | -0.53 | -0.77 [-1.91, +0.39] p=0.185 |
| MACD | -0.12 | -0.36 [-1.66, +0.92] p=0.589 |
| KDJ+RSI | 0.65 | +0.41 [-0.62, +1.40] p=0.440 |
| ZMR | 0.21 | -0.03 [-1.04, +1.03] p=0.962 |

### mean capital share per sleeve: all26_rp

| index | SPY | EFA | EEM | IWM | TLT | IEF | LQD | HYG | GLD | DBC | VNQ | EURUSD | USDJPY | GBPUSD | AUDUSD | USDCAD | NZDUSD | USDCHF | EURGBP | EURJPY | GBPJPY | AUDJPY | EURCHF | AUDNZD | CADJPY | EURAUD |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| mean share | 0.016 | 0.015 | 0.014 | 0.011 | 0.020 | 0.042 | 0.028 | 0.035 | 0.020 | 0.024 | 0.014 | 0.038 | 0.024 | 0.051 | 0.042 | 0.132 | 0.058 | 0.072 | 0.070 | 0.016 | 0.019 | 0.017 | 0.033 | 0.089 | 0.025 | 0.076 |

# v0.9 phase 3: strategy combination, 2022-01-03 -> 2026-06-30, 260 periods/year

## streams (excess returns)

| stream | Sharpe | t | vol % | excess return %/yr | MDD % | n |
|:--|--:|--:|--:|--:|--:|--:|
| beta | -0.09 | -0.18 | 7.61 | -0.66 | 19.38 | 1167 |
| trend_etf | 0.16 | 0.33 | 4.91 | +0.76 | 10.47 | 1167 |
| trend_fx | 0.30 | 0.64 | 3.59 | +1.09 | 6.06 | 1167 |
| carry | 0.41 | 0.87 | 1.24 | +0.51 | 2.38 | 1167 |

## correlation of daily excess returns

| | beta | trend_etf | trend_fx | carry |
|:--|--:|--:|--:|--:|
| beta | 1.00 | 0.79 | -0.01 | 0.01 |
| trend_etf | 0.79 | 1.00 | 0.00 | 0.00 |
| trend_fx | -0.01 | 0.00 | 1.00 | 0.28 |
| carry | 0.01 | 0.00 | 0.28 | 1.00 |

## books (risk parity across streams; block-bootstrap Sharpe difference vs the base)

| book | mean shares | Sharpe | vol % | MDD % | Sharpe − base [95% CI] p | with DD overlay: Sharpe / MDD % / days halved | overlay − base [95% CI] p |
|:--|:--|--:|--:|--:|:--|:--|:--|
| beta (base) | {'beta': 1.0} | -0.09 | 7.61 | 19.38 | +0.00 [+0.00, +0.00] p 1.000 | -0.17 / 21.50 / 1% | -0.08 [-0.19, +0.00] p 0.084 |
| beta + trend_etf | {'beta': 0.396, 'trend_etf': 0.604} | -0.01 | 5.51 | 14.97 | +0.08 [-0.33, +0.50] p 0.709 | -0.01 / 14.97 / 0% | +0.08 [-0.33, +0.50] p 0.709 |
| beta + carry | {'beta': 0.172, 'carry': 0.828} | -0.29 | 2.01 | 6.33 | -0.21 [-0.93, +0.58] p 0.596 | -0.29 / 6.33 / 0% | -0.21 [-0.93, +0.58] p 0.596 |
| beta + trend_etf + carry | {'beta': 0.11, 'trend_etf': 0.192, 'carry': 0.698} | -0.27 | 1.88 | 6.54 | -0.18 [-0.85, +0.54] p 0.608 | -0.27 / 6.54 / 0% | -0.18 [-0.85, +0.54] p 0.608 |
| all four | {'beta': 0.087, 'trend_etf': 0.161, 'trend_fx': 0.202, 'carry': 0.55} | -0.18 | 1.68 | 4.48 | -0.09 [-0.86, +0.73] p 0.830 | -0.18 / 4.48 / 0% | -0.09 [-0.86, +0.73] p 0.830 |
| trend + carry (no beta) | {'trend_etf': 0.208, 'trend_fx': 0.217, 'carry': 0.576} | 0.23 | 1.33 | 2.63 | +0.31 [-0.82, +1.53] p 0.613 | 0.23 / 2.63 / 0% | +0.31 [-0.82, +1.53] p 0.613 |

