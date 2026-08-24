from copy import deepcopy
from pathlib import Path

import pytest

from beeagent_module.core.settings import load_settings, validate_settings


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_load_settings_uses_ai_source_of_truth_without_llm(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-token")
    monkeypatch.setenv("BEEAGENT_WEB_OPERATOR_TOKEN", "operator-token")

    settings = load_settings(_project_root() / "config" / "settings.yml")

    assert "llm" not in settings
    assert "recommendations" not in settings
    assert settings["ai"]["prompts"]["path"] == "config/prompts.yml"
    assert settings["ai"]["profiles"]["openai"]["api_key_env"] == "OPENAI_API_KEY"


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda data: data["rop"]["mailbox_poll"].update(enabled="true"), "enabled"),
        (lambda data: data["rop"]["mailbox_poll"].update(source_id=""), "source_id"),
        (
            lambda data: data["rop"]["mailbox_poll"].update(source_id="missing"),
            "not found",
        ),
        (
            lambda data: data["rop"]["mailbox_poll"].update(sources_all="true"),
            "sources_all",
        ),
        (
            lambda data: data["rop"]["sources"][1].update(
                source_type="json_batch",
                batch={"path": "storage/mock/rop_batch_sample.json", "period": "x"},
            ),
            "mailbox_readonly",
        ),
        (
            lambda data: data["rop"]["sources"][1].update(authority="draft_only"),
            "read_only",
        ),
        (
            lambda data: data["rop"]["sources"][1].update(routing="invalid"),
            "routing",
        ),
        (
            lambda data: data["rop"]["sources"][1].update(
                routing={"email_recipient": "not-an-email"}
            ),
            "email_recipient",
        ),
        (
            lambda data: data["rop"]["sources"][1].update(
                routing={"email_recipient": "a b@welding.kz"}
            ),
            "email_recipient",
        ),
        (
            lambda data: data["rop"]["sources"][1].update(
                routing={"email_recipient": "a@welding.kz,b@welding.kz"}
            ),
            "email_recipient",
        ),
        (
            lambda data: data["rop"]["sources"][1].update(
                routing={"email_recipient": "a@welding.kz;b@welding.kz"}
            ),
            "email_recipient",
        ),
        (
            lambda data: data["rop"]["sources"][1].update(
                routing={"email_recipient": "a@@welding.kz"}
            ),
            "email_recipient",
        ),
        (
            lambda data: data["rop"]["sources"][1].update(
                routing={"email_recipient": "@welding.kz"}
            ),
            "email_recipient",
        ),
        (
            lambda data: data["rop"]["sources"][1].update(
                routing={"email_recipient": "a@welding.kz", "other": "x"}
            ),
            "Unsupported",
        ),
    ],
)
def test_mailbox_poll_settings_fail_fast(monkeypatch, mutate, match):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN1_TOKEN", "admin1-token")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN2_TOKEN", "admin2-token")
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    mutate(changed)
    with pytest.raises(RuntimeError, match=match):
        validate_settings(changed)


def _base_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN1_TOKEN", "admin1-token")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN2_TOKEN", "admin2-token")


def test_mailbox_poll_sources_all_true_with_enabled_mailbox_passes(
    monkeypatch,
) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["mailbox_poll"]["sources_all"] = True
    validate_settings(changed)


def test_mailbox_poll_sources_all_true_without_source_id_passes(
    monkeypatch,
) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["mailbox_poll"].update(sources_all=True, source_id=None)
    validate_settings(changed)


def test_mailbox_poll_old_all_sources_key_fails(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["mailbox_poll"]["all_sources"] = True
    with pytest.raises(RuntimeError, match="Unsupported.*all_sources"):
        validate_settings(changed)


def test_routing_old_recipient_email_key_fails(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["sources"][1]["routing"] = {
        "recipient_email": "hotline@welding.kz"
    }
    with pytest.raises(RuntimeError, match="recipient_email"):
        validate_settings(changed)


def test_mailbox_poll_single_source_without_source_id_fails(
    monkeypatch,
) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["mailbox_poll"].update(sources_all=False, source_id=None)
    with pytest.raises(RuntimeError, match="source_id"):
        validate_settings(changed)


def test_mailbox_poll_single_source_config_passes(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["mailbox_poll"].pop("sources_all")
    validate_settings(changed)


def test_mailbox_poll_sources_all_true_without_mailbox_source_fails(
    monkeypatch,
) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["mailbox_poll"]["sources_all"] = True
    changed["rop"]["sources"][1]["enabled"] = False
    with pytest.raises(RuntimeError, match="sources_all"):
        validate_settings(changed)


def _attach_env(monkeypatch) -> None:
    _base_env(monkeypatch)


def test_attachment_storage_missing_block_fails(monkeypatch) -> None:
    _attach_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["attachments"].pop("storage")
    with pytest.raises(RuntimeError, match="rop.attachments.storage"):
        validate_settings(changed)


@pytest.mark.parametrize(
    "key",
    [
        "file_max_bytes",
        "message_aggregate_max_bytes",
        "files_max_per_message",
    ],
)
def test_attachment_storage_invalid_value_fails(monkeypatch, key) -> None:
    _attach_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["attachments"]["storage"][key] = 0
    with pytest.raises(RuntimeError, match=key):
        validate_settings(changed)


def test_attachment_storage_enabled_must_be_bool(monkeypatch) -> None:
    _attach_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["attachments"]["storage"]["enabled"] = "yes"
    with pytest.raises(RuntimeError, match="storage.enabled"):
        validate_settings(changed)


def test_attachment_analysis_invalid_file_capable_fails(monkeypatch) -> None:
    _attach_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["attachments"]["analysis"]["file_capable"] = "yes"
    with pytest.raises(RuntimeError, match="analysis.file_capable"):
        validate_settings(changed)


def test_attachment_analysis_invalid_max_chars_fails(monkeypatch) -> None:
    _attach_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["attachments"]["analysis"]["max_chars"] = -1
    with pytest.raises(RuntimeError, match="analysis.max_chars"):
        validate_settings(changed)


def test_bitrix_writeback_file_attach_required_bool(monkeypatch) -> None:
    _attach_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["bitrix"]["writeback"]["file_attach"] = "yes"
    with pytest.raises(RuntimeError, match="bitrix.writeback.file_attach"):
        validate_settings(changed)


def test_attachment_config_valid_passes(monkeypatch) -> None:
    _attach_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    validate_settings(settings)
    assert settings["rop"]["attachments"]["storage"]["enabled"] is True
    assert settings["bitrix"]["writeback"]["file_attach"] is False


def test_attachment_analysis_requires_storage_enabled(monkeypatch) -> None:
    _attach_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["attachments"]["storage"]["enabled"] = False
    with pytest.raises(RuntimeError, match="storage.enabled=true"):
        validate_settings(changed)


def test_attachment_analysis_disabled_with_storage_disabled_passes(
    monkeypatch,
) -> None:
    _attach_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["attachments"]["enabled"] = False
    changed["rop"]["attachments"]["storage"]["enabled"] = False
    validate_settings(changed)
