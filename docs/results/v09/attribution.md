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
