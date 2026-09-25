# Evaluation

This document records how agentic-trader is evaluated, what was measured, and what the
numbers do and do not show. Every figure here comes from a recorded run. To reproduce them,
see [Reproducing](#reproducing).

> **Scope of these results.** All numbers were produced by the **rule-based agents** (offline
> mode, no LLM). The LLM mode, which the TradingAgents paper evaluates, has **not** been
> evaluated here, so nothing below says anything about Claude's trading performance, and none
> of the paper's reported results are claimed. The measurements were taken on 2026-09-25 with
> the C++ backend.

## Protocol

The protocol mirrors the paper's evaluation layout:

| Item | Setting |
|---|---|
| Window | 2024-01-02 → 2024-03-28 (Q1 2024; the paper uses Jan 1 – Mar 29, 2024) |
| Equities | AAPL, NVDA, MSFT, META, GOOGL |
| FX (project addition) | EURUSD, USDJPY, GBPUSD |
| Rebalancing | Every 5 bars: full `propagate()` with data up to that close; weight held to the next rebalance |
| Warm-up | 400 calendar days of history before the window for indicators |
| Baselines | Buy & Hold, SMA(20/50) crossover, MACD(12,26,9), KDJ(9)+RSI(14), ZMR (20-day z-score, entry 1.0, exit 0.0) |
| Execution | Weight decided at close *t* earns the return from *t* to *t + 1* |
| Equity costs | 1 bps commission + 1 bps slippage per unit turnover; 1% p.a. borrow on shorts (shorts disabled by default) |
| FX costs | Half of a 0.8-pip spread converted to bps at the window's mean price, + 0.2 bps slippage; shorts enabled |
| FX carry | `(base rate − quote rate)` from the **static illustrative config** (see caveat below), accrued daily on the position |
| Position limits | \|weight\| ≤ 1.0; 1-day VaR95 of the position ≤ 2%; weights below 0.05 become flat |
| Debate rounds | 2 research rounds, 1 risk round |

### Metrics

With per-period returns *r*, *n* periods and *P* periods per year (252 equity, 260 FX):

| Metric | Definition |
|---|---|
| CR (cumulative return) | *V_end / V_start − 1* |
| AR (annualised return) | *(1 + CR)^(P/n) − 1* |
| Vol | *std(r, ddof = 1) · √P* |
| Sharpe | *(mean(r) − r_f/P) / std(r) · √P*, with *r_f = 0* |
| Sortino | *(mean(r) − r_f/P) / √mean(min(r − r_f/P, 0)²) · √P* |
| MDD (max drawdown) | *max over t of (1 − V_t / max_{s ≤ t} V_s)* |
| Calmar | *AR / MDD* |
| Win rate | Share of positive returns among periods with a non-zero position |
| Trades | Number of changes in the held weight |

AR over one quarter is heavily compounded (for example NVDA buy & hold is +1303%), so read
CR, Sharpe and MDD first.

## Results on real prices (Yahoo Finance)

Real daily prices for Q1 2024. Because Yahoo serves only recent news and current-snapshot
fundamentals, the point-in-time guards give the agents **no news and no fundamentals** for
these historical dates. The decisions are therefore driven mainly by the technical analyst,
the market-based sentiment proxies and, for FX, the macro analyst.

### Summary: agent vs buy & hold

| Symbol | Agent CR % | B&H CR % | Agent MDD % | B&H MDD % | Agent Sharpe | B&H Sharpe | Best baseline by Sharpe |
|---|---:|---:|---:|---:|---:|---:|---|
| AAPL | -3.49 | -7.53 | 3.49 | 13.30 | -3.84 | -1.55 | KDJ+RSI (0.35) |
| NVDA | 35.23 | 87.56 | 4.54 | 8.70 | 5.42 | 5.46 | Buy&Hold (5.46) |
| MSFT | 7.57 | 13.63 | 2.79 | 4.21 | 2.51 | 2.90 | KDJ+RSI (4.47) |
| META | 23.56 | 40.34 | 2.88 | 5.58 | 3.06 | 3.10 | Buy&Hold (3.10) |
| GOOGL | 3.58 | 9.21 | 6.93 | 14.40 | 1.07 | 1.46 | Buy&Hold (1.46) |
| EURUSD | -0.64 | -2.57 | 2.44 | 3.25 | -0.70 | -2.05 | ZMR (0.82) |
| USDJPY | 3.79 | 8.16 | 2.12 | 2.49 | 2.72 | 4.31 | KDJ+RSI (7.58) |
| GBPUSD | -1.32 | -0.94 | 1.77 | 2.01 | -1.63 | -0.68 | ZMR (3.73) |

**What this shows:**

- **Drawdown.** The rule-based firm had a lower maximum drawdown than buy & hold on
  **all 8** instruments. The volatility-targeted, VaR-capped sizing does what it is designed
  to do.
- **Returns.** It returned **less** than buy & hold on every instrument that rallied
  (NVDA, MSFT, META, GOOGL, USDJPY). Q1 2024 was a strong one-way market for these names,
  and partial sizing gives up upside.
- **Down-trending instruments.** It lost less than buy & hold on AAPL (−3.5% vs −7.5%)
  and EURUSD (−0.6% vs −2.6%), but slightly more on GBPUSD.
- **Sharpe.** It did not beat the best baseline on Sharpe for any instrument. The best was
  NVDA, where 5.42 vs 5.46 is about equal at half the volatility (23.9% vs 50.9%).
- **Oversold baselines.** KDJ+RSI and ZMR never entered NVDA or META: a long-only oversold
  signal never fired in a one-way rally.

### Full table

| Symbol | Strategy | CR % | AR % | Sharpe | MDD % | Trades |
|---|---|---:|---:|---:|---:|---:|
| AAPL | **AgenticTrader** | -3.49 | -13.85 | -3.84 | 3.49 | 2 |
|  | Buy&Hold | -7.53 | -28.02 | -1.55 | 13.30 | 1 |
|  | SMA(20/50) | -1.63 | -6.69 | -1.00 | 2.42 | 2 |
|  | MACD | -5.04 | -19.51 | -1.65 | 7.74 | 3 |
|  | KDJ+RSI | 1.05 | 4.50 | 0.35 | 10.66 | 5 |
|  | ZMR | -1.38 | -5.66 | -0.31 | 8.71 | 6 |
| NVDA | **AgenticTrader** | 35.23 | 255.24 | 5.42 | 4.54 | 12 |
|  | Buy&Hold | 87.56 | 1303.30 | 5.46 | 8.70 | 1 |
|  | SMA(20/50) | 87.56 | 1303.30 | 5.46 | 8.70 | 1 |
|  | MACD | 48.02 | 419.14 | 4.81 | 7.44 | 4 |
|  | KDJ+RSI | 0.00 | 0.00 | 0.00 | 0.00 | 0 |
|  | ZMR | 0.00 | 0.00 | 0.00 | 0.00 | 0 |
| MSFT | **AgenticTrader** | 7.57 | 35.88 | 2.51 | 2.79 | 12 |
|  | Buy&Hold | 13.63 | 71.02 | 2.90 | 4.21 | 1 |
|  | SMA(20/50) | 13.63 | 71.02 | 2.90 | 4.21 | 1 |
|  | MACD | 2.75 | 12.09 | 0.93 | 5.42 | 5 |
|  | KDJ+RSI | 9.04 | 43.84 | 4.47 | 1.01 | 4 |
|  | ZMR | 3.39 | 15.04 | 2.69 | 0.18 | 4 |
| META | **AgenticTrader** | 23.56 | 143.19 | 3.06 | 2.88 | 12 |
|  | Buy&Hold | 40.34 | 315.16 | 3.10 | 5.58 | 1 |
|  | SMA(20/50) | 40.34 | 315.16 | 3.10 | 5.58 | 1 |
|  | MACD | 25.70 | 161.36 | 2.34 | 4.27 | 4 |
|  | KDJ+RSI | 0.00 | 0.00 | 0.00 | 0.00 | 0 |
|  | ZMR | 0.00 | 0.00 | 0.00 | 0.00 | 0 |
| GOOGL | **AgenticTrader** | 3.58 | 15.93 | 1.07 | 6.93 | 11 |
|  | Buy&Hold | 9.21 | 44.80 | 1.46 | 14.40 | 1 |
|  | SMA(20/50) | -0.79 | -3.26 | -0.02 | 11.16 | 2 |
|  | MACD | 4.84 | 21.96 | 1.02 | 8.75 | 5 |
|  | KDJ+RSI | 5.22 | 23.82 | 1.24 | 11.81 | 4 |
|  | ZMR | -2.13 | -8.63 | -0.54 | 8.81 | 2 |
| EURUSD | **AgenticTrader** | -0.64 | -2.65 | -0.70 | 2.44 | 10 |
|  | Buy&Hold | -2.57 | -10.35 | -2.05 | 3.25 | 1 |
|  | SMA(20/50) | -4.05 | -15.93 | -3.31 | 4.08 | 3 |
|  | MACD | 0.39 | 1.65 | 0.34 | 2.24 | 6 |
|  | KDJ+RSI | -0.57 | -2.36 | -0.42 | 2.68 | 2 |
|  | ZMR | 0.88 | 3.75 | 0.82 | 1.83 | 9 |
| USDJPY | **AgenticTrader** | 3.79 | 16.88 | 2.72 | 2.12 | 8 |
|  | Buy&Hold | 8.16 | 38.93 | 4.31 | 2.49 | 1 |
|  | SMA(20/50) | -1.86 | -7.57 | -0.95 | 5.53 | 2 |
|  | MACD | -0.01 | -0.03 | 0.04 | 4.19 | 8 |
|  | KDJ+RSI | 13.83 | 72.13 | 7.58 | 1.11 | 4 |
|  | ZMR | -0.51 | -2.10 | -0.27 | 4.77 | 8 |
| GBPUSD | **AgenticTrader** | -1.32 | -5.41 | -1.63 | 1.77 | 11 |
|  | Buy&Hold | -0.94 | -3.90 | -0.68 | 2.01 | 1 |
|  | SMA(20/50) | -3.63 | -14.37 | -2.75 | 4.13 | 3 |
|  | MACD | 2.12 | 9.21 | 1.59 | 1.69 | 3 |
|  | KDJ+RSI | 0.87 | 3.69 | 0.67 | 2.49 | 1 |
|  | ZMR | 4.63 | 20.90 | 3.73 | 1.79 | 13 |

Bars in the window: 61 for the equities, 63 for FX. Effective FX transaction cost per unit
of turnover: EURUSD 0.37 bps, USDJPY 0.27 bps, GBPUSD 0.32 bps (plus 0.2 bps slippage).

> **FX carry caveat.** Carry uses the static `fx_policy_rates` in `config.py`: USD 4.25%,
> EUR 2.00%, JPY 0.50%, GBP 4.00%. That gives EURUSD −2.25%, USDJPY +3.75% and GBPUSD
> −0.25% p.a. These are illustrative levels, **not** the policy rates in force in Q1 2024
> (for example, the Fed funds rate was about 5.33% and the BoJ rate negative until March
> 2024). The same carry applies to the agent and to every baseline. For period-accurate
> carry, set `fx_macro_source="fred"`.

## Results on synthetic data (offline)

The same protocol on the seeded synthetic market (`synthetic_seed=7`). These prices, news
and fundamentals are fake. The table demonstrates that the full pipeline (news, social
posts, fundamentals and macro all present) runs end to end and deterministically; it says
nothing about real-world performance.

| Symbol | Agent CR % | B&H CR % | Agent MDD % | B&H MDD % | Agent Sharpe | B&H Sharpe | Best baseline by Sharpe |
|---|---:|---:|---:|---:|---:|---:|---|
| AAPL | 4.30 | 23.60 | 4.46 | 7.80 | 1.58 | 2.60 | ZMR (4.09) |
| NVDA | -4.51 | 3.88 | 7.55 | 17.69 | -1.58 | 0.58 | MACD (1.15) |
| MSFT | 4.85 | 18.20 | 4.30 | 9.93 | 1.83 | 2.52 | ZMR (3.36) |
| META | -5.10 | -15.84 | 8.52 | 27.18 | -2.23 | -1.86 | KDJ+RSI (-0.44) |
| GOOGL | -0.73 | -16.59 | 2.13 | 22.82 | -0.57 | -2.14 | MACD (-0.67) |
| EURUSD | -1.12 | -0.09 | 2.18 | 1.70 | -1.45 | -0.04 | ZMR (2.41) |
| USDJPY | 0.41 | 1.23 | 1.26 | 1.62 | 0.47 | 1.01 | SMA(20/50) (2.15) |
| GBPUSD | -4.45 | 3.22 | 5.15 | 3.54 | -3.71 | 1.52 | ZMR (2.82) |

## Engineering measurements

| Measurement | Value |
|---|---|
| One `propagate()`, offline, C++ backend | 3.7 ms (AAPL), 2.9 ms (EURUSD), mean of 20 runs after warm-up |
| Q1 walk-forward backtest, NVDA synthetic: 63 bars, 13 agent decisions + 5 baselines | 0.08 s |
| LLM calls per decision at default rounds | 14 = 4 quick-tier (analysts) + 10 deep-tier (2×2 debate turns, facilitator, trader, 3 risk views, PM) |
| LLM calls for a Q1 backtest at `--every 5` | 12–13 decisions × 14 ≈ 170–180 per instrument |
| Tests | 18 pytest (11 pipeline, 7 quant) + 7 C++ test groups (21 checks); CI: 8 jobs across 3 OSes and Python 3.10–3.14 |

## What would make these results stronger

- **Evaluate the LLM mode** on the same protocol, with several seeds or runs per date,
  because LLM decisions are not deterministic. Report the rule-based firm as the control.
- **Use point-in-time news and fundamentals** (a historical news vendor, as-filed
  financials). Without them, the real-price results test only half of the analyst team.
- **Use a longer window** covering more than one regime. One quarter of a one-way rally
  favours buy & hold by construction.
- **Use period-accurate FX carry** (`fx_macro_source="fred"`).

## Reproducing

```bash
# the offline synthetic table (deterministic)
python examples/compare_baselines.py

# one real-price row (needs network; Yahoo data can be revised slightly over time)
agentic-trader backtest NVDA --data yahoo --start 2024-01-02 --end 2024-03-28 --every 5
```

To count LLM calls per decision, see the "Count LLM calls" recipe in
[COOKBOOK.md](../../COOKBOOK.md).
