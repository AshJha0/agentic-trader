"""Common agent plumbing.

Each agent follows the same pattern:
  1. *Tools*: deterministic data gathering / quant computation (C++ core).
  2. *Rules*: a transparent rule-based judgement over those facts. Always
     computed; it is the result in offline mode and the fallback otherwise.
  3. *LLM*: when enabled, the model reasons over the same facts and returns a
     structured JSON document that replaces the rule-based judgement.
"""
from __future__ import annotations

import json
import logging
import math
from typing import Any

from ..llm import LLM, extract_json

log = logging.getLogger(__name__)

FIRM_CONTEXT = (
    "You are part of a multi-agent trading firm that mirrors a real trading desk: an analyst "
    "team, bull and bear researchers, a trader, a risk-management team and a portfolio "
    "manager. Agents share information through concise structured reports. Base every "
    "claim on the data you are given; do not invent numbers, news or events."
)


def clip(x: Any, lo: float, hi: float, default: float = 0.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    if math.isnan(v):
        return default
    return max(lo, min(hi, v))


def fmt_facts(facts: dict[str, Any]) -> str:
    def conv(v):
        if isinstance(v, float):
            return round(v, 6)
        return v
    return json.dumps({k: conv(v) for k, v in facts.items()}, indent=1, default=str)


class Agent:
    name = "agent"
    role = "agent"
    deep = False  # which model tier to use

    def __init__(self, llm: LLM | None, config: dict):
        self.llm = llm
        self.config = config

    @property
    def system_prompt(self) -> str:
        return f"{FIRM_CONTEXT}\n\nYour role: {self.role}"

    def ask_text(self, prompt: str) -> str | None:
        if self.llm is None:
            return None
        return self.llm.complete(self.system_prompt, prompt, deep=self.deep)

    def ask_json(self, prompt: str, required: tuple[str, ...]) -> dict[str, Any] | None:
        if self.llm is None:
            return None
        text = self.llm.complete(
            self.system_prompt,
            prompt + "\n\nRespond with a single JSON object only (no prose outside it).",
            deep=self.deep,
        )
        data = extract_json(text)
        if data is None or any(k not in data for k in required):
            if text is not None:
                log.warning("%s: LLM reply missing %s; using rule-based output", self.name, required)
            return None
        return data
