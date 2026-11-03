# Security and privacy

Python Doctor runs on students' machines and produces reports that will be shared. This page lists what it does and doesn't do, and which test enforces each claim. If you find a gap, open an issue rather than a PR with a working exploit.

## Invariants

| Invariant | How | Enforced by |
|---|---|---|
| Never modifies files, installs, or deletes | No write calls anywhere in the scan path | `test_scan_does_not_modify_anything` (hashes the whole temp tree before/after) |
| No implicit code execution | Interpreter probes use `-I -S` (below); no imports of project modules; project entry points are never run | `test_scan_never_executes_project_code_or_pth_files` (planted `json.py`, `sysconfig.py`, `main.py` and a `.pth` file each write a marker if executed). Mutation-tested: removing `-I` or `-S` makes it fail. |
| No shell | All subprocesses go through `proc.run_bounded`: argv list, `shell=False`, stdin closed, timeout, output cap | `test_never_uses_shell`, `test_every_subprocess_is_a_safe_probe` (fails if `subprocess.run`/`os.system` is used anywhere during a scan) |
| `--no-probe` means no subprocesses | | `test_no_probe_starts_no_processes` |
| Environment variable **values** are never collected | Only presence flags for an allowlist. For `VIRTUAL_ENV`, comparisons are computed in memory and only booleans are stored | `test_env_values_never_reach_evidence` (seeds fake values, including an API-key-shaped one, then searches evidence and output for them) |
| Only allowlisted files are read | `pyproject.toml`, `.python-version`, `<venv>/pyvenv.cfg`. Never `.env`, credentials, SSH keys, pip config | `test_never_reads_dotenv` |
| No reads through symlinks out of the project | `paths.safe_read_text` resolves and checks containment | `test_safe_read_text_refuses_symlink_out_of_root` |
| Size limits on reads | 1 MB for `pyproject.toml`, 64 KB for `pyvenv.cfg`, 4 KB for `.python-version` | `test_safe_read_text_limits` |
| No network | No networking modules are imported | Review. *A test that blocks sockets during a scan is planned for Milestone D.* |
| Failures produce `unknown`, not guesses | Collector or rule crashes and invalid rule output become `unknown` findings | `test_engine_turns_rule_crash_into_unknown`, `test_broken_target_is_unknown_not_a_diagnosis` |

## The interpreter probe

To learn about an interpreter other than its own (`python` on PATH, or `--python`), Python Doctor runs:

```
<interpreter> -I -S -c "<one-line stdlib-only script>"
```

* `-I` (isolated mode) ignores `PYTHON*` environment variables and the user site directory, and keeps the current directory off `sys.path`. Without it, a student's `json.py` would be imported instead of the standard library's.
* `-S` skips `site`, which is what processes `.pth` files. `.pth` lines starting with `import` are executed, and packages ship them, so this is real code execution.
* **Consequence of `-S`:** `site` is also what moves `sys.prefix` onto a virtual environment. Under `-S`, a venv interpreter reports its *base* prefix. The probe re-applies `site.venv()`'s rule itself (a `pyvenv.cfg` beside the executable or one directory up) and reports both the effective `prefix` and the raw startup `raw_prefix`. `test_probe_sees_venv_even_though_site_is_skipped` guards this.
* It imports only `sys`, `os`, `json`, `sysconfig`. Because of `-I`, those come from the interpreter's standard library, not the project.
* Timeout 5 s, stdout/stderr capped at 16 KB, output parsed as JSON, and only known string fields kept.

**What the probe still trusts:** the interpreter binary itself. If the file on PATH called `python` is malicious, running it with any arguments runs it. That is the same trust the student extends every time they type `python`. Use `--no-probe` to avoid it entirely, at the cost of PATH-location-only evidence (findings drop to `medium` confidence and say why).

**Windows Store alias.** `...\WindowsApps\python.exe` is detected by path and never executed, because running it can open the Microsoft Store.

## Output

The terminal report is for the person at the keyboard and shows real paths. **It is not safe to paste publicly.** The sanitized `--share` report (allowlisted fields, home/username/hostname replacement, preview before export) is Milestone B. Redaction will be best-effort, and the tool will say so.

Evidence records carry a `sensitivity` of `public`, `path` or `sensitive` (for example, the project name) so the sanitizer can apply an allowlist rather than guessing.

## Future commands

`check import` (Milestone B) executes a module's import-time code. It will require `--allow-import-execution` or an interactive yes, refuse when stdin isn't a terminal, run in a subprocess with a timeout, and warn first. Any `fix` command needs a separate design and approval and is out of scope for the MVP.
