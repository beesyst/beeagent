from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
import yaml

from beeagent_module.cli.auth import ensure_auth_env

AUTH_ENABLED_YAML = """
web:
  auth:
    enabled: true
    mode: beeui_session
    session_secret_env: BEEAGENT_WEB_SESSION_SECRET
    principals:
      - id: admin_1
        username: admin1
        role: admin
        token_env: BEEAGENT_WEB_ADMIN1_TOKEN
      - id: admin_2
        username: admin2
        role: admin
        token_env: BEEAGENT_WEB_ADMIN2_TOKEN
"""

AUTH_DISABLED_YAML = """
web:
  auth:
    enabled: false
    mode: beeui_session
    session_secret_env: BEEAGENT_WEB_SESSION_SECRET
    principals:
      - id: admin_1
        username: admin1
        role: admin
        token_env: BEEAGENT_WEB_ADMIN1_TOKEN
      - id: admin_2
        username: admin2
        role: admin
        token_env: BEEAGENT_WEB_ADMIN2_TOKEN
"""

SESSION_ENV = "BEEAGENT_WEB_SESSION_SECRET"
ADMIN1_ENV = "BEEAGENT_WEB_ADMIN1_TOKEN"
ADMIN2_ENV = "BEEAGENT_WEB_ADMIN2_TOKEN"


@pytest.fixture
def enabled_project(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config = yaml.safe_load(AUTH_ENABLED_YAML)
    (config_dir / "settings.yml").write_text(yaml.safe_dump(config), encoding="utf-8")
    return tmp_path


@pytest.fixture
def disabled_project(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config = yaml.safe_load(AUTH_DISABLED_YAML)
    (config_dir / "settings.yml").write_text(yaml.safe_dump(config), encoding="utf-8")
    return tmp_path


def _env_path(project_root: Path) -> Path:
    return project_root / ".env"


def _settings_path(project_root: Path) -> Path:
    return project_root / "config" / "settings.yml"


def _env_map(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _clear_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(SESSION_ENV, raising=False)
    monkeypatch.delenv(ADMIN1_ENV, raising=False)
    monkeypatch.delenv(ADMIN2_ENV, raising=False)


def test_auth_disabled_returns_empty_and_does_not_create_env(
    disabled_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_auth_env(monkeypatch)

    generated = ensure_auth_env(
        project_root=disabled_project,
        settings_path=_settings_path(disabled_project),
        env_path=_env_path(disabled_project),
        quiet=True,
    )

    assert generated == {}
    assert not _env_path(disabled_project).exists()


def test_auth_enabled_creates_missing_env_values(
    enabled_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_auth_env(monkeypatch)

    generated = ensure_auth_env(
        project_root=enabled_project,
        settings_path=_settings_path(enabled_project),
        env_path=_env_path(enabled_project),
        quiet=True,
    )

    env_map = _env_map(_env_path(enabled_project))
    assert set(generated) == {SESSION_ENV, ADMIN1_ENV, ADMIN2_ENV}
    assert env_map[SESSION_ENV] == generated[SESSION_ENV]
    assert env_map[ADMIN1_ENV] == generated[ADMIN1_ENV]
    assert env_map[ADMIN2_ENV] == generated[ADMIN2_ENV]


def test_existing_values_are_preserved_by_default(
    enabled_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_auth_env(monkeypatch)
    _env_path(enabled_project).write_text(
        "\n".join(
            [
                f"{SESSION_ENV}=existing-session",
                f"{ADMIN1_ENV}=existing-admin1",
                f"{ADMIN2_ENV}=existing-admin2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    generated = ensure_auth_env(
        project_root=enabled_project,
        settings_path=_settings_path(enabled_project),
        env_path=_env_path(enabled_project),
        quiet=True,
    )

    assert generated == {}
    assert _env_map(_env_path(enabled_project)) == {
        SESSION_ENV: "existing-session",
        ADMIN1_ENV: "existing-admin1",
        ADMIN2_ENV: "existing-admin2",
    }


def test_empty_env_values_are_replaced(
    enabled_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_auth_env(monkeypatch)
    _env_path(enabled_project).write_text(
        "\n".join([f"{SESSION_ENV}=", f"{ADMIN1_ENV}=", f"{ADMIN2_ENV}="]) + "\n",
        encoding="utf-8",
    )

    generated = ensure_auth_env(
        project_root=enabled_project,
        settings_path=_settings_path(enabled_project),
        env_path=_env_path(enabled_project),
        quiet=True,
    )

    env_map = _env_map(_env_path(enabled_project))
    assert env_map[SESSION_ENV] == generated[SESSION_ENV]
    assert env_map[ADMIN1_ENV] == generated[ADMIN1_ENV]
    assert env_map[ADMIN2_ENV] == generated[ADMIN2_ENV]


def test_rotate_admin1_changes_only_admin1(
    enabled_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_auth_env(monkeypatch)
    _env_path(enabled_project).write_text(
        "\n".join(
            [
                f"{SESSION_ENV}=session-old",
                f"{ADMIN1_ENV}=admin1-old",
                f"{ADMIN2_ENV}=admin2-old",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    generated = ensure_auth_env(
        project_root=enabled_project,
        settings_path=_settings_path(enabled_project),
        env_path=_env_path(enabled_project),
        rotate="admin1",
        quiet=True,
    )

    env_map = _env_map(_env_path(enabled_project))
    assert set(generated) == {ADMIN1_ENV}
    assert env_map[SESSION_ENV] == "session-old"
    assert env_map[ADMIN2_ENV] == "admin2-old"
    assert env_map[ADMIN1_ENV] == generated[ADMIN1_ENV]
    assert env_map[ADMIN1_ENV] != "admin1-old"


def test_rotate_admin2_changes_only_admin2(
    enabled_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_auth_env(monkeypatch)
    _env_path(enabled_project).write_text(
        "\n".join(
            [
                f"{SESSION_ENV}=session-old",
                f"{ADMIN1_ENV}=admin1-old",
                f"{ADMIN2_ENV}=admin2-old",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    generated = ensure_auth_env(
        project_root=enabled_project,
        settings_path=_settings_path(enabled_project),
        env_path=_env_path(enabled_project),
        rotate="admin2",
        quiet=True,
    )

    env_map = _env_map(_env_path(enabled_project))
    assert set(generated) == {ADMIN2_ENV}
    assert env_map[SESSION_ENV] == "session-old"
    assert env_map[ADMIN1_ENV] == "admin1-old"
    assert env_map[ADMIN2_ENV] == generated[ADMIN2_ENV]
    assert env_map[ADMIN2_ENV] != "admin2-old"


def test_rotate_session_changes_only_session(
    enabled_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_auth_env(monkeypatch)
    _env_path(enabled_project).write_text(
        "\n".join(
            [
                f"{SESSION_ENV}=session-old",
                f"{ADMIN1_ENV}=admin1-old",
                f"{ADMIN2_ENV}=admin2-old",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    generated = ensure_auth_env(
        project_root=enabled_project,
        settings_path=_settings_path(enabled_project),
        env_path=_env_path(enabled_project),
        rotate="session",
        quiet=True,
    )

    env_map = _env_map(_env_path(enabled_project))
    assert set(generated) == {SESSION_ENV}
    assert env_map[ADMIN1_ENV] == "admin1-old"
    assert env_map[ADMIN2_ENV] == "admin2-old"
    assert env_map[SESSION_ENV] == generated[SESSION_ENV]
    assert env_map[SESSION_ENV] != "session-old"


def test_rotate_all_changes_all_auth_values(
    enabled_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_auth_env(monkeypatch)
    _env_path(enabled_project).write_text(
        "\n".join(
            [
                f"{SESSION_ENV}=session-old",
                f"{ADMIN1_ENV}=admin1-old",
                f"{ADMIN2_ENV}=admin2-old",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    generated = ensure_auth_env(
        project_root=enabled_project,
        settings_path=_settings_path(enabled_project),
        env_path=_env_path(enabled_project),
        rotate="all",
        quiet=True,
    )

    env_map = _env_map(_env_path(enabled_project))
    assert set(generated) == {SESSION_ENV, ADMIN1_ENV, ADMIN2_ENV}
    assert env_map[SESSION_ENV] == generated[SESSION_ENV]
    assert env_map[ADMIN1_ENV] == generated[ADMIN1_ENV]
    assert env_map[ADMIN2_ENV] == generated[ADMIN2_ENV]
    assert env_map[SESSION_ENV] != "session-old"
    assert env_map[ADMIN1_ENV] != "admin1-old"
    assert env_map[ADMIN2_ENV] != "admin2-old"


def test_unsupported_rotate_target_raises(
    enabled_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_auth_env(monkeypatch)

    with pytest.raises(RuntimeError, match="Unsupported rotate target"):
        ensure_auth_env(
            project_root=enabled_project,
            settings_path=_settings_path(enabled_project),
            env_path=_env_path(enabled_project),
            rotate="nope",
            quiet=True,
        )


def test_env_chmod_is_0600_on_posix(
    enabled_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_auth_env(monkeypatch)

    ensure_auth_env(
        project_root=enabled_project,
        settings_path=_settings_path(enabled_project),
        env_path=_env_path(enabled_project),
        quiet=True,
    )

    if os.name == "posix":
        mode = stat.S_IMODE(_env_path(enabled_project).stat().st_mode)
        assert mode == (stat.S_IRUSR | stat.S_IWUSR)


def test_generated_values_are_not_written_to_logs_or_storage(
    enabled_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_auth_env(monkeypatch)
    (enabled_project / "logs").mkdir()
    (enabled_project / "storage").mkdir()

    generated = ensure_auth_env(
        project_root=enabled_project,
        settings_path=_settings_path(enabled_project),
        env_path=_env_path(enabled_project),
        quiet=True,
    )

    logs_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (enabled_project / "logs").rglob("*")
        if path.is_file()
    )
    storage_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (enabled_project / "storage").rglob("*")
        if path.is_file()
    )

    for value in generated.values():
        assert value not in logs_text
        assert value not in storage_text
