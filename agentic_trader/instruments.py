"""Instrument definitions shared by the equity and FX pipelines."""
from __future__ import annotations

import re
from dataclasses import dataclass

CURRENCIES = {
    "USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD", "SEK", "NOK", "DKK",
    "CNH", "CNY", "HKD", "SGD", "MXN", "ZAR", "TRY", "PLN", "INR", "KRW", "BRL",
}

EQUITY = "equity"
FX = "fx"


@dataclass(frozen=True)
class Instrument:
    symbol: str             # canonical: "AAPL" or "EURUSD"
    asset_class: str        # "equity" | "fx"
    base: str | None = None
    quote: str | None = None

    @property
    def is_fx(self) -> bool:
        return self.asset_class == FX

    @property
    def pip_size(self) -> float:
        if not self.is_fx:
            return 0.01
        return 0.01 if self.quote == "JPY" else 0.0001

    @property
    def periods_per_year(self) -> float:
        return 260.0 if self.is_fx else 252.0

    @property
    def yahoo_symbol(self) -> str:
        return f"{self.base}{self.quote}=X" if self.is_fx else self.symbol

    @property
    def display(self) -> str:
        return f"{self.base}/{self.quote}" if self.is_fx else self.symbol

    @classmethod
    def parse(cls, text: str, asset_class: str | None = None) -> "Instrument":
        """Parse "AAPL", "BRK.B", "EURUSD", "EUR/USD" or "EURUSD=X".

        Six-letter codes made of two known currencies are treated as FX unless
        ``asset_class="equity"`` is given explicitly. A "/" or "=X" marks the text
        as an intended currency pair, so a typo such as "EUR/XYZ" is rejected
        instead of silently becoming an equity ticker.
        """
        if not isinstance(text, str) or not text.strip():
            raise ValueError("empty symbol")
        if asset_class not in (None, EQUITY, FX):
            raise ValueError(f"unknown asset class {asset_class!r}")
        raw = text.strip().upper()
        cleaned = raw.replace("/", "").replace("=X", "").replace("_", "")
        looks_fx = len(cleaned) == 6 and cleaned[:3] in CURRENCIES and cleaned[3:] in CURRENCIES
        fx_intent = "/" in raw or raw.endswith("=X")
        if asset_class == FX or (asset_class is None and (looks_fx or fx_intent)):
            if not looks_fx:
                raise ValueError(f"{text!r} is not a recognised currency pair")
            return cls(cleaned, FX, cleaned[:3], cleaned[3:])
        if not _TICKER.fullmatch(raw):
            raise ValueError(f"{text!r} is not a valid equity ticker")
        return cls(raw, EQUITY)


# Letters/digits with optional class or exchange suffix: AAPL, BRK.B, BRK-B, RDS-A, ^GSPC, 7203.T
_TICKER = re.compile(r"\^?[A-Z0-9]{1,10}([.\-][A-Z0-9]{1,5})?")
