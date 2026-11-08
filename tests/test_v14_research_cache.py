"""PLAN.md item 5.2b: the research inputs built once per series give the same forecasts,
regime labels and decisions as rebuilding them per decision, and stay point-in-time."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from agentic_trader.combine import desk_forecast, signal_inputs
from agentic_trader.config import make_config
from agentic_trader.data.synthetic import SyntheticProvider
from agentic_trader.graph import TradingGraph
from agentic_trader.instruments import Instrument
from agentic_trader.leakage import future_leak_canary
from agentic_trader.memory import DecisionMemory
from agentic_trader.quant import pycore
from agentic_trader.regime import RegimeSeries, regime_labels

# Synthetic bars start on 2015-01-01; the regime model is fitted from 2016 so its fixed
# history start (fit_start - 150 days) lies inside the data.
REGIME = {"enabled": True, "condition": True, "states": 2, "fit_start": "2016-01-01", "fit_end": "2019-12-31"}
IC = {"method": "ic", "window": 504}


def _frame(symbol: str = "AAPL") -> pd.DataFrame:
    return SyntheticProvider(make_config({})).history(Instrument.parse(symbol), date(2015, 1, 1), date(2022, 12, 31))


def test_vectorised_rolling_std_is_bit_identical_to_the_loop():
    rng = np.random.default_rng(3)
    x = 100 + np.cumsum(rng.standard_normal(900))
    x[[50, 400, 401]] = np.nan
    r = pycore.pct_change(x)
    for n in (5, 20, 126, 252):
        loop = np.full(len(x), np.nan)
        for i in range(n - 1, len(x)):
            loop[i] = x[i - n + 1:i + 1].std()
        assert np.array_equal(pycore.rolling_std(x, n), loop, equal_nan=True)
        loop = np.full(len(r), np.nan)
        for i in range(n, len(r)):
            loop[i] = r[i - n + 1:i + 1].std() * np.sqrt(252.0)
        assert np.array_equal(pycore.realized_vol(x, n, 252.0), loop, equal_nan=True)
    assert np.isnan(pycore.realized_vol(x[:10], 20, 252.0)).all()


def test_regime_labels_sliced_from_the_series_equal_labels_on_each_prefix():
    close = _frame()["Close"]
    series = RegimeSeries(close)
    for end in range(900, len(close), 37):
        fit_end = min(pd.Timestamp("2019-12-31"), close.index[end].replace(day=1))
        a = series.labels(end, 2, pd.Timestamp("2016-01-01"), fit_end)
        b = regime_labels(close.iloc[:end + 1], None, 2, pd.Timestamp("2016-01-01"), fit_end)
        assert np.array_equal(a[0], b[0])
        assert (a[1] is None) == (b[1] is None)
        if a[1] is not None:
            assert np.array_equal(a[1], b[1])


@pytest.mark.parametrize("conformal", [False, True])
def test_forecast_from_sliced_inputs_equals_the_rebuilt_forecast(conformal):
    df = _frame()
    ins = Instrument.parse("AAPL")
    cfg = {**make_config({"combination": IC})["combination"],
           "conformal": {"enabled": conformal, "alpha": 0.2, "calibration_share": 0.4}}
    inputs = signal_inputs(df, ins, cfg)
    series = RegimeSeries(df["Close"])
    for end in range(800, len(df), 41):
        head = df.iloc[:end + 1]
        labels = series.labels(end, 2, pd.Timestamp("2016-01-01"), pd.Timestamp("2019-12-31"))[0]
        for regimes in (None, labels):
            a = desk_forecast(head, ins, cfg, None, regimes, inputs.head(end + 1))
            b = desk_forecast(head, ins, cfg, None, regimes)
            assert repr(a) == repr(b)          # exact: float repr round-trips, NaN prints alike


def test_inputs_must_match_the_frame():
    df = _frame()
    cfg = make_config({"combination": IC})["combination"]
    inputs = signal_inputs(df, Instrument.parse("AAPL"), cfg)
    with pytest.raises(ValueError):
        desk_forecast(df.iloc[:-1], Instrument.parse("AAPL"), cfg, inputs=inputs)


@pytest.mark.parametrize("symbol,conformal", [("AAPL", False), ("EURUSD", True)])
def test_cached_desk_decides_exactly_like_the_rebuilding_desk(symbol, conformal):
    """Many as-of dates through the full offline desk: forecast, regime label and decision
    are identical with the series cache on and off."""
    overrides = {"data_provider": "synthetic", "llm_provider": "offline", "combination": IC,
                 "regime": REGIME, "conformal": {"enabled": conformal}}
    provider = SyntheticProvider(make_config({}))
    on = TradingGraph({**overrides, "research_history_end": "2021-12-31"}, provider=provider,
                      memory=DecisionMemory(None), on_event=lambda *_: None)
    off = TradingGraph(overrides, provider=provider, memory=DecisionMemory(None), on_event=lambda *_: None)
    labelled = 0
    dates = [date(2020, 1, 6) + timedelta(days=23 * i) for i in range(30)]
    for d in dates:
        sa, da = on.propagate(symbol, d)
        sb, db = off.propagate(symbol, d)
        assert repr(sa.forecast) == repr(sb.forecast)
        assert sa.regime == sb.regime
        labelled += sa.regime is not None
        assert repr(da) == repr(db)
    assert labelled == len(dates)
    assert len(on._research) == 1                      # one series built, sliced 30 times
    assert not off._research


def test_cache_is_off_when_the_history_start_moves():
    """IC combination alone: the history start follows the as-of date, so nothing is cached."""
    g = TradingGraph({"data_provider": "synthetic", "llm_provider": "offline", "combination": IC,
                      "research_history_end": "2021-12-31"},
                     memory=DecisionMemory(None), on_event=lambda *_: None)
    g.prepare("AAPL", date(2020, 6, 1))
    assert not g._research


def test_future_leak_canary_is_clean_with_the_cache_on():
    shock = date(2020, 9, 1)
    config = {"data_provider": "synthetic", "analysts": ["technical", "alpha"], "alpha_lookback_days": 700,
              "combination": IC, "regime": REGIME, "conformal": {"enabled": True},
              "research_history_end": "2021-06-30"}
    res = future_leak_canary(config, SyntheticProvider(make_config({})), "AAPL", shock,
                             [shock - timedelta(days=30), shock - timedelta(days=1)], [shock + timedelta(days=10)],
                             record_prompts=False)
    assert res.clean, f"look-ahead: {res.leaks}"
    assert res.reacted
