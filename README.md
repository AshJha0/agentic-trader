# AgenticTrader

[![CI](https://github.com/AshJha0/agentic-trader/actions/workflows/ci.yml/badge.svg)](https://github.com/AshJha0/agentic-trader/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-ashjha0.github.io%2Fagentic--trader-16697a)](https://ashjha0.github.io/agentic-trader/)

**Documentation site: https://ashjha0.github.io/agentic-trader/**

| Guide | For |
|---|---|
| [LEARN.md](LEARN.md) | 26 concepts: how the repo implements them, real numbers, questions |
| [COOKBOOK.md](COOKBOOK.md) | 56 copy-pasteable recipes, including the agentic layer and quant research |
| [Architecture](docs/architecture/overview.md) · [Diagrams](docs/DIAGRAMS.md) | Components, data flow, design decisions, 24 diagrams |
| [Specification](docs/SPECIFICATION.md) · [Threat model](docs/threat-model/threat-model.md) | Requirements with status; 32 threats mapped to controls and tests |
| [Evaluation](docs/evaluation/evaluation.md) · [API](docs/api/api.md) | Real-price results with a design / holdout split; the Python, HTTP, MCP and C++ interfaces |

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

On **real prices**, the rule-based desk was evaluated over 15 instruments (10 equities, 5 FX
pairs). Rules were chosen on 2016–2021 only and judged once on a 2022–2026 holdout.

- **Per instrument:** it does **not** beat buy & hold on Sharpe out of sample (0.44 vs
  0.55).
- **Drawdown:** it has **about half the drawdown** in every period.
- **As a 15-sleeve portfolio:** it beats plain buy & hold on Sharpe (1.14 vs 1.06, with a
  6.8% vs 20.8% drawdown), but not buy & hold scaled to the same volatility (1.24).
- **Alpha analyst (v0.4):** adding the alpha library as a fifth analyst moved design-period
  mean Sharpe from 0.65 to 0.60 and the median from 0.55 to 0.60: noise, so it stays off by default.
- **LLM mode:** not evaluated; no claims are made about it.

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
                 │ Technical │ Fundamentals (equity) / Macro-rates (FX) │ News │ Sentiment │ [Alpha] │
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
  fully invested, FX flat), and conviction tilts around it.
* **Point-in-time data.** Prices are clipped twice. FX macro comes from FRED as known on
  each date. Stale feeds are refused. Memory outcomes become visible only after their horizon.

### Equity vs FX

| | Equity | FX |
|---|---|---|
| Value analyst | Fundamentals: P/E vs sector, growth, margins, leverage, FCF, EPS surprise, insiders | Macro: point-in-time policy-rate differential (carry), inflation (PPP), distance from the 200-day average |
| Alpha library | 8 signals (momentum, reversal, breakout, MACD, RSI, low-vol, 52-week high) | The same plus carry |
| News scoring | Headline tone | Tone oriented to base vs quote ("JPY weakens" is bullish for USD/JPY) |
| Strategic weight | 1.0 | 0.0 |
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
    api.py                 FastAPI gateway: tasks, reports, traces, evidence, approvals, tools, metrics
  alpha.py                 alpha library, IC / decay / hit rate / turnover, combination, AlphaAnalyst inputs
  algo.py                  TWAP / VWAP / POV / Almgren-Chriss schedules, intraday simulator, decision -> plan
  portfolio.py             EWMA + Ledoit-Wolf covariance, equal / inverse-vol / risk parity / min-var / mean-var, risk attribution
  stats.py                 bootstrap Sharpe CI, probabilistic and deflated Sharpe, minimum track record
  quant/                   facade: C++ if built, otherwise pycore.py (numpy mirror)
  data/                    synthetic | yahoo | csv providers, clean_ohlcv, fred.py (point-in-time macro)
  agents/                  analysts (incl. alpha), researchers + facilitator, trader, risk team + PM
  graph.py                 TradingGraph stages, propagate() and scan()
  backtest.py              walk-forward agent backtest vs 6 baselines; portfolio backtest with weighting schemes
  evaluation.py            design / holdout / Q1-2024 evaluation harness
  memory.py · llm.py · anonymize.py · cli.py
tests/                     197 pytest tests (agentic 30, adversarial 15, services 7, quant research 18, ...)
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
agentic-trader tools                                   # the 15-tool catalogue
agentic-trader serve                                   # HTTP API at http://127.0.0.1:8000/docs
agentic-trader mcp                                     # the same tools as an MCP stdio server

# research
agentic-trader backtest  NVDA --start 2024-01-02 --end 2024-03-28 --stops on
agentic-trader portfolio AAPL,JPM,XOM,EURUSD,USDJPY --start 2023-01-02 --end 2023-12-29 --weighting risk_parity
agentic-trader alpha     USDJPY --start 2021-01-04 --end 2024-03-28 --horizon 10
agentic-trader execute   AAPL --date 2024-03-01 --target 0.6 --current 0.1 --capital 5000000
agentic-trader stats     returns.csv --trials 16
agentic-trader evaluate  AAPL,EURUSD --periods q1_2024
```

With real prices (network) and Claude (API key):

```bash
agentic-trader evaluate --data yahoo --periods design,holdout,q1_2024      # the published protocol
set ANTHROPIC_API_KEY=...                                                  # or `ant auth login`
agentic-trader task MSFT --llm anthropic --data yahoo --max-llm-calls 50 --llm-planner
```

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
| `llm_timeout_s` · `max_llm_calls` · `llm_anonymize` | Timeout; hard call cap; hide ticker, dates and price level from the model |
| `agentic.approval` | `auto`, `queued` or `deny` for tool calls that need approval |
| `agentic.llm_planner` · `llm_critic` · `llm_reporter` | Which governance steps may use the model (all validated / audited either way) |
| `agentic.symbol_universe` · `deny_tools` · `tool_timeout_s` | Policy inputs |
| `agentic.api_keys` | API key → role map for `serve` (development values) |
| `analysts` | Analyst set; add `"alpha"` for the alpha library analyst |
| `risk.neutral_weight` · `rebalance_band` · `max_position` · `max_var_95` | Strategic weight, no-trade band, firm limits |
| `backtest.use_stops` · `costs.*` · `fx_macro_source` · `max_data_staleness_days` | Backtest and data behaviour |

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
* **New rule change:** put it behind a `config["rules"]` switch, choose it on the design
  period with `evaluate`, then judge it once on the holdout.
* **New quant routine:** add it to `cpp/`, bind it in `module.cpp`, mirror it in `pycore.py`
  and add a cross-check test.

## Tests

```bash
pytest -q                                   # 197 tests incl. adversarial, API and a real MCP stdio round trip
AGENTIC_TRADER_BACKEND=python pytest -q     # the numpy fallback
ctest --test-dir build -C Release           # 13 C++ test groups
```
