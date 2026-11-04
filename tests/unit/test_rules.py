"""Rules are pure functions of evidence, so they're tested with synthetic evidence."""

from pathlib import Path

import pytest
from conftest import evset

from python_doctor.context import ScanContext
from python_doctor.models import Finding
from python_doctor.rules import environment_rules as R
from python_doctor.rules.engine import run_rules

VENV = str(Path("/work/app/.venv"))


def ctx(platform="linux") -> ScanContext:
    return ScanContext(Path("/work/app"), Path("/work/app"), ("pyproject.toml",), None, True, platform, None)


def ids(findings):
    return {f.finding_id: f for f in findings}


def run(values, platform="linux"):
    ev = evset(values)
    return ids(run_rules(ev, ctx(platform), R.RULES))


BASE = {
    "interp.running.executable": "/opt/tools/python",
    "interp.running.version": "3.12.1",
    "interp.running.in_venv": True,
    "project.root": "/work/app",
    "project.root_markers": "pyproject.toml",
    "project.cwd_is_root": True,
    "project.pyproject.present": True,
    "project.pyproject.parsed": True,
    "project.pyproject.has_project_table": True,
    "project.uv_lock.present": False,
    "env.VIRTUAL_ENV.present": False,
    "env.PYTHONPATH.present": False,
    "env.PYTHONHOME.present": False,
    "env.CONDA_PREFIX.present": False,
    "env.UV_PROJECT_ENVIRONMENT.present": False,
    "target.selected": False,
}
GOOD_VENV = {
    "project.venv.present": True,
    "project.venv.dir_name": ".venv",
    "project.venv.path": VENV,
    "project.venv.python": VENV + "/bin/python",
    "project.venv.python_exists": True,
    "project.venv.cfg.present": True,
    "project.venv.cfg.version": "3.12.1",
}


def with_(*dicts, **extra):
    out = {}
    for d in dicts:
        out.update(d)
    out.update({k.replace("__", "."): v for k, v in extra.items()})
    return out


def test_every_finding_cites_evidence_and_never_crashes():
    found = run(with_(BASE, GOOD_VENV, {"shell.python.path": "/usr/bin/python", "shell.python.probe.status": "ok", "shell.python.prefix": "/usr", "shell.python.version": "3.12.0"}))
    assert not any(k.startswith("engine.") for k in found)
    for f in found.values():
        assert isinstance(f, Finding)


def test_mismatch_from_probed_prefix_is_high_confidence_warn():
    found = run(with_(BASE, GOOD_VENV, {
        "shell.python.path": "/usr/bin/python",
        "shell.python.probe.status": "ok",
        "shell.python.prefix": "/usr",
    }))
    f = found["venv.path_python_differs_from_project"]
    assert f.status == "warn" and f.confidence == "high"
    assert "shell.python.prefix" in f.evidence_ids
    assert any("does not by itself prove" in lim for lim in f.limitations)


def test_mismatch_without_probe_is_medium_and_says_so():
    found = run(with_(BASE, GOOD_VENV, {"shell.python.path": "/usr/bin/python", "shell.python.probe.status": "skipped_disabled"}))
    f = found["venv.path_python_differs_from_project"]
    assert f.confidence == "medium"
    assert any("PATH location only" in lim for lim in f.limitations)


def test_match_by_prefix_passes():
    found = run(with_(BASE, GOOD_VENV, {
        "shell.python.path": VENV + "/bin/python",
        "shell.python.probe.status": "ok",
        "shell.python.prefix": VENV,
    }))
    assert found["venv.path_python_matches_project"].status == "pass"
    assert "venv.path_python_differs_from_project" not in found


def test_dot_venv_presence_alone_never_asserts_mismatch():
    # .venv exists, but nothing on PATH to compare against: no mismatch claim.
    found = run(with_(BASE, GOOD_VENV, {"shell.python.path": None, "shell.python3.path": None}))
    assert not any("differs" in k for k in found)
    assert found["path.no_python"].status == "warn"


def test_broken_venv_does_not_produce_mismatch_claim():
    broken = with_(GOOD_VENV, {"project.venv.python_exists": False, "project.venv.python_dangling_symlink": True, "project.venv.python_expected": VENV + "/bin/python"})
    found = run(with_(BASE, broken, {"shell.python.path": "/usr/bin/python", "shell.python.probe.status": "ok", "shell.python.prefix": "/usr"}))
    assert "venv.path_python_differs_from_project" not in found
    assert found["venv.broken_interpreter_link"].confidence == "high"


def test_uv_project_suggests_uv_run_comparison():
    found = run(with_(BASE, GOOD_VENV, {
        "project.uv_lock.present": True,
        "shell.python.path": "/usr/bin/python", "shell.python.probe.status": "ok", "shell.python.prefix": "/usr",
    }))
    assert "uv run" in found["venv.path_python_differs_from_project"].next_check


def test_non_uv_project_suggests_activation_for_platform():
    vals = with_(BASE, GOOD_VENV, {"shell.python.path": r"C:\Python312\python.exe", "shell.python.probe.status": "ok", "shell.python.prefix": r"C:\Python312"})
    nxt = run(vals, platform="win32")["venv.path_python_differs_from_project"].next_check
    assert "Activate.ps1" in nxt and "source" not in nxt


def test_python3_only_uses_python3_command():
    found = run(with_(BASE, GOOD_VENV, {
        "shell.python.path": None,
        "shell.python3.path": "/usr/bin/python3", "shell.python3.probe.status": "ok", "shell.python3.prefix": "/usr",
    }))
    assert "No `python` command" in found["path.python"].summary
    f = found["venv.path_python_differs_from_project"]
    assert "`python3`" in f.summary
    assert 'python3 -c "import sys; print(sys.prefix)"' in f.next_check


def test_windows_store_alias_is_warned_and_not_treated_as_python():
    found = run(with_(BASE, {"shell.python.path": r"C:\Users\a\AppData\Local\Microsoft\WindowsApps\python.exe", "shell.python.store_alias": True, "shell.python3.path": None}), platform="win32")
    assert found["path.python.store_alias"].status == "warn"
    assert found["path.no_python"].status == "warn"


def test_other_os_layout():
    v = with_(GOOD_VENV, {"project.venv.python_exists": False, "project.venv.python_dangling_symlink": False, "project.venv.windows_layout": True, "project.venv.posix_layout": False, "project.venv.python_expected": VENV + "/bin/python"})
    assert run(with_(BASE, v))["venv.other_os_layout"].status == "warn"


def test_base_python_missing():
    v = with_(GOOD_VENV, {"project.venv.cfg.home": "/opt/py311/bin", "project.venv.cfg.home_exists": False})
    assert run(with_(BASE, v))["venv.base_missing"].status == "warn"


def test_healthy_venv_passes_with_scope_limitation():
    f = run(with_(BASE, GOOD_VENV))["venv.structure_ok"]
    assert f.status == "pass" and any("Structure only" in lim for lim in f.limitations)


def test_no_venv_is_low_confidence_info():
    f = run(with_(BASE, {"project.venv.present": False}))["venv.none_in_project"]
    assert f.status == "info" and f.confidence == "low"


def test_virtual_env_states():
    stale = run(with_(BASE, GOOD_VENV, {"env.VIRTUAL_ENV.present": True, "env.VIRTUAL_ENV.exists": False}))
    assert stale["venv.activated_missing"].status == "warn"
    other = run(with_(BASE, GOOD_VENV, {"env.VIRTUAL_ENV.present": True, "env.VIRTUAL_ENV.exists": True, "env.VIRTUAL_ENV.matches_project_venv": False}))
    assert other["venv.activated_is_other"].status == "warn"
    same = run(with_(BASE, GOOD_VENV, {"env.VIRTUAL_ENV.present": True, "env.VIRTUAL_ENV.exists": True, "env.VIRTUAL_ENV.matches_project_venv": True}))
    assert same["venv.activated_is_project"].status == "pass"


def test_env_flags():
    found = run(with_(BASE, GOOD_VENV, {"env.PYTHONPATH.present": True, "env.PYTHONHOME.present": True, "env.CONDA_PREFIX.present": True}))
    assert found["env.pythonpath_set"].confidence == "low"
    assert found["env.pythonhome_set"].status == "warn"
    assert "env.conda_and_venv" in found


def test_invalid_pyproject_warns():
    found = run(with_(BASE, {"project.pyproject.parsed": False, "project.pyproject.parse_error": "Expected '=' (at line 2, column 5)"}))
    assert found["project.pyproject.invalid"].status == "warn"


def test_unparsed_on_old_python_is_unknown():
    found = run(with_(BASE, {"project.pyproject.parsed": False, "project.pyproject.parse_error": "tomllib unavailable (Python < 3.11); presence only"}))
    assert found["project.pyproject.not_parsed"].status == "unknown"


def test_subdirectory_note():
    f = run(with_(BASE, {"project.cwd_is_root": False}))["project.root"]
    assert any("subdirectory" in lim for lim in f.limitations)


def test_target_missing_fails_and_unqueried_is_unknown():
    t = with_(BASE, {"target.selected": True, "target.path": "/nope/python", "target.exists": False})
    assert run(t)["interpreter.target.missing"].status == "fail"
    t = with_(BASE, {"target.selected": True, "target.path": "/x/python", "target.exists": True, "target.probe.status": "timeout"})
    assert run(t)["interpreter.target.unqueried"].status == "unknown"


def test_collector_error_becomes_unknown():
    found = run(with_(BASE, {"collector.project.error": "OSError: boom"}))
    assert found["engine.collector.project.error"].status == "unknown"


def test_engine_turns_rule_crash_into_unknown():
    def bad_rule(ev, c):
        raise RuntimeError("bug")

    out = run_rules(evset({}), ctx(), [bad_rule])
    assert [f.status for f in out] == ["unknown"]
    assert out[0].finding_id == "engine.rule_error.bad_rule"


@pytest.mark.parametrize(
    "produced",
    [
        [Finding("a", "info", "s", evidence_ids=("missing.id",))],
        [Finding("a", "info", "s"), Finding("a", "info", "s")],
    ],
)
def test_engine_rejects_contract_violations(produced):
    def rule(ev, c):
        return produced

    out = run_rules(evset({}), ctx(), [rule])
    assert [f.status for f in out] == ["unknown"]
