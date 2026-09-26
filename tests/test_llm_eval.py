"""LLM-evaluation plumbing, tested offline with stand-in models: prompt
anonymisation, cost accounting, the shared thread-safe budget, and parallel
evaluation."""
import json
import re
import threading
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from agentic_trader import Instrument, TradingGraph, evaluate, make_config
from agentic_trader.anonymize import Anonymizer
from agentic_trader.cli import main
from agentic_trader.llm import BudgetedLLM, UsageTracker, llm_usage
from agentic_trader.memory import DecisionMemory

CFG = make_config(memory_path=None)
QUIET = dict(memory=DecisionMemory(None), on_event=lambda *_: None)


# ------------------------------------------------------------ anonymizer
def test_anonymizer_equity_names_dates_prices():
    a = Anonymizer(Instrument.parse("AAPL"), date(2024, 3, 1), 180.0)
    text = "AAPL beat on 2024-02-28; AAPLX and XAAPL untouched; report 2023-12-31, as of 2024-03-01"
    s = a.scrub(text)
    assert re.search(r"(?<![A-Za-z0-9])AAPL(?![A-Za-z0-9])", s) is None
    assert s.startswith("STOCK_X beat on D-2")
    assert "AAPLX" in s and "XAAPL" in s                  # only whole tokens are replaced
    assert "D-61" in s and s.endswith("as of D0")
    assert a.px(180.0) == 100.0 and a.unpx(95.0) == pytest.approx(171.0)
    assert a.facts({"close": 180.0, "rsi14": 70.0, "sma50": 171.0}) == {"close": 100.0, "rsi14": 70.0, "sma50": 95.0}
    assert a.restore({"k": ["STOCK_X up"], "n": 1}) == {"k": ["AAPL up"], "n": 1}
    assert a.scrub("bad date 2024-13-45 stays") == "bad date 2024-13-45 stays"


def test_anonymizer_fx_pair_and_codes():
    a = Anonymizer(Instrument.parse("EURUSD"), date(2024, 3, 1), 1.08)
    s = a.scrub("EUR/USD rallies; EURUSD=X feed; USD weakens vs EUR; EURUSD spot")
    assert re.search(r"\b(EUR|USD)\b", s) is None
    assert "CCY_BASE/CCY_QUOTE rallies" in s and "PAIR_X feed" in s and "CCY_QUOTE weakens vs CCY_BASE" in s
    assert a.restore("buy CCY_BASE / sell CCY_QUOTE on CCY_BASE/CCY_QUOTE") == "buy EUR / sell USD on EUR/USD"
    with pytest.raises(ValueError):
        Anonymizer(Instrument.parse("EURUSD"), date(2024, 3, 1), 0.0)


class Recorder:
    """Stand-in model: records every prompt and answers like a real trader would."""

    def __init__(self, trader_stop=95.0):
        self.prompts, self.lock, self.trader_stop = [], threading.Lock(), trader_stop

    def complete(self, system, prompt, *, deep):
        with self.lock:
            self.prompts.append(prompt)
        if "Trader." in system:
            return json.dumps({"action": "BUY", "target_weight": 0.8, "confidence": 0.6,
                               "stop_loss": self.trader_stop, "take_profit": 110,
                               "horizon_days": 10, "rationale": "STOCK_X looks strong"})
        return None


@pytest.mark.parametrize("symbol", ["AAPL", "USDJPY"])
def test_anonymized_prompts_leak_no_name_date_or_price(symbol):
    rec = Recorder()
    g = TradingGraph(make_config(CFG, llm_anonymize=True), llm=rec, **QUIET)
    st, d = g.propagate(symbol, "2024-03-01", current_weight=0.2)
    assert len(rec.prompts) >= 10
    ins = st.instrument
    names = [ins.symbol] + ([ins.base, ins.quote] if ins.is_fx else [])
    last = st.last_price
    price_strings = {f"{last:.5g}", f"{last:.6g}", f"{last:.4g}"}
    for p in rec.prompts:
        for n in names:
            assert re.search(rf"(?<![A-Za-z0-9]){n}(?![A-Za-z0-9])", p) is None, (n, p[:300])
        assert re.search(r"\b20\d\d-\d\d-\d\d\b", p) is None
        assert not any(s in p for s in price_strings), p[:300]
    # The trader answered in rebased units: stop 95 -> 95% of the real last close.
    if not ins.is_fx:
        assert st.proposal.stop_loss == pytest.approx(0.95 * last)
        assert st.proposal.rationale == "AAPL looks strong"      # name restored for the audit trail


def test_anonymization_is_off_without_an_llm_and_by_default():
    st, _ = TradingGraph(make_config(CFG, llm_anonymize=True), **QUIET).propagate("AAPL", "2024-03-01")
    assert st.anon is None                                       # rules have no memory to leak from
    rec = Recorder()
    TradingGraph(CFG, llm=rec, **QUIET).propagate("AAPL", "2024-03-01")
    assert any("AAPL" in p for p in rec.prompts)


# -------------------------------------------------------- cost tracking
def test_usage_tracker_prices_by_serving_model():
    u = UsageTracker()
    u.add("claude-opus-5", SimpleNamespace(input_tokens=1_000_000, output_tokens=100_000,
                                           cache_read_input_tokens=0, cache_creation_input_tokens=0))
    u.add("claude-haiku-4-5", SimpleNamespace(input_tokens=2_000_000, output_tokens=0))
    u.add("some-future-model", SimpleNamespace(input_tokens=5, output_tokens=5))
    u.count("errors")
    s = u.summary()
    assert s["calls"] == 3 and s["errors"] == 1
    assert s["by_model"]["claude-opus-5"]["cost_usd"] == pytest.approx(5.0 + 2.5)
    assert s["by_model"]["claude-haiku-4-5"]["cost_usd"] == pytest.approx(2.0)
    assert s["by_model"]["some-future-model"]["cost_usd"] is None   # unknown price: not guessed
    assert s["cost_usd"] == pytest.approx(9.5)


def test_budget_is_thread_safe():
    class Slow:
        def complete(self, *a, **k):
            return None
    b = BudgetedLLM(Slow(), 50)
    threads = [threading.Thread(target=lambda: [b.complete("s", "p", deep=True) for _ in range(40)])
               for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert b.calls == 50 and b.refused == 8 * 40 - 50


def test_llm_usage_helper_handles_non_tracking_models():
    assert llm_usage(None) is None and llm_usage(Recorder()) is None


# --------------------------------------------------- parallel evaluation
def test_parallel_evaluation_matches_sequential():
    kw = dict(symbols=["AAPL", "EURUSD", "MSFT"], periods={"q": ("2024-01-02", "2024-03-28")},
              config=CFG, rebalance_every=10)
    seq, par = evaluate(**kw), evaluate(**kw, workers=3)
    pd.testing.assert_frame_equal(seq.rows, par.rows)
    assert "usage" not in seq.meta                    # offline: nothing to account


def test_evaluation_counts_llm_outputs_and_shares_one_budget():
    rec = Recorder()
    cfg = make_config(CFG, max_llm_calls=30)
    budget = BudgetedLLM(rec, 30)
    res = evaluate(["AAPL", "NVDA"], {"q": ("2024-01-02", "2024-02-29")}, cfg, rebalance_every=10,
                   llm=budget, workers=2)
    assert budget.calls == 30 and len(rec.prompts) == 30          # one budget across both runs
    src = res.meta["agent_sources"]
    assert src["llm"] > 0 and src["rules"] > 0                    # trader answered; others fell back
    assert res.meta["budget_refused"] > 0 and res.meta["usage"] is None


def test_cli_accepts_llm_run_flags(capsys):
    assert main(["evaluate", "AAPL", "--periods", "q1_2024", "--every", "20", "--workers", "2",
                 "--anonymize", "--deep-effort", "medium", "--max-llm-calls", "5"]) == 0
    with pytest.raises(SystemExit):
        main(["evaluate", "--deep-effort", "extreme"])
    with pytest.raises(ValueError):
        evaluate(["AAPL"], {"q": ("2024-01-02", "2024-01-31")}, CFG, workers=0)
