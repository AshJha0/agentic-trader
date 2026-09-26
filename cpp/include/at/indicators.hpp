// Technical indicators used by the Technical Analyst agent and baseline strategies.
//
// Conventions (mirrored exactly by agentic_trader/quant/pycore.py):
//   * Every function returns a vector the same length as its input.
//   * Warm-up values that cannot be computed are NaN.
//   * Rolling standard deviations use the population estimator (ddof = 0).
#pragma once

#include <vector>

namespace at {

using Series = std::vector<double>;

struct MACD {
    Series line;
    Series signal;
    Series hist;
};

struct Bollinger {
    Series mid;
    Series upper;
    Series lower;
    Series percent_b;  // (close - lower) / (upper - lower)
};

struct KDJ {
    Series k;
    Series d;
    Series j;
};

Series sma(const Series& x, int n);
// EMA seeded with the SMA of the first n valid points; leading NaNs are skipped.
Series ema(const Series& x, int n);
Series rolling_std(const Series& x, int n);
Series zscore(const Series& x, int n);
// Wilder-smoothed RSI.
Series rsi(const Series& close, int n = 14);
MACD macd(const Series& close, int fast = 12, int slow = 26, int signal = 9);
Bollinger bollinger(const Series& close, int n = 20, double k = 2.0);
// Wilder-smoothed Average True Range.
Series atr(const Series& high, const Series& low, const Series& close, int n = 14);
// Stochastic KDJ (K and D start at 50, smoothing 1/3).
KDJ kdj(const Series& high, const Series& low, const Series& close, int n = 9);
// Simple returns p[t]/p[t-1]-1, first element NaN.
Series pct_change(const Series& x);
// Annualised rolling volatility of simple returns (population std).
Series realized_vol(const Series& close, int n, double periods_per_year);
// Rolling window extremes (NaN warm-up; NaN inputs propagate through their window).
Series rolling_max(const Series& x, int n);
Series rolling_min(const Series& x, int n);
// Spearman rank correlation over pairs where both values are finite (average
// ranks for ties). NaN with fewer than 3 pairs or zero variance.
double spearman(const Series& x, const Series& y);
// Almgren-Chriss optimal liquidation schedule: the quantity to trade in each of
// n equal slices when kappa = sqrt(lambda * sigma^2 / eta) (risk aversion times
// variance over temporary impact). kappa -> 0 gives TWAP; larger kappa
// front-loads. Returns n non-negative quantities summing to `total`.
Series almgren_chriss(double total, int n, double kappa);

}  // namespace at
