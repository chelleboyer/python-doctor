"""The one place Python Doctor starts subprocesses.

Invariants (enforced here, tested in tests/unit/test_proc.py):

* argv is a sequence of strings; a bare string is rejected, never split.
* ``shell=False`` always. No user-provided string is ever interpolated into a
  shell command line.
* stdin is closed (``DEVNULL``) so a child can never block waiting for input.
* Wall-clock timeout; the child is killed when it expires.
* Captured output is capped at ``max_bytes`` per stream; the rest is drained
  and discarded so the child cannot block on a full pipe.
* Missing executables and permission errors become a result, not an exception.
"""

from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from typing import IO, Sequence

DEFAULT_TIMEOUT = 5.0
DEFAULT_MAX_BYTES = 64 * 1024


@dataclass(frozen=True)
class ProcResult:
    argv: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    truncated: bool = False
    error: str | None = None  # "not_found" | "permission_denied" | "os_error: ..."

    @property
    def ok(self) -> bool:
        return self.error is None and not self.timed_out and self.returncode == 0


def _drain(stream: IO[bytes], limit: int, sink: list[bytes], flag: list[bool]) -> None:
    kept = 0
    try:
        while True:
            chunk = stream.read(8192)
            if not chunk:
                break
            if kept < limit:
                take = chunk[: limit - kept]
                sink.append(take)
                kept += len(take)
                if len(take) < len(chunk):
                    flag[0] = True
            else:
                flag[0] = True  # keep reading so the child never blocks
    except (OSError, ValueError):
        pass


def run_bounded(
    argv: Sequence[str],
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    cwd: str | None = None,
) -> ProcResult:
    if isinstance(argv, (str, bytes)):
        raise TypeError("run_bounded requires an argument list, not a command string")
    args = tuple(str(a) for a in argv)
    if not args:
        raise ValueError("empty argv")

    try:
        proc = subprocess.Popen(  # noqa: S603 - argv list, shell=False by design
            list(args),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            cwd=cwd,
        )
    except FileNotFoundError:
        return ProcResult(args, None, "", "", error="not_found")
    except PermissionError:
        return ProcResult(args, None, "", "", error="permission_denied")
    except OSError as exc:  # e.g. exec format error, Windows app-alias oddities
        return ProcResult(args, None, "", "", error=f"os_error: {exc.strerror or exc}")

    out: list[bytes] = []
    err: list[bytes] = []
    out_trunc = [False]
    err_trunc = [False]
    threads = [
        threading.Thread(target=_drain, args=(proc.stdout, max_bytes, out, out_trunc), daemon=True),
        threading.Thread(target=_drain, args=(proc.stderr, max_bytes, err, err_trunc), daemon=True),
    ]
    for t in threads:
        t.start()

    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
        proc.wait()
    for t in threads:
        t.join(timeout=2)

    return ProcResult(
        argv=args,
        returncode=None if timed_out else proc.returncode,
        stdout=b"".join(out).decode("utf-8", errors="replace"),
        stderr=b"".join(err).decode("utf-8", errors="replace"),
        timed_out=timed_out,
        truncated=out_trunc[0] or err_trunc[0],
    )
