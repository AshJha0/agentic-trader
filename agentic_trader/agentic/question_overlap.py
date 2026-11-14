"""Lexical-overlap check for retrieval questions (v0.17 R3.2, review finding B5).

A question written while looking at its gold passage tends to reuse the passage's literals
("from 80 cents to 84 cents"). TF-IDF and BM25 reward exactly that, so recall on such a set
says little about analyst-style questions. This check rejects a question that shares too much
wording with its gold passage.

Formal rule. Tokens are those of :func:`agentic_trader.agentic.rag.tokenize` (lower case,
stop words and one-character tokens dropped); unigrams U(q) and adjacent bigrams B(q) are taken
from that list. A question q with gold passage text p is **rejected** when either

* it shares any content bigram with p: ``B(q) & B(p)`` is non-empty, or
* its unigram containment ``|U(q) & U(p)| / |U(q)|`` exceeds ``MAX_CONTAINMENT`` (0.34, so a
  question may reuse at most about one content word in three).

Ticker symbols, section names and central-bank codes are passage *metadata*, not passage text,
so a question may name the company ("is BOLT's margin exposed to lithium?" shares only
``lithium``). Worked example: "How much did ACME net sales grow last year?" against "Net sales
rose 14 percent ..." shares the bigram ``net_sales`` and is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass

from .rag import tokenize

MAX_CONTAINMENT = 0.34


def _split(text: str) -> tuple[set[str], set[str]]:
    toks = tokenize(text)
    return {t for t in toks if "_" not in t}, {t for t in toks if "_" in t}


@dataclass(frozen=True)
class Overlap:
    containment: float
    shared_unigrams: tuple[str, ...]
    shared_bigrams: tuple[str, ...]

    @property
    def rejected(self) -> bool:
        return bool(self.shared_bigrams) or self.containment > MAX_CONTAINMENT


def lexical_overlap(question: str, passage: str) -> Overlap:
    qu, qb = _split(question)
    pu, pb = _split(passage)
    su, sb = qu & pu, qb & pb
    return Overlap(len(su) / len(qu) if qu else 0.0, tuple(sorted(su)), tuple(sorted(sb)))
