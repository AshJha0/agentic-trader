"""v0.6 features: one lookback knob, the prompt registry, the cross-instrument bootstrap,
repeated runs, the calibration harness, the cross-sectional alpha analyst, the bounded
task pool and multi-process serving, and the docs scripts."""
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agentic_trader import Instrument, TradingGraph, make_config
from agentic_trader.agentic import AgentHarness, DeskTools, QueuedApprovalGateway, build_registry
from agentic_trader.agents.analysts import XAlphaAnalyst
from agentic_trader.backtest import AGENT
from agentic_trader.calibration import CalibrationReport, calibrate
from agentic_trader.cli import main
from agentic_trader.data import SyntheticProvider
from agentic_trader.evaluation import UNIVERSES, EvaluationResult, evaluate

UNIVERSES_ALL = UNIVERSES["all"]
from agentic_trader.memory import DecisionMemory
from agentic_trader.prompts import prompt_bundle_hash, prompt_registry
from agentic_trader.stats import paired_bootstrap

CFG = make_config(memory_path=None)
QUIET = dict(memory=DecisionMemory(None), on_event=lambda *_: None)
ROOT = Path(__file__).resolve().parents[1]


# ----------------------------------------------------------- lookback knob
def test_one_lookback_knob_drives_analyst_and_tools():
    provider = SyntheticProvider(CFG)
    short = make_config(CFG, alpha_lookback_days=500)
    assert XAlphaAnalyst(None, short).lookback_days == 500
    from agentic_trader.agents.analysts import AlphaAnalyst
    assert AlphaAnalyst(None, short).lookback_days == 500 and AlphaAnalyst(None, CFG).lookback_days == 900
    tools = DeskTools(provider, make_config(CFG, lookback_days=120, alpha_lookback_days=800))
    h = tools.history("AAPL", date(2024, 3, 1))
    assert 70 <= len(h["dates"]) <= 90                      # ~120 calendar days of bars, not 400
    a = tools.alpha("AAPL", date(2024, 3, 1))
    assert max(v["n"] for v in a["ic"].values() if v.get("n")) > 300   # the 800-day alpha window
    schema = build_registry(tools).get("quant.alpha").descriptor.input_schema
    assert schema["properties"]["lookback_days"].get("nullable")       # None = configured window


# ----------------------------------------------------------- prompt registry
def test_prompt_registry_is_stable_and_sensitive():
    reg = prompt_registry(CFG)
    assert set(reg["agents"]) >= {"analyst:technical", "analyst:xalpha", "bull", "bear", "facilitator", "trader",
                                  "risk:aggressive", "risk:neutral", "risk:conservative", "pm", "firm_context"}
    assert all(len(v["system"]) == 16 for v in reg["agents"].values())
    assert reg["bundle"] == prompt_bundle_hash(CFG) == prompt_bundle_hash(make_config(CFG, lookback_days=10))
    res = evaluate(["AAPL"], {"q": ("2024-01-02", "2024-01-31")}, CFG, rebalance_every=10)
    assert res.meta["prompts"]["bundle"] == reg["bundle"] and res.meta["repeats"] == 1
    assert res.meta["alpha_lookback_days"] == 900 and res.meta["edgar"] is False


# ---------------------------------------------------- cross-instrument bootstrap
def test_paired_bootstrap_separates_signal_from_noise():
    rng = np.random.default_rng(1)
    base = rng.normal(0.5, 0.3, 40)
    same = paired_bootstrap(base + rng.normal(0, 0.05, 40), base, n_boot=2000)
    better = paired_bootstrap(base + 0.3 + rng.normal(0, 0.05, 40), base, n_boot=2000)
    assert same.n == 40 and not same.significant and same.p_value > 0.05
    assert better.significant and better.ci_low > 0.2 and better.p_value < 0.01 and better.wins == 40
    tiny = paired_bootstrap([1.0, 2.0], [0.5, 0.5])
    assert tiny.n == 2 and np.isnan(tiny.ci_low) and tiny.p_value == 1.0
    nan = paired_bootstrap([np.nan, 1.0, 2.0, 3.0], [0.0, 0.0, 0.0, 0.0])
    assert nan.n == 3 and nan.mean_diff == 2.0
    with pytest.raises(ValueError):
        paired_bootstrap([1, 2], [1])


def test_evaluation_paired_tables_and_repeats():
    res = evaluate(["AAPL", "MSFT", "NVDA", "EURUSD"], {"q": ("2024-01-02", "2024-03-28")}, CFG,
                   rebalance_every=10, repeats=2)
    agent = res.rows[res.rows.strategy == AGENT]
    assert sorted(agent.run.unique()) == [0, 1] and len(agent) == 8
    assert (res.rows[res.rows.strategy != AGENT].run == 0).all()          # baselines once
    disp = res.run_dispersion()
    assert disp.loc["q", "runs"] == 2 and disp.loc["q", "mean_std"] == 0.0  # rules are deterministic
    pb = res.paired("Buy&Hold", period="q")
    assert pb.n == 4
    tab = res.paired_table()
    assert set(tab.baseline) >= {"Buy&Hold", "B&H vol-target"} and (tab.n == 4).all()
    assert res.summary().loc[("q", AGENT), "n"] == 4                      # instruments, not instruments x runs
    with pytest.raises(ValueError):
        evaluate(["AAPL"], {"q": ("2024-01-02", "2024-01-31")}, CFG, repeats=0)


# ------------------------------------------------------------ calibration
def test_calibration_offline_is_deterministic_and_measures_anchoring(tmp_path):
    g = TradingGraph(CFG, **QUIET)
    rep = calibrate(g, "AAPL", "2024-03-01", n=2, anchors=(None, -0.5, 0.0, 0.5))
    assert len(rep.samples) == 8 and rep.prompts == prompt_bundle_hash(CFG)
    d = rep.dispersion(None)
    assert d["runs"] == 2 and d["std"] == 0.0 and d["agreement"] == 1.0
    a = rep.anchoring()
    assert a["anchors"] == 3 and np.isfinite(a["slope"]) and -0.5 <= a["slope"] <= 1.5
    s = rep.summary()
    assert s["llm_share"] == 0.0 and s["symbol"] == "AAPL"
    rep.to_json(tmp_path / "c.json")
    back = CalibrationReport.from_json(tmp_path / "c.json")
    drift = rep.compare(back)
    assert drift["same_prompts"] and drift["mean_target_shift"] == 0.0 and drift["action_distribution_distance"] == 0.0
    with pytest.raises(ValueError):
        rep.compare(CalibrationReport("MSFT", "2024-03-01", rep.samples, rep.prompts))
    with pytest.raises(ValueError):
        calibrate(g, "AAPL", "2024-03-01", n=0)


def test_calibration_with_a_noisy_model():
    class Noisy:
        def __init__(self):
            self.k = 0

        def complete(self, system, prompt, *, deep):
            if "Trader." not in system:
                return None
            self.k += 1
            w = 0.3 + 0.1 * (self.k % 3)
            return json.dumps({"action": "BUY", "target_weight": w, "confidence": 0.6, "stop_loss": 150,
                               "take_profit": 220, "horizon_days": 10, "rationale": "x"})
    g = TradingGraph(CFG, llm=Noisy(), **QUIET)
    rep = calibrate(g, "AAPL", "2024-03-01", n=3, anchors=(None,))
    d = rep.dispersion(None)
    assert d["runs"] == 3 and d["std"] > 0 and rep.samples.llm_share.mean() > 0


def test_calibrate_cli(tmp_path, capsys):
    out = tmp_path / "cal.json"
    assert main(["calibrate", "AAPL", "--date", "2024-03-01", "--n", "1", "--anchors", "none,0.2",
                 "--out", str(out)]) == 0
    assert out.exists() and '"anchoring"' in capsys.readouterr().out
    assert main(["calibrate", "AAPL", "--date", "2024-03-01", "--n", "1", "--anchors", "none",
                 "--compare", str(out)]) == 0
    assert "drift vs" in capsys.readouterr().out


# -------------------------------------------------- cross-sectional alpha analyst
def test_xalpha_analyst_ranks_within_its_universe():
    provider = SyntheticProvider(CFG)
    cfg = make_config(CFG, xalpha_universe=["AAPL", "MSFT", "NVDA", "META", "GOOGL", "AMZN"])
    ins = Instrument.parse("JPM")                                       # not in the list: added to the cross-section
    as_of = date(2020, 6, 1)
    df = provider.history(ins, date(2017, 1, 1), as_of)
    from agentic_trader.state import TradingState
    st = TradingState(ins, as_of, df[df.index <= pd.Timestamp(as_of)])
    an = XAlphaAnalyst(None, cfg)
    facts = an.gather(st, provider)
    assert facts["breadth"] == 7 and "JPM" in facts["universe"] and facts["horizon"] == 10
    assert set(facts["ic"]) and all({"IC", "t(IC)", "n"} <= set(v) for v in facts["ic"].values())
    rep = an.rules(facts, st)
    assert rep.analyst == "xalpha" and (rep.abstained or -1 <= rep.signal <= 1)
    # the cross-section is cached per (universe, date): members of the list share one entry
    from agentic_trader.agents import analysts as mod
    cache = mod._xalpha_cache_for(provider)
    before = len(cache)
    an.gather(TradingState(Instrument.parse("AAPL"), as_of, df), provider)
    an.gather(TradingState(Instrument.parse("MSFT"), as_of, df), provider)
    assert len(cache) == before + 1
    # thin cross-section -> abstain
    thin = XAlphaAnalyst(None, make_config(CFG, xalpha_universe=["AAPL", "MSFT"]))
    assert thin.rules(thin.gather(st, provider), st).abstained
    # wired into the desk
    g = TradingGraph(make_config(cfg, analysts=["technical", "xalpha"]), provider=provider, **QUIET)
    state, _ = g.propagate("AAPL", "2020-06-01")
    assert "xalpha" in state.reports
    # the CLI can set the peer set by universe name or by list
    from agentic_trader.cli import _config
    from types import SimpleNamespace
    base = dict(data="synthetic", llm="offline", csv_dir=None, rounds=None, deep_model=None, quick_model=None)
    assert _config(SimpleNamespace(**base, xalpha_universe="all"))["xalpha_universe"] == UNIVERSES_ALL
    assert _config(SimpleNamespace(**base, xalpha_universe="AAPL,MSFT"))["xalpha_universe"] == ["AAPL", "MSFT"]
    assert main(["analyze", "AAPL", "--date", "2020-06-01", "--analysts", "technical,xalpha", "--xalpha-universe", "core",
                 "--no-memory", "--json"]) == 0


# --------------------------------------------------- bounded task pool / processes
def test_api_task_pool_is_bounded():
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from agentic_trader.agentic.api import create_app
    h = AgentHarness(TradingGraph(CFG, **QUIET), gateway=QueuedApprovalGateway())
    c = TestClient(create_app(harness=h, workers=2, queue_limit=0))
    hd = c.get("/health").json()
    assert hd["workers"] == 2 and hd["queue_limit"] == 0 and hd["in_flight"] == 0 and "worker_pid" in hd
    r = c.post("/tasks", json={"symbol": "AAPL", "as_of": "2024-03-01"}, headers={"X-API-Key": "dev-trader-key"})
    assert r.status_code == 503 and r.headers["retry-after"] == "5"
    with pytest.raises(ValueError):
        create_app(harness=h, workers=0)
    c2 = TestClient(create_app(harness=h, workers=1, queue_limit=4))
    tids = [c2.post("/tasks", json={"symbol": s, "as_of": "2024-03-01"},
                    headers={"X-API-Key": "dev-trader-key"}).json()["task_id"] for s in ("AAPL", "MSFT", "EURUSD")]
    import time
    t0 = time.time()
    while time.time() - t0 < 60 and any(c2.get(f"/tasks/{t}", headers={"X-API-Key": "dev-viewer-key"}).json()["state"]
                                        not in ("COMPLETED", "FAILED") for t in tids):
        time.sleep(0.05)
    assert all(c2.get(f"/tasks/{t}", headers={"X-API-Key": "dev-viewer-key"}).json()["state"] == "COMPLETED" for t in tids)


def test_multiprocess_serving_needs_a_store_and_plumbs_the_config(monkeypatch, tmp_path, capsys):
    pytest.importorskip("fastapi")
    from agentic_trader.agentic.api import CONFIG_ENV, app_factory, multiprocess_options, serve
    assert multiprocess_options(1, CFG) == {}
    with pytest.raises(ValueError, match="task store"):
        multiprocess_options(2, CFG)
    cfg = make_config(CFG, agentic={"task_db": str(tmp_path / "t.sqlite")})
    assert multiprocess_options(3, cfg) == {"workers": 3}
    with pytest.raises(ValueError):
        multiprocess_options(0, cfg)
    uvicorn = pytest.importorskip("uvicorn")
    seen = {}

    def fake_run(app, **kw):
        seen.update(kw, app=app, env=dict(__import__("os").environ))
    monkeypatch.setattr(uvicorn, "run", fake_run)
    serve("127.0.0.1", 9, cfg, processes=2)
    assert seen["workers"] == 2 and seen["app"] == "agentic_trader.agentic.api:app_factory" and seen["factory"]
    assert CONFIG_ENV in seen["env"] and not Path(seen["env"][CONFIG_ENV]).exists()   # temp config cleaned up
    # the factory builds the app from the JSON the parent wrote
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(cfg, default=str), encoding="utf-8")
    monkeypatch.setenv(CONFIG_ENV, str(p))
    app = app_factory()
    assert app.state.harness.store is not None
    assert main(["serve", "--port", "9", "--processes", "2", "--task-db", str(tmp_path / "s.sqlite"),
                 "--workers", "3"]) == 0
    assert "2 process(es) x 3 task threads" in capsys.readouterr().out
    assert main(["serve", "--port", "9", "--processes", "2"]) == 2


# ---------------------------------------------------------------- docs scripts
def test_docs_scripts_run():
    py = sys.executable
    links = subprocess.run([py, str(ROOT / "scripts/check_links.py")], capture_output=True, text=True, cwd=ROOT)
    assert links.returncode == 0, links.stdout + links.stderr
    mm = subprocess.run([py, str(ROOT / "scripts/check_mermaid.py"), "--html"], capture_output=True, text=True, cwd=ROOT)
    assert mm.returncode == 0 and (ROOT / "build/mermaid_check.html").exists()
    cb = subprocess.run([py, str(ROOT / "scripts/run_cookbook.py"), "--offline", "--only", "one decision"],
                        capture_output=True, text=True, cwd=ROOT, timeout=600)
    assert cb.returncode == 0 and ("OK " in cb.stdout or "SKIP" in cb.stdout), cb.stdout + cb.stderr


# ------------------------------------------------- review findings (regressions)
def test_records_are_visible_across_processes_through_the_store(tmp_path):
    """Two harnesses on one task store stand in for two `serve --processes` workers: a task run
    on the first is readable on the second (record, listing, health) and cancel answers 409."""
    pytest.importorskip("fastapi")
    from datetime import date as _date

    from fastapi.testclient import TestClient

    from agentic_trader.agentic import Role, Task
    from agentic_trader.agentic.api import create_app
    from agentic_trader.agentic.store import TaskStore
    db = tmp_path / "shared.sqlite"
    a = AgentHarness(TradingGraph(CFG, **QUIET), store=TaskStore(db))
    b = AgentHarness(TradingGraph(CFG, **QUIET), store=TaskStore(db), sweep_interrupted=False)   # a sibling starting later
    run = a.run(Task("AAPL", _date(2024, 3, 1), Role.TRADER))
    assert run.state.value == "COMPLETED" and run.id not in b.archive                          # not in B's start-up snapshot
    assert b.record(run.id)["state"] == "COMPLETED"                                              # ... but served from the store
    c = TestClient(create_app(harness=b))
    assert c.get(f"/tasks/{run.id}", headers={"X-API-Key": "dev-viewer-key"}).json()["live"] is False
    assert c.get(f"/tasks/{run.id}/report", headers={"X-API-Key": "dev-viewer-key"}).status_code == 200
    assert any(t["task_id"] == run.id for t in c.get("/tasks", headers={"X-API-Key": "dev-viewer-key"}).json())
    assert c.get("/health").json()["archived"] >= 1
    assert c.post(f"/tasks/{run.id}/cancel", headers={"X-API-Key": "dev-trader-key"}).status_code == 409
    assert c.post("/tasks/TASK-nope/cancel", headers={"X-API-Key": "dev-trader-key"}).status_code == 404
    # a sibling must not fail the other worker's in-flight runs: the sweep is off for it
    live = a.submit(Task("MSFT", _date(2024, 3, 1), Role.TRADER))
    AgentHarness(TradingGraph(CFG, **QUIET), store=TaskStore(db), sweep_interrupted=False)
    assert TaskStore(db).load(live.id)["state"] == "CREATED"
    AgentHarness(TradingGraph(CFG, **QUIET), store=TaskStore(db))                                # a real restart sweeps
    assert TaskStore(db).load(live.id)["state"] == "FAILED"


def test_queued_task_can_be_cancelled_before_it_starts_and_shutdown_drains_nothing():
    pytest.importorskip("fastapi")
    import time
    from datetime import date as _date

    from fastapi.testclient import TestClient

    from agentic_trader.agentic import Role, Task
    from agentic_trader.agentic.api import create_app
    h = AgentHarness(TradingGraph(CFG, **QUIET))
    run = h.submit(Task("AAPL", _date(2024, 3, 1), Role.TRADER))
    h.cancel(run.id)
    assert h.resume(run).state.value == "CANCELLED" and run.plan is None                        # no planning, no data
    app = create_app(harness=h, workers=1, queue_limit=10)
    with TestClient(app) as c:                                                                     # lifespan runs
        r = c.post("/tasks", json={"symbol": "EURUSD", "as_of": "2024-03-01"}, headers={"X-API-Key": "dev-trader-key"})
        tid = r.json()["task_id"]
        t0 = time.time()
        while time.time() - t0 < 30 and h.runs[tid].state.value not in ("COMPLETED", "FAILED", "CANCELLED"):
            time.sleep(0.02)
    assert app.state.pool._shutdown                                                                # closed on shutdown


def test_validate_app_config_fails_before_forking(tmp_path):
    pytest.importorskip("fastapi")
    from agentic_trader.agentic.api import multiprocess_options, validate_app_config
    with pytest.raises(ValueError, match="workers"):
        validate_app_config(make_config(CFG, agentic={"workers": 0}))
    with pytest.raises(ValueError, match="unknown role"):
        validate_app_config(make_config(CFG, agentic={"api_keys": {"k": "emperor"}}))
    with pytest.raises(ValueError):
        multiprocess_options(2, make_config(CFG, agentic={"task_db": str(tmp_path / "t.sqlite"), "queue_limit": -1}))


def test_coerce_arguments_rejects_non_finite_numbers():
    from agentic_trader.agentic.tools import coerce_arguments
    schema = {"type": "object", "properties": {"n": {"type": "integer"}, "x": {"type": "number"}}, "required": []}
    for bad in ({"n": float("inf")}, {"n": float("nan")}, {"x": float("inf")}, {"x": float("-inf")}):
        with pytest.raises(ValueError):
            coerce_arguments(schema, bad)
    assert coerce_arguments(schema, {"n": 3.0, "x": 2}) == {"n": 3, "x": 2.0}


def test_xalpha_cache_is_per_provider_and_thread_safe():
    import threading

    from agentic_trader.agents import analysts as mod
    from agentic_trader.state import TradingState
    seeds = {}
    for seed in (7, 11):
        prov = SyntheticProvider(make_config(CFG, synthetic_seed=seed))
        ins = Instrument.parse("AAPL")
        df = prov.history(ins, date(2017, 1, 1), date(2020, 6, 1))
        st = TradingState(ins, date(2020, 6, 1), df)
        an = XAlphaAnalyst(None, make_config(CFG, xalpha_universe=["AAPL", "MSFT", "NVDA", "META", "GOOGL", "AMZN"]))
        seeds[seed] = an.gather(st, prov)["combined_z"]
        assert prov in mod._XALPHA_CACHES
    assert seeds[7] != seeds[11]                                                   # a new provider never sees another's cross-section
    cache = {}
    old = mod._XALPHA_CACHE_MAX
    mod._XALPHA_CACHE_MAX = 8
    try:
        errors = []

        def hammer(k):
            try:
                for i in range(200):
                    mod._xalpha_cache_put(cache, (k, i), i)
            except Exception as e:  # noqa: BLE001
                errors.append(e)
        ts = [threading.Thread(target=hammer, args=(k,)) for k in range(6)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert not errors and len(cache) <= 8
    finally:
        mod._XALPHA_CACHE_MAX = old


def test_calibration_compare_uses_a_shared_anchor():
    g = TradingGraph(CFG, **QUIET)
    a = calibrate(g, "AAPL", "2024-03-01", n=1, anchors=(0.0, 0.5))
    b = calibrate(g, "AAPL", "2024-03-01", n=1, anchors=(0.5, -0.5))
    d = a.compare(b)
    assert d["anchor"] == 0.5 and d["mean_target_shift"] == 0.0 and np.isfinite(d["action_distribution_distance"])
    assert a.summary()["dispersion"]["runs"] == 1 and a.base_anchor() == 0.0
    with pytest.raises(ValueError, match="anchor"):
        a.compare(calibrate(g, "AAPL", "2024-03-01", n=1, anchors=(-0.25,)))


def test_summary_counts_instruments_once_with_repeats_and_baselines_pair_with_agent_rows():
    res = evaluate(["AAPL", "MSFT"], {"q": ("2024-01-02", "2024-02-29")}, CFG, rebalance_every=10, repeats=3)
    s = res.summary()
    assert s.loc[("q", AGENT), "n"] == 2 and s.loc[("q", "Buy&Hold"), "n"] == 2
    assert (res.rows[res.rows.strategy != AGENT].run == 0).all()
    have_agent = set(map(tuple, res.rows[res.rows.strategy == AGENT][["period", "symbol"]].drop_duplicates().to_numpy()))
    have_bh = set(map(tuple, res.rows[res.rows.strategy == "Buy&Hold"][["period", "symbol"]].to_numpy()))
    assert have_agent == have_bh


def test_check_links_anchor_slugs_follow_github():
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_links", ROOT / "scripts/check_links.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    md = "# Fixed\n\n```python\n# not a heading\n```\n\n## Fixed\n\n## `Code` heading\n"
    assert mod.anchors(md) == {"fixed", "fixed-1", "code-heading"}


def test_prompt_registry_marks_missing_source_instead_of_hashing_repr(monkeypatch):
    from agentic_trader import prompts as pm

    def no_source(obj):
        raise OSError("no source")
    monkeypatch.setattr(pm.inspect, "getsource", no_source)
    reg = pm.prompt_registry(CFG)
    assert all(v.get("template") == pm.SOURCE_UNAVAILABLE for k, v in reg["agents"].items() if k != "firm_context")
