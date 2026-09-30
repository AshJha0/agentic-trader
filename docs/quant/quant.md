# How the quant works: the core, the backtester, risk, alphas, portfolios and the statistics

This page explains the quantitative side of AgenticTrader in one place: what is computed,
with which conventions, where the code is, and how a result is tested before it is believed.
The agents, the language model and the agentic layer have their own page:
[How the AI works](../ai/ai.md).

Related pages: [architecture](../architecture/overview.md), [diagrams](../DIAGRAMS.md)
(17 to 38), [API](../api/api.md), [evaluation](../evaluation/evaluation.md), and concepts
18 to 50 of [LEARN.md](../../LEARN.md). No number on this page is a result; the measured
results are on the evaluation pages.

## The map

| Layer | Code | What it holds |
|---|---|---|
| Quant core | `cpp/` (C++17) and `agentic_trader/quant/pycore.py` (numpy twin), behind the facade `agentic_trader/quant/__init__.py` | Indicators, risk primitives, baseline strategies, the backtester, metrics |
| Backtests | `backtest.py` | Walk-forward desk backtest against nine baselines; portfolio backtest with sleeves |
| Alphas | `alpha.py`, `xalpha.py` | A signal library with time-series and cross-sectional tests |
| Execution | `algo.py` | Schedules (TWAP, VWAP, POV, Almgren-Chriss), a fill simulator, implementation shortfall |
| Portfolio | `portfolio.py` | Covariance estimation, five weighting schemes, risk budgets, book VaR |
| Statistics | `stats.py` | Sharpe inference, bootstraps, deflated Sharpe, false discovery control, VaR coverage tests |
| Evaluation | `evaluation.py`, `scripts/` | Periods, universes, the trials registry, the measurement and rendering scripts |
| Data | `data/` | Synthetic, Yahoo and CSV prices; FRED (rates, inflation, vintages); SEC EDGAR (filings) |

## 1. One core in two languages

Every routine in the core exists twice: in C++ (compiled to the `_atcore` extension with
pybind11) and in numpy. The facade uses C++ when the extension is built and numpy otherwise;
`AGENTIC_TRADER_BACKEND=python` forces numpy. The reason is trust, not speed alone: two
independent implementations that agree on thousands of random inputs are unlikely to share a
mistake.

The contract at the boundary, enforced by the facade on both backends:

- every function returns an array of the input's length (or a plain float), or raises
  `ValueError`. Nothing else crosses the boundary;
- window arguments are validated in one place (an integer of at least 1; a boolean is refused);
- both backends refuse the same bad inputs and agree on good ones.

`tests/test_quant.py` cross-checks the two on fixed series. `tests/test_fuzz.py` uses
hypothesis to throw NaN, infinities, empty arrays and extreme values at every exported
function and asserts the contract. In v0.12 that fuzzing found a real disagreement in an old
strategy on one platform (a threshold decided by rounding noise), which is now fixed with a
dead band. The procedure for adding a routine is in the README's *Extending* section and in
diagram 37.

## 2. Indicators

Conventions (stated in `cpp/include/at/indicators.hpp`, mirrored in `pycore.py`):

- values that cannot be computed yet (the warm-up) are NaN, never zero;
- rolling standard deviations use the population estimator;
- a missing input makes every window that touches it NaN, and the series recovers once the
  window has passed. The recursive indicators (EMA, and Wilder's smoothing inside RSI and
  ATR) reset at the gap and re-seed. A gap is never treated as a zero change.

| Function | Definition |
|---|---|
| `sma`, `ema` | Simple and exponential moving average; the EMA is seeded with the SMA of its first `n` points |
| `rolling_std`, `zscore` | Rolling population standard deviation; (x − mean) / std over the window |
| `rsi` | Wilder-smoothed relative strength index |
| `macd` | Fast EMA minus slow EMA, its signal EMA, and the histogram |
| `bollinger` | Mean ± k standard deviations, and %B, the position of the close inside the band |
| `atr` | Wilder-smoothed average true range |
| `kdj` | Stochastic K, D (smoothing 1/3, starting at 50) and J = 3K − 2D |
| `pct_change`, `realized_vol` | Simple returns; annualised rolling volatility of simple returns |
| `rolling_max`, `rolling_min` | Window extremes |
| `spearman` | Rank correlation over pairs where both values are finite, average ranks for ties |

## 3. Risk primitives

| Function | Definition |
|---|---|
| `quantile` | Linear-interpolated quantile, NaNs ignored |
| `historical_var(returns, alpha)` | The loss at the (1 − alpha) quantile of the return history, as a positive fraction |
| `historical_cvar` | The mean loss beyond that VaR (expected shortfall) |
| `vol_target_weight(signal, vol, target, cap)` | `signal × target / vol`, clipped to the cap; 0 when the volatility is missing |
| `kelly_fraction(p, b)` | `p − (1 − p) / b`, not clipped |
| `position_units` | Units such that hitting the stop loses a chosen fraction of equity |
| `max_drawdown` | Largest peak-to-trough fall of an equity curve, as a positive fraction |

The desk's own risk check is a 95% one-day historical VaR of the instrument's last 250 daily
returns, on the side of the position (the left tail for a long, the right tail for a short),
multiplied by the absolute weight and compared with a 2% limit. Whether that forecast is
calibrated is tested, not assumed: section 9.

## 4. The backtester

One vectorised engine serves equities and FX (`cpp/include/at/backtest.hpp` states every
convention; `run_backtest` in the facade).

**Timing.** The target weight at bar `t` is decided with information up to and including bar
`t` and earns the return from `t` to `t+1`. There is no look-ahead as long as the weight
depends only on data up to `t`.

**Constant units between decisions.** A target is executed on a decision bar (the target
changes, or the rebalance mask is set). Costs on the weight change are paid out of equity
first, and the target is a fraction of what is left:

```
E[t+1] = E[t] × (1 − k_in) × (1 + g) × (1 − k_out)
g      = w × r_price + w × carry / ppy + cash_fraction × rf / ppy − borrow
```

Between decisions the number of units is held, so the weight drifts with the market. No
trade and no cost is charged on a hold bar. `positions[t]` is the weight actually held.

**Costs.** Commission or half-spread and slippage in basis points per unit of turnover; a
borrow fee on equity shorts; for FX the spread in pips and the carry (the interest rate
differential, per bar, point in time).

**Cash leg.** Idle capital earns the bill rate. A funded position (equities) earns it on
`1 − |w|`. An FX forward is unfunded: the whole account earns it and the carry term is the
rate differential. Sharpe, Sortino and the t-statistic are computed on **excess** returns over
that rate, so a strategy that sits in cash is not credited with the bill's return as skill.

**Market impact.** Optional, off by default. A trade of `|dw|` at bar `t` costs
`|dw|^1.5 × K_t × sqrt(E_t / E_0)` of equity, with
`K_t = coeff × daily_vol_t × sqrt(capital / (price_t × ADV_t))`: the square-root law, scaled
to the equity actually traded. Average daily volume is taken on the as-traded (unadjusted)
close. The schedule assumed for working the trade (VWAP, TWAP or Almgren-Chriss) scales the
cost.

**Stops and targets.** A position with a stop or take-profit level is closed inside the next
bar when the level trades. The open is resolved first: a gap through either level fills at
the open. If both levels trade inside one bar the stop is assumed to fill first, the
conservative reading of a daily bar. After an exit the position stays flat until the next
decision.

**Ruin.** If any leg of a bar consumes the whole account the equity is floored at zero, the
position is written off and every later bar is flat. The metrics report it.

**Metrics** (`compute_metrics`): cumulative and annualised return, annualised volatility,
Sharpe and Sortino on excess returns, maximum drawdown, Calmar, win rate, number of trades,
turnover, average exposure and the Sharpe t-statistic. A return series that is constant to
rounding has Sharpe 0 on both backends, not noise divided by noise. Annualisation uses 252
periods a year for equities and 260 for FX and mixed portfolios.

## 5. Baselines and the fair control

Every backtest prints the desk beside nine baselines, all through the same engine with the
same costs (`baseline_weights`):

| Baseline | Rule |
|---|---|
| `Buy&Hold` | Always fully long |
| `B&H vol-target` | Long at `target_vol / realized_vol`, capped: no view on direction, only on size. **This is the fair control** for a desk that sizes by volatility |
| `SMA(20/50)`, `MACD`, `KDJ+RSI`, `ZMR` | Classic crossover, momentum, oscillator and z-score mean-reversion rules |
| `TSMOM(12-1)` | Sign of the 12-month return skipping the last month, at the vol-target size; long-only where the desk may not short |
| `TSMOM(L/S)` | Average sign of the 1, 3 and 12 month returns, long and short, at the vol-target size (`quant.strat_tsmom`) |
| `Carry` | FX: the rate differential mapped to a position; flat on equities |

The desk run is walk-forward (`run_agent_backtest`): at each rebalance the full desk decides
with history up to that bar and with the position it actually holds after drift or a stop.
`run_portfolio_backtest` runs one sleeve per symbol and combines them by a weighting scheme
re-estimated from trailing returns only.

## 6. Alphas

An alpha is a function from price history to a number in [−1, 1] (`alpha.ALPHAS`): 12-1
momentum scaled by volatility, 20-day momentum, 5-day reversal, proximity to the 52-week
high, position in the 20-day channel, MACD in ATR units, contrarian RSI, low volatility, and
FX carry.

`alpha_report` tests each one on one instrument: the information coefficient (the rank
correlation between the signal and the forward return) with a t-statistic corrected for the
overlap of forward returns (an effective sample size, or Newey-West), its decay over
horizons, hit rate, tercile spread and autocorrelation, and the correlations between signals.

`xalpha.py` asks the cross-sectional question: on each day, does ranking the names by the
signal rank their forward returns? Signals are z-scored or ranked within an asset class per
day; the IC is computed per date and summarised with an overlap-aware t-statistic; quantile
spreads give the long-short return.

Only signals whose IC t-statistic is at least 2 in magnitude are combined. The two alpha
analysts that use them are off by default because the design period did not support them.

## 7. Execution

`plan_execution` turns a decision into a parent order (side, quantity in the instrument's
units, notional) and a schedule. `simulate_execution` fills the schedule against intraday
bars with half-spread and square-root impact and reports implementation shortfall against
the arrival price, the opportunity cost of any unfilled quantity, and the slippage against
the session VWAP.

| Schedule | Idea |
|---|---|
| TWAP | Equal size per slice |
| VWAP | Proportional to the expected volume curve (U-shaped for equities) |
| POV | A fixed share of each slice's volume, with a cap |
| Almgren-Chriss | Front-loaded by the urgency `kappa = sqrt(risk aversion × variance / temporary impact)`; `kappa → 0` is TWAP. Computed in a form that cannot overflow |

## 8. Portfolio construction

`portfolio.construct` takes the desk's signed targets and a return history and produces
weights.

- **Covariance.** Exponentially weighted (60-day half-life by default), then shrunk towards a
  constant-correlation target with the Ledoit-Wolf intensity. Few observations per asset
  means more shrinkage.
- **Schemes.** Equal, inverse volatility, risk parity (each sleeve contributes the same share
  of risk, or a chosen budget), minimum variance and mean-variance, the last two with a
  per-sleeve cap.
- **Risk budgets across groups.** A budget per asset class, then risk parity within each.
- **Volatility target.** The allocation is scaled to a target, with the scale capped so no
  sleeve exceeds its maximum.
- **Diagnostics.** Marginal and component risk per sleeve, share of risk, diversification ratio.
- **Book VaR.** `book_var_95` for a set of positions, and `book_var_scale`, which finds the
  largest size a new position may take within the book's limit by search, because a new
  position can be a partial hedge and book VaR is not monotonic in its weight.

## 9. Statistics: is the result real?

This is the part of the quant that decides what the project is allowed to claim.

| Question | Tool | Notes |
|---|---|---|
| How uncertain is one Sharpe ratio? | `sharpe_stats`, `sharpe_ci_bootstrap` | A block bootstrap keeps the autocorrelation of returns |
| Is strategy A's Sharpe higher than B's? | `paired_sharpe_block_bootstrap` | Both series are resampled together in blocks of days |
| Is the desk better across instruments? | `paired_bootstrap` | A cluster bootstrap over asset-class groups when there are enough, because ten technology stocks are not ten independent tests |
| Did I find this by trying many things? | `deflated_sharpe`, `expected_max_sharpe`, `selection_report` | The Sharpe is compared with the best one expected from that many unskilled trials. `evaluation.TRIALS` registers every variant ever judged |
| Are the flagged rows of a table luck? | `benjamini_hochberg` | False discovery rate over the rows printed |
| How long a record is needed? | `min_track_record`, `probabilistic_sharpe` | A Sharpe near 1 needs years |
| Is the VaR forecast honest? | `rolling_var_forecast`, `var_backtest` | Kupiec tests the breach rate, Christoffersen tests whether breaches cluster |

## 10. The evaluation protocol

| Period | Dates | May be used to |
|---|---|---|
| `design` | 2016-01-04 to 2021-12-31 | choose rules |
| `design_long` | 2008-07-01 to 2021-12-31 | choose return streams on the ETF and FX universes |
| `holdout` | 2022-01-03 to 2026-06-30 | report only: it was looked at in v0.8 and is spent |
| `reserve`, extended universe | 2026-07-01 to 2026-09-25; 45 instruments | report only: both were consulted for earlier decisions |
| forward paper record | from 2026-09-29 | test: the only unseen data |

The rules (diagram 36):

1. a change goes behind a switch and is measured on a design period only;
2. it is adopted only if the interval of its Sharpe difference against `B&H vol-target` is
   above zero;
3. every variant tried is registered as a trial, adopted or not;
4. anything that will be reported on spent data is pre-registered first
   ([v09_preregistration.md](../evaluation/v09_preregistration.md));
5. every published number is copied from a result file by a script, and each result file
   carries the commit, whether the tree was clean, and the backend that produced it.

## 11. Data: point in time

A backtest is only as honest as its data timing.

- **Prices.** Yahoo closes are adjusted; average daily volume for impact uses the as-traded
  close. Inputs pass through `clean_ohlcv`, and the desk refuses to decide on stale data.
- **Macro.** FRED policy rates and inflation with publication lags; ALFRED vintages give
  inflation as first published, not as later revised.
- **Filings.** SEC EDGAR fundamentals are visible from the first session whose close comes
  after the filing's acceptance time (converted from UTC to New York time), and facts are
  joined to filings by accession number.
- **Synthetic.** The default provider makes fake prices, news and fundamentals from a seed,
  so everything runs offline and deterministically. It is for tests and examples, never
  for results.

## 12. What the quant has found

Stated plainly, because it is the point of the statistics above:

- The rule-based desk beats unmanaged buy and hold on some measures and **has no measurable
  edge over the volatility-targeted control**. Attribution shows it is about nine tenths of
  that control plus a tilt with no measurable alpha.
- A multi-asset base, trend (long-only and long/short), carry, their combinations, and the
  desk's tilt as a sized overlay were each tried on design data. None beat its control.
  Nothing was adopted in v0.9, v0.10 or v0.12.
- The test that remains is the forward paper-trading record.

The numbers, with intervals, are in [evaluation.md](../evaluation/evaluation.md),
[v09_research.md](../evaluation/v09_research.md), [v010_overlay.md](../evaluation/v010_overlay.md),
[v011_review.md](../evaluation/v011_review.md) and [v012_trend_core.md](../evaluation/v012_trend_core.md).

## 13. Try it

```bash
agentic-trader backtest NVDA --start 2023-01-02 --end 2023-12-29       # the desk against the nine baselines
agentic-trader portfolio AAPL,JPM,XOM,EURUSD,USDJPY --start 2023-01-02 --end 2023-12-29 --weighting risk_parity
agentic-trader alpha NVDA --start 2021-01-04 --end 2023-12-29 --horizon 10   # the alpha library's IC report
agentic-trader stats returns.csv --var-backtest                        # Sharpe inference and VaR coverage on your own returns
```

Cookbook recipes 9 to 16 (backtests and the core), 51 to 59 (alphas, execution, portfolios,
deflated Sharpe, impact) and 73 to 100 (VaR tests, bootstraps, trend and carry streams, the
overlay, risk budgets, the trials registry) show each piece in a few lines.
