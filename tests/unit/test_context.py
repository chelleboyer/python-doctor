from pathlib import Path

from python_doctor.context import ScanContext, find_project_root


def test_finds_nearest_marker(tmp_path: Path):
    root = tmp_path / "proj"
    deep = root / "src" / "pkg"
    deep.mkdir(parents=True)
    (root / "pyproject.toml").write_text("")
    (root / "uv.lock").write_text("")
    found, markers = find_project_root(deep, stop_at=tmp_path)
    assert found == root
    assert markers == ("pyproject.toml", "uv.lock")


def test_stops_at_home(tmp_path: Path):
    # A marker *above* home must not be picked up.
    (tmp_path / "requirements.txt").write_text("")
    home = tmp_path / "home"
    cwd = home / "scratch"
    cwd.mkdir(parents=True)
    assert find_project_root(cwd, stop_at=home) == (None, ())


def test_home_itself_is_checked(tmp_path: Path):
    home = tmp_path / "home"
    (home / "work").mkdir(parents=True)
    (home / ".git").mkdir()
    assert find_project_root(home / "work", stop_at=home)[0] == home


def test_explicit_project_overrides_walk(tmp_path: Path):
    other = tmp_path / "other"
    other.mkdir()
    (other / "setup.cfg").write_text("")
    ctx = ScanContext.discover(cwd=tmp_path, project=other, home=tmp_path)
    assert ctx.project_root == other.absolute()
    assert ctx.root_markers == ("setup.cfg",)


def test_no_project(tmp_path: Path):
    ctx = ScanContext.discover(cwd=tmp_path, home=tmp_path)
    assert ctx.project_root is None and ctx.root_markers == ()
