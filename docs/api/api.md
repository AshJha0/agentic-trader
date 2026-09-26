# API reference

This reference covers the public Python API (the desk, the agentic layer and the research
layer), the HTTP API, the MCP server, the CLI, the C++ API and the standalone C++ tool.
Anything not listed here is internal and may change.

```python
from agentic_trader import (TradingGraph, run_agent_backtest, run_portfolio_backtest,
                            ComparisonReport, PortfolioReport, evaluate, EvaluationResult,
                            make_config, DEFAULT_CONFIG, RULES_V02, Instrument, Action,
                            FinalDecision, TradingState)
from agentic_trader.agentic import (AgentHarness, Task, Role, TaskState, PolicyEngine,
                                    QueuedApprovalGateway, EvidenceStore, KnowledgeBase, ...)
from agentic_trader import alpha, algo, portfolio, stats, quant
```

## Part 1 — The desk

### `TradingGraph(config=None, provider=None, llm=None, memory=None, on_event=None)`

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `config` | `dict \| None` | `DEFAULT_CONFIG` | Deep-merged over the defaults with `make_config` |
| `provider` | `MarketDataProvider \| None` | From `config["data_provider"]` | Data source |
| `llm` | `LLM \| None` | From `config["llm_provider"]` | Any object with `complete(system, prompt, *, deep) -> str \| None`; `None` means offline. Wrapped in `BudgetedLLM` when `config["max_llm_calls"]` is set |
| `memory` | `DecisionMemory \| None` | `DecisionMemory(config["memory_path"])` | Pass `DecisionMemory(None)` for in-memory only |
| `on_event` | `Callable[[str, str], None] \| None` | Logs at INFO | Called with `(stage, message)` for `data`, `analyst`, `debate`, `trader`, `risk`, `decision` and `report` |

#### `propagate(symbol, as_of, asset_class=None, current_weight=None) -> tuple[TradingState, FinalDecision]`

Runs the whole desk once. `symbol` is a `str` (`"AAPL"`, `"BRK.B"`, `"EURUSD"`, `"EUR/USD"`,
`"USDJPY=X"`) or an `Instrument`; `as_of` a `date` or ISO string (a weekend or holiday uses
the last close); `current_weight` the position held going into the decision.

It raises `ValueError` when the symbol is invalid, fewer than 30 bars are available, the
latest bar is more than `max_data_staleness_days` before `as_of`, `current_weight` is not
finite, or the provider raises it. The decision is recorded to memory and, with
`config["save_reports"]`, `results/<SYM>/<date>/report.md` is written.

#### Stages

`propagate` is composed of stages the harness reuses:

| Stage | Signature | Does |
|---|---|---|
| `prepare` | `(symbol, as_of, asset_class=None, current_weight=None, provider=None) -> TradingState` | Point-in-time history, guards, memory; no agent runs |
| `analyst_names` | `(instrument) -> list[str]` | The configured analysts for the asset class |
| `run_analyst` | `(state, name, provider=None) -> AnalystReport` | One analyst; stores the report in `state.reports` |
| `run_debate` | `(state, rounds=None) -> DebateOutcome` | Bull/bear rounds and the facilitator |
| `run_trader` | `(state) -> TradeProposal` | The proposal |
| `run_risk` | `(state, rounds=None) -> FinalDecision` | Risk team, portfolio manager, limits and band |
| `record` | `(state) -> None` | Memory and the optional report file |

#### `scan(symbols, as_of, positions=None) -> pandas.DataFrame`

One row per symbol: `symbol`, `asset_class`, `last`, `action`, `target_weight`,
`confidence`, `stop_loss`, `take_profit`, `debate`, `score`, `analysts_voting`, `approved`,
`adjustments`, `error`. A failing symbol gets `action == "ERROR"` and the scan continues.

### State documents (`agentic_trader.state`)

| Class | Fields |
|---|---|
| `Action` | `str` enum: `BUY` (hold long), `SELL` (short, or exit when shorting is not allowed), `HOLD` (flat) |
| `AnalystReport` | `analyst`, `signal` ∈ [-1, 1], `confidence` ∈ [0, 1], `summary`, `key_points`, `facts`, `source` (`rules` \| `llm`), `abstained`, `rule_signal` (the rule view when the model overrode it), `evidence_ids` |
| `DebateTurn` | `speaker`, `round`, `argument` |
| `DebateOutcome` | `winner` (`bull` \| `bear` \| `balanced`), `score`, `conviction`, `summary`, `turns`, `source`, `evidence_ids` |
| `TradeProposal` | `action`, `target_weight`, `confidence`, `entry_price`, `stop_loss`, `take_profit`, `horizon_days`, `rationale`, `source`, `evidence_ids` |
| `RiskView` | `stance`, `recommended_weight`, `argument`, `round`, `source`, `evidence_ids` |
| `FinalDecision` | `symbol`, `as_of`, `action`, `target_weight`, `confidence`, `stop_loss`, `take_profit`, `rationale`, `approved`, `adjustments`, `source`, `evidence_ids`; `to_dict()` |
| `TradingState` | `instrument`, `as_of`, `history`, `current_weight`, `reports`, `debate`, `proposal`, `risk_views`, `decision`, `lessons`, `track_record`, `log`, `knowledge` (retrieved passages), `alpha` (alpha snapshot); `last_price`, `reports_digest()`, `to_markdown()` |

### Agents (`agentic_trader.agents`)

Every agent is constructed as `Agent(llm, config)`; `RiskAnalyst` also takes a stance.

| Class | Entry point | Tier |
|---|---|---|
| `TechnicalAnalyst`, `FundamentalsAnalyst`, `MacroAnalyst`, `NewsAnalyst`, `SentimentAnalyst`, `AlphaAnalyst` | `run(state, provider) -> AnalystReport` | quick |
| `BullResearcher`, `BearResearcher` | `speak(state, round, history) -> DebateTurn` | deep |
| `DebateFacilitator` | `judge(state, turns) -> DebateOutcome` | deep |
| `Trader` | `run(state) -> TradeProposal` | deep |
| `RiskAnalyst` | `speak(state, facts, round, history) -> RiskView` | deep |
| `PortfolioManager` | `run(state, facts) -> FinalDecision`; `guardrails(w, facts)`; `no_trade_band(w, current, facts)` | deep |

Helpers: `run_debate(state, bull, bear, facilitator, rounds)`, `run_risk_team(state, analysts,
pm, rounds)`, `researchers.consensus_score(state, weights, skip_abstained=False)`,
`trader.protective_levels(direction, entry, atr, risk)`, `trader.sane_levels(...)`,
`trader.policy_passages(state)`, `base.untrusted_block(label, lines)`, the `ANALYSTS`
registry. To add an analyst, subclass `analysts.Analyst` (`name`, `role`, `instructions`,
`untrusted_keys`, `gather`, `rules`, `abstain`).

### LLM (`agentic_trader.llm`, `agentic_trader.anonymize`)

| Name | Meaning |
|---|---|
| `LLM` | Protocol: `complete(system, prompt, *, deep: bool) -> str \| None` |
| `AnthropicLLM(config)` | Claude through the Anthropic SDK: `quick_think_llm` / `deep_think_llm`, adaptive thinking and `deep_effort`, `llm_timeout_s`, refusal fallback; returns `None` on refusal, rate limit, status or connection errors; records usage |
| `BudgetedLLM(inner, max_calls)` | Passes the first `max_calls` calls through, then returns `None`; `calls`, `exhausted`, `usage` |
| `UsageTracker` | Thread-safe tokens and outcomes per serving model; `calls`, `cost_usd`, `summary()` |
| `get_llm(config)`, `llm_usage(llm)` | Build from config; usage summary or `None` |
| `extract_json(text)` | The first JSON object in a reply, or `None` |
| `Anonymizer` | Replaces symbols, names, dates and price levels in prompts and restores them in replies; on with `llm_anonymize` |

### Data (`agentic_trader.data`)

`MarketDataProvider(config)` contract: `history(instrument, start, end)` (OHLCV through
`clean_ohlcv`), `news` and `social(instrument, as_of, lookback_days)` (published ≤ `as_of`),
`fundamentals(instrument, as_of)`, `macro(instrument, as_of)`, `carry_series(instrument,
dates)`; `real_world` class attribute. Implementations: `SyntheticProvider`, `YahooProvider`,
`CSVProvider`; `get_provider(config)`, `PROVIDERS`; `fred.FredClient` with `RATE_SERIES` and
`CPI_SERIES`; `base.fx_macro`.

### Memory (`agentic_trader.memory`)

`DecisionMemory(path=None)`: `record(...)`, `resolve(symbol, as_of, price) -> int`,
`lessons(symbol, as_of, k=3)`, `track_record(symbol, as_of, k=20)`; `skipped_lines`.

### Backtesting (`agentic_trader.backtest`)

#### `run_agent_backtest(symbol, start, end, config=None, rebalance_every=5, provider=None, llm=None, asset_class=None, on_decision=None, include_agent=True) -> ComparisonReport`

Walk-forward backtest of the desk plus six baselines. `ComparisonReport`: `instrument`,
`dates`, `prices`, `results` (`AgenticTrader`, `Buy&Hold`, `B&H vol-target`, `SMA(20/50)`,
`MACD`, `KDJ+RSI`, `ZMR`), `decisions`, `backtest_config`, `carry`, `table()`,
`equity_curves()`, `returns()`.

#### `run_portfolio_backtest(symbols, start, end, config=None, rebalance_every=5, provider=None, llm=None, on_decision=None, weighting="equal", cov_window=120) -> PortfolioReport`

One sleeve per symbol. `weighting` ∈ `equal`, `inverse_vol`, `risk_parity`, `min_variance`,
`mean_variance`; the covariance is re-estimated from the trailing `cov_window` returns at
each rebalance and the same allocation is applied to every strategy. `PortfolioReport`:
`symbols`, `dates`, `returns`, `metrics`, `sleeves`, `weighting`, `allocations` (per rebalance),
`table()`.

Also: `backtest_config_for(...)`, `baseline_weights(full, allow_short, target_vol=0.15, ...)`.

### Evaluation (`agentic_trader.evaluation`)

#### `evaluate(symbols=None, periods=None, config=None, rebalance_every=5, provider=None, progress=None, llm=None, workers=1) -> EvaluationResult`

`symbols` defaults to `DEFAULT_UNIVERSE` (10 equities, 5 FX pairs); `periods` to `PERIODS`
(`design` 2016-01-04 → 2021-12-31, `holdout` 2022-01-03 → 2026-06-30, `q1_2024` 2024-01-02 →
2024-03-28). `workers > 1` runs backtests in parallel sharing one LLM budget. Failures are
recorded in `meta["errors"]`. `EvaluationResult`: `rows`, `meta` (incl. LLM usage),
`summary(period=None)`, `head_to_head()`, `to_json` / `from_json`.

### Configuration and instruments

`make_config(overrides=None, **kw)` deep-merges over `DEFAULT_CONFIG`; `RULES_V02` reproduces
the v0.2 rules. The important keys are listed in
[architecture/overview.md](../architecture/overview.md#configuration-surface).

`Instrument(symbol, asset_class, base=None, quote=None)`: `is_fx`, `pip_size`,
`periods_per_year`, `yahoo_symbol`, `display`; `Instrument.parse(text, asset_class=None)`
treats six known currency letters, "/" and "=X" as FX intent and validates equity tickers.

## Part 2 — The agentic layer (`agentic_trader.agentic`)

### Domain (`domain.py`)

All frozen dataclasses unless stated.

| Type | Fields / notes |
|---|---|
| `Task(symbol, as_of, role=Role.TRADER, current_weight=None, question="")` | `id` (`TASK-…`), `created_at` |
| `Role` | `viewer`, `analyst`, `trader`, `risk`, `admin` |
| `Capability` | `read_market_data`, `read_knowledge`, `run_analytics`, `run_models`, `propose_trades`, `approve_trades`, `admin`; `ROLE_CAPABILITIES` maps roles to sets |
| `TaskState` | `CREATED`, `PLANNING`, `VALIDATING_PLAN`, `EXECUTING`, `AWAITING_APPROVAL`, `CRITIQUING`, `VALIDATING_EVIDENCE`, `FINALISING`, `COMPLETED`, `FAILED`, `CANCELLED`; `TRANSITIONS` is the legal-move table |
| `StepType` | `TOOL`, `ANALYST`, `DEBATE`, `TRADER`, `RISK`, `CRITIC`, `VALIDATE_EVIDENCE`, `FINALISE` |
| `PlanStep.make(type_, name, arguments=None, depends_on=(), rationale="")` | `id` is a digest of the content |
| `Plan(task_id, steps, source, rationale)` | `source` is `canonical` or `llm` |
| `ToolAnnotations(read_only, risk, required, evidence_type)` | `RiskLevel` ∈ `low`, `medium`, `high` |
| `ToolDescriptor(name, server, description, input_schema, annotations)` | `name` is `server.tool` |
| `ToolRequest(tool, arguments, requested_by, correlation_id)` | `request_id` = digest of tool + arguments (the approval identity) |
| `ToolResult(request, ok, payload, error, started_at, duration_ms, attempts, evidence_id, policy, pending_approval)` | |
| `Evidence.build(type_, source, summary, payload, correlation_id, arguments=None)` | `id` (`EV-…`), `digest` (SHA-256 of canonical JSON); `EvidenceType` ∈ `DATA`, `CALCULATION`, `DOCUMENT`, `MODEL_OUTPUT`, `DECISION`, `APPROVAL`, `ORDER`, `FAILED` |
| `Finding.make(agent, claim, confidence, evidence_ids, tags=())` | |
| `PolicyDecision(outcome, rule, reason)` | `PolicyOutcome` ∈ `allow`, `deny`, `require_approval`; `allowed` |
| `canonical_json(obj)`, `digest(obj)` | Stable serialisation and hash |

### Tools (`tools.py`)

| Name | Meaning |
|---|---|
| `schema_from_signature(fn)` | JSON schema from type hints and defaults |
| `coerce_arguments(schema, arguments)` | Dates, integers, numbers, booleans, strings (≤ 2000 chars), arrays (≤ 1000); rejects extras and bad types with `ValueError` |
| `ToolRegistry()` | `register(server, fn, name=None, annotations=None)`, `@tool(server, read_only=..., risk=..., ...)`, `register_descriptor(descriptor, fn)`, `get(name)`, `descriptors(server=None)`, `servers`, `catalogue()`, `len()` |
| `ExecutorConfig(timeout_s=30, max_attempts=2, retry_backoff_s=0.2)` | |
| `ToolExecutor(registry, policy, gateway, evidence, role, config=None, tracer=None)` | `call(name, correlation_id=None, requested_by="harness", **arguments) -> ToolResult`; `evidence_for(result)` |

Execution order in `call`: policy → gateway (when `require_approval`) → coercion → timed run
with retry → evidence record (`FAILED` on error) → metrics and span.

### Desk tools (`servers.py`)

`DeskTools(provider, config, knowledge=None, positions=None, capital=None)` and
`build_registry(tools)` give 15 tools on five servers:

| Tool | Arguments | Evidence | Notes |
|---|---|---|---|
| `market_data.history` | `symbol, as_of, lookback_days=400` | DATA | OHLCV up to the close |
| `market_data.news`, `market_data.social` | `symbol, as_of, lookback_days=7` | DATA | Published ≤ `as_of` |
| `market_data.fundamentals`, `market_data.macro` | `symbol, as_of` | DATA | Point in time |
| `quant.technical` | `symbol, as_of, lookback_days=400` | CALCULATION | Indicator snapshot |
| `quant.risk` | `symbol, as_of, proposed_weight=0, lookback_days=400` | CALCULATION | Vol, VaR, CVaR, drawdown, ATR, limits |
| `quant.alpha` | `symbol, as_of, horizon=10, lookback_days=900` | CALCULATION | Snapshot, IC table, best three (needs 300 bars) |
| `quant.baselines` | `symbol, start, end` | CALCULATION | Six baselines' CR, Sharpe, MDD |
| `knowledge.search` | `query, k=3` | DOCUMENT | `k` in 1–10 |
| `knowledge.list_documents` | — | DOCUMENT | |
| `portfolio.position` | `symbol` | DATA | Weight and capital |
| `portfolio.construct` | `symbols, targets, as_of, method="risk_parity", lookback_days=400` | CALCULATION | Trailing covariance |
| `execution.plan` | `symbol, as_of, target_weight, current_weight=0, algo=None` | CALCULATION | Simulated; no order |
| `execution.submit_order` | `symbol, side, quantity, note=""` | ORDER | High risk, not read-only: always needs approval; writes a ticket only |

`RecordingProvider(executor, inner, correlation_id)` is a `MarketDataProvider` whose calls go
through the executor; `frame_from_payload(payload)` rebuilds a frame from a history payload.

### Policy (`policy.py`)

| Name | Meaning |
|---|---|
| `PolicyContext(request, tool, role, capabilities, config)` | What a rule sees |
| `DEFAULT_RULES` | `deny_list_rule`, `capability_rule`, `read_only_rule`, `argument_guard_rule`, `risk_level_rule`, `allow_rule`, in that order; a rule returns a `PolicyDecision` or `None` to pass |
| `PolicyEngine(config=None, rules=DEFAULT_RULES, role_capabilities=None)` | `evaluate(request, tool, role) -> PolicyDecision`; fails closed with rule `no_rule`; `decisions` log. Config keys: `symbol_universe`, `deny_tools`, `max_position` |
| `ApprovalGateway.decide(task_id, request, reason) -> bool \| None` | `AutoApprovalGateway` (True), `DenyApprovalGateway` (False), `QueuedApprovalGateway` (None until resolved; `pending(task_id=None)`, `all()`, `resolve(approval_id, approve, decided_by, note)`) |
| `ApprovalRequest` | `id`, `task_id`, `request`, `reason`, `created_at`, `decided`, `approved`, `decided_by`, `note` |

### Evidence (`evidence.py`)

`EvidenceStore()`: `add`, `record(type_, source, summary, payload, correlation_id,
arguments=None)`, `get`, `resolve(ev_id)` (re-hashes the payload), `unresolved(ids)`,
`by_type`, `by_source`, `ids_since(n)`, `summary_rows()`, `len()`. Thread-safe.

### Planning (`planner.py`)

| Name | Meaning |
|---|---|
| `canonical_plan(task, instrument, analysts, config, catalogue)` | Knowledge search, alpha (when `use_alpha_tool`), analysts, debate, trader, risk, then the governance steps |
| `governance_steps()` | `critic`, `validate_evidence`, `finalise` |
| `propose_plan(llm, task, instrument, analysts, catalogue)` | Model-proposed raw steps, or `None` |
| `validate_plan(raw_steps, task, instrument, analysts, catalogue)` | Drops unknown tools and analysts, pins `symbol` and `as_of`, coerces arguments, de-duplicates, appends governance |
| `make_plan(task, instrument, analysts, config, catalogue, llm=None)` | LLM plan when `agentic.llm_planner`, else canonical; always validated |
| `plan_to_dict(plan)` | JSON |

### Harness (`harness.py`)

#### `AgentHarness(graph, policy=None, gateway=None, knowledge=None, positions=None, capital=None)`

| Method | Meaning |
|---|---|
| `run(task) -> TaskRun` | `submit` then `resume` |
| `submit(task) -> TaskRun` | Register a run in `CREATED` |
| `resume(run) -> TaskRun` | Drive to a terminal state or `AWAITING_APPROVAL` |
| `cancel(task_id) -> TaskRun` | Sets the flag; a waiting run is cancelled immediately |
| `pending_approvals(task_id=None)` | Queued gateway only |
| `decide_approval(approval_id, approve, decided_by="human", note="") -> TaskRun` | Records APPROVAL evidence and resumes |
| `runs`, `registry`, `policy`, `gateway`, `tools`, `critic` | State and collaborators |

`TaskRun`: `task`, `state`, `plan`, `trading_state`, `findings`, `critic`, `report`,
`evidence`, `tracer`, `history` (state, time and note), `completed_steps`, `step_results`,
`errors`, `pending_step`, `cancel_requested`, `started_at`, `finished_at`, `correlation_id`;
`id`, `done`, `decision`, `to_dict(include_report=True)`. `IllegalTransition` is raised for a
move not in `TRANSITIONS`. `wait_until_done(run, timeout_s=60)` blocks on a run driven by
another thread.

### Critic (`critic.py`)

`Critic(config, llm=None).review(state, findings, evidence, risk_facts=None) ->
CriticReport`. Checks: `evidence_resolves` (error), `model_rule_divergence`,
`analyst_contradiction`, `firm_limits` (error), `protective_levels` (error),
`direction_vs_verdict`, `single_evidence_cap`. `CriticReport`: `checks` (`Check(name, passed,
detail, severity)`), `multiplier` ≤ 1, `llm_concerns`, `llm_multiplier`, `passed`, `failed`,
`to_dict()`.

### Reports (`reporter.py`)

| Name | Meaning |
|---|---|
| `collect_facts(state, critic) -> dict[str, float]` | Every number the narrative may use, counts included |
| `number_audit(narrative, facts, rel_tol=1e-6) -> list[str]` | Numbers that match no fact at the displayed precision (percent-aware) |
| `evidence_audit(narrative, findings, evidence) -> list[str]` | `EV-` ids that do not exist |
| `template_narrative(...)`, `llm_narrative(llm, ...)` | Deterministic or model summary |
| `build_report(task, state, findings, critic, evidence, llm=None) -> Report` | Audits run either way |
| `Report` | `task_id`, `symbol`, `as_of`, `facts`, `sections`, `narrative`, `warnings`, `narrative_source`; `to_dict()`, `to_markdown()` |

### Knowledge (`rag.py`)

`KnowledgeBase.from_dir(path=DOCS_DIR)`, `from_texts({id: text})`, `search(query, k=3,
min_score=0.05) -> list[Passage]`, `get(chunk_id)`, `documents`; `Passage`: `chunk_id`,
`doc_id`, `title`, `text`, `score`, `to_dict()`. `default_knowledge_base()` is cached.
The embedder is a hashed TF-IDF (`HashedTfidf`), so no network or model is needed.

### Tracing (`tracing.py`)

`Tracer().span(name, **attrs)` context manager with `Span.set`, `fail`, `duration_ms`;
`to_list()`, `summary()`; `Tracer.metrics` is a `Metrics` with `inc`, `observe`, `counter`,
`render()` (Prometheus text). `configure_json_logging(level)` switches the root logger to
JSON lines.

### MCP (`mcp_server.py`; needs `pip install "agentic-trader[mcp]"`)

| Name | Meaning |
|---|---|
| `build_mcp_server(registry, name="agentic-trader")` | An `MCPServer` with one tool per descriptor, named `server__tool`, annotated read-only/destructive with risk, required capabilities and evidence type in `meta` |
| `python -m agentic_trader.agentic.mcp_server [--data synthetic\|yahoo\|csv] [--csv-dir DIR]` | Serve over stdio (also `agentic-trader mcp`) |
| `discover(server_args=None)` | The remote tools' names, descriptions, schemas and annotations |
| `call(name, arguments, server_args=None)` | One remote call; raises `RuntimeError` on a tool error |
| `registry_from_stdio(server_args=None) -> ToolRegistry` | Remote tools as local descriptors, so policy, coercion and evidence apply unchanged |

### HTTP API (`api.py`; needs `pip install "agentic-trader[api]"`)

`create_app(harness=None, graph=None, config=None, api_keys=None)` returns a FastAPI app;
`serve(host, port, config)` runs it with uvicorn (`agentic-trader serve`). Every route except
`/health` and `/metrics` needs an `X-API-Key` header mapped to a role
(`config["agentic"]["api_keys"]`, development values by default).

| Method and path | Capability | Returns |
|---|---|---|
| `GET /health` | — | `{status, tasks, tools}` |
| `GET /metrics` | — | Prometheus text for every task |
| `GET /tools` | any key | The catalogue |
| `POST /tasks` `{symbol, as_of, current_weight?, question?}` | `run_analytics` | `202 {task_id, state}`; the task runs in a thread |
| `GET /tasks/{id}` | any key | `TaskRun.to_dict()` without the report |
| `GET /tasks/{id}/report?format=json\|markdown` | any key | The report, or `409` before it exists |
| `GET /tasks/{id}/trace`, `/evidence` | any key | Spans and summary; evidence rows |
| `POST /tasks/{id}/cancel` | `run_analytics` | `{task_id, state}` |
| `GET /approvals` | `approve_trades` | Pending approvals |
| `POST /approvals/{id}` `{approve, note?}` | `approve_trades` | `{approval_id, approved, task_id, state}`; `404` unknown, `409` already decided |

Errors: `401` missing or unknown key, `403` role lacks the capability, `404` unknown task,
`422` invalid body.

## Part 3 — Quant research

### Alphas (`agentic_trader.alpha`)

| Name | Meaning |
|---|---|
| `ALPHAS` | `tsmom_12_1`, `mom_20_vol`, `reversal_5`, `high_52w`, `donchian_20`, `macd_norm`, `rsi_contrarian`, `low_vol`, `carry` (FX); `EQUITY_ALPHAS`, `FX_ALPHAS` |
| `AlphaInputs.from_frame(df, instrument, carry=None)` | Arrays a signal reads |
| `compute_alphas(df, instrument, names=None, carry_series=None) -> DataFrame` | One column per alpha in [-1, 1] or NaN |
| `combine(signals, weights=None) -> Series` | Weighted mean ignoring NaN |
| `forward_returns(close, horizon)`, `information_coefficient(signal, fwd) -> (ic, t, n)` | Spearman IC |
| `alpha_report(df, instrument, horizon=10, names=None, carry_series=None, decay_horizons=(1,5,10,21,42), weights=None) -> AlphaReport` | `table` (IC, t(IC), n, hit%, tercile spread%, autocorr, coverage%), `decay`, `correlations`, `signals`, `best(k)` |
| `alpha_snapshot(df, instrument, carry_series=None, weights=None) -> dict` | Latest values plus `combined` |

### Execution (`agentic_trader.algo`)

| Name | Meaning |
|---|---|
| `volume_profile(kind, n)`, `synthetic_intraday_bars(day, n, kind="equity", seed=0)` | U-shaped (equity) or session-weighted (FX) profile; Brownian-bridge bars consistent with the daily bar, with `VWAP` |
| `twap_schedule(total, n)`, `vwap_schedule(total, profile)`, `pov_schedule(total, volumes, participation, cap=0.2)`, `almgren_chriss_schedule(total, n, sigma_session, eta, risk_aversion)` | Slice quantities |
| `simulate_execution(schedule, bars, side, algo="custom", spread_bps=2, impact_coeff=1, daily_vol=0.02, adv=None) -> ExecutionReport` | Fills at bar VWAP plus half-spread and square-root impact; `is_bps`, `vs_vwap_bps`, `spread_cost_bps`, `impact_cost_bps`, `max_participation`, `completion`, `fills`; `to_dict()` |
| `plan_execution(decision, instrument, current_weight, capital, last_price, adv=None, algo=None, slices=None, max_adv_participation=0.1) -> ExecutionPlan \| None` | FX → TWAP; equity → VWAP, or POV above the ADV threshold; `None` when nothing to trade |
| `ExecutionPlan.schedule(bars, participation=0.1, sigma_session=None, eta=None, risk_aversion=1e-6)` | The chosen algorithm's schedule |

### Portfolio construction (`agentic_trader.portfolio`)

| Name | Meaning |
|---|---|
| `sample_cov`, `ewma_cov(returns, halflife=60)`, `ledoit_wolf_shrink(returns, cov=None) -> (cov, delta)`, `estimate_cov(returns, halflife=60, shrink=True)` | Annualisation is the caller's; `construct` handles it |
| `equal_weights(n)`, `inverse_vol_weights(cov)`, `risk_parity_weights(cov, budget=None)`, `min_variance_weights(cov, cap=1)`, `mean_variance_weights(mu, cov, risk_aversion=5, cap=1)` | Long-only allocations summing to 1 |
| `risk_contributions(w, cov)` | `vol`, `marginal`, `component`, `pct` |
| `construct(targets, returns, method="risk_parity", *, periods_per_year=252, halflife=60, shrink=True, max_weight=0.5, gross_cap=1, target_vol=0.15, risk_aversion=5, expected_returns=None) -> PortfolioWeights` | `symbols`, `allocation`, `weights` (signed), `method`, `expected_vol`, `contributions`, `diversification_ratio`, `correlations`, `scale`; `to_dict()` |
| `METHODS` | The five method names |

### Statistics (`agentic_trader.stats`)

| Name | Meaning |
|---|---|
| `sharpe_stats(returns, periods_per_year=252) -> SharpeStats` | `n`, `mean`, `std`, `skew`, `kurt`, `sharpe` (per period), `sharpe_annual`, `t_stat` |
| `sharpe_ci_bootstrap(returns, periods_per_year=252, n_boot=2000, block=10, ci=0.95, seed=0)` | Circular block bootstrap interval of the annual Sharpe |
| `probabilistic_sharpe(sr, n, skew=0, kurt=3, sr_benchmark=0)` | P(true Sharpe > benchmark); per-period inputs |
| `expected_max_sharpe(n_trials, var_trials_sr)` | The DSR benchmark |
| `deflated_sharpe(sr, n, n_trials, var_trials_sr, skew=0, kurt=3)` | PSR against the expected maximum |
| `min_track_record(sr, sr_benchmark=0, skew=0, kurt=3, confidence=0.95)` | Periods needed; `inf` when not above the benchmark |
| `selection_report(chosen_returns, trial_sharpes_annual, periods_per_year=252) -> dict` | All of the above for a chosen variant |

### Quant core (`agentic_trader.quant`)

`quant.BACKEND` is `"cpp"` or `"python"`; `AGENTIC_TRADER_BACKEND=python` forces numpy.

| Function | Returns |
|---|---|
| `sma`, `ema`, `rolling_std`, `zscore`, `rolling_max`, `rolling_min` `(x, n)` | array; `sma` resets on NaN |
| `rsi(close, n=14)`, `macd(close, 12, 26, 9)`, `bollinger(close, 20, 2.0)`, `atr(high, low, close, 14)`, `kdj(high, low, close, 9)`, `pct_change(x)`, `realized_vol(close, n, ppy)` | arrays / tuples |
| `spearman(x, y)` | float (NaN when a side is constant) |
| `almgren_chriss(total, n, kappa)` | slice quantities |
| `quantile`, `historical_var`, `historical_cvar`, `kelly_fraction`, `vol_target_weight`, `position_units`, `max_drawdown` | floats |
| `strat_buy_hold`, `strat_sma_cross`, `strat_macd`, `strat_kdj_rsi`, `strat_zmr` | weights |
| `run_backtest(prices, target_weights, config=None, *, carry, open, high, low, stop, take, rebalance)` | `BacktestResult` (`equity`, `returns`, `positions`, `trades`, `metrics`, `stop_exits`) |
| `compute_metrics(equity, positions, ppy, rf=0)` | `Metrics` (incl. `sharpe_tstat`, `avg_exposure`) |

`BacktestConfig`: `initial_capital`=100000, `cost_bps`=1, `slippage_bps`=0,
`periods_per_year`=252, `carry_annual`=0, `borrow_annual`=0, `max_leverage`=1,
`allow_short`=True, `risk_free_annual`=0. Prices must be positive and finite.

## Part 4 — CLI

```text
agentic-trader analyze   SYMBOL [--date D] [--position W] [--save] [--json] [--no-memory] [common]
agentic-trader task      SYMBOL [--date D] [--position W] [--role R] [--approval auto|queued|deny]
                                [--llm-planner] [--question TEXT] [--save] [--json] [--no-memory] [common]
agentic-trader scan      SYM1,SYM2,... [--date D] [--positions JSON] [--out file.csv|.json] [common]
agentic-trader backtest  SYMBOL --start D --end D [--every N] [--stops on|off] [--out curves.csv] [common]
agentic-trader baselines SYMBOL --start D --end D [--out curves.csv] [common]
agentic-trader portfolio SYM1,SYM2,... --start D --end D [--every N] [--stops on|off]
                                [--weighting equal|inverse_vol|risk_parity|min_variance|mean_variance] [--out returns.csv] [common]
agentic-trader evaluate  [SYM1,...] [--periods design,holdout,q1_2024] [--every N] [--workers N] [--out results.json] [common]
agentic-trader alpha     SYMBOL --start D --end D [--horizon N] [--out signals.csv] [common]
agentic-trader execute   SYMBOL --target W [--current W] [--date D] [--capital X] [--algo twap|vwap|pov|ac]
                                [--participation P] [--spread-bps X] [--impact X] [--seed N] [common]
agentic-trader stats     returns.csv [--column NAME] [--ppy N] [--trials N] [--trial-sharpes a,b,c]
agentic-trader tools     [--json] [common]
agentic-trader serve     [--host H] [--port P] [--approval auto|queued|deny] [common]
agentic-trader mcp       [common]
agentic-trader info

common: [--asset-class equity|fx] [--data synthetic|yahoo|csv] [--csv-dir DIR]
        [--llm offline|anthropic] [--deep-model ID] [--quick-model ID] [--deep-effort LEVEL]
        [--rounds N] [--analysts a,b,c] [--allow-short] [--band X] [--max-llm-calls N]
        [--rules default|v02] [--anonymize] [-v]
```

Exit status is 0 on success; invalid input gives 2 and a one-line `error:` message; `scan`
returns 1 when every symbol failed. `python -m agentic_trader` is equivalent.

## Part 5 — C++ API (`cpp/include/at/*.hpp`, namespace `at`)

`Series` is `std::vector<double>`.

| Header | Declarations |
|---|---|
| `indicators.hpp` | `sma`, `ema`, `rolling_std`, `zscore`, `rsi`, `macd → MACD{line, signal, hist}`, `bollinger → Bollinger{mid, upper, lower, percent_b}`, `atr`, `kdj → KDJ{k, d, j}`, `pct_change`, `realized_vol`, `rolling_max`, `rolling_min`, `spearman(x, y)`, `almgren_chriss(total, n, kappa)` |
| `risk.hpp` | `quantile`, `historical_var`, `historical_cvar`, `kelly_fraction`, `vol_target_weight`, `position_units` |
| `strategies.hpp` | `strat_buy_hold`, `strat_sma_cross`, `strat_macd`, `strat_kdj_rsi`, `strat_zmr` |
| `backtest.hpp` | `BacktestConfig`, `BacktestInputs{carry, open, high, low, stop, take, rebalance}`, `Trade`, `Metrics`, `BacktestResult`, `run_backtest`, `run_backtest_ex`, `compute_metrics`, `max_drawdown` |

Invalid inputs throw `std::invalid_argument`. Link against the `at_core` static library from
`CMakeLists.txt`; `ctest` runs 13 test groups.

### `at_backtest` (C++ CLI)

```text
at_backtest <prices.csv> [--fx] [--short] [--cost-bps X] [--carry X] [--ppy N]
```

The CSV needs a header with `Close` (or `Adj Close`); `High` and `Low` are optional; at
least 60 rows. It prints CR, AR, Sharpe, MDD, win rate and trades for the five rule-based
baselines. `--fx` enables shorts and 260 periods per year.
