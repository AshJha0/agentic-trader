"""v0.17 R0.5 (review Appendix B A2): one VaR method default shared by the desk config and the
risk_model functions. Regression: risk_model defaulted to "fhs" while config used "ewma"."""

from __future__ import annotations

import inspect

import numpy as np

from agentic_trader import risk_model as rm
from agentic_trader.config import DEFAULT_CONFIG, DEFAULT_VAR_METHOD


def test_config_and_function_defaults_agree() -> None:
    assert DEFAULT_VAR_METHOD == "ewma"  # owner decision 2026-11-07
    assert DEFAULT_CONFIG["risk"]["book_var_method"] == DEFAULT_VAR_METHOD
    for fn in (rm.var_forecast, rm.var_next):
        assert inspect.signature(fn).parameters["method"].default == DEFAULT_VAR_METHOD, fn.__name__


def test_direct_caller_gets_the_desk_method() -> None:
    r = np.random.default_rng(0).normal(0, 0.01, 400)
    assert rm.var_next(r) == rm.var_next(r, DEFAULT_CONFIG["risk"]["book_var_method"])
    np.testing.assert_array_equal(rm.var_forecast(r), rm.var_forecast(r, "ewma"))
