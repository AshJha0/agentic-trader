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
equity premium) and FX 0.0 (flat). Use 0 for an absolute-return mandate that should sit in
cash without a view.

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
On real 2016–2021 data, stops lowered returns at a similar Sharpe, which is why they are
off by default.

### 31. Backtest a multi-asset portfolio

Each symbol is a sleeve with 1/N of the capital and its own costs, carry and positions. The
portfolio return is the daily mean of the sleeves, and equity and FX calendars are aligned.

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
the queued gateway the call parks until a person decides.

```python
from datetime import date
from agentic_trader import TradingGraph, make_config
from agentic_trader.agentic import AgentHarness, QueuedApprovalGateway, Role, Task
from agentic_trader.memory import DecisionMemory

h = AgentHarness(TradingGraph(make_config(), memory=DecisionMemory(None), on_event=lambda *_: None),
                 gateway=QueuedApprovalGateway())
run = h.submit(Task("AAPL", date(2024, 3, 1), Role.TRADER))
ex = h._executor(run)
first = ex.call("execution.submit_order", symbol="AAPL", side="buy", quantity=100)
print(first.ok, first.error)
pending = h.pending_approvals(run.id)
print([(a.id, a.request.tool, a.reason) for a in pending])
h.gateway.resolve(pending[0].id, approve=True, decided_by="risk", note="within limits")
second = ex.call("execution.submit_order", symbol="AAPL", side="buy", quantity=100)
print(second.ok, second.payload)          # the ticket; no broker is involved
```

### 43. Write a policy rule

A rule is a callable that returns a decision or `None` to pass. Put it before `allow_rule`.

```python
from agentic_trader.agentic import PolicyEngine, PolicyOutcome, Role
from agentic_trader.agentic.domain import PolicyDecision, ToolRequest
from agentic_trader.agentic.policy import DEFAULT_RULES, allow_rule
from agentic_trader.agentic import DeskTools, build_registry
from agentic_trader import make_config
from agentic_trader.data import SyntheticProvider

def no_fx_after_hours(ctx):
    """Deny FX order tickets outside the desk's hours (the hour comes from the arguments here)."""
    if ctx.tool.name == "execution.submit_order" and ctx.request.arguments.get("note", "").startswith("after-hours"):
        return PolicyDecision(PolicyOutcome.DENY, "desk_hours", "no order tickets after hours")
    return None

rules = tuple(r for r in DEFAULT_RULES if r is not allow_rule) + (no_fx_after_hours, allow_rule)
engine = PolicyEngine({"max_position": 1.0}, rules=rules)
cfg = make_config()
tool = build_registry(DeskTools(SyntheticProvider(cfg), cfg)).get("execution.submit_order").descriptor
d = engine.evaluate(ToolRequest("execution.submit_order", {"symbol": "EURUSD", "side": "buy", "quantity": 1, "note": "after-hours"}, "C"), tool, Role.TRADER)
print(d.outcome.value, d.rule, d.reason)
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
agentic-trader mcp                        # stdio server for any MCP client
```

```python
from agentic_trader.agentic import EvidenceStore, PolicyEngine, Role, ToolExecutor
from agentic_trader.agentic.mcp_server import call, discover, registry_from_stdio

tools = discover()
print(len(tools), tools[1]["name"], tools[1]["read_only"])
print(call("knowledge__list_documents", {}))
reg = registry_from_stdio()                              # remote tools as a local registry
ex = ToolExecutor(reg, PolicyEngine({"max_position": 1.0}), EvidenceStore(), Role.TRADER)
r = ex.call("quant.technical", symbol="AAPL", as_of="2024-03-01")
print(r.ok, round(r.payload["rsi14"], 1), "evidence:", len(ex.evidence))   # policy and evidence apply to remote tools
```

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
print(rep.table[["IC", "t(IC)", "hit%", "autocorr"]])
print(rep.decay)                                          # IC by horizon: pick the rebalance frequency
print(rep.correlations.round(2))
print("best by IC:", rep.best())
```

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

The alpha analyst is off by default because it measured as noise on the design period
(see the evaluation). Adding a new alpha changes the composite, so re-run `evaluate` on the
design period before adopting it.

### 53. Plan and simulate an execution

```python
from datetime import date
from agentic_trader import Instrument, make_config
from agentic_trader.algo import plan_execution, simulate_execution, synthetic_intraday_bars
from agentic_trader.data import SyntheticProvider
from agentic_trader.state import Action, FinalDecision

p = SyntheticProvider(make_config())
ins = Instrument.parse("AAPL")
df = p.history(ins, date(2024, 1, 1), date(2024, 3, 1))
last, adv = float(df["Close"].iloc[-1]), float(df["Volume"].tail(20).mean())
decision = FinalDecision("AAPL", date(2024, 3, 1), Action.BUY, 0.6, 0.5, None, None, "")
plan = plan_execution(decision, ins, current_weight=0.1, capital=50_000_000, last_price=last, adv=adv)
print(plan.side, round(plan.quantity), plan.algo, plan.slices, plan.reason)
bars = synthetic_intraday_bars(df.iloc[-1], plan.slices, "equity", seed=1)
rep = simulate_execution(plan.schedule(bars), bars, plan.side, plan.algo, spread_bps=2.0, impact_coeff=1.0,
                         daily_vol=float(df["Close"].pct_change().tail(20).std()), adv=adv)
print(f"filled {rep.completion:.0%}; IS {rep.is_bps:+.1f} bps; vs VWAP {rep.vs_vwap_bps:+.1f} bps; "
      f"spread {rep.spread_cost_bps:.1f} + impact {rep.impact_cost_bps:.1f} bps; max participation {rep.max_participation:.1%}")
```

CLI: `agentic-trader execute AAPL --date 2024-03-01 --target 0.6 --current 0.1 --capital 50000000`.

### 54. Compare execution algorithms on the same day

```python
from datetime import date
import numpy as np
from agentic_trader import Instrument, make_config
from agentic_trader.algo import (almgren_chriss_schedule, pov_schedule, simulate_execution,
                                 synthetic_intraday_bars, twap_schedule, vwap_schedule)
from agentic_trader.data import SyntheticProvider

p = SyntheticProvider(make_config())
df = p.history(Instrument.parse("NVDA"), date(2024, 2, 1), date(2024, 3, 1))
day = df.iloc[-1]
adv = float(df["Volume"].tail(20).mean())
qty = 0.02 * adv                                            # a 2%-of-ADV order
for seed in (1, 2, 3):
    bars = synthetic_intraday_bars(day, 78, "equity", seed)
    vols = bars["Volume"].to_numpy()
    sigma = float(bars["Close"].std())
    for name, sched in (("TWAP", twap_schedule(qty, 78)), ("VWAP", vwap_schedule(qty, vols)),
                        ("POV 10%", pov_schedule(qty, vols, 0.10)),
                        ("AC", almgren_chriss_schedule(qty, 78, sigma, eta=sigma * 1e-6, risk_aversion=1e-5))):
        r = simulate_execution(sched, bars, "buy", name, 2.0, 1.0, 0.02, adv)
        print(f"seed {seed} {name:<8} filled {r.completion:5.0%}  IS {r.is_bps:+6.1f} bps  vs VWAP {r.vs_vwap_bps:+6.1f} bps")
```

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
does the same from a CSV. The evaluation applies this to the desk's own 16-variant rule search.

## v0.5: execution-aware evaluation, cross-sectional research, operations

### 57. Backtest with market impact at three account sizes

Backtests assume costless closes-to-close fills unless you say otherwise. `costs.impact_coeff`
charges the execution simulator's square-root impact per trade, to the agent and to every
baseline, and trade sizes scale with `initial_capital`, so the same strategy gets cheaper or
dearer with the account. `Impact%` is the cumulative cost paid.

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
cache-aware) and is checked before every call, so the overshoot is at most one call.

```python
from agentic_trader import TradingGraph, make_config
from agentic_trader.llm import BudgetedLLM, ModelUsage, UsageTracker

class Priced:                                   # stands in for AnthropicLLM: 16k output tokens per call
    def __init__(self):
        self.usage = UsageTracker()
    def complete(self, system, prompt, *, deep):
        u = self.usage.by_model.setdefault("claude-opus-5", ModelUsage())
        u.calls += 1
        u.output_tokens += 16_000
        return '{"signal": 0.4, "confidence": 0.5, "summary": "ok"}'

llm = BudgetedLLM(Priced(), max_cost_usd=1.0)
for _ in range(6):
    llm.complete("system", "prompt", deep=True)
print(f"calls {llm.calls}, refused {llm.refused}, spent ${llm.spent_usd:.2f}, exhausted {llm.exhausted}")

g = TradingGraph(make_config(max_llm_cost_usd=0.0), llm=Priced())   # a zero budget: rules only
print(g.propagate("AAPL", "2024-03-01")[1].source)
```

`agentic-trader evaluate --llm anthropic --max-llm-cost 25 --max-llm-calls 2000` *(API key)*
stops at whichever cap comes first.

### 62. Keep tasks across restarts

Without a store the harness forgets every task when the process ends. `agentic.task_db`
writes each run to SQLite at every state transition; a new process serves the old records
through the same API, and anything left mid-flight is failed, not resumed.

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
(sector equities, rates / credit / commodity ETFs, FX crosses) were never consulted, so they
are out of sample on every period, and the `reserve` period is untouched by every published
number. Rows carry a `universe` tag so the two can be read separately.

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
