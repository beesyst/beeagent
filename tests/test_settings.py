from pathlib import Path
from copy import deepcopy

import pytest

from beeagent_module.core.settings import load_settings, validate_settings


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_load_settings_uses_ai_source_of_truth_without_llm(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN1_TOKEN", "admin1-token")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN2_TOKEN", "admin2-token")

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
        (lambda data: data["rop"]["mailbox_poll"].update(source_id="missing"), "not found"),
        (
            lambda data: data["rop"]["sources"][1].update(
                source_type="json_batch",
                batch={"path": "storage/mock/rop_batch_sample.json", "period": "x"},
            ),
            "mailbox_readonly",
        ),
        (lambda data: data["rop"]["sources"][1].update(authority="draft_only"), "read_only"),
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
