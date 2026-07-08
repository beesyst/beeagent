from pathlib import Path

from beeagent_module.core.settings import load_settings


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
