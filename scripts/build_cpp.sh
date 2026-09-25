#!/usr/bin/env bash
# Builds the C++ core, the at_backtest CLI, the C++ tests and the Python extension.
# Requires: CMake >= 3.18, a C++17 compiler and `pip install pybind11`.
set -euo pipefail
cd "$(dirname "$0")/.."
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -Dpybind11_DIR="$(python -m pybind11 --cmakedir)"
cmake --build build --config Release -j
ctest --test-dir build -C Release --output-on-failure
python -c "import agentic_trader.quant as q; print('quant backend:', q.BACKEND)"
