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
| A12 | Alpha analyst that reads the alpha library's snapshot | realised as an opt-in analyst (`"alpha"`); measured on the design period and left off by default | `AlphaAnalyst`, `alpha.alpha_snapshot` |

## 2. Communication and reasoning

| ID | Requirement | Status | Where |
|---|---|---|---|
| C1 | Structured documents in a global state, not long message histories | realised | `state.py`, `reports_digest()` |
| C2 | Natural language only inside debates, stored as structured turns | realised | `DebateTurn`, `RiskView` |
| C3 | Quick model for retrieval and summaries, deep model for reasoning | realised | `quick_think_llm` / `deep_think_llm` |
| C4 | Interleaved reasoning and tool use | partial: tools run under the harness before a single reasoning call per agent; the model may propose the plan but does not drive a tool-call loop | `AgentHarness`, `planner.py` |
| C5 | Explainable decisions: a rationale at every step, with evidence ids | realised | `to_markdown()`, `evidence_ids` on every document |
| C6 | Deterministic rule-based reasoning when no LLM is configured, and as the fallback on any LLM failure | realised; tested with a garbage-emitting model | `Agent.ask_json`, `rules()` |
| C7 | LLM output clipped to valid ranges, validated for required keys, non-numeric values coerced | realised; tested with `inf`, `nan`, strings and wrong-side stops | `clip`, `extract_json`, `sane_levels` |
| C8 | Third-party text isolated from instructions in prompts | realised; tested with injected headlines and tag-escape attempts | `untrusted_block`, `Analyst.untrusted_keys` |
| C9 | Hard cap on model calls, a request timeout and usage/cost accounting | realised; tested | `BudgetedLLM`, `UsageTracker`, `max_llm_calls`, `llm_timeout_s` |
| C10 | Portfolio context: the firm knows the current position | realised | `propagate(current_weight=)`, `scan(positions=)` |
| C11 | Prompts can be anonymised (symbols, names, dates replaced) before leaving the process | realised; tested | `anonymize.py`, `llm_anonymize` |
| C12 | Agents read retrieved policy passages | realised: the trader and risk prompts include `state.knowledge` | `trader.policy_passages` |

## 3. Risk and execution controls

| ID | Requirement | Status | Where |
|---|---|---|---|
| R1 | Firm limits enforced after any model output: max position, 1-day VaR95, shorting, minimum trade | realised; tested with a hijacked model | `PortfolioManager.guardrails` |
| R2 | ATR-based stop-loss and take-profit on every directional decision, consistent with the final direction | realised; tested | `protective_levels`, `sane_levels` |
| R3 | Volatility-targeted sizing for the neutral view; VaR-capped conservative view | realised | `RiskAnalyst.rules_weight` |
| R4 | Transaction costs, slippage, equity borrow fees and point-in-time FX carry in backtests | realised; tested | `run_backtest` (`carry=`) |
| R5 | No-trade band that never holds a position the limits forbid | realised; tested | `PortfolioManager.no_trade_band` |
| R6 | Protective stops simulated intraday with gap fills | realised; tested in C++ and Python, cross-checked | `run_backtest_ex` |
| R7 | Refuse decisions on stale or insufficient data | realised; tested | `graph.prepare` |
| R8 | Live order execution / broker connectivity | roadmap: `execution.submit_order` is a policy-gated stub that records an ORDER evidence record; `scan --out` exports decisions | — |

## 4. Data

| ID | Requirement | Status | Where |
|---|---|---|---|
| D1 | Historical prices | realised: Yahoo (total-return), CSV, synthetic | `data/` |
| D2 | Point-in-time discipline: no information after the as-of close | realised: provider contract plus a second clip in the graph; tested | `graph.prepare`, `clip_history` |
| D3 | Financial statements and insider transactions | partial: synthetic quarterly reports with a 30-day lag; Yahoo fundamentals only near today (refused for past dates to avoid leakage) | `SyntheticProvider.fundamentals`, `YahooProvider.fundamentals` |
| D4 | News and social media | partial: synthetic, Yahoo recent news, CSV news; no historical news vendor | `news`, `social` |
| D5 | Macro inputs for FX: policy rates and inflation | realised: FRED with publication lags and staleness checks; the static table only for synthetic data or recent dates | `data/fred.py`, `fx_macro` |
| D6 | Deterministic offline dataset | realised: seeded, regime-switching, fat-tailed | `SyntheticProvider` |
| D7 | Robust ingestion of messy files | realised; tested | `clean_ohlcv`, `CSVProvider` |
| D8 | Vintage-accurate macro data (as first published) | roadmap: FRED serves latest vintages; ALFRED would fix CPI revisions | — |
| D9 | Every data access under the harness is a catalogued, evidenced tool call | realised; tested | `RecordingProvider` |

## 5. Evaluation

| ID | Requirement | Status | Where |
|---|---|---|---|
| E1 | Multi-year design / holdout protocol; rule choices on design data only | realised | `evaluation.py`, `agentic-trader evaluate` |
| E2 | Baselines: Buy & Hold, SMA, MACD, KDJ+RSI, ZMR | realised (C++) | `strategies.cpp`, `baseline_weights` |
| E3 | Metrics: cumulative and annualised return, volatility, Sharpe and its t-statistic, Sortino, max drawdown, Calmar, win rate, exposure, trades | realised | `compute_metrics` |
| E4 | Volatility-matched control baseline | realised | `B&H vol-target` |
| E5 | FX evaluation on the same protocol | realised (rule-based) | [evaluation/evaluation.md](evaluation/evaluation.md) |
| E6 | A short reference window (Q1 2024) inside the holdout | realised | `PERIODS["q1_2024"]` |
| E7 | Reproducible before/after for every rule change | realised | `RULES_V02`, `--rules v02` |
| E8 | Multi-asset portfolio evaluation with a chosen weighting scheme | realised | `run_portfolio_backtest(weighting=)` |
| E9 | Selection-aware statistics: bootstrap interval, probabilistic and deflated Sharpe, minimum track record | realised | `stats.selection_report`, `agentic-trader stats` |
| E10 | LLM-mode evaluation with usage and cost, in parallel | realised as a harness (`evaluate(workers=)`, `UsageTracker`, anonymisation); **the run itself has not been made**, so no LLM result is claimed | `evaluation.py`, `llm.py` |

## 6. Engineering

| ID | Requirement | Status | Where |
|---|---|---|---|
| G1 | C++17 quant core exposed to Python | realised: pybind11 | `cpp/`, `quant/` |
| G2 | Runs without a compiler | realised: numpy twin, selected automatically | `quant/pycore.py` |
| G3 | C++ and numpy backends numerically identical | realised: cross-checked to 1e-9 (indicators) and 1e-11 (randomised extended backtests) in CI, including rolling extremes, Spearman and Almgren-Chriss | `tests/test_quant.py`, `tests/test_quant_edges.py`, `tests/test_quant_research.py` |
| G4 | CI on Linux, Windows and macOS; Python 3.10–3.14 | realised | `.github/workflows/ci.yml` |
| G5 | Reflection / memory of past decisions, crash-safe | realised: horizon-gated, atomic writes, corrupt lines skipped | `memory.py` |
| G6 | Checkpoint and resume of long runs | partial: a task pauses in AWAITING_APPROVAL and resumes in-process; there is no on-disk checkpoint | `AgentHarness.resume` |
| G7 | Portfolio-level (multi-asset) allocation | realised: five weighting schemes with shrunk covariance and risk attribution | `portfolio.py` |
| G8 | Watchlist runs that survive individual failures | realised; tested | `TradingGraph.scan`, `agentic-trader scan` |
| G9 | Friendly CLI failures (no tracebacks for bad input) | realised; tested | `cli.main` |

## 7. Agentic governance

| ID | Requirement | Status | Where |
|---|---|---|---|
| V1 | A frozen domain model: tasks, plans, tool requests and results, evidence, findings, policy decisions, roles, capabilities | realised | `agentic/domain.py` |
| V2 | A tool registry whose schemas are derived from function signatures; arguments coerced and validated (dates, numbers, bounded strings and arrays, no extras) | realised; tested | `ToolRegistry`, `coerce_arguments` |
| V3 | Every tool call passes through a policy engine with ordered, named rules that fail closed | realised; tested | `PolicyEngine`, `DEFAULT_RULES` |
| V4 | Role-based capabilities: viewer, analyst, trader, risk, admin | realised; tested | `ROLE_CAPABILITIES` |
| V5 | State-changing tools always require approval; approval identity is the tool and its arguments within a task; approvals can be queued, automatic or denied | realised; tested (a re-submitted approved request is recognised) | `read_only_rule`, `ToolRequest.request_id`, `QueuedApprovalGateway` |
| V6 | Every tool result becomes an evidence record with a SHA-256 digest before it is interpreted; failures are evidenced too | realised; tested | `ToolExecutor`, `EvidenceStore` |
| V7 | Findings cite evidence ids; findings whose ids do not resolve are dropped | realised; tested | `Finding`, `VALIDATING_EVIDENCE` |
| V8 | A canonical plan, an optional model-proposed plan, and a validator that strips unknown tools, pins the symbol and date, repairs arguments and appends governance steps | realised; tested with hostile plans | `planner.py` |
| V9 | A harness state machine with a transition table, pause on approval, resume, cancel and terminal states | realised; tested | `AgentHarness`, `TRANSITIONS` |
| V10 | Tool steps batched in parallel with timeouts and bounded retries | realised | `ExecutorConfig` |
| V11 | A critic with deterministic checks; a model critique can only lower confidence | realised; tested | `Critic` |
| V12 | Reports audited for numbers (rounding tolerated, invention rejected) and evidence ids | realised; tested | `number_audit`, `evidence_audit` |
| V13 | Retrieval over a local knowledge base without a network or a model | realised: hashed TF-IDF over 11 documents | `KnowledgeBase` |
| V14 | Tracing spans, Prometheus-style metrics and JSON logs | realised | `tracing.py`, `/metrics` |
| V15 | The registry served over MCP (stdio), and remote MCP tools usable under the same policy | realised; tested with a real stdio round trip | `mcp_server.py` |
| V16 | An HTTP API with API-key roles, asynchronous tasks and approvals | realised; tested with the FastAPI client | `api.py`, `agentic-trader serve` |
| V17 | Persistent task store and multi-process workers | roadmap: tasks live in the process that runs them | — |

## 8. Quant research

| ID | Requirement | Status | Where |
|---|---|---|---|
| Q1 | An alpha library of point-in-time signals for equities and FX | realised: nine signals, no future bars | `alpha.ALPHAS` |
| Q2 | Signal diagnostics: IC and t-stat, decay, hit rate, tercile spread, autocorrelation, correlations, combination | realised | `alpha_report`, `combine` |
| Q3 | Execution algorithms: TWAP, VWAP, POV, Almgren-Chriss | realised; Almgren-Chriss in C++ with the numpy twin | `algo.py`, `at::almgren_chriss` |
| Q4 | An execution simulator with spread, square-root impact and implementation shortfall | realised; tested | `simulate_execution` |
| Q5 | A decision turned into a parent order and schedule | realised | `plan_execution`, `agentic-trader execute` |
| Q6 | Covariance estimation with EWMA and Ledoit-Wolf shrinkage | realised; tested (shrinkage in [0, 1], PSD) | `estimate_cov` |
| Q7 | Weighting schemes: equal, inverse-vol, risk parity, minimum variance, mean-variance, with risk attribution | realised; tested | `portfolio.py` |
| Q8 | Backtest statistics that account for selection | realised | `stats.py` |
| Q9 | Research results feed decisions only through measured, opt-in switches | realised: the alpha analyst was measured on the design period and is off by default | [evaluation/evaluation.md](evaluation/evaluation.md) |
| Q10 | Cross-sectional (multi-name) alpha models | roadmap: alphas are per instrument | — |
