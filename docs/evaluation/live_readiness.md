# Live-readiness statement (PLAN 6.3)

**AgenticTrader is not a production trading system and makes no claim to be one.** It never
connects to a broker. This page says, component by component, what exists in the repository,
what exists only as a simulation, and what is absent, so that nobody has to infer it from the
code.

How to read the table. *Exists* means the code runs on real inputs the way a desk would use it
(still on free daily data). *Simulated* means the logic is there but it acts on a paper book
or a fixture, never on an external system. *Absent* means there is no code; anything a real
desk needs here would be new work. Every row names the file that implements it and a test
that exercises it; a row with no test says so.

Worked example: an order. `oms.py` takes it through new, acked, partial, filled, runs the
pre-trade checks and reconciles it at end of day against the ledger (simulated, tested in
`tests/test_v14_oms.py`). Nothing leaves the process: there is no broker adapter, so the
"broker" row below is absent, and the reconciliation is against our own ledger, not against a
custodian statement.

| Component | Status | What there is | Source | Test |
|---|---|---|---|---|
| Broker / execution venue | **Absent** | No broker, FIX or exchange adapter. Fills are modelled with the backtester's cost model at a participation cap. | `agentic_trader/oms.py` (fill model only) | `tests/test_v14_oms.py::test_fill_cost_matches_the_backtester_on_a_toy_order` |
| Order management (OMS) | **Simulated** | Order states and legal transitions, idempotent client order id, fat-finger, collar, duplicate and borrow checks, market hours and NYSE holidays, T+1 / FX T+2 settlement, cash projection, FX roll at 17:00 NY. Shadow record `oms_shadow_v14`, off by default. | `agentic_trader/oms.py` | `tests/test_v14_oms.py` (state machine, checks, settlement, roll) |
| Kill switch | **Simulated** | Global and per-sleeve, persisted, honoured by the OMS and by the agentic `submit_order` tool. | `agentic_trader/oms.py`, `agentic_trader/agentic/tools.py` | `tests/test_v14_oms.py::test_kill_switch_blocks_every_path_and_persists`, `::test_kill_switch_blocks_the_agentic_submit_order_tool` |
| Pre-trade risk | **Simulated** | Book VaR limit (EWMA default since the owner decision of 2026-11-07, `config.DEFAULT_VAR_METHOD`, shared with `risk_model.var_forecast`/`var_next`; FHS and historical options), short-notional cap, position limits in the risk team. Limits are loose and untuned (PLAN §9, 2026-11-07). | `agentic_trader/risk_model.py`, `agentic_trader/validate.py` | `tests/test_v14_risk.py::test_book_var_default_on_and_ewma`, `tests/test_v17_r0_var.py`, `tests/test_v14_oms.py::test_duplicate_guard_and_short_notional_cap` |
| Approvals / four-eyes | **Simulated** | Approval gateway; signed approvals with N-of-M quorum, TTL and re-pricing check, from the `agentic.approval` block. Shared-secret HMAC is a residual risk (CHANGELOG v0.15.1). | `agentic_trader/agentic/governance.py`, `agentic_trader/agentic/harness.py` | `tests/test_v14_oms.py::test_approval_gateway_gates_orders`, `tests/test_v15_followup.py` |
| Entitlements (who may see or do what) | **Simulated, partial** | Tool-level policy: every data access and action is a catalogued tool call checked by a policy and evidenced. There are no user accounts, roles, data-vendor licences or market-data entitlements. | `agentic_trader/agentic/policy.py`, `agentic_trader/agentic/tools.py` | `tests/test_agentic.py`, `tests/test_v15_security.py` |
| Custodian reconciliation | **Absent** | End-of-day reconciliation exists only between the paper OMS and the paper ledger (quantity, cash and price breaks). No custodian or prime-broker statement is read. | `agentic_trader/oms.py` (internal reconciliation) | `tests/test_v14_oms.py::test_reconciliation_detects_qty_cash_and_price_breaks` (internal only) |
| Tax lots | **Absent** | Positions are net weights; no lot tracking, no FIFO/HIFO, no wash-sale logic. | none | none |
| Margin and financing | **Simulated, partial** | No margin model and no haircut; shorts are capped by notional, not by margin. A financing spread on borrowed notional (\|w\| > 1 pays rf + 50 bp by default, optional spread under rf on idle cash) is applied after a run by `financing.run_backtest_financed` (v0.17); the in-loop engine hook is pending. | `agentic_trader/financing.py` (carry: `agentic_trader/backtest.py`) | `tests/test_v17_l8.py::test_levered_run_pays_spread_exactly_without_costs` |
| Trade surveillance | **Absent** | No market-abuse, wash-trade or spoofing surveillance. The governance report audits the agent's evidence trail, which is a different thing. | none | none |
| Data vintages | **Exists** | Each paper session records a `price_vintage` hash of the bars it read in `results/paper/runs.jsonl`; recomputations that differ are logged to `revisions.csv`, never absorbed; FRED series read first-published values. | `scripts/paper_trade_v09.py`, `agentic_trader/data/` | `tests/test_v14_ops.py::test_vintage_hash_is_stable_and_moves_with_any_price`, `tests/test_v05.py::test_fred_vintages_read_first_published_values` |
| Point-in-time data and leakage | **Exists** | Purged walk-forward IC, a future-leak canary, a point-in-time feature store. Blind spot: leaks inside a provider's own news or fundamentals (PLAN §9). | `agentic_trader/leakage.py` | `tests/test_v14_leakage.py` |
| Forward paper record | **Exists (paper)** | Daily scheduled run on GitHub Actions, append-only ledger, freshness check, issue on failure. Paper only. | `.github/workflows/paper.yml`, `scripts/paper_trade_v09.py` | `tests/test_v09_paper.py`, `tests/test_v14_ops.py::test_freshness_rule_skips_without_a_record_and_fails_past_two_business_days` |
| Model drift and refusals | **Exists** | Served-model drift is counted and can be refused; a refusal is evidenced as missing data. | `agentic_trader/llm.py` | `tests/test_v13_foundation.py::test_drift_is_rejected_when_strict_and_always_counted` |

What would have to change before any of this touched money: a broker adapter behind the OMS,
reconciliation against an external statement, tax lots, margin, surveillance and real
entitlements, each with its own tests, and an independent review. None of it is planned in
`docs/review/PLAN.md`.

## Forward paper record: operational evidence, not a test that can decide

Plain idea. The forward paper record (`results/paper/`) is the only data no design choice has
seen, but a short record cannot tell a 0.2 Sharpe difference from noise. Until the
pre-registered decision look it shows that the pipeline runs, fills reconcile and nothing
leaks: operational evidence. It does not show that anything has an edge.

Formal statement. The v0.9 pre-registration amendment (`docs/evaluation/v09_preregistration.md`)
fixes one decision look. The holdout's paired block-bootstrap half-width for the desk minus its
control was h = 0.35 Sharpe over n = 1,167 sessions. Half-widths shrink as 1 / sqrt(n), so a
Sharpe difference d has a 95 % interval that just reaches zero after n_d = 1,167 x (0.35 / d)^2
sessions. Corrected 2026-11-12 (review C3): that is the point where a true effect of size d is
detected half the time, so it is 50 % power, not "detectable". At 80 % power the count is
((1.96 + 0.84) / 1.96)^2 = 2.04 times larger.

Worked example (`evidence_bounds.decision_horizon`; evidence class: arithmetic on
pre-registered numbers, tested in `tests/test_v17_l8.py::test_decision_horizon_from_prereg_numbers`):

| Sharpe difference d | power | sessions | years (252 a year) | look, counting NYSE sessions from 2026-09-29 |
|---|--:|--:|--:|---|
| 0.2 (pre-registered look) | 50 % | 3,574 | 14.2 | 2040-12-19 |
| 0.2 | 80 % | 7,303 | 29.0 | 2055-10-29 |
| 0.5 | 50 % | 572 | 2.3 | 2029-01-05 |
| 0.5 | 80 % | 1,169 | 4.6 | 2031-05-23 |

Plainly: the pre-registered look in 2040 stays where it was registered, but it has an even
chance of missing a real 0.2 effect, and a properly powered answer would take about 29 years.
The forward record cannot decide an effect of this size. It is an operations record.

The interim summary prints Sharpes and, after 60 sessions, intervals of about +/-1.2 to
+/-1.5 Sharpe; those are descriptions, not decisions. The calendar is the OMS NYSE holiday
table, so the date can move by a few sessions as one-off closures are added.

