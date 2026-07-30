from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from beeagent_module.core.rop_ai_assist import (
    _build_assist_prompt,
    _call_ai_provider,
    _is_event_eligible_for_ai_assist,
    _parse_ai_response,
    _validate_ai_output,
    resolve_ai_profile,
    run_ai_assist_for_event,
    write_ai_assist_artifacts,
)


def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_rop_ai_assist")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def _default_ai_cfg() -> dict:
    return {
        "enabled": False,
        "events_max": 20,
        "request_timeout": 30,
        "ai_confidence_min": 0.70,
        "dry_run": True,
    }


def _default_ai_settings() -> dict:
    return {
        "profiles": {
            "openai": {
                "enabled": True,
                "provider": "openai_responses",
                "api_key_env": "OPENAI_API_KEY",
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-5.4-mini",
            },
            "deepseek": {
                "enabled": False,
                "provider": "openai_compatible",
                "api_key_env": "DEEPSEEK_API_KEY",
                "base_url": "https://api.deepseek.com/v1",
                "model": "deepseek-chat",
            },
            "lmstudio": {
                "enabled": False,
                "provider": "openai_compatible",
                "api_key_env": "LMSTUDIO_API_KEY",
                "base_url": "http://127.0.0.1:1234/v1",
                "model": "local-model",
            },
            "custom": {
                "enabled": False,
                "provider": "openai_compatible",
                "api_key_env": "CUSTOM_AI_API_KEY",
                "base_url": "https://example.test/v1",
                "model": "custom-model",
            },
        }
    }


def _valid_settings() -> dict:
    return {
        "app": {"name": "BeeAgent", "env": "dev"},
        "run": {"mode": "telegram"},
        "web": {
            "host": "127.0.0.1",
            "port": 8000,
            "open_browser": False,
            "auth": {
                "enabled": False,
                "mode": "beeui_session",
                "session_secret_env": "BEEAGENT_WEB_SESSION_SECRET",
                "principals": [],
            },
        },
        "telegram": {
            "enabled": False,
            "bot_token_env": "TELEGRAM_BOT_TOKEN",
            "chat_id_env": "CHAT_ID",
            "telemetry_enabled": True,
        },
        "logging": {"clear_logs": True, "utc": True, "level": "INFO"},
        "mock": {
            "seed": 42,
            "weeks": 4,
            "stores": 3,
            "skus": 12,
            "category": "Vitamins",
        },
        "data": {"adapter": "mock", "mock": {"dataset_id": None}},
        "scheduler": {"enabled": False, "interval": 100, "start_run": True},
        "approval": {"reject_reason": "Rejected"},
        "promo": {"stock_min": 10, "units_max": 2},
        "i18n": {"lang": "ru", "path": "config/i18n/ru.yml"},
        "quiz": {"enabled": False, "path": "config/quiz/pharmacy_quiz.json"},
        "modules": {
            "registry": [
                {
                    "id": "beeagent-rop",
                    "package": "beeagent_rop",
                    "entry": "RopModule",
                    "enabled": True,
                }
            ]
        },
        "rop": {
            "email_preview": {"body_chars_max": 4000},
            "ai_assist": {
                "enabled": False,
                "events_max": 20,
                "request_timeout": 30,
                "ai_confidence_min": 0.70,
                "dry_run": False,
                "adjudicator": {
                    "enabled": False,
                    "timeout": 20,
                    "input_chars_max": 8000,
                    "confidence_accept_min": 0.70,
                    "events_max": 20,
                    "prompt_key": "rop.ai_adjudicator",
                },
            },
            "routing": {
                "queues": {
                    "sales": {"bitrix_category": "sales"},
                    "tender": {"bitrix_category": "tender"},
                    "logistics": {"bitrix_category": "logistics"},
                    "finance": {"bitrix_category": "finance"},
                    "procurement": {"bitrix_category": "procurement"},
                    "manual_review": {"bitrix_category": "manual_review"},
                },
            },
            "attachments": {
                "enabled": True,
                "chars_max": 500,
                "size_max": 1048576,
                "types": ["text/plain"],
            },
            "sources": [],
            "dashboard": {"default_period": "7d", "periods": ["7d", "30d", "all"]},
        },
        "bitrix": {
            "enabled": True,
            "webhook_env": "BITRIX_WEBHOOK_URL",
            "timeout": 10,
            "page_size": 50,
            "pages_max": 3,
            "types_entity": [1, 2, 3, 4],
            "reconciliation": {
                "enabled": False,
                "candidate_limit": 20,
                "window_date": 180,
            },
            "widget": {
                "enabled": False,
                "token_env": "BITRIX_ROP_WIDGET_TOKEN",
                "default_period": "7d",
                "max_items": 50,
            },
        },
        "ai": {
            "prompts": {"path": "config/prompts.yml", "store": False},
            **_default_ai_settings(),
        },
    }


def test_ai_disabled_by_default() -> None:
    assert _default_ai_cfg()["enabled"] is False


def test_ai_enabled_missing_env_fail_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _valid_settings()
    settings["rop"]["ai_assist"]["enabled"] = True
    settings["rop"]["ai_assist"]["dry_run"] = False

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        validate_settings(settings)


def test_adjudicator_requires_ai_assist_when_enabled() -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _valid_settings()
    settings["rop"]["ai_assist"]["adjudicator"]["enabled"] = True

    with pytest.raises(RuntimeError, match="requires rop.ai_assist.enabled: true"):
        validate_settings(settings)


def test_resolve_ai_profile_uses_enabled_profile() -> None:
    resolved = resolve_ai_profile(_default_ai_cfg(), _default_ai_settings())
    assert resolved["provider"] == "openai_responses"
    assert resolved["model"] == "gpt-5.4-mini"
    assert resolved["api_key_env"] == "OPENAI_API_KEY"
    assert resolved["base_url"] == "https://api.openai.com/v1"


def test_eligible_fallback_event_creates_ai_request() -> None:
    assert _is_event_eligible_for_ai_assist(
        {"event_id": "evt-001", "case_type": "unknown", "is_fallback": True}
    )


def test_confident_spam_does_not_trigger_ai() -> None:
    assert not _is_event_eligible_for_ai_assist(
        {
            "event_id": "evt-001",
            "case_type": "spam",
            "confidence": 0.95,
            "is_fallback": False,
        }
    )


def test_parse_valid_json_response() -> None:
    result = _parse_ai_response(
        '{"case_type": "new_lead", "confidence": 0.85, "reason_code": "ai", "risk_flags": []}'
    )
    assert result is not None
    assert result["case_type"] == "new_lead"


def test_validate_ai_output_blocked_write_back_action() -> None:
    validated = _validate_ai_output(
        {
            "case_type": "new_lead",
            "correct_action": "create lead in CRM",
            "confidence": 0.9,
            "risk_flags": [],
        }
    )
    assert validated["correct_action"] is None
    assert "blocked_write_back_action" in validated["risk_flags"]


def test_invalid_ai_output_degraded_path() -> None:
    result = run_ai_assist_for_event(
        event={"event_id": "evt-001", "case_type": "unknown", "is_fallback": True},
        ai_cfg=resolve_ai_profile(_default_ai_cfg(), _default_ai_settings()),
        thread_context=None,
        min_ai_confidence=0.70,
        logger=_null_logger(),
    )
    assert result["result"]["ai_assist_status"] in {
        "ok",
        "low_confidence",
        "degraded",
        "not_eligible",
    }


def test_provider_failure_preserves_deterministic_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "beeagent_module.core.rop_ai_assist._call_ai_provider",
        lambda ai_cfg, prompt, logger: None,
    )

    cfg = resolve_ai_profile(_default_ai_cfg(), _default_ai_settings())
    cfg["dry_run"] = False

    result = run_ai_assist_for_event(
        event={
            "event_id": "evt-provider-failed",
            "case_type": "unknown",
            "case_subtype": None,
            "recommended_queue": None,
            "correct_action": None,
            "is_fallback": True,
        },
        ai_cfg=cfg,
        thread_context=None,
        min_ai_confidence=0.70,
        logger=_null_logger(),
    )

    assert result["decision"]["status"] == "degraded"
    assert result["result"]["final_case_type"] == "unknown"


def test_unparseable_provider_output_is_not_retained_in_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    marker = "LEGACY-AI-ASSIST-PROVIDER-MARKER"
    monkeypatch.setattr(
        "beeagent_module.core.rop_ai_assist._call_ai_provider",
        lambda ai_cfg, prompt, logger: marker,
    )
    cfg = resolve_ai_profile(_default_ai_cfg(), _default_ai_settings())
    cfg["dry_run"] = False

    output = run_ai_assist_for_event(
        event={
            "event_id": "evt-invalid-provider",
            "case_type": "unknown",
            "is_fallback": True,
        },
        ai_cfg=cfg,
        thread_context=None,
        min_ai_confidence=0.70,
        logger=_null_logger(),
    )

    assert marker not in json.dumps(output)
    assert "raw_response_preview" not in output["decision"]
    write_ai_assist_artifacts(
        storage_dir=tmp_path,
        run_id="invalid-provider-output",
        requests=[output["request"]],
        decisions=[output["decision"]],
        results=[output["result"]],
        counters={},
        logger=_null_logger(),
    )
    run_dir = tmp_path / "runs" / "invalid-provider-output"
    for artifact_name in (
        "rop_ai_assist_requests.json",
        "rop_ai_assist_decisions.json",
        "rop_ai_assist_results.json",
    ):
        content = (run_dir / artifact_name).read_text(encoding="utf-8")
        assert marker not in content
        assert "raw_response_preview" not in content


def test_write_ai_assist_artifacts(tmp_path: Path) -> None:
    refs = write_ai_assist_artifacts(
        storage_dir=tmp_path,
        run_id="test-ai-write",
        requests=[{"event_id": "evt-001"}],
        decisions=[{"event_id": "evt-001", "status": "ok"}],
        results=[{"event_id": "evt-001", "ai_assist_status": "ok"}],
        counters={
            "ai_assist_enabled": 1,
            "ai_assist_requested_count": 1,
            "ai_assist_used_count": 1,
            "ai_assist_invalid_count": 0,
            "ai_assist_degraded_count": 0,
        },
        logger=_null_logger(),
    )
    assert len(refs) == 3


def test_build_assist_prompt_no_secrets() -> None:
    prompt = _build_assist_prompt(
        {
            "event_id": "evt-001",
            "subject": "Test subject",
            "body": "Test body content",
            "sender": "user@example.com",
        },
        None,
    )
    assert "OPENAI_API_KEY" not in prompt
    assert "password" not in prompt.lower()


def test_dry_run_returns_placeholder() -> None:
    cfg = resolve_ai_profile(_default_ai_cfg(), _default_ai_settings())
    cfg["dry_run"] = True
    result = _call_ai_provider(cfg, "test", _null_logger())
    assert result is not None
    parsed = json.loads(result)
    assert parsed["reason_code"] == "dry_run_placeholder"
