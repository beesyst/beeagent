from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

CONTEXT_ENRICHMENT_ARTIFACT = "rop_context_enrichment.json"


def build_context_enrichment(
    storage_dir: Path,
    run_id: str,
    logger: logging.Logger,
) -> dict[str, Any]:
    run_dir = _resolve_run_dir(storage_dir, run_id)

    normalized = _read_json_list(run_dir / "normalized_events.json")
    classified = _read_json_list(run_dir / "classified_events.json")
    bitrix_reconciliation = _read_json_dict(run_dir / "bitrix_reconciliation.json")
    thread_context = _read_json_dict(run_dir / "mail_thread_context.json")
    attachment_extraction = _read_json_dict(run_dir / "attachment_extraction.json")

    classified_lookup: dict[str, dict[str, Any]] = {}
    if isinstance(classified, list):
        for evt in classified:
            eid = evt.get("event_id", "")
            if eid:
                classified_lookup[eid] = evt

    bitrix_lookup: dict[str, dict[str, Any]] = {}
    if isinstance(bitrix_reconciliation, dict):
        for item in bitrix_reconciliation.get("items", []):
            eid = item.get("event_id", "")
            if eid:
                bitrix_lookup[eid] = item

    thread_map: dict[str, dict[str, Any]] = {}
    if isinstance(thread_context, dict):
        for ctx in thread_context.get("contexts", []):
            eid = ctx.get("event_id", "")
            if eid:
                thread_map[eid] = ctx

    enrichment_items: list[dict[str, Any]] = []
    aggregate = {
        "event_count": 0,
        "enriched_count": 0,
        "possible_existing_deal_count": 0,
        "manual_review_routed_count": 0,
        "ai_fallback_eligible_count": 0,
        "thread_context_available_count": 0,
    }

    if isinstance(normalized, list):
        aggregate["event_count"] = len(normalized)
        sender_history = _build_sender_history(normalized)

        for event in normalized:
            event_id = event.get("event_id", "")
            cls = classified_lookup.get(event_id, {})
            bitrix = bitrix_lookup.get(event_id, {})
            thread_ctx = thread_map.get(event_id)

            enrichment = _enrich_event(
                event=event,
                classified=cls,
                bitrix=bitrix,
                thread_ctx=thread_ctx,
                sender_history=sender_history,
                attachment_extraction=attachment_extraction,
            )

            if enrichment.get("enrichment_flags"):
                aggregate["enriched_count"] += 1

            if enrichment.get("possible_existing_deal"):
                aggregate["possible_existing_deal_count"] += 1

            if enrichment.get("delivery_routing") == "manual_review":
                aggregate["manual_review_routed_count"] += 1

            if enrichment.get("ai_fallback_eligible"):
                aggregate["ai_fallback_eligible_count"] += 1

            if enrichment.get("thread_context_available"):
                aggregate["thread_context_available_count"] += 1

            enrichment_items.append(enrichment)

    artifact = {
        "run_id": run_id,
        "status": "ok",
        "read_only": True,
        "aggregate": aggregate,
        "items": enrichment_items,
    }

    return artifact


def write_context_enrichment_artifact(
    storage_dir: Path,
    run_id: str,
    artifact: dict[str, Any],
    logger: logging.Logger,
) -> Path:
    run_dir = storage_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = run_dir / CONTEXT_ENRICHMENT_ARTIFACT
    artifact_path.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(
        "rop_context_enrichment written: run_id=%s path=%s",
        run_id,
        artifact_path.relative_to(storage_dir),
    )
    return artifact_path


def _resolve_run_dir(storage_dir: Path, run_id: str) -> Path:
    runs_root = (storage_dir / "runs").resolve()
    run_dir = (runs_root / run_id).resolve()
    try:
        run_dir.relative_to(runs_root)
    except ValueError:
        raise ValueError(f"Invalid run_id: path traversal detected for '{run_id}'")
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")
    return run_dir


def _read_json_list(path: Path) -> list[dict[str, Any]] | None:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else None
    except json.JSONDecodeError, OSError:
        pass
    return None


def _read_json_dict(path: Path) -> dict[str, Any] | None:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
    except json.JSONDecodeError, OSError:
        pass
    return None


def _build_sender_history(
    normalized: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    history: dict[str, dict[str, Any]] = {}
    for event in normalized:
        sender = (event.get("sender") or "").strip().lower()
        if not sender:
            continue
        if sender not in history:
            history[sender] = {
                "event_count": 0,
                "event_ids": [],
                "subjects": [],
                "source_ids": set(),
            }
        entry = history[sender]
        entry["event_count"] += 1
        entry["event_ids"].append(event.get("event_id", ""))
        subject = (event.get("subject") or "").strip()
        if subject:
            entry["subjects"].append(subject)
        source_id = (event.get("source_id") or "").strip()
        if source_id:
            entry["source_ids"].add(source_id)

    for sender, entry in history.items():
        entry["source_ids"] = sorted(entry["source_ids"])

    return history


def _enrich_event(
    event: dict[str, Any],
    classified: dict[str, Any],
    bitrix: dict[str, Any] | None,
    thread_ctx: dict[str, Any] | None,
    sender_history: dict[str, dict[str, Any]],
    attachment_extraction: dict[str, Any] | None,
) -> dict[str, Any]:
    event_id = event.get("event_id", "")
    sender = (event.get("sender") or "").strip().lower()
    sender_info = sender_history.get(sender, {})

    flags: list[str] = []
    has_thread = bool(thread_ctx)
    has_bitrix = bool(bitrix)
    bitrix_match_status = bitrix.get("bitrix_match_status", "") if bitrix else ""

    bot_case_type = classified.get("case_type", "")

    possible_existing_deal = False
    delivery_routing = "standard"
    ai_fallback_eligible = False

    if bot_case_type == "irrelevant" and has_thread and thread_ctx:
        prev_type = thread_ctx.get("previous_case_type", "")
        if prev_type in ("existing_deal", "follow_up"):
            possible_existing_deal = True
            flags.append("irrelevant_but_thread_indicates_existing_deal")

    if bot_case_type == "irrelevant" and has_bitrix:
        if bitrix_match_status.startswith("matched_"):
            possible_existing_deal = True
            flags.append("irrelevant_but_bitrix_match_found")

    if bot_case_type == "irrelevant" and sender_info.get("event_count", 0) > 1:
        possible_existing_deal = True
        flags.append("irrelevant_but_sender_has_multiple_events")

    if possible_existing_deal:
        delivery_routing = "manual_review"
        ai_fallback_eligible = True

    if classified.get("is_fallback"):
        delivery_routing = "manual_review"
        ai_fallback_eligible = True
        flags.append("classification_fallback")

    if bitrix_match_status in ("weak_match", "ambiguous", "duplicate_candidate"):
        delivery_routing = "manual_review"
        if not possible_existing_deal:
            flags.append("bitrix_uncertain_match")

    if bitrix_match_status == "connector_degraded":
        delivery_routing = "manual_review"
        flags.append("bitrix_connector_degraded")

    confidence = classified.get("confidence", 0.0)
    if isinstance(confidence, (int, float)) and confidence < 0.60:
        delivery_routing = "manual_review"
        ai_fallback_eligible = True
        flags.append("low_confidence")

    enrichment = {
        "event_id": event_id,
        "source_id": event.get("source_id", ""),
        "sender": event.get("sender", ""),
        "subject": event.get("subject", ""),
        "bot_case_type": bot_case_type,
        "possible_existing_deal": possible_existing_deal,
        "delivery_routing": delivery_routing,
        "ai_fallback_eligible": ai_fallback_eligible,
        "thread_context_available": has_thread,
        "thread_id": thread_ctx.get("thread_id", "") if thread_ctx else "",
        "previous_case_type": thread_ctx.get("previous_case_type", "")
        if thread_ctx
        else "",
        "bitrix_match_status": bitrix_match_status,
        "bitrix_match_quality": bitrix.get("bitrix_match_quality", "")
        if bitrix
        else "",
        "bitrix_entity_type": bitrix.get("bitrix_entity_type", "") if bitrix else "",
        "bitrix_entity_id": bitrix.get("bitrix_entity_id") if bitrix else None,
        "sender_events_in_run": sender_info.get("event_count", 0),
        "sender_source_count": len(sender_info.get("source_ids", [])),
        "enrichment_flags": flags,
        "confidence": confidence if isinstance(confidence, (int, float)) else None,
    }

    return enrichment
