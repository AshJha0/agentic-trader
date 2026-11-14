"""v0.19 lane B: local-model retry, provider-miss skips, k/N progress. Fakes only (no Ollama,
no network)."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import socket
import sys
import urllib.error
from pathlib import Path
from typing import Any

import pytest

from agentic_trader import study_lineage as lin
from agentic_trader.config import make_config
from agentic_trader.local_llm import LocalLLM, LocalLLMUnavailable, backoff_delays, is_transient
from agentic_trader.study_robust import ProviderMiss, retry_provider

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import v16_local_study as v16  # noqa: E402
from test_v017_study_rigour import FakeFirst, _hdr  # noqa: E402

OK = {"model": "m", "message": {"content": "hi"}, "done_reason": "stop"}


def _llm(budget: float = 30.0) -> tuple[LocalLLM, list[float], list[str]]:
    m = LocalLLM({"local_llm_model": "m", "local_llm_seed": 7, "local_llm_retry_budget_s": budget, "local_llm_retry_base_s": 1.0})
    sleeps: list[float] = []
    m._sleep = sleeps.append
    bodies: list[str] = []
    return m, sleeps, bodies


def _poster(bodies: list[str], fails: list[BaseException]) -> Any:
    def post(body: dict[str, Any]) -> dict[str, Any]:
        bodies.append(hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest())
        if fails:
            raise fails.pop(0)
        return OK

    return post


def test_backoff_is_bounded_and_doubles() -> None:
    d = backoff_delays(600, 2, 60)
    assert d[:5] == [2, 4, 8, 16, 32] and max(d) == 60 and abs(sum(d) - 600) < 1e-9
    assert backoff_delays(0) == []


def test_transient_classification() -> None:
    assert is_transient(TimeoutError()) and is_transient(socket.timeout())
    assert is_transient(urllib.error.URLError(ConnectionRefusedError()))
    assert is_transient(ConnectionResetError())
    assert is_transient(urllib.error.HTTPError("u", 503, "busy", {}, io.BytesIO()))  # type: ignore[arg-type]
    assert not is_transient(urllib.error.HTTPError("u", 404, "no model", {}, io.BytesIO()))  # type: ignore[arg-type]
    assert not is_transient(ValueError("bad json"))


def test_retry_then_success_same_body(monkeypatch: pytest.MonkeyPatch) -> None:
    m, sleeps, bodies = _llm()
    fails: list[BaseException] = [urllib.error.URLError(ConnectionRefusedError()), TimeoutError("hang")]
    monkeypatch.setattr(m, "_post", _poster(bodies, fails))
    assert m.complete("s", "p", deep=False) == "hi"
    assert sleeps == [1.0, 2.0] and len(bodies) == 3 and len(set(bodies)) == 1  # digest unchanged
    assert m.usage.retries == 2 and m.usage.errors == 0
    assert m.usage.summary()["retries"] == 2


def test_retry_exhausted_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    m, sleeps, bodies = _llm(budget=7.0)  # delays 1, 2, 4 -> 4 attempts
    monkeypatch.setattr(m, "_post", _poster(bodies, [TimeoutError("hang")] * 10))
    with pytest.raises(LocalLLMUnavailable):
        m.complete("s", "p", deep=False)
    assert sleeps == [1.0, 2.0, 4.0] and len(bodies) == 4 and len(set(bodies)) == 1
    assert m.usage.errors == 1


@pytest.mark.parametrize(
    "exc",
    [
        urllib.error.HTTPError("u", 400, "bad", {}, io.BytesIO()),  # type: ignore[arg-type]
        ValueError("reply body is not a JSON object"),
    ],
)
def test_4xx_and_parse_error_not_retried(monkeypatch: pytest.MonkeyPatch, exc: BaseException) -> None:
    m, sleeps, bodies = _llm()
    monkeypatch.setattr(m, "_post", _poster(bodies, [exc]))
    assert m.complete("s", "p", deep=False) is None
    assert sleeps == [] and len(bodies) == 1 and m.usage.errors == 1


def test_default_budget_zero_keeps_old_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    m = LocalLLM({"local_llm_model": "m"})
    bodies: list[str] = []
    monkeypatch.setattr(m, "_post", _poster(bodies, [TimeoutError("x")]))
    assert m.complete("s", "p", deep=False) is None and len(bodies) == 1 and m.usage.timeouts == 1


def test_retry_provider() -> None:
    n = {"k": 0}

    def flaky() -> int:
        n["k"] += 1
        if n["k"] < 3:
            raise ValueError("no Yahoo data")
        return 5

    assert retry_provider(flaky, tries=3, sleep=lambda s: None) == 5
    with pytest.raises(ProviderMiss) as e:
        retry_provider(lambda: (_ for _ in ()).throw(ValueError("no Yahoo data for GOOGL")), tries=2, sleep=lambda s: None)
    assert e.value.tries == 2 and "GOOGL" in e.value.reason


@pytest.fixture(scope="module")
def graph() -> Any:
    return v16.make_graph("synthetic")


def test_recall2_skips_provider_miss_and_counts_progress(graph: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_init = v16.FrozenState.__init__
    bad: dict[str, Any] = {}

    def init(self: Any, g: Any, symbol: str, as_of: Any, placebo_seed: int | None = None) -> None:
        if not bad:
            bad["key"] = (symbol, as_of)
        if (symbol, as_of) == bad["key"] and placebo_seed is None:
            raise ValueError(f"no Yahoo data for {symbol} between x and y")
        real_init(self, g, symbol, as_of, placebo_seed)

    monkeypatch.setattr(v16.FrozenState, "__init__", init)
    lines: list[str] = []
    out = tmp_path / "r2.json"
    res = v16.run_recall2(
        FakeFirst(), graph, out, header=_hdr(), limit=6, placebo_n=3, log=lines.append, provider_tries=2, sleep=lambda s: None
    )
    sk = res["skipped"]
    assert sk["units"] == 15 and sk["n"] == 2 and sk["by_kind"] == {"real": 1, "placebo": 0, "leak": 1}
    assert all("no Yahoo data" in r["reason"] for r in sk["rows"])
    assert len(res["rows"]) == 8 and len(res["leak_rows"]) == 5
    prog = [ln.split()[1] for ln in lines if ln.startswith(("recall2 ", "leak "))]
    assert prog[0] == "1/15" and prog[-1] == "15/15" and len(prog) == 15
    # resume retries the skipped units; with the provider back they complete
    monkeypatch.setattr(v16.FrozenState, "__init__", real_init)
    res2 = v16.run_recall2(FakeFirst(), graph, out, header=_hdr(), limit=6, placebo_n=3, log=lambda m: None)
    assert res2["skipped"]["n"] == 0 and len(res2["rows"]) == 9


def _study() -> Any:
    spec = importlib.util.spec_from_file_location("llm_study_v019", ROOT / "scripts" / "llm_study.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["llm_study_v019"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_llm_study_skip_row_recorded_and_counted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    study = _study()
    out = tmp_path / "p2.jsonl"
    cell = next(c for c in study.CELLS if c.name == "rules")
    dates = study.design_dates(20)[1:3]
    real = study.StudyGraph.propagate

    def prop(self: Any, name: str, d: Any) -> Any:
        if d == dates[0]:
            raise ValueError(f"no Yahoo data for {name} between a and b")
        return real(self, name, d)

    monkeypatch.setattr(study.StudyGraph, "propagate", prop)
    echoed: list[str] = []
    rows = study.run_study(
        ["AAPL"],
        dates,
        1,
        [cell],
        make_config(study.STUDY_BASE),
        out,
        None,
        echoed.append,
        header=_hdr(),
        provider_tries=2,
        sleep=lambda s: None,
    )
    assert len(rows) == 1 and rows[0]["as_of"] == dates[1].isoformat()
    skips = study.load_skips(out)
    assert len(skips) == 1 and "no Yahoo data" in skips[0]["skip_reason"] and skips[0]["header_id"]
    assert echoed[0].startswith("[1/2]") and "SKIPPED" in echoed[0] and echoed[1].startswith("[2/2]")
    monkeypatch.setattr(study.StudyGraph, "propagate", real)
    rows = study.run_study(["AAPL"], dates, 1, [cell], make_config(study.STUDY_BASE), out, None, lambda s: None, header=_hdr())
    assert len(rows) == 2 and study.load_skips(out) == []
    assert lin.stamp({}, _hdr())["header_id"]
