# Evaluation

This document records how agentic-trader is evaluated, what was measured, and what the
numbers do and do not show. Every figure comes from a recorded run, and the tables were
generated from the saved result files rather than typed. To reproduce them, see
[Reproducing](#reproducing).

> **Scope.** All results use the **rule-based agents** (offline mode, no LLM) on **real
> prices** from Yahoo Finance. The LLM mode has **not** been evaluated, so nothing here
> describes Claude's trading performance. The trading measurements were taken on 2026-09-25
> and the v0.4 engineering measurements on 2026-09-26, both with the C++ backend.

## Summary

- **Out of sample, the agents do not beat buy & hold on Sharpe instrument by instrument.**
  Holdout mean Sharpe is 0.44 against 0.55 for buy & hold, over 15 instruments. In equities
  alone it is 0.63 against 0.68.
- **They consistently take about half the drawdown.** Holdout equity mean maximum drawdown is
  19.1% against 40.2% for buy & hold, and it is lower in every period.
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

### Settings

| Item | Setting |
|---|---|
| Universe | 10 equities: AAPL, NVDA, MSFT, META, GOOGL, AMZN, JPM, XOM, JNJ and SPY (large-cap technology plus financials, energy, healthcare and the index). 5 FX pairs: EURUSD, USDJPY, GBPUSD, AUDUSD, USDCAD |
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

## Holdout per instrument

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
| Tests | 197 pytest tests (agentic 30, adversarial 15, services 7 including a real MCP stdio round trip, quant research 18, LLM evaluation 11, plus the v0.3 suites) + 13 C++ test groups (34 checks) |

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
- **15 instruments is a small sample.** Differences in mean Sharpe below about 0.1 between
  variants should be read as noise; the alpha-analyst result is an example.
- **The holdout has been seen.** Every v0.4 choice was made on the design period, but any
  further tuning that consults the 2022–2026 numbers needs a new holdout.
- **Execution model.** Close-to-close fills, with costs as a fixed bps per unit of turnover.
  Stops fill at the level, or at the open on a gap. The backtests have no market impact; the
  execution simulator (`agentic-trader execute`) models spread and square-root impact but is
  not wired into the backtests.

## Reproducing

```bash
pip install -e ".[all]"

# the full protocol on real prices (design, holdout, q1_2024), all 15 instruments
agentic-trader evaluate --data yahoo --periods design,holdout,q1_2024 --out results/eval_v03.json

# the same with the v0.2 rule set, for the before/after comparison
agentic-trader evaluate --data yahoo --periods design,holdout,q1_2024 --rules v02 --out results/eval_v02.json

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
28 shows how to run one and recipe 56 the selection report. Yahoo occasionally revises
adjusted history, so re-runs can differ in the second decimal.
