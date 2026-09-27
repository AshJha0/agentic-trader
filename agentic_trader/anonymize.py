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

Residual leakage (documented in the threat model): distinctive statistics such
as a -0.1% policy rate, company names in real headlines, and the shape of the
return series itself.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

from .instruments import Instrument

log = logging.getLogger(__name__)

# Fact keys that carry price levels (or price differences) and must be rebased.
PRICE_KEYS = frozenset({
    "close", "last_close", "sma20", "sma50", "sma200", "macd_line", "macd_hist",
    "macd_hist_prev", "atr14", "entry_price", "stop_loss", "take_profit",
})

# Scale-free fact keys that may reach an anonymised prompt unchanged. Strings among them
# (dates, currency codes, a source label) are still passed through ``scrub``.
SCALE_FREE_KEYS = frozenset({
    # technical
    "rsi14", "bollinger_pct_b", "kdj_k", "kdj_d", "kdj_j", "realized_vol_20d_annual",
    "realized_vol_1y_annual", "zscore20", "return_5d", "return_20d", "return_60d", "return_12_1m",
    "bars", "atr_pct",
    # fundamentals: ratios, growth rates, margins, yields and filing dates
    "pe_ratio", "forward_pe", "sector_pe", "revenue_growth_yoy", "net_margin", "debt_to_equity",
    "fcf_yield", "eps_surprise", "insider_net_buying", "report_period_end", "revenue_period_end", "filed",
    "lag_days", "source",
    # FX macro
    "base", "quote", "base_rate", "quote_rate", "rate_diff", "base_inflation", "quote_inflation",
    "deviation_from_200d",
    # news and sentiment (headline text is fenced separately, never a fact)
    "lookback_days", "count", "recency_weighted_tone", "posts", "mean_post_sentiment",
    "recent_post_sentiment", "bullish_share", "volume_zscore",
    # alpha library: z-scores, ICs and counts (the peer list is replaced by its size)
    "latest", "ic", "combined_z", "breadth", "horizon",
    # trader and risk facts
    "short_selling_allowed", "max_position", "debate_winner", "debate_score", "debate_conviction",
    "current_position", "strategic_weight_when_neutral", "track_n", "track_hit_rate", "track_avg_pnl",
    "proposed_weight", "var_95_1d", "var_95_1d_short", "cvar_95_1d", "drawdown_from_60d_high",
    "target_vol", "max_var_95", "rebalance_band", "max_book_var_95", "book_var_95_now",
})

# Numeric keys not listed above pass when their name says they are dimensionless.
_SCALE_FREE_SUFFIXES = ("_yoy", "_pct", "_ratio", "_yield", "_margin", "_z", "_zscore", "_share",
                        "_rate", "_tone", "_sentiment", "_vol", "_ic", "_growth", "_surprise")
_SCALE_FREE_PREFIXES = ("return_", "track_", "ic_", "z_", "var_", "cvar_")

_ISO_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")

_dropped_logged: set[str] = set()


def is_scale_free_key(key: str) -> bool:
    return (key in SCALE_FREE_KEYS or key.endswith(_SCALE_FREE_SUFFIXES)
            or key.startswith(_SCALE_FREE_PREFIXES))


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
            self.restores = [("CCY_BASE/CCY_QUOTE", instrument.display), ("PAIR_X", instrument.symbol),
                             ("CCY_BASE", instrument.base), ("CCY_QUOTE", instrument.quote)]
        else:
            self.aliases = [(instrument.yahoo_symbol, "STOCK_X"), (instrument.symbol, "STOCK_X")]
            self.restores = [("STOCK_X", instrument.symbol)]
        self._patterns = [(re.compile(rf"(?<![A-Za-z0-9]){re.escape(real)}(?![A-Za-z0-9])"), alias)
                          for real, alias in self.aliases]

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

    def scrub(self, text: str) -> str:
        for pat, alias in self._patterns:
            text = pat.sub(alias, text)

        def repl(m: re.Match) -> str:
            try:
                return self.relative(date(int(m[1]), int(m[2]), int(m[3])))
            except ValueError:  # not a real date
                return m[0]
        return _ISO_DATE.sub(repl, text)

    def restore(self, value: Any) -> Any:
        """Put real names back into model output (recursively for JSON)."""
        if isinstance(value, str):
            for alias, real in self.restores:
                value = value.replace(alias, real)
            return value
        if isinstance(value, list):
            return [self.restore(v) for v in value]
        if isinstance(value, dict):
            return {k: self.restore(v) for k, v in value.items()}
        return value
