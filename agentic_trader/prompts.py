"""Prompt registry: a content hash over the prompts the trading desk's agents send.

An LLM evaluation is only reproducible if the prompts are pinned. Each agent's
*system* prompt is a string; its *user* prompt is built by a method. The registry
hashes both -- the system text and the source code that formats the facts -- so
``EvaluationResult.meta["prompts"]`` records which wording produced a result, and
two runs can be told apart (or shown identical) without reading transcripts.

What the bundle covers, exactly:

* per agent (every analyst in ``ANALYSTS``, bull, bear, facilitator, trader, the three
  risk stances, pm): the system prompt text and the source of the agent's class and of
  every base class below ``Agent``;
* ``firm_context``: the ``FIRM_CONTEXT`` preamble;
* ``shared``: the source of each callable enumerated in ``shared_prompt_code()`` (the
  fact formatter, the untrusted-text fence and the ``fenced`` helper, the state's prompt
  facts, report digest, lessons block, ``untrusted_inputs`` flag and the debate / verdict /
  proposal / risk-views blocks, the direction note, the consensus score, the policy
  passages, the risk facts, the anonymiser and its key test, the memory's settle and
  track-record methods, the risk percentage formatter) and the value of each constant enumerated in
  ``shared_prompt_constants()`` (the fence tag ``state._TAG`` and the anonymiser's
  price-key and scale-free-key allow-lists, suffixes, prefixes and date pattern).

Nothing else is covered. A module-level constant or helper outside those two lists,
the data providers' fact dictionaries, the knowledge documents the tools return, and
the agentic harness's own prompts (``agentic/critic.py``, ``agentic/planner.py``,
``agentic/reporter.py``, sent outside any ``Agent``) can change prompt text while the
bundle stays the same; extend the lists when such a source is added to the desk.

The hashes are SHA-256 over UTF-8 text, truncated to 16 hex characters; the
``bundle`` hash covers every entry in name order, so a single number identifies
the whole prompt set.
"""
from __future__ import annotations

import hashlib
import inspect
from typing import Any, Callable

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


def shared_prompt_code() -> dict[str, Callable[..., Any] | type]:
    """The functions and classes outside the agent classes whose source shapes prompt text.

    Looked up at call time (not bound at import), so a replaced function is seen.
    """
    from . import anonymize, memory, state
    from .agents import analysts, base, researchers, risk, trader
    return {
        "Agent.system_prompt": base.Agent.system_prompt.fget,
        "Agent._complete": base.Agent._complete,
        "Agent.ask_json": base.Agent.ask_json,
        "Agent._contract_problem": base.Agent._contract_problem,
        "fmt_facts": base.fmt_facts,
        "untrusted_block": state.untrusted_block,
        "fenced": state.fenced,
        "TradingState.px": state.TradingState.px,
        "TradingState.fmt_px": state.TradingState.fmt_px,
        "TradingState.prompt_facts": state.TradingState.prompt_facts,
        "TradingState.reports_digest": state.TradingState.reports_digest,
        "TradingState.lessons_block": state.TradingState.lessons_block,
        "TradingState.untrusted_inputs": state.TradingState.untrusted_inputs.fget,
        "TradingState.debate_block": state.TradingState.debate_block,
        "TradingState.verdict_block": state.TradingState.verdict_block,
        "TradingState.proposal_block": state.TradingState.proposal_block,
        "TradingState.risk_views_block": state.TradingState.risk_views_block,
        "_direction_note": analysts._direction_note,
        "consensus_score": researchers.consensus_score,
        "policy_passages": trader.policy_passages,
        "risk_facts": risk.risk_facts,
        "_pct": risk._pct,
        "Anonymizer": anonymize.Anonymizer,
        "is_scale_free_key": anonymize.is_scale_free_key,
        "DecisionMemory._settle": memory.DecisionMemory._settle,
        "DecisionMemory.track_record": memory.DecisionMemory.track_record,
    }


def shared_prompt_constants() -> dict[str, str]:
    """Module-level constants whose *value* shapes prompt text (``inspect.getsource`` cannot
    see them through the functions that read them), rendered as stable text. Looked up at
    call time, like ``shared_prompt_code``."""
    from . import anonymize, state
    return {
        "state._TAG": str(state._TAG),
        "anonymize.PRICE_KEYS": repr(sorted(anonymize.PRICE_KEYS)),
        "anonymize.SCALE_FREE_KEYS": repr(sorted(anonymize.SCALE_FREE_KEYS)),
        "anonymize._SCALE_FREE_SUFFIXES": repr(list(anonymize._SCALE_FREE_SUFFIXES)),
        "anonymize._SCALE_FREE_PREFIXES": repr(list(anonymize._SCALE_FREE_PREFIXES)),
        "anonymize._ISO_DATE": anonymize._ISO_DATE.pattern,
    }


def _shared_entry() -> dict[str, str]:
    parts = []
    for name, obj in shared_prompt_code().items():
        src = _source(obj)
        if src == SOURCE_UNAVAILABLE:
            return {"template": SOURCE_UNAVAILABLE}
        parts.append(f"{name}:{src}")
    parts += [f"{name}={value}" for name, value in shared_prompt_constants().items()]
    return {"template": _h("\n".join(parts))}


def prompt_registry(config: dict) -> dict[str, Any]:
    """Hashes for every agent's system prompt and prompt-building code under ``config``.

    The result has one entry per agent (``analyst:technical`` ... ``pm``), the
    ``firm_context`` shared preamble, a ``shared`` entry over the prompt helpers every
    agent uses, and a ``bundle`` hash over all of them.
    """
    agents: dict[str, Agent] = {f"analyst:{name}": cls(None, config) for name, cls in ANALYSTS.items()}
    agents.update({"bull": BullResearcher(None, config), "bear": BearResearcher(None, config),
                   "facilitator": DebateFacilitator(None, config), "trader": Trader(None, config),
                   "pm": PortfolioManager(None, config)})
    for stance in ("aggressive", "neutral", "conservative"):
        agents[f"risk:{stance}"] = RiskAnalyst(None, config, stance)
    entries = {name: _agent_entry(a) for name, a in sorted(agents.items())}
    entries["firm_context"] = {"system": _h(FIRM_CONTEXT)}
    shared = _shared_entry()
    bundle = _h("\n".join(f"{k}={v}" for k, v in sorted(entries.items())) + f"\nshared={shared}")
    return {"bundle": bundle, "agents": entries, "shared": shared}


def prompt_bundle_hash(config: dict) -> str:
    return prompt_registry(config)["bundle"]


__all__ = ["prompt_registry", "prompt_bundle_hash", "shared_prompt_code", "shared_prompt_constants"]
