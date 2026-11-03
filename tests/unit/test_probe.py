import json
import os
import sys

from python_doctor.collectors.probe import (
    PROBE_SCRIPT,
    parse_probe_output,
    probe_argv,
    probe_interpreter,
)


def test_probe_runs_isolated_and_without_site():
    argv = probe_argv("python")
    assert argv[1:3] == ["-I", "-S"]
    assert argv[3] == "-c"
    # Single line, so Windows command-line quoting can't mangle it.
    assert "\n" not in PROBE_SCRIPT


def test_probe_imports_only_stdlib():
    head = PROBE_SCRIPT.split(";", 1)[0]
    assert head == "import sys, os, json, sysconfig"
    assert PROBE_SCRIPT.count("import ") == 1


def test_probe_of_current_interpreter():
    r = probe_interpreter(sys.executable)
    assert r.ok, r.detail
    assert r.data["version"] == "%d.%d.%d" % sys.version_info[:3]
    # Our process ran *with* site, so its prefix is authoritative.
    assert os.path.normcase(os.path.realpath(r.data["prefix"])) == os.path.normcase(os.path.realpath(sys.prefix))


def test_parse_rejects_non_json_and_missing_keys():
    assert parse_probe_output("hello").status == "invalid_output"
    assert parse_probe_output("[1]").status == "invalid_output"
    assert parse_probe_output(json.dumps({"executable": "x"})).status == "invalid_output"


def test_parse_drops_unknown_and_non_string_fields():
    payload = {
        "executable": "/x/python", "version": "3.12.0", "prefix": "/x", "base_prefix": "/x",
        "purelib": None, "evil": "rm -rf /", "platform": 42,
    }
    r = parse_probe_output(json.dumps(payload))
    assert r.ok
    assert "evil" not in r.data and "platform" not in r.data
    assert r.data["purelib"] is None


def test_probe_of_missing_interpreter(tmp_path):
    assert probe_interpreter(str(tmp_path / "nope")).status == "not_found"
