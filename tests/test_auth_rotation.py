from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

import pytest
import yaml

from beeagent_module.cli.auth import (
    _available_principals,
    _do_rotate,
    _find_principal,
    _read_auth_config,
    _read_env_lines,
    _update_env_file,
    ensure_web_auth_env,
    handle_auth_cli,
)

SAMPLE_YAML = """
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
bitrix:
  widget:
    enabled: false
    token_env: BITRIX_ROP_WIDGET_TOKEN
    default_period: "7d"
    max_items: 50
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

SESSION_SECRET_ENV_NAME = "BEEAGENT_WEB_SESSION_SECRET"
ADMIN1_ENV = "BEEAGENT_WEB_ADMIN1_TOKEN"
ADMIN2_ENV = "BEEAGENT_WEB_ADMIN2_TOKEN"
WIDGET_ENV = "BITRIX_ROP_WIDGET_TOKEN"
PRINCIPAL_TOKEN_ENVS = [ADMIN1_ENV, ADMIN2_ENV]

UNRELATED_ENV = (
    "TELEGRAM_BOT_TOKEN=bot123\nCHAT_ID=chat456\nOPENAI_API_KEY=sk-old-key\n"
)

INITIAL_ENV = (
    f"{UNRELATED_ENV}"
    f"# BeeAgent web auth\n"
    f"{SESSION_SECRET_ENV_NAME}=old-session-secret\n"
    f"{ADMIN1_ENV}=old-token-1\n"
    f"{ADMIN2_ENV}=old-token-2\n"
    f"{WIDGET_ENV}=old-widget-token\n"
)


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    raw = yaml.safe_load(SAMPLE_YAML)
    (cfg_dir / "settings.yml").write_text(yaml.dump(raw), encoding="utf-8")
    env = tmp_path / ".env"
    env.write_text(INITIAL_ENV.strip() + "\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def tmp_project_no_env(tmp_path: Path) -> Path:
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    raw = yaml.safe_load(SAMPLE_YAML)
    (cfg_dir / "settings.yml").write_text(yaml.dump(raw), encoding="utf-8")
    return tmp_path


@pytest.fixture
def tmp_project_auth_disabled(tmp_path: Path) -> Path:
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    raw = yaml.safe_load(AUTH_DISABLED_YAML)
    (cfg_dir / "settings.yml").write_text(yaml.dump(raw), encoding="utf-8")
    return tmp_path


@pytest.fixture
def tmp_project_with_empty_env(tmp_path: Path) -> Path:
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    raw = yaml.safe_load(SAMPLE_YAML)
    (cfg_dir / "settings.yml").write_text(yaml.dump(raw), encoding="utf-8")
    env_content = (
        f"{UNRELATED_ENV}{SESSION_SECRET_ENV_NAME}=\n"
        f"{ADMIN1_ENV}=\n{ADMIN2_ENV}=\n{WIDGET_ENV}=\n"
    )
    env = tmp_path / ".env"
    env.write_text(env_content, encoding="utf-8")
    return tmp_path


@pytest.fixture
def auth_cfg() -> dict[str, Any]:
    return yaml.safe_load(SAMPLE_YAML)["web"]["auth"]


@pytest.fixture
def auth_disabled_cfg() -> dict[str, Any]:
    return yaml.safe_load(AUTH_DISABLED_YAML)["web"]["auth"]


class TestReadAuthConfig:
    def test_reads_auth_config(self, tmp_project: Path) -> None:
        cfg = _read_auth_config(tmp_project / "config" / "settings.yml")
        assert cfg is not None
        assert cfg["session_secret_env"] == SESSION_SECRET_ENV_NAME
        assert len(cfg["principals"]) == 2

    def test_returns_none_on_missing_file(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope.yml"
        assert _read_auth_config(missing) is None

    def test_returns_empty_on_no_web_key(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config"
        cfg.mkdir()
        (cfg / "settings.yml").write_text("app:\n  name: test\n", encoding="utf-8")
        result = _read_auth_config(cfg / "settings.yml")
        assert result is not None
        assert result["session_secret_env"] is None
        assert result["principals"] == []


class TestFindPrincipal:
    def test_find_by_id(self, auth_cfg: dict) -> None:
        p = _find_principal(auth_cfg["principals"], "admin_1")
        assert p is not None
        assert p["id"] == "admin_1"

    def test_find_by_username(self, auth_cfg: dict) -> None:
        p = _find_principal(auth_cfg["principals"], "admin1")
        assert p is not None
        assert p["id"] == "admin_1"

    def test_returns_none_for_unknown(self, auth_cfg: dict) -> None:
        assert _find_principal(auth_cfg["principals"], "nobody") is None


class TestAvailablePrincipals:
    def test_lists_ids_and_usernames(self, auth_cfg: dict) -> None:
        lines = _available_principals(auth_cfg["principals"])
        assert len(lines) == 2
        assert all("id=" in l and "username=" in l for l in lines)

    def test_handles_non_dict_items(self) -> None:
        assert _available_principals([None, "x", 42]) == []


class TestEnvFileHandling:
    def test_read_env_lines_returns_list(self, tmp_project: Path) -> None:
        lines = _read_env_lines(tmp_project / ".env")
        assert isinstance(lines, list)
        assert len(lines) > 0

    def test_read_env_lines_returns_empty_list_if_missing(self, tmp_path: Path) -> None:
        lines = _read_env_lines(tmp_path / ".env")
        assert lines == []

    def test_update_env_file_preserves_unrelated_values(
        self, tmp_project: Path
    ) -> None:
        env_path = tmp_project / ".env"
        lines = _read_env_lines(env_path)
        _update_env_file(env_path, lines, {"BEEAGENT_WEB_ADMIN1_TOKEN": "new-val"})
        content = env_path.read_text(encoding="utf-8")
        assert "TELEGRAM_BOT_TOKEN=bot123" in content
        assert "new-val" in content
        assert "old-token-1" not in content

    def test_update_env_file_creates_file_if_missing(
        self, tmp_project_no_env: Path
    ) -> None:
        env_path = tmp_project_no_env / ".env"
        assert not env_path.exists()
        _update_env_file(env_path, [], {"BEEAGENT_WEB_ADMIN1_TOKEN": "new-token"})
        assert env_path.exists()
        content = env_path.read_text(encoding="utf-8")
        assert "BEEAGENT_WEB_ADMIN1_TOKEN=new-token" in content

    def test_update_env_file_sets_posix_permissions(self, tmp_project: Path) -> None:
        env_path = tmp_project / ".env"
        lines = _read_env_lines(env_path)
        _update_env_file(env_path, lines, {"BEEAGENT_WEB_ADMIN1_TOKEN": "new-val"})
        if os.name == "posix":
            mode = stat.S_IMODE(env_path.stat().st_mode)
            assert mode == (stat.S_IRUSR | stat.S_IWUSR)

    def test_update_env_file_updates_empty_key_in_place(self, tmp_path: Path) -> None:
        env_path = tmp_path / ".env"
        env_path.write_text(
            "BEEAGENT_WEB_ADMIN1_TOKEN=\nBEEAGENT_WEB_ADMIN2_TOKEN=old-val\n",
            encoding="utf-8",
        )
        lines = _read_env_lines(env_path)
        _update_env_file(env_path, lines, {"BEEAGENT_WEB_ADMIN1_TOKEN": "new-val"})
        content = env_path.read_text(encoding="utf-8")
        assert "BEEAGENT_WEB_ADMIN1_TOKEN=new-val" in content
        assert "BEEAGENT_WEB_ADMIN2_TOKEN=old-val" in content
        lines_in_file = [
            l for l in content.splitlines() if l.startswith("BEEAGENT_WEB_ADMIN1_TOKEN")
        ]
        assert len(lines_in_file) == 1


class TestRotateSingle:
    def test_rotate_by_id_changes_only_that_token(
        self, tmp_project: Path, auth_cfg: dict
    ) -> None:
        env_path = tmp_project / ".env"
        _do_rotate(auth_cfg, tmp_project, "admin_1", logout_all=False)
        content = env_path.read_text(encoding="utf-8")
        lines = [
            l.strip()
            for l in content.splitlines()
            if l.strip() and not l.strip().startswith("#")
        ]
        env_map: dict[str, str] = {}
        for line in lines:
            if "=" in line:
                k, v = line.split("=", 1)
                env_map[k.strip()] = v.strip()
        assert env_map["BEEAGENT_WEB_ADMIN1_TOKEN"] != "old-token-1"
        assert env_map["BEEAGENT_WEB_ADMIN2_TOKEN"] == "old-token-2"
        assert env_map["BEEAGENT_WEB_SESSION_SECRET"] == "old-session-secret"

    def test_rotate_by_username_works(self, tmp_project: Path, auth_cfg: dict) -> None:
        env_path = tmp_project / ".env"
        _do_rotate(auth_cfg, tmp_project, "admin1", logout_all=False)
        content = env_path.read_text(encoding="utf-8")
        assert "old-token-1" not in content
        assert "old-token-2" in content

    def test_unknown_principal_returns_error(
        self, tmp_project: Path, auth_cfg: dict
    ) -> None:
        code = _do_rotate(auth_cfg, tmp_project, "nobody", logout_all=False)
        assert code == 1

    def test_unknown_principal_lists_available(
        self, tmp_project: Path, auth_cfg: dict, capsys: Any
    ) -> None:
        _do_rotate(auth_cfg, tmp_project, "nobody", logout_all=False)
        stderr = capsys.readouterr().err
        assert "admin_1" in stderr
        assert "admin1" in stderr
        assert "admin_2" in stderr
        assert "admin2" in stderr
        assert "old-token" not in stderr

    def test_principal_token_printed_to_stdout(
        self, tmp_project: Path, auth_cfg: dict, capsys: Any
    ) -> None:
        _do_rotate(auth_cfg, tmp_project, "admin_1", logout_all=False)
        stdout = capsys.readouterr().out
        token_line = stdout.splitlines()[0]
        assert len(token_line) > 10
        assert "Restart required" in stdout


class TestRotateAll:
    def test_rotate_all_changes_all_tokens(
        self, tmp_project: Path, auth_cfg: dict
    ) -> None:
        env_path = tmp_project / ".env"
        _do_rotate(auth_cfg, tmp_project, "all", logout_all=False)
        content = env_path.read_text(encoding="utf-8")
        assert "old-token-1" not in content
        assert "old-token-2" not in content
        assert "old-session-secret" in content

    def test_rotate_all_does_not_change_session_secret_by_default(
        self, tmp_project: Path, auth_cfg: dict
    ) -> None:
        env_path = tmp_project / ".env"
        _do_rotate(auth_cfg, tmp_project, "all", logout_all=False)
        content = env_path.read_text(encoding="utf-8")
        assert "old-session-secret" in content

    def test_rotate_all_does_not_change_widget_token(
        self, tmp_project: Path, auth_cfg: dict
    ) -> None:
        env_path = tmp_project / ".env"
        _do_rotate(auth_cfg, tmp_project, "all", logout_all=False)
        content = env_path.read_text(encoding="utf-8")
        assert "old-widget-token" in content

    def test_rotate_all_logout_all_changes_everything(
        self, tmp_project: Path, auth_cfg: dict
    ) -> None:
        env_path = tmp_project / ".env"
        _do_rotate(auth_cfg, tmp_project, "all", logout_all=True)
        content = env_path.read_text(encoding="utf-8")
        assert "old-token-1" not in content
        assert "old-token-2" not in content
        assert "old-session-secret" not in content

    def test_rotate_all_prints_tokens_with_usernames(
        self, tmp_project: Path, auth_cfg: dict, capsys: Any
    ) -> None:
        _do_rotate(auth_cfg, tmp_project, "all", logout_all=False)
        stdout = capsys.readouterr().out
        lines = [l for l in stdout.splitlines() if "Restart" not in l]
        assert len(lines) == 2
        assert all(": " in l for l in lines)
        assert "admin1:" in stdout
        assert "admin2:" in stdout

    def test_rotate_all_logout_all_does_not_print_session_secret(
        self, tmp_project: Path, auth_cfg: dict, capsys: Any
    ) -> None:
        _do_rotate(auth_cfg, tmp_project, "all", logout_all=True)
        stdout = capsys.readouterr().out
        secret = _env_value_from_file(tmp_project / ".env", SESSION_SECRET_ENV_NAME)
        assert secret not in stdout


class TestRotateSession:
    def test_rotate_session_changes_only_session_secret(
        self, tmp_project: Path, auth_cfg: dict
    ) -> None:
        env_path = tmp_project / ".env"
        _do_rotate(auth_cfg, tmp_project, "session", logout_all=False)
        content = env_path.read_text(encoding="utf-8")
        assert "old-session-secret" not in content
        assert "old-token-1" in content
        assert "old-token-2" in content

    def test_rotate_session_does_not_print_secret_value(
        self, tmp_project: Path, auth_cfg: dict, capsys: Any
    ) -> None:
        _do_rotate(auth_cfg, tmp_project, "session", logout_all=False)
        stdout = capsys.readouterr().out
        secret = _env_value_from_file(tmp_project / ".env", SESSION_SECRET_ENV_NAME)
        assert secret not in stdout
        assert "Warning" in stdout


class TestRotateBitrixWidget:
    def test_rotate_bitrix_widget_changes_only_widget_token(
        self, tmp_project: Path, auth_cfg: dict
    ) -> None:
        env_path = tmp_project / ".env"
        cfg = {**auth_cfg, "widget_token_env": WIDGET_ENV}

        _do_rotate(cfg, tmp_project, "bitrix-widget", logout_all=False)

        content = env_path.read_text(encoding="utf-8")
        assert "old-widget-token" not in content
        assert "old-session-secret" in content
        assert "old-token-1" in content
        assert "old-token-2" in content

    def test_rotate_bitrix_widget_does_not_print_actual_token(
        self, tmp_project: Path, auth_cfg: dict, capsys: Any
    ) -> None:
        cfg = {**auth_cfg, "widget_token_env": WIDGET_ENV}

        _do_rotate(cfg, tmp_project, "bitrix-widget", logout_all=False)

        stdout = capsys.readouterr().out
        token = _env_value_from_file(tmp_project / ".env", WIDGET_ENV)
        assert token not in stdout
        assert f"{WIDGET_ENV}=<generated>" in stdout
        assert "Restart required for the running web app/widget API" in stdout

    def test_rotate_bitrix_widget_missing_token_env_fails(
        self, tmp_project: Path, auth_cfg: dict, capsys: Any
    ) -> None:
        cfg = dict(auth_cfg)

        code = _do_rotate(cfg, tmp_project, "bitrix-widget", logout_all=False)

        stderr = capsys.readouterr().err
        assert code == 1
        assert "Error: bitrix.widget.token_env is not configured" in stderr


class TestUnsupportedFlags:
    def test_logout_all_with_single_principal_fails(
        self, tmp_project: Path, auth_cfg: dict
    ) -> None:
        code = _do_rotate(auth_cfg, tmp_project, "admin1", logout_all=True)
        assert code == 1

    def test_logout_all_with_session_fails(
        self, tmp_project: Path, auth_cfg: dict
    ) -> None:
        code = _do_rotate(auth_cfg, tmp_project, "session", logout_all=True)
        assert code == 1

    def test_unknown_flag_fails(self, tmp_project: Path) -> None:
        code = handle_auth_cli(["rotate", "admin1", "--foo"], tmp_project)
        assert code == 2

    def test_unknown_flag_with_all_fails(self, tmp_project: Path) -> None:
        code = handle_auth_cli(["rotate", "all", "--foo"], tmp_project)
        assert code == 2


class TestHandleAuthCli:
    def test_auth_rotate_by_id(self, tmp_project: Path) -> None:
        handle_auth_cli(["rotate", "admin_1"], tmp_project)
        env_content = (tmp_project / ".env").read_text(encoding="utf-8")
        assert "old-token-1" not in env_content
        assert "old-token-2" in env_content

    def test_auth_rotate_all(self, tmp_project: Path) -> None:
        handle_auth_cli(["rotate", "all"], tmp_project)
        env_content = (tmp_project / ".env").read_text(encoding="utf-8")
        assert "old-token-1" not in env_content
        assert "old-token-2" not in env_content
        assert "old-session-secret" in env_content

    def test_auth_rotate_all_logout_all(self, tmp_project: Path) -> None:
        handle_auth_cli(["rotate", "all", "--logout-all"], tmp_project)
        env_content = (tmp_project / ".env").read_text(encoding="utf-8")
        assert "old-token-1" not in env_content
        assert "old-token-2" not in env_content
        assert "old-session-secret" not in env_content

    def test_auth_rotate_session(self, tmp_project: Path) -> None:
        handle_auth_cli(["rotate", "session"], tmp_project)
        env_content = (tmp_project / ".env").read_text(encoding="utf-8")
        assert "old-session-secret" not in env_content
        assert "old-token-1" in env_content

    def test_auth_rotate_bitrix_widget(self, tmp_project: Path) -> None:
        handle_auth_cli(["rotate", "bitrix-widget"], tmp_project)
        env_content = (tmp_project / ".env").read_text(encoding="utf-8")
        assert "old-widget-token" not in env_content
        assert "old-session-secret" in env_content
        assert "old-token-1" in env_content
        assert "old-token-2" in env_content

    def test_no_args_returns_error(self, tmp_project: Path) -> None:
        code = handle_auth_cli([], tmp_project)
        assert code == 2

    def test_unknown_subcommand_returns_error(self, tmp_project: Path) -> None:
        code = handle_auth_cli(["unknown"], tmp_project)
        assert code == 2


class TestSecurity:
    def test_session_secret_not_in_stdout(
        self, tmp_project: Path, auth_cfg: dict, capsys: Any
    ) -> None:
        _do_rotate(auth_cfg, tmp_project, "session", logout_all=False)
        stdout = capsys.readouterr().out
        assert SESSION_SECRET_ENV_NAME not in stdout
        secret_val = _env_value_from_file(tmp_project / ".env", SESSION_SECRET_ENV_NAME)
        assert secret_val not in stdout

    def test_error_on_unknown_does_not_leak_tokens(
        self, tmp_project: Path, auth_cfg: dict, capsys: Any
    ) -> None:
        _do_rotate(auth_cfg, tmp_project, "nobody", logout_all=False)
        stderr = capsys.readouterr().err
        assert "old-token" not in stderr


class TestEdgeCases:
    def test_rotate_with_missing_env_creates_it(
        self, tmp_project_no_env: Path, auth_cfg: dict
    ) -> None:
        env_path = tmp_project_no_env / ".env"
        assert not env_path.exists()
        _do_rotate(auth_cfg, tmp_project_no_env, "all", logout_all=False)
        assert env_path.exists()
        content = env_path.read_text(encoding="utf-8")
        for env_name in PRINCIPAL_TOKEN_ENVS:
            assert env_name in content

    def test_multiple_calls_rotate_different_tokens(
        self, tmp_project: Path, auth_cfg: dict
    ) -> None:
        _do_rotate(auth_cfg, tmp_project, "admin_1", logout_all=False)
        token1_first = _env_value_from_file(
            tmp_project / ".env", "BEEAGENT_WEB_ADMIN1_TOKEN"
        )
        _do_rotate(auth_cfg, tmp_project, "admin_1", logout_all=False)
        token1_second = _env_value_from_file(
            tmp_project / ".env", "BEEAGENT_WEB_ADMIN1_TOKEN"
        )
        assert token1_first != token1_second

    def test_rotate_with_no_principals_configured(self, tmp_project: Path) -> None:
        empty_cfg: dict[str, Any] = {"session_secret_env": None, "principals": []}
        code = _do_rotate(empty_cfg, tmp_project, "all", logout_all=False)
        assert code == 1

    def test_no_principals_no_crash_on_session(self, tmp_project: Path) -> None:
        empty_cfg: dict[str, Any] = {"session_secret_env": None, "principals": []}
        code = _do_rotate(empty_cfg, tmp_project, "session", logout_all=False)
        assert code == 1


class TestEnsureWebAuthEnv:
    def test_bootstrap_generates_missing_secrets(
        self, tmp_project_no_env: Path, monkeypatch: Any
    ) -> None:
        monkeypatch.delenv("BEEAGENT_WEB_ADMIN1_TOKEN", raising=False)
        monkeypatch.delenv("BEEAGENT_WEB_ADMIN2_TOKEN", raising=False)
        monkeypatch.delenv("BEEAGENT_WEB_SESSION_SECRET", raising=False)
        monkeypatch.delenv("BITRIX_ROP_WIDGET_TOKEN", raising=False)
        env_path = tmp_project_no_env / ".env"
        assert not env_path.exists()
        ensure_web_auth_env(
            tmp_project_no_env, tmp_project_no_env / "config" / "settings.yml"
        )
        assert env_path.exists()
        content = env_path.read_text(encoding="utf-8")
        assert "BEEAGENT_WEB_ADMIN1_TOKEN=" in content
        assert "BEEAGENT_WEB_ADMIN2_TOKEN=" in content
        assert "BEEAGENT_WEB_SESSION_SECRET=" in content
        assert "BITRIX_ROP_WIDGET_TOKEN=" in content

    def test_bootstrap_fills_empty_env_keys_in_place(
        self, tmp_project_with_empty_env: Path, monkeypatch: Any
    ) -> None:
        monkeypatch.delenv("BEEAGENT_WEB_ADMIN1_TOKEN", raising=False)
        monkeypatch.delenv("BEEAGENT_WEB_ADMIN2_TOKEN", raising=False)
        monkeypatch.delenv("BEEAGENT_WEB_SESSION_SECRET", raising=False)
        monkeypatch.delenv("BITRIX_ROP_WIDGET_TOKEN", raising=False)
        env_path = tmp_project_with_empty_env / ".env"
        ensure_web_auth_env(
            tmp_project_with_empty_env,
            tmp_project_with_empty_env / "config" / "settings.yml",
        )
        content = env_path.read_text(encoding="utf-8")
        assert "BEEAGENT_WEB_ADMIN1_TOKEN=" in content
        admin1_lines = [
            l
            for l in content.splitlines()
            if l.startswith("BEEAGENT_WEB_ADMIN1_TOKEN=")
        ]
        assert len(admin1_lines) == 1
        val = admin1_lines[0].split("=", 1)[1]
        assert val != ""
        widget_val = _env_value_from_file(env_path, WIDGET_ENV)
        assert widget_val != ""

    def test_bootstrap_does_not_overwrite_existing_env(self, tmp_project: Path) -> None:
        ensure_web_auth_env(tmp_project, tmp_project / "config" / "settings.yml")
        content = (tmp_project / ".env").read_text(encoding="utf-8")
        assert "old-token-1" in content
        assert "old-token-2" in content
        assert "old-session-secret" in content
        assert "old-widget-token" in content

    def test_bootstrap_preserves_unrelated_values(
        self, tmp_project_no_env: Path, monkeypatch: Any
    ) -> None:
        monkeypatch.delenv("BEEAGENT_WEB_ADMIN1_TOKEN", raising=False)
        monkeypatch.delenv("BEEAGENT_WEB_ADMIN2_TOKEN", raising=False)
        monkeypatch.delenv("BEEAGENT_WEB_SESSION_SECRET", raising=False)
        monkeypatch.delenv("BITRIX_ROP_WIDGET_TOKEN", raising=False)
        env_path = tmp_project_no_env / ".env"
        env_path.write_text("UNRELATED=keep-me\n", encoding="utf-8")
        ensure_web_auth_env(
            tmp_project_no_env, tmp_project_no_env / "config" / "settings.yml"
        )
        content = env_path.read_text(encoding="utf-8")
        assert "UNRELATED=keep-me" in content

    def test_bootstrap_sets_env_for_current_process(
        self, tmp_project_no_env: Path, monkeypatch: Any
    ) -> None:
        monkeypatch.delenv("BEEAGENT_WEB_ADMIN1_TOKEN", raising=False)
        monkeypatch.delenv("BITRIX_ROP_WIDGET_TOKEN", raising=False)
        ensure_web_auth_env(
            tmp_project_no_env, tmp_project_no_env / "config" / "settings.yml"
        )
        assert os.environ.get("BEEAGENT_WEB_ADMIN1_TOKEN", "") != ""

    def test_bootstrap_does_not_print_actual_secrets(
        self, tmp_project_no_env: Path, capsys: Any, monkeypatch: Any
    ) -> None:
        monkeypatch.delenv("BEEAGENT_WEB_ADMIN1_TOKEN", raising=False)
        monkeypatch.delenv("BEEAGENT_WEB_ADMIN2_TOKEN", raising=False)
        monkeypatch.delenv("BEEAGENT_WEB_SESSION_SECRET", raising=False)
        monkeypatch.delenv("BITRIX_ROP_WIDGET_TOKEN", raising=False)
        ensure_web_auth_env(
            tmp_project_no_env, tmp_project_no_env / "config" / "settings.yml"
        )
        stdout = capsys.readouterr().out
        lines = stdout.splitlines()
        assert len(lines) > 0
        for line in lines:
            assert "<generated>" in line
            assert "=" in line
            val = line.split("=", 1)[1]
            assert val == "<generated>"

    def test_bootstrap_does_nothing_when_auth_disabled(
        self, tmp_project_auth_disabled: Path
    ) -> None:
        env_path = tmp_project_auth_disabled / ".env"
        if env_path.exists():
            env_path.unlink()
        ensure_web_auth_env(
            tmp_project_auth_disabled,
            tmp_project_auth_disabled / "config" / "settings.yml",
        )
        assert not env_path.exists()

    def test_bootstrap_sets_posix_permissions(
        self, tmp_project_no_env: Path, monkeypatch: Any
    ) -> None:
        monkeypatch.delenv("BEEAGENT_WEB_ADMIN1_TOKEN", raising=False)
        monkeypatch.delenv("BEEAGENT_WEB_ADMIN2_TOKEN", raising=False)
        monkeypatch.delenv("BEEAGENT_WEB_SESSION_SECRET", raising=False)
        monkeypatch.delenv("BITRIX_ROP_WIDGET_TOKEN", raising=False)
        ensure_web_auth_env(
            tmp_project_no_env, tmp_project_no_env / "config" / "settings.yml"
        )
        env_path = tmp_project_no_env / ".env"
        if os.name == "posix":
            mode = stat.S_IMODE(env_path.stat().st_mode)
            assert mode == (stat.S_IRUSR | stat.S_IWUSR)

    def test_bootstrap_uses_existing_env_value_when_present(
        self, tmp_project: Path, monkeypatch: Any
    ) -> None:
        monkeypatch.delenv("BEEAGENT_WEB_ADMIN1_TOKEN", raising=False)
        ensure_web_auth_env(tmp_project, tmp_project / "config" / "settings.yml")
        assert os.environ.get("BEEAGENT_WEB_ADMIN1_TOKEN") == "old-token-1"


def _env_value_from_file(env_path: Path, key: str) -> str:
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        k, v = stripped.split("=", 1)
        if k.strip() == key:
            return v.strip()
    raise KeyError(f"{key} not found in {env_path}")
