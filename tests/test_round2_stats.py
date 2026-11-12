"""Round 2 (review 2026-11-12, lane C): worked numeric examples for C1, C2, C3, C8, C10, C11, C12.

Each test pins a number the pre-round-2 code got wrong or could not produce."""
from __future__ import annotations

import importlib.util
import json
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agentic_trader import evaluation, evidence_bounds, kpi, recall_audit, stats
from agentic_trader.bootstrap import null_centred_pvalue

ROOT = Path(__file__).resolve().parents[1]


def _common_mean_world(n: int = 1564, seed: int = 3):
    """A no-skill 'chosen' book: the control (annual Sharpe about 1.3) plus 0.1 % daily noise,
    and v0.11-like trial Sharpes 1.20..1.46 that all share the control's mean."""
    rng = np.random.default_rng(seed)
    sd = 0.01
    control = rng.normal(1.3 / math.sqrt(252) * sd, sd, n)
    chosen = control + rng.normal(0.0, 0.001, n)
    trials = np.linspace(1.20, 1.46, 42)
    return chosen, control, trials


# ------------------------------------------------------------------ C1 differential DSR
def test_c1_absolute_dsr_passes_a_no_skill_book_differential_does_not():
    chosen, control, trials = _common_mean_world()
    rep = stats.selection_report(chosen, trials, n_trials=81, control_returns=control)
    # the old statistic: a book that only copies the control "passes" (benchmark ~ 0.15 annual)
    assert rep["deflated_sharpe_prob"] > 0.95
    assert rep["expected_max_sharpe_annual"] < 0.2
    # the selection statistic says it added nothing
    assert rep["deflated_sharpe_prob_differential"] < 0.5
    assert rep["selection_statistic"] == stats.DIFFERENTIAL_SELECTION_STATISTIC
    # without a control the report says the absolute number is not a selection test
    assert "NOT a selection test" in stats.selection_report(chosen, trials)["selection_statistic"]


def test_c1_null_variance_and_benchmark_hand_worked():
    assert stats.null_trial_sharpe_variance(1564) == pytest.approx(1 / 1563)
    # 81 independent zero-skill trials over 1564 days at 260/yr: SR0 = sqrt(1/1563) * E[max] * sqrt(260)
    sr0 = stats.expected_max_sharpe(81, 1 / 1563) * math.sqrt(260)
    assert sr0 == pytest.approx(1.002, abs=0.002)


def test_c1_differential_detects_a_real_edge_against_measured_trials():
    rng = np.random.default_rng(5)
    n, sd = 1500, 0.01
    control = rng.normal(0.0005, sd, n)
    trial_returns = np.column_stack([control + rng.normal(0, 0.002, n) for _ in range(10)])
    chosen = control + rng.normal(0.0006, 0.002, n)          # differential Sharpe about 4.8 annual
    e = stats.deflated_sharpe_differential(chosen, control, 10, trial_returns=trial_returns)
    assert e["benchmark_variance_source"].startswith("variance of the trials' differential")
    assert e["sharpe_annual"] > 3.0 and e["deflated_sharpe_prob"] > 0.99
    raw = stats.deflated_sharpe_differential(chosen, control, 10, match_vol=False)
    assert raw["control_scale"] == 1.0 and e["control_scale"] != 1.0


def test_c1_differential_validates_inputs():
    with pytest.raises(ValueError):
        stats.deflated_sharpe_differential([0.1, 0.2], [0.1], 5)
    with pytest.raises(ValueError):
        stats.deflated_sharpe_differential([0.1, 0.2, 0.3], [0.1, 0.0, 0.2], 0)


# ------------------------------------------------------------------ C2 one selection number
def _load_script():
    spec = importlib.util.spec_from_file_location("selection_stat", ROOT / "scripts" / "selection_stat.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_c2_selection_stat_script_on_synthetic_inputs(tmp_path):
    chosen, control, trials = _common_mean_world(n=800)
    idx = pd.bdate_range("2016-01-04", periods=801)
    frame = pd.DataFrame({"AgenticTrader": np.r_[0.0, chosen], "B&H vol-target": np.r_[0.0, control],
                          "rf": 0.0}, index=idx)
    frame.to_csv(tmp_path / "portfolio_design.csv")
    (tmp_path / "trials.json").write_text(json.dumps(
        {"trials": [{"name": f"t{i}", "portfolio_sharpe": float(s)} for i, s in enumerate(trials)]}))
    mod = _load_script()
    out = mod.compute(tmp_path)
    assert out["n_registry"] == len(evaluation.TRIALS)
    assert out["n_pre_registry"] == evaluation.PRE_REGISTRY_TRIALS_ESTIMATE
    d = out["differential"]["registry"]
    assert d["trials"] == len(evaluation.TRIALS) and 0.0 <= d["deflated_sharpe_prob"] < 0.5
    assert out["absolute"]["control_at_registry"]["deflated_sharpe_prob"] > 0.9   # C1 on the control
    text = mod.render(out)
    assert "Selection statistic" in text and "not computable" in text
    assert mod.main(["--results", str(tmp_path / "missing")]) == 2


# ------------------------------------------------------------------ C3 power
def test_c3_sessions_needed_at_80_percent_power():
    assert evidence_bounds.sessions_needed(0.2) == pytest.approx(7302.4, abs=0.5)
    assert evidence_bounds.sessions_needed(0.2, power=0.5) == pytest.approx(3573.9, abs=0.1)
    h = evidence_bounds.decision_horizon(0.2)
    assert h["power"] == 0.8 and h["sessions"] == 7303 and 28.9 < h["years"] < 29.1
    assert h["sessions_at_50pct_power"] == 3574
    assert evidence_bounds.decision_horizon(0.5)["sessions"] == 1169
    with pytest.raises(ValueError):
        evidence_bounds.sessions_needed(0.2, power=1.0)


# ------------------------------------------------------------------ C8 time-block primary
def _shared_path(seed: int = 9, t: int = 400, k: int = 20):
    rng = np.random.default_rng(seed)
    base = rng.normal(0.0004, 0.01, (t, k))
    common = rng.normal(0.0, 0.004, t)[:, None]               # one regime moves every difference
    a = base + 0.3 * common + rng.normal(0.0, 0.0005, (t, k))
    return a, base


def test_c8_time_block_interval_is_wider_than_cross_instrument():
    a, b = _shared_path()
    r = stats.paired_time_block(a, b, n_boot=400)
    w_time = r.ci_high - r.ci_low
    w_inst = r.secondary.ci_high - r.secondary.ci_low
    assert r.scheme == "time-block" and r.n_instruments == 20
    assert w_time > 3 * w_inst                                  # cross-instrument is path-conditional
    assert "conditional on the realised time path" in r.secondary.conditioning
    assert r.mean_diff == pytest.approx(r.secondary.mean_diff)


def test_c8_table_uses_primary_p_for_bh():
    a, b = _shared_path()
    rows = stats.paired_time_block_table([{"label": "x", "a": a, "b": b}], n_boot=300)
    row = rows[0]
    assert row["primary"] == "time-block" and row["secondary"].startswith("cross-instrument")
    assert row["significant"] == bool(stats.benjamini_hochberg([row["p"]])[0])
    two = stats.paired_time_block(a, b, n_boot=200, two_way=True)
    assert two.scheme.startswith("two-way") and math.isfinite(two.ci_low)
    with pytest.raises(ValueError):
        stats.paired_time_block(a[:, :3], b, n_boot=50)


# ------------------------------------------------------------------ C10 decision frequency
def _weekly_records():
    rng = np.random.default_rng(1)
    d0 = date(2024, 1, 1)                                         # Mondays
    return [kpi.KPIRecord((d0 + timedelta(weeks=i)).isoformat(), "A", float(rng.choice([-1, 1])),
                          float(rng.choice([-1, 1])), float(rng.normal(0.002, 0.02))) for i in range(52)]


def test_c10_weekly_records_annualise_at_decision_frequency():
    recs = _weekly_records()
    t = kpi.kpi_table(recs)
    assert t["ppy"] == pytest.approx(50.4)
    model_book = [r.model_signal * r.outcome_return for r in recs]
    assert t["sharpe_model"] == pytest.approx(kpi.sharpe(model_book, 50.4))
    # the old default overstated it by sqrt(252 / 50.4) = 2.236
    assert kpi.sharpe(model_book, 252.0) / t["sharpe_model"] == pytest.approx(math.sqrt(5))
    with pytest.raises(ValueError):
        kpi.kpi_table(recs, ppy=252.0)
    assert kpi.kpi_table(recs, ppy=252.0, ppy_check=False)["ppy"] == 252.0
    assert kpi.decision_ppy(["2024-01-02", "2024-01-03", "2024-01-04"]) == 252.0
    assert kpi.decision_ppy(["d1", "d2"]) is None


# ------------------------------------------------------------------ C11 audit power
def test_c11_audit_power_numbers():
    p100 = recall_audit.audit_power(100, 100, 15)["power"]
    p300 = recall_audit.audit_power(300, 300, 15)["power"]
    size = recall_audit.audit_power(300, 300, 15, recall_share=0.0)["power"]
    assert 0.5 < p100 < 0.7 and p300 > 0.9 and size < 0.05
    assert recall_audit.audit_power(300, 0, 15)["power"] == 0.0
    assert 0.06 < recall_audit.min_detectable_recall_share(300, 300, 15) < 0.09


def test_c11_summarise_reports_power_and_keeps_pass_rule():
    names = [f"N{i}" for i in range(15)]
    real = recall_audit.build_items(names, ["2020-01-06", "2020-02-03"], seed=1)
    plc = recall_audit.build_items(names, ["2020-01-06", "2020-02-03"], seed=1, arm="placebo")
    res = recall_audit.summarise(real, [None] * len(real), plc, [None] * len(plc), n_perm=200)
    d = res.as_dict()
    assert d["recall_flagged"] is False                         # the rule itself is unchanged
    assert d["power"]["n_real"] == 30 and d["power"]["power"] < 0.5
    assert any("power to flag" in r for r in d["reasons"])


# ------------------------------------------------------------------ C12 one p convention
def test_c12_paired_bootstrap_p_is_null_centred():
    d = np.r_[np.full(9, 0.02), -0.15, np.full(5, 0.05)]       # skewed differences
    pb = stats.paired_bootstrap(d, np.zeros_like(d), n_boot=4000, seed=0)
    rng = np.random.default_rng(0)
    means = d[rng.integers(0, d.size, size=(4000, d.size))].mean(axis=1)
    assert pb.p_value == pytest.approx(null_centred_pvalue(means, d.mean()))
    assert pb.p_value_percentile == pytest.approx(min(1.0, 2 * min((means <= 0).mean(), (means >= 0).mean())))
    assert pb.p_value != pb.p_value_percentile


def test_c12_sharpe_block_bootstrap_p_is_null_centred():
    rng = np.random.default_rng(2)
    a, b = rng.normal(0.0008, 0.01, 300), rng.normal(0.0, 0.01, 300)
    r = stats.paired_sharpe_block_bootstrap(a, b, n_boot=500)
    assert 0 < r.p_value <= 1 and 0 <= r.p_value_percentile <= 1
    same = stats.paired_sharpe_block_bootstrap(a, a, n_boot=200)
    assert same.p_value == 1.0 and same.p_value_percentile == 1.0
