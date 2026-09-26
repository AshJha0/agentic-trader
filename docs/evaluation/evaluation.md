# Evaluation

This document records how agentic-trader is evaluated, what was measured, and what the
numbers do and do not show. Every figure comes from a recorded run, and the tables were
generated from the saved result files rather than typed. To reproduce them, see
[Reproducing](#reproducing).

> **Scope.** All results use the **rule-based agents** (offline mode, no LLM) on **real
> prices** from Yahoo Finance. The LLM mode has **not** been evaluated, so nothing here
> describes Claude's trading performance. The core-universe measurements were taken on
> 2026-09-25, the extended-universe, reserve-period and impact-sweep measurements on
> 2026-09-26, all with the C++ backend and the frozen v0.3 rules.

## Summary

- **Out of sample, the agents do not beat buy & hold on Sharpe instrument by instrument.**
  Holdout mean Sharpe is 0.44 against 0.55 for buy & hold over the 15 core instruments, and
  0.37 against 0.50 over the 45 extended instruments that no rule choice ever consulted
  (v0.5). In core equities alone it is 0.63 against 0.68.
- **They consistently take about half the drawdown.** Holdout equity mean maximum drawdown is
  19.1% against 40.2% for buy & hold on the core universe, 17.7% against 27.2% on the
  extended one, and it is lower in every period and on 40 of the 45 extended names.
- **Execution costs do not change the ranking below institutional size.** With square-root
  market impact on (v0.5), the desk's mean Sharpe on the core universe is unchanged at
  $100k, 0.01 lower at $10M and 0.09 lower at $1B; signal-flipping baselines lose far more.
- **As a portfolio of all 15 instruments they beat plain buy & hold on Sharpe** in both
  periods: 1.14 against 1.06 on the holdout, with a drawdown of 6.8% against 20.8%. They do
  **not** beat buy & hold scaled to the same volatility target (1.24).
- **v0.3's rule changes were chosen on 2016–2021 data only.**
  - On that data, equity mean Sharpe rose from 0.76 to 0.99.
  - On the untouched 2022–2026 holdout, the gain shrank to 0.60 → 0.63. Mean return still
    rose from 21% to 32%, and trades fell by about half (163 → 86).
- **Most literature-backed signal tweaks did nothing** measurable on the design period. The
  one change that worked, a strategic (benchmark) equity weight, works by collecting the
  equity premium, not by forecasting better.
- **The v0.4 alpha analyst did not help either** on the design period (mean Sharpe 0.65 →
  0.60), so it is off by default.
- **After correcting for the 16 variants tried, the chosen rule set still clears the bar on
  the design period** (deflated Sharpe probability 1.00), with the caveats given below.
- **FX is roughly zero** before and after the changes.

## Protocol

### Periods

| Period | Key | Dates | Use |
|---|---|---|---|
| **Design** | `design` | 2016-01-04 → 2021-12-31 | The **only** data used to choose rule changes and defaults |
| **Holdout** | `holdout` | 2022-01-03 → 2026-06-30 | Run **once**, with frozen rules. Never used for a choice |
| **Q1 2024** | `q1_2024` | 2024-01-02 → 2024-03-28 | A short reference window inside the holdout, kept because a single quarter is what many published LLM-trading results are based on |
| **Reserve** | `reserve` | 2026-07-01 → 2026-09-25 | v0.5. Untouched by every choice and every number quoted anywhere else; it grows with time and is part of the fresh holdout for the next rule change (see [the next rule change](#the-next-rule-change-what-counts-as-unseen)) |

### Settings

| Item | Setting |
|---|---|
| Core universe | The 15 instruments every rule choice through v0.4 was made on. 10 equities: AAPL, NVDA, MSFT, META, GOOGL, AMZN, JPM, XOM, JNJ and SPY (large-cap technology plus financials, energy, healthcare and the index). 5 FX pairs: EURUSD, USDJPY, GBPUSD, AUDUSD, USDCAD |
| Extended universe (v0.5) | 45 instruments that no choice ever consulted. 26 equities across sectors and styles: UNH, V, MA, PG, HD, COST, WMT, KO, PEP, CVX, LLY, ABBV, MRK, BAC, GS, CAT, BA, BRK-B, QQQ, IWM, XLF, XLE, XLV, XLU, EEM, EFA. 9 rates / credit / commodity / real-estate ETFs, traded as equities: TLT, IEF, LQD, HYG, GLD, SLV, USO, DBC, VNQ. 10 FX crosses whose both legs have FRED policy-rate series: NZDUSD, USDCHF, EURGBP, EURJPY, GBPJPY, AUDJPY, EURCHF, AUDNZD, CADJPY, EURAUD |
| Prices | Yahoo Finance daily, dividend- and split-adjusted (total return) |
| News and fundamentals | None for historical dates. Yahoo serves only recent news and current-snapshot fundamentals, and the point-in-time guards refuse both, so the news and fundamentals analysts have no data |
| FX macro | Point-in-time **FRED** policy rates. Values are publication-lagged (daily series by 1 day, monthly averages by about 40 days) and treated as unavailable when stale. Carry is accrued per bar from the same series |
| Rebalancing | Every 5 bars: a full `propagate()` with data up to that close and the current position. The weight is held to the next rebalance |
| Warm-up | 400 calendar days of history before each window |
| Equity costs | 1 bps commission + 1 bps slippage per unit of turnover; 1% p.a. borrow (shorts are disabled) |
| FX costs | Half of a 0.8-pip spread, in bps at the window's first price, + 0.2 bps slippage; shorts enabled |
| Limits | \|weight\| ≤ 1.0; 1-day VaR95 of the position ≤ 2%; weights below 0.05 become flat |
| Execution | A weight decided at close *t* earns the return from *t* to *t + 1* |

### Baselines

| Baseline | What it tests |
|---|---|
| Buy & Hold | The market |
| **B&H vol-target** | Buy & hold scaled every day to the risk team's 15% volatility target, from trailing 20-day volatility (ex ante), capped at 1.0. **This is the fair control.** A risk-managed strategy beats plain buy & hold on drawdown just by holding less; beating this version requires good directional calls |
| SMA(20/50), MACD(12,26,9), KDJ(9)+RSI(14), ZMR (20-day z-score) | Common rule-based trend and mean-reversion strategies |

### Metrics

With per-period returns *r*, *n* periods and *P* periods per year (252 for equities, 260
for FX):

| Metric | Definition |
|---|---|
| CR | *V_end / V_start − 1* |
| AR | *(1 + CR)^(P/n) − 1* |
| Vol | *std(r, ddof = 1) · √P* |
| Sharpe | *mean(r) / std(r) · √P* (risk-free rate 0) |
| t(SR) | *mean(r) / std(r) · √n*: the t-statistic of the mean return. About 2 is needed before a Sharpe ratio is distinguishable from 0 |
| MDD | *max over t of (1 − V_t / max_{s≤t} V_s)* |
| Exposure | Mean \|weight\| per period |
| Trades | Number of changes in the held weight (vol-target B&H changes weight almost daily) |

Cross-instrument figures are simple means or medians over instruments. The `n` column
counts instruments.

## Headline results

### Design period (2016–2021): used to choose the v0.3 rules

| class | strategy | n | mean Sharpe | median Sharpe | mean CR % | mean MDD % | mean Vol % | mean exposure % | mean trades |
|:--|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| equity | AgenticTrader v0.2 | 10 | 0.76 | 0.68 | 73.40 | 16.47 | 10.21 | 38.02 | 210.40 |
| equity | **AgenticTrader v0.3** | 10 | **0.99** | **1.05** | 158.23 | 17.78 | 14.36 | 59.19 | 82.40 |
| equity | Buy & hold | 10 | 0.96 | 0.99 | 622.20 | 39.66 | 28.61 | 100.00 | 1.00 |
| equity | B&H vol-target | 10 | 1.04 | 1.13 | 187.15 | 20.89 | 16.28 | 71.58 | 1117.80 |
| fx | AgenticTrader v0.2 | 5 | -0.04 | 0.11 | -1.04 | 11.63 | 4.87 | 51.71 | 272.40 |
| fx | **AgenticTrader v0.3** | 5 | -0.03 | 0.12 | -0.79 | 11.58 | 4.87 | 51.69 | 154.60 |
| fx | Buy & hold | 5 | -0.05 | -0.06 | -4.30 | 21.82 | 8.42 | 100.00 | 1.00 |
| fx | B&H vol-target | 5 | -0.06 | -0.06 | -5.11 | 21.65 | 8.31 | 99.52 | 44.40 |
| all | AgenticTrader v0.2 | 15 | 0.50 | 0.42 | 48.59 | 14.86 | 8.43 | 42.58 | 231.07 |
| all | **AgenticTrader v0.3** | 15 | **0.65** | **0.55** | 105.22 | 15.72 | 11.20 | 56.69 | 106.47 |
| all | Buy & hold | 15 | 0.63 | 0.76 | 413.36 | 33.71 | 21.88 | 100.00 | 1.00 |
| all | B&H vol-target | 15 | 0.67 | 0.75 | 123.06 | 21.15 | 13.63 | 80.89 | 760.00 |

### Holdout period (2022–2026): run once with frozen rules

| class | strategy | n | mean Sharpe | median Sharpe | mean CR % | mean MDD % | mean Vol % | mean exposure % | mean trades |
|:--|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| equity | AgenticTrader v0.2 | 10 | 0.60 | 0.69 | 30.42 | 15.05 | 9.78 | 28.29 | 143.10 |
| equity | **AgenticTrader v0.3** | 10 | **0.63** | 0.68 | 47.37 | 19.07 | 14.23 | 50.68 | 73.70 |
| equity | Buy & hold | 10 | 0.68 | 0.74 | 131.34 | 40.24 | 31.00 | 100.00 | 1.00 |
| equity | B&H vol-target | 10 | 0.71 | 0.71 | 63.37 | 21.85 | 17.03 | 63.28 | 962.10 |
| fx | AgenticTrader v0.2 | 5 | 0.06 | -0.01 | 1.95 | 11.21 | 5.37 | 54.18 | 202.40 |
| fx | **AgenticTrader v0.3** | 5 | 0.04 | -0.02 | 1.47 | 11.27 | 5.34 | 53.95 | 110.20 |
| fx | Buy & hold | 5 | 0.28 | -0.03 | 12.97 | 16.76 | 8.76 | 100.00 | 1.00 |
| fx | B&H vol-target | 5 | 0.26 | -0.10 | 12.02 | 16.73 | 8.66 | 99.53 | 39.00 |
| all | AgenticTrader v0.2 | 15 | 0.42 | 0.44 | 20.93 | 13.77 | 8.31 | 36.92 | 162.87 |
| all | **AgenticTrader v0.3** | 15 | **0.44** | 0.44 | 32.07 | 16.47 | 11.27 | 51.77 | 85.87 |
| all | Buy & hold | 15 | 0.55 | 0.56 | 91.89 | 32.41 | 23.59 | 100.00 | 1.00 |
| all | B&H vol-target | 15 | 0.56 | 0.62 | 46.25 | 20.15 | 14.24 | 75.36 | 654.40 |

**Reading it.**

- **The design-period Sharpe gain did not survive** out of sample: equities improved by
  only 0.03.
- **The return and cost gains did survive:** equity mean return rose from 30% to 47%, and
  trades roughly halved.
- **The drawdown profile held:** about half of buy & hold's.
- **FX stays near zero.** Buy & hold's positive FX mean comes mostly from USDJPY (+67%) and
  USDCAD, while the median pair lost money.

### Q1 2024 window (inside the holdout)

| class | strategy | n | mean Sharpe | median Sharpe | mean CR % | mean MDD % | mean Vol % | mean exposure % | mean trades |
|:--|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| equity | AgenticTrader v0.2 | 10 | 2.22 | 2.95 | 10.12 | 3.06 | 13.04 | 45.24 | 10.10 |
| equity | **AgenticTrader v0.3** | 10 | **2.47** | **3.07** | 11.88 | 4.30 | 15.76 | 66.07 | 3.40 |
| equity | Buy & hold | 10 | 2.67 | 3.07 | 20.58 | 6.60 | 24.76 | 100.00 | 1.00 |
| equity | B&H vol-target | 10 | 2.73 | 3.06 | 12.01 | 5.01 | 17.04 | 75.60 | 39.00 |
| fx | AgenticTrader v0.2 | 5 | -0.43 | -0.25 | -0.07 | 2.20 | 4.08 | 54.26 | 10.00 |
| fx | **AgenticTrader v0.3** | 5 | -0.44 | -0.37 | -0.11 | 2.20 | 4.01 | 53.36 | 5.60 |
| fx | Buy & hold | 5 | 0.34 | -0.66 | 0.70 | 2.80 | 6.29 | 100.00 | 1.00 |
| fx | B&H vol-target | 5 | 0.34 | -0.66 | 0.70 | 2.80 | 6.29 | 100.00 | 1.00 |
| all | AgenticTrader v0.2 | 15 | 1.34 | 2.37 | 6.72 | 2.77 | 10.06 | 48.25 | 10.07 |
| all | **AgenticTrader v0.3** | 15 | **1.50** | **2.48** | 7.88 | 3.60 | 11.84 | 61.83 | 4.13 |
| all | Buy & hold | 15 | 1.89 | 2.90 | 13.95 | 5.33 | 18.61 | 100.00 | 1.00 |
| all | B&H vol-target | 15 | 1.94 | 3.00 | 8.24 | 4.27 | 13.46 | 83.74 | 26.33 |

One quarter of a strong rally is a weak test: the t-statistics are below 3 even at a Sharpe
of 5, and almost every strategy looks good. It is kept as a short reference window; the
multi-year periods above are the evidence.

## Head to head (per instrument, Sharpe)

Number of the 15 instruments on which the agent's Sharpe exceeds each baseline's, with the
median difference:

| period | baseline | v0.2 wins | v0.3 wins | v0.3 median Sharpe diff |
|:--|:--|--:|--:|--:|
| design | Buy & hold | 7 | 10 | +0.11 |
| design | B&H vol-target | 5 | 6 | −0.02 |
| design | SMA(20/50) | 5 | 8 | +0.08 |
| design | MACD | 7 | 11 | +0.31 |
| design | KDJ+RSI | 8 | 10 | +0.36 |
| design | ZMR | 9 | 12 | +0.37 |
| holdout | Buy & hold | 5 | 5 | −0.06 |
| holdout | B&H vol-target | 6 | 4 | −0.10 |
| holdout | SMA(20/50) | 9 | 11 | +0.24 |
| holdout | MACD | 10 | 11 | +0.29 |
| holdout | KDJ+RSI | 7 | 6 | −0.15 |
| holdout | ZMR | 9 | 10 | +0.21 |
| q1_2024 | Buy & hold | 3 | 5 | −0.07 |
| q1_2024 | B&H vol-target | 4 | 3 | −0.28 |

Out of sample the agent reliably beats the trend and mean-reversion baselines (SMA, MACD,
ZMR), loses to buy & hold on most instruments, and loses more often to volatility-targeted
buy & hold.

## How the v0.3 rules were chosen (design-period ablation)

Every candidate change was run alone and in combination on the design period only. The
columns are agent statistics across the 15 instruments. "beats" counts instruments where
the agent's Sharpe exceeds that baseline's.

| variant | mean Sharpe | median Sharpe | equity median SR | FX median SR | mean CR% | mean MDD% | mean Exp% | mean trades | beats B&H | beats vol-target B&H |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| v0.2 (control) | 0.50 | 0.42 | 0.68 | 0.11 | 48.59 | 14.86 | 42.58 | 231.07 | 7 | 5 |
| + 12-1 month time-series momentum | 0.47 | 0.37 | 0.70 | -0.08 | 61.02 | 15.68 | 46.29 | 218.80 | 5 | 3 |
| + trend-filtered reversal | 0.48 | 0.41 | 0.67 | 0.05 | 48.05 | 15.04 | 43.16 | 225.13 | 7 | 5 |
| + abstain without data | 0.51 | 0.39 | 0.71 | 0.13 | 59.94 | 15.92 | 47.51 | 219.47 | 5 | 4 |
| + no-trade band 0.10 | 0.50 | 0.37 | 0.69 | 0.12 | 48.42 | 14.77 | 42.47 | 130.33 | 7 | 5 |
| + intraday stops | 0.47 | 0.60 | 0.72 | -0.04 | 34.82 | 14.31 | 39.01 | 258.93 | 6 | 5 |
| signal changes (momentum + filter + abstain) | 0.51 | 0.43 | 0.73 | -0.08 | 70.49 | 15.84 | 49.80 | 203.20 | 6 | 5 |
| signal changes + band | 0.51 | 0.41 | 0.73 | -0.09 | 68.38 | 15.74 | 49.25 | 105.67 | 6 | 5 |
| all five | 0.50 | 0.48 | 0.77 | -0.11 | 48.69 | 14.88 | 45.08 | 152.73 | 5 | 3 |
| strategic equity weight 0.25 | 0.54 | 0.40 | 0.79 | 0.11 | 64.44 | 15.62 | 47.50 | 235.93 | 6 | 5 |
| strategic equity weight 0.50 | 0.58 | 0.50 | 0.87 | 0.11 | 78.30 | 15.41 | 50.89 | 231.20 | 6 | 5 |
| strategic equity weight 1.00 | 0.66 | 0.53 | 1.06 | 0.11 | 108.43 | 15.64 | 57.36 | 231.80 | 10 | 6 |
| strategic 0.50 + band | 0.58 | 0.53 | 0.86 | 0.12 | 76.92 | 15.43 | 50.26 | 116.33 | 7 | 5 |
| strategic 0.50 + signal changes + band | 0.58 | 0.49 | 0.93 | -0.09 | 90.78 | 16.12 | 54.46 | 107.60 | 7 | 5 |
| strategic 0.50 + abstain + band | 0.56 | 0.45 | 0.84 | 0.15 | 73.78 | 16.14 | 51.51 | 111.80 | 5 | 4 |
| **frozen v0.3: strategic 1.00 + band** | **0.65** | **0.55** | **1.05** | **0.12** | 105.11 | 15.71 | 56.69 | **106.40** | **10** | **6** |

**Decisions, and why:**

- **Time-series momentum, trend-filtered reversal and abstention: off.** None moved mean
  Sharpe outside ±0.02 of the control, which is within noise for 15 instruments. Momentum
  hurt FX. The switches stay in `config["rules"]` for research.
- **Intraday stops: off by default.** They cut mean return by about 30% at similar Sharpe.
  The engine supports them (`backtest.use_stops`) for users whose mandate requires stops.
- **No-trade band 0.10: on.** It gave the same Sharpe with **44% fewer trades**, which means
  lower costs in live trading and less churn from noisy LLM targets.
- **Strategic equity weight 1.0: on.** The effect is monotonic in the weight (0.25 → 0.5 →
  1.0), matches a strong prior (the equity risk premium), and does not change FX, where the
  neutral weight stays 0. It is a **benchmark choice, not a forecasting improvement**:
  equities are held at the benchmark weight unless the firm is convinced otherwise, instead
  of sitting flat whenever the view is weak.

## The v0.4 alpha analyst (design-period check)

v0.4 adds an alpha library (nine point-in-time signals with IC diagnostics) and an
`AlphaAnalyst` that reads the latest signals as one more analyst. Before making it a default
it was measured the same way as every other rule change, on the design period only:

| variant | mean Sharpe | median Sharpe | equity median SR | FX median SR | mean CR% | mean MDD% | mean Exp% | mean trades | beats B&H | beats vol-target B&H |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| v0.3 default (technical, sentiment, macro/fundamentals, news) | 0.65 | 0.55 | 1.05 | 0.12 | 105.22 | 15.72 | 56.69 | 106.47 | 10 | 6 |
| + alpha analyst (IC-weighted, all signals) | 0.60 | 0.60 | 1.04 | -0.12 | 107.56 | 16.73 | 55.90 | 110.87 | 9 | 5 |
| alpha analyst replaces the technical analyst (IC-weighted, all signals) | 0.63 | 0.68 | 1.00 | 0.17 | 97.19 | 17.27 | 52.81 | 141.80 | 8 | 3 |

**First attempt (v0.4.0): off by default.** Mean Sharpe fell by 0.05 and the median rose by
0.05, with one fewer instrument beating each baseline: noise on 15 instruments. Weighting
every alpha by `max(0, IC)` let many near-zero, statistically insignificant signals add
turnover without predictive value.

**Second attempt: restrict the combination to significant alphas only.** `AlphaAnalyst` was
changed to weight only alphas whose IC clears `|t(IC)| >= 2` with at least 30 observations,
and to abstain when none qualify (previously it always produced a view). Measured the same
way:

| variant | mean Sharpe | median Sharpe | equity median SR | FX median SR | mean CR% | mean MDD% | mean Exp% | mean trades | beats B&H | beats vol-target B&H |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| v0.3 default | 0.65 | 0.55 | 1.05 | 0.12 | 105.22 | 15.72 | 56.69 | 106.47 | 10 | 6 |
| + alpha analyst (significance-gated) | 0.58 | 0.57 | 0.96 | -0.09 | 98.96 | 17.04 | 56.44 | 124.40 | 7 | 4 |
| alpha analyst replaces the technical analyst (significance-gated) | 0.61 | **0.70** | 0.94 | -0.07 | 103.12 | 17.94 | 53.52 | **90.73** | **10** | **6** |

The significance-gated version was still not a clean fix on its own: "+ alpha analyst" got
*worse* (mean Sharpe and beat-counts both fell, and trades rose rather than fell). "Alpha
replaces technical" tied the default's head-to-head win counts with fewer trades and a
higher median Sharpe, but its mean Sharpe was still below default.

**Third attempt: two real bugs found on review, independent of the Sharpe question.**

1. *Harness/direct inconsistency.* `AlphaAnalyst` computed its own significance-gated
   combination when invoked directly, but under the agentic harness (where the canonical
   plan runs `quant.alpha` before the analyst) it returned that tool's raw output, which
   combines *every* alpha equally weighted -- silently bypassing the significance gate on
   that path. Both paths now go through one shared function, `alpha.significant_alpha_signal`.
2. *Window mismatch.* The direct path reused `state.history`, the desk's general ~400-day
   window sized for the other analysts. A 273-day signal like `tsmom_12_1` barely produces
   its first non-NaN value in that window, so it (and other longer-horizon alphas) almost
   never had enough points to clear the significance bar there, while the harness path's
   `quant.alpha` tool call used a 900-day default -- a second silent inconsistency, and a
   window too short for reliable IC estimation either way. The analyst now always fetches
   its own 900-day window.

Both are correctness fixes on their own merits (the same analyst should not behave
differently depending on how it is invoked). Re-measured on the design period with both
fixed:

| variant | mean Sharpe | median Sharpe | equity median SR | FX median SR | mean CR% | mean MDD% | mean Exp% | mean trades | beats B&H | beats vol-target B&H |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| v0.3 default | 0.65 | 0.55 | 1.05 | 0.12 | 105.22 | 15.72 | 56.85 | 106.87 | 10 | 6 |
| + alpha analyst (significance-gated, 900-day window) | 0.65 | **0.62** | 1.00 | **0.17** | 101.38 | 16.84 | 52.29 | 115.67 | 8 | 6 |
| alpha analyst replaces the technical analyst (900-day window) | 0.57 | 0.59 | 0.82 | -0.03 | 59.47 | 16.12 | 39.42 | 147.73 | 5 | 5 |

**Decision: still off by default, but the picture changed.** With both bugs fixed, "+ alpha
analyst" is close to Sharpe-neutral (0.647 vs 0.654, a 0.007 gap that is pure noise on 15
instruments), with a *higher* median Sharpe and a *better* FX median than the default, at the
cost of two fewer instruments beating buy & hold and about 8% more trades. "Alpha replaces
technical" is now clearly worse than before (mean Sharpe 0.57, down from 0.63 with the old
window) -- dropping the desk's tuned technical analyst entirely is a bad trade regardless of
window length. Even though "+ alpha analyst" now looks closer to acceptable than either
earlier attempt, this is the **third** combination-logic variant measured on the same design
period; treating a closer-to-parity result as a green light after repeated tuning attempts
would be exactly the kind of selection bias this evaluation's own methodology warns against
(see [selection statistics](#selection-statistics-for-the-chosen-rules)). The analyst stays
off by default. It remains available (`config["analysts"] = [..., "alpha"]`, or `--analysts`)
and the `quant.alpha` tool still runs in every harness task, so the signals and their
information coefficients are in the evidence for anyone who wants to read them.

## Selection statistics for the chosen rules

Choosing the best of 16 variants on the same data inflates the winner's Sharpe ratio. v0.4
reports the standard corrections (`stats.selection_report`) for the frozen v0.3 rule set,
using the 15-sleeve portfolio's daily returns on the design period and the 16 variants'
mean Sharpe ratios as the trials:

| Statistic | Value |
|---|---|
| Observations | 1,565 daily returns |
| Annual Sharpe (t-stat) | 1.48 (3.69) |
| Skew, kurtosis | −0.63, 7.2 |
| Bootstrap 95% interval for the Sharpe (block 10) | [0.74, 2.27] |
| Probabilistic Sharpe vs 0 | 1.00 |
| Trials | 16 |
| Expected maximum Sharpe of 16 null trials | 0.11 |
| Deflated Sharpe probability | 1.00 |
| Minimum track record to beat that benchmark at 95% | 389 days |

**How to read it, and why it is not a triumph.**

- The trials' dispersion is that of per-instrument *mean* Sharpes (0.47 to 0.66), which is
  much narrower than the dispersion of the portfolio Sharpes would be, so the expected
  maximum (0.11) understates the selection benchmark. The probabilities of 1.00 are
  therefore an upper bound.
- The returns are from the **design period**, on which the rules were chosen; the
  correction accounts for the number of trials, not for the fact that the same data judged
  them. The **holdout** is the real check, and there the portfolio Sharpe was 1.14 against
  1.24 for volatility-targeted buy & hold.
- The bootstrap interval is wide: six years of daily returns cannot separate a Sharpe of
  1.5 from one of 0.8 with much confidence.

The same report is available for any returns series with `agentic-trader stats returns.csv
--trial-sharpes ...` (cookbook recipe 56).

## The extended universe (v0.5): out of sample on every period

Every rule choice through v0.4 was made on the 15 core instruments, and by v0.4 the holdout
itself had been reported and compared against, so it no longer counts as unseen. v0.5 adds
45 instruments that no choice ever consulted, which makes them out of sample on *every*
period, including the design period. The rules are the frozen v0.3 defaults; nothing was
tuned for the new names.

### Headline results, extended universe (45 instruments)

| period | class | strategy | n | mean Sharpe | median Sharpe | mean CR % | mean MDD % | mean exposure % | mean trades |
|:--|:--|:--|--:|--:|--:|--:|--:|--:|--:|
| design | equity + ETF | **AgenticTrader** | 35 | 0.70 | 0.66 | 62.95 | 20.10 | 64.32 | 83.77 |
| design | equity + ETF | Buy & hold | 35 | 0.70 | 0.70 | 133.13 | 37.37 | 100.00 | 1.00 |
| design | equity + ETF | B&H vol-target | 35 | 0.77 | 0.77 | 91.70 | 22.52 | 81.82 | 838.91 |
| design | fx | **AgenticTrader** | 10 | -0.24 | -0.25 | -6.84 | 14.61 | 48.63 | 164.60 |
| design | fx | Buy & hold | 10 | 0.05 | 0.04 | 0.45 | 18.11 | 100.00 | 1.00 |
| design | fx | B&H vol-target | 10 | 0.05 | 0.02 | 0.38 | 17.67 | 99.10 | 76.30 |
| design | all | **AgenticTrader** | 45 | **0.49** | **0.56** | 47.44 | 18.88 | 60.83 | 101.73 |
| design | all | Buy & hold | 45 | 0.56 | 0.60 | 103.65 | 33.09 | 100.00 | 1.00 |
| design | all | B&H vol-target | 45 | 0.61 | 0.64 | 71.41 | 21.44 | 85.66 | 669.44 |
| holdout | equity + ETF | **AgenticTrader** | 35 | 0.45 | 0.45 | 30.94 | 19.43 | 59.40 | 77.17 |
| holdout | equity + ETF | Buy & hold | 35 | 0.53 | 0.58 | 74.53 | 30.79 | 100.00 | 1.00 |
| holdout | equity + ETF | B&H vol-target | 35 | 0.49 | 0.50 | 41.96 | 23.17 | 77.75 | 769.86 |
| holdout | fx | **AgenticTrader** | 10 | 0.12 | 0.17 | 4.54 | 11.48 | 57.01 | 104.20 |
| holdout | fx | Buy & hold | 10 | 0.39 | 0.30 | 19.53 | 14.44 | 100.00 | 1.00 |
| holdout | fx | B&H vol-target | 10 | 0.39 | 0.32 | 19.32 | 13.84 | 99.43 | 40.50 |
| holdout | all | **AgenticTrader** | 45 | **0.37** | **0.42** | 25.07 | 17.66 | 58.87 | 83.18 |
| holdout | all | Buy & hold | 45 | 0.50 | 0.57 | 62.31 | 27.16 | 100.00 | 1.00 |
| holdout | all | B&H vol-target | 45 | 0.47 | 0.50 | 36.93 | 21.10 | 82.57 | 607.78 |
| q1_2024 | all | **AgenticTrader** | 45 | 1.64 | 2.36 | 4.57 | 3.59 | 69.64 | 3.89 |
| q1_2024 | all | Buy & hold | 45 | 2.11 | 2.47 | 6.77 | 4.86 | 100.00 | 1.00 |
| q1_2024 | all | B&H vol-target | 45 | 2.11 | 2.34 | 6.15 | 4.13 | 90.83 | 24.04 |
| reserve | all | **AgenticTrader** | 45 | -0.07 | -0.01 | 0.81 | 4.74 | 58.05 | 4.62 |
| reserve | all | Buy & hold | 45 | 0.01 | 0.07 | 1.66 | 8.13 | 100.00 | 1.00 |
| reserve | all | B&H vol-target | 45 | 0.02 | 0.11 | 0.80 | 5.75 | 79.01 | 35.07 |

The 9 macro ETFs alone (rates, credit, commodities, real estate): holdout mean Sharpe 0.33
against 0.34 for buy & hold and 0.34 vol-targeted, with a mean drawdown of 19.2% against
30.2%; design 0.54 against 0.54 and 0.58. The desk treats them as equities (strategic weight
1.0), and they behave like the equity sleeves: parity on Sharpe, lower drawdown.

**Head to head, extended universe** (instruments on which the agent's Sharpe exceeds the
baseline's, of 45, with the median difference):

| period | Buy & hold | B&H vol-target | SMA(20/50) | MACD | KDJ+RSI | ZMR |
|:--|--:|--:|--:|--:|--:|--:|
| design | 18 (−0.02) | 10 (−0.10) | 27 (+0.06) | 28 (+0.05) | 31 (+0.19) | 36 (+0.33) |
| holdout | 14 (−0.13) | 14 (−0.07) | 36 (+0.23) | 23 (+0.02) | 24 (+0.03) | 30 (+0.17) |
| q1_2024 | 9 (−0.09) | 13 (−0.09) | 27 (+0.16) | 35 (+1.09) | 23 (+0.15) | 27 (+0.63) |
| reserve | 16 (−0.08) | 16 (−0.14) | 29 (+0.20) | 30 (+0.56) | 14 (−0.37) | 18 (−0.51) |

**Reading it.**

- **The core-universe story survives, and it does not improve.** On names the rules never
  saw, the desk again does not beat buy & hold on Sharpe (14 of 45 on the holdout, median
  difference −0.13) and again takes about two thirds of the drawdown (17.7% against 27.2%;
  lower on 40 of 45). The gap to buy & hold is a little wider than on the core universe
  (0.13 against 0.11 of Sharpe), which is what one expects when a rule set moves from the
  names it was tuned on to names it was not.
- **FX crosses are the weak spot.** On the design period the desk *loses* on the 10 crosses
  (−0.24 mean Sharpe against +0.05) and on the holdout it trails (0.12 against 0.39). The
  strategic FX weight is 0, so every FX return comes from directional calls, and on crosses
  those calls are worse than on the dollar pairs the rules were chosen on.
- **The reserve period is three months and says little**, as expected: every strategy is
  near zero on the extended universe and the desk trails plain buy & hold on the core one
  (0.72 against 1.01). It is reported because it will be the primary holdout as it grows.
- **Q1 2024 stays a weak test**: the extended-universe Sharpe of every strategy is above 1.6
  with drawdowns under 5%.

### Extended universe, holdout per instrument

| symbol | group | agent Sharpe | B&H Sharpe | vol-target B&H Sharpe | agent CR % | B&H CR % | agent MDD % | B&H MDD % | agent trades |
|:--|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| UNH | equity | -0.27 | 0.10 | -0.08 | -20.60 | -10.29 | 33.90 | 61.39 | 94 |
| V | equity | 0.27 | 0.58 | 0.49 | 12.63 | 60.31 | 16.60 | 24.14 | 88 |
| MA | equity | 0.09 | 0.46 | 0.26 | 1.31 | 42.17 | 21.56 | 28.25 | 85 |
| PG | equity | 0.02 | 0.10 | 0.10 | -1.85 | 0.95 | 16.35 | 23.77 | 94 |
| HD | equity | 0.10 | 0.09 | 0.02 | 2.21 | -3.17 | 20.79 | 34.20 | 89 |
| COST | equity | 0.66 | 0.65 | 0.85 | 44.31 | 73.59 | 16.57 | 31.40 | 82 |
| WMT | equity | 1.03 | 1.02 | 1.12 | 89.21 | 148.41 | 14.92 | 25.74 | 73 |
| KO | equity | 0.53 | 0.69 | 0.58 | 27.08 | 56.46 | 12.15 | 17.27 | 81 |
| PEP | equity | -0.06 | -0.02 | -0.03 | -6.47 | -9.55 | 22.87 | 30.32 | 92 |
| CVX | equity | 0.28 | 0.58 | 0.58 | 14.45 | 66.41 | 26.87 | 24.95 | 89 |
| LLY | equity | 1.02 | 1.20 | 1.25 | 89.83 | 359.65 | 23.70 | 34.48 | 81 |
| ABBV | equity | 0.70 | 0.86 | 0.89 | 53.88 | 118.98 | 18.61 | 21.92 | 84 |
| MRK | equity | 0.79 | 0.74 | 0.60 | 52.84 | 91.79 | 21.43 | 43.44 | 91 |
| BAC | equity | 0.33 | 0.40 | 0.32 | 18.05 | 38.06 | 27.81 | 46.64 | 94 |
| GS | equity | 0.81 | 0.97 | 0.84 | 64.37 | 185.81 | 24.88 | 30.90 | 86 |
| CAT | equity | 1.51 | 1.37 | 1.39 | 185.69 | 456.43 | 15.80 | 34.05 | 78 |
| BA | equity | 0.20 | 0.21 | 0.04 | 8.30 | 4.12 | 31.90 | 48.73 | 64 |
| BRK-B | equity | 0.56 | 0.74 | 0.68 | 31.23 | 66.33 | 17.51 | 26.58 | 67 |
| QQQ | equity | 0.90 | 0.72 | 0.88 | 58.10 | 88.42 | 14.68 | 34.84 | 75 |
| IWM | equity | 0.45 | 0.45 | 0.35 | 24.57 | 41.02 | 17.45 | 27.50 | 82 |
| XLF | equity | 0.49 | 0.55 | 0.49 | 24.52 | 46.53 | 17.39 | 25.81 | 70 |
| XLE | equity | 0.48 | 0.80 | 0.71 | 30.31 | 117.15 | 16.24 | 26.04 | 82 |
| XLV | equity | -0.04 | 0.37 | 0.32 | -3.78 | 22.46 | 16.89 | 17.11 | 74 |
| XLU | equity | 0.43 | 0.57 | 0.43 | 22.17 | 46.43 | 16.24 | 25.26 | 77 |
| EEM | equity | 0.75 | 0.59 | 0.50 | 44.30 | 54.07 | 12.48 | 32.71 | 70 |
| EFA | equity | 0.64 | 0.62 | 0.46 | 31.56 | 50.59 | 12.19 | 28.74 | 63 |
| TLT | macro ETF | -0.55 | -0.42 | -0.48 | -21.55 | -29.74 | 22.74 | 39.86 | 85 |
| IEF | macro ETF | -0.03 | -0.10 | -0.10 | -1.29 | -4.79 | 10.59 | 18.79 | 42 |
| LQD | macro ETF | 0.41 | 0.03 | 0.04 | 11.01 | -0.39 | 6.51 | 22.73 | 49 |
| HYG | macro ETF | 0.77 | 0.52 | 0.52 | 18.38 | 18.41 | 8.04 | 15.54 | 23 |
| GLD | macro ETF | 1.16 | 1.02 | 1.18 | 87.69 | 118.80 | 14.93 | 26.21 | 70 |
| SLV | macro ETF | 0.77 | 0.74 | 0.84 | 71.86 | 152.40 | 20.02 | 50.97 | 74 |
| USO | macro ETF | 0.28 | 0.59 | 0.59 | 15.76 | 94.09 | 35.51 | 36.23 | 87 |
| DBC | macro ETF | 0.21 | 0.55 | 0.52 | 8.25 | 46.85 | 34.44 | 27.34 | 82 |
| VNQ | macro ETF | -0.06 | 0.10 | -0.03 | -5.54 | -0.06 | 19.54 | 33.97 | 84 |
| NZDUSD | fx | -0.39 | -0.34 | -0.41 | -9.83 | -17.16 | 21.82 | 20.77 | 149 |
| USDCHF | fx | 0.30 | -0.06 | -0.07 | 7.12 | -3.62 | 7.78 | 19.28 | 109 |
| EURGBP | fx | -0.48 | -0.06 | 0.14 | -8.00 | -4.25 | 10.48 | 18.41 | 93 |
| EURJPY | fx | 0.62 | 1.10 | 1.11 | 16.58 | 55.36 | 8.77 | 10.23 | 86 |
| GBPJPY | fx | 0.63 | 1.14 | 1.12 | 18.34 | 62.21 | 9.55 | 11.28 | 89 |
| AUDJPY | fx | 0.76 | 0.89 | 0.83 | 23.14 | 53.30 | 11.77 | 17.94 | 102 |
| EURCHF | fx | -0.41 | -0.26 | -0.26 | -7.00 | -7.09 | 9.30 | 11.26 | 108 |
| AUDNZD | fx | 0.04 | 0.51 | 0.51 | 0.35 | 11.12 | 9.67 | 8.81 | 98 |
| CADJPY | fx | 0.42 | 0.86 | 0.86 | 11.29 | 44.07 | 9.40 | 12.35 | 99 |
| EURAUD | fx | -0.31 | 0.08 | 0.10 | -6.62 | 1.34 | 16.24 | 14.05 | 109 |

Lower drawdown than buy & hold on 40 of 45; higher Sharpe on 14 of 45 (CAT, WMT, COST, MRK,
QQQ, EEM, EFA, HD, IWM-tie, LQD, HYG, GLD, SLV, USDCHF). The five where the drawdown is
*not* lower are the two low-volatility FX crosses (NZDUSD, AUDNZD), EURAUD, CVX and DBC.

## Execution costs: the impact sweep (v0.5)

The backtests above fill at the close with a fixed bps cost, which assumes an account small
enough not to move prices. v0.5 charges the execution simulator's square-root market impact
inside the backtester (`costs.impact_coeff`, see [the architecture](../architecture/overview.md)):
a trade of `|dw|` costs `|dw|^1.5 · K_t` of equity, `K_t = coeff · daily_vol_t ·
sqrt(capital / (price_t · ADV_t))`, applied to the desk and to every baseline. The core
universe, textbook coefficient 1.0, three account sizes; "impact %" is the cumulative cost
paid over the period as a percentage of equity, averaged over the 15 instruments.

| strategy | period | Sharpe (off) | $100k | $10M | $1B | impact % $100k | $10M | $1B |
|:--|:--|--:|--:|--:|--:|--:|--:|--:|
| **AgenticTrader** | design | 0.65 | 0.65 | 0.64 | **0.56** | 0.08 | 0.77 | 7.70 |
| B&H vol-target | design | 0.67 | 0.67 | 0.67 | 0.62 | 0.06 | 0.57 | 5.74 |
| Buy & hold | design | 0.62 | 0.62 | 0.62 | 0.62 | 0.01 | 0.10 | 0.97 |
| SMA(20/50) | design | 0.59 | 0.58 | 0.57 | 0.41 | 0.21 | 2.12 | 21.16 |
| MACD | design | 0.42 | 0.41 | 0.35 | **-0.24** | 0.75 | 7.54 | 75.35 |
| **AgenticTrader** | holdout | 0.44 | 0.44 | 0.43 | **0.35** | 0.05 | 0.52 | 5.20 |
| B&H vol-target | holdout | 0.56 | 0.56 | 0.55 | 0.52 | 0.03 | 0.33 | 3.25 |
| Buy & hold | holdout | 0.55 | 0.55 | 0.55 | 0.54 | 0.00 | 0.05 | 0.48 |
| SMA(20/50) | holdout | 0.26 | 0.26 | 0.24 | 0.12 | 0.13 | 1.29 | 12.93 |
| MACD | holdout | 0.21 | 0.20 | 0.15 | **-0.31** | 0.47 | 4.72 | 47.23 |

**Reading it.**

- **Impact is invisible at $100k and small at $10M** for every strategy; the published
  tables (impact off) describe accounts up to that size well.
- **At $1B it is material and it reorders the baselines, not the desk's verdict.** The desk
  pays 7.7% of equity over six years and loses 0.09 of Sharpe; it still trails the
  vol-targeted control (0.56 against 0.62) and still beats the rule-based baselines, by
  more than before.
- **Many small trades are cheaper than a few large ones.** The daily vol-target baseline
  makes ~1,100 trades and pays *less* impact than the desk's ~106, because the cost of a trade
  grows with `|dw|^1.5`: a hundred 1% adjustments cost a tenth of one 100% jump. MACD, which
  flips whole positions, loses three quarters of its equity to impact at $1B.
- Buy & hold is not free either: its single entry trade at $1B costs about 1%.

FX sleeves get no impact in these runs (no exchange volume; set `costs.fx_adv_notional` to
model it), so the FX rows are unchanged across the columns and the averages above are
driven by the equities.

## The next rule change: what counts as unseen

By v0.4 the 2022–2026 holdout had been run, reported and compared against, so any rule
that "improves the holdout" from now on is being fitted to it. v0.5 fixes the protocol for
the next change before there is one:

1. **Choose** on the core universe's design period only (`evaluate --universe core
   --periods design`), exactly as before, and publish the full ablation.
2. **Judge** on data no choice has touched: the extended universe over the design and
   holdout periods (`--universe extended --periods design,holdout`) and the reserve period on
   both universes (`--periods reserve`). Report all of it, including the parts that do not
   flatter the change.
3. **Do not touch the reserve period for a choice.** It is small now and grows every month;
   the extended universe carries the weight until it is long enough.
4. If the change alters what the desk trades (a new asset class, a new analyst input),
   the alpha-analyst rule applies: measure it, and treat a result within about 0.1 of Sharpe
   on 15 instruments (about 0.06 on 45) as noise.

## Holdout per instrument (core universe)

| symbol | v0.2 Sharpe | v0.3 Sharpe | B&H Sharpe | vol-target B&H Sharpe | v0.3 CR % | B&H CR % | v0.3 MDD % | B&H MDD % | v0.3 trades |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| AAPL | 0.14 | 0.44 | 0.53 | 0.61 | 24.95 | 62.58 | 20.84 | 33.36 | 70 |
| NVDA | 0.84 | 1.14 | 1.07 | 1.24 | 126.84 | 566.25 | 18.55 | 62.71 | 51 |
| MSFT | 0.02 | 0.18 | 0.26 | 0.30 | 7.17 | 15.66 | 19.26 | 35.59 | 84 |
| META | 1.05 | 0.77 | 0.48 | 0.63 | 65.19 | 67.82 | 19.12 | 73.74 | 63 |
| GOOGL | 0.77 | 0.78 | 0.79 | 0.86 | 62.71 | 148.61 | 20.04 | 43.63 | 71 |
| AMZN | 0.44 | 0.35 | 0.39 | 0.38 | 20.38 | 39.84 | 18.11 | 51.99 | 73 |
| JPM | 0.86 | 0.80 | 0.86 | 0.81 | 60.20 | 126.97 | 17.27 | 37.93 | 80 |
| XOM | 0.23 | 0.59 | 0.91 | 0.83 | 40.71 | 151.32 | 16.91 | 20.51 | 79 |
| JNJ | 0.60 | 0.38 | 0.75 | 0.62 | 18.07 | 68.27 | 27.76 | 18.41 | 96 |
| SPY | 1.05 | 0.89 | 0.73 | 0.78 | 47.50 | 66.11 | 12.80 | 24.51 | 70 |
| EURUSD | 0.02 | 0.02 | -0.16 | -0.16 | -0.18 | -6.81 | 11.61 | 17.05 | 100 |
| USDJPY | 0.65 | 0.63 | 1.16 | 1.18 | 18.87 | 66.73 | 10.21 | 13.96 | 97 |
| GBPUSD | -0.34 | -0.35 | -0.03 | -0.10 | -8.09 | -2.72 | 15.79 | 21.82 | 128 |
| AUDUSD | -0.01 | -0.06 | -0.12 | -0.20 | -2.48 | -8.07 | 12.60 | 23.67 | 126 |
| USDCAD | -0.03 | -0.02 | 0.56 | 0.56 | -0.79 | 15.72 | 6.12 | 7.31 | 100 |

Highlights:

- **Drawdown:** the agent's maximum drawdown is below buy & hold's on 14 of 15 instruments.
  The exception is JNJ, a low-volatility stock where the agent churned (96 trades) through
  a choppy market.
- **Sharpe:** the agent beats buy & hold on META, NVDA, SPY, EURUSD and AUDUSD.

## Q1 2024 per instrument

| symbol | v0.2 Sharpe | v0.3 Sharpe | B&H Sharpe | vol-target B&H Sharpe | v0.3 CR % | B&H CR % | v0.3 MDD % | B&H MDD % | v0.3 trades |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| AAPL | -3.84 | -1.88 | -1.55 | -1.58 | -3.63 | -7.53 | 6.73 | 13.30 | 9 |
| NVDA | 5.42 | 5.50 | 5.46 | 5.78 | 41.08 | 87.56 | 5.08 | 8.70 | 2 |
| MSFT | 2.51 | 3.07 | 2.90 | 3.08 | 11.65 | 13.63 | 3.22 | 4.21 | 2 |
| META | 3.06 | 2.93 | 3.10 | 3.04 | 22.44 | 40.34 | 3.34 | 5.58 | 3 |
| GOOGL | 1.07 | 0.88 | 1.46 | 1.35 | 3.46 | 9.21 | 9.88 | 14.40 | 5 |
| AMZN | 2.84 | 3.07 | 3.04 | 3.00 | 13.70 | 20.29 | 2.76 | 4.22 | 3 |
| JPM | 4.96 | 4.98 | 4.98 | 4.98 | 14.84 | 17.09 | 2.63 | 3.01 | 1 |
| XOM | 4.22 | 3.27 | 3.34 | 3.71 | 8.11 | 14.59 | 3.26 | 6.22 | 4 |
| JNJ | -1.93 | -1.17 | -0.09 | -0.09 | -2.47 | -0.38 | 4.57 | 4.62 | 4 |
| SPY | 3.87 | 4.06 | 4.06 | 4.06 | 9.57 | 10.99 | 1.49 | 1.71 | 1 |
| EURUSD | -0.24 | -0.28 | -1.88 | -1.88 | -0.26 | -2.36 | 2.01 | 3.15 | 5 |
| USDJPY | 2.37 | 2.48 | 4.51 | 4.51 | 3.21 | 8.57 | 1.93 | 2.44 | 4 |
| GBPUSD | -2.20 | -2.22 | -0.66 | -0.66 | -1.87 | -0.92 | 2.32 | 2.01 | 5 |
| AUDUSD | -0.25 | -0.37 | -2.45 | -2.45 | -0.45 | -4.47 | 2.64 | 5.36 | 5 |
| USDCAD | -1.81 | -1.81 | 2.18 | 2.18 | -1.16 | 2.67 | 2.11 | 1.05 | 9 |

## Portfolio view (15 equal-capital sleeves)

`run_portfolio_backtest` gives each instrument 1/15 of the capital, runs every sleeve with
its own costs, carry and position, and averages the daily returns. A sleeve with no bar on a
date contributes 0 that day.

| Portfolio | Design Sharpe (t) | Design CR % | Design MDD % | Holdout Sharpe (t) | Holdout CR % | Holdout MDD % | Holdout exposure % |
|:--|--:|--:|--:|--:|--:|--:|--:|
| **AgenticTrader v0.3** | **1.50** (3.69) | 78.26 | 8.05 | **1.14** (2.41) | 31.48 | 6.78 | 50.54 |
| AgenticTrader v0.2 | 1.33 (3.27) | 38.64 | 5.86 | 1.21 (2.55) | 20.45 | 3.59 | 36.23 |
| Buy & hold | 1.32 (3.24) | 192.18 | 22.74 | 1.06 (2.24) | 86.57 | 20.78 | 97.57 |
| B&H vol-target | 1.49 (3.65) | 92.85 | 9.75 | 1.24 (2.63) | 46.29 | 9.84 | 73.82 |
| SMA(20/50) | 1.42 (3.49) | 108.57 | 9.53 | 0.84 (1.79) | 34.61 | 13.28 | 72.11 |
| MACD | 1.15 (2.83) | 64.81 | 15.37 | 0.54 (1.14) | 20.15 | 16.34 | 65.70 |
| KDJ+RSI | 0.84 (2.06) | 60.49 | 18.18 | 0.81 (1.73) | 39.02 | 13.21 | 59.12 |
| ZMR | 0.59 (1.44) | 37.76 | 19.30 | 0.53 (1.13) | 22.16 | 10.33 | 48.36 |

Diversification across 15 instruments lifts every strategy's Sharpe. The agent portfolio
beats plain buy & hold on Sharpe in both periods and has a third of its drawdown. It
matches volatility-targeted buy & hold on the design period (1.50 vs 1.49) and trails it on
the holdout (1.14 vs 1.24).

**Trade-off from v0.3.** On the holdout, v0.3 has a *lower* portfolio Sharpe than v0.2
(1.14 vs 1.21) but **54% more return** (31.5% vs 20.5%). v0.2 was mostly flat, and its low
volatility flattered its ratio. Which is preferable depends on the mandate.

v0.4 adds `--weighting` (inverse-vol, risk parity, minimum variance, mean-variance, all from
trailing returns) to the portfolio backtest. Those schemes are applied identically to every
strategy, so they change the level of every row, not the ranking; the equal-weight table
above remains the reference.

## Engineering measurements

| Measurement | Value |
|---|---|
| One `propagate()`, offline, C++ backend | ≈8 ms (AAPL), mean of 20 runs after warm-up |
| One harness task (`AgentHarness.run`), offline | ≈31 ms: 12 plan steps, 2 parallel tool calls, 4 analysts, debate, trader, risk, critic (6 checks), validation, audited report; 21 evidence records, 7 findings, 18 spans |
| Q1 walk-forward backtest (NVDA, synthetic): 63 bars, 13 agent decisions + 6 baselines | 0.07 s |
| Full evaluation: 15 instruments × 3 periods, real prices, v0.3 | 27 s (after the first data download) |
| Real-data backtest speed-up in v0.3 | ≈8× (2.0 s → 0.24 s per quarter): Yahoo news is no longer requested for dates it cannot serve |
| LLM calls per decision at default rounds | 14 = 4 quick-tier + 10 deep-tier. An analyst with no data makes no call, so it is 13 when news is missing |
| Full v0.5 evaluation: 60 instruments × 4 periods, real prices, impact off | 115 s (after the first data download); each 15-instrument impact run ≈ 14 s |
| Tests | 240 pytest tests (fuzz 21 property tests, v0.5 features 18, agentic 30, adversarial 15, services 7 including a real MCP stdio round trip, quant research 19, LLM evaluation 11, plus the v0.3 suites) + 14 C++ test groups (42 checks) |

## Limitations

- **No LLM results.** The whole point of the framework, whether LLM reasoning adds value
  over the rule-based firm, is unmeasured. The harness for it (usage and cost accounting,
  anonymised prompts, parallel workers, the Q1 2024 window) is in place.
- **Half the analyst team is idle historically.** Without point-in-time news, social or
  fundamentals data, the historical results test the technical, sentiment-proxy and macro
  analysts only.
- **FRED serves the latest vintage.** Policy rates are not revised, but the few CPI inputs
  can differ slightly from what was first published. ALFRED vintages would remove this.
- **Survivorship.** The equity universe is today's large caps, so it is biased towards
  names that did well. Buy & hold benefits from this at least as much as the agent.
- **The core universe is a small sample.** Differences in mean Sharpe below about 0.1
  between variants on 15 instruments (about 0.06 on the 45 extended ones) should be read as
  noise; the alpha-analyst result is an example.
- **The holdout has been seen.** Every choice was made on the design period, but the
  2022–2026 numbers have been reported and compared against; the extended universe and the
  reserve period are the unseen data from here (see [the next rule change](#the-next-rule-change-what-counts-as-unseen)).
- **Execution model.** Close-to-close fills, with costs as a fixed bps per unit of turnover
  and, optionally, square-root market impact scaled by account size (the impact sweep
  above). Stops fill at the level, or at the open on a gap. FX impact needs a configured
  notional ADV. There is no spread widening in stress and no venue or queue model.
- **Macro vintages.** FRED serves the latest revision. `fred_vintages` reads revised series
  (CPI) from the ALFRED vintage current at each date, sampled monthly, so inflation enters as
  first published; it is off in the published runs, which therefore carry a small revision
  leak in the FX inflation inputs (policy rates are never revised).

## Reproducing

```bash
pip install -e ".[all]"

# the core protocol on real prices (design, holdout, q1_2024), the 15 core instruments
agentic-trader evaluate --data yahoo --universe core --periods design,holdout,q1_2024 --out results/eval_v03.json

# the same with the v0.2 rule set, for the before/after comparison
agentic-trader evaluate --data yahoo --universe core --periods design,holdout,q1_2024 --rules v02 --out results/eval_v02.json

# v0.5: all 60 instruments on every period, and the impact sweep on the core universe
agentic-trader evaluate --data yahoo --universe all --periods design,holdout,q1_2024,reserve --out results/eval_v05_all.json
agentic-trader evaluate --data yahoo --universe core --periods design,holdout --impact 1.0 --capital 1e9 --out results/eval_v05_impact_1e9.json

# the alpha-analyst check (design period only)
agentic-trader evaluate --data yahoo --periods design --analysts technical,sentiment,macro,fundamentals,news,alpha

# the portfolio view
agentic-trader portfolio AAPL,NVDA,MSFT,META,GOOGL,AMZN,JPM,XOM,JNJ,SPY,EURUSD,USDJPY,GBPUSD,AUDUSD,USDCAD \
    --data yahoo --start 2022-01-03 --end 2026-06-30 --out results/portfolio_holdout.csv

# selection statistics for a returns series against the variants tried
agentic-trader stats results/portfolio_design.csv --column AgenticTrader \
    --trial-sharpes 0.496,0.465,0.483,0.512,0.496,0.471,0.509,0.511,0.497,0.535,0.577,0.655,0.579,0.583,0.652,0.561
```

The ablation variants are ordinary config overrides (see the tables above). Cookbook recipe
28 shows how to run one, recipe 56 the selection report, recipe 57 an impact backtest and
recipe 64 the universe partition. Yahoo occasionally revises adjusted history, so re-runs can
differ in the second decimal; the extended-universe tables above were generated from the saved
JSON with pandas, like every other table here.
