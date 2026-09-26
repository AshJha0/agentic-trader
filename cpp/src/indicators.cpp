#include "at/indicators.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace at {
namespace {

const double NaN = std::numeric_limits<double>::quiet_NaN();

void check_window(int n) {
    if (n <= 0) throw std::invalid_argument("window must be positive");
}

std::size_t first_valid(const Series& x) {
    for (std::size_t i = 0; i < x.size(); ++i)
        if (!std::isnan(x[i])) return i;
    return x.size();
}

// Wilder smoothing seeded with the mean of the first n values starting at `start`.
Series wilder(const Series& x, int n, std::size_t start) {
    Series out(x.size(), NaN);
    const std::size_t seed = start + static_cast<std::size_t>(n) - 1;
    if (seed >= x.size()) return out;
    double acc = 0.0;
    for (std::size_t i = start; i <= seed; ++i) acc += x[i];
    double prev = acc / n;
    out[seed] = prev;
    for (std::size_t i = seed + 1; i < x.size(); ++i) {
        prev = (prev * (n - 1) + x[i]) / n;
        out[i] = prev;
    }
    return out;
}

}  // namespace

Series sma(const Series& x, int n) {
    check_window(n);
    Series out(x.size(), NaN);
    // Running sum over the current NaN-free stretch: a NaN resets it, so leading
    // NaNs (a derived series' warm-up) do not poison every later window.
    double acc = 0.0;
    int count = 0;
    for (std::size_t i = 0; i < x.size(); ++i) {
        if (std::isnan(x[i])) {
            acc = 0.0;
            count = 0;
            continue;
        }
        acc += x[i];
        if (count == n) acc -= x[i - n];
        else ++count;
        if (count == n) out[i] = acc / n;
    }
    return out;
}

Series ema(const Series& x, int n) {
    check_window(n);
    Series out(x.size(), NaN);
    const std::size_t start = first_valid(x);
    const std::size_t seed = start + static_cast<std::size_t>(n) - 1;
    if (seed >= x.size()) return out;
    double acc = 0.0;
    for (std::size_t i = start; i <= seed; ++i) acc += x[i];
    double prev = acc / n;
    out[seed] = prev;
    const double alpha = 2.0 / (n + 1.0);
    for (std::size_t i = seed + 1; i < x.size(); ++i) {
        prev = alpha * x[i] + (1.0 - alpha) * prev;
        out[i] = prev;
    }
    return out;
}

Series rolling_std(const Series& x, int n) {
    check_window(n);
    Series out(x.size(), NaN);
    for (std::size_t i = static_cast<std::size_t>(n) - 1; i < x.size(); ++i) {
        double mean = 0.0;
        for (std::size_t j = i + 1 - n; j <= i; ++j) mean += x[j];
        mean /= n;
        double var = 0.0;
        for (std::size_t j = i + 1 - n; j <= i; ++j) var += (x[j] - mean) * (x[j] - mean);
        out[i] = std::sqrt(var / n);
    }
    return out;
}

Series zscore(const Series& x, int n) {
    const Series m = sma(x, n);
    const Series s = rolling_std(x, n);
    Series out(x.size(), NaN);
    for (std::size_t i = 0; i < x.size(); ++i) {
        if (std::isnan(m[i]) || std::isnan(s[i])) continue;
        out[i] = s[i] > 0.0 ? (x[i] - m[i]) / s[i] : 0.0;
    }
    return out;
}

Series rsi(const Series& close, int n) {
    check_window(n);
    Series out(close.size(), NaN);
    if (close.size() <= static_cast<std::size_t>(n)) return out;
    Series gains(close.size(), 0.0), losses(close.size(), 0.0);
    for (std::size_t i = 1; i < close.size(); ++i) {
        const double d = close[i] - close[i - 1];
        gains[i] = d > 0 ? d : 0.0;
        losses[i] = d < 0 ? -d : 0.0;
    }
    const Series ag = wilder(gains, n, 1);
    const Series al = wilder(losses, n, 1);
    for (std::size_t i = n; i < close.size(); ++i) {
        if (al[i] == 0.0)
            out[i] = ag[i] == 0.0 ? 50.0 : 100.0;
        else
            out[i] = 100.0 - 100.0 / (1.0 + ag[i] / al[i]);
    }
    return out;
}

MACD macd(const Series& close, int fast, int slow, int signal) {
    MACD m;
    const Series ef = ema(close, fast);
    const Series es = ema(close, slow);
    m.line.assign(close.size(), NaN);
    for (std::size_t i = 0; i < close.size(); ++i)
        if (!std::isnan(ef[i]) && !std::isnan(es[i])) m.line[i] = ef[i] - es[i];
    m.signal = ema(m.line, signal);
    m.hist.assign(close.size(), NaN);
    for (std::size_t i = 0; i < close.size(); ++i)
        if (!std::isnan(m.line[i]) && !std::isnan(m.signal[i])) m.hist[i] = m.line[i] - m.signal[i];
    return m;
}

Bollinger bollinger(const Series& close, int n, double k) {
    Bollinger b;
    b.mid = sma(close, n);
    const Series s = rolling_std(close, n);
    b.upper.assign(close.size(), NaN);
    b.lower.assign(close.size(), NaN);
    b.percent_b.assign(close.size(), NaN);
    for (std::size_t i = 0; i < close.size(); ++i) {
        if (std::isnan(b.mid[i])) continue;
        b.upper[i] = b.mid[i] + k * s[i];
        b.lower[i] = b.mid[i] - k * s[i];
        const double w = b.upper[i] - b.lower[i];
        b.percent_b[i] = w > 0.0 ? (close[i] - b.lower[i]) / w : 0.5;
    }
    return b;
}

Series atr(const Series& high, const Series& low, const Series& close, int n) {
    check_window(n);
    if (high.size() != close.size() || low.size() != close.size())
        throw std::invalid_argument("atr: high/low/close length mismatch");
    Series tr(close.size(), NaN);
    for (std::size_t i = 0; i < close.size(); ++i) {
        if (i == 0) {
            tr[i] = high[i] - low[i];
        } else {
            tr[i] = std::max({high[i] - low[i], std::fabs(high[i] - close[i - 1]),
                              std::fabs(low[i] - close[i - 1])});
        }
    }
    return wilder(tr, n, 0);
}

KDJ kdj(const Series& high, const Series& low, const Series& close, int n) {
    check_window(n);
    if (high.size() != close.size() || low.size() != close.size())
        throw std::invalid_argument("kdj: high/low/close length mismatch");
    KDJ r;
    r.k.assign(close.size(), NaN);
    r.d.assign(close.size(), NaN);
    r.j.assign(close.size(), NaN);
    double k = 50.0, d = 50.0;
    for (std::size_t i = static_cast<std::size_t>(n) - 1; i < close.size(); ++i) {
        double hh = high[i], ll = low[i];
        for (std::size_t j = i + 1 - n; j <= i; ++j) {
            hh = std::max(hh, high[j]);
            ll = std::min(ll, low[j]);
        }
        const double rsv = hh > ll ? (close[i] - ll) / (hh - ll) * 100.0 : 50.0;
        k = 2.0 / 3.0 * k + rsv / 3.0;
        d = 2.0 / 3.0 * d + k / 3.0;
        r.k[i] = k;
        r.d[i] = d;
        r.j[i] = 3.0 * k - 2.0 * d;
    }
    return r;
}

Series pct_change(const Series& x) {
    Series out(x.size(), NaN);
    for (std::size_t i = 1; i < x.size(); ++i)
        out[i] = x[i - 1] != 0.0 ? x[i] / x[i - 1] - 1.0 : NaN;
    return out;
}

Series rolling_max(const Series& x, int n) {
    check_window(n);
    Series out(x.size(), NaN);
    for (std::size_t i = static_cast<std::size_t>(n) - 1; i < x.size(); ++i) {
        double m = -std::numeric_limits<double>::infinity();
        bool bad = false;
        for (std::size_t j = i + 1 - n; j <= i; ++j) {
            if (std::isnan(x[j])) { bad = true; break; }
            m = std::max(m, x[j]);
        }
        if (!bad) out[i] = m;
    }
    return out;
}

Series rolling_min(const Series& x, int n) {
    check_window(n);
    Series out(x.size(), NaN);
    for (std::size_t i = static_cast<std::size_t>(n) - 1; i < x.size(); ++i) {
        double m = std::numeric_limits<double>::infinity();
        bool bad = false;
        for (std::size_t j = i + 1 - n; j <= i; ++j) {
            if (std::isnan(x[j])) { bad = true; break; }
            m = std::min(m, x[j]);
        }
        if (!bad) out[i] = m;
    }
    return out;
}

namespace {

// Average ranks (1-based) with ties sharing the mean rank.
Series average_ranks(const Series& v) {
    std::vector<std::size_t> idx(v.size());
    for (std::size_t i = 0; i < v.size(); ++i) idx[i] = i;
    std::stable_sort(idx.begin(), idx.end(), [&](std::size_t a, std::size_t b) { return v[a] < v[b]; });
    Series r(v.size());
    std::size_t i = 0;
    while (i < idx.size()) {
        std::size_t j = i;
        while (j + 1 < idx.size() && v[idx[j + 1]] == v[idx[i]]) ++j;
        const double avg = (static_cast<double>(i) + static_cast<double>(j)) / 2.0 + 1.0;
        for (std::size_t k = i; k <= j; ++k) r[idx[k]] = avg;
        i = j + 1;
    }
    return r;
}

}  // namespace

double spearman(const Series& x, const Series& y) {
    if (x.size() != y.size()) throw std::invalid_argument("spearman: length mismatch");
    Series a, b;
    for (std::size_t i = 0; i < x.size(); ++i) {
        if (std::isfinite(x[i]) && std::isfinite(y[i])) {
            a.push_back(x[i]);
            b.push_back(y[i]);
        }
    }
    if (a.size() < 3) return NaN;
    const Series ra = average_ranks(a), rb = average_ranks(b);
    const double n = static_cast<double>(a.size());
    double ma = 0, mb = 0;
    for (std::size_t i = 0; i < a.size(); ++i) { ma += ra[i]; mb += rb[i]; }
    ma /= n; mb /= n;
    double sab = 0, saa = 0, sbb = 0;
    for (std::size_t i = 0; i < a.size(); ++i) {
        sab += (ra[i] - ma) * (rb[i] - mb);
        saa += (ra[i] - ma) * (ra[i] - ma);
        sbb += (rb[i] - mb) * (rb[i] - mb);
    }
    if (saa <= 0.0 || sbb <= 0.0) return NaN;
    return sab / std::sqrt(saa * sbb);
}

Series almgren_chriss(double total, int n, double kappa) {
    if (n <= 0) throw std::invalid_argument("almgren_chriss: n must be positive");
    if (!(kappa >= 0.0)) throw std::invalid_argument("almgren_chriss: kappa must be >= 0");
    Series out(n, 0.0);
    if (kappa < 1e-8) {  // risk-neutral limit: uniform (TWAP)
        for (int k = 0; k < n; ++k) out[k] = total / n;
        return out;
    }
    // Remaining inventory x(t) = X sinh(kappa (T - t)) / sinh(kappa T) with T = 1.
    const double denom = std::sinh(kappa);
    double prev = total;
    for (int k = 1; k <= n; ++k) {
        const double t = static_cast<double>(k) / n;
        const double remaining = total * std::sinh(kappa * (1.0 - t)) / denom;
        out[k - 1] = prev - remaining;
        prev = remaining;
    }
    return out;
}

Series realized_vol(const Series& close, int n, double periods_per_year) {
    check_window(n);
    const Series r = pct_change(close);
    Series out(close.size(), NaN);
    for (std::size_t i = static_cast<std::size_t>(n); i < close.size(); ++i) {
        double mean = 0.0;
        for (std::size_t j = i + 1 - n; j <= i; ++j) mean += r[j];
        mean /= n;
        double var = 0.0;
        for (std::size_t j = i + 1 - n; j <= i; ++j) var += (r[j] - mean) * (r[j] - mean);
        out[i] = std::sqrt(var / n) * std::sqrt(periods_per_year);
    }
    return out;
}

}  // namespace at
