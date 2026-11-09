"""v0.17 R4: session vintage storage, finality, NYSE special days, OMS book limits, push retry."""
from __future__ import annotations

import gzip
import importlib.util
import json
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agentic_trader.config import make_config
from agentic_trader.instruments import Instrument
from agentic_trader.oms import (NYSE_SPECIAL_CLOSURES, OMS, SleeveCalendar, nyse_close_time, nyse_early_closes,
                                nyse_holidays)

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- R4.1 session bars
class FakeYahoo:
    """Answers like the Yahoo provider: adjusted history plus a raw-close/actions table."""

    def __init__(self, dividend: float = 0.5):
        idx = pd.bdate_range("2026-01-02", "2026-03-31")
        self.idx = idx
        close = pd.Series(np.linspace(100, 110, len(idx)), index=idx)
        self.adj = pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1, "Close": close,
                                 "Volume": 1e6}, index=idx)
        split = pd.Series(0.0, index=idx)
        split.iloc[30] = 2.0
        div = pd.Series(0.0, index=idx)
        div.iloc[40] = dividend
        self.actions = pd.DataFrame({"RawClose": close * 1.01, "Split": split, "Dividend": div}, index=idx)

    def history(self, instrument, start, end):
        return self.adj.loc[(self.adj.index >= pd.Timestamp(start)) & (self.adj.index <= pd.Timestamp(end))]

    def corporate_actions(self, instrument):
        return None if instrument.is_fx else self.actions.copy()


def test_session_bars_are_stored_compact_deterministic_and_append_only(tmp_path):
    ops = _load("paper_ops")
    fake = FakeYahoo()
    rec = ops.VintageRecorder(fake)
    for sym in ("SPY", "AAPL", "EURUSD"):
        rec.history(Instrument.parse(sym), date(2026, 1, 2), date(2026, 3, 20))
    rec.history(Instrument.parse("SPY"), date(2026, 2, 1), date(2026, 3, 20))   # a narrower request too
    w = ops.store_session_bars(rec, tmp_path, date(2026, 3, 20))
    assert list(w["files"]) == ["prices.csv.gz", "actions.csv.gz"] and w["symbols"] == 3
    assert all(len(h) == 64 for h in w["files"].values())   # only these hashes are published
    day = tmp_path / "2026-03-20"
    prices = ops.read_session_bars(day / "prices.csv.gz")
    assert set(prices) == {"SPY", "AAPL", "EURUSD"}
    # the widest frame per symbol, round-tripped bit-exactly
    pd.testing.assert_frame_equal(prices["SPY"], fake.history(None, date(2026, 1, 2), date(2026, 3, 20)),
                                  check_names=False, check_freq=False, check_dtype=False)
    acts = ops.read_session_bars(day / "actions.csv.gz")
    assert set(acts) == {"SPY", "AAPL"}                      # FX has no actions
    assert set(acts["SPY"].columns) == {"RawClose", "Split", "Dividend"}
    assert acts["SPY"]["Split"].max() == 2.0 and acts["SPY"]["Dividend"].max() == 0.5
    assert acts["SPY"].index.max() <= pd.Timestamp("2026-03-20")
    # unadjusted close is recoverable: RawClose x splits after the date
    raw = acts["SPY"]
    unadj = raw["RawClose"] * raw["Split"].where(raw["Split"] > 0, 1.0)[::-1].cumprod()[::-1].shift(-1).fillna(1.0)
    assert unadj.iloc[0] == pytest.approx(raw["RawClose"].iloc[0] * 2.0)
    # deterministic bytes (gzip mtime 0): a re-run with the same bars changes nothing
    before = (day / "prices.csv.gz").read_bytes()
    assert gzip.decompress(before).startswith(b"date,symbol")
    ops.store_session_bars(rec, tmp_path, date(2026, 3, 20))
    assert sorted(p.name for p in day.iterdir()) == ["actions.csv.gz", "prices.csv.gz"]
    assert (day / "prices.csv.gz").read_bytes() == before
    # a same-session re-run that read different bars keeps both files (append-only)
    fake.adj.loc[fake.adj.index[-15], "Close"] += 1.0
    rec2 = ops.VintageRecorder(fake)
    rec2.history(Instrument.parse("SPY"), date(2026, 1, 2), date(2026, 3, 20))
    w2 = ops.store_session_bars(rec2, tmp_path, date(2026, 3, 20))
    name2 = next(iter(w2["files"]))
    assert name2.startswith("prices.") and name2 != "prices.csv.gz"
    assert (day / "prices.csv.gz").read_bytes() == before
    # size note: 3 symbols x ~55 bars
    assert w["bytes"] < 20_000


def test_bars_are_never_published_and_a_provider_without_actions_still_stores_prices(tmp_path):
    ops = _load("paper_ops")
    assert "bars" not in ops.PUBLISHED and "ledger_vintage.csv" in ops.PUBLISHED
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "results/paper/bars/" in ignore     # Yahoo bars stay local / in a private artifact

    class NoActions:
        def history(self, instrument, start, end):
            return FakeYahoo().history(instrument, start, end)

    rec = ops.VintageRecorder(NoActions())
    rec.history(Instrument.parse("SPY"), date(2026, 1, 2), date(2026, 1, 30))
    assert list(ops.store_session_bars(rec, tmp_path, date(2026, 1, 30))["files"]) == ["prices.csv.gz"]


def test_paper_run_writes_the_session_bars_and_records_them(tmp_path):
    mod = _load("paper_trade_v09")
    out = tmp_path / "paper"
    assert mod.main(["--data", "synthetic", "--freeze", "2024-01-02", "--as-of", "2024-02-15", "--out", str(out)]) == 0
    run = json.loads((out / "runs.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert (out / "bars" / "2024-02-15" / "prices.csv.gz").exists()
    assert list(run["bars"]["files"]) == ["prices.csv.gz"] and run["bars"]["symbols"] >= 30
    assert run["vintage_id"] == json.loads(mod.FREEZE_FILE.read_text(encoding="utf-8"))["vintage_id"]
    vint = pd.read_csv(out / "ledger_vintage.csv")
    led = pd.read_csv(out / "ledger.csv", index_col=0)
    assert len(vint) == len(led) and set(vint["vintage_id"]) == {run["vintage_id"]}
    assert run["same_day_revisions"] == 0 and run["fetched_at_utc"].endswith("Z")


# ---------------------------------------------------------------- R4.2 finality
def test_a_session_that_may_not_be_final_is_refused():
    mod = _load("paper_trade_v09")
    mod.assert_final(date(2026, 11, 6), date(2026, 11, 9))       # strictly before: fine
    for as_of in (date(2026, 11, 9), date(2026, 11, 10)):
        with pytest.raises(SystemExit, match="not be final"):
            mod.assert_final(as_of, date(2026, 11, 9))


def test_main_refuses_today_in_new_york(tmp_path, monkeypatch):
    mod = _load("paper_trade_v09")
    monkeypatch.setattr(mod, "exchange_today", lambda: date(2024, 2, 15))
    with pytest.raises(SystemExit, match="not be final"):
        mod.main(["--data", "synthetic", "--freeze", "2024-01-02", "--as-of", "2024-02-15", "--out", str(tmp_path)])
    assert not (tmp_path / "ledger.csv").exists()


def test_same_day_revision_is_flagged_in_the_report(tmp_path, monkeypatch):
    mod = _load("paper_trade_v09")
    out = tmp_path / "paper"
    assert mod.main(["--data", "synthetic", "--freeze", "2024-01-02", "--as-of", "2024-02-15", "--out", str(out)]) == 0
    first = pd.read_csv(out / "ledger.csv", index_col=0, parse_dates=True)
    real = mod.recompute

    def restated_last(as_of, cfg, provider, freeze, exposure=None):
        f = real(as_of, cfg, provider, freeze)
        f.loc[first.index[-1], f.columns[0]] += 0.002            # the session the previous run recorded
        return f

    monkeypatch.setattr(mod, "recompute", restated_last)
    assert mod.main(["--data", "synthetic", "--freeze", "2024-01-02", "--as-of", "2024-02-16", "--out", str(out)]) == 0
    text = (out / "summary.md").read_text(encoding="utf-8")
    assert "Same-day revision" in text and first.index[-1].date().isoformat() in text
    run = json.loads((out / "runs.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert run["same_day_revisions"] == 1
    # an older restatement is a revision but not a same-day one
    assert mod.same_day_revisions(first, [{"date": first.index[3].date().isoformat()}]) == []


# ---------------------------------------------------------------- R4.3 NYSE special days
@pytest.mark.parametrize("d", sorted(NYSE_SPECIAL_CLOSURES))
def test_each_special_closure_is_not_a_session(d):
    assert d in nyse_holidays(d.year)
    assert not SleeveCalendar("equity").is_trading_day(d)


@pytest.mark.parametrize("d", [
    date(2000, 7, 3), date(2001, 7, 3), date(2002, 7, 5), date(2008, 7, 3), date(2013, 7, 3), date(2019, 7, 3),
    date(2024, 7, 3), date(2025, 7, 3), date(2025, 11, 28), date(2026, 11, 27), date(2012, 11, 23),
    date(2001, 12, 24), date(2018, 12, 24), date(2024, 12, 24), date(2025, 12, 24), date(2026, 12, 24),
])
def test_early_closes_at_1300(d):
    assert d in nyse_early_closes(d.year) and nyse_close_time(d).hour == 13


@pytest.mark.parametrize("d", [
    date(2002, 7, 3),    # 4 July on a Thursday before 2013: early close was the 5th
    date(2015, 7, 2),    # 4 July on a Saturday: 3 July is the holiday, 2 July a full day
    date(2021, 7, 2),    # 4 July on a Sunday
    date(2022, 7, 1),    # 4 July on a Monday
    date(2021, 12, 24),  # Friday 24 December is the observed Christmas holiday
    date(2026, 12, 23),
])
def test_full_days_are_not_early_closes(d):
    assert d not in nyse_early_closes(d.year) and nyse_close_time(d).hour == 16


def test_equity_hours_respect_early_close_and_special_closure():
    cal = SleeveCalendar("equity")
    # Black Friday 2026-11-27 (EST, UTC-5): 12:59 open, 14:00 closed
    assert cal.is_open(datetime(2026, 11, 27, 17, 59, tzinfo=UTC))
    assert not cal.is_open(datetime(2026, 11, 27, 19, 0, tzinfo=UTC))
    assert cal.is_open(datetime(2026, 11, 25, 19, 0, tzinfo=UTC))      # a normal day at 14:00
    assert not cal.is_open(datetime(2025, 1, 9, 15, 0, tzinfo=UTC))     # Carter mourning day, 10:00
    assert SleeveCalendar("fx").is_open(datetime(2025, 1, 9, 15, 0, tzinfo=UTC))


# ---------------------------------------------------------------- R4.4 OMS book limits
T = datetime(2026, 11, 6, 20, 55, tzinfo=UTC)   # Friday 15:55 New York


def _oms(**limits):
    c = make_config(data_provider="synthetic", memory_path=None)
    c["oms"] = {"max_order_notional": 1e9, "max_order_quantity": 1e9, "borrow_list": ["MSFT", "AAPL"], **limits}
    return OMS(c, capital=100_000.0)


def test_concentration_limit_refuses_and_names_the_reason():
    oms = _oms(max_name_concentration=0.2)
    ok = oms.submit("a", "AAPL", "buy", 100, price=100.0, last_close=100.0, at=T)        # 10%
    assert ok.reject_reason == ""
    bad = oms.submit("b", "AAPL", "buy", 150, price=100.0, last_close=100.0, at=T)       # 25% with working
    assert bad.reject_reason.startswith("concentration: AAPL")


def test_gross_and_net_limits_count_existing_positions_at_their_marks():
    oms = _oms(max_gross_exposure=1.0, max_net_exposure=0.5, max_name_concentration=None)
    oms.positions = {"MSFT": 300.0}
    oms.marks["MSFT"] = 100.0                                  # 30% long
    r = oms.submit("n", "AAPL", "buy", 300, price=100.0, last_close=100.0, at=T)        # net 60%
    assert r.reject_reason.startswith("net_exposure")
    short = oms.submit("s", "AAPL", "sell", 300, price=100.0, last_close=100.0, at=T)   # net 0, gross 60%
    assert short.reject_reason == ""
    g = oms.submit("g", "SPY", "buy", 500, price=100.0, last_close=100.0, at=T)        # gross 110%
    assert g.reject_reason.startswith("gross_exposure")


def test_an_order_that_reduces_a_breach_is_not_refused():
    oms = _oms(max_name_concentration=0.2)
    oms.positions = {"AAPL": 500.0}
    oms.marks["AAPL"] = 100.0                                  # 50%: already over
    assert oms.submit("r", "AAPL", "sell", 100, price=100.0, last_close=100.0, at=T).reject_reason == ""


def test_order_time_var_limit_uses_the_risk_model():
    oms = _oms(max_var_pct=0.01, max_name_concentration=None)
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2025-01-01", periods=300)
    oms.returns["AAPL"] = pd.Series(rng.normal(0, 0.02, 300), index=idx)   # ~3.3% daily VaR at full weight
    small = oms.submit("v1", "AAPL", "buy", 100, price=100.0, last_close=100.0, at=T)   # 10% -> ~0.33%
    assert small.reject_reason == ""
    big = oms.submit("v2", "AAPL", "buy", 500, price=100.0, last_close=100.0, at=T)     # 60% -> ~2%
    assert big.reject_reason.startswith("var: 1-day 95% VaR")
    none = oms.submit("v3", "SPY", "buy", 10, price=100.0, last_close=100.0, at=T)
    assert none.reject_reason == "var: no return history for SPY"


def test_book_limit_defaults_are_documented_and_permissive_for_small_orders():
    from agentic_trader.oms import OMS_DEFAULTS
    assert OMS_DEFAULTS["max_gross_exposure"] == 3.0 and OMS_DEFAULTS["max_net_exposure"] == 2.0
    assert OMS_DEFAULTS["max_name_concentration"] == 1.0 and OMS_DEFAULTS["max_var_pct"] is None
    oms = _oms()
    assert oms.submit("d", "AAPL", "buy", 100, price=100.0, last_close=100.0, at=T).reject_reason == ""


# ---------------------------------------------------------------- R4.5 push retry
def test_push_retries_a_lost_race_with_backoff():
    ops = _load("paper_ops")
    calls, waits = [], []
    pushes = iter([1, 1, 0])

    def run(cmd):
        calls.append(cmd[1])
        return next(pushes) if cmd[1] == "push" else 0

    assert ops.push_with_retry(5, 2.0, run=run, sleep=waits.append)
    assert calls == ["push", "pull", "push", "pull", "push"] and waits == [2.0, 4.0]


def test_push_gives_up_after_the_attempts_and_aborts_on_a_conflict():
    ops = _load("paper_ops")
    waits = []
    assert not ops.push_with_retry(3, 1.0, run=lambda cmd: 1 if cmd[1] == "push" else 0, sleep=waits.append)
    assert waits == [1.0, 2.0]
    calls = []

    def conflict(cmd):
        calls.append(cmd[1])
        return 1
    assert not ops.push_with_retry(5, 1.0, run=conflict, sleep=lambda s: None)
    assert calls == ["push", "pull", "rebase"]


# ---------------------------------------------------------------- N1 engine freeze
def test_a_changed_engine_is_refused_and_a_refreeze_starts_a_new_vintage(tmp_path):
    mod = _load("paper_trade_v09")
    frozen = tmp_path / "freeze.json"
    spec = json.loads(mod.FREEZE_FILE.read_text(encoding="utf-8"))
    frozen.write_text(json.dumps(spec), encoding="utf-8")
    cfg = make_config(data_provider="synthetic", memory_path=None)
    assert mod.check_freeze(frozen, cfg) == spec["vintage_id"]                    # the repo engine matches
    changed = dict(cfg, risk={**cfg["risk"], "target_vol": 0.20})                # a config edit
    with pytest.raises(SystemExit, match="engine changed since freeze vintage"):
        mod.check_freeze(frozen, changed)
    spec_bad = dict(spec, engine_hash="0" * 64)                                   # a code edit
    frozen.write_text(json.dumps(spec_bad), encoding="utf-8")
    out = tmp_path / "paper"
    with pytest.raises(SystemExit, match="engine changed"):
        mod.main(["--data", "synthetic", "--freeze", "2024-01-02", "--as-of", "2024-02-15", "--out", str(out),
                  "--freeze-file", str(frozen)])
    assert not (out / "ledger.csv").exists()
    with pytest.raises(SystemExit, match="new vintage id"):
        mod.refreeze(frozen, cfg, spec["vintage_id"], "reuse", date(2026, 11, 9))
    with pytest.raises(SystemExit, match="reason"):
        mod.refreeze(frozen, cfg, "v2", " ", date(2026, 11, 9))
    assert mod.main(["--data", "synthetic", "--freeze", "2024-01-02", "--as-of", "2024-02-15", "--out", str(out),
                     "--freeze-file", str(frozen), "--refreeze", "v2", "--reason", "test"]) == 0
    new = json.loads(frozen.read_text(encoding="utf-8"))
    assert new["vintage_id"] == "v2" and new["history"][-1]["engine_hash"] == "0" * 64
    assert mod.check_freeze(frozen, cfg) == "v2"


# ---------------------------------------------------------------- N9 weekends and holidays
@pytest.mark.parametrize("yesterday,session", [
    (date(2026, 11, 8), date(2026, 11, 6)),     # Monday run: Sunday -> Friday
    (date(2026, 11, 26), date(2026, 11, 25)),   # day after Thanksgiving: -> Wednesday
    (date(2025, 1, 9), date(2025, 1, 8)),       # Carter day of mourning
    (date(2026, 11, 5), date(2026, 11, 5)),     # an ordinary session stays
])
def test_as_of_resolves_to_the_last_nyse_session(yesterday, session):
    assert _load("paper_trade_v09").resolve_as_of(yesterday) == session


def test_freshness_does_not_count_weekends_or_holidays(tmp_path):
    ops = _load("paper_ops")
    runs = tmp_path / "runs.jsonl"
    runs.write_text(json.dumps({"as_of": "2026-11-25"}) + "\n", encoding="utf-8")
    # Wed 25th recorded; Thu 26th Thanksgiving, Fri 27th a session, weekend, Mon 30th
    assert ops.business_days_stale(date(2026, 11, 25), date(2026, 11, 30)) == 2
    assert ops.freshness(runs, date(2026, 11, 30))[0]
    assert not ops.freshness(runs, date(2026, 12, 1))[0]
    assert ops.business_days_stale(date(2026, 12, 24), date(2026, 12, 28)) == 1   # Christmas Friday
