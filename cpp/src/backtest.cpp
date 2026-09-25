#include "at/backtest.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>

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
    m.sortino = dd > 0.0 ? (mean - rf) / dd * ann : 0.0;
    m.max_drawdown = max_drawdown(equity);
    m.calmar = m.max_drawdown > 0.0 ? m.annualized_return / m.max_drawdown : 0.0;

    int held = 0, wins = 0;
    double prev = 0.0;
    for (std::size_t i = 0; i < positions.size(); ++i) {
        const double p = positions[i];
        if (p != prev) {
            ++m.num_trades;
            m.turnover += std::fabs(p - prev);
        }
        prev = p;
        if (i < n && p != 0.0) {
            ++held;
            if (r[i] > 0.0) ++wins;
        }
    }
    m.win_rate = held > 0 ? static_cast<double>(wins) / held : 0.0;
    return m;
}

BacktestResult run_backtest(const Series& prices, const Series& target_weights,
                            const BacktestConfig& cfg) {
    if (prices.size() != target_weights.size())
        throw std::invalid_argument("run_backtest: prices and weights length mismatch");
    if (cfg.periods_per_year <= 0.0) throw std::invalid_argument("periods_per_year must be > 0");

    BacktestResult res;
    const std::size_t T = prices.size();
    res.equity.assign(T, cfg.initial_capital);
    res.returns.assign(T, 0.0);
    res.positions.assign(T, 0.0);
    if (T == 0) return res;

    const double lo = cfg.allow_short ? -cfg.max_leverage : 0.0;
    const double hi = cfg.max_leverage;
    const double unit_cost = (cfg.cost_bps + cfg.slippage_bps) / 1e4;

    double prev = 0.0;
    for (std::size_t t = 0; t + 1 < T; ++t) {
        double w = target_weights[t];
        if (std::isnan(w)) w = 0.0;
        w = std::clamp(w, lo, hi);

        const double trade = w - prev;
        if (trade != 0.0) res.trades.push_back({static_cast<int>(t), prev, w, prices[t]});

        const double price_ret = prices[t + 1] / prices[t] - 1.0;
        const double carry = w * cfg.carry_annual / cfg.periods_per_year;
        const double borrow = w < 0.0 ? -w * cfg.borrow_annual / cfg.periods_per_year : 0.0;
        const double ret = w * price_ret + carry - borrow - std::fabs(trade) * unit_cost;

        res.positions[t] = w;
        res.returns[t + 1] = ret;
        res.equity[t + 1] = res.equity[t] * (1.0 + ret);
        prev = w;
    }
    res.positions[T - 1] = prev;  // no new trade on the final bar
    res.metrics = compute_metrics(res.equity, res.positions, cfg.periods_per_year,
                                  cfg.risk_free_annual);
    return res;
}

}  // namespace at
