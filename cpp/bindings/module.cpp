// pybind11 bindings exposing the C++ core as agentic_trader.quant._atcore.
// The Python wrapper (agentic_trader/quant/__init__.py) converts the results to
// numpy arrays and dataclasses so callers never see backend-specific types.
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "at/backtest.hpp"
#include "at/indicators.hpp"
#include "at/risk.hpp"
#include "at/strategies.hpp"

namespace py = pybind11;
using namespace at;

PYBIND11_MODULE(_atcore, m) {
    m.doc() = "AgenticTrader C++ quant core";

    // ---- indicators ------------------------------------------------------
    m.def("sma", &sma, py::arg("x"), py::arg("n"));
    m.def("ema", &ema, py::arg("x"), py::arg("n"));
    m.def("rolling_std", &rolling_std, py::arg("x"), py::arg("n"));
    m.def("zscore", &zscore, py::arg("x"), py::arg("n"));
    m.def("rsi", &rsi, py::arg("close"), py::arg("n") = 14);
    m.def("pct_change", &pct_change, py::arg("x"));
    m.def("realized_vol", &realized_vol, py::arg("close"), py::arg("n"),
          py::arg("periods_per_year"));
    m.def("atr", &atr, py::arg("high"), py::arg("low"), py::arg("close"), py::arg("n") = 14);
    m.def(
        "macd",
        [](const Series& c, int f, int s, int sig) {
            MACD r = macd(c, f, s, sig);
            return py::make_tuple(r.line, r.signal, r.hist);
        },
        py::arg("close"), py::arg("fast") = 12, py::arg("slow") = 26, py::arg("signal") = 9);
    m.def(
        "bollinger",
        [](const Series& c, int n, double k) {
            Bollinger b = bollinger(c, n, k);
            return py::make_tuple(b.mid, b.upper, b.lower, b.percent_b);
        },
        py::arg("close"), py::arg("n") = 20, py::arg("k") = 2.0);
    m.def(
        "kdj",
        [](const Series& h, const Series& l, const Series& c, int n) {
            KDJ r = kdj(h, l, c, n);
            return py::make_tuple(r.k, r.d, r.j);
        },
        py::arg("high"), py::arg("low"), py::arg("close"), py::arg("n") = 9);

    // ---- risk ------------------------------------------------------------
    m.def("quantile", &quantile, py::arg("x"), py::arg("q"));
    m.def("historical_var", &historical_var, py::arg("returns"), py::arg("alpha") = 0.95);
    m.def("historical_cvar", &historical_cvar, py::arg("returns"), py::arg("alpha") = 0.95);
    m.def("kelly_fraction", &kelly_fraction, py::arg("p"), py::arg("b"));
    m.def("vol_target_weight", &vol_target_weight, py::arg("signal"),
          py::arg("realized_vol_annual"), py::arg("target_vol"), py::arg("max_leverage"));
    m.def("position_units", &position_units, py::arg("equity"), py::arg("risk_fraction"),
          py::arg("entry"), py::arg("stop"));

    // ---- strategies ------------------------------------------------------
    m.def("strat_buy_hold", &strat_buy_hold, py::arg("close"));
    m.def("strat_sma_cross", &strat_sma_cross, py::arg("close"), py::arg("fast") = 20,
          py::arg("slow") = 50, py::arg("allow_short") = false);
    m.def("strat_macd", &strat_macd, py::arg("close"), py::arg("fast") = 12,
          py::arg("slow") = 26, py::arg("signal") = 9, py::arg("allow_short") = false);
    m.def("strat_kdj_rsi", &strat_kdj_rsi, py::arg("high"), py::arg("low"), py::arg("close"),
          py::arg("kdj_n") = 9, py::arg("rsi_n") = 14, py::arg("rsi_low") = 30.0,
          py::arg("rsi_high") = 70.0, py::arg("allow_short") = false);
    m.def("strat_zmr", &strat_zmr, py::arg("close"), py::arg("n") = 20, py::arg("entry") = 1.0,
          py::arg("exit") = 0.0, py::arg("allow_short") = false);

    // ---- backtest --------------------------------------------------------
    py::class_<BacktestConfig>(m, "BacktestConfig")
        .def(py::init<>())
        .def_readwrite("initial_capital", &BacktestConfig::initial_capital)
        .def_readwrite("cost_bps", &BacktestConfig::cost_bps)
        .def_readwrite("slippage_bps", &BacktestConfig::slippage_bps)
        .def_readwrite("periods_per_year", &BacktestConfig::periods_per_year)
        .def_readwrite("carry_annual", &BacktestConfig::carry_annual)
        .def_readwrite("borrow_annual", &BacktestConfig::borrow_annual)
        .def_readwrite("max_leverage", &BacktestConfig::max_leverage)
        .def_readwrite("allow_short", &BacktestConfig::allow_short)
        .def_readwrite("risk_free_annual", &BacktestConfig::risk_free_annual);

    py::class_<Metrics>(m, "Metrics")
        .def_readonly("cumulative_return", &Metrics::cumulative_return)
        .def_readonly("annualized_return", &Metrics::annualized_return)
        .def_readonly("annualized_vol", &Metrics::annualized_vol)
        .def_readonly("sharpe", &Metrics::sharpe)
        .def_readonly("sortino", &Metrics::sortino)
        .def_readonly("max_drawdown", &Metrics::max_drawdown)
        .def_readonly("calmar", &Metrics::calmar)
        .def_readonly("win_rate", &Metrics::win_rate)
        .def_readonly("num_trades", &Metrics::num_trades)
        .def_readonly("turnover", &Metrics::turnover)
        .def_readonly("periods", &Metrics::periods);

    py::class_<Trade>(m, "Trade")
        .def_readonly("index", &Trade::index)
        .def_readonly("from_weight", &Trade::from_weight)
        .def_readonly("to_weight", &Trade::to_weight)
        .def_readonly("price", &Trade::price);

    py::class_<BacktestResult>(m, "BacktestResult")
        .def_readonly("equity", &BacktestResult::equity)
        .def_readonly("returns", &BacktestResult::returns)
        .def_readonly("positions", &BacktestResult::positions)
        .def_readonly("trades", &BacktestResult::trades)
        .def_readonly("metrics", &BacktestResult::metrics);

    m.def("run_backtest", &run_backtest, py::arg("prices"), py::arg("target_weights"),
          py::arg("config"));
    m.def("compute_metrics", &compute_metrics, py::arg("equity"), py::arg("positions"),
          py::arg("periods_per_year"), py::arg("risk_free_annual") = 0.0);
    m.def("max_drawdown", &max_drawdown, py::arg("equity"));
}
