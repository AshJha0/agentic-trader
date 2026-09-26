# Learn agentic-trader

This guide works through the ideas behind the project in order. For each concept it gives the
idea, where the repository implements it, the real numbers it produces, and questions to test
your understanding. Recipes are in [COOKBOOK.md](COOKBOOK.md); component detail is in
[docs/architecture/overview.md](docs/architecture/overview.md); the measured results are in
[docs/evaluation/evaluation.md](docs/evaluation/evaluation.md).

**Part I — the trading desk**

1. [Why a desk of specialist agents?](#1-why-a-desk-of-specialist-agents)
2. [Structured communication](#2-structured-communication)
3. [The analyst team](#3-the-analyst-team)
4. [Debate as a decision mechanism](#4-debate-as-a-decision-mechanism)
5. [From view to trade: strategic weight and tilt](#5-from-view-to-trade-strategic-weight-and-tilt)
6. [Risk: volatility targeting, VaR, and who has the last word](#6-risk-volatility-targeting-var-and-who-has-the-last-word)
7. [Where the LLM sits, and where it does not](#7-where-the-llm-sits-and-where-it-does-not)
8. [Equity vs FX](#8-equity-vs-fx)

**Part II — the agentic layer**

9. [Tools as the only way to reach data](#9-tools-as-the-only-way-to-reach-data)
10. [Evidence before interpretation](#10-evidence-before-interpretation)
11. [Policy: who may do what, explained by rule](#11-policy-who-may-do-what-explained-by-rule)
12. [Plans, and why a plan must be validated](#12-plans-and-why-a-plan-must-be-validated)
13. [The harness: a state machine owns the loop](#13-the-harness-a-state-machine-owns-the-loop)
14. [The critic can only lower confidence](#14-the-critic-can-only-lower-confidence)
15. [Audited reports](#15-audited-reports)
16. [Retrieval over the desk's own rules](#16-retrieval-over-the-desks-own-rules)
17. [MCP, the API and observability](#17-mcp-the-api-and-observability)

**Part III — trading it for real**

18. [Backtesting without fooling yourself](#18-backtesting-without-fooling-yourself)
19. [Stops, gaps and the no-trade band](#19-stops-gaps-and-the-no-trade-band)
20. [Alpha research](#20-alpha-research)
21. [Execution: from a weight to fills](#21-execution-from-a-weight-to-fills)
22. [Portfolio construction](#22-portfolio-construction)
23. [Memory, edge cases and refusing to guess](#23-memory-edge-cases-and-refusing-to-guess)

**Part IV — knowing whether it works**

24. [Designing an honest evaluation](#24-designing-an-honest-evaluation)
25. [Is a Sharpe ratio real? Selection and deflation](#25-is-a-sharpe-ratio-real-selection-and-deflation)
26. [Reading the results honestly](#26-reading-the-results-honestly)

**Part V — v0.5: a wider test, real execution costs, and running it**

27. [A holdout is spent the moment you look at it](#27-a-holdout-is-spent-the-moment-you-look-at-it)
28. [Execution costs belong in the backtest, not in a footnote](#28-execution-costs-belong-in-the-backtest-not-in-a-footnote)
29. [Cross-sectional alphas: rank the room, not the stock](#29-cross-sectional-alphas-rank-the-room-not-the-stock)
30. [Operating the desk: budgets in dollars, records that survive, keys that are real](#30-operating-the-desk-budgets-in-dollars-records-that-survive-keys-that-are-real)

---

# Part I — the trading desk

## 1. Why a desk of specialist agents?

**Idea.** Real trading desks split work between specialists: analysts, researchers, traders,
risk managers and a portfolio manager. Each role has a narrow job and a different incentive.
Organising LLM agents the same way gives narrow prompts, explicit hand-offs, and a decision
that can be explained role by role rather than one opaque "should I buy?".

**In the repo.** `TradingGraph` in `graph.py` runs the desk as stages: `prepare`,
`run_analyst` (4 by default, 5 with the alpha analyst), `run_debate` (bull, bear,
facilitator), `run_trader`, `run_risk` (three analysts and the portfolio manager) and
`record`. `propagate()` runs them in order; the agentic harness (Part II) runs the same
stages under a plan.

**Numbers.** One decision takes about 8 ms offline through `propagate()` and about 31 ms
through the harness with its tools, critic and audit. With Claude enabled it makes 14 LLM
calls at default settings, or 13 when one analyst has no data.

**Questions.**
- What does a fixed stage order give up compared with letting a model choose the next agent?
  What does it gain?
- Which role would you remove first if LLM calls were expensive, and why?

## 2. Structured communication

**Idea.** If agents pass free text along a chain, details degrade at every hop. Agents
therefore write concise typed documents into a shared state, and dialogue is used only where
argument is the point: the debates.

**In the repo.** `state.py` defines `AnalystReport`, `DebateOutcome`, `TradeProposal`,
`RiskView` and `FinalDecision`. Every document carries `evidence_ids`, filled in by the
harness, and an analyst report keeps `rule_signal` when a model reply replaced it, so the
critic can measure the divergence. Downstream agents read `state.reports_digest()`, not
transcripts. `to_markdown()` turns the whole state into an audit trail.

**Questions.**
- Why must each report carry a *confidence* as well as a *signal*?
- What would you lose if the trader read the raw debate transcript instead of the verdict?

## 3. The analyst team

**Idea.** Each analyst turns one kind of raw data into a signal in [-1, 1] and a confidence
in [0, 1], or abstains when it has no data.

**In the repo** (`agents/analysts.py`):

| Analyst | Inputs (tools) | Rule-based view |
|---|---|---|
| Technical | SMA 20/50/200, MACD, RSI, Bollinger %B, KDJ, ATR, vol-adjusted momentum | Trend + MACD + momentum ± overbought/oversold |
| Fundamentals (equity) | P/E vs sector, growth, margin, D/E, FCF yield, EPS surprise, insiders | Value tilt + tanh-scaled quality and growth |
| Macro (FX) | Point-in-time policy-rate and inflation differentials, distance from the 200-day average | Carry − PPP drag − mean reversion |
| News | Headlines in the last 7 days | Lexicon tone with negation and a 2-day half-life |
| Sentiment | Social posts, RSI extremes, volume spikes | Crowd tone + contrarian flag at extremes |
| Alpha (optional) | The alpha library's latest values and their measured IC | IC-weighted composite |

An abstaining analyst makes no LLM call: an empty input invites the model to invent a view.

**Numbers.** On the 2016–2021 design period, adding the alpha analyst changed mean Sharpe from
0.65 to 0.60 and median from 0.55 to 0.60. That is noise across 15 instruments, so it is off
by default (section 24).

**Questions.**
- Why use `tanh` to squash terms instead of clipping them?
- The alpha analyst reuses signals the technical analyst also sees. What does that do to the
  consensus, and how would you detect it?

## 4. Debate as a decision mechanism

**Idea.** Forcing a bull and a bear to argue brings out evidence that one balanced analysis
smooths over. A facilitator decides who made the better case and records it as data.

**In the repo.** `researchers.py`: the bull and bear speak for `max_debate_rounds` (default
2). The facilitator computes the confidence- and role-weighted consensus
`Σ wᵢ·confᵢ·signalᵢ / Σ wᵢ·confᵢ`, declares `bull` or `bear` when |score| > 0.10, and sets
conviction = |score| · (0.5 + mean confidence). With an LLM it returns a JSON verdict instead.

**Questions.**
- In offline mode the verdict is a weighted average, so the debate text does not change the
  number. What would have to be true for the LLM debate to add value over that average?
- How would you detect a facilitator that always sides with the last speaker?

## 5. From view to trade: strategic weight and tilt

**Idea.** A view is not a trade. The trader must choose a size, a stop, a target and a
horizon, and must decide what to hold with *no* view. A real mandate has a benchmark: an
equity fund without a strong opinion holds the index; active management is a tilt around it.

**In the repo** (`agents/trader.py`): weight = `neutral + 2·score` when |score| exceeds the
threshold, else `neutral`, clipped to [-1, 1]. `risk.neutral_weight` is 1.0 for equities and
0.0 for FX. Stops sit 2 ATR against the position and targets 3 ATR in favour; model-supplied
levels on the wrong side are replaced (`sane_levels`). Retrieved policy passages
(section 16) are shown to the trader when the harness ran `knowledge.search`.

**Numbers.** Raising the equity neutral weight from 0 to 0.25, 0.5 and 1.0 moved equity median
Sharpe on the design period from 0.68 to 0.79, 0.87 and 1.06. It was the only change that
clearly helped, and it helps by collecting the premium, not by forecasting.

**Questions.**
- With a 2-ATR stop and a 3-ATR target, what hit rate breaks even before costs?
- Why did the strategic weight raise returns far more than Sharpe out of sample?

## 6. Risk: volatility targeting, VaR, and who has the last word

**Idea.** The same signal should mean a smaller position in a more volatile asset. Tail risk
needs a hard ceiling. One party must be able to say no, and its limits must be code.

**In the repo** (`agents/risk.py`): the neutral analyst volatility-targets at 15%; the
aggressive one takes max(1.25·|w|, vol-target); the conservative one halves the smaller and
caps it by VaR. The portfolio manager blends 25/50/25 (or takes the model's weight), then
applies the firm limits in order (shorting policy, max position 1.0, 1-day VaR95 ≤ 2%,
minimum trade 0.05) and the no-trade band. Every adjustment is logged.

**Numbers.** In the sample AAPL decision the trader proposed +1.00; the views were +1.00,
+0.46 and +0.23; the PM decided +0.54.

**Questions.**
- Historical VaR from 250 days: what does it miss that CVaR catches?
- Why must the limits run *after* the LLM rather than be stated in its prompt?

## 7. Where the LLM sits, and where it does not

**Idea.** LLMs weigh heterogeneous evidence and explain decisions well. They are unreliable
calculators, and a trading system must survive the model being wrong, down, expensive or
manipulated.

**In the repo.** Every agent runs tools, then rules, then optionally the model
(`agents/base.py`). Missing keys, non-JSON output, API errors and refusals fall back to the
rules; values are clipped and coerced. Third-party text reaches the model only inside
`<untrusted_data>` blocks that cannot be closed from inside. `max_llm_calls` wraps the model
in a thread-safe budget. `llm_anonymize` hides the ticker, the calendar and the price level so
a model cannot recall what happened in a backtest window. Usage is tracked per model with
list-price cost.

**Try it.** Cookbook recipes 17, 18, 36 and 40.

**Questions.**
- Why is "fall back to rules" safer than "retry until valid JSON"?
- Anonymisation removes names, dates and price levels. Name two things it cannot remove.

## 8. Equity vs FX

**Idea.** The desk structure carries over between asset classes, but the finance does not.

| | Equity | FX |
|---|---|---|
| Value analyst | Company fundamentals | Rates carry, inflation (PPP), long-run valuation from FRED |
| Alpha library | 8 signals | The same plus carry |
| News orientation | The stock is the subject | Scored from the **base** currency's view |
| Strategic weight | 1.0 | 0.0 |
| Shorting | Off by default | On |
| Execution default | VWAP over 78 five-minute slices; POV above 10% of ADV | TWAP over 288 slices; spread in pips |
| Financing | Borrow fee on shorts | Carry accrued per bar from point-in-time rates |
| Periods per year | 252 | 260 |

**Questions.**
- Why does a long USD/JPY position *earn* carry when US rates exceed Japanese rates?
- Why is TWAP the FX default when VWAP is the equity default?

# Part II — the agentic layer

## 9. Tools as the only way to reach data

**Idea.** If an agent can call any Python function, nothing can be governed. If every
capability is a catalogued tool with a schema and annotations, then one definition serves
the in-process executor, the planner's catalogue, an MCP server, and the policy engine.

**In the repo** (`agentic/tools.py`, `agentic/servers.py`). `ToolRegistry.register` derives a
JSON schema from the Python signature (type hints, defaults, docstring). `DeskTools` holds 15
tools on 5 servers: `market_data` (history, news, social, fundamentals, macro), `quant`
(technical, risk, alpha, baselines), `knowledge` (search, list_documents), `portfolio`
(position, construct), `execution` (plan, submit_order). Each carries `ToolAnnotations`:
read-only, risk level, required capabilities, evidence type. `RecordingProvider` makes the
desk's analysts reach data through these tools without changing the analysts.

**Numbers.** 16 tools, 5 servers, schemas with `additionalProperties: false`; arguments are
coerced (dates, integers, bounds) and unknown arguments are refused.

**Questions.**
- Why derive schemas from signatures instead of writing them by hand?
- `submit_order` writes a ticket and never talks to a broker. Why is it in the catalogue at all?

## 10. Evidence before interpretation

**Idea.** An audit trail that is assembled after the fact can be edited. If every tool call
produces a record with a digest *before* any agent interprets the result, then a finding
can cite it, a validator can check it, and a tampered payload is detectable.

**In the repo** (`agentic/domain.py`, `agentic/evidence.py`). `Evidence` holds the type
(DATA, CALCULATION, DOCUMENT, MODEL_OUTPUT, DECISION, APPROVAL), source, arguments,
correlation id and the SHA-256 of the canonical JSON payload. `EvidenceStore.resolve(id)` is
true only when the id exists and the stored payload still hashes to its digest. The harness
records DATA evidence for every provider call, CALCULATION evidence for each analyst's facts
and the risk facts, DECISION evidence for every document, and APPROVAL evidence for approvals.
Findings cite evidence ids; `validate_evidence` drops any finding whose ids do not resolve.

**Numbers.** One task produces 21 evidence records and 7 findings; a mutated payload fails
`resolve` (tested).

**Questions.**
- Why hash the canonical JSON rather than the Python object's `repr`?
- A failed tool call is recorded as evidence too. What can a report say with it that it
  could not say without it?

## 11. Policy: who may do what, explained by rule

**Idea.** "The agent should not do X" must be a rule that runs, not a sentence in a prompt.
The decision must say which rule fired, so a denial can be explained and a grant can be audited.

**In the repo** (`agentic/policy.py`). Five roles map to capabilities. `PolicyEngine`
evaluates ordered rules and the first that decides wins: deny list → required capabilities →
read-only (a state-changing tool needs `propose_trades` and approval) → argument guards
(symbol universe and validity, no future dates, finite weights within the cap, bounded
lookback) → risk level (HIGH always needs approval) → allow. A rule set without a terminal
rule fails closed. Approval gateways: `auto` (development), `queued` (a person decides; the
API exposes the queue), `deny`. The approval key is the tool and its arguments within the
task, so a request re-submitted after approval is recognised.

**Numbers.** 6 rules; a viewer's task fails at plan validation before any tool runs.

**Questions.**
- Why does the read-only rule return DENY for an analyst but REQUIRE_APPROVAL for a trader?
- What is the risk of keying approvals on the correlation id instead of the arguments?

## 12. Plans, and why a plan must be validated

**Idea.** Letting a model plan is useful; trusting the plan is not. A plan is restricted to
the catalogue and the desk's stages, and everything a plan cannot be allowed to do is fixed
before it runs.

**In the repo** (`agentic/planner.py`). `canonical_plan` is the default: knowledge search,
alpha snapshot, analysts, debate, trader, risk, then critic, validation, finalisation.
`propose_plan` asks the model for JSON restricted to the catalogue. `validate_plan` drops
unknown tools, stages and step types, drops unknown arguments, pins `symbol` and `as_of` to
the task, refuses state-changing tools in plans, removes duplicate stages, inserts missing
stages in order, caps the length and appends the governance steps. Unusable model output falls
back to the canonical plan with a note. The harness then pre-checks every tool step against
policy so an impossible plan fails before execution.

**Numbers.** In the adversarial test a plan with an order, another symbol, a future date, a
shell command and a skipped governance step becomes a valid canonical-shaped plan with notes.

**Questions.**
- Why pin the symbol rather than deny a plan that names another symbol?
- The validator refuses state-changing tools in plans even for a trader. Why not let policy
  handle it at run time?

## 13. The harness: a state machine owns the loop

**Idea.** Agents propose; the harness disposes. An explicit state machine with a transition
table means a bug cannot jump to COMPLETED, an approval pause is a state rather than a flag,
and cancellation is checked at defined points.

**In the repo** (`agentic/harness.py`). `AgentHarness.run(task)` moves through CREATED →
PLANNING → VALIDATING_PLAN → EXECUTING (⇄ AWAITING_APPROVAL) → CRITIQUING →
VALIDATING_EVIDENCE → FINALISING → COMPLETED, with FAILED and CANCELLED reachable from any
non-terminal state; `TRANSITIONS` refuses anything else. Consecutive tool steps run in a
thread pool; agent stages run through `TradingGraph` with the recording provider; each stage
attributes the evidence added during it to the document it produced. A REQUIRE_APPROVAL
outcome with no answer pauses the run at that step; `decide_approval` resumes it from the
same step. Every run has its own tracer.

**Numbers.** 12 steps, 18 spans, about 31 ms per task offline; four tasks run concurrently
from threads in the tests.

**Questions.**
- Why is AWAITING_APPROVAL a state rather than a blocking call?
- The harness appends governance steps to any plan. What could go wrong if the planner were
  allowed to place them?

## 14. The critic can only lower confidence

**Idea.** A reviewer that can raise confidence is another source of overconfidence. The
critic's deterministic checks run first; a model critique may add concerns and a multiplier,
and the multiplier is clipped to at most 1.

**In the repo** (`agentic/critic.py`). Checks: every cited evidence id resolves (error);
a model-sourced analyst signal within 0.6 of its rule-based signal on the same facts; no strong
bull/bear contradiction without a balanced verdict; firm limits (size, shorting, VaR); stops
and targets on the correct side (error); the trader's tilt agrees with the verdict and the PM
did not flip direction without an adjustment; single-evidence findings capped at 0.6. The
decision's confidence is scaled by the multiplier at finalisation.

**Numbers.** 6 checks per task; in the injected-headline test the divergence check fails and the
multiplier drops to 0.7.

**Questions.**
- Sizing below the strategic weight by the risk team is not a directional flip. How did the
  first version of the direction check get this wrong, and what fixed it?
- Which of the seven checks would you make an error rather than a warning, and why?

## 15. Audited reports

**Idea.** A narrative written by a model can contain a number the facts do not support or an
evidence id that does not exist. Audit it after it is written and attach what fails.

**In the repo** (`agentic/reporter.py`). `collect_facts` gathers every figure the narrative
may use (prices, signals, weights, counts of analysts and turns). The narrative is a template,
or a model given only those facts. `number_audit` extracts every number and accepts it only if
some fact, rounded to the token's displayed precision (or its percentage form), equals it.
`evidence_audit` checks every id against the store. Warnings are listed in the markdown.

**Numbers.** In the fabricated-narrative test, "350 bps", "88%" and "CALC-badbadba" are flagged
while "+0.54" and "0.51" pass.

**Questions.**
- The audit's tolerance is half a unit of the *displayed* precision, scaled for percentages.
  What went wrong when it was half a unit of the raw token?
- Counts ("3 analysts") were once exempt from the audit. Why is putting counts into the facts
  better than exempting small integers?

## 16. Retrieval over the desk's own rules

**Idea.** The desk's policies (limits, sizing, stops, carry, execution, evaluation) should be
readable by the agents at decision time, and a passage that shaped a decision should be
evidence.

**In the repo** (`agentic/rag.py`, `agentic/knowledge/docs`). Eleven Markdown documents are
split by heading into 59 chunks and embedded with a hashed TF-IDF (unigrams and bigrams into
4,096 buckets, log-tf × idf, L2-normalised), so retrieval is a cosine with no model download.
`knowledge.search` returns passages as DOCUMENT evidence; the harness puts them in
`state.knowledge`, and the trader's and PM's prompts include them.

**Numbers.** "What is the value at risk cap" retrieves the risk-limits policy first; "carry
publication lag FRED" retrieves the FX carry methodology.

**Questions.**
- Hashed TF-IDF has collisions. Why is that acceptable here, and when would it not be?
- A policy passage says "the VaR cap is 2%". The model reads it and the code enforces it.
  Which one matters, and why show the passage at all?

## 17. MCP, the API and observability

**Idea.** A capability layer earns its keep when other systems can use it. The Model Context
Protocol lets any client discover and call the tools; an HTTP gateway lets an operator run
tasks, read audited reports and approve orders; traces and metrics make it operable.

**In the repo.** `agentic/mcp_server.py` exposes the registry as an MCP stdio server with
read-only and risk annotations, and `registry_from_stdio` turns a remote server's tools into a
local registry so policy and evidence apply to remote tools unchanged (tested with a real
subprocess round trip). `agentic/api.py` is a FastAPI gateway with API-key roles: tasks are
202-accepted and run in a background thread; reports, traces, evidence, cancel, approvals,
tools, health and Prometheus text metrics. `agentic/tracing.py` records spans with parent ids,
JSON-lines logs and labelled counters and histograms.

**Questions.**
- Why must a remote tool's read-only annotation be trusted less than a local one, and what
  does the executor do about it?
- Which endpoint should a trader be refused, and which rule refuses it?

# Part III — trading it for real

## 18. Backtesting without fooling yourself

**Idea.** Most impressive backtests are look-ahead bugs. Information must be used only after
it existed, and a signal must not earn the return of the bar that produced it.

**In the repo.** Providers return data only up to `as_of` and the graph clips again;
synthetic fundamentals publish 30 days after quarter end; Yahoo's current fundamentals are
refused for past dates; FRED values are publication-lagged and staleness-checked; news is
filtered twice; memory resolves only after its horizon; a weight decided at close *t* earns
*t → t+1*; the FX spread is converted at the window's first price. Alphas are computed bar by
bar from past data, and a test truncates the history to show earlier values do not change.

**Questions.**
- Can news published after the close on day *t* leak into day *t*'s decision? (Yes; threat T3.)
- FRED serves the latest vintage. When does that matter?

## 19. Stops, gaps and the no-trade band

**Idea.** A stop is only as good as its fill; markets gap. And every rebalance costs spread,
so a target that moved from 0.54 to 0.50 is not worth trading.

**In the repo.** The C++ backtester fills a stop or target at the level, or at the open when
the market gaps through it, assumes the stop first when both trade in a bar, and re-arms at
the next rebalance. The no-trade band keeps a position within 0.10 of the target, only if that
position still passes every limit today.

**Numbers.** On 2016–2021 real data the band gave the same Sharpe with 44% fewer trades; stops
lowered mean return by about 30% at similar Sharpe, so they are off by default.

**Questions.**
- Why is "stop first when both trade" the right default with daily bars?
- The band makes the result path-dependent. Why is that realistic rather than a flaw?

## 20. Alpha research

**Idea.** A signal is only worth trading if it predicts, if the prediction lasts long enough to
trade, and if it is not just another copy of a signal you already have.

**In the repo** (`alpha.py`). Nine signals in [-1, 1]: 12-1 month momentum, vol-adjusted
20-day momentum, 5-day reversal, 52-week-high proximity, Donchian channel position, MACD in ATR
units, contrarian RSI, low-vol, and FX carry. `alpha_report` computes, for a horizon, the
Spearman IC and its t-statistic, IC decay across horizons, hit rate, tercile spread, signal
autocorrelation (turnover) and coverage, plus the correlation matrix of signals and a combined
alpha. The C++ core supplies rolling extremes and Spearman correlation.

**Numbers.** On synthetic USD/JPY over 2021–2024, `mom_20_vol` has IC 0.146 (t 4.2) and
`rsi_contrarian` −0.157 (t −4.5); the synthetic market is regime-switching, so momentum and
contrarian signals pull opposite ways. Real-data ICs are in the cookbook recipe.

**Questions.**
- An IC of 0.3 on daily data appears in your report. What is the first thing to check?
- Why is signal autocorrelation a cost measure?

## 21. Execution: from a weight to fills

**Idea.** A decision is a target weight; the market only knows orders. Splitting a parent order
over the session trades market impact against timing risk, and the cost must be measured.

**In the repo** (`algo.py`). `plan_execution` turns a weight change into a parent order:
shares or base-currency units, side, and an algorithm (VWAP for equities, POV above 10% of
ADV, TWAP for FX; Almgren-Chriss on request, with `kappa = sqrt(λσ²/η)` from the C++ core).
`synthetic_intraday_bars` builds a session from the daily bar as a Brownian bridge kept inside
the high and low, with a U-shaped equity volume profile. `simulate_execution` fills each slice
at the bar's VWAP plus half the spread and square-root impact, caps a slice at the bar's
volume, and reports implementation shortfall against arrival and slippage against VWAP in
basis points.

**Numbers.** A 2.5 million-dollar AAPL buy (0.06% of ADV) via VWAP in 78 slices: 100% filled,
spread 1.0 bps, impact 0.4 bps, −5.4 bps shortfall against arrival on that day's path.

**Questions.**
- Why does a VWAP-shaped schedule show exactly the half-spread against session VWAP while a
  TWAP schedule does not?
- When would you choose Almgren-Chriss over VWAP, and which parameter decides?

## 22. Portfolio construction

**Idea.** Diversification is the one free lunch, but only with a usable covariance and a
weighting scheme that matches the mandate.

**In the repo** (`portfolio.py`). Covariance: EWMA (60-day half-life) shrunk toward the
constant-correlation target with the Ledoit-Wolf intensity. Schemes: equal, inverse-vol, risk
parity (equal risk contributions via cyclical coordinate descent), long-only minimum variance
and mean-variance with a per-sleeve cap (projected gradient on the capped simplex). `construct`
applies a scheme to the desk's signed targets, scales to a 15% volatility target without
levering above the gross cap, and reports marginal and component risk, percentage
contributions, the diversification ratio and the correlation matrix.
`run_portfolio_backtest(weighting=...)` re-estimates allocations from trailing returns only.

**Numbers.** Risk parity on a 4-asset test covariance gives exactly 25% risk contribution
each; for independent synthetic instruments it coincides with inverse-vol, as it should.

**Questions.**
- Why is the scheme applied to capital shares and then multiplied by the signed targets,
  rather than solved on the signed weights directly?
- Equal capital across a 15%-vol stock and an 8%-vol currency gives very unequal risk. Which
  scheme fixes that, and what does it cost?

## 23. Memory, edge cases and refusing to guess

**Idea.** The happy path is the easy 10%. A system meets holidays, bad ticks, typos, dead
feeds and broken files every week, and must either handle each or refuse loudly.

**In the repo.** Memory writes atomically and skips corrupt lines; weekends use the last
close; feeds older than 7 days are refused; mistyped pairs and invalid tickers are refused;
CSVs are cleaned; flat prices, NaN weights and non-finite positions are handled; model output
that is `inf`, `nan`, a string or a wrong-side stop is coerced or replaced; a bad symbol in a
watchlist becomes an error row; a task that fails ends in FAILED with the reason. Each has a
test.

**Questions.**
- Why refuse stale data rather than warn and continue?
- Which failures would you page on in production, and which only log?

# Part IV — knowing whether it works

## 24. Designing an honest evaluation

**Idea.** If you try enough variants on the data you report, one will look good by chance.
Choose everything on a design period, freeze, run the holdout once, and report it whatever it
shows.

**In the repo** (`evaluation.py`). Periods: design 2016–2021, holdout 2022 to mid-2026, and a
Q1 2024 reference window. Universe: 10 equities and 5 FX pairs. `RULES_V02` reproduces the old
rules so every change has a before and after. The v0.3 search tried 16 variants on the design
period; two were adopted. In v0.4 the alpha analyst was measured the same way and not adopted.

**Questions.**
- The design-period Sharpe gain mostly vanished out of sample while the return gain survived.
  Explain why, using section 5.
- Having seen the holdout, may you tune against it? What would you need instead?

## 25. Is a Sharpe ratio real? Selection and deflation

**Idea.** A Sharpe ratio is an estimate with an error bar, and the best of N tries is biased
upward. Three tools: the t-statistic and a bootstrap interval for the error bar; the
probabilistic Sharpe ratio for the chance the true Sharpe exceeds a benchmark given skew and
kurtosis; the deflated Sharpe ratio, which raises the benchmark to the expected maximum of N
null trials.

**In the repo** (`stats.py`, `agentic-trader stats`). `sharpe_ci_bootstrap` (circular block
bootstrap), `probabilistic_sharpe`, `expected_max_sharpe`, `deflated_sharpe`,
`min_track_record` and `selection_report`. The evaluation applies them to the desk's own
16-variant search.

**Numbers.** See the evaluation's "selection" section for the chosen variant's bootstrap
interval, PSR and DSR.

**Questions.**
- Why does negative skew lower the probabilistic Sharpe for the same Sharpe ratio?
- Sixteen variants were tried. If their Sharpe ratios were all identical, what would the
  deflation be, and why?

## 26. Reading the results honestly

**What was measured** (rule-based desk, real prices, frozen rules):

- **Per instrument, out of sample:** mean Sharpe 0.44 against 0.55 for buy & hold. No edge on
  risk-adjusted return.
- **Drawdown:** about half of buy & hold's, and lower on 14 of 15 instruments.
- **As a portfolio:** 1.14 against 1.06 for plain buy & hold, but below the vol-targeted control
  at 1.24.
- **Alpha analyst:** noise on the design period; not adopted.
- **FX:** close to zero throughout.

**What was not measured:** the LLM mode, and therefore whether the agentic layer's planner,
critic and reporter change decisions for the better. The layer's value is demonstrated as
*governance* (what it prevents and what it makes auditable), not as *alpha*.

**Questions.**
- Design the experiment that would show whether Claude adds value over the rule-based desk:
  control, runs per date, periods, metric, and how you would keep the model from recalling
  the period.
- The evaluation reports what the desk cannot do. What would you want to see before trusting
  a report that only listed what it can?

## 27. A holdout is spent the moment you look at it

**The idea.** A holdout period proves something only while nobody has used it for a choice.
v0.3 chose its rules on 2016–2021 and judged them once on 2022–2026; v0.4 then *reported*
the holdout, compared variants against it and wrote it on the landing page. From that moment
any new rule that "improves the holdout" is being fitted to it. The honest response is to
declare what "unseen" means from now on, before there is a new rule to test.

**In the repo.** v0.5 widens the universe from 15 to 60 instruments and partitions it:
`UNIVERSES["core"]` (the 15 every choice was made on) and `UNIVERSES["extended"]` (26
sector equities, 9 rates / credit / commodity ETFs, 10 FX crosses) that no choice ever
consulted, so the extended names are out of sample on *every* period, including the design
period. `PERIODS["reserve"]` (2026-07-01 → 2026-09-25) is untouched by every published
number and grows with time. Every result row carries a `universe` tag; `summary(universe=)`
and `evaluate --universe core|extended|all` keep the two apart. The protocol for the next
rule change is written in the evaluation: choose on the core design period, then judge on
the extended universe and the reserve period, and report all three.

**Numbers.** The extended universe is a harder test: on its holdout the desk's mean Sharpe
is 0.37 against 0.50 for buy & hold (core: 0.44 vs 0.55), it beats buy & hold on 14 of 45
names, and its drawdown is 17.7% against 27.2%. The story from the core universe (no
Sharpe edge per instrument, about half the drawdown) survives; it does not get better.

**Questions.**
- The reserve period is three months. What is it good for now, and what would it take
  for it to become the primary holdout?
- Why is a universe partition a stronger out-of-sample test than a time partition for a
  rule that was tuned on one set of names?

## 28. Execution costs belong in the backtest, not in a footnote

**The idea.** Close-to-close fills with a fixed bps cost are fine for a $100k account trading
large caps and wrong for a $1B one: market impact grows with the square root of the trade's
share of daily volume, so the same strategy has a different Sharpe at a different size. If
the execution model lives only in a separate simulator, the backtest is quietly assuming the
account is small.

**In the repo.** `costs.impact_coeff` turns the execution simulator's square-root model into
a per-bar coefficient for the backtester: a trade of `|dw|` costs `|dw|^1.5 · K_t` of equity
with `K_t = coeff · daily_vol_t · sqrt(capital / (price_t · ADV_t))`, everything known at the
close of bar `t` (trailing 20-day volatility and volume). The engine (C++ and the numpy twin)
charges it on entries, exits and stop fills, reports `impact_paid`, and the same series is
applied to every baseline so the comparison stays fair. FX has no exchange volume and gets
no impact unless `costs.fx_adv_notional` is set. `--impact 1.0 --capital 1e9` on the
backtest, portfolio and evaluation commands.

**Numbers.** On the core universe with the textbook coefficient, impact over the six-year
design period is 0.08% of equity at $100k, 0.8% at $10M and 7.7% at $1B for the desk (mean
Sharpe 0.65 → 0.64 → 0.56). The surprise is the direction of the ranking: the daily
volatility-target baseline, with ~1,100 trades, pays *less* (5.7% at $1B) than the desk with
~106, because a square-root law makes many tiny adjustments cheap and a few large jumps
dear; MACD, which flips whole positions, loses 75% to impact at $1B and its Sharpe goes
negative. The evaluation has the full sweep.

**Questions.**
- Why does impact per trade scale with `|dw|^1.5`, and what does that imply for a strategy
  that rebalances rarely but in big steps?
- At which account size does the desk's ranking against the vol-target control change,
  and what does that say about quoting a Sharpe ratio without a capital figure?

## 29. Cross-sectional alphas: rank the room, not the stock

**The idea.** A time-series alpha asks whether one instrument will go up. A cross-sectional
alpha asks which instruments will do better than the others today, which removes the
market's common move and is how most equity quant desks actually use momentum, reversal
and quality signals. The same raw signal can be near-useless as a timing tool and useful as a
ranking tool.

**In the repo.** `xalpha.py` computes the library's signals per instrument, then standardises
them across the names of a group every day (z-score or rank; equities and FX separately, so
an FX cross never ranks against a stock). Evaluation is per date: Spearman IC across names,
summarised as the mean IC, an information ratio, a t-statistic that only counts one
independent observation per horizon (daily ICs of a 10-day return overlap), the share of
positive days, top-minus-bottom quantile spreads rebalanced every horizon and breadth.
`xalpha_report`, `xalpha_snapshot`, the `quant.xalpha` tool and `agentic-trader xalpha`.
It is a research layer: no analyst consumes it yet, deliberately (see 27 for the bar a new
input has to clear).

**Questions.**
- Why must a cross-sectional score be computed within an asset class?
- The t-statistic divides the day count by the horizon. What happens to it if you forget?

## 30. Operating the desk: budgets in dollars, records that survive, keys that are real

**The idea.** Three things separate a research tool from something you can leave running:
a spend cap in the unit the invoice uses, records that outlive the process, and a service
that refuses to be deployed insecurely by default.

**In the repo.** `max_llm_cost_usd` caps estimated spend (list prices, cache-aware) next to
`max_llm_calls`; an Opus call is roughly fifteen Haiku calls, so a call count alone does not
bound a bill. `agentic.task_db` (or `serve --task-db`) writes every run to SQLite at each
state transition; a new process serves old records through the same routes, and anything
left mid-flight by a crash is marked FAILED "process restarted", never silently resumed.
`serve` refuses a non-loopback bind with the shipped development keys, warns about plain
HTTP off loopback, takes `--ssl-cert/--ssl-key`, and `make_config` now *replaces*
`agentic.api_keys` instead of merging into the dev keys. Underneath, `tests/test_fuzz.py`
fuzzes the Python ↔ C++ boundary with hypothesis: every quant function on NaN, ±inf, empty
and huge inputs must either answer or raise `ValueError`, and both backends must agree on
sane inputs. It found five real divergences on its first run (see the changelog), which is
the point.

**Questions.**
- Why is an in-flight task failed on restart instead of resumed?
- The fuzzer's "backends agree" property is only asserted for |x| ≤ 1e6. What breaks above
  ~2^53, and is that a bug?
