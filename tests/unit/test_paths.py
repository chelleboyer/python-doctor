import os
import sys
from pathlib import Path

import pytest

from python_doctor.paths import (
    OutsideRootError,
    is_within,
    looks_like_windows_store_alias,
    safe_read_text,
    same_dir,
    venv_python_candidates,
)


def test_venv_layout_per_platform():
    v = Path("proj") / ".venv"
    assert venv_python_candidates(v, "win32") == [v / "Scripts" / "python.exe"]
    assert venv_python_candidates(v, "linux") == [v / "bin" / "python", v / "bin" / "python3"]
    assert venv_python_candidates(v, "darwin")[0] == v / "bin" / "python"


@pytest.mark.parametrize(
    "path,expected",
    [
        (r"C:\Users\ana\AppData\Local\Microsoft\WindowsApps\python.exe", True),
        (r"C:\Users\ana\AppData\Local\Programs\Python\Python312\python.exe", False),
        ("/usr/bin/python3", False),
        (None, False),
    ],
)
def test_store_alias_detection(path, expected):
    assert looks_like_windows_store_alias(path) is expected


def test_is_within_is_lexical_for_the_file(tmp_path):
    venv = tmp_path / ".venv"
    (venv / "bin").mkdir(parents=True)
    assert is_within(venv / "bin" / "python", venv)
    assert not is_within(tmp_path / "other" / "python", venv)
    # Prefix-string trap: ".venv2" is not inside ".venv".
    assert not is_within(tmp_path / ".venv2" / "bin" / "python", venv)


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_is_within_does_not_resolve_the_executable_symlink(tmp_path):
    venv = tmp_path / ".venv"
    (venv / "bin").mkdir(parents=True)
    link = venv / "bin" / "python"
    link.symlink_to(sys.executable)
    assert is_within(link, venv)  # resolving would point outside the venv


def test_same_dir(tmp_path):
    assert same_dir(tmp_path, str(tmp_path) + os.sep)
    assert not same_dir(tmp_path, tmp_path / "x")
    assert not same_dir(None, tmp_path)


def test_safe_read_text_limits(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello")
    assert safe_read_text(f, tmp_path) == "hello"
    f.write_text("x" * 100)
    with pytest.raises(ValueError):
        safe_read_text(f, tmp_path, max_bytes=10)
    with pytest.raises(FileNotFoundError):
        safe_read_text(tmp_path / "missing", tmp_path)


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_safe_read_text_refuses_symlink_out_of_root(tmp_path):
    outside = tmp_path / "secret.txt"
    outside.write_text("token=abc")
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").symlink_to(outside)
    with pytest.raises(OutsideRootError):
        safe_read_text(root / "pyproject.toml", root)
