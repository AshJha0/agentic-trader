"""Suite-wide fixtures."""

import os

import pytest


@pytest.fixture(autouse=True)
def _restore_environ():
    """Snapshot ``os.environ`` before every test and restore it afterwards, so a test that
    sets, pops or forgets a variable (a backend switch, a probe read from a .env file, an
    API key) cannot leak it into the tests that run after it."""
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)


@pytest.fixture(autouse=True)
def _replay_allowlist_in_tmp(tmp_path_factory, monkeypatch):
    """Replay recordings saved by tests list their digests in a per-test temporary allowlist,
    never in the user's ~/.agentic_trader/replay_allowlist.txt."""
    monkeypatch.setenv("AGENTIC_TRADER_REPLAY_ALLOWLIST", str(tmp_path_factory.mktemp("replay_allow") / "allowlist.txt"))


# The slowest tests (about 10 s or more each in `pytest --durations=40`, measured 2026-11-07
# on the owner's laptop). The PR gate runs `-m "not slow"`; nightly.yml runs them. Kept in
# one list so what the gate skips is reviewable at a glance.
SLOW = {
    "tests/test_v08_alpha.py::test_alpha_analyst_gate_is_a_five_percent_test_on_pure_noise",
    "tests/test_services.py::test_mcp_stdio_round_trip_and_remote_registry",
    "tests/test_v05.py::test_xalpha_report_and_snapshot",
    "tests/test_llm_eval.py::test_parallel_evaluation_matches_sequential",
    "tests/test_v08_agentic.py::test_mcp_server_routes_every_call_through_policy_approval_and_evidence",
    "tests/test_v05.py::test_xalpha_tool_and_cli",
    "tests/test_services.py::test_cli_task_tools_and_research_commands",
    "tests/test_agentic.py::test_harness_is_usable_from_threads",
    "tests/test_v06.py::test_xalpha_analyst_ranks_within_its_universe",
    "tests/test_agentic.py::test_harness_awaits_approval_then_resumes_or_cancels",
    "tests/test_v08_agentic.py::test_stdio_session_serves_calls_concurrently_so_an_abandoned_call_does_not_block_the_next",
    "tests/test_v08_agentic.py::test_remote_tools_are_classified_fail_closed_whatever_the_server_claims",
    "tests/test_v05.py::test_portfolio_backtest_with_class_budgets",
    "tests/test_v08_agentic.py::test_interrupted_sweep_spares_a_live_siblings_runs",
    "tests/test_v09_paper.py::test_paper_record_is_recomputed_appended_and_revisions_are_logged",
}


def pytest_collection_modifyitems(config, items):
    for item in items:
        if item.nodeid.split("[", 1)[0] in SLOW:
            item.add_marker(pytest.mark.slow)
