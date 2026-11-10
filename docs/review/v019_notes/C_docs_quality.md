# Lane C: operations doc, build scripts, edge-case tests, docs accuracy

Evidence class: docs and offline tests. No model was run and nothing was downloaded.

## 1. Operations doc

New `docs/operations/long_runs.md`, linked from `docs/INDEX.md` and the README v0.18 section:
detached WMI launch of `.cmd` jobs (CRLF, no background start from a Bash-style tool),
`done_*` markers and per-unit resume, what dies on shutdown or reboot and the restart order
(start Ollama, check `http://127.0.0.1:11434/api/tags`, relaunch chains), spotting a hung
Ollama (process alive, port dead), the two-pass red-team v2 design, and why
`scripts/v17_exec_lag.py` must run uninterrupted. Checked in its source: it writes all output
only at the end and has no resume, so a kill loses the whole run.

## 2. Build scripts

`scripts/build_cpp.ps1` and `scripts/build_cpp.sh` now use `.venv\Scripts\python.exe` /
`.venv/bin/python` (or `.venv/Scripts/python.exe` under Git Bash) when present, fall back to
`python` on PATH with a warning, stop with a message naming the interpreter when pybind11 is
missing, pass `-DPython_EXECUTABLE` so CMake builds the extension for the same interpreter,
and (PowerShell) stop on a failing native step. README build note updated. Checked: PowerShell
parser reports 0 errors, `bash -n` passes. Not run end to end (CPU busy; no compiler run).

## 3. Tests

`tests/test_v19_edge_cases.py`, 27 tests, chosen by test-reference count (lowest first):
`nyse_calendar` (no direct tests before: holiday list, weekend observance, rule start years,
special closures, early closes incl. 2002 and Friday 24 December, session arithmetic),
`evidence_bounds` (scaling, error paths, holiday-skipping `nth_session`, hand-worked premium),
`question_overlap` (empty/stop-word questions, the 1/3 containment boundary, bigram rejection
at low containment), `output_guard` (ticker allow-list normalisation, zero-width characters,
several reasons in order, empty canary, poison threshold). Expected values are worked by hand.

## 4. Docs accuracy (v0.18)

- README: new "v0.18 (unreleased)" section: next-open fills with stops, `stats` trial-count
  flags, `--oms-corporate-actions` (default off), paper vintage `v09-engine-3`, red-team scope.
- `docs/evaluation/evaluation.md`: closing section "v0.18 changes that bear on evaluation".
- `docs/INDEX.md`: operations row; paper-freeze row names `v09-engine-3`; evaluation row
  points at the new section.
- `scripts/check_links.py`: no broken internal links (87 markdown files).

## Open items for the coordinator

- CHANGELOG entry for this lane (not edited here by instruction).
- LEARN/COOKBOOK not touched; a recipe for the restart checklist could follow.
- `docs/review/v017_notes/L4_governance.md` and `v018_notes/E_redteam_scope.md` contain an
  absolute path with a personal username in their command blocks (pre-existing; not changed).
