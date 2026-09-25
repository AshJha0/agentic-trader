# Learn agentic-trader

This guide works through the ideas behind the project in order. For each concept it gives the
idea, where the repository implements it, the real numbers it produces, and questions to test
your understanding. Recipes are in [COOKBOOK.md](COOKBOOK.md); component detail is in
[docs/architecture/overview.md](docs/architecture/overview.md); the measured results are in
[docs/evaluation/evaluation.md](docs/evaluation/evaluation.md).

**Part I — the trading firm**

1. [Why a multi-agent trading firm?](#1-why-a-multi-agent-trading-firm)
2. [Structured communication](#2-structured-communication)
3. [The analyst team](#3-the-analyst-team)
4. [Debate as a decision mechanism](#4-debate-as-a-decision-mechanism)
5. [From view to trade: strategic weight and tilt](#5-from-view-to-trade-strategic-weight-and-tilt)
6. [Risk: volatility targeting, VaR, and who has the last word](#6-risk-volatility-targeting-var-and-who-has-the-last-word)
7. [Where the LLM sits, and where it does not](#7-where-the-llm-sits-and-where-it-does-not)
8. [Equity vs FX](#8-equity-vs-fx)

**Part II — trading it for real**

9. [Backtesting without fooling yourself](#9-backtesting-without-fooling-yourself)
10. [Performance metrics](#10-performance-metrics)
11. [Stops, gaps and the no-trade band](#11-stops-gaps-and-the-no-trade-band)
12. [From single names to a portfolio](#12-from-single-names-to-a-portfolio)
13. [Memory and reflection](#13-memory-and-reflection)
14. [Edge cases a production system must survive](#14-edge-cases-a-production-system-must-survive)

**Part III — knowing whether it works**

15. [Designing an honest evaluation](#15-designing-an-honest-evaluation)
16. [Is a Sharpe ratio real?](#16-is-a-sharpe-ratio-real)
17. [C++ core with a Python twin](#17-c-core-with-a-python-twin)
18. [Reading the results honestly](#18-reading-the-results-honestly)

---

# Part I — the trading firm

## 1. Why a multi-agent trading firm?

**Idea.** Real trading desks split work between specialists: analysts, researchers, traders,
risk managers and a portfolio manager. Each role has a narrow job and a different incentive.
The TradingAgents paper (Xiao et al., 2024) argues that LLM agents organised the same way make
better, more explainable decisions than one model asked "should I buy?".

**In the repo.** `TradingGraph.propagate()` in `graph.py` runs 12 agents in a fixed order:

- 4 analysts
- a bull researcher, a bear researcher and a facilitator
- a trader
- aggressive, neutral and conservative risk analysts
- a portfolio manager

The order is fixed on purpose: agents never control the workflow, only their own output.

**Numbers.** One decision takes about 3–4 ms offline on the C++ backend. At default settings
it needs 14 LLM calls when Claude is enabled, or 13 when one analyst has no data.

**Questions.**
- What does a fixed pipeline give up compared with letting an LLM planner choose the next
  agent? What does it gain?
- Which role would you remove first if LLM calls were expensive, and why?

## 2. Structured communication

**Idea.** If agents pass free text along a chain, details degrade at every hop (the
"telephone effect"). The paper instead has agents write concise structured documents into a
shared global state, and uses dialogue only where argument is the point: the debates.

**In the repo.** `state.py` defines `AnalystReport`, `DebateOutcome`, `TradeProposal`,
`RiskView` and `FinalDecision`. Downstream agents read `state.reports_digest()`, a compact
view of every report, and never the transcripts. The state also carries portfolio context
(`current_weight`). `to_markdown()` turns the whole state into an audit trail.

**Questions.**
- Why must each report carry a *confidence* as well as a *signal*?
- What would you lose if the trader read the raw debate transcript instead of the
  facilitator's verdict?

## 3. The analyst team

**Idea.** Each analyst turns one kind of raw data into a signal in [-1, 1] and a confidence in
[0, 1]. When it has no data at all, it abstains rather than inventing a view.

**In the repo** (`agents/analysts.py`):

| Analyst | Inputs (tools) | Rule-based view |
|---|---|---|
| Technical | SMA 20/50/200, MACD, RSI, Bollinger %B, KDJ, ATR, 20-day vol-adjusted momentum; optional 12-1 month momentum | Trend (±0.30, ±0.20) + MACD (±0.15) + momentum (0.15·tanh) ± overbought/oversold |
| Fundamentals (equity) | P/E vs sector, revenue growth, net margin, D/E, FCF yield, EPS surprise, insiders | Value tilt + tanh-scaled quality and growth terms; negative earnings count against |
| Macro (FX) | Point-in-time policy-rate differential, inflation differential, distance from the 200-day average | Carry 0.5·tanh(Δr/1.5) − PPP drag − mean reversion |
| News | Headlines in the last 7 days | Lexicon tone with negation, 2-day recency half-life, tanh(2·tone) |
| Sentiment | Social posts, RSI extremes, volume spikes | Crowd tone + contrarian flag at RSI > 78 or < 22 |

**Abstaining.** `AnalystReport.abstained` marks "no data" (no news in the window, no
point-in-time fundamentals, no rates for the pair). An abstaining analyst makes no LLM call:
there is nothing to analyse, and an empty input invites the model to invent a view. With
`rules.abstain_without_data` it is also left out of the consensus. That switch sounds
obviously right, but it measured as noise on real data (section 15), so it is off by default.

**Try it.** Cookbook recipe 2 prints every report for one decision.

**Questions.**
- Why use `tanh` to squash terms instead of clipping them?
- Counting a missing data source as a zero signal pulls every consensus towards "no view".
  Why might that *help* a strategy anyway? (Hint: section 5.)

## 4. Debate as a decision mechanism

**Idea.** Forcing a bull and a bear to argue brings out evidence that one "balanced"
analysis tends to smooth over. A facilitator then decides who made the better case.

**In the repo.** `researchers.py`: the bull and bear speak for `max_debate_rounds` (default
2, so 4 turns). Each cites its strongest supporting reports and rebuts the other side's
weakest evidence. The facilitator computes a confidence- and role-weighted consensus:

> score = Σ wᵢ · confᵢ · signalᵢ / Σ wᵢ · confᵢ

It declares `bull` or `bear` when |score| > `decision_threshold` (0.10), otherwise
`balanced`, and sets conviction = |score| · (0.5 + mean confidence).

**Questions.**
- In offline mode the facilitator's verdict is a weighted average, so the debate text does
  not change the number. What would have to be true for the LLM debate to add value over
  that average?
- How would you detect a facilitator that always sides with the last speaker?

## 5. From view to trade: strategic weight and tilt

**Idea.** A view ("mildly bullish") is not a trade. The trader must choose a size, an exit
if wrong (stop), an exit if right (target) and a horizon. It must also decide **what to hold
with no view at all.** A real mandate has a benchmark: an equity fund with no strong opinion
holds the index, it doesn't sit in cash. Active management is a *tilt* around that
benchmark.

**In the repo** (`agents/trader.py`):

- **Weight:** `neutral + 2·score` when |score| exceeds the threshold, else `neutral`,
  clipped to [-1, 1] and floored at 0 for equities unless shorting is allowed.
- **Neutral weight:** `risk.neutral_weight` sets it per asset class: equities 1.0 (fully
  invested), FX 0.0 (flat).
- **Stop and target:** 2 × ATR14 and 3 × ATR14 from the entry price. If a model supplies a
  level on the wrong side of the entry, it is replaced (`sane_levels`).
- **Track record:** the size is cut 25% when memory shows a hit rate below 40% over at least
  5 calls.

**Why equities 1.0 and FX 0.** Equities carry a long-run risk premium, so a flat position
with no view forfeits it every day. Currencies have no comparable premium apart from carry,
which the macro analyst already scores.

**Numbers.** On real 2016–2021 data, raising the equity neutral weight from 0 to 0.25, 0.5
and 1.0 moved equity median Sharpe from 0.68 to 0.79, 0.87 and 1.06. That was the only
change that clearly helped. It helps by *collecting the premium*, not by forecasting better.

**Questions.**
- With a 2-ATR stop and a 3-ATR target, what hit rate breaks even before costs?
- The strategic weight raised returns far more than Sharpe out of sample. Why is that
  exactly what you'd expect from a benchmark choice?

## 6. Risk: volatility targeting, VaR, and who has the last word

**Idea.** The same signal should mean a smaller position in a more volatile asset. Tail risk
needs a hard ceiling. And one party must be able to say no.

**In the repo** (`agents/risk.py`):

- **Neutral analyst:** `w · target_vol / realised_vol` (volatility targeting, 15% annual).
- **Aggressive analyst:** max(1.25·|w|, |vol-target w|).
- **Conservative analyst:** ½·min(|w|, |vol-target w|), then capped so that
  VaR95 × |w| ≤ 2%.
- **Portfolio manager:** blends 25/50/25, or takes Claude's call, then applies the firm
  limits in order: shorting policy, max position 1.0, 1-day VaR95 cap 2%, minimum trade 0.05.
  After that comes the **no-trade band** (section 11). Every adjustment is logged in
  `FinalDecision.adjustments`.

**Numbers.** In the sample AAPL decision the trader proposed +1.00, the risk team said
aggressive +1.00, neutral +0.46 and conservative +0.23, and the PM decided +0.54.

**Questions.**
- Historical VaR from 250 days of returns: what does it miss that CVaR catches?
- Why must the limits run *after* the LLM rather than be stated in its prompt?

## 7. Where the LLM sits, and where it does not

**Idea.** LLMs are good at weighing heterogeneous evidence and explaining a decision. They
are unreliable calculators, and a trading system must survive the model being wrong, down,
expensive, or manipulated.

**In the repo.** Every agent follows three steps (`agents/base.py`):

1. **Tools.** Deterministic numbers come from the C++ core and the providers.
2. **Rules.** The agent always computes a rule-based answer.
3. **LLM.** When enabled, Claude sees the same facts and returns JSON. Missing keys,
   non-JSON output, API errors or a refusal all fall back to the rules. Values are clipped
   to valid ranges, and "inf", "nan" and strings are coerced or rejected.

The defences around that core:

- **Prompt injection.** Headlines and social posts are third-party text. They reach the
  model only inside `<untrusted_data>` blocks, and the system prompt tells the model to
  treat them as data. `untrusted_block()` neutralises any attempt to open or close the tag
  from inside, so a crafted headline cannot end the block and smuggle instructions out. Even
  a fully hijacked reply is harmless to size, because the limits run afterwards. The tests
  feed injected headlines and a model that returns `1e9`, `"inf"` and a negative stop.
- **Cost.** `max_llm_calls` wraps the model in `BudgetedLLM`. Past the cap every call
  returns `None` and the agents use their rules, so a backtest cannot run up an unbounded
  bill. Requests also time out (`llm_timeout_s`).
- **Tiers.** `claude-haiku-4-5` handles analysts; `claude-opus-5` with adaptive thinking
  handles the reasoning roles.

**Try it.** Cookbook recipes 17, 18 and 36.

**Questions.**
- Why is "fall back to rules" safer than "retry until valid JSON"?
- Injection can still bias a direction *within* the limits. What additional control would
  catch a consistently manipulated analyst? ([Threat model](docs/threat-model/threat-model.md), T6.)

## 8. Equity vs FX

**Idea.** The agent structure carries over between asset classes, but the finance does not.

**In the repo.** The differences are confined to a few places:

| | Equity | FX |
|---|---|---|
| Value analyst | Company fundamentals | Rates carry, inflation (PPP), long-run valuation |
| Macro data | — | Point-in-time FRED policy rates and CPI (section 9) |
| News orientation | The headline's subject is the stock | Scored from the **base** currency's view: "JPY weakens" is bullish USD/JPY |
| Strategic weight | 1.0 (risk premium) | 0.0 |
| Shorting | Off by default | On |
| Costs | bps commission + slippage, borrow on shorts | Half-spread in pips → bps at the first price, plus slippage |
| Financing | Borrow fee | Carry: (base rate − quote rate), accrued per bar from the rates known that day |
| Periods per year | 252 | 260 |

**Numbers.** USD/JPY carry in January 2024 was +5.34% p.a. (Fed funds 5.33%, BoJ −0.01%).
The illustrative static table would have said +3.75%.

**Questions.**
- Why does a long USD/JPY position *earn* carry when US rates exceed Japanese rates?
- The agents' FX results are close to zero in every period. Which analyst would you improve
  first, and with what data?

# Part II — trading it for real

## 9. Backtesting without fooling yourself

**Idea.** Most impressive backtests are look-ahead bugs. Information must be used only after
it existed, and a signal must not earn the return of the bar that produced it.

**In the repo:**

- **Price history:** providers return data only up to `as_of`, and the graph clips again.
- **Fundamentals:** synthetic fundamentals publish 30 days after quarter end. Yahoo's
  current-snapshot fundamentals are *refused* for past dates.
- **FX macro (`data/fred.py`):** each FRED value becomes visible only after its publication
  lag: 1 day for daily rates, about 40 days for monthly averages, about 45 days for monthly
  CPI and about 120 days for quarterly CPI. A series whose latest visible value is older
  than its maximum age is *unavailable*: several OECD series stopped updating in 2024, and a
  2021 value must not stand in for 2024. On real data, today's illustrative static table is
  never used for old dates.
- **News:** it is filtered to `published <= as_of` twice.
- **Memory:** an outcome is resolved only after its horizon has passed.
- **Timing:** a weight decided at close *t* earns *t → t+1*. `test_no_lookahead_timing`
  checks that a weight set on the last bar earns nothing.
- **Costs:** the FX spread is converted to bps at the window's *first* price, not the
  window average, which would use prices not yet seen.

**Questions.**
- Daily timestamps: can news published after the close on day *t* leak into day *t*'s
  decision? (Yes. See threat T3.)
- FRED serves the *latest vintage* of each series. When does that matter, and what would
  fix it? (Revised CPI; ALFRED vintages.)

## 10. Performance metrics

**Idea.** Return alone says little. The paper reports cumulative return, annualised return,
Sharpe and maximum drawdown. This project adds volatility, Sortino, Calmar, win rate,
**exposure**, **trades** and the **Sharpe t-statistic**.

**In the repo.** `compute_metrics` in `cpp/src/backtest.cpp`; formulas are in
[docs/evaluation/evaluation.md](docs/evaluation/evaluation.md#metrics).

**Numbers.** NVDA, Q1 2024: buy & hold made +87.6%, an annualised return of +1303%. That
shows why a one-quarter annualised return misleads.

**Questions.**
- Why use ddof = 1 for the Sharpe denominator but a population estimator for rolling
  indicator windows?
- Two strategies have the same Sharpe but exposures of 40% and 100%. What else do you need
  to know before choosing?

## 11. Stops, gaps and the no-trade band

**Idea.** A protective stop is only as good as its fill. Markets gap: a stock can close at
100 and open at 90, straight through a 95 stop. And every rebalance costs spread, so a
target that moved from 0.54 to 0.50 isn't worth trading.

**In the repo:**

- **Stop fills** (`run_backtest_ex` in C++ and its numpy twin). A position held over
  (t, t+1] with a stop or target is checked against bar t+1:
  - it fills at the level if the level trades inside the bar;
  - it fills at the open if the market gaps through the level;
  - if both levels trade in one bar, the stop is assumed first (daily bars can't show
    which came first, so the engine takes the pessimistic side);
  - after an exit the position stays flat until the next rebalance re-arms it;
  - the exit costs the usual bps.
- **No-trade band** (`PortfolioManager.no_trade_band`). If the new target is within
  `rebalance_band` (0.10) of the current position, the position is kept, but only when it
  passes every firm limit today. The band can't hold a position the VaR cap now forbids.

**Numbers** (real prices, 2016–2021):

- The band gave the same Sharpe with 44% fewer trades (231 → 130).
- Stops lowered mean return by about 30% at a similar Sharpe, so they are available
  (`backtest.use_stops`) but off by default.

**Questions.**
- Why is "stop first when both trade" the right default, and what data would let you drop
  the assumption?
- The band makes the result depend on the path (what you held before). Why is that
  realistic rather than a flaw?

## 12. From single names to a portfolio

**Idea.** Individual strategies are noisy; diversification across unrelated instruments is
the one free lunch.

**In the repo.** `run_portfolio_backtest` gives each symbol an equal-capital sleeve with its
own costs, carry, stops and positions, and averages the daily returns. A sleeve with no bar
on a date (equity holidays vs FX) contributes 0. `TradingGraph.scan` is the live
counterpart: one decision per symbol, with the current positions, and an error row instead
of a crash for a bad ticker.

**Numbers.** On the 2022–2026 holdout, the 15-sleeve portfolio of rule-based agents had a
Sharpe of 1.14 (t = 2.41). Buy & hold had 1.06 and vol-targeted buy & hold 1.24. The
agents' drawdown was 6.8% against 20.8%. Per instrument, the agents' mean Sharpe was only
0.44.

**Questions.**
- Why is the portfolio Sharpe (1.14) so much higher than the average instrument Sharpe
  (0.44)?
- Equal capital per sleeve gives a 15%-vol stock and an 8%-vol currency very different risk
  weights. How would you change it to equal *risk*?

## 13. Memory and reflection

**Idea.** A desk that never reviews its calls repeats its mistakes. Reflection feeds realised
outcomes back into later decisions.

**In the repo.** `memory.py` logs each decision. It writes to a temporary file and then
renames it, so a crash can't leave a half-written log, and a corrupt line is skipped with a
warning instead of breaking every later run. Once a decision's horizon passes, the memory
attaches the P&L (weight × price return) and a one-line lesson. Later runs receive the last
3 lessons and a hit-rate track record, which the trader uses to size down.

**Questions.**
- Why does `lessons()` filter on the *resolution* date and not the decision date?
- How could memory introduce selection bias into a backtest, and how does resetting it per
  run avoid that?

## 14. Edge cases a production system must survive

**Idea.** The happy path is the easy 10%. A trading system meets holidays, bad ticks,
typos, dead feeds and broken files every week, and each must either be handled or refused
loudly.

**In the repo** (each has a test):

| Situation | Behaviour |
|---|---|
| Weekend or holiday `as_of` | Decides on the last close (Friday) |
| Feed stopped (delisting, outage) | Refused if the last bar is more than `max_data_staleness_days` (7) old |
| Fewer than 30 bars | Refused with the bar count |
| Mistyped pair (`EUR/XYZ`) | Refused. A "/" or "=X" signals FX intent, so it can't silently become an equity ticker |
| Invalid ticker characters | Refused (`AA$PL`, spaces, over-long symbols) |
| CSV unsorted, duplicate dates, blank closes, High < Close | Cleaned by `clean_ohlcv` |
| Flat prices (zero volatility) | Vol targeting gives 0, not a division error; the VaR cap is skipped at zero VaR |
| NaN target weights | Treated as flat |
| Non-finite `current_weight` | Refused |
| Model returns `inf`, `nan`, strings, lowercase actions, stops on the wrong side | Clipped, coerced or replaced |
| Corrupt memory line | Skipped with a warning |
| One bad symbol in a watchlist | An `ERROR` row; the scan continues |
| Any of the above from the CLI | Exit status 2 and a one-line `error:`; no traceback |

**Questions.**
- Why refuse stale data rather than warn and continue?
- Which of these would you want paged about in production, and which only logged?

# Part III — knowing whether it works

## 15. Designing an honest evaluation

**Idea.** If you try enough rule tweaks on the data you report, one will look good by
chance. The defence is procedural:

1. Choose everything on a **design** period.
2. **Freeze** the rules.
3. Run a **holdout** period **once**, and report it whatever it shows.

**In the repo** (`evaluation.py`, the `evaluate` command):

- **Periods:** design 2016–2021, holdout 2022 to mid-2026, and the paper's Q1 2024 window.
- **Universe:** 10 equities (the paper's names plus other sectors and SPY) and 5 FX pairs.
- **Before/after:** `RULES_V02` reproduces the old rules exactly, so the comparison is
  fair.

**What happened (v0.3):**

1. **The ablation.** Sixteen variants were run on the design period.
2. **Signal tweaks.** Three literature-backed tweaks moved mean Sharpe by no more than
   ±0.02, which is noise across 15 instruments: 12-1 month momentum (Moskowitz, Ooi and
   Pedersen), trend-filtered reversals and abstention.
3. **What was adopted.** Only the strategic weight clearly helped, and the band cut trades
   at no cost. Those two were adopted and everything else stayed off.
4. **The holdout.** Equity mean Sharpe went from 0.60 to 0.63 (on the design period it had
   gone from 0.76 to 0.99). Return rose from 30% to 47%. Trades halved.

**Questions.**
- The design-period Sharpe gain mostly vanished out of sample while the return gain
  survived. Explain why, using section 5.
- Having seen the holdout, may you now tune against it? What would you need instead?

## 16. Is a Sharpe ratio real?

**Idea.** A Sharpe ratio is an estimate with an error bar. Beating buy & hold can also mean
simply holding less. Two tools answer both points:

- **The t-statistic.** `t(SR) = mean / std · √n`, about annual Sharpe × √years. Around 2 is
  needed before a Sharpe ratio is distinguishable from 0. A Sharpe of 5.5 over one quarter
  has t ≈ 2.7. A Sharpe of 0.6 over four and a half years has t ≈ 1.3.
- **The volatility-matched control.** `B&H vol-target` holds the asset scaled to the risk
  team's 15% target from *trailing* volatility (no look-ahead). A risk-managed strategy
  beats plain buy & hold on drawdown just by holding less; beating this control requires
  good directional calls.

**Numbers.** On the holdout, the agents' portfolio beat plain buy & hold on Sharpe (1.14 vs
1.06) but not the vol-targeted control (1.24). The honest reading is that most of the
agents' risk-adjusted performance comes from *sizing*, not from *direction*.

**Try it.** Cookbook recipes 33 and 34.

**Questions.**
- Why is the vol-targeted control ex ante (trailing vol) rather than scaled to the agent's
  realised volatility after the fact?
- What sample would you need to show a Sharpe difference of 0.1 is real?

## 17. C++ core with a Python twin

**Idea.** Performance-critical numerics belong in a compiled language, but a research package
should still work without a compiler. And two implementations are only useful if they are
proven identical.

**In the repo.** `cpp/` is a C++17 static library with pybind11 bindings. `quant/pycore.py`
is a line-for-line numpy mirror. `quant/__init__.py` picks C++ when `_atcore` imports, and
`AGENTIC_TRADER_BACKEND=python` forces numpy. CI builds with GCC, MSVC and Clang and asserts
which backend is active. It cross-checks every indicator and strategy, plus eight randomised
extended backtests covering stops, gaps, carry, re-arming and shorts, to 1e-11.

**Questions.**
- The cross-check test *skips* when the extension is missing. Why is the explicit backend
  assertion in CI essential?
- The first CI run found a real bug: integer window sizes were converted to floats before
  reaching C++. Why did the numpy path never hit it?

## 18. Reading the results honestly

**What was measured** (rule-based agents, real prices, frozen v0.3 rules):

- **Per instrument, out of sample:** mean Sharpe 0.44 against 0.55 for buy & hold. **No
  edge** on risk-adjusted return.
- **Drawdown:** **about half of buy & hold's** in every period, and lower on 14 of 15
  instruments in the holdout.
- **As a portfolio:** it beats plain buy & hold on Sharpe but not the vol-targeted
  control.
- **Against the paper's baselines:** SMA, MACD and ZMR are beaten on most instruments out
  of sample.
- **FX:** close to zero throughout.

**What was not measured:** the LLM mode. None of the paper's LLM results (cumulative return
23–27%, Sharpe 5.6–8.2) are claimed.

**Questions.**
- Design the experiment that would show whether Claude adds value over the rule-based firm.
  What is the control, how many runs per date, which periods, and which metric?
- The paper's headline window was one quarter of a strong rally. What does section 16 say
  about the evidence one quarter can provide?
