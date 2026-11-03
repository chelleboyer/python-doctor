# Python Doctor — Product & Engineering Specification

**Version:** 0.1  
**Status:** Ready for implementation planning  
**Primary user:** Experienced .NET/SQL engineer preparing to support beginner AI engineering students  
**Core principle:** Diagnose with evidence. Teach the reasoning. Never silently change the environment.

## 1. Executive summary

Python Doctor is a local-first, cross-platform command-line diagnostic and learning tool for Python development environments. It helps an experienced software engineer troubleshoot Python, `uv`, virtual environments, imports, dependencies, VS Code, and Jupyter while learning to explain those problems to beginners.

It must operate without Claude, an LLM, network access, or elevated privileges. Optional AI integration is a later phase and must never replace deterministic findings.

**Two distinct modes:**
- **Diagnose:** Gather read-only evidence and present likely causes, confidence, next checks, and proposed commands.
- **Practice:** Present intentionally broken, isolated scenarios, ask the user what to inspect next, and evaluate their reasoning. Do not reveal fixes immediately.

**Success means:** The user can explain and resolve common Python environment problems without AI assistance, and can guide a student through the same process safely.

## 2. Users and jobs to be done

### Primary user: peer supporter
- Quickly triage a student's problem without taking over their computer.
- Know which command to ask for next and why.
- Recognize when evidence is insufficient.
- Translate Python-specific concepts into familiar .NET analogies.
- Build independent troubleshooting skill through repeated practice.

### Secondary user: beginner student
- Run a safe diagnostic on their own machine.
- Share a sanitized report with a supporter.
- Learn one step at a time rather than receiving a wall of commands.

## 3. Scope

### MVP (must ship)
1. Python executable/version and interpreter context.
2. Working directory and project root discovery.
3. Virtual environment detection (`VIRTUAL_ENV`, `.venv`, `sys.prefix`, `sys.base_prefix`), with caveats.
4. `uv` availability and project metadata detection (`pyproject.toml`, `uv.lock`).
5. Distribution-package presence checks scoped to an explicitly identified interpreter.
6. Import checks performed in a separate subprocess, opt-in only; warn that imports may execute arbitrary code.
7. Interpreter/environment mismatch investigation based on observable paths; never assert a mismatch from mere presence of `.venv`.
8. VS Code interpreter guidance, without modifying settings.
9. Jupyter kernel discovery when installed; no notebook execution.
10. Clear terminal and JSON reports, including sanitized sharing output.
11. Interactive troubleshooting workflow and knowledge cards for 10 common errors.
12. At least 10 safe practice scenarios with answer/rationale grading.
13. Unit tests, integration tests, and cross-platform CI.

### Post-MVP
- LangChain/LangGraph package and import-path troubleshooting.
- API errors (401/403/429/timeouts), with redacted diagnostic examples.
- Dependency resolution conflicts and Python-version compatibility.
- More scenarios, progress tracking, spaced repetition, printable cheat sheets.
- Optional AI explanations behind an explicit opt-in.

### Out of scope for MVP
- Automatic installation, environment repair, deletion, or configuration changes.
- Executing arbitrary project scripts during ordinary scans.
- Uploading diagnostics to any remote service.
- Full dependency solver, vulnerability scanner, IDE extension, or web dashboard.
- Claiming root-cause certainty without reproducing and verifying a fix.

## 4. Design principles and safety invariants

1. **Read-only by default.** All standard checks inspect local state only.
2. **No implicit code execution.** Import probes are explicitly opted into, run in subprocesses with timeouts, and clearly warn that imports can have side effects. Avoid running project entry points.
3. **No secrets.** Never collect environment-variable values, credentials, tokens, `.env` contents, pip configuration secrets, or full command history. Collect only safe metadata or allowlisted variable presence flags.
4. **Data minimization.** Report only the paths needed for diagnosis; sanitize usernames, home directories, hostnames, project names, and tokens in shareable output. Explain that automatic redaction is best-effort and require user review before sharing.
5. **Evidence before inference.** Every finding has observations, hypothesis, confidence, unknowns, and a next verification step.
6. **No blind fixes.** Never suggest `pip install` or `uv add` until the project environment and dependency declaration have been inspected.
7. **Offline-first.** No network calls during scans or practice.
8. **Portable.** Use `pathlib`, `subprocess` argument arrays, and platform-specific alternatives; no assumptions about Bash on Windows.
9. **Teaching-first.** Explain what a command proves, what it cannot prove, and how to interpret the result.
10. **Deterministic core.** No model-generated diagnoses in the MVP.

## 5. User experience and CLI

Proposed executable: `python-doctor` (package entry point). Also support `python -m python_doctor`.

```text
python-doctor scan
python-doctor scan --json
python-doctor scan --share
python-doctor check import langchain_core --explain
python-doctor check package langchain-core
python-doctor troubleshoot
python-doctor practice
python-doctor practice --topic environments
python-doctor explain module-not-found
python-doctor commands
python-doctor --help
```

**Important:** `check import` must ask for confirmation or require `--allow-import-execution`; never execute imports silently. `scan` must not run imports or dependency-install commands.

### Sample terminal report

```text
PYTHON DOCTOR 0.1 — READ-ONLY SCAN

[PASS] Running interpreter: /project/.venv/bin/python (3.12.x)
[INFO] Project metadata: pyproject.toml and uv.lock found
[INFO] uv executable: found
[WARN] Shell `python` resolves to /usr/bin/python3
       Evidence: explicit path checks
       Hypothesis: shell command may bypass the project environment
       Confidence: high for path difference; root cause not yet proven
       Next check: compare execution via `uv run python ...`
[UNKNOWN] langchain_core importability (import execution not authorized)

No changes made. No secrets collected.
```

The scan must not label a package as absent just because its distribution metadata is not found under a different interpreter.

### Troubleshooting interaction

For each question:
1. State the symptom.
2. Ask one discriminating question or propose one safe check.
3. Explain why it matters.
4. Accept observed results.
5. Update the hypothesis set.
6. Offer a fix only after enough evidence, and request confirmation of outcome.

## 6. Diagnostic pipeline

```text
CLI
  -> Context discovery
  -> Read-only collectors
  -> Normalized evidence records
  -> Deterministic rule engine
  -> Findings + competing hypotheses
  -> Next-step planner
  -> Terminal / JSON / sanitized-share renderers

Practice mode
  -> Scenario fixture
  -> User's selected diagnostic step
  -> Simulated result
  -> Explanation and scoring
```

### Data model

Use typed dataclasses or Pydantic only if justified; prefer the standard library initially.

```python
@dataclass(frozen=True)
class Evidence:
    check_id: str
    observed_at: str
    source: str
    fact: str
    value: str | bool | None
    sensitivity: str  # public | path | sensitive

@dataclass(frozen=True)
class Finding:
    finding_id: str
    status: str  # pass | info | warn | fail | unknown
    summary: str
    evidence_ids: tuple[str, ...]
    hypothesis: str | None
    confidence: str  # low | medium | high | not_applicable
    next_check: str | None
    limitations: tuple[str, ...]
```

Separate `status` (what a check found) from `confidence` (strength of a causal hypothesis). Include schema version in JSON. Findings should use stable IDs and never rely on display text as an identifier.

## 7. Checks and their boundaries

| Check | Evidence | Caveat |
|---|---|---|
| Running interpreter | `sys.executable`, `sys.version` | Reports the Doctor process, not necessarily the student's launch command |
| Shell interpreter | `shutil.which('python')`, optional subprocess | Shell aliases/functions can differ from PATH lookup |
| Virtual environment | `sys.prefix`, `sys.base_prefix`, `VIRTUAL_ENV`, `.venv` | `.venv` existing does not mean it is active |
| Project metadata | `pyproject.toml`, `uv.lock` existence and safe parsing | Presence alone does not prove synchronization |
| Distribution metadata | `importlib.metadata` under target interpreter | Distribution names differ from import names |
| Importability | `importlib.util.find_spec` or subprocess import | `find_spec` can trigger parent-package imports; full imports execute code |
| uv | executable presence and optional version | `uv pip` and `uv run` may target different contexts |
| VS Code | optional workspace settings | User settings and actual selected interpreter may differ |
| Jupyter | kernelspec metadata | A kernelspec can reference a missing or wrong interpreter |

Do not assume `python -m pip` works: some environments do not contain pip. If a target interpreter differs from the Doctor process, use an explicitly selected subprocess to query that interpreter with bounded timeouts and no shell interpolation.

## 8. Diagnostic knowledge cards

Store cards as Markdown with machine-readable front matter or structured JSON metadata. Each card must include:

- Error signature and common variants.
- What the error establishes (and does not establish).
- Competing causes ranked by diagnostic relevance, not assumed prevalence.
- Safe checks, expected outputs, and interpretations.
- Fix options with prerequisites and rollback notes.
- Verification command and success criteria.
- Beginner-friendly explanation.
- Optional .NET analogy, labeled as analogy rather than exact equivalence.
- Common anti-patterns.

**MVP cards:** `ModuleNotFoundError`, `ImportError`, `AttributeError`, `TypeError`, `FileNotFoundError`, interpreter mismatch, missing/incorrect virtual environment, `uv` dependency mismatch, Jupyter kernel mismatch, and missing API-key configuration (presence only, never values).

Example: `ModuleNotFoundError: No module named 'langchain_core'`:
1. Identify exact launch command and interpreter.
2. Inspect project dependency declarations and environment.
3. Check distribution `langchain-core` in the target interpreter.
4. Distinguish distribution name from import name `langchain_core`.
5. Compare `python main.py` and `uv run python main.py` only when appropriate.
6. Recommend a targeted fix only after locating the mismatch.
7. Re-run the original failing command to verify.

## 9. Practice mode and learning design

Each scenario is an isolated, deterministic fixture, not a script that damages the user's machine. It includes:
- Student's original report and terminal output.
- Hidden underlying cause and plausible distractors.
- Available diagnostic actions with simulated outputs.
- Expected reasoning sequence, acceptable alternate sequences, and hints.
- Scoring for evidence gathering, safety, root-cause identification, verification, and student-friendly explanation.

**First 10 scenarios:**
1. Installed with `uv pip`, launched with system Python.
2. VS Code selects an interpreter different from the terminal.
3. Jupyter kernelspec points to a deleted environment.
4. Distribution name differs from import name.
5. Dependency exists but incompatible version removed/renamed an API.
6. `pyproject.toml` updated but environment not synchronized.
7. Wrong working directory causes file lookup failure.
8. Local file shadows an installed module (`json.py`, `typing.py`).
9. API key absent from the actual running process (never display values).
10. `python -m pip` fails because pip is unavailable in that interpreter.

Practice must have **hint**, **reveal**, **retry**, and **explain-to-student** stages. Score diagnostic method, not command memorization. Store progress locally and allow reset/export.

## 10. Architecture and repository structure

```text
python-doctor/
├── README.md
├── pyproject.toml
├── LICENSE
├── src/python_doctor/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── models.py
│   ├── context.py
│   ├── collectors/
│   │   ├── interpreter.py
│   │   ├── project.py
│   │   ├── packages.py
│   │   ├── uv.py
│   │   ├── vscode.py
│   │   └── jupyter.py
│   ├── rules/
│   │   ├── engine.py
│   │   └── environment_rules.py
│   ├── renderers/
│   │   ├── terminal.py
│   │   ├── json_output.py
│   │   └── sanitized.py
│   ├── teaching/
│   │   ├── troubleshoot.py
│   │   └── practice.py
│   └── security/
│       └── redaction.py
├── knowledge/
├── scenarios/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
└── docs/
    ├── TROUBLESHOOTING_METHOD.md
    ├── COMMAND_CHEATSHEET.md
    ├── SECURITY.md
    └── CONTRIBUTING.md
```

Prefer minimal runtime dependencies. `pytest` as a development dependency is acceptable. Use `uv` for developing the project, but ensure the tool can diagnose a machine without `uv` installed.

## 11. Security and privacy requirements

- No outbound telemetry, update checks, or model calls in MVP.
- No admin rights required.
- Do not read `.env`, credentials, SSH keys, token stores, browser data, or pip config secrets.
- Treat diagnostic output and error strings as untrusted input; redact before saving/sharing.
- Never construct subprocess commands with `shell=True` or interpolate student-provided strings into a shell command.
- Bound subprocess time and output size; gracefully handle missing executables and permissions.
- Avoid following symlinks outside the chosen project root when scanning project files.
- A `--share` report must use allowlisted fields, replace sensitive paths, and show a preview before export.
- Do not claim redaction is perfect; advise manual review.
- Any future `fix` command must require a separate explicit design and approval process.

## 12. Testing and quality gates

**Unit tests:** environment classification, path normalization, package/import-name distinction, evidence-to-finding rules, redaction, JSON schema, scenario scoring.

**Integration tests:** isolated temporary projects and virtual environments; subprocess timeout/error handling; missing `uv`, missing `pip`, missing `.venv`, malformed metadata; Windows path behavior.

**CI matrix:** Windows, macOS, Linux; supported Python versions selected after verifying current AI Makerspace prerequisites. Avoid hard-coding an unverified required Python version.

**Required safety tests:**
- `scan` does not modify files or install dependencies.
- No API-key values or home-directory identifiers appear in `--share` output.
- Normal scans do not execute imports or user project entry points.
- A failed check returns `unknown` or a scoped error rather than a false definitive diagnosis.
- All commands are correctly quoted or presented for the user's shell.

## 13. Acceptance criteria

MVP is complete when:
1. A fresh clone can be installed and run following documented instructions on Windows, macOS, and Linux.
2. `scan`, `scan --json`, and `scan --share` produce consistent, schema-versioned output.
3. A mismatched interpreter scenario is flagged as a hypothesis with supporting path evidence, not asserted as proven root cause.
4. The tool identifies missing package metadata without silently installing anything.
5. A Jupyter kernelspec pointing to a missing executable is reported correctly.
6. All 10 knowledge cards and 10 practice scenarios work offline.
7. Reports never contain values of known secret-bearing variables.
8. Test suite and CI pass on supported platforms.
9. Documentation explains how to verify each proposed fix using the original failing command.
10. A beginner can run a scan and a peer supporter can interpret the report without needing an LLM.

## 14. Delivery plan

**Milestone A — Foundation:** repository, packaging, CLI, typed models, interpreter/project collectors, tests.

**Milestone B — Diagnosis:** package and `uv` checks, evidence-based rules, terminal/JSON renderers, sanitized reports.

**Milestone C — Teaching:** knowledge cards, interactive troubleshooting, first 10 practice fixtures, progress tracking.

**Milestone D — Hardening:** Windows/macOS/Linux validation, security review, documentation, sample outputs, release candidate.

Deliver each milestone as a separate reviewable PR. Do not merge or release automatically. Each PR must include tests, a change summary, and known limitations.

## 15. Instructions for Claude Code

You are implementing **Python Doctor** according to this specification. Work as a senior Python engineer and educator. Do not substitute an AI chatbot for the deterministic diagnostic engine.

**First response:**
1. Inspect the existing repository, if any; do not overwrite existing work.
2. Identify ambiguous requirements and propose conservative defaults.
3. Produce a concise implementation plan, package/dependency choices, and milestone breakdown.
4. Identify the five highest-risk technical assumptions and how you will test them.
5. Wait for explicit approval before making changes.

**After approval:**
- Implement Milestone A first, with tests and docs.
- Prefer small, reviewable commits/PRs.
- Explain decisions and tradeoffs, especially any commands that could execute untrusted code.
- Never claim tests passed unless actually run; report exact commands and results.
- Never fabricate diagnostic findings or suppress uncertainty.
- Do not add remote services, telemetry, or AI integrations without separate authorization.

## 16. Personal learning outcomes

After using the tool, the primary user should be able to independently answer:
- Which interpreter is actually running this code?
- Where does this interpreter look for modules?
- Which distribution supplies this import name?
- What does `uv run` change compared with direct `python` execution?
- Why might VS Code or Jupyter use a different interpreter?
- What evidence distinguishes a missing package from an interpreter mismatch?
- How can I explain the cause and verification step to a beginner?

**North-star metric:** Percentage of realistic scenarios diagnosed correctly, with a verified explanation and no AI assistance—not number of commands executed or fixes suggested.
