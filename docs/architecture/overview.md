# Architecture overview

agentic-trader has three layers:

1. **The desk** — specialised agents that turn point-in-time data into a sized, explained
   decision (`agentic_trader.graph`, `agents`, `state`).
2. **The agentic layer** — the control plane that runs the desk the way an enterprise system
   would: catalogued tools, policy, evidence, planning, a state-machine harness, a critic,
   audited reports, retrieval, an MCP server and an HTTP API (`agentic_trader.agentic`).
3. **The quant research layer** — alphas, execution algorithms, portfolio construction and
   backtest statistics, on top of the C++ core (`alpha`, `algo`, `portfolio`, `stats`, `quant`, `cpp/`).

This document covers the components, the flow of one task, the design decisions and the
extension points. Diagrams are in [../DIAGRAMS.md](../DIAGRAMS.md).

## Components

### The desk

| Module | Responsibility |
|---|---|
| `graph.py` | `TradingGraph` stages: `prepare` (point-in-time data, guards, memory), `run_analyst`, `run_debate`, `run_trader`, `run_risk`, `record`. `propagate()` runs them in order; `scan()` runs a watchlist |
| `state.py` | Typed documents with `evidence_ids`: `AnalystReport` (with `abstained`, `rule_signal`), `DebateOutcome`, `TradeProposal`, `RiskView`, `FinalDecision`; `TradingState` with `current_weight`, `knowledge`, `alpha` |
| `agents/analysts.py` | Technical, Fundamentals, Macro (FX), News, Sentiment and Alpha analysts; `untrusted_keys`; abstention |
| `agents/researchers.py` | Bull, bear, facilitator, weighted consensus |
| `agents/trader.py` | Strategic weight plus tilt, ATR stops and targets, `sane_levels`, policy passages in the prompt |
| `agents/risk.py` | Three risk analysts, portfolio manager, firm limits, no-trade band |
| `llm.py`, `anonymize.py` | Claude client with tiers, timeout, refusal fallback, usage and cost; call budget; anonymised prompts |
| `data/` | `MarketDataProvider`, `clean_ohlcv`, synthetic / Yahoo / CSV providers, `fred.py` point-in-time macro |
| `memory.py` | Atomic, corruption-tolerant decision log; horizon-gated outcomes |

### The agentic layer (`agentic_trader.agentic`)

| Module | Responsibility |
|---|---|
| `domain.py` | Frozen dataclasses: `Task`, `Plan`, `PlanStep`, `StepType`, `ToolDescriptor`, `ToolAnnotations`, `ToolRequest`/`ToolResult`, `Evidence`, `EvidenceType`, `Finding`, `PolicyDecision`, `Role`, `Capability`, `TaskState` and the legal `TRANSITIONS` |
| `tools.py` | `ToolRegistry` (schemas derived from signatures, `register_descriptor` for remote tools), `coerce_arguments`, `ToolExecutor` (policy → gateway → coerce → timed run with retry → evidence, traced) |
| `servers.py` | `DeskTools` and `build_registry`: 15 tools on `market_data`, `quant`, `knowledge`, `portfolio`, `execution`; `RecordingProvider` |
| `policy.py` | Rules, `PolicyEngine`, `ROLE_CAPABILITIES`, `AutoApprovalGateway`, `QueuedApprovalGateway`, `DenyApprovalGateway` |
| `planner.py` | `canonical_plan`, `propose_plan` (model), `validate_plan`, `make_plan` |
| `harness.py` | `AgentHarness`, `TaskRun`: the state machine, tool batching, approvals, cancellation, governance steps |
| `critic.py` | `Critic`: seven deterministic checks and an optional model critique that only lowers confidence |
| `reporter.py` | `collect_facts`, template or model narrative, `number_audit`, `evidence_audit`, `Report` (JSON and markdown) |
| `rag.py`, `knowledge/docs` | `KnowledgeBase` with a hashed TF-IDF embedder over 11 documents |
| `tracing.py` | `Tracer` spans, `Metrics` (Prometheus text), JSON-lines logging |
| `mcp_server.py` | The registry as an MCP stdio server; `discover`, `call`, `registry_from_stdio` |
| `api.py` | FastAPI gateway with API-key roles |

### The quant research layer

| Module | Responsibility |
|---|---|
| `alpha.py` | Nine alphas, `compute_alphas`, `combine`, `alpha_report` (IC, decay, hit rate, spread, autocorrelation, correlations), `alpha_snapshot` |
| `algo.py` | Volume profiles, intraday bars, TWAP / VWAP / POV / Almgren-Chriss schedules, `simulate_execution`, `plan_execution` |
| `portfolio.py` | EWMA and Ledoit-Wolf covariance, five weighting schemes, `risk_contributions`, `construct` |
| `stats.py` | `sharpe_stats`, `sharpe_ci_bootstrap`, `probabilistic_sharpe`, `expected_max_sharpe`, `deflated_sharpe`, `min_track_record`, `selection_report` |
| `backtest.py` | Walk-forward agent backtest vs six baselines; `run_portfolio_backtest(weighting=...)` |
| `evaluation.py` | Design / holdout / Q1-2024 harness with parallel workers and LLM usage accounting |
| `quant/`, `cpp/` | Indicators (incl. rolling extremes, Spearman), risk, strategies, backtester with stops and carry, Almgren-Chriss; numpy twin |

## One task, step by step

1. **Submit.** `AgentHarness.run(Task(symbol, as_of, role, current_weight, question))` creates a
   `TaskRun` with its own `EvidenceStore` and `Tracer`.
2. **Plan** (PLANNING → VALIDATING_PLAN). The canonical plan is knowledge search, alpha
   snapshot, the asset class's analysts, debate, trader, risk, then critic, validation and
   finalisation. With `agentic.llm_planner` the model proposes steps and the validator makes
   them safe. Every tool step is pre-checked against policy for the task's role; a denial fails
   the task here, before anything runs.
3. **Prepare** (EXECUTING). `TradingGraph.prepare` loads history through the
   `RecordingProvider`, so even the price history is a policy-checked tool call with DATA
   evidence. The guards apply: at least 30 bars, latest bar within 7 days, finite position.
4. **Tool batch.** Consecutive tool steps run in parallel through the `ToolExecutor`.
   `knowledge.search` passages go into `state.knowledge`; `quant.alpha` into `state.alpha`.
   If a step needs approval and the gateway has no answer, the run pauses in
   AWAITING_APPROVAL with `pending_step` set.
5. **Analysts.** Each analyst runs through the graph with the recording provider, so its
   news, social, fundamentals and macro calls are policy-checked and evidenced. The harness
   records CALCULATION evidence for the analyst's facts and DECISION evidence for the report,
   attributes every record added during the stage to the report's `evidence_ids`, and adds a
   `Finding` unless the analyst abstained.
6. **Debate, trader, risk.** The same, with the facilitator's verdict citing every analyst's
   evidence, the proposal citing the verdict, and the decision citing the proposal, the risk
   facts and every risk view.
7. **Critic** (CRITIQUING). Deterministic checks, then the optional model critique. The
   multiplier is at most 1.
8. **Validate** (VALIDATING_EVIDENCE). Findings whose evidence ids do not resolve are dropped
   and the fact is recorded.
9. **Finalise** (FINALISING → COMPLETED). The report is built and audited, the decision's
   confidence is scaled by the critic's multiplier, and the decision is written to memory.

At any point, `cancel()` sets a flag checked between steps; an exception ends the run in
FAILED with the reason; `IllegalTransition` is raised if code tries to skip a state.

## The decision inside the task

The desk's own logic is unchanged by the harness. In brief (details in the v0.3 sections of
[the evaluation](../evaluation/evaluation.md)):

- **Analysts** produce a signal in [-1, 1] and a confidence, or abstain.
- **Facilitator** computes `Σ wᵢ·confᵢ·signalᵢ / Σ wᵢ·confᵢ` and names the winner above a 0.10
  threshold.
- **Trader** sets `neutral + 2·score` (equities 1.0, FX 0.0 when neutral), ATR-based stop and
  target, and reads retrieved policy passages.
- **Risk team** sizes by volatility targeting (neutral), 1.25× or vol-target (aggressive),
  half and VaR-capped (conservative).
- **Portfolio manager** blends 25/50/25, applies shorting policy, max position, VaR cap and
  minimum trade, then the no-trade band, and rebuilds the protective levels if the direction
  changed.

## Backtesting, research and evaluation

- **Walk-forward** (`run_agent_backtest`): the full graph at each rebalance with the held
  position; stops and per-bar carry in the C++ engine; six baselines including
  volatility-targeted buy & hold.
- **Portfolio** (`run_portfolio_backtest`): one sleeve per symbol; `weighting` in `equal`,
  `inverse_vol`, `risk_parity`, `min_variance`, `mean_variance`, re-estimated from trailing
  returns at each rebalance and applied identically to every strategy.
- **Alphas** (`alpha_report`): IC and t-stat, decay, hit rate, tercile spread, autocorrelation,
  correlations, combination.
- **Execution** (`plan_execution`, `simulate_execution`): decision → parent order → schedule →
  fills with spread and square-root impact → implementation shortfall.
- **Statistics** (`selection_report`): bootstrap Sharpe interval, probabilistic and deflated
  Sharpe, minimum track record.
- **Evaluation** (`evaluate`): design 2016–2021 for choices, holdout 2022–2026 run once,
  Q1 2024 reference window; `RULES_V02` for before/after.

## Design decisions

**Tools are the only path to data.** Agents keep calling a provider interface, but under the
harness that provider is `RecordingProvider`, which turns every call into a catalogued tool
call. One registry serves the executor, the planner's catalogue and the MCP server, so a
capability cannot exist in one place and not the others.

**Evidence is written before interpretation.** The executor records the digest of a tool's
payload before returning it. Findings cite ids; the validator drops what does not resolve;
the reporter audits the narrative. Tampering with a payload after the fact is detectable
because `resolve` re-hashes it.

**Policy is code that names its rule.** Ordered rules with a fail-closed default; roles map
to capabilities; state-changing tools always need approval; the approval identity is the tool
and its arguments within a task. Prompts describe the rules for the model's benefit, but they
are not what enforces them.

**The harness owns the loop.** A transition table, not a flag, decides what states are
reachable. The governance steps are appended to any plan, including hand-built ones. Agents
cannot schedule state changes; only the executor, under policy, can perform them.

**The critic can only lower confidence.** Deterministic checks are the review; a model may
add concerns and a multiplier that is clipped to at most 1.

**Audits accept rounding, not invention.** A number in the narrative must match a fact when
the fact is rounded to the number's displayed precision; counts are facts too, so nothing is
exempt.

**Tools, then rules, then LLM.** Every agent has a rule-based answer; the model's structured
reply replaces it when valid; failures degrade to rules. The rule-based desk is also the
control for measuring what a model adds.

**Point in time or nothing.** Prices are clipped twice; FRED values are lagged and staleness
checked; the static macro table is never used for historical real data; alphas use only past
bars; portfolio covariance uses only trailing returns.

**C++ with a numpy twin, cross-checked.** The numpy mirror keeps the package usable without a
compiler, and CI proves the two agree, including the new rolling extremes, Spearman and
Almgren-Chriss functions.

**Measured, then decided.** New rules, analysts and alphas go through the design period
before they can become defaults; the alpha analyst was measured and left off.

## Configuration surface

See `config.py` for the full dictionary.

| Key | Default | Effect |
|---|---|---|
| `llm_provider`, `deep_think_llm`, `quick_think_llm`, `deep_effort` | `offline`, `claude-opus-5`, `claude-haiku-4-5`, `high` | Model tiers |
| `llm_timeout_s`, `max_llm_calls`, `llm_anonymize` | 300, None, False | Timeout; hard call cap; anonymised prompts |
| `agentic.approval` | `auto` | `auto`, `queued` or `deny` gateway |
| `agentic.llm_planner`, `llm_critic`, `llm_reporter` | False, True, True | Which governance steps may use the model |
| `agentic.use_alpha_tool`, `critic_divergence`, `tool_timeout_s` | True, 0.6, 30 | Canonical plan and executor settings |
| `agentic.symbol_universe`, `deny_tools`, `api_keys` | None, [], dev keys | Policy inputs and API roles |
| `analysts` | asset-class default | Add `"alpha"` for the alpha analyst |
| `risk.neutral_weight`, `rebalance_band`, `max_position`, `max_var_95`, `min_trade_weight` | equity 1.0 / fx 0.0, 0.10, 1.0, 0.02, 0.05 | Strategic weight, band, firm limits |
| `risk.stop_atr_mult`, `take_profit_atr_mult` | 2.0, 3.0 | Protective levels |
| `backtest.use_stops`, `costs.*`, `fx_macro_source`, `max_data_staleness_days` | False, bps and pips, `auto`, 7 | Backtest and data behaviour |

## Extension points

| To add | Do this |
|---|---|
| A tool | A method on `DeskTools` (JSON-safe payload), registered in `build_registry` with `ToolAnnotations` (read-only, risk, required capabilities, evidence type). It is then in-process, over MCP and in the planner's catalogue, under policy |
| A policy rule | A callable `PolicyContext -> PolicyDecision | None`; place it before `allow_rule` in the tuple passed to `PolicyEngine` |
| A critic check | Append a `Check` in `Critic.review`; use severity `error` for anything that must fail the review |
| A knowledge document | A Markdown file in `agentic/knowledge/docs`; headings become chunks |
| An analyst | Subclass `Analyst` (`gather`, `rules`, `untrusted_keys`, `abstain`) and register it in `ANALYSTS` |
| An alpha | A function `AlphaInputs -> ndarray` in `ALPHAS` (and the asset-class lists) |
| A weighting scheme | A function over a covariance in `portfolio.py`, added to `METHODS` and `construct` |
| An execution algorithm | A schedule function in `algo.py` and a branch in `ExecutionPlan.schedule` |
| A data source | Subclass `MarketDataProvider`, pass prices through `clean_ohlcv`, return only data available at `as_of` |
| A rule change | Behind a `config["rules"]` switch; choose on the design period with `evaluate`; judge once on the holdout |
| A quant routine | C++ plus `pycore.py` mirror, bound in `module.cpp`, exported in `quant/__init__.py`, cross-checked in tests |
