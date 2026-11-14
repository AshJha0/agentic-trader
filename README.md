# AgenticTrader

[![CI](https://github.com/AshJha0/agentic-trader/actions/workflows/ci.yml/badge.svg)](https://github.com/AshJha0/agentic-trader/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-ashjha0.github.io%2Fagentic--trader-16697a)](https://ashjha0.github.io/agentic-trader/)

**AgenticTrader** is a research harness for trading agents under hard governance, with a
rules-based desk for equities and FX measured against simple controls, and a designed but
not yet run test of what a language model adds. The
short version of what it has found: nothing has beaten a simple control, and the project says
so with intervals.

**What it found.**

- **The rules desk does not beat a vol-targeted hold.** On real prices with costs and a cash
  leg, the 15-sleeve holdout portfolio has Sharpe 0.91 against 0.99 for the vol-target control
  (difference -0.08, 95 % interval [-0.46, +0.30]) and 0.86 for buy and hold
  ([v0.11 re-measurement](docs/evaluation/v011_review.md)).
- **The rules were not selected by skill.** The deflated Sharpe of desk minus vol-matched
  control on the design period is 0.009 at the registry's 81 trials
  ([selection statistic](docs/results/round2/selection_stat.md)).
- **A local language model has added nothing measurable so far.** With `qwen2.5:7b-instruct`
  in the analyst seats, the 20-bar IC was 0.046 below the rules desk (95 % interval
  [-0.185, +0.067]; two complete cells of a first pass that was then stopped, descriptive only). In that cell 404 of 1,200
  analyst outputs came from the model and the rest from rules, so the result is about the
  technical analyst and the FX macro analyst, not about text-reading analysts
  ([interim report](docs/results/v17/llm_study_interim_report.md)).

**What was controlled for.** Lookahead (point-in-time data, a future-leak canary),
memorisation (anonymised prompts, a recall audit with a placebo arm), multiple testing (a
trial registry counted in every selection statistic) and equity beta (a vol-target control
with no desk beside every claim).

**What is not known yet.**

- Whether the model adds information beyond the rules. That is one
  [pre-registered](docs/evaluation/v16_preregistration.md) test, signed on 2026-11-12 before
  any of its rows existed. It has **not been run**: the queue needed about 227 hours of model
  time on one laptop and the owner stopped the study the same day
  ([status](docs/evaluation/v16_prereg_status_2026-11-12.md)). There is no pre-registered
  finding about the model, only a signed design.
- A lag-1 version of most published Sharpes. The registered rules trials were re-run at lag 0,
  lag 1 and next open (2026-11-13): no trial beats the vol-target control at any timing (all
  p > 0.16), so the conclusions do not depend on the same-close fill
  ([exec-lag results](docs/results/v17_exec_lag/trials_lag_yahoo.md)). The other published
  Sharpes still fill at the close the signal saw.
- Corrected FX numbers everywhere. FX P&L was converted to the USD account on 2026-11-12. The
  v0.9 design, v0.9 holdout and v0.12 pages were rebuilt from clean re-runs on 3f80a69 and no
  headline conclusion changed (every desk-minus-control interval still contains zero); other
  pages that hold FX books have not been re-run ([changelog](CHANGELOG.md)).
- Anything the forward paper record could decide. It has run daily since 2026-09-29
  ([results/paper/](https://github.com/AshJha0/agentic-trader/tree/paper-ledger/results/paper)); its pre-registered look at about 3,600 sessions
  (2040) has 50 % power for a 0.2 Sharpe difference, and 80 % power would need about 29 years
  ([live-readiness statement](docs/evaluation/live_readiness.md)). It is an operations record.

**Try it** (offline, synthetic data, no key):

```bash
pip install -e .
agentic-trader task EURUSD --date 2024-03-01 --position 0.2
```

> Research and education only. This is not investment advice. Nothing here is production
> trading and the framework never connects to a broker. The synthetic data mode produces fake
> prices, news and fundamentals.

**Documentation site: https://ashjha0.github.io/agentic-trader/**

| Guide | For |
|---|---|
| [How the AI works](docs/ai/ai.md) · [How the quant works](docs/quant/quant.md) | Start here. The agents, the LLM, what is and is not machine learning, and the agentic layer; then the quant core, the backtester, risk, alphas, portfolios and the statistics |
| [Evaluation](docs/evaluation/evaluation.md) · [What the model adds](docs/evaluation/what_the_model_adds.md) | Real-price results on 60 instruments with a design / holdout / reserve split; every model variant scored against the rules desk |
| [AI learning path](docs/learn/ai_learning_path.md) · [LEARN.md](LEARN.md) | Ten modules on the kinds of AI used here, each with an offline exercise; then the concepts one by one, with how the repo implements each |
| [COOKBOOK.md](COOKBOOK.md) | Copy-pasteable recipes for the agentic layer, quant research and operations |
| [Architecture](docs/architecture/overview.md) · [Diagrams](docs/DIAGRAMS.md) | Components, data flow, design decisions |
| [Specification](docs/SPECIFICATION.md) · [Threat model](docs/threat-model/threat-model.md) · [API](docs/api/api.md) | Requirements with status; threats mapped to controls and tests; the Python, HTTP, MCP and C++ interfaces |

## What it is

It is an **agentic trading desk** for **equities and FX**. A team of specialised
agents (analysts, bull and bear researchers, a trader, a risk team, a portfolio manager)
produces sized, explained decisions. An **agentic layer** runs them the way an enterprise
system would: every data access is a catalogued, policy-gated tool call that leaves an
evidence record; a plan (canonical or model-proposed) is validated before it runs; a critic
checks the result; and the report is audited so every number and every evidence id traces
back. Underneath is a **C++17 quant core** (indicators, backtester with stops and carry,
risk, alphas, execution schedules) exposed to Python through pybind11, and a **quant research
layer** for alphas, execution algorithms, portfolio construction and backtest statistics.

## Results by release

*v0.12 research ([docs/evaluation/v012_trend_core.md](docs/evaluation/v012_trend_core.md)):
the three steps the review approved were run on design data only: a longer design period
(2008-07-01 to 2021-12-31), a long/short multi-horizon trend stream (`TSMOM(L/S)`, now a
baseline in every table, its signal `strat_tsmom` in the C++ core) and the vol-target book as
the core with the desk's tilt as a sized overlay. None of them beat the vol-target control,
every interval includes zero, and nothing was adopted. The forward paper record remains the test.*

*v0.11 ([docs/evaluation/v011_review.md](docs/evaluation/v011_review.md)): a second
adversarial review's 89 confirmed findings are implemented and every table re-measured; the 15-sleeve
holdout portfolio is at Sharpe 0.91 against 0.86 buy & hold and 0.99 vol-target (desk − vol-target −0.08
[−0.46, +0.30]), still no measurable edge over the control; the detailed numbers below are the v0.8.0 measurement and the v0.11 page has each of them re-measured.*

*v0.9 and v0.10 research ([docs/evaluation/v09_research.md](docs/evaluation/v09_research.md)):
attribution shows the desk's active tilts add nothing over the vol-targeted control (alpha
+0.41%/yr on design, −0.80%/yr on holdout, both inside noise); a multi-asset base, trend and
carry streams were tried on the design period and none beat its control, so nothing was
adopted; the [pre-registered](docs/evaluation/v09_preregistration.md) holdout report is
published as a report, and a daily paper-trading job from 2026-09-29 is the forward test. Its append-only ledger, revision
log and assumptions are published in [results/paper/ on the `paper-ledger` branch](https://github.com/AshJha0/agentic-trader/tree/paper-ledger/results/paper), updated after each run.*

On **real prices**, the rule-based desk is evaluated over 60 instruments: the 15 *core*
ones every rule choice was made on (10 equities, 5 FX pairs; rules chosen on 2016–2021 only,
judged once on a 2022–2026 holdout) and 45 *extended* ones (sector equities, rates / credit /
commodity ETFs, FX crosses) that no rule was tuned on. v0.8.0 corrected the engine (constant
units between decisions, a cash leg with Sharpe on excess returns, equity-scaled impact, the
desk told its true position after a stop) and **re-measured every number**: everything below
is copied from `results/v08/tables.md`, written by `scripts/measure_v08.py` and rendered by
`scripts/render_v08_tables.py`; no earlier figure is carried forward. Summary tables quote
the *median* Sharpe; paired tables the *mean* difference with its 95% bootstrap interval —
resampling instruments (`scheme=instruments`) on the core and extended slices and a two-stage
cluster bootstrap over the five asset-class-by-universe groups (core equities, core FX, extended equities, macro ETFs, FX crosses; `scheme=clusters`) on all 60 — its p, and whether
the Benjamini–Hochberg correction across the table flags it ("BH-significant").

*Updated 2026-11-14 (review C8): the paired Sharpe intervals below are now the time-block
bootstrap on every slice (the returns were not reaching the slices, and the daily series are
now excess over the cash rate, which removed a degenerate Carry row); drawdown and Calmar stay
on the cross-instrument interval because the metric is not Sharpe. Source:
`results/v08_c8_fixed/tables_render.md`, run 2026-11-14 on bee26ad. The portfolio bullet is
unchanged.*

**The headline:** per instrument the desk has **no Sharpe edge over the volatility-targeted
control**, and **about half of buy & hold's drawdown, most of which the control achieves too.**

- **Per instrument:** all 60, design period, desk − vol-target (buy & hold scaled every day to
  the same 15% volatility target the desk's risk analysts use, capped at the 1.0 position
  limit — the fair control) −0.07 [−0.20, +0.07] p 0.32; desk − B&H −0.03 [−0.25, +0.21]
  p 0.85. The only BH-significant design-period difference on all 60 is against Carry, +0.50
  [+0.18, +0.82]; desk − TSMOM(L/S) +0.40 [+0.06, +0.72] p 0.02 is not BH-significant. On the
  holdout nothing is BH-significant (TSMOM(L/S) +0.37 p 0.02, SMA(20/50) +0.22 p 0.04). Core
  holdout medians 0.35 (desk) vs 0.51 (buy & hold) vs 0.52 (vol-target). On Q1 2024 the desk
  is significantly worse than both controls on the 45 extended names (−0.30 [−0.48, −0.12]
  and −0.29 [−0.48, −0.13]).
- **Drawdown, against the fair control:** core holdout mean max drawdown 13.19% (desk) vs
  31.50% (buy & hold) vs 18.92% (vol-target): desk − B&H −18.31 points [−27.63, −9.99] and
  desk − vol-target −5.73 [−8.44, −2.73], both p 0.00 and BH-significant. On the 45 extended
  names 14.42% vs 26.18% vs 19.72%: desk − vol-target −5.29 [−7.09, −3.53] p 0.00
  BH-significant. On FX the vol-target control sits at the shared 1.0 position cap most of
  the time, so the FX drawdown comparison has essentially no control.
- **As a 15-sleeve equal-capital portfolio:** holdout Sharpe 0.80 with a 7.80% drawdown and
  59.10% exposure, against 0.86 / 20.43% for plain buy & hold and 0.99 / 9.17% for buy & hold
  at the same volatility; the v0.7 claim that it beat plain buy & hold (1.09 vs 1.06) is
  **retracted**. Paired block bootstrap over days (block 10, n 1167): desk − B&H −0.06
  [−0.41, +0.30] p 0.748; desk − vol-target −0.19 [−0.53, +0.16] p 0.297. Design period 1.40
  vs 1.28 vs 1.43 (desk − B&H +0.12 [−0.16, +0.40] p 0.434; desk − vol-target −0.03
  [−0.28, +0.23] p 0.898). Shifting the rebalance phase by 0–4 bars moves the desk's holdout
  Sharpe across 0.80 / 0.85 / 0.86 / 0.80 / 0.84 (spread 0.06): the cadence noise floor is as
  large as the portfolio differences quoted. *The cash leg:* since v0.8 idle capital earns the
  3-month bill (FRED DTB3, one-day publication lag) and Sharpe is on excess returns; with the
  cash leg off (the v0.7 convention) the holdout Sharpes are 1.04 / 1.05 / 1.24, so the order
  desk < buy & hold < vol-target is the same under either convention.
- **Point-in-time filings (SEC EDGAR, since v0.6), re-checked:** agent Sharpe with the
  filings minus without — design core +0.01 [−0.03, +0.04] p 0.72 (better on 4 of 15; the
  filings reach the 10 equities only), holdout core −0.01 [−0.07, +0.04] p 0.83, holdout
  extended +0.03 [+0.01, +0.06] p 0.00 (15 of 45), all 60 holdout +0.02 [−0.02, +0.05] p 0.39
  (clusters); the on/off tables print p without a BH flag. On the core names the filings add
  exposure and drawdown for about no Sharpe (design mean 0.66 on vs 0.65 off; cumulative
  return 118.18% vs 110.44%; drawdown 17.59% vs 15.30%; exposure 63.31% vs 60.48%). The data
  stays on; the untuned rules that read it remain the next protocol item.
- **Cross-sectional analyst (v0.6):** with minus without — design core −0.01 [−0.02, +0.00]
  p 0.36, holdout core 0.00 [−0.01, +0.02] p 0.60, holdout extended −0.00 [−0.01, +0.00]
  p 0.23, reserve extended −0.02 [−0.06, +0.01] p 0.20 — **off by default** stands.
- **Alpha analyst (corrected gate):** design core −0.00 [−0.05, +0.05] p 0.90, holdout −0.00
  [−0.04, +0.02] p 0.79: the design period shows nothing, so it stays off; how often the
  corrected gate speaks was not measured.
- **FX carry weight (v0.5.1):** the protocol's first adopted rule change, on minus off:
  design core +0.04 [−0.01, +0.10] p 0.11 (better on 4 of 15 — it touches FX only), holdout
  core +0.02 [−0.02, +0.07] p 0.37, holdout extended +0.04 [+0.00, +0.08] p 0.04, Q1 2024
  core +0.49 [+0.12, +0.94] p 0.01, reserve extended +0.14 [+0.03, +0.28] p 0.00, all 60
  holdout +0.03 [−0.00, +0.12] p 0.23 (clusters): positive on every slice, small, with
  intervals touching zero on most.
- **Execution costs:** with equity-scaled square-root impact on (textbook coefficient 1.0,
  core universe) the desk keeps its Sharpe at $100k and $10M (design 0.66 → 0.66 → 0.66;
  holdout 0.34 → 0.34 → 0.34) and loses 0.05 on the design period (0.66 → 0.61, 4.24% of
  equity paid in impact) and 0.03 on the holdout (0.34 → 0.31, 2.53%) at $1B; the
  vol-targeted control goes 0.64 → 0.57 (design) and 0.45 → 0.41 (holdout), SMA(20/50)
  0.57 → 0.38 and 0.18 → 0.04, MACD 0.40 → −0.18 and 0.14 → −0.30 (impact charges summing to 64.71% of equity over the period, added up daily, not a terminal loss, paid in
  impact on the design period).
- **VaR coverage:** the desk's own per-instrument forecast (250-day historical VaR) against
  next-day returns over the holdout: Kupiec rejects at 5% on 2 of the 15 core instruments
  (AAPL breach rate 0.0657, p 0.0207; AUDUSD 0.0634, p 0.0432), breach rates run
  0.0523–0.0657 (every one above 0.05), and the Christoffersen independence test rejects on
  6 of 15 — breaches cluster; book-level VaR was off in every published run and is untested.
- **Selection statistics:** the selection test is a deflated Sharpe on desk-minus-control
  returns (the vol-target control levered to the desk's volatility) at the registry's trial
  count. On the design period it is **0.009** at 81 registered trials (0.005 at 145, adding the
  estimate of unregistered early trials). The differential Sharpe is 0.040 a year, against 1.00
  expected from the best of 81 zero-skill trials. There is no evidence that the rules select
  better than a vol-targeted hold. Evidence class: measured, design period, stored v0.11 files;
  source [selection_stat.md](docs/results/round2/selection_stat.md), from
  `scripts/selection_stat.py`. The figure printed here before, 0.998 at 26 trials, compared two
  different statistics and had already been withdrawn in the evaluation document. The absolute
  deflated Sharpe (0.925 at 81 trials) is not a selection test either: the control, which takes
  no decisions, scores 0.921 on it. The frozen rules' design-period portfolio itself: annual
  Sharpe 1.375, bootstrap 95% CI [0.593, 2.17].
- **LLM desk:** measured once (v0.5.1: five stocks, Q1 2024, Claude Opus, anonymised prompts,
  $4): the same Sharpe as the rules with less than half the exposure — produced under the
  v0.7-and-earlier engine and **not re-derived under v0.8**. The multi-year harness — Opus,
  Sonnet and Haiku tiers on the core universe over design and holdout, repeated runs for the
  model's variance, a calibration — exists (staged, dollar-capped per stage) but **has not
  been run**; this remains the only measured LLM result.
- **Nothing remains unseen.** The reserve period (2026-07-01 → 2026-09-25) and the extended
  universe were consulted for the v0.5.1 carry rule and the v0.6 decisions, and v0.8
  re-measured every period; the next unseen data is the future. On its own the three-month
  reserve says little: core median Sharpe 0.81 (desk) vs 1.05 (both controls), extended
  −0.11 vs −0.08 (buy & hold) / −0.11 (vol-target); desk − B&H −0.06 [−0.21, +0.12] p 0.44
  (core) and +0.08 [−0.14, +0.33] p 0.54 (extended), neither BH-significant.

Details: [the v0.8 section of the evaluation](docs/evaluation/evaluation.md#v08-engine-and-protocol-corrections-and-every-number-re-measured);
the historical sections keep their earlier-engine numbers under a banner saying so.

## Architecture

```
 request ──► AgentHarness (state machine) ──► Planner ──► validated Plan ──► executor
                                                                              │ policy: ALLOW / DENY / REQUIRE_APPROVAL
                                                                              │ evidence: SHA-256 record per call
                 ┌────────────── tool servers (also an MCP stdio server) ─────┴───────────────────┐
                 │ market_data · quant · knowledge (RAG) · portfolio · execution (simulate, order) │
                 └────────────────────────────────┬────────────────────────────────────────────────┘
                 ┌──────────────── Analyst team (quick-thinking model) ─────────────────┐
                 │ Technical │ Fundamentals (equity) / Macro-rates (FX) │ News │ Sentiment │ [Alpha] [XAlpha] │
                 └───────────────────────────────┬────────────────────────────────────────┘
                     structured reports (signal, confidence, key points, evidence ids — or abstain)
                                                 ▼
                       Bull researcher ⇄ Bear researcher  ──►  Facilitator → verdict
                                                 ▼
          Trader → strategic weight + tilt, stop, target, horizon   ◄── current position, policy passages
                                                 ▼
                 Aggressive ⇄ Neutral ⇄ Conservative risk analysts (m rounds)
                                                 ▼
    Portfolio manager → firm limits (size, VaR, shorting, min trade) → no-trade band
                                                 ▼
        Critic (deterministic checks; a flag cuts the weight, never adds) → evidence validation
                                                 ▼
        Audited report (number audit · evidence-id audit) → decision memory → HTTP API / CLI
```

* **Tools, then rules, then LLM.** Each agent computes facts with the C++ core and forms a
  transparent rule-based judgement. If Claude is enabled, its structured JSON replaces the
  judgement; if the LLM fails, the rules stand. An analyst with no data abstains.
* **Evidence first.** Every tool call yields an `Evidence` record (arguments, correlation
  id, SHA-256 digest) before any agent interprets it. Findings cite evidence ids; a finding
  whose ids do not resolve is dropped; the narrative is audited afterwards.
* **Policy, not prose.** Roles map to capabilities; ordered rules decide every call and name
  the rule that fired; state-changing tools always need approval; a queued gateway parks
  them for a person.
* **The harness owns the loop.** An explicit state machine (CREATED → PLANNING →
  VALIDATING_PLAN → EXECUTING ⇄ AWAITING_APPROVAL → CRITIQUING → VALIDATING_EVIDENCE →
  FINALISING → COMPLETED) with cancellation, per-step timeouts, retry and tracing. The
  critic, evidence validation and finalisation are appended to any plan that omits them.
* **Contained, capped, bounded.** Third-party text reaches the model only inside
  `<untrusted_data>` blocks that cannot be escaped. `max_llm_calls` and `max_llm_cost_usd` cap calls and dollars. The firm
  limits run after any model output.
* **A benchmark, then tilts.** With no view the desk holds a strategic weight (equities
  fully invested; FX the higher-yielding side, sized by the point-in-time carry and capped
  at ±0.5), and conviction tilts around it.
* **Point-in-time data.** Prices are clipped twice. FX macro comes from FRED as known on
  each date. Stale feeds are refused. Memory outcomes become visible only after their horizon.

### Equity vs FX

| | Equity | FX |
|---|---|---|
| Value analyst | Fundamentals: P/E, growth, margins, leverage, FCF from SEC EDGAR facts as known on the decision date (point in time; each trailing year from one XBRL tag and one reporting basis); EPS surprise and insider direction only when a source has them | Macro: point-in-time policy-rate differential (carry), inflation (PPP), distance from the 200-day average |
| Alpha library | 8 signals (momentum, reversal, breakout, MACD, RSI, low-vol, 52-week high) | The same plus carry |
| News scoring | Headline tone; historically the SEC filing stream (8-K events, reports, ownership and insider filings) with a conservative per-item tone, plus recent Yahoo headlines | Tone oriented to base vs quote ("JPY weakens" is bullish for USD/JPY) |
| Strategic weight | 1.0 (the equity premium) | carry / 2, capped at ±0.5 (the carry premium; v0.5.1) |
| Shorting | Off by default | On |
| Execution | VWAP by default; POV above 10% of ADV; 78 five-minute slices | TWAP; 288 slices; spread in pips |
| Costs | Commission + slippage bps, borrow fee on shorts | Half-spread in pips converted to bps, plus per-bar carry |
| Periods per year | 252 | 260 |

## Layout

```
cpp/include/at/*.hpp       C++ API: indicators (incl. rolling extremes, Spearman), backtest, risk, strategies, Almgren-Chriss
cpp/src/*.cpp              implementation · cpp/bindings/module.cpp (pybind11) · cpp/apps/at_backtest.cpp · cpp/tests
agentic_trader/
  agentic/                 the agentic layer
    domain.py              Task, Plan, PlanStep, ToolDescriptor, Evidence, Finding, PolicyDecision, states
    tools.py               ToolRegistry (schemas from signatures), policy-gated ToolExecutor (evidence, retry, timeout)
    servers.py             market_data · quant · knowledge · portfolio · execution tools; RecordingProvider
    policy.py              rules -> ALLOW / DENY / REQUIRE_APPROVAL; roles; auto / queued / deny gateways
    planner.py             canonical plan, model-proposed plan, validator (strip, pin, repair, append governance)
    harness.py             AgentHarness state machine: batching, approvals, cancellation, governance steps
    critic.py              deterministic checks + model critique; lowers confidence, a flag cuts the weight
    reporter.py            structured report, narrative, number audit, evidence-id audit
    rag.py + knowledge/    hashed TF-IDF retrieval over 11 runbooks and policies
    tracing.py             spans, JSON-lines logs, Prometheus text metrics
    mcp_server.py          the catalogue as an MCP stdio server + client (remote tools into a registry)
    api.py                 FastAPI gateway: tasks, reports, traces, evidence, approvals, tools, metrics; TLS guards
    store.py               SQLite task store: records survive restarts; in-flight runs carry an owner and a heartbeat and are failed only once their lease expires
  alpha.py                 alpha library, IC / decay / hit rate / turnover, significance-gated combination
  xalpha.py                cross-sectional alphas: per-day z-scores / ranks within asset class, per-date IC, spreads
  algo.py                  TWAP / VWAP / POV / Almgren-Chriss schedules, intraday simulator, decision -> plan
  portfolio.py             EWMA + Ledoit-Wolf covariance, 5 weighting schemes, cross-asset risk budgets, attribution
  stats.py                 bootstrap Sharpe CI, probabilistic and deflated Sharpe, minimum track record, paired (cluster) bootstrap across
                           instruments, block-bootstrap Sharpe difference between two daily series, Kupiec / Christoffersen VaR coverage
  prompts.py               prompt registry: a content hash of every prompt the desk can send, recorded in every evaluation
  calibration.py           dispersion / anchoring / drift of the desk's judgement on one frozen state
  quant/                   facade: C++ if built, otherwise pycore.py (numpy mirror)
  data/                    synthetic | yahoo | csv providers, clean_ohlcv, fred.py (point-in-time macro, ALFRED vintages),
                           edgar.py (SEC EDGAR: point-in-time fundamentals, as known at as_of, and filing-stream news)
  agents/                  analysts (incl. alpha and cross-sectional xalpha), researchers + facilitator, trader, risk team + PM
  graph.py                 TradingGraph stages, propagate() and scan()
  backtest.py              walk-forward agent backtest vs 9 baselines (incl. vol-target, trend and carry streams) with optional market impact; portfolio backtest
  evaluation.py            design / design_long / holdout / Q1-2024 / reserve evaluation over the core and extended universes; repeats, paired bootstraps,
                           the registry of every variant judged on the design period (TRIALS)
  memory.py · llm.py (call and dollar budgets) · anonymize.py · provenance.py (version, commit, backend and dependency versions in every result)
  cli/                     common.py, decisions.py (analyze/task/scan), research.py (backtest/portfolio/xalpha/alpha/execute/stats),
                           evaluate.py, services.py (tools/serve/mcp/info), parser.py (argparse wiring), __init__.py (main)
scripts/                   measure_v08.py (re-measures every published table into results/v08/) · render_v08_tables.py (prints the tables from it)
                           measure_v09.py · combine_v09.py · overlay_v09.py · attribution_v09.py (return streams, books, overlay, attribution; v0.9 to v0.12)
                           render_v09_doc.py · render_v11_doc.py · render_v12_doc.py (write the evaluation pages from result files) · paper_trade_v09.py (the forward record)
                           run_cookbook.py · check_mermaid.py · check_links.py (the CI docs job) · build_cpp · set_api_key
tests/                     pytest tests on both backends; about 2,100 in the PR gate (the CI log has the count). Largest groups at v0.8 (v0.8 fixes 105 + 17 CLI, fuzz 73 C++ boundary + 7 agentic layer, v0.8 agents 68, v0.8 engine 57,
                           v0.8 data 57, v0.8 execution 41, v0.8 agentic 41, quant edges 38, v0.7 37, agents 35, v0.8 portfolio 30, agentic 30, v0.11 18 + 4, v0.9 8 + 3, ...)
examples/                  equity, FX, baseline comparison
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (source .venv/bin/activate on Linux/macOS)
pip install -e ".[all]"           # anthropic, yfinance, pybind11, pytest, mcp, fastapi, uvicorn
pip install -e ".[otel]"          # optional: OpenTelemetry export of traces
```

### Build the C++ core (optional, recommended)

You need CMake 3.18 or later and a C++17 compiler: Visual Studio Build Tools on Windows,
gcc or clang elsewhere.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_cpp.ps1
```
```bash
./scripts/build_cpp.sh
```

Both scripts use the project interpreter, `.venv\Scripts\python.exe` (or `.venv/bin/python`),
when it exists, because a bare `python` on PATH is often another interpreter without
pybind11. Without a `.venv` they fall back to `python` on PATH with a warning, and stop with
a message naming the interpreter if pybind11 is missing from it.

Without the build, everything runs on the numpy fallback, which uses identical formulas
(cross-checked in CI). When the compiled core is missing, importing `agentic_trader.quant`
emits one `RuntimeWarning` saying that every number will come from the numpy backend; set
`AGENTIC_TRADER_BACKEND=python` to choose the fallback explicitly, which also silences the
warning. The CLI header names the backend in use (`quant=cpp` or `quant=python`).

## Usage

Offline mode needs no API key or network, so every command below runs as-is:

```bash
# one decision through the agentic harness: plan, policy-gated tools, critic, audited report
agentic-trader task      EURUSD --date 2024-03-01 --position 0.2
agentic-trader task      AAPL --date 2024-03-01 --approval queued --json

# the desk without the harness, a watchlist, and the services
agentic-trader analyze   AAPL --date 2024-03-01 --position 0.4
agentic-trader scan      AAPL,NVDA,EURUSD --date 2024-03-01 --positions '{"AAPL": 0.5}' --out orders.csv
agentic-trader tools                                   # the 16-tool catalogue
agentic-trader serve --task-db results/tasks.sqlite    # HTTP API at http://127.0.0.1:8000/docs, records kept
agentic-trader mcp --approval deny                     # the same tools as an MCP stdio server, locked down: tools that need approval are refused (default: the config's mode; queued is refused on stdio); --role picks the role every call is evaluated for (default trader)

# research
agentic-trader backtest  NVDA --start 2024-01-02 --end 2024-03-28 --stops on --impact 1.0 --capital 1e8
agentic-trader portfolio AAPL,JPM,XOM,EURUSD,USDJPY --start 2023-01-02 --end 2023-12-29 --weighting risk_parity --class-budgets equity=0.6,fx=0.4
agentic-trader alpha     USDJPY --start 2021-01-04 --end 2024-03-28 --horizon 10
agentic-trader xalpha    AAPL,MSFT,NVDA,JPM,XOM --start 2021-01-04 --end 2024-03-28
agentic-trader execute   AAPL --date 2024-03-01 --target 0.6 --current 0.1 --capital 5000000   # --capital defaults to config initial_capital; whole shares (FX: whole lots of the base currency); sized at the as-of close, simulated on the next session
agentic-trader stats     returns.csv --trials 26
agentic-trader stats     returns.csv --trials 26 --pre-registry-trials 64 --trial-returns trials.csv   # DSR at the registered, registered + pre-registry, and effective trial counts
agentic-trader stats     returns.csv --var-backtest                        # Kupiec and Christoffersen coverage tests of a rolling VaR
agentic-trader evaluate  AAPL,EURUSD --periods q1_2024
```

With real prices (network) and Claude (API key):

```bash
agentic-trader evaluate --data yahoo --universe all --periods design,holdout,q1_2024,reserve   # the published protocol
agentic-trader evaluate --data yahoo --universe core --periods design,holdout --impact 1.0 --capital 1e9   # the impact sweep: --impact / --capital / --execution-algo / --ac-kappa on evaluate too
agentic-trader evaluate --data yahoo --fred-vintages --fred-cache results/fred_cache          # CPI as first published
agentic-trader evaluate --data yahoo --universe core --periods design,holdout --edgar-cache results/edgar_cache  # EDGAR fundamentals and filing news (EDGAR_USER_AGENT in .env)
set ANTHROPIC_API_KEY=...                                                  # or `ant auth login`
agentic-trader task MSFT --llm anthropic --data yahoo --max-llm-calls 50 --max-llm-cost 5 --llm-planner
agentic-trader evaluate AAPL,NVDA --data yahoo --periods holdout --every 10 --repeats 3 --llm anthropic --anonymize --max-llm-cost 50   # model variance
agentic-trader calibrate AAPL --date 2024-03-01 --n 5 --anchors none,-0.5,0,0.5 --llm anthropic --anonymize --max-llm-cost 10        # dispersion, anchoring, drift
agentic-trader serve --processes 4 --workers 4 --task-db results/tasks.sqlite                                                       # bounded pool per process
python scripts/measure_v09.py --period design_long --out results/v12                                                                # the v0.12 research runs (2008-07-01 to 2021-12-31), then combine_v09.py, overlay_v09.py, render_v12_doc.py
```

The CLI also reads a project-local `.env` (`ANTHROPIC_API_KEY=...` and
`EDGAR_USER_AGENT="Name email@domain"`, the contact the SEC requires; git-ignored, never
overriding the environment). On Windows, `scripts\set_api_key.ps1` stores the key as a user
environment variable with hidden input and reports only its length back.

From Python:

```python
from datetime import date
from agentic_trader import TradingGraph, make_config, run_portfolio_backtest
from agentic_trader.agentic import AgentHarness, Role, Task

harness = AgentHarness(TradingGraph(make_config()), positions={"EURUSD": 0.2})
run = harness.run(Task("EURUSD", date(2024, 3, 1), Role.TRADER, current_weight=0.2))
print(run.state.value, run.decision.target_weight, len(run.evidence), run.report.warnings)
print(run.report.to_markdown())        # decision, findings with evidence ids, critic checks, evidence, audit warnings

port = run_portfolio_backtest(["AAPL", "JPM", "EURUSD"], "2023-01-02", "2023-12-29", make_config(),
                              weighting="risk_parity")
print(port.table())
```

## Configuration highlights (`config.py`)

| key | meaning |
|---|---|
| `llm_provider` · `deep_think_llm` · `quick_think_llm` · `deep_effort` | Model tiers and effort: `claude-sonnet-5-5` at `medium` for the reasoning roles, `claude-haiku-5-5` for the analysts; `claude-opus-5-5` is the optional upgrade for the deep tier |
| `llm_count_tokens` · `llm_min_input_tokens` · `llm_strict_model` | How budget admission prices a prompt (`auto`: the free `count_tokens` endpoint when `ANTHROPIC_API_KEY` is set, else a conservative local estimate); a floor under that estimate (0); reject a reply served by an unexpected model with no recorded fallback (`True`) |
| `llm_timeout_s` · `max_llm_calls` · `max_llm_cost_usd` · `llm_anonymize` | Timeout; hard call cap; hard spend cap (USD, list prices); hide ticker, dates and price level from the model |
| `agentic.approval` | `auto`, `queued`, `deny`, or a block `{"gateway": "signed", "approvers": {id: SECRET_ENV_VAR_NAME}, "quorum", "submit_order_quorum", "tool_quorum", "ttl_s", "price_tolerance", "log_path", "reprice"}` for tool calls that need approval; approver secrets come only from the named environment variables, and re-pricing reads the provider's last close unless `reprice` is false |
| `agentic.memory_tool` | Register `memory.recall` and `memory.remember` (off); `remember` goes through approvals |
| `text_analysts` · `text_analyst_options` | LLM text analysts in the desk (`[]`, off): `fundamentals_text`, `macro_text`; statements path, gated research retrieval |
| `agentic.llm_planner` · `llm_critic` · `llm_reporter` | Which governance steps may use the model (all validated / audited either way) |
| `agentic.symbol_universe` · `deny_tools` · `tool_timeout_s` · `task_db` | Policy inputs; SQLite path for the persistent task store |
| `agentic.workers` · `agentic.queue_limit` · `agentic.sweep_interrupted` · `agentic.instance_id` · `agentic.lease_s` | Task threads per API process; tasks in flight beyond which `POST /tasks` answers 503; whether this process sweeps the store's interrupted records at startup (the parent of `serve --processes N` does it once) — the sweep fails only records owned by this `instance_id` or whose heartbeat lease (`lease_s`, 90 s) has expired, so a sibling instance's live runs survive |
| `agentic.api_keys` | API key → role map for `serve` (development values; an override *replaces* them) |
| `analysts` · `xalpha_universe` | Analyst set; add `"alpha"` (time-series alpha library) or `"xalpha"` (cross-sectional, ranked against `xalpha_universe`, default the core universe of the asset class) |
| `lookback_days` · `alpha_lookback_days` | History handed to the analysts and desk tools (400 days) and to the alpha library and its tools (900 days) |
| `edgar` · `edgar_user_agent` · `edgar_cache_dir` · `edgar_cache_max_age_days` · `edgar_ciks` | SEC EDGAR point-in-time fundamentals and filing news for real-data equities; the SEC requires a contact (`EDGAR_USER_AGENT="Name email@domain"`, read from `.env` by the CLI), without which EDGAR is skipped with one warning; cached endpoint files older than the max age (7 days) are re-fetched |
| `risk.neutral_weight` · `rebalance_band` · `max_position` · `max_var_95` | Strategic weight, no-trade band, firm limits |
| `rules.news_tone_mass` · `risk.aggressive_vol_scaled` | The two v0.11 rules, on by default: news confidence follows the tone the headlines carry (it abstains when they carry almost none); the aggressive risk stance is 1.25 times the vol-target size. `RULES_V02` switches both off |
| `llm_budget_mode` · `llm_max_retries` | `hard` (default) reserves each call's maximum cost before it is sent, so parallel workers cannot overshoot `max_llm_cost_usd`; a retry must be admitted by the budget like a new call |
| `costs.impact_coeff` · `costs.fx_adv_notional` · `initial_capital` · `account_currency` | Square-root market impact in backtests (0 = off), the account size trades scale with (100,000) and the currency it is denominated in (USD) |
| `cash_leg` · `risk_free_annual` | What idle cash earns and what Sharpe is measured against: `auto` credits the 3-month bill (FRED DTB3, one-day publication lag) on real-world providers and the constant `risk_free_annual` (0) on synthetic and CSV data; `fred`, `static`, `off` |
| `execution.fx_lot_size` · `execution.max_order_notional` | FX orders round down to whole lots of the base currency (1000); the cap on one ticket's notional, enforced by policy before approval and again at execution (`None` = `initial_capital * risk.max_position`) |
| `backtest.use_stops` · `costs.*` · `fx_macro_source` · `fred_vintages` · `max_data_staleness_days` | Backtest and data behaviour; ALFRED vintages for revised series |

`make_config(RULES_V02)` reproduces the v0.2 rules for before/after comparisons.

## Extending

Each line below was checked against the code for v0.12; `strat_tsmom` is the worked example
of the last one.

* **New tool:** add a method to `DeskTools`, register it in `build_registry` with the right
  `ToolAnnotations` (read-only, risk, required capabilities, evidence type). It is then
  callable in-process, over MCP, and by the planner, under policy.
* **New policy rule:** a callable `PolicyContext -> PolicyDecision | None`; put it in the
  rule tuple before `allow_rule` and pass the tuple as `PolicyEngine(rules=...)` (the default
  is `DEFAULT_RULES`). A tuple with no terminal rule fails closed.
* **New analyst:** subclass `Analyst` with `gather()` and `rules()`, list free-text keys in
  `untrusted_keys`, return `self.abstain(...)` without data, register it in `ANALYSTS`, and
  name it in `config["analysts"]` (or `DEFAULT_ANALYSTS`) so the graph runs it.
* **New alpha:** a function `AlphaInputs -> ndarray in [-1, 1]` added to `ALPHAS`, and to
  `EQUITY_ALPHAS` / `FX_ALPHAS` so the reports and the alpha analysts use it by default.
* **New baseline stream:** a weight function added to `baseline_weights` in `backtest.py`
  (as `TSMOM(12-1)`, `TSMOM(L/S)` and `Carry` are); it then appears, fully costed, in every
  backtest, portfolio and evaluation table. Its signal belongs in the quant core (last line).
* **New rule change:** put it behind a `config["rules"]` switch and choose it on a design
  period only: `evaluate --data yahoo --universe core --periods design` for the desk's rules,
  `scripts/measure_v09.py --period design_long` for a return stream on the multi-asset
  universes. Adopt it only if its interval against `B&H vol-target` is above zero, and
  register every variant tried in `evaluation.TRIALS`, adopted or not. The holdout, the
  extended universe and the reserve period are spent (consulted for the v0.5.1 and v0.6
  decisions, re-measured in v0.8): they are reports, never a basis for a choice. The next
  unseen data is the forward paper-trading record.
* **New quant routine:** declare it in `cpp/include/at/`, implement it in `cpp/src/`, bind it
  in `cpp/bindings/module.cpp`, mirror it in `quant/pycore.py`, export it through
  `quant/__init__.py` (which validates arguments so both backends refuse the same input), add
  a cross-check to `tests/test_quant.py` and a hypothesis test to `tests/test_fuzz.py`. Every
  function the facade exports is fuzzed on both backends.

## v0.19 (release candidates v0.19.0rc1 and rc2, 2026-11-12): long runs that survive, skips that are counted

Evidence class: code and offline tests (fakes only); no model was run. Running study chains
keep their start-of-run code.

- **Resumable runs.** `agentic_trader/checkpoint.py` (append-only JSON lines, fingerprinted
  header, fsync per unit, torn last line cut; since 2026-11-13 a corrupt line in the middle is
  skipped on its own, the valid rows after it are kept and counted in `Checkpoint.skipped_lines`,
  and the file is rewritten clean); `scripts/v17_exec_lag.py` resumes by default
  (`--fresh` to restart) and a resumed run writes byte-identical files.
- **Local model retries.** `local_llm_retry_budget_s` (default 0; 600 s in the study drivers)
  retries timeouts, refused connections and 5xx with the same request body and raises
  `LocalLLMUnavailable` when spent, instead of silently falling back to rules.
- **Provider misses become counted skips.** `agentic_trader/study_robust.py`: three tries, then a
  skipped row with its reason, retried on resume. The pre-registration rule
  ([v16 draft](docs/evaluation/v16_preregistration.md), "Skipped units"): N is quoted with
  its skip count, skips are counted apart from fallbacks, and a cell with more than 10 % skipped
  is inadmissible; `llm_study --report` shows a `skipped` column.
- **Trial files.** `scripts/measure_v08.py run_trials` writes atomically and fingerprints its
  inputs; files written before fingerprints existed are kept, so registered statistics do not move.
- **Frozen eval set.** `agentic/eval_set.py` reads the paper ledger only up to `LEDGER_CUTOFF`
  (2026-11-06).
- Operations guide: [docs/operations/long_runs.md](docs/operations/long_runs.md). Recipes 131-135
  in [COOKBOOK.md](COOKBOOK.md), lessons 66-68 in [LEARN.md](LEARN.md). Details in
  [CHANGELOG.md](CHANGELOG.md).

## v0.18 (never tagged on its own; shipped in v0.19.0rc1): leftovers closed

Evidence class: code and offline tests; no model was run.

- **Next-open fills with stops.** `backtest.fill = "next_open"` together with
  `backtest.use_stops` used to raise; it now runs in both backends. A stop or take level
  already through the next open exits at that open; otherwise the bar's range decides.
- **Trial counts in `stats`.** `--pre-registry-trials N` and `--trial-returns CSV` report the
  deflated Sharpe at the registered, registered plus pre-registry, and effective trial counts
  (see [Usage](#usage) and the evaluation page).
- **Paper OMS corporate actions are opt-in.** `scripts/paper_trade_v09.py --oms` applies
  corporate actions to the OMS shadow book only with `--oms-corporate-actions` (default off).
  The frozen forward record is unaffected; its current engine vintage is `v09-engine-3`
  (`docs/evaluation/paper_freeze.json`, [how freezing works](docs/evaluation/paper_freeze.md)).
- **Red-team v2 scope.** The end-to-end run on all 1,500 units is replaced by two passes:
  analyst only on 1,500 units, then end to end on `--per-category 2` (100 units). Not run yet.
  How the local-model queue is run and restarted:
  [docs/operations/long_runs.md](docs/operations/long_runs.md).

## v0.16 (v0.16.0, 2026-11-09): the LLM study on a local model

**Plain idea.** Does a language model make the desk better, and in which roles? Asking that of
Claude across a full design costs about $215 per cell (dry-run estimate at list prices), so the
study runs at $0 on a local open-weight model, `qwen2.5:7b-instruct` (4-bit, CPU, Ollama on 127.0.0.1).
The answer is about that 7B model class only.

**What is built (tested offline).** A study driver with a model at the analysts only
(`local_analysts`) and in every role (`local_all`), compared with the rules desk and a
vol-target control; an anonymisation recall audit (can the model name the ticker and month from
a scrubbed prompt?); calibration (dispersion, anchoring, drift between builds); a 150-item
analyst eval set with deterministic checks and a local judge; and a pre-registration of the
decisive test and the single holdout look, amended and signed on 2026-11-12
([document](docs/evaluation/v16_preregistration.md), [amendment record](docs/evaluation/v16_prereg_amendment_2026-11-12.md)). Recipes 114-117 in [COOKBOOK.md](COOKBOOK.md), lesson 56 in
[LEARN.md](LEARN.md).

**First-pass result (2026-11-12, two complete cells; the study was then stopped): no evidence
that the model analysts help.**
Source: [`docs/results/v17/llm_study_interim_report.md`](docs/results/v17/llm_study_interim_report.md)
(`scripts/llm_study.py --report`, 300 decisions per cell, 15 names x 20 dates; evidence class:
measured on real prices, design period, one local model).

| cell | IC, 20-bar forward return [95% CI] | hit rate | Sharpe (secondary) | fallback | admissible |
|---|---|---:|---:|---:|---|
| rules | +0.005 [-0.133, +0.146] | 55.1% | +2.28 | 0.0% | yes |
| local_analysts | -0.042 [-0.173, +0.101] | 54.6% | +1.77 | 0.0% | yes |
| vol-target control | | | +1.93 | | |

The table is descriptive: the first pass has too few dates to accept or reject an edge, and
the pre-registration says so. The difference in IC, local_analysts minus rules, is **-0.046
[95% CI -0.185, +0.067]**. The interval includes zero and its centre is negative, so these data
give no reason to think putting `qwen2.5:7b-instruct` at the analysts improves the desk's
ranking of names. The Sharpe ratios are noisier still (local_analysts minus control -0.16
[-0.85, +0.30]). Read it with four cautions:

- **Most of the "model" cell is rules.** 404 of its 1,200 analyst outputs came from the model
  (the technical analyst on all 300 decisions, the FX macro analyst on 100, sentiment on 4);
  news and fundamentals ran on rules throughout. "0.0% fallback" counts failed model calls,
  not this. The result speaks to the technical and FX macro analysts only.
- **The scoring has since been corrected and this table has not been re-scored.** It ranks
  equities and FX pairs together, and two of the 20 design dates (2016-01-01, 2017-11-23) are
  NYSE closures on which only the five FX pairs were scored; the report's reason for the 20
  left-out decisions ("without 20 forward bars") was wrong. From 2026-11-12 the report ranks
  within asset class and drops closed dates for every name. The re-scored table follows when
  the remaining cells finish.
- **The study was stopped on 2026-11-12.** `local_all` reached 59 of 300 decisions and
  `critic_on` never started; both would have measured the desk as it was before that day's
  critic and weight-bound fixes ([status](docs/evaluation/v16_prereg_status_2026-11-12.md)).
- **This is not the decisive test.** The pre-registered question is whether the model's signal
  carries information the rule's signal does not (the residual IC, on 313 weekly dates, with a
  replication on dates after the model's release). It has not been run and is not scheduled.
  The holdout is untouched.

**Judge calibration (n = 30, [`agreement.json`](docs/results/v17/agreement.json)).** Cohen's
kappa against hand labels, `llama3.1` judge versus the deterministic rule checker:

| criterion | judge kappa (agree) | rule checker kappa (agree) |
|---|---:|---:|
| used_facts | 0.28 (20/30) | 1.00 (30/30) |
| no_invented_numbers | 0.68 (26/30) | 0.81 (28/30) |
| respected_fence | 0.30 (20/30) | 1.00 (30/30) |

The judge is weak on two of the three criteria, and 30 items give wide intervals, so its
verdicts are not used where the rule checker exists.

## v0.15 (v0.15.1, 2026-11-08): text, retrieval and an auditable agent

Filing text from EDGAR and GDELT headlines are in, always fenced as untrusted text. The filing
tone-change feature was run on the design period (9 names, 201 filings): mean IC negative at
every horizon and no horizon reaches |t| = 2, so it is **not supported**
([evaluation](docs/evaluation/evaluation.md), trial 3.2). The GDELT feature is registered as a trial
and its design run is still pending. Research retrieval is
point in time and gated: on 100 questions over a 34-passage invented corpus, recall@5 is 0.990
(TF-IDF and hybrid), which shows the mechanism and says nothing about real filings. The text
analysts are in the desk behind `text_analysts` (off by default, v0.15.1). A 150-snippet injection corpus is
150/150 fenced; on the local qwen2.5:7b-instruct model 21/150 attacks (14%) moved the News analyst's signal (measured, a 7B floor, not Claude). Signed N-of-M approvals (opt-in), deferred tool
loading, `task --record` / `replay`, and stage SLOs are new. Recipes 106-112 in
[COOKBOOK.md](COOKBOOK.md); details in [CHANGELOG.md](CHANGELOG.md). Paper trading is unchanged
by v0.15. Since 2026-11-08 the forward record is produced by `paper.yml` on GitHub Actions
(five runs to 2026-11-12, all green), and the laptop task is only the fallback.

## Operations (v0.14)

The forward paper record runs on GitHub Actions (`.github/workflows/paper.yml`, weekdays
21:30 UTC: jobs `session`, `publish`, `freshness`, `report`). Since round 3 (review E-3) the
record lives on its own append-only branch, `paper-ledger`, not on `main`: the session and
freshness jobs check out code from `main` and `results/paper/` from `paper-ledger`, and
`publish` commits and pushes only to `paper-ledger` (it creates the branch from `main` the
first time). The `results/paper/` copy on `main` is the snapshot from that day and is no
longer updated; read the live record at
[`paper-ledger:results/paper/`](https://github.com/AshJha0/agentic-trader/tree/paper-ledger/results/paper).
Each run records a
`price_vintage` hash of the bars it read in `results/paper/runs.jsonl`; the freshness job fails
when the last session is more than two business days old, and any failure opens or comments on
one issue labelled `paper-record`. The laptop task `scripts/paper_daily.cmd` is the fallback;
run only one of the two. `ci.yml` is the PR gate and also runs on every push to `main`. A newer push cancels an older run on
the same PR branch but never on `main`, so every `main` commit gets a complete result. Jobs:
lint (ruff blocking with the rule sets `E4`, `E7`, `E9`, `F`, bugbear `B` and bandit `S`, the
remaining `B`/`S` hits ignored per file with a reason in `pyproject.toml`; `scripts/gen_counts.py
--check`; mypy blocking on the quant core and advisory on the whole package); the Python 3.10 to
3.14 matrix, each installing its hashed lock `requirements/lock-py<version>.txt` with
`pip install --require-hashes` and running `pytest -m "not slow"` with coverage, which is a gate
(`fail_under = 90` in `[tool.coverage.report]`; a run below it fails); a minimum-versions leg
(Python 3.10 with the declared floors numpy 1.24.0 and pandas 2.1.0); a leg that installs the
v0.8 pin set `requirements-lock.txt` and checks the installed versions equal its pins; the C++
core; and the docs checks. `nightly.yml` (03:17 UTC) runs the full suite, slow tests included, on
the numpy backend and on the C++ backend (Python 3.12). `lockfiles.yml` (manual) regenerates the
hashed locks with uv. `paper.yml` installs `requirements/paper-lock-py3.12.txt`, the same v0.8
versions with a SHA-256 per file. The paper OMS shadow record (`--oms`, off by
default) is labelled `oms_shadow_v14` and never writes `ledger.csv`; the frozen forward record
(from 2026-09-29) is unchanged.

Steps only the repository owner can take on GitHub:

1. Settings > Actions > General: allow Actions to run.
2. Workflow permissions can stay at the default (read). `paper.yml` grants `contents: write` to
   the `publish` job and `issues: write` to `report` explicitly, which overrides the default
   for those jobs only; raising the repository default would widen every other workflow.
3. Ruleset on `main` with no bypass: require a pull request, block force pushes and deletion,
   and require the `ci.yml` checks (`Lint (ruff) and types (mypy, blocking on the quant core)`,
   `Python 3.10 (numpy backend)` to `Python 3.14 (numpy backend)`,
   `Minimum declared versions (Python 3.10, numpy backend)`,
   `Locked dependencies (Python 3.12, numpy backend)`, `C++ core (ubuntu-latest)`,
   `C++ core (windows-latest)`, `C++ core (macos-latest)`, `Docs (cookbook, diagrams, links)`).
   The paper job no longer pushes to `main`, so no bypass is needed.
4. Ruleset on `paper-ledger`: block force pushes and deletion (the record is append-only) and
   require nothing else, since the bot pushes to it directly.
5. After the first green scheduled run, disable the laptop `paper_daily.cmd` task so two
   runners do not write the same record.

## Tests

```bash
pytest -q -m "not slow"                     # CI, Python 3.12, numpy backend, v0.19 branch (run 43228695881): 2073 passed, 53 skipped, 17 slow deselected; incl. adversarial, API, a real MCP stdio round trip and hypothesis fuzzing of both boundaries
pytest --cov=agentic_trader --cov-report=term-missing   # <!-- count:coverage_pct2 -->94.01<!-- /count -->% line+branch coverage in that CI run (<!-- count:coverage_statements -->16,582<!-- /count --> statements, <!-- count:coverage_branches -->4,966<!-- /count --> branches; <!-- count:coverage_missed_lines -->744<!-- /count --> lines and <!-- count:coverage_missed_branches -->457<!-- /count --> branch arcs missed); CI fails below 90% ([tool.coverage.report] fail_under); it counts the numpy backend (quant/pycore.py) only: the C++ core in cpp/ is checked by the parity tests, not measured by coverage
AGENTIC_TRADER_BACKEND=python pytest -q     # the numpy fallback: 839 passed, 40 skipped (C++-only tests)
ctest --test-dir build -C Release           # 26 C++ test functions in cpp/tests/test_core.cpp, run as the one ctest test at_core_tests
python scripts/run_cookbook.py --offline && python scripts/check_mermaid.py && python scripts/check_links.py   # the docs, as CI runs them
python scripts/gen_counts.py --check        # quoted counts in step with the repository, as CI runs it
```

**Quoted counts.** A number such as the coverage figure above sits between
`<!-- count:NAME -->` and `<!-- /count -->` markers in README.md and the docs site.
`scripts/gen_counts.py` recomputes each one from the repository and rewrites the text between
the markers; `--check` writes nothing and exits non-zero on drift, and CI runs it in the lint
job. Test counts need a full collection (`--with-tests`) and coverage counts need the
`coverage.xml` of a full run with branch data (`--coverage-xml PATH`, for example the
`coverage-xml` artifact of the Python 3.12 CI leg); without them those counts are skipped,
not guessed, because an old or partial file gives false drift. To update after a change, run
`python scripts/gen_counts.py` (with the two options when test or coverage figures moved),
read the diff and commit it.
