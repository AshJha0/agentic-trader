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
| Risk model | `risk_model.py` (v0.14) | EWMA and filtered-historical-simulation VaR forecasts, factor exposures, stress rows, a capacity row |
| Validation and leakage | `validate.py`, `leakage.py` (v0.14) | Bar validator and edge-case conventions; purged walk-forward IC, the future-leak canary, a point-in-time feature table |
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

### Conditional VaR forecasts (v0.14, plan item 5.4)

**The idea.** A 250-day window treats a quiet day a year ago the same as yesterday, so after
volatility jumps the forecast catches up slowly: breaches arrive in runs, then become rare.
On the design period that rule passed Kupiec for 2 of 15 names and Christoffersen
independence for 6 of 15 (PLAN.md section 2). `risk_model.py` adds two forecasters that
condition on current volatility.

**Precisely.** `var_forecast(returns, method, window=250, alpha=0.95)` returns, for each day
`t`, a VaR built from returns before `t` only, aligned so `stats.var_backtest` scores it.

| Method | Forecast for day `t` |
|---|---|
| `historical` | The `1 - alpha` quantile of the last `window` returns (identical to `stats.rolling_var_forecast`) |
| `ewma` | `-z(1 - alpha) * sigma_t`, with `sigma_t^2 = 0.94 * sigma_{t-1}^2 + 0.06 * r_{t-1}^2` (RiskMetrics, 1996) |
| `fhs` | Divide each past return by its own ex-ante `sigma`; take the `1 - alpha` quantile of the last `window` such residuals; multiply by `sigma_t` (Barone-Adesi, Giannopoulos and Vosper, 1999) |

The decay 0.94 is the RiskMetrics value, not tuned on any period here. FHS keeps the shape of
the historical tail and scales it to today's volatility.

**Example.** On simulated GARCH(1,1) returns with Student-t shocks and volatility rising
threefold over 3000 days, FHS passes both tests (p >= 0.05) on 8 of 8 seeds and the 250-day
historical window on at most 2 of 8 (`tests/test_v14_risk.py`;
[recipe 103](../../COOKBOOK.md#103-fhs-against-historical-var-on-synthetic-garch-returns)).
On the design period (2016-01-04 to 2021-12-31, the 15 core names, 5% level,
`scripts/v14_var_design.py`, `results/v14/var_design.json`) the pass counts are:

| Method | Kupiec | Independence | Both |
|---|---|---|---|
| historical (250 days) | 14/15 | 4/15 | 4/15 |
| EWMA | 15/15 | 13/15 | 13/15 |
| FHS | 15/15 | 10/15 | 10/15 |

Conditioning on current volatility fixes most of the clustering the historical window shows.
EWMA did better than FHS here; the book default stays `"fhs"` pending an owner decision
recorded in the round's PR, so the default was not switched after seeing the result. The older
figure "Kupiec 2/15, independence 6/15" (PLAN.md section 2) is a different measurement: the
desk's 250-day historical forecast on the 2022-2023 holdout, from the v0.7/v0.8 evaluation
([evaluation.md](../evaluation/evaluation.md), VaR coverage). There the counts are rejections
(2 of 15 rejected by Kupiec, 6 of 15 by independence); here they are passes, on another period.

**Book VaR is on by default.** `risk.max_book_var_95` is now 0.05 (it was `None`), measured with
`risk.book_var_method = "fhs"`. The 5% is a loose budget, not tuned on any period; it binds only
on concentrated or highly correlated books. Only a multi-sleeve `TradingGraph.scan` builds a
book, so a single `propagate` is unaffected.

**Factor, stress and capacity rows.** `factor_exposures` regresses a return series jointly on
SPY, IEF, UUP and MTUM proxies over a rolling 126-day window. `stress_rows` reports cumulative
return, worst day, drawdown and volatility over 2008, 2020 and 2022; the 2022 window is inside
the holdout, so a 2022 row may only report a series that has already been run there.
`capacity_aum` gives the AUM at which square-root impact costs 0.1 of annual Sharpe. Impact per
trade scales with `sqrt(capital)`, so annual drag at AUM `A` is `D * sqrt(A / capital)`; setting
`D(A) / vol = 0.1` gives `A = capital * (0.1 * vol / D)^2`. Example: a run at 1 000 000 with 15%
volatility that paid 0.5% a year in impact has capacity `1e6 * (0.1 * 0.15 / 0.005)^2 =
9 000 000`. The trading schedule is held fixed, so trades a larger fund would skip are ignored.

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
correlation between the signal and the forward return), its decay over
horizons, hit rate, tercile spread and autocorrelation, and the correlations between signals.

`xalpha.py` asks the cross-sectional question: on each day, does ranking the names by the
signal rank their forward returns? Signals are z-scored or ranked within an asset class per
day; the IC is computed per date; quantile spreads give the long-short return.

Since v0.14 (plan item 5.8) both reports, and the alpha analysts' gate, estimate IC on purged
walk-forward folds (`leakage.ic_purged`, `ic_purged_series`). The bars are cut into five
contiguous blocks; the last `horizon` bars of each block are not scored, because their
forward returns run into the next block; the IC is the mean of the five fold ICs and the
t-statistic is `mean / (sd / sqrt(5))` over them. Folds share no return, so the t-statistic
does not count overlapping pairs as separate evidence. IC, t(IC) and `n` in these tables
therefore differ from earlier releases. `information_coefficient` (effective sample size or
Newey-West) remains public for comparison. With five folds the t-statistic has four degrees
of freedom, so the right threshold is a Student-t critical value, not the normal one; that
correction is plan item 5.1.

Only signals whose IC t-statistic clears the gate (`min_tstat`) are combined. The two alpha
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
| Is the VaR forecast honest? | `rolling_var_forecast`, `risk_model.var_forecast`, `var_backtest` | Kupiec tests the breach rate, Christoffersen tests whether breaches cluster |
| Is a signal's IC real, given overlapping labels? | `leakage.ic_purged`, `ic_purged_series` | Purged, embargoed walk-forward folds; t from the dispersion of fold ICs |
| Can the code see the future? | `leakage.future_leak_canary` | Shock the data from date T; every output before T must be byte-identical |

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
- **Validation (v0.14).** After the provider's repair, `TradingGraph.prepare` refuses a
  history with bad prices, duplicate or unsorted dates, or a gap longer than its limit
  (section 14).
- **Feature visibility (v0.14).** `leakage.PointInTimeStore` keeps each feature value with
  the date it became public and raises `LookaheadError` on a read before that date. It is
  in place for P3; no analyst reads from it yet.
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

## 14. Edge-case conventions (v0.14, plan item 5.7)

These conventions are pinned by `tests/test_v14_edges.py`; the code is in `agentic_trader/validate.py`.

**Bars are validated, not repaired, at the graph.** Providers repair raw downloads with `clean_ohlcv`. After that, `TradingGraph.prepare` runs `require_valid_bars` on the history it is handed and refuses with every reason found: a NaN, zero or negative price, High below Low, a duplicate date, dates out of order, or a step between bars longer than 7 calendar days for equities or 5 for FX (or `max_data_staleness_days`, when that is larger). Seven days covers the longest US closure in the free-data era (11 to 17 September 2001).

**Session clocks.** A daily bar is labelled with its New York trade date. The equity session closes at 16:00 New York; the FX day closes at the 17:00 New York roll, one hour later. Both are New York wall time, so a US daylight-saving change moves both together and the one-hour gap holds all year (21:00/22:00 UTC in winter, 20:00/21:00 UTC in summer). A European DST change on another weekend moves neither. Example: on 26 March 2024, after the US change and before the European one, the equity close is 20:00 UTC and the FX roll 21:00 UTC.

**Holidays across sleeves.** Sleeves align on trade dates. A date on which one sleeve has no bar (4 July: equities shut, FX trades) is not a common session, so a multi-sleeve rebalance waits for the next date every sleeve trades (`validate.common_sessions`).

**Splits.** Every metric is computed from returns of a split-adjusted series, so it cannot depend on the price scale. A property test builds an unadjusted series with a k-for-1 step, adjusts it back, and checks that cumulative return, volatility, Sharpe, drawdown, historical VaR and CVaR, and every equity alpha are unchanged, as they are under any constant rescaling.

**Stops and targets.** Levels are checked against the open first, then against the bar's range. A gap through the stop fills at the open, not at the stop. When the stop and the target both lie inside one bar's range, the stop is assumed to have traded first: daily bars do not say which came first, and the worse outcome is the conservative assumption. This was already the rule on both backends; v0.14 pins it and does not change it.

**Survivorship.** `validate.survivorship_statement` writes one line per table row saying whether the name was trading at design start, listed afterwards (chosen with hindsight), or absent.

**Short notional.** Borrow availability and recall are not modelled. `risk.max_short_notional` (default `None`: only `max_position` binds) caps a short in the Portfolio Manager's guardrails, after the short-selling check and before the position cap.

**Ledger floats.** The paper ledger is written with each float's shortest round-trip `repr` and read back with pandas' round-trip parser, so a row survives a write and read bit for bit. Ledgers are compared with a tolerance (`validate.ledgers_match`, default 1e-12), never with `==`.

## 15. Estimated combination, regimes and conformal sizing (v0.14, plan items 5.1-5.3)

**The idea.** The rules desk adds its evidence with hand-set numbers nobody estimated (role
weights, 0.30 / 0.20 / 0.15 / 0.15 technical weights, a 2x tilt, a 25 / 50 / 25 risk blend).
The alternative is to weight each signal by how well it has predicted returns, and to give a
signal no weight at all unless that record clears a significance bar.

**Precisely.** `agentic_trader/combine.py`, on with `combination.method = "ic"`:

1. every library alpha plus two trend components, each a trailing z-score clipped at +-3;
2. a trailing purged IC per signal over the last `window` bars whose forward return is known
   at the as-of bar (`leakage.ic_purged`);
3. shrinkage: `IC * max(0, 1 - (t_crit / t)^2)`, where `t_crit` is the two-sided 5% Student-t
   value for `k - 1` degrees of freedom over the `k` finite folds (2.776 for five folds); with
   fewer than three finite folds nothing passes;
4. `mu = sigma_h * sum_i IC_i z_i` (Grinold; overstates `mu` when correlated signals survive);
5. tilt `mu / (gamma sigma_h^2)`, or `Sigma^-1 mu / gamma` with a Ledoit-Wolf covariance for a
   book, then a turnover no-trade band of half-width `kappa / (gamma sigma^2)`.

Only `window` (504) is a registered parameter; `horizon` 10, `risk_aversion` 2.5 and
`turnover_penalty` 0.0005 were fixed in `DEFAULT_CONFIG` before any run.

`regime.py` fits a 2- or 3-state diagonal Gaussian HMM (Baum-Welch in numpy) to log 20-day
volatility, the 60-day return over 60-day volatility and the 20-day change in the 3-month bill
rate, on bars from `regime.fit_start` up to the earlier of the as-of date and `regime.fit_end`
(the design end). Labels are forward-filtered probabilities, ordered calm to stressed.
`regime.enabled` adds the label as a fact; `regime.condition` estimates ICs and the sizing
volatility on bars of the current regime only.

`conformal.enabled` splits the window in time: ICs are estimated on its first part, and the
absolute forecast errors on the last `calibration_share` give the interval half-width at
miscoverage `alpha`; the PM scales the tilt by `min(1, |mu| / half-width)`.

**Example: the design result.** 2016-01-04 to 2021-12-31, 15 names, Yahoo (`results/v14/`):

| Trial | Mean Sharpe | Control | Difference | 95% CI | p | Beats control |
|---|---|---|---|---|---|---|
| rules desk (current default) | 0.6477 | 0.6437 | +0.004 | [-0.128, +0.148] | 0.989 | 6/15 |
| IC combination, window 504 | 0.5125 | 0.6437 | -0.131 | [-0.314, +0.059] | 0.174 | 5/15 |

The pre-registered expectation was that the tilt would go to zero on what is mostly noise.
It did not: some signal survived shrinkage on 82.6% of sampled design dates
(`ic_tilt_design.json`, every fifth date), mostly slow price-level signals whose fold ICs are
consistently signed. Nothing was adopted or tuned. The regime and conformal trials are
registered with their design run pending (follow-up 5.2b). See
[LEARN concept 53](../../LEARN.md#53-a-pre-registered-expectation-that-failed).

## 16. Paper order management (v0.14, plan item 4.7)

`oms.py` simulates the order path between a decision and a fill; nothing reaches a broker. A
fill of notional `N` on capital `C` pays `N (cost_bps + slippage_bps) / 1e4 + C K_t (N / C)^1.5`,
exactly the entry cost `quant.run_backtest` charges for a weight change `N / C`
(`tests/test_v14_oms.py` checks the parity), capped at `participation_cap` (0.10) of modelled
daily volume. Equities settle T+1 on the NYSE calendar; FX spot settles T+2 and an FX trade at
or after 17:00 New York belongs to the next trade date. Limits: static borrow list, no
non-USD holidays unless listed, no intraday path.
[Recipe 104](../../COOKBOOK.md#104-a-paper-order-through-the-oms).
