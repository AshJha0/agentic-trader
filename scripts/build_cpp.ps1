# Builds the C++ core, the at_backtest CLI, the C++ tests and the Python extension.
# Requires: CMake >= 3.18, a C++17 compiler (MSVC Build Tools or MinGW), and pybind11
# installed in the project virtual environment (`pip install -e ".[all]"` installs it).
#
# The interpreter is the project's .venv\Scripts\python.exe when it exists. A bare `python`
# on PATH is often a different interpreter without pybind11, so it is used only when no .venv
# exists, and the script stops with a clear message if pybind11 is missing from it.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $venvPy = Join-Path $root ".venv\Scripts\python.exe"
    if (Test-Path $venvPy) {
        $py = $venvPy
    } else {
        $cmd = Get-Command python -ErrorAction SilentlyContinue
        if (-not $cmd) {
            throw "No .venv\Scripts\python.exe and no python on PATH. Create the venv first: python -m venv .venv; .venv\Scripts\pip install -e "".[all]"""
        }
        $py = $cmd.Source
        Write-Warning "No .venv found; using $py"
    }
    $pybind = & $py -m pybind11 --cmakedir
    if ($LASTEXITCODE -ne 0 -or -not $pybind) {
        throw "pybind11 is not installed for $py. Run: & '$py' -m pip install pybind11 (or pip install -e "".[all]"" in the venv)"
    }
    $pybind = $pybind.Trim()
    cmake -S . -B build -DCMAKE_BUILD_TYPE=Release "-Dpybind11_DIR=$pybind" "-DPython_EXECUTABLE=$py"
    if ($LASTEXITCODE -ne 0) { throw "cmake configure failed" }
    cmake --build build --config Release
    if ($LASTEXITCODE -ne 0) { throw "cmake build failed" }
    ctest --test-dir build -C Release --output-on-failure
    if ($LASTEXITCODE -ne 0) { throw "ctest failed" }
    & $py -c "import agentic_trader.quant as q; print('quant backend:', q.BACKEND)"
} finally {
    Pop-Location
}
