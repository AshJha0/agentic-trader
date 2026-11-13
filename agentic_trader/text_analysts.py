"""LLM text analysts over filings and macro text (PLAN.md 3.8).

Two analysts, both structured-output and both fenced:

* ``FundamentalsTextAnalyst`` reads EDGAR sections (``data.edgar_text.FilingSection``) and
  returns claims, each citing the accession and section it came from and quoting the words
  that support it. A claim whose quote is not found verbatim in the cited section is dropped
  (a model cannot cite what it was not shown), and a claim citing a section it was not given
  is dropped too. Since Round 1 (A7) a quote must also have at least three words, twelve
  characters and one content word; a repeated quote is dropped and at most twelve claims count.
* ``MacroTextAnalyst`` reads central-bank or macro text and returns a hawkish/dovish stance
  and a shift in [-1, 1] against the previous text, with cited quotes checked the same way. A
  shift that is not a finite number in [-1, 1] is rejected, not clipped (A8).

Prompt budget (A11). The fundamentals prompt is held to ``max_prompt_tokens`` (default
``DEFAULT_FUNDAMENTALS_PROMPT_TOKENS``), counted with the deterministic, conservative
``llm.estimate_tokens`` over the system and user prompt (no tokeniser, no API call). Sections
are admitted newest first until the next one would not fit; the rest are left out, and the
cut is recorded (``TextAnalysis.budget``, then ``facts["prompt_budget"]`` in the report). A
reply whose backend says the server truncated the prompt (``last_call["truncated"]``) is
rejected with a logged reason, and the report abstains, so the desk runs on its rules analysts.

The model never computes a number the rules can compute: it reads and cites. Every input text
is third-party and goes into the prompt inside an ``<untrusted_data>`` block.

Backends: any object with ``complete_json(system, prompt, *, deep, schema)``. In this repo
that is ``local_llm.LocalLLM`` (Ollama, $0) for the P2 cells, or ``FixtureLLM`` replaying
recorded replies in tests. Claude variants are dry-run only: ``dry_run`` builds the exact
request and its size and makes no call.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Iterable

from .state import FENCE_NOTE, untrusted_block

log = logging.getLogger(__name__)

FUNDAMENTALS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "claims": {"type": "array", "items": {
            "type": "object",
            "properties": {"claim": {"type": "string"}, "direction": {"type": "string",
                                                                        "enum": ["positive", "negative", "neutral"]},
                           "accession": {"type": "string"}, "section": {"type": "string"},
                           "quote": {"type": "string"}},
            "required": ["claim", "direction", "accession", "section", "quote"]}},
    },
    "required": ["claims"],
}
MACRO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "stance": {"type": "string", "enum": ["hawkish", "dovish", "neutral"]},
        "shift": {"type": "number", "minimum": -1, "maximum": 1},
        "quotes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["stance", "shift", "quotes"],
}

FUNDAMENTALS_SYSTEM = ("You are a fundamentals analyst reading company filings. Return claims about the "
                       "business, each with the accession and section it comes from and a short verbatim "
                       "quote (under 30 words) that supports it. Do not compute numbers. " + FENCE_NOTE)
MACRO_SYSTEM = ("You are a macro analyst. Classify the central-bank text as hawkish, dovish or neutral and give "
                "the shift in [-1, 1] versus the previous text (positive = more hawkish), with short verbatim "
                "quotes that support it. " + FENCE_NOTE)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


@dataclass
class TextAnalysis:
    analyst: str
    ok: bool
    result: dict[str, Any] = field(default_factory=dict)
    dropped: list[dict[str, Any]] = field(default_factory=list)
    untrusted: bool = True
    problem: str | None = None
    budget: dict[str, Any] | None = None    # A11: the prompt budget and what it left out


class FixtureLLM:
    """Replays recorded replies keyed by the sha256 of (system, prompt); an unknown request
    returns None (the analyst then reports no result). ``record`` adds a reply."""

    def __init__(self, replies: dict[str, str] | None = None):
        self.replies = dict(replies or {})
        self.calls = 0

    @staticmethod
    def key(system: str, prompt: str) -> str:
        return hashlib.sha256((system + "\x00" + prompt).encode("utf-8")).hexdigest()

    def record(self, system: str, prompt: str, reply: str) -> None:
        self.replies[self.key(system, prompt)] = reply

    def complete(self, system: str, prompt: str, *, deep: bool) -> str | None:
        self.calls += 1
        return self.replies.get(self.key(system, prompt))

    def complete_json(self, system: str, prompt: str, *, deep: bool, schema: dict[str, Any]) -> str | None:
        return self.complete(system, prompt, deep=deep)


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-finite JSON constant {name}")


def _parse(reply: str | None) -> dict[str, Any] | None:
    """The reply as a dict, or None. ``NaN``/``Infinity`` constants are a rejection (A8):
    plain ``json.loads`` accepts them, and ``max(-1, min(1, nan))`` is 1.0 in Python."""
    if not reply:
        return None
    try:
        d = json.loads(reply, parse_constant=_reject_constant)
    except ValueError:      # JSONDecodeError is a ValueError
        return None
    return d if isinstance(d, dict) else None


# Round 1 (A7): what a cited quote must be before it counts. Twenty claims each quoting "the"
# used to pass the substring check and drive the signal to +1.
MIN_QUOTE_WORDS = 3
MIN_QUOTE_CHARS = 12
MAX_CLAIMS = 12
# A11: the fundamentals prompt budget in estimated tokens (llm.estimate_tokens, which is
# conservative). 6,000 leaves room for the schema and the reply in the 8,192-token local window.
DEFAULT_FUNDAMENTALS_PROMPT_TOKENS = 6000
_STOPWORDS = frozenset("""
a an the of to and or is are was were be been being this that these those it its on in at for with by
as from has have had not no but if then than so such can may might will would should could do does did
we our us you your they their them he she his her which who whom what when where while there here
""".split())


def quote_problem(quote: str) -> str | None:
    """Why a normalised quote cannot support a claim, or None when it can: at least
    ``MIN_QUOTE_WORDS`` words and ``MIN_QUOTE_CHARS`` characters, and one content token (a word
    of four or more letters that is not a stop word)."""
    words = re.findall(r"[a-z0-9%$.'-]+", quote)
    if len(words) < MIN_QUOTE_WORDS or len(quote) < MIN_QUOTE_CHARS:
        return f"quote shorter than {MIN_QUOTE_WORDS} words / {MIN_QUOTE_CHARS} characters"
    if not any(len(re.sub(r"[^a-z]", "", w)) >= 4 and w not in _STOPWORDS for w in words):
        return "quote has no content word"
    return None


class FundamentalsTextAnalyst:
    name = "fundamentals_text"
    system = FUNDAMENTALS_SYSTEM
    schema = FUNDAMENTALS_SCHEMA

    def __init__(self, llm: Any, max_chars_per_section: int = 6000, anon: Any = None,
                 max_prompt_tokens: int = DEFAULT_FUNDAMENTALS_PROMPT_TOKENS):
        if max_prompt_tokens <= 0:
            raise ValueError("max_prompt_tokens must be positive")
        self.llm = llm
        self.max_chars = max_chars_per_section
        self.anon = anon     # anonymize.Anonymizer (None = prompts carry real names and dates)
        self.max_prompt_tokens = int(max_prompt_tokens)

    def _t(self, text: str) -> str:
        return self.anon.scrub_text(text) if self.anon is not None else text

    def prompt(self, symbol: str, sections: Iterable[Any]) -> str:
        """The user prompt. With ``anon`` set the company line, accession numbers (which carry
        the CIK), acceptance times and the filing text itself go through ``scrub_text``."""
        blocks = [untrusted_block(self._t(f"EDGAR {s.form} accession={s.accession} section={s.section} "
                                          f"accepted={s.visible_date.isoformat()}"),
                                  [self._t(s.text[: self.max_chars])])
                  for s in sections]
        return self._t(f"Company: {symbol}") + "\nFiling sections:\n" + "\n".join(blocks)

    def estimate(self, symbol: str, sections: list[Any]) -> int:
        """Estimated input tokens of the request (system + user prompt); deterministic."""
        from .llm import estimate_tokens
        return estimate_tokens(self.system, self.prompt(symbol, sections))

    def fit(self, symbol: str, sections: list[Any]) -> tuple[list[Any], dict[str, Any]]:
        """The sections that fit ``max_prompt_tokens``, admitted newest first (by
        ``visible_date``) and returned in their original order, and a record of the cut."""
        order = sorted(range(len(sections)), key=lambda i: (sections[i].visible_date, -i), reverse=True)
        chosen: list[int] = []
        for i in order:
            trial = sorted(chosen + [i])
            if self.estimate(symbol, [sections[j] for j in trial]) > self.max_prompt_tokens:
                break     # newest first: everything older is left out too
            chosen = trial
        keep = set(chosen)
        kept = [sections[j] for j in chosen]
        left = [sections[j] for j in range(len(sections)) if j not in keep]
        record = {"max_prompt_tokens": self.max_prompt_tokens,
                  "estimated_tokens": self.estimate(symbol, kept) if kept else 0,
                  "sections_given": len(sections), "sections_kept": len(kept),
                  "truncated": bool(left),
                  "left_out": [f"{s.accession}/{s.section}" for s in left]}
        return kept, record

    def analyze(self, symbol: str, sections: list[Any]) -> TextAnalysis:
        if not sections:
            return TextAnalysis(self.name, False, problem="no sections")
        sections, budget = self.fit(symbol, sections)
        if not sections:
            return TextAnalysis(self.name, False, problem="prompt budget leaves no section", budget=budget)
        reply = _parse(self.llm.complete_json(self.system, self.prompt(symbol, sections), deep=False,
                                              schema=self.schema))
        last = getattr(self.llm, "last_call", None)
        if isinstance(last, dict) and last.get("truncated"):
            budget["server_truncated"] = True
            log.warning("fundamentals_text %s: reply rejected, the server truncated the prompt "
                        "(prompt_eval_count=%s, estimate=%s, num_ctx=%s)", symbol,
                        last.get("prompt_eval_count"), last.get("prompt_tok_est"), last.get("num_ctx"))
            return TextAnalysis(self.name, False, problem="reply rejected: the server truncated the prompt",
                                budget=budget)
        if reply is None or not isinstance(reply.get("claims"), list):
            return TextAnalysis(self.name, False, problem="no usable reply", budget=budget)
        # The model saw the scrubbed text and the aliased accession, so quotes are checked
        # against what it saw and the cited accession is mapped back to the real one.
        by_key = {(s.accession, s.section): _norm(self._t(s.text[: self.max_chars])) for s in sections}
        if self.anon is not None:
            reply["claims"] = [{**c, "accession": self.anon.accession_real(str(c.get("accession")))}
                               if isinstance(c, dict) else c for c in reply["claims"]]
        kept: list[dict[str, Any]] = []
        dropped: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for c in reply["claims"]:
            if not isinstance(c, dict):
                continue
            key = (str(c.get("accession")), str(c.get("section")))
            text = by_key.get(key)
            quote = _norm(str(c.get("quote", "")))
            if text is None:
                dropped.append({**c, "reason": "cites a section it was not given"})
            elif not quote or quote not in text:
                dropped.append({**c, "reason": "quote not found in the cited section"})
            elif (why := quote_problem(quote)) is not None:
                dropped.append({**c, "reason": why})
            elif (*key, quote) in seen:
                dropped.append({**c, "reason": "duplicate quote"})
            elif len(kept) >= MAX_CLAIMS:
                dropped.append({**c, "reason": f"over the {MAX_CLAIMS}-claim cap"})
            else:
                seen.add((*key, quote))
                kept.append(c)
        directions: dict[Any, int] = {"positive": 1, "negative": -1}
        score = sum(directions.get(c.get("direction"), 0) for c in kept)
        return TextAnalysis(self.name, True, {"claims": kept, "net_direction": score}, dropped, budget=budget)


class MacroTextAnalyst:
    name = "macro_text"
    system = MACRO_SYSTEM
    schema = MACRO_SCHEMA

    def __init__(self, llm: Any, anon: Any = None):
        self.llm = llm
        self.anon = anon     # anonymize.Anonymizer: statement dates become offsets

    def _t(self, text: str | None) -> str | None:
        return self.anon.scrub_text(text) if self.anon is not None and text else text

    def prompt(self, current: str, previous: str | None = None) -> str:
        parts = [untrusted_block("central-bank text (current)", [self._t(current) or ""])]
        if previous:
            parts.insert(0, untrusted_block("central-bank text (previous)", [self._t(previous) or ""]))
        return "\n".join(parts)

    def analyze(self, current: str, previous: str | None = None) -> TextAnalysis:
        reply = _parse(self.llm.complete_json(self.system, self.prompt(current, previous), deep=False,
                                              schema=self.schema))
        current, previous = self._t(current) or "", self._t(previous)   # quotes are checked against what it saw
        if reply is None or reply.get("stance") not in ("hawkish", "dovish", "neutral"):
            return TextAnalysis(self.name, False, problem="no usable reply")
        raw = reply.get("shift")
        # A8: a finite JSON number in [-1, 1] or a rejection; never clipped, never a NaN that
        # max/min would turn into +1.0, never a bool or a numeric string.
        if not isinstance(raw, (int, float)) or isinstance(raw, bool) or not math.isfinite(raw):
            return TextAnalysis(self.name, False, problem="shift not a finite number")
        if not -1.0 <= raw <= 1.0:
            return TextAnalysis(self.name, False, problem=f"shift {raw} outside [-1, 1]")
        shift = float(raw)
        src = _norm(current + " " + (previous or ""))
        quotes = [q for q in reply.get("quotes", []) if isinstance(q, str)] \
            if isinstance(reply.get("quotes"), list) else []
        kept: list[str] = []
        dropped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for q in quotes:
            n = _norm(q)
            why = ("quote not found in the text" if not n or n not in src
                   else quote_problem(n) or ("duplicate quote" if n in seen else None))
            if why is None and len(kept) >= MAX_CLAIMS:
                why = f"over the {MAX_CLAIMS}-quote cap"
            if why is None:
                seen.add(n)
                kept.append(q)
            else:
                dropped.append({"quote": q, "reason": why})
        if not kept:   # an uncited stance is not evidence
            return TextAnalysis(self.name, False, {"stance": reply["stance"], "shift": shift}, dropped,
                                problem="no verifiable quote")
        return TextAnalysis(self.name, True, {"stance": reply["stance"], "shift": shift, "quotes": kept}, dropped)


def dry_run(analyst: Any, *args: Any, model: str = "claude") -> dict[str, Any]:
    """The request a Claude variant would send, with its size; no call is made ($0)."""
    prompt = analyst.prompt(*args)
    return {"analyst": analyst.name, "model": model, "dry_run": True, "system_chars": len(analyst.system),
            "prompt_chars": len(prompt), "schema": analyst.schema,
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest()}


# P2 cells (scripts/llm_study.py convention): what a trial entry needs to reproduce each
# local-model text cell. Claude rows are dry-run only and never call the API.
TEXT_CELLS: tuple[dict[str, Any], ...] = (
    {"name": "fundamentals_text_local", "trial_name": "v0.15 LLM fundamentals-text analyst (local, cited claims)",
     "overrides": {"llm_provider": "local", "text_analysts": ["fundamentals_text"]}},
    {"name": "macro_text_local", "trial_name": "v0.15 LLM macro-text hawkish/dovish (local)",
     "overrides": {"llm_provider": "local", "text_analysts": ["macro_text"]}},
    {"name": "fundamentals_text_claude", "trial_name": None, "dry_run_only": True,
     "overrides": {"llm_provider": "anthropic", "text_analysts": ["fundamentals_text"]}},
    {"name": "macro_text_claude", "trial_name": None, "dry_run_only": True,
     "overrides": {"llm_provider": "anthropic", "text_analysts": ["macro_text"]}},
)


# ------------------------------------------------------------------ trading-graph wiring
# Off by default: ``config["text_analysts"] = []`` leaves the desk exactly as before. Naming
# "fundamentals_text" and/or "macro_text" adds one fenced, cited report each to the state
# before the debate. Inputs are point in time: a filing section or central-bank statement is
# used only when its ``visible_date`` is at or before the decision cut-off (``as_of`` at
# ``TEXT_CUTOFF_UTC``, the US close in summer time, so a filing accepted after the close is
# not read the same day). Research retrieval reaches an analyst only through
# ``research_rag.analyst_retriever`` (the 0.8 recall@5 gate); a corpus that fails the gate
# leaves the analyst with its own sections.
TEXT_ANALYST_NAMES = ("fundamentals_text", "macro_text")
TEXT_CUTOFF_UTC = (20, 0)
CCY_BANK = {"USD": "FOMC", "EUR": "ECB", "GBP": "BoE", "JPY": "BoJ"}


def text_cutoff(as_of: Any) -> datetime:
    if isinstance(as_of, datetime):
        return as_of if as_of.tzinfo else as_of.replace(tzinfo=timezone.utc)
    d = as_of if isinstance(as_of, date) else date.fromisoformat(str(as_of))
    return datetime(d.year, d.month, d.day, *TEXT_CUTOFF_UTC, tzinfo=timezone.utc)


@dataclass
class TextInputs:
    """What the text analysts may read. ``edgar`` is anything with ``sections(symbol, as_of)``
    (``data.edgar_text.EdgarProvider``); ``statements`` are ``research_rag.CentralBankStatement``;
    ``retriever`` must come from ``research_rag.analyst_retriever``."""
    edgar: Any = None
    statements: list[Any] = field(default_factory=list)
    retriever: Any = None
    retrieval_k: int = 3
    fundamentals_max_prompt_tokens: int = DEFAULT_FUNDAMENTALS_PROMPT_TOKENS

    @classmethod
    def from_config(cls, config: dict) -> "TextInputs":
        from .agentic import research_rag as rr
        from .data.edgar_text import EdgarProvider
        opts = config.get("text_analyst_options") or {}
        statements = rr.load_central_bank_statements(opts["central_bank_path"]) if opts.get("central_bank_path") else []
        retriever = None
        if opts.get("research_retrieval"):
            corpus = (rr.load_eval_corpus(opts["research_corpus_path"]) if opts.get("research_corpus_path")
                      else rr.ResearchCorpus.build(statements=statements))
            qs = rr.load_questions(opts["retrieval_questions_path"]) if opts.get("retrieval_questions_path") else None
            try:
                retriever = rr.analyst_retriever(corpus, qs, opts.get("retrieval_method", "tfidf"))
            except (rr.RetrievalGateError, ValueError) as e:   # fail closed: no retrieval
                log.warning("research retrieval refused: %s", e)
        return cls(EdgarProvider.from_config(config), statements, retriever, int(opts.get("retrieval_k", 3)),
                   int(opts.get("fundamentals_max_prompt_tokens") or DEFAULT_FUNDAMENTALS_PROMPT_TOKENS))


def _visible(items: Iterable[Any], cut: datetime) -> list[Any]:
    return [x for x in items if getattr(x, "visible_date", None) is not None and x.visible_date <= cut]


def _edgar_identity(edgar: Any, symbol: str) -> list[str]:
    """Company names (``entityName``, ``formerNames``) from the cached EDGAR submissions JSON."""
    fn = getattr(edgar, "company_names", None)
    if fn is None:
        return []
    try:
        return list(fn(symbol))
    except Exception as e:   # a failed lookup leaves the built-in name map in force
        log.warning("EDGAR company names for %s unavailable: %s", symbol, e)
        return []


def text_reports(names: Iterable[str], llm: Any, inputs: TextInputs, instrument: Any, as_of: Any,
                 anon: Any = None) -> list[Any]:
    """One ``AnalystReport`` per requested text analyst, point in time and fenced.

    With ``anon`` (``state.anon``, set when ``llm_anonymize`` is on) every text prompt goes
    through ``Anonymizer.scrub_text``, and the report's points and summary keep the aliases
    the model saw (``ACC_1``, ``COMPANY_X``), so they stay anonymised when later agents quote
    them. The real accession numbers stay in ``facts["sections"]`` for the audit trail; facts
    outside the anonymiser's allow-list never reach a prompt.
    """
    from .state import AnalystReport
    cut = text_cutoff(as_of)
    if anon is not None and inputs.edgar is not None and not instrument.is_fx:
        anon.add_names(_edgar_identity(inputs.edgar, instrument.symbol))
    out = []
    for name in names:
        if name not in TEXT_ANALYST_NAMES:
            raise ValueError(f"unknown text analyst {name!r}; choose from {TEXT_ANALYST_NAMES}")
        facts: dict[str, Any] = {"cutoff": cut.isoformat()}
        if llm is None or not hasattr(llm, "complete_json"):
            res = TextAnalysis(name, False, problem="no model backend")
        elif name == "fundamentals_text":
            if instrument.is_fx:
                res = TextAnalysis(name, False, problem="no filings for FX")
            else:
                secs = _visible(inputs.edgar.sections(instrument.symbol, cut), cut) if inputs.edgar else []
                if inputs.retriever is not None:
                    hits = inputs.retriever(f"{instrument.symbol} business outlook risks results", cut,
                                            k=inputs.retrieval_k, symbol=instrument.symbol)
                    have = {(s.accession, s.section) for s in secs}
                    extra = [h.passage for h in hits if (h.passage.accession, h.passage.section) not in have]
                    facts["retrieved"] = [p.id for p in extra]
                    secs = secs + _visible(extra, cut)
                facts["sections"] = [f"{s.accession}/{s.section}" for s in secs]
                facts["visible_dates"] = [s.visible_date.isoformat() for s in secs]
                res = FundamentalsTextAnalyst(llm, anon=anon,
                                              max_prompt_tokens=inputs.fundamentals_max_prompt_tokens
                                              ).analyze(instrument.symbol, secs)
                if res.budget is not None:
                    facts["prompt_budget"] = res.budget
        else:
            pairs = ([(CCY_BANK.get(instrument.base), 1.0), (CCY_BANK.get(instrument.quote), -1.0)]
                     if instrument.is_fx else [("FOMC", -0.5)])   # tighter policy is an equity headwind
            sts: list[Any] = []
            for bank, sign in pairs:
                sts = sorted((st for st in inputs.statements if bank and st.bank == bank and st.released <= cut),
                             key=lambda st: st.released)
                if sts:
                    facts.update(bank=bank, sign=sign)
                    break
            if not sts:
                res = TextAnalysis(name, False, problem="no central-bank text visible")
            else:
                facts.update(statements=[st.accession for st in sts[-2:]],
                             visible_dates=[st.released.isoformat() for st in sts[-2:]])
                res = MacroTextAnalyst(llm, anon=anon).analyze(sts[-1].text,
                                                               sts[-2].text if len(sts) > 1 else None)
        facts["dropped"] = len(res.dropped)
        if not res.ok:
            out.append(AnalystReport(name, 0.0, 0.0, f"{name}: {res.problem}", facts=facts, source="llm",
                                     abstained=True, untrusted=True))
            continue
        if name == "fundamentals_text":
            claims = res.result["claims"]
            signal = max(-1.0, min(1.0, res.result["net_direction"] / max(3, len(claims))))
            conf = min(0.5, 0.1 * len(claims))
            points = [f"{c['direction']}: {c['claim']} [{c['accession']} {c['section']}]" for c in claims]
            if anon is not None:
                points = [anon.scrub_text(p) for p in points]
            summary = f"{len(claims)} cited filing claims, net {res.result['net_direction']:+d}"
        else:
            signal = max(-1.0, min(1.0, facts["sign"] * res.result["shift"]))
            conf = 0.3
            points = list(res.result["quotes"])
            summary = f"{facts['bank']} {res.result['stance']}, shift {res.result['shift']:+.2f}"
        out.append(AnalystReport(name, signal, conf, summary, points, facts, source="llm", untrusted=True))
    return out
