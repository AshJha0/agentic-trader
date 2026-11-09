# Dataset card: SEC EDGAR

Back to the [inventory](INVENTORY.md). Evidence classes are defined there.

**Code:** `agentic_trader/data/edgar.py` (XBRL facts, filing events),
`agentic_trader/data/edgar_text.py` (filing sections). **Licence:** see `DATA_LICENSING.md`;
SEC fair-access rules require a declared user agent and limited request rate.

## What it provides
XBRL fundamentals, 8-K and periodic-report events, filing sections (risk factors, MD&A, 8-K
items), and the submissions JSON with `name` and `formerNames`, used since v0.17 to build the
anonymiser's company-name map.

## Point-in-time handling
Every filing is visible from its acceptance time (UTC); the text analysts read a filing only if
accepted at or before 20:00 UTC on the decision day (`text_analysts.TEXT_CUTOFF_UTC`).

## Known issues
- Accession numbers start with the filer's CIK, which identifies the company; the anonymiser
  replaces them with `ACC_n` since v0.17 (review N2).
- Filing text names the company, its products and competitors; the built-in name map covers
  the research universe only.
