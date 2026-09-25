"""Default configuration. Copy and override with ``make_config(**overrides)``."""
from __future__ import annotations

import copy
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    # ---- LLM ---------------------------------------------------------------
    # "offline": every agent uses its deterministic rule-based reasoning (no API key needed).
    # "anthropic": agents reason with Claude; rule-based output is the fallback on any error.
    "llm_provider": "offline",
    "deep_think_llm": "claude-opus-5",      # researchers, facilitator, trader, risk team, PM
    "quick_think_llm": "claude-haiku-4-5",  # analysts summarising tool output
    "deep_effort": "high",
    "quick_effort": "low",
    "max_tokens": 16000,
    # Server-side refusal fallback for claude-opus-5 / claude-fable-5-1 (beta).
    "use_refusal_fallback": True,
    "llm_timeout_s": 300,   # per request; adaptive thinking on the deep tier can take minutes
    "max_llm_calls": None,  # hard cap per TradingGraph (None = unlimited); beyond it agents use rules

    # ---- Workflow ------------------------------------------------------------
    "analysts": None,  # None -> default set per asset class (see graph.DEFAULT_ANALYSTS)
    "max_debate_rounds": 2,
    "max_risk_discuss_rounds": 1,
    "analyst_weights": {
        "technical": 1.0, "fundamentals": 1.0, "macro": 1.0, "news": 0.7, "sentiment": 0.5,
    },
    "decision_threshold": 0.10,  # |consensus score| below this -> no directional view
    # Rule-based reasoning switches. Each is a separately measured change; the
    # defaults were chosen on the 2016-2021 design period only (ablation in
    # docs/evaluation/evaluation.md). None of these three improved risk-adjusted
    # returns there, so they are off; they stay available for research.
    "rules": {
        "tsmom": False,                    # 12-1 month time-series momentum in the technical view
        "trend_filtered_reversal": False,  # RSI/Bollinger fades only when not fighting the 200d trend
        "abstain_without_data": False,     # analysts with no data do not vote in the consensus
    },

    # ---- Data ----------------------------------------------------------------
    "data_provider": "synthetic",  # "synthetic" | "yahoo" | "csv"
    "csv_dir": "data",
    "lookback_days": 400,          # calendar days of history handed to analysts
    "max_data_staleness_days": 7,  # refuse to decide if the latest bar is older than this
    "news_lookback_days": 7,
    "synthetic_seed": 7,

    # ---- Risk limits (enforced by the Portfolio Manager after any LLM output) --
    "risk": {
        "max_position": 1.0,       # |target weight| cap (1.0 = 100% of equity notional)
        "target_vol": 0.15,        # annualised vol target used by the neutral risk analyst
        "max_var_95": 0.02,        # cap on 1-day 95% historical VaR of the position
        "min_trade_weight": 0.05,  # smaller targets are rounded to flat
        "rebalance_band": 0.10,    # keep the current position if the new target is within this
                                   # distance of it (a no-trade band; 0 disables)
        # Strategic (benchmark) weight per asset class: the position held with no
        # directional view; conviction tilts around it. Equities default to fully
        # invested (they carry a risk premium); FX to flat. v0.2 used 0 for both.
        "neutral_weight": {"equity": 1.0, "fx": 0.0},
        "allow_short_equity": False,
        "allow_short_fx": True,
        "stop_atr_mult": 2.0,
        "take_profit_atr_mult": 3.0,
    },

    # ---- Costs / backtest ----------------------------------------------------
    "costs": {
        "equity_cost_bps": 1.0,
        "equity_slippage_bps": 1.0,
        "equity_borrow_annual": 0.01,
        "fx_spread_pips": 0.8,
        "fx_slippage_bps": 0.2,
    },
    "initial_capital": 100_000.0,
    "risk_free_annual": 0.0,
    "backtest": {
        "use_stops": False,  # enforce the decision's stop-loss / take-profit intraday
    },

    # ---- FX macro inputs -----------------------------------------------------
    # "auto": synthetic data uses the static table below; real data (yahoo, csv) uses
    #         point-in-time FRED rates, falling back to the static table only for dates
    #         within static_macro_max_age_days of today.
    # "static" / "fred": force one source.
    "fx_macro_source": "auto",
    "static_macro_max_age_days": 180,
    # Illustrative policy-rate / CPI levels (percent), roughly mid-2025. NOT live data.
    "fx_policy_rates": {
        "USD": 4.25, "EUR": 2.00, "GBP": 4.00, "JPY": 0.50, "CHF": 0.00,
        "AUD": 3.60, "CAD": 2.75, "NZD": 3.00, "SEK": 2.00, "NOK": 4.25,
    },
    "fx_inflation": {
        "USD": 2.7, "EUR": 2.0, "GBP": 3.6, "JPY": 3.0, "CHF": 0.1,
        "AUD": 2.1, "CAD": 1.7, "NZD": 2.7, "SEK": 0.8, "NOK": 3.0,
    },

    # ---- Output --------------------------------------------------------------
    "results_dir": "results",
    "memory_path": "results/memory.jsonl",  # None -> in-memory only
    "save_reports": False,
}


def _merge(base: dict, over: dict) -> dict:
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


# Settings that reproduce v0.2 rule behaviour, for before/after comparisons.
RULES_V02: dict[str, Any] = {
    "rules": {"tsmom": False, "trend_filtered_reversal": False, "abstain_without_data": False},
    "risk": {"rebalance_band": 0.0, "neutral_weight": {"equity": 0.0, "fx": 0.0}},
    "backtest": {"use_stops": False},
}


def make_config(overrides: dict | None = None, **kw) -> dict[str, Any]:
    """Deep-copy DEFAULT_CONFIG and deep-merge overrides into it."""
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if overrides:
        _merge(cfg, copy.deepcopy(overrides))
    if kw:
        _merge(cfg, copy.deepcopy(kw))
    return cfg
