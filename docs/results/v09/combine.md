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

