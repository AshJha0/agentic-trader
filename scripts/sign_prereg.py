"""Sign the v0.16 pre-registration (the owner runs this; nobody else).

Plain idea. The pre-registration is a draft until the owner signs it, and the study runner
refuses to start a registered cell while it is a draft (``study_design.prereg_gate``). Signing
is one command and one commit:

    python scripts/sign_prereg.py --signer "Your Name"
    git add -A
    git commit -m "Sign the v0.16 pre-registration"

What the command does: renames ``docs/evaluation/v16_preregistration_DRAFT.md`` to
``v16_preregistration.md``, removes "DRAFT" from the title, sets the status line, fills the
signing block (signer, date, model digest, runner commit, registered trial count) and points
the links in the top-level documents at the new name. It changes no rule and commits nothing;
read the diff before you commit. The commit is the signature: its hash and time are what a
reader checks against the first ``decisive_ta`` row.

It refuses when the signed file already exists, when the working tree has other uncommitted
changes (so the signing commit holds the signature and nothing else), or when a ``decisive_ta``
or ``postcutoff_ta`` rows file is found next to the first-pass rows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentic_trader.study_design import DESIGN_CELLS, PREREG_DRAFT, PREREG_SIGNED  # noqa: E402

# Documents whose links follow the rename. Review notes and the changelog are history and keep
# the old name.
LINKING_DOCS = ("README.md", "LEARN.md", "COOKBOOK.md", "docs/ai/ai.md", "docs/index.html",
                "docs/learn/ai_learning_path.md", "docs/evaluation/v16_prereg_amendment_2026-11-12.md")
TITLE_DRAFT = "# v0.16 pre-registration (DRAFT):"
STATUS_DRAFT = "**Status: draft, not signed, not executed.**"
BINDING_DRAFT = "This draft becomes binding only when the owner signs it:"
DEFAULT_HEADER = "results/v17_local/first_pass.jsonl.header.json"


class SigningRefused(RuntimeError):
    pass


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def sign(root: Path, signer: str, on: date, model_digest: str, commit: str, trials: int, *,
         use_git: bool = True) -> dict[str, str]:
    """Write the signed document under ``root`` and return ``{"path", "sha256"}``."""
    draft, signed = root / PREREG_DRAFT, root / PREREG_SIGNED
    if signed.exists():
        raise SigningRefused(f"{PREREG_SIGNED} already exists: the pre-registration is signed")
    if not signer.strip():
        raise SigningRefused("--signer is empty")
    if len(model_digest) < 12:
        raise SigningRefused("the model digest is missing or too short to identify a build")
    text = draft.read_text(encoding="utf-8")
    edits = [
        (TITLE_DRAFT, "# v0.16 pre-registration:"),
        (STATUS_DRAFT, f"**Status: signed by {signer} on {on.isoformat()}; binding from the commit that adds "
                       "this file.**"),
        (BINDING_DRAFT, "It was a draft until the owner signed it:"),
        ("Filled by `python scripts/sign_prereg.py` when the owner signs; empty in the draft.",
         "Filled by `python scripts/sign_prereg.py` at signing."),
        ("- Signed by: (not signed)", f"- Signed by: {signer}"),
        ("- Signed on: (not signed)", f"- Signed on: {on.isoformat()}"),
        ("digest (filled at signing from the first-pass run header)", f"digest `{model_digest}`"),
        ("- Runner code at signing: (git commit, filled at signing)", f"- Runner code at signing: `{commit}`"),
        ("`len(evaluation.TRIALS)`: (filled at signing)", f"`len(evaluation.TRIALS)`: {trials}"),
    ]
    for old, new in edits:
        if text.count(old) != 1:
            raise SigningRefused(f"expected exactly one {old!r} in the draft; found {text.count(old)}")
        text = text.replace(old, new)
    if use_git:
        _git(root, "mv", PREREG_DRAFT, PREREG_SIGNED)
    else:
        draft.unlink()
    signed.write_text(text, encoding="utf-8", newline="\n")
    old_name, new_name = Path(PREREG_DRAFT).name, Path(PREREG_SIGNED).name
    for rel in LINKING_DOCS:
        doc = root / rel
        if doc.is_file():
            body = doc.read_text(encoding="utf-8")
            if old_name in body:
                doc.write_text(body.replace(old_name, new_name), encoding="utf-8", newline="\n")
    return {"path": PREREG_SIGNED, "sha256": hashlib.sha256(signed.read_bytes()).hexdigest()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sign the v0.16 pre-registration (owner only).")
    ap.add_argument("--signer", required=True, help="your name as it should appear in the document")
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--model-digest", help="digest of the model build; default: read from --header")
    ap.add_argument("--header", default=DEFAULT_HEADER, help="first-pass run header with the served model digest")
    a = ap.parse_args(argv)
    try:
        if _git(ROOT, "status", "--porcelain"):
            raise SigningRefused("the working tree has uncommitted changes; commit or stash them first, so the "
                                 "signing commit holds only the signature")
        digest = a.model_digest
        if not digest:
            hp = ROOT / a.header
            if not hp.is_file():
                raise SigningRefused(f"no run header at {a.header}; pass --model-digest (see `ollama list`)")
            digest = str(json.loads(hp.read_text(encoding="utf-8")).get("model_digest") or "")
        for cell in DESIGN_CELLS:
            rows = (ROOT / a.header).parent / f"{cell.name}.jsonl"
            if rows.is_file() and rows.stat().st_size:
                raise SigningRefused(f"{rows} already has rows: this cell ran before the signature. Do not sign "
                                     "over it; record what happened in the document first.")
        from agentic_trader.evaluation import TRIALS
        res = sign(ROOT, a.signer, date.fromisoformat(a.date), digest, _git(ROOT, "rev-parse", "HEAD"), len(TRIALS))
    except (SigningRefused, subprocess.CalledProcessError) as e:
        print(f"not signed: {e}", file=sys.stderr)
        return 2
    print(f"signed: {res['path']}\nsha256: {res['sha256']}\n\nRead the diff (git diff --staged; git diff), then:\n"
          '  git add -A\n  git commit -m "Sign the v0.16 pre-registration"\n'
          "The hash changes if the file is edited again before the commit; the runner records the hash it finds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
