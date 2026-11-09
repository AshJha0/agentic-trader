"""v0.16 LLM study first pass (PLAN.md 2.3, 2.5): resume, smoke failure detection, metrics shape.

Every test uses a fake LLM; no model and no network is called.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from agentic_trader.config import make_config
from agentic_trader.evaluation import TRIALS

NAMES = ["AAPL", "EURUSD"]


def _study() -> Any:
    path = Path(__file__).resolve().parents[1] / "scripts" / "llm_study.py"
    spec = importlib.util.spec_from_file_location("llm_study", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["llm_study"] = mod
    spec.loader.exec_module(mod)
    return mod


study = _study()


def _value(spec: dict[str, Any]) -> Any:
    if "enum" in spec:
        return spec["enum"][0]
    t = spec.get("type")
    t = t[0] if isinstance(t, list) else t
    return {"number": 0.2, "integer": 1, "string": "fake reply", "array": [], "boolean": False,
            "object": {}}.get(t, "fake")


class FakeLLM:
    """Answers every schema call with a minimal valid object; ``bad_every`` turns every n-th
    call into prose (unparseable) and ``none_every`` into no reply (fallback)."""

    def __init__(self, bad_every: int = 0, none_every: int = 0):
        self.n = 0
        self.bad_every, self.none_every = bad_every, none_every
        self.last_call: dict[str, Any] | None = None

    def _reply(self, text: str) -> str | None:
        self.n += 1
        self.last_call = {"model_served": "fake:1", "stop_reason": "stop"}
        if self.none_every and self.n % self.none_every == 0:
            return None
        if self.bad_every and self.n % self.bad_every == 0:
            return "I think the market will go up."
        return text

    def complete(self, system: str, prompt: str, *, deep: bool) -> str | None:
        return self._reply("A short argument with no numbers.")

    def complete_json(self, system: str, prompt: str, *, deep: bool, schema: dict[str, Any]) -> str | None:
        props = schema.get("properties", {})
        return self._reply(json.dumps({k: _value(v) for k, v in props.items()}))


def _cfg() -> dict:
    return make_config(study.STUDY_BASE)


def _cell(name: str) -> Any:
    return next(c for c in study.CELLS if c.name == name)


def test_first_pass_cells_are_registered_trials() -> None:
    names = {t.name for t in TRIALS}
    cells = study._first_pass_cells()
    assert [c.name for c in cells] == ["rules", "local_analysts", "local_all"]
    assert all(c.trial_name in names for c in cells if c.llm_roles)
    assert len(study.design_dates(study.FIRST_PASS["dates"])) == 20
    assert study.LOCAL_BUDGET["max_tokens"] <= 512 and 0 < study.MAX_FALLBACK_SHARE < 0.5


def test_every_study_cell_is_a_registered_trial() -> None:
    # PLAN 6.1: every model cell counts in the deflated Sharpe, run or not.
    names = {t.name for t in TRIALS}
    assert all(c.trial_name in names for c in study.CELLS if c.llm_roles)
    assert sum(1 for c in study.CELLS if c.llm_roles) == 7


def test_selection_report_counts_unmeasured_trials() -> None:
    from agentic_trader.evaluation import registered_trial_count
    from agentic_trader.stats import selection_report
    r = np.random.default_rng(0).normal(0.0005, 0.01, 1000)
    sharpes = [0.2, 0.4, 0.1, 0.5, 0.3]
    base = selection_report(r, sharpes)
    more = selection_report(r, sharpes, n_trials=registered_trial_count())
    assert base["trials"] == base["trials_measured"] == 5
    assert more["trials"] == len(TRIALS) and more["trials_measured"] == 5
    assert more["expected_max_sharpe_annual"] > base["expected_max_sharpe_annual"]
    assert more["deflated_sharpe_prob"] <= base["deflated_sharpe_prob"]
    assert selection_report(r, sharpes, n_trials=2)["trials"] == 5
    assert registered_trial_count("v0.14") < registered_trial_count("v0.15") < len(TRIALS)
    with pytest.raises(ValueError):
        registered_trial_count("v9.9")


def test_run_checkpoints_and_resumes(tmp_path: Path) -> None:
    out = tmp_path / "run.jsonl"
    dates = study.design_dates(20)[1:3]
    fakes: list[FakeLLM] = []

    def factory(cfg: dict) -> FakeLLM:
        fakes.append(FakeLLM())
        return fakes[-1]

    lines: list[str] = []
    rows = study.run_study(NAMES, dates[:1], 1, [_cell("local_analysts")], _cfg(), out, factory, lines.append)
    assert len(rows) == 2 and len(lines) == 2 and "[1/2] local_analysts" in lines[0]
    first_calls = fakes[0].n
    assert first_calls > 0 and all(c["reply"] and c["status"] == "ok" for r in rows for c in r["calls"])
    # a torn last line from a killed run is ignored, finished decisions are skipped
    with out.open("a", encoding="utf-8") as fh:
        fh.write('{"cell": "local_analysts", "sym')
    lines.clear()
    rows = study.run_study(NAMES, dates, 1, [_cell("local_analysts")], _cfg(), out, factory, lines.append)
    assert len(rows) == 4 and len(lines) == 2                       # only the two new decisions ran
    assert fakes[1].n == first_calls                               # same calls per decision, no repeats
    keys = [(r["symbol"], r["as_of"]) for r in rows]
    assert len(set(keys)) == 4
    for r in rows:
        assert {"close", "vt_weight", "regime", "sources", "calls", "target_weight"} <= set(r)
        assert any(v == "llm" for k, v in r["sources"].items() if k.startswith("analyst:"))
        assert all(v == "rules" for k, v in r["sources"].items() if not k.startswith("analyst:"))


def test_smoke_flags_unparseable_and_fallback(tmp_path: Path) -> None:
    out = tmp_path / "smoke.jsonl"
    quiet: list[str] = []
    assert study.smoke(_cfg(), out, lambda cfg: FakeLLM(), NAMES, quiet.append) == 0
    assert study.smoke(_cfg(), out, lambda cfg: FakeLLM(bad_every=5), NAMES, quiet.append) == 1
    assert study.smoke(_cfg(), out, lambda cfg: FakeLLM(none_every=7), NAMES, quiet.append) == 1
    rows = study.load_rows(out)
    assert len(rows) == 2 and "smoke: 2 decisions" in quiet[-1]
    assert any(c["status"] == "fallback" for r in rows for c in r["calls"])


def test_metrics_shape_and_bias_table(tmp_path: Path) -> None:
    out = tmp_path / "m.jsonl"
    dates = study.design_dates(20)[1:5]
    cells = [_cell("rules"), _cell("local_analysts")]
    rows = study.run_study(NAMES, dates, 1, cells, _cfg(), out, lambda cfg: FakeLLM(bad_every=4),
                           lambda s: None)
    m = study.cell_metrics(rows, _cfg())
    assert [x["cell"] for x in m] == ["rules", "local_analysts"]
    for x in m:
        assert x["decisions"] == 8 and x["periods"] == 3
        for k in ("sharpe", "control_sharpe", "sharpe_minus_control", "ci_lo", "ci_hi", "p",
                  "contract_rejection_rate", "fallback_share", "dispersion", "cost_usd_per_decision"):
            assert k in x
    rules, llm = m
    assert rules["calls"] == 0 and rules["admissible"] and rules["cost_usd_per_decision"] == 0
    assert llm["calls"] > 0 and llm["contract_rejection_rate"] > 0.1 and not llm["admissible"]
    assert llm["cost_usd_per_decision"] > 0 and np.isnan(llm["dispersion"])     # one seed
    bias = study.fallback_bias(rows)
    assert {(b["cell"], b["by"]) for b in bias} == {("local_analysts", "regime"), ("local_analysts", "as_of")}
    assert all(0.0 <= b["p"] <= 1.0 for b in bias)
    text = study.render_metrics(m, bias)
    assert text.count("Admissible fallback share per cell") == 2 and "| local_analysts |" in text and "NOT" in text


def test_block_bootstrap_and_chi2() -> None:
    rng = np.random.default_rng(1)
    a = rng.normal(0.02, 0.05, 40)
    diff, lo, hi, p = study.block_bootstrap_diff(a, a, 4.0)
    assert diff == 0 and lo <= 0 <= hi and p == 1.0
    diff, lo, hi, p = study.block_bootstrap_diff(a + 0.05, a - 0.05 + rng.normal(0, 0.01, 40), 4.0)
    assert diff > 0 and lo > 0 and p < 0.05
    assert study._chi2(np.array([[10, 0], [10, 0]])) == (0.0, 1.0)
    assert study._chi2(np.array([[20, 0], [0, 20]]))[1] < 0.001
    assert study.chi2_sf(3.841, 1) == pytest.approx(0.05, abs=1e-3)
    assert study.chi2_sf(18.307, 10) == pytest.approx(0.05, abs=1e-3)
    assert "calls" in study.wall_clock(4, 300)


def test_main_refuses_without_server_and_reports(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert study.main(["--smoke", "--model", "m", "--url", "http://127.0.0.1:9"]) == 2
    assert "refusing --smoke" in capsys.readouterr().err
    out = tmp_path / "r.jsonl"
    study.run_study(NAMES, study.design_dates(20)[1:4], 1, [_cell("rules")], _cfg(), out, None, lambda s: None)
    assert study.main(["--report", "--out", str(out)]) == 0
    assert "| rules |" in capsys.readouterr().out
