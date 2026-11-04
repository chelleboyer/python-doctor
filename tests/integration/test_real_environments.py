"""End-to-end checks against real virtual environments and real subprocesses.

These cover the spec's required safety tests:
* scan does not modify files or install dependencies
* normal scans do not execute imports or user project code
* a failed check returns unknown rather than a false diagnosis
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import IS_WINDOWS, ctx_for, make_venv, prepend_path, venv_bin, venv_python

from python_doctor import cli, proc
from python_doctor.collectors.probe import probe_interpreter
from python_doctor.scan import run_scan

pytestmark = pytest.mark.integration


def finding_ids(report):
    return {f.finding_id: f for f in report.findings}


# ---------------------------------------------------------------- probe truth


def test_probe_sees_venv_even_though_site_is_skipped(tmp_path):
    """Regression for the -S trap: without site, sys.prefix is the *base*."""
    venv = make_venv(tmp_path / "v")
    r = probe_interpreter(str(venv_python(venv)))
    assert r.ok, r.detail
    assert os.path.normcase(os.path.realpath(r.data["prefix"])) == os.path.normcase(os.path.realpath(venv))
    assert r.data["prefix"] != r.data["base_prefix"]
    purelib = os.path.normcase(r.data["purelib"])
    assert purelib.startswith(os.path.normcase(os.path.realpath(venv))) or purelib.startswith(os.path.normcase(str(venv)))
    assert "site-packages" in purelib


def _other_pythons() -> list[str]:
    seen, out = set(), []
    for minor in range(10, 15):
        exe = shutil.which(f"python3.{minor}")
        if exe and os.path.realpath(exe) not in seen:
            seen.add(os.path.realpath(exe))
            out.append(exe)
    return out


@pytest.mark.parametrize("python", _other_pythons() or [pytest.param(None, marks=pytest.mark.skip(reason="no python3.X on PATH"))])
def test_probe_across_installed_versions(tmp_path, python):
    venv = make_venv(tmp_path / "v", python=python)
    r = probe_interpreter(str(venv_python(venv)))
    assert r.ok, r.detail
    expected = subprocess.run([python, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"], capture_output=True, text=True, timeout=30).stdout.strip()
    assert r.data["version"].startswith(expected + ".")
    assert os.path.normcase(os.path.realpath(r.data["prefix"])) == os.path.normcase(os.path.realpath(venv))


# ------------------------------------------------------- mismatch, end to end


def test_path_python_from_another_env_is_flagged(project, tmp_path, clean_env):
    make_venv(project / ".venv")
    other = make_venv(tmp_path / "other-env")
    prepend_path(clean_env, venv_bin(other))
    report = run_scan(ctx_for(project))
    f = finding_ids(report)["venv.path_python_differs_from_project"]
    assert f.status == "warn" and f.confidence == "high"
    assert "shell.python.prefix" in f.evidence_ids


def test_path_python_from_project_env_passes(project, clean_env):
    venv = make_venv(project / ".venv")
    prepend_path(clean_env, venv_bin(venv))
    found = finding_ids(run_scan(ctx_for(project)))
    assert found["venv.path_python_matches_project"].status == "pass"
    assert found["venv.structure_ok"].status == "pass"


def test_explicit_target(project, clean_env):
    venv = make_venv(project / ".venv")
    found = finding_ids(run_scan(ctx_for(project, target_python=venv_python(venv))))
    f = found["interpreter.target"]
    assert f.status == "pass" and "inside a virtual environment" in f.summary


# ------------------------------------------------------------- safety tests


def _snapshot(root: Path) -> dict[str, tuple[int, str]]:
    snap = {}
    for p in sorted(root.rglob("*")):
        if p.is_symlink():
            snap[str(p)] = (0, "link:" + os.readlink(p))
        elif p.is_file():
            snap[str(p)] = (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
        elif p.is_dir():
            snap[str(p)] = (0, "dir")
    return snap


def test_scan_does_not_modify_anything(project, tmp_path, clean_env, capsys):
    venv = make_venv(project / ".venv")
    (project / "uv.lock").write_text("version = 1\n")
    prepend_path(clean_env, venv_bin(venv))
    clean_env.chdir(project)
    before = _snapshot(tmp_path)
    assert cli.main(["scan", "--verbose", "--python", str(venv_python(venv))]) == cli.EXIT_OK
    capsys.readouterr()
    assert _snapshot(tmp_path) == before


def test_scan_never_executes_project_code_or_pth_files(project, tmp_path, clean_env, capsys):
    """A student's json.py must not shadow the probe's stdlib import, and
    .pth files in the venv must not run. Both write a marker if executed."""
    marker = tmp_path / "EXECUTED"
    venv = make_venv(project / ".venv")
    payload = f"open({str(marker)!r}, 'a').write('x')\n"
    (project / "json.py").write_text(payload)
    (project / "sysconfig.py").write_text(payload)
    (project / "main.py").write_text(payload)
    site_packages = Path(probe_interpreter(str(venv_python(venv))).data["purelib"])
    site_packages.mkdir(parents=True, exist_ok=True)
    (site_packages / "zz_evil.pth").write_text(f"import os; {payload}")
    prepend_path(clean_env, venv_bin(venv))
    clean_env.chdir(project)

    # Sanity: the trap is armed. Running python normally (with site) fires the .pth.
    subprocess.run([str(venv_python(venv)), "-c", "pass"], check=True, timeout=60)
    assert marker.exists()
    marker.unlink()

    cli.main(["scan", "--verbose", "--python", str(venv_python(venv))])
    capsys.readouterr()
    assert not marker.exists(), "scan executed project code or a .pth file"


def test_every_subprocess_is_a_safe_probe(project, tmp_path, clean_env, monkeypatch):
    venv = make_venv(project / ".venv")
    prepend_path(clean_env, venv_bin(venv))
    calls = []
    real = subprocess.Popen

    def spy(argv, **kw):
        calls.append((argv, kw))
        return real(argv, **kw)

    monkeypatch.setattr(proc.subprocess, "Popen", spy)
    for name in ("run", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, lambda *a, **k: pytest.fail(f"subprocess.{name} used outside proc.run_bounded"))
    monkeypatch.setattr(os, "system", lambda *a: pytest.fail("os.system used"))

    run_scan(ctx_for(project, target_python=venv_python(venv)))
    assert calls, "expected at least one probe"
    for argv, kw in calls:
        assert kw["shell"] is False and isinstance(argv, list)
        assert argv[1:4] == ["-I", "-S", "-c"], argv
        joined = " ".join(argv).lower()
        assert "pip" not in joined and "install" not in joined


def test_no_probe_starts_no_processes(project, clean_env, monkeypatch):
    make_venv(project / ".venv")
    monkeypatch.setattr(proc.subprocess, "Popen", lambda *a, **k: pytest.fail("process started with --no-probe"))
    report = run_scan(ctx_for(project, probe_enabled=False))
    assert report.findings


def test_broken_target_is_unknown_not_a_diagnosis(project, tmp_path, clean_env):
    """A file that exists but isn't a working interpreter -> unknown."""
    fake = tmp_path / ("fake.exe" if IS_WINDOWS else "fake-python")
    fake.write_bytes(b"not an executable")
    if not IS_WINDOWS:
        fake.chmod(0o755)
    found = finding_ids(run_scan(ctx_for(project, target_python=fake)))
    assert found["interpreter.target.unqueried"].status == "unknown"
    assert "interpreter.target" not in found


@pytest.mark.skipif(IS_WINDOWS, reason="POSIX venv symlinks")
def test_real_venv_with_deleted_base_is_reported(project, tmp_path, clean_env):
    """Copy an interpreter, build a venv from the copy, delete the copy."""
    base_dir = tmp_path / "base" / "bin"
    base_dir.mkdir(parents=True)
    real_exe = os.path.realpath(sys.executable)
    fake_base = base_dir / "python3"
    os.symlink(real_exe, fake_base)
    venv = project / ".venv"
    try:
        subprocess.run([str(fake_base), "-m", "venv", "--without-pip", "--symlinks", str(venv)], check=True, capture_output=True, timeout=120)
    except subprocess.CalledProcessError:
        pytest.skip("this interpreter can't run from a symlinked location (e.g. some macOS framework builds)")
    if not (venv / "bin" / "python").is_symlink():
        pytest.skip("venv did not use symlinks on this platform")
    shutil.rmtree(tmp_path / "base")
    if (venv / "bin" / "python").exists():
        # macOS framework builds resolve the base to the real framework binary,
        # so deleting our symlinked "base" doesn't break the venv. The venv is
        # healthy and Doctor correctly says so; this scenario can't be built here.
        pytest.skip("venv does not depend on the deleted base on this platform")
    found = finding_ids(run_scan(ctx_for(project, probe_enabled=False)))
    assert "venv.broken_interpreter_link" in found or "venv.base_missing" in found
