from __future__ import annotations

from typing import Any

_PUBLIC_THREAD_CONTEXT_KEYS = frozenset(
    {
        "thread_id",
        "previous_event_id",
        "reply_markers",
        "forward_markers",
        "previous_case_type",
        "participant_hints",
        "previous_subject",
        "previous_summary",
        "crm_deal_hint_summary",
        "thread_confidence",
        "reason_codes",
    }
)
_PUBLIC_THREAD_REASON_CODES = frozenset(
    {
        "reply_chain",
        "forward_only",
        "previous_existing_deal",
        "participant_overlap",
        "weak_continuation",
        "thread_id_present",
        "sender_subject_match",
    }
)


def build_public_thread_context(
    context: dict[str, Any],
    event: dict[str, Any],
) -> dict[str, Any]:
    previous_ids = context.get("previous_event_ids")
    previous_event_id = ""
    if isinstance(previous_ids, list):
        for item in reversed(previous_ids):
            if isinstance(item, str) and item:
                previous_event_id = item[:200]
                break

    thread_id = _bounded_text(context.get("thread_id"), 200)
    previous_case_type = _bounded_text(context.get("previous_case_type"), 200)
    reply_markers = bool(context.get("reply_or_forward")) and not bool(
        event.get("forwarded_wrapper")
    )
    transport_labels = _strings(event.get("transport_labels"))
    forward_markers = bool(event.get("forwarded_wrapper")) or bool(
        {"auto_fwd", "fwd"}.intersection(transport_labels)
    )
    reason_codes: list[str] = []
    if reply_markers:
        reason_codes.append("reply_chain")
    if forward_markers and not reply_markers:
        reason_codes.append("forward_only")
    if previous_case_type == "existing_deal":
        reason_codes.append("previous_existing_deal")
    if context.get("participant_overlap") is True:
        reason_codes.append("participant_overlap")
    if "subject_match" in _strings(context.get("reason_codes")):
        reason_codes.append("weak_continuation")
    if "sender_subject_match" in _strings(context.get("reason_codes")):
        reason_codes.append("sender_subject_match")
    if thread_id:
        reason_codes.append("thread_id_present")

    confidence = context.get("thread_context_confidence", 0.0)
    if isinstance(confidence, bool) or not isinstance(confidence, int | float):
        confidence = 0.0

    payload = {
        "thread_id": thread_id,
        "previous_event_id": previous_event_id,
        "reply_markers": reply_markers,
        "forward_markers": forward_markers,
        "previous_case_type": previous_case_type,
        "participant_hints": (
            "participant_overlap" if context.get("participant_overlap") is True else ""
        ),
        "previous_subject": _bounded_text(context.get("previous_subject"), 500),
        "previous_summary": _bounded_text(context.get("previous_summary"), 1000),
        "crm_deal_hint_summary": "",
        "thread_confidence": min(max(float(confidence), 0.0), 1.0),
        "reason_codes": [
            code for code in reason_codes if code in _PUBLIC_THREAD_REASON_CODES
        ][:10],
    }
    return {key: payload[key] for key in _PUBLIC_THREAD_CONTEXT_KEYS}


def _bounded_text(value: Any, max_length: int) -> str:
    return value.strip()[:max_length] if isinstance(value, str) else ""


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]
