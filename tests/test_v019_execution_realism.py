"""v0.19 coverage: execution-realism edges (stop slippage, participation cap, impact
calibration). Deterministic and offline."""
from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agentic_trader import execution_realism as er


def test_stop_fill_cases():
    assert er.stop_fill_with_slippage(1.0, 95, 94, 100, 90, 0.001) == pytest.approx(94 * 0.999)  # long gap
    assert er.stop_fill_with_slippage(1.0, 95, 99, 100, 90, 0.0, 0.5) == pytest.approx(92.5)
    assert math.isnan(er.stop_fill_with_slippage(1.0, 95, 99, 100, 96))                     # not hit
    assert er.stop_fill_with_slippage(-1.0, 105, 106, 110, 100) == pytest.approx(106)       # short gap
    assert er.stop_fill_with_slippage(-1.0, 105, 101, 110, 100, 0.0, 1.0) == pytest.approx(110)
    assert math.isnan(er.stop_fill_with_slippage(-1.0, 105, 101, 104, 100))
    assert math.isnan(er.stop_fill_with_slippage(0.0, 95, 94, 100, 90))
    assert math.isnan(er.stop_fill_with_slippage(1.0, float("nan"), 94, 100, 90))
    for bad in ({"range_frac": 1.5}, {"half_spread": -0.1}):
        with pytest.raises(ValueError):
            er.stop_fill_with_slippage(1.0, 95, 94, 100, 90, **bad)


@settings(max_examples=100, deadline=None)
@given(side=st.sampled_from([1.0, -1.0]), o=st.floats(90, 110), stop=st.floats(90, 110),
       spread=st.floats(0, 0.01), frac=st.floats(0, 1))
def test_stop_fill_stays_inside_the_bar_and_slippage_is_a_cost(side, o, stop, spread, frac):
    h, low = max(o, 110.0), min(o, 90.0)
    px = er.stop_fill_with_slippage(side, stop, o, h, low, spread, frac)
    if not math.isnan(px):
        assert low - 1e-9 <= px <= h + 1e-9
    s = er.stop_slippage_frac(side, stop, o, h, low, spread, frac)
    assert s >= -1e-12


def test_stop_slippage_frac_zero_cases():
    assert er.stop_slippage_frac(0.0, 95, 94, 100, 90) == 0.0
    assert er.stop_slippage_frac(1.0, 95, 99, 100, 96) == 0.0


def test_cap_participation_errors():
    with pytest.raises(ValueError):
        er.cap_participation([0.1], [10.0], [1e6], capital=0)
    with pytest.raises(ValueError):
        er.cap_participation([0.1, 0.2], [10.0], [1e6], capital=1e6)


def test_spread_helpers_and_calibration():
    assert math.isnan(er.spread_consistent_y(-1, 0.01))
    assert math.isnan(er.spread_consistent_y(0.001, 0.0))
    assert er.spread_consistent_y(0.002, 0.01, 0.01) == pytest.approx(1.0)
    assert math.isnan(er.abdi_ranaldo([1.0], [1.0], [1.0]))
    assert er.calibrate_impact({}).empty
    df = er.simulate_ohlc(120, spread=0.002, seed=3)
    out = er.calibrate_impact({"X": df})
    assert list(out.index) == ["X"] and out.loc["X", "days"] == 120
    assert np.isfinite(out.loc["X", "daily_vol_pct"])
