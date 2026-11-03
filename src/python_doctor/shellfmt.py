"""Present commands so they paste correctly into the user's shell.

We never *run* these strings; they are shown to the user. Rules:

* Snippets passed to ``python -c`` use only double quotes and contain no ``$``,
  backticks or ``%``, so the same text works in bash, zsh, PowerShell and cmd.
* Paths are double-quoted. On Windows we show the PowerShell form
  (``& "C:\\path\\python.exe" ...``), which is the default terminal; the cmd.exe
  form is the same without the leading ``& ``.
"""

from __future__ import annotations

PRINT_PREFIX = 'python -c "import sys; print(sys.prefix)"'
PRINT_EXECUTABLE = 'python -c "import sys; print(sys.executable)"'


def with_command(snippet: str, command: str) -> str:
    """Swap the leading ``python`` in a snippet for ``command`` (e.g. python3)."""
    assert snippet.startswith("python ")
    return command + snippet[len("python"):]


def quote_path(path: str) -> str:
    if '"' in path:
        # Paths with double quotes are vanishingly rare and can't be quoted
        # portably. Present them raw and let the reader adapt.
        return path
    return f'"{path}"'


def invoke(path: str, args: str, platform: str) -> str:
    """Show how to run an executable at ``path`` with ``args``."""
    if platform == "win32":
        return f"& {quote_path(path)} {args}"
    return f"{quote_path(path)} {args}"


def activation_commands(venv_dir: str, platform: str) -> list[tuple[str, str]]:
    if platform == "win32":
        return [
            ("PowerShell", f"{venv_dir}\\Scripts\\Activate.ps1"),
            ("cmd.exe", f"{venv_dir}\\Scripts\\activate.bat"),
        ]
    return [("bash/zsh", f"source {venv_dir}/bin/activate")]
