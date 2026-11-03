import os
import subprocess
import sys

import pytest

from python_doctor import __version__, cli
from python_doctor.context import ScanContext
from python_doctor.renderers import terminal
from python_doctor.scan import run_scan


@pytest.mark.parametrize(
    "argv",
    [
        ["check", "package", "requests"],
        ["check", "import", "requests"],
        ["troubleshoot"],
        ["practice"],
        ["explain", "module-not-found"],
        ["commands"],
        ["scan", "--json"],
        ["scan", "--share"],
    ],
)
def test_planned_commands_exit_2_and_say_so(argv, capsys):
    assert cli.main(argv) == cli.EXIT_USAGE
    assert "Milestone" in capsys.readouterr().err


def test_no_command_prints_help(capsys):
    assert cli.main([]) == cli.EXIT_USAGE
    assert "scan" in capsys.readouterr().out


def test_scan_runs_in_a_project(project, clean_env, capsys):
    clean_env.chdir(project)
    code = cli.main(["scan", "--project", str(project), "--no-probe"])
    out = capsys.readouterr().out
    assert code == cli.EXIT_OK
    assert out.startswith(f"PYTHON DOCTOR {__version__} - READ-ONLY SCAN")
    assert "No changes made." in out


def test_scan_rejects_missing_project_dir(tmp_path, capsys):
    assert cli.main(["scan", "--project", str(tmp_path / "nope")]) == cli.EXIT_USAGE


def test_missing_target_exits_1(project, clean_env, tmp_path):
    clean_env.chdir(project)
    assert cli.main(["scan", "--python", str(tmp_path / "nope" / "python"), "--no-probe"]) == cli.EXIT_FINDINGS


def test_terminal_output_is_ascii(project, clean_env):
    ctx = ScanContext.discover(cwd=project, home=project.parent)
    text = terminal.render(run_scan(ctx), verbose=True)
    text.encode("ascii")  # raises if not
    assert "Evidence:" in text


def test_module_entry_point():
    r = subprocess.run([sys.executable, "-m", "python_doctor", "--version"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and __version__ in r.stdout


def test_env_values_never_reach_evidence(project, clean_env):
    secrets = {
        "PYTHONPATH": "/home/secret-user/zz-pythonpath-value",
        "VIRTUAL_ENV": "/home/secret-user/zz-venv-value",
        "CONDA_PREFIX": "/home/secret-user/zz-conda-value",
        "OPENAI_API_KEY": "sk-zz-test-not-a-real-key",
        "UV_PROJECT_ENVIRONMENT": "/home/secret-user/zz-uv-env",
    }
    for k, v in secrets.items():
        clean_env.setenv(k, v)
    report = run_scan(ScanContext.discover(cwd=project, home=project.parent, probe_enabled=False))
    blob = "\n".join(f"{e.check_id}={e.value}" for e in report.evidence)
    blob += terminal.render(report, verbose=True)
    for v in secrets.values():
        assert v not in blob
    assert report.evidence.value("env.PYTHONPATH.present") is True
