> **FX re-run, 2026-11-13 (review D5 closed).** Every table on this page was re-measured from main
> 3f80a69, whose engine converts FX P&L to the USD account (the earlier tables booked a USD-base pair's
> return r where r / (1 + r) is due and left crosses unconverted). Source: `results/v12_fx_final_2009/tables.md`. The re-run
> replaces the 2026-11-12 correction notice.
> The v0.12 period now starts 2009-10-01, not 2008-07-01: the bar check refuses the 2008 EUR/USD data gap inside the 400-day lookback, so the first scorable day moves forward. core15 is not on this page (it fails the bar check on META in 2012; it was not on the earlier page either).

### portfolio table, etf11_rp: 11 sleeves, risk_parity, 2009-10-01 -> 2021-12-31, provenance 3f80a69 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 60.55 | 3.94 | 3.84 | 0.90 | 3.14 | 7.84 | 0.50 | 73.43 |
| Buy&Hold | 109.39 | 6.22 | 5.94 | 0.96 | 3.37 | 14.55 | 0.43 | 100.00 |
| B&H vol-target | 85.59 | 5.18 | 5.03 | 0.93 | 3.26 | 9.93 | 0.52 | 95.44 |
| SMA(20/50) | 71.93 | 4.53 | 4.42 | 0.91 | 3.19 | 6.43 | 0.70 | 65.43 |
| MACD | 39.96 | 2.79 | 3.67 | 0.63 | 2.21 | 6.38 | 0.44 | 50.64 |
| KDJ+RSI | 46.66 | 3.18 | 4.39 | 0.62 | 2.18 | 12.06 | 0.26 | 36.78 |
| ZMR | 23.98 | 1.77 | 4.49 | 0.30 | 1.06 | 12.00 | 0.15 | 30.66 |
| TSMOM(12-1) | 61.71 | 4.01 | 4.39 | 0.80 | 2.81 | 7.47 | 0.54 | 71.42 |
| TSMOM(L/S) | 24.45 | 1.80 | 3.87 | 0.35 | 1.23 | 5.39 | 0.33 | 66.03 |
| Carry | 6.26 | 0.50 | 0.00 | 0.00 | 0.00 | 0.00 | 1392.63 | 0.00 |

### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): etf11_rp

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | 0.90 | -0.04 [-0.20, +0.13] p=0.682 |
| Buy&Hold | 0.96 | +0.03 [-0.16, +0.20] p=0.744 |
| TSMOM(12-1) | 0.80 | -0.13 [-0.39, +0.14] p=0.318 |
| TSMOM(L/S) | 0.35 | -0.58 [-1.24, +0.08] p=0.081 |
| Carry | 0.00 | -0.93 [-1.54, -0.35] p=0.003 |
| SMA(20/50) | 0.91 | -0.02 [-0.39, +0.34] p=0.910 |
| MACD | 0.63 | -0.30 [-0.81, +0.16] p=0.222 |
| KDJ+RSI | 0.62 | -0.31 [-0.70, +0.15] p=0.159 |
| ZMR | 0.30 | -0.63 [-1.05, -0.16] p=0.006 |

### mean capital share per sleeve: etf11_rp

| index | SPY | EFA | EEM | IWM | TLT | IEF | LQD | HYG | GLD | DBC | VNQ |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| mean share | 0.061 | 0.052 | 0.040 | 0.047 | 0.106 | 0.238 | 0.146 | 0.126 | 0.070 | 0.064 | 0.049 |

### portfolio table, etf11_equal: 11 sleeves, equal, 2009-10-01 -> 2021-12-31, provenance 3f80a69 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 64.67 | 4.16 | 5.04 | 0.74 | 2.57 | 9.56 | 0.44 | 68.37 |
| Buy&Hold | 157.43 | 8.03 | 9.82 | 0.79 | 2.75 | 21.69 | 0.37 | 100.00 |
| B&H vol-target | 106.98 | 6.12 | 7.03 | 0.81 | 2.83 | 13.41 | 0.46 | 91.40 |
| SMA(20/50) | 83.66 | 5.09 | 6.22 | 0.75 | 2.62 | 12.78 | 0.40 | 63.87 |
| MACD | 60.10 | 3.92 | 5.63 | 0.62 | 2.18 | 7.83 | 0.50 | 51.32 |
| KDJ+RSI | 70.10 | 4.44 | 6.94 | 0.59 | 2.06 | 19.64 | 0.23 | 35.44 |
| ZMR | 36.93 | 2.60 | 7.34 | 0.32 | 1.12 | 19.68 | 0.13 | 31.01 |
| TSMOM(12-1) | 70.13 | 4.44 | 5.72 | 0.70 | 2.45 | 9.85 | 0.45 | 66.26 |
| TSMOM(L/S) | 19.71 | 1.48 | 4.67 | 0.23 | 0.81 | 6.56 | 0.23 | 62.90 |
| Carry | 6.26 | 0.50 | 0.00 | 0.00 | 0.00 | 0.00 | 1392.63 | 0.00 |

### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): etf11_equal

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | 0.74 | -0.07 [-0.25, +0.11] p=0.419 |
| Buy&Hold | 0.79 | -0.02 [-0.23, +0.17] p=0.834 |
| TSMOM(12-1) | 0.70 | -0.11 [-0.36, +0.14] p=0.386 |
| TSMOM(L/S) | 0.23 | -0.58 [-1.28, +0.14] p=0.115 |
| Carry | 0.00 | -0.81 [-1.43, -0.23] p=0.007 |
| SMA(20/50) | 0.75 | -0.06 [-0.43, +0.30] p=0.748 |
| MACD | 0.62 | -0.19 [-0.67, +0.27] p=0.443 |
| KDJ+RSI | 0.59 | -0.22 [-0.64, +0.26] p=0.347 |
| ZMR | 0.32 | -0.49 [-0.89, -0.03] p=0.028 |

### portfolio table, fx15_rp: 15 sleeves, risk_parity, 2009-10-01 -> 2021-12-31, provenance 3f80a69 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 0.26 | 0.02 | 2.94 | -0.15 | -0.52 | 11.07 | 0.00 | 64.04 |
| Buy&Hold | -5.87 | -0.49 | 2.87 | -0.33 | -1.16 | 13.58 | -0.04 | 98.09 |
| B&H vol-target | -8.37 | -0.71 | 2.68 | -0.44 | -1.53 | 15.36 | -0.05 | 97.26 |
| SMA(20/50) | -6.51 | -0.55 | 4.03 | -0.24 | -0.84 | 10.69 | -0.05 | 97.87 |
| MACD | -0.25 | -0.02 | 4.13 | -0.10 | -0.37 | 8.22 | -0.00 | 98.88 |
| KDJ+RSI | 39.30 | 2.73 | 3.83 | 0.59 | 2.08 | 7.98 | 0.34 | 101.27 |
| ZMR | 17.64 | 1.33 | 4.03 | 0.22 | 0.79 | 6.48 | 0.21 | 80.60 |
| TSMOM(12-1) | -6.58 | -0.55 | 3.87 | -0.25 | -0.88 | 11.68 | -0.05 | 97.61 |
| TSMOM(L/S) | -4.26 | -0.35 | 3.11 | -0.26 | -0.90 | 8.58 | -0.04 | 63.87 |
| Carry | 7.79 | 0.61 | 1.73 | 0.07 | 0.26 | 5.31 | 0.12 | 28.19 |

### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): fx15_rp

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | -0.15 | +0.29 [-0.32, +0.91] p=0.322 |
| Buy&Hold | -0.33 | +0.11 [-0.01, +0.24] p=0.090 |
| TSMOM(12-1) | -0.25 | +0.18 [-0.60, +0.93] p=0.637 |
| TSMOM(L/S) | -0.26 | +0.18 [-0.55, +0.90] p=0.621 |
| Carry | 0.07 | +0.51 [-0.08, +1.16] p=0.099 |
| SMA(20/50) | -0.24 | +0.20 [-0.53, +0.87] p=0.570 |
| MACD | -0.10 | +0.33 [-0.36, +1.01] p=0.332 |
| KDJ+RSI | 0.59 | +1.03 [+0.29, +1.69] p=0.006 |
| ZMR | 0.22 | +0.66 [-0.08, +1.34] p=0.068 |

### mean capital share per sleeve: fx15_rp

| index | EURUSD | USDJPY | GBPUSD | AUDUSD | USDCAD | NZDUSD | USDCHF | EURGBP | EURJPY | GBPJPY | AUDJPY | EURCHF | AUDNZD | CADJPY | EURAUD |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| mean share | 0.047 | 0.037 | 0.072 | 0.053 | 0.146 | 0.073 | 0.133 | 0.082 | 0.021 | 0.025 | 0.022 | 0.050 | 0.102 | 0.035 | 0.103 |

_core15_rp.json missing_

### portfolio table, all26_rp: 26 sleeves, risk_parity, class budgets {'equity': 0.6, 'fx': 0.4}, 2009-10-01 -> 2021-12-31, provenance 3f80a69 clean

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 14.91 | 1.14 | 2.46 | 0.27 | 0.95 | 7.52 | 0.15 | 66.36 |
| Buy&Hold | 17.44 | 1.32 | 2.73 | 0.31 | 1.09 | 7.92 | 0.17 | 97.49 |
| B&H vol-target | 12.26 | 0.95 | 2.48 | 0.19 | 0.67 | 8.86 | 0.11 | 95.69 |
| SMA(20/50) | 14.57 | 1.11 | 3.15 | 0.21 | 0.73 | 5.15 | 0.22 | 86.63 |
| MACD | 10.89 | 0.84 | 3.06 | 0.13 | 0.45 | 5.55 | 0.15 | 82.51 |
| KDJ+RSI | 40.13 | 2.78 | 2.97 | 0.77 | 2.70 | 6.70 | 0.42 | 79.83 |
| ZMR | 17.50 | 1.32 | 3.14 | 0.28 | 0.96 | 7.77 | 0.17 | 63.94 |
| TSMOM(12-1) | 10.98 | 0.85 | 3.09 | 0.13 | 0.45 | 5.70 | 0.15 | 88.43 |
| TSMOM(L/S) | 4.84 | 0.39 | 2.55 | -0.03 | -0.11 | 6.11 | 0.06 | 63.90 |
| Carry | 7.21 | 0.57 | 1.19 | 0.06 | 0.23 | 3.71 | 0.15 | 18.72 |

### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): all26_rp

| stream | Sharpe | Sharpe - B&H vol-target [95% CI] p |
|:--|--:|:--|
| AgenticTrader | 0.27 | +0.08 [-0.39, +0.52] p=0.731 |
| Buy&Hold | 0.31 | +0.12 [+0.01, +0.24] p=0.047 |
| TSMOM(12-1) | 0.13 | -0.06 [-0.82, +0.63] p=0.867 |
| TSMOM(L/S) | -0.03 | -0.22 [-1.09, +0.56] p=0.595 |
| Carry | 0.06 | -0.13 [-0.68, +0.44] p=0.644 |
| SMA(20/50) | 0.21 | +0.02 [-0.73, +0.71] p=0.962 |
| MACD | 0.13 | -0.06 [-0.87, +0.68] p=0.866 |
| KDJ+RSI | 0.77 | +0.58 [-0.17, +1.26] p=0.119 |
| ZMR | 0.28 | +0.08 [-0.66, +0.76] p=0.809 |

### mean capital share per sleeve: all26_rp

| index | SPY | EFA | EEM | IWM | TLT | IEF | LQD | HYG | GLD | DBC | VNQ | EURUSD | USDJPY | GBPUSD | AUDUSD | USDCAD | NZDUSD | USDCHF | EURGBP | EURJPY | GBPJPY | AUDJPY | EURCHF | AUDNZD | CADJPY | EURAUD |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| mean share | 0.020 | 0.017 | 0.013 | 0.016 | 0.034 | 0.076 | 0.048 | 0.042 | 0.023 | 0.021 | 0.016 | 0.033 | 0.025 | 0.048 | 0.036 | 0.099 | 0.047 | 0.086 | 0.056 | 0.015 | 0.018 | 0.015 | 0.038 | 0.068 | 0.024 | 0.068 |
