from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from python_doctor.context import ScanContext
from python_doctor.models import Evidence, EvidenceSet

IS_WINDOWS = sys.platform == "win32"


def venv_bin(venv: Path) -> Path:
    return venv / ("Scripts" if IS_WINDOWS else "bin")


def venv_python(venv: Path) -> Path:
    return venv_bin(venv) / ("python.exe" if IS_WINDOWS else "python")


def make_venv(path: Path, python: str | None = None) -> Path:
    """Create a real venv without pip (fast, offline)."""
    subprocess.run(
        [python or sys.executable, "-m", "venv", "--without-pip", str(path)],
        check=True,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=120,
    )
    return path


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """An empty project dir; the walk is bounded by passing home=tmp_path."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0"\nrequires-python = ">=3.10"\ndependencies = ["requests"]\n')
    return root


def ctx_for(root: Path, **kw) -> ScanContext:
    kw.setdefault("home", root.parent)
    return ScanContext.discover(cwd=root, **kw)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in ("VIRTUAL_ENV", "CONDA_PREFIX", "PYTHONPATH", "PYTHONHOME", "UV_PROJECT_ENVIRONMENT"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def evset(values: dict) -> EvidenceSet:
    """Build an EvidenceSet from {check_id: value}."""
    out = EvidenceSet()
    for cid, value in values.items():
        out.add(Evidence(cid, "test", cid, value))
    return out


def prepend_path(monkeypatch: pytest.MonkeyPatch, directory: Path) -> None:
    monkeypatch.setenv("PATH", str(directory) + os.pathsep + os.environ.get("PATH", ""))
