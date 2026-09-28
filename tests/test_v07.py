"""v0.7 features: VaR coverage backtesting, book-level risk aggregation, a grouped
cross-instrument bootstrap (stratified in v0.7, a cluster bootstrap since v0.8),
execution-aware cost scheduling, FDR-corrected significance, solver convergence flags,
dependency lock, and CLI restructuring."""
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agentic_trader import Instrument, TradingGraph, make_config
from agentic_trader.algo import algo_cost_ratio, volume_profile
from agentic_trader.backtest import run_agent_backtest
from agentic_trader.memory import DecisionMemory
from agentic_trader.portfolio import (
    Convergence, book_var_95, book_var_scale, construct, mean_variance_weights, min_variance_weights,
)
from agentic_trader.state import Book
from agentic_trader.stats import (
    DEFLATED_SHARPE_CAVEAT, PairedBootstrap, benjamini_hochberg, paired_bootstrap, rolling_var_forecast,
    selection_report, var_backtest,
)

CFG = make_config(memory_path=None)
QUIET = dict(memory=DecisionMemory(None), on_event=lambda *_: None)
ROOT = Path(__file__).resolve().parents[1]


def _graph(cfg=CFG, **kw):
    return TradingGraph(cfg, **{**QUIET, **kw})


# ------------------------------------------------------------- Benjamini-Hochberg
def test_benjamini_hochberg_matches_the_textbook_example():
    # Benjamini & Hochberg (1995) illustrative case: only the two smallest survive at q=0.05.
    p = [0.01, 0.04, 0.03, 0.005, 0.5, 0.7, 0.9, 0.99]
    got = benjamini_hochberg(p, q=0.05)
    assert list(got) == [True, False, False, True, False, False, False, False]
    assert not benjamini_hochberg([0.5, 0.6, 0.7]).any()
    assert benjamini_hochberg([]).size == 0
    # NaN (fewer than three instruments) is never significant, and does not block the others
    got = benjamini_hochberg([float("nan"), 0.001, 0.02], q=0.1)
    assert list(got) == [False, True, True]


def test_selection_report_carries_its_upper_bound_caveat():
    rng = np.random.default_rng(3)
    r = rng.normal(0.001, 0.01, 500)
    rep = selection_report(r, [0.5, 0.6, 0.7])
    assert rep["caveat"] == DEFLATED_SHARPE_CAVEAT
    assert selection_report(r, [0.5])["caveat"] is None   # a single trial has no search space to bound


def test_paired_table_significance_is_fdr_corrected(monkeypatch):
    from agentic_trader.evaluation import EvaluationResult
    # Six baselines, only two of which are "real": everything else near zero, matching the
    # textbook p-value pattern so the corrected column should keep exactly those two.
    from agentic_trader.backtest import AGENT
    rows = []
    for i, base in enumerate(["b0", "b1", "b2", "b3", "b4", "b5"]):
        rows.append({"period": "q", "symbol": f"S{i}", "strategy": AGENT, "universe": "core", "Sharpe": 1.0})
        rows.append({"period": "q", "symbol": f"S{i}", "strategy": base, "universe": "core", "Sharpe": 1.0})
    res = EvaluationResult(pd.DataFrame(rows), {})

    fake_p = {"b0": 0.01, "b1": 0.04, "b2": 0.03, "b3": 0.005, "b4": 0.5, "b5": 0.7}

    def fake_paired(self, baseline, metric="Sharpe", period=None, universe=None, strategy=AGENT, n_boot=10_000,
                    seed=0, cluster=True):
        return PairedBootstrap(10, 0.1, -0.05, 0.2, fake_p[baseline], 6)
    monkeypatch.setattr(EvaluationResult, "paired", fake_paired)
    tab = res.paired_table()
    assert list(tab.sort_values("baseline")["significant"]) == [True, False, False, True, False, False]


# --------------------------------------------------------- solver convergence
def test_min_variance_reports_non_convergence_on_a_hard_cap():
    rng = np.random.default_rng(0)
    a = rng.normal(0, 1, (8, 8))
    cov = (a @ a.T + np.eye(8) * 1e-6) * 1e-4   # genuinely ill-conditioned: needs ~300 iterations
    w, info = min_variance_weights(cov, cap=1.0, return_info=True)
    assert isinstance(info, Convergence) and info.converged and info.iterations > 0
    w2, info2 = min_variance_weights(cov, cap=1.0, iters=3, return_info=True)
    assert not info2.converged and info2.iterations == 3
    assert isinstance(w2, np.ndarray) and w2.shape == (8,)
    # the plain (no return_info) call keeps returning just the array, unchanged behaviour
    assert isinstance(min_variance_weights(cov, cap=1.0), np.ndarray)


def test_mean_variance_convergence_flag():
    cov = np.eye(3) * 0.04
    mu = np.array([0.1, 0.05, -0.02])
    w, info = mean_variance_weights(mu, cov, risk_aversion=2.0, cap=0.6, return_info=True)
    assert info.converged
    # the cap binds on the first asset, so the solve is [0.6, 0.4, 0]: a full simplex, capped
    assert isinstance(w, np.ndarray) and w.sum() == pytest.approx(1.0) and w.max() <= 0.6 + 1e-9
    assert w.min() >= 0.0


def test_construct_surfaces_non_convergence(caplog):
    idx = pd.bdate_range("2023-01-01", periods=120)
    # three near-duplicate return series: an ill-conditioned covariance for min_variance
    base = np.random.default_rng(0).normal(0, 0.01, 120)
    rets = pd.DataFrame({"A": base + 1e-6, "B": base + 2e-6, "C": base + 3e-6}, index=idx)
    pw = construct({"A": 1.0, "B": 1.0, "C": 1.0}, rets, method="min_variance", target_vol=None)
    assert hasattr(pw, "converged") and isinstance(pw.converged, bool)
    assert "converged" in pw.to_dict()
    pw_equal = construct({"A": 1.0, "B": 1.0, "C": 1.0}, rets, method="equal", target_vol=None)
    assert pw_equal.converged is True   # closed-form schemes are always reported converged


# ---------------------------------------------------- grouped (cluster) bootstrap
# The v0.7 release shipped a *stratified* scheme here (fixed count per group every replicate)
# and these tests asserted nothing that could tell it from plain resampling. v0.8 replaced it
# with a cluster bootstrap that needs at least MIN_CLUSTER_GROUPS groups; the sensitivity
# tests live in tests/test_v08_stats.py, these cover the fallback paths.
def test_paired_bootstrap_with_two_groups_falls_back_to_plain_and_says_so():
    """Two clusters cannot be resampled as clusters (a two-point bootstrap of the between-
    cluster shock is meaningless), so the plain instrument bootstrap is used and reported;
    the v0.7 stratified scheme silently narrowed this interval from 0.35 to 0.05."""
    rng = np.random.default_rng(4)
    cluster_a = rng.normal(0.5, 0.05, 10)   # ten near-identical "instruments"
    cluster_b = rng.normal(-0.3, 0.05, 10)
    a = np.concatenate([cluster_a, cluster_b])
    b = np.zeros_like(a)
    groups = np.array(["A"] * 10 + ["B"] * 10)
    grouped = paired_bootstrap(a, b, n_boot=5000, groups=groups, seed=1)
    plain = paired_bootstrap(a, b, n_boot=5000, groups=None, seed=1)
    assert grouped.scheme == "instruments" and grouped.n_groups == 2
    assert plain.scheme == "instruments" and plain.n_groups == 0
    assert grouped.n == plain.n == 20 and grouped.mean_diff == pytest.approx(plain.mean_diff)
    assert (grouped.ci_low, grouped.ci_high, grouped.p_value) == (plain.ci_low, plain.ci_high, plain.p_value)
    assert grouped.ci_high - grouped.ci_low > 0.3   # not the 0.05-wide stratified interval


def test_paired_bootstrap_single_group_matches_plain():
    rng = np.random.default_rng(2)
    a, b = rng.normal(0.5, 0.2, 15), rng.normal(0.3, 0.2, 15)
    groups = np.array(["only"] * 15)
    with_one_group = paired_bootstrap(a, b, groups=groups, seed=9, n_boot=4000)
    without = paired_bootstrap(a, b, groups=None, seed=9, n_boot=4000)
    assert with_one_group.scheme == "instruments" and with_one_group.n_groups == 1
    assert with_one_group.ci_low == pytest.approx(without.ci_low)
    assert with_one_group.ci_high == pytest.approx(without.ci_high)


def test_paired_bootstrap_groups_validation():
    with pytest.raises(ValueError):
        paired_bootstrap([1, 2, 3], [1, 2, 3], groups=["a", "b"])   # wrong length


def test_evaluation_paired_reports_the_fallback_below_five_groups_and_can_reproduce_v06():
    res = evaluate_full_universe()   # three (asset_class, universe) groups: below the cluster threshold
    grouped = res.paired("Buy&Hold", period="q")
    plain = res.paired("Buy&Hold", period="q", cluster=False)
    assert grouped.n == plain.n == 6   # same pairs
    assert grouped.scheme == "instruments" and grouped.n_groups == 3   # the labels were seen, then declined
    assert plain.scheme == "instruments" and plain.n_groups == 0       # cluster=False passes no labels
    assert grouped.mean_diff == pytest.approx(plain.mean_diff)   # the point estimate never changes
    assert (grouped.ci_low, grouped.ci_high) == (plain.ci_low, plain.ci_high)   # identical draws
    tab = res.paired_table()
    tab_old = res.paired_table(cluster=False)
    assert list(tab.columns) == list(tab_old.columns)
    assert {"scheme", "groups"} <= set(tab.columns)
    assert (tab.scheme == "instruments").all() and (tab.groups == 3).all() and (tab_old.groups == 0).all()


def evaluate_full_universe():
    from agentic_trader.evaluation import EvaluationResult
    rows = []
    for sym, ac, uni in [("AAPL", "equity", "core"), ("MSFT", "equity", "core"),
                        ("GLD", "equity", "extended-macro"), ("SLV", "equity", "extended-macro"),
                        ("EURUSD", "fx", "core"), ("USDJPY", "fx", "core")]:
        for strat in ("AgenticTrader", "Buy&Hold"):
            rows.append({"period": "q", "symbol": sym, "asset_class": ac, "universe": uni,
                        "strategy": strat, "Sharpe": 1.0 if strat == "AgenticTrader" else 0.5})
    return EvaluationResult(pd.DataFrame(rows), {})


# --------------------------------------------------------------- VaR coverage
def test_var_backtest_kupiec_matches_the_textbook_formula():
    n, x, p = 100, 10, 0.05
    rate = x / n
    expected_lr = -2 * math.log((1 - p) ** (n - x) * p ** x) + 2 * math.log((1 - rate) ** (n - x) * rate ** x)
    returns = np.zeros(n)
    returns[np.arange(0, n, 10)] = -0.02   # exactly 10 breaches, evenly spaced (not clustered)
    forecast = np.full(n, 0.01)
    vb = var_backtest(returns, forecast, alpha=0.95)
    assert vb.n == 100 and vb.breaches == 10 and vb.breach_rate == pytest.approx(0.10)
    assert vb.kupiec_lr == pytest.approx(expected_lr, abs=1e-4)
    assert vb.kupiec_p < 0.05   # double the nominal rate over 100 obs is a real miss


def test_var_backtest_well_calibrated_series_is_not_rejected():
    rng = np.random.default_rng(7)
    n = 2000
    returns = rng.normal(0, 0.01, n)
    forecast = rolling_var_forecast(returns, window=250, alpha=0.95)
    vb = var_backtest(returns, forecast, alpha=0.95)
    assert vb.n == n - 250   # the warm-up window is dropped as NaN
    assert 0.03 < vb.breach_rate < 0.07   # close to the nominal 5%
    assert vb.kupiec_p > 0.05
    assert vb.christoffersen_p is None or vb.christoffersen_p > 0.01
    assert vb.conditional_coverage_p is None or vb.conditional_coverage_p > 0.01


def test_var_backtest_flags_clustered_breaches_even_at_the_right_rate():
    """Same total breach count, same nominal rate; only whether they cluster differs."""
    n = 200
    clustered = np.zeros(n)
    clustered[80:90] = -0.05             # all 10 breaches in one run
    spread = np.zeros(n)
    spread[np.arange(0, n, 20)] = -0.05  # the same 10 breaches, evenly spaced
    forecast = np.full(n, 0.01)
    vb_clustered = var_backtest(clustered, forecast, alpha=0.95)
    vb_spread = var_backtest(spread, forecast, alpha=0.95)
    assert vb_clustered.breaches == vb_spread.breaches == 10
    assert vb_clustered.kupiec_p == pytest.approx(vb_spread.kupiec_p)   # coverage is identical...
    assert vb_clustered.christoffersen_p < vb_spread.christoffersen_p   # ...independence is not
    assert vb_clustered.christoffersen_p < 0.05   # clustered breaches reject independence


def test_var_backtest_edge_cases_never_crash():
    forecast = np.full(50, 0.01)
    zero = var_backtest(np.zeros(50), forecast)   # no breaches at all
    assert zero.breaches == 0 and math.isfinite(zero.kupiec_lr) and zero.christoffersen_p is None
    one = var_backtest(np.where(np.arange(50) == 10, -0.05, 0.0), forecast)   # exactly one breach
    assert one.breaches == 1 and one.christoffersen_p is None   # too few breaches to test clustering
    assert var_backtest(np.array([]), np.array([])).n == 0
    with pytest.raises(ValueError):
        var_backtest([1, 2, 3], [1, 2])
    # NaN pairs (e.g. the warm-up window) are dropped, not propagated
    r = np.concatenate([[np.nan] * 5, np.zeros(45)])
    vb = var_backtest(r, forecast)
    assert vb.n == 45


def test_rolling_var_forecast_has_no_look_ahead():
    rng = np.random.default_rng(1)
    r = rng.normal(0, 0.01, 400)
    base = rolling_var_forecast(r, window=250)
    assert np.isnan(base[:250]).all() and not np.isnan(base[250:]).any()
    perturbed = r.copy()
    perturbed[300] *= 100   # a huge outlier at t=300
    again = rolling_var_forecast(perturbed, window=250)
    assert np.array_equal(again[:300], base[:300], equal_nan=True)   # forecasts before t=300 unchanged
    assert not np.isnan(again[300])
    assert again[301] != base[301]   # but t=300's outlier now enters the window used at t=301+


# --------------------------------------------------------- book-level risk
def _corr_returns(n=250, corr=0.95, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2023-01-02", periods=n)
    common = rng.normal(0, 0.01, n)
    # two series with the target correlation via a shared factor
    idio_a = rng.normal(0, 0.01, n)
    idio_b = rng.normal(0, 0.01, n)
    f = corr
    a = f * common + np.sqrt(max(0.0, 1 - f * f)) * idio_a
    b = f * common + np.sqrt(max(0.0, 1 - f * f)) * idio_b
    return pd.DataFrame({"A": a, "B": b}, index=idx)


def test_book_var_95_matches_the_weighted_series():
    from agentic_trader import quant
    rets = _corr_returns()
    w = {"A": 0.6, "B": 0.4}
    got = book_var_95(w, rets)
    expected = quant.historical_var((rets[["A", "B"]].to_numpy() @ np.array([0.6, 0.4])), 0.95)
    assert got == pytest.approx(expected)
    assert book_var_95({"A": 0.6, "NOPE": 0.4}, rets) == pytest.approx(
        quant.historical_var(rets["A"].to_numpy() * 0.6, 0.95))
    assert book_var_95({"NOWHERE": 1.0}, rets) is None
    assert book_var_95({"A": 0.1}, rets.iloc[:5]) is None   # too few observations


def test_book_var_scale_leaves_room_within_budget():
    rets = _corr_returns(corr=0.2)
    other = {"A": 0.3}
    limit = book_var_95({"A": 0.3, "B": 1.0}, rets) + 0.05   # generous: the full weight fits
    w, after, note = book_var_scale("B", 0.5, other, rets, limit)
    assert w == 0.5 and note is None and after is not None


def test_book_var_scale_shrinks_a_correlated_addition():
    rets = _corr_returns(corr=0.97)
    other = {"A": 0.8}
    tight = book_var_95({"A": 0.8}, rets) * 1.05   # just above the book's VaR with A alone
    w, after, note = book_var_scale("B", 0.8, other, rets, tight)
    assert 0 <= w < 0.8 and note is not None and "book VaR limit" in note
    assert after is not None and after <= tight + 1e-9


def test_book_var_scale_flattens_when_already_over_budget():
    rets = _corr_returns(corr=0.9)
    other = {"A": 1.0}
    already_over = book_var_95({"A": 1.0}, rets) * 0.5   # A alone already breaches this
    w, after, note = book_var_scale("B", 0.5, other, rets, already_over)
    assert w == 0.0 and "already exceeds" in note


def test_book_var_scale_off_or_zero_weight_is_a_no_op():
    rets = _corr_returns()
    w, after, note = book_var_scale("B", 0.5, {"A": 1.0}, rets, None)
    assert w == 0.5 and note is None
    w, after, note = book_var_scale("B", 0.0, {"A": 1.0}, rets, 0.001)
    assert w == 0.0 and note is None


def test_scan_enforces_book_level_var_when_configured():
    cfg = make_config(CFG, risk={"max_book_var_95": 0.0005})   # absurdly tight: always binds
    g = _graph(cfg)
    df = g.scan(["AAPL", "MSFT"], "2024-03-01", positions={"AAPL": 0.5, "MSFT": 0.5})
    assert not df.error.any()
    assert df.adjustments.str.contains("book VaR").any()
    # the same scan with the check off never mentions book VaR
    off = _graph(CFG).scan(["AAPL", "MSFT"], "2024-03-01", positions={"AAPL": 0.5, "MSFT": 0.5})
    assert not off.adjustments.str.contains("book VaR").any()


def test_propagate_without_book_is_unaffected_even_with_the_cap_on():
    """A standalone propagate() (no book=) never builds one on its own -- only scan() does --
    so setting max_book_var_95 alone must not change single-instrument behaviour."""
    cfg = make_config(CFG, risk={"max_book_var_95": 0.0005})
    state, dec = _graph(cfg).propagate("AAPL", "2024-03-01")
    assert state.book is None
    assert not any("book VaR" in a for a in dec.adjustments)


def test_book_field_is_excluded_from_the_llm_prompt():
    """The raw Book (a DataFrame) must never reach fmt_facts/the prompt -- only the two
    plain-float book_var facts do -- so a book-aware decision costs no extra tokens and
    never leaks other instruments' return series into this instrument's prompt."""
    from agentic_trader.agents.base import fmt_facts
    from agentic_trader.agents.risk import risk_facts
    cfg = make_config(CFG, risk={"max_book_var_95": 0.02})
    ins = Instrument.parse("AAPL")
    hist = _graph(cfg).provider.history(ins, pd.Timestamp("2023-01-01").date(), pd.Timestamp("2024-03-01").date())
    from datetime import date as _date
    from agentic_trader.state import TradingState
    book = Book({"MSFT": 0.3}, _corr_returns())
    st = TradingState(ins, _date(2024, 3, 1), hist[hist.index <= pd.Timestamp("2024-03-01")],
                      current_weight=0.1, book=book)
    f = risk_facts(st, cfg)
    assert "book_var_95_now" in f and isinstance(f["book_var_95_now"], (float, type(None)))
    rendered = fmt_facts(st.prompt_facts(f))
    assert "MSFT" not in rendered and "DataFrame" not in rendered


# ------------------------------------------------------------------ CI config
def _workflow_steps(text: str) -> dict[str, str]:
    """``name -> body`` of every ``- name:`` step in a GitHub workflow, by indentation alone
    (no PyYAML: the dev extra does not install it, and an ``importorskip`` here made this
    test skip in the very CI it guards)."""
    steps, name, body = {}, None, []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- name:"):
            if name is not None:
                steps[name] = "\n".join(body)
            name, body = stripped.split(":", 1)[1].strip(), []
        elif name is not None:
            body.append(line)
    if name is not None:
        steps[name] = "\n".join(body)
    return steps


def test_ci_collects_coverage_as_a_report_not_a_gate():
    text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    python_job = text.split("\n  python:", 1)[1].split("\n  lock:", 1)[0]   # the python matrix job only
    steps = _workflow_steps(python_job)
    run_tests = steps["Run tests"]
    assert "--cov=agentic_trader" in run_tests
    assert "--cov-fail-under" not in run_tests   # a report, never a merge-blocking gate
    assert "path: coverage.xml" in steps["Upload coverage report"]


# ---------------------------------------------------------- job timing
def test_evaluate_records_per_job_timings(tmp_path):
    from agentic_trader.evaluation import EvaluationResult, evaluate
    res = evaluate(["AAPL", "MSFT", "EUR/XYZ"], {"q": ("2024-01-02", "2024-03-28")}, CFG, rebalance_every=10)
    timings = res.meta["timings"]
    assert len(timings) == 3
    assert {t["symbol"] for t in timings} == {"AAPL", "MSFT", "EUR/XYZ"}
    assert all(t["seconds"] >= 0 for t in timings)
    assert any(t["error"] for t in timings) and sum(t["error"] for t in timings) == 1
    slow = res.slowest(2)
    assert len(slow) == 2 and list(slow["seconds"]) == sorted(slow["seconds"], reverse=True)
    # round-trips through JSON (meta is dumped verbatim): every timing value must be a JSON
    # scalar, not a numpy one that json.dumps(default=str) would silently stringify
    res.to_json(tmp_path / "e.json")
    back = EvaluationResult.from_json(tmp_path / "e.json")
    assert back.meta["timings"] == timings
    assert all(type(t["seconds"]) is float and type(t["error"]) is bool for t in back.meta["timings"])


def test_slowest_with_no_timings_is_a_typed_empty_frame():
    from agentic_trader.evaluation import EvaluationResult
    res = EvaluationResult(pd.DataFrame(), {})
    empty = res.slowest()
    assert empty.empty and list(empty.columns) == ["period", "symbol", "run", "seconds", "error"]


def test_cli_evaluate_prints_slowest_jobs(capsys):
    from agentic_trader.cli import main
    assert main(["evaluate", "AAPL,MSFT", "--periods", "q1_2024", "--every", "20"]) == 0
    assert "slowest jobs" in capsys.readouterr().out


# ------------------------------------------------------- execution algo cost model
def test_algo_cost_ratio_vwap_is_always_exactly_one():
    """VWAP matches each slice's participation to the volume curve, which minimises the
    square-root-law sum by construction -- true for any n and any curve shape."""
    for kind, n in [("equity", 78), ("equity", 12), ("fx", 288), ("fx", 5)]:
        assert algo_cost_ratio("vwap", n, kind) == pytest.approx(1.0, abs=1e-9)


def test_algo_cost_ratio_twap_matches_vwap_only_on_a_flat_curve():
    # FX's volume_profile is flat, so ignoring it (TWAP) costs the same as tracking it (VWAP).
    assert algo_cost_ratio("twap", 288, "fx") == pytest.approx(1.0, abs=1e-9)
    # equity's U-shaped curve makes ignoring it strictly worse.
    assert algo_cost_ratio("twap", 78, "equity") > 1.001


def test_algo_cost_ratio_ac_kappa_zero_is_twap_and_cost_is_monotone_beyond_it():
    n, kind = 78, "equity"
    assert algo_cost_ratio("ac", n, kind, kappa=0.0) == pytest.approx(algo_cost_ratio("twap", n, kind), abs=1e-6)
    ratios = [algo_cost_ratio("ac", n, kind, kappa=k) for k in (2.0, 3.0, 5.0, 8.0)]
    assert all(b > a for a, b in zip(ratios, ratios[1:])), ratios
    assert all(r >= 1.0 for r in ratios)


def test_algo_cost_ratio_rejects_pov_and_unknown_algos():
    with pytest.raises(ValueError, match="pov"):
        algo_cost_ratio("pov", 78, "equity")
    with pytest.raises(ValueError):
        algo_cost_ratio("vwip", 78, "equity")


def test_algo_cost_ratio_ignores_kappa_outside_ac():
    # The ratio is dimensionless by construction (algo_cost_ratio takes no size or capital),
    # so the only parameter that could leak between algos is kappa: it must not.
    r1 = algo_cost_ratio("twap", 78, "equity")
    r2 = algo_cost_ratio("twap", 78, "equity", kappa=999.0)  # kappa is unused outside "ac"
    assert r1 == r2
    assert algo_cost_ratio("vwap", 78, "equity", kappa=999.0) == algo_cost_ratio("vwap", 78, "equity")


def test_impact_coefficients_scale_by_execution_algo_and_default_is_unchanged():
    from agentic_trader.backtest import impact_coefficients
    from agentic_trader.data import SyntheticProvider
    provider = SyntheticProvider(CFG)
    ins = Instrument.parse("AAPL")
    full = provider.history(ins, pd.Timestamp("2023-01-01").date(), pd.Timestamp("2024-01-01").date())
    base_cfg = make_config(CFG, costs={"impact_coeff": 1.0})
    k_default = impact_coefficients(full, ins, base_cfg)
    k_explicit_vwap = impact_coefficients(full, ins, make_config(base_cfg, costs={"execution_algo": "vwap"}))
    k_twap = impact_coefficients(full, ins, make_config(base_cfg, costs={"execution_algo": "twap"}))
    k_ac = impact_coefficients(full, ins, make_config(base_cfg, costs={"execution_algo": "ac", "ac_kappa": 5.0}))
    assert k_default is not None and k_twap is not None
    finite = np.isfinite(k_default) & np.isfinite(k_twap) & np.isfinite(k_explicit_vwap)
    assert finite.sum() > 100
    np.testing.assert_allclose(k_default[finite], k_explicit_vwap[finite])
    ratio = algo_cost_ratio("twap", 78, "equity")
    np.testing.assert_allclose(k_twap[finite], k_default[finite] * ratio)
    assert (k_ac[finite] >= k_default[finite]).all()


def test_run_agent_backtest_execution_algo_changes_impact_paid_not_the_default():
    base = run_agent_backtest("AAPL", "2024-01-02", "2024-03-28", CFG, rebalance_every=10)
    twap_cfg = make_config(CFG, costs={"impact_coeff": 1.0, "execution_algo": "twap"})
    vwap_cfg = make_config(CFG, costs={"impact_coeff": 1.0})
    base_impact = run_agent_backtest("AAPL", "2024-01-02", "2024-03-28", vwap_cfg, rebalance_every=10)
    twap_impact = run_agent_backtest("AAPL", "2024-01-02", "2024-03-28", twap_cfg, rebalance_every=10)
    assert all(r.impact_paid == 0.0 for r in base.results.values())
    for name in base_impact.results:
        if base_impact.results[name].impact_paid > 0:
            assert twap_impact.results[name].impact_paid > base_impact.results[name].impact_paid


# ------------------------------------------------------------------- CLI
def test_cli_stats_var_backtest(tmp_path, capsys):
    from agentic_trader.cli import main
    path = tmp_path / "r.csv"
    pd.DataFrame({"r": np.random.default_rng(0).normal(0.0004, 0.01, 600)},
                 index=pd.bdate_range("2021-01-01", periods=600)).to_csv(path)
    assert main(["stats", str(path), "--var-backtest", "--var-window", "100"]) == 0
    out = capsys.readouterr().out
    assert "VaR coverage" in out and "kupiec_p" in out and "christoffersen_p" in out


def test_cli_backtest_execution_algo(capsys):
    from agentic_trader.cli import main
    assert main(["backtest", "AAPL", "--start", "2024-01-02", "--end", "2024-03-28",
                 "--every", "10", "--impact", "1.0", "--capital", "1e9",
                 "--execution-algo", "twap"]) == 0
    twap_out = capsys.readouterr().out
    assert main(["backtest", "AAPL", "--start", "2024-01-02", "--end", "2024-03-28",
                 "--every", "10", "--impact", "1.0", "--capital", "1e9"]) == 0
    vwap_out = capsys.readouterr().out
    assert "Impact%" in twap_out and "Impact%" in vwap_out and twap_out != vwap_out
    assert main(["backtest", "AAPL", "--start", "2024-01-02", "--end", "2024-03-28",
                 "--ac-kappa", "-1"]) == 2


# ------------------------------------------------------------- risk edge case
def test_conservative_risk_view_survives_zero_var():
    """historical_var is always >= 0 (max(0, -quantile)), so the conservative stance's VaR
    scaling can never divide by zero: locking that invariant in, since it depends on knowing
    quant.historical_var's sign convention rather than being obvious from risk.py alone."""
    from agentic_trader.agents.risk import RiskAnalyst
    an = RiskAnalyst(None, CFG, "conservative")
    f = {"proposed_weight": 0.5, "realized_vol_20d_annual": 0.2, "target_vol": 0.15,
         "max_position": 1.0, "var_95_1d": 0.0, "max_var_95": 0.02}
    w = an.rules_weight(f)   # must not raise ZeroDivisionError
    assert np.isfinite(w)
    f["var_95_1d"] = float("nan")
    assert np.isfinite(an.rules_weight(f))
