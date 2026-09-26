# AgenticTrader

[![CI](https://github.com/AshJha0/agentic-trader/actions/workflows/ci.yml/badge.svg)](https://github.com/AshJha0/agentic-trader/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-ashjha0.github.io%2Fagentic--trader-16697a)](https://ashjha0.github.io/agentic-trader/)

**Documentation site: https://ashjha0.github.io/agentic-trader/**

| Guide | For |
|---|---|
| [LEARN.md](LEARN.md) | 33 concepts: how the repo implements them, real numbers, questions |
| [COOKBOOK.md](COOKBOOK.md) | 72 copy-pasteable recipes, including the agentic layer, quant research and operations; every offline one runs in CI |
| [Architecture](docs/architecture/overview.md) · [Diagrams](docs/DIAGRAMS.md) | Components, data flow, design decisions, 30 diagrams |
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

On **real prices**, the rule-based desk was evaluated over 60 instruments: the 15 *core*
ones every rule choice was made on (10 equities, 5 FX pairs; rules chosen on 2016–2021 only,
judged once on a 2022–2026 holdout) and 45 *extended* ones (sector equities, rates / credit /
commodity ETFs, FX crosses) that no choice ever consulted. Since v0.6 the fundamentals and
news analysts read SEC EDGAR filings point in time, and every difference carries a bootstrap
interval across instruments.

- **Per instrument:** it does **not** beat buy & hold on Sharpe out of sample — core
  0.46 vs 0.55 (difference -0.08, 95% interval
  [-0.19, +0.02]); extended 0.45 vs 0.50
  (-0.04 [-0.10, +0.01]), beating buy & hold on 14 of 45 names.
- **Drawdown:** **about half of buy & hold's** — core equities 21.9% vs
  40.2% on the holdout, extended 17.6% vs
  27.1%, lower on 42 of the 45 extended names.
- **As a 15-sleeve portfolio:** Sharpe 1.09 on the holdout with a
  7.8% drawdown, against 1.06 / 20.8% for plain
  buy & hold and 1.24 for buy & hold scaled to the same volatility. Under the
  v0.5.1 defaults (no filings) it was 1.16 / 7.0%.
- **Point-in-time filings (v0.6):** giving the untuned fundamentals and news rules real
  data changed the core equities' Sharpe by 0.00 (design) and +0.01
  (holdout), intervals ±0.1, while adding 4–7 points of exposure and 3–4 points of
  drawdown; on the 22 (of 26) extended equities whose result changed — names the rules never saw — it added +0.02 and
  +0.07 with intervals that exclude zero. The data stays on; the rules are the
  next thing for the protocol.
- **Cross-sectional analyst (v0.6):** measured under the protocol — core design
  -0.01 [-0.02, 0.00], core holdout 0.00, extended holdout
  -0.01, reserve -0.03 — so it is **off by default**.
- **FX carry weight (v0.5.1):** the protocol's first adopted rule change — chosen on the
  core pairs' design period, it improved every unseen slice without making FX beat buy & hold.
- **Execution costs:** with square-root market impact on, the desk keeps its Sharpe at $100k
  and $10M and loses 0.09 at $1B; signal-flipping baselines lose far more.
- **Alpha analyst:** measured three times on the design period: noise, so it stays off.
- **LLM desk:** measured once (v0.5.1: five stocks, Q1 2024, Claude Opus, anonymised prompts,
  $4): the same Sharpe as the rules with less than half the exposure. The multi-year run —
  Opus, Sonnet and Haiku tiers on the core universe over design and holdout, repeated runs
  for the model's variance, a calibration — is staged with a dollar cap per stage and its
  results are reported the moment it has run.

Details: [docs/evaluation](docs/evaluation/evaluation.md).

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
  `<untrusted_data>` blocks that cannot be escaped. `max_llm_calls` caps spend. The firm
  limits run after any model output.
* **A benchmark, then tilts.** With no view the desk holds a strategic weight (equities
  fully invested; FX the higher-yielding side, sized by the point-in-time carry and capped
  at ±0.5), and conviction tilts around it.
* **Point-in-time data.** Prices are clipped twice. FX macro comes from FRED as known on
  each date. Stale feeds are refused. Memory outcomes become visible only after their horizon.

### Equity vs FX

| | Equity | FX |
|---|---|---|
| Value analyst | Fundamentals: P/E, growth, margins, leverage, FCF from SEC EDGAR facts as first filed (point in time); EPS surprise and insider direction only when a source has them | Macro: point-in-time policy-rate differential (carry), inflation (PPP), distance from the 200-day average |
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
    store.py               SQLite task store: records survive restarts, in-flight runs are failed on reload
  alpha.py                 alpha library, IC / decay / hit rate / turnover, significance-gated combination
  xalpha.py                cross-sectional alphas: per-day z-scores / ranks within asset class, per-date IC, spreads
  algo.py                  TWAP / VWAP / POV / Almgren-Chriss schedules, intraday simulator, decision -> plan
  portfolio.py             EWMA + Ledoit-Wolf covariance, 5 weighting schemes, cross-asset risk budgets, attribution
  stats.py                 bootstrap Sharpe CI, probabilistic and deflated Sharpe, minimum track record, paired bootstrap across instruments
  prompts.py               prompt registry: a content hash of every prompt the desk can send, recorded in every evaluation
  calibration.py           dispersion / anchoring / drift of the desk's judgement on one frozen state
  quant/                   facade: C++ if built, otherwise pycore.py (numpy mirror)
  data/                    synthetic | yahoo | csv providers, clean_ohlcv, fred.py (point-in-time macro, ALFRED vintages),
                           edgar.py (SEC EDGAR: point-in-time fundamentals and filing-stream news, first prints)
  agents/                  analysts (incl. alpha and cross-sectional xalpha), researchers + facilitator, trader, risk team + PM
  graph.py                 TradingGraph stages, propagate() and scan()
  backtest.py              walk-forward agent backtest vs 6 baselines with optional market impact; portfolio backtest
  evaluation.py            design / holdout / Q1-2024 / reserve evaluation over the core and extended universes; repeats, paired bootstraps
  memory.py · llm.py (call and dollar budgets) · anonymize.py · cli.py
scripts/                   run_cookbook.py · check_mermaid.py · check_links.py (the CI docs job) · build_cpp · set_api_key
tests/                     280 pytest tests (fuzz 21 C++ boundary + 7 agentic layer, v0.6 20, EDGAR 11, v0.5 18, agentic 30, adversarial 15, ...)
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
(cross-checked in CI). Set `AGENTIC_TRADER_BACKEND=python` to force the fallback.

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
agentic-trader mcp                                     # the same tools as an MCP stdio server

# research
agentic-trader backtest  NVDA --start 2024-01-02 --end 2024-03-28 --stops on --impact 1.0 --capital 1e8
agentic-trader portfolio AAPL,JPM,XOM,EURUSD,USDJPY --start 2023-01-02 --end 2023-12-29 --weighting risk_parity --class-budgets equity=0.6,fx=0.4
agentic-trader alpha     USDJPY --start 2021-01-04 --end 2024-03-28 --horizon 10
agentic-trader xalpha    AAPL,MSFT,NVDA,JPM,XOM --start 2021-01-04 --end 2024-03-28
agentic-trader execute   AAPL --date 2024-03-01 --target 0.6 --current 0.1 --capital 5000000
agentic-trader stats     returns.csv --trials 16
agentic-trader evaluate  AAPL,EURUSD --periods q1_2024
```

With real prices (network) and Claude (API key):

```bash
agentic-trader evaluate --data yahoo --universe all --periods design,holdout,q1_2024,reserve   # the published protocol
agentic-trader evaluate --data yahoo --universe core --periods design,holdout --impact 1.0 --capital 1e9
agentic-trader evaluate --data yahoo --fred-vintages --fred-cache results/fred_cache          # CPI as first published
agentic-trader evaluate --data yahoo --universe core --periods design,holdout --edgar-cache results/edgar_cache  # EDGAR fundamentals and filing news (EDGAR_USER_AGENT in .env)
set ANTHROPIC_API_KEY=...                                                  # or `ant auth login`
agentic-trader task MSFT --llm anthropic --data yahoo --max-llm-calls 50 --max-llm-cost 5 --llm-planner
agentic-trader evaluate AAPL,NVDA --data yahoo --periods holdout --every 10 --repeats 3 --llm anthropic --anonymize --max-llm-cost 50   # model variance
agentic-trader calibrate AAPL --date 2024-03-01 --n 5 --anchors none,-0.5,0,0.5 --llm anthropic --anonymize --max-llm-cost 10        # dispersion, anchoring, drift
agentic-trader serve --processes 4 --workers 4 --task-db results/tasks.sqlite                                                       # bounded pool per process
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
| `agentic.workers` · `agentic.queue_limit` · `agentic.sweep_interrupted` | Task threads per API process; tasks in flight beyond which `POST /tasks` answers 503; whether this process marks the store's in-flight records FAILED at startup (the parent of `serve --processes N` does it once) |
| `agentic.api_keys` | API key → role map for `serve` (development values; an override *replaces* them) |
| `analysts` · `xalpha_universe` | Analyst set; add `"alpha"` (time-series alpha library) or `"xalpha"` (cross-sectional, ranked against `xalpha_universe`, default the core universe of the asset class) |
| `lookback_days` · `alpha_lookback_days` | History handed to the analysts and desk tools (400 days) and to the alpha library and its tools (900 days) |
| `edgar` · `edgar_user_agent` · `edgar_cache_dir` · `edgar_cache_max_age_days` · `edgar_ciks` | SEC EDGAR point-in-time fundamentals and filing news for real-data equities; the SEC requires a contact (`EDGAR_USER_AGENT="Name email@domain"`, read from `.env` by the CLI), without which EDGAR is skipped with one warning; cached endpoint files older than the max age (7 days) are re-fetched |
| `risk.neutral_weight` · `rebalance_band` · `max_position` · `max_var_95` | Strategic weight, no-trade band, firm limits |
| `costs.impact_coeff` · `costs.fx_adv_notional` · `initial_capital` | Square-root market impact in backtests (0 = off) and the account size trades scale with |
| `backtest.use_stops` · `costs.*` · `fx_macro_source` · `fred_vintages` · `max_data_staleness_days` | Backtest and data behaviour; ALFRED vintages for revised series |

`make_config(RULES_V02)` reproduces the v0.2 rules for before/after comparisons.

## Extending

* **New tool:** add a method to `DeskTools`, register it in `build_registry` with the right
  annotations (read-only, risk, required capabilities, evidence type). It is then callable
  in-process, over MCP, and by the planner, under policy.
* **New policy rule:** a callable `PolicyContext -> PolicyDecision | None`; put it in the
  rule tuple before `allow_rule`.
* **New analyst:** subclass `Analyst` with `gather()` and `rules()`, list free-text keys in
  `untrusted_keys`, return `self.abstain(...)` without data, then register it in `ANALYSTS`.
* **New alpha:** a function `AlphaInputs -> ndarray in [-1, 1]` added to `ALPHAS`.
* **New rule change:** put it behind a `config["rules"]` switch, choose it on the *core*
  design period with `evaluate --universe core --periods design`, then judge it on the
  extended universe and the reserve period (`--universe extended --periods design,holdout,reserve`).
* **New quant routine:** add it to `cpp/`, bind it in `module.cpp`, mirror it in `pycore.py`,
  add a cross-check test, and add it to `tests/test_fuzz.py` so hypothesis fuzzes it.

## Tests

```bash
pytest -q                                   # 280 tests incl. adversarial, API, a real MCP stdio round trip and hypothesis fuzzing of both boundaries
AGENTIC_TRADER_BACKEND=python pytest -q     # the numpy fallback
ctest --test-dir build -C Release           # 14 C++ test groups
python scripts/run_cookbook.py --offline && python scripts/check_mermaid.py && python scripts/check_links.py   # the docs, as CI runs them
```
