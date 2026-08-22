from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib import request

import yaml

from beeagent_module.core.paths import get_project_root
from beeagent_module.core.rop_reason_contract import (
    AI_EVIDENCE_CODES,
    AI_EVIDENCE_CODES_MAX,
    AI_REASON_CODES,
    AI_REASON_CODES_BY_CASE_TYPE,
)
from beeagent_module.core.settings import (
    apply_runtime_settings_overrides,
    get_rop_ai_adjudicator_runtime_state,
)

_SUPPORTED_AI_PROVIDERS = frozenset({"openai_responses"})
_DATA_BASE64_RE = re.compile(
    r"data:[^;\s]+;base64,[A-Za-z0-9+/=\s]{20,}",
    re.IGNORECASE,
)
_LONG_BASE64_RE = re.compile(r"\b(?:[A-Za-z0-9+/]{80,}={0,2})\b")
_EMAIL_BRACKET_RE = re.compile(
    r"<([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})>",
    re.IGNORECASE,
)
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
_CUSTOMER_REQUEST_MARKERS = frozenset(
    {
        "rfq",
        "request for quotation",
        "request for quote",
        "need quote",
        "please quote",
        "please send quote",
        "pricing request",
        "quotation request",
        "quote request",
        "bid invitation",
        "price quote",
        "customer request",
        "purchase order",
        "po ",
        "тендер",
        "запрос котировок",
        "коммерческое предложение",
    }
)
_TENDER_MARKERS = frozenset(
    {
        "tender",
        "rfq",
        "request for quotation",
        "request for quote",
        "bid invitation",
        "invitation to bid",
        "тендер",
        "запрос котировок",
    }
)
_LOGISTICS_MARKERS = frozenset(
    {
        "shipment",
        "delivery",
        "customs",
        "transport",
        "warehouse",
        "container",
        "bill of lading",
        "packing list",
        "awb",
        "tracking",
        "eta",
        "etd",
        "отгруз",
        "доставк",
        "тамож",
        "перевоз",
        "склад",
    }
)
_FINANCE_MARKERS = frozenset(
    {
        "invoice",
        "reconciliation",
        "statement of account",
        "payment",
        "accounting",
        "act of",
        "tax invoice",
        "счет",
        "счёт",
        "сверк",
        "оплат",
        "акт",
        "бухгалтер",
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
_RISKY_DETERMINISTIC_QUEUES = frozenset(
    {
        "sales",
        "tender",
        "logistics",
        "finance",
        "procurement",
    }
)
_RISKY_REASON_CODE_PARTS = (
    "fallback",
    "ambiguous",
    "low_signal",
    "existing_deal_reference_signal",
)
_VALID_CASE_TYPES = frozenset({"new_lead", "existing_deal", "irrelevant"})
_DUPLICATE_DECISIONS = frozenset({"confirm_duplicate", "reject_duplicate"})
_DUPLICATE_REASON_CODES = frozenset(
    {"duplicate_hypothesis_confirmed", "duplicate_hypothesis_rejected"}
)
_VALID_QUEUES = frozenset(
    {
        "sales",
        "tender",
        "logistics",
        "finance",
        "procurement",
        "ignore",
    }
)
_VALID_ACTIONS = frozenset(
    {
        "review_new_lead",
        "review_tender",
        "attach_to_deal",
        "check_bitrix",
        "ignore",
    }
)
_VALID_RISK_FLAGS = frozenset(
    {
        "marketing_conflict",
        "spam_rfq_conflict",
        "supplier_outreach",
        "low_signal",
        "ambiguous_bitrix",
        "newsletter_bulk",
        "finance_sales_conflict",
        "business_ignore_conflict",
        "attachment_mismatch",
    }
)
_MAX_CASE_SUBTYPE_LENGTH = 80
_MAX_REASON_LENGTH = 600
_MAX_RISK_FLAGS = 8
_MAX_RISK_FLAG_LENGTH = 64
_MAX_CONFLICT_SIGNALS = 12
_MAX_AI_EVIDENCE_CODE_LENGTH = 80
_MAX_AI_REASON_CODE_LENGTH = 80
_ROP_AI_ADJUDICATOR_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "case_type",
        "case_subtype",
        "recommended_queue",
        "correct_action",
        "should_rop_see",
        "confidence",
        "reason",
        "risk_flags",
        "reason_code",
        "evidence_codes",
        "duplicate_decision",
    ],
    "properties": {
        "case_type": {
            "type": "string",
            "enum": sorted(_VALID_CASE_TYPES),
        },
        "case_subtype": {
            "type": "string",
            "maxLength": _MAX_CASE_SUBTYPE_LENGTH,
        },
        "recommended_queue": {
            "type": "string",
            "enum": sorted(_VALID_QUEUES),
        },
        "correct_action": {
            "type": "string",
            "enum": sorted(_VALID_ACTIONS),
        },
        "should_rop_see": {
            "type": "boolean",
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "reason": {
            "type": "string",
            "maxLength": _MAX_REASON_LENGTH,
            "description": "Concise canonical English audit reason. Must not copy full email or attachment content.",
        },
        "risk_flags": {
            "type": "array",
            "maxItems": _MAX_RISK_FLAGS,
            "items": {
                "type": "string",
                "maxLength": _MAX_RISK_FLAG_LENGTH,
            },
        },
        "reason_code": {
            "type": "string",
            "enum": sorted(AI_REASON_CODES),
            "description": "Structured reason code for the AI adjudicator decision.",
        },
        "evidence_codes": {
            "type": "array",
            "maxItems": AI_EVIDENCE_CODES_MAX,
            "items": {
                "type": "string",
                "enum": sorted(AI_EVIDENCE_CODES),
            },
            "description": (
                "Bounded allowlisted evidence codes supporting "
                "the AI adjudicator decision."
            ),
        },
        "duplicate_decision": {
            "anyOf": [
                {"type": "string", "enum": sorted(_DUPLICATE_DECISIONS)},
                {"type": "null"},
            ],
        },
    },
}


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _resolve_config_path(path: str) -> Path:
    path_value = Path(path)
    if path_value.is_absolute():
        return path_value
    return get_project_root() / path_value


def _get_nested_prompt_value(payload: dict[str, Any], key_path: tuple[str, ...]) -> Any:
    current: Any = payload
    for key in key_path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _load_prompts(path: str) -> dict[str, Any]:
    file_path = _resolve_config_path(path)
    if not file_path.exists():
        raise RuntimeError(f"Prompts file not found: {file_path}")

    with file_path.open("r", encoding="utf-8") as file:
        content = yaml.safe_load(file)

    if not isinstance(content, dict):
        raise RuntimeError("Prompts file must contain a top-level mapping")

    return content


def _build_prompt_messages_by_key(
    prompts_path: str,
    prompt_key: str,
    template_vars: dict[str, Any],
) -> tuple[str, str]:
    if not isinstance(prompts_path, str) or not prompts_path:
        raise RuntimeError("Invalid ai.prompts.path, expected non-empty string")

    prompts = _load_prompts(prompts_path)
    prompt_payload = _get_nested_prompt_value(prompts, tuple(prompt_key.split(".")))
    if not isinstance(prompt_payload, dict):
        raise RuntimeError(f"Prompt key not found in prompts file: {prompt_key}")

    system_template = prompt_payload.get("system")
    user_template = prompt_payload.get("user")
    if not isinstance(system_template, str) or not system_template:
        raise RuntimeError(f"Prompt '{prompt_key}.system' must be a non-empty string")
    if not isinstance(user_template, str) or not user_template:
        raise RuntimeError(f"Prompt '{prompt_key}.user' must be a non-empty string")

    template_vars_used = set(re.findall(r"{([a-zA-Z_][a-zA-Z0-9_]*)}", user_template))
    missing_vars = sorted(template_vars_used.difference(template_vars))
    if missing_vars:
        raise RuntimeError(
            f"Prompt '{prompt_key}.user' references unknown variables: "
            + ", ".join(missing_vars)
        )

    user_prompt = user_template.format_map(_SafeDict(**template_vars))

    return system_template, user_prompt


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
    text = _EMAIL_BRACKET_RE.sub(r" \1 ", text)
    text = _HTML_TAG_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text[:max_chars]


def _sanitize_prompt_list(
    values: Any,
    *,
    max_items: int,
    item_chars: int,
) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    for value in values:
        if len(cleaned) >= max_items:
            break
        if value is None:
            continue
        item = _sanitize_prompt_text(value, item_chars)
        if item:
            cleaned.append(item)
    return cleaned


def _sanitize_output_text(value: Any, max_chars: int) -> str:
    if not isinstance(value, str):
        return ""
    return _WHITESPACE_RE.sub(" ", value).strip()[:max_chars]


def _extract_attachment_metadata(event: dict[str, Any]) -> tuple[list[str], list[str]]:
    attachments = event.get("attachments")
    if not isinstance(attachments, list):
        attachments = []

    filenames = [
        _sanitize_prompt_text(attachment.get("filename", ""), 200)
        for attachment in attachments
        if isinstance(attachment, dict) and attachment.get("filename")
    ]
    mime_types = [
        _sanitize_prompt_text(attachment.get("content_type", ""), 200)
        for attachment in attachments
        if isinstance(attachment, dict) and attachment.get("content_type")
    ]

    if not filenames:
        filenames = _sanitize_prompt_list(
            event.get("attachment_filenames"),
            max_items=20,
            item_chars=200,
        )
    if not mime_types:
        mime_types = _sanitize_prompt_list(
            event.get("attachment_mime_types"),
            max_items=20,
            item_chars=200,
        )

    return filenames, mime_types


def _attachment_preview_evidence(event: dict[str, Any]) -> dict[str, Any] | None:
    result: dict[str, Any] = {}
    extraction_status = _sanitize_prompt_text(
        event.get("attachment_extraction_status"), 80
    )
    if extraction_status:
        result["extraction_status"] = extraction_status
    preview_available = event.get("attachment_preview_available")
    if isinstance(preview_available, bool):
        result["preview_available"] = preview_available
    refusal_reasons = _sanitize_prompt_list(
        event.get("attachment_refusal_reasons"),
        max_items=8,
        item_chars=160,
    )
    if refusal_reasons:
        result["refusal_reasons"] = refusal_reasons
    if preview_available is True:
        text_preview = _sanitize_prompt_text(event.get("attachment_text_preview"), 800)
        if text_preview:
            result["text_preview"] = text_preview

    attachments = event.get("attachments")
    if isinstance(attachments, list):
        bounded_attachments: list[dict[str, Any]] = []
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            entry: dict[str, Any] = {}
            filename = _sanitize_prompt_text(attachment.get("filename"), 200)
            if filename:
                entry["filename"] = filename
            content_type = _sanitize_prompt_text(attachment.get("content_type"), 120)
            if content_type:
                entry["content_type"] = content_type
            if entry:
                bounded_attachments.append(entry)
            if len(bounded_attachments) >= 8:
                break
        if bounded_attachments:
            result["attachments"] = bounded_attachments

    if not result:
        return None
    return result


def _bounded_thread_context_payload(
    event: dict[str, Any],
) -> dict[str, Any] | None:
    tc = event.get("thread_context")
    if not isinstance(tc, dict):
        return None
    result: dict[str, Any] = {}
    for key, limit in (
        ("thread_id", 120),
        ("previous_event_id", 120),
        ("previous_case_type", 60),
        ("previous_subject", 200),
        ("previous_summary", 400),
    ):
        value = _sanitize_prompt_text(tc.get(key), limit)
        if value:
            result[key] = value
    if isinstance(tc.get("reply_markers"), bool):
        result["reply_markers"] = tc["reply_markers"]
    if isinstance(tc.get("forward_markers"), bool):
        result["forward_markers"] = tc["forward_markers"]
    participant_hints = _sanitize_prompt_list(
        tc.get("participant_hints"), max_items=8, item_chars=120
    )
    if participant_hints:
        result["participant_hints"] = participant_hints
    thread_confidence = tc.get("thread_confidence")
    if isinstance(thread_confidence, (int, float)) and not isinstance(
        thread_confidence, bool
    ):
        result["thread_confidence"] = min(max(float(thread_confidence), 0.0), 1.0)
    reason_codes = _sanitize_prompt_list(
        tc.get("reason_codes"), max_items=8, item_chars=80
    )
    if reason_codes:
        result["reason_codes"] = reason_codes
    return result or None


def _bounded_conversation_context_payload(
    event: dict[str, Any],
) -> dict[str, Any] | None:
    cc = event.get("conversation_context")
    if not isinstance(cc, dict):
        return None
    result: dict[str, Any] = {}
    conversation_id = _sanitize_prompt_text(cc.get("conversation_id"), 120)
    if conversation_id:
        result["conversation_id"] = conversation_id
    message_count = cc.get("message_count")
    if isinstance(message_count, int) and not isinstance(message_count, bool):
        result["message_count"] = message_count
    other_events = cc.get("other_events")
    if isinstance(other_events, list):
        bounded_events: list[dict[str, Any]] = []
        for other in other_events:
            if not isinstance(other, dict):
                continue
            entry: dict[str, Any] = {}
            for key, limit in (
                ("event_id", 120),
                ("role", 40),
                ("case_type", 60),
            ):
                value = _sanitize_prompt_text(other.get(key), limit)
                if value:
                    entry[key] = value
            subject = _sanitize_prompt_text(other.get("subject"), 120)
            if subject:
                entry["subject"] = subject
            sender = _sanitize_prompt_text(other.get("sender"), 160)
            if sender:
                entry["sender"] = sender
            if entry:
                bounded_events.append(entry)
            if len(bounded_events) >= 8:
                break
        if bounded_events:
            result["other_events"] = bounded_events
    return result or None


def _event_signal_map(event: dict[str, Any]) -> dict[str, bool]:
    text = _event_text_for_marker_scan(event)
    return {
        "spam": bool(event.get("spam_label_present", False)),
        "reply": bool(event.get("reply_label_present", False)),
        "forwarded": bool(event.get("forwarded_wrapper", False)),
        "supplier_outreach": _contains_any_marker(text, _SUPPLIER_OR_PRODUCT_MARKERS),
        "newsletter_bulk": _contains_any_marker(
            text,
            _NEWSLETTER_HR_LEGAL_TRAINING_MARKERS,
        ),
        "customer_request": _contains_any_marker(text, _CUSTOMER_REQUEST_MARKERS),
        "tender": _contains_any_marker(text, _TENDER_MARKERS),
        "logistics": _contains_any_marker(text, _LOGISTICS_MARKERS),
        "finance": _contains_any_marker(text, _FINANCE_MARKERS),
    }


def _has_actionable_business_evidence(event: dict[str, Any]) -> bool:
    signal_map = _event_signal_map(event)
    return any(
        signal_map[key]
        for key in ("customer_request", "tender", "logistics", "finance")
    )


def _has_non_tender_actionable_signal(event: dict[str, Any]) -> bool:
    signal_map = _event_signal_map(event)
    return (
        (signal_map["customer_request"] and not signal_map["tender"])
        or signal_map["logistics"]
        or signal_map["finance"]
    )


def _has_false_positive_markers(event: dict[str, Any]) -> bool:
    signal_map = _event_signal_map(event)
    return (
        signal_map["supplier_outreach"]
        or signal_map["newsletter_bulk"]
        or signal_map["spam"]
    )


def _deterministic_is_safe_ignore(event: dict[str, Any]) -> bool:
    return (
        _deterministic_value(event, "case_type", "") == "irrelevant"
        and _deterministic_value(event, "recommended_queue", "") == "ignore"
        and _deterministic_value(event, "correct_action", "") == "ignore"
    )


def _is_deterministic_tender_candidate(event: dict[str, Any]) -> bool:
    return (
        _deterministic_value(event, "recommended_queue", "") == "tender"
        or _deterministic_value(event, "correct_action", "") == "review_tender"
    )


def _deterministic_final_routing(event: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (
        event.get("recommended_queue"),
        event.get("correct_action"),
        event.get("should_rop_see"),
    )


def _has_conflict_marker_combinations(event: dict[str, Any]) -> bool:
    signal_map = _event_signal_map(event)
    deterministic_case_type = _deterministic_value(event, "case_type", "unknown")
    deterministic_queue = _deterministic_value(event, "recommended_queue", "")

    if signal_map["spam"] and (signal_map["customer_request"] or signal_map["tender"]):
        return True

    if signal_map["newsletter_bulk"] and deterministic_case_type in {
        "existing_deal",
        "new_lead",
    }:
        return True

    if signal_map["supplier_outreach"] and (
        deterministic_case_type == "existing_deal"
        or deterministic_queue == "procurement"
    ):
        return True

    if signal_map["finance"] and (
        deterministic_case_type == "new_lead" or deterministic_queue == "sales"
    ):
        return True

    if _deterministic_is_safe_ignore(event) and _has_actionable_business_evidence(
        event
    ):
        return True

    return False


def _build_conflict_signals(event: dict[str, Any]) -> list[str]:
    signal_map = _event_signal_map(event)
    deterministic_confidence = _deterministic_value(event, "confidence", 0.0)
    if not isinstance(deterministic_confidence, (int, float)):
        deterministic_confidence = 0.0

    signals: list[str] = []
    if signal_map["spam"]:
        signals.append("spam_label_present")
    if signal_map["reply"]:
        signals.append("reply_label_present")
    if signal_map["forwarded"]:
        signals.append("forwarded_wrapper")
    if signal_map["supplier_outreach"]:
        signals.append("supplier_outreach")
    if signal_map["newsletter_bulk"]:
        signals.append("newsletter_bulk")
    if signal_map["customer_request"]:
        signals.append("customer_request")
    if signal_map["tender"]:
        signals.append("tender_marker")
    if signal_map["logistics"]:
        signals.append("logistics_marker")
    if signal_map["finance"]:
        signals.append("finance_marker")
    if event.get("is_fallback", False):
        signals.append("deterministic_fallback")
    if (
        _deterministic_value(event, "correct_action", "")
        in _DANGEROUS_DETERMINISTIC_ACTIONS
    ):
        signals.append("deterministic_risky_action")
    if (
        _deterministic_value(event, "recommended_queue", "")
        in _RISKY_DETERMINISTIC_QUEUES
    ):
        signals.append("deterministic_risky_queue")
    if float(deterministic_confidence) < 0.60:
        signals.append("deterministic_low_confidence")

    deduped: list[str] = []
    for signal in signals:
        if signal not in deduped:
            deduped.append(signal)
        if len(deduped) >= _MAX_CONFLICT_SIGNALS:
            break
    return deduped


def _build_bitrix_match_summary(event: dict[str, Any]) -> dict[str, Any] | None:
    summary: dict[str, Any] = {}
    for key in (
        "bitrix_match_summary",
        "bitrix_match_status",
        "bitrix_match_quality",
        "bitrix_confidence",
        "safe_to_use_as_target",
    ):
        value = event.get(key)
        if value in (None, "", []):
            continue
        if isinstance(value, str):
            summary[key] = _sanitize_prompt_text(value, 200)
        elif isinstance(value, (int, float, bool)):
            summary[key] = value

    return summary or None


def _bounded_classification(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        key: _sanitize_prompt_text(value.get(key), 200)
        for key in (
            "case_type",
            "case_subtype",
            "recommended_queue",
            "correct_action",
            "reason_code",
        )
        if value.get(key) is not None
    }


def _bounded_duplicate_candidate(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, Any] = {}
    for key in ("existing_lead_id", "event_id", "reason_code"):
        if isinstance(value.get(key), str):
            result[key] = _sanitize_prompt_text(value[key], 200)
    if isinstance(value.get("matched_fields"), list):
        result["matched_fields"] = _sanitize_prompt_list(
            value["matched_fields"], max_items=8, item_chars=80
        )
    return result


def _is_possible_duplicate(event: dict[str, Any]) -> bool:
    duplicate = event.get("duplicate")
    return (
        isinstance(duplicate, dict) and duplicate.get("resolution_status") == "possible"
    )


def _base_classification_fields(
    event: dict[str, Any],
) -> tuple[Any, Any, Any, Any, Any]:
    base = event.get("base_classification")
    if not isinstance(base, dict):
        return (
            event.get("case_type", "unknown"),
            event.get("case_subtype"),
            event.get("recommended_queue"),
            event.get("correct_action"),
            event.get("should_rop_see"),
        )
    return (
        base.get("case_type", event.get("case_type", "unknown")),
        base.get("case_subtype", event.get("case_subtype")),
        base.get("recommended_queue", event.get("recommended_queue")),
        base.get("correct_action", event.get("correct_action")),
        base.get("should_rop_see", event.get("should_rop_see")),
    )


def _build_prompt_event_payload(
    event: dict[str, Any],
    *,
    body_chars_max: int = 1200,
) -> dict[str, Any]:
    attachment_filenames, attachment_mime_types = _extract_attachment_metadata(event)

    payload = {
        "event_id": event.get("event_id", ""),
        "source_id": event.get("source_id", ""),
        "sender": _sanitize_prompt_text(event.get("sender") or "", 200),
        "original_sender": _sanitize_prompt_text(
            event.get("original_sender") or "",
            200,
        ),
        "original_sender_email": _sanitize_prompt_text(
            event.get("original_sender_email") or event.get("original_sender") or "",
            200,
        ),
        "subject": _sanitize_prompt_text(event.get("subject") or "", 200),
        "clean_subject": _sanitize_prompt_text(
            event.get("clean_subject") or "",
            200,
        ),
        "transport_labels": _sanitize_prompt_list(
            event.get("transport_labels", []),
            max_items=20,
            item_chars=80,
        ),
        "spam_label_present": event.get("spam_label_present", False),
        "reply_label_present": event.get("reply_label_present", False),
        "forwarded_wrapper": event.get("forwarded_wrapper", False),
        "body_preview": _sanitize_prompt_text(
            event.get("body_preview")
            or event.get("body_short")
            or event.get("text_preview")
            or event.get("body")
            or "",
            body_chars_max,
        ),
        "attachment_filenames": attachment_filenames,
        "attachment_mime_types": attachment_mime_types,
        "attachment_evidence": _attachment_preview_evidence(event),
        "thread_context": _bounded_thread_context_payload(event),
        "conversation_context": _bounded_conversation_context_payload(event),
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
        "deterministic_risk_flags": _sanitize_prompt_list(
            event.get("risk_flags") or event.get("warnings") or [],
            max_items=_MAX_RISK_FLAGS,
            item_chars=_MAX_RISK_FLAG_LENGTH,
        ),
        "conflict_signals": _build_conflict_signals(event),
        "bitrix_match_summary": _build_bitrix_match_summary(event),
    }
    duplicate = event.get("duplicate")
    if isinstance(duplicate, dict) and duplicate.get("resolution_status") == "possible":
        candidate = duplicate.get("candidate")
        payload["adjudication_kind"] = "possible_duplicate"
        payload["base_classification"] = _bounded_classification(
            event.get("base_classification")
        )
        payload["duplicate_hypothesis"] = {
            "resolution_status": "possible",
            "reason_code": _sanitize_prompt_text(duplicate.get("reason_code"), 80),
            "reasoning": _sanitize_prompt_text(duplicate.get("reasoning"), 300),
            "candidate": _bounded_duplicate_candidate(candidate),
        }
    return payload


def _event_text_for_marker_scan(event: dict[str, Any]) -> str:
    attachment_filenames, attachment_mime_types = _extract_attachment_metadata(event)
    parts: list[str] = [
        _sanitize_prompt_text(event.get("sender") or "", 200),
        _sanitize_prompt_text(
            event.get("original_sender_email") or event.get("original_sender") or "",
            200,
        ),
        _sanitize_prompt_text(event.get("subject") or "", 200),
        _sanitize_prompt_text(event.get("clean_subject") or "", 200),
        _sanitize_prompt_text(
            event.get("body_preview")
            or event.get("body_short")
            or event.get("text_preview")
            or event.get("body")
            or "",
            500,
        ),
    ]
    parts.extend(attachment_filenames)
    parts.extend(attachment_mime_types)
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

    deterministic_action = _deterministic_value(event, "correct_action", "")
    if deterministic_action in _DANGEROUS_DETERMINISTIC_ACTIONS:
        return True

    deterministic_queue = _deterministic_value(event, "recommended_queue", "")
    if deterministic_queue in _RISKY_DETERMINISTIC_QUEUES:
        return True

    if _has_false_positive_markers(event):
        return True

    if _has_conflict_marker_combinations(event):
        return True

    return False


def _ai_output_conflicts_with_marker_signals(
    event: dict[str, Any],
    validated: dict[str, Any],
) -> bool:
    ai_case_type = validated.get("case_type")
    ai_queue = validated.get("recommended_queue")
    ai_correct_action = validated.get("correct_action")
    if ai_case_type == "irrelevant":
        return not (ai_queue == "ignore" and ai_correct_action == "ignore")
    if ai_queue == "ignore" or ai_correct_action == "ignore":
        return True
    return False


_NON_ACTIONABLE_DOWNGRADE_RULES = (
    ("non_actionable_supplier_outreach", "supplier_outreach"),
    ("non_actionable_bulk_or_newsletter", "newsletter_bulk"),
)
_NEW_LEAD_TRANSITION_REASON_CODES = frozenset(
    {"customer_request_detected", "tender_or_rfq_detected"}
)
_EXISTING_DEAL_TRANSITION_REASON_CODES = frozenset(
    {"existing_deal_continuation", "logistics_or_finance_continuation"}
)


def _ai_transition_is_authorized(
    event: dict[str, Any],
    validated: dict[str, Any],
) -> bool:
    deterministic_case_type = _deterministic_value(event, "case_type", "unknown")
    ai_case_type = validated.get("case_type")
    if ai_case_type == deterministic_case_type:
        return True
    ai_reason_code = str(validated.get("reason_code", "") or "")
    ai_evidence_codes = set(validated.get("evidence_codes", []) or [])
    if ai_case_type == "irrelevant":
        return any(
            ai_reason_code == reason_code and evidence_code in ai_evidence_codes
            for reason_code, evidence_code in _NON_ACTIONABLE_DOWNGRADE_RULES
        )
    if ai_case_type == "new_lead":
        return ai_reason_code in _NEW_LEAD_TRANSITION_REASON_CODES
    if ai_case_type == "existing_deal":
        return ai_reason_code in _EXISTING_DEAL_TRANSITION_REASON_CODES
    return False


def _is_low_confidence_safe_ignore_preservation(
    event: dict[str, Any],
    validated: dict[str, Any],
) -> bool:
    return (
        _deterministic_is_safe_ignore(event)
        and validated.get("case_type") == "irrelevant"
        and validated.get("recommended_queue") == "ignore"
        and validated.get("correct_action") == "ignore"
        and not _has_actionable_business_evidence(event)
    )


def _is_high_confidence_false_positive_resolution(
    event: dict[str, Any],
    validated: dict[str, Any],
    min_confidence: float,
) -> bool:
    if validated.get("confidence", 0.0) < min_confidence:
        return False
    if validated.get("case_type") != "irrelevant":
        return False
    if validated.get("recommended_queue") != "ignore":
        return False
    if validated.get("correct_action") != "ignore":
        return False
    if not _has_false_positive_markers(event):
        return False
    if _has_actionable_business_evidence(event):
        return False
    return _has_conflict_or_risky_deterministic_signal(event, min_confidence)


def _minimal_event_json(event: dict[str, Any]) -> str:
    minimal = {
        "event_id": _sanitize_prompt_text(event.get("event_id"), 120),
        "sender": _sanitize_prompt_text(event.get("sender") or "", 200),
        "subject": _sanitize_prompt_text(event.get("subject") or "", 200),
        "body_preview": _sanitize_prompt_text(
            event.get("body_preview")
            or event.get("body_short")
            or event.get("text_preview")
            or event.get("body")
            or "",
            160,
        ),
        "deterministic_case_type": _deterministic_value(event, "case_type", "unknown"),
        "deterministic_confidence": _deterministic_value(event, "confidence", 0.0),
    }
    return json.dumps(minimal, ensure_ascii=False)


def _build_event_json_within_budget(
    event: dict[str, Any],
    budget_chars: int,
    body_chars_max: int = 1600,
) -> str:
    body_chars_max = min(body_chars_max, max(160, budget_chars // 3))
    while body_chars_max >= 160:
        payload = _build_prompt_event_payload(event, body_chars_max=body_chars_max)
        event_json = json.dumps(payload, ensure_ascii=False)
        if len(event_json) <= budget_chars:
            return event_json
        body_chars_max = int(body_chars_max * 0.7)
    return _minimal_event_json(event)


def _build_adjudicator_prompt(
    prompts_cfg: dict[str, Any],
    event: dict[str, Any],
    prompt_key: str,
    max_chars: int,
    body_chars_max: int = 1600,
) -> str:
    system_prompt, user_template = _build_prompt_messages_by_key(
        prompts_path=prompts_cfg["path"],
        prompt_key=prompt_key,
        template_vars={"event_json": ""},
    )
    base_len = len(f"System:\n{system_prompt}\n\nUser:\n{user_template}")
    event_budget = max(400, max_chars - base_len - 200)
    event_json = _build_event_json_within_budget(
        event, event_budget, body_chars_max=body_chars_max
    )

    system_prompt, user_prompt = _build_prompt_messages_by_key(
        prompts_path=prompts_cfg["path"],
        prompt_key=prompt_key,
        template_vars={"event_json": event_json},
    )
    prompt = f"System:\n{system_prompt}\n\nUser:\n{user_prompt}"
    if len(prompt) > max_chars:
        minimal_json = _minimal_event_json(event)
        system_prompt, user_prompt = _build_prompt_messages_by_key(
            prompts_path=prompts_cfg["path"],
            prompt_key=prompt_key,
            template_vars={"event_json": minimal_json},
        )
        prompt = f"System:\n{system_prompt}\n\nUser:\n{user_prompt}"
    if len(prompt) > max_chars:
        raise ValueError("AI adjudicator prompt exceeds input_chars_max")
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


def _validate_ai_output(
    data: dict[str, Any],
    *,
    possible_duplicate: bool = False,
) -> dict[str, Any]:
    validated: dict[str, Any] = {}
    errors: list[str] = []
    warnings: list[str] = []
    dropped_risk_flags: list[str] = []

    case_type = data.get("case_type", "")
    if isinstance(case_type, str) and case_type in _VALID_CASE_TYPES:
        validated["case_type"] = case_type
    else:
        errors.append(f"invalid case_type: {case_type}")
        validated["case_type"] = "irrelevant"

    subtype = data.get("case_subtype")
    if isinstance(subtype, str):
        cleaned_subtype = _sanitize_output_text(subtype, _MAX_CASE_SUBTYPE_LENGTH)
        validated["case_subtype"] = cleaned_subtype or None
    else:
        validated["case_subtype"] = None

    queue = data.get("recommended_queue", "")
    if isinstance(queue, str) and queue in _VALID_QUEUES:
        validated["recommended_queue"] = queue
    else:
        errors.append(f"invalid recommended_queue: {queue}")
        validated["recommended_queue"] = ""

    should_see = data.get("should_rop_see")
    if isinstance(should_see, bool):
        validated["should_rop_see"] = should_see
    else:
        errors.append(f"invalid should_rop_see: {should_see}")
        validated["should_rop_see"] = True

    action = data.get("correct_action", "")
    if isinstance(action, str) and action in _VALID_ACTIONS:
        validated["correct_action"] = action
    else:
        errors.append(f"invalid correct_action: {action}")
        validated["correct_action"] = ""

    confidence = data.get("confidence", 0.0)
    if isinstance(confidence, (int, float)) and 0.0 <= confidence <= 1.0:
        validated["confidence"] = float(confidence)
    else:
        errors.append(f"invalid confidence: {confidence}")
        validated["confidence"] = 0.0

    reason = data.get("reason")
    validated["reason"] = _sanitize_output_text(reason, _MAX_REASON_LENGTH)

    risk_flags = data.get("risk_flags", [])
    cleaned_flags: list[str] = []
    if isinstance(risk_flags, list):
        for flag in risk_flags:
            if len(cleaned_flags) >= _MAX_RISK_FLAGS:
                break
            if isinstance(flag, str) and flag in _VALID_RISK_FLAGS:
                cleaned_flags.append(flag)
            elif isinstance(flag, str):
                cleaned_flag = _sanitize_output_text(flag, _MAX_RISK_FLAG_LENGTH)
                if cleaned_flag:
                    dropped_risk_flags.append(cleaned_flag)
                    warnings.append(f"dropped unknown risk_flag: {cleaned_flag}")
        validated["risk_flags"] = cleaned_flags[:_MAX_RISK_FLAGS]
    else:
        warnings.append("risk_flags was not a list; replaced with []")
        validated["risk_flags"] = []

    reason_code = _sanitize_output_text(
        data.get("reason_code"), _MAX_AI_REASON_CODE_LENGTH
    )
    reason_code_diagnostic = reason_code or "<invalid>"
    if possible_duplicate:
        duplicate_decision = data.get("duplicate_decision", "")
        if duplicate_decision in _DUPLICATE_DECISIONS:
            validated["duplicate_decision"] = duplicate_decision
        else:
            errors.append(f"invalid duplicate_decision: {duplicate_decision}")
            validated["duplicate_decision"] = ""
        if reason_code in _DUPLICATE_REASON_CODES:
            expected_reason = (
                "duplicate_hypothesis_confirmed"
                if validated["duplicate_decision"] == "confirm_duplicate"
                else "duplicate_hypothesis_rejected"
            )
            if reason_code == expected_reason:
                validated["reason_code"] = reason_code
            else:
                errors.append("reason_code incompatible with duplicate_decision")
                validated["reason_code"] = ""
        else:
            errors.append(f"invalid duplicate reason_code: {reason_code_diagnostic}")
            validated["reason_code"] = ""
    elif reason_code in AI_REASON_CODES:
        allowed_reason_codes = AI_REASON_CODES_BY_CASE_TYPE[validated["case_type"]]
        if reason_code in allowed_reason_codes:
            validated["reason_code"] = reason_code
        else:
            errors.append(
                "reason_code incompatible with case_type: "
                f"{reason_code}/{validated['case_type']}"
            )
            validated["reason_code"] = ""
    else:
        errors.append(f"invalid reason_code: {reason_code_diagnostic}")
        validated["reason_code"] = ""

    evidence_codes = data.get("evidence_codes", [])
    cleaned_evidence: list[str] = []
    dropped_evidence: list[str] = []
    if isinstance(evidence_codes, list):
        for code in evidence_codes:
            if len(cleaned_evidence) >= AI_EVIDENCE_CODES_MAX:
                break
            cleaned_code = _sanitize_output_text(code, _MAX_AI_EVIDENCE_CODE_LENGTH)
            if cleaned_code in AI_EVIDENCE_CODES:
                cleaned_evidence.append(cleaned_code)
            elif isinstance(code, str):
                if cleaned_code:
                    dropped_evidence.append(cleaned_code)
                    warnings.append(f"dropped unknown evidence_code: {cleaned_code}")
        validated["evidence_codes"] = cleaned_evidence[:AI_EVIDENCE_CODES_MAX]
    else:
        warnings.append("evidence_codes was not a list; replaced with []")
        validated["evidence_codes"] = []

    validated["errors"] = errors
    validated["warnings"] = warnings
    validated["dropped_risk_flags"] = dropped_risk_flags[:_MAX_RISK_FLAGS]
    validated["dropped_evidence_codes"] = dropped_evidence[:AI_EVIDENCE_CODES_MAX]
    return validated


def _is_business_impacting_deterministic(event: dict[str, Any]) -> bool:
    action = _deterministic_value(event, "correct_action", "")
    queue = _deterministic_value(event, "recommended_queue", "")
    return (
        action in _DANGEROUS_DETERMINISTIC_ACTIONS
        or queue in _RISKY_DETERMINISTIC_QUEUES
    )


def _ai_output_is_semantic_unresolved(validated: dict[str, Any]) -> bool:
    return not validated.get("recommended_queue") or not validated.get("correct_action")


def _is_event_eligible_for_adjudicator(event: dict[str, Any]) -> bool:
    if _is_possible_duplicate(event):
        return True
    return event.get("case_type", "") != "duplicate"


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

    payload = _build_openai_responses_payload(prompt=prompt, model=model)

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


def _build_openai_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "rop_ai_adjudicator_decision",
        "strict": True,
        "schema": _ROP_AI_ADJUDICATOR_RESPONSE_SCHEMA,
    }


def _build_openai_responses_payload(*, prompt: str, model: str) -> dict[str, Any]:
    return {
        "model": model,
        "input": prompt,
        "temperature": 0.1,
        "max_output_tokens": 500,
        "text": {"format": _build_openai_response_format()},
    }


def _build_result(
    event: dict[str, Any],
    *,
    ai_used: bool,
    ai_provider: str,
    ai_model: str,
    ai_status: str,
    ai_confidence: float | None,
    ai_reason: str,
    ai_reason_code: str,
    ai_evidence_codes: list[str],
    ai_risk_flags: list[str],
    ai_error: str,
    final_case_type: Any,
    final_case_subtype: Any,
    final_recommended_queue: Any,
    final_correct_action: Any,
    final_should_rop_see: Any,
    merge_reason: str,
    errors: list[str],
    warnings: list[str],
    dropped_risk_flags: list[str],
) -> dict[str, Any]:
    return {
        "event_id": event.get("event_id", ""),
        "event_instance_id": event.get("event_instance_id", ""),
        "ai_used": ai_used,
        "ai_provider": ai_provider,
        "ai_model": ai_model,
        "ai_status": ai_status,
        "ai_confidence": ai_confidence,
        "ai_reason": ai_reason,
        "ai_reason_code": ai_reason_code,
        "ai_evidence_codes": ai_evidence_codes,
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
        "warnings": warnings,
        "dropped_risk_flags": dropped_risk_flags,
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
            **safe_payload,
            "body_preview_chars": len(safe_payload.get("body_preview", "")),
        },
    }
    artifact["response_format"] = _build_openai_response_format()

    if prompts_cfg.get("store") and prompt:
        artifact["prompt_chars"] = len(prompt)

    return artifact


def run_adjudicator_for_event(
    event: dict[str, Any],
    adj_cfg: dict[str, Any],
    profile_cfg: dict[str, Any],
    prompts_cfg: dict[str, Any],
    logger: logging.Logger,
    body_chars_max: int = 1600,
) -> dict[str, Any]:
    eligible = _is_event_eligible_for_adjudicator(event)
    provider = profile_cfg["provider"]
    model = profile_cfg["model"]
    possible_duplicate = _is_possible_duplicate(event)
    final_case_type = event.get("case_type", "unknown")
    final_case_subtype = event.get("case_subtype")
    final_recommended_queue = event.get("recommended_queue")
    final_correct_action = event.get("correct_action")
    final_should_rop_see = event.get("should_rop_see")

    prompt: str | None = None
    prompt_budget_error: str | None = None
    if eligible:
        try:
            prompt = _build_adjudicator_prompt(
                prompts_cfg=prompts_cfg,
                event=event,
                prompt_key=adj_cfg["prompt_key"],
                max_chars=int(adj_cfg["input_chars_max"]),
                body_chars_max=body_chars_max,
            )
        except ValueError as exc:
            prompt_budget_error = str(exc)
            prompt = None

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
                ai_reason_code="",
                ai_evidence_codes=[],
                ai_risk_flags=[],
                ai_error="",
                final_case_type=final_case_type,
                final_case_subtype=final_case_subtype,
                final_recommended_queue=final_recommended_queue,
                final_correct_action=final_correct_action,
                final_should_rop_see=final_should_rop_see,
                merge_reason="deterministic_result_preserved",
                errors=[],
                warnings=[],
                dropped_risk_flags=[],
            ),
        }

    if prompt_budget_error:
        final_recommended_queue, final_correct_action, final_should_rop_see = (
            _deterministic_final_routing(event)
        )
        return {
            "request": request_artifact,
            "decision": {
                "event_id": event.get("event_id", ""),
                "provider": provider,
                "model": model,
                "status": "degraded",
                "reason_code": "prompt_budget_exceeded",
                "error": prompt_budget_error,
            },
            "result": _build_result(
                event,
                ai_used=False,
                ai_provider=provider,
                ai_model=model,
                ai_status="degraded",
                ai_confidence=None,
                ai_reason="",
                ai_reason_code="",
                ai_evidence_codes=[],
                ai_risk_flags=[],
                ai_error=prompt_budget_error,
                final_case_type=final_case_type,
                final_case_subtype=final_case_subtype,
                final_recommended_queue=final_recommended_queue,
                final_correct_action=final_correct_action,
                final_should_rop_see=final_should_rop_see,
                merge_reason="prompt_budget_exceeded_deterministic_result_preserved",
                errors=[prompt_budget_error],
                warnings=[],
                dropped_risk_flags=[],
            ),
        }

    api_key_env = profile_cfg["api_key_env"]
    api_key = os.getenv(api_key_env, "").strip()
    if not api_key:
        error = "AI adjudicator API key not found; deterministic result preserved"
        final_recommended_queue, final_correct_action, final_should_rop_see = (
            _deterministic_final_routing(event)
        )
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
                ai_reason_code="",
                ai_evidence_codes=[],
                ai_risk_flags=[],
                ai_error=error,
                final_case_type=final_case_type,
                final_case_subtype=final_case_subtype,
                final_recommended_queue=final_recommended_queue,
                final_correct_action=final_correct_action,
                final_should_rop_see=final_should_rop_see,
                merge_reason="missing_api_key_deterministic_result_preserved",
                errors=[error],
                warnings=[],
                dropped_risk_flags=[],
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
        final_recommended_queue, final_correct_action, final_should_rop_see = (
            _deterministic_final_routing(event)
        )
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
                ai_reason_code="",
                ai_evidence_codes=[],
                ai_risk_flags=[],
                ai_error=error,
                final_case_type=final_case_type,
                final_case_subtype=final_case_subtype,
                final_recommended_queue=final_recommended_queue,
                final_correct_action=final_correct_action,
                final_should_rop_see=final_should_rop_see,
                merge_reason="provider_call_failed_deterministic_result_preserved",
                errors=[error],
                warnings=[],
                dropped_risk_flags=[],
            ),
        }

    parsed = _parse_ai_response(raw_response)
    if parsed is None:
        error = "AI output was unparseable; deterministic result preserved"
        final_recommended_queue, final_correct_action, final_should_rop_see = (
            _deterministic_final_routing(event)
        )
        return {
            "request": request_artifact,
            "decision": {
                "event_id": event.get("event_id", ""),
                "provider": provider,
                "model": model,
                "status": "invalid",
                "reason_code": "unparseable_response",
                "error": error,
            },
            "result": _build_result(
                event,
                ai_used=True,
                ai_provider=provider,
                ai_model=model,
                ai_status="invalid",
                ai_confidence=None,
                ai_reason="",
                ai_reason_code="",
                ai_evidence_codes=[],
                ai_risk_flags=[],
                ai_error=error,
                final_case_type=final_case_type,
                final_case_subtype=final_case_subtype,
                final_recommended_queue=final_recommended_queue,
                final_correct_action=final_correct_action,
                final_should_rop_see=final_should_rop_see,
                merge_reason="ai_output_invalid_deterministic_result_preserved",
                errors=[error],
                warnings=[],
                dropped_risk_flags=[],
            ),
        }

    validated = _validate_ai_output(parsed, possible_duplicate=possible_duplicate)
    ai_confidence = float(validated.get("confidence", 0.0))
    ai_reason = str(validated.get("reason", ""))
    ai_risk_flags = list(validated.get("risk_flags", []))
    validation_errors = list(validated.get("errors", []))
    validation_warnings = list(validated.get("warnings", []))
    dropped_risk_flags = list(validated.get("dropped_risk_flags", []))
    min_confidence = float(adj_cfg["confidence_accept_min"])

    if possible_duplicate:
        if ai_confidence >= min_confidence and not validation_errors:
            if validated.get("duplicate_decision") == "confirm_duplicate":
                final_case_type = "duplicate"
                final_case_subtype = None
                final_recommended_queue = event.get("recommended_queue")
                final_correct_action = event.get("correct_action")
                final_should_rop_see = event.get("should_rop_see", True)
                merge_reason = "possible_duplicate_confirmed"
            else:
                (
                    final_case_type,
                    final_case_subtype,
                    final_recommended_queue,
                    final_correct_action,
                    final_should_rop_see,
                ) = _base_classification_fields(event)
                merge_reason = "possible_duplicate_rejected_base_preserved"
            status = "ok"
            ai_error = ""
        else:
            status = "duplicate_unresolved"
            (
                final_case_type,
                final_case_subtype,
                final_recommended_queue,
                final_correct_action,
                final_should_rop_see,
            ) = _base_classification_fields(event)
            ai_error = (
                "Possible duplicate AI result was not accepted; "
                "base classification preserved and deferred."
            )
            merge_reason = "possible_duplicate_unresolved_base_preserved"

        decision = {
            "event_id": event.get("event_id", ""),
            "provider": provider,
            "model": model,
            "status": status,
            "reason_code": merge_reason,
            "duplicate_decision": validated.get("duplicate_decision", ""),
            "ai_confidence": ai_confidence,
            "ai_reason": ai_reason,
            "ai_risk_flags": ai_risk_flags,
            "ai_reason_code": str(validated.get("reason_code", "")),
            "ai_evidence_codes": list(validated.get("evidence_codes", [])),
            "validation_errors": validation_errors,
            "validation_warnings": validation_warnings,
            "dropped_risk_flags": dropped_risk_flags,
            "dropped_evidence_codes": list(validated.get("dropped_evidence_codes", [])),
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
                ai_reason_code=str(validated.get("reason_code", "")),
                ai_evidence_codes=list(validated.get("evidence_codes", [])),
                ai_risk_flags=ai_risk_flags,
                ai_error=ai_error,
                final_case_type=final_case_type,
                final_case_subtype=final_case_subtype,
                final_recommended_queue=final_recommended_queue,
                final_correct_action=final_correct_action,
                final_should_rop_see=final_should_rop_see,
                merge_reason=merge_reason,
                errors=validation_errors,
                warnings=validation_warnings,
                dropped_risk_flags=dropped_risk_flags,
            ),
        }

    status = "ok"
    ai_error = ""
    errors = validation_errors
    warnings = validation_warnings
    merge_reason = "validated_ai_adjudicator_output"
    ai_decision_valid = not validation_errors and bool(validated.get("reason_code", ""))
    if ai_decision_valid and ai_confidence >= min_confidence:
        if _ai_output_is_semantic_unresolved(validated):
            status = "deterministic_preserved"
            final_case_type = _deterministic_value(event, "case_type", "unknown")
            final_case_subtype = _deterministic_value(event, "case_subtype", None)
            final_recommended_queue, final_correct_action, final_should_rop_see = (
                _deterministic_final_routing(event)
            )
            ai_error = (
                "AI output did not resolve a semantic decision; "
                "deterministic result preserved."
            )
            merge_reason = "ai_output_unresolved_deterministic_result_preserved"
        elif _ai_output_conflicts_with_marker_signals(event, validated):
            status = "deterministic_preserved"
            final_case_type = _deterministic_value(event, "case_type", "unknown")
            final_case_subtype = _deterministic_value(event, "case_subtype", None)
            final_recommended_queue, final_correct_action, final_should_rop_see = (
                _deterministic_final_routing(event)
            )
            ai_error = (
                "AI output conflicts with supplier/newsletter conflict signals; "
                "deterministic result preserved."
            )
            merge_reason = "ai_output_conflict_deterministic_result_preserved"
        elif not _ai_transition_is_authorized(event, validated):
            status = "deterministic_preserved"
            final_case_type = _deterministic_value(event, "case_type", "unknown")
            final_case_subtype = _deterministic_value(event, "case_subtype", None)
            final_recommended_queue, final_correct_action, final_should_rop_see = (
                _deterministic_final_routing(event)
            )
            ai_error = (
                "AI semantic transition is not authorized by an explicit "
                "evidence rule; deterministic result preserved."
            )
            merge_reason = (
                "ai_transition_rule_not_satisfied_deterministic_result_preserved"
            )
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
            if _is_high_confidence_false_positive_resolution(
                event,
                validated,
                min_confidence,
            ):
                merge_reason = "ai_resolved_risky_false_positive"
    elif ai_decision_valid:
        errors = [*validation_errors, "ai_confidence_below_acceptance_threshold"]
        if _is_low_confidence_safe_ignore_preservation(event, validated):
            status = "low_confidence_preserve"
            ai_error = (
                "AI confidence below acceptance threshold; safe deterministic ignore "
                "preserved."
            )
            merge_reason = "ai_low_confidence_safe_ignore_preserved"
        else:
            status = "low_confidence_preserve"
            final_case_type = _deterministic_value(event, "case_type", "unknown")
            final_case_subtype = _deterministic_value(event, "case_subtype", None)
            final_recommended_queue, final_correct_action, final_should_rop_see = (
                _deterministic_final_routing(event)
            )
            ai_error = (
                "AI confidence below acceptance threshold; "
                "deterministic result preserved."
            )
            merge_reason = (
                "ai_confidence_below_threshold_deterministic_result_preserved"
            )
    else:
        status = "deterministic_preserved"
        errors = validation_errors
        final_case_type = _deterministic_value(event, "case_type", "unknown")
        final_case_subtype = _deterministic_value(event, "case_subtype", None)
        final_recommended_queue, final_correct_action, final_should_rop_see = (
            _deterministic_final_routing(event)
        )
        ai_error = (
            "; ".join(validation_errors)
            if validation_errors
            else "AI output failed validation; deterministic result preserved."
        )
        merge_reason = "ai_output_invalid_deterministic_result_preserved"

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
        "ai_reason_code": str(validated.get("reason_code", "")),
        "ai_evidence_codes": list(validated.get("evidence_codes", [])),
        "validation_errors": validation_errors,
        "validation_warnings": validation_warnings,
        "dropped_risk_flags": dropped_risk_flags,
        "dropped_evidence_codes": list(validated.get("dropped_evidence_codes", [])),
        "error": ai_error,
    }

    ai_reason_code = str(validated.get("reason_code", ""))
    ai_evidence_codes = list(validated.get("evidence_codes", []))

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
            ai_reason_code=ai_reason_code,
            ai_evidence_codes=ai_evidence_codes,
            ai_risk_flags=ai_risk_flags,
            ai_error=ai_error,
            final_case_type=final_case_type,
            final_case_subtype=final_case_subtype,
            final_recommended_queue=final_recommended_queue,
            final_correct_action=final_correct_action,
            final_should_rop_see=final_should_rop_see,
            merge_reason=merge_reason,
            errors=errors,
            warnings=warnings,
            dropped_risk_flags=dropped_risk_flags,
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
    apply_runtime_settings_overrides(settings)
    adjudicator_state = get_rop_ai_adjudicator_runtime_state(settings)
    adj_cfg = _resolve_adj_config(settings)
    if not adj_cfg or not adjudicator_state["enabled"]:
        logger.info("adjudicator disabled")
        return [], [], [], {"adjudicator_enabled": 0}

    _, profile_cfg = _resolve_active_ai_profile(settings)
    prompts_cfg = _resolve_ai_prompts_cfg(settings)
    email_preview = settings.get("rop", {}).get("email_preview", {})
    body_chars_max = int(email_preview.get("body_chars_max", 1600))
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
            body_chars_max=body_chars_max,
        )
        requests.append(adjudicator_result.get("request", {}))
        decisions.append(adjudicator_result.get("decision", {}))
        results.append(adjudicator_result.get("result", {}))

    used_count = sum(1 for result in results if result.get("ai_used", False))
    degraded_count = sum(
        1
        for result in results
        if result.get("ai_status")
        in (
            "degraded",
            "invalid",
            "low_confidence",
            "low_confidence_preserve",
            "deterministic_preserved",
            "duplicate_unresolved",
            "manual_review_degrade",
        )
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
