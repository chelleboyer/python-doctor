# Contributing

## Setup

```bash
uv sync
uv run pytest                       # everything
uv run pytest -m "not integration"  # fast unit tests
uv run python-doctor scan --verbose
```

Integration tests create real virtual environments. They use any `python3.X` they find on PATH, so installing a few versions (`uv python install 3.10 3.11 3.12`) widens coverage.

## Architecture

```
cli.py -> ScanContext.discover() -> collectors -> EvidenceSet -> rules -> Findings -> renderers
```

| Layer | May do | Must not do |
|---|---|---|
| `collectors/` | Read allowlisted files, call `shutil.which`, run probes via `proc.run_bounded` | Raise (return error evidence instead), read env var values, write anything |
| `rules/` | Pure functions over `EvidenceSet` | Any I/O. If a rule needs a fact, add a collector |
| `renderers/` | Format findings | Decide anything |

## Adding a collector fact

1. Pick a stable dotted `check_id` (`area.thing.attribute`). IDs are API: JSON consumers and rules depend on them. Never derive behavior from display text.
2. Values are `str`, `bool` or `None`. Stringify counts.
3. Set `sensitivity`: `path` for filesystem paths, `sensitive` for anything identifying (project names), otherwise `public`.
4. Write a unit test using a temp directory.

## Adding a rule

1. Write a function `rule_x(ev, ctx) -> list[Finding]` in `rules/` and add it to `RULES`.
2. Every finding cites the evidence it used (`ev.ids(...)` drops IDs that weren't collected). The engine rejects findings that cite missing evidence.
3. `status` is what was observed. Give a `hypothesis` only with a `confidence`. Confidence is about the hypothesis, not the observation.
4. Put blind spots in `limitations`. "This doesn't prove it causes your error" is the honest default for any path-difference finding.
5. **Never** conclude a mismatch from the presence of `.venv` alone. Compare observed prefixes or paths and say which basis you used.
6. Commands in `next_check` must paste correctly into bash, zsh, PowerShell and cmd. Use `shellfmt` helpers, only double quotes in `python -c` snippets, and no `$`, backticks or `%`.
7. Never suggest `pip install` / `uv add` from a scan-level finding. That needs the dependency declaration and the target interpreter inspected first (Milestone B).
8. Unit-test it with synthetic evidence (`tests/unit/test_rules.py`).

## Pull requests

One milestone or one concern per PR. Include tests, a change summary, and known limitations. Don't claim a platform works unless CI ran on it.
