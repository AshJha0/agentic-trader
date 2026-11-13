# v0.9 phase 3: strategy combination, 2009-10-01 -> 2021-12-31, 260 periods/year

## streams (excess returns)

| stream | Sharpe | t | vol % | excess return %/yr | MDD % | n |
|:--|--:|--:|--:|--:|--:|--:|
| beta | 0.93 | 3.26 | 5.02 | +4.66 | 9.98 | 3196 |
| trend_etf | 0.35 | 1.23 | 3.86 | +1.36 | 7.08 | 3196 |
| trend_fx | -0.26 | -0.90 | 3.11 | -0.80 | 13.83 | 3196 |
| carry | 0.07 | 0.26 | 1.73 | +0.13 | 5.95 | 3196 |

## correlation of daily excess returns

| | beta | trend_etf | trend_fx | carry |
|:--|--:|--:|--:|--:|
| beta | 1.00 | 0.32 | 0.00 | 0.07 |
| trend_etf | 0.32 | 1.00 | 0.10 | 0.04 |
| trend_fx | 0.00 | 0.10 | 1.00 | -0.09 |
| carry | 0.07 | 0.04 | -0.09 | 1.00 |

## books (risk parity across streams; block-bootstrap Sharpe difference vs the base)

| book | mean shares | Sharpe | vol % | MDD % | Sharpe − base [95% CI] p | with DD overlay: Sharpe / MDD % / days halved | overlay − base [95% CI] p |
|:--|:--|--:|--:|--:|:--|:--|:--|
| beta (base) | {'beta': 1.0} | 0.93 | 5.02 | 9.98 | +0.00 [+0.00, +0.00] p 1.000 | 0.93 / 9.98 / 0% | +0.00 [+0.00, +0.00] p 1.000 |
| beta + trend_etf | {'beta': 0.424, 'trend_etf': 0.576} | 0.86 | 3.51 | 5.76 | -0.07 [-0.42, +0.27] p 0.693 | 0.86 / 5.76 / 0% | -0.07 [-0.42, +0.27] p 0.693 |
| beta + carry | {'beta': 0.237, 'carry': 0.763} | 0.64 | 1.89 | 6.45 | -0.29 [-0.78, +0.16] p 0.220 | 0.64 / 6.45 / 0% | -0.29 [-0.78, +0.16] p 0.220 |
| beta + trend_etf + carry | {'beta': 0.167, 'trend_etf': 0.226, 'carry': 0.607} | 0.62 | 1.84 | 5.37 | -0.31 [-0.75, +0.12] p 0.173 | 0.62 / 5.37 / 0% | -0.31 [-0.75, +0.12] p 0.173 |
| all four | {'beta': 0.126, 'trend_etf': 0.167, 'trend_fx': 0.227, 'carry': 0.48} | 0.48 | 1.59 | 4.05 | -0.45 [-0.98, +0.08] p 0.096 | 0.48 / 4.05 / 0% | -0.45 [-0.98, +0.08] p 0.096 |
| trend + carry (no beta) | {'trend_etf': 0.207, 'trend_fx': 0.254, 'carry': 0.538} | 0.07 | 1.52 | 5.82 | -0.86 [-1.52, -0.15] p 0.014 | 0.07 / 5.82 / 0% | -0.86 [-1.52, -0.15] p 0.014 |

