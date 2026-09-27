"""``tools`` / ``serve`` / ``mcp`` / ``info``: the operational commands (tool catalogue,
HTTP API, MCP stdio server, effective configuration)."""
from __future__ import annotations

import json

from .. import quant
from ..config import make_config
from .common import _config


def cmd_tools(args) -> int:
    from ..agentic import DeskTools, build_registry
    from ..data import get_provider
    cfg = _config(args)
    reg = build_registry(DeskTools(get_provider(cfg), cfg))
    if args.json:
        print(json.dumps(reg.catalogue(), indent=1))
        return 0
    print(f"{len(reg)} tools on {len(reg.servers())} servers")
    for d in reg.descriptors():
        flags = ("read-only" if d.annotations.read_only else "STATE-CHANGING") + f", {d.annotations.risk.value} risk"
        args_ = ", ".join(d.input_schema.get("properties", {}))
        print(f"  {d.name:<26} ({args_})  [{flags}]\n      {d.description.splitlines()[0]}")
    return 0


def cmd_serve(args) -> int:
    from ..agentic.api import serve
    cfg = _config(args)
    if args.task_db:
        cfg["agentic"]["task_db"] = args.task_db
    if args.workers is not None:
        cfg["agentic"]["workers"] = args.workers
    scheme = "https" if args.ssl_cert else "http"
    print(f"serving on {scheme}://{args.host}:{args.port}  (docs at /docs; approvals "
          f"{cfg['agentic']['approval']}; task store {args.task_db or 'in memory'}; "
          f"{args.processes} process(es) x {cfg['agentic']['workers']} task threads)")
    serve(args.host, args.port, cfg, ssl_certfile=args.ssl_cert, ssl_keyfile=args.ssl_key,
          allow_dev_keys=args.allow_dev_keys, processes=args.processes)
    return 0


def cmd_mcp(args) -> int:
    from ..agentic.mcp_server import main as mcp_main
    argv = ["--data", args.data, "--role", args.role] + (["--csv-dir", args.csv_dir] if args.csv_dir else [])
    if args.approval:
        argv += ["--approval", args.approval]
    return mcp_main(argv)


def cmd_info(args) -> int:
    print(f"quant backend: {quant.BACKEND}")
    print(json.dumps(make_config(), indent=2))
    return 0
