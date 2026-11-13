"""v0.16 analyst eval (PLAN.md 2.7): run, check, judge and agreement over the frozen eval set.

The set is 150 frozen (state, rubric) items in ``agentic_trader/agentic/knowledge/eval_set/``;
the criteria and the exact number-matching rule are in ``agentic_trader/agentic/eval_set.py``.
Model calls go to a local Ollama model only ($0); ``check`` and ``agreement`` call no model.

    python scripts/v16_eval.py run       --model qwen2.5:7b-instruct --out results/v16_eval/run.jsonl
    python scripts/v16_eval.py check     --replies results/v16_eval/run.jsonl --out results/v16_eval/check.json
    python scripts/v16_eval.py judge     --replies results/v16_eval/run.jsonl --out results/v16_eval/judge.jsonl
        (v0.17: the judge is --judge-model, default llama3.1:8b-instruct-q4_K_M; a judge from the
        --judged-model family is refused unless --allow-same-family)
    python scripts/v16_eval.py judge     --calibration --out results/v16_eval/judge_calibration.jsonl
    python scripts/v16_eval.py agreement --judged results/v16_eval/judge_calibration.jsonl --out results/v16_eval/agreement.json
    python scripts/v16_eval.py freeze    # regenerate the frozen items (deliberately, never to pass a test)

Every subcommand takes ``--limit N`` and ``--smoke`` (3 items; exit 1 when any reply is
unparseable). ``run`` and ``judge`` write one JSONL row per item as soon as it is answered (raw
reply kept) and a rerun resumes from the rows already in ``--out``.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentic_trader import contracts  # noqa: E402
from agentic_trader.agentic import eval_set as ev  # noqa: E402

JSON_SUFFIX = "\n\nRespond with a single JSON object only (no prose outside it)."


def make_llm(a: argparse.Namespace):
    from agentic_trader.local_llm import LocalLLM, reachable
    cfg = {"llm_provider": "local", "local_llm_model": a.model, "local_llm_timeout_s": a.timeout,
           "local_llm_seed": 7, "max_tokens": a.max_tokens}
    llm = LocalLLM(cfg)
    if not reachable(llm.url):
        raise SystemExit("no Ollama server at 127.0.0.1:11434")
    return llm


def _n(a: argparse.Namespace) -> int:
    return 3 if a.smoke else a.limit


def _read_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows[r["id"]] = r
    return rows


def _checkpointed(out: Path, todo: list[dict[str, Any]], answer, label: str) -> dict[str, dict[str, Any]]:
    """Append one row per item to ``out`` as soon as it is answered; skip ids already there."""
    out.parent.mkdir(parents=True, exist_ok=True)
    done = _read_jsonl(out)
    t0 = time.time()
    with out.open("a", encoding="utf-8") as f:
        for it in todo:
            if it["id"] in done:
                continue
            row = answer(it)
            done[it["id"]] = row
            f.write(json.dumps(row, default=str) + "\n")
            f.flush()
            print(f"{label} {len(done)}/{len(todo)} {time.time() - t0:.0f}s", flush=True)
    return done


def _items(a: argparse.Namespace) -> list[dict[str, Any]]:
    items = ev.load_items(Path(a.items)) if a.items else ev.load_items()
    n = _n(a)
    return items[:n] if n else items


def _write_meta(out: Path, llm, extra: dict[str, Any]) -> None:
    meta = {"run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), **extra}
    if llm is not None:
        meta.update(model=getattr(llm, "model", None), calls=getattr(llm, "calls", None),
                    usage=llm.usage.summary() if hasattr(llm, "usage") else None,
                    note="local open-weight model, $0; a floor for a small model, not Claude")
    out.with_suffix(".meta.json").write_text(json.dumps(meta, indent=1, default=str), encoding="utf-8")


def cmd_run(a: argparse.Namespace, llm=None) -> int:
    llm = llm or make_llm(a)
    items = _items(a)
    out = Path(a.out)

    def answer(it):
        err = None
        try:
            raw = llm.complete_json(it["system"], it["prompt"] + JSON_SUFFIX, deep=False, schema=contracts.ANALYST)
        except Exception as e:  # noqa: BLE001 - recorded, never substituted
            raw, err = None, f"{type(e).__name__}: {e}"
        return {"id": it["id"], "raw": raw, "parsed": ev.parse_reply(raw), "error": err}

    done = _checkpointed(out, items, answer, "run")
    _write_meta(out, llm, {"subcommand": "run", "n": len(items)})
    bad = [i["id"] for i in items if done[i["id"]]["parsed"] is None]
    print(json.dumps({"n": len(items), "unparseable": len(bad)}))
    return 1 if a.smoke and bad else 0


def check_rows(items: list[dict[str, Any]], replies: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for it in items:
        if it["id"] not in replies:
            continue
        rep = replies[it["id"]]
        parsed = rep.get("parsed") if "parsed" in rep else ev.parse_reply(rep.get("raw"))
        v = ev.check_reply(it, parsed)
        rows.append({"id": it["id"], "role": it["role"], "source": it["source"],
                     "fenced_injection": bool(it["rubric"]["fence"]), **v})
    n = len(rows)
    fenced = [r for r in rows if r["fenced_injection"]]
    summary = {"n": n, "parsed": sum(r["parsed"] for r in rows),
               "used_facts": sum(r["used_facts"] for r in rows),
               "no_invented_numbers": sum(r["no_invented_numbers"] for r in rows),
               "fenced_items": len(fenced), "respected_fence": sum(r["respected_fence"] for r in fenced),
               "all_three": sum(r["used_facts"] and r["no_invented_numbers"] and r["respected_fence"] for r in rows)}
    return {"summary": summary, "rows": rows}


def cmd_check(a: argparse.Namespace, llm=None) -> int:
    items = _items(a)
    replies = _read_jsonl(Path(a.replies))
    res = check_rows(items, replies)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps(res["summary"]))
    return 1 if a.smoke and res["summary"]["parsed"] < res["summary"]["n"] else 0


def _calibration_targets(a: argparse.Namespace) -> list[dict[str, Any]]:
    """(item, reply) pairs to judge: calibration rows, or the replies of a ``run``."""
    by_id = {it["id"]: it for it in ev.load_items()}
    if a.calibration:
        rows = ev.load_calibration()
        pairs = [{"id": r["cal_id"], "item": by_id[r["item_id"]], "raw": json.dumps(r["reply"])} for r in rows]
    else:
        reps = _read_jsonl(Path(a.replies))
        pairs = [{"id": i, "item": by_id[i], "raw": r.get("raw")} for i, r in reps.items() if i in by_id]
    n = _n(a)
    return pairs[:n] if n else pairs


def cmd_judge(a: argparse.Namespace, llm=None) -> int:
    from agentic_trader.agentic.judge_kit import JudgeConfigError, resolve_judge_model
    try:   # v0.17 R3.1: judge from another model family than the judged one (self-preference)
        a.model = resolve_judge_model(a.judge_model, a.judged_model, a.allow_same_family)
    except JudgeConfigError as e:
        raise SystemExit(str(e)) from e
    llm = llm or make_llm(a)
    pairs = _calibration_targets(a)
    out = Path(a.out)

    def answer(p):
        err = None
        try:
            raw = llm.complete_json(ev.JUDGE_SYSTEM, ev.judge_prompt(p["item"], p["raw"]), deep=False,
                                    schema=ev.JUDGE_SCHEMA)
        except Exception as e:  # noqa: BLE001
            raw, err = None, f"{type(e).__name__}: {e}"
        return {"id": p["id"], "item_id": p["item"]["id"], "raw": raw, "verdict": ev.parse_judge(raw), "error": err}

    done = _checkpointed(out, pairs, answer, "judge")
    _write_meta(out, llm, {"subcommand": "judge", "n": len(pairs), "calibration": bool(a.calibration),
                           "judge_model": a.model, "judged_model": a.judged_model})
    bad = [p["id"] for p in pairs if done[p["id"]]["verdict"] is None]
    print(json.dumps({"n": len(pairs), "unparseable": len(bad)}))
    return 1 if a.smoke and bad else 0


def agreement(judged: dict[str, dict[str, Any]], calibration: list[dict[str, Any]]) -> dict[str, Any]:
    """Cohen's kappa per criterion: judge vs human labels, and deterministic checker vs human
    labels, over the calibration rows the judge answered (unparseable judge rows are counted and
    excluded)."""
    by_id = {it["id"]: it for it in ev.load_items()}
    out: dict[str, Any] = {"n_calibration": len(calibration), "judge_unparseable": 0, "criteria": {}}
    pairs = []
    for r in calibration:
        j = judged.get(r["cal_id"])
        if j is None:
            continue
        if j.get("verdict") is None:
            out["judge_unparseable"] += 1
            continue
        pairs.append((r, j["verdict"], ev.check_reply(by_id[r["item_id"]], r["reply"])))
    out["n_scored"] = len(pairs)
    for c in ev.CRITERIA:
        human = [bool(r["labels"][c]) for r, _, _ in pairs]
        judge = [bool(v[c]) for _, v, _ in pairs]
        det = [bool(d[c]) for _, _, d in pairs]
        out["criteria"][c] = {
            "judge_kappa": ev.cohen_kappa(judge, human), "judge_agree": sum(x == y for x, y in zip(judge, human)),
            "checker_kappa": ev.cohen_kappa(det, human), "checker_agree": sum(x == y for x, y in zip(det, human)),
            "n": len(pairs)}
    return out


def cmd_agreement(a: argparse.Namespace, llm=None) -> int:
    cal = ev.load_calibration()
    n = _n(a)
    cal = cal[:n] if n else cal
    judged = _read_jsonl(Path(a.judged))
    res = agreement(judged, cal)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps(res, indent=1, default=str))
    return 1 if a.smoke and (res["judge_unparseable"] or res["n_scored"] < len(cal)) else 0


def cmd_freeze(a: argparse.Namespace, llm=None) -> int:
    items = ev.build_items()
    ev.freeze(items, Path(a.out) if a.out else ev.ITEMS_PATH)
    print(f"froze {len(items)} items")
    return 0


def main(argv: list[str] | None = None, llm=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (("run", cmd_run), ("check", cmd_check), ("judge", cmd_judge),
                     ("agreement", cmd_agreement), ("freeze", cmd_freeze)):
        s = sub.add_parser(name)
        s.add_argument("--out", required=name != "freeze", default=None)
        s.add_argument("--limit", type=int, default=0)
        s.add_argument("--smoke", action="store_true", help="3 items; exit 1 if any reply is unparseable")
        s.add_argument("--items", default=None, help="items JSON (default: the frozen set)")
        s.add_argument("--model", default="qwen2.5:7b-instruct")
        s.add_argument("--timeout", type=float, default=300)
        s.add_argument("--max-tokens", type=int, default=1024)
        s.add_argument("--replies", default=None, help="check/judge: JSONL from run")
        s.add_argument("--calibration", action="store_true", help="judge: the human-labelled calibration rows")
        s.add_argument("--judged", default=None, help="agreement: JSONL from judge --calibration")
        if name == "judge":
            from agentic_trader.agentic.judge_kit import DEFAULT_JUDGE_MODEL, DEFAULT_JUDGED_MODEL
            s.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL, help="judge model (other family)")
            s.add_argument("--judged-model", default=DEFAULT_JUDGED_MODEL, help="model that wrote the replies")
            s.add_argument("--allow-same-family", action="store_true", help="permit a same-family judge")
        s.set_defaults(fn=fn)
    a = p.parse_args(argv)
    if a.cmd in ("check",) and not a.replies:
        p.error("check needs --replies")
    if a.cmd == "judge" and not (a.replies or a.calibration):
        p.error("judge needs --replies or --calibration")
    if a.cmd == "agreement" and not a.judged:
        p.error("agreement needs --judged")
    return a.fn(a, llm)


if __name__ == "__main__":
    raise SystemExit(main())
