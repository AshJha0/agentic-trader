"""v0.8 portfolio-risk fixes (tier-1 review findings 2, 3, 24, 25, 26, 27): per-sleeve caps
honoured by every scheme and after vol targeting, book VaR failing closed on short history,
short positions sized on the right tail, hedges sized rather than flattened, a Ledoit-Wolf
intensity that matches the (EWMA) estimator it shrinks, and degenerate windows raising."""
import logging
from datetime import date

import numpy as np
import pandas as pd
import pytest

from agentic_trader import Instrument, TradingGraph, make_config, quant
from agentic_trader.agents.risk import PortfolioManager, RiskAnalyst, risk_facts
from agentic_trader.backtest import run_portfolio_backtest
from agentic_trader.data.synthetic import SyntheticProvider
from agentic_trader.memory import DecisionMemory
from agentic_trader.portfolio import (
    METHODS, MIN_BOOK_OBS, book_returns, book_var_95, book_var_scale, construct, estimate_cov, ewma_cov,
    ewma_weights, ledoit_wolf_shrink, risk_parity_weights, sample_cov,
)
from agentic_trader.state import Book, TradingState

CFG = make_config(memory_path=None)
QUIET = dict(memory=DecisionMemory(None), on_event=lambda *_: None)


def _graph(cfg=CFG, **kw):
    return TradingGraph(cfg, **{**QUIET, **kw})


def _frame(vols, n=300, seed=0, corr=0.0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2023-01-02", periods=n)
    common = rng.normal(0, 1, n)
    cols = {}
    for i, (s, v) in enumerate(vols.items()):
        z = corr * common + np.sqrt(1 - corr * corr) * rng.normal(0, 1, n)
        cols[s] = v * z
    return pd.DataFrame(cols, index=idx)


# ------------------------------------------------ finding 2: max_weight for every scheme
SKEWED = {"BIL": 0.002, "EQ1": 0.02, "EQ2": 0.02}   # a bill ETF next to two equities


@pytest.mark.parametrize("method", METHODS)
def test_construct_caps_every_scheme_on_a_skewed_covariance(method):
    rets = _frame(SKEWED)
    pw = construct({s: 1.0 for s in SKEWED}, rets, method, max_weight=0.5, target_vol=None)
    assert pw.allocation.max() <= 0.5 + 1e-9 and np.abs(pw.weights).max() <= 0.5 + 1e-9
    assert pw.allocation.sum() == pytest.approx(1.0) and (pw.allocation >= -1e-12).all()
    assert pw.contributions["allocation"].max() <= 0.5 + 1e-9
    if method in ("inverse_vol", "risk_parity"):
        assert pw.allocation[0] == pytest.approx(0.5)   # the low-vol sleeve sits exactly on the cap


@pytest.mark.parametrize("method", METHODS)
def test_vol_target_scale_up_respects_the_cap_and_the_gross_cap(method):
    rets = _frame({"A": 0.01, "B": 0.01, "C": 0.01}, seed=1)
    pw = construct({"A": 1.0, "B": 0.1, "C": 0.1}, rets, method, max_weight=0.5, target_vol=0.15)
    assert pw.scale >= 1.0
    assert np.abs(pw.weights).max() <= 0.5 + 1e-9
    assert np.abs(pw.weights).sum() <= 1.0 + 1e-9
    assert pw.allocation.sum() <= 1.0 + 1e-9 and pw.allocation.max() <= 0.5 + 1e-9
    assert pw.contributions["allocation"].sum() <= 1.0 + 3 * 5e-5   # the frame is rounded to 4 dp
    assert pw.expected_vol <= 0.15 + 1e-9
    np.testing.assert_allclose(pw.weights, pw.allocation * np.array([1.0, 0.1, 0.1]) * pw.scale)


def test_vol_target_scale_binds_on_the_per_sleeve_cap():
    """Equal 1/3 split, targets 1/0.1/0.1: the gross cap alone would allow x2.5 (to 0.83 in A);
    the per-sleeve cap stops the scale at 1.5 (A at exactly 0.5)."""
    rets = _frame({"A": 0.01, "B": 0.01, "C": 0.01}, seed=1)
    pw = construct({"A": 1.0, "B": 0.1, "C": 0.1}, rets, "equal", max_weight=0.5, target_vol=0.15)
    assert pw.scale == pytest.approx(1.5)
    np.testing.assert_allclose(pw.weights, [0.5, 0.05, 0.05])
    np.testing.assert_allclose(pw.allocation, [1 / 3] * 3)


def test_group_budgets_honour_the_cap_within_and_across_groups(caplog):
    rets = _frame({**SKEWED, "FX": 0.005}, seed=2)
    groups = {"BIL": "eq", "EQ1": "eq", "EQ2": "eq", "FX": "fx"}
    for method in METHODS:
        pw = construct({s: 1.0 for s in rets.columns}, rets, method, max_weight=0.5, target_vol=None,
                       groups=groups, group_budgets={"eq": 0.6, "fx": 0.4})
        assert pw.allocation.max() <= 0.5 + 1e-9 and pw.allocation.sum() == pytest.approx(1.0)
    # a two-sleeve group with 0.2%/2% vols: within-group inverse vol wants 0.91 in the bill
    pw = construct({"BIL": 1.0, "EQ1": 1.0, "FX": 1.0}, rets, "inverse_vol", max_weight=0.5, target_vol=None,
                   groups=groups, group_budgets={"eq": 0.9, "fx": 0.1})
    assert pw.allocation.max() <= 0.5 + 1e-9
    # a single-sleeve group whose budget wants more than the cap: the cap wins and says so
    with caplog.at_level(logging.WARNING, logger="agentic_trader.portfolio"):
        pw = construct({"BIL": 1.0, "EQ1": 1.0, "FX": 1.0}, rets, "equal", max_weight=0.4, target_vol=None,
                       groups=groups, group_budgets={"eq": 0.05, "fx": 0.95})
    assert pw.allocation.max() <= 0.4 + 1e-9 and pw.allocation.sum() == pytest.approx(1.0)
    assert "overrides the group risk budgets" in caplog.text


def test_cap_below_one_over_k_is_raised_to_the_feasible_cap():
    rets = _frame({"A": 0.01, "B": 0.02}, seed=3)
    pw = construct({"A": 1.0, "B": 1.0}, rets, "risk_parity", max_weight=0.1, target_vol=None)
    assert pw.allocation.max() <= 0.5 + 1e-9 and pw.allocation.sum() == pytest.approx(1.0)


# -------------------------------------------- finding 3: book VaR fails closed, not open
def _book_frame(n=250, short_bars=10, seed=0):
    rets = _frame({"A": 0.01, "B": 0.012}, n=n, seed=seed, corr=0.3)
    new = pd.Series(np.nan, index=rets.index)
    new.iloc[-short_bars:] = np.random.default_rng(seed + 1).normal(0, 0.02, short_bars)
    rets["NEW"] = new
    return rets


def test_zero_weight_short_history_symbol_does_not_change_the_book_check():
    rets = _book_frame()
    assert book_var_95({"A": 1.0}, rets) == pytest.approx(book_var_95({"A": 1.0, "NEW": 0.0}, rets))
    limit = book_var_95({"A": 1.0}, rets) * 1.02   # tight: B has to be scaled down
    without = book_var_scale("B", 0.5, {"A": 1.0}, rets, limit)
    with_new = book_var_scale("B", 0.5, {"A": 1.0, "NEW": 0.0}, rets, limit)
    assert without == with_new
    assert without[0] < 0.5 and without[2] is not None   # the cap is live in both cases
    # the fewer-than-20-rows condition that used to disable the check is what NEW alone shows
    assert book_returns({"A": 1.0, "NEW": 0.0}, rets).size == len(rets)
    assert book_returns({"A": 1.0, "NEW": 0.2}, rets).size == 10


def test_held_short_history_symbol_fails_closed_with_a_note():
    rets = _book_frame()
    assert book_var_95({"A": 1.0, "NEW": 0.2}, rets) is None
    w, after, note = book_var_scale("B", 0.5, {"A": 1.0, "NEW": 0.2}, rets, 0.05)
    assert w == 0.0 and after is None
    assert "could not be evaluated" in note and "10 aligned observations" in note
    # a held symbol absent from the frame is zero-return (documented; scan() gives every held
    # symbol a column so this only arises for hand-built books) ...
    w, after, note = book_var_scale("B", 0.5, {"GHOST": 0.2}, rets.drop(columns="NEW"), 0.05)
    assert w == 0.5 and note is None
    # ... but the symbol being sized must have history, or the check cannot say anything
    w, after, note = book_var_scale("GHOST", 0.5, {"A": 1.0}, rets.drop(columns="NEW"), 0.05)
    assert w == 0.0 and after is None and "no return history for GHOST" in note
    # an all-NaN column (scan's stand-in for a failed fetch) is 0 aligned observations
    w, after, note = book_var_scale("B", 0.5, {"A": 1.0, "NEW": 0.2}, rets.assign(NEW=np.nan), 0.05)
    assert w == 0.0 and "0 aligned observations" in note
    # the check being off still returns the proposal untouched
    assert book_var_scale("B", 0.5, {"A": 1.0, "NEW": 0.2}, rets, None) == (0.5, None, None)
    # an empty book has no VaR
    assert book_var_95({}, rets) == 0.0 and book_var_95({"A": 0.0}, rets.iloc[:3]) == 0.0


def test_pm_guardrails_record_the_fail_closed_note():
    rets = _book_frame()
    pm = PortfolioManager(None, CFG)
    f = {"max_position": 1.0, "max_var_95": 0.0, "var_95_1d": 0.01, "var_95_1d_short": 0.01,
         "short_selling_allowed": True, "rebalance_band": 0.0, "max_book_var_95": 0.05}
    w, notes = pm.guardrails(0.5, f, "B", Book({"A": 1.0, "NEW": 0.2}, rets))
    assert w == 0.0 and any("could not be evaluated" in n for n in notes)
    w, notes = pm.guardrails(0.5, f, "B", Book({"A": 1.0, "NEW": 0.0}, rets))
    assert w == 0.5 and notes == []
    # no_trade_band never keeps a position the (now failing-closed) check forbids
    kept, band_note = pm.no_trade_band(0.45, 0.5, {**f, "rebalance_band": 0.1}, "B",
                                       Book({"A": 1.0, "NEW": 0.2}, rets))
    assert kept == 0.45 and band_note is None


def _truncate(provider, symbol, bars):
    orig = provider.history

    def history(instrument, start, end):
        h = orig(instrument, start, end)
        return h.iloc[-bars:] if instrument.symbol == symbol else h
    provider.history = history


def test_scan_book_check_survives_a_short_history_symbol(caplog):
    cfg = make_config(CFG, risk={"max_book_var_95": 0.005})   # binds with SPY held at 1.0
    base = _graph(cfg).scan(["SPY", "QQQ"], "2024-03-01", positions={"SPY": 1.0})
    base_row = base[base.symbol == "QQQ"].iloc[0]
    assert "book VaR" in base_row.adjustments and base_row.target_weight == 0.0

    g = _graph(cfg)
    _truncate(g.provider, "NEW", 10)
    with caplog.at_level(logging.WARNING, logger="agentic_trader.graph"):
        df = g.scan(["SPY", "QQQ", "NEW"], "2024-03-01", positions={"SPY": 1.0, "NEW": 0.0})
    row = df[df.symbol == "QQQ"].iloc[0]
    assert row.target_weight == base_row.target_weight and row.adjustments == base_row.adjustments
    assert "NEW has 9 bars of book history (need 20)" in caplog.text   # 10 closes -> 9 returns

    g = _graph(cfg)
    _truncate(g.provider, "NEW", 10)
    df = g.scan(["SPY", "QQQ", "NEW"], "2024-03-01", positions={"SPY": 1.0, "NEW": 0.1})
    row = df[df.symbol == "QQQ"].iloc[0]
    assert row.target_weight == 0.0 and "could not be evaluated" in row.adjustments


def test_scan_book_includes_held_symbols_outside_the_watchlist():
    cfg = make_config(CFG, risk={"max_book_var_95": 0.02})
    g = _graph(cfg)
    seen = {}
    orig = g.propagate

    def spy(ins, as_of, **kw):
        seen["book"] = kw.get("book")
        return orig(ins, as_of, **kw)
    g.propagate = spy
    g.scan(["AAPL"], "2024-03-01", positions={"AAPL": 0.5, "TLT": 3.0})
    assert "TLT" in seen["book"].returns.columns and seen["book"].positions == {"TLT": 3.0}
    assert seen["book"].returns["TLT"].notna().sum() >= MIN_BOOK_OBS


# ------------------------------------------- finding 24: shorts are sized on the right tail
def _skewed_returns(sign=+1):
    r = np.array([-0.005] * 235 + [0.03] * 15) * sign
    np.random.default_rng(1).shuffle(r)
    return r


def _facts(r, **over):
    f = {"max_position": 1.0, "max_var_95": 0.02, "var_95_1d": quant.historical_var(r, 0.95),
         "var_95_1d_short": quant.historical_var(-r, 0.95), "short_selling_allowed": True,
         "rebalance_band": 0.0, "proposed_weight": -1.0, "realized_vol_20d_annual": None, "target_vol": 0.15}
    f.update(over)
    return f


def test_short_var_guardrail_uses_the_right_tail():
    pm = PortfolioManager(None, CFG)
    r = _skewed_returns()                       # q05 = -0.5%, q95 = +3%
    f = _facts(r)
    assert f["var_95_1d"] == pytest.approx(0.005) and f["var_95_1d_short"] == pytest.approx(0.03)
    w, notes = pm.guardrails(-1.0, f)
    assert w == pytest.approx(-0.02 / 0.03) and any("VaR limit" in n for n in notes)
    assert pm.guardrails(1.0, f) == (1.0, [])
    # the short's cap agrees with the book-level check on the same single-instrument book
    df = pd.DataFrame({"X": r})
    assert book_var_95({"X": -1.0}, df) == pytest.approx(0.03)
    assert book_var_95({"X": w}, df) <= 0.02 + 1e-12
    # mirrored (left-skewed) series: the short is fine, the long is capped
    fm = _facts(_skewed_returns(-1))
    assert pm.guardrails(-1.0, fm) == (-1.0, [])
    assert pm.guardrails(1.0, fm)[0] == pytest.approx(0.02 / 0.03)
    # symmetric series: both sides get the same cap
    sym = np.random.default_rng(0).normal(0, 0.02, 500)
    fs = _facts(np.concatenate([sym, -sym]))
    assert pm.guardrails(1.0, fs)[0] == pytest.approx(-pm.guardrails(-1.0, fs)[0])


def test_conservative_analyst_and_risk_facts_use_the_short_tail():
    r = _skewed_returns()
    an = RiskAnalyst(None, CFG, "conservative")
    # realised vol at target -> vt = proposal -> conservative w = -0.5; 0.5 * 3% > the 1% cap
    w = an.rules_weight(_facts(r, max_var_95=0.01, realized_vol_20d_annual=0.15))
    assert w == pytest.approx(-0.5 * 0.01 / 0.015)
    # the long side of the same series (0.5 * 0.5% < 1%) is untouched
    assert an.rules_weight(_facts(r, proposed_weight=1.0, max_var_95=0.01,
                                  realized_vol_20d_annual=0.15)) == pytest.approx(0.5)
    closes = 100 * np.cumprod(1 + np.r_[0.0, r])
    hist = pd.DataFrame({"Open": closes, "High": closes * 1.01, "Low": closes * 0.99, "Close": closes,
                         "Volume": 1e6}, index=pd.bdate_range("2023-01-02", periods=len(closes)))
    st = TradingState(Instrument.parse("EURUSD"), date(2024, 1, 1), hist)
    f = risk_facts(st, CFG)
    assert f["var_95_1d"] == pytest.approx(quant.historical_var(r, 0.95))
    assert f["var_95_1d_short"] == pytest.approx(quant.historical_var(-r, 0.95)) == pytest.approx(0.03)


def test_critic_firm_limits_check_the_short_tail():
    from agentic_trader.agentic.critic import Critic
    from agentic_trader.agentic.evidence import EvidenceStore
    st, _ = _graph().propagate("EURUSD", "2024-03-01")
    st.decision.target_weight = -0.7
    facts = {"var_95_1d": 0.005, "var_95_1d_short": 0.03}
    rep = Critic(make_config(CFG, agentic={"llm_critic": False})).review(st, [], EvidenceStore(), facts)
    limits = next(c for c in rep.checks if c.name == "firm_limits")
    assert not limits.passed and "VaR 2.10%" in limits.detail
    st.decision.target_weight = -0.6
    rep = Critic(make_config(CFG, agentic={"llm_critic": False})).review(st, [], EvidenceStore(), facts)
    assert next(c for c in rep.checks if c.name == "firm_limits").passed


# ------------------------------------------ finding 25: a feasible hedge is sized, not cut
def _hedge_pair(T=2000, seed=0):
    rng = np.random.default_rng(seed)
    z1, z2 = rng.standard_normal(T), rng.standard_normal(T)
    a = 0.01 * z1
    b = 0.02 * (0.5 * z1 + np.sqrt(1 - 0.25) * z2)
    return pd.DataFrame({"A": a, "B": b})


def test_partial_hedge_is_sized_to_the_largest_feasible_size_when_the_rest_already_breaches():
    rets = _hedge_pair()
    other = {"A": 1.0}
    zero = book_var_95({"A": 1.0}, rets)
    cs = np.linspace(0, 1, 41)
    vs = np.array([book_var_95({"A": 1.0, "B": -c}, rets) for c in cs])
    limit = (zero + vs.min()) / 2
    assert vs.min() < limit < zero < vs[-1]          # rest over, full hedge over, partial sizes under
    w, after, note = book_var_scale("B", -1.0, other, rets, limit)
    expected = -max(c for c, v in zip(cs, vs) if v <= limit)
    assert w == pytest.approx(expected) and w < 0
    assert after <= limit + 1e-12 and "sized to the largest hedge" in note
    # a positively correlated addition still cannot help: flattened with an explicit reason
    w, after, note = book_var_scale("B", 1.0, other, rets, limit)
    assert w == 0.0 and "already exceeds" in note and "no size of it" in note
    # and when the rest of the book is within budget the sizing note is unchanged
    w, after, note = book_var_scale("B", 0.2, other, rets, zero * 1.05)
    assert 0 < w < 0.2 and after <= zero * 1.05 + 1e-12 and note.startswith("book VaR limit")


# ------------------------------- finding 26: the intensity matches the estimator it shrinks
def _cov_cor_reference(x):
    """Ledoit & Wolf (2004) constant-correlation shrinkage intensity, transcribed from
    covCor.m: loops, equal weights, the 1/T sample covariance."""
    t, n = x.shape
    x = x - x.mean(axis=0)
    sample = x.T @ x / t
    var = np.diag(sample)
    sq = np.sqrt(var)
    rbar = (np.sum(sample / np.outer(sq, sq)) - n) / (n * (n - 1))
    prior = rbar * np.outer(sq, sq)
    np.fill_diagonal(prior, var)
    y = x ** 2
    phi_mat = y.T @ y / t - 2 * (x.T @ x) * sample / t + sample ** 2
    phi = phi_mat.sum()
    term1 = (x ** 3).T @ x / t
    help_ = x.T @ x / t
    theta = term1 - np.diag(help_)[:, None] * sample - help_ * var[:, None] + var[:, None] * sample
    np.fill_diagonal(theta, 0.0)
    rho = np.trace(phi_mat) + rbar * np.sum(np.outer(1 / sq, sq) * theta)
    gamma = np.linalg.norm(sample - prior, "fro") ** 2
    kappa = (phi - rho) / gamma
    return max(0.0, min(1.0, kappa / t)), prior, sample


def test_ledoit_wolf_intensity_matches_the_reference_implementation():
    rng = np.random.default_rng(5)
    x = rng.multivariate_normal(np.zeros(4), np.array([[4, 1, 0.5, 0], [1, 3, 0.2, 0.1],
                                                      [0.5, 0.2, 2, 0.3], [0, 0.1, 0.3, 1]]) * 1e-4, 200)
    delta_ref, prior, sample = _cov_cor_reference(x)
    shrunk, delta = ledoit_wolf_shrink(x, sample, np.full(200, 1.0 / 200))
    assert 0 < delta_ref < 1 and delta == pytest.approx(delta_ref, abs=1e-12)
    np.testing.assert_allclose(shrunk, delta_ref * prior + (1 - delta_ref) * sample, rtol=1e-12)
    # equal weights are the default and the sample-covariance path is unchanged numerically
    _, d_default = ledoit_wolf_shrink(x)
    _, d_explicit = ledoit_wolf_shrink(x, sample_cov(x), None)
    assert d_default == d_explicit


def test_weighted_intensity_reduces_to_the_unweighted_one_on_the_weighted_rows():
    rng = np.random.default_rng(8)
    x = rng.normal(0, 0.01, (300, 3)) + rng.normal(0, 0.005, (300, 1))
    w = np.r_[np.zeros(200), np.full(100, 0.01)]
    last = x[-100:] - x[-100:].mean(axis=0)
    s_last = last.T @ last / 100
    _, d_w = ledoit_wolf_shrink(x, s_last, w)
    _, d_u = ledoit_wolf_shrink(x[-100:], s_last)
    assert d_w == pytest.approx(d_u, rel=1e-12)
    assert 0 < d_u <= 1


def test_ewma_intensity_ignores_history_the_weights_ignore():
    """Prepending 300 rows that the EWMA weights at ~1.6% in total must move the intensity by
    about that much -- not divide it by 8 because T grew from 120 to 420."""
    rng = np.random.default_rng(0)
    n, hl = 5, 20.0
    L = rng.standard_normal((n, n))
    c = L @ L.T
    c = c / np.outer(np.sqrt(np.diag(c)), np.sqrt(np.diag(c)))
    recent = rng.multivariate_normal(np.zeros(n), 0.02 ** 2 * c, 120)
    quiet = rng.multivariate_normal(np.zeros(n), 0.005 ** 2 * c, 300)
    same = rng.multivariate_normal(np.zeros(n), 0.02 ** 2 * c, 300)
    _, d0 = ledoit_wolf_shrink(recent, ewma_cov(recent, hl), ewma_weights(120, hl))
    for old in (quiet, same):
        full = np.vstack([old, recent])
        _, d1 = ledoit_wolf_shrink(full, ewma_cov(full, hl), ewma_weights(420, hl))
        assert abs(d1 - d0) / d0 < 0.05
        assert np.abs(estimate_cov(full, hl) - estimate_cov(recent, hl)).max() < 0.03 * np.abs(estimate_cov(recent, hl)).max()
    # the old formula (equal weights, divide by T) on the same EWMA covariance is what collapses
    _, bad0 = ledoit_wolf_shrink(recent, ewma_cov(recent, hl))
    _, bad1 = ledoit_wolf_shrink(np.vstack([quiet, recent]), ewma_cov(np.vstack([quiet, recent]), hl))
    assert bad1 < 0.25 * bad0
    with pytest.raises(ValueError):
        ledoit_wolf_shrink(recent, ewma_cov(recent, hl), np.ones(5))


def test_effective_sample_size_is_the_weights_own():
    rng = np.random.default_rng(2)
    x = rng.normal(0, 0.01, (400, 4))
    w = ewma_weights(400, 60.0)
    assert 1 / (w @ w) == pytest.approx(169.8, abs=0.1)   # Kish ESS of the default halflife at T=400
    # same covariance, same rows: the equal-weight/T intensity understates by about T / n_eff
    s = ewma_cov(x, 60.0)
    _, d_w = ledoit_wolf_shrink(x, s, w)
    _, d_t = ledoit_wolf_shrink(x, s)
    assert d_w > d_t


def test_zero_variance_column_shrinks_without_nan():
    rng = np.random.default_rng(0)
    x = np.column_stack([rng.normal(0, 0.01, 120), rng.normal(0, 0.01, 120), np.zeros(120)])
    shrunk, delta = ledoit_wolf_shrink(x, sample_cov(x))
    assert np.isfinite(shrunk).all() and 0 <= delta <= 1
    assert shrunk[2].tolist() == [0.0, 0.0, 0.0]
    np.testing.assert_allclose(np.diag(shrunk), np.diag(sample_cov(x)))
    assert np.isfinite(estimate_cov(x, 60.0)).all()


# ------------------------------- finding 27: degenerate windows raise, never allocate NaN
def test_risk_parity_raises_on_a_covariance_without_variance():
    with pytest.raises(ValueError):
        risk_parity_weights(np.zeros((3, 3)))
    with pytest.raises(ValueError):
        risk_parity_weights(np.full((3, 3), np.nan))
    # one flat sleeve among live ones is fine: it gets nothing, the others split the risk
    cov = np.diag([0.01, 0.02, 0.0])
    w = risk_parity_weights(cov)
    assert np.isfinite(w).all() and w[2] == 0.0 and w.sum() == pytest.approx(1.0)


def test_construct_raises_on_a_flat_window_and_survives_one_flat_sleeve():
    idx = pd.bdate_range("2024-01-01", periods=60)
    flat = pd.DataFrame(0.0, index=idx, columns=list("ABC"))
    for method in METHODS:
        with pytest.raises(ValueError):
            construct({"A": 1, "B": 1, "C": 1}, flat, method, max_weight=1.0, target_vol=None)
    rng = np.random.default_rng(0)
    mixed = pd.DataFrame({"A": rng.normal(0, 0.01, 60), "B": rng.normal(0, 0.01, 60), "C": 0.0}, index=idx)
    # the backtest's call (uncapped, default shrink=True): the flat sleeve gets nothing
    pw = construct({"A": 1, "B": 1, "C": 1}, mixed, "risk_parity", max_weight=1.0, target_vol=None)
    assert np.isfinite(pw.allocation).all() and pw.allocation[2] == 0.0
    assert pw.allocation.sum() == pytest.approx(1.0) and np.isfinite(pw.expected_vol)
    for method in METHODS:   # and every scheme stays finite at the default cap
        pw = construct({"A": 1, "B": 1, "C": 1}, mixed, method)
        assert np.isfinite(pw.allocation).all() and np.isfinite(pw.weights).all()
        assert np.isfinite(pw.expected_vol) and pw.allocation.sum() == pytest.approx(1.0)


class _FlatBlock(SyntheticProvider):
    """Every instrument's prices are frozen over the block: a covariance window with no variance."""
    flat_start, flat_end = pd.Timestamp("2024-01-25"), pd.Timestamp("2024-03-08")

    def history(self, instrument, start, end):
        h = super().history(instrument, start, end).copy()
        m = (h.index >= self.flat_start) & (h.index <= self.flat_end)
        if m.any():
            first = h.index[m][0]
            for c in ("Open", "High", "Low", "Close"):
                h.loc[m, c] = h.loc[first, "Close"]
        return h


def test_portfolio_backtest_keeps_the_previous_allocation_on_a_degenerate_window(monkeypatch):
    import agentic_trader.portfolio as P
    raised, real = [], P.construct

    def recording(*a, **k):
        try:
            return real(*a, **k)
        except ValueError:
            raised.append(len(a[1]))
            raise
    monkeypatch.setattr(P, "construct", recording)
    rp = run_portfolio_backtest(["AAPL", "JPM"], "2024-01-02", "2024-03-28", CFG, 5, provider=_FlatBlock(CFG),
                                weighting="risk_parity", cov_window=20)
    a = rp.allocations
    assert raised and all(n == 20 for n in raised)          # full-size windows that were still degenerate
    assert np.isfinite(a.to_numpy()).all()
    np.testing.assert_allclose(a.sum(axis=1), 1.0)
    inside = a[(a.index >= "2024-02-26") & (a.index <= "2024-03-08")]
    assert len(inside) >= 5 and (inside.nunique() == 1).all()    # held, not re-solved, through the block
    assert np.isfinite(rp.table().to_numpy(float)).all()
