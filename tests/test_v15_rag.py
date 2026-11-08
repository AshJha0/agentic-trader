"""v0.15 research RAG (PLAN.md 3.4-3.7, 3.9): point-in-time corpus, hybrid retrieval,
citations and their audit, the retrieval evaluation gate, the runbook ablation trial."""
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone

import pytest

from agentic_trader.agentic import research_rag as rr
from agentic_trader.evaluation import TRIALS

UTC = timezone.utc


@dataclass(frozen=True)
class FilingSection:            # the shared contract, duplicated here as a fixture
    symbol: str
    accession: str
    form: str
    section: str
    visible_date: datetime
    text: str


SECS = [
    FilingSection("ZZZ", "acc-1", "10-K", "risk_factors", datetime(2024, 2, 1, 21, tzinfo=UTC),
                  "Copper supply shortages could stop our cable plant.\n\nInterest rate rises raise our funding cost."),
    FilingSection("ZZZ", "acc-2", "10-Q", "mda", datetime(2024, 5, 1, 21, tzinfo=UTC),
                  "Cable revenue fell because copper prices jumped."),
    FilingSection("YYY", "acc-3", "10-K", "legal", datetime(2024, 3, 1, 21, tzinfo=UTC),
                  "A copper theft lawsuit is pending."),
]
STMT = rr.CentralBankStatement("FOMC", datetime(2024, 9, 18, 18, tzinfo=UTC), "fixture",
                               "The Committee lowered the federal funds rate by half a point.")


def corpus(**kw):
    return rr.ResearchCorpus.build(SECS, [STMT], **kw)


# ---- 3.4 corpus and point in time
def test_passages_carry_metadata_and_paragraph_ids():
    c = corpus()
    assert len(c) == 5
    p = c.get("acc-1#risk_factors#1")
    assert p.metadata == {"symbol": "ZZZ", "accession": "acc-1", "visible_date": "2024-02-01T21:00:00+00:00",
                          "section": "risk_factors"}
    assert c.get("FOMC-2024-09-18#statement#0").source == "central_bank"


@pytest.mark.parametrize("method", ["tfidf", "hybrid"])
def test_point_in_time_filter_never_returns_future_passages(method):
    c = corpus()
    as_of = datetime(2024, 4, 1, tzinfo=UTC)
    hits = c.search("copper cable revenue", as_of, k=10, method=method)
    assert hits and all(h.passage.visible_date <= as_of for h in hits)
    assert "acc-2#mda#0" not in {h.passage.id for h in hits}
    assert "acc-2#mda#0" in {h.passage.id for h in c.search("copper cable revenue", date(2024, 5, 2), method=method)}
    assert c.search("copper", datetime(2024, 1, 1, tzinfo=UTC)) == []


def test_release_time_is_exact_and_naive_times_refused():
    c = corpus()
    before = c.search("federal funds rate", datetime(2024, 9, 18, 17, 59, tzinfo=UTC), k=10)
    after = c.search("federal funds rate", datetime(2024, 9, 18, 18, 0, tzinfo=UTC), k=10)
    assert "FOMC-2024-09-18#statement#0" not in {h.passage.id for h in before}
    assert after[0].passage.id == "FOMC-2024-09-18#statement#0"
    with pytest.raises(ValueError):
        c.search("x", datetime(2024, 1, 1))


def test_idf_fitted_on_visible_passages_only():
    c = corpus()
    early = c.search("copper", datetime(2024, 2, 2, tzinfo=UTC), k=5)
    # only acc-1 is visible; the ranking must equal a corpus built from acc-1 alone
    alone = rr.ResearchCorpus.build(SECS[:1]).search("copper", datetime(2024, 2, 2, tzinfo=UTC), k=5)
    assert [(h.passage.id, h.score) for h in early] == [(h.passage.id, h.score) for h in alone]


def test_symbol_filter_and_central_bank_loader(tmp_path):
    f = tmp_path / "cb.json"
    f.write_text(json.dumps([{"bank": "ECB", "released": "2024-06-06T12:15:00+00:00", "title": "t",
                              "text": "Deposit rate cut.\n\nInflation easing."}]), encoding="utf-8")
    sts = rr.load_central_bank_statements(tmp_path)
    assert sts[0].accession == "ECB-2024-06-06" and sts[0].released.tzinfo is not None
    assert len(rr.passages_from_statements(sts)) == 2
    f.write_text(json.dumps([{"bank": "XYZ", "released": "2024-06-06T12:15:00+00:00", "text": "x"}]), encoding="utf-8")
    with pytest.raises(ValueError):
        rr.load_central_bank_statements(f)
    hits = corpus().search("copper", date(2025, 1, 1), symbol="YYY")
    assert {h.passage.symbol for h in hits} == {"YYY"}


# ---- 3.5 hybrid
def test_reciprocal_rank_fusion():
    assert rr.reciprocal_rank_fusion([[1, 2, 3], [3, 1, 2]]) == [1, 3, 2]
    assert rr.reciprocal_rank_fusion([[5], [7]]) == [5, 7]


def test_embeddings_are_optional():
    if rr.embeddings_available():
        pytest.skip("[rag] extra installed; the missing-extra path is not testable here")
    with pytest.raises(RuntimeError, match=r"\[rag\]"):
        corpus(use_embeddings=True)


def test_hybrid_with_local_embeddings():
    pytest.importorskip("sentence_transformers")
    hits = corpus(use_embeddings=True).search("copper shortage", date(2025, 1, 1), method="hybrid")
    assert hits


# ---- 3.6 citations
def test_document_blocks_and_request_payload():
    hits = corpus().search("copper", date(2025, 1, 1), k=2)
    req = rr.build_cited_request("What risks?", hits)
    blocks = req["messages"][0]["content"]
    assert [b["type"] for b in blocks] == ["document", "document", "text"]
    assert all(b["citations"] == {"enabled": True} for b in blocks[:2])
    assert blocks[0]["title"] == hits[0].passage.id
    assert json.loads(blocks[0]["context"])["accession"] == hits[0].passage.accession


def test_citation_audit_requires_every_quote_to_map_to_a_passage():
    hits = corpus().search("copper", date(2025, 1, 1), k=3)
    p = hits[0].passage
    good = [{"quote": p.text[:20], "passage_id": p.id}]
    assert rr.audit_citations(good, hits).ok
    bad = good + [{"quote": "invented sentence", "passage_id": p.id}, {"quote": "copper", "passage_id": "nope"}]
    a = rr.audit_citations(bad, hits)
    assert not a.ok and len(a.failures) == 2
    assert not rr.audit_citations([], hits).ok
    resp = {"content": [{"type": "text", "text": "x",
                         "citations": [{"type": "char_location", "cited_text": p.text[:10], "document_index": 0}]}]}
    assert rr.audit_citations(rr.citations_from_response(resp), hits).ok
    resp["content"][0]["citations"][0]["document_index"] = 9
    assert not rr.audit_citations(rr.citations_from_response(resp), hits).ok


# ---- 3.7 evaluation and gate
def test_question_set_is_well_formed_and_gold_is_visible():
    c, qs = rr.load_eval_corpus(), rr.load_questions()
    assert len(qs) == 100 and len({q.id for q in qs}) == 100
    for q in qs:
        for g in q.gold:
            p = c.get(g)
            assert p is not None and p.accession == q.gold_accession and p.visible_date <= q.as_of


def test_retrieval_evaluation_and_gate():
    c, qs = rr.load_eval_corpus(), rr.load_questions()
    reps = [rr.evaluate_retrieval(c, qs, m) for m in ("tfidf", "hybrid")]
    assert all(r.passes_gate for r in reps)
    assert "| tfidf | 100 |" in rr.comparison_table(reps)
    retrieve = rr.analyst_retriever(c, qs)
    assert retrieve.report.recall_at_5 >= rr.RECALL_GATE
    assert retrieve("Fed cut", date(2025, 1, 1))


def test_gate_refuses_retrieval_below_threshold():
    c = rr.load_eval_corpus()
    wrong = [rr.Question("x", "anvil steel supplier", datetime(2026, 1, 1, tzinfo=UTC), ("no-such#id#0",), "none")]
    with pytest.raises(rr.RetrievalGateError):
        rr.analyst_retriever(c, wrong)


# ---- 3.9 runbook ablation
def test_runbook_trial_registered():
    assert any(t.name == rr.RUNBOOK_TRIAL_NAME and t.version == "v0.15" for t in TRIALS)


def test_runbook_ablation_one_cell_changes_nothing_on_rules_path():
    r = rr.runbook_rag_ablation(symbols=("AAPL",), dates=(date(2024, 3, 1),))
    assert r["cells"] == 1 and r["changed"] == 0 and r["rows"][0]["with_rag"] is not None


@pytest.mark.slow
def test_runbook_ablation_full_grid():
    r = rr.runbook_rag_ablation()
    assert r["cells"] == 9 and r["changed"] == 0
