# Registered rules trials: lag0 vs lag1 vs next open (yahoo, design)

lagK: the decision taken on the close of bar t is filled at the close of bar t+K (lag0 is the same-close fill behind every number published before round 2). next open: filled at the open of bar t+1. delta: the portfolio Sharpe minus the B&H vol-target control's at the same timing; p: paired circular block bootstrap.

| trial | SR lag0 | delta lag0 | p lag0 | SR lag1 | delta lag1 | p lag1 | SR next open | delta next open | p next open |
|---|---|---|---|---|---|---|---|---|---|
| v0.2 (control) | 1.193 | -0.226 | 0.440 | 1.175 | -0.208 | 0.469 | 1.164 | -0.230 | 0.419 |
| + 12-1 month time-series momentum | 1.188 | -0.231 | 0.393 | 1.207 | -0.175 | 0.515 | 1.175 | -0.219 | 0.423 |
| + trend-filtered reversal | 1.166 | -0.253 | 0.388 | 1.141 | -0.241 | 0.407 | 1.130 | -0.264 | 0.360 |
| + abstain without data | 1.247 | -0.173 | 0.531 | 1.261 | -0.121 | 0.658 | 1.217 | -0.177 | 0.519 |
| + no-trade band 0.10 | 1.221 | -0.198 | 0.497 | 1.193 | -0.189 | 0.509 | 1.193 | -0.201 | 0.486 |
| + intraday stops | 1.177 | -0.242 | 0.457 | 1.175 | -0.207 | 0.530 | 1.160 | -0.235 | 0.468 |
| signal changes (momentum + filter + abstain) | 1.264 | -0.155 | 0.555 | 1.276 | -0.106 | 0.685 | 1.254 | -0.140 | 0.595 |
| signal changes + band | 1.276 | -0.143 | 0.581 | 1.281 | -0.102 | 0.695 | 1.263 | -0.131 | 0.618 |
| all five | 1.272 | -0.147 | 0.630 | 1.209 | -0.173 | 0.589 | 1.247 | -0.147 | 0.633 |
| strategic equity weight 0.25 | 1.273 | -0.146 | 0.578 | 1.268 | -0.114 | 0.648 | 1.248 | -0.146 | 0.571 |
| strategic equity weight 0.50 | 1.337 | -0.082 | 0.726 | 1.315 | -0.067 | 0.760 | 1.310 | -0.085 | 0.717 |
| strategic equity weight 1.00 | 1.433 | +0.014 | 0.924 | 1.355 | -0.028 | 0.832 | 1.363 | -0.031 | 0.816 |
| strategic 0.50 + band | 1.334 | -0.085 | 0.711 | 1.332 | -0.050 | 0.809 | 1.319 | -0.075 | 0.738 |
| strategic 0.50 + signal changes + band | 1.373 | -0.047 | 0.812 | 1.308 | -0.075 | 0.693 | 1.322 | -0.072 | 0.711 |
| strategic 0.50 + abstain + band | 1.330 | -0.089 | 0.703 | 1.320 | -0.062 | 0.790 | 1.304 | -0.090 | 0.707 |
| frozen v0.3: strategic 1.00 + band | 1.412 | -0.007 | 0.965 | 1.350 | -0.032 | 0.806 | 1.356 | -0.039 | 0.772 |
| + alpha analyst (significance-gated, 900-day window) | 1.373 | -0.046 | 0.718 | 1.334 | -0.048 | 0.707 | 1.317 | -0.078 | 0.544 |
| FX carry / 4, cap 0.5 | 1.447 | +0.028 | 0.850 | 1.389 | +0.007 | 0.962 | 1.394 | -0.000 | 0.998 |
| FX carry / 2, cap 0.5 (adopted) | 1.457 | +0.038 | 0.798 | 1.404 | +0.022 | 0.875 | 1.409 | +0.015 | 0.916 |
| FX carry / 4, cap 1.0 | 1.446 | +0.027 | 0.856 | 1.388 | +0.006 | 0.968 | 1.393 | -0.001 | 0.994 |
| FX carry / 8, cap 0.25 | 1.432 | +0.013 | 0.933 | 1.373 | -0.009 | 0.954 | 1.378 | -0.017 | 0.903 |
| + cross-sectional alpha analyst | 1.419 | -0.000 | 0.999 | 1.350 | -0.033 | 0.801 | 1.361 | -0.033 | 0.807 |
| EDGAR filings off | 1.457 | +0.038 | 0.798 | 1.404 | +0.022 | 0.875 | 1.409 | +0.015 | 0.916 |
| track-record size cut off | 1.467 | +0.048 | 0.746 | 1.417 | +0.035 | 0.799 | 1.420 | +0.026 | 0.854 |
| aggressive stance at the cap (v0.8 rule) | 1.456 | +0.037 | 0.775 | 1.401 | +0.019 | 0.882 | 1.423 | +0.028 | 0.836 |
| news confidence by count (v0.8 rule) | 1.457 | +0.038 | 0.798 | 1.404 | +0.022 | 0.875 | 1.409 | +0.015 | 0.916 |
| strategic equity weight 0.8 (symmetric tilt) | 1.449 | +0.030 | 0.864 | 1.407 | +0.025 | 0.886 | 1.405 | +0.010 | 0.951 |
| v0.14 IC-weighted combination (window 504) | 1.057 | -0.363 | 0.207 | 1.099 | -0.283 | 0.314 | 1.068 | -0.326 | 0.240 |
| v0.14 IC combination + HMM regime conditioning | 1.022 | -0.398 | 0.161 | 1.001 | -0.381 | 0.185 | 1.002 | -0.392 | 0.160 |
| v0.14 IC combination + conformal interval sizing | 1.119 | -0.300 | 0.172 | 1.125 | -0.257 | 0.264 | 1.107 | -0.287 | 0.192 |
| v0.17 IC combination + conformal interval sizing (non-overlapping, vol-scaled calibration) | 1.114 | -0.305 | 0.168 | 1.134 | -0.248 | 0.281 | 1.110 | -0.284 | 0.199 |
