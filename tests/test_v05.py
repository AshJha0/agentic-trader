"""v0.5 features: cross-sectional alphas, ALFRED vintages, cross-asset risk budgets,
the dollar LLM budget, the persistent task store, TLS / deployment guards for the
API, and the widened evaluation universe. All offline."""
import json
import logging
from datetime import date

import numpy as np
import pandas as pd
import pytest

from agentic_trader import Instrument, TradingGraph, make_config
from agentic_trader.agentic import AgentHarness, QueuedApprovalGateway, Role, Task
from agentic_trader.agentic.store import TaskStore, record_of
from agentic_trader.backtest import AGENT, run_portfolio_backtest
from agentic_trader.cli import main
from agentic_trader.data import SyntheticProvider
from agentic_trader.data import fred as fred_mod
from agentic_trader.data.fred import CPI_SERIES, FredClient, FredSeries, default_client
from agentic_trader.evaluation import (CORE_UNIVERSE, EXTENDED_UNIVERSE, PERIODS, UNIVERSES, evaluate,
                                       universe_group)
from agentic_trader.llm import BudgetedLLM, UsageTracker, budget_llm
from agentic_trader.memory import DecisionMemory
from agentic_trader.portfolio import construct
from agentic_trader.xalpha import (cross_sectional_ic, cs_rank, cs_zscore, forward_return_panel, ic_summary,
                                   quantile_spread, signal_panels, xalpha_report, xalpha_snapshot)

CFG = make_config(memory_path=None)
QUIET = dict(memory=DecisionMemory(None), on_event=lambda *_: None)


# ------------------------------------------------------- cross-sectional alphas
@pytest.fixture(scope="module")
def universe():
    p = SyntheticProvider(CFG)
    frames, instruments, carry = {}, {}, {}
    for s in ("AAPL", "MSFT", "NVDA", "JPM", "XOM", "JNJ", "EURUSD", "USDJPY", "GBPUSD"):
        ins = Instrument.parse(s)
        df = p.history(ins, date(2021, 1, 1), date(2024, 3, 28))
        frames[s], instruments[s] = df, ins
        if ins.is_fx:
            carry[s] = p.carry_series(ins, df.index)
    return frames, instruments, carry


def test_cs_zscore_and_rank_properties():
    idx = pd.bdate_range("2024-01-01", periods=4)
    panel = pd.DataFrame({"a": [1, 2, 3, np.nan], "b": [2, 2, 5, 1.0], "c": [3, 2, 7, 2.0], "d": [4, 2, 9, np.nan]},
                         index=idx)
    z = cs_zscore(panel, min_names=3)
    assert np.allclose(np.nanmean(z.iloc[0]), 0.0) and np.nanmax(z.abs().to_numpy()) <= 1.0 + 1e-12
    assert z.iloc[1].isna().all()                        # a constant row has no dispersion
    assert z.iloc[3].isna().all()                        # only two names: below min_names
    r = cs_rank(panel, min_names=3)
    assert r.iloc[0].tolist() == pytest.approx([-1.0, -1 / 3, 1 / 3, 1.0])
    groups = {"a": "g1", "b": "g1", "c": "g2", "d": "g2"}
    zg = cs_zscore(panel, groups, min_names=2)
    assert np.allclose(zg.iloc[0][["a", "b"]].sum(), 0.0) and np.allclose(zg.iloc[0][["c", "d"]].sum(), 0.0)


def test_cross_sectional_ic_recovers_a_perfect_signal():
    rng = np.random.default_rng(3)
    idx = pd.bdate_range("2023-01-02", periods=80)
    closes = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.01, (80, 8)), axis=0)), index=idx,
                          columns=list("ABCDEFGH"))
    fwd = forward_return_panel(closes, 5)
    perfect = fwd.rank(axis=1)                            # the signal *is* the forward-return ranking
    ic = cross_sectional_ic(perfect, fwd, min_names=5)
    assert ic.dropna().size == 75 and np.allclose(ic.dropna(), 1.0)
    s = ic_summary(ic, 5)
    assert s["mean IC"] == pytest.approx(1.0) and s["IC>0%"] == 100.0 and s["days"] == 75
    spread = quantile_spread(perfect, fwd, 5, quantile=0.25, min_names=5)
    assert spread.size == 15 and (spread > 0).all()
    anti = cross_sectional_ic(-perfect, fwd, min_names=5)
    assert np.allclose(anti.dropna(), -1.0)
    with pytest.raises(ValueError):
        forward_return_panel(closes, 0)
    with pytest.raises(ValueError):
        quantile_spread(perfect, fwd, 5, quantile=0.7)


def test_xalpha_report_and_snapshot(universe):
    frames, instruments, carry = universe
    rep = xalpha_report(frames, instruments, 10, carry=carry)
    assert "combined" in rep.table.index and {"mean IC", "IC IR", "t(IC)", "IC>0%", "breadth"} <= set(rep.table.columns)
    assert set(rep.decay.columns) == {1, 5, 10, 21, 42}
    assert rep.groups["AAPL"] == "equity" and rep.groups["EURUSD"] == "fx"
    # Equity and FX are standardised separately: an equity score never depends on an FX name.
    comb = rep.signals["combined"]
    eq_cols = [s for s in frames if not instruments[s].is_fx]
    assert np.nanmax(comb[eq_cols].abs().to_numpy()) <= 1.0 + 1e-9
    # FX days exist where no equity name has a score (different calendars): the FX
    # block is scored on its own, so the equity columns are NaN there, never 0-filled.
    assert comb[eq_cols].isna().any(axis=1).any()
    assert set(rep.best(2)) <= set(rep.table.index) - {"combined"}
    assert rep.correlations.shape[0] == rep.correlations.shape[1] == len(rep.signals) - 1
    snap = xalpha_snapshot(frames, instruments, carry=carry)
    assert set(snap) == set(frames) and "combined" in snap["AAPL"]
    ranked = xalpha_report(frames, instruments, 10, carry=carry, standardise="rank")
    assert np.nanmax(ranked.signals["combined"].abs().to_numpy()) <= 1.0 + 1e-9
    with pytest.raises(ValueError):
        xalpha_report(frames, instruments, 10, standardise="bogus")
    with pytest.raises(ValueError):
        signal_panels({}, {})


def test_xalpha_tool_and_cli(universe, tmp_path, capsys):
    from agentic_trader.agentic.servers import DeskTools
    tools = DeskTools(SyntheticProvider(CFG), CFG)
    out = tools.xalpha(["AAPL", "MSFT", "NVDA", "JPM"], date(2024, 3, 1), horizon=10, lookback_days=900)
    assert set(out["latest"]) == {"AAPL", "MSFT", "NVDA", "JPM"} and "combined" in out["ic"]
    json.dumps(out)  # JSON-safe payload
    with pytest.raises(ValueError):
        tools.xalpha(["AAPL", "MSFT"], date(2024, 3, 1))
    assert main(["xalpha", "AAPL,MSFT,NVDA,JPM,XOM", "--start", "2021-01-04", "--end", "2024-03-28",
                 "--out", str(tmp_path / "x.csv")]) == 0
    assert "mean IC" in capsys.readouterr().out and (tmp_path / "x.csv").exists()
    assert main(["xalpha", "AAPL,MSFT", "--start", "2021-01-04", "--end", "2024-03-28"]) == 2


# ---------------------------------------------------------------- ALFRED vintages
def _fake_fetch(url: str) -> pd.DataFrame:
    """CPI level series: the 2019-11 print was first published as 100 and later revised to 101."""
    obs = pd.to_datetime(["2018-11-01", "2019-11-01", "2019-12-01"])
    if "vintage_date=" in url:
        vd = url.split("vintage_date=")[1]
        if vd < "2020-02-01":                              # the first vintage knows only the first print
            return pd.DataFrame({"CPIAUCSL": [95.0, 100.0]}, index=obs[:2])
        return pd.DataFrame({"CPIAUCSL": [95.0, 101.0, 102.0]}, index=obs)
    return pd.DataFrame({"CPIAUCSL": [95.0, 101.0, 102.0]}, index=obs)  # the latest vintage


def test_fred_vintages_read_first_published_values(tmp_path):
    spec = FredSeries("CPIAUCSL", 45, 120, revised=True)   # no yoy transform, so values are levels
    latest = FredClient(fetch=_fake_fetch)
    vint = FredClient(vintages=True, fetch=_fake_fetch, cache_dir=tmp_path)
    when = date(2020, 1, 10)                               # 2019-11 print visible (lag 45d), 2019-12 not yet
    assert latest.value_asof(spec, when) == 101.0          # FRED: the later revision leaks into the past
    assert vint.value_asof(spec, when) == 100.0            # ALFRED: as first published
    assert vint.vintage_date(when) <= when and (when - vint.vintage_date(when)).days < 31
    # 2020-01-20: the 2019-12 print is public, but the sampled (older) vintage does not have it
    # yet -- the conservative side of monthly vintage sampling.
    assert latest.value_asof(spec, date(2020, 1, 20)) == 102.0 and vint.value_asof(spec, date(2020, 1, 20)) == 100.0
    # Once the revised vintage is current both agree.
    assert vint.value_asof(spec, date(2020, 3, 20)) == 102.0 == latest.value_asof(spec, date(2020, 3, 20))
    # Vectorised path groups dates by vintage and matches the point lookups.
    dates = pd.bdate_range("2020-01-06", "2020-03-27")
    vec = vint.series_asof(spec, dates)
    for d in dates[::7]:
        v = vint.value_asof(spec, d.date())
        assert (np.isnan(vec[d]) and v is None) or vec[d] == v
    # Unrevised series ignore vintages entirely; the disk cache holds the vintage files.
    rate = FredSeries("DFF", 1, 10)
    assert vint._series_for(rate, when) is vint._load(rate)
    assert any(f.name.startswith("CPIAUCSL_v") for f in tmp_path.iterdir())
    with pytest.raises(ValueError):
        FredClient(vintage_step_days=0)


def test_default_client_per_setting(monkeypatch):
    monkeypatch.setattr(fred_mod, "_default", None)
    monkeypatch.setattr(fred_mod, "_defaults", {})
    a = default_client(make_config())
    b = default_client(make_config(fred_vintages=True))
    assert a is not b and b.vintages and not a.vintages
    assert default_client(make_config(fred_vintages=True)) is b
    assert all(s.revised for s in CPI_SERIES.values())


def test_fred_vintage_cli_flag(capsys):
    assert main(["analyze", "EURUSD", "--date", "2024-03-01", "--fred-vintages", "--json"]) == 0
    assert '"symbol": "EURUSD"' in capsys.readouterr().out   # synthetic data: flag accepted, static macro used


# --------------------------------------------------------- cross-asset risk budgets
def test_group_risk_budgets_hit_their_targets():
    rng = np.random.default_rng(11)
    n = 600
    eq = rng.normal(0, 0.02, (n, 3)) + rng.normal(0, 0.01, (n, 1))     # correlated equity block
    fx = rng.normal(0, 0.006, (n, 2)) + rng.normal(0, 0.003, (n, 1))   # calmer, correlated FX block
    rets = pd.DataFrame(np.hstack([eq, fx]), columns=["A", "B", "C", "EURUSD", "USDJPY"])
    groups = {"A": "equity", "B": "equity", "C": "equity", "EURUSD": "fx", "USDJPY": "fx"}
    targets = {s: 1.0 for s in rets.columns}
    pw = construct(targets, rets, "risk_parity", groups=groups, group_budgets={"equity": 0.6, "fx": 0.4},
                   max_weight=1.0, target_vol=None, halflife=None, shrink=False)
    assert pw.group_risk is not None and list(pw.group_risk.index) == ["equity", "fx"]
    assert pw.group_risk["risk_share"].tolist() == pytest.approx([0.6, 0.4], abs=0.02)
    assert pw.allocation.sum() == pytest.approx(1.0) and (pw.allocation >= 0).all()
    # Without budgets the calmer FX sleeves get most of the capital under plain risk parity.
    plain = construct(targets, rets, "risk_parity", max_weight=1.0, target_vol=None, halflife=None, shrink=False)
    assert plain.group_risk is None and plain.allocation[3:].sum() > pw.allocation[3:].sum()
    assert "group_risk" in pw.to_dict()
    # A group with no active sleeve drops out and the rest are renormalised.
    off = construct({**targets, "EURUSD": 0.0, "USDJPY": 0.0}, rets, "risk_parity", groups=groups,
                    group_budgets={"equity": 0.6, "fx": 0.4}, max_weight=1.0, target_vol=None)
    assert list(off.group_risk.index) == ["equity"] and off.allocation[3:].sum() == 0.0
    for bad in ({"equity": 0.6}, {"equity": -1, "fx": 2}):
        with pytest.raises(ValueError):
            construct(targets, rets, "risk_parity", groups=groups, group_budgets=bad)
    with pytest.raises(ValueError):
        construct(targets, rets, "risk_parity", group_budgets={"equity": 1.0})


def test_portfolio_backtest_with_class_budgets(capsys):
    syms = ["AAPL", "JPM", "EURUSD"]
    eq = run_portfolio_backtest(syms, "2024-01-02", "2024-03-28", CFG, 10, class_budgets={"equity": 0.5, "fx": 0.5})
    assert eq.allocations is not None
    assert eq.allocations.iloc[0].tolist() == pytest.approx([0.25, 0.25, 0.5])
    rp = run_portfolio_backtest(syms, "2024-01-02", "2024-03-28", CFG, 10, weighting="risk_parity",
                                class_budgets={"equity": 0.7, "fx": 0.3})
    assert np.allclose(rp.allocations.sum(axis=1), 1.0, atol=1e-9)
    with pytest.raises(ValueError):
        run_portfolio_backtest(syms, "2024-01-02", "2024-03-28", CFG, 10, class_budgets={"equity": 1.0})
    with pytest.raises(ValueError):
        run_portfolio_backtest(syms, "2024-01-02", "2024-03-28", CFG, 10, class_budgets={"equity": 0, "fx": 0})
    assert main(["portfolio", "AAPL,EURUSD", "--start", "2024-01-02", "--end", "2024-02-29", "--every", "10",
                 "--class-budgets", "equity=0.6,fx=0.4"]) == 0
    assert "class budgets" in capsys.readouterr().out
    assert main(["portfolio", "AAPL,EURUSD", "--start", "2024-01-02", "--end", "2024-02-29",
                 "--class-budgets", "equity:0.6"]) == 2


# ------------------------------------------------------------- dollar LLM budget
class Priced:
    """A model whose every call costs 0.40 USD on the tracker."""

    def __init__(self):
        self.usage = UsageTracker()
        self.calls = 0

    def complete(self, system, prompt, *, deep):
        self.calls += 1
        self.usage.by_model.setdefault("claude-opus-5", type("U", (), {})())
        u = self.usage.by_model["claude-opus-5"]
        from agentic_trader.llm import ModelUsage
        if not isinstance(u, ModelUsage):
            self.usage.by_model["claude-opus-5"] = u = ModelUsage()
        u.calls += 1
        u.output_tokens += 16_000   # 16k output tokens at Opus list price ~ 0.40 USD
        return '{"signal": 0.5, "confidence": 0.5, "summary": "ok"}'


def test_dollar_budget_caps_spend():
    inner = Priced()
    b = BudgetedLLM(inner, max_cost_usd=1.0)
    replies = [b.complete("s", "p", deep=True) for _ in range(6)]
    assert inner.calls == 3 and replies[3:] == [None, None, None] and b.refused == 3
    assert b.exhausted and b.spent_usd == pytest.approx(inner.usage.cost_usd) and b.spent_usd >= 1.0
    both = BudgetedLLM(Priced(), max_calls=2, max_cost_usd=100.0)
    assert [both.complete("s", "p", deep=False) is None for _ in range(3)] == [False, False, True]
    with pytest.raises(ValueError):
        BudgetedLLM(Priced())
    with pytest.raises(ValueError):
        BudgetedLLM(Priced(), max_cost_usd=-1)
    wrapped = budget_llm(Priced(), make_config(max_llm_cost_usd=0.5))
    assert isinstance(wrapped, BudgetedLLM) and wrapped.max_calls is None and wrapped.max_cost_usd == 0.5
    assert budget_llm(wrapped, make_config(max_llm_calls=3)) is wrapped
    g = TradingGraph(make_config(CFG, max_llm_cost_usd=0.0), llm=Priced(), **QUIET)
    st, dec = g.propagate("AAPL", "2024-03-01")
    assert isinstance(g.llm, BudgetedLLM) and g.llm.inner.calls == 0 and dec.source == "rules"


def test_dollar_budget_cli_flag(capsys):
    assert main(["analyze", "AAPL", "--date", "2024-03-01", "--max-llm-cost", "2.5", "--json"]) == 0
    assert main(["analyze", "AAPL", "--date", "2024-03-01", "--max-llm-cost", "-1"]) == 2


# ----------------------------------------------------------- persistent task store
def test_task_store_persists_and_archives(tmp_path):
    db = tmp_path / "tasks.sqlite"
    h1 = AgentHarness(TradingGraph(CFG, **QUIET), store=TaskStore(db))
    run = h1.run(Task("AAPL", date(2024, 3, 1), Role.TRADER, 0.1))
    assert run.state.value == "COMPLETED" and len(h1.store) == 1
    rec = h1.store.load(run.id)
    assert rec["state"] == "COMPLETED" and rec["decision"]["symbol"] == "AAPL" and rec["report"]
    assert len(rec["evidence_rows"]) == rec["evidence_count"] and rec["spans"]
    assert h1.record(run.id)["task_id"] == run.id
    h1.store.close()

    # A record left mid-flight by a "crashed" process is failed on reload, never resumed.
    store = TaskStore(db)
    stuck = dict(record_of(run), task_id="TASK-stuck", state="EXECUTING", finished_at=None)
    store.save_record(stuck)
    h2 = AgentHarness(TradingGraph(CFG, **QUIET), store=store)
    assert set(h2.archive) == {run.id, "TASK-stuck"} and not h2.runs
    assert h2.archive["TASK-stuck"]["state"] == "FAILED" and "process restarted" in h2.archive["TASK-stuck"]["errors"]
    assert h2.record(run.id)["decision"]["target_weight"] == rec["decision"]["target_weight"]
    assert h2.record("TASK-nope") is None
    # New runs in the new process are persisted next to the archive.
    r2 = h2.run(Task("EURUSD", date(2024, 3, 1), Role.TRADER))
    assert len(store) == 3 and store.summaries()[-1]["symbol"] == "EURUSD"
    assert store.delete("TASK-stuck") and not store.delete("TASK-stuck")
    store.close()

    # Config wiring: agentic.task_db builds the store.
    h3 = AgentHarness(TradingGraph(make_config(CFG, agentic={"task_db": str(db)}), **QUIET))
    assert h3.store is not None and r2.id in h3.archive
    h3.store.close()


def test_api_serves_archived_tasks(tmp_path):
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from agentic_trader.agentic.api import create_app
    db = tmp_path / "api.sqlite"
    first = AgentHarness(TradingGraph(CFG, **QUIET), gateway=QueuedApprovalGateway(), store=TaskStore(db))
    run = first.run(Task("AAPL", date(2024, 3, 1), Role.TRADER))
    first.store.close()
    h = AgentHarness(TradingGraph(CFG, **QUIET), gateway=QueuedApprovalGateway(), store=TaskStore(db))
    c = TestClient(create_app(harness=h))
    k = {"X-API-Key": "dev-viewer-key"}
    health = c.get("/health").json()
    assert health["archived"] == 1 and health["live"] == 0 and health["persistent"]
    listing = c.get("/tasks", headers=k).json()
    assert listing[0]["task_id"] == run.id and listing[0]["live"] is False
    t = c.get(f"/tasks/{run.id}", headers=k).json()
    assert t["state"] == "COMPLETED" and t["live"] is False and "report" not in t
    assert c.get(f"/tasks/{run.id}/report", headers=k).json()["symbol"] == "AAPL"
    assert c.get(f"/tasks/{run.id}/report?format=markdown", headers=k).text.startswith("# AAPL decision")
    assert c.get(f"/tasks/{run.id}/evidence", headers=k).json()
    assert c.get(f"/tasks/{run.id}/trace", headers=k).json()["spans"]
    assert c.post(f"/tasks/{run.id}/cancel", headers={"X-API-Key": "dev-trader-key"}).status_code == 409
    assert c.post("/tasks/TASK-nope/cancel", headers={"X-API-Key": "dev-trader-key"}).status_code == 404
    h.store.close()


# --------------------------------------------------------------- TLS and posture
def test_serve_options_guard_deployment(tmp_path, caplog):
    fastapi = pytest.importorskip("fastapi")
    from agentic_trader.agentic.api import serve_options, uses_dev_keys
    cfg = make_config()
    assert uses_dev_keys(cfg["agentic"]["api_keys"]) and not uses_dev_keys({"k9f2...": "trader"})
    assert serve_options("127.0.0.1", cfg) == {}
    with pytest.raises(ValueError, match="development API keys"):
        serve_options("0.0.0.0", cfg)
    with caplog.at_level(logging.WARNING):
        assert serve_options("0.0.0.0", cfg, allow_dev_keys=True) == {}
    assert "plain HTTP" in caplog.text
    real = make_config(agentic={"api_keys": {"s3cr3t-long-random": "trader"}})
    with pytest.raises(ValueError, match="both"):
        serve_options("0.0.0.0", real, ssl_certfile="cert.pem")
    with pytest.raises(ValueError, match="not found"):
        serve_options("0.0.0.0", real, ssl_certfile="nope.pem", ssl_keyfile="nope.key")
    cert, key = tmp_path / "c.pem", tmp_path / "k.pem"
    cert.write_text("x"), key.write_text("y")
    assert serve_options("0.0.0.0", real, str(cert), str(key)) == {"ssl_certfile": str(cert), "ssl_keyfile": str(key)}


def test_serve_cli_plumbs_tls_and_store(monkeypatch, tmp_path, capsys):
    fastapi = pytest.importorskip("fastapi")
    import uvicorn
    seen = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: seen.update(kw))
    cert, key = tmp_path / "c.pem", tmp_path / "k.pem"
    cert.write_text("x"), key.write_text("y")
    assert main(["serve", "--host", "127.0.0.1", "--port", "9", "--ssl-cert", str(cert), "--ssl-key", str(key),
                 "--task-db", str(tmp_path / "t.sqlite")]) == 0
    assert seen["ssl_certfile"] == str(cert) and seen["port"] == 9
    assert "https://127.0.0.1:9" in capsys.readouterr().out
    assert main(["serve", "--host", "0.0.0.0", "--port", "9"]) == 2   # dev keys on a public interface


# ------------------------------------------------------------- evaluation universe
def test_universes_and_reserve_period():
    assert len(UNIVERSES["core"]) == 15 and len(UNIVERSES["extended"]) == 45 and len(UNIVERSES["all"]) == 60
    assert not set(UNIVERSES["core"]) & set(UNIVERSES["extended"])
    assert all(Instrument.parse(s) for s in UNIVERSES["all"])
    assert universe_group("AAPL") == "core" and universe_group("GLD") == "extended-macro"
    assert universe_group("EUR/GBP") == "extended" and universe_group("ZZZZ") == "other"
    assert set(EXTENDED_UNIVERSE) == {"equity", "macro_etf", "fx"} and set(CORE_UNIVERSE) == {"equity", "fx"}
    assert PERIODS["reserve"][0] > PERIODS["holdout"][1]
    res = evaluate(["AAPL", "GLD", "EURGBP"], {"q": ("2024-01-02", "2024-02-29")}, CFG, rebalance_every=10)
    assert set(res.rows.universe) == {"core", "extended-macro", "extended"}
    assert res.summary(universe="core").index.get_level_values("strategy").tolist()
    assert res.head_to_head(universe="extended")["instruments"].iloc[0] == 1
    assert "Impact%" in res.rows.columns and res.meta["impact_coeff"] == 0.0


def test_cli_loads_dotenv_without_overriding(tmp_path, monkeypatch):
    from agentic_trader.cli import load_dotenv
    env = tmp_path / ".env"
    env.write_text("# comment\nAT_TEST_NEW=from-file\nAT_TEST_OLD='quoted'\nbroken line\n", encoding="utf-8")
    monkeypatch.delenv("AT_TEST_NEW", raising=False)
    monkeypatch.setenv("AT_TEST_OLD", "from-env")
    assert load_dotenv(str(env)) == ["AT_TEST_NEW"]
    import os
    assert os.environ["AT_TEST_NEW"] == "from-file" and os.environ["AT_TEST_OLD"] == "from-env"
    monkeypatch.delenv("AT_TEST_NEW", raising=False)
    assert load_dotenv(str(tmp_path / "missing.env")) == []


def test_evaluate_cli_universe_flag(capsys):
    assert main(["evaluate", "--universe", "core", "AAPL", "--periods", "q1_2024", "--every", "20"]) == 0
    assert "median Sharpe" in capsys.readouterr().out
