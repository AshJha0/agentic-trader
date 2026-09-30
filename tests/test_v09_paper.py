"""v0.9 phase 4: the daily paper-trading record recomputes from the freeze date, on synthetic data."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def _paper():
    path = Path(__file__).resolve().parents[1] / "scripts" / "paper_trade_v09.py"
    spec = importlib.util.spec_from_file_location("paper_trade_v09", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_paper_record_is_recomputed_appended_and_revisions_are_logged(tmp_path):
    mod = _paper()
    out = tmp_path / "paper"
    assert mod.main(["--data", "synthetic", "--freeze", "2024-01-02", "--as-of", "2023-12-29", "--out", str(out)]) == 0
    assert not (out / "ledger.csv").exists()                      # before the freeze: nothing recorded
    # on the freeze session itself there is one bar and no return yet: a clean no-op, not a crash
    assert mod.main(["--data", "synthetic", "--freeze", "2024-01-02", "--as-of", "2024-01-02", "--out", str(out)]) == 0
    assert not (out / "ledger.csv").exists()
    assert mod.main(["--data", "synthetic", "--freeze", "2024-01-02", "--as-of", "2024-02-15", "--out", str(out)]) == 0
    first = pd.read_csv(out / "ledger.csv", index_col=0, parse_dates=True)
    cols = {"core15/AgenticTrader", "core15/B&H vol-target", "core15/Buy&Hold", "etf11/B&H vol-target",
            "etf11/TSMOM(12-1)", "fx15/Carry", "fx15/TSMOM(12-1)", "rf"}
    assert cols <= set(first.columns) and first.index[0].date().isoformat() == "2024-01-02"
    assert 25 <= len(first) <= 35
    text = (out / "summary.md").read_text(encoding="utf-8")
    assert "interval after 60 sessions" in text and "core15/AgenticTrader" in text
    # the next day extends the record; earlier rows are unchanged on deterministic data
    assert mod.main(["--data", "synthetic", "--freeze", "2024-01-02", "--as-of", "2024-02-16", "--out", str(out)]) == 0
    second = pd.read_csv(out / "ledger.csv", index_col=0, parse_dates=True)
    assert len(second) == len(first) + 1
    pd.testing.assert_frame_equal(second.loc[first.index], first)
    runs = [json.loads(l) for l in (out / "runs.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(runs) == 2 and runs[1]["revisions"] == {} and runs[1]["dropped"] == [] and runs[1]["appended"] == 1
    assert runs[1]["provenance"]["version"] and (out / "ledger_recomputed.csv").exists()
    assert not (out / "revisions.csv").exists()
    # a revised return is reported (column, date, cells) and a dropped session is named
    tampered = second.copy(); tampered.iloc[3, 0] += 0.01
    rev = mod.revisions(tampered, second)
    col = second.columns[0]
    assert list(rev["changed"]) == [col] and abs(rev["changed"][col]["max_abs"] - 0.01) < 1e-9
    assert rev["changed"][col]["date"] == second.index[3].date().isoformat() and len(rev["cells"]) == 1
    assert mod.revisions(second, second.drop(second.index[10]))["dropped"] == [second.index[10].date().isoformat()]
    assert np.isfinite(second["rf"]).all()


def test_ledger_is_append_only_and_a_revised_recomputation_is_logged_not_absorbed(tmp_path, monkeypatch):
    mod = _paper()
    out = tmp_path / "paper"
    assert mod.main(["--data", "synthetic", "--freeze", "2024-01-02", "--as-of", "2024-02-15", "--out", str(out)]) == 0
    first = pd.read_csv(out / "ledger.csv", index_col=0, parse_dates=True)
    real = mod.recompute

    def shifted(as_of, cfg, provider, freeze):
        f = real(as_of, cfg, provider, freeze)
        f.iloc[5, 0] += 0.005                                          # a restated return on an old session
        return f

    monkeypatch.setattr(mod, "recompute", shifted)
    assert mod.main(["--data", "synthetic", "--freeze", "2024-01-02", "--as-of", "2024-02-16", "--out", str(out)]) == 0
    led = pd.read_csv(out / "ledger.csv", index_col=0, parse_dates=True)
    pd.testing.assert_frame_equal(led.loc[first.index], first)          # the ledger kept its rows
    assert len(led) == len(first) + 1
    rec = pd.read_csv(out / "ledger_recomputed.csv", index_col=0, parse_dates=True)
    assert abs(rec.iloc[5, 0] - first.iloc[5, 0] - 0.005) < 1e-12
    revs = pd.read_csv(out / "revisions.csv")
    assert len(revs) == 1 and revs.loc[0, "column"] == first.columns[0]
    runs = [json.loads(l) for l in (out / "runs.jsonl").read_text(encoding="utf-8").splitlines()]
    assert list(runs[-1]["revisions"]) == [first.columns[0]]
    # a recomputation that ends before the ledger is refused
    with pytest.raises(SystemExit, match="shrink"):
        mod.main(["--data", "synthetic", "--freeze", "2024-01-02", "--as-of", "2024-02-10", "--out", str(out)])
    assert mod.main(["--data", "synthetic", "--freeze", "2024-01-02", "--as-of", "2024-02-10", "--out", str(out),
                     "--allow-shrink"]) == 0


def test_a_truncated_sleeve_is_a_failure_not_a_no_op(tmp_path, monkeypatch):
    mod = _paper()
    from agentic_trader.data import SyntheticProvider

    class Truncated(SyntheticProvider):
        def history(self, instrument, start, end):
            h = super().history(instrument, start, end)
            return h[h.index <= pd.Timestamp("2024-01-19")] if instrument.symbol == "TLT" else h

    monkeypatch.setattr(mod, "get_provider", lambda cfg: Truncated(cfg))
    with pytest.raises(ValueError, match="TLT"):
        mod.main(["--data", "synthetic", "--freeze", "2024-01-02", "--as-of", "2024-02-15", "--out", str(tmp_path / "p")])
