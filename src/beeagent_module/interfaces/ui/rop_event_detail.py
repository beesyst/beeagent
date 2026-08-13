from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from beeagent_module.core.rop_final_decision import (
    find_final_decision,
    load_or_build_final_decisions,
)
from beeagent_module.core.rop_reason_contract import (
    AI_EVIDENCE_CODES,
    AI_EVIDENCE_CODES_MAX,
)
from beeagent_module.interfaces.ui.artifacts import resolve_artifact_path
from beeagent_module.interfaces.ui.locale import t
from beeagent_module.interfaces.ui.reason_catalog import (
    get_ai_evidence_display,
    get_ai_reason_display,
    get_attention_reason_display,
    get_classification_reason_display,
)
from beeagent_module.interfaces.ui.url_builder import build_rop_url

_PRIORITY_TONE = {
    "low": "muted",
    "medium": "warning",
    "high": "danger",
    "critical": "danger",
}

_ADJUDICATOR_STATUS_TONE = {
    "ok": "success",
    "low_confidence_preserve": "warning",
    "manual_review_degrade": "warning",
    "invalid_output": "danger",
    "provider_unavailable": "danger",
    "module_contract_unavailable": "danger",
}

_QUEUE_ACTION_TONE = {
    "manual_review": "warning",
    "ignore": "muted",
}
_MAX_REASON_TEXT_LENGTH = 600
_MAX_REASON_CODE_LENGTH = 80


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


def _queue_action_tone(value: str) -> str:
    return _QUEUE_ACTION_TONE.get(value, "default")


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
    for evt in events:
        if not isinstance(evt, dict) or evt.get("event_id") != event_id:
            continue
        if (
            event_instance_id is None
            or evt.get("event_instance_id") == event_instance_id
        ):
            return evt
    return None


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
    for item in items:
        if not isinstance(item, dict) or item.get("event_id") != event_id:
            continue
        if (
            event_instance_id is None
            or item.get("event_instance_id") == event_instance_id
        ):
            return item
    return None


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
    action_drafts = _read_json(run_dir / "rop_action_drafts.json")
    operator_summary = _read_json(run_dir / "operator_summary.json")

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
                _bounded_str(
                    matched_adjudicator.get("ai_status", ""),
                    _MAX_REASON_CODE_LENGTH,
                ),
                _bounded_str(
                    matched_adjudicator.get("merge_reason", ""),
                    _MAX_REASON_CODE_LENGTH,
                ),
            )
            if ai_reason_warn:
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
            "needs_attention": needs_attention,
            "attention_reason": attention_reason or None,
            "attention_reason_code": attention_reason_code or None,
            "attention_evidence_codes": attn_evidence_display_list,
            "attention_reason_display": attn_reason_display_val,
            "automation_allowed": False,
            "bitrix_write_allowed": False,
        }

    bitrix_section: dict[str, Any] = {}
    bitrix_available = False
    if isinstance(bitrix_reconciliation, dict):
        items = _safe_list(bitrix_reconciliation.get("items"))
        for item in items:
            if isinstance(item, dict) and item.get("event_id") == event_id:
                bitrix_section = {
                    "available": True,
                    "bitrix_status": _str(
                        item.get("bitrix_match_status")
                        or item.get("match_status")
                        or item.get("bitrix_status")
                        or item.get("status")
                    ),
                    "match_quality": item.get("match_quality"),
                    "candidate_count": _int(item.get("candidate_count", 0)),
                    "entity_type": _str(item.get("entity_type", "")),
                    "entity_id": _int(item.get("entity_id", 0)),
                    "entity_url": _str(item.get("entity_url", "")),
                }
                bitrix_available = True
                break
    if not bitrix_available:
        bitrix_section = {"available": False}

    action_draft_section: dict[str, Any] = {}
    draft_available = False
    if isinstance(action_drafts, dict):
        items = _safe_list(action_drafts.get("items", action_drafts.get("drafts", [])))
        for item in items:
            if isinstance(item, dict) and item.get("event_id") == event_id:
                action_draft_section = {
                    "available": True,
                    "action_type": _str(item.get("action_type", item.get("type", ""))),
                    "summary": _str(item.get("summary", item.get("description", ""))),
                    "draft_status": _str(item.get("status", "draft")),
                    "read_only": True,
                }
                draft_available = True
                break
    if not draft_available:
        action_draft_section = {"available": False}

    attachments_section: list[dict[str, Any]] = []
    if norm_event:
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
        "mail_thread_context_json",
        "rop_ai_assist_results_json",
        "rop_ai_adjudicator_results_json",
        "rop_final_decisions_json",
        "bitrix_reconciliation_json",
        "rop_action_drafts_json",
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

    result = {
        "run_id": run_id,
        "event_id": event_id,
        "event_instance_id": event_instance_id or "",
        "source": source_section,
        "message": message_section,
        "classification": classification_section,
        "thread": thread_section,
        "ai_assist": ai_section,
        "ai_adjudicator": adj_section,
        "final_decision": final_decision_section,
        "bitrix": bitrix_section,
        "action_draft": action_draft_section,
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
    duplicate = _safe_dict(classification.get("duplicate"))
    thread = _safe_dict(data.get("thread"))
    ai_assist = _safe_dict(data.get("ai_assist"))
    ai_adjudicator = _safe_dict(data.get("ai_adjudicator"))
    final_decision = _safe_dict(data.get("final_decision"))
    bitrix = _safe_dict(data.get("bitrix"))
    action_draft = _safe_dict(data.get("action_draft"))
    attachments = _safe_list(data.get("attachments"))
    evidence_links = _safe_list(data.get("evidence_links"))

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
            "title": t("Message body", lang),
            "items": _page_kv_items(
                [
                    _kv(t("Event ID", lang), event_id),
                    _kv(t("Sender", lang), message.get("sender")),
                    _kv(t("Subject", lang), message.get("subject")),
                    _kv(t("Date", lang), _format_iso_datetime(message.get("date"))),
                    _kv(
                        t("Body preview", lang),
                        message.get("body_preview"),
                        hint="long_text",
                    ),
                ]
            ),
        },
        {
            "kind": "key_value",
            "title": t("Classification", lang),
            "items": _page_kv_items(
                [
                    _kv(
                        t("Case type", lang),
                        classification.get("case_type"),
                        variant="badge",
                        tone="default",
                    ),
                    _kv(t("Subtype", lang), classification.get("case_subtype")),
                    _kv(
                        t("Priority", lang),
                        classification.get("priority"),
                        variant="badge",
                        tone=_priority_tone(classification.get("priority", "")),
                    ),
                    _kv(
                        t("Confidence", lang),
                        classification.get("confidence"),
                        hint="confidence",
                    ),
                    _kv(t("Reason code", lang), classification.get("reason_code")),
                    _kv(
                        t("Reason", lang),
                        classification.get("reason_display"),
                        hint="localized_reason",
                    ),
                    _kv(
                        t("Recommended queue", lang),
                        classification.get("recommended_queue"),
                        variant="badge",
                        tone=_queue_action_tone(
                            classification.get("recommended_queue", "")
                        ),
                    ),
                    _kv(
                        t("Recommended action", lang),
                        classification.get("correct_action"),
                        variant="badge",
                        tone=_queue_action_tone(
                            classification.get("correct_action", "")
                        ),
                    ),
                    _kv(
                        t("Should ROP see", lang),
                        _bool_display(classification.get("should_rop_see"), lang),
                        variant="badge",
                        tone="warning"
                        if classification.get("should_rop_see") is True
                        else "muted",
                    ),
                    *(
                        [
                            _kv(
                                t("Base case type", lang),
                                classification.get("base_case_type"),
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
                                t("Duplicate reason code", lang),
                                duplicate.get("reason_code"),
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
            "title": t("Thread context", lang),
            "no_data": not thread.get("available", False),
            "items": _page_kv_items(
                [
                    _kv(t("Thread ID", lang), thread.get("thread_id")),
                    _kv(t("Connection", lang), thread.get("thread_connection")),
                    _kv(
                        t("Reply/forward", lang),
                        _bool_display(thread.get("reply_or_forward"), lang),
                        variant="boolean",
                    ),
                ]
            ),
        },
        {
            "kind": "key_value",
            "title": t("AI Assist", lang),
            "no_data": ai_assist.get("ai_assist_status")
            in ("unavailable", "not_applied"),
            "items": _page_kv_items(
                [
                    _kv(t("AI status", lang), ai_assist.get("ai_assist_status")),
                    _kv(
                        t("AI used", lang),
                        _bool_display(ai_assist.get("ai_assist_used"), lang),
                        variant="boolean",
                    ),
                    _kv(
                        t("AI confidence", lang),
                        ai_assist.get("ai_assist_confidence"),
                        hint="confidence",
                    ),
                    _kv(t("Final type", lang), ai_assist.get("final_case_type")),
                    _kv(t("Final priority", lang), ai_assist.get("final_priority")),
                ]
            ),
        },
        {
            "kind": "key_value",
            "title": t("AI Adjudicator", lang),
            "no_data": not bool(ai_adjudicator),
            "items": _page_kv_items(
                [
                    _kv(
                        t("AI adjudicator used", lang),
                        _bool_display(ai_adjudicator.get("ai_adjudicator_used"), lang),
                        variant="badge",
                        tone="default"
                        if ai_adjudicator.get("ai_adjudicator_used") is True
                        else "muted",
                    ),
                    _kv(
                        t("AI adjudicator status", lang),
                        ai_adjudicator.get("ai_adjudicator_status"),
                        variant="badge",
                        tone=_adjudicator_status_tone(
                            ai_adjudicator.get("ai_adjudicator_status", "")
                        ),
                    ),
                    _kv(
                        t("AI adjudicator confidence", lang),
                        ai_adjudicator.get("ai_adjudicator_confidence"),
                        hint="confidence",
                    ),
                    _kv(
                        t("AI adjudicator reason", lang),
                        ai_adjudicator.get("ai_adjudicator_reason_display"),
                        hint="localized_reason",
                    ),
                    _kv(
                        t("Reasoning", lang),
                        ai_adjudicator.get("ai_adjudicator_reason"),
                        variant="long_text",
                        collapsible=True,
                        display=ai_adjudicator.get("ai_adjudicator_reason", ""),
                    ),
                    _kv(
                        t("AI proposed case type", lang),
                        ai_adjudicator.get("final_case_type"),
                        variant="badge",
                        tone="default",
                    ),
                    _kv(
                        t("AI proposed queue", lang),
                        ai_adjudicator.get("final_recommended_queue"),
                        variant="badge",
                        tone=_queue_action_tone(
                            ai_adjudicator.get("final_recommended_queue", "")
                        ),
                    ),
                    _kv(
                        t("AI proposed action", lang),
                        ai_adjudicator.get("final_correct_action"),
                        variant="badge",
                        tone=_queue_action_tone(
                            ai_adjudicator.get("final_correct_action", "")
                        ),
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
                        final_decision.get("final_case_type"),
                        variant="badge",
                        tone="default",
                    ),
                    _kv(
                        t("Final queue", lang),
                        final_decision.get("final_queue"),
                        variant="badge",
                        tone=_queue_action_tone(final_decision.get("final_queue", "")),
                    ),
                    _kv(
                        t("Final action", lang),
                        final_decision.get("final_action"),
                        variant="badge",
                        tone=_queue_action_tone(final_decision.get("final_action", "")),
                    ),
                    _kv(
                        t("Final confidence", lang),
                        final_decision.get("final_confidence"),
                        hint="confidence",
                    ),
                    _kv(
                        t("Decision source", lang),
                        final_decision.get("final_decision_source"),
                        variant="badge",
                        tone="muted",
                    ),
                    _kv(
                        t("Needs attention", lang),
                        _bool_display(final_decision.get("needs_attention"), lang),
                        variant="badge",
                        tone="warning"
                        if final_decision.get("needs_attention") is True
                        else "muted",
                    ),
                    *(
                        [
                            _kv(
                                t("Attention reason", lang),
                                final_decision.get("attention_reason_display"),
                                hint="localized_reason",
                            )
                        ]
                        if final_decision.get("needs_attention") is True
                        else []
                    ),
                    _kv(
                        t("Automation allowed", lang),
                        _bool_display(final_decision.get("automation_allowed"), lang),
                        variant="badge",
                        tone="success"
                        if final_decision.get("automation_allowed") is True
                        else "muted",
                    ),
                    _kv(
                        t("Bitrix write allowed", lang),
                        _bool_display(final_decision.get("bitrix_write_allowed"), lang),
                        variant="badge",
                        tone="success"
                        if final_decision.get("bitrix_write_allowed") is True
                        else "muted",
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
                    _kv(t("Bitrix status", lang), bitrix.get("bitrix_status")),
                    _kv(t("Match quality", lang), bitrix.get("match_quality")),
                    _kv(t("Candidate count", lang), bitrix.get("candidate_count")),
                    _kv(t("Entity type", lang), bitrix.get("entity_type")),
                    _kv(t("Entity ID", lang), bitrix.get("entity_id")),
                ]
            ),
        },
        {
            "kind": "key_value",
            "title": t("Action draft", lang),
            "no_data": not action_draft.get("available", False),
            "items": _page_kv_items(
                [
                    _kv(t("Action type", lang), action_draft.get("action_type")),
                    _kv(t("Summary", lang), action_draft.get("summary")),
                    _kv(t("Draft status", lang), action_draft.get("draft_status")),
                ]
            ),
        },
    ]

    attachment_rows = [
        {
            "filename": attachment.get("filename"),
            "content_type": attachment.get("content_type"),
            "size_bytes": _format_size(attachment.get("size_bytes")),
        }
        for attachment in attachments
        if isinstance(attachment, dict)
    ]
    if attachment_rows:
        sections.append(
            {
                "kind": "table",
                "title": t("Attachment Processing", lang),
                "columns": [
                    {"key": "filename", "label": t("Filename", lang)},
                    {"key": "content_type", "label": t("Content type", lang)},
                    {"key": "size_bytes", "label": t("Size", lang)},
                ],
                "rows": attachment_rows,
            }
        )

    link_items = [
        {
            "label": _str(link.get("artifact_id")),
            "href": _str(link.get("url")),
        }
        for link in evidence_links
        if isinstance(link, dict) and link.get("available") and link.get("url")
    ]
    if link_items:
        sections.append(
            {
                "kind": "links",
                "title": t("Evidence artifacts", lang),
                "items": link_items,
            }
        )

    # Sort: filled sections first, "not used" sections last
    sections.sort(key=lambda s: s.get("no_data", False))

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
