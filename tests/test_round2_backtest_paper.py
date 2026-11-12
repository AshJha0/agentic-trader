"""Round 2 (review lane D, quant correctness): the backtest engine and the paper pipeline.

Each test has a worked numeric example that fails on the code before the fix:

* D4  a PM keep is an engine flag, not a weight: at exec_lag 1 it no longer trades back to
      the stale weight held at the decision bar.
* D5  FX P&L in the USD account: USDJPY books 1 - P0/P1 (r / (1 + r)), not r; a cross is
      converted with its quote currency's dollar rate.
* D8  the participation cap sizes a sleeve with the capital it is given.
* D2/D3/D6/D7 and the C7 exec-lag table: see the paper sections below.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agentic_trader import quant
from agentic_trader.quant import pycore

ROOT = Path(__file__).resolve().parents[1]


def _cfg(**kw) -> quant.BacktestConfig:
    base = dict(initial_capital=100_000.0, cost_bps=10.0, slippage_bps=0.0, periods_per_year=252.0,
                max_leverage=1.0, allow_short=True)
    base.update(kw)
    return quant.BacktestConfig(**base)


def _both(prices, weights, cfg, **extras):
    """(numpy result, facade result); the facade is the C++ engine when it is built."""
    return (pycore.run_backtest_ex(prices, weights, cfg, **extras),
            quant.run_backtest(prices, weights, cfg, **extras))


# ------------------------------------------------------------------ D4: keep is a flag
def _keep_path(lag: int, flag: bool):
    """Price +1 %/day; a 0.5 target at bar 0, then PM keeps at bars 5, 10 and 15, built the way
    run_agent_backtest builds them (the held weight replayed from the engine)."""
    n = 21
    prices = 100.0 * 1.01 ** np.arange(n)
    cfg = _cfg(exec_lag=lag)
    w, reb, keep = np.zeros(n), np.zeros(n), np.zeros(n)
    w[0:] = 0.5
    reb[0] = 1.0
    for i in (5, 10, 15):
        ex = dict(rebalance=reb[:i + 1], keep=keep[:i + 1] if flag else None)
        held = float(quant.run_backtest(prices[:i + 1], w[:i + 1], cfg, **ex).positions[i])
        w[i:] = held
        reb[i] = 1.0
        keep[i:] = 1.0
    return prices, w, cfg, reb, keep


def test_d4_keep_at_lag1_is_no_trade():
    prices, w, cfg, reb, keep = _keep_path(lag=1, flag=True)
    for r in _both(prices, w, cfg, rebalance=reb, keep=keep):
        # one trade: the entry at bar 1 (the bar-0 decision executed one bar later)
        assert [(t.index, round(t.to_weight, 6)) for t in r.trades] == [(1, 0.5)]
        # worked number: entry cost 0.5 x 10 bps, then constant units, so
        # E_T = E0 (1 - 0.0005) (1 + 0.5 (1.01^19 - 1))
        expect = 100_000.0 * (1 - 0.0005) * (1 + 0.5 * (1.01 ** 19 - 1))
        assert r.equity[-1] == pytest.approx(expect, rel=1e-12)


def test_d4_old_numeric_keep_traded_back_to_the_stale_weight():
    """The pre-fix behaviour (keep passed only as a number) is still what a caller without the
    flag gets: three phantom trades at bars 6, 11 and 16 (review snippet: 0.51244 -> 0.50995)."""
    prices, w, cfg, reb, _ = _keep_path(lag=1, flag=False)
    r = quant.run_backtest(prices, w, cfg, rebalance=reb)
    phantom = [(t.index, round(t.from_weight, 5), round(t.to_weight, 5)) for t in r.trades[1:]]
    assert [p[0] for p in phantom] == [6, 11, 16]
    assert phantom[0][1:] == (0.51244, 0.50995)


def test_d4_keep_flag_is_bit_identical_at_lag0():
    prices, w, cfg, reb, keep = _keep_path(lag=0, flag=True)
    a = quant.run_backtest(prices, w, cfg, rebalance=reb, keep=keep)
    b = quant.run_backtest(prices, w, cfg, rebalance=reb)
    assert np.array_equal(a.equity, b.equity) and len(a.trades) == len(b.trades) == 1


def test_d4_keep_next_open_holds_the_units():
    prices, w, _, reb, keep = _keep_path(lag=1, flag=True)
    cfg = _cfg(exec_lag=1, fill_next_open=True)
    opens = prices * 0.999
    for r in _both(prices, w, cfg, rebalance=reb, keep=keep, open=opens):
        assert len(r.trades) == 1


# ------------------------------------------------------------------ D5: FX in USD
def test_d5_usd_base_pair_books_r_over_1_plus_r():
    """Long $1 of USDJPY, 100 -> 110: the JPY P&L 10 per dollar is worth 10/110 = 0.0909 USD,
    not 0.10. Short: -0.0909, not -0.10."""
    p = np.array([100.0, 110.0, 110.0])
    for w, want in ((1.0, 1 - 100 / 110), (-1.0, -(1 - 100 / 110))):
        cfg = _cfg(cost_bps=0.0, quote_inverse=True)
        for r in _both(p, np.full(3, w), cfg):
            assert r.returns[1] == pytest.approx(want, abs=1e-15)
        old = quant.run_backtest(p, np.full(3, w), _cfg(cost_bps=0.0))
        assert old.returns[1] == pytest.approx(0.10 * w, abs=1e-15)   # the pre-fix number


def test_d5_usd_base_keeps_a_constant_dollar_notional():
    """A held USDJPY position is a fixed number of dollars: its weight drifts only with equity."""
    p = np.array([100.0, 110.0, 99.0, 104.0])
    for r in _both(p, np.array([1.0, 1.0, 1.0, 1.0]), _cfg(cost_bps=0.0, quote_inverse=True)):
        e = r.equity
        # USD P&L each bar = N (1 - P_t / P_{t+1}) with N = $100,000 throughout
        want = 100_000.0 + np.cumsum([0.0] + [100_000.0 * (1 - p[t] / p[t + 1]) for t in range(3)])
        assert np.allclose(e, want, rtol=1e-12)


def test_d5_cross_converts_with_the_quote_dollar_rate():
    """Long EURJPY 150 -> 153 (+2 %) while USDJPY goes 100 -> 102: the JPY P&L is worth
    0.02 x 100 / 102 = 0.0196078 of the USD notional."""
    p = np.array([150.0, 153.0, 153.0])
    qfx = 1.0 / np.array([100.0, 102.0, 102.0])
    for r in _both(p, np.ones(3), _cfg(cost_bps=0.0), quote_fx=qfx):
        assert r.returns[1] == pytest.approx(0.02 * 100 / 102, abs=1e-15)


def test_d5_monte_carlo_bias_is_gone():
    """Review Monte Carlo: at 10 % vol the uncorrected engine overstates a long USD-base pair by
    about r^2 per day (~1 %/yr). With quote_inverse the mean daily return equals E[1 - P0/P1]."""
    rng = np.random.default_rng(0)
    r = rng.normal(0.0, 0.10 / np.sqrt(252), 252 * 40)
    p = 100.0 * np.exp(np.cumsum(np.r_[0.0, r]))
    res = quant.run_backtest(p, np.ones(p.size), _cfg(cost_bps=0.0, quote_inverse=True, max_leverage=10.0))
    got = res.returns[1:]
    # positions drift (constant dollars), so compare the dollar P&L per bar
    pnl = np.diff(res.equity)
    want = 100_000.0 * (1 - p[:-1] / p[1:])
    assert np.allclose(pnl, want, rtol=1e-9, atol=1e-6)
    assert got.size == r.size


def test_d5_parity_with_stops_next_open_and_lag():
    rng = np.random.default_rng(7)
    n = 60
    p = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    o = p * np.exp(rng.normal(0, 0.003, n))
    h = np.maximum(p, o) * 1.004
    lo = np.minimum(p, o) * 0.996
    w = np.round(rng.uniform(-1, 1, n), 1)
    keep = (rng.uniform(size=n) < 0.3).astype(float)
    stop = np.where(w > 0, p * 0.99, p * 1.01)
    qfx = 1.0 / (100.0 * np.exp(np.cumsum(rng.normal(0, 0.005, n))))
    for inv, q in ((True, None), (False, qfx)):
        for lag in (0, 1, 2):
            for nxt in (False, True):
                cfg = _cfg(exec_lag=lag, fill_next_open=nxt, quote_inverse=inv)
                a, b = _both(p, w, cfg, open=o, high=h, low=lo, stop=stop, keep=keep, quote_fx=q)
                assert np.allclose(a.equity, b.equity, rtol=1e-9)
                assert np.allclose(a.positions, b.positions, rtol=1e-9, atol=1e-12)


def test_d5_inverse_and_series_are_exclusive():
    with pytest.raises(ValueError, match="mutually exclusive"):
        quant.run_backtest([1.0, 2.0], [1.0, 1.0], _cfg(quote_inverse=True), quote_fx=[1.0, 1.0])
    with pytest.raises(ValueError, match="quote_fx"):
        quant.run_backtest([1.0, 2.0], [1.0, 1.0], _cfg(), quote_fx=[1.0, 0.0])


class _FxProvider:
    """Closes for the dollar pairs a cross is converted with."""

    def __init__(self, frames):
        self.frames = frames

    def history(self, ins, start, end):
        return self.frames[ins.symbol]


def test_d5_quote_fx_series_for_crosses():
    from agentic_trader.backtest import quote_fx_series
    from agentic_trader.instruments import Instrument
    idx = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"])
    prov = _FxProvider({
        "GBPUSD": pd.DataFrame({"Close": [1.25, 1.30]}, index=idx[[0, 2]]),   # no bar on the 6th
        "USDJPY": pd.DataFrame({"Close": [100.0, 102.0, 104.0]}, index=idx),
    })
    q = quote_fx_series(Instrument.parse("EURGBP"), prov, idx, date(2026, 1, 1), date(2026, 1, 7))
    assert q.tolist() == [1.25, 1.25, 1.30]                                 # carried forward
    q = quote_fx_series(Instrument.parse("EURJPY"), prov, idx, date(2026, 1, 1), date(2026, 1, 7))
    assert np.allclose(q, [1 / 100, 1 / 102, 1 / 104])
    for s in ("EURUSD", "USDJPY", "AAPL"):
        assert quote_fx_series(Instrument.parse(s), prov, idx, date(2026, 1, 1), date(2026, 1, 7)) is None
    late = _FxProvider({"GBPUSD": pd.DataFrame({"Close": [1.3]}, index=idx[[2]])})
    with pytest.raises(ValueError, match="cannot convert"):
        quote_fx_series(Instrument.parse("EURGBP"), late, idx, date(2026, 1, 1), date(2026, 1, 7))


def test_d5_config_switch():
    from agentic_trader.backtest import backtest_config_for, fx_account_currency
    from agentic_trader.config import make_config
    from agentic_trader.instruments import Instrument

    class P:
        def macro(self, ins, start):
            return {"rate_diff": 0.0}
    cfg = make_config()
    assert fx_account_currency(cfg) is True
    prices = np.array([150.0, 151.0])
    assert backtest_config_for(Instrument.parse("USDJPY"), cfg, prices, P(), date(2026, 1, 2)).quote_inverse
    assert not backtest_config_for(Instrument.parse("EURUSD"), cfg, prices, P(), date(2026, 1, 2)).quote_inverse
    old = make_config(cfg, backtest={**cfg.get("backtest", {}), "fx_account_currency": False})
    assert not backtest_config_for(Instrument.parse("USDJPY"), old, prices, P(), date(2026, 1, 2)).quote_inverse


# ------------------------------------------------------------------ D8: sleeve capital
def test_d8_participation_cap_uses_the_sleeve_capital():
    """ADV 1,000 shares at $100 and a 10 % cap allow $10,000 a bar: 1 % of a $1m account, but
    15 % of a 1/15 sleeve ($66,667). A 0.10 target is reached in one bar for the sleeve; before,
    the sleeve was capped at 0.01 a bar as if it held the whole account."""
    from agentic_trader.backtest import participation_capper
    from agentic_trader.instruments import Instrument
    n = 30
    full = pd.DataFrame({"Close": np.full(n, 100.0), "Volume": np.full(n, 1000.0)},
                        index=pd.bdate_range("2026-01-01", periods=n))
    mask = np.arange(n) >= 20
    cfg = {"costs": {"backtest_participation_cap": 0.10}}
    target = np.full(10, 0.10)
    ins = Instrument.parse("AAPL")
    whole = participation_capper(full, mask, ins, cfg, 1_000_000.0)(target)
    sleeve = participation_capper(full, mask, ins, cfg, 1_000_000.0, np.full(10, 1 / 15))(target)
    assert whole[0] == pytest.approx(0.01)
    assert sleeve[0] == pytest.approx(0.10)


# ------------------------------------------------------------------ paper pipeline
def _load(name: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location(f"r2_{name}", ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _paper_current():
    """paper_trade_v09 with its freeze file re-frozen on the current engine (the committed one
    trips by design until the owner re-freezes, see D3)."""
    import shutil
    import tempfile

    from agentic_trader.config import make_config
    mod = _load("paper_trade_v09")
    copy = Path(tempfile.mkdtemp()) / "paper_freeze.json"
    shutil.copy(mod.FREEZE_FILE, copy)
    mod.refreeze(copy, make_config(data_provider="synthetic", memory_path=None), "r2-tests", "tests", date.today())
    mod.FREEZE_FILE = copy
    return mod


def _lagging(symbol: str, last_ok: str):
    from agentic_trader.data import SyntheticProvider

    class Lagging(SyntheticProvider):
        """Yahoo-style transient lag: one symbol's history stops a session early."""

        def history(self, instrument, start, end):
            h = super().history(instrument, start, end)
            return h[h.index <= pd.Timestamp(last_ok)] if instrument.symbol == symbol else h
    return Lagging


def test_d2_a_lagging_symbol_holds_the_session_back_instead_of_recording_a_zero(tmp_path, monkeypatch):
    """TLT (etf11) is served through 2024-02-14 while every other symbol reaches 2024-02-15.
    Before: 2024-02-15 was appended with TLT's return filled as 0, for good. Now the session is
    held back, the skip and its reason go into runs.jsonl, and the next complete run appends it
    with the real numbers."""
    mod = _paper_current()
    out = tmp_path / "paper"
    args = ["--data", "synthetic", "--freeze", "2024-01-02", "--as-of", "2024-02-15", "--out", str(out)]
    real_provider = mod.get_provider
    monkeypatch.setattr(mod, "get_provider", lambda cfg: _lagging("TLT", "2024-02-14")(cfg))
    assert mod.main(args) == 0
    led = pd.read_csv(out / "ledger.csv", index_col=0, parse_dates=True)
    assert led.index[-1] == pd.Timestamp("2024-02-14")
    run = json.loads((out / "runs.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert run["skipped"] == [{"date": "2024-02-15", "reason": "incomplete session: no bar yet for etf11:TLT"}]
    assert run["last_bar"] == "2024-02-14"
    monkeypatch.setattr(mod, "get_provider", real_provider)
    assert mod.main(args) == 0
    led2 = pd.read_csv(out / "ledger.csv", index_col=0, parse_dates=True)
    assert led2.index[-1] == pd.Timestamp("2024-02-15") and len(led2) == len(led) + 1
    full = pd.read_csv(out / "ledger_recomputed.csv", index_col=0, parse_dates=True)
    assert led2.loc["2024-02-15"].equals(full.loc["2024-02-15"])
    assert json.loads((out / "runs.jsonl").read_text(encoding="utf-8").splitlines()[-1])["skipped"] == []


def test_d3_freeze_covers_the_whole_package_and_the_lock(tmp_path):
    ops = _load("paper_ops")
    pkg = tmp_path / "agentic_trader" / "data"
    pkg.mkdir(parents=True)
    (tmp_path / "agentic_trader" / "backtest.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "agentic_trader" / "regime.py").write_text("y = 1\n", encoding="utf-8")
    (pkg / "yahoo.py").write_text("z = 1\n", encoding="utf-8")
    (tmp_path / "requirements-lock.txt").write_text("numpy==2.0\n", encoding="utf-8")
    narrow = ["agentic_trader/backtest.py"]
    wide = ops.engine_patterns(narrow)
    assert set(ops.REQUIRED_ENGINE_FILES) <= set(wide) and "agentic_trader/backtest.py" in wide

    def fp(patterns):
        return ops.engine_fingerprint(tmp_path, patterns, {}, [], "books")
    before_narrow, before_wide = fp(narrow), fp(wide)
    for path, text in ((tmp_path / "agentic_trader" / "regime.py", "y = 2\n"), (pkg / "yahoo.py", "z = 2\n"),
                       (tmp_path / "requirements-lock.txt", "numpy==2.1\n")):
        path.write_text(text, encoding="utf-8")
        assert fp(narrow) == before_narrow          # the old freeze did not see this edit
        assert fp(wide) != before_wide              # the round-2 freeze does
        before_wide = fp(wide)


def test_d3_refreeze_writes_the_widened_file_list(tmp_path):
    from agentic_trader.config import make_config
    mod = _load("paper_trade_v09")
    frozen = tmp_path / "freeze.json"
    frozen.write_text(mod.FREEZE_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    cfg = make_config(data_provider="synthetic", memory_path=None)
    spec = mod.refreeze(frozen, cfg, "r2-check", "test", date(2026, 11, 12))
    assert "agentic_trader/**/*.py" in spec["engine_files"] and "requirements-lock.txt" in spec["engine_files"]
    assert mod.check_freeze(frozen, cfg) == "r2-check"


def test_d6_ledger_hash_chain_and_append_only_check():
    ops, chk = _load("paper_ops"), _load("paper_ledger_check")
    old = "date,a,rf\n2026-11-10,0.01,0.04\n2026-11-11,-0.02,0.04\n"
    new = old + "2026-11-12,0.003,0.04\n"
    heads = ops.ledger_chain(new)
    # worked chain: h0 = sha256(seed + header), h_k = sha256(h_{k-1} + "\n" + row_k)
    h0 = hashlib.sha256(ops.CHAIN_SEED + b"date,a,rf").hexdigest()
    h1 = hashlib.sha256(h0.encode() + b"\n2026-11-10,0.01,0.04").hexdigest()
    assert heads[:2] == [h0, h1] and len(heads) == 4
    assert ops.ledger_chain(old.replace("\n", "\r\n")) == heads[:3]          # CRLF checkout hashes alike
    runs_old = json.dumps({"as_of": "2026-11-11", "ledger_rows": 2, "ledger_chain": heads[2]}) + "\n"
    runs_new = runs_old + json.dumps({"as_of": "2026-11-12", "ledger_rows": 3, "ledger_chain": heads[3]}) + "\n"
    good = {"ledger.csv": new, "runs.jsonl": runs_new}
    base = {"ledger.csv": old, "runs.jsonl": runs_old}
    assert chk.run_checks(base, good) == []
    assert chk.run_checks(base, base) == []                                   # nothing appended: fine
    rewritten = new.replace("-0.02", "-0.03")                                 # a recorded row rewritten
    errs = chk.run_checks(base, {"ledger.csv": rewritten, "runs.jsonl": runs_new})
    assert any("line 3 differs" in e for e in errs) and any("chain head" in e for e in errs)
    errs = chk.run_checks({"ledger.csv": new}, {"ledger.csv": old})            # a stale artifact
    assert errs == ["ledger.csv: 4 committed line(s), only 3 now (the record shrank)"]
    assert chk.run_checks({"revisions.csv": "x\n"}, {}) == ["revisions.csv: committed file is missing from the publish"]


def test_d6_mask_touches_only_the_newest_runs_line(tmp_path):
    mask = _load("paper_mask_paths")
    old = '{"provenance": {"executable": "C:/old/python.exe"}}'      # published earlier, left verbatim
    new = '{"provenance": {"executable": "/opt/hostedtoolcache/python"}}'
    p = tmp_path / "runs.jsonl"
    p.write_text(old + "\n" + new + "\n", encoding="utf-8")
    assert mask.main([str(p)]) == 0
    lines = p.read_text(encoding="utf-8").splitlines()
    assert lines == [old, '{"provenance": {"executable": "<local python>"}}']


def test_d6_paper_run_records_the_chain_head(tmp_path):
    mod, ops, chk = _paper_current(), _load("paper_ops"), _load("paper_ledger_check")
    out = tmp_path / "paper"
    assert mod.main(["--data", "synthetic", "--freeze", "2024-01-02", "--as-of", "2024-02-15", "--out", str(out)]) == 0
    first = {n: (out / n).read_text(encoding="utf-8") for n in chk.APPEND_ONLY if (out / n).exists()}
    assert mod.main(["--data", "synthetic", "--freeze", "2024-01-02", "--as-of", "2024-02-16", "--out", str(out)]) == 0
    second = {n: (out / n).read_text(encoding="utf-8") for n in chk.APPEND_ONLY if (out / n).exists()}
    runs = [json.loads(x) for x in second["runs.jsonl"].splitlines()]
    heads = ops.ledger_chain(second["ledger.csv"])
    assert runs[-1]["ledger_rows"] == len(heads) - 1 and runs[-1]["ledger_chain"] == heads[-1]
    assert runs[0]["ledger_chain"] == heads[runs[0]["ledger_rows"]]
    assert chk.run_checks(first, second) == []


def test_d7_freshness_reads_the_ledger_not_the_requested_as_of(tmp_path):
    """Yahoo stalls: the ledger ends 2026-11-04, but each run still writes an as_of of
    yesterday with appended 0. The old check read the as_of and stayed green."""
    ops = _load("paper_ops")
    runs, ledger = tmp_path / "runs.jsonl", tmp_path / "ledger.csv"
    runs.write_text(json.dumps({"as_of": "2026-11-09", "appended": 0}) + "\n", encoding="utf-8")
    ledger.write_text("date,a,rf\n2026-11-03,0.0,0.04\n2026-11-04,0.01,0.04\n", encoding="utf-8")
    assert ops.freshness(runs, date(2026, 11, 10))[0]                         # the old reading: ok
    ok, msg = ops.freshness(runs, date(2026, 11, 10), ledger=ledger)
    assert not ok and msg.startswith("STALE") and "2026-11-04" in msg and "4 business day" in msg
    assert ops.main(["freshness", "--runs", str(runs), "--today", "2026-11-10"]) == 1   # ledger beside runs
    assert ops.last_ledger_session(ledger) == date(2026, 11, 4)


def test_f6_raw_bars_are_not_uploaded():
    wf = (ROOT / ".github" / "workflows" / "paper.yml").read_text(encoding="utf-8")
    assert "name: paper-bars" not in wf and "PAPER_BARS_ARTIFACT" not in wf
    assert "!results/paper/bars/" in wf                       # and excluded from the record artifact
    assert "paper_ledger_check.py --base HEAD" in wf
    lic = (ROOT / "DATA_LICENSING.md").read_text(encoding="utf-8")
    assert "private `paper-bars` Actions artifact" not in lic and "removed in round 2" in lic


def test_d12_laptop_task_pulls_before_the_session():
    cmd = (ROOT / "scripts" / "paper_daily.cmd").read_text(encoding="utf-8").splitlines()
    pull = next(i for i, ln in enumerate(cmd) if ln.startswith("git pull"))
    run = next(i for i, ln in enumerate(cmd) if "paper_trade_v09.py" in ln and not ln.startswith("rem"))
    assert pull < run


# ------------------------------------------------------------------ C7/D1: the timing table
def test_c7_exec_lag_variants_and_table():
    ex = _load("v17_exec_lag")
    assert ex.parse_variants("0,1,next_open") == [0, 1, "next_open"]
    assert ex.variant_timing("next_open") == (0, "next_open") and ex.variant_timing(1) == (1, "close")
    for bad in ("0,0", "x", "-1", ""):
        with pytest.raises(ValueError):
            ex.parse_variants(bad)
    cfg = ex.trial_config("synthetic", {}, "next_open")
    assert cfg["backtest"]["exec_lag"] == 0 and cfg["backtest"]["fill"] == "next_open"
    assert ex.trial_config("synthetic", {}, 1)["backtest"] == {**cfg["backtest"], "exec_lag": 1, "fill": "close"}

    class T:
        name = "rules v0.8"
    rows = [{"trial": "rules v0.8", "exec_lag": v, "sharpe": s, "delta_vs_control": d, "p_value": p}
            for v, s, d, p in ((0, 0.81, 0.10, 0.04), (1, 0.62, -0.05, 0.40), ("next_open", 0.66, -0.02, 0.70))]
    lines = ex.table_lines(rows, "yahoo", "design", [0, 1, "next_open"], [T()])
    assert lines[-1] == "| rules v0.8 | 0.810 | +0.100 | 0.040 | 0.620 | -0.050 | 0.400 | 0.660 | -0.020 | 0.700 |"
    assert "SR next open" in lines[4] and "same-close fill" in lines[2]


def test_c7_defaults_are_unchanged_for_published_studies():
    from agentic_trader.backtest import backtest_config_for
    from agentic_trader.config import make_config
    from agentic_trader.instruments import Instrument

    class P:
        def macro(self, ins, start):
            return {}
    bt = backtest_config_for(Instrument.parse("AAPL"), make_config(), np.array([1.0, 2.0]), P(), date(2026, 1, 2))
    assert bt.exec_lag == 0 and bt.fill_next_open is False
