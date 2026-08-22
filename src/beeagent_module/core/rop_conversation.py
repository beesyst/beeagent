from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from beeagent_module.core.thread_index import _extract_message_ids

CONVERSATION_ID_PREFIX = "conv"
_MAX_TIMELINE_ITEMS = 60
_MAX_CONVERSATION_EVENTS = 100


def _bounded_text(value: Any, max_length: int) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:max_length]


def _safe_list(value: Any) -> list:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _safe_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _event_role(
    event: dict[str, Any],
    thread_has_prior: bool,
) -> str:
    _message_id, in_reply_to, references = _extract_message_ids(event)
    if in_reply_to or references:
        return "reply"
    if thread_has_prior:
        return "continuation"
    return "root"


def build_conversation_relation(
    events: list[dict[str, Any]],
    thread_index: dict[str, Any],
    classified_events: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    threads = thread_index.get("threads", [])
    if not isinstance(threads, list):
        threads = []

    event_position: dict[str, int] = {}
    for index, event in enumerate(events):
        eid = event.get("event_id")
        if isinstance(eid, str) and eid:
            event_position[eid] = index

    classified_by_event: dict[str, dict[str, Any]] = {}
    if classified_events:
        for ce in classified_events:
            if isinstance(ce, dict):
                eid = ce.get("event_id")
                if isinstance(eid, str) and eid:
                    classified_by_event[eid] = ce

    conversations: list[dict[str, Any]] = []
    for thread_index_id, thread in enumerate(threads, start=1):
        thread_event_ids = [eid for eid in _safe_strings(thread.get("event_ids"))]
        thread_events: list[dict[str, Any]] = []
        ordered_ids = sorted(
            thread_event_ids,
            key=lambda eid: (event_position.get(eid, 0), eid),
        )
        prior_seen = False
        for eid in ordered_ids:
            event = None
            for candidate in events:
                if isinstance(candidate, dict) and candidate.get("event_id") == eid:
                    event = candidate
                    break
            if event is None:
                continue
            classified = classified_by_event.get(eid, {})
            thread_events.append(
                {
                    "event_id": eid,
                    "event_instance_id": _bounded_text(
                        event.get("event_instance_id"), 80
                    ),
                    "source_id": _bounded_text(event.get("source_id"), 200),
                    "role": _event_role(event, prior_seen),
                    "message_id": _bounded_text(event.get("message_id"), 320),
                    "subject": _bounded_text(event.get("subject"), 200),
                    "sender": _bounded_text(event.get("sender"), 320),
                    "date": _bounded_text(
                        event.get("received_at")
                        or event.get("date")
                        or event.get("event_date"),
                        200,
                    ),
                    "case_type": _bounded_text(classified.get("case_type"), 80),
                }
            )
            prior_seen = True

        source_ids = _safe_strings(thread.get("source_ids"))
        message_ids = _safe_strings(thread.get("message_ids"))
        client_id = ""
        for eid in thread_event_ids:
            for event in events:
                if isinstance(event, dict) and event.get("event_id") == eid:
                    candidate = event.get("client_id")
                    if isinstance(candidate, str) and candidate:
                        client_id = candidate
                        break
            if client_id:
                break

        root_message_id = ""
        for message_id in message_ids:
            if message_id:
                root_message_id = message_id
                break

        conversations.append(
            {
                "conversation_id": f"{CONVERSATION_ID_PREFIX}_{thread_index_id:03d}",
                "thread_id": _bounded_text(thread.get("thread_id"), 200),
                "client_id": client_id,
                "source_ids": source_ids[:_MAX_CONVERSATION_EVENTS],
                "message_ids": message_ids[:_MAX_CONVERSATION_EVENTS],
                "root_message_id": root_message_id,
                "events": thread_events[:_MAX_CONVERSATION_EVENTS],
            }
        )

    return {
        "conversations": conversations,
    }


def build_event_conversation_context(
    relation: dict[str, Any] | None,
    event_id: str,
) -> dict[str, Any] | None:
    if not isinstance(relation, dict):
        return None
    conversations = relation.get("conversations")
    if not isinstance(conversations, list):
        return None
    for conversation in conversations:
        if not isinstance(conversation, dict):
            continue
        events = conversation.get("events")
        if not isinstance(events, list):
            continue
        if not any(
            isinstance(e, dict) and e.get("event_id") == event_id for e in events
        ):
            continue
        other_events: list[dict[str, Any]] = []
        for e in events:
            if not isinstance(e, dict) or e.get("event_id") == event_id:
                continue
            entry: dict[str, Any] = {}
            for key, limit in (
                ("event_id", 120),
                ("role", 80),
                ("case_type", 80),
            ):
                value = _bounded_text(e.get(key), limit)
                if value:
                    entry[key] = value
            subject = _bounded_text(e.get("subject"), 120)
            if subject:
                entry["subject"] = subject
            sender = _bounded_text(e.get("sender"), 160)
            if sender:
                entry["sender"] = sender
            if entry:
                other_events.append(entry)
            if len(other_events) >= 8:
                break
        result: dict[str, Any] = {
            "conversation_id": _bounded_text(conversation.get("conversation_id"), 120),
            "message_count": len(events),
        }
        if other_events:
            result["other_events"] = other_events
        return result
    return None


def _read_writeback_state(storage_dir: Path) -> dict[str, Any]:
    path = storage_dir / "interfaces" / "rop_writeback_state.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError, TypeError:
        return {}
    if not isinstance(data, dict):
        return {}
    events = data.get("events")
    if not isinstance(events, dict):
        return {}
    return {key: value for key, value in events.items() if isinstance(value, dict)}


def _record_identity_matches(
    record: dict[str, Any],
    event_id: str,
    event_instance_id: str,
) -> bool:
    if record.get("event_id") != event_id:
        return False
    if event_instance_id and record.get("event_instance_id") != event_instance_id:
        return False
    return True


def _find_seed_record(
    records: list[dict[str, Any]],
    event_id: str,
    event_instance_id: str,
    message_id: str,
) -> dict[str, Any] | None:
    for record in records:
        if _record_identity_matches(record, event_id, event_instance_id):
            return record
    if message_id:
        for record in records:
            if record.get("message_id") == message_id:
                return record
    return None


def _extract_record_refs(record: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for header in ("in_reply_to", "references"):
        value = record.get(header)
        if not isinstance(value, str) or not value.strip():
            continue
        for token in value.replace(",", " ").split():
            token = token.strip()
            if token and token not in refs:
                refs.append(token)
    return refs


def _record_role(record: dict[str, Any]) -> str:
    if _extract_record_refs(record):
        return "reply"
    return "root"


def _writeback_outcome_summary(record: dict[str, Any]) -> dict[str, Any]:
    target_id = record.get("target_entity_id")
    if isinstance(target_id, bool) or not isinstance(target_id, int):
        target_id = None
    return {
        "outcome": _bounded_text(record.get("outcome"), 80),
        "status": _bounded_text(record.get("status"), 80),
        "reason_code": _bounded_text(record.get("reason_code"), 120),
        "target_entity_type": _bounded_text(record.get("target_entity_type"), 80),
        "target_entity_id": target_id,
        "target_provenance": _bounded_text(record.get("target_provenance"), 120),
    }


def _collect_conversation_records(
    records: list[dict[str, Any]],
    seed: dict[str, Any],
    client_id: str,
) -> list[dict[str, Any]]:
    client_records = [
        record
        for record in records
        if record.get("client_id") == client_id
        and (record.get("message_id") or _extract_record_refs(record))
    ]
    if not client_records:
        return []

    by_message_id: dict[str, list[int]] = {}
    by_ref: dict[str, list[int]] = {}
    for index, record in enumerate(client_records):
        message_id = record.get("message_id")
        if isinstance(message_id, str) and message_id:
            by_message_id.setdefault(message_id, []).append(index)
        for ref_id in _extract_record_refs(record):
            by_ref.setdefault(ref_id, []).append(index)

    seed_ids: set[str] = set()
    seed_message_id = seed.get("message_id")
    if isinstance(seed_message_id, str) and seed_message_id:
        seed_ids.add(seed_message_id)
    seed_ids.update(_extract_record_refs(seed))

    visited: set[int] = set()
    frontier: set[str] = set(seed_ids)
    while frontier:
        current_frontier: set[str] = set()
        for ref_id in frontier:
            for index in by_message_id.get(ref_id, []):
                if index in visited:
                    continue
                visited.add(index)
                record = client_records[index]
                current_frontier.update(_extract_record_refs(record))
                message_id = record.get("message_id")
                if isinstance(message_id, str) and message_id:
                    current_frontier.add(message_id)
            for index in by_ref.get(ref_id, []):
                if index in visited:
                    continue
                visited.add(index)
                record = client_records[index]
                current_frontier.update(_extract_record_refs(record))
                message_id = record.get("message_id")
                if isinstance(message_id, str) and message_id:
                    current_frontier.add(message_id)
        frontier = current_frontier

    result = [client_records[index] for index in sorted(visited)]
    if not result:
        result = [seed]
    return result


def build_conversation_timeline(
    storage_dir: Path,
    run_id: str,
    event_id: str,
    event_instance_id: str | None = None,
) -> dict[str, Any]:
    records = list(_read_writeback_state(storage_dir).values())
    message_id = ""
    runs_root = (storage_dir / "runs").resolve()
    run_dir = (runs_root / run_id).resolve()
    if not run_dir.is_relative_to(runs_root):
        return {
            "available": False,
            "message": "invalid run_id",
            "events": [],
        }
    normalized_path = run_dir / "normalized_events.json"
    if normalized_path.exists():
        try:
            normalized = json.loads(normalized_path.read_text(encoding="utf-8"))
        except OSError, json.JSONDecodeError, TypeError:
            normalized = []
        if isinstance(normalized, list):
            for event in normalized:
                if not isinstance(event, dict):
                    continue
                if event.get("event_id") == event_id and (
                    event_instance_id is None
                    or event.get("event_instance_id") == event_instance_id
                ):
                    candidate = event.get("message_id")
                    if isinstance(candidate, str):
                        message_id = candidate
                    break

    seed = _find_seed_record(records, event_id, event_instance_id or "", message_id)
    if seed is None:
        return {
            "available": False,
            "message": "no conversation records",
            "events": [],
        }

    client_id = _bounded_text(seed.get("client_id"), 200)
    conversation_records = _collect_conversation_records(records, seed, client_id)

    def _sort_key(record: dict[str, Any]) -> tuple[int, str, str, str]:
        date_value = record.get("created_at_utc") or record.get("updated_at_utc") or ""
        return (
            0 if isinstance(date_value, str) and date_value else 1,
            str(date_value),
            _bounded_text(record.get("source_id"), 200),
            _bounded_text(record.get("event_id"), 200),
        )

    ordered = sorted(conversation_records, key=_sort_key)
    timeline: list[dict[str, Any]] = []
    for record in ordered[:_MAX_TIMELINE_ITEMS]:
        timeline.append(
            {
                "run_id": _bounded_text(record.get("last_run_id"), 200),
                "source_id": _bounded_text(record.get("source_id"), 200),
                "event_id": _bounded_text(record.get("event_id"), 200),
                "event_instance_id": _bounded_text(record.get("event_instance_id"), 80),
                "message_id": _bounded_text(record.get("message_id"), 320),
                "role": _record_role(record),
                "subject": _bounded_text(record.get("subject"), 200),
                "sender": _bounded_text(
                    record.get("sender_email") or record.get("sender"), 320
                ),
                "case_type": _bounded_text(record.get("case_type"), 80),
                "semantic_case_type": _bounded_text(
                    record.get("semantic_case_type"), 80
                ),
                "date": _bounded_text(
                    record.get("created_at_utc") or record.get("updated_at_utc"),
                    200,
                ),
                "writeback": _writeback_outcome_summary(record),
            }
        )

    return {
        "available": True,
        "client_id": client_id,
        "message_count": len(timeline),
        "events": timeline,
    }


def write_conversation_artifacts(
    storage_dir: Path,
    run_id: str,
    relation: dict[str, Any],
    logger: logging.Logger,
) -> list[str]:
    run_dir = storage_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    path = run_dir / "rop_conversation.json"
    artifact = {
        "run_id": run_id,
        "conversations": relation.get("conversations", []),
    }
    path.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(
        "rop_conversation written: run_id=%s conversations=%d",
        run_id,
        len(artifact["conversations"]),
    )
    return [str(path.relative_to(storage_dir))]
