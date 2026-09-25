# Publishing this documentation with GitHub Pages

The `docs/` folder is ready for GitHub Pages. `docs/index.html` is a self-contained static
landing page: no build step, no Jekyll configuration and no external assets. It uses the same
style as the AgenticAICashEquities, intraday-alpha-platform and Quant-Finance-Library sites.
Every link on it points at Markdown rendered on GitHub, so nothing else needs generating.

## One-time setup

1. Push the repository to GitHub (`AshJha0/agentic-trader`). If you use a different
   repository name, update the hard-coded links in `docs/index.html` (search for
   `AshJha0/agentic-trader`) and in this file.
2. On GitHub, open **Settings → Pages → Build and deployment** and set:
   - Source: *Deploy from a branch*
   - Branch: `main`, folder: `/docs`

   Or use the CLI:

   ```bash
   gh api -X POST repos/AshJha0/agentic-trader/pages -f "source[branch]=main" -f "source[path]=/docs"
   ```
3. The site appears at `https://ashjha0.github.io/agentic-trader/` within a minute or two.
   The first deploy can take a few minutes; the Actions tab shows the
   `pages build and deployment` job.

The landing page is plain HTML, so Jekyll does not affect it. If you ever add files whose
names begin with an underscore, add an empty `docs/.nojekyll` so Pages serves them.

## What gets served

| URL | Content |
|---|---|
| `/` | `docs/index.html`: the landing page (numbers block, honesty note, boundary strip, out-of-sample results tables, component cards, sample decision, sample watchlist scan, quick start) |
| Everything else | Linked to Markdown rendered on github.com: `LEARN.md`, `COOKBOOK.md`, `docs/architecture/overview.md`, `docs/DIAGRAMS.md`, `docs/SPECIFICATION.md`, `docs/threat-model/threat-model.md`, `docs/evaluation/evaluation.md`, `docs/api/api.md` |

The Mermaid diagrams in `docs/DIAGRAMS.md` render natively on github.com; no plugin is
needed.

## Keeping the landing page honest

`docs/index.html` and `docs/evaluation/evaluation.md` quote real measured numbers. If you
change the code, re-check them against these sources:

| Figure | How to re-measure |
|---|---|
| Test counts | `pytest --collect-only -q` (per file); the `void test_` functions and `check(` calls in `cpp/tests/test_core.cpp` |
| CI jobs | `.github/workflows/ci.yml` matrix: 5 Python versions + 3 OSes |
| Decision latency | Time `TradingGraph(...).propagate("AAPL", "2024-03-01")` over 20 runs after one warm-up run |
| LLM calls per decision | Cookbook recipe 17 (prints `14 4 10` at default rounds) |
| Real-price evaluation (per instrument, design / holdout / paper) | `agentic-trader evaluate --data yahoo --periods design,holdout,paper --out results/eval_v03.json`; the same with `--rules v02` for the "before" column |
| Ablation table | The 16 config overrides listed in `docs/evaluation/evaluation.md`, each run with `evaluate(periods={"design": PERIODS["design"]})` |
| Portfolio results | `agentic-trader portfolio <15 symbols> --data yahoo --start 2022-01-03 --end 2026-06-30` (and the design dates) |
| Code size | Non-empty lines in `agentic_trader/**/*.py`, `tests/**/*.py` and `cpp/**/*.{cpp,hpp}` |
| Cookbook | Run every ```python block in `COOKBOOK.md`; all must exit 0 (recipe 35 needs network) |
| Diagrams | Parse every ```mermaid block in `docs/DIAGRAMS.md` with Mermaid 11 |

The evaluation tables are generated from the saved JSON with pandas (`to_markdown`), not
typed by hand. Keep it that way.

A wrong number on the landing page is a documentation bug. Treat it like one.
