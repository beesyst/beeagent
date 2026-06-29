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
    run_ai_assist_for_event,
    write_ai_assist_artifacts,
)


def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_rop_ai_assist")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def _valid_settings() -> dict:
    return {
        "app": {"name": "BeeAgent", "env": "dev"},
        "run": {"mode": "telegram"},
        "web": {"host": "127.0.0.1", "port": 8000, "open_browser": False},
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
        "recommendations": {"enabled": True, "items_max": 10},
        "llm": {
            "enabled": True,
            "provider": "openai",
            "model": "gpt-5-nano",
            "api_key_env": "OPENAI_API_KEY",
            "api_url": "https://api.openai.com/v1/responses",
            "prompts_path": "config/prompts.yml",
            "assistant": {"prompts_key": "oos.llm_assistant_qa", "items_max": 5},
            "throttling": {"timeout": 60, "retries": 2},
        },
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
            "attachments": {
                "enabled": True,
                "chars_max": 500,
                "size_max": 1048576,
                "types": ["text/plain"],
            },
            "sources": [
                {
                    "source_id": "rop_batch_sample",
                    "source_type": "json_batch",
                    "source_role": "batch_sample",
                    "client_id": "welding",
                    "display_name": "ROP Batch Sample",
                    "enabled": True,
                    "authority": "read_only",
                    "items_max": 2,
                    "batch": {
                        "path": "storage/mock/rop_batch_sample.json",
                        "period": "2026-05",
                    },
                }
            ],
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
        },
    }


def _default_ai_cfg() -> dict:
    return {
        "enabled": False,
        "provider": "openai_compatible",
        "model_env": "ROP_AI_MODEL",
        "api_key_env": "ROP_AI_API_KEY",
        "base_url_env": "ROP_AI_BASE_URL",
        "events_max": 20,
        "request_timeout": 30,
        "ai_confidence_min": 0.70,
        "dry_run": True,
    }


def test_ai_disabled_by_default() -> None:
    cfg = _default_ai_cfg()
    assert cfg["enabled"] is False


def test_ai_enabled_missing_env_fail_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _valid_settings()
    settings["rop"]["ai_assist"] = {
        "enabled": True,
        "provider": "openai_compatible",
        "model_env": "ROP_AI_MODEL",
        "api_key_env": "ROP_AI_API_KEY",
        "base_url_env": "ROP_AI_BASE_URL",
        "events_max": 20,
        "request_timeout": 30,
        "ai_confidence_min": 0.70,
        "dry_run": False,
    }

    monkeypatch.delenv("ROP_AI_MODEL", raising=False)
    monkeypatch.delenv("ROP_AI_API_KEY", raising=False)
    monkeypatch.delenv("ROP_AI_BASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="Missing required ROP AI assist env vars"):
        validate_settings(settings)


def test_eligible_fallback_event_creates_ai_request() -> None:
    event = {"event_id": "evt-001", "case_type": "unknown", "is_fallback": True}
    assert _is_event_eligible_for_ai_assist(event) is True


def test_confident_spam_does_not_trigger_ai() -> None:
    event = {
        "event_id": "evt-001",
        "case_type": "spam",
        "confidence": 0.95,
        "is_fallback": False,
    }
    assert _is_event_eligible_for_ai_assist(event) is False


def test_confident_noise_does_not_trigger_ai() -> None:
    event = {
        "event_id": "evt-001",
        "case_type": "noise",
        "confidence": 0.85,
        "is_fallback": False,
    }
    assert _is_event_eligible_for_ai_assist(event) is False


def test_confident_new_lead_does_not_trigger_ai() -> None:
    event = {
        "event_id": "evt-001",
        "case_type": "new_lead",
        "confidence": 0.90,
        "is_fallback": False,
    }
    assert _is_event_eligible_for_ai_assist(event) is False


def test_low_confidence_event_triggers_ai() -> None:
    event = {
        "event_id": "evt-001",
        "case_type": "new_lead",
        "confidence": 0.50,
        "is_fallback": False,
    }
    assert _is_event_eligible_for_ai_assist(event) is True


def test_parse_valid_json_response() -> None:
    raw = '{"case_type": "new_lead", "confidence": 0.85, "reason_code": "ai_classified", "risk_flags": []}'
    result = _parse_ai_response(raw)
    assert result is not None
    assert result["case_type"] == "new_lead"


def test_parse_json_with_markdown_fence() -> None:
    raw = '```json\n{"case_type": "noise", "confidence": 0.90, "reason_code": "ai", "risk_flags": []}\n```'
    result = _parse_ai_response(raw)
    assert result is not None
    assert result["case_type"] == "noise"


def test_parse_invalid_json_returns_none() -> None:
    raw = "not json at all"
    result = _parse_ai_response(raw)
    assert result is None


def test_validate_ai_output_valid() -> None:
    data = {
        "case_type": "existing_deal",
        "case_subtype": "follow_up",
        "recommended_queue": "review",
        "should_rop_see": True,
        "correct_action": "contact_client",
        "confidence": 0.85,
        "reason_code": "ai_assist",
        "risk_flags": [],
    }
    validated = _validate_ai_output(data)
    assert validated["case_type"] == "existing_deal"
    assert validated["case_subtype"] == "follow_up"
    assert validated["confidence"] == 0.85


def test_validate_ai_output_invalid_case_type() -> None:
    data = {"case_type": "invalid_type", "confidence": 0.5, "risk_flags": []}
    validated = _validate_ai_output(data)
    assert validated["case_type"] == "unknown"
    assert len(validated["warnings"]) > 0


def test_validate_ai_output_blocked_write_back_action() -> None:
    data = {
        "case_type": "new_lead",
        "correct_action": "create lead in CRM",
        "confidence": 0.9,
        "risk_flags": [],
    }
    validated = _validate_ai_output(data)
    assert validated["correct_action"] is None
    assert any(
        "blocked_write_back_action" in str(f) for f in validated.get("risk_flags", [])
    )


def test_invalid_ai_output_degraded_path() -> None:
    event = {"event_id": "evt-001", "case_type": "unknown", "is_fallback": True}
    cfg = _default_ai_cfg()
    result = run_ai_assist_for_event(
        event=event,
        ai_cfg=cfg,
        thread_context=None,
        min_ai_confidence=0.70,
        logger=_null_logger(),
    )
    assert result["result"]["ai_assist_status"] in (
        "ok",
        "low_confidence",
        "degraded",
        "not_eligible",
    )


def test_provider_failure_preserves_deterministic_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "beeagent_module.core.rop_ai_assist._call_ai_provider",
        lambda ai_cfg, prompt, logger: None,
    )

    event = {
        "event_id": "evt-provider-failed",
        "case_type": "unknown",
        "case_subtype": None,
        "recommended_queue": None,
        "correct_action": None,
        "is_fallback": True,
    }

    cfg = dict(_default_ai_cfg())
    cfg["dry_run"] = False

    result = run_ai_assist_for_event(
        event=event,
        ai_cfg=cfg,
        thread_context=None,
        min_ai_confidence=0.70,
        logger=_null_logger(),
    )

    assert result["decision"]["status"] == "degraded"
    assert result["decision"]["reason_code"] == "provider_call_failed"
    assert result["result"]["ai_assist_status"] == "degraded"
    assert result["result"]["ai_assist_used"] is False
    assert result["result"]["final_case_type"] == "unknown"
    assert result["result"]["merge_reason"] == (
        "provider_call_failed_deterministic_result_preserved"
    )


def test_write_ai_assist_artifacts(tmp_path: Path) -> None:
    requests = [{"event_id": "evt-001"}]
    decisions = [{"event_id": "evt-001", "status": "ok"}]
    results = [{"event_id": "evt-001", "ai_assist_status": "ok"}]
    counters = {
        "ai_assist_enabled": 1,
        "ai_assist_requested_count": 1,
        "ai_assist_used_count": 1,
        "ai_assist_invalid_count": 0,
        "ai_assist_degraded_count": 0,
    }
    refs = write_ai_assist_artifacts(
        storage_dir=tmp_path,
        run_id="test-ai-write",
        requests=requests,
        decisions=decisions,
        results=results,
        counters=counters,
        logger=_null_logger(),
    )
    assert len(refs) == 3

    for name in (
        "rop_ai_assist_requests.json",
        "rop_ai_assist_decisions.json",
        "rop_ai_assist_results.json",
    ):
        path = tmp_path / "runs" / "test-ai-write" / name
        assert path.exists(), f"Missing {name}"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["run_id"] == "test-ai-write"
        assert "counters" in data


def test_build_assist_prompt_no_secrets() -> None:
    event = {
        "event_id": "evt-001",
        "subject": "Test subject",
        "body": "Test body content",
        "sender": "user@example.com",
    }
    prompt = _build_assist_prompt(event, None)
    assert "ROP_AI_API_KEY" not in prompt
    assert "password" not in prompt.lower()
    assert "secret" not in prompt.lower()


def test_dry_run_returns_placeholder() -> None:
    cfg = dict(_default_ai_cfg())
    cfg["dry_run"] = True
    prompt = "test"
    result = _call_ai_provider(cfg, prompt, _null_logger())
    assert result is not None
    parsed = json.loads(result)
    assert parsed["case_type"] == "existing_deal"
    assert "dry_run" in parsed.get("risk_flags", [])
