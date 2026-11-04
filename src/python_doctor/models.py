"""Core data model.

Two record types, deliberately separate:

* :class:`Evidence` is something we *observed* (a path, a version, a flag).
* :class:`Finding` is what we *conclude* from evidence, with an explicit
  hypothesis, a confidence, what we still don't know, and the next check.

``status`` describes what a check found. ``confidence`` describes how strongly
the evidence supports the causal hypothesis. They are independent: a check can
``warn`` with ``low`` confidence in its explanation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Iterator, Union

#: Bump when the JSON shape of Evidence/Finding/report changes incompatibly.
SCHEMA_VERSION = "0.1"

STATUSES = ("pass", "info", "warn", "fail", "unknown")
CONFIDENCES = ("low", "medium", "high", "not_applicable")
SENSITIVITIES = ("public", "path", "sensitive")

EvidenceValue = Union[str, bool, None]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Evidence:
    """A single observed fact.

    ``check_id`` is the stable identifier for this fact within a scan and is
    what findings reference in ``evidence_ids``. ``sensitivity`` tells the
    (Milestone B) sanitizer how to treat ``value`` when building share output:

    * ``public``: safe to share as-is (versions, booleans).
    * ``path``: a filesystem path; home dirs/usernames must be replaced.
    * ``sensitive``: omit from shared output entirely (e.g. project name).
    """

    check_id: str
    source: str
    fact: str
    value: EvidenceValue
    sensitivity: str = "public"
    observed_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.check_id or not isinstance(self.check_id, str):
            raise ValueError("Evidence.check_id must be a non-empty string")
        if self.sensitivity not in SENSITIVITIES:
            raise ValueError(f"invalid sensitivity {self.sensitivity!r}")
        if self.value is not None and not isinstance(self.value, (str, bool)):
            raise TypeError(
                f"Evidence.value must be str, bool or None, got {type(self.value).__name__}"
            )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Finding:
    finding_id: str
    status: str
    summary: str
    evidence_ids: tuple[str, ...] = ()
    hypothesis: str | None = None
    confidence: str = "not_applicable"
    next_check: str | None = None
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.finding_id:
            raise ValueError("Finding.finding_id must be non-empty")
        if self.status not in STATUSES:
            raise ValueError(f"invalid status {self.status!r}")
        if self.confidence not in CONFIDENCES:
            raise ValueError(f"invalid confidence {self.confidence!r}")
        # Guard against a common bug: passing a bare string becomes a tuple of chars.
        for name in ("evidence_ids", "limitations"):
            if isinstance(getattr(self, name), str):
                raise TypeError(f"Finding.{name} must be a tuple, not a str")
        if self.hypothesis is not None and self.confidence == "not_applicable":
            raise ValueError("a Finding with a hypothesis must state a confidence")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["evidence_ids"] = list(self.evidence_ids)
        d["limitations"] = list(self.limitations)
        return d


class EvidenceSet:
    """Evidence indexed by ``check_id``. Later duplicates are rejected."""

    def __init__(self, items: Iterable[Evidence] = ()) -> None:
        self._items: dict[str, Evidence] = {}
        for item in items:
            self.add(item)

    def add(self, item: Evidence) -> None:
        if item.check_id in self._items:
            raise ValueError(f"duplicate evidence id {item.check_id!r}")
        self._items[item.check_id] = item

    def extend(self, items: Iterable[Evidence]) -> None:
        for item in items:
            self.add(item)

    def get(self, check_id: str) -> Evidence | None:
        return self._items.get(check_id)

    def value(self, check_id: str, default: EvidenceValue = None) -> EvidenceValue:
        item = self._items.get(check_id)
        return default if item is None else item.value

    def has(self, check_id: str) -> bool:
        return check_id in self._items

    def ids(self, *check_ids: str) -> tuple[str, ...]:
        """Return the subset of ``check_ids`` that exist, preserving order."""
        return tuple(c for c in check_ids if c in self._items)

    def with_prefix(self, prefix: str) -> list[Evidence]:
        return [e for k, e in self._items.items() if k.startswith(prefix)]

    def __iter__(self) -> Iterator[Evidence]:
        return iter(self._items.values())

    def __len__(self) -> int:
        return len(self._items)
