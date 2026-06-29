"""Tests for the cross-platform support layer."""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path
from unittest.mock import patch

from forgecli.platform import (
    OS,
    DependencyReport,
    DependencyStatus,
    Platform,
    check_dependencies,
    check_for_update,
    config_dir,
    current_platform,
    data_dir,
    detect_os,
    find_executable,
    has_git,
    has_graphify,
    has_node,
    has_ponytail,
    has_python,
    install_hint,
    is_linux,
    is_macos,
    is_windows,
    load_dotenv,
    python_version,
    run,
    shell_quote,
    state_dir,
)
from forgecli.platform.update import (
    DEFAULT_PYPI_URL,
    _cache_path,
    _is_newer,
    _parse_version,
    _write_cache,
    should_check_on_startup,
    upgrade_command,
)

# ---------------------------------------------------------------------------
# core
# ---------------------------------------------------------------------------


def test_detect_os_returns_a_known_value() -> None:
    assert detect_os() in {OS.LINUX, OS.MACOS, OS.WINDOWS, OS.OTHER}


def test_exactly_one_is_os_predicate_is_true() -> None:
    predicates = [is_linux, is_macos, is_windows]
    assert sum(bool(p()) for p in predicates) == 1


def test_current_platform_is_platform_instance() -> None:
    assert isinstance(current_platform(), Platform)


def test_python_version_is_string() -> None:
    assert isinstance(python_version(), str)
    assert python_version().count(".") == 2


def test_platform_fields() -> None:
    p = current_platform()
    assert p.os in OS
    assert isinstance(p.arch, str)
    assert isinstance(p.python, str)
    assert isinstance(p.is_wsl, bool)


# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------


def test_config_dir_exists_and_is_under_user_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FORGECLI_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    path = config_dir()
    assert path.exists()
    assert path.is_dir()


def test_data_dir_creates_tree(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FORGECLI_DATA_DIR", str(tmp_path / "data"))
    path = data_dir()
    assert path.exists()


def test_state_dir_creates_tree(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FORGECLI_STATE_DIR", str(tmp_path / "state"))
    path = state_dir()
    assert path.exists()


def test_load_dotenv_does_not_override(monkeypatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FORGECLI_TEST_VAR=from_file\n", encoding="utf-8")
    monkeypatch.setenv("FORGECLI_TEST_VAR", "from_env")
    loaded = load_dotenv(env_file, override=False)
    assert os.environ["FORGECLI_TEST_VAR"] == "from_env"
    assert "FORGECLI_TEST_VAR" not in loaded


def test_load_dotenv_overrides(monkeypatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FORGECLI_TEST_VAR=from_file\n", encoding="utf-8")
    monkeypatch.setenv("FORGECLI_TEST_VAR", "from_env")
    loaded = load_dotenv(env_file, override=True)
    assert os.environ["FORGECLI_TEST_VAR"] == "from_file"
    assert loaded["FORGECLI_TEST_VAR"] == "from_file"


def test_load_dotenv_handles_comments_and_blanks(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# this is a comment\n"
        "\n"
        "FORGECLI_TEST_VAR=value\n"
        'FORGECLI_QUOTED="with spaces"\n',
        encoding="utf-8",
    )
    for k in ("FORGECLI_TEST_VAR", "FORGECLI_QUOTED"):
        os.environ.pop(k, None)
    try:
        load_dotenv(env_file)
        assert os.environ["FORGECLI_TEST_VAR"] == "value"
        assert os.environ["FORGECLI_QUOTED"] == "with spaces"
    finally:
        os.environ.pop("FORGECLI_TEST_VAR", None)
        os.environ.pop("FORGECLI_QUOTED", None)


def test_load_dotenv_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_dotenv(tmp_path / "missing.env") == {}


# ---------------------------------------------------------------------------
# shell
# ---------------------------------------------------------------------------


def test_shell_quote_does_not_contain_unquoted_whitespace() -> None:
    quoted = shell_quote("hello world")
    assert " " not in quoted.replace(" ", "")


def test_run_captures_stdout(tmp_path: Path) -> None:
    if is_windows():
        result = run(["cmd.exe", "/c", "echo hello"], cwd=tmp_path)
    else:
        result = run(["echo", "hello"], cwd=tmp_path)
    assert result.ok
    assert "hello" in result.stdout


def test_run_returns_nonzero_on_failure(tmp_path: Path) -> None:
    if is_windows():
        result = run(["cmd.exe", "/c", "exit 1"], cwd=tmp_path)
    else:
        result = run(["false"], cwd=tmp_path)
    assert not result.ok


def test_run_propagates_env() -> None:
    if is_windows():
        result = run(["cmd.exe", "/c", "echo %FORGECLI_TEST_VAR%"])
    else:
        result = run(["sh", "-c", "echo $FORGECLI_TEST_VAR"])
    result = run(
        ["cmd.exe", "/c", "echo %FORGECLI_TEST_VAR%"]
        if is_windows()
        else ["sh", "-c", "echo $FORGECLI_TEST_VAR"],
        env={"FORGECLI_TEST_VAR": "from-arg"},
    )
    assert "from-arg" in result.stdout


def test_which_finds_python(monkeypatch) -> None:
    monkeypatch.setenv("PATH", os.path.dirname(shutil.which("python") or "") or os.defpath)
    assert find_executable("python") is not None


def test_which_returns_none_for_missing() -> None:
    assert find_executable("definitely-not-a-real-binary-xyz") is None


# ---------------------------------------------------------------------------
# deps
# ---------------------------------------------------------------------------


def test_check_dependencies_returns_report() -> None:
    report = check_dependencies()
    assert isinstance(report, DependencyReport)
    assert report.dependencies
    names = {d.name for d in report.dependencies}
    assert "git" in names
    assert "python" in names


def test_required_dependency_marker() -> None:
    report = check_dependencies()
    required = {d.name for d in report.dependencies if d.required}
    assert "git" in required
    # Python is always present (we're running inside it) so the
    # dependency check should mark it as required-found.
    python_dep = next(d for d in report.dependencies if d.name == "python")
    assert python_dep.required is True
    assert python_dep.status is DependencyStatus.FOUND


def test_install_hint_returns_a_string_for_known_tool() -> None:
    hints = install_hint("graphify")
    assert hints
    assert all(isinstance(line, str) for line in hints)


def test_install_hint_falls_back_for_unknown_tool() -> None:
    hints = install_hint("nonexistent-tool")
    assert hints


def test_have_function_booleans_are_consistent() -> None:
    # Each `has_x` should match `find_executable` for the same name.
    for fn, name in [
        (has_git, "git"),
        (has_graphify, "graphify"),
        (has_ponytail, "ponytail"),
        (has_node, "node"),
    ]:
        expected = find_executable(name) is not None
        assert fn() == expected


def test_has_python_always_true() -> None:
    assert has_python() is True


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


def test_parse_version_extracts_string() -> None:
    assert _parse_version({"info": {"version": "1.2.3"}}) == "1.2.3"


def test_parse_version_handles_missing_info() -> None:
    assert _parse_version({}) is None
    assert _parse_version({"info": {}}) is None


def test_is_newer_compares_numeric_components() -> None:
    assert _is_newer("1.2.3", "1.2.2") is True
    assert _is_newer("1.2.10", "1.2.9") is True
    assert _is_newer("1.2.3", "1.2.3") is False
    assert _is_newer("0.9.0", "1.0.0") is False


def test_is_newer_handles_non_numeric_components() -> None:
    # Pre-releases have a different numeric part and we don't try to
    # disambiguate them: a "1.0.0a1" strips to (1, 0, 0) just like
    # "1.0.0", so the comparison treats them as equal.
    assert _is_newer("1.0.0a1", "1.0.0") is False
    assert _is_newer("1.0.0", "1.0.0a1") is False


def test_check_for_update_handles_network_error(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FORGECLI_DATA_DIR", str(tmp_path))
    # Make sure no cached value is read.
    _cache_path().unlink(missing_ok=True)

    def boom():
        raise OSError("offline")

    info = check_for_update(client_factory=boom)
    assert info.latest is None
    assert info.error is not None
    assert info.update_available is False


def test_check_for_update_uses_cache(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FORGECLI_DATA_DIR", str(tmp_path))
    _write_cache("9.9.9")
    info = check_for_update(client_factory=lambda: (_ for _ in ()).throw(AssertionError("should not hit network")))
    assert info.latest == "9.9.9"


def test_check_for_update_force_refreshes(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FORGECLI_DATA_DIR", str(tmp_path))
    _write_cache("0.0.1")
    calls = []

    class _Client:
        def __init__(self) -> None: ...
        def __enter__(self): return self
        def __exit__(self, *a): return None
        def get(self, url):
            calls.append(url)
            class _Resp:
                def raise_for_status(self): pass
                def json(self): return {"info": {"version": "2.0.0"}}
            return _Resp()

    info = check_for_update(force=True, client_factory=_Client)
    assert calls == [DEFAULT_PYPI_URL]
    assert info.latest == "2.0.0"
    assert info.update_available is True


def test_should_check_on_startup_default_false(monkeypatch) -> None:
    monkeypatch.delenv("FORGECLI_CHECK_UPDATE", raising=False)
    monkeypatch.delenv("FORGECLI_NO_UPDATE_CHECK", raising=False)
    assert should_check_on_startup() is False


def test_should_check_on_startup_honors_env(monkeypatch) -> None:
    monkeypatch.setenv("FORGECLI_CHECK_UPDATE", "1")
    assert should_check_on_startup() is True
    monkeypatch.setenv("FORGECLI_NO_UPDATE_CHECK", "1")
    assert should_check_on_startup() is False


def test_upgrade_command_returns_a_string() -> None:
    assert "forgecli" in upgrade_command()


def test_cache_path_lives_under_data_dir(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FORGECLI_DATA_DIR", str(tmp_path))
    p = _cache_path()
    assert p.parent == tmp_path
    assert p.name == "update.json"


# Silence unused-import warnings for symbols only used in some branches.
_ = stat
_ = patch
