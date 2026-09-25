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
  9. [Backtest against the paper's baselines](#9-backtest-against-the-papers-baselines)
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

### 9. Backtest against the paper's baselines

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
