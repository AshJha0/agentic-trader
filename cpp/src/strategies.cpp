#include "at/strategies.hpp"

#include <cmath>

namespace at {

Series strat_buy_hold(const Series& close) { return Series(close.size(), 1.0); }

Series strat_sma_cross(const Series& close, int fast, int slow, bool allow_short) {
    const Series f = sma(close, fast);
    const Series s = sma(close, slow);
    Series out(close.size(), 0.0);
    for (std::size_t i = 0; i < close.size(); ++i) {
        if (std::isnan(f[i]) || std::isnan(s[i])) continue;
        out[i] = f[i] > s[i] ? 1.0 : (allow_short ? -1.0 : 0.0);
    }
    return out;
}

Series strat_macd(const Series& close, int fast, int slow, int signal, bool allow_short) {
    const MACD m = macd(close, fast, slow, signal);
    Series out(close.size(), 0.0);
    for (std::size_t i = 0; i < close.size(); ++i) {
        if (std::isnan(m.hist[i])) continue;
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
            const bool oversold = r[i] < rsi_low || k.j[i] < 0.0;
            const bool overbought = r[i] > rsi_high || k.j[i] > 100.0;
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

}  // namespace at
