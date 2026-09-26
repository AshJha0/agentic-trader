"""Dependency-free retrieval over the desk's runbooks and policies.

Documents (Markdown files in ``knowledge/docs``) are split by heading into
chunks. Each chunk is embedded with a **hashed TF-IDF**: unigrams and bigrams
are hashed into a fixed number of buckets, weighted by term frequency and
inverse document frequency, and L2-normalised, so similarity is a cosine. No
model download, no external service, deterministic results.

Retrieved passages are returned with their document id, heading and score and
become DOCUMENT evidence when reached through the ``knowledge.search`` tool.
"""
from __future__ import annotations

import math
import re
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np

DOCS_DIR = Path(__file__).with_name("knowledge") / "docs"
_TOKEN = re.compile(r"[a-z0-9][a-z0-9\-']*")
_STOP = frozenset("""a an and are as at be by for from has have if in into is it its of on or that the
    their then there these this to was were will with which when what how why can not no""".split())


def tokenize(text: str) -> list[str]:
    toks = [t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 1]
    return toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]


@dataclass(frozen=True)
class Chunk:
    doc_id: str
    title: str
    heading: str
    text: str
    order: int

    @property
    def id(self) -> str:
        return f"{self.doc_id}#{self.order}"


@dataclass
class Passage:
    chunk: Chunk
    score: float

    def to_dict(self) -> dict:
        return {"id": self.chunk.id, "document": self.chunk.doc_id, "title": self.chunk.title,
                "heading": self.chunk.heading, "text": self.chunk.text, "score": round(self.score, 4)}


def split_markdown(doc_id: str, text: str) -> list[Chunk]:
    """One chunk per heading section (the title line is kept with the intro)."""
    lines = text.splitlines()
    title = next((l.lstrip("# ").strip() for l in lines if l.startswith("# ")), doc_id)
    chunks, heading, buf = [], "Introduction", []

    def flush():
        body = "\n".join(buf).strip()
        if body:
            chunks.append(Chunk(doc_id, title, heading, body, len(chunks)))

    for line in lines:
        if line.startswith("# "):
            continue
        if line.startswith("## "):
            flush()
            heading, buf = line[3:].strip(), []
        else:
            buf.append(line)
    flush()
    return chunks


class HashedTfidf:
    def __init__(self, buckets: int = 4096):
        self.buckets = buckets
        self.idf: np.ndarray | None = None

    def _bucket(self, token: str) -> int:
        return zlib.crc32(token.encode("utf-8")) % self.buckets

    def _tf(self, text: str) -> np.ndarray:
        v = np.zeros(self.buckets)
        for t in tokenize(text):
            v[self._bucket(t)] += 1.0
        return v

    def fit(self, texts: Iterable[str]) -> "HashedTfidf":
        tfs = [self._tf(t) for t in texts]
        n = max(len(tfs), 1)
        df = np.sum([tf > 0 for tf in tfs], axis=0) if tfs else np.zeros(self.buckets)
        self.idf = np.log((1 + n) / (1 + df)) + 1.0
        return self

    def embed(self, text: str) -> np.ndarray:
        if self.idf is None:
            raise RuntimeError("fit the embedder first")
        v = self._tf(text)
        v = np.log1p(v) * self.idf
        norm = np.linalg.norm(v)
        return v / norm if norm > 0 else v


@dataclass
class KnowledgeBase:
    chunks: list[Chunk]
    embedder: HashedTfidf = field(default_factory=HashedTfidf)
    _matrix: np.ndarray | None = field(default=None, repr=False)

    @classmethod
    def from_dir(cls, path: Path | str = DOCS_DIR) -> "KnowledgeBase":
        chunks: list[Chunk] = []
        for f in sorted(Path(path).glob("*.md")):
            chunks.extend(split_markdown(f.stem, f.read_text(encoding="utf-8")))
        return cls(chunks).build()

    @classmethod
    def from_texts(cls, docs: dict[str, str]) -> "KnowledgeBase":
        chunks: list[Chunk] = []
        for doc_id, text in docs.items():
            chunks.extend(split_markdown(doc_id, text))
        return cls(chunks).build()

    def build(self) -> "KnowledgeBase":
        self.embedder.fit(f"{c.title} {c.heading} {c.text}" for c in self.chunks)
        self._matrix = np.vstack([self.embedder.embed(f"{c.title} {c.heading} {c.text}") for c in self.chunks]) \
            if self.chunks else np.zeros((0, self.embedder.buckets))
        return self

    @property
    def documents(self) -> list[str]:
        return sorted({c.doc_id for c in self.chunks})

    def search(self, query: str, k: int = 3, min_score: float = 0.05) -> list[Passage]:
        if not self.chunks or not query.strip():
            return []
        q = self.embedder.embed(query)
        scores = self._matrix @ q
        order = np.argsort(-scores)[:max(1, k)]
        return [Passage(self.chunks[i], float(scores[i])) for i in order if scores[i] >= min_score]

    def get(self, chunk_id: str) -> Chunk | None:
        return next((c for c in self.chunks if c.id == chunk_id), None)

    def __len__(self) -> int:
        return len(self.chunks)


_default: KnowledgeBase | None = None


def default_knowledge_base() -> KnowledgeBase:
    global _default
    if _default is None:
        _default = KnowledgeBase.from_dir()
    return _default
