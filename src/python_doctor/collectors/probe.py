"""Ask *another* interpreter about itself, safely.

We run ``<python> -I -S -c <PROBE_SCRIPT>``:

* ``-I`` (isolated): ignores PYTHON* env vars and the user site dir, and does
  not put the current directory on ``sys.path``. That last point matters: a
  student's ``json.py`` in the project folder would otherwise shadow the stdlib
  ``json`` our probe imports.
* ``-S``: skips ``site``. ``site`` processes ``.pth`` files, and ``.pth`` files
  can execute arbitrary code.

The catch with ``-S``: ``site.venv()`` is what moves ``sys.prefix`` onto the
virtual environment, so under ``-S`` a venv interpreter reports its *base*
prefix (verified on CPython 3.11-3.13). The probe therefore applies
``site.venv()``'s own rule itself: a ``pyvenv.cfg`` in the executable's
directory or its parent makes that directory the effective prefix. The
startup value is still reported as ``raw_prefix`` for transparency. For the
same reason, ``purelib`` is computed with the ``venv`` install scheme when a
venv is detected (3.11+); otherwise distro schemes such as Debian's
``posix_local`` would give a wrong site-packages path.

The probe only imports stdlib modules and prints one JSON object. It is kept on
a single line so it survives Windows command-line quoting unchanged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from python_doctor.proc import run_bounded

PROBE_VERSION = 2

PROBE_SCRIPT = (
    "import sys, os, json, sysconfig; "
    "e = sys.executable or ''; "
    "d = os.path.dirname(e); "
    "c = [p for p in (os.path.join(d, 'pyvenv.cfg'), os.path.join(os.path.dirname(d), 'pyvenv.cfg')) "
    "if e and os.path.isfile(p)]; "
    "v = os.path.dirname(c[0]) if c else None; "
    "x = v or sys.prefix; "
    "sys.stdout.write(json.dumps({"
    "'probe_version': 2, "
    "'executable': e, "
    "'version': '%d.%d.%d' % tuple(sys.version_info[:3]), "
    "'implementation': getattr(getattr(sys, 'implementation', None), 'name', 'unknown'), "
    "'prefix': x, "
    "'raw_prefix': sys.prefix, "
    "'base_prefix': getattr(sys, 'base_prefix', sys.prefix), "
    "'venv_cfg': c[0] if c else None, "
    "'platform': sys.platform, "
    "'purelib': (sysconfig.get_paths('venv', vars={'base': x, 'platbase': x}) "
    "if v and 'venv' in sysconfig.get_scheme_names() "
    "else sysconfig.get_paths(vars={'base': x, 'platbase': x})).get('purelib')"
    "}))"
)

REQUIRED_STR_KEYS = ("executable", "version", "prefix", "base_prefix")


@dataclass(frozen=True)
class ProbeResult:
    status: str  # ok | timeout | not_found | permission_denied | error | invalid_output
    data: dict | None = None
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def probe_argv(python: str) -> list[str]:
    return [python, "-I", "-S", "-c", PROBE_SCRIPT]


def probe_interpreter(python: str, timeout: float = 5.0) -> ProbeResult:
    res = run_bounded(probe_argv(python), timeout=timeout, max_bytes=16 * 1024)
    if res.error == "not_found":
        return ProbeResult("not_found", detail="executable not found")
    if res.error == "permission_denied":
        return ProbeResult("permission_denied", detail="permission denied")
    if res.error:
        return ProbeResult("error", detail=res.error)
    if res.timed_out:
        return ProbeResult("timeout", detail=f"no response within {timeout:g}s")
    if res.returncode != 0:
        tail = (res.stderr or res.stdout).strip().splitlines()[-1:] or [""]
        return ProbeResult("error", detail=f"exit code {res.returncode}: {tail[0][:300]}")
    return parse_probe_output(res.stdout)


def parse_probe_output(text: str) -> ProbeResult:
    try:
        data = json.loads(text)
    except ValueError:
        return ProbeResult("invalid_output", detail="probe output was not JSON")
    if not isinstance(data, dict):
        return ProbeResult("invalid_output", detail="probe output was not a JSON object")
    for key in REQUIRED_STR_KEYS:
        if not isinstance(data.get(key), str):
            return ProbeResult("invalid_output", detail=f"probe output missing {key!r}")
    # Keep only known keys with string values; never trust extra fields.
    clean = {
        k: v
        for k, v in data.items()
        if k in (*REQUIRED_STR_KEYS, "implementation", "platform", "purelib", "raw_prefix", "venv_cfg")
        and (isinstance(v, str) or v is None)
    }
    return ProbeResult("ok", data=clean)
