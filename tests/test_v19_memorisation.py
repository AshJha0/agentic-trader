"""Round 4 part B (memorisation pair): grid, prompts per arm, gate, scoring arithmetic and the
CLI wiring. Offline: synthetic prices and a fake model."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from agentic_trader import memorisation as mm
from agentic_trader import study_lineage as lin

ROOT = Path(__file__).resolve().parents[1]


def _script(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_grid_matches_registration() -> None:
    names = [f"N{i}" for i in range(15)]
    g = mm.grid(names)
    assert len(g) == 2700  # 15 x (20 + 70) x 2, the signed number
    assert g[0][3] == "anon" and g[1][3] == "named" and g[0][:3] == g[1][:3]  # arms adjacent
    dr = mm.dry_run(names)
    assert dr["per_cell"] == {"pre_anon": 300, "pre_named": 300, "post_anon": 1050, "post_named": 1050}
    assert dr["blocks"] == {"pre": 1, "post": 4}
    assert dr["post_dates"][:2] == ["2025-07-01", "2026-10-27"]


def test_first_pass_dates_match_llm_study() -> None:
    study = _script("llm_study")
    assert mm.first_pass_dates() == study.design_dates(study.FIRST_PASS["dates"])


def test_registration_gate(tmp_path: Path) -> None:
    assert mm.registration_gate(ROOT)["registration_path"] == mm.REGISTRATION
    with pytest.raises(mm.RegistrationNotSigned, match="does not exist"):
        mm.registration_gate(tmp_path)
    p = tmp_path / mm.REGISTRATION
    p.parent.mkdir(parents=True)
    p.write_text("# Round 4 registration (DRAFT, unsigned)\n", encoding="utf-8")
    with pytest.raises(mm.RegistrationNotSigned, match="not marked signed"):
        mm.registration_gate(tmp_path)


class FakeModel:
    """Analyst replies +0.5 when it can see a real ticker in the prompt, -0.5 otherwise."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete_json(self, system: str, prompt: str, *, deep: bool, schema: Any) -> str:
        self.prompts.append(prompt)
        sig = 0.5 if ("AAPL" in prompt or "EURUSD" in prompt) else -0.5
        return json.dumps({"signal": sig, "confidence": 0.6, "summary": "fake.", "key_points": ["fake"]})

    def complete(self, system: str, prompt: str, *, deep: bool) -> str:
        return self.complete_json(system, prompt, deep=deep, schema=None)


def _hdr() -> dict[str, Any]:
    return lin.build_header(
        model=None, url=None, options={}, prompt_hash="p", git=lambda: ("abc", False), extra={"data": "synthetic"}
    )


def test_run_both_arms_and_resume(tmp_path: Path) -> None:
    v16 = _script("v16_local_study")
    graph = v16.make_graph("synthetic")
    llm = FakeModel()
    out = tmp_path / "memo.jsonl"
    rows = mm.run(["AAPL"], graph, llm, out, header=_hdr(), limit=6, echo=lambda m: None)
    assert [r["arm"] for r in rows] == ["anon", "named"] * 3
    by_arm = {r["arm"]: r for r in rows if not r.get("error")}
    assert by_arm["named"]["signal_model"] == pytest.approx(0.5)  # saw the real ticker
    assert by_arm["anon"]["signal_model"] == pytest.approx(-0.5)  # did not
    assert all(r["data_provider"] == "synthetic" and r["window"] == "pre" for r in rows)
    assert not any("AAPL" in p for p in llm.prompts[::2])  # anonymised prompts carry no ticker
    again = mm.run(["AAPL"], graph, None, out, header=_hdr(), limit=6, echo=lambda m: None)
    assert len(again) == 6  # resumed: nothing new


def test_run_records_errors(tmp_path: Path) -> None:
    class Boom:
        config: dict[str, Any] = {}

        def prepare(self, *a: Any) -> Any:
            raise KeyError("no bar")

    rows = mm.run(["AAPL"], Boom(), None, tmp_path / "e.jsonl", header=_hdr(), limit=2, echo=lambda m: None)
    assert all("KeyError" in r["error"] and r["signal_model"] is None for r in rows)


def _rows(gap_pre: float, gap_post: float, seed: int = 0) -> list[dict[str, Any]]:
    """Synthetic rows: the named arm tracks the return with strength ``gap``; anon is noise."""
    rng = np.random.default_rng(seed)
    out = []
    for window, dates, gap in (("pre", mm.first_pass_dates(), gap_pre), ("post", mm.weekly_dates(mm.POSTCUTOFF), gap_post)):
        for d in dates:
            fwd = rng.normal(size=10)
            for arm in mm.ARMS:
                strength = gap if arm == "named" else 0.0
                sig = strength * fwd + rng.normal(size=10)
                for i in range(10):
                    out.append(
                        {
                            "window": window,
                            "arm": arm,
                            "symbol": f"S{i}",
                            "asset_class": "equity",
                            "as_of": d.isoformat(),
                            "signal_model": float(sig[i]),
                            "signal_rule": 0.0,
                            "fwd_ret": float(fwd[i]),
                        }
                    )
    return out


def test_score_detects_memorisation_and_null() -> None:
    hit = mm.score(_rows(3.0, 0.0), n_boot=400)
    assert hit["admissible"] and hit["ci95"][0] > 0 and hit["verdict"].startswith("memorisation")
    assert hit["gaps"]["pre"]["block"] == 1 and hit["gaps"]["post"]["block"] == 4
    null = mm.score(_rows(0.0, 0.0, seed=1), n_boot=400)
    assert null["verdict"].startswith("no evidence") and null["ci95"][0] <= 0 <= null["ci95"][1]


def test_score_inadmissible_and_unscorable() -> None:
    rows = _rows(3.0, 0.0)
    for r in rows:
        if r["window"] == "post" and r["arm"] == "anon" and r["symbol"] in ("S0", "S1"):
            r["signal_model"] = None  # 20 % fallback
    rep = mm.score(rows, n_boot=100)
    assert not rep["admissible"] and rep["verdict"].startswith("inadmissible")
    assert mm.score([], n_boot=10)["verdict"] == "not scorable"


def test_block_length_edges() -> None:
    assert mm.block_length(["2025-07-01"]) == 1
    assert mm.block_length(["2025-07-01", "2025-07-08", "2025-07-15"]) == 4


def test_cli_dry_run_score_and_gate(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    v16 = _script("v16_local_study")
    assert v16.main(["memo", "--out", str(tmp_path / "m.jsonl"), "--dry-run"]) == 0
    assert '"decisions": 2700' in capsys.readouterr().out
    out = tmp_path / "s.jsonl"
    out.write_text("".join(json.dumps(r) + "\n" for r in _rows(3.0, 0.0)), encoding="utf-8")
    assert v16.main(["memo", "--out", str(out), "--score"]) == 0
    assert json.loads(out.with_suffix(".report.json").read_text())["verdict"].startswith("memorisation")
    capsys.readouterr()
    fake = lambda a: FakeModel()  # noqa: E731
    assert v16.main(["memo", "--out", str(tmp_path / "x.jsonl"), "--data", "synthetic", "--limit", "4"], llm_factory=fake) == 2
    assert "refusing memo --limit" in capsys.readouterr().err
    monkeypatch.setattr(v16, "ROOT", tmp_path)
    assert v16.main(["memo", "--out", str(tmp_path / "y.jsonl"), "--data", "synthetic"], llm_factory=fake) == 2
    assert "refusing memo" in capsys.readouterr().err
    assert v16.main(["memo", "--out", str(tmp_path / "z.jsonl"), "--data", "synthetic", "--smoke"], llm_factory=fake) == 0
    assert "smoke ok: 3 decisions" in capsys.readouterr().out


def test_signals_are_paired_by_date() -> None:
    rows = _rows(3.0, 0.0)
    ics = mm.per_date_ic([r for r in rows if r["window"] == "pre" and r["arm"] == "named"])
    assert set(ics) <= {d.isoformat() for d in mm.first_pass_dates()}
    assert date.fromisoformat(min(ics)) >= mm.DESIGN_START
