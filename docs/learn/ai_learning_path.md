# AI learning path

Ten modules on the kinds of AI this project really uses, in the order they build on each
other. Each module has the same six parts: plain idea, formal statement, a worked example from
this repository, an offline exercise, pitfalls, and three self-check questions with answers.
The deeper explanations live in [LEARN.md](../../LEARN.md); this path links to them rather
than repeating them. Every exercise is a [COOKBOOK](../../COOKBOOK.md) recipe that runs offline
and is executed in CI (`python scripts/run_cookbook.py --offline`).

Evidence classes used below: **code** (what the source does), **offline test**, **synthetic
fixture** (numbers that say nothing about markets), **arithmetic**, **measured** (a real run,
with its file), **planning estimate**.

This is one track of a series. The modules titled LLMs, Agents and the harness, Guardrails,
RAG, Classical ML, Honest AI evaluation and Local models share their titles and headings with
the matching track of the sibling project AgenticAICashEquities
([lesson index](https://github.com/AshJha0/AgenticAICashEquities/blob/main/docs/learn/ai/README.md),
being published at the time of writing). The other three modules are specific to this repo.

1. [Agents and the harness](#1-agents-and-the-harness)
2. [LLMs](#2-llms)
3. [Local models](#3-local-models)
4. [Structured outputs and the contract gate](#4-structured-outputs-and-the-contract-gate)
5. [Guardrails](#5-guardrails)
6. [Tools and MCP](#6-tools-and-mcp)
7. [RAG](#7-rag)
8. [Memory and reflection](#8-memory-and-reflection)
9. [Classical ML](#9-classical-ml)
10. [Honest AI evaluation](#10-honest-ai-evaluation)

---

## 1. Agents and the harness

### Plain idea

A decision is split across specialists, the way a desk splits it: analysts write reports, a
bull and a bear argue, a trader sizes, a risk team challenges the size, a portfolio manager
decides. None of them runs the loop. A harness owns the order of steps, and every step is a
state transition it records.

### Formal statement

Each agent follows one pattern (`agentic_trader/agents/base.py`): gather facts with tools,
compute a rules answer, and only then, if a model is configured and within budget, ask the
model; a reply that fails the contract leaves the rules answer in place. The harness
(`agentic_trader/agentic/harness.py`) drives a task through the states in
`agentic/domain.py` (`TRANSITIONS`; terminal states COMPLETED, FAILED, CANCELLED), with a plan
validated before it runs (`agentic/planner.py`) and a critic after it (`agentic/critic.py`).
See LEARN sections [1](../../LEARN.md#1-why-a-desk-of-specialist-agents) and
[13](../../LEARN.md#13-the-harness-a-state-machine-owns-the-loop).

### Worked example from this repo

The portfolio manager blends the three risk views 25 % aggressive, 50 % neutral, 25 %
conservative (`agents/risk.py`, `PortfolioManager.stance_weights`). Views of +0.80, +0.50 and
+0.20 give 0.25 x 0.80 + 0.5 x 0.50 + 0.25 x 0.20 = +0.50 of capital (arithmetic). That is the
rules answer the model may replace, and the firm limits are applied to whichever answer wins.

### Offline exercise

COOKBOOK [1. Get one decision](../../COOKBOOK.md#1-get-one-decision) and
[2. Read the full audit trail](../../COOKBOOK.md#2-read-the-full-audit-trail): run a decision
with no model and find, in the trail, which agent produced each number.

### Pitfalls

- Letting an agent call the next agent: the loop then has no single owner and no record.
- Treating the debate as evidence; it is a structured summary of the same facts.
- Forgetting that with no model every agent still answers (rules), so "the AI decided" is
  often false; read each output's `source`.

### Self-check (with answers)

1. *What happens when the model is off?* Every agent returns its rules answer; the desk runs
   end to end with no model call.
2. *Who decides the next step?* The harness, from its transition table; agents never control
   the loop.
3. *Where do the firm limits apply?* In `PortfolioManager.guardrails`, after the PM's (rules or
   model) weight is chosen.

Same concept, another desk: [AgenticAICashEquities AI track](https://github.com/AshJha0/AgenticAICashEquities/blob/main/docs/learn/ai/README.md) (matching lesson coming).

---

## 2. LLMs

### Plain idea

The language model writes judgement and narrative from facts it is handed. It never computes a
metric, never invents an evidence id and never places an order.

### Formal statement

A model call is `complete(system, prompt)` or `complete_json(system, prompt, schema)` behind
the `LLM` protocol (`agentic_trader/llm.py`; `local_llm.py` for Ollama). Prompts are scrubbed of
names and dates on the way out when anonymisation is on, and names restored on the way back
(`Agent._complete`); `llm_anonymize` is forced on whenever a model is used (v0.17). Calls are
capped in number and dollars (`BudgetedLLM`). See LEARN
[7](../../LEARN.md#7-where-the-llm-sits-and-where-it-does-not).

### Worked example from this repo

The one measured Claude run (v0.5.1, five stocks, one quarter, 271 calls, $4, pre-v0.8
engine): the same Sharpe as the rules with less than half the exposure (measured; one quarter
shows behaviour, not edge). Nothing a model produced has been adopted since
([what the model adds](../evaluation/what_the_model_adds.md)).

### Offline exercise

COOKBOOK [17. Count LLM calls](../../COOKBOOK.md#17-count-llm-calls) and
[18. Plug in your own model](../../COOKBOOK.md#18-plug-in-your-own-model): plug in a fake model
and watch which agents call it.

### Pitfalls

- Asking the model for a number the code can compute.
- Comparing a model run to buy and hold instead of to the rules desk on the same states.
- Forgetting that a model may recognise the company from the series (module 10).

### Self-check (with answers)

1. *Why anonymise?* So the model reasons from the facts rather than from memory of the company.
2. *What does the call cap protect against?* A runaway loop spending money or CPU-days.
3. *What is the control for "the model helps"?* The rules cell on the same names and dates.

Same concept, another desk: [AgenticAICashEquities AI track](https://github.com/AshJha0/AgenticAICashEquities/blob/main/docs/learn/ai/README.md) (matching lesson coming).

---

## 3. Local models

### Plain idea

Asking Claude across a full study design was estimated at about $215 per cell at list prices,
so the study runs at $0 on an open-weight 7-8B model served by Ollama on this machine's CPU.
Slow and small, but free and private; the results describe that model class only.

### Formal statement

`agentic_trader/local_llm.py` talks to Ollama on 127.0.0.1 (a non-loopback URL is refused
unless explicitly allowed) and uses JSON-schema constrained decoding. The study budget
`LOCAL_BUDGET` in `scripts/llm_study.py` is `max_tokens` 384, `local_llm_timeout_s` 300 and
`local_llm_retry_budget_s` 600. A call that still fails falls back to the rules answer and is
counted; `MAX_FALLBACK_SHARE = 0.10` makes a cell inadmissible when more than 10 % of its model
calls fell back or failed the contract. The run header pins the model digest, and
`run_study` re-checks the served digest every `SWAP_CHECK_EVERY = 25` rows (`ModelSwapped`).

### Worked example from this repo

`SECONDS_PER_CALL = (50, 100)` is the planning range on this machine (planning estimate). The
`decisive_ta` cell is 4,695 calls, so 65 to 130 CPU hours, 2.7 to 5.4 days
(`docs/review/v017_notes/L10_study_rigour.md`, arithmetic on that estimate). Its dollar cost is
0, and `--report` shows the Claude list-price equivalent per decision beside it. Measured
seconds per call are written per run (`seconds_per_call` in the cell metrics) once a run
finishes.

### Offline exercise

COOKBOOK [131. Resume a killed run and read the skipped block](../../COOKBOOK.md#131-resume-a-killed-run-and-read-the-skipped-block);
then read [114](../../COOKBOOK.md#114-study-driver-dry-run-smoke-first-pass-report) for the
real commands (they need Ollama and are not run in CI).

### Pitfalls

- Reading a cell with 30 % fallbacks as "the model": it is mostly the rules.
- Retrying forever: a hung server must stop the run (`LocalLLMUnavailable`), not hide.
- Mixing rows from two model digests in one file.

### Self-check (with answers)

1. *Why is a fallback-heavy cell inadmissible?* Its numbers describe the rules more than the model.
2. *What does the digest check catch?* A model updated or swapped under the same name mid-run.
3. *Why is a skip not a fallback?* The unit never reached the model (LEARN
   [66](../../LEARN.md#66-long-runs-that-survive-a-kill-and-skips-that-are-counted)).

Same concept, another desk: [AgenticAICashEquities AI track](https://github.com/AshJha0/AgenticAICashEquities/blob/main/docs/learn/ai/README.md) (matching lesson coming).

---

## 4. Structured outputs and the contract gate

### Plain idea

The model must answer in a fixed JSON shape. If the reply is not that shape, or a number is
out of range, the whole reply is rejected and the rules answer stands. Nothing is clipped into
range, because a clipped value would be booked as the model's view.

### Formal statement

Schemas live in `agentic_trader/contracts.py`. `Agent.ask_json` requires the listed keys,
finite JSON numbers for numeric keys, and values inside the schema's `minimum`/`maximum` or
`enum` (`_contract_problem`); any failure returns `None`. See LEARN
[51](../../LEARN.md#51-structured-outputs-and-the-contract-gate).

### Worked example from this repo

A reply `{"signal": 999}` is a contract failure since v0.17 (it used to be clipped to +1.0);
the analyst keeps its rules signal and the call is logged as rejected (code + offline tests,
CHANGELOG v0.17 R0.4).

### Offline exercise

COOKBOOK [101. Structured outputs and the per-call evidence](../../COOKBOOK.md#101-structured-outputs-and-the-per-call-evidence).

### Pitfalls

- Coercing `"0.4"` or `null` to a number; the contract refuses strings and a required `null`.
- Trusting constrained decoding alone; the contract check is the second gate.

### Self-check (with answers)

1. *Why reject rather than clip?* A clipped value is a number the model did not say.
2. *What does a rejected reply cost?* That agent's answer is the rules answer for this call.
3. *Where is rejection recorded?* In the call evidence (`state.llm_calls`) and the fallback count.

---

## 5. Guardrails

### Plain idea

Several independent fences surround the model: untrusted text is fenced, a critic can only make
the decision more cautious, hard limits apply after the model, state-changing tools need
approval, and a red team measures how often an injection still moves the answer.

### Formal statement

- Fence: untrusted text is NFKC-normalised and fenced (`state.normalise_untrusted`); output
  guard `agentic/output_guard.py`.
- Critic (`agentic/critic.py`): failed checks lower confidence; on a model/rules divergence above
  `critic_divergence` 0.6, `apply_weight_rule` moves the weight toward neutral
  (`scale` 0.5 by default), never away from it.
- Hard limits: `PortfolioManager.guardrails` (short policy, max position, VaR95 cap, book VaR,
  minimum trade) run after the PM's weight.
- Policy and approvals: `agentic/policy.py`, six rules in order (deny list, capabilities,
  read-only, argument guards, risk level, allow); a non-read-only or high-risk tool needs approval;
  signed N-of-M and Ed25519 approvals are opt-in.
- Red team: `agentic/redteam_v2.py` with a benign control arm.

LEARN [11](../../LEARN.md#11-policy-who-may-do-what-explained-by-rule),
[14](../../LEARN.md#14-the-critic-can-only-lower-confidence),
[55](../../LEARN.md#55-red-teaming-the-fence-and-what-the-numbers-do-and-do-not-cover),
[65](../../LEARN.md#65-a-red-team-needs-a-control-arm).

### Worked example from this repo

The model asks for +0.80 on an FX pair, whose neutral weight is 0.0 by default (`config.py`); the
critic flags a divergence from the rules signal and `scale` gives 0 + 0.5 x (0.80 - 0) = +0.40
(arithmetic on `critic.apply_weight_rule`). In the v0.15 local run 21 of 150 attacks (14 %)
moved the News analyst's signal by more than 0.5 (measured, qwen2.5:7b, no control arm, so an
upper bound on compliance).

### Offline exercise

COOKBOOK [106](../../COOKBOOK.md#106-cut-a-filing-into-sections-and-fence-them),
[123](../../COOKBOOK.md#123-run-the-desk-with-the-critic-governing-position-size) and
[42. Queue an order for human approval](../../COOKBOOK.md#42-queue-an-order-for-human-approval).

### Pitfalls

- A critic that can raise confidence becomes a second, unaudited decision maker.
- Counting "attack moved the signal" without a control arm of the same length.
- Applying limits before the model: the model's answer then bypasses them.

### Self-check (with answers)

1. *Why may the critic only move toward neutral?* Neutral is a weight the limits already admit.
2. *Which runs first, approval or argument guards?* The guards; a bad request is denied before
   anyone is asked to approve it.
3. *Why does 14 % overstate compliance?* Appending any text can move a small model; only the
   attacked-minus-control difference measures obedience.

Same concept, another desk: [AgenticAICashEquities AI track](https://github.com/AshJha0/AgenticAICashEquities/blob/main/docs/learn/ai/README.md) (matching lesson coming).

---

## 6. Tools and MCP

### Plain idea

Agents reach data only through catalogued tools. Each call is policy-checked and leaves an
evidence record with a digest before the agent sees the result. The same tools are served over
MCP so another client can use them.

### Formal statement

`agentic/tools.py` (catalogue, schemas from Python signatures), `agentic/servers.py`,
`agentic/evidence.py`, `agentic/mcp_server.py`, deferred loading in `agentic/tool_search.py`.
LEARN [9](../../LEARN.md#9-tools-as-the-only-way-to-reach-data) and
[17](../../LEARN.md#17-mcp-the-api-and-observability).

### Worked example from this repo

A role without the `PROPOSE_TRADES` capability asking for a state-changing tool is denied by
the read-only rule, which requires that capability and approval (`agentic/domain.py`, `agentic/policy.py`; code + tests).

### Offline exercise

COOKBOOK [41. Call a tool directly, under policy](../../COOKBOOK.md#41-call-a-tool-directly-under-policy)
and [49. Expose the tools over MCP and consume them](../../COOKBOOK.md#49-expose-the-tools-over-mcp-and-consume-them).

### Pitfalls

- A side door (a direct provider call inside an agent) that leaves no evidence.
- Trusting tool output text as instructions; it is data.

### Self-check (with answers)

1. *What makes a finding traceable?* It cites evidence ids that resolve in the store.
2. *Why derive schemas from signatures?* One definition, so in-process and MCP cannot drift.
3. *What does deferred loading save?* Prompt space: tool schemas are loaded only when searched for.

---

## 7. RAG

### Plain idea

Retrieval hands the model passages from the desk's own policies and, separately, point-in-time
research text. A retriever is measured on a labelled question set before any analyst may use it.

### Formal statement

`agentic/rag.py` (hashed TF-IDF over the knowledge docs) and `agentic/research_rag.py` (point in
time: a passage is visible only after its timestamp), with a recall gate. LEARN
[16](../../LEARN.md#16-retrieval-over-the-desks-own-rules) and
[54](../../LEARN.md#54-measuring-retrieval-before-an-analyst-may-use-it).

### Worked example from this repo

On 100 questions over a 34-passage invented corpus, recall@5 is 0.990 for TF-IDF and hybrid
(synthetic fixture; it shows the mechanism and says nothing about real filings). The
paraphrased v2 set is in `docs/results/v17_retrieval/`.

### Offline exercise

COOKBOOK [107. Research retrieval and the recall gate](../../COOKBOOK.md#107-research-retrieval-and-the-recall-gate).

### Pitfalls

- Questions written with the gold passage's words: recall is then inflated (hence v2).
- Retrieving a document dated after the as-of.

### Self-check (with answers)

1. *Why gate on recall?* An analyst fed the wrong passage is worse than one fed none.
2. *What makes retrieval point in time?* A passage is filtered out unless it was public before the as-of.
3. *Why does 0.990 not transfer?* The corpus is small and invented.

Same concept, another desk: [AgenticAICashEquities AI track](https://github.com/AshJha0/AgenticAICashEquities/blob/main/docs/learn/ai/README.md) (matching lesson coming).

---

## 8. Memory and reflection

### Plain idea

After a decision's horizon passes, its outcome is attached with a short lesson. Later decisions
on the same instrument see up to three lessons and a track record, and only resolved outcomes.

### Formal statement

`agentic_trader/memory.py`: entries resolve after `horizon_days`; `lessons(symbol, as_of, k=3)`
returns lessons resolved before the as-of; lessons hold no raw price level, because they are
fed back into prompts. Memory writes are guarded (`output_guard.poison_match`). LEARN
[23](../../LEARN.md#23-memory-edge-cases-and-refusing-to-guess).

### Worked example from this repo

A paraphrased steering phrase planted in memory: the poison corpus went from 19/20 to 20/20
refused in v0.18, in sample (one phrase was written after seeing the miss), so no
out-of-sample rate is claimed (CHANGELOG v0.18).

### Offline exercise

COOKBOOK [24. Persist memory across runs](../../COOKBOOK.md#24-persist-memory-across-runs).

### Pitfalls

- Showing a lesson whose outcome resolved after the as-of: look-ahead through memory.
- Letting model text write itself into memory unguarded.

### Self-check (with answers)

1. *Why only resolved outcomes?* An unresolved one would reveal the future or be noise.
2. *Why no price levels in lessons?* They would de-anonymise the series.
3. *Why is 20/20 not a guard rate?* It was reached after looking at the miss.

---

## 9. Classical ML

### Plain idea

The statistical learning here is classical and opt-in: an HMM for volatility regimes, a shrunk
IC-weighted signal combination, conformal intervals for sizing, and purged cross-validation with
a leak canary to check none of it saw the future.

### Formal statement

`agentic_trader/regime.py` (Gaussian HMM, Baum-Welch), `agentic_trader/combine.py`
(James-Stein-shrunk ICs, Ledoit-Wolf, split conformal), `agentic_trader/leakage.py`
(`purged_walk_forward`, Student-t gate, `future_leak_canary`). The `regime`, `conformal` and
`combination.method: "ic"` switches are off by default. LEARN
[52](../../LEARN.md#52-purged-cross-validation-and-the-leak-canary),
[64](../../LEARN.md#64-conformal-intervals-when-the-data-are-not-exchangeable),
[67](../../LEARN.md#67-classical-ml-in-this-repo-what-is-fitted-and-when-it-is-on).

### Worked example from this repo

On design data (real prices, 15 core names, 2016-2021, `results/v14/`) the three variants
scored mean Sharpe minus the control's -0.131 (IC combination), -0.179 (regime conditioning)
and -0.079 (conformal sizing). None was adopted and nothing was tuned afterwards.

### Offline exercise

COOKBOOK [132](../../COOKBOOK.md#132-classical-ml-used-by-the-desk-an-hmm-regime-and-a-conformal-interval),
[102. Purged walk-forward IC on a signal](../../COOKBOOK.md#102-purged-walk-forward-ic-on-a-signal),
[105. The Student-t gate on purged fold ICs](../../COOKBOOK.md#105-the-student-t-gate-on-purged-fold-ics).

### Pitfalls

- Fitting the HMM on the whole sample, then labelling the past with it.
- Ordinary k-fold on overlapping forward returns: the label windows leak across folds.
- Reading a split-conformal interval as valid on autocorrelated data.

### Self-check (with answers)

1. *What does the embargo add to purging?* A gap after the test fold for serial dependence.
2. *What does a canary failure mean?* Some output changed when only future prices changed: a leak.
3. *Why shrink ICs?* A noisy IC taken at face value overweights luck.

Same concept, another desk: [AgenticAICashEquities AI track](https://github.com/AshJha0/AgenticAICashEquities/blob/main/docs/learn/ai/README.md) (matching lesson coming).

---

## 10. Honest AI evaluation

### Plain idea

Decide what you will measure before you look, keep data the decision never saw, check that the
model is not just remembering, and check the judge before trusting its grades.

### Formal statement

Pre-registration: `docs/evaluation/v09_preregistration.md` and the draft
[v16 pre-registration](../evaluation/v16_preregistration_DRAFT.md) (including the skip rule).
Every cell is a trial in `evaluation.TRIALS`, counted in the deflated Sharpe. The recall audit
(`scripts/v16_local_study.py recall2`) scores the model against a label-permutation null and a
placebo arm. LLM-as-judge: `agentic/judge_kit.py`, Cohen's kappa against human labels, judge
from another model family. LEARN [27](../../LEARN.md#27-a-holdout-is-spent-the-moment-you-look-at-it),
[43](../../LEARN.md#43-pre-registration-decide-before-you-look),
[62](../../LEARN.md#62-did-the-model-remember-a-recall-audit-with-a-null-and-a-placebo),
[68](../../LEARN.md#68-llm-as-judge-a-judge-must-agree-with-labels-first).

### Worked example from this repo

The forward paper record (daily since 2026-09-29) is the only unseen data; its single
pre-registered decision look is at 3,600 sessions, about 14 years
([pre-registration](../evaluation/v09_preregistration.md)). The judge's calibration result is
pending: its output file is not committed yet, so no kappa is quoted.

### Offline exercise

COOKBOOK [133. LLM-as-judge](../../COOKBOOK.md#133-llm-as-judge-agreement-with-labels-before-trusting-the-judge)
and [122. Is a null IC a real null?](../../COOKBOOK.md#122-is-a-null-ic-a-real-null).

### Pitfalls

- Looking at the holdout "just once" before the rule is frozen.
- Quoting raw agreement instead of kappa.
- Dropping skipped or failed units without reporting them.

### Self-check (with answers)

1. *Why count unrun cells as trials?* They were chosen among; the deflated Sharpe must pay for them.
2. *What does the placebo arm control for?* A model that picks a position (say the first option)
   regardless of content.
3. *Why must the judge come from another family?* Self-preference bias.

Same concept, another desk: [AgenticAICashEquities AI track](https://github.com/AshJha0/AgenticAICashEquities/blob/main/docs/learn/ai/README.md) (matching lesson coming).
