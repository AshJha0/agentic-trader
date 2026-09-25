# Builds the C++ core, the at_backtest CLI, the C++ tests and the Python extension.
# Requires: CMake >= 3.18, a C++17 compiler (MSVC Build Tools or MinGW), and `pip install pybind11`.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $pybind = (python -m pybind11 --cmakedir).Trim()
    cmake -S . -B build -DCMAKE_BUILD_TYPE=Release "-Dpybind11_DIR=$pybind"
    cmake --build build --config Release
    ctest --test-dir build -C Release --output-on-failure
    python -c "import agentic_trader.quant as q; print('quant backend:', q.BACKEND)"
} finally {
    Pop-Location
}
