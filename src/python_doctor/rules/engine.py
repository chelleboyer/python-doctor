"""Run rules over an EvidenceSet.

A rule is a pure function ``(EvidenceSet, ScanContext) -> list[Finding]``.
Rules must not touch the filesystem or start processes; everything they need
is in the evidence. A rule that raises, or that produces an invalid finding
(duplicate id, citing evidence that doesn't exist), yields a single
``unknown`` finding instead of a guess. Spec §12: a failed check returns
unknown, not a false diagnosis.
"""

from __future__ import annotations

from typing import Callable, Iterable

from python_doctor.context import ScanContext
from python_doctor.models import EvidenceSet, Finding

Rule = Callable[[EvidenceSet, ScanContext], "list[Finding]"]


class RuleContractError(Exception):
    pass


def _validate(produced: list[Finding], evidence: EvidenceSet, seen: set[str]) -> None:
    local: set[str] = set()
    for f in produced:
        if not isinstance(f, Finding):
            raise RuleContractError(f"rule returned {type(f).__name__}, not Finding")
        if f.finding_id in seen or f.finding_id in local:
            raise RuleContractError(f"duplicate finding id {f.finding_id!r}")
        for eid in f.evidence_ids:
            if not evidence.has(eid):
                raise RuleContractError(f"{f.finding_id} cites missing evidence {eid!r}")
        local.add(f.finding_id)


def run_rules(evidence: EvidenceSet, ctx: ScanContext, rules: Iterable[Rule]) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[str] = set()
    for rule in rules:
        name = getattr(rule, "__name__", "rule")
        try:
            produced = list(rule(evidence, ctx))
            _validate(produced, evidence, seen)
        except Exception as exc:  # noqa: BLE001
            produced = [
                Finding(
                    finding_id=f"engine.rule_error.{name}",
                    status="unknown",
                    summary=f"Internal error in rule {name}; this area was not assessed",
                    limitations=(f"{type(exc).__name__}: {exc}",),
                )
            ]
        for f in produced:
            seen.add(f.finding_id)
            findings.append(f)
    return findings
