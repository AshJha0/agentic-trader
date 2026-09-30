### summary: core (15), design

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| design | AgenticTrader | 15 | 0.67 | 118.18 | 17.59 | 12.22 | 63.31 |
| design | B&H vol-target | 15 | 0.69 | 128.28 | 20.17 | 13.60 | 80.51 |
| design | Buy&Hold | 15 | 0.73 | 415.17 | 32.83 | 21.81 | 99.10 |
| design | KDJ+RSI | 15 | 0.54 | 75.97 | 27.23 | 16.21 | 54.24 |
| design | MACD | 15 | 0.54 | 95.79 | 24.95 | 15.04 | 67.80 |
| design | SMA(20/50) | 15 | 0.64 | 172.49 | 23.14 | 16.67 | 78.78 |
| design | ZMR | 15 | 0.41 | 47.07 | 27.75 | 15.56 | 44.42 |

### summary: core (15), holdout

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| holdout | AgenticTrader | 15 | 0.30 | 49.52 | 17.40 | 12.82 | 60.51 |
| holdout | B&H vol-target | 15 | 0.52 | 60.63 | 18.98 | 14.12 | 73.67 |
| holdout | Buy&Hold | 15 | 0.51 | 98.41 | 31.64 | 23.40 | 97.39 |
| holdout | KDJ+RSI | 15 | 0.44 | 54.53 | 23.93 | 17.50 | 60.70 |
| holdout | MACD | 15 | 0.19 | 32.78 | 27.53 | 17.19 | 66.59 |
| holdout | SMA(20/50) | 15 | 0.36 | 52.12 | 25.04 | 17.20 | 72.99 |
| holdout | ZMR | 15 | 0.22 | 37.62 | 21.72 | 16.01 | 49.57 |

### summary: core (15), q1_2024

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| q1_2024 | AgenticTrader | 15 | 2.79 | 9.27 | 3.47 | 12.36 | 69.27 |
| q1_2024 | B&H vol-target | 15 | 2.81 | 8.89 | 4.12 | 13.44 | 83.51 |
| q1_2024 | Buy&Hold | 15 | 2.62 | 14.37 | 5.22 | 18.59 | 99.77 |
| q1_2024 | KDJ+RSI | 15 | 0.09 | 3.68 | 2.96 | 6.89 | 50.23 |
| q1_2024 | MACD | 15 | 0.72 | 7.14 | 4.62 | 14.67 | 67.54 |
| q1_2024 | SMA(20/50) | 15 | 0.37 | 12.98 | 4.28 | 16.96 | 88.27 |
| q1_2024 | ZMR | 15 | 0.00 | 2.20 | 2.29 | 5.63 | 35.94 |

### summary: core (15), reserve

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| reserve | AgenticTrader | 15 | 0.81 | 4.67 | 4.58 | 12.99 | 64.95 |
| reserve | B&H vol-target | 15 | 1.05 | 4.72 | 4.42 | 13.05 | 71.07 |
| reserve | Buy&Hold | 15 | 1.05 | 8.12 | 7.76 | 22.75 | 99.83 |
| reserve | KDJ+RSI | 15 | 1.76 | 7.70 | 4.81 | 15.37 | 65.72 |
| reserve | MACD | 15 | 1.03 | 2.92 | 6.96 | 16.93 | 66.32 |
| reserve | SMA(20/50) | 15 | 0.22 | 1.47 | 6.25 | 15.80 | 77.46 |
| reserve | ZMR | 15 | 1.03 | 4.11 | 3.55 | 11.54 | 44.49 |

### head to head: core (15)

| period | baseline | agent wins | instruments | median Sharpe diff |
|:--|:--|--:|--:|--:|
| design | B&H vol-target | 6 | 15 | -0.04 |
| design | Buy&Hold | 9 | 15 | 0.08 |
| design | KDJ+RSI | 10 | 15 | 0.31 |
| design | MACD | 10 | 15 | 0.29 |
| design | SMA(20/50) | 8 | 15 | 0.05 |
| design | ZMR | 12 | 15 | 0.33 |
| holdout | B&H vol-target | 4 | 15 | -0.09 |
| holdout | Buy&Hold | 3 | 15 | -0.06 |
| holdout | KDJ+RSI | 5 | 15 | -0.16 |
| holdout | MACD | 12 | 15 | 0.28 |
| holdout | SMA(20/50) | 11 | 15 | 0.24 |
| holdout | ZMR | 10 | 15 | 0.14 |
| q1_2024 | B&H vol-target | 4 | 15 | -0.16 |
| q1_2024 | Buy&Hold | 5 | 15 | -0.03 |
| q1_2024 | KDJ+RSI | 8 | 15 | 0.45 |
| q1_2024 | MACD | 13 | 15 | 0.71 |
| q1_2024 | SMA(20/50) | 10 | 15 | 0.17 |
| q1_2024 | ZMR | 10 | 15 | 1.64 |
| reserve | B&H vol-target | 4 | 15 | -0.08 |
| reserve | Buy&Hold | 2 | 15 | -0.07 |
| reserve | KDJ+RSI | 5 | 15 | -1.35 |
| reserve | MACD | 10 | 15 | 0.89 |
| reserve | SMA(20/50) | 11 | 15 | 0.93 |
| reserve | ZMR | 8 | 15 | 0.18 |

### summary: extended (45), design

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| design | AgenticTrader | 45 | 0.51 | 57.08 | 18.37 | 11.05 | 65.34 |
| design | B&H vol-target | 45 | 0.58 | 74.13 | 20.77 | 13.17 | 85.23 |
| design | Buy&Hold | 45 | 0.55 | 104.91 | 32.58 | 19.86 | 99.16 |
| design | KDJ+RSI | 45 | 0.41 | 43.42 | 28.85 | 15.02 | 49.52 |
| design | MACD | 45 | 0.40 | 50.02 | 21.07 | 13.30 | 61.93 |
| design | SMA(20/50) | 45 | 0.51 | 57.64 | 24.00 | 13.73 | 72.31 |
| design | ZMR | 45 | 0.27 | 29.75 | 28.34 | 14.60 | 40.94 |

### summary: extended (45), holdout

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| holdout | AgenticTrader | 45 | 0.25 | 42.00 | 15.46 | 11.65 | 64.73 |
| holdout | B&H vol-target | 45 | 0.27 | 46.35 | 19.79 | 13.88 | 81.32 |
| holdout | Buy&Hold | 45 | 0.39 | 66.81 | 26.39 | 19.19 | 97.87 |
| holdout | KDJ+RSI | 45 | 0.39 | 47.17 | 20.14 | 13.65 | 54.19 |
| holdout | MACD | 45 | 0.15 | 38.94 | 21.48 | 13.89 | 61.62 |
| holdout | SMA(20/50) | 45 | -0.09 | 27.63 | 24.39 | 14.55 | 67.00 |
| holdout | ZMR | 45 | 0.16 | 33.77 | 19.23 | 12.85 | 44.63 |

### summary: extended (45), q1_2024

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| q1_2024 | AgenticTrader | 45 | 2.27 | 5.53 | 3.52 | 10.12 | 73.90 |
| q1_2024 | B&H vol-target | 45 | 2.32 | 6.55 | 4.02 | 11.93 | 90.64 |
| q1_2024 | Buy&Hold | 45 | 2.32 | 7.05 | 4.78 | 13.74 | 99.81 |
| q1_2024 | KDJ+RSI | 45 | 0.53 | 3.09 | 2.82 | 6.89 | 44.88 |
| q1_2024 | MACD | 45 | 0.38 | 2.90 | 3.91 | 10.07 | 59.83 |
| q1_2024 | SMA(20/50) | 45 | 0.80 | 5.16 | 4.39 | 11.76 | 82.57 |
| q1_2024 | ZMR | 45 | 0.68 | 2.28 | 2.21 | 5.89 | 34.09 |

### summary: extended (45), reserve

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| reserve | AgenticTrader | 45 | -0.11 | 1.54 | 4.60 | 11.03 | 63.09 |
| reserve | B&H vol-target | 45 | -0.11 | 1.21 | 5.61 | 12.55 | 78.90 |
| reserve | Buy&Hold | 45 | -0.08 | 1.87 | 8.05 | 18.30 | 99.89 |
| reserve | KDJ+RSI | 45 | 0.42 | 3.51 | 4.73 | 12.10 | 59.86 |
| reserve | MACD | 45 | -0.82 | -0.76 | 6.07 | 12.84 | 55.92 |
| reserve | SMA(20/50) | 45 | -0.49 | 0.44 | 6.39 | 13.94 | 71.70 |
| reserve | ZMR | 45 | 0.81 | 2.51 | 3.99 | 10.23 | 46.71 |

### head to head: extended (45)

| period | baseline | agent wins | instruments | median Sharpe diff |
|:--|:--|--:|--:|--:|
| design | B&H vol-target | 12 | 45 | -0.09 |
| design | Buy&Hold | 20 | 45 | -0.02 |
| design | KDJ+RSI | 32 | 45 | 0.18 |
| design | MACD | 26 | 45 | 0.13 |
| design | SMA(20/50) | 26 | 45 | 0.06 |
| design | ZMR | 35 | 45 | 0.25 |
| holdout | B&H vol-target | 16 | 45 | -0.03 |
| holdout | Buy&Hold | 12 | 45 | -0.08 |
| holdout | KDJ+RSI | 21 | 45 | -0.06 |
| holdout | MACD | 23 | 45 | 0.04 |
| holdout | SMA(20/50) | 36 | 45 | 0.31 |
| holdout | ZMR | 27 | 45 | 0.10 |
| q1_2024 | B&H vol-target | 14 | 45 | -0.01 |
| q1_2024 | Buy&Hold | 11 | 45 | -0.01 |
| q1_2024 | KDJ+RSI | 23 | 45 | 0.03 |
| q1_2024 | MACD | 34 | 45 | 0.97 |
| q1_2024 | SMA(20/50) | 27 | 45 | 0.13 |
| q1_2024 | ZMR | 28 | 45 | 0.60 |
| reserve | B&H vol-target | 18 | 45 | -0.04 |
| reserve | Buy&Hold | 19 | 45 | -0.02 |
| reserve | KDJ+RSI | 14 | 45 | -0.34 |
| reserve | MACD | 29 | 45 | 0.62 |
| reserve | SMA(20/50) | 29 | 45 | 0.18 |
| reserve | ZMR | 14 | 45 | -0.58 |

### paired Sharpe, agent minus baseline: core (15) (scheme column: clusters needs 5 groups)

| period | baseline | n | mean Sharpe diff | ci95 low | ci95 high | p | wins | scheme | groups | significant |
|:--|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|
| design | B&H vol-target | 15 | 0.02 | -0.11 | 0.15 | 0.80 | 6 | instruments | 2 |  |
| design | Buy&Hold | 15 | 0.06 | -0.06 | 0.17 | 0.29 | 9 | instruments | 2 |  |
| design | KDJ+RSI | 15 | 0.20 | -0.10 | 0.48 | 0.17 | 10 | instruments | 2 |  |
| design | MACD | 15 | 0.26 | 0.09 | 0.43 | 0.00 | 10 | instruments | 2 | yes |
| design | SMA(20/50) | 15 | 0.09 | -0.09 | 0.29 | 0.34 | 8 | instruments | 2 |  |
| design | ZMR | 15 | 0.31 | -0.00 | 0.62 | 0.05 | 12 | instruments | 2 |  |
| holdout | B&H vol-target | 15 | -0.11 | -0.21 | -0.00 | 0.04 | 4 | instruments | 2 |  |
| holdout | Buy&Hold | 15 | -0.10 | -0.21 | -0.00 | 0.04 | 3 | instruments | 2 |  |
| holdout | KDJ+RSI | 15 | -0.04 | -0.25 | 0.20 | 0.68 | 5 | instruments | 2 |  |
| holdout | MACD | 15 | 0.21 | -0.01 | 0.40 | 0.05 | 12 | instruments | 2 |  |
| holdout | SMA(20/50) | 15 | 0.17 | -0.09 | 0.42 | 0.20 | 11 | instruments | 2 |  |
| holdout | ZMR | 15 | 0.16 | -0.11 | 0.48 | 0.28 | 10 | instruments | 2 |  |
| q1_2024 | B&H vol-target | 15 | 0.13 | -0.49 | 0.93 | 0.79 | 4 | instruments | 2 |  |
| q1_2024 | Buy&Hold | 15 | 0.18 | -0.45 | 0.96 | 0.70 | 5 | instruments | 2 |  |
| q1_2024 | KDJ+RSI | 15 | 0.65 | -0.69 | 2.00 | 0.35 | 8 | instruments | 2 |  |
| q1_2024 | MACD | 15 | 1.34 | 0.21 | 2.54 | 0.02 | 13 | instruments | 2 |  |
| q1_2024 | SMA(20/50) | 15 | 0.87 | -0.03 | 1.90 | 0.06 | 10 | instruments | 2 |  |
| q1_2024 | ZMR | 15 | 0.96 | -0.62 | 2.44 | 0.23 | 10 | instruments | 2 |  |
| reserve | B&H vol-target | 15 | -0.06 | -0.24 | 0.14 | 0.53 | 4 | instruments | 2 |  |
| reserve | Buy&Hold | 15 | -0.06 | -0.21 | 0.12 | 0.44 | 2 | instruments | 2 |  |
| reserve | KDJ+RSI | 15 | -0.76 | -1.66 | 0.19 | 0.11 | 5 | instruments | 2 |  |
| reserve | MACD | 15 | 0.36 | -0.65 | 1.32 | 0.47 | 10 | instruments | 2 |  |
| reserve | SMA(20/50) | 15 | 1.15 | 0.58 | 1.72 | 0.00 | 11 | instruments | 2 | yes |
| reserve | ZMR | 15 | 0.10 | -0.70 | 0.89 | 0.80 | 8 | instruments | 2 |  |

### paired Sharpe, agent minus baseline: extended (45) (scheme column: clusters needs 5 groups)

| period | baseline | n | mean Sharpe diff | ci95 low | ci95 high | p | wins | scheme | groups | significant |
|:--|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|
| design | B&H vol-target | 45 | -0.09 | -0.15 | -0.03 | 0.01 | 12 | instruments | 3 | yes |
| design | Buy&Hold | 45 | -0.04 | -0.10 | 0.02 | 0.21 | 20 | instruments | 3 |  |
| design | KDJ+RSI | 45 | 0.09 | -0.06 | 0.22 | 0.21 | 32 | instruments | 3 |  |
| design | MACD | 45 | 0.08 | -0.03 | 0.19 | 0.16 | 26 | instruments | 3 |  |
| design | SMA(20/50) | 45 | 0.05 | -0.05 | 0.14 | 0.32 | 26 | instruments | 3 |  |
| design | ZMR | 45 | 0.21 | 0.10 | 0.32 | 0.00 | 35 | instruments | 3 | yes |
| holdout | B&H vol-target | 45 | -0.03 | -0.09 | 0.02 | 0.19 | 16 | instruments | 3 |  |
| holdout | Buy&Hold | 45 | -0.07 | -0.12 | -0.02 | 0.01 | 12 | instruments | 3 | yes |
| holdout | KDJ+RSI | 45 | -0.06 | -0.22 | 0.09 | 0.43 | 21 | instruments | 3 |  |
| holdout | MACD | 45 | 0.08 | -0.07 | 0.23 | 0.30 | 23 | instruments | 3 |  |
| holdout | SMA(20/50) | 45 | 0.28 | 0.16 | 0.41 | 0.00 | 36 | instruments | 3 | yes |
| holdout | ZMR | 45 | 0.07 | -0.05 | 0.19 | 0.26 | 27 | instruments | 3 |  |
| q1_2024 | B&H vol-target | 45 | -0.26 | -0.63 | 0.01 | 0.06 | 14 | instruments | 3 |  |
| q1_2024 | Buy&Hold | 45 | -0.26 | -0.63 | 0.01 | 0.06 | 11 | instruments | 3 |  |
| q1_2024 | KDJ+RSI | 45 | 0.58 | -0.25 | 1.42 | 0.17 | 23 | instruments | 3 |  |
| q1_2024 | MACD | 45 | 1.14 | 0.59 | 1.69 | 0.00 | 34 | instruments | 3 | yes |
| q1_2024 | SMA(20/50) | 45 | 0.54 | 0.04 | 1.07 | 0.04 | 27 | instruments | 3 |  |
| q1_2024 | ZMR | 45 | 0.58 | -0.27 | 1.43 | 0.19 | 28 | instruments | 3 |  |
| reserve | B&H vol-target | 45 | 0.07 | -0.15 | 0.33 | 0.61 | 18 | instruments | 3 |  |
| reserve | Buy&Hold | 45 | 0.08 | -0.14 | 0.33 | 0.54 | 19 | instruments | 3 |  |
| reserve | KDJ+RSI | 45 | -0.81 | -1.40 | -0.22 | 0.01 | 14 | instruments | 3 | yes |
| reserve | MACD | 45 | 0.72 | 0.24 | 1.22 | 0.00 | 29 | instruments | 3 | yes |
| reserve | SMA(20/50) | 45 | 0.61 | 0.19 | 1.03 | 0.00 | 29 | instruments | 3 | yes |
| reserve | ZMR | 45 | -0.70 | -1.14 | -0.26 | 0.00 | 14 | instruments | 3 | yes |

### paired Sharpe, agent minus baseline: all 60 (scheme column: clusters needs 5 groups)

| period | baseline | n | mean Sharpe diff | ci95 low | ci95 high | p | wins | scheme | groups | significant |
|:--|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|
| design | B&H vol-target | 60 | -0.06 | -0.15 | 0.04 | 0.20 | 18 | clusters | 5 |  |
| design | Buy&Hold | 60 | -0.01 | -0.13 | 0.07 | 0.81 | 29 | clusters | 5 |  |
| design | KDJ+RSI | 60 | 0.12 | -0.33 | 0.36 | 0.49 | 42 | clusters | 5 |  |
| design | MACD | 60 | 0.12 | -0.04 | 0.26 | 0.12 | 36 | clusters | 5 |  |
| design | SMA(20/50) | 60 | 0.06 | -0.11 | 0.16 | 0.43 | 34 | clusters | 5 |  |
| design | ZMR | 60 | 0.24 | -0.11 | 0.45 | 0.15 | 47 | clusters | 5 |  |
| holdout | B&H vol-target | 60 | -0.05 | -0.15 | 0.00 | 0.07 | 20 | clusters | 5 |  |
| holdout | Buy&Hold | 60 | -0.08 | -0.15 | -0.03 | 0.00 | 15 | clusters | 5 | yes |
| holdout | KDJ+RSI | 60 | -0.06 | -0.22 | 0.09 | 0.37 | 26 | clusters | 5 |  |
| holdout | MACD | 60 | 0.11 | -0.04 | 0.37 | 0.17 | 35 | clusters | 5 |  |
| holdout | SMA(20/50) | 60 | 0.25 | 0.01 | 0.43 | 0.04 | 47 | clusters | 5 |  |
| holdout | ZMR | 60 | 0.09 | -0.06 | 0.23 | 0.20 | 37 | clusters | 5 |  |
| q1_2024 | B&H vol-target | 60 | -0.17 | -0.69 | 0.27 | 0.36 | 18 | clusters | 5 |  |
| q1_2024 | Buy&Hold | 60 | -0.15 | -0.68 | 0.28 | 0.40 | 16 | clusters | 5 |  |
| q1_2024 | KDJ+RSI | 60 | 0.60 | -0.77 | 1.46 | 0.34 | 31 | clusters | 5 |  |
| q1_2024 | MACD | 60 | 1.19 | 0.52 | 1.85 | 0.00 | 47 | clusters | 5 | yes |
| q1_2024 | SMA(20/50) | 60 | 0.63 | 0.04 | 1.86 | 0.03 | 37 | clusters | 5 |  |
| q1_2024 | ZMR | 60 | 0.67 | -0.74 | 1.63 | 0.29 | 38 | clusters | 5 |  |
| reserve | B&H vol-target | 60 | 0.04 | -0.16 | 0.27 | 0.73 | 22 | clusters | 5 |  |
| reserve | Buy&Hold | 60 | 0.04 | -0.15 | 0.27 | 0.66 | 21 | clusters | 5 |  |
| reserve | KDJ+RSI | 60 | -0.79 | -1.55 | -0.25 | 0.01 | 19 | clusters | 5 | yes |
| reserve | MACD | 60 | 0.63 | -0.55 | 1.26 | 0.26 | 39 | clusters | 5 |  |
| reserve | SMA(20/50) | 60 | 0.75 | 0.36 | 1.38 | 0.00 | 40 | clusters | 5 | yes |
| reserve | ZMR | 60 | -0.50 | -0.95 | 0.23 | 0.17 | 22 | clusters | 5 |  |

### paired MDD%, agent minus control: core (15)

| period | baseline | n | mean MDD% diff | ci95 low | ci95 high | p | wins | scheme | groups | significant |
|:--|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|
| design | B&H vol-target | 15 | -2.58 | -6.49 | 0.88 | 0.17 | 9 | instruments | 2 |  |
| design | Buy&Hold | 15 | -15.24 | -19.36 | -11.62 | 0.00 | 0 | instruments | 2 | yes |
| holdout | B&H vol-target | 15 | -1.58 | -4.33 | 1.14 | 0.27 | 8 | instruments | 2 |  |
| holdout | Buy&Hold | 15 | -14.24 | -20.41 | -8.70 | 0.00 | 2 | instruments | 2 | yes |
| q1_2024 | B&H vol-target | 15 | -0.66 | -1.13 | -0.22 | 0.00 | 2 | instruments | 2 | yes |
| q1_2024 | Buy&Hold | 15 | -1.75 | -2.52 | -1.03 | 0.00 | 0 | instruments | 2 | yes |
| reserve | B&H vol-target | 15 | 0.16 | -0.34 | 0.75 | 0.58 | 7 | instruments | 2 |  |
| reserve | Buy&Hold | 15 | -3.18 | -4.87 | -1.76 | 0.00 | 0 | instruments | 2 | yes |

### paired MDD%, agent minus control: extended (45)

| period | baseline | n | mean MDD% diff | ci95 low | ci95 high | p | wins | scheme | groups | significant |
|:--|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|
| design | B&H vol-target | 45 | -2.40 | -4.20 | -0.76 | 0.00 | 18 | instruments | 3 | yes |
| design | Buy&Hold | 45 | -14.21 | -17.93 | -10.81 | 0.00 | 3 | instruments | 3 | yes |
| holdout | B&H vol-target | 45 | -4.33 | -6.10 | -2.55 | 0.00 | 7 | instruments | 3 | yes |
| holdout | Buy&Hold | 45 | -10.93 | -13.41 | -8.64 | 0.00 | 2 | instruments | 3 | yes |
| q1_2024 | B&H vol-target | 45 | -0.49 | -0.76 | -0.26 | 0.00 | 7 | instruments | 3 | yes |
| q1_2024 | Buy&Hold | 45 | -1.25 | -1.88 | -0.76 | 0.00 | 3 | instruments | 3 | yes |
| reserve | B&H vol-target | 45 | -1.01 | -1.56 | -0.49 | 0.00 | 8 | instruments | 3 | yes |
| reserve | Buy&Hold | 45 | -3.45 | -4.42 | -2.57 | 0.00 | 1 | instruments | 3 | yes |

### paired Calmar, agent minus control: core (15)

| period | baseline | n | mean Calmar diff | ci95 low | ci95 high | p | wins | scheme | groups | significant |
|:--|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|
| design | B&H vol-target | 15 | -0.09 | -0.25 | 0.10 | 0.32 | 6 | instruments | 2 |  |
| design | Buy&Hold | 15 | 0.10 | -0.01 | 0.24 | 0.07 | 11 | instruments | 2 |  |
| holdout | B&H vol-target | 15 | -0.08 | -0.23 | 0.07 | 0.29 | 4 | instruments | 2 |  |
| holdout | Buy&Hold | 15 | 0.03 | -0.12 | 0.15 | 0.72 | 10 | instruments | 2 |  |
| q1_2024 | B&H vol-target | 15 | 0.77 | -1.89 | 3.52 | 0.59 | 7 | instruments | 2 |  |
| q1_2024 | Buy&Hold | 15 | -5.92 | -18.29 | 1.65 | 0.27 | 5 | instruments | 2 |  |
| reserve | B&H vol-target | 15 | -0.20 | -1.12 | 0.73 | 0.64 | 4 | instruments | 2 |  |
| reserve | Buy&Hold | 15 | -1.12 | -3.29 | 0.22 | 0.21 | 6 | instruments | 2 |  |

### paired Calmar, agent minus control: extended (45)

| period | baseline | n | mean Calmar diff | ci95 low | ci95 high | p | wins | scheme | groups | significant |
|:--|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|
| design | B&H vol-target | 45 | -0.08 | -0.14 | -0.03 | 0.00 | 16 | instruments | 3 | yes |
| design | Buy&Hold | 45 | 0.03 | -0.01 | 0.07 | 0.14 | 27 | instruments | 3 |  |
| holdout | B&H vol-target | 45 | 0.07 | 0.00 | 0.14 | 0.05 | 29 | instruments | 3 |  |
| holdout | Buy&Hold | 45 | 0.11 | 0.03 | 0.19 | 0.00 | 32 | instruments | 3 | yes |
| q1_2024 | B&H vol-target | 45 | -0.45 | -1.45 | 0.55 | 0.36 | 21 | instruments | 3 |  |
| q1_2024 | Buy&Hold | 45 | -0.19 | -1.17 | 0.75 | 0.70 | 22 | instruments | 3 |  |
| reserve | B&H vol-target | 45 | -0.17 | -1.07 | 0.79 | 0.69 | 21 | instruments | 3 |  |
| reserve | Buy&Hold | 45 | -0.14 | -1.03 | 0.84 | 0.73 | 23 | instruments | 3 |  |

### summary by asset class: core (15) equity (10), design

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| design | AgenticTrader | 10 | 0.99 | 172.32 | 21.37 | 15.60 | 63.55 |
| design | B&H vol-target | 10 | 1.07 | 192.10 | 20.64 | 16.28 | 71.58 |
| design | Buy&Hold | 10 | 0.94 | 622.20 | 39.66 | 28.61 | 100.00 |
| design | KDJ+RSI | 10 | 0.58 | 102.43 | 32.93 | 20.03 | 30.66 |
| design | MACD | 10 | 0.64 | 148.46 | 26.13 | 18.40 | 52.13 |
| design | SMA(20/50) | 10 | 0.89 | 254.61 | 26.08 | 20.91 | 69.13 |
| design | ZMR | 10 | 0.39 | 60.85 | 34.89 | 19.53 | 26.87 |

### summary by asset class: core (15) equity (10), holdout

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| holdout | AgenticTrader | 10 | 0.45 | 61.38 | 22.11 | 16.15 | 58.05 |
| holdout | B&H vol-target | 10 | 0.53 | 74.27 | 21.28 | 17.02 | 63.28 |
| holdout | Buy&Hold | 10 | 0.52 | 131.34 | 40.24 | 30.99 | 100.00 |
| holdout | KDJ+RSI | 10 | 0.52 | 68.10 | 27.87 | 21.76 | 40.17 |
| holdout | MACD | 10 | 0.43 | 41.38 | 34.03 | 21.46 | 50.40 |
| holdout | SMA(20/50) | 10 | 0.33 | 69.82 | 30.36 | 21.54 | 60.37 |
| holdout | ZMR | 10 | 0.25 | 48.25 | 24.60 | 20.07 | 33.13 |

### summary by asset class: core (15) equity (10), q1_2024

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| q1_2024 | AgenticTrader | 10 | 2.82 | 12.39 | 4.41 | 16.26 | 69.13 |
| q1_2024 | B&H vol-target | 10 | 2.89 | 12.37 | 4.96 | 17.04 | 75.60 |
| q1_2024 | Buy&Hold | 10 | 2.92 | 20.58 | 6.60 | 24.76 | 100.00 |
| q1_2024 | KDJ+RSI | 10 | 0.52 | 3.78 | 3.43 | 7.23 | 25.50 |
| q1_2024 | MACD | 10 | 0.90 | 10.50 | 5.05 | 18.89 | 51.83 |
| q1_2024 | SMA(20/50) | 10 | 2.92 | 20.18 | 4.72 | 22.28 | 82.33 |
| q1_2024 | ZMR | 10 | 0.00 | 1.77 | 2.28 | 5.75 | 15.83 |

### summary by asset class: core (15) equity (10), reserve

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| reserve | AgenticTrader | 10 | 1.34 | 6.72 | 5.51 | 17.10 | 58.36 |
| reserve | B&H vol-target | 10 | 1.54 | 6.74 | 5.04 | 16.63 | 56.87 |
| reserve | Buy&Hold | 10 | 1.39 | 11.84 | 10.04 | 31.18 | 100.00 |
| reserve | KDJ+RSI | 10 | 2.26 | 10.78 | 5.95 | 20.11 | 48.33 |
| reserve | MACD | 10 | -0.82 | 3.20 | 9.12 | 22.49 | 49.83 |
| reserve | SMA(20/50) | 10 | 0.52 | 2.88 | 7.97 | 20.78 | 66.33 |
| reserve | ZMR | 10 | 2.01 | 6.02 | 4.14 | 14.61 | 22.67 |

### paired Sharpe by asset class, agent minus control: core (15) equity (10)

| period | baseline | n | mean Sharpe diff | ci95 low | ci95 high | p | wins | scheme | groups | significant |
|:--|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|
| design | B&H vol-target | 10 | -0.05 | -0.12 | 0.04 | 0.22 | 2 | instruments | 1 |  |
| design | Buy&Hold | 10 | 0.02 | -0.03 | 0.07 | 0.49 | 5 | instruments | 1 |  |
| holdout | B&H vol-target | 10 | -0.09 | -0.14 | -0.03 | 0.00 | 2 | instruments | 1 | yes |
| holdout | Buy&Hold | 10 | -0.07 | -0.12 | -0.02 | 0.01 | 1 | instruments | 1 | yes |
| q1_2024 | B&H vol-target | 10 | -0.16 | -0.25 | -0.07 | 0.00 | 2 | instruments | 1 | yes |
| q1_2024 | Buy&Hold | 10 | -0.09 | -0.19 | 0.01 | 0.08 | 3 | instruments | 1 |  |
| reserve | B&H vol-target | 10 | -0.07 | -0.23 | 0.11 | 0.43 | 3 | instruments | 1 |  |
| reserve | Buy&Hold | 10 | -0.07 | -0.15 | 0.01 | 0.10 | 1 | instruments | 1 |  |

### paired MDD% by asset class, agent minus control: core (15) equity (10)

| period | baseline | n | mean MDD% diff | ci95 low | ci95 high | p | wins | scheme | groups | significant |
|:--|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|
| design | B&H vol-target | 10 | 0.73 | -3.38 | 3.62 | 0.60 | 9 | instruments | 1 |  |
| design | Buy&Hold | 10 | -18.29 | -22.98 | -14.60 | 0.00 | 0 | instruments | 1 | yes |
| holdout | B&H vol-target | 10 | 0.83 | -1.63 | 3.21 | 0.50 | 7 | instruments | 1 |  |
| holdout | Buy&Hold | 10 | -18.13 | -25.66 | -10.72 | 0.00 | 1 | instruments | 1 | yes |
| q1_2024 | B&H vol-target | 10 | -0.55 | -1.11 | -0.03 | 0.03 | 2 | instruments | 1 |  |
| q1_2024 | Buy&Hold | 10 | -2.19 | -3.15 | -1.26 | 0.00 | 0 | instruments | 1 | yes |
| reserve | B&H vol-target | 10 | 0.47 | -0.23 | 1.27 | 0.21 | 7 | instruments | 1 |  |
| reserve | Buy&Hold | 10 | -4.53 | -6.49 | -2.81 | 0.00 | 0 | instruments | 1 | yes |

### summary by asset class: core (15) fx (5), design

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| design | AgenticTrader | 5 | 0.13 | 9.91 | 10.03 | 5.46 | 62.83 |
| design | B&H vol-target | 5 | -0.07 | 0.63 | 19.25 | 8.23 | 98.37 |
| design | Buy&Hold | 5 | -0.07 | 1.13 | 19.17 | 8.22 | 97.30 |
| design | KDJ+RSI | 5 | 0.25 | 23.03 | 15.83 | 8.58 | 101.40 |
| design | MACD | 5 | -0.31 | -9.56 | 22.59 | 8.32 | 99.13 |
| design | SMA(20/50) | 5 | 0.16 | 8.25 | 17.26 | 8.19 | 98.08 |
| design | ZMR | 5 | 0.41 | 19.49 | 13.46 | 7.63 | 79.52 |

### summary by asset class: core (15) fx (5), holdout

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| holdout | AgenticTrader | 5 | 0.06 | 25.82 | 8.00 | 6.17 | 65.43 |
| holdout | B&H vol-target | 5 | -0.11 | 33.36 | 14.40 | 8.33 | 94.43 |
| holdout | Buy&Hold | 5 | -0.05 | 32.54 | 14.45 | 8.20 | 92.17 |
| holdout | KDJ+RSI | 5 | 0.21 | 27.40 | 16.05 | 8.98 | 101.75 |
| holdout | MACD | 5 | 0.02 | 15.57 | 14.51 | 8.66 | 98.95 |
| holdout | SMA(20/50) | 5 | 0.38 | 16.74 | 14.39 | 8.54 | 98.21 |
| holdout | ZMR | 5 | -0.04 | 16.36 | 15.95 | 7.91 | 82.45 |

### summary by asset class: core (15) fx (5), q1_2024

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| q1_2024 | AgenticTrader | 5 | 0.98 | 3.02 | 1.58 | 4.57 | 69.54 |
| q1_2024 | B&H vol-target | 5 | -0.66 | 1.95 | 2.46 | 6.25 | 99.32 |
| q1_2024 | Buy&Hold | 5 | -0.66 | 1.95 | 2.46 | 6.25 | 99.32 |
| q1_2024 | KDJ+RSI | 5 | -0.26 | 3.50 | 2.01 | 6.20 | 99.69 |
| q1_2024 | MACD | 5 | 0.22 | 0.42 | 3.76 | 6.25 | 98.94 |
| q1_2024 | SMA(20/50) | 5 | -2.25 | -1.42 | 3.39 | 6.34 | 100.14 |
| q1_2024 | ZMR | 5 | 0.86 | 3.04 | 2.30 | 5.40 | 76.16 |

### summary by asset class: core (15) fx (5), reserve

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| reserve | AgenticTrader | 5 | -0.09 | 0.59 | 2.72 | 4.77 | 78.15 |
| reserve | B&H vol-target | 5 | -0.18 | 0.66 | 3.20 | 5.87 | 99.48 |
| reserve | Buy&Hold | 5 | -0.18 | 0.66 | 3.20 | 5.87 | 99.48 |
| reserve | KDJ+RSI | 5 | -0.05 | 1.55 | 2.53 | 5.88 | 100.49 |
| reserve | MACD | 5 | 2.71 | 2.37 | 2.64 | 5.80 | 99.31 |
| reserve | SMA(20/50) | 5 | -1.96 | -1.35 | 2.82 | 5.86 | 99.73 |
| reserve | ZMR | 5 | -1.42 | 0.28 | 2.37 | 5.40 | 88.13 |

### paired Sharpe by asset class, agent minus control: core (15) fx (5)

| period | baseline | n | mean Sharpe diff | ci95 low | ci95 high | p | wins | scheme | groups | significant |
|:--|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|
| design | B&H vol-target | 5 | 0.16 | -0.21 | 0.46 | 0.30 | 4 | instruments | 1 |  |
| design | Buy&Hold | 5 | 0.15 | -0.21 | 0.44 | 0.34 | 4 | instruments | 1 |  |
| holdout | B&H vol-target | 5 | -0.15 | -0.43 | 0.14 | 0.33 | 2 | instruments | 1 |  |
| holdout | Buy&Hold | 5 | -0.16 | -0.45 | 0.13 | 0.23 | 2 | instruments | 1 |  |
| q1_2024 | B&H vol-target | 5 | 0.72 | -1.32 | 2.75 | 0.54 | 2 | instruments | 1 |  |
| q1_2024 | Buy&Hold | 5 | 0.72 | -1.32 | 2.75 | 0.54 | 2 | instruments | 1 |  |
| reserve | B&H vol-target | 5 | -0.04 | -0.44 | 0.47 | 0.80 | 1 | instruments | 1 |  |
| reserve | Buy&Hold | 5 | -0.04 | -0.44 | 0.47 | 0.80 | 1 | instruments | 1 |  |

### paired MDD% by asset class, agent minus control: core (15) fx (5)

| period | baseline | n | mean MDD% diff | ci95 low | ci95 high | p | wins | scheme | groups | significant |
|:--|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|
| design | B&H vol-target | 5 | -9.22 | -14.75 | -5.72 | 0.00 | 0 | instruments | 1 | yes |
| design | Buy&Hold | 5 | -9.15 | -14.46 | -5.67 | 0.00 | 0 | instruments | 1 | yes |
| holdout | B&H vol-target | 5 | -6.40 | -10.32 | -2.09 | 0.00 | 1 | instruments | 1 | yes |
| holdout | Buy&Hold | 5 | -6.46 | -10.34 | -2.14 | 0.00 | 1 | instruments | 1 | yes |
| q1_2024 | B&H vol-target | 5 | -0.88 | -1.82 | -0.25 | 0.00 | 0 | instruments | 1 | yes |
| q1_2024 | Buy&Hold | 5 | -0.88 | -1.82 | -0.25 | 0.00 | 0 | instruments | 1 | yes |
| reserve | B&H vol-target | 5 | -0.48 | -0.59 | -0.38 | 0.00 | 0 | instruments | 1 | yes |
| reserve | Buy&Hold | 5 | -0.48 | -0.59 | -0.38 | 0.00 | 0 | instruments | 1 | yes |

### summary by asset class: extended (45) equity (35), design

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| design | AgenticTrader | 35 | 0.58 | 73.25 | 20.14 | 12.69 | 66.82 |
| design | B&H vol-target | 35 | 0.72 | 93.43 | 22.29 | 14.56 | 81.82 |
| design | Buy&Hold | 35 | 0.64 | 133.13 | 37.37 | 23.14 | 100.00 |
| design | KDJ+RSI | 35 | 0.39 | 46.91 | 32.73 | 16.80 | 34.80 |
| design | MACD | 35 | 0.49 | 62.57 | 21.93 | 14.66 | 51.32 |
| design | SMA(20/50) | 35 | 0.66 | 75.15 | 24.78 | 15.24 | 64.87 |
| design | ZMR | 35 | 0.27 | 35.83 | 32.22 | 16.51 | 29.79 |

### summary by asset class: extended (45) equity (35), holdout

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| holdout | AgenticTrader | 35 | 0.25 | 44.67 | 17.68 | 13.29 | 63.26 |
| holdout | B&H vol-target | 35 | 0.27 | 47.70 | 22.44 | 15.50 | 77.75 |
| holdout | Buy&Hold | 35 | 0.39 | 74.53 | 30.79 | 22.37 | 100.00 |
| holdout | KDJ+RSI | 35 | 0.39 | 50.00 | 22.15 | 15.03 | 40.77 |
| holdout | MACD | 35 | 0.23 | 46.27 | 23.19 | 15.39 | 50.91 |
| holdout | SMA(20/50) | 35 | -0.07 | 32.98 | 26.80 | 16.25 | 58.00 |
| holdout | ZMR | 35 | 0.16 | 34.70 | 21.57 | 14.27 | 34.21 |

### summary by asset class: extended (45) equity (35), q1_2024

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| q1_2024 | AgenticTrader | 35 | 2.02 | 6.06 | 4.11 | 11.74 | 73.62 |
| q1_2024 | B&H vol-target | 35 | 1.97 | 7.09 | 4.68 | 13.66 | 88.22 |
| q1_2024 | Buy&Hold | 35 | 2.23 | 7.74 | 5.66 | 15.99 | 100.00 |
| q1_2024 | KDJ+RSI | 35 | 1.29 | 3.37 | 2.83 | 7.13 | 28.86 |
| q1_2024 | MACD | 35 | 0.38 | 3.35 | 4.23 | 11.23 | 48.48 |
| q1_2024 | SMA(20/50) | 35 | 1.67 | 6.49 | 4.76 | 13.38 | 77.62 |
| q1_2024 | ZMR | 35 | 0.68 | 2.30 | 2.19 | 6.01 | 20.24 |

### summary by asset class: extended (45) equity (35), reserve

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| reserve | AgenticTrader | 35 | -0.11 | 1.84 | 5.23 | 12.79 | 60.02 |
| reserve | B&H vol-target | 35 | -0.07 | 1.38 | 6.32 | 14.36 | 73.02 |
| reserve | Buy&Hold | 35 | -0.08 | 2.23 | 9.46 | 21.76 | 100.00 |
| reserve | KDJ+RSI | 35 | 0.20 | 3.45 | 5.43 | 13.79 | 48.29 |
| reserve | MACD | 35 | -1.27 | -1.26 | 7.07 | 14.73 | 43.52 |
| reserve | SMA(20/50) | 35 | -0.32 | 0.95 | 7.04 | 16.16 | 63.67 |
| reserve | ZMR | 35 | 0.99 | 2.83 | 4.47 | 11.54 | 37.19 |

### paired Sharpe by asset class, agent minus control: extended (45) equity (35)

| period | baseline | n | mean Sharpe diff | ci95 low | ci95 high | p | wins | scheme | groups | significant |
|:--|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|
| design | B&H vol-target | 35 | -0.05 | -0.09 | -0.01 | 0.02 | 9 | instruments | 2 |  |
| design | Buy&Hold | 35 | 0.00 | -0.03 | 0.04 | 0.87 | 17 | instruments | 2 |  |
| holdout | B&H vol-target | 35 | -0.01 | -0.06 | 0.04 | 0.73 | 15 | instruments | 2 |  |
| holdout | Buy&Hold | 35 | -0.06 | -0.11 | -0.01 | 0.02 | 10 | instruments | 2 |  |
| q1_2024 | B&H vol-target | 35 | -0.13 | -0.27 | -0.01 | 0.03 | 13 | instruments | 2 |  |
| q1_2024 | Buy&Hold | 35 | -0.12 | -0.26 | -0.01 | 0.04 | 10 | instruments | 2 |  |
| reserve | B&H vol-target | 35 | 0.07 | -0.09 | 0.24 | 0.44 | 15 | instruments | 2 |  |
| reserve | Buy&Hold | 35 | 0.08 | -0.06 | 0.25 | 0.31 | 16 | instruments | 2 |  |

### paired MDD% by asset class, agent minus control: extended (45) equity (35)

| period | baseline | n | mean MDD% diff | ci95 low | ci95 high | p | wins | scheme | groups | significant |
|:--|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|
| design | B&H vol-target | 35 | -2.15 | -4.24 | -0.28 | 0.02 | 15 | instruments | 2 | yes |
| design | Buy&Hold | 35 | -17.23 | -21.52 | -13.56 | 0.00 | 0 | instruments | 2 | yes |
| holdout | B&H vol-target | 35 | -4.76 | -7.00 | -2.54 | 0.00 | 7 | instruments | 2 | yes |
| holdout | Buy&Hold | 35 | -13.12 | -15.86 | -10.59 | 0.00 | 1 | instruments | 2 | yes |
| q1_2024 | B&H vol-target | 35 | -0.56 | -0.88 | -0.26 | 0.00 | 5 | instruments | 2 | yes |
| q1_2024 | Buy&Hold | 35 | -1.54 | -2.33 | -0.94 | 0.00 | 1 | instruments | 2 | yes |
| reserve | B&H vol-target | 35 | -1.10 | -1.76 | -0.45 | 0.00 | 7 | instruments | 2 | yes |
| reserve | Buy&Hold | 35 | -4.24 | -5.33 | -3.24 | 0.00 | 0 | instruments | 2 | yes |

### summary by asset class: extended (45) fx (10), design

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| design | AgenticTrader | 10 | -0.15 | 0.48 | 12.16 | 5.31 | 60.15 |
| design | B&H vol-target | 10 | 0.03 | 6.60 | 15.43 | 8.30 | 97.16 |
| design | Buy&Hold | 10 | 0.03 | 6.13 | 15.82 | 8.38 | 96.20 |
| design | KDJ+RSI | 10 | 0.57 | 31.19 | 15.28 | 8.77 | 101.07 |
| design | MACD | 10 | -0.02 | 6.11 | 18.03 | 8.54 | 99.04 |
| design | SMA(20/50) | 10 | -0.10 | -3.68 | 21.27 | 8.44 | 98.35 |
| design | ZMR | 10 | 0.10 | 8.48 | 14.75 | 7.94 | 79.97 |

### summary by asset class: extended (45) fx (10), holdout

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| holdout | AgenticTrader | 10 | 0.26 | 32.64 | 7.68 | 5.91 | 69.88 |
| holdout | B&H vol-target | 10 | 0.32 | 41.63 | 10.54 | 8.17 | 93.83 |
| holdout | Buy&Hold | 10 | 0.28 | 39.79 | 10.97 | 8.06 | 90.40 |
| holdout | KDJ+RSI | 10 | 0.42 | 37.28 | 13.11 | 8.84 | 101.16 |
| holdout | MACD | 10 | -0.06 | 13.28 | 15.47 | 8.64 | 99.09 |
| holdout | SMA(20/50) | 10 | -0.35 | 8.93 | 15.99 | 8.60 | 98.51 |
| holdout | ZMR | 10 | 0.18 | 30.51 | 11.04 | 7.88 | 81.10 |

### summary by asset class: extended (45) fx (10), q1_2024

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| q1_2024 | AgenticTrader | 10 | 2.86 | 3.66 | 1.45 | 4.44 | 74.91 |
| q1_2024 | B&H vol-target | 10 | 2.86 | 4.65 | 1.71 | 5.88 | 99.14 |
| q1_2024 | Buy&Hold | 10 | 2.86 | 4.65 | 1.71 | 5.88 | 99.14 |
| q1_2024 | KDJ+RSI | 10 | 0.04 | 2.13 | 2.80 | 6.04 | 100.95 |
| q1_2024 | MACD | 10 | 0.26 | 1.33 | 2.79 | 6.01 | 99.54 |
| q1_2024 | SMA(20/50) | 10 | -0.28 | 0.49 | 3.10 | 6.06 | 99.92 |
| q1_2024 | ZMR | 10 | 1.01 | 2.19 | 2.29 | 5.48 | 82.56 |

### summary by asset class: extended (45) fx (10), reserve

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| reserve | AgenticTrader | 10 | -0.14 | 0.50 | 2.42 | 4.86 | 73.87 |
| reserve | B&H vol-target | 10 | -0.34 | 0.62 | 3.10 | 6.21 | 99.50 |
| reserve | Buy&Hold | 10 | -0.34 | 0.62 | 3.10 | 6.21 | 99.50 |
| reserve | KDJ+RSI | 10 | 1.92 | 3.70 | 2.30 | 6.18 | 100.35 |
| reserve | MACD | 10 | -0.52 | 1.01 | 2.58 | 6.20 | 99.32 |
| reserve | SMA(20/50) | 10 | -1.50 | -1.36 | 4.14 | 6.16 | 99.82 |
| reserve | ZMR | 10 | 0.63 | 1.41 | 2.30 | 5.65 | 80.02 |

### paired Sharpe by asset class, agent minus control: extended (45) fx (10)

| period | baseline | n | mean Sharpe diff | ci95 low | ci95 high | p | wins | scheme | groups | significant |
|:--|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|
| design | B&H vol-target | 10 | -0.19 | -0.42 | 0.03 | 0.09 | 3 | instruments | 1 |  |
| design | Buy&Hold | 10 | -0.19 | -0.41 | 0.03 | 0.09 | 3 | instruments | 1 |  |
| holdout | B&H vol-target | 10 | -0.12 | -0.25 | 0.02 | 0.08 | 1 | instruments | 1 |  |
| holdout | Buy&Hold | 10 | -0.11 | -0.25 | 0.04 | 0.14 | 2 | instruments | 1 |  |
| q1_2024 | B&H vol-target | 10 | -0.75 | -2.29 | 0.37 | 0.26 | 1 | instruments | 1 |  |
| q1_2024 | Buy&Hold | 10 | -0.75 | -2.29 | 0.37 | 0.26 | 1 | instruments | 1 |  |
| reserve | B&H vol-target | 10 | 0.07 | -0.68 | 1.08 | 0.94 | 3 | instruments | 1 |  |
| reserve | Buy&Hold | 10 | 0.07 | -0.68 | 1.08 | 0.94 | 3 | instruments | 1 |  |

### paired MDD% by asset class, agent minus control: extended (45) fx (10)

| period | baseline | n | mean MDD% diff | ci95 low | ci95 high | p | wins | scheme | groups | significant |
|:--|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|
| design | B&H vol-target | 10 | -3.27 | -6.46 | 0.20 | 0.06 | 3 | instruments | 1 |  |
| design | Buy&Hold | 10 | -3.66 | -6.84 | -0.24 | 0.04 | 3 | instruments | 1 |  |
| holdout | B&H vol-target | 10 | -2.85 | -4.55 | -1.40 | 0.00 | 0 | instruments | 1 | yes |
| holdout | Buy&Hold | 10 | -3.28 | -5.31 | -1.51 | 0.00 | 1 | instruments | 1 | yes |
| q1_2024 | B&H vol-target | 10 | -0.25 | -0.53 | 0.03 | 0.08 | 2 | instruments | 1 |  |
| q1_2024 | Buy&Hold | 10 | -0.25 | -0.53 | 0.03 | 0.08 | 2 | instruments | 1 |  |
| reserve | B&H vol-target | 10 | -0.69 | -1.24 | -0.25 | 0.00 | 1 | instruments | 1 | yes |
| reserve | Buy&Hold | 10 | -0.69 | -1.24 | -0.25 | 0.00 | 1 | instruments | 1 | yes |

### EDGAR on (a) vs off (b)

| period | universe | n | mean Sharpe (a) | mean Sharpe (b) | mean diff | 95% CI | p | scheme | wins |
|:--|:--|--:|--:|--:|--:|:--|--:|:--|:--|
| design | core | 15 | 0.66 | 0.65 | 0.01 | [-0.03, +0.04] | 0.72 | instruments | 4 / 15 |
| design | extended | 45 | 0.48 | 0.47 | 0.01 | [+0.00, +0.02] | 0.02 | instruments | 16 / 45 |
| design | all | 60 | 0.52 | 0.51 | 0.01 | [-0.01, +0.02] | 0.19 | clusters | 20 / 60 |
| holdout | core | 15 | 0.34 | 0.35 | -0.01 | [-0.07, +0.04] | 0.83 | instruments | 6 / 15 |
| holdout | extended | 45 | 0.26 | 0.23 | 0.03 | [+0.01, +0.06] | 0.00 | instruments | 15 / 45 |
| holdout | all | 60 | 0.28 | 0.26 | 0.02 | [-0.02, +0.05] | 0.39 | clusters | 21 / 60 |
| q1_2024 | core | 15 | 1.89 | 1.80 | 0.09 | [+0.00, +0.21] | 0.02 | instruments | 4 / 15 |
| q1_2024 | extended | 45 | 1.55 | 1.50 | 0.05 | [+0.01, +0.11] | 0.00 | instruments | 7 / 45 |
| q1_2024 | all | 60 | 1.64 | 1.57 | 0.06 | [+0.00, +0.12] | 0.03 | clusters | 11 / 60 |
| reserve | core | 15 | 0.86 | 0.75 | 0.11 | [+0.00, +0.23] | 0.04 | instruments | 5 / 15 |
| reserve | extended | 45 | -0.09 | -0.11 | 0.03 | [-0.04, +0.10] | 0.45 | instruments | 10 / 45 |
| reserve | all | 60 | 0.15 | 0.10 | 0.05 | [-0.01, +0.13] | 0.16 | clusters | 15 / 60 |

### FX carry rule on (a) vs off (b)

| period | universe | n | mean Sharpe (a) | mean Sharpe (b) | mean diff | 95% CI | p | scheme | wins |
|:--|:--|--:|--:|--:|--:|:--|--:|:--|:--|
| design | core | 15 | 0.66 | 0.62 | 0.04 | [-0.01, +0.10] | 0.11 | instruments | 4 / 15 |
| design | extended | 45 | 0.48 | 0.46 | 0.02 | [-0.00, +0.05] | 0.11 | instruments | 6 / 45 |
| design | all | 60 | 0.52 | 0.50 | 0.03 | [+0.00, +0.09] | 0.20 | clusters | 10 / 60 |
| holdout | core | 15 | 0.34 | 0.32 | 0.02 | [-0.02, +0.07] | 0.37 | instruments | 4 / 15 |
| holdout | extended | 45 | 0.26 | 0.23 | 0.04 | [+0.00, +0.08] | 0.04 | instruments | 7 / 45 |
| holdout | all | 60 | 0.28 | 0.25 | 0.03 | [-0.00, +0.12] | 0.23 | clusters | 11 / 60 |
| q1_2024 | core | 15 | 1.89 | 1.39 | 0.49 | [+0.12, +0.94] | 0.01 | instruments | 5 / 15 |
| q1_2024 | extended | 45 | 1.55 | 1.40 | 0.15 | [+0.02, +0.30] | 0.02 | instruments | 8 / 45 |
| q1_2024 | all | 60 | 1.64 | 1.40 | 0.24 | [+0.00, +0.80] | 0.17 | clusters | 13 / 60 |
| reserve | core | 15 | 0.86 | 0.73 | 0.13 | [-0.06, +0.37] | 0.22 | instruments | 4 / 15 |
| reserve | extended | 45 | -0.09 | -0.23 | 0.14 | [+0.03, +0.28] | 0.00 | instruments | 6 / 45 |
| reserve | all | 60 | 0.15 | 0.01 | 0.14 | [+0.00, +0.48] | 0.19 | clusters | 10 / 60 |

### with the cross-sectional analyst (a) vs default (b)

| period | universe | n | mean Sharpe (a) | mean Sharpe (b) | mean diff | 95% CI | p | scheme | wins |
|:--|:--|--:|--:|--:|--:|:--|--:|:--|:--|
| design | core | 15 | 0.66 | 0.66 | -0.01 | [-0.02, +0.00] | 0.36 | instruments | 5 / 15 |
| design | extended | 45 | 0.48 | 0.48 | 0.00 | [-0.01, +0.01] | 0.50 | instruments | 21 / 45 |
| design | all | 60 | 0.53 | 0.52 | 0.00 | [-0.01, +0.02] | 0.94 | clusters | 26 / 60 |
| holdout | core | 15 | 0.35 | 0.34 | 0.00 | [-0.01, +0.02] | 0.60 | instruments | 9 / 15 |
| holdout | extended | 45 | 0.26 | 0.26 | -0.00 | [-0.01, +0.00] | 0.23 | instruments | 18 / 45 |
| holdout | all | 60 | 0.28 | 0.28 | -0.00 | [-0.02, +0.01] | 0.64 | clusters | 27 / 60 |
| q1_2024 | core | 15 | 1.98 | 1.89 | 0.09 | [+0.00, +0.20] | 0.04 | instruments | 5 / 15 |
| q1_2024 | extended | 45 | 1.53 | 1.55 | -0.02 | [-0.09, +0.02] | 0.46 | instruments | 14 / 45 |
| q1_2024 | all | 60 | 1.64 | 1.64 | 0.00 | [-0.08, +0.10] | 0.87 | clusters | 19 / 60 |
| reserve | core | 15 | 0.87 | 0.86 | 0.01 | [-0.00, +0.04] | 0.28 | instruments | 3 / 15 |
| reserve | extended | 45 | -0.11 | -0.09 | -0.02 | [-0.06, +0.01] | 0.20 | instruments | 14 / 45 |
| reserve | all | 60 | 0.14 | 0.15 | -0.01 | [-0.06, +0.02] | 0.56 | clusters | 17 / 60 |

### with the alpha analyst, corrected gate (a) vs default (b)

| period | universe | n | mean Sharpe (a) | mean Sharpe (b) | mean diff | 95% CI | p | scheme | wins |
|:--|:--|--:|--:|--:|--:|:--|--:|:--|:--|
| design | core | 15 | 0.66 | 0.66 | -0.00 | [-0.05, +0.05] | 0.90 | instruments | 5 / 15 |
| design | all | 15 | 0.66 | 0.66 | -0.00 | [-0.05, +0.05] | 0.90 | instruments | 5 / 15 |
| holdout | core | 15 | 0.34 | 0.34 | -0.00 | [-0.04, +0.02] | 0.79 | instruments | 8 / 15 |
| holdout | all | 15 | 0.34 | 0.34 | -0.00 | [-0.04, +0.02] | 0.79 | instruments | 8 / 15 |
| q1_2024 | core | 15 | 1.98 | 1.89 | 0.10 | [+0.01, +0.23] | 0.01 | instruments | 6 / 15 |
| q1_2024 | all | 15 | 1.98 | 1.89 | 0.10 | [+0.01, +0.23] | 0.01 | instruments | 6 / 15 |
| reserve | core | 15 | 0.93 | 0.86 | 0.07 | [-0.00, +0.20] | 0.21 | instruments | 3 / 15 |
| reserve | all | 15 | 0.93 | 0.86 | 0.07 | [-0.00, +0.20] | 0.21 | instruments | 3 / 15 |

### track-record size cut off (a) vs on (b)

| period | universe | n | mean Sharpe (a) | mean Sharpe (b) | mean diff | 95% CI | p | scheme | wins |
|:--|:--|--:|--:|--:|--:|:--|--:|:--|:--|
| design | core | 15 | 0.66 | 0.66 | 0.00 | [-0.00, +0.01] | 0.51 | instruments | 5 / 15 |
| design | extended | 45 | 0.49 | 0.48 | 0.01 | [+0.00, +0.01] | 0.01 | instruments | 24 / 45 |
| design | all | 60 | 0.53 | 0.52 | 0.01 | [+0.00, +0.01] | 0.03 | clusters | 29 / 60 |
| holdout | core | 15 | 0.35 | 0.34 | 0.01 | [-0.01, +0.02] | 0.46 | instruments | 7 / 15 |
| holdout | extended | 45 | 0.27 | 0.26 | 0.01 | [+0.00, +0.02] | 0.02 | instruments | 27 / 45 |
| holdout | all | 60 | 0.29 | 0.28 | 0.01 | [+0.00, +0.02] | 0.05 | clusters | 34 / 60 |
| q1_2024 | core | 15 | 1.91 | 1.89 | 0.02 | [-0.02, +0.07] | 0.55 | instruments | 2 / 15 |
| q1_2024 | extended | 45 | 1.59 | 1.55 | 0.04 | [+0.01, +0.07] | 0.00 | instruments | 7 / 45 |
| q1_2024 | all | 60 | 1.67 | 1.64 | 0.03 | [+0.01, +0.07] | 0.01 | clusters | 9 / 60 |
| reserve | core | 15 | 0.90 | 0.86 | 0.04 | [+0.00, +0.09] | 0.04 | instruments | 4 / 15 |
| reserve | extended | 45 | -0.09 | -0.09 | -0.00 | [-0.02, +0.02] | 0.86 | instruments | 6 / 45 |
| reserve | all | 60 | 0.16 | 0.15 | 0.01 | [-0.02, +0.05] | 0.54 | clusters | 10 / 60 |

### cash leg off (a) vs on (b)

| period | universe | n | mean Sharpe (a) | mean Sharpe (b) | mean diff | 95% CI | p | scheme | wins |
|:--|:--|--:|--:|--:|--:|:--|--:|:--|:--|
| design | core | 15 | 0.69 | 0.66 | 0.03 | [+0.02, +0.04] | 0.00 | instruments | 12 / 15 |
| design | extended | 45 | 0.52 | 0.48 | 0.04 | [+0.03, +0.06] | 0.00 | instruments | 35 / 45 |
| design | all | 60 | 0.57 | 0.52 | 0.04 | [+0.01, +0.06] | 0.01 | clusters | 47 / 60 |
| holdout | core | 15 | 0.45 | 0.34 | 0.10 | [+0.06, +0.15] | 0.00 | instruments | 10 / 15 |
| holdout | extended | 45 | 0.43 | 0.26 | 0.17 | [+0.13, +0.21] | 0.00 | instruments | 36 / 45 |
| holdout | all | 60 | 0.44 | 0.28 | 0.15 | [+0.04, +0.23] | 0.02 | clusters | 46 / 60 |
| q1_2024 | core | 15 | 2.07 | 1.89 | 0.18 | [+0.10, +0.27] | 0.00 | instruments | 11 / 15 |
| q1_2024 | extended | 45 | 1.84 | 1.55 | 0.29 | [+0.22, +0.35] | 0.00 | instruments | 37 / 45 |
| q1_2024 | all | 60 | 1.89 | 1.64 | 0.26 | [+0.07, +0.38] | 0.02 | clusters | 48 / 60 |
| reserve | core | 15 | 0.97 | 0.86 | 0.11 | [+0.07, +0.16] | 0.00 | instruments | 12 / 15 |
| reserve | extended | 45 | 0.09 | -0.09 | 0.18 | [+0.13, +0.24] | 0.00 | instruments | 35 / 45 |
| reserve | all | 60 | 0.31 | 0.15 | 0.16 | [+0.04, +0.27] | 0.00 | clusters | 47 / 60 |

### v0.3+ rules (a) vs v0.2 rules (b), core

| period | universe | n | mean Sharpe (a) | mean Sharpe (b) | mean diff | 95% CI | p | scheme | wins |
|:--|:--|--:|--:|--:|--:|:--|--:|:--|:--|
| design | core | 15 | 0.66 | 0.47 | 0.19 | [+0.10, +0.28] | 0.00 | instruments | 12 / 15 |
| design | all | 15 | 0.66 | 0.47 | 0.19 | [+0.10, +0.28] | 0.00 | instruments | 12 / 15 |
| holdout | core | 15 | 0.34 | 0.34 | -0.00 | [-0.11, +0.09] | 0.99 | instruments | 8 / 15 |
| holdout | all | 15 | 0.34 | 0.34 | -0.00 | [-0.11, +0.09] | 0.99 | instruments | 8 / 15 |
| q1_2024 | core | 15 | 1.89 | 1.17 | 0.72 | [+0.29, +1.17] | 0.00 | instruments | 12 / 15 |
| q1_2024 | all | 15 | 1.89 | 1.17 | 0.72 | [+0.29, +1.17] | 0.00 | instruments | 12 / 15 |
| reserve | core | 15 | 0.86 | -0.09 | 0.95 | [+0.45, +1.47] | 0.00 | instruments | 13 / 15 |
| reserve | all | 15 | 0.86 | -0.09 | 0.95 | [+0.45, +1.47] | 0.00 | instruments | 13 / 15 |

### portfolio: design

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 93.64 | 11.61 | 7.37 | 1.40 | 3.43 | 10.17 | 1.14 | 61.81 |
| Buy&Hold | 197.51 | 19.87 | 14.25 | 1.28 | 3.13 | 22.69 | 0.88 | 96.74 |
| B&H vol-target | 98.58 | 12.08 | 7.53 | 1.43 | 3.50 | 9.45 | 1.28 | 78.80 |
| SMA(20/50) | 115.79 | 13.64 | 8.87 | 1.38 | 3.39 | 9.49 | 1.44 | 77.13 |
| MACD | 71.22 | 9.35 | 7.44 | 1.11 | 2.73 | 14.77 | 0.63 | 66.53 |
| KDJ+RSI | 67.72 | 8.98 | 9.96 | 0.82 | 2.01 | 18.06 | 0.50 | 53.47 |
| ZMR | 44.36 | 6.29 | 9.94 | 0.57 | 1.40 | 19.25 | 0.33 | 43.75 |

### portfolio Sharpe difference (paired block bootstrap over days): design

- agent minus B&H vol-target: -0.03 [-0.28, +0.23] p=0.898 (n=1564 days, block 10)
- agent minus Buy&Hold: +0.12 [-0.16, +0.40] p=0.434 (n=1564 days, block 10)

### cash leg on vs off: design

| index | Sharpe (cash leg) | CR% (cash leg) | MDD% (cash leg) | Exp% (cash leg) | Sharpe (no cash leg) | CR% (no cash leg) | MDD% (no cash leg) | Exp% (no cash leg) |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 1.40 | 93.64 | 10.17 | 61.81 | 1.46 | 87.97 | 10.20 | 61.86 |
| Buy&Hold | 1.28 | 197.51 | 22.69 | 96.74 | 1.32 | 192.05 | 22.77 | 97.76 |
| B&H vol-target | 1.43 | 98.58 | 9.45 | 78.80 | 1.49 | 92.72 | 9.76 | 79.25 |
| SMA(20/50) | 1.38 | 115.79 | 9.49 | 77.13 | 1.43 | 109.09 | 9.53 | 77.17 |
| MACD | 1.11 | 71.22 | 14.77 | 66.53 | 1.16 | 65.06 | 15.37 | 66.54 |
| KDJ+RSI | 0.82 | 67.72 | 18.06 | 53.47 | 0.84 | 60.49 | 18.21 | 53.51 |
| ZMR | 0.57 | 44.36 | 19.25 | 43.75 | 0.59 | 37.91 | 19.32 | 43.76 |

### portfolio: holdout

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 50.62 | 9.55 | 6.71 | 0.80 | 1.70 | 7.80 | 1.22 | 59.10 |
| Buy&Hold | 96.91 | 16.29 | 14.08 | 0.86 | 1.82 | 20.43 | 0.80 | 94.96 |
| B&H vol-target | 61.48 | 11.27 | 7.01 | 0.99 | 2.10 | 9.17 | 1.23 | 72.12 |
| SMA(20/50) | 49.35 | 9.35 | 8.22 | 0.64 | 1.36 | 11.98 | 0.78 | 71.51 |
| MACD | 35.29 | 6.97 | 8.22 | 0.38 | 0.80 | 16.02 | 0.43 | 65.35 |
| KDJ+RSI | 58.49 | 10.81 | 9.57 | 0.70 | 1.49 | 12.92 | 0.84 | 59.70 |
| ZMR | 40.93 | 7.94 | 9.11 | 0.45 | 0.95 | 9.82 | 0.81 | 48.75 |

### portfolio Sharpe difference (paired block bootstrap over days): holdout

- agent minus B&H vol-target: -0.19 [-0.53, +0.16] p=0.297 (n=1167 days, block 10)
- agent minus Buy&Hold: -0.06 [-0.41, +0.30] p=0.748 (n=1167 days, block 10)

### cash leg on vs off: holdout

| index | Sharpe (cash leg) | CR% (cash leg) | MDD% (cash leg) | Exp% (cash leg) | Sharpe (no cash leg) | CR% (no cash leg) | MDD% (no cash leg) | Exp% (no cash leg) |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 0.80 | 50.62 | 7.80 | 59.10 | 1.04 | 35.17 | 8.01 | 59.07 |
| Buy&Hold | 0.86 | 96.91 | 20.43 | 94.96 | 1.05 | 86.23 | 20.79 | 97.47 |
| B&H vol-target | 0.99 | 61.48 | 9.17 | 72.12 | 1.24 | 46.21 | 9.85 | 73.94 |
| SMA(20/50) | 0.64 | 49.35 | 11.98 | 71.51 | 0.85 | 34.89 | 13.23 | 71.66 |
| MACD | 0.38 | 35.29 | 16.02 | 65.35 | 0.54 | 20.26 | 16.31 | 65.39 |
| KDJ+RSI | 0.70 | 58.49 | 12.92 | 59.70 | 0.81 | 38.85 | 13.50 | 59.87 |
| ZMR | 0.45 | 40.93 | 9.82 | 48.75 | 0.54 | 22.25 | 10.38 | 48.79 |

### execution algorithm, $1B holdout portfolio (sleeve impact at the sleeve's capital; FX sleeves pay no impact without costs.fx_adv_notional and are excluded from the mean)

| execution algo | Sharpe | CR% | MDD% | mean equity-sleeve impact paid % | equity sleeves |
|:--|--:|--:|--:|--:|--:|
| VWAP (default) | 0.78 | 49.62 | 7.83 | 0.99 | 10 |
| TWAP | 0.78 | 49.56 | 7.83 | 1.05 | 10 |
| Almgren-Chriss, kappa=5 | 0.77 | 49.30 | 7.84 | 1.31 | 10 |

### impact sweep, core universe, textbook coefficient 1.0 (equity-scaled impact)

| strategy | period | Sharpe (off) | Sharpe $100k | impact % $100k | Sharpe $10M | impact % $10M | Sharpe $1B | impact % $1B |
|:--|:--|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | design | 0.66 | 0.66 | 0.04 | 0.66 | 0.43 | 0.61 | 4.24 |
| AgenticTrader | holdout | 0.34 | 0.34 | 0.03 | 0.34 | 0.26 | 0.31 | 2.53 |
| B&H vol-target | design | 0.64 | 0.64 | 0.07 | 0.64 | 0.71 | 0.57 | 6.92 |
| B&H vol-target | holdout | 0.45 | 0.45 | 0.04 | 0.45 | 0.36 | 0.41 | 3.57 |
| Buy&Hold | design | 0.60 | 0.60 | 0.01 | 0.60 | 0.10 | 0.59 | 0.97 |
| Buy&Hold | holdout | 0.45 | 0.45 | 0.00 | 0.45 | 0.05 | 0.44 | 0.48 |
| SMA(20/50) | design | 0.57 | 0.57 | 0.28 | 0.55 | 2.75 | 0.38 | 24.63 |
| SMA(20/50) | holdout | 0.18 | 0.18 | 0.14 | 0.16 | 1.37 | 0.04 | 12.99 |
| MACD | design | 0.40 | 0.39 | 0.87 | 0.32 | 8.42 | -0.18 | 64.71 |
| MACD | holdout | 0.14 | 0.13 | 0.46 | 0.09 | 4.53 | -0.30 | 39.01 |

### VaR coverage: rolling historical VaR of the 15-sleeve portfolio's own returns

| forecast | n | breaches | breach_rate | kupiec_p | christoffersen_p | conditional_coverage_p |
|:--|--:|--:|--:|--:|--:|--:|
| portfolio returns, 120-day rolling historical VaR | 1048 | 65 | 0.0620 | 0.0847 | 0.1488 | 0.0798 |
| portfolio returns, 250-day rolling historical VaR | 918 | 42 | 0.0458 | 0.5493 | 0.1650 | 0.3188 |

### VaR coverage: the desk's own per-instrument forecast (250-day historical VaR, agents/risk.py) vs next-day returns, holdout; Kupiec rejects at 5%: 2 of 15

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

### trials registry: 26 variants judged on the design period

| trial | version | design portfolio Sharpe | design mean Sharpe (v0.8 engine) | recorded (v0.3 engine) | re-measured | design mean CR% | design mean MDD% | design mean Exp% | design mean Trades |
|:--|:--|:--|--:|--:|--:|--:|--:|--:|--:|
| v0.2 (control) | v0.3 | None | 0.47 | 0.50 | yes | 58.24 | 13.31 | 43.99 | 254.20 |
| + 12-1 month time-series momentum | v0.3 | None | 0.47 | 0.47 | yes | 73.93 | 13.56 | 47.74 | 262.47 |
| + trend-filtered reversal | v0.3 | None | 0.46 | 0.48 | yes | 58.40 | 13.50 | 44.66 | 254.53 |
| + abstain without data | v0.3 | None | 0.48 | 0.51 | yes | 62.72 | 13.98 | 46.78 | 258.27 |
| + no-trade band 0.10 | v0.3 | None | 0.47 | 0.50 | yes | 58.11 | 13.18 | 43.80 | 135.20 |
| + intraday stops | v0.3 | None | 0.45 | 0.47 | yes | 44.10 | 12.67 | 40.30 | 292.20 |
| signal changes (momentum + filter + abstain) | v0.3 | None | 0.48 | 0.51 | yes | 77.65 | 13.98 | 50.33 | 268.27 |
| signal changes + band | v0.3 | None | 0.48 | 0.51 | yes | 77.71 | 14.01 | 49.85 | 117.27 |
| all five | v0.3 | None | 0.46 | 0.50 | yes | 54.82 | 13.16 | 45.66 | 188.80 |
| strategic equity weight 0.25 | v0.3 | None | 0.54 | 0.54 | yes | 82.41 | 14.00 | 50.55 | 282.40 |
| strategic equity weight 0.50 | v0.3 | None | 0.58 | 0.58 | yes | 100.26 | 14.71 | 54.86 | 287.73 |
| strategic equity weight 1.00 | v0.3 | None | 0.63 | 0.66 | yes | 121.95 | 17.07 | 60.37 | 292.67 |
| strategic 0.50 + band | v0.3 | None | 0.58 | 0.58 | yes | 96.41 | 14.73 | 54.20 | 118.60 |
| strategic 0.50 + signal changes + band | v0.3 | None | 0.57 | 0.58 | yes | 105.72 | 15.89 | 57.42 | 104.67 |
| strategic 0.50 + abstain + band | v0.3 | None | 0.58 | 0.56 | yes | 97.10 | 14.98 | 55.60 | 117.40 |
| frozen v0.3: strategic 1.00 + band | v0.3 | None | 0.62 | 0.65 | yes | 116.52 | 17.62 | 59.52 | 98.60 |
| + alpha analyst (IC-weighted, all signals) | v0.4 | None |  | 0.60 |  |  |  |  |  |
| + alpha analyst (significance-gated, 400-day window) | v0.4 | None |  | 0.58 |  |  |  |  |  |
| + alpha analyst (significance-gated, 900-day window) | v0.5 | None | 0.66 | 0.65 | yes | 119.23 | 17.42 | 62.42 | 93.87 |
| FX carry / 4, cap 0.5 | v0.5.1 | None | 0.65 |  | yes | 117.63 | 17.53 | 62.15 | 94.27 |
| FX carry / 2, cap 0.5 (adopted) | v0.5.1 | None | 0.66 |  | yes | 118.18 | 17.59 | 63.31 | 91.73 |
| FX carry / 4, cap 1.0 | v0.5.1 | None | 0.65 |  | yes | 117.63 | 17.55 | 62.16 | 93.60 |
| FX carry / 8, cap 0.25 | v0.5.1 | None | 0.64 |  | yes | 117.18 | 17.53 | 61.11 | 96.87 |
| + cross-sectional alpha analyst | v0.6 | None | 0.66 |  | yes | 119.86 | 17.70 | 63.28 | 90.33 |
| EDGAR filings off | v0.6 | None | 0.65 |  | yes | 110.44 | 15.30 | 60.48 | 108.00 |
| track-record size cut off | v0.8 | None | 0.66 |  | yes | 118.74 | 17.97 | 63.79 | 89.80 |

### selection statistics for the frozen rules (design-period 15-sleeve portfolio Sharpe, 260 periods/year, every trial's portfolio Sharpe as the benchmark)

```json
{
 "n": 1564,
 "sharpe_annual": 1.4,
 "t_stat": 3.43,
 "skew": -0.635,
 "kurtosis": 8.41,
 "bootstrap_ci_95": [
  0.607,
  2.209
 ],
 "psr_vs_zero": 1.0,
 "trials": 0,
 "expected_max_sharpe_annual": 0.0,
 "deflated_sharpe_prob": 1.0,
 "min_track_record_periods": 385,
 "caveat": null,
 "trials_in_registry": 26,
 "trials_without_portfolio_sharpe": [
  "v0.2 (control)",
  "+ 12-1 month time-series momentum",
  "+ trend-filtered reversal",
  "+ abstain without data",
  "+ no-trade band 0.10",
  "+ intraday stops",
  "signal changes (momentum + filter + abstain)",
  "signal changes + band",
  "all five",
  "strategic equity weight 0.25",
  "strategic equity weight 0.50",
  "strategic equity weight 1.00",
  "strategic 0.50 + band",
  "strategic 0.50 + signal changes + band",
  "strategic 0.50 + abstain + band",
  "frozen v0.3: strategic 1.00 + band",
  "+ alpha analyst (IC-weighted, all signals)",
  "+ alpha analyst (significance-gated, 400-day window)",
  "+ alpha analyst (significance-gated, 900-day window)",
  "FX carry / 4, cap 0.5",
  "FX carry / 2, cap 0.5 (adopted)",
  "FX carry / 4, cap 1.0",
  "FX carry / 8, cap 0.25",
  "+ cross-sectional alpha analyst",
  "EDGAR filings off",
  "track-record size cut off"
 ]
}
```

### rebalance-phase sweep, holdout portfolio (5-bar cadence, offsets 0-4): agent Sharpe spread 0.06

| offset | agent Sharpe | vol-target Sharpe | B&H Sharpe | agent - vol-target | agent - B&H |
|--:|--:|--:|--:|:--|:--|
| 0 | 0.80 | 0.99 | 0.86 | -0.19 [-0.53, +0.16] p=0.297 (n=1167 days, block 10) | -0.06 [-0.41, +0.30] p=0.748 (n=1167 days, block 10) |
| 1 | 0.85 | 0.99 | 0.86 | -0.14 [-0.46, +0.19] p=0.429 (n=1167 days, block 10) | -0.01 [-0.34, +0.35] p=0.988 (n=1167 days, block 10) |
| 2 | 0.86 | 0.99 | 0.86 | -0.13 [-0.46, +0.21] p=0.468 (n=1167 days, block 10) | +0.00 [-0.35, +0.38] p=0.981 (n=1167 days, block 10) |
| 3 | 0.80 | 0.99 | 0.86 | -0.19 [-0.51, +0.15] p=0.284 (n=1167 days, block 10) | -0.06 [-0.40, +0.31] p=0.774 (n=1167 days, block 10) |
| 4 | 0.84 | 0.99 | 0.86 | -0.15 [-0.49, +0.19] p=0.390 (n=1167 days, block 10) | -0.02 [-0.37, +0.34] p=0.911 (n=1167 days, block 10) |
