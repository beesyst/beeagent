from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from beeagent_module.core.rop_conversation import build_conversation_timeline
from beeagent_module.core.rop_final_decision import (
    find_final_decision,
    load_or_build_final_decisions,
)
from beeagent_module.core.rop_reason_contract import (
    AI_EVIDENCE_CODES,
    AI_EVIDENCE_CODES_MAX,
)
from beeagent_module.interfaces.ui.artifacts import resolve_artifact_path
from beeagent_module.interfaces.ui.locale import (
    case_subtype_label,
    case_type_label,
    t,
    writeback_outcome_label,
)
from beeagent_module.interfaces.ui.reason_catalog import (
    get_ai_evidence_display,
    get_ai_reason_display,
    get_attention_reason_display,
    get_classification_reason_display,
)
from beeagent_module.interfaces.ui.url_builder import (
    build_rop_event_url,
    build_rop_url,
)

_PRIORITY_TONE = {
    "low": "muted",
    "medium": "warning",
    "high": "danger",
    "critical": "danger",
}

_ADJUDICATOR_STATUS_TONE = {
    "ok": "success",
    "not_eligible": "muted",
    "low_confidence_preserve": "warning",
    "manual_review_degrade": "warning",
    "deterministic_preserved": "warning",
    "duplicate_unresolved": "warning",
    "degraded": "danger",
    "invalid": "danger",
    "invalid_output": "danger",
    "provider_unavailable": "danger",
    "module_contract_unavailable": "danger",
}

_MAX_REASON_TEXT_LENGTH = 600
_MAX_REASON_CODE_LENGTH = 80
_TRUSTED_ATTACH_PROVENANCES = frozenset({"thread_resolved", "bitrix_outbound_exact"})
_BITRIX_LINKABLE_ENTITY_TYPES = frozenset({"lead", "deal"})
_EXPECTED_REASONLESS_AI_STATUSES = frozenset(
    {
        "degraded",
        "deterministic_preserved",
        "duplicate_unresolved",
        "low_confidence_preserve",
        "manual_review_degrade",
    }
)

_ATTACHMENT_CONTENT_TYPE_LABELS = {
    "application/msword": "Word document",
    "application/octet-stream": "Binary file",
    "application/pdf": "PDF document",
    "application/vnd.ms-excel.12": "Excel spreadsheet",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": (
        "Excel spreadsheet"
    ),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
        "Word document"
    ),
    "image/bmp": "Image",
    "image/gif": "Image",
    "image/jpeg": "Image",
    "image/png": "Image",
    "message/delivery-status": "Delivery status message",
    "message/disposition-notification": "Read receipt",
    "text/calendar": "Calendar event",
    "text/plain": "Text file",
    "text/rfc822-headers": "Email headers",
}

_ATTACHMENT_STORAGE_STATUS_LABELS = {
    "stored": "Saved",
    "malformed": "Damaged",
}

_ATTACHMENT_REASON_LABELS = {
    "ai_analysis_preview": "AI text extraction",
    "attachment_oversized": "File is too large",
    "docling_extraction_failed": "Text extraction failed",
    "local_extraction_preview": "Text extracted locally",
    "metadata_only_no_safe_text": "No safe text available",
    "unsupported_content_type": "Unsupported file type",
}

_ATTACHMENT_ANALYSIS_STATUS_LABELS = {
    "failed": "Processing failed",
    "ok": "Processed",
    "unsupported": "Not supported",
}


def _bool_display(value: Any, lang: str) -> str:
    if value is True:
        return t("Yes", lang)
    if value is False:
        return t("No", lang)
    return t("n/a", lang)


def _nullable_bool(*values: Any) -> bool | None:
    for v in values:
        if isinstance(v, bool):
            return v
    return None


def _priority_tone(value: str) -> str:
    return _PRIORITY_TONE.get(value, "muted")


def _adjudicator_status_tone(value: str) -> str:
    return _ADJUDICATOR_STATUS_TONE.get(value, "default")


def _adjudicator_status_display(value: Any, lang: str) -> str:
    labels = {
        "ok": "AI review completed",
        "not_eligible": "AI review not required",
        "low_confidence_preserve": "Low AI confidence",
        "manual_review_degrade": "Manual review required",
        "deterministic_preserved": "Base classification kept",
        "duplicate_unresolved": "Duplicate needs review",
        "degraded": "AI unavailable",
        "invalid": "Invalid AI response",
        "invalid_output": "Invalid AI response",
        "provider_unavailable": "AI unavailable",
        "module_contract_unavailable": "AI unavailable",
    }
    raw_value = _str(value)
    return t(labels.get(raw_value, raw_value), lang)


def _final_decision_basis_display(value: Any, lang: str) -> str:
    labels = {
        "ai_adjudicator": "AI",
        "deterministic": "Base classification",
        "deterministic_preserved": "Base classification",
        "fallback_policy": "System rule",
        "policy_override": "System rule",
        "artifact": "Saved decision",
        "legacy": "Historical decision",
    }
    raw_value = _str(value)
    return t(labels.get(raw_value, raw_value), lang)


def _conversation_role_label(value: Any, lang: str) -> str:
    labels = {
        "root": "First email",
        "reply": "Reply",
        "continuation": "Continuation",
    }
    return t(labels.get(_str(value), _str(value)), lang)


def _attachment_value_display(
    value: Any,
    labels: dict[str, str],
    lang: str,
) -> str:
    raw_value = _str(value)
    return t(labels.get(raw_value, raw_value), lang)


def _responsible_status_display(value: Any, lang: str) -> str:
    labels = {
        "matched": "Found",
        "not_found": "Not found",
        "not_attempted": "Not checked",
    }
    raw_value = _str(value)
    return t(labels.get(raw_value, raw_value), lang)


def _routing_status_tone(value: str) -> str:
    if value == "resolved":
        return "success"
    if value in ("ambiguous", "unresolved"):
        return "warning"
    return "muted"


def _responsible_status_tone(value: str) -> str:
    if value == "matched":
        return "success"
    if value == "not_found":
        return "muted"
    if value in ("ambiguous", "connector_degraded"):
        return "warning"
    return "muted"


def _format_iso_datetime(value: Any) -> str:
    """Parse an ISO datetime string and return as DD.MM.YYYY, HH:MM."""
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return f"{dt.day:02d}.{dt.month:02d}.{dt.year}, {dt.hour:02d}:{dt.minute:02d}"
    except ValueError, TypeError:
        return value


def _read_json(path: Path) -> dict | list | None:
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
    except json.JSONDecodeError, OSError:
        pass
    return None


def _safe_list(value: Any, default: list | None = None) -> list:
    if isinstance(value, list):
        return value
    return default if default is not None else []


def _safe_dict(value: Any, default: dict | None = None) -> dict:
    if isinstance(value, dict):
        return value
    return default if default is not None else {}


def _int(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _str(value: Any) -> str:
    if isinstance(value, str):
        return value
    return ""


def _bounded_str(value: Any, max_chars: int) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:max_chars]


def _resolve_run_dir(storage_dir: Path, run_id: str) -> tuple[Path | None, str]:
    runs_dir = (storage_dir / "runs").resolve()
    run_dir = (runs_dir / run_id).resolve()
    try:
        run_dir.relative_to(runs_dir)
    except ValueError:
        return None, "invalid_run_id"
    if not run_dir.is_dir():
        return None, "not_found"
    return run_dir, ""


def _find_event(
    events: list | None,
    event_id: str,
    event_instance_id: str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(events, list):
        return None
    return _select_event_occurrence(
        [
            evt
            for evt in events
            if isinstance(evt, dict) and evt.get("event_id") == event_id
        ],
        event_instance_id,
    )


def _find_events_for_id(events: list | None, event_id: str) -> list[dict[str, Any]]:
    if not isinstance(events, list):
        return []
    return [
        evt
        for evt in events
        if isinstance(evt, dict) and evt.get("event_id") == event_id
    ]


def _match_by_event_id(
    artifact: dict | None,
    event_id: str,
    event_instance_id: str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(artifact, dict):
        return None
    items = _safe_list(
        artifact.get("results", artifact.get("items", artifact.get("events", [])))
    )
    return _select_event_occurrence(
        [
            item
            for item in items
            if isinstance(item, dict) and item.get("event_id") == event_id
        ],
        event_instance_id,
    )


def _match_writeback_state_event(
    state: dict | None,
    run_id: str,
    source_id: str,
    event_id: str,
    event_instance_id: str | None,
) -> dict[str, Any] | None:
    if not isinstance(state, dict):
        return None
    records = state.get("events")
    if not isinstance(records, dict):
        return None
    candidates = [
        record
        for record in records.values()
        if isinstance(record, dict)
        and record.get("event_id") == event_id
        and record.get("last_run_id") == run_id
        and (not source_id or record.get("source_id") == source_id)
    ]
    return _select_event_occurrence(candidates, event_instance_id)


def _bitrix_delivery_status(writeback: dict[str, Any] | None) -> str:
    if not isinstance(writeback, dict):
        return ""
    outcome = _str(writeback.get("outcome"))
    status = _str(writeback.get("status"))
    attachment_status = _str(writeback.get("email_attachment_status"))
    if attachment_status == "attached" or (
        outcome == "attach_existing" and status == "attached"
    ):
        return "matched_lead"
    if outcome == "create_lead" and status == "created":
        return "lead_created"
    if status in {"planned", "pending", "deferred", "error", "failed"}:
        return status
    return ""


def _bitrix_status_display(status: str, lang: str) -> str:
    if status.startswith("matched_"):
        return t("Matched in Bitrix", lang)
    labels = {
        "lead_created": "Lead created in Bitrix",
        "not_found": "Not found in Bitrix",
        "weak_match": "Needs clarification",
        "ambiguous": "Needs clarification",
        "duplicate_candidate": "Possible duplicate",
        "identity_only_no_target": "Contact without lead/deal",
        "unreconciled": "Reconciliation not run",
        "connector_degraded": "Bitrix connection error",
        "error": "Bitrix reconciliation error",
        "skipped": "Reconciliation not required",
        "planned": "Bitrix delivery planned",
        "pending": "Bitrix delivery pending",
        "deferred": "Bitrix delivery deferred",
        "failed": "Bitrix delivery failed",
    }
    return t(labels.get(status, status.replace("_", " ").title()), lang)


def _match_attachment_extraction_items(
    artifact: dict | None,
    event_id: str,
    event_instance_id: str | None,
) -> list[dict[str, Any]]:
    if not isinstance(artifact, dict):
        return []
    items = _safe_list(artifact.get("items"))
    candidates = [
        item
        for item in items
        if isinstance(item, dict) and item.get("event_id") == event_id
    ]
    if event_instance_id is not None:
        exact = [
            item
            for item in candidates
            if item.get("event_instance_id") == event_instance_id
        ]
        if exact:
            return exact
    return candidates


def _select_event_occurrence(
    candidates: list[dict[str, Any]],
    event_instance_id: str | None,
) -> dict[str, Any] | None:
    if event_instance_id is not None:
        exact = [
            item
            for item in candidates
            if item.get("event_instance_id") == event_instance_id
        ]
        if len(exact) == 1:
            return exact[0]
        legacy = [
            item
            for item in candidates
            if not isinstance(item.get("event_instance_id"), str)
            or not item.get("event_instance_id")
        ]
        return legacy[0] if len(candidates) == len(legacy) == 1 else None
    return candidates[0] if len(candidates) == 1 else None


def _safe_artifact_ref(
    artifact: dict | None, artifact_id: str, storage_dir: Path, run_dir: Path
) -> dict[str, Any]:
    if artifact is None:
        return {
            "available": False,
            "artifact_id": artifact_id,
            "warning": f"{artifact_id} not available",
        }
    return {
        "available": True,
        "artifact_id": artifact_id,
        "url": f"/runs/{run_dir.name}/artifacts/{artifact_id}",
    }


def build_rop_event_detail_read_model(
    storage_dir: Path,
    run_id: str,
    event_id: str,
    *,
    event_instance_id: str | None = None,
    lang: str = "en",
    period: str | None = None,
    filter_params: dict[str, str] | None = None,
    page: int = 1,
    page_size: int = 25,
    sort: str = "received_at",
    order: str = "desc",
) -> dict[str, Any]:
    run_dir, error = _resolve_run_dir(storage_dir, run_id)
    if run_dir is None:
        return {"ok": False, "error": error, "read_only": True}

    warnings: list[str] = []

    normalized = _read_json(run_dir / "normalized_events.json")
    classified = _read_json(run_dir / "classified_events.json")
    attachment_extraction = _read_json(run_dir / "attachment_extraction.json")
    thread_context = _read_json(run_dir / "mail_thread_context.json")
    ai_results = _read_json(run_dir / "rop_ai_assist_results.json")
    ai_adjudicator_results = _read_json(run_dir / "rop_ai_adjudicator_results.json")
    bitrix_reconciliation = _read_json(run_dir / "bitrix_reconciliation.json")
    recipient_routing = _read_json(run_dir / "rop_recipient_routing.json")
    operator_summary = _read_json(run_dir / "operator_summary.json")
    writeback_state = _read_json(
        storage_dir / "interfaces" / "rop_writeback_state.json"
    )

    norm_event = _find_event(_safe_list(normalized), event_id, event_instance_id)
    class_event = _find_event(_safe_list(classified), event_id, event_instance_id)

    if norm_event is None and class_event is None:
        return {
            "ok": False,
            "error": "not_found",
            "message": f"Event {event_id} not found in run {run_id}",
            "read_only": True,
        }

    source_section: dict[str, Any] = {}
    message_section: dict[str, Any] = {}

    if norm_event:
        source_section = {
            "source_id": _str(norm_event.get("source_id")),
            "source_type": _str(norm_event.get("source_type")),
            "source_role": _str(norm_event.get("source_role")),
            "source_display_name": _str(norm_event.get("source_display_name")),
            "client_id": _str(norm_event.get("client_id")),
        }
        message_section = {
            "event_id": event_id,
            "message_id": _str(norm_event.get("message_id")),
            "sender": _str(norm_event.get("sender")),
            "from_email": _str(norm_event.get("from_email")),
            "from_name": _str(norm_event.get("from_name")),
            "to": norm_event.get("to", []),
            "cc": norm_event.get("cc", []),
            "subject": _str(norm_event.get("subject")),
            "date": _str(
                norm_event.get("event_date")
                or norm_event.get("received_at")
                or norm_event.get("timestamp")
                or norm_event.get("created_at")
                or norm_event.get("date")
            ),
            "body_preview": _str(norm_event.get("body_preview", "")),
            "body_preview_chars": _int(norm_event.get("body_preview_chars", 0)),
            "body_preview_truncated": bool(
                norm_event.get("body_preview_truncated", False)
            ),
            "body_preview_source": _str(
                norm_event.get("body_preview_source", "unavailable")
            ),
            "body_short": _str(norm_event.get("body_short", "")),
            "attachment_count": len(_safe_list(norm_event.get("attachments"))),
        }
    elif class_event:
        source_section = {
            "source_id": _str(class_event.get("source_id")),
            "client_id": _str(class_event.get("client_id")),
        }
        message_section = {
            "event_id": event_id,
            "sender": _str(class_event.get("sender")),
            "subject": _str(class_event.get("subject")),
            "body_preview_source": "unavailable",
        }

    if message_section.get("body_preview"):
        pass
    elif norm_event:
        body_short = _str(norm_event.get("body_short", ""))
        if body_short:
            message_section["body_preview"] = body_short
            message_section["body_preview_source"] = "existing_body_short"

    classification_section: dict[str, Any] = {}
    if class_event:
        reason = _bounded_str(
            class_event.get("reasoning") or class_event.get("reason_code", ""),
            _MAX_REASON_TEXT_LENGTH,
        )
        reason_code_str = _bounded_str(
            class_event.get("reason_code"), _MAX_REASON_CODE_LENGTH
        )
        reason_display, reason_warning = get_classification_reason_display(
            reason_code_str, lang
        )
        if reason_warning:
            warnings.append(reason_warning)
        classification_section = {
            "case_type": _str(class_event.get("case_type")),
            "case_subtype": _str(class_event.get("case_subtype")),
            "priority": _str(class_event.get("priority")),
            "confidence": class_event.get("confidence"),
            "reason_code": reason_code_str,
            "reason": reason,
            "reason_display": reason_display,
            "is_fallback": bool(class_event.get("is_fallback")),
            "recommended_queue": _str(class_event.get("recommended_queue", "")),
            "recommended_next_step": _str(class_event.get("recommended_queue", "")),
            "correct_action": _str(class_event.get("correct_action", "")),
            "should_rop_see": class_event.get("should_rop_see"),
        }
        duplicate_block = class_event.get("duplicate")
        if isinstance(duplicate_block, dict):
            base_classification = class_event.get("base_classification")
            candidate = duplicate_block.get("candidate")
            classification_section["base_case_type"] = (
                _str(base_classification.get("case_type"))
                if isinstance(base_classification, dict)
                else ""
            )
            classification_section["duplicate"] = {
                "is_duplicate": bool(duplicate_block.get("is_duplicate", False)),
                "confidence": duplicate_block.get("confidence"),
                "reason_code": _bounded_str(
                    duplicate_block.get("reason_code"), _MAX_REASON_CODE_LENGTH
                ),
                "reason_path": [
                    str(item)
                    for item in duplicate_block.get("reason_path", [])
                    if isinstance(item, str)
                ],
                "reasoning": _bounded_str(
                    duplicate_block.get("reasoning"), _MAX_REASON_TEXT_LENGTH
                ),
                "candidate_event_id": (
                    _str(candidate.get("event_id"))
                    if isinstance(candidate, dict)
                    else ""
                ),
                "existing_lead_id": (
                    _str(candidate.get("existing_lead_id"))
                    if isinstance(candidate, dict)
                    else ""
                ),
                "similarity_score": (
                    candidate.get("similarity_score")
                    if isinstance(candidate, dict)
                    else None
                ),
                "matched_fields": [
                    str(item)
                    for item in candidate.get("matched_fields", [])
                    if isinstance(item, str)
                ]
                if isinstance(candidate, dict)
                else [],
                "is_fallback": bool(duplicate_block.get("is_fallback", False)),
            }
    else:
        warnings.append("Event not found in classified_events.json")

    deterministic_keys = (
        "deterministic_case_type",
        "deterministic_case_subtype",
        "deterministic_recommended_queue",
        "deterministic_correct_action",
        "deterministic_confidence",
        "deterministic_reason_code",
    )

    if class_event and any(key in class_event for key in deterministic_keys):
        deterministic_reason_code = _bounded_str(
            class_event.get("deterministic_reason_code"),
            _MAX_REASON_CODE_LENGTH,
        )
        deterministic_reason_display, deterministic_reason_warning = (
            get_classification_reason_display(deterministic_reason_code, lang)
        )
        if deterministic_reason_warning:
            warnings.append(deterministic_reason_warning)
        deterministic_section = {
            "available": True,
            "case_type": _bounded_str(
                class_event.get("deterministic_case_type"),
                _MAX_REASON_CODE_LENGTH,
            ),
            "case_subtype": _bounded_str(
                class_event.get("deterministic_case_subtype"),
                _MAX_REASON_CODE_LENGTH,
            ),
            "recommended_queue": _bounded_str(
                class_event.get("deterministic_recommended_queue"),
                _MAX_REASON_CODE_LENGTH,
            ),
            "correct_action": _bounded_str(
                class_event.get("deterministic_correct_action"),
                _MAX_REASON_CODE_LENGTH,
            ),
            "confidence": class_event.get("deterministic_confidence"),
            "reason_code": deterministic_reason_code,
            "reason_display": deterministic_reason_display,
            "is_fallback": bool(class_event.get("is_fallback")),
        }
    else:
        deterministic_section = {"available": False}

    thread_section: dict[str, Any] = {}
    thread_available = False
    if isinstance(thread_context, dict):
        contexts = _safe_list(thread_context.get("contexts"))
        for ctx in contexts:
            if isinstance(ctx, dict) and ctx.get("event_id") == event_id:
                thread_section = {
                    "available": True,
                    "thread_id": _str(ctx.get("thread_id")),
                    "previous_event_ids": _safe_list(ctx.get("previous_event_ids")),
                    "reply_or_forward": _nullable_bool(
                        ctx.get("reply_or_forward"), ctx.get("is_reply_or_forward")
                    ),
                    "thread_connection": _str(
                        ctx.get("thread_connection")
                        or ctx.get("connection")
                        or ctx.get("link_reason")
                    ),
                    "reason_codes": _safe_list(ctx.get("reason_codes")),
                }
                thread_available = True
                break
    if not thread_available:
        thread_section = {"available": False}

    ai_section: dict[str, Any] = {}
    if isinstance(ai_results, dict):
        matched = _match_by_event_id(ai_results, event_id, event_instance_id)
        if matched:
            ai_section = {
                "ai_assist_status": _str(
                    matched.get("ai_assist_status", matched.get("status", ""))
                ),
                "ai_assist_used": _nullable_bool(
                    matched.get("ai_assist_used"), matched.get("used")
                ),
                "ai_assist_confidence": matched.get("ai_assist_confidence"),
                "final_case_type": _str(matched.get("final_case_type")),
                "final_priority": _str(matched.get("final_priority")),
                "final_recommended_queue": _str(
                    matched.get("final_recommended_queue", "")
                ),
                "final_correct_action": _str(matched.get("final_correct_action", "")),
                "final_should_rop_see": matched.get("final_should_rop_see"),
            }
        else:
            ai_section = {"ai_assist_status": "not_applied"}
    else:
        ai_section = {"ai_assist_status": "unavailable"}

    final_decision_section: dict[str, Any] = {}
    adj_section: dict[str, Any] = {}
    matched_adjudicator: dict[str, Any] | None = None

    if isinstance(ai_adjudicator_results, dict):
        matched_adjudicator = _match_by_event_id(
            ai_adjudicator_results,
            event_id,
            event_instance_id,
        )
        if matched_adjudicator:
            ai_reason_code_str = _bounded_str(
                matched_adjudicator.get("ai_reason_code", ""),
                _MAX_REASON_CODE_LENGTH,
            )
            ai_status = _bounded_str(
                matched_adjudicator.get("ai_status", ""),
                _MAX_REASON_CODE_LENGTH,
            )
            expected_reasonless_status = (
                not ai_reason_code_str and ai_status in _EXPECTED_REASONLESS_AI_STATUSES
            )
            ai_evidence_list = matched_adjudicator.get(
                "ai_evidence_codes",
                [],
            )
            if not isinstance(ai_evidence_list, list):
                ai_evidence_list = []

            if len(ai_evidence_list) > AI_EVIDENCE_CODES_MAX:
                warnings.append("ai_evidence_codes exceeded maximum; truncated")

            ai_reason_display_val, ai_reason_warn = get_ai_reason_display(
                ai_reason_code_str if ai_reason_code_str else None,
                lang,
                ai_status,
                _bounded_str(
                    matched_adjudicator.get("merge_reason", ""),
                    _MAX_REASON_CODE_LENGTH,
                ),
                "ai_reason_code" in matched_adjudicator
                and not expected_reasonless_status,
            )
            if ai_reason_warn and not expected_reasonless_status:
                warnings.append(ai_reason_warn)

            ai_evidence_display_list: list[dict[str, str]] = []
            for code in ai_evidence_list[:AI_EVIDENCE_CODES_MAX]:
                if not isinstance(code, str) or code not in AI_EVIDENCE_CODES:
                    warnings.append("unknown ai evidence code ignored")
                    continue

                ev_display, ev_warn = get_ai_evidence_display(code, lang)
                if ev_warn:
                    warnings.append(ev_warn)

                ai_evidence_display_list.append({"code": code, "display": ev_display})
            adj_section = {
                "ai_adjudicator_used": _nullable_bool(
                    matched_adjudicator.get("ai_used")
                ),
                "ai_adjudicator_status": _bounded_str(
                    matched_adjudicator.get("ai_status", ""),
                    _MAX_REASON_CODE_LENGTH,
                ),
                "ai_adjudicator_confidence": matched_adjudicator.get("ai_confidence"),
                "ai_adjudicator_reason": _bounded_str(
                    matched_adjudicator.get("ai_reason", ""),
                    _MAX_REASON_TEXT_LENGTH,
                ),
                "ai_adjudicator_reason_code": ai_reason_code_str,
                "ai_adjudicator_evidence_codes": ai_evidence_display_list,
                "ai_adjudicator_reason_display": ai_reason_display_val,
                "final_case_type": _str(matched_adjudicator.get("final_case_type", "")),
                "final_case_subtype": _str(
                    matched_adjudicator.get("final_case_subtype", "")
                ),
                "final_recommended_queue": _str(
                    matched_adjudicator.get("final_recommended_queue", "")
                ),
                "final_correct_action": _str(
                    matched_adjudicator.get("final_correct_action", "")
                ),
            }

    final_decisions, _ = load_or_build_final_decisions(run_dir)
    final_decision = find_final_decision(
        final_decisions,
        event_id,
        event_instance_id,
    )
    if final_decision:
        final_case_subtype = final_decision.get("final_case_subtype")
        attention_reason = _bounded_str(
            final_decision.get("attention_reason"), _MAX_REASON_TEXT_LENGTH
        )
        attention_reason_code = _bounded_str(
            final_decision.get("attention_reason_code"), _MAX_REASON_CODE_LENGTH
        )
        attention_evidence_list = final_decision.get("attention_evidence_codes")
        if not isinstance(attention_evidence_list, list):
            attention_evidence_list = []
        needs_attention = final_decision.get("needs_attention") is True
        attn_reason_display_val: str | None = None
        attn_reason_warn: str | None = None
        if needs_attention:
            attn_reason_display_val, attn_reason_warn = get_attention_reason_display(
                attention_reason_code or None,
                lang,
                _bounded_str(
                    matched_adjudicator.get("merge_reason", ""),
                    _MAX_REASON_CODE_LENGTH,
                )
                if matched_adjudicator
                else None,
            )
        if attn_reason_warn:
            warnings.append(attn_reason_warn)
        attn_evidence_display_list: list[dict[str, str]] = []
        for code in attention_evidence_list:
            if isinstance(code, str):
                ev_display, ev_warn = get_ai_evidence_display(code, lang)
                if ev_warn:
                    warnings.append(ev_warn)
                attn_evidence_display_list.append({"code": code, "display": ev_display})
        final_decision_section = {
            "event_id": _str(final_decision.get("event_id", "")),
            "final_case_type": _str(final_decision.get("final_case_type", "")),
            "final_case_subtype": (
                final_case_subtype if isinstance(final_case_subtype, str) else None
            ),
            "final_queue": _str(final_decision.get("final_queue", "")),
            "final_action": _str(final_decision.get("final_action", "")),
            "final_confidence": final_decision.get("final_confidence"),
            "final_decision_source": _str(
                final_decision.get("final_decision_source", "")
            ),
            "classification_override_reason": (
                t("Sender blacklisted", lang)
                if final_decision.get("policy_override_reason")
                == "sender_blacklisted"
                else None
            ),
            "needs_attention": needs_attention,
            "attention_reason": attention_reason or None,
            "attention_reason_code": attention_reason_code or None,
            "attention_evidence_codes": attn_evidence_display_list,
            "attention_reason_display": attn_reason_display_val,
            "automation_allowed": False,
            "bitrix_write_allowed": False,
        }

    reconciliation_status = ""
    reconciliation_item: dict[str, Any] | None = None
    if isinstance(bitrix_reconciliation, dict):
        reconciliation_item = _match_by_event_id(
            bitrix_reconciliation,
            event_id,
            event_instance_id,
        )
        if reconciliation_item:
            reconciliation_status = _str(
                reconciliation_item.get("bitrix_match_status")
                or reconciliation_item.get("match_status")
                or reconciliation_item.get("bitrix_status")
                or reconciliation_item.get("status")
            )

    reconciliation_entity_type = _str(
        reconciliation_item.get("bitrix_entity_type")
        or reconciliation_item.get("entity_type", "")
        if reconciliation_item
        else ""
    )
    reconciliation_entity_id = _int(
        reconciliation_item.get("bitrix_entity_id")
        or reconciliation_item.get("entity_id", 0)
        if reconciliation_item
        else 0
    )
    writeback = _match_writeback_state_event(
        writeback_state if isinstance(writeback_state, dict) else None,
        run_id,
        _str(source_section.get("source_id")),
        event_id,
        event_instance_id,
    )
    delivery_status = _bitrix_delivery_status(writeback)
    if delivery_status:
        bitrix_section = {
            "available": True,
            "bitrix_status": delivery_status,
            "status_source": "writeback",
            "reconciliation_status": reconciliation_status,
            "writeback_outcome": _str(writeback.get("outcome")),
            "writeback_status": _str(writeback.get("status")),
            "match_quality": (
                reconciliation_item.get("match_quality")
                if reconciliation_item
                else None
            ),
            "candidate_count": _int(
                reconciliation_item.get("candidate_count", 0)
                if reconciliation_item
                else 0
            ),
            "entity_type": _str(writeback.get("target_entity_type"))
            or reconciliation_entity_type,
            "entity_id": _int(writeback.get("target_entity_id", 0))
            or reconciliation_entity_id,
            "entity_url": (
                _str(reconciliation_item.get("entity_url", ""))
                if reconciliation_item
                else ""
            ),
        }
    elif reconciliation_item:
        bitrix_section = {
            "available": True,
            "bitrix_status": reconciliation_status,
            "status_source": "reconciliation",
            "reconciliation_status": reconciliation_status,
            "writeback_outcome": "",
            "writeback_status": "",
            "match_quality": reconciliation_item.get("match_quality"),
            "candidate_count": _int(reconciliation_item.get("candidate_count", 0)),
            "entity_type": reconciliation_entity_type,
            "entity_id": reconciliation_entity_id,
            "entity_url": _str(reconciliation_item.get("entity_url", "")),
        }
    else:
        bitrix_section = {"available": False}

    recipient_routing_section: dict[str, Any] = {}
    routing_available = False
    if isinstance(recipient_routing, dict):
        item = _match_by_event_id(recipient_routing, event_id, event_instance_id)
        if item:
            responsible = _safe_dict(item.get("responsible"))
            recipient_routing_section = {
                "available": True,
                "recipient": _str(item.get("recipient")),
                "recipient_candidates": _safe_list(item.get("recipient_candidates")),
                "recipient_evidence_source": _str(
                    item.get("recipient_evidence_source")
                ),
                "recipient_status": _str(item.get("recipient_status")),
                "responsible_status": _str(responsible.get("status")),
                "proposed_responsible_user_id": responsible.get("user_id"),
                "proposed_responsible_name": _str(responsible.get("name")),
                "proposed_responsible_email": _str(responsible.get("email")),
            }
            routing_available = True
    if not routing_available:
        recipient_routing_section = {"available": False}

    attachments_section: list[dict[str, Any]] = []
    extraction_items = _match_attachment_extraction_items(
        attachment_extraction, event_id, event_instance_id
    )
    if extraction_items:
        for att in extraction_items:
            if isinstance(att, dict):
                attachments_section.append(
                    {
                        "attachment_id": _str(att.get("attachment_id")),
                        "filename": _str(att.get("filename")),
                        "content_type": _str(att.get("content_type")),
                        "size_bytes": _int(att.get("size_bytes", att.get("size", 0))),
                        "extraction_status": _str(att.get("extraction_status")),
                        "storage_status": _str(att.get("storage_status")),
                        "reason_code": _str(att.get("reason_code")),
                        "analysis_status": _str(att.get("analysis_status")),
                        "analysis_reason_code": _str(att.get("analysis_reason_code")),
                        "sha256": _str(att.get("sha256")),
                        "download_url": _str(att.get("download_url")),
                        "preview_available": bool(att.get("preview_available")),
                        "text_preview": _str(att.get("text_preview")),
                    }
                )
    elif norm_event:
        for att in _safe_list(norm_event.get("attachments")):
            if isinstance(att, dict):
                attachments_section.append(
                    {
                        "filename": _str(att.get("filename")),
                        "content_type": _str(att.get("content_type")),
                        "size_bytes": _int(att.get("size", att.get("size_bytes", 0))),
                    }
                )
    if not attachments_section:
        attachments_section = []

    evidence_ids = [
        "normalized_events_json",
        "classified_events_json",
        "attachment_extraction_json",
        "attachment_manifest_json",
        "attachment_analysis_json",
        "mail_thread_context_json",
        "rop_ai_assist_results_json",
        "rop_ai_adjudicator_results_json",
        "rop_final_decisions_json",
        "bitrix_reconciliation_json",
        "rop_recipient_routing_json",
        "rop_review_table_tsv",
        "operator_summary_json",
    ]
    evidence_links: list[dict[str, Any]] = []
    for aid in evidence_ids:
        available = resolve_artifact_path(storage_dir, run_id, aid) is not None
        evidence_links.append(
            {
                "artifact_id": aid,
                "available": available,
                "url": f"/runs/{run_id}/artifacts/{aid}" if available else None,
            }
        )

    if isinstance(attachment_extraction, dict):
        extracted = _match_by_event_id(
            attachment_extraction,
            event_id,
            event_instance_id,
        )
        if extracted:
            evidence_links.append(
                {
                    "artifact_id": "attachment_extraction_json",
                    "available": True,
                    "url": f"/runs/{run_id}/artifacts/attachment_extraction_json",
                }
            )

    if isinstance(operator_summary, dict):
        operator_text = _str(operator_summary.get("summary", ""))
    else:
        operator_text = ""

    conversation_section = build_conversation_timeline(
        storage_dir,
        run_id,
        event_id,
        event_instance_id,
    )
    if not conversation_section.get("available"):
        conversation_section = {"available": False}

    if isinstance(conversation_section, dict) and final_decision_section:
        conversation_event = _select_event_occurrence(
            [
                item
                for item in _safe_list(conversation_section.get("events"))
                if isinstance(item, dict) and item.get("event_id") == event_id
            ],
            event_instance_id,
        )

        if conversation_event is not None:
            writeback = _safe_dict(conversation_event.get("writeback"))
            if (
                writeback.get("outcome") == "attach_existing"
                and writeback.get("target_provenance") in _TRUSTED_ATTACH_PROVENANCES
            ):
                final_decision_section["semantic_case_type"] = _str(
                    final_decision_section.get("final_case_type", "")
                )
                final_decision_section["final_case_type"] = "existing_deal"

    result = {
        "run_id": run_id,
        "event_id": event_id,
        "event_instance_id": event_instance_id or "",
        "source": source_section,
        "message": message_section,
        "classification": classification_section,
        "deterministic": deterministic_section,
        "thread": thread_section,
        "ai_assist": ai_section,
        "ai_adjudicator": adj_section,
        "final_decision": final_decision_section,
        "bitrix": bitrix_section,
        "conversation": conversation_section,
        "recipient_routing": recipient_routing_section,
        "attachments": attachments_section,
        "evidence_links": evidence_links,
        "operator_summary": operator_text,
        "warnings": warnings,
        "read_only": True,
    }

    return result


def _kv(
    label: str, value: Any, *, hint: str | None = None, **kwargs: Any
) -> dict[str, Any]:
    """Create a key_value item with optional type hint for visual styling."""
    item: dict[str, Any] = {"label": label, "value": value}
    if hint:
        item["type_hint"] = hint
    item.update(kwargs)
    return item


def _bitrix_entity_href(entity_type: Any, entity_id: Any) -> str:
    normalized_type = _str(entity_type).lower()
    normalized_id = _int(entity_id)
    if (
        normalized_type not in _BITRIX_LINKABLE_ENTITY_TYPES
        or normalized_id <= 0
    ):
        return ""
    return f"/rop/bitrix/{normalized_type}/{normalized_id}"


def _format_size(size_bytes: Any) -> str:
    """Convert bytes to a human-readable file size string."""
    if not isinstance(size_bytes, (int, float)) or size_bytes < 0:
        return "n/a"
    if size_bytes == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(size_bytes)
    while size >= 1024 and i < len(units) - 1:
        size /= 1024
        i += 1
    if i == 0:
        return f"{int(size)} {units[i]}"
    return f"{size:.1f} {units[i]}"


def _page_kv_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return items


def build_rop_event_detail_page_model(
    storage_dir: Path,
    run_id: str,
    event_id: str,
    *,
    event_instance_id: str | None = None,
    lang: str = "en",
    period: str | None = None,
    filter_params: dict[str, str] | None = None,
    page: int = 1,
    page_size: int = 25,
    sort: str = "received_at",
    order: str = "desc",
) -> dict[str, Any]:
    data = build_rop_event_detail_read_model(
        storage_dir=storage_dir,
        run_id=run_id,
        event_id=event_id,
        event_instance_id=event_instance_id,
        lang=lang,
    )
    if not data.get("ok", True):
        return data

    source = _safe_dict(data.get("source"))
    message = _safe_dict(data.get("message"))
    classification = _safe_dict(data.get("classification"))
    deterministic = _safe_dict(data.get("deterministic"))
    basic_classification = (
        deterministic if deterministic.get("available", False) else classification
    )
    duplicate = _safe_dict(classification.get("duplicate"))
    ai_adjudicator = _safe_dict(data.get("ai_adjudicator"))
    final_decision = _safe_dict(data.get("final_decision"))
    bitrix = _safe_dict(data.get("bitrix"))
    conversation = _safe_dict(data.get("conversation"))
    recipient_routing = _safe_dict(data.get("recipient_routing"))
    attachments = _safe_list(data.get("attachments"))

    sections: list[dict[str, Any]] = [
        {
            "kind": "key_value",
            "title": t("Source", lang),
            "items": _page_kv_items(
                [
                    _kv(t("Source", lang), source.get("source_id")),
                    _kv(t("Client", lang), source.get("client_id")),
                    _kv(t("Source type", lang), source.get("source_type")),
                    _kv(t("Source role", lang), source.get("source_role")),
                ]
            ),
        },
        {
            "kind": "key_value",
            "title": t("Message", lang),
            "items": _page_kv_items(
                [
                    _kv(t("Subject", lang), message.get("subject")),
                    _kv(t("Sender", lang), message.get("sender")),
                    _kv(
                        t("Body preview", lang),
                        message.get("body_preview"),
                        variant="modal_text",
                    ),
                    _kv(t("Date", lang), _format_iso_datetime(message.get("date"))),
                ]
            ),
        },
        {
            "kind": "key_value",
            "title": t("Basic classification", lang),
            "no_data": not bool(basic_classification),
            "items": _page_kv_items(
                [
                    _kv(
                        t("Case type", lang),
                        case_type_label(basic_classification.get("case_type"), lang),
                        variant="badge",
                        tone="default",
                    ),
                    _kv(
                        t("Subtype", lang),
                        case_subtype_label(
                            basic_classification.get("case_subtype"), lang
                        ),
                    ),
                    _kv(
                        t("Reason", lang),
                        basic_classification.get("reason_display"),
                        hint="localized_reason",
                    ),
                    _kv(
                        t("Confidence", lang),
                        basic_classification.get("confidence"),
                        hint="confidence",
                    ),
                    _kv(
                        t("Priority", lang),
                        classification.get("priority"),
                        variant="badge",
                        tone=_priority_tone(classification.get("priority", "")),
                    ),
                    _kv(
                        t("Fallback classification", lang),
                        _bool_display(basic_classification.get("is_fallback"), lang),
                        variant="boolean",
                    ),
                    *(
                        [
                            _kv(
                                t("Base case type", lang),
                                case_type_label(
                                    classification.get("base_case_type"), lang
                                ),
                            ),
                            _kv(
                                t("Duplicate candidate event", lang),
                                duplicate.get("candidate_event_id"),
                            ),
                            _kv(
                                t("Duplicate candidate entity", lang),
                                duplicate.get("existing_lead_id"),
                            ),
                            _kv(
                                t("Duplicate confidence", lang),
                                duplicate.get("confidence"),
                                hint="confidence",
                            ),
                            _kv(
                                t("Duplicate reasoning", lang),
                                duplicate.get("reasoning"),
                                variant="long_text",
                                collapsible=True,
                                display=duplicate.get("reasoning", ""),
                            ),
                        ]
                        if duplicate.get("is_duplicate") is True
                        else []
                    ),
                ]
            ),
        },
        {
            "kind": "key_value",
            "title": t("AI review", lang),
            "no_data": not bool(ai_adjudicator),
            "items": _page_kv_items(
                [
                    *(
                        [
                            _kv(
                                t("AI proposed case type", lang),
                                case_type_label(
                                    ai_adjudicator.get("final_case_type"), lang
                                ),
                                variant="badge",
                                tone="default",
                            ),
                        ]
                        if ai_adjudicator.get("ai_adjudicator_used") is True
                        else []
                    ),
                    _kv(
                        t("AI adjudicator status", lang),
                        _adjudicator_status_display(
                            ai_adjudicator.get("ai_adjudicator_status"), lang
                        ),
                        variant="badge",
                        tone=_adjudicator_status_tone(
                            ai_adjudicator.get("ai_adjudicator_status", "")
                        ),
                    ),
                    _kv(
                        t("AI adjudicator reason", lang),
                        ai_adjudicator.get("ai_adjudicator_reason_display"),
                        hint="localized_reason",
                    ),
                    _kv(
                        t("AI adjudicator confidence", lang),
                        ai_adjudicator.get("ai_adjudicator_confidence"),
                        hint="confidence",
                    ),
                    _kv(
                        t("Reasoning", lang),
                        ai_adjudicator.get("ai_adjudicator_reason"),
                        variant="long_text",
                        collapsible=True,
                        display=ai_adjudicator.get("ai_adjudicator_reason", ""),
                    ),
                ]
            ),
        },
        {
            "kind": "key_value",
            "title": t("Final decision", lang),
            "no_data": not bool(final_decision),
            "items": _page_kv_items(
                [
                    _kv(
                        t("Final case type", lang),
                        case_type_label(final_decision.get("final_case_type"), lang),
                        variant="badge",
                        tone="default",
                    ),
                    _kv(
                        t("Decision basis", lang),
                        _final_decision_basis_display(
                            final_decision.get("final_decision_source"), lang
                        ),
                        variant="badge",
                        tone="default",
                    ),
                    *(
                        [
                            _kv(
                                t("Classification override reason", lang),
                                final_decision.get("classification_override_reason"),
                                variant="badge",
                                tone="warning",
                            )
                        ]
                        if final_decision.get("classification_override_reason")
                        else []
                    ),
                    _kv(
                        t("Final confidence", lang),
                        final_decision.get("final_confidence"),
                        hint="confidence",
                    ),
                ]
            ),
        },
        {
            "kind": "key_value",
            "title": t("Bitrix evidence", lang),
            "no_data": not bitrix.get("available", False),
            "items": _page_kv_items(
                [
                    _kv(
                        t("Bitrix status", lang),
                        _bitrix_status_display(
                            _str(bitrix.get("bitrix_status")), lang
                        ),
                    ),
                    *(
                        [
                            _kv(
                                t("Bitrix check before delivery", lang),
                                _bitrix_status_display(
                                    _str(bitrix.get("reconciliation_status")), lang
                                ),
                            )
                        ]
                        if bitrix.get("status_source") == "writeback"
                        and bitrix.get("reconciliation_status")
                        else []
                    ),
                    *(
                        [
                            _kv(
                                t("Candidate count", lang),
                                bitrix.get("candidate_count"),
                            )
                        ]
                        if _str(bitrix.get("reconciliation_status"))
                        in {
                            "weak_match",
                            "ambiguous",
                            "duplicate_candidate",
                            "identity_only_no_target",
                        }
                        and _int(bitrix.get("candidate_count")) >= 2
                        else []
                    ),
                    *(
                        [_kv(t("Entity type", lang), bitrix.get("entity_type"))]
                        if _str(bitrix.get("entity_type"))
                        else []
                    ),
                    *(
                        [
                            _kv(
                                t("Entity ID", lang),
                                bitrix.get("entity_id"),
                                href=_bitrix_entity_href(
                                    bitrix.get("entity_type"),
                                    bitrix.get("entity_id"),
                                ),
                            )
                        ]
                        if _int(bitrix.get("entity_id")) > 0
                        else []
                    ),
                ]
            ),
        },
        {
            "kind": "key_value",
            "title": t("Recipient routing", lang),
            "no_data": not recipient_routing.get("available", False),
            "items": _page_kv_items(
                [
                    _kv(t("Recipient", lang), recipient_routing.get("recipient")),
                    _kv(
                        t("Responsible", lang),
                        recipient_routing.get("proposed_responsible_name")
                        or recipient_routing.get("proposed_responsible_email"),
                    ),
                    _kv(
                        t("Responsible status", lang),
                        _responsible_status_display(
                            recipient_routing.get("responsible_status"), lang
                        ),
                        variant="badge",
                        tone=_responsible_status_tone(
                            recipient_routing.get("responsible_status", "")
                        ),
                    ),
                ]
            ),
        },
        {
            "kind": "table",
            "title": t("Conversation timeline", lang),
            "no_data": not conversation.get("available", False),
            "columns": [
                {"key": "subject", "label": t("Subject", lang), "cell": "link"},
                {"key": "sender", "label": t("Sender", lang)},
                {"key": "date", "label": t("Date", lang)},
                {"key": "role", "label": t("Role", lang)},
                {"key": "case_type", "label": t("Case type", lang)},
                {"key": "writeback", "label": t("CRM outcome", lang)},
            ],
            "rows": [
                {
                    "subject": {
                        "label": item.get("subject"),
                        "href": (
                            build_rop_event_url(
                                _str(item.get("event_id")),
                                _str(item.get("run_id")),
                                event_instance_id=_str(item.get("event_instance_id"))
                                or None,
                                lang=lang,
                            )
                            if _str(item.get("event_id")) and _str(item.get("run_id"))
                            else ""
                        ),
                    },
                    "sender": item.get("sender"),
                    "date": _format_iso_datetime(item.get("date")),
                    "role": _conversation_role_label(item.get("role"), lang),
                    "case_type": case_type_label(item.get("case_type"), lang),
                    "writeback": writeback_outcome_label(
                        item.get("writeback", {}).get("outcome", ""), lang
                    ),
                }
                for item in _safe_list(conversation.get("events"))
            ],
        },
    ]

    attachment_rows = [
        {
            "filename": {
                "label": attachment.get("filename"),
                "href": attachment.get("download_url"),
            },
            "content_type": _attachment_value_display(
                attachment.get("content_type"),
                _ATTACHMENT_CONTENT_TYPE_LABELS,
                lang,
            ),
            "size_bytes": _format_size(attachment.get("size_bytes")),
            "storage_status": _attachment_value_display(
                attachment.get("storage_status"),
                _ATTACHMENT_STORAGE_STATUS_LABELS,
                lang,
            ),
            "reason_code": _attachment_value_display(
                attachment.get("reason_code"),
                _ATTACHMENT_REASON_LABELS,
                lang,
            ),
            "analysis_status": _attachment_value_display(
                attachment.get("analysis_status"),
                _ATTACHMENT_ANALYSIS_STATUS_LABELS,
                lang,
            ),
            "download_url": attachment.get("download_url"),
        }
        for attachment in attachments
        if isinstance(attachment, dict)
    ]
    if attachment_rows:
        sections.append(
            {
                "kind": "table",
                "title": t("Attached files", lang),
                "columns": [
                    {
                        "key": "filename",
                        "label": t("Filename", lang),
                        "cell": "link",
                    },
                    {"key": "content_type", "label": t("Content type", lang)},
                    {"key": "size_bytes", "label": t("Size", lang)},
                    {
                        "key": "storage_status",
                        "label": t("Storage status", lang),
                    },
                    {
                        "key": "reason_code",
                        "label": t("Processing result", lang),
                    },
                    {
                        "key": "analysis_status",
                        "label": t("Analysis status", lang),
                    },
                ],
                "rows": attachment_rows,
            }
        )

    # Sort: filled sections first, "not used" sections last
    sections.sort(key=lambda s: s.get("no_data", False))

    bitrix_title = t("Bitrix evidence", lang)
    recipient_routing_title = t("Recipient routing", lang)
    bitrix_index = next(
        (
            index
            for index, section in enumerate(sections)
            if section.get("title") == bitrix_title
        ),
        None,
    )
    recipient_routing_index = next(
        (
            index
            for index, section in enumerate(sections)
            if section.get("title") == recipient_routing_title
        ),
        None,
    )
    if bitrix_index is not None and recipient_routing_index is not None:
        recipient_routing_section = sections.pop(recipient_routing_index)
        if recipient_routing_index < bitrix_index:
            bitrix_index -= 1
        sections.insert(bitrix_index + 1, recipient_routing_section)

    back_href = build_rop_url(
        tab="queue",
        run_id=run_id,
        period=period,
        lang=lang,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
        filter_params=filter_params,
    )

    return {
        "page_id": "rop_event_detail",
        "title": t("Event Detail", lang),
        "subtitle": f"{run_id} · {event_id}",
        "back_href": back_href,
        "warnings": [w for w in _safe_list(data.get("warnings")) if isinstance(w, str)],
        "sections": sections,
    }
