import dataclasses

import pytest

from python_doctor.models import SCHEMA_VERSION, Evidence, EvidenceSet, Finding


def test_evidence_rejects_bad_sensitivity_and_value_types():
    with pytest.raises(ValueError):
        Evidence("a", "s", "f", "v", sensitivity="secret")
    with pytest.raises(TypeError):
        Evidence("a", "s", "f", 3)  # ints must be stringified by the collector
    with pytest.raises(ValueError):
        Evidence("", "s", "f", None)


def test_evidence_is_frozen():
    e = Evidence("a", "s", "f", True)
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.value = False  # type: ignore[misc]


def test_finding_validates_status_and_confidence():
    with pytest.raises(ValueError):
        Finding("x", "broken", "s")
    with pytest.raises(ValueError):
        Finding("x", "warn", "s", confidence="certain")


def test_finding_with_hypothesis_requires_confidence():
    with pytest.raises(ValueError):
        Finding("x", "warn", "s", hypothesis="because")
    Finding("x", "warn", "s", hypothesis="because", confidence="low")


def test_finding_rejects_bare_string_tuples():
    with pytest.raises(TypeError):
        Finding("x", "info", "s", evidence_ids="abc")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Finding("x", "info", "s", limitations="abc")  # type: ignore[arg-type]


def test_finding_to_dict_uses_lists():
    d = Finding("x", "info", "s", evidence_ids=("a",), limitations=("l",)).to_dict()
    assert d["evidence_ids"] == ["a"] and d["limitations"] == ["l"]


def test_evidence_set_rejects_duplicates_and_filters_ids():
    s = EvidenceSet([Evidence("a", "s", "f", True), Evidence("b.c", "s", "f", None)])
    with pytest.raises(ValueError):
        s.add(Evidence("a", "s", "f", False))
    assert s.ids("a", "missing", "b.c") == ("a", "b.c")
    assert s.value("missing", "dflt") == "dflt"
    assert s.value("b.c", "dflt") is None  # present-but-None is not "missing"
    assert [e.check_id for e in s.with_prefix("b.")] == ["b.c"]


def test_schema_version_is_declared():
    assert SCHEMA_VERSION
