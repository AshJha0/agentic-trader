// Dependency-free unit tests for the C++ core. Run via `ctest` or directly.
#include <cmath>
#include <cstdio>
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
    test_risk();
    if (failures == 0) std::printf("all C++ core tests passed\n");
    return failures == 0 ? 0 : 1;
}
