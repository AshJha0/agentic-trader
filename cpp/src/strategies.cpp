#include "at/strategies.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <vector>

namespace at {

Series strat_buy_hold(const Series& close) { return Series(close.size(), 1.0); }

// Crossover dead band: two averages of the same window of identical prices differ only
// by summation-order noise (~1e-16 relative), whose sign differs between backends. A
// gap at or below 1e-12 of the price level is no cross: the position is flat.
Series strat_sma_cross(const Series& close, int fast, int slow, bool allow_short) {
    const Series f = sma(close, fast);
    const Series s = sma(close, slow);
    Series out(close.size(), 0.0);
    for (std::size_t i = 0; i < close.size(); ++i) {
        if (std::isnan(f[i]) || std::isnan(s[i])) continue;
        const double band = 1e-12 * std::max(std::fabs(f[i]), std::fabs(s[i]));
        if (std::fabs(f[i] - s[i]) <= band) continue;
        out[i] = f[i] > s[i] ? 1.0 : (allow_short ? -1.0 : 0.0);
    }
    return out;
}

Series strat_macd(const Series& close, int fast, int slow, int signal, bool allow_short) {
    const MACD m = macd(close, fast, slow, signal);
    Series out(close.size(), 0.0);
    for (std::size_t i = 0; i < close.size(); ++i) {
        if (std::isnan(m.hist[i])) continue;
        if (std::fabs(m.hist[i]) <= 1e-12 * std::fabs(close[i])) continue;
        out[i] = m.hist[i] > 0.0 ? 1.0 : (allow_short ? -1.0 : 0.0);
    }
    return out;
}

Series strat_kdj_rsi(const Series& high, const Series& low, const Series& close, int kdj_n,
                     int rsi_n, double rsi_low, double rsi_high, bool allow_short) {
    const KDJ k = kdj(high, low, close, kdj_n);
    const Series r = rsi(close, rsi_n);
    Series out(close.size(), 0.0);
    double pos = 0.0;
    for (std::size_t i = 0; i < close.size(); ++i) {
        if (!std::isnan(k.j[i]) && !std::isnan(r[i])) {
            // J saturates at exactly 0 or 100 (K = D at the bound) up to rounding noise whose
            // sign differs between platforms; a breach has to clear 1e-9 to count.
            const bool oversold = r[i] < rsi_low || k.j[i] < -1e-9;
            const bool overbought = r[i] > rsi_high || k.j[i] > 100.0 + 1e-9;
            if (oversold)
                pos = 1.0;
            else if (overbought)
                pos = allow_short ? -1.0 : 0.0;
        }
        out[i] = pos;
    }
    return out;
}

Series strat_zmr(const Series& close, int n, double entry, double exit, bool allow_short) {
    const Series z = zscore(close, n);
    Series out(close.size(), 0.0);
    double pos = 0.0;
    for (std::size_t i = 0; i < close.size(); ++i) {
        if (!std::isnan(z[i])) {
            if (pos > 0.0 && z[i] >= -exit) pos = 0.0;
            if (pos < 0.0 && z[i] <= exit) pos = 0.0;
            if (z[i] < -entry)
                pos = 1.0;
            else if (z[i] > entry && allow_short)
                pos = -1.0;
        }
        out[i] = pos;
    }
    return out;
}

Series strat_tsmom(const Series& close, const std::vector<int>& horizons, int skip,
                   bool allow_short) {
    if (horizons.empty()) throw std::invalid_argument("horizons must not be empty");
    int longest = 0, shortest = horizons.front();
    for (int h : horizons) {
        if (h < 1) throw std::invalid_argument("horizon must be positive");
        longest = std::max(longest, h);
        shortest = std::min(shortest, h);
    }
    if (skip < 0 || skip >= shortest) throw std::invalid_argument("skip must be in [0, min horizon)");
    Series out(close.size(), 0.0);
    const double k = static_cast<double>(horizons.size());
    for (std::size_t i = static_cast<std::size_t>(longest); i < close.size(); ++i) {
        double score = 0.0;
        for (int h : horizons) {
            const double r = close[i - static_cast<std::size_t>(skip)] / close[i - static_cast<std::size_t>(h)] - 1.0;
            if (std::isfinite(r)) score += (r > 0.0) - (r < 0.0);
        }
        score /= k;
        out[i] = allow_short ? score : std::max(score, 0.0);
    }
    return out;
}

}  // namespace at
