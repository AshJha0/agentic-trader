"""Instrument definitions shared by the equity and FX pipelines."""
from __future__ import annotations

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
        """Parse "AAPL", "EURUSD", "EUR/USD" or "EURUSD=X".

        Six-letter codes made of two known currencies are treated as FX unless
        ``asset_class="equity"`` is given explicitly.
        """
        raw = text.strip().upper()
        cleaned = raw.replace("/", "").replace("=X", "").replace("_", "")
        looks_fx = len(cleaned) == 6 and cleaned[:3] in CURRENCIES and cleaned[3:] in CURRENCIES
        if asset_class == FX or (asset_class is None and looks_fx):
            if not looks_fx:
                raise ValueError(f"{text!r} is not a recognised currency pair")
            return cls(cleaned, FX, cleaned[:3], cleaned[3:])
        if asset_class not in (None, EQUITY):
            raise ValueError(f"unknown asset class {asset_class!r}")
        return cls(raw, EQUITY)
