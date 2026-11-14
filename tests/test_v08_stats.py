"""v0.8 statistics fixes: the cross-instrument bootstrap resamples correlated *clusters*
(review findings 4 and 54), and Benjamini-Hochberg runs on unrounded p-values over the
rows that were actually tested (finding 80)."""
import math

import numpy as np
import pandas as pd
import pytest

from agentic_trader import stats
from agentic_trader.backtest import AGENT
from agentic_trader.evaluation import EvaluationResult
from agentic_trader.stats import MIN_CLUSTER_GROUPS, PairedBootstrap, benjamini_hochberg, paired_bootstrap


def _labels(sizes):
    return np.array(sum([[f"g{i}"] * n for i, n in enumerate(sizes)], []))


def _common_factor_draw(rng, sizes, rho):
    """Per-instrument differences with a true mean of zero and a factor shared inside each
    group: corr(d_i, d_j) = rho within a group, 0 across groups."""
    return np.concatenate([math.sqrt(rho) * rng.normal() + math.sqrt(1 - rho) * rng.normal(size=n) for n in sizes])


# ------------------------------------------------------------- finding 4: cluster scheme
def test_cluster_bootstrap_coverage_under_a_common_factor_is_closer_to_nominal_than_plain():
    """Monte Carlo: true mean difference 0, a factor shared inside each of six groups. Plain
    instrument resampling treats the shared shock as six independent draws and covers zero
    far less often than 95%; the cluster scheme carries the shock into the interval. Fixed
    seed and a modest n_boot keep this a unit test rather than a study; the numbers below are
    from that seed (plain about 0.65, clusters about 0.90 at rho=0.6)."""
    sizes = [6] * 6
    groups = _labels(sizes)
    rng = np.random.default_rng(2024)
    n_mc, covered, false_pos = 150, {"instruments": 0, "clusters": 0}, {"instruments": 0, "clusters": 0}
    for _ in range(n_mc):
        d = _common_factor_draw(rng, sizes, rho=0.6)
        zero = np.zeros_like(d)
        for name, g in (("instruments", None), ("clusters", groups)):
            pb = paired_bootstrap(d, zero, n_boot=400, seed=1, groups=g)
            assert pb.scheme == name
            covered[name] += pb.ci_low <= 0.0 <= pb.ci_high
            false_pos[name] += pb.p_value < 0.05
    cov = {k: v / n_mc for k, v in covered.items()}
    fp = {k: v / n_mc for k, v in false_pos.items()}
    assert cov["instruments"] < 0.80, cov                      # the defect: plain is badly anti-conservative here
    assert cov["clusters"] > cov["instruments"] + 0.15, cov
    assert abs(cov["clusters"] - 0.95) < abs(cov["instruments"] - 0.95), cov
    assert fp["clusters"] < fp["instruments"] / 2, fp


def test_cluster_bootstrap_is_not_anti_conservative_when_groups_are_independent():
    """rho = 0: the groups carry no shared shock, so plain resampling is already right and
    the cluster scheme must not undercut it (it errs wide, never narrow)."""
    sizes = [6] * 6
    groups = _labels(sizes)
    rng = np.random.default_rng(7)
    n_mc, covered = 120, {"instruments": 0, "clusters": 0}
    for _ in range(n_mc):
        d = _common_factor_draw(rng, sizes, rho=0.0)
        for name, g in (("instruments", None), ("clusters", groups)):
            pb = paired_bootstrap(d, np.zeros_like(d), n_boot=400, seed=1, groups=g)
            covered[name] += pb.ci_low <= 0.0 <= pb.ci_high
    assert covered["clusters"] / n_mc >= 0.90
    assert covered["clusters"] >= covered["instruments"] - 3


def test_cluster_bootstrap_needs_five_groups_and_reports_the_fallback():
    rng = np.random.default_rng(3)
    d = _common_factor_draw(rng, [5] * 6, rho=0.5)
    zero = np.zeros_like(d)
    assert MIN_CLUSTER_GROUPS == 5
    for n_groups in (2, 3, 4):
        groups = _labels([30 // n_groups + (1 if i < 30 % n_groups else 0) for i in range(n_groups)])
        grouped = paired_bootstrap(d, zero, n_boot=2000, seed=5, groups=groups)
        plain = paired_bootstrap(d, zero, n_boot=2000, seed=5)
        assert grouped.scheme == "instruments" and grouped.n_groups == n_groups
        assert (grouped.ci_low, grouped.ci_high, grouped.p_value) == (plain.ci_low, plain.ci_high, plain.p_value)
    five = paired_bootstrap(d, zero, n_boot=2000, seed=5, groups=_labels([6] * 5))
    assert five.scheme == "clusters" and five.n_groups == 5
    # the threshold is a parameter: a caller who accepts four clusters can say so
    four = paired_bootstrap(d, zero, n_boot=2000, seed=5, groups=_labels([8, 8, 7, 7]), min_groups=4)
    assert four.scheme == "clusters" and four.n_groups == 4
    # groups are counted among the *finite* pairs: a group whose only member is NaN does not count
    a = np.concatenate([d, [np.nan]])
    labels = np.concatenate([_labels([6] * 5), ["ghost"]])
    assert paired_bootstrap(a, np.zeros_like(a), n_boot=200, groups=labels).n_groups == 5
    assert paired_bootstrap([1.0, 2.0], [0.0, 0.0], groups=["a", "b"]).n_groups == 2


def test_cluster_bootstrap_result_is_deterministic_and_a_proper_interval():
    rng = np.random.default_rng(11)
    d = _common_factor_draw(rng, [10, 9, 5, 6, 4], rho=0.5)
    groups = _labels([10, 9, 5, 6, 4])
    one = paired_bootstrap(d, np.zeros_like(d), n_boot=3000, seed=1, groups=groups)
    again = paired_bootstrap(d, np.zeros_like(d), n_boot=3000, seed=1, groups=groups)
    assert one == again
    assert one.ci_low < one.mean_diff < one.ci_high and 0.0 <= one.p_value <= 1.0
    assert one.n == 34 and one.wins == int((d > 0).sum())
    other_seed = paired_bootstrap(d, np.zeros_like(d), n_boot=3000, seed=2, groups=groups)
    assert abs(one.ci_low - other_seed.ci_low) < 0.1 and abs(one.ci_high - other_seed.ci_high) < 0.1


# ------------------------------------------- finding 54: grouping is visibly applied
def test_cluster_scheme_gives_a_different_answer_from_plain_on_a_designed_fixture():
    """Six clusters whose means differ far more than their members do: resampling clusters
    exposes the between-cluster spread, resampling instruments hides most of it. A regression
    that silently drops ``groups`` makes every assertion here fail."""
    rng = np.random.default_rng(9)
    centres = np.array([0.6, -0.4, 0.5, -0.3, 0.4, -0.2])
    d = np.concatenate([c + rng.normal(0, 0.02, 5) for c in centres])
    groups = _labels([5] * 6)
    clustered = paired_bootstrap(d, np.zeros_like(d), n_boot=5000, seed=1, groups=groups)
    plain = paired_bootstrap(d, np.zeros_like(d), n_boot=5000, seed=1)
    assert clustered.scheme == "clusters" and clustered.n_groups == 6
    assert clustered.mean_diff == pytest.approx(plain.mean_diff)
    assert clustered.ci_high - clustered.ci_low > 1.5 * (plain.ci_high - plain.ci_low)
    assert clustered.p_value > plain.p_value
    assert clustered.ci_low != plain.ci_low and clustered.ci_high != plain.ci_high


def _five_group_result():
    rows = []
    rng = np.random.default_rng(5)
    universe = [("equity", "core", ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"]),
                ("fx", "core", ["EURUSD", "USDJPY", "GBPUSD", "AUDUSD"]),
                ("equity", "extended", ["JPM", "XOM", "JNJ", "PG", "KO"]),
                ("equity", "extended-macro", ["TLT", "IEF", "LQD", "HYG", "GLD"]),
                ("fx", "extended", ["NZDUSD", "USDCHF", "EURGBP", "EURJPY"])]
    for k, (ac, uni, syms) in enumerate(universe):
        shock = rng.normal(0, 0.4)
        for sym in syms:
            rows.append({"period": "q", "symbol": sym, "asset_class": ac, "universe": uni,
                         "strategy": AGENT, "Sharpe": 0.5 + shock + rng.normal(0, 0.05)})
            rows.append({"period": "q", "symbol": sym, "asset_class": ac, "universe": uni,
                         "strategy": "Buy&Hold", "Sharpe": 0.5})
    return EvaluationResult(pd.DataFrame(rows), {}), universe


def test_evaluation_paired_uses_the_cluster_scheme_with_five_groups_and_it_changes_the_answer():
    res, _ = _five_group_result()
    clustered = res.paired("Buy&Hold", period="q")
    plain = res.paired("Buy&Hold", period="q", cluster=False)
    assert clustered.scheme == "clusters" and clustered.n_groups == 5
    assert plain.scheme == "instruments" and plain.n_groups == 0
    assert clustered.n == plain.n == 23 and clustered.mean_diff == pytest.approx(plain.mean_diff)
    assert clustered.ci_low != plain.ci_low and clustered.ci_high != plain.ci_high
    assert clustered.ci_high - clustered.ci_low > plain.ci_high - plain.ci_low
    tab = res.paired_table()
    # review C8: rows only (no daily returns), so the labelled cross-instrument fallback
    assert list(tab.scheme) == ["cross-instrument (clusters); fallback: no daily returns held"] and list(tab.groups) == [5]
    assert list(res.paired_table(cluster=False).scheme) == ["cross-instrument (instruments); fallback: no daily returns held"]


def test_c8_paired_table_uses_the_time_block_primary_when_daily_returns_are_held(tmp_path):
    """Review C8: with daily returns the primary is the time-block interval; differences that load
    on one common daily factor give a much wider primary than the cross-instrument secondary."""
    rng = np.random.default_rng(4)
    days, syms = pd.bdate_range("2024-01-02", periods=250), [f"S{i}" for i in range(12)]
    common = rng.normal(0, 0.01, size=(250, 1))
    base = pd.DataFrame(rng.normal(0.0003, 0.01, size=(250, 12)), index=days, columns=syms)
    agent = base + common + rng.normal(0, 0.001, size=(250, 12))
    rows = [{"period": "q", "symbol": s, "asset_class": "equity", "universe": "core", "strategy": st,
             "Sharpe": float(stats.sharpe_stats(df[s]).sharpe_annual)}
            for s in syms for st, df in (("AgenticTrader", agent), ("Buy&Hold", base))]
    res = EvaluationResult(pd.DataFrame(rows), {}, {"q|AgenticTrader": agent, "q|Buy&Hold": base})
    tab = res.paired_table(n_boot=400)
    r = tab.iloc[0]
    assert r.scheme == "time-block" and r.days == 250 and r.n == 12
    assert "conditional" in r.secondary and r.secondary.endswith("(instruments)")
    assert (r["ci95 high"] - r["ci95 low"]) > 3 * (r["secondary ci95 high"] - r["secondary ci95 low"])
    res.to_json(tmp_path / "a.json")
    assert EvaluationResult.from_json(tmp_path / "a.json").paired_table(n_boot=400).scheme[0].startswith(
        "cross-instrument")
    res.to_json(tmp_path / "b.json", include_returns=True)
    back = EvaluationResult.from_json(tmp_path / "b.json").paired_table(n_boot=400)
    assert back.scheme[0] == "time-block" and back["ci95 low"][0] == r["ci95 low"]


def test_evaluation_paired_passes_the_asset_class_universe_labels_as_groups(monkeypatch):
    res, universe = _five_group_result()
    seen = {}
    real = stats.paired_bootstrap

    def spy(a, b, **kw):
        seen["groups"] = None if kw.get("groups") is None else list(kw["groups"])
        seen["n"] = len(a)
        return real(a, b, **kw)
    monkeypatch.setattr(stats, "paired_bootstrap", spy)
    res.paired("Buy&Hold", period="q")
    label = {sym: f"{ac}:{uni}" for ac, uni, syms in universe for sym in syms}
    expected = [label[s] for s in sorted(label)]   # the pivot orders instruments by symbol
    assert seen["n"] == 23 and seen["groups"] == expected
    res.paired("Buy&Hold", period="q", cluster=False)
    assert seen["groups"] is None


# --------------------------------------------- finding 80: BH on unrounded, tested p only
def test_benjamini_hochberg_counts_only_tested_rows_in_m():
    assert list(benjamini_hochberg([0.02, np.nan, np.nan, np.nan], q=0.05)) == [True, False, False, False]
    assert list(benjamini_hochberg([np.nan, np.nan])) == [False, False]
    # with m = 2 the second threshold is q, not 2/3 q: 0.045 clears it only when NaN is excluded
    assert list(benjamini_hochberg([0.01, 0.045, np.nan], q=0.05)) == [True, True, False]
    # unchanged textbook behaviour on a fully tested set
    p = [0.01, 0.04, 0.03, 0.005, 0.5, 0.7, 0.9, 0.99]
    assert list(benjamini_hochberg(p, q=0.05)) == [True, False, False, True, False, False, False, False]


def test_benjamini_hochberg_is_sensitive_to_the_fourth_decimal():
    p_true = np.array([0.01665, 0.4, 0.6])          # 0.01665 <= 1/3 * 0.05 = 0.016667
    assert list(benjamini_hochberg(p_true)) == [True, False, False]
    assert not benjamini_hochberg(np.round(p_true, 3)).any()   # what the v0.7 table fed it


def _table_with(monkeypatch, fake: dict[str, PairedBootstrap]):
    rows = []
    for i, base in enumerate(fake):
        rows.append({"period": "q", "symbol": f"S{i}", "strategy": AGENT, "universe": "core", "Sharpe": 1.0})
        rows.append({"period": "q", "symbol": f"S{i}", "strategy": base, "universe": "core", "Sharpe": 1.0})
    res = EvaluationResult(pd.DataFrame(rows), {})

    def fake_paired(self, baseline, metric="Sharpe", period=None, universe=None, strategy=AGENT, n_boot=10_000,
                    seed=0, cluster=True):
        return fake[baseline]
    monkeypatch.setattr(EvaluationResult, "paired", fake_paired)
    return res.paired_table().sort_values("baseline").reset_index(drop=True)


def test_paired_table_applies_bh_to_the_unrounded_p(monkeypatch):
    tab = _table_with(monkeypatch, {
        "b0": PairedBootstrap(10, 0.1, 0.01, 0.2, 0.01665, 8),
        "b1": PairedBootstrap(10, 0.0, -0.1, 0.1, 0.4, 5),
        "b2": PairedBootstrap(10, 0.0, -0.1, 0.1, 0.6, 4),
    })
    assert list(tab.p) == [0.017, 0.4, 0.6]                  # displayed at 3 dp
    assert list(tab.significant) == [True, False, False]     # decided on the 5th


def test_paired_table_untested_rows_are_nan_and_do_not_shrink_the_others_threshold(monkeypatch):
    nan = float("nan")
    tab = _table_with(monkeypatch, {
        "b0": PairedBootstrap(12, 0.2, 0.02, 0.4, 0.025, 9),
        "b1": PairedBootstrap(2, 0.3, nan, nan, 1.0, 2),    # fewer than three instruments: never tested
        "b2": PairedBootstrap(2, -0.1, nan, nan, 1.0, 0),
    })
    assert list(tab.n) == [12, 2, 2]
    assert tab.p[0] == 0.025 and np.isnan(tab.p[1]) and np.isnan(tab.p[2])
    assert list(tab.significant) == [True, False, False]     # m = 1, not 3 (which would need p <= 0.0167)


def test_paired_table_columns_carry_the_scheme(monkeypatch):
    tab = _table_with(monkeypatch, {"b0": PairedBootstrap(10, 0.1, 0.01, 0.2, 0.02, 8, "clusters", 5)})
    assert list(tab.columns) == ["period", "baseline", "n", "mean Sharpe diff", "ci95 low", "ci95 high", "p",
                                 "wins", "scheme", "days", "secondary", "secondary ci95 low",
                                 "secondary ci95 high", "secondary p", "groups", "significant"]
    # no daily returns held: the cross-instrument figure is the fallback, and the label says so
    assert tab.scheme[0] == "cross-instrument (clusters); fallback: no daily returns held" and tab.groups[0] == 5


# ---------------------------------- C8 follow-ups (Round 3 part 3, lane c8)
def _two_group_result(with_returns: bool = True):
    rng = np.random.default_rng(7)
    days, syms = pd.bdate_range("2024-01-02", periods=120), [f"S{i}" for i in range(6)]
    base = pd.DataFrame(rng.normal(0.0003, 0.01, size=(120, 6)), index=days, columns=syms)
    agent = base + rng.normal(0, 0.002, size=(120, 6))
    rows = [{"period": "q", "symbol": s, "asset_class": "fx" if i % 2 else "equity", "universe": "core",
             "strategy": st, "Sharpe": float(stats.sharpe_stats(df[s]).sharpe_annual), "MDD%": -1.0 * i}
            for i, s in enumerate(syms) for st, df in (("AgenticTrader", agent), ("Buy&Hold", base))]
    rets = {"q|AgenticTrader": agent, "q|Buy&Hold": base} if with_returns else {}
    return EvaluationResult(pd.DataFrame(rows), {}, rets)


def test_c8_time_block_is_not_gated_by_the_cluster_group_count():
    res = _two_group_result()
    r = res.paired_table(universe="core", n_boot=200).iloc[0]
    assert r.groups < MIN_CLUSTER_GROUPS and r.scheme == "time-block" and r.days == 120


def test_c8_fallback_label_states_the_real_reason():
    assert _two_group_result(False).paired_table(n_boot=200).scheme[0].endswith("fallback: no daily returns held")
    s = _two_group_result().paired_table("MDD%", n_boot=200).scheme[0]
    assert s.startswith("cross-instrument") and s.endswith("fallback: metric is not Sharpe")


def test_c8_render_subset_keeps_daily_returns():
    import importlib.util
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "scripts" / "render_v08_tables.py"
    spec = importlib.util.spec_from_file_location("render_v08_tables", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    res = _two_group_result()
    assert mod.subset(res, ("core",)).paired_table(n_boot=200).scheme[0] == "time-block"


def test_c8_excess_returns_make_a_cash_only_book_sharpe_zero():
    """A strategy flat on an instrument earns rf: raw daily returns are smooth and positive (the
    v0.8 Carry rows read +17.6 on raw returns, giving -12.69 agent minus Carry), excess returns are 0."""
    from types import SimpleNamespace
    from agentic_trader.backtest import ComparisonReport as Report
    n = 300
    rf = np.linspace(0.01, 0.05, n)                    # annual, per bar
    r = np.r_[0.0, rf[:-1] / 252.0]                    # returns[t+1] earns rf[t] / ppy
    rep = SimpleNamespace(results={"Carry": SimpleNamespace(returns=r)}, dates=pd.bdate_range("2020-01-01", periods=n),
                          rf=rf, backtest_config=None, instrument=SimpleNamespace(periods_per_year=252.0))
    rep.returns = lambda: Report.returns(rep)
    raw = rep.returns()["Carry"].iloc[1:].to_numpy()[:, None]
    ex = Report.excess_returns(rep)
    assert len(ex) == n - 1 and np.allclose(ex["Carry"], 0.0)
    assert stats._column_sharpes(raw, 252.0)[0] > 5
    assert stats._column_sharpes(ex.to_numpy(), 252.0)[0] == 0.0
