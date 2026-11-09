"""v0.16 quality pass, round 2: the 3.5 local-embeddings retrieval path through an injected
deterministic fake embedder, plus error paths and edge cases in v15/v16 library code.

Offline and $0: no network, no model calls, no sentence-transformers, no thread timing.
"""
from __future__ import annotations

import hashlib
import json
import logging
import socket
import sys
import types
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agentic_trader.agentic import research_rag as rr
from agentic_trader.agentic.replay import ReplayLLM, ReplayMissingPayload, RecordingLLM, Tape, decision_fingerprint
from agentic_trader.agentic.research_rag import ResearchCorpus, ResearchPassage, reciprocal_rank_fusion
from agentic_trader.agentic.tracing import Metrics, Tracer, configure_json_logging, export_otel
from agentic_trader.data import edgar_text as et
from agentic_trader.local_llm import LocalLLM, served_matches

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


# --------------------------------------------------------------------------- fake embedder
class FakeEmbedder:
    """Deterministic stand-in for a sentence model: words map to concept buckets, so
    synonyms ("liquidity", "funding") land on the same axis even with no shared token.
    Rows are unit-normalised, matching ``normalize_embeddings=True``."""
    CONCEPTS = {"liquidity": "cash", "funding": "cash", "cash": "cash",
                "inflation": "prices", "prices": "prices", "cpi": "prices"}
    DIM = 64

    def __init__(self):
        self.calls: list[int] = []

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.DIM)
        for w in text.lower().split():
            key = self.CONCEPTS.get(w.strip(".,"), w)
            v[int(hashlib.sha1(key.encode()).hexdigest(), 16) % self.DIM] += 1.0
        n = np.linalg.norm(v)
        return v / n if n else v

    def encode(self, texts):
        texts = list(texts)
        self.calls.append(len(texts))
        return np.vstack([self._vec(t) for t in texts]) if texts else np.zeros((0, self.DIM))


def _p(i: int, text: str, days: int = 0, symbol: str = "AAA", source: str = "edgar") -> ResearchPassage:
    return ResearchPassage(id=f"p{i}", source=source, symbol=symbol, accession=f"acc{i}", form="10-K",
                           section="risk", visible_date=T0 + timedelta(days=days), text=text)


def _corpus(**kw) -> ResearchCorpus:
    ps = [_p(0, "funding pressure rose across the quarter", 0),
          _p(1, "revenue growth in software segment", 1),
          _p(2, "dividend policy unchanged board said", 2),
          _p(3, "funding markets tightened again", 30)]
    return ResearchCorpus(ps, **kw)


def test_embeddings_need_extra_without_seam(monkeypatch):
    monkeypatch.setattr(rr, "embeddings_available", lambda: False)
    with pytest.raises(RuntimeError, match=r"\[rag\] extra"):
        _corpus(use_embeddings=True)


def test_injected_embedder_used_and_encoded_once_for_corpus(monkeypatch):
    monkeypatch.setattr(rr, "embeddings_available", lambda: False)   # seam bypasses the extra
    fake = FakeEmbedder()
    c = _corpus(use_embeddings=True, embedder=fake)
    assert fake.calls == [4]
    c.search("liquidity", T0 + timedelta(days=5), method="hybrid")
    assert fake.calls == [4, 1]            # one query encode, corpus not re-encoded
    c.search("liquidity", T0 + timedelta(days=5), method="tfidf")
    assert fake.calls == [4, 1]            # tfidf never touches the embedder


def test_embedding_ranker_recovers_synonym_tfidf_misses():
    """'liquidity' shares no token with any passage; only the embedding ranker links it to
    'funding', so hybrid with embeddings ranks p0 first."""
    as_of = T0 + timedelta(days=5)
    emb = _corpus(use_embeddings=True, embedder=FakeEmbedder()).search("liquidity", as_of, method="hybrid", k=3)
    assert emb[0].passage.id == "p0"
    # three rankers fused: the top score is at most 3 / (k + 1)
    assert emb[0].score <= 3 / (rr.RRF_K + 1) + 1e-12


def test_embedding_path_respects_point_in_time_and_filters():
    c = _corpus(use_embeddings=True, embedder=FakeEmbedder())
    hits = c.search("funding", T0 + timedelta(days=5), method="hybrid", k=10)
    assert "p3" not in {h.passage.id for h in hits}          # visible on day 30 only
    assert c.search("funding", T0 + timedelta(days=5), method="hybrid", symbol="ZZZ") == []
    assert c.search("funding", T0 - timedelta(days=1), method="hybrid") == []
    assert c.search("   ", T0 + timedelta(days=5), method="hybrid") == []


def test_embedding_rows_align_after_date_sort():
    """Passages are sorted by visible date before encoding; give them out of order and
    check the embedding row for each passage is the encoding of that passage's text."""
    fake = FakeEmbedder()
    ps = [_p(2, "dividend policy", 9), _p(0, "funding stress", 0), _p(1, "inflation cpi", 4)]
    c = ResearchCorpus(ps, use_embeddings=True, embedder=fake)
    for row, p in zip(c._emb, c.passages):
        assert np.allclose(row, fake._vec(c._doc_text(p)))


def test_empty_corpus_with_embeddings():
    c = ResearchCorpus([], use_embeddings=True, embedder=FakeEmbedder())
    assert len(c) == 0 and c.search("funding", T0, method="hybrid") == []


def test_unknown_method_and_naive_time_refused():
    c = _corpus()
    with pytest.raises(ValueError, match="unknown retrieval method"):
        c.search("x", T0, method="dense")
    with pytest.raises(ValueError, match="naive"):
        c.search("x", datetime(2024, 1, 2))


def test_duplicate_ids_refused():
    with pytest.raises(ValueError, match="duplicate"):
        ResearchCorpus([_p(0, "a"), _p(0, "b", 1)])


@settings(max_examples=40, deadline=None)
@given(days=st.lists(st.integers(0, 60), min_size=1, max_size=12),
       cut=st.integers(-1, 61), method=st.sampled_from(["tfidf", "hybrid"]))
def test_property_never_returns_future_passages(days, cut, method):
    words = ["funding", "liquidity", "inflation", "revenue", "dividend", "cash"]
    ps = [_p(i, f"{words[i % 6]} {words[(i * 5) % 6]} note", d) for i, d in enumerate(days)]
    c = ResearchCorpus(ps, use_embeddings=True, embedder=FakeEmbedder())
    as_of = T0 + timedelta(days=cut)
    hits = c.search("liquidity funding", as_of, k=20, method=method)
    assert all(h.passage.visible_date <= as_of for h in hits)
    assert len(hits) <= sum(1 for d in days if d <= cut)
    assert len({h.passage.id for h in hits}) == len(hits)


@given(st.lists(st.lists(st.integers(0, 9), unique=True, max_size=10), max_size=4))
def test_property_rrf_is_permutation_of_union(rankings):
    out = reciprocal_rank_fusion(rankings)
    assert sorted(out) == sorted({i for r in rankings for i in r})


# --------------------------------------------------------------------------- replay tapes
def test_tape_serves_in_order_then_repeats_last_and_replays_raises():
    t = Tape()
    t.put("k", "lbl", "return", [1])
    t.put("k", "lbl", "return", [2])
    assert [t.serve("k", "lbl") for _ in range(3)] == [[1], [2], [2]]
    first = t.serve("k", "lbl")
    first.append(99)                                    # served values are copies
    assert t.serve("k", "lbl") == [2]

    def boom():
        raise ValueError("boom")
    with pytest.raises(ValueError, match="boom"):
        t.call("e", "err", boom)
    with pytest.raises(ValueError, match="boom"):
        t.serve("e", "err")
    with pytest.raises(ReplayMissingPayload, match="nothing"):
        t.serve("absent", "nothing")
    assert t.misses == ["nothing"] and len(t) == 3


class _JsonModel:
    extra = "passthrough"

    def complete(self, system, prompt, *, deep):
        return f"{system}|{prompt}|{deep}"

    def complete_json(self, system, prompt, *, deep, schema):
        return '{"ok": true}'


class _PlainModel:
    def complete(self, system, prompt, *, deep):
        return "plain"


def test_recording_llm_round_trip_and_json_gating():
    rec = RecordingLLM(_JsonModel())
    assert rec.complete("s", "p", deep=True) == "s|p|True"
    assert rec.complete_json("s", "p", deep=False, schema={"a": 1}) == '{"ok": true}'
    assert rec.extra == "passthrough"
    rep = ReplayLLM(rec.tape, has_json=True)
    assert rep.complete("s", "p", deep=True) == "s|p|True"
    assert rep.complete_json("s", "p", deep=False, schema={"a": 1}) == '{"ok": true}'
    with pytest.raises(ReplayMissingPayload):
        rep.complete_json("s", "p", deep=False, schema={"a": 2})   # different schema, different key
    with pytest.raises(ReplayMissingPayload):
        rep.complete("s", "p", deep=False)
    assert not hasattr(RecordingLLM(_PlainModel()), "complete_json")
    assert not hasattr(ReplayLLM(Tape()), "complete_json")


def test_replay_llm_from_offline_recording_refused():
    with pytest.raises(ReplayMissingPayload, match="offline"):
        ReplayLLM.from_recording(types.SimpleNamespace(llm_tape=None))


def test_decision_fingerprint_drops_ids_keeps_count():
    assert decision_fingerprint(None) is None
    assert decision_fingerprint({"action": "buy", "evidence_ids": ["a", "b"]}) == {"action": "buy", "evidence_ids": 2}
    assert decision_fingerprint({"action": "hold"})["evidence_ids"] == 0


# --------------------------------------------------------------------------- edgar text
@settings(max_examples=60, deadline=None)
@given(text=st.text(alphabet=st.sampled_from(list("ab \n")), max_size=600),
       max_chars=st.integers(20, 120), overlap=st.integers(0, 19))
def test_property_chunk_text_bounded_substrings(text, max_chars, overlap):
    chunks = et.chunk_text(text, max_chars, overlap)
    assert all(0 < len(c) <= max_chars and c in text for c in chunks)
    if text.strip():
        assert chunks


def test_chunk_text_refuses_overlap_ge_max():
    with pytest.raises(ValueError, match="exceed"):
        et.chunk_text("x" * 50, 10, 10)
    assert et.chunk_text("", 10, 2) == []


def test_parse_accepted_variants():
    assert et._parse_accepted(None) is None
    assert et._parse_accepted("not a date") is None
    assert et._parse_accepted("2024-02-01T21:05:00").tzinfo == UTC
    assert et._parse_accepted("2024-02-01T16:05:00-05:00") == datetime(2024, 2, 1, 21, 5, tzinfo=UTC)


def _edgar_fetch(docs_fail: bool = False):
    sub = {"filings": {"recent": {"form": ["10-K", "8-K", "8-K", "S-1"],
                                  "accessionNumber": ["a-1", "a-2", "a-3", "a-4"],
                                  "primaryDocument": ["k.htm", "e.htm", "f.htm", "s.htm"],
                                  "items": ["", "5.02", "2.02,9.01", ""],
                                  "acceptanceDateTime": ["2024-02-01T21:00:00.000Z", "2024-03-01T21:00:00.000Z",
                                                         "2024-04-01T21:00:00.000Z", "2024-01-01T00:00:00.000Z"]},
                       "files": [{"name": "page2.json"}]}}
    page2 = {"form": ["10-Q"], "accessionNumber": ["a-0"], "acceptanceDateTime": [None]}
    seen: list[str] = []

    def fetch(url: str) -> bytes:
        seen.append(url)
        if url == et.TICKERS_URL:
            return json.dumps({"0": {"ticker": "BRK.B", "cik_str": 1067983}}).encode()
        if url.endswith("CIK0001067983.json"):
            return json.dumps(sub).encode()
        if url.endswith("page2.json"):
            return json.dumps(page2).encode()
        if docs_fail:
            raise OSError("reset")
        return b"<p>Item 2.02 Results of Operations</p><p>" + b"Revenue rose. " * 40 + b"</p>"
    return fetch, seen


def test_edgar_index_filters_forms_items_and_dot_dash_ticker():
    fetch, _ = _edgar_fetch()
    p = et.EdgarProvider(fetch=fetch, min_interval=0)
    assert p.cik("brk-b") == "0001067983"
    rows = p.filing_index("BRK-B")
    # S-1 dropped, 8-K without a kept item dropped, undated 10-Q from page 2 sorted last
    assert [r["accession"] for r in rows] == ["a-1", "a-3", "a-0"]
    assert rows[-1]["accepted"] is None and rows[-1]["doc"] == ""
    n = p.requests
    p.filing_index("BRK-B")
    assert p.requests == n                      # memoised
    assert et.EdgarProvider(fetch=fetch, min_interval=0, ciks={"ZZ": "7"}).cik("zz") == "0000000007"
    assert p.cik("NOPE") is None


def test_edgar_sections_point_in_time_never_fetch_future(tmp_path):
    fetch, seen = _edgar_fetch()
    p = et.EdgarProvider(fetch=fetch, min_interval=0, cache_dir=tmp_path)
    secs = p.sections("BRK-B", datetime(2024, 3, 15))          # naive read as UTC
    assert all(s.visible_date <= datetime(2024, 3, 15, tzinfo=UTC) for s in secs)
    assert not any("f.htm" in u for u in seen)                 # the April 8-K was never fetched
    assert (tmp_path / "a-1.txt").exists()                     # cached on disk

    def no_fetch(url):
        raise AssertionError(url)
    p2 = et.EdgarProvider(fetch=no_fetch, min_interval=0, cache_dir=tmp_path)
    assert p2.document({"accession": "a-1", "cik": "1", "doc": "k.htm"}) == \
        (tmp_path / "a-1.txt").read_text(encoding="utf-8")


def test_edgar_unreadable_document_loses_sections_not_ticker():
    fetch, _ = _edgar_fetch(docs_fail=True)
    p = et.EdgarProvider(fetch=fetch, min_interval=0)
    assert p.sections("BRK-B", datetime(2025, 1, 1, tzinfo=UTC)) == []


def test_edgar_from_config_off_by_default():
    assert et.EdgarProvider.from_config({}) is None


# --------------------------------------------------------------------------- local model client
def test_local_llm_config_refusals():
    with pytest.raises(ValueError, match="local_llm_model"):
        LocalLLM({})
    with pytest.raises(ValueError, match="> 0"):
        LocalLLM({"local_llm_model": "m", "local_llm_timeout_s": 0})
    m = LocalLLM({"local_llm_model": "m"})
    assert m.model_for(True) == "m" and m.estimate_cost(True, 10_000) == 0.0


def test_served_matches_latest_tag():
    assert served_matches("qwen", "qwen:latest") and served_matches("qwen:latest", "qwen")
    assert not served_matches("qwen:7b", "qwen:14b") and not served_matches("qwen", None)


@pytest.mark.parametrize("exc, counter", [
    (urllib.error.URLError(socket.timeout("slow")), "timeouts"),
    (TimeoutError("slow"), "timeouts"),
    (urllib.error.URLError(ConnectionRefusedError("no")), None),
    (ValueError("reply body is not a JSON object"), None),
])
def test_local_llm_failures_fall_back_and_count(monkeypatch, exc, counter):
    m = LocalLLM({"local_llm_model": "m"})

    def fail(body):
        raise exc
    monkeypatch.setattr(m, "_post", fail)
    assert m.complete("s", "p", deep=False) is None
    assert m.usage.errors == 1 and m.last_call is None
    if counter:
        assert getattr(m.usage, counter) == 1


def test_local_llm_non_object_body_refused(monkeypatch):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"[1, 2]"
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: _Resp())
    m = LocalLLM({"local_llm_model": "m"})
    assert m.complete_json("s", "p", deep=False, schema={"type": "object"}) is None
    assert m.usage.errors == 1


def test_local_llm_drift_strict_and_lenient():
    strict = LocalLLM({"local_llm_model": "m:7b"})
    assert strict.read_response({"model": "m:14b", "message": {"content": "hi"}}) is None
    assert strict.last_call["model_drift"] is True
    lenient = LocalLLM({"local_llm_model": "m:7b", "llm_strict_model": False})
    assert lenient.read_response({"model": "m:14b", "message": {"content": " hi "}}) == "hi"
    assert lenient.read_response({"message": "not a dict"}) is None


# --------------------------------------------------------------------------- tracing without the OTel SDK
def _fake_otel(monkeypatch):
    """Minimal stand-ins for the opentelemetry SDK modules export_otel imports."""
    rec = {"started": [], "ended": [], "status": [], "shutdown": 0, "exported_via": None}

    class FakeSpan:
        def __init__(self, name, context, start_time, attributes):
            self.name, self.context, self.start, self.attributes = name, context, start_time, attributes
            rec["started"].append(self)

        def set_status(self, status):
            rec["status"].append((self.name, status))

        def end(self, end_time):
            rec["ended"].append((self.name, end_time))

    class FakeTracer:
        def start_span(self, name, context=None, start_time=None, attributes=None):
            return FakeSpan(name, context, start_time, attributes)

    class TracerProvider:
        def __init__(self, resource):
            self.resource = resource

        def add_span_processor(self, p):
            rec["exported_via"] = p.exporter

        def get_tracer(self, name):
            return FakeTracer()

        def shutdown(self):
            rec["shutdown"] += 1

    class SimpleSpanProcessor:
        def __init__(self, exporter):
            self.exporter = exporter

    mods = {
        "opentelemetry": types.ModuleType("opentelemetry"),
        "opentelemetry.sdk": types.ModuleType("opentelemetry.sdk"),
        "opentelemetry.sdk.resources": types.SimpleNamespace(Resource=types.SimpleNamespace(create=dict)),
        "opentelemetry.sdk.trace": types.SimpleNamespace(TracerProvider=TracerProvider),
        "opentelemetry.sdk.trace.export": types.SimpleNamespace(SimpleSpanProcessor=SimpleSpanProcessor),
        "opentelemetry.trace": types.SimpleNamespace(
            Status=lambda code, desc: (code, desc), StatusCode=types.SimpleNamespace(ERROR="ERROR"),
            set_span_in_context=lambda parent: ("ctx", parent.name)),
    }
    for k, v in mods.items():
        monkeypatch.setitem(sys.modules, k, v)
    return rec


def test_export_otel_parents_errors_and_attribute_coercion(monkeypatch):
    rec = _fake_otel(monkeypatch)
    tr = Tracer()
    with tr.span("decision:AAA", obj={"x": 1}, n=3):
        with tr.span("agent:tech"):
            pass
        with pytest.raises(RuntimeError):
            with tr.span("agent:risk"):
                raise RuntimeError("bad")
    sentinel = object()
    assert export_otel(tr, exporter=sentinel) == 3
    assert rec["exported_via"] is sentinel and rec["shutdown"] == 1
    by = {s.name: s for s in rec["started"]}
    assert by["decision:AAA"].context is None
    assert by["agent:tech"].context == ("ctx", "decision:AAA")
    assert by["decision:AAA"].attributes == {"obj": "{'x': 1}", "n": 3}
    assert rec["status"] == [("agent:risk", ("ERROR", "RuntimeError: bad"))]
    ends = dict(rec["ended"])
    assert ends["decision:AAA"] >= max(ends["agent:tech"], ends["agent:risk"])   # parent encloses children
    assert all(e >= by[n].start for n, e in rec["ended"])


def test_configure_json_logging_formats_json_and_text():
    root = logging.getLogger("agentic_trader")
    saved = (root.handlers[:], root.level, root.propagate)
    try:
        configure_json_logging(logging.INFO)
        h = root.handlers[0]

        def mk(msg):
            return logging.LogRecord("agentic_trader.x", logging.INFO, __file__, 1, msg, None, None)
        assert json.loads(h.format(mk('{"span": "a"}')))["span"] == "a"
        assert json.loads(h.format(mk("{not json")))["message"] == "{not json"
        out = json.loads(h.format(mk("plain")))
        assert out["message"] == "plain" and out["level"] == "INFO" and root.propagate is False
    finally:
        root.handlers, root.level, root.propagate = saved


def test_stage_quantile_beyond_last_bucket_returns_max():
    m = Metrics()
    m.observe("stage_latency_ms", 50_000.0, stage="slow")
    assert m.stage_quantile("slow", 0.99) == 50_000.0
    assert m.stage_quantile("absent", 0.5) is None
