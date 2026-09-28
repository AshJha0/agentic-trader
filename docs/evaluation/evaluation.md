# Evaluation

This document records how agentic-trader is evaluated, what was measured, and what the
numbers do and do not show. Every figure comes from a recorded run, and the tables were
generated from the saved result files rather than typed. The current record is
[the v0.8 section](#v08-engine-and-protocol-corrections-and-every-number-re-measured): every number there is pasted from
`results/v08/tables.md`, which `scripts/render_v08_tables.py` renders from the files
`scripts/measure_v08.py` wrote. The sections before it are the historical record of
v0.2–v0.7, measured under earlier engines; each carries a banner saying so, and where a
v0.8 number reverses a section's conclusion the section says so in one sentence. To
reproduce anything, see [Reproducing](#reproducing).

> **Scope.** Every table except [the LLM section](#the-llm-desk-v051-the-first-measured-result)
> uses the **rule-based agents** (offline mode, no LLM) on **real prices** from Yahoo Finance,
> with SEC EDGAR filings for the equities since v0.6 and FRED policy rates and bills for FX
> and the cash leg. The LLM desk was measured once, in v0.5.1, on one quarter and five stocks
> (271 calls, $4); that section says exactly what it does and does not show, and its numbers
> are not re-derived under the v0.8 engine. The v0.8 tables were measured on 2026-09-28 with
> the C++ backend (`results/v08/manifest.json`); the historical sections were measured on
> 2026-09-25 (core universe), 2026-09-26 (extended universe, reserve period, impact sweep,
> LLM, and the v0.6 EDGAR, cross-sectional-analyst and cross-instrument-bootstrap sections)
> and 2026-09-27 (the v0.7 execution-algorithm and VaR-coverage sections), also with the C++
> backend.

## Summary

The v0.8 re-measurement is the current record: every number in this summary is from
[the v0.8 section](#v08-engine-and-protocol-corrections-and-every-number-re-measured) (`results/v08`, measured
2026-09-28 under the corrected engine, Sharpe on returns in excess of the credited 3-month
bill); the earlier sections are the historical record and carry a banner saying so. Median
Sharpe is quoted from the summary tables; mean differences, with their 95% bootstrap
interval, two-sided p and the Benjamini–Hochberg flag where the table prints one, from the
paired tables. The bootstrap resamples instruments on the core (15) and extended (45)
universes (`scheme=instruments`, fewer than 5 asset-class-by-universe groups) and clusters
of those groups on all 60 (`scheme=clusters`, 5 groups: core equities, core FX, extended
equities, macro ETFs, FX crosses). An interval printed as [0.00, x] or [-0.00, x] is
never called "excluding zero".

- **Per instrument, out of sample, the desk is below buy & hold on Sharpe, and below the
  volatility-targeted control too.** Core holdout median Sharpe 0.30 against 0.51 (buy &
  hold) and 0.52 (vol-target); paired mean difference desk − B&H -0.10 [-0.21, -0.00] p 0.04
  and desk − vol-target -0.11 [-0.21, -0.00] p 0.04, neither BH-significant. Extended
  universe (45 names no rule was chosen on), holdout: 0.25 against 0.39 and 0.27; desk − B&H
  -0.07 [-0.12, -0.02] p 0.01, **BH-significant**; desk − vol-target -0.03 [-0.09, +0.02]
  p 0.19, not BH-significant. All 60 (clusters): desk − B&H -0.08 [-0.15, -0.03] p 0.00,
  **BH-significant**; desk − vol-target -0.05 [-0.15, 0.00] p 0.07, not significant. On the
  design period the core desk is level: 0.67 against 0.73 and 0.69; desk − B&H +0.06
  [-0.06, +0.17] p 0.29, not BH-significant. This is stronger than v0.7's "noise either way":
  on the extended names, which no rule was tuned on, the deficit against buy & hold clears
  the BH bar. The desk still beats the signal-flipping baselines on most slices (holdout,
  all 60, desk − SMA +0.25 [+0.01, +0.43] p 0.04, not BH-flagged; extended holdout +0.28
  [+0.16, +0.41] p 0.00, BH-significant).
- **"About half the drawdown" is true against plain buy & hold and is almost entirely
  volatility scaling.** Core holdout mean maximum drawdown 17.40% (desk) against 31.64%
  (buy & hold) and 18.98% (vol-target); paired desk − B&H -14.24 points [-20.41, -8.70]
  p 0.00, BH-significant; desk − vol-target -1.58 [-4.33, +1.14] p 0.27, not significant. On
  the ten core equities the desk's holdout drawdown is not lower than the fair control's:
  22.11% against 21.28%, +0.83 [-1.63, +3.21] p 0.50, not BH-significant. On the extended
  universe it is: 15.46% against 19.79% (and 26.39% for buy & hold); desk − vol-target -4.33
  [-6.10, -2.55] p 0.00, BH-significant; desk − B&H -10.93 [-13.41, -8.64] p 0.00,
  BH-significant. On FX the vol-target control sits at the shared 1.0 position cap most of
  the time, so the FX drawdown comparison has essentially no control. Calmar on the extended
  holdout: desk − B&H +0.11 [+0.03, +0.19] p 0.00, BH-significant; desk − vol-target +0.07
  [0.00, +0.14] p 0.05, not flagged.
- **As a 15-sleeve equal-capital portfolio the desk no longer beats plain buy & hold on
  Sharpe; the v0.7 claim (1.09 against 1.06) is retracted.** Holdout Sharpe 0.80 (CR 50.62%,
  MDD 7.80%, exposure 59.10%) against 0.86 for buy & hold (96.91%, 20.43%) and 0.99 for the
  vol-targeted control (61.48%, 9.17%); paired block bootstrap over days (block 10, n 1167):
  desk − B&H -0.06 [-0.41, +0.30] p 0.748, desk − vol-target -0.19 [-0.53, +0.16] p 0.297.
  Design: 1.40 against 1.28 and 1.43; desk − B&H +0.12 [-0.16, +0.40] p 0.434; desk −
  vol-target -0.03 [-0.28, +0.23] p 0.898. Shifting the 5-bar rebalance phase (offsets 0–4)
  moves the desk's holdout Sharpe across 0.80 / 0.85 / 0.86 / 0.80 / 0.84, a spread of 0.06
  against a fixed 0.99 (vol-target) and 0.86 (buy & hold): the cadence noise floor is the
  size of the portfolio differences quoted.
- **The cash leg (new in v0.8) lowered every strategy's Sharpe on the holdout and decides
  nothing about the ranking.** Equities are funded, so (1 − |w|) of the account earns the
  3-month bill (FRED DTB3, one-day publication lag); FX forwards earn it on the whole
  account; Sharpe and Sortino are on excess returns; CR, AR, MDD and Calmar stay total
  return; synthetic data is unchanged (its rate is the constant 0). Holdout portfolio with the
  leg on → off: desk 0.80 → 1.04 (CR 50.62% → 35.17%), buy & hold 0.86 → 1.05, vol-target
  0.99 → 1.24; under either convention the order is desk < buy & hold < vol-target. Per
  instrument, the agent's Sharpe with the leg off minus on is +0.10 [+0.06, +0.15] p 0.00 on
  the core holdout and +0.15 [+0.04, +0.23] p 0.02 on all 60 (clusters); the credited bill
  averaged 3.99% a year over the 2022–2026 holdout and 0.94% over the 2016–2021 design period
  (`rf` column of `results/v08/portfolio_holdout.csv` and `results/v08/portfolio_design.csv`),
  so the design period barely moves (+0.03 [+0.02, +0.04] p 0.00 on the core). Of the
  v0.7 → v0.8 portfolio holdout move 1.09 → 0.80, the convention accounts for 1.04 → 0.80
  (measured on one engine); the rest, 1.09 → 1.04, is a difference between two records on two
  engines, not a measured effect.
- **Execution costs do not change the ranking below institutional size.** With
  equity-scaled square-root impact (coefficient 1.0, core universe) the desk's mean Sharpe is
  unchanged at $100k and $10M (design 0.66 → 0.66 → 0.66, holdout 0.34 → 0.34 → 0.34) and
  goes to 0.61 (impact paid 4.24% of equity) and 0.31 (2.53%) at $1B; the vol-targeted
  control goes 0.64 → 0.57 and 0.45 → 0.41, SMA 0.57 → 0.38 and 0.18 → 0.04, MACD
  0.40 → -0.18 and 0.14 → -0.30 (64.71% of equity paid on the design period). v0.7's "loses
  0.09 at $1B" is replaced by these. Execution algorithms on the $1B holdout portfolio, each
  sleeve paying impact at its own capital: VWAP 0.78 (impact paid 0.66%), TWAP 0.78 (0.70%),
  Almgren–Chriss κ=5 0.77 (0.87%); the v0.7 table charged √15 times too much and is
  retracted, its ordering survives.
- **EDGAR filings on against off** (the v0.6 data decision, re-checked under the corrected
  per-concept, per-basis reconstruction; every earlier EDGAR figure is superseded): agent
  Sharpe with the filings minus without, design core +0.01 [-0.03, +0.04] p 0.72 (the filings
  reach the 10 equities only), design extended +0.01 [+0.00, +0.02] p 0.02, design all 60
  +0.01 [-0.01, +0.02] p 0.19 (clusters); holdout core -0.01 [-0.07, +0.04] p 0.83, holdout
  extended +0.03 [+0.01, +0.06] p 0.00, holdout all 60 +0.02 [-0.02, +0.05] p 0.39. These
  on-vs-off tables print no BH flag. The core design period cannot tell on from off; the
  extended equities, which no rule was tuned on, show a small gain; the all-60 cluster
  interval covers zero. The data stays on; the untuned rules that read it remain the next
  protocol item.
- **The FX carry-neutral rule (v0.5.1), re-checked:** on minus off, design core +0.04
  [-0.01, +0.10] p 0.11 (the rule touches FX only); holdout core +0.02 [-0.02, +0.07] p 0.37;
  holdout extended +0.04 [+0.00, +0.08] p 0.04; q1_2024 core +0.49 [+0.12, +0.94] p 0.01;
  reserve extended +0.14 [+0.03, +0.28] p 0.00; all 60 holdout +0.03 [-0.00, +0.12] p 0.23
  (clusters). Positive on every slice, small, intervals touching zero on most.
- **v0.3's rule changes were chosen on 2016–2021 data only.** Against the v0.2 rules on the
  core universe: design +0.19 [+0.10, +0.28] p 0.00; holdout -0.00 [-0.11, +0.09] p 0.99
  (0.34 against 0.34) — the design-period gain did not carry to the holdout at all (v0.7 said
  "shrank"); the two short windows favour v0.3 (q1_2024 +0.72 [+0.29, +1.17] p 0.00, reserve
  +0.95 [+0.45, +1.47] p 0.00).
- **The cross-sectional analyst (v0.6) stays off by default:** design core -0.01
  [-0.02, +0.00] p 0.36; holdout core 0.00 [-0.01, +0.02] p 0.60; holdout extended -0.00
  [-0.01, +0.00] p 0.23; reserve extended -0.02 [-0.06, +0.01] p 0.20.
- **The alpha analyst with the corrected gate stays off by default:** core design -0.00
  [-0.05, +0.05] p 0.90; holdout -0.00 [-0.04, +0.02] p 0.79; q1_2024 +0.10 [+0.01, +0.23]
  p 0.01; reserve +0.07 [-0.00, +0.20] p 0.21. How often the corrected gate speaks was not
  measured.
- **The track-record size cut stays on** (`rules.track_record_cut`): off minus on, design
  core +0.00 [-0.00, +0.01] p 0.51 — the only basis the protocol accepts cannot tell the two
  apart. Design extended +0.01 [+0.00, +0.01] p 0.01, holdout extended +0.01 [+0.00, +0.02]
  p 0.02, q1_2024 extended +0.04 [+0.01, +0.07] p 0.00 and reserve core +0.04 [+0.00, +0.09]
  p 0.04 are recorded as information for the next rule change, not as a choice basis.
- **Most literature-backed signal tweaks did nothing measurable on the design period**
  (re-measured trials: 0.45–0.48 of mean Sharpe around the control's 0.47). The one change
  that worked, a strategic (benchmark) equity weight, works by collecting the equity premium
  (0.47 → 0.63 at weight 1.00, CR 58.24% → 121.95%, exposure 43.99% → 60.37%), not by
  forecasting better.
- **After correcting for the 26 variants tried, the chosen rule set still clears the bar on
  the design period** (deflated Sharpe probability 0.998; annual Sharpe 1.375, t 3.42 —
  annualised at 252 periods/year by the renderer; the same series is the 1.40, t 3.43 of the
  portfolio tables at their 260 periods/year — bootstrap 95% interval [0.593, 2.17], expected
  maximum of 26 null trials 0.161) — but that number is an *upper bound*, not the real figure:
  the trials' dispersion is narrower than the true search space (details in
  [selection statistics: 26 trials](#9-selection-statistics-26-trials)).
- **VaR coverage, two labelled tests.** (a) The rolling historical VaR of the holdout
  portfolio's own returns: 120-day window 65 breaches in 1048 days (rate 0.0620; Kupiec
  p 0.0847, Christoffersen p 0.1488, conditional coverage p 0.0798) — not rejected at 5%, but
  close; 250-day window 42 in 918 (0.0458; 0.5493, 0.1650, 0.3188). (b) The desk's own
  per-instrument forecast (250-day historical VaR, `agents/risk.py`) against each core
  instrument's next-day return over the holdout: Kupiec rejects at 5% on 2 of 15 (AAPL
  0.0657, p 0.0207; AUDUSD 0.0634, p 0.0432), every breach rate is above 5% (0.0523 to
  0.0657), and Christoffersen independence rejects on 6 of 15 — breaches cluster. Book-level
  VaR was off in every published run and its coverage is untested. v0.7's "the desk's own
  risk model is calibrated" is replaced by these.
- **The reserve period (three months) says little:** core desk median Sharpe 0.81 against
  1.05 for both controls; extended -0.11 against -0.08 (buy & hold) and -0.11 (vol-target);
  the paired differences against the controls are not significant.
- **Nothing remains unseen.** The reserve period and the extended universe were consulted
  for the v0.5.1 carry rule and the v0.6 EDGAR and cross-sectional decisions, and v0.8
  re-measured every period; the next unseen data is the future (see
  [the next rule change](#the-next-rule-change-what-counts-as-unseen)).
- **The LLM desk is still one measurement:** five stocks, one quarter, $4 (v0.5.1), no
  Sharpe edge over the rules (2.19 against 2.19), smaller positions with lower returns and
  drawdowns. The multi-year harness exists and has not been executed, and the v0.5.1 numbers
  were produced under the v0.7-and-earlier engine and are not re-derived under the v0.8
  engine.
- **FX is roughly zero** before and after every change: core FX holdout median Sharpe 0.06
  (desk) against -0.05 (buy & hold) and -0.11 (vol-target).

## Protocol

### Periods

| Period | Key | Dates | Use |
|---|---|---|---|
| **Design** | `design` | 2016-01-04 → 2021-12-31 | The **only** data used to choose rule changes and defaults |
| **Holdout** | `holdout` | 2022-01-03 → 2026-06-30 | Run **once**, with frozen rules. Never used for a choice |
| **Q1 2024** | `q1_2024` | 2024-01-02 → 2024-03-28 | A short reference window inside the holdout, kept because a single quarter is what many published LLM-trading results are based on |
| **Reserve** | `reserve` | 2026-07-01 → 2026-09-25 | v0.5. Consulted for the v0.5.1 carry rule and the v0.6 EDGAR and cross-sectional decisions, and re-measured with every other period in v0.8, so it is no longer unseen; its end is pinned at 2026-09-25 in `PERIODS` until the constant is moved (see [the next rule change](#the-next-rule-change-what-counts-as-unseen)) |

### Settings

| Item | Setting |
|---|---|
| Core universe | The 15 instruments every rule choice through v0.4 was made on. 10 equities: AAPL, NVDA, MSFT, META, GOOGL, AMZN, JPM, XOM, JNJ and SPY (large-cap technology plus financials, energy, healthcare and the index). 5 FX pairs: EURUSD, USDJPY, GBPUSD, AUDUSD, USDCAD |
| Extended universe (v0.5) | 45 instruments that no choice ever consulted. 26 equities across sectors and styles: UNH, V, MA, PG, HD, COST, WMT, KO, PEP, CVX, LLY, ABBV, MRK, BAC, GS, CAT, BA, BRK-B, QQQ, IWM, XLF, XLE, XLV, XLU, EEM, EFA. 9 rates / credit / commodity / real-estate ETFs, traded as equities: TLT, IEF, LQD, HYG, GLD, SLV, USO, DBC, VNQ. 10 FX crosses whose both legs have FRED policy-rate series: NZDUSD, USDCHF, EURGBP, EURJPY, GBPJPY, AUDJPY, EURCHF, AUDNZD, CADJPY, EURAUD |
| Prices | Yahoo Finance daily, dividend- and split-adjusted (total return) |
| Filings, news and fundamentals (data) | SEC EDGAR point-in-time filings for real-data equities since v0.6 (None under `--no-edgar`); social: none. Yahoo serves only recent news and current-snapshot fundamentals, and the point-in-time guards refuse both |
| FX macro | Point-in-time **FRED** policy rates. Values are publication-lagged (daily series by 1 day, monthly averages by about 40 days) and treated as unavailable when stale. Carry is accrued per bar from the same series |
| FX rate source (v0.8) | FRED only, as known on the date, with no static-table fallback in backtests (the static table serves synthetic data only); a stale, discontinued or unlisted leg gives no macro view, a strategic FX weight of 0 and NaN carry. SEK has no series (its OECD series stopped in 2020-10); NOK was added in v0.8. No published instrument has a SEK or NOK leg |
| Cash leg (v0.8) | `cash_leg: auto`: the 3-month bill (FRED DTB3, one-day publication lag) is credited on (1 − \|w\|) of the account for funded equity positions and on the whole account for FX forwards; the constant 0 on synthetic data. Sharpe, Sortino and t(SR) are on returns in excess of it; CR, AR, MDD and Calmar stay total return. `cash_leg: off` credits nothing and uses `risk_free_annual` (0): the v0.7 convention |
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
for FX; a multi-sleeve portfolio annualises with the largest *P* among its sleeves, 260
when an FX pair is present):

| Metric | Definition |
|---|---|
| CR | *V_end / V_start − 1* |
| AR | *(1 + CR)^(P/n) − 1* |
| Vol | *std(r, ddof = 1) · √P* |
| Sharpe | *mean(r − rf) / std(r − rf) · √P*. Since v0.8 *rf* is the per-bar credited cash rate (the [cash leg](#4-the-cash-leg)); through v0.7, and on synthetic data, it is 0 |
| t(SR) | *mean(r − rf) / std(r − rf) · √n*: the t-statistic of the mean excess return. About 2 is needed before a Sharpe ratio is distinguishable from 0 |
| Calmar | *AR / MDD*, total return |
| MDD | *max over t of (1 − V_t / max_{s≤t} V_s)* |
| Exposure | Mean \|weight\| per period |
| Trades | Number of changes in the held weight (vol-target B&H changes weight almost daily) |

Cross-instrument figures are simple means or medians over instruments. The `n` column
counts instruments.

## Headline results

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

Under v0.8 the core holdout median Sharpe is 0.30 (desk) against 0.51 (buy & hold) and 0.52
(vol-target), with the desk's paired mean difference -0.10 [-0.21, -0.00] p 0.04 against buy
& hold and -0.11 [-0.21, -0.00] p 0.04 against the control, neither BH-significant
([headline re-measurement](#2-headline-re-measurement-eval_mainjson)); the mean-Sharpe columns
below are the v0.3 record.

### Design period (2016–2021): used to choose the v0.3 rules

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

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

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

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
  only 0.03. (v0.8, v0.3 rules minus v0.2 rules on the core universe: design +0.19
  [+0.10, +0.28] p 0.00, holdout -0.00 [-0.11, +0.09] p 0.99 — the gain did not carry at all;
  see [re-checks](#7-every-earlier-decision-re-checked-under-the-v08-engine).)
- **The return and cost gains did survive:** equity mean return rose from 30% to 47%, and
  trades roughly halved.
- **The drawdown profile held:** about half of buy & hold's. (v0.8: true against plain buy &
  hold — core holdout -14.24 points [-20.41, -8.70] p 0.00, BH-significant — but not against
  the fair control, -1.58 [-4.33, +1.14] p 0.27, not BH-significant; on the ten core equities
  +0.83 [-1.63, +3.21] p 0.50, not BH-significant; see
  [drawdown against the fair control](#5-drawdown-against-the-fair-control).)
- **FX stays near zero.** Buy & hold's positive FX mean comes mostly from USDJPY (+67%) and
  USDCAD, while the median pair lost money.

### Q1 2024 window (inside the holdout)

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

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

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

v0.8 head to head (core holdout): the desk beats buy & hold on 3 of 15 and the vol-targeted
control on 4 of 15, median differences -0.06 and -0.09. The first two clauses of the
conclusion below stand (it still beats SMA, MACD and ZMR on 11 / 12 / 10 of 15 and still
loses to buy & hold on most instruments); the last does not: by count it now loses to plain
buy & hold slightly more often than to the control (12 against 11 of 15), although the median
shortfall is larger against the control (-0.09 against -0.06)
([v0.8 tables](#2-headline-re-measurement-eval_mainjson)).

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

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

Re-measured under the v0.8 engine in the [trials registry](#9-selection-statistics-26-trials):
control 0.47 (recorded 0.50), strategic equity weight 0.25 / 0.50 / 1.00 = 0.54 / 0.58 / 0.63
(recorded 0.54 / 0.58 / 0.66), frozen v0.3 0.62 (0.65); the ordering is unchanged. Two of the
decision sentences below are superseded by the re-measured numbers: intraday stops cut the
design-period mean CR from 58.24% to 44.10% at a mean Sharpe of 0.45 against 0.47 (about a
quarter, not "about 30%"), and the no-trade band gives the same 0.47 at 135.20 trades per
instrument against 254.20 (47% fewer, not "44% fewer").

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

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

Under v0.8, with the overlap-aware `t(IC)` that corrects the gate, the alpha analyst against the
default on the core universe: design -0.00 [-0.05, +0.05] p 0.90, holdout -0.00 [-0.04, +0.02]
p 0.79 — off by default stands ([re-checks](#7-every-earlier-decision-re-checked-under-the-v08-engine)).

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

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

v0.8 recomputes this with the 26-entry trials registry: deflated Sharpe probability 0.998,
expected maximum of 26 null trials 0.161, bootstrap 95% interval [0.593, 2.17] — see
[selection statistics: 26 trials](#9-selection-statistics-26-trials). The holdout portfolio
Sharpe quoted below (1.14 against 1.24) is the v0.3 record; under v0.8 it is 0.80 against 0.99.

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
| Deflated Sharpe probability | 1.00 (upper bound — see below) |
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

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

Under v0.8 the extended-universe conclusion holds and hardens: holdout desk − B&H -0.07
[-0.12, -0.02] p 0.01, BH-significant, and the drawdown is lower than the fair control's too,
-4.33 [-6.10, -2.55] p 0.00, BH-significant. The extended universe is no longer unseen: it
judged the v0.5.1 and v0.6 decisions and v0.8 re-measured it
([what remains unseen](#10-what-remains-unseen)).

Every rule choice through v0.4 was made on the 15 core instruments, and by v0.4 the holdout
itself had been reported and compared against, so it no longer counts as unseen. v0.5 adds
45 instruments that no choice ever consulted, which makes them out of sample on *every*
period, including the design period. The rules are the frozen v0.3 defaults; nothing was
tuned for the new names.

### Headline results, extended universe (45 instruments)

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

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

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

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

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

Under v0.8 (impact scaled by the equity actually traded) the desk goes 0.66 → 0.61 on the
design period and 0.34 → 0.31 on the holdout at $1B, paying 4.24% and 2.53% of equity; the
"loses 0.09" below is the v0.5 record
([impact](#6-impact-and-execution-algorithms-at-the-sleeves-capital)).

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
  more than before. (Retracted in v0.8: 0.66 → 0.61 on the design period, 4.24% of equity
  paid; the control 0.64 → 0.57, so at $1B the desk is above the control on the design
  period (0.61 against 0.57) and still trails it on the holdout (0.31 against 0.41).)
- **Many small trades are cheaper than a few large ones.** The daily vol-target baseline
  makes ~1,100 trades and pays *less* impact than the desk's ~106, because the cost of a trade
  grows with `|dw|^1.5`: a hundred 1% adjustments cost a tenth of one 100% jump. MACD, which
  flips whole positions, loses three quarters of its equity to impact at $1B. (Neither reading
  survives v0.8: with impact scaled by the equity actually traded, the vol-target control pays
  *more* than the desk at $1B — 6.92% against 4.24% of equity on the design period, 3.57%
  against 2.53% on the holdout — and the v0.8 renderer prints no trade counts for the sweep,
  so the ~1,100-vs-~106 comparison is not restated; MACD pays 64.71% / 39.01% of equity with
  Sharpe 0.40 → -0.18 / 0.14 → -0.30, and the "three quarters" sentence is withdrawn in
  CHANGELOG v0.8.0 Retracted; see
  [the v0.8 impact table](#6-impact-and-execution-algorithms-at-the-sleeves-capital).)
- Buy & hold is not free either: its single entry trade at $1B costs about 1%.

FX sleeves get no impact in these runs (no exchange volume; set `costs.fx_adv_notional` to
model it), so the FX rows are unchanged across the columns and the averages above are
driven by the equities.

### Execution-algorithm-aware impact (v0.7)

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

**The magnitudes in this table are retracted** (CHANGELOG v0.8.0, Retracted):
`run_portfolio_backtest` ran every sleeve with the whole book's capital, so each sleeve paid
√15 times the impact of a $1B/15 sleeve. Re-measured at the sleeve's own capital: VWAP 0.78
Sharpe / 0.66% of equity, TWAP 0.78 / 0.70%, Almgren-Chriss κ=5 0.77 / 0.87% — the ordering
VWAP < TWAP < AC survives, the magnitudes do not
([v0.8 table](#6-impact-and-execution-algorithms-at-the-sleeves-capital)).

The impact sweep above assumes every trade is worked across the session in proportion to
volume (VWAP), which minimises square-root-law impact cost for a fixed order size (see
`agentic_trader.algo.algo_cost_ratio`) -- so it is also what `costs.execution_algo` unset
means. Setting it to `"twap"` (equal size per slice, ignoring the intraday volume curve) or
`"ac"` (Almgren-Chriss, trading faster than the volume curve to cut timing risk) scales the
day's impact by that schedule's cost relative to VWAP, so **the simulated cost of a trade
now depends on how it would be worked, not only on its size.** Core universe with EDGAR
fundamentals and news, $1B capital, `impact_coeff` 1.0, holdout period, combined 15-sleeve
portfolio:

| execution algo | Sharpe | CR % | MDD % | mean sleeve impact paid % |
|:--|--:|--:|--:|--:|
| VWAP (default) | 1.009 | 33.0 | 7.84 | 2.37 |
| TWAP | 1.004 | 32.8 | 7.85 | 2.51 |
| Almgren-Chriss, kappa=5 | 0.982 | 32.0 | 7.88 | 3.14 |

TWAP costs a little more than VWAP, because equities' U-shaped intraday volume curve (heavy
at the open and close) means equal-sized slices over-trade the illiquid middle of the
session; Almgren-Chriss at an aggressive urgency (kappa=5, front-loaded to cut timing risk)
costs substantially more, because it deliberately trades ahead of the volume curve rather
than with it. This is a same-session, always-fills cost model -- it does not represent POV's
own fill risk (see `algo_cost_ratio`'s docstring) -- and the default (unset, VWAP-equivalent)
is unchanged, so every number in the sweep above and everywhere else on this page is
unaffected by this feature existing.

## The FX carry-neutral rule (v0.5.1): the protocol's first use

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

Re-checked under v0.8 (rule on minus off, agent Sharpe): design core +0.04 [-0.01, +0.10]
p 0.11 (the rule touches FX only); holdout core +0.02 [-0.02, +0.07] p 0.37; holdout extended
+0.04 [+0.00, +0.08] p 0.04; q1_2024 core +0.49 [+0.12, +0.94] p 0.01; reserve extended +0.14
[+0.03, +0.28] p 0.00; all 60 holdout +0.03 [-0.00, +0.12] p 0.23 (clusters). Positive on
every slice, small, intervals touching zero on most: "improved every unseen slice" stands
only with these numbers beside it
([re-checks](#7-every-earlier-decision-re-checked-under-the-v08-engine)).

The extended-universe results above singled out FX crosses as the weak spot: with a
strategic FX weight of 0, every FX return comes from directional calls, and on the crosses
those calls lost money. The equity fix in v0.3 was to hold the equity premium unless
convinced otherwise. The FX analogue is to hold the **carry premium**: the strategic FX weight
becomes `clip(rate_diff% / scale, -cap, cap)`, where `rate_diff` is the point-in-time policy-rate
differential the macro analyst already reads (publication-lagged FRED), so the desk holds the
higher-yielding currency at a size that grows with the differential and is capped.

**Step 1 — choose on the core FX pairs' design period only** (5 pairs, 2016–2021; nothing
else consulted):

| variant | mean Sharpe | median Sharpe | mean CR % | mean MDD % | mean exposure % | mean trades | beats B&H | beats vol-target |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| control (FX strategic weight 0, v0.3 rules) | -0.03 | 0.12 | -0.79 | 11.58 | 51.7 | 154.6 | 4 / 5 | 4 / 5 |
| carry / 4, cap 0.5 | 0.08 | 0.16 | 2.95 | 11.41 | 59.7 | 140.0 | 4 / 5 | 4 / 5 |
| **carry / 2, cap 0.5** | **0.11** | 0.12 | 4.54 | 11.48 | 63.3 | 132.0 | 4 / 5 | 4 / 5 |
| carry / 4, cap 1.0 | 0.08 | 0.15 | 2.88 | 11.46 | 59.6 | 138.2 | 4 / 5 | 4 / 5 |
| carry / 8, cap 0.25 | 0.03 | 0.16 | 1.27 | 11.43 | 56.6 | 150.8 | 4 / 5 | 4 / 5 |

Every setting helps and the effect is monotonic in the strength of the tilt up to
`carry / 2`, which was chosen (a 1% differential holds 0.5; the cap binds from 1%).

**Step 2 — judge on data no choice touched**, with that one setting:

| data | period | n | control mean Sharpe | carry / 2 mean Sharpe | control CR % | carry / 2 CR % | control MDD % | carry / 2 MDD % | B&H mean Sharpe |
|:--|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| extended crosses (unseen) | design | 10 | -0.24 | **-0.15** | -6.8 | -5.2 | 14.6 | 14.9 | 0.05 |
| extended crosses (unseen) | holdout | 10 | 0.12 | **0.31** | 4.5 | 11.9 | 11.5 | 11.7 | 0.39 |
| extended crosses (unseen) | reserve | 10 | -0.63 | **0.22** | -1.2 | -0.1 | 3.2 | 2.8 | -0.10 |
| core pairs (seen) | holdout | 5 | 0.04 | 0.10 | 1.5 | 5.0 | 11.3 | 12.6 | 0.28 |
| core pairs (seen) | reserve | 5 | -0.58 | -0.10 | -0.9 | -0.3 | 2.9 | 3.0 | -0.12 |

**Decision: adopted as the default (`rules.fx_carry_neutral`, scale 2, cap 0.5).** The rule
was chosen on five pairs over one period and then improved every one of the four slices it
had never seen, in the same direction and by more than the noise floor on the largest of
them (+0.19 on the 10-cross holdout), with a prior as strong as the equity premium's. Two
things it does **not** do: it does not make the desk beat buy & hold on the crosses (2 of 10
on the holdout, against 0.39 for buy & hold), and it does not change the equity sleeves at
all. `RULES_V03` / `--rules v03` reproduces the rule set without it, and the headline tables
above marked "v0.3 rules" are that record; the tables marked "v0.5.1 rules" below are the
same runs with the new default.

### The published tables under the v0.5.1 rules

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

The portfolio numbers at the end of this subsection (holdout 1.16 against 1.06 and 1.24) are
the v0.5.1 record; under v0.8 the holdout portfolio is 0.80 against 0.86 (buy & hold) and
0.99 (vol-target) ([portfolio view](#3-portfolio-view-15-equal-capital-sleeves-with-intervals)).

The same runs as above with the new default (equity rows are identical; every FX row and
every mixed aggregate moves). Agent rows only; the baselines do not change.

| slice | period | v0.3 rules mean Sharpe | **v0.5.1 rules** | v0.3 CR % | v0.5.1 CR % | v0.3 MDD % | v0.5.1 MDD % | v0.5.1 beats B&H | beats vol-target | B&H mean Sharpe | vol-target mean Sharpe |
|:--|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| core, all 15 | design | 0.65 | **0.70** | 105.2 | 107.0 | 15.7 | 15.7 | 10 / 15 | 6 / 15 | 0.63 | 0.67 |
| core, all 15 | holdout | 0.44 | **0.46** | 32.1 | 33.3 | 16.5 | 16.9 | 5 / 15 | 4 / 15 | 0.55 | 0.56 |
| core, all 15 | q1_2024 | 1.50 | **2.02** | 7.9 | 8.5 | 3.6 | 3.5 | 5 / 15 | 3 / 15 | 1.89 | 1.94 |
| core, all 15 | reserve | 0.72 | **0.88** | 3.1 | 3.3 | 4.6 | 4.7 | 3 / 15 | 5 / 15 | 1.01 | 1.01 |
| core FX (5) | design | -0.03 | **0.11** | -0.8 | 4.5 | 11.6 | 11.5 | 4 / 5 | 4 / 5 | -0.05 | -0.06 |
| core FX (5) | holdout | 0.04 | **0.10** | 1.5 | 5.0 | 11.3 | 12.6 | 2 / 5 | 2 / 5 | 0.28 | 0.26 |
| core FX (5) | q1_2024 | -0.44 | **1.12** | -0.1 | 1.8 | 2.2 | 2.0 | 2 / 5 | 2 / 5 | 0.34 | 0.34 |
| core FX (5) | reserve | -0.58 | **-0.10** | -0.9 | -0.3 | 2.9 | 3.0 | 1 / 5 | 1 / 5 | -0.12 | -0.12 |
| extended, all 45 | design | 0.49 | **0.51** | 47.4 | 47.8 | 18.9 | 19.0 | 18 / 45 | 10 / 45 | 0.56 | 0.61 |
| extended, all 45 | holdout | 0.37 | **0.42** | 25.1 | 26.7 | 17.7 | 17.7 | 15 / 45 | 14 / 45 | 0.50 | 0.47 |
| extended, all 45 | q1_2024 | 1.64 | **1.79** | 4.6 | 4.8 | 3.6 | 3.6 | 9 / 45 | 13 / 45 | 2.11 | 2.11 |
| extended, all 45 | reserve | -0.07 | **0.11** | 0.8 | 1.1 | 4.7 | 4.7 | 16 / 45 | 16 / 45 | 0.01 | 0.02 |
| extended FX crosses (10) | design | -0.24 | **-0.15** | -6.8 | -5.2 | 14.6 | 14.9 | 3 / 10 | 3 / 10 | 0.05 | 0.05 |
| extended FX crosses (10) | holdout | 0.12 | **0.31** | 4.5 | 11.9 | 11.5 | 11.7 | 2 / 10 | 2 / 10 | 0.39 | 0.39 |
| extended FX crosses (10) | q1_2024 | 0.77 | **1.45** | 1.2 | 2.4 | 1.7 | 1.8 | 1 / 10 | 1 / 10 | 2.21 | 2.21 |
| extended FX crosses (10) | reserve | -0.63 | **0.22** | -1.2 | -0.1 | 3.2 | 2.8 | 2 / 10 | 2 / 10 | -0.10 | -0.10 |

The 15-sleeve portfolio under the v0.5.1 rules: design Sharpe **1.54** (t 3.79, CR 81.3%,
MDD 8.3%) against 1.50 before; holdout **1.16** (t 2.46, CR 32.8%, MDD 7.0%) against 1.14,
still between plain buy & hold (1.06) and the vol-targeted control (1.24). The impact sweep
moves with it: core design Sharpe 0.70 → 0.70 / 0.69 / 0.60 at $100k / $10M / $1B, holdout
0.46 → 0.46 / 0.45 / 0.37; the impact paid is identical (FX sleeves get no impact).

<!-- v0.6 sections -->
## v0.6: point-in-time filings for the idle analysts, and the cross-sectional analyst

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

Every EDGAR-derived number in this section was produced by the v0.6 reconstruction, which v0.8
replaced (per concept, per reporting basis, with recency and share-class guards); the
on-vs-off comparison is re-measured under
[re-checks](#7-every-earlier-decision-re-checked-under-the-v08-engine).

Two changes went through the protocol in v0.6. The first is a *data* change: the fundamentals
and news analysts, which had abstained on every historical date since v0.1 because no
point-in-time source existed, now read SEC EDGAR — every XBRL fact and every filing carries
the date it was filed, so a backtest sees exactly what the market could, as first printed
(see `data/edgar.py`; funds and index ETFs have no company facts and are unchanged; FX is
unchanged). The second is a *rule* change: the cross-sectional alpha analyst (`xalpha`), the
v0.5 research consumed by an analyst for the first time. Both were measured on all 60
instruments over all four periods; the choice was made on the core design period, the
extended universe and the reserve period judged it. The cross-instrument bootstrap
(`stats.paired_bootstrap`, new in v0.6) gives every difference an interval: instruments are
resampled with replacement, pairs kept together, so the interval says whether a mean
difference across the universe is more than the luck of which instruments were drawn.

### Regression check first

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

Before measuring anything, the v0.5.1 configuration was re-run with EDGAR off
(`--no-edgar`) on the rebuilt code:

1680 rows compared; max |diff| Sharpe 0.3000, CR% 3.9900, MDD% 0.2300

Three things moved, all understood. Nineteen of the 1,680 rows differ from the v0.5.1 record
because of the `sma` fix in this release (the C++ boundary fuzzer found a window where a
running sum's cancellation noise turned a flat z-score into ±1; both backends now sum each
window directly): fourteen at the last displayed digit, and a handful where a moving-average
crossing sat exactly on a threshold and one trade flipped — the largest is a baseline
(XLF SMA(20/50), design CR 127.0% → 123.0%, Sharpe 0.95 → 0.93); the desk's own rows move by
at most 0.21 of CR and one trade (LLY design, HD holdout). The Q1 2024 differences of 0.01
are Yahoo's adjusted-price history moving by a day's dividend adjustments. The one larger
difference (TLT, reserve, Sharpe 0.30) is the sentiment analyst's Yahoo headline feed, which
only exists for the last 30 days and changes every day — the reserve period ends yesterday,
so it is the one period that is never exactly reproducible from a live feed. Everything
else reproduces to the last digit; the tables in this section are all from the rebuilt code.

### The data change: EDGAR fundamentals and news

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

Under the corrected reconstruction (v0.8, agent Sharpe with the filings minus without, all
instruments): core design +0.01 [-0.03, +0.04] p 0.72; extended holdout +0.03 [+0.01, +0.06]
p 0.00, in a table that prints no BH flag; all 60 holdout +0.02 [-0.02, +0.05] p 0.39
(clusters). The core design period cannot tell on from off.

Per instrument, the agent's Sharpe with EDGAR on minus with EDGAR off, over the instruments
whose result changed at all (equities with company facts; ETFs and FX are identical by
construction):

| universe | period | n changed | mean Sharpe diff | 95% CI | p | better on | mean MDD diff | mean exposure diff |
|:--|:--|--:|--:|:--|--:|--:|--:|--:|
| core | design | 9 | +0.004 | [-0.07, +0.08] | 0.91 | 4 / 9 | +3.83 | +4.4 |
| core | holdout | 9 | +0.010 | [-0.09, +0.10] | 0.81 | 6 / 9 | +3.24 | +6.8 |
| core | q1_2024 | 4 | +0.335 | [-0.05, +0.81] | 0.11 | 3 / 4 | +0.56 | +7.6 |
| core | reserve | 8 | +0.244 | [+0.05, +0.46] | 0.01 | 5 / 8 | +0.07 | +5.4 |
| extended | design | 18 | +0.028 | [0.00, +0.05] | 0.03 | 10 / 18 | +1.11 | +4.1 |
| extended | holdout | 18 | +0.089 | [+0.04, +0.14] | 0.00 | 13 / 18 | -0.15 | +6.6 |
| extended | q1_2024 | 7 | +0.309 | [+0.11, +0.51] | 0.00 | 7 / 7 | +0.36 | +7.3 |
| extended | reserve | 14 | -0.050 | [-0.23, +0.08] | 0.58 | 8 / 14 | +0.45 | +5.7 |
| extended-macro | design | 4 | +0.002 | [-0.01, +0.01] | 0.85 | 1 / 4 | +0.29 | +0.2 |
| extended-macro | holdout | 4 | +0.010 | [0.00, +0.02] | 0.07 | 3 / 4 | -0.27 | +0.1 |
| extended-macro | q1_2024 | 2 | +0.075 | [+nan, +nan] | 1.00 | 2 / 2 | +0.03 | +0.7 |
| extended-macro | reserve | 1 | +0.000 | [+nan, +nan] | 1.00 | 0 / 1 | +0.41 | +2.3 |
| extended45 | design | 22 | +0.023 | [0.00, +0.05] | 0.04 | 11 / 22 | +0.96 | +3.3 |
| extended45 | holdout | 22 | +0.075 | [+0.03, +0.12] | 0.00 | 16 / 22 | -0.17 | +5.4 |
| extended45 | q1_2024 | 9 | +0.257 | [+0.10, +0.43] | 0.00 | 9 / 9 | +0.29 | +5.8 |
| extended45 | reserve | 15 | -0.047 | [-0.21, +0.07] | 0.58 | 8 / 15 | +0.45 | +5.5 |

### Core equities, per instrument (agent Sharpe, EDGAR off → on)

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

| symbol | design off | design on | holdout off | holdout on | q1_2024 off | q1_2024 on | reserve off | reserve on |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AAPL | 1.45 | 1.38 | 0.44 | 0.45 | -1.88 | -1.87 | 2.25 | 2.35 |
| NVDA | 1.65 | 1.55 | 1.14 | 1.04 | 5.50 | 5.50 | 1.12 | 1.59 |
| MSFT | 1.37 | 1.38 | 0.18 | 0.17 | 3.07 | 3.07 | 3.23 | 3.23 |
| META | 0.67 | 0.74 | 0.77 | 0.43 | 2.93 | 2.93 | 1.81 | 2.25 |
| GOOGL | 0.96 | 0.96 | 0.78 | 0.80 | 0.88 | 1.24 | -1.25 | -0.42 |
| AMZN | 1.20 | 1.20 | 0.35 | 0.42 | 3.07 | 3.07 | 0.33 | 0.56 |
| JPM | 0.55 | 0.77 | 0.80 | 0.86 | 4.98 | 4.98 | 0.57 | 0.47 |
| XOM | 0.43 | 0.22 | 0.60 | 0.83 | 3.27 | 3.16 | 2.92 | 2.90 |
| JNJ | 0.52 | 0.64 | 0.38 | 0.53 | -1.17 | -0.09 | 1.49 | 1.49 |
| SPY | 1.14 | 1.14 | 0.89 | 0.89 | 4.06 | 4.06 | 1.22 | 1.22 |

| symbol | design off | design on | holdout off | holdout on | q1_2024 off | q1_2024 on | reserve off | reserve on |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AAPL | 1.45 | 1.38 | 0.44 | 0.45 | -1.88 | -1.87 | 2.25 | 2.35 |
| NVDA | 1.65 | 1.55 | 1.14 | 1.04 | 5.50 | 5.50 | 1.12 | 1.59 |
| MSFT | 1.37 | 1.38 | 0.18 | 0.17 | 3.07 | 3.07 | 3.23 | 3.23 |
| META | 0.67 | 0.74 | 0.77 | 0.43 | 2.93 | 2.93 | 1.81 | 2.25 |
| GOOGL | 0.96 | 0.96 | 0.78 | 0.80 | 0.88 | 1.24 | -1.25 | -0.42 |
| AMZN | 1.20 | 1.20 | 0.35 | 0.42 | 3.07 | 3.07 | 0.33 | 0.56 |
| JPM | 0.55 | 0.77 | 0.80 | 0.86 | 4.98 | 4.98 | 0.57 | 0.47 |
| XOM | 0.43 | 0.22 | 0.60 | 0.83 | 3.27 | 3.16 | 2.92 | 2.90 |
| JNJ | 0.52 | 0.64 | 0.38 | 0.53 | -1.17 | -0.09 | 1.49 | 1.49 |
| SPY | 1.14 | 1.14 | 0.89 | 0.89 | 4.06 | 4.06 | 1.22 | 1.22 |

**Reading.** On the core equities the rules were chosen on, the real fundamentals and news
add nothing to risk-adjusted return — the mean Sharpe difference is 0.00 on the design period and
+0.01 on the holdout, with intervals [-0.07, +0.08] and
[-0.09, +0.10] — while raising exposure by 4–7 points and maximum
drawdown by 3–4 points. On the 22 extended equities the rules never saw, the same data adds
+0.02 (design) and +0.07 (holdout) of Sharpe with intervals [0.00, +0.05]
and [+0.03, +0.12], for 3–5 points more exposure and +0.96 / -0.17
points of drawdown. The pattern is what a data change, rather than a fitted one, looks like:
the fundamentals analyst's rules (P/E against a fixed sector multiple, growth, margin, leverage,
FCF yield) were written against the synthetic provider and never tuned; on large-cap names
that mostly grew, the real numbers read bullish and the desk holds more. The portfolio view:

| configuration | period | strategy | Sharpe | t(SR) | CR % | MDD % | Exp % |
|:--|:--|:--|--:|--:|--:|--:|--:|
| v0.5.1 rules (EDGAR off) | design | AgenticTrader | 1.54 | 3.79 | 81.3 | 8.3 | 59.2 |
| v0.5.1 rules (EDGAR off) | design | Buy&Hold | 1.32 | 3.24 | 192.2 | 22.7 | 97.6 |
| v0.5.1 rules (EDGAR off) | design | B&H vol-target | 1.49 | 3.65 | 92.8 | 9.8 | 79.2 |
| v0.5.1 rules (EDGAR off) | holdout | AgenticTrader | 1.16 | 2.46 | 32.8 | 7.0 | 54.6 |
| v0.5.1 rules (EDGAR off) | holdout | Buy&Hold | 1.06 | 2.24 | 86.6 | 20.8 | 97.6 |
| v0.5.1 rules (EDGAR off) | holdout | B&H vol-target | 1.24 | 2.63 | 46.3 | 9.8 | 73.8 |
| EDGAR on | design | AgenticTrader | 1.47 | 3.62 | 89.2 | 10.2 | 61.7 |
| EDGAR on | design | Buy&Hold | 1.32 | 3.24 | 192.2 | 22.7 | 97.6 |
| EDGAR on | design | B&H vol-target | 1.49 | 3.65 | 92.8 | 9.8 | 79.2 |
| EDGAR on | holdout | AgenticTrader | 1.09 | 2.31 | 36.2 | 7.8 | 58.5 |
| EDGAR on | holdout | Buy&Hold | 1.06 | 2.24 | 86.6 | 20.8 | 97.6 |
| EDGAR on | holdout | B&H vol-target | 1.24 | 2.63 | 46.3 | 9.8 | 73.8 |
| EDGAR + xalpha | design | AgenticTrader | 1.46 | 3.58 | 89.3 | 10.4 | 61.6 |
| EDGAR + xalpha | design | Buy&Hold | 1.32 | 3.24 | 192.2 | 22.7 | 97.6 |
| EDGAR + xalpha | design | B&H vol-target | 1.49 | 3.65 | 92.8 | 9.8 | 79.2 |
| EDGAR + xalpha | holdout | AgenticTrader | 1.08 | 2.28 | 36.3 | 7.8 | 58.5 |
| EDGAR + xalpha | holdout | Buy&Hold | 1.06 | 2.24 | 86.6 | 20.8 | 97.6 |
| EDGAR + xalpha | holdout | B&H vol-target | 1.24 | 2.63 | 46.3 | 9.8 | 73.8 |

noedgar: 122.1 s, errors 0, prompts bundle 5cf06b89f9264768, edgar False

edgar: 300.6 s, errors 0, prompts bundle 5cf06b89f9264768, edgar True

xalpha: 1007.7 s, errors 0, prompts bundle 5cf06b89f9264768, edgar True

With the real data the 15-sleeve portfolio's design Sharpe goes from 1.54 to 1.47 and its
holdout Sharpe from 1.16 to 1.09 — still above plain buy & hold (1.06) — with drawdowns of 10.2%
and 7.8% instead of 8.3% and 7.0%. ("Still above plain buy & hold" is retracted in v0.8: the
holdout portfolio is 0.80 against 0.86, desk − B&H -0.06 [-0.41, +0.30] p 0.748 by the paired
block bootstrap; see [portfolio view](#3-portfolio-view-15-equal-capital-sleeves-with-intervals)
and [the cash leg](#4-the-cash-leg).)

**Decision.** The data stays on by default. A desk that has point-in-time filings and
ignores them because they do not flatter its untuned rules would be optimising the
headline, not the desk, and the LLM desk needs the analysts to have something to read.
The *rules* that consume the data are not changed in v0.6: fitting the fundamentals
analyst's thresholds to make the real data help is a rule change under the protocol, to be
chosen on the core design period and judged on the extended universe and the reserve
period — and the extended-universe result above (a small, interval-clearing gain where the
rules never looked) is the reason to expect that work to be worth doing. Every published
number below is under the new default; the v0.5.1 EDGAR-off numbers above are the record.
(The "interval-clearing" wording is retracted in v0.8: under the corrected reconstruction the
extended-holdout gain is +0.03 [+0.01, +0.06] p 0.00 in a table that prints no BH flag, and
the all-60 cluster interval, +0.02 [-0.02, +0.05] p 0.39, covers zero; the data stays on for
the reasons above, not because of an interval.)

### The rule change: the cross-sectional alpha analyst

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

Re-checked under v0.8: design core -0.01 [-0.02, +0.00] p 0.36, holdout core 0.00
[-0.01, +0.02] p 0.60, holdout extended -0.00 [-0.01, +0.00] p 0.23, reserve extended -0.02
[-0.06, +0.01] p 0.20 — off by default stands
([re-checks](#7-every-earlier-decision-re-checked-under-the-v08-engine)).

`xalpha` z-scores the nine alphas across the instrument's peers on every date (peers: the
60-name universe filtered by asset class in this run, so every name is a member and the
cross-section is computed once per date), measures each alpha's cross-sectional IC over the
900-day window, keeps only alphas whose IC t-statistic is at least 2 in magnitude — the
same gate as the time-series alpha analyst — and abstains when none qualifies. It was added
to the default analyst set on top of EDGAR; the difference below is therefore the analyst
alone:

| universe | period | n | mean Sharpe diff | 95% CI | p | better on | mean MDD diff | mean exposure diff | mean trades diff |
|:--|:--|--:|--:|:--|--:|--:|--:|--:|--:|
| core | design | 15 | -0.008 | [-0.02, 0.00] | 0.13 | 5 / 15 | +0.18 | -0.1 | -1.9 |
| core | holdout | 15 | -0.004 | [-0.02, +0.01] | 0.54 | 8 / 15 | +0.01 | -0.0 | -0.7 |
| core | q1_2024 | 15 | +0.095 | [+0.01, +0.22] | 0.02 | 6 / 15 | -0.05 | +0.1 | +0.1 |
| core | reserve | 15 | +0.009 | [-0.01, +0.04] | 0.57 | 3 / 15 | -0.01 | -0.5 | -0.1 |
| extended | design | 36 | +0.003 | [-0.01, +0.01] | 0.58 | 18 / 36 | +0.01 | +0.3 | -2.5 |
| extended | holdout | 36 | -0.007 | [-0.02, 0.00] | 0.14 | 13 / 36 | +0.09 | +0.3 | -1.4 |
| extended | q1_2024 | 36 | -0.016 | [-0.09, +0.03] | 0.75 | 9 / 36 | +0.03 | +0.3 | +0.2 |
| extended | reserve | 36 | -0.007 | [-0.02, +0.01] | 0.34 | 7 / 36 | +0.04 | +0.5 | -0.0 |
| extended-macro | design | 9 | +0.000 | [-0.02, +0.01] | 0.93 | 5 / 9 | +0.38 | +1.2 | -3.1 |
| extended-macro | holdout | 9 | -0.008 | [-0.02, +0.01] | 0.26 | 2 / 9 | +0.57 | +1.3 | -1.0 |
| extended-macro | q1_2024 | 9 | -0.039 | [-0.15, +0.03] | 0.58 | 5 / 9 | +0.03 | +0.8 | +0.3 |
| extended-macro | reserve | 9 | -0.127 | [-0.29, +0.01] | 0.08 | 3 / 9 | +0.21 | +2.4 | +0.4 |
| extended45 | design | 45 | +0.002 | [-0.01, +0.01] | 0.61 | 23 / 45 | +0.08 | +0.5 | -2.6 |
| extended45 | holdout | 45 | -0.007 | [-0.01, 0.00] | 0.08 | 15 / 45 | +0.19 | +0.5 | -1.3 |
| extended45 | q1_2024 | 45 | -0.021 | [-0.09, +0.02] | 0.56 | 14 / 45 | +0.03 | +0.4 | +0.2 |
| extended45 | reserve | 45 | -0.031 | [-0.07, 0.00] | 0.05 | 10 / 45 | +0.08 | +0.9 | +0.1 |

**Reading.** On the core design period — the only slice a choice may be made on — the
analyst changed the desk's per-instrument Sharpe by -0.01 [-0.02, 0.00],
better on 5 of 15 names, with -0.10 points of exposure, +0.18 points of drawdown and
-1.87 trades per name. The unseen slices say: core holdout 0.00 [-0.02, +0.01],
extended design 0.00 [-0.01, +0.01], extended holdout -0.01
[-0.01, 0.00] (better on 15 of 45), reserve +0.01 on the core and
-0.03 on the extended names. The design-period interval does not clear zero, so under the protocol the analyst is **off by default** — available as `analysts=[..., "xalpha"]`, exactly like the time-series alpha analyst, and measured rather than assumed.
The reason the numbers are so close to zero is that the gate almost never opens: sampled every 60 bars over the design period on the 15 core names (390 decisions), the analyst spoke on 2.6% of them — 3.8% of the equity decisions, never on FX — with a mean |signal| of 0.30 when it did.
Cross-sectionally, over a 900-day window, no alpha in the library clears |t(IC)| ≥ 2 on most
dates; the desk is not being told anything it did not know. Its cost is real either way: one
cross-section per decision date, cached across the names that share it.

### Cross-instrument bootstrap: is any edge real across the universe?

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

These tables used the plain instrument bootstrap (v0.8 labels it `scheme=instruments`) and
carry no BH flag; the v0.7 "stratified" variant is retracted (CHANGELOG v0.8.0). The v0.8
paired tables carry `scheme`, `groups`, `p` and the BH `significant` column.

The agent's Sharpe minus each baseline's, per instrument, bootstrapped across instruments
(10,000 resamples; two-sided p):

| configuration | universe | period | baseline | n | mean diff | 95% CI | p | wins |
|:--|:--|:--|:--|--:|--:|:--|--:|--:|
| v0.5.1 rules, EDGAR off (the v0.5.1 record) | core | design | Buy&Hold | 15 | +0.073 | [-0.06, +0.20] | 0.27 | 10 / 15 |
| v0.5.1 rules, EDGAR off (the v0.5.1 record) | core | design | B&H vol-target | 15 | +0.026 | [-0.12, +0.18] | 0.75 | 6 / 15 |
| v0.5.1 rules, EDGAR off (the v0.5.1 record) | core | holdout | Buy&Hold | 15 | -0.089 | [-0.21, +0.03] | 0.16 | 5 / 15 |
| v0.5.1 rules, EDGAR off (the v0.5.1 record) | core | holdout | B&H vol-target | 15 | -0.099 | [-0.21, +0.01] | 0.07 | 4 / 15 |
| v0.5.1 rules, EDGAR off (the v0.5.1 record) | core | q1_2024 | Buy&Hold | 15 | +0.127 | [-0.55, +0.96] | 0.82 | 5 / 15 |
| v0.5.1 rules, EDGAR off (the v0.5.1 record) | core | q1_2024 | B&H vol-target | 15 | +0.085 | [-0.59, +0.93] | 0.90 | 3 / 15 |
| v0.5.1 rules, EDGAR off (the v0.5.1 record) | core | reserve | Buy&Hold | 15 | -0.135 | [-0.33, +0.10] | 0.22 | 3 / 15 |
| v0.5.1 rules, EDGAR off (the v0.5.1 record) | core | reserve | B&H vol-target | 15 | -0.130 | [-0.39, +0.15] | 0.34 | 5 / 15 |
| v0.5.1 rules, EDGAR off (the v0.5.1 record) | extended45 | design | Buy&Hold | 45 | -0.044 | [-0.11, +0.02] | 0.18 | 18 / 45 |
| v0.5.1 rules, EDGAR off (the v0.5.1 record) | extended45 | design | B&H vol-target | 45 | -0.098 | [-0.16, -0.04] | 0.00 | 10 / 45 |
| v0.5.1 rules, EDGAR off (the v0.5.1 record) | extended45 | holdout | Buy&Hold | 45 | -0.079 | [-0.14, -0.02] | 0.01 | 15 / 45 |
| v0.5.1 rules, EDGAR off (the v0.5.1 record) | extended45 | holdout | B&H vol-target | 45 | -0.051 | [-0.11, +0.01] | 0.08 | 14 / 45 |
| v0.5.1 rules, EDGAR off (the v0.5.1 record) | extended45 | q1_2024 | Buy&Hold | 45 | -0.324 | [-0.70, -0.04] | 0.02 | 9 / 45 |
| v0.5.1 rules, EDGAR off (the v0.5.1 record) | extended45 | q1_2024 | B&H vol-target | 45 | -0.322 | [-0.69, -0.05] | 0.02 | 13 / 45 |
| v0.5.1 rules, EDGAR off (the v0.5.1 record) | extended45 | reserve | Buy&Hold | 45 | +0.107 | [-0.10, +0.36] | 0.37 | 16 / 45 |
| v0.5.1 rules, EDGAR off (the v0.5.1 record) | extended45 | reserve | B&H vol-target | 45 | +0.097 | [-0.12, +0.35] | 0.43 | 16 / 45 |
| v0.5.1 rules + EDGAR fundamentals and news | core | design | Buy&Hold | 15 | +0.076 | [-0.04, +0.19] | 0.19 | 11 / 15 |
| v0.5.1 rules + EDGAR fundamentals and news | core | design | B&H vol-target | 15 | +0.029 | [-0.10, +0.17] | 0.69 | 7 / 15 |
| v0.5.1 rules + EDGAR fundamentals and news | core | holdout | Buy&Hold | 15 | -0.083 | [-0.19, +0.02] | 0.12 | 5 / 15 |
| v0.5.1 rules + EDGAR fundamentals and news | core | holdout | B&H vol-target | 15 | -0.093 | [-0.20, +0.01] | 0.08 | 5 / 15 |
| v0.5.1 rules + EDGAR fundamentals and news | core | q1_2024 | Buy&Hold | 15 | +0.216 | [-0.43, +1.02] | 0.62 | 5 / 15 |
| v0.5.1 rules + EDGAR fundamentals and news | core | q1_2024 | B&H vol-target | 15 | +0.174 | [-0.48, +1.00] | 0.73 | 3 / 15 |
| v0.5.1 rules + EDGAR fundamentals and news | core | reserve | Buy&Hold | 15 | -0.005 | [-0.17, +0.21] | 0.90 | 6 / 15 |
| v0.5.1 rules + EDGAR fundamentals and news | core | reserve | B&H vol-target | 15 | +0.000 | [-0.20, +0.23] | 0.95 | 7 / 15 |
| v0.5.1 rules + EDGAR fundamentals and news | extended45 | design | Buy&Hold | 45 | -0.032 | [-0.10, +0.03] | 0.32 | 21 / 45 |
| v0.5.1 rules + EDGAR fundamentals and news | extended45 | design | B&H vol-target | 45 | -0.087 | [-0.15, -0.03] | 0.00 | 9 / 45 |
| v0.5.1 rules + EDGAR fundamentals and news | extended45 | holdout | Buy&Hold | 45 | -0.043 | [-0.10, +0.01] | 0.13 | 14 / 45 |
| v0.5.1 rules + EDGAR fundamentals and news | extended45 | holdout | B&H vol-target | 45 | -0.015 | [-0.07, +0.04] | 0.57 | 19 / 45 |
| v0.5.1 rules + EDGAR fundamentals and news | extended45 | q1_2024 | Buy&Hold | 45 | -0.272 | [-0.64, 0.00] | 0.05 | 11 / 45 |
| v0.5.1 rules + EDGAR fundamentals and news | extended45 | q1_2024 | B&H vol-target | 45 | -0.270 | [-0.64, 0.00] | 0.05 | 15 / 45 |
| v0.5.1 rules + EDGAR fundamentals and news | extended45 | reserve | Buy&Hold | 45 | +0.092 | [-0.11, +0.34] | 0.43 | 16 / 45 |
| v0.5.1 rules + EDGAR fundamentals and news | extended45 | reserve | B&H vol-target | 45 | +0.081 | [-0.12, +0.33] | 0.50 | 16 / 45 |
| EDGAR + cross-sectional alpha analyst | core | design | Buy&Hold | 15 | +0.068 | [-0.05, +0.18] | 0.23 | 11 / 15 |
| EDGAR + cross-sectional alpha analyst | core | design | B&H vol-target | 15 | +0.021 | [-0.10, +0.16] | 0.78 | 6 / 15 |
| EDGAR + cross-sectional alpha analyst | core | holdout | Buy&Hold | 15 | -0.087 | [-0.20, +0.02] | 0.11 | 5 / 15 |
| EDGAR + cross-sectional alpha analyst | core | holdout | B&H vol-target | 15 | -0.097 | [-0.21, +0.01] | 0.08 | 6 / 15 |
| EDGAR + cross-sectional alpha analyst | core | q1_2024 | Buy&Hold | 15 | +0.311 | [-0.31, +1.12] | 0.42 | 5 / 15 |
| EDGAR + cross-sectional alpha analyst | core | q1_2024 | B&H vol-target | 15 | +0.269 | [-0.35, +1.09] | 0.52 | 3 / 15 |
| EDGAR + cross-sectional alpha analyst | core | reserve | Buy&Hold | 15 | +0.004 | [-0.17, +0.22] | 0.97 | 6 / 15 |
| EDGAR + cross-sectional alpha analyst | core | reserve | B&H vol-target | 15 | +0.009 | [-0.20, +0.24] | 0.99 | 8 / 15 |
| EDGAR + cross-sectional alpha analyst | extended45 | design | Buy&Hold | 45 | -0.030 | [-0.10, +0.03] | 0.34 | 22 / 45 |
| EDGAR + cross-sectional alpha analyst | extended45 | design | B&H vol-target | 45 | -0.085 | [-0.15, -0.03] | 0.00 | 10 / 45 |
| EDGAR + cross-sectional alpha analyst | extended45 | holdout | Buy&Hold | 45 | -0.050 | [-0.10, 0.00] | 0.06 | 13 / 45 |
| EDGAR + cross-sectional alpha analyst | extended45 | holdout | B&H vol-target | 45 | -0.022 | [-0.07, +0.03] | 0.39 | 21 / 45 |
| EDGAR + cross-sectional alpha analyst | extended45 | q1_2024 | Buy&Hold | 45 | -0.293 | [-0.66, 0.00] | 0.05 | 12 / 45 |
| EDGAR + cross-sectional alpha analyst | extended45 | q1_2024 | B&H vol-target | 45 | -0.291 | [-0.66, -0.01] | 0.05 | 15 / 45 |
| EDGAR + cross-sectional alpha analyst | extended45 | reserve | Buy&Hold | 45 | +0.061 | [-0.12, +0.30] | 0.62 | 16 / 45 |
| EDGAR + cross-sectional alpha analyst | extended45 | reserve | B&H vol-target | 45 | +0.050 | [-0.13, +0.29] | 0.70 | 16 / 45 |

**Reading.** Against plain buy & hold the desk's per-instrument Sharpe edge is not
distinguishable from zero on any core slice — the widest intervals are Q1 2024's, a single
quarter on 15 names — and on the extended universe the sign is negative with intervals that
touch or exclude zero on the holdout. Against the vol-targeted control the desk is behind on
the extended design period (interval excludes zero) and level elsewhere. This is the
statistical form of what the tables have said since v0.3: the desk's per-instrument Sharpe
is buy & hold's, give or take the noise of 15 or 45 names; what it changes is the drawdown.
(v0.8, with BH: on the extended holdout desk − B&H -0.07 [-0.12, -0.02] p 0.01 is
BH-significant and desk − vol-target -0.03 [-0.09, +0.02] p 0.19 is not — the deficit against
buy & hold is no longer noise on the 45 extended names no rule was tuned on.)

### The published tables under the v0.6 defaults

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

Agent rows per configuration (means over instruments; the baselines do not depend on the
configuration):

| configuration | period | n | mean Sharpe | median Sharpe | mean CR % | mean MDD % | mean Exp % | mean trades | beats B&H | beats vol-target |
|:--|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| v0.5.1 rules, EDGAR off (the v0.5.1 record) | design | 15 | 0.70 | 0.67 | 107.0 | 15.7 | 60.6 | 98.9 | 10 / 15 | 6 / 15 |
| v0.5.1 rules, EDGAR off (the v0.5.1 record) | holdout | 15 | 0.46 | 0.44 | 33.3 | 16.9 | 55.8 | 78.5 | 5 / 15 | 4 / 15 |
| v0.5.1 rules, EDGAR off (the v0.5.1 record) | q1_2024 | 15 | 2.02 | 2.93 | 8.5 | 3.5 | 67.1 | 3.9 | 5 / 15 | 3 / 15 |
| v0.5.1 rules, EDGAR off (the v0.5.1 record) | reserve | 15 | 0.88 | 0.81 | 3.3 | 4.6 | 61.9 | 3.9 | 3 / 15 | 5 / 15 |
| v0.5.1 rules + EDGAR fundamentals and news | design | 15 | 0.70 | 0.74 | 115.1 | 18.0 | 63.2 | 84.1 | 11 / 15 | 7 / 15 |
| v0.5.1 rules + EDGAR fundamentals and news | holdout | 15 | 0.46 | 0.45 | 36.4 | 18.9 | 59.9 | 66.0 | 5 / 15 | 5 / 15 |
| v0.5.1 rules + EDGAR fundamentals and news | q1_2024 | 15 | 2.11 | 2.93 | 8.8 | 3.7 | 69.1 | 3.6 | 5 / 15 | 3 / 15 |
| v0.5.1 rules + EDGAR fundamentals and news | reserve | 15 | 1.01 | 0.81 | 4.2 | 4.7 | 64.7 | 3.2 | 6 / 15 | 7 / 15 |
| EDGAR + cross-sectional alpha analyst | design | 15 | 0.69 | 0.71 | 115.6 | 18.2 | 63.1 | 82.2 | 11 / 15 | 6 / 15 |
| EDGAR + cross-sectional alpha analyst | holdout | 15 | 0.46 | 0.46 | 36.4 | 18.9 | 59.9 | 65.3 | 5 / 15 | 6 / 15 |
| EDGAR + cross-sectional alpha analyst | q1_2024 | 15 | 2.20 | 2.93 | 8.9 | 3.6 | 69.2 | 3.7 | 5 / 15 | 3 / 15 |
| EDGAR + cross-sectional alpha analyst | reserve | 15 | 1.02 | 0.82 | 4.3 | 4.7 | 64.3 | 3.1 | 6 / 15 | 8 / 15 |
| Buy&Hold | design | 15 | 0.63 | 0.76 | 413.4 | 33.7 | 100.0 | 1.0 | — | — |
| Buy&Hold | holdout | 15 | 0.55 | 0.56 | 91.9 | 32.4 | 100.0 | 1.0 | — | — |
| Buy&Hold | q1_2024 | 15 | 1.89 | 2.90 | 14.0 | 5.3 | 100.0 | 1.0 | — | — |
| Buy&Hold | reserve | 15 | 1.01 | 1.04 | 7.8 | 7.9 | 100.0 | 1.0 | — | — |
| B&H vol-target | design | 15 | 0.67 | 0.75 | 123.1 | 21.1 | 80.9 | 760.0 | — | — |
| B&H vol-target | holdout | 15 | 0.56 | 0.62 | 46.3 | 20.1 | 75.4 | 654.4 | — | — |
| B&H vol-target | q1_2024 | 15 | 1.94 | 3.00 | 8.2 | 4.3 | 83.7 | 26.3 | — | — |
| B&H vol-target | reserve | 15 | 1.01 | 1.04 | 4.1 | 4.6 | 71.2 | 35.9 | — | — |

| configuration | period | n | mean Sharpe | median Sharpe | mean CR % | mean MDD % | mean Exp % | mean trades | beats B&H | beats vol-target |
|:--|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| v0.5.1 rules, EDGAR off (the v0.5.1 record) | design | 45 | 0.51 | 0.56 | 47.8 | 19.0 | 63.4 | 96.1 | 18 / 45 | 10 / 45 |
| v0.5.1 rules, EDGAR off (the v0.5.1 record) | holdout | 45 | 0.42 | 0.43 | 26.7 | 17.7 | 61.9 | 76.7 | 15 / 45 | 14 / 45 |
| v0.5.1 rules, EDGAR off (the v0.5.1 record) | q1_2024 | 45 | 1.79 | 2.40 | 4.8 | 3.6 | 72.4 | 3.4 | 9 / 45 | 13 / 45 |
| v0.5.1 rules, EDGAR off (the v0.5.1 record) | reserve | 45 | 0.12 | -0.01 | 1.1 | 4.7 | 61.9 | 4.3 | 16 / 45 | 16 / 45 |
| v0.5.1 rules + EDGAR fundamentals and news | design | 45 | 0.52 | 0.57 | 53.8 | 19.4 | 65.1 | 87.3 | 21 / 45 | 9 / 45 |
| v0.5.1 rules + EDGAR fundamentals and news | holdout | 45 | 0.45 | 0.48 | 31.2 | 17.6 | 64.6 | 68.3 | 14 / 45 | 19 / 45 |
| v0.5.1 rules + EDGAR fundamentals and news | q1_2024 | 45 | 1.84 | 2.40 | 4.9 | 3.7 | 73.6 | 3.2 | 11 / 45 | 15 / 45 |
| v0.5.1 rules + EDGAR fundamentals and news | reserve | 45 | 0.11 | 0.10 | 1.0 | 4.8 | 63.7 | 3.9 | 16 / 45 | 16 / 45 |
| EDGAR + cross-sectional alpha analyst | design | 45 | 0.53 | 0.54 | 54.3 | 19.5 | 65.5 | 84.7 | 22 / 45 | 10 / 45 |
| EDGAR + cross-sectional alpha analyst | holdout | 45 | 0.45 | 0.50 | 31.2 | 17.8 | 65.1 | 67.0 | 13 / 45 | 21 / 45 |
| EDGAR + cross-sectional alpha analyst | q1_2024 | 45 | 1.82 | 2.40 | 4.9 | 3.7 | 74.0 | 3.4 | 12 / 45 | 15 / 45 |
| EDGAR + cross-sectional alpha analyst | reserve | 45 | 0.07 | 0.10 | 1.0 | 4.9 | 64.7 | 4.0 | 16 / 45 | 16 / 45 |
| Buy&Hold | design | 45 | 0.56 | 0.60 | 103.6 | 33.1 | 100.0 | 1.0 | — | — |
| Buy&Hold | holdout | 45 | 0.50 | 0.57 | 62.3 | 27.2 | 100.0 | 1.0 | — | — |
| Buy&Hold | q1_2024 | 45 | 2.11 | 2.47 | 6.8 | 4.9 | 100.0 | 1.0 | — | — |
| Buy&Hold | reserve | 45 | 0.01 | 0.07 | 1.7 | 8.1 | 100.0 | 1.0 | — | — |
| B&H vol-target | design | 45 | 0.61 | 0.64 | 71.4 | 21.4 | 85.7 | 669.4 | — | — |
| B&H vol-target | holdout | 45 | 0.47 | 0.50 | 36.9 | 21.1 | 82.6 | 607.8 | — | — |
| B&H vol-target | q1_2024 | 45 | 2.11 | 2.34 | 6.1 | 4.1 | 90.8 | 24.0 | — | — |
| B&H vol-target | reserve | 45 | 0.02 | 0.11 | 0.8 | 5.7 | 79.0 | 35.1 | — | — |

## The LLM desk (v0.5.1): the first measured result

> *Measured under the v0.5.1 engine (the v0.7-and-earlier engine: constant weight between decisions, no cash leg, static-table FX fallback); not re-derived under v0.8 — this is still the only LLM measurement, and the multi-year harness has not been executed. See [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured) for what changed in the engine.*

Everything above is the rule-based desk. This is the first run of the same desk with Claude
in every reasoning role, on the same bars, cadence, costs and baselines as a rule-based
control run alongside it. It is deliberately small — a lean run to establish the cost and
the method before anything larger — and a single quarter on five stocks is a weak test: it
can show what the model *does*, not whether it has an edge.

**Setup.** AAPL, NVDA, MSFT, META, GOOGL; Q1 2024 (2024-01-02 → 2024-03-28); a decision every
10 bars (6 per stock, 30 in all); one debate round; `claude-opus-5` at medium effort for the
reasoning roles and `claude-haiku-4-5` for the analysts; prompts **anonymised** (no ticker,
no dates, no price level, so the model cannot recall the quarter); hard cap 400 calls;
three backtests in parallel sharing one budget. The rule-based control is the identical
command without `--llm anthropic`. News, fundamentals and social analysts abstained on
both (no point-in-time data), so the technical analyst was the only model-read analyst.

**Usage.** 271 calls (240 Opus, 31 Haiku), 0 errors, 0 refusals, 0 budget refusals; every
one of the 211 agent outputs came from the model (no rule fallback was needed). 366k input
and 103k output tokens; **$4.12** at list prices (Opus $4.05, Haiku $0.07); 639 s wall clock.

| symbol | LLM Sharpe | rules Sharpe | B&H Sharpe | vol-target B&H | LLM CR % | rules CR % | B&H CR % | LLM MDD % | rules MDD % | B&H MDD % | LLM exposure % | rules exposure % | LLM trades | rules trades |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| AAPL | -1.55 | -1.98 | -1.55 | -1.58 | -0.89 | -3.83 | -7.53 | 1.68 | 6.81 | 13.30 | 12.0 | 40.7 | 1 | 4 |
| NVDA | 5.46 | 5.51 | 5.46 | 5.78 | 12.52 | 41.29 | 87.56 | 1.60 | 5.08 | 8.70 | 18.0 | 51.5 | 1 | 2 |
| MSFT | 3.09 | 3.06 | 2.90 | 3.08 | 3.44 | 11.35 | 13.63 | 1.06 | 3.37 | 4.21 | 23.3 | 78.7 | 2 | 2 |
| META | 2.81 | 3.13 | 3.10 | 3.04 | 17.37 | 23.88 | 40.34 | 2.36 | 2.74 | 5.58 | 37.0 | 53.6 | 6 | 3 |
| GOOGL | 1.14 | 1.21 | 1.46 | 1.35 | 2.01 | 5.01 | 9.21 | 4.15 | 10.06 | 14.40 | 23.7 | 59.5 | 2 | 3 |

| strategy (means over the 5 stocks) | mean Sharpe | median Sharpe | mean CR % | mean MDD % | mean exposure % | mean trades |
|:--|--:|--:|--:|--:|--:|--:|
| **LLM desk** (Opus medium, 1 round, anonymised) | **2.19** | 2.81 | 6.89 | **2.17** | 22.8 | 2.4 |
| rule-based desk (same cadence) | 2.19 | 3.06 | 15.54 | 5.61 | 56.8 | 2.8 |
| Buy & hold | 2.27 | 2.90 | 28.64 | 9.24 | 100.0 | 1.0 |
| B&H vol-target | 2.33 | 3.04 | 13.31 | 6.60 | 62.4 | 54.8 |

**What it shows.**

- **No Sharpe edge over the rules: 2.19 against 2.19.** The model beat the rule-based desk on
  2 of 5 names and buy & hold on 1 of 5, all by margins that a single quarter cannot
  distinguish from zero.
- **The model is more conservative than the rules, consistently.** It held 23% average
  exposure against the rules' 57%, so its returns were less than half (6.9% against 15.5%)
  and its drawdowns less than half (2.2% against 5.6%) — on every one of the five names.
  Reading the transcripts, the portfolio manager repeatedly sized *down* from the trader's
  proposal citing the abstaining analysts ("the only live signal is a weak technical
  read"); that is the correct reading of the evidence it was given, and it is why the
  positions are small.
- **The governance layer is not the bottleneck.** Zero refusals, zero fallbacks, zero budget
  hits, zero errors: the anonymised prompts, the JSON contracts and the limits all worked
  end to end at $0.14 per decision.

**What it does not show.** Whether Claude adds value over the rules. That needs the design
and holdout periods (roughly 1,500 decisions per stock at this cadence, so tens of dollars
per name), the full analyst team with point-in-time news and fundamentals rather than a
technical-only desk, and more than one run per date to measure the model's own variance.
The harness for that exists (`--workers`, the dollar budget, anonymisation); the run is a
matter of spend, and the protocol above applies to it as to any other change.

Reproduce: `agentic-trader evaluate AAPL,NVDA,MSFT,META,GOOGL --data yahoo --periods q1_2024
--every 10 --rounds 1 --llm anthropic --deep-effort medium --max-llm-calls 400 --anonymize
--workers 3` and the same command without `--llm anthropic` for the control.

## The next rule change: what counts as unseen

No held-out data remains. The holdout has been seen since v0.3; the reserve period and the
extended universe were used to judge the v0.5.1 carry rule and the v0.6 EDGAR and
cross-sectional decisions; v0.8 re-measures every period under the corrected engine. The
next unseen data is the future.

What the protocol still fixes for the next change:

1. **Choose** on the core universe's design period only (`evaluate --universe core
   --periods design`), publish the full ablation, and register the variant in
   `evaluation.TRIALS` so the trial count in the selection statistics is read from the
   record.
2. **Report** the extended universe and the reserve period on every period
   (`--universe extended`, `--periods reserve` on both universes), including the parts that
   do not flatter the change — as *information*, not as unseen data. These slices have been
   consulted and are published here, so a change that flatters them may be fitted to them.
3. **The only bars no choice and no published number has touched are the ones after
   2026-09-25** (`PERIODS["reserve"]` is a fixed constant ending 2026-09-25; it was not moved
   for the 2026-09-28 re-measurement, and bars after it enter no published table until it is
   moved), and only until they are reported.
4. If the change alters what the desk trades (a new asset class, a new analyst input),
   the alpha-analyst rule applies: measure it, treat a result within about 0.1 of Sharpe on
   15 instruments (about 0.06 on 45) as noise, and read every paired table with its interval,
   p and BH flag.

## Holdout per instrument (core universe)

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

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

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

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

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

**"Beats plain buy & hold on Sharpe" is retracted.** Under v0.8 the holdout portfolio is 0.80
against 0.86 for buy & hold, desk − B&H -0.06 [-0.41, +0.30] p 0.748 (paired block bootstrap
over days, block 10), and trails the vol-targeted control, -0.19 [-0.53, +0.16] p 0.297; the
design period is 1.40 against 1.28 and 1.43, +0.12 [-0.16, +0.40] p 0.434 and -0.03
[-0.28, +0.23] p 0.898. The holdout drawdown is 7.80% against 20.43% (buy & hold) and 9.17%
(vol-target). See [portfolio view](#3-portfolio-view-15-equal-capital-sleeves-with-intervals)
and [the cash leg](#4-the-cash-leg).

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

## VaR coverage: is the desk's risk model calibrated?

> *Measured under the v0.7 engine (constant weight between decisions, no cash leg, per-instrument impact at whole-book capital, static-table FX fallback); superseded by the v0.8 re-measurement — see [v0.8](#v08-engine-and-protocol-corrections-and-every-number-re-measured).*

**What this section measures is the rolling historical VaR of the 15-sleeve portfolio's own
returns, at 120 and 250 days — not the desk's risk model.** The forecast the desk sizes on
(the 250-day historical VaR of each instrument's returns, `agents/risk.py`) was first tested
in v0.8, per instrument against next-day returns; both tests, labelled, are under
[VaR coverage, re-measured and labelled](#8-var-coverage-re-measured-and-labelled). The
conclusion at the end of this section is retracted there.

Every decision scales down when its 95% historical VaR breaches a configured cap
(`max_var_95`), and v0.7 extends that to a book-level cap across sleeves
(`max_book_var_95`, off by default and off in every published run, so its coverage is
untested -- see the book-VaR bullet in [Limitations](#limitations)). A cap is only useful if
the VaR forecast behind it is honest:
a 95% VaR should be breached on roughly 5% of days, and those breaches should not cluster
together (clustering means the model is slow to react, not just imprecise on average).

Two standard tests check this, run against the same 15-sleeve equal-capital core portfolio's
holdout-period daily returns used throughout this page (`agentic-trader stats --var-backtest`,
which wraps `rolling_var_forecast` + `var_backtest` -- see
[Reproducing](#reproducing) for the exact command):

- **Kupiec (1995) unconditional coverage**: does the breach rate match the target rate?
- **Christoffersen (1998) independence**: are breaches spread out in time, or do they cluster?

Both are likelihood-ratio tests against a rolling, walk-forward VaR forecast (each day's
forecast uses only the trailing window before it, never the day itself or later) at two
window lengths:

| Window | n | breaches | breach rate | expected | Kupiec LR | Kupiec p | Christoffersen LR | Christoffersen p | conditional coverage p |
|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 120 days | 1048 | 60 | 5.73% | 5.00% | 1.111 | 0.292 | 1.801 | 0.180 | 0.233 |
| 250 days | 918 | 41 | 4.47% | 5.00% | 0.570 | 0.450 | 2.158 | 0.142 | 0.256 |

Neither test rejects at any conventional significance level, at either window length: the
breach rate is statistically indistinguishable from 5% (Kupiec), and breaches are
statistically indistinguishable from independent across time (Christoffersen). The v0.7
sentence that followed, "the desk's own historical-VaR risk model is well-calibrated on this
data", is **retracted**: a rolling quantile of the book's own realised returns is not the
model the desk sizes on. Under v0.8 the same portfolio-returns test gives 65 breaches in 1048
days at 120 days (rate 0.0620; Kupiec p 0.0847, Christoffersen p 0.1488, conditional
coverage p 0.0798 — not rejected at 5%, but close) and 42 in 918 at 250 days (0.0458;
0.5493, 0.1650, 0.3188), while the desk's own per-instrument forecast is rejected by Kupiec
on 2 of 15 core instruments and by Christoffersen independence on 6 of 15
([v0.8 tables](#8-var-coverage-re-measured-and-labelled)).

## v0.8: engine and protocol corrections, and every number re-measured

A tier-1 review of v0.7.0 produced 91 findings; the engine, data and statistics changes
made for them ([CHANGELOG v0.8.0](../../CHANGELOG.md#retracted)) move every backtest-derived
number, so nothing from v0.7 or earlier is carried forward. Every table in this section is
pasted from `results/v08/tables.md`, which `scripts/render_v08_tables.py` renders from the
files `scripts/measure_v08.py` wrote (real prices, C++ backend, EDGAR on unless the table
says otherwise, measured 2026-09-28; provenance under
[reproducing](#11-reproducing-the-v08-numbers)).

**Conventions.** Universe slices: core (15) = 10 equities + 5 FX pairs; extended (45) = 26
sector equities + 9 macro ETFs (asset class `equity`) + 10 FX crosses; all 60. Summary tables
report the median Sharpe across instruments and means of the other columns; the v0.3
tables' `mean Sharpe` column is not printed. Paired tables report the mean difference across
instruments with a 95% bootstrap interval (10,000 resamples, pairs kept together), a
two-sided p, a `wins` count and — where the table has the column — the Benjamini–Hochberg
flag `significant`, computed on the unrounded p across the table's rows. `wins` counts the
instruments where the desk's value is the *larger*, whatever the metric: in a Sharpe or
Calmar table that is a win, in an MDD% table it is the larger drawdown (so a `wins` of `0` on
the design row against buy & hold in the core MDD% table means the desk's drawdown was never
the larger). Bootstrap scheme: `instruments` (plain instrument resampling) on the core and extended
universes, which have fewer than 5 `asset_class:universe` groups; `clusters` (two stages:
groups drawn with replacement, then instruments within each drawn group) on all 60, which has
5 groups — the v0.7 "stratified" scheme is retracted. Sharpe and Sortino are on returns in
excess of the credited cash rate (FRED DTB3, one-day lag); CR, AR, MDD and Calmar are total
return. An interval printed as [0.00, x] or [-0.00, x] is never called "excluding zero".

### 1. What changed and why

- **Engine** ([CHANGELOG → Engine](../../CHANGELOG.md#engine)): constant units between
  decisions with post-cost sizing (v0.7 held the *weight* constant, a free daily rebalance
  whose turnover was never paid for); a ruin floor; the desk is told its true position after a
  stop, take-profit or ruin (v0.7 told it the pre-stop position and bought it back); a gap
  through the take-profit fills at the open; impact scaled by the equity actually traded;
  sleeves pay impact at the sleeve's capital; a cash leg, with Sharpe on excess returns.
- **Data** ([CHANGELOG → Data](../../CHANGELOG.md#data)): EDGAR quarters reconstructed per
  concept and per reporting basis, with recency and share-class guards; one FX rate resolver
  with no static fallback (FRED as known on the date; Norway's policy rate added, Sweden has
  no series); no partial Yahoo bar.
- **Statistics** ([CHANGELOG → Statistics](../../CHANGELOG.md#statistics)): the two-stage
  cluster bootstrap replaces the v0.7 stratified one (retracted: it could only narrow the
  intervals); `t(IC)` accounts for overlapping forward returns (about 3.16 times smaller at
  the analysts' horizon of 10); Benjamini–Hochberg on the unrounded p; block-bootstrap
  intervals for portfolio Sharpe differences; a trials registry of 26 variants.
- **Analysts** ([CHANGELOG → Agents and LLM](../../CHANGELOG.md#agents-and-llm)): no
  fabricated sector P/E on real data; the alpha analyst's significance gate is corrected by
  the overlap-aware `t(IC)`, so it admits far fewer alphas (on 200 seeded random walks it
  speaks on about a fifth of pure-noise histories,
  `tests/test_v08_alpha.py::test_alpha_analyst_gate_is_a_five_percent_test_on_pure_noise`).
- **What moved and what did not.** Numbers produced by the synthetic provider are unchanged
  by the cash leg (its rate is the constant 0 there); every real-data number moved. A v0.7
  number set beside a v0.8 number is a difference between two records measured on two
  engines, not a measured effect — except where this section measures one thing on one
  engine (the cash leg on against off, [part 4](#4-the-cash-leg)).

### 2. Headline re-measurement (`eval_main.json`)

All 60 instruments over the four periods, the v0.8 defaults (v0.5.1 rules, EDGAR on, cash
leg on). Core universe first, then the extended universe, then the paired Sharpe tables with
the scheme, groups, p and BH columns.

#### summary: core (15), design

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| design | AgenticTrader | 15 | 0.67 | 118.18 | 17.59 | 12.22 | 63.31 |
| design | B&H vol-target | 15 | 0.69 | 128.28 | 20.17 | 13.60 | 80.51 |
| design | Buy&Hold | 15 | 0.73 | 415.17 | 32.83 | 21.81 | 99.10 |
| design | KDJ+RSI | 15 | 0.54 | 75.97 | 27.23 | 16.21 | 54.24 |
| design | MACD | 15 | 0.54 | 95.79 | 24.95 | 15.04 | 67.80 |
| design | SMA(20/50) | 15 | 0.64 | 172.49 | 23.14 | 16.67 | 78.78 |
| design | ZMR | 15 | 0.41 | 47.07 | 27.75 | 15.56 | 44.42 |

#### summary: core (15), holdout

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| holdout | AgenticTrader | 15 | 0.30 | 49.52 | 17.40 | 12.82 | 60.51 |
| holdout | B&H vol-target | 15 | 0.52 | 60.63 | 18.98 | 14.12 | 73.67 |
| holdout | Buy&Hold | 15 | 0.51 | 98.41 | 31.64 | 23.40 | 97.39 |
| holdout | KDJ+RSI | 15 | 0.44 | 54.53 | 23.93 | 17.50 | 60.70 |
| holdout | MACD | 15 | 0.19 | 32.78 | 27.53 | 17.19 | 66.59 |
| holdout | SMA(20/50) | 15 | 0.36 | 52.12 | 25.04 | 17.20 | 72.99 |
| holdout | ZMR | 15 | 0.22 | 37.62 | 21.72 | 16.01 | 49.57 |

#### summary: core (15), q1_2024

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| q1_2024 | AgenticTrader | 15 | 2.79 | 9.27 | 3.47 | 12.36 | 69.27 |
| q1_2024 | B&H vol-target | 15 | 2.81 | 8.89 | 4.12 | 13.44 | 83.51 |
| q1_2024 | Buy&Hold | 15 | 2.62 | 14.37 | 5.22 | 18.59 | 99.77 |
| q1_2024 | KDJ+RSI | 15 | 0.09 | 3.68 | 2.96 | 6.89 | 50.23 |
| q1_2024 | MACD | 15 | 0.72 | 7.14 | 4.62 | 14.67 | 67.54 |
| q1_2024 | SMA(20/50) | 15 | 0.37 | 12.98 | 4.28 | 16.96 | 88.27 |
| q1_2024 | ZMR | 15 | 0.00 | 2.20 | 2.29 | 5.63 | 35.94 |

#### summary: core (15), reserve

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| reserve | AgenticTrader | 15 | 0.81 | 4.67 | 4.58 | 12.99 | 64.95 |
| reserve | B&H vol-target | 15 | 1.05 | 4.72 | 4.42 | 13.05 | 71.07 |
| reserve | Buy&Hold | 15 | 1.05 | 8.12 | 7.76 | 22.75 | 99.83 |
| reserve | KDJ+RSI | 15 | 1.76 | 7.70 | 4.81 | 15.37 | 65.72 |
| reserve | MACD | 15 | 1.03 | 2.92 | 6.96 | 16.93 | 66.32 |
| reserve | SMA(20/50) | 15 | 0.22 | 1.47 | 6.25 | 15.80 | 77.46 |
| reserve | ZMR | 15 | 1.03 | 4.11 | 3.55 | 11.54 | 44.49 |

#### head to head: core (15)

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

#### summary: extended (45), design

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| design | AgenticTrader | 45 | 0.51 | 57.08 | 18.37 | 11.05 | 65.34 |
| design | B&H vol-target | 45 | 0.58 | 74.13 | 20.77 | 13.17 | 85.23 |
| design | Buy&Hold | 45 | 0.55 | 104.91 | 32.58 | 19.86 | 99.16 |
| design | KDJ+RSI | 45 | 0.41 | 43.42 | 28.85 | 15.02 | 49.52 |
| design | MACD | 45 | 0.40 | 50.02 | 21.07 | 13.30 | 61.93 |
| design | SMA(20/50) | 45 | 0.51 | 57.64 | 24.00 | 13.73 | 72.31 |
| design | ZMR | 45 | 0.27 | 29.75 | 28.34 | 14.60 | 40.94 |

#### summary: extended (45), holdout

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| holdout | AgenticTrader | 45 | 0.25 | 42.00 | 15.46 | 11.65 | 64.73 |
| holdout | B&H vol-target | 45 | 0.27 | 46.35 | 19.79 | 13.88 | 81.32 |
| holdout | Buy&Hold | 45 | 0.39 | 66.81 | 26.39 | 19.19 | 97.87 |
| holdout | KDJ+RSI | 45 | 0.39 | 47.17 | 20.14 | 13.65 | 54.19 |
| holdout | MACD | 45 | 0.15 | 38.94 | 21.48 | 13.89 | 61.62 |
| holdout | SMA(20/50) | 45 | -0.09 | 27.63 | 24.39 | 14.55 | 67.00 |
| holdout | ZMR | 45 | 0.16 | 33.77 | 19.23 | 12.85 | 44.63 |

#### summary: extended (45), q1_2024

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| q1_2024 | AgenticTrader | 45 | 2.27 | 5.53 | 3.52 | 10.12 | 73.90 |
| q1_2024 | B&H vol-target | 45 | 2.32 | 6.55 | 4.02 | 11.93 | 90.64 |
| q1_2024 | Buy&Hold | 45 | 2.32 | 7.05 | 4.78 | 13.74 | 99.81 |
| q1_2024 | KDJ+RSI | 45 | 0.53 | 3.09 | 2.82 | 6.89 | 44.88 |
| q1_2024 | MACD | 45 | 0.38 | 2.90 | 3.91 | 10.07 | 59.83 |
| q1_2024 | SMA(20/50) | 45 | 0.80 | 5.16 | 4.39 | 11.76 | 82.57 |
| q1_2024 | ZMR | 45 | 0.68 | 2.28 | 2.21 | 5.89 | 34.09 |

#### summary: extended (45), reserve

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| reserve | AgenticTrader | 45 | -0.11 | 1.54 | 4.60 | 11.03 | 63.09 |
| reserve | B&H vol-target | 45 | -0.11 | 1.21 | 5.61 | 12.55 | 78.90 |
| reserve | Buy&Hold | 45 | -0.08 | 1.87 | 8.05 | 18.30 | 99.89 |
| reserve | KDJ+RSI | 45 | 0.42 | 3.51 | 4.73 | 12.10 | 59.86 |
| reserve | MACD | 45 | -0.82 | -0.76 | 6.07 | 12.84 | 55.92 |
| reserve | SMA(20/50) | 45 | -0.49 | 0.44 | 6.39 | 13.94 | 71.70 |
| reserve | ZMR | 45 | 0.81 | 2.51 | 3.99 | 10.23 | 46.71 |

#### head to head: extended (45)

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

#### paired Sharpe, agent minus baseline: core (15) (scheme column: clusters needs 5 groups)

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

#### paired Sharpe, agent minus baseline: extended (45) (scheme column: clusters needs 5 groups)

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

#### paired Sharpe, agent minus baseline: all 60 (scheme column: clusters needs 5 groups)

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

**Reading it.**

- **Per instrument, out of sample, the desk is below buy & hold on Sharpe, and below the
  volatility-targeted control too.** Core holdout median Sharpe 0.30 (desk) against 0.51
  (buy & hold) and 0.52 (vol-target); paired mean difference desk − B&H -0.10 [-0.21, -0.00]
  p 0.04 and desk − vol-target -0.11 [-0.21, -0.00] p 0.04, neither BH-significant. Extended
  holdout: 0.25 against 0.39 and 0.27; desk − B&H -0.07 [-0.12, -0.02] p 0.01,
  **BH-significant**; desk − vol-target -0.03 [-0.09, +0.02] p 0.19, not BH-significant. All
  60 (clusters): desk − B&H -0.08 [-0.15, -0.03] p 0.00, **BH-significant**; desk −
  vol-target -0.05 [-0.15, 0.00] p 0.07, not significant. Design period, core: 0.67 against
  0.73 and 0.69; desk − B&H +0.06 [-0.06, +0.17] p 0.29, not BH-significant. This is stronger
  than v0.7's "noise either way": on the names no rule was chosen on, the deficit against buy
  & hold clears the BH bar.
- **It beats the signal-flipping baselines on most slices**: holdout, all 60, desk − SMA
  +0.25 [+0.01, +0.43] p 0.04 (not BH-flagged); extended holdout desk − SMA +0.28
  [+0.16, +0.41] p 0.00, BH-significant; core holdout desk − MACD +0.21 [-0.01, +0.40] p 0.05,
  not significant. KDJ+RSI is the exception on the holdout (core -0.04 [-0.25, +0.20] p 0.68,
  not BH-significant).
- **The reserve period (three months) says little**: core desk median 0.81 against 1.05 for
  both controls, extended -0.11 against -0.08 (buy & hold) and -0.11 (vol-target); paired
  against the controls, core desk − B&H -0.06 [-0.21, +0.12] p 0.44 and extended +0.08
  [-0.14, +0.33] p 0.54, not significant.
- **Q1 2024 stays a weak test**: core medians 2.79 (desk), 2.81 (vol-target) and 2.62 (buy &
  hold) in one quarter of a rally.

### 3. Portfolio view: 15 equal-capital sleeves, with intervals

`run_portfolio_backtest` gives each core instrument 1/15 of the capital, runs every sleeve
with its own costs, carry, cash leg and position, and averages the daily returns
(`portfolio_design.json` / `portfolio_holdout.json` and their CSVs). New in v0.8: the
portfolio-level Sharpe difference with a paired block bootstrap over days (block 10,
`stats.paired_sharpe_block_bootstrap`), and the rebalance-phase sweep as the cadence noise
floor (`phase_sweep_holdout.json`). No BH flag applies to these: they are single comparisons
of two daily series, not a table of instruments.

#### portfolio: design

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 93.64 | 11.61 | 7.37 | 1.40 | 3.43 | 10.17 | 1.14 | 61.81 |
| Buy&Hold | 197.51 | 19.87 | 14.25 | 1.28 | 3.13 | 22.69 | 0.88 | 96.74 |
| B&H vol-target | 98.58 | 12.08 | 7.53 | 1.43 | 3.50 | 9.45 | 1.28 | 78.80 |
| SMA(20/50) | 115.79 | 13.64 | 8.87 | 1.38 | 3.39 | 9.49 | 1.44 | 77.13 |
| MACD | 71.22 | 9.35 | 7.44 | 1.11 | 2.73 | 14.77 | 0.63 | 66.53 |
| KDJ+RSI | 67.72 | 8.98 | 9.96 | 0.82 | 2.01 | 18.06 | 0.50 | 53.47 |
| ZMR | 44.36 | 6.29 | 9.94 | 0.57 | 1.40 | 19.25 | 0.33 | 43.75 |

#### portfolio Sharpe difference (paired block bootstrap over days): design

- agent minus B&H vol-target: -0.03 [-0.28, +0.23] p=0.898 (n=1564 days, block 10)
- agent minus Buy&Hold: +0.12 [-0.16, +0.40] p=0.434 (n=1564 days, block 10)

#### portfolio: holdout

| index | CR% | AR% | Vol% | Sharpe | t(SR) | MDD% | Calmar | Exp% |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 50.62 | 9.55 | 6.71 | 0.80 | 1.70 | 7.80 | 1.22 | 59.10 |
| Buy&Hold | 96.91 | 16.29 | 14.08 | 0.86 | 1.82 | 20.43 | 0.80 | 94.96 |
| B&H vol-target | 61.48 | 11.27 | 7.01 | 0.99 | 2.10 | 9.17 | 1.23 | 72.12 |
| SMA(20/50) | 49.35 | 9.35 | 8.22 | 0.64 | 1.36 | 11.98 | 0.78 | 71.51 |
| MACD | 35.29 | 6.97 | 8.22 | 0.38 | 0.80 | 16.02 | 0.43 | 65.35 |
| KDJ+RSI | 58.49 | 10.81 | 9.57 | 0.70 | 1.49 | 12.92 | 0.84 | 59.70 |
| ZMR | 40.93 | 7.94 | 9.11 | 0.45 | 0.95 | 9.82 | 0.81 | 48.75 |

#### portfolio Sharpe difference (paired block bootstrap over days): holdout

- agent minus B&H vol-target: -0.19 [-0.53, +0.16] p=0.297 (n=1167 days, block 10)
- agent minus Buy&Hold: -0.06 [-0.41, +0.30] p=0.748 (n=1167 days, block 10)

#### rebalance-phase sweep, holdout portfolio (5-bar cadence, offsets 0-4): agent Sharpe spread 0.06

| offset | agent Sharpe | vol-target Sharpe | B&H Sharpe | agent - vol-target | agent - B&H |
|--:|--:|--:|--:|:--|:--|
| 0 | 0.80 | 0.99 | 0.86 | -0.19 [-0.53, +0.16] p=0.297 (n=1167 days, block 10) | -0.06 [-0.41, +0.30] p=0.748 (n=1167 days, block 10) |
| 1 | 0.85 | 0.99 | 0.86 | -0.14 [-0.46, +0.19] p=0.429 (n=1167 days, block 10) | -0.01 [-0.34, +0.35] p=0.988 (n=1167 days, block 10) |
| 2 | 0.86 | 0.99 | 0.86 | -0.13 [-0.46, +0.21] p=0.468 (n=1167 days, block 10) | +0.00 [-0.35, +0.38] p=0.981 (n=1167 days, block 10) |
| 3 | 0.80 | 0.99 | 0.86 | -0.19 [-0.51, +0.15] p=0.284 (n=1167 days, block 10) | -0.06 [-0.40, +0.31] p=0.774 (n=1167 days, block 10) |
| 4 | 0.84 | 0.99 | 0.86 | -0.15 [-0.49, +0.19] p=0.390 (n=1167 days, block 10) | -0.02 [-0.37, +0.34] p=0.911 (n=1167 days, block 10) |

**Reading it.** As a 15-sleeve equal-capital portfolio the desk no longer beats plain buy &
hold on Sharpe; the v0.7 claim (1.09 against 1.06) is retracted. Holdout: desk Sharpe 0.80
(t 1.70), CR 50.62%, MDD 7.80%, exposure 59.10%; buy & hold 0.86 / 96.91% / 20.43%; the
vol-targeted control 0.99 / 61.48% / 9.17%. Paired block bootstrap over days (block 10,
n 1167): desk − B&H -0.06 [-0.41, +0.30] p 0.748; desk − vol-target -0.19 [-0.53, +0.16]
p 0.297. Design: 1.40 (t 3.43) against 1.28 and 1.43; desk − B&H +0.12 [-0.16, +0.40] p 0.434;
desk − vol-target -0.03 [-0.28, +0.23] p 0.898. The rebalance-phase sweep (holdout, offsets
0–4) moves the desk across 0.80 / 0.85 / 0.86 / 0.80 / 0.84 — a spread of 0.06 against a
fixed 0.99 (vol-target) and 0.86 (buy & hold): the cadence noise floor is the size of the
portfolio differences quoted, and no offset changes the sign of desk − vol-target. The
holdout drawdown, 7.80% against 20.43% and 9.17%, is the part of the v0.7 portfolio claim
that survives.

### 4. The cash leg

**Convention (v0.8).** Equities are funded: (1 − |w|) of the account earns the 3-month bill
(FRED DTB3, one-day publication lag). FX forwards: the whole account earns it. Sharpe and
Sortino are on returns in excess of that bill; AR, CR, MDD and Calmar stay total return.
Synthetic data is unchanged (its rate is the constant 0). `cash_leg: "off"` credits nothing
and uses `risk_free_annual` (0) in the metrics, i.e. the v0.7 convention. The two
conventions were measured on the same engine and the same bars
(`portfolio_*_cash_leg_off.json`, `eval_cash_leg_off.json`), so the difference is what idle
cash at the point-in-time bill rate is worth to each strategy — and nothing else.

#### cash leg on vs off: design

| index | Sharpe (cash leg) | CR% (cash leg) | MDD% (cash leg) | Exp% (cash leg) | Sharpe (no cash leg) | CR% (no cash leg) | MDD% (no cash leg) | Exp% (no cash leg) |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 1.40 | 93.64 | 10.17 | 61.81 | 1.46 | 87.97 | 10.20 | 61.86 |
| Buy&Hold | 1.28 | 197.51 | 22.69 | 96.74 | 1.32 | 192.05 | 22.77 | 97.76 |
| B&H vol-target | 1.43 | 98.58 | 9.45 | 78.80 | 1.49 | 92.72 | 9.76 | 79.25 |
| SMA(20/50) | 1.38 | 115.79 | 9.49 | 77.13 | 1.43 | 109.09 | 9.53 | 77.17 |
| MACD | 1.11 | 71.22 | 14.77 | 66.53 | 1.16 | 65.06 | 15.37 | 66.54 |
| KDJ+RSI | 0.82 | 67.72 | 18.06 | 53.47 | 0.84 | 60.49 | 18.21 | 53.51 |
| ZMR | 0.57 | 44.36 | 19.25 | 43.75 | 0.59 | 37.91 | 19.32 | 43.76 |

#### cash leg on vs off: holdout

| index | Sharpe (cash leg) | CR% (cash leg) | MDD% (cash leg) | Exp% (cash leg) | Sharpe (no cash leg) | CR% (no cash leg) | MDD% (no cash leg) | Exp% (no cash leg) |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| AgenticTrader | 0.80 | 50.62 | 7.80 | 59.10 | 1.04 | 35.17 | 8.01 | 59.07 |
| Buy&Hold | 0.86 | 96.91 | 20.43 | 94.96 | 1.05 | 86.23 | 20.79 | 97.47 |
| B&H vol-target | 0.99 | 61.48 | 9.17 | 72.12 | 1.24 | 46.21 | 9.85 | 73.94 |
| SMA(20/50) | 0.64 | 49.35 | 11.98 | 71.51 | 0.85 | 34.89 | 13.23 | 71.66 |
| MACD | 0.38 | 35.29 | 16.02 | 65.35 | 0.54 | 20.26 | 16.31 | 65.39 |
| KDJ+RSI | 0.70 | 58.49 | 12.92 | 59.70 | 0.81 | 38.85 | 13.50 | 59.87 |
| ZMR | 0.45 | 40.93 | 9.82 | 48.75 | 0.54 | 22.25 | 10.38 | 48.79 |

#### cash leg off (a) vs on (b)

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

**Reading it.** The cash leg lowered every strategy's Sharpe on the holdout and decides
nothing about the ranking. Holdout portfolio, cash leg on → off: desk Sharpe 0.80 → 1.04,
CR 50.62% → 35.17%, MDD 7.80% → 8.01%; buy & hold 0.86 → 1.05, CR 96.91% → 86.23%;
vol-target 0.99 → 1.24, CR 61.48% → 46.21%; SMA 0.64 → 0.85; MACD 0.38 → 0.54. Design
portfolio: desk 1.40 → 1.46 (CR 93.64% → 87.97%), buy & hold 1.28 → 1.32, vol-target
1.43 → 1.49. Per instrument (the last table; no BH flag is printed), the agent's Sharpe with
the leg off minus on: holdout core +0.10 [+0.06, +0.15] p 0.00, extended +0.17 [+0.13, +0.21]
p 0.00, all 60 +0.15 [+0.04, +0.23] p 0.02 (clusters); design core +0.03 [+0.02, +0.04]
p 0.00, all 60 +0.04 [+0.01, +0.06] p 0.01. Reading: the credited bill averaged 3.99% a year
over the 2022–2026 holdout (`rf` column of `results/v08/portfolio_holdout.csv`), so an
excess-return Sharpe is lower for everyone, and crediting the desk's idle capital (exposure
59.10%) raises its cumulative return (35.17% → 50.62%) but not its excess-return Sharpe by
as much as the bill takes from a low-volatility strategy; buy & hold holds almost no cash.
Over 2016–2021 it averaged 0.94% (`rf` column of `results/v08/portfolio_design.csv`), so the
design period barely moves.

**Decomposition of the v0.7 → v0.8 portfolio holdout move, 1.09 → 0.80.** The cash-leg
convention accounts for 1.04 → 0.80 (-0.24, measured here on one engine). The other engine
corrections (constant units and post-cost sizing, the desk told its true position after a
stop, gap-through-take fills, sleeve impact) plus any data drift since 2026-09-25 account for
1.09 → 1.04 — compared across engines, so it is a difference between two records, not a
measured effect. Under either convention the holdout order is desk < buy & hold < vol-target
(1.04 / 1.05 / 1.24 off; 0.80 / 0.86 / 0.99 on), so the v0.7 "beats plain buy & hold" was
already inside the noise and is retracted regardless of the cash leg. The README headline
follows the cash-leg-on numbers and states the convention in one clause.

### 5. Drawdown against the fair control

The paired maximum-drawdown and Calmar tables, desk minus each control, with the BH flag;
then the by-asset-class tables for the core equities (10) and the core FX pairs (5) on the
holdout.

#### paired MDD%, agent minus control: core (15)

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

#### paired MDD%, agent minus control: extended (45)

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

#### paired Calmar, agent minus control: core (15)

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

#### paired Calmar, agent minus control: extended (45)

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

#### summary by asset class: core (15) equity (10), holdout

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| holdout | AgenticTrader | 10 | 0.45 | 61.38 | 22.11 | 16.15 | 58.05 |
| holdout | B&H vol-target | 10 | 0.53 | 74.27 | 21.28 | 17.02 | 63.28 |
| holdout | Buy&Hold | 10 | 0.52 | 131.34 | 40.24 | 30.99 | 100.00 |
| holdout | KDJ+RSI | 10 | 0.52 | 68.10 | 27.87 | 21.76 | 40.17 |
| holdout | MACD | 10 | 0.43 | 41.38 | 34.03 | 21.46 | 50.40 |
| holdout | SMA(20/50) | 10 | 0.33 | 69.82 | 30.36 | 21.54 | 60.37 |
| holdout | ZMR | 10 | 0.25 | 48.25 | 24.60 | 20.07 | 33.13 |

#### paired Sharpe by asset class, agent minus control: core (15) equity (10)

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

#### paired MDD% by asset class, agent minus control: core (15) equity (10)

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

#### summary by asset class: core (15) fx (5), holdout

| period | strategy | n | median Sharpe | mean CR% | mean MDD% | mean Vol% | mean Exp% |
|:--|:--|--:|--:|--:|--:|--:|--:|
| holdout | AgenticTrader | 5 | 0.06 | 25.82 | 8.00 | 6.17 | 65.43 |
| holdout | B&H vol-target | 5 | -0.11 | 33.36 | 14.40 | 8.33 | 94.43 |
| holdout | Buy&Hold | 5 | -0.05 | 32.54 | 14.45 | 8.20 | 92.17 |
| holdout | KDJ+RSI | 5 | 0.21 | 27.40 | 16.05 | 8.98 | 101.75 |
| holdout | MACD | 5 | 0.02 | 15.57 | 14.51 | 8.66 | 98.95 |
| holdout | SMA(20/50) | 5 | 0.38 | 16.74 | 14.39 | 8.54 | 98.21 |
| holdout | ZMR | 5 | -0.04 | 16.36 | 15.95 | 7.91 | 82.45 |

#### paired Sharpe by asset class, agent minus control: core (15) fx (5)

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

#### paired MDD% by asset class, agent minus control: core (15) fx (5)

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

**Reading it.** "About half the drawdown" is true against plain buy & hold and is almost
entirely volatility scaling. Core holdout mean MDD 17.40% (desk) against 31.64% (buy & hold)
and 18.98% (vol-target); paired desk − B&H -14.24 points [-20.41, -8.70] p 0.00,
BH-significant; desk − vol-target -1.58 [-4.33, +1.14] p 0.27, not significant. On the core
*equities* — the names the rules were tuned on — the holdout drawdown is 22.11% against
40.24% and 21.28%, and desk − vol-target is **+0.83 [-1.63, +3.21] p 0.50, not
BH-significant**: the desk's drawdown is not lower than the fair control's there, and its
Sharpe is below it (-0.09 [-0.14, -0.03] p 0.00, BH-significant). On the extended universe
(45) the holdout is 15.46% against 26.39% and 19.79%; desk − vol-target -4.33 [-6.10, -2.55]
p 0.00, BH-significant; desk − B&H -10.93 [-13.41, -8.64] p 0.00, BH-significant. **On FX
the comparison has essentially no control:** the vol-target baseline sits at the shared 1.0
position cap most of the time, so its rows coincide with buy & hold's — on the core FX pairs
the q1_2024 and reserve rows against the two are identical, and the holdout rows are -6.40
[-10.32, -2.09] against vol-target and -6.46 [-10.34, -2.14] against buy & hold. Calmar:
extended holdout desk − B&H +0.11 [+0.03, +0.19] p 0.00, BH-significant; desk − vol-target
+0.07 [0.00, +0.14] p 0.05, not flagged; core holdout desk − vol-target -0.08 [-0.23, +0.07]
p 0.29 and desk − B&H +0.03 [-0.12, +0.15] p 0.72, neither BH-significant.

### 6. Impact, and execution algorithms at the sleeve's capital

The v0.5 impact sweep re-measured (`eval_impact_1e5/1e7/1e9.json`): square-root market
impact inside the backtester, textbook coefficient 1.0, now scaled by the equity actually
traded, core universe, design and holdout, for the desk and every baseline; "impact %" is
the cumulative cost paid over the period as a percentage of equity, averaged over the 15
instruments (FX sleeves get no impact without a configured notional ADV). Then the v0.7
execution-algorithm table re-measured with each sleeve paying the impact of its own capital
share (`portfolio_holdout_impact_1e9_{vwap,twap,ac}.json`).

#### impact sweep, core universe, textbook coefficient 1.0 (equity-scaled impact)

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

#### execution algorithm, $1B holdout portfolio (sleeve impact at the sleeve's capital)

| execution algo | Sharpe | CR% | MDD% | mean sleeve impact paid % |
|:--|--:|--:|--:|--:|
| VWAP (default) | 0.78 | 49.62 | 7.83 | 0.66 |
| TWAP | 0.78 | 49.56 | 7.83 | 0.70 |
| Almgren-Chriss, kappa=5 | 0.77 | 49.30 | 7.84 | 0.87 |

**Reading it.** The desk keeps its Sharpe at $100k and $10M (design 0.66 → 0.66 → 0.66;
holdout 0.34 → 0.34 → 0.34) and goes to 0.61 on the design period (impact paid 4.24% of
equity) and 0.31 on the holdout (2.53%) at $1B. The vol-targeted control goes 0.64 → 0.57 and
0.45 → 0.41 at $1B; SMA 0.57 → 0.38 and 0.18 → 0.04; MACD 0.40 → -0.18 and 0.14 → -0.30 (MACD
pays 64.71% of equity in impact on the design period at $1B). **v0.7's "loses 0.09 at $1B"
is replaced by these**; the ranking below institutional size is unchanged. Execution
algorithms at $1B on the holdout portfolio: VWAP 0.78 Sharpe / CR 49.62% / MDD 7.83% / mean
sleeve impact paid 0.66%; TWAP 0.78 / 49.56% / 7.83% / 0.70%; Almgren–Chriss κ=5 0.77 /
49.30% / 7.84% / 0.87%. **The v0.7 table charged √15 times too much** (every sleeve ran with
the whole book's capital; retracted in the CHANGELOG); the ordering VWAP < TWAP < AC survives,
the magnitudes do not.

### 7. Every earlier decision re-checked under the v0.8 engine

Each earlier decision, one table and one sentence: the agent's Sharpe under (a) minus under
(b), mean difference across instruments with its interval, p, scheme and wins. These
on-vs-off tables print no BH flag, so none of their differences is called BH-significant
here. The cash leg (off against on) is [part 4](#4-the-cash-leg).

#### EDGAR on (a) vs off (b)

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

**EDGAR on against off** (the v0.6 data decision, under the corrected per-concept, per-basis
reconstruction; every earlier EDGAR figure is superseded): design core +0.01 [-0.03, +0.04]
p 0.72 (4 / 15 wins; the filings reach the 10 equities only), design extended +0.01
[+0.00, +0.02] p 0.02 (16 / 45), design all 60 +0.01 [-0.01, +0.02] p 0.19 (clusters);
holdout core -0.01 [-0.07, +0.04] p 0.83, holdout extended +0.03 [+0.01, +0.06] p 0.00
(15 / 45), holdout all 60 +0.02 [-0.02, +0.05] p 0.39; q1_2024 core +0.09 [+0.00, +0.21]
p 0.02, extended +0.05 [+0.01, +0.11] p 0.00; reserve core +0.11 [+0.00, +0.23] p 0.04,
extended +0.03 [-0.04, +0.10] p 0.45. The core design period — the choice basis — cannot tell
on from off; the extended equities, which no rule was tuned on, show a small gain, with the
all-60 cluster interval covering zero. The data stays on (it is a data source, not a rule,
and the design period shows no harm);
the untuned rules that read it remain the next protocol item. In the
[trials registry](#9-selection-statistics-26-trials), "EDGAR filings off" has a design mean
Sharpe of 0.65 against 0.66 on, CR 110.44% against 118.18%, MDD 15.30% against 17.59%,
exposure 60.48% against 63.31%: the filings add exposure and drawdown on the core names for
about no Sharpe — the v0.6 finding, re-measured.

#### FX carry rule on (a) vs off (b)

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

**The FX carry-neutral rule (v0.5.1) on against off:** design core +0.04 [-0.01, +0.10]
p 0.11 (4 / 15 wins — the rule touches FX only); holdout core +0.02 [-0.02, +0.07] p 0.37;
holdout extended +0.04 [+0.00, +0.08] p 0.04; q1_2024 core +0.49 [+0.12, +0.94] p 0.01;
reserve extended +0.14 [+0.03, +0.28] p 0.00; all 60 holdout +0.03 [-0.00, +0.12] p 0.23
(clusters). Positive on every slice, small, intervals touching zero on most; the v0.5.1
"improved every unseen slice" may stay only with these numbers beside it. The rule stays.

#### v0.3+ rules (a) vs v0.2 rules (b), core

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

**The v0.3 rules against the v0.2 rules (core):** design +0.19 [+0.10, +0.28] p 0.00
(12 / 15); **holdout -0.00 [-0.11, +0.09] p 0.99** (0.34 against 0.34, 8 / 15); q1_2024 +0.72
[+0.29, +1.17] p 0.00; reserve +0.95 [+0.45, +1.47] p 0.00. The design-period gain of the
chosen rules did not carry to the holdout at all (v0.7 said "shrank"); the two short windows
favour v0.3.

#### with the cross-sectional analyst (a) vs default (b)

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

**The cross-sectional analyst (`xalpha`) against the default:** design core -0.01
[-0.02, +0.00] p 0.36; holdout core 0.00 [-0.01, +0.02] p 0.60; holdout extended -0.00
[-0.01, +0.00] p 0.23; q1_2024 core +0.09 [+0.00, +0.20] p 0.04; reserve extended -0.02
[-0.06, +0.01] p 0.20. Off by default stands.

#### with the alpha analyst, corrected gate (a) vs default (b)

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

**The alpha analyst with the corrected gate against the default (core; the `all` rows are
the same 15 instruments):** design -0.00 [-0.05, +0.05] p 0.90; holdout -0.00 [-0.04, +0.02]
p 0.79; q1_2024 +0.10 [+0.01, +0.23] p 0.01; reserve +0.07 [-0.00, +0.20] p 0.21. Off by
default stands (the design period shows nothing). How often the corrected gate speaks in
these runs was **not measured**: the driver recorded no abstention tally, so no speak rate is
given here.

#### track-record size cut off (a) vs on (b)

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

**The track-record size cut off against on:** design core +0.00 [-0.00, +0.01] p 0.51;
design extended +0.01 [+0.00, +0.01] p 0.01; design all 60 +0.01 [+0.00, +0.01] p 0.03
(clusters); holdout core +0.01 [-0.01, +0.02] p 0.46; holdout extended +0.01 [+0.00, +0.02]
p 0.02; q1_2024 extended +0.04 [+0.01, +0.07] p 0.00; reserve core +0.04 [+0.00, +0.09]
p 0.04. Removing the cut is worth about +0.01 on nearly every slice, and the core design
period — the only basis the protocol accepts for a rule change — cannot tell the two apart.
**The default stays on** (`rules.track_record_cut: True`); the other slices are recorded as
information for the next rule change, not as a choice basis.

### 8. VaR coverage, re-measured and labelled

Two tests, each labelled as what it is (`var_coverage.json`; Kupiec unconditional coverage
and Christoffersen independence, likelihood-ratio tests against a walk-forward forecast that
uses only the trailing window before each day). (a) The rolling historical VaR of the
15-sleeve holdout portfolio's *own* returns at 120 and 250 days — what v0.7 measured and
called the desk's risk model. (b) New: the forecast the desk actually sizes on — the 250-day
historical VaR from `agents/risk.py` `risk_facts` — walked forward over the holdout for each
of the 15 core instruments and tested against that instrument's next-day return.

#### VaR coverage: rolling historical VaR of the 15-sleeve portfolio's own returns

| forecast | n | breaches | breach_rate | kupiec_p | christoffersen_p | conditional_coverage_p |
|:--|--:|--:|--:|--:|--:|--:|
| portfolio returns, 120-day rolling historical VaR | 1048 | 65 | 0.0620 | 0.0847 | 0.1488 | 0.0798 |
| portfolio returns, 250-day rolling historical VaR | 918 | 42 | 0.0458 | 0.5493 | 0.1650 | 0.3188 |

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

**Reading it.** (a) Portfolio returns, 120-day window: n 1048, 65 breaches, rate 0.0620,
Kupiec p 0.0847, Christoffersen p 0.1488, conditional coverage p 0.0798 — not rejected at
5%, but close; 250-day window: n 918, 42 breaches, 0.0458, Kupiec p 0.5493, Christoffersen
p 0.1650, conditional coverage p 0.3188. (b) The desk's own per-instrument forecast (n 1126
for the equities, 1167 for FX): Kupiec rejects at 5% on 2 of 15 (AAPL, rate 0.0657, p 0.0207;
AUDUSD, 0.0634, p 0.0432); every breach rate is above 5% (0.0523 to 0.0657);
**Christoffersen independence rejects on 6 of 15** (AAPL p 0.0027, SPY 0.0121, JPM 0.0158,
GBPUSD 0.0182, META 0.0274, USDCAD 0.0441): the breaches cluster. What these establish: the
desk's forecast is slightly too tight on every core instrument and slow to react on six of
them; the portfolio-returns quantile passes at 250 days and is close to rejection at 120.
Book-level VaR (`max_book_var_95`) was off in every published run and its coverage is
untested. The v0.7 sentence "the desk's own risk model is calibrated" is replaced by these
two labelled tests.

### 9. Selection statistics: 26 trials

`evaluation.TRIALS` names the 26 variants judged on the design period since the v0.2
control: 24 are reproducible under the current engine and were re-measured
(`trial_*.json`, `trials.json`), 2 are historical (the v0.4 alpha-analyst variants, recorded
only). The registry prints the re-measured design mean Sharpe beside the v0.3 record, and
the design mean CR / MDD / exposure / trades per instrument. `stats.selection_report` is then
run on the design-period 15-sleeve portfolio returns with the 26 trials' mean Sharpes.

#### trials registry: 26 variants judged on the design period

| trial | version | design mean Sharpe (v0.8 engine) | recorded (v0.3 engine) | re-measured | design mean CR% | design mean MDD% | design mean Exp% | design mean Trades |
|:--|:--|--:|--:|--:|--:|--:|--:|--:|
| v0.2 (control) | v0.3 | 0.47 | 0.50 | yes | 58.24 | 13.31 | 43.99 | 254.20 |
| + 12-1 month time-series momentum | v0.3 | 0.47 | 0.47 | yes | 73.93 | 13.56 | 47.74 | 262.47 |
| + trend-filtered reversal | v0.3 | 0.46 | 0.48 | yes | 58.40 | 13.50 | 44.66 | 254.53 |
| + abstain without data | v0.3 | 0.48 | 0.51 | yes | 62.72 | 13.98 | 46.78 | 258.27 |
| + no-trade band 0.10 | v0.3 | 0.47 | 0.50 | yes | 58.11 | 13.18 | 43.80 | 135.20 |
| + intraday stops | v0.3 | 0.45 | 0.47 | yes | 44.10 | 12.67 | 40.30 | 292.20 |
| signal changes (momentum + filter + abstain) | v0.3 | 0.48 | 0.51 | yes | 77.65 | 13.98 | 50.33 | 268.27 |
| signal changes + band | v0.3 | 0.48 | 0.51 | yes | 77.71 | 14.01 | 49.85 | 117.27 |
| all five | v0.3 | 0.46 | 0.50 | yes | 54.82 | 13.16 | 45.66 | 188.80 |
| strategic equity weight 0.25 | v0.3 | 0.54 | 0.54 | yes | 82.41 | 14.00 | 50.55 | 282.40 |
| strategic equity weight 0.50 | v0.3 | 0.58 | 0.58 | yes | 100.26 | 14.71 | 54.86 | 287.73 |
| strategic equity weight 1.00 | v0.3 | 0.63 | 0.66 | yes | 121.95 | 17.07 | 60.37 | 292.67 |
| strategic 0.50 + band | v0.3 | 0.58 | 0.58 | yes | 96.41 | 14.73 | 54.20 | 118.60 |
| strategic 0.50 + signal changes + band | v0.3 | 0.57 | 0.58 | yes | 105.72 | 15.89 | 57.42 | 104.67 |
| strategic 0.50 + abstain + band | v0.3 | 0.58 | 0.56 | yes | 97.10 | 14.98 | 55.60 | 117.40 |
| frozen v0.3: strategic 1.00 + band | v0.3 | 0.62 | 0.65 | yes | 116.52 | 17.62 | 59.52 | 98.60 |
| + alpha analyst (IC-weighted, all signals) | v0.4 |  | 0.60 |  |  |  |  |  |
| + alpha analyst (significance-gated, 400-day window) | v0.4 |  | 0.58 |  |  |  |  |  |
| + alpha analyst (significance-gated, 900-day window) | v0.5 | 0.66 | 0.65 | yes | 119.23 | 17.42 | 62.42 | 93.87 |
| FX carry / 4, cap 0.5 | v0.5.1 | 0.65 |  | yes | 117.63 | 17.53 | 62.15 | 94.27 |
| FX carry / 2, cap 0.5 (adopted) | v0.5.1 | 0.66 |  | yes | 118.18 | 17.59 | 63.31 | 91.73 |
| FX carry / 4, cap 1.0 | v0.5.1 | 0.65 |  | yes | 117.63 | 17.55 | 62.16 | 93.60 |
| FX carry / 8, cap 0.25 | v0.5.1 | 0.64 |  | yes | 117.18 | 17.53 | 61.11 | 96.87 |
| + cross-sectional alpha analyst | v0.6 | 0.66 |  | yes | 119.86 | 17.70 | 63.28 | 90.33 |
| EDGAR filings off | v0.6 | 0.65 |  | yes | 110.44 | 15.30 | 60.48 | 108.00 |
| track-record size cut off | v0.8 | 0.66 |  | yes | 118.74 | 17.97 | 63.79 | 89.80 |

#### selection statistics for the frozen rules (design-period portfolio, all trials)

```json
{
 "n": 1564,
 "sharpe_annual": 1.375,
 "t_stat": 3.42,
 "skew": -0.635,
 "kurtosis": 8.41,
 "bootstrap_ci_95": [
  0.593,
  2.17
 ],
 "psr_vs_zero": 1.0,
 "trials": 26,
 "expected_max_sharpe_annual": 0.161,
 "deflated_sharpe_prob": 0.998,
 "min_track_record_periods": 496,
 "caveat": "an upper bound on the true significance: the benchmark is built from the dispersion of trial_sharpes_annual, which is usually narrower than the dispersion of the full return series each trial would have produced, so the true search space is wider than this reports and the real probability is no higher than the number given."
}
```

**Reading it.** n 1564 daily returns, annual Sharpe 1.375, t 3.42, skew -0.635, kurtosis
8.41, bootstrap 95% interval [0.593, 2.17], probabilistic Sharpe against 0 = 1.00 (the Sharpe
and the interval are annualised at 252 periods/year with rf/252 per bar, as
`scripts/render_v08_tables.py` computes them; part 3's portfolio table prints the same
1564-day series at the 260 periods/year and rf/260 per bar the portfolio metrics use, which
is why it reads 1.40, t 3.43 — the per-period Sharpe, PSR, deflated probability and minimum
track record do not depend on the annualisation); with 26 trials the expected maximum Sharpe
of null trials is 0.161, the deflated Sharpe probability
0.998 and the minimum track record 496 periods. The caveat in the JSON stands verbatim: this
is an *upper bound* — the benchmark is built from the dispersion of the trials' mean Sharpes,
which is narrower than the dispersion of the full return series each trial would have
produced, so the real probability is no higher than the number given; and the returns are
from the design period, on which the rules were chosen. Trials re-measured under the v0.8
engine against the v0.3 record: control 0.47 (was 0.50), strategic equity weight 0.25 / 0.50
/ 1.00 = 0.54 / 0.58 / 0.63 (recorded 0.54 / 0.58 / 0.66), frozen v0.3 0.62 (0.65). The
ordering of the 16-variant ablation is unchanged: the strategic weight is the one change that
matters (0.47 → 0.63, CR 58.24% → 121.95%, exposure 43.99% → 60.37%) and the signal tweaks
sit at 0.45–0.48 around the control's 0.47. "+ intraday stops": 0.45 Sharpe, CR 44.10%, MDD
12.67%, 292.20 trades against the control's 0.47 / 58.24% / 13.31% / 254.20 — stops cut the
cumulative return by about a quarter at a similar Sharpe. "+ no-trade band 0.10": 0.47 /
58.11% at 135.20 trades per instrument against 254.20 — 47% fewer trades at the same Sharpe.
Trials added since v0.3: the v0.5 gated alpha analyst (0.66), the four v0.5.1 carry variants
(0.65 / 0.66 adopted / 0.65 / 0.64), the v0.6 cross-sectional analyst (0.66) and EDGAR filings
off (0.65), and the v0.8 track-record cut off (0.66); the two historical v0.4 variants keep
their recorded 0.60 and 0.58.

### 10. What remains unseen

Nothing. The reserve period (2026-07-01 → 2026-09-25) and the extended universe were
consulted for the v0.5.1 carry rule and the v0.6 EDGAR and cross-sectional decisions, and
v0.8 re-measured every period on every universe. No held-out data remains; the next unseen
data is the future. The other-slice results above (the track-record cut, the carry rule) are
information for the next rule change, not a basis for one; see
[the next rule change](#the-next-rule-change-what-counts-as-unseen).

### 11. Reproducing the v0.8 numbers

```bash
pip install -r requirements-lock.txt && pip install -e . --no-deps   # Python 3.12 only

# every table in this section (about an hour on the C++ backend; a run whose output exists is skipped)
.venv\Scripts\python.exe scripts/measure_v08.py                       # --only eval_main,portfolio_holdout,... for a subset
.venv\Scripts\python.exe scripts/render_v08_tables.py                 # prints every table, writes results/v08/tables.md
```

`measure_v08.py` writes `results/v08/*.json|csv` (Yahoo, FRED and SEC EDGAR are needed;
`EDGAR_USER_AGENT` in `.env`); `--only` takes run names (`eval_main`, `eval_noedgar`,
`eval_rules_v03`, `eval_rules_v02`, `eval_xalpha`, `eval_alpha`, `eval_no_trackrecord_cut`,
`eval_cash_leg_off`, `eval_impact_1e5/1e7/1e9`, the portfolios, `var_coverage`, `trials`,
`phase_sweep`). `render_v08_tables.py` renders the markdown pasted above from those files
(`--section` for one) and computes the design-period block-bootstrap difference and the
selection report in the process. The lock file is the full transitive freeze of the
environment that produced these numbers (CPython 3.12.10, win_amd64) and is valid for
**Python 3.12 only**.

**Provenance.** Every file under `results/v08` carries `provenance` with `git_commit` and
`git_dirty: false`, and every `--out` CSV has a `<stem>.provenance.json` sidecar;
`results/v08/manifest.json` records the run. `eval_main.json` was written at `c4385e2` (fix
round 3); the impact sweeps, `eval_alpha`, `eval_xalpha`, `eval_no_trackrecord_cut`, both
portfolios, the execution-algorithm portfolios, `var_coverage`, `phase_sweep` and 23 of the
24 trials at `eec0d27` (identical engine, data and rules code: `eec0d27` changed only the
`FIRM_CONTEXT` prompt string, prompt bundle hash `a2fb8be5c3066730`, on which no offline
rules-based number depends); `eval_noedgar`, `eval_cash_leg_off`, the two cash-leg-off
portfolios, `trial_edgar_filings_off`, `eval_rules_v03` and `eval_rules_v02` at `ac727ce` (the
driver fix below and a renderer change; no engine code).

**Why five files were re-measured.** The first run handed one shared Yahoo provider to every
run, and `edgar` / `cash_leg` are read from the provider's own config, so the "EDGAR off" and
"cash leg off" runs had both still on: their `meta["edgar"]` recorded `True`, and their
tables showed zero difference on every instrument, which is what exposed it. The fix is
`MarketDataProvider.reconfigured(config)` (the same downloaded bars under the run's own
settings) and `provider_for()` in the driver, with regression tests
`tests/test_v08_fixes.py::test_36_a_reconfigured_provider_shares_the_downloads_under_its_own_settings`
and
`tests/test_v08_protocol.py::test_measurement_driver_reconfigures_the_shared_provider_for_provider_level_overrides`;
the affected files were re-measured before any number was published, and no result from the
first run of those files appears on this page (the engineering table quotes that run's
wall-clock timings, labelled as the first run).

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
| Full v0.6 evaluation with EDGAR fundamentals and news (60 × 4) | ≈ 340 s: the fundamentals are rebuilt once per filing per name (memoised on the last filing date), the filing news is a frame filter per decision |
| One 45-name cross-section for the `xalpha` analyst (900 days, 9 alphas, IC only) | ≈ 1.4 s, computed once per (universe, date) and shared by every name at that date |
| EDGAR walk-forward lookups | 300 fundamentals calls ≈ 1.9 s, 300 news calls ≈ 0.2 s (AAPL, after the one-off download of the company facts and filing index) |
| v0.8 measurement, first run (`scripts/measure_v08.py`, C++ backend, 4 workers, idle machine; `results/v08/measure.log` lines 1–1791). Its `eval_noedgar`, `eval_cash_leg_off`, cash-leg-off portfolio and EDGAR-off trial outputs were superseded (EDGAR and the cash leg were still on, see [Reproducing](#reproducing)) and its `eval_rules_v03` / `eval_rules_v02` outputs were re-measured on a clean tree; the timings of the published files for those runs are in the next row | `eval_main` 312 s (60 instruments × 4 periods); `eval_noedgar` 184 s (EDGAR still on); `eval_rules_v03` 170 s; `eval_rules_v02` 44 s (core); `eval_xalpha` 1727 s; `eval_alpha` 109 s (core); `eval_no_trackrecord_cut` 159 s; `eval_cash_leg_off` 157 s (cash leg still on); each impact sweep 41 s (core, 2 periods); each 15-sleeve portfolio 14–20 s; 23 of the 24 trials 24–25 s, the gated alpha-analyst trial 59 s; the whole script 3787 s |
| v0.8 re-measurement after the shared-provider fix (see [Reproducing](#reproducing)); the published files (`ac727ce`) are from the 473 s and 317 s runs | three `--only` runs of 525 s, 473 s and 317 s: `eval_noedgar` 124 s and 122 s, `eval_cash_leg_off` 309 s and 278 s, the two cash-leg-off portfolios 36 s/30 s and 31 s/26 s, the EDGAR-off trial 26 s and 15 s, then `eval_rules_v03` 273 s and `eval_rules_v02` 44 s (re-run because the first run's files were stamped dirty by concurrent doc edits) |
| Tests | 832 collected on both backends (`pytest --collect-only -q`, 2026-09-28): the C++ suite 832 passed; the numpy suite 796 passed and 36 skipped (the C++-only tests); plus 25 C++ test functions in `cpp/tests/test_core.cpp` (ctest) |
| Line coverage (`pytest --cov=agentic_trader`, numpy backend, 2026-09-28; CI report only -- not a merge gate) | 95% of 9284 statements (425 missed); weakest `data/yahoo.py` 75% (network branches), `quant/__init__.py` 77% (the C++ dispatch is skipped on the numpy backend), `provenance.py` 82%; `llm.py` 99% |

## Limitations

- **One small LLM result, and that is still the only one that has actually run.** The LLM
  desk has been measured exactly once: five stocks, one quarter, $4 (no Sharpe edge over the
  rules; smaller positions, lower returns and drawdowns). The multi-year harness -- model
  tiers on the core universe over design and holdout, repeated runs for the model's variance,
  a calibration -- has existed since v0.6 (staged, with a dollar cap per stage), but **as of
  this writing it has not been executed**: "staged" here means the code and budget exist, not
  that a result does. The v0.5.1 numbers were produced under the v0.7-and-earlier engine and
  are not re-derived under v0.8. There is no multi-year LLM section because there is no
  multi-year LLM result yet; when the staged run is made, its section replaces this bullet,
  not the other way around, so a reader is never left to infer completion from a code
  capability.
- **The cash-leg convention is a choice.** Since v0.8 funded equity positions earn the
  3-month bill on (1 − |w|) of the account and FX forwards earn it on the whole account
  (FRED DTB3, one-day publication lag; the constant 0 on synthetic data), and Sharpe, Sortino
  and t(SR) are on returns in excess of it, while CR, AR, MDD and Calmar stay total return.
  Any v0.7-or-earlier Sharpe set beside a v0.8 one differs by this convention as well as by
  the engine; the [cash leg](#4-the-cash-leg) measures the convention alone on one engine.
- **Portfolio metrics annualise with the largest periods-per-year among the sleeves** (260
  when an FX pair is present, 252 for an all-equity book); a sleeve with no bar on a date
  contributes 0 that day.
- **EDGAR reconstruction has judgement in it.** Quarters are rebuilt per concept and per
  reporting basis: a re-print within 5% of the value held is a revision; a larger change
  opens a new basis generation only when corroborated, and a lone material re-print is
  ignored until repeated. The concept chosen for a window is the highest-ranked tag that
  covers it, so a filer that changes tags can lose a year of growth across the change (Apple
  2018 is such a gap); lagging windows are flagged rather than served as current; BRK-B has
  no P/E or FCF yield at any date. Every EDGAR-on number depends on this rule, which changed
  in every v0.8 fix round, so an EDGAR-on table is evidence only for the commit its provenance
  names.
- **The social analyst is still idle historically, and the fundamentals and news rules
  were never fitted.** v0.6 gives the fundamentals and news analysts real point-in-time
  data (SEC EDGAR); social media has no free point-in-time archive. The rules that read the
  filings were written against the synthetic provider and never tuned: with real data they
  add exposure and drawdown for about no Sharpe on the core names (trials registry, "EDGAR
  filings off": 0.65 against 0.66, exposure 60.48% against 63.31%, MDD 15.30% against 17.59%);
  tuning them is a rule change for the protocol, not a data fix.
- **Filing dates are days.** EDGAR gives the date a filing was accepted, not the time; a
  release after the close is treated as known on that day's decision. Consensus data does
  not exist in EDGAR, so the EPS-surprise input is always empty.
- **FRED serves the latest vintage.** Policy rates are not revised, but the few CPI inputs
  can differ slightly from what was first published. ALFRED vintages would remove this.
- **Two currencies have no usable policy-rate series.** Sweden's OECD series on FRED stopped
  in 2020-10, so a SEK leg gives no macro view, a strategic FX weight of 0 and NaN carry;
  Norway's was added in v0.8. No published instrument has a SEK or NOK leg.
- **Memory is provider-scoped.** Lessons and the track record are valued on one provider's
  series; entries written before v0.8 carry no provider, are never valued, and only expire
  (any named provider's visit past twice their horizon), so a migrated log drains rather than
  informs.
- **Book-level VaR exists but is unmeasured.** `max_book_var_95` (v0.7) caps the 95% VaR of
  the whole book across sleeves. The cap is off by default and was off in every published run;
  its coverage is untested. The per-instrument forecast the desk does size on was tested for
  the first time in v0.8 ([VaR coverage](#8-var-coverage-re-measured-and-labelled)) and is
  rejected by Kupiec on 2 of 15 core instruments and by Christoffersen on 6 of 15.
- **Anonymisation leaks through the shape of the return series.** The anonymiser replaces
  names, dates and price levels and passes only scale-free facts, but the return series
  itself, distinctive statistics (a -0.1% policy rate) and company names in real headlines
  can still identify the instrument and the date. No de-anonymisation probe has been run
  against a model, so the residual leakage is asserted, not measured.
- **The alpha gate is a per-alpha test with no multiplicity control.** Each alpha is admitted
  on its own |t(IC)| ≥ 2; across the eight equity alphas (the ninth, `carry`, is FX-only) the
  analyst speaks on about a fifth (≈22%, 43 of 200) of pure-noise histories in the
  200-random-walk test
  (`tests/test_v08_alpha.py::test_alpha_analyst_gate_is_a_five_percent_test_on_pure_noise`,
  which bounds it at 35%). How often it spoke in the published runs was not recorded.
- **Survivorship.** The equity universe is today's large caps, so it is biased towards
  names that did well. Buy & hold benefits from this at least as much as the agent.
- **The core universe is a small sample.** Differences in mean Sharpe below about 0.1
  between variants on 15 instruments (about 0.06 on the 45 extended ones) should be read as
  noise; the alpha-analyst result is an example.
- **No held-out data remains.** The holdout has been seen since v0.3; the reserve period and
  the extended universe were used to judge the v0.5.1 carry rule and the v0.6 EDGAR and
  cross-sectional decisions; v0.8 re-measures every period under the corrected engine. The
  next unseen data is the future (see
  [the next rule change](#the-next-rule-change-what-counts-as-unseen)).
- **The track-record cut's other-slice evidence is information, not a basis.** Removing the
  cut is worth about +0.01 of Sharpe on nearly every slice outside the core design period,
  which cannot tell the two apart; the default stays on because the protocol accepts only
  that period for a rule change, and the other slices are recorded for the next one.
- **Execution model.** Close-to-close fills, with costs as a fixed bps per unit of turnover
  and, optionally, square-root market impact scaled by account size and by the equity
  actually traded (the impact sweep above). Stops and take-profits fill at the level, or at
  the open on a gap. FX impact needs a configured notional ADV. There is no spread widening
  in stress and no venue or queue model.
- **A tool timeout is isolation, not termination.** A timed-out tool worker is abandoned and
  counted, not killed; a synchronous remote MCP tool may still finish and land its ticket
  after the deadline, so its outcome is unknown and is reconciled through the pending
  tickets, and state-changing tools get exactly one attempt.
- **Macro vintages.** FRED serves the latest revision. `fred_vintages` reads revised series
  (CPI) from the ALFRED vintage current at each date, sampled monthly, so inflation enters as
  first published; it is off in the published runs, which therefore carry a small revision
  leak in the FX inflation inputs (policy rates are never revised).
- **The measurement driver had a defect, found and fixed before publication.** The first v0.8
  run shared one Yahoo provider across runs, so the "EDGAR off" and "cash leg off" runs were
  measured with both still on; the zero differences exposed it, the driver now reconfigures
  the provider per run, and the affected files were re-measured (see
  [Reproducing](#reproducing)). Nothing from that first run is published.

Every number on this page and on the landing site is measured, not typed: see
[docs/GITHUB_PAGES.md "Keeping the landing page honest"](../GITHUB_PAGES.md#keeping-the-landing-page-honest)
for the process (and the re-measurement command) behind each figure, and the dependency-lock
note under [Reproducing](#reproducing) below for telling dependency drift apart from a real
change.

## Reproducing

**v0.8 (the current record).** Every table in [the v0.8 section](#v08-engine-and-protocol-corrections-and-every-number-re-measured)
comes from two scripts; nothing on that page is typed:

```bash
pip install -r requirements-lock.txt && pip install -e . --no-deps   # the lock is Python 3.12 only

.venv\Scripts\python.exe scripts/measure_v08.py                # about an hour on the C++ backend; --only eval_main,portfolio_holdout,... for a subset
.venv\Scripts\python.exe scripts/render_v08_tables.py          # prints every table and writes results/v08/tables.md

# the impact sweep is also an ordinary evaluate run (the flags parse since v0.8)
agentic-trader evaluate --data yahoo --universe core --periods design,holdout --impact 1.0 --capital 1e9 --out results/eval_impact_1e9.json
```

`measure_v08.py` writes `results/v08/*.json|csv`; a run whose output exists is skipped, so
re-running fills gaps. Every `results/v08/*.json` carries `provenance` (package version, git
commit and dirty flag, quant backend, Python, platform, dependency versions) and every
`--out` CSV has a `<stem>.provenance.json` sidecar; `results/v08/manifest.json` records the
run. The published files were written at three commits with identical engine and rules code:
`eval_main.json` at `c4385e2`; most of the rest at `eec0d27` (the `FIRM_CONTEXT` prompt
string and comments only; no engine, data or rules code); and the five files re-measured
after the shared-provider fix — `eval_noedgar`, `eval_cash_leg_off`, the two cash-leg-off
portfolios, `trial_edgar_filings_off` — together with `eval_rules_v03` and `eval_rules_v02`
at `ac727ce`, whose only code change since `eec0d27` is the additive
`MarketDataProvider.reconfigured()` / `YahooProvider.reconfigured()` that the driver fix
uses (`980ebf9`; it computes nothing — a provider built from the run's own config over the
same downloaded bars — and `ac727ce` itself touched only the renderer); the first run had
measured "EDGAR off" and "cash leg off" with both still on because the runs shared one
provider, and `MarketDataProvider.reconfigured(config)` now gives each run its own settings
on the same bars (details under
[reproducing the v0.8 numbers](#11-reproducing-the-v08-numbers)). A table whose provenance
does not name the commit under test is not evidence for that commit.

To rule out dependency drift as the reason a re-run differs from a published number, install
the exact versions [requirements-lock.txt](../../requirements-lock.txt) recorded them with
first (`pip install -r requirements-lock.txt && pip install -e . --no-deps`); with only
`pyproject.toml`'s lower bounds, `pip install -e ".[all]"` can legitimately resolve a
different numpy/pandas. The lock is the full transitive freeze of the environment that
produced the v0.8 numbers (CPython 3.12.10, win_amd64) and is valid for **Python 3.12 only**
(numpy 2.5.3 requires 3.12 or later); CI's `lock` job installs from it. A remaining
difference is then data drift (Yahoo's occasional revision of adjusted history, an EDGAR
cache built at a different time, a FRED series that has since been revised) or a real code
change, not the dependency resolution.

**Earlier releases (the historical record).** The commands below produced the v0.3–v0.7
sections; run under the current engine they give the v0.8 numbers, not the historical ones,
so they are kept for what each section measured rather than as a way to regenerate it.

```bash
pip install -e ".[all]"

# the core protocol on real prices (design, holdout, q1_2024), the 15 core instruments
agentic-trader evaluate --data yahoo --universe core --periods design,holdout,q1_2024 --out results/eval_v03.json

# the same with the v0.2 rule set, for the before/after comparison
agentic-trader evaluate --data yahoo --universe core --periods design,holdout,q1_2024 --rules v02 --out results/eval_v02.json

# v0.5: all 60 instruments on every period, and the impact sweep on the core universe
agentic-trader evaluate --data yahoo --universe all --periods design,holdout,q1_2024,reserve --out results/eval_v05_all.json
agentic-trader portfolio AAPL,NVDA,MSFT,META,GOOGL,AMZN,JPM,XOM,JNJ,SPY,EURUSD,USDJPY,GBPUSD,AUDUSD,USDCAD \
    --data yahoo --start 2022-01-03 --end 2026-06-30 --impact 1.0 --capital 1e9 --edgar-cache results/edgar_cache \
    --out results/portfolio_holdout_impact_1e9.csv

# v0.7: the same, worked as TWAP or Almgren-Chriss instead of the default VWAP-equivalent
agentic-trader portfolio AAPL,NVDA,MSFT,META,GOOGL,AMZN,JPM,XOM,JNJ,SPY,EURUSD,USDJPY,GBPUSD,AUDUSD,USDCAD \
    --data yahoo --start 2022-01-03 --end 2026-06-30 --impact 1.0 --capital 1e9 --edgar-cache results/edgar_cache \
    --execution-algo twap --out results/portfolio_holdout_impact_1e9_twap.csv
agentic-trader portfolio AAPL,NVDA,MSFT,META,GOOGL,AMZN,JPM,XOM,JNJ,SPY,EURUSD,USDJPY,GBPUSD,AUDUSD,USDCAD \
    --data yahoo --start 2022-01-03 --end 2026-06-30 --impact 1.0 --capital 1e9 --edgar-cache results/edgar_cache \
    --execution-algo ac --ac-kappa 5.0 --out results/portfolio_holdout_impact_1e9_ac.csv

# the alpha-analyst check (design period only)
agentic-trader evaluate --data yahoo --periods design --analysts technical,sentiment,macro,fundamentals,news,alpha

# v0.6: EDGAR off (the v0.5.1 record), EDGAR on (the default), and the cross-sectional analyst;
# EDGAR_USER_AGENT="Name email@domain" in .env; --edgar-cache keeps the SEC downloads
agentic-trader evaluate --data yahoo --universe all --periods design,holdout,q1_2024,reserve --no-edgar --out results/eval_v06_noedgar.json
agentic-trader evaluate --data yahoo --universe all --periods design,holdout,q1_2024,reserve --edgar-cache results/edgar_cache --out results/eval_v06_edgar.json
agentic-trader evaluate --data yahoo --universe all --periods design,holdout,q1_2024,reserve --edgar-cache results/edgar_cache \
    --analysts technical,fundamentals,news,sentiment,xalpha --xalpha-universe all --out results/eval_v06_xalpha.json   # peers: the 60 names, by asset class
# every evaluation prints the cross-instrument bootstrap; EvaluationResult.paired_table() reproduces the tables (scheme, groups and BH columns since v0.8)

# v0.6: the multi-year LLM run, staged with a dollar cap per stage (control, Opus, Sonnet, Haiku, repeats, calibration) -- not yet executed
agentic-trader evaluate --data yahoo --universe core --periods design,holdout --every 10 --rounds 1 --edgar-cache results/edgar_cache --out results/llm_control.json
agentic-trader evaluate --data yahoo --universe core --periods design,holdout --every 10 --rounds 1 --edgar-cache results/edgar_cache \
    --llm anthropic --deep-effort medium --anonymize --workers 4 --max-llm-cost 650 --out results/llm_opus.json
agentic-trader evaluate --data yahoo --universe core --periods design,holdout --every 10 --rounds 1 --edgar-cache results/edgar_cache \
    --llm anthropic --deep-model claude-sonnet-5 --deep-effort medium --anonymize --workers 4 --max-llm-cost 350 --out results/llm_sonnet.json
agentic-trader evaluate --data yahoo --universe core --periods design,holdout --every 10 --rounds 1 --edgar-cache results/edgar_cache \
    --llm anthropic --deep-model claude-haiku-4-5 --anonymize --workers 4 --max-llm-cost 150 --out results/llm_haiku.json
agentic-trader evaluate AAPL,NVDA,MSFT,META,GOOGL --data yahoo --periods holdout --every 10 --rounds 1 --edgar-cache results/edgar_cache \
    --llm anthropic --deep-effort medium --anonymize --workers 5 --repeats 3 --max-llm-cost 260 --out results/llm_repeats.json
agentic-trader calibrate AAPL --date 2024-03-01 --n 5 --anchors none,-0.5,0,0.5 --data yahoo --rounds 1 --edgar-cache results/edgar_cache \
    --llm anthropic --deep-effort medium --anonymize --max-llm-cost 12 --out results/calibration_opus.json

# the portfolio view
agentic-trader portfolio AAPL,NVDA,MSFT,META,GOOGL,AMZN,JPM,XOM,JNJ,SPY,EURUSD,USDJPY,GBPUSD,AUDUSD,USDCAD \
    --data yahoo --start 2022-01-03 --end 2026-06-30 --out results/portfolio_holdout.csv

# selection statistics for a returns series against the variants tried (the 16 v0.3 trials; v0.8 reads the 26 from evaluation.TRIALS)
agentic-trader stats results/portfolio_design.csv --column AgenticTrader \
    --trial-sharpes 0.496,0.465,0.483,0.512,0.496,0.471,0.509,0.511,0.497,0.535,0.577,0.655,0.579,0.583,0.652,0.561

# v0.7: the rolling historical VaR of the same holdout portfolio returns, at both window lengths
agentic-trader stats results/portfolio_holdout.csv --column AgenticTrader --var-backtest --var-window 120
agentic-trader stats results/portfolio_holdout.csv --column AgenticTrader --var-backtest --var-window 250
```

The ablation variants are ordinary config overrides (see the tables above; since v0.8 they
are registered in `evaluation.TRIALS`). Cookbook recipe 28 shows how to run one, recipe 56
the selection report, recipe 57 an impact backtest and recipe 64 the universe partition.
Yahoo occasionally revises adjusted history, so re-runs can differ in the second decimal; the
historical extended-universe tables above were generated from their saved JSON with pandas,
and the v0.8 tables by `scripts/render_v08_tables.py`, like every other table here.
