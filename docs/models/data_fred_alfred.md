# Dataset card: FRED / ALFRED

Back to the [inventory](INVENTORY.md). Evidence classes are defined there.

**Code:** `agentic_trader/data/fred.py`. **Licence:** see `DATA_LICENSING.md`. No API key.

## What it provides
Policy rates, T-bill yields and inflation per currency.

## Point-in-time handling
With `fred_vintages` on, revised series (CPI) are read from the ALFRED vintage current at the
as-of date, sampled monthly, so a value may appear up to a month late, the conservative side.
Policy rates are never revised and come from the latest download (`fred.py` docstring).

## Known issues
Without vintages, revised series show today's numbers for past dates (look-ahead). The default
is `fred_vintages: False`; research runs should set it.
