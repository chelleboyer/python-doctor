"""Interpreter evidence: the Doctor's own process, an explicit target, and PATH.

Caveats recorded as evidence/limitations rather than hidden:

* The *running* interpreter is the one running Python Doctor. If the Doctor was
  installed with pipx/uv tool, that is not the student's project interpreter.
* PATH lookup (``shutil.which``) cannot see shell aliases, functions, or
  ``pyenv``-style shims' final target. It answers "what would PATH pick".
* Environment variables are recorded as *presence flags only*. We never store
  their values. For ``VIRTUAL_ENV`` we compute comparisons (does it exist, does
  it match the running prefix / project venv) and keep only the booleans.
"""

from __future__ import annotations

import os
import shutil
import sys

from python_doctor.collectors.probe import ProbeResult, probe_interpreter
from python_doctor.collectors.project import find_project_venv
from python_doctor.context import ScanContext
from python_doctor.models import Evidence
from python_doctor.paths import looks_like_windows_store_alias, same_dir

#: Presence-only flags. Values are never read into evidence.
PRESENCE_ENV_VARS = (
    "VIRTUAL_ENV",
    "CONDA_PREFIX",
    "PYTHONPATH",
    "PYTHONHOME",
    "UV_PROJECT_ENVIRONMENT",
)


def collect(ctx: ScanContext) -> list[Evidence]:
    ev: list[Evidence] = []
    ev += collect_running()
    ev += collect_env_flags(ctx)
    ev += collect_target(ctx)
    ev += collect_path_pythons(ctx)
    return ev


def collect_running() -> list[Evidence]:
    src = "sys (Python Doctor process)"
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    ver = "%d.%d.%d" % sys.version_info[:3]
    return [
        Evidence("interp.running.executable", "sys.executable", "Interpreter running Python Doctor", sys.executable or None, "path"),
        Evidence("interp.running.version", "sys.version_info", "Version of the Doctor's interpreter", ver),
        Evidence("interp.running.implementation", "sys.implementation", "Implementation", sys.implementation.name),
        Evidence("interp.running.prefix", src, "sys.prefix of the Doctor's interpreter", sys.prefix, "path"),
        Evidence("interp.running.base_prefix", src, "sys.base_prefix of the Doctor's interpreter", sys.base_prefix, "path"),
        Evidence("interp.running.in_venv", src, "Doctor's interpreter is inside a virtual environment (prefix != base_prefix)", in_venv),
    ]


def collect_env_flags(ctx: ScanContext) -> list[Evidence]:
    ev: list[Evidence] = []
    for name in PRESENCE_ENV_VARS:
        ev.append(
            Evidence(
                f"env.{name}.present",
                "os.environ (presence only)",
                f"{name} is set (value not collected)",
                bool(os.environ.get(name)),
            )
        )
    venv_value = os.environ.get("VIRTUAL_ENV")
    if venv_value:
        # Compare in memory; store only the booleans.
        ev.append(Evidence("env.VIRTUAL_ENV.exists", "os.environ + filesystem", "The directory named by VIRTUAL_ENV exists", os.path.isdir(venv_value)))
        ev.append(Evidence("env.VIRTUAL_ENV.matches_running_prefix", "os.environ + sys.prefix", "VIRTUAL_ENV equals the Doctor's sys.prefix", same_dir(venv_value, sys.prefix)))
        if ctx.project_root is not None:
            pv = find_project_venv(ctx.project_root)
            ev.append(
                Evidence(
                    "env.VIRTUAL_ENV.matches_project_venv",
                    "os.environ + project",
                    "VIRTUAL_ENV equals the project's virtual environment directory",
                    same_dir(venv_value, pv) if pv else False,
                )
            )
    return ev


def _probe_evidence(prefix: str, label: str, result: ProbeResult) -> list[Evidence]:
    src = f"probe ({label}, python -I -S)"
    ev = [Evidence(f"{prefix}.probe.status", src, f"Probe of {label}", result.status)]
    if result.detail:
        ev.append(Evidence(f"{prefix}.probe.detail", src, f"Probe detail for {label}", result.detail, "path"))
    if result.ok and result.data:
        d = result.data
        ev += [
            Evidence(f"{prefix}.executable", src, f"sys.executable reported by {label}", d["executable"], "path"),
            Evidence(f"{prefix}.version", src, f"Version reported by {label}", d["version"]),
            Evidence(f"{prefix}.prefix", src, f"sys.prefix reported by {label}", d["prefix"], "path"),
            Evidence(f"{prefix}.base_prefix", src, f"sys.base_prefix reported by {label}", d["base_prefix"], "path"),
            Evidence(f"{prefix}.in_venv", src, f"{label} is inside a virtual environment", d["prefix"] != d["base_prefix"]),
        ]
        if d.get("purelib"):
            ev.append(Evidence(f"{prefix}.purelib", src, f"site-packages directory for {label}", d["purelib"], "path"))
    return ev


def collect_target(ctx: ScanContext) -> list[Evidence]:
    if ctx.target_python is None:
        return [Evidence("target.selected", "cli", "An explicit target interpreter was selected with --python", False)]
    raw = os.path.abspath(str(ctx.target_python))
    ev = [
        Evidence("target.selected", "cli", "An explicit target interpreter was selected with --python", True),
        Evidence("target.path", "cli --python", "Target interpreter path as given", raw, "path"),
        Evidence("target.exists", "filesystem", "Target interpreter path exists and is a file", os.path.isfile(raw)),
    ]
    if not os.path.isfile(raw):
        return ev
    if looks_like_windows_store_alias(raw):
        ev.append(Evidence("target.probe.status", "policy", "Probe of target", "skipped_store_alias"))
        return ev
    if not ctx.probe_enabled:
        ev.append(Evidence("target.probe.status", "policy", "Probe of target", "skipped_disabled"))
        return ev
    return ev + _probe_evidence("target", "target interpreter", probe_interpreter(raw))


def path_command_names(platform: str) -> list[str]:
    names = ["python", "python3"]
    if platform == "win32":
        names.append("py")
    return names


def collect_path_pythons(ctx: ScanContext) -> list[Evidence]:
    ev: list[Evidence] = []
    for name in path_command_names(ctx.platform):
        found = shutil.which(name)
        base = f"shell.{name}"
        ev.append(Evidence(f"{base}.path", f"shutil.which({name!r})", f"`{name}` resolves on PATH to", found, "path"))
        if not found:
            continue
        alias = looks_like_windows_store_alias(found)
        ev.append(Evidence(f"{base}.store_alias", "path inspection", f"`{name}` is the Windows Store app alias", alias))
        if alias:
            ev.append(Evidence(f"{base}.probe.status", "policy", f"Probe of `{name}`", "skipped_store_alias"))
            continue
        if not ctx.probe_enabled:
            ev.append(Evidence(f"{base}.probe.status", "policy", f"Probe of `{name}`", "skipped_disabled"))
            continue
        ev += _probe_evidence(base, f"`{name}` on PATH", probe_interpreter(found))
    return ev


__all__ = ["collect", "PRESENCE_ENV_VARS", "path_command_names"]
