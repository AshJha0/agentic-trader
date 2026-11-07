"""JSON schemas for every structured model reply (structured outputs, ``output_config.format``).

Each schema mirrors the contract the agent checks after the reply (``Agent.ask_json``'s
``required`` and ``numeric``): the schema removes the parse failure mode at the API, the
contract check stays as the second gate, and both must agree. ``tests/test_v13_contract_sites.py``
pins that agreement for every call site.

Rules the API imposes on these schemas: ``type: object`` at the top, ``additionalProperties:
false``, and every key the agent reads listed under ``properties``. Optional keys stay out of
``required``; a nullable number is ``["number", "null"]``.
"""
from __future__ import annotations

from typing import Any

NUM = {"type": "number"}
NUM_OR_NULL = {"type": ["number", "null"]}
TEXT = {"type": "string"}


def obj(properties: dict[str, Any], required: tuple[str, ...]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": list(required),
            "additionalProperties": False}


ANALYST = obj({"signal": NUM, "confidence": NUM, "summary": TEXT,
               "key_points": {"type": "array", "items": TEXT}},
              ("signal", "confidence", "summary"))

FACILITATOR = obj({"winner": {"type": "string", "enum": ["bull", "bear", "balanced"]},
                   "score": NUM, "conviction": NUM_OR_NULL, "summary": TEXT},
                  ("winner", "score", "summary"))

RISK_VIEW = obj({"recommended_weight": NUM, "argument": TEXT},
                ("recommended_weight", "argument"))

PORTFOLIO_MANAGER = obj({"target_weight": NUM, "confidence": NUM_OR_NULL, "rationale": TEXT},
                        ("target_weight", "rationale"))

TRADER = obj({"action": {"type": "string", "enum": ["BUY", "SELL", "HOLD"]},
              "target_weight": NUM, "confidence": NUM_OR_NULL, "stop_loss": NUM_OR_NULL,
              "take_profit": NUM_OR_NULL, "horizon_days": NUM_OR_NULL, "rationale": TEXT},
             ("action", "target_weight", "rationale"))

ALL: dict[str, dict[str, Any]] = {
    "analyst": ANALYST, "facilitator": FACILITATOR, "risk_view": RISK_VIEW,
    "portfolio_manager": PORTFOLIO_MANAGER, "trader": TRADER,
}
