from copy import deepcopy
from pathlib import Path

import pytest

from beeagent_module.core.settings import (
    get_rop_ai_adjudicator_runtime_state,
    load_settings,
    validate_settings,
)


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
    monkeypatch.setenv("BITRIX_ROP_BLACKLIST_TRIGGER_SECRET", "trigger-secret")
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
        (
            lambda data: data["rop"]["mailbox_poll"].update(
                source_id="", sources_all=False
            ),
            "source_id",
        ),
        (
            lambda data: data["rop"]["mailbox_poll"].update(
                source_id="missing", sources_all=False
            ),
            "not found",
        ),
        (
            lambda data: data["rop"]["mailbox_poll"].update(sources_all="true"),
            "sources_all",
        ),
    ],
)
def test_mailbox_poll_settings_fail_fast(monkeypatch, mutate, match):
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    mutate(changed)
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match=match):
        validate_settings(changed)


def _base_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BITRIX_ROP_BLACKLIST_TRIGGER_SECRET", "trigger-secret")
    monkeypatch.setenv("BITRIX_WRITEBACK_WEBHOOK_URL", "https://write.example.test")
    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-token")
    monkeypatch.setenv("BEEAGENT_WEB_OPERATOR_TOKEN", "operator-token")


def _enable_rop(settings: dict) -> None:
    for item in settings["modules"]["registry"]:
        if item["id"] == "beeagent-rop":
            item["enabled"] = True
            return
    raise AssertionError("beeagent-rop must be declared in modules.registry")


@pytest.mark.parametrize("install_extra", ["", "rop_extra", "ROP", 1])
def test_module_install_extra_fails_fast(monkeypatch, install_extra) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["modules"]["registry"][0]["install_extra"] = install_extra
    with pytest.raises(RuntimeError, match="install_extra"):
        validate_settings(changed)


def test_module_install_extra_remains_optional(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["modules"]["registry"][0].pop("install_extra")
    validate_settings(changed)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data["beedrill"].pop("ai_assist"),
        lambda data: data["beedrill"].update(ai_assist=[]),
        lambda data: data["beedrill"]["ai_assist"].update(enabled="true"),
        lambda data: data["beedrill"]["ai_assist"].update(timeout=0),
        lambda data: data["beedrill"]["ai_assist"].update(input_chars_max=20_001),
        lambda data: data["beedrill"]["ai_assist"].update(prompt_key=""),
    ],
)
def test_beedrill_ai_assist_settings_fail_fast(monkeypatch, mutate) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    mutate(changed)
    with pytest.raises(RuntimeError, match="beedrill"):
        validate_settings(changed)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data["rop"]["dashboard"].pop("leaderboard"),
        lambda data: data["rop"]["dashboard"]["leaderboard"].pop("plan_lead"),
        lambda data: data["rop"]["dashboard"]["leaderboard"].update(plan_lead=0),
        lambda data: data["rop"]["dashboard"]["leaderboard"].update(plan_lead=-1),
        lambda data: data["rop"]["dashboard"]["leaderboard"].update(plan_lead=True),
        lambda data: data["rop"]["dashboard"]["leaderboard"].update(plan_lead="20"),
    ],
)
def test_leaderboard_plan_lead_fails_fast(monkeypatch, mutate) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    mutate(changed)
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="leaderboard"):
        validate_settings(changed)


def test_leaderboard_plan_lead_is_valid(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    _enable_rop(settings)
    validate_settings(settings)


def test_user_name_fallback_is_valid_with_user_id_fallback(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["bitrix"]["writeback"]["user_id_fallback"] = 167
    changed["bitrix"]["writeback"]["user_name_fallback"] = "ROBOT WG"
    validate_settings(changed)


@pytest.mark.parametrize("fallback_name", [None, "", "  ", 167])
def test_user_name_fallback_is_required_with_user_id_fallback(
    monkeypatch, fallback_name
) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["bitrix"]["writeback"]["user_name_fallback"] = fallback_name
    with pytest.raises(RuntimeError, match="user_name_fallback"):
        validate_settings(changed)


def test_legacy_inline_sources_are_rejected(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["sources"] = []
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="Unsupported rop.sources"):
        validate_settings(changed)


def test_mailbox_poll_sources_all_true_with_enabled_mailbox_passes(
    monkeypatch,
) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["mailbox_poll"]["sources_all"] = True
    _enable_rop(changed)
    validate_settings(changed)


def test_mailbox_poll_sources_all_true_without_source_id_passes(
    monkeypatch,
) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["mailbox_poll"].update(sources_all=True, source_id=None)
    _enable_rop(changed)
    validate_settings(changed)


def test_mailbox_poll_old_all_sources_key_fails(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["mailbox_poll"]["all_sources"] = True
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="Unsupported.*all_sources"):
        validate_settings(changed)


@pytest.mark.parametrize("enabled", [[], ["openai", "deepseek"]])
def test_rop_ai_assist_requires_exactly_one_enabled_profile(
    monkeypatch,
    enabled,
) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["ai_assist"].update(enabled=True, dry_run=True)
    changed["rop"]["ai_assist"]["adjudicator"]["enabled"] = False
    for name, profile in changed["ai"]["profiles"].items():
        profile["enabled"] = name in enabled
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="Exactly one"):
        validate_settings(changed)


@pytest.mark.parametrize(
    "key",
    ["provider", "model_env", "api_key_env", "base_url_env"],
)
def test_rop_ai_assist_top_level_transport_keys_fail_fast(monkeypatch, key) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["ai_assist"][key] = "obsolete"
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="Unsupported top-level"):
        validate_settings(changed)


def test_enabled_bitrix_widget_requires_token_env(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["bitrix"]["widget"]["enabled"] = True
    monkeypatch.delenv(changed["bitrix"]["widget"]["token_env"], raising=False)
    with pytest.raises(RuntimeError, match="bitrix.widget.enabled=true"):
        validate_settings(changed)


def test_mailbox_poll_single_source_without_source_id_fails(
    monkeypatch,
) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["mailbox_poll"].update(sources_all=False, source_id=None)
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="source_id"):
        validate_settings(changed)


def test_mailbox_poll_single_source_config_passes(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["mailbox_poll"].pop("sources_all")
    _enable_rop(changed)
    validate_settings(changed)


def _attach_env(monkeypatch) -> None:
    _base_env(monkeypatch)


def test_attachment_storage_missing_block_fails(monkeypatch) -> None:
    _attach_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["attachments"].pop("storage")
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="rop.attachments.storage"):
        validate_settings(changed)


@pytest.mark.parametrize(
    "key",
    [
        "file_max",
        "message_max",
        "files_message_max",
    ],
)
def test_attachment_storage_invalid_value_fails(monkeypatch, key) -> None:
    _attach_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["attachments"]["storage"][key] = 0
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match=key):
        validate_settings(changed)


def test_attachment_storage_enabled_must_be_bool(monkeypatch) -> None:
    _attach_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["attachments"]["storage"]["enabled"] = "yes"
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="storage.enabled"):
        validate_settings(changed)


def test_attachment_extraction_invalid_engine_fails(monkeypatch) -> None:
    _attach_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["attachments"]["extraction"]["engine"] = "tika"
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="extraction.engine"):
        validate_settings(changed)


def test_selected_unimplemented_extractor_fails(monkeypatch) -> None:
    _attach_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["attachments"]["extraction"]["engine"] = "xberg"
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="not implemented"):
        validate_settings(changed)


@pytest.mark.parametrize(
    "key", ["engine", "chars_max", "pages_max", "timeout_seconds", "ocr_enabled"]
)
def test_attachment_extraction_required_keys_fail_fast(monkeypatch, key) -> None:
    _attach_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["attachments"]["extraction"].pop(key)
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match=f"attachments.extraction.{key}"):
        validate_settings(changed)


def test_attachment_extraction_invalid_chars_max_fails(monkeypatch) -> None:
    _attach_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["attachments"]["extraction"]["chars_max"] = -1
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="extraction.chars_max"):
        validate_settings(changed)


def _attach_env_full(monkeypatch) -> None:
    _attach_env(monkeypatch)
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-token")
    monkeypatch.setenv("BEEAGENT_WEB_OPERATOR_TOKEN", "operator-token")


def test_adjudicator_attachment_chars_max_required(monkeypatch) -> None:
    _attach_env_full(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["ai_assist"]["adjudicator"].pop("attachment_chars_max")
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="attachment_chars_max"):
        validate_settings(changed)


def test_adjudicator_attachment_chars_max_invalid_fails(monkeypatch) -> None:
    _attach_env_full(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["ai_assist"]["adjudicator"]["attachment_chars_max"] = 0
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="attachment_chars_max"):
        validate_settings(changed)


def test_attachment_chars_max_must_not_exceed_adjudicator_budget(
    monkeypatch,
) -> None:
    _attach_env_full(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["attachments"]["chars_max"] = 5000
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="attachments.chars_max"):
        validate_settings(changed)


def test_adjudicator_attachment_budget_must_not_exceed_extraction(
    monkeypatch,
) -> None:
    _attach_env_full(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["ai_assist"]["adjudicator"]["attachment_chars_max"] = 5000
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="attachment_chars_max"):
        validate_settings(changed)


def test_attachment_budget_invariant_valid_passes(monkeypatch) -> None:
    _attach_env_full(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    _enable_rop(settings)
    validate_settings(settings)
    assert (
        settings["rop"]["attachments"]["chars_max"]
        <= settings["rop"]["ai_assist"]["adjudicator"]["attachment_chars_max"]
        <= settings["rop"]["attachments"]["extraction"]["chars_max"]
    )


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
    _enable_rop(settings)
    validate_settings(settings)
    assert settings["rop"]["attachments"]["storage"]["enabled"] is True
    assert settings["rop"]["attachments"]["extraction"]["engine"] == "docling"
    assert settings["bitrix"]["writeback"]["file_attach"] is True


def test_attachment_analysis_requires_storage_enabled(monkeypatch) -> None:
    _attach_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    changed = deepcopy(settings)
    changed["rop"]["attachments"]["storage"]["enabled"] = False
    _enable_rop(changed)
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
    _enable_rop(changed)
    validate_settings(changed)


def test_disabled_rop_does_not_require_ai_or_bitrix_credentials(
    monkeypatch,
) -> None:
    _base_env(monkeypatch)
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.delenv("BITRIX_ROP_BLACKLIST_TRIGGER_SECRET")
    monkeypatch.delenv("BITRIX_WRITEBACK_WEBHOOK_URL")

    settings = load_settings(_project_root() / "config" / "settings.yml")

    assert settings["ai"]["profiles"]["openai"]["enabled"] is True
    validate_settings(settings)


def test_enabled_rop_requires_adjudicator_ai_credential(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    _enable_rop(settings)
    monkeypatch.delenv("OPENAI_API_KEY")

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        validate_settings(settings)


def test_disabled_rop_does_not_apply_adjudicator_env_override(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    monkeypatch.setenv("BEEAGENT_ROP_AI_ADJUDICATOR_ENABLED", "0")

    validate_settings(settings)

    adjudicator = settings["rop"]["ai_assist"]["adjudicator"]
    assert adjudicator["enabled"] is True
    assert "_env_override_present" not in adjudicator


def test_disabled_rop_adjudicator_runtime_state_is_dormant(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")

    assert get_rop_ai_adjudicator_runtime_state(settings) == {
        "enabled": False,
        "env_override_present": False,
        "yaml_enabled": False,
    }


def test_enabled_rop_applies_adjudicator_env_override(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    _enable_rop(settings)
    monkeypatch.setenv("BEEAGENT_ROP_AI_ADJUDICATOR_ENABLED", "0")

    validate_settings(settings)

    adjudicator = settings["rop"]["ai_assist"]["adjudicator"]
    assert adjudicator["enabled"] is False
    assert adjudicator["_env_override_present"] is True


def test_disabled_rop_does_not_load_rop_sources(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    settings["rop"]["sources_path"] = "config/rop/missing.yml"

    validate_settings(settings)


def test_global_ai_and_bitrix_schema_still_validate_with_rop_disabled(
    monkeypatch,
) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    invalid_ai = deepcopy(settings)
    invalid_ai["ai"]["profiles"]["openai"]["enabled"] = "true"

    with pytest.raises(RuntimeError, match="ai.profiles.openai.enabled"):
        validate_settings(invalid_ai)

    invalid_bitrix = deepcopy(settings)
    invalid_bitrix["bitrix"]["writeback"]["file_attach"] = "true"

    with pytest.raises(RuntimeError, match="bitrix.writeback.file_attach"):
        validate_settings(invalid_bitrix)


def test_enabled_rop_requires_bitrix_writeback_credential(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_settings(_project_root() / "config" / "settings.yml")
    _enable_rop(settings)
    monkeypatch.delenv("BITRIX_WRITEBACK_WEBHOOK_URL")

    with pytest.raises(RuntimeError, match="BITRIX_WRITEBACK_WEBHOOK_URL"):
        validate_settings(settings)
