# AgenticTrader

AgenticTrader is a multi-agent LLM trading framework for **equities and FX**. It has a
**C++ quant core** (indicators, backtester, risk) exposed to **Python** through pybind11.

The design follows *TradingAgents: Multi-Agents LLM Financial Trading Framework*
(Xiao et al., 2024). The code is written from scratch and is not a fork of the TradingAgents
repository.

> Research and education only. This is not investment advice. The synthetic data mode
> produces fake prices, news and fundamentals.

## Architecture

```
                 ┌──────────────── Analyst team (quick-thinking model) ───────────────┐
 market data ──► │ Technical │ Fundamentals (equity) / Macro-rates (FX) │ News │ Sentiment │
                 └───────────────────────────────┬────────────────────────────────────┘
                                   structured reports (signal, confidence, key points)
                                                 ▼
                       Bull researcher ⇄ Bear researcher   (n debate rounds)
                                                 ▼
                                  Debate facilitator → verdict
                                                 ▼
                          Trader → proposal (weight, stop, target, horizon)
                                                 ▼
                 Aggressive ⇄ Neutral ⇄ Conservative risk analysts (m rounds)
                                                 ▼
               Portfolio manager → final decision + hard limits (VaR, size, shorting)
                                                 ▼
                         Decision memory → reflections fed to later runs
```

* **Structured communication.** Agents write typed documents into one shared
  `TradingState` (see `state.py`) instead of passing around a long chat history.
  Natural language is only used inside the two debates.
* **Two model tiers.** The quick model (`claude-haiku-4-5`) handles the analysts. The
  deep model (`claude-opus-5`, adaptive thinking) handles the researchers, facilitator,
  trader, risk team and portfolio manager.
* **Tools, then rules, then LLM.** Each agent first computes facts with deterministic
  tools (the C++ core). It then forms a transparent rule-based judgement. When an LLM is
  enabled, the model reasons over the same facts and its structured JSON replaces the
  rules. If the LLM fails for any reason, the rule-based output is used instead.
* **Hard limits run after the LLM.** The portfolio manager's position cap, 1-day VaR95
  cap, shorting policy and minimum trade size cannot be overridden by model output.
* **Point-in-time data.** Providers only return information available at the as-of close,
  and the graph clips price history a second time. Memory outcomes become visible only
  after their horizon has elapsed.

### Equity vs FX

| | Equity | FX |
|---|---|---|
| Value analyst | Fundamentals: P/E vs sector, growth, margins, leverage, FCF, EPS surprise, insiders | Macro: policy-rate differential (carry), inflation differential (PPP), distance from the 200-day average |
| News scoring | Headline tone | Tone oriented to base vs quote ("JPY weakens" is bullish for USD/JPY) |
| Shorting | Off by default (`allow_short_equity`) | On |
| Costs | Commission + slippage bps, borrow fee on shorts | Half-spread in pips converted to bps, plus carry accrual |
| Periods per year | 252 | 260 |

## Layout

```
cpp/include/at/*.hpp     C++ API: indicators, backtest, risk, strategies
cpp/src/*.cpp            implementation
cpp/bindings/module.cpp  pybind11 module -> agentic_trader/quant/_atcore
cpp/apps/at_backtest.cpp standalone C++ CLI: baselines on a CSV
cpp/tests/test_core.cpp  C++ unit tests (ctest)
agentic_trader/
  quant/                 facade: C++ if built, otherwise pycore.py (numpy mirror)
  data/                  synthetic | yahoo (yfinance + FRED) | csv providers
  agents/                analysts, researchers + facilitator, trader, risk team + PM
  graph.py               TradingGraph.propagate()
  backtest.py            walk-forward agent backtest vs B&H, MACD, KDJ+RSI, ZMR, SMA
  memory.py              decision log + reflection
  llm.py                 Claude client (Anthropic SDK) / offline mode
  cli.py                 `agentic-trader` command
tests/                   pytest suite (includes C++ vs Python cross-checks)
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
agentic-trader analyze AAPL --date 2024-03-01
agentic-trader analyze EURUSD --date 2024-03-01 --rounds 2 --save
agentic-trader backtest NVDA  --start 2024-01-01 --end 2024-03-29 --every 5
agentic-trader baselines USDJPY --start 2023-01-01 --end 2023-12-31 --out curves.csv
```

For live mode, use Claude with real prices:

```bash
set ANTHROPIC_API_KEY=...          # or `ant auth login`
agentic-trader analyze MSFT --llm anthropic --data yahoo
agentic-trader analyze GBPUSD --llm anthropic --data yahoo --deep-model claude-opus-5
```

From Python:

```python
from agentic_trader import TradingGraph, make_config, run_agent_backtest

cfg = make_config(llm_provider="anthropic", data_provider="yahoo", max_debate_rounds=2)
state, decision = TradingGraph(cfg).propagate("EURUSD", "2025-06-02")
print(state.to_markdown())          # full audit trail: reports, debate, proposal, risk, decision

rep = run_agent_backtest("AAPL", "2024-01-02", "2024-03-29", make_config(), rebalance_every=5)
print(rep.table())                  # CR%, AR%, Vol%, Sharpe, Sortino, MDD%, Calmar, Win%, Trades
```

Standalone C++ baselines on any OHLC CSV:

```bash
build/Release/at_backtest prices.csv --fx --carry 0.02
```

## Configuration highlights (`config.py`)

| key | meaning |
|---|---|
| `llm_provider` | `offline` or `anthropic` |
| `deep_think_llm` / `quick_think_llm` | model IDs for each tier |
| `deep_effort` / `quick_effort` | adaptive-thinking effort level |
| `use_refusal_fallback` | server-side refusal fallback on Opus 5 (beta); on by default |
| `max_debate_rounds` / `max_risk_discuss_rounds` | number of debate rounds |
| `analysts` | subset or order of analysts; `None` uses the asset-class default |
| `risk.*` | position cap, vol target, VaR cap, shorting, ATR stop multiples |
| `costs.*` | equity bps and borrow; FX spread in pips |
| `fx_policy_rates` / `fx_inflation` | illustrative macro inputs; update them or set `fx_macro_source="fred"` |

## Extending

* **New data source** (for example Reddit or StockTwits, or a paid news API): subclass
  `MarketDataProvider` and implement `history`, `news`, `social`, `fundamentals` and
  `macro`. Only return data available at `as_of`.
* **New analyst:** subclass `Analyst` with `gather()` (tools) and `rules()`, then register
  it in `ANALYSTS`.
* **New quant routine:** add it to `cpp/`, bind it in `module.cpp`, mirror it in `pycore.py`
  and add it to the cross-check test.

## Tests

```bash
pytest -q
ctest --test-dir build -C Release
```
