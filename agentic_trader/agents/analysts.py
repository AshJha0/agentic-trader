"""Analyst team: each analyst turns raw data into a structured report."""
from __future__ import annotations

import math
from datetime import date
from typing import Any

import numpy as np

from .. import quant
from ..data.base import MarketDataProvider, NewsItem
from ..sentiment import score_fx_headline, score_text
from ..state import AnalystReport, TradingState
from .base import Agent, clip, fmt_facts, untrusted_block


def _last(x) -> float | None:
    v = float(np.asarray(x)[-1]) if len(x) else float("nan")
    return None if math.isnan(v) else v


def _direction_note(state: TradingState) -> str:
    ins = state.instrument
    if ins.is_fx:
        return (f"{ins.base} versus {ins.quote} (positive = {ins.display} rate rises, i.e. "
                f"buy {ins.base} / sell {ins.quote})")
    return f"{ins.symbol} shares (positive = price rises)"


class Analyst(Agent):
    deep = False
    instructions = ""
    # Fact keys holding third-party free text. They are removed from the JSON facts
    # and shown to the model inside an <untrusted_data> block instead.
    untrusted_keys: tuple[str, ...] = ()

    def gather(self, state: TradingState, provider: MarketDataProvider) -> dict[str, Any]:
        raise NotImplementedError

    def rules(self, facts: dict[str, Any], state: TradingState) -> AnalystReport:
        raise NotImplementedError

    def prompt(self, facts: dict[str, Any], state: TradingState) -> str:
        plain = {k: v for k, v in facts.items() if k not in self.untrusted_keys}
        blocks = [untrusted_block(k, [str(x) for x in facts[k]])
                  for k in self.untrusted_keys if facts.get(k)]
        return (
            f"Instrument: {state.instrument.display} ({state.instrument.asset_class}). "
            f"As-of date: {state.as_of.isoformat()}. Last close: {state.fmt_px(state.last_price)}.\n"
            f"Data from your tools (a null value is unavailable: do not estimate it):\n"
            f"{fmt_facts(state.prompt_facts(plain))}\n"
            + ("\n".join(blocks) + "\n" if blocks else "")
            + f"\n{self.instructions}\nSignal direction refers to {_direction_note(state)}.\n"
            'JSON keys: "signal" (number in [-1, 1]), "confidence" (number in [0, 1]), '
            '"summary" (2-3 sentences), "key_points" (list of at most 5 short strings).'
        )

    def run(self, state: TradingState, provider: MarketDataProvider) -> AnalystReport:
        facts = self.gather(state, provider)
        report = self.rules(facts, state)
        # Nothing to analyse -> no model call (saves cost, and the model cannot
        # invent a view from an empty input).
        if not report.abstained:
            data = self.ask_json(self.prompt(facts, state), ("signal", "confidence", "summary"),
                                 state=state, numeric=("signal", "confidence"))
            if data:
                kp = data.get("key_points") or []
                report = AnalystReport(
                    analyst=self.name,
                    signal=clip(data["signal"], -1, 1),
                    confidence=clip(data["confidence"], 0, 1, 0.5),
                    summary=str(data["summary"]),
                    key_points=[str(k) for k in kp][:5] if isinstance(kp, list) else [],
                    facts=facts,
                    source="llm",
                    rule_signal=report.signal,
                )
        # Text derived from headlines or posts stays fenced wherever it is shown next.
        report.untrusted = bool(self.untrusted_keys)
        state.reports[self.name] = report
        return report

    def abstain(self, reason: str, facts: dict[str, Any]) -> AnalystReport:
        return AnalystReport(self.name, 0.0, 0.1, reason, [], facts, abstained=True)


# --------------------------------------------------------------------------
class TechnicalAnalyst(Analyst):
    name = "technical"
    role = ("Technical Analyst. You read price action and indicators (trend, momentum, "
            "mean-reversion, volatility) to forecast the direction over the next 1-4 weeks.")
    instructions = ("Weigh trend (moving averages), momentum (MACD, returns, 12-1 month "
                    "time-series momentum), overbought/oversold conditions (RSI, Bollinger "
                    "%B, KDJ) and volatility (ATR).")

    def gather(self, state, provider):
        h = state.history
        c, hi, lo = h["Close"].to_numpy(), h["High"].to_numpy(), h["Low"].to_numpy()
        ppy = state.instrument.periods_per_year
        macd_line, _, hist = quant.macd(c)
        _, _, _, pb = quant.bollinger(c, 20, 2.0)
        k, d, j = quant.kdj(hi, lo, c, 9)
        a = quant.atr(hi, lo, c, 14)

        def ret(n, skip=0):
            if len(c) <= n:
                return None
            return float(c[-1 - skip] / c[-1 - n] - 1.0)

        facts = {
            "close": float(c[-1]),
            "sma20": _last(quant.sma(c, 20)), "sma50": _last(quant.sma(c, 50)),
            "sma200": _last(quant.sma(c, 200)),
            "rsi14": _last(quant.rsi(c, 14)),
            "macd_line": _last(macd_line), "macd_hist": _last(hist),
            "macd_hist_prev": float(hist[-2]) if len(hist) > 1 and not math.isnan(hist[-2]) else None,
            "bollinger_pct_b": _last(pb),
            "kdj_k": _last(k), "kdj_d": _last(d), "kdj_j": _last(j),
            "atr14": _last(a),
            "realized_vol_20d_annual": _last(quant.realized_vol(c, 20, ppy)),
            "zscore20": _last(quant.zscore(c, 20)),
            "return_5d": ret(5), "return_20d": ret(20), "return_60d": ret(60),
            # 12-1 month momentum: the year's return skipping the last month, the
            # standard time-series momentum definition (Moskowitz, Ooi, Pedersen 2012).
            "return_12_1m": ret(252, skip=21),
            "realized_vol_1y_annual": _last(quant.realized_vol(c, 252, ppy)) if len(c) > 252 else None,
            "bars": len(c),
        }
        if facts["atr14"]:
            facts["atr_pct"] = facts["atr14"] / facts["close"]
        return facts

    def rules(self, f, state):
        opts = self.config.get("rules", {})
        s, pts = 0.0, []
        c = f["close"]
        uptrend = downtrend = False
        if f["sma50"]:
            up = c > f["sma50"]
            s += 0.30 if up else -0.30
            # Scale-free wording: no raw price level in text that reaches a prompt.
            pts.append(f"Price {abs(c / f['sma50'] - 1):.1%} {'above' if up else 'below'} the 50-day SMA")
        if f["sma50"] and f["sma200"]:
            golden = f["sma50"] > f["sma200"]
            uptrend, downtrend = golden, not golden
            s += 0.20 if golden else -0.20
            pts.append(f"50-day SMA {'above' if golden else 'below'} 200-day SMA "
                       f"({'uptrend' if golden else 'downtrend'} regime)")
        if f["macd_hist"] is not None:
            pos = f["macd_hist"] > 0
            s += 0.15 if pos else -0.15
            rising = f["macd_hist_prev"] is not None and f["macd_hist"] > f["macd_hist_prev"]
            pts.append(f"MACD histogram {'positive' if pos else 'negative'} and "
                       f"{'rising' if rising else 'falling'}")
        if f["return_20d"] is not None and f["realized_vol_20d_annual"]:
            scale = f["realized_vol_20d_annual"] * math.sqrt(20 / state.instrument.periods_per_year)
            mom = math.tanh(f["return_20d"] / scale) if scale > 0 else 0.0
            s += 0.15 * mom
            pts.append(f"20-day return {f['return_20d']:+.2%} ({mom:+.2f} vol-adjusted)")
        if opts.get("tsmom") and f["return_12_1m"] is not None and f["realized_vol_1y_annual"]:
            ts = math.tanh(f["return_12_1m"] / f["realized_vol_1y_annual"])
            s += 0.25 * ts
            pts.append(f"12-1 month momentum {f['return_12_1m']:+.1%} ({ts:+.2f} vol-adjusted)")

        filt = opts.get("trend_filtered_reversal", False)
        if f["rsi14"] is not None:
            r = f["rsi14"]
            if r > 70 and filt and uptrend:
                pts.append(f"RSI {r:.0f}: overbought, but in an uptrend - fade suppressed")
            elif r > 70:
                s -= 0.15
                pts.append(f"RSI {r:.0f}: overbought")
            elif r < 30 and filt and downtrend:
                pts.append(f"RSI {r:.0f}: oversold, but in a downtrend - fade suppressed")
            elif r < 30:
                s += 0.15
                pts.append(f"RSI {r:.0f}: oversold")
            else:
                pts.append(f"RSI {r:.0f}: neutral")
        if f["bollinger_pct_b"] is not None:
            b = f["bollinger_pct_b"]
            if b > 1 and not (filt and uptrend):
                s -= 0.05
                pts.append("Close above upper Bollinger band (stretched)")
            elif b < 0 and not (filt and downtrend):
                s += 0.05
                pts.append("Close below lower Bollinger band (stretched)")
        if f.get("atr_pct"):
            pts.append(f"ATR(14) {f['atr_pct']:.2%} of price")
        sig = clip(s, -1, 1)
        conf = clip(0.35 + 0.5 * abs(sig), 0, 0.9) if f["bars"] >= 200 else 0.3
        bias = "bullish" if sig > 0.1 else "bearish" if sig < -0.1 else "neutral"
        return AnalystReport(self.name, sig, conf,
                             f"Technical picture is {bias} (score {sig:+.2f}).", pts, f)


# --------------------------------------------------------------------------
# A point-in-time fundamentals report older than STALE_REPORT_DAYS at the decision date (a
# skipped periodic filing) is not scored at all; a series whose four-quarter window ends
# more than STALE_WINDOW_DAYS behind the report period (a recast or renamed tag not yet
# covering the newest quarters, flagged by the provider under ``<series>_period_end``) has
# its term skipped. A window one quarter behind is scored as before.
STALE_REPORT_DAYS = 120
STALE_WINDOW_DAYS = 100
_WINDOW_KEYS = {"revenue": "revenue_period_end", "net_income": "net_income_period_end",
                "eps": "eps_period_end", "ocf": "ocf_period_end"}
_WINDOW_LABELS = {"revenue": "revenue figures", "net_income": "net income", "eps": "EPS", "ocf": "cash flow"}


def _window_lag(f: dict[str, Any], end: str) -> int | None:
    """Days the window ending ``end`` lags the report period, or None when either date is unreadable."""
    try:
        return (date.fromisoformat(str(f.get("report_period_end"))) - date.fromisoformat(str(end))).days
    except ValueError:
        return None


class FundamentalsAnalyst(Analyst):
    name = "fundamentals"
    role = ("Fundamentals Analyst. You assess a company's intrinsic value and financial "
            "health from its latest reported financials and insider activity.")
    instructions = ("Assess valuation (against the sector only when a sector P/E is given), growth, "
                    "profitability, balance-sheet leverage, cash generation, and earnings surprise "
                    "and insider activity where they are reported.")

    def gather(self, state, provider):
        return provider.fundamentals(state.instrument, state.as_of)

    def rules(self, f, state):
        usable = {k: v for k, v in f.items() if isinstance(v, (int, float)) and v is not None and k != "lag_days"}
        if not usable:
            return self.abstain("No point-in-time fundamental data available.", f)
        # A point-in-time provider says how old its report is and which of its windows end
        # behind the report period; neither is scored as if current.
        lag = f.get("lag_days")
        if isinstance(lag, (int, float)) and lag > STALE_REPORT_DAYS:
            return self.abstain(f"Latest report ({f.get('report_period_end', 'n/a')}) is {int(lag)} days old "
                                f"at {state.as_of.isoformat()}: no current fundamentals to score.", f)
        stale = {name: (end, days) for name, key in _WINDOW_KEYS.items()
                 if (end := f.get(key)) and (days := _window_lag(f, end)) is not None and days > STALE_WINDOW_DAYS}

        def skipped(name: str, term: str) -> bool:
            if name not in stale:
                return False
            end, days = stale[name]
            pts.append(f"{term} not scored: its window ends {end}, {days} days behind the report period")
            return True

        s, pts, scored = 0.0, [], 0
        pe, spe = f.get("pe_ratio"), f.get("sector_pe")
        # Relative valuation needs a benchmark from the data; the real providers have no
        # sector P/E, and a placeholder would be scored and reported as a fact.
        if pe is not None and skipped("eps", "P/E"):
            pass
        elif pe and pe > 0 and spe and spe > 0:
            v = clip((spe - pe) / spe, -0.3, 0.3)
            s += v
            scored += 1
            pts.append(f"P/E {pe:.1f} vs sector {spe:.1f} ({'cheap' if v > 0 else 'rich'})")
        elif pe and pe > 0:
            scored += 1
            pts.append(f"P/E {pe:.1f}; no sector benchmark available")
        elif pe is not None and pe <= 0:
            s -= 0.1
            scored += 1
            pts.append("Negative earnings (P/E not meaningful)")
        if (g := f.get("revenue_growth_yoy")) is not None and not skipped("revenue", "Revenue growth"):
            s += 0.3 * math.tanh(g / 0.15)
            scored += 1
            pts.append(f"Revenue growth {g:+.1%} YoY")
        if (m := f.get("net_margin")) is not None and not skipped("net_income", "Net margin"):
            s += 0.15 * math.tanh(m / 0.15)
            scored += 1
            pts.append(f"Net margin {m:.1%}")
        if (de := f.get("debt_to_equity")) is not None:
            if de > 2.0:
                s -= 0.15
            scored += 1
            pts.append(f"Debt/equity {de:.2f}{' (high)' if de > 2 else ''}")
        if (fy := f.get("fcf_yield")) is not None and not skipped("ocf", "FCF yield"):
            s += 0.15 * math.tanh(fy / 0.05)
            scored += 1
            pts.append(f"FCF yield {fy:.1%}")
        if (es := f.get("eps_surprise")) is not None:
            s += 0.15 * math.tanh(es / 0.05)
            scored += 1
            pts.append(f"EPS surprise {es:+.1%}")
        if (ins := f.get("insider_net_buying")) is not None and ins != 0:
            s += 0.05 * np.sign(ins)
            scored += 1
            pts.append(f"Insiders net {'buyers' if ins > 0 else 'sellers'} ({ins:+d} filings)")
        if not scored:
            return self.abstain("Every fundamental term is on a window behind the report period: "
                                + "; ".join(pts), f)
        sig = clip(s, -1, 1)
        window = f"({f.get('report_period_end', 'n/a')}"
        for name, key in _WINDOW_KEYS.items():
            if f.get(key):
                window += f"; {_WINDOW_LABELS[name]} through {f[key]}"
        return AnalystReport(self.name, sig, clip(0.3 + 0.4 * abs(sig), 0, 0.8),
                             f"Fundamentals score {sig:+.2f} from the latest report {window}).", pts, f)


# --------------------------------------------------------------------------
class MacroAnalyst(Analyst):
    """FX counterpart of the Fundamentals Analyst: rates, inflation and valuation."""
    name = "macro"
    role = ("Macro / Rates Analyst for FX. You assess a currency pair from interest-rate "
            "differentials (carry), inflation differentials (purchasing-power parity) and "
            "long-run valuation.")
    instructions = ("Consider carry (policy-rate differential), relative inflation, and how "
                    "far the pair trades from its long-run (200-day) average.")

    def gather(self, state, provider):
        f = dict(provider.macro(state.instrument, state.as_of))
        c = state.history["Close"].to_numpy()
        sma200 = _last(quant.sma(c, 200))
        if sma200:
            f["deviation_from_200d"] = float(c[-1] / sma200 - 1.0)
        return f

    def rules(self, f, state):
        ins = state.instrument
        if "rate_diff" not in f:
            return self.abstain("No point-in-time policy-rate data for this pair.", f)
        s, pts = 0.0, []
        rd = f["rate_diff"]
        s += 0.5 * math.tanh(rd / 1.5)
        pts.append(f"Policy rates {ins.base} {f['base_rate']:.2f}% vs {ins.quote} "
                   f"{f['quote_rate']:.2f}% -> carry {rd:+.2f}% p.a. "
                   f"{'favours long' if rd > 0 else 'favours short'} {ins.display}")
        bi, qi = f.get("base_inflation"), f.get("quote_inflation")
        if bi is not None and qi is not None:
            idiff = bi - qi
            s -= 0.2 * math.tanh(idiff / 2.0)
            pts.append(f"Inflation {ins.base} {bi:.1f}% vs {ins.quote} {qi:.1f}% "
                       f"(PPP drag on the higher-inflation currency)")
        if (dev := f.get("deviation_from_200d")) is not None:
            s -= 0.2 * math.tanh(dev / 0.08)
            pts.append(f"{ins.display} {dev:+.1%} from its 200-day average")
        sig = clip(s, -1, 1)
        return AnalystReport(self.name, sig, clip(0.35 + 0.4 * abs(sig), 0, 0.8),
                             f"Macro backdrop score {sig:+.2f} (carry-led).", pts, f)


# --------------------------------------------------------------------------
def _score(item: NewsItem, state: TradingState) -> float:
    if item.sentiment is not None:
        return clip(item.sentiment, -1, 1)
    ins = state.instrument
    if ins.is_fx:
        return score_fx_headline(item.headline, ins.base, ins.quote)
    return score_text(item.headline)


def _weighted_tone(items: list[NewsItem], state: TradingState, half_life_days: float = 2.0):
    if not items:
        return 0.0, []
    scored = []
    num = den = 0.0
    for it in items:
        age = max((state.as_of - it.published).days, 0)
        w = 0.5 ** (age / half_life_days)
        sc = _score(it, state)
        num += w * sc
        den += w
        scored.append((it, sc))
    return (num / den if den else 0.0), scored


class NewsAnalyst(Analyst):
    name = "news"
    role = ("News Analyst. You monitor company news and macroeconomic headlines and judge "
            "how they are likely to move the instrument over the coming days.")
    instructions = ("Judge the net impact of the headlines. Recent and material news "
                    "(earnings, guidance, central-bank signals, regulation) matters most.")
    untrusted_keys = ("headlines",)

    def gather(self, state, provider):
        days = self.config["news_lookback_days"]
        items = provider.news(state.instrument, state.as_of, days)
        items = [i for i in items if i.published <= state.as_of]  # hard point-in-time guard
        items.sort(key=lambda i: i.published, reverse=True)
        return {"lookback_days": days, "count": len(items),
                "headlines": [f"{i.published.isoformat()} | {i.headline}" for i in items[:25]],
                "_items": items}

    def rules(self, f, state):
        items = f.pop("_items")
        if not items:
            return self.abstain("No relevant news in the lookback window.", f)
        tone, scored = _weighted_tone(items, state)
        sig = clip(math.tanh(2.0 * tone), -1, 1)
        top = sorted(scored, key=lambda x: abs(x[1]), reverse=True)[:4]
        pts = [f"{it.published.isoformat()}: {it.headline} ({sc:+.2f})" for it, sc in top]
        if self.config.get("rules", {}).get("news_tone_mass", True):
            mass = float(sum(abs(sc) for _, sc in scored))
            if mass < 0.05:
                f["recency_weighted_tone"] = tone
                return self.abstain(f"{len(items)} headlines in {f['lookback_days']}d carry no tone.", f)
            conf = clip(0.2 + 0.1 * mass, 0, 0.7)
        else:
            conf = clip(0.2 + 0.05 * len(items), 0, 0.7)
        f["recency_weighted_tone"] = tone
        return AnalystReport(self.name, sig, conf,
                             f"{len(items)} headlines in {f['lookback_days']}d; recency-weighted "
                             f"tone {tone:+.2f}.", pts, f)


# --------------------------------------------------------------------------
class SentimentAnalyst(Analyst):
    name = "sentiment"
    role = ("Sentiment Analyst. You gauge crowd sentiment and positioning from social-media "
            "posts and market-based proxies, flagging when sentiment is extreme enough to be "
            "a contrarian signal.")
    instructions = ("Estimate short-term sentiment. Moderate optimism supports the trend; "
                    "euphoric or capitulating extremes are contrarian warnings.")
    untrusted_keys = ("sample_posts",)

    def gather(self, state, provider):
        posts = provider.social(state.instrument, state.as_of, 7)
        posts = [p for p in posts if p.published <= state.as_of]
        h = state.history
        c = h["Close"].to_numpy()
        f: dict[str, Any] = {"posts": len(posts)}
        if posts:
            scores = [_score(p, state) for p in posts]
            recent = [s for p, s in zip(posts, scores) if (state.as_of - p.published).days <= 2]
            f["mean_post_sentiment"] = float(np.mean(scores))
            f["recent_post_sentiment"] = float(np.mean(recent)) if recent else None
            f["bullish_share"] = float(np.mean([s > 0.2 for s in scores]))
            f["sample_posts"] = [p.headline for p in posts[-8:]]
        if len(c) > 5:
            f["return_5d"] = float(c[-1] / c[-6] - 1.0)
        f["rsi14"] = _last(quant.rsi(c, 14))
        vol = h["Volume"].to_numpy(dtype=float)
        if len(vol) >= 60 and vol[-20:].sum() > 0:
            base = vol[-60:-1]
            f["volume_zscore"] = float((vol[-1] - base.mean()) / (base.std() or 1.0))
        return f

    def rules(self, f, state):
        s, pts = 0.0, []
        extreme = False
        if f.get("posts"):
            m = f["mean_post_sentiment"]
            s += 0.6 * m
            pts.append(f"{f['posts']} social posts, mean tone {m:+.2f}, "
                       f"{f['bullish_share']:.0%} bullish")
            if (r := f.get("recent_post_sentiment")) is not None:
                s += 0.2 * (r - m)
                pts.append(f"Last-2-day tone {r:+.2f} ({'improving' if r > m else 'fading'})")
        else:
            pts.append("No social-media feed; using market-based proxies only")
        rsi = f.get("rsi14")
        if rsi is not None and (rsi > 78 or rsi < 22):
            extreme = True
            s += -0.3 if rsi > 78 else 0.3
            pts.append(f"RSI {rsi:.0f} signals crowd {'euphoria' if rsi > 78 else 'capitulation'} "
                       "(contrarian)")
        if (vz := f.get("volume_zscore")) is not None and abs(vz) > 2:
            pts.append(f"Volume spike ({vz:+.1f} sigma): attention elevated")
        if not f.get("posts") and not extreme:
            return AnalystReport(self.name, 0.0, 0.15, "No sentiment data and no crowding "
                                 "extreme; no view.", pts, f, abstained=True)
        sig = clip(s, -1, 1)
        conf = 0.45 if f.get("posts") else 0.15
        return AnalystReport(self.name, sig, conf, f"Crowd sentiment score {sig:+.2f}.", pts, f)


# --------------------------------------------------------------------------
class AlphaAnalyst(Analyst):
    """Quant analyst: the alpha library's combined signal, weighted by *significant* IC only.

    Uses the ``quant.alpha`` tool output when the agentic harness ran it (so the IC table is
    evidence); otherwise computes the snapshot from the state's history. Either way, the
    *decision* always goes through ``alpha.significant_alpha_signal``: only alphas whose IC
    t-statistic clears the significance bar (``|t(IC)| >= 2`` and at least 30 observations)
    get non-zero weight in the combination, and the analyst abstains when none qualify. This
    is stricter than a plain IC-weighted average -- weighting by ``max(0, IC)`` let many
    near-zero, statistically insignificant alphas add turnover without predictive value (see
    docs/evaluation/evaluation.md). Using one shared function for both invocation paths also
    fixes a real inconsistency: the ``quant.alpha`` tool's own "combined" field is an
    equal-weighted composite over *every* alpha (useful as a general-purpose diagnostic), and
    naively trusting it under the harness would have silently bypassed the significance gate
    that applies when the analyst computes its own snapshot directly.
    """
    name = "alpha"
    role = ("Quantitative Alpha Analyst. You read a library of systematic signals (momentum, "
            "reversal, breakout, volatility, carry) and their measured predictive power, and "
            "give a direction for the next one to four weeks.")
    instructions = ("Only trust a signal whose IC t-statistic is at least 2 in magnitude; report "
                    "its combined view and the strongest components, and abstain when none qualify.")
    min_ic_tstat = 2.0
    min_ic_n = 30
    # The desk's general lookback (config["lookback_days"], 400 by default) is sized for
    # the other analysts. A 273-day signal like tsmom_12_1 barely produces its first
    # non-NaN value in that window, leaving too few points to ever clear the significance
    # bar. The alpha analyst needs a much longer history to estimate IC at all reliably,
    # so it fetches its own window -- config["alpha_lookback_days"], the same knob the
    # ``quant.alpha`` / ``quant.xalpha`` tools default to -- instead of reusing
    # ``state.history``, so the harness path and the direct path see the same window.
    @property
    def lookback_days(self) -> int:
        return int(self.config.get("alpha_lookback_days", 900))

    def gather(self, state, provider):
        from datetime import timedelta

        import pandas as pd

        from ..alpha import alpha_snapshot, compute_alphas, forward_returns, information_coefficient
        if state.alpha:
            return {"latest": dict(state.alpha.get("latest") or {}), "ic": dict(state.alpha.get("ic") or {})}
        ins = state.instrument
        df = provider.history(ins, state.as_of - timedelta(days=self.lookback_days), state.as_of)
        df = df[df.index <= pd.Timestamp(state.as_of)]
        carry = provider.carry_series(ins, df.index) if ins.is_fx else None
        latest = alpha_snapshot(df, ins, carry)
        ic = {}
        if len(df) >= 120:
            sig = compute_alphas(df, ins, None, carry)
            horizon = 10
            fwd = forward_returns(df["Close"].to_numpy(float), horizon)
            for name in sig.columns:
                v, t, n = information_coefficient(sig[name].to_numpy(), fwd, horizon)
                ic[name] = {"IC": v, "t(IC)": t, "n": n}
        return {"latest": latest, "ic": ic}

    def rules(self, f, state):
        from ..alpha import significant_alpha_signal
        latest, ic = f.get("latest") or {}, f.get("ic") or {}
        comb, strong_names = significant_alpha_signal(latest, ic, self.min_ic_tstat, self.min_ic_n)
        if comb is None:
            return self.abstain(
                "No alpha signal clears the significance bar (|t(IC)| >= 2, n >= 30) over the "
                "lookback." if ic else "Not enough history for the alpha library.", f)
        pts = []
        for name in strong_names[:3]:
            v = ic[name]
            val = latest.get(name)
            pts.append(f"{name}: value {val:+.2f}, IC {v['IC']:+.3f} (t {v['t(IC)']:.1f})"
                       if val is not None else f"{name}: IC {v['IC']:+.3f}")
        sig = clip(comb, -1, 1)
        conf = clip(0.3 + 0.3 * abs(sig) + 0.05 * len(strong_names), 0, 0.8)
        total = sum(1 for v in ic.values() if v.get("IC") is not None)
        return AnalystReport(self.name, sig, conf,
                             f"IC-weighted alpha composite {sig:+.2f} from {len(strong_names)} of "
                             f"{total} signals with |t(IC)| >= {self.min_ic_tstat:.0f} over the "
                             "lookback.", pts, f)


class XAlphaAnalyst(Analyst):
    """Cross-sectional quant analyst: where this name ranks *within its universe* today.

    The time-series alpha analyst asks whether a signal predicts this instrument's own
    forward return. This one asks the question a stock-picker asks: ranked against its
    peers on the same signals, is the name at the top or the bottom of the room? Signals
    are z-scored across the configured universe (``xalpha_universe``; the core universe
    of its asset class by default) on every date, each alpha's cross-sectional IC is
    measured over ``alpha_lookback_days``, and -- exactly as for ``AlphaAnalyst`` --
    only alphas whose IC t-statistic clears the significance bar carry weight through
    ``alpha.significant_alpha_signal``; the analyst abstains when none does.

    The universe's histories are fetched once per (universe, date) and cached across
    instruments and threads, so an evaluation over the whole universe pays for the
    cross-section once per decision date.
    """
    name = "xalpha"
    role = ("Cross-Sectional Alpha Analyst. You rank this instrument against its peer universe on "
            "systematic signals (momentum, reversal, breakout, volatility, carry) whose cross-sectional "
            "predictive power has been measured, and give a relative direction for the next one to "
            "four weeks.")
    instructions = ("Only trust a signal whose cross-sectional IC t-statistic is at least 2 in magnitude; "
                    "report the name's rank-based combined view and the strongest components, and abstain "
                    "when none qualify.")
    min_ic_tstat = 2.0
    min_ic_n = 30
    horizon = 10
    min_names = 5

    @property
    def lookback_days(self) -> int:
        return int(self.config.get("alpha_lookback_days", 900))

    def universe(self, state) -> list[str]:
        """Peers of the instrument's asset class from ``xalpha_universe`` (default: the core
        universe of that class), plus the instrument itself. A mixed list is filtered by
        asset class, so one configured list serves equities and FX."""
        from ..instruments import Instrument
        names = self.config.get("xalpha_universe")
        if not names:
            from ..evaluation import CORE_UNIVERSE
            names = CORE_UNIVERSE[state.instrument.asset_class]
        out = []
        for n in names:
            try:
                ins = Instrument.parse(n)
            except ValueError:
                continue
            if ins.asset_class == state.instrument.asset_class and ins.symbol not in out:
                out.append(ins.symbol)
        if state.instrument.symbol not in out:
            out.append(state.instrument.symbol)
        return out

    def gather(self, state, provider):
        from datetime import timedelta

        import pandas as pd

        from ..instruments import Instrument
        from ..xalpha import _combine_scores, cross_sectional_ic, cs_zscore, forward_return_panel, ic_summary, signal_panels
        names = self.universe(state)
        key = (tuple(names), state.as_of, self.horizon, self.lookback_days)
        cache = _xalpha_cache_for(provider)
        with _XALPHA_LOCK:
            cached = cache.get(key)
        if cached is None:
            frames, instruments, carry = {}, {}, {}
            start = state.as_of - timedelta(days=self.lookback_days)
            for n in names:
                try:
                    ins = Instrument.parse(n)
                    df = provider.history(ins, start, state.as_of)
                except Exception:  # a missing peer shrinks the cross-section; it does not stop it
                    continue
                df = df[df.index <= pd.Timestamp(state.as_of)]
                if len(df) < 300:
                    continue
                frames[ins.symbol], instruments[ins.symbol] = df, ins
                if ins.is_fx:
                    carry[ins.symbol] = provider.carry_series(ins, df.index)
            if len(frames) >= self.min_names:
                # The same standardisation and IC as xalpha_report / xalpha_snapshot, without the
                # decay curves, quantile spreads and correlations the analyst does not use
                # (those cost about six times the IC itself, once per decision date).
                groups = {s: instruments[s].asset_class for s in frames}
                panels = signal_panels(frames, instruments, None, carry or None)
                closes = pd.DataFrame({s: df["Close"] for s, df in frames.items()}).sort_index()
                fwd = forward_return_panel(closes, self.horizon)
                ppy = float(np.mean([instruments[s].periods_per_year for s in frames]))
                scores, ic = {}, {}
                for n, panel in panels.items():
                    sc = cs_zscore(panel, groups, min_names=3)
                    scores[n] = sc
                    summ = ic_summary(cross_sectional_ic(sc, fwd, self.min_names), self.horizon, ppy)
                    ic[n] = {"IC": float(summ["mean IC"]), "t(IC)": float(summ["t(IC)"]), "n": int(summ["days"])}
                scores["combined"] = _combine_scores(scores, None)
                snap: dict[str, dict[str, float | None]] = {s: {} for s in frames}
                for n, sc in scores.items():
                    if sc.empty:
                        continue
                    last = sc.iloc[-1]
                    for s in frames:
                        v = last.get(s)
                        snap[s][n] = None if v is None or pd.isna(v) else float(v)
                cached = (snap, ic, sorted(frames))
            else:
                cached = ({}, {}, sorted(frames))
            _xalpha_cache_put(cache, key, cached)
        snap, ic, members = cached
        me = dict(snap.get(state.instrument.symbol) or {})
        return {"universe": members, "breadth": len(members), "horizon": self.horizon,
                "latest": {k: v for k, v in me.items() if k != "combined"}, "combined_z": me.get("combined"), "ic": ic}

    def rules(self, f, state):
        from ..alpha import significant_alpha_signal
        latest, ic = f.get("latest") or {}, f.get("ic") or {}
        if f.get("breadth", 0) < self.min_names:
            return self.abstain(f"Cross-section too thin ({f.get('breadth', 0)} names with enough history).", f)
        if state.instrument.symbol not in (f.get("universe") or []) or not latest:
            return self.abstain(f"{state.instrument.symbol} has too little history (< 300 bars) to be scored "
                                f"against the {f.get('breadth', 0)}-name cross-section.", f)
        comb, strong = significant_alpha_signal(latest, ic, self.min_ic_tstat, self.min_ic_n)
        if comb is None:
            return self.abstain("No cross-sectional alpha clears the significance bar (|t(IC)| >= 2, "
                                "n >= 30) over the lookback." if ic else "Not enough history for the cross-section.", f)
        pts = []
        for name in strong[:3]:
            v, val = ic[name], latest.get(name)
            pts.append(f"{name}: z {val:+.2f} vs {f['breadth']} peers, IC {v['IC']:+.3f} (t {v['t(IC)']:.1f})"
                       if val is not None else f"{name}: IC {v['IC']:+.3f}")
        sig = clip(comb, -1, 1)
        conf = clip(0.3 + 0.3 * abs(sig) + 0.05 * len(strong), 0, 0.8)
        return AnalystReport(self.name, sig, conf,
                             f"Cross-sectional composite {sig:+.2f} from {len(strong)} significant alpha(s) "
                             f"across {f['breadth']} names.", pts, f)


# One cache per provider (weakly referenced, so it dies with the provider and can never
# serve another provider's data), one entry per (universe, date): a walk-forward
# evaluation asks for every decision date of the first instrument before the second
# starts, so a cache must hold a whole period's dates (a few hundred) or every later
# name recomputes them. Reads and writes are locked: evaluate(workers>1) shares it.
import threading as _threading
import weakref as _weakref

_XALPHA_CACHES: "_weakref.WeakKeyDictionary" = _weakref.WeakKeyDictionary()
_XALPHA_LOCK = _threading.Lock()
_XALPHA_CACHE_MAX = 4096


def _xalpha_cache_for(provider) -> dict:
    with _XALPHA_LOCK:
        cache = _XALPHA_CACHES.get(provider)
        if cache is None:
            cache = _XALPHA_CACHES[provider] = {}
        return cache


def _xalpha_cache_put(cache: dict, key, value) -> None:
    with _XALPHA_LOCK:
        while len(cache) >= _XALPHA_CACHE_MAX:
            cache.pop(next(iter(cache)), None)
        cache[key] = value


ANALYSTS = {
    "technical": TechnicalAnalyst,
    "fundamentals": FundamentalsAnalyst,
    "macro": MacroAnalyst,
    "news": NewsAnalyst,
    "sentiment": SentimentAnalyst,
    "alpha": AlphaAnalyst,
    "xalpha": XAlphaAnalyst,
}
