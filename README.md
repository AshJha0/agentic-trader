# AgenticTrader

[![CI](https://github.com/AshJha0/agentic-trader/actions/workflows/ci.yml/badge.svg)](https://github.com/AshJha0/agentic-trader/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-ashjha0.github.io%2Fagentic--trader-16697a)](https://ashjha0.github.io/agentic-trader/)

**Documentation site: https://ashjha0.github.io/agentic-trader/**

| Guide | For |
|---|---|
| [How the AI works](docs/ai/ai.md) · [How the quant works](docs/quant/quant.md) | Start here. The agents, the LLM, what is and is not machine learning, and the agentic layer; then the quant core, the backtester, risk, alphas, portfolios and the statistics |
| [LEARN.md](LEARN.md) | 50 concepts: how the repo implements them, real numbers, questions |
| [COOKBOOK.md](COOKBOOK.md) | 100 copy-pasteable recipes, including the agentic layer, quant research, operations and the v0.7 to v0.12 research tools; every offline one runs in CI |
| [Architecture](docs/architecture/overview.md) · [Diagrams](docs/DIAGRAMS.md) | Components, data flow, design decisions, 38 diagrams |
| [Specification](docs/SPECIFICATION.md) · [Threat model](docs/threat-model/threat-model.md) | Requirements with status; 40 threats mapped to controls and tests |
| [Evaluation](docs/evaluation/evaluation.md) · [API](docs/api/api.md) | Real-price results on 60 instruments with a design / holdout / reserve split and an impact sweep; the Python, HTTP, MCP and C++ interfaces |

AgenticTrader is an **agentic trading desk** for **equities and FX**. A team of specialised
agents (analysts, bull and bear researchers, a trader, a risk team, a portfolio manager)
produces sized, explained decisions. An **agentic layer** runs them the way an enterprise
system would: every data access is a catalogued, policy-gated tool call that leaves an
evidence record; a plan (canonical or model-proposed) is validated before it runs; a critic
checks the result; and the report is audited so every number and every evidence id traces
back. Underneath is a **C++17 quant core** (indicators, backtester with stops and carry,
risk, alphas, execution schedules) exposed to Python through pybind11, and a **quant research
layer** for alphas, execution algorithms, portfolio construction and backtest statistics.

> Research and education only. This is not investment advice. The synthetic data mode
> produces fake prices, news and fundamentals. The framework never connects to a broker.

## Results in one paragraph

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
published as a report, and a daily paper-trading job from 2026-09-29 is the forward test.*

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

**The headline:** out of sample the desk is **below buy & hold on Sharpe**, per instrument
and as a portfolio — inside the noise for the portfolio, BH-significant on the 45 names it
was never tuned on — with **about half of buy & hold's drawdown, which the
volatility-targeted control achieves too.**

- **Per instrument:** core holdout median Sharpe 0.30 (desk) vs 0.51 (buy & hold) vs 0.52
  (buy & hold scaled every day to the same 15% volatility target the desk's risk analysts use, from trailing 20-day volatility and capped at the 1.0 position limit — the fair control); mean paired difference
  desk − B&H −0.10 [−0.21, −0.00] p 0.04 and desk − vol-target −0.11 [−0.21, −0.00] p 0.04,
  neither BH-significant. Extended holdout 0.25 vs 0.39 vs 0.27: desk − B&H −0.07
  [−0.12, −0.02] p 0.01 **BH-significant** (the desk beats buy & hold on 12 of 45 names);
  desk − vol-target −0.03 [−0.09, +0.02] p 0.19, not BH-significant. All 60 (clusters):
  desk − B&H −0.08 [−0.15, −0.03] p 0.00 BH-significant; desk − vol-target −0.05
  [−0.15, 0.00] p 0.07, not BH-significant. On the design period the core medians are 0.67 vs
  0.73 vs 0.69 (desk − B&H +0.06 [−0.06, +0.17] p 0.29, not BH-significant). It beats the
  signal-flipping baselines on most slices: holdout, desk − SMA(20/50) +0.28 [+0.16, +0.41]
  p 0.00 BH-significant on the extended names and +0.25 [+0.01, +0.43] p 0.04 (not
  BH-significant) on all 60.
- **Drawdown, against the fair control:** core holdout mean max drawdown 17.40% (desk) vs
  31.64% (buy & hold) vs 18.98% (vol-target): desk − B&H −14.24 points [−20.41, −8.70] p 0.00
  BH-significant; desk − vol-target −1.58 [−4.33, +1.14] p 0.27, not BH-significant. On the
  10 core *equities* — the names the rules were tuned on — 22.11% vs 40.24% vs 21.28%, and
  desk − vol-target is +0.83 [−1.63, +3.21] p 0.50, not BH-significant: not lower than the control's. On the 45
  extended names 15.46% vs 26.39% vs 19.79%: desk − vol-target −4.33 [−6.10, −2.55] p 0.00
  BH-significant, desk − B&H −10.93 [−13.41, −8.64] p 0.00 BH-significant. On FX the
  vol-target control sits at the shared 1.0 position cap most of the time (core FX holdout
  drawdown 14.40% vs buy & hold's 14.45%), so the FX drawdown comparison has no control.
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
- **Selection statistics:** 26 trials judged on the design period (24 re-measured under the
  v0.8 engine, 2 historical); the frozen rules' design-period portfolio: annual Sharpe 1.375,
  bootstrap 95% CI [0.593, 2.17], expected maximum Sharpe of 26 null trials 0.161, deflated
  Sharpe probability 0.998, minimum track record 496 periods — an upper bound on the true
  significance, as the report itself says.
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
        Critic (deterministic checks; model may only lower confidence) → evidence validation
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
    critic.py              deterministic checks + model critique that can only lower confidence
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
tests/                     879 pytest tests on both backends (v0.8 fixes 105 + 17 CLI, fuzz 73 C++ boundary + 7 agentic layer, v0.8 agents 68, v0.8 engine 57,
                           v0.8 data 57, v0.8 execution 41, v0.8 agentic 41, quant edges 38, v0.7 37, agents 35, v0.8 portfolio 30, agentic 30, v0.11 18 + 4, v0.9 8 + 3, ...)
examples/                  equity, FX, baseline comparison
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (source .venv/bin/activate on Linux/macOS)
pip install -e ".[all]"           # anthropic, yfinance, pybind11, pytest, mcp, fastapi, uvicorn
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
| `llm_provider` · `deep_think_llm` · `quick_think_llm` · `deep_effort` | Model tiers and effort |
| `llm_timeout_s` · `max_llm_calls` · `max_llm_cost_usd` · `llm_anonymize` | Timeout; hard call cap; hard spend cap (USD, list prices); hide ticker, dates and price level from the model |
| `agentic.approval` | `auto`, `queued` or `deny` for tool calls that need approval |
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

## Tests

```bash
pytest -q                                   # 879 tests collected on either backend (C++ backend: 879 passed) incl. adversarial, API, a real MCP stdio round trip and hypothesis fuzzing of both boundaries
pytest --cov=agentic_trader --cov-report=term-missing   # 95% line coverage on the numpy backend at v0.8.0 (a report, not a gate); weakest file data/yahoo.py at 75% (network branches)
AGENTIC_TRADER_BACKEND=python pytest -q     # the numpy fallback: 839 passed, 40 skipped (C++-only tests)
ctest --test-dir build -C Release           # 26 C++ test functions in cpp/tests/test_core.cpp, run as the one ctest test at_core_tests
python scripts/run_cookbook.py --offline && python scripts/check_mermaid.py && python scripts/check_links.py   # the docs, as CI runs them
```
