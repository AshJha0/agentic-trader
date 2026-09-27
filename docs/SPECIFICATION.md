# Specification

The governing requirements for agentic-trader and the status of each: **realised**
(implemented and tested), **partial** (implemented with a stated gap) or **roadmap** (not
implemented). Requirements are grouped by layer: the desk (sections 1–6), the agentic layer
(section 7) and the quant research layer (section 8).

## 1. Organisation of agents

| ID | Requirement | Status | Where |
|---|---|---|---|
| A1 | Fundamentals analyst: financials, valuation, insider activity | realised | `FundamentalsAnalyst` |
| A2 | Sentiment analyst: social and market-based crowding | partial: synthetic social posts plus market-based crowding proxies; no live social feed | `SentimentAnalyst`, `MarketDataProvider.social` |
| A3 | News analyst: company and macro news | realised: headline tone with recency weighting (Yahoo serves recent news only) | `NewsAnalyst` |
| A4 | Technical analyst: MACD, RSI, Bollinger, trend and volatility | realised; optional 12-1 month momentum | `TechnicalAnalyst` |
| A5 | Bullish and bearish researchers debating over n rounds | realised | `BullResearcher`, `BearResearcher`, `run_debate` |
| A6 | Debate facilitator that records the prevailing view as structured data | realised | `DebateFacilitator` |
| A7 | Trader that synthesises reports and debate into a decision | realised: strategic weight plus tilt | `Trader` |
| A8 | Risk team with aggressive, neutral and conservative views, in discussion | realised | `RiskAnalyst`, `run_risk_team` |
| A9 | Portfolio manager that approves or adjusts the final trade | realised | `PortfolioManager` |
| A10 | FX macro / rates analyst in place of company fundamentals | realised: point-in-time FRED inputs | `MacroAnalyst` |
| A11 | Analysts abstain rather than invent a view without data, and make no model call | realised; tested | `Analyst.abstain`, `AnalystReport.abstained` |
| A12 | Alpha analyst that reads the alpha library's snapshot | realised as an opt-in analyst (`"alpha"`): it speaks only through `alpha.significant_alpha_signal` (alphas whose overlap-aware `t(IC)` at the 10-bar horizon clears 2.0 with at least 30 pairs — a per-alpha 5% test with no multiplicity control, so on pure-noise histories it still speaks about 22% of the time); measured on the design period and left off by default | `AlphaAnalyst`, `alpha.significant_alpha_signal` |

## 2. Communication and reasoning

| ID | Requirement | Status | Where |
|---|---|---|---|
| C1 | Structured documents in a global state, not long message histories | realised | `state.py`, `reports_digest()` |
| C2 | Natural language only inside debates, stored as structured turns | realised | `DebateTurn`, `RiskView` |
| C3 | Quick model for retrieval and summaries, deep model for reasoning | realised | `quick_think_llm` / `deep_think_llm` |
| C4 | Interleaved reasoning and tool use | partial: tools run under the harness before a single reasoning call per agent; the model may propose the plan but does not drive a tool-call loop | `AgentHarness`, `planner.py` |
| C5 | Explainable decisions: a rationale at every step, with evidence ids | realised | `to_markdown()`, `evidence_ids` on every document |
| C6 | Deterministic rule-based reasoning when no LLM is configured, and as the fallback on any LLM failure | realised; tested with a garbage-emitting model | `Agent.ask_json`, `rules()` |
| C7 | LLM output clipped to valid ranges, validated for required keys; a required number that is null, a string, a boolean or non-finite rejects the whole reply (the rules apply) rather than being coerced | realised (v0.8); tested with `inf`, `nan`, strings, nulls and wrong-side stops | `Agent.ask_json(numeric=)`, `clip`, `extract_json`, `sane_levels` |
| C8 | Third-party text isolated from instructions in prompts | realised; tested with injected headlines and tag-escape attempts | `untrusted_block`, `Analyst.untrusted_keys` |
| C9 | Hard caps on model calls and on estimated spend, a request timeout and usage/cost accounting | realised; tested. Spend is bounded by the dollar cap: each call reserves its estimated maximum before dispatch, so concurrent workers cannot overshoot; a served model id without a list price exhausts the budget; a timed-out request is billed at its estimate per SDK attempt | `BudgetedLLM`, `UsageTracker`, `max_llm_calls`, `max_llm_cost_usd`, `llm_timeout_s`, `llm_max_retries` |
| C10 | Portfolio context: the firm knows the current position | realised | `propagate(current_weight=)`, `scan(positions=)` |
| C11 | Prompts can be anonymised (symbols, names, dates replaced) before leaving the process | realised; tested | `anonymize.py`, `llm_anonymize` |
| C12 | Agents read retrieved policy passages | realised: the trader and risk prompts include `state.knowledge` | `trader.policy_passages` |

## 3. Risk and execution controls

| ID | Requirement | Status | Where |
|---|---|---|---|
| R1 | Firm limits enforced after any model output: max position, 1-day VaR95 (the left tail for a long, the right tail for a short), shorting, minimum trade; optionally the whole book's VaR, which fails closed when it cannot be evaluated | realised; tested with a hijacked model | `PortfolioManager.guardrails`, `risk.position_var`, `portfolio.book_var_scale` |
| R2 | ATR-based stop-loss and take-profit on every directional decision, consistent with the final direction | realised; tested | `protective_levels`, `sane_levels` |
| R3 | Volatility-targeted sizing for the neutral view; VaR-capped conservative view | realised | `RiskAnalyst.rules_weight` |
| R4 | Transaction costs, slippage, equity borrow fees and point-in-time FX carry in backtests | realised; tested. Since v0.8 costs are multiplicative and the target is a fraction of post-cost equity; units are constant between decisions and carry accrues on the constant notional | `run_backtest` (`carry=`) |
| R9 | Market impact in backtests, scaled by account size, charged to the agent and every baseline alike | realised (v0.5); tested and cross-checked C++ vs numpy; FX needs a configured notional ADV. Since v0.8 the coefficient follows the equity actually traded (`sqrt(equity_t / initial_capital)`) and a portfolio sleeve pays the impact of its own capital share, not the whole book's | `costs.impact_coeff`, `backtest.impact_coefficients`, `run_backtest(impact=)`, `run_agent_backtest(capital_share=)` |
| R11 | Idle cash earns the point-in-time bill rate and Sharpe is on excess returns, so a low-exposure strategy is compared fairly with buy & hold | realised (v0.8): FRED DTB3 with a 1-day publication lag on real data (`cash_leg`); equities fund positions so `1 - \|w\|` earns it, FX forwards earn it on the whole account; AR, CR and Calmar stay total-return. Constant 0 on synthetic data | `data.base.cash_rates`, `run_backtest(cash_rate=)`, `compute_metrics(rf=)`, [evaluation](evaluation/evaluation.md) |
| R12 | Ruin is a floor, not a negative equity | realised (v0.8): when a bar would take equity to 0 the return is -1, the position is written off and every later bar is flat; statistics stop at the ruin bar | `BacktestResult.ruined_at`, `Metrics.ruined` |
| R10 | An FX strategic weight from the point-in-time carry (the FX analogue of the equity premium weight), chosen on the core design period and judged on unseen crosses | realised (v0.5.1); tested; `RULES_V03` reproduces the rule set without it | `rules.fx_carry_neutral`, `risk.fx_carry_neutral_scale/cap`, [evaluation](evaluation/evaluation.md#the-fx-carry-neutral-rule-v051-the-protocols-first-use) |
| R5 | No-trade band that never holds a position the limits forbid | realised; tested | `PortfolioManager.no_trade_band` |
| R6 | Protective stops simulated intraday with gap fills | realised; tested in C++ and Python, cross-checked. The open is resolved against both levels first (a gap through the take-profit fills at the open, as a gap through the stop does), then the stop-first rule applies to the intrabar range; the desk is told it is flat after an exit | `run_backtest_ex`, `run_agent_backtest` |
| R7 | Refuse decisions on stale or insufficient data | realised; tested | `graph.prepare` |
| R8 | Live order execution / broker connectivity | roadmap: `execution.submit_order` is a policy-gated stub that records a ticket (whole shares or whole FX lots of the base currency, notional in the account currency, the reference price, a plan reference that must verify, the intent and the position before and after) as a DECISION evidence record; the notional is capped by policy before approval and again at execution; `scan --out` exports decisions | `servers.DeskTools.submit_order`, `execution.max_order_notional` |
| R13 | FX orders are sized in the base currency of the pair from a notional in the account currency, once, at plan time | realised (v0.8): `USDJPY` on a USD account is `notional` USD of base, a cross needs the base->account rate (fetched point in time from the provider) or is refused; the plan, the `execution.plan` payload, the ticket and the CLI all carry the same rounded quantity with its unit | `account_currency`, `algo.plan_execution`, `algo.base_to_account_rate` |

## 4. Data

| ID | Requirement | Status | Where |
|---|---|---|---|
| D1 | Historical prices | realised: Yahoo (total-return), CSV, synthetic | `data/` |
| D2 | Point-in-time discipline: no information after the as-of close | realised: provider contract plus a second clip in the graph; tested | `graph.prepare`, `clip_history` |
| D3 | Financial statements and insider transactions | realised (v0.6, corrected v0.8) for real-data equities: SEC EDGAR XBRL facts by the date they were *filed*, each span valued as known at the as-of date (the latest print filed by then); quarterly flows rebuilt separately per XBRL tag and per reporting basis (a re-print more than 5% away opens a new basis generation; no difference ever straddles tags or generations; a trailing year is one tag, one basis), trailing-twelve-month growth, margin, EPS and P/E, leverage, FCF yield, with every per-share print rebased across later stock splits and the ratios taken on the close as traded; per-share ratios are absent when the share count or EPS window has stopped updating (400-day / one-quarter recency guards) or fails the market-cap and EPS sanity checks (another share class); insider Form 4 filings counted in the news stream. No consensus data, so EPS surprise stays `None`; funds and index ETFs return nothing; a cross-tag rename (Apple 2018) costs a year of growth by design. Synthetic reports keep the 30-day lag | `data/edgar.py` (`quarterly_table`), `YahooProvider.fundamentals` |
| D4 | News and social media | partial → news realised (v0.6) for real-data equities from the EDGAR filing stream (8-K item codes as headlines with a conservative tone, periodic and ownership filings, insider counts) plus Yahoo's recent headlines; social media has no free point-in-time archive and that analyst still abstains historically | `EdgarClient.news`, `YahooProvider.news`, `social` |
| D5 | Macro inputs for FX: policy rates and inflation | realised: FRED with publication lags and staleness checks through one resolver shared by the macro analyst and the carry the backtester credits; the static table only for synthetic data (or `fx_macro_source="static"`), never as a fallback — a date with no point-in-time rate for either leg has no macro view and no carry, whatever the wall-clock date. SEK has no series; every macro answer records its source | `data/base.py` (`fx_rates`, `fx_macro`), `data/fred.py` |
| D10 | A point-in-time cash rate for the backtester's idle cash | realised (v0.8): FRED 3-month bill (`DTB3`, 1-day lag, 10-day max age) on real-data providers; the constant `risk_free_annual` on synthetic and CSV data; `off` credits nothing | `MarketDataProvider.risk_free_series`, `cash_leg` |
| D6 | Deterministic offline dataset | realised: seeded, regime-switching, fat-tailed | `SyntheticProvider` |
| D7 | Robust ingestion of messy files | realised; tested | `clean_ohlcv`, `CSVProvider` |
| D8 | Vintage-accurate macro data (as first published) | realised (v0.5), opt-in: revised series are read from the ALFRED vintage current at each date, sampled monthly; policy rates are never revised. Off in the published runs | `fred_vintages`, `FredClient(vintages=True)` |
| D9 | Every data access under the harness is a catalogued, evidenced tool call | realised; tested | `RecordingProvider` |

## 5. Evaluation

| ID | Requirement | Status | Where |
|---|---|---|---|
| E1 | Multi-year design / holdout protocol; rule choices on design data only | realised | `evaluation.py`, `agentic-trader evaluate` |
| E2 | Baselines: Buy & Hold, SMA, MACD, KDJ+RSI, ZMR | realised (C++) | `strategies.cpp`, `baseline_weights` |
| E3 | Metrics: cumulative and annualised return, volatility, Sharpe and its t-statistic, Sortino, max drawdown, Calmar, win rate, exposure, trades | realised; since v0.8 Sharpe, Sortino and the t-statistic are on excess returns over the per-bar cash rate, turnover and the trade count come from the trades actually executed (exit fills included), and a ruined series stops at the ruin bar | `compute_metrics` |
| E4 | Volatility-matched control baseline | realised | `B&H vol-target` |
| E5 | FX evaluation on the same protocol | realised (rule-based) | [evaluation/evaluation.md](evaluation/evaluation.md) |
| E6 | A short reference window (Q1 2024) inside the holdout | realised | `PERIODS["q1_2024"]` |
| E11 | A universe wide enough that Sharpe differences are not noise, partitioned into the names choices were made on and names never consulted | realised (v0.5): 15 core + 45 extended instruments, tagged per row | `UNIVERSES`, `universe_group`, `evaluate --universe` |
| E12 | A fresh holdout for the next rule change, declared before the change exists | partial: the protocol is written down and the machinery exists (the extended universe on every period plus a `reserve` period from 2026-07-01), but that data is spent — the reserve and the extended universe judged the v0.5.1 carry rule and the v0.6 EDGAR / cross-sectional decisions, and v0.8 re-measured every period under the corrected engine — so no held-out data remains and the next unseen data is the future | `PERIODS["reserve"]`, [evaluation](evaluation/evaluation.md#the-next-rule-change-what-counts-as-unseen) |
| E7 | Reproducible before/after for every rule change | realised | `RULES_V02`, `--rules v02` |
| E8 | Multi-asset portfolio evaluation with a chosen weighting scheme | realised | `run_portfolio_backtest(weighting=)` |
| E9 | Selection-aware statistics: bootstrap interval, probabilistic and deflated Sharpe, minimum track record | realised | `stats.selection_report`, `agentic-trader stats` |
| E10 | LLM-mode evaluation with usage and cost, in parallel | realised; first run in v0.5.1 (5 stocks, Q1 2024, $4); v0.6 adds the multi-year harness (design + holdout, model tiers, `repeats` for model variance, prompt hashes in `meta`) and its staged runner with per-stage dollar caps — see the evaluation for what has been run | `evaluation.py`, `llm.py`, [evaluation](evaluation/evaluation.md#the-llm-desk-v051-the-first-measured-result) |
| E13 | Statistical power across the universe, not only along time | realised (v0.6, corrected v0.8): `paired_bootstrap` resamples instruments (pairs kept together) for the mean difference between two strategies, and with five or more `asset_class:universe` groups (`--universe all`) runs a two-stage cluster bootstrap that respects the common factor within a group (v0.7's within-group fixed-count scheme, which could only narrow the interval, is retracted); `EvaluationResult.paired` / `paired_table` and the CLI print the 95% interval, two-sided `p`, the scheme used and a Benjamini-Hochberg flag on the unrounded `p` for every baseline | `stats.paired_bootstrap(groups=)`, `stats.benjamini_hochberg`, `evaluate --repeats` |
| E16 | Portfolio-level differences carry an interval of their own, and the cadence noise floor is measured | realised (v0.8): `PortfolioReport.sharpe_difference` is a paired block bootstrap over the same days on excess returns; `rebalance_offset` shifts the decision grid so the spread across phases can be reported beside any difference | `stats.paired_sharpe_block_bootstrap`, `run_portfolio_backtest(rebalance_offset=)` |
| E17 | The selection statistics count every variant ever judged on the design period | realised (v0.8): a trials registry of 26 variants (24 re-measurable under the current engine, 2 historical from the record) feeds `selection_report` | `evaluation.TRIALS`, `reproducible_trials` |
| E18 | The risk model's forecasts are tested against what happened | realised (v0.7, rewritten v0.8): Kupiec and Christoffersen coverage tests of a rolling historical VaR forecast, and of the desk's own per-instrument 250-day VaR against next-day returns; book-level VaR was off in every published run and its coverage is untested | `stats.rolling_var_forecast`, `stats.var_backtest`, `agentic-trader stats --var-backtest` |
| E19 | Every saved result says what produced it | realised (v0.8): package version, git commit and dirty flag, quant backend, interpreter, platform and dependency versions in `meta["provenance"]` of every evaluation and calibration, a `*.provenance.json` sidecar beside every `--out` CSV, and the same line in the CLI header | `provenance.py`, `cli.common.write_sidecar` |
| E14 | The model's own variance, anchoring on the book, and drift over time are measured, not assumed | realised (v0.6): `evaluate(repeats=)` + `run_dispersion`; `calibrate` runs one frozen state `n` times per anchor and reports dispersion, the anchoring slope and drift against a stored report | `calibration.py`, `agentic-trader calibrate` |
| E15 | Prompts are pinned: a result records exactly which wording produced it | realised (v0.6): SHA-256 hashes of every agent's system prompt and prompt-building code, bundled into one hash in every evaluation and calibration record | `prompts.py`, `EvaluationResult.meta["prompts"]` |

## 6. Engineering

| ID | Requirement | Status | Where |
|---|---|---|---|
| G1 | C++17 quant core exposed to Python | realised: pybind11 | `cpp/`, `quant/` |
| G2 | Runs without a compiler | realised: numpy twin, selected automatically | `quant/pycore.py` |
| G3 | C++ and numpy backends numerically identical | realised: cross-checked to 1e-9 (indicators) and 1e-11 (randomised extended backtests) in CI, including rolling extremes, Spearman, Almgren-Chriss and impact; property-based fuzzing (hypothesis) asserts crash-freedom on wild inputs and agreement on sane ones | `tests/test_quant.py`, `tests/test_quant_edges.py`, `tests/test_quant_research.py`, `tests/test_fuzz.py` |
| G4 | CI on Linux, Windows and macOS; Python 3.10–3.14 | realised | `.github/workflows/ci.yml` |
| G5 | Reflection / memory of past decisions, crash-safe | realised: horizon in trading days, outcomes valued on the provider's own price series (a split or a provider switch cannot become a verdict), an append-only log with one `fsync` per line under a lock so threads and sibling processes cannot overwrite each other, corrupt lines skipped | `memory.py` |
| G6 | Checkpoint and resume of long runs | partial: a task pauses in AWAITING_APPROVAL and resumes in-process, and every run is persisted at each transition with its owner and a heartbeat (v0.5, v0.8); a run whose owner stopped heartbeating is failed after `lease_s` (or at restart when `instance_id` is stable), not resumed; a live sibling's runs survive; long backtests have no checkpoint | `AgentHarness.resume`, `TaskStore.mark_interrupted(owner, lease_s)` |
| G7 | Portfolio-level (multi-asset) allocation | realised: five weighting schemes with shrunk covariance and risk attribution, and (v0.5) hierarchical risk budgets across asset classes | `portfolio.py` (`groups`, `group_budgets`), `run_portfolio_backtest(class_budgets=)` |
| G8 | Watchlist runs that survive individual failures | realised; tested | `TradingGraph.scan`, `agentic-trader scan` |
| G9 | Friendly CLI failures (no tracebacks for bad input) | realised; tested | `cli.main` |
| G10 | The API serves many tasks without unbounded threads or spend, and scales past one process | realised (v0.6): a bounded thread pool per process with a queue limit (`503` + `Retry-After` when full), `serve --processes N` over a shared task store (records from any process; cancel/approve only on the owning process, `409` elsewhere) | `api.create_app(workers, queue_limit)`, `multiprocess_options`, `app_factory` |
| G11 | The documentation is executed and checked in CI: cookbook recipes, Mermaid diagrams, links | realised (v0.6): a `docs` job runs every offline recipe, renders every diagram with mermaid-cli and resolves every internal link | `scripts/run_cookbook.py`, `scripts/check_mermaid.py`, `scripts/check_links.py`, `.github/workflows/ci.yml` |
| G12 | The agentic layer's input boundaries are fuzzed, not only the C++ one | realised (v0.6): hypothesis properties over `coerce_arguments` (random schemas and JSON), `validate_plan` (random plans must yield a plan that ends with governance, pins symbol and date, schedules no state change), `PolicyEngine.evaluate` (always a decision; never ALLOW on a denied, unauthorised or state-changing request), `extract_json` and `untrusted_block` | `tests/test_fuzz_agentic.py` |
| G13 | One configuration knob for the alpha window | realised (v0.6): `alpha_lookback_days` (900) drives the alpha analysts and the `quant.alpha` / `quant.xalpha` tools; `lookback_days` (400) drives everything else, and every tool's `lookback_days` argument defaults to the configured value | `config.py`, `DeskTools._history` |

## 7. Agentic governance

| ID | Requirement | Status | Where |
|---|---|---|---|
| V1 | A frozen domain model: tasks, plans, tool requests and results, evidence, findings, policy decisions, roles, capabilities | realised | `agentic/domain.py` |
| V2 | A tool registry whose schemas are derived from function signatures; arguments coerced and validated (dates, numbers, bounded strings and arrays, no extras) | realised; tested | `ToolRegistry`, `coerce_arguments` |
| V3 | Every tool call passes through a policy engine with ordered, named rules that fail closed | realised; tested. Since v0.8 the argument guards (universe, dates, weights, lookback, a bounded `symbols` list, a finite positive quantity, a notional cap) run before the approval decision, so a bad order is denied rather than parked for a person | `PolicyEngine`, `DEFAULT_RULES` |
| V4 | Role-based capabilities: viewer, analyst, trader, risk, admin | realised; tested | `ROLE_CAPABILITIES` |
| V5 | State-changing tools always require approval; approval identity is the tool and its arguments within a task; approvals can be queued, automatic or denied | realised; tested (a re-submitted approved request is recognised) | `read_only_rule`, `ToolRequest.request_id`, `QueuedApprovalGateway` |
| V6 | Every tool result becomes an evidence record with a SHA-256 digest before it is interpreted; failures are evidenced too | realised; tested | `ToolExecutor`, `EvidenceStore` |
| V7 | Findings cite evidence ids; findings whose ids do not resolve are dropped | realised; tested | `Finding`, `VALIDATING_EVIDENCE` |
| V8 | A canonical plan, an optional model-proposed plan, and a validator that strips unknown tools, pins the symbol and date, repairs arguments and appends governance steps | realised; tested with hostile plans | `planner.py` |
| V9 | A harness state machine with a transition table, pause on approval, resume, cancel and terminal states | realised; tested | `AgentHarness`, `TRANSITIONS` |
| V10 | Tool steps batched in parallel with timeouts and bounded retries | realised: read-only tools retry within `max_attempts`; a state-changing tool gets exactly one attempt and a timeout or transient failure is reported as `outcome unknown, not retried`. A timeout isolates the call (the worker is abandoned and counted) but cannot terminate it | `ExecutorConfig`, `tools.invoke_with_deadline` |
| V11 | A critic with deterministic checks; a model critique can only lower confidence | realised; tested | `Critic` |
| V12 | Reports audited for numbers (rounding tolerated, invention rejected) and evidence ids | realised; tested | `number_audit`, `evidence_audit` |
| V13 | Retrieval over a local knowledge base without a network or a model | realised: hashed TF-IDF over 11 documents | `KnowledgeBase` |
| V14 | Tracing spans, Prometheus-style metrics and JSON logs | realised: one process-level metrics exposition that every run's tracer writes to, label values escaped | `tracing.py`, `AgentHarness.metrics`, `/metrics` |
| V15 | The registry served over MCP (stdio), and remote MCP tools usable under the same policy | realised; tested with a real stdio round trip. Since v0.8 the served side is governed too (every call goes through a policy engine, the configured approval gateway and an evidence store for an operator-chosen role) and remote tools without annotations are classified fail-closed (not read-only, high risk) unless the operator overrides them | `mcp_server.py` (`governed_executor`, `classify_remote_tool`) |
| V16 | An HTTP API with API-key roles, asynchronous tasks and approvals | realised; tested with the FastAPI client. The gateway follows `agentic.approval`; `/approvals` answers 409 when approvals are not queued; two decisions on one run can never drive it twice | `api.py`, `agentic-trader serve` |
| V17 | Persistent task store | realised (v0.5, v0.6, v0.8): SQLite records written at every transition with owner and heartbeat, served by the same routes after a restart and from any of `serve --processes N` workers (G10); the sweep of interrupted runs is lease-gated | `agentic/store.py`, `agentic.task_db`, `serve --task-db`, `agentic.instance_id`, `agentic.lease_s` |
| V18 | Deployment guards: TLS, no development keys off loopback, keys replaced rather than merged | realised (v0.5); tested | `serve_options`, `serve --ssl-cert/--ssl-key`, `config._REPLACE_KEYS` |

## 8. Quant research

| ID | Requirement | Status | Where |
|---|---|---|---|
| Q1 | An alpha library of point-in-time signals for equities and FX | realised: nine signals, no future bars | `alpha.ALPHAS` |
| Q2 | Signal diagnostics: IC and t-stat, decay, hit rate, tercile spread, autocorrelation, correlations, combination | realised; since v0.8 the t-statistic is overlap-aware (`n / horizon` effective observations, the rule the cross-sectional report already used, so published `t(IC)` at horizon 10 is about 3.16x smaller than before), the hit rate is printed beside the base rate (`up%`) and terciles are assigned by rank so a signal tied on most bars still has a top and a bottom | `alpha_report`, `information_coefficient(horizon=)`, `tercile_spread`, `combine` |
| Q3 | Execution algorithms: TWAP, VWAP, POV, Almgren-Chriss | realised; Almgren-Chriss in C++ with the numpy twin | `algo.py`, `at::almgren_chriss` |
| Q4 | An execution simulator with spread, square-root impact and implementation shortfall | realised; tested. Each slice pays impact against its own bar's volume, so VWAP reproduces the backtester's single-shot law at any slice count; the shortfall is on the requested quantity with the unfilled remainder marked at the close and reported separately; fills are simulated on the session after the decision | `simulate_execution(requested=)` |
| Q5 | A decision turned into a parent order and schedule | realised: whole shares or whole FX lots in the base currency, an intent, a verifiable plan reference, and an Almgren-Chriss schedule driven by a dimensionless urgency independent of the price level | `plan_execution`, `ExecutionPlan.schedule`, `agentic-trader execute` |
| Q6 | Covariance estimation with EWMA and Ledoit-Wolf shrinkage | realised; tested (shrinkage in [0, 1], PSD). The intensity is the weighted Ledoit-Wolf constant-correlation estimate for the EWMA covariance itself: weighted centring and moments, and the effective sample size `1 / sum(w^2)` of the EWMA weights in place of `T` (it reduces to the unweighted formula at equal weights) | `estimate_cov`, `ledoit_wolf_shrink(weights=)`, `ewma_weights` |
| Q7 | Weighting schemes: equal, inverse-vol, risk parity, minimum variance, mean-variance, with risk attribution | realised; tested. Every scheme's allocation is projected onto the capped simplex so `max_weight` is honoured exactly; `allocation` is the pre-vol-target split and the vol-target scale never breaks the gross or per-sleeve cap; a window with no variance raises instead of returning NaN | `portfolio.construct`, `PortfolioWeights` |
| Q8 | Backtest statistics that account for selection | realised | `stats.py` |
| Q9 | Research results feed decisions only through measured, opt-in switches | realised: the alpha analyst was measured on the design period and is off by default | [evaluation/evaluation.md](evaluation/evaluation.md) |
| Q10 | Cross-sectional (multi-name) alpha models | realised (v0.5): per-day z-scores / ranks within asset class, per-date IC with an overlap-aware t-statistic, quantile spreads, breadth; a tool and a CLI command. v0.6 adds the `xalpha` analyst (significance-gated, peers = the core universe of the asset class by default) and measures it under the protocol — see the evaluation for the verdict and whether it is on | `xalpha.py`, `quant.xalpha`, `XAlphaAnalyst`, `agentic-trader xalpha` |
