"""v0.18 lane D: behaviour and error-path tests for the honest-trial-count DSR (N6/N8, R1.3),
the walk-forward gate and the ``stats`` CLI flags that render them."""

import json

import numpy as np
import pandas as pd
import pytest

from agentic_trader.alpha import walk_forward_gated_series
from agentic_trader.evaluation import PRE_REGISTRY_TRIALS_ESTIMATE, pre_registry_trial_estimate
from agentic_trader.stats import selection_report


def _returns(seed: int, n: int = 500, mu: float = 0.0005) -> np.ndarray:
    return np.random.default_rng(seed).normal(mu, 0.01, n)


# ------------------------------------------------------------ selection_report
def test_pre_registry_trials_lower_the_deflated_sharpe():
    r = _returns(0)
    trials = [0.2, 0.5, 0.8, 1.0, 0.3]
    base = selection_report(r, trials)
    rep = selection_report(r, trials, pre_registry_trials=64)
    assert "trials_incl_pre_registry" not in base
    assert rep["trials_incl_pre_registry"] == 5 + 64
    # more trials -> higher expected maximum -> no higher deflated probability
    assert rep["expected_max_sharpe_annual_incl_pre_registry"] > rep["expected_max_sharpe_annual"]
    assert rep["deflated_sharpe_prob_incl_pre_registry"] <= rep["deflated_sharpe_prob"]
    # the registered-count figure is unchanged by the extra rows
    assert rep["deflated_sharpe_prob"] == base["deflated_sharpe_prob"]


def test_n_trials_floor_and_validation():
    r = _returns(1)
    rep = selection_report(r, [0.4, 0.6], n_trials=10)
    assert rep["trials"] == 10 and rep["trials_measured"] == 2
    assert selection_report(r, [0.4, 0.6], n_trials=1)["trials"] == 2  # never below measured
    with pytest.raises(ValueError, match="n_trials"):
        selection_report(r, [0.4, 0.6], n_trials=0)


def test_effective_trials_collapse_for_identical_trials():
    r = _returns(2)
    base = _returns(3)
    rng = np.random.default_rng(4)
    near_copies = np.column_stack([base + rng.normal(0, 1e-5, base.size) for _ in range(8)])
    independent = np.column_stack([_returns(10 + k) for k in range(8)])
    copies = selection_report(r, [0.5] * 7 + [0.6], trial_returns=near_copies)
    indep = selection_report(r, [0.5] * 7 + [0.6], trial_returns=independent)
    assert copies["trials_effective"] < 1.5  # eight copies of one strategy are ~one trial
    assert indep["trials_effective"] > 4.0
    assert copies["trials_mean_corr"] > 0.99


def test_pre_registry_estimate_default_and_error():
    assert PRE_REGISTRY_TRIALS_ESTIMATE == pre_registry_trial_estimate()
    assert pre_registry_trial_estimate(1) == 0  # one value per constant = nothing rejected
    with pytest.raises(ValueError):
        pre_registry_trial_estimate(0)


# ------------------------------------------------------------ walk-forward gate
def test_walk_forward_gate_is_nan_before_min_bars_and_uses_no_future():
    n, h = 400, 5
    rng = np.random.default_rng(5)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    fwd = np.r_[np.log(close[h:] / close[:-h]), [np.nan] * h]
    idx = pd.bdate_range("2020-01-01", periods=n)
    sig = pd.DataFrame(
        {
            "good": np.clip(np.nan_to_num(fwd) * 50, -1, 1),  # peeks: a perfect alpha
            "noise": rng.uniform(-1, 1, n),
        },
        index=idx,
    )
    g = walk_forward_gated_series(sig, close, h, window=200, min_bars=100)
    assert g.iloc[: 100 + h].isna().all()
    assert g.dropna().between(-1, 1).all() and g.notna().sum() > 0
    # changing the future of the signals must not change any earlier gated value
    cut = 300
    sig2 = sig.copy()
    sig2.iloc[cut:] = -sig2.iloc[cut:]
    g2 = walk_forward_gated_series(sig2, close, h, window=200, min_bars=100)
    pd.testing.assert_series_equal(g.iloc[:cut], g2.iloc[:cut])


def test_walk_forward_gate_all_nan_when_nothing_passes():
    n = 300
    rng = np.random.default_rng(6)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    sig = pd.DataFrame({"flat": np.zeros(n)}, index=pd.bdate_range("2020-01-01", periods=n))
    assert walk_forward_gated_series(sig, close, 5, window=150, min_bars=60).isna().all()


# ------------------------------------------------------------ CLI render
def _csv(tmp_path, name, data: dict) -> str:
    p = tmp_path / name
    pd.DataFrame(data, index=pd.bdate_range("2021-01-01", periods=len(next(iter(data.values()))))).to_csv(p)
    return str(p)


def _json_out(out: str) -> dict:
    return json.loads(out[out.index("{") :])


def test_cli_stats_renders_honest_and_effective_dsr(tmp_path, capsys):
    from agentic_trader.cli import main

    r = _csv(tmp_path, "r.csv", {"r": _returns(7)})
    tr = _csv(tmp_path, "t.csv", {f"t{k}": _returns(20 + k) for k in range(4)})
    assert (
        main(
            [
                "stats",
                r,
                "--trials",
                "4",
                "--trial-sharpes",
                "0.2,0.4,0.6,0.8",
                "--pre-registry-trials",
                "64",
                "--trial-returns",
                tr,
            ]
        )
        == 0
    )
    rep = _json_out(capsys.readouterr().out)
    assert rep["trials_incl_pre_registry"] == 68
    assert "deflated_sharpe_prob_effective" in rep and rep["trials_effective"] > 1.0


def test_cli_stats_trials_count_exceeds_listed_sharpes(tmp_path, capsys):
    from agentic_trader.cli import main

    r = _csv(tmp_path, "r.csv", {"r": _returns(8)})
    assert main(["stats", r, "--trials", "9", "--trial-sharpes", "0.2,0.5"]) == 0
    rep = _json_out(capsys.readouterr().out)
    assert rep["trials"] == 9 and rep["trials_measured"] == 2


def test_cli_stats_rejects_single_column_trial_returns(tmp_path, capsys):
    from agentic_trader.cli import main

    r = _csv(tmp_path, "r.csv", {"r": _returns(9)})
    tr = _csv(tmp_path, "t.csv", {"t0": _returns(30)})
    assert main(["stats", r, "--trials", "2", "--trial-returns", tr]) != 0
    assert "two trial columns" in capsys.readouterr().err
