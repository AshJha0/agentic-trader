# Data licensing: what this repository stores, publishes and why

This project reads three free data sources. This page says, for each one, what the code
fetches, what ends up in the public repository, and the reason that is allowed. It is the
maintainer's reading of each provider's published terms, not legal advice; nobody has had
it checked by counsel. Each row carries its evidence class: **terms** (read in the
provider's published terms), **code** (checked in this repository's code) or **unverified**.

## The plain rule

Raw third-party data does not go into git. What is committed is derived from it (returns of
a strategy, summary statistics, hashes) and cannot be turned back into the source series.

## Per source

| Source | Fetched by | Raw data stored | Published in the repo | Why this is allowed |
|---|---|---|---|---|
| Yahoo Finance (via `yfinance`) | `agentic_trader/data/yahoo.py` | Local caches only (`build/`, git-ignored); the paper session's bars and corporate actions under `results/paper/bars/<as-of>/` (git-ignored, on the machine that ran the session; not uploaded as an Actions artifact since round 2) (code) | Strategy daily returns (`results/paper/ledger*.csv`), exposure and cost fractions, revision cells (differences of strategy returns), the SHA-256 of each stored bar file in `runs.jsonl` (code) | Yahoo's terms allow personal, non-commercial use and forbid redistributing the data (terms). Returns of a rule-based book and file hashes are our own computation; no price, volume or corporate-action series is published (code). |
| FRED (St. Louis Fed) | `agentic_trader/data/fred.py` | Local cache under `build/fred_cache` (git-ignored) (code) | Nothing raw; the risk-free rate enters the ledger only as the `rf` column credited to the books (code) | The FRED API terms allow use with attribution. Some series are owned by third parties and carry their own copyright notes (terms); `rf` is a policy-rate series, but which exact series is used has not been checked against its notes (unverified). |
| SEC EDGAR | `agentic_trader/data/edgar.py`, `edgar_text.py` | Local cache under `build/edgar_cache` (git-ignored) (code) | Retrieval questions written for the evaluation set (`agentic_trader/agentic/knowledge/retrieval_eval/`) that quote short passages of filings (code) | EDGAR filings are public records of the US government and free to reuse; access must follow the SEC fair-access policy: a declared User-Agent and at most 10 requests per second (terms). The provider sends `edgar_user_agent` (code). |

## Paper record and Yahoo bars (v0.17, R4.1)

Plain idea: to reproduce a past paper session after Yahoo re-adjusts its history, we need the
bars that session read. We keep them, but privately.

What happens: `scripts/paper_trade_v09.py` writes `prices.csv.gz` (the adjusted bars as
served) and `actions.csv.gz` (raw close, split ratio, cash dividend per ex-date) to
`results/paper/bars/<as-of>/`. That directory is in `.gitignore` and excluded from the
`paper-record` artifact the publish job commits from. It is not uploaded anywhere: the
`paper-bars` Actions artifact was removed in round 2 (owner decision D6, 2026-11-12), because
the repository is public and a public repository's Actions artifacts can be downloaded by
other GitHub users (code: `.github/workflows/paper.yml` has no bars upload step). The copy
that persists is the one on the machine that ran the session: the laptop fallback
(`scripts/paper_daily.cmd`) keeps it in its git-ignored `results/paper/bars/`; a run on the
Actions runner discards it when the job ends. `runs.jsonl` records `bars.files`: file name to
SHA-256.

Worked example: to check that a revision on 2026-11-12 came from a dividend re-adjustment,
take the laptop's `results/paper/bars/2026-11-11/` and `2026-11-12/`, confirm each file's
SHA-256 against `runs.jsonl`, then compare `actions.csv.gz` for the symbol in question. For a
session the Actions runner recorded, only the hashes exist; the bars can be re-fetched, and
a re-fetch whose SHA-256 differs is itself evidence that Yahoo restated the history.

## Owner checks still open

- Confirm the FRED series behind `rf` has no third-party copyright note (unverified above).
- Since the bars are no longer uploaded, sessions recorded by the Actions runner keep only
  their hashes. If an archive of those bars is wanted, it has to be a private store outside
  the public repository (not an Actions artifact).
