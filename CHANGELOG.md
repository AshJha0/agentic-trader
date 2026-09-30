# Changelog

## Unreleased — v0.11: the tier-2 review

A second adversarial review (337 agents: ten finders, a constructive alpha-proposal track,
two or three verification lenses per finding, a gap round and a three-judge panel) produced
110 findings, 89 confirmed (11 high, 56 medium, 22 low); the digest with every verifier's
reasoning is the record. Nothing here changes a rule choice on published data; the behaviour
changes below move the next re-measurement (`results/v11`, [v011_review.md](docs/evaluation/v011_review.md)).

- **EDGAR is visible when it was accepted, not when it was dated.** A filing accepted at or
  after 16:00 Eastern is public from the next session; the submissions feed's
  `acceptanceDateTime` (UTC) is converted and joined to every XBRL fact by accession number.
  Filings without a known acceptance time keep their filing date. Facts, fundamentals and the
  filing news stream all use the visible date.
- **Market impact prices dollar volume in the shares' own units**: the dollar ADV uses the
  split-adjusted, dividend-unadjusted close (`MarketDataProvider.as_traded_closes`) instead of the
  total-return close, which understated dollar volume on high-yield names.
- **The aggressive risk analyst sizes at 1.25× the vol-targeted weight** (`risk.aggressive_vol_scaled`,
  default on). The v0.8 rule, `max(1.25 × proposal, vol target)`, pinned the aggressive view at the
  position cap and gave the blended book a fixed floor at a quarter of the cap; the old rule is a
  registered trial and the v0.2 rule set keeps it.
- **The news analyst's confidence follows the tone the headlines carry** (`rules.news_tone_mass`,
  default on): a window of toneless filings is an abstention, not a zero vote at up to 0.7
  confidence; the v0.8 count rule is a registered trial.
- **Evaluation rows are stored at full precision** (`ComparisonReport.table(decimals=None)`); every
  aggregate, interval and p in a re-measured table runs on unrounded per-instrument metrics.
- **Benjamini–Hochberg runs over the rows a table prints** (`paired_table(baselines=...)`): the
  control-only drawdown and Calmar tables were corrected over six baselines and then cut to two.
- **The deflated Sharpe is computed on one statistic**: every reproducible trial's design-period
  15-sleeve portfolio Sharpe (`scripts/measure_v08.py` measures it; `selection_report` warns when the
  chosen Sharpe is more than three trial standard deviations above the best trial). The v0.8 number
  is withdrawn as a "clears the bar" claim.
- **The trials registry counts v0.9, v0.10 and the new switches**: 44 entries (`Trial.recorded_portfolio_sharpe`
  for the return-level trials).
- **Engine parity and validation**: a NaN risk-free rate reads as 0 on the numpy backend as it does
  in C++; `BacktestConfig` fields are validated (finite non-negative costs, finite leverage and carry)
  before either backend runs.
- **The harness's critic, reporter and planner prompts are anonymised** with the analysts'
  (`agents.base.complete_anon`); the reporter drops price levels from the prompt; the planner names
  neither the instrument nor the date and clips the question.
- **A plan is single-use**: `execution.submit_order` consumes the plan it ticketed and refuses the
  same plan again (`DeskTools.ticketed`, a lock shared by every book view).
- **The hard LLM budget admits every attempt**: `BudgetedLLM` reserves one more attempt before each
  retry (`AnthropicLLM.admit_retry`) and prices the prompt at its actual size, so retried timeouts
  cannot overshoot the cap.
- **Decision memory catches up on a shared file**: every read and write first ingests lines other
  processes appended (append-only log, byte offset), so `serve --processes N` shares lessons and the
  track record.
- **The forward record is append-only** (`scripts/paper_trade_v09.py`): recomputed sessions are added,
  never rewritten; differences go to `revisions.csv`; a shrinking recomputation is refused; a sleeve
  whose bars stop early is an error; the summary names the pre-registered decision look (3,600
  sessions, see the amendment in `docs/evaluation/v09_preregistration.md`).
- **Renderer**: `--section` writes its own file; the execution-algorithm table averages impact over
  the sleeves that can pay it (FX sleeves pay none without `costs.fx_adv_notional`).
- **Re-measured (`results/v11`, copied to `docs/results/v11/tables.md`; every file at a clean commit).**
  15-sleeve portfolio, holdout: desk Sharpe 0.91 with a 6.41% drawdown (v0.8: 0.80 / 7.80%) against 0.86
  buy & hold and 0.99 vol-target; desk − vol-target −0.08 [−0.46, +0.30] p 0.688, desk − buy & hold +0.05
  [−0.40, +0.50] p 0.820. Core holdout median Sharpe 0.35 (v0.8: 0.30) against 0.52 for the control, paired
  difference −0.08 [−0.18, +0.02] p 0.14; extended 0.21 (v0.8: 0.25) against 0.27. The desk still has no
  measurable edge over the vol-targeted control. Design-period choice of the two rule changes: the
  vol-scaled aggressive stance gives portfolio Sharpe 1.44 against 1.40 for the v0.8 rule; the news
  tone-mass rule 1.44 against 1.44 (kept for correctness, not for Sharpe); a symmetric equity tilt 1.45
  (inside noise, not adopted). Deflated Sharpe on one statistic: 42 trials with a portfolio Sharpe,
  expected maximum 0.746, probability 0.949 (an upper bound; v0.8's 0.998 is withdrawn). The
  cross-sectional analyst's four-period re-check was not re-measured in v0.11 (it is off by default and
  its v0.8 result stands); its design-period trial was.
- The rendered result tables are in the repository (`docs/results/v08`, `v09`, `v11`), so every published
  number can be read without the machine that measured it.
- Docs: survivorship's direction for the alpha library, eight baselines in the API reference, the
  impact "% of equity" wording (a sum of daily charges, not a terminal loss).

## Unreleased — v0.9 research (branch `research/v0.9-multi-asset`)

The Sharpe plan that followed v0.8: attribution first, then a multi-asset base, trend and
carry streams, their combination, and a forward test. Every number is in
[docs/evaluation/v09_research.md](docs/evaluation/v09_research.md) (generated from
`results/v09` by `scripts/render_v09_doc.py`) and the rule for what the holdout run may
mean was written before it ran ([docs/evaluation/v09_preregistration.md](docs/evaluation/v09_preregistration.md)).

- **Attribution** (`scripts/attribution_v09.py`): against the vol-target control the v0.8
  desk has beta 0.92 (design) / 0.89 (holdout), R² 0.89 / 0.86, alpha +0.41%/yr (t 0.40) /
  −0.80%/yr (t −0.68); the active tilt's Sharpe is −0.17 [−0.90, +0.56] and −0.61
  [−1.51, +0.29]. The signals add nothing over holding the same sleeves mechanically.
- **Two return streams as baselines in every sleeve**, fully costed and combinable by the
  portfolio machinery: `TSMOM(12-1)` (sign of the trailing 12-month return skipping the last
  month, at the vol-target size, long-only where shorts are not allowed) and `Carry` (the
  FX carry premium at the desk's strategic size; flat on equities). Every `backtest`,
  `baselines`, `portfolio` and `evaluate` table gains the two rows.
- **Design-period verdict (2016–2021), nothing adopted**: the 11-ETF risk-parity base
  (`B&H vol-target`) has Sharpe 1.02 against the v0.8 core-15 control's 1.43; risk parity
  on the core 15 gives 0.91 (it overweights FX sleeves that earn nothing); ETF trend 0.50,
  −0.52 [−0.89, −0.15] p 0.007 against its control; FX carry 0.13, +0.05 [−0.98, +1.08];
  every risk-parity book with trend or carry is at or below the base (beta + trend −0.24
  [−0.42, −0.05] p 0.012). Six books and five runs count as trials.
- **The pre-registered holdout report (2022–2026)**, a report and not a choice: the
  bond-heavy base −0.09, ETF trend 0.16, FX carry 0.43, the core-15 controls 1.28–1.32;
  no difference clears its interval.
- **The forward test** (`scripts/paper_trade_v09.py`): from 2026-09-29 a daily job
  recomputes the frozen books' returns (the v0.8 desk on the core 15 with its controls, the
  ETF base with trend, the FX pairs with carry and trend), writes `results/paper/ledger.csv`,
  a summary with block-bootstrap intervals after 60 sessions, and a `runs.jsonl` line with
  provenance and any revision of an earlier return. A candidate is adopted only when its
  forward Sharpe minus its control's clears an interval that excludes zero.
- Drivers: `scripts/measure_v09.py` (`--period design|holdout`), `scripts/combine_v09.py`
  (risk parity across streams, drawdown overlay), `scripts/render_v09_tables.py`,
  `scripts/render_v09_doc.py`. Tests: `tests/test_v09.py`, `tests/test_v09_paper.py`.

## v0.8.0 — 2026-09-28

A tier-1 review of v0.7.0 -- the code, the tests and every claim in the documentation --
produced 91 findings (17 high, 58 medium, 16 low; the digest with each verifier's reasoning
is the record). The code changes for them are in this release, one bullet per finding group
below; the findings about what the documentation claimed are answered by retracting the
claims and re-measuring. The engine changed in ways that move every backtest-derived number
(constant units between decisions, a cash leg, equity-scaled impact, the desk told its true
position after a stop), so no number from v0.7 or earlier is carried forward: `scripts/measure_v08.py`
re-measures every published table into `results/v08/` (each file carries `provenance`) and
`scripts/render_v08_tables.py` prints the tables the documents paste. Numbers produced by the
synthetic provider are unchanged by the cash leg (its rate is the constant 0 there); real-data
numbers are not.

### Retracted
- **The v0.7 "stratified bootstrap"** (`stats.paired_bootstrap(groups=...)`, the default in
  `EvaluationResult.paired` since v0.7). Resampling within each group with the group's count
  held fixed removes the between-group component of the variance: it can only *narrow* the
  interval and lower `p`, the opposite of what the v0.7 entry claimed, and it does nothing
  about correlation inside a cluster. Every interval, `p` and BH flag printed by
  `agentic-trader evaluate` under v0.7 defaults is withdrawn (finding 4). Replaced by a
  two-stage cluster bootstrap, below; the v0.6 tables, which used the plain instrument
  bootstrap, stand and are now labelled `scheme=instruments`.
- **The magnitudes in the v0.7 execution-algorithm table** (VWAP 2.37% / TWAP 2.51% /
  Almgren-Chriss 3.14% of equity to impact on the $1B 15-sleeve holdout portfolio, and its
  Sharpe column). `run_portfolio_backtest` ran every sleeve with the whole book's capital and
  combined them at 1/N, so with impact proportional to the square root of capital each sleeve
  paid sqrt(15) = 3.87 times what a sleeve of $1B/15 pays (finding 1). The ordering
  VWAP < TWAP < AC is a property of the schedules and survives; the table is re-measured at
  the sleeve's own capital under Re-measured results.
- **"The desk's own risk model is well-calibrated"** (the v0.7 VaR-coverage entry, the
  evaluation's VaR section and LEARN #34). What was tested was a 120/250-day rolling
  historical quantile of the 15-sleeve portfolio's *own realised returns* against those same
  returns. The forecast the desk sizes on -- the 250-day historical VaR of each instrument's
  price returns, times |weight|, against `max_var_95` -- was never tested, and book-level VaR
  (`max_book_var_95`) was off in every published run (findings 28, 62). v0.8 tests the
  per-instrument forecast against each core instrument's next-day return over the holdout;
  the portfolio-returns test is kept and labelled as exactly that.
- **The headline results** of v0.5 through v0.7 -- per-instrument Sharpe against buy & hold,
  the 15-sleeve portfolio's "beats plain buy & hold on Sharpe", "about half of buy & hold's
  drawdown", the impact sweep and the EDGAR deltas -- were measured under an engine that
  credited nothing on idle cash and used a risk-free rate of 0 (finding 14), compared
  drawdown against 100%-invested buy & hold rather than the vol-targeted control the
  evaluation itself names as fair (finding 66), and reported the EDGAR gain on extended
  equities as "intervals that exclude zero" when the project's own FDR correction did not
  flag it (finding 61). All of them are re-measured in this release, on excess returns with
  the cash leg credited; whether each claim still holds is stated, with its interval, under
  Re-measured results. Measured, the portfolio claim does not hold: on the
  holdout the 15-sleeve desk's Sharpe is 0.80 against plain buy & hold's 0.86, a difference of
  -0.06 [-0.41, +0.30] p 0.748 (paired block bootstrap over days), so **"beats plain buy &
  hold on Sharpe" is retracted**; with the cash leg off the order is the same (1.04 against
  1.05), so the v0.7 figure was inside the noise under either convention.
- **"$1B: MACD loses three quarters of its equity to impact"** (the v0.5 impact-sweep
  sentence, LEARN #28). It was measured with impact charged at the constant initial capital
  (finding 23); with impact following the equity, the core-universe MACD baseline pays 64.71%
  of equity in impact on the design period at $1B and 39.01% on the holdout
  (`results/v08/tables.md`, impact sweep). The sentence is withdrawn and the sweep is under
  Re-measured results.
- **"The reserve period is untouched by every choice"** (the evaluation's periods table,
  LEARN #27, README and the landing page). The reserve (2026-07-01 to 2026-09-25) and the
  extended universe were consulted for the v0.5.1 carry rule and the v0.6 EDGAR and
  cross-sectional decisions, and v0.8 re-measures every period, so no held-out data remains:
  the next unseen data is the future (finding 64).

### Re-measured results
Every measured number here is copied from `results/v08/tables.md` (the earlier releases'
figures quoted beside their retraction or replacement, and the v0.5.1 LLM record, are
labelled as such and are not in the tables), which `scripts/render_v08_tables.py` renders
from the files `scripts/measure_v08.py` wrote to `results/v08/` (the section named in each
bullet is the table it came from; the full tables are in
[the evaluation's v0.8 section](docs/evaluation/evaluation.md#v08-engine-and-protocol-corrections-and-every-number-re-measured)).
Conventions: Sharpe and Sortino are on returns in excess of the credited 3-month bill
(FRED DTB3, one-day publication lag); CR, AR, MDD and Calmar are total return; summary
tables quote the *median* Sharpe across instruments and paired tables the *mean* difference
with its 95% bootstrap interval, `p` and, on the paired Sharpe, MDD% and Calmar tables, the
Benjamini-Hochberg flag over the unrounded `p` across the table (the (a)-versus-(b) re-check
tables print `p` but no BH column); the bootstrap scheme is `instruments` on core (15 = 10
equities + 5 FX pairs) and extended (45 = 26 sector equities, 9 macro ETFs, 10 FX crosses)
and `clusters` (two-stage over the five asset-class-by-universe groups) on all 60. An
interval printed as [0.00, x] or [-0.00, x] is not "excluding zero". Periods: design
2016-2021, holdout 2022-mid-2026, q1_2024, reserve 2026-07-01 to 2026-09-25.
- **Per instrument, out of sample, the desk is below buy & hold on Sharpe, and below the
  vol-targeted control** ("summary: core (15), holdout"; "paired Sharpe, agent minus
  baseline"). Core holdout median Sharpe 0.30 (desk) vs 0.51 (B&H) vs 0.52 (B&H vol-target);
  paired mean difference desk - B&H -0.10 [-0.21, -0.00] p 0.04, not BH-significant; desk -
  vol-target -0.11 [-0.21, -0.00] p 0.04, not BH-significant. Extended holdout medians 0.25
  vs 0.39 vs 0.27; desk - B&H -0.07 [-0.12, -0.02] p 0.01, BH-significant; desk - vol-target
  -0.03 [-0.09, +0.02] p 0.19, not BH-significant. All 60 (clusters): desk - B&H -0.08
  [-0.15, -0.03] p 0.00, BH-significant; desk - vol-target -0.05 [-0.15, 0.00] p 0.07, not
  BH-significant. Design period, core: medians 0.67 vs 0.73 vs 0.69; desk - B&H +0.06
  [-0.06, +0.17] p 0.29, not BH-significant. v0.7's "noise either way" is superseded: on the
  names the rules never saw, the Sharpe deficit against buy & hold clears the BH bar. The
  desk stays ahead of the signal-flipping baselines on most slices (holdout, all 60: desk -
  SMA(20/50) +0.25 [+0.01, +0.43] p 0.04, not BH-significant; holdout, extended: +0.28
  [+0.16, +0.41] p 0.00, BH-significant; design, core: desk - MACD +0.26 [+0.09, +0.43] p
  0.00, BH-significant).
- **Drawdown against the fair control** ("paired MDD%, agent minus control", "summary by
  asset class", "paired Calmar"). Core holdout mean MDD 17.40% (desk) vs 31.64% (B&H) vs
  18.98% (vol-target); paired desk - B&H -14.24 points [-20.41, -8.70] p 0.00,
  BH-significant; desk - vol-target -1.58 [-4.33, +1.14] p 0.27, not BH-significant. On the
  ten core equities, the names the rules were tuned on, holdout mean MDD is 22.11% vs 40.24%
  vs 21.28% and desk - vol-target is +0.83 [-1.63, +3.21] p 0.50, not BH-significant: the desk's drawdown is not
  below the fair control's there. Extended holdout: 15.46% vs 26.39% vs 19.79%; desk -
  vol-target -4.33 [-6.10, -2.55] p 0.00, BH-significant; desk - B&H -10.93 [-13.41, -8.64]
  p 0.00, BH-significant. On FX the vol-target control sits at the shared 1.0 position cap
  most of the time and coincides with buy & hold (core FX holdout: mean MDD 14.40% vs 14.45%,
  exposure 94.43% vs 92.17%), so the FX drawdown comparison has no separate control. Calmar,
  extended holdout: desk - B&H +0.11 [+0.03, +0.19] p 0.00, BH-significant; desk - vol-target
  +0.07 [0.00, +0.14] p 0.05, not BH-significant. "About half the drawdown" is true against
  plain buy & hold and is almost entirely volatility scaling.
- **The 15-sleeve equal-capital portfolio beats neither control on Sharpe** ("portfolio:
  holdout", "portfolio Sharpe difference (paired block bootstrap over days)",
  "rebalance-phase sweep"). Holdout: desk Sharpe 0.80, CR 50.62%, MDD 7.80%, exposure
  59.10%; B&H 0.86 / 96.91% / 20.43%; vol-target 0.99 / 61.48% / 9.17%. Paired block
  bootstrap over days (block 10, n 1167): desk - B&H -0.06 [-0.41, +0.30] p 0.748; desk -
  vol-target -0.19 [-0.53, +0.16] p 0.297. Design (n 1564): desk 1.40 vs B&H 1.28 vs
  vol-target 1.43; desk - B&H +0.12 [-0.16, +0.40] p 0.434; desk - vol-target -0.03 [-0.28,
  +0.23] p 0.898. The rebalance-phase sweep (holdout, offsets 0-4) puts the desk at 0.80 /
  0.85 / 0.86 / 0.80 / 0.84 (spread 0.06) against a fixed 0.99 (vol-target) and 0.86 (B&H):
  the cadence noise floor is the size of the portfolio differences quoted. The v0.7 "beats
  plain buy & hold on Sharpe" (1.09 vs 1.06) is retracted above.
- **The cash leg lowered every strategy's holdout Sharpe and leaves the desk below both
  controls under either convention** ("cash leg on vs off: holdout / design"; "cash leg off
  (a) vs on (b)"). Under
  `cash_leg: auto` (the default) an equity position is funded, so `(1 - |w|)` of the account
  earns the bill; an FX forward leaves the whole account earning it; Sharpe and Sortino are
  on excess returns; `cash_leg: "off"` credits nothing and uses `risk_free_annual` (0), the
  v0.7 convention; synthetic data is unchanged either way (its rate is the constant 0).
  Holdout portfolio, cash leg on -> off: desk 0.80 -> 1.04 (CR 50.62% -> 35.17%, MDD 7.80% ->
  8.01%); B&H 0.86 -> 1.05 (96.91% -> 86.23%); vol-target 0.99 -> 1.24 (61.48% -> 46.21%);
  SMA(20/50) 0.64 -> 0.85; MACD 0.38 -> 0.54. Design portfolio: desk 1.40 -> 1.46 (CR 93.64%
  -> 87.97%), B&H 1.28 -> 1.32, vol-target 1.43 -> 1.49. Per instrument, agent Sharpe with
  the leg off minus on (these on/off tables carry `p` but no BH column): holdout core +0.10
  [+0.06, +0.15] p 0.00, extended +0.17 [+0.13, +0.21] p 0.00, all 60 +0.15 [+0.04, +0.23] p
  0.02 (clusters); design core +0.03 [+0.02, +0.04] p 0.00, all 60 +0.04 [+0.01, +0.06] p
  0.01. Reading: 2022-2026 bills paid several percent a year, so an excess-return Sharpe is
  lower for everyone; crediting the desk's idle capital raises its cumulative return (35.17%
  -> 50.62%) but not its excess-return Sharpe by as much as the bill takes from a
  low-volatility strategy, while buy & hold holds almost no cash; 2016-2021 bills were near
  zero, so the design period barely moves. Of the v0.7 -> v0.8 holdout portfolio move 1.09
  -> 0.80, the cash-leg convention accounts for 1.04 -> 0.80, measured here on one engine;
  the remaining 1.09 -> 1.04 (the other engine corrections plus any data drift since
  2026-09-25) is a difference between two records across two engines, not a measured
  effect. Under either convention the holdout order is desk < B&H < vol-target (1.04 / 1.05
  / 1.24 off; 0.80 / 0.86 / 0.99 on). The README headline follows the cash-leg-on numbers.
- **Impact, equity-scaled, textbook coefficient 1.0, core universe** ("impact sweep"). Desk
  Sharpe with impact off / at $100k / $10M / $1B: design 0.66 / 0.66 / 0.66 / 0.61 (impact
  paid 0.04% / 0.43% / 4.24% of equity), holdout 0.34 / 0.34 / 0.34 / 0.31 (0.03% / 0.26% /
  2.53%). B&H vol-target: design 0.64 -> 0.57 at $1B (6.92%), holdout 0.45 -> 0.41 (3.57%);
  SMA(20/50): 0.57 -> 0.38 (24.63%) and 0.18 -> 0.04 (12.99%); MACD: 0.40 -> -0.18 (64.71%)
  and 0.14 -> -0.30 (39.01%). v0.7's "the desk loses 0.09 Sharpe at $1B" is replaced by these
  figures.
- **Execution algorithms at $1B, holdout portfolio, sleeve impact at the sleeve's capital**
  ("execution algorithm, $1B holdout portfolio"): VWAP Sharpe 0.78 / CR 49.62% / MDD 7.83% /
  mean sleeve impact paid 0.66%; TWAP 0.78 / 49.56% / 7.83% / 0.70%; Almgren-Chriss kappa=5
  0.77 / 49.30% / 7.84% / 0.87%. The v0.7 magnitudes (2.37% / 2.51% / 3.14%) are retracted
  above; the ordering VWAP < TWAP < AC survives, the magnitudes do not.
- **EDGAR on vs off, re-checked under the per-tag, per-basis reconstruction** ("EDGAR on (a)
  vs off (b)"; every earlier EDGAR figure is superseded; this and every (a)-versus-(b)
  re-check table below, through the track-record cut, carry `p` but no BH column, so none
  of their rows is called BH-significant). Agent mean Sharpe with the filings minus without:
  design core +0.01 [-0.03, +0.04] p 0.72 (4 / 15 wins; the filings reach the
  ten equities only), design extended +0.01 [+0.00, +0.02] p 0.02 (16 / 45), design all 60
  +0.01 [-0.01, +0.02] p 0.19 (clusters); holdout core -0.01 [-0.07, +0.04] p 0.83, holdout
  extended +0.03 [+0.01, +0.06] p 0.00 (15 / 45), holdout all 60 +0.02 [-0.02, +0.05] p 0.39;
  q1_2024 core +0.09 [+0.00, +0.21] p 0.02; reserve core +0.11 [+0.00, +0.23] p 0.04,
  reserve extended +0.03 [-0.04, +0.10] p 0.45. The core design period, the choice basis,
  cannot tell on from off; the extended equities, which no rule was tuned on, show a small gain with the cluster interval
  covering zero. The data stays on (it is a data source, not a rule, and the design period
  shows no harm); the untuned rules that read it remain the next protocol item. Trials
  registry: "EDGAR filings off" design mean Sharpe 0.65 vs 0.66 with them, CR 110.44% vs
  118.18%, MDD 15.30% vs 17.59%, exposure 60.48% vs 63.31% -- the filings add exposure and
  drawdown on the core names for about no Sharpe, the v0.6 finding re-measured.
- **FX carry-neutral rule on vs off** ("FX carry rule on (a) vs off (b)"; the v0.5.1 rule):
  design core +0.04 [-0.01, +0.10] p 0.11 (4 / 15 wins: the rule touches FX only); holdout
  core +0.02 [-0.02, +0.07] p 0.37; holdout extended +0.04 [+0.00, +0.08] p 0.04; holdout all
  60 +0.03 [-0.00, +0.12] p 0.23 (clusters); q1_2024 core +0.49 [+0.12, +0.94] p 0.01;
  reserve extended +0.14 [+0.03, +0.28] p 0.00. Positive on every slice, small, with the
  interval touching zero on most.
- **v0.3 rules vs v0.2 rules, core** ("v0.3+ rules (a) vs v0.2 rules (b), core"): design
  +0.19 [+0.10, +0.28] p 0.00 (12 / 15 wins); holdout -0.00 [-0.11, +0.09] p 0.99 (0.34 vs
  0.34, 8 / 15); q1_2024 +0.72 [+0.29, +1.17] p 0.00; reserve +0.95 [+0.45, +1.47] p 0.00.
  The design-period gain of the chosen rules did not carry to the holdout at all (v0.7 said
  it "shrank"); the two short windows favour v0.3.
- **Cross-sectional analyst vs default** ("with the cross-sectional analyst (a) vs default
  (b)"): design core -0.01 [-0.02, +0.00] p 0.36; holdout core 0.00 [-0.01, +0.02] p 0.60;
  holdout extended -0.00 [-0.01, +0.00] p 0.23; q1_2024 core +0.09 [+0.00, +0.20] p 0.04;
  reserve extended -0.02 [-0.06, +0.01] p 0.20. Off by default stands.
- **Alpha analyst with the corrected gate vs default, core** ("with the alpha analyst,
  corrected gate (a) vs default (b)"): design -0.00 [-0.05, +0.05] p 0.90; holdout -0.00
  [-0.04, +0.02] p 0.79; q1_2024 +0.10 [+0.01, +0.23] p 0.01; reserve +0.07 [-0.00, +0.20] p
  0.21. Off by default stands: the design period shows nothing. How often the corrected gate
  speaks on real data was not recorded by the driver (the result metadata carries no
  abstention tally), so it is not measured.
- **Track-record size cut off vs on** ("track-record size cut off (a) vs on (b)"): design
  core +0.00 [-0.00, +0.01] p 0.51; design extended +0.01 [+0.00, +0.01] p 0.01; design all
  60 +0.01 [+0.00, +0.01] p 0.03 (clusters); holdout core +0.01 [-0.01, +0.02] p 0.46;
  holdout extended +0.01 [+0.00, +0.02] p 0.02; q1_2024 extended +0.04 [+0.01, +0.07] p 0.00;
  reserve core +0.04 [+0.00, +0.09] p 0.04. Removing the cut is worth about +0.01 on nearly
  every slice, but the core design period, the only basis the protocol accepts for a rule
  change, cannot tell the two apart: the default stays on (`rules.track_record_cut: True`)
  and the other slices are recorded as information for the next rule change, not as a choice
  basis.
- **VaR coverage, two labelled tests** ("VaR coverage: rolling historical VaR of the
  15-sleeve portfolio's own returns"; "VaR coverage: the desk's own per-instrument
  forecast"). (a) Rolling historical VaR of the holdout portfolio's own returns: 120-day
  window n 1048, 65 breaches, rate 0.0620, Kupiec p 0.0847, Christoffersen p 0.1488,
  conditional coverage p 0.0798 -- not rejected at 5%, but close; 250-day window n 918, 42
  breaches, 0.0458, Kupiec p 0.5493, Christoffersen p 0.1650, conditional coverage p 0.3188.
  (b) The forecast the desk sizes on, the 250-day historical VaR of each core instrument
  (`agents/risk.py` risk_facts), against next-day returns over the holdout (n 1126 equities,
  1167 FX): Kupiec rejects at 5% on 2 of 15 (AAPL, breach rate 0.0657, p 0.0207; AUDUSD,
  0.0634, p 0.0432); every breach rate is above 5% (0.0523 to 0.0657); Christoffersen
  independence rejects on 6 of 15 (AAPL p 0.0027, SPY 0.0121, JPM 0.0158, GBPUSD 0.0182, META
  0.0274, USDCAD 0.0441): breaches cluster. Book-level VaR (`max_book_var_95`) was off in
  every published run and its coverage is untested.
- **Selection statistics, 26 trials** ("selection statistics for the frozen rules"; "trials
  registry"). Design-period 15-sleeve portfolio: n 1564 days, annual Sharpe 1.375, t 3.42,
  skew -0.635, kurtosis 8.41, bootstrap 95% CI [0.593, 2.17], PSR vs 0 = 1.00, expected
  maximum Sharpe of 26 null trials 0.161, deflated Sharpe probability 0.998, minimum track
  record 496 periods -- "an upper bound on the true significance: the benchmark is built
  from the dispersion of trial_sharpes_annual, which is usually narrower than the dispersion
  of the full return series each trial would have produced, so the true search space is wider
  than this reports and the real probability is no higher than the number given." The 24
  reproducible trials re-measured under the v0.8 engine against the v0.3 record: control 0.47
  (recorded 0.50); strategic equity weight 0.25 / 0.50 / 1.00 = 0.54 / 0.58 / 0.63 (recorded
  0.54 / 0.58 / 0.66); frozen v0.3 0.62 (0.65). The reading of the 16-variant ablation is
  unchanged, though not every rank (the strategic-weight ranking 0.25 < 0.50 < 1.00 holds
  under both engines; the signal tweaks, alone or on top of strategic 0.50, reorder among
  themselves): the strategic weight is the one change that matters (control 0.47, CR 58.24%,
  exposure 43.99% -> strategic 1.00 0.63, 121.95%, 60.37%), the signal tweaks move the mean
  Sharpe by a few hundredths. "+ intraday stops": 0.45 / CR 44.10% / MDD 12.67% / 292.20
  trades per instrument vs the control's 0.47 / 58.24% / 13.31% / 254.20 (stops cut the
  cumulative return by about a quarter at a similar Sharpe; the "about 30%" of earlier
  documents is replaced); "+ no-trade band 0.10": 0.47 / 58.11% with 135.20 trades vs 254.20
  (the same Sharpe with far fewer trades; replaces "44% fewer"). Trials added since v0.3:
  the v0.5 gated alpha analyst (0.66), the four v0.5.1 carry variants (0.65 / 0.66 adopted /
  0.65 / 0.64), the v0.6 cross-sectional analyst (0.66) and EDGAR off (0.65), and the v0.8
  track-record cut off (0.66); the two v0.4 alpha-analyst variants are historical (recorded
  0.60 and 0.58, not re-measured).
- **Nothing remains unseen.** The reserve period and the extended universe were consulted
  for the v0.5.1 carry rule and the v0.6 EDGAR and cross-sectional decisions, and this
  release re-measures every period, so the next unseen data is the future; "untouched by
  every choice" is retracted above. The three-month reserve says little on its own
  ("summary: core (15), reserve"; "paired Sharpe, agent minus baseline"): core desk median
  Sharpe 0.81 vs 1.05 (B&H) and 1.05 (vol-target), paired desk - B&H -0.06 [-0.21, +0.12] p
  0.44 and desk - vol-target -0.06 [-0.24, +0.14] p 0.53, neither BH-significant; extended
  -0.11 vs -0.08 / -0.11, paired +0.08 [-0.14, +0.33] p 0.54 and +0.07 [-0.15, +0.33] p 0.61,
  neither BH-significant.
- **The LLM desk is not re-measured.** The one language-model measurement is still v0.5.1's
  (five stocks, one quarter, about $4), produced under the v0.7-and-earlier engine and not
  re-derived under v0.8; the multi-year LLM harness is unexecuted. Wherever those numbers
  are quoted they are labelled so.

### Engine
- **Constant units between decisions** (finding 79). A target is executed on a decision bar;
  between decisions the position drifts with the market and nothing is charged. v0.7 held the
  *weight* constant, which is a free daily rebalance; the desk's own turnover was partly
  never paid for. Costs are multiplicative and sizing is post-cost:
  `E[t+1] = E[t] (1 - k_in) (1 + g) (1 - k_out)`. The leverage cap binds on targets;
  `positions[t]` is now the drifted weight and can sit above the cap between decisions.
  Turnover comes from the per-bar traded fraction (`BacktestResult.traded`, exit fills
  included) and the trade count from executed trades. FX carry accrues on the constant
  notional, which moves the FX baselines by more than the equity ones.
- **A cash leg, and Sharpe on excess returns** (finding 14). `run_backtest(cash_rate=...)`
  credits `(1 - |w|) * rf` per bar on funded positions (equities) and the full capital's `rf`
  on FX forwards; `compute_metrics` takes a constant or a per-bar rate and computes Sharpe,
  Sortino and the t-statistic on `r_t - rf_t`. Annualised return, cumulative return and
  Calmar remain total-return quantities. The rate comes from
  `MarketDataProvider.risk_free_series` under the new config key `cash_leg` (`auto`: FRED
  3-month bills, DTB3, with a one-day publication lag on real-world providers and the
  constant `risk_free_annual` on synthetic and CSV data; `fred`, `static`, `off`).
  `ComparisonReport.rf` records what was credited.
- **The desk is told its true position** (finding 22). `run_agent_backtest` replays the
  engine before each decision and hands the desk the position it actually holds: 0 after a
  stop, take-profit or ruin, otherwise the previous decision's units drifted with the market.
  Under v0.7 the desk was told it still held the pre-stop position, the PM "kept" a phantom
  and the backtester bought it back. A keep is only what the PM's no-trade band marks: the
  new `FinalDecision.kept` field (default `False`, in `to_dict()`) is set exactly when the
  band holds the current position, which it does only when that position passes every firm
  limit, and only such a decision is executed as no trade (the engine leaves a target equal
  to the held weight unclamped and untraded). Every other decision, including one equal to
  the cap while the held weight has drifted past it (a losing short, a capped FX long with
  negative carry), is a target the engine clamps and trades, so a drifted position past the
  cap is trimmed back to it at the next decision bar rather than carried; fix round 2 had
  made any decision at the cap a keep, fix round 3 restricts it to the band's own mark.
  `BacktestResult.exits` marks the bars where a protective level filled.
- **A ruin floor** (finding 18). When a bar takes equity to zero or below the return is -1,
  every later bar is flat, `BacktestResult.ruined_at` records the bar and `Metrics.ruined` is
  set; statistics stop there. v0.7 let negative equity compound with inverted sign. Ruin is
  declared per factor: the entry cost `(1 - k_in)`, the move `(1 + g)` and the exit cost
  `(1 - k_out)` are each checked, so two factors at or below zero on one bar can no longer
  multiply into a surviving account; the non-ruin arithmetic is unchanged.
- **A gap through the take-profit fills at the open** (finding 21), as a gap through the stop
  already did; the stop-first rule applies only inside the bar's range.
- **Impact follows the equity, not the initial capital** (finding 23): the impact coefficient
  is scaled by `sqrt(equity_t / initial_capital)`, so a strategy that has lost most of its
  equity is no longer charged as if it still traded the whole account.
- **Sleeves pay impact at the sleeve's capital** (finding 1): `run_portfolio_backtest`
  computes the allocation first and runs each sleeve with `capital_share`, which scales the
  impact coefficient by `sqrt(share)` -- exactly the impact of an account of that size.
- **Almgren-Chriss is finite for any urgency** (findings 19, 32, 33): the inventory path uses
  an `expm1` form instead of `sinh`, so `--ac-kappa` above ~710 charges impact instead of
  silently switching it off; a non-finite `algo_cost_ratio` is a `ValueError`. `costs.ac_kappa`
  0 is TWAP everywhere it is read -- the backtester's `impact_coefficients`, the desk's
  `execution.plan` tool and `plan_execution` (a `costs.get("ac_kappa") or 3.0` had turned 0
  into the default urgency) -- and an infinite, NaN or negative kappa is rejected with
  `ValueError` by `almgren_chriss` and `plan_execution` on both backends; `--ac-kappa` must be
  finite and `>= 0` or the command exits 2 instead of printing an all-NaN report.
- **Both backends agree on flat windows** (finding 20): the crossover baselines hold no
  position when the two averages differ only by rounding noise.
- **Zero variance is zero, not noise** (fix rounds 2 and 3). An excess-return series that is
  constant to rounding (sample standard deviation at most `quant.ZERO_VARIANCE_TOL`, 1e-12,
  times `max(1, |mean|)`) reports Sharpe, Sortino, t-statistic and annualised volatility of 0
  on both backends -- a flat book under a constant rate, a flat book earning exactly a
  varying cash leg, a curve compounding at exactly rf -- where the two backends printed
  +-1e16 or an O(1) random value. The same tolerance applies to the downside deviation on its
  own, so a series whose only losses are rounding noise (flat bars under a cash leg) has
  Sortino 0 while its Sharpe stands, and a constant *negative* excess return's Sortino is 0
  as well (was -sqrt(ppy)). The stats helpers (`sharpe_stats`, `sharpe_ci_bootstrap`,
  `paired_sharpe_block_bootstrap`, hence `PortfolioReport.sharpe_difference` and `research
  stats`) use the same rule.
- **Small engine contracts** (fix round 2): the numpy backend carries equity as float64 for an
  integer `initial_capital` (it truncated per bar; now bit-identical to the C++ backend); an
  empty `risk_free_annual` or `traded` array means absent on both backends instead of raising
  on numpy; `compute_metrics` called without `traded` warns once (`RuntimeWarning`) that trades
  are inferred from position changes, which drift every bar under constant units -- no engine
  path triggers it.
- **One NaN rule across indicators** (finding 76): windowed functions are NaN while the gap is
  inside their window; `ema`, `rsi` and `atr` reset at the gap and re-seed, instead of
  poisoning the rest of the series (or, for RSI, treating a missing close as a zero change).
- **Inputs are validated before the engine runs** (findings 57, 77, 78):
  `pycore.validate_backtest_inputs`, called by the facade for both backends, rejects
  non-finite or non-positive prices and bar ranges, infinite carry, levels, impact or cash
  rate, and length mismatches, as `ValueError`;
  `compute_metrics` requires `positions` to match `equity` in length; every window argument
  is checked at the facade (an integer in `[1, 2**31 - 1]`, `bool` rejected). The hypothesis
  property that draws every optional input now asserts finite results and backend agreement.

### Data
- **EDGAR quarters are reconstructed per concept and per reporting basis** (findings 7, 8,
  34; fix rounds 1-3). A concept is one XBRL tag, or tags proven equivalent for the filer (a
  rename: every span both print agrees within `TAG_EQUIVALENCE_TOLERANCE`, 1%); no span of one
  concept is differenced against another's, each trailing-year window is taken whole from
  the concept that covers it, and the concept already reported is kept across filings while
  it covers the window (rank decides only when it does not), so a rename or a gross/net pair
  no longer flips the series or drops growth for a year. A re-print within
  `BASIS_CHANGE_TOLERANCE` (5%) of the value held is a revision and the latest print wins. A
  material change must be corroborated: a filing that recasts at least
  `BASIS_CHANGE_MIN_SPANS` (2) spans of a concept, or the year-earlier comparative of a span
  it prints for the first time, and whose quarters reconcile with its own annual span
  (`ANNUAL_CHECK_TOLERANCE`, 2% of the larger of the annual figure and the quarters' total
  magnitude; `PER_SHARE_CHECK_TOLERANCE`, 0.15, for per-share series) opens a new basis
  generation. A lone material re-print is ignored, logged once and remembered; a later
  filing repeating it within 5% confirms it as a correction, taken in place within the
  current basis and never as a basis change (logged: `<tag> <start>..<end> re-printed as <v>
  on <filed>, repeating a print ignored earlier: a correction confirmed by repetition; taken
  in place of <held>`). A recast whose quarters do not add up to its own annual figure is
  mis-tagged and ignored (logged once), that year's Q4 being the annual span less the
  quarters held. Every difference and every year-over-year growth is taken within one
  concept and one generation. A direct Q4 print of an additive flow disagreeing with the
  annual span by more than 2% is replaced by the annual figure less the three quarters
  (logged once per ticker, tag and year); a per-share print is never overridden. Revenue
  quarters that reconstruct to zero or below are rejected. Balance-sheet instants must be
  dated within 400 days of the report period; a flow series is dead only when no filing
  within `MAX_FLOW_LAG_DAYS` (120) of the newest filing printed it, and a live series whose
  latest four-quarter window ends before the report period is kept and flagged
  (`revenue_period_end`, `net_income_period_end`, `eps_period_end`, `ocf_period_end`, each
  present only when that window lags). `net_margin` is reported only when the revenue and
  net-income windows end together; `fcf_yield` only when the OCF and capex windows end
  together or the filer never reports capex, so a stale capex series removes the FCF figure
  rather than the capex. Market-cap and EPS sanity checks and a share-class ratio table
  (`BRK.B` and `BRK-B` alike) drop ratios built on another class's prints, warning once per
  ticker and kind. User-visible: some filers lose a year of growth across a basis change,
  lagging windows are flagged instead of served as current or dropped as dead, filers whose
  capex tag lags have no FCF yield, and BRK-B reports no P/E or FCF yield at any date. Every
  EDGAR-on real-data number is re-measured under Re-measured results.
- **One FX rate resolver, no static fallback** (findings 15, 35). `base.fx_rates` serves both
  the macro analyst and the credited carry: the static table only on synthetic data or with
  `fx_macro_source="static"`; otherwise FRED as known on the date, and a stale, discontinued
  or unlisted leg gives no macro (the analyst abstains, the strategic FX weight is 0) and NaN
  carry. The answer for a date no longer depends on when it is asked. Every non-empty macro
  dict carries `macro_source`, `provider.macro_sources` tallies per run and
  `EvaluationResult.meta["macro_sources"]` records the tally for the run (cleared at the start
  of every `evaluate`). The FRED disk cache expires (`fred_cache_max_age_days`, 1; vintage
  snapshots never), downloads are validated before they are written, and fetches have a 30 s
  timeout; when the re-download of an expired file fails the stale series is served with a
  warning naming it and its last observation, so an offline historical re-run keeps its FX
  macro view instead of losing it. The config key
  `static_macro_max_age_days`, which gated the fallback, is removed. Norway's policy rate is
  in `RATE_SERIES`; Sweden has no series.
- **No partial Yahoo bar** (finding 36): history never includes or caches a bar dated today,
  where today is the New York calendar date whatever the host's timezone: a bar dated D is
  served once it is D+1 in New York, so a host east of UTC+4 no longer sees the bar still
  trading and a host west of New York no longer waits for its own midnight. An empty download
  raises the documented `ValueError` instead of a `TypeError`. A live decision "at the
  close" uses yesterday's complete bar.
- **CSV prices on one basis** (findings 37, 57; fix rounds 1-3): with `Close` and `Adj Close`
  present every price column is put on the adjusted basis and `Volume` is divided by the
  split component of the factor only (a day-over-day jump above `SPLIT_JUMP`, 5%), never by
  the dividend drift, so dollar volume, ADV and the impact ratio stay as traded across a
  split and a dividend payer's volume is served as traded (fix round 2 had divided by the
  whole factor); a row with a blank `Adj Close` keeps its bar with the nearest dated row's
  factor instead of being dropped; with only `Adj Close` the raw open/high/low are dropped
  with a warning rather than served on another basis. `clean_ohlcv` drops a non-finite close
  like a missing one and repairs `+inf` open/high/low from the close instead of widening the
  high to infinity.
- **Synthetic data** (findings 68, 88, 69): JPY crosses outside the classic pairs start near
  their real level, so their half-spread is a fraction of a basis point rather than tens;
  synthetic fundamentals draw from their own stream, so P/E is no longer a function of the
  instrument's volatility; `score_fx_headline` understands currency names, nicknames and
  central banks ("dollar", "yen", "Fed", "BoJ") and reads each clause from the subject it
  names first: the pair is recognised before its legs, only a clause about the quote
  currency is flipped, a two-leg clause takes the first-named subject, and a clause naming
  none inherits the headline's. "USD/JPY falls as yen rallies" scores -0.76 (was 0.00) and
  "Yen gains against dollar" -0.46 (was +0.46); the synthetic FX template "Hawkish {q}
  policymakers boost {q}, pressuring {s}" scores -0.905 instead of -0.462, so synthetic FX
  runs whose headline draw includes it get a different news signal. Synthetic price paths
  and the classic FX pairs are unchanged; synthetic equity results that use the
  fundamentals analyst, and synthetic FX runs that draw that template, are not.

### Statistics
- **Cluster bootstrap replaces the stratified one** (findings 4, 54). With `groups` given,
  `stats.paired_bootstrap` draws whole groups with replacement and then instruments within
  each drawn group, engaging only with at least `MIN_CLUSTER_GROUPS = 5` distinct labels
  (`min_groups`); below that it falls back to the plain instrument bootstrap and says so.
  `PairedBootstrap` gains `scheme` (`instruments` | `clusters`) and `n_groups`;
  `EvaluationResult.paired` / `paired_table` rename the kwarg `stratify` to `cluster` (no
  shim) and the table gains `scheme` and `groups` columns. In practice the core (2 groups)
  and extended (3 groups) universes report `scheme=instruments` and `--universe all` (5
  groups) reports `scheme=clusters`, with materially wider intervals. A sensitivity test now
  fails when the groups are ignored (a mutant that v0.7's tests did not detect).
- **Benjamini-Hochberg on the unrounded `p`** (finding 80); `m` counts only rows whose test
  ran, and a period with fewer than three paired instruments prints `p` as NaN instead of
  1.000 and no longer shrinks the other rows' thresholds.
- **`t(IC)` accounts for overlapping forward returns** (finding 5).
  `alpha.information_coefficient(signal, fwd, horizon, method)` scales by the effective
  sample `n / horizon` by default (the rule `xalpha` already used), with a Newey-West
  variant for comparison. At the analysts' horizon of 10 every published `t(IC)` is
  sqrt(10), about 3.16 times, smaller; IC, `n` and the decay ICs are unchanged. The alpha
  analyst's significance gate therefore admits far fewer alphas: on 200 seeded random walks
  it speaks on about a fifth of pure-noise histories instead of nearly all of them
  (`tests/test_v08_alpha.py::test_alpha_analyst_gate_is_a_five_percent_test_on_pure_noise`).
- **Tercile spread by rank, hit rate beside its base rate** (finding 29):
  `alpha.tercile_spread` assigns terciles by rank with boundary ties shared fractionally, so
  a signal stuck at one value on most bars no longer merges its top and bottom groups; every
  alpha table gains an `up%` column (share of positive forward returns on the same pairs)
  next to `hit%`.
- **Portfolio-level intervals** (finding 65): `stats.paired_sharpe_block_bootstrap` resamples
  two daily return series with the same circular blocks and reports the interval and `p` of
  the difference in excess-return Sharpe; `PortfolioReport.sharpe_difference` exposes it and
  `run_portfolio_backtest(rebalance_offset=...)` lets the rebalance phase be swept as the
  cadence noise floor. `sharpe_difference` pairs each bar's return with the rate credited
  over that bar (`rf[:-1]`), as `compute_metrics` does, so its point estimates equal the
  table's Sharpe under a per-bar rate (fix round 2; the mismatch was ~2e-6 with DTB3).
- **A trials registry** (finding 87): `evaluation.TRIALS` names the 26 variants judged on the
  design period, from the v0.2 control on (24 reproducible under the current engine, 2
  historical from the record; `reproducible_trials()`), so the deflated-Sharpe trial count is
  read from the record instead of frozen at 16.

### Risk and portfolio
- **`max_weight` is honoured** (finding 2): every weighting scheme's allocation is projected
  onto the capped simplex (equal and inverse-vol included, and again after group budgets),
  and the vol-target scale-up stops at the per-sleeve and gross caps.
  `PortfolioWeights.allocation` is now the pre-vol-target split (sums to the gross cap, each
  sleeve at most the cap) and `weights = allocation * target * scale`; callers that read
  `allocation` as the final weight must read `weights`. The uncapped backtest path
  (`max_weight=1.0`) is bit-identical.
- **Book VaR fails closed** (findings 3, 25): a zero-weight symbol no longer deletes the
  book's rows; when the book VaR cannot be evaluated (a held symbol with fewer than 20 aligned
  returns, or one whose fetch failed) the proposal is flattened with a note rather than the
  check silently passing; `TradingGraph.scan` fetches history for held symbols outside the
  watchlist. A hedge is sized to the largest size that brings an already-breaching book
  within the limit, and flattened only when no size does. `TradingGraph.scan` parses every
  `positions` key like a symbol (`EUR/USD`, `eurusd`, `EURUSD=X` name one key), so a held
  position is seen however its key is spelled, and raises `ValueError` on an unparseable key
  or on two keys naming one symbol with different weights.
- **Short positions use the right tail** (finding 24): `risk_facts` adds `var_95_1d_short`
  and `cvar_95_1d_short`, `agents.risk.position_var` and the new `position_cvar` select the
  tail by the sign of the weight, the PM guardrail, the conservative analyst's cap and the
  Critic's firm-limits check all read it, and the rules-mode risk analyst's text quotes the
  CVaR of the proposal's own side. The Critic falls back to `var_95_1d` for a short whose
  facts lack the short-side key instead of silently skipping the check.
- **Weighted Ledoit-Wolf** (finding 26): the shrinkage intensity is the Ledoit-Wolf (2004)
  constant-correlation estimator for the weighted (EWMA) covariance it is applied to, with
  the Kish effective sample size; every `construct()` with a non-equal weighting differs
  slightly from v0.7. The unweighted path is numerically unchanged.
- **A frozen sleeve gets nothing; only a window without variance raises** (finding 27).
  `construct()` marks an active sleeve with zero sample variance (a forward-filled or frozen
  series) inactive before any scheme runs, with a warning naming it, so every scheme
  allocates it 0 (min-variance and mean-variance handed it the whole book under v0.7); on the
  group-budget path a group whose only sleeves are flat drops out of the cross-group step.
  `risk_parity_weights` and `construct()` raise `ValueError` only when no active sleeve has
  variance, or a scheme returns a non-finite allocation, and `run_portfolio_backtest` then
  keeps the previous allocation as it was designed to, instead of propagating NaN weights.

### Execution
- **One impact law** (finding 6): the intraday simulator charges each slice
  `impact_coeff * daily_vol * sqrt(q_i / V_i)` against the bar's own volume, so VWAP
  reproduces the backtester's single-shot law at any slice count and TWAP / AC reproduce
  `algo_cost_ratio`; the v0.7 simulator charged about an eighth of that and ranked TWAP
  cheaper than VWAP.
- **FX quantities in the base currency, an account currency** (finding 16): new config key
  `account_currency` (USD); `plan_execution` sizes USD-base pairs as the notional itself,
  quote-USD pairs as notional / price, and crosses through `algo.base_to_account_rate`
  (point in time), refusing a cross without a rate. Plans, payloads and tickets carry
  `quantity_unit`, `notional_currency` and the reference price. A USDJPY order that was
  sized in yen-per-dollar units is now 500,000 USD when 500,000 USD is meant.
- **Whole shares and whole lots, once** (finding 91): `plan_execution` rounds at plan time
  (shares; `execution.fx_lot_size`, 1000 base units, for FX) and recomputes the notional; the
  schedule, payload, ticket and CLI all carry that quantity. A change that rounds down to
  zero lots is nothing to trade, not an error (fix round 2): `plan_execution` returns `None`
  as it does for an unchanged target, `execution.plan` answers `{"trade": false, "reason":
  "weight change ... is below one share/lot; nothing to trade"}`, and `execute` prints the
  change it sized -- the truncated change under the long-only policy, with the truncation
  note -- and that it is below one share or lot (`ValueError` is reserved for invalid inputs).
- **Fill risk is visible** (finding 30): `simulate_execution(requested=...)` reports
  completion as executed / requested, the shortfall is the Perold implementation shortfall
  on the requested quantity with the unfilled remainder marked at the close
  (`opportunity_cost_bps`, `unfilled`), and `execute` prints "executed X of Y (Z%)". A POV
  order five times the day's volume no longer reports 100% complete. `execute` prints the
  unfilled clause only when at least one share or one lot went unfilled: a closed-form
  schedule can leave 1e-14 of a share, which used to print as "opportunity cost of 0
  unfilled".
- **Next-session fills** (finding 31): `execution.plan` and `execute` size at the as-of close
  and simulate on the first session after it (arrival = that session's open,
  `execution_date` reported); when no later session exists the plan is returned unsimulated
  with a note, instead of filling on the decision day's own bar.
- **Almgren-Chriss urgency is dimensionless** (finding 32): `ExecutionPlan.schedule(bars,
  participation, kappa)` uses `costs.ac_kappa` (3.0; 0 = TWAP) directly, so the schedule is
  identical at any price level and seed; `execute --ac-kappa` is exposed.
- **`submit_order` takes a ticket, not a float** (finding 71): its signature is now
  `(symbol, side, quantity, quantity_unit, notional, notional_currency, price, plan_id,
  note="")`; `plan_id` is verified against `algo.plan_reference` (a checksum over the ticket
  fields, so edited numbers fail), the unit and currency must match, quantities must be whole
  shares or lots, and the notional must be within `DeskTools.order_cap`
  (`execution.max_order_notional`, default `initial_capital * risk.max_position`), which
  policy enforces before an approver ever sees the ticket. `servers.ticket_from_plan` builds
  the arguments from a plan payload; tickets record unit, notional, price, plan id, intent
  and the position before and after.
- **Plans start from the run's book, and tickets move it** (findings 71, 72, 73; fix rounds 1
  and 3). Each task run has its own position book: the harness seeds it from
  `Task.current_weight` and from an optional `positions` map (`AgentHarness.submit(task,
  positions=...)`, `POST /tasks` body `positions: {symbol: weight}`, 422 on a bad map), the
  tools run over it, the trading state is prepared from it, and the planner drops a
  model-written `current_weight` whenever the book holds the symbol (`validate_plan(...,
  book=...)`), so the position is one fact for the planner, the agents and the tools.
  `DeskTools.plan` defaults `current_weight` to the book and refuses a contradicting explicit
  value; its payload carries `ticketable` and `order_cap`, and a plan over the cap is
  returned with the cap and a note instead of a ticket the desk would refuse.
  `execution.submit_order` accepts only a plan this desk produced with exactly these fields
  (`plan_known`); the plan reference alone is a checksum anyone can compute, so a forged
  ticket is refused before it is written, and the new key `execution.allow_external_plans`
  (`False`) admits tickets planned elsewhere. A ticket moves the book to `position_after`, so
  the second leg of a split order plans from the reduced book and a second reduce cannot
  re-sell the same shares; `portfolio.position` lists pending tickets and its weight counts
  them. `execution.max_order_notional` of 0 is a cap of 0 (ticketing frozen), not "unset".
  A negative equity target under the default long-only policy is truncated to flat with the
  reason stated; every plan and ticket carries an `intent` (open / add / reduce / close long,
  sell short, buy to cover, reverse), and `submit_order` refuses a ticket that would take a
  long-only book short. `execute` honours `--allow-short`.
- **`execute` defaults** (finding 90): `--capital` defaults to the configured
  `initial_capital` (100,000), the convention the desk tools, `task` and the API already
  used, instead of a hard-coded 1,000,000; the header prints the capital and account
  currency; `task` and `serve` accept `--capital`.
- **The carry line says what was credited** (finding 89): the backtest and baselines header
  prints the mean carry over the accruing bars (every bar but the last, which has no
  following bar to accrue into) with unknown bars as 0 -- what the backtester actually
  credits -- plus the count of accruing bars with no point-in-time rate, and says "accruing
  bars"; a rate known only on the final bar prints as 0 credited, matching the engine.

### Agents and LLM
- **The dollar budget fails closed, and is a hard bound by default** (findings 13, 38; fix
  round 3). A served model id without a list price exhausts the cap instead of costing $0,
  and `budget_llm` / `get_llm` refuse at construction to run an unpriced deep or quick model
  under a dollar cap. `BudgetedLLM` reserves each call under the lock before dispatch and
  counts calls in flight against the cap; what is reserved is set by the new key
  `llm_budget_mode`: `"hard"` (the default) reserves the input estimate plus a full
  `max_tokens` reply -- the same maximum a timed-out attempt is billed at -- so spend can
  never exceed the cap, N workers cannot overshoot it, and a cap that cannot afford one such
  call refuses that tier before any spend; `"estimate"` reserves the input estimate plus
  `llm_reserve_output_tokens` (2000) and is a soft cap, overshooting by at most the calls in
  flight times `(max_tokens - reserve)` at list price. The v0.5.0 entry's "overshoot is at
  most one call" is superseded either way. `BudgetedLLM.exhausted_for(deep)` says whether the
  next call on a tier would be refused and `exhausted` is `exhausted_for(True)`. Retries are
  `AnthropicLLM`'s own (the SDK client is built with `max_retries=0`): `llm_max_retries` (2)
  attempts after the first, a timed-out attempt billed at its maximum each time, a
  `retry-after` / `retry-after-ms` header honoured up to 60 s on a rate limit or overload
  and `llm_retry_backoff_s` (0.5, validated finite and `>= 0`) otherwise. The Anthropic call
  path is exercised end to end against a fake SDK module.
- **Request shape per model family** (finding 81): thinking and effort parameters are sent
  only to families that accept them; older ids that failed on every call under v0.7 (and
  silently turned the run rule-based) now get a plain request. `deep_effort` / `quick_effort`
  outside `low`, `medium`, `high`, `xhigh`, `max` raise `ValueError` when `AnthropicLLM` is
  built instead of silently sending `high`.
- **Anonymised prompts are an allow-list** (finding 9): price-like facts are rebased,
  scale-free ones pass, everything else (revenue, EPS, market cap, the sector string, the
  peer list) is dropped, so `pe_ratio * eps_ttm` can no longer reproduce the real close.
- **Memory is an append-only log under a lock** (finding 10): one write and fsync per record
  and per resolution, no whole-file rewrite, so threads in one `serve` process and separate
  processes sharing `results/memory.jsonl` cannot lose or overwrite each other's records;
  old files load. Callers that parsed the file as one record per line must expect
  `{"resolve": ...}` lines too.
- **Memory outcomes are valued on one series, in bars** (findings 17, 75).
  `DecisionMemory.resolve(symbol, as_of, history, provider, price_basis)` takes the current
  history and values the entry from its own bar to `horizon` bars later on that series, only for entries
  recorded by the same provider and price basis; a split or dividend rebase, a provider
  switch or a multi-year gap no longer becomes a "was wrong" verdict that cuts live size.
  `horizon_days` means trading days; an entry the series cannot value, or whose exit bar
  never arrives, expires after twice the horizon. An entry is valued only when the decision
  day sat within the desk's `max_data_staleness_days` of its entry bar:
  `DecisionMemory(path, max_staleness_days=7)` and `resolve(..., max_staleness_days=None)`
  take the setting, and `TradingGraph` wires its own into both, so a desk allowed to decide
  on a ten-day gap settles those entries too. Lessons and the track record are
  provider-scoped; entries written before v0.8 carry no provider, are never valued, and are
  expired by any named provider's visit past twice their horizon, so a migrated log drains.
- **The track-record size cut is a rule switch** (finding 74): `rules.track_record_cut`
  (default on, so no published number moves) can be switched off for measurement; the
  design-period measurement is under Re-measured results.
- **Invalid numbers are rejected, not coerced** (finding 39): `Agent.ask_json(numeric=...)`
  rejects a reply whose numeric field is null, a string, a boolean or non-finite (the rules
  apply, `source="rules"`); `extract_json` rejects bare NaN / Infinity. A null
  `target_weight` no longer liquidates a held position.
- **No fabricated sector P/E** (finding 41): the fundamentals rules score P/E against a
  sector benchmark only when the data carries `sector_pe`; on real data (Yahoo, EDGAR) it
  never does, so every real-data equity fundamentals signal loses that term and the key point
  says no benchmark is available. Synthetic data supplies one and is unchanged.
- **The fundamentals analyst scores only current windows** (fix round 3). `FundamentalsAnalyst`
  abstains when the report is older than `STALE_REPORT_DAYS` (120) at the decision date, and
  skips a term whose window lags `report_period_end` by more than `STALE_WINDOW_DAYS` (100) as
  the provider flags it (`revenue_period_end` for growth, `eps_period_end` for P/E and the
  negative-earnings penalty, `net_income_period_end` for margin, `ocf_period_end` for FCF
  yield) with a key point naming the window and its lag; it abstains when nothing was scored,
  a metadata-only fact dict abstains, and the summary names every lagging window. A window
  one quarter behind, and every provider without lag flags (synthetic), score as before.
- **The untrusted fence covers digests, lessons, debate turns and rationales** (finding 42;
  fix round 3): reports from analysts with untrusted inputs are marked and their summaries
  fenced in every downstream prompt, memory lessons enter the researcher, trader and PM
  prompts only inside `<untrusted_data>`, and so do debate turns, verdicts and trade and
  decision rationales written from such text; `FIRM_CONTEXT` names them. Findings written
  from third-party text carry `Finding.untrusted`, emitted in the `/tasks` record and the
  report's findings, and the critic's and reporter's prompts fence those claims and the PM
  rationale (`critic.findings_block`, `critic.decision_untrusted`) under a `FENCE_NOTE`
  prefix; a clean run's prompts are unchanged.
- **Shared prompt code is hashed** (finding 40): `prompt_registry` gains a `shared` entry over
  every prompt-building helper outside the agent classes -- including the fence helpers
  (`state.fenced`, `TradingState.untrusted_inputs`, the debate / verdict / proposal /
  risk-views blocks), `risk._pct`, `anonymize.is_scale_free_key` and
  `DecisionMemory.track_record` -- and the values of `shared_prompt_constants()` (the fence
  tag `state._TAG`, the anonymiser's price-key and scale-free-key sets, suffixes, prefixes
  and date pattern), folded into the bundle hash, which therefore differs from every hash
  recorded before v0.8 although no prompt text changed; the `prompts.py` docstring
  enumerates exactly what is covered and what is not. The bundle hash of `make_config()` is
  `a2fb8be5c3066730` at this release. The policy documents under
  `agentic/knowledge/docs/` are retrieval content, not prompt code: `prompts.py` never reads
  them, so editing them does not move the hash.
- **`.env` is read only from the real command line** (finding 84): `cli.main(argv=...)`
  called in-process (the tests) no longer loads the developer's API key and EDGAR contact
  into the shared process; `AGENTIC_TRADER_NO_DOTENV` disables it outright.

### Services
- **One driver per run** (findings 11, 45, 12): a per-run driving lock makes `resume` and
  `cancel` non-reentrant, so two approvals on one task, or an approval racing a cancel, cannot
  drive the same run twice or execute a state-changing tool twice; `POST /approvals/{id}`
  schedules a continuation only when the run is parked and undriven and reports `resumed`;
  an `IllegalTransition` inside a drive ends the run FAILED with the error instead of
  vanishing into a Future. Only terminal records are cached; anything in flight is re-read
  from the store, so a sibling process serves COMPLETED once the owner finishes. A decision
  that lands as the driver parks is no longer lost (`resume` releases the driving lock inside
  the same critical section as the final awaiting-approval check), and a cancel requested
  while a run is parked or not yet started cancels it (AWAITING_APPROVAL -> CANCELLED)
  instead of being missed or resuming the work. When a run finishes or is cancelled its
  pending approvals are withdrawn (`QueuedApprovalGateway.withdraw`), so `POST
  /approvals/{id}` answers 409 for a finished or cancelled run without consuming the
  approval, and 404 once the run has been evicted (`forget`).
- **Argument guards run before the approval decision** (findings 43, 59, 46): the universe,
  date, weight, lookback, quantity and notional guards now apply to state-changing tools, so a
  bad order is denied by `argument_guard` rather than parked for a person, and argument
  binding runs before the approval decision too, so a state-changing call with a missing or
  unknown argument (a bare-float `submit_order`) is `DENY (argument_guard): bad arguments`
  and never parked; `current_weight` is guarded as a fact about the book -- finite, never
  capped, `bool` rejected -- while `weight`, `target_weight` and `proposed_weight` stay
  capped; `symbols` lists are checked element-wise and capped
  (`agentic.max_symbols_per_call`, 60), and the planner clips a model's list to the
  configured universe (canonical spelling, duplicates removed, a parallel `targets` list kept
  aligned) with a note instead of failing the run, repairs a string `symbols` to a
  one-element list and drops a step whose `symbols` has any other shape; a plan's total data
  budget is bounded (`agentic.max_plan_lookback_bars`, 200,000 symbol-days) and duplicate
  tool steps are dropped before the step cap is applied.
- **A tool deadline isolates, it does not terminate** (finding 44): each attempt runs on its
  own thread with a hard deadline; a timed-out worker is abandoned and counted
  (`tool_calls_abandoned_total`); state-changing tools get exactly one attempt and a timeout
  or transient failure is reported as "outcome unknown, not retried". A call to a remote MCP
  server has the same deadline by default: `registry_from_stdio(server_args=None,
  overrides=None, call_timeout_s=None, config=None)` takes `agentic.tool_timeout_s` (30 s
  shipped) when `call_timeout_s` is `None`, `math.inf` waits without limit, and a
  non-positive value is refused before a server is launched; when the deadline passes the
  SDK only sends its `notifications/cancelled` courtesy notice, which is as far as the
  cancellation reaches -- a synchronous remote tool still finishes and may land its ticket,
  so the outcome is unknown and is reconciled through `portfolio.position`'s pending tickets.
- **Remote MCP tools fail closed, whatever the server claims** (finding 47; fix round 1):
  `classify_remote_tool` never reads a remote `read_only_hint` or `meta` (risk, required,
  evidence type): every discovered tool is state-changing, HIGH risk, needs `PROPOSE_TRADES`
  and yields DATA evidence, the remote's claims are kept for display only, and the operator
  `overrides` map is the only relaxation. `registry_from_stdio(overrides=None)` applies
  `mcp_server.desk_overrides()` -- the annotations of this package's own catalogue, keyed by
  local name, because the client only ever launches this package's own server -- and `{}`
  relaxes nothing. The client now keeps one live server session per registry
  (`StdioSession`; `registry.session.close()`) instead of a fresh server process per call, so
  the remote desk keeps its plans, book and tickets across calls.
- **The MCP server is governed** (finding 58; fix round 1): every call routes through a
  `ToolExecutor` with the configured policy, approval gateway, evidence store and tracer for
  the operator's role; refusals surface as MCP errors with the policy reason.
  `python -m agentic_trader.agentic.mcp_server` and the `agentic-trader mcp` subcommand
  both take `--role` (default `trader`) and `--approval auto|deny` (default: the configured
  `agentic.approval`); `queued` is refused with an explanation (exit 2), since nothing on a
  stdio server can decide a parked request, and `build_mcp_server(registry, name, executor,
  config, role, gateway, order_cap)` raises `ValueError` for a queued gateway. The default
  executor caps every ticket at the desk's per-order cap (`servers.default_order_cap`).
  Operators exposing either should pass `--approval deny` or set `agentic.approval`.
- **Bounded memory and threads** (findings 48, 49): a malformed model critique is recorded as
  a failed warning check named `llm_critique_wellformed` and the run completes; finished runs beyond
  `agentic.max_retained_runs` (256) are evicted, terminal runs drop their executor, and the
  policy decision log is a bounded deque.
- **`/metrics` is one exposition** (finding 51): one process-level `Metrics` that every run
  writes to, one TYPE line per family, counters summed across runs, label values escaped.
  Scrapers that read the last run's page now read the process total. Histograms keep count,
  sum, min, max and cumulative counts over the 11 fixed buckets, never the observations
  (`Metrics.histogram()` returns them), so memory is bounded over a long-lived process, and
  counters render exactly (integers as integers) instead of through `%g`; the exposition
  lines are the same.
- **The API follows the configured approval mode** (finding 52): `create_app` builds the
  gateway from `agentic.approval` (`make_config` default `auto`; the `serve` CLI default stays
  `queued`); `/health` reports the mode and instance id; `GET /approvals` answers 409 unless
  the gateway is queued. `POST /tasks` accepts an optional `positions: {symbol: weight}` map
  for the run's book (422 on a bad map).
- **Lease-only sweeps** (finding 53; fix round 1): task records carry an owner and a
  heartbeat; a live run heartbeats every `lease_s / 3` (`agentic.lease_s`, 90 s, at least 1;
  validated by the harness and by `validate_app_config` before workers fork) and
  `TaskStore.heartbeat(owner, task_ids)` refreshes only the runs this instance drives.
  `mark_interrupted(note, owner=None, lease_s=None)` fails only records whose heartbeat is
  older than `lease_s` or that have no owner or heartbeat (legacy rows); the owner never
  widens the sweep and `owner` without `lease_s` raises `ValueError`; each update is a
  compare-and-swap on the state and version selected, so a record its owner finished
  meanwhile stays finished. A second instance on the same task DB no longer fails the first
  one's live runs, and a restart under the same configured `instance_id` no longer fails its
  predecessor's records at once: they are failed by any live instance once `lease_s` has
  passed. `AgentHarness.close()` stops the heartbeat thread.

### CLI, tests and packaging
- **`evaluate` takes the cost flags** (finding 60): `--impact`, `--capital`,
  `--execution-algo` and `--ac-kappa` are attached to `evaluate` as well as `backtest`,
  `baselines` and `portfolio`, so the documented impact-sweep command parses and is honoured.
- **`--rules v02` survives the other flags** (finding 50): per-flag overrides merge into the
  config section instead of replacing it, so `--rules v02 --band 0.2` still runs the v0.2
  neutral weights.
- **The default as-of date is New York's yesterday** (fix round 2): without `--date`, the
  desk commands and `calibrate` decide as of the last complete exchange day on the New York
  calendar (`cli.common.default_as_of`), whatever the host's clock, instead of the host's
  local yesterday; a host east of New York shortly after its local midnight now gets one day
  earlier than before. An explicit `--date` is unchanged.
- **One version, recorded everywhere** (finding 56): `pyproject.toml` is the single source
  (`0.8.0`; `agentic_trader.__version__` and the FastAPI app read it); the new
  `agentic_trader.provenance` module records version, git commit and dirty flag, quant
  backend, interpreter, platform and dependency versions into every `evaluate` and
  `calibrate` result (`meta.provenance`), into a `<stem>.provenance.json` sidecar next to
  every `--out` CSV, and into the CLI header (`quant=<backend> | v<version> <commit>`).
  `git_commit` and `git_dirty` are computed at every `provenance()` call, no longer cached
  per process, so a long run stamps the tree as it is when each result is written.
- **The lock is the full freeze** (finding 55): `requirements-lock.txt` pins every
  transitive dependency, states that it is valid for Python 3.12 only and why, and a CI
  `lock` job installs from it, asserts every pin and runs the suite.
- **The wheel is tagged for what it ships** (finding 82): `setup.py` includes the compiled
  core only when it matches the packaging interpreter and tags the wheel platform-specific
  then, pure otherwise. A machine without the core prints one `RuntimeWarning` at import
  naming the numpy backend; set `AGENTIC_TRADER_BACKEND=python` to choose it explicitly and
  silence the warning.
- **Tests** (findings 57, 70, 83, 54): a hypothesis property over every optional backtester
  input; direction tests for each analyst's rules (a rule that reads the data backwards now
  fails a test rather than only a golden number); the v0.7 assertions that could not fail
  were repaired; a mutant that ignores bootstrap groups is detected. `tests/test_v08_*.py`
  (agentic, agents, alpha, cli, data, engine, execution, portfolio, protocol, stats, and the
  fix rounds' `fixes` and `fixes_cli`) cover every item above. An autouse fixture in
  `tests/conftest.py` snapshots `os.environ` before each test and restores it after, so a
  test that sets a backend or key can no longer leak it into the rest of the session.
  `pytest --collect-only -q` collects 832 tests on the C++ backend and 832 with
  `AGENTIC_TRADER_BACKEND=python` (skips differ at run time, not at collection): the C++
  suite runs 832 passed, the numpy suite 796 passed and 36 skipped (the C++-only tests), and
  line coverage on the numpy backend is 95% (`pytest --cov=agentic_trader`; weakest
  `data/yahoo.py` at 75%, the network branches, and `quant/__init__.py` at 77%, the C++
  dispatch that backend skips). The C++ core has 25 `void test_` functions in
  `cpp/tests/test_core.cpp` under one registered ctest test.
- **Measurement is a script**: `scripts/measure_v08.py` (with `--only`) writes every
  re-measured table to `results/v08/` and `scripts/render_v08_tables.py` renders the markdown
  from it; the documents' Reproducing sections name them. The driver shares one Yahoo
  provider across runs and, for a run that overrides a provider-level key (`edgar`,
  `cash_leg`, the FRED/FX settings), hands it `provider.reconfigured(cfg)`: the same
  downloaded bars under the run's own config. `MarketDataProvider.reconfigured(config)` is
  new for this; the first v0.8 measurement had run "EDGAR off" and "cash leg off" with both
  still on (the shared provider kept its settings, and `meta["edgar"]` recorded it; their
  tables showed zero difference on every instrument, which is what exposed it), and those
  files were re-measured before any number was published. The published files therefore
  come from three commits of one engine (`results/v08/manifest.json` and each file's
  `provenance` say which, all `git_dirty: false`): `eval_main.json` at `c4385e2` (fix round
  3); the impact sweeps, `eval_alpha`, `eval_xalpha`, `eval_no_trackrecord_cut`, both
  portfolios, the execution-algorithm portfolios, `var_coverage`, `phase_sweep` and 23 of the
  24 re-measured trials at `eec0d27` (which changed only the `FIRM_CONTEXT` prompt string,
  read by no offline rules-based number); `eval_noedgar`, `eval_cash_leg_off`, the two
  cash-leg-off portfolios, `trial_edgar_filings_off`, `eval_rules_v03` and `eval_rules_v02` at
  `ac727ce` (the driver fix and a renderer change; no engine code). The regression tests are
  `tests/test_v08_fixes.py::test_36_a_reconfigured_provider_shares_the_downloads_under_its_own_settings`
  and
  `tests/test_v08_protocol.py::test_measurement_driver_reconfigures_the_shared_provider_for_provider_level_overrides`.
- New config keys, all additive with defaults that keep prior behaviour except where a bullet
  above says otherwise: `account_currency`, `cash_leg`, `execution.fx_lot_size`,
  `execution.max_order_notional`, `execution.allow_external_plans`, `fred_cache_max_age_days`,
  `llm_max_retries`, `llm_retry_backoff_s`, `llm_budget_mode`, `llm_reserve_output_tokens`,
  `rules.track_record_cut`, `agentic.max_symbols_per_call`, `agentic.max_plan_lookback_bars`,
  `agentic.max_retained_runs`, `agentic.instance_id`, `agentic.lease_s`. Behaviour changes
  behind existing keys: `costs.ac_kappa` 0 is TWAP (was read as the default 3.0),
  `execution.max_order_notional` 0 freezes ticketing (was "unset"), and a dollar cap under
  `max_llm_cost_usd` admits fewer concurrent calls under the default `llm_budget_mode`
  (`estimate` restores the earlier admission at the price of a soft cap).

## v0.7.0 — 2026-09-27

A pass through the whole codebase against its own highest-quality bar: risk aggregated
across the book instead of only per-instrument, two textbook tests of whether the risk
model's own coverage claim is true, multiple-comparison correction on the cross-instrument
bootstrap, a stratified variant of it for correlated clusters, solver convergence reported
rather than assumed, a CLI split into a package, and a locked dependency set to tell
dependency drift apart from a real result change.

### Risk
- **Book-level VaR** (`portfolio.book_var_95`, `portfolio.book_var_scale`, `state.Book`).
  Per-instrument VaR caps do not see correlation across sleeves; `max_book_var_95` (off by
  default) aggregates the whole book's historical VaR and scales a proposed weight down
  (never up) to respect it, by grid search over the position size rather than a closed-form
  or bisected solve, since a new position could be a partial hedge rather than added risk.
  `TradingGraph.scan()` builds the `Book` from the watchlist's own return history when the
  cap is configured; `propagate()` alone never builds one.
- **VaR coverage backtesting** (`stats.rolling_var_forecast`, `stats.var_backtest`,
  `agentic-trader stats --var-backtest`). Kupiec (1995) unconditional-coverage and
  Christoffersen (1998) independence likelihood-ratio tests of a walk-forward historical-VaR
  forecast against realized returns, closed-form against the standard normal CDF (no scipy
  dependency). Run against the 15-sleeve core portfolio's holdout returns: neither test
  rejects at either a 120-day or 250-day window — the desk's own risk model is
  well-calibrated on this data (see
  [the evaluation's VaR coverage section](docs/evaluation/evaluation.md#var-coverage-is-the-desks-risk-model-calibrated)
  and [LEARN.md #34](LEARN.md#34-is-the-risk-model-telling-the-truth-var-coverage-backtesting)).
  *Retracted in v0.8.0: the test covered a rolling quantile of the portfolio's own returns,
  not the per-instrument forecast the desk sizes on — see [v0.8.0 Retracted](#v080--2026-09-28).*

### Execution
- **Execution-algorithm-aware impact cost** (`algo.algo_cost_ratio`,
  `costs.execution_algo` / `--execution-algo {twap,vwap,ac}`, `costs.ac_kappa` /
  `--ac-kappa`). The daily backtester's square-root impact formula
  (`backtest.impact_coefficients`) implicitly assumed a trade is worked as VWAP -- matching
  participation to the volume curve, which minimises impact cost for a fixed order size, by
  the same convexity argument that already justifies VWAP as the execution simulator's
  default. TWAP (ignores the curve) or Almgren-Chriss (front-loads for urgency, `ac_kappa`)
  now scale the day's impact by that schedule's own cost relative to VWAP on the same
  volume curve, so a trade's simulated cost depends on how it would be worked, not only on
  its size. Off by default (unset == VWAP-equivalent == the existing formula exactly), so
  every previously published impact number is unchanged; measured on the core universe's
  $1B holdout portfolio, TWAP pays 2.51% of equity to impact over the period against VWAP's
  2.37%, and an aggressively front-loaded Almgren-Chriss (kappa=5) pays 3.14% (see
  [the evaluation's execution-algorithm section](docs/evaluation/evaluation.md#execution-algorithm-aware-impact-v07)).
  *Retracted in v0.8.0: these magnitudes charged each sleeve sqrt(15) times the impact of its
  own capital; the ordering stands, the numbers are re-measured — see [v0.8.0 Retracted](#v080--2026-09-28).*

### Evaluation
- **Benjamini-Hochberg FDR correction** (`stats.benjamini_hochberg`). The cross-instrument
  bootstrap's `p` was reported per baseline with no correction for testing several baselines
  at once; `EvaluationResult.paired_table(fdr_q=0.05)` now flags `significant` at the
  FDR-corrected threshold, not the raw `p < 0.05`.
- **Stratified bootstrap** (`stats.paired_bootstrap(groups=...)`). Resamples within each
  asset-class/universe group rather than pooling, so correlated clusters (e.g. the FX
  majors) do not masquerade as independent draws; `EvaluationResult.paired(stratify=True)`
  is the default when the rows carry more than one group.
  *Retracted in v0.8.0: this scheme narrows the interval rather than widening it and was
  replaced by a cluster bootstrap — see [v0.8.0 Retracted](#v080--2026-09-28).*
- **Deflated-Sharpe caveat** made explicit in `selection_report`'s own output
  (`DEFLATED_SHARPE_CAVEAT`), not only in the surrounding prose.
- **Significance-gated diagnostic column** (`alpha.significance_gated_series`,
  `xalpha.significance_gated_scores`) added to the alpha and cross-sectional alpha reports:
  the same per-bar t-stat gate the analysts apply, exposed as its own row so a reader can see
  what passes the gate without re-deriving it from the `ic` column by hand.
- **Solver convergence reported, not assumed** (`portfolio.Convergence`,
  `PortfolioWeights.converged`). `min_variance_weights` / `mean_variance_weights` can now
  report whether their iterative projection actually converged within the iteration budget;
  `construct()` logs a warning and carries the flag through when it did not.
- **Per-job timing** (`EvaluationResult.slowest`). `evaluate()` now times every backtest job
  and `agentic-trader evaluate` prints the slowest, so a hung or unusually slow (period,
  symbol) is visible without instrumenting a re-run.

### Engineering
- **`agentic_trader/cli.py` split into a package** (`agentic_trader/cli/`: `common.py`,
  `decisions.py`, `research.py`, `evaluate.py`, `services.py`, `parser.py`, `__init__.py`),
  one module per concern instead of one 700-line file. `main`, `build_parser`,
  `load_dotenv` and `_config` remain importable from `agentic_trader.cli` exactly as before;
  the `agentic-trader` console script is unchanged.
- **`requirements-lock.txt`**: the exact dependency versions each published number was
  measured with, so a re-run that differs can rule out dependency drift before suspecting
  data drift or a real code change (see Reproducing in
  [the evaluation](docs/evaluation/evaluation.md#reproducing)).
- **Coverage reporting in CI** (`pytest-cov`, `--cov-report=xml`/`term-missing`, uploaded as
  a CI artifact) — report-only, not a merge gate. 94% overall on the numpy backend; weakest
  are `data/yahoo.py` (50%, mostly network-dependent branches) and `llm.py` (75%, the live
  Anthropic call path).
- 319 tests (up from 280), including a new `tests/test_v07.py` covering every item above.

## v0.6.0 — 2026-09-27

Point-in-time filings for the idle half of the analyst team, statistical power across the
universe, a calibration harness for the model's judgement, pinned prompts, a cross-sectional
analyst measured under the protocol, fuzzing of the agentic layer, a bounded task pool with
multi-process serving, the documentation checked in CI, and one configuration knob for the
alpha window. The measured results of every data and rule change are in
[docs/evaluation](docs/evaluation/evaluation.md).

### Data
- **SEC EDGAR point-in-time fundamentals and filing news** (`data/edgar.py`). Free and
  keyless; the SEC requires a contact e-mail in the User-Agent (`EDGAR_USER_AGENT` in
  `.env`), without which EDGAR is skipped with one warning. Every XBRL fact carries the date
  it was *filed*, so a fact exists at `as_of` iff `filed <= as_of`, and a restated value never
  replaces the first print. Quarterly flows are rebuilt from the reported spans (direct
  quarters, year-to-date differencing, Q4 from the 10-K, 12/16-week fiscal calendars such as
  Costco's and PepsiCo's) and summed to trailing-twelve-month growth, margin, EPS and P/E,
  leverage and FCF yield; EPS surprise and insider direction stay `None` because EDGAR has no
  consensus data; funds and index ETFs (SIC 6221, no company facts) return nothing. The news
  feed is the filing stream itself: 8-K item codes mapped to headlines with a conservative
  tone, periodic and ownership filings, insider Form 4 counts; the thousands of routine
  prospectus supplements banks file are excluded. Predecessor filers are mapped
  (`edgar_ciks`; Exxon's 2026 holding-company reorganisation is shipped). Coverage was
  checked for every equity in the 60-name universe at two dates. The Yahoo provider uses it
  for every historical date; `--no-edgar` and `--edgar-cache` on the CLI. Social media has no
  free point-in-time archive and that analyst still abstains on real data.
- `alpha_lookback_days` (900) is the one knob for the alpha library's window — the alpha
  analysts and the `quant.alpha` / `quant.xalpha` tools — next to `lookback_days` (400) for
  everything else; every desk tool's `lookback_days` argument now defaults to the configured
  value instead of a hard-coded 400 or 900.

### Evaluation
- **Cross-instrument bootstrap.** `stats.paired_bootstrap` resamples instruments (pairs
  kept together) for the mean difference between two strategies; `EvaluationResult.paired`
  and `paired_table` give the 95% interval and two-sided `p` per period and baseline, and
  `agentic-trader evaluate` prints them. The published tables now say whether an edge across
  the universe is distinguishable from the luck of which instruments were drawn.
- **Repeated runs.** `evaluate(repeats=N)` / `--repeats N` runs the agent N times per
  (period, symbol), tags rows with `run`, and `run_dispersion` reports the across-run
  spread — the model's own variance, which any single-run difference has to clear.
- **Prompt registry** (`prompts.py`). A SHA-256 hash of every agent's system prompt and
  prompt-building code, bundled into one hash recorded in every evaluation and calibration
  result.
- **Calibration harness** (`calibration.py`, `agentic-trader calibrate`). One frozen state,
  `n` runs per anchor: dispersion of the target weight and action agreement, the anchoring
  slope of the target on the position the desk is told it holds, and drift against a stored
  report on the same state.
- **Cross-sectional alpha analyst** (`xalpha`): the v0.5 cross-sectional research consumed
  by an analyst at last — z-scored against a peer universe on every date (`xalpha_universe`,
  `--xalpha-universe core|extended|all|SYM,...`), significance-gated exactly like the
  time-series alpha analyst, cached per (universe, date). Measured under the protocol on top
  of EDGAR: core design -0.01 [-0.02, 0.00] of per-instrument
  Sharpe, core holdout 0.00, extended holdout -0.01 [-0.01, 0.00],
  reserve +0.01 / -0.03 — **off by default**: it spoke on 2.6% of sampled decisions (never on
  FX) because no alpha clears the cross-sectional significance gate on most dates.
- **The multi-year LLM harness**: model tiers, repeats and prompt hashes on the core universe
  over design and holdout, staged with a dollar cap per stage -- built and budgeted, **not
  yet run**; the evaluation says so explicitly rather than leaving it implied.

### Engineering
- **Agentic-layer fuzzing** (`tests/test_fuzz_agentic.py`): hypothesis properties over
  `coerce_arguments` on random schemas and JSON, `validate_plan` on random plans (the result
  always ends with governance, pins the task's symbol and date, schedules no state change),
  `PolicyEngine.evaluate` (always a decision; never ALLOW for a denied, unauthorised or
  state-changing request), `extract_json` and `untrusted_block`.
- **Bounded task pool and multi-process serving.** `create_app(workers, queue_limit)` runs
  tasks on a thread pool per process and answers `503` + `Retry-After` beyond
  `agentic.queue_limit` in-flight tasks; `/health` reports in-flight, running and queued.
  `serve --processes N` starts uvicorn worker processes from an app factory over a shared task
  store (required: `multiprocess_options` refuses without one); every process serves every
  record, cancel and approvals must reach the owning process (`409` elsewhere).
- **Docs checked in CI**: a `docs` job runs every offline cookbook recipe
  (`scripts/run_cookbook.py --offline`), renders every Mermaid diagram with mermaid-cli
  (`scripts/check_mermaid.py`) and resolves every internal link (`scripts/check_links.py`).
- **Landing page**: what changed in this release at the top; the older result tables below
  the fold.

### Fixed
- **Split basis in the EDGAR per-share ratios** (found by the release review): P/E and FCF
  yield divided a split-adjusted Yahoo close by as-first-printed EPS and share counts, so every
  date before a stock split was off by the split factor (AAPL 2019: P/E 6 instead of 25; NVDA
  2020: 2 instead of 85), and a trailing year that straddled a split mixed share units. The
  fundamentals now take the close *as traded* (from a second, unadjusted Yahoo download with
  the split table) and rebase every EPS and share-count print to the as-of basis before mixing
  quarters; the EDGAR-on tables in the evaluation were re-run on the fix.
- EDGAR: year-over-year revenue growth is only reported when the two trailing years are
  exactly a year apart; the earliest print of a span wins whatever tag it was filed under; a
  missing older submissions page loses its filings, not the ticker; a 404 is never written to
  the disk cache; cached endpoint files older than `edgar_cache_max_age_days` (7) are
  re-fetched so a reused cache cannot hide new filings from a live decision.
- Multi-process serving: a record another process wrote after this one started is loaded
  from the store on demand (`GET /tasks`, `/tasks/{id}`, `/health` and the cancel `409` all
  see it); the interrupted-run sweep runs once in the parent so a worker restart cannot fail
  its siblings' live runs; the configuration is validated before any worker forks; approvals
  resume on the task pool rather than the request thread; a queued task can be cancelled
  before it starts; stopping the server cancels the queue instead of draining it.
- `coerce_arguments` rejects non-finite numbers with `ValueError` (an infinite integer used to
  escape as `OverflowError`); the plan cap only ever drops tool calls, never the analysts or
  the debate / trader / risk stages; `untrusted_block` neutralises tags split across lines or
  left unterminated; the cross-sectional cache is per provider and locked; the calibration
  drift compares at an anchor both reports sampled; baseline rows survive a failed first
  repeat and `summary()` counts instruments once under repeats; `scripts/check_links.py`
  slugs headings the way GitHub does.
- `sma` on both backends now sums each window directly (as `rolling_std` already did)
  instead of carrying a running sum: the C++ boundary fuzzer found a window `[1e-38, 0]`
  after a `1.0` where the running sum left cancellation noise the flatness floor could not
  see, so `zscore` answered +1 on one backend and 0 on the other. The published tables were
  re-run on the fixed code; 19 of 1,680 rows moved, all but a few at the last displayed
  digit (the regression check in the evaluation lists the largest).
- `YahooProvider.history` extends every download to today: a walk-forward caller asks for
  a window ending at each successive as-of date, and each step used to be a new download
  once the requested end passed the cached range (found when the cross-sectional analyst
  fetched 45 peers per decision date). The point-in-time cut is still applied by
  `clip_history` at the requested end.
- The cross-sectional analyst computes only the IC it needs instead of the full
  `xalpha_report` (decay curves, quantile spreads and correlations cost six times the IC
  itself), and the desk tools' `lookback_days` arguments no longer carry hard-coded windows.

## v0.5.1 — 2026-09-26

The first measured LLM results, and the evaluation protocol's first use for a rule change.

### LLM evaluation (first ever)
- **The LLM desk measured for the first time**, lean by design: AAPL, NVDA, MSFT, META,
  GOOGL over Q1 2024, a decision every 10 bars, one debate round, `claude-opus-5` at medium
  effort with `claude-haiku-4-5` analysts, anonymised prompts, a 400-call cap, against the
  rule-based desk on identical bars. 271 calls, 0 refusals, 0 fallbacks, 0 errors, $4.12.
  **Same Sharpe as the rules (2.19 vs 2.19)**, less than half the exposure (23% vs 57%),
  return (6.9% vs 15.5%) and drawdown (2.2% vs 5.6%) on every name: the model sized down
  citing the abstaining analysts. A single quarter shows what it does, not whether it has an
  edge; the multi-year run with the full analyst team is a matter of spend. Every
  "not evaluated" caveat in the docs is replaced by this result and its limits.

### Rules
- **FX carry-neutral strategic weight** (`rules.fx_carry_neutral`, on by default). The FX
  analogue of the equity strategic weight: `clip(rate_diff% / 2, ±0.5)` from the macro
  analyst's point-in-time policy-rate differential, so the desk holds the higher-yielding
  currency unless convinced otherwise. Chosen on the core FX pairs' design period only
  (mean Sharpe −0.03 → +0.11, monotonic across five settings), then judged on data no choice
  had touched, where it improved every slice: extended crosses design −0.24 → −0.15, holdout
  +0.12 → +0.31, reserve −0.63 → +0.22; core reserve −0.58 → −0.10. It does not make the desk
  beat buy & hold on crosses. `RULES_V03` / `--rules v03` reproduces the previous rule set;
  the published tables are re-run under the new default and the v0.3-rule tables are kept as
  the record. Re-run headline numbers: core holdout mean Sharpe 0.44 → 0.46, extended holdout
  0.37 → 0.42, 15-sleeve portfolio holdout 1.14 → 1.16 (design 1.50 → 1.54); equities unchanged.

### Fixed
- `UsageTracker` cost lookup now matches a served model id with a date suffix
  (`claude-haiku-4-5-20251001`) to its family's list price instead of reporting `n/a`.

## v0.5.0 — 2026-09-26

A wider, fresher evaluation; execution-aware backtests; cross-sectional alphas; cross-asset
risk budgets; ALFRED vintages; a persistent task store; a dollar LLM budget; TLS and
deployment guards; property-based fuzzing of the C++ boundary; and the alpha-analyst fixes.

### Evaluation
- **Universe widened from 15 to 60 instruments.** The 15 *core* instruments (every rule
  choice through v0.4 was made on them) are joined by 45 *extended* ones that no choice ever
  consulted: 26 equities across sectors and styles (UNH, V, MA, PG, HD, COST, WMT, KO, PEP,
  CVX, LLY, ABBV, MRK, BAC, GS, CAT, BA, BRK-B, QQQ, IWM, XLF, XLE, XLV, XLU, EEM, EFA), 9
  rates / credit / commodity / real-estate ETFs (TLT, IEF, LQD, HYG, GLD, SLV, USO, DBC, VNQ)
  and 10 FX crosses whose both legs have FRED policy-rate series (NZDUSD, USDCHF, EURGBP,
  EURJPY, GBPJPY, AUDJPY, EURCHF, AUDNZD, CADJPY, EURAUD). `UNIVERSES`, `universe_group()`,
  a `universe` column in every result row, `summary(universe=)`, `head_to_head(universe=)`
  and `evaluate --universe core|extended|all`.
- **A fresh holdout for the next rule change.** The 2022–2026 holdout has been seen, so
  v0.5 defines what "unseen" means from here: the extended universe over *every* period,
  plus a `reserve` period (2026-07-01 → 2026-09-25) that no number in the documentation
  consults. The protocol is written down in the evaluation.
- **Execution-aware backtests.** `costs.impact_coeff` (default 0) charges square-root market
  impact in the backtester — the execution simulator's model, applied per trade to the agent
  *and* every baseline: a trade of `|dw|` costs `|dw|^1.5 · K_t` of equity with
  `K_t = coeff · daily_vol · sqrt(capital / (price · ADV))`. `Impact%` is reported per
  strategy; `--impact` and `--capital` on the backtest, portfolio and evaluation commands.
  The published tables include the core universe at three account sizes.
- **Alpha analyst.** Two bugs fixed (see below); measured a third time and still off by default.

### Research
- **Cross-sectional alphas** (`xalpha.py`): the same signals standardised across the names of
  a group every day (z-score or rank, equities and FX separately), evaluated with per-date
  Spearman IC, an IC information ratio, a t-statistic that accounts for overlapping horizons,
  the share of positive days, top-minus-bottom quantile spreads and breadth. `xalpha_report`,
  `xalpha_snapshot`, the `quant.xalpha` tool (16 tools now) and `agentic-trader xalpha`.
- **Cross-asset risk budgets** (`portfolio.construct(groups=, group_budgets=)`): the chosen
  scheme allocates within each asset class, then risk parity with the budgets allocates
  across classes from the full covariance; `group_risk` reports budget vs realised risk
  share. `run_portfolio_backtest(class_budgets=)` and `portfolio --class-budgets equity=0.6,fx=0.4`.
- **ALFRED vintages** (`fred_vintages`, `--fred-vintages`): revised series (CPI) are read from
  the ALFRED vintage current at each date, so inflation enters the backtest as first
  published. Monthly vintage sampling (one download per series per month, cached in memory
  and optionally on disk with `fred_cache_dir`). Off by default; policy rates are never
  revised and are unaffected.

### Agentic layer and services
- **Persistent task store** (`agentic/store.py`, `agentic.task_db`, `serve --task-db`): every
  run is written to SQLite at each state transition; a new process serves old records
  through the same API routes (`GET /tasks`, `/tasks/{id}`, `/report`, `/trace`,
  `/evidence`); records left mid-flight by a crash are marked FAILED "process restarted",
  never silently resumed.
- **Dollar LLM budget** (`max_llm_cost_usd`, `--max-llm-cost`): `BudgetedLLM` now caps
  estimated spend as well as calls (list prices, cache-aware); the overshoot is at most one call.
- **TLS and deployment guards** (`serve --ssl-cert/--ssl-key`, `serve_options`): binding a
  non-loopback interface with the shipped development API keys is refused unless
  `--allow-dev-keys`; plain HTTP off loopback logs a warning. `make_config` now *replaces*
  `agentic.api_keys` instead of merging into the dev keys (a real footgun: adding a real key
  used to leave every dev key live).
- **`.env` loading.** The CLI reads a project-local `.env` (`KEY=VALUE`, git-ignored) without
  overriding the environment; `scripts/set_api_key.ps1` stores the key as a Windows user
  variable with hidden input.

### Quant core
- `BacktestInputs.impact` / `BacktestResult.impact_paid` in C++, the numpy twin and the
  bindings; `run_backtest(impact=)`.
- **Property-based fuzzing of the Python ↔ C++ boundary** (`tests/test_fuzz.py`, hypothesis):
  every quant entry point on NaN / ±inf / empty / huge inputs must either return a
  well-formed result or raise `ValueError`, and the two backends must agree on sane inputs.
  It found and fixed five divergences: `quantile(x, NaN)`, `max_drawdown` with NaN (numpy
  did not skip it), `kdj` and `atr` windows containing NaN (`std::max` silently skips NaN,
  numpy propagates it — both now treat a missing bar as a missing range), `zscore` on a
  flat window (cancellation noise gave ±1; both now floor the spread), and a
  `compute_metrics` overflow on the numpy side. Non-finite prices are now rejected by both.

### Fixed
- `AlphaAnalyst` now weights only alphas whose IC clears significance (`|t(IC)| >= 2`,
  n >= 30) and abstains when none qualify, instead of weighting every alpha by `max(0, IC)`.
- Fixed a real inconsistency: under the agentic harness, `AlphaAnalyst` silently reused the
  `quant.alpha` tool's raw (equal-weighted, ungated) "combined" value instead of applying its
  own significance gate. Both invocation paths now share one function,
  `alpha.significant_alpha_signal`, so the analyst can no longer disagree with itself
  depending on how it is called.
- Fixed a window mismatch: the analyst reused the desk's general ~400-day lookback, too
  short for a 273-day signal like `tsmom_12_1` to ever gather enough points to be judged
  significant. It now fetches its own 900-day window, matching the `quant.alpha` tool.
- Net effect, re-measured on the design period: "+ alpha analyst" moved from mean Sharpe 0.60
  (v0.4.0) to 0.65 (essentially tied with the 0.65 default) with a higher median Sharpe (0.62
  vs 0.55) and a better FX median, at the cost of two fewer instruments beating buy & hold
  and ~8% more trades. Given this is the third combination-logic variant measured on the same
  data, a closer-to-parity result is treated as noise, not a green light: the alpha analyst
  **stays off by default**. See
  [docs/evaluation/evaluation.md](docs/evaluation/evaluation.md#the-v04-alpha-analyst-design-period-check).

### Tests and docs
- **Tests:** 199 → **240** pytest tests (v0.5 features 18, fuzz 21 property tests, impact 3)
  + 14 C++ test groups; hypothesis added to the `dev` and `all` extras.
- **Docs:** LEARN (30 concepts), COOKBOOK (64 recipes), DIAGRAMS (27), architecture,
  specification, threat model (36 threats), API, evaluation (60-instrument tables, impact
  sweep, the fresh-holdout protocol) and the landing page updated.

## v0.4.0 — 2026-09-26

The agentic layer, the quant research layer, and a rewrite of the documentation.

### Agentic layer (`agentic_trader.agentic`)
- **Domain model.** Frozen dataclasses for `Task`, `Plan`, `PlanStep`, `ToolDescriptor`,
  `ToolRequest`/`ToolResult`, `Evidence` (six types, SHA-256 digests), `Finding`,
  `PolicyDecision`, roles and capabilities, and the task state machine with its legal
  transitions.
- **Tools.** A `ToolRegistry` derives JSON schemas from Python signatures. The
  `ToolExecutor` runs every call through the policy engine, with a per-call timeout,
  bounded retry on transient errors, argument coercion, tracing and an evidence record for
  every call, successful or not.
- **Tool servers.** 15 tools on 5 servers: `market_data` (history, news, social,
  fundamentals, macro), `quant` (technical, risk, alpha, baselines), `knowledge` (search,
  list_documents), `portfolio` (position, construct) and `execution` (plan; `submit_order`,
  which is state-changing and always needs approval). `RecordingProvider` routes the
  analysts' data access through these tools.
- **Policy engine.** Ordered rules (deny list, required capabilities, read-only, argument
  guards, risk level) returning ALLOW / DENY / REQUIRE_APPROVAL with the rule that fired;
  five roles; auto, queued and deny approval gateways.
- **Planner.** A canonical plan per asset class and an optional model-proposed plan. The
  validator strips unknown tools, stages and arguments, pins the symbol and date, repairs
  stage order, refuses state-changing tools in plans, and appends the governance steps.
- **Harness.** `AgentHarness` runs a plan through an explicit state machine with parallel
  tool batches, AWAITING_APPROVAL pause and resume, cooperative cancellation, and the
  governance steps (critic, evidence validation, audited report) that cannot be skipped.
- **Critic.** Seven deterministic checks (evidence resolves, model-vs-rules divergence,
  contradictions, firm limits, protective levels, direction vs verdict, single-evidence
  cap) and an optional model critique that can only lower confidence.
- **Audited reports.** A number audit (every figure in the narrative must trace to the
  structured facts, tolerant of rounding and percentage forms) and an evidence-id audit;
  discrepancies become warnings.
- **Knowledge base.** 11 runbooks and policies (59 chunks) with a dependency-free hashed
  TF-IDF embedder; retrieved passages are DOCUMENT evidence and are shown to the trader and PM.
- **Observability.** Spans with parent ids, JSON-lines logging and Prometheus text metrics.
- **MCP server.** The catalogue as a real MCP stdio server (official SDK 2.x), plus a client
  that turns a remote server's tools into a local registry so policy and evidence apply unchanged.
- **HTTP API.** FastAPI gateway with API-key roles: tasks (202 accepted, background run),
  reports (JSON or markdown), traces, evidence, cancel, approvals, tools, health, metrics.
- **CLI.** `task`, `tools`, `serve`, `mcp`.

### Quant research layer
- **Alpha library** (`alpha.py`): nine signals (12-1 momentum, vol-adjusted 20-day
  momentum, 5-day reversal, 52-week high, Donchian, MACD, RSI, low-vol, FX carry) with IC,
  IC t-stat, decay, hit rate, tercile spread, autocorrelation and correlations; combination;
  an `AlphaAnalyst` agent (off by default, see the evaluation).
- **Execution algorithms** (`algo.py`): TWAP, VWAP, POV and Almgren-Chriss schedules; an
  intraday simulator (Brownian-bridge bars from a daily bar, half-spread and square-root
  impact, implementation shortfall and slippage vs VWAP); decision → parent order planning.
- **Portfolio construction** (`portfolio.py`): EWMA and Ledoit-Wolf covariance; equal,
  inverse-vol, risk parity, minimum variance and mean-variance weights with caps; risk
  contributions and diversification ratio; `run_portfolio_backtest(weighting=...)` with
  trailing (no look-ahead) covariance.
- **Statistics** (`stats.py`): block-bootstrap Sharpe CI, probabilistic and deflated Sharpe
  ratios, minimum track record, and a selection report for a chosen variant.
- **C++ core:** `rolling_max`, `rolling_min`, `spearman`, `almgren_chriss`; `sma` no longer
  returns all-NaN after a leading NaN (a bug the alpha library exposed).
- **CLI.** `alpha`, `execute`, `stats`, `portfolio --weighting`.

### Evaluation
- The evaluation period formerly labelled after an external publication is now `q1_2024`.
- Adding the alpha analyst was measured on the design period (mean Sharpe 0.65 → 0.60,
  median 0.55 → 0.60): noise, so it stays off by default.
- Deflated Sharpe ratio reported for the v0.3 rule choice (16 variants).

### Changed
- References to an external research paper and repository were removed from the code and
  documentation; the design is described on its own terms.
- Approval identity is the tool and its arguments within a task, so a request re-submitted
  after approval is recognised.
- `TradingGraph` is split into stages (`prepare`, `run_analyst`, `run_debate`, `run_trader`,
  `run_risk`, `record`) that the harness reuses; `propagate` is unchanged.
- LLM usage and cost accounting (`UsageTracker`), anonymised prompts (`llm_anonymize`) and
  parallel evaluation (`evaluate(workers=)`) from the pending LLM-evaluation work are included.

### Tests and docs
- **Tests:** 116 → **197** pytest tests (agentic 30, adversarial 15, services 7 incl. a real
  MCP stdio round trip and the FastAPI client, quant research 18, LLM evaluation 11).
- **Docs:** LEARN (26 concepts), COOKBOOK (56 recipes), DIAGRAMS (24), architecture,
  specification, threat model (32 threats), API and evaluation rewritten; landing page updated.

## v0.3.0 — 2026-09-25

Hardening, real-life workflows and an honest real-price evaluation.

### Evaluation
- **New protocol on real prices.** The universe is 15 instruments (10 equities, 5 FX pairs)
  and there are three periods:
  - a 2016–2021 **design** period, the only data used for choices;
  - a 2022–2026 **holdout**, run once with frozen rules;
  - a Q1 2024 reference window.

  The protocol is available as `evaluate()` and `agentic-trader evaluate`.
- **Volatility-targeted buy & hold baseline**, the fair control for a risk-managed strategy.
  **Sharpe t-statistic** and **average exposure** are added to every result.
- **16-variant design-period ablation**, published in full.
- **Findings.** Out of sample the agents do not beat buy & hold on Sharpe per instrument, and
  take about half the drawdown. As a 15-sleeve portfolio they beat plain buy & hold (Sharpe
  1.14 vs 1.06) but not the vol-targeted control (1.24). See `docs/evaluation/evaluation.md`.

### Rule changes (chosen on design data only)
- **Strategic weight plus tilt.** With no view the trader holds `risk.neutral_weight`
  (equities 1.0, FX 0.0) instead of going flat. Design equity mean Sharpe went from 0.76 to
  0.99; on the holdout it went from 0.60 to 0.63, return from 30% to 47%, and trades halved.
- **No-trade band** (`risk.rebalance_band` 0.10) around the current position. It is applied
  only when that position still passes every limit. It cut trades by 44% at equal Sharpe.
- **Research switches, off by default** because they measured as noise: 12-1 month
  time-series momentum, trend-filtered reversals, and abstention from the consensus.
- `RULES_V02` / `--rules v02` reproduces the v0.2 rules exactly (tested against the
  published AAPL decision).

### Engine (C++ and numpy twin)
- `run_backtest_ex` adds per-bar carry, **intraday stop and take-profit fills** (at the
  level, or at the open on a gap; stop first when both trade; re-arm at the next
  rebalance), exit costs, and validation of lengths and prices.
- Randomised C++ vs numpy cross-checks of the extended backtester.

### Real-life workflows
- **Portfolio context.** `propagate(current_weight=)`; `analyze --position`.
- **Watchlists.** `TradingGraph.scan()` / `agentic-trader scan`, with positions and CSV/JSON
  export. A bad symbol becomes an error row.
- **Multi-asset portfolios.** `run_portfolio_backtest()` / `agentic-trader portfolio` (equal-capital
  sleeves with equity and FX calendars aligned).
- **Stops in backtests.** `backtest.use_stops` / `--stops on`.

### Data
- **Point-in-time FX macro from FRED** (`data/fred.py`). Values are publication-lagged and
  staleness-checked, and carry is accrued per bar. On real data, today's illustrative
  static rates are never used for old dates.
- `clean_ohlcv` normalises every provider's output: sort, dedupe, drop bad closes, fill and
  widen OHLC, strip time zones.
- **Yahoo performance.** Coverage-cached downloads, and news is no longer requested for
  dates Yahoo cannot serve. Real-data backtests are about 8× faster.

### Safety and robustness
- **Prompt-injection containment.** Headlines and posts reach the model only inside
  `<untrusted_data>` blocks that cannot be escaped.
- **LLM cost and failure handling.** `max_llm_calls` sets a hard budget (`BudgetedLLM`);
  requests time out; an analyst with no data abstains and makes no model call.
- **Model-supplied levels.** Stops and targets on the wrong side of the entry are replaced,
  and the levels are rebuilt when the PM flips direction.
- **Input guards.** Stale-data refusal (`max_data_staleness_days`); strict symbol parsing (a
  mistyped pair like `EUR/XYZ` no longer becomes an equity); non-finite position guard.
- **Memory.** Writes are atomic, and a corrupt log line is skipped.
- **CLI.** Friendly errors (exit status 2, no traceback).
- **`at_backtest`.** Skips invalid rows instead of crashing.
- `.env` files are git-ignored.

### Tests and docs
- **Tests.** 18 → **116** pytest tests; 7 → **13** C++ test groups (34 checks).
- **Docs.**
  - `LEARN.md` now has 18 concepts, `COOKBOOK.md` 38 recipes (all runnable ones executed),
    and `DIAGRAMS.md` 16 diagrams, each parsed with Mermaid 11.
  - Architecture, specification, threat model (20 threats), API reference, evaluation and
    the landing page were rewritten.

## v0.2.0 — 2026-09-25

### Added
- **Documentation site**, published with GitHub Pages from `docs/` at
  https://ashjha0.github.io/agentic-trader/. The landing page shows measured figures, an
  honesty note, the architectural boundary, component cards, a sample decision and a
  real-price backtest.
- `LEARN.md`: a guided tour through 13 concepts, each with implementation pointers, real
  numbers and questions.
- `COOKBOOK.md`: 25 recipes; all 22 Python recipes are executed when the docs are checked.
- `docs/architecture/overview.md`, `docs/DIAGRAMS.md` (10 Mermaid diagrams),
  `docs/SPECIFICATION.md` (requirements with status),
  `docs/threat-model/threat-model.md`, `docs/evaluation/evaluation.md`, `docs/api/api.md`,
  `docs/INDEX.md` and `docs/GITHUB_PAGES.md`.
- An evaluation on **real Q1 2024 prices** (Yahoo) for AAPL, NVDA, MSFT, META, GOOGL, EURUSD,
  USDJPY and GBPUSD with the rule-based agents, next to the synthetic results.
- GitHub Actions CI (#1): pytest on Python 3.10–3.14, and a C++ build with ctest and pytest
  on the C++ backend on Linux, Windows and macOS.

### Changed
- `examples/compare_baselines.py` now covers all eight evaluation instruments over the
  documented window (2024-01-02 → 2024-03-28).

## v0.1.0 — 2026-09-25

First release.

- **Agents.** A multi-agent trading firm for equities and FX:
  - analysts: technical, fundamentals or macro/rates, news, sentiment;
  - a bull/bear debate with a facilitator;
  - a trader;
  - an aggressive/neutral/conservative risk team;
  - a portfolio manager with hard limits.
- **LLMs.** Claude through the Anthropic SDK with quick and deep tiers, an offline
  rule-based mode, and a rule-based fallback on any LLM failure.
- **C++17 quant core.** Indicators, risk, rule-based baselines and a backtester, exposed via
  pybind11, with a numpy twin.
- **Data.** Synthetic, Yahoo/FRED and CSV providers with point-in-time guards; decision
  memory with reflection.
- **Tools.** Walk-forward backtesting against the baselines, the `agentic-trader` CLI,
  examples, and the pytest and ctest suites.
