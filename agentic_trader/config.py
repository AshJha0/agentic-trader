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
    # Attempts after the first for a request that timed out, was rate limited, hit a 5xx or lost
    # its connection. AnthropicLLM runs the retry loop itself (the SDK client makes none), so a
    # timed-out attempt is billed at its estimated maximum whether or not a later attempt succeeds.
    "llm_max_retries": 2,
    # Delay before the first retry; doubles per attempt, capped at 8 s, jittered. A retry-after /
    # retry-after-ms header on a rate limit or overload is honoured instead (up to 60 s).
    "llm_retry_backoff_s": 0.5,
    # How max_llm_cost_usd is enforced. "hard": every call reserves its maximum possible cost
    # (the input estimate plus max_tokens of reply) before it is dispatched and a timed-out
    # attempt is billed at that maximum, so parallel workers can never overshoot the cap; a
    # call the remaining cap cannot afford at that size is refused. "estimate": each call
    # reserves the input estimate plus llm_reserve_output_tokens (a realistic reply), which
    # admits more concurrent calls but makes the cap soft: spend can exceed it by up to the
    # number of calls in flight times (max_tokens - llm_reserve_output_tokens) at list price.
    "llm_budget_mode": "hard",
    # Output tokens reserved per call under max_llm_cost_usd in "estimate" mode (a timed-out
    # attempt is still billed at max_tokens).
    "llm_reserve_output_tokens": 2000,
    "max_llm_calls": None,  # hard cap per TradingGraph (None = unlimited); beyond it agents use rules
    "max_llm_cost_usd": None,  # cap on estimated spend (list prices; see llm_budget_mode); beyond it agents use rules
    # Hide ticker, calendar and price level from the model (anonymize.py). Use it for
    # any backtest inside the model's training period: otherwise the model can recall
    # what happened next instead of reasoning from the data.
    "llm_anonymize": False,

    # ---- Workflow ------------------------------------------------------------
    "analysts": None,  # None -> default set per asset class (see graph.DEFAULT_ANALYSTS)
    "max_debate_rounds": 2,
    "max_risk_discuss_rounds": 1,
    "analyst_weights": {
        "technical": 1.0, "fundamentals": 1.0, "macro": 1.0, "news": 0.7, "sentiment": 0.5,
        "alpha": 1.0, "xalpha": 1.0,
    },
    # Peer universe for the cross-sectional alpha analyst (None -> the core universe of the
    # instrument's asset class). The instrument itself is always included.
    "xalpha_universe": None,
    "decision_threshold": 0.10,  # |consensus score| below this -> no directional view
    # Rule-based reasoning switches. Each is a separately measured change; the
    # defaults were chosen on the 2016-2021 design period only (ablation in
    # docs/evaluation/evaluation.md). None of these three improved risk-adjusted
    # returns there, so they are off; they stay available for research.
    "rules": {
        "tsmom": False,                    # 12-1 month time-series momentum in the technical view
        "trend_filtered_reversal": False,  # RSI/Bollinger fades only when not fighting the 200d trend
        "abstain_without_data": False,     # analysts with no data do not vote in the consensus
        # v0.5.1: the FX analogue of the equity strategic weight. Chosen on the core FX pairs'
        # design period (mean Sharpe -0.03 -> +0.11) and then judged on data no choice had
        # touched, where it improved every slice (extended crosses design -0.24 -> -0.15,
        # holdout +0.12 -> +0.31, reserve -0.63 -> +0.22). RULES_V03 turns it off.
        "fx_carry_neutral": True,          # FX strategic weight = point-in-time carry / scale, capped
        # v0.8: the trader's 0.75x size cut when memory's hit rate over the last >= 5 resolved
        # calls is below 40%. On in every published backtest so far (never measured
        # separately); the switch exists so the docs pass can measure it on the design period.
        "track_record_cut": True,
    },

    # ---- Data ----------------------------------------------------------------
    "data_provider": "synthetic",  # "synthetic" | "yahoo" | "csv"
    "csv_dir": "data",
    "lookback_days": 400,          # calendar days of history handed to analysts and desk tools
    # The alpha library's window (the alpha analyst and the quant.alpha / quant.xalpha
    # tools). Longer than lookback_days because IC needs hundreds of forward returns
    # after a 273-day signal (tsmom_12_1) has produced its first value.
    "alpha_lookback_days": 900,
    "max_data_staleness_days": 7,  # refuse to decide if the latest bar is older than this
    "news_lookback_days": 7,
    "synthetic_seed": 7,

    # ---- Risk limits (enforced by the Portfolio Manager after any LLM output) --
    "risk": {
        "max_position": 1.0,       # |target weight| cap (1.0 = 100% of equity notional)
        "target_vol": 0.15,        # annualised vol target used by the neutral risk analyst
        "max_var_95": 0.02,        # cap on 1-day 95% historical VaR of the position
        # Book-level risk aggregation (off by default: None). Per-instrument VaR above is
        # exactly that -- per instrument; a desk running several sleeves at once (TradingGraph
        # .scan(), which already threads a positions dict across a watchlist) has no check
        # that the *book* as a whole stays within a risk budget. Set this to enforce one: the
        # 1-day 95% historical VaR of the whole book (this instrument's proposed weight plus
        # every other symbol's current weight from the same scan) is capped, and a breach
        # scales *this* instrument's weight down (found by search over its own weight, since
        # book VaR is not assumed monotonic -- a new position could be a partial hedge).
        "max_book_var_95": None,
        "min_trade_weight": 0.05,  # smaller targets are rounded to flat
        "rebalance_band": 0.10,    # keep the current position if the new target is within this
                                   # distance of it (a no-trade band; 0 disables)
        # Strategic (benchmark) weight per asset class: the position held with no
        # directional view; conviction tilts around it. Equities default to fully
        # invested (they carry a risk premium); FX to flat. v0.2 used 0 for both.
        "neutral_weight": {"equity": 1.0, "fx": 0.0},
        # With rules.fx_carry_neutral: FX strategic weight = clip(rate_diff% / scale, -cap, cap),
        # so a 1% carry holds 0.5 and the cap binds from 1% (chosen among scale 2/4/8, cap 0.25/0.5/1).
        "fx_carry_neutral_scale": 2.0,
        "fx_carry_neutral_cap": 0.5,
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
        # Square-root market impact in backtests: a trade of q units against an
        # average daily volume ADV moves the price by impact_coeff * daily_vol *
        # sqrt(q / ADV) (the same model as the execution simulator). 0 disables it,
        # which keeps the published results reproducible; 1.0 is the textbook value.
        # Trade sizes scale with initial_capital, so the impact of a 100k account on
        # a large cap is negligible and that of a 100M account is not.
        "impact_coeff": 0.0,
        # FX has no exchange volume; set a notional ADV per pair (quote currency) to
        # apply impact to FX sleeves, or leave None for no FX impact.
        "fx_adv_notional": None,
        # How the day's trade is assumed to be worked, for impact_coeff's cost: None (or
        # "vwap") matches the formula above exactly (spread across the session in proportion
        # to volume, which minimises impact under the square-root law); "twap" (equal size
        # per slice, ignoring the volume curve) or "ac" (Almgren-Chriss, urgency ac_kappa)
        # scale the day's impact by that schedule's cost relative to VWAP (see
        # agentic_trader.algo.algo_cost_ratio). Unset by default so every published number
        # stays reproducible without opting in.
        "execution_algo": None,
        # Dimensionless Almgren-Chriss urgency (0 = TWAP, larger = more front-loaded): used by
        # algo_cost_ratio above and by the execution simulator's "ac" schedule (execute --ac-kappa).
        "ac_kappa": 3.0,
    },
    "initial_capital": 100_000.0,
    # Currency the account is denominated in: initial_capital, order notionals and tickets are
    # in it; FX order quantities are converted from it into the pair's base currency
    # (algo.plan_execution), fetching the base->account rate for crosses.
    "account_currency": "USD",
    "risk_free_annual": 0.0,
    # Cash leg / risk-free rate per bar (data/base.py risk_free_series): "auto" = FRED 3-month
    # T-bill (DTB3, 1-day publication lag) on real-world providers and risk_free_annual on
    # synthetic/CSV data; "fred" forces DTB3; "static" = risk_free_annual everywhere; "off" =
    # unknown (NaN) everywhere, so the backtester credits nothing.
    "cash_leg": "auto",
    "backtest": {
        "use_stops": False,  # enforce the decision's stop-loss / take-profit intraday
    },
    # ---- Execution planning (algo.plan_execution: the `execute` command, execution.plan) ---
    "execution": {
        "fx_lot_size": 1000.0,       # FX orders are rounded down to whole lots of the base currency
        # Cap on one ticket's notional in account_currency, enforced by policy before approval
        # and again by execution.submit_order. None = initial_capital * risk.max_position.
        "max_order_notional": None,
        # Accept execution.submit_order tickets whose plan this desk did not produce. Off: a
        # ticket must name a plan_id the desk issued and repeat its quantity, notional and
        # price (plan_id alone is a checksum anyone can compute, not authentication).
        "allow_external_plans": False,
    },

    # ---- FX macro inputs -----------------------------------------------------
    # "auto": synthetic data uses the static table below; real data (yahoo, csv) uses
    #         point-in-time FRED rates only -- a date with no FRED value for either leg
    #         has no macro view (the analyst abstains, strategic FX weight 0, carry 0).
    # "static" / "fred": force one source. Whatever the source, macro() and carry_series()
    # come from the same resolver, so what the desk is shown is what the backtest credits.
    "fx_macro_source": "auto",
    # ALFRED vintages for revised series (CPI): read each value from the data vintage
    # that was current at the as-of date, so the backtest sees inflation as first
    # published, not as later revised. One download per series per month of history
    # (cached in memory, and on disk when fred_cache_dir is set). Off by default so
    # the published FX results stay reproducible without ~600 extra requests.
    "fred_vintages": False,
    "fred_vintage_step_days": 31,
    "fred_cache_dir": None,
    "fred_cache_max_age_days": 1,     # re-download a cached latest-vintage series older than this (None = never)
    # SEC EDGAR point-in-time fundamentals and filing-stream news for real-data equities
    # (yahoo provider). Free and keyless, but the SEC requires a contact User-Agent:
    # EDGAR_USER_AGENT="Name email@domain" in the environment or .env (never committed),
    # or edgar_user_agent here. Without it EDGAR is skipped with one warning.
    "edgar": True,
    "edgar_user_agent": None,
    "edgar_cache_dir": None,          # on-disk JSON cache (one file per SEC endpoint call)
    "edgar_cache_max_age_days": 7,    # re-fetch a cached endpoint file older than this (None = never)
    "edgar_ciks": {},                 # ticker -> CIK overrides (predecessor filers)
    # Illustrative policy-rate / CPI levels (percent), roughly mid-2025. NOT live data.
    "fx_policy_rates": {
        "USD": 4.25, "EUR": 2.00, "GBP": 4.00, "JPY": 0.50, "CHF": 0.00,
        "AUD": 3.60, "CAD": 2.75, "NZD": 3.00, "SEK": 2.00, "NOK": 4.25,
    },
    "fx_inflation": {
        "USD": 2.7, "EUR": 2.0, "GBP": 3.6, "JPY": 3.0, "CHF": 0.1,
        "AUD": 2.1, "CAD": 1.7, "NZD": 2.7, "SEK": 0.8, "NOK": 3.0,
    },

    # ---- Agentic layer (agentic_trader.agentic) ----------------------------------
    "agentic": {
        "approval": "auto",          # auto | queued | deny: what happens to REQUIRE_APPROVAL
        "llm_planner": False,        # let the model propose the plan (validated either way)
        "llm_critic": True,          # optional model critique (can only lower confidence)
        "llm_reporter": True,        # model-written executive summary (audited either way)
        "use_alpha_tool": True,      # run quant.alpha in the canonical plan
        "critic_divergence": 0.6,    # max |model signal - rule signal| before the critic flags it
        "tool_timeout_s": 30.0,
        "symbol_universe": None,     # list of allowed symbols for tool calls (None = any valid)
        "deny_tools": [],
        # Argument guards (policy) and plan budget (validator); v0.8 agentic-services fixes.
        "max_symbols_per_call": 60,          # longest `symbols` list one tool call may name
        "max_plan_lookback_bars": 200_000,   # symbols x lookback days a plan's tool steps may load in total
        "max_retained_runs": 256,            # finished runs kept in memory per harness (older ones are evicted)
        # Owner id stamped on the runs an instance drives (None = host:pid:random). A stable id per
        # deployment slot is safe across a rolling restart: the sweep fails only records whose
        # heartbeat lease has expired, never a live sibling's just because it shares the id.
        "instance_id": None,
        "lease_s": 90.0,                     # a live run's heartbeat lease (>= 1 s); only expired records are swept
        "task_db": None,             # SQLite path for a persistent task store (None = in memory only)
        "workers": 4,                # task threads per API process
        "queue_limit": 64,           # tasks accepted but unfinished per process; beyond it POST /tasks -> 503
        # At startup, mark FAILED the store records whose heartbeat lease has expired or that have no
        # owner (never a live sibling's, whatever instance id it shares); the parent does it once for
        # --processes N. The periodic sweep runs regardless.
        "sweep_interrupted": True,
        # API keys -> roles for `agentic-trader serve`. Development values only.
        "api_keys": {"dev-viewer-key": "viewer", "dev-analyst-key": "analyst",
                     "dev-trader-key": "trader", "dev-risk-key": "risk", "dev-admin-key": "admin"},
    },

    # ---- Output --------------------------------------------------------------
    "results_dir": "results",
    "memory_path": "results/memory.jsonl",  # None -> in-memory only
    "save_reports": False,
}


# Nested dicts merge key by key, except these, which an override replaces outright: merging
# a user's real API keys *into* the shipped development keys would leave the dev keys live.
_REPLACE_KEYS = {"api_keys"}


def _merge(base: dict, over: dict) -> dict:
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict) and k not in _REPLACE_KEYS:
            _merge(base[k], v)
        else:
            base[k] = v
    return base


# Settings that reproduce v0.2 rule behaviour, for before/after comparisons.
RULES_V02: dict[str, Any] = {
    "rules": {"tsmom": False, "trend_filtered_reversal": False, "abstain_without_data": False,
              "fx_carry_neutral": False},
    "risk": {"rebalance_band": 0.0, "neutral_weight": {"equity": 0.0, "fx": 0.0}},
    "backtest": {"use_stops": False},
}

# Settings that reproduce the v0.3 / v0.4 / v0.5.0 rules (FX strategic weight 0), for
# before/after comparisons of the v0.5.1 FX carry-neutral rule.
RULES_V03: dict[str, Any] = {
    "rules": {"fx_carry_neutral": False},
}


def make_config(overrides: dict | None = None, **kw) -> dict[str, Any]:
    """Deep-copy DEFAULT_CONFIG and deep-merge overrides into it."""
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if overrides:
        _merge(cfg, copy.deepcopy(overrides))
    if kw:
        _merge(cfg, copy.deepcopy(kw))
    return cfg
