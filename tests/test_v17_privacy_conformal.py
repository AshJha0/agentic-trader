"""v0.17 lane L11: review findings N2, N7, N8 and N11 (docs/review/2026-11-09_review_and_plan.md).

Offline and model-free: fake backends only.
"""

from __future__ import annotations

import json
import logging
import math
import re
from datetime import date, datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from agentic_trader.anonymize import COMPANY_NAMES, Anonymizer, enforce_llm_anonymize
from agentic_trader.combine import calibration_points, conformal_halfwidth, conformal_interval
from agentic_trader.config import make_config
from agentic_trader.evaluation import CORE_UNIVERSE
from agentic_trader.instruments import Instrument
from agentic_trader.text_analysts import FundamentalsTextAnalyst, MacroTextAnalyst, TextInputs, text_reports

UTC = timezone.utc
AAPL = Instrument.parse("AAPL")
AS_OF = date(2021, 3, 1)
ACC = "0000320193-20-000096"  # Apple's CIK 320193 is its first 10 digits

FILING = (
    "Apple Inc. (CIK 0000320193) designs the iPhone and Mac. AAPL competes with "
    "Microsoft Corporation, GOOGL and Amazon. On October 30, 2020 the Company reported "
    "fiscal 2020 results; the board met 2020-10-29 and again 10/15/2020, and in January 2021. "
    "Revenue increased across every segment."
)


class Recorder:
    """A backend that records every prompt and replies with a canned claim."""

    def __init__(self, reply=None):
        self.prompts: list[str] = []
        self.reply = reply

    def complete_json(self, system, prompt, *, deep, schema):
        self.prompts.append(prompt)
        return self.reply(prompt) if callable(self.reply) else self.reply


def _sections():
    return [
        SimpleNamespace(
            symbol="AAPL",
            accession=ACC,
            form="10-K",
            section="7",
            visible_date=datetime(2020, 10, 30, 21, 30, tzinfo=UTC),
            text=FILING,
        )
    ]


def _leaks(prompt: str) -> list[str]:
    found = []
    for t in CORE_UNIVERSE["equity"]:
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(t)}(?![A-Za-z0-9])", prompt):
            found.append(t)
    for word in ("Apple", "APPLE", "iPhone", "Microsoft", "Amazon", "320193", ACC):
        if word in prompt:
            found.append(word)
    found += re.findall(r"\d{4}-\d{2}-\d{2}", prompt)
    found += re.findall(r"(?<!\d)(?:19|20)\d\d(?!\d)", prompt)
    return found


# ------------------------------------------------------------------ N2
def test_scrub_text_removes_names_cik_accession_and_dates():
    anon = Anonymizer(AAPL, AS_OF, 120.0)
    out = anon.scrub_text(f"accession={ACC} accepted=2020-10-30T21:30:00+00:00 " + FILING)
    assert _leaks(out) == [], out
    assert "COMPANY_X" in out and "PRODUCT_X" in out and "OTHER_CO" in out and "CIK_X" in out
    assert "ACC_1" in out and anon.accession_real("ACC_1") == ACC
    assert "D-122" in out and "Y-1" in out and "M-2" in out  # 2020-10-30, 2020, Jan 2021
    # ordinary words that happen to be product names in another case stay
    assert "prime" in anon.scrub_text("a prime example")


def test_fundamentals_prompt_is_anonymised_and_claims_map_back():
    def reply(prompt):
        quote = "Revenue increased across every segment."
        return json.dumps(
            {
                "claims": [
                    {"claim": "COMPANY_X growing", "direction": "positive", "accession": "ACC_1", "section": "7", "quote": quote}
                ]
            }
        )

    llm = Recorder(reply)
    anon = Anonymizer(AAPL, AS_OF, 120.0)
    res = FundamentalsTextAnalyst(llm, anon=anon).analyze("AAPL", _sections())
    assert _leaks(llm.prompts[0]) == [], llm.prompts[0]
    assert res.ok and res.result["claims"][0]["accession"] == ACC  # audit keeps the real id


def test_old_path_leaks_without_anon():
    """Regression guard: without an anonymiser the prompt does carry the identifiers (the
    pre-v0.17 behaviour for every text-analyst run, anonymised or not)."""
    llm = Recorder(None)
    FundamentalsTextAnalyst(llm).analyze("AAPL", _sections())
    assert "AAPL" in llm.prompts[0] and ACC in llm.prompts[0]


def test_text_reports_passes_the_anonymiser_and_edgar_names():
    class Edgar:
        def sections(self, symbol, cut):
            return _sections()

        def company_names(self, symbol):
            return ["APPLE COMPUTER INC", "Cupertino Fruit Holdings"]

    secs = _sections()
    secs[0].text += " Cupertino Fruit Holdings is the former name."
    llm = Recorder(
        json.dumps(
            {
                "claims": [
                    {"claim": "x", "direction": "positive", "accession": "ACC_1", "section": "7", "quote": "Revenue increased"}
                ]
            }
        )
    )
    anon = Anonymizer(AAPL, AS_OF, 120.0)
    edgar = Edgar()
    edgar.sections = lambda symbol, cut: secs
    reps = text_reports(["fundamentals_text"], llm, TextInputs(edgar=edgar), AAPL, AS_OF, anon=anon)
    p = llm.prompts[0]
    assert _leaks(p) == [] and "Cupertino" not in p, p
    assert not any(_leaks(x) for x in reps[0].key_points)  # later agents see aliases
    assert reps[0].facts["sections"] == [f"{ACC}/7"]  # audit trail keeps the real id


def test_macro_prompt_dates_scrubbed():
    llm = Recorder(json.dumps({"stance": "hawkish", "shift": 0.5, "quotes": ["rates rise at D-30"]}))
    anon = Anonymizer(Instrument.parse("EURUSD"), AS_OF, 1.2)
    res = MacroTextAnalyst(llm, anon=anon).analyze("On 2021-01-30 the Committee said rates rise at 2021-01-30.")
    assert "2021" not in llm.prompts[0] and res.ok


def test_price_path_scrub_keeps_numbers_and_scrubs_names():
    anon = Anonymizer(AAPL, AS_OF, 120.0)
    s = "AAPL close 120.0 on 2021-02-26, rsi 55, 2000 shares, Apple headline"
    assert anon.scrub(s) == "STOCK_X close 120.0 on D-3, rsi 55, 2000 shares, COMPANY_X headline"


def test_price_path_headlines_do_not_name_the_company():
    # v0.17 boundary fix: on v0.16 code ``scrub`` left every name in a headline untouched.
    anon = Anonymizer(AAPL, AS_OF, 120.0)
    heads = [
        "Apple Inc. beats estimates as iPhone sales jump",
        "Microsoft and Apple trade blows over the App Store",
        "APPLE files 10-K; Nvidia rallies",
    ]
    out = [anon.scrub(h) for h in heads]
    assert out == [
        "COMPANY_X beats estimates as PRODUCT_X sales jump",
        "OTHER_CO and COMPANY_X trade blows over the PRODUCT_X",
        "COMPANY_X files 10-K; OTHER_CO rallies",
    ]
    names = [n for t in CORE_UNIVERSE for n in COMPANY_NAMES.get(t, ()) if len(n) >= 3]
    assert not any(re.search(rf"(?<![A-Za-z0-9]){re.escape(n)}(?![A-Za-z0-9])", o) for o in out for n in names)
    # peer tickers are not aliased on the price path (``MA``, ``CAT`` collide with prompt text)
    assert anon.scrub("MA crossover; CAT score 3") == "MA crossover; CAT score 3"
    assert anon.scrub(anon.scrub(heads[0])) == out[0]  # idempotent


# ------------------------------------------------------------------ N8
def test_model_path_forces_anonymisation(caplog):
    cfg = make_config()
    with caplog.at_level(logging.WARNING):
        assert enforce_llm_anonymize(cfg) is True
    assert cfg["llm_anonymize"] and cfg["llm_anonymize_forced"] and "forced on" in caplog.text
    ctl = make_config({"allow_deanonymized_llm": True})
    assert enforce_llm_anonymize(ctl) is False and not ctl["llm_anonymize"]
    assert make_config()["llm_anonymize"] is False  # rules path default unchanged


def test_graph_with_model_turns_anonymisation_on():
    from agentic_trader.graph import TradingGraph

    g = TradingGraph({"memory_path": None}, llm=Recorder(None))
    assert g.config["llm_anonymize"] is True
    assert TradingGraph({"memory_path": None}).config["llm_anonymize"] is False


def test_remote_local_llm_url_refused_unless_flagged():
    from agentic_trader.local_llm import LocalLLM, is_loopback_host

    base = {"local_llm_model": "qwen2.5:7b"}
    for ok in ("http://127.0.0.1:11434", "http://localhost:11434", "http://[::1]:11434", "http://127.0.0.2"):
        assert LocalLLM({**base, "local_llm_url": ok}).host
    for bad in ("http://10.0.0.5:11434", "https://ollama.example.com", "http://localhost.evil.com:1"):
        with pytest.raises(ValueError, match="loopback"):
            LocalLLM({**base, "local_llm_url": bad})
    llm = LocalLLM({**base, "local_llm_url": "http://10.0.0.5:11434", "allow_remote_llm": True})
    llm.read_response({"model": "qwen2.5:7b", "message": {"content": "hi"}})
    assert llm.last_call["llm_host"] == "10.0.0.5" and llm.last_call["remote_llm_allowed"] is True
    assert not is_loopback_host("0.0.0.0")


# ------------------------------------------------------------------ N7
def test_calibration_points_non_overlapping_and_regime_masked():
    t14 = calibration_points(100, 300, 5, design="v14")
    assert np.all(np.diff(t14) == 1)
    t17 = calibration_points(100, 300, 5)
    assert t17[-1] == 295 and np.all(np.diff(t17) == 5) and t17[0] >= 105
    rows = np.zeros(301, bool)
    rows[200:] = True
    assert np.all(calibration_points(100, 300, 5, rows) >= 200)
    with pytest.raises(ValueError):
        calibration_points(100, 300, 5, design="nope")


def _garch(n, seed):
    rng = np.random.default_rng(seed)
    r = np.empty(n)
    v = np.empty(n)
    var = 1e-4
    for i in range(n):
        v[i] = math.sqrt(var)
        r[i] = v[i] * rng.standard_t(6) / math.sqrt(1.5)
        var = 2e-6 + 0.10 * r[i] ** 2 + 0.88 * var
    return r, v


def test_normalised_conformal_covers_on_garch_paths():
    """Coverage on a dependent (GARCH(1,1), t-innovation) path. Calibration uses the bars
    before each forecast; the target is the next non-overlapping 5-bar return. v17 must sit
    near the nominal 80% overall and in the high-volatility quartile, where raw residuals
    (v14) under-cover because their calm-window quantile is too narrow."""
    h, alpha, win = 5, 0.2, 250
    cover = {"v14": [], "v17": []}
    hi = {"v14": [], "v17": []}
    for seed in range(6):
        r, sd = _garch(3000, seed)
        close = 100 * np.exp(np.cumsum(r))
        # trailing 20-bar realised vol, known at each bar (the desk's horizon_vol analogue)
        rv = np.full(close.size, np.nan)
        for i in range(20, close.size):
            rv[i] = r[i - 19 : i + 1].std(ddof=1) * math.sqrt(h)
        mus = np.zeros(close.size)
        q75 = np.nanquantile(rv, 0.75)
        for end in range(win + 40, close.size - h, 25):
            fwd = close[end + h] / close[end] - 1.0
            for d in ("v14", "v17"):
                cal = calibration_points(end - win, end, h, design=d)
                w = conformal_interval(close[: end + 1], mus[: end + 1], rv[: end + 1], cal, h, alpha, d)
                hit = w is not None and abs(fwd) <= w
                cover[d].append(hit)
                if rv[end] > q75:
                    hi[d].append(hit)
    c17, h17, h14 = np.mean(cover["v17"]), np.mean(hi["v17"]), np.mean(hi["v14"])
    assert 0.74 <= c17 <= 0.88, c17
    assert h17 >= 0.72 and h17 > h14, (h17, h14)


def test_conformal_halfwidth_unchanged():
    assert conformal_halfwidth(np.arange(10.0), 0.2) == 8.0


# ------------------------------------------------------------------ N11
def test_dev_keys_refused_on_loopback_without_flag():
    pytest.importorskip("fastapi")
    from agentic_trader.agentic.api import serve_options

    cfg = make_config()
    with pytest.raises(ValueError, match="development API keys"):
        serve_options("127.0.0.1", cfg)
    assert serve_options("127.0.0.1", cfg, allow_dev_keys=True) == {}
    assert serve_options("127.0.0.1", make_config(agentic={"api_keys": {"k9f2x7": "trader"}})) == {}


def test_secrets_never_written_to_the_temp_config(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")
    uvicorn = pytest.importorskip("uvicorn")
    from agentic_trader.agentic.api import CONFIG_ENV, REDACTED, SECRETS_ENV, app_factory, merge_secrets, serve, split_secrets

    cfg = make_config(
        agentic={"api_keys": {"real-secret-1": "trader"}, "task_db": str(tmp_path / "t.sqlite")}, fred_api_token="tok-123"
    )
    red, sec = split_secrets(cfg)
    assert red["agentic"]["api_keys"] == REDACTED and red["fred_api_token"] == REDACTED
    assert merge_secrets(json.loads(json.dumps(red)), sec)["agentic"]["api_keys"] == {"real-secret-1": "trader"}
    seen = {}

    def fake_run(app, **kw):
        import os

        path = os.environ[CONFIG_ENV]
        seen["file"] = open(path, encoding="utf-8").read()
        seen["app"] = app_factory()
        seen["secrets_env"] = os.environ[SECRETS_ENV]

    monkeypatch.setattr(uvicorn, "run", fake_run)
    serve("127.0.0.1", 9, cfg, processes=2)
    assert "real-secret-1" not in seen["file"] and "tok-123" not in seen["file"]
    assert REDACTED in seen["file"] and "real-secret-1" in seen["secrets_env"]
    assert seen["app"].state.harness is not None
