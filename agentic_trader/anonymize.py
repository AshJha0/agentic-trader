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
          is rebased so that the last close is 100.

Returns, ratios, rates, volatilities and indicator values (RSI, %B, KDJ) are
scale-free and pass through unchanged. Prices the model returns (stop-loss,
take-profit) are mapped back with ``unpx``; names in its text are restored for
the audit trail.

Residual leakage (documented in the threat model): distinctive statistics such
as a -0.1% policy rate, company names in real headlines, and the shape of the
return series itself.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from .instruments import Instrument

# Fact keys that carry price levels (or price differences) and must be rebased.
PRICE_KEYS = frozenset({
    "close", "last_close", "sma20", "sma50", "sma200", "macd_line", "macd_hist",
    "macd_hist_prev", "atr14", "entry_price", "stop_loss", "take_profit",
})

_ISO_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")


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
        out = {}
        for k, v in facts.items():
            if k in PRICE_KEYS and isinstance(v, (int, float)) and not isinstance(v, bool):
                out[k] = self.px(float(v))
            else:
                out[k] = v
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
