"""End-to-end workflows: guards, watchlist scans, portfolios, evaluation, memory
robustness and the CLI (all offline, synthetic data)."""
import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from agentic_trader import TradingGraph, make_config, run_agent_backtest
from agentic_trader.backtest import AGENT, run_portfolio_backtest
from agentic_trader.cli import main
from agentic_trader.data import SyntheticProvider
from agentic_trader.evaluation import EvaluationResult, evaluate
from agentic_trader.memory import DecisionMemory

CFG = make_config(memory_path=None)
QUIET = dict(memory=DecisionMemory(None), on_event=lambda *_: None)


# ------------------------------------------------------------------ guards
class EndsEarly(SyntheticProvider):
    """Data that stops on 2024-01-31 (delisting, outage, stale feed)."""

    def history(self, instrument, start, end):
        return super().history(instrument, start, min(end, date(2024, 1, 31)))


def test_stale_data_is_refused():
    g = TradingGraph(CFG, provider=EndsEarly(CFG), **QUIET)
    g.propagate("AAPL", "2024-02-05")                       # 5 days: a long weekend is fine
    with pytest.raises(ValueError, match="stale"):
        g.propagate("AAPL", "2024-03-01")


def test_weekend_as_of_uses_friday_close():
    st, d = TradingGraph(CFG, **QUIET).propagate("AAPL", "2024-03-03")    # Sunday
    assert st.history.index[-1].date() == date(2024, 3, 1) and d.as_of == date(2024, 3, 3)


def test_too_little_history():
    with pytest.raises(ValueError, match="not enough history"):
        TradingGraph(CFG, **QUIET).propagate("AAPL", "2015-01-20")    # synthetic data starts 2015


def test_backtest_argument_errors():
    with pytest.raises(ValueError, match="before start"):
        run_agent_backtest("AAPL", "2024-03-01", "2024-01-01", CFG)
    with pytest.raises(ValueError, match="fewer than 2 bars"):
        run_agent_backtest("AAPL", "2024-03-02", "2024-03-03", CFG)   # a weekend


# -------------------------------------------------------------------- scan
def test_scan_continues_past_bad_symbols():
    df = TradingGraph(CFG, **QUIET).scan(["AAPL", "EURUSD", "EUR/XYZ"], "2024-03-01",
                                         positions={"aapl": 0.5})
    assert list(df.symbol) == ["AAPL", "EURUSD", "EUR/XYZ"]
    ok = df[df.action != "ERROR"]
    assert len(ok) == 2 and (ok.error == "").all()
    assert df.iloc[2].action == "ERROR" and df.iloc[2].error


# --------------------------------------------------------------- backtests
def test_stops_fire_in_walk_forward():
    cfg = make_config(CFG, backtest={"use_stops": True}, risk={"stop_atr_mult": 0.5})
    rep = run_agent_backtest("NVDA", "2023-01-02", "2023-12-29", cfg, rebalance_every=10)
    assert rep.results[AGENT].stop_exits > 0
    assert rep.table().loc[AGENT, "Stops"] == rep.results[AGENT].stop_exits


def test_fx_backtest_uses_carry_series_everywhere():
    rep = run_agent_backtest("USDJPY", "2024-01-02", "2024-02-29", CFG, rebalance_every=10)
    assert rep.carry is not None and len(rep.carry) == len(rep.dates)
    assert np.allclose(rep.carry, (CFG["fx_policy_rates"]["USD"] - CFG["fx_policy_rates"]["JPY"]) / 100)


def test_vol_target_baseline_never_exceeds_max_position():
    rep = run_agent_backtest("NVDA", "2024-01-02", "2024-03-28", CFG, include_agent=False)
    pos = rep.results["B&H vol-target"].positions
    assert pos.max() <= CFG["risk"]["max_position"] and pos.min() >= 0


def test_portfolio_combines_sleeves_with_equal_capital():
    rep = run_portfolio_backtest(["AAPL", "EURUSD"], "2024-01-02", "2024-03-28", CFG, rebalance_every=10)
    assert set(rep.sleeves) == {"AAPL", "EURUSD"} and AGENT in rep.table().index
    # Portfolio return = mean of sleeve returns (0 on a sleeve's non-trading day).
    d = rep.dates[10]
    sleeve = [pd.Series(r.results[AGENT].returns, index=r.dates).get(d, 0.0) for r in rep.sleeves.values()]
    assert rep.returns.loc[d, AGENT] == pytest.approx(np.mean(sleeve))
    with pytest.raises(ValueError):
        run_portfolio_backtest([], "2024-01-02", "2024-03-28", CFG)


def test_evaluation_harness_records_errors_and_round_trips(tmp_path):
    res = evaluate(["AAPL", "EUR/XYZ"], {"q1": ("2024-01-02", "2024-03-28")}, CFG, rebalance_every=10)
    assert set(res.rows.symbol) == {"AAPL"} and len(res.meta["errors"]) == 1
    assert {AGENT, "Buy&Hold", "B&H vol-target"} <= set(res.rows.strategy)
    h2h = res.head_to_head()
    assert (h2h["instruments"] == 1).all()
    res.to_json(tmp_path / "e.json")
    back = EvaluationResult.from_json(tmp_path / "e.json")
    pd.testing.assert_frame_equal(back.rows, res.rows)


# ------------------------------------------------------------------ memory
def test_memory_survives_corrupt_lines_and_writes_atomically(tmp_path):
    path = tmp_path / "m.jsonl"
    m = DecisionMemory(path)
    m.record("X", date(2024, 1, 1), "BUY", 0.5, 100.0, "ok")
    with open(path, "a", encoding="utf-8") as f:
        f.write('{"symbol": "X", "as_of": \n')           # torn write
        f.write('{"unexpected": 1}\n')                   # wrong schema
    m2 = DecisionMemory(path)
    assert len(m2.entries) == 1 and m2.skipped_lines == 2
    m2.record("X", date(2024, 1, 2), "HOLD", 0.0, 101.0, "ok")
    assert not (tmp_path / "m.jsonl.tmp").exists() and len(DecisionMemory(path).entries) == 2


# --------------------------------------------------------------------- CLI
def test_cli_analyze_json(capsys):
    assert main(["analyze", "AAPL", "--date", "2024-03-01", "--json", "--no-memory"]) == 0
    out = capsys.readouterr().out
    d = json.loads(out[out.index("{"):])
    assert d["symbol"] == "AAPL" and d["action"] in {"BUY", "SELL", "HOLD"}


def test_cli_scan_writes_file(tmp_path, capsys):
    out = tmp_path / "d.json"
    assert main(["scan", "AAPL,EURUSD", "--date", "2024-03-01", "--out", str(out)]) == 0
    assert [r["symbol"] for r in json.loads(out.read_text())] == ["AAPL", "EURUSD"]


def test_cli_errors_exit_2_without_traceback(capsys):
    assert main(["analyze", "AAPL", "--date", "2015-01-20", "--no-memory"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error:") and "Traceback" not in err
    assert main(["backtest", "AAPL", "--start", "2024-03-01", "--end", "2024-01-01"]) == 2
    assert main(["analyze", "AAPL", "--rounds", "0"]) == 2


def test_cli_backtest_portfolio_evaluate_info(tmp_path, capsys):
    assert main(["backtest", "EURUSD", "--start", "2024-01-02", "--end", "2024-02-29",
                 "--every", "10", "--stops", "on", "--band", "0.2"]) == 0
    assert "stops on" in capsys.readouterr().out
    assert main(["portfolio", "AAPL,EURUSD", "--start", "2024-01-02", "--end", "2024-02-29",
                 "--every", "10", "--out", str(tmp_path / "p.csv")]) == 0
    assert (tmp_path / "p.csv").exists()
    assert main(["evaluate", "AAPL", "--periods", "paper", "--every", "10"]) == 0
    assert main(["info"]) == 0
    assert '"neutral_weight"' in capsys.readouterr().out


def test_cli_v02_rules_flag(capsys):
    main(["analyze", "AAPL", "--date", "2024-03-01", "--json", "--no-memory", "--rules", "v02"])
    out = capsys.readouterr().out
    assert json.loads(out[out.index("{"):])["target_weight"] == 0.5354
