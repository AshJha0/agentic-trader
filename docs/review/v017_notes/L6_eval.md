# L6 - R3 evaluation credibility (review findings B2, B5, C1)

Branch `worktree-agent-a850e7af9527501ed`, based on `feat/v0.16-round2` at ae26242. No model was
called and nothing was downloaded.

## R3.1 (B2) judge credibility

**What changed.**

- New module `agentic_trader/agentic/judge_kit.py`.
  - `resolve_judge_model(judge, judged, allow_same_family=False)`. The judge is now a separate
    setting. Its default is `DEFAULT_JUDGE_MODEL = "llama3.1:8b-instruct-q4_K_M"`, Meta's Llama 3.1
    8B at 4-bit, which is a different open-weight family from the judged `qwen2.5:7b-instruct`. A
    judge from the judged model's family (`model_family()`: the tag name with version digits
    removed) raises `JudgeConfigError` unless same-family is explicitly allowed.
  - Labelling kit: `sample_replies` (stratified by the checker's verdict pattern, with equal
    shares per pattern and a fixed seed, shuffled so row order hides the stratum), `write_sheet`
    (writes `labels.csv` to fill in, `sheet.html` to read, `INSTRUCTIONS.txt`, and `key.json` with
    the checker verdicts so the labeller stays blind), `import_sheet` (rejects cells that are not
    1/0/yes/no and rows whose item does not match the key; a blank cell means "undecided" and is
    counted), `agreement_report` (Cohen's kappa per criterion with a 95 % percentile bootstrap
    CI, for checker vs human and for judge vs human), and `write_calibration` (the
    `calibration.json` row shape).
- New script `scripts/v17_label_kit.py` with `sheet` and `import` subcommands.
- `scripts/v16_eval.py`: a minimal change, all of it inside the `judge` subcommand.
  - New flags `--judge-model` (default llama3.1:8b-instruct-q4_K_M), `--judged-model` (default
    qwen2.5:7b-instruct) and `--allow-same-family`.
  - `cmd_judge` resolves the model before it builds the LLM. In `judge`, `--model` is now
    overridden by `--judge-model`.
  - The judge `.meta.json` records `judge_model` and `judged_model`.
  - `run`, `check`, `agreement` and `freeze` are untouched, so L1's freeze is not affected.
- No real replies are in the repo yet (`results/v16_eval/run.jsonl` does not exist; it comes from
  the queued eval run). So the kit is tested on a synthetic fixture run built in the test, and a
  sheet built with `--fixture` is marked `fixture:` in key.json. `sheet --replies` refuses to
  write fewer than 100 rows.

**Evidence class.** Code and tests only. No kappa number exists yet: it needs the real run, then
the owner's labels.

**Commands to queue (owner / maintainer).**

```
ollama pull llama3.1:8b-instruct-q4_K_M          # ~4.9 GB, free; OD-D in the plan
# after the v0.16 eval run has produced results/v16_eval/run.jsonl (qwen2.5:7b-instruct):
python scripts/v17_label_kit.py sheet --replies results/v16_eval/run.jsonl --out results/v17_labels
#   owner: read results/v17_labels/sheet.html, fill labels.csv (about 2-3 h for 100 rows)
python scripts/v16_eval.py judge --replies results/v16_eval/run.jsonl \
    --judge-model llama3.1:8b-instruct-q4_K_M --judged-model qwen2.5:7b-instruct \
    --out results/v17_eval/judge_llama.jsonl
python scripts/v17_label_kit.py import --sheet results/v17_labels --labeller owner \
    --judged results/v17_eval/judge_llama.jsonl --out results/v17_labels/agreement.json \
    --calibration-out results/v17_labels/calibration_real.json
# optional cross-judge check (same-family on purpose, labelled as such):
python scripts/v16_eval.py judge --replies results/v16_eval/run.jsonl --judge-model qwen2.5:7b-instruct \
    --allow-same-family --out results/v17_eval/judge_qwen.jsonl
```

The judge run covers all 150 replies. `import` matches judge rows to sheet rows by item id. To
judge only the 100 sampled replies, filter `run.jsonl` by the `item_id` values in key.json first.

## R3.2 (B5) retrieval question set v2

**What changed.**

- `agentic_trader/agentic/question_overlap.py`, `lexical_overlap(question, passage)`. A question
  is rejected if it shares any content bigram (rag tokenizer, stop words dropped) with its gold
  passage text, or if more than 0.34 of its content unigrams appear in the passage. Ticker and
  section names are passage metadata, not passage text, so a question may name the company.
- `agentic_trader/agentic/knowledge/retrieval_eval/questions_v2.json` has 100 questions over the
  in-repo fixture corpus (34 passages). They are paraphrased away from the passage wording; gold
  ids, accessions and `as_of` values are taken from the old set; every gold passage is covered (2
  to 4 questions each). All 100 pass the overlap check. The old fixture set fails it on 85 of 100.
- `scripts/v17_retrieval_eval.py` refuses to report if any v2 question fails the check. It
  evaluates tfidf and hybrid on both sets and writes `docs/results/v17_retrieval/retrieval_v1_v2.json`
  and `.meta.json`.
- The retrieval gate (`analyst_retriever`) still uses the old set. I did not change it; that is a
  decision for the maintainer (see follow-ups).

**Numbers** (synthetic fixture corpus, offline, deterministic; a test pins them):

| set | method | n | recall@5 | MRR | accession recall@5 | gate >= 0.8 |
|---|---|---|---|---|---|---|
| v1 (old, 85/100 overlap-rejected) | tfidf | 100 | 0.990 | 0.954 | 0.990 | pass |
| v1 | hybrid | 100 | 0.990 | 0.961 | 1.000 | pass |
| v2 (paraphrased, 0/100 rejected) | tfidf | 100 | 0.740 | 0.422 | 0.850 | FAIL |
| v2 | hybrid | 100 | 0.820 | 0.475 | 0.850 | pass |

Reading. Once the wording is independent, tfidf drops below the 0.8 gate and hybrid only just
clears it; MRR roughly halves. This supports B5: the old number mostly measured lexical overlap.
The corpus is tiny (34 passages, at most 34 visible per question), so recall@5 has a high chance
floor (about 5/34 = 0.15 for a random ranker), and the true gap on a realistic corpus is likely
larger. Evidence class: synthetic fixture.

**Not done: the real-EDGAR set.** `results/edgar_text_cache` is not on this machine (git-ignored;
not in the round-2 checkout or the main checkout; I did not look in AgenticTrader-v16, per the
lane rules). So the 50-question real set (0.92/0.98) could not be re-run, and I did not write
real-EDGAR v2 questions: I could not see the gold passage text, so I could neither check them for
answerability nor run the overlap check on them. Follow-up, on the machine that holds the cache:
write paraphrased EDGAR questions with `question_overlap.lexical_overlap` against
`corpus.get(gold).text`, then run `scripts/v15_edgar_design.py rag` on both sets.

## R3.3 (C1) eval-regression gate

- `agentic_trader/agentic/eval_gate.py` and the baseline file
  `agentic_trader/agentic/knowledge/eval_set/eval_baseline.json`. The baseline records
  `prompt_bundle_hash` (00f090781c114a97), the sha256 of the frozen items (CRLF normalised), a
  hash of the judge prompt, and the checker's exact verdict and agreement counts on the 30
  recorded calibration replies (for example no_invented_numbers 27/30 agree with the labels).
- `tests/test_v17_eval_credibility.py::test_eval_regression_gate` is fast and deterministic. It
  fails when any recorded field drifts, and the failure message prints the update command.
  Further tests show that a hash change is caught, that an edit to a real agent `role` changes
  the hash, and that re-recording requires a reason and keeps a history.
- How to update the baseline deliberately (COOKBOOK recipe text for the maintainer):

  > **Recipe: changing a prompt without tripping the eval gate.** Edit the prompt. Re-freeze the
  > items if the analysts' prompts changed (`python scripts/v16_eval.py freeze`). Re-run the eval
  > on a local model (`v16_eval.py run` then `check`) and compare it with the last run. Then
  > record the new baseline with a reason that names the run:
  > `python scripts/v17_eval_baseline.py --update --reason "trader prompt v3; checked by results/v17_eval/run.jsonl, all_three 61 -> 63"`.
  > `python scripts/v17_eval_baseline.py` with no flags checks for drift (exit 1).

- Limitation. The gate ties the prompt hash to a recorded decision. It cannot check that the
  model score did not fall, because CI has no model. The `reason` field is where the human
  records that check.
- Interaction with other lanes. Any lane that edits prompts, analyst classes or the
  prompt-helper code will fail this test until the baseline is re-recorded. The maintainer should
  re-record once after merging all lanes, with the reason "v0.17 merge".

## Tests and checks

- `tests/test_v17_eval_credibility.py` (new, 17 test cases) together with `tests/test_v16_eval.py`
  and `tests/test_v15_rag.py`: 49 passed, 1 skipped (the skip is pre-existing).
- `ruff check agentic_trader scripts/paper_ops.py tests` and the new scripts: clean.
- mypy (global C:\Python312) on the three new modules: no issues.
- Regression for B2: `test_cli_judge_refuses_same_family_and_records_models` fails on the old
  code, which has no `--judge-model` flag and no family check.

## Follow-ups

1. Real-EDGAR v2 questions and re-run (needs the cache), as described above.
2. Maintainer decision: should `analyst_retriever` gate on v2 (tfidf would then fail the gate on
   the fixture), or on both sets?
3. Re-record `eval_baseline.json` after the v0.17 lanes merge.
4. Queue the llama pull and the judge and label commands above once `run.jsonl` exists.
