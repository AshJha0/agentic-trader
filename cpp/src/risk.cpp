#include "at/risk.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

namespace at {

double quantile(const Series& x, double q) {
    if (std::isnan(q)) return std::numeric_limits<double>::quiet_NaN();
    Series v;
    v.reserve(x.size());
    for (double e : x)
        if (!std::isnan(e)) v.push_back(e);
    if (v.empty()) return std::numeric_limits<double>::quiet_NaN();
    std::sort(v.begin(), v.end());
    q = std::clamp(q, 0.0, 1.0);
    const double pos = q * (v.size() - 1);
    const std::size_t lo = static_cast<std::size_t>(std::floor(pos));
    const std::size_t hi = std::min(lo + 1, v.size() - 1);
    const double frac = pos - lo;
    return v[lo] + (v[hi] - v[lo]) * frac;
}

double historical_var(const Series& returns, double alpha) {
    const double q = quantile(returns, 1.0 - alpha);
    return std::isnan(q) ? 0.0 : std::max(0.0, -q);
}

double historical_cvar(const Series& returns, double alpha) {
    const double q = quantile(returns, 1.0 - alpha);
    if (std::isnan(q)) return 0.0;
    double acc = 0.0;
    int cnt = 0;
    for (double r : returns) {
        if (!std::isnan(r) && r <= q) {
            acc += r;
            ++cnt;
        }
    }
    return cnt > 0 ? std::max(0.0, -acc / cnt) : 0.0;
}

double kelly_fraction(double p, double b) {
    if (b <= 0.0) return 0.0;
    return p - (1.0 - p) / b;
}

double vol_target_weight(double signal, double realized_vol_annual, double target_vol,
                         double max_leverage) {
    if (std::isnan(realized_vol_annual) || realized_vol_annual <= 0.0) return 0.0;
    const double w = signal * target_vol / realized_vol_annual;
    return std::clamp(w, -max_leverage, max_leverage);
}

double position_units(double equity, double risk_fraction, double entry, double stop) {
    const double per_unit = std::fabs(entry - stop);
    if (per_unit <= 0.0) return 0.0;
    return equity * risk_fraction / per_unit;
}

}  // namespace at
