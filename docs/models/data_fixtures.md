# Dataset card: fixtures and synthetic series

Back to the [inventory](INVENTORY.md). Evidence classes are defined there.

**Code:** `tests/`, `tests/data/`, `agentic_trader/data/synthetic.py`. **Licence:** repository
licence (`LICENSE`); recorded model replies are this project's own output.

## What it provides
Invented filings and statements, recorded model plans (`tests/data/v15_local_model_plans.jsonl`),
synthetic price paths (GBM, GARCH) for tests.

## Point-in-time handling
By construction; tests assert that a forecast at bar i is unchanged when later bars change.

## Known issues
Fixture results test the machinery, never a model's quality (evidence class fixture).
