// Event-free vectorised backtester shared by equity and FX.
//
// Timing convention: target weight w[t] is decided with information up to and
// including bar t and earns the return from bar t to bar t+1. There is therefore
// no look-ahead as long as w[t] only depends on data <= t.
#pragma once

#include <string>
#include <vector>

#include "at/indicators.hpp"

namespace at {

struct BacktestConfig {
    double initial_capital = 100000.0;
    double cost_bps = 1.0;        // commission / half-spread per unit of turnover, in bps
    double slippage_bps = 0.0;    // extra execution slippage per unit of turnover, in bps
    double periods_per_year = 252.0;
    double carry_annual = 0.0;    // FX: base-rate minus quote-rate earned by a +1 position (decimal p.a.)
    double borrow_annual = 0.0;   // equity: annual borrow fee charged on short exposure (decimal p.a.)
    double max_leverage = 1.0;    // |w| is clipped to this
    bool allow_short = true;
    double risk_free_annual = 0.0;
};

struct Trade {
    int index = 0;
    double from_weight = 0.0;
    double to_weight = 0.0;
    double price = 0.0;
};

struct Metrics {
    double cumulative_return = 0.0;
    double annualized_return = 0.0;
    double annualized_vol = 0.0;
    double sharpe = 0.0;
    double sortino = 0.0;
    double max_drawdown = 0.0;  // positive fraction, e.g. 0.12 == -12%
    double calmar = 0.0;
    double win_rate = 0.0;
    int num_trades = 0;
    double turnover = 0.0;
    int periods = 0;
};

struct BacktestResult {
    Series equity;
    Series returns;
    Series positions;  // weight actually held over (t, t+1]
    std::vector<Trade> trades;
    Metrics metrics;
};

BacktestResult run_backtest(const Series& prices, const Series& target_weights,
                            const BacktestConfig& cfg);

Metrics compute_metrics(const Series& equity, const Series& positions,
                        double periods_per_year, double risk_free_annual = 0.0);

double max_drawdown(const Series& equity);

}  // namespace at
