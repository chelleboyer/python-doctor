"""Scan orchestration: context -> collectors -> evidence -> rules -> findings."""

from __future__ import annotations

from dataclasses import dataclass

from python_doctor import __version__
from python_doctor.collectors import default_collectors, run_collectors
from python_doctor.context import ScanContext
from python_doctor.models import SCHEMA_VERSION, EvidenceSet, Finding, utc_now
from python_doctor.rules.engine import run_rules
from python_doctor.rules.environment_rules import RULES


@dataclass(frozen=True)
class ScanReport:
    schema_version: str
    tool_version: str
    started_at: str
    context: ScanContext
    evidence: EvidenceSet
    findings: tuple[Finding, ...]

    def counts(self) -> dict[str, int]:
        c = {s: 0 for s in ("pass", "info", "warn", "fail", "unknown")}
        for f in self.findings:
            c[f.status] += 1
        return c


def run_scan(ctx: ScanContext) -> ScanReport:
    started = utc_now()
    evidence = run_collectors(ctx, default_collectors())
    findings = run_rules(evidence, ctx, RULES)
    return ScanReport(SCHEMA_VERSION, __version__, started, ctx, evidence, tuple(findings))
