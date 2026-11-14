"""v0.17 R0.1 (seed pseudo-replication, review A1) and R0.3 (per-decision horizon scoring,
review B4) in scripts/llm_study.py. Fixture rows only; no model, no network."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from agentic_trader.config import make_config
from agentic_trader.local_llm import LocalLLM


def _study() -> Any:
    path = Path(__file__).resolve().parents[1] / "scripts" / "llm_study.py"
    spec = importlib.util.spec_from_file_location("llm_study_r0", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["llm_study_r0"] = mod
    spec.loader.exec_module(mod)
    return mod


study = _study()
NAMES = ["A", "B", "C", "D", "E"]


def _rows(
    n_dates: int = 12,
    seeds: tuple[int, ...] = (0,),
    cell: str = "local_all",
    weight=lambda i, j, s: 0.1 * ((i * 7 + j * 3) % 5 - 2),
    price=None,
) -> list[dict[str, Any]]:
    price = price or (lambda name, k: 100.0 * (1 + 0.01 * ((k * (NAMES.index(name) + 2)) % 9 - 4)))
    dates = study.design_dates(n_dates)
    rows = []
    for s in seeds:
        for i, d in enumerate(dates):
            for j, n in enumerate(NAMES):
                rows.append(
                    {
                        "cell": cell,
                        "seed": s,
                        "symbol": n,
                        "as_of": d.isoformat(),
                        "target_weight": weight(i, j, s),
                        "vt_weight": 0.5,
                        "close": price(n, i),
                        "regime": 0,
                        "source": "llm",
                        "sources": {},
                        "calls": [],
                    }
                )
    return rows


# ---- R0.1 -----------------------------------------------------------------------------------


def test_identical_seed_replays_do_not_narrow_the_interval() -> None:
    """Regression for A1: the old code concatenated seeds into one series, so two identical
    replays gave a narrower CI than one seed. Now the CI is the one-seed CI exactly."""
    cfg = make_config(study.STUDY_BASE)
    one = study.cell_metrics(_rows(seeds=(0,)), cfg)[0]
    two = study.cell_metrics(_rows(seeds=(0, 1)), cfg)[0]
    assert two["periods"] == one["periods"]
    assert (two["sharpe_minus_control"], two["ci_lo"], two["ci_hi"], two["p"]) == pytest.approx(
        (one["sharpe_minus_control"], one["ci_lo"], one["ci_hi"], one["p"])
    )
    assert two["seed_replays"] and not one["seed_replays"]
    assert [p["seed"] for p in two["per_seed"]] == [0, 1]


def test_distinct_seeds_are_reported_separately_and_averaged() -> None:
    cfg = make_config(study.STUDY_BASE)
    rows = _rows(seeds=(0, 1), weight=lambda i, j, s: 0.1 * ((i * 7 + j * 3 + 2 * s) % 5 - 2))
    m = study.cell_metrics(rows, cfg)[0]
    assert not m["seed_replays"]
    assert m["sharpe_minus_control"] == pytest.approx(np.mean([p["sharpe_minus_control"] for p in m["per_seed"]]))


def test_seeds_above_one_refused_at_temperature_zero(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="identical replays"):
        study.run_study(["AAPL"], study.design_dates(20)[1:2], 2, [], make_config(study.STUDY_BASE), tmp_path / "x.jsonl")
    study.check_seeds(2, 0.7)
    study.check_seeds(1, 0.0)
    with pytest.raises(SystemExit):
        study.main(["--dry-run", "--seeds", "2"])


def test_local_llm_sends_configured_temperature() -> None:
    base = make_config(llm_provider="local", local_llm_model="m")
    assert LocalLLM(base).build_request("s", "p")["options"]["temperature"] == 0.0
    hot = make_config(llm_provider="local", local_llm_model="m", local_llm_temperature=0.7)
    assert LocalLLM(hot).build_request("s", "p")["options"]["temperature"] == 0.7
    with pytest.raises(ValueError):
        LocalLLM(make_config(llm_provider="local", local_llm_model="m", local_llm_temperature=-1))


# ---- R0.3 -----------------------------------------------------------------------------------


def _prices_from(paths: dict[str, pd.Series]):
    def fn(symbol: str, start: date, end: date) -> pd.Series:
        s = paths[symbol]
        return s[(s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))]

    return fn


def _paths(seed: int = 3) -> dict[str, pd.Series]:
    idx = pd.bdate_range("2015-06-01", "2022-06-30")
    rng = np.random.default_rng(seed)
    return {n: pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(idx)))), index=idx) for n in NAMES}


def _rows_on(paths: dict[str, pd.Series], cell: str, weight) -> list[dict[str, Any]]:
    rows = []
    for i, d in enumerate(study.design_dates(15)):
        ts = paths[NAMES[0]].index[paths[NAMES[0]].index.get_indexer([pd.Timestamp(d)], method="bfill")[0]]
        for j, n in enumerate(NAMES):
            rows.append(
                {
                    "cell": cell,
                    "seed": 0,
                    "symbol": n,
                    "as_of": ts.date().isoformat(),
                    "target_weight": weight(paths, n, ts),
                    "vt_weight": 0.5,
                    "close": float(paths[n][ts]),
                    "calls": [],
                    "sources": {},
                    "regime": 0,
                }
            )
    return rows


def _fwd(paths, n, ts, h=20):
    s = paths[n]
    k = s.index.get_loc(ts)
    return s.iloc[k + h] / s.iloc[k] - 1


def test_horizon_returns_use_the_decision_horizon_and_check_price_source() -> None:
    paths = _paths()
    rows = _rows_on(paths, "rules", lambda p, n, ts: 0.0)
    fwd, problems = study.horizon_returns(rows, _prices_from(paths), 20)
    # Review C6: 3 of these 15 weekday design dates are NYSE closures (2016-01-01, 2017-04-14,
    # 2019-01-01). They are dropped for every name and listed with the true reason.
    assert len(problems) == 3 and all("not an NYSE session" in p for p in problems)
    assert len(fwd) == len(rows) - 3 * len(NAMES)
    r = rows[7]
    assert fwd[(r["symbol"], r["as_of"])] == pytest.approx(_fwd(paths, r["symbol"], pd.Timestamp(r["as_of"])))
    # One decision of a symbol off by 1 % against its other decisions: a different source,
    # left out. A common factor on every decision of a symbol is a later re-adjustment, kept.
    sym = rows[5]["symbol"]
    mine = [r for r in rows if r["symbol"] == sym]
    bad = [dict(r, close=r["close"] * (1.01 if r is rows[5] else 1.0)) for r in mine]
    fwd2, problems2 = study.horizon_returns(bad, _prices_from(paths), 20)
    assert (sym, rows[5]["as_of"]) not in fwd2 and any("stored close" in p for p in problems2)
    scaled = [dict(r, close=r["close"] * 1.01) for r in mine]
    fwd3, _ = study.horizon_returns(scaled, _prices_from(paths), 20)
    assert fwd3 == {k: v for k, v in fwd.items() if k[0] == sym}


def test_horizon_metrics_perfect_foresight_and_noise() -> None:
    paths = _paths()
    oracle = _rows_on(paths, "local_all", lambda p, n, ts: float(np.clip(10 * _fwd(p, n, ts), -1, 1)))
    rules = _rows_on(paths, "rules", lambda p, n, ts: 0.1 * (NAMES.index(n) - 2))
    rows = rules + oracle
    fwd, _ = study.horizon_returns(rows, _prices_from(paths), 20)
    hm = {m["cell"]: m for m in study.horizon_metrics(rows, fwd, 20, n_boot=300)}
    o = hm["local_all"]
    assert o["ic"] > 0.95 and o["hit_rate"] == pytest.approx(1.0) and o["ic_ci"][0] > 0.9
    assert o["ic_minus_rules_ci"][0] > 0 and o["horizon_sharpe"] > 0
    assert np.isnan(hm["rules"]["ic_minus_rules"])
    assert abs(hm["rules"]["ic"]) < 0.5 and hm["rules"]["ic_ci"][0] < hm["rules"]["ic"] < hm["rules"]["ic_ci"][1]
    text = study.render_horizon(list(hm.values()), [])
    assert "IC - rules" in text and "| local_all |" in text


def test_horizon_metrics_work_on_stored_first_pass_rows(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The report path reads rows the run already wrote (no model) and prints the primary table."""
    out = tmp_path / "r.jsonl"
    cfg = make_config(study.STUDY_BASE)
    study.run_study(["AAPL", "MSFT", "SPY"], study.design_dates(20)[1:5], 1, [study.CELLS[0]], cfg, out, None, lambda s: None)
    assert study.main(["--report", "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "Descriptive (per decision, 20-bar forward return" in text and "Left out" not in text
