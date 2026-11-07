"""Every ``ask_json`` call site passes a schema whose ``required`` keys equal the call's
``required`` tuple and whose properties cover every ``numeric`` key (schema and gate agree)."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from agentic_trader import contracts

AGENTS = Path(__file__).resolve().parents[1] / "agentic_trader" / "agents"


def _sites():
    for path in sorted(AGENTS.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "ask_json":
                yield f"{path.name}:{node.lineno}", node


SITES = list(_sites())


def test_there_are_five_sites():
    assert len(SITES) == 5


@pytest.mark.parametrize("where,node", SITES, ids=[w for w, _ in SITES])
def test_site_schema_matches_its_gate(where, node):
    kw = {k.arg: k.value for k in node.keywords}
    assert "schema" in kw, f"{where} sends no schema"
    schema = getattr(contracts, kw["schema"].attr)
    required = ast.literal_eval(node.args[1])
    numeric = ast.literal_eval(kw["numeric"]) if "numeric" in kw else ()
    assert set(schema["required"]) == set(required), where
    assert set(numeric) <= set(schema["properties"]), where
    for k in numeric:
        t = schema["properties"][k]["type"]
        assert t == "number" or (k not in required and t == ["number", "null"]), (where, k)
