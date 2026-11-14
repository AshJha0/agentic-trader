"""v0.18 lane E: scoped red-team design (--per-category), interleaved order, Wilson report.

No model is called: ``run_unit`` is replaced by a fake that records which units ran."""

import json
import math
from collections import Counter

import pytest

from agentic_trader.agentic import redteam_v2 as rt2
from agentic_trader.agentic.redteam import load_corpus

STATES = rt2.DEFAULT_STATES
AN = ("news", "sentiment")


def _fake_corpus():
    cats = {"a": 7, "b": 3, "c": 5}
    return [{"id": f"{c}{i:02d}", "category": c, "carrier": "x", "payload": "y"} for c, n in cats.items() for i in range(n)]


def test_per_category_is_deterministic_and_seeded():
    corpus = _fake_corpus()
    a = rt2.select_per_category(corpus, 2, 2026)
    b = rt2.select_per_category(list(reversed(corpus)), 2, 2026)  # input order does not matter
    assert [s["id"] for s in a] == [s["id"] for s in b]
    assert Counter(s["category"] for s in a) == {"a": 2, "b": 2, "c": 2}
    others = {tuple(s["id"] for s in rt2.select_per_category(corpus, 2, seed)) for seed in range(20)}
    assert len(others) > 1
    assert rt2.select_per_category(corpus, None) == corpus
    assert len(rt2.select_per_category(corpus, 5)) == 5 + 3 + 5  # short category gives all


def test_real_corpus_design_sizes():
    corpus = load_corpus()
    cats = Counter(s["category"] for s in corpus)
    assert len(corpus) == 150 and len(cats) == 5
    assert len(rt2.plan_units(corpus, STATES, AN, ("json",))) == 1500
    sub = rt2.select_per_category(corpus, 2, 2026)
    assert len(rt2.plan_units(sub, STATES, AN, ("json",))) == 100


def test_balance_and_interleaving():
    sub = rt2.select_per_category(load_corpus(), 2, 2026)
    units = rt2.plan_units(sub, STATES, AN, ("json",))
    cells = Counter((u.symbol, u.analyst) for u in units)
    assert len(cells) == 10 and set(cells.values()) == {len(sub)}
    per_cell = {}
    for u in units:
        per_cell.setdefault((u.symbol, u.analyst), set()).add(u.snippet["id"])
    assert len({frozenset(v) for v in per_cell.values()}) == 1  # every cell, same snippets
    for k in (7, 23, 55):  # any prefix is near balanced
        c = Counter((u.symbol, u.analyst) for u in units[:k])
        assert max(c.values()) - min(c.values(), default=0) <= 1 and len(c) == min(k, 10)


def test_keys_unchanged_by_reordering():
    corpus = load_corpus()[:4]
    units = rt2.plan_units(corpus, STATES, rt2.ANALYSTS, rt2.MODES)
    old = [
        f"{m}|{s}|{d}|{a}|{sn['id']}"
        for m in rt2.MODES
        for s, d in STATES
        for a in rt2.ANALYSTS
        if not ((m == "free" and a in rt2.TEXT_ONLY_JSON) or (s == "EURUSD" and a == "fundamentals_text"))
        for sn in corpus
    ]
    assert sorted(u.key for u in units) == sorted(old) and len(units) == len(old)


@pytest.fixture
def fake_run_unit(monkeypatch):
    ran = []

    def fake(u, config, provider, model, threshold=0.5, end_to_end=True):
        ran.append(u.key)
        return {
            "key": u.key,
            "mode": u.mode,
            "analyst": u.analyst,
            "category": u.snippet["category"],
            "target": 1,
            "directed_complied": True,
            "weight_dir_matched": False,
            "critic_acted_attack": True,
        }

    monkeypatch.setattr(rt2, "run_unit", fake)
    return ran


def test_resume_and_design_guard(tmp_path, fake_run_unit):
    corpus = _fake_corpus()
    sub = rt2.select_per_category(corpus, 2, 2026)
    units = rt2.plan_units(sub, STATES[:2], AN, ("json",))
    design = {"per_category": 2, "seed": 2026, "selected_ids": [s["id"] for s in sub]}
    out = tmp_path / "e2e.jsonl"
    summ = rt2.run(units[:5], {}, None, None, out, log=lambda _m: None, design=design)
    assert len(fake_run_unit) == 5 and summ["design"]["selected_ids"] == design["selected_ids"]
    rt2.run(units, {}, None, None, out, log=lambda _m: None, design=design)
    assert len(fake_run_unit) == len(units)  # resumed: only the rest ran
    rt2.run(units, {}, None, None, out, log=lambda _m: None, design=design)
    assert len(fake_run_unit) == len(units)
    with pytest.raises(ValueError, match="different --out"):
        rt2.run(units, {}, None, None, out, log=lambda _m: None, design={**design, "seed": 1})
    with pytest.raises(ValueError, match="different --out"):
        rt2.run(units, {}, None, None, out, log=lambda _m: None, design=design, end_to_end=False)
    full = tmp_path / "full.jsonl"
    full.write_text('{"key": "x"}\n', encoding="utf-8")  # legacy rows, no header
    with pytest.raises(ValueError, match="without a design header"):
        rt2.run(units, {}, None, None, full, log=lambda _m: None, design=design)
    assert json.loads(out.with_suffix(".design.json").read_text())["per_category"] == 2


def test_wilson_values():
    lo, hi = rt2.wilson(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-4) and hi == pytest.approx(0.7634, abs=1e-4)
    lo, hi = rt2.wilson(0, 20)
    assert lo == 0.0 and hi == pytest.approx(0.1611, abs=1e-4)
    assert rt2.wilson(20, 20)[1] == 1.0
    assert all(math.isnan(x) for x in rt2.wilson(0, 0))


def test_report_conditional_catch_rate():
    def r(cat, comp, matched=None, target=1, mode="json"):
        row = {"mode": mode, "category": cat, "target": target, "directed_complied": comp}
        if matched is not None:
            row.update(weight_dir_matched=matched, critic_acted_attack=not matched)
        return row

    rows = [r("a", True, False), r("a", True, True), r("a", False, False), r("b", True, False), r("b", False, False, target=0)]
    rep = rt2.compliance_report(rows)
    assert rep["total"]["compliance"]["k"] == 3 and rep["total"]["compliance"]["n"] == 4
    g = rep["total"]["governance_catch_given_complied"]
    assert (g["k"], g["n"]) == (2, 3)
    assert rep["by_category"]["a"]["compliance"]["n"] == 3
    assert rep["by_category"]["b"]["governance_catch_given_complied"]["k"] == 1
    analyst_only = rt2.compliance_report([r("a", True)])
    assert "governance_catch_given_complied" not in analyst_only["total"]
