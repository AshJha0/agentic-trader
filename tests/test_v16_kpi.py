"""PLAN 6.4: KPI table on fixture records (offline, no model calls)."""

import json
from pathlib import Path

import pytest

from agentic_trader.cli import main
from agentic_trader.kpi import KPIRecord, brier, calibration_bins, hit_rate, kpi_table, load_records, sharpe

FIX = Path(__file__).parent / "fixtures" / "kpi_records.jsonl"


def test_hit_rate_ignores_flat_views():
    assert hit_rate([1, -1, 0], [0.1, 0.1, 0.1]) == (0.5, 2)
    assert hit_rate([0], [1]) == (None, 0)


def test_brier_and_bins():
    assert brier([1.0, 0.0], [0.1, -0.1]) == 0.0
    assert brier([0.5], [0.1]) == pytest.approx(0.25)
    rows = calibration_bins([0.05, 0.95, 1.0], [-1, 1, 1], bins=10)
    assert [r["n"] for r in rows] == [1, 2] and rows[1]["freq_up"] == 1.0
    with pytest.raises(ValueError):
        calibration_bins([0.5], [1], bins=0)


def test_sharpe_degenerate():
    assert sharpe([0.01]) is None and sharpe([0.01, 0.01]) is None


def test_worked_example_from_docstring():
    recs = [KPIRecord("d", "A", 1, -1, 0.02), KPIRecord("d", "B", 1, 1, -0.01)]
    t = kpi_table(recs)
    assert t["hit_rate_model"] == 0.5 and t["hit_rate_control"] == 0.0
    assert t["delta_book_total"] == pytest.approx(0.04)
    assert t["brier"] is None and t["calibration"] == []


def test_fixture_table():
    t = kpi_table(load_records(FIX))
    assert t["n_records"] == 4 and t["n_dates"] == 2
    assert t["hit_rate_model"] == pytest.approx(2 / 3)
    assert t["hit_rate_control"] == pytest.approx(1 / 4)
    # date 1: 2*0.02 + 0 = 0.04; date 2: (-1)(-0.03) + (-1)(0.01) = 0.02
    assert t["delta_book_total"] == pytest.approx(0.06)
    assert t["cost_per_decision_usd"] == pytest.approx(0.01)
    assert t["brier"] == pytest.approx((0.04 + 0.36 + 0.09 + 0.25) / 4)
    assert t["agent_sources"] == {"llm": 4, "rules": 2}


def test_validation():
    with pytest.raises(ValueError):
        KPIRecord.from_dict({"as_of": "d", "symbol": "A"})
    with pytest.raises(ValueError):
        KPIRecord.from_dict(
            {"as_of": "d", "symbol": "A", "model_signal": 1, "rule_signal": 0, "outcome_return": 0.1, "prob_up": 1.5}
        )
    with pytest.raises(ValueError):
        kpi_table([])


def test_cli(capsys):
    assert main(["kpi", str(FIX)], dotenv=False) == 0
    out = capsys.readouterr().out
    assert "hit rate, model" in out and "Sharpe, model book" in out
    assert main(["kpi", str(FIX), "--json"], dotenv=False) == 0
    assert json.loads(capsys.readouterr().out)["n_records"] == 4
