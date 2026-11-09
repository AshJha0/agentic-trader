# Dataset card: Yahoo Finance

Back to the [inventory](INVENTORY.md). Evidence classes are defined there.

**Code:** `agentic_trader/data/yahoo.py`. **Licence:** see `DATA_LICENSING.md`. Yahoo data is
for personal use; review Appendix D, N2 notes that storing raw bars in a public repository
would redistribute it.

## What it provides
Daily dividend- and split-adjusted closes (`auto_adjust=True`), recent headlines, and an
unadjusted download used to rebuild the as-traded close for fundamentals ratios.

## Point-in-time handling
- A bar dated today (New York calendar) is never served, so an in-progress bar is not read as a
  close (`yahoo.py` docstring).
- Historical headlines come from the EDGAR filing stream instead; Yahoo headlines only for the
  last month.

## Known issues
- Adjusted closes are re-adjusted after every later dividend or split, so a stored row cannot
  be recomputed exactly from a later download (review N6).
- Survivorship: the universes are today's survivors.
