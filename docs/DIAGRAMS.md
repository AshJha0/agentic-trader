# Diagrams

These Mermaid diagrams render natively on github.com. The prose explanation is in
[architecture/overview.md](architecture/overview.md).

1. [Decision pipeline](#1-decision-pipeline)
2. [Agent pattern: tools, then rules, then LLM](#2-agent-pattern-tools-then-rules-then-llm)
3. [Sequence of one `propagate()` call](#3-sequence-of-one-propagate-call)
4. [Structured state](#4-structured-state)
5. [Portfolio-manager guardrails](#5-portfolio-manager-guardrails)
6. [Quant backend selection](#6-quant-backend-selection)
7. [Walk-forward backtest timing](#7-walk-forward-backtest-timing)
8. [Memory without look-ahead](#8-memory-without-look-ahead)
9. [Package dependencies](#9-package-dependencies)
10. [CI matrix](#10-ci-matrix)

## 1. Decision pipeline

```mermaid
flowchart TD
    D[("Market data<br/>point-in-time, up to the as-of close")] --> A
    subgraph A["Analyst team (quick tier)"]
        T[Technical]
        F["Fundamentals (equity)<br/>or Macro / rates (FX)"]
        N[News]
        S[Sentiment]
    end
    A -->|4 AnalystReports| R
    subgraph R["Research team (deep tier)"]
        B[Bull researcher] <-->|n rounds| BR[Bear researcher]
        B --> FA[Facilitator]
        BR --> FA
    end
    FA -->|DebateOutcome| TR["Trader<br/>weight, stop, target, horizon"]
    TR -->|TradeProposal| K
    subgraph K["Risk management team (deep tier)"]
        AG[Aggressive] <--> NE[Neutral] <--> CO[Conservative]
    end
    K -->|3 RiskViews per round| PM[Portfolio manager]
    PM --> G{{"Firm limits<br/>short policy, max position,<br/>VaR95 cap, min trade"}}
    G --> DEC[/FinalDecision/]
    DEC --> M[(Decision memory)]
    M -.->|"lessons + track record<br/>(resolved outcomes only)"| TR
```

## 2. Agent pattern: tools, then rules, then LLM

```mermaid
flowchart LR
    S[TradingState] --> G["gather()<br/>tools: C++ indicators,<br/>providers, risk stats"]
    G --> FA[(facts)]
    FA --> RU["rules()<br/>transparent rule-based judgement"]
    RU --> RR[rule-based result]
    FA --> Q{LLM enabled?}
    Q -- no --> OUT[result = rule-based]
    Q -- yes --> L["Claude<br/>facts → JSON"]
    L --> V{"valid JSON with<br/>required keys?"}
    V -- yes --> CL["clip to valid ranges<br/>source = llm"]
    V -- "no / error / refusal" --> OUT
    RR --> OUT
    CL --> W[write into TradingState]
    OUT --> W
```

## 3. Sequence of one `propagate()` call

```mermaid
sequenceDiagram
    participant U as Caller
    participant G as TradingGraph
    participant P as Provider
    participant Mem as Memory
    participant An as Analysts
    participant Rs as Bull/Bear + Facilitator
    participant Tr as Trader
    participant Rk as Risk team
    participant PM as Portfolio manager
    U->>G: propagate("EURUSD", 2024-03-01)
    G->>P: history(ins, as_of - lookback, as_of)
    P-->>G: OHLCV (clipped again to <= as_of)
    G->>Mem: resolve(), lessons(), track_record()
    loop 4 analysts
        G->>An: run(state, provider)
        An->>P: news / social / fundamentals / macro (as_of)
        An-->>G: AnalystReport
    end
    loop max_debate_rounds
        G->>Rs: bull.speak(), bear.speak()
    end
    Rs-->>G: DebateOutcome (facilitator)
    G->>Tr: run(state)
    Tr-->>G: TradeProposal
    loop max_risk_discuss_rounds
        G->>Rk: aggressive, neutral, conservative speak
    end
    G->>PM: run(state, risk facts)
    PM-->>G: FinalDecision (after guardrails)
    G->>Mem: record(decision)
    G-->>U: (TradingState, FinalDecision)
```

## 4. Structured state

```mermaid
classDiagram
    class TradingState {
        Instrument instrument
        date as_of
        DataFrame history
        dict reports
        DebateOutcome debate
        TradeProposal proposal
        list~RiskView~ risk_views
        FinalDecision decision
        list~str~ lessons
        dict track_record
        reports_digest()
        to_markdown()
    }
    class AnalystReport {
        str analyst
        float signal
        float confidence
        str summary
        list key_points
        dict facts
        str source
    }
    class DebateOutcome {
        str winner
        float score
        float conviction
        str summary
        list~DebateTurn~ turns
    }
    class TradeProposal {
        Action action
        float target_weight
        float stop_loss
        float take_profit
        int horizon_days
    }
    class RiskView {
        str stance
        float recommended_weight
        str argument
        int round
    }
    class FinalDecision {
        Action action
        float target_weight
        bool approved
        list adjustments
        str rationale
    }
    TradingState "1" o-- "4" AnalystReport
    TradingState o-- DebateOutcome
    TradingState o-- TradeProposal
    TradingState "1" o-- "3..n" RiskView
    TradingState o-- FinalDecision
```

## 5. Portfolio-manager guardrails

```mermaid
flowchart TD
    W["weight from blend (25/50/25)<br/>or from Claude"] --> S{"w < 0 and shorting<br/>not allowed?"}
    S -- yes --> Z1[w = 0]
    S -- no --> C{"abs(w) > max_position?"}
    Z1 --> C
    C -- yes --> C1["w = ±max_position"]
    C -- no --> V{"VaR95 · abs(w) > max_var_95?"}
    C1 --> V
    V -- yes --> V1["w = ±max_var_95 / VaR95"]
    V -- no --> MN{"0 < abs(w) < min_trade_weight?"}
    V1 --> MN
    MN -- yes --> Z2[w = 0]
    MN -- no --> F[final weight]
    Z2 --> F
    F --> A["action = BUY / SELL / HOLD<br/>each adjustment recorded"]
```

## 6. Quant backend selection

```mermaid
flowchart LR
    I[import agentic_trader.quant] --> E{"AGENTIC_TRADER_BACKEND<br/>== python?"}
    E -- yes --> PY[pycore.py numpy]
    E -- no --> T{"_atcore extension<br/>importable?"}
    T -- yes --> CPP["C++17 core via pybind11<br/>BACKEND = cpp"]
    T -- no --> PY2["pycore.py numpy<br/>BACKEND = python"]
    CPP --> API["same API, numpy arrays<br/>and dataclasses out"]
    PY --> API
    PY2 --> API
```

## 7. Walk-forward backtest timing

```mermaid
flowchart LR
    subgraph t0["bar t (rebalance)"]
        C0[close t] --> DEC["propagate(as_of = t)<br/>data <= close t"]
    end
    DEC -->|"target weight w_t"| H["held from close t<br/>to next rebalance"]
    H --> R["earns return t → t+1, t+1 → t+2, …<br/>minus abs(Δw) × (cost + slippage)<br/>plus carry / minus borrow"]
    R --> N["bar t+k: next rebalance"]
```

## 8. Memory without look-ahead

```mermaid
sequenceDiagram
    participant G as TradingGraph @ as_of = d
    participant M as DecisionMemory
    G->>M: resolve(symbol, d, price_d)
    Note over M: only entries with d - entry_date >= horizon_days<br/>get pnl = weight × (price_d / entry_price - 1)
    G->>M: lessons(symbol, d)
    Note over M: only lessons with resolved_on <= d
    G->>M: record(decision_d)
```

## 9. Package dependencies

```mermaid
flowchart TD
    CLI[cli] --> GR[graph]
    CLI --> BT[backtest]
    BT --> GR
    BT --> Q[quant]
    GR --> AG[agents]
    GR --> DA[data]
    GR --> ME[memory]
    GR --> LL[llm]
    AG --> Q
    AG --> ST[state]
    AG --> SE[sentiment]
    AG --> LL
    DA --> IN[instruments]
    ST --> IN
    Q --> PYC["quant.pycore (numpy)"]
    Q -. optional .-> ATC["quant._atcore (C++)"]
    ATC --> CORE["cpp/ at_core static lib"]
```

## 10. CI matrix

```mermaid
flowchart LR
    P[push to main / pull request] --> PYJ["python job<br/>ubuntu, Python 3.10–3.14<br/>assert BACKEND == python<br/>pytest"]
    P --> CJ["cpp job<br/>ubuntu (GCC) · windows (MSVC) · macOS (Clang)"]
    CJ --> B[cmake configure + build]
    B --> CT[ctest]
    CT --> AS[assert BACKEND == cpp]
    AS --> PT["pytest incl. C++ vs numpy cross-check"]
```
