// Risk primitives used by the Risk Management team and Portfolio Manager.
#pragma once

#include "at/indicators.hpp"

namespace at {

// Linear-interpolated quantile (matches numpy's default "linear" method). NaNs are ignored.
double quantile(const Series& x, double q);
// Historical Value-at-Risk at confidence `alpha`, returned as a positive loss fraction.
double historical_var(const Series& returns, double alpha = 0.95);
// Expected shortfall beyond the historical VaR, positive loss fraction.
double historical_cvar(const Series& returns, double alpha = 0.95);
// Kelly fraction for win probability p and win/loss payoff ratio b. Not clipped.
double kelly_fraction(double p, double b);
// Scale a directional signal in [-1, 1] so the position targets `target_vol`.
double vol_target_weight(double signal, double realized_vol_annual, double target_vol,
                         double max_leverage);
// Units to trade so that hitting `stop` loses `risk_fraction` of equity.
double position_units(double equity, double risk_fraction, double entry, double stop);

}  // namespace at
