"""Offline checks for scripts/v16_local_study.py (plan items 2.4 and 2.6) with fake LLMs only."""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import v16_local_study as v16  # noqa: E402


class FakeRecall:
    def __init__(self, answer_for=None):
        self.prompts: list[str] = []
        self.answer_for = answer_for

    def complete(self, system, prompt, *, deep):
        self.prompts.append(prompt)
        if self.answer_for is not None:
            return self.answer_for(prompt)
        return "TICKER: SPY\nMONTH: 2016-01"


class FakeAnalyst:
    """Signal = (50 - rsi14) / 100 plus a temperature-dependent jitter; records sampling settings."""

    def __init__(self, bad=False):
        self.temperature, self.seed, self.calls, self.bad = 0.0, 0, [], bad

    def complete_json(self, system, prompt, *, deep, schema):
        assert schema is v16.contracts.ANALYST
        self.calls.append((self.temperature, self.seed))
        if self.bad:
            return "not json"
        m = re.search(r'"rsi14":\s*([-0-9.e]+)', prompt)
        rsi = float(m.group(1)) if m else 50.0
        jitter = 0.01 * (self.seed % 3 - 1) if self.temperature > 0 else 0.0
        return json.dumps({"signal": (50 - rsi) / 100 + jitter, "confidence": 0.5, "summary": "x",
                           "key_points": []})


@pytest.fixture(scope="module")
def graph():
    return v16.make_graph("synthetic")


def test_anonymised_prompt_hides_name_date_and_level(graph):
    st = v16.FrozenState(graph, "AAPL", v16.design_dates(14)[3])
    p = st.prompt()
    assert "AAPL" not in p and "STOCK_X" in p and "D0" in p
    assert not re.search(r"20\d\d-\d\d-\d\d", p)
    assert "Last close: 100" in p
    assert "rsi14" in st.prompt_keys() and '"rsi14"' not in st.prompt(drop="rsi14")
    fx = v16.FrozenState(graph, "EURUSD", v16.design_dates(14)[3]).prompt()
    assert "EUR" not in fx and "CCY_BASE" in fx


def test_parse_and_score_recall():
    g = v16.parse_recall("TICKER: **eur/usd**\nMONTH: 2019-3", v16.NAMES)
    assert g == {"ticker": "EURUSD", "month": "2019-03"}
    assert v16.parse_recall("TICKER: TSLA\nMONTH: 2019-03", v16.NAMES) is None
    assert v16.parse_recall("I cannot tell", v16.NAMES) is None
    s = v16.score(g, "EURUSD", date(2019, 4, 2))
    assert s["ticker_hit"] and not s["month_hit"] and s["month_near"] and s["month_err"] == -1


def test_stats():
    assert v16.binom_sf(0, 10, 0.3) == pytest.approx(1.0)
    assert v16.binom_sf(10, 10, 0.5) == pytest.approx(0.5 ** 10)
    lo, hi = v16.wilson(20, 200)
    assert lo < 0.1 < hi
    r = v16.rate_row(40, 200, 1 / 15)
    assert r["above_chance"] and r["p_one_sided"] < 1e-6


def test_recall_items_count():
    items = v16.recall_items()
    assert len(items) == 200 and len({n for n, _ in items}) == 15


def test_recall_run_resume_and_ablation(graph, tmp_path):
    def ans(prompt):
        hit = "Instrument: STOCK_X" in prompt and '"rsi14"' in prompt
        return "TICKER: AAPL\nMONTH: 2030-01" if hit else "TICKER: SPY\nMONTH: 2030-01"

    llm = FakeRecall(ans)
    out = tmp_path / "recall.json"
    res = v16.run_recall(llm, graph, out, limit=2, log=lambda m: None)
    assert res["n"] == 2 and res["ticker"]["hits"] == 2 and res["unparsed"] == 0
    assert all(r["raw"] for r in res["rows"])
    assert res["ablation"]["leaking_keys"] == ["rsi14"]
    assert len(llm.prompts) == 2 + sum(len(r["keys"]) for r in res["rows"])
    llm2 = FakeRecall(ans)
    res2 = v16.run_recall(llm2, graph, out, limit=2, log=lambda m: None)
    assert llm2.prompts == [] and res2["ticker"]["hits"] == 2


def test_calibration_dispersion_anchor_and_drift(graph, tmp_path):
    llm = FakeAnalyst()
    res = v16.run_calibration(llm, graph, tmp_path / "a.json", limit=3, log=lambda m: None)
    assert res["calls"] == 3 * (1 + 5 + 4) == len(llm.calls) and res["unparsed"] == 0
    assert {t for t, _ in llm.calls} == {0.0, 0.7}
    assert res["dispersion"]["mean_std"] > 0
    assert res["anchoring"]["slope"] == pytest.approx(-0.01, abs=1e-6)
    assert len(res["baseline"]) == 3
    a = json.loads(json.dumps(res, default=str))
    b = json.loads(json.dumps(res, default=str))
    b["baseline"] = {k: v + 0.1 for k, v in a["baseline"].items()}
    d = v16.drift(a, b)
    assert d["n"] == 3 and d["mean_abs_diff"] == pytest.approx(0.1)
    b["states"] = ["X@2020-01-01"]
    with pytest.raises(ValueError):
        v16.drift(a, b)


def test_calibration_states_are_frozen():
    assert v16.calibration_states() == v16.calibration_states()
    assert len(v16.calibration_states()) == 20


def test_smoke_exit_codes(tmp_path):
    args = ["--data", "synthetic", "--smoke", "--repeats", "1", "--anchor-values", "30"]
    assert v16.main(["calibration", "--out", str(tmp_path / "c.json"), *args],
                    llm_factory=lambda a: FakeAnalyst()) == 0
    assert (tmp_path / "c.smoke.json").exists()
    assert v16.main(["calibration", "--out", str(tmp_path / "d.json"), *args],
                    llm_factory=lambda a: FakeAnalyst(bad=True)) == 1
    assert v16.main(["recall", "--out", str(tmp_path / "r.json"), "--data", "synthetic", "--smoke"],
                    llm_factory=lambda a: FakeRecall(lambda p: "no idea")) == 1
    assert v16.main(["recall", "--out", str(tmp_path / "r2.json"), "--data", "synthetic", "--smoke"],
                    llm_factory=lambda a: FakeRecall()) == 0


def test_drift_cli(graph, tmp_path):
    res = v16.run_calibration(FakeAnalyst(), graph, tmp_path / "a.json", limit=2, repeats=1,
                              anchor_values=(30.0,), log=lambda m: None)
    full = tmp_path / "a_full.json"
    full.write_text(json.dumps(res, default=str), encoding="utf-8")
    assert v16.main(["drift", "--a", str(full), "--b", str(full), "--out", str(tmp_path / "d.json")]) == 0
    d = json.loads((tmp_path / "d.json").read_text(encoding="utf-8"))
    assert d["mean_abs_diff"] == 0 and d["sign_agreement"] == 1.0


def test_sampled_llm_sets_temperature_without_network():
    llm = v16.SampledLocalLLM({"local_llm_model": "m:7b", "local_llm_seed": 1})
    llm.temperature, llm.seed = 0.7, 9
    body = llm.build_request("s", "p", v16.contracts.ANALYST)
    assert body["options"]["temperature"] == 0.7 and body["options"]["seed"] == 9 and body["format"]
