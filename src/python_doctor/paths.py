"""Path helpers that behave the same on Windows, macOS and Linux."""

from __future__ import annotations

import os
from pathlib import Path


class OutsideRootError(Exception):
    """A project file resolves (via symlink) to somewhere outside the project."""


def norm(p: str | os.PathLike[str]) -> str:
    """Canonical form for *comparing* directories: realpath + normcase.

    Use this for directories such as ``sys.prefix``. Do NOT use it on a venv's
    ``python`` executable: on POSIX that is usually a symlink to the base
    interpreter, so resolving it erases exactly the information we want.
    """
    return os.path.normcase(os.path.realpath(os.fspath(p)))


def same_dir(a: str | os.PathLike[str] | None, b: str | os.PathLike[str] | None) -> bool:
    if a is None or b is None:
        return False
    return norm(a) == norm(b)


def is_within(child: str | os.PathLike[str], parent: str | os.PathLike[str]) -> bool:
    """True if ``child`` is ``parent`` or lies beneath it (lexically, no resolve).

    Lexical comparison is intentional for executables found on PATH: we want to
    know if ``.../.venv/bin/python`` is *in* the venv dir, even though the file
    is a symlink to an interpreter elsewhere. Only the parent is resolved, to
    handle platform aliases like macOS ``/var`` -> ``/private/var``.
    """
    child_s = os.path.abspath(os.fspath(child))
    parent_s = os.fspath(parent)
    # The child's *directory* may be resolved; its final component must not be.
    childs = {
        child_s,
        os.path.join(os.path.realpath(os.path.dirname(child_s)), os.path.basename(child_s)),
    }
    parents = {os.path.abspath(parent_s), os.path.realpath(parent_s)}
    for c in childs:
        c = os.path.normcase(c)
        for p in parents:
            p = os.path.normcase(p).rstrip(os.sep)
            if c == p or c.startswith(p + os.sep):
                return True
    return False


def venv_python_candidates(venv_dir: Path, platform: str) -> list[Path]:
    """Where a venv's interpreter lives for a given ``sys.platform`` value."""
    if platform == "win32":
        return [venv_dir / "Scripts" / "python.exe"]
    return [venv_dir / "bin" / "python", venv_dir / "bin" / "python3"]


def looks_like_windows_store_alias(path: str | None) -> bool:
    """The ``python.exe`` App Execution Alias under ``...\\WindowsApps``.

    Running it when Python isn't installed from the Store opens the Store app
    (or prints a hint and exits 9009). We never execute it.
    """
    if not path:
        return False
    # Split on both separators so this also works when testing on POSIX.
    parts = [p.lower() for p in path.replace("\\", "/").split("/")]
    return "windowsapps" in parts


def safe_read_text(path: Path, root: Path, max_bytes: int = 1024 * 1024) -> str:
    """Read a small project file without following symlinks out of ``root``.

    Raises OutsideRootError, FileNotFoundError, PermissionError, or ValueError
    (file too large).
    """
    resolved = Path(os.path.realpath(path))
    root_resolved = Path(os.path.realpath(root))
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        raise OutsideRootError(str(path)) from None
    size = resolved.stat().st_size
    if size > max_bytes:
        raise ValueError(f"file is {size} bytes; limit is {max_bytes}")
    with open(resolved, "rb") as fh:
        data = fh.read(max_bytes + 1)
    return data.decode("utf-8", errors="replace")
