from datetime import date

import pytest

from agentic_trader import Action, Instrument, TradingGraph, make_config, run_agent_backtest
from agentic_trader.llm import extract_json
from agentic_trader.memory import DecisionMemory
from agentic_trader.sentiment import score_fx_headline

CFG = make_config(memory_path=None)


def test_instrument_parsing():
    assert Instrument.parse("aapl").asset_class == "equity"
    fx = Instrument.parse("EUR/USD")
    assert (fx.asset_class, fx.base, fx.quote, fx.pip_size) == ("fx", "EUR", "USD", 1e-4)
    assert Instrument.parse("USDJPY=X").pip_size == 0.01
    assert Instrument.parse("EURUSD", "equity").asset_class == "equity"
    assert Instrument.parse(" brk.b ").symbol == "BRK.B"
    assert Instrument.parse("^GSPC").asset_class == "equity"


@pytest.mark.parametrize("bad", ["", "   ", "EUR/XYZ", "ABC=X", "AAPL MSFT", "AA$PL",
                                 "TOOLONGTICKER12"])
def test_instrument_parsing_rejects_bad_symbols(bad):
    with pytest.raises(ValueError):
        Instrument.parse(bad)


def test_instrument_parsing_rejects_unknown_asset_class():
    with pytest.raises(ValueError):
        Instrument.parse("AAPL", "crypto")
    with pytest.raises(ValueError):
        Instrument.parse("AAPL", "fx")


@pytest.mark.parametrize("symbol,expected", [
    ("AAPL", {"technical", "fundamentals", "news", "sentiment"}),
    ("EURUSD", {"technical", "macro", "news", "sentiment"}),
])
def test_propagate_offline(symbol, expected):
    g = TradingGraph(CFG, memory=DecisionMemory(None), on_event=lambda *_: None)
    state, dec = g.propagate(symbol, date(2024, 3, 1))
    assert set(state.reports) == expected
    assert state.history.index.max().date() <= date(2024, 3, 1)
    assert len(state.debate.turns) == 2 * CFG["max_debate_rounds"]
    assert len(state.risk_views) == 3 * CFG["max_risk_discuss_rounds"]
    assert -1.0 <= dec.target_weight <= 1.0
    assert isinstance(dec.action, Action)
    if symbol == "AAPL":  # long-only equities by default
        assert dec.target_weight >= 0
    assert "Portfolio manager decision" in state.to_markdown()


def test_deterministic_offline():
    g1 = TradingGraph(CFG, memory=DecisionMemory(None), on_event=lambda *_: None)
    g2 = TradingGraph(CFG, memory=DecisionMemory(None), on_event=lambda *_: None)
    assert g1.propagate("MSFT", "2024-02-15")[1] == g2.propagate("MSFT", "2024-02-15")[1]


def test_memory_resolves_only_past():
    m = DecisionMemory(None)
    m.record("X", date(2024, 1, 1), "BUY", 0.5, 100.0, "test", horizon_days=10)
    assert m.resolve("X", date(2024, 1, 5), 110.0) == 0  # horizon not elapsed
    assert m.resolve("X", date(2024, 1, 12), 110.0) == 1
    assert m.entries[0].pnl == pytest.approx(0.05)
    assert m.lessons("X", date(2024, 1, 11)) == []  # not known before resolution date
    assert len(m.lessons("X", date(2024, 1, 12))) == 1


def test_fx_headline_orientation():
    assert score_fx_headline("JPY weakens after dovish comments", "USD", "JPY") > 0
    assert score_fx_headline("USD strengthens on strong data", "USD", "JPY") > 0
    assert score_fx_headline("USD/JPY drops amid recession fears", "USD", "JPY") < 0


def test_extract_json():
    assert extract_json('blah ```json\n{"a": 1}\n``` tail') == {"a": 1}
    assert extract_json('Result: {"signal": 0.3}') == {"signal": 0.3}
    assert extract_json("no json") is None


class StubLLM:
    """Returns canned JSON per role so every agent's LLM branch is exercised."""

    def __init__(self, pm_weight=-0.8):
        self.pm_weight = pm_weight
        self.calls = []

    def complete(self, system, prompt, *, deep):
        self.calls.append((system.split("Your role: ")[-1][:20], deep))
        if "Researcher" in system:
            return "Evidence-based argument."
        if "Facilitator" in system:
            return '{"winner": "bull", "score": 0.6, "conviction": 0.7, "summary": "Bull wins."}'
        if "Trader." in system:
            return ('```json\n{"action": "BUY", "target_weight": 0.9, "confidence": 0.7, '
                    '"stop_loss": 1, "take_profit": null, "horizon_days": 5, "rationale": "r"}\n```')
        if "Risk Analyst" in system:
            return '{"recommended_weight": 5.0, "argument": "size up"}'  # out of range -> clipped
        if "Portfolio Manager" in system:
            return f'{{"target_weight": {self.pm_weight}, "confidence": 0.6, "rationale": "pm"}}'
        return '{"signal": 2.5, "confidence": 0.8, "summary": "LLM view", "key_points": ["a"]}'


def test_llm_branches_and_guardrails():
    llm = StubLLM(pm_weight=-0.8)  # PM tries to short an equity -> guardrail forces flat
    g = TradingGraph(CFG, llm=llm, memory=DecisionMemory(None), on_event=lambda *_: None)
    state, dec = g.propagate("AAPL", "2024-03-01")
    assert all(r.source == "llm" and r.signal == 1.0 for r in state.reports.values())
    assert state.debate.source == "llm" and state.debate.winner == "bull"
    assert state.proposal.source == "llm" and state.proposal.horizon_days == 5
    assert all(v.recommended_weight == CFG["risk"]["max_position"] for v in state.risk_views)
    assert dec.source == "llm" and dec.target_weight == 0.0 and not dec.approved
    assert any("short selling not allowed" in a for a in dec.adjustments)
    # analysts use the quick tier, everyone downstream the deep tier
    assert [deep for _, deep in llm.calls[:4]] == [False] * 4 and all(d for _, d in llm.calls[4:])


def test_llm_garbage_falls_back_to_rules():
    class Garbage:
        def complete(self, *a, **k):
            return "I cannot produce JSON today."
    g = TradingGraph(CFG, llm=Garbage(), memory=DecisionMemory(None), on_event=lambda *_: None)
    state, dec = g.propagate("EURUSD", "2024-03-01")
    assert all(r.source == "rules" for r in state.reports.values())
    assert dec.source == "rules"


@pytest.mark.parametrize("symbol", ["NVDA", "GBPUSD"])
def test_backtest_runs(symbol):
    rep = run_agent_backtest(symbol, "2024-01-01", "2024-03-29", CFG, rebalance_every=10)
    t = rep.table()
    assert {"AgenticTrader", "Buy&Hold", "MACD", "KDJ+RSI", "ZMR", "SMA(20/50)"} <= set(t.index)
    assert rep.decisions and all(d.as_of <= date(2024, 3, 29) for d in rep.decisions)
