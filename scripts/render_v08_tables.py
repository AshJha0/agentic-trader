"""Render every v0.8 table in the documentation from results/v08 (see scripts/measure_v08.py).

No number in docs/evaluation/evaluation.md, README.md or docs/index.html is typed by hand:
this script prints the markdown tables (and writes them to results/v08/tables.md) and the
documentation pastes them. Sections whose inputs are missing are skipped with a note.

    .venv\\Scripts\\python.exe scripts/render_v08_tables.py [--in results/v08] [--section name]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentic_trader.backtest import AGENT  # noqa: E402
from agentic_trader.evaluation import EvaluationResult, trial_slug  # noqa: E402
from agentic_trader.stats import paired_bootstrap, paired_sharpe_block_bootstrap, selection_report  # noqa: E402

PERIODS = ("design", "holdout", "q1_2024", "reserve")
BASELINES = ("Buy&Hold", "B&H vol-target", "SMA(20/50)", "MACD", "KDJ+RSI", "ZMR")
OUT: list[str] = []


def emit(title: str, body: str) -> None:
    OUT.append(f"### {title}\n\n{body.strip()}\n")


def md(df: pd.DataFrame, index: bool = True, floatfmt: str = ".2f") -> str:
    df = df.copy()
    if index:
        df = df.reset_index()
    cols = list(df.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |",
             "|" + "|".join("--:" if pd.api.types.is_numeric_dtype(df[c]) else ":--" for c in cols) + "|"]
    for _, row in df.iterrows():
        cells = []
        for c in cols:
            v = row[c]
            if isinstance(v, (float, np.floating)):
                cells.append("" if not np.isfinite(v) else format(v, floatfmt))
            elif isinstance(v, (bool, np.bool_)):
                cells.append("yes" if v else "")
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def load_eval(path: Path) -> EvaluationResult | None:
    return EvaluationResult.from_json(path) if path.exists() else None


def load_json(path: Path) -> dict | None:
    return json.load(open(path, encoding="utf-8")) if path.exists() else None


# ------------------------------------------------------------------ eval_main
def subset(res: EvaluationResult, universes: tuple[str, ...] | None) -> EvaluationResult:
    if universes is None:
        return res
    return EvaluationResult(res.rows[res.rows["universe"].isin(universes)].reset_index(drop=True), res.meta)


# The documentation's three slices: the 15 instruments every rule choice was made on, the 45
# that no choice consulted (sector equities, macro ETFs and FX crosses), and all 60.
SLICES = (("core (15)", ("core",)), ("extended (45)", ("extended", "extended-macro")), ("all 60", None))


def section_headline(res: EvaluationResult) -> None:
    for label, universes in SLICES[:2]:
        view = subset(res, universes)
        for period in PERIODS:
            s = view.summary(period=period)
            if len(s):
                emit(f"summary: {label}, {period}", md(s))
        emit(f"head to head: {label}", md(view.head_to_head(), index=False))
    for label, universes in SLICES:
        view = subset(res, universes)
        emit(f"paired Sharpe, agent minus baseline: {label} (scheme column: clusters needs 5 groups)",
             md(view.paired_table("Sharpe"), index=False))
    for metric in ("MDD%", "Calmar"):
        for label, universes in SLICES[:2]:
            t = subset(res, universes).paired_table(metric)
            t = t[t["baseline"].isin(["Buy&Hold", "B&H vol-target"])] if "baseline" in t else t
            emit(f"paired {metric}, agent minus control: {label}", md(t, index=False))


def section_asset_class(res: EvaluationResult) -> None:
    """The headline summaries and the paired controls split by asset class. The documents'
    drawdown statements were made for equities, and on FX the vol-target control is the
    shared position cap, so the split says which comparison has a control at all. The
    equity rows of the extended slice include its 9 macro ETFs (asset_class "equity")."""
    for label, universes in SLICES[:2]:
        view = subset(res, universes)
        for ac in sorted(view.rows["asset_class"].astype(str).unique()):
            sub = EvaluationResult(view.rows[view.rows["asset_class"] == ac].reset_index(drop=True), view.meta)
            n = sub.rows["symbol"].nunique()
            for period in PERIODS:
                s = sub.summary(period=period)
                if len(s):
                    emit(f"summary by asset class: {label} {ac} ({n}), {period}", md(s))
            for metric in ("Sharpe", "MDD%"):
                t = sub.paired_table(metric)
                t = t[t["baseline"].isin(["Buy&Hold", "B&H vol-target"])] if "baseline" in t else t
                emit(f"paired {metric} by asset class, agent minus control: {label} {ac} ({n})", md(t, index=False))


def agent_sharpe(res: EvaluationResult) -> pd.DataFrame:
    r = res.rows[res.rows["strategy"] == AGENT]
    return r.groupby(["period", "symbol"], as_index=False).agg(
        Sharpe=("Sharpe", "mean"), asset_class=("asset_class", "first"), universe=("universe", "first"))


def section_recheck(a: EvaluationResult, b: EvaluationResult, title: str, universes=("core", "extended")) -> None:
    """Agent Sharpe under a minus under b, per period and universe, with the cross-instrument
    bootstrap (clusters when the rows carry 5 groups, instruments otherwise)."""
    sa, sb = agent_sharpe(a), agent_sharpe(b)
    both = sa.merge(sb[["period", "symbol", "Sharpe"]], on=["period", "symbol"], suffixes=("_a", "_b"))
    rows = []
    for period in PERIODS:
        for universe in list(universes) + ["all"]:
            sub = both[both["period"] == period]
            if universe == "core":
                sub = sub[sub["universe"] == "core"]
            elif universe == "extended":
                sub = sub[sub["universe"].isin(["extended", "extended-macro"])]
            if len(sub) < 3:
                continue
            groups = (sub["asset_class"] + ":" + sub["universe"]).to_numpy()
            pb = paired_bootstrap(sub["Sharpe_a"].to_numpy(), sub["Sharpe_b"].to_numpy(), groups=groups)
            rows.append({"period": period, "universe": universe, "n": pb.n,
                         "mean Sharpe (a)": sub["Sharpe_a"].mean(), "mean Sharpe (b)": sub["Sharpe_b"].mean(),
                         "mean diff": pb.mean_diff, "95% CI": f"[{pb.ci_low:+.2f}, {pb.ci_high:+.2f}]",
                         "p": pb.p_value, "scheme": pb.scheme, "wins": f"{pb.wins} / {pb.n}"})
    emit(title, md(pd.DataFrame(rows), index=False))


# --------------------------------------------------------------- portfolios
def diff_line(d: dict) -> str:
    return f"{d['diff']:+.2f} [{d['ci_low']:+.2f}, {d['ci_high']:+.2f}] p={d['p_value']:.3f} (n={d['n']} days, block {d['block']})"


def section_portfolio(p: dict, title: str) -> None:
    t = pd.DataFrame(p["table"]).T
    emit(f"portfolio: {title}", md(t))
    if "sharpe_vs_vol_target" in p:
        emit(f"portfolio Sharpe difference (paired block bootstrap over days): {title}",
             f"- agent minus B&H vol-target: {diff_line(p['sharpe_vs_vol_target'])}\n"
             f"- agent minus Buy&Hold: {diff_line(p['sharpe_vs_buy_hold'])}")


def section_cash_leg(on: dict, off: dict, title: str) -> None:
    a, b = pd.DataFrame(on["table"]).T, pd.DataFrame(off["table"]).T
    cols = ["Sharpe", "CR%", "MDD%", "Exp%"]
    t = a[cols].join(b[cols], lsuffix=" (cash leg)", rsuffix=" (no cash leg)")
    emit(f"cash leg on vs off: {title}", md(t))


def section_exec_algo(files: dict[str, dict]) -> None:
    rows = []
    for label, p in files.items():
        t = p["table"][AGENT]
        imp = np.mean([s[AGENT]["impact_paid"] for s in p["sleeves"].values()])
        rows.append({"execution algo": label, "Sharpe": t["Sharpe"], "CR%": t["CR%"], "MDD%": t["MDD%"],
                     "mean sleeve impact paid %": 100 * imp})
    emit("execution algorithm, $1B holdout portfolio (sleeve impact at the sleeve's capital)", md(pd.DataFrame(rows), index=False))


def section_impact(main: EvaluationResult, sweeps: dict[str, EvaluationResult]) -> None:
    rows = []
    for strat in (AGENT, "B&H vol-target", "Buy&Hold", "SMA(20/50)", "MACD"):
        for period in ("design", "holdout"):
            base = main.rows[(main.rows["strategy"] == strat) & (main.rows["period"] == period)
                             & (main.rows["universe"] == "core")]
            row = {"strategy": strat, "period": period, "Sharpe (off)": base["Sharpe"].mean()}
            for label, res in sweeps.items():
                r = res.rows[(res.rows["strategy"] == strat) & (res.rows["period"] == period)]
                row[f"Sharpe {label}"] = r["Sharpe"].mean()
                row[f"impact % {label}"] = r["Impact%"].mean()
            rows.append(row)
    emit("impact sweep, core universe, textbook coefficient 1.0 (equity-scaled impact)", md(pd.DataFrame(rows), index=False))


def section_var(v: dict) -> None:
    rows = [{"forecast": f"portfolio returns, {w}-day rolling historical VaR", **{k: r[k] for k in
             ("n", "breaches", "breach_rate", "kupiec_p", "christoffersen_p", "conditional_coverage_p")}}
            for w, r in v["portfolio"].items()]
    emit("VaR coverage: rolling historical VaR of the 15-sleeve portfolio's own returns", md(pd.DataFrame(rows), index=False, floatfmt=".4f"))
    rows = [{"instrument": s, **{k: r[k] for k in ("n", "breaches", "breach_rate", "kupiec_p", "christoffersen_p")}}
            for s, r in v["instruments"].items()]
    df = pd.DataFrame(rows)
    rejects = int((df["kupiec_p"] < 0.05).sum())
    emit(f"VaR coverage: the desk's own per-instrument forecast ({v['desk_window']}-day historical VaR, "
         f"agents/risk.py) vs next-day returns, holdout; Kupiec rejects at 5%: {rejects} of {len(df)}",
         md(df, index=False, floatfmt=".4f"))


def trial_means(d: Path, name: str) -> dict:
    """Design-period agent means of CR% / MDD% / Exp% for one re-measured trial (its own file)."""
    res = load_eval(d / f"trial_{trial_slug(name)}.json")
    if res is None:
        return {}
    rows = res.rows[(res.rows["strategy"] == AGENT) & (res.rows["period"] == "design")]
    return {f"design mean {c}": float(rows[c].mean()) for c in ("CR%", "MDD%", "Exp%")} if len(rows) else {}


def section_selection(trials: dict, design_csv: Path, d: Path) -> None:
    frame = pd.read_csv(design_csv, index_col=0, parse_dates=True)
    r = frame[AGENT].to_numpy(float)[1:]
    rf = frame["rf"].to_numpy(float)[1:] if "rf" in frame else 0.0
    excess = r - (np.where(np.isfinite(rf), rf, 0.0) / 252.0 if np.ndim(rf) else rf / 252.0)
    sharpes = [t["mean_sharpe"] if t["mean_sharpe"] is not None else t["recorded_mean_sharpe_v03_engine"]
               for t in trials["trials"]]
    sharpes = [s for s in sharpes if s is not None]
    rep = selection_report(excess, sharpes, 252.0)
    t = pd.DataFrame([{"trial": t["name"], "version": t["version"],
                       "design mean Sharpe (v0.8 engine)": t["mean_sharpe"],
                       "recorded (v0.3 engine)": t["recorded_mean_sharpe_v03_engine"],
                       "re-measured": t["reproducible"], **trial_means(d, t["name"])} for t in trials["trials"]])
    emit(f"trials registry: {len(trials['trials'])} variants judged on the design period", md(t, index=False))
    emit("selection statistics for the frozen rules (design-period portfolio, all trials)",
         "```json\n" + json.dumps(rep, indent=1, default=str) + "\n```")


def section_phase_sweep(ps: dict) -> None:
    rows = []
    for offset, r in ps["offsets"].items():
        rows.append({"offset": int(offset), "agent Sharpe": r["table"][AGENT]["Sharpe"],
                     "vol-target Sharpe": r["table"]["B&H vol-target"]["Sharpe"],
                     "B&H Sharpe": r["table"]["Buy&Hold"]["Sharpe"],
                     "agent - vol-target": diff_line(r["sharpe_vs_vol_target"]),
                     "agent - B&H": diff_line(r["sharpe_vs_buy_hold"])})
    df = pd.DataFrame(rows)
    spread = df["agent Sharpe"].max() - df["agent Sharpe"].min()
    emit(f"rebalance-phase sweep, holdout portfolio (5-bar cadence, offsets 0-4): agent Sharpe spread {spread:.2f}",
         md(df, index=False))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--in", dest="inp", default=str(ROOT / "results" / "v08"))
    ap.add_argument("--section", default=None)
    args = ap.parse_args(argv)
    d = Path(args.inp)
    want = lambda name: args.section is None or args.section == name  # noqa: E731

    main_res = load_eval(d / "eval_main.json")
    if main_res is None:
        print("eval_main.json missing; nothing to render", file=sys.stderr)
        return 1
    if want("headline"):
        section_headline(main_res)
    if want("asset_class"):
        section_asset_class(main_res)
    rechecks = [("eval_noedgar", "EDGAR on (a) vs off (b)"), ("eval_rules_v03", "FX carry rule on (a) vs off (b)"),
                ("eval_xalpha", "with the cross-sectional analyst (a) vs default (b)"),
                ("eval_alpha", "with the alpha analyst, corrected gate (a) vs default (b)"),
                ("eval_no_trackrecord_cut", "track-record size cut off (a) vs on (b)"),
                ("eval_cash_leg_off", "cash leg off (a) vs on (b)")]
    for name, title in rechecks:
        other = load_eval(d / f"{name}.json")
        if other is None:
            OUT.append(f"_{name}.json missing: {title} not rendered_\n")
        elif want("rechecks"):
            if name in ("eval_xalpha", "eval_alpha", "eval_no_trackrecord_cut", "eval_cash_leg_off"):
                section_recheck(other, main_res, title)
            else:
                section_recheck(main_res, other, title)
    v02 = load_eval(d / "eval_rules_v02.json")
    if v02 is not None and want("rechecks"):
        section_recheck(main_res, v02, "v0.3+ rules (a) vs v0.2 rules (b), core", universes=("core",))
    for name in ("portfolio_design", "portfolio_holdout"):
        p = load_json(d / f"{name}.json")
        if p is not None and want("portfolio"):
            section_portfolio(p, name.replace("portfolio_", ""))
        off = load_json(d / f"{name}_cash_leg_off.json")
        if p is not None and off is not None and want("portfolio"):
            section_cash_leg(p, off, name.replace("portfolio_", ""))
    algos = {label: load_json(d / f"portfolio_holdout_impact_1e9_{key}.json")
             for key, label in (("vwap", "VWAP (default)"), ("twap", "TWAP"), ("ac", "Almgren-Chriss, kappa=5"))}
    if all(v is not None for v in algos.values()) and want("execution"):
        section_exec_algo(algos)
    sweeps = {label: load_eval(d / f"eval_impact_{key}.json") for key, label in (("1e5", "$100k"), ("1e7", "$10M"), ("1e9", "$1B"))}
    if all(v is not None for v in sweeps.values()) and want("impact"):
        section_impact(main_res, sweeps)
    v = load_json(d / "var_coverage.json")
    if v is not None and want("var"):
        section_var(v)
    trials = load_json(d / "trials.json")
    if trials is not None and (d / "portfolio_design.csv").exists() and want("selection"):
        section_selection(trials, d / "portfolio_design.csv", d)
    ps = load_json(d / "phase_sweep_holdout.json")
    if ps is not None and want("phase"):
        section_phase_sweep(ps)
    text = "\n".join(OUT)
    (d / "tables.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
