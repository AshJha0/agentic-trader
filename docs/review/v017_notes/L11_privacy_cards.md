# L11: privacy, conformal and model cards (review N2, N7, N8, N10, N11)

Base: feat/v0.16-round2 @ 1237706. No model runs, no network, $0.

## N2 (high): text analysts now go through the anonymiser
- `graph.py`: one call-site change, `text_reports(..., anon=state.anon)` (plus one line for N8, below).
- `text_analysts.py`: `FundamentalsTextAnalyst(llm, anon=)` and `MacroTextAnalyst(llm, anon=)` scrub the
  company line, accession numbers, acceptance timestamps and the filing / statement text with
  `Anonymizer.scrub_text`. Quotes are verified against the scrubbed text the model saw; cited `ACC_n`
  is mapped back to the real accession for the audit trail. Report points stay aliased (they are
  quoted by later agents); real accessions stay in `facts["sections"]` (not on the facts allow-list,
  so never in a prompt). EDGAR `name`/`formerNames` extend the name map (`EdgarProvider.company_names`,
  reads the already-cached submissions JSON).
- `anonymize.py`: `scrub_text` adds own company names (built-in map for the research universe +
  EDGAR names, with suffix-stripped stems) -> `COMPANY_X`, product names -> `PRODUCT_X`, other universe
  tickers (>= 2 letters) and their names -> `OTHER_CO`, written / US-style dates -> `D` offsets,
  "Month YYYY" -> `M` offsets, bare years 1950-2099 -> `Y` offsets. `scrub` (price path) additionally
  rewrites accession numbers (`ACC_n`), CIKs (`CIK_X`) and ISO timestamps with a time part; none of
  these occur in price-path prompts, so price-path prompts and fixture hashes are unchanged (test).
- Residuals (documented in the module docstring): names outside the map, one-letter tickers (V),
  filing wording, company names in price-path headlines (scrub leaves names alone on purpose, so
  P2 prompt hashes do not move; follow-up below).
- Evidence class: fixture. The 3.8 local text-analyst result (`docs/results/v15_local/text_analysts.json`)
  ran de-anonymised and should be labelled so.

## N8: remote model hosts and forced anonymisation
- `local_llm.py`: a non-loopback `local_llm_url` (anything but `localhost`, 127.0.0.0/8, ::1; other
  names are not resolved and count as remote) raises unless `allow_remote_llm: true`. Every call's
  evidence (`last_call`) now carries `llm_host` and `remote_llm_allowed`.
- `anonymize.enforce_llm_anonymize` called from `TradingGraph.__init__` when a model is attached:
  sets `llm_anonymize: True` with a warning and `llm_anonymize_forced: True`, unless
  `allow_deanonymized_llm: true` (deliberate control run). Written back into the config, so
  evaluation/calibration `anonymized=` evidence records what ran. Rules path default unchanged (False).
- New config keys: `allow_remote_llm`, `allow_deanonymized_llm` (both False).
- Note for L1: `last_call` dict gained one `update(...)` line after the evidence dict in `read_response`.

## N7: conformal calibration
- `combine.calibration_points` (v17 default: stride `h` counted back from `end - h`, so no overlap;
  regime mask applied when regime conditioning is on) and `combine.conformal_interval` (v17:
  residuals divided by the horizon vol at their own bar, quantile scaled by today's vol). Config
  `conformal.design` = "v17" (default) or "v14" (old: every bar, raw residuals).
- The registered trial "v0.14 IC combination + conformal interval sizing" is pinned to `design: "v14"`
  in `evaluation.TRIALS`, so its recorded result still describes its config.
- Dependent-data test (fixture, GARCH(1,1) with t(6) innovations, 6 seeds, h = 5, alpha 0.2, window
  250, 654 forecasts, 169 in the top-vol quartile): coverage overall v14 0.760 / v17 0.778; top
  quartile v14 0.675 / v17 0.882 (target 0.80). v17 over-covers in high vol; under-coverage gone.
- Re-run of the registered design trial NOT done: `scripts/v14_design_trials.py` downloads Yahoo data
  (network), which the lane rules forbid. `docs/results/v17_conformal/` not created. To queue (rules
  only, no model; it skips existing files so use a fresh dir):
  `PYTHONPATH=. .venv\Scripts\python.exe scripts/v14_design_trials.py --out results/v17_conformal`
  after adding a v17 variant (trial with `"conformal": {"enabled": True, "design": "v17"}`; registering
  it adds one trial to the deflated-Sharpe count, maintainer decision).

## N10: docs/models/
`INVENTORY.md` plus 9 model cards (rules analysts, LLM roles, qwen2.5 local, planned llama3.1 judge,
retrieval, IC combination, HMM regime, conformal, VaR) and 4 dataset cards (Yahoo, FRED/ALFRED, EDGAR,
fixtures). Every number cites its source file / PLAN row and evidence class. `DATA_LICENSING.md` does
not exist on this base; the cards point to it (another lane owns it). Maintainer: link INVENTORY.md
from docs/INDEX.md.

## N11: dev API keys and the temp config
- `serve_options` refuses the shipped dev keys on every host, loopback included, unless
  `allow_dev_keys` / `--allow-dev-keys`. `create_app` (tests) is unchanged.
- Multi-process serve: the temp JSON config is written with secrets redacted (`split_secrets`:
  `api_keys`, `*_secret`, `*_token`, `*password`, `*api_key`); the secrets travel in the
  `AGENTIC_TRADER_APP_SECRETS` environment variable inherited by workers and removed afterwards;
  `app_factory` merges them back.
- Changed old tests that encoded the previous behaviour: `tests/test_v05.py` (loopback with dev keys
  now refused), `tests/test_v06.py` (serve calls pass the dev flag).

## Tests
`tests/test_v17_privacy_conformal.py` (14 tests). Targeted run: v17 + test_v05, v06, v15_text, v15_security, v14_combine, v14_research_cache, v14_local_llm, services, agents, adversarial, v08_agents: 558 passed after updating two old assertions (test_v05 serve CLI now passes --allow-dev-keys; test_v14_local_llm evidence dict has llm_host / remote_llm_allowed). Full suite not run (exceeds 10 min).

## COOKBOOK recipe (text for the maintainer)
**Run a de-anonymised control.** Any run with a model is anonymised automatically. To measure how much
the model relies on recognising the company, run the same cell twice: once as is, once with
`{"allow_deanonymized_llm": true, "llm_anonymize": false}`. Compare the two; a gap is memory, not
reasoning. Check the run's evidence shows `anonymized: false` only on the control.

## Follow-ups
1. Price-path headlines still carry company names; switching `scrub` to the name map changes P2
   prompt hashes, so do it at a version boundary.
2. Real-data v17 conformal coverage and the design trial (above).
3. Re-label the 3.8 local text-analyst result as de-anonymised in what_the_model_adds.md.
