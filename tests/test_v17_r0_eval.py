"""v0.17 R0.2 (review B1): the frozen eval items are anonymised exactly as the P2 study's prompts
are, so eval scores describe the prompt distribution the trading cells see. No model is called."""
from __future__ import annotations

import json
import re

import pytest

from agentic_trader.agentic import eval_set as ev
from agentic_trader.evaluation import CORE_UNIVERSE

ITEMS = ev.load_items()
EVAL_NAMES = ["AAPL", "MSFT", "NVDA", "JPM", "XOM", "KO", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "PAPERNAV"]
CODES = ["EUR", "USD", "GBP", "JPY", "AUD", "CHF", "CAD"]
COMPANIES = ["Apple", "Microsoft", "Nvidia", "JPMorgan", "Exxon", "Coca-Cola", "Amazon", "Alphabet", "Google",
             "Tesla", "Meta"]
TICKERS = sorted({*EVAL_NAMES, *(n for names in CORE_UNIVERSE.values() for n in names), *CODES})


def _model_facing(it: dict) -> str:
    """Everything a model can see for an item (instrument/as_of are provenance only)."""
    return json.dumps({k: it[k] for k in ("system", "prompt", "facts", "last_close")})


@pytest.mark.parametrize("word", TICKERS + COMPANIES)
def test_no_universe_ticker_or_company_name_reaches_a_prompt(word: str) -> None:
    pat = re.compile(rf"(?<![A-Za-z]){re.escape(word)}(?![A-Za-z])", re.I if word in COMPANIES else 0)
    leaks = [it["id"] for it in ITEMS if pat.search(_model_facing(it))]
    assert not leaks, (word, leaks[:5])


def test_items_are_on_the_study_scale() -> None:
    for it in ITEMS:
        assert it["anonymized"] and it["last_close"] == pytest.approx(100.0)
        assert not re.search(r"\d{4}-\d{2}-\d{2}", _model_facing(it)), it["id"]
        assert re.match(r"Instrument: (STOCK_X|CCY_BASE/CCY_QUOTE) ", it["prompt"]), it["id"]


def test_named_arm_still_available_as_leak_probe() -> None:
    named = ev.build_items(anonymize=False)
    assert any("AAPL" in it["prompt"] for it in named) and not named[0]["anonymized"]
    assert [it["id"] for it in named] == [it["id"] for it in ITEMS]
