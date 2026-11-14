"""JSON schemas for every structured model reply (structured outputs, ``output_config.format``).

Each schema mirrors the contract the agent checks after the reply (``Agent.ask_json``'s
``required`` and ``numeric``): the schema removes the parse failure mode at the API, the
contract check stays as the second gate, and both must agree. ``tests/test_v13_contract_sites.py``
pins that agreement for every call site.

Rules the API imposes on these schemas: ``type: object`` at the top, ``additionalProperties:
false``, and every key the agent reads listed under ``properties``. Optional keys stay out of
``required``; a nullable number is ``["number", "null"]``.

Ranges (v0.17 R0.4, review A3): every bounded number carries ``minimum``/``maximum``. Ollama's
grammar decoding honours them; the contract check (``violation``) enforces them for every
backend, so an out-of-range value is a contract rejection (rules apply, counted as a contract
failure), never clipped to the nearest bound. The Anthropic structured-outputs endpoint does
not accept numeric bounds, so ``api_schema`` strips them (into ``description``) for that path.
"""

from __future__ import annotations

import math
from typing import Any

NUM = {"type": "number"}
NUM_OR_NULL = {"type": ["number", "null"]}
TEXT = {"type": "string"}


def num(lo: float, hi: float, nullable: bool = False) -> dict[str, Any]:
    """A number in [lo, hi] (optionally ``null``)."""
    return {"type": ["number", "null"] if nullable else "number", "minimum": lo, "maximum": hi}


SIGNED = num(-1, 1)  # signals, scores, weights as signed fractions of capital
UNIT = num(0, 1)  # confidence, conviction
UNIT_OR_NULL = num(0, 1, nullable=True)
PRICE_OR_NULL = {"type": ["number", "null"], "exclusiveMinimum": 0}


def obj(properties: dict[str, Any], required: tuple[str, ...]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


ANALYST = obj(
    {"signal": SIGNED, "confidence": UNIT, "summary": TEXT, "key_points": {"type": "array", "items": TEXT}},
    ("signal", "confidence", "summary"),
)

FACILITATOR = obj(
    {
        "winner": {"type": "string", "enum": ["bull", "bear", "balanced"]},
        "score": SIGNED,
        "conviction": UNIT_OR_NULL,
        "summary": TEXT,
    },
    ("winner", "score", "summary"),
)

RISK_VIEW = obj({"recommended_weight": SIGNED, "argument": TEXT}, ("recommended_weight", "argument"))

PORTFOLIO_MANAGER = obj({"target_weight": SIGNED, "confidence": UNIT_OR_NULL, "rationale": TEXT}, ("target_weight", "rationale"))

TRADER = obj(
    {
        "action": {"type": "string", "enum": ["BUY", "SELL", "HOLD"]},
        "target_weight": SIGNED,
        "confidence": UNIT_OR_NULL,
        "stop_loss": PRICE_OR_NULL,
        "take_profit": PRICE_OR_NULL,
        "horizon_days": num(1, 90, nullable=True),
        "rationale": TEXT,
    },
    ("action", "target_weight", "rationale"),
)

ALL: dict[str, dict[str, Any]] = {
    "analyst": ANALYST,
    "facilitator": FACILITATOR,
    "risk_view": RISK_VIEW,
    "portfolio_manager": PORTFOLIO_MANAGER,
    "trader": TRADER,
}


_BOUNDS = ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum")


def violation(data: dict[str, Any], schema: dict[str, Any] | None) -> str | None:
    """The first range or enum breach of ``data`` against ``schema``'s properties, or ``None``.

    Only present, numeric (or string, for ``enum``) values are checked; presence and type stay
    with the caller's ``required``/``numeric`` gate. Enum matching ignores case, as the agents
    already upper/lower-case these strings before use."""
    for key, spec in ((schema or {}).get("properties") or {}).items():
        if key not in data or data[key] is None:
            continue
        v = data[key]
        if "enum" in spec:
            if not isinstance(v, str) or v.lower() not in {str(e).lower() for e in spec["enum"]}:
                return f"{key}={v!r} not in {spec['enum']}"
            continue
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
            continue
        if (
            ("minimum" in spec and v < spec["minimum"])
            or ("maximum" in spec and v > spec["maximum"])
            or ("exclusiveMinimum" in spec and v <= spec["exclusiveMinimum"])
            or ("exclusiveMaximum" in spec and v >= spec["exclusiveMaximum"])
        ):
            rng = ", ".join(f"{b}={spec[b]}" for b in _BOUNDS if b in spec)
            return f"{key}={v!r} out of range ({rng})"
    return None


def api_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """``schema`` without numeric bounds (moved into ``description``), for the Anthropic
    structured-outputs endpoint, which rejects them. ``violation`` still enforces the bounds."""
    props = {}
    for key, spec in schema.get("properties", {}).items():
        bounds = {b: spec[b] for b in _BOUNDS if b in spec}
        if bounds:
            spec = {k: v for k, v in spec.items() if k not in _BOUNDS}
            spec["description"] = ", ".join(f"{b} {v}" for b, v in bounds.items())
        props[key] = spec
    return {**schema, "properties": props}
