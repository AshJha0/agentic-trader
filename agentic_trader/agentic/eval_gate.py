"""Eval-regression gate tied to the prompt registry (v0.17 R3.3, review finding C1).

Plain idea: a prompt change can make the analysts worse without any test noticing, because the
model is not called in CI. The gate pins the prompt-registry bundle hash to a recorded baseline
of deterministic eval results. If the hash changes and the baseline was not re-recorded on
purpose, CI fails. Re-recording is one command and leaves a reason in the file, so a prompt
change always arrives with a visible eval record.

What is recorded (``knowledge/eval_set/eval_baseline.json``):

* ``prompt_bundle_hash`` -- ``prompts.prompt_bundle_hash(make_config(memory_path=None))``.
* ``items_sha256`` -- the frozen 150-item eval set (its prompts are rendered from the agents, so
  a prompt edit that reaches the analysts also changes this file once it is re-frozen).
* ``judge_prompt_sha256`` -- the judge system prompt and a rendered judge prompt template.
* ``checker`` -- the deterministic checker's verdict counts on the recorded calibration replies
  and its agreement counts with their labels. These are fixtures, so the numbers are exact.

Update deliberately with ``python scripts/v17_eval_baseline.py --update --reason "..."`` after
re-running the eval on the new prompts (``scripts/v16_eval.py run/check`` with a local model);
the reason should name that run. No model is called here.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import eval_set as ev

BASELINE_PATH = ev.EVAL_DIR / "eval_baseline.json"
GATED_KEYS = ("prompt_bundle_hash", "items_sha256", "judge_prompt_sha256", "checker")
UPDATE_HINT = 'python scripts/v17_eval_baseline.py --update --reason "<what changed and which eval run checked it>"'


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def current_record(items_path: Path = ev.ITEMS_PATH, calibration_path: Path = ev.CALIBRATION_PATH) -> dict[str, Any]:
    from .. import make_config
    from ..prompts import prompt_bundle_hash
    items = ev.load_items(items_path)
    by_id = {it["id"]: it for it in items}
    cal = ev.load_calibration(calibration_path)
    verdicts = [(r, ev.check_reply(by_id[r["item_id"]], r["reply"])) for r in cal]
    checker = {"n": len(verdicts)}
    for c in ev.CRITERIA:
        checker[f"{c}_pass"] = sum(bool(v[c]) for _, v in verdicts)
        checker[f"{c}_agree_with_labels"] = sum(bool(v[c]) == bool(r["labels"][c]) for r, v in verdicts)
    judge_sample = ev.judge_prompt({"prompt": "<PROMPT>"}, "<REPLY>")
    return {"prompt_bundle_hash": prompt_bundle_hash(make_config(memory_path=None)),
            "items_sha256": _sha(items_path.read_bytes().replace(b"\r\n", b"\n")),
            "judge_prompt_sha256": _sha((ev.JUDGE_SYSTEM + "\n" + judge_sample).encode("utf-8")),
            "checker": checker}


def load_baseline(path: Path = BASELINE_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def gate_failures(current: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    """Human-readable mismatches between the current record and the baseline (empty = pass)."""
    out = []
    for k in GATED_KEYS:
        if current.get(k) != baseline.get(k):
            out.append(f"{k}: baseline {baseline.get(k)!r} != current {current.get(k)!r}")
    return out


def write_baseline(reason: str, path: Path = BASELINE_PATH, record: dict[str, Any] | None = None) -> dict[str, Any]:
    if not reason or not reason.strip():
        raise ValueError("a non-empty reason is required to re-record the eval baseline")
    rec = record or current_record()
    old = load_baseline(path) if path.exists() else {}
    history = list(old.get("history", []))
    if old:
        history.append({k: old.get(k) for k in ("prompt_bundle_hash", "reason")})
    doc = {"_note": "Eval-regression gate baseline (v0.17 R3.3). Re-record only with " + UPDATE_HINT,
           **rec, "reason": reason.strip(), "history": history}
    path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return doc
