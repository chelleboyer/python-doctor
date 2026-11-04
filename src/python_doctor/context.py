"""Scan context: where we are, which project, which interpreter is the target."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

#: Files/dirs that mark a project root, in priority order for reporting.
ROOT_MARKERS = (
    "pyproject.toml",
    "uv.lock",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    ".git",
)

MAX_WALK_DEPTH = 64


@dataclass(frozen=True)
class ScanContext:
    cwd: Path
    project_root: Path | None
    root_markers: tuple[str, ...]
    target_python: Path | None  # explicitly selected with --python; None = running interpreter
    probe_enabled: bool
    platform: str
    home: Path | None

    @classmethod
    def discover(
        cls,
        *,
        cwd: Path | None = None,
        project: Path | None = None,
        target_python: Path | None = None,
        probe_enabled: bool = True,
        platform: str | None = None,
        home: Path | None = None,
    ) -> ScanContext:
        cwd = Path(cwd or os.getcwd())
        home = home if home is not None else _home()
        if project is not None:
            root: Path | None = Path(project).absolute()
            markers = _markers_in(root)
        else:
            root, markers = find_project_root(cwd, stop_at=home)
        return cls(
            cwd=cwd,
            project_root=root,
            root_markers=markers,
            target_python=Path(target_python) if target_python else None,
            probe_enabled=probe_enabled,
            platform=platform or sys.platform,
            home=home,
        )


def _home() -> Path | None:
    try:
        return Path.home()
    except (RuntimeError, KeyError):  # no HOME / no passwd entry
        return None


def _markers_in(d: Path) -> tuple[str, ...]:
    found = []
    for m in ROOT_MARKERS:
        try:
            if (d / m).exists():
                found.append(m)
        except OSError:
            continue
    return tuple(found)


def find_project_root(start: Path, stop_at: Path | None = None) -> tuple[Path | None, tuple[str, ...]]:
    """Walk up from ``start`` to the nearest directory containing a root marker.

    The walk never goes above ``stop_at`` (normally the home directory) so that
    a stray ``~/../pyproject.toml`` or ``/requirements.txt`` doesn't hijack the
    result. ``stop_at`` itself is checked. If ``start`` is not under
    ``stop_at``, the walk continues to the filesystem root.
    """
    current = Path(os.path.abspath(start))
    stop = Path(os.path.abspath(stop_at)) if stop_at else None
    if stop is not None and not _is_under(current, stop):
        stop = None
    for _ in range(MAX_WALK_DEPTH):
        markers = _markers_in(current)
        if markers:
            return current, markers
        if stop is not None and os.path.normcase(str(current)) == os.path.normcase(str(stop)):
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None, ()


def _is_under(child: Path, parent: Path) -> bool:
    c, p = os.path.normcase(str(child)), os.path.normcase(str(parent))
    return c == p or c.startswith(p.rstrip(os.sep) + os.sep)
