# Publishing this documentation with GitHub Pages

The `docs/` folder is ready for GitHub Pages. `docs/index.html` is a self-contained static
landing page: no build step, no Jekyll configuration and no external assets. Every link on it
points at Markdown rendered on GitHub, so nothing else needs generating.

## One-time setup

1. Push the repository to GitHub (`AshJha0/agentic-trader`). If you use a different
   repository name, update the hard-coded links in `docs/index.html` (search for
   `AshJha0/agentic-trader`) and in this file.
2. On GitHub, open **Settings → Pages → Build and deployment** and set:
   - Source: *Deploy from a branch*
   - Branch: `main`, folder: `/docs`

   Or use the CLI:

   ```bash
   gh api -X POST repos/AshJha0/agentic-trader/pages -f "source[branch]=main" -f "source[path]=/docs"
   ```
3. The site appears at `https://ashjha0.github.io/agentic-trader/` within a minute or two.
   The Actions tab shows the `pages build and deployment` job; `gh api
   repos/AshJha0/agentic-trader/pages/builds/latest` reports its status.

The landing page is plain HTML, so Jekyll does not affect it. If you ever add files whose
names begin with an underscore, add an empty `docs/.nojekyll` so Pages serves them.

## What gets served

| URL | Content |
|---|---|
| `/` | `docs/index.html`: the landing page (what changed in the current release, numbers block, honesty note, the three layers, the current out-of-sample tables with the earlier ones folded below, component cards, a sample audited task, quick start) |
| Everything else | Linked to Markdown rendered on github.com: `LEARN.md`, `COOKBOOK.md`, `docs/architecture/overview.md`, `docs/DIAGRAMS.md`, `docs/SPECIFICATION.md`, `docs/threat-model/threat-model.md`, `docs/evaluation/evaluation.md`, `docs/api/api.md` |

The Mermaid diagrams in `docs/DIAGRAMS.md` render natively on github.com; no plugin is
needed.

## Keeping the landing page honest

`docs/index.html`, `README.md`, `LEARN.md` and `docs/evaluation/evaluation.md` quote real
measured numbers. Since v0.8 every real-data number comes from one place: `results/v08/`,
written by `scripts/measure_v08.py` and turned into the markdown tables by
`scripts/render_v08_tables.py`. Nothing in those files is typed by hand. If you change the
code, re-run the driver and re-render; if you change a document, re-check its numbers against
these sources:

| Figure | How to re-measure |
|---|---|
| Every real-data table (per-instrument summaries, head-to-head, paired tables, portfolio views, cash leg on/off, drawdown against the control, impact sweep, execution algorithms, EDGAR / carry / rules / xalpha / alpha / track-record re-checks, VaR coverage, selection statistics, rebalance-phase sweep) | `.venv\Scripts\python.exe scripts/measure_v08.py` (about an hour on the C++ backend with 4 workers; `results/v08/measure.log` records `eval_main: done in 312s` for the headline run, `eval_xalpha: done in 1727s` for the slowest, and `all done in 3787s` for the whole script on its first complete run (the three later `all done` lines are the partial re-measurements); `--only eval_main,portfolio_holdout,...` or the stages `var_coverage`, `trials`, `phase_sweep` for a subset; a run whose output exists is skipped, so re-running fills gaps; every run gets the shared downloads under its own settings through `provider_for()`), then `.venv\Scripts\python.exe scripts/render_v08_tables.py` (prints every table and writes `results/v08/tables.md`; `--section` for one). Yahoo, FRED and SEC EDGAR (`EDGAR_USER_AGENT` in `.env`) are needed. A document quotes a number only by copying it from `tables.md` (or, when the renderer does not print it, from the named JSON/CSV) |
| Provenance of a number | Every `results/v08/*.json` carries `provenance` (package version, git commit and dirty flag, quant backend, Python, platform, dependency versions) and every `--out` CSV has a `<stem>.provenance.json` sidecar; `results/v08/manifest.json` records the run. A table whose provenance does not name the commit under test is not evidence for that commit. The published v0.8 files were written at three commits of identical engine, data and rules code (`git_dirty: false` in every file; the evaluation's Reproducing section lists which file came from which). Seven of them were re-measured: five (`eval_noedgar`, `eval_cash_leg_off`, the two `portfolio_*_cash_leg_off` files and `trial_edgar_filings_off`) because of a driver defect: the first run handed one shared Yahoo provider to every run, and because `edgar` and `cash_leg` are read from the provider's own config those "off" runs still had EDGAR and the cash leg on (their `meta["edgar"]` recorded `True`; their tables showed zero difference on every instrument, which is what exposed it). The fix is `MarketDataProvider.reconfigured(config)` (same downloaded bars, its own settings) and `provider_for()` in the driver, pinned by `tests/test_v08_fixes.py::test_36_a_reconfigured_provider_shares_the_downloads_under_its_own_settings` and `tests/test_v08_protocol.py::test_measurement_driver_reconfigures_the_shared_provider_for_provider_level_overrides`. An on/off table in which every instrument's difference is exactly zero is a sign of this defect, not a result. The other two, `eval_rules_v03` and `eval_rules_v02`, were re-run at `ac727ce` only because the first run's files had been stamped `git_dirty: true` by documentation edits made while the driver was running (`results/v08/measure.log`, re-measurement 4); the log prints the same per-instrument Sharpe on every row of both runs |
| Dependency versions behind a re-run | `pip install -r requirements-lock.txt` before reproducing, so a discrepancy is data drift or a code change, not a different numpy/pandas resolution. The lock is the full transitive freeze of the environment that produced the v0.8 numbers (CPython 3.12.10, win_amd64, 2026-09-27) and is valid for **Python 3.12 only** (numpy 2.5.3 requires ≥ 3.12); CI's `lock` job installs from it and runs the suite; see [the evaluation's Reproducing section](evaluation/evaluation.md#reproducing) |
| Test counts and coverage | `pytest --collect-only -q` on both backends (879 collected on either backend at v0.12.0: C++ backend 879 passed, numpy backend 839 passed and 40 skipped; 832 on both at v0.8.0; the per-file breakdown in README and `index.html` is the same listing grouped by file); the suites themselves: C++ backend 832 passed, numpy backend 796 passed and 36 skipped (the C++-only tests); `pytest --cov=agentic_trader` on the numpy backend for the line coverage (95% at v0.8.0, weakest file `data/yahoo.py` 75% for its network branches); the `void test_` functions in `cpp/tests/test_core.cpp` (25 at v0.8.0, run as the single `ctest` test `at_core_tests`) |
| CI jobs | `.github/workflows/ci.yml`: `python` (5 versions, 3.10–3.14, numpy backend), `lock` (3.12 from the lock file), `cpp` (3 OSes), `docs` |
| Decision and task latency | Time `TradingGraph(...).propagate("AAPL", "2024-03-01")` and `AgentHarness(graph).run(Task("AAPL", date(2024, 3, 1)))` over 20 runs after one warm-up run, offline, C++ backend |
| Evidence, findings, steps, checks and spans per task | `run.to_dict()` of the task above: `evidence_count`, `len(findings)`, `len(plan.steps)`, `len(critic.checks)`, `trace.spans` |
| Tools and servers | `len(harness.registry)` and `harness.registry.servers()` (or `agentic-trader tools`): 16 tools on 5 servers at v0.8.0 |
| Knowledge documents and chunks | `len(default_knowledge_base().documents)` and `len(default_knowledge_base().chunks)`: 11 documents, 76 chunks at v0.8.0 (the knowledge documents were rewritten in the docs pass, so the chunk count moved) |
| LLM calls per decision | Cookbook recipe 17 (prints `14 4 10` at default rounds) |
| Real-price evaluation (per instrument, design / holdout / Q1 2024 / reserve), all 60 instruments | `measure_v08.py --only eval_main` (`agentic-trader evaluate --data yahoo --universe all --periods design,holdout,q1_2024,reserve --out results/v08/eval_main.json` is the same run); `--only eval_rules_v02` for the v0.2 "before" column on the core universe, `eval_rules_v03` for the FX carry rule off; tables by `universe` from `EvaluationResult.summary` / `paired_table` (the `scheme` column says whether the cluster bootstrap engaged: `clusters` needs 5 groups, i.e. `--universe all`) |
| Cash leg | `measure_v08.py --only eval_cash_leg_off,portfolio_design_cash_leg_off,portfolio_holdout_cash_leg_off` beside the defaults. The convention (`cash_leg: auto`, the default on real-data providers): equities are funded, so `(1 - |w|)` of the account earns the 3-month bill (FRED DTB3, one-day publication lag); FX forwards earn it on the whole account; Sharpe, Sortino and t are on returns in excess of that bill while annualised return, cumulative return, drawdown and Calmar stay total-return. `cash_leg: off` credits nothing and the metrics use the constant `risk_free_annual` (0), i.e. the v0.7 convention, so the difference between the two files is what idle cash at the point-in-time bill is worth to each strategy and what an excess-return Sharpe costs it. The README headline quotes the cash-leg-on numbers and says the ranking is the same under either convention. Synthetic-provider numbers do not move (the rate is the constant 0). These runs are provider-level overrides and need the driver's `provider_for()` (see Provenance) |
| Impact sweep | `agentic-trader evaluate --data yahoo --universe core --periods design,holdout --impact 1.0 --capital <1e5 / 1e7 / 1e9>` (parses since v0.8; `measure_v08.py --only eval_impact_1e5,eval_impact_1e7,eval_impact_1e9` is the same); the coefficient is now scaled by the equity actually traded |
| Execution algorithms at $1B | `measure_v08.py --only portfolio_holdout_impact_1e9_vwap,portfolio_holdout_impact_1e9_twap,portfolio_holdout_impact_1e9_ac`: each sleeve pays the impact of its own capital share |
| Ablation tables and selection statistics | The trials registry `evaluation.TRIALS` (26 variants, `reproducible_trials()` the 24 the current engine can re-run), each with `evaluate(periods={"design": PERIODS["design"]})` on the core universe — `measure_v08.py --only trials` writes `trial_*.json` and `trials.json`; `stats.selection_report(portfolio design returns, the trials' mean Sharpes)` in `render_v08_tables.py` |
| Portfolio results and their intervals | `measure_v08.py --only portfolio_design,portfolio_holdout` (equal weight, core 15; `agentic-trader portfolio <15 symbols> --data yahoo --start 2022-01-03 --end 2026-06-30 --out ...` is the holdout run); `PortfolioReport.sharpe_difference` for the desk − vol-target and desk − B&H intervals; `--only phase_sweep` for the rebalance-offset noise floor (offsets 0–4) |
| VaR coverage | `measure_v08.py --only var_coverage` → `var_coverage.json`: the rolling historical VaR of the portfolio's own returns at 120 / 250 days and the desk's per-instrument 250-day forecast against each core instrument's next-day return over the holdout (Kupiec and Christoffersen p); `agentic-trader stats returns.csv --var-backtest` for any series |
| LLM desk vs rules (Q1 2024, 5 stocks) | `agentic-trader evaluate AAPL,NVDA,MSFT,META,GOOGL --data yahoo --periods q1_2024 --every 10 --rounds 1 --llm anthropic --deep-effort medium --max-llm-calls 400 --anonymize --workers 3` (API key, ≈$4) and the same without `--llm anthropic`. The one published LLM result (v0.5.1) was measured under the pre-v0.8 engine and has not been re-derived |
| Code size | Non-empty lines in `agentic_trader/**/*.py`, `tests/**/*.py` and `cpp/**/*.{cpp,hpp}` |
| Cookbook | `python scripts/run_cookbook.py` (every ```python block in a fresh process; `--offline` skips the network recipes, which is what CI runs); all must exit 0 |
| EDGAR coverage | `EdgarClient(cache_dir=...).fundamentals(t, date, price, splits)` and `.news(t, date, 90)` for every equity in `UNIVERSES["all"]` at two dates; operating companies must report growth, margin, EPS, leverage and FCF yield where the guards allow it (margin only when the revenue and net-income windows end together, FCF yield only when the OCF and capex windows do, per-share ratios behind the 400-day instant and share-class checks, a lagging live window served flagged by `*_period_end`), funds and index ETFs nothing. `tests/test_v08_data.py::test_cached_filers_offline_regression` pins the served figures for the cached filers at fixed cutoffs; the reconstruction rule changed in every v0.8 fix round, so any EDGAR-on table must carry the provenance of the commit that produced it |
| EDGAR-on vs EDGAR-off, cross-sectional analyst, alpha analyst, track-record cut | `measure_v08.py --only eval_noedgar` / `eval_xalpha` / `eval_alpha` / `eval_no_trackrecord_cut` against `eval_main`; paired bootstraps from `EvaluationResult.paired_table()` with the BH flag |
| Multi-year LLM desk | The staged runner in the evaluation (control, Opus, Sonnet, Haiku tiers on the core universe over design + holdout at `--every 10`, three repeated Opus runs on five stocks, one calibration run), each stage with its own `--max-llm-cost`. Not run as of v0.8.0 |
| Cross-sectional analyst activity | `TradingGraph(make_config(analysts=["technical", "fundamentals", "news", "sentiment", "xalpha"], xalpha_universe=UNIVERSES["all"])).propagate(sym, d)` every 60 business days over the design period on the 15 core names; share of `reports["xalpha"]` not abstained |
| Calibration | `agentic-trader calibrate AAPL --date 2024-03-01 --n 5 --anchors none,-0.5,0,0.5 --llm anthropic --anonymize --deep-effort medium` |
| Fuzz findings | `pytest tests/test_fuzz.py`; the "found and fixed" list in the changelog is the record of what the first run caught |
| Diagrams | `python scripts/check_mermaid.py` (mermaid-cli; `--html` writes `build/mermaid_check.html`, open it and read `window.__mermaid`) |
| Links | `python scripts/check_links.py` (`--external` also requests every external URL) |

The evaluation tables are generated from the saved JSON by `scripts/render_v08_tables.py`
(earlier sections: pandas `to_markdown` from the JSON of their day), not typed by hand. Keep
it that way. The historical sections of the evaluation keep the numbers measured under the
earlier engines, each under a banner saying so; the v0.8 section is the current measurement.

The real-data numbers quoted in `README.md`, `docs/index.html`, `LEARN.md` and the
evaluation are only as current as the last render of `results/v08`: after any re-run of the
driver, re-render and re-paste before publishing. The render script's output is the
reference; a document that disagrees with it is the one that is wrong.

A wrong number on the landing page is a documentation bug. Treat it like one.
