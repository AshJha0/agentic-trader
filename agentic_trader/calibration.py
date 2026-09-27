"""Calibration harness for the desk's judgement.

A backtest says what the desk did once per date. It cannot say how *stable* that
judgement is: ask the same model the same question five times and the target
weights differ; tell it the book already holds the position and it may anchor on
that; run it again next month and the wording of a new model drifts. Three
measurements, on one frozen state:

* **dispersion** -- ``n`` runs at the same anchor: the standard deviation and
  range of the target weight, and how often the action agrees with the modal one;
* **anchoring** -- the same state with different ``current_weight`` values: the
  slope of the mean target weight on the anchor (0 = ignores the book, 1 = keeps
  whatever it holds);
* **drift** -- ``CalibrationReport.compare`` against a stored earlier report on
  the same state: shift of the mean target weight and of the action distribution.

Offline the rules are deterministic, so dispersion is zero and the anchoring
slope is whatever the no-trade band produces; the harness exists for the LLM
desk, where each run costs money and the answer is not a constant.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from .backtest import _sources
from .graph import TradingGraph
from .instruments import Instrument
from .llm import llm_usage
from .prompts import prompt_bundle_hash
from .provenance import provenance

DEFAULT_ANCHORS: tuple[float | None, ...] = (None, -0.5, 0.0, 0.5)


@dataclass
class CalibrationReport:
    symbol: str
    as_of: str
    samples: pd.DataFrame            # run, anchor, action, target_weight, confidence, approved, llm_share
    prompts: str                     # prompt bundle hash
    meta: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------- measures
    def dispersion(self, anchor: float | None = None) -> dict[str, float]:
        """Across runs at one anchor: std / range of target weight, action agreement, mean confidence."""
        s = self._at(anchor)
        if s.empty:
            return {"runs": 0, "std": float("nan"), "range": float("nan"), "agreement": float("nan"),
                    "mean_target": float("nan"), "mean_confidence": float("nan")}
        modal = s.action.mode().iloc[0]
        return {"runs": int(len(s)), "std": float(s.target_weight.std(ddof=1)) if len(s) > 1 else 0.0,
                "range": float(s.target_weight.max() - s.target_weight.min()),
                "agreement": float((s.action == modal).mean()), "modal_action": str(modal),
                "mean_target": float(s.target_weight.mean()), "mean_confidence": float(s.confidence.mean())}

    def anchoring(self) -> dict[str, float]:
        """Slope of the mean target weight on the numeric anchor (least squares over anchors)."""
        s = self.samples[self.samples.anchor.notna()]
        if s.anchor.nunique() < 2:
            return {"anchors": int(s.anchor.nunique()), "slope": float("nan"), "intercept": float("nan")}
        m = s.groupby("anchor").target_weight.mean()
        x, y = m.index.to_numpy(float), m.to_numpy(float)
        slope, intercept = np.polyfit(x, y, 1)
        return {"anchors": int(len(m)), "slope": float(slope), "intercept": float(intercept),
                "means": {float(k): round(float(v), 4) for k, v in m.items()}}

    def base_anchor(self) -> float | None:
        """The anchor dispersion and drift are read at: no book if it was sampled, else the
        first numeric anchor."""
        if self.samples.anchor.isna().any():
            return None
        return float(self.samples.anchor.dropna().iloc[0])

    def summary(self) -> dict[str, Any]:
        base = self.dispersion(self.base_anchor())
        return {"symbol": self.symbol, "as_of": self.as_of, "prompts": self.prompts, "dispersion": base,
                "anchoring": self.anchoring(), "llm_share": float(self.samples.llm_share.mean()),
                **{k: v for k, v in self.meta.items() if k in ("usage", "models", "effort")}}

    def compare(self, earlier: "CalibrationReport") -> dict[str, Any]:
        """Drift against an earlier report on the same state."""
        if (self.symbol, self.as_of) != (earlier.symbol, earlier.as_of):
            raise ValueError("drift needs two reports on the same symbol and date")
        mine = {None if pd.isna(a) else float(a) for a in self.samples.anchor}
        theirs = {None if pd.isna(a) else float(a) for a in earlier.samples.anchor}
        common = [a for a in [None] + sorted(x for x in mine if x is not None) if a in mine and a in theirs]
        if not common:
            raise ValueError("drift needs at least one anchor sampled in both reports")
        anchor = common[0]
        now, then = self.dispersion(anchor), earlier.dispersion(anchor)
        a_now = self._at(anchor).action.value_counts(normalize=True)
        a_then = earlier._at(anchor).action.value_counts(normalize=True)
        actions = sorted(set(a_now.index) | set(a_then.index))
        tv = 0.5 * sum(abs(float(a_now.get(a, 0.0)) - float(a_then.get(a, 0.0))) for a in actions)
        return {"same_prompts": self.prompts == earlier.prompts, "anchor": anchor,
                "mean_target_shift": now["mean_target"] - then["mean_target"],
                "std_change": now["std"] - then["std"],
                "action_distribution_distance": tv,   # total variation in [0, 1]
                "anchoring_slope_change": self.anchoring()["slope"] - earlier.anchoring()["slope"]}

    # --------------------------------------------------------------- i/o
    def to_dict(self) -> dict[str, Any]:
        return {"symbol": self.symbol, "as_of": self.as_of, "prompts": self.prompts, "meta": self.meta,
                "samples": self.samples.to_dict(orient="records"), "summary": self.summary()}

    def to_json(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_dict(), indent=1, default=str), encoding="utf-8")

    @classmethod
    def from_json(cls, path: str | Path) -> "CalibrationReport":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(d["symbol"], d["as_of"], pd.DataFrame(d["samples"]), d["prompts"], d.get("meta", {}))

    def _at(self, anchor: float | None) -> pd.DataFrame:
        s = self.samples
        return s[s.anchor.isna()] if anchor is None else s[s.anchor == anchor]


def calibrate(graph: TradingGraph, symbol: str | Instrument, as_of: date | str, n: int = 5,
              anchors: tuple[float | None, ...] = DEFAULT_ANCHORS,
              progress: Callable[[str], None] | None = None) -> CalibrationReport:
    """Run the desk ``n`` times at each anchor on one frozen state and collect the decisions.

    ``anchors`` are ``current_weight`` values; ``None`` means no book context. Every run
    is a full ``propagate`` (analysts, debate, trader, risk), so the LLM cost is
    ``n * len(anchors)`` decisions; the shared budget on the graph's model applies.
    """
    if n < 1:
        raise ValueError("n must be >= 1")
    ins = symbol if isinstance(symbol, Instrument) else Instrument.parse(symbol)
    as_of = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of
    rows = []
    for anchor in anchors:
        for k in range(n):
            st, dec = graph.propagate(ins, as_of, current_weight=anchor)
            srcs = _sources(st)   # the same accounting as evaluate()'s agent_sources
            llm_share = srcs.count("llm") / max(1, len(srcs))
            rows.append({"run": k, "anchor": anchor, "action": dec.action.value, "target_weight": float(dec.target_weight),
                         "confidence": float(dec.confidence), "approved": bool(dec.approved), "llm_share": llm_share,
                         "trader_target": float(st.proposal.target_weight) if st.proposal else float("nan")})
            if progress:
                progress(f"anchor {anchor!s:>5} run {k}: {dec.action.value:<4} target {dec.target_weight:+.2f} "
                         f"conf {dec.confidence:.2f}")
    samples = pd.DataFrame(rows)
    cfg = graph.config
    meta: dict[str, Any] = {"n": n, "anchors": list(anchors), "llm_provider": cfg["llm_provider"],
                            "provenance": provenance()}
    if graph.llm is not None:
        meta.update(models={"deep": cfg["deep_think_llm"], "quick": cfg["quick_think_llm"]},
                    effort={"deep": cfg["deep_effort"], "quick": cfg["quick_effort"]},
                    anonymized=bool(cfg.get("llm_anonymize")), usage=llm_usage(graph.llm))
    return CalibrationReport(ins.symbol, as_of.isoformat(), samples, prompt_bundle_hash(cfg), meta)


__all__ = ["CalibrationReport", "calibrate", "DEFAULT_ANCHORS"]
