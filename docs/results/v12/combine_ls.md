# v0.9 phase 3: strategy combination, 2008-07-01 -> 2021-12-31, 260 periods/year

## streams (excess returns)

| stream | Sharpe | t | vol % | excess return %/yr | MDD % | n |
|:--|--:|--:|--:|--:|--:|--:|
| beta | 0.87 | 3.21 | 5.25 | +4.57 | 9.89 | 3523 |
| trend_etf | 0.40 | 1.46 | 4.23 | +1.67 | 7.39 | 3523 |
| trend_fx | -0.13 | -0.47 | 3.49 | -0.44 | 14.43 | 3523 |
| carry | -0.05 | -0.18 | 2.15 | -0.11 | 8.57 | 3523 |

## correlation of daily excess returns

| | beta | trend_etf | trend_fx | carry |
|:--|--:|--:|--:|--:|
| beta | 1.00 | 0.30 | 0.01 | 0.06 |
| trend_etf | 0.30 | 1.00 | 0.22 | -0.15 |
| trend_fx | 0.01 | 0.22 | 1.00 | -0.34 |
| carry | 0.06 | -0.15 | -0.34 | 1.00 |

## books (risk parity across streams; block-bootstrap Sharpe difference vs the base)

| book | mean shares | Sharpe | vol % | MDD % | Sharpe − base [95% CI] p | with DD overlay: Sharpe / MDD % / days halved | overlay − base [95% CI] p |
|:--|:--|--:|--:|--:|:--|:--|:--|
| beta (base) | {'beta': 1.0} | 0.87 | 5.25 | 9.89 | +0.00 [+0.00, +0.00] p 1.000 | 0.87 / 9.89 / 0% | +0.00 [+0.00, +0.00] p 1.000 |
| beta + trend_etf | {'beta': 0.424, 'trend_etf': 0.576} | 0.81 | 3.71 | 5.94 | -0.06 [-0.38, +0.26] p 0.674 | 0.81 / 5.94 / 0% | -0.06 [-0.38, +0.26] p 0.674 |
| beta + carry | {'beta': 0.241, 'carry': 0.759} | 0.51 | 2.10 | 7.83 | -0.36 [-0.77, +0.06] p 0.094 | 0.51 / 7.83 / 0% | -0.36 [-0.77, +0.06] p 0.094 |
| beta + trend_etf + carry | {'beta': 0.167, 'trend_etf': 0.23, 'carry': 0.602} | 0.62 | 1.92 | 4.90 | -0.25 [-0.64, +0.15] p 0.225 | 0.62 / 4.90 / 0% | -0.25 [-0.64, +0.15] p 0.225 |
| all four | {'beta': 0.125, 'trend_etf': 0.168, 'trend_fx': 0.228, 'carry': 0.479} | 0.56 | 1.66 | 3.50 | -0.31 [-0.79, +0.16] p 0.195 | 0.56 / 3.50 / 0% | -0.31 [-0.79, +0.16] p 0.195 |
| trend + carry (no beta) | {'trend_etf': 0.206, 'trend_fx': 0.254, 'carry': 0.539} | 0.26 | 1.60 | 5.09 | -0.61 [-1.25, +0.03] p 0.062 | 0.26 / 5.09 / 0% | -0.61 [-1.25, +0.03] p 0.062 |

