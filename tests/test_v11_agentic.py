"""v0.11 (tier-2 review, batch 3): anonymised harness prompts, single-use plans, per-attempt
budget admission, cross-process memory catch-up."""
from datetime import date

import numpy as np
import pytest

from agentic_trader import make_config
from agentic_trader.memory import DecisionMemory


class Recorder:
    """An LLM stub that records every prompt and answers with a fixed JSON object."""

    def __init__(self, reply="{}"):
        self.prompts: list[tuple[str, str]] = []
        self.reply = reply

    def complete(self, system, prompt, *, deep):
        self.prompts.append((system, prompt))
        return self.reply


def test_critic_reporter_and_planner_prompts_carry_no_name_or_date_under_anonymisation():
    from agentic_trader.agentic.critic import Critic
    from agentic_trader.agentic.domain import Finding
    from agentic_trader.agentic.planner import propose_plan
    from agentic_trader.agentic.reporter import llm_narrative
    from agentic_trader.graph import TradingGraph

    cfg = make_config(memory_path=None, llm_anonymize=True)
    g = TradingGraph(cfg, llm=Recorder("{}"))               # anonymisation is attached only with a model
    state, dec = g.propagate("NVDA", date(2024, 3, 1))
    assert state.anon is not None and state.decision is not None
    rec = Recorder('{"concerns": [], "confidence_multiplier": 1.0}')
    Critic(cfg, rec)._llm_critique(state, [])
    rec2 = Recorder("A summary.")
    llm_narrative(rec2, state, {"last_close": 812.5, "target_weight": 0.5, "realized_vol_20d_annual": 0.3}, [])
    for r in (rec, rec2):
        joined = " ".join(p for _, p in r.prompts)
        assert "NVDA" not in joined and "2024-03-01" not in joined and "812.5" not in joined
    assert "STOCK_X" in " ".join(p for _, p in rec.prompts)
    # the planner names neither the instrument nor the date when anonymising
    from agentic_trader.agentic.domain import Role, Task
    from agentic_trader.agentic.servers import DeskTools, build_registry
    from agentic_trader.data import SyntheticProvider
    reg = build_registry(DeskTools(SyntheticProvider(cfg), cfg))
    rec3 = Recorder('{"steps": []}')
    propose_plan(rec3, Task("NVDA", date(2024, 3, 1), Role.TRADER, question="x" * 900), state.instrument,
                 ["technical"], reg, anonymize=True)
    p = rec3.prompts[0][1]
    assert "NVDA" not in p and "2024-03-01" not in p and "the instrument (equity)" in p and p.count("x") < 600


def test_a_plan_is_consumed_by_its_ticket_and_the_desk_lock_is_shared_by_book_views():
    from agentic_trader.agentic.servers import DeskTools, ticket_from_plan
    from agentic_trader.data import SyntheticProvider
    cfg = make_config(memory_path=None)
    desk = DeskTools(SyntheticProvider(cfg), cfg)
    plan = desk.plan("AAPL", "2024-03-01", 0.2)
    ticket = desk.submit_order(**ticket_from_plan(plan))
    assert ticket["plan_known"] is True and desk.ticketed[plan["plan_id"]] == ticket["id"]
    with pytest.raises(ValueError, match="already ticketed"):
        desk.submit_order(**ticket_from_plan(plan))
    assert len(desk.orders) == 1 and plan["plan_id"] not in desk.plans
    view = desk.for_book({"AAPL": 0.2})
    assert view._lock is desk._lock and view.ticketed is desk.ticketed
    with pytest.raises(ValueError, match="already ticketed"):
        view.submit_order(**ticket_from_plan(plan))


def test_hard_budget_reserves_every_retry_so_timeouts_cannot_overshoot_the_cap(monkeypatch):
    from test_v08_agents import _APITimeoutError, _budgeted, _hammer

    # every attempt times out and is billed at its maximum; with two retries a call may bill
    # three attempts, and each one must be admitted against the cap before it is made
    llm, recorded = _budgeted(monkeypatch, "hard", fail=_APITimeoutError("t"), llm_max_retries=2,
                              llm_retry_backoff_s=0.0)
    worst = llm.inner.estimate_cost(True)
    _hammer(llm)
    assert llm.spent_usd <= 1.0 + 1e-9 and llm.reserved_usd == pytest.approx(0.0, abs=1e-12)
    assert llm.inner.usage.timeouts >= 2 and llm.spent_usd == pytest.approx(llm.inner.usage.timeouts * worst)
    assert llm.inner.estimate_cost(True, prompt_chars=300_000) > worst   # a long prompt reserves more


def test_memory_instances_on_one_file_see_each_others_records_and_resolutions(tmp_path):
    path = tmp_path / "memory.jsonl"
    a, b = DecisionMemory(path), DecisionMemory(path)
    d0 = date(2024, 1, 2)
    a.record("X", d0, "BUY", 0.5, 100.0, "t", horizon_days=5, provider="synthetic")
    idx = [date(2024, 1, 2 + i) for i in range(12)]
    closes = np.linspace(100.0, 111.0, 12)
    import pandas as pd
    hist = pd.DataFrame({"Close": closes}, index=pd.DatetimeIndex(idx))
    assert b.resolve("X", date(2024, 1, 13), hist, provider="synthetic") == 1      # b sees a's record
    assert a.track_record("X", date(2024, 1, 14), provider="synthetic")["n"] == 1  # a sees b's resolution
    assert len(a.entries) == 1 and len(b.entries) == 1 and a.skipped_lines == b.skipped_lines == 0
