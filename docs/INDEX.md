# Documentation index

The landing site, https://ashjha0.github.io/agentic-trader/, is served from this folder. See
[GITHUB_PAGES.md](GITHUB_PAGES.md) for how it is published.

| Document | What it is for |
|---|---|
| [../README.md](../README.md) | Overview, results in one paragraph, setup, usage, layout, configuration |
| [../LEARN.md](../LEARN.md) | Guided tour in six parts (the desk, the agentic layer, trading it for real, knowing whether it works, v0.5: a wider test, execution costs and operations, v0.6: real filings, statistical power and the variance of a judgement): 33 concepts with real numbers and questions |
| [../COOKBOOK.md](../COOKBOOK.md) | 72 copy-pasteable recipes: decisions, backtests, quant core, LLMs, data, extending, real-life workflows, the agentic layer (harness, evidence, policy, approvals, plans, tools, knowledge, audits, API, MCP, tracing), quant research (alphas, execution, portfolio construction, deflated Sharpe), v0.5 (market impact, cross-sectional alphas, risk budgets, ALFRED vintages, dollar budgets, the task store, TLS, the extended universe) and v0.6 (EDGAR filings, the cross-sectional analyst, the paired bootstrap, repeated runs, calibration, the prompt registry, the task pool, the docs checks). Every offline recipe runs in CI |
| [SPECIFICATION.md](SPECIFICATION.md) | Requirements for the desk, the agentic layer and the research layer, each marked realised, partial or roadmap |
| [architecture/overview.md](architecture/overview.md) | The three layers, one task step by step, design decisions, configuration, extension points |
| [DIAGRAMS.md](DIAGRAMS.md) | Thirty Mermaid diagrams: pipeline, agent pattern, state, sizing, guardrails, injection containment, agentic overview, task state machine, task sequence, tool-call path, policy flow, approval flow, plan validation, evidence model, critic and audits, MCP/API topology, FRED, backtest timing, stop fills, alpha pipeline, execution, portfolio construction, evaluation protocol, packages, execution-aware backtest, cross-sectional alphas, hierarchical risk budgets, EDGAR point-in-time filings, the calibration harness, the API task pool. Every one is rendered in CI |
| [threat-model/threat-model.md](threat-model/threat-model.md) | Assets, eight trust boundaries, 40 threats mapped to controls and tests, residual risks |
| [evaluation/evaluation.md](evaluation/evaluation.md) | Design / holdout / Q1-2024 / reserve protocol, v0.2 vs v0.3, the rule ablation, the alpha-analyst checks, selection statistics, the 45-instrument extended universe, the market-impact sweep, what counts as unseen for the next rule change, per-instrument and portfolio results, limitations |
| [api/api.md](api/api.md) | Python API (desk, agentic layer, research), HTTP API, MCP server, CLI, C++ API, `at_backtest` |
| [GITHUB_PAGES.md](GITHUB_PAGES.md) | How the site is published and how to keep its numbers honest |
| [../CHANGELOG.md](../CHANGELOG.md) | Release notes |
