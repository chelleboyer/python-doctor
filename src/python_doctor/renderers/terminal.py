"""Plain-text report for a local terminal.

ASCII only, so it renders on legacy Windows code pages. This output is for
the person at the keyboard and shows real paths. It is *not* the shareable
report (``--share``, Milestone B), which redacts.
"""

from __future__ import annotations

import textwrap

from python_doctor.models import EvidenceSet, EvidenceValue, Finding
from python_doctor.scan import ScanReport

INDENT = " " * 7
WIDTH = 100
DETAILED = ("warn", "fail", "unknown")


def fmt_value(v: EvidenceValue) -> str:
    if v is True:
        return "yes"
    if v is False:
        return "no"
    if v is None:
        return "(none)"
    return v


def _wrap(label: str, text: str) -> list[str]:
    first = f"{INDENT}{label}"
    return textwrap.wrap(
        text,
        width=WIDTH,
        initial_indent=first,
        subsequent_indent=INDENT + " " * len(label),
        break_long_words=False,
        break_on_hyphens=False,
    ) or [first.rstrip()]


def render_finding(f: Finding, ev: EvidenceSet, verbose: bool = False) -> list[str]:
    lines = [f"[{f.status.upper()}] {f.summary}"]
    detailed = verbose or f.status in DETAILED
    if detailed and f.evidence_ids:
        lines.append(f"{INDENT}Evidence:")
        for eid in f.evidence_ids:
            e = ev.get(eid)
            if e is not None:
                lines += _wrap("  - ", f"{e.fact}: {fmt_value(e.value)}")
    if f.hypothesis:
        lines += _wrap("Hypothesis: ", f.hypothesis)
        lines += _wrap("Confidence: ", f.confidence)
    if f.next_check:
        lines += _wrap("Next check: ", f.next_check)
    if f.limitations and (detailed or f.status == "info"):
        for lim in f.limitations:
            lines += _wrap("Note: ", lim)
    return lines


def render(report: ScanReport, verbose: bool = False) -> str:
    out = [f"PYTHON DOCTOR {report.tool_version} - READ-ONLY SCAN", ""]
    for f in report.findings:
        out += render_finding(f, report.evidence, verbose)
        out.append("")
    c = report.counts()
    out.append(
        "Summary: "
        + ", ".join(f"{c[s]} {s}" for s in ("fail", "warn", "unknown", "info", "pass"))
    )
    out.append("No changes made. No imports run. Environment variable values were not collected.")
    if not verbose:
        out.append("Use --verbose to show the evidence behind every finding.")
    return "\n".join(out) + "\n"
