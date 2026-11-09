# What the model adds (PLAN 6.2, skeleton)

The question this page answers: when a language model sits inside the desk, does it add
information the rules desk does not already have, and what does it cost in risk? The rules
desk is the incumbent control. A model result counts only if it is measured against that
control on the same states.

This is a skeleton. It collects the results that exist today, each with its evidence class,
and leaves explicit rows for what is pending. No row is filled from expectation.

Evidence classes used below:

- **real-local**: measured on real inputs with the local model (qwen2.5:7b Q4 on CPU). A 7B
  floor; it says nothing about frontier models.
- **real-rules**: measured on real data, no model involved.
- **fixture**: measured on an invented or synthetic corpus; tests the machinery, not a model.
- **pending**: built, not yet measured.

Worked example of reading a row: the red-team row says 21 of 150 attacks moved the local
model's signal by more than 0.5. That is a rate for one 7B model on one corpus. It is evidence
that the fence alone does not stop instruction-bearing text from reaching a small model's
judgement; it is not evidence about Claude.

| Item | Result | Evidence class | Source |
|---|---|---|---|
| 4.4 Injection red-team, local model | 21/150 (14%) attacks moved the signal > 0.5: instruction 10/32, multilingual 8/26, role play 2/20, encoded 1/40, fence escape 0/32. All 300 replies readable. | real-local | `docs/results/v15_local/redteam_compliance.json`; PLAN §9 2026-11-08 (evening) |
| 4.4 Fence structure, rules path | 150/150 fenced; rules signal equals the lexicon score 150/150; 6/150 direction flips from the lexicon words buy/sell. | fixture | PLAN §4 row 4.4; `tests/test_v15_security.py` |
| 3.2 Filing tone change (rules feature) | Not supported: IC negative at all horizons, no \|t\| >= 2 (design period, 9 names, 201 real SEC filings). | real-rules | PLAN §9 2026-11-08 (later) |
| 3.7 Retrieval on real filings | recall@5 TF-IDF 0.92, hybrid 0.98; the 0.8 gate passes. | real-rules | PLAN §9 2026-11-08 (later) |
| 3.7 Retrieval on fixture corpus | 100 questions, 34 invented passages: TF-IDF recall@5 0.990 MRR 0.954, hybrid 0.990 / 0.961. | fixture | PLAN §4 row 3.7 |
| 3.8 LLM text analysts, local model | Macro: 11/12 usable, stance agrees with label 11/11 usable. Fundamentals: 10/10 sections usable, 10 claims kept, 0 dropped. Usability only, not predictive value. | real-local | `docs/results/v15_local/text_analysts.json`; PLAN §4 row 3.8 |
| 4.2 Planner survival, real model plans | 200 tasks, qwen2.5:7b-instruct (4-bit, CPU, temperature 0, compact grammar-constrained prompt): 1,345 of 1,506 proposed steps survived the validator (89.3%); the validator added 520 required steps, repaired 145 plans, and 13 plans (6.5%) were unusable (timeout or unparseable); 0 data-budget hits. Canonical and rule planner: 100% (1800/1800). Recorded plans: `tests/data/v15_local_model_plans.jsonl` (+ `.meta.json`; the run resumed twice after shutdowns, so the meta usage block covers the last segment only). | real-local | PLAN §4 row 4.2; PLAN §9 2026-11-09 |
| P2 LLM study cells (hit rate, Brier, model-delta book vs rules control) | Pending. The KPI table (`agentic-trader kpi`, PLAN 6.4) will be computed from the P2 records when they exist. | pending | PLAN §4 P2; `agentic_trader/kpi.py` |

## Selection statistics and cost per decision (PLAN 6.1)

**Plain idea.** Each study cell is one more variant tried on the design data, so each one is
counted in the deflated Sharpe whether or not it is run or adopted. Each cell is also shown
with what a decision cost.

**Formally.** `evaluation.TRIALS` holds 77 registered trials, of which 7 are the P2 model
cells (all registered before any run; `tests/test_v16_study.py`). The deflated Sharpe uses
`stats.selection_report(returns, measured_sharpes, n_trials=evaluation.registered_trial_count())`:
the expected-maximum benchmark counts all 77, the dispersion uses the measured Sharpes only, and
the output carries both `trials` and `trials_measured`. Cost per decision is
`kpi.cost_per_decision_usd` (total model spend / decisions; 0 for rules and the local model).

**Worked example of reading the table.** A cell with a Sharpe difference of +0.10 over the
control, a deflated probability of 0.40 and a cost of $0 per decision would be free noise, not
an edge. No such number exists yet; every cell below is pending.

| Cell | Model roles | Sharpe minus control | Deflated Sharpe prob. (n_trials = 77) | Cost per decision, USD | Evidence class |
|---|---|---|---|---|---|
| rules (control) | none | 0 by definition | pending | 0 | pending |
| local_analysts | analysts | pending | pending | pending | pending |
| local_all | every role | pending | pending | pending | pending |
| local_text | bull, bear | pending | pending | pending | pending |
| local_pm | portfolio manager | pending | pending | pending | pending |
| no_debate | all but the debate | pending | pending | pending | pending |
| debate_1 | every role, one debate round | pending | pending | pending | pending |
| neutral_risk | every role, one neutral risk analyst | pending | pending | pending | pending |

Source: cell definitions `scripts/llm_study.py` `CELLS`; registry `agentic_trader/evaluation.py`.
The first pass runs rules, local_analysts and local_all; the other five are registered and unrun.

> **Ready but unrun.** Every Claude cell is dry-run only at $0. No row on this page is a
> Claude measurement.

What would change this page: the P2 records arriving (feed them to `agentic-trader kpi`), and any Claude cell being run with a recorded budget.
