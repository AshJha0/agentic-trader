"""Batch-friendly loop (plan item 1.5b): 15 names advance together, one batch per pass."""

from types import SimpleNamespace

import pytest

from agentic_trader import make_config, run_agent_backtest
from agentic_trader.batch import BatchLLM, FakeBatchBackend, PassPending, run_jobs, walk_forward_jobs


class StubLLM:
    """Canned replies per role (as in test_v13_batch), so every agent's LLM branch runs."""

    def complete(self, system, prompt, *, deep):
        if "Researcher" in system:
            return "Evidence-based argument."
        if "Facilitator" in system:
            return '{"winner": "bull", "score": 0.6, "conviction": 0.7, "summary": "Bull wins."}'
        if "Trader." in system:
            return (
                '{"action": "BUY", "target_weight": 0.5, "confidence": 0.7, "stop_loss": null, '
                '"take_profit": null, "horizon_days": 5, "rationale": "r"}'
            )
        if "Risk Analyst" in system:
            return '{"recommended_weight": 0.4, "argument": "fine"}'
        if "Portfolio Manager" in system:
            return '{"target_weight": 0.3, "confidence": 0.6, "rationale": "pm"}'
        return '{"signal": 0.5, "confidence": 0.8, "summary": "LLM view", "key_points": ["a"]}'


STUB = StubLLM()


def respond(params):
    return STUB.complete(params["system"], params["prompt"], deep=params["deep"])


def key(decisions):
    return [(d.symbol, d.as_of, d.action, d.target_weight, d.source) for d in decisions]


CFG = make_config(memory_path=None)
NAMES = ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "JPM", "XOM", "JNJ", "PG", "SPY", "TLT", "GLD", "EURUSD", "USDJPY")
FEW = NAMES[:3]
START, END, EVERY = "2024-01-01", "2024-02-05", 5  # 25 bars -> 5 decision dates per name
DATES = 5


def decisions(reports):
    return [d for r in reports for d in r.decisions]


def direct(names):
    return [d for s in names for d in run_agent_backtest(s, START, END, CFG, rebalance_every=EVERY, llm=STUB).decisions]


def one_name_passes(sym, tmp):
    """The 1.5 loop (``run_until_complete``) on one name: about stages x dates passes."""
    llm = BatchLLM(None, FakeBatchBackend(respond), tmp / f"{sym}.jsonl")
    passes = []
    llm.run_until_complete(
        lambda: passes.append(1) or run_agent_backtest(sym, START, END, CFG, rebalance_every=EVERY, llm=llm), max_passes=80
    )
    return len(passes), sum(len(b) for b in llm.backend.batches)


def joint(names, tmp, *, stop):
    backend = FakeBatchBackend(respond, shuffle=True)
    llm = BatchLLM(None, backend, tmp / f"joint-{stop}.jsonl")
    reports = walk_forward_jobs(llm, names, START, END, CFG, rebalance_every=EVERY, stop_at_pending=stop)
    return SimpleNamespace(
        llm=llm, passes=len(backend.batches) + 1, requests=sum(len(b) for b in backend.batches), decisions=decisions(reports)
    )


@pytest.mark.parametrize("stop", [False, True])
def test_three_names_equal_direct_and_share_passes(tmp_path, stop):
    got = joint(FEW, tmp_path, stop=stop)
    assert len(got.decisions) == len(FEW) * DATES and all(d.source == "llm" for d in got.decisions)
    assert key(got.decisions) == key(direct(FEW))  # shuffled result order is harmless
    assert got.llm.summary["failed"] == 0
    singles = [one_name_passes(s, tmp_path) for s in FEW]
    if stop:  # no speculative request: fewer requests than the names run one by one
        assert got.requests < sum(r for _, r in singles)
    else:  # the names share every batch: the slowest name's passes, not the sum
        assert got.passes <= max(p for p, _ in singles)


@pytest.mark.slow
def test_fifteen_names_need_one_names_passes(tmp_path):
    """PLAN 1.5b acceptance. Measured 2026-11-09: one name alone 33-34 passes (about 6.8 stages x
    5 dates), so 15 names one after another 505; together 34 (default) or 41 with
    ``stop_at_pending`` (3,748 requests instead of 12,115)."""
    singles = [one_name_passes(s, tmp_path) for s in NAMES]
    slowest = max(p for p, _ in singles)
    spec = joint(NAMES, tmp_path, stop=False)
    assert key(spec.decisions) == key(direct(NAMES))
    assert spec.passes <= slowest  # not sum(passes) = names x stages x dates
    assert spec.passes * len(NAMES) <= sum(p for p, _ in singles) + len(NAMES)
    lean = joint(NAMES, tmp_path, stop=True)
    assert key(lean.decisions) == key(spec.decisions)
    assert lean.requests < spec.requests / 2 and lean.passes <= slowest + DATES * 2


def test_offsets_run_as_parallel_jobs(tmp_path):
    llm = BatchLLM(None, FakeBatchBackend(respond), tmp_path / "s.jsonl")
    reports = walk_forward_jobs(llm, FEW[:2], START, END, CFG, rebalance_every=EVERY, offsets=(0, 2))
    for r, (sym, off) in zip(reports, [(s, o) for s in FEW[:2] for o in (0, 2)]):
        ref = run_agent_backtest(sym, START, END, CFG, rebalance_every=EVERY, llm=STUB, rebalance_offset=off)
        assert key(r.decisions) == key(ref.decisions)


def test_default_backtest_path_ignores_stop_check():
    a = run_agent_backtest("AAPL", START, END, CFG, rebalance_every=EVERY, llm=STUB)
    b = run_agent_backtest("AAPL", START, END, CFG, rebalance_every=EVERY, llm=STUB, stop_check=lambda: False)
    assert key(a.decisions) == key(b.decisions)
    with pytest.raises(PassPending):
        run_agent_backtest("AAPL", START, END, CFG, rebalance_every=EVERY, llm=STUB, stop_check=lambda: True)


def test_run_jobs_settles_independent_jobs_and_caps_passes(tmp_path):
    llm = BatchLLM(None, FakeBatchBackend(lambda p: p["prompt"].upper()), tmp_path / "s.jsonl")

    def chain(name, steps):
        def job(stop):
            text = name
            for _ in range(steps):
                text = llm.complete("s", text + "-", deep=False) or text
                if stop():
                    raise PassPending
            return text

        return job

    out = run_jobs(llm, [chain("a", 3), chain("b", 1), chain("c", 3)])
    assert out == ["A---", "B-", "C---"]
    assert llm.submissions == 3  # the longest chain, not 3 + 1 + 3
    with pytest.raises(RuntimeError):
        run_jobs(
            BatchLLM(None, FakeBatchBackend(lambda p: p["prompt"] + "x"), tmp_path / "t.jsonl"),
            [lambda stop: (_ for _ in ()).throw(PassPending)],
            max_passes=2,
        )
