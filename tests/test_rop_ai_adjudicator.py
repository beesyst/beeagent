from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from beeagent_module.core.rop_ai_adjudicator import (
    _build_adjudicator_prompt,
    _build_request_artifact,
    _is_event_eligible_for_adjudicator,
    _parse_ai_response,
    _validate_ai_output,
    call_openai_responses_api,
    run_adjudicator_batch,
    run_adjudicator_for_event,
    write_adjudicator_artifacts,
)


def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_adjudicator")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def _minimal_adj_cfg() -> dict:
    return {
        "enabled": True,
        "timeout": 20,
        "input_chars_max": 8000,
        "confidence_accept_min": 0.70,
        "events_max": 20,
        "prompt_key": "rop.ai_adjudicator",
    }


def _minimal_prompts_cfg() -> dict:
    return {"path": "config/prompts.yml", "store": False}


def _minimal_profile_cfg(
    *,
    provider: str = "openai_responses",
    api_key_env: str = "OPENAI_API_KEY",
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-5.4-mini",
) -> dict:
    return {
        "enabled": True,
        "provider": provider,
        "api_key_env": api_key_env,
        "base_url": base_url,
        "model": model,
    }


def _settings(
    *,
    ai_assist_enabled: bool = False,
    adjudicator_enabled: bool = False,
    profiles: dict | None = None,
) -> dict:
    return {
        "rop": {
            "ai_assist": {
                "enabled": ai_assist_enabled,
                "events_max": 20,
                "request_timeout": 30,
                "ai_confidence_min": 0.70,
                "dry_run": False,
                "adjudicator": {
                    **_minimal_adj_cfg(),
                    "enabled": adjudicator_enabled,
                },
            }
        },
        "ai": {
            "prompts": _minimal_prompts_cfg(),
            "profiles": profiles or {"openai": _minimal_profile_cfg()},
        },
    }


def _sample_ineligible_event() -> dict:
    return {
        "event_id": "evt-001",
        "case_type": "new_lead",
        "case_subtype": "rfq",
        "recommended_queue": "sales",
        "correct_action": "review_new_lead",
        "should_rop_see": True,
        "confidence": 0.95,
        "is_fallback": False,
        "reason_code": "new_contact",
        "sender": "test@example.com",
        "subject": "New RFQ",
        "body_preview": "We need 100 units",
    }


def _sample_eligible_event() -> dict:
    return {
        "event_id": "evt-002",
        "case_type": "unknown",
        "case_subtype": None,
        "recommended_queue": "manual_review",
        "correct_action": "manual_review",
        "should_rop_see": True,
        "confidence": 0.0,
        "is_fallback": True,
        "sender": "ambiguous@example.com",
        "subject": "Question about order",
        "body_preview": "Is this still available?",
        "source_id": "test_source",
        "clean_subject": "Question about order",
        "transport_labels": [],
        "spam_label_present": False,
        "reply_label_present": False,
        "forwarded_wrapper": False,
        "attachments": [],
        "reason_code": "fallback_low_signal",
        "deterministic_case_type": "unknown",
        "deterministic_case_subtype": None,
        "deterministic_recommended_queue": "manual_review",
        "deterministic_correct_action": "manual_review",
        "deterministic_confidence": 0.0,
        "deterministic_reason_code": "fallback_low_signal",
    }


def _sample_supplier_spam_false_positive_event() -> dict:
    return {
        "event_id": "evt-supplier-spam",
        "case_type": "existing_deal",
        "case_subtype": "existing_deal_procurement",
        "recommended_queue": "procurement",
        "correct_action": "check_bitrix",
        "should_rop_see": True,
        "confidence": 0.91,
        "is_fallback": False,
        "reason_code": "existing_deal_reference_signal",
        "spam_label_present": True,
        "subject": "*** SPAM *** OEM submerged-arc welding machine supplied",
        "clean_subject": "OEM submerged-arc welding machine supplied",
        "body_preview": "We are manufacturer and we offer product line catalogue.",
        "attachments": [
            {
                "filename": "SAW welder presentation.pdf",
                "content_type": "application/pdf",
            }
        ],
    }


def _sample_hr_newsletter_false_positive_event() -> dict:
    return {
        "event_id": "evt-hr-newsletter",
        "case_type": "existing_deal",
        "case_subtype": "existing_deal_procurement",
        "recommended_queue": "procurement",
        "correct_action": "check_bitrix",
        "should_rop_see": True,
        "confidence": 0.88,
        "is_fallback": False,
        "reason_code": "existing_deal_reference_signal",
        "subject": "С 8 июня ГПХ могут признать трудовым договором",
        "body_preview": (
            "Семинар, обучение, вебинар, программа семинара, заявка на участие"
        ),
    }


class TestEligibility:
    def test_fallback_is_eligible(self) -> None:
        assert _is_event_eligible_for_adjudicator(_sample_eligible_event()) is True

    def test_high_confidence_new_lead_not_eligible(self) -> None:
        assert _is_event_eligible_for_adjudicator(_sample_ineligible_event()) is False

    def test_supplier_spam_false_positive_is_eligible(self) -> None:
        assert (
            _is_event_eligible_for_adjudicator(
                _sample_supplier_spam_false_positive_event()
            )
            is True
        )

    def test_hr_newsletter_false_positive_is_eligible(self) -> None:
        assert (
            _is_event_eligible_for_adjudicator(
                _sample_hr_newsletter_false_positive_event()
            )
            is True
        )


class TestPromptBuilding:
    def test_prompt_contains_safe_bounded_fields(self) -> None:
        prompt = _build_adjudicator_prompt(
            prompts_cfg=_minimal_prompts_cfg(),
            event=_sample_eligible_event(),
            prompt_key="rop.ai_adjudicator",
            max_chars=8000,
        )
        assert "event_id" in prompt
        assert "ambiguous@example.com" in prompt
        assert "fallback_low_signal" in prompt
        assert "OPENAI_API_KEY" not in prompt
        assert "raw_eml" not in prompt

    def test_adjudicator_prompt_preserves_user_template_with_event_json(
        self,
        tmp_path: Path,
    ) -> None:
        prompts_path = tmp_path / "prompts.yml"
        prompts_path.write_text(
            """
rop:
  ai_adjudicator:
    system: "System prompt"
    user: >
      Analyze this bounded ROP event.

      Event JSON:
      {event_json}
""".strip()
            + "\n",
            encoding="utf-8",
        )

        prompt = _build_adjudicator_prompt(
            prompts_cfg={"path": str(prompts_path), "store": False},
            event={
                "event_id": "evt-prompt",
                "sender": "lead@example.com",
                "subject": "Need welding quote",
                "case_type": "new_lead",
                "confidence": 0.5,
                "is_fallback": True,
            },
            prompt_key="rop.ai_adjudicator",
            max_chars=8000,
        )

        assert "Analyze this bounded ROP event." in prompt
        assert "Template variables JSON" not in prompt
        assert '"event_id": "evt-prompt"' in prompt

    def test_prompt_sanitizes_html_and_base64_like_text(self) -> None:
        event = _sample_eligible_event()
        event["sender"] = "<b>sender@example.com</b>"
        event["subject"] = (
            "<div>Hello</div> data:image/png;base64,AAAAABBBBBCCCCCDDDDDEEEEEFFFFFGGGGGHHHHH"
        )
        event["body_preview"] = (
            "<p>Visible text</p> "
            "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFB"
        )
        prompt = _build_adjudicator_prompt(
            prompts_cfg=_minimal_prompts_cfg(),
            event=event,
            prompt_key="rop.ai_adjudicator",
            max_chars=8000,
        )
        assert "<b>" not in prompt
        assert "<div>" not in prompt
        assert "data:image/png;base64" not in prompt
        assert (
            "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFB"
            not in prompt
        )
        assert "sender@example.com" in prompt
        assert "Visible text" in prompt

    def test_prompt_respects_max_chars(self) -> None:
        prompt = _build_adjudicator_prompt(
            prompts_cfg=_minimal_prompts_cfg(),
            event=_sample_eligible_event(),
            prompt_key="rop.ai_adjudicator",
            max_chars=100,
        )
        assert len(prompt) <= 100


class TestResponseParsing:
    def test_valid_json(self) -> None:
        result = _parse_ai_response('{"case_type": "new_lead", "confidence": 0.85}')
        assert result is not None
        assert result["case_type"] == "new_lead"

    def test_invalid_json_returns_none(self) -> None:
        assert _parse_ai_response("not json") is None


class TestValidation:
    def test_valid_output(self) -> None:
        validated = _validate_ai_output(
            {
                "case_type": "new_lead",
                "case_subtype": "tender",
                "recommended_queue": "tender",
                "should_rop_see": True,
                "correct_action": "review_tender",
                "confidence": 0.85,
                "reason": "Clear RFQ content",
                "risk_flags": [],
            }
        )
        assert validated["errors"] == []
        assert validated["case_type"] == "new_lead"

    def test_invalid_taxonomy_adds_errors(self) -> None:
        validated = _validate_ai_output(
            {
                "case_type": "alien_invasion",
                "recommended_queue": "mars",
                "correct_action": "launch_missiles",
                "confidence": 0.95,
                "risk_flags": [],
            }
        )
        assert validated["errors"]


class TestProviderCall:
    def test_missing_api_key_returns_none(self) -> None:
        result = call_openai_responses_api(
            prompt="test",
            provider="openai_responses",
            model="gpt-5.4-mini",
            api_key="",
            base_url="https://api.openai.com/v1",
            timeout_seconds=10,
            logger=_null_logger(),
        )
        assert result is None

    def test_provider_timeout_returns_none(self) -> None:
        import socket

        def _raise_timeout(*args: object, **kwargs: object) -> object:
            raise socket.timeout("timed out")

        with patch(
            "beeagent_module.core.rop_ai_adjudicator.request.urlopen",
            _raise_timeout,
        ):
            result = call_openai_responses_api(
                prompt="test",
                provider="openai_responses",
                model="gpt-5.4-mini",
                api_key="sk-test",
                base_url="https://api.openai.com/v1",
                timeout_seconds=5,
                logger=_null_logger(),
            )
        assert result is None


class TestAdjudicatorForEvent:
    def test_not_eligible_skips_provider(self) -> None:
        result = run_adjudicator_for_event(
            event=_sample_ineligible_event(),
            adj_cfg=_minimal_adj_cfg(),
            profile_cfg=_minimal_profile_cfg(),
            prompts_cfg=_minimal_prompts_cfg(),
            logger=_null_logger(),
        )
        assert result["decision"]["status"] == "skipped"
        assert result["result"]["ai_status"] == "not_eligible"
        assert result["result"]["ai_used"] is False

    def test_enabled_missing_api_key_degrades(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            result = run_adjudicator_for_event(
                event=_sample_eligible_event(),
                adj_cfg=_minimal_adj_cfg(),
                profile_cfg=_minimal_profile_cfg(),
                prompts_cfg=_minimal_prompts_cfg(),
                logger=_null_logger(),
            )
        assert result["decision"]["status"] == "degraded"
        assert result["decision"]["reason_code"] == "missing_api_key"
        assert result["result"]["ai_error"]

    def test_provider_failure_preserves_deterministic(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            with patch(
                "beeagent_module.core.rop_ai_adjudicator.call_openai_responses_api",
                lambda **kwargs: None,
            ):
                result = run_adjudicator_for_event(
                    event=_sample_supplier_spam_false_positive_event(),
                    adj_cfg=_minimal_adj_cfg(),
                    profile_cfg=_minimal_profile_cfg(),
                    prompts_cfg=_minimal_prompts_cfg(),
                    logger=_null_logger(),
                )
        assert result["decision"]["status"] == "degraded"
        assert result["result"]["ai_status"] == "degraded"
        assert result["result"]["final_correct_action"] == "check_bitrix"

    def test_valid_ai_output_accepted(self) -> None:
        def _return_valid(**kwargs: object) -> str:
            return json.dumps(
                {
                    "case_type": "new_lead",
                    "case_subtype": "tender",
                    "recommended_queue": "tender",
                    "should_rop_see": True,
                    "correct_action": "review_tender",
                    "confidence": 0.85,
                    "reason": "Clear RFQ content",
                    "risk_flags": [],
                }
            )

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            with patch(
                "beeagent_module.core.rop_ai_adjudicator.call_openai_responses_api",
                _return_valid,
            ):
                result = run_adjudicator_for_event(
                    event=_sample_eligible_event(),
                    adj_cfg=_minimal_adj_cfg(),
                    profile_cfg=_minimal_profile_cfg(),
                    prompts_cfg=_minimal_prompts_cfg(),
                    logger=_null_logger(),
                )
        assert result["decision"]["status"] == "ok"
        assert result["result"]["final_case_type"] == "new_lead"
        assert result["result"]["ai_confidence"] == 0.85
        assert result["result"]["ai_reason"] == "Clear RFQ content"
        assert result["result"]["errors"] == []

    def test_conflicting_high_confidence_ai_output_routes_to_manual_review(
        self,
    ) -> None:
        def _return_conflicting(**kwargs: object) -> str:
            return json.dumps(
                {
                    "case_type": "existing_deal",
                    "case_subtype": "existing_deal_procurement",
                    "recommended_queue": "procurement",
                    "should_rop_see": True,
                    "correct_action": "check_bitrix",
                    "confidence": 0.90,
                    "reason": "Looks like procurement continuation",
                    "risk_flags": [],
                }
            )

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            with patch(
                "beeagent_module.core.rop_ai_adjudicator.call_openai_responses_api",
                _return_conflicting,
            ):
                result = run_adjudicator_for_event(
                    event=_sample_supplier_spam_false_positive_event(),
                    adj_cfg=_minimal_adj_cfg(),
                    profile_cfg=_minimal_profile_cfg(),
                    prompts_cfg=_minimal_prompts_cfg(),
                    logger=_null_logger(),
                )
        assert result["result"]["ai_status"] == "manual_review_degrade"
        assert result["result"]["final_case_type"] == "existing_deal"
        assert result["result"]["final_recommended_queue"] == "manual_review"
        assert result["result"]["final_correct_action"] == "manual_review"
        assert result["result"]["merge_reason"] == "ai_output_conflict_manual_review"

    def test_low_confidence_conflict_routes_to_manual_review(self) -> None:
        def _return_low_conf(**kwargs: object) -> str:
            return json.dumps(
                {
                    "case_type": "irrelevant",
                    "case_subtype": "spam_or_bulk",
                    "recommended_queue": "ignore",
                    "should_rop_see": False,
                    "correct_action": "ignore",
                    "confidence": 0.35,
                    "reason": (
                        "Looks like supplier/newsletter spam but confidence is below "
                        "threshold."
                    ),
                    "risk_flags": ["low_signal"],
                }
            )

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            with patch(
                "beeagent_module.core.rop_ai_adjudicator.call_openai_responses_api",
                _return_low_conf,
            ):
                result = run_adjudicator_for_event(
                    event=_sample_supplier_spam_false_positive_event(),
                    adj_cfg=_minimal_adj_cfg(),
                    profile_cfg=_minimal_profile_cfg(),
                    prompts_cfg=_minimal_prompts_cfg(),
                    logger=_null_logger(),
                )
        assert result["decision"]["status"] == "manual_review_degrade"
        assert result["result"]["ai_status"] == "manual_review_degrade"
        assert result["result"]["final_case_type"] == "existing_deal"
        assert result["result"]["final_recommended_queue"] == "manual_review"
        assert result["result"]["final_correct_action"] == "manual_review"
        assert result["result"]["final_should_rop_see"] is True
        assert result["result"]["merge_reason"] == "ai_low_confidence_manual_review"
        assert result["result"]["ai_error"]

    def test_invalid_json_does_not_crash(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            with patch(
                "beeagent_module.core.rop_ai_adjudicator.call_openai_responses_api",
                lambda **kwargs: "not json",
            ):
                result = run_adjudicator_for_event(
                    event=_sample_eligible_event(),
                    adj_cfg=_minimal_adj_cfg(),
                    profile_cfg=_minimal_profile_cfg(),
                    prompts_cfg=_minimal_prompts_cfg(),
                    logger=_null_logger(),
                )
        assert result["decision"]["status"] == "invalid"
        assert result["result"]["final_case_type"] == "unknown"
        assert result["result"]["final_correct_action"] == "manual_review"
        assert result["result"]["ai_error"]

    def test_invalid_taxonomy_rejected(self) -> None:
        def _return_invalid_taxonomy(**kwargs: object) -> str:
            return json.dumps(
                {
                    "case_type": "alien_invasion",
                    "recommended_queue": "mars",
                    "correct_action": "launch_missiles",
                    "confidence": 0.95,
                    "reason": "Bad taxonomy",
                    "risk_flags": [],
                }
            )

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            with patch(
                "beeagent_module.core.rop_ai_adjudicator.call_openai_responses_api",
                _return_invalid_taxonomy,
            ):
                result = run_adjudicator_for_event(
                    event=_sample_eligible_event(),
                    adj_cfg=_minimal_adj_cfg(),
                    profile_cfg=_minimal_profile_cfg(),
                    prompts_cfg=_minimal_prompts_cfg(),
                    logger=_null_logger(),
                )
        assert result["result"]["ai_status"] == "manual_review_degrade"
        assert result["result"]["final_case_type"] == "unknown"
        assert result["result"]["final_recommended_queue"] == "manual_review"
        assert result["result"]["errors"]

    def test_validation_error_conflict_routes_to_manual_review(self) -> None:
        def _return_invalid_taxonomy(**kwargs: object) -> str:
            return json.dumps(
                {
                    "case_type": "",
                    "recommended_queue": "",
                    "correct_action": "",
                    "confidence": 0.78,
                    "reason": "Looks like supplier spam",
                    "risk_flags": ["supplier_outreach", "unknown_flag"],
                }
            )

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            with patch(
                "beeagent_module.core.rop_ai_adjudicator.call_openai_responses_api",
                _return_invalid_taxonomy,
            ):
                result = run_adjudicator_for_event(
                    event=_sample_supplier_spam_false_positive_event(),
                    adj_cfg=_minimal_adj_cfg(),
                    profile_cfg=_minimal_profile_cfg(),
                    prompts_cfg=_minimal_prompts_cfg(),
                    logger=_null_logger(),
                )
        assert result["result"]["ai_status"] == "manual_review_degrade"
        assert result["result"]["final_case_type"] == "existing_deal"
        assert result["result"]["final_recommended_queue"] == "manual_review"
        assert result["result"]["final_correct_action"] == "manual_review"
        assert result["result"]["merge_reason"] == "ai_validation_error_manual_review"


class TestAdjudicatorBatch:
    def test_batch_disabled_by_default(self) -> None:
        requests, decisions, results, counters = run_adjudicator_batch(
            events=[_sample_eligible_event()],
            settings=_settings(ai_assist_enabled=False, adjudicator_enabled=False),
            logger=_null_logger(),
        )
        assert requests == []
        assert decisions == []
        assert results == []
        assert counters["adjudicator_enabled"] == 0

    def test_gate_true_calls_provider_once(self) -> None:
        calls: list[str] = []

        def _fake_call(**kwargs: object) -> str:
            calls.append("called")
            return json.dumps(
                {
                    "case_type": "new_lead",
                    "case_subtype": "tender",
                    "recommended_queue": "tender",
                    "should_rop_see": True,
                    "correct_action": "review_tender",
                    "confidence": 0.85,
                    "reason": "Clear RFQ content",
                    "risk_flags": [],
                }
            )

        settings = _settings(ai_assist_enabled=True, adjudicator_enabled=True)
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            with patch(
                "beeagent_module.core.rop_ai_adjudicator.call_openai_responses_api",
                _fake_call,
            ):
                _, _, results, counters = run_adjudicator_batch(
                    events=[_sample_ineligible_event(), _sample_eligible_event()],
                    settings=settings,
                    logger=_null_logger(),
                )
        assert len(calls) == 1
        assert counters["adjudicator_eligible_count"] == 1
        assert results[0]["ai_status"] == "ok"


class TestArtifacts:
    def test_write_adjudicator_artifacts(self, tmp_path: Path) -> None:
        refs = write_adjudicator_artifacts(
            storage_dir=tmp_path,
            run_id="test-artifact-run",
            requests=[{"event_id": "evt-001", "eligible": True}],
            decisions=[{"event_id": "evt-001", "status": "ok"}],
            results=[
                {
                    "event_id": "evt-001",
                    "ai_used": True,
                    "ai_provider": "openai_responses",
                    "ai_model": "gpt-5.4-mini",
                    "ai_status": "ok",
                    "ai_confidence": 0.91,
                    "ai_reason": "Clear RFQ content",
                    "ai_risk_flags": [],
                    "ai_error": "",
                    "deterministic_case_type": "unknown",
                    "deterministic_case_subtype": None,
                    "deterministic_recommended_queue": "manual_review",
                    "deterministic_correct_action": "manual_review",
                    "deterministic_confidence": 0.0,
                    "deterministic_reason_code": "fallback_low_signal",
                    "final_case_type": "new_lead",
                    "final_case_subtype": "tender",
                    "final_recommended_queue": "tender",
                    "final_correct_action": "review_tender",
                    "final_should_rop_see": True,
                    "merge_reason": "validated_ai_adjudicator_output",
                    "errors": [],
                }
            ],
            counters={
                "adjudicator_enabled": 1,
                "adjudicator_eligible_count": 1,
                "adjudicator_used_count": 1,
                "adjudicator_degraded_count": 0,
            },
            logger=_null_logger(),
        )
        assert len(refs) == 3
        content = json.loads(
            (
                tmp_path
                / "runs"
                / "test-artifact-run"
                / "rop_ai_adjudicator_results.json"
            ).read_text(encoding="utf-8")
        )
        result = content["results"][0]
        assert result["ai_provider"] == "openai_responses"
        assert result["ai_model"] == "gpt-5.4-mini"

    def test_request_artifact_no_secrets(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            with patch(
                "beeagent_module.core.rop_ai_adjudicator.call_openai_responses_api",
                lambda **kwargs: json.dumps(
                    {
                        "case_type": "new_lead",
                        "case_subtype": "tender",
                        "recommended_queue": "tender",
                        "should_rop_see": True,
                        "correct_action": "review_tender",
                        "confidence": 0.85,
                        "reason": "Clear RFQ content",
                        "risk_flags": [],
                    }
                ),
            ):
                result = run_adjudicator_for_event(
                    event=_sample_eligible_event(),
                    adj_cfg=_minimal_adj_cfg(),
                    profile_cfg=_minimal_profile_cfg(),
                    prompts_cfg=_minimal_prompts_cfg(),
                    logger=_null_logger(),
                )
        artifact = json.dumps(result["request"], ensure_ascii=False)
        assert "OPENAI_API_KEY" not in artifact
        assert "sk-test" not in artifact
        assert "raw_eml" not in artifact

    def test_request_artifact_preview_is_sanitized(self) -> None:
        secret_env_value = (
            "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFB"
            "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFB"
        )
        event = _sample_eligible_event()
        event["sender"] = "<b>lead@example.com</b>"
        event["subject"] = (
            "<div>Need quote</div> "
            "data:image/png;base64,AAAAABBBBBCCCCCDDDDDEEEEEFFFFFGGGGGHHHHH"
        )
        event["clean_subject"] = f"<p>Need quote</p> {secret_env_value}"
        event["body_preview"] = f"<p>Visible text</p> {secret_env_value}"
        event["attachments"] = [
            {
                "filename": f"<script>spec.pdf</script> {secret_env_value}",
                "content_type": f"<b>text/plain</b> {secret_env_value}",
            }
        ]

        artifact = _build_request_artifact(
            event,
            eligible=True,
            profile_cfg=_minimal_profile_cfg(),
            adj_cfg=_minimal_adj_cfg(),
            prompts_cfg=_minimal_prompts_cfg(),
            prompt=None,
        )
        preview = artifact["request_preview"]
        serialized = json.dumps(artifact, ensure_ascii=False)

        assert preview["sender"] == "lead@example.com"
        assert preview["subject"] == "Need quote"
        assert preview["clean_subject"] == "Need quote"
        assert preview["attachment_filenames"] == ["spec.pdf"]
        assert preview["attachment_mime_types"] == ["text/plain"]
        assert preview["body_preview_chars"] == len("Visible text")

        assert "<b>" not in serialized
        assert "<div>" not in serialized
        assert "<script>" not in serialized
        assert "data:image/png;base64" not in serialized
        assert secret_env_value not in serialized
        assert "lead@example.com" in serialized
        assert "Need quote" in serialized
        assert "spec.pdf" in serialized


class TestConfig:
    def test_adjudicator_config_disabled_is_valid(self) -> None:
        from beeagent_module.core.settings import _validate_rop_ai_adjudicator_settings

        _validate_rop_ai_adjudicator_settings(
            _settings(ai_assist_enabled=False, adjudicator_enabled=False)
        )

    def test_adjudicator_enabled_requires_ai_assist(self) -> None:
        from beeagent_module.core.settings import _validate_rop_ai_adjudicator_settings

        with pytest.raises(RuntimeError, match="requires rop.ai_assist.enabled: true"):
            _validate_rop_ai_adjudicator_settings(
                _settings(ai_assist_enabled=False, adjudicator_enabled=True)
            )

    def test_adjudicator_enabled_missing_env_fails(self) -> None:
        from beeagent_module.core.settings import _validate_rop_ai_adjudicator_settings

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
                _validate_rop_ai_adjudicator_settings(
                    _settings(ai_assist_enabled=True, adjudicator_enabled=True)
                )

    def test_openai_compatible_provider_rejected_for_enabled_adjudicator(self) -> None:
        from beeagent_module.core.settings import _validate_rop_ai_adjudicator_settings

        profiles = {
            "deepseek": {
                **_minimal_profile_cfg(
                    provider="openai_compatible",
                    api_key_env="DEEPSEEK_API_KEY",
                    base_url="https://api.deepseek.com/v1",
                    model="deepseek-chat",
                ),
                "enabled": True,
            }
        }
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}, clear=True):
            with pytest.raises(RuntimeError, match="expected openai_responses"):
                _validate_rop_ai_adjudicator_settings(
                    _settings(
                        ai_assist_enabled=True,
                        adjudicator_enabled=True,
                        profiles=profiles,
                    )
                )

    def test_exactly_one_enabled_profile_required(self) -> None:
        from beeagent_module.core.settings import _validate_rop_ai_adjudicator_settings

        profiles = {
            "openai": _minimal_profile_cfg(),
            "deepseek": {
                **_minimal_profile_cfg(
                    provider="openai_compatible",
                    api_key_env="DEEPSEEK_API_KEY",
                    base_url="https://api.deepseek.com/v1",
                    model="deepseek-chat",
                ),
                "enabled": True,
            },
        }
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "sk-test", "DEEPSEEK_API_KEY": "sk-test"},
            clear=True,
        ):
            with pytest.raises(RuntimeError, match="Exactly one ai.profiles"):
                _validate_rop_ai_adjudicator_settings(
                    _settings(
                        ai_assist_enabled=True,
                        adjudicator_enabled=True,
                        profiles=profiles,
                    )
                )
