// Standalone C++ baseline backtester.
//
//   at_backtest <prices.csv> [--fx] [--short] [--cost-bps X] [--carry X] [--ppy N]
//
// The CSV needs a header row containing a Close (or "Adj Close") column; High and
// Low are optional (Close is used when missing). Rows must be in date order.
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "at/backtest.hpp"
#include "at/strategies.hpp"

namespace {

std::vector<std::string> split(const std::string& line) {
    std::vector<std::string> out;
    std::stringstream ss(line);
    std::string cell;
    while (std::getline(ss, cell, ',')) {
        while (!cell.empty() && (cell.back() == '\r' || cell.back() == ' ')) cell.pop_back();
        out.push_back(cell);
    }
    return out;
}

int find_col(const std::vector<std::string>& header, const std::string& name) {
    for (std::size_t i = 0; i < header.size(); ++i)
        if (header[i] == name) return static_cast<int>(i);
    return -1;
}

void usage() {
    std::cerr << "usage: at_backtest <prices.csv> [--fx] [--short] [--cost-bps X] "
                 "[--carry X] [--ppy N]\n";
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        usage();
        return 2;
    }
    at::BacktestConfig cfg;
    cfg.allow_short = false;  // equities default to long-only; --short or --fx enables shorts
    bool fx = false;
    for (int i = 2; i < argc; ++i) {
        const std::string a = argv[i];
        auto next = [&]() -> double {
            if (i + 1 >= argc) {
                usage();
                std::exit(2);
            }
            return std::atof(argv[++i]);
        };
        if (a == "--fx") fx = true;
        else if (a == "--short") cfg.allow_short = true;
        else if (a == "--cost-bps") cfg.cost_bps = next();
        else if (a == "--carry") cfg.carry_annual = next();
        else if (a == "--ppy") cfg.periods_per_year = next();
        else {
            usage();
            return 2;
        }
    }
    if (fx) {
        cfg.allow_short = true;
        if (cfg.periods_per_year == 252.0) cfg.periods_per_year = 260.0;  // FX trades 5d/wk all year
    }

    std::ifstream in(argv[1]);
    if (!in) {
        std::cerr << "cannot open " << argv[1] << "\n";
        return 1;
    }
    std::string line;
    std::getline(in, line);
    const auto header = split(line);
    int ci = find_col(header, "Close");
    if (ci < 0) ci = find_col(header, "Adj Close");
    const int hi = find_col(header, "High");
    const int li = find_col(header, "Low");
    if (ci < 0) {
        std::cerr << "CSV needs a Close column\n";
        return 1;
    }
    at::Series close, high, low;
    int skipped = 0;
    auto field = [](const std::vector<std::string>& cells, int i, double fallback) {
        if (i < 0 || i >= static_cast<int>(cells.size())) return fallback;
        const double v = std::atof(cells[i].c_str());
        return v > 0.0 ? v : fallback;  // blank / non-numeric / non-positive -> fallback
    };
    while (std::getline(in, line)) {
        const auto cells = split(line);
        const double c = field(cells, ci, 0.0);
        if (!(c > 0.0)) {  // blank, non-numeric or non-positive close: not a tradable bar
            ++skipped;
            continue;
        }
        close.push_back(c);
        high.push_back(std::max(field(cells, hi, c), c));
        low.push_back(std::min(field(cells, li, c), c));
    }
    if (skipped) std::cerr << "skipped " << skipped << " rows without a positive close\n";
    if (close.size() < 60) {
        std::cerr << "need at least 60 rows, got " << close.size() << "\n";
        return 1;
    }

    const bool s = cfg.allow_short;
    struct Named {
        const char* name;
        at::Series w;
    };
    const std::vector<Named> strategies = {
        {"Buy&Hold", at::strat_buy_hold(close)},
        {"SMA(20/50)", at::strat_sma_cross(close, 20, 50, s)},
        {"MACD", at::strat_macd(close, 12, 26, 9, s)},
        {"KDJ+RSI", at::strat_kdj_rsi(high, low, close, 9, 14, 30, 70, s)},
        {"ZMR", at::strat_zmr(close, 20, 1.0, 0.0, s)},
    };

    std::printf("%-12s %9s %9s %8s %8s %8s %7s\n", "Strategy", "CR%", "AR%", "Sharpe", "MDD%",
                "Win%", "Trades");
    try {
        for (const auto& st : strategies) {
            const auto r = at::run_backtest(close, st.w, cfg);
            const auto& m = r.metrics;
            std::printf("%-12s %9.2f %9.2f %8.2f %8.2f %8.1f %7d\n", st.name,
                        100 * m.cumulative_return, 100 * m.annualized_return, m.sharpe,
                        100 * m.max_drawdown, 100 * m.win_rate, m.num_trades);
        }
    } catch (const std::exception& e) {
        std::cerr << "error: " << e.what() << "\n";
        return 1;
    }
    return 0;
}
