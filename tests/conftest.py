from __future__ import annotations

import os
from copy import deepcopy

import pytest

os.environ["BITRIX_WRITEBACK_WEBHOOK_URL"] = "https://portal.test/rest/1/writetoken/"
os.environ["BITRIX_WEBHOOK_URL"] = "https://portal.test/rest/1/readonlytoken/"


@pytest.fixture
def isolated_ai_settings(monkeypatch):
    profiles = {
        "openai": ("openai_responses", "https://api.openai.com/v1"),
        "openrouter": ("openai_compatible", "https://openrouter.ai/api/v1"),
        "deepseek": ("openai_compatible", "https://api.deepseek.com/v1"),
    }
    for name in profiles:
        monkeypatch.setenv(f"{name.upper()}_API_KEY", "sk-test")

    def deny_network(*args, **kwargs):
        pytest.fail("AI transport must be mocked in unit tests")

    monkeypatch.setattr(
        "beeagent_module.core.ai_transport.request.urlopen", deny_network
    )

    def configure(settings, selected):
        isolated = deepcopy(settings)
        isolated["ai"]["profiles"] = {
            name: {
                "enabled": name == selected,
                "provider": provider,
                "base_url": url,
                "model": f"test-{name}-model",
                "api_key_env": f"{name.upper()}_API_KEY",
            }
            for name, (provider, url) in profiles.items()
        }
        return isolated

    return configure
