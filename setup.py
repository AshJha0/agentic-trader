"""Wheel tagging for the optional C++ core.

``pyproject.toml`` carries all the metadata; this file exists only because the compiled
quant core (``agentic_trader/quant/_atcore<EXT_SUFFIX>``) is built by CMake *into the source
tree* rather than by setuptools, so setuptools does not know the package can be binary.
Without this hook every wheel was tagged ``py3-none-any`` while shipping whatever
``_atcore*.pyd``/``.so`` happened to be in the tree -- a CPython-3.12/win_amd64 binary that
pip would install on any OS and Python, where it can never import.

Rule: a wheel ships the compiled core only when it was built for the interpreter doing the
packaging (the file name ends in this interpreter's ``EXT_SUFFIX``), and is then tagged for
that interpreter and platform (``cp312-cp312-win_amd64``). Otherwise the wheel is honestly
pure Python (``py3-none-any``), contains no binary, and ``agentic_trader.quant`` warns once
at import that it is running on the numpy backend.
"""
from __future__ import annotations

import sysconfig
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUANT_DIR = HERE / "agentic_trader" / "quant"


def extension_files(quant_dir: Path = QUANT_DIR) -> list[Path]:
    """Every compiled ``_atcore`` module lying in the package, whatever it was built for."""
    return sorted(p for p in quant_dir.glob("_atcore*") if p.suffix in (".pyd", ".so"))


def native_extension(quant_dir: Path = QUANT_DIR, ext_suffix: str | None = None) -> Path | None:
    """The compiled core built for *this* interpreter and platform, or ``None``."""
    suffix = ext_suffix or sysconfig.get_config_var("EXT_SUFFIX")
    for p in extension_files(quant_dir):
        if p.name == f"_atcore{suffix}":
            return p
    return None


def package_data(quant_dir: Path = QUANT_DIR, ext_suffix: str | None = None) -> dict[str, list[str]]:
    ext = native_extension(quant_dir, ext_suffix)
    return {"agentic_trader.quant": [ext.name] if ext else [],
            "agentic_trader.agentic.knowledge": ["docs/*.md"]}


def build_cmdclass() -> dict:
    from setuptools.command.bdist_wheel import bdist_wheel

    class BinaryAwareWheel(bdist_wheel):
        """Pure-Python tag unless the native core is shipped; then the interpreter's tag."""

        def finalize_options(self):
            super().finalize_options()
            self.root_is_pure = native_extension() is None

        def get_tag(self):
            # With root_is_pure False the base class derives (cpXY, cpXY, <platform>) from the
            # running interpreter, which is exactly what the shipped .pyd/.so was built for.
            return super().get_tag()

    return {"bdist_wheel": BinaryAwareWheel}


if __name__ == "__main__":
    from setuptools import setup

    setup(package_data=package_data(), cmdclass=build_cmdclass())
