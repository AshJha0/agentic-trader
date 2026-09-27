# Learn agentic-trader

This guide works through the 35 ideas behind the project in order. For each concept it gives
the idea, where the repository implements it, the real numbers it produces, and questions to
test your understanding. Recipes are in [COOKBOOK.md](COOKBOOK.md); component detail is in
[docs/architecture/overview.md](docs/architecture/overview.md); the measured results are in
[docs/evaluation/evaluation.md](docs/evaluation/evaluation.md). Numbers from the synthetic
provider or a local command were regenerated for v0.8; a real-data figure carries the release
that measured it, and v0.8 re-measured every one of them under a corrected engine (concept 35).

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

**Part VI — v0.6: real filings, statistical power, and the variance of a judgement**

31. [Point in time is a property of the source](#31-point-in-time-is-a-property-of-the-source)
32. [Rank the room and put it through the protocol](#32-rank-the-room-and-put-it-through-the-protocol)
33. [Power across instruments, and the variance of a judgement](#33-power-across-instruments-and-the-variance-of-a-judgement)

**Part VII — v0.7 and v0.8: testing the risk model, and re-measuring everything**

34. [Is the risk model telling the truth? VaR coverage backtesting](#34-is-the-risk-model-telling-the-truth-var-coverage-backtesting)
35. [Constant units, idle cash and the fair comparison](#35-constant-units-idle-cash-and-the-fair-comparison)

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
| Fundamentals (equity) | P/E vs a sector P/E when one is supplied (synthetic data only; none on real data), growth, margin, D/E, FCF yield, EPS surprise, insiders | Value tilt (only with a sector benchmark) + tanh-scaled quality and growth |
| Macro (FX) | Point-in-time policy-rate and inflation differentials, distance from the 200-day average | Carry − PPP drag − mean reversion |
| News | Headlines in the last 7 days | Lexicon tone with negation and a 2-day half-life |
| Sentiment | Social posts, RSI extremes, volume spikes | Crowd tone + contrarian flag at extremes |
| Alpha (optional) | The alpha library's latest values and their measured IC | IC-weighted composite |

An abstaining analyst makes no LLM call: an empty input invites the model to invent a view.

**Numbers.** On the 2016–2021 design period, adding the alpha analyst changed mean Sharpe from
0.65 to 0.60 and median from 0.55 to 0.60. That is noise across 15 instruments, so it is off
by default (section 24). Those figures were measured with a significance gate that passed
noise (section 20); v0.8 corrected the gate and re-measured the analyst, so read the
evaluation's v0.8 section for the current number.

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
threshold, else `neutral`, clipped to [-1, 1]. `risk.neutral_weight` is 1.0 for equities.
For FX (v0.5.1, `rules.fx_carry_neutral`) the neutral weight is the *carry premium*:
`clip(rate_diff% / 2, ±0.5)` from the macro analyst's point-in-time policy-rate
differential, so the desk holds the higher-yielding currency unless convinced otherwise —
the same logic as the equity benchmark, with the same "hold the premium" prior. Stops sit
2 ATR against the position and targets 3 ATR in favour; model-supplied levels on the wrong
side are replaced (`sane_levels`). Retrieved policy passages (section 16) are shown to the
trader when the harness ran `knowledge.search`.

**Numbers.** Raising the equity neutral weight from 0 to 0.25, 0.5 and 1.0 moved equity median
Sharpe on the design period from 0.68 to 0.79, 0.87 and 1.06. It was the only change that
clearly helped, and it helps by collecting the premium, not by forecasting. The FX carry
weight repeated the pattern: core-pair design mean Sharpe −0.03 → +0.11, then better on every
unseen slice (the 10 crosses' holdout +0.12 → +0.31), still short of buy & hold on crosses.
Both were measured under the v0.7 engine; section 27 says what judging the carry rule on
those slices spent, and section 35 why every such number was re-measured in v0.8.

**Questions.**
- With a 2-ATR stop and a 3-ATR target, what hit rate breaks even before costs?
- Why did the strategic weight raise returns far more than Sharpe out of sample?

## 6. Risk: volatility targeting, VaR, and who has the last word

**Idea.** The same signal should mean a smaller position in a more volatile asset. Tail risk
needs a hard ceiling. One party must be able to say no, and its limits must be code.

**In the repo** (`agents/risk.py`): the neutral analyst volatility-targets at 15%; the
aggressive one takes max(1.25·|w|, vol-target); the conservative one halves the smaller and
caps it by VaR. The portfolio manager blends 25/50/25 (or takes the model's weight), then
applies the firm limits in order (shorting policy, max position 1.0, 1-day VaR95 ≤ 2% — the
left tail of the instrument's returns for a long, the right tail for a short, `risk_facts`
carries both — minimum trade 0.05) and the no-trade band. Every adjustment is logged.

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
rules; a numeric field that is present but null, a string or not finite rejects the whole
reply (rules apply, `source="rules"`) rather than being coerced to 0, and valid values are
clipped. Third-party text reaches the model only inside
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
| Strategic weight | 1.0 (equity premium) | carry / 2 capped at ±0.5 (carry premium, v0.5.1) |
| Shorting | Off by default | On |
| Execution default | VWAP over 78 five-minute slices; POV above 10% of ADV | TWAP over 288 slices; spread in pips |
| Order unit | Whole shares | Whole lots of the **base** currency (`execution.fx_lot_size`, 1,000) |
| Financing | Borrow fee on shorts | Carry accrued per bar from point-in-time rates |
| Idle cash (v0.8) | The uninvested fraction `1 − abs(w)` earns the bill rate | A forward: the whole account earns the bill rate |
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
JSON schema from the Python signature (type hints, defaults, docstring). `DeskTools` holds 16
tools on 5 servers: `market_data` (history, news, social, fundamentals, macro), `quant`
(technical, risk, alpha, xalpha, baselines), `knowledge` (search, list_documents), `portfolio`
(position, construct), `execution` (plan, submit_order). Each carries `ToolAnnotations`:
read-only, risk level, required capabilities, evidence type. `RecordingProvider` makes the
desk's analysts reach data through these tools without changing the analysts.

**Numbers.** 16 tools, 5 servers — measured:
`len(build_registry(DeskTools(SyntheticProvider(cfg), cfg)).descriptors()) = 16` — schemas
with `additionalProperties: false`; arguments are coerced (dates, integers, bounds) and unknown
arguments are refused.

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
argument guards (symbol universe and validity, every element of a `symbols` list, no future
dates, finite weights within the cap, bounded lookback, a positive quantity and a ticket
notional within `execution.max_order_notional`) → read-only (a state-changing tool needs
`propose_trades` and approval) → risk level (HIGH always needs approval) → allow. The guards
run *before* the approval decision so a bad order is denied by rule, never parked for a
person to approve. A rule set without a terminal rule fails closed. Approval gateways: `auto`
(development), `queued` (a person decides; the API exposes the queue), `deny`. The approval
key is the tool and its arguments within the task, so a request re-submitted after approval
is recognised.

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
unknown tools, stages and step types, drops unknown arguments, pins `symbol`, `as_of` and
`current_weight` to the task, refuses state-changing tools in plans, removes duplicate stages
and duplicate tool steps, inserts missing stages in order, caps the length and the plan's
total data budget (`agentic.max_plan_lookback_bars` symbol-days) and appends the governance
steps. Unusable model output falls back to the canonical plan with a note. The harness then
pre-checks every tool step against policy so an impossible plan fails before execution.

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
same step, and a per-run driving lock means two decisions landing together drive the run
once, not twice. Every run has its own tracer writing into one process-level `Metrics`.

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
read-only and risk annotations; every call it serves goes through a `ToolExecutor` with the
policy engine, the configured approval gateway and an evidence store for the role given on the
command line (`--role`, `--approval`), so a refusal comes back as an MCP error naming the
rule. `registry_from_stdio` turns a remote server's tools into a local registry so policy and
evidence apply to remote tools unchanged (tested with a real subprocess round trip); a remote
tool without annotations is classified fail-closed (not read-only, HIGH risk) and only an
operator override relaxes it. `agentic/api.py` is a FastAPI gateway with API-key roles: tasks
are 202-accepted and run in a background thread; reports, traces, evidence, cancel, approvals,
tools, health and one Prometheus exposition for the whole process. `agentic/tracing.py`
records spans with parent ids, JSON-lines logs and labelled counters and histograms.

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

**In the repo.** The C++ backtester (and its numpy twin) resolves the bar's open against
*both* levels first — a gap through the take-profit fills at the open exactly as a gap
through the stop does — then the intraday range, stop before target when both trade inside
the bar, and re-arms at the next rebalance. After an exit the desk is told it is flat (v0.8):
before each decision the walk-forward replays the engine on the bars so far and hands the
desk the position it actually holds, so the band cannot "keep" a position a stop already
closed. The no-trade band keeps a position within 0.10 of the target, only if that position
still passes every limit today.

**Numbers.** On 2016–2021 real data the band gave the same Sharpe with 44% fewer trades; stops
lowered mean return by about 30% at similar Sharpe, so they are off by default. Both figures
come from the v0.7 engine, and the stop figure was measured while the desk was still told it
held the pre-stop position after every exit (so it measured stops plus a forced re-entry);
v0.8 re-measured the ablation, see the evaluation's v0.8 section.

**Questions.**
- Why is "stop first when both trade" the right default with daily bars?
- The band makes the result path-dependent. Why is that realistic rather than a flaw?

## 20. Alpha research

**Idea.** A signal is only worth trading if it predicts, if the prediction lasts long enough to
trade, and if it is not just another copy of a signal you already have.

**In the repo** (`alpha.py`). Nine signals in [-1, 1]: 12-1 month momentum, vol-adjusted
20-day momentum, 5-day reversal, 52-week-high proximity, Donchian channel position, MACD in ATR
units, contrarian RSI, low-vol, and FX carry. `alpha_report` computes, for a horizon, the
Spearman IC and its t-statistic, IC decay across horizons, hit rate next to the base rate
(`up%`, the share of positive forward returns on the same bars, so a signal stuck at +1
shows `hit% == up%`), the tercile spread with terciles assigned by rank (bars tied at a
boundary share it as fractional weights, so the top and bottom groups never merge), signal
autocorrelation (turnover) and coverage, plus the correlation matrix of signals, a combined
alpha and a `significance_gated` row: the combination of only those alphas whose t clears
the gate, measured like any other alpha. The C++ core supplies rolling extremes and Spearman
correlation.

**The t-statistic is the trap.** A 10-day forward return sampled every day overlaps with its
neighbours, so of `n` pairs only about `n / 10` are independent. Until v0.8 the t-statistic
was `IC · sqrt(n)`, roughly three times too large, and the alpha analyst's "|t| ≥ 2" gate
passed pure noise on 98% of random-walk histories. `information_coefficient(signal, fwd,
horizon)` now returns `IC · sqrt(n / horizon)` (the same rule `xalpha.ic_summary` uses, so
the two analysts share one test); on 200 seeded random walks the analyst now speaks on about
22% of noise histories instead of 98% (`tests/test_v08_alpha.py`). A Newey-West variant is
offered for comparison only: with lags covering the return overlap it under-corrects these
slow signals badly.

**Numbers.** `agentic-trader alpha USDJPY --start 2021-01-04 --end 2024-03-28` on the
synthetic provider: `mom_20_vol` has IC 0.146 (t 1.32, n 814) and `rsi_contrarian` −0.157
(t −1.42, n 820); nothing clears the gate, so the `significance_gated` row is empty. The
same ICs read t 4.2 and −4.5 under the old statistic. The synthetic market is
regime-switching, so momentum and contrarian signals pull opposite ways. Real-data ICs are in
the cookbook recipe.

**Questions.**
- An IC of 0.3 on daily data appears in your report. What is the first thing to check?
- Why is signal autocorrelation a cost measure?
- Eight alphas are each gated at a per-alpha 5% level. Why does the analyst still speak on
  about a fifth of pure-noise histories, and what would a Bonferroni gate cost you?

## 21. Execution: from a weight to fills

**Idea.** A decision is a target weight; the market only knows orders. Splitting a parent order
over the session trades market impact against timing risk, and the cost must be measured.

**In the repo** (`algo.py`). `plan_execution` turns a weight change into a parent order
sized at the as-of close: `notional = |target − current| · capital` in the account currency
(`account_currency`, USD by default), a quantity in the instrument's own unit — whole shares
for an equity, whole lots of the *base* currency for FX (`execution.fx_lot_size`, 1,000), so
a USD/JPY order for 50,000 USD is 50,000 USD and a EUR/JPY order needs the EUR/USD rate or is
refused — rounded down once, here, and carried unchanged into the schedule, the ticket and
the CLI. It records the side, the intent (`open_long`, `add_long`, `reduce_long`,
`sell_short`, ...), a plan reference (a checksum over the ticket's fields, so an edited
number fails to verify) and the algorithm: VWAP for equities, POV above 10% of ADV, TWAP for
FX; Almgren-Chriss on request with the dimensionless urgency `costs.ac_kappa` (3.0; 0 is
TWAP), so the schedule no longer depends on the price level. A negative target under the
long-only equity policy is truncated to flat with the reason on the plan.
`synthetic_intraday_bars` builds the *next* session from its daily bar as a Brownian bridge
kept inside the high and low, with a U-shaped equity volume profile: the desk decides at the
close and the order works the following day, so the fill contains that day's drift, unknown
at decision time, rather than the decision day's own open-to-close move. `simulate_execution`
fills each slice at the bar's VWAP plus half the spread plus temporary impact
`coeff · daily_vol · sqrt(q_i / V_i)` on the slice's own participation in the bar's volume,
caps a slice at the bar's volume, and reports implementation shortfall on the *requested*
quantity — an unfilled remainder is marked at the close against arrival and shown as
opportunity cost — plus slippage against VWAP, in basis points. That is the same square-root
law the daily backtester charges (section 28): a VWAP schedule reproduces
`daily_vol · sqrt(Q / ADV)` exactly at any slice count, and TWAP and Almgren-Chriss reproduce
`algo_cost_ratio`. The v0.7 simulator charged each slice against the whole day's volume and
came out about eight times cheaper than the backtester for the same order, and ranked TWAP
below VWAP; one model now serves both.

**Numbers.** `agentic-trader execute AAPL --date 2024-03-01 --target 1.0` on the synthetic
provider, capital from the config (100,000 USD):

```
BUY 447 shares (notional 99,779 USD at 223.22) via VWAP in 78 slices; weight +0.00 -> +1.00; intent open_long; PLAN-7433f965648e
order is 0.00% of 20-day ADV
executed 447 of 447 shares (100%) on 2024-03-04; arrival 223.16, avg fill 224.57, session VWAP 224.53, close 228.44
implementation shortfall +63.3 bps, vs VWAP +1.7 bps (spread 1.0 bps, impact 0.7 bps), max slice participation 0.0%
```

Read the last line carefully: the order cost 1.7 bps against the session's VWAP (half the
2 bps quoted spread plus 0.7 bps of impact), and 63 bps against arrival, nearly all of which
is Monday's own rise from the open — timing, not cost. The same buy at $50 million
(`--capital 50000000 --target 0.6 --current 0.1`, 0.27% of ADV) pays 11.6 bps of impact and
12.6 bps against VWAP.

**The daily backtest's cost model, and closing the loop (v0.7).** The one-shot square-root
formula in `backtest.impact_coefficients` (used for the walk-forward backtests throughout
this page, one decision per rebalance day rather than an intraday session) implicitly assumes
a trade is *worked* as VWAP -- matching participation to the volume curve, which
`algo.algo_cost_ratio` shows minimises the square-root-law sum for a fixed total quantity, by
the same convexity argument as the questions below. `costs.execution_algo` makes that
assumption explicit and, when set to `"twap"` or `"ac"`, scales the day's impact by that
schedule's cost relative to VWAP on the same volume curve -- so the backtest's simulated cost
depends on *how* a trade would be worked, not only its size. v0.7 measured it on the core
universe's holdout portfolio at $1B: TWAP cost a little more than VWAP (2.51% vs 2.37% of
equity paid in impact over the period) because it ignores equities' U-shaped intraday curve,
and an aggressively front-loaded Almgren-Chriss (kappa=5) more again (3.14%), for trading
ahead of the volume rather than with it. **Those magnitudes are retracted**: every sleeve of
that portfolio was charged impact as if it traded the whole $1B rather than its fifteenth,
which is sqrt(15) ≈ 3.9 times too much (section 35); the VWAP < TWAP < AC ordering survives
and the table was re-measured at the sleeve's real capital in v0.8. `ac_kappa` above about
710 used to overflow `sinh`, turn the ratio into NaN and silently switch impact *off*; the
schedule is now computed in a form that is finite for any kappa and a non-finite ratio is an
error.

**Questions.**
- Why does a VWAP-shaped schedule show exactly the half-spread against session VWAP while a
  TWAP schedule does not?
- When would you choose Almgren-Chriss over VWAP, and which parameter decides?
- `algo_cost_ratio` is exactly 1.0 for VWAP by construction, for *any* volume curve. What
  property of the square-root law makes matching the curve always at least as good as any
  other split of the same total quantity?
- The shortfall above is +63 bps and the cost against VWAP +1.7 bps. Which number would you
  put in a transaction-cost model, and what would you need many days for?

## 22. Portfolio construction

**Idea.** Diversification is the one free lunch, but only with a usable covariance and a
weighting scheme that matches the mandate.

**In the repo** (`portfolio.py`). Covariance: EWMA (60-day half-life) shrunk toward the
constant-correlation target with the Ledoit-Wolf intensity *for that estimator*: the
intensity is computed with the same observation weights the covariance used (weighted
centring, weighted `pi`, `theta` and `rho`) and their effective sample size
`1 / sum(w²)` instead of `T`, which is what Ledoit and Wolf's formula reduces to for equal
weights. Computing the intensity with equal weights and `T` for an EWMA covariance measured
the noise of a different estimator and shrank less the more stale history sat in front of
the window (prepending 300 old rows moved the intensity eight times as much as it does now).
Schemes: equal, inverse-vol, risk parity (equal risk contributions via cyclical coordinate
descent), long-only minimum variance and mean-variance. Every scheme's allocation is
projected onto the capped simplex `{a ≥ 0, a ≤ max_weight, sum a = 1}`, so no sleeve holds
more than the cap under any scheme, and the cap is enforced again after a cross-group
budget step. `construct` applies the scheme to the desk's signed targets and reports
`allocation` — the pre-vol-target capital split, which sums to the gross cap — and `scale`,
the factor that takes the book to a 15% volatility target, capped so that neither the gross
cap nor the per-sleeve cap is exceeded; `weights = allocation · target · scale`. It also
reports marginal and component risk, percentage contributions, the diversification ratio
and the correlation matrix, and raises `ValueError` on a window with no variance so that
`run_portfolio_backtest(weighting=...)`, which re-estimates allocations from trailing
returns only, keeps its previous allocation rather than hold NaN.

**Numbers.** Risk parity on a 4-asset test covariance gives exactly 25% risk contribution
each; for independent synthetic instruments it coincides with inverse-vol, as it should. On
a skewed covariance the old clip-then-renormalise step left inverse-vol and risk parity at
0.72 in one sleeve under a 0.50 cap; the projection gives exactly 0.50
(`tests/test_v08_portfolio.py`).

**Questions.**
- Why is the scheme applied to capital shares and then multiplied by the signed targets,
  rather than solved on the signed weights directly?
- Equal capital across a 15%-vol stock and an 8%-vol currency gives very unequal risk. Which
  scheme fixes that, and what does it cost?
- Clipping an allocation at the cap and renormalising the rest can push another sleeve over
  the cap. Why does the Euclidean projection onto the capped simplex not have that problem?

## 23. Memory, edge cases and refusing to guess

**Idea.** The happy path is the easy 10%. A system meets holidays, bad ticks, typos, dead
feeds and broken files every week, and must either handle each or refuse loudly.

**In the repo.** Memory is an append-only log (one `write` and `fsync` per decision and per
resolution under a lock, so threads and separate `serve` processes sharing one file cannot
overwrite each other) that skips corrupt lines; an entry is valued on the recording
provider's own price series, `horizon_days` trading bars after the entry, and is expired
without a verdict when no series can value it (a provider switch, a split on another
source), rather than settled against whatever price the next visit happens to see. Weekends
use the last close; feeds older than 7 days are refused; mistyped pairs and invalid tickers
are refused; CSVs are put on one price basis and cleaned; flat prices, NaN weights and
non-finite positions are handled; a model reply whose number is `inf`, `nan`, `null` or a
string is rejected in favour of the rules, and a wrong-side stop is replaced; a bad symbol
in a watchlist becomes an error row; a task that fails ends in FAILED with the reason. Each
has a test.

**Questions.**
- Why refuse stale data rather than warn and continue?
- Which failures would you page on in production, and which only log?

# Part IV — knowing whether it works

## 24. Designing an honest evaluation

**Idea.** If you try enough variants on the data you report, one will look good by chance.
Choose everything on a design period, freeze, run the holdout once, and report it whatever it
shows.

**In the repo** (`evaluation.py`). Periods: design 2016–2021, holdout 2022 to mid-2026, a
Q1 2024 reference window and an opt-in reserve (2026-07-01 → 2026-09-25; three months is a
weak test, so a plain `evaluate()` does not run it). Universe: 10 equities and 5 FX pairs.
`RULES_V02` reproduces the old rules so every change has a before and after. The v0.3
search tried 16 variants on the design period; two were adopted. In v0.4 the alpha analyst
was measured the same way and not adopted. Every variant judged on the design period since
is an entry in `evaluation.TRIALS` (section 25), and `scripts/measure_v08.py` re-runs every
published table into `results/v08/` with the package version, commit and backend recorded
in each file's `provenance`, so a number in the documentation can be traced to the run that
produced it.

**The unit of measurement changed in v0.8.** Every Sharpe is now on *excess* returns over
the point-in-time 3-month bill rate, and idle cash earns that rate inside the backtest
(`cash_leg: auto` — FRED DTB3 with a one-day publication lag on real data, the constant
`risk_free_annual` on synthetic data, where it is 0 so synthetic numbers did not move).
Before v0.8 Sharpe was mean over standard deviation of raw returns with cash earning
nothing, which over 2022–2026, when bills paid 4–5%, compared a half-invested desk to a
fully invested benchmark on different footings. Section 35 has the mechanism.

**Questions.**
- The design-period Sharpe gain mostly vanished out of sample while the return gain survived.
  Explain why, using section 5.
- Having seen the holdout, may you tune against it? What would you need instead?
- A strategy is 55% invested and bills pay 4%. Its raw-return Sharpe and its excess-return
  Sharpe with idle cash credited answer different questions. State both questions.

## 25. Is a Sharpe ratio real? Selection and deflation

**Idea.** A Sharpe ratio is an estimate with an error bar, and the best of N tries is biased
upward. Three tools: the t-statistic and a bootstrap interval for the error bar; the
probabilistic Sharpe ratio for the chance the true Sharpe exceeds a benchmark given skew and
kurtosis; the deflated Sharpe ratio, which raises the benchmark to the expected maximum of N
null trials.

**In the repo** (`stats.py`, `agentic-trader stats`). `sharpe_ci_bootstrap` (circular block
bootstrap), `probabilistic_sharpe`, `expected_max_sharpe`, `deflated_sharpe`,
`min_track_record` and `selection_report`. The evaluation applies them to every variant
ever judged on the design period. From v0.3 to v0.7 that count was frozen at the 16
variants of the original ablation while more were tried; `evaluation.TRIALS` is now the
registry — 26 entries at v0.8 (the 16 v0.3 variants, three alpha-analyst variants, four FX
carry settings, the cross-sectional analyst, the EDGAR toggle and the track-record cut),
24 of them reproducible from config overrides and re-measured under the current engine by
`scripts/measure_v08.py`, 2 kept from the record because no config reproduces them — so the
deflation counts what was actually tried. The count is still a lower bound on the trials a
researcher ran in their head.

**Numbers.** See the evaluation's "selection" section for the chosen variant's bootstrap
interval, PSR and DSR, and the dispersion of the 26 trials' design-period mean Sharpes.

**Questions.**
- Why does negative skew lower the probabilistic Sharpe for the same Sharpe ratio?
- Twenty-six variants were tried. If their Sharpe ratios were all identical, what would the
  deflation be, and why?
- Two of the 26 trials cannot be re-run. Should they count toward `N`? What would leaving
  them out assume?

## 26. Reading the results honestly

**What was measured** (rule-based desk, real prices, frozen rules). Every figure in this
list is the v0.7-engine record: raw-return Sharpe with idle cash earning nothing, constant
weight between decisions, and plain buy & hold as the drawdown control. v0.8 re-measured
all of them under the conventions of section 35; the evaluation's v0.8 section has the
current values and this list is read as history.

- **Per instrument, out of sample:** mean Sharpe 0.46 against 0.55 for buy & hold on the core
  universe, 0.42 against 0.50 on the 45 unseen names. No edge on risk-adjusted return.
- **Drawdown:** lower than plain buy & hold's on 14 of 15 core and 40 of 45 extended
  instruments — measured against the wrong control. A desk that is about half invested
  draws down less than a fully invested benchmark by holding less; the fair control is the
  vol-targeted buy & hold, against which the gap is small and was never tested with a
  paired interval before v0.8. On FX there is no such control at all: the vol-target weight
  is capped at 1.0 and FX volatility sits below the 15% target, so the "control" is buy &
  hold itself.
- **As a portfolio:** 1.16 against 1.06 for plain buy & hold, but below the vol-targeted control
  at 1.24 — three point estimates with no interval on any difference, on raw returns over
  years when bills paid 4–5%. v0.8 credits idle cash, computes Sharpe on excess returns and
  puts a block-bootstrap interval on the portfolio-level difference (section 35), and the
  README's headline is whatever that interval supports.
- **Alpha analyst:** noise on the design period, three times; not adopted. Its significance
  gate was passing noise until v0.8 (section 20), so the analyst that was measured spoke
  far more often than the corrected one does.
- **FX:** close to zero; the carry weight (v0.5.1) lifts it on every unseen slice without
  reaching buy & hold on the crosses. Judging it on those slices spent them (section 27).

**What was measured once, small (v0.5.1):** the LLM desk — Claude Opus in every reasoning
role, anonymised prompts, five stocks, one quarter, 271 calls, $4. Same Sharpe as the rules
(2.19 against 2.19), less than half the exposure, return and drawdown on every name: the
model read the abstaining analysts as a reason to size down, which is the right reading of
the evidence it was given. Zero refusals, fallbacks or budget hits. It is still the only
LLM measurement, and it was not re-derived under the v0.8 engine: the multi-year harness is
staged and unexecuted (section 33).

**What was not measured:** whether the model adds value over the rules on the multi-year
periods with the full analyst team, and therefore whether the agentic layer's planner,
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

**In the repo.** v0.5 widened the universe from 15 to 60 instruments and partitioned it:
`UNIVERSES["core"]` (the 15 every choice was made on) and `UNIVERSES["extended"]` (26
sector equities, 9 rates / credit / commodity ETFs, 10 FX crosses) that no choice had
consulted, so the extended names were out of sample on *every* period, including the
design period. `PERIODS["reserve"]` (2026-07-01 → 2026-09-25) was declared the slice no
published number would consult. Every result row carries a `universe` tag;
`summary(universe=)` and `evaluate --universe core|extended|all` keep the two apart. The
protocol for the next rule change was written in the evaluation: choose on the core design
period, then judge on the extended universe and the reserve period, and report all three.

**The reserve is spent.** The protocol was used exactly as written, and using it consumed
the judge set. The FX carry weight (section 5) was chosen on the core pairs' design period
and adopted because it improved the four slices it had never seen — the ten crosses on the
design and holdout periods, and the reserve period on both universes. The v0.6 decisions to
keep EDGAR on and the cross-sectional analyst off quoted the reserve and extended numbers
too. By the document's own standard — the holdout stopped being unseen once it was reported
and compared against — the extended universe and the reserve were seen from v0.5.1 on, and
the evaluation kept calling the reserve "untouched" for two releases; that wording is gone.
Then v0.8 corrected the engine and re-measured every period on every universe (section 35),
so there is no slice left that has not been looked at. The next unseen data is the future:
bars after the v0.8 measurement date, and instruments the desk has never traded. Two more
honest notes on the carry decision: the design-period signal (−0.03 → +0.11 on five pairs)
sits inside the evaluation's own noise floor scaled to five instruments, and a three-month
reserve slice — where the standard error of a per-instrument annualised Sharpe is about 2 —
carries no evidential weight, yet counted as two of the four confirmations. The rule stays
because it was adopted under the protocol as it stood; what changed is what the record says
about how much it proved.

**Numbers** (v0.7 engine; re-measured in v0.8). The extended universe is a harder test: on
its holdout the desk's mean Sharpe is 0.42 against 0.50 for buy & hold (core: 0.46 vs
0.55; 0.37 and 0.44 under the v0.3 rules), it beats buy & hold on 15 of 45 names, and its
drawdown is 17.7% against 27.2% — against plain buy & hold, the control that section 26
explains is automatic to beat on drawdown. The story from the core universe (no Sharpe
edge per instrument, a lower drawdown that has yet to be shown against the fair control)
survives; it does not get better.

**Questions.**
- The reserve period grows every month, but every bar of it up to 2026-09-25 has been
  reported. From which date is it unseen again, and what has to be true of the *rules* on
  that date for the answer to matter?
- Why is a universe partition a stronger out-of-sample test than a time partition for a
  rule that was tuned on one set of names? What did judging the carry rule on the extended
  crosses cost, and would a time partition have cost less?

## 28. Execution costs belong in the backtest, not in a footnote

**The idea.** Close-to-close fills with a fixed bps cost are fine for a $100k account trading
large caps and wrong for a $1B one: market impact grows with the square root of the trade's
share of daily volume, so the same strategy has a different Sharpe at a different size. If
the execution model lives only in a separate simulator, the backtest is quietly assuming the
account is small.

**In the repo.** `costs.impact_coeff` turns the execution simulator's square-root model into
a per-bar coefficient for the backtester: a trade of `|dw|` costs
`|dw|^1.5 · K_t · sqrt(equity_t / initial_capital)` of equity with
`K_t = coeff · daily_vol_t · sqrt(capital / (price_t · ADV_t))`, everything known at the
close of bar `t` (trailing 20-day volatility and volume; the equity is the bar's opening
equity, so there is no look-ahead). The `sqrt(equity_t / initial_capital)` factor is v0.8:
a weight is a fraction of *current* equity, so a trade's notional follows the account, and
until v0.8 the engine charged every trade as if the account were still its starting size —
over-charging a strategy that had lost money and under-charging one that had made it,
compounding along the path. The engine (C++ and the numpy twin) charges it on entries,
exits and stop fills, reports `impact_paid`, and the same series is applied to every
baseline so the comparison stays fair. A portfolio sleeve is charged for the capital it
actually receives: `run_portfolio_backtest` computes the allocation first and passes each
sleeve `capital_share`, which scales `K_t` by `sqrt(share_t)` (section 35 says what went
wrong before). FX has no exchange volume and gets no impact unless `costs.fx_adv_notional`
is set. `--impact 1.0 --capital 1e9` on the backtest, portfolio and evaluate commands
(`evaluate` did not accept the flags until v0.8, although the README had said so).

**Numbers** (v0.7 engine, constant-capital impact; re-measured in v0.8). On the core
universe with the textbook coefficient, impact over the six-year design period was 0.08%
of equity at $100k, 0.8% at $10M and 7.7% at $1B for the desk (mean Sharpe 0.65 → 0.64 →
0.56). The direction of the ranking is the durable lesson: the daily volatility-target
baseline, with ~1,100 trades, pays *less* (5.7% at $1B) than the desk with ~106, because a
square-root law makes many tiny adjustments cheap and a few large jumps dear. The v0.7
claim that MACD "loses 75% to impact at $1B" is retracted: it read `impact_paid`, a sum of
per-bar fractions that can exceed 100%, as an equity loss, and it charged a strategy that
had already lost most of its equity as if it still traded a full $1B. Measured now:
`agentic-trader baselines NVDA --start 2016-01-04 --end 2021-12-31 --impact 1.0 --capital 1e9`
on the synthetic provider prints MACD `Impact% 92.15` with `CR% -91.26` (the review's
reproduction of the same run under the constant-capital engine, finding 23, charged 167%);
`tests/test_v08_engine.py::test_23_impact_coefficient_scales_with_sqrt_equity` pins the
rule. MACD still pays the most of the trend baselines and its Sharpe still goes negative at
$1B; the real-data magnitudes are the evaluation's v0.8 impact table.

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
independent observation per horizon (daily ICs of a 10-day return overlap: `n / horizon`
effective observations), the share of positive days, top-minus-bottom quantile spreads
rebalanced every horizon and breadth. `xalpha_report`, `xalpha_snapshot`, the
`quant.xalpha` tool and `agentic-trader xalpha`. Since v0.8 the time-series report
(section 20) applies the same `n / horizon` rule, so the two libraries' t-statistics are
comparable and the two analysts share one significance gate through
`significant_alpha_signal`; and both reports carry a `significance_gated` row — the
combination of only those alphas whose t clears the gate — measured like any other alpha,
so "combine the significant ones" is a number rather than a hope. The research layer got
its consumer in v0.6: `XAlphaAnalyst` (section 32) ranks the peer universe on these
scores, was put through the protocol and is off by default because it did not clear the
bar section 27 sets.

**Questions.**
- Why must a cross-sectional score be computed within an asset class?
- The t-statistic divides the day count by the horizon. What happens to it if you forget?
  (Section 20 has the measured answer for the time-series library.)

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

---

# Part VI — v0.6: real filings, statistical power, and the variance of a judgement

## 31. Point in time is a property of the source

**The idea.** "Point in time" is not a flag you set on a provider; it is a property of where
a number came from. A vendor snapshot of today's fundamentals cannot be used for 2019 no
matter how carefully you clip it, because the values were restated, the fields were added
later and the snapshot has no memory of what was known when. What makes a source point in
time is that every value carries the date it became public, and that the first print is
kept when a later one replaces it.

**In the repo.** SEC EDGAR is such a source, and it is free and keyless. `data/edgar.py`
reads the company-facts file (every XBRL fact a company ever filed, each with its `filed`
date) and the submissions file (every filing with its date and, for 8-Ks, its item codes).
A fact exists at `as_of` iff `filed <= as_of`. The awkward part is the accounting: 10-Q
cash-flow items are year-to-date, the fourth quarter is only ever reported inside the 10-K,
and Costco's quarters are 12 weeks with a 16-week fourth. `quarterly_table` rebuilds
quarters from the reported spans (direct quarters, year-to-date differencing, annual minus
nine months) and `ttm` sums four contiguous ones, so growth, margin, EPS, leverage and FCF
yield come out as a desk would have seen them, filing by filing.

**Per tag, per basis (v0.8).** Two rules that v0.6 got wrong, each found by a real filer.
First, a company often reports the same line under more than one XBRL tag (Mastercard
files gross and net revenue concurrently; Apple's revenue tag was renamed in 2018). v0.6
pooled the tags and differenced one against another, so a Q4 could be a 10-K total under
one tag minus nine months under a different one — a negative quarter, and a −25% "growth"
for Mastercard. Now every tag is reconstructed on its own, each trailing-year window is
taken whole from the highest-ranked tag that covers it (with a preference for staying on
the tag of the most recent window), and growth needs the same tag for both years, so a
rename costs one year of growth rather than inventing one. Second, "first print wins" was
the wrong rule for restated comparatives. Prints are replayed filing by filing, and a
filing that re-prints a past span at a materially different value (more than 5%) opens a
new *reporting basis*; the latest print within a basis wins, every difference is taken
within one basis, and a trailing year is one tag on one basis — so a desk on the date
between a 10-Q and the 10-K that recasts the year sees the latest single-basis year, never
a mix of old and new bases (Johnson & Johnson's 2023 recast). Around it sit recency guards
— a share count or balance-sheet instant older than 400 days, or a flow series that ended
more than a quarter before the report period, yields no ratio rather than a stale one — a
share-class ratio for Berkshire's B shares, and two sanity checks (market cap below 1% of
revenue, EPS above half the price) that drop a ratio and log why. Under v0.6, Berkshire's
P/E was 0.03 and its FCF yield 12,000%, and the analyst tilted +0.45 on it in every
decision; it now reports no per-share ratio for that ticker at any date. What EDGAR does
not have — consensus estimates, so the EPS surprise — is reported as `None`, and funds and
index ETFs, whose "facts" are not fundamentals, return nothing. The filing stream doubles
as a news feed: an 8-K item 2.02 is an earnings release, 4.02 a restatement, 1.03 a
bankruptcy; banks' thousands of structured-note prospectus supplements are not news and
are dropped. Coverage was checked for every equity in the 60-name universe at two dates.
The SEC asks for a contact in the User-Agent, so the client refuses to run without
`EDGAR_USER_AGENT` rather than sending a fake one.

**What it measured** (v0.6, under the v0.7 engine and the v0.6 EDGAR reconstruction;
re-measured in v0.8 with the rules above, with the fundamentals analyst no longer scoring
P/E against a sector multiple it does not have on real data, and with Sharpe on excess
returns). With real fundamentals and news, the rule-based fundamentals and news analysts
stopped abstaining — and the result is a lesson about rules written against synthetic
data. On the core equities the per-instrument Sharpe did not move (0.00 on design, +0.01
on holdout, intervals about ±0.1) while exposure rose 4–7 points and drawdown 3–4 points;
the 15-sleeve portfolio's holdout Sharpe went from 1.16 to 1.09, still above plain buy &
hold (1.06) on the raw-return convention of the time. On the 22 extended equities the
rules never saw, the same data added +0.02 (design) and +0.07 (holdout) of Sharpe, with
intervals whose lower bound printed as 0.00 — which is not an interval that excludes zero,
whatever v0.6 called it. The data stays on — a desk that hides filings from itself to
protect a headline is not a desk — and the rules that read it are the next thing to put
through the protocol.

**Questions.**
- Why is a restated comparative the right value for a backtest once it was public, and
  why must the year it is compared against be on the same basis?
- On synthetic data the fundamentals analyst scores P/E against a supplied sector multiple;
  on real data no sector multiple exists and the term is absent. What would a
  point-in-time sector P/E need, and which of EDGAR's files could supply it?

## 32. Rank the room and put it through the protocol

**The idea.** A time-series alpha asks whether a signal predicts an instrument's own
return. A cross-sectional alpha asks where the instrument ranks against its peers on the
same signal today. The second question is the stock-picker's, and v0.5 built the research
for it without letting an analyst consume it, because an analyst that has not cleared the
evaluation bar is a rule change in disguise.

**In the repo.** `XAlphaAnalyst` fetches the peer universe's histories (the core universe
of the instrument's asset class by default, or `xalpha_universe`), z-scores every alpha
across the peers on every date, measures each alpha's cross-sectional IC over the 900-day
window, and keeps only alphas whose IC t-statistic is at least 2 in magnitude — the same
significance gate as the time-series alpha analyst, through the same function
(`significant_alpha_signal`). It abstains when nothing qualifies. The cross-section is
computed once per (universe, date) and cached, so an evaluation over the whole universe
pays for it once per decision date, and the analyst computes only the IC it needs rather
than the full report's decay curves and spreads.

**What it measured.** Put through the protocol on top of the EDGAR data, the analyst changed the core
design period's per-instrument Sharpe by -0.01 [-0.02, 0.00] (better on 5 of
15); on the unseen slices, core holdout 0.00, extended holdout -0.01
[-0.01, 0.00], reserve +0.01 / -0.03. The design-period interval does not clear zero, so it is off by default — the third analyst in this repository to be measured and kept out, which is what the protocol is for. The mechanism is plain: sampled every 60 bars over the design period on the 15 core names (390 decisions), the analyst spoke on 2.6% of them — 3.8% of the equity decisions, never on FX — with a mean |signal| of 0.30 when it did, because over a 900-day window no alpha clears the cross-sectional |t(IC)| ≥ 2 gate on most dates.

**Questions.**
- The peer set for the published run was the whole 60-name universe, filtered by asset
  class. Does using the extended names as *peers* spend them as a holdout? What exactly
  would spend them?
- Why must the cross-sectional analyst and the time-series alpha analyst share one
  significance gate?

## 33. Power across instruments, and the variance of a judgement

**The idea.** Two questions hide behind "is the edge real?". The first is along time: is
this instrument's Sharpe distinguishable from zero? The block bootstrap answers it. The
second is across the universe: is the *mean* difference between two strategies over 15 or
45 instruments more than the luck of which instruments were drawn? That needs a bootstrap
over instruments, pairs kept together. And when the strategy is a model rather than a rule,
a third question comes first: ask it the same thing five times — how far apart are the
answers?

**In the repo.** `stats.paired_bootstrap` resamples instruments with replacement and
returns the mean paired difference, its interval and a two-sided p; `EvaluationResult.paired`
and `paired_table` apply it to any metric against any baseline, and the CLI prints the
table after every evaluation with a `scheme` and `groups` column and a Benjamini-Hochberg
`significant` flag computed on the unrounded p (rows with fewer than three paired
instruments print p as NaN and do not count toward the correction). Read against the core
universe (`scheme=instruments`, v0.6 measurement under the v0.7 engine; re-measured in
v0.8): the desk's per-instrument Sharpe minus buy & hold's is +0.07 [−0.05, +0.19] on the
design period and −0.10 [−0.20, 0.00] on the holdout — the noise floor the earlier concepts
estimated, now measured.

**Instruments are not exchangeable, and the v0.7 fix made it worse.** The plain bootstrap
assumes the instruments are independent draws. Nine rate, credit and commodity ETFs that
mostly move together are one noisy draw shared nine times, so the effective sample is
nearer the number of clusters than the number of names and the plain interval is too
narrow. v0.7 tried to fix this with a *stratified* bootstrap: resample within each
asset-class group with the group's count held fixed. That conditions on the group
composition, so its replicate variance is the pooled *within*-group variance only — the
between-group component that plain resampling at least retains is discarded — and it can
only narrow the interval while doing nothing about the correlation it was meant to handle;
the changelog said the opposite, and every v0.7 interval and BH flag was anti-conservative
relative to v0.6 on the same data. It is retracted. v0.8 replaces it with a two-stage *cluster* bootstrap: draw whole groups with
replacement, then instruments within each drawn group, and take the pooled mean. Drawing
whole groups is what carries the shared shock into the interval; the within-group stage is
kept because with a handful of groups the groups-only scheme is itself anti-conservative,
and in Monte Carlo under a shared within-group factor the two-stage scheme's coverage of a
true zero is closest to nominal and errs conservative when the groups turn out to be
independent (`tests/test_v08_stats.py`). It engages only with at least
`MIN_CLUSTER_GROUPS = 5` distinct labels, which the core (equity, FX: 2) and extended (3)
universes do not have — there it falls back to the plain instrument scheme and the table
says so — and `--universe all` has five (equity and FX, core and extended, and the macro
ETFs), where the intervals come out materially wider and fewer rows are flagged. A
plain-scheme interval over a clustered universe should still be read as too narrow.
`evaluate(repeats=N)` runs the agent N times per (period, symbol) and `run_dispersion`
reports the across-run spread, which is zero for the rules and the first number to read for
a model. `calibration.calibrate` freezes one state and runs it n times at each of several
anchors (the position the desk is told it already holds): dispersion of the target weight
and agreement of the action; the anchoring slope of the mean target on the anchor (0 ignores
the book, 1 keeps whatever it holds); and drift against a stored report on the same state
after a model or prompt change. `prompts.prompt_registry` makes the last comparison
meaningful: a SHA-256 of every agent's system prompt and prompt-building code, bundled into
one hash and recorded in every evaluation and calibration result, so "same prompts" is a
fact in the record rather than a recollection. The multi-year LLM harness that uses all of
this — model tiers on the core universe over design and holdout, three repeated runs for
variance, one calibration — is staged with a dollar cap per stage but **has not been run**;
the evaluation's Limitations section says so explicitly, so "the code supports it" is never
mistaken for "it has been measured".

**Questions.**
- The paired bootstrap treats instruments as exchangeable draws. Which of the 45 extended
  names most obviously violate that, and what would the plain interval understate? Why does
  resampling *within* their group with a fixed count make it worse rather than better?
- With exactly five clusters, one of which holds 26 of the 60 instruments, what does the
  pooled mean of a cluster replicate mostly measure, and what would a wild-cluster
  bootstrap or a t(G−1) critical value change?
- An anchoring slope of 1 means the desk keeps whatever it holds. Is that always wrong?
  When is it exactly the no-trade band doing its job?

## 34. Is the risk model telling the truth? VaR coverage backtesting

**The idea.** A 95% VaR cap is a promise: "on 95% of days, the loss will not exceed this
number." A promise needs a test, not a diagram. Two questions separate a well-calibrated
risk model from a lucky or unlucky one: does the *rate* of breaches match the target (too
many means overconfident, too few means needlessly wide), and are breaches *independent* in
time (clustering means the model reacts too slowly to a regime change, even if its average
rate looks fine)? Kupiec (1995) answers the first with a likelihood-ratio test of the
observed breach count against a binomial at the target rate. Christoffersen (1998) answers
the second by comparing the likelihood of the observed breach/no-breach sequence under
independence versus under a first-order Markov chain that lets the breach probability depend
on yesterday. Both reduce to a chi-square statistic; this repo computes the tail probability
in closed form from the standard normal CDF rather than pulling in scipy for one function.

**In the repo.** `stats.rolling_var_forecast` builds a walk-forward historical-VaR forecast
(each day uses only the trailing window before it, so there is no look-ahead), and
`stats.var_backtest` runs both tests against the realized returns, returning a `VarBacktest`
with the breach rate, both LR statistics and both p-values, plus a two-test "conditional
coverage" p-value (the sum of the two LRs against 2 degrees of freedom). `agentic-trader
stats --var-backtest` exposes it on any returns CSV.

**Which VaR is being tested.** v0.7 ran the tests on the 15-sleeve core portfolio's own
holdout returns — the equal-weight book's realised daily P&L after sizing, caps, stops and
costs — with a 120- and a 250-day rolling historical quantile of that same series, and
called the outcome "the desk's own risk model is well calibrated". That claim is retracted:
the desk's risk model is something else. What sizes a position live is
`agents.risk.risk_facts`: a 95% historical VaR of the instrument's last 250 daily returns
(the left tail for a long, the right tail for a short, since v0.8), multiplied by `|w|`
and checked against the 2% cap in `PortfolioManager.guardrails`. The 120-day window is
not used anywhere by the desk, no per-instrument forecast was ever compared with a
realised instrument return, and a book-return series that the caps themselves produced is
the least demanding input a historical-simulation forecast can be given. So v0.8 reports
two things and labels each: (a) *a rolling historical VaR of the portfolio's own returns*
at 120 and 250 days, which is what v0.7 measured (under the v0.7 engine: breach rate 5.7%
and 4.5% respectively, neither test rejecting; re-measured in v0.8), and (b) *the desk's
per-instrument forecast* — the 250-day historical VaR from `risk_facts`, walked forward
over the holdout for each of the 15 core instruments and tested against that instrument's
next-day return, one row per instrument with n, breaches, breach rate, Kupiec p and
Christoffersen p, and a count of how many instruments reject at 5%
(`scripts/measure_v08.py`, `results/v08/var_coverage.json` → `instruments`). Only (b)
speaks to the model the desk trades on; the evaluation's v0.8 section has the table.
Book-level VaR (`risk.max_book_var_95`) was off in every published run and is not covered
by either test. What makes any of this usable is that a p-value that had rejected would
have been reported exactly the same way.

**Questions.**
- Kupiec and Christoffersen both look backward at realized breaches. What kind of risk-model
  failure would neither test ever catch?
- The portfolio test feeds a VaR-capped, vol-targeted book's returns to a historical-VaR
  forecast of those returns. Why is passing that test weak evidence, and what does the
  per-instrument test add?
- The forecast here is historical VaR on 120/250-day windows. What would change if the
  window were much shorter — would you expect more or fewer breaches to cluster?

## 35. Constant units, idle cash and the fair comparison

**The idea.** A backtest is a set of accounting conventions, and every Sharpe in this
repository is a function of them. v0.8 changed several at once because a review of the
code found that each biased a published comparison in a known direction. Every real-data
number in the earlier sections moved as a result, and the honest order of business is to
say what changed and why before quoting any of the new ones.

**What the engine does now** (`cpp/include/at/backtest.hpp`, the `run_backtest` docstring;
the numpy twin is held to the C++ core by the parity tests in `tests/test_v08_engine.py`).

1. *Constant units between decisions.* Until v0.7 the engine held the *weight* constant
   between decisions, which means it silently re-levered the book every bar for free: a
   position that rose was trimmed and one that fell was topped up, with no trade recorded
   and no cost charged, and FX carry accrued on a notional that reset daily. Now a target
   is executed on a decision bar — the target changes or the rebalance mask is set —
   fees and impact on `|dw|` come out of equity first and the target is a fraction of what
   is left, `E[t+1] = E[t] · (1 − k_in) · (1 + g) · (1 − k_out)`; on a hold bar the units
   are held, the weight drifts as `w · (1 + r) / (1 + g)`, and nothing is traded or charged.
   The leverage cap binds on targets, so a held weight can sit above it between decisions.
   Trade counts come from executed trades and turnover from the per-bar `traded` array,
   exit fills included. Measured with `quant.run_backtest` on four bars, one decision
   (`cost_bps=0`):

   ```
   constant units, target 0.5 decided once:
     prices     [100.0, 110.0, 99.0, 99.0]
     positions  [0.5, 0.5238, 0.4975, 0.4975]
     traded     [0.5, 0.0, 0.0, 0.0]
     equity     [100000.0, 105000.0, 99500.0, 99500.0]
   ```

   The 0.5238 is the old convention's silent trade: 0.5 of a book worth 105,000 after a
   10% move is 52.4% of it, and holding it there is what a desk that decided once actually
   does. Costs are multiplicative now as well: a 10 bps entry, a 5% stop and a 10 bps exit
   are `0.999 · 0.95 · 0.999`, not `1 − 0.001 − 0.05 − 0.001`.
2. *The desk is told its true position.* Before each decision the walk-forward replays the
   engine on the bars so far and hands the desk the weight it actually holds coming into
   that bar: the previous decision's units drifted with the market, or 0 after a stop,
   take-profit or ruin. Until v0.7 it was told the previous *target*, so after a stop the
   portfolio manager's no-trade band could "keep" a position that no longer existed and the
   engine bought it back at cost, and every decision record and prompt misstated the book
   (section 19). A "keep" inside the band now executes as no trade rather than as a trade
   to the rounded weight. Every desk path changed — the desk re-decides on its drifted
   position, so its turnover and trade counts moved in both directions across instruments.
3. *A gap through the take-profit fills at the open*, as a gap through the stop always did
   (section 19).
4. *Ruin is a floor.* When a bar's loss reaches the whole account the return is −1, equity
   is 0, the position is written off and every later bar is flat; `ruined_at` records the
   bar and the metrics stop there instead of annualising a resurrection.
5. *Impact follows equity* (section 28): the coefficient built for the starting capital is
   rescaled by `sqrt(equity_t / initial_capital)`, because a weight is a fraction of the
   equity the account has, not the equity it started with.
6. *A sleeve pays the impact of its own capital.* `run_portfolio_backtest` ran every sleeve
   with the whole portfolio's `initial_capital` and then combined them at `1/N`. The impact
   coefficient is proportional to `sqrt(capital)`, so a sleeve of a 15-sleeve $1B book was
   charged as if it traded $1B rather than $67M — `sqrt(15) ≈ 3.87` times too much, on
   every trade of every sleeve. That is why the v0.7 execution-algorithm table in section
   21 is retracted in magnitude while its ordering survives: the factor was common to VWAP,
   TWAP and Almgren-Chriss. The allocation is now computed before the sleeves run and each
   sleeve receives `capital_share`, which scales its coefficient by `sqrt(share_t)`;
   `tests/test_v08_engine.py::test_1_portfolio_of_n_sleeves_pays_the_impact_of_capital_over_n`
   checks the sleeve against a standalone account of `capital / N` to 1e-9, for every
   strategy, equal weighting and class budgets alike.

**Idle cash, and what a Sharpe ratio is a ratio of.** The engine had no cash leg: a desk
that was 55% invested earned nothing on the other 45%, and every published Sharpe was
mean over standard deviation of raw returns with the risk-free rate set to 0. Over
2022–2026, when three-month bills paid 4–5%, that compared a half-invested desk with a
fully invested benchmark on different footings, and the portfolio headline — desk 1.16
against plain buy & hold 1.06 — was the kind of number that convention produces. v0.8 adds
the cash leg and changes the metric together, because neither alone is right: subtracting
the bill rate without crediting cash penalises a half-invested book twice, which is what
turning on `risk_free_annual` did before. The convention now: an equity position is
*funded*, so the uninvested `1 − |w|` of the account earns the bill rate; an FX forward is
not, so the whole account earns it and the position's carry is the interest differential,
as it always was; Sharpe, Sortino and t(SR) are computed on `r_t − rf_t / ppy` with the
same per-bar rate; annualised and cumulative return and Calmar stay total-return, because
they are properties of the equity curve. The rate is the provider's point-in-time series
(`risk_free_series`; `cash_leg: auto` is FRED DTB3 with a one-day publication lag on real
data and the constant `risk_free_annual` on synthetic and CSV data; `off` credits nothing
and the metrics fall back to the constant). Synthetic numbers are therefore unchanged by
the cash leg — the constant is 0 — and every real-data number is not. On a seeded random
walk with bills at 4%, rebalanced daily at zero cost (`quant.run_backtest`,
`quant.compute_metrics`):

```
seeded random walk, 6 years, bills 4%:
  v0.8: idle cash credited, Sharpe on excess returns   w=0.5: AR +3.68% Sharpe -0.010 | w=1.0: AR +2.65% Sharpe -0.010
  cash_leg off, rf 4% subtracted only                  w=0.5: AR +1.63% Sharpe -0.265 | w=1.0: AR +2.65% Sharpe -0.010
  v0.7: no cash leg, rf 0                              w=0.5: AR +1.63% Sharpe +0.245 | w=1.0: AR +2.65% Sharpe +0.245
```

Read the columns. Under the v0.8 convention halving every position leaves the Sharpe
unchanged, which is the property a comparison between a 55%-exposed strategy and a
98%-exposed one needs. Subtracting the rate without the credit (middle row) punishes the
half-invested book for holding cash it was in fact paid for. The v0.7 convention is also
scale-invariant, but it answers a different question: return per unit of risk *over
zero*. When cash pays 4%, zero is not the alternative an investor faced, and a strategy
that earned a few points a year at low volatility has beaten cash by less, per unit of
risk, than its raw Sharpe suggests — while the idle-cash credit gives some of that back.
Which effect wins is an empirical matter that the evaluation's v0.8 section settles for
the real portfolio; the review's arithmetic on the published figures put the desk, buy &
hold and the vol-targeted control within a few hundredths of one another, and the README
headline is whatever the measured interval supports, not the old ordering.

**The fair comparison, at portfolio level.** Three more things the review found the
portfolio comparison lacked, all added in v0.8.

- *An interval on the difference.* Section 33's bootstrap resamples instruments, so it
  cannot see that all fifteen sleeves lived through the same 2022 bear market and the same
  2023–24 rally; for a single 15-sleeve portfolio the unit of independence is the day.
  `stats.paired_sharpe_block_bootstrap` (`PortfolioReport.sharpe_difference`) resamples
  both daily return series with the same circular blocks, takes each replicate's Sharpe on
  excess returns and reports the interval and p of the difference — desk minus vol-target
  and desk minus buy & hold — printed next to every portfolio Sharpe.
- *The cadence's phase.* Every published number was decision bar 0 of a five-bar cadence.
  `rebalance_offset` runs the same backtest starting on bars 1 to 4; the spread across the
  five is the noise floor a portfolio difference has to clear before it means anything, and
  it is reported alongside.
- *Drawdown against the fair control.* Section 26 explains why plain buy & hold is the
  wrong drawdown control. `paired_table(metric="MDD%")` against the vol-targeted control,
  with the Benjamini-Hochberg flag, is now part of the record — and where the control does
  not exist it says so: on FX the vol-target weight `min(1.0, 0.15 / vol)` is 1.0 whenever
  trailing volatility is below 15%, which for the major pairs is nearly always, so the
  "control" row equals buy & hold and the drawdown comparison has no control there.

**What did not change.** The rules. No parameter of the desk was re-fitted to the new
engine; the same frozen rules were re-measured under the corrected conventions, and the
evaluation's v0.8 section reports each earlier decision re-checked under them — EDGAR on
or off, the carry rule, the v0.2 rules, the alpha analysts, the track-record cut — as
information, with the design period as the only basis for a choice. The v0.5.1 LLM result
was not re-derived and remains the only LLM measurement.

**Questions.**
- A carry-earning FX position under constant units de-levers as cash accrues; under
  constant weight it did not. In which direction did the switch move the FX baselines'
  returns, and why did equities barely move?
- Equities credit the bill on `1 − |w|`, forwards on the whole account. Why is that the
  right pair, and what double-counting would treating a forward as funded introduce, given
  that its carry is already the interest differential?
- The sleeve error was a factor of `sqrt(N)`, not `N`. What property of the impact law
  makes it `sqrt`, and what does that say about splitting a fixed book across more sleeves?
- The block bootstrap over days and the cluster bootstrap over instruments (section 33)
  answer different questions. Describe a result that would clear one and not the other.
- The desk now sees its drifted position and the no-trade band compares the new target to
  it. When the drifted position sits above a cap the band cannot keep it. Is that the band
  failing, or the cap working?
