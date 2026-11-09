# v0.17 lane L8: remaining quant and ops findings

Branch `lane/L8-quant-rest`, based on `feat/v0.16-round2` @ ae26242. $0, no network, no model
calls. Engine loops (`backtest.py`, `pycore.run_backtest_ex`), `oms._pre_trade`/calendar,
`stats.py`, `leakage.py`, `paper_trade_v09.py`, `ci.yml` and risk-model defaults were not
edited; every new piece is a new module, and the one-line hooks other lanes' files need are
listed under "Hooks for other lanes".

## What changed, item by item

| Item | Change | Files | Tests | Evidence class |
|---|---|---|---|---|
| A5 financing spread | `financing_drag(w, funding, cash)` = `max(\|w\|-1,0)*s_b + max(1-\|w\|,0)*s_c`; `apply_financing(result, ppy, ...)` takes it out of each bar's return after a run (exact at zero costs, first-order otherwise: error = drag x cost, ~1e-9 a bar); `run_backtest_financed(...)` is the engine entry point with the parameter. Defaults: `DEFAULT_FUNDING_SPREAD_BPS = 50` (convention, not measured), cash spread 0 so unlevered results do not move. | `agentic_trader/financing.py` | 3 | convention + tested arithmetic |
| A6 var_next NaN policy | Policy = **keep alignment**: non-finite returns stay in place (inf becomes NaN) so the trailing window covers the same calendar span as `var_forecast`; only the finite count gates `None`. Agreement: `var_next(r) == var_forecast(append(r, x))[-1]` for all three methods across a NaN month and an inf. Regression test fails on the old code (FHS window moved back over dropped days). Signature untouched (L1 owns the default). | `agentic_trader/risk_model.py` (body of `var_next` only) | 4 | tested |
| B6 forward record | `evidence_bounds.decision_horizon`: n = 1,167 x (0.35/d)^2; d = 0.2 gives **3,574 sessions, 14.2 years, look on 2040-12-19** (NYSE sessions from 2026-09-29); d = 0.5 gives 572 sessions, 2.3 years, 2029-01-05. New section "Forward paper record: operational evidence, decision in 2040" in `docs/evaluation/live_readiness.md`. | `agentic_trader/evidence_bounds.py`, `docs/evaluation/live_readiness.md` | 1 | arithmetic on pre-registered numbers |
| B8 survivorship | Strict survivorship (point-in-time top-N by market cap) **cannot be measured with free data**: no free source here gives historical shares outstanding or delisted names. Measured instead, on the published holdout buy-and-hold rows (2022-01-03 to 2026-06-30, `docs/evaluation/evaluation.md` "Holdout per instrument"), the premium of the nine hindsight-chosen names over SPY: **mean CR +72.5 pp (138.6 % vs 66.1 %, +8.4 %/yr annualised), median CR +2.2 pp, mean Sharpe -0.06.** Reading: hindsight selection lifts an equal-weight buy-and-hold control's mean return by up to ~8 %/yr on that window, almost all from one name (NVDA +566 %), and does not lift the typical name's Sharpe. Since the desk is compared with B&H vol-target per name and summarised by median Sharpe, the bound on the comparison is small; the bound on any absolute equity return is large. This is an upper bound (it mixes selection with luck). Design-period equivalent needs SPY's design CR (network; queued below). | `agentic_trader/evidence_bounds.py` | 1 | measured (v0.7-engine table, B&H rows only) |
| C1 execution realism | (1) `stop_fill_with_slippage`: intrabar stop fills at `stop*(1-half_spread) - range_frac*(stop-low)`, floored at the low; gap fills at open less half spread; both 0 reproduces `pycore._exit_fill` (tested). `stop_slippage_frac` gives the extra loss over the engine's fill. (2) `cap_participation`: weight path limited to `cap*ADV*price/equity` per bar, residual carried; `participation_shortfall` summarises the lag. (3) Corwin-Schultz (with overnight adjustment, floored and unfloored) and Abdi-Ranaldo estimators; `spread_consistent_y` = half spread / (daily vol x sqrt(0.01)); `calibrate_impact` per symbol. | `agentic_trader/execution_realism.py`, `scripts/v17_costs.py`, `docs/results/v17_costs/estimator_validation.{md,json}` | 5 | simulation |
| C3 corporate actions | `apply_actions(positions_in_shares, actions, through, after, prices)`: ex-date-ordered splits (`q*k`, cash in lieu for fractional remainders at a given price, refusal without one) and dividends (`q*D`, shorts pay); returns positions, cash and an audit list; `cash_flow_rows` in `OMS.cash_flows` shape. | `agentic_trader/corporate_actions.py` | 3 | tested |
| C4 GJR-GARCH, ES, book coverage | `fit_gjr` (Gaussian QMLE; SciPy Nelder-Mead when importable, own Nelder-Mead otherwise; SciPy is not installed in the venv and not added), `gjr_var_es_forecast` aligned like `var_forecast`, `simulate_gjr`, Acerbi-Szekely Z2 and a simulated one-sided p-value. CI test: 3-name book on fixed GJR paths, GJR VaR passes Kupiec (p 0.53) and Christoffersen (p 0.040 > 0.01 bar; a weighted sum of GJR paths is only close to GJR), ES passes Z2; half-size VaR/ES rejected by both (p < 0.001). Fit recovers persistence within 0.05 on 3,000 days. | `agentic_trader/garch.py` | 4 | simulation |
| C5 TCA | `tca_rows(orders, arrival, predicted)`: realised = q*s*(fill-arrival) + fees, predicted scaled to the filled part, slippage in bp, fill ratio; `tca_summary` notional-weighted. A real `OMS` fill against the backtester cost gives 0 bp (the OMS fills at the reference, so today the report measures rounding and participation only). | `agentic_trader/tca.py` | 2 | tested; operational |
| Q4 horizon from decay | `lagged_ic` (Spearman of the k-bar-old signal vs next return), `half_life_from_ic` (log-linear fit over the leading same-sign run), `rebalance_from_decay` (round(half-life) clipped to [1, 21]; default 5 kept when \|t(IC0)\| < 2). AR(1) phi 0.9 recovers the 6.6-bar half-life. Option only; default unchanged. Design-period table: `scripts/v17_costs.py horizon` (network, queued). | `agentic_trader/horizon.py`, `scripts/v17_costs.py` | 2 | simulation; table queued |
| D1 benchmark | `scripts/bench_core.py`: 15 names x 2,520 bars, TSMOM signal + `run_backtest` per sleeve, best of 5. **numpy: 2.59 s** on this laptop (AGENTIC_TRADER_BACKEND=python; idle-ish, P2 chain running, so an upper bound). C++ not built in this venv: row reads "not built". pytest-benchmark is not installed and there is no `.benchmarks/`, so this is a plain script, not a pytest-benchmark test. C++ core not deleted. | `scripts/bench_core.py` | run by hand | measured (numpy only) |
| D3/D4 hygiene | `.gitignore` already covers `.claude/` (so `.claude/worktrees/`), `coverage.xml`, `.coverage`, `htmlcov/`, `build/`, `*.egg-info/`, `__pycache__/`. `git ls-files` shows 0 tracked files under any of them, so nothing to `git rm --cached`. No change needed; no worktree touched. | none | `git ls-files` check | checked |
| (e) coverage note | README Tests block: coverage counts the numpy backend only; cpp/ is checked by parity tests, not measured. | `README.md` (one comment, no counts) | none | doc |
| (e) marker audit | See table below. | | | |
| D5 | Sentence for PLAN (maintainer to insert): "Rule-variant research on the single-name desk has stopped (v0.17); the desk is kept only as control #3 for the agentic and multi-asset results." | none | none | decision record |

## C1 result: what free daily OHLC can say about spreads (simulation, `docs/results/v17_costs/estimator_validation.md`)

Five seeds x 1,500 days, 100 trades a day, known spread:

| true spread | daily vol | CS unfloored mean | CS floored (paper's daily rule) | AR mean (sd) |
|--:|--:|--:|--:|--:|
| 2 bp | 1 % | 0.3 bp | 36.9 bp | 5.0 (7.2) bp |
| 5 bp | 1 % | 0.7 bp | 37.4 bp | 5.2 (7.6) bp |
| 20 bp | 1 % | 10.6 bp | 43.9 bp | 12.5 (11.8) bp |
| 20 bp | 2 % | 5.3 bp | 78.1 bp | 15.1 (16.1) bp |

Plain reading: at mega-cap spreads (1-5 bp) next to 1-2 % daily volatility, neither estimator
resolves the spread from six years of daily bars. Flooring daily CS estimates turns noise into
a 37-78 bp upward bias; unfloored CS is biased down by discrete sampling; Abdi-Ranaldo is
roughly unbiased but its standard error over six years is 7-16 bp. **Conclusion: a $0
calibration of `impact_coeff` for the core ten names from daily OHLC is not informative**;
the honest setting is a sensitivity band from the literature (Y in {0.1, 0.3, 1.0}), which the
existing impact sweep already supports. The real-data `calibrate` run is queued only to
confirm this on actual bars (expect AR estimates indistinguishable from 0 to ~15 bp).

## Marker audit (skip / xfail / flaky), 63 grep hits in tests/

No `xfail` and no `flaky` marker exists. Every "flaky" hit is a test double named `flaky*`
(a function that fails once on purpose to test retries), not a quarantine.

| Marker | Where | Reason | Verdict |
|---|---|---|---|
| `skipif(BACKEND != "cpp")` / `needs_cpp` / `pytest.skip("C++ extension not built")` | test_quant.py:62, test_quant_edges.py:181, test_quant_research.py:77, test_v08_engine.py:24, test_v08_fixes.py:49, test_fuzz.py:73,92,144,387 | parity needs the compiled core; CI runs a C++ job | keep (justified) |
| `importorskip("hypothesis")` | test_fuzz.py:14, test_fuzz_agentic.py:16 | dev extra | keep |
| `importorskip("fastapi"/"mcp"/"uvicorn"/"yaml"/"setuptools"/"opentelemetry.sdk"/"sentence_transformers")` | test_services.py, test_v05/06, test_v08_agentic, test_v08_cli, test_v14_ops, test_v15_* (about 40 sites) | optional extras | keep |
| `importorskip("tomllib")` | test_v15_followup.py:256 | 3.10 has no tomllib | keep |
| `skipif(no build/edgar_cache)` + `skip("cache incomplete")` | test_v08_data.py:768,782 | offline EDGAR cache under build/ (git-ignored) | keep; note it never runs in CI (build/ is ignored), so it is effectively a local-only test |
| `skip("git not installed")`, `skipif(git None)` | test_v08_fixes_cli.py:199, test_v14_ops.py:79 | needs git | keep |
| `skipif(no ANTHROPIC_API_KEY)` | test_v13_foundation.py:130 | network + key; never runs in CI | keep (free call, documented) |
| `skip("[rag] extra installed ...")` | test_v15_rag.py:102 | missing-extra path untestable when installed | keep |

No dead markers found; nothing removed.

**Previously flaky test** (`test_v08_agentic.py::test_interrupted_sweep_spares_a_live_siblings_runs`,
PLAN 4.11): run 20 times in a row, numpy backend, while a 13-minute test run and the P2 chain shared the CPU: **17 passed, 3 failed. The flake is not fixed.** It is a wall-clock lease test (3 s lease, `time.sleep(3.5)`, 5 s and 15 s polling deadlines) that depends on heartbeat threads being scheduled under load. That breaks lane rule 4 (no thread-timing assertions). Proposed fix, for whoever owns `agentic/harness.py` and the task store: inject a clock into the lease and heartbeat logic and advance it by hand in the test. Until then, mark the test `slow` (nightly only) or quarantine it. Not changed here because it is outside L8's files.

## Hooks for other lanes (one line each)

- **L2 (`quant/pycore.py` loop, line `cash = ...`, and the C++ mirror in `cpp/`):** add a
  `funding_spread` (and optional `cash_spread`) field to `BacktestConfig`, default 0 so
  published numbers do not move, and after `cash = ...` add
  `cash -= financing_drag(w, config.funding_spread, config.cash_spread) / ppy`
  (scalar form: `max(abs(w)-1,0)*funding_spread + max(1-abs(w),0)*cash_spread`). Then
  `financing.apply_financing` becomes a check (parity test: in-loop equals post-hoc at zero cost).
- **L2 (stop fill):** `_exit_fill` could take `half_spread, range_frac` and call
  `execution_realism.stop_fill_with_slippage`; defaults 0 keep parity.
- **L2 / backtest callers (participation):** `w = cap_participation(w, close, adv20, capital, cap)`
  before `run_backtest`, behind a config flag (`costs.backtest_participation_cap`, default None).
- **L5 (`oms.paper_session`, before the order loop):** `oms.positions, cash, ev =
  apply_actions(oms.positions, actions, through=d, after=prev_session)` then
  `oms.cash_flows += cash_flow_rows(ev)`, with `actions` from the raw bars plus actions L5
  stores per session (B4).
- **L5 (`paper_session`, after each execute):** collect `tca_rows([order], {cid: arrival},
  {cid: fill_cost(...)})` into `tca.csv` beside `orders.csv`.
- **L1 (risk model):** `var_next` body changed (A6) but not its signature; if L1 moves the
  default to a `DEFAULT_VAR_METHOD` constant the two edits do not overlap.

## Tests run

`pytest tests/test_v17_l8.py tests/test_v14_risk.py tests/test_v14_oms.py tests/test_v08_portfolio.py` (numpy backend): **140 passed**, 0 failed (25 new in test_v17_l8.py). ruff on the lane-rule paths plus the two new scripts: clean. mypy on the 8 touched or new modules: 0 errors. The banned-word grep (owner rule 2026-10-27): one hit, in the pre-existing docs/review/v017_LANE_RULES.md (the rule itself).

## Model runs / network runs to queue (maintainer, $0, network only)

```
set PYTHONPATH=. & .venv\Scripts\python.exe scripts\v17_costs.py calibrate --provider yahoo
set PYTHONPATH=. & .venv\Scripts\python.exe scripts\v17_costs.py horizon --provider yahoo
.venv\Scripts\python.exe scripts\bench_core.py          # on a machine with _atcore built, idle
```

All three read the design period only (2016-2021 plus 400 days warm-up); no model call.

## COOKBOOK recipe (text for the maintainer to number)

**Financing a levered backtest.** `from agentic_trader.financing import run_backtest_financed`;
`res = run_backtest_financed(prices, weights, cfg, funding_spread_bps=50)`. A 1.5x book pays
rf + 50 bp on the borrowed half: about 0.25 % a year on the account. Cash spread defaults to 0.

**Is my stop realistic?** `stop_fill_with_slippage(w=1, stop=95, o=100, h=101, low=94,
half_spread=5e-4, range_frac=0.5)` returns 94.45 (stop less half spread less half of the 1.00
from stop to low), against 95.00 in the engine.

## Follow-ups

- In-loop financing and stop slippage in both engines (L2 hooks above), with parity tests.
- Point-in-time universe: needs a free historical constituent list; none found. Keep the
  bound statement in each equity table header.
- GJR on the 15 design names (`scripts/v14_var_design.py` pattern), network run, later.
