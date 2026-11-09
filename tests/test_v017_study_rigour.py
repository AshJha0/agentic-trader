"""v0.17 lane L10 (review 2026-11-09 N1, N3, N4, N5, N6, N9): fake HTTP and fake models only."""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import pandas as pd
import pytest

from agentic_trader import recall_audit as ra
from agentic_trader import study_design as sd
from agentic_trader import study_lineage as lin
from agentic_trader.config import make_config
from agentic_trader.evaluation import CORE_UNIVERSE, TRIALS
from agentic_trader.local_llm import LocalLLM, model_digest, server_version, truncation_flag

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import v16_local_study as v16  # noqa: E402

NAMES = CORE_UNIVERSE["equity"] + CORE_UNIVERSE["fx"]


# ---------------------------------------------------------------- fake Ollama (GET endpoints)
class FakeTags(BaseHTTPRequestHandler):
    digest = "sha256:aaa"

    def do_GET(self) -> None:
        if self.path == "/api/version":
            obj: dict[str, Any] = {"version": "0.12.3"}
        else:
            obj = {"models": [{"name": "qwen2.5:7b-instruct", "digest": type(self).digest, "size": 4,
                               "details": {"quantization_level": "Q4_K_M", "family": "qwen2"}}]}
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a: Any) -> None:
        pass


@pytest.fixture
def tags() -> Iterator[str]:
    FakeTags.digest = "sha256:aaa"
    httpd = HTTPServer(("127.0.0.1", 0), FakeTags)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


# ---------------------------------------------------------------- N4
def test_num_ctx_default_and_configurable() -> None:
    llm = LocalLLM(make_config(local_llm_model="m:7b"))
    assert llm.build_request("s", "p")["options"]["num_ctx"] == 8192
    assert llm.build_request("s", "p")["options"]["temperature"] == 0.0
    llm = LocalLLM(make_config(local_llm_model="m:7b", local_llm_num_ctx=4096))
    assert llm.build_request("s", "p")["options"]["num_ctx"] == 4096
    with pytest.raises(ValueError):
        LocalLLM(make_config(local_llm_model="m:7b", local_llm_num_ctx=-1))


def test_truncation_flag_and_stored_counts() -> None:
    assert truncation_flag(100, 100, "stop") is False
    assert truncation_flag(50, 100, "stop") is True              # far fewer tokens evaluated
    assert truncation_flag(8192, 5000, "stop", 8192) is True     # window full
    assert truncation_flag(None, 100, "length") is True
    assert truncation_flag(None, 100, "stop") is False
    llm = LocalLLM(make_config(local_llm_model="m:7b"))
    prompt = "x" * 40_000                                         # ~10,000 neutral tokens
    text = llm.read_response({"model": "m:7b", "message": {"content": "ok"}, "done_reason": "stop",
                              "prompt_eval_count": 2048, "eval_count": 7}, prompt_estimate=10_000)
    assert text == "ok"
    ev = llm.last_call
    assert ev["prompt_eval_count"] == 2048 and ev["eval_count"] == 7 and ev["truncated"] is True
    assert llm.usage.summary()["truncated"] == 1
    assert len(prompt) == 40_000


# ---------------------------------------------------------------- N5
def test_server_version_and_digest(tags: str) -> None:
    assert server_version(tags) == "0.12.3"
    e = model_digest(tags, "qwen2.5:7b-instruct")
    assert e["digest"] == "sha256:aaa" and e["quantization"] == "Q4_K_M"
    assert model_digest(tags, "llama3:8b") is None
    assert server_version("http://127.0.0.1:9") is None


def _hdr(url: str | None = None, sha: str = "abc", **kw: Any) -> dict[str, Any]:
    return lin.build_header(model="qwen2.5:7b-instruct" if url else None, url=url, options={"num_ctx": 8192},
                            prompt_hash=kw.pop("prompt_hash", "p1"), git=lambda: (sha, False), **kw)


def test_header_resume_refuses_mismatch_and_records_allowed_change(tmp_path: Path, tags: str) -> None:
    rows = tmp_path / "r.jsonl"
    h = _hdr(tags)
    assert h["model_digest"] == "sha256:aaa" and h["ollama_version"] == "0.12.3"
    assert h["header_id"] == _hdr(tags)["header_id"]                  # timestamp not in the id
    lin.check_resume(rows, h)
    rows.write_text('{"x": 1}\n', encoding="utf-8")
    assert lin.check_resume(rows, _hdr(tags))["header_id"] == h["header_id"]
    with pytest.raises(lin.LineageMismatch) as e:
        lin.check_resume(rows, _hdr(tags, sha="def"))
    assert e.value.fields == ["git_sha"]
    with pytest.raises(lin.LineageMismatch):
        lin.check_resume(rows, _hdr(tags, prompt_hash="p2"))
    FakeTags.digest = "sha256:bbb"                                    # re-pulled tag, new weights
    with pytest.raises(lin.LineageMismatch) as e:
        lin.check_resume(rows, _hdr(tags))
    assert e.value.fields == ["model_digest"]
    rec = lin.check_resume(rows, _hdr(tags), allow_version_change=True)
    assert rec["allowed_change"] and rec["changed_fields"] == ["model_digest"]
    assert len(lin.read_headers(rows)) == 2


def test_rows_without_header_are_refused(tmp_path: Path) -> None:
    rows = tmp_path / "old.jsonl"
    rows.write_text('{"x": 1}\n', encoding="utf-8")
    with pytest.raises(lin.LineageMismatch):
        lin.check_resume(rows, _hdr())
    assert lin.check_resume(rows, _hdr(), allow_version_change=True)["legacy_rows"] is True


def test_swapped_digest_and_stamp(tags: str) -> None:
    h = _hdr(tags)
    assert lin.swapped_digest(h, tags) is None
    FakeTags.digest = "sha256:ccc"
    assert lin.swapped_digest(h, tags) == "sha256:ccc"
    row = lin.stamp({"id": 1}, h)
    assert row["header_id"] == h["header_id"] and row["model_digest"] == "sha256:aaa" and row["git_sha"] == "abc"
    assert lin.prompt_sha256("a", "b") != lin.prompt_sha256("ab", "")


# ---------------------------------------------------------------- N6
def test_vintage_hash_and_market_lineage() -> None:
    idx = pd.bdate_range("2020-01-01", periods=5)
    a = pd.DataFrame({"Close": [1.0, 2, 3, 4, 5]}, index=idx)
    b = a.copy()
    b.iloc[0, 0] = 0.99                                    # a later dividend re-adjustment
    assert lin.vintage_hash(a["Close"]) != lin.vintage_hash(b["Close"])

    class P:
        horizon_days = 10
    m = lin.market_lineage(a, P())
    assert m["horizon_days"] == 10 and m["asof_close"] == 5.0 and m["entry_bar_date"] == "2020-01-07"
    assert lin.row_vintage_status(m) == "current" and lin.row_vintage_status({"close": 1}) == "legacy"
    assert "single" in lin.LEGACY_ROW_POLICY


# ---------------------------------------------------------------- N1 recall audit
DATES = [d.isoformat() for d in v16.design_dates(14)]


def _always_first(items: list[ra.AuditItem]) -> list[dict[str, Any]]:
    return [{"ranked": list(i.candidates[:3]), "month": "2019-10"} for i in items]


def test_items_interleaved_and_candidates_shuffled() -> None:
    items = ra.build_items(NAMES, DATES, seed=7)
    assert len(items) == 210 and len({i.truth for i in items[:30]}) >= 10
    assert len({i.candidates for i in items}) > 150
    assert ra.build_items(NAMES, DATES, seed=7) == items                # recorded seed reproduces
    assert all(sorted(i.candidates) == sorted(NAMES) for i in items)


def test_always_first_responder_is_not_flagged() -> None:
    real = ra.build_items(NAMES, DATES, seed=7)
    plc = ra.build_items(NAMES, DATES, seed=7, arm="placebo", limit=60)
    res = ra.summarise(real, _always_first(real), plc, _always_first(plc), n_perm=500)
    assert not res.flagged
    assert res.real["p_perm"] > 0.05
    assert res.position_bias["first_share"] == 1.0 and res.position_bias["p"] < 1e-6   # bias reported
    # every prefix too: stopping early cannot flag it
    for n in (30, 60, 100):
        r = ra.summarise(real[:n], _always_first(real[:n]), plc, _always_first(plc), n_perm=300)
        assert not r.flagged


def test_old_v16_design_flags_always_first_on_a_prefix() -> None:
    """Regression for the bug: name-major items + fixed AAPL-first candidates make an
    always-first model look like recall on a 30-item prefix (14/30 hits vs p0 1/15)."""
    items = v16.recall_items()[:30]
    hits = sum(1 for sym, _ in items if sym == v16.NAMES[0])
    assert v16.rate_row(hits, 30, 1 / 15)["above_chance"]


def test_constant_responder_is_not_flagged() -> None:
    real = ra.build_items(NAMES, DATES, seed=3)
    ans = [{"ranked": ["AAPL", "MSFT", "SPY"], "month": "2019-10"} for _ in real]
    res = ra.summarise(real, ans, real[:40], ans[:40], n_perm=500)
    assert not res.flagged and res.concentration["modal_share"] == 1.0


def test_recognising_model_is_flagged_and_placebo_is_not() -> None:
    real = ra.build_items(NAMES, DATES, seed=5)
    plc = ra.build_items(NAMES, DATES, seed=5, arm="placebo", limit=60)
    knows = [{"ranked": [i.truth, *[c for c in i.candidates if c != i.truth][:2]], "month": i.as_of[:7]}
             for i in real]
    res = ra.summarise(real, knows, plc, _always_first(plc), n_perm=500)
    assert res.flagged and res.real["mrr"] == 1.0 and res.month["p_perm"] < 0.01
    no_placebo = ra.summarise(real, knows, n_perm=200)
    assert not no_placebo.flagged and "incomplete" in " ".join(no_placebo.reasons)
    # same skill on placebo as on real: not recall
    pk = [{"ranked": [i.truth], "month": None} for i in plc]
    assert not ra.summarise(real[:60], knows[:60], plc, pk, n_perm=300).flagged


def test_parse_ranked() -> None:
    c = tuple(NAMES)
    assert ra.parse_ranked("RANK1: **eur/usd**\nRANK2: AAPL\nRANK3: AAPL\nMONTH: 2019-3", c) == \
        {"ranked": ["EURUSD", "AAPL"], "month": "2019-03"}
    assert ra.parse_ranked("RANK2: AAPL", c) is None and ra.parse_ranked("RANK1: TSLA", c) is None
    assert ra.reciprocal_rank(["A", "B", "C"], "C") == pytest.approx(1 / 3)
    assert ra.chance_mrr(15) == pytest.approx((1 + 0.5 + 1 / 3) / 15)
    assert ra.chi2_sf(3.841459, 1) == pytest.approx(0.05, abs=1e-5)
    assert ra.chi2_sf(23.68479, 14) == pytest.approx(0.05, abs=1e-4)


def test_leak_test_real_vs_shifted() -> None:
    rng = np.random.default_rng(0)
    rows = []
    for d in range(40):
        for n in range(10):
            f = float(rng.normal())
            rows.append({"as_of": str(d), "signal": f + 0.3 * float(rng.normal()), "fwd_real": f,
                         "fwd_shift": float(rng.normal())})
    r = ra.leak_test(rows, n_boot=300)
    assert r["ic_real"] > 0.8 and abs(r["ic_shift"]) < 0.2 and r["ci95"][0] > 0
    for x in rows:
        x["signal"] = float(rng.normal())
    assert ra.leak_test(rows, n_boot=300)["ci95"][0] < 0


def test_placebo_series_matches_drift_and_vol() -> None:
    idx = pd.bdate_range("2015-01-01", periods=800)
    r = np.random.default_rng(1).normal(0.0005, 0.015, 800)
    c = 100 * np.exp(np.cumsum(r))
    h = pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c, "Volume": 1.0}, index=idx)
    p = ra.placebo_ohlc(h, 3)
    pr = np.diff(np.log(p["Close"].to_numpy()))
    assert list(p.columns) == list(h.columns) and (p.index == h.index).all()
    assert pr.std() == pytest.approx(r[1:].std(), rel=0.1)
    assert (p["High"] >= p["Close"]).all() and (p["Low"] <= p["Close"]).all()
    assert not np.allclose(p["Close"].to_numpy(), c)


class FakeFirst:
    """Picks the first listed candidate; analyst replies a fixed signal. No network."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, system: str, prompt: str, *, deep: bool) -> str:
        self.prompts.append(prompt)
        opts = re.findall(r"^\s+\d+\. (\S+)$", prompt, re.M)
        return f"RANK1: {opts[0]}\nRANK2: {opts[1]}\nRANK3: {opts[2]}\nMONTH: 2019-10"

    def complete_json(self, system: str, prompt: str, *, deep: bool, schema: dict[str, Any]) -> str:
        return json.dumps({"signal": 0.1, "confidence": 0.5, "summary": "x", "key_points": []})


@pytest.fixture(scope="module")
def graph() -> Any:
    return v16.make_graph("synthetic")


def test_run_recall2_end_to_end_with_resume(graph: Any, tmp_path: Path) -> None:
    out = tmp_path / "recall2.json"
    h = _hdr()
    llm = FakeFirst()
    res = v16.run_recall2(llm, graph, out, header=h, limit=6, placebo_n=3, log=lambda m: None)
    assert len(res["rows"]) == 9 and not res["recall_flagged"]
    assert {r["kind"] for r in res["rows"]} == {"real", "placebo"}
    assert all(r["header_id"] == h["header_id"] and r["prompt_sha256"] for r in res["rows"])
    assert len(res["leak_rows"]) == 6 and all(r["fwd_real"] is not None for r in res["leak_rows"])
    assert len({tuple(r["candidates"]) for r in res["rows"]}) > 1
    n = len(llm.prompts)
    llm2 = FakeFirst()
    v16.run_recall2(llm2, graph, out, header=h, limit=6, placebo_n=3, log=lambda m: None)
    assert llm2.prompts == [] and n == 9


def test_recall2_cli_refuses_changed_header(graph: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"sha": "one"}
    monkeypatch.setattr(v16, "_header", lambda a, llm, g, extra: _hdr(sha=calls["sha"]))
    args = ["recall2", "--out", str(tmp_path / "r.json"), "--data", "synthetic", "--smoke"]
    assert v16.main(args, llm_factory=lambda a: FakeFirst()) == 0
    calls["sha"] = "two"
    assert v16.main(args, llm_factory=lambda a: FakeFirst()) == 2
    assert v16.main([*args, "--allow-version-change"], llm_factory=lambda a: FakeFirst()) == 0


# ---------------------------------------------------------------- N3 / N9
def test_design_cells_registered_and_dry_run() -> None:
    names = {t.name for t in TRIALS}
    assert all(c.trial_name in names for c in sd.DESIGN_CELLS)
    dec = sd.dry_run(sd.DECISIVE, NAMES)
    assert 300 <= dec["dates"] <= 320 and 4500 <= dec["decisions"] <= 4800
    assert dec["calls"] == dec["decisions"] and dec["horizon_days"] == 5
    assert 60 < dec["cpu_hours"][0] < dec["cpu_hours"][1] < 140
    assert dec["mde"]["mde"] == pytest.approx(0.093, abs=0.005)
    post = sd.dry_run(sd.POSTCUTOFF, NAMES)
    assert post["first_date"] >= "2025-07-01" and post["last_date"] <= "2026-10-30"
    fp = sd.first_pass_mde()
    assert fp["sharpe_mde_corr0.7_6y"] == pytest.approx(0.89, abs=0.02) and fp["ic_mde_neff60"] > 0.3


def _ic_rows(effect: float, dates: int = 60, names: int = 15, seed: int = 0) -> list[dict[str, Any]]:
    rng = np.random.default_rng(seed)
    rows = []
    for d in range(dates):
        for n in range(names):
            rule = float(rng.normal())
            f = float(rng.normal())
            rows.append({"as_of": f"d{d:03d}", "signal_rule": rule, "signal_model": rule + effect * f
                         + float(rng.normal()), "fwd_ret": f})
    return rows


def test_incremental_ic_and_futility() -> None:
    strong = sd.incremental_ic(_ic_rows(1.0))
    assert strong["incremental"]["ic"] > 0.4 and strong["incremental"]["ci95"][0] > 0
    null = sd.incremental_ic(_ic_rows(0.0))
    assert abs(null["incremental"]["ic"]) < 0.06
    rows = _ic_rows(0.0) + [{"as_of": "x", "signal_rule": 0.1, "signal_model": None, "fwd_ret": 0.0}]
    assert sd.incremental_ic(rows)["excluded_rows"] == 1
    neg = _ic_rows(-0.5)
    assert sd.futility_stop(neg)["stop"] is True
    assert sd.futility_stop(_ic_rows(1.0))["stop"] is False
    assert sd.futility_stop(_ic_rows(-0.5, dates=10))["stop"] is False     # too few dates
    assert sd.newey_west_se([1.0, -1.0] * 50, lag=1) < sd.newey_west_se([1.0, 1.0, -1.0, -1.0] * 25, lag=1)


def test_run_design_cell_with_fake_model(graph: Any, tmp_path: Path) -> None:
    out = tmp_path / "dec.jsonl"
    h = _hdr()
    rows = sd.run_cell(sd.DECISIVE, ["AAPL", "EURUSD"], graph, FakeFirst(), out, header=h, limit=4,
                       echo=lambda m: None)
    assert len(rows) == 4
    r = rows[0]
    assert r["signal_model"] == pytest.approx(0.1) and r["signal_rule"] is not None and r["horizon_days"] == 5
    assert r["vintage_hash"] and r["header_id"] == h["header_id"] and r["prompt_sha256"]
    assert r["fwd_ret"] is not None
    assert len(sd.run_cell(sd.DECISIVE, ["AAPL", "EURUSD"], graph, None, out, header=h, limit=4,
                           echo=lambda m: None)) == 4                       # resumed, nothing new
    rep = sd.report(sd.DECISIVE, rows, ["AAPL", "EURUSD"])
    assert rep["fallback_share"] == 0 and rep["headers"] == [h["header_id"]]


def test_prereg_draft_states_descriptive_first_pass() -> None:
    text = (ROOT / "docs/evaluation/v16_preregistration_DRAFT.md").read_text(encoding="utf-8")
    assert "DRAFT" in text and "descriptive" in text and "decisive_ta" in text and "postcutoff_ta" in text


# ---------------------------------------------------------------- llm_study call sites
def _study() -> Any:
    spec = importlib.util.spec_from_file_location("llm_study_l10", ROOT / "scripts" / "llm_study.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["llm_study_l10"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_llm_study_rows_carry_lineage_and_refuse_mismatch(tmp_path: Path) -> None:
    study = _study()
    out = tmp_path / "p2.jsonl"
    cell = next(c for c in study.CELLS if c.name == "rules")
    dates = study.design_dates(20)[1:2]
    rows = study.run_study(["AAPL"], dates, 1, [cell], make_config(study.STUDY_BASE), out, None,
                           lambda s: None, header=_hdr())
    assert rows[0]["header_id"] and rows[0]["vintage_hash"] and "asof_close" in rows[0]
    with pytest.raises(lin.LineageMismatch):
        study.run_study(["AAPL"], dates, 1, [cell], make_config(study.STUDY_BASE), out, None,
                        lambda s: None, header=_hdr(sha="other"))
    ev = {"prompt_eval_count": 5, "eval_count": 2, "truncated": False}
    assert lin.call_lineage("s", "p", ev)["prompt_eval_count"] == 5


def test_llm_study_stops_on_a_mid_run_model_swap(tmp_path: Path) -> None:
    """L10: run_study re-checks the served digest every N written rows and stops on a swap."""
    study = _study()
    out = tmp_path / "swap.jsonl"
    cell = next(c for c in study.CELLS if c.name == "rules")
    dates = study.design_dates(20)[1:6]
    hdr = dict(_hdr(), model="m:7b", model_digest="sha256:aaa")
    served = iter(["sha256:aaa", "sha256:aaa", "sha256:bbb"])
    looks: list[str] = []

    def digest_fn(url: str, model: str) -> dict[str, Any]:
        looks.append(model)
        return {"digest": next(served)}
    cfg = make_config(study.STUDY_BASE, local_llm_url="http://127.0.0.1:11434")
    with pytest.raises(study.ModelSwapped, match="sha256:bbb"):
        study.run_study(["AAPL"], dates, 1, [cell], cfg, out, None, lambda s: None, header=hdr,
                        swap_check_every=2, digest_fn=digest_fn)
    assert looks == ["m:7b"] * 3                               # before rows 1, 3 and 5
    assert len(study.load_rows(out)) == 4                      # rows before the swap are kept
    seen: list[str] = []

    def never(url: str, model: str) -> dict[str, Any]:
        seen.append(model)
        return {"digest": "x"}
    study.run_study(["AAPL"], dates, 1, [cell], cfg, out, None, lambda s: None, header=hdr,
                    swap_check_every=0, digest_fn=never)
    assert seen == [] and len(study.load_rows(out)) == 5      # 0 disables the check
