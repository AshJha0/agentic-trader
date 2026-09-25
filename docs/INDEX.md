# Documentation index

The landing site, https://ashjha0.github.io/agentic-trader/, is served from this folder. See
[GITHUB_PAGES.md](GITHUB_PAGES.md) for how it is published.

| Document | What it is for |
|---|---|
| [../README.md](../README.md) | Overview, results in one paragraph, setup, usage, layout, configuration |
| [../LEARN.md](../LEARN.md) | Guided tour in three parts (the firm, trading it for real, knowing whether it works): 18 concepts with real numbers and questions |
| [../COOKBOOK.md](../COOKBOOK.md) | 38 copy-pasteable recipes, including real-life workflows (positions, watchlists, portfolios, evaluation, cost stress, spend caps, bad input). Every runnable recipe is executed when the docs are checked |
| [SPECIFICATION.md](SPECIFICATION.md) | Requirements from the paper and this project, each marked realised, partial or roadmap |
| [architecture/overview.md](architecture/overview.md) | Components, one decision step by step, backtesting and evaluation layers, design decisions, configuration, extension points |
| [DIAGRAMS.md](DIAGRAMS.md) | Sixteen Mermaid diagrams: pipeline, agent pattern, sequence, state, sizing chain, guardrails and band, injection containment, point-in-time FRED, backtest timing, stop fills, portfolio and scan, memory, evaluation protocol, backend selection, packages, CI |
| [threat-model/threat-model.md](threat-model/threat-model.md) | Assets, trust boundaries, 20 threats mapped to controls and tests, residual risks |
| [evaluation/evaluation.md](evaluation/evaluation.md) | Design / holdout / paper-window protocol, v0.2 vs v0.3, ablation, per-instrument and portfolio results, limitations |
| [api/api.md](api/api.md) | Python API, evaluation, quant functions, state documents, CLI, C++ API, `at_backtest` |
| [GITHUB_PAGES.md](GITHUB_PAGES.md) | How the site is published and how to keep its numbers honest |
| [../CHANGELOG.md](../CHANGELOG.md) | Release notes |
