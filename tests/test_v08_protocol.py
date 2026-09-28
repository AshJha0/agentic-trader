"""v0.8 protocol machinery: portfolio-level Sharpe intervals over time and the rebalance-phase
sweep (review finding 65), and the trials registry behind the deflated Sharpe (finding 87)."""
import numpy as np
import pytest

from agentic_trader import make_config
from agentic_trader.backtest import AGENT, run_agent_backtest, run_portfolio_backtest
from agentic_trader.data import SyntheticProvider
from agentic_trader.evaluation import TRIALS, reproducible_trials, trial_slug
from agentic_trader.stats import SharpeDifference, paired_sharpe_block_bootstrap

CFG = make_config(memory_path=None)


def test_paired_sharpe_block_bootstrap_identical_series_is_zero_with_p_one():
    r = np.random.default_rng(0).normal(0.0004, 0.01, 800)
    d = paired_sharpe_block_bootstrap(r, r.copy(), 252.0)
    assert isinstance(d, SharpeDifference) and d.n == 800
    assert d.diff == 0.0 and d.ci_low <= 0.0 <= d.ci_high and d.p_value == 1.0


def test_paired_sharpe_block_bootstrap_detects_a_real_difference_and_is_deterministic():
    rng = np.random.default_rng(1)
    a = rng.normal(0.0008, 0.01, 1200)
    b = a - 0.0006                                   # same days, same noise, lower mean
    d1 = paired_sharpe_block_bootstrap(a, b, 252.0, n_boot=2000, seed=3)
    d2 = paired_sharpe_block_bootstrap(a, b, 252.0, n_boot=2000, seed=3)
    assert d1 == d2
    assert d1.diff > 0 and d1.ci_low > 0 and d1.p_value < 0.05
    assert d1.sharpe_a == pytest.approx(a.mean() / a.std(ddof=1) * np.sqrt(252))
    assert d1.ci_low <= d1.diff <= d1.ci_high


def test_paired_sharpe_block_bootstrap_uses_excess_returns_and_drops_bad_days():
    rng = np.random.default_rng(2)
    a, b = rng.normal(0.0005, 0.01, 600), rng.normal(0.0002, 0.02, 600)
    a[10], b[20] = np.nan, np.inf
    scalar = paired_sharpe_block_bootstrap(a, b, 252.0, rf=0.04, n_boot=500)
    per_day = paired_sharpe_block_bootstrap(a, b, 252.0, rf=np.full(600, 0.04), n_boot=500)
    raw = paired_sharpe_block_bootstrap(a, b, 252.0, n_boot=500)
    assert scalar.n == per_day.n == 598
    assert scalar == per_day
    assert scalar.diff != raw.diff                   # the risk-free rate does not cancel in a Sharpe difference
    with pytest.raises(ValueError):
        paired_sharpe_block_bootstrap(a, b[:-1], 252.0)
    tiny = paired_sharpe_block_bootstrap([0.1, 0.2], [0.1, 0.3], 252.0)
    assert tiny.n == 2 and np.isnan(tiny.diff) and tiny.p_value == 1.0


def test_rebalance_offset_shifts_the_decision_bars_and_is_validated():
    base = run_agent_backtest("AAPL", "2024-01-02", "2024-03-28", CFG, rebalance_every=10)
    shifted = run_agent_backtest("AAPL", "2024-01-02", "2024-03-28", CFG, rebalance_every=10, rebalance_offset=3)
    assert base.decisions[0].as_of == base.dates[0].date()
    expected = [base.dates[i].date() for i in range(3, len(base.dates) - 1, 10)]
    assert [d.as_of for d in shifted.decisions] == expected
    assert np.all(shifted.results[AGENT].positions[:3] == 0.0)   # flat until the first decision
    for bad in (-1, 10, 11):
        with pytest.raises(ValueError):
            run_agent_backtest("AAPL", "2024-01-02", "2024-03-28", CFG, rebalance_every=10, rebalance_offset=bad)


def test_portfolio_report_sharpe_difference_and_offset_pass_through():
    syms = ["AAPL", "MSFT", "EURUSD"]
    rep = run_portfolio_backtest(syms, "2024-01-02", "2024-03-28", CFG, rebalance_every=10)
    d = rep.sharpe_difference(AGENT, "Buy&Hold")
    assert isinstance(d, SharpeDifference) and d.n == len(rep.returns) - 1 and np.isfinite(d.diff)
    assert d.ci_low <= d.diff <= d.ci_high
    # the same bars, ddof, periods-per-year and excess-return convention as the report's metrics
    assert d.sharpe_a == pytest.approx(rep.metrics[AGENT].sharpe, abs=1e-9)
    assert d.sharpe_b == pytest.approx(rep.metrics["Buy&Hold"].sharpe, abs=1e-9)
    rep3 = run_portfolio_backtest(syms, "2024-01-02", "2024-03-28", CFG, rebalance_every=10, rebalance_offset=3)
    assert rep3.sleeves["AAPL"].decisions[0].as_of == rep3.sleeves["AAPL"].dates[3].date()
    assert rep3.sleeves["AAPL"].decisions[0].as_of != rep.sleeves["AAPL"].decisions[0].as_of


def test_trials_registry_is_complete_and_every_reproducible_trial_builds_a_config():
    names = [t.name for t in TRIALS]
    assert len(names) == len(set(names)) and len(TRIALS) >= 25
    assert sum(t.version == "v0.3" for t in TRIALS) == 16      # the ablation the v0.3 rules were chosen from
    assert {t.version for t in TRIALS} >= {"v0.3", "v0.4", "v0.5", "v0.5.1", "v0.6", "v0.8"}
    assert any(t.overrides is None for t in TRIALS)             # historical trials not reproducible from config
    for t in reproducible_trials():
        cfg = make_config(t.overrides)
        assert isinstance(cfg["rules"]["fx_carry_neutral"], bool)
    control = next(t for t in TRIALS if t.name == "v0.2 (control)")
    cfg = make_config(control.overrides)
    assert cfg["risk"]["neutral_weight"] == {"equity": 0.0, "fx": 0.0} and cfg["risk"]["rebalance_band"] == 0.0
    assert not cfg["rules"]["fx_carry_neutral"] and not cfg["backtest"]["use_stops"]
    assert len({trial_slug(t.name) for t in TRIALS}) == len(TRIALS)


# v0.8 regression review (d): the bootstrap pairs the return over (t-1, t] with rf[t-1], as the metrics do.
class _RampRF(SyntheticProvider):
    """A per-bar risk-free rate that varies with the date (the synthetic default is constant, which
    cannot see a one-bar shift in the rf alignment)."""

    def risk_free_series(self, dates):
        return np.array([0.01 + 0.0002 * (d.dayofyear % 40) + 0.03 * (d.day % 3 == 0) for d in dates])


def test_portfolio_report_sharpe_difference_pairs_a_varying_rf_like_the_metrics():
    syms = ["AAPL", "MSFT", "EURUSD"]
    rep = run_portfolio_backtest(syms, "2024-01-02", "2024-03-28", CFG, rebalance_every=10, provider=_RampRF(CFG))
    assert isinstance(rep.rf, np.ndarray) and np.std(rep.rf) > 0.005
    d = rep.sharpe_difference(AGENT, "Buy&Hold")
    assert d.sharpe_a == pytest.approx(rep.metrics[AGENT].sharpe, abs=1e-9)          # was off by one bar of rf
    assert d.sharpe_b == pytest.approx(rep.metrics["Buy&Hold"].sharpe, abs=1e-9)
    a, b = (rep.returns[s].to_numpy(dtype=float)[1:] for s in (AGENT, "Buy&Hold"))
    ppy = max(r.instrument.periods_per_year for r in rep.sleeves.values())
    shifted = paired_sharpe_block_bootstrap(a, b, ppy, rf=rep.rf[1:], n_boot=50)       # the pre-fix pairing
    aligned = paired_sharpe_block_bootstrap(a, b, ppy, rf=rep.rf[:-1], n_boot=50)
    assert abs(shifted.sharpe_a - rep.metrics[AGENT].sharpe) > 1e-6                    # the test can see the shift
    assert aligned.sharpe_a == pytest.approx(rep.metrics[AGENT].sharpe, abs=1e-9)


# Final code review (stats.py, medium): a flat agent reads Sharpe 0 in the table and in the printed
# Sharpe difference alike, under a constant rf and under a varying cash leg.
@pytest.mark.parametrize("provider", [None, "ramp"])
def test_portfolio_report_sharpe_difference_of_a_flat_agent_is_zero_like_the_table(monkeypatch, provider):
    from dataclasses import replace

    from agentic_trader import TradingGraph
    from agentic_trader.state import Action

    orig = TradingGraph.propagate

    def flat(self, symbol, as_of, asset_class=None, current_weight=None, book=None):
        st, dec = orig(self, symbol, as_of, asset_class, current_weight, book)
        return st, replace(dec, action=Action.HOLD, target_weight=0.0, stop_loss=None, take_profit=None)

    monkeypatch.setattr(TradingGraph, "propagate", flat)
    syms = ["AAPL", "MSFT", "EURUSD"]
    rep = run_portfolio_backtest(syms, "2024-01-02", "2024-03-28", CFG, rebalance_every=10,
                                 provider=_RampRF(CFG) if provider else None)
    assert rep.metrics[AGENT].avg_exposure == 0.0 and rep.metrics[AGENT].num_trades == 0
    d = rep.sharpe_difference(AGENT, "Buy&Hold")
    assert d.sharpe_a == pytest.approx(rep.metrics[AGENT].sharpe, abs=1e-9)               # was -3.5e16 vs 0.0
    assert d.sharpe_b == pytest.approx(rep.metrics["Buy&Hold"].sharpe, abs=1e-9) and abs(d.ci_low) < 1e3
    if provider is None:                                                                  # constant rf: exactly flat
        assert rep.metrics[AGENT].sharpe == 0.0 and d.sharpe_a == 0.0 and d.diff == -d.sharpe_b
