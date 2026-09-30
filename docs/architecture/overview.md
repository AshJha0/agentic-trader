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
| `agents/analysts.py` | Technical, Fundamentals, Macro (FX), News, Sentiment, Alpha and (v0.6) cross-sectional XAlpha analysts; `untrusted_keys`; abstention |
| `agents/researchers.py` | Bull, bear, facilitator, weighted consensus |
| `agents/trader.py` | Strategic weight plus tilt, ATR stops and targets, `sane_levels`, policy passages in the prompt |
| `agents/risk.py` | Three risk analysts, portfolio manager, firm limits, no-trade band |
| `llm.py`, `anonymize.py` | Claude client with tiers, timeout, refusal fallback, usage and cost; call and dollar budgets (`BudgetedLLM`); anonymised prompts |
| `data/` | `MarketDataProvider` (with `reconfigured(config)`: the same downloaded bars under other settings, and `risk_free_series` for the cash leg), `clean_ohlcv`, synthetic / Yahoo / CSV providers, `fred.py` point-in-time macro (one FX rate resolver, no static fallback on real data; the DTB3 cash rate) with optional ALFRED vintages for revised series, `edgar.py` (v0.6) point-in-time fundamentals and filing-stream news from SEC EDGAR (facts as known at `as_of`; since v0.8 each trailing window is reconstructed from one XBRL tag and one reporting basis, with recency and share-class guards) |
| `prompts.py`, `calibration.py`, `provenance.py` | v0.6: content hashes of every prompt the desk can send (recorded in every evaluation); the dispersion / anchoring / drift harness for the desk's judgement on one frozen state; v0.8: package version, git commit, backend and dependency versions written into every result and `*.provenance.json` sidecar |
| `memory.py` | Append-only, corruption-tolerant decision log (entries are provider- and price-basis-scoped; pre-v0.8 entries are never valued and only expire); horizon-gated outcomes |

### The agentic layer (`agentic_trader.agentic`)

| Module | Responsibility |
|---|---|
| `domain.py` | Frozen dataclasses: `Task`, `Plan`, `PlanStep`, `StepType`, `ToolDescriptor`, `ToolAnnotations`, `ToolRequest`/`ToolResult`, `Evidence`, `EvidenceType`, `Finding`, `PolicyDecision`, `Role`, `Capability`, `TaskState` and the legal `TRANSITIONS` |
| `tools.py` | `ToolRegistry` (schemas derived from signatures, `register_descriptor` for remote tools), `coerce_arguments`, `ToolExecutor` (policy → gateway → coerce → timed run with retry → evidence, traced) |
| `servers.py` | `DeskTools` and `build_registry`: 16 tools on `market_data`, `quant` (incl. `xalpha`), `knowledge`, `portfolio`, `execution`; `RecordingProvider` |
| `store.py` | `TaskStore`: SQLite records of every run, written at each transition; archived records served read-only after a restart; in-flight ones carry an owner (`agentic.instance_id`) and a heartbeat and are failed only once their lease (`agentic.lease_s`) has expired, never a live sibling's |
| `policy.py` | Rules, `PolicyEngine`, `ROLE_CAPABILITIES`, `AutoApprovalGateway`, `QueuedApprovalGateway`, `DenyApprovalGateway` |
| `planner.py` | `canonical_plan`, `propose_plan` (model), `validate_plan`, `make_plan` |
| `harness.py` | `AgentHarness`, `TaskRun`: the state machine, tool batching, approvals, cancellation, governance steps |
| `critic.py` | `Critic`: seven deterministic checks and an optional model critique that only lowers confidence |
| `reporter.py` | `collect_facts`, template or model narrative, `number_audit`, `evidence_audit`, `Report` (JSON and markdown) |
| `rag.py`, `knowledge/docs` | `KnowledgeBase` with a hashed TF-IDF embedder over 11 documents |
| `tracing.py` | `Tracer` spans, `Metrics` (Prometheus text), JSON-lines logging |
| `mcp_server.py` | The registry as an MCP stdio server; `discover`, `call`, `registry_from_stdio` |
| `api.py` | FastAPI gateway with API-key roles; `serve_options` (TLS, no development keys off loopback); archive fallback on the read routes; (v0.6) a bounded task pool with a queue limit (`503` when full) and multi-process serving over a shared task store |

### The quant research layer

| Module | Responsibility |
|---|---|
| `alpha.py` | Nine alphas, `compute_alphas`, `combine`, `alpha_report` (IC, decay, hit rate, spread, autocorrelation, correlations), `alpha_snapshot`, `significant_alpha_signal` |
| `xalpha.py` | Cross-sectional alphas: per-day z-scores / ranks within asset class, per-date IC with an overlap-aware t-statistic, quantile spreads, breadth; `xalpha_report`, `xalpha_snapshot` |
| `algo.py` | Volume profiles, intraday bars, TWAP / VWAP / POV / Almgren-Chriss schedules, `simulate_execution`, `plan_execution` |
| `portfolio.py` | EWMA and Ledoit-Wolf covariance, five weighting schemes, hierarchical risk budgets across groups, `risk_contributions`, `construct` |
| `stats.py` | `sharpe_stats`, `sharpe_ci_bootstrap`, `probabilistic_sharpe`, `expected_max_sharpe`, `deflated_sharpe`, `min_track_record`, `selection_report`, (v0.6) `paired_bootstrap` across instruments — since v0.8 a two-stage cluster bootstrap over asset-class-by-universe groups when there are at least five (`scheme=clusters`), the plain instrument bootstrap otherwise (`scheme=instruments`); `benjamini_hochberg` on the unrounded p; `paired_sharpe_block_bootstrap` for the Sharpe difference between two daily series; `rolling_var_forecast` and `var_backtest` (Kupiec, Christoffersen) |
| `backtest.py` | Walk-forward agent backtest vs nine baselines (buy & hold, vol-targeted buy & hold, SMA, MACD, KDJ+RSI, ZMR, `TSMOM(12-1)`, `TSMOM(L/S)`, `Carry`): constant units between decisions with post-cost sizing, a cash leg (idle capital earns the point-in-time bill; Sharpe on excess returns), optional equity-scaled square-root market impact (`impact_coefficients`); `run_portfolio_backtest(weighting=..., class_budgets=...)` with each sleeve's impact at its own capital share and `PortfolioReport.sharpe_difference` (block bootstrap over days) |
| `evaluation.py` | Design / holdout / Q1-2024 / reserve harness over the core and extended universes, with parallel workers, LLM usage accounting, (v0.6) repeated runs, cross-instrument paired bootstraps and the prompt hashes in `meta`; (v0.8) `TRIALS`, the registry of every variant judged on the design period (26; 24 reproducible on the current engine), and `provenance` in every result |
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
- **Trader** sets `neutral + 2·score` (equities 1.0; FX the capped point-in-time carry weight
  `clip(rate_diff% / 2, ±0.5)` since v0.5.1), ATR-based stop and
  target, and reads retrieved policy passages.
- **Risk team** sizes by volatility targeting (neutral), 1.25× or vol-target (aggressive),
  half and VaR-capped (conservative).
- **Portfolio manager** blends 25/50/25, applies shorting policy, max position, VaR cap and
  minimum trade, then the no-trade band, and rebuilds the protective levels if the direction
  changed.

## Backtesting, research and evaluation

- **Walk-forward** (`run_agent_backtest`): the full graph at each rebalance with the held
  (drifted, or flat after a stop) position; constant units between decisions, stops (a gap
  through the take-profit fills at the open), per-bar carry and the cash leg in the C++
  engine; nine baselines including volatility-targeted buy & hold, the fair control, and the
  trend and carry streams (`TSMOM(12-1)`, `TSMOM(L/S)`, `Carry`) at the vol-target size.
  `TSMOM(L/S)` runs long and short whatever the desk's mandate: it is a reference stream.
- **Portfolio** (`run_portfolio_backtest`): one sleeve per symbol; `weighting` in `equal`,
  `inverse_vol`, `risk_parity`, `min_variance`, `mean_variance`, re-estimated from trailing
  returns at each rebalance and applied identically to every strategy.
- **Alphas** (`alpha_report`): IC and t-stat, decay, hit rate, tercile spread, autocorrelation,
  correlations, combination.
- **Execution** (`plan_execution`, `simulate_execution`): decision → parent order → schedule →
  fills with spread and square-root impact → implementation shortfall.
- **Statistics** (`selection_report`): bootstrap Sharpe interval, probabilistic and deflated
  Sharpe, minimum track record.
- **Evaluation** (`evaluate`): design 2016–2021 for choices, holdout 2022–2026, Q1 2024
  reference window, reserve 2026-07 → 2026-09; `RULES_V02` / `RULES_V03` for before/after.
  `scripts/measure_v08.py` runs every published table into `results/v08/` and
  `scripts/render_v08_tables.py` renders them; the reserve and the extended universe were
  consulted for the v0.5.1 and v0.6 decisions and v0.8 re-measured every period, so no
  held-out data remains.
- **Research rounds after v0.8** (`scripts/`): `attribution_v09.py` regresses the desk on its
  control; `measure_v09.py` runs the multi-asset and FX universes under risk parity on
  `design`, `design_long` (2008-07-01 → 2021-12-31) or, once, the holdout; `combine_v09.py`
  builds books from the costed streams with risk parity across streams; `overlay_v09.py`
  sizes the desk's tilt over the vol-target core; `render_v09_doc.py`, `render_v11_doc.py`
  and `render_v12_doc.py` write the evaluation pages from the result files, so no published
  number is typed. Every variant is a `Trial` in `evaluation.TRIALS`.
- **Forward record** (`scripts/paper_trade_v09.py`): a daily job recomputes every stream from
  the freeze date and appends the new day to an append-only ledger; recomputed values that
  differ from what was written go to `revisions.csv`, and the ledger never shrinks.

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
checked; the static macro table is never used for historical real data; the cash leg is the
bill rate as published (one-day lag); EDGAR facts are as known at `as_of`; alphas use only
past bars; portfolio covariance uses only trailing returns.

**C++ with a numpy twin, cross-checked.** The numpy mirror keeps the package usable without a
compiler, and CI proves the two agree, including the new rolling extremes, Spearman and
Almgren-Chriss functions.

**Measured, then decided.** New rules, analysts and alphas go through the design period
before they can become defaults; the alpha analyst was measured and left off.

## Configuration surface

See `config.py` for the full dictionary.

| Key | Default | Effect |
|---|---|---|
| `llm_provider`, `deep_think_llm`, `quick_think_llm`, `deep_effort`, `quick_effort`, `max_tokens` | `offline`, `claude-opus-5`, `claude-haiku-4-5`, `high`, `low`, 16000 | Model tiers, effort and reply size |
| `llm_timeout_s`, `max_llm_calls`, `max_llm_cost_usd`, `llm_anonymize` | 300, None, None, False | Timeout; hard call cap; spend cap (list prices); anonymised prompts |
| `llm_max_retries`, `llm_retry_backoff_s` | 2, 0.5 | Attempts after the first for a timed-out, rate-limited, 5xx or dropped request (the client runs the loop itself; a timed-out attempt is billed at its maximum); first-retry delay, doubling to 8 s with jitter, unless a `retry-after` header (up to 60 s) is honoured instead |
| `llm_budget_mode`, `llm_reserve_output_tokens` | `hard`, 2000 | How `max_llm_cost_usd` is enforced: `hard` reserves each call's maximum cost (input estimate + `max_tokens`) before dispatch so parallel workers cannot overshoot; `estimate` reserves input + `llm_reserve_output_tokens` and is a soft cap |
| `analysts`, `xalpha_universe` | None (asset-class default), None (the core universe of the asset class) | Add `"alpha"` for the alpha analyst or `"xalpha"` for the cross-sectional one; the peer universe it ranks against |
| `rules.tsmom`, `trend_filtered_reversal`, `abstain_without_data` | False, False, False | Rule switches measured on the design period and left off |
| `rules.fx_carry_neutral`, `risk.fx_carry_neutral_scale`, `fx_carry_neutral_cap` | True, 2.0, 0.5 | FX strategic weight = clip(carry% / scale, ±cap) from the point-in-time rate differential (v0.5.1); `RULES_V03` turns it off |
| `rules.track_record_cut` | True | The trader's 0.75× size cut when memory's hit rate over the last ≥ 5 resolved calls is below 40%; on in every published backtest; measured on/off in v0.8 (`results/v08/eval_no_trackrecord_cut.json`) and kept |
| `data_provider`, `csv_dir`, `lookback_days`, `alpha_lookback_days`, `max_data_staleness_days`, `news_lookback_days`, `synthetic_seed` | `synthetic`, `data`, 400, 900, 7, 7, 7 | Data source and windows; refuse to decide on a bar older than the staleness limit |
| `risk.neutral_weight`, `rebalance_band`, `max_position`, `max_var_95`, `min_trade_weight`, `target_vol` | equity 1.0 / fx 0.0 (overridden by the carry rule above), 0.10, 1.0, 0.02, 0.05, 0.15 | Strategic weight, band, firm limits, the neutral risk analyst's vol target |
| `risk.max_book_var_95` | None (off) | Book-level (cross-sleeve) 95% historical VaR cap; scales a proposed weight down by grid search over the book's other positions (`portfolio.book_var_scale`); off in every published run |
| `risk.allow_short_equity`, `allow_short_fx`, `stop_atr_mult`, `take_profit_atr_mult` | False, True, 2.0, 3.0 | Shorting policy per asset class; protective levels |
| `costs.equity_cost_bps`, `equity_slippage_bps`, `equity_borrow_annual`, `fx_spread_pips`, `fx_slippage_bps` | 1.0, 1.0, 0.01, 0.8, 0.2 | Multiplicative per-trade costs; borrow on equity shorts |
| `costs.impact_coeff`, `costs.fx_adv_notional` | 0.0, None | Equity-scaled square-root market impact in backtests (0 = off; 1.0 the textbook value); a notional ADV per FX pair to apply it to FX sleeves |
| `costs.execution_algo`, `costs.ac_kappa` | None (VWAP-equivalent), 3.0 | How the day's trade is worked, for `impact_coeff`'s cost: `twap` or `ac` scale it by that schedule's cost relative to VWAP (`algo.algo_cost_ratio`); the dimensionless Almgren-Chriss urgency (0 = TWAP) |
| `initial_capital`, `account_currency` | 100000.0, `USD` | The account size trade sizes scale with and the currency it, order notionals and tickets are denominated in |
| `cash_leg`, `risk_free_annual` | `auto`, 0.0 | What idle cash earns and what Sharpe is measured against: `auto` = FRED DTB3 (one-day lag) on real-world providers and `risk_free_annual` on synthetic / CSV data; `fred`, `static`, `off` (credits nothing) |
| `backtest.use_stops` | False | Enforce the decision's stop-loss / take-profit intraday |
| `execution.fx_lot_size`, `execution.max_order_notional`, `execution.allow_external_plans` | 1000.0, None (= `initial_capital * risk.max_position`), False | FX orders round down to whole lots of the base currency; the cap on one ticket's notional, enforced by policy before approval and again at execution; whether `execution.submit_order` accepts a ticket whose plan this desk did not produce |
| `fx_macro_source` | `auto` | Synthetic data uses the static table; real data uses point-in-time FRED rates only (a date with no rate has no macro view); `static` / `fred` force one source |
| `fred_vintages`, `fred_vintage_step_days`, `fred_cache_dir`, `fred_cache_max_age_days` | False, 31, None, 1 | ALFRED vintages for revised series; on-disk cache and how old a cached latest-vintage series may be before it is re-downloaded (None = never) |
| `edgar`, `edgar_user_agent`, `edgar_cache_dir`, `edgar_cache_max_age_days`, `edgar_ciks` | True, None, None, 7, {} | SEC EDGAR fundamentals and filing news for real-data equities; the SEC's required contact (or `EDGAR_USER_AGENT` in `.env`), without which EDGAR is skipped with one warning; endpoint cache and its age; ticker → CIK overrides |
| `agentic.approval` | `auto` | `auto`, `queued` or `deny` gateway (`serve` defaults to `queued`; `mcp` refuses `queued`) |
| `agentic.llm_planner`, `llm_critic`, `llm_reporter` | False, True, True | Which governance steps may use the model |
| `agentic.use_alpha_tool`, `critic_divergence`, `tool_timeout_s` | True, 0.6, 30.0 | Canonical plan and executor settings; the deadline also applies to remote MCP calls |
| `agentic.symbol_universe`, `deny_tools`, `api_keys`, `task_db` | None, [], dev keys, None | Policy inputs, API roles (an override replaces the dev keys) and the persistent task store |
| `agentic.max_symbols_per_call`, `max_plan_lookback_bars`, `max_retained_runs` | 60, 200000, 256 | Longest `symbols` list one tool call may name; symbols × lookback days a plan's tool steps may load in total; finished runs kept in memory per harness |
| `agentic.instance_id`, `lease_s` | None (host:pid:random), 90.0 | Owner id stamped on the runs an instance drives; a live run's heartbeat lease (≥ 1 s) — only records whose lease has expired are swept |
| `agentic.workers`, `queue_limit`, `sweep_interrupted` | 4, 64, True | Task threads per API process; tasks in flight beyond which `POST /tasks` answers 503; whether this process sweeps expired records at startup |
| `results_dir`, `memory_path`, `save_reports` | `results`, `results/memory.jsonl`, False | Output locations; `memory_path` None keeps memory in-process only |

`static_macro_max_age_days` no longer exists: real data never falls back to the static table.

## Extension points

| To add | Do this |
|---|---|
| A tool | A method on `DeskTools` (JSON-safe payload), registered in `build_registry` with `ToolAnnotations` (read-only, risk, required capabilities, evidence type). It is then in-process, over MCP and in the planner's catalogue, under policy |
| A policy rule | A callable `PolicyContext -> PolicyDecision | None`; place it before `allow_rule` in the tuple passed to `PolicyEngine` |
| A critic check | Append a `Check` in `Critic.review`; use severity `error` for anything that must fail the review |
| A knowledge document | A Markdown file in `agentic/knowledge/docs`; headings become chunks |
| An analyst | Subclass `Analyst` (`gather`, `rules`, `untrusted_keys`, `abstain`), register it in `ANALYSTS`, and name it in `config["analysts"]` or `DEFAULT_ANALYSTS` |
| A baseline stream | A weight function added to `baseline_weights` in `backtest.py`; it is then costed and printed in every table. Add it to `LONG_SHORT_STREAMS` if it must short whatever the mandate |
| An alpha | A function `AlphaInputs -> ndarray` in `ALPHAS` (and the asset-class lists) |
| A weighting scheme | A function over a covariance in `portfolio.py`, added to `METHODS` and `construct` |
| An execution algorithm | A schedule function in `algo.py` and a branch in `ExecutionPlan.schedule` |
| A data source | Subclass `MarketDataProvider`, pass prices through `clean_ohlcv`, return only data available at `as_of` |
| A rule change | Behind a `config["rules"]` switch; choose on a design period only (`evaluate --data yahoo --universe core --periods design`, or `scripts/measure_v09.py --period design_long` for a return stream), adopt only if the interval against `B&H vol-target` is above zero, register every variant in `evaluation.TRIALS`; report the extended universe and the reserve period as information, not as a choice basis — both were consulted for the v0.5.1 and v0.6 decisions and v0.8 re-measured every period, so no held-out data remains |
| A quant routine | Declared in `cpp/include/at/`, implemented in `cpp/src/`, bound in `module.cpp`, mirrored in `pycore.py`, exported (with argument validation) in `quant/__init__.py`, cross-checked in `tests/test_quant.py` and fuzzed in `tests/test_fuzz.py`; `strat_tsmom` is the worked example and every exported function is fuzzed |
| A cross-sectional alpha | It is the same `AlphaInputs -> ndarray` function: `xalpha.signal_panels` standardises every library alpha across the universe |
