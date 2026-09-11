import os
import re
from pathlib import Path

import pytest
import yaml

from beeagent_module.adapters.mailbox import MailboxAuthError
from beeagent_module.interfaces.ui.adapter import BeeAgentUiAdapter
from beeagent_module.core.rop_sources import (
    RopSourcesError,
    add_mailbox_source,
    add_rop_source,
    credential_env_names,
    load_rop_source_connection_health,
    load_rop_sources,
    remove_rop_source,
    record_rop_source_connection_health,
    remove_rop_source_connection_health,
    resolve_sources_path,
    update_rop_source,
    update_mailbox_source,
    update_rop_source_display_name,
)


def _settings() -> dict:
    return {
        "rop": {
            "sources_path": "config/rop/sources.yml",
            "mailbox_poll": {
                "enabled": False,
                "source_id": "mailbox",
                "sources_all": False,
            },
        }
    }


def _source(source_id: str = "batch") -> dict:
    return {
        "source_id": source_id,
        "source_type": "json_batch",
        "source_role": "sample",
        "client_id": "client",
        "display_name": "Sample",
        "enabled": True,
        "authority": "read_only",
        "items_max": 10,
        "batch": {"path": "storage/sample.json", "period": "2026-01"},
    }


def _mailbox_source(source_id: str = "mailbox") -> dict:
    return {
        "source_id": source_id,
        "source_type": "mailbox_readonly",
        "source_role": "hotline",
        "client_id": "client",
        "display_name": "Mailbox",
        "enabled": True,
        "authority": "read_only",
        "items_max": 42,
        "mailbox": {
            "host": "imap.example.test",
            "port": 993,
            "use_ssl": True,
            "folder": "INBOX",
            "username_env": "TEST_MAILBOX_USERNAME",
            "password_env": "TEST_MAILBOX_PASSWORD",
        },
    }


def _write_registry(tmp_path: Path, sources: list[dict]) -> None:
    path = tmp_path / "config" / "rop"
    path.mkdir(parents=True)
    (path / "sources.yml").write_text(
        yaml.safe_dump({"version": 1, "sources": sources}, sort_keys=False),
        encoding="utf-8",
    )


def test_registry_add_update_remove_round_trip(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "rop").mkdir()
    (config / "rop" / "sources.yml").write_text("version: 1\nsources: []\n")
    settings = _settings()
    source = _source()
    assert add_rop_source(tmp_path, settings, source)[1] is True
    updated = {**source, "display_name": "Changed"}
    assert update_rop_source(tmp_path, settings, "batch", updated)[1] is True
    assert load_rop_sources(tmp_path, settings)[0]["display_name"] == "Changed"
    assert remove_rop_source(tmp_path, settings, "batch")[1] is True
    assert load_rop_sources(tmp_path, settings) == []


def test_connection_health_is_safe_and_removes_only_requested_source(
    tmp_path: Path,
) -> None:
    record_rop_source_connection_health(tmp_path, "mailbox", "connected", "ok")
    record_rop_source_connection_health(
        tmp_path, "other_mailbox", "failed", "auth_failure"
    )
    health = load_rop_source_connection_health(tmp_path)
    assert health["mailbox"]["status"] == "connected"
    assert health["other_mailbox"]["reason_code"] == "auth_failure"
    assert set(health["mailbox"]) == {"status", "reason_code", "checked_at_utc"}
    assert "USERNAME" not in str(health)
    assert "PASSWORD" not in str(health)
    remove_rop_source_connection_health(tmp_path, "mailbox")
    assert set(load_rop_source_connection_health(tmp_path)) == {"other_mailbox"}


def test_registry_path_and_credential_env_names_are_bounded(tmp_path: Path) -> None:
    settings = _settings()
    settings["rop"]["sources_path"] = "../sources.yml"
    with pytest.raises(RopSourcesError):
        resolve_sources_path(tmp_path, settings)
    assert credential_env_names("sales_mailbox") == (
        "BEEAGENT_ROP_SOURCE_SALES_MAILBOX_USERNAME",
        "BEEAGENT_ROP_SOURCE_SALES_MAILBOX_PASSWORD",
    )


def test_mailbox_add_derives_profile_and_preserves_hidden_fields(
    tmp_path: Path,
) -> None:
    _write_registry(tmp_path, [_mailbox_source()])
    source, changed = add_mailbox_source(
        tmp_path,
        _settings(),
        {
            "display_name": "New mailbox",
            "host": "imap.new.example.test",
            "folder": "",
            "enabled": False,
        },
    )
    assert changed is True
    assert re.fullmatch(r"mailbox_[0-9a-f]{8}", source["source_id"])
    assert credential_env_names(source["source_id"]) == (
        source["mailbox"]["username_env"],
        source["mailbox"]["password_env"],
    )
    assert source["source_role"] == "hotline"
    assert source["client_id"] == "client"
    assert source["items_max"] == 42
    assert source["authority"] == "read_only"
    assert source["mailbox"] == {
        "host": "imap.new.example.test",
        "port": 993,
        "use_ssl": True,
        "folder": "INBOX",
        "username_env": source["mailbox"]["username_env"],
        "password_env": source["mailbox"]["password_env"],
    }


def test_mailbox_add_retries_short_generated_id_collision(
    monkeypatch, tmp_path: Path
) -> None:
    existing = _mailbox_source("mailbox_deadbeef")
    _write_registry(tmp_path, [existing])
    settings = _settings()
    settings["rop"]["mailbox_poll"]["source_id"] = existing["source_id"]
    generated = iter(["deadbeef", "a1b2c3d4"])

    class _Uuid:
        @property
        def hex(self) -> str:
            return next(generated) + "0" * 24

    monkeypatch.setattr("beeagent_module.core.rop_sources.uuid.uuid4", lambda: _Uuid())
    source, changed = add_mailbox_source(
        tmp_path,
        settings,
        {
            "display_name": "New mailbox",
            "host": "imap.new.example.test",
            "folder": "INBOX",
            "enabled": True,
        },
    )

    assert changed is True
    assert source["source_id"] == "mailbox_a1b2c3d4"


def test_existing_long_mailbox_id_remains_loadable_and_editable(tmp_path: Path) -> None:
    source = _mailbox_source("mailbox_1234567890abcdef")
    _write_registry(tmp_path, [source])

    updated, changed = update_mailbox_source(
        tmp_path,
        _settings(),
        source["source_id"],
        {"display_name": "Changed", "host": "imap.changed.test", "folder": "INBOX"},
    )

    assert changed is True
    assert updated["source_id"] == source["source_id"]
    assert updated["mailbox"]["username_env"] == source["mailbox"]["username_env"]


@pytest.mark.parametrize(
    "host",
    [
        "",
        " imap.example.test",
        "imap example.test",
        "https://imap.example.test",
        "imap.example.test/a",
    ],
)
def test_mailbox_add_rejects_noncanonical_host(tmp_path: Path, host: str) -> None:
    _write_registry(tmp_path, [_mailbox_source()])
    with pytest.raises(RopSourcesError, match="mailbox host"):
        add_mailbox_source(
            tmp_path,
            _settings(),
            {
                "display_name": "New mailbox",
                "host": host,
                "folder": "INBOX",
                "enabled": True,
            },
        )


def test_visible_source_updates_preserve_hidden_configuration(tmp_path: Path) -> None:
    mailbox = _mailbox_source()
    batch = _source()
    _write_registry(tmp_path, [mailbox, batch])
    updated, changed = update_mailbox_source(
        tmp_path,
        _settings(),
        "mailbox",
        {"display_name": "Changed", "host": "imap.changed.test", "folder": "Archive"},
    )
    assert changed is True
    assert updated["mailbox"]["port"] == 993
    assert updated["mailbox"]["use_ssl"] is True
    assert updated["mailbox"]["username_env"] == "TEST_MAILBOX_USERNAME"
    json_updated, changed = update_rop_source_display_name(
        tmp_path, _settings(), "batch", "Batch changed"
    )
    assert changed is True
    assert json_updated["batch"] == batch["batch"]


def test_registry_lock_is_created_and_gitignored(tmp_path: Path) -> None:
    _write_registry(tmp_path, [_mailbox_source()])
    update_mailbox_source(
        tmp_path,
        _settings(),
        "mailbox",
        {"display_name": "Changed", "host": "imap.changed.test", "folder": "INBOX"},
    )
    assert (tmp_path / "config" / "rop" / "sources.yml.lock").exists()


def test_source_status_toggle_persists_and_renders(monkeypatch, tmp_path: Path) -> None:
    _write_registry(tmp_path, [_mailbox_source()])
    settings = _settings()
    settings["web"] = {
        "auth": {
            "principals": [
                {"id": "admin", "scopes": ["rop"]},
                {"id": "operator", "scopes": ["rop"]},
            ]
        }
    }
    monkeypatch.setattr(
        "beeagent_module.interfaces.ui.adapter.get_project_root", lambda: tmp_path
    )
    adapter = BeeAgentUiAdapter(tmp_path / "storage", settings)
    actor = {"user_id": "admin", "role": "admin"}

    result = adapter.execute_action(
        "rop_source_set_enabled",
        {"source_id": "mailbox", "enabled": False},
        actor,
    )
    assert result.status == "ok"
    assert load_rop_sources(tmp_path, settings)[0]["enabled"] is False
    table = adapter._sources_layout({"tab": "sources"}, "en")[0]
    assert table["rows"][0]["status"]["checked"] is False

    denied = adapter.execute_action(
        "rop_source_set_enabled",
        {"source_id": "mailbox", "enabled": True},
        {"user_id": "operator", "role": "operator"},
    )
    assert denied.status == "error"
    assert load_rop_sources(tmp_path, settings)[0]["enabled"] is False

    result = adapter.execute_action(
        "rop_source_set_enabled",
        {"source_id": "mailbox", "enabled": True},
        actor,
    )
    assert result.status == "ok"
    assert load_rop_sources(tmp_path, settings)[0]["enabled"] is True
    table = adapter._sources_layout({"tab": "sources"}, "en")[0]
    assert table["rows"][0]["status"]["checked"] is True


def test_source_layout_uses_mail_server_without_credentials(
    monkeypatch, tmp_path: Path
) -> None:
    source = _mailbox_source()
    source["mailbox"]["host"] = "web01.srv.welding.kz"
    _write_registry(tmp_path, [source, _source()])
    monkeypatch.setattr(
        "beeagent_module.interfaces.ui.adapter.get_project_root", lambda: tmp_path
    )
    adapter = BeeAgentUiAdapter(tmp_path / "storage", _settings())

    ru_table = adapter._sources_layout({"tab": "sources"}, "ru")[0]
    assert [column["label"] for column in ru_table["columns"]] == [
        "Название",
        "Почтовый сервер",
        "Папка",
        "Имя пользователя",
        "Пароль",
        "Статус",
        "Обработано всего",
        "",
    ]
    assert [column["key"] for column in ru_table["columns"]] == [
        "display_name",
        "host",
        "folder",
        "username",
        "masked_value",
        "status",
        "processed_total",
        "actions",
    ]
    add_action = ru_table["toolbar"]["actions"][1]
    assert [field["name"] for field in add_action["fields"]] == [
        "display_name",
        "host",
        "folder",
        "username",
        "password",
        "enabled",
    ]
    assert "description" not in add_action
    assert add_action["fields"][4]["type"] == "password"
    assert add_action["fields"][4]["required"] is True
    assert add_action["follow_up_action_id"] == "rop_source_check_connection"
    assert add_action["follow_up_match_arg"] == "source_id"
    assert "username_env" not in str(ru_table)
    assert "password_env" not in str(ru_table)

    en_table = adapter._sources_layout({"tab": "sources"}, "en")[0]
    assert [column["label"] for column in en_table["columns"]] == [
        "Name",
        "Mail server",
        "Folder",
        "Username",
        "Password",
        "Status",
        "Processed total",
        "",
    ]
    assert en_table["rows"][0]["host"]["label"] == "web01.srv.welding.kz"
    check_action, edit_action, delete_action = en_table["rows"][0]["actions"]
    assert check_action["action_id"] == "rop_source_check_connection"
    assert check_action["icon"] == "check"
    assert check_action["tone"] == "secondary"
    assert edit_action["inline_edit"] is True
    assert edit_action["pending_action_id"] == "rop_source_check_connection"
    assert [field["name"] for field in edit_action["fields"]] == [
        "display_name",
        "host",
        "folder",
        "username",
        "password",
    ]
    assert edit_action["fields"][-1]["column_key"] == "masked_value"
    assert delete_action["icon"] == "trash"
    batch_edit_action = en_table["rows"][1]["actions"][0]
    assert batch_edit_action["inline_edit"] is True
    assert "pending_action_id" not in batch_edit_action
    assert [field["name"] for field in batch_edit_action["fields"]] == ["display_name"]


def test_source_processed_total_uses_all_time_source_contribution(
    monkeypatch, tmp_path: Path
) -> None:
    first = _mailbox_source("mailbox_a")
    second = _mailbox_source("mailbox_b")
    _write_registry(tmp_path, [first, second])
    settings = _settings()
    settings["rop"]["dashboard"] = {
        "default_period": "7d",
        "periods": ["7d", "all"],
    }
    monkeypatch.setattr(
        "beeagent_module.interfaces.ui.adapter.get_project_root", lambda: tmp_path
    )
    monkeypatch.setattr(
        "beeagent_module.interfaces.ui.adapter.build_rop_tab_read_model",
        lambda *_args, **_kwargs: {
            "series": {
                "source_contribution": {
                    "labels": ["mailbox_a"],
                    "series": [3],
                }
            }
        },
    )

    table = BeeAgentUiAdapter(tmp_path / "storage", settings)._sources_layout(
        {"tab": "sources"}, "en"
    )[0]

    assert table["rows"][0]["processed_total"]["label"] == "3"
    assert table["rows"][1]["processed_total"]["label"] == "0"
    monkeypatch.setattr(
        "beeagent_module.interfaces.ui.adapter.build_rop_tab_read_model",
        lambda *_args, **_kwargs: {"error": "web_projection_unavailable"},
    )
    unavailable = BeeAgentUiAdapter(tmp_path / "storage", settings)._sources_layout(
        {"tab": "sources"}, "en"
    )[0]
    assert unavailable["rows"][0]["processed_total"]["label"] == "—"


def test_mailbox_credentials_are_bounded_and_secret_free_in_layout(
    monkeypatch, tmp_path: Path
) -> None:
    _write_registry(tmp_path, [_mailbox_source()])
    (tmp_path / ".env").write_text(
        "TEST_MAILBOX_USERNAME=mail-user\nTEST_MAILBOX_PASSWORD=stored-value\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("TEST_MAILBOX_USERNAME", raising=False)
    monkeypatch.delenv("TEST_MAILBOX_PASSWORD", raising=False)
    monkeypatch.setattr(
        "beeagent_module.interfaces.ui.adapter.get_project_root", lambda: tmp_path
    )
    table = BeeAgentUiAdapter(tmp_path / "storage", _settings())._sources_layout(
        {"tab": "sources"}, "en"
    )[0]
    row = table["rows"][0]
    assert row["username"]["label"] == "mail-user"
    assert row["masked_value"]["label"] == "********"
    action = row["actions"][1]
    password = next(field for field in action["fields"] if field["name"] == "password")
    assert password == {
        "name": "password",
        "column_key": "masked_value",
        "type": "password",
        "label": "Password",
        "required": False,
        "max_length": 1024,
        "value": "",
    }
    assert "stored-value" not in str(table)
    (tmp_path / ".env").write_text(
        "TEST_MAILBOX_USERNAME=mail-user\n", encoding="utf-8"
    )
    table = BeeAgentUiAdapter(tmp_path / "storage", _settings())._sources_layout(
        {"tab": "sources"}, "en"
    )[0]
    assert table["rows"][0]["masked_value"]["label"] == "—"


def test_admin_add_and_edit_mailbox_credentials(monkeypatch, tmp_path: Path) -> None:
    _write_registry(tmp_path, [_mailbox_source()])
    (tmp_path / ".env").write_text(
        "TEST_MAILBOX_USERNAME=before-user\nTEST_MAILBOX_PASSWORD=before-value\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("TEST_MAILBOX_USERNAME", raising=False)
    monkeypatch.delenv("TEST_MAILBOX_PASSWORD", raising=False)
    monkeypatch.setattr(
        "beeagent_module.interfaces.ui.adapter.get_project_root", lambda: tmp_path
    )
    checks: list[object] = []

    def check_access(*args):
        checks.append(args)
        return "failed", "mailbox_unavailable"

    monkeypatch.setattr(
        "beeagent_module.interfaces.ui.adapter._check_mailbox_source_access",
        check_access,
    )
    settings = _settings()
    settings["web"] = {"auth": {"principals": [{"id": "admin", "scopes": ["rop"]}]}}
    adapter = BeeAgentUiAdapter(tmp_path / "storage", settings)
    actor = {"user_id": "admin", "role": "admin"}
    added = adapter.execute_action(
        "rop_source_add",
        {
            "display_name": "New mailbox",
            "host": "imap.new.example.test",
            "folder": "INBOX",
            "username": "new-user",
            "password": "new-value",
            "enabled": "true",
        },
        actor,
    )
    assert added.status == "ok"
    assert set(added.data) == {"changed", "source_id"}
    assert added.data["source_id"]
    assert "new-user" not in str(added.data)
    assert "new-value" not in str(added.data)
    assert checks == []
    new_source = load_rop_sources(tmp_path, settings)[1]
    mailbox = new_source["mailbox"]
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert f"{mailbox['username_env']}=new-user" in env_text
    assert f"{mailbox['password_env']}=new-value" in env_text
    assert os.environ[mailbox["username_env"]] == "new-user"
    audit = (tmp_path / "storage" / "interfaces" / "rop_sources_audit.jsonl").read_text(
        encoding="utf-8"
    )
    assert "new-user" not in audit
    assert "new-value" not in audit

    preserved = adapter.execute_action(
        "rop_source_update",
        {
            "source_id": "mailbox",
            "display_name": "Mailbox changed",
            "host": "imap.changed.example.test",
            "folder": "Archive",
            "username": "after-user",
            "password": "",
        },
        actor,
    )
    assert preserved.status == "ok"
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "TEST_MAILBOX_USERNAME=after-user" in env_text
    assert "TEST_MAILBOX_PASSWORD=before-value" in env_text
    replaced = adapter.execute_action(
        "rop_source_update",
        {
            "source_id": "mailbox",
            "display_name": "Mailbox changed",
            "host": "imap.changed.example.test",
            "folder": "Archive",
            "username": "after-user",
            "password": "after-value",
        },
        actor,
    )
    assert replaced.status == "ok"
    assert "TEST_MAILBOX_PASSWORD=after-value" in (tmp_path / ".env").read_text(
        encoding="utf-8"
    )

    credentials_only = adapter.execute_action(
        "rop_source_update",
        {
            "source_id": "mailbox",
            "display_name": "Mailbox changed",
            "host": "imap.changed.example.test",
            "folder": "Archive",
            "username": "credential-only-user",
            "password": "",
        },
        actor,
    )
    assert credentials_only.data["changed"] is True

    deleted = adapter.execute_action(
        "rop_source_remove",
        {"source_id": new_source["source_id"]},
        actor,
    )
    assert deleted.status == "ok"
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert mailbox["username_env"] not in env_text
    assert mailbox["password_env"] not in env_text


def test_connection_check_persists_safe_failure_without_action_error(
    monkeypatch, tmp_path: Path
) -> None:
    _write_registry(tmp_path, [_mailbox_source()])
    (tmp_path / ".env").write_text(
        "TEST_MAILBOX_USERNAME=user\nTEST_MAILBOX_PASSWORD=secret\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "beeagent_module.interfaces.ui.adapter.get_project_root", lambda: tmp_path
    )

    def reject_access(*_args, **_kwargs) -> None:
        raise MailboxAuthError("secret")

    monkeypatch.setattr(
        "beeagent_module.interfaces.ui.adapter.ImapReadonlyMailboxClient.check_access",
        reject_access,
    )
    settings = _settings()
    settings["web"] = {"auth": {"principals": [{"id": "admin", "scopes": ["rop"]}]}}
    adapter = BeeAgentUiAdapter(tmp_path / "storage", settings)
    result = adapter.execute_action(
        "rop_source_check_connection",
        {"source_id": "mailbox"},
        {"user_id": "admin", "role": "admin"},
    )
    assert result.status == "ok"
    health = load_rop_source_connection_health(tmp_path / "storage")["mailbox"]
    assert health["status"] == "failed"
    assert health["reason_code"] == "auth_failure"
    assert health["checked_at_utc"]
    assert "secret" not in str(result)


@pytest.mark.parametrize("value", ["line\nbreak", "line\rbreak", "null\x00byte"])
def test_mailbox_credentials_reject_control_characters(
    monkeypatch, tmp_path: Path, value: str
) -> None:
    _write_registry(tmp_path, [_mailbox_source()])
    monkeypatch.setattr(
        "beeagent_module.interfaces.ui.adapter.get_project_root", lambda: tmp_path
    )
    settings = _settings()
    settings["web"] = {"auth": {"principals": [{"id": "admin", "scopes": ["rop"]}]}}
    result = BeeAgentUiAdapter(tmp_path / "storage", settings).execute_action(
        "rop_source_add",
        {
            "display_name": "New mailbox",
            "host": "imap.new.example.test",
            "folder": "INBOX",
            "username": "new-user",
            "password": value,
            "enabled": "true",
        },
        {"user_id": "admin", "role": "admin"},
    )
    assert result.status == "error"
    assert value not in str(result)
    assert load_rop_sources(tmp_path, settings) == [_mailbox_source()]


def test_failed_credential_write_does_not_persist_source(
    monkeypatch, tmp_path: Path
) -> None:
    _write_registry(tmp_path, [_mailbox_source()])

    def fail_write(*_args, **_kwargs):
        raise ValueError("write failed")

    monkeypatch.setattr(
        "beeagent_module.interfaces.ui.adapter.get_project_root", lambda: tmp_path
    )
    monkeypatch.setattr(
        "beeagent_module.interfaces.ui.adapter.update_selected_env_values",
        fail_write,
    )
    settings = _settings()
    settings["web"] = {"auth": {"principals": [{"id": "admin", "scopes": ["rop"]}]}}
    result = BeeAgentUiAdapter(tmp_path / "storage", settings).execute_action(
        "rop_source_add",
        {
            "display_name": "New mailbox",
            "host": "imap.new.example.test",
            "folder": "INBOX",
            "username": "new-user",
            "password": "new-value",
            "enabled": "true",
        },
        {"user_id": "admin", "role": "admin"},
    )
    assert result.status == "error"
    assert "new-value" not in str(result)
    assert load_rop_sources(tmp_path, settings) == [_mailbox_source()]


def test_source_action_rejects_browser_supplied_environment_references(
    monkeypatch, tmp_path: Path
) -> None:
    _write_registry(tmp_path, [_mailbox_source()])
    monkeypatch.setattr(
        "beeagent_module.interfaces.ui.adapter.get_project_root", lambda: tmp_path
    )
    settings = _settings()
    settings["web"] = {"auth": {"principals": [{"id": "admin", "scopes": ["rop"]}]}}
    result = BeeAgentUiAdapter(tmp_path / "storage", settings).execute_action(
        "rop_source_add",
        {
            "display_name": "New mailbox",
            "host": "imap.new.example.test",
            "folder": "INBOX",
            "username": "new-user",
            "password": "new-value",
            "enabled": "true",
            "username_env": "ARBITRARY_NAME",
        },
        {"user_id": "admin", "role": "admin"},
    )
    assert result.status == "error"
    assert load_rop_sources(tmp_path, settings) == [_mailbox_source()]


def test_checked_in_registry_is_canonical() -> None:
    settings = yaml.safe_load(Path("config/settings.yml").read_text(encoding="utf-8"))
    assert "sources" not in settings["rop"]
    assert settings["rop"]["sources_path"] == "config/rop/sources.yml"
    registry = yaml.safe_load(
        Path("config/rop/sources.yml").read_text(encoding="utf-8")
    )
    assert registry["version"] == 1
    assert isinstance(registry["sources"], list)
    sources = load_rop_sources(Path("."), settings)
    assert isinstance(sources, list)
