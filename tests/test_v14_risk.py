"""v0.14 plan item 5.4: risk model (EWMA / FHS VaR, book VaR default, factors, stress, capacity).

Synthetic data only; no network.
"""
from __future__ import annotations

import copy
import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from agentic_trader import risk_model as rm
from agentic_trader.config import DEFAULT_CONFIG
from agentic_trader.data.synthetic import SyntheticProvider
from agentic_trader.portfolio import book_var_95, book_var_scale
from agentic_trader.quant import BacktestResult
from agentic_trader.stats import rolling_var_forecast, var_backtest


def garch_returns(n: int, seed: int, trend: float = 3.0, w: float = 2e-6, a: float = 0.08,
                  b: float = 0.90, df: int = 6) -> np.ndarray:
    """GARCH(1,1) with unit-variance Student-t innovations, scaled by a volatility that rises
    linearly to ``trend`` times its start: clustered and drifting volatility, the two things a
    250-day historical window reacts to slowly."""
    rng = np.random.default_rng(seed)
    s2, scale, r = w / (1 - a - b), np.linspace(1.0, trend, n), np.empty(n)
    for t in range(n):
        e = math.sqrt(s2) * rng.standard_t(df) / math.sqrt(df / (df - 2))
        r[t] = e * scale[t]
        s2 = w + a * e * e + b * s2
    return r


# ---------------------------------------------------------------- calibration
def test_fhs_passes_where_historical_window_fails():
    r = garch_returns(3000, seed=1)
    hist = var_backtest(r, rm.var_forecast(r, "historical"))
    fhs = var_backtest(r, rm.var_forecast(r, "fhs"))
    assert hist.kupiec_p < 0.05 and hist.christoffersen_p < 0.05
    assert fhs.kupiec_p > 0.05 and fhs.christoffersen_p > 0.05


def test_fhs_calibrated_across_seeds_historical_mostly_not():
    both = {"historical": 0, "fhs": 0}
    for seed in range(8):
        r = garch_returns(3000, seed)
        for m in both:
            bt = var_backtest(r, rm.var_forecast(r, m))
            both[m] += bt.kupiec_p >= 0.05 and bt.christoffersen_p >= 0.05
    assert both["fhs"] == 8
    assert both["historical"] <= 2


# ---------------------------------------------------------------- forecaster properties
def test_historical_method_reproduces_stats_rule():
    r = garch_returns(600, seed=3, trend=1.0)
    np.testing.assert_array_equal(rm.var_forecast(r, "historical"), rolling_var_forecast(r))


@pytest.mark.parametrize("method", rm.VAR_METHODS)
def test_no_look_ahead_and_alignment(method):
    r = garch_returns(500, seed=4, trend=1.0)
    f = rm.var_forecast(r, method, window=100)
    assert f.shape == r.shape
    assert np.isnan(f[:100]).all() and np.isfinite(f[100:]).all() and (f[100:] >= 0).all()
    shocked = r.copy()
    shocked[300:] *= 5.0          # change the future only
    np.testing.assert_array_equal(rm.var_forecast(shocked, method, window=100)[:301], f[:301])


def test_var_next_is_last_forecast_and_scales_with_returns():
    r = garch_returns(400, seed=5, trend=1.0)
    for m in rm.VAR_METHODS:
        nxt = rm.var_next(r, m)
        assert nxt == pytest.approx(rm.var_forecast(np.append(r, 0.0), m)[-1])
        assert rm.var_next(2 * r, m) == pytest.approx(2 * nxt)   # VaR is positively homogeneous


def test_ewma_reacts_to_a_vol_jump_faster_than_historical():
    rng = np.random.default_rng(0)
    r = np.concatenate([rng.normal(0, 0.01, 400), rng.normal(0, 0.03, 20)])
    assert rm.var_next(r, "ewma") > 1.5 * rm.var_next(r, "historical")
    assert rm.var_next(r, "fhs") > 1.5 * rm.var_next(r, "historical")


def test_ewma_vol_handles_nan_and_short_input():
    assert np.isnan(rm.ewma_vol(np.full(10, 0.01))).all()
    r = np.full(60, 0.01)
    r[40] = np.nan
    s = rm.ewma_vol(r)
    assert s.size == 61 and np.isfinite(s[21:]).all()
    assert s[41] == pytest.approx(s[40]) and s[-1] == pytest.approx(0.01)
    with pytest.raises(ValueError):
        rm.ewma_vol(r, lam=1.0)


def test_bad_arguments_and_short_history():
    r = np.zeros(300)
    with pytest.raises(ValueError):
        rm.var_forecast(r, "garch")
    with pytest.raises(ValueError):
        rm.var_forecast(r, alpha=0.4)
    assert rm.var_next(np.full(10, 0.01)) is None
    assert rm.var_next(np.full(300, np.nan)) is None
    assert rm.var_next(np.zeros(300), "fhs") is None      # zero volatility: no residuals


# ---------------------------------------------------------------- book VaR default
def _book_frame(n: int = 300) -> pd.DataFrame:
    rng = np.random.default_rng(2)
    common = rng.normal(0, 0.01, n)
    return pd.DataFrame({"A": common + rng.normal(0, 0.004, n),
                         "B": common + rng.normal(0, 0.004, n)})


def test_book_var_default_on_and_fhs():
    assert DEFAULT_CONFIG["risk"]["max_book_var_95"] == 0.05
    assert DEFAULT_CONFIG["risk"]["book_var_method"] == "fhs"


def test_book_var_methods():
    df = _book_frame()
    w = {"A": 1.0, "B": 0.5}
    port = (df.to_numpy() @ np.array([1.0, 0.5]))
    assert book_var_95(w, df, method="fhs") == pytest.approx(rm.var_next(port, "fhs"))
    assert book_var_95(w, df) == pytest.approx(book_var_95(w, df, method="historical"))
    assert book_var_95({"A": 0.0}, df, method="fhs") == 0.0
    assert book_var_95(w, df.iloc[:30], method="fhs") is None   # too short to forecast


def test_book_var_scale_uses_method():
    df = _book_frame()
    limit = 0.5 * book_var_95({"A": 1.0, "B": 1.0}, df, method="fhs")
    w, after, note = book_var_scale("B", 1.0, {"A": 0.2}, df, limit, method="fhs")
    assert 0 < w < 1.0 and after <= limit and note


def test_scan_builds_book_by_default():
    from agentic_trader.config import make_config
    from agentic_trader.graph import TradingGraph
    from agentic_trader.memory import DecisionMemory
    cfg = make_config(memory_path=None)
    g = TradingGraph(cfg, memory=DecisionMemory(None), on_event=lambda *_: None)
    seen = []
    orig = g.propagate

    def spy(*a, **k):
        seen.append(k.get("book"))
        return orig(*a, **k)

    g.propagate = spy
    g.scan(["AAPL", "MSFT"], "2024-03-01", positions={"AAPL": 0.5})
    assert len(seen) == 2 and all(b is not None for b in seen)


# ---------------------------------------------------------------- factor exposures
def test_factor_exposures_recover_known_betas():
    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2020-01-01", periods=400)
    f = pd.DataFrame(rng.normal(0, 0.01, (400, 4)), index=idx, columns=list(rm.FACTOR_PROXIES))
    y = 1.2 * f["market"] - 0.5 * f["rates"] + 0.3 * f["momentum"] + rng.normal(0, 0.001, 400)
    b = rm.factor_exposures(y, f, window=126)
    assert b.iloc[:125].isna().all().all()
    last = b.iloc[-1]
    assert last["market"] == pytest.approx(1.2, abs=0.03)
    assert last["rates"] == pytest.approx(-0.5, abs=0.03)
    assert last["usd"] == pytest.approx(0.0, abs=0.03)
    assert last["r2"] > 0.95


def test_factor_returns_from_synthetic_provider():
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    f = rm.factor_returns(SyntheticProvider(cfg), date(2020, 1, 1), date(2020, 12, 31))
    assert list(f.columns) == list(rm.FACTOR_PROXIES) and len(f) > 200
    assert np.isfinite(f.to_numpy()).mean() > 0.95


# ---------------------------------------------------------------- stress and capacity
def test_stress_rows():
    idx = pd.bdate_range("2007-01-01", "2010-12-31")
    r = pd.Series(-0.01, index=idx)
    t = rm.stress_rows(r)
    assert list(t["window"]) == ["2008", "2020", "2022"]
    row08 = t.iloc[0]
    assert row08["days"] > 100 and row08["CR%"] < -50 and row08["worst_day%"] == pytest.approx(-1.0)
    assert row08["MDD%"] == pytest.approx(-row08["CR%"])
    assert t.iloc[1]["days"] == 0 and math.isnan(t.iloc[1]["CR%"])


def test_capacity_aum_closed_form_and_edges():
    # Drag 0.5%/yr at 1m on 10% vol costs 0.05 Sharpe; 0.1 needs drag x2, i.e. AUM x4.
    assert rm.capacity_aum(0.005, 0.10, 1e6) == pytest.approx(4e6)
    a = rm.capacity_aum(0.005, 0.10, 1e6)
    assert 0.005 * math.sqrt(a / 1e6) / 0.10 == pytest.approx(0.1)
    assert rm.capacity_aum(0.0, 0.10, 1e6) == math.inf
    with pytest.raises(ValueError):
        rm.capacity_aum(0.01, 0.0, 1e6)


def test_capacity_row_from_backtest_result():
    rng = np.random.default_rng(0)
    rets = rng.normal(0, 0.01, 504)
    res = BacktestResult(equity=np.cumprod(1 + rets), returns=rets, positions=np.ones(504),
                         impact_paid=0.01)
    row = rm.capacity_row(res, capital=1e6)
    vol = rets.std(ddof=1) * math.sqrt(252)
    assert row["impact_drag%"] == pytest.approx(0.5)
    assert row["capacity_aum"] == pytest.approx(1e6 * (0.1 * vol / 0.005) ** 2)
