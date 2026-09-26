"""Prompt registry: a content hash for every prompt the desk can send.

An LLM evaluation is only reproducible if the prompts are pinned. Each agent's
*system* prompt is a string; its *user* prompt is built by a method. The registry
hashes both -- the system text and the source code of the method that formats the
facts -- so ``EvaluationResult.meta["prompts"]`` records exactly which wording
produced a result, and two runs can be told apart (or shown identical) without
reading transcripts.

The hashes are SHA-256 over UTF-8 text, truncated to 16 hex characters; the
``bundle`` hash covers every entry in name order, so a single number identifies
the whole prompt set.
"""
from __future__ import annotations

import hashlib
import inspect
from typing import Any

from .agents.analysts import ANALYSTS
from .agents.base import FIRM_CONTEXT, Agent
from .agents.researchers import BearResearcher, BullResearcher, DebateFacilitator
from .agents.risk import PortfolioManager, RiskAnalyst
from .agents.trader import Trader


def _h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


SOURCE_UNAVAILABLE = "source-unavailable"


def _source(obj: Any) -> str:
    """The object's source text, or a fixed marker when no source file ships (a zipapp or
    byte-code-only install): the marker makes ``template`` obviously not a content hash
    rather than a hash of ``repr(cls)`` that would differ between install types."""
    try:
        return inspect.getsource(obj)
    except (OSError, TypeError):
        return SOURCE_UNAVAILABLE


def _agent_entry(agent: Agent) -> dict[str, str]:
    """``system``: the system prompt text. ``template``: the source of the agent's class
    and of every base class up to ``Agent`` (the user prompts are assembled inside their
    methods, so the class source is the template). Any edit to the wording, the facts
    included or the JSON contract changes the hash; so does an unrelated edit to the same
    class, which is the conservative reading -- a changed agent is a changed prompt set."""
    cls = type(agent)
    chain = [c for c in cls.__mro__ if issubclass(c, Agent) and c is not Agent]
    sources = [_source(c) for c in chain]
    if any(src == SOURCE_UNAVAILABLE for src in sources):
        return {"system": _h(agent.system_prompt), "template": SOURCE_UNAVAILABLE}
    return {"system": _h(agent.system_prompt),
            "template": _h("\n".join(f"{c.__name__}:{src}" for c, src in zip(chain, sources)))}


def prompt_registry(config: dict) -> dict[str, Any]:
    """Hashes for every agent's system prompt and prompt-building code under ``config``.

    The result has one entry per agent (``analyst:technical`` ... ``pm``), the
    ``firm_context`` shared preamble, and a ``bundle`` hash over all of them.
    """
    agents: dict[str, Agent] = {f"analyst:{name}": cls(None, config) for name, cls in ANALYSTS.items()}
    agents.update({"bull": BullResearcher(None, config), "bear": BearResearcher(None, config),
                   "facilitator": DebateFacilitator(None, config), "trader": Trader(None, config),
                   "pm": PortfolioManager(None, config)})
    for stance in ("aggressive", "neutral", "conservative"):
        agents[f"risk:{stance}"] = RiskAnalyst(None, config, stance)
    entries = {name: _agent_entry(a) for name, a in sorted(agents.items())}
    entries["firm_context"] = {"system": _h(FIRM_CONTEXT)}
    bundle = _h("\n".join(f"{k}={v}" for k, v in sorted(entries.items())))
    return {"bundle": bundle, "agents": entries}


def prompt_bundle_hash(config: dict) -> str:
    return prompt_registry(config)["bundle"]


__all__ = ["prompt_registry", "prompt_bundle_hash"]
