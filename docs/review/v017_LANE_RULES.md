# v0.17 lane rules (read first)

Plan: docs/review/2026-11-09_review_and_plan.md (sections 3 R0-R4, appendices A and B hold file:line evidence).

1. Start: in YOUR worktree run `git fetch -q origin; git reset --hard feat/v0.16-round2` (local branch exists in the shared repo) and verify `git log -1` shows 4b4bb2d or later. Work only in your worktree.
2. Never touch C:\Work\Claude\AgenticTrader-v16 or C:\Work\Claude\AgenticTrader (live jobs). Never call Ollama or any model; never download anything. $0, no network beyond git.
3. Do NOT edit CHANGELOG.md, docs/review/PLAN.md, README.md counts. Write your summary to docs/review/v017_notes/<lane>.md (what changed, files, tests, numbers, evidence class, follow-ups, any model runs to queue with exact commands). The maintainer folds notes into the docs.
4. Fixes with tests; every bug gets a regression test that fails on old code. No thread-timing assertions. Never the word banned by the owner rule of 2026-10-27 (a case-insensitive git grep for it must stay empty).
5. Checks: ruff check agentic_trader scripts/paper_ops.py tests (global ruff 0.17.2); mypy on touched agentic_trader files must not add errors; your tests plus related existing tests via PYTHONPATH=. C:\Work\Claude\AgenticTrader\.venv\Scripts\python.exe -m pytest <files> -q. Do NOT pip install into that venv.
6. Docs you own (LEARN/COOKBOOK sections, docs/*) follow: two audiences, plain idea then formal then worked example, evidence class on every claim, careful-engineer voice, no AI tells. New COOKBOOK recipes: put them in your notes file as text; the maintainer numbers and inserts them.
7. Commit on your worktree branch, message ends "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>". Do not push. Report: branch, sha, tests run with counts, notes file path, anything not done.
