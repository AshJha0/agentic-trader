"""Where a number came from: package version, git commit, quant backend, interpreter and
dependency versions, recorded into every saved result so that two files that disagree in
the last digit can be told apart by *what produced them* rather than by guesswork.

The version has one source of truth, ``pyproject.toml``. A source checkout reads it
directly (an editable install's distribution metadata goes stale the moment the file is
bumped); an installed wheel has no ``pyproject.toml`` and reads the metadata instead.
"""
from __future__ import annotations

import platform
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path

DIST_NAME = "agentic-trader"
_ROOT = Path(__file__).resolve().parent.parent
KEY_DEPENDENCIES = ("numpy", "pandas", "anthropic", "yfinance", "pybind11", "hypothesis")


def _version_from_pyproject(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        import tomllib
        project = tomllib.loads(text).get("project", {})
        if project.get("name") == DIST_NAME:
            return str(project.get("version")) if project.get("version") else None
        return None
    except ModuleNotFoundError:                   # Python 3.10: no tomllib
        block = text.split("[project]", 1)[-1].split("\n[", 1)[0]
        if f'name = "{DIST_NAME}"' not in block:
            return None
        m = re.search(r'^version\s*=\s*"([^"]+)"', block, re.M)
        return m.group(1) if m else None


def package_version(pyproject: Path | None = None) -> str:
    v = _version_from_pyproject(pyproject or _ROOT / "pyproject.toml")
    if v:
        return v
    try:
        return metadata.version(DIST_NAME)
    except metadata.PackageNotFoundError:
        return "0.0.0+unknown"


def git_info(root: str | None = None) -> tuple[str | None, bool | None]:
    """``(commit sha, dirty?)`` of the checkout containing the package, or ``(None, None)``
    when git or the repository is unavailable. Computed on every call (two short git
    subprocesses): a long-running process that writes results while commits land or files
    change must stamp each result with the tree state at write time, not at first call."""
    cwd = root or str(_ROOT)

    def run(*args: str) -> str | None:
        try:
            out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return None
        return out.stdout.strip() if out.returncode == 0 else None

    sha = run("rev-parse", "HEAD")
    if not sha:
        return None, None
    status = run("status", "--porcelain", "--untracked-files=no")
    return sha, (bool(status) if status is not None else None)




def _dist_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def provenance() -> dict:
    """Everything a saved result needs to be tied back to the code and environment that
    produced it. Cheap enough to call per command; all fields are JSON scalars."""
    from . import quant
    sha, dirty = git_info()
    return {"version": package_version(), "git_commit": sha, "git_dirty": dirty,
            "quant_backend": quant.BACKEND,
            "python": platform.python_version(), "implementation": platform.python_implementation(),
            "platform": platform.platform(), "machine": platform.machine(),
            "executable": sys.executable,
            "dependencies": {name: _dist_version(name) for name in KEY_DEPENDENCIES}}
