from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ACTION_DRAFTS_ARTIFACT = "rop_action_drafts.json"


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

    action_items: list[dict[str, Any]] = []
    warnings: list[str] = []

    for item in items_raw:
        if not isinstance(item, dict):
            continue
        try:
            draft = _build_action_draft_item(item, run_id=run_id)
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
) -> dict[str, Any]:
    event_id = item.get("event_id", "")
    bot_case_type = item.get("bot_case_type", "")
    match_status = item.get("bitrix_match_status", "")
    match_quality = item.get("bitrix_match_quality", "")
    needs_manual = item.get("needs_manual_review", True)
    safe_target = item.get("safe_to_use_as_target", False)

    queue, recommended_action, recommended_next_step, priority, reason_code = (
        _map_action_v0(bot_case_type, match_status, match_quality)
    )

    if queue == "ignore":
        needs_manual = False

    return {
        "action_draft_id": str(uuid.uuid4()),
        "event_id": event_id,
        "run_id": run_id,
        "source_id": item.get("source_id", ""),
        "bot_case_type": bot_case_type,
        "bitrix_match_status": match_status,
        "queue": queue,
        "recommended_action": recommended_action,
        "recommended_next_step": recommended_next_step,
        "priority": priority,
        "reason_code": reason_code,
        "needs_manual_review": needs_manual,
        "safe_to_use_as_target": safe_target,
        "target_entity_type": item.get("bitrix_entity_type", ""),
        "target_entity_id": item.get("bitrix_entity_id"),
        "evidence_refs": [
            "bitrix_reconciliation_json",
            "classified_events_json",
        ],
        "read_only": True,
    }


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
