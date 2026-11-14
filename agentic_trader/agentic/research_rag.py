"""Point-in-time research retrieval over filings and central-bank statements (PLAN.md 3.4-3.7).

This extends the policy-runbook RAG in :mod:`agentic_trader.agentic.rag` rather than
duplicating it: the same tokenizer and hashed TF-IDF embedder are used, over a second,
dated corpus.

* **Corpus (3.4).** Passages come from EDGAR filing sections (any object shaped like
  ``agentic_trader.data.edgar.FilingSection``; consumed by duck type so this module does
  not import it) and central-bank statements (FOMC, ECB, BoE, BoJ) dated by their release
  time in UTC. Every passage carries ``{symbol, accession, visible_date, section}``.
* **Point in time.** ``search(query, as_of)`` never returns a passage whose
  ``visible_date`` is after ``as_of``, and the IDF weights are fitted on the visible
  passages only, so document frequencies from the future do not leak into the ranking.
* **Hybrid retrieval (3.5).** Hashed TF-IDF is the default. ``method="hybrid"`` fuses
  TF-IDF with BM25 (dependency-free) and, when the optional ``[rag]`` extra is installed
  and ``use_embeddings=True``, a local sentence-embedding ranker, by reciprocal-rank fusion.
* **Citations (3.6).** Passages render as Anthropic ``document`` content blocks with
  ``citations: {"enabled": true}``; :func:`build_cited_request` builds the request payload
  and makes no call. :func:`audit_citations` fails unless every quoted span maps to a
  passage id whose text contains it.
* **Evaluation gate (3.7).** :func:`evaluate_retrieval` reports recall@5 and MRR over a
  hand-labelled question set; :func:`analyst_retriever` refuses to hand retrieval to the
  analysts unless recall@5 >= 0.8 (``RECALL_GATE``).
"""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol, Sequence

import numpy as np

from .rag import HashedTfidf, tokenize

EVAL_DIR = Path(__file__).with_name("knowledge") / "retrieval_eval"
RECALL_GATE = 0.8
RRF_K = 60
CENTRAL_BANKS = ("FOMC", "ECB", "BoE", "BoJ")


class FilingSectionLike(Protocol):
    """Duck type of ``agentic_trader.data.edgar.FilingSection`` (shared contract)."""

    symbol: str
    accession: str
    form: str
    section: str
    visible_date: datetime
    text: str


def _utc(ts: datetime | date | str) -> datetime:
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if not isinstance(ts, datetime):
        # a bare date means "known by the end of that day": the conservative reading
        ts = datetime(ts.year, ts.month, ts.day, 23, 59, 59, tzinfo=timezone.utc)
    if ts.tzinfo is None:
        raise ValueError(f"naive datetime {ts!r}: visible times must be timezone-aware UTC")
    return ts.astimezone(timezone.utc)


@dataclass(frozen=True)
class ResearchPassage:
    id: str
    source: str  # "edgar" | "central_bank"
    symbol: str  # ticker, or the bank ("FOMC", "ECB", ...)
    accession: str
    form: str
    section: str
    visible_date: datetime
    text: str
    title: str = ""

    @property
    def metadata(self) -> dict[str, str]:
        return {
            "symbol": self.symbol,
            "accession": self.accession,
            "visible_date": self.visible_date.isoformat(),
            "section": self.section,
        }

    def to_dict(self, score: float | None = None) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "source": self.source,
            "form": self.form,
            "title": self.title,
            "text": self.text,
            **self.metadata,
        }
        if score is not None:
            d["score"] = round(score, 4)
        return d


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def _merge_paragraphs(paras: list[str], min_chars: int) -> list[str]:
    """Consecutive paragraphs joined until each passage has at least ``min_chars`` characters.
    Real filings converted from HTML split tables and headings into lines of a few characters
    (median 9 on the 2016-2021 core-name filings), which are useless as passages alone."""
    out: list[str] = []
    cur: list[str] = []
    n = 0
    for p in paras:
        cur.append(p)
        n += len(p)
        if n >= min_chars:
            out.append("\n\n".join(cur))
            cur, n = [], 0
    if cur:
        if out and n < min_chars // 4:
            out[-1] = out[-1] + "\n\n" + "\n\n".join(cur)
        else:
            out.append("\n\n".join(cur))
    return out


def passages_from_filings(sections: Iterable[FilingSectionLike], min_chars: int = 0) -> list[ResearchPassage]:
    """One passage per paragraph of each filing section; id ``{accession}#{section}#{i}``.
    With ``min_chars > 0`` consecutive paragraphs are merged into passages of at least that
    many characters (real filings; the fixture corpus keeps one passage per paragraph)."""
    out: list[ResearchPassage] = []
    for s in sections:
        vis = _utc(s.visible_date)
        paras = _paragraphs(s.text)
        if min_chars > 0:
            paras = _merge_paragraphs(paras, min_chars)
        for i, para in enumerate(paras):
            out.append(
                ResearchPassage(
                    f"{s.accession}#{s.section}#{i}",
                    "edgar",
                    s.symbol,
                    s.accession,
                    s.form,
                    s.section,
                    vis,
                    para,
                    f"{s.symbol} {s.form} {s.section}",
                )
            )
    return out


@dataclass(frozen=True)
class CentralBankStatement:
    bank: str
    released: datetime  # release time, UTC
    title: str
    text: str

    @property
    def accession(self) -> str:
        return f"{self.bank}-{self.released:%Y-%m-%d}"


def load_central_bank_statements(path: Path | str) -> list[CentralBankStatement]:
    """Statements from a JSON file (list of {bank, released, title, text}) or a directory of
    them. ``released`` must be an ISO time with an offset; the statement is visible from then."""
    p = Path(path)
    files = sorted(p.glob("*.json")) if p.is_dir() else [p]
    out = []
    for f in files:
        rows = json.loads(f.read_text(encoding="utf-8"))
        for r in rows if isinstance(rows, list) else [rows]:
            if r["bank"] not in CENTRAL_BANKS:
                raise ValueError(f"unknown central bank {r['bank']!r}")
            out.append(CentralBankStatement(r["bank"], _utc(r["released"]), r.get("title", ""), r["text"]))
    return out


def passages_from_statements(statements: Iterable[CentralBankStatement]) -> list[ResearchPassage]:
    out = []
    for st in statements:
        for i, para in enumerate(_paragraphs(st.text)):
            out.append(
                ResearchPassage(
                    f"{st.accession}#statement#{i}",
                    "central_bank",
                    st.bank,
                    st.accession,
                    "statement",
                    "statement",
                    st.released,
                    para,
                    st.title,
                )
            )
    return out


# ------------------------------------------------------------------ rankers
class _Bm25:
    def __init__(self, texts: Sequence[str], k1: float = 1.5, b: float = 0.75):
        self.docs = [Counter(tokenize(t)) for t in texts]
        self.len = np.array([sum(d.values()) for d in self.docs], dtype=float)
        self.avg = float(self.len.mean()) if len(self.docs) else 0.0
        df = Counter(t for d in self.docs for t in d)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.k1, self.b = k1, b

    def scores(self, query: str) -> np.ndarray:
        q = set(tokenize(query))
        out = np.zeros(len(self.docs))
        for i, d in enumerate(self.docs):
            norm = self.k1 * (1 - self.b + self.b * self.len[i] / (self.avg or 1.0))
            out[i] = sum(self.idf[t] * d[t] * (self.k1 + 1) / (d[t] + norm) for t in q if t in d)
        return out


def embeddings_available() -> bool:
    try:
        import sentence_transformers  # noqa: F401
    except Exception:
        return False
    return True


class _LocalEmbedder:
    """Optional local sentence embeddings (``pip install agentic-trader[rag]``). Lazy import;
    the model is a local download, never a paid API."""

    def __init__(self, model: str = "sentence-transformers/all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model)

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        return np.asarray(self.model.encode(list(texts), normalize_embeddings=True))


def reciprocal_rank_fusion(rankings: Sequence[Sequence[int]], k: int = RRF_K) -> list[int]:
    """Fuse ranked lists of indices: score(d) = sum 1 / (k + rank). Ties broken by index."""
    score: dict[int, float] = {}
    for ranking in rankings:
        for r, idx in enumerate(ranking):
            score[idx] = score.get(idx, 0.0) + 1.0 / (k + r + 1)
    return sorted(score, key=lambda i: (-score[i], i))


@dataclass
class Hit:
    passage: ResearchPassage
    score: float

    def to_dict(self) -> dict[str, Any]:
        return self.passage.to_dict(self.score)


@dataclass
class ResearchCorpus:
    passages: list[ResearchPassage]
    buckets: int = 4096
    use_embeddings: bool = False
    # seam: any object with ``encode(texts) -> (n, d) array`` of unit rows; tests inject a
    # deterministic fake here. None means the optional local sentence-transformers model.
    embedder: Any = field(default=None, repr=False)
    _cache: dict[int, tuple] = field(default_factory=dict, repr=False)
    _embedder: Any = field(default=None, repr=False)

    def __post_init__(self):
        ids = [p.id for p in self.passages]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate passage ids in the research corpus")
        self.passages = sorted(self.passages, key=lambda p: (p.visible_date, p.id))
        self._times = [p.visible_date for p in self.passages]
        if self.use_embeddings:
            if self.embedder is not None:
                self._embedder = self.embedder
            elif not embeddings_available():
                raise RuntimeError("use_embeddings needs the optional [rag] extra (sentence-transformers)")
            else:
                self._embedder = _LocalEmbedder()
            self._emb = self._embedder.encode([self._doc_text(p) for p in self.passages])

    @classmethod
    def build(
        cls, filings: Iterable[FilingSectionLike] = (), statements: Iterable[CentralBankStatement] = (), min_chars: int = 0, **kw
    ) -> "ResearchCorpus":
        return cls(passages_from_filings(filings, min_chars) + passages_from_statements(statements), **kw)

    @staticmethod
    def _doc_text(p: ResearchPassage) -> str:
        return f"{p.title} {p.symbol} {p.section} {p.text}"

    def _visible(self, as_of: datetime) -> int:
        """Passages are sorted by visible time, so the visible set is a prefix."""
        lo, hi = 0, len(self._times)
        while lo < hi:
            mid = (lo + hi) // 2
            if self._times[mid] <= as_of:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def _index(self, n: int) -> tuple:
        if n not in self._cache:
            texts = [self._doc_text(p) for p in self.passages[:n]]
            emb = HashedTfidf(self.buckets).fit(texts)
            mat = np.vstack([emb.embed(t) for t in texts]) if texts else np.zeros((0, self.buckets))
            self._cache[n] = (emb, mat, _Bm25(texts))
        return self._cache[n]

    def search(
        self,
        query: str,
        as_of: datetime | date | str,
        k: int = 5,
        method: str = "tfidf",
        symbol: str | None = None,
        source: str | None = None,
    ) -> list[Hit]:
        if method not in ("tfidf", "hybrid"):
            raise ValueError(f"unknown retrieval method {method!r}")
        cut = _utc(as_of)
        n = self._visible(cut)
        if n == 0 or not query.strip():
            return []
        emb, mat, bm25 = self._index(n)
        allowed = [
            i
            for i in range(n)
            if (symbol is None or self.passages[i].symbol == symbol) and (source is None or self.passages[i].source == source)
        ]
        if not allowed:
            return []
        tf = mat @ emb.embed(query)
        rank_tf = sorted(allowed, key=lambda i: (-tf[i], i))
        if method == "tfidf":
            order, score = rank_tf, {i: float(tf[i]) for i in allowed}
        else:
            bm = bm25.scores(query)
            rankings = [rank_tf, sorted(allowed, key=lambda i: (-bm[i], i))]
            if self.use_embeddings:
                qe = self._embedder.encode([query])[0]
                es = self._emb[:n] @ qe
                rankings.append(sorted(allowed, key=lambda i: (-es[i], i)))
            order = reciprocal_rank_fusion(rankings)
            score = {i: sum(1.0 / (RRF_K + r.index(i) + 1) for r in rankings) for i in order}
        hits = [Hit(self.passages[i], score[i]) for i in order[:k]]
        assert all(h.passage.visible_date <= cut for h in hits), "point-in-time violation"
        return hits

    def get(self, passage_id: str) -> ResearchPassage | None:
        return next((p for p in self.passages if p.id == passage_id), None)

    def __len__(self) -> int:
        return len(self.passages)


# ------------------------------------------------------------------ citations (3.6)
def to_document_blocks(hits: Sequence[Hit | ResearchPassage]) -> list[dict[str, Any]]:
    """Anthropic ``document`` content blocks, one per passage, citations enabled. The
    passage id and metadata ride in ``title`` and ``context`` so a citation's
    ``document_index`` maps back to a passage id."""
    blocks = []
    for h in hits:
        p = h.passage if isinstance(h, Hit) else h
        blocks.append(
            {
                "type": "document",
                "source": {"type": "text", "media_type": "text/plain", "data": p.text},
                "title": p.id,
                "context": json.dumps(p.metadata, sort_keys=True),
                "citations": {"enabled": True},
            }
        )
    return blocks


def build_cited_request(
    question: str, hits: Sequence[Hit | ResearchPassage], model: str = "claude-opus-5-5", max_tokens: int = 1024
) -> dict[str, Any]:
    """The Messages API payload for a cited answer. Built only; nothing is sent."""
    return {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": to_document_blocks(hits) + [{"type": "text", "text": question}]}],
    }


@dataclass
class CitationAudit:
    ok: bool
    checked: int
    failures: list[str]


def audit_citations(claims: Iterable[dict[str, Any]], passages: Sequence[Hit | ResearchPassage]) -> CitationAudit:
    """Every quoted span must map to a passage id whose text contains it verbatim.

    A claim is ``{"quote": str, "passage_id": str}`` or an Anthropic citation
    ``{"cited_text": str, "document_index": int}`` / ``{"cited_text", "document_title"}``
    over the blocks from :func:`to_document_blocks` (title = passage id)."""
    ps = [h.passage if isinstance(h, Hit) else h for h in passages]
    by_id = {p.id: p for p in ps}
    failures, n = [], 0
    for c in claims:
        n += 1
        quote = c.get("quote", c.get("cited_text"))
        pid = c.get("passage_id", c.get("document_title"))
        if pid is None and "document_index" in c:
            idx = c["document_index"]
            pid = ps[idx].id if isinstance(idx, int) and 0 <= idx < len(ps) else None
        if not quote or not str(quote).strip():
            failures.append(f"claim {n}: empty quote")
        elif pid not in by_id:
            failures.append(f"claim {n}: no passage id for quote {str(quote)[:60]!r}")
        elif str(quote).strip() not in by_id[pid].text:
            failures.append(f"claim {n}: quote not found in {pid}")
    return CitationAudit(not failures and n > 0, n, failures if n else ["no claims to audit"])


def citations_from_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the citations of a Messages API response (dict form) into audit claims."""
    out = []
    for block in response.get("content", []):
        for cit in block.get("citations") or []:
            out.append(
                {
                    "cited_text": cit.get("cited_text"),
                    "document_index": cit.get("document_index"),
                    "document_title": cit.get("document_title"),
                }
            )
    return out


# ------------------------------------------------------------------ evaluation (3.7)
@dataclass(frozen=True)
class Question:
    id: str
    text: str
    as_of: datetime
    gold: tuple[str, ...]  # gold passage ids
    gold_accession: str


def load_questions(path: Path | str = EVAL_DIR / "questions.json") -> list[Question]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Question(r["id"], r["question"], _utc(r["as_of"]), tuple(r["gold"]), r["gold_accession"]) for r in rows]


def load_eval_corpus(path: Path | str = EVAL_DIR / "corpus.json", **kw) -> ResearchCorpus:
    """The fixture corpus: filing sections as plain dicts (FilingSection-shaped) plus statements."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))

    @dataclass(frozen=True)
    class _Section:
        symbol: str
        accession: str
        form: str
        section: str
        visible_date: datetime
        text: str

    secs = [
        _Section(r["symbol"], r["accession"], r["form"], r["section"], _utc(r["visible_date"]), r["text"]) for r in raw["filings"]
    ]
    sts = [CentralBankStatement(r["bank"], _utc(r["released"]), r.get("title", ""), r["text"]) for r in raw["statements"]]
    return ResearchCorpus.build(secs, sts, **kw)  # type: ignore[arg-type]  # _Section is FilingSectionLike at runtime


@dataclass
class RetrievalReport:
    method: str
    n: int
    recall_at_5: float
    mrr: float
    accession_recall_at_5: float

    @property
    def passes_gate(self) -> bool:
        return self.recall_at_5 >= RECALL_GATE


def evaluate_retrieval(
    corpus: ResearchCorpus, questions: Sequence[Question], method: str = "tfidf", k: int = 5
) -> RetrievalReport:
    if not questions:
        raise ValueError("empty question set")
    rec = mrr = acc = 0.0
    for q in questions:
        hits = corpus.search(q.text, q.as_of, k=max(k, 10), method=method)
        ids = [h.passage.id for h in hits]
        rec += any(g in ids[:k] for g in q.gold)
        acc += any(h.passage.accession == q.gold_accession for h in hits[:k])
        rank = next((r for r, pid in enumerate(ids, 1) if pid in q.gold), None)
        mrr += 1.0 / rank if rank else 0.0
    n = len(questions)
    return RetrievalReport(method, n, rec / n, mrr / n, acc / n)


def comparison_table(reports: Sequence[RetrievalReport]) -> str:
    lines = ["| method | questions | recall@5 | MRR | accession recall@5 | gate (>= 0.8) |", "|---|---|---|---|---|---|"]
    lines += [
        f"| {r.method} | {r.n} | {r.recall_at_5:.3f} | {r.mrr:.3f} | {r.accession_recall_at_5:.3f} | "
        f"{'pass' if r.passes_gate else 'FAIL'} |"
        for r in reports
    ]
    return "\n".join(lines)


class RetrievalGateError(RuntimeError):
    pass


def analyst_retriever(
    corpus: ResearchCorpus, questions: Sequence[Question] | None = None, method: str = "tfidf"
) -> Callable[..., list[Hit]]:
    """The only way analysts get research retrieval: measured first, refused below the gate."""
    report = evaluate_retrieval(corpus, questions if questions is not None else load_questions(), method)
    if not report.passes_gate:
        raise RetrievalGateError(
            f"{method} recall@5 {report.recall_at_5:.3f} < {RECALL_GATE}: retrieval is not available to analysts"
        )

    def retrieve(query: str, as_of, k: int = 5, **kw) -> list[Hit]:
        return corpus.search(query, as_of, k=k, method=method, **kw)

    retrieve.report = report  # type: ignore[attr-defined]
    return retrieve


# ------------------------------------------------------------------ 3.9 runbook ablation
RUNBOOK_TRIAL_NAME = "v0.15 policy-runbook RAG removed (decision ablation)"


def runbook_rag_ablation(
    symbols: Sequence[str] = ("AAPL", "MSFT", "EURUSD"),
    dates: Sequence[date] = (date(2024, 3, 1), date(2024, 6, 3), date(2024, 9, 2)),
    config: dict | None = None,
) -> dict[str, Any]:
    """Run the agentic harness on the rules path (no LLM, synthetic data, offline) with the
    policy-runbook knowledge base and with one that returns nothing, and count decisions that
    differ. On the rules path the passages only feed LLM prompts, so the expected answer is
    zero changed decisions; the LLM path needs a model and is not run here."""
    from .. import TradingGraph, make_config
    from ..memory import DecisionMemory
    from .harness import AgentHarness, Task
    from .rag import KnowledgeBase, default_knowledge_base

    class _Empty(KnowledgeBase):
        def search(self, query, k=3, min_score=0.05):
            return []

        def __len__(self) -> int:  # truthy, so DeskTools does not fall back to the default base
            return 1

    cfg = config or make_config(memory_path=None)
    empty = _Empty([]).build()
    rows, changed = [], 0
    for sym in symbols:
        for d in dates:
            out = []
            for kb in (default_knowledge_base(), empty):
                g = TradingGraph(cfg, memory=DecisionMemory(None), on_event=lambda *_: None)
                run = AgentHarness(g, knowledge=kb).run(Task(sym, d))
                dec = run.trading_state.decision if run.trading_state else None
                out.append((dec.action.value, round(dec.target_weight, 10)) if dec else None)
            diff = out[0] != out[1]
            changed += diff
            rows.append({"symbol": sym, "as_of": d.isoformat(), "with_rag": out[0], "without_rag": out[1], "changed": diff})
    return {"trial": RUNBOOK_TRIAL_NAME, "cells": len(rows), "changed": changed, "rows": rows}
