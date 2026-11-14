"""v0.14 items 5.1-5.3 and the purged-IC gate: Student-t bar, IC combination, regime HMM,
split-conformal sizing. Offline only (synthetic data, no network)."""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from agentic_trader.alpha import _alpha_diagnostics, significant_alpha_signal
from agentic_trader.combine import (
    conformal_halfwidth,
    desk_forecast,
    james_stein_factor,
    ledoit_wolf,
    mean_variance,
    signal_panel,
    trailing_ics,
    turnover_penalised,
)
from agentic_trader.config import make_config
from agentic_trader.data.synthetic import SyntheticProvider
from agentic_trader.evaluation import TRIALS
from agentic_trader.graph import TradingGraph
from agentic_trader.instruments import Instrument
from agentic_trader.leakage import PurgedIC, future_leak_canary, passes_gate, scored_mask, student_t_crit, student_t_sf
from agentic_trader.regime import fit_hmm, regime_labels
from agentic_trader.xalpha import ic_summary

NAN = float("nan")

# ------------------------------------------------------------------ Student-t gate


@pytest.mark.parametrize(
    "df,crit", [(1, 12.706204736), (3, 3.182446305), (4, 2.776445105), (30, 2.042272456), (1000, 1.962339081)]
)
def test_student_t_critical_values_match_tables(df, crit):
    assert student_t_crit(df) == pytest.approx(crit, abs=1e-8)
    assert 2 * student_t_sf(crit, df) == pytest.approx(0.05, abs=1e-10)


def test_student_t_sf_is_symmetric_and_rejects_bad_arguments():
    assert student_t_sf(0.0, 4) == pytest.approx(0.5)
    assert student_t_sf(-1.3, 7) == pytest.approx(1 - student_t_sf(1.3, 7))
    with pytest.raises(ValueError):
        student_t_sf(1.0, 0)
    with pytest.raises(ValueError):
        student_t_crit(4, 1.5)


def test_t_crit_uses_the_finite_folds_actually_used():
    five = PurgedIC(0.05, 3.0, 400, (0.04, 0.05, 0.06, 0.05, 0.05))
    four = PurgedIC(0.05, 3.0, 320, (NAN, 0.04, 0.06, 0.05, 0.05))  # warm-up left fold 0 empty
    two = PurgedIC(0.05, NAN, 160, (NAN, NAN, NAN, 0.04, 0.06))
    assert five.k == 5 and five.t_crit == pytest.approx(2.776445105)
    assert four.k == 4 and four.t_crit == pytest.approx(3.182446305)
    assert five.significant and not four.significant  # 3.0 clears 2.78, not 3.18
    assert math.isnan(two.t_crit) and not two.significant
    assert not passes_gate(two.as_gate(), min_n=30)  # < 3 folds: the gate refuses
    assert passes_gate(five.as_gate(), min_n=30) and not passes_gate(four.as_gate(), min_n=30)


def test_gate_holds_purged_entries_to_their_student_t_bar():
    latest = {"a": 1.0, "b": -1.0}
    # t = 2.5 cleared the old |t| >= 2 bar; at 4 df the 5% bar is 2.776
    ic = {
        "a": {"IC": 0.1, "t(IC)": 2.5, "n": 200, "t_crit": student_t_crit(4)},
        "b": {"IC": 0.1, "t(IC)": 2.9, "n": 200, "t_crit": student_t_crit(4)},
    }
    comb, names = significant_alpha_signal(latest, ic)
    assert names == ["b"] and comb == pytest.approx(-1.0)
    # a hand-built entry with no fold count keeps the fallback bar
    assert passes_gate({"IC": 0.1, "t(IC)": 2.5, "n": 200})
    assert not passes_gate({"IC": NAN, "t(IC)": 5.0, "n": 200})


def test_alpha_diagnostics_measure_every_column_on_the_scored_pairs():
    rng = np.random.default_rng(3)
    n, h = 300, 10
    s = rng.normal(size=n)
    fwd = rng.normal(size=n)
    row = _alpha_diagnostics(s, fwd, h)
    m = scored_mask(n, h)
    assert row["n"] == int(m.sum()) < n
    assert row["hit%"] == pytest.approx(100 * np.mean(np.sign(s[m]) == np.sign(fwd[m])))
    assert row["up%"] == pytest.approx(100 * np.mean(fwd[m] > 0))
    # the unscored positions are where a pooled hit rate would differ: make them all hits
    s2, f2 = s.copy(), fwd.copy()
    f2[~m] = np.abs(f2[~m]) * np.sign(s2[~m])
    assert _alpha_diagnostics(s2, f2, h)["hit%"] == pytest.approx(row["hit%"])


def test_ic_summary_columns_share_the_scored_dates():
    n, h = 300, 10
    m = scored_mask(n, h)
    v = np.where(m, -0.05, 0.5) + np.random.default_rng(1).normal(0, 0.01, n)
    out = ic_summary(pd.Series(v), h)
    assert out["days"] == int(m.sum())
    assert out["IC>0%"] == pytest.approx(0.0)  # the positive dates are all unscored
    assert out["IC IR"] < 0 and out["mean IC"] < 0


# ------------------------------------------------------------------ 5.1 combination


def _gbm(n: int, seed: int, vol: float = 0.012) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, vol, n)))
    idx = pd.bdate_range("2010-01-04", periods=n)
    hi, lo = close * 1.005, close * 0.995
    return pd.DataFrame({"Open": close, "High": hi, "Low": lo, "Close": close, "Volume": 1e6}, index=idx)


CFG = {"window": 504, "horizon": 10, "risk_aversion": 2.5, "turnover_penalty": 0.0005}
EQ = Instrument.parse("AAPL")


def test_james_stein_factor_is_zero_unless_significant():
    assert james_stein_factor(PurgedIC(0.05, 2.0, 400, (0.1,) * 5)) == 0.0
    big = PurgedIC(0.05, 10.0, 400, (0.1,) * 5)
    assert james_stein_factor(big) == pytest.approx(1 - (student_t_crit(4) / 10.0) ** 2)
    assert james_stein_factor(PurgedIC(NAN, NAN, 0, ())) == 0.0


def test_pure_noise_signals_shrink_the_tilt_to_about_zero():
    """Ten iid noise signals against a random walk: the shrunk IC is exactly zero for about
    95% of them (the 5% test's false-positive rate), so the combined tilt, sum IC x z, is a
    small fraction of what the unshrunk ICs would give."""
    zero, total, shrunk_tilt, raw_tilt = 0, 0, [], []
    for seed in range(20):
        df = _gbm(800, seed)
        rng = np.random.default_rng(100 + seed)
        sig = pd.DataFrame(rng.normal(size=(800, 10)), index=df.index, columns=[f"n{i}" for i in range(10)])
        est = trailing_ics(sig, df["Close"].to_numpy(float), 10, 504)
        z = sig.iloc[-1].to_numpy()
        shrunk = np.array([est[c][0] for c in sig.columns])
        raw = np.array([est[c][1].ic for c in sig.columns])
        zero += int((shrunk == 0).sum())
        total += shrunk.size
        shrunk_tilt.append(abs(shrunk @ z))
        raw_tilt.append(abs(raw @ z))
    assert zero / total >= 0.9
    assert np.mean(shrunk_tilt) < 0.2 * np.mean(raw_tilt)


def test_a_real_signal_survives_the_shrinkage():
    rng = np.random.default_rng(7)
    n = 1100
    # a 20-day trend in the drift: momentum genuinely predicts the next ten days
    drift = np.repeat(rng.choice([-1, 1], n // 40 + 1), 40)[:n] * 0.004
    close = 100 * np.exp(np.cumsum(drift + rng.normal(0, 0.006, n)))
    df = pd.DataFrame(
        {"Open": close, "High": close * 1.003, "Low": close * 0.997, "Close": close, "Volume": 1e6},
        index=pd.bdate_range("2010-01-04", periods=n),
    )
    f = desk_forecast(df, EQ, CFG)
    assert f.active and all(f.t_stats[k] > 0 or f.weights[k] < 0 for k in f.active)


def test_trailing_ics_never_read_past_the_as_of_bar():
    df = _gbm(1100, 4)
    close = df["Close"].to_numpy(float)
    sig = signal_panel(df, EQ)
    end = 900
    a = trailing_ics(sig, close, 10, 504, end)
    future = close.copy()
    future[end + 1 :] *= 3.0  # a shock after the as-of bar
    sig_f = sig.copy()
    sig_f.iloc[end + 1 :] = 1.0
    b = trailing_ics(sig_f, future, 10, 504, end)
    assert {k: v[0] for k, v in a.items()} == {k: v[0] for k, v in b.items()}
    # the as-of bar's own forward return is not known yet: changing it changes nothing either
    future2 = close.copy()
    future2[end] *= 1.5
    c = trailing_ics(sig, future2, 10, 504, end - 1)
    d = trailing_ics(sig, close, 10, 504, end - 1)
    assert c.keys() == d.keys()
    assert all(np.array_equal(c[k][1].folds, d[k][1].folds, equal_nan=True) for k in c)


def test_ledoit_wolf_shrinks_toward_scaled_identity():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(30, 20))  # T barely above N: sample cov is noisy
    cov, delta = ledoit_wolf(x)
    assert 0.0 < delta <= 1.0
    assert np.all(np.linalg.eigvalsh(cov) > 0)
    assert np.allclose(cov, cov.T)
    big = rng.normal(size=(5000, 3)) @ np.diag([1.0, 2.0, 3.0])
    cov_b, delta_b = ledoit_wolf(big)
    assert delta_b < 0.05  # plenty of data: little shrinkage
    w = mean_variance(np.array([0.01, 0.02, 0.03]), cov_b, 2.0)
    assert w == pytest.approx(np.linalg.solve(cov_b, [0.01, 0.02, 0.03]) / 2.0)
    with pytest.raises(ValueError):
        ledoit_wolf(np.array([[1.0, np.nan], [0.0, 1.0]]))
    with pytest.raises(ValueError):
        mean_variance(np.ones(2), np.eye(2), 0.0)


def test_turnover_penalty_is_the_exact_l1_solution():
    v, g, k = 0.0016, 2.5, 0.0005
    margin = k / (g * v)
    assert turnover_penalised(0.30, 0.25, v, g, k) == 0.25  # inside the margin: hold
    assert turnover_penalised(0.80, 0.0, v, g, k) == pytest.approx(0.80 - margin)
    assert turnover_penalised(-0.80, 0.0, v, g, k) == pytest.approx(-0.80 + margin)
    assert turnover_penalised(0.8, 0.0, v, g, 0.0) == 0.8
    # brute force on a grid agrees with the closed form
    mu = 0.8 * g * v
    grid = np.linspace(-1, 1, 200001)
    obj = mu * grid - 0.5 * g * v * grid**2 - k * np.abs(grid - 0.1)
    assert turnover_penalised(0.8, 0.1, v, g, k) == pytest.approx(grid[obj.argmax()], abs=1e-4)


# ------------------------------------------------------------------ 5.3 conformal


def test_conformal_halfwidth_covers_at_the_nominal_rate():
    rng = np.random.default_rng(11)
    hits = []
    for _ in range(400):
        cal = rng.normal(size=60)
        q = conformal_halfwidth(cal, 0.2)
        hits.append(abs(rng.normal()) <= q)
    assert np.mean(hits) == pytest.approx(0.8, abs=0.05)
    assert conformal_halfwidth(np.ones(3), 0.2) is None  # rank ceil(4 * 0.8) = 4 > 3


def test_conformal_sizing_calibrates_strictly_before_the_forecast():
    df = _gbm(1100, 5)
    cfg = {**CFG, "conformal": {"enabled": True, "alpha": 0.2, "calibration_share": 0.4}}
    f = desk_forecast(df, EQ, cfg)
    assert f.interval is not None and f.interval > 0
    assert 0.0 <= f.size_scale() <= 1.0
    # the forecast at bar i is a function of bars <= i only: appending later bars to the
    # frame and cutting them off again reproduces it exactly
    g = desk_forecast(df.iloc[:900], EQ, cfg)
    h = desk_forecast(pd.concat([df.iloc[:900], df.iloc[900:] * 2.0]).iloc[:900], EQ, cfg)
    assert (g.mu, g.interval) == (h.mu, h.interval)
    # too short a window for any calibration point sizes to zero
    tiny = desk_forecast(df, EQ, {**cfg, "window": 40})
    assert tiny.size_scale() in (0.0, 1.0) and (tiny.interval == math.inf or tiny.mu == 0.0)


# ------------------------------------------------------------------ 5.2 regime


def _two_regime(n: int = 1500, seed: int = 2) -> tuple[pd.Series, np.ndarray]:
    rng = np.random.default_rng(seed)
    state = np.repeat(rng.integers(0, 2, n // 150 + 1), 150)[:n]
    r = rng.normal(0, np.where(state == 1, 0.03, 0.006))
    close = pd.Series(100 * np.exp(np.cumsum(r)), index=pd.bdate_range("2005-01-03", periods=n))
    return close, state


def test_hmm_recovers_volatility_regimes_and_orders_them_calm_first():
    close, state = _two_regime()
    lab, probs, model = regime_labels(close, None, 2, None, close.index[-1])
    ok = lab >= 0
    acc = np.mean(lab[ok] == state[ok])
    assert acc > 0.85
    assert model.means[0, 0] < model.means[1, 0]
    assert probs is not None and probs.sum() == pytest.approx(1.0)
    assert np.allclose(model.trans.sum(axis=1), 1.0)


def test_regime_labels_are_filtered_not_smoothed():
    close, _ = _two_regime()
    fit_end = close.index[800]
    full, _, _ = regime_labels(close, None, 2, None, fit_end)
    part, _, _ = regime_labels(close.iloc[:1000], None, 2, None, fit_end)
    assert np.array_equal(full[:1000], part)  # later bars never change an earlier label


def test_fit_hmm_rejects_bad_input():
    with pytest.raises(ValueError):
        fit_hmm(np.zeros((5, 2)), 2)
    with pytest.raises(ValueError):
        fit_hmm(np.ones((100, 2)), 4)
    with pytest.raises(ValueError):
        fit_hmm(np.full((100, 2), np.nan), 2)


# ------------------------------------------------------------------ desk wiring


DESK = {"data_provider": "synthetic", "llm_provider": "offline"}


def test_default_config_keeps_the_rules_desk():
    cfg = make_config({})
    assert cfg["combination"]["method"] == "rules"
    assert not cfg["regime"]["enabled"] and not cfg["conformal"]["enabled"]
    st, _ = TradingGraph(DESK, on_event=lambda *a: None).propagate("AAPL", date(2023, 3, 1))
    assert st.forecast is None and st.regime == {}
    assert "[regime]" not in st.reports_digest()


def test_switches_validate_their_dependencies():
    for bad in (
        {"combination": {"method": "magic"}},
        {"conformal": {"enabled": True}},
        {"regime": {"enabled": True, "condition": True}},
    ):
        g = TradingGraph({**DESK, **bad}, on_event=lambda *a: None)
        with pytest.raises(ValueError):
            g.prepare("AAPL", date(2023, 3, 1))


def test_ic_desk_sizes_from_the_forecast_and_exposes_the_regime():
    cfg = {
        **DESK,
        "combination": {"method": "ic"},
        "regime": {"enabled": True, "condition": True, "fit_start": "2018-01-01"},
        "conformal": {"enabled": True},
    }
    st, dec = TradingGraph(cfg, on_event=lambda *a: None).propagate("AAPL", date(2023, 3, 1))
    assert st.forecast is not None and st.forecast.regime == st.regime["label"]
    assert st.regime["name"] in ("calm", "stressed") and "[regime]" in st.reports_digest()
    assert "IC-combination weight" in dec.rationale


def test_v14_trials_are_registered_with_their_switches():
    v14 = [t for t in TRIALS if t.version == "v0.14"]
    assert len(v14) == 3 and all(t.overrides["combination"] == {"method": "ic", "window": 504} for t in v14)
    assert v14[1].overrides["regime"]["condition"] and v14[2].overrides["conformal"]["enabled"]


@pytest.mark.parametrize(
    "extra", [{}, {"regime": {"enabled": True, "condition": True, "fit_start": "2018-01-01"}, "conformal": {"enabled": True}}]
)
def test_ic_desk_passes_the_future_leak_canary(extra):
    cfg = {"data_provider": "synthetic", "analysts": None, "alpha_lookback_days": 700, "combination": {"method": "ic"}, **extra}
    res = future_leak_canary(
        make_config(cfg),
        SyntheticProvider(make_config({})),
        "AAPL",
        date(2023, 6, 1),
        before=[date(2023, 5, 1), date(2023, 5, 30)],
        after=[date(2023, 6, 20)],
    )
    assert res.clean, res.leaks
    assert res.reacted
