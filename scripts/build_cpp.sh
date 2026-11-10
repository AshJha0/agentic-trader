#!/usr/bin/env bash
# Builds the C++ core, the at_backtest CLI, the C++ tests and the Python extension.
# Requires: CMake >= 3.18, a C++17 compiler and pybind11 in the project virtual environment
# (`pip install -e ".[all]"` installs it).
#
# The interpreter is .venv/bin/python (or .venv/Scripts/python.exe under Git Bash) when it
# exists; otherwise python3/python on PATH, with a clear error if pybind11 is missing there.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -x .venv/bin/python ]; then
  PY=.venv/bin/python
elif [ -x .venv/Scripts/python.exe ]; then
  PY=.venv/Scripts/python.exe
elif command -v python3 >/dev/null 2>&1; then
  PY=$(command -v python3); echo "warning: no .venv found; using $PY" >&2
elif command -v python >/dev/null 2>&1; then
  PY=$(command -v python); echo "warning: no .venv found; using $PY" >&2
else
  echo "error: no .venv and no python on PATH; create one: python3 -m venv .venv && .venv/bin/pip install -e '.[all]'" >&2
  exit 1
fi
if ! PYBIND_DIR=$("$PY" -m pybind11 --cmakedir 2>/dev/null); then
  echo "error: pybind11 is not installed for $PY; run: $PY -m pip install pybind11 (or pip install -e '.[all]')" >&2
  exit 1
fi
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -Dpybind11_DIR="$PYBIND_DIR" -DPython_EXECUTABLE="$PY"
cmake --build build --config Release -j
ctest --test-dir build -C Release --output-on-failure
"$PY" -c "import agentic_trader.quant as q; print('quant backend:', q.BACKEND)"
