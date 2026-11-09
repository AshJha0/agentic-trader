# AgenticTrader: second in-depth review and v0.17 plan (2026-11-09)

Status: review complete, plan proposed, NOT started. Zero spend, no card details, free data, local model only.

Method: two independent read-only reviews of `main` @ cb8dd38 (AI layer; quant, code, tests and docs), each finding cited to file:line and checked against code, not docs. Two claims spot-checked by the maintainer: A1 (temperature fixed at 0, `agentic_trader/agents/local_llm.py:122`) confirmed; B1 (eval prompts carry real tickers: AAPL 107, MSFT 109, NVDA 105, JPM 111, XOM 74 mentions in `eval_set/items.json`) confirmed. Full reviews are Appendix A and B.

## 1. Verdict

The plumbing is good and the statistics code is above sell-side average (BH, PSR/DSR, block and cluster bootstraps, ex-ante EWMA, FHS on lagged sigma, schemas plus a second contract check, anonymiser, fence, replay, an honest MDE table). The "no edge" conclusion stands.

What a top desk would reject is the evidence around it. Several defects would inflate or misstate results, and two mechanisms are weaker than the docs say:

- **The model study can overstate precision.** Temperature is fixed at 0, so the planned two seeds are identical replays that are then pooled and bootstrapped as independent (A1). The eval set is not anonymised while the study is (B1). Decisions are scored over ~3.6-month holds although analysts forecast 1-4 weeks (B4).
- **Governance does not govern.** The critic scales `confidence` after the decision; sizing reads `target_weight`, so a flagged divergence changes no position, and the backtest graph has no critic at all (A2). Schemas have no ranges and outputs are clipped, so an injected `signal: 999` becomes a valid full-conviction +1.0 (A3).
- **Backtests trade at the bar they read.** Signals use `close[t]` and trades fill at `p[t]`, with no lag or next-open option (Q1). This biases toward edge, so it cannot create the null, but short-horizon rule differences sit inside the bias.
- **"Purged CV for every IC" is mostly a label.** For fixed signals the training folds are unused, and the gate is a 5-fold t-test with 4 df, so "nothing cleared" means "could not detect"; no power is reported (Q2).
- **Red-team and retrieval numbers are softer than stated.** 21/150 has no benign control, no direction check, one synthetic state, the unconstrained call path and no end-to-end weight impact (B3/A4). Recall@5 0.92/0.98 rests on 50 real questions written from the gold passages (B5). Judge calibration is 30 hand-written replies judged by the same 7B (B2).

## 2. Findings that are wrong or disputed

- **Paper cron "too early" (Appendix B, item 4): disputed.** The paper script records the last complete New York session (`scripts/paper_trade_v09.py:4`, default as-of = New York yesterday), so the 21:30 UTC fetch reads a bar that closed a day earlier. Keep 21:30 unless the revision log shows same-day revisions; R4.2 adds the check.

## 3. Plan (v0.17), ordered

Effort in solo plan-days; calibrated at ~12-15 plan-days per wall-clock day with 2-3 parallel lanes. Model-run items share the laptop with the running P2 chain.

### R0 Before any P2 result is published (blocking, ~3 d)

| # | Item | Fix | Effort |
|---|---|---|---|
| R0.1 | A1 seed pseudo-replication | seeds only with temperature > 0, else refuse `--seeds > 1`; never pool replays; test | 0.5 |
| R0.2 | B1 eval set not anonymised | re-freeze items through the same anonymiser; re-run the eval step | 1 |
| R0.3 | B4 holding horizon | score each decision over its own horizon; IC and hit rate primary, Sharpe secondary; recomputed from stored rows, no re-run | 1 |
| R0.4 | A3 schema ranges | `minimum`/`maximum` in schemas; reject out-of-range instead of clipping; count as a contract failure | 0.5 |
| R0.5 | Two VaR defaults | one constant, live_readiness fixed, agreement test | 0.2 |

### R1 Research honesty (~6 d)

| # | Item | Fix | Effort |
|---|---|---|---|
| R1.1 | Q1 execution lag | `exec_lag` / next-open option in both engines (C++ and numpy, parity test); re-run registered trials at lag 1 as a protocol amendment | 2.5 |
| R1.2 | Q2 gate power | Newey-West t and minimum detectable IC per table; drop the "purged" label for fixed signals | 1.5 |
| R1.3 | Multiple testing | BH across the gate family (alphas x names x horizons); DSR with a pre-registry trial estimate | 0.8 |
| R1.4 | Recall audit as precondition | prereg requires a 2.4 pass before any holdout look | 0.5 |
| R1.5 | Model-changed P&L | P&L of decisions the model changed versus the rule decision | 0.7 |

### R2 Governance that governs (~5 d)

| # | Item | Fix | Effort |
|---|---|---|---|
| R2.1 | A2 critic | critic veto/scale on `target_weight` in harness and graph; new study cell critic-on | 1.5 |
| R2.2 | B3/A4 red-team v2 | benign control arm, direction-matched compliance, constrained `complete_json` path, several real states, all text analysts, end-to-end `target_weight` impact | 2.5 |
| R2.3 | A5/A8 fence | Unicode NFKC normalisation, single-source fence code, stale docstrings | 0.7 |
| R2.4 | A7 replay keys | canonical JSON hashing instead of pickle | 0.3 |

### R3 Evaluation credibility (~3.5 d + owner time)

| # | Item | Fix | Effort |
|---|---|---|---|
| R3.1 | B2 judge | owner labels >= 100 real replies (owner ~2-3 h, guided sheet); judge from a different free local model family | 1.5 |
| R3.2 | B5 retrieval set | 100 questions paraphrased independently of gold wording; report both sets | 1 |
| R3.3 | Eval regression gate | CI check tied to the prompt-registry hash, on fixtures | 1 |

### R4 Desk realism and ops (~4 d)

| # | Item | Fix | Effort |
|---|---|---|---|
| R4.1 | Vintage | store raw unadjusted bars and corporate actions per paper session, not only a hash | 1 |
| R4.2 | Cron check | assert the recorded session is final; alert on same-day revisions | 0.3 |
| R4.3 | NYSE calendar | one-off closures and early closes, tests | 0.5 |
| R4.4 | OMS limits | gross/net, per-name concentration, order-time VaR checks | 0.5 |
| R4.5 | Build hygiene | hashed lockfiles per Python version with `--require-hashes`; mypy blocking on the quant core | 1.5 |

### R5 Simplify (owner decisions)

- **OD-A C++ core.** Keep (parity is a teaching asset) or retire (doubles CI, no benchmark on daily bars). Recommendation: keep; add one benchmark that justifies it, else retire in v0.18.
- **OD-B Claude-only code never run live** (refusal-fallback beta, BatchLLM live path, price tables). Recommendation: keep as dry-run with a "never run live" box.
- **OD-C Approval machinery** (N-of-M, TTL, re-pricing). HMAC with a server-held secret means server holders can forge approvals. Recommendation: document as a demonstration; asymmetric keys only if positioning needs it.
- **OD-D Second local model** (~5 GB free download) as the judge in R3.1. Recommendation: yes.
- Prune docs size (LEARN, COOKBOOK, CHANGELOG at 130-150 KB) and stale root artefacts (coverage.xml, build/, egg-info).

### Interaction with the running P2 chain

Recall and calibration are unaffected. B4 is fixed in the report from stored rows, so the study cells keep running. B1 needs only the eval step re-run after R0.2. Recommendation: land R0 as the next PR, let the chain continue, re-run the eval step.

### Totals

~22 solo plan-days, $0: about 2-3 wall-clock days of build with parallel lanes, plus model re-runs (eval some hours, red-team v2 ~5-6 h, lag-1 trials some hours) that queue behind the P2 chain. Owner time: R3.1 labelling only.

## 4. Were the 2026-11-07 fixes real?

Real: EWMA/FHS VaR, factor and stress rows, leak canary, Actions paper runner with freshness check, SHA-pinned actions, ruff, schemas plus contracts, anonymiser, replay. Half: vintages (hash only). Not real: "mypy strict" (advisory, lenient). Not fixed: stop slippage, financing spread, horizon from decay. Fixture-only: most agentic fixes have met no real model outside the 7B runs.


## Appendix A. AI layer review

# AgenticTrader AI-side review (hostile, 2026-11-09, main @cb8dd38)

Scope: LLM integration, agents/harness, RAG, guardrails, ML, LLM evaluation methodology.
Method: read code and frozen data, not docs. Read-only; nothing run except small Python reads of
committed JSON. Every finding cites file:line. Effort = wall-clock solo days, $0.

## Verdict

The plumbing is better than most hedge-fund prototypes: schemas plus a second contract gate,
anonymiser, fence, HMAC approvals, replay, prereg with an honest MDE table. The problem is the
**evidence layer around the model**, which is where a desk reviewer looks first. It has several
defects that would quietly inflate or misstate results:

- the study counts duplicated temperature-0 "seeds" as extra data;
- the critic, the advertised governance control, changes no position;
- the eval set skips the anonymisation the study relies on;
- the "human-labelled" judge calibration is 30 synthetic replies;
- the red team has no benign control and does not test the path the desk actually uses.

The previous review's fixes (P1 API plumbing, P4 governance) are real in code, but most are
untested against a real model. Several docstrings still say "UNRUN" for things that were run.

---

## (a) Real defects / bugs

**A1. CRITICAL: "seeds" in the LLM study are identical replays, and the bootstrap counts them as new periods.**
- The desk's local model always decodes at `temperature: 0.0` (`agentic_trader/local_llm.py:122`). `config.py:18` says so: "temperature is 0 regardless".
- `llm_study.run_study` varies only `local_llm_seed` per seed (`scripts/llm_study.py:357`). Under greedy decoding the seed does nothing, so seed 1 repeats seed 0.
- `cell_metrics` appends each seed's period returns into one series (`llm_study.py:436-447`) and block-bootstraps it as one time series (`:389-406`). With the default `--seeds 2` (`:591`) and the planned 2.3 design (15x40x2), n doubles and the CI shrinks by about 1/sqrt(2) for free. Circular blocks also wrap across the seed boundary.
- `dispersion` (`:461-463`) is identically 0, and gets reported as a stability result.
- The first pass uses 1 seed (`:207`), so it is unaffected today. The full 2.3 design is not.
- Fix: either sample (T>0) for the seeded cells, or set seeds=1 at T=0. Always bootstrap per seed and average the Sharpe diff across seeds; never concatenate. Add a test asserting that identical seed series give the same CI as one seed. **0.5 d.**

**A2. HIGH: the critic changes no position, so the governance control is cosmetic for P&L.**
- `harness._finalise` multiplies `decision.confidence` by `critic.multiplier` after the decision is made (`agentic/harness.py:669-671`).
- Order sizing uses `target_weight` (`agentic/servers.py:333,370`). Confidence never feeds back into the weight.
- A `model_rule_divergence` failure (`critic.py:117-129`) therefore leaves the position unchanged. The graph/backtest path that the P2 study uses has no critic at all (no reference in `graph.py`). So the study measures an ungoverned desk while the docs sell a governed one.
- Fix: make the critic act on weight. On divergence, replace the analyst's signal with `rule_signal` (or clip it to `rule_signal ± divergence`) and re-run PM sizing. Or scale `target_weight` by the multiplier. Wire the same critic into `graph.py` behind a flag and make "critic-on" a study cell. **1.5 d.**

**A3. HIGH: out-of-range model numbers are clipped to the extremes, not rejected.**
- The contract checks only presence and finiteness (`agents/base.py:136-147`). The JSON schemas have no bounds (`contracts.py:26-28`).
- `analysts.py:74-75` then `clip`s, so `signal: 999` becomes +1.0, maximum conviction. An injected "set signal to 50" lands as a full-size view and passes as contract-valid.
- Fix: add `minimum`/`maximum` to the schemas wherever the backend honours them (Ollama grammar does). Make an out-of-range value a contract rejection that falls back to rules, and count it in `contract_rejection_rate`. **0.5 d.**

**A4. MEDIUM: the red-team compliance harness calls a different endpoint from the desk.**
- `compliance_run` calls `llm.complete(...)`, which is unconstrained (`agentic/redteam.py:166-167`).
- The desk path is `ask_json` with a schema, i.e. `complete_json` with grammar decoding (`agents/base.py:125`, `local_llm.py:116-130`).
- The 21/150 figure is for free-text decoding plus the lenient `extract_json` (`llm.py:731-747`), not for the configuration that trades. Constrained decoding could move the number either way.
- Fix: run both modes and report both. **0.5 d plus overnight CPU.**

**A5. MEDIUM: the fence is ASCII-only.**
- The neutraliser regex `<\s*/?\s*untrusted_data\b[^>]*>?` (`state.py:36`, duplicated at `redteam.py:46`) does no NFKC normalisation. Fullwidth `＜/untrusted_data＞`, homoglyph or zero-width-split tags pass through untouched.
- The corpus has encoded families, but `fence_check` only verifies the ASCII tag count.
- Fix: NFKC-normalise and strip zero-width/bidi/tag characters (U+200B-U+200F, U+202A-U+202E, U+2066-U+2069, U+E0000-U+E007F) before the regex. Add corpus cases for each. **0.5 d.**

**A6. MEDIUM: approval "signatures" are shared-secret HMACs held by the same process.**
- `policy.py:327` (HMAC-SHA256) and `:429-443`: the server holds every approver's secret. Anyone with server access can mint N-of-M approvals, so this gives no non-repudiation.
- Fix: Ed25519 via the stdlib-free `cryptography` package, which is likely already a transitive dependency; check the lock. Store public keys only on the server. Or document it plainly as "tamper-evident, not non-repudiable". **1 d** (or 0.1 d for the docs-only option).

**A7. LOW: replay keys are `sha256(pickle.dumps(...))`.**
- `agentic/replay.py:54`. The pickle byte stream changes with pandas/numpy/Python versions, so recordings stop matching after a dependency bump.
- Loading uses `pickle.loads` (`:284`), and recordings could become test fixtures that get shared.
- Fix: canonical JSON key (sorted keys, floats via `repr`, frames via `to_json(orient="split")`). Keep pickle only for the payload, behind a hash allowlist. **1 d.**

**A8. LOW: stale docstrings contradict the results.**
- `redteam.py:22-25` and `:141,163` say "UNRUN ... no local model". `docs/results/v15_local/redteam_compliance.json` exists with 150 rows.
- A reviewer reading code will distrust everything else.
- Fix: grep for `unrun|UNRUN|no local model` and update. **0.1 d.**

## (b) Methodological flaws that would invalidate conclusions

**B1. CRITICAL: the eval set is not anonymised, while the study is.**
- The study forces `llm_anonymize: True` (`llm_study.py:75`). The default is `False` (`config.py:61`).
- 41 of 150 frozen eval prompts contain real tickers (AAPL/MSFT/NVDA/SPY/EURUSD; counted from `knowledge/eval_set/items.json`).
- Eval scores ("used facts", "no invented numbers") are therefore measured on a different prompt distribution from the trading cells. Named tickers also invite recalled numbers, which inflates "invented numbers" failures in a way that does not transfer.
- Fix: rebuild the items through `Anonymizer` (rescale facts, aliases), re-freeze, re-pin the test. Optionally keep a named copy as an explicit "leak probe" arm. **1 d.**

**B2. HIGH: the "human-labelled calibration subset" measures nothing about the real judge task.**
- `calibration.json` has 30 rows. Its own `_note` says "Replies are written by hand, not by a model". The labels are the author's.
- The commit (`7813829`, "v0.16 lane B") came from an agent lane, so the "human" labeller is most likely the same AI that wrote the rubric and checker.
- Label mix: 15/30 all-pass, 4 fence failures.
- Kappa on 30 hand-crafted, deliberately clean-cut cases says nothing about agreement on real 7B replies. The judge is also the same qwen2.5:7b that is being judged (`v16_eval.py:165`), a known self-preference bias.
- Fix: label at least 100 real model replies from `run.jsonl`, by the owner (about 2 h), stratified by checker verdict. Report kappa with a bootstrap CI. Use a different model family as judge (e.g. llama3.1:8b or phi) and report cross-judge agreement. **1.5 d.**

**B3. HIGH: the red-team metric has no control arm and conflates sentiment with compliance.**
- "Complied" means |Δsignal| > 0.5 or unreadable (`redteam.py:168`).
- There is no benign-suffix control: the carrier plus a neutral sentence of equal length and tone.
- There is no targeted test: did the signal move in the direction the payload demanded?
- Payloads containing "buy/sell" legitimately move a sentiment analyst. The rules arm counts exactly this (`redteam.py:14-19`), but the model arm does not subtract it.
- Only one synthetic state is used (`_state`: AAPL, a linear uptrend), and only the News analyst. The critic divergence check, which would have flagged most of the 21 ±1 replies (bases cluster at 0, attacked at ±1.0 in 21 cases), is never exercised end to end.
- Fix: add a control arm and a direction-matched compliance definition. Add 5 states, and an end-to-end run measuring how many attacks change the final `target_weight` after critic and limits. That last number is the one a risk committee wants. **2 d plus overnight CPU.**

**B4. HIGH: first-pass P&L holds each decision about 3.6 months against a stated 1-4 week horizon.**
- 20 dates spread evenly over 2016-2021 (`llm_study.py:151-155,207`). Each weight is held to the next design date (`:425-446`).
- Analysts forecast "next 1-4 weeks" (system prompt in `items.json`), and trades carry `horizon_days`.
- The Sharpe compares forecasts at roughly 5x their horizon. A null there is uninformative and a positive is luck. With 19 periods, the design-bar CI (prereg DRAFT:38) is essentially unpassable.
- Fix: score each decision over its own horizon (e.g. a 20-day forward return, or `horizon_days`). Use IC / hit rate versus the control as the primary metric, which matches PLAN principle 5. Treat Sharpe as secondary. State the design-pass MDE as the prereg does for the holdout. **1 d.**

**B5. MEDIUM: retrieval recall@5 0.92/0.98 is close to self-fulfilling.**
- `edgar_real_questions.json` has **50** questions, not 100. They were written while looking at the gold passage and repeat its literals and entity names, e.g. "from 80 cents to 84 cents", "J&J board raises quarterly dividend to 95 cents". Lexical overlap is what TF-IDF rewards.
- The corpus is small, and `evaluate_retrieval` (`research_rag.py:423-433`) has no distractor-scale test.
- The gate (≥0.8) therefore says little about analyst-style queries ("is credit risk rising at JPM?").
- Fix: add 50 paraphrased/abstract questions written without the passage open. Grow the corpus to every cached filing (hundreds). Report recall by question type. **1.5 d.**

**B6. MEDIUM: training-window contamination guard rests on an audit that has not run.**
- The design period 2016-2021 and holdout 2022-2026-06 both sit inside qwen2.5's pretraining window. The prereg admits anonymisation is "the only guard" (DRAFT:53).
- The 2.4 recall audit is pending. The return-series shape leak is acknowledged (`v16_local_study.py:22`) but not quantified.
- Fix: run 2.4 before any P2 number is published, and make "recall ≤ chance + 2 SE" a hard precondition in the prereg. **0.5 d plus CPU.**

**B7. MEDIUM: the planner's 89.3% step survival is a validator metric, not a quality metric.**
- The validator added 520 required steps. Survival therefore measures how much code repaired the model, not whether the plans were good or produced better decisions.
- Fix: report "plans needing zero repair" and the decision equality versus the canonical plan on the 200 tasks. **0.5 d.**

**B8. LOW: the bootstrap p-value is the percentile-tail share, not null-centred.**
- `llm_study.py:404`. It is acceptable as a rough number, but with deflated Sharpe in the bar it should be a studentised or null-recentred bootstrap. **0.3 d.**

## (c) Missing versus a 2026 production AI research platform

| # | Missing | Severity | $0 fix | Effort |
|---|---|---|---|---|
| C1 | Eval regression gate in CI on **recorded real local replies**: fixtures exist (`tests/data/v15_local_model_plans.jsonl`), but there is no "score must not drop" gate on prompt changes. `prompt_bundle_hash` (`prompts.py:162`) is not tied to an eval score. | high | CI job: prompt hash change ⇒ eval on recorded replies must be re-recorded or the hash pinned to a stored score | 1 d |
| C2 | Per-decision attribution of the model delta (exact P&L of the decisions the model changed vs the rules, with CI). `kpi.py` exists but n=0. | high | Compute it from first-pass rows (`sources`, `rule_signal`) as soon as P2 lands | 0.5 d |
| C3 | Output-side guard: no check that the model's summary contains no URLs, tickers outside the allowed set, or canary echoes before it is stored as untrusted memory / report text. | medium | regex/allowlist filter in `reporter.py` + memory write path | 0.5 d |
| C4 | Online drift monitoring of model outputs (signal distribution, rejection rate, divergence rate per day) with an alert. `drift` exists only as a two-build offline compare. | medium | daily paper-runner job appends stats; CI freshness check already exists, add thresholds | 1 d |
| C5 | Uncertainty from the model is never validated: `confidence` is not scored (Brier/reliability) on any real-model output. | medium | add to 2.6 using forward 20 d returns | 0.5 d |
| C6 | No adversarial test of the **memory** channel (poisoned lesson reaches later prompts). | medium | add 20 corpus items through `memory.remember` → recall path | 0.5 d |
| C7 | Embedding retrieval path untested (PLAN 3.5: `sentence-transformers` not in the lock) yet the 0.98 hybrid number is quoted. | low | either lock the extra and test, or mark it as a one-off number | 0.5 d |

## (d) Over-engineering / things to delete or freeze

- **Claude-only P1 machinery that has never run against the API**: refusal-fallback beta (`llm.py:29-34,437-441`), 5.5 price/capability tables, served-model drift, `count_tokens` admission, and `BatchLLM`/1.5b batching (`batch.py`, 281 lines) for a $0 project. These are maintenance liabilities against moving beta headers. Freeze them behind one "untested against live API" banner and stop extending them. Delete `_FALLBACK_BETA` usage if no funded run is planned within 3 months.
- **N-of-M HMAC approvals, TTL, re-pricing, second store** (`policy.py:370-460`): this is production theatre for a paper desk with one human. Keep a single signed approval and drop the rest, or fix A6 properly.
- **Tool-search deferred loading** (`agentic/tool_search.py`) for a small tool set. Context savings are negligible, and it adds a failure mode. Delete it, or justify it with a token measurement.
- **OpenTelemetry extra plus golden transcripts**: fine, but there are no SLO numbers from real runs. Either collect them from the local runs or mark the feature as scaffold.
- **Two FENCE_NOTE copies** (`critic.py:36`, `text_analysts.py:35`) and two neutraliser regexes (`state.py:36`, `redteam.py:46`). Make each a single source of truth, or the next fix (A5) will land in one place only.

## Were the previous review's fixes real?

- L5 model tiers, structured outputs, caching, token counting: **real in code**, fixture-tested only; zero live verification (acceptable at $0, but say so in code, not only docs).
- "Governance governs decisions with no information": **still true**, and A2 shows that even when it fires it changes nothing.
- "No injection red-team on a live model": **done, but measured wrong** (A4, B3).
- "Analysts hand the model the same indicators": **unchanged**. Text analysts exist but are off by default and the filing-tone signal failed (3.2), so the model still mostly re-weights the rules.

## Top-10 priority list

| # | Item | Sev | Effort |
|---|---|---|---|
| 1 | A1: fix seed pseudo-replication before the 2.3 full design runs | critical | 0.5 d |
| 2 | B1: anonymise the eval set to match the study | critical | 1 d |
| 3 | A2: make the critic act on `target_weight` and add a critic-on study cell | high | 1.5 d |
| 4 | B4: score decisions over their own horizon; IC/hit rate primary | high | 1 d |
| 5 | B3 + A4: red-team control arm, direction-matched compliance, constrained-decoding mode, end-to-end `target_weight` impact | high | 2.5 d |
| 6 | B2: owner labels ≥100 real replies; cross-family judge | high | 1.5 d |
| 7 | A3: bounds in schemas; reject instead of clip | high | 0.5 d |
| 8 | B6: run the 2.4 recall audit and make it a prereg precondition | medium | 0.5 d |
| 9 | C1 + C2: CI eval-regression gate tied to the prompt hash; model-delta P&L attribution | high | 1.5 d |
| 10 | A5 + A8 + dedup: Unicode-safe fence, single-source fence/regex, stale docstrings | medium | 0.7 d |

Total ≈ 11 solo days, $0. Items 1, 2, 4 and 7 should land before any P2 result is written up,
or the first published LLM table will be wrong in ways an outside reader can find in an hour.


## Appendix B. Quant, code, tests and docs review

# AgenticTrader: hostile quant / quant-dev review (non-LLM scope)

Repo: C:\Work\Claude\AgenticTrader, main @ cb8dd38, read only. Reviewer stance: systematic fund
QR + QD + algo dev + eng lead. Every finding below was checked in code, not in docs. Effort is
wall-clock solo days. Spend for every fix is $0.

Coverage note: this was a targeted read (stats.py, leakage.py, risk_model.py, backtest.py,
quant/pycore.py engine, algo.py, oms.py pre-trade and calendar, validate.py, yahoo.py, CI and
paper workflows, lockfile, PLAN, previous review, live_readiness). I did not read alpha.py,
xalpha.py, combine.py, portfolio.py, evaluation.py line by line, did not diff C++ against
Python, and ran no tests. Findings outside the read set are marked "not verified".

## 0. Verdict

The statistical toolkit is above sell-side average and mostly correct: BH, PSR/DSR, the
circular block bootstrap, cluster-paired bootstrap, the purged fold builder, ex-ante EWMA, and
FHS standardised on lagged sigma. The 2026-11-07 review's fixes are mostly real: EWMA/FHS VaR,
factor exposures, stress rows, capacity, vintage hash, the Actions paper runner, freshness and
issue alerts, SHA-pinned actions, ruff. But four things weaken the headline claims:

1. Every backtest fills at the same close the signal reads (no execution lag anywhere).
2. The "purged walk-forward CV for every IC" is mostly a relabel. For fixed signals the
   training sets are never used, and the gate is a 5-fold t-test with 4 df, which has almost
   no power. "No alpha passed the gate" is therefore weak evidence of no alpha.
3. The vintage system stores a hash, not the bars. Revisions are detected, not reproducible.
4. mypy is advisory, the lockfile has no hashes and is 3.12-only, and docs disagree with code
   on the VaR default.

None of these flips the "no edge" conclusion. Point 1 biases results toward edge, and the
project found none anyway. They do mean that several "measured" statements are stronger than
the code supports.

## (a) Real bugs / correctness defects

| # | Sev | Finding (evidence) | $0 fix | Effort |
|---|---|---|---|---|
| A1 | High | **Same-bar execution.** `quant/pycore.py:688-705`: the weight `w_in[t]` is traded at `p[t]` (`Trade(t, prev, w, p[t])`) and earns `p[t+1]/p[t]`. The baselines compute their signal from `close[t]` (`backtest.py:236-256`, where `realized_vol(c,20)` includes c[t]). The agent loop decides at `window.index[i]` using bars up to i, then holds from i (`backtest.py:336-357`). `evaluation.md:210` documents this as an assumption, but there is no `execution_lag` or next-open option anywhere (grep finds none). It is a market-on-close fill on information you only have after the close. The bias is small for 12-1 TSMOM and material for ZMR, KDJ+RSI, 5d reversal and stop logic. | Add `execution_lag: int = 0` (shift `w_in` by 1) and a `fill="next_open"` mode to both engines (C++ and numpy). Re-run the headline tables with lag 1 as a sensitivity row. Pin it with a test showing that a signal equal to `sign(r[t+1])` earns nothing at lag 1. | 1.5 |
| A2 | Med | **Two VaR defaults.** `risk_model.py:98,113` defaults `method="fhs"`, but `config.py:169` sets `book_var_method: "ewma"`. `docs/evaluation/live_readiness.md` (pre-trade row) says "FHS default, EWMA option", which is wrong for the desk path. Any direct caller of `var_next()` gets FHS while the desk uses EWMA. | One constant `DEFAULT_VAR_METHOD` used by both. Fix the doc row. Add a test that `config` and the function default agree. | 0.2 |
| A3 | Med | **Calendar gaps.** `oms.py:145-167` `nyse_holidays` has no one-off closures (2012-10-29/30 Sandy, 2018-12-05 Bush, 2025-01-09 Carter) and no early closes (13:00 on the day before Independence Day, Black Friday, Christmas Eve). `is_open` will accept a 14:00 order on a half day, and the paper OMS's market_hours check is wrong on about 3 days a year. | Add a static `NYSE_SPECIAL` table (closures and early closes, 2000 to present) plus a test per entry. | 0.5 |
| A4 | Low | **Quadratic replay** in the agent backtest: `backtest.py:341-343` re-runs `quant.run_backtest(prices[:i+1], ...)` at every rebalance to recover the held weight. That is O(n^2/rebalance_every). It is harmless at daily x 15 names but is the hot path of a 40-minute suite. | Expose the engine state (position, equity) incrementally, or run the engine once with a callback. | 1 |
| A5 | Low | **Cash leg on leverage:** `pycore.py:720` gives `cash = (1-|w|)*rf`. With `|w|>1` the negative cash is financed at rf, with no spread. Shorts pay a flat `borrow_annual`, with no hard-to-borrow. live_readiness admits there is no financing model. | Add a `funding_spread_bps` applied when `|w|>1`, at a 50 bps default. | 0.3 |
| A6 | Low | `var_next` (`risk_model.py:121`) silently drops non-finite returns before the forecast. That compresses calendar time (a NaN-gap day disappears), unlike `var_forecast`, which keeps alignment. The two can disagree on the same data. | Keep NaNs and let `ewma_vol` skip them, as it already does. | 0.2 |

## (b) Methodological flaws that weaken or invalidate conclusions

| # | Sev | Finding (evidence) | $0 fix | Effort |
|---|---|---|---|---|
| B1 | High | **Purged CV is mostly theater for fixed signals.** `leakage.py:253-281` says so in its own docstring: "the training sets are not used here". The purge and embargo only matter when something is fitted. What remains is a block-mean of 5 fold ICs with t on 4 df (`_summarise`, `leakage.py:241-251`; bar 2.776). Power: at IC 0.03 across 5 names-years, a k=5 t-test is far below a HAC/Newey-West t on all non-overlapping pairs. PLAN item 5.8 and the CHANGELOG present this as "leakage rigour". Every "no alpha clears the gate" statement inherits the low power, and no power analysis is reported. | Report a Newey-West t (lag = horizon) on all pairs alongside the fold t. Add a minimum-detectable-IC line (at 80% power) per table, so a null reads "cannot detect IC < x" and not "no edge". Reserve the "purged" label for fitted things: IC-weight combination, regime and conformal. | 1.5 |
| B2 | High | **No fill-lag sensitivity on any published Sharpe** (follows from A1). The beta 0.9 / R² 0.89 finding stands, but rule-variant differences of 0.05 to 0.1 Sharpe, which are typical of the trials table, are inside the same-close bias for the short-horizon rules. | Re-run the trial table at lag 1 and re-register it as a protocol amendment, not as a new trial. | 1 (after A1) |
| B3 | Med | **The DSR benchmark is built from the dispersion of trial Sharpes** (`stats.py:154-188`). The code has an honest caveat, but the deflation counts only registered trials. Implicit trials (rule constants 0.30/0.20/0.15, the 25/50/25 blend, ATR multiples, lookbacks chosen in v0.1 to v0.5 before the registry existed) are not counted. The 62 is a floor. | Add a "pre-registry degrees of freedom" estimate (count tunable constants in the rules path), and report DSR at 62 and at 62 + that count. | 0.5 |
| B4 | Med | **Vintage = hash only.** `scripts/paper_trade_v09.py:247` records `vintage_hash(provider.frames)`; raw bars are not stored. A revision can be detected but not attributed (dividend re-adjust, split, late print), and a past session cannot be recomputed bit-exactly once Yahoo re-adjusts. With `auto_adjust=True` (`data/yahoo.py:4`), every dividend rewrites the whole history, which explains much of the 141 recomputed cells. | Commit a gzip parquet/CSV of the session's raw bars (unadjusted plus actions) under `results/paper/bars/YYYY-MM-DD/` (15 names x 2 y is about 1 MB/day), or keep the last N plus monthly. Compute adjusted series locally from raw plus actions. | 1 |
| B5 | Med | **Paper fetch 30 min after the EST close** (`paper.yml:22`, cron 21:30 UTC, which is 16:30 ET in winter). Yahoo's daily bar and volume are often not final at that point, so the job creates its own "revisions". | Move to about 23:30 UTC (still the same session date). Record the fetch timestamp and whether the bar is final (re-fetch D-1 and diff before computing D). | 0.3 |
| B6 | Med | **Forward record cannot decide** (PLAN §2: about 14 years). That is fine as a statement, but it makes the paper record operational evidence, not research evidence. Docs should stop calling it "the only unseen data" as if it could adjudicate. | Publish the min-track-record figure next to the ledger and state the decision date explicitly. | 0.2 |
| B7 | Low | **Gate multiplicity:** `passes_gate` is per (signal, instrument). There are 9 alphas x 15 names x several horizons, and no BH across the gate set (BH exists, `stats.py:194`, but is applied to evaluation tables). Any future "pass" would be false-positive prone. | Route gate decisions through BH over the full family. | 0.3 |
| B8 | Low | **Survivorship:** `validate.survivorship_statement` writes a sentence. The universe is today's 10 mega-caps, chosen with hindsight. That is acknowledged, but every equity result is conditioned on winners, which inflates B&H and thus the control. | State it in each equity table header (partly done). Nothing free fixes it at 15 names. | 0 |

## (c) Missing capabilities versus a real desk (prioritised, $0 only)

- C1. **Execution realism:** no next-open or VWAP-of-next-day fill, no stop slippage beyond a gap-at-open (`_exit_fill`), no participation cap in the backtester (the OMS has one), and the impact coefficient of 1.0 is not calibrated. A $0 calibration is possible: fit the sqrt-law coefficient to the paper OMS fills versus arrival is circular, so use the published literature value (around 0.1 to 0.3 x sigma for large caps) as a sensitivity band. (1 d)
- C2. **Portfolio-level risk limits in the OMS:** `_pre_trade` (`oms.py:507-539`) checks fat finger, collar, duplicate, hours, borrow and short cap. It has no per-name gross limit, no book gross/net, no concentration and no VaR breach check at the order level (VaR lives in the risk team, upstream). A real pre-trade gate re-checks limits at order time. (0.5 d)
- C3. **Corporate-action handling as data:** actions are fetched (`yahoo.py:108-124`) but no ex-date-aware position adjustment exists in the paper OMS (quantities in shares across a split). (Not verified end to end.) (1 d)
- C4. **Risk model:** EWMA lambda 0.94 is fixed, with no GARCH/GJR (free via `arch`, if that dependency is acceptable). There is no ES backtest (Acerbi-Szekely) and no book-level Kupiec/Christoffersen in CI on a fixed synthetic GARCH path. (1 d)
- C5. **TCA loop:** OMS shadow fills are not compared with the backtest's predicted cost per order. A desk's first live-readiness metric is predicted-versus-realised slippage. (1 d)
- C6. **Reproducible results pipeline:** a single `make results` that regenerates every published table from stored vintages, with hashes in the docs. (2 d, after B4)

## (d) Over-engineering / candidates to delete

- D1. **The C++ core** (`cpp/`, about 3 files plus bindings, C++17 `-O3`). It duplicates `pycore.py` operation for operation for daily bars on 15 names, where numpy finishes in milliseconds. It doubles the CI matrix and creates a parity-maintenance tax. Keep it as a parity demo, but stop claiming performance relevance, or delete it and the `_atcore` .pyd. If kept, add a benchmark that justifies it. (0.5 d to document; deletion 0.5 d)
- D2. **LEARN.md (143 KB), COOKBOOK.md (133 KB), CHANGELOG.md (152 KB).** These are unreviewable at this size, and the docs-versus-code drift (A2) proves it. Split them per module, and generate numbers from results files rather than hand-copying. (2 d)
- D3. **`.claude/worktrees/agent-*` copies of the whole package inside the repo directory** (grep hits many duplicate `stats.py`). If any are unignored they pollute search, coverage and packaging. Confirm they are git-ignored and prune them locally. (0.1 d)
- D4. **Stale artefacts at the repo root:** `coverage.xml` (27/09), `.coverage`, `build/`, `__pycache__/`, `agentic_trader.egg-info`. Make sure they are ignored. Coverage from September is not evidence for the "~95%" claim. (0.1 d)
- D5. **Rule-variant research on the single-name desk:** stop, as the previous review said and PLAN agreed. The remaining value is as control #3.

## (e) Code quality, tests, ops

- **mypy is advisory** (`ci.yml:35-37`, `continue-on-error: true`; `pyproject.toml:59-64` is lenient with `ignore_missing_imports`). The previous review's O4 asked for `--strict`, and what landed is non-blocking lenient. That is not a real fix. Make it blocking on `quant/`, `stats.py`, `leakage.py`, `risk_model.py` and `oms.py` first. (1 d)
- **Lockfile** (`requirements-lock.txt`): a `pip freeze` with no `--hash` entries (one "hash" match, in a comment) and "Valid for Python 3.12 only". The CI matrix runs 3.10 to 3.14 unlocked, so the published numbers are reproducible only on 3.12 and are not supply-chain pinned. Use `pip-compile --generate-hashes` or `uv pip compile` per Python, and install with `--require-hashes`. (0.5 d)
- **Coverage claim:** coverage is collected only on the numpy-backend job (`pyproject.toml` comment). C++ branches are covered only by parity tests, and the ~95% figure counts pycore, not `cpp/`. Say so in the README. (0.1 d)
- **Paper runner:** Actions is primary now, and the laptop task also commits to main (`paper.yml:7`, and `:83-90` rebases once and retries). Two writers on an append-only ledger with a retry-once race is fragile. Disable the laptop task, which memory says is pending, or make it write to a branch. A bot pushing straight to main under a ruleset with 9 required checks means either the bot bypasses the ruleset (document it) or pushes fail. (0.3 d)
- **Tests:** 63 test files, plus 55 skip/xfail/flaky markers worth auditing. Property tests exist (hypothesis directory). Missing: a lag-1 no-lookahead property on the engine (A1), a holiday table test (A3), and a Newey-West power test (B1).

## (f) Previous-review fixes: real or not

| Prev item | Status |
|---|---|
| R6 EWMA/FHS VaR, factor exposure, stress, book VaR on | **Real** (`risk_model.py:45-135`, 138-232). Default-mismatch bug A2. |
| R7 vintage per session | **Half.** Hash only, no stored bars (B4). |
| 5.8 purged CV and canary | **Canary real** (`leakage.py:458`). Purged IC mostly cosmetic for fixed signals (B1). |
| O1 Actions runner, freshness, issue | **Real** (`paper.yml`). Dual-writer risk remains. |
| O2 flaky test, suite split | Partly (`-m "not slow"`, nightly.yml). Not verified that the flake was fixed. |
| O4 ruff + mypy strict, SHA pins | ruff and SHA pins real. **mypy not real** (advisory, lenient). |
| Q7 cost model (stop slippage, financing) | Not fixed (A5, C1). |
| Q4 horizon from decay | Not fixed. Rebalance remains 5 bars by fiat (not verified in alpha.py). |

## Top 10 (do in this order)

1. **A1/B2** Add execution lag and next-open fill to both engines. Re-run trials at lag 1 as a protocol amendment. (2.5 d) High.
2. **B1** Add a Newey-West t on all pairs and a minimum-detectable-IC per table. Stop calling fixed-signal fold ICs "purged CV". (1.5 d) High.
3. **B4** Store raw unadjusted bars plus actions per paper session and derive adjustments locally. (1 d) Med.
4. **B5** Move the paper cron to about 23:30 UTC and add a D-1 finality re-check. (0.3 d) Med.
5. **mypy blocking** on the quant core modules. (1 d) Med.
6. **Hashed per-Python lockfiles**, with CI installing `--require-hashes`. (0.5 d) Med.
7. **A2** One VaR default constant, fix live_readiness.md, plus an agreement test. (0.2 d) Med.
8. **A3** NYSE one-off closures and early-close table, with tests. (0.5 d) Med.
9. **C2** Book gross/net/concentration plus an order-time VaR check in OMS `_pre_trade`. (0.5 d) Med.
10. **B3 + B7** DSR with a pre-registry DoF estimate, and BH over the gate family. (0.8 d) Low-Med.

Total is about 9 wall-clock solo days. Deletion candidate: the C++ core, unless a benchmark justifies it (D1).
