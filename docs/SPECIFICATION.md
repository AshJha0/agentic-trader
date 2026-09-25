# Specification

The governing requirements for agentic-trader and the status of each:
**realised** (implemented and tested), **partial** (implemented with a stated gap) or
**roadmap** (not implemented).

The requirements come from two sources:

- **Paper:** the design in *TradingAgents: Multi-Agents LLM Financial Trading Framework*
  (Xiao, Sun, Luo, Wang, 2024).
- **Project:** additions this project makes on top of the paper, such as FX support, the C++
  core and hard limits.

The code is an independent implementation, not a port of the paper's repository.

## 1. Organisation of agents

| ID | Requirement | Source | Status | Where |
|---|---|---|---|---|
| A1 | Fundamentals analyst: financials, valuation, insider activity | Paper | realised | `FundamentalsAnalyst` |
| A2 | Sentiment analyst: social media and public sentiment | Paper | partial: synthetic social posts plus market-based crowding proxies; no live Reddit or StockTwits feed | `SentimentAnalyst`, `MarketDataProvider.social` |
| A3 | News analyst: company and macro news | Paper | realised: headline tone with recency weighting (Yahoo serves recent news only) | `NewsAnalyst` |
| A4 | Technical analyst: MACD, RSI and other indicators | Paper | realised | `TechnicalAnalyst` |
| A5 | Bullish and bearish researchers debating over n rounds | Paper | realised | `BullResearcher`, `BearResearcher`, `run_debate` |
| A6 | Debate facilitator that records the prevailing view as structured data | Paper | realised | `DebateFacilitator` |
| A7 | Trader that synthesises reports and debate into a decision | Paper | realised | `Trader` |
| A8 | Risk team with risk-seeking, neutral and conservative views, in discussion | Paper | realised | `RiskAnalyst`, `run_risk_team` |
| A9 | Fund or portfolio manager that approves or adjusts the final trade | Paper | realised | `PortfolioManager` |
| A10 | FX macro / rates analyst in place of company fundamentals | Project | realised | `MacroAnalyst` |

## 2. Communication and reasoning

| ID | Requirement | Source | Status | Where |
|---|---|---|---|---|
| C1 | Structured documents in a global state, not long message histories | Paper | realised | `state.py`, `reports_digest()` |
| C2 | Natural language only inside debates, stored as structured turns | Paper | realised | `DebateTurn`, `RiskView` |
| C3 | Quick-thinking model for retrieval/summaries, deep-thinking model for reasoning | Paper | realised | `quick_think_llm` / `deep_think_llm` |
| C4 | ReAct-style interleaving of reasoning and tool calls | Paper | partial: tools run deterministically before a single reasoning call per agent; there is no model-driven tool-call loop | `Analyst.run` |
| C5 | Explainable decisions: a natural-language rationale at every step | Paper | realised | `to_markdown()` audit trail |
| C6 | Deterministic rule-based reasoning when no LLM is configured, and as the fallback on any LLM failure | Project | realised; tested with a garbage-emitting model | `Agent.ask_json`, `rules()` |
| C7 | LLM output clipped to valid ranges and validated for required keys | Project | realised; tested | `clip`, `extract_json` |

## 3. Risk and execution controls

| ID | Requirement | Source | Status | Where |
|---|---|---|---|---|
| R1 | Firm limits enforced after any model output: max position, 1-day VaR95, shorting, minimum trade | Project | realised; tested with a model that tries to short an equity | `PortfolioManager.guardrails` |
| R2 | ATR-based stop-loss and take-profit on every directional proposal | Project | realised | `Trader.run` |
| R3 | Volatility-targeted sizing for the neutral view; VaR-capped conservative view | Project | realised | `RiskAnalyst.rules_weight` |
| R4 | Transaction costs, slippage, equity borrow fees and FX carry in backtests | Project | realised; tested | `run_backtest` |
| R5 | Live order execution / broker connectivity | Project | roadmap: out of scope for a research framework | — |

## 4. Data

| ID | Requirement | Source | Status | Where |
|---|---|---|---|---|
| D1 | Historical prices | Paper | realised: Yahoo, CSV, synthetic | `data/` |
| D2 | Point-in-time discipline: no information after the as-of close | Project | realised: provider contract plus a second clip in the graph; tested | `graph.propagate`, `clip_history` |
| D3 | Financial statements and insider transactions | Paper | partial: synthetic quarterly reports with a 30-day lag; Yahoo fundamentals only near today (refused for past dates to avoid leakage) | `SyntheticProvider.fundamentals`, `YahooProvider.fundamentals` |
| D4 | News and social media | Paper | partial: synthetic, Yahoo recent news, CSV news; no historical news vendor | `news`, `social` |
| D5 | Macro inputs for FX (policy rates, inflation) | Project | realised: static config or FRED policy rates | `static_fx_macro`, `YahooProvider._fred_rate` |
| D6 | Deterministic offline dataset | Project | realised: seeded, regime-switching, fat-tailed | `SyntheticProvider` |

## 5. Evaluation

| ID | Requirement | Source | Status | Where |
|---|---|---|---|---|
| E1 | Backtest over Jan–Mar 2024 on large-cap US stocks | Paper | realised | [evaluation/evaluation.md](evaluation/evaluation.md) |
| E2 | Baselines: Buy & Hold, MACD, KDJ+RSI, ZMR, SMA | Paper | realised (C++) | `strategies.cpp`, `baseline_weights` |
| E3 | Metrics: cumulative return, annualised return, Sharpe, max drawdown | Paper | realised, plus volatility, Sortino, Calmar, win rate and trades | `compute_metrics` |
| E4 | Reproduce the paper's LLM results (CR 23–27%, Sharpe 5.6–8.2) | Paper | **roadmap: the LLM mode has not been evaluated.** The measured numbers are rule-based only | — |
| E5 | FX evaluation on the same protocol | Project | realised (rule-based) | [evaluation/evaluation.md](evaluation/evaluation.md) |

## 6. Engineering

| ID | Requirement | Source | Status | Where |
|---|---|---|---|---|
| G1 | C++17 quant core exposed to Python | Project | realised: pybind11 | `cpp/`, `quant/` |
| G2 | Runs without a compiler | Project | realised: numpy twin, selected automatically | `quant/pycore.py` |
| G3 | C++ and numpy backends numerically identical | Project | realised: cross-checked to 1e-9 in CI | `tests/test_quant.py` |
| G4 | CI on Linux, Windows and macOS; Python 3.10–3.14 | Project | realised | `.github/workflows/ci.yml` |
| G5 | Reflection / memory of past decisions | Project | realised; resolution is horizon-gated | `memory.py` |
| G6 | Checkpoint and resume of long runs | Project | roadmap | — |
| G7 | Portfolio-level (multi-asset) allocation | Project | roadmap: decisions are per instrument | — |
