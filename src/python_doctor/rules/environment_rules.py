"""Milestone A rules: interpreter, PATH, virtual environment, project metadata.

Writing rules here:

* Cite every piece of evidence a finding relies on in ``evidence_ids``.
* ``status`` = what was observed. ``confidence`` = how well the evidence
  supports the *hypothesis*, and only when there is one.
* Never conclude "mismatch" from the mere presence of ``.venv``. Compare
  observed paths/prefixes, and say which basis was used.
* Put what the check cannot see in ``limitations``.
"""

from __future__ import annotations

from python_doctor.context import ScanContext
from python_doctor.models import EvidenceSet, Finding
from python_doctor.paths import is_within, same_dir
from python_doctor.shellfmt import PRINT_PREFIX, activation_commands, invoke, with_command

RUNNING_CAVEAT = (
    "This is the interpreter running Python Doctor. It is not necessarily the "
    "one your project, terminal command, or editor uses."
)
NOT_CAUSE_PROOF = "This shows a path difference; it does not by itself prove that this causes your error."
PREFIX_AND_BASE_ARGS = '-c "import sys; print(sys.prefix, sys.base_prefix)"'
ALIAS_CAVEAT = "Shell aliases, functions, and activation in a different terminal window are not visible to this check."


def _yes(v: object) -> bool:
    return v is True


def _path_command(ev: EvidenceSet) -> str | None:
    """The command a beginner would type: `python`, else `python3`."""
    for name in ("python", "python3"):
        if ev.value(f"shell.{name}.path") and not _yes(ev.value(f"shell.{name}.store_alias")):
            return name
    return None


# --------------------------------------------------------------------------- #
# Interpreters
# --------------------------------------------------------------------------- #

def rule_running_interpreter(ev: EvidenceSet, ctx: ScanContext) -> list[Finding]:
    exe = ev.value("interp.running.executable") or "(unknown executable)"
    ver = ev.value("interp.running.version")
    venv = " inside a virtual environment" if _yes(ev.value("interp.running.in_venv")) else ""
    return [
        Finding(
            finding_id="interpreter.running",
            status="info",
            summary=f"Python Doctor is running under {exe} (Python {ver}){venv}",
            evidence_ids=ev.ids(
                "interp.running.executable", "interp.running.version",
                "interp.running.prefix", "interp.running.base_prefix", "interp.running.in_venv",
            ),
            limitations=(RUNNING_CAVEAT,),
        )
    ]


def rule_target_interpreter(ev: EvidenceSet, ctx: ScanContext) -> list[Finding]:
    if not _yes(ev.value("target.selected")):
        return []
    path = str(ev.value("target.path"))
    if not _yes(ev.value("target.exists")):
        return [
            Finding(
                finding_id="interpreter.target.missing",
                status="fail",
                summary=f"The interpreter given with --python does not exist: {path}",
                evidence_ids=ev.ids("target.path", "target.exists"),
                next_check="Check the path for typos. On Windows a venv interpreter is at .venv\\Scripts\\python.exe; elsewhere .venv/bin/python.",
            )
        ]
    status = ev.value("target.probe.status")
    if status == "ok":
        venv = "inside a virtual environment" if _yes(ev.value("target.in_venv")) else "not a virtual environment"
        return [
            Finding(
                finding_id="interpreter.target",
                status="pass",
                summary=f"Target interpreter responded: Python {ev.value('target.version')}, {venv}",
                evidence_ids=ev.ids("target.path", "target.probe.status", "target.executable", "target.version", "target.prefix", "target.base_prefix", "target.in_venv"),
            )
        ]
    reason = {
        "skipped_disabled": "probing is disabled (--no-probe)",
        "skipped_store_alias": "it is the Windows Store app alias, which can open the Store instead of running Python",
    }.get(str(status), f"the probe failed ({status})")
    return [
        Finding(
            finding_id="interpreter.target.unqueried",
            status="unknown",
            summary=f"Could not query the target interpreter: {reason}",
            evidence_ids=ev.ids("target.path", "target.probe.status", "target.probe.detail"),
            next_check=f"Run it directly and read the output: {invoke(path, '--version', ctx.platform)}",
        )
    ]


def rule_path_python(ev: EvidenceSet, ctx: ScanContext) -> list[Finding]:
    out: list[Finding] = []
    for name in ("python", "python3", "py"):
        if _yes(ev.value(f"shell.{name}.store_alias")):
            out.append(
                Finding(
                    finding_id=f"path.{name}.store_alias",
                    status="warn",
                    summary=f"`{name}` on PATH is the Windows Store app alias, not an installed Python",
                    evidence_ids=ev.ids(f"shell.{name}.path", f"shell.{name}.store_alias"),
                    hypothesis=f"Typing `{name}` may open the Microsoft Store or print a hint instead of running Python.",
                    confidence="high",
                    next_check="Run `py -0p` to list installed interpreters. The alias can be turned off under Settings > Apps > Advanced app settings > App execution aliases.",
                    limitations=("Python Doctor never runs the alias, so it cannot tell whether a Store Python is actually installed behind it.",),
                )
            )

    cmd = _path_command(ev)
    if cmd is None:
        out.append(
            Finding(
                finding_id="path.no_python",
                status="warn",
                summary="Neither `python` nor `python3` resolves to an interpreter on PATH",
                evidence_ids=ev.ids("shell.python.path", "shell.python3.path"),
                hypothesis="Python is not installed for this shell, or its directory is not on PATH.",
                confidence="medium",
                next_check="Open a new terminal (PATH changes need one) and try `python --version`. On Windows, also try `py --version`.",
                limitations=("Python Doctor itself is running, so some interpreter exists; it was started by a path or launcher that isn't on PATH.",),
            )
        )
        return out

    base = f"shell.{cmd}"
    where = ev.value(f"{base}.path")
    probe = ev.value(f"{base}.probe.status")
    detail = f" (Python {ev.value(f'{base}.version')})" if probe == "ok" else ""
    lim = [ALIAS_CAVEAT]
    if probe not in ("ok", None):
        lim.append(f"The interpreter was not queried ({probe}); only its PATH location is known.")
    if cmd == "python3":
        out.append(
            Finding(
                finding_id="path.python",
                status="info",
                summary=f"No `python` command on PATH; `python3` resolves to {where}{detail}",
                evidence_ids=ev.ids("shell.python.path", f"{base}.path", f"{base}.probe.status", f"{base}.version"),
                hypothesis="Instructions that say `python ...` will fail with 'command not found' here unless a virtual environment is activated (activation provides `python`).",
                confidence="medium",
                next_check="Use `python3`, or activate the project environment, or use `uv run python`.",
                limitations=tuple(lim),
            )
        )
    else:
        out.append(
            Finding(
                finding_id="path.python",
                status="info",
                summary=f"`python` on PATH resolves to {where}{detail}",
                evidence_ids=ev.ids(f"{base}.path", f"{base}.probe.status", f"{base}.version", f"{base}.prefix"),
                limitations=tuple(lim),
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Virtual environments
# --------------------------------------------------------------------------- #

def rule_path_python_vs_project_venv(ev: EvidenceSet, ctx: ScanContext) -> list[Finding]:
    """The central mismatch check: does the beginner's `python` use the project venv?"""
    if not (_yes(ev.value("project.venv.present")) and _yes(ev.value("project.venv.python_exists"))):
        return []
    cmd = _path_command(ev)
    if cmd is None:
        return []
    venv_dir = str(ev.value("project.venv.path"))
    venv_name = str(ev.value("project.venv.dir_name"))
    base = f"shell.{cmd}"
    shell_path = str(ev.value(f"{base}.path"))
    prefix = ev.value(f"{base}.prefix")

    if isinstance(prefix, str):
        inside = same_dir(prefix, venv_dir)
        basis_ids = ev.ids(f"{base}.path", f"{base}.prefix", "project.venv.path")
        uses = prefix
        basis_note: tuple[str, ...] = ()
    else:
        inside = is_within(shell_path, venv_dir)
        basis_ids = ev.ids(f"{base}.path", f"{base}.probe.status", "project.venv.path")
        uses = shell_path
        basis_note = ("Based on PATH location only; the interpreter was not queried.",)

    if inside:
        return [
            Finding(
                finding_id="venv.path_python_matches_project",
                status="pass",
                summary=f"`{cmd}` on PATH uses this project's {venv_name}",
                evidence_ids=basis_ids,
                limitations=(ALIAS_CAVEAT, *basis_note),
            )
        ]

    compare = f'`{with_command(PRINT_PREFIX, cmd)}`'
    uses_uv = _yes(ev.value("project.uv_lock.present")) or _yes(ev.value("project.pyproject.has_tool_uv"))
    if uses_uv:
        nxt = f"Compare {compare} with `uv run {PRINT_PREFIX}`. The second shows what `uv run` uses."
    else:
        acts = "; ".join(f"{shell}: `{c}`" for shell, c in activation_commands(venv_name, ctx.platform))
        nxt = f"Run {compare} before and after activating {venv_name} ({acts})."
    return [
        Finding(
            finding_id="venv.path_python_differs_from_project",
            status="warn",
            summary=f"`{cmd}` on PATH is not this project's {venv_name}",
            evidence_ids=basis_ids,
            hypothesis=(
                f"Running `{cmd} your_script.py` in this shell uses {uses}, so packages installed "
                f"into {venv_name} won't be visible to it."
            ),
            confidence="high" if not basis_note else "medium",
            next_check=nxt,
            limitations=(NOT_CAUSE_PROOF, ALIAS_CAVEAT, *basis_note),
        )
    ]


def rule_virtual_env_var(ev: EvidenceSet, ctx: ScanContext) -> list[Finding]:
    present = _yes(ev.value("env.VIRTUAL_ENV.present"))
    venv_present = _yes(ev.value("project.venv.present"))
    venv_name = ev.value("project.venv.dir_name") or ".venv"
    if not present:
        if not venv_present:
            return []
        return [
            Finding(
                finding_id="venv.not_activated",
                status="info",
                summary="No virtual environment is activated in this shell (VIRTUAL_ENV is not set)",
                evidence_ids=ev.ids("env.VIRTUAL_ENV.present", "project.venv.present"),
                limitations=(
                    "Activation is optional: `uv run` and an explicit path like .venv/bin/python select the environment without it.",
                    "Editors (VS Code, Jupyter) choose their interpreter independently of this shell.",
                ),
            )
        ]
    if ev.has("env.VIRTUAL_ENV.exists") and not _yes(ev.value("env.VIRTUAL_ENV.exists")):
        return [
            Finding(
                finding_id="venv.activated_missing",
                status="warn",
                summary="VIRTUAL_ENV names a directory that no longer exists",
                evidence_ids=ev.ids("env.VIRTUAL_ENV.present", "env.VIRTUAL_ENV.exists"),
                hypothesis="This shell is still 'activated' for a virtual environment that was deleted or moved.",
                confidence="high",
                next_check="Run `deactivate` (or open a new terminal), then check `python --version` again.",
            )
        ]
    if venv_present and ev.has("env.VIRTUAL_ENV.matches_project_venv"):
        if _yes(ev.value("env.VIRTUAL_ENV.matches_project_venv")):
            return [
                Finding(
                    finding_id="venv.activated_is_project",
                    status="pass",
                    summary=f"The activated virtual environment is this project's {venv_name}",
                    evidence_ids=ev.ids("env.VIRTUAL_ENV.present", "env.VIRTUAL_ENV.matches_project_venv"),
                )
            ]
        return [
            Finding(
                finding_id="venv.activated_is_other",
                status="warn",
                summary=f"A virtual environment is activated, but it is not this project's {venv_name}",
                evidence_ids=ev.ids("env.VIRTUAL_ENV.present", "env.VIRTUAL_ENV.matches_project_venv", "project.venv.path"),
                hypothesis="This shell was activated for a different project; `python` here probably points at that project's environment.",
                confidence="high",
                next_check="Run `deactivate`, then activate this project's environment, or use `uv run`.",
                limitations=("VIRTUAL_ENV is set by activation scripts. It records what was activated, not necessarily what `python` resolves to now.",),
            )
        ]
    return [
        Finding(
            finding_id="venv.activated",
            status="info",
            summary="A virtual environment is activated in this shell (VIRTUAL_ENV is set; value not collected)",
            evidence_ids=ev.ids("env.VIRTUAL_ENV.present", "env.VIRTUAL_ENV.matches_running_prefix"),
        )
    ]


def rule_venv_health(ev: EvidenceSet, ctx: ScanContext) -> list[Finding]:
    if not _yes(ev.value("project.venv.present")):
        return []
    name = str(ev.value("project.venv.dir_name"))
    home = ev.value("project.venv.cfg.home")
    if not _yes(ev.value("project.venv.python_exists")):
        expected = ev.value("project.venv.python_expected")
        if _yes(ev.value("project.venv.python_dangling_symlink")):
            return [
                Finding(
                    finding_id="venv.broken_interpreter_link",
                    status="warn",
                    summary=f"{name}'s interpreter is a broken link: {expected}",
                    evidence_ids=ev.ids("project.venv.python_expected", "project.venv.python_dangling_symlink", "project.venv.cfg.home", "project.venv.cfg.home_exists"),
                    hypothesis=f"The Python that {name} was created from has been uninstalled, upgraded, or moved; {name} cannot run until it is recreated.",
                    confidence="high",
                    next_check=f"Check whether the base directory {home} still exists. Recreating {name} replaces its installed packages, so check how they were installed first (uv.lock / requirements.txt).",
                )
            ]
        other_os = (ctx.platform != "win32" and _yes(ev.value("project.venv.windows_layout"))) or (
            ctx.platform == "win32" and _yes(ev.value("project.venv.posix_layout"))
        )
        if other_os:
            return [
                Finding(
                    finding_id="venv.other_os_layout",
                    status="warn",
                    summary=f"{name} has the directory layout of a different operating system",
                    evidence_ids=ev.ids("project.venv.posix_layout", "project.venv.windows_layout", "project.venv.python_exists"),
                    hypothesis=f"{name} was created on another OS (or copied from another machine, e.g. via a synced folder or zip) and cannot run here.",
                    confidence="medium",
                    next_check=f"Ask where {name} came from. Virtual environments are not portable between machines; they are recreated from the dependency files.",
                )
            ]
        return [
            Finding(
                finding_id="venv.no_interpreter",
                status="warn",
                summary=f"{name} exists but has no interpreter at the expected location ({expected})",
                evidence_ids=ev.ids("project.venv.python_expected", "project.venv.python_exists", "project.venv.cfg.present"),
                hypothesis=f"{name} was only partially created, or it isn't a virtual environment at all.",
                confidence="low",
                next_check=f"List the contents of {name} and look for pyvenv.cfg and a bin/ or Scripts/ directory.",
            )
        ]
    if not _yes(ev.value("project.venv.cfg.present")):
        return [
            Finding(
                finding_id="venv.no_pyvenv_cfg",
                status="warn",
                summary=f"{name} has an interpreter but no pyvenv.cfg",
                evidence_ids=ev.ids("project.venv.python", "project.venv.cfg.present"),
                hypothesis=f"{name} may not be a standard virtual environment (for example a copied interpreter or a conda environment).",
                confidence="low",
                next_check=f"Run {invoke(str(ev.value('project.venv.python')), PREFIX_AND_BASE_ARGS, ctx.platform)}. Matching values mean it is not a venv.",
            )
        ]
    if ev.has("project.venv.cfg.home_exists") and not _yes(ev.value("project.venv.cfg.home_exists")):
        return [
            Finding(
                finding_id="venv.base_missing",
                status="warn",
                summary=f"The base Python directory recorded in {name}/pyvenv.cfg no longer exists: {home}",
                evidence_ids=ev.ids("project.venv.cfg.home", "project.venv.cfg.home_exists"),
                hypothesis=f"The Python that {name} was built from was removed or upgraded; {name} may fail to start.",
                confidence="medium",
                next_check=f"Run {invoke(str(ev.value('project.venv.python')), '--version', ctx.platform)} and read any error.",
            )
        ]
    ver = ev.value("project.venv.cfg.version")
    made_by = ", created by uv" if _yes(ev.value("project.venv.cfg.created_by_uv")) else ""
    return [
        Finding(
            finding_id="venv.structure_ok",
            status="pass",
            summary=f"{name} looks structurally valid (Python {ver or 'unknown'}{made_by})",
            evidence_ids=ev.ids("project.venv.path", "project.venv.python", "project.venv.cfg.present", "project.venv.cfg.version", "project.venv.cfg.created_by_uv"),
            limitations=("Structure only. This does not show whether the installed packages match the project's declared dependencies.",),
        )
    ]


def rule_no_project_venv(ev: EvidenceSet, ctx: ScanContext) -> list[Finding]:
    if ev.value("project.root") is None or _yes(ev.value("project.venv.present")):
        return []
    lim = ["UV_PROJECT_ENVIRONMENT, conda, Poetry and pyenv-virtualenv can keep environments outside the project folder."]
    if _yes(ev.value("env.UV_PROJECT_ENVIRONMENT.present")):
        lim.insert(0, "UV_PROJECT_ENVIRONMENT is set, so uv may be using an environment elsewhere.")
    return [
        Finding(
            finding_id="venv.none_in_project",
            status="info",
            summary="No .venv or venv directory at the project root",
            evidence_ids=ev.ids("project.root", "project.venv.present", "env.UV_PROJECT_ENVIRONMENT.present"),
            hypothesis="Packages for this project are installed in a global/user interpreter or an environment stored somewhere else, or not installed yet.",
            confidence="low",
            next_check=f"Ask how the student installed packages, then run `{PRINT_PREFIX}` the same way they run their code.",
            limitations=tuple(lim),
        )
    ]


# --------------------------------------------------------------------------- #
# Project
# --------------------------------------------------------------------------- #

def rule_project_root(ev: EvidenceSet, ctx: ScanContext) -> list[Finding]:
    root = ev.value("project.root")
    if root is None:
        return [
            Finding(
                finding_id="project.no_root",
                status="info",
                summary="No project root found (searched upward for pyproject.toml, uv.lock, setup.py, setup.cfg, requirements.txt, .git)",
                evidence_ids=ev.ids("project.cwd", "project.root"),
                next_check="Change into the project folder (`cd path/to/project`) and run the scan again, or pass --project.",
            )
        ]
    markers = ev.value("project.root_markers")
    lim: tuple[str, ...] = ()
    if ev.value("project.cwd_is_root") is False:
        lim = ("You are in a subdirectory of the project. Relative file paths in scripts are resolved from where you run them, not from the project root.",)
    rp = ev.value("project.requires_python")
    extra = f"; requires-python {rp}" if rp else ""
    return [
        Finding(
            finding_id="project.root",
            status="info",
            summary=f"Project root: {root} (found {markers}{extra})",
            evidence_ids=ev.ids("project.root", "project.root_markers", "project.cwd_is_root", "project.requires_python"),
            limitations=lim,
        )
    ]


def rule_pyproject(ev: EvidenceSet, ctx: ScanContext) -> list[Finding]:
    out: list[Finding] = []
    if ev.has("project.pyproject.read_error"):
        out.append(
            Finding(
                finding_id="project.pyproject.unreadable",
                status="unknown",
                summary=f"pyproject.toml exists but was not read ({ev.value('project.pyproject.read_error')})",
                evidence_ids=ev.ids("project.pyproject.present", "project.pyproject.read_error"),
                limitations=("Files that are symlinks pointing outside the project, larger than 1 MB, or unreadable are skipped on purpose.",),
            )
        )
    elif ev.value("project.pyproject.parsed") is False:
        err = str(ev.value("project.pyproject.parse_error"))
        if err.startswith("tomllib unavailable"):
            out.append(
                Finding(
                    finding_id="project.pyproject.not_parsed",
                    status="unknown",
                    summary="pyproject.toml exists; its contents were not parsed on this Python version",
                    evidence_ids=ev.ids("project.pyproject.present", "project.pyproject.parse_error"),
                    limitations=("Parsing needs Python 3.11+ (tomllib). Run Python Doctor with a newer interpreter to see declared metadata.",),
                )
            )
        else:
            out.append(
                Finding(
                    finding_id="project.pyproject.invalid",
                    status="warn",
                    summary=f"pyproject.toml is not valid TOML: {err}",
                    evidence_ids=ev.ids("project.pyproject.present", "project.pyproject.parsed", "project.pyproject.parse_error"),
                    hypothesis="uv, pip, and other tools will refuse to use this project until the syntax error is fixed.",
                    confidence="high",
                    next_check="Open pyproject.toml at the reported line and column. Look for missing quotes, '=' or closing brackets.",
                )
            )
    elif _yes(ev.value("project.pyproject.parsed")) and not _yes(ev.value("project.pyproject.has_project_table")):
        out.append(
            Finding(
                finding_id="project.pyproject.no_project_table",
                status="info",
                summary="pyproject.toml has no [project] table",
                evidence_ids=ev.ids("project.pyproject.parsed", "project.pyproject.has_project_table"),
                limitations=("It may only configure tools (for example black or pytest), or use an older Poetry layout ([tool.poetry]). uv expects a [project] table.",),
            )
        )
    if _yes(ev.value("project.uv_lock.present")) and not _yes(ev.value("project.pyproject.present")):
        out.append(
            Finding(
                finding_id="project.uv_lock_without_pyproject",
                status="warn",
                summary="uv.lock exists but pyproject.toml does not",
                evidence_ids=ev.ids("project.uv_lock.present", "project.pyproject.present"),
                hypothesis="pyproject.toml was deleted or never committed; uv cannot use the lock file without it.",
                confidence="medium",
                next_check="Check version control history for pyproject.toml.",
            )
        )
    return out


def rule_env_flags(ev: EvidenceSet, ctx: ScanContext) -> list[Finding]:
    out: list[Finding] = []
    if _yes(ev.value("env.PYTHONPATH.present")):
        out.append(
            Finding(
                finding_id="env.pythonpath_set",
                status="warn",
                summary="PYTHONPATH is set (value not collected)",
                evidence_ids=ev.ids("env.PYTHONPATH.present"),
                hypothesis="Extra directories are added to every interpreter's import path, so imports can find (or shadow) modules that aren't in the environment.",
                confidence="low",
                next_check="Ask whether PYTHONPATH was set on purpose. If an import behaves strangely, retry in a shell where it is unset.",
                limitations=("Many setups set PYTHONPATH deliberately. On its own it is not a problem.",),
            )
        )
    if _yes(ev.value("env.PYTHONHOME.present")):
        out.append(
            Finding(
                finding_id="env.pythonhome_set",
                status="warn",
                summary="PYTHONHOME is set (value not collected)",
                evidence_ids=ev.ids("env.PYTHONHOME.present"),
                hypothesis="PYTHONHOME overrides where Python finds its standard library and commonly breaks virtual environments and other interpreters.",
                confidence="medium",
                next_check="Retry the failing command in a shell where PYTHONHOME is unset.",
            )
        )
    if _yes(ev.value("env.CONDA_PREFIX.present")) and _yes(ev.value("project.venv.present")):
        out.append(
            Finding(
                finding_id="env.conda_and_venv",
                status="info",
                summary="A conda environment is active and the project also has a virtual environment",
                evidence_ids=ev.ids("env.CONDA_PREFIX.present", "project.venv.present"),
                hypothesis="Two environment systems are in play, so `python` may come from conda rather than the project venv.",
                confidence="low",
                next_check=f"Run `{PRINT_PREFIX}` and compare it with the project venv path.",
            )
        )
    return out


def rule_collector_errors(ev: EvidenceSet, ctx: ScanContext) -> list[Finding]:
    return [
        Finding(
            finding_id=f"engine.{e.check_id}",
            status="unknown",
            summary=f"{e.fact}; related checks were not performed",
            evidence_ids=(e.check_id,),
        )
        for e in ev.with_prefix("collector.")
        if e.check_id.endswith(".error")
    ]


RULES = [
    rule_collector_errors,
    rule_running_interpreter,
    rule_target_interpreter,
    rule_path_python,
    rule_project_root,
    rule_pyproject,
    rule_venv_health,
    rule_no_project_venv,
    rule_virtual_env_var,
    rule_path_python_vs_project_venv,
    rule_env_flags,
]
