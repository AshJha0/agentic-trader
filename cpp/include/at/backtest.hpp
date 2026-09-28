// Event-free vectorised backtester shared by equity and FX.
//
// Timing convention: target weight w[t] is decided with information up to and
// including bar t and earns the return from bar t to bar t+1. There is therefore
// no look-ahead as long as w[t] only depends on data <= t.
//
// Position convention (constant units between decisions): a target is executed on
// a decision bar -- a bar where the target changes or the rebalance mask is set.
// Fees and impact on the weight change |dw| are paid out of equity first and the
// target is a fraction of what is left, so the bar's equity evolves as
//     E[t+1] = E[t] (1 - k_in) (1 + g) (1 - k_out),
// g = w r_price + w carry/ppy + cash_fraction rf/ppy - borrow (the gross return of the
// book), k_in = |dw| cost + impact, k_out the exit fill's cost when a level trades.
// Between decisions the number of units is held, so the weight drifts with the
// market, w[t+1] = w[t] (1 + r_price) / (1 + g): a 100% book stays at 100%, a
// carry-earning FX position de-levers as cash accrues. No trade and no cost is
// charged on a hold bar. The leverage cap and the short-sale flag apply to targets;
// a held position is not trimmed between decisions (the desk re-decides at every
// rebalance and the protective levels are the intrabar risk control). A target equal
// to the weight currently held is a decision to keep the position and is executed as
// no trade even when drift has carried that weight outside the cap: the cap binds on
// new targets, not on drift (run_agent_backtest passes the held weight only for a
// genuine keep, FinalDecision.kept; any other decision past the cap is trimmed).
// ``positions[t]`` is the weight actually held over (t, t+1], drifted.
//
// Cash leg: idle capital earns ``cash_rate[t]`` (annual, per bar). For funded
// positions (equities, cfg.funded = true) the cash fraction is 1 - |w|; for
// unfunded forwards (FX, cfg.funded = false) the whole account earns it and the
// carry term is the interest differential. NaN or empty = nothing credited.
//
// Market impact: a trade of |dw| at bar t costs |dw|^1.5 * K_t * sqrt(E_t / E_0) of
// equity, i.e. the coefficient supplied for the account's initial capital is
// rescaled to the equity actually traded (K is proportional to sqrt(capital)).
//
// Protective stops (run_backtest_ex): a position held over (t, t+1] with a stop
// or take-profit level is closed inside bar t+1 when the level trades. The opening
// print is known, so it is resolved first against both levels: a gap through the
// stop fills at the open, and a gap through the target fills at the open too. Only
// when neither level is through at the open is the intrabar range consulted, and if
// both the stop and the target trade in the same bar the stop is assumed to fill
// first (the conservative choice with daily bars). After an exit the position stays
// flat until the next rebalance.
//
// Ruin: once any leg of a bar consumes the whole account -- the entry cost
// ((1 - k_in) <= 0), the move ((1 + g) <= 0), the exit cost ((1 - k_out) <= 0) or the
// resulting equity (<= 0) -- the equity is floored at 0, the position is written off
// and every later bar is flat with return 0; ``ruined_at`` records the bar and the
// metrics report ``ruined``.
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
    double max_leverage = 1.0;    // |target weight| is clipped to this
    bool allow_short = true;
    double risk_free_annual = 0.0;  // constant rf for the metrics when no cash_rate series is given
    bool funded = true;           // positions are funded from the account (cash fraction 1 - |w|);
                                  // false for FX forwards (the whole account earns cash_rate)
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
    double sharpe = 0.0;        // mean / std of the excess return r_t - rf_t / ppy, annualised
    double sortino = 0.0;
    double max_drawdown = 0.0;  // positive fraction, e.g. 0.12 == -12%
    double calmar = 0.0;
    double win_rate = 0.0;
    int num_trades = 0;
    double turnover = 0.0;
    int periods = 0;
    double avg_exposure = 0.0;  // mean |weight| held per period
    double sharpe_tstat = 0.0;  // mean excess return / its standard error (= per-period SR * sqrt(n))
    bool ruined = false;        // equity reached 0; statistics stop at the ruin bar
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
    Series impact;     // square-root market-impact coefficient K_t (decimal) for an account of
                       // cfg.initial_capital: a trade of |dw| at bar t costs
                       // |dw|^1.5 * K_t * sqrt(equity_t / initial_capital) of equity on top of
                       // the bps costs, where K_t = coeff * daily_vol_t * sqrt(capital / (price_t * ADV_t)).
                       // NaN or empty = no impact.
    Series cash_rate;  // annual risk-free rate per bar credited on idle cash (see header); the
                       // metrics then use it as the per-bar rf. NaN -> 0; empty = none.
};

struct BacktestResult {
    Series equity;
    Series returns;
    Series positions;  // weight actually held over (t, t+1]
    Series traded;     // |dw| executed at each bar (exit fills at their fill bar)
    Series exits;      // 1 where a protective level filled inside the bar
    std::vector<Trade> trades;
    Metrics metrics;
    int stop_exits = 0;       // positions closed by a stop or take-profit
    double impact_paid = 0.0; // cumulative market-impact cost, as a fraction of equity
    int ruined_at = -1;       // bar at which equity reached 0, or -1
};

BacktestResult run_backtest(const Series& prices, const Series& target_weights,
                            const BacktestConfig& cfg);
BacktestResult run_backtest_ex(const Series& prices, const Series& target_weights,
                               const BacktestConfig& cfg, const BacktestInputs& in);

// Metrics of an equity curve. ``positions`` must have the same length as ``equity``
// (invalid_argument otherwise). ``risk_free_annual`` is a constant, or a per-bar
// series of the same length (NaN -> 0; empty = absent, rf 0); Sharpe, Sortino and the
// t-stat use the excess return r_t - rf_t / ppy. An excess-return series that is
// constant to rounding (sample sd <= kZeroVarianceTol * max(1, |mean|)) has no
// dispersion to divide by: Sharpe, Sortino, the t-stat and annualized_vol are 0
// rather than noise over noise (a flat book, or one earning exactly rf). The same
// tolerance applies to the downside deviation on its own: real dispersion whose only
// losses are rounding noise gives Sortino 0 while Sharpe stands. ``traded``
// (|dw| per bar) gives the turnover and trade count; without it both are inferred
// from changes in ``positions``, which drift every bar under constant units.
constexpr double kZeroVarianceTol = 1e-12;
Metrics compute_metrics(const Series& equity, const Series& positions,
                        double periods_per_year, double risk_free_annual = 0.0,
                        const Series& traded = Series{});
Metrics compute_metrics_rf(const Series& equity, const Series& positions,
                           double periods_per_year, const Series& risk_free_annual,
                           const Series& traded = Series{});

double max_drawdown(const Series& equity);

}  // namespace at
