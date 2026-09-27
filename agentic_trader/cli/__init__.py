"""Command-line interface.

Decisions
    agentic-trader analyze   AAPL --date 2024-03-01 [--position 0.4]
    agentic-trader task      EURUSD --date 2024-03-01 [--role trader] [--approval queued]
    agentic-trader scan      AAPL,MSFT,EURUSD --date 2024-03-01 --out decisions.csv
Backtests and research
    agentic-trader backtest  NVDA --start 2024-01-02 --end 2024-03-28 --every 5
    agentic-trader baselines USDJPY --start 2023-01-02 --end 2023-12-29
    agentic-trader portfolio AAPL,MSFT,EURUSD --start ... --end ... [--weighting risk_parity]
    agentic-trader evaluate  --data yahoo --periods design,holdout,q1_2024
    agentic-trader alpha     AAPL --start 2021-01-04 --end 2024-03-28 [--horizon 10]
    agentic-trader execute   AAPL --date 2024-03-01 --target 0.6 --current 0.1 [--algo vwap]
    agentic-trader stats     returns.csv [--trials 16]
Agentic services
    agentic-trader tools     [--json]
    agentic-trader serve     [--host 127.0.0.1 --port 8000]
    agentic-trader mcp       [--data yahoo]
    agentic-trader info

Invalid input (unknown symbol, no data, bad dates) exits with status 2 and a
one-line error instead of a traceback; use -v for details.
"""
from __future__ import annotations

import json
import logging
import os
import sys

from .common import _config, load_dotenv  # noqa: F401  (re-exported for backward compatibility)
from .parser import build_parser

log = logging.getLogger("agentic_trader.cli")

NO_DOTENV_ENV = "AGENTIC_TRADER_NO_DOTENV"


def main(argv: list[str] | None = None, *, dotenv: bool | None = None) -> int:
    """Run one command. ``argv=None`` reads the real command line and, unless
    ``AGENTIC_TRADER_NO_DOTENV`` is set, the local ``.env``; a caller that passes ``argv``
    (tests, embedding code) gets no file read into its process environment unless it
    asks with ``dotenv=True``."""
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if dotenv is None:
        dotenv = argv is None
    if dotenv and not os.environ.get(NO_DOTENV_ENV):
        load_dotenv()
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if getattr(args, "verbose", False) else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    try:
        return args.func(args)
    except (ValueError, FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        if getattr(args, "verbose", False):
            log.exception("failed")
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
