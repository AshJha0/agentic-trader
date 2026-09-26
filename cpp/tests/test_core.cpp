// Dependency-free unit tests for the C++ core. Run via `ctest` or directly.
#include <cmath>
#include <cstdio>
#include <limits>
#include <stdexcept>
#include <string>

#include "at/backtest.hpp"
#include "at/indicators.hpp"
#include "at/risk.hpp"
#include "at/strategies.hpp"

namespace {

int failures = 0;

void check(bool ok, const std::string& what) {
    if (!ok) {
        ++failures;
        std::printf("FAIL: %s\n", what.c_str());
    }
}

bool near(double a, double b, double tol = 1e-9) { return std::fabs(a - b) <= tol; }

void test_sma_ema() {
    const at::Series x = {1, 2, 3, 4, 5};
    const auto s = at::sma(x, 3);
    check(std::isnan(s[1]) && near(s[2], 2.0) && near(s[4], 4.0), "sma");
    const auto e = at::ema(x, 3);
    // seed = mean(1,2,3) = 2; alpha = 0.5 -> 3, 4
    check(near(e[2], 2.0) && near(e[3], 3.0) && near(e[4], 4.0), "ema");
}

void test_rsi_bounds() {
    at::Series up(30);
    for (int i = 0; i < 30; ++i) up[i] = 100.0 + i;
    const auto r = at::rsi(up, 14);
    check(std::isnan(r[13]) && near(r[14], 100.0), "rsi monotone up == 100");
    at::Series flat(30, 5.0);
    check(near(at::rsi(flat, 14)[20], 50.0), "rsi flat == 50");
}

void test_bollinger_atr_kdj() {
    at::Series c(40), h(40), l(40);
    for (int i = 0; i < 40; ++i) {
        c[i] = 100 + std::sin(i * 0.3) * 5;
        h[i] = c[i] + 1;
        l[i] = c[i] - 1;
    }
    const auto b = at::bollinger(c, 20, 2.0);
    check(b.upper[30] > b.mid[30] && b.mid[30] > b.lower[30], "bollinger ordering");
    const auto a = at::atr(h, l, c, 14);
    check(std::isnan(a[12]) && a[13] >= 2.0 - 1e-12, "atr >= high-low range");
    const auto k = at::kdj(h, l, c, 9);
    check(k.k[20] >= 0 && k.k[20] <= 100, "kdj K in [0,100]");
}

void test_backtest_buy_hold() {
    const at::Series p = {100, 110, 121};
    at::BacktestConfig cfg;
    cfg.cost_bps = 0.0;
    const auto r = at::run_backtest(p, at::strat_buy_hold(p), cfg);
    check(near(r.metrics.cumulative_return, 0.21), "buy&hold CR == 21%");
    check(r.metrics.num_trades == 1, "buy&hold one trade");
    check(near(r.metrics.max_drawdown, 0.0), "no drawdown on monotone path");
}

void test_backtest_costs_and_carry() {
    const at::Series p(11, 1.0);  // flat price
    at::BacktestConfig cfg;
    cfg.cost_bps = 10.0;
    cfg.carry_annual = 0.0;
    auto r = at::run_backtest(p, at::Series(11, 1.0), cfg);
    check(near(r.equity.back(), cfg.initial_capital * (1 - 0.001)), "entry cost 10bps");

    cfg.cost_bps = 0.0;
    cfg.carry_annual = 0.0252;
    cfg.periods_per_year = 252;
    r = at::run_backtest(p, at::Series(11, 1.0), cfg);
    check(near(r.equity.back(), cfg.initial_capital * std::pow(1.0001, 10), 1e-6), "carry accrual");
}

void test_short_clip() {
    const at::Series p = {100, 90};
    at::BacktestConfig cfg;
    cfg.cost_bps = 0;
    cfg.allow_short = false;
    auto r = at::run_backtest(p, at::Series{-1, -1}, cfg);
    check(near(r.metrics.cumulative_return, 0.0), "shorts clipped when disallowed");
    cfg.allow_short = true;
    r = at::run_backtest(p, at::Series{-1, -1}, cfg);
    check(near(r.metrics.cumulative_return, 0.10), "short profits on decline");
}

at::BacktestConfig no_cost() {
    at::BacktestConfig cfg;
    cfg.cost_bps = 0.0;
    return cfg;
}

void test_stop_intraday_and_gap() {
    // Long 1.0 from 100 with a stop at 95. Bar 1 trades down to 94 -> filled at 95.
    const at::Series c = {100, 97, 99}, o = {100, 99, 97}, h = {100, 100, 99}, l = {100, 94, 96};
    at::BacktestInputs in;
    in.open = o; in.high = h; in.low = l;
    in.stop = {95, 95, 95};
    auto r = at::run_backtest_ex(c, at::Series(3, 1.0), no_cost(), in);
    check(r.stop_exits == 1, "one stop exit");
    check(near(r.equity[1], 100000 * 0.95), "stop filled at the level, not the close");
    check(near(r.equity[2], r.equity[1]), "flat after the stop until re-armed");
    // Gap: bar opens at 90, below the 95 stop -> filled at the open (worse than the stop).
    in.open = {100, 90, 97}; in.low = {100, 89, 96};
    r = at::run_backtest_ex(c, at::Series(3, 1.0), no_cost(), in);
    check(near(r.equity[1], 100000 * 0.90), "gap through the stop fills at the open");
}

void test_take_profit_and_short() {
    const at::Series c = {100, 104, 104}, o = {100, 101, 104}, h = {100, 106, 104}, l = {100, 100, 104};
    at::BacktestInputs in;
    in.open = o; in.high = h; in.low = l;
    in.take = {105, 105, 105};
    auto r = at::run_backtest_ex(c, at::Series(3, 1.0), no_cost(), in);
    check(near(r.equity[1], 100000 * 1.05), "take-profit filled at the target");
    // Short with stop 103: bar 1 high 106 -> stopped at 103, loss 3%.
    in.take.clear();
    in.stop = {103, 103, 103};
    r = at::run_backtest_ex(c, at::Series(3, -1.0), no_cost(), in);
    check(near(r.equity[1], 100000 * 0.97), "short stop above entry");
}

void test_stop_before_target_same_bar() {
    const at::Series c = {100, 100}, o = {100, 100}, h = {100, 110}, l = {100, 90};
    at::BacktestInputs in;
    in.open = o; in.high = h; in.low = l;
    in.stop = {95, 95}; in.take = {105, 105};
    auto r = at::run_backtest_ex(c, at::Series(2, 1.0), no_cost(), in);
    check(near(r.equity[1], 100000 * 0.95), "both levels in one bar: stop assumed first");
}

void test_rearm_on_rebalance() {
    const at::Series c = {100, 95, 95, 100}, o = c, h = c, l = {100, 90, 95, 95};
    at::BacktestInputs in;
    in.open = o; in.high = h; in.low = l;
    in.stop = {96, 96, 90, 90};
    in.rebalance = {1, 0, 1, 0};
    auto r = at::run_backtest_ex(c, at::Series(4, 1.0), no_cost(), in);
    check(r.stop_exits == 1 && r.positions[1] == 0.0 && r.positions[2] == 1.0,
          "stopped, then re-entered at the next rebalance");
}

void test_carry_series_and_validation() {
    const at::Series p(3, 1.0);
    at::BacktestConfig cfg = no_cost();
    cfg.periods_per_year = 100;
    at::BacktestInputs in;
    in.carry = {0.10, 0.20, 0.0};
    auto r = at::run_backtest_ex(p, at::Series(3, 1.0), cfg, in);
    check(near(r.equity.back(), 100000 * 1.001 * 1.002), "per-bar carry series");

    bool threw = false;
    try { at::run_backtest(at::Series{100, 0, 101}, at::Series(3, 1.0), cfg); }
    catch (const std::invalid_argument&) { threw = true; }
    check(threw, "non-positive price rejected");
    threw = false;
    at::BacktestInputs bad;
    bad.stop = {1, 1, 1};
    try { at::run_backtest_ex(p, at::Series(3, 1.0), cfg, bad); }
    catch (const std::invalid_argument&) { threw = true; }
    check(threw, "stop levels without OHLC rejected");
}

void test_impact_cost() {
    // Flat prices, one entry of |dw| = 1 at t = 0 with K = 0.01: cost is 1^1.5 * 0.01.
    const at::Series p(4, 100.0);
    at::BacktestInputs in;
    in.impact = {0.01, 0.01, 0.01, 0.01};
    auto r = at::run_backtest_ex(p, at::Series(4, 1.0), no_cost(), in);
    check(near(r.equity[1], 100000 * (1 - 0.01)), "entry impact = |dw|^1.5 * K");
    check(near(r.equity.back(), r.equity[1]), "no impact without a trade");
    check(near(r.impact_paid, 0.01), "impact_paid accumulates");
    // A half-size trade costs 0.5^1.5 * K: the square-root law, not linear.
    r = at::run_backtest_ex(p, at::Series(4, 0.5), no_cost(), in);
    check(near(r.equity[1], 100000 * (1 - std::pow(0.5, 1.5) * 0.01)), "square-root scaling");
    // A stop exit at t+1 pays impact at the exit bar's coefficient.
    at::BacktestInputs ex;
    ex.open = {100, 100, 100, 100}; ex.high = {100, 100, 100, 100}; ex.low = {100, 90, 100, 100};
    ex.stop = {95, 95, 95, 95};
    ex.impact = {0.0, 0.02, 0.0, 0.0};
    r = at::run_backtest_ex(p, at::Series(4, 1.0), no_cost(), ex);
    check(r.stop_exits == 1 && near(r.impact_paid, 0.02), "exit impact uses K at the exit bar");
    // NaN means no impact; length mismatch is rejected.
    at::BacktestInputs nan_in;
    nan_in.impact = at::Series(4, std::numeric_limits<double>::quiet_NaN());
    r = at::run_backtest_ex(p, at::Series(4, 1.0), no_cost(), nan_in);
    check(near(r.impact_paid, 0.0) && near(r.equity.back(), 100000.0), "NaN impact = none");
    bool threw = false;
    at::BacktestInputs bad;
    bad.impact = {0.01, 0.01};
    try { at::run_backtest_ex(p, at::Series(4, 1.0), no_cost(), bad); }
    catch (const std::invalid_argument&) { threw = true; }
    check(threw, "impact length mismatch rejected");
}

void test_exposure_and_tstat() {
    const at::Series p = {100, 101, 100, 102, 101};
    const auto r = at::run_backtest(p, at::Series{0.5, 0.5, 0.0, 0.0, 0.0}, no_cost());
    check(near(r.metrics.avg_exposure, 0.25), "average exposure = mean |w| per period");
    check(std::fabs(r.metrics.sharpe_tstat - r.metrics.sharpe * std::sqrt(4.0 / 252.0)) < 1e-12,
          "t-stat = annual Sharpe * sqrt(n / periods_per_year)");
}

void test_risk() {
    const at::Series r = {-0.05, -0.02, 0.0, 0.01, 0.03};
    check(near(at::quantile(r, 0.5), 0.0), "median");
    check(near(at::quantile(r, 0.25), -0.02), "q25");
    check(at::historical_var(r, 0.95) > 0.04, "VaR95 positive");
    check(at::historical_cvar(r, 0.95) >= at::historical_var(r, 0.95) - 1e-12, "CVaR >= VaR");
    check(near(at::kelly_fraction(0.6, 1.0), 0.2), "kelly");
    check(near(at::vol_target_weight(1.0, 0.2, 0.1, 1.0), 0.5), "vol target");
    check(near(at::position_units(100000, 0.01, 50, 48), 500), "units");
}

}  // namespace

int main() {
    test_sma_ema();
    test_rsi_bounds();
    test_bollinger_atr_kdj();
    test_backtest_buy_hold();
    test_backtest_costs_and_carry();
    test_short_clip();
    test_stop_intraday_and_gap();
    test_take_profit_and_short();
    test_stop_before_target_same_bar();
    test_rearm_on_rebalance();
    test_carry_series_and_validation();
    test_impact_cost();
    test_exposure_and_tstat();
    test_risk();
    if (failures == 0) std::printf("all C++ core tests passed\n");
    return failures == 0 ? 0 : 1;
}
