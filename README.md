# AgenticTrader

[![CI](https://github.com/AshJha0/agentic-trader/actions/workflows/ci.yml/badge.svg)](https://github.com/AshJha0/agentic-trader/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-ashjha0.github.io%2Fagentic--trader-16697a)](https://ashjha0.github.io/agentic-trader/)

**Documentation site: https://ashjha0.github.io/agentic-trader/**

| Guide | For |
|---|---|
| [LEARN.md](LEARN.md) | 18 concepts: how the repo implements them, real numbers, questions |
| [COOKBOOK.md](COOKBOOK.md) | 38 copy-pasteable recipes, including real-life workflows |
| [Architecture](docs/architecture/overview.md) · [Diagrams](docs/DIAGRAMS.md) | Components, data flow, design decisions, 16 diagrams |
| [Specification](docs/SPECIFICATION.md) · [Threat model](docs/threat-model/threat-model.md) | Requirements with status; 20 threats mapped to controls and tests |
| [Evaluation](docs/evaluation/evaluation.md) · [API](docs/api/api.md) | Real-price results with a design / holdout split; the full API and CLI reference |

AgenticTrader is a multi-agent LLM trading framework for **equities and FX**. It has a
**C++ quant core** (indicators, backtester with stops and carry, risk) exposed to **Python**
through pybind11.

The design follows *TradingAgents: Multi-Agents LLM Financial Trading Framework*
(Xiao et al., 2024). The code is written from scratch and is not a fork of the TradingAgents
repository.

> Research and education only. This is not investment advice. The synthetic data mode
> produces fake prices, news and fundamentals.

## Results in one paragraph

On **real prices**, the rule-based firm was evaluated over 15 instruments (10 equities, 5 FX
pairs). Rules were chosen on 2016–2021 only and judged once on a 2022–2026 holdout.

- **Per instrument:** it does **not** beat buy & hold on Sharpe out of sample (0.44 vs
  0.55).
- **Drawdown:** it has **about half the drawdown** in every period.
- **As a 15-sleeve portfolio:** it beats plain buy & hold on Sharpe (1.14 vs 1.06, with a
  6.8% vs 20.8% drawdown), but not buy & hold scaled to the same volatility (1.24).
- **LLM mode:** not evaluated, so none of the paper's LLM results are claimed.

Details: [docs/evaluation](docs/evaluation/evaluation.md).

## Architecture

```
                 ┌──────────────── Analyst team (quick-thinking model) ───────────────┐
 market data ──► │ Technical │ Fundamentals (equity) / Macro-rates (FX) │ News │ Sentiment │
 (point-in-time) └───────────────────────────────┬────────────────────────────────────┘
                     structured reports (signal, confidence, key points — or abstain)
                                                 ▼
                       Bull researcher ⇄ Bear researcher   (n debate rounds)
                                                 ▼
                                  Debate facilitator → verdict
                                                 ▼
          Trader → strategic weight + tilt, stop, target, horizon   ◄── current position
                                                 ▼
                 Aggressive ⇄ Neutral ⇄ Conservative risk analysts (m rounds)
                                                 ▼
    Portfolio manager → firm limits (size, VaR, shorting, min trade) → no-trade band
                                                 ▼
                         Decision memory → reflections fed to later runs
```

* **Structured communication.** Agents write typed documents into one shared
  `TradingState` instead of passing around a long chat history. Natural language is only
  used inside the two debates.
* **Two model tiers.** `claude-haiku-4-5` handles the analysts; `claude-opus-5` with
  adaptive thinking handles the researchers, facilitator, trader, risk team and portfolio
  manager.
* **Tools, then rules, then LLM.** Each agent computes facts with the C++ core and forms a
  transparent rule-based judgement. If Claude is enabled, its structured JSON replaces the
  judgement; if the LLM fails, the rules stand. An analyst with no data abstains and makes
  no model call.
* **Contained, capped, bounded.** Third-party text reaches the model only inside
  `<untrusted_data>` blocks that can't be escaped. `max_llm_calls` caps spend. The
  portfolio manager's limits run after any model output.
* **A benchmark, then tilts.** With no view the firm holds a strategic weight (equities
  fully invested, FX flat), and conviction tilts around it. A no-trade band avoids paying
  spread for trivial changes.
* **Point-in-time data.** Prices are clipped twice. FX macro comes from FRED as known on
  each date (publication-lagged, staleness-checked). Stale feeds are refused, and memory
  outcomes become visible only after their horizon.

### Equity vs FX

| | Equity | FX |
|---|---|---|
| Value analyst | Fundamentals: P/E vs sector, growth, margins, leverage, FCF, EPS surprise, insiders | Macro: point-in-time policy-rate differential (carry), inflation (PPP), distance from the 200-day average |
| News scoring | Headline tone | Tone oriented to base vs quote ("JPY weakens" is bullish for USD/JPY) |
| Strategic weight | 1.0 | 0.0 |
| Shorting | Off by default (`allow_short_equity`) | On |
| Costs | Commission + slippage bps, borrow fee on shorts | Half-spread in pips converted to bps, plus per-bar carry |
| Periods per year | 252 | 260 |

## Layout

```
cpp/include/at/*.hpp     C++ API: indicators, backtest (stops, carry), risk, strategies
cpp/src/*.cpp            implementation
cpp/bindings/module.cpp  pybind11 module -> agentic_trader/quant/_atcore
cpp/apps/at_backtest.cpp standalone C++ CLI: baselines on a CSV
cpp/tests/test_core.cpp  C++ unit tests (ctest)
agentic_trader/
  quant/                 facade: C++ if built, otherwise pycore.py (numpy mirror)
  data/                  synthetic | yahoo | csv providers, clean_ohlcv, fred.py (point-in-time macro)
  agents/                analysts, researchers + facilitator, trader, risk team + PM
  graph.py               TradingGraph.propagate() and scan()
  backtest.py            walk-forward agent backtest vs 6 baselines; portfolio backtest
  evaluation.py          design / holdout / paper-window evaluation harness
  memory.py              decision log + reflection (atomic, corruption-tolerant)
  llm.py                 Claude client, call budget, offline mode
  cli.py                 `agentic-trader` command
tests/                   116 pytest tests (quant edges, data, agents, workflows, CLI, cross-checks)
examples/                equity, FX, baseline comparison
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (source .venv/bin/activate on Linux/macOS)
pip install -e ".[all]"
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

The build does four things:

* compiles `agentic_trader/quant/_atcore.*`
* builds `build/at_backtest`
* builds and runs the C++ tests
* prints `quant backend: cpp`

Without the build, everything still runs on the numpy fallback, which uses identical
formulas. Set `AGENTIC_TRADER_BACKEND=python` to force the fallback.

## Usage

Offline mode needs no API key or network, so every command below runs as-is:

```bash
agentic-trader analyze   AAPL --date 2024-03-01 --position 0.4
agentic-trader scan      AAPL,NVDA,EURUSD --date 2024-03-01 --positions '{"AAPL": 0.5}' --out orders.csv
agentic-trader backtest  NVDA --start 2024-01-02 --end 2024-03-28 --stops on
agentic-trader baselines USDJPY --start 2023-01-02 --end 2023-12-29 --out curves.csv
agentic-trader portfolio AAPL,JPM,XOM,EURUSD,USDJPY --start 2023-01-02 --end 2023-12-29
agentic-trader evaluate  AAPL,EURUSD --periods paper
```

With real prices (network) and Claude (API key):

```bash
agentic-trader evaluate --data yahoo --periods design,holdout,paper      # the published protocol
set ANTHROPIC_API_KEY=...                                               # or `ant auth login`
agentic-trader analyze MSFT --llm anthropic --data yahoo --max-llm-calls 50
```

From Python:

```python
from agentic_trader import TradingGraph, make_config, run_agent_backtest, run_portfolio_backtest

graph = TradingGraph(make_config(llm_provider="anthropic", data_provider="yahoo", max_llm_calls=100))
state, decision = graph.propagate("EURUSD", "2025-06-02", current_weight=0.2)
print(state.to_markdown())          # full audit trail: reports, debate, proposal, risk, decision

rep = run_agent_backtest("AAPL", "2024-01-02", "2024-03-28", make_config())
print(rep.table())                  # CR, AR, Vol, Sharpe, t(SR), Sortino, MDD, Calmar, Win, Exp, Trades, Stops

port = run_portfolio_backtest(["AAPL", "JPM", "EURUSD"], "2023-01-02", "2023-12-29", make_config())
print(port.table())
```

Standalone C++ baselines on any OHLC CSV:

```bash
build/Release/at_backtest prices.csv --fx --carry 0.02
```

## Configuration highlights (`config.py`)

| key | meaning |
|---|---|
| `llm_provider` | `offline` or `anthropic` |
| `deep_think_llm` / `quick_think_llm` | Model IDs for each tier |
| `deep_effort` / `quick_effort` | Adaptive-thinking effort level |
| `llm_timeout_s` / `max_llm_calls` | Request timeout; hard cap on calls per graph |
| `use_refusal_fallback` | Server-side refusal fallback on Opus 5 (beta); on by default |
| `max_debate_rounds` / `max_risk_discuss_rounds` | Number of debate rounds |
| `analysts` | Subset or order of analysts; `None` uses the asset-class default |
| `rules.*` | Research switches (momentum, trend-filtered reversal, abstention); off by default, see the evaluation |
| `risk.neutral_weight` | Strategic weight held with no view (equity 1.0, FX 0.0) |
| `risk.rebalance_band` | No-trade band around the current position (0.10) |
| `risk.*` | Position cap, vol target, VaR cap, shorting, ATR stop multiples |
| `backtest.use_stops` | Enforce stops and targets intraday in backtests |
| `costs.*` | Equity bps and borrow; FX spread in pips |
| `fx_macro_source` | `auto`: static table for synthetic data, point-in-time FRED for real data |
| `max_data_staleness_days` | Refuse to decide on a feed older than this (7) |

`make_config(RULES_V02)` reproduces the v0.2 rules for before/after comparisons.

## Extending

* **New data source** (Reddit, StockTwits, a paid news API): subclass `MarketDataProvider`,
  pass prices through `clean_ohlcv`, and only return data available at `as_of`.
* **New analyst:** subclass `Analyst` with `gather()` and `rules()`, list free-text keys in
  `untrusted_keys`, return `self.abstain(...)` without data, then register it in
  `ANALYSTS`.
* **New rule:** put it behind a `config["rules"]` switch, choose it on the design period with
  `evaluate`, then judge it once on the holdout.
* **New quant routine:** add it to `cpp/`, bind it in `module.cpp`, mirror it in `pycore.py`
  and add a cross-check test.

## Tests

```bash
pytest -q                                   # 116 tests; C++ cross-checks run when the extension is built
AGENTIC_TRADER_BACKEND=python pytest -q     # the numpy fallback
ctest --test-dir build -C Release           # 13 C++ test groups
```
