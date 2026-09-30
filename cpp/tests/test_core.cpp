// Dependency-free unit tests for the C++ core. Run via `ctest` or directly.
#include <cmath>
#include <cstdio>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>

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
    // Direct window sums: a running sum left ~1e-16 of cancellation noise after the 1.0
    // dropped out, which the tiny final window read as its mean (zscore +1 instead of -1).
    const at::Series tiny = {1.0, 1.17549435e-38, 1.17549435e-38, 0.0};
    const auto st = at::sma(tiny, 2);
    const auto z = at::zscore(tiny, 2);
    check(near(st[3], 0.5 * 1.17549435e-38, 1e-50) && near(z[3], -1.0) && near(z[1], -1.0) && z[2] == 0.0,
          "sma direct window sums (no running-sum drift)");
    const at::Series gap = {1.0, std::nan(""), 2.0, 3.0};
    const auto g = at::sma(gap, 2);
    check(std::isnan(g[2]) && near(g[3], 2.5), "sma window straddling a NaN is NaN");
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
    // Constant units: carry accrues on the held notional (linear), it is not reinvested
    // into a larger position each bar (which would compound 1.0001^10).
    check(near(r.equity.back(), cfg.initial_capital * 1.001, 1e-6), "carry accrual on constant notional");
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
    check(near(r.equity.back(), 100000 * (1 + 0.001 + 0.002)), "per-bar carry series (linear on constant notional)");

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
    // Bar 1 holds the units bought at bar 0: the weight has drifted to 0.5 * 1.01 / 1.005.
    const double drifted = 0.5 * 1.01 / 1.005;
    check(near(r.positions[1], drifted), "held weight drifts with the price between decisions");
    check(near(r.metrics.avg_exposure, (0.5 + drifted) / 4.0), "average exposure = mean |w| per period");
    check(std::fabs(r.metrics.sharpe_tstat - r.metrics.sharpe * std::sqrt(4.0 / 252.0)) < 1e-12,
          "t-stat = annual Sharpe * sqrt(n / periods_per_year)");
}

// v0.8: constant units between decisions (finding 79).
void test_constant_units_between_decisions() {
    const at::Series p = {100, 110, 110, 121};
    at::BacktestConfig cfg = no_cost();
    cfg.cost_bps = 10.0;
    auto r = at::run_backtest(p, at::Series(4, 0.5), cfg);
    // Entry: fee 10 bps * 0.5 out of equity, then 0.5 * 10% on the rest; hold: no trade, no cost.
    check(near(r.equity[1], 100000 * (1 - 0.0005) * 1.05), "entry cost then return");
    check(near(r.equity[2], r.equity[1]), "no cost on a hold bar");
    const double w1 = 0.5 * 1.1 / 1.05;
    check(near(r.positions[1], w1) && near(r.positions[2], w1), "units held: weight drifts once, then flat price");
    check(near(r.equity[3], r.equity[2] * (1 + w1 * 0.1)), "drifted weight earns the next move");
    check(r.metrics.num_trades == 1 && near(r.metrics.turnover, 0.5), "one trade, turnover 0.5");
    check(near(r.traded[0], 0.5) && near(r.traded[1], 0.0), "traded records |dw| per bar");
    // A rebalance back to the same target is a trade (the drift correction) and is charged.
    at::BacktestInputs in;
    in.rebalance = {1, 1, 0, 0};
    r = at::run_backtest_ex(p, at::Series(4, 0.5), cfg, in);
    check(near(r.positions[1], 0.5) && near(r.metrics.turnover, 0.5 + std::fabs(0.5 - w1)),
          "rebalancing to the same target charges the drift correction");
}

// v0.8: ruin floor (finding 18).
void test_ruin_floor() {
    const at::Series p = {10, 10, 24, 20, 15, 12};
    at::BacktestConfig cfg;
    cfg.cost_bps = 1.0;
    const auto r = at::run_backtest(p, at::Series(6, -1.0), cfg);
    check(near(r.equity[1], 99990.0) && r.equity[2] == 0.0 && r.equity[5] == 0.0, "equity floored at 0");
    check(r.returns[2] == -1.0 && r.returns[3] == 0.0 && r.returns[5] == 0.0, "-100% then 0");
    check(r.positions[2] == 0.0 && r.positions[5] == 0.0 && r.ruined_at == 2, "flat after ruin");
    check(r.metrics.ruined && near(r.metrics.max_drawdown, 1.0) && near(r.metrics.cumulative_return, -1.0),
          "metrics report ruin");
    check(near(r.metrics.win_rate, 0.0), "post-ruin bars are not counted as live");
    const auto ok = at::run_backtest(at::Series{100, 110, 121}, at::Series(3, 1.0), no_cost());
    check(!ok.metrics.ruined && ok.ruined_at == -1, "no ruin flag on a live account");
}

// v0.8 verification: ruin is tested per factor, not on their product (finding 18).
void test_ruin_per_factor() {
    // Fee alone (k_in = 3 * 0.5 = 1.5 > 1) and the move alone (3 * -80%) each ruin the account;
    // their product (-0.5 * -1.4) is positive and used to survive with equity 70000.
    at::BacktestConfig cfg;
    cfg.cost_bps = 5000.0;
    cfg.max_leverage = 3.0;
    cfg.allow_short = false;
    auto r = at::run_backtest(at::Series{100, 20, 25}, at::Series(3, 3.0), cfg);
    check(r.ruined_at == 1 && r.equity[1] == 0.0 && r.equity[2] == 0.0 && r.returns[1] == -1.0,
          "entry cost and move both negative: ruined, not a positive product");
    check(r.positions[1] == 0.0 && r.positions[2] == 0.0 && r.metrics.ruined, "flat after per-factor ruin");
    // Impact form: |dw| = 2, K = 0.5 -> k_in = 2^1.5 * 0.5 = 1.41 > 1 on a -80% bar at 2x.
    at::BacktestInputs in;
    in.impact = at::Series(3, 0.5);
    cfg.cost_bps = 0.0;
    r = at::run_backtest_ex(at::Series{100, 20, 25}, at::Series(3, 2.0), cfg, in);
    check(r.ruined_at == 1 && r.equity[1] == 0.0, "entry impact >= 100%: ruined");
    // Exit-cost form: a stop gapped through on a -80% bar at 2x (move factor -0.6) with an
    // exit impact of 141% (exit factor -0.41); the product is +0.25.
    const double nan = std::numeric_limits<double>::quiet_NaN();
    at::BacktestInputs ex;
    ex.open = {100, 20, 25}; ex.high = {100, 20, 25}; ex.low = {100, 20, 25};
    ex.stop = {99.0, nan, nan};
    ex.impact = {0.0, 0.5, 0.0};
    at::BacktestConfig c2;
    c2.cost_bps = 0.0;
    c2.max_leverage = 2.0;
    r = at::run_backtest_ex(at::Series{100, 20, 25}, at::Series(3, 2.0), c2, ex);
    check(r.stop_exits == 1 && r.ruined_at == 1 && r.equity[1] == 0.0, "exit impact >= 100%: ruined");
    // A growth so small that equity[t] * (1 + ret) rounds to 0 is ruin on that bar, not the next.
    at::BacktestConfig c3;
    c3.cost_bps = 1e4;
    c3.allow_short = false;
    const double w = std::nextafter(1.0, 0.0);
    r = at::run_backtest(at::Series{100, 50, 60}, at::Series(3, w), c3);
    check(r.ruined_at == 1 && r.equity[1] == 0.0 && r.returns[2] == 0.0 && r.positions[1] == 0.0,
          "equity reaching 0 sets the ruin flag on that bar");
    // Unchanged where a single factor is merely negative.
    const auto ok = at::run_backtest(at::Series{100, 110, 121}, at::Series(3, 1.0), no_cost());
    check(!ok.metrics.ruined && ok.ruined_at == -1, "no ruin on a live account");
}

// v0.8: a gap through the take-profit fills at the open, never at the stop (finding 21).
void test_gap_through_take_profit() {
    at::BacktestInputs in;
    in.open = {100, 112}; in.high = {100, 115}; in.low = {100, 88};
    in.stop = {90, 90}; in.take = {110, 110};
    auto r = at::run_backtest_ex(at::Series{100, 100}, at::Series(2, 1.0), no_cost(), in);
    check(near(r.equity[1], 112000.0) && r.trades.back().price == 112.0, "long: gap through the take fills at the open");
    in.open = {100, 88}; in.high = {100, 112}; in.low = {100, 85};
    in.stop = {110, 110}; in.take = {90, 90};
    r = at::run_backtest_ex(at::Series{100, 100}, at::Series(2, -1.0), no_cost(), in);
    check(near(r.equity[1], 112000.0) && r.trades.back().price == 88.0, "short: gap through the take fills at the open");
    // Open inside both levels: the intrabar rule still fills the stop first.
    in.open = {100, 100}; in.high = {100, 112}; in.low = {100, 85};
    r = at::run_backtest_ex(at::Series{100, 100}, at::Series(2, -1.0), no_cost(), in);
    check(near(r.equity[1], 90000.0), "short: both levels intrabar -> stop first");
}

// v0.8: cash leg (finding 14).
void test_cash_leg_and_excess_metrics() {
    const at::Series p(3, 100.0);
    at::BacktestConfig cfg = no_cost();
    cfg.periods_per_year = 252;
    at::BacktestInputs in;
    in.cash_rate = {0.0252, std::numeric_limits<double>::quiet_NaN(), 0.0252};
    auto r = at::run_backtest_ex(p, at::Series(3, 0.5), cfg, in);
    check(near(r.equity[1], 100000 * (1 + 0.5 * 1e-4)) && near(r.equity[2], r.equity[1]),
          "funded: idle cash (1-|w|) earns the rate; NaN credits nothing");
    cfg.funded = false;
    r = at::run_backtest_ex(p, at::Series(3, 0.5), cfg, in);
    check(near(r.equity[1], 100000 * (1 + 1e-4)), "unfunded (FX): the whole account earns the rate");
    // Excess-return Sharpe with a per-bar rf equals the constant-rf Sharpe when rf is constant.
    const at::Series e = {100, 101, 100.5, 102, 103};
    const at::Series pos(5, 1.0);
    const auto a = at::compute_metrics(e, pos, 252, 0.03);
    const auto b = at::compute_metrics_rf(e, pos, 252, at::Series(5, 0.03));
    check(near(a.sharpe, b.sharpe) && near(a.sortino, b.sortino) && near(a.sharpe_tstat, b.sharpe_tstat),
          "per-bar rf == constant rf when constant");
    const auto c = at::compute_metrics_rf(e, pos, 252, at::Series{0.0, 0.0, 0.0, 0.0, 0.0});
    check(near(c.sharpe, at::compute_metrics(e, pos, 252, 0.0).sharpe), "zero series == rf 0");
    // Hand-computed excess-return Sharpe with a varying rf: mean / std (ddof 1) of r_t - rf_t / ppy.
    const at::Series rf = {0.01, 0.02, 0.03, 0.04, 0.05};
    double ex[4], mean = 0.0;
    for (int i = 0; i < 4; ++i) { ex[i] = e[i + 1] / e[i] - 1.0 - rf[i] / 252.0; mean += ex[i] / 4.0; }
    double var = 0.0;
    for (double v : ex) var += (v - mean) * (v - mean) / 3.0;
    const auto d = at::compute_metrics_rf(e, pos, 252, rf);
    check(near(d.sharpe, mean / std::sqrt(var) * std::sqrt(252.0), 1e-12), "excess-return Sharpe with per-bar rf");
    bool threw = false;
    try { at::compute_metrics(e, at::Series(3, 1.0), 252); }
    catch (const std::invalid_argument&) { threw = true; }
    check(threw, "compute_metrics rejects a positions length mismatch");
}

// v0.8: impact rescales with the equity actually traded (finding 23).
void test_impact_scales_with_equity() {
    const at::Series p = {100, 200, 200, 200};
    at::BacktestInputs in;
    in.impact = {0.0, 0.0, 0.01, 0.0};
    auto r = at::run_backtest_ex(p, at::Series{1, 1, 0, 0}, no_cost(), in);
    check(near(r.equity[1], 200000.0) && near(r.positions[1], 1.0), "doubling keeps a 100% book at 100%");
    check(near(r.impact_paid, 0.01 * std::sqrt(2.0)), "K_t scaled by sqrt(equity / initial capital)");
    check(near(r.equity[3], 200000.0 * (1 - 0.01 * std::sqrt(2.0))), "impact charged at the scaled coefficient");
}

// v0.8: crossovers ignore rounding noise on flat windows (finding 20).
void test_crossover_dead_band() {
    for (double level : {1.08, 7e5, 0.3333333}) {
        const at::Series flat(120, level);
        const auto s = at::strat_sma_cross(flat, 20, 50, true);
        const auto m = at::strat_macd(flat, 12, 26, 9, true);
        bool all_flat = true;
        for (std::size_t i = 0; i < flat.size(); ++i) all_flat = all_flat && s[i] == 0.0 && m[i] == 0.0;
        check(all_flat, "flat series -> no position");
    }
    at::Series up(120);
    for (int i = 0; i < 120; ++i) up[i] = 100.0 + i;
    check(at::strat_sma_cross(up, 20, 50, true).back() == 1.0, "a real trend is still a signal");
}

// v0.8: one NaN bar affects only the window it touches, on every indicator (finding 76).
void test_nan_recovery() {
    at::Series c(80), h(80), l(80);
    for (int i = 0; i < 80; ++i) {
        c[i] = 100 + std::sin(i * 0.37) * 5 + 0.05 * i;
        h[i] = c[i] + 1;
        l[i] = c[i] - 1;
    }
    const auto clean_rsi = at::rsi(c, 14);
    const int k = 40;
    at::Series cn = c, hn = h, ln = l;
    cn[k] = hn[k] = ln[k] = std::nan("");
    auto span = [](const at::Series& v, int from) {
        int first = -1, last = -1;
        for (std::size_t i = from; i < v.size(); ++i)
            if (std::isnan(v[i])) { if (first < 0) first = static_cast<int>(i); last = static_cast<int>(i); }
        return std::pair<int, int>(first, last);
    };
    const auto e = at::ema(cn, 10);
    check(span(e, 20) == std::make_pair(k, k + 9) && !std::isnan(e[k + 10]), "ema: NaN for k..k+n-1, then recovers");
    const auto r = at::rsi(cn, 14);
    check(span(r, 20) == std::make_pair(k, k + 14) && !std::isnan(r[k + 15]), "rsi: NaN for k..k+n (two changes lost)");
    check(near(r[k - 1], clean_rsi[k - 1]), "rsi unchanged before the gap");
    const auto a = at::atr(hn, ln, cn, 14);
    check(span(a, 20) == std::make_pair(k, k + 14) && !std::isnan(a[k + 15]), "atr: NaN for k..k+n, then recovers");
    const auto m = at::macd(cn, 12, 26, 9);
    check(span(m.hist, 39) == std::make_pair(k, k + 33) && !std::isnan(m.hist[k + 34]), "macd hist: slow + signal - 1 bars");
    // ema still skips leading NaNs.
    const auto lead = at::ema(at::Series{std::nan(""), std::nan(""), 1.0, 2.0, 3.0}, 3);
    check(std::isnan(lead[3]) && near(lead[4], 2.0), "ema skips leading NaNs");
}

// v0.8: Almgren-Chriss never overflows (findings 19 / 33).
void test_almgren_chriss_stable() {
    for (double kappa : {1e-6, 1e-3, 0.5, 3.0, 50.0, 700.0, 1e4, 1e6}) {
        const auto q = at::almgren_chriss(1.0, 78, kappa);
        double sum = 0.0;
        bool finite = true;
        for (double v : q) { sum += v; finite = finite && std::isfinite(v) && v >= -1e-15; }
        check(finite && near(sum, 1.0, 1e-9), "schedule finite, non-negative and sums to total");
    }
    check(near(at::almgren_chriss(1.0, 78, 1e4)[0], 1.0, 1e-12), "huge kappa: everything in the first slice");
    // Matches the textbook sinh form where that form is representable.
    const auto q = at::almgren_chriss(1.0, 5, 3.0);
    double prev = 1.0;
    for (int k = 1; k <= 5; ++k) {
        const double rem = std::sinh(3.0 * (1.0 - k / 5.0)) / std::sinh(3.0);
        check(near(q[k - 1], prev - rem, 1e-14), "stable form == sinh form");
        prev = rem;
    }
    const auto tiny = at::almgren_chriss(1.0, 4, 1e-6);
    check(near(tiny[0], 0.25, 1e-6) && near(tiny[3], 0.25, 1e-6), "small kappa -> TWAP without cancellation");
    for (double bad : {std::numeric_limits<double>::infinity(), std::numeric_limits<double>::quiet_NaN(), -1.0}) {
        bool threw = false;
        try { at::almgren_chriss(1.0, 78, bad); } catch (const std::invalid_argument&) { threw = true; }
        check(threw, "non-finite or negative kappa throws");
    }
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

// v0.8 regression review (a): a constant excess return has no dispersion to divide by.
void test_zero_variance_metrics() {
    const at::Series flat(250, 100.0);
    at::BacktestConfig cfg = no_cost();
    cfg.periods_per_year = 252;
    cfg.risk_free_annual = 0.03;
    auto r = at::run_backtest(flat, at::Series(250, 0.0), cfg);
    check(r.metrics.sharpe == 0.0 && r.metrics.sharpe_tstat == 0.0 && r.metrics.sortino == 0.0 &&
              r.metrics.annualized_vol == 0.0,
          "flat book with a constant rf: Sharpe, Sortino, t-stat and vol are 0, not -8e15");
    at::BacktestInputs in;
    in.cash_rate.resize(250);
    for (int i = 0; i < 250; ++i) in.cash_rate[i] = 0.03 + 0.004 * std::sin(i * 0.37);
    cfg.risk_free_annual = 0.0;
    r = at::run_backtest_ex(flat, at::Series(250, 0.0), cfg, in);
    check(r.metrics.sharpe == 0.0 && r.metrics.sharpe_tstat == 0.0 && r.metrics.sortino == 0.0 &&
              r.metrics.annualized_vol == 0.0,
          "flat book earning exactly a varying rf: 0/0/0, not rounding noise over rounding noise");
    // an equity curve compounding at exactly rf (the portfolio path)
    at::Series e(400), rf(400);
    e[0] = 100000.0;
    for (int i = 0; i < 400; ++i) rf[i] = 0.02 + 0.03 * i / 399.0;
    for (int i = 0; i + 1 < 400; ++i) e[i + 1] = e[i] * (1.0 + rf[i] / 252.0);
    const auto z = at::compute_metrics_rf(e, at::Series(400, 1.0), 252, rf, at::Series(400, 0.0));
    check(z.sharpe == 0.0 && z.sharpe_tstat == 0.0 && z.sortino == 0.0 && z.annualized_vol == 0.0,
          "curve at exactly rf: 0/0/0");
    // genuine dispersion, however small, is untouched
    at::Series e2(6);
    e2[0] = 100000.0;
    const double rr[5] = {1e-4, 1.1e-4, 0.9e-4, 1.05e-4, 0.95e-4};
    for (int i = 0; i < 5; ++i) e2[i + 1] = e2[i] * (1.0 + rr[i]);
    const auto m = at::compute_metrics(e2, at::Series(6, 1.0), 252, 0.0, at::Series(6, 0.0));
    check(m.sharpe > 10.0 && m.annualized_vol > 0.0, "a series with real dispersion keeps its Sharpe");
    // final review (a): the rule applies to the downside deviation on its own. Real dispersion (five
    // winning bars held long) whose only negative excess returns are the rounding noise of flat
    // bars under a cash leg has no downside to divide by: Sortino 0, Sharpe untouched.
    at::Series px(30, 100.0);
    for (int i = 1; i < 6; ++i) px[i] = 100.0 * std::pow(1.005, i);
    for (int i = 6; i < 30; ++i) px[i] = px[5];
    at::Series wl(30, 0.0);
    for (int i = 0; i < 5; ++i) wl[i] = 1.0;
    at::BacktestInputs leg;
    leg.cash_rate.resize(30);
    for (int i = 0; i < 30; ++i) leg.cash_rate[i] = 0.03 + 0.004 * std::sin(i * 0.37);
    cfg.risk_free_annual = 0.0;
    const auto n = at::run_backtest_ex(px, wl, cfg, leg);
    int noise = 0;
    for (int i = 1; i < 30; ++i) {
        const double ex = n.returns[i] - leg.cash_rate[i - 1] / 252.0;
        if (ex < 0.0 && ex > -1e-14) ++noise;
    }
    check(noise > 5, "the fixture's only losses are rounding noise on flat bars");
    check(n.metrics.sharpe > 5.0 && n.metrics.annualized_vol > 0.02, "real dispersion keeps its Sharpe and vol");
    check(n.metrics.sortino == 0.0, "Sortino is 0 when only the downside is rounding noise (was +2.8e14)");
    // a genuine loss, however small next to the noise, still gives a finite Sortino
    at::Series e3(n.equity);
    e3[20] *= 1.0 - 1e-6;
    const auto g = at::compute_metrics_rf(e3, n.positions, 252, leg.cash_rate, n.traded);
    check(g.sortino > 0.0 && g.sortino < 1e6 && g.sharpe > 5.0, "one real losing bar: a finite Sortino");
}

// v0.8 regression review (e): a target equal to the held weight is a keep, not clamped.
void test_keep_at_cap_is_no_trade() {
    const at::Series p(12, 100.0);
    at::BacktestConfig cfg = no_cost();
    cfg.borrow_annual = 0.05;
    cfg.max_leverage = 1.0;
    at::BacktestInputs in;
    in.rebalance.assign(12, 0.0);
    in.rebalance[0] = in.rebalance[5] = 1.0;
    at::BacktestInputs pre;
    pre.rebalance.assign(in.rebalance.begin(), in.rebalance.begin() + 6);
    const double held = at::run_backtest_ex(at::Series(6, 100.0), at::Series(6, -1.0), cfg, pre).positions[5];
    check(held < -1.0, "borrow de-levers a capped short past the cap");
    at::Series keep(12, -1.0);
    for (int i = 5; i < 12; ++i) keep[i] = held;
    const auto r = at::run_backtest_ex(p, keep, cfg, in);
    check(r.trades.size() == 1 && r.traded[5] == 0.0 && r.metrics.num_trades == 1,
          "a keep at the cap books no cap-enforcement trade (was a +0.00099 trim)");
    check(r.positions[5] == held && r.positions[6] < held, "the held weight is kept and keeps drifting");
    at::Series trim(12, -1.0);
    for (int i = 5; i < 12; ++i) trim[i] = -1.5;
    const auto t = at::run_backtest_ex(p, trim, cfg, in);
    check(t.trades.size() == 2 && t.positions[5] == -1.0 && near(t.traded[5], -held - 1.0),
          "a new target outside the cap is still clamped");
    const auto t2 = at::run_backtest_ex(p, at::Series(12, -1.0), cfg, in);
    check(t2.trades.size() == 2 && t2.positions[5] == -1.0, "a new target at the cap while held past it is a trim");
}

}  // namespace

static void test_tsmom() {
    at::Series up, down;
    for (int i = 0; i < 12; ++i) {
        up.push_back(100.0 + i);
        down.push_back(100.0 - i);
    }
    const auto u = at::strat_tsmom(up, {2, 5});
    check(u[4] == 0.0 && u[5] == 1.0 && u.back() == 1.0, "tsmom is flat until the longest horizon, then long a rise");
    check(at::strat_tsmom(down, {2, 5}).back() == -1.0, "tsmom is short a fall");
    check(at::strat_tsmom(down, {2, 5}, 0, false).back() == 0.0, "long-only tsmom goes flat, not short");
    at::Series mixed = up;   // 12 bars up, then a dip shorter than the long horizon
    mixed.push_back(108.0);
    const auto m = at::strat_tsmom(mixed, {1, 10});
    check(m.back() == 0.0, "opposed horizons average to zero");
    bool threw = false;
    try {
        at::strat_tsmom(up, {5}, 5);
    } catch (const std::invalid_argument&) {
        threw = true;
    }
    check(threw, "skip at or beyond the shortest horizon is refused");
}

int main() {
    test_tsmom();
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
    test_constant_units_between_decisions();
    test_ruin_floor();
    test_ruin_per_factor();
    test_gap_through_take_profit();
    test_cash_leg_and_excess_metrics();
    test_impact_scales_with_equity();
    test_crossover_dead_band();
    test_nan_recovery();
    test_almgren_chriss_stable();
    test_zero_variance_metrics();
    test_keep_at_cap_is_no_trade();
    if (failures == 0) std::printf("all C++ core tests passed\n");
    return failures == 0 ? 0 : 1;
}
