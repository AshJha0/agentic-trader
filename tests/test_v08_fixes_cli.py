"""Post-v0.8 verification fixes, cli-llm-misc cluster: ``--ac-kappa`` must be finite (finding
32), the execute ticket's unfilled clause and the credited-carry line count what the
simulator / backtester actually did (31, 32, 89), ``UsageTracker`` reads its dict under the
lock and an unknown effort is a configuration error (13), ``git_info`` is not cached (56),
``evaluate`` records the macro-source tally (15), and the prompt registry hashes the fence
tag and the anonymiser's allow-lists (40). Every test here fails on release/v0.8.0 c2619d2."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import threading
import time
import types
from datetime import date
from types import SimpleNamespace

import numpy as np
import pytest

from agentic_trader import Instrument, make_config, quant
from agentic_trader import provenance as prov_mod
from agentic_trader.cli import main
from agentic_trader.cli.common import _config
from agentic_trader.cli.parser import build_parser
from agentic_trader.cli.research import carry_summary
from agentic_trader.data import SyntheticProvider
from agentic_trader.evaluation import evaluate
from agentic_trader.llm import EFFORT_LEVELS, AnthropicLLM, BudgetedLLM, UsageTracker, request_shape
from agentic_trader.prompts import prompt_bundle_hash, prompt_registry, shared_prompt_constants

CFG = make_config(memory_path=None)
EXECUTE = ["execute", "AAPL", "--date", "2024-03-01", "--target", "0.5"]
BASELINES = ["baselines", "AAPL", "--start", "2024-01-02", "--end", "2024-02-29", "--execution-algo", "ac"]


# ------------------------------------------------------------ (a) finding 32: --ac-kappa
@pytest.mark.parametrize("bad", ["inf", "-inf", "nan", "-1"])
def test_ac_kappa_must_be_finite_and_non_negative(bad, capsys):
    assert main(EXECUTE + ["--algo", "ac", f"--ac-kappa={bad}"]) == 2     # '=' so argparse takes '-1'
    assert "--ac-kappa must be finite and >= 0" in capsys.readouterr().err
    assert main(BASELINES + [f"--ac-kappa={bad}"]) == 2
    assert "--ac-kappa must be finite and >= 0" in capsys.readouterr().err


def test_ac_kappa_zero_and_positive_still_pass_through():
    assert _config(build_parser().parse_args(EXECUTE + ["--ac-kappa", "0"]))["costs"]["ac_kappa"] == 0.0
    assert _config(build_parser().parse_args(BASELINES + ["--ac-kappa", "8"]))["costs"]["ac_kappa"] == 8.0


# ------------------------------------------------- (b) findings 31/32: the unfilled clause
def test_execute_prints_no_unfilled_clause_for_a_complete_fill(capsys):
    # The closed-form AC schedule sums to Q - 3e-14: not an unfilled share.
    assert main(EXECUTE + ["--algo", "ac"]) == 0
    out = capsys.readouterr().out
    assert "(100%)" in out and "unfilled" not in out
    assert re.search(r"\(spread [\d.]+ bps, impact [\d.]+ bps\)", out)


def test_execute_still_reports_a_real_unfilled_remainder(capsys):
    assert main(["execute", "EURUSD", "--date", "2024-03-01", "--target", "0.5", "--algo", "pov",
                 "--participation", "0.001"]) == 0
    out = capsys.readouterr().out
    assert re.search(r"opportunity cost of [\d,]+ unfilled [+-][\d.]+ bps", out)


# --------------------------------------------- (b) finding 89: carry over accruing bars only
def test_carry_summary_counts_only_the_bars_that_accrue():
    T = 63
    carry = np.array([0.0325] * 36 + [np.nan] * 27)
    line = carry_summary(carry, 0.0)
    assert line == ("carry +1.89% p.a. credited (+3.25% on 36/62 accruing bars, "
                    "0 on 26 with no point-in-time rate)")
    # ... and that is what the backtester credits: flat prices, full weight, no costs.
    bt = quant.BacktestConfig(cost_bps=0.0, slippage_bps=0.0, periods_per_year=252, allow_short=True)
    res = quant.run_backtest(np.ones(T), np.ones(T), bt, carry=carry)
    credited = res.returns[1:]                                   # bar t's carry lands in returns[t + 1]
    assert int((credited != 0).sum()) == 36 and int((credited == 0).sum()) == 26
    printed = float(re.match(r"carry ([+-][\d.]+)%", line).group(1)) / 100
    assert printed == pytest.approx(36 * 0.0325 / 62, abs=5e-5)
    assert printed == pytest.approx(np.mean(credited) * 252, rel=0.01)   # compounding drifts w below 1
    # a rate known only on the final bar credits nothing
    tail_only = np.array([np.nan] * 62 + [0.0325])
    assert carry_summary(tail_only, 0.0) == \
        "carry +0.00% p.a. credited (62/62 accruing bars with no point-in-time rate)"
    res = quant.run_backtest(np.ones(T), np.ones(T), bt, carry=tail_only)
    assert res.metrics.cumulative_return == pytest.approx(0.0, abs=1e-12)
    assert carry_summary(np.full(T, 0.0325), 0.0) == "carry +3.25% p.a. credited (point-in-time, all 62 accruing bars)"
    assert carry_summary(np.full(1, 0.0325), 0.0) == "carry +0.00% p.a. credited (point-in-time, all 0 accruing bars)"
    assert carry_summary(None, 0.0252) == "carry +2.52% p.a."


# -------------------------------------------------------- (c) finding 13: UsageTracker lock
class _LockedDict(dict):
    """A ``by_model`` that refuses to be iterated unless the tracker's lock is held."""

    def __init__(self, tracker):
        super().__init__()
        self._tracker = tracker

    def _check(self):
        assert self._tracker._lock.locked(), "by_model iterated without the tracker lock"

    def items(self):
        self._check()
        return super().items()

    def values(self):
        self._check()
        return super().values()


def test_usage_tracker_reads_by_model_under_its_lock():
    tr = UsageTracker()
    tr.by_model = _LockedDict(tr)
    tr.add("claude-opus-5", SimpleNamespace(input_tokens=1000, output_tokens=100))
    tr.add("some-beta-alias", SimpleNamespace(input_tokens=10, output_tokens=1))
    assert tr.calls == 2
    assert tr.cost_usd == pytest.approx((1000 * 5 + 100 * 25) / 1e6)
    assert tr.unpriced_models == ["some-beta-alias"]
    s = tr.summary()
    assert s["calls"] == 2 and s["unpriced_models"] == ["some-beta-alias"] and set(s["by_model"]) == {
        "claude-opus-5", "some-beta-alias"}
    b = BudgetedLLM(SimpleNamespace(usage=tr, complete=lambda *a, **k: "x"), max_cost_usd=1e9)
    assert b.exhausted                       # unpriced -> fail closed, read under the lock
    assert not tr._lock.locked()             # nothing left holding it


def test_usage_tracker_survives_inserts_while_a_budget_check_iterates():
    # 50000 new ids against a reader paced at 1ms: the unlocked v0.8.0 reads raised on 10/10 runs.
    n_keys = 50000
    tr = UsageTracker()
    b = BudgetedLLM(SimpleNamespace(usage=tr, complete=lambda *a, **k: "x"), max_cost_usd=1e9)
    errors, done = [], threading.Event()

    def adder():                             # every add inserts a new served id
        for i in range(n_keys):
            tr.add(f"claude-opus-5-{i:08d}", SimpleNamespace(input_tokens=1, output_tokens=1))
        done.set()

    def reader():                            # each read walks the growing dict
        try:
            while not done.is_set():
                b.exhausted
                tr.cost_usd
                tr.calls
                time.sleep(0.001)
        except RuntimeError as e:            # "dictionary changed size during iteration"
            errors.append(str(e))

    threads = [threading.Thread(target=adder), threading.Thread(target=reader)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    assert errors == [] and tr.calls == n_keys


# ------------------------------------------------- (c) finding 13: effort is validated early
def _fake_anthropic(monkeypatch):
    fake = types.ModuleType("anthropic")
    fake.Anthropic = lambda **kw: SimpleNamespace(messages=None, beta=None)
    monkeypatch.setitem(sys.modules, "anthropic", fake)


@pytest.mark.parametrize("key", ["deep_effort", "quick_effort"])
def test_effort_outside_levels_is_rejected_at_construction(monkeypatch, key):
    _fake_anthropic(monkeypatch)
    cfg = make_config(llm_provider="anthropic", **{key: "extreme"})
    with pytest.raises(ValueError, match=rf"{key}: effort must be one of .*'extreme'"):
        AnthropicLLM(cfg)
    AnthropicLLM(make_config(llm_provider="anthropic"))      # the defaults are valid


def test_request_shape_rejects_an_unknown_effort_instead_of_sending_high():
    with pytest.raises(ValueError, match="effort must be one of"):
        request_shape("claude-opus-5", "extreme", 100)
    with pytest.raises(ValueError):
        request_shape("claude-opus-5", None, 100)
    for e in EFFORT_LEVELS:
        assert request_shape("claude-opus-5", e, 100)["output_config"] == {"effort": e}
    assert request_shape("claude-opus-4-6", "xhigh", 100)["output_config"] == {"effort": "high"}   # lowered, logged


# ----------------------------------------------------------- (d) finding 56: git_info is live
def _git(repo, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
                           "-c", "commit.gpgsign=false", *args], cwd=repo, capture_output=True, text=True,
                          check=True).stdout.strip()


def test_git_info_reflects_the_tree_at_each_call(tmp_path, monkeypatch):
    if not shutil.which("git"):
        pytest.skip("git not installed")
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    f = repo / "a.txt"
    f.write_text("one\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "one")
    sha1 = _git(repo, "rev-parse", "HEAD")
    assert prov_mod.git_info(str(repo)) == (sha1, False)
    f.write_text("two\n", encoding="utf-8")
    assert prov_mod.git_info(str(repo)) == (sha1, True)          # the same process sees the edit
    _git(repo, "commit", "-q", "-am", "two")
    sha2 = _git(repo, "rev-parse", "HEAD")
    assert sha2 != sha1 and prov_mod.git_info(str(repo)) == (sha2, False)
    # provenance() stamps the state at write time, not at first call
    monkeypatch.setattr(prov_mod, "_ROOT", repo)
    assert prov_mod.provenance()["git_commit"] == sha2 and prov_mod.provenance()["git_dirty"] is False
    f.write_text("three\n", encoding="utf-8")
    assert prov_mod.provenance()["git_dirty"] is True
    _git(repo, "commit", "-q", "-am", "three")
    assert prov_mod.provenance()["git_commit"] == _git(repo, "rev-parse", "HEAD") != sha2


# ---------------------------------------------------- (e) finding 15: macro sources in meta
def test_evaluate_records_this_runs_macro_sources():
    provider = SyntheticProvider(CFG)
    provider.macro(Instrument.parse("EURUSD"), date(2024, 1, 2))      # a stale tally from before the run
    res = evaluate(["USDJPY"], {"q": ("2024-01-02", "2024-01-31")}, CFG, rebalance_every=10, provider=provider)
    ms = res.meta["macro_sources"]
    assert set(ms) == {"static"} and ms["static"] >= 2 and ms == provider.macro_sources
    json.dumps(res.meta)
    # equities never ask for macro, and the tally is reset at the start of every run
    res = evaluate(["AAPL"], {"q": ("2024-01-02", "2024-01-31")}, CFG, rebalance_every=10, provider=provider)
    assert res.meta["macro_sources"] == {} and provider.macro_sources == {}


# ------------------------------------------- (f) finding 40: fence tag and allow-lists hashed
def test_prompt_registry_hashes_the_fence_tag_and_the_anonymizer_key_sets(monkeypatch):
    import agentic_trader.anonymize as anon
    import agentic_trader.state as state_mod
    reg = prompt_registry(CFG)
    before = reg["bundle"]
    assert prompt_registry(CFG) == reg                           # stable across calls
    assert set(shared_prompt_constants()) == {"state._TAG", "anonymize.PRICE_KEYS", "anonymize.SCALE_FREE_KEYS",
                                              "anonymize._SCALE_FREE_SUFFIXES", "anonymize._SCALE_FREE_PREFIXES",
                                              "anonymize._ISO_DATE"}

    monkeypatch.setattr(anon, "SCALE_FREE_KEYS", anon.SCALE_FREE_KEYS | {"phantom_ratio_key"})
    with_key = prompt_bundle_hash(CFG)
    assert with_key != before
    monkeypatch.undo()
    assert prompt_bundle_hash(CFG) == before

    monkeypatch.setattr(anon, "PRICE_KEYS", anon.PRICE_KEYS - {"close"})
    assert prompt_bundle_hash(CFG) not in (before, with_key)
    monkeypatch.undo()

    monkeypatch.setattr(state_mod, "_TAG", "external_text")
    assert prompt_bundle_hash(CFG) not in (before, with_key)
    monkeypatch.undo()
    assert prompt_bundle_hash(CFG) == before


def test_prompts_docstring_states_the_hashed_sources_and_the_gaps():
    import agentic_trader.prompts as pm
    doc = pm.__doc__
    assert "shared_prompt_code()" in doc and "shared_prompt_constants()" in doc
    assert "Nothing else is covered" in doc and "agentic/critic.py" in doc
    assert "anywhere in the prompt-building code" not in doc
