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
                        double risk_free_annual, const Series& traded) {
    return compute_metrics_rf(equity, positions, periods_per_year,
                              Series(equity.size(), risk_free_annual), traded);
}

Metrics compute_metrics_rf(const Series& equity, const Series& positions, double periods_per_year,
                           const Series& risk_free_annual, const Series& traded) {
    if (positions.size() != equity.size())
        throw std::invalid_argument("compute_metrics: positions and equity length mismatch");
    if (!risk_free_annual.empty() && risk_free_annual.size() != equity.size())
        throw std::invalid_argument("compute_metrics: risk_free_annual length does not match equity");
    if (!traded.empty() && traded.size() != equity.size())
        throw std::invalid_argument("compute_metrics: traded length does not match equity");
    Metrics m;
    if (equity.size() < 2) return m;
    const std::size_t n = equity.size() - 1;
    m.periods = static_cast<int>(n);

    // Statistics stop at the ruin bar: a dead account has no returns to measure.
    std::size_t live = n;
    if (!(equity[0] > 0.0)) {
        live = 0;
        m.ruined = true;
    }
    Series r(n);
    for (std::size_t i = 0; i < n; ++i) {
        r[i] = equity[i] > 0.0 ? equity[i + 1] / equity[i] - 1.0 : 0.0;
        if (!m.ruined && equity[i + 1] <= 0.0) {
            live = i + 1;
            m.ruined = true;
        }
    }

    m.cumulative_return = equity.front() > 0.0 ? equity.back() / equity.front() - 1.0
                                               : std::numeric_limits<double>::quiet_NaN();
    m.annualized_return = m.cumulative_return > -1.0
                              ? std::pow(1.0 + m.cumulative_return, periods_per_year / n) - 1.0
                              : -1.0;

    Series ex(live);
    double mean = 0.0;
    for (std::size_t i = 0; i < live; ++i) {
        const double rf = risk_free_annual.empty() || std::isnan(risk_free_annual[i])
                              ? 0.0
                              : risk_free_annual[i];
        ex[i] = r[i] - rf / periods_per_year;
        mean += ex[i];
    }
    if (live > 0) mean /= live;
    double var = 0.0, down = 0.0;
    for (double v : ex) {
        var += (v - mean) * (v - mean);
        const double d = std::min(v, 0.0);
        down += d * d;
    }
    const double sd = live > 1 ? std::sqrt(var / (live - 1)) : 0.0;
    const double dd = live > 0 ? std::sqrt(down / live) : 0.0;
    const double ann = std::sqrt(periods_per_year);
    m.annualized_vol = sd * ann;
    m.sharpe = sd > 0.0 ? mean / sd * ann : 0.0;
    m.sharpe_tstat = sd > 0.0 ? mean / sd * std::sqrt(static_cast<double>(live)) : 0.0;
    m.sortino = dd > 0.0 ? mean / dd * ann : 0.0;
    m.max_drawdown = max_drawdown(equity);
    m.calmar = m.max_drawdown > 0.0 ? m.annualized_return / m.max_drawdown : 0.0;

    int held = 0, wins = 0;
    double exposure = 0.0;
    for (std::size_t i = 0; i < n; ++i) {
        exposure += std::fabs(positions[i]);
        if (i < live && positions[i] != 0.0) {
            ++held;
            if (r[i] > 0.0) ++wins;
        }
    }
    if (traded.empty()) {
        double prev = 0.0;
        for (double p : positions) {
            if (p != prev) {
                ++m.num_trades;
                m.turnover += std::fabs(p - prev);
            }
            prev = p;
        }
    } else {
        for (double d : traded) {
            if (d != 0.0) ++m.num_trades;
            m.turnover += d;
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

// Fill price if a protective level trades inside the next bar, else NaN. The open is
// resolved first against both levels (a gap through either fills at the open); only
// then is the intrabar range consulted, stop before target.
double exit_fill(double w, double stop, double take, double o, double h, double l) {
    const double nan = std::numeric_limits<double>::quiet_NaN();
    if (w > 0.0) {
        if (!std::isnan(stop) && o <= stop) return o;
        if (!std::isnan(take) && o >= take) return o;
        if (!std::isnan(stop) && l <= stop) return stop;
        if (!std::isnan(take) && h >= take) return take;
    } else if (w < 0.0) {
        if (!std::isnan(stop) && o >= stop) return o;
        if (!std::isnan(take) && o <= take) return o;
        if (!std::isnan(stop) && h >= stop) return stop;
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
    if (!(cfg.initial_capital > 0.0) || std::isinf(cfg.initial_capital))
        throw std::invalid_argument("initial_capital must be positive and finite");
    const std::size_t T = prices.size();
    check_len(in.carry, T, "carry");
    check_len(in.open, T, "open");
    check_len(in.high, T, "high");
    check_len(in.low, T, "low");
    check_len(in.stop, T, "stop");
    check_len(in.take, T, "take");
    check_len(in.rebalance, T, "rebalance");
    check_len(in.impact, T, "impact");
    check_len(in.cash_rate, T, "cash_rate");
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
    res.traded.assign(T, 0.0);
    res.exits.assign(T, 0.0);
    if (T == 0) return res;

    const double lo = cfg.allow_short ? -cfg.max_leverage : 0.0;
    const double hi = cfg.max_leverage;
    const double unit_cost = (cfg.cost_bps + cfg.slippage_bps) / 1e4;
    const double ppy = cfg.periods_per_year;
    const double nan = std::numeric_limits<double>::quiet_NaN();
    auto impact_k = [&](std::size_t i) {
        if (in.impact.empty() || std::isnan(in.impact[i])) return 0.0;
        return in.impact[i];
    };

    double prev = 0.0;         // weight held coming into bar t (drifted since the last trade)
    double prev_target = nan;  // last target seen (a change is a decision)
    bool stopped = false, ruined = false;
    for (std::size_t t = 0; t + 1 < T; ++t) {
        double target = target_weights[t];
        if (std::isnan(target)) target = 0.0;
        target = std::clamp(target, lo, hi);

        const bool rearm = in.rebalance.empty() ? target != prev_target : in.rebalance[t] != 0.0;
        const bool decide = rearm || target != prev_target;
        if (rearm) stopped = false;
        prev_target = target;
        const double w = (ruined || stopped) ? 0.0 : (decide ? target : prev);

        const double trade = w - prev;
        if (trade != 0.0) {
            res.trades.push_back({static_cast<int>(t), prev, w, prices[t]});
            res.traded[t] += std::fabs(trade);
        }

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
        double cash_rate = 0.0;
        if (!in.cash_rate.empty() && !std::isnan(in.cash_rate[t])) cash_rate = in.cash_rate[t];

        // Costs come out of equity before the position is put on, so w is a fraction of
        // post-cost equity: E_{t+1} = E_t (1 - k_in) (1 + g) (1 - k_out), with g the gross return
        // of the book and k the fee + impact fractions. A 100% book therefore stays at 100%.
        const double gross = px_end / prices[t];  // kept as a ratio: 1 + (gross - 1) loses digits on a huge move
        const double price_ret = gross - 1.0;
        const double carry = w * carry_rate / ppy;
        const double cash = (cfg.funded ? 1.0 - std::fabs(w) : 1.0) * cash_rate / ppy;
        const double borrow = w < 0.0 ? -w * cfg.borrow_annual / ppy : 0.0;
        const double scale = std::sqrt(res.equity[t] / cfg.initial_capital);
        const double impact_in = trade != 0.0 ? std::pow(std::fabs(trade), 1.5) * impact_k(t) * scale : 0.0;
        const double k_in = std::fabs(trade) * unit_cost + impact_in;
        const double g = w * price_ret + carry + cash - borrow;
        const double f_in = 1.0 - k_in;
        const double f_g = 1.0 + g;
        double f_out = 1.0;
        double growth = f_in * f_g;
        res.impact_paid += impact_in;
        if (exited) {
            const double impact_out = std::pow(std::fabs(w), 1.5) * impact_k(t + 1) * scale;
            f_out = 1.0 - (std::fabs(w) * unit_cost + impact_out);  // cost of the exit fill
            growth *= f_out;
            res.impact_paid += impact_out;
            res.trades.push_back({static_cast<int>(t + 1), w, 0.0, exit_px});
            res.traded[t + 1] += std::fabs(w);
            res.exits[t + 1] = 1.0;
            ++res.stop_exits;
            stopped = true;
        }

        // Each factor is a fraction of the account left after one leg of the bar (entry cost,
        // the move, the exit cost); any one of them reaching zero is ruin, whatever the product.
        double ret = growth - 1.0;
        double next = res.equity[t] * (1.0 + ret);
        if (ruined) {
            ret = 0.0;
            next = res.equity[t];
        } else if (f_in <= 0.0 || f_g <= 0.0 || f_out <= 0.0 || next <= 0.0) {
            ret = -1.0;
            next = 0.0;
            ruined = true;
            res.ruined_at = static_cast<int>(t + 1);
        }
        res.positions[t] = w;
        res.returns[t + 1] = ret;
        res.equity[t + 1] = next;
        prev = (exited || ruined || w == 0.0) ? 0.0 : w * gross / (1.0 + g);
    }
    res.positions[T - 1] = prev;  // no new trade on the final bar
    res.metrics = in.cash_rate.empty()
                      ? compute_metrics(res.equity, res.positions, ppy, cfg.risk_free_annual, res.traded)
                      : compute_metrics_rf(res.equity, res.positions, ppy, in.cash_rate, res.traded);
    res.metrics.num_trades = static_cast<int>(res.trades.size());
    return res;
}

}  // namespace at
