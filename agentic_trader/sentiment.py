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
    "hike", "hikes", "hiked", "tightens", "strengthen", "appreciates", "climbs", "jumps",
    "soars", "firms", "firmer",
}
NEGATIVE = {
    "miss", "misses", "downgrade", "downgraded", "weak", "weaker", "weakens", "decline",
    "declines", "cut", "cuts", "falls", "fall", "slides", "drops", "drop", "probe",
    "slowdown", "concerns", "fears", "recession", "bearish", "puts", "dump", "sell",
    "breakdown", "loss", "ugly", "disappoints", "dovish", "pressuring", "lawsuit",
    "underperform", "plunge", "plunges", "risk-off", "worse",
    "weaken", "weakness", "depreciates", "slumps", "tumbles", "sinks", "slips", "eases", "easing",
    "softer", "softens",
}
NEGATORS = {"not", "no", "never", "without", "hardly"}
_WORD = re.compile(r"[a-z][a-z\-']*")


def _tone_total(text: str) -> float:
    words = _WORD.findall(text.lower())
    total = 0.0
    for i, w in enumerate(words):
        s = 1.0 if w in POSITIVE else -1.0 if w in NEGATIVE else 0.0
        if s and i > 0 and words[i - 1] in NEGATORS:
            s = -s
        total += s
    return total


def score_text(text: str) -> float:
    """Return a sentiment score in [-1, 1]."""
    return math.tanh(_tone_total(text) / 2.0)


# Currency names, nicknames and central banks -> ISO code. Multi-word phrases are matched
# before single words, and every match is on word boundaries ("CADENCE" is not CAD).
_ALIASES: list[tuple[str, str]] = [
    (r"u\.?s\.? dollars?", "USD"), (r"us dollars?", "USD"), (r"australian dollars?", "AUD"),
    (r"aussie dollars?", "AUD"), (r"canadian dollars?", "CAD"), (r"new zealand dollars?", "NZD"),
    (r"kiwi dollars?", "NZD"), (r"hong kong dollars?", "HKD"), (r"singapore dollars?", "SGD"),
    (r"swiss francs?", "CHF"), (r"swiss national bank", "CHF"), (r"federal reserve", "USD"),
    (r"bank of japan", "JPY"), (r"japanese yen", "JPY"), (r"european central bank", "EUR"),
    (r"bank of england", "GBP"), (r"british pound", "GBP"), (r"pound sterling", "GBP"),
    (r"reserve bank of australia", "AUD"), (r"bank of canada", "CAD"),
    (r"reserve bank of new zealand", "NZD"), (r"norges bank", "NOK"), (r"swedish krona", "SEK"),
    (r"norwegian krone", "NOK"), (r"danish krone", "DKK"), (r"south african rand", "ZAR"),
    (r"mexican peso", "MXN"), (r"chinese yuan", "CNY"), (r"peoples? bank of china", "CNY"),
    (r"dollars?", "USD"), (r"greenback", "USD"), (r"fed", "USD"), (r"fomc", "USD"),
    (r"yen", "JPY"), (r"boj", "JPY"), (r"euros?", "EUR"), (r"ecb", "EUR"),
    (r"pounds?", "GBP"), (r"sterling", "GBP"), (r"boe", "GBP"),
    (r"francs?", "CHF"), (r"swissie", "CHF"), (r"snb", "CHF"),
    (r"aussie", "AUD"), (r"rba", "AUD"), (r"loonie", "CAD"), (r"boc", "CAD"),
    (r"kiwi", "NZD"), (r"rbnz", "NZD"), (r"krona", "SEK"), (r"riksbank", "SEK"),
    (r"krone", "NOK"), (r"norges", "NOK"), (r"rand", "ZAR"), (r"sarb", "ZAR"),
    (r"yuan", "CNY"), (r"renminbi", "CNY"), (r"pboc", "CNY"), (r"rupee", "INR"), (r"rbi", "INR"),
    (r"lira", "TRY"), (r"zloty", "PLN"), (r"peso", "MXN"),
    # "buck", "cable", "won" and "real" are everyday words far more often than currencies: left out.
]
_ALIAS_RE = [(re.compile(rf"\b{pat}\b", re.IGNORECASE), code) for pat, code in _ALIASES]
_EQUIVALENT = {"CNH": "CNY"}   # offshore and onshore yuan are one currency for a headline
_CLAUSE_SPLIT = re.compile(r"[;:,.!?()]|\s[-–—]+\s|\s(?:as|after|while|but|whereas|though|although)\s",
                           re.IGNORECASE)


def _normalise(text: str, base: str, quote: str) -> str:
    """Upper-case text with the pair itself removed and every currency alias replaced by its code."""
    t = text
    for pat, code in _ALIAS_RE:
        t = pat.sub(f" {code} ", t)
    t = t.upper()
    for pair in (f"{base}/{quote}", f"{base}-{quote}", f"{base}{quote}", f"{base} {quote}"):
        t = t.replace(pair, " ")
    return t


def _mentions(t: str, code: str) -> bool:
    codes = {code} | {k for k, v in _EQUIVALENT.items() if v == code} | ({_EQUIVALENT[code]} if code in _EQUIVALENT else set())
    return any(re.search(rf"\b{c}\b", t) for c in codes)


def score_fx_headline(text: str, base: str, quote: str) -> float:
    """Score a headline from the point of view of the base currency of base/quote.

    Headline tone is about its subject: "Yen weakens" is bad for JPY but good for
    USD/JPY. Currencies are recognised by ISO code, name, nickname or central bank
    ("dollar", "greenback", "Fed" -> USD; "yen", "BoJ" -> JPY; "sterling", "BoE" -> GBP;
    "aussie", "RBA" -> AUD; "loonie", "BoC" -> CAD; "kiwi", "RBNZ" -> NZD; "franc",
    "SNB" -> CHF; "krona", "Riksbank" -> SEK; "krone", "Norges" -> NOK ...), on word
    boundaries. The headline is scored clause by clause (split at punctuation and at
    "as", "after", "while", "but"): a clause about the quote currency alone is flipped,
    one about the base currency or the pair itself is not, and a clause naming neither
    takes the orientation of the headline as a whole. "Dollar weakens; yen strengthens
    on hawkish BoJ" is thus negative for USD/JPY on both counts.
    """
    base, quote = base.upper(), quote.upper()
    whole = _normalise(text, base, quote)
    whole_flip = _mentions(whole, quote) and not _mentions(whole, base)
    total = 0.0
    for clause in _CLAUSE_SPLIT.split(text):
        if not clause or not clause.strip():
            continue
        tone = _tone_total(clause)
        if not tone:
            continue
        t = _normalise(clause, base, quote)
        has_base, has_quote = _mentions(t, base), _mentions(t, quote)
        flip = whole_flip if not (has_base or has_quote) else (has_quote and not has_base)
        total += -tone if flip else tone
    return math.tanh(total / 2.0)
