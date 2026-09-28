# v0.9 pre-registration: what the holdout run is allowed to mean

Written 2026-09-28, before any v0.9 stream or book was run on data after 2021-12-31, and
committed before the holdout run (`git log -- docs/evaluation/v09_preregistration.md`).

## What was chosen, and on what

Every v0.9 decision was made on the 2016–2021 design period only
(`results/v09/tables.md`, `scripts/measure_v09.py`, `scripts/combine_v09.py`; provenance in
every file). The candidates were three return streams — a multi-asset risk-parity base
(`B&H vol-target` over 11 ETFs), time-series momentum (`TSMOM(12-1)` at the vol-target size)
and FX carry (`Carry` at the desk's strategic size) — and their risk-parity combinations,
each judged against the same run's `B&H vol-target` control by a paired circular block
bootstrap over days.

Design-period verdict, stated before the holdout run: **no stream and no combination beats
its control.** The multi-asset base has Sharpe 1.02 against the v0.8 core-15 control's 1.43
on the same period; risk parity on the core 15 gives 0.91 (it overweights FX sleeves that
earn nothing); ETF trend 0.50 (−0.52 [−0.89, −0.15] p 0.007 against the base); FX carry 0.13
(+0.05 [−0.98, +1.08] against the FX control); every book with trend or carry is at or below
the base. Six books and five runs were tried; they count as trials for any deflated-Sharpe
statement in v0.9.

Because nothing cleared the bar on the design period, **nothing is adopted**: the desk's
default rules, universe and allocation stay exactly as released in v0.8.0.

## What the holdout run is

`scripts/measure_v09.py --period holdout --out results/v09/holdout` runs the same five
runs once on 2022-01-03 → 2026-06-30 and `scripts/combine_v09.py --in results/v09/holdout`
combines them the same way. It is **a report, not a choice**: whichever stream or book looks
best there will not be adopted on that basis, because the holdout was reported in v0.8 and
is spent; a stream that looks good on the holdout but not on the design period is exactly
the selection bias the protocol exists to refuse. The numbers are published with their
intervals so that a reader can see them, and so that the forward record can be compared
with them later.

## What the forward test is

From the freeze date, a daily paper-trading job records, without look-ahead and without
any further change, the returns of: the v0.8 desk on the core 15 (the incumbent), its
`B&H vol-target` and `Buy&Hold` controls, the multi-asset base (11 ETFs, risk parity,
`B&H vol-target`), and the trend and carry streams on the ETF and FX universes. That
record is the only unseen data; a candidate is adopted only when its forward Sharpe minus
its control's clears a block-bootstrap interval that excludes zero over a period long
enough for that to be possible (at Sharpe differences of the size seen here, years).
