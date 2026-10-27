import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from beeagent_module.core.settings import (
    get_rop_ai_adjudicator_runtime_state,
    load_settings,
    validate_settings,
)
from tests.settings_support import load_test_settings, read_test_settings


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True, params=["openai", "openrouter"])
def _isolated_global_ai(request, monkeypatch, isolated_ai_settings, tmp_path):
    def load_isolated():
        settings = isolated_ai_settings(read_test_settings(), request.param)
        config = tmp_path / "settings-loader" / "config"
        config.mkdir(parents=True, exist_ok=True)
        path = config / "settings.yml"
        path.write_text(yaml.safe_dump(settings))
        return load_settings(path)

    monkeypatch.setattr(f"{__name__}.load_test_settings", load_isolated)


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

    settings = load_test_settings()

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
    settings = load_test_settings()
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
    settings = load_test_settings()
    changed = deepcopy(settings)
    changed["modules"]["registry"][0]["install_extra"] = install_extra
    with pytest.raises(RuntimeError, match="install_extra"):
        validate_settings(changed)


def test_module_install_extra_remains_optional(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_test_settings()
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
    settings = load_test_settings()
    changed = deepcopy(settings)
    for module in changed["modules"]["registry"]:
        if module["id"] == "beedrill":
            module["enabled"] = True
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
    settings = load_test_settings()
    changed = deepcopy(settings)
    mutate(changed)
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="leaderboard"):
        validate_settings(changed)


def test_leaderboard_plan_lead_is_valid(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_test_settings()
    _enable_rop(settings)
    validate_settings(settings)


def test_user_name_fallback_is_valid_with_user_id_fallback(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_test_settings()
    changed = deepcopy(settings)
    changed["bitrix"]["writeback"]["user_id_fallback"] = 167
    changed["bitrix"]["writeback"]["user_name_fallback"] = "ROBOT WG"
    validate_settings(changed)


@pytest.mark.parametrize("fallback_name", [None, "", "  ", 167])
def test_user_name_fallback_is_required_with_user_id_fallback(
    monkeypatch, fallback_name
) -> None:
    _base_env(monkeypatch)
    settings = load_test_settings()
    changed = deepcopy(settings)
    changed["bitrix"]["writeback"]["user_name_fallback"] = fallback_name
    with pytest.raises(RuntimeError, match="user_name_fallback"):
        validate_settings(changed)


def test_legacy_inline_sources_are_rejected(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_test_settings()
    changed = deepcopy(settings)
    changed["rop"]["sources"] = []
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="Unsupported rop.sources"):
        validate_settings(changed)


def test_mailbox_poll_sources_all_true_with_enabled_mailbox_passes(
    monkeypatch,
) -> None:
    _base_env(monkeypatch)
    settings = load_test_settings()
    changed = deepcopy(settings)
    changed["rop"]["mailbox_poll"]["sources_all"] = True
    _enable_rop(changed)
    validate_settings(changed)


def test_mailbox_poll_sources_all_true_without_source_id_passes(
    monkeypatch,
) -> None:
    _base_env(monkeypatch)
    settings = load_test_settings()
    changed = deepcopy(settings)
    changed["rop"]["mailbox_poll"].update(sources_all=True, source_id=None)
    _enable_rop(changed)
    validate_settings(changed)


def test_mailbox_poll_old_all_sources_key_fails(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_test_settings()
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
    settings = load_test_settings()
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
    settings = load_test_settings()
    changed = deepcopy(settings)
    changed["rop"]["ai_assist"][key] = "obsolete"
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="Unsupported top-level"):
        validate_settings(changed)


def test_enabled_bitrix_widget_requires_token_env(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_test_settings()
    changed = deepcopy(settings)
    changed["bitrix"]["widget"]["enabled"] = True
    monkeypatch.delenv(changed["bitrix"]["widget"]["token_env"], raising=False)
    with pytest.raises(RuntimeError, match="bitrix.widget.enabled=true"):
        validate_settings(changed)


def test_mailbox_poll_single_source_without_source_id_fails(
    monkeypatch,
) -> None:
    _base_env(monkeypatch)
    settings = load_test_settings()
    changed = deepcopy(settings)
    changed["rop"]["mailbox_poll"].update(sources_all=False, source_id=None)
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="source_id"):
        validate_settings(changed)


def test_mailbox_poll_single_source_config_passes(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_test_settings()
    changed = deepcopy(settings)
    changed["rop"]["mailbox_poll"].pop("sources_all")
    _enable_rop(changed)
    validate_settings(changed)


def _attach_env(monkeypatch) -> None:
    _base_env(monkeypatch)


def test_attachment_storage_missing_block_fails(monkeypatch) -> None:
    _attach_env(monkeypatch)
    settings = load_test_settings()
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
    settings = load_test_settings()
    changed = deepcopy(settings)
    changed["rop"]["attachments"]["storage"][key] = 0
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match=key):
        validate_settings(changed)


def test_attachment_storage_enabled_must_be_bool(monkeypatch) -> None:
    _attach_env(monkeypatch)
    settings = load_test_settings()
    changed = deepcopy(settings)
    changed["rop"]["attachments"]["storage"]["enabled"] = "yes"
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="storage.enabled"):
        validate_settings(changed)


def test_attachment_extraction_invalid_engine_fails(monkeypatch) -> None:
    _attach_env(monkeypatch)
    settings = load_test_settings()
    changed = deepcopy(settings)
    changed["rop"]["attachments"]["extraction"]["engine"] = "tika"
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="extraction.engine"):
        validate_settings(changed)


def test_selected_unimplemented_extractor_fails(monkeypatch) -> None:
    _attach_env(monkeypatch)
    settings = load_test_settings()
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
    settings = load_test_settings()
    changed = deepcopy(settings)
    changed["rop"]["attachments"]["extraction"].pop(key)
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match=f"attachments.extraction.{key}"):
        validate_settings(changed)


def test_attachment_extraction_invalid_chars_max_fails(monkeypatch) -> None:
    _attach_env(monkeypatch)
    settings = load_test_settings()
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
    settings = load_test_settings()
    changed = deepcopy(settings)
    changed["rop"]["ai_assist"]["adjudicator"].pop("attachment_chars_max")
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="attachment_chars_max"):
        validate_settings(changed)


def test_adjudicator_attachment_chars_max_invalid_fails(monkeypatch) -> None:
    _attach_env_full(monkeypatch)
    settings = load_test_settings()
    changed = deepcopy(settings)
    changed["rop"]["ai_assist"]["adjudicator"]["attachment_chars_max"] = 0
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="attachment_chars_max"):
        validate_settings(changed)


def test_attachment_chars_max_must_not_exceed_adjudicator_budget(
    monkeypatch,
) -> None:
    _attach_env_full(monkeypatch)
    settings = load_test_settings()
    changed = deepcopy(settings)
    changed["rop"]["attachments"]["chars_max"] = 5000
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="attachments.chars_max"):
        validate_settings(changed)


def test_adjudicator_attachment_budget_must_not_exceed_extraction(
    monkeypatch,
) -> None:
    _attach_env_full(monkeypatch)
    settings = load_test_settings()
    changed = deepcopy(settings)
    changed["rop"]["ai_assist"]["adjudicator"]["attachment_chars_max"] = 5000
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="attachment_chars_max"):
        validate_settings(changed)


def test_attachment_budget_invariant_valid_passes(monkeypatch) -> None:
    _attach_env_full(monkeypatch)
    settings = load_test_settings()
    _enable_rop(settings)
    validate_settings(settings)
    assert (
        settings["rop"]["attachments"]["chars_max"]
        <= settings["rop"]["ai_assist"]["adjudicator"]["attachment_chars_max"]
        <= settings["rop"]["attachments"]["extraction"]["chars_max"]
    )


def test_bitrix_writeback_file_attach_required_bool(monkeypatch) -> None:
    _attach_env(monkeypatch)
    settings = load_test_settings()
    changed = deepcopy(settings)
    changed["bitrix"]["writeback"]["file_attach"] = "yes"
    with pytest.raises(RuntimeError, match="bitrix.writeback.file_attach"):
        validate_settings(changed)


def test_attachment_config_valid_passes(monkeypatch) -> None:
    _attach_env(monkeypatch)
    settings = load_test_settings()
    _enable_rop(settings)
    validate_settings(settings)
    assert settings["rop"]["attachments"]["storage"]["enabled"] is True
    assert settings["rop"]["attachments"]["extraction"]["engine"] == "docling"
    assert settings["bitrix"]["writeback"]["file_attach"] is True


def test_attachment_analysis_requires_storage_enabled(monkeypatch) -> None:
    _attach_env(monkeypatch)
    settings = load_test_settings()
    changed = deepcopy(settings)
    changed["rop"]["attachments"]["storage"]["enabled"] = False
    _enable_rop(changed)
    with pytest.raises(RuntimeError, match="storage.enabled=true"):
        validate_settings(changed)


def test_attachment_analysis_disabled_with_storage_disabled_passes(
    monkeypatch,
) -> None:
    _attach_env(monkeypatch)
    settings = load_test_settings()
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

    settings = load_test_settings()

    active = [p for p in settings["ai"]["profiles"].values() if p["enabled"]]
    assert len(active) == 1
    monkeypatch.delenv(active[0]["api_key_env"], raising=False)
    validate_settings(settings)


def test_enabled_rop_requires_adjudicator_ai_credential(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_test_settings()
    _enable_rop(settings)
    active = next(p for p in settings["ai"]["profiles"].values() if p["enabled"])
    monkeypatch.delenv(active["api_key_env"])

    with pytest.raises(RuntimeError, match=active["api_key_env"]):
        validate_settings(settings)


def test_disabled_rop_does_not_apply_adjudicator_env_override(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_test_settings()
    monkeypatch.setenv("BEEAGENT_ROP_AI_ADJUDICATOR_ENABLED", "0")

    validate_settings(settings)

    adjudicator = settings["rop"]["ai_assist"]["adjudicator"]
    assert adjudicator["enabled"] is True
    assert "_env_override_present" not in adjudicator


def test_disabled_rop_adjudicator_runtime_state_is_dormant(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_test_settings()

    assert get_rop_ai_adjudicator_runtime_state(settings) == {
        "enabled": False,
        "env_override_present": False,
        "yaml_enabled": False,
    }


def test_enabled_rop_applies_adjudicator_env_override(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_test_settings()
    _enable_rop(settings)
    monkeypatch.setenv("BEEAGENT_ROP_AI_ADJUDICATOR_ENABLED", "0")

    validate_settings(settings)

    adjudicator = settings["rop"]["ai_assist"]["adjudicator"]
    assert adjudicator["enabled"] is False
    assert adjudicator["_env_override_present"] is True


def test_disabled_rop_does_not_load_rop_sources(monkeypatch) -> None:
    _base_env(monkeypatch)
    settings = load_test_settings()
    settings["rop"]["sources_path"] = "config/rop/missing.yml"

    validate_settings(settings)


def test_global_ai_and_bitrix_schema_still_validate_with_rop_disabled(
    monkeypatch,
) -> None:
    _base_env(monkeypatch)
    settings = load_test_settings()
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
    settings = load_test_settings()
    _enable_rop(settings)
    monkeypatch.delenv("BITRIX_WRITEBACK_WEBHOOK_URL")

    with pytest.raises(RuntimeError, match="BITRIX_WRITEBACK_WEBHOOK_URL"):
        validate_settings(settings)


@pytest.mark.parametrize(
    "module,section",
    [("rop", "ai_assist"), ("beedrill", "ai_assist"), ("beescan", "investigation")],
)
@pytest.mark.parametrize("value", [None, False, [], {}, "", "missing", "bad/name"])
def test_invalid_module_selector_fails_when_disabled(
    monkeypatch, module, section, value
):
    _base_env(monkeypatch)
    settings = load_test_settings()
    settings[module][section].update(enabled=False, ai_profile=value)
    with pytest.raises(RuntimeError):
        validate_settings(settings)


def test_beescan_can_inherit_default_with_strict_https(monkeypatch):
    from beeagent_module.integrations.beescan.investigation import named_ai_profile

    _base_env(monkeypatch)
    settings = load_test_settings()
    settings["beescan"]["investigation"].pop("ai_profile")
    settings["ai"]["default_profile"] = "deepseek"
    for profile in settings["ai"]["profiles"].values():
        profile.pop("enabled")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    validate_settings(settings)
    assert (
        named_ai_profile(settings, require_key=False)["model"] == "test-deepseek-model"
    )
    settings["ai"]["profiles"]["deepseek"]["base_url"] = "http://127.0.0.1:1234/v1"
    with pytest.raises(RuntimeError, match="investigation"):
        validate_settings(settings)


def test_rop_override_credential_and_beedrill_degraded_policy(monkeypatch):
    _base_env(monkeypatch)
    settings = load_test_settings()
    settings["beedrill"]["ai_assist"].update(enabled=True, ai_profile="deepseek")
    for module in settings["modules"]["registry"]:
        if module["id"] == "beedrill":
            module["enabled"] = True
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    validate_settings(settings)
    settings["rop"]["ai_assist"]["ai_profile"] = "deepseek"
    _enable_rop(settings)
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        validate_settings(settings)


@pytest.mark.parametrize("trusted_local", [False, True])
@pytest.mark.parametrize("profile", ["openai", "openrouter"])
@pytest.mark.parametrize("modules_enabled", [False, True])
def test_independent_tests_ignore_operator_settings(
    tmp_path, monkeypatch, trusted_local, profile, modules_enabled
):
    from beeagent_module.core.settings import load_settings as runtime_load_settings
    from tests.test_beescan_investigation import configure_approved

    _base_env(monkeypatch)
    settings = read_test_settings()
    settings["ai"]["default_profile"] = profile
    settings["beescan"]["investigation"].update(
        trusted_local_enabled=trusted_local, ai_profile=profile
    )
    if modules_enabled:
        configure_approved(settings, monkeypatch)
    for module in settings["modules"]["registry"]:
        module["enabled"] = module["id"] == "beescan" or modules_enabled
    config = tmp_path / "config"
    (config / "rop").mkdir(parents=True)
    (config / "prompts.yml").write_bytes(
        (_project_root() / "config/prompts.yml").read_bytes()
    )
    (config / "rop/sources.yml").write_bytes(
        (_project_root() / "config/rop/sources.yml").read_bytes()
    )
    operator_path = config / "settings.yml"
    operator_path.write_text(yaml.safe_dump(settings))
    runtime_load_settings(operator_path)
    nodes = [
        "test_settings.py::test_load_settings_uses_ai_source_of_truth_without_llm",
        "test_beescan_investigation.py::test_configuration_and_policy",
        "test_bitrix_embed.py::TestSettingsValidation::test_disabled_embedded_app_with_empty_origin_passes",
        "test_bitrix_reconciliation.py::TestBitrixConfigValidation::test_bitrix_config_exists",
        "test_start_cli_dispatch.py::test_resolve_extras_disabled_attachments_uses_enabled_module",
    ]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; from pathlib import Path; import pytest; "
                "from beeagent_module.core import paths; "
                "paths.ROOT_DIR = Path.cwd(); sys.exit(pytest.main(sys.argv[1:]))"
            ),
            "-q",
            "-rs",
            *(str(_project_root() / "tests" / node) for node in nodes),
        ],
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                (str(_project_root()), str(_project_root() / "src"))
            ),
        },
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "6 passed" in result.stdout
    assert yaml.safe_load(operator_path.read_text()) == settings


@pytest.mark.parametrize("profile", ["openai", "openrouter"])
def test_enabled_trusted_local_still_requires_real_credentials(monkeypatch, profile):
    _base_env(monkeypatch)
    settings = load_test_settings()
    settings["beescan"]["investigation"].update(
        trusted_local_enabled=True, ai_profile=profile
    )
    monkeypatch.delenv(
        settings["ai"]["profiles"][profile]["api_key_env"], raising=False
    )
    with pytest.raises(RuntimeError, match="investigation contract or AI profile"):
        validate_settings(settings)
