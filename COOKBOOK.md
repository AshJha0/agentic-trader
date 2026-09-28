# Cookbook

Copy-pasteable recipes. Unless marked *(network)* or *(API key)*, every recipe runs offline
on synthetic data and is executed as-is when the docs are checked.

- [Decisions](#decisions)
  1. [Get one decision](#1-get-one-decision)
  2. [Read the full audit trail](#2-read-the-full-audit-trail)
  3. [Decide on an FX pair](#3-decide-on-an-fx-pair)
  4. [Stream progress events](#4-stream-progress-events)
  5. [Change the debate length and choose analysts](#5-change-the-debate-length-and-choose-analysts)
  6. [Tighten the firm's risk limits](#6-tighten-the-firms-risk-limits)
  7. [Allow shorting equities](#7-allow-shorting-equities)
  8. [Save a Markdown report](#8-save-a-markdown-report)
- [Backtests](#backtests)
  9. [Backtest against the classic baselines](#9-backtest-against-the-classic-baselines)
  10. [Baselines only](#10-baselines-only)
  11. [Export and compare equity curves](#11-export-and-compare-equity-curves)
  12. [Backtest your own weights with the C++ engine](#12-backtest-your-own-weights-with-the-c-engine)
  13. [Model FX costs and carry explicitly](#13-model-fx-costs-and-carry-explicitly)
- [Quant core](#quant-core)
  14. [Indicators](#14-indicators)
  15. [Risk numbers](#15-risk-numbers)
  16. [Check which backend is running](#16-check-which-backend-is-running)
- [LLMs](#llms)
  17. [Count LLM calls](#17-count-llm-calls)
  18. [Plug in your own model](#18-plug-in-your-own-model)
  19. [Use Claude](#19-use-claude)
- [Data](#data)
  20. [Use real prices](#20-use-real-prices)
  21. [Use your own CSV files](#21-use-your-own-csv-files)
  22. [Write a custom data provider](#22-write-a-custom-data-provider)
- [Extending](#extending)
  23. [Add a custom analyst](#23-add-a-custom-analyst)
  24. [Persist memory across runs](#24-persist-memory-across-runs)
  25. [C++ baselines from the command line](#25-c-baselines-from-the-command-line)
- [Real-life workflows](#real-life-workflows)
  26. [Tell the firm what you already hold](#26-tell-the-firm-what-you-already-hold)
  27. [Morning run over a watchlist](#27-morning-run-over-a-watchlist)
  28. [Compare two rule sets on the same data](#28-compare-two-rule-sets-on-the-same-data)
  29. [Choose the strategic (benchmark) weight](#29-choose-the-strategic-benchmark-weight)
  30. [Enforce stop-loss and take-profit in a backtest](#30-enforce-stop-loss-and-take-profit-in-a-backtest)
  31. [Backtest a multi-asset portfolio](#31-backtest-a-multi-asset-portfolio)
  32. [Evaluate on your own universe and periods](#32-evaluate-on-your-own-universe-and-periods)
  33. [Judge a result: t-stat and the vol-targeted control](#33-judge-a-result-t-stat-and-the-vol-targeted-control)
  34. [Stress the cost assumptions](#34-stress-the-cost-assumptions)
  35. [Point-in-time FX carry from FRED](#35-point-in-time-fx-carry-from-fred)
  36. [Cap LLM spend](#36-cap-llm-spend)
  37. [Clean messy price files](#37-clean-messy-price-files)
  38. [Fail safely on bad input](#38-fail-safely-on-bad-input)
- [The agentic layer](#the-agentic-layer)
  39. [Run a task through the harness](#39-run-a-task-through-the-harness)
  40. [Read the evidence behind a decision](#40-read-the-evidence-behind-a-decision)
  41. [Call a tool directly, under policy](#41-call-a-tool-directly-under-policy)
  42. [Queue an order for human approval](#42-queue-an-order-for-human-approval)
  43. [Write a policy rule](#43-write-a-policy-rule)
  44. [Validate a model-proposed plan](#44-validate-a-model-proposed-plan)
  45. [Add a tool to the catalogue](#45-add-a-tool-to-the-catalogue)
  46. [Search the desk's knowledge base](#46-search-the-desks-knowledge-base)
  47. [Audit a narrative](#47-audit-a-narrative)
  48. [Serve the HTTP API and drive it](#48-serve-the-http-api-and-drive-it)
  49. [Expose the tools over MCP and consume them](#49-expose-the-tools-over-mcp-and-consume-them)
  50. [Trace a run and export metrics](#50-trace-a-run-and-export-metrics)
- [Quant research](#quant-research)
  51. [Evaluate the alpha library](#51-evaluate-the-alpha-library)
  52. [Add an alpha and use the alpha analyst](#52-add-an-alpha-and-use-the-alpha-analyst)
  53. [Plan and simulate an execution](#53-plan-and-simulate-an-execution)
  54. [Compare execution algorithms on the same day](#54-compare-execution-algorithms-on-the-same-day)
  55. [Construct a portfolio and read its risk](#55-construct-a-portfolio-and-read-its-risk)
  56. [Deflate a Sharpe ratio after a search](#56-deflate-a-sharpe-ratio-after-a-search)
- [v0.5: execution-aware evaluation, cross-sectional research, operations](#v05-execution-aware-evaluation-cross-sectional-research-operations)
  57. [Backtest with market impact at three account sizes](#57-backtest-with-market-impact-at-three-account-sizes)
  58. [Cross-sectional alpha report over a universe](#58-cross-sectional-alpha-report-over-a-universe)
  59. [Risk budgets across asset classes](#59-risk-budgets-across-asset-classes)
  60. [Read inflation as first published (ALFRED vintages)](#60-read-inflation-as-first-published-alfred-vintages)
  61. [Cap the LLM bill in dollars](#61-cap-the-llm-bill-in-dollars)
  62. [Keep tasks across restarts](#62-keep-tasks-across-restarts)
  63. [Serve with TLS and real API keys](#63-serve-with-tls-and-real-api-keys)
  64. [Evaluate the extended universe and the reserve period](#64-evaluate-the-extended-universe-and-the-reserve-period)
- [v0.6: point-in-time filings, statistical power, calibration, operations](#v06-point-in-time-filings-statistical-power-calibration-operations)
  65. [Point-in-time fundamentals and filing news from SEC EDGAR](#65-point-in-time-fundamentals-and-filing-news-from-sec-edgar)
  66. [Rank a name against its peers: the cross-sectional analyst](#66-rank-a-name-against-its-peers-the-cross-sectional-analyst)
  67. [Is the edge real across instruments? The paired bootstrap](#67-is-the-edge-real-across-instruments-the-paired-bootstrap)
  68. [Measure the model's own variance with repeated runs](#68-measure-the-models-own-variance-with-repeated-runs)
  69. [Calibrate the desk: dispersion, anchoring, drift](#69-calibrate-the-desk-dispersion-anchoring-drift)
  70. [Pin the prompts: the registry hash](#70-pin-the-prompts-the-registry-hash)
  71. [Serve with a bounded task pool and several processes](#71-serve-with-a-bounded-task-pool-and-several-processes)
  72. [Check the docs the way CI does](#72-check-the-docs-the-way-ci-does)

## Decisions

### 1. Get one decision

```python
from agentic_trader import TradingGraph, make_config
from agentic_trader.memory import DecisionMemory

graph = TradingGraph(make_config(), memory=DecisionMemory(None), on_event=lambda *_: None)
state, decision = graph.propagate("AAPL", "2024-03-01")
print(decision.action.value, decision.target_weight, decision.stop_loss)
```

### 2. Read the full audit trail

```python
from agentic_trader import TradingGraph, make_config
from agentic_trader.memory import DecisionMemory

state, _ = TradingGraph(make_config(), memory=DecisionMemory(None),
                        on_event=lambda *_: None).propagate("MSFT", "2024-02-15")
for r in state.reports.values():
    print(f"{r.analyst:<12} {r.signal:+.2f} ({r.confidence:.2f}) {r.summary}")
print("debate:", state.debate.winner, f"{state.debate.score:+.2f}")
for turn in state.debate.turns:
    print(f"  {turn.speaker} r{turn.round}: {turn.argument[:90]}...")
print(state.to_markdown()[:500])
```

### 3. Decide on an FX pair

Equity and FX use the same call. FX pairs automatically get the macro analyst, shorting,
pip-based costs and carry.

```python
from agentic_trader import TradingGraph, make_config, Instrument
from agentic_trader.memory import DecisionMemory

ins = Instrument.parse("USD/JPY")
print(ins.asset_class, ins.base, ins.quote, ins.pip_size)       # fx USD JPY 0.01
state, d = TradingGraph(make_config(), memory=DecisionMemory(None),
                        on_event=lambda *_: None).propagate(ins, "2024-03-01")
print(state.reports["macro"].key_points[0])
print(d.action.value, d.target_weight)
```

### 4. Stream progress events

```python
from agentic_trader import TradingGraph, make_config
from agentic_trader.memory import DecisionMemory

def show(stage, message):
    print(f"[{stage}] {message}")

TradingGraph(make_config(), memory=DecisionMemory(None), on_event=show).propagate("NVDA", "2024-03-01")
```

### 5. Change the debate length and choose analysts

```python
from agentic_trader import TradingGraph, make_config
from agentic_trader.memory import DecisionMemory

cfg = make_config(max_debate_rounds=3, max_risk_discuss_rounds=2,
                  analysts=["technical", "news"])
state, _ = TradingGraph(cfg, memory=DecisionMemory(None), on_event=lambda *_: None).propagate("GOOGL", "2024-03-01")
print(sorted(state.reports), len(state.debate.turns), len(state.risk_views))   # ['news', 'technical'] 6 6
```

### 6. Tighten the firm's risk limits

The limits run after any model output, so they hold even with an LLM.

```python
from agentic_trader import TradingGraph, make_config
from agentic_trader.memory import DecisionMemory

cfg = make_config(risk={"max_position": 0.25, "max_var_95": 0.005, "min_trade_weight": 0.02})
_, d = TradingGraph(cfg, memory=DecisionMemory(None), on_event=lambda *_: None).propagate("AAPL", "2024-03-01")
print(d.target_weight, d.adjustments)
```

### 7. Allow shorting equities

```python
from agentic_trader import make_config

cfg = make_config(risk={"allow_short_equity": True}, costs={"equity_borrow_annual": 0.02})
print(cfg["risk"]["allow_short_equity"], cfg["risk"]["max_position"])   # other keys are kept
```

### 8. Save a Markdown report

```bash
agentic-trader analyze AAPL --date 2024-03-01 --save --no-memory
# -> results/AAPL/2024-03-01/report.md
```

## Backtests

### 9. Backtest against the classic baselines

```python
from agentic_trader import run_agent_backtest, make_config

rep = run_agent_backtest("NVDA", "2024-01-02", "2024-03-28", make_config(), rebalance_every=5)
print(rep.table()[["CR%", "Sharpe", "MDD%", "Trades"]])
print(len(rep.decisions), "agent decisions")
```

### 10. Baselines only

This runs in milliseconds because there are no agents.

```python
from agentic_trader import run_agent_backtest, make_config

rep = run_agent_backtest("EURUSD", "2023-01-02", "2023-12-29", make_config(), include_agent=False)
print(rep.table())
```

### 11. Export and compare equity curves

```python
from agentic_trader import run_agent_backtest, make_config

rep = run_agent_backtest("MSFT", "2024-01-02", "2024-03-28", make_config(), rebalance_every=5)
curves = rep.equity_curves()
curves.to_csv("msft_curves.csv")
print((curves.iloc[-1] / curves.iloc[0] - 1).sort_values(ascending=False))
```

### 12. Backtest your own weights with the C++ engine

```python
import numpy as np
from agentic_trader import quant

prices = 100 * np.cumprod(1 + np.random.default_rng(0).normal(0.0005, 0.01, 250))
fast, slow = quant.sma(prices, 10), quant.sma(prices, 30)
weights = np.where(fast > slow, 1.0, 0.0)          # NaN warm-up compares False -> flat
cfg = quant.BacktestConfig(cost_bps=2.0, slippage_bps=1.0, allow_short=False)
res = quant.run_backtest(prices, weights, cfg)
m = res.metrics
print(f"CR {m.cumulative_return:.2%}  Sharpe {m.sharpe:.2f}  MDD {m.max_drawdown:.2%}  trades {m.num_trades}")
```

### 13. Model FX costs and carry explicitly

```python
import numpy as np
from agentic_trader import quant, Instrument

ins = Instrument.parse("AUDUSD")
prices = np.linspace(0.66, 0.67, 130)
half_spread_bps = 0.8 * ins.pip_size / prices.mean() * 1e4 / 2   # 0.8-pip spread
cfg = quant.BacktestConfig(cost_bps=half_spread_bps, carry_annual=(3.60 - 4.25) / 100,
                           periods_per_year=ins.periods_per_year, allow_short=True)
res = quant.run_backtest(prices, np.ones(len(prices)), cfg)
print(f"{half_spread_bps:.3f} bps per unit turnover, CR {res.metrics.cumulative_return:.3%}")
```

## Quant core

### 14. Indicators

```python
import numpy as np
from agentic_trader import quant

rng = np.random.default_rng(1)
close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 300)))
high, low = close * 1.005, close * 0.995
line, signal, hist = quant.macd(close)
mid, upper, lower, pct_b = quant.bollinger(close, 20, 2.0)
k, d, j = quant.kdj(high, low, close, 9)
print(round(quant.rsi(close)[-1], 1), round(quant.atr(high, low, close)[-1], 3), round(pct_b[-1], 2))
```

### 15. Risk numbers

```python
import numpy as np
from agentic_trader import quant

r = np.random.default_rng(2).normal(0, 0.012, 500)
print("VaR95", round(quant.historical_var(r, 0.95), 4), "CVaR95", round(quant.historical_cvar(r, 0.95), 4))
print("kelly", quant.kelly_fraction(0.55, 1.2))
print("vol-target weight", quant.vol_target_weight(1.0, 0.30, 0.15, 1.0))     # 0.5
print("units for 1% risk", quant.position_units(100_000, 0.01, 50.0, 48.0))     # 500.0
```

### 16. Check which backend is running

```python
from agentic_trader import quant
print(quant.BACKEND)   # "cpp" once scripts/build_cpp.* has run, else "python"
```

Set `AGENTIC_TRADER_BACKEND=python` before import to force the numpy twin.

## LLMs

### 17. Count LLM calls

A recording stub shows exactly which calls a real model would receive and which tier each
would use.

```python
from agentic_trader import TradingGraph, make_config
from agentic_trader.memory import DecisionMemory

class Recorder:
    def __init__(self):
        self.calls = []
    def complete(self, system, prompt, *, deep):
        self.calls.append(("deep" if deep else "quick", system.split("Your role: ")[-1][:30]))
        return None          # None -> every agent falls back to its rules

rec = Recorder()
TradingGraph(make_config(), llm=rec, memory=DecisionMemory(None), on_event=lambda *_: None).propagate("AAPL", "2024-03-01")
print(len(rec.calls), sum(t == "quick" for t, _ in rec.calls), sum(t == "deep" for t, _ in rec.calls))  # 14 4 10
```

### 18. Plug in your own model

Any object with `complete(system, prompt, *, deep) -> str | None` works. Return JSON for
the structured agents and prose for the researchers; return `None` to fall back to the
rules.

```python
import json
from agentic_trader import TradingGraph, make_config
from agentic_trader.memory import DecisionMemory

class AlwaysCautious:
    def complete(self, system, prompt, *, deep):
        if "Portfolio Manager" in system:
            return json.dumps({"target_weight": 0.1, "confidence": 0.4, "rationale": "Small size."})
        return None

_, d = TradingGraph(make_config(), llm=AlwaysCautious(), memory=DecisionMemory(None),
                    on_event=lambda *_: None).propagate("AAPL", "2024-03-01")
print(d.source, d.target_weight)          # llm 0.1
```

### 19. Use Claude

*(API key)*

```bash
pip install -e ".[llm]"
export ANTHROPIC_API_KEY=...            # or: ant auth login
agentic-trader analyze MSFT --date 2024-03-01 --llm anthropic
agentic-trader analyze EURUSD --llm anthropic --data yahoo --deep-model claude-opus-5 --rounds 1
```

In Python, use `make_config(llm_provider="anthropic", deep_effort="medium")`. Each decision
costs 14 calls at default rounds, so start with `--rounds 1` for backtests.

## Data

### 20. Use real prices

*(network)*

```bash
pip install -e ".[data]"
agentic-trader backtest NVDA --data yahoo --start 2024-01-02 --end 2024-03-28 --every 5
```

### 21. Use your own CSV files

```python
import os
import tempfile
from agentic_trader import TradingGraph, make_config
from agentic_trader.data import SyntheticProvider
from agentic_trader.instruments import Instrument
from agentic_trader.memory import DecisionMemory
from datetime import date

folder = tempfile.mkdtemp()
ins = Instrument.parse("TSLA")
SyntheticProvider(make_config()).history(ins, date(2023, 1, 1), date(2024, 3, 1)).to_csv(
    os.path.join(folder, "TSLA.csv"), index_label="Date")
with open(os.path.join(folder, "TSLA_news.csv"), "w") as f:
    f.write("Date,Headline\n2024-02-28,TSLA beats estimates on record deliveries\n")

cfg = make_config(data_provider="csv", csv_dir=folder)
state, d = TradingGraph(cfg, memory=DecisionMemory(None), on_event=lambda *_: None).propagate("TSLA", "2024-03-01")
print(state.reports["news"].summary, d.action.value)
```

### 22. Write a custom data provider

```python
from datetime import date
from agentic_trader import TradingGraph, make_config
from agentic_trader.data import SyntheticProvider, NewsItem
from agentic_trader.memory import DecisionMemory

class WithMyNews(SyntheticProvider):
    """Synthetic prices plus an in-house news feed (only items known by as_of)."""
    FEED = [NewsItem(date(2024, 2, 29), "AAPL downgraded on weak demand", "MyDesk")]
    def news(self, instrument, as_of, lookback_days):
        return [n for n in self.FEED if n.published <= as_of]

state, _ = TradingGraph(make_config(), provider=WithMyNews(make_config()), memory=DecisionMemory(None),
                        on_event=lambda *_: None).propagate("AAPL", "2024-03-01")
print(state.reports["news"].signal < 0)   # True
```

## Extending

### 23. Add a custom analyst

```python
from agentic_trader import TradingGraph, make_config
from agentic_trader.agents import ANALYSTS
from agentic_trader.agents.analysts import Analyst
from agentic_trader.memory import DecisionMemory
from agentic_trader.state import AnalystReport

class SeasonalityAnalyst(Analyst):
    name = "seasonality"
    role = "Seasonality Analyst. You judge calendar effects."
    instructions = "Weigh month-of-year effects."

    def gather(self, state, provider):
        return {"month": state.as_of.month}

    def rules(self, facts, state):
        sig = 0.2 if facts["month"] in (11, 12, 1) else 0.0
        return AnalystReport(self.name, sig, 0.3, f"Month {facts['month']} seasonal bias {sig:+.1f}.", [], facts)

ANALYSTS["seasonality"] = SeasonalityAnalyst
cfg = make_config(analysts=["technical", "seasonality"], analyst_weights={"seasonality": 0.3})
state, _ = TradingGraph(cfg, memory=DecisionMemory(None), on_event=lambda *_: None).propagate("AAPL", "2024-01-15")
print(state.reports["seasonality"].summary)
```

### 24. Persist memory across runs

An entry is valued only by the provider and price basis that recorded it, on the history
the desk holds, from its entry bar to the bar `horizon_days` trading days later, and only
when the decision day sat within the desk's `max_data_staleness_days` of its entry bar
(`DecisionMemory(path, max_staleness_days=7)`; `TradingGraph` passes its own setting to
the memory it builds and to every `resolve`). An entry the series cannot value expires
without a verdict after twice its horizon; entries written before v0.8 carry no provider,
are never valued, and are expired by any named provider's visit.

```python
import os
import tempfile
from agentic_trader import TradingGraph, make_config

path = os.path.join(tempfile.mkdtemp(), "memory.jsonl")
g = TradingGraph(make_config(memory_path=path), on_event=lambda *_: None)
for day in ["2024-01-02", "2024-01-16", "2024-01-30", "2024-02-13"]:
    g.propagate("AAPL", day)
state, _ = g.propagate("AAPL", "2024-02-27")
print(len(state.lessons), state.track_record)
print(state.lessons[-1][:120])
```

### 25. C++ baselines from the command line

After `scripts/build_cpp.*`:

```bash
build/Release/at_backtest prices.csv            # Windows (MSVC); Linux/macOS: build/at_backtest
build/Release/at_backtest fx.csv --fx --carry 0.0375 --cost-bps 0.3
```

## Real-life workflows

### 26. Tell the firm what you already hold

Pass the current position. The trader and the portfolio manager see it. The no-trade band
(`risk.rebalance_band`, 0.10 by default) keeps the position when the new target is close,
so you don't pay spread for trivial changes. The band only applies if the position still
passes every firm limit today.

```python
from agentic_trader import TradingGraph, make_config
from agentic_trader.memory import DecisionMemory

g = TradingGraph(make_config(), memory=DecisionMemory(None), on_event=lambda *_: None)
_, fresh = g.propagate("AAPL", "2024-03-01")                      # no position: +0.5354
_, held = g.propagate("AAPL", "2024-03-01", current_weight=0.50)  # within 0.10 of the target
print(fresh.target_weight, held.target_weight, held.adjustments)
# 0.5354 0.5 ['within no-trade band (0.04 < 0.10): keep +0.50']
```

### 27. Morning run over a watchlist

One call decides every symbol. A bad ticker becomes an `ERROR` row instead of stopping the
run, and the result is a DataFrame ready for an order-management system.

```python
from agentic_trader import TradingGraph, make_config
from agentic_trader.memory import DecisionMemory

g = TradingGraph(make_config(), memory=DecisionMemory(None), on_event=lambda *_: None)
df = g.scan(["AAPL", "NVDA", "EURUSD", "USD/XYZ"], "2024-03-01", positions={"AAPL": 0.5})
print(df[["symbol", "action", "target_weight", "stop_loss", "error"]].to_string(index=False))
orders = df[(df.action != "ERROR")]
orders.to_csv("orders.csv", index=False)
```

From the command line:

```bash
agentic-trader scan AAPL,NVDA,EURUSD --date 2024-03-01 --positions '{"AAPL": 0.5}' --out orders.json
```

### 28. Compare two rule sets on the same data

Any config difference can be measured this way. `RULES_V02` reproduces the v0.2 rules
exactly.

```python
from agentic_trader import make_config, run_agent_backtest
from agentic_trader.config import RULES_V02

variants = {
    "v0.2": make_config(RULES_V02),
    "v0.3 default": make_config(),
    "v0.3 + momentum": make_config(rules={"tsmom": True}),
}
for name, cfg in variants.items():
    t = run_agent_backtest("MSFT", "2023-01-02", "2023-12-29", cfg).table()
    a = t.loc["AgenticTrader"]
    print(f"{name:<16} Sharpe {a['Sharpe']:5.2f}  t {a['t(SR)']:5.2f}  CR {a['CR%']:6.2f}%  trades {a['Trades']:.0f}")
```

Choose rule changes on a *design* period and judge them once on a *holdout* (recipe 32).
Comparing many variants on the same window you report is how backtests overfit.

### 29. Choose the strategic (benchmark) weight

With no directional view the trader holds `risk.neutral_weight` for the asset class, and
conviction tilts around it. The defaults are equities 1.0 (fully invested, collecting the
equity premium) and, for FX, the carry weight `clip(rate_diff% / 2, ±0.5)` from the
point-in-time rate differential (`rules.fx_carry_neutral`, v0.5.1; `RULES_V03` turns it off,
leaving FX flat). Use 0 for an absolute-return mandate that should sit in cash without a view.

```python
from agentic_trader import TradingGraph, make_config
from agentic_trader.memory import DecisionMemory

for neutral in (0.0, 0.5, 1.0):
    cfg = make_config(risk={"neutral_weight": {"equity": neutral}}, decision_threshold=5.0)  # force "no view"
    _, d = TradingGraph(cfg, memory=DecisionMemory(None), on_event=lambda *_: None).propagate("JPM", "2024-03-01")
    print(neutral, d.target_weight)   # the benchmark weight, after vol-targeting and VaR limits
```

### 30. Enforce stop-loss and take-profit in a backtest

The engine closes a position inside the bar when its stop or target trades. It fills at the
level, or at the open when the market gaps through it. If both levels trade in the same bar,
it assumes the stop filled first. The position stays flat until the next rebalance.

```python
from agentic_trader import make_config, run_agent_backtest

cfg = make_config(backtest={"use_stops": True})
rep = run_agent_backtest("NVDA", "2023-01-02", "2023-12-29", cfg)
print(rep.table().loc[["AgenticTrader", "Buy&Hold"], ["CR%", "Sharpe", "MDD%", "Trades", "Stops"]])
```

`agentic-trader backtest NVDA --start 2023-01-02 --end 2023-12-29 --stops on` does the same.
On the real 2016–2021 design period (core universe, re-measured under the v0.8 engine:
`results/v08/tables.md`, trials registry), the "+ intraday stops" trial gave a design mean
Sharpe of 0.45 against the control's 0.47, a mean cumulative return of 44.10% against
58.24%, a mean MDD of 12.67% against 13.31% and 292.20 trades per instrument against 254.20:
a similar Sharpe for about a quarter less return, which is why stops are off by default.

### 31. Backtest a multi-asset portfolio

Each symbol is a sleeve with 1/N of the capital and its own costs, carry, positions and market
impact charged at the sleeve's own capital. The portfolio return is the daily mean of the
sleeves, and equity and FX calendars are aligned.

```python
from agentic_trader import make_config, run_portfolio_backtest

rep = run_portfolio_backtest(["AAPL", "JPM", "XOM", "EURUSD", "USDJPY"], "2023-01-02", "2023-12-29", make_config())
print(rep.table())
print(rep.returns["AgenticTrader"].describe())
```

### 32. Evaluate on your own universe and periods

The evaluation harness runs every (period, symbol) pair, records failures instead of
raising, and summarises the results.

```python
from agentic_trader import evaluate, make_config

res = evaluate(["AAPL", "MSFT", "EURUSD"],
               {"design": ("2021-01-04", "2022-12-30"), "holdout": ("2023-01-02", "2023-12-29")},
               make_config(), rebalance_every=5)
print(res.summary())
print(res.head_to_head())            # on how many instruments the agent's Sharpe wins
res.to_json("my_eval.json")
```

The real-data protocol used in [docs/evaluation](docs/evaluation/evaluation.md) is
`agentic-trader evaluate --data yahoo --periods design,holdout,q1_2024` *(network)*.

### 33. Judge a result: t-stat and the vol-targeted control

Two questions to ask of any backtest before believing it:

- **Is the Sharpe distinguishable from luck?** Check `t(SR)`. It is about Sharpe × √years,
  and a value around 2 or more is needed.
- **Did the strategy add value beyond holding less?** Compare it with `B&H vol-target`,
  buy & hold scaled to the same volatility target from trailing volatility.

Sharpe and `t(SR)` are computed on returns in excess of the cash leg (`cash_leg`: the constant
`risk_free_annual` on synthetic and CSV data, the 3-month T-bill from FRED on real data), so a
strategy that sits in cash is credited the bill rate rather than zero.

```python
from agentic_trader import make_config, run_agent_backtest

t = run_agent_backtest("GOOGL", "2023-01-02", "2023-12-29", make_config()).table()
print(t.loc[["AgenticTrader", "Buy&Hold", "B&H vol-target"], ["Sharpe", "t(SR)", "Vol%", "MDD%", "Exp%"]])
```

### 34. Stress the cost assumptions

A strategy that only works at 1 bp is not a strategy. Re-run with higher costs and watch
Sharpe and the trade count:

```python
from agentic_trader import make_config, run_agent_backtest

for bps in (1, 5, 20):
    cfg = make_config(costs={"equity_cost_bps": bps, "equity_slippage_bps": bps})
    a = run_agent_backtest("AMZN", "2023-01-02", "2023-12-29", cfg).table().loc["AgenticTrader"]
    print(f"{bps:>3} bps + {bps} bps slippage: Sharpe {a['Sharpe']:.2f}, CR {a['CR%']:.1f}%, trades {a['Trades']:.0f}")
```

### 35. Point-in-time FX carry from FRED

*(network)*

On real data, FX rates come from FRED as they were known on each date. Values are lagged
by their publication delay, and a series that has stopped updating counts as missing
rather than being carried forward.

```python
from datetime import date
from agentic_trader import Instrument, make_config
from agentic_trader.data import YahooProvider

p = YahooProvider(make_config())
print(p.macro(Instrument.parse("USDJPY"), date(2024, 1, 15)))     # USD 5.33 vs JPY -0.01
import pandas as pd
carry = p.carry_series(Instrument.parse("EURUSD"), pd.bdate_range("2022-01-03", "2023-12-29"))
print(carry[:3], carry[-3:])                                        # the ECB-Fed gap moving through the hiking cycle
```

### 36. Cap LLM spend

*(API key for the real model; the example below uses a stand-in)*

`max_llm_calls` is a hard cap per graph. Beyond it, every agent falls back to its rules and
the run completes normally. At default rounds one decision is 14 calls, so a one-year
weekly backtest of one instrument is about 730.

```python
from agentic_trader import TradingGraph, make_config
from agentic_trader.memory import DecisionMemory

class StandIn:                      # replace with llm_provider="anthropic" for Claude
    def complete(self, system, prompt, *, deep):
        return None

g = TradingGraph(make_config(max_llm_calls=20), llm=StandIn(), memory=DecisionMemory(None), on_event=lambda *_: None)
for day in ("2024-02-01", "2024-02-15", "2024-03-01"):
    g.propagate("AAPL", day)
print(g.llm.calls, g.llm.refused)   # 20 calls made, the rest refused -> rules
```

```bash
agentic-trader backtest AAPL --llm anthropic --start 2024-01-02 --end 2024-03-28 --max-llm-calls 200
```

### 37. Clean messy price files

`clean_ohlcv` is what every provider uses. It does four things:

- sorts the dates and drops duplicates;
- drops rows without a positive close;
- fills missing open, high and low from the close;
- widens impossible bars so the stop logic never sees a high below the close.

```python
import pandas as pd
from agentic_trader.data import clean_ohlcv

raw = pd.DataFrame({"Open": [10, None, 12], "High": [9, 12, 13], "Low": [9, 11, 0],
                    "Close": [10, 11.5, 0]},
                   index=["2024-01-03", "2024-01-02", "2024-01-04"])
print(clean_ohlcv(raw))
```

### 38. Fail safely on bad input

Every guard raises `ValueError` with a clear message. The CLI turns these into exit status 2
and a one-line `error:` instead of a traceback.

```python
from agentic_trader import Instrument, TradingGraph, make_config, run_agent_backtest
from agentic_trader.memory import DecisionMemory

g = TradingGraph(make_config(), memory=DecisionMemory(None), on_event=lambda *_: None)
for attempt in (lambda: Instrument.parse("EUR/XYZ"),                      # mistyped pair
                lambda: g.propagate("AAPL", "2015-01-20"),                # not enough history
                lambda: g.propagate("AAPL", "2024-03-01", current_weight=float("nan")),
                lambda: run_agent_backtest("AAPL", "2024-03-01", "2024-01-01", make_config())):
    try:
        attempt()
    except ValueError as e:
        print("refused:", e)
```

A feed that has stopped updating is refused too. If the latest bar is more than
`max_data_staleness_days` (7) before the decision date, `propagate` raises instead of
trading on an old price.

## The agentic layer

### 39. Run a task through the harness

The harness plans, runs policy-gated tools, runs the desk's stages, then the critic, evidence
validation and the audited report. It ends in a terminal state with everything attached.

```python
from datetime import date
from agentic_trader import TradingGraph, make_config
from agentic_trader.agentic import AgentHarness, Role, Task
from agentic_trader.memory import DecisionMemory

graph = TradingGraph(make_config(), memory=DecisionMemory(None), on_event=lambda *_: None)
harness = AgentHarness(graph)
run = harness.run(Task("EURUSD", date(2024, 3, 1), Role.TRADER, current_weight=0.2))
print(run.state.value, [s.name for s in run.plan.steps])
print(run.decision.action.value, run.decision.target_weight, "confidence", run.decision.confidence)
print("evidence", len(run.evidence), "findings", len(run.findings), "audit warnings", run.report.warnings)
print(run.report.to_markdown()[:600])
```

The same from the command line: `agentic-trader task EURUSD --date 2024-03-01 --position 0.2`.

### 40. Read the evidence behind a decision

Every document cites the evidence it was built from, and every id resolves to a record with a
digest.

```python
from datetime import date
from agentic_trader import TradingGraph, make_config
from agentic_trader.agentic import AgentHarness, Task
from agentic_trader.memory import DecisionMemory

run = AgentHarness(TradingGraph(make_config(), memory=DecisionMemory(None), on_event=lambda *_: None)).run(Task("AAPL", date(2024, 3, 1)))
for f in run.findings:
    print(f"{f.agent:<18} {f.confidence:.2f}  cites {len(f.evidence_ids)} records")
for ev_id in run.decision.evidence_ids[:5]:
    ev = run.evidence.get(ev_id)
    print(ev.id, ev.type.value, ev.source, ev.digest[:12], "resolves:", run.evidence.resolve(ev.id))
by_type = {}
for ev in run.evidence:
    by_type[ev.type.value] = by_type.get(ev.type.value, 0) + 1
print(by_type)
```

### 41. Call a tool directly, under policy

The executor is usable on its own. A call is checked, coerced, timed, traced and evidenced.

```python
from agentic_trader import make_config
from agentic_trader.agentic import DeskTools, EvidenceStore, PolicyEngine, Role, ToolExecutor, build_registry
from agentic_trader.data import SyntheticProvider

cfg = make_config()
reg = build_registry(DeskTools(SyntheticProvider(cfg), cfg))
ex = ToolExecutor(reg, PolicyEngine({"max_position": 1.0, "symbol_universe": ["AAPL", "EURUSD"]}), EvidenceStore(), Role.ANALYST)
ok = ex.call("quant.technical", symbol="AAPL", as_of="2024-03-01")
print(ok.ok, round(ok.payload["rsi14"], 1), f"{ok.elapsed_ms:.1f} ms")
denied = ex.call("market_data.news", symbol="MSFT", as_of="2024-03-01", lookback_days=7)
print(denied.ok, denied.error)
bad = ex.call("market_data.news", symbol="AAPL", as_of="2024-03-01", lookback_days=7.5)
print(bad.ok, bad.error)
print(len(ex.evidence), "evidence records, including the failures")
```

### 42. Queue an order for human approval

`execution.submit_order` is state-changing and high risk, so it always needs approval. With
the queued gateway the call parks until a person decides. A ticket is the plan `execution.plan`
produced, not a bare number: the quantity in its unit (whole shares, or whole lots of the
pair's base currency), the notional in the account currency, the reference price and the
`plan_id` that binds them (an edited field fails to verify). `ticket_from_plan` turns the plan
payload into the call's arguments; the notional is checked against the per-order cap
(`execution.max_order_notional`, default `initial_capital × risk.max_position`; 0 freezes
ticketing) by policy before anyone is asked to approve, and the plan payload already says
whether the order is `ticketable` against that `order_cap`. `submit_order` accepts only a
plan this desk produced, with exactly its fields (`plan_known`; the plan id is a checksum
anyone can compute, so it is not authentication by itself; `execution.allow_external_plans`
admits tickets planned elsewhere), and a ticket moves the desk's book to `position_after`,
so a later plan in the same session sizes from it.

```python
from datetime import date
from agentic_trader import TradingGraph, make_config
from agentic_trader.agentic import AgentHarness, QueuedApprovalGateway, Role, Task
from agentic_trader.agentic.servers import ticket_from_plan
from agentic_trader.memory import DecisionMemory

h = AgentHarness(TradingGraph(make_config(), memory=DecisionMemory(None), on_event=lambda *_: None),
                 gateway=QueuedApprovalGateway())
run = h.submit(Task("AAPL", date(2024, 3, 1), Role.TRADER))
ex = h._executor(run)
plan = ex.call("execution.plan", symbol="AAPL", as_of="2024-03-01", target_weight=0.5).payload   # read-only: runs at once
print(plan["side"], plan["quantity"], plan["quantity_unit"], round(plan["notional"]), plan["notional_currency"], plan["plan_id"])
ticket = ticket_from_plan(plan, note="morning run")            # the submit_order arguments, unchanged
first = ex.call("execution.submit_order", **ticket)
print(first.ok, first.error)
pending = h.pending_approvals(run.id)
print([(a.id, a.request.tool, a.reason) for a in pending])
h.gateway.resolve(pending[0].id, approve=True, decided_by="risk", note="within limits")
second = ex.call("execution.submit_order", **ticket)
print(second.ok, second.payload)          # the ticket; no broker is involved
```

```
buy 223.0 shares 49778 USD PLAN-064e3ec3a337
False awaiting approval (read_only): execution.submit_order changes state; approval required
[('APPROVAL-7e4a9252', 'execution.submit_order', 'execution.submit_order changes state; approval required')]
True {'id': 'ORD-00001', 'plan_id': 'PLAN-064e3ec3a337', 'symbol': 'AAPL', 'side': 'buy', 'intent': 'open_long', 'quantity': 223.0, 'quantity_unit': 'shares', 'notional': 49777.900624837486, 'notional_currency': 'USD', 'price': 223.21928531317258, 'position_before': 0.0, 'position_after': 0.497779, 'plan_known': True, 'note': 'morning run', 'status': 'ticketed'}
```

The ticket records the position before and after against the desk's book, and `intent` says
whether it opens, adds, reduces, closes or shorts; a sell that would take a long-only book
short is refused at execution.

### 43. Write a policy rule

A rule is a callable that returns a decision or `None` to pass. Rules run in order and the first
decision wins: the defaults are deny list, capability, argument guards, then `read_only_rule`,
which parks every state-changing tool for approval. A rule that denies therefore goes first; a
rule that merely allows goes just before `allow_rule`.

```python
from agentic_trader.agentic import PolicyEngine, PolicyOutcome, Role
from agentic_trader.agentic.domain import PolicyDecision, ToolRequest
from agentic_trader.agentic.policy import DEFAULT_RULES
from agentic_trader.agentic import DeskTools, build_registry
from agentic_trader import make_config
from agentic_trader.data import SyntheticProvider

def no_fx_after_hours(ctx):
    """Deny FX order tickets outside the desk's hours (the hour comes from the arguments here)."""
    if ctx.tool.name == "execution.submit_order" and ctx.request.arguments.get("note", "").startswith("after-hours"):
        return PolicyDecision(PolicyOutcome.DENY, "desk_hours", "no order tickets after hours")
    return None

engine = PolicyEngine({"max_position": 1.0}, rules=(no_fx_after_hours,) + DEFAULT_RULES)
cfg = make_config()
tool = build_registry(DeskTools(SyntheticProvider(cfg), cfg)).get("execution.submit_order").descriptor
args = {"symbol": "EURUSD", "side": "buy", "quantity": 1000, "note": "after-hours"}
d = engine.evaluate(ToolRequest("execution.submit_order", args, "C"), tool, Role.TRADER)
print(d.outcome.value, d.rule, d.reason)            # DENY desk_hours ...
d = engine.evaluate(ToolRequest("execution.submit_order", {**args, "note": "open"}, "C"), tool, Role.TRADER)
print(d.outcome.value, d.rule, d.reason)            # REQUIRE_APPROVAL read_only ...
```

### 44. Validate a model-proposed plan

Whatever a model proposes is stripped, pinned and repaired before it runs.

```python
from datetime import date
from agentic_trader import Instrument, make_config
from agentic_trader.agentic import DeskTools, Task, build_registry, validate_plan
from agentic_trader.data import SyntheticProvider

cfg = make_config()
reg = build_registry(DeskTools(SyntheticProvider(cfg), cfg))
proposed = [
    {"type": "tool", "name": "market_data.news", "arguments": {"symbol": "NVDA", "as_of": "2025-01-01", "lookback_days": 5, "verbose": True}},
    {"type": "tool", "name": "execution.submit_order", "arguments": {"symbol": "AAPL", "side": "buy", "quantity": 1e9}},
    {"type": "agent", "name": "risk"},
]
plan = validate_plan(proposed, Task("AAPL", date(2024, 3, 1)), Instrument.parse("AAPL"), ["technical", "news"], reg)
print(plan.source)
for step in plan.steps:
    print(f"  {step.type.value:<6} {step.name:<20} {step.arguments}")
for note in plan.notes:
    print("note:", note)
```

To let the model plan for real: `make_config(agentic={"llm_planner": True}, llm_provider="anthropic")`.

### 45. Add a tool to the catalogue

Register a function; its schema comes from the signature. Annotations decide the policy.

```python
from agentic_trader import make_config
from agentic_trader.agentic import DeskTools, EvidenceStore, PolicyEngine, Role, ToolExecutor, build_registry
from agentic_trader.agentic.domain import Capability, EvidenceType, RiskLevel, ToolAnnotations
from agentic_trader.data import SyntheticProvider

cfg = make_config()
tools = DeskTools(SyntheticProvider(cfg), cfg)
reg = build_registry(tools)

def realized_range(symbol: str, as_of: str, days: int = 20) -> dict:
    """High-low range of the last `days` bars as a fraction of the last close."""
    h = tools.history(symbol, as_of, 60)
    hi, lo, c = max(h["High"][-days:]), min(h["Low"][-days:]), h["Close"][-1]
    return {"days": days, "range_pct": (hi - lo) / c}

reg.register("quant", realized_range, annotations=ToolAnnotations(
    True, RiskLevel.LOW, frozenset({Capability.RUN_ANALYTICS}), EvidenceType.CALCULATION))
ex = ToolExecutor(reg, PolicyEngine({"max_position": 1.0}), EvidenceStore(), Role.ANALYST)
print(reg.get("quant.realized_range").descriptor.input_schema["properties"])
print(ex.call("quant.realized_range", symbol="AAPL", as_of="2024-03-01").payload)
```

### 46. Search the desk's knowledge base

```python
from agentic_trader.agentic import default_knowledge_base

kb = default_knowledge_base()
print(len(kb.documents), "documents,", len(kb), "chunks")
for p in kb.search("how big can a position be and what is the VaR cap", k=3):
    print(f"{p.score:.3f}  {p.chunk.doc_id} / {p.chunk.heading}: {p.chunk.text[:90]}...")
```

Inside a task the same search is the `knowledge.search` step; the passages are DOCUMENT
evidence and appear in the trader's and PM's prompts.

### 47. Audit a narrative

The audits are plain functions you can run on any text against any facts.

```python
from agentic_trader.agentic import EvidenceStore, EvidenceType, evidence_audit, number_audit

facts = {"target_weight": 0.5354, "last_close": 223.219, "n_bullish": 4.0, "confidence": 0.51}
text = "BUY +0.54 (confidence 0.51), last close 223.22, 4 bullish analysts, 53.5% of capital, alpha 350 bps."
print("untraceable numbers:", number_audit(text, facts))
store = EvidenceStore()
ev = store.record(EvidenceType.DATA, "market_data.news", "3 headlines", [{"h": "x"}], "CID")
print("unresolved ids:", evidence_audit(f"see {ev.id} and DATA-deadbeef", [], store))
```

### 48. Serve the HTTP API and drive it

*(needs the `api` extra)*

```bash
agentic-trader serve --port 8000          # docs at http://127.0.0.1:8000/docs, approvals queued
```

```python
from fastapi.testclient import TestClient
from agentic_trader import TradingGraph, make_config
from agentic_trader.agentic import AgentHarness, QueuedApprovalGateway
from agentic_trader.agentic.api import create_app
from agentic_trader.memory import DecisionMemory
import time

h = AgentHarness(TradingGraph(make_config(), memory=DecisionMemory(None), on_event=lambda *_: None), gateway=QueuedApprovalGateway())
c = TestClient(create_app(harness=h))                   # in-process; the same app uvicorn serves
r = c.post("/tasks", json={"symbol": "AAPL", "as_of": "2024-03-01", "current_weight": 0.1}, headers={"X-API-Key": "dev-trader-key"})
tid = r.json()["task_id"]
while c.get(f"/tasks/{tid}", headers={"X-API-Key": "dev-viewer-key"}).json()["state"] not in ("COMPLETED", "FAILED"):
    time.sleep(0.05)
print(c.get(f"/tasks/{tid}/report?format=markdown", headers={"X-API-Key": "dev-viewer-key"}).text[:200])
print(c.get("/approvals", headers={"X-API-Key": "dev-risk-key"}).json())
print(c.get("/tools", headers={"X-API-Key": "dev-viewer-key"}).json()[0]["name"])
```

### 49. Expose the tools over MCP and consume them

*(needs the `mcp` extra; spawns a subprocess)*

```bash
agentic-trader mcp                        # stdio server for any MCP client; every call runs under policy,
                                          # approval and evidence for --role (trader) and --approval
agentic-trader mcp --approval deny        # locked down: every state-changing call is refused
agentic-trader mcp --role viewer          # read-only tools only; --approval queued is refused (exit 2)
```

```python
from agentic_trader.agentic import EvidenceStore, PolicyEngine, Role, ToolExecutor
from agentic_trader.agentic.mcp_server import call, discover, registry_from_stdio

tools = discover()
print(len(tools), tools[1]["name"], tools[1]["read_only"])
print(call("knowledge__list_documents", {}))
reg = registry_from_stdio()                              # remote tools as a local registry, over one server session
ex = ToolExecutor(reg, PolicyEngine({"max_position": 1.0}), EvidenceStore(), Role.TRADER)
r = ex.call("quant.technical", symbol="AAPL", as_of="2024-03-01")
print(r.ok, round(r.payload["rsi14"], 1), "evidence:", len(ex.evidence))   # policy and evidence apply to remote tools
reg.session.close()                                      # ends the server process (also on garbage collection)
```

A discovered tool is classified fail-closed whatever the server annotates: state-changing,
high risk, trader-only, data evidence. The `overrides` map is the only relaxation; by default
it is the desk's own catalogue, since the client only launches this package's server, and
`overrides={}` relaxes nothing. `registry_from_stdio(server_args=None, overrides=None,
call_timeout_s=None, config=None)`: the per-call deadline defaults to `agentic.tool_timeout_s`
(30 s), `math.inf` waits without limit, and a timeout only sends the SDK's cancellation
notice, which is as far as it reaches. A state-changing call that times out may still have
landed its ticket on the server: its outcome is unknown, so reconcile through
`portfolio.position`, which lists pending tickets.

### 50. Trace a run and export metrics

```python
from datetime import date
from agentic_trader import TradingGraph, make_config
from agentic_trader.agentic import AgentHarness, Task
from agentic_trader.memory import DecisionMemory

run = AgentHarness(TradingGraph(make_config(), memory=DecisionMemory(None), on_event=lambda *_: None)).run(Task("AAPL", date(2024, 3, 1)))
print(run.tracer.summary())
for span in run.tracer.to_list()[:6]:
    print(f"{span['name']:<24} {span['duration_ms']:>7.2f} ms  parent={span['parent_id']}")
print(run.tracer.metrics.render().splitlines()[:4])       # Prometheus text format
```

`agentic_trader.agentic.tracing.configure_json_logging()` routes the package's loggers to
JSON lines on stderr.

## Quant research

### 51. Evaluate the alpha library

```python
from datetime import date
from agentic_trader import Instrument, make_config
from agentic_trader.alpha import alpha_report
from agentic_trader.data import SyntheticProvider

p = SyntheticProvider(make_config())
ins = Instrument.parse("USDJPY")
df = p.history(ins, date(2020, 1, 1), date(2024, 3, 28))
rep = alpha_report(df, ins, horizon=10, carry_series=p.carry_series(ins, df.index))
print(rep.table[["IC", "t(IC)", "hit%", "up%", "tercile spread%", "autocorr"]])
print(rep.decay)                                          # IC by horizon: pick the rebalance frequency
print(rep.correlations.round(2))
print("best by IC:", rep.best())
```

`t(IC)` is overlap-aware: with forward returns over `horizon` bars only every `horizon`-th pair
is new, so the t-statistic uses `n / horizon` effective observations (`information_coefficient`
also offers `method="newey_west"`). `up%` is the share of positive forward returns on the same
pairs, the base rate a `hit%` must beat; the tercile spread assigns terciles by rank, so a signal
stuck at one value on most bars still has a top and a bottom third.

On real prices: `agentic-trader alpha USDJPY --data yahoo --start 2016-01-04 --end 2021-12-31`.

### 52. Add an alpha and use the alpha analyst

```python
import numpy as np
from datetime import date
from agentic_trader import TradingGraph, make_config
from agentic_trader.alpha import ALPHAS, EQUITY_ALPHAS, AlphaInputs, compute_alphas
from agentic_trader.memory import DecisionMemory

def gap_fade(x: AlphaInputs) -> np.ndarray:
    """Fade yesterday's close-to-close jump larger than 2 ATR-equivalents (toy)."""
    r = np.full(len(x.close), np.nan)
    r[1:] = x.close[1:] / x.close[:-1] - 1.0
    return -np.tanh(r / 0.02)

ALPHAS["gap_fade"] = gap_fade
EQUITY_ALPHAS.append("gap_fade")
g = TradingGraph(make_config(analysts=["technical", "alpha", "news", "sentiment"]),
                 memory=DecisionMemory(None), on_event=lambda *_: None)
state, d = g.propagate("AAPL", date(2024, 3, 1))
print(state.reports["alpha"].summary)
print(state.reports["alpha"].key_points)
```

The alpha analyst is off by default because, with the corrected gate, it measures as nothing
on the core design period: agent mean Sharpe with it minus without −0.00 [−0.05, +0.05]
p 0.90, and on the holdout −0.00 [−0.04, +0.02] p 0.79 (`results/v08/tables.md`, "with the
alpha analyst, corrected gate (a) vs default (b)"; a paired bootstrap over instruments,
`scheme=instruments`, recipe 67, printed with p and no BH flag; how often the gate speaks on
real data was not recorded). Adding a new alpha changes the composite, so re-run `evaluate`
on the design period before adopting it.

### 53. Plan and simulate an execution

The order is sized at the as-of close (`notional = |target − current| × capital` in the
account currency, rounded down once to whole shares or, for FX, to whole lots of the base
currency) and worked on the *next* session, the first one a decision at the close can trade
in. A change that rounds down to zero shares or lots is nothing to trade, not an error:
`plan_execution` returns `None`, as it does for an unchanged target. `simulate_execution`
takes the requested quantity so an unfilled remainder shows up as a completion below 100%
and as opportunity cost inside the implementation shortfall.

```python
from datetime import date
import pandas as pd
from agentic_trader import Instrument, make_config
from agentic_trader.algo import plan_execution, simulate_execution, synthetic_intraday_bars
from agentic_trader.data import SyntheticProvider
from agentic_trader.state import Action, FinalDecision

p = SyntheticProvider(make_config())
ins = Instrument.parse("AAPL")
as_of = date(2024, 3, 1)
df = p.history(ins, date(2024, 1, 1), date(2024, 3, 8))
known = df[df.index <= pd.Timestamp(as_of)]                       # what the desk sees at the as-of close
last, adv = float(known["Close"].iloc[-1]), float(known["Volume"].tail(20).mean())
decision = FinalDecision("AAPL", as_of, Action.BUY, 0.6, 0.5, None, None, "")
plan = plan_execution(decision, ins, current_weight=0.1, capital=50_000_000, last_price=last, adv=adv)
print(f"{plan.side} {plan.quantity:,.0f} {plan.quantity_unit} (notional {plan.notional:,.0f} {plan.notional_currency} "
      f"at {plan.price:.2f}) via {plan.algo} in {plan.slices} slices; {plan.reason}; intent {plan.intent}; {plan.id}")
session = df[df.index > pd.Timestamp(as_of)].iloc[0]              # the first session the order can trade in
bars = synthetic_intraday_bars(session, plan.slices, "equity", seed=0)
rep = simulate_execution(plan.schedule(bars), bars, plan.side, plan.algo, spread_bps=2.0, impact_coeff=1.0,
                         daily_vol=float(known["Close"].pct_change().tail(20).std()), adv=adv, requested=plan.quantity)
print(f"executed {rep.executed:,.0f} of {rep.requested:,.0f} ({rep.completion:.0%}) on {session.name.date()}; "
      f"IS {rep.is_bps:+.1f} bps; vs VWAP {rep.vs_vwap_bps:+.1f} bps; spread {rep.spread_cost_bps:.1f} + impact "
      f"{rep.impact_cost_bps:.1f} bps; max participation {rep.max_participation:.1%}")
```

```
buy 111,997 shares (notional 24,999,890 USD at 223.22) via vwap in 78 slices; weight +0.10 -> +0.60; intent add_long; PLAN-eccd6b94ec5b
executed 111,997 of 111,997 (100%) on 2024-03-04; IS +74.2 bps; vs VWAP +12.6 bps; spread 1.0 + impact 11.6 bps; max participation 0.3%
```

The CLI does the same. `--capital` defaults to the config's `initial_capital` (100,000, the
convention the desk tools, `task` and the API share); FX quantities are in the base currency
(a USD/JPY order for 50,000 USD is 50,000 USD, not a count of JPY-priced units), and an
order larger than the day's liquidity reports what it filled:

```
$ agentic-trader execute AAPL --date 2024-03-01 --target 0.6 --current 0.1 --capital 50000000
BUY 111,997 shares (notional 24,999,890 USD at 223.22) via VWAP in 78 slices; weight +0.10 -> +0.60; intent add_long; PLAN-eccd6b94ec5b
order is 0.27% of 20-day ADV
executed 111,997 of 111,997 shares (100%) on 2024-03-04; arrival 223.16, avg fill 224.82, session VWAP 224.53, close 228.44
implementation shortfall +74.2 bps, vs VWAP +12.6 bps (spread 1.0 bps, impact 11.6 bps), max slice participation 0.3%

$ agentic-trader execute AAPL --date 2024-03-01 --target 0.6 --current 0.1
BUY 223 shares (notional 49,778 USD at 223.22) via VWAP in 78 slices; weight +0.10 -> +0.60; intent add_long; PLAN-064e3ec3a337
order is 0.00% of 20-day ADV
executed 223 of 223 shares (100%) on 2024-03-04; arrival 223.16, avg fill 224.57, session VWAP 224.53, close 228.44
implementation shortfall +63.0 bps, vs VWAP +1.5 bps (spread 1.0 bps, impact 0.5 bps), max slice participation 0.0%

$ agentic-trader execute USDJPY --date 2024-03-01 --target 0.5
BUY 50,000 USD (notional 50,000 USD at 133.78) via TWAP in 288 slices; weight +0.00 -> +0.50; intent open_long; PLAN-9fffc0aea2da
executed 50,000 of 50,000 USD (100%) on 2024-03-04; arrival 133.7, avg fill 133.75, session VWAP 133.75, close 132.96
implementation shortfall +3.8 bps, vs VWAP +0.3 bps (spread 0.3 bps, impact 0.0 bps)

$ agentic-trader execute NVDA --date 2024-03-01 --target 1.0 --capital 1000000000
BUY 27,588,377 shares (notional 999,999,966 USD at 36.247) via POV in 78 slices; weight +0.00 -> +1.00; 133.6% of ADV exceeds 10% -> POV; intent open_long; PLAN-794907a342fe
order is 133.56% of 20-day ADV
executed 1,473,029 of 27,588,377 shares (5%) on 2024-03-04; arrival 36.071, avg fill 36.49, session VWAP 36.3, close 36.7
implementation shortfall +171.3 bps, vs VWAP +52.4 bps (spread 1.0 bps, impact 51.4 bps, opportunity cost of 26,115,348 unfilled +165.1 bps), max slice participation 10.0%

$ agentic-trader execute AAPL --date 2024-03-01 --target 0.1001 --current 0.1
nothing to trade: the change +0.1000 -> +0.1001 (10 USD) is below one share

$ agentic-trader execute AAPL --date 2024-03-01 --target 0.5 --algo ac --ac-kappa inf
error: --ac-kappa must be finite and >= 0
```

Most of the AAPL shortfall is the next session's own rise from the open, timing rather than
cost; the cost is the line against VWAP. The unfilled clause is printed only when at least
one share or lot went unfilled (a closed-form schedule can leave 1e-14 of a share). A
negative equity target under the default long-only policy is truncated to flat
(`--allow-short` lifts it; when the truncated change is itself below one share the message
sizes that change, not the one asked for, and says why), and `--ac-kappa` sets the
Almgren-Chriss urgency for `--algo ac` (dimensionless,
`costs.ac_kappa` 3.0; 0 is TWAP; an infinite, NaN or negative value exits 2).

### 54. Compare execution algorithms on the same day

Each slice pays temporary impact `impact_coeff × daily_vol × √(q_i / V_i)` on its own share
of the bar's volume, the same square-root law the daily backtester charges, so a schedule
that matches the volume curve (VWAP) pays the least impact for a given quantity and a
front-loaded one pays more. The shortfall against arrival differs from seed to seed because
it contains the session's own drift; the impact column does not.

```python
from datetime import date
import math
from agentic_trader import Instrument, make_config, quant
from agentic_trader.algo import pov_schedule, simulate_execution, synthetic_intraday_bars, twap_schedule, vwap_schedule
from agentic_trader.data import SyntheticProvider

p = SyntheticProvider(make_config())
df = p.history(Instrument.parse("NVDA"), date(2024, 2, 1), date(2024, 3, 4))
session, history = df.iloc[-1], df.iloc[:-1]                 # decide at the 2024-03-01 close, trade on 2024-03-04
adv = float(history["Volume"].tail(20).mean())
daily_vol = float(history["Close"].pct_change().tail(20).std())
qty = math.floor(0.02 * adv)                                 # a 2%-of-ADV order, whole shares
for seed in (1, 2, 3):
    bars = synthetic_intraday_bars(session, 78, "equity", seed)
    vols = bars["Volume"].to_numpy()
    for name, sched in (("TWAP", twap_schedule(qty, 78)), ("VWAP", vwap_schedule(qty, vols)),
                        ("POV 10%", pov_schedule(qty, vols, 0.10)),
                        ("AC k=3", quant.almgren_chriss(qty, 78, 3.0))):   # dimensionless urgency; 0 = TWAP, inf/nan/negative raise
        r = simulate_execution(sched, bars, "buy", name, 2.0, 1.0, daily_vol, adv, requested=qty)
        print(f"seed {seed} {name:<8} filled {r.completion:5.0%}  IS {r.is_bps:+6.1f} bps  vs VWAP {r.vs_vwap_bps:+6.1f} bps"
              f"  impact {r.impact_cost_bps:4.1f} bps")
```

```
seed 1 TWAP     filled  100%  IS +137.3 bps  vs VWAP  +31.0 bps  impact 28.9 bps
seed 1 VWAP     filled  100%  IS +134.4 bps  vs VWAP  +28.2 bps  impact 27.2 bps
seed 1 POV 10%  filled  100%  IS  +92.7 bps  vs VWAP  -13.1 bps  impact 51.2 bps
seed 1 AC k=3   filled  100%  IS +108.9 bps  vs VWAP   +2.9 bps  impact 31.3 bps
seed 2 TWAP     filled  100%  IS +117.1 bps  vs VWAP  +29.2 bps  impact 28.9 bps
seed 2 VWAP     filled  100%  IS +116.1 bps  vs VWAP  +28.2 bps  impact 27.2 bps
seed 2 POV 10%  filled  100%  IS  +59.8 bps  vs VWAP  -27.6 bps  impact 51.2 bps
seed 2 AC k=3   filled  100%  IS  +79.4 bps  vs VWAP   -8.1 bps  impact 31.3 bps
seed 3 TWAP     filled  100%  IS +133.4 bps  vs VWAP  +37.9 bps  impact 28.9 bps
seed 3 VWAP     filled  100%  IS +123.6 bps  vs VWAP  +28.2 bps  impact 27.2 bps
seed 3 POV 10%  filled  100%  IS  +55.9 bps  vs VWAP  -38.9 bps  impact 51.2 bps
seed 3 AC k=3   filled  100%  IS  +90.4 bps  vs VWAP   -4.6 bps  impact 31.3 bps
```

On this rising session the schedules that trade early (POV at its 10% cap, the front-loaded
Almgren-Chriss) beat the session VWAP and pay a smaller shortfall against arrival, at a higher
impact cost; on a falling one the ordering of the shortfall flips and the impact column does
not. `ExecutionPlan.schedule(bars, kappa=...)` is the same choice inside a plan.

### 55. Construct a portfolio and read its risk

```python
from datetime import date
import pandas as pd
from agentic_trader import Instrument, make_config
from agentic_trader.data import SyntheticProvider
from agentic_trader.portfolio import construct

p = SyntheticProvider(make_config())
syms = ["AAPL", "JPM", "XOM", "EURUSD", "USDJPY"]
rets = pd.DataFrame({s: p.history(Instrument.parse(s), date(2023, 1, 1), date(2024, 3, 1))["Close"].pct_change() for s in syms}).dropna()
targets = {"AAPL": 1.0, "JPM": 0.6, "XOM": 0.0, "EURUSD": -0.5, "USDJPY": 0.8}     # the desk's signed targets
for method in ("equal", "inverse_vol", "risk_parity", "min_variance"):
    pw = construct(targets, rets, method, max_weight=0.5, target_vol=0.12)
    print(f"{method:<12} vol {pw.expected_vol:.3f}  DR {pw.diversification_ratio:.2f}  scale {pw.scale:.2f}  "
          + " ".join(f"{s}={w:+.2f}" for s, w in zip(pw.symbols, pw.weights)))
print(pw.contributions)                                   # allocation, weight, vol, marginal, component, pct_of_risk
```

`allocation` is the split before vol-targeting (it sums to the gross cap, every sleeve at most
`max_weight`); `weights = allocation × target × scale`, and the scale is capped so no sleeve
exceeds `max_weight` after scaling up. The shrinkage intensity on the EWMA covariance is the
weighted Ledoit-Wolf constant-correlation estimate (`ledoit_wolf_shrink(..., weights=)`).

In a backtest: `run_portfolio_backtest(syms, start, end, cfg, weighting="risk_parity")` or
`agentic-trader portfolio AAPL,JPM,XOM,EURUSD,USDJPY --start ... --end ... --weighting risk_parity`.

### 56. Deflate a Sharpe ratio after a search

You tried several variants and kept the best. The deflated Sharpe ratio asks whether the best
would still look good against the expected maximum of that many null tries.

```python
import numpy as np
from agentic_trader.stats import selection_report, sharpe_stats

rng = np.random.default_rng(0)
chosen = rng.normal(0.0006, 0.01, 1000)                  # daily returns of the variant you kept
tried = [0.4, 0.9, 1.1, 0.7, 0.2, 0.95, 0.85, 0.6]        # annual Sharpes of everything you tried
print(sharpe_stats(chosen).sharpe_annual)
print(selection_report(chosen, tried))
```

`agentic-trader stats returns.csv --trials 8 --trial-sharpes 0.4,0.9,1.1,0.7,0.2,0.95,0.85,0.6`
does the same from a CSV. The evaluation applies this to the desk's own rule search:
`agentic_trader.evaluation.TRIALS` lists every variant judged on the design period (26 as of
v0.8: 24 re-measured under the current engine by `scripts/measure_v08.py`, 2 historical), and
the design-period mean Sharpes of those trials are the `trial_sharpes` of the published report.
That report (`results/v08/tables.md`, "selection statistics for the frozen rules", rendered
from `results/v08/trials.json` and `portfolio_design.csv`) gives, for 26 trials, an expected
maximum null Sharpe of 0.161 and a deflated Sharpe probability of 0.998 — an upper bound, as
the report's own caveat says, because the trial Sharpes' dispersion understates the search.

## v0.5: execution-aware evaluation, cross-sectional research, operations

### 57. Backtest with market impact at three account sizes

Backtests assume costless closes-to-close fills unless you say otherwise. `costs.impact_coeff`
charges the execution simulator's square-root impact per trade, to the agent and to every
baseline. The charge follows the notional actually traded: the coefficient scales with
`initial_capital` and, bar by bar, with √(equity / initial capital), so the same strategy gets
cheaper or dearer with the account and a compounding account pays for what it trades.
`Impact%` is the cumulative cost paid.

```python
from agentic_trader import make_config, run_agent_backtest

for capital in (1e5, 1e7, 1e9):
    cfg = make_config(costs={"impact_coeff": 1.0}, initial_capital=capital)
    rep = run_agent_backtest("AAPL", "2024-01-02", "2024-03-28", cfg, rebalance_every=5)
    t = rep.table()
    print(f"{capital:>10.0e}  agent CR {t.loc['AgenticTrader', 'CR%']:+.2f}%  impact {t.loc['AgenticTrader', 'Impact%']:.3f}%"
          f"  | B&H vol-target impact {t.loc['B&H vol-target', 'Impact%']:.3f}%")
```

`agentic-trader backtest AAPL --start 2024-01-02 --end 2024-03-28 --impact 1.0 --capital 1e9`
does the same. FX has no exchange volume, so it gets no impact unless `costs.fx_adv_notional`
is set. The evaluation reports the core universe at $100k, $10M and $1B.

### 58. Cross-sectional alpha report over a universe

A time-series alpha asks "will this name go up?"; a cross-sectional one asks "which names
will do better than the others?". The same signals are z-scored across the group every day
(equities with equities, FX with FX) and scored by per-date IC, quantile spreads and breadth.

```python
from datetime import date
from agentic_trader import Instrument, make_config
from agentic_trader.data import get_provider
from agentic_trader.xalpha import xalpha_report

p = get_provider(make_config())
names = ["AAPL", "MSFT", "NVDA", "JPM", "XOM", "JNJ", "EURUSD", "USDJPY", "GBPUSD"]
frames = {s: p.history(Instrument.parse(s), date(2021, 1, 4), date(2024, 3, 28)) for s in names}
instruments = {s: Instrument.parse(s) for s in names}
carry = {s: p.carry_series(instruments[s], frames[s].index) for s in names if instruments[s].is_fx}

rep = xalpha_report(frames, instruments, horizon=10, carry=carry)
print(rep.table[["mean IC", "IC IR", "t(IC)", "IC>0%", "spread%/period", "breadth"]])
print("best:", rep.best(3))
print(rep.signals["combined"].tail(2).round(2))   # today's relative ranking, in [-1, 1]
```

`agentic-trader xalpha AAPL,MSFT,NVDA,JPM,XOM --start 2021-01-04 --end 2024-03-28` prints the
same; `--standardise rank` uses ranks instead of z-scores. Under the harness the `quant.xalpha`
tool returns the snapshot and IC table for a list of symbols as evidence.

### 59. Risk budgets across asset classes

Plain risk parity gives the calmest sleeves the most capital, so a mixed book drifts towards
FX. Group budgets fix the *share of risk* per class: the scheme allocates within each class,
then risk parity with the budgets allocates across classes from the full covariance.

```python
from datetime import date
import pandas as pd
from agentic_trader import Instrument, make_config, run_portfolio_backtest
from agentic_trader.data import get_provider
from agentic_trader.portfolio import construct

p = get_provider(make_config())
names = ["AAPL", "JPM", "XOM", "EURUSD", "USDJPY"]
returns = pd.DataFrame({s: p.history(Instrument.parse(s), date(2023, 1, 2), date(2023, 12, 29))["Close"].pct_change()
                        for s in names}).dropna()
groups = {s: Instrument.parse(s).asset_class for s in names}

pw = construct({s: 1.0 for s in names}, returns, "risk_parity", groups=groups,
               group_budgets={"equity": 0.6, "fx": 0.4}, max_weight=1.0, target_vol=None)
print(pw.group_risk)                                   # budget vs realised risk share
print(pw.contributions[["allocation", "pct_of_risk"]])

rep = run_portfolio_backtest(names, "2023-07-03", "2023-12-29", make_config(), rebalance_every=10,
                             weighting="risk_parity", class_budgets={"equity": 0.6, "fx": 0.4})
print(rep.table().loc[["AgenticTrader", "Buy&Hold"]])
```

`agentic-trader portfolio AAPL,JPM,XOM,EURUSD,USDJPY --start 2023-07-03 --end 2023-12-29
--weighting risk_parity --class-budgets equity=0.6,fx=0.4`.

### 60. Read inflation as first published (ALFRED vintages)

FRED serves the latest revision of a series, so a backtest in 2019 sees the CPI number as
revised in 2020. ALFRED keeps every vintage. With `fred_vintages` on, a revised series is
read from the vintage that was current at the as-of date (sampled monthly, cached).

```python
from datetime import date
import pandas as pd
from agentic_trader.data.fred import FredClient, FredSeries

# Offline stand-in for the two web services: the 2019-11 CPI print was first published
# as 100 and revised to 101 a month later. A real client just omits `fetch=`.
obs = pd.to_datetime(["2018-11-01", "2019-11-01", "2019-12-01"])
def fetch(url):
    if "vintage_date=" in url and url.split("vintage_date=")[1] < "2020-02-01":
        return pd.DataFrame({"CPIAUCSL": [95.0, 100.0]}, index=obs[:2])   # what ALFRED knew in Jan 2020
    return pd.DataFrame({"CPIAUCSL": [95.0, 101.0, 102.0]}, index=obs)   # the latest vintage

spec = FredSeries("CPIAUCSL", lag_days=45, max_age_days=120, revised=True)
latest = FredClient(fetch=fetch)
vintages = FredClient(vintages=True, fetch=fetch)
print("FRED (latest):", latest.value_asof(spec, date(2020, 1, 10)))     # 101.0: the revision leaked back
print("ALFRED vintage:", vintages.value_asof(spec, date(2020, 1, 10)))  # 100.0: as first published
```

For the real thing: `make_config(fred_vintages=True, fred_cache_dir="results/fred_cache")`, or
`agentic-trader evaluate --data yahoo --fred-vintages --fred-cache results/fred_cache`
*(network)*. Policy rates are never revised, so only the inflation inputs change.

### 61. Cap the LLM bill in dollars

`max_llm_calls` caps calls; an Opus call costs about fifteen Haiku calls, so a call count
does not bound the bill. `max_llm_cost_usd` caps the estimated spend (list prices,
cache-aware). Before a call is dispatched its reservation (`estimate_cost`) is taken, and
calls in flight count against the cap, so parallel workers sharing one budget cannot each
slip a call past it. What is reserved is `llm_budget_mode`: in the default `"hard"` mode it
is the most the call can cost (the input estimate plus a full `max_tokens` reply, which is
also what a timed-out attempt is billed at), so spend stays within the cap and a cap that
cannot afford one such call refuses that tier before any spend; in `"estimate"` mode it is
the input estimate plus `llm_reserve_output_tokens` (2000), which admits more concurrent
calls but makes the cap soft by what replies exceed the reserve. `exhausted_for(deep)` says
whether a tier's next call would be refused, and `exhausted` asks about the deep tier. A
served model id without a list price exhausts the budget instead of spending unbounded, and
a configured id without one is refused at construction.

```python
from agentic_trader import TradingGraph, make_config
from agentic_trader.llm import BudgetedLLM, ModelUsage, UsageTracker, estimate_call_cost

class Priced:                                   # stands in for AnthropicLLM: 16k output tokens per call
    def __init__(self):
        self.usage = UsageTracker()
    def estimate_cost(self, deep):              # the most one call can cost; reserved before dispatch
        return estimate_call_cost("claude-opus-5", 16_000)
    def complete(self, system, prompt, *, deep):
        u = self.usage.by_model.setdefault("claude-opus-5", ModelUsage())
        u.calls += 1
        u.output_tokens += 16_000
        return '{"signal": 0.4, "confidence": 0.5, "summary": "ok"}'

llm = BudgetedLLM(Priced(), max_cost_usd=1.0)
for _ in range(6):
    llm.complete("system", "prompt", deep=True)
print(f"calls {llm.calls}, refused {llm.refused}, spent ${llm.spent_usd:.2f}")   # the third call's reservation would cross $1

g = TradingGraph(make_config(max_llm_cost_usd=0.0), llm=Priced())   # a zero budget: rules only
print(g.propagate("AAPL", "2024-03-01")[1].source)
```

`agentic-trader evaluate --llm anthropic --max-llm-cost 25 --max-llm-calls 2000` *(API key)*
stops at whichever cap comes first.

### 62. Keep tasks across restarts

Without a store the harness forgets every task when the process ends. `agentic.task_db`
writes each run to SQLite at every state transition and a new process serves the old records
through the same API. Nothing is resumed: each live run is owned and heartbeated by its
instance, and a record whose owner has not heartbeated for `agentic.lease_s` (90 s, at least
1) is failed by whichever live instance sweeps next. The configured `agentic.instance_id`
never widens the sweep: a restart under the same id does not fail its predecessor's
in-flight records at once but once their lease has passed, and a live sibling sharing the id
keeps its runs because it keeps heartbeating them.

```python
import os
import tempfile
from datetime import date
from agentic_trader import TradingGraph, make_config
from agentic_trader.agentic import AgentHarness, Role, Task
from agentic_trader.agentic.store import TaskStore

db = os.path.join(tempfile.mkdtemp(), "tasks.sqlite")
first = AgentHarness(TradingGraph(make_config(memory_path=None)), store=TaskStore(db))
run = first.run(Task("EURUSD", date(2024, 3, 1), Role.TRADER, 0.2))
first.close()                                                                           # stops its heartbeat
first.store.close()

second = AgentHarness(TradingGraph(make_config(memory_path=None)), store=TaskStore(db))   # "after a restart"
rec = second.record(run.id)
print(rec["state"], rec["decision"]["target_weight"], len(rec["evidence_rows"]), "evidence rows")
print(second.store.summaries())
```

`agentic-trader serve --task-db results/tasks.sqlite` does this for the API; `GET /tasks` lists
archived and live tasks and `GET /health` reports both counts.

### 63. Serve with TLS and real API keys

`serve` refuses to bind a non-loopback interface with the shipped development keys, and
warns about plain HTTP off loopback. Pass a certificate and key for TLS, and real keys in
the config (`api_keys` is replaced, not merged, so no dev key survives).

```python
from agentic_trader import make_config
from agentic_trader.agentic.api import serve_options, uses_dev_keys

dev = make_config()
print(uses_dev_keys(dev["agentic"]["api_keys"]))                        # True
real = make_config(agentic={"api_keys": {"k1-long-random-value": "trader", "k2-long-random-value": "risk"}})
print(uses_dev_keys(real["agentic"]["api_keys"]))                       # False: dev keys are gone
print(serve_options("127.0.0.1", dev))                                  # {} : loopback is fine
try:
    serve_options("0.0.0.0", dev)
except ValueError as e:
    print("refused:", str(e)[:60], "...")
```

```bash
agentic-trader serve --host 0.0.0.0 --ssl-cert cert.pem --ssl-key key.pem --task-db results/tasks.sqlite
```

### 64. Evaluate the extended universe and the reserve period

Every rule choice through v0.4 was made on the 15 *core* instruments. The 45 *extended* ones
(sector equities, rates / credit / commodity ETFs, FX crosses) and the `reserve` period were
the unseen data that judged the v0.5.1 carry rule and the v0.6 EDGAR and cross-sectional
decisions, and v0.8 re-measures every period under the corrected engine, so no held-out data
remains: the next unseen data is the future. Rows carry a `universe` tag so core and extended
can still be read separately.

```python
from agentic_trader import make_config
from agentic_trader.evaluation import PERIODS, UNIVERSES, evaluate, universe_group

print(len(UNIVERSES["core"]), len(UNIVERSES["extended"]), universe_group("GLD"), PERIODS["reserve"])
res = evaluate(["AAPL", "GLD", "EURGBP"], {"q": ("2024-01-02", "2024-02-29")}, make_config(), rebalance_every=10)
print(res.rows[["symbol", "universe", "strategy", "Sharpe", "Impact%"]].head(6))
print(res.summary(universe="extended"))
```

The published run is `agentic-trader evaluate --data yahoo --universe all --periods
design,holdout,q1_2024,reserve` *(network)*; `--universe core` reproduces the v0.3/v0.4 tables.

## v0.6: point-in-time filings, statistical power, calibration, operations

### 65. Point-in-time fundamentals and filing news from SEC EDGAR

The SEC's EDGAR API is free and keyless, and every fact carries the date it was *filed*, so a
backtest can see exactly what the market could. The SEC requires a contact in the User-Agent:
`EDGAR_USER_AGENT="Name email@domain"`. The `agentic-trader` CLI reads it from `.env`
(git-ignored); a Python script does not, so export it in the shell, pass
`make_config(..., edgar_user_agent="Name email@domain")`, or call
`agentic_trader.cli.load_dotenv()` first. With it, the Yahoo provider serves historical
fundamentals and a filing-stream news feed for every real-data equity; without it, both fall
back to the old behaviour with one warning. Per-share figures use the close *as traded* on the
date and EDGAR's prints rebased across every later stock split. Quarters are reconstructed per
XBRL tag and per reporting basis, as known at the as-of date, and a ratio whose inputs are
stale (a share count older than 400 days, a flow series ending more than a quarter before
the report) is absent rather than wrong.

```python
from datetime import date
from agentic_trader import Instrument, make_config
from agentic_trader.data import get_provider

from agentic_trader.cli import load_dotenv
load_dotenv()                                                                              # EDGAR_USER_AGENT from .env
p = get_provider(make_config(data_provider="yahoo", edgar_cache_dir="results/edgar_cache"))   # network
assert p.edgar is not None, "set EDGAR_USER_AGENT"
ins = Instrument.parse("AAPL")
p.history(ins, date(2022, 1, 1), date(2022, 12, 31))        # the close is needed for P/E and FCF yield
f = p.fundamentals(ins, date(2022, 6, 15))
print(f["report_period_end"], f["filed"], f["lag_days"], f["revenue_growth_yoy"], f["pe_ratio"], f["source"])
for item in p.news(ins, date(2022, 6, 15), 60):
    print(item.published, item.headline, item.sentiment)
```

The client itself is usable on its own — `EdgarClient(cache_dir=...).fundamentals("COST",
date(2023, 6, 15), price=500.0)` — and a `fetch` argument replaces the download for tests.
Funds and index ETFs return `{}`, and `eps_surprise` is `None`: EDGAR has no consensus data,
and the desk does not guess.

### 66. Rank a name against its peers: the cross-sectional analyst

The `xalpha` analyst z-scores the alpha library across a peer universe on every date, keeps
only alphas whose cross-sectional IC is significant, and reports where the name sits today.
Peers default to the core universe of the instrument's asset class; a mixed list is filtered
by asset class, so one setting serves equities and FX.

```python
from agentic_trader import TradingGraph, make_config
from agentic_trader.memory import DecisionMemory

cfg = make_config(analysts=["technical", "xalpha"], xalpha_universe=["AAPL", "MSFT", "NVDA", "META", "GOOGL", "AMZN", "JPM"])
g = TradingGraph(cfg, memory=DecisionMemory(None), on_event=lambda *_: None)
state, decision = g.propagate("AAPL", "2020-06-01")
r = state.reports["xalpha"]
print(r.abstained, round(r.signal, 3), r.summary)
print(r.facts["breadth"], r.facts["universe"][:4])
print({k: {m: round(x, 3) for m, x in v.items()} for k, v in list(r.facts["ic"].items())[:2]})   # IC, t(IC), n per alpha
```

The cross-section is computed once per (universe, date) and cached across instruments and
threads, so an evaluation over the whole universe pays for it once per decision date. Whether
it is on by default is decided by the protocol, not by taste: see the evaluation.

### 67. Is the edge real across instruments? The paired bootstrap

The time-series bootstrap asks whether one instrument's Sharpe is real. Across a universe the
question is different: is the *mean* difference between two strategies more than the luck of
which instruments were drawn? `paired_bootstrap` resamples instruments with replacement, pairs
kept together. With five or more (asset class, universe) groups it draws whole groups first
and instruments within them (`scheme=clusters`, so a shock shared by a group counts once);
below that it is the plain instrument bootstrap (`scheme=instruments`), and the table's
`scheme` and `groups` columns say which. Every evaluation prints the table, with
Benjamini-Hochberg `significant` flags computed on the unrounded p-values.

```python
import numpy as np
from agentic_trader import make_config
from agentic_trader.evaluation import evaluate
from agentic_trader.stats import paired_bootstrap

rng = np.random.default_rng(1)
base = rng.normal(0.5, 0.3, 30)                                                # 30 instruments' Sharpes
print(paired_bootstrap(base + rng.normal(0.02, 0.3, 30), base))                # a small edge lost in the noise
print(paired_bootstrap(base + 0.25 + rng.normal(0, 0.05, 30), base).significant)

res = evaluate(["AAPL", "MSFT", "NVDA", "META", "GOOGL", "EURUSD", "USDJPY"], {"q": ("2024-01-02", "2024-03-28")},
               make_config(), rebalance_every=10)
print(res.paired_table())                                                      # per period and baseline
print(res.paired("B&H vol-target", metric="MDD%", period="q"))                 # any metric column
```

### 68. Measure the model's own variance with repeated runs

Ask the same model the same question three times and the answers differ. `repeats` runs the
agent that many times per (period, symbol) — the baselines once — tags every row with `run`,
and `run_dispersion` reports the across-run spread. Offline the rules are deterministic, so the
dispersion is zero; with `--llm anthropic` it is the number you want before reading any
single-run difference.

```python
from agentic_trader import make_config
from agentic_trader.evaluation import AGENT, evaluate

res = evaluate(["AAPL", "EURUSD"], {"q": ("2024-01-02", "2024-02-29")}, make_config(), rebalance_every=10, repeats=3)
print(res.rows[res.rows.strategy == AGENT][["symbol", "run", "Sharpe"]])
print(res.run_dispersion())
```

```bash
agentic-trader evaluate AAPL,NVDA --data yahoo --periods holdout --every 10 --repeats 3 --llm anthropic --anonymize --max-llm-cost 50
```

### 69. Calibrate the desk: dispersion, anchoring, drift

One frozen state, `n` runs per anchor. Dispersion is the spread of the target weight at one
anchor; anchoring is the slope of the mean target on the position the desk is told it already
holds; drift is the comparison against a stored report on the same state after a model or
prompt change.

```python
from agentic_trader import TradingGraph, make_config
from agentic_trader.calibration import CalibrationReport, calibrate
from agentic_trader.memory import DecisionMemory

g = TradingGraph(make_config(), memory=DecisionMemory(None), on_event=lambda *_: None)
rep = calibrate(g, "AAPL", "2024-03-01", n=2, anchors=(None, -0.5, 0.0, 0.5))
print(rep.samples[["anchor", "run", "action", "target_weight"]].to_string(index=False))
print(rep.dispersion(None))            # std 0, agreement 1: the rules are deterministic
print(rep.anchoring())                 # slope of target on anchor
rep.to_json("results/calibration_rules.json")
print(rep.compare(CalibrationReport.from_json("results/calibration_rules.json"))["same_prompts"])
```

```bash
agentic-trader calibrate AAPL --date 2024-03-01 --n 5 --anchors none,-0.5,0,0.5 --llm anthropic --anonymize --deep-effort medium --max-llm-cost 10 --out results/calibration_opus.json
```

### 70. Pin the prompts: the registry hash

Every evaluation and calibration record carries a hash of every agent's system prompt and
prompt-building code, so two results can be shown to have used identical wording.

```python
from agentic_trader import make_config
from agentic_trader.prompts import prompt_bundle_hash, prompt_registry

reg = prompt_registry(make_config())
print(reg["bundle"], len(reg["agents"]))
print(reg["agents"]["trader"], reg["agents"]["analyst:news"])
assert prompt_bundle_hash(make_config(lookback_days=10)) == reg["bundle"]      # config knobs are not prompts
```

### 71. Serve with a bounded task pool and several processes

Tasks run on a pool of `agentic.workers` threads per process; when `agentic.queue_limit` tasks
are in flight, `POST /tasks` answers `503` with `Retry-After` instead of opening another thread
and another LLM budget. Several processes share one task store.

```python
from fastapi.testclient import TestClient
from agentic_trader import TradingGraph, make_config
from agentic_trader.agentic import AgentHarness
from agentic_trader.agentic.api import create_app, multiprocess_options

h = AgentHarness(TradingGraph(make_config(memory_path=None)))
c = TestClient(create_app(harness=h, workers=2, queue_limit=0))
print(c.get("/health").json()["workers"], c.post("/tasks", json={"symbol": "AAPL", "as_of": "2024-03-01"},
                                                 headers={"X-API-Key": "dev-trader-key"}).status_code)   # 503
try:
    multiprocess_options(2, make_config())
except ValueError as e:
    print("refused:", str(e)[:50], "...")
print(multiprocess_options(2, make_config(agentic={"task_db": "results/tasks.sqlite"})))
```

```bash
agentic-trader serve --processes 4 --workers 4 --task-db results/tasks.sqlite --host 127.0.0.1
```

### 72. Check the docs the way CI does

```bash
python scripts/run_cookbook.py --offline      # every recipe in a fresh process; --offline skips the network ones
python scripts/check_mermaid.py               # mermaid-cli renders every diagram (or --html for a browser page)
python scripts/check_links.py                 # every relative link and anchor; --external requests the URLs too
```
