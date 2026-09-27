"""v0.8 alpha-evaluation fixes (review findings 5 and 29): the time-series IC t-statistic
is overlap-aware for a multi-bar forward horizon and is threaded through every caller, the
tercile spread is computed on rank-assigned disjoint terciles that survive tied signals, and
the hit rate is reported next to the base rate it must be read against."""
import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from agentic_trader import Instrument, make_config
from agentic_trader.agents.analysts import AlphaAnalyst
from agentic_trader.alpha import (IC_T_METHODS, _alpha_diagnostics, alpha_report, compute_alphas, forward_returns,
                                  information_coefficient, significant_alpha_signal, tercile_spread)
from agentic_trader.data import SyntheticProvider
from agentic_trader.state import TradingState

CFG = make_config(memory_path=None)
NAN = float("nan")
H = 10


def _random_walk_frame(rng: np.random.Generator, n_bars: int = 620) -> pd.DataFrame:
    r = rng.normal(0.0003, 0.015, n_bars)
    close = 100 * np.cumprod(1 + r)
    noise = np.abs(rng.normal(0, 0.007, n_bars))
    idx = pd.bdate_range("2019-01-01", periods=n_bars)
    return pd.DataFrame({"Open": close, "High": close * (1 + noise), "Low": close * (1 - noise),
                         "Close": close, "Volume": np.full(n_bars, 1e6)}, index=idx)


# ------------------------------------------------------------ finding 5: overlap-aware t(IC)
def test_ic_tstat_uses_the_effective_sample_n_over_h_like_xalpha():
    s, f = [1, 2, 3, 4, 5, 6, 7, 8], [2, 1, 4, 3, 6, 5, 8, 7]
    ic, t1, n = information_coefficient(s, f)
    assert n == 8 and t1 == pytest.approx(ic * math.sqrt(8))
    for h in (2, 4, 8):
        assert information_coefficient(s, f, horizon=h)[1] == pytest.approx(ic * math.sqrt(8 / h))
    # more overlap than pairs: the effective sample floors at one, never below
    assert information_coefficient(s, f, horizon=100)[1] == pytest.approx(ic)
    # the IC itself and the raw pair count never depend on the horizon
    assert information_coefficient(s, f, horizon=4)[0] == pytest.approx(ic)
    assert information_coefficient(s, f, horizon=4)[2] == 8
    assert set(IC_T_METHODS) == {"n_eff", "newey_west"}
    assert math.isfinite(information_coefficient(s, f, horizon=3, method="newey_west")[1])
    with pytest.raises(ValueError):
        information_coefficient(s, f, horizon=0)
    with pytest.raises(ValueError):
        information_coefficient(s, f, method="hac")
    assert all(math.isnan(v) for v in information_coefficient([1, NAN, 2], [1, 2, 3], horizon=5)[:2])


def test_ic_tstat_variants_on_synthetic_overlapping_returns():
    """A persistent signal against overlapping 10-bar sums of pure noise: the iid formula's
    null t has SD ~2.5, the n/h rule brings it back near 1 and the Newey-West variant with
    h-1 lags removes most, though not all, of the inflation (its Bartlett window is shorter
    than the signal's memory)."""
    rng = np.random.default_rng(11)
    naive, n_eff, nw = [], [], []
    for _ in range(300):
        e = rng.normal(size=400)
        fwd = np.convolve(e, np.ones(H), mode="valid")[:390]
        sig = np.empty(390)
        z = 0.0
        for i in range(390):
            z = 0.9 * z + rng.normal()
            sig[i] = z
        ic, t_eff, n = information_coefficient(sig, fwd, H)
        naive.append(ic * math.sqrt(n))
        n_eff.append(t_eff)
        nw.append(information_coefficient(sig, fwd, H, "newey_west")[1])
    naive, n_eff, nw = (np.array(v) for v in (naive, n_eff, nw))
    assert naive.std() > 2.0 and np.mean(np.abs(naive) >= 2) > 0.3
    assert 0.6 < n_eff.std() < 1.1 and np.mean(np.abs(n_eff) >= 2) <= 0.05
    assert nw.std() < 1.6 and np.mean(np.abs(nw) >= 2) < np.mean(np.abs(naive) >= 2) / 2
    # Newey-West with no lags is the plain heteroskedasticity-robust t: SD 1 on iid pairs
    iid = np.array([information_coefficient(rng.normal(size=300), rng.normal(size=300), 1, "newey_west")[1]
                    for _ in range(500)])
    assert 0.85 < iid.std() < 1.15


def test_alpha_analyst_gate_is_a_five_percent_test_on_pure_noise():
    """The analyst's exact path -- compute_alphas -> forward_returns(close, 10) ->
    information_coefficient(..., horizon=10) -> significant_alpha_signal -- on seeded random
    walks. Under the null the corrected |t| >= 2 gate fires at a few percent per alpha and
    the analyst abstains on the large majority of histories; the old IC*sqrt(n) statistic,
    computed on the same numbers, fired on 35-70% per alpha and let the analyst speak on
    ~98% of noise."""
    rng = np.random.default_rng(7)
    ins = Instrument.parse("AAPL")
    n_sim = 200
    t_new: dict[str, list[float]] = {}
    t_old: dict[str, list[float]] = {}
    emit_new = emit_old = 0
    for _ in range(n_sim):
        df = _random_walk_frame(rng)
        sig = compute_alphas(df, ins)
        fwd = forward_returns(df["Close"].to_numpy(float), H)
        ic_new, ic_old = {}, {}
        for name in sig.columns:
            v, t, n = information_coefficient(sig[name].to_numpy(), fwd, H)
            ic_new[name] = {"IC": v, "t(IC)": t, "n": n}
            ic_old[name] = {"IC": v, "t(IC)": v * math.sqrt(n), "n": n}
            t_new.setdefault(name, []).append(t)
            t_old.setdefault(name, []).append(v * math.sqrt(n))
        latest = {k: (None if pd.isna(v) else float(v)) for k, v in sig.iloc[-1].items()}
        emit_new += significant_alpha_signal(latest, ic_new, 2.0, 30)[0] is not None
        emit_old += significant_alpha_signal(latest, ic_old, 2.0, 30)[0] is not None

    rate_new = {k: float(np.mean(np.abs(v) >= 2)) for k, v in t_new.items()}
    rate_old = {k: float(np.mean(np.abs(v) >= 2)) for k, v in t_old.items()}
    sd_new = {k: float(np.std(v)) for k, v in t_new.items()}
    assert set(rate_new) == {"tsmom_12_1", "mom_20_vol", "reversal_5", "high_52w", "donchian_20",
                             "macd_norm", "rsi_contrarian", "low_vol"}
    for name in rate_new:
        assert rate_new[name] <= 0.10, (name, rate_new[name])
        assert 0.5 <= sd_new[name] <= 1.25, (name, sd_new[name])      # null SD of a t-statistic is 1
        assert rate_old[name] > 0.10, (name, rate_old[name])          # the shipped formula fails the band
    pooled_new = float(np.mean([r for r in rate_new.values()]))
    pooled_old = float(np.mean([r for r in rate_old.values()]))
    assert 0.02 <= pooled_new <= 0.10, pooled_new
    assert pooled_old > 0.3, pooled_old
    # 8 alphas gated per-alpha at 5% still let the analyst speak on ~1 in 4 noise histories
    # (no multiplicity control); the old gate let it speak on nearly all of them.
    assert emit_new / n_sim <= 0.35, emit_new / n_sim
    assert emit_old / n_sim >= 0.8, emit_old / n_sim


def test_alpha_analyst_gather_reports_the_overlap_aware_t():
    provider = SyntheticProvider(make_config(synthetic_seed=7))
    ins = Instrument.parse("AAPL")
    as_of = date(2020, 6, 1)
    df = provider.history(ins, date(2016, 1, 1), as_of)
    state = TradingState(ins, as_of, df[df.index <= pd.Timestamp(as_of)])
    facts = AlphaAnalyst(None, CFG).gather(state, provider)
    assert facts["ic"]
    for name, v in facts["ic"].items():
        if v["IC"] == v["IC"]:
            assert v["t(IC)"] == pytest.approx(v["IC"] * math.sqrt(v["n"] / H))
            assert v["t(IC)"] != pytest.approx(v["IC"] * math.sqrt(v["n"]))


def test_alpha_report_threads_the_horizon_into_every_t_and_reports_the_base_rate():
    provider = SyntheticProvider(make_config(synthetic_seed=3))
    ins = Instrument.parse("MSFT")
    df = provider.history(ins, date(2019, 1, 1), date(2022, 12, 30))
    rep10 = alpha_report(df, ins, 10)
    rep1 = alpha_report(df, ins, 1)
    for name in rep10.table.index:
        row = rep10.table.loc[name]
        if row["IC"] == row["IC"]:
            assert row["t(IC)"] == pytest.approx(row["IC"] * math.sqrt(row["n"] / 10), abs=2e-3)
        row1 = rep1.table.loc[name]
        if row1["IC"] == row1["IC"]:
            assert row1["t(IC)"] == pytest.approx(row1["IC"] * math.sqrt(row1["n"]), abs=2e-3)
    assert "up%" in rep10.table.columns
    up = rep10.table["up%"].dropna()
    assert ((up >= 0) & (up <= 100)).all()
    # every alpha's up% is the same base rate: it is a property of the return sample, not the signal
    full = rep10.table.loc[rep10.table["coverage%"] == 100, "up%"]
    assert full.nunique() <= 1 or (full.max() - full.min()) < 1e-9


# ---------------------------------------------- finding 29: rank terciles and the base rate
def _quantile_threshold_spread(s: np.ndarray, fwd: np.ndarray) -> float:
    """The pre-v0.8 computation: value thresholds at the 1/3 and 2/3 quantiles."""
    lo, hi = np.quantile(s, [1 / 3, 2 / 3])
    top, bot = fwd[s >= hi], fwd[s <= lo]
    return float(top.mean() - bot.mean())


def test_tercile_spread_survives_a_signal_tied_on_most_bars():
    rng = np.random.default_rng(0)
    n = 100
    s = np.full(n, -1.0)
    s[rng.choice(n, 30, replace=False)] = rng.uniform(-0.9, 1.0, 30)
    fwd = rng.normal(0, 0.01, n)
    fwd[s == -1.0] -= 0.02                                       # the -1 days really are 2% worse
    true_spread = fwd[s > -1.0].mean() - fwd[s == -1.0].mean()
    old = _quantile_threshold_spread(s, fwd)
    new = tercile_spread(s, fwd)
    assert old < 0.4 * true_spread                               # lo == hi == -1: "top" was every bar
    assert new == pytest.approx(true_spread, rel=0.15)
    assert new > 2.5 * old
    assert _alpha_diagnostics(s, fwd)["tercile spread%"] == pytest.approx(100 * new)
    # the same bars in another order give the same number: ties are shared, not broken by position
    perm = rng.permutation(n)
    assert tercile_spread(s[perm], fwd[perm]) == pytest.approx(new)
    # the 1/3 < tie share < 2/3 variant: the bottom group must hold n/3 bars, not every tied one
    s2 = np.where(np.arange(n) < 50, -1.0, rng.uniform(-0.9, 1.0, n))
    fwd2 = rng.normal(0, 0.01, n)
    fwd2[s2 == -1.0] -= 0.02
    top2 = np.sort(s2)[n - n // 3]
    expected2 = fwd2[s2 >= top2].mean() - fwd2[s2 == -1.0].mean()  # top 33 (distinct values) vs the tied 50
    assert tercile_spread(s2, fwd2) == pytest.approx(expected2, rel=1e-9)


def test_tercile_spread_on_distinct_values_is_the_plain_top_minus_bottom_third():
    rng = np.random.default_rng(5)
    s = rng.normal(size=91)
    fwd = 0.3 * s + rng.normal(size=91)
    order = np.argsort(s)
    k = 91 // 3
    assert tercile_spread(s, fwd) == pytest.approx(fwd[order[-k:]].mean() - fwd[order[:k]].mean())
    # without ties the old threshold rule differs only by the one boundary bar np.quantile interpolates
    assert tercile_spread(s, fwd) == pytest.approx(_quantile_threshold_spread(s, fwd), rel=0.15)
    assert tercile_spread(np.ones(60), fwd[:60]) == 0.0           # no ranking possible -> no spread
    assert math.isnan(tercile_spread(s[:2], fwd[:2]))
    assert math.isnan(tercile_spread(np.full(40, NAN), fwd[:40]))


def test_hit_rate_is_reported_next_to_the_base_rate():
    rng = np.random.default_rng(1)
    fwd = rng.normal(0.003, 0.01, 200)                            # a rally: most 10-day returns are up
    fwd[fwd == 0] = 1e-6
    bull = _alpha_diagnostics(np.ones(200), fwd)
    assert bull["up%"] == pytest.approx(100 * np.mean(fwd > 0)) and bull["up%"] > 55
    assert bull["hit%"] == pytest.approx(bull["up%"])              # zero skill reads as hit == base
    bear = _alpha_diagnostics(-np.ones(200), fwd)
    assert bear["hit%"] == pytest.approx(100 - bear["up%"])
    assert math.isnan(_alpha_diagnostics(np.full(5, NAN), fwd[:5])["up%"])
    assert set(bull) == {"IC", "t(IC)", "n", "hit%", "up%", "tercile spread%", "autocorr", "coverage%"}
