"""v0.17 lane L3: research honesty (R1.2-R1.5, N4-N8, N10)."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agentic_trader import evaluation, kpi, leakage, stats, xalpha

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- R1.2 Newey-West
def test_newey_west_known_answer_by_hand():
    # x = [1, 2, 3, 4, 5], lag 1. mean 3, d = [-2,-1,0,1,2]
    # g0 = (4+1+0+1+4)/5 = 2; g1 = (2+0+0+2)/5 = 0.8
    # S = 2 + 2 * (1 - 1/2) * 0.8 = 2.8; se = sqrt(2.8/5); t = 3 / se = 4.0089
    r = stats.newey_west_t([1, 2, 3, 4, 5], lag=1)
    assert r.lag == 1 and r.n == 5
    assert r.se == pytest.approx(math.sqrt(2.8 / 5))
    assert r.t == pytest.approx(3 / math.sqrt(0.56), rel=1e-12)
    assert r.t == pytest.approx(4.0089, abs=1e-4)
    assert r.n_eff == pytest.approx(5 * 2 / 2.8)


def test_newey_west_lag_zero_is_iid_t_with_n_denominator():
    x = np.array([0.5, -0.2, 0.1, 0.4, -0.1, 0.3])
    r = stats.newey_west_t(x, lag=0)
    assert r.t == pytest.approx(x.mean() / math.sqrt(x.var(ddof=0) / x.size))


def test_newey_west_lag_rule():
    assert stats.newey_west_lag(1000) == 6          # floor(4 * 10 ** (2/9)) = floor(6.67)
    assert stats.newey_west_lag(100) == 4
    assert stats.newey_west_lag(1000, horizon=10) == 10


def test_hac_t_is_smaller_than_naive_t_on_overlapping_returns():
    rng = np.random.default_rng(1)
    e = rng.standard_normal(3000)
    h = 10
    over = np.convolve(e, np.ones(h), "valid") + 0.5   # overlapping sums: strong MA(h-1)
    naive = over.mean() / (over.std(ddof=1) / math.sqrt(over.size))
    nw = stats.newey_west_t(over, horizon=h)
    assert nw.lag >= h and abs(nw.t) < 0.6 * abs(naive)


def test_min_detectable_ic_known_answer():
    k = 1.959963984540054 + 0.8416212335729143
    assert stats.min_detectable_ic(1000) == pytest.approx(math.tanh(k / math.sqrt(997)), rel=1e-9)
    assert stats.min_detectable_ic(0, se=0.01) == pytest.approx(k * 0.01)
    assert math.isnan(stats.min_detectable_ic(3))


def test_rank_ic_newey_west_detects_real_ic():
    rng = np.random.default_rng(2)
    s = rng.standard_normal(2000)
    f = 0.3 * s + rng.standard_normal(2000)
    r = stats.rank_ic_newey_west(s, f, horizon=1)
    assert r.mean == pytest.approx(0.28, abs=0.05) and r.t > 8


def test_blocked_fold_ic_carries_nw_and_mde_and_honest_label():
    rng = np.random.default_rng(3)
    s = rng.standard_normal(1500)
    f = rng.standard_normal(1500)
    r = leakage.ic_blocked_folds(s, f, horizon=1)
    assert leakage.ic_purged is leakage.ic_blocked_folds        # old name kept
    assert math.isfinite(r.t_nw) and r.nw_lag >= 1
    assert 0.03 < r.mde_ic < 0.12          # ~1200 scored pairs -> about 0.08
    assert "no fit" in r.method and "purge inactive" in r.method
    g = r.as_gate()
    assert {"t_NW", "MDE_IC", "df"} <= set(g) and g["df"] == r.k - 1
    assert "purged walk-forward cross-validation" not in (leakage.__doc__ or "")


def test_series_counterpart_has_nw():
    rng = np.random.default_rng(4)
    ic = pd.Series(0.05 + 0.1 * rng.standard_normal(800))
    r = leakage.ic_blocked_folds_series(ic, horizon=5)
    assert r.t_nw > 3 and r.nw_lag >= 5 and math.isfinite(r.mde_ic)


# ---------------------------------------------------------------- R1.3 BH + DSR
def _entry(t_fold, t_nw, n=200):
    return {"IC": 0.05, "t(IC)": t_fold, "n": n, "t_crit": leakage.student_t_crit(4), "df": 4, "t_NW": t_nw}


def test_gate_family_bh_removes_nominal_passes_in_a_big_null_family():
    from statistics import NormalDist
    # 400 null tests: NW p-values spread uniformly on (0, 1); entry 0 has p ~ 0.028 and a
    # nominal fold-t pass, the kind of row that used to read as a discovery.
    ps = (np.arange(400) + 0.5) / 400
    fam = {("a", i, 10): _entry(0.5, NormalDist().inv_cdf(1 - p / 2)) for i, p in enumerate(ps)}
    fam[("a", 0, 10)] = _entry(3.0, 2.2)
    fam[("real", 0, 10)] = _entry(6.0, 6.0)
    res = leakage.gate_family_bh(fam, q=0.05)          # default: Newey-West p
    assert res[("a", 0, 10)]["nominal"] and not res[("a", 0, 10)]["passes"]
    assert res[("real", 0, 10)]["passes"]
    # a lone test with the same NW t passes: the family, not the statistic, changed the verdict
    lone = leakage.gate_family_bh({"a": _entry(3.0, 2.2)}, q=0.05)
    assert lone["a"]["passes"]


def test_gate_p_value_fold_and_nw():
    e = _entry(2.776445105, 1.959963985)
    assert leakage.gate_p_value(e, "fold") == pytest.approx(0.05, abs=1e-6)
    assert leakage.gate_p_value(e, "nw") == pytest.approx(0.05, abs=1e-6)
    assert math.isnan(leakage.gate_p_value({"t(IC)": 3.0}, "fold"))
    table = leakage.format_gate_family({("x", "AAPL", 10): e})
    assert "min detectable IC" in table and "Family: 1 tests" in table
    assert set(leakage.GATE_FAMILIES) == {"time_series", "cross_sectional"}


def test_pre_registry_estimate_and_dsr_rows():
    assert evaluation.PRE_REGISTRY_TRIALS_ESTIMATE == sum(evaluation.PRE_REGISTRY_CONSTANTS.values()) * 2
    assert evaluation.pre_registry_trial_estimate(1) == 0
    rng = np.random.default_rng(5)
    r = 0.0005 + 0.01 * rng.standard_normal(1500)
    trials = list(0.3 + 0.2 * rng.standard_normal(30))
    base = stats.selection_report(r, trials, n_trials=77)
    assert "deflated_sharpe_prob_incl_pre_registry" not in base
    rep = stats.selection_report(r, trials, n_trials=77, pre_registry_trials=64)
    assert rep["trials_incl_pre_registry"] == 141
    assert rep["deflated_sharpe_prob_incl_pre_registry"] <= rep["deflated_sharpe_prob"]
    assert rep["expected_max_sharpe_annual_incl_pre_registry"] > rep["expected_max_sharpe_annual"]


# ---------------------------------------------------------------- N8 effective trials
def test_effective_trials_extremes_and_correction():
    rng = np.random.default_rng(6)
    ind = rng.standard_normal((2000, 10))
    n_eff, rho = stats.effective_trials(ind)
    assert n_eff == pytest.approx(10, rel=0.05) and abs(rho) < 0.05
    common = rng.standard_normal((2000, 1))
    corr = common + 0.1 * rng.standard_normal((2000, 10))      # one-rule ablations
    n_eff2, rho2 = stats.effective_trials(corr)
    assert n_eff2 < 1.5 and rho2 > 0.9
    e = stats.deflated_sharpe_effective(0.05, 1500, corr, 1e-4)
    assert e["var_trials_corrected"] == pytest.approx(1e-4 / (1 - rho2))
    rep = stats.selection_report(0.0005 + 0.01 * rng.standard_normal(1500), [0.3, 0.32, 0.31, 0.29],
                                 trial_returns=corr)
    assert "deflated_sharpe_prob_effective" in rep and "participation ratio" in rep["effective_trials_method"]


# ---------------------------------------------------------------- R1.4 recall guard
def _recall(t_hits, m_hits=1, near=5, n=200, unparsed=0):
    def row(k, p0):
        return {"hits": k, "n": n, "rate": k / n, "chance": p0}
    return {"n": n, "unparsed": unparsed, "ticker": row(t_hits, 1 / 15), "month": row(m_hits, 1 / 72),
            "month_within_1": row(near, 3 / 72)}


def test_recall_verdict_worked_example():
    assert evaluation.recall_audit_verdict(_recall(20))["passed"]
    v = evaluation.recall_audit_verdict(_recall(21))
    assert not v["passed"] and "ticker" in v["reasons"][0]
    assert v["bounds"]["ticker"] == pytest.approx(1 / 15 + 2 * math.sqrt((1 / 15) * (14 / 15) / 200))
    assert not evaluation.recall_audit_verdict(_recall(5, n=50))["passed"]
    assert not evaluation.recall_audit_verdict(_recall(5, unparsed=30))["passed"]


def test_require_recall_pass_guard(tmp_path):
    with pytest.raises(evaluation.HoldoutLocked):
        evaluation.require_recall_pass(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(_recall(40)), encoding="utf-8")
    with pytest.raises(evaluation.HoldoutLocked):
        evaluation.require_recall_pass(bad)
    good = tmp_path / "good.json"
    good.write_text(json.dumps(_recall(10)), encoding="utf-8")
    assert evaluation.require_recall_pass(good)["passed"]


def test_evaluate_refuses_local_model_holdout_without_recall(tmp_path):
    assert evaluation.touches_holdout({"q1_2024": evaluation.PERIODS["q1_2024"]})
    assert not evaluation.touches_holdout({"design": evaluation.PERIODS["design"]})

    class FakeLLM:  # never called: the guard fires first
        pass
    with pytest.raises(evaluation.HoldoutLocked):
        evaluation.evaluate(["AAPL"], {"holdout": evaluation.PERIODS["holdout"]},
                            config={"llm_provider": "local", "recall_audit_path": str(tmp_path / "none.json")},
                            llm=FakeLLM())


def test_prereg_states_recall_precondition_and_no_hand_count():
    text = (ROOT / "docs/evaluation/v16_preregistration_DRAFT.md").read_text(encoding="utf-8")
    assert "Precondition: the 2.4 recall audit must pass" in text
    assert "require_recall_pass" in text
    assert not re.search(r"\(\d+ at writing\)", text)                    # N10
    ev = (ROOT / "docs/evaluation/evaluation.md").read_text(encoding="utf-8")
    assert "62 to 65" not in ev and "Breadth: 15 names" in ev


# ---------------------------------------------------------------- R1.5 model-changed P&L
def _rec(d, sym, m, r, out):
    return kpi.KPIRecord(as_of=d, symbol=sym, model_signal=m, rule_signal=r, outcome_return=out)


def test_model_changed_worked_example():
    recs = [_rec("d1", "A", 1, -1, 0.02), _rec("d1", "B", 1, 1, 0.05), _rec("d2", "A", 0, 1, -0.01)]
    a = kpi.model_changed_attribution(recs, n_boot=500)
    assert a["n_changed"] == 2 and a["share_changed"] == pytest.approx(2 / 3)
    assert a["pnl_delta_total"] == pytest.approx(0.05)
    assert a["pnl_delta_mean"] == pytest.approx(0.025)
    assert a["hit_rate_model"] == 1.0 and a["hit_rate_rules"] == 0.0
    lo, hi = a["ci_total"]
    assert lo <= a["pnl_delta_total"] <= hi


def test_model_changed_none_and_table_rows():
    recs = [_rec("d1", "A", 1, 1, 0.01), _rec("d2", "A", -1, -1, -0.01)]
    a = kpi.model_changed_attribution(recs)
    assert a["n_changed"] == 0 and a["pnl_delta_total"] == 0.0
    t = kpi.kpi_table(recs)
    assert any(r[0] == "model-changed, P&L delta total" for r in t["rows"])
    with pytest.raises(ValueError):
        kpi.model_changed_attribution(recs, by="x")


def test_model_changed_ci_brackets_zero_for_noise():
    rng = np.random.default_rng(7)
    recs = [_rec(f"d{i}", "A", float(rng.choice([-1, 1])), float(rng.choice([-1, 1])), float(rng.normal(0, 0.01)))
            for i in range(300)]
    a = kpi.model_changed_attribution(recs, n_boot=1000)
    assert a["ci_total"][0] < 0 < a["ci_total"][1]


# ---------------------------------------------------------------- N4 / N5 / N6 / N7 xalpha
def test_grouped_ic_does_not_mix_classes():
    idx = pd.RangeIndex(60)
    rng = np.random.default_rng(8)
    eq = [f"E{i}" for i in range(5)]
    fx = [f"F{i}" for i in range(5)]
    groups = {**{c: "equity" for c in eq}, **{c: "fx" for c in fx}}
    # Within each class the signal predicts perfectly; FX returns are 100x smaller, so a
    # pooled ranking puts every equity above every FX pair and loses the within-class order.
    sig = pd.DataFrame(rng.standard_normal((60, 10)), index=idx, columns=eq + fx)
    fwd = sig.copy()
    fwd[eq] = sig[eq] + 50.0
    fwd[fx] = sig[fx] * 0.01 - 50.0
    sig[fx] = sig[fx] + 10.0     # FX signals high, FX returns low: pooled IC is negative
    g = xalpha.grouped_cross_sectional_ic(sig, fwd, groups, min_names=5)
    pooled = xalpha.cross_sectional_ic(sig, fwd, min_names=5)
    assert np.allclose(g.to_numpy(), 1.0)
    assert pooled.mean() < 0.5


def test_beta_neutralise_removes_beta_exposure():
    idx = pd.RangeIndex(5)
    betas = pd.DataFrame([[0.5, 1.0, 1.5, 2.0]] * 5, index=idx, columns=list("ABCD"))
    panel = 3.0 * betas + 1.0
    res = xalpha.beta_neutralise(panel, betas)
    assert np.allclose(res.to_numpy(), 0.0, atol=1e-12)


def test_significance_gated_no_fixed_two_bar():
    scores = {"a": pd.DataFrame({"X": [1.0], "Y": [-1.0]})}
    # old behaviour: t = 2.5 with no t_crit passed the fixed 2.0 bar
    assert xalpha.significance_gated_scores(scores, {"a": {"IC": 0.1, "t(IC)": 2.5, "n": 100}}).isna().all().all()
    # a t between 2.0 and 2.776 at 4 df fails too
    e = {"IC": 0.1, "t(IC)": 2.5, "n": 100, "t_crit": 2.776, "df": 4, "t_NW": 5.0}
    assert xalpha.significance_gated_scores(scores, {"a": e}).isna().all().all()


def test_gate_entry_recovers_df():
    e = xalpha.gate_entry({"mean IC": 0.02, "t(IC)": 1.0, "t_crit": leakage.student_t_crit(4), "days": 500,
                           "t_NW": 1.2, "MDE_IC": 0.01})
    assert e["df"] == 4 and e["n"] == 500
