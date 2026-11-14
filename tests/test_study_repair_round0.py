"""Round 0 study repair (review 2026-11-12: C4, C5, C6, B2, B3, B4, B10).

Each test states the failure it would have caught. Fixture rows and fake models only: no
model call, no network."""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
import pytest

from agentic_trader import evaluation
from agentic_trader import study_design as sd
from agentic_trader.evaluation import CORE_UNIVERSE
from agentic_trader.nyse_calendar import is_session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import v16_local_study as v16  # noqa: E402

NAMES = CORE_UNIVERSE["equity"] + CORE_UNIVERSE["fx"]
Model = Callable[[np.ndarray, np.ndarray, np.random.Generator], np.ndarray]


def _rows(model: Model, rule_strength: float, dates: int = 150, seed: int = 0,
          class_drift: dict[str, float] | None = None) -> list[dict[str, Any]]:
    """10 equities and 5 FX pairs per date; the rule signal is tanh(strength x return + noise)."""
    rng = np.random.default_rng(seed)
    out: list[dict[str, Any]] = []
    for d in range(dates):
        for cls, n in (("equity", 10), ("fx", 5)):
            f = rng.normal(size=n) + (class_drift or {}).get(cls, 0.0)
            q = np.tanh(rule_strength * f + rng.normal(size=n))
            m = model(q, f, rng)
            out += [{"as_of": f"d{d:03d}", "asset_class": cls, "signal_rule": float(q[i]),
                     "signal_model": float(m[i]), "fwd_ret": float(f[i])} for i in range(n)]
    return out


# ---------------------------------------------------------------- C4: the metric
@pytest.mark.parametrize("name,model", [
    ("half the rule", lambda q, f, r: 0.5 * q),
    ("minus the rule", lambda q, f, r: -q),
    ("twice the rule", lambda q, f, r: 2.0 * q),
])
def test_a_linear_copy_of_the_rule_scores_exactly_zero(name: str, model: Model) -> None:
    """C4: Spearman(model - rule, return) gave half-the-rule minus the rule's IC. With an
    anti-predictive rule that was a pass for a model that adds nothing."""
    res = sd.incremental_ic(_rows(model, rule_strength=-0.3))
    assert res["primary"]["ic"] == 0.0 and res["primary"]["t"] is None
    assert all(f["copy_of_rule"] for f in res["rule_fit"].values())
    assert not res["primary"]["ci95"][0] > 0


def test_the_old_metric_passed_a_model_that_adds_nothing() -> None:
    """The documented flaw, kept as a regression: the legacy statistic is reported, shows a
    'significant' positive value for half-the-rule beside an anti-predictive rule, and the
    primary does not."""
    res = sd.incremental_ic(_rows(lambda q, f, r: 0.5 * q, rule_strength=-0.3, dates=313))
    assert res["rule"]["ic"] < -0.1
    assert res["legacy_model_minus_rule"]["ci95"][0] > 0
    assert res["primary"]["ic"] == 0.0


@pytest.mark.parametrize("name,model", [
    ("rounded to one decimal", lambda q, f, r: np.round(q, 1)),
    ("rounded to halves", lambda q, f, r: np.round(2 * q) / 2),
    ("clipped", lambda q, f, r: np.clip(2 * q, -1, 1)),
    ("sign only", lambda q, f, r: np.sign(q)),
    ("pure noise", lambda q, f, r: r.normal(size=len(q))),
])
def test_a_function_of_the_rule_or_noise_does_not_pass(name: str, model: Model) -> None:
    """A model that coarsens a strongly predictive rule, or ignores everything, must not get
    a 95 % interval above zero. (A per-date rank residual failed this for rounding: ranks
    discard the spacing between names and the rounded copy keeps some of it.)"""
    passes = 0
    for seed in range(6):
        res = sd.incremental_ic(_rows(model, rule_strength=0.3, dates=313, seed=seed))
        passes += bool(res["primary"]["ci95"][0] > 0)
        assert abs(res["primary"]["ic"]) < 0.06
    assert passes <= 1                                    # nominal size is 2.5 % per run


def test_real_added_information_is_detected() -> None:
    def model(q: np.ndarray, f: np.ndarray, r: np.random.Generator) -> np.ndarray:
        return np.round(np.tanh(q + 0.25 * f + 0.5 * r.normal(size=len(q))), 1)
    res = sd.incremental_ic(_rows(model, rule_strength=0.1, dates=313))
    assert res["primary"]["ci95"][0] > 0 and res["primary"]["ic"] > 0.1
    assert res["metric"].startswith("residual IC") and res["rows"] == 313 * 15


# ---------------------------------------------------------------- C5: asset-class timing
def test_asset_class_timing_is_not_scored_as_selection() -> None:
    """C5: equities drift up and FX is flat; a model that is simply more bullish on every
    equity than on any FX pair ranks perfectly across classes and has no skill inside one."""
    def model(q: np.ndarray, f: np.ndarray, r: np.random.Generator) -> np.ndarray:
        return (0.5 if len(q) == 10 else -0.5) + 0.2 * r.normal(size=len(q))
    rows = _rows(model, rule_strength=0.0, dates=200, class_drift={"equity": 3.0, "fx": 0.0})
    res = sd.incremental_ic(rows)
    assert res["legacy_model_minus_rule"]["ic"] > 0.3     # pooled ranking: looks like skill
    assert abs(res["primary"]["ic"]) < 0.05 and not res["primary"]["ci95"][0] > 0
    assert set(res["rule_fit"]) == {"equity", "fx"}


def test_classes_come_from_the_symbol_and_small_classes_are_left_out() -> None:
    assert sd.asset_class_of("AAPL") == "equity" and sd.asset_class_of("EURUSD") == "fx"
    assert sd.asset_class_of(None) == "all"
    rows = [{"as_of": "d0", "symbol": s, "signal_rule": 0.1 * i, "signal_model": 0.3 - 0.1 * i, "fwd_ret": 0.01 * i}
            for i, s in enumerate(["AAPL", "MSFT", "NVDA", "META", "JPM", "EURUSD", "USDJPY"])]
    res = sd.incremental_ic(rows)
    assert res["rows_in_small_classes"] == 2 and res["primary"]["dates"] == 1


# ---------------------------------------------------------------- C6: dates
def test_design_dates_are_nyse_sessions() -> None:
    """C6: weekly anchors used to land on Monday closures (about 28 of 313), where equities
    were read on Friday's bar and FX on Monday's."""
    dec, post = sd.weekly_dates(sd.DECISIVE), sd.weekly_dates(sd.POSTCUTOFF)
    assert len(dec) == 313 and len(post) == 70
    assert all(is_session(d) for d in dec + post)
    assert date(2016, 1, 18) not in dec and date(2016, 1, 19) in dec       # MLK day rolls to Tuesday
    assert all(b > a for a, b in zip(dec, dec[1:]))
    assert dec[0] == date(2016, 1, 4) and post[0] >= date(2025, 7, 1) and post[-1] <= date(2026, 10, 30)


def test_a_stale_bar_is_excluded_and_counted() -> None:
    rows = _rows(lambda q, f, r: q + 0.3 * f, rule_strength=0.1, dates=20)
    for r in rows:
        r["entry_bar_date"] = r["as_of"]
    rows[0]["entry_bar_date"] = "an earlier bar"
    rows[1]["signal_model"] = None
    rows[2]["fwd_ret"] = None
    res = sd.incremental_ic(rows)
    assert res["excluded"] == {"fallback": 1, "no_forward_return": 1, "stale_bar": 1} and res["excluded_rows"] == 3


# ---------------------------------------------------------------- B10: power arithmetic
def test_mde_uses_the_per_date_null_variance() -> None:
    m = sd.mde_ic_dates(313, [10, 5])
    assert m["sd_per_date"] == pytest.approx(0.278, abs=0.002) and m["mde"] == pytest.approx(0.044, abs=0.001)
    assert sd.mde_ic_dates(70, [10, 5])["mde_one_sided_95"] == pytest.approx(0.083, abs=0.002)
    null = [sd.incremental_ic(_rows(lambda q, f, r: r.normal(size=len(q)), 0.0, dates=313, seed=s))["primary"]
            for s in range(8)]
    sd_date = float(np.mean([x["se"] * np.sqrt(x["dates"]) for x in null]))
    assert sd_date == pytest.approx(m["sd_per_date"], rel=0.10)            # the formula matches simulation


# ---------------------------------------------------------------- B2: replication
def _rep(ic: float, se: float, fallback: float = 0.0) -> dict[str, Any]:
    return {"fallback_share": fallback, "metric": {"primary": {
        "ic": ic, "se": se, "ci95": [ic - sd.Z_975 * se, ic + sd.Z_975 * se], "lower95_one_sided": ic - sd.Z_95 * se}}}


def test_a_design_pass_counts_only_if_it_replicates() -> None:
    """B2: under the old rule a post-cutoff IC of zero with a wide interval left a memory
    effect 'not attributed to memory', and it was adopted."""
    passed = _rep(0.10, 0.016)
    assert sd.replication_verdict(passed, _rep(0.00, 0.033))["adopt"] is False
    assert sd.replication_verdict(passed, _rep(0.04, 0.033))["adopt"] is False          # positive, not proven
    assert sd.replication_verdict(passed, _rep(0.09, 0.033))["adopt"] is True
    assert sd.replication_verdict(passed, None)["adopt"] is False
    assert sd.replication_verdict(passed, _rep(0.09, 0.033, fallback=0.2))["adopt"] is False
    null = sd.replication_verdict(_rep(0.02, 0.016), _rep(0.09, 0.033))
    assert null["design_pass"] is False and null["adopt"] is False
    assert sd.replication_verdict(_rep(0.10, 0.016, fallback=0.11), _rep(0.09, 0.033))["design_pass"] is False


# ---------------------------------------------------------------- B4: signature gate
def test_registered_cells_need_the_signed_preregistration(tmp_path: Path) -> None:
    with pytest.raises(sd.PreregNotSigned, match="still a draft"):
        sd.prereg_gate(tmp_path)
    signed = tmp_path / sd.PREREG_SIGNED
    signed.parent.mkdir(parents=True)
    signed.write_text("# v0.16 pre-registration (DRAFT): ...\n", encoding="utf-8")
    with pytest.raises(sd.PreregNotSigned):
        sd.prereg_gate(tmp_path)
    signed.write_text("# v0.16 pre-registration\n\n**Status: signed 2026-11-13.**\n", encoding="utf-8")
    gate = sd.prereg_gate(tmp_path)
    assert gate["prereg_path"] == sd.PREREG_SIGNED and len(gate["prereg_sha256"]) == 64
    assert sd.prereg_document(tmp_path) == signed


class _NeverCalled:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError("the gate must fire before any model call")


def test_design_runner_refuses_without_signature_and_with_a_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                  capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(v16, "ROOT", tmp_path)                 # a tree with no signed pre-registration
    monkeypatch.setattr(v16, "_header", lambda a, llm, g, extra: {"header_id": "h", "git_sha": "x"})
    monkeypatch.setattr(v16.lineage, "check_resume", lambda path, hdr, **kw: hdr)
    base = ["design", "--cell", "decisive_ta", "--out", str(tmp_path / "d.jsonl"), "--data", "synthetic"]
    assert v16.main(base, llm_factory=lambda a: _NeverCalled()) == 2
    assert "still a draft" in capsys.readouterr().err
    assert v16.main([*base, "--limit", "30"], llm_factory=lambda a: _NeverCalled()) == 2
    assert "refusing design --limit" in capsys.readouterr().err
    assert not (tmp_path / "d.jsonl").exists()


# ---------------------------------------------------------------- B3: holdout lock
def test_holdout_access_needs_a_recorded_basis_or_the_v2_audit(tmp_path: Path) -> None:
    assert sd.holdout_access(sd.DECISIVE) == {"touches_holdout": False}
    post = sd.holdout_access(sd.POSTCUTOFF)
    assert post["touches_holdout"] and "2025-06-30" in post["holdout_basis"]
    bare = sd.DesignCell("x", "no basis", "2024-01-02", "2024-06-28")
    with pytest.raises(evaluation.HoldoutLocked):
        sd.holdout_access(bare, tmp_path / "none.json")
    ok = tmp_path / "recall2.json"
    ok.write_text(json.dumps({"recall_flagged": False, "reasons": [], "real": {"n": 200}, "placebo": {"n": 60},
                              "equivalence": {"passed": True}}),
                  encoding="utf-8")
    assert sd.holdout_access(bare, ok)["holdout_basis"] == "v2 recall audit passed"
    assert evaluation.DEFAULT_RECALL_AUDIT_PATH.endswith("recall2.json")


# ---------------------------------------------------------------- first-pass report
def _llm_study() -> Any:
    spec = importlib.util.spec_from_file_location("llm_study_round0", ROOT / "scripts" / "llm_study.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["llm_study_round0"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_first_pass_report_drops_closed_dates_for_every_name() -> None:
    """C6: on 2016-01-01 the ten equities were left out with the reason 'fewer than 20 bars'
    while the five FX pairs were scored alone."""
    study = _llm_study()
    days = pd.bdate_range("2015-12-28", "2016-03-31")

    def prices(symbol: str, start: date, end: date) -> pd.Series:
        idx = days if symbol == "EURUSD" else pd.DatetimeIndex([d for d in days if is_session(d.date())])
        s = pd.Series(100.0 + np.arange(len(idx)), index=idx)
        return s[(s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))]
    rows = [{"symbol": s, "as_of": d, "close": float(prices(s, date(2015, 12, 1), date.fromisoformat(d)).iloc[-1])}
            for d in ("2016-01-01", "2016-01-04") for s in ("AAPL", "EURUSD")]
    fwd, problems = study.horizon_returns(rows, prices, 20)
    assert set(fwd) == {("AAPL", "2016-01-04"), ("EURUSD", "2016-01-04")}
    assert problems == ["2016-01-01: not an NYSE session, design date dropped for all 2 names"]


def test_first_pass_report_scores_rows_stored_on_an_older_adjustment_vintage() -> None:
    """Rescore bug: the rows hold adjusted closes from the run's vintage; the provider at report
    time has re-adjusted for a later dividend (every close x 0.9992) or serves a different
    source altogether (unadjusted / synthetic). The first must score with the provider's own
    return; the second must be left out, never scored."""
    study = _llm_study()
    idx = pd.DatetimeIndex([d for d in pd.bdate_range("2016-04-01", "2016-08-31") if is_session(d.date())])
    adjusted = pd.Series(23.0 * np.exp(0.002 * np.arange(len(idx))), index=idx)
    revintaged = adjusted * 0.9992                      # dividend paid after the run
    unadjusted = adjusted * 26.0 * (1.0 + 0.01 * np.sin(np.arange(len(idx))))   # different basis and path

    def feed(series: pd.Series) -> Callable[[str, date, date], pd.Series]:
        return lambda sym, start, end: series[(series.index >= pd.Timestamp(start)) & (series.index <= pd.Timestamp(end))]
    dates = [idx[0], idx[10], idx[30]]
    rows = [{"symbol": "AAPL", "as_of": d.date().isoformat(), "close": float(adjusted.loc[d])} for d in dates]
    fwd, problems = study.horizon_returns(rows, feed(revintaged), 20)
    assert problems == [] and len(fwd) == 3
    i0 = idx.get_loc(dates[1])
    assert fwd[("AAPL", dates[1].date().isoformat())] == pytest.approx(adjusted.iloc[i0 + 20] / adjusted.iloc[i0] - 1)
    fwd, problems = study.horizon_returns(rows, feed(unadjusted), 20)
    assert len(fwd) < 3 and problems and all("different source or adjustment basis" in p for p in problems)


def test_first_pass_ic_is_within_asset_class() -> None:
    study = _llm_study()
    syms = ["AAPL", "MSFT", "NVDA", "JPM", "EURUSD", "USDJPY", "GBPUSD"]
    w = np.array([0.9, 0.8, 0.7, 0.6, -0.6, -0.7, -0.8])        # long equities, short FX
    f = np.array([0.04, 0.05, 0.06, 0.07, -0.01, 0.0, 0.01])    # equities up; inside a class the order is wrong
    assert study._spearman(w, f) >= 0.5                         # pooled: looks like skill
    assert study._grouped_ic(syms, w, f) == pytest.approx(-1.0)
    assert np.isnan(study._grouped_ic(["AAPL", "EURUSD"], w[:2], f[:2]))


# ---------------------------------------------------------------- B4: the signing command
def test_sign_prereg_produces_a_document_the_gate_accepts(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("sign_prereg_round0", ROOT / "scripts" / "sign_prereg.py")
    assert spec and spec.loader
    sp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sp)
    draft = tmp_path / sd.PREREG_DRAFT
    draft.parent.mkdir(parents=True)
    source = sd.prereg_document(ROOT)
    if source.name != Path(sd.PREREG_DRAFT).name:
        pytest.skip("the pre-registration is already signed in this tree")
    draft.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "README.md").write_text("see docs/evaluation/v16_preregistration_DRAFT.md\n", encoding="utf-8")
    with pytest.raises(sp.SigningRefused):
        sp.sign(tmp_path, "A. Owner", date(2026, 11, 13), "", "abc1234", 81, use_git=False)
    res = sp.sign(tmp_path, "A. Owner", date(2026, 11, 13), "845dbda0ea48ed74", "abc1234", 81, use_git=False)
    text = (tmp_path / sd.PREREG_SIGNED).read_text(encoding="utf-8")
    assert not draft.exists() and "DRAFT" not in text.splitlines()[0]
    assert "signed by A. Owner on 2026-11-13" in text and "(not signed)" not in text and "filled at signing" not in text
    assert "`845dbda0ea48ed74`" in text and "`abc1234`" in text and "`len(evaluation.TRIALS)`: 81" in text
    assert sd.prereg_gate(tmp_path)["prereg_sha256"] == res["sha256"]
    assert "v16_preregistration.md" in (tmp_path / "README.md").read_text(encoding="utf-8")
    with pytest.raises(sp.SigningRefused, match="already exists"):
        sp.sign(tmp_path, "A. Owner", date(2026, 11, 13), "845dbda0ea48ed74", "abc1234", 81, use_git=False)
