"""Read-only collectors. Each returns a list of Evidence and never raises."""

from __future__ import annotations

from typing import Callable

from python_doctor.context import ScanContext
from python_doctor.models import Evidence, EvidenceSet

Collector = Callable[[ScanContext], "list[Evidence]"]


def run_collectors(ctx: ScanContext, collectors: list[tuple[str, Collector]]) -> EvidenceSet:
    """Run each collector; a crash becomes ``collector.<name>.error`` evidence."""
    evidence = EvidenceSet()
    for name, collect in collectors:
        try:
            items = collect(ctx)
        except Exception as exc:  # noqa: BLE001 - a collector bug must not kill the scan
            items = [
                Evidence(
                    check_id=f"collector.{name}.error",
                    source=f"collector:{name}",
                    fact=f"The {name} collector failed",
                    value=f"{type(exc).__name__}: {exc}",
                    sensitivity="path",  # exception text may contain paths
                )
            ]
        for item in items:
            if evidence.has(item.check_id):
                # Two collectors claiming one id is a programming error; keep the first.
                continue
            evidence.add(item)
    return evidence


def default_collectors() -> list[tuple[str, Collector]]:
    from python_doctor.collectors import interpreter, project

    return [
        ("interpreter", interpreter.collect),
        ("project", project.collect),
    ]
