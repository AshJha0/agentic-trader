# v0.11 review measurement: every published table under the corrected engine

This page is written by `scripts/render_v11_doc.py` from `results/v11/tables.md`, which
`scripts/render_v08_tables.py --in results/v11` renders from the files
`scripts/measure_v08.py --out results/v11` wrote. No number on this page is typed. It is the
re-measurement after the tier-2 review ([CHANGELOG](../../CHANGELOG.md), "Unreleased —
v0.11"): EDGAR visible from the session whose close could know a filing, market impact priced
on the as-traded close, the aggressive risk analyst sized at 1.25× the vol-targeted weight,
the news analyst's confidence by the tone its headlines carry, evaluation rows at full
precision, Benjamini–Hochberg over the printed rows, and the deflated Sharpe on every
trial's portfolio Sharpe.

Conventions are those of the v0.8 section of [evaluation.md](evaluation.md): summary tables
report the median Sharpe across instruments; paired tables the mean difference with a 95%
bootstrap interval (`instruments` on core and extended, `clusters` on all 60), two-sided p
and the BH flag over the table's rows; on/off tables print p and no BH flag; Sharpe and
Sortino are on excess returns over the credited bill; `wins` counts the instruments where
the desk's value is the larger, whatever the metric. The two rule changes of v0.11 were
chosen on the 2016–2021 design period against their v0.8 counterparts, which are registered
trials in the table below; the holdout is reported, not chosen on.


Measured 2026-09-30 08:22:34 at commit `b21ec62` (clean tree), cpp backend, 3276 s.


## Headline, core (15)

#### summary: core (15), design

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| design | AgenticTrader | 15 | 0.67 | 98.41 | 14.66 | 11.09 | 60.97 |
| design | B&H vol-target | 15 | 0.69 | 128.28 | 20.17 | 13.60 | 80.51 |
| design | Buy&Hold | 15 | 0.73 | 415.17 | 32.83 | 21.81 | 99.10 |
| design | Carry | 15 | 0.00 | 6.98 | 1.63 | 0.89 | 9.32 |
| design | KDJ+RSI | 15 | 0.54 | 75.97 | 27.23 | 16.21 | 54.24 |
| design | MACD | 15 | 0.54 | 95.79 | 24.95 | 15.04 | 67.80 |
| design | SMA(20/50) | 15 | 0.64 | 172.49 | 23.14 | 16.67 | 78.78 |
| design | TSMOM(12-1) | 15 | 0.49 | 97.66 | 20.41 | 12.70 | 73.40 |
| design | ZMR | 15 | 0.41 | 47.07 | 27.75 | 15.56 | 44.42 |

#### summary: core (15), holdout

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| holdout | AgenticTrader | 15 | 0.35 | 48.71 | 14.54 | 11.52 | 57.08 |
| holdout | B&H vol-target | 15 | 0.52 | 60.63 | 18.98 | 14.13 | 73.67 |
| holdout | Buy&Hold | 15 | 0.51 | 98.41 | 31.64 | 23.40 | 97.39 |
| holdout | Carry | 15 | 0.00 | 21.42 | 1.61 | 1.10 | 10.86 |
| holdout | KDJ+RSI | 15 | 0.44 | 54.53 | 23.93 | 17.50 | 60.70 |
| holdout | MACD | 15 | 0.19 | 32.77 | 27.53 | 17.19 | 66.58 |
| holdout | SMA(20/50) | 15 | 0.36 | 52.13 | 25.04 | 17.20 | 72.99 |
| holdout | TSMOM(12-1) | 15 | 0.29 | 47.29 | 16.78 | 12.75 | 65.52 |
| holdout | ZMR | 15 | 0.22 | 37.62 | 21.72 | 16.02 | 49.57 |

#### head to head: core (15)

| period | baseline | agent wins | instruments | median Sharpe diff |
|:--|:--|--:|--:|--:|
| design | B&H vol-target | 7 | 15 | -0.04 |
| design | Buy&Hold | 10 | 15 | 0.05 |
| design | Carry | 12 | 15 | 0.67 |
| design | KDJ+RSI | 10 | 15 | 0.26 |
| design | MACD | 10 | 15 | 0.28 |
| design | SMA(20/50) | 7 | 15 | -0.03 |
| design | TSMOM(12-1) | 9 | 15 | 0.13 |
| design | ZMR | 12 | 15 | 0.30 |
| holdout | B&H vol-target | 5 | 15 | -0.08 |
| holdout | Buy&Hold | 7 | 15 | -0.00 |
| holdout | Carry | 10 | 15 | 0.35 |
| holdout | KDJ+RSI | 5 | 15 | -0.11 |
| holdout | MACD | 12 | 15 | 0.26 |
| holdout | SMA(20/50) | 11 | 15 | 0.29 |
| holdout | TSMOM(12-1) | 6 | 15 | -0.03 |
| holdout | ZMR | 9 | 15 | 0.25 |
| q1_2024 | B&H vol-target | 5 | 15 | -0.21 |
| q1_2024 | Buy&Hold | 7 | 15 | -0.00 |
| q1_2024 | Carry | 8 | 15 | 0.70 |
| q1_2024 | KDJ+RSI | 8 | 15 | 0.45 |
| q1_2024 | MACD | 12 | 15 | 0.93 |
| q1_2024 | SMA(20/50) | 11 | 15 | 0.26 |
| q1_2024 | TSMOM(12-1) | 4 | 15 | -0.21 |
| q1_2024 | ZMR | 10 | 15 | 1.35 |
| reserve | B&H vol-target | 6 | 15 | -0.10 |
| reserve | Buy&Hold | 5 | 15 | -0.06 |
| reserve | Carry | 10 | 15 | 0.80 |
| reserve | KDJ+RSI | 5 | 15 | -1.38 |
| reserve | MACD | 10 | 15 | 0.96 |
| reserve | SMA(20/50) | 11 | 15 | 0.90 |
| reserve | TSMOM(12-1) | 8 | 15 | 0.01 |
| reserve | ZMR | 8 | 15 | 0.16 |


## Headline, extended (45)

#### summary: extended (45), design

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| design | AgenticTrader | 45 | 0.50 | 51.89 | 16.93 | 10.33 | 63.71 |
| design | B&H vol-target | 45 | 0.58 | 74.13 | 20.76 | 13.17 | 85.23 |
| design | Buy&Hold | 45 | 0.55 | 104.91 | 32.58 | 19.86 | 99.16 |
| design | Carry | 45 | 0.00 | 5.63 | 1.14 | 0.64 | 6.61 |
| design | KDJ+RSI | 45 | 0.41 | 43.42 | 28.85 | 15.02 | 49.52 |
| design | MACD | 45 | 0.40 | 50.02 | 21.07 | 13.30 | 61.93 |
| design | SMA(20/50) | 45 | 0.51 | 57.55 | 24.00 | 13.73 | 72.31 |
| design | TSMOM(12-1) | 45 | 0.29 | 46.43 | 20.08 | 11.48 | 69.62 |
| design | ZMR | 45 | 0.27 | 29.69 | 28.34 | 14.60 | 40.94 |

#### summary: extended (45), holdout

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| holdout | AgenticTrader | 45 | 0.21 | 39.81 | 14.43 | 10.95 | 62.45 |
| holdout | B&H vol-target | 45 | 0.27 | 46.35 | 19.79 | 13.87 | 81.33 |
| holdout | Buy&Hold | 45 | 0.39 | 66.81 | 26.39 | 19.19 | 97.87 |
| holdout | Carry | 45 | 0.00 | 21.35 | 0.99 | 0.76 | 7.62 |
| holdout | KDJ+RSI | 45 | 0.39 | 47.17 | 20.14 | 13.65 | 54.19 |
| holdout | MACD | 45 | 0.15 | 38.94 | 21.48 | 13.89 | 61.62 |
| holdout | SMA(20/50) | 45 | -0.09 | 27.63 | 24.39 | 14.55 | 67.00 |
| holdout | TSMOM(12-1) | 45 | 0.15 | 36.21 | 17.55 | 11.85 | 64.95 |
| holdout | ZMR | 45 | 0.16 | 33.71 | 19.23 | 12.85 | 44.64 |

#### head to head: extended (45)

| period | baseline | agent wins | instruments | median Sharpe diff |
|:--|:--|--:|--:|--:|
| design | B&H vol-target | 9 | 45 | -0.08 |
| design | Buy&Hold | 19 | 45 | -0.02 |
| design | Carry | 38 | 45 | 0.50 |
| design | KDJ+RSI | 31 | 45 | 0.21 |
| design | MACD | 27 | 45 | 0.14 |
| design | SMA(20/50) | 28 | 45 | 0.06 |
| design | TSMOM(12-1) | 31 | 45 | 0.11 |
| design | ZMR | 35 | 45 | 0.28 |
| holdout | B&H vol-target | 17 | 45 | -0.03 |
| holdout | Buy&Hold | 14 | 45 | -0.08 |
| holdout | Carry | 30 | 45 | 0.15 |
| holdout | KDJ+RSI | 20 | 45 | -0.02 |
| holdout | MACD | 23 | 45 | 0.01 |
| holdout | SMA(20/50) | 36 | 45 | 0.28 |
| holdout | TSMOM(12-1) | 29 | 45 | 0.10 |
| holdout | ZMR | 28 | 45 | 0.07 |
| q1_2024 | B&H vol-target | 16 | 45 | -0.01 |
| q1_2024 | Buy&Hold | 12 | 45 | -0.02 |
| q1_2024 | Carry | 32 | 45 | 1.09 |
| q1_2024 | KDJ+RSI | 22 | 45 | -0.00 |
| q1_2024 | MACD | 34 | 45 | 0.97 |
| q1_2024 | SMA(20/50) | 28 | 45 | 0.15 |
| q1_2024 | TSMOM(12-1) | 20 | 45 | -0.01 |
| q1_2024 | ZMR | 28 | 45 | 0.66 |
| reserve | B&H vol-target | 19 | 45 | -0.05 |
| reserve | Buy&Hold | 20 | 45 | -0.01 |
| reserve | Carry | 20 | 45 | -0.09 |
| reserve | KDJ+RSI | 16 | 45 | -0.31 |
| reserve | MACD | 31 | 45 | 0.61 |
| reserve | SMA(20/50) | 31 | 45 | 0.29 |
| reserve | TSMOM(12-1) | 15 | 45 | -0.16 |
| reserve | ZMR | 12 | 45 | -0.57 |


## Paired Sharpe against every baseline

#### paired Sharpe, agent minus baseline: core (15) (scheme column: clusters needs 5 groups)

| period | baseline | n | mean Sharpe diff | ci95 low | ci95 high | p | wins | scheme | groups | significant |
|:--|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|
| design | B&H vol-target | 15 | 0.02 | -0.10 | 0.15 | 0.76 | 7 | instruments | 2 |  |
| design | Buy&Hold | 15 | 0.07 | -0.05 | 0.18 | 0.25 | 10 | instruments | 2 |  |
| design | Carry | 15 | 0.61 | 0.31 | 0.91 | 0.00 | 12 | instruments | 2 | yes |
| design | KDJ+RSI | 15 | 0.20 | -0.09 | 0.49 | 0.17 | 10 | instruments | 2 |  |
| design | MACD | 15 | 0.27 | 0.09 | 0.44 | 0.00 | 10 | instruments | 2 | yes |
| design | SMA(20/50) | 15 | 0.09 | -0.09 | 0.30 | 0.33 | 7 | instruments | 2 |  |
| design | TSMOM(12-1) | 15 | 0.16 | -0.00 | 0.35 | 0.05 | 9 | instruments | 2 |  |
| design | ZMR | 15 | 0.32 | -0.00 | 0.63 | 0.05 | 12 | instruments | 2 |  |
| holdout | B&H vol-target | 15 | -0.08 | -0.18 | 0.02 | 0.14 | 5 | instruments | 2 |  |
| holdout | Buy&Hold | 15 | -0.07 | -0.19 | 0.03 | 0.21 | 7 | instruments | 2 |  |
| holdout | Carry | 15 | 0.30 | 0.12 | 0.48 | 0.00 | 10 | instruments | 2 | yes |
| holdout | KDJ+RSI | 15 | -0.01 | -0.23 | 0.24 | 0.89 | 5 | instruments | 2 |  |
| holdout | MACD | 15 | 0.24 | 0.03 | 0.43 | 0.03 | 12 | instruments | 2 |  |
| holdout | SMA(20/50) | 15 | 0.20 | -0.05 | 0.44 | 0.12 | 11 | instruments | 2 |  |
| holdout | TSMOM(12-1) | 15 | 0.01 | -0.14 | 0.16 | 0.87 | 6 | instruments | 2 |  |
| holdout | ZMR | 15 | 0.19 | -0.08 | 0.51 | 0.19 | 9 | instruments | 2 |  |
| q1_2024 | B&H vol-target | 15 | 0.15 | -0.48 | 0.95 | 0.76 | 5 | instruments | 2 |  |
| q1_2024 | Buy&Hold | 15 | 0.20 | -0.44 | 1.00 | 0.65 | 7 | instruments | 2 |  |
| q1_2024 | Carry | 15 | 1.12 | -0.14 | 2.41 | 0.08 | 8 | instruments | 2 |  |
| q1_2024 | KDJ+RSI | 15 | 0.67 | -0.68 | 2.04 | 0.34 | 8 | instruments | 2 |  |
| q1_2024 | MACD | 15 | 1.37 | 0.21 | 2.59 | 0.02 | 12 | instruments | 2 |  |
| q1_2024 | SMA(20/50) | 15 | 0.89 | -0.00 | 1.92 | 0.05 | 11 | instruments | 2 |  |
| q1_2024 | TSMOM(12-1) | 15 | -0.41 | -0.84 | -0.04 | 0.02 | 4 | instruments | 2 |  |
| q1_2024 | ZMR | 15 | 0.98 | -0.61 | 2.46 | 0.22 | 10 | instruments | 2 |  |
| reserve | B&H vol-target | 15 | -0.03 | -0.20 | 0.16 | 0.72 | 6 | instruments | 2 |  |
| reserve | Buy&Hold | 15 | -0.03 | -0.21 | 0.17 | 0.73 | 5 | instruments | 2 |  |
| reserve | Carry | 15 | 0.69 | -0.05 | 1.39 | 0.07 | 10 | instruments | 2 |  |
| reserve | KDJ+RSI | 15 | -0.73 | -1.64 | 0.22 | 0.12 | 5 | instruments | 2 |  |
| reserve | MACD | 15 | 0.39 | -0.63 | 1.36 | 0.44 | 10 | instruments | 2 |  |
| reserve | SMA(20/50) | 15 | 1.18 | 0.61 | 1.77 | 0.00 | 11 | instruments | 2 | yes |
| reserve | TSMOM(12-1) | 15 | 0.57 | 0.07 | 1.19 | 0.02 | 8 | instruments | 2 |  |
| reserve | ZMR | 15 | 0.13 | -0.65 | 0.92 | 0.73 | 8 | instruments | 2 |  |

#### paired Sharpe, agent minus baseline: extended (45) (scheme column: clusters needs 5 groups)

| period | baseline | n | mean Sharpe diff | ci95 low | ci95 high | p | wins | scheme | groups | significant |
|:--|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|
| design | B&H vol-target | 45 | -0.09 | -0.15 | -0.04 | 0.00 | 9 | instruments | 3 | yes |
| design | Buy&Hold | 45 | -0.05 | -0.11 | 0.01 | 0.15 | 19 | instruments | 3 |  |
| design | Carry | 45 | 0.48 | 0.36 | 0.60 | 0.00 | 38 | instruments | 3 | yes |
| design | KDJ+RSI | 45 | 0.08 | -0.06 | 0.21 | 0.25 | 31 | instruments | 3 |  |
| design | MACD | 45 | 0.07 | -0.04 | 0.19 | 0.22 | 27 | instruments | 3 |  |
| design | SMA(20/50) | 45 | 0.04 | -0.06 | 0.14 | 0.39 | 28 | instruments | 3 |  |
| design | TSMOM(12-1) | 45 | 0.11 | 0.03 | 0.18 | 0.01 | 31 | instruments | 3 | yes |
| design | ZMR | 45 | 0.20 | 0.09 | 0.31 | 0.00 | 35 | instruments | 3 | yes |
| holdout | B&H vol-target | 45 | -0.04 | -0.09 | 0.01 | 0.15 | 17 | instruments | 3 |  |
| holdout | Buy&Hold | 45 | -0.08 | -0.13 | -0.02 | 0.01 | 14 | instruments | 3 | yes |
| holdout | Carry | 45 | 0.19 | 0.06 | 0.32 | 0.00 | 30 | instruments | 3 | yes |
| holdout | KDJ+RSI | 45 | -0.07 | -0.23 | 0.09 | 0.39 | 20 | instruments | 3 |  |
| holdout | MACD | 45 | 0.08 | -0.07 | 0.23 | 0.34 | 23 | instruments | 3 |  |
| holdout | SMA(20/50) | 45 | 0.28 | 0.15 | 0.41 | 0.00 | 36 | instruments | 3 | yes |
| holdout | TSMOM(12-1) | 45 | 0.08 | -0.02 | 0.17 | 0.11 | 29 | instruments | 3 |  |
| holdout | ZMR | 45 | 0.07 | -0.06 | 0.19 | 0.28 | 28 | instruments | 3 |  |
| q1_2024 | B&H vol-target | 45 | -0.26 | -0.63 | 0.01 | 0.06 | 16 | instruments | 3 |  |
| q1_2024 | Buy&Hold | 45 | -0.26 | -0.64 | 0.01 | 0.07 | 12 | instruments | 3 |  |
| q1_2024 | Carry | 45 | 1.05 | 0.40 | 1.67 | 0.00 | 32 | instruments | 3 | yes |
| q1_2024 | KDJ+RSI | 45 | 0.58 | -0.26 | 1.43 | 0.18 | 22 | instruments | 3 |  |
| q1_2024 | MACD | 45 | 1.14 | 0.59 | 1.69 | 0.00 | 34 | instruments | 3 | yes |
| q1_2024 | SMA(20/50) | 45 | 0.54 | 0.03 | 1.08 | 0.04 | 28 | instruments | 3 |  |
| q1_2024 | TSMOM(12-1) | 45 | -0.13 | -0.91 | 0.77 | 0.73 | 20 | instruments | 3 |  |
| q1_2024 | ZMR | 45 | 0.58 | -0.28 | 1.44 | 0.19 | 28 | instruments | 3 |  |
| reserve | B&H vol-target | 45 | 0.06 | -0.18 | 0.33 | 0.69 | 19 | instruments | 3 |  |
| reserve | Buy&Hold | 45 | 0.07 | -0.17 | 0.35 | 0.64 | 20 | instruments | 3 |  |
| reserve | Carry | 45 | -0.09 | -0.55 | 0.37 | 0.70 | 20 | instruments | 3 |  |
| reserve | KDJ+RSI | 45 | -0.81 | -1.41 | -0.22 | 0.01 | 16 | instruments | 3 | yes |
| reserve | MACD | 45 | 0.71 | 0.22 | 1.21 | 0.01 | 31 | instruments | 3 | yes |
| reserve | SMA(20/50) | 45 | 0.60 | 0.19 | 1.01 | 0.00 | 31 | instruments | 3 | yes |
| reserve | TSMOM(12-1) | 45 | -0.07 | -0.30 | 0.17 | 0.54 | 15 | instruments | 3 |  |
| reserve | ZMR | 45 | -0.71 | -1.15 | -0.28 | 0.00 | 12 | instruments | 3 | yes |

#### paired Sharpe, agent minus baseline: all 60 (scheme column: clusters needs 5 groups)

| period | baseline | n | mean Sharpe diff | ci95 low | ci95 high | p | wins | scheme | groups | significant |
|:--|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|
| design | B&H vol-target | 60 | -0.06 | -0.15 | 0.04 | 0.17 | 16 | clusters | 5 |  |
| design | Buy&Hold | 60 | -0.02 | -0.13 | 0.07 | 0.73 | 29 | clusters | 5 |  |
| design | Carry | 60 | 0.51 | 0.03 | 0.77 | 0.04 | 50 | clusters | 5 |  |
| design | KDJ+RSI | 60 | 0.11 | -0.33 | 0.35 | 0.50 | 41 | clusters | 5 |  |
| design | MACD | 60 | 0.12 | -0.04 | 0.26 | 0.13 | 37 | clusters | 5 |  |
| design | SMA(20/50) | 60 | 0.06 | -0.11 | 0.16 | 0.46 | 35 | clusters | 5 |  |
| design | TSMOM(12-1) | 60 | 0.12 | -0.01 | 0.22 | 0.06 | 40 | clusters | 5 |  |
| design | ZMR | 60 | 0.23 | -0.12 | 0.44 | 0.15 | 47 | clusters | 5 |  |
| holdout | B&H vol-target | 60 | -0.05 | -0.13 | 0.00 | 0.06 | 22 | clusters | 5 |  |
| holdout | Buy&Hold | 60 | -0.07 | -0.14 | -0.01 | 0.02 | 21 | clusters | 5 |  |
| holdout | Carry | 60 | 0.22 | -0.07 | 0.39 | 0.12 | 40 | clusters | 5 |  |
| holdout | KDJ+RSI | 60 | -0.06 | -0.21 | 0.10 | 0.42 | 25 | clusters | 5 |  |
| holdout | MACD | 60 | 0.12 | -0.04 | 0.38 | 0.19 | 35 | clusters | 5 |  |
| holdout | SMA(20/50) | 60 | 0.26 | 0.03 | 0.44 | 0.03 | 47 | clusters | 5 |  |
| holdout | TSMOM(12-1) | 60 | 0.06 | -0.07 | 0.16 | 0.33 | 35 | clusters | 5 |  |
| holdout | ZMR | 60 | 0.10 | -0.05 | 0.25 | 0.16 | 37 | clusters | 5 |  |
| q1_2024 | B&H vol-target | 60 | -0.16 | -0.69 | 0.28 | 0.38 | 21 | clusters | 5 |  |
| q1_2024 | Buy&Hold | 60 | -0.15 | -0.68 | 0.29 | 0.42 | 19 | clusters | 5 |  |
| q1_2024 | Carry | 60 | 1.07 | -0.75 | 2.09 | 0.24 | 40 | clusters | 5 |  |
| q1_2024 | KDJ+RSI | 60 | 0.60 | -0.78 | 1.47 | 0.34 | 30 | clusters | 5 |  |
| q1_2024 | MACD | 60 | 1.20 | 0.51 | 1.86 | 0.00 | 46 | clusters | 5 | yes |
| q1_2024 | SMA(20/50) | 60 | 0.63 | 0.04 | 1.87 | 0.03 | 39 | clusters | 5 |  |
| q1_2024 | TSMOM(12-1) | 60 | -0.20 | -1.05 | 0.65 | 0.46 | 24 | clusters | 5 |  |
| q1_2024 | ZMR | 60 | 0.68 | -0.74 | 1.64 | 0.29 | 38 | clusters | 5 |  |
| reserve | B&H vol-target | 60 | 0.04 | -0.19 | 0.26 | 0.72 | 25 | clusters | 5 |  |
| reserve | Buy&Hold | 60 | 0.04 | -0.19 | 0.27 | 0.67 | 25 | clusters | 5 |  |
| reserve | Carry | 60 | 0.11 | -0.59 | 0.85 | 0.76 | 30 | clusters | 5 |  |
| reserve | KDJ+RSI | 60 | -0.79 | -1.58 | -0.25 | 0.01 | 21 | clusters | 5 |  |
| reserve | MACD | 60 | 0.63 | -0.59 | 1.27 | 0.27 | 41 | clusters | 5 |  |
| reserve | SMA(20/50) | 60 | 0.74 | 0.36 | 1.34 | 0.00 | 42 | clusters | 5 | yes |
| reserve | TSMOM(12-1) | 60 | 0.09 | -0.21 | 0.60 | 0.63 | 23 | clusters | 5 |  |
| reserve | ZMR | 60 | -0.50 | -0.94 | 0.21 | 0.16 | 20 | clusters | 5 |  |


## Drawdown and Calmar against the two controls

#### paired MDD%, agent minus control: core (15)

| period | baseline | n | mean MDD% diff | ci95 low | ci95 high | p | wins | scheme | groups | significant |
|:--|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|
| design | B&H vol-target | 15 | -5.51 | -9.01 | -2.57 | 0.00 | 2 | instruments | 2 | yes |
| design | Buy&Hold | 15 | -18.17 | -23.45 | -13.34 | 0.00 | 0 | instruments | 2 | yes |
| holdout | B&H vol-target | 15 | -4.44 | -6.54 | -2.30 | 0.00 | 3 | instruments | 2 | yes |
| holdout | Buy&Hold | 15 | -17.11 | -25.34 | -9.90 | 0.00 | 2 | instruments | 2 | yes |
| q1_2024 | B&H vol-target | 15 | -0.79 | -1.27 | -0.37 | 0.00 | 1 | instruments | 2 | yes |
| q1_2024 | Buy&Hold | 15 | -1.88 | -2.73 | -1.07 | 0.00 | 0 | instruments | 2 | yes |
| reserve | B&H vol-target | 15 | -0.49 | -0.68 | -0.29 | 0.00 | 1 | instruments | 2 | yes |
| reserve | Buy&Hold | 15 | -3.83 | -6.03 | -2.00 | 0.00 | 0 | instruments | 2 | yes |

#### paired MDD%, agent minus control: extended (45)

| period | baseline | n | mean MDD% diff | ci95 low | ci95 high | p | wins | scheme | groups | significant |
|:--|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|
| design | B&H vol-target | 45 | -3.83 | -5.56 | -2.23 | 0.00 | 11 | instruments | 3 | yes |
| design | Buy&Hold | 45 | -15.65 | -19.82 | -11.85 | 0.00 | 3 | instruments | 3 | yes |
| holdout | B&H vol-target | 45 | -5.36 | -7.03 | -3.78 | 0.00 | 3 | instruments | 3 | yes |
| holdout | Buy&Hold | 45 | -11.96 | -14.77 | -9.40 | 0.00 | 2 | instruments | 3 | yes |
| q1_2024 | B&H vol-target | 45 | -0.61 | -0.88 | -0.36 | 0.00 | 4 | instruments | 3 | yes |
| q1_2024 | Buy&Hold | 45 | -1.37 | -2.13 | -0.79 | 0.00 | 3 | instruments | 3 | yes |
| reserve | B&H vol-target | 45 | -1.39 | -1.92 | -0.92 | 0.00 | 6 | instruments | 3 | yes |
| reserve | Buy&Hold | 45 | -3.83 | -5.02 | -2.77 | 0.00 | 1 | instruments | 3 | yes |

#### paired Calmar, agent minus control: core (15)

| period | baseline | n | mean Calmar diff | ci95 low | ci95 high | p | wins | scheme | groups | significant |
|:--|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|
| design | B&H vol-target | 15 | 0.00 | -0.14 | 0.16 | 0.95 | 7 | instruments | 2 |  |
| design | Buy&Hold | 15 | 0.19 | 0.09 | 0.32 | 0.00 | 13 | instruments | 2 | yes |
| holdout | B&H vol-target | 15 | -0.01 | -0.16 | 0.13 | 0.94 | 7 | instruments | 2 |  |
| holdout | Buy&Hold | 15 | 0.10 | -0.08 | 0.25 | 0.27 | 10 | instruments | 2 |  |
| q1_2024 | B&H vol-target | 15 | 0.25 | -2.35 | 2.82 | 0.88 | 7 | instruments | 2 |  |
| q1_2024 | Buy&Hold | 15 | -6.44 | -19.71 | 1.71 | 0.26 | 5 | instruments | 2 |  |
| reserve | B&H vol-target | 15 | -0.68 | -1.92 | 0.27 | 0.20 | 6 | instruments | 2 |  |
| reserve | Buy&Hold | 15 | -1.59 | -5.46 | 0.69 | 0.53 | 7 | instruments | 2 |  |

#### paired Calmar, agent minus control: extended (45)

| period | baseline | n | mean Calmar diff | ci95 low | ci95 high | p | wins | scheme | groups | significant |
|:--|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|
| design | B&H vol-target | 45 | -0.07 | -0.12 | -0.02 | 0.01 | 18 | instruments | 3 | yes |
| design | Buy&Hold | 45 | 0.04 | -0.01 | 0.10 | 0.09 | 26 | instruments | 3 |  |
| holdout | B&H vol-target | 45 | 0.08 | 0.01 | 0.16 | 0.02 | 30 | instruments | 3 |  |
| holdout | Buy&Hold | 45 | 0.12 | 0.04 | 0.20 | 0.00 | 30 | instruments | 3 | yes |
| q1_2024 | B&H vol-target | 45 | -0.20 | -1.23 | 0.84 | 0.69 | 21 | instruments | 3 |  |
| q1_2024 | Buy&Hold | 45 | 0.06 | -1.02 | 1.09 | 0.91 | 22 | instruments | 3 |  |
| reserve | B&H vol-target | 45 | -0.22 | -1.05 | 0.74 | 0.58 | 21 | instruments | 3 |  |
| reserve | Buy&Hold | 45 | -0.19 | -1.26 | 0.93 | 0.70 | 24 | instruments | 3 |  |

#### summary by asset class: core (15) equity (10), holdout

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| holdout | AgenticTrader | 10 | 0.47 | 60.12 | 17.77 | 14.17 | 52.46 |
| holdout | B&H vol-target | 10 | 0.53 | 74.27 | 21.27 | 17.02 | 63.28 |
| holdout | Buy&Hold | 10 | 0.52 | 131.34 | 40.24 | 30.99 | 100.00 |
| holdout | Carry | 10 | 0.00 | 19.47 | 0.00 | 0.00 | 0.00 |
| holdout | KDJ+RSI | 10 | 0.53 | 68.10 | 27.87 | 21.75 | 40.17 |
| holdout | MACD | 10 | 0.43 | 41.38 | 34.04 | 21.45 | 50.40 |
| holdout | SMA(20/50) | 10 | 0.33 | 69.82 | 30.36 | 21.54 | 60.37 |
| holdout | TSMOM(12-1) | 10 | 0.52 | 56.73 | 19.11 | 14.93 | 49.63 |
| holdout | ZMR | 10 | 0.25 | 48.25 | 24.60 | 20.07 | 33.13 |

#### paired MDD% by asset class, agent minus control: core (15) equity (10)

| period | baseline | n | mean MDD% diff | ci95 low | ci95 high | p | wins | scheme | groups | significant |
|:--|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|
| design | B&H vol-target | 10 | -3.80 | -8.04 | -0.99 | 0.00 | 2 | instruments | 1 | yes |
| design | Buy&Hold | 10 | -22.82 | -28.61 | -18.07 | 0.00 | 0 | instruments | 1 | yes |
| holdout | B&H vol-target | 10 | -3.51 | -5.60 | -1.33 | 0.00 | 2 | instruments | 1 | yes |
| holdout | Buy&Hold | 10 | -22.47 | -32.66 | -12.84 | 0.00 | 1 | instruments | 1 | yes |
| q1_2024 | B&H vol-target | 10 | -0.74 | -1.33 | -0.28 | 0.00 | 1 | instruments | 1 | yes |
| q1_2024 | Buy&Hold | 10 | -2.39 | -3.45 | -1.34 | 0.00 | 0 | instruments | 1 | yes |
| reserve | B&H vol-target | 10 | -0.50 | -0.77 | -0.22 | 0.00 | 1 | instruments | 1 | yes |
| reserve | Buy&Hold | 10 | -5.51 | -8.14 | -3.22 | 0.00 | 0 | instruments | 1 | yes |


## The 15-sleeve portfolio

#### portfolio: design

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 81.81 | 10.45 | 6.39 | 1.44 | 3.53 | 8.43 | 1.24 | 59.56 |
| Buy&Hold | 197.51 | 19.87 | 14.25 | 1.28 | 3.13 | 22.69 | 0.88 | 96.74 |
| B&H vol-target | 98.58 | 12.08 | 7.53 | 1.43 | 3.50 | 9.45 | 1.28 | 78.80 |
| SMA(20/50) | 115.79 | 13.64 | 8.87 | 1.38 | 3.39 | 9.49 | 1.44 | 77.13 |
| MACD | 71.22 | 9.35 | 7.44 | 1.11 | 2.73 | 14.77 | 0.63 | 66.53 |
| KDJ+RSI | 67.72 | 8.98 | 9.96 | 0.82 | 2.01 | 18.06 | 0.50 | 53.47 |
| ZMR | 44.36 | 6.29 | 9.94 | 0.57 | 1.40 | 19.25 | 0.33 | 43.75 |
| TSMOM(12-1) | 72.54 | 9.49 | 6.73 | 1.24 | 3.05 | 7.68 | 1.24 | 71.93 |
| Carry | 6.99 | 1.13 | 0.51 | 0.35 | 0.86 | 0.44 | 2.57 | 9.30 |

#### portfolio Sharpe difference (paired block bootstrap over days): design

- agent minus B&H vol-target: +0.01 [-0.23, +0.26] p=0.871 (n=1564 days, block 10)
- agent minus Buy&Hold: +0.16 [-0.24, +0.57] p=0.489 (n=1564 days, block 10)

#### portfolio: holdout

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 49.57 | 9.38 | 5.68 | 0.91 | 1.92 | 6.41 | 1.46 | 55.80 |
| Buy&Hold | 96.91 | 16.29 | 14.08 | 0.86 | 1.82 | 20.43 | 0.80 | 94.96 |
| B&H vol-target | 61.48 | 11.27 | 7.01 | 0.99 | 2.10 | 9.17 | 1.23 | 72.12 |
| SMA(20/50) | 49.35 | 9.35 | 8.22 | 0.64 | 1.36 | 11.98 | 0.78 | 71.51 |
| MACD | 35.29 | 6.97 | 8.22 | 0.38 | 0.80 | 16.02 | 0.43 | 65.35 |
| KDJ+RSI | 58.49 | 10.81 | 9.57 | 0.70 | 1.49 | 12.92 | 0.84 | 59.70 |
| ZMR | 40.93 | 7.94 | 9.11 | 0.45 | 0.95 | 9.82 | 0.81 | 48.75 |
| TSMOM(12-1) | 48.49 | 9.21 | 5.99 | 0.83 | 1.77 | 6.83 | 1.35 | 64.30 |
| Carry | 21.34 | 4.40 | 0.83 | 0.39 | 0.84 | 0.84 | 5.26 | 10.85 |

#### portfolio Sharpe difference (paired block bootstrap over days): holdout

- agent minus B&H vol-target: -0.08 [-0.46, +0.30] p=0.688 (n=1167 days, block 10)
- agent minus Buy&Hold: +0.05 [-0.40, +0.50] p=0.820 (n=1167 days, block 10)

#### cash leg on vs off: holdout

| index | Sharpe (cash leg) | CR% (cash leg) | MDD% (cash leg) | Exp% (cash leg) | Sharpe (no cash leg) | CR% (no cash leg) | MDD% (no cash leg) | Exp% (no cash leg) |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 0.91 | 49.57 | 6.41 | 55.80 | 1.17 | 33.68 | 6.76 | 55.90 |
| Buy&Hold | 0.86 | 96.91 | 20.43 | 94.96 | 1.05 | 86.23 | 20.79 | 97.47 |
| B&H vol-target | 0.99 | 61.48 | 9.17 | 72.12 | 1.24 | 46.21 | 9.85 | 73.94 |
| SMA(20/50) | 0.64 | 49.35 | 11.98 | 71.51 | 0.85 | 34.89 | 13.23 | 71.66 |
| MACD | 0.38 | 35.29 | 16.02 | 65.35 | 0.54 | 20.26 | 16.31 | 65.39 |
| KDJ+RSI | 0.70 | 58.49 | 12.92 | 59.70 | 0.81 | 38.85 | 13.50 | 59.87 |
| ZMR | 0.45 | 40.93 | 9.82 | 48.75 | 0.54 | 22.25 | 10.38 | 48.79 |
| TSMOM(12-1) | 0.83 | 48.49 | 6.83 | 64.30 | 1.06 | 32.14 | 7.29 | 64.59 |
| Carry | 0.39 | 21.34 | 0.84 | 10.85 | 0.43 | 1.64 | 1.64 | 11.42 |


## Re-checks under the v0.11 engine

#### EDGAR on (a) vs off (b)

| period | universe | n | mean Sharpe (a) | mean Sharpe (b) | mean diff | 95% CI | p | scheme | wins |
|:--|:--|--:|--:|--:|--:|:--|--:|:--|:--|
| design | core | 15 | 0.67 | 0.65 | 0.02 | [-0.01, +0.05] | 0.31 | instruments | 5 / 15 |
| design | extended | 45 | 0.47 | 0.46 | 0.01 | [-0.00, +0.02] | 0.14 | instruments | 14 / 45 |
| design | all | 60 | 0.52 | 0.51 | 0.01 | [-0.00, +0.03] | 0.17 | clusters | 19 / 60 |
| holdout | core | 15 | 0.37 | 0.37 | 0.01 | [-0.05, +0.05] | 0.78 | instruments | 6 / 15 |
| holdout | extended | 45 | 0.26 | 0.23 | 0.03 | [+0.01, +0.06] | 0.01 | instruments | 17 / 45 |
| holdout | all | 60 | 0.29 | 0.26 | 0.03 | [-0.01, +0.06] | 0.24 | clusters | 23 / 60 |
| q1_2024 | core | 15 | 1.91 | 1.84 | 0.07 | [+0.00, +0.17] | 0.02 | instruments | 4 / 15 |
| q1_2024 | extended | 45 | 1.55 | 1.51 | 0.04 | [+0.01, +0.08] | 0.01 | instruments | 5 / 45 |
| q1_2024 | all | 60 | 1.64 | 1.59 | 0.05 | [+0.00, +0.09] | 0.16 | clusters | 9 / 60 |
| reserve | core | 15 | 0.89 | 0.73 | 0.16 | [+0.04, +0.31] | 0.00 | instruments | 6 / 15 |
| reserve | extended | 45 | -0.10 | -0.14 | 0.05 | [-0.02, +0.12] | 0.21 | instruments | 9 / 45 |
| reserve | all | 60 | 0.15 | 0.07 | 0.07 | [+0.00, +0.18] | 0.19 | clusters | 15 / 60 |

#### FX carry rule on (a) vs off (b)

| period | universe | n | mean Sharpe (a) | mean Sharpe (b) | mean diff | 95% CI | p | scheme | wins |
|:--|:--|--:|--:|--:|--:|:--|--:|:--|:--|
| design | core | 15 | 0.67 | 0.62 | 0.05 | [-0.01, +0.11] | 0.10 | instruments | 4 / 15 |
| design | extended | 45 | 0.47 | 0.45 | 0.02 | [-0.01, +0.05] | 0.16 | instruments | 6 / 45 |
| design | all | 60 | 0.52 | 0.49 | 0.03 | [+0.00, +0.09] | 0.20 | clusters | 10 / 60 |
| holdout | core | 15 | 0.37 | 0.35 | 0.02 | [-0.02, +0.08] | 0.30 | instruments | 4 / 15 |
| holdout | extended | 45 | 0.26 | 0.22 | 0.04 | [+0.00, +0.08] | 0.03 | instruments | 7 / 45 |
| holdout | all | 60 | 0.29 | 0.25 | 0.04 | [-0.00, +0.13] | 0.22 | clusters | 11 / 60 |
| q1_2024 | core | 15 | 1.91 | 1.39 | 0.52 | [+0.13, +0.99] | 0.01 | instruments | 5 / 15 |
| q1_2024 | extended | 45 | 1.55 | 1.40 | 0.15 | [+0.01, +0.30] | 0.03 | instruments | 8 / 45 |
| q1_2024 | all | 60 | 1.64 | 1.40 | 0.24 | [+0.00, +0.82] | 0.17 | clusters | 13 / 60 |
| reserve | core | 15 | 0.89 | 0.76 | 0.12 | [-0.07, +0.36] | 0.25 | instruments | 4 / 15 |
| reserve | extended | 45 | -0.10 | -0.24 | 0.15 | [+0.04, +0.29] | 0.00 | instruments | 6 / 45 |
| reserve | all | 60 | 0.15 | 0.01 | 0.14 | [+0.00, +0.49] | 0.20 | clusters | 10 / 60 |

_eval_xalpha.json missing: with the cross-sectional analyst (a) vs default (b) not rendered_

#### with the alpha analyst, corrected gate (a) vs default (b)

| period | universe | n | mean Sharpe (a) | mean Sharpe (b) | mean diff | 95% CI | p | scheme | wins |
|:--|:--|--:|--:|--:|--:|:--|--:|:--|:--|
| design | core | 15 | 0.66 | 0.67 | -0.00 | [-0.05, +0.04] | 0.86 | instruments | 9 / 15 |
| design | all | 15 | 0.66 | 0.67 | -0.00 | [-0.05, +0.04] | 0.86 | instruments | 9 / 15 |
| holdout | core | 15 | 0.37 | 0.37 | -0.01 | [-0.04, +0.02] | 0.71 | instruments | 9 / 15 |
| holdout | all | 15 | 0.37 | 0.37 | -0.01 | [-0.04, +0.02] | 0.71 | instruments | 9 / 15 |
| q1_2024 | core | 15 | 2.01 | 1.91 | 0.10 | [-0.00, +0.24] | 0.07 | instruments | 11 / 15 |
| q1_2024 | all | 15 | 2.01 | 1.91 | 0.10 | [-0.00, +0.24] | 0.07 | instruments | 11 / 15 |
| reserve | core | 15 | 0.95 | 0.89 | 0.06 | [-0.00, +0.19] | 0.52 | instruments | 3 / 15 |
| reserve | all | 15 | 0.95 | 0.89 | 0.06 | [-0.00, +0.19] | 0.52 | instruments | 3 / 15 |

#### track-record size cut off (a) vs on (b)

| period | universe | n | mean Sharpe (a) | mean Sharpe (b) | mean diff | 95% CI | p | scheme | wins |
|:--|:--|--:|--:|--:|--:|:--|--:|:--|:--|
| design | core | 15 | 0.67 | 0.67 | 0.01 | [+0.00, +0.01] | 0.01 | instruments | 10 / 15 |
| design | extended | 45 | 0.48 | 0.47 | 0.01 | [+0.00, +0.02] | 0.00 | instruments | 33 / 45 |
| design | all | 60 | 0.53 | 0.52 | 0.01 | [+0.00, +0.02] | 0.00 | clusters | 43 / 60 |
| holdout | core | 15 | 0.38 | 0.37 | 0.01 | [-0.01, +0.03] | 0.43 | instruments | 9 / 15 |
| holdout | extended | 45 | 0.26 | 0.26 | 0.01 | [-0.00, +0.01] | 0.21 | instruments | 28 / 45 |
| holdout | all | 60 | 0.29 | 0.29 | 0.01 | [-0.00, +0.02] | 0.16 | clusters | 37 / 60 |
| q1_2024 | core | 15 | 1.95 | 1.91 | 0.04 | [-0.01, +0.11] | 0.13 | instruments | 7 / 15 |
| q1_2024 | extended | 45 | 1.59 | 1.55 | 0.04 | [+0.01, +0.07] | 0.00 | instruments | 16 / 45 |
| q1_2024 | all | 60 | 1.68 | 1.64 | 0.04 | [+0.01, +0.09] | 0.00 | clusters | 23 / 60 |
| reserve | core | 15 | 0.93 | 0.89 | 0.04 | [-0.00, +0.10] | 0.07 | instruments | 3 / 15 |
| reserve | extended | 45 | -0.11 | -0.10 | -0.02 | [-0.04, +0.01] | 0.25 | instruments | 6 / 45 |
| reserve | all | 60 | 0.15 | 0.15 | -0.00 | [-0.03, +0.04] | 0.99 | clusters | 9 / 60 |

#### cash leg off (a) vs on (b)

| period | universe | n | mean Sharpe (a) | mean Sharpe (b) | mean diff | 95% CI | p | scheme | wins |
|:--|:--|--:|--:|--:|--:|:--|--:|:--|:--|
| design | core | 15 | 0.69 | 0.67 | 0.03 | [+0.02, +0.04] | 0.00 | instruments | 11 / 15 |
| design | extended | 45 | 0.52 | 0.47 | 0.05 | [+0.04, +0.06] | 0.00 | instruments | 37 / 45 |
| design | all | 60 | 0.56 | 0.52 | 0.04 | [+0.01, +0.07] | 0.02 | clusters | 48 / 60 |
| holdout | core | 15 | 0.48 | 0.37 | 0.11 | [+0.06, +0.15] | 0.00 | instruments | 12 / 15 |
| holdout | extended | 45 | 0.43 | 0.26 | 0.17 | [+0.14, +0.22] | 0.00 | instruments | 38 / 45 |
| holdout | all | 60 | 0.44 | 0.29 | 0.16 | [+0.04, +0.23] | 0.01 | clusters | 50 / 60 |
| q1_2024 | core | 15 | 2.09 | 1.91 | 0.18 | [+0.10, +0.27] | 0.00 | instruments | 11 / 15 |
| q1_2024 | extended | 45 | 1.84 | 1.55 | 0.29 | [+0.22, +0.35] | 0.00 | instruments | 38 / 45 |
| q1_2024 | all | 60 | 1.90 | 1.64 | 0.26 | [+0.07, +0.38] | 0.02 | clusters | 49 / 60 |
| reserve | core | 15 | 0.99 | 0.89 | 0.10 | [+0.06, +0.15] | 0.00 | instruments | 13 / 15 |
| reserve | extended | 45 | 0.07 | -0.10 | 0.17 | [+0.12, +0.23] | 0.00 | instruments | 37 / 45 |
| reserve | all | 60 | 0.30 | 0.15 | 0.15 | [+0.04, +0.26] | 0.00 | clusters | 50 / 60 |

#### v0.3+ rules (a) vs v0.2 rules (b), core

| period | universe | n | mean Sharpe (a) | mean Sharpe (b) | mean diff | 95% CI | p | scheme | wins |
|:--|:--|--:|--:|--:|--:|:--|--:|:--|:--|
| design | core | 15 | 0.67 | 0.47 | 0.19 | [+0.11, +0.28] | 0.00 | instruments | 12 / 15 |
| design | all | 15 | 0.67 | 0.47 | 0.19 | [+0.11, +0.28] | 0.00 | instruments | 12 / 15 |
| holdout | core | 15 | 0.37 | 0.34 | 0.03 | [-0.05, +0.11] | 0.44 | instruments | 10 / 15 |
| holdout | all | 15 | 0.37 | 0.34 | 0.03 | [-0.05, +0.11] | 0.44 | instruments | 10 / 15 |
| q1_2024 | core | 15 | 1.91 | 1.18 | 0.73 | [+0.28, +1.20] | 0.00 | instruments | 11 / 15 |
| q1_2024 | all | 15 | 1.91 | 1.18 | 0.73 | [+0.28, +1.20] | 0.00 | instruments | 11 / 15 |
| reserve | core | 15 | 0.89 | -0.08 | 0.97 | [+0.45, +1.53] | 0.00 | instruments | 13 / 15 |
| reserve | all | 15 | 0.89 | -0.08 | 0.97 | [+0.45, +1.53] | 0.00 | instruments | 13 / 15 |


## Execution and impact

#### execution algorithm, $1B holdout portfolio (sleeve impact at the sleeve's capital; FX sleeves pay no impact without costs.fx_adv_notional and are excluded from the mean)

| execution algo | Sharpe | CR% | MDD% | mean equity-sleeve impact paid % | equity sleeves |
|:--|--:|--:|--:|--:|--:|
| VWAP (default) | 0.88 | 48.40 | 6.45 | 1.17 | 10 |
| TWAP | 0.87 | 48.33 | 6.45 | 1.24 | 10 |
| Almgren-Chriss, kappa=5 | 0.87 | 48.03 | 6.46 | 1.55 | 10 |

#### impact sweep, core universe, textbook coefficient 1.0 (equity-scaled impact)

| strategy | period | Sharpe (off) | Sharpe $100k | impact % $100k | Sharpe $10M | impact % $10M | Sharpe $1B | impact % $1B |
|:--|:--|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | design | 0.67 | 0.66 | 0.05 | 0.66 | 0.52 | 0.60 | 5.10 |
| AgenticTrader | holdout | 0.37 | 0.37 | 0.03 | 0.37 | 0.30 | 0.33 | 2.99 |
| B&H vol-target | design | 0.64 | 0.64 | 0.07 | 0.64 | 0.68 | 0.58 | 6.61 |
| B&H vol-target | holdout | 0.45 | 0.45 | 0.04 | 0.45 | 0.36 | 0.41 | 3.51 |
| Buy&Hold | design | 0.60 | 0.60 | 0.01 | 0.60 | 0.09 | 0.59 | 0.90 |
| Buy&Hold | holdout | 0.45 | 0.45 | 0.00 | 0.45 | 0.05 | 0.44 | 0.46 |
| SMA(20/50) | design | 0.57 | 0.57 | 0.27 | 0.55 | 2.62 | 0.39 | 23.55 |
| SMA(20/50) | holdout | 0.18 | 0.18 | 0.13 | 0.16 | 1.34 | 0.04 | 12.77 |
| MACD | design | 0.40 | 0.39 | 0.83 | 0.33 | 8.02 | -0.16 | 62.19 |
| MACD | holdout | 0.14 | 0.13 | 0.45 | 0.09 | 4.45 | -0.29 | 38.43 |


## VaR coverage

#### VaR coverage: rolling historical VaR of the 15-sleeve portfolio's own returns

| forecast | n | breaches | breach_rate | kupiec_p | christoffersen_p | conditional_coverage_p |
|:--|--:|--:|--:|--:|--:|--:|
| portfolio returns, 120-day rolling historical VaR | 1048 | 62 | 0.0592 | 0.1855 | 0.4820 | 0.3251 |
| portfolio returns, 250-day rolling historical VaR | 918 | 45 | 0.0490 | 0.8913 | 0.0848 | 0.2243 |

#### VaR coverage: the desk's own per-instrument forecast (250-day historical VaR, agents/risk.py) vs next-day returns, holdout; Kupiec rejects at 5%: 2 of 15

| instrument | n | breaches | breach_rate | kupiec_p | christoffersen_p |
|:--|--:|--:|--:|--:|--:|
| AAPL | 1126 | 74 | 0.0657 | 0.0207 | 0.0027 |
| NVDA | 1126 | 67 | 0.0595 | 0.1549 | 0.6034 |
| MSFT | 1126 | 70 | 0.0622 | 0.0706 | 0.8541 |
| META | 1126 | 63 | 0.0560 | 0.3683 | 0.0274 |
| GOOGL | 1126 | 68 | 0.0604 | 0.1208 | 0.1628 |
| AMZN | 1126 | 68 | 0.0604 | 0.1208 | 0.3492 |
| JPM | 1126 | 66 | 0.0586 | 0.1961 | 0.0158 |
| XOM | 1126 | 60 | 0.0533 | 0.6165 | 0.6480 |
| JNJ | 1126 | 67 | 0.0595 | 0.1549 | 0.9704 |
| SPY | 1126 | 59 | 0.0524 | 0.7140 | 0.0121 |
| EURUSD | 1167 | 65 | 0.0557 | 0.3800 | 0.0886 |
| USDJPY | 1167 | 65 | 0.0557 | 0.3800 | 0.2221 |
| GBPUSD | 1167 | 62 | 0.0531 | 0.6273 | 0.0182 |
| AUDUSD | 1167 | 74 | 0.0634 | 0.0432 | 0.2856 |
| USDCAD | 1167 | 61 | 0.0523 | 0.7238 | 0.0441 |


## Selection statistics on one statistic

#### trials registry: 44 variants judged on the design period

| trial | version | design portfolio Sharpe | design mean Sharpe (v0.8 engine) | recorded (v0.3 engine) | re-measured | design mean CR% | design mean MDD% | design mean Exp% | design mean Trades |
|:--|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| v0.2 (control) | v0.3 | 1.22 | 0.45 | 0.50 | yes | 47.97 | 12.94 | 43.41 | 254.87 |
| + 12-1 month time-series momentum | v0.3 | 1.26 | 0.45 | 0.47 | yes | 59.71 | 13.13 | 46.74 | 263.53 |
| + trend-filtered reversal | v0.3 | 1.20 | 0.44 | 0.48 | yes | 48.25 | 13.06 | 44.03 | 255.07 |
| + abstain without data | v0.3 | 1.23 | 0.46 | 0.51 | yes | 52.79 | 13.57 | 46.55 | 259.60 |
| + no-trade band 0.10 | v0.3 | 1.22 | 0.45 | 0.50 | yes | 47.79 | 12.77 | 43.19 | 131.67 |
| + intraday stops | v0.3 | 1.22 | 0.44 | 0.47 | yes | 38.52 | 12.21 | 39.77 | 293.20 |
| signal changes (momentum + filter + abstain) | v0.3 | 1.29 | 0.47 | 0.51 | yes | 64.92 | 13.45 | 49.51 | 269.13 |
| signal changes + band | v0.3 | 1.28 | 0.47 | 0.51 | yes | 63.34 | 13.44 | 49.03 | 115.13 |
| all five | v0.3 | 1.28 | 0.45 | 0.50 | yes | 48.93 | 12.57 | 44.86 | 187.33 |
| strategic equity weight 0.25 | v0.3 | 1.33 | 0.52 | 0.54 | yes | 66.17 | 13.36 | 48.96 | 280.87 |
| strategic equity weight 0.50 | v0.3 | 1.39 | 0.56 | 0.58 | yes | 80.16 | 13.55 | 52.74 | 286.87 |
| strategic equity weight 1.00 | v0.3 | 1.42 | 0.62 | 0.66 | yes | 98.34 | 14.54 | 57.85 | 292.40 |
| strategic 0.50 + band | v0.3 | 1.39 | 0.57 | 0.58 | yes | 78.51 | 13.57 | 52.21 | 118.20 |
| strategic 0.50 + signal changes + band | v0.3 | 1.39 | 0.57 | 0.58 | yes | 86.95 | 14.14 | 55.36 | 104.27 |
| strategic 0.50 + abstain + band | v0.3 | 1.41 | 0.58 | 0.56 | yes | 80.47 | 13.78 | 53.60 | 117.60 |
| frozen v0.3: strategic 1.00 + band | v0.3 | 1.40 | 0.62 | 0.65 | yes | 96.52 | 14.69 | 57.19 | 100.00 |
| + alpha analyst (IC-weighted, all signals) | v0.4 |  |  | 0.60 |  |  |  |  |  |
| + alpha analyst (significance-gated, 400-day window) | v0.4 |  |  | 0.58 |  |  |  |  |  |
| + alpha analyst (significance-gated, 900-day window) | v0.5 | 1.44 | 0.66 | 0.65 | yes | 97.97 | 14.57 | 59.95 | 95.93 |
| FX carry / 4, cap 0.5 | v0.5.1 | 1.43 | 0.66 |  | yes | 97.91 | 14.57 | 59.84 | 96.67 |
| FX carry / 2, cap 0.5 (adopted) | v0.5.1 | 1.44 | 0.67 |  | yes | 98.41 | 14.66 | 60.97 | 94.07 |
| FX carry / 4, cap 1.0 | v0.5.1 | 1.43 | 0.66 |  | yes | 97.89 | 14.57 | 59.84 | 96.13 |
| FX carry / 8, cap 0.25 | v0.5.1 | 1.42 | 0.64 |  | yes | 97.27 | 14.54 | 58.81 | 99.60 |
| + cross-sectional alpha analyst | v0.6 | 1.44 | 0.66 |  | yes | 99.26 | 14.80 | 60.87 | 93.00 |
| EDGAR filings off | v0.6 | 1.46 | 0.65 |  | yes | 87.94 | 13.57 | 58.34 | 108.53 |
| track-record size cut off | v0.8 | 1.45 | 0.67 |  | yes | 99.60 | 14.91 | 61.42 | 93.07 |
| v0.9 run etf11_rp (multi-asset base) | v0.9 | 1.02 |  |  |  |  |  |  |  |
| v0.9 run etf11_equal | v0.9 | 1.02 |  |  |  |  |  |  |  |
| v0.9 run fx15_rp | v0.9 | 0.08 |  |  |  |  |  |  |  |
| v0.9 run core15_rp | v0.9 | 0.91 |  |  |  |  |  |  |  |
| v0.9 run all26_rp | v0.9 | 0.71 |  |  |  |  |  |  |  |
| v0.9 book beta + trend_etf | v0.9 | 0.78 |  |  |  |  |  |  |  |
| v0.9 book beta + carry | v0.9 | 1.02 |  |  |  |  |  |  |  |
| v0.9 book beta + trend_etf + carry | v0.9 | 0.88 |  |  |  |  |  |  |  |
| v0.9 book all four | v0.9 | 0.57 |  |  |  |  |  |  |  |
| v0.9 book trend + carry (no beta) | v0.9 | 0.11 |  |  |  |  |  |  |  |
| v0.10 overlay lam 0.00 | v0.10 | 1.43 |  |  |  |  |  |  |  |
| v0.10 overlay lam 0.25 | v0.10 | 1.44 |  |  |  |  |  |  |  |
| v0.10 overlay lam 0.50 | v0.10 | 1.43 |  |  |  |  |  |  |  |
| v0.10 overlay lam 0.75 | v0.10 | 1.42 |  |  |  |  |  |  |  |
| v0.10 overlay lam 1.00 | v0.10 | 1.40 |  |  |  |  |  |  |  |
| aggressive stance at the cap (v0.8 rule) | v0.11 | 1.40 | 0.66 |  | yes | 117.92 | 17.49 | 63.22 | 91.80 |
| news confidence by count (v0.8 rule) | v0.11 | 1.44 | 0.67 |  | yes | 98.58 | 14.73 | 61.06 | 93.93 |
| strategic equity weight 0.8 (symmetric tilt) | v0.11 | 1.45 | 0.65 |  | yes | 91.16 | 13.59 | 59.15 | 102.67 |

#### selection statistics for the frozen rules (design-period 15-sleeve portfolio Sharpe, 260 periods/year, every trial's portfolio Sharpe as the benchmark)

```json
{
 "n": 1564,
 "sharpe_annual": 1.439,
 "t_stat": 3.53,
 "skew": -0.706,
 "kurtosis": 7.3,
 "bootstrap_ci_95": [
  0.661,
  2.231
 ],
 "psr_vs_zero": 1.0,
 "trials": 42,
 "expected_max_sharpe_annual": 0.746,
 "deflated_sharpe_prob": 0.949,
 "min_track_record_periods": 1576,
 "caveat": "an upper bound on the true significance: the benchmark is built from the dispersion of trial_sharpes_annual, which is usually narrower than the dispersion of the full return series each trial would have produced, so the true search space is wider than this reports and the real probability is no higher than the number given.",
 "trials_in_registry": 44,
 "trials_without_portfolio_sharpe": [
  "+ alpha analyst (IC-weighted, all signals)",
  "+ alpha analyst (significance-gated, 400-day window)"
 ]
}
```


## Rebalance-phase sweep

#### rebalance-phase sweep, holdout portfolio (5-bar cadence, offsets 0-4): agent Sharpe spread 0.12

| offset | agent Sharpe | vol-target Sharpe | B&H Sharpe | agent - vol-target | agent - B&H |
|--:|--:|--:|--:|:--|:--|
| 0 | 0.91 | 0.99 | 0.86 | -0.08 [-0.46, +0.30] p=0.688 (n=1167 days, block 10) | +0.05 [-0.40, +0.50] p=0.820 (n=1167 days, block 10) |
| 1 | 0.94 | 0.99 | 0.86 | -0.05 [-0.42, +0.34] p=0.818 (n=1167 days, block 10) | +0.08 [-0.36, +0.55] p=0.707 (n=1167 days, block 10) |
| 2 | 0.87 | 0.99 | 0.86 | -0.12 [-0.50, +0.25] p=0.531 (n=1167 days, block 10) | +0.01 [-0.44, +0.46] p=0.961 (n=1167 days, block 10) |
| 3 | 0.82 | 0.99 | 0.86 | -0.17 [-0.54, +0.20] p=0.388 (n=1167 days, block 10) | -0.04 [-0.49, +0.42] p=0.870 (n=1167 days, block 10) |
| 4 | 0.85 | 0.99 | 0.86 | -0.14 [-0.54, +0.26] p=0.495 (n=1167 days, block 10) | -0.01 [-0.47, +0.46] p=0.966 (n=1167 days, block 10) |


_Sections not rendered in this measurement: with the cross-sectional analyst (a) vs default (b)_
