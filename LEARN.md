# Learn agentic-trader

This guide works through the 68 ideas behind the project in order. For each concept it gives
the idea, where the repository implements it, the real numbers it produces, and questions to
test your understanding. Two shorter pages give the whole picture first: [how the AI works](docs/ai/ai.md) and
[how the quant works](docs/quant/quant.md). Recipes are in [COOKBOOK.md](COOKBOOK.md); component detail is in
[docs/architecture/overview.md](docs/architecture/overview.md); the measured results are in
[docs/evaluation/evaluation.md](docs/evaluation/evaluation.md). Numbers from the synthetic
provider or a local command were regenerated for v0.8. Every real-data figure is copied from
`results/v08/tables.md`, which `scripts/render_v08_tables.py` renders from the files
`scripts/measure_v08.py` wrote under `results/v08/` (each carries the commit that produced
it); a figure kept from an earlier release says so, and concept 35 explains why v0.8
re-measured every one of them under a corrected engine. The measured section of the
evaluation is
[v0.8: engine and protocol corrections, and every number re-measured](docs/evaluation/evaluation.md#v08-engine-and-protocol-corrections-and-every-number-re-measured).

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

**Part VIII — v0.9 and v0.10: looking for an edge, and not finding one**

36. [Attribution: whose return is it?](#36-attribution-whose-return-is-it)
37. [The control that is hard to beat](#37-the-control-that-is-hard-to-beat)
38. [A wider base: many asset classes, equal risk](#38-a-wider-base-many-asset-classes-equal-risk)
39. [Trend as a return stream](#39-trend-as-a-return-stream)
40. [Carry as a return stream](#40-carry-as-a-return-stream)
41. [Combining streams with a risk budget](#41-combining-streams-with-a-risk-budget)
42. [Core and overlay: how big should the view be?](#42-core-and-overlay-how-big-should-the-view-be)
43. [Pre-registration: decide before you look](#43-pre-registration-decide-before-you-look)
44. [The forward record is the only unseen data](#44-the-forward-record-is-the-only-unseen-data)
45. [Append-only records and honest revisions](#45-append-only-records-and-honest-revisions)

**Part IX — v0.11 and v0.12: a second review, and a longer test**

46. [When did the market know?](#46-when-did-the-market-know)
47. [Confidence should follow the evidence](#47-confidence-should-follow-the-evidence)
48. [One statistic, every trial, every row](#48-one-statistic-every-trial-every-row)
49. [A longer design period](#49-a-longer-design-period)
50. [A negative result, and one routine in two languages](#50-a-negative-result-and-one-routine-in-two-languages)

**Part X — v0.13: the model interface**

51. [Structured outputs and the contract gate](#51-structured-outputs-and-the-contract-gate)

**Part XI — v0.14: leakage and risk**

52. [Purged cross-validation and the leak canary](#52-purged-cross-validation-and-the-leak-canary)
53. [A pre-registered expectation that failed](#53-a-pre-registered-expectation-that-failed)

**Part XII — v0.15: text, retrieval and an auditable agent**

54. [Measuring retrieval before an analyst may use it](#54-measuring-retrieval-before-an-analyst-may-use-it)
55. [Red-teaming the fence, and what the numbers do and do not cover](#55-red-teaming-the-fence-and-what-the-numbers-do-and-do-not-cover)

**Part XIII — v0.16: what the model adds**

56. [Asking a small model where it helps, and checking it first (v0.16)](#56-asking-a-small-model-where-it-helps-and-checking-it-first-v016)
57. [Every study cell is a trial, and what a decision costs (v0.16)](#57-every-study-cell-is-a-trial-and-what-a-decision-costs-v016)

**Part XIV — v0.17: a second review, and measuring the measurements**

58. [How small an IC could the test have seen? Newey-West t and the MDE](#58-how-small-an-ic-could-the-test-have-seen-newey-west-t-and-the-mde)
59. [Many gates are one family: Benjamini-Hochberg across them](#59-many-gates-are-one-family-benjamini-hochberg-across-them)
60. [Effective trials: hidden ones and correlated ones](#60-effective-trials-hidden-ones-and-correlated-ones)
61. [Execution lag: deciding on a close you have not seen yet](#61-execution-lag-deciding-on-a-close-you-have-not-seen-yet)
62. [Did the model remember? A recall audit with a null and a placebo](#62-did-the-model-remember-a-recall-audit-with-a-null-and-a-placebo)
63. [Lineage: which code, prompt and model made this row](#63-lineage-which-code-prompt-and-model-made-this-row)
64. [Conformal intervals when the data are not exchangeable](#64-conformal-intervals-when-the-data-are-not-exchangeable)
65. [A red team needs a control arm](#65-a-red-team-needs-a-control-arm)
66. [Long runs that survive a kill, and skips that are counted](#66-long-runs-that-survive-a-kill-and-skips-that-are-counted)
67. [Classical ML in this repo: what is fitted, and when it is on](#67-classical-ml-in-this-repo-what-is-fitted-and-when-it-is-on)
68. [LLM-as-judge: a judge must agree with labels first](#68-llm-as-judge-a-judge-must-agree-with-labels-first)

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

**Numbers** (v0.8; `results/v08/tables.md`, "with the alpha analyst, corrected gate (a) vs
default (b)"). On the 2016–2021 design period, core 15, the desk with the alpha analyst
behind the corrected gate against the default desk: mean Sharpe 0.66 vs 0.66, mean
difference −0.00 [−0.05, +0.05], p 0.90, better on 5 of 15. The interval is a paired
bootstrap over instruments (`scheme=instruments`, section 33; the on-vs-off tables print p
without a Benjamini-Hochberg flag). That is noise across 15 instruments, so it is off by
default (section 24). The holdout says the same (−0.00 [−0.04, +0.02], p 0.79); the two
short windows favour it (q1_2024 +0.10 [+0.01, +0.23], p 0.01; reserve +0.07 [−0.00, +0.20],
p 0.21) and are information, not a choice basis (section 27). How often the corrected gate
speaks in these runs was not measured: the driver recorded no abstention tally. The v0.4
analyst was measured with a gate that passed noise (section 20) and under the v0.3 engine;
its two variants survive only as the recorded entries of the trials registry (0.60 and
0.58 against the frozen rules' recorded 0.65; section 25).

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

**Numbers** (v0.8; `results/v08/tables.md`, "trials registry" and "FX carry rule on (a) vs
off (b)"). Raising the equity neutral weight from 0 to 0.25, 0.50 and 1.00 moved the
design-period mean Sharpe over the core 15 from the v0.2 control's 0.47 to 0.54, 0.58 and
0.63, cumulative return from 58.24% to 82.41%, 100.26% and 121.95%, and exposure from
43.99% to 50.55%, 54.86% and 60.37% (the trials table prints means without intervals; the
ordering is the reading, not the second decimal). It was the one change of the 16-variant
ablation that clearly helped — the signal tweaks leave the mean at 0.45–0.48 around the
control's 0.47 — and it helps by collecting the premium, not by forecasting. The FX carry
weight repeated the pattern at a smaller scale. Agent mean Sharpe with the rule on minus off
(a paired bootstrap over instruments, `scheme=instruments`; the rule touches only the
currency pairs, so most names tie): design core 0.66 vs 0.62, +0.04 [−0.01, +0.10], p 0.11,
4 of 15 wins; holdout core +0.02 [−0.02, +0.07], p 0.37; holdout extended (means over all
45; only its 10 crosses can differ) 0.26 vs 0.23, +0.04 [+0.00, +0.08], p 0.04, 7 of 45
wins; q1_2024 core +0.49 [+0.12, +0.94], p 0.01; reserve extended +0.14 [+0.03, +0.28], p
0.00; all 60 under the cluster scheme, holdout +0.03 [−0.00, +0.12], p 0.23. Positive on
every slice, small, with most intervals touching zero. On the crosses the desk is still
short of buy & hold: extended FX (10) holdout median Sharpe 0.26 against 0.28, paired −0.11
[−0.25, +0.04], p 0.14, not BH-significant ("paired Sharpe by asset class ... extended (45)
fx (10)"). Section 27 says what judging the carry rule on those slices spent, and section 35
why every such number was re-measured in v0.8.

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
decision's confidence is scaled by the multiplier at finalisation. When a model signal diverges,
`apply_weight_rule` also cuts the weight: toward the PM's rules weight when a model PM
overrode it, toward flat otherwise, and never to a larger absolute exposure; the PM guardrails
then run on the result. With a weight of 0.30 and scale 0.5 the rule gives 0.15 (COOKBOOK
recipe 134). Until 2026-11-12 the rule moved toward the neutral weight, which is 1.0 for
equities, so the same alarm turned 0.30 into 0.65: an alarm that added risk (review A4). So
the title holds for confidence, which is only ever lowered; the weight can be cut as well.

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
split by heading into 76 chunks and embedded with a hashed TF-IDF (unigrams and bigrams into
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

**Numbers** (v0.8 engine, 2016–2021 design period, core 15; `results/v08/tables.md`,
"trials registry"). The no-trade band gave the same design mean Sharpe as the v0.2 control
(0.47 vs 0.47; cumulative return 58.11% vs 58.24%) with 47% fewer trades per instrument
(135.20 vs 254.20). Intraday stops: Sharpe 0.45 vs 0.47, cumulative return 44.10% vs
58.24%, drawdown 12.67% vs 13.31%, 292.20 trades — about a quarter less cumulative return
at a similar Sharpe, so they are off by default. The trials table prints means without
intervals. The earlier record (the table's recorded column: 0.50 for the control and the
band, 0.47 for stops, v0.3 engine) measured stops while the desk was still told it held
the pre-stop position after every exit, so it measured stops plus a forced re-entry; the
v0.8 figures are with the desk told its true position. The whole ablation is in
[the evaluation's v0.8 section](docs/evaluation/evaluation.md#v08-engine-and-protocol-corrections-and-every-number-re-measured).

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

**Numbers.** `agentic-trader execute AAPL --date 2024-03-01 --target 0.6 --current 0.1` on
the synthetic provider, capital from the config (100,000 USD); the transcript is copied from
cookbook recipe 53, which is where it is regenerated:

```
BUY 223 shares (notional 49,778 USD at 223.22) via VWAP in 78 slices; weight +0.10 -> +0.60; intent add_long; PLAN-064e3ec3a337
order is 0.00% of 20-day ADV
executed 223 of 223 shares (100%) on 2024-03-04; arrival 223.16, avg fill 224.57, session VWAP 224.53, close 228.44
implementation shortfall +63.0 bps, vs VWAP +1.5 bps (spread 1.0 bps, impact 0.5 bps), max slice participation 0.0%
```

Read the last line carefully: the order cost 1.5 bps against the session's VWAP (half the
2 bps quoted spread plus 0.5 bps of impact), and 63 bps against arrival, nearly all of which
is Monday's own rise from the open — timing, not cost. The same buy at $50 million
(`--capital 50000000`, 0.27% of ADV; the transcript just before it in recipe 53) pays 11.6
bps of impact and 12.6 bps against VWAP, and the recipe's $1B NVDA order shows a partial
fill with its unfilled remainder priced as opportunity cost.

**The daily backtest's cost model, and closing the loop (v0.7).** The one-shot square-root
formula in `backtest.impact_coefficients` (used for the walk-forward backtests throughout
this page, one decision per rebalance day rather than an intraday session) implicitly assumes
a trade is *worked* as VWAP -- matching participation to the volume curve, which
`algo.algo_cost_ratio` shows minimises the square-root-law sum for a fixed total quantity, by
the same convexity argument as the questions below. `costs.execution_algo` makes that
assumption explicit and, when set to `"twap"` or `"ac"`, scales the day's impact by that
schedule's cost relative to VWAP on the same volume curve -- so the backtest's simulated cost
depends on *how* a trade would be worked, not only its size. v0.8 measured it on the core
universe's holdout portfolio at $1B with every sleeve charged at its own capital
(`results/v08/tables.md`, "execution algorithm, $1B holdout portfolio"): VWAP Sharpe 0.78,
cumulative return 49.62%, drawdown 7.83%, mean sleeve impact paid 0.66% of equity; TWAP
0.78 / 49.56% / 7.83% / 0.70%, a little dearer because it ignores equities' U-shaped
intraday curve; an aggressively front-loaded Almgren-Chriss (kappa=5) 0.77 / 49.30% / 7.84%
/ 0.87%, for trading ahead of the volume rather than with it. These are three point
estimates from one portfolio path with no interval printed on their differences; the
rebalance-phase spread of 0.06 in section 35 is the noise floor to read them against. The
v0.7 table (2.51% for TWAP against 2.37% for VWAP, 3.14% for Almgren-Chriss) **is retracted
in magnitude**: every sleeve of that portfolio was charged impact as if it traded the whole
$1B rather than its fifteenth, which is sqrt(15) ≈ 3.9 times too much (section 35); the
VWAP < TWAP < AC ordering survives. `ac_kappa` above about
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
source), rather than settled against whatever price the next visit happens to see; an entry
written before v0.8 names no provider, is never valued, and is expired by any named
provider's visit once twice its horizon has passed (`DecisionMemory(path,
max_staleness_days=7)`; `resolve` takes the same tolerance). Weekends
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
nothing, which over 2022–2026, when bills averaged 3.99% a year (the `rf` column of
`results/v08/portfolio_holdout.csv`), compared a half-invested desk to a
fully invested benchmark on different footings. Section 35 has the mechanism.

**Numbers** (v0.8; `results/v08/tables.md`, "v0.3+ rules (a) vs v0.2 rules (b), core";
paired over instruments, `scheme=instruments`). The rules chosen in v0.3 against the v0.2
rules they replaced, agent mean Sharpe on the core 15: design 0.66 vs 0.47, +0.19 [+0.10,
+0.28], p 0.00, 12 of 15 wins; holdout 0.34 vs 0.34, −0.00 [−0.11, +0.09], p 0.99, 8 of 15;
q1_2024 +0.72 [+0.29, +1.17], p 0.00; reserve +0.95 [+0.45, +1.47], p 0.00. The
design-period gain did not carry to the holdout at all (v0.7 said it shrank); the two short
windows favour v0.3. Cumulative return is where the strategic weight shows: on the design
period the frozen v0.3 rules' 116.52% (the current rules' 118.18%) against the control's
58.24% (trials table).

**Questions.**
- The v0.3 rules' design-period Sharpe gain over the v0.2 rules did not carry to the holdout
  at all. Using section 5, say what the strategic weight collects and why that need not show
  up as a Sharpe gain out of sample.
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

**Numbers** (v0.8; `results/v08/tables.md`, "selection statistics for the frozen rules" and
"trials registry"). The frozen rules' design-period 15-sleeve portfolio: n 1564 days, annual
Sharpe 1.375 (annualised at 252 periods a year by `selection_report`; the portfolio tables
of sections 26 and 35 print 1.40 for the same daily series because portfolio metrics
annualise at 260, the FX sleeves' count: 1.375 × √(260/252) ≈ 1.40), t 3.42, skew −0.635,
kurtosis 8.41, bootstrap 95% interval [0.593, 2.17], PSR against zero 1.00; with 26 trials
the expected maximum Sharpe of that many null trials is 0.161, the deflated Sharpe
probability 0.998 and the minimum track record 496 periods. (Corrected 2026-11-12: 0.998 was withdrawn; it and its v0.11 successor are an absolute deflated Sharpe, which is not a selection test (the no-desk vol-target control scores 0.921 on it at 81 trials). The selection statistic is the deflated Sharpe of desk minus vol-matched control: 0.009 at the registry's 81 trials (`docs/results/round2/selection_stat.md`).) The table's caveat, verbatim:
"an upper bound on the true significance: the benchmark is built from the dispersion of
trial_sharpes_annual, which is usually narrower than the dispersion of the full return
series each trial would have produced, so the true search space is wider than this reports
and the real probability is no higher than the number given." The dispersion itself:
re-measured under the v0.8 engine the v0.2 control is 0.47 (recorded 0.50 under the v0.3
engine), the strategic equity weight 0.25 / 0.50 / 1.00 is 0.54 / 0.58 / 0.63 (recorded 0.54
/ 0.58 / 0.66), the frozen v0.3 rules 0.62 (0.65); the ordering of the 16-variant ablation
is unchanged. Trials added since v0.3: the gated alpha analyst of v0.5 (0.66), the four
carry settings of v0.5.1 (0.65, 0.66 adopted, 0.65, 0.64), the cross-sectional analyst
(0.66) and EDGAR off (0.65) from v0.6, and the track-record cut off (0.66) from v0.8 — all
between 0.64 and 0.66 on the design period, which is why the deflation moves so little.

**Questions.**
- Why does negative skew lower the probabilistic Sharpe for the same Sharpe ratio?
- Twenty-six variants were tried. If their Sharpe ratios were all identical, what would the
  deflation be, and why?
- Two of the 26 trials cannot be re-run. Should they count toward `N`? What would leaving
  them out assume?

## 26. Reading the results honestly

**What was measured** (rule-based desk, real prices, frozen rules; v0.8 engine and
conventions, section 35). Every figure below is copied from `results/v08/tables.md` and is
current — the same story as
[the evaluation's v0.8 section](docs/evaluation/evaluation.md#v08-engine-and-protocol-corrections-and-every-number-re-measured);
the v0.7-engine record it replaces (raw-return Sharpe with idle cash earning nothing,
constant weight between decisions, plain buy & hold as the drawdown control) is kept in the
evaluation's earlier sections under a banner. "Median Sharpe" is the summary tables'
per-instrument median; a difference is the paired tables' mean difference with its 95%
interval, p and Benjamini-Hochberg flag; the bootstrap resamples instruments
(`scheme=instruments`) on core and extended and whole asset-class-by-universe groups
first (`scheme=clusters`, 5 groups: core equities, core FX, extended equities, macro ETFs,
FX crosses) on all 60 (section 33).

*Under review (2026-11-13, review C8): this significance used the cross-instrument interval; the time-block re-run is pending.*

- **Per instrument, out of sample, the desk is below buy & hold on Sharpe, and below the
  vol-targeted control too.** Core 15 holdout median Sharpe 0.30 (desk) against 0.51 (buy &
  hold) and 0.52 (vol-target); desk minus buy & hold −0.10 [−0.21, −0.00], p 0.04, not
  BH-significant; desk minus vol-target −0.11 [−0.21, −0.00], p 0.04, not BH-significant.
  Extended 45 holdout 0.25 against 0.39 and 0.27; desk minus buy & hold −0.07 [−0.12,
  −0.02], p 0.01, BH-significant; desk minus vol-target −0.03 [−0.09, +0.02], p 0.19, not
  BH-significant. All 60 (clusters): desk minus buy & hold −0.08 [−0.15, −0.03], p 0.00,
  BH-significant; desk minus vol-target −0.05 [−0.15, 0.00], p 0.07, not BH-significant.
  Design period, core: 0.67 against 0.73 and 0.69; desk minus buy & hold +0.06 [−0.06,
  +0.17], p 0.29, not BH-significant. On the extended names, which no rule was tuned on, the Sharpe deficit against buy &
  hold clears the BH bar, which is more than v0.7's "noise either way". The desk does beat
  the signal-flipping baselines on most slices (holdout, all 60, desk minus SMA +0.25
  [+0.01, +0.43], p 0.04, not BH-flagged; extended +0.28 [+0.16, +0.41], p 0.00,
  BH-significant).
- **Drawdown: lower than plain buy & hold's, and almost all of it is volatility scaling.**
  Core holdout mean maximum drawdown 17.40% (desk) against 31.64% (buy & hold) and 18.98%
  (vol-target); paired desk minus buy & hold −14.24 points [−20.41, −8.70], p 0.00,
  BH-significant; desk minus vol-target −1.58 [−4.33, +1.14], p 0.27, not significant. On
  the core equities (10), the names the desk was tuned on, holdout 22.11% against 40.24%
  and 21.28%, desk minus vol-target +0.83 [−1.63, +3.21], p 0.50, not BH-significant: no
  lower than the fair control's. On the extended 45 the gap against the fair control is real
  but a fraction of the gap against buy & hold: 15.46% against 26.39% and 19.79%; desk minus
  vol-target −4.33 [−6.10, −2.55], p 0.00, BH-significant; desk minus buy & hold −10.93
  [−13.41, −8.64], p 0.00, BH-significant. On FX there is essentially no control: the
  vol-target weight is capped at 1.0 and FX volatility sits below the 15% target nearly
  always, so the core FX (5) rows against vol-target and against buy & hold differ only in
  the second decimal (holdout −6.40 [−10.32, −2.09] against vol-target and −6.46 [−10.34,
  −2.14] against buy & hold, both p 0.00, BH-significant; the q1_2024 and reserve rows are
  identical). Calmar on the extended holdout: desk minus buy & hold +0.11 [+0.03, +0.19], p
  0.00, BH-significant; desk minus vol-target +0.07 [0.00, +0.14], p 0.05, not flagged — a
  lower bound printed as 0.00 does not exclude zero.
- **As a 15-sleeve equal-capital portfolio the desk no longer beats plain buy & hold on
  Sharpe; the v0.7 claim (1.09 against 1.06) is retracted.** Holdout, idle cash credited and
  Sharpe on excess returns: desk 0.80 (cumulative return 50.62%, drawdown 7.80%, exposure
  59.10%), buy & hold 0.86 (96.91%, 20.43%), vol-target 0.99 (61.48%, 9.17%). The
  portfolio-level difference now carries a paired block-bootstrap interval over days (block
  10, n 1167): desk minus buy & hold −0.06 [−0.41, +0.30], p 0.748; desk minus vol-target
  −0.19 [−0.53, +0.16], p 0.297. Design: 1.40 against 1.28 and 1.43; +0.12 [−0.16, +0.40], p
  0.434 and −0.03 [−0.28, +0.23], p 0.898. The rebalance-phase sweep (holdout, offsets 0–4)
  gives the desk 0.80 / 0.85 / 0.86 / 0.80 / 0.84 — a spread of 0.06 — against a fixed 0.99
  and 0.86, so the cadence noise floor is the size of the differences quoted. The README
  headline follows these cash-leg-on numbers and says the convention in one clause; section
  35 has the cash leg's own effect.
- **Alpha analyst:** noise on the design period, three times; not adopted. With the
  corrected gate (section 20) it is −0.00 [−0.05, +0.05], p 0.90 on the core design period
  (section 3); the v0.4 analyst that was measured spoke far more often, and how often the
  corrected one speaks was not recorded.
- **FX:** close to zero. Core FX (5) holdout median Sharpe 0.06 (desk) against −0.05 (buy &
  hold); extended FX (10) holdout 0.26 against 0.28. The carry weight (v0.5.1) is positive
  on every slice and small — design core +0.04 [−0.01, +0.10], p 0.11; holdout extended
  +0.04 [+0.00, +0.08], p 0.04 (section 5) — without reaching buy & hold on the crosses.
  Judging it on those slices spent them (section 27).

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
honest notes on the carry decision: the design-period signal (re-measured in v0.8 as +0.04
[−0.01, +0.10], p 0.11 over the core 15, with only the five pairs able to differ; section 5)
sits inside the evaluation's own noise floor, and a three-month reserve slice — where the
standard error of a per-instrument annualised Sharpe is about 2 — carries no evidential
weight, yet counted as two of the four confirmations. The rule stays because it was adopted
under the protocol as it stood; what changed is what the record says about how much it
proved.

*Under review (2026-11-13, review C8): this significance used the cross-instrument interval; the time-block re-run is pending.*

**Numbers** (v0.8; `results/v08/tables.md`, "summary: extended (45), holdout", the paired
Sharpe and MDD% tables and "summary: extended (45), reserve"; `scheme=instruments`). The
extended universe is a harder test: on its holdout the desk's median Sharpe is 0.25
against 0.39 for buy & hold and 0.27 for the vol-targeted control (core: 0.30 against 0.51
and 0.52), the paired mean difference against buy & hold is −0.07 [−0.12, −0.02], p 0.01,
BH-significant, and against vol-target −0.03 [−0.09, +0.02], p 0.19, not BH-significant; it
beats buy & hold on 12 of 45 names. Its mean drawdown is 15.46% against 26.39% for plain buy
& hold — the control section 26 explains is automatic to beat — and 19.79% for the fair
control, a paired −4.33 points [−6.10, −2.55], p 0.00, BH-significant, against −10.93
[−13.41, −8.64] for buy & hold. The reserve period says little: core median 0.81 against
1.05 for both controls, extended −0.11 against −0.08 and −0.11, with paired differences
whose intervals cover zero (core desk minus buy & hold −0.06 [−0.21, +0.12], p 0.44;
extended +0.08 [−0.14, +0.33], p 0.54; neither BH-significant). The story from the core
universe (no Sharpe edge per instrument, a drawdown that is mostly volatility scaling)
survives on the extended names, which no rule was tuned on, and gets one notch worse: there the Sharpe deficit against buy
& hold clears the BH bar.

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

**Numbers** (v0.8, equity-scaled impact, textbook coefficient 1.0, core 15;
`results/v08/tables.md`, "impact sweep, core universe"). The desk keeps its mean Sharpe at
$100k and $10M — design 0.66 → 0.66 → 0.66 paying 0.04% and 0.43% of equity in impact,
holdout 0.34 → 0.34 → 0.34 paying 0.03% and 0.26% — and at $1B loses 0.05 on the design
period (0.61, impact paid 4.24%) and 0.03 on the holdout (0.31, 2.53%). The vol-target
baseline, which adjusts every day, loses 0.07 and 0.04 at $1B (0.64 → 0.57 paying 6.92%;
0.45 → 0.41 paying 3.57%): under the equity-scaled law it pays *more* than the desk, not
less. The v0.7 reading — that its ~1,100 small trades cost less (5.7% at $1B) than the
desk's ~106 (7.7%), so many tiny adjustments were cheap and a few large jumps dear — was
measured with impact charged at constant starting capital and does not survive; the v0.8
renderer prints no trade counts for the sweep, so that comparison is not restated. Where
size decides everything is the signal-flippers: SMA loses 0.19 and 0.14 at $1B (design
0.57 → 0.38 paying 24.63%; holdout 0.18 → 0.04, 12.99%) and MACD 0.58 and 0.44 (0.40 →
−0.18 with impact charges summing to 64.71% of equity over the period (added up daily, not a terminal loss); 0.14 → −0.30, 39.01%), while buy & hold barely
notices (0.60 → 0.59, 0.97%; 0.45 → 0.44, 0.48%). The v0.7 claim that MACD "loses 75% to
impact at $1B" is retracted: it read `impact_paid`, a sum of per-bar fractions that can
exceed 100%, as an equity loss, and it charged a strategy that had already lost most of its
equity as if it still traded a full $1B. Measured now on the synthetic provider (a local
command, not real data):
`agentic-trader baselines NVDA --start 2016-01-04 --end 2021-12-31 --impact 1.0 --capital 1e9`
prints MACD `Impact% 92.15` with `CR% -91.26` (the review's reproduction of the same run
under the constant-capital engine, finding 23, charged 167%);
`tests/test_v08_engine.py::test_23_impact_coefficient_scales_with_sqrt_equity` pins the
rule. On real data MACD still pays the most of the baselines and its Sharpe goes negative
at $1B; the table is in
[the evaluation's v0.8 section](docs/evaluation/evaluation.md#v08-engine-and-protocol-corrections-and-every-number-re-measured).

**Questions.**
- Why does impact per trade scale with `|dw|^1.5`, and what does that imply for a strategy
  that rebalances rarely but in big steps?
- The sweep changes no ranking between the desk and the vol-target control, but it turns
  MACD's Sharpe negative at $1B. What does that say about quoting a Sharpe ratio without a
  capital figure, and for which kind of strategy does the capital figure matter most?

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
rename costs one year of growth rather than inventing one (two tags whose prints agree
within 1% are one concept). Second, "first print wins" was the wrong rule for restated
comparatives, and "any re-print opens a new basis" turned out to be wrong too. Prints are
replayed filing by filing. A filing that re-prints a past span at a materially different
value (more than 5%) is not believed on its own: a lone re-print is ignored and remembered,
and a later filing that repeats it within 5% confirms it as a *correction*, taken in place
of the held value and never a basis change. A recast opens a new *reporting basis* only on
spans no ignored print anticipated, only when corroborated — two re-printed spans, or a
first-print comparative — and only when the recast year reconciles with its quarters
(within 2% of the larger of the annual value and the sum of the quarters; per-share values
within 15%); a re-print whose spans look mis-tagged is rejected rather than opened as a
basis. Within a basis the latest print wins, every difference is taken within one basis,
and a trailing year is one tag on one basis — so a desk on the date between a 10-Q and the
10-K that recasts the year sees the latest single-basis year, never a mix of old and new
bases (Johnson & Johnson's 2023 recast). The fourth quarter is cross-checked directly
against the annual only for additive flows. Around it sit recency guards: a share count or
balance-sheet instant older than 400 days yields no ratio; a flow series is declared dead
only after 120 filing days without a print, and until then a window that lags the report
period is served with a flag (`revenue_period_end`, `net_income_period_end`,
`eps_period_end`, `ocf_period_end`) that the fundamentals analyst reads — it skips a term
whose window lags by more than 100 days and abstains when the report itself is more than
120 days stale — while free-cash-flow yield is computed only when the operating-cash-flow
and capex windows end together. A share-class ratio handles Berkshire's B shares, and two
sanity checks (market cap below 1% of revenue, EPS above half the price) drop a ratio and
log why. Under v0.6, Berkshire's P/E was 0.03 and its FCF yield 12,000%, and the analyst
tilted +0.45 on it in every decision; it now reports no per-share ratio for that ticker at
any date. What EDGAR does
not have — consensus estimates, so the EPS surprise — is reported as `None`, and funds and
index ETFs, whose "facts" are not fundamentals, return nothing. The filing stream doubles
as a news feed: an 8-K item 2.02 is an earnings release, 4.02 a restatement, 1.03 a
bankruptcy; banks' thousands of structured-note prospectus supplements are not news and
are dropped. Coverage was checked for every equity in the 60-name universe at two dates.
The SEC asks for a contact in the User-Agent, so the client refuses to run without
`EDGAR_USER_AGENT` rather than sending a fake one.

**What it measured** (v0.8, under the reconstruction above, with the fundamentals analyst
no longer scoring P/E against a sector multiple it does not have on real data, and with
Sharpe on excess returns; every earlier EDGAR figure is superseded. `results/v08/tables.md`,
"EDGAR on (a) vs off (b)": agent mean Sharpe with the filings minus without, paired over
instruments on core and extended and over the five asset-class-by-universe groups on all
60 — the on-vs-off
tables print p without a BH flag). With real fundamentals and news, the rule-based
fundamentals and news analysts stopped abstaining — and the result is a lesson about rules
written against synthetic data. The filings reach only the equities, so on the core 15 the
design period cannot tell on from off: +0.01 [−0.03, +0.04], p 0.72, 4 of 15 better; the
holdout says the same, −0.01 [−0.07, +0.04], p 0.83. On the core names the filings add
exposure and drawdown for about no Sharpe: the trials table's "EDGAR filings off" row has
design mean Sharpe 0.65 against 0.66 with them, cumulative return 110.44% against 118.18%,
drawdown 15.30% against 17.59%, exposure 60.48% against 63.31%. On the extended 45 the
rules never saw, the same data adds +0.01 [+0.00, +0.02], p 0.02 on the design period (16 of
45) and +0.03 [+0.01, +0.06], p 0.00 on the holdout (15 of 45) — a lower bound printed as
+0.00 is not an interval that excludes zero, whatever v0.6 called it, and under the cluster
scheme on all 60 the interval covers zero on both periods (design +0.01 [−0.01, +0.02], p
0.19; holdout +0.02 [−0.02, +0.05], p 0.39). The short windows lean the same way (q1_2024
core +0.09 [+0.00, +0.21], p 0.02; reserve core +0.11 [+0.00, +0.23], p 0.04; reserve
extended +0.03 [−0.04, +0.10], p 0.45). The data stays on — it is a data source, not a
rule, the design period shows no harm, and a desk that hides filings from itself to
protect a headline is not a desk — and the untuned rules that read it are the next thing
to put through the protocol.

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

**What it measured** (v0.8; `results/v08/tables.md`, "with the cross-sectional analyst (a)
vs default (b)"; paired over instruments, `scheme=instruments`, p without a BH flag). Put
through the protocol on top of the EDGAR data, the analyst changed the core design
period's per-instrument mean Sharpe by −0.01 [−0.02, +0.00], p 0.36 (better on 5 of 15); on
the slices no rule was tuned on, core holdout 0.00 [−0.01, +0.02], p 0.60, extended holdout −0.00 [−0.01,
+0.00], p 0.23, reserve core +0.01 [−0.00, +0.04], p 0.28 and reserve extended −0.02 [−0.06,
+0.01], p 0.20; the one slice that moves is q1_2024 core, +0.09 [+0.00, +0.20], p 0.04, a
lower bound printed as +0.00. The design period shows nothing, so it is off by default —
the third analyst in this repository to be measured and kept out, which is what the
protocol is for. The mechanism is plain, on the v0.6 measurement (not re-run in v0.8):
sampled every 60 bars over the design period on the 15 core names (390 decisions), the
analyst spoke on 2.6% of them — 3.8% of the equity decisions, never on FX — with a mean
|signal| of 0.30 when it did, because over a 900-day window no alpha clears the
cross-sectional |t(IC)| ≥ 2 gate on most dates.

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
instruments print p as NaN and do not count toward the correction). Since 2026-11-13 (review
C8) the primary interval and p of a Sharpe row come from `stats.paired_time_block_table`:
circular day blocks (length 10) shared by every instrument, `scheme=time-block`, with the
path length in `days`. The reason: every instrument's difference comes from the same calendar
path, so resampling instruments treats one path as N independent draws and gives an interval
several times too narrow (`tests/test_round2_stats.py`: 20 instruments loading on one daily
factor). The cross-instrument figure moves to `secondary` columns, read as a statement about
these names in this window; a row without daily returns (another metric, or a result read
from JSON written without `include_returns=True`) falls back to it and its `scheme` says so.
The BH flag is decided on the primary p. The figures that follow were measured before this
change. Read against the core
universe (v0.8; `results/v08/tables.md`, "paired Sharpe, agent minus baseline: core (15)";
`scheme=instruments`, groups 2): the desk's per-instrument mean Sharpe minus buy & hold's
is +0.06 [−0.06, +0.17], p 0.29, on the design period and −0.10 [−0.21, −0.00], p 0.04, on
the holdout, neither BH-significant — the noise floor the earlier concepts estimated, now
measured. The contrast is the same comparison over all 60 under the cluster scheme (5
groups): holdout desk minus buy & hold −0.08 [−0.15, −0.03], p 0.00, BH-significant.

*Under review (2026-11-13, review C8): this significance used the cross-instrument interval; the time-block re-run is pending.*

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
ETFs), where the table prints `clusters`. A plain-scheme interval over a clustered
universe should still be read as too narrow.
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
two things and labels each (`results/v08/tables.md`, the two "VaR coverage" tables, from
`results/v08/var_coverage.json`): (a) *a rolling historical VaR of the 15-sleeve
portfolio's own holdout returns*, which is what v0.7 measured — 120-day window: n 1048, 65
breaches, breach rate 6.20%, Kupiec p 0.0847, Christoffersen p 0.1488, conditional
coverage p 0.0798, not rejected at 5% but close; 250-day window: n 918, 42 breaches, 4.58%,
Kupiec p 0.5493, Christoffersen p 0.1650, conditional coverage p 0.3188 — and (b) *the desk's
per-instrument forecast*: the 250-day historical VaR from `risk_facts`, walked forward over
the holdout for each of the 15 core instruments and tested against that instrument's
next-day return (n 1126 for the equities, 1167 for the pairs). Every breach rate is above
5% (5.23% to 6.57%); Kupiec rejects at 5% on 2 of 15 (AAPL 6.57%, p 0.0207; AUDUSD 6.34%,
p 0.0432); Christoffersen independence rejects on 6 of 15 (AAPL 0.0027, SPY 0.0121, JPM
0.0158, GBPUSD 0.0182, META 0.0274, USDCAD 0.0441): breaches cluster. Only (b) speaks to
the model the desk trades on, and what it says is that the instrument forecast is a little
thin and slow to react;
[the evaluation's v0.8 section](docs/evaluation/evaluation.md#v08-engine-and-protocol-corrections-and-every-number-re-measured)
has the 15-row table. Book-level VaR (`risk.max_book_var_95`) was off in every published run
and is not covered by either test. What makes any of this usable is that a p-value that had
rejected would have been reported exactly the same way — and eight of them did (two Kupiec,
six Christoffersen).

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
2022–2026, when three-month bills averaged 3.99% a year (the `rf` column of
`results/v08/portfolio_holdout.csv`), that compared a half-invested desk with a
fully invested benchmark on different footings, and the v0.7 portfolio headline — desk 1.09
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
Which effect wins is an empirical matter, and the measurement settles it
(`results/v08/tables.md`, "cash leg on vs off: holdout" and "cash leg off (a) vs on (b)"):
the cash leg lowered every strategy's holdout Sharpe and decided nothing about the
ranking. Holdout 15-sleeve portfolio, cash leg on → off: desk 0.80 → 1.04 (cumulative
return 50.62% → 35.17%, drawdown 7.80% → 8.01%), buy & hold 0.86 → 1.05 (96.91% → 86.23%),
vol-target 0.99 → 1.24 (61.48% → 46.21%), SMA 0.64 → 0.85, MACD 0.38 → 0.54; design
portfolio: desk 1.40 → 1.46 (93.64% → 87.97%), buy & hold 1.28 → 1.32, vol-target 1.43 →
1.49. Per instrument, agent Sharpe with the cash leg off minus on: holdout core +0.10
[+0.06, +0.15], p 0.00; extended +0.17 [+0.13, +0.21], p 0.00; all 60 +0.15 [+0.04, +0.23],
p 0.02 under the cluster scheme; design core +0.03 [+0.02, +0.04], p 0.00, all 60 +0.04
[+0.01, +0.06], p 0.01. The reading: 2022–2026 bills averaged 3.99% a year (the `rf` column of
`results/v08/portfolio_holdout.csv`), so an
excess-return Sharpe is lower for everyone; crediting the desk's idle capital raises its
cumulative return (35% → 51%) but not its excess-return Sharpe by as much as the bill takes
from a low-volatility strategy, and buy & hold holds almost no cash; 2016–2021 bills were
near zero, so the design period barely moves. Under either convention the holdout order is
desk < buy & hold < vol-target (1.04 / 1.05 / 1.24 off; 0.80 / 0.86 / 0.99 on), so the v0.7
"beats plain buy & hold" was already inside the noise and is retracted regardless of the
cash leg. Decomposing the v0.7 → v0.8 holdout portfolio move from 1.09 to 0.80: the
cash-leg convention accounts for 1.04 → 0.80 (−0.24, measured here on one engine); the
other engine corrections above, plus any data drift since 2026-09-25, account for 1.09 →
1.04 — a difference between two records made on two engines, not a measured effect. The
README headline follows the cash-leg-on numbers and says the convention in one clause.
Portfolio metrics annualise with the largest periods-per-year among the sleeves, 260 when
a currency pair is present.

**The fair comparison, at portfolio level.** Three more things the review found the
portfolio comparison lacked, all added in v0.8.

- *An interval on the difference.* Section 33's bootstrap resamples instruments, so it
  cannot see that all fifteen sleeves lived through the same 2022 bear market and the same
  2023–24 rally; for a single 15-sleeve portfolio the unit of independence is the day.
  `stats.paired_sharpe_block_bootstrap` (`PortfolioReport.sharpe_difference`) resamples
  both daily return series with the same circular blocks, takes each replicate's Sharpe on
  excess returns and reports the interval and p of the difference — desk minus vol-target
  and desk minus buy & hold — printed next to every portfolio Sharpe. Measured on the
  holdout (block 10, n 1167 days): desk minus vol-target −0.19 [−0.53, +0.16], p 0.297;
  desk minus buy & hold −0.06 [−0.41, +0.30], p 0.748; on the design period (n 1564 days)
  −0.03 [−0.28, +0.23], p 0.898 and +0.12 [−0.16, +0.40], p 0.434 (`results/v08/tables.md`,
  "portfolio Sharpe difference").
- *The cadence's phase.* Every published number was decision bar 0 of a five-bar cadence.
  `rebalance_offset` runs the same backtest starting on bars 1 to 4; the spread across the
  five is the noise floor a portfolio difference has to clear before it means anything, and
  it is reported alongside. Measured on the holdout ("rebalance-phase sweep"): the desk's
  Sharpe is 0.80, 0.85, 0.86, 0.80 and 0.84 on offsets 0 to 4, a spread of 0.06, against a
  fixed 0.99 for vol-target and 0.86 for buy & hold; every offset's difference against
  either control has an interval covering zero (offset 2, desk minus buy & hold +0.00
  [−0.35, +0.38], p 0.981).
- *Drawdown against the fair control.* Section 26 explains why plain buy & hold is the
  wrong drawdown control. `paired_table(metric="MDD%")` against the vol-targeted control,
  with the Benjamini-Hochberg flag, is now part of the record — and where the control does
  not exist it says so: on FX the vol-target weight `min(1.0, 0.15 / vol)` is 1.0 whenever
  trailing volatility is below 15%, which for the major pairs is nearly always, so the
  "control" row equals buy & hold and the drawdown comparison has no control there.
  Measured ("paired MDD%, agent minus control"): core 15 holdout desk minus vol-target
  −1.58 [−4.33, +1.14], p 0.27, not BH-significant, against −14.24 [−20.41, −8.70] for buy
  & hold; extended 45 holdout −4.33 [−6.10, −2.55], p 0.00, BH-significant; on the core
  equities (10) alone +0.83 [−1.63, +3.21], p 0.50, not BH-significant — the desk draws down no less than the
  fair control on the names it was tuned on (section 26).

*Under review (2026-11-13, review C8): this significance used the cross-instrument interval; the time-block re-run is pending.*

**What did not change.** The rules. No parameter of the desk was re-fitted to the new
engine; the same frozen rules were re-measured under the corrected conventions, and
[the evaluation's v0.8 section](docs/evaluation/evaluation.md#v08-engine-and-protocol-corrections-and-every-number-re-measured)
reports each earlier decision re-checked under them — EDGAR on or off (section 31), the
carry rule (section 5), the v0.2 rules (section 24), the alpha analysts (sections 3 and 32),
the track-record cut — as information, with the design period as the only basis for a
choice. The track-record cut, the one new toggle: removing it is worth about +0.01 on nearly
every slice (design extended +0.01 [+0.00, +0.01], p 0.01; holdout extended +0.01 [+0.00,
+0.02], p 0.02; reserve core +0.04 [+0.00, +0.09], p 0.04), and the core design period —
the only basis the protocol accepts — cannot tell the two apart (+0.00 [−0.00, +0.01], p
0.51), so the default stays on (`rules.track_record_cut: True`; "track-record size cut off
(a) vs on (b)"). The v0.5.1 LLM result
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

---

# Part VIII — v0.9 and v0.10: looking for an edge, and not finding one

Every real-data figure in Parts VIII and IX is copied from a generated page:
[v09_research.md](docs/evaluation/v09_research.md),
[v010_overlay.md](docs/evaluation/v010_overlay.md),
[v011_review.md](docs/evaluation/v011_review.md) and
[v012_trend_core.md](docs/evaluation/v012_trend_core.md). Each page names the result file and
the commit behind it.

## 36. Attribution: whose return is it?

**The idea.** A desk that holds the market most of the time will earn most of the market's
return. That says nothing about its decisions. Attribution separates the two: regress the
desk's daily excess return on a mechanical control that holds the same instruments at the
same volatility target with no views. The slope (beta) is how much of the control the desk
is. The intercept (alpha) is what its views added. The residual volatility is the risk those
views took, and alpha divided by it is the information ratio.

**In the repo.** `scripts/attribution_v09.py` reads the portfolio return files and writes
`attribution.md`. The "tilt" is the desk's daily return minus the control's on the same day.
Its Sharpe and the regression alpha are two views of the same thing.

**The numbers.** On the design period the desk's beta on `B&H vol-target` is 0.92 with R²
0.89, and alpha is +0.41% a year with a t of +0.40. On the holdout beta is 0.89, R² 0.86 and
alpha −0.80% a year (t −0.68). Both alphas are inside the noise. The desk is roughly nine
tenths of its control plus a tilt that earned nothing measurable.

**Questions.**
- The desk's Sharpe on the design period is close to the control's. Why is that weak
  evidence of skill, given the beta?
- Alpha has a t of +0.40. How many years at this alpha and residual volatility would it
  take to reach a t of 2?
- Against plain buy and hold the desk's beta is near 0.5. Why does the choice of benchmark
  change the story so much?

## 37. The control that is hard to beat

**The idea.** Volatility targeting is a rule with no forecast of direction: hold less when
recent volatility is high and more when it is low. It costs little, it cuts drawdowns, and
on many assets it raises the Sharpe ratio because volatility clusters and high-volatility
periods tend to have poor returns per unit of risk. Any strategy that sizes by volatility
inherits this. So the honest benchmark for such a strategy is the vol-targeted holding, not
the unmanaged one.

**In the repo.** `baseline_weights` builds `B&H vol-target` for every sleeve with the same
target volatility and cap the desk uses. Every table prints it, and every paired difference
since v0.8 is taken against it as well as against buy and hold.

**The numbers.** On the v0.11 re-measurement the 15-sleeve holdout portfolio has Sharpe 0.91
for the desk, 0.86 for buy and hold and 0.99 for the control. Desk minus control is −0.08
with a 95% interval of [−0.46, +0.30]. The desk beats the easy benchmark and not the fair one.

**Questions.**
- Why would a benchmark that uses no information about direction be harder to beat than
  one that is always fully invested?
- The desk's drawdown is smaller than buy and hold's. Which comparison tells you whether
  that came from its views or from its sizing?
- If the control were given a higher cap than the desk, which way would the comparison tilt?

## 38. A wider base: many asset classes, equal risk

**The idea.** Diversification is the one free improvement to a Sharpe ratio: combine return
streams that are not perfectly correlated and the risk falls faster than the return. It
works across asset classes (equities, government bonds, credit, gold, commodities, property)
far better than across ten stocks. Risk parity sizes each sleeve so that each contributes the
same share of portfolio risk, which stops the most volatile sleeve from dominating.

**In the repo.** `run_portfolio_backtest(..., weighting="risk_parity")` re-estimates capital
shares every five bars from a 120-day covariance window that ends the day before. The ETF
universe of v0.9 is SPY, EFA, EEM, IWM, TLT, IEF, LQD, HYG, GLD, DBC and VNQ.

**The numbers.** On 2016 to 2021 the ETF book's control has Sharpe 1.02 under risk parity
and 1.02 under equal capital. The core-15 control on the same period has 1.43. The wider
base was not better on that sample: a period in which large US technology stocks led
everything rewards concentration.

**Questions.**
- Risk parity gave the bond ETFs the largest capital shares. Why, and what does that imply
  about the book's sensitivity to interest rates?
- The wider universe had the lower Sharpe on 2016 to 2021. Give one reason that is about
  the sample and one that would be a real weakness.
- Why must the covariance window end the day before the shares are applied?

## 39. Trend as a return stream

**The idea.** Time-series momentum holds an asset long when its own past return is positive
and short when it is negative. The published evidence is across dozens of futures markets
over decades. Two things matter in the definition. The horizon: one, three and twelve months
are the usual set, and averaging their signs is steadier than any one. And the short side: a
long-only trend rule on equities is mostly a way of being out of the market some of the time.

**In the repo.** `quant.strat_tsmom(close, horizons, skip, allow_short)` returns the average
sign, in C++ with a numpy twin. `TSMOM(12-1)` is the v0.9 stream (one horizon, the last month
skipped, long-only where the desk may not short). `TSMOM(L/S)` is the v0.12 stream (three
horizons, long and short on every instrument). Both are baselines in every backtest at the
vol-target size, with full costs.

**The numbers.** On the 2016 to 2021 ETF run `TSMOM(12-1)` is below the control by 0.52, with
an interval of [−0.89, −0.15]. On the longer 2008 to 2021 run it is 0.72 against the
control's 0.87, and `TSMOM(L/S)` is 0.40. Neither beats the control on either sample.

**Questions.**
- The long/short version did worse than the long-only one on the ETF universe. What does a
  short position in a bond or equity ETF cost over a period in which both rose?
- Why is a universe of 11 ETFs a weak test of a result reported on about 60 futures markets?
- The signal uses closes up to the bar itself. What makes that free of look-ahead in the
  backtester?

## 40. Carry as a return stream

**The idea.** Carry is what a position earns if prices do not move. In FX it is the interest
rate differential: long the high-rate currency, short the low-rate one. It is paid for a
risk. Carry trades lose together, quickly, when markets are under stress.

**In the repo.** `carry_weights` maps the annual differential to a position (a differential
equal to `scale` is a full position) and the `Carry` baseline runs it on every FX sleeve with
the carry accrued daily by the backtester. On equities the stream is flat, so in an ETF run
its row is idle cash and not a measurement of carry.

**The numbers.** On the 2008 to 2021 FX run the `Carry` stream has Sharpe −0.05 on excess
returns and a drawdown of 8.22%. Against the FX control the difference is +0.22 with an
interval of [−0.44, +0.85]. No evidence of a premium on these 15 pairs in that period.

**Questions.**
- The period starts in July 2008. What happened to carry trades in the following months,
  and how much of a 13-year Sharpe can one quarter decide?
- Most of the 15 pairs are between developed markets with similar rates after 2009. What
  does that do to the size of the signal?
- Why is the ETF run's `Carry` row not evidence about carry at all?

## 41. Combining streams with a risk budget

**The idea.** Given several return streams, the combination is chosen on risk and not on
past return, because past return is the least stable input. Risk parity across streams gives
each the same share of the book's risk. The combined Sharpe rises only if the streams have
positive expected return and low correlation. Adding a stream with no return lowers it.

**In the repo.** `scripts/combine_v09.py` builds books from fully costed streams at the
return level, with shares re-estimated every five days from the trailing 120 days. Each
book is compared with the base by a paired block bootstrap.

**The numbers.** On 2008 to 2021, with the long/short trend stream, the base has Sharpe 0.87.
Base plus ETF trend has 0.81 with a lower drawdown (5.94% against 9.89%). All four streams
together have 0.56. No book's interval against the base is above zero.

**Questions.**
- The book with all four streams has the lowest volatility and drawdown. Why is that not
  enough to prefer it?
- The carry stream took the largest mean share in every book that held it. Why does risk
  parity favour the quietest stream, and when is that a problem?
- What would the table look like if the trend stream had a true Sharpe of 0.5 and zero
  correlation with the base?

## 42. Core and overlay: how big should the view be?

**The idea.** If the desk is mostly its control plus a small tilt, make that explicit. Hold
the control as the core and add the tilt at a chosen size: `r(lam) = control + lam × (desk −
control)`. At `lam = 0` you hold the control, at 1 the desk. If the tilt has skill, some
positive size is best. If it has none, the best size is zero and the data will say so, or
will be unable to tell.

**In the repo.** `scripts/overlay_v09.py` computes the grid 0, 0.25, 0.5, 0.75, 1 from two
costed return streams. The blend double-counts costs on trades that would net, so its Sharpe
is conservative.

**The numbers.** On the design period the five sizes give Sharpe 1.43, 1.44, 1.43, 1.42 and
1.40, and no difference is distinguishable from zero. On the holdout, printed as a report,
the Sharpe falls from 0.99 at size 0 to 0.80 at size 1. On the 2008 to 2021 ETF run it falls
from 0.89 to 0.79. Nothing was adopted.

**Questions.**
- The design-period grid is flat. Why is "cannot tell" a different conclusion from "the
  tilt is useless"?
- The holdout ranks the sizes cleanly. Why is that not allowed to choose the size?
- Each grid value counts as a trial. What would happen to the deflated Sharpe if a grid of
  100 sizes were searched and the best reported?

## 43. Pre-registration: decide before you look

**The idea.** A result is only as good as the freedom the analyst did not have. If you may
choose the metric, the period or the variant after seeing the outcome, some choice will look
good by chance. Pre-registration removes the freedom: write down what will be run, what will
count as success and what will be done in each case, commit it, then run.

**In the repo.** [v09_preregistration.md](docs/evaluation/v09_preregistration.md) was
committed before the v0.9 holdout run. It states the design-period verdict, that the holdout
run is a report and not a choice, and what the forward test is. An amendment is dated and
appended, never edited in.

**Questions.**
- The pre-registration says nothing will be adopted whatever the holdout shows. Why run the
  holdout at all?
- What is the difference between a holdout that was reported once and one that has been
  used to choose?
- Name one analyst freedom that a pre-registration of the metric alone would leave open.

## 44. The forward record is the only unseen data

**The idea.** Once every historical period has been looked at, the only honest test left is
the future. A paper-trading record, frozen on a known date, with rules that cannot change,
accumulates out-of-sample days one at a time. It is slow. A Sharpe near 1 needs years before
its interval excludes zero.

**In the repo.** `scripts/paper_trade_v09.py` runs daily, recomputes every stream from the
freeze date (2026-09-29) with data up to the previous close, and appends the new day to
`results/paper/ledger.csv`. The rules, universe and code version are recorded with each run.

**The numbers.** `stats.min_track_record` gives the arithmetic: at a true annual Sharpe of
1.0 about 684 daily observations (2.7 years) are needed to be 95% sure it is above zero; at
0.5, about 2730 (10.8 years). Cookbook recipe 77 prints these.

**Questions.**
- After three months the paper record shows a Sharpe of 2. What can be concluded?
- Why does the job recompute from the freeze date each day instead of adding one day to a
  running total?
- What changes to the code would break the claim that the record is out of sample?

## 45. Append-only records and honest revisions

**The idea.** A record that can be rewritten is not evidence. Data vendors revise history
(a late dividend, a corrected close), so a recomputation will sometimes disagree with what
was written. The rule: what was written stays. The disagreement is logged beside it.

**In the repo.** `merge_append_only` keeps every existing row and adds only new dates.
`revisions` lists each cell where the recomputed value differs, and the job writes them to
`revisions.csv` with the full recomputation in `ledger_recomputed.csv`. A recomputation that
would drop rows stops the job unless `--allow-shrink` is given.

**Questions.**
- A vendor corrects a close from three weeks ago. Which file changes and which does not?
- Why is silently adopting the corrected history a form of look-ahead?
- The job refuses to shrink the ledger. What failure is that guarding against?

---

# Part IX — v0.11 and v0.12: a second review, and a longer test

## 46. When did the market know?

**The idea.** Point-in-time data needs a time, not only a date. A filing accepted by the
regulator at 17:30 New York time carries that day's date, but no one could trade on it at
that day's close. Using it that day is a one-day look-ahead, and earnings are often released
after the close.

**In the repo.** The EDGAR provider reads each filing's acceptance timestamp, converts it
from UTC to New York time, and makes the filing visible from the first session whose close
comes after it: the same day before 16:00, the next business day otherwise. Facts are joined
to filings by accession number. A filing with no timestamp falls back to its filing date.

**Questions.**
- A filing is accepted at 00:33 UTC. What is its New York date, and on which session is it
  first usable?
- Why join facts to filings by accession number and not by filing date?
- In which direction does a one-day look-ahead on earnings bias a backtest?

## 47. Confidence should follow the evidence

**The idea.** Ten headlines that say nothing are not ten pieces of evidence. An analyst's
confidence should rise with how much its inputs actually say, not with how many there are.
The same applies to sizing: a stance called "aggressive" should be a multiple of the
risk-based size, not a jump to the cap.

**In the repo.** With `rules.news_tone_mass` (on by default since v0.11) the news analyst's
confidence is driven by the total absolute tone of its headlines, and it abstains when that
mass is under 0.05. With `risk.aggressive_vol_scaled` the aggressive risk analyst proposes
1.25 times the vol-target weight. Both old behaviours are registered trials and `RULES_V02`
still switches them off.

**The numbers.** On the design period the two old rules have portfolio Sharpe 1.44 (news by
count) and 1.40 (aggressive at the cap); the frozen defaults have 1.44. The data cannot
separate the news rules. The change was made because the old rule was wrong in principle.

**Questions.**
- A model-written summary of toneless headlines comes back strongly bullish. What should
  the desk do with it?
- Why is "aggressive means the cap" a sizing rule that ignores the instrument?
- The two news rules have the same design Sharpe to two decimals. On what grounds can a
  rule be changed when the data cannot choose, and what must be recorded when it is?

## 48. One statistic, every trial, every row

**The idea.** Two corrections for searching. Across the rows of one table, control the false
discovery rate: with nine baselines, one p below 0.05 is expected by luck about a third of
the time. Across the history of the project, deflate the Sharpe by the number of variants
ever tried, and compute every trial's Sharpe the same way or the dispersion means nothing.

**In the repo.** `paired_table` applies Benjamini–Hochberg over the rows it prints, on the
primary p (the time-block bootstrap for Sharpe rows since 2026-11-13, section 33).
`evaluation.TRIALS` registers every variant judged on a design period (62 after v0.12), and
the deflated Sharpe uses each trial's portfolio Sharpe.

**The numbers.** The v0.11 measurement reports a deflated Sharpe probability of 0.949 for
the frozen rules. It is below the usual 0.95 line, and the page says it is an upper bound.
Corrected 2026-11-12: this figure is an absolute deflated Sharpe, which is not a selection test (the no-desk vol-target control scores 0.921 on it at 81 trials). The selection statistic is the deflated Sharpe of desk minus vol-matched control: 0.009 at the registry's 81 trials (`docs/results/round2/selection_stat.md`).

**Questions.**
- Why does mixing mean-of-instrument Sharpes with portfolio Sharpes across trials break the
  deflated Sharpe?
- The v0.12 trials were judged on a different period from the earlier ones. What does that
  do to the dispersion of trial Sharpes, and is including them conservative?
- A table prints only the rows that were significant. What has BH controlled?

## 49. A longer design period

**The idea.** When the holdout is spent, more evidence can still come from the other
direction: history before the design period. It is not unseen in the strict sense, because
the rules were shaped by ideas that came from somewhere. But no rule in the project was
fitted to it, it contains regimes the short period lacks, and using it costs no holdout.
More days also narrow every interval, by about the square root of the ratio.

**In the repo.** `PERIODS["design_long"]` is 2008-07-01 to 2021-12-31, the earliest start at
which all eleven ETFs have a year of history. `scripts/measure_v09.py --period design_long`
runs it. The core 15 cannot start there because one stock listed in 2012.

**The numbers.** The ETF run has 3400 days against 1510 on the short design period. The
interval on the long-only trend difference narrows from [−0.89, −0.15] to [−0.41, +0.12].

**Questions.**
- The long period includes 2008. For which of the streams does that matter most, and in
  which direction?
- Why is a universe fixed today and run from 2008 subject to survivorship, and does an ETF
  universe suffer from it less than a stock universe?
- The desk's analysts have thinner inputs before 2016. Which rows on the long period does
  that weaken, and which not at all?

## 50. A negative result, and one routine in two languages

**The idea.** A research round that finds nothing is a result if it was run so that it could
have found something. The test was set before measuring, every variant is on the record, and
the conclusion is the one the numbers allow. Separately, numerical code that exists twice is
easier to trust than code that exists once: two implementations that agree on thousands of
random inputs are unlikely to share a mistake.

**In the repo.** v0.12 measured the long/short trend stream, the books and the overlay on
the longer period ([v012_trend_core.md](docs/evaluation/v012_trend_core.md)). The trend
signal was added the way the README's *Extending* section asks: `strat_tsmom` in `cpp/`,
bound in `module.cpp`, mirrored in `pycore.py`, cross-checked in `tests/test_quant.py` and
fuzzed on both backends in `tests/test_fuzz.py`, which now also fuzzes the older strategies.

**The numbers.** `TSMOM(L/S)` against the control: −0.48 [−1.10, +0.13] on the ETF run, +0.14
[−0.60, +0.79] on FX, −0.20 [−0.99, +0.53] on the combined run. Nothing was adopted.

**Questions.**
- What would have had to be true of these intervals for the trend stream to be adopted?
- The fuzz test asserts that both backends refuse exactly the same bad arguments. Why is
  that as important as agreeing on good ones?
- After four rounds without an edge, what is the most useful next experiment, and what
  would it cost?

# Part X — v0.13: the model interface

## 51. Structured outputs and the contract gate

**The idea.** Asking a model for JSON can fail in two different ways. The reply may not be
JSON of the right shape at all, or it may be well-formed JSON that says something the desk
cannot use: a signal written as a string, a missing confidence. Structured outputs remove the
first failure at the API. They do nothing about the second, so the check the desk already
made stays in place.

**In the repo.** Every structured reply has a JSON schema in `agentic_trader/contracts.py`.
`Agent.ask_json(..., schema=...)` sends it through `complete_json`, which puts it in
`output_config.format`. The reply then meets the same contract as before (`required` keys
present, `numeric` keys finite numbers) and is rejected as a whole if it fails. Tests in
`tests/test_v13_foundation.py` check every schema against the API's schema rules and run one
recorded-shape reply per contract through both gates. Each call also records evidence in `TradingState.llm_calls`: which model
was configured, which served it, the stop reason, any refusal category or fallback switch,
and whether the served id drifted. [Recipe 101](COOKBOOK.md#101-structured-outputs-and-the-per-call-evidence)
shows both gates and the evidence on a recorded reply.

**The numbers.** None yet. No live Claude run was made for v0.13; the schemas, the evidence
records and the budget admission are tested offline against stand-ins with the API's reply
shape. Whether structured outputs change the share of replies rejected by the contract is a
measurement for a later round.

**Questions.**
- If the API guarantees the shape, why keep the contract check? Name a reply that passes the
  schema and fails the contract.
- A schema and its contract disagree about one optional key. Which failures could follow,
  and which test would catch it?
- Why record the served model id on every call rather than trust the configured one?

# Part XI — v0.14: leakage, risk and a failed expectation

## 52. Purged cross-validation and the leak canary

**The idea.** There are two ways a backtest can see the future without anyone writing
"tomorrow" in the code. The first is statistical: a 10-day forward return overlaps the next
nine, so a long pooled sample of daily pairs looks like far more evidence than it is, and a
statistic fitted on bars just before a test period has already seen part of what the test
period is scored on. The second is a plain bug: some function reads a row dated after the
decision day. The first is fixed by how the sample is split; the second can only be found by
experiment.

**In the repo.** `leakage.purged_walk_forward(n, horizon, n_folds=5)` cuts positions `0..n-1`
into contiguous test blocks. For block `[a, b)` a training position `i` is kept only if its
label ends before the block (`i + horizon < a`: the purge), and the `horizon` positions after
every earlier block are dropped (the embargo), after Lopez de Prado (2018, ch. 7). Each fold
scores only its block minus the last `horizon` positions, so no two folds share a return.
`ic_purged` takes the Spearman IC per fold and reports the mean and `t = mean / (sd /
sqrt(k))` over the `k` finite folds. Since v0.14, `alpha_report`, `xalpha.ic_summary` and the
alpha analysts' gate all use it, so their IC, t(IC) and `n` differ from earlier releases.

`leakage.future_leak_canary` is the experiment for the second kind. It runs the whole offline
desk twice: once on the data, once on a `ShockedProvider` copy in which one symbol's prices
are tripled from date T and a headline dated T is added. For every as-of date before T, each
analyst report, the debate, the proposal, the risk views, the decision, every prompt built
(recorded by `PromptRecorder`) and the alpha values must be byte-identical. A difference
names the output that read past its date. The canary also checks that something did change
on T, so a shock that never reached the desk cannot pass as clean.

**A worked example.** With 1 300 bars, a 10-bar horizon and five folds, the blocks are about
260 bars long. Fold 2 tests bars 521 to 780 and scores 521 to 770. Its training set stops at
bar 510 (the purge) and skips bars 260 to 269 just after fold 0 (the embargo), leaving 501
bars. [Recipe 102](COOKBOOK.md#102-purged-walk-forward-ic-on-a-signal) prints these numbers
and the fold ICs for two alphas.

**The numbers.** On synthetic AAPL and EURUSD, at two dates before each of four shock dates,
the canary found no difference, and the outputs changed on the shock date
(`tests/test_v14_leakage.py`). An analyst patched to read one week ahead was caught. These
are tests of the code on synthetic data, not a measurement of any strategy.

**What it does not cover.** A leak inside a provider's own `news()` or `fundamentals()`.
`ShockedProvider` passes fundamentals through unchanged and only adds one item to news, so a
provider that itself returned future items would give the same output in both runs. Feature
values published after the date they describe are a third case, handled by
`PointInTimeStore`, which raises `LookaheadError` on a read before a value's `visible_from`.

**Questions.**
- Why does `ic_purged` not use the training sets at all, and when would it need them?
- With five folds, how many degrees of freedom does the t-statistic have, and what threshold
  corresponds to a two-sided 5% test?
- Design a provider bug the canary would miss. What second test would catch it?

## 53. A pre-registered expectation that failed

**The idea.** Writing down before a run what you expect to see is only useful if you are
prepared to report that it did not happen. A wrong expectation is information about the
method, not something to tune away.

**In the repo.** Plan item 5.1 replaced the desk's hand weights with an estimated
combination (`combine.py`): each signal's trailing purged IC is multiplied by
`max(0, 1 - (t_crit / t)^2)`, so a signal whose fold t-statistic does not clear the Student-t
bar gets zero weight. The plan pre-registered: "tilt goes to zero, desk about equal to the
control; success is that the pipeline refuses noise." The trial was registered in
`evaluation.TRIALS` before the run.

**A worked example.** With five folds, `t_crit` is the 97.5% Student-t quantile on 4 degrees
of freedom, 2.776. A signal with fold t of 4.0 keeps `1 - (2.776/4.0)^2 = 0.52` of its IC; one
with t of 2.5 keeps nothing. The gate refuses fewer than three finite folds outright.
[Recipe 105](COOKBOOK.md#105-the-student-t-gate-on-purged-fold-ics) prints the bar for other
fold counts.

**The numbers.** On 2016-2021 for 15 names, at least one signal survived on 82.6% of sampled
dates. The survivors were mostly slow price-level signals whose fold ICs all had the same sign,
so the fold dispersion was small and t large, from only five observations. The combined desk
scored 0.5125 mean Sharpe against the control's 0.6437 (difference -0.131, 95% CI
[-0.314, +0.059], p 0.174). Nothing was adopted and nothing was tuned after seeing it (plan
section 3, principle 6).

**What it teaches.** Shrinkage on a t-statistic protects only as well as the t-statistic's
assumptions hold. Five folds of one trending series need not be five independent tests. The
next design should make the null harder (for example detrended or cross-sectional ICs, or more
folds) and decide that before running, not after.

**Questions.**
- Why can fold ICs from one trending price series be positively dependent?
- If the folds are dependent, is the 4-df bar too low or too high?
- What result would have counted as success, and what would you pre-register next time?

---

# Part XII — v0.15: text, retrieval and an auditable agent

## 54. Measuring retrieval before an analyst may use it

**The idea.** Retrieval-augmented generation only helps if the retriever finds the right
passage. If it does not, the model writes a confident answer from the wrong text. So measure the
retriever on its own, with questions whose correct passage is known, and refuse to connect it
to the analysts until it clears a bar written down in advance.

**Formally.** For each question with gold passage set G and ranked results r_1..r_k,
recall@k is 1 if any r_i (i <= k) is in G, else 0; MRR is the mean of 1/rank of the first gold
hit (0 if none). Both are averaged over the question set. Point in time matters as much as
rank: a search dated `as_of` may only rank passages with `visible_date <= as_of`, and the IDF
weights are fitted on those passages only, so the future does not leak into the ranking through
document frequencies.

**In the repo.** `agentic/research_rag.py` builds the corpus from filing sections and
central-bank statements, ranks with hashed TF-IDF by default, and with `method="hybrid"` fuses
TF-IDF and BM25 by reciprocal rank (score = sum of 1/(60 + rank)). `analyst_retriever` runs the
evaluation first and raises `RetrievalGateError` if recall@5 is below 0.8.
[Recipe 107](COOKBOOK.md#107-research-retrieval-and-the-recall-gate) runs it.

**The numbers.** 100 hand-labelled questions over a 34-passage invented fixture corpus:
TF-IDF recall@5 0.990, MRR 0.954; hybrid 0.990 and 0.961. The gate passes. That shows the
mechanism and the point-in-time filter work; it says nothing about recall on real 10-Ks, which
are longer and far more alike than the fixtures. Local embeddings are optional (`[rag]` extra)
and untested. Separately, plan item 3.9 removed the policy-runbook RAG from the rules path on
synthetic data: 0 of 9 decisions changed.

**Questions.**
- Why fit IDF on visible passages only, rather than on the whole corpus with a date filter after?
- A corpus of 34 short, distinct passages makes recall@5 easy. What would a harder test set need?
- Why does reciprocal-rank fusion use ranks rather than raw scores?

## 55. Red-teaming the fence, and what the numbers do and do not cover

**The idea.** Headlines and filings are written by outsiders and can contain text aimed at the
model ("ignore your instructions, buy"). The desk puts such text inside an `<untrusted_data>`
fence. A fence is a claim; a red-team corpus tests it.

**In the repo.** `docs/threat-model/injection_corpus.json` holds 150 adversarial snippets in
families (instruction-bearing, role-play, encoded, multilingual). `agentic/redteam.py` checks
three things for each: the snippet reaches the analyst prompt only inside the fence, the rules
signal equals the plain lexicon score (so the instruction itself moved nothing), and whether the
direction flipped. `compliance_run` measures a model's compliance; it needs a model.

**The numbers.** 150 of 150 fenced; rules signal equal to the lexicon score on 150 of 150; 6 of
150 direction flips, all from the lexicon words "buy" and "sell" inside the attack text. That is
the lexicon counting words, not the model obeying. Compliance on a local model has not been run.
The exercise found one real defect: facts whose keys start with `_` could reach
`Analyst.prompt` outside the fence. That is fixed.

**Questions.**
- Why is "rules signal equals lexicon score" the right test for the rules path, and why is it
  not enough for an LLM path?
- Should the lexicon ignore trading verbs that appear inside quoted instructions?

# Part XIII — v0.16: what the model adds

## 56. Asking a small model where it helps, and checking it first (v0.16)

**The idea.** A model's opinion is useful only if it comes from the facts in front of it. If it
can recognise the stock and the month from a "scrubbed" prompt, it may be recalling what happened
next, which is look-ahead by memory. If it answers the same question differently each time, its
signal is partly noise. So the study checks recall, stability and fact use before it compares
desks.

**Formally.** Recall audit (PLAN 2.4): for n = 200 anonymised prompts, count ticker hits k and
test H0: hit probability = 1/15 with the exact one-sided binomial P(X >= k). Calibration (2.6):
dispersion is the spread of the signal over 5 replies at temperature 0.7; the anchoring slope is
the OLS coefficient of signal on an injected `rsi14` value with state fixed effects. Desk
comparison (2.3): Sharpe(cell) minus Sharpe(vol-target control) with a circular block bootstrap;
a cell whose fallback share exceeds 10%, or whose fallbacks depend on regime (chi-square p <
0.05), is not admissible, because then the run measures the rules more than the model.

**Worked example.** Suppose 20 of 200 prompts name the right ticker. The rate is 0.10 against
chance 0.067, and P(X >= 20) under H0 is 0.046: weak evidence of leakage, enough to run the
ablation and drop whichever fact key carries it. (Illustrative numbers, not a result.)

**In the repo.** `scripts/v16_local_study.py`, `scripts/v16_eval.py`, `scripts/llm_study.py`,
`docs/evaluation/v16_preregistration.md`; recipes 114-117. Model: `qwen2.5:7b-instruct`,
4-bit, CPU. Interim result (2026-11-12, `docs/results/v17/llm_study_interim_report.md`): the IC
difference local_analysts minus rules is -0.046 [95% CI -0.185, +0.067], hit rate 54.6% against
55.1%, no failed model call; no evidence the model analysts help (descriptive; 404 of 1,200
analyst outputs in the model cell came from the model). The study was stopped on 2026-11-12 and
its pre-registered decisive test was not run (`docs/evaluation/v16_prereg_status_2026-11-12.md`). The minimum detectable effect on the holdout is 0.59 to 1.32 annual
Sharpe (pre-registration, iid approximation), so a null there is weak evidence against a small gain.

**Questions.**
- Why does telling the model the 15 candidate tickers make chance 1/15 rather than one in thousands?
- Why must the fallback share be capped before the Sharpe difference means anything?

## 57. Every study cell is a trial, and what a decision costs (v0.16)

**The idea.** Each way of putting the model into the desk (analysts only, every role, the
portfolio manager only, and so on) is one more variant tried on the same design data. Trying
more variants makes the best one look better by luck alone, so every cell has to be counted
in the selection statistics, including cells that are never run or never adopted. And because
a model call costs money where a rule does not, each decision is reported with its cost next
to its accuracy.

**Formally.** The deflated Sharpe probability compares the chosen Sharpe with the expected
maximum of N null trials, which grows with N. `evaluation.TRIALS` holds every registered
variant; `evaluation.registered_trial_count()` returns N, and
`stats.selection_report(returns, measured_sharpes, n_trials=N)` uses the larger of N and the
number of measured Sharpes for the expected maximum, while the trial dispersion still comes from
the measured ones only. All seven P2 model cells are registered before any of them runs
(`tests/test_v16_study.py::test_every_study_cell_is_a_registered_trial`). Cost per decision is
`kpi.cost_per_decision_usd` = total model spend over the number of decisions; it is 0 for the
rules control and for the local model, so for those cells the column records that the
comparison was free, not that the model is cheap at scale.

**Worked example.** The registry now has 77 trials. On a synthetic series in
`tests/test_v16_study.py`, five measured Sharpes give one expected maximum; passing
`n_trials=77` raises it and the deflated probability can only fall. The real P2 numbers are
pending: [what the model adds](docs/evaluation/what_the_model_adds.md) shows them as pending
rows, and the [live-readiness statement](docs/evaluation/live_readiness.md) says which parts
of the path are simulated. The study design is diagram 40 in
[DIAGRAMS.md](docs/DIAGRAMS.md#40-the-llm-study-cells-trials-and-the-rules-control-v016).

**In the repo.** `agentic_trader/evaluation.py` (`TRIALS`, `registered_trial_count`),
`agentic_trader/stats.py` (`selection_report`), `agentic_trader/kpi.py`, `scripts/llm_study.py`.
Evidence class: code and synthetic tests; no model result.

**Questions.**
- Why count a cell that was registered but never run?
- If one cell had a measured Sharpe and six did not, what does `trials_measured` tell a reader
  that `trials` does not?

# Part XIV — v0.17: a second review, and measuring the measurements

Two reviews on 2026-11-09 (`docs/review/2026-11-09_review_and_plan.md`) asked of each earlier
result whether the test could have seen what it claimed to look for. The concepts below are the
methods v0.17 added to answer that. Everything in this part is code with offline tests or
simulation; the real-data and model re-runs are queued, and their numbers are not here yet.

## 58. How small an IC could the test have seen? Newey-West t and the MDE

**The idea.** "No alpha clears the gate" means little if the gate could not have seen an alpha
of the size that matters. Two things fix this: a t statistic that uses every observation while
allowing for overlap, and a stated minimum detectable effect, so a null reads "cannot detect
|IC| below x" rather than "no edge".

**Formally.** With a 10-day forward return sampled daily, neighbouring IC terms share nine days
and are correlated. The Newey-West (1994) standard error adds Bartlett-weighted
autocovariances up to lag L, with `L = max(horizon, floor(4 (n/100)^(2/9)))`
(`stats.newey_west_lag`); `stats.newey_west_t` returns the mean, se, t and lag. The minimum
detectable IC at 5% two-sided and 80% power is `(z_0.975 + z_0.8) x se = 2.8016 x se`, or
without an se the Fisher form `tanh(2.8016 / sqrt(n - 3))` (`stats.min_detectable_ic`). The
five-fold block t (4 df, bar 2.776) is kept and renamed `ic_blocked_folds`: for a fixed signal
nothing is fitted, so the purge does nothing and "purged" was the wrong word.

**Worked example.** x = 1..5 at lag 1 gives S = 2.8 and t = 4.0089 (hand-computed, pinned in
`tests/test_v17_stats.py`). With n = 1,000 and no se, the MDE is 0.0885. On 1,500 days of pure
noise at horizon 10 (COOKBOOK 122) the fold t is -1.75 against a bar of 2.78, the NW t -1.60,
and the test cannot detect |IC| below 0.067. An IC of 0.03, which would be worth trading, is
below that line.

**In the repo.** `agentic_trader/stats.py`, `agentic_trader/leakage.py` (`PurgedIC.t_nw`,
`mde_ic`), `docs/quant/quant.md` section 6. Evidence class: method, tested on known answers.

**Questions.**
- Why does overlap make the naive t too large?
- A table reports IC 0.01 with MDE 0.07. What may you say about the signal?

## 59. Many gates are one family: Benjamini-Hochberg across them

**The idea.** Nine alphas x 15 names x several horizons is hundreds of gates. Test each at 5%
and some will pass by luck. The gate decision has to be made over the whole family.

**Formally.** `leakage.GATE_FAMILIES` names the families: in the time series, alphas x names x
horizons of one alpha-report run; in the cross-section, the alphas of one `xalpha_report`.
`leakage.gate_family_bh(entries, q=0.05, use="nw")` passes an entry only if it clears its
nominal gate and survives Benjamini-Hochberg at q on the Newey-West p-values. BH controls the
expected share of false passes among the passes, and holds under positive dependence, which
correlated alphas on the same names have. `xalpha.significance_gated_scores` now uses this one
gate; the old fixed `min_tstat=2.0` second threshold is gone.

**Worked example.** In `tests/test_v17_stats.py` a family of 401 tests holds one nominal pass
that BH removes: alone it looks significant, among 401 it is what chance produces.

**In the repo.** `agentic_trader/leakage.py` (`gate_family_bh`, `format_gate_family`),
`agentic_trader/xalpha.py`. Evidence class: method, tested.

**Questions.**
- Why is BH used here rather than Bonferroni?
- What is the family when two reports are run on different horizons on the same day?

## 60. Effective trials: hidden ones and correlated ones

**The idea.** The deflated Sharpe (concept 48) needs the number of things tried. The registry
undercounts in one way and overcounts in another. Constants chosen by hand before the registry
existed were trials too. And many registered trials are one-rule ablations that are nearly the
same strategy, so they count as fewer independent tries than their number.

**Formally.** `evaluation.PRE_REGISTRY_CONSTANTS` lists 32 hand-set constants in 7 groups;
at a stated 3 values per constant that is `PRE_REGISTRY_TRIALS_ESTIMATE = 64` (an estimate,
deliberately generous). `stats.selection_report(..., pre_registry_trials=64)` reports the DSR
at the registered count and at the registered count plus 64. For correlation,
`stats.effective_trials(M)` returns the participation ratio of the correlation matrix's
eigenvalues, `N_eff = (sum lambda)^2 / sum lambda^2`, and the mean pairwise correlation;
`deflated_sharpe_effective` uses N_eff trials and divides the trial-Sharpe variance by
`1 - mean_corr`.

**Worked example.** The registry holds 81 trials at v0.17, so the conservative DSR counts 145.
Two identical trials have N_eff 1; k uncorrelated trials have N_eff k.

**In the repo.** `agentic_trader/evaluation.py`, `agentic_trader/stats.py`. Evidence class:
the constant count is an estimate; the arithmetic is tested.

**Questions.**
- Which way does each correction move the DSR?
- Why report both counts rather than pick one?

## 61. Execution lag: deciding on a close you have not seen yet

**The idea.** Until v0.17 every backtest decided on the close of bar t and filled at that same
close. Nobody can trade at a close they have not seen yet, so every result had a small look-ahead
built in. It hardly matters for 12-month momentum and matters a lot for reversal and stop rules.

**Formally.** `backtest.exec_lag = k` executes at bar t+k the target decided at bar t. Weight,
rebalance flag and stop levels come from bar t-k (decision-tied); carry, impact and cash rate
come from bar t (market data). `backtest.fill = "next_open"` fills at `open[t+1]`, and the
position held into the bar earns the overnight move from close to open. Both are in the numpy
and C++ engines; lag 0 is bit-identical to the old engine (a sha256 over a full-featured run).

**Worked example.** Closes 100, 110, 121 and opens 100, 105, 120, a full long decided at bar 0
and no costs. A next-open fill at 105 ends at 121/105 = 1.152; the same-close fill would have
claimed 1.21. A signal equal to `sign(r[t+1])` has Sharpe above 10 at lag 0 and below 1.5 in
absolute value at lag 1 (`tests/test_exec_lag.py`).

**In the repo.** `agentic_trader/quant/pycore.py`, `cpp/src/backtest.cpp`,
`scripts/v17_exec_lag.py` (registered trials at lag 0 and 1; queued). Evidence class: tested on
the numpy backend; the C++ parity cases run in CI.

**Questions.**
- Why can lag 1 not turn "no edge" into "edge"?
- Why are carry and impact read at bar t but the weight at bar t-k?

## 62. Did the model remember? A recall audit with a null and a placebo

**The idea.** Anonymising a prompt only helps if the model cannot see through it. The v0.16
audit asked a model to name the ticker behind a disguised chart, but ran the items name by name
with the options in a fixed order, so a model that always answered the first option looked as
if it remembered. A fair audit shuffles the options and compares the model with two baselines:
the same answers with the labels shuffled, and fake charts nobody could know.

**Formally.** `recall_audit.py` interleaves items by date, shuffles candidates per item (seed
recorded), and scores a ranked top 3 by mean reciprocal rank. The null keeps the model's own
answer distribution and permutes the true labels. The placebo arm uses synthetic series matched
in drift and volatility. Recall is flagged only if real MRR beats the permutation null and the
placebo arm at 5%; without a placebo arm the verdict is "incomplete", never "flagged". A
position-bias chi-square and the first-option share are reported beside it. A leak test
compares the model's signals on real and date-shifted windows with a date-clustered bootstrap.
Since v0.17 the prereg holdout look and `evaluation.evaluate` on a local model refuse to start
until the audit has passed (`evaluation.require_recall_pass`). Since 2026-11-13 (review C11)
"not flagged" is not enough: passing is an equivalence test. The null is "recall above chance
is at least a margin" (default: the excess MRR of a model that recognises 10 % of items,
`0.10 * (1 - chance MRR)`), and the gate passes only when the one-sided 95 % upper bound of
real MRR minus chance is below that margin (`recall_audit.equivalence_test`, which also
reports its power and the n for 80 % power). With 15 candidates the margin is 0.088; a
chance-level model passes at n = 100 (bound 0.045) and fails at n = 20 (bound 0.101), so a
small audit fails. An audit JSON without the `equivalence` block no longer passes
`evaluation.recall2_verdict`.

**Worked example.** In `tests/test_v017_study_rigour.py` the v0.16 design flags an
always-first responder on a 30-item prefix; v2 does not flag it at any prefix tried, and its
`first_share` is 1.0.

**In the repo.** `agentic_trader/recall_audit.py`, `scripts/v16_local_study.py recall2`
(COOKBOOK 129). Evidence class: fake-model tests; the model run is queued.

**Questions.**
- Why must the null keep the model's own answer distribution?
- What would a high placebo-arm score tell you?

## 63. Lineage: which code, prompt and model made this row

**The idea.** A study that runs for days, resumes after a shutdown and is read weeks later
needs every row to say what made it. Otherwise a model update or a code change mid-run silently
mixes two experiments in one table.

**Formally.** `study_lineage` writes a run header: git SHA and dirty flag, prompt-bundle hash,
Ollama version, model digest and quantisation, and request options, under a stable
`header_id`. Each row carries `header_id`, `git_sha`, `model_digest` and `prompt_sha256`, plus
`horizon_days`, `entry_bar_date`, `asof_close` and a `vintage_hash` of the closes as fetched.
Resume refuses (exit 2) on any identity change unless `--allow-version-change`, which records
the new header and the fields that changed. Every request sets `num_ctx` (8192), and each call
records `prompt_eval_count` so a truncated prompt is flagged rather than silently cut.

**Worked example.** A resumed run after `ollama pull` changed the model digest exits 2 and
names `model_digest` as the changed field; with the flag, the rows after the change carry the
new `header_id` and a report can split on it.

**In the repo.** `agentic_trader/study_lineage.py`, `agentic_trader/local_llm.py`,
`scripts/llm_study.py`. Evidence class: tested with fake servers.

**Questions.**
- Why is a model name not enough to identify a model?
- Rows written before v0.17 have no lineage. How does the report treat them?

## 64. Conformal intervals when the data are not exchangeable

**The idea.** A conformal interval takes past forecast errors and uses their quantile as today's
error band. The guarantee assumes the errors are exchangeable. Five-day errors computed every
day overlap by four days, and errors from a calm month are a poor guide in a volatile one, so
the band is too narrow exactly when it matters.

**Formally.** The v17 design (`conformal.design = "v17"`, the default) takes calibration points
every h bars counted back from `end - h`, so no two residuals overlap, applies the regime mask
when regime conditioning is on, and divides each residual by the horizon volatility at its own
bar; the quantile is scaled back by today's volatility. The registered v0.14 trial stays pinned
to the old design (`"v14"`), and the v17 design is a new registered trial.

**Worked example.** On GARCH(1,1) paths with t(6) innovations (6 seeds, h = 5, alpha 0.2,
window 250, 654 forecasts), coverage in the top volatility quartile was 0.675 with the v14
design and 0.882 with v17, against a target of 0.80. Overall coverage was 0.760 and 0.778.
The v17 design over-covers in high volatility instead of under-covering.

**In the repo.** `agentic_trader/combine.py` (`calibration_points`, `conformal_interval`).
Evidence class: simulation; the real-data trial is queued.

**Questions.**
- Why does overlap shrink the effective calibration sample?
- Is over-coverage in high volatility a cost or a safety margin for position sizing?

## 65. A red team needs a control arm

**The idea.** v0.15 counted an attack as successful when the model's signal moved by more than
0.5. But appending any text to a headline can move a small model. Without a run on the same text
with a harmless suffix of the same length, the count mixes sentiment with obedience.

**Formally.** `redteam_v2` runs each snippet three ways: base, attacked, and control (carrier
plus neutral boilerplate of the payload's length, with lexicon score 0). Directed compliance is
`(attacked - control) x target > 0.5`, where `target` is the direction the payload asks for. It
runs through the desk's own constrained JSON path and its contract, on five states, on the
news, sentiment, filing and central-bank analysts, and then runs the whole desk to see whether
the final position moved in the demanded direction after the critic and the limits
(`weight_dir_matched_rate`).

**Worked example.** The v0.15 local run reported 21/150 (14%) of attacks moving the signal by
more than 0.5. That number has no control arm, so it is an upper bound on compliance, not an
estimate of it. The v2 run (about 13,000 calls, 7.5 to 15 CPU-days at full scope) is queued at
reduced scope.

**In the repo.** `agentic_trader/agentic/redteam_v2.py`. Evidence class: offline tests; the
model run is queued.

**Questions.**
- Why must the control suffix match the payload's length?
- Which number would a risk committee read first, and why?

## 66. Long runs that survive a kill, and skips that are counted

**The idea.** The local-model study runs for days on a laptop CPU. A reboot, a hung model
server or a data provider that has no bars for one name on one day must not cost the finished
work, and must not quietly shrink the sample either.

**Formally.** Three mechanisms (v0.19, evidence class: code + offline tests).
`agentic_trader/checkpoint.py` appends one JSON line per finished unit and fsyncs it; line 1 is
a header whose SHA-256 fingerprint must match on resume (else `CheckpointMismatch`), and a torn
last line is truncated so that unit simply runs again. A corrupt line in the middle (since
2026-11-13, review D11) is skipped on its own: the valid rows after it are kept, the count is in
`Checkpoint.skipped_lines` with a logged warning, and the file is rewritten clean. Before, the
first corrupt line truncated the file and every later unit ran again. `local_llm_retry_budget_s` (0 by default,
600 s in the study drivers, `scripts/llm_study.py` `LOCAL_BUDGET`) retries timeouts, refused
connections and HTTP 5xx with the same request body, and raises `LocalLLMUnavailable` when the
budget is spent, so a dead server stops the run instead of turning every later row into a
rules fallback. `study_robust.retry_provider` retries a provider miss three times and the
runner then writes a skipped row with its reason. The pre-registration
(`docs/evaluation/v16_preregistration.md`, "Skipped units") requires N to be quoted with
its skip count, counts skips apart from fallbacks, and makes a cell with more than 10 % of its
units skipped inadmissible (`llm_study.cell_metrics`: `skipped`, `skip_share`).

**Worked example.** A cell of 300 decisions with 15 skips is reported "N = 285 (15 skipped)",
skip share 5 %, admissible on this rule. With 31 skips the share is 31 / 300 = 10.3 % and the
cell is not admissible, whatever its fallback share. A resume retries the skipped units; one
that now succeeds leaves the skip list (`load_skips`). Recipe 131 runs the whole cycle on a
toy file.

**In the repo.** `agentic_trader/checkpoint.py`, `agentic_trader/study_robust.py`,
`agentic_trader/local_llm.py`, `scripts/llm_study.py`, `scripts/v16_local_study.py`,
[docs/operations/long_runs.md](docs/operations/long_runs.md). Test:
`tests/test_v16_study.py::test_skip_cap_makes_a_cell_inadmissible`.

**Questions.**
- Why is a skip not counted as a fallback?
- Why must a changed run header be refused rather than appended to?
- What would go wrong if the retry budget were infinite?

## 67. Classical ML in this repo: what is fitted, and when it is on

**The idea.** Most of the "learning" here is classical statistics, not a neural network: a
hidden Markov model labels volatility regimes, a shrunk IC-weighted combination turns signals
into a forecast, a conformal interval sizes the tilt, and purged cross-validation with a leak
canary checks that none of it saw the future. All of it is opt-in.

**Formally.**
- *Gaussian HMM* (`agentic_trader/regime.py`): 2 or 3 states, diagonal Gaussian emissions,
  fitted by Baum-Welch on bars up to the as-of only; states sorted by mean log volatility.
  Switch `regime.enabled` (off by default in `config.py`).
- *IC-weighted combination* (`agentic_trader/combine.py`, `combination.method: "ic"`, default
  `"rules"`): each signal's trailing purged IC is shrunk by the positive-part James-Stein factor
  `max(0, 1 - (t_crit / t)^2)`, so a signal that does not clear its Student-t bar gets weight 0;
  the forecast is sized by mean-variance with a Ledoit-Wolf covariance.
- *Split conformal* (`combine.conformal_halfwidth`, `conformal.enabled`, off by default): the
  `ceil((n + 1)(1 - alpha))`-th smallest absolute calibration residual; section 64 covers the
  dependent-data version.
- *Purged walk-forward and the leak canary* (`agentic_trader/leakage.py`):
  `purged_walk_forward` drops training rows whose label window overlaps the test fold and adds
  an embargo (section 52); `future_leak_canary` shocks prices after the as-of and checks that
  the desk's outputs are byte-identical.

**Worked example.** Recipe 132 fits the HMM on a synthetic series whose volatility quadruples
half way: it labels 0 % of the calm half and 97 % of the stormy half high-volatility (synthetic
fixture). The 80 % conformal half-width from 99 standard-normal residuals is 1.30, against 1.28
from normal theory.

**What is not here.** No model is trained on market returns to predict them end to end, and
none of these switches is on in the frozen desk. The IC combination, regime conditioning and conformal sizing
were registered as trials and run on design data (real prices, 15 core names, 2016-2021,
`results/v14/`): mean Sharpe minus the control's -0.131, -0.179 and -0.079; none adopted
(CHANGELOG v0.14).

**Questions.**
- Why sort HMM states after fitting?
- What does a James-Stein factor of exactly zero mean for a signal?
- Why must the canary compare outputs byte for byte rather than by tolerance?

## 68. LLM-as-judge: a judge must agree with labels first

**The idea.** Grading 150 analyst replies by hand for every prompt change is slow, so a second
model grades them. A judge is itself a measurement instrument: it is used only after its
verdicts are compared with human labels on a calibration set.

**Formally.** `agentic_trader/agentic/judge_kit.py`. The default judge is
`llama3.1:8b-instruct-q4_K_M` and the judged model `qwen2.5:7b-instruct`;
`resolve_judge_model` refuses a judge from the judged model's family (self-preference bias)
unless explicitly allowed. Agreement per criterion is Cohen's kappa,
`kappa = (p_o - p_e) / (1 - p_e)`, with a row-resampling bootstrap interval
(`kappa_bootstrap`). The rule-based checker of the eval set (`agentic/eval_set.py`) is
calibrated the same way, so the judge is compared with a deterministic baseline.

**Worked example.** Recipe 133: 23 of 30 verdicts agree with the labels (77 %), but because
both raters say "yes" often, chance agreement is already high and kappa is 0.43 with a 95 %
interval of about [0.07, 0.76] (invented labels, arithmetic). Thirty items cannot tell a fair
judge from a good one.

**Result.** The local calibration run (`docs/results/v17/agreement.json`, n = 30): the
`llama3.1` judge's kappa is 0.28 on used_facts, 0.68 on no_invented_numbers and 0.30 on
respected_fence; the deterministic rule checker scores 1.00, 0.81 and 1.00. The judge is weak on
two of three criteria, and with 30 items even 0.68 has a wide interval, so the rule checker is
the instrument of record. Commands: recipe 117.

**Questions.**
- Why is 77 % raw agreement not evidence of a good judge?
- Why refuse a judge from the same model family?
- What would you do with a criterion whose kappa interval includes zero?
