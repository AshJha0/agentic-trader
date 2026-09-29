"""v0.11 (tier-2 review, batch 1): engine parity and validation, unrounded evaluation rows,
BH over the printed rows, EDGAR visibility by acceptance time, impact ADV on the as-traded
close, the vol-scaled aggressive stance, news confidence by tone mass, the trials registry."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from agentic_trader import make_config
from agentic_trader.backtest import AGENT, impact_coefficients, run_agent_backtest
from agentic_trader.config import RULES_V02
from agentic_trader.data import SyntheticProvider
from agentic_trader.data.edgar import visible_dates
from agentic_trader.evaluation import TRIALS, EvaluationResult, evaluate
from agentic_trader.instruments import Instrument
from agentic_trader.quant import pycore

CFG = make_config(memory_path=None)


# ------------------------------------------------------------------ engine
def test_numpy_metrics_read_a_nan_risk_free_rate_as_zero_like_the_cpp_core():
    eq = 100_000 * np.cumprod(1 + np.random.default_rng(1).normal(0.0004, 0.01, 300))
    pos = np.ones(300)
    a = pycore.compute_metrics(eq, pos, 252.0, float("nan"))
    b = pycore.compute_metrics(eq, pos, 252.0, 0.0)
    assert a.sharpe == b.sharpe and np.isfinite(a.annualized_vol) and a.annualized_vol == b.annualized_vol


@pytest.mark.parametrize("field,bad", [("cost_bps", float("nan")), ("cost_bps", -1.0), ("slippage_bps", float("inf")),
                                       ("borrow_annual", -0.01), ("max_leverage", float("nan")), ("max_leverage", -1.0),
                                       ("carry_annual", float("inf")), ("risk_free_annual", float("inf"))])
def test_backtest_config_fields_are_validated_on_both_backends(field, bad):
    from agentic_trader import quant
    cfg = pycore.BacktestConfig(**{field: bad})
    prices, w = np.linspace(100, 110, 30), np.full(30, 0.5)
    with pytest.raises(ValueError):
        pycore.validate_backtest_inputs(prices, w, cfg)
    with pytest.raises(ValueError):
        quant.run_backtest(prices, w, cfg)


def test_a_nan_risk_free_rate_is_allowed_and_means_zero():
    cfg = pycore.BacktestConfig(risk_free_annual=float("nan"))
    prices, w = np.linspace(100, 110, 30), np.full(30, 0.5)
    pycore.validate_backtest_inputs(prices, w, cfg)


# ------------------------------------------------------------------ evaluation precision and BH
def test_evaluation_rows_keep_full_precision_and_paired_tables_correct_over_printed_rows(monkeypatch):
    res = evaluate(["AAPL", "MSFT", "EURUSD"], {"p": ("2024-01-02", "2024-03-28")}, CFG, 10, workers=1)
    sharpe = res.rows["Sharpe"].to_numpy(float)
    assert any(abs(v - round(v, 2)) > 1e-9 for v in sharpe if np.isfinite(v))   # stored unrounded
    # BH is decided over the rows the table prints: two controls at p 0.03/0.06 are not
    # flagged when they are the only rows (thresholds 0.025 and 0.05), but the 0.03 row is
    # flagged among six naive rows at 1e-4 (its threshold rises to 5 x 0.05 / 8 = 0.031).
    from agentic_trader.stats import PairedBootstrap
    p_of = {"Buy&Hold": 0.03, "B&H vol-target": 0.06, "SMA(20/50)": 1e-4, "MACD": 1e-4, "KDJ+RSI": 1e-4, "ZMR": 1e-4,
            "TSMOM(12-1)": 1e-4, "Carry": 1e-4}

    def fake_paired(self, base, metric="Sharpe", period=None, universe=None, strategy=AGENT, cluster=True):
        return PairedBootstrap(3, 0.1, 0.01, 0.2, p_of[base], 2, "instruments", 1)

    monkeypatch.setattr(EvaluationResult, "paired", fake_paired)
    controls = ("Buy&Hold", "B&H vol-target")
    only = res.paired_table("MDD%", baselines=controls)
    assert set(only["baseline"]) == set(controls) and not only["significant"].any()
    every = res.paired_table("MDD%")
    flags = every[every["period"] == "p"].set_index("baseline")["significant"]
    assert bool(flags["Buy&Hold"]) and not bool(flags["B&H vol-target"])


# ------------------------------------------------------------------ EDGAR visibility
def test_edgar_visibility_follows_the_acceptance_time_in_eastern_time():
    filed = pd.Series(pd.to_datetime(["2019-05-08", "2019-04-30", "2013-04-26", "2019-05-07", "2020-01-10"]))
    # UTC timestamps as the submissions feed prints them: 16:34 ET (after the close), 06:49 ET,
    # 19:36 ET the evening before the filing date, unknown, and 10:00 ET
    accepted = pd.Series(["2019-05-08T20:34:31.000Z", "2019-04-30T10:49:33.000Z", "2013-04-25T23:36:25.000Z",
                          None, "2020-01-10T15:00:00.000Z"])
    vis = visible_dates(filed, accepted)
    assert [d.date().isoformat() for d in vis] == ["2019-05-09", "2019-04-30", "2013-04-26", "2019-05-07", "2020-01-10"]
    assert visible_dates(filed, None).equals(filed)                  # no timestamps at all: the filing date


def test_edgar_news_and_facts_use_the_visible_date(tmp_path, monkeypatch):
    from agentic_trader.data import edgar as edgar_mod
    from agentic_trader.data.edgar import EdgarClient
    sub = {"filings": {"recent": {"form": ["10-Q", "8-K"], "filingDate": ["2024-05-02", "2024-05-06"],
                                  "reportDate": ["2024-03-31", ""], "items": ["", "2.02"],
                                  "accessionNumber": ["0000000001-24-000001", "0000000001-24-000002"],
                                  "acceptanceDateTime": ["2024-05-02T21:15:00.000Z", "2024-05-06T12:00:00.000Z"]},
                       "files": []}, "sic": "3571"}
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
        {"start": "2024-01-01", "end": "2024-03-31", "val": 1e9, "filed": "2024-05-02", "form": "10-Q",
         "fy": 2024, "fp": "Q1", "accn": "0000000001-24-000001"}]}}}}}
    import json

    def fetch(url):
        if "company_tickers" in url:
            return json.dumps({"0": {"ticker": "TST", "cik_str": 1, "title": "Test Co"}})
        return json.dumps(sub if "submissions" in url else facts)
    c = EdgarClient(user_agent="t t@example.com", cache_dir=str(tmp_path), fetch=fetch, ciks={"TST": "0000000001"})
    monkeypatch.setattr(EdgarClient, "profile", lambda self, t: {"sic": "3571"})
    fl = c.filings("TST")
    assert fl["visible"].dt.date.tolist() == [date(2024, 5, 3), date(2024, 5, 6)]   # 17:15 ET -> next session
    assert [n.published for n in c.news("TST", date(2024, 5, 2), 5)] == []
    assert [n.published for n in c.news("TST", date(2024, 5, 3), 5)] == [date(2024, 5, 3)]
    f = c.facts("TST")
    assert f.loc[0, "filed"].date() == date(2024, 5, 3) and f.loc[0, "accn"] == "0000000001-24-000001"


# ------------------------------------------------------------------ impact basis
def test_impact_uses_the_as_traded_close_for_dollar_volume():
    n = 80
    idx = pd.bdate_range("2024-01-01", periods=n)
    close = np.full(n, 100.0) * np.exp(np.cumsum(np.random.default_rng(0).normal(0, 0.01, n)))
    full = pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": 1e6}, index=idx)
    cfg = make_config(costs={"impact_coeff": 1.0}, initial_capital=1e8)
    ins = Instrument.parse("AAPL")
    k_tr = impact_coefficients(full, ins, cfg)
    k_raw = impact_coefficients(full, ins, cfg, as_traded_close=close * 2.0)   # twice the price per share
    ok = np.isfinite(k_tr) & np.isfinite(k_raw)
    assert ok.any() and np.allclose(k_raw[ok], k_tr[ok] / np.sqrt(2.0))           # K ~ sqrt(capital / (price * ADV))
    assert np.allclose(impact_coefficients(full, ins, cfg, as_traded_close=np.full(n, np.nan))[ok], k_tr[ok])


def test_synthetic_provider_has_no_as_traded_series_and_backtests_still_run():
    p = SyntheticProvider(CFG)
    assert p.as_traded_closes(Instrument.parse("AAPL"), pd.bdate_range("2024-01-01", periods=5)) is None
    rep = run_agent_backtest("AAPL", "2024-01-02", "2024-02-29", make_config(CFG, costs={"impact_coeff": 1.0}), 10)
    assert rep.results[AGENT].impact_paid >= 0.0


# ------------------------------------------------------------------ sizing and news rules
def test_aggressive_stance_scales_with_volatility_so_the_blended_book_is_a_vol_target():
    from agentic_trader.agents.risk import RiskAnalyst
    f = {"proposed_weight": 1.0, "max_position": 1.0, "target_vol": 0.15, "max_var_95": 0.0,
         "realized_vol_20d_annual": None, "drawdown_from_60d_high": 0.0, "var_95_1d": 0.02,
         "var_95_1d_short": 0.02, "cvar_95_1d": 0.03}
    weights = {}
    for vol in (0.10, 0.20, 0.40, 0.80):
        f["realized_vol_20d_annual"] = vol
        agg = RiskAnalyst(None, CFG, "aggressive").rules_weight(f)
        neu = RiskAnalyst(None, CFG, "neutral").rules_weight(f)
        weights[vol] = (agg, neu)
    assert weights[0.10] == (1.0, 1.0)                                   # both capped
    for vol in (0.20, 0.40, 0.80):
        agg, neu = weights[vol]
        assert agg == pytest.approx(min(1.0, 1.25 * neu)) and neu == pytest.approx(min(1.0, 0.15 / vol))
    old = make_config(CFG, risk={"aggressive_vol_scaled": False})
    f["realized_vol_20d_annual"] = 0.80
    assert RiskAnalyst(None, old, "aggressive").rules_weight(f) == 1.0    # the v0.8 rule: pinned at the cap
    assert RULES_V02["risk"]["aggressive_vol_scaled"] is False and RULES_V02["rules"]["news_tone_mass"] is False


def test_news_analyst_abstains_when_the_headlines_carry_no_tone():
    from agentic_trader.agents.analysts import NewsAnalyst
    from agentic_trader.data.base import NewsItem

    class Flat(SyntheticProvider):
        def news(self, instrument, as_of, lookback_days):
            return [NewsItem(published=as_of, headline=f"Quarterly report filed {i}", source="SEC EDGAR",
                             summary="", sentiment=0.0, tags=["10-Q"]) for i in range(7)]

    from agentic_trader.graph import TradingGraph
    g = TradingGraph(CFG, provider=Flat(CFG))
    rep = NewsAnalyst(None, CFG).run(g.prepare("AAPL", date(2024, 3, 1)), g.provider)
    assert rep.abstained and rep.confidence <= 0.2
    old = make_config(CFG, rules={"news_tone_mass": False})
    g2 = TradingGraph(old, provider=Flat(old))
    rep2 = NewsAnalyst(None, old).run(g2.prepare("AAPL", date(2024, 3, 1)), g2.provider)
    assert not rep2.abstained and rep2.confidence == pytest.approx(0.55)   # 0.2 + 0.05 x 7, the v0.8 rule


# ------------------------------------------------------------------ trials registry
def test_trials_registry_counts_the_v09_v010_and_v011_variants():
    versions = [t.version for t in TRIALS]
    assert versions.count("v0.9") == 10 and versions.count("v0.10") == 5 and versions.count("v0.11") == 3
    assert all(t.overrides is None and t.recorded_portfolio_sharpe is not None for t in TRIALS if t.version in ("v0.9", "v0.10"))
    assert len({t.name for t in TRIALS}) == len(TRIALS) == 44
    for t in TRIALS:
        if t.version == "v0.11":
            make_config(t.overrides)
