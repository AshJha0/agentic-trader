"""Run headers and per-row lineage for model studies (review 2026-11-09, N5 and N6).

Plain idea: every row a model study writes must say which code, which prompts, which server
and which weights produced it, and a resumed run must not quietly mix two of any of them.

Formally, a run header is a dict of identity fields

    git_sha, git_dirty, prompt_bundle_hash, ollama_version, model, model_digest, options

plus free ``extra`` fields. Its ``header_id`` is the first 16 hex characters of the sha256 of
the canonical JSON of the identity fields only (not the timestamp), so two starts of the same
code, prompts, server and weights get the same id. Every row is stamped with ``header_id``,
``git_sha``, ``model_digest`` and the sha256 of its own prompt (``prompt_sha256``).

Resume rule: the header file sits next to the rows (``<rows>.header.json``, one JSON object
per line, newest last). On start, the new header is compared with the newest stored one field
by field. Any difference in an identity field refuses the resume with the list of fields,
unless ``allow_version_change`` is set, in which case the change is appended to the header
file with ``allowed_change: true`` and the differing fields, so the mix is on the record.

Worked example: a chain resumes after ``ollama pull qwen2.5:7b-instruct`` fetched new weights
under the same tag. The served name still matches (``local_llm.served_matches``), but
``/api/tags`` now reports a different digest, so ``check_resume`` raises
``LineageMismatch(['model_digest'])`` and the run stops before writing a row.

Evidence class: design and unit tests against fake HTTP servers; no model has been run
through this module.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

IDENTITY_FIELDS = ("git_sha", "git_dirty", "prompt_bundle_hash", "ollama_version", "model",
                   "model_digest", "options")


class LineageMismatch(RuntimeError):
    """A resume would mix rows from different code, prompts, server or weights."""

    def __init__(self, fields: list[str], old: dict[str, Any], new: dict[str, Any]):
        self.fields = fields
        detail = "; ".join(f"{f}: {old.get(f)!r} -> {new.get(f)!r}" for f in fields)
        super().__init__(f"refusing to resume: run identity changed ({detail}). "
                         "Start a new output file, or pass --allow-version-change to record the "
                         "change and continue.")


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def prompt_sha256(system: str, prompt: str) -> str:
    """Hash of one model call's full input (system and user text, separated)."""
    return sha256_text((system or "") + "\x00" + (prompt or ""))


def header_id(header: dict[str, Any]) -> str:
    ident = {k: header.get(k) for k in IDENTITY_FIELDS}
    return sha256_text(json.dumps(ident, sort_keys=True, default=str))[:16]


def build_header(*, model: str | None, url: str | None, options: dict[str, Any] | None,
                 config: dict | None = None, prompt_hash: str | None = None,
                 git: Callable[[], tuple[str | None, bool | None]] | None = None,
                 version_fn: Callable[[str], str | None] | None = None,
                 digest_fn: Callable[[str, str], dict[str, Any] | None] | None = None,
                 extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Collect the run identity. Callables are injectable so tests use fakes; the defaults read
    git, ``prompts.prompt_bundle_hash(config)`` and the Ollama ``/api/version`` and ``/api/tags``
    endpoints. A rules-only run passes ``model=None`` and gets no server fields."""
    from .provenance import git_info
    sha, dirty = (git or git_info)()
    if prompt_hash is None and config is not None:
        from .prompts import prompt_bundle_hash
        prompt_hash = prompt_bundle_hash(config)
    version = digest = None
    entry: dict[str, Any] | None = None
    if model and url:
        from .local_llm import model_digest, server_version
        version = (version_fn or server_version)(url)
        entry = (digest_fn or model_digest)(url, model)
        digest = (entry or {}).get("digest")
    h: dict[str, Any] = {
        "git_sha": sha, "git_dirty": dirty, "prompt_bundle_hash": prompt_hash,
        "ollama_version": version, "model": model, "model_digest": digest,
        "options": dict(sorted((options or {}).items())),
        "model_entry": entry, "server_url": url,
        "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **(extra or {}),
    }
    h["header_id"] = header_id(h)
    return h


def header_path(rows_path: Path) -> Path:
    return Path(str(rows_path) + ".header.json")


def read_headers(rows_path: Path) -> list[dict[str, Any]]:
    p = header_path(rows_path)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def diff_fields(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    return [f for f in IDENTITY_FIELDS if old.get(f) != new.get(f)]


def check_resume(rows_path: Path, header: dict[str, Any], *, allow_version_change: bool = False,
                 rows_exist: bool | None = None) -> dict[str, Any]:
    """Write or verify the run header before any row is written; return the header in force.

    No stored header and no rows: the header is written (fresh run). No stored header but rows
    exist: the rows predate lineage; refused unless ``allow_version_change`` (then recorded as
    ``legacy_rows: true``). Stored header: identical identity resumes silently; a difference
    raises ``LineageMismatch`` unless allowed, in which case the new header is appended with
    ``allowed_change`` and the changed fields."""
    rows_path = Path(rows_path)
    if rows_exist is None:
        rows_exist = rows_path.exists() and rows_path.stat().st_size > 0
    stored = read_headers(rows_path)
    hp = header_path(rows_path)
    hp.parent.mkdir(parents=True, exist_ok=True)
    if not stored:
        if rows_exist and not allow_version_change:
            raise LineageMismatch(["header (rows written before lineage existed)"], {}, header)
        rec = {**header, **({"legacy_rows": True, "allowed_change": True} if rows_exist else {})}
        _append(hp, rec)
        return rec
    last = stored[-1]
    changed = diff_fields(last, header)
    if not changed:
        return last
    if not allow_version_change:
        raise LineageMismatch(changed, last, header)
    rec = {**header, "allowed_change": True, "changed_fields": changed, "previous_header_id": last.get("header_id")}
    _append(hp, rec)
    return rec


def _append(path: Path, rec: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")


def stamp(row: dict[str, Any], header: dict[str, Any]) -> dict[str, Any]:
    """Add the lineage fields every row carries (in place; returns the row)."""
    row["header_id"] = header.get("header_id")
    row["git_sha"] = header.get("git_sha")
    row["model_digest"] = header.get("model_digest")
    return row


def call_lineage(system: str, prompt: str, evidence: dict[str, Any] | None) -> dict[str, Any]:
    """Per-call fields (N4, N5): prompt hash and the server's token counts and truncation flag
    (``LocalLLM.last_call``; ``None`` for backends that do not report them)."""
    ev = evidence or {}
    return {"prompt_sha256": prompt_sha256(system, prompt), "prompt_eval_count": ev.get("prompt_eval_count"),
            "eval_count": ev.get("eval_count"), "truncated": ev.get("truncated")}


def swapped_digest(header: dict[str, Any], url: str | None,
                   digest_fn: Callable[[str, str], dict[str, Any] | None] | None = None) -> str | None:
    """Mid-run model-swap check: the digest now served for ``header['model']`` when it differs
    from the header's, else ``None``. A study calls this every N rows and stops on a swap."""
    model = header.get("model")
    if not model or not url:
        return None
    from .local_llm import model_digest
    entry = (digest_fn or model_digest)(url, model)
    now = (entry or {}).get("digest")
    return now if now != header.get("model_digest") else None


# ---- N6: data vintage and per-row market fields ----------------------------------------------

def vintage_hash(close: Any) -> str:
    """sha256 (16 hex) of a close series as fetched (index dates and values to 10 significant
    digits). Two fetches of the same name with different dividend re-adjustment give different
    hashes, so rows from different vintages are not silently spliced."""
    pairs = close.items() if hasattr(close, "items") else enumerate(close)
    items = [(str(i)[:10], f"{float(v):.10g}") for i, v in pairs]
    return sha256_text(json.dumps(items))[:16]


# How rows written before N6 are handled (quoted by reports; see docs/review/v017_notes/L10).
LEGACY_ROW_POLICY = (
    "Rows without horizon_days / vintage_hash predate v0.17 N6. They are not spliced with "
    "forward closes from a later fetch: the report re-fetches each name once, recomputes both "
    "the entry close and the forward close from that single vintage (ignoring the stored "
    "close), and takes the horizon from the stored trader reply for model cells or recomputes "
    "it with the rules for rule cells. Such rows are labelled 'legacy (single re-fetched "
    "vintage)' in every table.")


def market_lineage(history: Any, proposal: Any | None) -> dict[str, Any]:
    """The N6 row fields: horizon in bars, entry bar date, as-of close and the data vintage."""
    close = history["Close"]
    return {"horizon_days": int(getattr(proposal, "horizon_days", 0) or 0) or None,
            "entry_bar_date": str(close.index[-1].date()) if hasattr(close.index[-1], "date") else str(close.index[-1]),
            "asof_close": float(close.iloc[-1]), "vintage_hash": vintage_hash(close)}


def row_vintage_status(row: dict[str, Any]) -> str:
    return "current" if row.get("vintage_hash") else "legacy"


__all__ = ["IDENTITY_FIELDS", "LineageMismatch", "build_header", "call_lineage", "check_resume", "header_id",
           "header_path", "read_headers", "stamp", "swapped_digest", "prompt_sha256", "sha256_text",
           "vintage_hash", "market_lineage", "row_vintage_status", "LEGACY_ROW_POLICY"]
