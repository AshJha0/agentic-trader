"""Recall audit v2: does a model recognise anonymised series? (review 2026-11-09, N1)

Plain idea. The v0.16 audit asked "which of these 15 tickers is it?" with the candidates always
in the same order, AAPL first, and ran the items name by name, AAPL first. A model that always
picks the first option scores about chance overall, yet looks like it recognises AAPL, and a
run stopped early looks "above chance". The audit measured option order, not memory.

v2 removes option order from the measurement and asks a sharper question:

1. Items are interleaved (date-major, then shuffled with a recorded seed), so any prefix of the
   run covers all names about equally.
2. Each item lists the candidates in its own random order (seed recorded per item), so "always
   pick option 1" is a uniform random guess over names.
3. The model gives a ranked top 3. The score is the mean reciprocal rank (MRR: 1, 1/2, 1/3 or 0
   per item).
4. The null is a label permutation: the true names are shuffled across items and MRR recomputed
   (``n_perm`` times). This keeps the model's own answer distribution, so a model that always
   says AAPL gets p near 1 however often AAPL is the truth.
5. A placebo arm asks the same question about synthetic series with the same drift and
   volatility as a real name. No model can recognise them, so placebo MRR is the instrument's
   own floor. Recall is flagged only if real MRR beats both the permutation null and the
   placebo arm.
6. A position-bias diagnostic reports how often the model picks each list position (chi-square
   against uniform). Position bias is reported, never mistaken for recall.
7. A behavioural test compares the information coefficient (IC) of the model's signal with the
   real forward return against the IC with a date-shifted forward return of the same name (a
   future of the same name the window cannot contain), with a date-clustered bootstrap.

Formally, for items i = 1..n with truth y_i and ranked answer (a_i1, a_i2, a_i3),
RR_i = 1/k if a_ik = y_i else 0, MRR = mean RR_i. Under H0 (answers independent of truth) the
permutation distribution of MRR(pi) = mean 1[a_ik = y_pi(i)]/k is exact given the answers.
p = (1 + #{MRR(pi) >= MRR}) / (1 + n_perm).

Worked example. 30 items, the model always answers its first listed candidate. With per-item
shuffling, its top-1 answers are uniform over 15 names, MRR is about 1/15 + small, and the
permutation p is about 0.5: not flagged. The v0.16 design would have reported 14/30 hits on the
AAPL-first prefix and flagged it.

Evidence class: design plus unit tests with fake models (tests/test_v017_recall_audit.py). No
model has been run through v2; the v0.16 result (recall.rows.jsonl) is void as a recall measure.
"""
from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import numpy as np

TOP_K = 3


@dataclass(frozen=True)
class AuditItem:
    """One question: which name (``truth``) and date, the arm, and the candidate order shown."""
    idx: int
    truth: str
    as_of: str
    arm: str                      # "real" or "placebo"
    candidates: tuple[str, ...]
    candidate_seed: int
    placebo_seed: int | None = None

    @property
    def id(self) -> str:
        return f"{self.arm}:{self.truth}@{self.as_of}"


def build_items(names: Sequence[str], dates: Sequence[str], *, seed: int, arm: str = "real",
                limit: int = 0) -> list[AuditItem]:
    """Interleaved items with a per-item candidate shuffle.

    Order: date-major (every name at date 1, then date 2, ...), then shuffled with
    ``Random(seed)``, so no prefix is dominated by one name. Candidate order per item uses
    ``Random(seed * 1_000_003 + idx)``, recorded as ``candidate_seed``. Placebo items get a
    ``placebo_seed`` for the synthetic series. ``limit`` truncates after the shuffle, so a
    truncated run stays balanced in expectation (unlike the v0.16 name-major cap)."""
    grid = [(n, d) for d in dates for n in names]
    rng = random.Random(seed)
    rng.shuffle(grid)
    if limit:
        grid = grid[:limit]
    out = []
    for i, (n, d) in enumerate(grid):
        cs = seed * 1_000_003 + i + (500_000 if arm == "placebo" else 0)
        cand = list(names)
        random.Random(cs).shuffle(cand)
        out.append(AuditItem(i, n, str(d), arm, tuple(cand), cs,
                             placebo_seed=(cs + 7) if arm == "placebo" else None))
    return out


def question(item: AuditItem, window: tuple[str, str]) -> str:
    """The audit question appended to the anonymised prompt (candidates in the item's order)."""
    opts = "\n".join(f"  {k + 1}. {c}" for k, c in enumerate(item.candidates))
    return ("\n\nAUDIT QUESTION (not a trading task). The data above is anonymised. It comes from "
            f"exactly one of these instruments (the order of the list is random):\n{opts}\n"
            f"The decision day (D0) lies between {window[0]} and {window[1]}. Rank your three best "
            "guesses for the instrument, most likely first, and give your best guess for the "
            "calendar month of D0, even if unsure. Reply with exactly four lines:\n"
            "RANK1: <ticker>\nRANK2: <ticker>\nRANK3: <ticker>\nMONTH: <YYYY-MM>")


_RANK = re.compile(r"RANK\s*([123])\s*[:=]\s*\**\s*([A-Za-z/=.]+)", re.I)
_MONTH = re.compile(r"MONTH\s*[:=]\s*\**\s*(\d{4})-(\d{1,2})", re.I)


def _norm(t: str) -> str:
    return t.upper().replace("/", "").replace("=X", "").strip(".")


def parse_ranked(text: str | None, candidates: Iterable[str]) -> dict[str, Any] | None:
    """``{"ranked": [t1, t2?, t3?], "month": "YYYY-MM" | None}``; ``None`` when RANK1 is missing
    or not a candidate. Unknown or repeated lower ranks are dropped."""
    if not text:
        return None
    cands = set(candidates)
    got: dict[int, str] = {}
    for m in _RANK.finditer(text):
        k, t = int(m.group(1)), _norm(m.group(2))
        if k not in got and t in cands and t not in got.values():
            got[k] = t
    if 1 not in got:
        return None
    ranked = [got[k] for k in (1, 2, 3) if k in got]
    mm = _MONTH.search(text)
    month = None
    if mm and 1 <= int(mm.group(2)) <= 12:
        month = f"{int(mm.group(1)):04d}-{int(mm.group(2)):02d}"
    return {"ranked": ranked, "month": month}


def reciprocal_rank(ranked: Sequence[str] | None, truth: str) -> float:
    if not ranked:
        return 0.0
    for k, t in enumerate(ranked[:TOP_K]):
        if t == truth:
            return 1.0 / (k + 1)
    return 0.0


def chance_mrr(n_candidates: int, k: int = TOP_K) -> float:
    """MRR of a uniform random ranking: (1/N) * sum_{j<=k} 1/j."""
    return sum(1.0 / j for j in range(1, k + 1)) / n_candidates


def mrr(answers: Sequence[Sequence[str] | None], truths: Sequence[str]) -> float:
    return float(np.mean([reciprocal_rank(a, t) for a, t in zip(answers, truths)])) if truths else float("nan")


def permutation_test(answers: Sequence[Sequence[str] | None], truths: Sequence[str], *,
                     n_perm: int = 2000, seed: int = 0) -> dict[str, Any]:
    """MRR against the label-permutation null (keeps the model's answer distribution)."""
    obs = mrr(answers, truths)
    rng = np.random.default_rng(seed)
    t = np.asarray(truths, dtype=object)
    null = np.empty(n_perm)
    for b in range(n_perm):
        null[b] = mrr(answers, list(rng.permutation(t)))
    p = float((1 + np.sum(null >= obs - 1e-12)) / (1 + n_perm))
    return {"mrr": obs, "null_mean": float(null.mean()), "null_q95": float(np.quantile(null, 0.95)),
            "p_perm": p, "n": len(truths), "n_perm": n_perm}


def two_sample_mrr(real_rr: Sequence[float], placebo_rr: Sequence[float], *, n_perm: int = 2000,
                   seed: int = 1) -> dict[str, Any]:
    """One-sided permutation test that real MRR exceeds placebo MRR (pooled relabelling)."""
    a, b = np.asarray(real_rr, float), np.asarray(placebo_rr, float)
    if len(a) == 0 or len(b) == 0:
        return {"diff": None, "p_perm": None}
    obs = float(a.mean() - b.mean())
    pool = np.concatenate([a, b])
    rng = np.random.default_rng(seed)
    cnt = 0
    for _ in range(n_perm):
        rng.shuffle(pool)
        cnt += pool[:len(a)].mean() - pool[len(a):].mean() >= obs - 1e-12
    return {"real_mrr": float(a.mean()), "placebo_mrr": float(b.mean()), "diff": obs,
            "p_perm": float((1 + cnt) / (1 + n_perm))}


def position_bias(items: Sequence[AuditItem], answers: Sequence[Sequence[str] | None]) -> dict[str, Any]:
    """How often RANK1 sits at each list position; chi-square against uniform."""
    n_pos = max((len(i.candidates) for i in items), default=0)
    counts = [0] * n_pos
    for it, a in zip(items, answers):
        if a:
            counts[it.candidates.index(a[0])] += 1
    n = sum(counts)
    if n == 0 or n_pos < 2:
        return {"counts": counts, "n": n, "first_share": None, "chi2": None, "p": None}
    e = n / n_pos
    chi2 = float(sum((c - e) ** 2 / e for c in counts))
    return {"counts": counts, "n": n, "first_share": counts[0] / n, "chi2": chi2,
            "p": chi2_sf(chi2, n_pos - 1)}


def chi2_sf(x: float, df: int) -> float:
    """Upper tail of the chi-square distribution (regularised upper incomplete gamma, series and
    continued fraction as in Numerical Recipes 6.2); no SciPy dependency."""
    if x <= 0:
        return 1.0
    a, z = df / 2.0, x / 2.0
    gln = math.lgamma(a)
    if z < a + 1:
        ap, s, d = a, 1.0 / a, 1.0 / a
        for _ in range(500):
            ap += 1
            d *= z / ap
            s += d
            if abs(d) < abs(s) * 1e-14:
                break
        return max(0.0, 1.0 - s * math.exp(-z + a * math.log(z) - gln))
    b, c, d = z + 1 - a, 1e300, 1.0 / (z + 1 - a)
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1.0 / d
        h *= d * c
        if abs(d * c - 1) < 1e-14:
            break
    return min(1.0, math.exp(-z + a * math.log(z) - gln) * h)


def answer_concentration(answers: Sequence[Sequence[str] | None]) -> dict[str, Any]:
    """Share of the most frequent RANK1 answer (1.0 = constant responder)."""
    top = [a[0] for a in answers if a]
    if not top:
        return {"modal": None, "modal_share": None}
    vals, cnts = np.unique(np.asarray(top, dtype=object), return_counts=True)
    j = int(np.argmax(cnts))
    return {"modal": str(vals[j]), "modal_share": float(cnts[j] / len(top))}


# ---- behavioural leak test ------------------------------------------------------------------

def _rank(x: np.ndarray) -> np.ndarray:
    order = np.argsort(x, kind="mergesort")
    r = np.empty(len(x))
    r[order] = np.arange(len(x))
    # average ties
    vals = x[order]
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and vals[j + 1] == vals[i]:
            j += 1
        if j > i:
            r[order[i:j + 1]] = (i + j) / 2.0
        i = j + 1
    return r


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    a, b = np.asarray(x, float), np.asarray(y, float)
    if len(a) < 3:
        return float("nan")
    ra, rb = _rank(a), _rank(b)
    if ra.std() == 0 or rb.std() == 0:
        return 0.0
    return float(np.corrcoef(ra, rb)[0, 1])


def leak_test(rows: Sequence[dict[str, Any]], *, n_boot: int = 2000, seed: int = 2) -> dict[str, Any]:
    """IC(signal, real forward return) minus IC(signal, date-shifted forward return).

    ``rows``: dicts with ``signal``, ``fwd_real``, ``fwd_shift`` and ``as_of`` (the cluster).
    The bootstrap resamples dates (clusters) with replacement. A positive difference with the
    95 % interval above zero says the signal is specific to the true future of that window.
    Whether that is memory or skill is settled by the in-training vs post-cutoff contrast (N9),
    not by this test alone."""
    rs = [r for r in rows if all(r.get(k) is not None and math.isfinite(float(r[k]))
                                 for k in ("signal", "fwd_real", "fwd_shift"))]
    if len(rs) < 5:
        return {"n": len(rs), "ic_real": None, "ic_shift": None, "diff": None, "ci95": None, "p": None}
    s = [r["signal"] for r in rs]
    ic_r, ic_s = spearman(s, [r["fwd_real"] for r in rs]), spearman(s, [r["fwd_shift"] for r in rs])
    by_d: dict[str, list[dict]] = {}
    for r in rs:
        by_d.setdefault(str(r["as_of"]), []).append(r)
    keys = list(by_d)
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(n_boot):
        pick = [x for k in rng.choice(len(keys), len(keys)) for x in by_d[keys[k]]]
        ss = [x["signal"] for x in pick]
        diffs.append(spearman(ss, [x["fwd_real"] for x in pick]) - spearman(ss, [x["fwd_shift"] for x in pick]))
    d = np.asarray(diffs)
    d = d[np.isfinite(d)]
    lo, hi = (float(np.quantile(d, 0.025)), float(np.quantile(d, 0.975))) if len(d) else (None, None)
    p = float(min(1.0, 2 * min(np.mean(d <= 0), np.mean(d >= 0)))) if len(d) else None
    return {"n": len(rs), "dates": len(keys), "ic_real": ic_r, "ic_shift": ic_s, "diff": ic_r - ic_s,
            "ci95": [lo, hi], "p": p}


# ---- placebo series ---------------------------------------------------------------------------

def placebo_ohlc(history: Any, seed: int) -> Any:
    """A synthetic OHLCV frame on the same index as ``history`` whose log returns are iid normal
    with the real series' mean and standard deviation (drift and volatility matched), the same
    starting level, and High/Low set from the real bars' relative ranges. No model can have seen
    it, so recall of the matched name on it is chance by construction."""
    import pandas as pd
    close = history["Close"].astype(float).to_numpy()
    r = np.diff(np.log(close))
    mu, sd = (float(r.mean()), float(r.std(ddof=1))) if len(r) > 1 else (0.0, 0.01)
    rng = np.random.default_rng(seed)
    path = close[0] * np.exp(np.concatenate([[0.0], np.cumsum(rng.normal(mu, sd, len(close) - 1))]))
    hi_rel = (history["High"].astype(float).to_numpy() / close).clip(min=1.0)
    lo_rel = (history["Low"].astype(float).to_numpy() / close).clip(max=1.0)
    out = pd.DataFrame(index=history.index)
    out["Open"] = np.concatenate([[path[0]], path[:-1]])
    out["High"] = np.maximum(path * hi_rel, np.maximum(out["Open"].to_numpy(), path))
    out["Low"] = np.minimum(path * lo_rel, np.minimum(out["Open"].to_numpy(), path))
    out["Close"] = path
    if "Volume" in history:
        out["Volume"] = history["Volume"].to_numpy()
    for c in history.columns:
        if c not in out:
            out[c] = history[c].to_numpy()
    return out[list(history.columns)]


# ---- summary and verdict ----------------------------------------------------------------------

@dataclass
class AuditResult:
    real: dict[str, Any]
    placebo: dict[str, Any] | None
    real_vs_placebo: dict[str, Any] | None
    position_bias: dict[str, Any]
    concentration: dict[str, Any]
    month: dict[str, Any]
    leak: dict[str, Any] | None
    flagged: bool
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"real": self.real, "placebo": self.placebo, "real_vs_placebo": self.real_vs_placebo,
                "position_bias": self.position_bias, "concentration": self.concentration,
                "month": self.month, "leak": self.leak, "recall_flagged": self.flagged,
                "reasons": self.reasons}


def month_test(answers_month: Sequence[str | None], truths_month: Sequence[str], *, n_perm: int = 2000,
               seed: int = 3) -> dict[str, Any]:
    """Exact-month hit rate against the permutation null of true months across items."""
    hits = lambda tr: float(np.mean([a == t for a, t in zip(answers_month, tr)])) if tr else float("nan")  # noqa: E731
    obs = hits(list(truths_month))
    rng = np.random.default_rng(seed)
    t = np.asarray(truths_month, dtype=object)
    null = np.array([hits(list(rng.permutation(t))) for _ in range(n_perm)])
    return {"hit_rate": obs, "null_mean": float(null.mean()) if len(null) else None,
            "p_perm": float((1 + np.sum(null >= obs - 1e-12)) / (1 + n_perm))}


def summarise(real_items: Sequence[AuditItem], real_answers: Sequence[dict[str, Any] | None],
              placebo_items: Sequence[AuditItem] = (), placebo_answers: Sequence[dict[str, Any] | None] = (),
              leak_rows: Sequence[dict[str, Any]] = (), *, alpha: float = 0.05,
              n_perm: int = 2000) -> AuditResult:
    """The audit verdict. Recall is flagged only when (a) real MRR beats the label-permutation
    null at ``alpha`` and (b) real MRR beats the placebo arm at ``alpha`` (when a placebo arm
    was run; without one the verdict says 'incomplete'). Position bias and answer
    concentration are reported but never flag recall by themselves."""
    ra = [(a or {}).get("ranked") for a in real_answers]
    truths = [i.truth for i in real_items]
    real = {**permutation_test(ra, truths, n_perm=n_perm),
            "chance_mrr": chance_mrr(len(real_items[0].candidates)) if real_items else None,
            "unparsed": sum(a is None for a in real_answers)}
    plc = rvp = None
    if placebo_items:
        pa = [(a or {}).get("ranked") for a in placebo_answers]
        plc = {**permutation_test(pa, [i.truth for i in placebo_items], n_perm=n_perm),
               "unparsed": sum(a is None for a in placebo_answers)}
        rvp = two_sample_mrr([reciprocal_rank(a, t) for a, t in zip(ra, truths)],
                             [reciprocal_rank(a, i.truth) for a, i in zip(pa, placebo_items)], n_perm=n_perm)
    months = month_test([(a or {}).get("month") for a in real_answers], [i.as_of[:7] for i in real_items],
                        n_perm=n_perm)
    reasons = []
    beats_null = real["p_perm"] < alpha
    reasons.append(f"real MRR {real['mrr']:.3f} vs permutation null mean {real['null_mean']:.3f} "
                   f"(p={real['p_perm']:.3f})")
    beats_placebo = None
    if rvp is not None and rvp.get("p_perm") is not None:
        beats_placebo = rvp["p_perm"] < alpha
        reasons.append(f"real minus placebo MRR {rvp['diff']:+.3f} (p={rvp['p_perm']:.3f})")
    else:
        reasons.append("no placebo arm: verdict incomplete")
    flagged = bool(beats_null and (beats_placebo is True))
    leak = leak_test(leak_rows) if leak_rows else None
    return AuditResult(real, plc, rvp, position_bias(real_items, ra), answer_concentration(ra), months,
                       leak, flagged, reasons)


__all__ = ["AuditItem", "AuditResult", "build_items", "question", "parse_ranked", "reciprocal_rank",
           "chance_mrr", "mrr", "permutation_test", "two_sample_mrr", "position_bias",
           "answer_concentration", "spearman", "leak_test", "placebo_ohlc", "month_test", "summarise"]
