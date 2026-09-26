#include "at/backtest.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <string>

namespace at {

double max_drawdown(const Series& equity) {
    double peak = 0.0, mdd = 0.0;
    for (double e : equity) {
        peak = std::max(peak, e);
        if (peak > 0.0) mdd = std::max(mdd, 1.0 - e / peak);
    }
    return mdd;
}

Metrics compute_metrics(const Series& equity, const Series& positions, double periods_per_year,
                        double risk_free_annual) {
    Metrics m;
    if (equity.size() < 2) return m;
    const std::size_t n = equity.size() - 1;
    m.periods = static_cast<int>(n);

    Series r(n);
    for (std::size_t i = 1; i < equity.size(); ++i) r[i - 1] = equity[i] / equity[i - 1] - 1.0;

    m.cumulative_return = equity.back() / equity.front() - 1.0;
    m.annualized_return = m.cumulative_return > -1.0
                              ? std::pow(1.0 + m.cumulative_return, periods_per_year / n) - 1.0
                              : -1.0;

    const double rf = risk_free_annual / periods_per_year;
    double mean = 0.0;
    for (double v : r) mean += v;
    mean /= n;
    double var = 0.0, down = 0.0;
    for (double v : r) {
        var += (v - mean) * (v - mean);
        const double ex = std::min(v - rf, 0.0);
        down += ex * ex;
    }
    const double sd = n > 1 ? std::sqrt(var / (n - 1)) : 0.0;
    const double dd = std::sqrt(down / n);
    const double ann = std::sqrt(periods_per_year);
    m.annualized_vol = sd * ann;
    m.sharpe = sd > 0.0 ? (mean - rf) / sd * ann : 0.0;
    m.sharpe_tstat = sd > 0.0 ? (mean - rf) / sd * std::sqrt(static_cast<double>(n)) : 0.0;
    m.sortino = dd > 0.0 ? (mean - rf) / dd * ann : 0.0;
    m.max_drawdown = max_drawdown(equity);
    m.calmar = m.max_drawdown > 0.0 ? m.annualized_return / m.max_drawdown : 0.0;

    int held = 0, wins = 0;
    double prev = 0.0, exposure = 0.0;
    for (std::size_t i = 0; i < positions.size(); ++i) {
        const double p = positions[i];
        if (p != prev) {
            ++m.num_trades;
            m.turnover += std::fabs(p - prev);
        }
        prev = p;
        if (i < n) {
            exposure += std::fabs(p);
            if (p != 0.0) {
                ++held;
                if (r[i] > 0.0) ++wins;
            }
        }
    }
    m.win_rate = held > 0 ? static_cast<double>(wins) / held : 0.0;
    m.avg_exposure = exposure / n;
    return m;
}

namespace {

void check_len(const Series& s, std::size_t T, const char* name) {
    if (!s.empty() && s.size() != T)
        throw std::invalid_argument(std::string("run_backtest: ") + name +
                                    " length does not match prices");
}

// Fill price if the protective level trades inside the next bar, else NaN.
double exit_fill(double w, double stop, double take, double o, double h, double l) {
    const double nan = std::numeric_limits<double>::quiet_NaN();
    if (w > 0.0) {
        if (!std::isnan(stop) && o <= stop) return o;   // gap through the stop
        if (!std::isnan(stop) && l <= stop) return stop;
        if (!std::isnan(take) && o >= take) return o;   // gap through the target
        if (!std::isnan(take) && h >= take) return take;
    } else if (w < 0.0) {
        if (!std::isnan(stop) && o >= stop) return o;
        if (!std::isnan(stop) && h >= stop) return stop;
        if (!std::isnan(take) && o <= take) return o;
        if (!std::isnan(take) && l <= take) return take;
    }
    return nan;
}

}  // namespace

BacktestResult run_backtest(const Series& prices, const Series& target_weights,
                            const BacktestConfig& cfg) {
    return run_backtest_ex(prices, target_weights, cfg, BacktestInputs{});
}

BacktestResult run_backtest_ex(const Series& prices, const Series& target_weights,
                               const BacktestConfig& cfg, const BacktestInputs& in) {
    if (prices.size() != target_weights.size())
        throw std::invalid_argument("run_backtest: prices and weights length mismatch");
    if (cfg.periods_per_year <= 0.0) throw std::invalid_argument("periods_per_year must be > 0");
    const std::size_t T = prices.size();
    check_len(in.carry, T, "carry");
    check_len(in.open, T, "open");
    check_len(in.high, T, "high");
    check_len(in.low, T, "low");
    check_len(in.stop, T, "stop");
    check_len(in.take, T, "take");
    check_len(in.rebalance, T, "rebalance");
    check_len(in.impact, T, "impact");
    const bool has_levels = !in.stop.empty() || !in.take.empty();
    const bool has_ohlc = !in.open.empty() && !in.high.empty() && !in.low.empty();
    if (has_levels && !has_ohlc)
        throw std::invalid_argument("run_backtest: stop/take levels need open, high and low");
    for (double p : prices)
        if (!(p > 0.0) || std::isinf(p))
            throw std::invalid_argument("run_backtest: prices must be positive and finite");

    BacktestResult res;
    res.equity.assign(T, cfg.initial_capital);
    res.returns.assign(T, 0.0);
    res.positions.assign(T, 0.0);
    if (T == 0) return res;

    const double lo = cfg.allow_short ? -cfg.max_leverage : 0.0;
    const double hi = cfg.max_leverage;
    const double unit_cost = (cfg.cost_bps + cfg.slippage_bps) / 1e4;
    const double nan = std::numeric_limits<double>::quiet_NaN();
    auto impact_k = [&](std::size_t i) {
        if (in.impact.empty() || std::isnan(in.impact[i])) return 0.0;
        return in.impact[i];
    };

    double prev = 0.0;         // weight held coming into bar t
    double prev_target = nan;  // last target seen (for re-arming without a rebalance mask)
    bool stopped = false;
    for (std::size_t t = 0; t + 1 < T; ++t) {
        double target = target_weights[t];
        if (std::isnan(target)) target = 0.0;
        target = std::clamp(target, lo, hi);

        const bool rearm = in.rebalance.empty() ? target != prev_target : in.rebalance[t] != 0.0;
        if (rearm) stopped = false;
        prev_target = target;
        const double w = stopped ? 0.0 : target;

        const double trade = w - prev;
        if (trade != 0.0) res.trades.push_back({static_cast<int>(t), prev, w, prices[t]});

        double exit_px = nan;
        if (w != 0.0 && has_levels) {
            const double s = in.stop.empty() ? nan : in.stop[t];
            const double k = in.take.empty() ? nan : in.take[t];
            exit_px = exit_fill(w, s, k, in.open[t + 1], in.high[t + 1], in.low[t + 1]);
        }
        const bool exited = !std::isnan(exit_px);
        const double px_end = exited ? exit_px : prices[t + 1];

        double carry_rate = cfg.carry_annual;
        if (!in.carry.empty()) carry_rate = std::isnan(in.carry[t]) ? 0.0 : in.carry[t];

        const double price_ret = px_end / prices[t] - 1.0;
        const double carry = w * carry_rate / cfg.periods_per_year;
        const double borrow = w < 0.0 ? -w * cfg.borrow_annual / cfg.periods_per_year : 0.0;
        const double impact_in = std::pow(std::fabs(trade), 1.5) * impact_k(t);
        double ret = w * price_ret + carry - borrow - std::fabs(trade) * unit_cost - impact_in;
        res.impact_paid += impact_in;
        if (exited) {
            const double impact_out = std::pow(std::fabs(w), 1.5) * impact_k(t + 1);
            ret -= std::fabs(w) * unit_cost + impact_out;  // cost of the exit fill
            res.impact_paid += impact_out;
            res.trades.push_back({static_cast<int>(t + 1), w, 0.0, exit_px});
            ++res.stop_exits;
            stopped = true;
        }

        res.positions[t] = w;
        res.returns[t + 1] = ret;
        res.equity[t + 1] = res.equity[t] * (1.0 + ret);
        prev = exited ? 0.0 : w;
    }
    res.positions[T - 1] = prev;  // no new trade on the final bar
    res.metrics = compute_metrics(res.equity, res.positions, cfg.periods_per_year,
                                  cfg.risk_free_annual);
    return res;
}

}  // namespace at
