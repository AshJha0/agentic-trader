# Card: split-conformal interval sizing

Back to the [inventory](INVENTORY.md). Evidence classes are defined there.

**Status:** research. **Code:** `agentic_trader/combine.py` (`calibration_points`,
`conformal_interval`, `conformal_halfwidth`); `config["conformal"]`.

## Purpose
Put an interval around the combined forecast and scale the position by
`min(1, |mu| / half-width)`, so a forecast whose interval straddles zero trades small.

## Plain idea, then formal
Plain: look at how wrong the forecast was on recent past bars, take the error size that was
beaten 80% of the time, and use that as the error bar today.

Formal: with calibration residuals `e_1..e_n`, the half-width is the `ceil((n+1)(1-alpha))`-th
smallest `|e_i|` (Lei et al., JASA 2018). Coverage `1 - alpha` holds if the residuals are
exchangeable with the future one.

Worked example: 40 calibration residuals, alpha 0.2: rank `ceil(41 x 0.8) = 33`, so the 33rd
smallest absolute residual is the half-width.

## What changed in v0.17 (review N7)
The v0.14 design used every bar as a calibration point. Neighbouring `h`-bar returns share
`h - 1` daily returns and volatility clusters, so the residuals are not exchangeable. The v0.17
default (`design: "v17"`): calibration bars spaced `h` apart (no overlap), restricted to the
current regime when regime conditioning is on, and residuals divided by the volatility known at
their own bar, the quantile scaled back by today's volatility (normalised conformal).
`design: "v14"` reproduces the registered trial, which is pinned to it in `evaluation.TRIALS`.

## Validation evidence
- Registered v0.14 trial, design period: 0.565 vs control 0.644, p 0.33, not adopted
  (real-rules; `docs/review/PLAN.md` log 2026-11-08). Measured with the v14 design.
- v17 design on synthetic GARCH(1,1) paths with t(6) innovations, 6 seeds: overall coverage
  and high-volatility coverage near the 80% target, with high-volatility coverage above the v14
  design's (fixture; `tests/test_v17_privacy_conformal.py`,
  `test_normalised_conformal_covers_on_garch_paths`; numbers in
  `docs/review/v017_notes/L11_privacy_cards.md`).
- v17 design on real data: not run (pending). The design-trial script needs Yahoo downloads.

## Limitations
Non-overlapping points cut the calibration set by a factor of `h`; with a regime mask it can
fall below the rank `ceil((n+1)(1-alpha))`, and then the interval is unbounded and the size is
zero.

## Monitoring
`ic_interval` per decision. Empirical coverage on walk-forward data should be reported in the
evaluation doc once the v17 design is run.

## Status
Research, not adopted.
