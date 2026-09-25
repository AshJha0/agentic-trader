# Specification

The governing requirements for agentic-trader and the status of each:
**realised** (implemented and tested), **partial** (implemented with a stated gap) or
**roadmap** (not implemented).

The requirements come from two sources:

- **Paper:** the design in *TradingAgents: Multi-Agents LLM Financial Trading Framework*
  (Xiao, Sun, Luo, Wang, 2024).
- **Project:** additions this project makes on top of the paper, such as FX support, the C++
  core, hard limits and the evaluation protocol.

The code is an independent implementation, not a port of the paper's repository.

## 1. Organisation of agents

| ID | Requirement | Source | Status | Where |
|---|---|---|---|---|
| A1 | Fundamentals analyst: financials, valuation, insider activity | Paper | realised | `FundamentalsAnalyst` |
| A2 | Sentiment analyst: social media and public sentiment | Paper | partial: synthetic social posts plus market-based crowding proxies; no live Reddit or StockTwits feed | `SentimentAnalyst`, `MarketDataProvider.social` |
| A3 | News analyst: company and macro news | Paper | realised: headline tone with recency weighting (Yahoo serves recent news only) | `NewsAnalyst` |
| A4 | Technical analyst: MACD, RSI and other indicators | Paper | realised; optional 12-1 month momentum | `TechnicalAnalyst` |
| A5 | Bullish and bearish researchers debating over n rounds | Paper | realised | `BullResearcher`, `BearResearcher`, `run_debate` |
| A6 | Debate facilitator that records the prevailing view as structured data | Paper | realised | `DebateFacilitator` |
| A7 | Trader that synthesises reports and debate into a decision | Paper | realised: strategic weight plus tilt | `Trader` |
| A8 | Risk team with risk-seeking, neutral and conservative views, in discussion | Paper | realised | `RiskAnalyst`, `run_risk_team` |
| A9 | Fund or portfolio manager that approves or adjusts the final trade | Paper | realised | `PortfolioManager` |
| A10 | FX macro / rates analyst in place of company fundamentals | Project | realised: point-in-time FRED inputs | `MacroAnalyst` |
| A11 | Analysts abstain rather than invent a view without data, and make no model call | Project | realised; tested | `Analyst.abstain`, `AnalystReport.abstained` |

## 2. Communication and reasoning

| ID | Requirement | Source | Status | Where |
|---|---|---|---|---|
| C1 | Structured documents in a global state, not long message histories | Paper | realised | `state.py`, `reports_digest()` |
| C2 | Natural language only inside debates, stored as structured turns | Paper | realised | `DebateTurn`, `RiskView` |
| C3 | Quick-thinking model for retrieval/summaries, deep-thinking model for reasoning | Paper | realised | `quick_think_llm` / `deep_think_llm` |
| C4 | ReAct-style interleaving of reasoning and tool calls | Paper | partial: tools run deterministically before a single reasoning call per agent; there is no model-driven tool-call loop | `Analyst.run` |
| C5 | Explainable decisions: a natural-language rationale at every step | Paper | realised | `to_markdown()` audit trail |
| C6 | Deterministic rule-based reasoning when no LLM is configured, and as the fallback on any LLM failure | Project | realised; tested with a garbage-emitting model | `Agent.ask_json`, `rules()` |
| C7 | LLM output clipped to valid ranges, validated for required keys, non-numeric values coerced | Project | realised; tested with `inf`, `nan`, strings and wrong-side stops | `clip`, `extract_json`, `sane_levels` |
| C8 | Third-party text isolated from instructions in prompts | Project | realised; tested with injected headlines and tag-escape attempts | `untrusted_block`, `Analyst.untrusted_keys` |
| C9 | Hard cap on model calls and a request timeout | Project | realised; tested | `BudgetedLLM`, `max_llm_calls`, `llm_timeout_s` |
| C10 | Portfolio context: the firm knows the current position | Project | realised | `propagate(current_weight=)`, `scan(positions=)` |

## 3. Risk and execution controls

| ID | Requirement | Source | Status | Where |
|---|---|---|---|---|
| R1 | Firm limits enforced after any model output: max position, 1-day VaR95, shorting, minimum trade | Project | realised; tested with a hijacked model | `PortfolioManager.guardrails` |
| R2 | ATR-based stop-loss and take-profit on every directional decision, consistent with the final direction | Project | realised; tested | `protective_levels`, `sane_levels` |
| R3 | Volatility-targeted sizing for the neutral view; VaR-capped conservative view | Project | realised | `RiskAnalyst.rules_weight` |
| R4 | Transaction costs, slippage, equity borrow fees and point-in-time FX carry in backtests | Project | realised; tested | `run_backtest` (`carry=`) |
| R5 | No-trade band that never holds a position the limits forbid | Project | realised; tested | `PortfolioManager.no_trade_band` |
| R6 | Protective stops simulated intraday with gap fills | Project | realised; tested in C++ and Python, cross-checked | `run_backtest_ex` |
| R7 | Refuse decisions on stale or insufficient data | Project | realised; tested | `graph.propagate` |
| R8 | Live order execution / broker connectivity | Project | roadmap: out of scope for a research framework (`scan` exports decisions for an OMS) | — |

## 4. Data

| ID | Requirement | Source | Status | Where |
|---|---|---|---|---|
| D1 | Historical prices | Paper | realised: Yahoo (total-return), CSV, synthetic | `data/` |
| D2 | Point-in-time discipline: no information after the as-of close | Project | realised: provider contract plus a second clip in the graph; tested | `graph.propagate`, `clip_history` |
| D3 | Financial statements and insider transactions | Paper | partial: synthetic quarterly reports with a 30-day lag; Yahoo fundamentals only near today (refused for past dates to avoid leakage) | `SyntheticProvider.fundamentals`, `YahooProvider.fundamentals` |
| D4 | News and social media | Paper | partial: synthetic, Yahoo recent news, CSV news; no historical news vendor | `news`, `social` |
| D5 | Macro inputs for FX: policy rates and inflation | Project | realised: FRED with publication lags and staleness checks; the static table only for synthetic data or recent dates | `data/fred.py`, `fx_macro` |
| D6 | Deterministic offline dataset | Project | realised: seeded, regime-switching, fat-tailed | `SyntheticProvider` |
| D7 | Robust ingestion of messy files | Project | realised; tested | `clean_ohlcv`, `CSVProvider` |
| D8 | Vintage-accurate macro data (as first published) | Project | roadmap: FRED serves latest vintages; ALFRED would fix CPI revisions | — |

## 5. Evaluation

| ID | Requirement | Source | Status | Where |
|---|---|---|---|---|
| E1 | Backtest over Jan–Mar 2024 on large-cap US stocks | Paper | realised | [evaluation/evaluation.md](evaluation/evaluation.md) |
| E2 | Baselines: Buy & Hold, MACD, KDJ+RSI, ZMR, SMA | Paper | realised (C++) | `strategies.cpp`, `baseline_weights` |
| E3 | Metrics: cumulative return, annualised return, Sharpe, max drawdown | Paper | realised, plus volatility, Sortino, Calmar, win rate, exposure, trades and the Sharpe t-statistic | `compute_metrics` |
| E4 | Reproduce the paper's LLM results (CR 23–27%, Sharpe 5.6–8.2) | Paper | **roadmap: the LLM mode has not been evaluated.** The measured numbers are rule-based only | — |
| E5 | FX evaluation on the same protocol | Project | realised (rule-based) | [evaluation/evaluation.md](evaluation/evaluation.md) |
| E6 | Multi-year design / holdout protocol; rule choices on design data only | Project | realised | `evaluation.py`, `agentic-trader evaluate` |
| E7 | Volatility-matched control baseline | Project | realised | `B&H vol-target` |
| E8 | Reproducible before/after for every rule change | Project | realised | `RULES_V02`, `--rules v02` |
| E9 | Multi-asset portfolio evaluation | Project | realised: equal-capital sleeves | `run_portfolio_backtest` |

## 6. Engineering

| ID | Requirement | Source | Status | Where |
|---|---|---|---|---|
| G1 | C++17 quant core exposed to Python | Project | realised: pybind11 | `cpp/`, `quant/` |
| G2 | Runs without a compiler | Project | realised: numpy twin, selected automatically | `quant/pycore.py` |
| G3 | C++ and numpy backends numerically identical | Project | realised: cross-checked to 1e-9 (indicators) and 1e-11 (randomised extended backtests) in CI | `tests/test_quant.py`, `tests/test_quant_edges.py` |
| G4 | CI on Linux, Windows and macOS; Python 3.10–3.14 | Project | realised | `.github/workflows/ci.yml` |
| G5 | Reflection / memory of past decisions, crash-safe | Project | realised: horizon-gated, atomic writes, corrupt lines skipped | `memory.py` |
| G6 | Checkpoint and resume of long runs | Project | roadmap | — |
| G7 | Portfolio-level (multi-asset) allocation | Project | partial: equal-capital sleeves in backtests; no cross-asset risk budgeting or correlation-aware sizing | `run_portfolio_backtest` |
| G8 | Watchlist runs that survive individual failures | Project | realised; tested | `TradingGraph.scan`, `agentic-trader scan` |
| G9 | Friendly CLI failures (no tracebacks for bad input) | Project | realised; tested | `cli.main` |
