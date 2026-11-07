"""v0.14 item 5.8: purged walk-forward CV, the future-leak canary, the point-in-time store."""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from agentic_trader.config import make_config
from agentic_trader.data.synthetic import SyntheticProvider
from agentic_trader.instruments import Instrument
from agentic_trader.leakage import (FeatureRecord, LookaheadError, PointInTimeStore, ShockedProvider, check_read,
                                    future_leak_canary, ic_purged, ic_purged_series, purged_walk_forward)

# ------------------------------------------------------------------ splitter


@pytest.mark.parametrize("n,h,k,emb", [(100, 5, 5, None), (257, 10, 4, 3), (60, 1, 3, 0)])
def test_walk_forward_folds_are_purged_and_embargoed(n, h, k, emb):
    folds = purged_walk_forward(n, h, k, emb)
    e = h if emb is None else emb
    assert len(folds) == k
    assert np.array_equal(np.concatenate([f.test for f in folds]), np.arange(n))  # tests tile the sample
    assert folds[0].train.size == 0
    for j, f in enumerate(folds):
        a = int(f.test[0])
        assert f.train.size == 0 or f.train.max() + h < a        # no training label reaches the test block
        for prev in folds[:j]:
            b = int(prev.test[-1]) + 1
            assert not np.isin(f.train, np.arange(b, b + e)).any()  # embargo after each earlier block
        assert np.array_equal(f.scored, f.test[: f.test.size - h])  # scored labels stay inside the block


def test_walk_forward_rejects_bad_arguments():
    with pytest.raises(ValueError):
        purged_walk_forward(100, 0)
    with pytest.raises(ValueError):
        purged_walk_forward(100, 5, 1)
    with pytest.raises(ValueError):
        purged_walk_forward(20, 5, 5)
    with pytest.raises(ValueError):
        purged_walk_forward(100, 5, 5, embargo=-1)


# ------------------------------------------------------------------ purged IC


def _fwd(close: np.ndarray, h: int) -> np.ndarray:
    out = np.full(close.size, np.nan)
    out[:-h] = close[h:] / close[:-h] - 1.0
    return out


def test_ic_purged_perfect_and_null_signals():
    rng = np.random.default_rng(0)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 1000)))
    fwd = _fwd(close, 10)
    perfect = ic_purged(fwd, fwd, 10)
    assert perfect.ic == pytest.approx(1.0) and len(perfect.folds) == 5
    assert perfect.n == 5 * (200 - 10)                          # each fold loses its last h labels
    noise = [ic_purged(rng.normal(size=1000), fwd, 10).t for _ in range(200)]
    # fold-dispersion t has 4 degrees of freedom: |t| >= 2.78 about 5% of the time under the null
    assert np.mean(np.abs(noise) >= 2.78) < 0.12


def test_ic_purged_handles_short_and_missing_inputs():
    short = ic_purged([1.0, 2.0, 3.0], [1.0, 2.0, 3.0], 1)
    assert math.isnan(short.ic) and short.n == 0
    with pytest.raises(ValueError):
        ic_purged([1.0, 2.0], [1.0], 1)
    with pytest.raises(ValueError):
        ic_purged(np.arange(100.0), np.arange(100.0), 0)
    s = np.full(500, np.nan)
    assert math.isnan(ic_purged(s, np.arange(500.0), 5).ic)
    gate = ic_purged(np.arange(500.0), np.arange(500.0), 5).as_gate()
    assert set(gate) == {"IC", "t(IC)", "n"} and gate["IC"] == pytest.approx(1.0)


def test_ic_purged_series_means_scored_dates():
    daily = pd.Series(np.r_[np.full(50, 0.1), np.full(50, 0.3)])
    pic = ic_purged_series(daily, 5, n_folds=2)
    assert pic.folds == pytest.approx((0.1, 0.3)) and pic.n == 90


# ------------------------------------------------------------------ canary

CONFIG = {"data_provider": "synthetic", "analysts": None, "alpha_lookback_days": 700}


def test_shocked_provider_changes_only_data_on_or_after_the_shock():
    base = SyntheticProvider(make_config({}))
    ins = Instrument.parse("AAPL")
    t = date(2023, 6, 1)
    shocked = ShockedProvider(base, "AAPL", t, 3.0)
    a = base.history(ins, date(2023, 1, 1), date(2023, 12, 31))
    b = shocked.history(ins, date(2023, 1, 1), date(2023, 12, 31))
    pre = a.index < pd.Timestamp(t)
    pd.testing.assert_frame_equal(a[pre], b[pre])
    assert np.allclose(b.loc[~pre, "Close"], 3.0 * a.loc[~pre, "Close"])
    assert shocked.name == base.name
    assert len(shocked.news(ins, date(2023, 5, 31), 7)) == len(base.news(ins, date(2023, 5, 31), 7))
    assert len(shocked.news(ins, t, 7)) == len(base.news(ins, t, 7)) + 1
    msft = Instrument.parse("MSFT")
    pd.testing.assert_frame_equal(base.history(msft, t, date(2023, 7, 1)), shocked.history(msft, t, date(2023, 7, 1)))


@pytest.mark.parametrize("symbol,shock,cross_section", [
    ("AAPL", date(2023, 6, 1), True),
    ("AAPL", date(2024, 2, 12), False),
    ("EURUSD", date(2023, 9, 4), True),
    ("EURUSD", date(2024, 3, 18), False),
])
def test_future_leak_canary_finds_no_leak(symbol, shock, cross_section):
    """Full offline desk (analysts incl. alpha, debate, trader, risk, PM, prompts) plus the
    alpha library: identical on two dates before the shock, changed on it. The cross-sectional
    analyst (the slowest, a universe per date) runs in one case per asset class."""
    from datetime import timedelta
    analysts = (["technical", "fundamentals", "news", "sentiment", "alpha"] if symbol == "AAPL"
                else ["technical", "macro", "news", "sentiment", "alpha"])
    if cross_section:
        analysts.append("xalpha")
    before, after = [shock - timedelta(days=15), shock - timedelta(days=1)], [shock]
    res = future_leak_canary({**CONFIG, "analysts": analysts}, SyntheticProvider(make_config({})), symbol, shock,
                             before, after)
    assert res.clean, f"look-ahead: {res.leaks}"
    assert res.reacted == after          # the shock did reach the desk


def test_canary_catches_an_analyst_that_reads_ahead(monkeypatch):
    """An analyst that reads one week past the as-of date must be caught."""
    from datetime import timedelta

    from agentic_trader.agents import analysts
    from agentic_trader.state import AnalystReport

    class Peeking(analysts.Analyst):
        name = "peeking"

        def gather(self, state, provider):
            h = provider.history(state.instrument, state.as_of, state.as_of + timedelta(days=7))
            return {"future_close": float(h["Close"].iloc[-1])}

        def rules(self, f, state):
            return AnalystReport(self.name, 0.0, 0.1, f"next week closes at {f['future_close']:.4f}", [], f)

    monkeypatch.setitem(analysts.ANALYSTS, "peeking", Peeking)
    shock = date(2023, 6, 1)
    res = future_leak_canary({**CONFIG, "analysts": ["technical", "peeking"]}, SyntheticProvider(make_config({})), "AAPL",
                             shock, [date(2023, 5, 29)], [], record_prompts=False)
    assert not res.clean and "report:peeking" in res.leaks[date(2023, 5, 29)]


def test_canary_rejects_misordered_dates():
    with pytest.raises(ValueError):
        future_leak_canary(CONFIG, SyntheticProvider(make_config({})), "AAPL", date(2023, 6, 1), [date(2023, 6, 1)], [])


# ------------------------------------------------------------------ point-in-time store


def _rec(value: float, as_of: date, visible: date, accn: str = "0001") -> FeatureRecord:
    return FeatureRecord("eps", "AAPL", as_of, visible, value, "edgar", accn)


def test_point_in_time_store_refuses_lookahead(tmp_path):
    path = tmp_path / "features.jsonl"
    store = PointInTimeStore(path)
    q1 = _rec(1.0, date(2024, 3, 31), date(2024, 5, 2))
    restated = _rec(1.1, date(2024, 3, 31), date(2024, 8, 1), "0002")
    store.append(q1)
    store.append(restated)
    store.append(q1)                                       # exact duplicate: no-op
    assert len(store) == 2
    assert store.latest("eps", "AAPL", date(2024, 4, 30)) is None   # quarter over, not yet filed
    assert store.latest("eps", "AAPL", date(2024, 6, 1)) == q1
    assert store.latest("eps", "AAPL", date(2024, 9, 1)) == restated
    with pytest.raises(LookaheadError):
        store.read(restated, date(2024, 6, 1))
    with pytest.raises(LookaheadError):
        check_read(q1, date(2024, 5, 1))
    assert store.read(q1, date(2024, 5, 2)) == q1
    with pytest.raises(ValueError):
        store.append(_rec(9.9, date(2024, 3, 31), date(2024, 5, 2)))     # same accession, new value
    with pytest.raises(ValueError):
        _rec(1.0, date(2024, 3, 31), date(2024, 3, 1))                  # public before it happened
    reloaded = PointInTimeStore(path)
    assert list(reloaded) == [q1, restated]
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2
    assert len(PointInTimeStore()) == 0
