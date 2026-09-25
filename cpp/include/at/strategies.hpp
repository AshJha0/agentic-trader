// Rule-based baselines from the TradingAgents paper's evaluation (B&H, MACD,
// KDJ+RSI, ZMR, SMA). Each returns a target-weight series in {-1, 0, 1}
// (or {0, 1} when allow_short is false) suitable for run_backtest.
#pragma once

#include "at/indicators.hpp"

namespace at {

Series strat_buy_hold(const Series& close);
Series strat_sma_cross(const Series& close, int fast = 20, int slow = 50, bool allow_short = false);
Series strat_macd(const Series& close, int fast = 12, int slow = 26, int signal = 9,
                  bool allow_short = false);
Series strat_kdj_rsi(const Series& high, const Series& low, const Series& close, int kdj_n = 9,
                     int rsi_n = 14, double rsi_low = 30.0, double rsi_high = 70.0,
                     bool allow_short = false);
// Z-score mean reversion: enter when |z| > entry, exit when z crosses back through exit.
Series strat_zmr(const Series& close, int n = 20, double entry = 1.0, double exit = 0.0,
                 bool allow_short = false);

}  // namespace at
