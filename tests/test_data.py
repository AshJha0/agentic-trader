"""Data layer: cleaning, CSV quirks, synthetic point-in-time behaviour, and the
FRED publication-lag / staleness rules (tested offline with injected series)."""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from agentic_trader import Instrument, make_config
from agentic_trader.data import CSVProvider, SyntheticProvider
from agentic_trader.data import fred as fred_mod
from agentic_trader.data.base import clean_ohlcv, fx_macro
from agentic_trader.data.fred import FredClient, FredSeries

NAN = float("nan")


# ------------------------------------------------------------- clean_ohlcv
def test_clean_ohlcv_repairs_messy_input():
    raw = pd.DataFrame({
        "Open": [10, NAN, 12, 11, 13],
        "High": [9, 12, 13, 11, 14],        # first High below Open/Close -> widened
        "Low": [9, 11, 0, 10, 12],          # zero Low -> filled from Close
        "Close": [10, 11.5, 12.5, 0, 13.5],  # zero Close -> row dropped
    }, index=pd.to_datetime(["2024-01-03", "2024-01-02", "2024-01-04", "2024-01-05", "2024-01-04"]))
    df = clean_ohlcv(raw)
    assert list(df.index) == list(pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]))
    assert df.loc["2024-01-04", "Close"] == 13.5            # duplicate date keeps the last row
    assert df.loc["2024-01-02", "Open"] == 11.5              # missing Open -> Close
    assert (df["High"] >= df[["Open", "Close"]].max(axis=1)).all()
    assert (df["Low"] <= df[["Open", "Close"]].min(axis=1)).all()
    assert (df["Volume"] == 0).all()                          # no Volume column -> 0


def test_clean_ohlcv_strips_timezone():
    raw = pd.DataFrame({"Close": [1.0, 2.0]},
                       index=pd.DatetimeIndex(["2024-01-02", "2024-01-03"], tz="UTC"))
    assert clean_ohlcv(raw).index.tz is None


# -------------------------------------------------------------------- CSV
def _write(tmp_path, name, text):
    (tmp_path / name).write_text(text)


def test_csv_lowercase_adj_close_unsorted(tmp_path):
    _write(tmp_path, "ABC.csv",
           "date,adj close,volume\n2024-01-03,11,5\n2024-01-02,10,5\nnot-a-date,99,1\n2024-01-04,,5\n")
    p = CSVProvider(make_config(csv_dir=str(tmp_path)))
    h = p.history(Instrument.parse("ABC"), date(2024, 1, 1), date(2024, 1, 31))
    assert list(h["Close"]) == [10, 11]
    assert (h["High"] == h["Close"]).all()


def test_csv_missing_file_and_missing_close(tmp_path):
    p = CSVProvider(make_config(csv_dir=str(tmp_path)))
    with pytest.raises(FileNotFoundError):
        p.history(Instrument.parse("NOPE"), date(2024, 1, 1), date(2024, 2, 1))
    _write(tmp_path, "BAD.csv", "Date,Open\n2024-01-02,1\n")
    with pytest.raises(ValueError):
        p.history(Instrument.parse("BAD"), date(2024, 1, 1), date(2024, 2, 1))


def test_csv_news_filters_dates_and_blank_rows(tmp_path):
    _write(tmp_path, "ABC_news.csv",
           "Date,Headline,Sentiment\n2024-01-10,future news,0.9\n2024-01-05,ABC beats estimates,\n"
           "2024-01-04,,0.5\n2023-12-01,too old,0.1\n")
    p = CSVProvider(make_config(csv_dir=str(tmp_path)))
    items = p.news(Instrument.parse("ABC"), date(2024, 1, 6), 7)
    assert [i.headline for i in items] == ["ABC beats estimates"]
    assert items[0].sentiment is None                        # blank sentiment -> scored by lexicon


# -------------------------------------------------------------- synthetic
def test_synthetic_is_deterministic_and_seed_sensitive():
    ins = Instrument.parse("AAPL")
    a = SyntheticProvider(make_config()).history(ins, date(2024, 1, 1), date(2024, 2, 1))
    b = SyntheticProvider(make_config()).history(ins, date(2024, 1, 1), date(2024, 2, 1))
    c = SyntheticProvider(make_config(synthetic_seed=8)).history(ins, date(2024, 1, 1), date(2024, 2, 1))
    pd.testing.assert_frame_equal(a, b)
    assert not np.allclose(a["Close"], c["Close"])


def test_synthetic_fundamentals_respect_publication_lag():
    p = SyntheticProvider(make_config())
    ins = Instrument.parse("MSFT")
    # Q4-2023 results are published ~30 days after 2023-12-31.
    assert p.fundamentals(ins, date(2024, 1, 20))["report_period_end"] == "2023-09-30"
    assert p.fundamentals(ins, date(2024, 2, 15))["report_period_end"] == "2023-12-31"
    assert p.fundamentals(Instrument.parse("EURUSD"), date(2024, 2, 15)) == {}


def test_synthetic_news_never_after_as_of():
    p = SyntheticProvider(make_config())
    d = date(2024, 3, 1)
    for items in (p.news(Instrument.parse("NVDA"), d, 30), p.social(Instrument.parse("NVDA"), d, 30)):
        assert items and all(i.published <= d for i in items)


def test_synthetic_macro_is_static_and_carry_series_constant():
    cfg = make_config()
    p = SyntheticProvider(cfg)
    ins = Instrument.parse("USDJPY")
    m = p.macro(ins, date(2016, 1, 4))
    assert m["rate_diff"] == cfg["fx_policy_rates"]["USD"] - cfg["fx_policy_rates"]["JPY"]
    carry = p.carry_series(ins, pd.bdate_range("2024-01-01", "2024-01-10"))
    assert np.allclose(carry, m["rate_diff"] / 100)
    assert not p.carry_series(Instrument.parse("AAPL"), pd.bdate_range("2024-01-01", "2024-01-05")).any()


# ------------------------------------------------------------------- FRED
@pytest.fixture
def fake_fred(monkeypatch):
    """A FredClient whose downloads are replaced by in-memory series."""
    client = FredClient()
    series = {
        "DFF": pd.Series([5.0, 5.25, 5.33],
                         index=pd.to_datetime(["2023-07-26", "2023-07-27", "2024-04-18"])),
        "IRSTCI01JPM156N": pd.Series([-0.05, 0.10], index=pd.to_datetime(["2024-02-01", "2024-03-01"])),
        "ECBDFR": pd.Series([4.0], index=pd.to_datetime(["2023-01-01"])),  # stale later on
    }

    def load(spec):
        s = series.get(spec.series_id)
        if s is None:
            return None
        out = s.copy()
        out.index = out.index + pd.Timedelta(days=spec.lag_days)
        return out

    monkeypatch.setattr(client, "_load", load)
    monkeypatch.setattr(fred_mod, "_default", client)
    return client


def test_fred_publication_lag(fake_fred):
    spec = FredSeries("IRSTCI01JPM156N", 40, 100)
    # The March-2024 monthly average is only known ~40 days after 2024-03-01.
    assert fake_fred.value_asof(spec, date(2024, 4, 5)) == -0.05
    assert fake_fred.value_asof(spec, date(2024, 4, 11)) == 0.10
    assert fake_fred.value_asof(spec, date(2024, 1, 1)) is None     # nothing published yet


def test_fred_staleness(fake_fred):
    spec = FredSeries("ECBDFR", 1, 10)
    assert fake_fred.value_asof(spec, date(2023, 1, 5)) == 4.0
    assert fake_fred.value_asof(spec, date(2023, 3, 1)) is None      # too old to be current


def test_fred_series_asof_matches_point_lookups(fake_fred):
    spec = FredSeries("DFF", 1, 10)
    dates = pd.bdate_range("2023-07-25", "2023-08-20")
    vec = fake_fred.series_asof(spec, dates)
    for d in dates:
        v = fake_fred.value_asof(spec, d.date())
        assert (np.isnan(vec[d]) and v is None) or vec[d] == v


def test_fx_macro_modes(fake_fred):
    cfg = make_config()
    ins = Instrument.parse("USDJPY")
    old = date(2024, 4, 20)
    m = fx_macro(ins, old, cfg, real_world=True)                     # auto -> FRED
    assert m["source"].startswith("FRED") and m["rate_diff"] == pytest.approx(5.33 - 0.10)
    # The same query months later, with no newer USD value published, is stale -> no data.
    assert fx_macro(ins, date(2024, 8, 1), cfg, real_world=True) == {}
    assert fx_macro(ins, old, cfg, real_world=False)["source"].startswith("static")
    # Real-world, old date, no FRED coverage for the pair -> nothing, not today's static rates.
    assert fx_macro(Instrument.parse("EURGBP"), date(2019, 1, 2), cfg, real_world=True) == {}
    # ...but a recent date may fall back to the static table.
    recent = date.today() - timedelta(days=5)
    assert fx_macro(Instrument.parse("EURGBP"), recent, cfg, real_world=True)["source"].startswith("static")
    with pytest.raises(ValueError):
        fx_macro(ins, old, make_config(fx_macro_source="bogus"), real_world=True)
