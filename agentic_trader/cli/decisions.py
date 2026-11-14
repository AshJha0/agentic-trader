"""``analyze`` / ``task`` / ``scan``: one decision, one agentic-harness task, or a watchlist."""

from __future__ import annotations

import json
import sys

from ..graph import TradingGraph
from ..llm import llm_usage
from .common import _as_of, _config, _header, _print_event, _print_usage, _symbols


def cmd_analyze(args) -> int:
    cfg = _config(args)
    cfg["save_reports"] = args.save
    as_of = _as_of(args)
    graph = TradingGraph(cfg, on_event=_print_event)
    _header(f"{args.symbol} as of {as_of}", cfg)
    state, dec = graph.propagate(args.symbol, as_of, args.asset_class, args.position)
    print()
    if args.json:
        print(json.dumps(dec.to_dict(), indent=2))
    else:
        print(state.to_markdown())
    _print_usage(llm_usage(graph.llm))
    return 0


def cmd_task(args) -> int:
    """Run the agentic harness: plan -> policy-gated tools -> agents -> critic -> audited report."""
    from ..agentic import AgentHarness, Role, Task

    cfg = _config(args)
    cfg["save_reports"] = args.save
    as_of = _as_of(args)
    on_event = _print_event if args.verbose else lambda *_: None
    recorder = None
    if getattr(args, "record", None):
        from ..agentic.replay import Recorder

        recorder = Recorder(cfg, on_event=on_event)
        graph = recorder.graph
    else:
        graph = TradingGraph(cfg, on_event=on_event)
    positions = {args.symbol: args.position} if args.position is not None else None
    harness = AgentHarness(graph, positions=positions)
    _header(f"task {args.symbol} as of {as_of} role={args.role} approval={cfg['agentic']['approval']}", cfg)
    run = harness.run(Task(args.symbol, as_of, Role(args.role), args.position, args.question or ""))
    # a task that fails before planning finishes (bad symbol, planner error) has no plan
    plan_src, n_steps = (run.plan.source, len(run.plan.steps)) if run.plan else ("none", 0)
    print(
        f"state: {run.state.value}  plan: {plan_src}  steps: {n_steps}  "
        f"evidence: {len(run.evidence)}  findings: {len(run.findings)}"
    )
    for note in run.plan.notes if run.plan else ():
        print(f"  plan note: {note}")
    for e in run.errors:
        print(f"  error: {e}")
    if recorder is not None:
        from ..agentic.replay import recording_path

        path = recorder.recording(run, positions).save(recording_path(run.id, args.record))
        print(f"  recorded: {path}  (replay with: agentic-trader replay {run.id} --dir {args.record})")
    if run.state.value == "AWAITING_APPROVAL":
        for a in harness.pending_approvals(run.id):
            print(f"  awaiting approval {a.id}: {a.request.tool} {a.request.arguments} ({a.reason})")
        return 3
    if run.report is None:
        return 1
    print()
    if args.json:  # the record alone, so the output is machine-readable
        print(json.dumps(run.to_dict(), indent=2, default=str))
    else:
        print(run.report.to_markdown())
        print(f"\ntrace: {run.tracer.summary()}")
        _print_usage(llm_usage(graph.llm))
    return 0 if run.state.value == "COMPLETED" else 1


def cmd_replay(args) -> int:
    """Re-run a recorded task from its payloads (no live data, no live model); exit 0 when the
    decision and end state match the recording, 1 when they diverge, 2 on a missing payload."""
    from pathlib import Path

    from ..agentic.replay import ReplayMissingPayload, load_recording, recording_path, replay

    ref = args.task_run_id
    path = Path(ref) if ref.endswith(".pkl") else recording_path(ref, args.dir)
    if not path.is_file():
        raise FileNotFoundError(f"no recording at {path}")
    rec = load_recording(path)
    try:
        res = replay(rec, check=False)
    except ReplayMissingPayload as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(res.run.to_dict(), indent=2, default=str))
    print(
        f"replay {rec.task_id}: recorded {rec.state} {(rec.decision or {}).get('action')} -> "
        f"replayed {res.replayed_state} {(res.replayed or {}).get('action')}: "
        f"{'MATCH' if res.matches else 'DIVERGED'}"
    )
    for k, (a, b) in res.diff().items():
        print(f"  {k}: {a!r} -> {b!r}")
    return 0 if res.matches else 1


def cmd_scan(args) -> int:
    cfg = _config(args)
    cfg["memory_path"] = None
    as_of = _as_of(args)
    syms = _symbols(args.symbol)
    positions = json.loads(args.positions) if args.positions else {}
    _header(f"scan of {len(syms)} symbols as of {as_of}", cfg)
    df = TradingGraph(cfg, on_event=lambda *_: None).scan(syms, as_of, positions)
    cols = [
        c
        for c in (
            "symbol",
            "action",
            "target_weight",
            "confidence",
            "last",
            "stop_loss",
            "take_profit",
            "debate",
            "analysts_voting",
            "error",
        )
        if c in df
    ]
    print(df[cols].to_string(index=False))
    if args.out:
        (df.to_json(args.out, orient="records", indent=1) if args.out.endswith(".json") else df.to_csv(args.out, index=False))
        print(f"decisions written to {args.out}")
    return 1 if (df["action"] == "ERROR").all() else 0
