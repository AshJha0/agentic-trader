"""v0.17 R0.4 (review A3): schema ranges are enforced by the contract check; an out-of-range
model number is a rejection (rules apply, counted as a contract failure), not a clip."""
from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd
import pytest

from agentic_trader import Instrument, contracts, make_config
from agentic_trader.agents.analysts import TechnicalAnalyst
from agentic_trader.llm import AnthropicLLM
from agentic_trader.state import TradingState

CFG = make_config(memory_path=None)


def _state() -> TradingState:
    idx = pd.bdate_range(end="2024-03-01", periods=300)
    c = 100 * np.exp(np.linspace(0, 0.3, 300))
    h = pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c, "Volume": np.full(300, 1e6)},
                     index=idx)
    return TradingState(Instrument.parse("AAPL"), idx[-1].date(), h)


class Fixed:
    def __init__(self, reply: dict[str, Any]):
        self.reply = json.dumps(reply)

    def complete(self, system: str, prompt: str, *, deep: bool) -> str:
        return self.reply

    def complete_json(self, system: str, prompt: str, *, deep: bool, schema: dict[str, Any]) -> str:
        return self.reply


def test_signal_999_is_rejected_not_clipped() -> None:
    """Regression: the old code clipped 999 to +1.0 and booked it as the model's view."""
    rules = TechnicalAnalyst(None, CFG).run(_state(), None)
    rep = TechnicalAnalyst(Fixed({"signal": 999, "confidence": 0.9, "summary": "x"}), CFG).run(_state(), None)
    assert rep.source == "rules" and rep.signal == pytest.approx(rules.signal) and rep.signal != 1.0
    ok = TechnicalAnalyst(Fixed({"signal": 0.4, "confidence": 0.9, "summary": "x"}), CFG).run(_state(), None)
    assert ok.source == "llm" and ok.signal == pytest.approx(0.4)
    bad_conf = TechnicalAnalyst(Fixed({"signal": 0.4, "confidence": 1.5, "summary": "x"}), CFG).run(_state(), None)
    assert bad_conf.source == "rules"


@pytest.mark.parametrize("name", sorted(contracts.ALL))
def test_every_number_in_every_schema_is_bounded(name: str) -> None:
    for key, spec in contracts.ALL[name]["properties"].items():
        t = spec.get("type")
        if t == "number" or (isinstance(t, list) and "number" in t):
            assert {"minimum", "maximum"} <= set(spec) or "exclusiveMinimum" in spec, (name, key)


@pytest.mark.parametrize("schema,data,bad", [
    (contracts.ANALYST, {"signal": 1.0, "confidence": 0.0}, False),
    (contracts.ANALYST, {"signal": -1.0001}, True),
    (contracts.FACILITATOR, {"winner": "Bull", "score": 0.1, "conviction": None}, False),
    (contracts.FACILITATOR, {"winner": "maybe", "score": 0.1}, True),
    (contracts.TRADER, {"action": "BUY", "target_weight": 0.5, "horizon_days": 200}, True),
    (contracts.TRADER, {"action": "BUY", "target_weight": 0.5, "stop_loss": 0}, True),
    (contracts.TRADER, {"action": "SELL", "target_weight": -0.5, "stop_loss": None}, False),
    (contracts.PORTFOLIO_MANAGER, {"target_weight": 50}, True),
    (contracts.RISK_VIEW, {"recommended_weight": -3}, True),
])
def test_violation(schema: dict, data: dict, bad: bool) -> None:
    assert (contracts.violation(data, schema) is not None) is bad


def test_anthropic_request_carries_no_numeric_bounds() -> None:
    llm = AnthropicLLM.__new__(AnthropicLLM)
    llm._request = lambda deep: {}            # type: ignore[attr-defined]
    llm._system_blocks = lambda s: s          # type: ignore[attr-defined]
    sent = llm.build_request("s", "p", deep=False, schema=contracts.ANALYST)["output_config"]["format"]["schema"]
    for spec in sent["properties"].values():
        assert not {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"} & set(spec)
    assert sent["properties"]["signal"]["type"] == "number" and "minimum" in contracts.ANALYST["properties"]["signal"]


def test_study_counts_out_of_range_as_contract_rejection() -> None:
    import importlib.util
    import sys
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "scripts" / "llm_study.py"
    spec = importlib.util.spec_from_file_location("llm_study_r0c", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["llm_study_r0c"] = mod
    spec.loader.exec_module(mod)
    s = mod.StudyLLM(Fixed({"signal": 999, "confidence": 0.5, "summary": "x"}))
    s.complete_json("s", "p", deep=False, schema=contracts.ANALYST)
    assert s.take()[0]["status"] == "unparseable"
