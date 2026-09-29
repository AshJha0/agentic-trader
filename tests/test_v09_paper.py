"""v0.9 phase 4: the daily paper-trading record recomputes from the freeze date, on synthetic data."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd


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
    assert len(runs) == 2 and runs[1]["revisions"] == {} and runs[1]["provenance"]["version"]
    # a revised return in the ledger is reported, not hidden
    tampered = second.copy(); tampered.iloc[3, 0] += 0.01
    rev = mod.revisions(tampered, second)
    assert list(rev) == [second.columns[0]] and abs(rev[second.columns[0]] - 0.01) < 1e-9
    assert np.isfinite(second["rf"]).all()
