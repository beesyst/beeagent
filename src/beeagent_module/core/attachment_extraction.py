from __future__ import annotations

from typing import Any

_BLOCKED_EMAIL_CONTENT_TYPE = "message/rfc822"


def build_attachment_extraction(
    run_id: str,
    events: list[dict[str, Any]],
    attachment_settings: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    enabled = bool(attachment_settings["enabled"])
    preview_chars_max = int(attachment_settings["chars_max"])
    size_max_bytes = int(attachment_settings["size_max"])
    allowed_types = {
        str(item).strip().lower()
        for item in attachment_settings["types"]
        if isinstance(item, str) and item.strip()
    }

    if not enabled:
        artifact = {
            "run_id": run_id,
            "status": "disabled",
            "aggregate": {
                "event_count": len(events),
                "attachment_count": 0,
                "preview_available_count": 0,
                "metadata_only_count": 0,
                "refused_count": 0,
                "unsupported_count": 0,
                "failed_count": 0,
            },
            "items": [],
        }
        return artifact, list(events)

    items: list[dict[str, Any]] = []
    enriched_events: list[dict[str, Any]] = []

    for event in events:
        enriched_event, event_items = _extract_event_attachments(
            event=event,
            preview_chars_max=preview_chars_max,
            size_max_bytes=size_max_bytes,
            allowed_types=allowed_types,
        )
        enriched_events.append(enriched_event)
        items.extend(event_items)

    aggregate = {
        "event_count": len(events),
        "attachment_count": len(items),
        "preview_available_count": sum(
            1 for item in items if item["preview_available"]
        ),
        "metadata_only_count": sum(
            1 for item in items if item["extraction_status"] == "metadata_only"
        ),
        "refused_count": sum(
            1 for item in items if item["extraction_status"] == "refused"
        ),
        "unsupported_count": sum(
            1 for item in items if item["extraction_status"] == "unsupported"
        ),
        "failed_count": sum(
            1 for item in items if item["extraction_status"] == "failed"
        ),
    }

    artifact = {
        "run_id": run_id,
        "status": "ok" if aggregate["failed_count"] == 0 else "degraded",
        "aggregate": aggregate,
        "items": items,
    }
    return artifact, enriched_events


def _extract_event_attachments(
    event: dict[str, Any],
    preview_chars_max: int,
    size_max_bytes: int,
    allowed_types: set[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    attachments = event.get("attachments")
    if not isinstance(attachments, list):
        attachments = []

    if not attachments:
        return dict(event), []

    event_id = _as_text(event.get("event_id"))

    event_items: list[dict[str, Any]] = []
    previews: list[str] = []
    refusal_reasons: list[str] = []

    for index, attachment in enumerate(attachments):
        item = _extract_attachment_item(
            event=event,
            attachment=attachment,
            attachment_id=f"{event_id or 'event'}-att-{index}",
            preview_chars_max=preview_chars_max,
            size_max_bytes=size_max_bytes,
            allowed_types=allowed_types,
        )
        event_items.append(item)

        if item["preview_available"] and item["text_preview"]:
            previews.append(item["text_preview"])
        if item["is_refused"] and item["reason_code"]:
            refusal_reasons.append(item["reason_code"])

    status = _resolve_event_status(event_items)

    merged_preview = "\n\n".join(previews)
    merged_preview = _sanitize_text(merged_preview)
    merged_preview = merged_preview[:preview_chars_max]

    enriched = dict(event)
    enriched["attachments"] = [
        item
        for item in attachments
        if isinstance(item, dict)
        and not _is_blocked_email_attachment(
            filename=_as_text(item.get("filename")),
            content_type=_as_text(item.get("content_type")),
        )
    ]
    enriched["attachment_extraction_status"] = status
    enriched["attachment_preview_available"] = bool(previews)
    enriched["attachment_text_preview"] = merged_preview
    enriched["attachment_extraction_refs"] = [
        item["attachment_id"] for item in event_items
    ]
    enriched["attachment_refusal_reasons"] = sorted(set(refusal_reasons))

    if status == "preview" and not enriched.get("attachment_text"):
        enriched["attachment_text"] = merged_preview

    return enriched, event_items


def _extract_attachment_item(
    event: dict[str, Any],
    attachment: Any,
    attachment_id: str,
    preview_chars_max: int,
    size_max_bytes: int,
    allowed_types: set[str],
) -> dict[str, Any]:
    base = {
        "event_id": _as_text(event.get("event_id")),
        "event_instance_id": _as_text(event.get("event_instance_id")),
        "source_id": _as_text(event.get("source_id")),
        "source_type": _as_text(event.get("source_type")),
        "source_role": _as_text(event.get("source_role")),
        "source_display_name": _as_text(event.get("source_display_name")),
        "client_id": _as_text(event.get("client_id")),
        "attachment_id": attachment_id,
        "filename": "",
        "content_type": "",
        "size_bytes": None,
        "extraction_status": "failed",
        "preview_available": False,
        "text_preview": "",
        "preview_chars": 0,
        "is_supported": False,
        "is_refused": False,
        "is_truncated": False,
        "reason_code": "malformed_attachment_metadata",
        "refusal_reason": "attachment metadata is invalid",
    }

    if not isinstance(attachment, dict):
        return base

    filename = _as_text(attachment.get("filename"))
    content_type = _as_text(attachment.get("content_type"))
    normalized_content_type = content_type.lower()
    size_bytes = _to_int(attachment.get("size_bytes"))
    if size_bytes is None:
        size_bytes = _to_int(attachment.get("size"))

    base["filename"] = filename
    base["content_type"] = content_type
    base["size_bytes"] = size_bytes

    if _is_blocked_email_attachment(
        filename=filename, content_type=normalized_content_type
    ):
        base.update(
            {
                "extraction_status": "refused",
                "is_refused": True,
                "reason_code": "blocked_email_attachment",
                "refusal_reason": "email attachments are blocked",
            }
        )
        return base

    if size_bytes is not None and size_bytes > size_max_bytes:
        base.update(
            {
                "extraction_status": "refused",
                "is_refused": True,
                "reason_code": "attachment_oversized",
                "refusal_reason": "attachment exceeds size limit",
            }
        )
        return base

    if normalized_content_type not in allowed_types:
        base.update(
            {
                "extraction_status": "unsupported",
                "reason_code": "unsupported_content_type",
                "refusal_reason": None,
            }
        )
        return base

    base["is_supported"] = True

    safe_preview = _extract_safe_preview(attachment)
    if not safe_preview:
        base.update(
            {
                "extraction_status": "metadata_only",
                "reason_code": "metadata_only_no_safe_text",
                "refusal_reason": None,
            }
        )
        return base

    is_truncated = len(safe_preview) > preview_chars_max
    bounded_preview = safe_preview[:preview_chars_max]
    base.update(
        {
            "extraction_status": "preview",
            "preview_available": True,
            "text_preview": bounded_preview,
            "preview_chars": len(bounded_preview),
            "is_truncated": is_truncated,
            "reason_code": "text_preview_extracted",
            "refusal_reason": None,
        }
    )
    return base


def _extract_safe_preview(attachment: dict[str, Any]) -> str:
    for key in ("text_preview", "text", "body_preview", "attachment_text"):
        value = attachment.get(key)
        if isinstance(value, str) and value.strip():
            return _sanitize_text(value)
    return ""


def _resolve_event_status(event_items: list[dict[str, Any]]) -> str:
    if not event_items:
        return "none"
    statuses = {item.get("extraction_status") for item in event_items}
    if "failed" in statuses:
        return "failed"
    if "refused" in statuses:
        return "refused"
    if "preview" in statuses:
        return "preview"
    if statuses == {"unsupported"}:
        return "unsupported"
    if "metadata_only" in statuses:
        return "metadata_only"
    return "none"


def _is_blocked_email_attachment(filename: str, content_type: str) -> bool:
    normalized_filename = filename.strip().lower()
    normalized_content_type = content_type.strip().lower()
    return (
        normalized_filename.endswith(".eml")
        or normalized_content_type == _BLOCKED_EMAIL_CONTENT_TYPE
    )


def _to_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return _sanitize_text(str(value))


def _sanitize_text(value: str) -> str:
    return " ".join(
        value.replace("\t", " ").replace("\n", " ").replace("\r", " ").split()
    )
