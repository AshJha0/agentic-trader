"""v0.15 plan item 3.3: the registered trial "v0.15 GDELT headline tone (rules lexicon)" on
the DESIGN period only.

GDELT DOC 2.0 (``data/gdelt.py``) only indexes articles from 2017-01-01, so the trial uses the
overlap of the design period (``evaluation.PERIODS["design"]``, 2016-01-04 -> 2021-12-31) with
that coverage: 2017-01-02 -> 2021-12-31. Nothing after the design end is requested; the holdout
is never read.

Two steps:

``download``: one ``artlist`` request per name per calendar week (250 headlines max, sorted
newest first, so busy weeks are truncated towards their last days: coverage is reported).
Raw JSON is cached under ``results/v15/gdelt_cache/`` (git-ignored) and the step resumes from
the cache. At least 6 s between requests; HTTP 429 or GDELT's plain-text throttle reply backs
off and retries. About 3,900 requests, so run it detached.

``analyse``: per name, de-duplicated English headlines scored by the rules lexicon
(``sentiment.score_text`` via ``GdeltProvider``), daily mean tone by UTC ``seendate``; the
signal on session ``t`` is the mean daily tone over the 7 calendar days strictly before ``t``
(a headline seen on day ``t`` is never used on ``t``). Purged IC and decay as every other
alpha: ``alpha.text_alpha_decay`` (``leakage.ic_purged``, 5 folds) against Yahoo closes.

    python scripts/v15_gdelt_design.py download
    python scripts/v15_gdelt_design.py analyse [--out results/v15/gdelt_design.json]

Network (GDELT, Yahoo); the test suite never runs this script. $0, no LLM calls.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError

import numpy as np
import pandas as pd

from agentic_trader.data.gdelt import GdeltProvider, clean_articles, daily_tone, _seen
from agentic_trader.evaluation import CORE_UNIVERSE, PERIODS
from agentic_trader.sentiment import score_text

GDELT_START = date(2017, 1, 1)   # first day DOC 2.0 indexes
CACHE = Path("results/v15/gdelt_cache")
MIN_INTERVAL = 6.0
LOOKBACK_DAYS = 7

QUERIES: dict[str, str] = {
    "AAPL": '"Apple Inc" OR "Apple shares" OR "Apple stock"',
    "NVDA": "Nvidia",
    "MSFT": "Microsoft",
    "META": 'Facebook OR "Meta Platforms"',
    "GOOGL": "Google OR Alphabet",
    "AMZN": "Amazon",
    "JPM": "JPMorgan",
    "XOM": "Exxon",
    "JNJ": '"Johnson & Johnson"',
    "SPY": '"stock market" OR "Wall Street" OR "S&P 500"',
    "EURUSD": '"euro" dollar',
    "USDJPY": '"yen" dollar',
    "GBPUSD": '"sterling" OR "British pound"',
    "AUDUSD": '"Australian dollar"',
    "USDCAD": '"Canadian dollar" OR loonie',
}


def window() -> tuple[date, date]:
    d0, d1 = (date.fromisoformat(x) for x in PERIODS["design"])
    return max(d0, GDELT_START), d1


def weeks(start: date, end: date):
    d = start
    while d <= end:
        e = min(d + timedelta(days=7), end + timedelta(days=1))
        yield d, e
        d = e


def query_for(sym: str) -> str:
    q = QUERIES[sym]
    return f"({q}) sourcelang:english" if " OR " in q else f"{q} sourcelang:english"


def download() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    p = GdeltProvider(min_interval=MIN_INTERVAL)
    start, end = window()
    todo = [(s, a, b) for s in QUERIES for a, b in weeks(start, end)
            if not (CACHE / s / f"{a:%Y%m%d}.json").exists()]
    print(f"{len(todo)} requests to go", flush=True)
    last, backoff = 0.0, 60.0
    for i, (sym, a, b) in enumerate(todo):
        url = p.url(query_for(sym), datetime(a.year, a.month, a.day), datetime(b.year, b.month, b.day))
        while True:
            wait = MIN_INTERVAL - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
            last = time.monotonic()
            try:
                raw = p._http(url)
            except HTTPError as e:
                if e.code == 429:
                    print(f"429, sleeping {backoff:.0f}s", flush=True)
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 900)
                    continue
                raw = b'{"articles": [], "error": "http %d"}' % e.code
            except (URLError, TimeoutError, OSError) as e:
                print(f"network error {e!r}, sleeping 60s", flush=True)
                time.sleep(60)
                continue
            if raw.lstrip()[:1] not in (b"{", b""):
                if b"limit requests" in raw:
                    print(f"throttled, sleeping {backoff:.0f}s", flush=True)
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 900)
                    continue
                raw = json.dumps({"articles": [], "error": raw[:200].decode("utf-8", "replace")}).encode()
            backoff = 60.0
            break
        (CACHE / sym).mkdir(exist_ok=True)
        (CACHE / sym / f"{a:%Y%m%d}.json").write_bytes(raw or b"{}")
        if i % 50 == 0:
            print(f"{i}/{len(todo)} {sym} {a}", flush=True)
    print("download done", flush=True)


def headlines(sym: str) -> list:
    from agentic_trader.data.base import NewsItem
    arts = []
    for f in sorted((CACHE / sym).glob("*.json")):
        try:
            arts += json.loads(f.read_bytes() or b"{}").get("articles", []) or []
        except json.JSONDecodeError:
            continue
    out = []
    for a in clean_articles(arts, "English"):
        t = _seen(a["seendate"])
        out.append(NewsItem(published=t.date(), headline=str(a["title"]), source="gdelt",
                            sentiment=score_text(str(a["title"])), tags=["gdelt"]))
    return out


def signal_on(sessions: pd.DatetimeIndex, tone: dict[date, float]) -> np.ndarray:
    s = pd.Series(tone, dtype=float)
    s.index = pd.to_datetime(s.index)
    out = np.full(len(sessions), np.nan)
    for i, t in enumerate(sessions):
        w = s[(s.index >= t - pd.Timedelta(days=LOOKBACK_DAYS)) & (s.index < t)]
        if len(w):
            out[i] = float(w.mean())
    return out


def analyse(out_path: Path) -> dict:
    from agentic_trader.alpha import text_alpha_decay
    from agentic_trader.config import DEFAULT_CONFIG
    from agentic_trader.data.yahoo import YahooProvider
    from agentic_trader.instruments import Instrument
    start, end = window()
    yp = YahooProvider(DEFAULT_CONFIG)
    rows = []
    for sym in CORE_UNIVERSE["equity"] + CORE_UNIVERSE["fx"]:
        items = headlines(sym)
        tone = daily_tone(items)
        h = yp.history(Instrument.parse(sym), start, end)
        h = h[(h.index >= pd.Timestamp(start)) & (h.index <= pd.Timestamp(end))]
        sig = signal_on(pd.DatetimeIndex(h.index).tz_localize(None), tone)
        dec = text_alpha_decay(sig, h["Close"].to_numpy(float))
        rows.append({"symbol": sym, "headlines": len(items), "days_with_headlines": len(tone),
                     "sessions": len(h), "signal_coverage": round(float(np.isfinite(sig).mean()), 4),
                     "decay": {str(k): {kk: (None if not np.isfinite(vv) else round(float(vv), 4))
                                        for kk, vv in v.items()} for k, v in dec.items()}})
        print(sym, rows[-1]["headlines"], rows[-1]["days_with_headlines"], dec[1], dec[5], flush=True)
    summary = {}
    for hz in ("1", "5", "10", "21", "63"):
        ics = [r["decay"][hz]["ic"] for r in rows if r["decay"][hz]["ic"] is not None]
        ts = [r["decay"][hz]["t"] for r in rows if r["decay"][hz]["t"] is not None]
        summary[hz] = {"mean_ic": round(float(np.mean(ics)), 4) if ics else None,
                       "mean_t": round(float(np.mean(ts)), 3) if ts else None,
                       "t_of_mean_ic": (round(float(np.mean(ics) / (np.std(ics, ddof=1) / np.sqrt(len(ics)))), 3)
                                        if len(ics) > 2 else None),
                       "names": len(ics), "names_abs_t_gt_2": int(sum(abs(t) > 2 for t in ts))}
    res = {"trial": "v0.15 GDELT headline tone (rules lexicon)", "design_period": PERIODS["design"],
           "window_used": [start.isoformat(), end.isoformat()],
           "note": "GDELT DOC 2.0 starts 2017-01-01; design overlap only. Weekly artlist, 250 max, newest first.",
           "lookback_days": LOOKBACK_DAYS, "n_folds": 5, "queries": QUERIES, "summary": summary, "rows": rows}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(res, indent=2))
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=("download", "analyse"))
    ap.add_argument("--out", default="results/v15/gdelt_design.json")
    a = ap.parse_args(argv)
    if a.step == "download":
        download()
    else:
        print(json.dumps(analyse(Path(a.out))["summary"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
