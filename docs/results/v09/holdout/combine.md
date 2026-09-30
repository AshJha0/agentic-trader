# v0.9 phase 3: strategy combination, 2022-01-03 -> 2026-06-30, 260 periods/year

## streams (excess returns)

| stream | Sharpe | t | vol % | excess return %/yr | MDD % | n |
|:--|--:|--:|--:|--:|--:|--:|
| beta | -0.09 | -0.18 | 7.61 | -0.66 | 19.38 | 1167 |
| trend_etf | 0.16 | 0.33 | 4.91 | +0.76 | 10.47 | 1167 |
| trend_fx | 0.32 | 0.68 | 3.61 | +1.16 | 5.95 | 1167 |
| carry | 0.43 | 0.92 | 1.25 | +0.54 | 2.38 | 1167 |

## correlation of daily excess returns

| | beta | trend_etf | trend_fx | carry |
|:--|--:|--:|--:|--:|
| beta | 1.00 | 0.79 | -0.01 | 0.01 |
| trend_etf | 0.79 | 1.00 | 0.00 | 0.00 |
| trend_fx | -0.01 | 0.00 | 1.00 | 0.29 |
| carry | 0.01 | 0.00 | 0.29 | 1.00 |

## books (risk parity across streams; block-bootstrap Sharpe difference vs the base)

| book | mean shares | Sharpe | vol % | MDD % | Sharpe − base [95% CI] p | with DD overlay: Sharpe / MDD % / days halved | overlay − base [95% CI] p |
|:--|:--|--:|--:|--:|:--|:--|:--|
| beta (base) | {'beta': 1.0} | -0.09 | 7.61 | 19.38 | +0.00 [+0.00, +0.00] p 1.000 | -0.17 / 21.50 / 1% | -0.08 [-0.19, +0.00] p 0.052 |
| beta + trend_etf | {'beta': 0.396, 'trend_etf': 0.604} | -0.01 | 5.51 | 14.97 | +0.08 [-0.33, +0.50] p 0.704 | -0.01 / 14.97 / 0% | +0.08 [-0.33, +0.50] p 0.704 |
| beta + carry | {'beta': 0.173, 'carry': 0.827} | -0.27 | 2.02 | 6.31 | -0.19 [-0.91, +0.59] p 0.651 | -0.27 / 6.31 / 0% | -0.19 [-0.91, +0.59] p 0.651 |
| beta + trend_etf + carry | {'beta': 0.111, 'trend_etf': 0.193, 'carry': 0.697} | -0.25 | 1.89 | 6.49 | -0.16 [-0.82, +0.55] p 0.671 | -0.25 / 6.49 / 0% | -0.16 [-0.82, +0.55] p 0.671 |
| all four | {'beta': 0.088, 'trend_etf': 0.162, 'trend_fx': 0.203, 'carry': 0.548} | -0.15 | 1.69 | 4.38 | -0.07 [-0.85, +0.75] p 0.898 | -0.15 / 4.38 / 0% | -0.07 [-0.85, +0.75] p 0.898 |
| trend + carry (no beta) | {'trend_etf': 0.209, 'trend_fx': 0.218, 'carry': 0.574} | 0.25 | 1.34 | 2.57 | +0.34 [-0.79, +1.57] p 0.560 | 0.25 / 2.57 / 0% | +0.34 [-0.79, +1.57] p 0.560 |

