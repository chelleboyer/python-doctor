import subprocess
import sys

import pytest

from python_doctor import proc
from python_doctor.proc import run_bounded


def test_rejects_command_strings():
    with pytest.raises(TypeError):
        run_bounded("echo hi")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        run_bounded([])


def test_missing_executable_is_a_result_not_an_exception(tmp_path):
    r = run_bounded([str(tmp_path / "definitely-not-here")])
    assert r.error == "not_found" and not r.ok


def test_success_captures_output():
    r = run_bounded([sys.executable, "-c", "print('hello')"])
    assert r.ok and r.stdout.strip() == "hello"


def test_nonzero_exit():
    r = run_bounded([sys.executable, "-c", "import sys; sys.exit(3)"])
    assert r.returncode == 3 and not r.ok and not r.timed_out


def test_timeout_kills_child():
    r = run_bounded([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.5)
    assert r.timed_out and r.returncode is None and not r.ok


def test_output_is_capped_and_child_does_not_block():
    r = run_bounded([sys.executable, "-c", "import sys; sys.stdout.write('x' * 500000)"], max_bytes=1000)
    assert r.ok and r.truncated and len(r.stdout) == 1000


def test_stdin_is_closed():
    r = run_bounded([sys.executable, "-c", "import sys; print(repr(sys.stdin.read()))"], timeout=5)
    assert r.ok and r.stdout.strip() == "''"


def test_never_uses_shell(monkeypatch):
    seen = {}
    real = subprocess.Popen

    def spy(*args, **kwargs):
        seen.update(kwargs)
        seen["argv"] = args[0]
        return real(*args, **kwargs)

    monkeypatch.setattr(proc.subprocess, "Popen", spy)
    run_bounded([sys.executable, "-c", "pass"])
    assert seen["shell"] is False
    assert isinstance(seen["argv"], list)
    assert seen["stdin"] is subprocess.DEVNULL
