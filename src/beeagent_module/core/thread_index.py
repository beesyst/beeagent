from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

THREAD_ID_PREFIX = "thr"


def _normalize_subject(subject: str) -> str:
    if not subject:
        return ""
    cleaned = re.sub(
        r"^(?:\s*(?:Re|Fwd|Fw|AW|WG|SV|Vs|ODP|回复|转发|回覆|Antw|Betr|enc|VB|RIF|RES|REF|RE|FW|FWD|Aw)\s*[:.\-]?\s*)+",
        "",
        subject,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", cleaned).strip().lower()


def _has_reply_prefix(subject: str) -> bool:
    if not subject:
        return False
    return bool(
        re.match(
            r"^\s*(?:Re|Fwd|Fw|AW|WG|SV|Vs|ODP|回复|转发|回覆|Antw|Betr|enc|VB|RIF|RES|REF)\s*[:.\-]",
            subject,
            flags=re.IGNORECASE,
        )
    )


def _extract_message_ids(
    event: dict[str, Any],
) -> tuple[str, list[str], list[str]]:
    message_id = event.get("message_id") or event.get("Message-ID") or ""
    in_reply_to_raw = event.get("in_reply_to") or event.get("In-Reply-To") or ""
    references_raw = event.get("references") or event.get("References") or ""
    if not isinstance(message_id, str):
        message_id = ""
    if not isinstance(in_reply_to_raw, str):
        in_reply_to_raw = ""
    if not isinstance(references_raw, str):
        references_raw = ""

    in_reply_to = [
        x.strip() for x in in_reply_to_raw.replace(",", " ").split() if x.strip()
    ]
    references = [
        x.strip() for x in references_raw.replace(",", " ").split() if x.strip()
    ]

    return message_id, in_reply_to, references


def _normalized_subject_key(event: dict[str, Any]) -> str:
    subject = event.get("subject") or ""
    return _normalize_subject(subject)


def _thread_scope_key(event: dict[str, Any]) -> tuple[str, str]:
    source_id = str(event.get("source_id") or event.get("source") or "")
    client_id = str(event.get("client_id") or "")
    return source_id, client_id


def _participants(event: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    sender = event.get("sender") or ""
    if sender:
        result.add(sender.lower())
    for field in ("to", "cc"):
        raw = event.get(field)
        if isinstance(raw, list):
            for addr in raw:
                if isinstance(addr, str) and addr:
                    result.add(addr.lower())
        elif isinstance(raw, str) and raw:
            result.add(raw.lower())
    return result


def build_thread_index(
    events: list[dict[str, Any]],
    logger: logging.Logger,
) -> dict[str, Any]:
    threads: list[dict[str, Any]] = []
    warnings: list[str] = []

    mid_to_thread: dict[str, int] = {}
    ref_to_thread: dict[str, list[int]] = {}
    subject_threads: dict[tuple[str, str, str], list[int]] = {}
    thread_data: list[dict[str, Any]] = []

    for idx, event in enumerate(events):
        message_id, in_reply_to, references = _extract_message_ids(event)
        norm_subject = _normalized_subject_key(event)

        matched_thread: int | None = None
        evidence: dict[str, bool] = {
            "message_id_link": False,
            "references_link": False,
            "subject_fallback": False,
        }

        if message_id and message_id in mid_to_thread:
            matched_thread = mid_to_thread[message_id]
            evidence["message_id_link"] = True

        if matched_thread is None:
            for ref_id in [*in_reply_to, *references]:
                if ref_id in mid_to_thread:
                    matched_thread = mid_to_thread[ref_id]
                    evidence["references_link"] = True
                    break

        if matched_thread is None:
            for ref_id in [*in_reply_to, *references]:
                candidates = ref_to_thread.get(ref_id, [])
                if candidates:
                    matched_thread = candidates[0]
                    evidence["references_link"] = True
                    break

        if matched_thread is None:
            reply_prefix = _has_reply_prefix(event.get("subject") or "")
            if reply_prefix and norm_subject:
                source_scope, client_scope = _thread_scope_key(event)
                subject_key = (source_scope, client_scope, norm_subject)
                candidates = subject_threads.get(subject_key, [])
                if candidates:
                    matched_thread = candidates[-1]
                    evidence["subject_fallback"] = True

        if matched_thread is None:
            thread_id = f"{THREAD_ID_PREFIX}_{len(thread_data) + 1:03d}"
            thread_entry: dict[str, Any] = {
                "thread_id": thread_id,
                "source_ids": [],
                "event_ids": [],
                "message_ids": [],
                "subject_normalized": norm_subject,
                "participants": set(),
                "latest_event_id": "",
                "latest_at": None,
                "evidence": evidence,
            }
            thread_data.append(thread_entry)
            matched_thread = len(thread_data) - 1

        thread = thread_data[matched_thread]

        source_id = event.get("source_id") or event.get("source", "")
        if source_id and source_id not in thread["source_ids"]:
            thread["source_ids"].append(source_id)

        event_id = event.get("event_id") or ""
        if event_id and event_id not in thread["event_ids"]:
            thread["event_ids"].append(event_id)

        if message_id and message_id not in thread["message_ids"]:
            thread["message_ids"].append(message_id)

        if norm_subject and not thread["subject_normalized"]:
            thread["subject_normalized"] = norm_subject

        evt_participants = _participants(event)
        thread["participants"].update(evt_participants)

        thread["latest_event_id"] = event_id

        event_date = event.get("date") or event.get("received_at") or ""
        if isinstance(event_date, str) and event_date:
            if (thread["latest_at"] is None) or (event_date > thread["latest_at"]):
                thread["latest_at"] = event_date

        if message_id:
            mid_to_thread[message_id] = matched_thread
            for ref_id in [*in_reply_to, *references]:
                if ref_id:
                    if ref_id not in ref_to_thread:
                        ref_to_thread[ref_id] = []
                    if matched_thread not in ref_to_thread[ref_id]:
                        ref_to_thread[ref_id].append(matched_thread)

        if matched_thread is not None and norm_subject:
            source_scope, client_scope = _thread_scope_key(event)
            subject_key = (source_scope, client_scope, norm_subject)
            if subject_key not in subject_threads:
                subject_threads[subject_key] = []
            if matched_thread not in subject_threads[subject_key]:
                subject_threads[subject_key].append(matched_thread)

        thread["evidence"]["message_id_link"] = (
            thread["evidence"]["message_id_link"] or evidence["message_id_link"]
        )
        thread["evidence"]["references_link"] = (
            thread["evidence"]["references_link"] or evidence["references_link"]
        )
        thread["evidence"]["subject_fallback"] = (
            thread["evidence"]["subject_fallback"] or evidence["subject_fallback"]
        )

        if (
            not thread["evidence"]["message_id_link"]
            and not thread["evidence"]["references_link"]
        ):
            if not _has_reply_prefix(event.get("subject") or ""):
                thread["evidence"]["subject_fallback"] = False

    result_threads: list[dict[str, Any]] = []
    for t in thread_data:
        t["participants"] = sorted(t["participants"])
        result_threads.append(t)

    if not result_threads:
        for idx, event in enumerate(events):
            tid = f"{THREAD_ID_PREFIX}_{idx + 1:03d}"
            event_id = event.get("event_id") or ""
            result_threads.append(
                {
                    "thread_id": tid,
                    "source_ids": [event.get("source_id") or event.get("source", "")],
                    "event_ids": [event_id] if event_id else [],
                    "message_ids": [event.get("message_id") or ""]
                    if event.get("message_id")
                    else [],
                    "subject_normalized": _normalized_subject_key(event),
                    "participants": sorted(_participants(event)),
                    "latest_event_id": event_id,
                    "latest_at": event.get("date") or event.get("received_at"),
                    "evidence": {
                        "message_id_link": False,
                        "references_link": False,
                        "subject_fallback": False,
                    },
                }
            )

    for t in result_threads:
        if t["latest_at"] is None:
            t["latest_at"] = None

    if warnings:
        logger.warning("thread index warnings: %s", "; ".join(warnings))

    return {
        "threads": result_threads,
        "warnings": warnings,
    }


def build_thread_context(
    events: list[dict[str, Any]],
    thread_index: dict[str, Any],
    classified_events: list[dict[str, Any]] | None,
    logger: logging.Logger,
) -> dict[str, Any]:
    threads = thread_index.get("threads", [])
    if not isinstance(threads, list):
        threads = []

    event_to_thread: dict[str, dict[str, Any]] = {}
    for thread in threads:
        for eid in thread.get("event_ids", []):
            if isinstance(eid, str):
                event_to_thread[eid] = thread

    classified_by_event: dict[str, dict[str, Any]] = {}
    if classified_events:
        for ce in classified_events:
            if isinstance(ce, dict):
                eid = ce.get("event_id") or ""
                if eid:
                    classified_by_event[eid] = ce

    contexts: list[dict[str, Any]] = []
    warnings: list[str] = []

    prior_event_ids: list[str] = []
    for event_position, event in enumerate(events):
        event_id = event.get("event_id") or ""
        if not event_id:
            continue

        thread = event_to_thread.get(event_id)
        if thread is None:
            continue

        previous_ids = [
            prior_event_id
            for prior_event_id in prior_event_ids
            if prior_event_id != event_id
            and event_to_thread.get(prior_event_id) is thread
        ]
        if not previous_ids:
            prior_event_ids.append(event_id)
            continue

        previous_classified: dict[str, Any] | None = None
        for pid in reversed(previous_ids):
            if pid in classified_by_event:
                previous_classified = classified_by_event[pid]
                break

        is_reply = False
        if event.get("in_reply_to") or event.get("In-Reply-To"):
            is_reply = True
        if not is_reply and _has_reply_prefix(event.get("subject") or ""):
            is_reply = True

        prev_case_type = ""
        prev_case_subtype = ""
        if previous_classified:
            prev_case_type = previous_classified.get("case_type", "")
            prev_case_subtype = previous_classified.get("case_subtype", "")

        previous_events = [
            previous_event
            for previous_event in events[:event_position]
            if event_to_thread.get(previous_event.get("event_id") or "") is thread
        ]

        evt_participants = _participants(event)
        prior_participants: set[str] = set()
        prior_message_ids: set[str] = set()
        prior_link_ids: set[str] = set()

        for previous_event in previous_events:
            prior_participants.update(_participants(previous_event))
            (
                previous_message_id,
                previous_in_reply_to,
                previous_references,
            ) = _extract_message_ids(previous_event)

            if previous_message_id:
                prior_message_ids.add(previous_message_id)
                prior_link_ids.add(previous_message_id)

            prior_link_ids.update(previous_in_reply_to)
            prior_link_ids.update(previous_references)

        current_message_id, current_in_reply_to, current_references = (
            _extract_message_ids(event)
        )
        current_reference_ids = {*current_in_reply_to, *current_references}
        current_subject_key = _normalized_subject_key(event)

        local_evidence = {
            "message_id_link": bool(
                current_message_id and current_message_id in prior_message_ids
            ),
            "references_link": bool(current_reference_ids & prior_link_ids),
            "subject_fallback": bool(
                _has_reply_prefix(event.get("subject") or "")
                and current_subject_key
                and any(
                    _normalized_subject_key(previous_event) == current_subject_key
                    for previous_event in previous_events
                )
            ),
        }

        participant_overlap = bool(evt_participants & prior_participants)

        reason_codes: list[str] = []
        if local_evidence["message_id_link"]:
            reason_codes.append("message_id_chain")
        if local_evidence["references_link"]:
            reason_codes.append("references_chain")
        if local_evidence["subject_fallback"]:
            reason_codes.append("subject_match")
        if is_reply:
            reason_codes.append("reply_or_forward")
        if prev_case_type:
            reason_codes.append(f"previous_{prev_case_type}")
        if prev_case_subtype:
            reason_codes.append(f"previous_{prev_case_subtype}")

        context_entry: dict[str, Any] = {
            "event_id": event_id,
            "thread_id": thread.get("thread_id", ""),
            "reply_or_forward": is_reply,
            "previous_event_ids": previous_ids,
            "previous_case_type": prev_case_type,
            "previous_case_subtype": prev_case_subtype,
            "participant_overlap": participant_overlap,
            "previous_subject": "",
            "previous_summary": "",
            "thread_context_confidence": _compute_confidence(
                evidence=local_evidence,
                is_reply=is_reply,
                prev_case_type=prev_case_type,
            ),
            "reason_codes": reason_codes,
        }

        if previous_classified:
            prev_subject_raw = previous_classified.get("subject") or ""
            context_entry["previous_subject"] = prev_subject_raw[:200]
            prev_reasoning = previous_classified.get("reasoning") or ""
            context_entry["previous_summary"] = prev_reasoning[:300]

        contexts.append(context_entry)
        prior_event_ids.append(event_id)

    return {
        "contexts": contexts,
        "warnings": warnings,
    }


def _compute_confidence(
    evidence: dict[str, bool],
    is_reply: bool,
    prev_case_type: str,
) -> float:
    score = 0.0

    if evidence.get("message_id_link"):
        score += 0.50
    if evidence.get("references_link"):
        score += 0.30
    if is_reply:
        score += 0.20
    if evidence.get("subject_fallback"):
        score += 0.10
    if prev_case_type:
        score += 0.15

    return min(round(score, 2), 0.95)


def write_thread_artifacts(
    storage_dir: Path,
    run_id: str,
    thread_index: dict[str, Any],
    thread_context: dict[str, Any],
    logger: logging.Logger,
) -> list[str]:
    run_dir = storage_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    refs: list[str] = []

    index_path = run_dir / "mail_thread_index.json"
    index_artifact = {
        "run_id": run_id,
        "threads": thread_index.get("threads", []),
        "warnings": thread_index.get("warnings", []),
    }
    index_path.write_text(
        json.dumps(index_artifact, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    refs.append(str(index_path.relative_to(storage_dir)))
    logger.info(
        "mail_thread_index written: run_id=%s threads=%d",
        run_id,
        len(thread_index.get("threads", [])),
    )

    context_path = run_dir / "mail_thread_context.json"
    context_artifact = {
        "run_id": run_id,
        "contexts": thread_context.get("contexts", []),
        "warnings": thread_context.get("warnings", []),
    }
    context_path.write_text(
        json.dumps(context_artifact, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    refs.append(str(context_path.relative_to(storage_dir)))
    logger.info(
        "mail_thread_context written: run_id=%s contexts=%d",
        run_id,
        len(thread_context.get("contexts", [])),
    )

    return refs
