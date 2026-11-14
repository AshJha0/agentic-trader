"""Prompt anonymisation against look-ahead through the model's memory.

A model trained on data that covers the backtest window may *recognise* the
situation ("NVDA, 2024-03-01") and recall what happened next instead of reasoning
from the data it is given. With ``config["llm_anonymize"]`` every prompt is
rewritten so the instrument, the calendar and the price level are hidden:

* names   the ticker / currency codes become neutral aliases (``STOCK_X``,
          ``CCY_BASE/CCY_QUOTE``);
* dates   every ISO date becomes an offset from the decision day (``D0``,
          ``D-12``, ``D+3``);
* prices  every price-level quantity (close, moving averages, ATR, MACD, stops)
          is rebased so that the last close is 100;
* facts   only known scale-free keys (returns, ratios, rates, volatilities,
          indicator values, counts) pass through; anything else is dropped. An
          absolute quantity such as TTM revenue identifies the company and the
          fiscal year, and per-share earnings times the P/E ratio is the real close,
          so the fact list is an allow-list, not a deny-list.

Prices the model returns (stop-loss, take-profit) are mapped back with ``unpx``;
names in its text are restored for the audit trail.

Third-party text (filings, central-bank statements) read by the text analysts goes through
``scrub_text``, which adds to ``scrub``:

* company  the instrument's company names (a built-in map for the research universe plus
           any names passed in, e.g. EDGAR ``entityName`` / ``formerNames``) and its best-known
           product names become ``COMPANY_X`` / ``PRODUCT_X``; other universe tickers and
           company names become ``OTHER_CO``;
* filings  SEC accession numbers (whose first 10 digits are the filer's CIK) become
           ``ACC_1``, ``ACC_2``... (``accession_real`` maps them back) and CIK numbers become
           ``CIK_X``;
* dates    ISO timestamps, US-style and written-out dates become ``D`` offsets; written
           months without a day become ``M`` offsets; bare years become ``Y`` offsets.

``scrub`` (the price path) also rewrites accession numbers, CIKs and ISO timestamps, which
never occur in a price-path prompt. Since v0.17 it also replaces company and product names
(own -> ``COMPANY_X`` / ``PRODUCT_X``, peers -> ``OTHER_CO``), so real headlines no longer name
the company; it does not alias peer tickers, which collide with ordinary upper-case text.

Residual leakage (documented in the threat model): distinctive statistics such
as a -0.1% policy rate, names outside the built-in map, the wording of a filing, and the
shape of the return series itself. One-letter tickers (``V``) are not aliased in text:
they collide with Roman numerals.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

from .instruments import Instrument

log = logging.getLogger(__name__)

# Fact keys that carry price levels (or price differences) and must be rebased.
PRICE_KEYS = frozenset(
    {
        "close",
        "last_close",
        "sma20",
        "sma50",
        "sma200",
        "macd_line",
        "macd_hist",
        "macd_hist_prev",
        "atr14",
        "entry_price",
        "stop_loss",
        "take_profit",
    }
)

# Scale-free fact keys that may reach an anonymised prompt unchanged. Strings among them
# (dates, currency codes, a source label) are still passed through ``scrub``.
SCALE_FREE_KEYS = frozenset(
    {
        # technical
        "rsi14",
        "bollinger_pct_b",
        "kdj_k",
        "kdj_d",
        "kdj_j",
        "realized_vol_20d_annual",
        "realized_vol_1y_annual",
        "zscore20",
        "return_5d",
        "return_20d",
        "return_60d",
        "return_12_1m",
        "bars",
        "atr_pct",
        # fundamentals: ratios, growth rates, margins, yields and filing dates
        "pe_ratio",
        "forward_pe",
        "sector_pe",
        "revenue_growth_yoy",
        "net_margin",
        "debt_to_equity",
        "fcf_yield",
        "eps_surprise",
        "insider_net_buying",
        "report_period_end",
        "revenue_period_end",
        "net_income_period_end",
        "eps_period_end",
        "ocf_period_end",
        "filed",
        "lag_days",
        "source",
        # FX macro
        "base",
        "quote",
        "base_rate",
        "quote_rate",
        "rate_diff",
        "base_inflation",
        "quote_inflation",
        "deviation_from_200d",
        # news and sentiment (headline text is fenced separately, never a fact)
        "lookback_days",
        "count",
        "recency_weighted_tone",
        "posts",
        "mean_post_sentiment",
        "recent_post_sentiment",
        "bullish_share",
        "volume_zscore",
        # alpha library: z-scores, ICs and counts (the peer list is replaced by its size)
        "latest",
        "ic",
        "combined_z",
        "breadth",
        "horizon",
        # trader and risk facts
        "short_selling_allowed",
        "max_position",
        "debate_winner",
        "debate_score",
        "debate_conviction",
        "current_position",
        "strategic_weight_when_neutral",
        "track_n",
        "track_hit_rate",
        "track_avg_pnl",
        "proposed_weight",
        "var_95_1d",
        "var_95_1d_short",
        "cvar_95_1d",
        "drawdown_from_60d_high",
        "target_vol",
        "max_var_95",
        "rebalance_band",
        "max_book_var_95",
        "book_var_95_now",
    }
)

# Numeric keys not listed above pass when their name says they are dimensionless.
_SCALE_FREE_SUFFIXES = (
    "_yoy",
    "_pct",
    "_ratio",
    "_yield",
    "_margin",
    "_z",
    "_zscore",
    "_share",
    "_rate",
    "_tone",
    "_sentiment",
    "_vol",
    "_ic",
    "_growth",
    "_surprise",
)
_SCALE_FREE_PREFIXES = ("return_", "track_", "ic_", "z_", "var_", "cvar_")

# An ISO date, with an optional time-of-day and zone suffix (``2020-02-20T21:30:00.000Z``).
_ISO_DATE = re.compile(
    r"(?<!\d)(\d{4})-(\d{2})-(\d{2})"
    r"(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?(?!\d)"
)
# SEC accession numbers: 0000320193-20-000096 (and the 18-digit form without dashes).
_ACCESSION = re.compile(r"(?<!\d)(\d{10})-(\d{2})-(\d{6})(?!\d)|(?<!\d)(\d{18})(?!\d)")
_CIK = re.compile(r"\bCIK\s*(?:No\.?|number|#)?\s*:?\s*\d{1,10}\b|(?<!\d)0\d{9}(?!\d)", re.I)
_MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")
    )
}
_MONTHS.update({m[:3]: i for m, i in list(_MONTHS.items())})
_MONTHS["sept"] = 9
_MON = (
    r"(January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)\.?"
)
_MDY = re.compile(rf"\b{_MON}\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.I)
_DMY = re.compile(rf"\b(\d{{1,2}})\s+{_MON},?\s+(\d{{4}})\b", re.I)
_MY = re.compile(rf"\b{_MON},?\s+(\d{{4}})\b", re.I)
_US_DATE = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})/(\d{4})(?![\d/])")
_YEAR = re.compile(r"(?<![\d.,$])(19[5-9]\d|20\d\d)(?![\d,]|\.\d)")

# Company and product names per ticker for the research universe (evaluation.py), so the
# text path can alias them without a network call. EDGAR names add to these at run time.
COMPANY_NAMES: dict[str, tuple[str, ...]] = {
    "AAPL": ("Apple Inc.", "Apple Computer", "Apple"),
    "NVDA": ("NVIDIA Corporation", "NVIDIA", "Nvidia"),
    "MSFT": ("Microsoft Corporation", "Microsoft"),
    "META": ("Meta Platforms", "Facebook, Inc.", "Facebook", "Meta"),
    "GOOGL": ("Alphabet Inc.", "Alphabet", "Google"),
    "AMZN": ("Amazon.com, Inc.", "Amazon.com", "Amazon"),
    "JPM": ("JPMorgan Chase & Co.", "JPMorgan Chase", "JPMorgan", "J.P. Morgan", "Chase"),
    "XOM": ("Exxon Mobil Corporation", "ExxonMobil", "Exxon Mobil", "Exxon"),
    "JNJ": ("Johnson & Johnson", "Janssen"),
    "SPY": ("SPDR S&P 500 ETF Trust", "SPDR S&P 500"),
    "UNH": ("UnitedHealth Group", "UnitedHealthcare", "UnitedHealth", "Optum"),
    "V": ("Visa Inc.", "Visa"),
    "MA": ("Mastercard Incorporated", "Mastercard"),
    "PG": ("Procter & Gamble", "P&G"),
    "HD": ("The Home Depot", "Home Depot"),
    "COST": ("Costco Wholesale", "Costco"),
    "WMT": ("Walmart Inc.", "Walmart", "Wal-Mart"),
    "KO": ("The Coca-Cola Company", "Coca-Cola"),
    "PEP": ("PepsiCo, Inc.", "PepsiCo", "Frito-Lay"),
    "CVX": ("Chevron Corporation", "Chevron"),
    "LLY": ("Eli Lilly and Company", "Eli Lilly", "Lilly"),
    "ABBV": ("AbbVie Inc.", "AbbVie"),
    "MRK": ("Merck & Co.", "Merck"),
    "BAC": ("Bank of America Corporation", "Bank of America"),
    "GS": ("The Goldman Sachs Group", "Goldman Sachs"),
    "CAT": ("Caterpillar Inc.", "Caterpillar"),
    "BA": ("The Boeing Company", "Boeing"),
    "BRK-B": ("Berkshire Hathaway",),
}
PRODUCT_NAMES: dict[str, tuple[str, ...]] = {
    "AAPL": ("iPhone", "iPad", "MacBook", "Mac", "iOS", "macOS", "App Store", "AirPods", "Apple Watch"),
    "NVDA": ("GeForce", "CUDA", "Mellanox", "DGX"),
    "MSFT": ("Windows", "Azure", "Xbox", "Office 365", "LinkedIn"),
    "META": ("Instagram", "WhatsApp", "Messenger", "Oculus"),
    "GOOGL": ("YouTube", "Android", "Waymo"),
    "AMZN": ("AWS", "Amazon Web Services", "Prime", "Alexa", "Whole Foods"),
    "JNJ": ("Tylenol", "Neutrogena"),
    "LLY": ("Mounjaro", "Trulicity"),
    "ABBV": ("Humira",),
    "MRK": ("Keytruda",),
    "BA": ("737 MAX",),
}


def _name_stem(name: str) -> str:
    """``Apple Inc.`` -> ``Apple``: drop a trailing corporate suffix (one level)."""
    return re.sub(
        r"[\s,]+(Inc\.?|Incorporated|Corporation|Corp\.?|Company|Co\.?|Ltd\.?|plc|PLC|"
        r"Holdings|Group|N\.A\.)$",
        "",
        name.strip(),
    ).strip(" ,")


def _universe() -> list[str]:
    from .evaluation import UNIVERSES  # local import: evaluation imports the desk

    return list(UNIVERSES["all"])


_dropped_logged: set[str] = set()


def is_scale_free_key(key: str) -> bool:
    return key in SCALE_FREE_KEYS or key.endswith(_SCALE_FREE_SUFFIXES) or key.startswith(_SCALE_FREE_PREFIXES)


class Anonymizer:
    def __init__(self, instrument: Instrument, as_of: date, ref_price: float):
        if not ref_price > 0:
            raise ValueError("reference price must be positive")
        self.instrument, self.as_of, self.ref = instrument, as_of, float(ref_price)
        if instrument.is_fx:
            self.aliases = [  # longest first so the pair is replaced before its parts
                (instrument.yahoo_symbol, "PAIR_X"),
                (f"{instrument.base}/{instrument.quote}", "CCY_BASE/CCY_QUOTE"),
                (instrument.symbol, "PAIR_X"),
                (instrument.base, "CCY_BASE"),
                (instrument.quote, "CCY_QUOTE"),
            ]
            self.restores = [
                ("CCY_BASE/CCY_QUOTE", instrument.display),
                ("PAIR_X", instrument.symbol),
                ("CCY_BASE", instrument.base),
                ("CCY_QUOTE", instrument.quote),
            ]
        else:
            self.aliases = [(instrument.yahoo_symbol, "STOCK_X"), (instrument.symbol, "STOCK_X")]
            self.restores = [("STOCK_X", instrument.symbol)]
        self._patterns = [
            (re.compile(rf"(?<![A-Za-z0-9]){re.escape(real)}(?![A-Za-z0-9])"), alias)  # type: ignore[type-var]  # aliases built from set symbols
            for real, alias in self.aliases
        ]
        self.accessions: dict[str, str] = {}  # real accession -> ACC_n
        self._names: set[str] = set()
        self._text_patterns: list[tuple[re.Pattern, str]] | None = None
        self._name_patterns: list[tuple[re.Pattern, str]] | None = None
        if not instrument.is_fx:
            self.add_names(COMPANY_NAMES.get(instrument.symbol.upper(), ()))

    # ------------------------------------------------------- name map
    def add_names(self, names: Any) -> None:
        """Add company names for the instrument (EDGAR ``entityName`` / ``formerNames``)."""
        for n in names or ():
            if isinstance(n, str) and len(n.strip()) >= 3:
                self._names.update({n.strip(), _name_stem(n)} - {""})
        self._text_patterns = None
        self._name_patterns = None

    def _build_rules(self, with_tickers: bool) -> list[tuple[re.Pattern, str]]:
        own = self.instrument.symbol.upper()
        mine = {n for n in self._names if len(n) >= 3}
        products = set(PRODUCT_NAMES.get(own, ())) if not self.instrument.is_fx else set()
        others: set[str] = set()
        for t in _universe():
            if t.upper() == own:
                continue
            if with_tickers and len(t) >= 2 and t.isupper():
                others.add(t)
            for n in COMPANY_NAMES.get(t, ()):
                others.update({n, _name_stem(n)} - {""})
        others -= mine
        # Case-sensitive (so "Prime" is not "prime"), plus the all-caps form EDGAR uses
        # ("APPLE INC"); a dict keeps the first alias for a spelling.
        rules: dict[str, str] = {}
        for names, alias in ((mine, "COMPANY_X"), (products, "PRODUCT_X"), (others, "OTHER_CO")):
            for n in names:
                rules.setdefault(n, alias)
                rules.setdefault(n.upper(), alias)
        return [
            (re.compile(rf"(?<![A-Za-z0-9]){re.escape(n)}(?![A-Za-z0-9])"), rules[n])
            for n in sorted(rules, key=len, reverse=True)
        ]  # longest first: "Apple Inc." before "Apple"

    def _text_rules(self) -> list[tuple[re.Pattern, str]]:
        """Names and other universe tickers (third-party text)."""
        if self._text_patterns is None:
            self._text_patterns = self._build_rules(with_tickers=True)
        return self._text_patterns

    def _name_rules(self) -> list[tuple[re.Pattern, str]]:
        """Company and product names only (price path). Other universe tickers are left alone
        here: short upper-case tickers (``MA``, ``CAT``, ``COST``) collide with prompt text."""
        if self._name_patterns is None:
            self._name_patterns = self._build_rules(with_tickers=False)
        return self._name_patterns

    def accession_real(self, alias: str) -> str:
        """``ACC_n`` -> the real accession number (unknown strings come back unchanged)."""
        for real, a in self.accessions.items():
            if a == alias:
                return real
        return alias

    # ------------------------------------------------------------ prices
    def px(self, v: float | None) -> float | None:
        return None if v is None else v * 100.0 / self.ref

    def unpx(self, v: float | None) -> float | None:
        return None if v is None else v * self.ref / 100.0

    def facts(self, facts: dict[str, Any]) -> dict[str, Any]:
        """Rebase price-level keys, keep scale-free keys, drop everything else.

        ``None`` and booleans always pass (they carry no scale). A dropped key is logged
        once per process at DEBUG so a new provider field can be added to the allow-list.
        """
        out = {}
        dropped = []
        for k, v in facts.items():
            if k in PRICE_KEYS and isinstance(v, (int, float)) and not isinstance(v, bool):
                out[k] = self.px(float(v))
            elif v is None or isinstance(v, bool) or is_scale_free_key(k):
                out[k] = v
            else:
                dropped.append(k)
        if dropped:
            new = [k for k in dropped if k not in _dropped_logged]
            if new:
                _dropped_logged.update(new)
                log.debug("anonymised prompt drops non-scale-free fact keys %s", new)
        return out

    # ------------------------------------------------------------- text
    def relative(self, d: date) -> str:
        n = (d - self.as_of).days
        return "D0" if n == 0 else f"D{n:+d}"

    def _acc(self, m: re.Match) -> str:
        real = m[0] if m[4] is None else f"{m[4][:10]}-{m[4][10:12]}-{m[4][12:]}"
        if real not in self.accessions:
            self.accessions[real] = f"ACC_{len(self.accessions) + 1}"
        return self.accessions[real]

    def _date_or(self, m: re.Match, y: int, mo: int, d: int) -> str:
        try:
            return self.relative(date(y, mo, d))
        except ValueError:  # not a real date
            return m[0]

    def scrub(self, text: str) -> str:
        for pat, alias in self._patterns:
            text = pat.sub(alias, text)
        # v0.17: company and product names (own -> COMPANY_X / PRODUCT_X, peers -> OTHER_CO), so
        # real headlines on the price path no longer name the company.
        for pat, alias in self._name_rules():
            text = pat.sub(alias, text)
        text = _ACCESSION.sub(self._acc, text)
        text = _CIK.sub("CIK_X", text)
        return _ISO_DATE.sub(lambda m: self._date_or(m, int(m[1]), int(m[2]), int(m[3])), text)

    def scrub_text(self, text: str) -> str:
        """``scrub`` plus company, product and peer names, written-out dates and bare years:
        for third-party text (filings, central-bank statements) on the text-analyst path."""
        text = self.scrub(text)
        for pat, alias in self._text_rules():
            text = pat.sub(alias, text)
        text = _MDY.sub(lambda m: self._date_or(m, int(m[3]), _MONTHS[m[1].lower()], int(m[2])), text)
        text = _DMY.sub(lambda m: self._date_or(m, int(m[3]), _MONTHS[m[2].lower()], int(m[1])), text)
        text = _US_DATE.sub(lambda m: self._date_or(m, int(m[3]), int(m[1]), int(m[2])), text)

        def month(m: re.Match) -> str:
            n = (int(m[2]) - self.as_of.year) * 12 + _MONTHS[m[1].lower()] - self.as_of.month
            return "M0" if n == 0 else f"M{n:+d}"

        text = _MY.sub(month, text)

        def year(m: re.Match) -> str:
            n = int(m[1]) - self.as_of.year
            return "Y0" if n == 0 else f"Y{n:+d}"

        return _YEAR.sub(year, text)

    def restore(self, value: Any) -> Any:
        """Put real names back into model output (recursively for JSON)."""
        if isinstance(value, str):
            for alias, real in self.restores:
                value = value.replace(alias, real)  # type: ignore[arg-type]  # restores built from set symbols
            # longest alias first so ACC_12 is not read as ACC_1 followed by "2"
            for real, alias in sorted(self.accessions.items(), key=lambda kv: -len(kv[1])):
                value = value.replace(alias, real)
            return value
        if isinstance(value, list):
            return [self.restore(v) for v in value]
        if isinstance(value, dict):
            return {k: self.restore(v) for k, v in value.items()}
        return value


def enforce_llm_anonymize(config: dict) -> bool:
    """Turn ``llm_anonymize`` on for a run that has a model attached (review N8).

    Every study date so far lies inside the local model's training window, so a model path
    without anonymisation can recall instead of reason. The rules path (no model) is not
    touched. ``allow_deanonymized_llm: True`` keeps ``llm_anonymize: False`` for a deliberate
    de-anonymised control run. The decision is written back into the config, so evaluation
    and calibration evidence (``anonymized=``) records what actually ran, and
    ``llm_anonymize_forced`` says whether this function changed it. Returns the final value.
    """
    if config.get("llm_anonymize"):
        config.setdefault("llm_anonymize_forced", False)
        return True
    if config.get("allow_deanonymized_llm"):
        log.warning(
            "model run WITHOUT anonymisation (allow_deanonymized_llm is set): prompts carry real tickers, names and dates"
        )
        config["llm_anonymize_forced"] = False
        return False
    log.warning("llm_anonymize forced on: a model is attached (set allow_deanonymized_llm to run a de-anonymised control)")
    config["llm_anonymize"] = True
    config["llm_anonymize_forced"] = True
    return True
