"""v0.17 R3 evaluation credibility: cross-family judge, owner labelling kit, paraphrased
retrieval set with an overlap check, and the prompt-hash eval-regression gate. No model calls."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

from agentic_trader.agentic import eval_gate as eg
from agentic_trader.agentic import eval_set as ev
from agentic_trader.agentic import judge_kit as jk
from agentic_trader.agentic.question_overlap import lexical_overlap
from agentic_trader.agentic.research_rag import EVAL_DIR, evaluate_retrieval, load_eval_corpus, load_questions

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import v16_eval  # noqa: E402
import v17_label_kit  # noqa: E402

ITEMS = ev.load_items()
BY_ID = {it["id"]: it for it in ITEMS}


# ------------------------------------------------------------------ R3.1 (a) judge model
@pytest.mark.parametrize(
    "name,fam",
    [
        ("qwen2.5:7b-instruct", "qwen"),
        ("llama3.1:8b-instruct-q4_K_M", "llama"),
        ("phi3:mini", "phi"),
        ("hf.co/org/Qwen2.5-7B:Q4", "qwen"),
    ],
)
def test_model_family(name, fam):
    assert jk.model_family(name) == fam


def test_judge_defaults_to_other_family_and_refuses_same():
    assert jk.resolve_judge_model(None, None) == jk.DEFAULT_JUDGE_MODEL
    assert jk.model_family(jk.DEFAULT_JUDGE_MODEL) != jk.model_family(jk.DEFAULT_JUDGED_MODEL)
    with pytest.raises(jk.JudgeConfigError):
        jk.resolve_judge_model("qwen2.5:14b", "qwen2.5:7b-instruct")
    assert jk.resolve_judge_model("qwen2.5:14b", "qwen2.5:7b-instruct", allow_same_family=True) == "qwen2.5:14b"


class _Judge:
    def __init__(self):
        self.calls, self.model = 0, "fake"

    def complete_json(self, system, prompt, *, deep, schema):
        self.calls += 1
        return json.dumps({"used_facts": True, "no_invented_numbers": True, "respected_fence": True, "reason": "r"})


def test_cli_judge_refuses_same_family_and_records_models(tmp_path):
    # regression for B2: on v0.16 code the judge was --model, qwen2.5:7b by default, i.e. the judged model
    out = tmp_path / "j.jsonl"
    with pytest.raises(SystemExit):
        v16_eval.main(
            ["judge", "--calibration", "--limit", "2", "--judge-model", "qwen2.5:7b-instruct", "--out", str(out)], llm=_Judge()
        )
    assert v16_eval.main(["judge", "--calibration", "--limit", "2", "--out", str(out)], llm=_Judge()) == 0
    meta = json.loads(out.with_suffix(".meta.json").read_text())
    assert meta["judge_model"] == jk.DEFAULT_JUDGE_MODEL and meta["judged_model"] == jk.DEFAULT_JUDGED_MODEL


# ------------------------------------------------------------------ R3.1 (b) labelling kit
def _fixture_run(path: Path) -> dict[str, dict]:
    """A run JSONL over all 150 items with a mix of good, invented-number, fence-breaking and
    unparseable replies, so every checker stratum is populated."""
    rows = {}
    for k, it in enumerate(ITEMS):
        close = it["last_close"]
        fence = it["rubric"]["fence"]
        if k % 7 == 0:
            raw = "not json"
        elif fence and k % 3 == 0:
            raw = json.dumps(
                {
                    "signal": fence["demanded_signal"],
                    "confidence": 0.5,
                    "summary": f"{fence['canary']} close {close}",
                    "key_points": [],
                }
            )
        elif k % 4 == 0:
            raw = json.dumps({"signal": 0.1, "confidence": 0.5, "summary": f"Close {close}; target 98765.4.", "key_points": []})
        elif k % 5 == 0:
            raw = json.dumps({"signal": 0.0, "confidence": 0.3, "summary": "Mixed picture.", "key_points": []})
        else:
            raw = json.dumps({"signal": 0.1, "confidence": 0.5, "summary": f"Last close {close}.", "key_points": []})
        rows[it["id"]] = {"id": it["id"], "raw": raw, "parsed": ev.parse_reply(raw), "error": None}
    path.write_text("\n".join(json.dumps(r) for r in rows.values()) + "\n", encoding="utf-8")
    return rows


def test_sample_is_stratified_blind_and_deterministic(tmp_path):
    rows = _fixture_run(tmp_path / "run.jsonl")
    s1 = jk.sample_replies(ITEMS, rows, n=100)
    s2 = jk.sample_replies(ITEMS, rows, n=100)
    assert len(s1) == 100 and [r["item"]["id"] for r in s1] == [r["item"]["id"] for r in s2]
    assert len({r["item"]["id"] for r in s1}) == 100
    strata = {jk._verdict_key(r["checker"]) for r in s1}
    assert len(strata) >= 4
    # the rarest verdict pattern in the run is over-represented in the sample (equal shares)
    from collections import Counter

    run_c = Counter(jk._verdict_key(ev.check_reply(BY_ID[i], r["parsed"])) for i, r in rows.items())
    samp_c = Counter(jk._verdict_key(r["checker"]) for r in s1)
    rare = min(run_c, key=run_c.get)
    assert samp_c[rare] / 100 >= run_c[rare] / sum(run_c.values())


def test_sheet_import_and_kappa_roundtrip(tmp_path):
    _fixture_run(tmp_path / "run.jsonl")
    sheet = tmp_path / "sheet"
    assert v17_label_kit.main(["sheet", "--fixture", str(tmp_path / "run.jsonl"), "--out", str(sheet)]) == 0
    header = (sheet / "labels.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
    assert tuple(header) == jk.SHEET_COLUMNS and "checker" not in " ".join(header)  # blind
    assert "label_used_facts" in (sheet / "sheet.html").read_text(encoding="utf-8")
    key = json.loads((sheet / "key.json").read_text())
    assert key["source"].startswith("fixture:") and key["n"] == 100
    # the "owner" agrees with the checker except on used_facts for the first 10 rows; one blank
    kk = {r["row_id"]: r for r in key["rows"]}
    with (sheet / "labels.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for n, r in enumerate(rows):
        ch = kk[r["row_id"]]["checker"]
        for c in ev.CRITERIA:
            v = ch[c] if not (c == "used_facts" and n < 10) else not ch[c]
            r[f"label_{c}"] = "1" if v else "0"
    rows[0]["label_respected_fence"] = ""
    with (sheet / "labels.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=jk.SHEET_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    judged = tmp_path / "judge.jsonl"  # judge rows keyed by item id, as v16_eval judge --replies writes them
    judged.write_text(
        "\n".join(json.dumps({"id": r["item_id"], "verdict": {c: True for c in ev.CRITERIA}}) for r in key["rows"]),
        encoding="utf-8",
    )
    out, cal = tmp_path / "agree.json", tmp_path / "cal.json"
    assert (
        v17_label_kit.main(
            [
                "import",
                "--sheet",
                str(sheet),
                "--labeller",
                "test",
                "--judged",
                str(judged),
                "--out",
                str(out),
                "--calibration-out",
                str(cal),
                "--n-boot",
                "200",
            ]
        )
        == 0
    )
    rep = json.loads(out.read_text())
    assert rep["criteria"]["no_invented_numbers"]["checker"]["kappa"] == pytest.approx(1.0)
    uf = rep["criteria"]["used_facts"]["checker"]
    assert uf["agree"] == 90 and uf["kappa"] < 1.0 and uf["ci_low"] <= uf["kappa"] <= uf["ci_high"]
    assert rep["criteria"]["respected_fence"]["blank"] == 1
    assert rep["criteria"]["used_facts"]["judge"]["n"] == 100 and rep["judge_missing"] == 0
    rows_cal = json.loads(cal.read_text())["rows"]
    assert len(rows_cal) == 100 and {"cal_id", "item_id", "reply", "labels"} <= set(rows_cal[0])


def test_import_rejects_bad_cells_and_mismatched_rows(tmp_path):
    _fixture_run(tmp_path / "run.jsonl")
    sheet = tmp_path / "s"
    v17_label_kit.main(["sheet", "--fixture", str(tmp_path / "run.jsonl"), "--out", str(sheet), "--n", "5"])
    text = (sheet / "labels.csv").read_text(encoding="utf-8").splitlines()
    first = text[1].split(",")
    first[4] = "maybe"
    (sheet / "labels.csv").write_text("\n".join([text[0], ",".join(first)] + text[2:]), encoding="utf-8")
    with pytest.raises(ValueError):
        jk.import_sheet(sheet / "labels.csv", sheet / "key.json")
    first[4], first[1] = "1", "syn-macro-99"
    (sheet / "labels.csv").write_text("\n".join([text[0], ",".join(first)] + text[2:]), encoding="utf-8")
    with pytest.raises(ValueError):
        jk.import_sheet(sheet / "labels.csv", sheet / "key.json")


def test_sheet_from_real_run_needs_enough_replies(tmp_path):
    rows = _fixture_run(tmp_path / "run.jsonl")
    small = tmp_path / "small.jsonl"
    small.write_text("\n".join(json.dumps(r) for r in list(rows.values())[:20]), encoding="utf-8")
    assert v17_label_kit.main(["sheet", "--replies", str(small), "--out", str(tmp_path / "x")]) == 1


def test_kappa_bootstrap_bounds():
    a = [True] * 30 + [False] * 30
    b = [True] * 25 + [False] * 5 + [False] * 28 + [True] * 2
    r = jk.kappa_bootstrap(a, b, n_boot=500)
    assert r["ci_low"] <= r["kappa"] <= r["ci_high"] and r["agree"] == 53


# ------------------------------------------------------------------ R3.2 retrieval v2
def test_overlap_rule():
    p = "Net sales rose 14 percent to 2.1 billion dollars, driven by rocket-skate volumes."
    assert lexical_overlap("How much did ACME net sales grow last year?", p).rejected  # bigram net_sales
    assert lexical_overlap("rocket-skate volumes percent dollars", p).rejected  # containment
    assert not lexical_overlap("ACME top-line growth and what drove it", p).rejected


def test_v2_questions_shape_and_overlap():
    corpus = load_eval_corpus()
    v1, v2 = load_questions(EVAL_DIR / "questions.json"), load_questions(EVAL_DIR / "questions_v2.json")
    assert len(v2) == 100 and len({q.id for q in v2}) == 100
    assert {q.gold for q in v2} <= {q.gold for q in v1}  # gold kept
    assert {g for q in v2 for g in q.gold} == {g for q in v1 for g in q.gold}  # every gold covered
    for q in v2:
        assert not lexical_overlap(q.text, corpus.get(q.gold[0]).text).rejected, q.id
    # the old set is the problem the check is meant to catch
    assert sum(lexical_overlap(q.text, corpus.get(q.gold[0]).text).rejected for q in v1) >= 50


def test_v2_recorded_results_match():
    rec = json.loads(
        (Path(__file__).resolve().parents[1] / "docs" / "results" / "v17_retrieval" / "retrieval_v1_v2.json").read_text()
    )
    corpus = load_eval_corpus()
    for name, f in (("v1_fixture", "questions.json"), ("v2_paraphrased", "questions_v2.json")):
        qs = load_questions(EVAL_DIR / f)
        for r in rec["sets"][name]["reports"]:
            now = evaluate_retrieval(corpus, qs, r["method"])
            assert now.recall_at_5 == pytest.approx(r["recall_at_5"]) and now.mrr == pytest.approx(r["mrr"])


# ------------------------------------------------------------------ R3.3 eval-regression gate
def test_eval_regression_gate():
    """Fails when the prompt registry, the frozen items, the judge prompt or the checker's
    fixture results change without a deliberately re-recorded baseline. To update: re-run the eval
    on the new prompts, then ``python scripts/v17_eval_baseline.py --update --reason "..."``."""
    fails = eg.gate_failures(eg.current_record(), eg.load_baseline())
    assert not fails, "\n".join(fails + ["update deliberately: " + eg.UPDATE_HINT])


def test_gate_detects_prompt_hash_change_and_needs_reason(tmp_path, monkeypatch):
    base = eg.load_baseline()
    cur = eg.current_record()
    assert eg.gate_failures({**cur, "prompt_bundle_hash": "deadbeef"}, base)[0].startswith("prompt_bundle_hash")
    bad_checker = {**cur["checker"], "used_facts_pass": cur["checker"]["used_facts_pass"] - 1}
    assert eg.gate_failures({**cur, "checker": bad_checker}, base)
    p = tmp_path / "b.json"
    with pytest.raises(ValueError):
        eg.write_baseline("  ", p, cur)
    eg.write_baseline("first", p, cur)
    doc = eg.write_baseline("second", p, {**cur, "prompt_bundle_hash": "x"})
    assert doc["history"] == [{"prompt_bundle_hash": cur["prompt_bundle_hash"], "reason": "first"}]


def test_gate_sees_a_real_prompt_edit(monkeypatch):
    from agentic_trader.agents import analysts

    cls = analysts.ANALYSTS["technical"]
    before = eg.current_record()["prompt_bundle_hash"]
    monkeypatch.setattr(cls, "role", cls.role + " Be brief.")
    assert eg.current_record()["prompt_bundle_hash"] != before
