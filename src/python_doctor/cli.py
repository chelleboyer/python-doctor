"""Command-line interface.

Exit codes:
  0  scan completed and nothing was ``fail``
  1  scan completed with at least one ``fail`` finding
  2  usage error, or a command that isn't available in this build yet
  3  internal error
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from python_doctor import __version__

EXIT_OK, EXIT_FINDINGS, EXIT_USAGE, EXIT_INTERNAL = 0, 1, 2, 3

#: Commands whose interface is fixed now but whose implementation lands later.
PLANNED = {
    "check": "Milestone B (package and import checks)",
    "troubleshoot": "Milestone C (interactive troubleshooting)",
    "practice": "Milestone C (practice scenarios)",
    "explain": "Milestone C (knowledge cards)",
    "commands": "Milestone C (command cheat sheet)",
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python-doctor",
        description=(
            "Read-only diagnostics for Python environments. "
            "Python Doctor never installs, deletes, or changes anything."
        ),
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    scan = sub.add_parser("scan", help="inspect interpreters, PATH, the project and its virtual environment")
    scan.add_argument("--project", type=Path, metavar="DIR", help="project root (default: search upward from the current directory)")
    scan.add_argument("--python", type=Path, metavar="PATH", dest="target_python", help="also query this interpreter (for example .venv/bin/python)")
    scan.add_argument("--no-probe", action="store_true", help="do not start any interpreter subprocesses; report PATH locations only")
    scan.add_argument("--verbose", "-v", action="store_true", help="show the evidence behind every finding")
    scan.add_argument("--json", action="store_true", help="machine-readable report (Milestone B)")
    scan.add_argument("--share", action="store_true", help="sanitized report for sharing (Milestone B)")

    check = sub.add_parser("check", help="check one package or import")
    csub = check.add_subparsers(dest="check_kind", metavar="KIND")
    ci = csub.add_parser("import", help="try importing a module in a subprocess (executes its code; needs consent)")
    ci.add_argument("module")
    ci.add_argument("--explain", action="store_true")
    ci.add_argument("--allow-import-execution", action="store_true", help="consent to running the module's import-time code")
    cp = csub.add_parser("package", help="look up an installed distribution's metadata (no code is run)")
    cp.add_argument("distribution")

    sub.add_parser("troubleshoot", help="guided, one-question-at-a-time troubleshooting")
    pr = sub.add_parser("practice", help="practice diagnosing broken environments safely")
    pr.add_argument("--topic")
    ex = sub.add_parser("explain", help="show a knowledge card, e.g. module-not-found")
    ex.add_argument("card", nargs="?")
    sub.add_parser("commands", help="diagnostic command cheat sheet")
    return p


def _configure_stdout() -> None:
    # Paths can contain characters the console code page can't encode.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def cmd_scan(args: argparse.Namespace) -> int:
    if args.json or args.share:
        flag = "--json" if args.json else "--share"
        print(f"python-doctor: {flag} is not available in this build yet; it is planned for Milestone B.", file=sys.stderr)
        return EXIT_USAGE

    from python_doctor.context import ScanContext
    from python_doctor.renderers import terminal
    from python_doctor.scan import run_scan

    if args.project is not None and not args.project.is_dir():
        print(f"python-doctor: --project {args.project} is not a directory", file=sys.stderr)
        return EXIT_USAGE
    ctx = ScanContext.discover(
        project=args.project,
        target_python=args.target_python,
        probe_enabled=not args.no_probe,
    )
    report = run_scan(ctx)
    sys.stdout.write(terminal.render(report, verbose=args.verbose))
    return EXIT_FINDINGS if report.counts()["fail"] else EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    _configure_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return EXIT_USAGE
    if args.command in PLANNED:
        print(
            f"python-doctor: `{args.command}` is not implemented in this build yet; "
            f"it is planned for {PLANNED[args.command]}.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    try:
        return cmd_scan(args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"python-doctor: internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("No changes were made. Please report this with the command you ran.", file=sys.stderr)
        return EXIT_INTERNAL


if __name__ == "__main__":
    raise SystemExit(main())
