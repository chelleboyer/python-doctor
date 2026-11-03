"""Project evidence: root markers, pyproject.toml, uv.lock, and the project venv.

Boundaries:

* Only a fixed allowlist of files is read: ``pyproject.toml``,
  ``.python-version`` and ``<venv>/pyvenv.cfg``. Never ``.env`` or anything
  else in the project.
* Reads are size-capped and refuse symlinks that resolve outside the project.
* Presence of ``.venv`` is recorded as presence. It says nothing about whether
  that environment is active or synchronized; the rules know that.
"""

from __future__ import annotations

import re
from pathlib import Path

from python_doctor.context import ScanContext
from python_doctor.models import Evidence
from python_doctor.paths import OutsideRootError, safe_read_text, venv_python_candidates

try:  # Python 3.11+
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover - exercised on 3.10 CI only
    _toml = None  # type: ignore[assignment]

VENV_DIR_NAMES = (".venv", "venv")
_PY_VERSION_FILE_RE = re.compile(r"^[A-Za-z0-9._+\-]{1,64}$")


def find_project_venv(root: Path) -> Path | None:
    for name in VENV_DIR_NAMES:
        d = root / name
        try:
            if d.is_dir():
                return d
        except OSError:
            continue
    return None


def _read(path: Path, root: Path, prefix: str, ev: list[Evidence], max_bytes: int = 1024 * 1024) -> str | None:
    try:
        return safe_read_text(path, root, max_bytes=max_bytes)
    except OutsideRootError:
        reason = "outside_root"
    except FileNotFoundError:
        reason = "not_found"
    except PermissionError:
        reason = "permission_denied"
    except ValueError:
        reason = "too_large"
    except OSError as exc:
        reason = f"os_error: {exc.strerror or exc}"
    ev.append(Evidence(f"{prefix}.read_error", "filesystem", f"Could not read {path.name}", reason))
    return None


def collect(ctx: ScanContext) -> list[Evidence]:
    ev: list[Evidence] = [
        Evidence("project.cwd", "os.getcwd()", "Current working directory", str(ctx.cwd), "path"),
        Evidence("project.root", "marker walk", "Detected project root", str(ctx.project_root) if ctx.project_root else None, "path"),
        Evidence("project.root_markers", "marker walk", "Root markers found", ", ".join(ctx.root_markers) or None),
    ]
    root = ctx.project_root
    if root is None:
        return ev
    ev.append(Evidence("project.cwd_is_root", "path comparison", "Working directory is the project root", Path(ctx.cwd).absolute() == root))
    ev += collect_pyproject(root)
    ev.append(Evidence("project.uv_lock.present", "filesystem", "uv.lock exists", (root / "uv.lock").is_file()))
    ev.append(Evidence("project.requirements_txt.present", "filesystem", "requirements.txt exists", (root / "requirements.txt").is_file()))
    ev += collect_python_version_file(root)
    ev += collect_venv(root, ctx.platform)
    return ev


def collect_pyproject(root: Path) -> list[Evidence]:
    p = root / "pyproject.toml"
    ev = [Evidence("project.pyproject.present", "filesystem", "pyproject.toml exists", p.is_file())]
    if not p.is_file():
        return ev
    text = _read(p, root, "project.pyproject", ev)
    if text is None:
        return ev
    if _toml is None:
        ev.append(Evidence("project.pyproject.parsed", "tomllib", "pyproject.toml parsed", False))
        ev.append(Evidence("project.pyproject.parse_error", "tomllib", "Why parsing was skipped", "tomllib unavailable (Python < 3.11); presence only"))
        return ev
    try:
        data = _toml.loads(text)
    except _toml.TOMLDecodeError as exc:
        ev.append(Evidence("project.pyproject.parsed", "tomllib", "pyproject.toml parsed", False))
        ev.append(Evidence("project.pyproject.parse_error", "tomllib", "TOML parse error", str(exc)[:300]))
        return ev
    ev.append(Evidence("project.pyproject.parsed", "tomllib", "pyproject.toml parsed", True))
    project = data.get("project") if isinstance(data.get("project"), dict) else None
    ev.append(Evidence("project.pyproject.has_project_table", "pyproject.toml", "[project] table present", project is not None))
    if project is not None:
        name = project.get("name")
        ev.append(Evidence("project.name", "pyproject.toml [project].name", "Project name", name if isinstance(name, str) else None, "sensitive"))
        rp = project.get("requires-python")
        ev.append(Evidence("project.requires_python", "pyproject.toml [project].requires-python", "Declared requires-python", rp if isinstance(rp, str) else None))
        deps = project.get("dependencies")
        count = len(deps) if isinstance(deps, list) else 0
        ev.append(Evidence("project.dependency_count", "pyproject.toml [project].dependencies", "Number of declared runtime dependencies", str(count)))
    groups = data.get("dependency-groups")
    ev.append(Evidence("project.pyproject.has_dependency_groups", "pyproject.toml", "[dependency-groups] table present", isinstance(groups, dict)))
    tool = data.get("tool") if isinstance(data.get("tool"), dict) else {}
    ev.append(Evidence("project.pyproject.has_tool_uv", "pyproject.toml", "[tool.uv] table present", isinstance(tool.get("uv"), dict)))
    return ev


def collect_python_version_file(root: Path) -> list[Evidence]:
    p = root / ".python-version"
    ev = [Evidence("project.python_version_file.present", "filesystem", ".python-version exists", p.is_file())]
    if not p.is_file():
        return ev
    text = _read(p, root, "project.python_version_file", ev, max_bytes=4096)
    if text is None:
        return ev
    first = next((ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")), "")
    value = first if _PY_VERSION_FILE_RE.match(first) else None
    ev.append(Evidence("project.python_version_file.value", ".python-version", "Pinned Python version (validated format only)", value))
    return ev


def parse_pyvenv_cfg(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, _, val = line.partition("=")
        out[key.strip().lower()] = val.strip()
    return out


def collect_venv(root: Path, platform: str) -> list[Evidence]:
    venv = find_project_venv(root)
    ev = [Evidence("project.venv.present", "filesystem", f"A {' or '.join(VENV_DIR_NAMES)} directory exists at the project root", venv is not None)]
    if venv is None:
        return ev
    ev.append(Evidence("project.venv.dir_name", "filesystem", "Name of the project venv directory", venv.name))
    ev.append(Evidence("project.venv.path", "filesystem", "Project venv directory", str(venv.absolute()), "path"))
    ev.append(Evidence("project.venv.posix_layout", "filesystem", "venv has a bin/ directory (POSIX layout)", (venv / "bin").is_dir()))
    ev.append(Evidence("project.venv.windows_layout", "filesystem", "venv has a Scripts/ directory (Windows layout)", (venv / "Scripts").is_dir()))

    expected = venv_python_candidates(venv, platform)
    found = next((c for c in expected if c.exists()), None)
    dangling = next((c for c in expected if c.is_symlink() and not c.exists()), None)
    ev.append(Evidence("project.venv.python", "filesystem", "venv interpreter for this OS", str(found.absolute()) if found else None, "path"))
    ev.append(Evidence("project.venv.python_exists", "filesystem", "venv interpreter exists at the expected location for this OS", found is not None))
    ev.append(Evidence("project.venv.python_dangling_symlink", "filesystem", "venv interpreter is a symlink whose target is missing", dangling is not None))
    if dangling is not None:
        ev.append(Evidence("project.venv.python_expected", "filesystem", "Expected venv interpreter path", str(dangling.absolute()), "path"))
    elif found is None:
        ev.append(Evidence("project.venv.python_expected", "filesystem", "Expected venv interpreter path", str(expected[0].absolute()), "path"))

    cfg_path = venv / "pyvenv.cfg"
    ev.append(Evidence("project.venv.cfg.present", "filesystem", "pyvenv.cfg exists", cfg_path.is_file()))
    if cfg_path.is_file():
        text = _read(cfg_path, root, "project.venv.cfg", ev, max_bytes=64 * 1024)
        if text is not None:
            cfg = parse_pyvenv_cfg(text)
            home = cfg.get("home")
            ev.append(Evidence("project.venv.cfg.home", "pyvenv.cfg", "Base interpreter directory recorded in pyvenv.cfg", home or None, "path"))
            if home:
                ev.append(Evidence("project.venv.cfg.home_exists", "pyvenv.cfg + filesystem", "Base interpreter directory still exists", Path(home).is_dir()))
            ver = cfg.get("version") or cfg.get("version_info")
            ev.append(Evidence("project.venv.cfg.version", "pyvenv.cfg", "Python version the venv was created with", ver or None))
            ev.append(Evidence("project.venv.cfg.created_by_uv", "pyvenv.cfg", "venv was created by uv", "uv" in cfg))
            isp = cfg.get("include-system-site-packages")
            ev.append(Evidence("project.venv.cfg.system_site_packages", "pyvenv.cfg", "venv can see the base interpreter's site-packages", None if isp is None else isp.lower() == "true"))
    return ev


__all__ = ["collect", "find_project_venv", "parse_pyvenv_cfg", "VENV_DIR_NAMES"]
