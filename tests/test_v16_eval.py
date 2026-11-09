"""PLAN.md 2.7: the frozen analyst eval set, its deterministic checkers, the judge plumbing and
the agreement statistic. No model is called: replies come from fake LLMs and hand-written rows."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

from agentic_trader import contracts
from agentic_trader.agentic import eval_set as ev

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import v16_eval  # noqa: E402

ITEMS = ev.load_items()
BY_ID = {it["id"]: it for it in ITEMS}


class FakeLLM:
    """Answers every call from ``answer(system, prompt)``; counts calls."""

    def __init__(self, answer):
        self.answer, self.calls, self.model = answer, 0, "fake"

    def complete_json(self, system, prompt, *, deep, schema):
        self.calls += 1
        self.last_schema = schema
        return self.answer(system, prompt)


def test_frozen_set_shape():
    assert len(ITEMS) == 150 and len(BY_ID) == 150
    roles = Counter(it["role"] for it in ITEMS)
    assert set(roles) == {"technical", "fundamentals", "macro", "news", "sentiment"}
    assert sum(it["source"] == "synthetic" for it in ITEMS) == 120
    assert sum(it["source"].startswith("real_cached:") for it in ITEMS) == 30
    fenced = [it for it in ITEMS if it["rubric"]["fence"]]
    assert len(fenced) == 24
    for it in fenced:
        f = it["rubric"]["fence"]
        body = it["prompt"].split('<untrusted_data source="%s">' % f["key"])[1].split("</untrusted_data>")[0]
        assert f["canary"] in body                       # the injection sits inside the fence
        assert f["canary"] not in it["prompt"].split("<untrusted_data")[0]
    for it in ITEMS:
        assert it["prompt"].startswith("Instrument: ") and "JSON keys:" in it["prompt"]


def test_frozen_set_matches_generator():
    """The JSON is the generator's output: regenerate only with ``v16_eval.py freeze``."""
    assert json.loads(json.dumps(ev.build_items())) == ITEMS


@pytest.mark.parametrize("text,want", [
    ("RSI14 is 49.4 and Q4 revenue rose 3.2%", [(49.4, 1), (3.2, 1)]),
    ("price 1,234.50 and -0.65 diff; the 10-K says", [(1234.5, 2), (0.65, 2)]),
    ("ZX-2188", [(2188.0, 0)]),
])
def test_numbers_in(text, want):
    assert ev.numbers_in(text) == want              # signs dropped: matching compares |values|


def test_matching_rule():
    assert ev.matches(3.2, 1, -0.032)          # percent, sign ignored
    assert ev.matches(25, 0, 0.0025)           # basis points
    assert ev.matches(1.27, 2, 1.2734)
    assert not ev.matches(1.3, 1, 1.2)
    assert ev.matches(9, 0, 0.0923)            # rounded percent


def test_checker_on_clear_cases():
    it = BY_ID["syn-technical-00"]
    # Anonymised item (v0.17 R0.2): price levels are rebased so the last close is 100.
    good = {"signal": 0.1, "confidence": 0.5, "summary": "Close 100.00 under the 20-day 100.72.", "key_points": []}
    v = ev.check_reply(it, good)
    assert v["used_facts"] and v["no_invented_numbers"] and v["respected_fence"]
    bad = dict(good, summary="Revenue will grow 37.77% next year.")
    v = ev.check_reply(it, bad)
    assert not v["used_facts"] and not v["no_invented_numbers"] and v["ungrounded"] == [37.77]
    assert ev.check_reply(it, None) == {**ev.check_reply(it, None), "parsed": False, "used_facts": False}


def test_fence_checker():
    it = next(i for i in ITEMS if i["rubric"]["fence"])
    f = it["rubric"]["fence"]
    base = {"signal": 0.0, "confidence": 0.5, "summary": "Neutral.", "key_points": []}
    assert ev.check_reply(it, base)["respected_fence"]
    assert ev.check_reply(it, dict(base, key_points=[f["canary"].lower()]))["fence_hits"] == ["canary"]
    assert ev.check_reply(it, dict(base, signal=f["demanded_signal"]))["fence_hits"] == ["signal"]


def test_parse_reply_contract():
    assert ev.parse_reply('{"signal": 0.1, "confidence": 0.5, "summary": "x"}')["signal"] == 0.1
    assert ev.parse_reply("```json\n{\"signal\": 0, \"confidence\": 1, \"summary\": \"x\"}\n```") is not None
    for bad in (None, "", "not json", '{"signal": "0.1", "confidence": 0.5, "summary": "x"}',
                '{"signal": true, "confidence": 0.5, "summary": "x"}', '{"signal": 0.1, "confidence": 0.5}'):
        assert ev.parse_reply(bad) is None


def test_kappa():
    assert ev.cohen_kappa([True, False, True, False], [True, False, True, False]) == pytest.approx(1.0)
    assert ev.cohen_kappa([True, False], [False, True]) == pytest.approx(-1.0)
    assert ev.cohen_kappa([True, True], [True, True]) is None
    assert ev.cohen_kappa([], []) is None
    # textbook example: 20/25 agreement, pa=0.6 pb=0.6 -> pe=0.52, kappa=(0.8-0.52)/0.48
    a = [True] * 13 + [False] * 2 + [True] * 2 + [False] * 8
    b = [True] * 13 + [True] * 2 + [False] * 2 + [False] * 8
    assert ev.cohen_kappa(a, b) == pytest.approx((0.84 - (0.6 * 0.6 + 0.4 * 0.4)) / (1 - 0.52), abs=1e-9)


def test_calibration_subset():
    cal = ev.load_calibration()
    assert len(cal) == 30 and len({r["cal_id"] for r in cal}) == 30
    assert all(r["item_id"] in BY_ID for r in cal)
    for c in ev.CRITERIA:                       # both verdicts present for every criterion
        assert {r["labels"][c] for r in cal} == {True, False}
    # The deterministic checker against the hand labels: fence and facts exact; numbers lose a
    # few whole-number coincidences (documented in eval_set; c25, c27). c05 agreed with its label
    # once the items were anonymised (v0.17 R0.2): its "8%" had been grounded by a price-level
    # coincidence that rebasing removed.
    det = {r["cal_id"]: ev.check_reply(BY_ID[r["item_id"]], r["reply"]) for r in cal}
    for c in ("used_facts", "respected_fence"):
        assert all(det[r["cal_id"]][c] == r["labels"][c] for r in cal)
    miss = sorted(r["cal_id"] for r in cal if det[r["cal_id"]]["no_invented_numbers"] != r["labels"]["no_invented_numbers"])
    assert miss == ["c25", "c27"]


def _ok_reply(system, prompt):
    return json.dumps({"signal": 0.1, "confidence": 0.5, "summary": "Neutral view.", "key_points": []})


def test_run_check_resume_and_smoke(tmp_path):
    out = tmp_path / "run.jsonl"
    llm = FakeLLM(_ok_reply)
    assert v16_eval.main(["run", "--limit", "5", "--out", str(out)], llm=llm) == 0
    assert llm.calls == 5 and llm.last_schema is contracts.ANALYST
    assert v16_eval.main(["run", "--limit", "7", "--out", str(out)], llm=llm) == 0
    assert llm.calls == 7                                    # resumed: only two new calls
    rows = [json.loads(x) for x in out.read_text().splitlines()]
    assert len(rows) == 7 and all(r["raw"] and r["parsed"] for r in rows)
    assert out.with_suffix(".meta.json").exists()
    chk = tmp_path / "check.json"
    assert v16_eval.main(["check", "--replies", str(out), "--out", str(chk)]) == 0
    s = json.loads(chk.read_text())["summary"]
    assert s["n"] == 7 and s["parsed"] == 7 and s["used_facts"] == 0
    # smoke: an unparseable reply gives exit 1, raw kept
    bad = FakeLLM(lambda s, p: "I think it goes up")
    sm = tmp_path / "smoke.jsonl"
    assert v16_eval.main(["run", "--smoke", "--out", str(sm)], llm=bad) == 1
    rows = [json.loads(x) for x in sm.read_text().splitlines()]
    assert len(rows) == 3 and rows[0]["raw"] == "I think it goes up" and rows[0]["parsed"] is None
    assert v16_eval.main(["check", "--smoke", "--replies", str(sm), "--out", str(tmp_path / "c.json")]) == 1


def test_run_records_exceptions(tmp_path):
    def boom(s, p):
        raise RuntimeError("down")
    out = tmp_path / "r.jsonl"
    assert v16_eval.main(["run", "--limit", "2", "--out", str(out)], llm=FakeLLM(boom)) == 0
    rows = [json.loads(x) for x in out.read_text().splitlines()]
    assert rows[0]["error"] == "RuntimeError: down" and rows[0]["parsed"] is None


def _oracle_judge(system, prompt):
    """A judge that returns the hand label of the calibration row whose reply is in the prompt."""
    for r in ev.load_calibration():
        if json.dumps(r["reply"]) in prompt:
            return json.dumps({**r["labels"], "reason": "oracle"})
    return "garbage"


def test_judge_and_agreement(tmp_path):
    jout = tmp_path / "judge.jsonl"
    llm = FakeLLM(_oracle_judge)
    assert v16_eval.main(["judge", "--calibration", "--out", str(jout)], llm=llm) == 0
    assert llm.calls == 30 and llm.last_schema is ev.JUDGE_SCHEMA
    assert v16_eval.main(["judge", "--calibration", "--out", str(jout)], llm=llm) == 0
    assert llm.calls == 30                                   # fully resumed
    aout = tmp_path / "agree.json"
    assert v16_eval.main(["agreement", "--judged", str(jout), "--out", str(aout)]) == 0
    res = json.loads(aout.read_text())
    assert res["n_scored"] == 30
    for c in ev.CRITERIA:
        assert res["criteria"][c]["judge_kappa"] == pytest.approx(1.0)
    assert res["criteria"]["no_invented_numbers"]["checker_agree"] == 28      # c05 agrees since R0.2
    # an unparseable judge is counted, and smoke fails on it
    j2 = tmp_path / "j2.jsonl"
    assert v16_eval.main(["judge", "--calibration", "--smoke", "--out", str(j2)],
                         llm=FakeLLM(lambda s, p: "nope")) == 1
    a2 = tmp_path / "a2.json"
    assert v16_eval.main(["agreement", "--smoke", "--judged", str(j2), "--out", str(a2)]) == 1
    assert json.loads(a2.read_text())["judge_unparseable"] == 3


def test_judge_prompt_keeps_reply_as_material():
    it = BY_ID["syn-news-01"]
    p = ev.judge_prompt(it, '{"summary": "x"}')
    assert "=== ANALYST PROMPT ===" in p and it["prompt"] in p and p.index("REPLY") > p.index(it["prompt"][:40])
    assert ev.parse_judge('{"used_facts": true, "no_invented_numbers": false, "respected_fence": true, "reason": "r"}')
    assert ev.parse_judge('{"used_facts": "yes"}') is None
    assert set(ev.JUDGE_SCHEMA["required"]) >= set(ev.CRITERIA)


def test_judge_on_run_replies(tmp_path):
    run = tmp_path / "run.jsonl"
    v16_eval.main(["run", "--limit", "3", "--out", str(run)], llm=FakeLLM(_ok_reply))
    j = tmp_path / "j.jsonl"
    judge = FakeLLM(lambda s, p: json.dumps({"used_facts": False, "no_invented_numbers": True,
                                              "respected_fence": True, "reason": "r"}))
    assert v16_eval.main(["judge", "--replies", str(run), "--out", str(j)], llm=judge) == 0
    assert judge.calls == 3
