from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROUTING_MAP_ARTIFACT = "rop_routing_map.json"
RECOMMENDATIONS_ARTIFACT = "rop_recommendations.json"
_ALLOWED_ACTIONS: frozenset[str] = frozenset(
    {
        "create_lead_draft",
        "create_tender_lead_draft",
        "attach_to_existing_deal",
        "attach_logistics_note",
        "attach_finance_note",
        "attach_procurement_note",
        "choose_correct_bitrix_entity",
        "check_duplicate",
        "ignore",
        "manual_review_required",
        "check_bitrix_connector",
    }
)
_REQUIRED_ROUTING_QUEUES: tuple[str, ...] = (
    "sales",
    "tender",
    "logistics",
    "finance",
    "procurement",
    "manual_review",
)


def _target_category(
    queues: dict[str, Any],
    queue_name: str,
) -> str:
    queue_cfg = queues[queue_name]
    return str(queue_cfg["bitrix_category"])


def build_routing_map(
    settings: dict[str, Any],
    storage_dir: Path,
    logger: logging.Logger,
) -> dict[str, Any]:
    routing_cfg = settings.get("rop", {}).get("routing", {})
    queues = routing_cfg.get("queues", {})

    routing_entries: list[dict[str, Any]] = [
        {
            "bitrix_match_status": "connector_degraded",
            "queue": "manual_review",
            "action": "check_bitrix_connector",
            "target_bitrix_category": _target_category(queues, "manual_review"),
        },
        {
            "bitrix_match_status": "weak_match",
            "queue": "manual_review",
            "action": "choose_correct_bitrix_entity",
            "target_bitrix_category": _target_category(queues, "manual_review"),
        },
        {
            "bitrix_match_status": "ambiguous",
            "queue": "manual_review",
            "action": "choose_correct_bitrix_entity",
            "target_bitrix_category": _target_category(queues, "manual_review"),
        },
        {
            "bitrix_match_status": "duplicate_candidate",
            "queue": "manual_review",
            "action": "check_duplicate",
            "target_bitrix_category": _target_category(queues, "manual_review"),
        },
        {
            "possible_existing_deal": True,
            "queue": "manual_review",
            "action": "manual_review_required",
            "target_bitrix_category": _target_category(queues, "manual_review"),
        },
        {
            "is_fallback": True,
            "queue": "manual_review",
            "action": "manual_review_required",
            "target_bitrix_category": _target_category(queues, "manual_review"),
        },
        {
            "case_type": "new_lead",
            "case_subtype": "tender",
            "bitrix_match_status": "not_found",
            "queue": "tender",
            "action": "create_tender_lead_draft",
            "target_bitrix_category": _target_category(queues, "tender"),
        },
        {
            "case_type": "existing_deal",
            "case_subtype": "logistics",
            "bitrix_match_status": "matched_deal",
            "bitrix_match_quality": "strong",
            "queue": "logistics",
            "action": "attach_logistics_note",
            "target_bitrix_category": _target_category(queues, "logistics"),
        },
        {
            "case_type": "existing_deal",
            "case_subtype": "invoice",
            "bitrix_match_status": "matched_deal",
            "queue": "finance",
            "action": "attach_finance_note",
            "target_bitrix_category": _target_category(queues, "finance"),
        },
        {
            "case_type": "existing_deal",
            "case_subtype": "procurement",
            "bitrix_match_status": "matched_deal",
            "queue": "procurement",
            "action": "attach_procurement_note",
            "target_bitrix_category": _target_category(queues, "procurement"),
        },
        {
            "case_type": "new_lead",
            "bitrix_match_status": "not_found",
            "queue": "sales",
            "action": "create_lead_draft",
            "target_bitrix_category": _target_category(queues, "sales"),
        },
        {
            "case_type": "existing_deal",
            "bitrix_match_status": "matched_deal",
            "queue": "sales",
            "action": "attach_to_existing_deal",
            "target_bitrix_category": _target_category(queues, "sales"),
        },
    ]

    artifact = {
        "run_id": None,
        "type": "routing_map",
        "read_only": True,
        "queues": queues,
        "routing_entries": routing_entries,
        "allowable_actions": sorted(_ALLOWED_ACTIONS),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    interfaces_dir = storage_dir / "interfaces"
    interfaces_dir.mkdir(parents=True, exist_ok=True)
    map_path = interfaces_dir / ROUTING_MAP_ARTIFACT
    map_path.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(
        "rop_routing_map written: path=%s queues=%d entries=%d",
        map_path.relative_to(storage_dir),
        len(queues),
        len(routing_entries),
    )

    return artifact


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


def _match_routing_rule(
    event: dict[str, Any],
    routing_entries: list[dict[str, Any]],
) -> dict[str, Any] | None:
    case_type = event.get("case_type", event.get("bot_case_type", ""))
    case_subtype = event.get("case_subtype", "")
    bitrix_status = event.get("bitrix_match_status", "")
    bitrix_quality = event.get("bitrix_match_quality", "")
    possible_deal = event.get("possible_existing_deal", False)
    is_fallback = event.get("is_fallback", False)

    for rule in routing_entries:
        if "is_fallback" in rule and rule["is_fallback"] and not is_fallback:
            continue
        if (
            "possible_existing_deal" in rule
            and rule["possible_existing_deal"]
            and not possible_deal
        ):
            continue
        if "bitrix_match_status" in rule:
            if bitrix_status != rule["bitrix_match_status"]:
                continue
        if "case_type" in rule:
            if case_type != rule["case_type"]:
                continue
        if "case_subtype" in rule:
            if case_subtype != rule.get("case_subtype", ""):
                continue
        if "bitrix_match_quality" in rule:
            if bitrix_quality != rule.get("bitrix_match_quality", ""):
                continue
        return rule

    return None


def build_recommendations(
    storage_dir: Path,
    run_id: str,
    settings: dict[str, Any],
    logger: logging.Logger,
) -> dict[str, Any]:
    runs_root = (storage_dir / "runs").resolve()
    run_dir = (runs_root / run_id).resolve()
    try:
        run_dir.relative_to(runs_root)
    except ValueError:
        raise ValueError(f"Invalid run_id: path traversal detected for '{run_id}'")

    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    classified = _read_json_list(run_dir / "classified_events.json") or []
    normalized = _read_json_list(run_dir / "normalized_events.json") or []
    bitrix_reconciliation = (
        _read_json_dict(run_dir / "bitrix_reconciliation.json") or {}
    )
    context_enrichment = _read_json_dict(run_dir / "rop_context_enrichment.json") or {}
    routing_cfg = settings.get("rop", {}).get("routing", {})

    bitrix_lookup: dict[str, dict[str, Any]] = {}
    for item in bitrix_reconciliation.get("items", []):
        eid = item.get("event_id", "")
        if eid:
            bitrix_lookup[eid] = item

    context_lookup: dict[str, dict[str, Any]] = {}
    for item in context_enrichment.get("items", []):
        eid = item.get("event_id", "")
        if eid:
            context_lookup[eid] = item

    normalized_lookup: dict[str, dict[str, Any]] = {}
    for item in normalized:
        event_id = item.get("event_id", "")
        if event_id:
            normalized_lookup[event_id] = item

    routing_map = (
        _read_json_dict(storage_dir / "interfaces" / ROUTING_MAP_ARTIFACT) or {}
    )
    routing_entries = routing_map.get("routing_entries", [])
    routing_queues = settings["rop"]["routing"]["queues"]
    manual_review_category = str(routing_queues["manual_review"]["bitrix_category"])

    items: list[dict[str, Any]] = []
    aggregate = {
        "event_count": len(classified),
        "recommendation_count": 0,
        "ignore_count": 0,
        "manual_review_count": 0,
        "actionable_count": 0,
    }
    warnings: list[str] = []

    for evt in classified:
        event_id = evt.get("event_id", "")
        original_event_id = evt.get("original_event_id", event_id)
        bitrix = bitrix_lookup.get(event_id, {})
        ctx = context_lookup.get(event_id, {})
        normalized_evt = normalized_lookup.get(original_event_id, {})

        merged = {**normalized_evt, **evt}
        if bitrix:
            merged["bitrix_match_status"] = bitrix.get("bitrix_match_status", "")
            merged["bitrix_match_quality"] = bitrix.get("bitrix_match_quality", "")
            merged["bitrix_entity_type"] = bitrix.get("bitrix_entity_type", "")
            merged["bitrix_entity_id"] = bitrix.get("bitrix_entity_id")
            merged["safe_to_use_as_target"] = bitrix.get("safe_to_use_as_target", False)
        if ctx:
            merged["possible_existing_deal"] = ctx.get("possible_existing_deal", False)
            merged["delivery_routing"] = ctx.get("delivery_routing", "standard")
            merged["ai_fallback_eligible"] = ctx.get("ai_fallback_eligible", False)

        rule = _match_routing_rule(merged, routing_entries)

        if rule:
            recommendation = _build_recommendation_item(merged, rule, run_id)
        else:
            recommendation = _build_default_recommendation(
                merged,
                run_id,
                manual_review_category,
            )

        if recommendation["recommended_action"] == "ignore":
            aggregate["ignore_count"] += 1
        elif recommendation["recommended_queue"] == "manual_review":
            aggregate["manual_review_count"] += 1
        else:
            aggregate["actionable_count"] += 1

        aggregate["recommendation_count"] += 1
        items.append(recommendation)

    artifact = {
        "run_id": run_id,
        "status": "ok",
        "read_only": True,
        "draft_only": True,
        "safe_to_execute": False,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "aggregate": aggregate,
        "items": items,
        "warnings": warnings,
    }

    artifact_path = run_dir / RECOMMENDATIONS_ARTIFACT
    artifact_path.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info(
        "rop_recommendations written: run_id=%s path=%s items=%d",
        run_id,
        artifact_path.relative_to(storage_dir),
        len(items),
    )

    return artifact


def _build_recommendation_item(
    event: dict[str, Any],
    rule: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    action = rule.get("action", "ignore")
    queue = rule.get("queue", "manual_review")
    is_ignore = action == "ignore"

    return {
        "event_id": event.get("event_id", ""),
        "sender": event.get("sender", ""),
        "subject": event.get("subject", ""),
        "title": _build_title(event),
        "summary": _build_summary(event),
        "recommended_action": action,
        "recommended_queue": queue,
        "target_bitrix_category": rule.get("target_bitrix_category", ""),
        "priority": event.get("priority", "medium"),
        "reason": _build_reason(event),
        "confidence": event.get("confidence", 0.0),
        "ai_used": bool(event.get("ai_assist_used")),
        "bitrix_status": event.get("bitrix_match_status", "unreconciled"),
        "safe_to_execute": False,
        "requires_human_confirmation": not is_ignore,
        "evidence_links": [
            f"/api/runs/{run_id}/artifacts/classified_events_json",
            f"/api/runs/{run_id}/artifacts/bitrix_reconciliation_json",
        ],
    }


def _build_default_recommendation(
    event: dict[str, Any],
    run_id: str,
    manual_review_category: str,
) -> dict[str, Any]:
    case_type = event.get("case_type", event.get("bot_case_type", ""))
    if case_type in ("spam", "noise", "auto_reply", "out_of_office", "irrelevant"):
        return _build_recommendation_item(
            event,
            {"action": "ignore", "queue": "ignore", "target_bitrix_category": ""},
            run_id,
        )

    return _build_recommendation_item(
        event,
        {
            "action": "manual_review_required",
            "queue": "manual_review",
            "target_bitrix_category": manual_review_category,
        },
        run_id,
    )


def _build_title(event: dict[str, Any]) -> str:
    case_type = event.get("case_type", event.get("bot_case_type", ""))
    subject = (event.get("subject") or "")[:80]
    sender = (event.get("sender") or "")[:40]
    if case_type == "new_lead":
        return f"New request: {subject}" if subject else f"New request from {sender}"
    if case_type == "existing_deal":
        return (
            f"Existing deal update: {subject}" if subject else f"Update from {sender}"
        )
    if case_type == "follow_up":
        return f"Follow-up: {subject}" if subject else f"Follow-up from {sender}"
    if case_type == "unknown":
        return f"Unclassified: {subject}" if subject else f"Unclassified from {sender}"
    return subject or f"Event from {sender}"


def _build_summary(event: dict[str, Any]) -> str:
    body = (event.get("body") or event.get("body_preview") or "")[:200]
    return body.strip() or "No preview available"


def _build_reason(event: dict[str, Any]) -> str:
    bitrix_status = event.get("bitrix_match_status", "")
    case_type = event.get("case_type", event.get("bot_case_type", ""))
    is_fallback = event.get("is_fallback", False)
    possible_deal = event.get("possible_existing_deal", False)

    if possible_deal:
        return "Possible existing deal detected via context evidence; manual review required."
    if is_fallback:
        return "Classification fallback; manual review required."
    if bitrix_status == "not_found":
        if case_type == "new_lead":
            return "New classified request was not found in Bitrix."
        return "Event was not found in Bitrix."
    if bitrix_status in ("weak_match", "ambiguous"):
        return "Bitrix match is uncertain; manual entity selection required."
    if bitrix_status == "duplicate_candidate":
        return "Multiple strong Bitrix candidates found; duplicate check required."
    if bitrix_status == "connector_degraded":
        return "Bitrix connector unavailable; reconciliation could not be performed."
    if bitrix_status.startswith("matched_"):
        return f"Matched in Bitrix as {bitrix_status.replace('matched_', '')}."
    if case_type in ("spam", "noise", "irrelevant"):
        return "Event classified as non-actionable."
    return "Review in operator context."
