from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from email.utils import getaddresses
from pathlib import Path
from typing import Any

from beeagent_module.adapters.bitrix_client import (
    BitrixApiError,
    BitrixAuthError,
    BitrixConnectorError,
    BitrixMalformedResponse,
    BitrixTimeoutError,
    BitrixTransportError,
    build_bitrix_client,
)
from beeagent_module.adapters.bitrix_write_client import (
    LEAD_ENTITY_TYPE_ID,
    BitrixWriteClient,
    build_bitrix_write_client,
)
from beeagent_module.core.input_source import effective_rop_sender_email

WRITEBACK_STATE_FILENAME = "rop_writeback_state.json"
WRITEBACK_SUMMARY_FILENAME = "rop_writeback_summary.json"
WRITEBACK_STATE_VERSION = 1

ORIGINATOR_ID = "beeagent-rop"
CREATE_CASE_TYPES: frozenset[str] = frozenset({"new_lead", "irrelevant"})
_MAX_IDENTITY_FIELD_LENGTH = 320
_MAX_ORIGIN_ID_LENGTH = 200
_MAX_LEAD_TITLE_LENGTH = 200
_MAX_LEAD_NAME_LENGTH = 120
_MAX_ACTIVITY_DESCRIPTION_LENGTH = 3000
_TERMINAL_TRANSPORT_CODES: frozenset[int] = frozenset({400})
_RECOVERABLE_PREREQUISITE_REASONS = frozenset(
    {
        "reconciliation_unavailable",
        "reconciliation_connector_degraded",
        "reconciliation_error",
    }
)


class RopWritebackError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _bounded_text(value: Any, max_length: int = _MAX_IDENTITY_FIELD_LENGTH) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:max_length]


def _bounded_email(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if "@" not in value:
        return ""
    return value[: _MAX_IDENTITY_FIELD_LENGTH]


def _bounded_sender_name(value: Any, max_length: int = _MAX_LEAD_NAME_LENGTH) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip().strip('"')
    if not value:
        return ""
    if "<" not in value and "@" not in value:
        return value[:max_length]
    try:
        pairs = getaddresses([value])
    except (TypeError, ValueError, IndexError):
        return ""
    for display_name, _addr in pairs:
        display_name = (display_name or "").strip().strip('"')
        if display_name:
            return display_name[:max_length]
    return ""


def _effective_sender_name(event: dict[str, Any]) -> str:
    if event.get("forwarded_wrapper") is True:
        return _bounded_sender_name(event.get("original_sender"))
    return _bounded_sender_name(event.get("from_name")) or _bounded_sender_name(
        event.get("sender")
    )


def _stable_remote_id(event: dict[str, Any]) -> str:
    for key in ("message_id", "x_email_id", "event_id"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return _bounded_text(value)
    return ""


def _stable_identity(client_id: str, source_id: str, remote_id: str) -> str:
    return "|".join((client_id, source_id, remote_id))


def _origin_id(identity: str) -> str:
    if len(identity) <= _MAX_ORIGIN_ID_LENGTH:
        return identity
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _state_path(storage_dir: Path) -> Path:
    return storage_dir / "interfaces" / WRITEBACK_STATE_FILENAME


def _load_state(storage_dir: Path) -> dict[str, Any]:
    path = _state_path(storage_dir)
    if not path.exists():
        return {
            "version": WRITEBACK_STATE_VERSION,
            "policy_snapshot": {},
            "events": {},
            "runs": {},
            "updated_at_utc": _utc_now(),
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        raise RopWritebackError(
            "ROP write-back state is invalid; inspect storage/interfaces/"
            f"{WRITEBACK_STATE_FILENAME}: {exc}"
        ) from exc
    if not isinstance(data, dict) or data.get("version") != WRITEBACK_STATE_VERSION:
        raise RopWritebackError(
            "ROP write-back state has an unsupported version; "
            f"expected {WRITEBACK_STATE_VERSION}"
        )
    if not isinstance(data.get("events"), dict):
        data["events"] = {}
    if not isinstance(data.get("runs"), dict):
        data["runs"] = {}
    if not isinstance(data.get("policy_snapshot"), dict):
        data["policy_snapshot"] = {}
    return data


def _save_state(storage_dir: Path, state: dict[str, Any]) -> Path:
    path = _state_path(storage_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at_utc"] = _utc_now()
    fd, temporary = tempfile.mkstemp(prefix=".rop_writeback_state.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def _writeback_policy(settings: dict) -> dict[str, Any]:
    bitrix_cfg = settings.get("bitrix", {})
    if not isinstance(bitrix_cfg, dict):
        bitrix_cfg = {}
    wb = bitrix_cfg.get("writeback", {})
    if not isinstance(wb, dict):
        wb = {}
    stages_cfg = wb.get("stages", {})
    if not isinstance(stages_cfg, dict):
        stages_cfg = {}
    stages = {
        str(key): str(value).strip()
        for key, value in stages_cfg.items()
        if isinstance(key, str) and isinstance(value, str) and value.strip()
    }
    webhook_env = str(wb.get("webhook_env") or "BITRIX_WRITEBACK_WEBHOOK_URL")
    return {
        "enabled": wb.get("enabled") is True,
        "dry_run": wb.get("dry_run") is True,
        "webhook_env": webhook_env,
        "timeout": int(wb.get("timeout", 10)),
        "attempts_retry_max": int(wb.get("attempts_retry_max", 3)),
        "stages": stages,
        "email_attach": wb.get("email_attach") is True,
        "source_id": str(wb.get("source_id") or ""),
        "credential_present": bool(os.environ.get(webhook_env)),
    }


def _read_json_list(run_dir: Path, filename: str, required: bool) -> list[dict[str, Any]]:
    path = run_dir / filename
    if not path.exists():
        if required:
            raise RopWritebackError(
                f"Required artifact not found for ROP write-back: {filename}"
            )
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        if required:
            raise RopWritebackError(
                f"Required artifact is invalid for ROP write-back: {filename}: {exc}"
            ) from exc
        return []
    if not isinstance(data, list):
        if required:
            raise RopWritebackError(
                f"Invalid artifact format for ROP write-back: {filename} "
                "must contain a JSON list."
            )
        return []
    return [item for item in data if isinstance(item, dict)]


def _read_json_dict(run_dir: Path, filename: str, required: bool) -> dict[str, Any]:
    path = run_dir / filename
    if not path.exists():
        if required:
            raise RopWritebackError(
                f"Required artifact not found for ROP write-back: {filename}"
            )
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        if required:
            raise RopWritebackError(
                f"Required artifact is invalid for ROP write-back: {filename}: {exc}"
            ) from exc
        return {}
    if not isinstance(data, dict):
        if required:
            raise RopWritebackError(
                f"Invalid artifact format for ROP write-back: {filename} "
                "must contain a JSON mapping."
            )
        return {}
    return data


def _final_decisions_by_identity(decisions: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for decision in decisions.get("events", []):
        if not isinstance(decision, dict):
            continue
        event_id = decision.get("event_id")
        instance_id = decision.get("event_instance_id")
        if not isinstance(event_id, str) or not event_id:
            continue
        result[(event_id, str(instance_id or ""))] = decision
    return result


def _items_by_identity(items: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        event_id = item.get("event_id")
        instance_id = item.get("event_instance_id")
        if not isinstance(event_id, str) or not event_id:
            continue
        result[(event_id, str(instance_id or ""))] = item
    return result


def _final_case_type(event: dict[str, Any], decision: dict[str, Any] | None) -> str:
    if decision is not None:
        value = decision.get("final_case_type")
        if isinstance(value, str) and value.strip():
            return value.strip()
    value = event.get("case_type")
    if isinstance(value, str) and value.strip():
        return value.strip()
    value = event.get("bot_case_type")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "unknown"


def _responsible_from_routing(routing_item: dict[str, Any] | None) -> dict[str, Any]:
    if routing_item is None:
        return {
            "status": "unresolved",
            "user_id": None,
            "reason": "no_routing_evidence",
        }
    responsible = routing_item.get("responsible")
    if not isinstance(responsible, dict):
        return {
            "status": "unresolved",
            "user_id": None,
            "reason": "no_responsible_evidence",
        }
    status = str(responsible.get("status") or "unresolved")
    user_id = responsible.get("user_id")
    if status == "matched" and isinstance(user_id, int) and user_id > 0:
        return {
            "status": "matched",
            "user_id": user_id,
            "reason": responsible.get("reason"),
        }
    return {
        "status": status,
        "user_id": None,
        "reason": responsible.get("reason"),
    }


def _decide_delivery(
    case_type: str,
    recon_item: dict[str, Any] | None,
    routing_item: dict[str, Any] | None,
    policy: dict[str, Any],
) -> dict[str, Any]:
    if recon_item is None:
        return {"outcome": "deferred", "reason_code": "reconciliation_unavailable"}
    recon_status = str(recon_item.get("bitrix_match_status") or "")
    if recon_status == "connector_degraded":
        return {
            "outcome": "deferred",
            "reason_code": "reconciliation_connector_degraded",
        }
    if recon_status == "error":
        return {"outcome": "deferred", "reason_code": "reconciliation_error"}
    if recon_status == "skipped":
        return {"outcome": "deferred", "reason_code": "event_skipped"}

    safe_target = recon_item.get("safe_to_use_as_target") is True
    target_entity_id = recon_item.get("bitrix_entity_id")
    target_entity_type = str(recon_item.get("bitrix_entity_type") or "")
    target_entity_type_id = recon_item.get("bitrix_entity_type_id")
    target_responsible_id = recon_item.get("bitrix_responsible_id")

    if safe_target:
        target_is_valid = (
            target_entity_type in {"lead", "deal"}
            and isinstance(target_entity_id, int)
            and not isinstance(target_entity_id, bool)
            and target_entity_id > 0
            and isinstance(target_entity_type_id, int)
            and target_entity_type_id in {LEAD_ENTITY_TYPE_ID, 2}
        )
        if not target_is_valid:
            return {"outcome": "deferred", "reason_code": "unsafe_target"}
        if (
            not isinstance(target_responsible_id, int)
            or isinstance(target_responsible_id, bool)
            or target_responsible_id <= 0
        ):
            return {"outcome": "deferred", "reason_code": "responsible_unresolved"}
        return {
            "outcome": "attach_existing",
            "reason_code": None,
            "target_entity_type": target_entity_type,
            "target_entity_type_id": target_entity_type_id,
            "target_entity_id": target_entity_id,
            "target_responsible_user_id": target_responsible_id,
        }
    if recon_status in ("weak_match", "ambiguous"):
        return {"outcome": "deferred", "reason_code": "ambiguous_target"}
    if recon_status == "duplicate_candidate":
        return {"outcome": "deferred", "reason_code": "duplicate_target"}

    target_absent = recon_status == "not_found" or (
        recon_status == "identity_only_no_target"
        and recon_item.get("suitable_target_search") == "completed_no_target"
    )
    if target_absent:
        if case_type in CREATE_CASE_TYPES:
            responsible = _responsible_from_routing(routing_item)
            if responsible["status"] != "matched":
                return {
                    "outcome": "deferred",
                    "reason_code": "responsible_unresolved",
                    "responsible_status": responsible["status"],
                    "responsible_reason": responsible["reason"],
                }
            stage_id = policy["stages"].get(case_type)
            if not stage_id:
                return {
                    "outcome": "deferred",
                    "reason_code": "stage_not_configured",
                    "responsible_status": responsible["status"],
                    "responsible_user_id": responsible["user_id"],
                }
            return {
                "outcome": "create_lead",
                "reason_code": None,
                "stage_id": stage_id,
                "responsible_status": responsible["status"],
                "responsible_user_id": responsible["user_id"],
                "responsible_reason": responsible.get("reason"),
            }
        return {"outcome": "deferred", "reason_code": "case_type_not_create_eligible"}

    if recon_status.startswith("matched_"):
        return {"outcome": "deferred", "reason_code": "unsafe_target"}

    return {"outcome": "deferred", "reason_code": "delivery_not_applicable"}


def _build_planned_record(
    event: dict[str, Any],
    decision: dict[str, Any] | None,
    recon_item: dict[str, Any] | None,
    routing_item: dict[str, Any] | None,
    policy: dict[str, Any],
    run_id: str,
) -> dict[str, Any] | None:
    client_id = _bounded_text(event.get("client_id"))
    source_id = _bounded_text(event.get("source_id"))
    remote_id = _stable_remote_id(event)
    if not remote_id:
        return None
    identity = _stable_identity(client_id, source_id, remote_id)
    event_id = _bounded_text(event.get("event_id"))
    event_instance_id = _bounded_text(event.get("event_instance_id"))
    case_type = _final_case_type(event, decision)
    should_rop_see = event.get("should_rop_see") is True

    delivery = _decide_delivery(case_type, recon_item, routing_item, policy)

    record = {
        "identity": identity,
        "client_id": client_id,
        "source_id": source_id,
        "remote_id": remote_id,
        "message_id": _bounded_text(event.get("message_id")),
        "x_email_id": _bounded_text(event.get("x_email_id")),
        "event_id": event_id,
        "event_instance_id": event_instance_id,
        "subject": _bounded_text(event.get("subject"), _MAX_LEAD_TITLE_LENGTH),
        "sender_email": effective_rop_sender_email(event),
        "sender_name": _effective_sender_name(event),
        "body_preview": _bounded_text(
            event.get("body_preview") or event.get("text_preview") or "",
            _MAX_ACTIVITY_DESCRIPTION_LENGTH,
        ),
        "email_activity_id": None,
        "email_attachment_required": (
            delivery["outcome"] in {"create_lead", "attach_existing"}
            and policy["email_attach"] is True
        ),
        "email_attachment_status": (
            "pending"
            if delivery["outcome"] in {"create_lead", "attach_existing"}
            and policy["email_attach"] is True
            else "not_required"
        ),
        "attach_attempts": 0,
        "last_attach_error_code": None,
        "case_type": case_type,
        "should_rop_see": should_rop_see,
        "outcome": delivery["outcome"],
        "status": (
            "pending"
            if delivery.get("reason_code") in _RECOVERABLE_PREREQUISITE_REASONS
            else "planned"
        ),
        "reason_code": delivery.get("reason_code"),
        "stage_id": delivery.get("stage_id"),
        "responsible_user_id": delivery.get("responsible_user_id"),
        "responsible_status": str(delivery.get("responsible_status") or ""),
        "responsible_reason": delivery.get("responsible_reason"),
        "target_entity_type": str(delivery.get("target_entity_type") or ""),
        "target_entity_type_id": delivery.get("target_entity_type_id"),
        "target_entity_id": delivery.get("target_entity_id"),
        "target_responsible_user_id": delivery.get("target_responsible_user_id"),
        "originator_id": ORIGINATOR_ID,
        "origin_id": _origin_id(identity),
        "remote_entity_type_id": None,
        "remote_entity_id": None,
        "attempts": 0,
        "last_error_code": None,
        "uncertain": False,
        "created_at_utc": _utc_now(),
        "updated_at_utc": _utc_now(),
        "last_run_id": run_id,
    }
    return record


def _occurrence_preferred(
    candidate: dict[str, Any],
    current: dict[str, Any],
) -> bool:
    candidate_duplicate = candidate.get("case_type") == "duplicate"
    current_duplicate = current.get("case_type") == "duplicate"
    if candidate_duplicate != current_duplicate:
        return not candidate_duplicate
    return False


def _merge_planned_record(
    existing: dict[str, Any] | None,
    planned: dict[str, Any],
) -> dict[str, Any]:
    if existing is None:
        return planned
    merged = dict(planned)
    status = existing.get("status")
    if status in ("created", "attached", "recovered"):
        merged["status"] = status
        merged["outcome"] = existing.get("outcome", planned["outcome"])
        merged["remote_entity_type_id"] = existing.get("remote_entity_type_id")
        merged["remote_entity_id"] = existing.get("remote_entity_id")
        merged["attempts"] = existing.get("attempts", 0)
        merged["last_error_code"] = existing.get("last_error_code")
        merged["uncertain"] = False
    elif status in ("pending", "uncertain", "failed"):
        merged["status"] = status
        merged["attempts"] = existing.get("attempts", 0)
        merged["last_error_code"] = existing.get("last_error_code")
        merged["uncertain"] = existing.get("uncertain", False) is True
        merged["remote_entity_type_id"] = existing.get("remote_entity_type_id")
        merged["remote_entity_id"] = existing.get("remote_entity_id")
    merged["created_at_utc"] = existing.get("created_at_utc", planned["created_at_utc"])
    merged["updated_at_utc"] = _utc_now()
    merged["email_activity_id"] = existing.get("email_activity_id")
    if "email_attachment_required" in existing:
        merged["email_attachment_required"] = existing["email_attachment_required"]
        merged["email_attachment_status"] = existing.get(
            "email_attachment_status", "unknown"
        )
    else:
        merged["email_attachment_required"] = None
        merged["email_attachment_status"] = "unknown"
    merged["attach_attempts"] = existing.get("attach_attempts", 0)
    merged["last_attach_error_code"] = existing.get("last_attach_error_code")
    return merged


def _aggregate_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    aggregate: dict[str, Any] = {
        "event_count": len(records),
        "outcome_counts": {
            "create_lead": 0,
            "attach_existing": 0,
            "deferred": 0,
        },
        "status_counts": {},
        "delivery_status_counts": {},
        "reason_counts": {},
    }
    for record in records:
        outcome = record.get("outcome")
        if outcome in aggregate["outcome_counts"]:
            aggregate["outcome_counts"][outcome] += 1
        status = str(record.get("status") or "unknown")
        aggregate["status_counts"][status] = (
            aggregate["status_counts"].get(status, 0) + 1
        )
        delivery_status = delivery_completion_status(record)
        aggregate["delivery_status_counts"][delivery_status] = (
            aggregate["delivery_status_counts"].get(delivery_status, 0) + 1
        )
        reason = str(record.get("reason_code") or "none")
        aggregate["reason_counts"][reason] = (
            aggregate["reason_counts"].get(reason, 0) + 1
        )
    return aggregate


def delivery_completion_status(record: dict[str, Any]) -> str:
    status = str(record.get("status") or "")
    if status in ("failed", "deferred"):
        return "failed"
    if record.get("outcome") == "attach_existing":
        if _positive_int(record.get("email_activity_id")):
            return "completed"
        if status == "uncertain" or record.get("email_attachment_status") == "uncertain":
            return "uncertain"
        return "pending"
    if record.get("outcome") != "create_lead":
        return "failed"
    if status not in ("created", "recovered"):
        return "uncertain" if status == "uncertain" else "pending"
    attachment_required = record.get("email_attachment_required")
    if attachment_required is False:
        return "completed"
    if attachment_required is not True:
        return "unknown"
    if _positive_int(record.get("email_activity_id")):
        return "completed"
    attachment_status = str(record.get("email_attachment_status") or "pending")
    if attachment_status in ("failed", "uncertain"):
        return attachment_status
    return "pending"


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _bounded_run_dir(storage_dir: Path, run_id: str) -> Path:
    runs_root = (storage_dir / "runs").resolve()
    run_dir = (runs_root / run_id).resolve()
    if not run_dir.is_relative_to(runs_root):
        raise RopWritebackError(
            "Invalid run_id for ROP write-back: path traversal is not allowed."
        )
    return run_dir


def _write_run_summary(
    storage_dir: Path,
    run_id: str,
    state: dict[str, Any],
    logger: logging.Logger,
) -> Path:
    run_dir = _bounded_run_dir(storage_dir, run_id)
    events = [
        record
        for record in state.get("events", {}).values()
        if isinstance(record, dict) and record.get("last_run_id") == run_id
    ]
    if not events and not run_dir.exists():
        logger.info(
            "ROP write-back summary skipped: no events for run_id=%s", run_id
        )
        return run_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "run_id": run_id,
        "projection": True,
        "read_only": True,
        "source_of_truth": WRITEBACK_STATE_FILENAME,
        "generated_at_utc": _utc_now(),
        "policy": {
            "enabled": state.get("policy_snapshot", {}).get("enabled") is True,
            "dry_run": state.get("policy_snapshot", {}).get("dry_run") is True,
        },
        "aggregate": _aggregate_records(events),
        "events": events,
    }
    path = run_dir / WRITEBACK_SUMMARY_FILENAME
    path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(
        "ROP write-back summary written: run_id=%s path=%s events=%d",
        run_id,
        str(path.relative_to(storage_dir)),
        len(events),
    )
    return path


def _refresh_changed_run_projections(
    storage_dir: Path,
    state: dict[str, Any],
    previous_records: dict[str, str],
    logger: logging.Logger,
) -> list[str]:
    changed_run_ids = sorted(
        {
            str(record.get("last_run_id"))
            for identity, record in state.get("events", {}).items()
            if isinstance(record, dict)
            and isinstance(record.get("last_run_id"), str)
            and record.get("last_run_id")
            and previous_records.get(str(identity))
            != json.dumps(record, sort_keys=True, ensure_ascii=False)
        }
    )
    if not changed_run_ids:
        return []

    from beeagent_module.cases.rop_action_drafts import build_action_drafts

    refreshed: list[str] = []
    for original_run_id in changed_run_ids:
        _write_run_summary(storage_dir, original_run_id, state, logger)
        try:
            run_dir = _bounded_run_dir(storage_dir, original_run_id)
            reconciliation = _read_json_dict(
                run_dir, "bitrix_reconciliation.json", required=True
            )
            build_action_drafts(storage_dir, original_run_id, reconciliation, logger)
        except Exception as exc:
            logger.warning(
                "ROP write-back projection refresh failed: run_id=%s reason=%s",
                original_run_id,
                exc,
            )
        refreshed.append(original_run_id)
    return refreshed


def build_writeback_plan(
    storage_dir: Path,
    run_id: str,
    settings: dict,
    logger: logging.Logger,
) -> dict[str, Any]:
    run_dir = _bounded_run_dir(storage_dir, run_id)
    if not run_dir.exists():
        raise RopWritebackError(f"Run directory not found: {run_dir}")

    classified = _read_json_list(run_dir, "classified_events.json", required=True)
    decisions = _read_json_dict(run_dir, "rop_final_decisions.json", required=True)
    reconciliation = _read_json_dict(
        run_dir, "bitrix_reconciliation.json", required=True
    )
    routing = _read_json_dict(run_dir, "rop_recipient_routing.json", required=False)

    decision_by_id = _final_decisions_by_identity(decisions)
    recon_by_id = _items_by_identity(reconciliation.get("items", []))
    routing_by_id = _items_by_identity(routing.get("items", []))

    policy = _writeback_policy(settings)

    state = _load_state(storage_dir)
    state["policy_snapshot"] = {
        "enabled": policy["enabled"],
        "dry_run": policy["dry_run"],
        "webhook_env": policy["webhook_env"],
        "attempts_retry_max": policy["attempts_retry_max"],
        "stages": policy["stages"],
        "email_attach": policy["email_attach"],
        "source_id": policy["source_id"],
    }

    planned_records: list[dict[str, Any]] = []
    planned_by_identity: dict[str, dict[str, Any]] = {}
    for event in classified:
        event_id = event.get("event_id")
        event_instance_id = event.get("event_instance_id")
        if not isinstance(event_id, str) or not event_id:
            continue
        identity_key = (event_id, str(event_instance_id or ""))
        planned = _build_planned_record(
            event=event,
            decision=decision_by_id.get(identity_key),
            recon_item=recon_by_id.get(identity_key),
            routing_item=routing_by_id.get(identity_key),
            policy=policy,
            run_id=run_id,
        )
        if planned is None:
            logger.warning(
                "ROP write-back plan skipped event without stable identity: "
                "run_id=%s event_id=%s",
                run_id,
                event_id,
            )
            continue
        identity = planned["identity"]
        existing_planned = planned_by_identity.get(identity)
        if existing_planned is None or _occurrence_preferred(
            planned, existing_planned
        ):
            planned_by_identity[identity] = planned

    for identity, planned in planned_by_identity.items():
        existing = state["events"].get(identity)
        merged = _merge_planned_record(existing, planned)
        state["events"][identity] = merged
        planned_records.append(merged)

    state["runs"][run_id] = {
        "run_id": run_id,
        "event_count": len(planned_records),
        "planned_at_utc": _utc_now(),
        "aggregate": _aggregate_records(planned_records),
    }

    path = _save_state(storage_dir, state)
    _write_run_summary(storage_dir, run_id, state, logger)

    logger.info(
        "ROP write-back plan persisted: run_id=%s path=%s events=%d outcome_create=%d "
        "outcome_attach=%d outcome_deferred=%d",
        run_id,
        str(path.relative_to(storage_dir)),
        len(planned_records),
        sum(1 for r in planned_records if r.get("outcome") == "create_lead"),
        sum(1 for r in planned_records if r.get("outcome") == "attach_existing"),
        sum(1 for r in planned_records if r.get("outcome") == "deferred"),
    )

    return {
        "run_id": run_id,
        "status": "planned",
        "policy": policy,
        "aggregate": _aggregate_records(planned_records),
        "events": planned_records,
    }


def refresh_recoverable_writeback_prerequisites(
    storage_dir: Path,
    settings: dict,
    logger: logging.Logger,
) -> list[str]:
    state = _load_state(storage_dir)
    run_ids = sorted(
        {
            record.get("last_run_id")
            for record in state["events"].values()
            if isinstance(record, dict)
            and record.get("outcome") == "deferred"
            and record.get("reason_code") in _RECOVERABLE_PREREQUISITE_REASONS
            and isinstance(record.get("last_run_id"), str)
            and record.get("last_run_id")
        }
    )
    if not run_ids:
        return []

    from beeagent_module.cases.rop_action_drafts import build_action_drafts
    from beeagent_module.cases.rop_bitrix_reconciliation import run_reconciliation

    refreshed: list[str] = []
    for run_id in run_ids:
        try:
            reconciliation = run_reconciliation(storage_dir, run_id, settings, logger)
            build_writeback_plan(storage_dir, run_id, settings, logger)
            build_action_drafts(storage_dir, run_id, reconciliation, logger)
            refreshed.append(run_id)
        except Exception as exc:
            logger.warning(
                "ROP write-back prerequisite refresh failed: run_id=%s reason=%s",
                run_id,
                exc,
            )
    return refreshed


def _validate_stages_against_bitrix(
    client: Any,
    stages: dict[str, str],
    logger: logging.Logger,
) -> list[str]:
    data = client.status_list()
    result = data.get("result")
    if not isinstance(result, list):
        raise BitrixMalformedResponse(
            "Bitrix returned malformed crm.status.list result"
        )
    status_ids = {
        str(entry.get("STATUS_ID"))
        for entry in result
        if isinstance(entry, dict)
        and str(entry.get("ENTITY_ID") or "") == "STATUS"
        and isinstance(entry.get("STATUS_ID"), str)
        and entry.get("STATUS_ID")
    }
    if not status_ids:
        raise BitrixConnectorError(
            "Bitrix lead status list is empty; stage validation is unavailable"
        )
    configured = set(stages.values())
    return sorted(stage for stage in configured if stage not in status_ids)


def _lookup_by_origin(
    client: Any,
    originator_id: str,
    origin_id: str,
) -> int | None:
    data = client.item_list(
        entity_type_id=LEAD_ENTITY_TYPE_ID,
        filter_params={"originatorId": originator_id, "originId": origin_id},
        select=["id"],
        limit=10,
    )
    result = data.get("result")
    if not isinstance(result, dict):
        raise BitrixMalformedResponse(
            "Bitrix returned malformed crm.item.list result"
        )
    items = result.get("items")
    if not isinstance(items, list):
        raise BitrixMalformedResponse(
            "Bitrix returned malformed crm.item.list items"
        )
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if isinstance(item_id, int) and not isinstance(item_id, bool) and item_id > 0:
            return item_id
        if isinstance(item_id, str) and item_id.strip().isdigit():
            return int(item_id)
    return None


def _build_lead_title(event: dict[str, Any]) -> str:
    subject = _bounded_text(event.get("subject"), _MAX_LEAD_TITLE_LENGTH)
    if subject:
        return subject
    event_id = _bounded_text(event.get("event_id"), _MAX_LEAD_TITLE_LENGTH)
    if event_id:
        return f"ROP lead {event_id}"
    return "ROP lead"


def _classify_write_failure(exc: Exception) -> tuple[str, bool, bool]:
    if isinstance(exc, BitrixAuthError):
        return "permission_denied", False, False
    if isinstance(exc, BitrixApiError):
        return "api_error", False, False
    if isinstance(exc, BitrixTimeoutError):
        return "timeout", True, True
    if isinstance(exc, BitrixMalformedResponse):
        return "malformed_response", True, True
    if isinstance(exc, BitrixTransportError):
        code = getattr(exc, "code", None)
        if code in _TERMINAL_TRANSPORT_CODES:
            return "invalid_request", False, False
        return "transport", True, False
    return "unexpected", True, False


def _activity_owner(record: dict[str, Any]) -> tuple[int, int, int] | None:
    if record.get("outcome") == "attach_existing":
        entity_type_id = record.get("target_entity_type_id")
        entity_id = record.get("target_entity_id")
        responsible_id = record.get("target_responsible_user_id")
    else:
        entity_type_id = LEAD_ENTITY_TYPE_ID
        entity_id = record.get("remote_entity_id")
        responsible_id = record.get("responsible_user_id")
    if all(
        isinstance(value, int) and not isinstance(value, bool) and value > 0
        for value in (entity_type_id, entity_id, responsible_id)
    ):
        return entity_type_id, entity_id, responsible_id
    return None


def _lookup_activity_by_origin(
    client: Any,
    owner_entity_type_id: int,
    owner_id: int,
    origin_id: str,
) -> int | None:
    data = client.activity_list(
        filter_params={
            "OWNER_TYPE_ID": owner_entity_type_id,
            "OWNER_ID": owner_id,
            "TYPE_ID": 4,
            "PROVIDER_ID": ORIGINATOR_ID,
            "PROVIDER_TYPE_ID": origin_id,
        },
        select=["ID"],
    )
    result = data.get("result")
    if not isinstance(result, list):
        raise BitrixMalformedResponse(
            "Bitrix returned malformed crm.activity.list result"
        )
    for item in result:
        if not isinstance(item, dict):
            continue
        activity_id = item.get("ID")
        if isinstance(activity_id, int) and not isinstance(activity_id, bool):
            if activity_id > 0:
                return activity_id
        if isinstance(activity_id, str) and activity_id.strip().isdigit():
            return int(activity_id)
    return None


def _execute_email_attachment(
    record: dict[str, Any],
    policy: dict[str, Any],
    readonly_client: Any,
    write_client: BitrixWriteClient,
    logger: logging.Logger,
) -> bool:
    attachment_required = record.get("email_attachment_required") is True
    if not attachment_required:
        record["email_attachment_status"] = "not_required"
        if record.get("outcome") == "attach_existing":
            record["status"] = "deferred"
            record["reason_code"] = "email_attachment_disabled"
        return False
    if not policy["email_attach"]:
        record["email_attachment_status"] = "pending"
        record["last_attach_error_code"] = "email_attachment_disabled"
        return False
    if record.get("email_activity_id"):
        record["email_attachment_status"] = "attached"
        if record.get("outcome") == "attach_existing":
            record["status"] = "attached"
        return False
    sender_email = record.get("sender_email") or ""
    if not sender_email:
        record["email_attachment_status"] = "failed"
        record["last_attach_error_code"] = "email_sender_unavailable"
        if record.get("outcome") == "attach_existing":
            record["status"] = "deferred"
            record["reason_code"] = "email_sender_unavailable"
        return False
    owner = _activity_owner(record)
    if owner is None:
        record["email_attachment_status"] = "failed"
        record["last_attach_error_code"] = "responsible_unresolved"
        if record.get("outcome") == "attach_existing":
            record["status"] = "deferred"
            record["reason_code"] = "responsible_unresolved"
        return False
    owner_entity_type_id, owner_id, responsible_id = owner
    attempts = int(record.get("attach_attempts", 0) or 0)
    if attempts >= policy["attempts_retry_max"]:
        record["email_attachment_status"] = "failed"
        record["last_attach_error_code"] = "retry_exhausted"
        if record.get("outcome") == "attach_existing":
            record["status"] = "failed"
            record["reason_code"] = "retry_exhausted"
        return False
    try:
        existing_id = _lookup_activity_by_origin(
            readonly_client,
            owner_entity_type_id,
            owner_id,
            record["origin_id"],
        )
    except BitrixConnectorError as exc:
        record["attach_attempts"] = attempts + 1
        record["email_attachment_status"] = "uncertain"
        record["last_attach_error_code"] = "activity_idempotency_lookup_failed"
        if record.get("outcome") == "attach_existing":
            record["status"] = "pending"
            record["uncertain"] = True
        logger.warning(
            "ROP write-back activity idempotency lookup failed: identity=%s reason=%s",
            record["identity"],
            exc,
        )
        return False
    if existing_id is not None:
        record["email_activity_id"] = existing_id
        record["email_attachment_status"] = "attached"
        record["last_attach_error_code"] = None
        record["attach_attempts"] = attempts
        record["uncertain"] = False
        if record.get("outcome") == "attach_existing":
            record["status"] = "attached"
        logger.info(
            "ROP write-back recovered email activity: identity=%s activity_id=%s",
            record["identity"],
            existing_id,
        )
        return False
    try:
        activity_id = write_client.add_email_activity(
            owner_entity_type_id=owner_entity_type_id,
            owner_id=owner_id,
            responsible_id=responsible_id,
            origin_id=record["origin_id"],
            subject=record.get("subject") or "",
            description=record.get("body_preview") or "",
            sender_email=sender_email,
        )
        record["email_activity_id"] = activity_id
        record["email_attachment_status"] = "attached"
        record["last_attach_error_code"] = None
        record["attach_attempts"] = attempts + 1
        record["uncertain"] = False
        if record.get("outcome") == "attach_existing":
            record["status"] = "attached"
        logger.info(
            "ROP write-back email activity attached: identity=%s activity_id=%s",
            record["identity"],
            activity_id,
        )
        return True
    except BitrixConnectorError as exc:
        error_code, retryable, uncertain = _classify_write_failure(exc)
        record["attach_attempts"] = attempts + 1
        record["last_attach_error_code"] = error_code
        record["email_attachment_status"] = (
            "uncertain" if uncertain else "pending" if retryable else "failed"
        )
        if record.get("outcome") == "attach_existing":
            if uncertain:
                record["status"] = "uncertain"
                record["uncertain"] = True
            elif retryable:
                record["status"] = "pending"
                record["uncertain"] = False
            else:
                record["status"] = "failed"
                record["reason_code"] = error_code
                record["uncertain"] = False
        logger.warning(
            "ROP write-back email activity attach failed: identity=%s error_code=%s",
            record["identity"],
            error_code,
        )
        return False


def _execute_create_lead(
    record: dict[str, Any],
    policy: dict[str, Any],
    readonly_client: Any,
    write_client: BitrixWriteClient,
    logger: logging.Logger,
) -> None:
    if record.get("remote_entity_id"):
        record["status"] = "created"
        record["uncertain"] = False
        record["last_error_code"] = None
        return

    attempts = int(record.get("attempts", 0) or 0)
    if attempts >= policy["attempts_retry_max"]:
        record["status"] = "failed"
        record["reason_code"] = "retry_exhausted"
        record["last_error_code"] = "retry_exhausted"
        return

    try:
        existing_id = _lookup_by_origin(
            readonly_client,
            record["originator_id"],
            record["origin_id"],
        )
    except BitrixConnectorError as exc:
        record["status"] = "pending"
        record["uncertain"] = True
        record["attempts"] = attempts + 1
        record["last_error_code"] = "idempotency_lookup_failed"
        logger.warning(
            "ROP write-back idempotency lookup failed: identity=%s reason=%s",
            record["identity"],
            exc,
        )
        return

    if existing_id is not None:
        record["status"] = "recovered"
        record["remote_entity_type_id"] = LEAD_ENTITY_TYPE_ID
        record["remote_entity_id"] = existing_id
        record["uncertain"] = False
        record["last_error_code"] = None
        logger.info(
            "ROP write-back recovered existing lead: identity=%s remote_entity_id=%s",
            record["identity"],
            existing_id,
        )
        return

    fields = {
        "TITLE": _build_lead_title(record),
        "STAGE_ID": record.get("stage_id"),
        "ASSIGNED_BY_ID": record.get("responsible_user_id"),
        "ORIGINATOR_ID": record["originator_id"],
        "ORIGIN_ID": record["origin_id"],
    }
    sender_name = record.get("sender_name") or ""
    if sender_name:
        fields["NAME"] = sender_name
    if policy.get("source_id"):
        fields["SOURCE_ID"] = policy["source_id"]
    sender_email = record.get("sender_email") or ""
    if sender_email:
        fields["fm"] = [
            {
                "typeId": "EMAIL",
                "value": sender_email,
                "valueType": "WORK",
            }
        ]

    try:
        item_id = write_client.add_lead(fields)
    except BitrixConnectorError as exc:
        error_code, retryable, uncertain = _classify_write_failure(exc)
        record["attempts"] = attempts + 1
        record["last_error_code"] = error_code
        if uncertain:
            record["status"] = "uncertain"
            record["uncertain"] = True
            logger.warning(
                "ROP write-back uncertain outcome: identity=%s error_code=%s",
                record["identity"],
                error_code,
            )
        elif retryable:
            record["status"] = "pending"
            record["uncertain"] = False
            logger.warning(
                "ROP write-back retryable failure: identity=%s error_code=%s",
                record["identity"],
                error_code,
            )
        else:
            record["status"] = "failed"
            record["uncertain"] = False
            record["reason_code"] = error_code
            logger.error(
                "ROP write-back terminal failure: identity=%s error_code=%s",
                record["identity"],
                error_code,
            )
        return

    record["status"] = "created"
    record["remote_entity_type_id"] = LEAD_ENTITY_TYPE_ID
    record["remote_entity_id"] = item_id
    record["uncertain"] = False
    record["last_error_code"] = None
    logger.info(
        "ROP write-back lead created: identity=%s remote_entity_id=%s stage_id=%s "
        "responsible_user_id=%s",
        record["identity"],
        item_id,
        record.get("stage_id"),
        record.get("responsible_user_id"),
    )


def execute_writeback_pending(
    storage_dir: Path,
    run_id: str,
    settings: dict,
    logger: logging.Logger,
    dry_run_override: bool | None = None,
    retry_failed: bool = False,
) -> dict[str, Any]:
    state = _load_state(storage_dir)
    policy = _writeback_policy(settings)
    effective_dry_run = (
        policy["dry_run"] if dry_run_override is None else bool(dry_run_override)
    )
    state["policy_snapshot"] = {
        "enabled": policy["enabled"],
        "dry_run": policy["dry_run"],
        "webhook_env": policy["webhook_env"],
        "attempts_retry_max": policy["attempts_retry_max"],
        "stages": policy["stages"],
        "email_attach": policy["email_attach"],
        "source_id": policy["source_id"],
    }

    events = state.get("events", {})
    if not events:
        logger.info("ROP write-back execute: no planned events")
        return {
            "run_id": run_id,
            "status": "noop",
            "writes_performed": 0,
            "policy": policy,
            "aggregate": _aggregate_records([]),
        }

    previous_records = {
        str(identity): json.dumps(record, sort_keys=True, ensure_ascii=False)
        for identity, record in events.items()
        if isinstance(record, dict)
    }

    def persist_and_refresh() -> None:
        _save_state(storage_dir, state)
        _refresh_changed_run_projections(
            storage_dir, state, previous_records, logger
        )

    if not policy["enabled"]:
        for record in events.values():
            if record.get("status") in ("planned", "pending", "uncertain"):
                record["status"] = "deferred"
                record["reason_code"] = "writeback_disabled"
                record["updated_at_utc"] = _utc_now()
        persist_and_refresh()
        logger.info("ROP write-back execute: disabled, zero writes: run_id=%s", run_id)
        return {
            "run_id": run_id,
            "status": "disabled",
            "writes_performed": 0,
            "policy": policy,
            "aggregate": _aggregate_records(list(events.values())),
        }

    if effective_dry_run:
        persist_and_refresh()
        logger.info(
            "ROP write-back execute: dry-run, zero writes: run_id=%s", run_id
        )
        return {
            "run_id": run_id,
            "status": "dry_run",
            "writes_performed": 0,
            "policy": policy,
            "aggregate": _aggregate_records(list(events.values())),
        }

    if not policy["credential_present"]:
        for record in events.values():
            if record.get("status") in ("planned", "pending", "uncertain"):
                record["status"] = "deferred"
                record["reason_code"] = "write_credential_missing"
                record["updated_at_utc"] = _utc_now()
        persist_and_refresh()
        logger.warning(
            "ROP write-back execute: write credential missing, zero writes: run_id=%s",
            run_id,
        )
        return {
            "run_id": run_id,
            "status": "credential_missing",
            "writes_performed": 0,
            "policy": policy,
            "aggregate": _aggregate_records(list(events.values())),
        }

    if retry_failed:
        rearmed = 0
        for record in events.values():
            if (
                record.get("outcome") == "create_lead"
                and record.get("status") == "failed"
                and record.get("reason_code") == "retry_exhausted"
            ):
                record["status"] = "pending"
                record["attempts"] = 0
                record["uncertain"] = False
                record["last_error_code"] = None
                record["reason_code"] = None
                rearmed += 1
            elif (
                record.get("outcome") == "attach_existing"
                and record.get("status") == "failed"
                and record.get("reason_code") == "retry_exhausted"
                and record.get("last_attach_error_code") == "retry_exhausted"
            ):
                record["status"] = "pending"
                record["attach_attempts"] = 0
                record["uncertain"] = False
                record["last_attach_error_code"] = None
                record["reason_code"] = None
                rearmed += 1
            elif (
                record.get("outcome") == "create_lead"
                and record.get("status") in ("created", "recovered")
                and not record.get("email_activity_id")
                and record.get("last_attach_error_code") == "retry_exhausted"
            ):
                record["attach_attempts"] = 0
                record["email_attachment_status"] = "pending"
                record["last_attach_error_code"] = None
                rearmed += 1
        if rearmed:
            logger.info(
                "ROP write-back retry-failed: re-armed %d exhausted write-back records: "
                "run_id=%s",
                rearmed,
                run_id,
            )

    create_records = [
        record
        for record in events.values()
        if record.get("outcome") == "create_lead"
        and record.get("status") in ("planned", "pending", "uncertain")
    ]
    attach_records = [
        record
        for record in events.values()
        if record.get("outcome") == "attach_existing"
        and record.get("status") in ("planned", "pending", "uncertain")
    ]

    for record in create_records:
        stage_id = record.get("stage_id")
        if not isinstance(stage_id, str) or not stage_id.strip():
            record["status"] = "deferred"
            record["reason_code"] = "stage_not_configured"
            record["updated_at_utc"] = _utc_now()

    try:
        readonly_client = build_bitrix_client(settings, logger=logger)
        invalid_stages = _validate_stages_against_bitrix(
            readonly_client, policy["stages"], logger
        )
    except BitrixConnectorError as exc:
        invalid_stages = None
        logger.warning(
            "ROP write-back stage validation degraded: run_id=%s reason=%s",
            run_id,
            exc,
        )
    if invalid_stages is not None and invalid_stages:
        for record in create_records:
            record["status"] = "deferred"
            record["reason_code"] = "stage_validation_failed"
            record["updated_at_utc"] = _utc_now()
        persist_and_refresh()
        logger.error(
            "ROP write-back stage validation failed, zero writes: run_id=%s "
            "invalid_stages=%s",
            run_id,
            ",".join(invalid_stages),
        )
        return {
            "run_id": run_id,
            "status": "stage_validation_failed",
            "writes_performed": 0,
            "policy": policy,
            "invalid_stages": invalid_stages,
            "aggregate": _aggregate_records(list(events.values())),
        }
    if invalid_stages is None:
        for record in create_records:
            record["status"] = "pending"
            record["uncertain"] = False
            record["last_error_code"] = "stage_validation_degraded"
            record["updated_at_utc"] = _utc_now()
        persist_and_refresh()
        return {
            "run_id": run_id,
            "status": "stage_validation_degraded",
            "writes_performed": 0,
            "policy": policy,
            "aggregate": _aggregate_records(list(events.values())),
        }

    try:
        write_client = build_bitrix_write_client(settings, logger=logger)
    except BitrixConnectorError as exc:
        for record in create_records + attach_records:
            record["status"] = "deferred"
            record["reason_code"] = "write_credential_invalid"
            record["updated_at_utc"] = _utc_now()
        persist_and_refresh()
        logger.error(
            "ROP write-back write client unavailable, zero writes: run_id=%s reason=%s",
            run_id,
            exc,
        )
        return {
            "run_id": run_id,
            "status": "write_client_unavailable",
            "writes_performed": 0,
            "policy": policy,
            "aggregate": _aggregate_records(list(events.values())),
        }

    writes_performed = 0
    for record in create_records:
        if record.get("status") in ("deferred", "failed"):
            continue
        before = record.get("remote_entity_id")
        _execute_create_lead(
            record,
            policy,
            readonly_client,
            write_client,
            logger,
        )
        if (
            record.get("status") == "created"
            and record.get("remote_entity_id")
            and before is None
        ):
            writes_performed += 1
        record["updated_at_utc"] = _utc_now()

    for record in events.values():
        if record.get("outcome") == "attach_existing":
            if record.get("status") not in ("planned", "pending", "uncertain"):
                continue
        elif (
            record.get("outcome") == "create_lead"
            and record.get("status") in ("created", "recovered")
            and not record.get("email_activity_id")
            and record.get("email_attachment_required") is True
            and record.get("email_attachment_status") in ("pending", "uncertain")
        ):
            pass
        else:
            continue
        if _execute_email_attachment(
            record,
            policy,
            readonly_client,
            write_client,
            logger,
        ):
            writes_performed += 1
        record["updated_at_utc"] = _utc_now()

    persist_and_refresh()

    logger.info(
        "ROP write-back execute finished: run_id=%s writes=%d status_counts=%s",
        run_id,
        writes_performed,
        _aggregate_records(list(events.values()))["status_counts"],
    )

    return {
        "run_id": run_id,
        "status": "executed",
        "writes_performed": writes_performed,
        "policy": policy,
        "aggregate": _aggregate_records(list(events.values())),
    }
