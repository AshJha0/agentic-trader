"""Plan item 5.7: edge-case validators and the conventions they pin (docs/review/PLAN.md section 6)."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agentic_trader import TradingGraph, make_config, quant
from agentic_trader.agents.risk import PortfolioManager
from agentic_trader.alpha import EQUITY_ALPHAS, compute_alphas
from agentic_trader.data import SyntheticProvider
from agentic_trader.instruments import Instrument
from agentic_trader.memory import DecisionMemory
from agentic_trader.quant import pycore
from agentic_trader.stats import sharpe_stats
from agentic_trader.validate import (BarValidationError, bar_problems, cap_short_notional, common_sessions,
                                     ledgers_match, read_ledger_csv, require_valid_bars, session_close_utc,
                                     survivorship_statement, write_ledger_csv)

CFG = make_config(memory_path=None)


def _bars(n: int = 40, start: str = "2024-01-02", seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    open_ = close * (1 + rng.normal(0, 0.002, n))
    return pd.DataFrame({"Open": open_, "High": np.maximum(open_, close) * 1.005,
                         "Low": np.minimum(open_, close) * 0.995, "Close": close,
                         "Volume": np.full(n, 1e6)}, index=idx)


# ------------------------------------------------------------------ bar validator
def test_clean_bars_pass():
    assert bar_problems(_bars(), "equity") == []


@pytest.mark.parametrize("row, col, value, reason", [
    (5, "Close", 0.0, "zero or negative Close"),
    (6, "Open", -1.0, "zero or negative Open"),
    (7, "Low", np.nan, "NaN Low"),
    (8, "High", 1.0, "High below Low"),
])
def test_bad_prices_refused_with_reason(row, col, value, reason):
    d = _bars()
    d.iat[row, d.columns.get_loc(col)] = value
    assert any(reason in r for r in bar_problems(d, "equity"))


def test_duplicate_unsorted_and_gap_dates_refused():
    d = _bars()
    dup = pd.concat([d.iloc[:10], d.iloc[9:10], d.iloc[10:]])
    assert any("duplicate date" in r for r in bar_problems(dup, "equity"))
    swapped = d.iloc[[0, 2, 1] + list(range(3, len(d)))]
    assert any("out of order" in r for r in bar_problems(swapped, "equity"))
    gapped = d.drop(d.index[10:16])  # 6 business days missing -> an 8+ calendar-day step
    assert any("gap of" in r for r in bar_problems(gapped, "equity"))
    # Calendar tolerance is per asset class: a 7-day step (4 business days missing)
    # passes equity, fails FX.
    week = d.drop(d.index[10:14])
    assert bar_problems(week, "equity") == []
    assert any("limit 5 for fx" in r for r in bar_problems(week, "fx"))


def test_require_valid_bars_raises_all_reasons():
    d = _bars()
    d.iat[3, 3] = np.nan
    d.iat[4, 0] = 0.0
    with pytest.raises(BarValidationError) as e:
        require_valid_bars(d, "equity", "SPY")
    assert len(e.value.reasons) == 2 and "refusing SPY" in str(e.value)


def test_graph_refuses_bad_bar_from_provider():
    class BadBar(SyntheticProvider):
        def history(self, instrument, start, end):
            h = super().history(instrument, start, end).copy()
            h.iat[-3, h.columns.get_loc("High")] = h.iat[-3, h.columns.get_loc("Low")] * 0.5
            return h

    g = TradingGraph(CFG, provider=BadBar(CFG), memory=DecisionMemory(None), on_event=lambda *_: None)
    with pytest.raises(BarValidationError, match="High below Low"):
        g.prepare("SPY", date(2024, 3, 1))


# ------------------------------------------------------- synthetic-split invariance
def _metrics_tuple(prices: np.ndarray, weights: np.ndarray) -> tuple[float, ...]:
    res = quant.run_backtest(prices, weights, quant.BacktestConfig(cost_bps=1.0))
    m = res.metrics
    r = np.diff(prices) / prices[:-1]
    return (m.cumulative_return, m.annualized_vol, m.sharpe, m.max_drawdown,
            sharpe_stats(r).sharpe_annual, quant.historical_var(r, 0.95), quant.historical_cvar(r, 0.95))


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(0, 10_000), factor=st.sampled_from([2.0, 3.0, 0.5, 10.0, 1 / 3]),
       split_at=st.integers(30, 270))
def test_split_adjusted_series_leaves_metrics_unchanged(seed, factor, split_at):
    """An unadjusted series has a factor-k step at the split; adjusting it (dividing every
    earlier price by k) must give back a series whose returns, and so every return-based
    metric, equal those of the true series. Scaling the whole series by a constant must
    leave the metrics and every scale-free alpha unchanged as well."""
    df = _bars(300, seed=seed)
    true = df["Close"].to_numpy()
    raw = true.copy()
    raw[:split_at] *= factor           # as traded: pre-split prices k times higher
    adjusted = raw.copy()
    adjusted[:split_at] /= factor      # the split-adjusted series a provider hands over
    w = np.where(np.arange(300) % 40 < 20, 1.0, 0.5)
    base = _metrics_tuple(true, w)
    np.testing.assert_allclose(_metrics_tuple(adjusted, w), base, rtol=1e-9, atol=1e-12)
    np.testing.assert_allclose(_metrics_tuple(true * factor, w), base, rtol=1e-9, atol=1e-12)

    ins = Instrument.parse("SPY")
    scaled = df.copy()
    scaled[["Open", "High", "Low", "Close"]] *= factor
    a, b = compute_alphas(df, ins, EQUITY_ALPHAS), compute_alphas(scaled, ins, EQUITY_ALPHAS)
    pd.testing.assert_frame_equal(a, b, rtol=1e-9, atol=1e-12)


# ----------------------------------------------- FX 17:00 NY vs equity close, DST
@pytest.mark.parametrize("d, eq_utc, fx_utc", [
    (date(2024, 1, 16), 21, 22),   # EST: UTC-5
    (date(2024, 7, 16), 20, 21),   # EDT: UTC-4
    (date(2024, 3, 8), 21, 22),    # Friday before the US change
    (date(2024, 3, 11), 20, 21),   # Monday after it
    (date(2024, 3, 26), 20, 21),   # between the US (10 Mar) and EU (31 Mar) changes: NY clock rules
])
def test_session_closes_follow_new_york_clock(d, eq_utc, fx_utc):
    eq, fx = session_close_utc(d, "equity"), session_close_utc(d, "fx")
    assert (eq.hour, fx.hour) == (eq_utc, fx_utc)
    assert eq.date() == fx.date() == d
    assert fx - eq == timedelta(hours=1)


def test_one_sleeve_holiday_is_not_a_rebalance_date():
    idx = pd.bdate_range("2024-07-01", "2024-07-08")
    fx = pd.DataFrame({"Close": 1.0}, index=idx)
    eq = fx.drop(pd.Timestamp("2024-07-04"))   # US Independence Day: equities shut, FX trades
    common = common_sessions({"SPY": eq, "EURUSD": fx})
    assert pd.Timestamp("2024-07-04") not in common
    assert list(common) == list(eq.index)


# ------------------------------------------------------------- stop convention
@pytest.fixture(params=["facade", "python"])
def backend(request, monkeypatch):
    if request.param == "python":
        monkeypatch.setattr(quant, "_cpp", None)
    return request.param


def _stop_run(open_, high, low, close, stop, take):
    n = len(close)
    cfg = quant.BacktestConfig(cost_bps=0.0)
    return quant.run_backtest(np.array(close, float), np.ones(n), cfg, open=np.array(open_, float),
                              high=np.array(high, float), low=np.array(low, float),
                              stop=np.full(n, stop), take=np.full(n, take))


def test_gap_through_stop_fills_at_open(backend):
    # Bar 2 opens at 90, below the 95 stop: the fill is the open, not the stop level.
    r = _stop_run([100, 100, 90, 92], [101, 101, 93, 93], [99, 99, 88, 91], [100, 100, 92, 92], 95.0, np.nan)
    assert r.exits[2] == 1
    assert r.equity[2] == pytest.approx(100_000 * 0.90, rel=1e-12)


def test_stop_inside_range_fills_at_stop(backend):
    r = _stop_run([100, 100, 99, 97], [101, 101, 100, 98], [99, 99, 94, 96], [100, 100, 97, 97], 95.0, np.nan)
    assert r.exits[2] == 1
    assert r.equity[2] == pytest.approx(100_000 * 0.95, rel=1e-12)


def test_stop_and_target_in_one_bar_resolves_to_stop(backend):
    """Pinned engine rule (pycore._exit_fill, cpp backtest.hpp): open first, then the range
    with the stop before the target. Daily bars do not say which traded first; assuming
    the worse one is the conservative choice and is kept."""
    r = _stop_run([100, 100, 100, 100], [101, 101, 111, 100], [99, 99, 94, 99], [100, 100, 100, 100], 95.0, 110.0)
    assert r.exits[2] == 1
    assert r.equity[2] == pytest.approx(100_000 * 0.95, rel=1e-12)


def test_gap_through_target_fills_at_open(backend):
    r = _stop_run([100, 100, 112, 112], [101, 101, 113, 113], [99, 99, 111, 111], [100, 100, 112, 112], 95.0, 110.0)
    assert r.equity[2] == pytest.approx(100_000 * 1.12, rel=1e-12)


# ------------------------------------------------------- survivorship, shorts, ledger
def test_survivorship_statement_per_row():
    start = date(2016, 1, 4)
    assert "trading at design start" in survivorship_statement("SPY", date(1993, 1, 29), start)
    assert "survivorship bias possible" in survivorship_statement("NEWCO", date(2019, 5, 1), start)
    assert "absent from the table" in survivorship_statement("GONE", None, start)


def test_cap_short_notional():
    assert cap_short_notional(-0.8, 0.3) == -0.3
    assert cap_short_notional(-0.2, 0.3) == -0.2
    assert cap_short_notional(0.9, 0.3) == 0.9
    assert cap_short_notional(-0.8, None) == -0.8
    with pytest.raises(ValueError):
        cap_short_notional(-0.5, float("nan"))


def test_guardrails_enforce_short_notional_cap():
    pm = PortfolioManager(None, CFG)
    f = {"max_position": 1.0, "max_var_95": 0.0, "var_95_1d": 0.01, "var_95_1d_short": 0.01,
         "short_selling_allowed": True, "max_short_notional": 0.25}
    w, notes = pm.guardrails(-0.9, f)
    assert w == -0.25 and any("max short notional" in n for n in notes)
    assert pm.guardrails(0.9, f)[0] == 0.9
    f["max_short_notional"] = None
    assert pm.guardrails(-0.9, f)[0] == -0.9


def test_ledger_floats_round_trip_exactly(tmp_path):
    rng = np.random.default_rng(3)
    frame = pd.DataFrame(rng.normal(0, 0.01, (20, 3)) / 3, columns=["a", "b", "c"],
                         index=pd.bdate_range("2026-09-29", periods=20))
    frame.iat[4, 1] = np.nan
    path = tmp_path / "ledger.csv"
    write_ledger_csv(frame, path)
    back = read_ledger_csv(path)
    back.index.freq = frame.index.freq
    np.testing.assert_array_equal(back.to_numpy(), frame.to_numpy())
    assert ledgers_match(back, frame, tol=0.0)
    nudged = frame + 1e-15
    assert ledgers_match(nudged, frame) and not ledgers_match(nudged, frame, tol=0.0)
    assert not ledgers_match(frame.iloc[:-1], frame)
