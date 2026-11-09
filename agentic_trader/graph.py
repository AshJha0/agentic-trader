"""The trading-desk workflow.

    Analyst team  ->  Bull/Bear debate + facilitator  ->  Trader
        ->  Risk team discussion  ->  Portfolio Manager  ->  decision (+ memory)

``TradingGraph.propagate(symbol, as_of)`` runs one pass and returns the full
structured state together with the final decision. The pass is built from
stage methods (``prepare``, ``run_analyst``, ``run_debate``, ``run_trader``,
``run_risk``, ``record``) so the agentic harness can execute the same stages
under a plan, with policy checks and evidence, without a second orchestration.
"""
from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from pathlib import Path
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

import pandas as pd

from .agents import (ANALYSTS, BearResearcher, BullResearcher, DebateFacilitator,
                     PortfolioManager, RiskAnalyst, Trader, run_debate, run_risk_team)
from .anonymize import Anonymizer
from .config import make_config
from .data import MarketDataProvider, get_provider
from .validate import MAX_GAP_DAYS, require_valid_bars
from .instruments import Instrument
from .llm import LLM, budget_llm, get_llm
from .memory import DecisionMemory, series_basis
from .state import AnalystReport, Book, DebateOutcome, FinalDecision, TradeProposal, TradingState

if TYPE_CHECKING:
    from .combine import SignalInputs
    from .regime import RegimeSeries
    from .text_analysts import TextInputs


@dataclass
class _ResearchSeries:
    """One provider's research history for one name, from a fixed first bar to
    ``config["research_history_end"]``, with the per-bar inputs built on it once.
    ``provider`` is held so the ``id()`` in the cache key cannot be reused."""
    provider: MarketDataProvider
    hist: pd.DataFrame
    inputs: "SignalInputs | None" = None
    regime: "RegimeSeries | None" = None


log = logging.getLogger(__name__)

DEFAULT_ANALYSTS = {
    "equity": ["technical", "fundamentals", "news", "sentiment"],
    "fx": ["technical", "macro", "news", "sentiment"],
}

Event = Callable[[str, str], None]  # (stage, message)


class TradingGraph:
    def __init__(self, config: dict | None = None, provider: MarketDataProvider | None = None,
                 llm: LLM | None = None, memory: DecisionMemory | None = None,
                 on_event: Event | None = None):
        self.config = make_config(config)
        self.provider = provider or get_provider(self.config)
        self.llm = llm if llm is not None else get_llm(self.config)
        if self.llm is not None:
            self.llm = budget_llm(self.llm, self.config)
        self.memory = memory if memory is not None else DecisionMemory(
            self.config.get("memory_path"), max_staleness_days=self.max_staleness_days)
        self.on_event = on_event or (lambda stage, msg: log.info("[%s] %s", stage, msg))
        self._research: dict[tuple[int, str, date], _ResearchSeries] = {}
        self.text_inputs: TextInputs | None = None   # built from the config on first use
        self.text_llm = None      # backend for the text analysts (None = self.llm)

        c, m = self.config, self.llm
        self.bull, self.bear = BullResearcher(m, c), BearResearcher(m, c)
        self.facilitator = DebateFacilitator(m, c)
        self.trader = Trader(m, c)
        self.risk_team = [RiskAnalyst(m, c, s) for s in ("aggressive", "neutral", "conservative")]
        self.pm = PortfolioManager(m, c)

    @property
    def max_staleness_days(self) -> int:
        """How far the decision day may sit after its last bar: the guard in ``prepare`` and the
        memory's entry-bar tolerance read the same setting, so an entry the desk was allowed to
        decide on is one its memory can value."""
        return int(self.config.get("max_data_staleness_days", 7))

    # ------------------------------------------------------------ stages
    def analyst_names(self, instrument: Instrument) -> list[str]:
        names = list(self.config.get("analysts") or DEFAULT_ANALYSTS[instrument.asset_class])
        out = []
        for n in names:
            if n == "fundamentals" and instrument.is_fx:
                n = "macro"  # FX has no company fundamentals
            if n == "macro" and not instrument.is_fx:
                n = "fundamentals"
            if n not in ANALYSTS:
                raise ValueError(f"unknown analyst {n!r}; choose from {sorted(ANALYSTS)}")
            if n not in out:
                out.append(n)
        return out

    def prepare(self, symbol: str | Instrument, as_of: date | str, asset_class: str | None = None,
                current_weight: float | None = None,
                provider: MarketDataProvider | None = None,
                book: Book | None = None) -> TradingState:
        """Load point-in-time data, apply the guards, consult memory; no agent runs yet.

        ``book`` is the rest of the current book (other symbols' positions and an aligned
        return history) for a book-level VaR check; see ``state.Book`` and ``scan()``, which
        builds one automatically when ``config["risk"]["max_book_var_95"]`` is set.
        """
        ins = symbol if isinstance(symbol, Instrument) else Instrument.parse(symbol, asset_class)
        as_of = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of
        if current_weight is not None and not math.isfinite(current_weight):
            raise ValueError("current_weight must be a finite number")
        provider = provider or self.provider

        start = as_of - timedelta(days=self.config["lookback_days"])
        hist = provider.history(ins, start, as_of)
        hist = hist[hist.index <= pd.Timestamp(as_of)]  # point-in-time guard, whatever the provider does
        # An outage the desk tolerates at the end of the series (max_data_staleness_days) is
        # tolerated inside it too, so the gap limit is the larger of the two.
        asset_class = "fx" if ins.is_fx else "equity"
        require_valid_bars(hist, asset_class, f"{ins.display} history to {as_of}",
                           max(MAX_GAP_DAYS[asset_class], self.max_staleness_days))
        if len(hist) < 30:
            raise ValueError(f"not enough history for {ins.display} up to {as_of} "
                             f"({len(hist)} bars)")
        # Decisions are for the last available bar (as_of may be a weekend/holiday),
        # but never on a price so old it no longer describes the market.
        bar_date = hist.index[-1].date()
        stale = (as_of - bar_date).days
        if stale > self.max_staleness_days:
            raise ValueError(f"latest {ins.display} bar is {bar_date}, {stale} days before "
                             f"{as_of}: refusing to decide on stale data")
        state = TradingState(ins, as_of, hist, current_weight=current_weight, book=book,
                             provider_name=getattr(provider, "name", ""), price_basis=series_basis(provider))
        if self.llm is not None and self.config.get("llm_anonymize"):
            state.anon = Anonymizer(ins, as_of, state.last_price)

        # Outcomes are valued on this very series (which ends at as_of), by the provider
        # that recorded them, so a rebase or a provider switch cannot fake a verdict.
        self.memory.resolve(ins.symbol, as_of, hist, provider=state.provider_name,
                            price_basis=state.price_basis, max_staleness_days=self.max_staleness_days)
        state.lessons = self.memory.lessons(ins.symbol, as_of, provider=state.provider_name)
        state.track_record = self.memory.track_record(ins.symbol, as_of, provider=state.provider_name)
        self.on_event("data", f"{ins.display} {ins.asset_class}: {len(hist)} bars to {bar_date}, "
                              f"last {state.last_price:.6g}")
        self._research_forecast(state, provider)
        return state

    def _research_forecast(self, state: TradingState, provider: MarketDataProvider) -> None:
        """Fill ``state.regime`` and ``state.forecast`` when their v0.14 switches are on.

        Both read one longer point-in-time history (bars ``<= as_of``): the IC combination
        needs ``window`` bars of signals plus the alpha library's warm-up, the regime model
        the bars from ``regime.fit_start``. Neither touches anything when its switch is off.
        """
        comb, reg, conf = self.config["combination"], self.config["regime"], self.config["conformal"]
        use_ic = comb["method"] == "ic"
        if comb["method"] not in ("rules", "ic"):
            raise ValueError(f"combination.method must be 'rules' or 'ic', not {comb['method']!r}")
        if (reg["condition"] or conf["enabled"]) and not use_ic:
            raise ValueError("regime.condition and conformal.enabled need combination.method 'ic'")
        if not (use_ic or reg["enabled"]):
            return
        ins, as_of = state.instrument, state.as_of
        days = int((int(comb["window"]) + 300 + int(comb["horizon"])) * 1.5)
        start = as_of - timedelta(days=max(days, self.config["lookback_days"]))
        floor = date.fromisoformat(reg["fit_start"]) - timedelta(days=150) if reg["enabled"] else None
        if floor is not None:
            start = min(start, floor)
        series = self._research_series(provider, state, start, floor)
        if series is None:
            hist = provider.history(ins, start, as_of)
            hist = hist[hist.index <= pd.Timestamp(as_of)]
        else:
            hist = series.hist.iloc[:int(series.hist.index.searchsorted(pd.Timestamp(as_of), "right"))]
        n = len(hist)
        labels = None
        if reg["enabled"]:
            from .regime import REGIME_NAMES, RegimeSeries
            k = int(reg["states"])
            # Refit monthly: the fit ends at the earlier of the design end and the first day
            # of the as-of month, so every fit uses bars before the decision only.
            fit_end = min(pd.Timestamp(reg["fit_end"]), pd.Timestamp(as_of.replace(day=1)))
            if series is None:
                rs = RegimeSeries(hist["Close"], provider.risk_free_series(hist.index), ins.periods_per_year)
            else:
                if series.regime is None:
                    series.regime = RegimeSeries(series.hist["Close"], provider.risk_free_series(series.hist.index),
                                                 ins.periods_per_year)
                rs = series.regime
            lab, probs, _ = rs.labels(n - 1, k, pd.Timestamp(reg["fit_start"]), fit_end)
            if probs is not None:
                state.regime = {"label": int(lab[-1]), "name": REGIME_NAMES[k][int(lab[-1])],
                                "prob": float(probs[int(lab[-1])])}
                if reg["condition"]:
                    labels = lab
        if use_ic:
            from .combine import desk_forecast, signal_inputs
            cfg = {**comb, "conformal": conf}
            if series is None:
                carry = provider.carry_series(ins, hist.index) if ins.is_fx else None
                state.forecast = desk_forecast(hist, ins, cfg, carry, labels)
            else:
                if series.inputs is None:
                    carry = provider.carry_series(ins, series.hist.index) if ins.is_fx else None
                    series.inputs = signal_inputs(series.hist, ins, cfg, carry)
                state.forecast = desk_forecast(hist, ins, cfg, None, labels, series.inputs.head(n))

    def _research_series(self, provider: MarketDataProvider, state: TradingState, start: date,
                         floor: date | None) -> _ResearchSeries | None:
        """The cached research series when it can stand in for the per-decision history.

        That needs ``config["research_history_end"]`` at or after the as-of date and a first
        bar that does not move with the as-of date: ``start == floor``, the regime model's
        fixed history start. When the start moves (the IC combination alone), the recursive
        indicators (EMA, Wilder) and the warm-up of the trailing z-scores depend on it, so a
        panel sliced from one long series would differ from the per-decision panel; that
        path rebuilds per decision. Returns ``None`` when the cache does not apply.
        """
        end = self.config.get("research_history_end")
        if end is None or floor is None or start != floor:
            return None
        end = date.fromisoformat(end) if isinstance(end, str) else end
        if state.as_of > end:
            return None
        key = (id(provider), state.instrument.symbol, start)
        series = self._research.get(key)
        if series is None or series.provider is not provider:
            hist = provider.history(state.instrument, start, end)
            series = _ResearchSeries(provider, hist[hist.index <= pd.Timestamp(end)])
            self._research[key] = series
        return series

    def run_analyst(self, state: TradingState, name: str,
                    provider: MarketDataProvider | None = None) -> AnalystReport:
        if name not in ANALYSTS:
            raise ValueError(f"unknown analyst {name!r}; choose from {sorted(ANALYSTS)}")
        r = ANALYSTS[name](self.llm, self.config).run(state, provider or self.provider)
        self.on_event("analyst", f"{r.analyst:<12} signal {r.signal:+.2f} conf {r.confidence:.2f} "
                                 f"[{r.source}] {r.summary}")
        return r

    def run_text_analysts(self, state: TradingState) -> list[AnalystReport]:
        """The v0.15 text analysts named in ``config["text_analysts"]`` (default none: a no-op).

        They read fenced EDGAR sections and central-bank text visible at the decision cut-off
        (``text_analysts.text_cutoff``) through ``self.text_inputs`` (built from
        ``config["text_analyst_options"]`` on first use) and the model in ``self.text_llm``
        (default: the desk's model). Each report joins ``state.reports``.
        """
        names = list(self.config.get("text_analysts") or [])
        if not names:
            return []
        from .text_analysts import TextInputs, text_reports
        if self.text_inputs is None:
            self.text_inputs = TextInputs.from_config(self.config)
        llm = self.text_llm if self.text_llm is not None else self.llm
        reports = text_reports(names, llm, self.text_inputs, state.instrument, state.as_of)
        for r in reports:
            state.reports[r.analyst] = r
            self.on_event("analyst", f"{r.analyst:<12} signal {r.signal:+.2f} conf {r.confidence:.2f} "
                                     f"[{r.source}] {r.summary}")
        return reports

    def run_debate(self, state: TradingState, rounds: int | None = None) -> DebateOutcome:
        d = run_debate(state, self.bull, self.bear, self.facilitator,
                       self.config["max_debate_rounds"] if rounds is None else rounds)
        self.on_event("debate", f"{len(d.turns)} turns -> winner {d.winner}, score {d.score:+.2f} "
                                f"[{d.source}]")
        return d

    def run_trader(self, state: TradingState) -> TradeProposal:
        p = self.trader.run(state)
        self.on_event("trader", f"{p.action.value} {p.target_weight:+.2f} [{p.source}]")
        return p

    def run_risk(self, state: TradingState, rounds: int | None = None) -> FinalDecision:
        dec = run_risk_team(state, self.risk_team, self.pm,
                            self.config["max_risk_discuss_rounds"] if rounds is None else rounds)
        views = ", ".join(f"{v.stance[:4]} {v.recommended_weight:+.2f}"
                          for v in state.risk_views[-len(self.risk_team):])
        self.on_event("risk", views)
        self.on_event("decision", f"{dec.action.value} target weight {dec.target_weight:+.2f} "
                                  f"(approved={dec.approved}) [{dec.source}]"
                                  + (f" | {'; '.join(dec.adjustments)}" if dec.adjustments else ""))
        return dec

    def record(self, state: TradingState) -> None:
        """Log the decision to memory and, when configured, save the report."""
        dec = state.decision
        if dec is None:
            raise ValueError("no decision to record")
        summary = self._guarded_summary(state, dec.rationale)
        self.memory.record(state.instrument.symbol, state.as_of, dec.action.value, dec.target_weight,
                           state.last_price, summary,
                           horizon_days=state.proposal.horizon_days if state.proposal else 10,
                           provider=state.provider_name, price_basis=state.price_basis)
        if self.config.get("save_reports"):
            path = self.save_report(state)
            self.on_event("report", f"saved {path}")

    def _guarded_summary(self, state: TradingState, text: str) -> str:
        """The desk's own decision summary through the output guard (v0.17, review C3) before it
        becomes a memory lesson. A refusal stores a redacted line naming the reasons instead of
        the text, so the decision is still recorded but a planted URL, foreign ticker, canary or
        instruction never reaches later prompts. ``config["agentic"]["memory_output_guard"]``
        False switches it off; ``["agentic"]["canaries"]`` adds canary strings."""
        ag = self.config.get("agentic", {}) or {}
        if not ag.get("memory_output_guard", True):
            return text
        from .agentic.output_guard import check_output
        ins = state.instrument
        allowed = {ins.symbol, getattr(ins, "display", ins.symbol)}
        allowed.update(str(s) for s in (ag.get("symbol_universe") or ()))
        allowed.update(str(s) for s in (self.config.get("xalpha_universe") or ()))
        g = check_output(str(text)[:400], allowed, ag.get("canaries") or ())
        if g.ok:
            return text
        log.warning("output guard redacted the %s %s decision summary: %s", ins.symbol, state.as_of, g.reason)
        self.on_event("guard", f"memory summary redacted: {g.reason}")
        # Only the reason categories are stored: the reasons quote the offending text.
        kinds = sorted({r.split(":", 1)[0].split()[0] for r in g.reasons})
        return f"[summary withheld by output guard: {', '.join(kinds)}]"

    # ---------------------------------------------------------- pipeline
    def propagate(self, symbol: str | Instrument, as_of: date | str,
                  asset_class: str | None = None,
                  current_weight: float | None = None,
                  book: Book | None = None) -> tuple[TradingState, FinalDecision]:
        """Run the desk once for ``symbol`` with information up to the close of ``as_of``.

        ``current_weight`` is the position held going into the decision (portfolio
        context). The trader and PM see it, and the PM's no-trade band keeps it when
        the new target is close enough. ``book`` adds a book-level VaR check across the
        rest of the current positions (see ``prepare``); ``scan()`` builds it automatically.
        """
        state = self.prepare(symbol, as_of, asset_class, current_weight, book=book)
        for name in self.analyst_names(state.instrument):
            self.run_analyst(state, name)
        self.run_text_analysts(state)
        self.run_debate(state)
        self.run_trader(state)
        dec = self.run_risk(state)
        if self.config.get("agentic", {}).get("critic_in_graph", False):
            self.run_critic(state)
        self.record(state)
        return state, dec

    def run_critic(self, state: TradingState):
        """v0.17 R2.1: the agentic critic on the plain graph path (the backtest and the P2
        study use ``propagate``), switched on by ``agentic.critic_in_graph`` (default off, so
        results produced before v0.17 are unchanged). The deterministic checks run on the
        state alone (no findings, no evidence store, no risk facts); the model critique runs
        only when ``agentic.critic_graph_llm`` is on. A flagged model/rules divergence acts
        on ``target_weight`` through ``critic.apply_weight_rule``; the confidence takes the
        critic's multiplier as in the harness. Returns the ``CriticReport``."""
        from .agentic.critic import Critic, apply_weight_rule
        from .agentic.evidence import EvidenceStore
        acfg = self.config.get("agentic", {})
        llm = self.llm if acfg.get("critic_graph_llm", False) else None
        critic = Critic({**self.config, "agentic": {**acfg, "llm_critic": llm is not None}}, llm)
        rep = critic.review(state, [], EvidenceStore())
        act = apply_weight_rule(state, rep, self.config)
        dec = state.decision
        if dec is not None:
            dec.confidence = round(dec.confidence * rep.multiplier, 4)
        state.critic_report = rep.to_dict()
        if act is not None:
            self.on_event("critic", f"{act['rule']}: weight {act['from']:+.2f} -> {act['to']:+.2f}")
        return rep

    def scan(self, symbols: list[str], as_of: date | str,
             positions: dict[str, float] | None = None,
             book_lookback_days: int = 250) -> pd.DataFrame:
        """Run the desk over a watchlist and return one row per symbol.

        A symbol that fails (no data, stale data, bad ticker) gets a row with its
        error instead of stopping the scan. ``positions`` maps symbol -> current weight;
        keys are parsed like watchlist symbols ('EUR/USD', 'EURUSD=X' and 'eurusd' are one
        holding) and an unparseable key raises ``ValueError`` before anything runs.

        When ``config["risk"]["max_book_var_95"]`` is set, every decision also sees the
        rest of the watchlist's current positions and an aligned ``book_lookback_days``
        return history, and the Portfolio Manager scales this instrument's weight down
        if the *book's* 1-day 95% historical VaR (this instrument's proposed weight plus
        every other symbol's current weight from ``positions``) would exceed the limit.
        Symbols with no position are still part of the book's return history (at zero
        weight) since a later scan could hold them; held symbols outside the watchlist are
        fetched too, since the book's VaR is the VaR of what is actually held. A held
        symbol whose history is missing or shorter than ``portfolio.MIN_BOOK_OBS`` bars
        keeps a (NaN) column, so the check fails closed for any book holding it (the
        Portfolio Manager flattens with a "could not be evaluated" note) instead of
        silently passing; at zero weight such a symbol has no effect on anyone.
        """
        rows = []
        positions = self._normalise_positions(positions)
        as_of_d = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of
        book_returns = None
        if self.config["risk"].get("max_book_var_95"):
            from .portfolio import MIN_BOOK_OBS
            start = as_of_d - timedelta(days=book_lookback_days)
            cols = {}
            watch = set()
            for x in symbols:
                try:
                    watch.add(Instrument.parse(x).symbol)
                except ValueError:
                    pass
            held_elsewhere = [s for s, w in positions.items() if w and s not in watch]
            for sym in [*symbols, *held_elsewhere]:
                try:
                    ins = Instrument.parse(sym)
                except Exception:  # the decision loop below reports the bad ticker
                    continue
                try:
                    h = self.provider.history(ins, start, as_of_d)
                    col = h[h.index <= pd.Timestamp(as_of_d)]["Close"].pct_change()
                except Exception as e:
                    log.warning("scan: could not build book history for %s: %s", sym, e)
                    col = pd.Series(dtype=float)
                bars = int(col.notna().sum())
                if bars < MIN_BOOK_OBS:
                    log.warning("scan: %s has %d bars of book history (need %d); a book holding it "
                                "cannot be VaR-checked and is flattened rather than sized",
                                ins.symbol, bars, MIN_BOOK_OBS)
                cols[ins.symbol] = col
            if cols:
                book_returns = pd.DataFrame(cols)
        for sym in symbols:
            try:
                ins = Instrument.parse(sym)
                book = None
                if book_returns is not None:
                    others = {s: w for s, w in positions.items() if s != ins.symbol}
                    book = Book(others, book_returns)
                state, d = self.propagate(ins, as_of,
                                          current_weight=positions.get(ins.symbol), book=book)
                votes = [r for r in state.reports.values() if not r.abstained]
                assert state.debate is not None  # propagate always runs the debate
                rows.append({
                    "symbol": ins.symbol, "asset_class": ins.asset_class,
                    "last": state.last_price, "action": d.action.value,
                    "target_weight": d.target_weight, "confidence": round(d.confidence, 3),
                    "stop_loss": d.stop_loss, "take_profit": d.take_profit,
                    "debate": state.debate.winner, "score": round(state.debate.score, 3),
                    "analysts_voting": len(votes), "approved": d.approved,
                    "adjustments": "; ".join(d.adjustments), "error": "",
                })
            except Exception as e:  # one bad symbol must not kill a watchlist run
                log.warning("scan: %s failed: %s", sym, e)
                rows.append({"symbol": sym.upper(), "action": "ERROR", "error": str(e)})
        return pd.DataFrame(rows)

    @staticmethod
    def _normalise_positions(positions: dict[str, float] | None) -> dict[str, float]:
        """Book positions keyed the way ``scan`` keys its return columns (``Instrument.symbol``),
        so 'EUR/USD', 'EURUSD=X' and 'eurusd ' are one holding; an unparseable key raises
        rather than becoming a position the book VaR check cannot see."""
        out: dict[str, float] = {}
        for k, v in (positions or {}).items():
            try:
                sym = Instrument.parse(k).symbol
            except ValueError as e:
                raise ValueError(f"positions: {k!r} is not a symbol the desk can hold ({e})") from e
            if sym in out and out[sym] != v:
                raise ValueError(f"positions: {k!r} and an earlier key both name {sym} with different weights")
            out[sym] = v
        return out

    def save_report(self, state: TradingState) -> Path:
        out = Path(self.config["results_dir"]) / state.instrument.symbol / state.as_of.isoformat()
        out.mkdir(parents=True, exist_ok=True)
        path = out / "report.md"
        path.write_text(state.to_markdown(), encoding="utf-8")
        return path
