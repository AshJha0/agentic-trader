"""``evaluate`` / ``calibrate``: the design/holdout/reserve protocol and the desk's own
judgement calibration, both of which run many decisions and take a while."""
from __future__ import annotations

import json

from .common import _config, _header, _print_usage, _symbols, default_as_of


def cmd_evaluate(args) -> int:
    from ..evaluation import PERIODS, UNIVERSES, evaluate
    cfg = _config(args)
    cfg["memory_path"] = None
    periods = {p: PERIODS[p] for p in _symbols(args.periods)}
    syms = _symbols(args.symbol) if args.symbol else UNIVERSES[args.universe]
    _header(f"evaluate {len(syms)} symbols x {list(periods)}", cfg)
    res = evaluate(syms, periods, cfg, args.every, progress=lambda m: print("  " + m, flush=True),
                   workers=args.workers, repeats=args.repeats)
    print("\n" + res.summary().to_string())
    if "universe" in res.rows and res.rows.universe.nunique() > 1:
        for u in sorted(res.rows.universe.unique()):
            print(f"\n[{u} universe]\n" + res.summary(universe=u).to_string())
    print("\n" + res.head_to_head().to_string(index=False))
    paired = res.paired_table()
    if len(paired) and (paired.n >= 3).any():
        print("\ncross-instrument bootstrap of the agent's Sharpe minus each baseline's (95% CI, two-sided p; "
              "'significant' is FDR-corrected across this table's rows, not the raw p):\n"
              + paired.to_string(index=False))
    disp = res.run_dispersion()
    if len(disp):
        print("\nacross-run dispersion of the agent's Sharpe (repeats):\n" + disp.to_string())
    if len(res.meta.get("timings", [])) > 1:
        print("\nslowest jobs:\n" + res.slowest(5).to_string(index=False))
    if res.meta["errors"]:
        print(f"\n{len(res.meta['errors'])} failures: {res.meta['errors']}")
    _print_usage(res.meta.get("usage"), res.meta.get("agent_sources"))
    if args.out:
        res.to_json(args.out)
        print(f"results written to {args.out}")
    return 0


def cmd_calibrate(args) -> int:
    from ..calibration import CalibrationReport, calibrate
    from ..graph import TradingGraph
    cfg = _config(args)
    cfg["memory_path"] = None
    anchors = tuple(None if a.lower() == "none" else float(a) for a in args.anchors.split(","))
    as_of = args.date or default_as_of().isoformat()
    _header(f"calibrate {args.symbol} as of {as_of}: {args.n} runs x anchors {list(anchors)}", cfg)
    rep = calibrate(TradingGraph(cfg), args.symbol, as_of, args.n, anchors,
                    progress=lambda m: print("  " + m, flush=True))
    print("\n" + rep.samples.to_string(index=False))
    print("\n" + json.dumps(rep.summary(), indent=1, default=str))
    if args.compare:
        print("\ndrift vs " + args.compare + ":\n" + json.dumps(rep.compare(CalibrationReport.from_json(args.compare)),
                                                              indent=1, default=str))
    _print_usage(rep.meta.get("usage"))
    if args.out:
        rep.to_json(args.out)
        print(f"report written to {args.out}")
    return 0
