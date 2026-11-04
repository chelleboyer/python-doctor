# Python Doctor

A local-first, read-only diagnostic and teaching CLI for Python environments.

Python Doctor helps a peer supporter answer *"which Python is actually running this, and why can't it see my package?"* with evidence instead of guesses. It works offline, needs no admin rights, has zero runtime dependencies, and **never installs, deletes, or changes anything**.

> **Status: Milestone A (foundation).** `scan` works for interpreters, PATH, the project, and its virtual environment. `--json`, `--share`, `check`, `troubleshoot`, `practice`, `explain` and `commands` are wired into the CLI but print a "planned for Milestone B/C" message and exit with code 2. See [Roadmap](#roadmap).

## Install

Python 3.10 or newer. *The 3.10 floor is provisional until it's checked against the AI Makerspace prerequisites.*

From a clone:

```bash
# with uv (recommended for development)
uv tool install .          # installs the python-doctor command
# or with plain pip, no uv needed
python -m pip install .
```

Then run it from any project folder:

```bash
python-doctor scan
python -m python_doctor scan    # same thing, if the script isn't on PATH
```

> Tip: install it as a *tool* (`uv tool install`, `pipx install`), not into the student's project venv. Python Doctor reports its own interpreter separately and doesn't need to share an environment with the project.

## What `scan` does

```text
python-doctor scan                       # current directory
python-doctor scan --project path/to/app # explicit project root
python-doctor scan --python .venv/bin/python   # also query this interpreter
python-doctor scan --no-probe            # don't start any subprocesses
python-doctor scan --verbose             # show the evidence behind every finding
```

It collects **evidence**, then runs deterministic **rules** over it. Each finding has a status, the evidence it relies on, a hypothesis with a confidence level (when there is one), a next check, and its limitations.

| Area | What's observed | What it *can't* tell you |
|---|---|---|
| Doctor's interpreter | `sys.executable`, version, `sys.prefix` vs `sys.base_prefix` | Which interpreter the student's code runs under |
| `python` / `python3` / `py` on PATH | `shutil.which`, plus a safe probe of each (see below) | Shell aliases/functions; a different terminal's activation |
| Explicit target (`--python`) | Same probe | Anything about other interpreters |
| Project root | Walks up to the nearest `pyproject.toml`, `uv.lock`, `setup.py`, `setup.cfg`, `requirements.txt` or `.git`, stopping at your home directory | Projects nested inside other projects |
| `pyproject.toml` | Valid TOML? `[project]`, `requires-python`, dependency count, `[tool.uv]` | Whether the environment is in sync (Milestone B) |
| `.venv` / `venv` | Layout, interpreter present, broken links, `pyvenv.cfg` (`home`, version, uv) | Whether it is *used*. That's what the PATH comparison is for |
| Environment variables | **Presence only**: `VIRTUAL_ENV`, `CONDA_PREFIX`, `PYTHONPATH`, `PYTHONHOME`, `UV_PROJECT_ENVIRONMENT` | Their values, which are never collected |

The key rule compares where `python` on PATH actually lives (its reported `sys.prefix`) with the project's venv. It **never** concludes there's a mismatch just because `.venv` exists. When they differ, the hypothesis is stated with high confidence about the *path difference*, along with a reminder that this alone doesn't prove it caused your error.

### Sample output (abridged)

```text
PYTHON DOCTOR 0.1.0.dev0 - READ-ONLY SCAN

[INFO] Python Doctor is running under /home/me/.local/share/uv/tools/python-doctor/bin/python (Python 3.13.1) inside a virtual environment
       Note: This is the interpreter running Python Doctor. It is not necessarily the one your
             project, terminal command, or editor uses.

[WARN] `python` on PATH is not this project's .venv
       Evidence:
         - `python` resolves on PATH to: /usr/bin/python
         - sys.prefix reported by `python` on PATH: /usr
         - Project venv directory: /home/me/app/.venv
       Hypothesis: Running `python your_script.py` in this shell uses /usr, so packages installed
                   into .venv won't be visible to it.
       Confidence: high
       Next check: Compare `python -c "import sys; print(sys.prefix)"` with `uv run python -c
                   "import sys; print(sys.prefix)"`. The second shows what `uv run` uses.
       Note: This shows a path difference; it does not by itself prove that this causes your error.

Summary: 0 fail, 1 warn, 0 unknown, 3 info, 1 pass
No changes made. No imports run. Environment variable values were not collected.
```

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Scan finished; no `fail` findings (warnings don't change the exit code) |
| 1 | Scan finished with at least one `fail` |
| 2 | Usage error, or a command not available in this build yet |
| 3 | Internal error. No changes were made |

## Safety model (short version)

* **Read-only.** Only `pyproject.toml`, `.python-version` and `pyvenv.cfg` are read, size-capped, and never through a symlink that points outside the project. `.env` and credential files are never opened.
* **Interpreter probes run with `-I -S`.** `-I` keeps a student's `json.py` from shadowing the stdlib. `-S` skips `site`, so `.pth` files (which can execute code) don't run. The probe imports only `sys`, `json` and `sysconfig` and prints one JSON line. It has a 5 s timeout, capped output, and runs without a shell. `--no-probe` disables it entirely.
* **The Windows Store `python.exe` alias is never executed.** It's detected by path and reported.
* **No network, no telemetry, no AI.** The diagnosis is deterministic.

Full details are in [docs/SECURITY.md](docs/SECURITY.md).

## Development

```bash
uv sync                 # creates .venv with pytest
uv run pytest           # unit + integration tests
uv run pytest -m "not integration"   # fast unit tests only
```

Integration tests build real virtual environments and use any extra interpreters they find (`python3.11`, `python3.12`, ...). CI runs Linux, macOS and Windows on Python 3.10–3.13 and installs with plain `pip`, which proves the tool doesn't need uv.

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for how to add collectors and rules. The full product spec is in [docs/SPEC.md](docs/SPEC.md).

## Roadmap

| Milestone | Scope | State |
|---|---|---|
| A: Foundation | Packaging, CLI, models, interpreter and project collectors, rules engine, terminal output, tests, CI | **This build** |
| B: Diagnosis | `uv` checks, distribution-metadata checks in the target interpreter, `check package`, opt-in `check import`, `--json`, `--share` with redaction | Planned |
| C: Teaching | 10 knowledge cards, `explain`, `troubleshoot`, 10 practice scenarios with scoring and local progress | Planned |
| D: Hardening | Cross-platform validation, security review, docs, sample outputs, release candidate | Planned |

## License

MIT. See [LICENSE](LICENSE).
