// Event-free vectorised backtester shared by equity and FX.
//
// Timing convention: target weight w[t] is decided with information up to and
// including bar t and earns the return from bar t to bar t+1. There is therefore
// no look-ahead as long as w[t] only depends on data <= t.
//
// Protective stops (run_backtest_ex): a position held over (t, t+1] with a stop
// or take-profit level is closed inside bar t+1 when the level trades. The fill
// is the level itself, or the open when the market gaps through it. If both the
// stop and the target trade in the same bar the stop is assumed to fill first
// (the conservative choice with daily bars). After an exit the position stays
// flat until the next rebalance.
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
    double avg_exposure = 0.0;  // mean |weight| held per period
    double sharpe_tstat = 0.0;  // mean excess return / its standard error (= per-period SR * sqrt(n))
};

// Optional per-bar inputs for run_backtest_ex. Empty vectors mean "not used";
// non-empty vectors must have the same length as the prices.
struct BacktestInputs {
    Series carry;      // annual carry rate per bar; overrides cfg.carry_annual (NaN -> 0)
    Series open;       // required together with high/low when stop or take is given
    Series high;
    Series low;
    Series stop;       // absolute stop level for the position held over (t, t+1]; NaN = none
    Series take;       // absolute take-profit level; NaN = none
    Series rebalance;  // non-zero where a new decision was made; re-arms after a stop exit.
                       // Empty: re-arm whenever the target weight changes.
};

struct BacktestResult {
    Series equity;
    Series returns;
    Series positions;  // weight actually held over (t, t+1]
    std::vector<Trade> trades;
    Metrics metrics;
    int stop_exits = 0;  // positions closed by a stop or take-profit
};

BacktestResult run_backtest(const Series& prices, const Series& target_weights,
                            const BacktestConfig& cfg);
BacktestResult run_backtest_ex(const Series& prices, const Series& target_weights,
                               const BacktestConfig& cfg, const BacktestInputs& in);

Metrics compute_metrics(const Series& equity, const Series& positions,
                        double periods_per_year, double risk_free_annual = 0.0);

double max_drawdown(const Series& equity);

}  // namespace at
