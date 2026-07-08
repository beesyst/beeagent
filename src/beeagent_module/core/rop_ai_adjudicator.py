from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib import request

from beeagent_module.core.llm import _build_prompt_messages_by_key

_SUPPORTED_AI_PROVIDERS = frozenset({"openai_responses"})
_DATA_BASE64_RE = re.compile(
    r"data:[^;\s]+;base64,[A-Za-z0-9+/=\s]{20,}",
    re.IGNORECASE,
)
_LONG_BASE64_RE = re.compile(r"\b(?:[A-Za-z0-9+/]{80,}={0,2})\b")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_SUPPLIER_OR_PRODUCT_MARKERS = frozenset(
    {
        "supplier",
        "manufacturer",
        "factory",
        "catalog",
        "catalogue",
        "presentation",
        "company profile",
        "product line",
        "machine supplied",
        "we produce",
        "we offer",
        "sole partner",
        "distributor",
        "dealer",
        "price list",
        "quotation for our products",
    }
)
_NEWSLETTER_HR_LEGAL_TRAINING_MARKERS = frozenset(
    {
        "unsubscribe",
        "view in browser",
        "newsletter",
        "webinar",
        "training",
        "seminar",
        "hr",
        "legal update",
        "employment contract",
        "labor contract",
        "кадровик",
        "гпх",
        "трудовым договором",
        "семинар",
        "обучение",
        "вебинар",
        "программа семинара",
        "заявка на участие",
    }
)
_DANGEROUS_DETERMINISTIC_ACTIONS = frozenset(
    {
        "attach_to_deal",
        "check_bitrix",
        "review_new_lead",
        "review_tender",
    }
)
_RISKY_REASON_CODE_PARTS = (
    "fallback",
    "ambiguous",
    "low_signal",
    "existing_deal_reference_signal",
)


def _resolve_adj_config(settings: dict) -> dict[str, Any]:
    adj_cfg = settings.get("rop", {}).get("ai_assist", {}).get("adjudicator", {})
    if not isinstance(adj_cfg, dict):
        return {}
    return adj_cfg


def _resolve_ai_prompts_cfg(settings: dict) -> dict[str, Any]:
    prompts_cfg = settings.get("ai", {}).get("prompts", {})
    if not isinstance(prompts_cfg, dict):
        raise RuntimeError("Invalid ai.prompts config")
    return prompts_cfg


def _resolve_active_ai_profile(settings: dict) -> tuple[str, dict[str, Any]]:
    profiles = settings.get("ai", {}).get("profiles", {})
    if not isinstance(profiles, dict):
        raise RuntimeError("Invalid ai.profiles config")

    enabled_profiles = [
        (profile_name, profile_cfg)
        for profile_name, profile_cfg in profiles.items()
        if isinstance(profile_cfg, dict) and profile_cfg.get("enabled") is True
    ]
    if len(enabled_profiles) != 1:
        raise RuntimeError("Exactly one ai.profiles.*.enabled must be true")
    return enabled_profiles[0]


def _sanitize_prompt_text(value: Any, max_chars: int) -> str:
    if value is None:
        return ""

    text = str(value)
    text = _DATA_BASE64_RE.sub(" ", text)
    text = _LONG_BASE64_RE.sub(" ", text)
    text = _HTML_TAG_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text[:max_chars]


def _build_prompt_event_payload(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": event.get("event_id", ""),
        "source_id": event.get("source_id", ""),
        "sender": _sanitize_prompt_text(event.get("sender") or "", 200),
        "original_sender_email": _sanitize_prompt_text(
            event.get("original_sender_email") or event.get("original_sender") or "",
            200,
        ),
        "subject": _sanitize_prompt_text(event.get("subject") or "", 200),
        "clean_subject": _sanitize_prompt_text(
            event.get("clean_subject") or "",
            200,
        ),
        "transport_labels": event.get("transport_labels", []),
        "spam_label_present": event.get("spam_label_present", False),
        "reply_label_present": event.get("reply_label_present", False),
        "forwarded_wrapper": event.get("forwarded_wrapper", False),
        "body_preview": _sanitize_prompt_text(
            event.get("body_preview")
            or event.get("text_preview")
            or event.get("body")
            or "",
            500,
        ),
        "attachment_filenames": [
            _sanitize_prompt_text(attachment.get("filename", ""), 200)
            for attachment in (event.get("attachments") or [])
            if isinstance(attachment, dict) and attachment.get("filename")
        ],
        "attachment_mime_types": [
            _sanitize_prompt_text(attachment.get("content_type", ""), 200)
            for attachment in (event.get("attachments") or [])
            if isinstance(attachment, dict) and attachment.get("content_type")
        ],
        "deterministic_case_type": _deterministic_value(event, "case_type", "unknown"),
        "deterministic_case_subtype": _deterministic_value(event, "case_subtype", None),
        "deterministic_recommended_queue": _deterministic_value(
            event,
            "recommended_queue",
            None,
        ),
        "deterministic_correct_action": _deterministic_value(
            event,
            "correct_action",
            None,
        ),
        "deterministic_confidence": _deterministic_value(event, "confidence", 0.0),
        "deterministic_reason_code": _deterministic_value(event, "reason_code", ""),
        "is_fallback": event.get("is_fallback", False),
        "risk_flags": event.get("risk_flags") or event.get("warnings") or [],
    }


def _event_text_for_marker_scan(event: dict[str, Any]) -> str:
    payload = _build_prompt_event_payload(event)
    parts: list[str] = [
        payload.get("sender", ""),
        payload.get("original_sender_email", ""),
        payload.get("subject", ""),
        payload.get("clean_subject", ""),
        payload.get("body_preview", ""),
    ]
    parts.extend(payload.get("attachment_filenames", []))
    parts.extend(payload.get("attachment_mime_types", []))
    return " ".join(part for part in parts if isinstance(part, str)).casefold()


def _contains_any_marker(text: str, markers: set[str] | frozenset[str]) -> bool:
    return any(marker in text for marker in markers)


def _has_supplier_or_product_outreach_signal(event: dict[str, Any]) -> bool:
    return _contains_any_marker(
        _event_text_for_marker_scan(event),
        _SUPPLIER_OR_PRODUCT_MARKERS,
    )


def _has_newsletter_hr_legal_training_signal(event: dict[str, Any]) -> bool:
    return _contains_any_marker(
        _event_text_for_marker_scan(event),
        _NEWSLETTER_HR_LEGAL_TRAINING_MARKERS,
    )


def _has_conflict_or_risky_deterministic_signal(
    event: dict[str, Any],
    min_confidence: float,
) -> bool:
    if event.get("is_fallback", False):
        return True

    deterministic_case_type = _deterministic_value(event, "case_type", "unknown")
    if deterministic_case_type == "unknown":
        return True

    deterministic_confidence = _deterministic_value(event, "confidence", 0.0)
    if not isinstance(deterministic_confidence, (int, float)):
        deterministic_confidence = 0.0
    if float(deterministic_confidence) < min_confidence:
        return True

    reason_code = str(_deterministic_value(event, "reason_code", "") or "").casefold()
    if any(part in reason_code for part in _RISKY_REASON_CODE_PARTS):
        return True

    if event.get(
        "spam_label_present", False
    ) and _has_supplier_or_product_outreach_signal(event):
        return True

    if _has_newsletter_hr_legal_training_signal(event):
        return True

    deterministic_action = _deterministic_value(event, "correct_action", "")
    if deterministic_action in _DANGEROUS_DETERMINISTIC_ACTIONS:
        return True

    return False


def _ai_output_conflicts_with_marker_signals(
    event: dict[str, Any],
    validated: dict[str, Any],
) -> bool:
    ai_case_type = validated.get("case_type")
    ai_correct_action = validated.get("correct_action")
    risky_ai_continuation = (
        ai_case_type in {"existing_deal", "new_lead"}
        or ai_correct_action in _DANGEROUS_DETERMINISTIC_ACTIONS
    )
    if not risky_ai_continuation:
        return False

    if event.get(
        "spam_label_present", False
    ) and _has_supplier_or_product_outreach_signal(event):
        return True

    if _has_newsletter_hr_legal_training_signal(event):
        return True

    return False


def _build_adjudicator_prompt(
    prompts_cfg: dict[str, Any],
    event: dict[str, Any],
    prompt_key: str,
    max_chars: int,
) -> str:
    event_json = json.dumps(_build_prompt_event_payload(event), ensure_ascii=False)
    system_prompt, user_prompt = _build_prompt_messages_by_key(
        llm_cfg={"prompts_path": prompts_cfg["path"]},
        prompt_key=prompt_key,
        template_vars={"event_json": event_json},
    )
    prompt = f"System:\n{system_prompt}\n\nUser:\n{user_prompt}"
    if len(prompt) > max_chars:
        return prompt[:max_chars]
    return prompt


def _parse_ai_response(raw_text: str) -> dict[str, Any] | None:
    if not raw_text or not raw_text.strip():
        return None

    cleaned = raw_text.strip()

    if cleaned.startswith("```"):
        end = cleaned.find("```", 3)
        if end != -1:
            cleaned = cleaned[3:end].strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        try:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                data = json.loads(cleaned[start : end + 1])
            else:
                return None
        except json.JSONDecodeError:
            return None

    if not isinstance(data, dict):
        return None

    return data


def _validate_ai_output(data: dict[str, Any]) -> dict[str, Any]:
    valid_case_types = {"new_lead", "existing_deal", "irrelevant"}
    valid_queues = {
        "sales",
        "tender",
        "logistics",
        "finance",
        "procurement",
        "manual_review",
        "ignore",
    }
    valid_actions = {
        "review_new_lead",
        "review_tender",
        "attach_to_deal",
        "check_bitrix",
        "manual_review",
        "ignore",
    }
    valid_risk_flags = {
        "marketing_conflict",
        "spam_rfq_conflict",
        "supplier_outreach",
        "low_signal",
        "ambiguous_bitrix",
    }

    validated: dict[str, Any] = {}
    errors: list[str] = []

    case_type = data.get("case_type", "")
    if isinstance(case_type, str) and case_type in valid_case_types:
        validated["case_type"] = case_type
    else:
        errors.append(f"invalid case_type: {case_type}")
        validated["case_type"] = "irrelevant"

    subtype = data.get("case_subtype")
    validated["case_subtype"] = subtype if isinstance(subtype, str) else None

    queue = data.get("recommended_queue", "")
    if isinstance(queue, str) and queue in valid_queues:
        validated["recommended_queue"] = queue
    else:
        errors.append(f"invalid recommended_queue: {queue}")
        validated["recommended_queue"] = "manual_review"

    should_see = data.get("should_rop_see")
    validated["should_rop_see"] = (
        bool(should_see) if isinstance(should_see, bool) else True
    )

    action = data.get("correct_action", "")
    if isinstance(action, str) and action in valid_actions:
        validated["correct_action"] = action
    else:
        errors.append(f"invalid correct_action: {action}")
        validated["correct_action"] = "manual_review"

    confidence = data.get("confidence", 0.0)
    if isinstance(confidence, (int, float)) and 0.0 <= confidence <= 1.0:
        validated["confidence"] = float(confidence)
    else:
        errors.append(f"invalid confidence: {confidence}")
        validated["confidence"] = 0.0

    reason = data.get("reason")
    validated["reason"] = reason if isinstance(reason, str) else ""

    risk_flags = data.get("risk_flags", [])
    if isinstance(risk_flags, list):
        cleaned_flags: list[str] = []
        for flag in risk_flags:
            if isinstance(flag, str) and flag in valid_risk_flags:
                cleaned_flags.append(flag)
            elif isinstance(flag, str):
                errors.append(f"unknown risk_flag: {flag}")
        validated["risk_flags"] = cleaned_flags
    else:
        validated["risk_flags"] = []

    validated["errors"] = errors
    return validated


def _is_event_eligible_for_adjudicator(event: dict[str, Any]) -> bool:
    case_type = event.get("case_type", "")
    is_fallback = event.get("is_fallback", False)
    confidence = event.get("confidence", 1.0)
    if isinstance(confidence, (int, float)):
        confidence = float(confidence)
    else:
        confidence = 1.0

    if is_fallback:
        return True

    if case_type == "unknown":
        return True

    if confidence < 0.60:
        return True

    eligible_low_conf_types = {"existing_deal", "follow_up"}
    if case_type in eligible_low_conf_types and confidence < 0.80:
        return True

    ai_assist_eligible = event.get("ai_assist_eligible")
    if ai_assist_eligible is True:
        return True

    high_risk_case_types = {"existing_deal", "new_lead"}
    if (
        case_type in high_risk_case_types
        and event.get("spam_label_present", False)
        and _has_supplier_or_product_outreach_signal(event)
    ):
        return True

    if case_type in high_risk_case_types and _has_newsletter_hr_legal_training_signal(
        event
    ):
        return True

    return False


def call_openai_responses_api(
    prompt: str,
    provider: str,
    model: str,
    api_key: str,
    base_url: str,
    timeout_seconds: int,
    logger: logging.Logger,
) -> str | None:
    if provider not in _SUPPORTED_AI_PROVIDERS:
        logger.warning("ai_adjudicator: unsupported provider=%s", provider)
        return None

    if not api_key.strip():
        logger.warning("ai_adjudicator: API key is empty")
        return None

    api_url = base_url.rstrip("/") + "/responses"

    payload = {
        "model": model,
        "input": prompt,
        "temperature": 0.1,
        "max_output_tokens": 500,
        "text": {"format": {"type": "json_object"}},
    }

    try:
        req = request.Request(
            api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=timeout_seconds) as resp:
            raw = resp.read().decode("utf-8")
        response_data = json.loads(raw)

        output_list = response_data.get("output", [])
        if not output_list:
            logger.warning("ai_adjudicator: no output in Responses API response")
            return None

        content_text = ""
        for item in output_list:
            if not isinstance(item, dict):
                continue
            content = item.get("content", "")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "output_text":
                        content_text += part.get("text", "")
            elif isinstance(content, str):
                content_text += content

        if not content_text:
            logger.warning("ai_adjudicator: empty content in Responses API response")
            return None

        return content_text
    except Exception as exc:
        logger.warning("ai_adjudicator: provider call failed: %s", exc)
        return None


def _deterministic_value(event: dict[str, Any], key: str, default: Any) -> Any:
    return event.get(f"deterministic_{key}", event.get(key, default))


def _build_result(
    event: dict[str, Any],
    *,
    ai_used: bool,
    ai_provider: str,
    ai_model: str,
    ai_status: str,
    ai_confidence: float | None,
    ai_reason: str,
    ai_risk_flags: list[str],
    ai_error: str,
    final_case_type: Any,
    final_case_subtype: Any,
    final_recommended_queue: Any,
    final_correct_action: Any,
    final_should_rop_see: Any,
    merge_reason: str,
    errors: list[str],
) -> dict[str, Any]:
    return {
        "event_id": event.get("event_id", ""),
        "ai_used": ai_used,
        "ai_provider": ai_provider,
        "ai_model": ai_model,
        "ai_status": ai_status,
        "ai_confidence": ai_confidence,
        "ai_reason": ai_reason,
        "ai_risk_flags": ai_risk_flags,
        "ai_error": ai_error,
        "deterministic_case_type": _deterministic_value(event, "case_type", "unknown"),
        "deterministic_case_subtype": _deterministic_value(event, "case_subtype", None),
        "deterministic_recommended_queue": _deterministic_value(
            event,
            "recommended_queue",
            None,
        ),
        "deterministic_correct_action": _deterministic_value(
            event,
            "correct_action",
            None,
        ),
        "deterministic_confidence": _deterministic_value(event, "confidence", 0.0),
        "deterministic_reason_code": _deterministic_value(event, "reason_code", ""),
        "final_case_type": final_case_type,
        "final_case_subtype": final_case_subtype,
        "final_recommended_queue": final_recommended_queue,
        "final_correct_action": final_correct_action,
        "final_should_rop_see": final_should_rop_see,
        "merge_reason": merge_reason,
        "errors": errors,
    }


def _build_request_artifact(
    event: dict[str, Any],
    *,
    eligible: bool,
    profile_cfg: dict[str, Any],
    adj_cfg: dict[str, Any],
    prompts_cfg: dict[str, Any],
    prompt: str | None,
) -> dict[str, Any]:
    safe_payload = _build_prompt_event_payload(event)

    artifact = {
        "event_id": safe_payload["event_id"],
        "eligible": eligible,
        "provider": profile_cfg.get("provider", ""),
        "model": profile_cfg.get("model", ""),
        "prompt_key": adj_cfg.get("prompt_key", ""),
        "request_preview": {
            "event_id": safe_payload["event_id"],
            "source_id": safe_payload["source_id"],
            "sender": safe_payload["sender"],
            "original_sender_email": safe_payload["original_sender_email"],
            "subject": safe_payload["subject"],
            "clean_subject": safe_payload["clean_subject"],
            "transport_labels": safe_payload["transport_labels"],
            "spam_label_present": safe_payload["spam_label_present"],
            "reply_label_present": safe_payload["reply_label_present"],
            "forwarded_wrapper": safe_payload["forwarded_wrapper"],
            "body_preview_chars": len(safe_payload.get("body_preview", "")),
            "attachment_filenames": safe_payload["attachment_filenames"],
            "attachment_mime_types": safe_payload["attachment_mime_types"],
            "deterministic_case_type": safe_payload["deterministic_case_type"],
            "deterministic_case_subtype": safe_payload["deterministic_case_subtype"],
            "deterministic_recommended_queue": safe_payload[
                "deterministic_recommended_queue"
            ],
            "deterministic_correct_action": safe_payload[
                "deterministic_correct_action"
            ],
            "deterministic_confidence": safe_payload["deterministic_confidence"],
            "deterministic_reason_code": safe_payload["deterministic_reason_code"],
            "is_fallback": safe_payload["is_fallback"],
        },
    }

    if prompts_cfg.get("store") and prompt:
        artifact["prompt_chars"] = len(prompt)

    return artifact


def run_adjudicator_for_event(
    event: dict[str, Any],
    adj_cfg: dict[str, Any],
    profile_cfg: dict[str, Any],
    prompts_cfg: dict[str, Any],
    logger: logging.Logger,
) -> dict[str, Any]:
    eligible = _is_event_eligible_for_adjudicator(event)
    provider = profile_cfg["provider"]
    model = profile_cfg["model"]
    final_case_type = event.get("case_type", "unknown")
    final_case_subtype = event.get("case_subtype")
    final_recommended_queue = event.get("recommended_queue")
    final_correct_action = event.get("correct_action")
    final_should_rop_see = event.get("should_rop_see")

    prompt: str | None = None
    if eligible:
        prompt = _build_adjudicator_prompt(
            prompts_cfg=prompts_cfg,
            event=event,
            prompt_key=adj_cfg["prompt_key"],
            max_chars=int(adj_cfg["input_chars_max"]),
        )

    request_artifact = _build_request_artifact(
        event,
        eligible=eligible,
        profile_cfg=profile_cfg,
        adj_cfg=adj_cfg,
        prompts_cfg=prompts_cfg,
        prompt=prompt,
    )

    if not eligible:
        return {
            "request": request_artifact,
            "decision": {
                "event_id": event.get("event_id", ""),
                "provider": provider,
                "model": model,
                "status": "skipped",
                "reason_code": "not_eligible",
                "error": "",
            },
            "result": _build_result(
                event,
                ai_used=False,
                ai_provider=provider,
                ai_model=model,
                ai_status="not_eligible",
                ai_confidence=None,
                ai_reason="",
                ai_risk_flags=[],
                ai_error="",
                final_case_type=final_case_type,
                final_case_subtype=final_case_subtype,
                final_recommended_queue=final_recommended_queue,
                final_correct_action=final_correct_action,
                final_should_rop_see=final_should_rop_see,
                merge_reason="deterministic_result_preserved",
                errors=[],
            ),
        }

    api_key_env = profile_cfg["api_key_env"]
    api_key = os.getenv(api_key_env, "").strip()
    if not api_key:
        error = "AI adjudicator API key not found; deterministic result preserved"
        return {
            "request": request_artifact,
            "decision": {
                "event_id": event.get("event_id", ""),
                "provider": provider,
                "model": model,
                "status": "degraded",
                "reason_code": "missing_api_key",
                "error": error,
            },
            "result": _build_result(
                event,
                ai_used=False,
                ai_provider=provider,
                ai_model=model,
                ai_status="degraded",
                ai_confidence=None,
                ai_reason="",
                ai_risk_flags=[],
                ai_error=error,
                final_case_type=final_case_type,
                final_case_subtype=final_case_subtype,
                final_recommended_queue=final_recommended_queue,
                final_correct_action=final_correct_action,
                final_should_rop_see=final_should_rop_see,
                merge_reason="missing_api_key_deterministic_result_preserved",
                errors=[error],
            ),
        }

    raw_response = call_openai_responses_api(
        prompt=prompt or "",
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=profile_cfg["base_url"],
        timeout_seconds=int(adj_cfg["timeout"]),
        logger=logger,
    )
    if raw_response is None:
        error = "AI provider call failed; deterministic result preserved"
        return {
            "request": request_artifact,
            "decision": {
                "event_id": event.get("event_id", ""),
                "provider": provider,
                "model": model,
                "status": "degraded",
                "reason_code": "provider_call_failed",
                "error": error,
            },
            "result": _build_result(
                event,
                ai_used=False,
                ai_provider=provider,
                ai_model=model,
                ai_status="degraded",
                ai_confidence=None,
                ai_reason="",
                ai_risk_flags=[],
                ai_error=error,
                final_case_type=final_case_type,
                final_case_subtype=final_case_subtype,
                final_recommended_queue=final_recommended_queue,
                final_correct_action=final_correct_action,
                final_should_rop_see=final_should_rop_see,
                merge_reason="provider_call_failed_deterministic_result_preserved",
                errors=[error],
            ),
        }

    parsed = _parse_ai_response(raw_response)
    if parsed is None:
        error = "AI output was unparseable; deterministic result preserved"
        return {
            "request": request_artifact,
            "decision": {
                "event_id": event.get("event_id", ""),
                "provider": provider,
                "model": model,
                "status": "invalid",
                "reason_code": "unparseable_response",
                "error": error,
                "raw_response_preview": raw_response[:500],
            },
            "result": _build_result(
                event,
                ai_used=True,
                ai_provider=provider,
                ai_model=model,
                ai_status="invalid",
                ai_confidence=None,
                ai_reason="",
                ai_risk_flags=[],
                ai_error=error,
                final_case_type=final_case_type,
                final_case_subtype=final_case_subtype,
                final_recommended_queue=final_recommended_queue,
                final_correct_action=final_correct_action,
                final_should_rop_see=final_should_rop_see,
                merge_reason="ai_output_invalid_deterministic_result_preserved",
                errors=[error],
            ),
        }

    validated = _validate_ai_output(parsed)
    ai_confidence = float(validated.get("confidence", 0.0))
    ai_reason = str(validated.get("reason", ""))
    ai_risk_flags = list(validated.get("risk_flags", []))
    validation_errors = list(validated.get("errors", []))
    min_confidence = float(adj_cfg["confidence_accept_min"])

    status = "ok"
    ai_error = ""
    errors = validation_errors
    merge_reason = "validated_ai_adjudicator_output"
    if ai_confidence >= min_confidence and not validation_errors:
        if _ai_output_conflicts_with_marker_signals(event, validated):
            status = "manual_review_degrade"
            final_case_type = _deterministic_value(event, "case_type", "unknown")
            final_case_subtype = None
            final_recommended_queue = "manual_review"
            final_correct_action = "manual_review"
            final_should_rop_see = True
            ai_error = (
                "AI output conflicts with supplier/newsletter conflict signals; "
                "routed to manual review."
            )
            merge_reason = "ai_output_conflict_manual_review"
        else:
            final_case_type = validated.get("case_type") or final_case_type
            final_case_subtype = validated.get("case_subtype")
            final_recommended_queue = (
                validated.get("recommended_queue") or final_recommended_queue
            )
            final_correct_action = (
                validated.get("correct_action") or final_correct_action
            )
            final_should_rop_see = validated.get("should_rop_see")
    elif ai_confidence >= min_confidence and validation_errors:
        if _has_conflict_or_risky_deterministic_signal(event, min_confidence):
            status = "manual_review_degrade"
            final_case_type = _deterministic_value(event, "case_type", "unknown")
            final_case_subtype = None
            final_recommended_queue = "manual_review"
            final_correct_action = "manual_review"
            final_should_rop_see = True
            ai_error = (
                "AI output had validation errors for ambiguous/conflict case; "
                "routed to manual review."
            )
            merge_reason = "ai_validation_error_manual_review"
        else:
            status = "degraded"
            ai_error = "; ".join(validation_errors)
            merge_reason = (
                "ai_output_with_validation_errors_deterministic_result_preserved"
            )
    else:
        errors = [*validation_errors, "ai_confidence_below_acceptance_threshold"]
        if _has_conflict_or_risky_deterministic_signal(event, min_confidence):
            status = "manual_review_degrade"
            final_case_type = _deterministic_value(event, "case_type", "unknown")
            final_case_subtype = None
            final_recommended_queue = "manual_review"
            final_correct_action = "manual_review"
            final_should_rop_see = True
            ai_error = (
                "AI confidence below acceptance threshold for ambiguous/conflict case; "
                "routed to manual review."
            )
            merge_reason = "ai_low_confidence_manual_review"
        else:
            status = "low_confidence"
            ai_error = "AI confidence below acceptance threshold; deterministic result preserved"
            merge_reason = (
                "ai_confidence_below_threshold_deterministic_result_preserved"
            )

    decision = {
        "event_id": event.get("event_id", ""),
        "provider": provider,
        "model": model,
        "status": status,
        "reason_code": merge_reason,
        "ai_case_type": validated.get("case_type"),
        "ai_case_subtype": validated.get("case_subtype"),
        "ai_recommended_queue": validated.get("recommended_queue"),
        "ai_correct_action": validated.get("correct_action"),
        "ai_should_rop_see": validated.get("should_rop_see"),
        "ai_confidence": ai_confidence,
        "ai_reason": ai_reason,
        "ai_risk_flags": ai_risk_flags,
        "validation_errors": validation_errors,
        "error": ai_error,
    }

    return {
        "request": request_artifact,
        "decision": decision,
        "result": _build_result(
            event,
            ai_used=True,
            ai_provider=provider,
            ai_model=model,
            ai_status=status,
            ai_confidence=ai_confidence,
            ai_reason=ai_reason,
            ai_risk_flags=ai_risk_flags,
            ai_error=ai_error,
            final_case_type=final_case_type,
            final_case_subtype=final_case_subtype,
            final_recommended_queue=final_recommended_queue,
            final_correct_action=final_correct_action,
            final_should_rop_see=final_should_rop_see,
            merge_reason=merge_reason,
            errors=errors,
        ),
    }


def run_adjudicator_batch(
    events: list[dict[str, Any]],
    settings: dict,
    logger: logging.Logger,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, int],
]:
    adj_cfg = _resolve_adj_config(settings)
    if not adj_cfg or not adj_cfg.get("enabled", False):
        return [], [], [], {"adjudicator_enabled": 0}

    _, profile_cfg = _resolve_active_ai_profile(settings)
    prompts_cfg = _resolve_ai_prompts_cfg(settings)
    max_events = int(adj_cfg["events_max"])
    eligible_events = [
        event for event in events if _is_event_eligible_for_adjudicator(event)
    ]
    eligible_events = eligible_events[:max_events]

    requests: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    for event in eligible_events:
        adjudicator_result = run_adjudicator_for_event(
            event=event,
            adj_cfg=adj_cfg,
            profile_cfg=profile_cfg,
            prompts_cfg=prompts_cfg,
            logger=logger,
        )
        requests.append(adjudicator_result.get("request", {}))
        decisions.append(adjudicator_result.get("decision", {}))
        results.append(adjudicator_result.get("result", {}))

    used_count = sum(1 for result in results if result.get("ai_used", False))
    degraded_count = sum(
        1
        for result in results
        if result.get("ai_status")
        in ("degraded", "invalid", "low_confidence", "manual_review_degrade")
    )

    counters = {
        "adjudicator_enabled": 1,
        "adjudicator_eligible_count": len(eligible_events),
        "adjudicator_used_count": used_count,
        "adjudicator_degraded_count": degraded_count,
    }

    logger.info(
        "ai_adjudicator batch finished: eligible=%d used=%d degraded=%d",
        len(eligible_events),
        used_count,
        degraded_count,
    )

    return requests, decisions, results, counters


def write_adjudicator_artifacts(
    storage_dir: Path,
    run_id: str,
    requests: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    results: list[dict[str, Any]],
    counters: dict[str, int],
    logger: logging.Logger,
) -> list[str]:
    if not requests and not decisions and not results:
        return []

    run_dir = storage_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    refs: list[str] = []

    requests_path = run_dir / "rop_ai_adjudicator_requests.json"
    requests_path.write_text(
        json.dumps(
            {"run_id": run_id, "counters": counters, "requests": requests},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    refs.append(str(requests_path.relative_to(storage_dir)))

    decisions_path = run_dir / "rop_ai_adjudicator_decisions.json"
    decisions_path.write_text(
        json.dumps(
            {"run_id": run_id, "counters": counters, "decisions": decisions},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    refs.append(str(decisions_path.relative_to(storage_dir)))

    results_path = run_dir / "rop_ai_adjudicator_results.json"
    results_path.write_text(
        json.dumps(
            {"run_id": run_id, "counters": counters, "results": results},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    refs.append(str(results_path.relative_to(storage_dir)))

    logger.info(
        "rop_ai_adjudicator artifacts written: run_id=%s requests=%d decisions=%d results=%d",
        run_id,
        len(requests),
        len(decisions),
        len(results),
    )

    return refs
