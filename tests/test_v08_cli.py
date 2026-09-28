"""v0.8 CLI, packaging and provenance: `--rules v02` survives per-flag overrides (finding
50), `evaluate` accepts the documented cost flags (60), one version source of truth and
provenance in every saved result (56), an honest and CI-exercised dependency lock (55),
a correctly tagged wheel and a loud numpy fallback (82)."""
import importlib
import json
import re
import shutil
import subprocess
import sys
import sysconfig
import zipfile
from importlib import metadata
from pathlib import Path

import pytest

import agentic_trader
from agentic_trader import provenance as prov_mod
from agentic_trader import quant
from agentic_trader.cli import main
from agentic_trader.cli.common import _config
from agentic_trader.cli.parser import build_parser
from agentic_trader.config import DEFAULT_CONFIG, RULES_V02

ROOT = Path(__file__).resolve().parents[1]
BT = ["backtest", "AAPL", "--start", "2024-01-02", "--end", "2024-02-29"]


def cfg_for(*argv):
    return _config(build_parser().parse_args(list(argv)))


# ------------------------------------------------------------ finding 50: rule-set merge
def test_v02_rules_survive_band_flag():
    cfg = cfg_for(*BT, "--rules", "v02", "--band", "0.2")
    assert cfg["risk"]["rebalance_band"] == 0.2
    assert cfg["risk"]["neutral_weight"] == {"equity": 0.0, "fx": 0.0}      # v0.2, not the 1.0 default
    assert cfg["rules"] == {**DEFAULT_CONFIG["rules"], **RULES_V02["rules"]}


def test_v02_rules_survive_allow_short_and_stops_flags():
    cfg = cfg_for(*BT, "--rules", "v02", "--allow-short")
    assert cfg["risk"]["allow_short_equity"] is True
    assert cfg["risk"]["rebalance_band"] == 0.0 and cfg["risk"]["neutral_weight"]["equity"] == 0.0
    cfg = cfg_for(*BT, "--rules", "v02", "--stops", "on", "--impact", "1.0")
    assert cfg["backtest"]["use_stops"] is True and cfg["costs"]["impact_coeff"] == 1.0
    assert cfg["risk"]["rebalance_band"] == 0.0 and cfg["rules"]["tsmom"] is False
    # Every key of the v0.2 rule set is present except the one the flag deliberately changed.
    plain = cfg_for(*BT, "--rules", "v02")
    changed = {k: v for k, v in cfg["backtest"].items() if plain["backtest"].get(k) != v}
    assert changed == {"use_stops": True}


def test_default_rules_flags_unchanged_and_v03_unaffected():
    cfg = cfg_for(*BT, "--band", "0.2", "--allow-short")
    assert cfg["risk"]["rebalance_band"] == 0.2 and cfg["risk"]["allow_short_equity"] is True
    assert cfg["risk"]["neutral_weight"] == DEFAULT_CONFIG["risk"]["neutral_weight"]
    cfg = cfg_for(*BT, "--rules", "v03", "--allow-short")
    assert cfg["rules"]["fx_carry_neutral"] is False and cfg["risk"]["allow_short_equity"] is True


def test_task_approval_flag_merges_into_agentic_block():
    cfg = _config(build_parser().parse_args(["task", "AAPL", "--approval", "deny", "--llm-planner"]))
    assert cfg["agentic"]["approval"] == "deny" and cfg["agentic"]["llm_planner"] is True
    assert set(DEFAULT_CONFIG["agentic"]) <= set(cfg["agentic"])


# ----------------------------------------------------- finding 60: evaluate cost flags
def test_documented_impact_sweep_command_parses():
    # README's re-measurement command, verbatim (data=yahoo is parsed, never fetched here).
    args = build_parser().parse_args(["evaluate", "--data", "yahoo", "--universe", "core", "--periods",
                                      "design,holdout", "--impact", "1.0", "--capital", "1e9"])
    assert args.impact == 1.0 and args.capital == 1e9 and args.execution_algo is None
    args = build_parser().parse_args(["evaluate", "--periods", "q1_2024", "--execution-algo", "ac",
                                      "--ac-kappa", "2.5"])
    assert args.execution_algo == "ac" and args.ac_kappa == 2.5


def test_evaluate_honours_impact_and_capital(tmp_path, capsys):
    out = tmp_path / "eval.json"
    assert main(["evaluate", "AAPL", "--periods", "q1_2024", "--every", "20", "--impact", "1.0",
                 "--capital", "1e9", "--execution-algo", "ac", "--ac-kappa", "2.0", "--out", str(out)]) == 0
    meta = json.loads(out.read_text(encoding="utf-8"))["meta"]
    assert meta["impact_coeff"] == 1.0 and meta["initial_capital"] == 1e9
    assert main(["evaluate", "AAPL", "--periods", "q1_2024", "--every", "20", "--impact", "-1"]) == 2
    assert main(["evaluate", "AAPL", "--periods", "q1_2024", "--every", "20", "--capital", "0"]) == 2
    err = capsys.readouterr().err
    assert "--impact must be >= 0" in err and "--capital must be positive" in err


# ----------------------------------------------- finding 56: version and provenance
def _pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version = "([^"]+)"', text, re.M).group(1)


def test_version_comes_from_pyproject():
    assert agentic_trader.__version__ == _pyproject_version()
    assert agentic_trader.__version__ != "0.0.0+unknown"
    assert prov_mod.package_version(ROOT / "pyproject.toml") == agentic_trader.__version__


def test_version_falls_back_to_distribution_metadata(tmp_path, monkeypatch):
    missing = tmp_path / "pyproject.toml"
    monkeypatch.setattr(prov_mod.metadata, "version", lambda name: {"agentic-trader": "9.9.9"}[name])
    assert prov_mod.package_version(missing) == "9.9.9"
    # a pyproject that belongs to some other project is not ours
    missing.write_text('[project]\nname = "something-else"\nversion = "1.2.3"\n', encoding="utf-8")
    assert prov_mod.package_version(missing) == "9.9.9"

    def not_installed(name):
        raise metadata.PackageNotFoundError(name)
    monkeypatch.setattr(prov_mod.metadata, "version", not_installed)
    assert prov_mod.package_version(tmp_path / "nope.toml") == "0.0.0+unknown"


def test_changelog_top_heading_matches_version():
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    heading = re.search(r"^## v(\d+\.\d+\.\d+)", text, re.M).group(1)
    assert heading == agentic_trader.__version__


def test_provenance_fields_are_json_scalars_and_name_the_backend():
    p = prov_mod.provenance()
    assert p["version"] == agentic_trader.__version__
    assert p["quant_backend"] == quant.BACKEND
    assert p["python"] == sysconfig.get_python_version() or p["python"].startswith(sysconfig.get_python_version())
    assert p["dependencies"]["numpy"] == metadata.version("numpy")
    assert p["dependencies"]["pandas"] == metadata.version("pandas")
    assert p["git_commit"] is None or re.fullmatch(r"[0-9a-f]{40}", p["git_commit"])
    json.dumps(p)                                   # no numpy scalars, paths or other non-JSON types


def test_git_info_handles_a_directory_without_git(tmp_path):
    assert prov_mod.git_info(str(tmp_path)) == (None, None)
    sha, dirty = prov_mod.git_info(str(ROOT))
    if shutil.which("git") and (ROOT / ".git").exists():
        assert sha and len(sha) == 40 and dirty in (True, False)
    assert not hasattr(prov_mod.git_info, "cache_clear")     # computed at every call, never cached


def test_evaluate_and_calibrate_json_record_provenance(tmp_path):
    out = tmp_path / "e.json"
    assert main(["evaluate", "AAPL", "--periods", "q1_2024", "--every", "20", "--out", str(out)]) == 0
    p = json.loads(out.read_text(encoding="utf-8"))["meta"]["provenance"]
    assert p["version"] == agentic_trader.__version__ and p["quant_backend"] == quant.BACKEND
    assert p["dependencies"]["numpy"] and p["python"]
    cal = tmp_path / "c.json"
    assert main(["calibrate", "AAPL", "--date", "2024-03-01", "--n", "1", "--anchors", "none",
                 "--out", str(cal)]) == 0
    p = json.loads(cal.read_text(encoding="utf-8"))["meta"]["provenance"]
    assert p["version"] == agentic_trader.__version__ and p["quant_backend"] == quant.BACKEND


def test_csv_outputs_get_a_provenance_sidecar(tmp_path, capsys):
    pf = tmp_path / "p.csv"
    assert main(["portfolio", "AAPL,EURUSD", "--start", "2024-01-02", "--end", "2024-02-29", "--every", "10",
                 "--out", str(pf)]) == 0
    side = json.loads((tmp_path / "p.provenance.json").read_text(encoding="utf-8"))
    assert side["provenance"]["quant_backend"] == quant.BACKEND and side["symbols"] == ["AAPL", "EURUSD"]
    assert side["weighting"] == "equal" and side["for"] == str(pf)
    bt = tmp_path / "b.csv"
    assert main([*BT, "--every", "10", "--out", str(bt)]) == 0
    side = json.loads((tmp_path / "b.provenance.json").read_text(encoding="utf-8"))
    assert side["provenance"]["version"] == agentic_trader.__version__
    assert side["backtest_config"]["initial_capital"] == DEFAULT_CONFIG["initial_capital"]
    out = capsys.readouterr().out
    assert f"quant={quant.BACKEND} | v{agentic_trader.__version__}" in out     # the header names both


def test_api_reports_the_package_version():
    pytest.importorskip("fastapi")
    from agentic_trader.agentic.api import create_app
    from agentic_trader.config import make_config
    app = create_app(config=make_config(memory_path=None))
    assert app.version == agentic_trader.__version__


# --------------------------------------------------- finding 55: the dependency lock
def _lock_requirements() -> list[tuple[str, str, str | None]]:
    reqs = []
    for raw in (ROOT / "requirements-lock.txt").read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        spec, _, marker = line.partition(";")
        m = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+)", spec.strip())
        assert m, f"not an exact pin: {raw!r}"
        reqs.append((m.group(1).lower().replace("_", "-"), m.group(2), marker.strip() or None))
    return reqs


def _pyproject_requirements(text: str) -> list[str]:
    """Every requirement string under [project] dependencies and optional-dependencies.

    ``tomllib`` is Python 3.11+, and ``tomli`` is not a dependency, so on 3.10 the two
    arrays are read with a regex (the file keeps one double-quoted requirement per entry).
    """
    try:
        import tomllib
    except ImportError:                                   # Python 3.10
        project = re.search(r"^\[project\]\n(.*?)(?=^\[)", text, re.S | re.M).group(1)
        optional = re.search(r"^\[project\.optional-dependencies\]\n(.*?)(?=^\[|\Z)", text, re.S | re.M).group(1)
        deps = re.search(r"^dependencies\s*=\s*\[(.*?)\]", project, re.S | re.M).group(1)
        return re.findall(r'"([^"]+)"', deps) + re.findall(r'"([^"]+)"', optional)
    proj = tomllib.loads(text)["project"]
    return proj["dependencies"] + [r for reqs in proj["optional-dependencies"].values() for r in reqs]


def _pyproject_requirement_names() -> set[str]:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return {re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", req).group(0).lower().replace("_", "-")
            for req in _pyproject_requirements(text)}


def test_lock_pins_every_declared_and_transitive_dependency(monkeypatch):
    import importlib.util

    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    if importlib.util.find_spec("tomllib") is not None:        # 3.11+: the 3.10 fallback reads the same
        with_tomllib = _pyproject_requirements(text)
        monkeypatch.setitem(sys.modules, "tomllib", None)      # import tomllib now raises ImportError
        assert _pyproject_requirements(text) == with_tomllib and len(with_tomllib) > 5
    reqs = _lock_requirements()
    names = {n for n, _, _ in reqs}
    assert len(names) == len(reqs)                                  # no duplicates
    missing = _pyproject_requirement_names() - names - {"cmake"}    # cmake is a system tool, said so in the file
    assert not missing, missing
    # transitive packages under pandas' dates, yfinance's HTTP layer and the API framework
    assert {"python-dateutil", "tzdata", "pydantic", "starlette", "requests", "curl-cffi", "anyio", "httpcore"} <= names
    assert len(reqs) >= 60


def test_lock_states_the_python_it_is_valid_for_and_marks_platform_pins():
    text = (ROOT / "requirements-lock.txt").read_text(encoding="utf-8")
    header = "\n".join(l for l in text.splitlines() if l.startswith("#"))
    assert re.search(r"CPython 3\.12\.\d+", header) and "Python 3.12 only" in header
    assert "3.10" in header and "3.11" in header                    # says why not, not just which
    markers = {n: m for n, _, m in _lock_requirements() if m}
    assert markers.get("pywin32") == 'sys_platform == "win32"'
    numpy = next(v for n, v, _ in _lock_requirements() if n == "numpy")
    if sys.version_info[:2] == (3, 12):
        assert numpy == metadata.version("numpy")                   # the lock describes this environment


def test_ci_installs_from_the_lock_and_runs_the_suite():
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    job = doc["jobs"]["lock"]
    runs = [s.get("run", "") for s in job["steps"]]
    assert any("pip install -r requirements-lock.txt" in r for r in runs)
    assert any("pip install -e . --no-deps" in r for r in runs) and any("pip check" in r for r in runs)
    assert any("pytest" in r for r in runs)
    assert job["env"]["AGENTIC_TRADER_BACKEND"] == "python"
    setup = next(s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/setup-python"))
    assert str(setup["with"]["python-version"]) == "3.12"


# --------------------------------------------------- finding 82: wheel tag and fallback
def _load_setup_module():
    spec = importlib.util.spec_from_file_location("at_setup", ROOT / "setup.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_setup_ships_only_a_core_built_for_this_interpreter(tmp_path):
    setup = _load_setup_module()
    suffix = sysconfig.get_config_var("EXT_SUFFIX")
    (tmp_path / "_atcore.cpython-39-x86_64-linux-gnu.so").write_bytes(b"x")
    (tmp_path / "_atcore.cp311-win_amd64.pyd").write_bytes(b"x")
    assert setup.native_extension(tmp_path) is None
    assert setup.package_data(tmp_path)["agentic_trader.quant"] == []
    native = tmp_path / f"_atcore{suffix}"
    native.write_bytes(b"x")
    assert setup.native_extension(tmp_path) == native
    assert setup.package_data(tmp_path)["agentic_trader.quant"] == [native.name]
    assert len(setup.extension_files(tmp_path)) == 3
    assert setup.package_data(tmp_path)["agentic_trader.agentic.knowledge"] == ["docs/*.md"]


def test_wheel_tag_matches_its_contents(tmp_path):
    pytest.importorskip("setuptools")
    src = tmp_path / "src"
    src.mkdir()
    for name in ("pyproject.toml", "setup.py", "README.md"):
        shutil.copy(ROOT / name, src / name)
    shutil.copytree(ROOT / "agentic_trader", src / "agentic_trader", ignore=shutil.ignore_patterns("__pycache__"))
    quant_dir = src / "agentic_trader" / "quant"
    foreign = "_atcore.cpython-39-x86_64-linux-gnu.so"
    (quant_dir / foreign).write_bytes(b"not for this interpreter")
    native = quant_dir / f"_atcore{sysconfig.get_config_var('EXT_SUFFIX')}"
    r = subprocess.run([sys.executable, "-m", "pip", "wheel", str(src), "--no-deps", "--no-build-isolation",
                        "-q", "-w", str(tmp_path / "dist")], capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    whl = next((tmp_path / "dist").glob("agentic_trader-*.whl"))
    assert whl.name.startswith(f"agentic_trader-{agentic_trader.__version__}-")
    with zipfile.ZipFile(whl) as z:
        names = z.namelist()
        tag = next(l for l in z.read(next(n for n in names if n.endswith("WHEEL"))).decode().splitlines()
                   if l.startswith("Tag:")).split(":", 1)[1].strip()
    shipped = [n for n in names if "/_atcore" in n]
    assert not any(n.endswith(foreign) for n in names)              # a foreign binary is never shipped
    if native.exists():
        assert shipped == [n for n in names if n.endswith(native.name)] and len(shipped) == 1
        impl = f"cp{sys.version_info.major}{sys.version_info.minor}"
        assert tag.startswith(f"{impl}-{impl}-") and not tag.endswith("-any"), tag
    else:
        assert shipped == [] and tag == "py3-none-any"


@pytest.fixture
def quant_without_extension(monkeypatch):
    """Re-import ``agentic_trader.quant`` as on a machine where ``_atcore`` cannot be imported,
    under a given AGENTIC_TRADER_BACKEND (None = unset); afterwards restore the process's
    real backend before the patches are undone, so the reload sees the original state."""
    def reload(backend_env):
        monkeypatch.setitem(sys.modules, "agentic_trader.quant._atcore", None)   # import -> ImportError
        monkeypatch.delattr(quant, "_atcore", raising=False)                     # else `from . import` short-circuits
        if backend_env is None:
            monkeypatch.delenv("AGENTIC_TRADER_BACKEND", raising=False)
        else:
            monkeypatch.setenv("AGENTIC_TRADER_BACKEND", backend_env)
        return importlib.reload(quant)
    before = quant.BACKEND
    yield reload
    monkeypatch.undo()
    importlib.reload(quant)
    assert quant.BACKEND == before


def test_missing_extension_warns_once_naming_the_numpy_backend(quant_without_extension):
    with pytest.warns(RuntimeWarning, match=r"numpy backend \(quant\.BACKEND='python'\)") as rec:
        mod = quant_without_extension(None)
    assert mod.BACKEND == "python" and mod._cpp is None
    assert sum("numpy backend" in str(w.message) for w in rec) == 1
    with pytest.warns(RuntimeWarning, match="_atcore"):
        quant_without_extension("cpp")          # asked for C++, did not get it


def test_explicit_python_backend_is_silent(quant_without_extension):
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        mod = quant_without_extension("python")
    assert mod.BACKEND == "python"
