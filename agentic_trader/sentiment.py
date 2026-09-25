"""Tiny finance sentiment lexicon used by the rule-based News/Sentiment analysts.

Deliberately simple (bag of words with negation handling). With an LLM enabled
the analysts reason over the raw headlines instead.
"""
from __future__ import annotations

import math
import re

POSITIVE = {
    "beat", "beats", "upgrade", "upgrades", "upgraded", "strong", "stronger", "strengthens",
    "record", "raise", "raises", "rally", "rallies", "surge", "surges", "gain", "gains",
    "growth", "accelerates", "robust", "praise", "bullish", "breakout", "buy", "calls",
    "moon", "momentum", "accumulating", "improves", "tightening", "hawkish", "lifting",
    "outperform", "boost", "boosts", "optimism", "recovery", "beat-estimates", "strength",
}
NEGATIVE = {
    "miss", "misses", "downgrade", "downgraded", "weak", "weaker", "weakens", "decline",
    "declines", "cut", "cuts", "falls", "fall", "slides", "drops", "drop", "probe",
    "slowdown", "concerns", "fears", "recession", "bearish", "puts", "dump", "sell",
    "breakdown", "loss", "ugly", "disappoints", "dovish", "pressuring", "lawsuit",
    "underperform", "plunge", "plunges", "risk-off", "worse", "rising costs",
}
NEGATORS = {"not", "no", "never", "without", "hardly"}
_WORD = re.compile(r"[a-z][a-z\-']*")


def score_text(text: str) -> float:
    """Return a sentiment score in [-1, 1]."""
    words = _WORD.findall(text.lower())
    total = 0.0
    for i, w in enumerate(words):
        s = 1.0 if w in POSITIVE else -1.0 if w in NEGATIVE else 0.0
        if s and i > 0 and words[i - 1] in NEGATORS:
            s = -s
        total += s
    return math.tanh(total / 2.0)


def score_fx_headline(text: str, base: str, quote: str) -> float:
    """Score a headline from the point of view of the base currency of base/quote.

    Headline tone is about its subject: "JPY weakens" is bad for JPY but good for
    USD/JPY. If only the quote currency is mentioned (after removing the pair
    itself), the lexicon score is flipped.
    """
    s = score_text(text)
    t = text.upper()
    for pair in (f"{base}/{quote}", f"{base}{quote}"):
        t = t.replace(pair, " ")
    has_base, has_quote = base in t, quote in t
    return -s if has_quote and not has_base else s
