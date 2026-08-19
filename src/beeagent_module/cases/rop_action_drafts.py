from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from beeagent_module.cases.rop_writeback import delivery_completion_status

ACTION_DRAFTS_ARTIFACT = "rop_action_drafts.json"
RECIPIENT_ROUTING_ARTIFACT = "rop_recipient_routing.json"
WRITEBACK_STATE_FILENAME = "rop_writeback_state.json"


def _load_routing_items(run_dir: Path) -> list[dict[str, Any]]:
    routing_path = run_dir / RECIPIENT_ROUTING_ARTIFACT
    if not routing_path.exists():
        return []
    try:
        data = json.loads(routing_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    items = data.get("items", []) if isinstance(data, dict) else []
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _routing_evidence_for_event(
    items: list[dict[str, Any]],
    event_id: str,
    event_instance_id: str | None,
) -> dict[str, Any]:
    candidates = [item for item in items if item.get("event_id") == event_id]
    if event_instance_id:
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
        return legacy[0] if len(candidates) == len(legacy) == 1 else {}
    if len(candidates) == 1:
        return candidates[0]
    return {}


def _load_writeback_items(
    storage_dir: Path,
    run_id: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    path = storage_dir / "interfaces" / WRITEBACK_STATE_FILENAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    events = data.get("events", {}) if isinstance(data, dict) else {}
    if not isinstance(events, dict):
        return {}
    return {
        (
            str(record.get("event_id") or ""),
            str(record.get("event_instance_id") or ""),
        ): record
        for record in events.values()
        if isinstance(record, dict)
        and record.get("last_run_id") == run_id
        and isinstance(record.get("event_id"), str)
        and record.get("event_id")
    }


def build_action_drafts(
    storage_dir: Path,
    run_id: str,
    reconciliation: dict[str, Any],
    logger: logging.Logger,
) -> dict[str, Any]:
    runs_root = (storage_dir / "runs").resolve()
    run_dir = (runs_root / run_id).resolve()

    if not run_dir.is_relative_to(runs_root):
        raise ValueError("Invalid run_id: path traversal is not allowed.")

    if not run_dir.exists():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    items_raw = reconciliation.get("items", [])
    if not isinstance(items_raw, list):
        raise ValueError("reconciliation items must be a list")

    routing_items = _load_routing_items(run_dir)
    writeback_items = _load_writeback_items(storage_dir, run_id)

    action_items: list[dict[str, Any]] = []
    warnings: list[str] = []

    for item in items_raw:
        if not isinstance(item, dict):
            continue
        try:
            event_instance_id = item.get("event_instance_id")
            routing_evidence = _routing_evidence_for_event(
                routing_items,
                str(item.get("event_id", "")),
                event_instance_id if isinstance(event_instance_id, str) else None,
            )
            draft = _build_action_draft_item(
                item,
                run_id=run_id,
                routing_evidence=routing_evidence,
                writeback_record=writeback_items.get(
                    (str(item.get("event_id") or ""), str(event_instance_id or ""))
                ),
            )
            action_items.append(draft)
        except Exception as exc:
            warnings.append(
                f"Failed to build action draft for event "
                f"{item.get('event_id', '?')}: {exc}"
            )

    aggregate = reconciliation.get("aggregate", {})
    if not isinstance(aggregate, dict):
        aggregate = {}

    artifact: dict[str, Any] = {
        "run_id": run_id,
        "status": reconciliation.get("status", "unknown"),
        "read_only": True,
        "draft_only": True,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "aggregate": {
            "event_count": aggregate.get("event_count", 0),
            "matched_actionable": sum(
                1
                for d in action_items
                if d.get("queue") not in ("ignore", "degraded", "unreconciled")
            ),
            "ignore_count": sum(1 for d in action_items if d.get("queue") == "ignore"),
            "degraded_count": sum(
                1 for d in action_items if d.get("queue") == "degraded"
            ),
            "unreconciled_count": sum(
                1 for d in action_items if d.get("queue") == "unreconciled"
            ),
            "needs_manual_review_count": sum(
                1 for d in action_items if d.get("needs_manual_review")
            ),
            "safe_to_use_as_target_count": sum(
                1 for d in action_items if d.get("safe_to_use_as_target")
            ),
        },
        "items": action_items,
        "warnings": warnings,
    }

    artifact_path = run_dir / ACTION_DRAFTS_ARTIFACT
    artifact_path.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info(
        "ROP action drafts artifact written: run_id=%s path=%s items=%d",
        run_id,
        str(artifact_path.relative_to(storage_dir)),
        len(action_items),
    )

    return artifact


def _build_action_draft_item(
    item: dict[str, Any],
    run_id: str,
    routing_evidence: dict[str, Any] | None = None,
    writeback_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event_id = item.get("event_id", "")
    bot_case_type = item.get("bot_case_type", "")
    match_status = item.get("bitrix_match_status", "")
    match_quality = item.get("bitrix_match_quality", "")
    needs_manual = item.get("needs_manual_review", True)
    safe_target = item.get("safe_to_use_as_target", False)

    if isinstance(writeback_record, dict):
        queue, recommended_action, recommended_next_step, priority, reason_code = (
            _map_writeback_projection(writeback_record)
        )
    else:
        queue, recommended_action, recommended_next_step, priority, reason_code = (
            _map_action_v0(bot_case_type, match_status, match_quality)
        )

    if queue == "ignore":
        needs_manual = False

    routing = routing_evidence if isinstance(routing_evidence, dict) else {}
    responsible = routing.get("responsible")
    if not isinstance(responsible, dict):
        responsible = {}

    return {
        "action_draft_id": str(uuid.uuid4()),
        "event_id": event_id,
        "event_instance_id": item.get("event_instance_id", ""),
        "run_id": run_id,
        "source_id": item.get("source_id", ""),
        "bot_case_type": bot_case_type,
        "bitrix_match_status": match_status,
        "queue": queue,
        "recommended_action": recommended_action,
        "recommended_next_step": recommended_next_step,
        "priority": priority,
        "reason_code": reason_code,
        "delivery_outcome": (
            writeback_record.get("outcome")
            if isinstance(writeback_record, dict)
            else None
        ),
        "delivery_status": (
            writeback_record.get("status")
            if isinstance(writeback_record, dict)
            else None
        ),
        "needs_manual_review": needs_manual,
        "safe_to_use_as_target": safe_target,
        "target_entity_type": item.get("bitrix_entity_type", ""),
        "target_entity_id": item.get("bitrix_entity_id"),
        "recipient": str(routing.get("recipient", "")),
        "recipient_evidence_source": str(
            routing.get("recipient_evidence_source", "")
        ),
        "recipient_status": str(routing.get("recipient_status", "")),
        "proposed_responsible_user_id": responsible.get("user_id"),
        "proposed_responsible_name": str(responsible.get("name", "")),
        "proposed_responsible_email": str(responsible.get("email", "")),
        "responsible_status": str(responsible.get("status", "")),
        "responsible_reason": str(responsible.get("reason", "")),
        "evidence_refs": [
            "bitrix_reconciliation_json",
            "classified_events_json",
            "rop_recipient_routing_json",
        ],
        "read_only": True,
    }


def _map_writeback_projection(
    record: dict[str, Any],
) -> tuple[str, str, str, str, str]:
    status = str(record.get("status") or "")
    outcome = record.get("outcome")
    delivery_status = delivery_completion_status(record)
    if delivery_status == "completed":
        return (
            "delivered",
            "delivery_completed",
            "no_action_required",
            "low",
            "delivery_completed",
        )
    if delivery_status in ("failed", "unknown"):
        return (
            "deferred",
            "review_delivery_failure",
            "review_deferred_delivery",
            "medium",
            str(
                record.get("last_attach_error_code")
                or record.get("reason_code")
                or "delivery_deferred"
            ),
        )
    if outcome == "create_lead" and status in ("created", "recovered"):
        return (
            "delivery_planned",
            "complete_email_attachment",
            "controlled_writeback_pending",
            "high",
            str(record.get("last_attach_error_code") or "email_attachment_pending"),
        )
    if outcome == "create_lead":
        return (
            "delivery_planned",
            "create_lead",
            "controlled_writeback_pending",
            "high",
            "create_lead",
        )
    if outcome == "attach_existing":
        return (
            "delivery_planned",
            "attach_existing",
            "controlled_writeback_pending",
            "medium",
            "attach_existing",
        )
    return (
        "deferred",
        "deferred",
        "review_deferred_delivery",
        "medium",
        str(record.get("reason_code") or "delivery_deferred"),
    )


def _map_action_v0(
    case_type: str,
    match_status: str,
    match_quality: str,
) -> tuple[str, str, str, str, str]:
    if match_status in ("connector_degraded",):
        return (
            "degraded",
            "check_bitrix_connector",
            "investigate_connector",
            "high",
            "connector_degraded",
        )
    if match_status == "error":
        return (
            "degraded",
            "check_bitrix_connector",
            "investigate_error",
            "high",
            "reconciliation_error",
        )
    if match_status == "skipped":
        return (
            "ignore",
            "ignore",
            "no_action_required",
            "low",
            "event_skipped",
        )

    if case_type == "irrelevant":
        return (
            "ignore",
            "ignore",
            "no_action_required",
            "low",
            "event_irrelevant",
        )

    if match_status == "not_found":
        if case_type == "new_lead":
            return (
                "lost_in_bitrix",
                "check_crm_gap",
                "create_lead_manually",
                "high",
                "new_lead_not_in_crm",
            )
        return (
            "lost_in_bitrix",
            "check_crm_gap",
            "review_crm_gap",
            "medium",
            "event_not_in_crm",
        )

    if match_status.startswith("matched_"):
        if case_type == "new_lead":
            return (
                "matched",
                "review_existing_lead",
                "verify_lead_accuracy",
                "medium",
                "lead_exists_in_crm",
            )
        if case_type == "existing_deal":
            return (
                "matched",
                "review_deal",
                "verify_deal_accuracy",
                "medium",
                "deal_exists_in_crm",
            )
        return (
            "matched",
            "review_existing_entity",
            "verify_entity_accuracy",
            "medium",
            "entity_exists_in_crm",
        )

    if match_status in ("weak_match", "ambiguous"):
        if match_quality == "weak":
            return (
                "ambiguous",
                "choose_correct_entity",
                "verify_and_select_target",
                "high",
                "weak_match_needs_verification",
            )
        return (
            "ambiguous",
            "choose_correct_entity",
            "verify_and_select_target",
            "high",
            "ambiguous_match_needs_resolution",
        )

    if match_status == "duplicate_candidate":
        return (
            "ambiguous",
            "resolve_duplicate_candidate",
            "select_correct_entity",
            "high",
            "duplicate_candidates_found",
        )

    return (
        "unreconciled",
        "run_read_only_reconciliation",
        "run_reconciliation",
        "medium",
        "not_reconciled",
    )
