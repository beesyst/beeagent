from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CURRENT_STATE_FILENAME = "rop_current_state.json"
BITRIX_RECONCILIATION_FILENAME = "bitrix_reconciliation.json"


def build_rop_current_state(
    storage_dir: Path,
    run_id: str,
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

    warnings: list[dict[str, Any]] = []
    artifact_refs: list[str] = []

    normalized_path = run_dir / "normalized_events.json"
    if not normalized_path.exists():
        warnings.append(
            {
                "code": "missing_artifact",
                "artifact": "normalized_events.json",
                "message": "normalized_events.json is missing; KPI will be incomplete.",
            }
        )
        normalized_events: list[dict] = []
    else:
        try:
            normalized_events = _read_json_list(normalized_path)
            artifact_refs.append(str(normalized_path.relative_to(storage_dir)))
        except (json.JSONDecodeError, OSError) as exc:
            warnings.append(
                {
                    "code": "malformed_artifact",
                    "artifact": "normalized_events.json",
                    "message": f"Failed to read normalized_events.json: {exc}",
                }
            )
            normalized_events = []

    classified_path = run_dir / "classified_events.json"
    if not classified_path.exists():
        warnings.append(
            {
                "code": "missing_artifact",
                "artifact": "classified_events.json",
                "message": "classified_events.json is missing; KPI will be incomplete.",
            }
        )
        classified_events: list[dict] = []
    else:
        try:
            classified_events = _read_json_list(classified_path)
            artifact_refs.append(str(classified_path.relative_to(storage_dir)))
        except (json.JSONDecodeError, OSError) as exc:
            warnings.append(
                {
                    "code": "malformed_artifact",
                    "artifact": "classified_events.json",
                    "message": f"Failed to read classified_events.json: {exc}",
                }
            )
            classified_events = []

    source_diag_path = run_dir / "source_diagnostics.json"
    source_diag: dict | None = None
    if source_diag_path.exists():
        try:
            source_diag = _read_json_dict(source_diag_path)
            artifact_refs.append(str(source_diag_path.relative_to(storage_dir)))
        except (json.JSONDecodeError, OSError) as exc:
            warnings.append(
                {
                    "code": "malformed_artifact",
                    "artifact": "source_diagnostics.json",
                    "message": f"Failed to read source_diagnostics.json: {exc}",
                }
            )

    intake_path = run_dir / "intake_metadata.json"
    intake: dict | None = None
    if intake_path.exists():
        try:
            intake = _read_json_dict(intake_path)
            artifact_refs.append(str(intake_path.relative_to(storage_dir)))
        except (json.JSONDecodeError, OSError) as exc:
            warnings.append(
                {
                    "code": "malformed_artifact",
                    "artifact": "intake_metadata.json",
                    "message": f"Failed to read intake_metadata.json: {exc}",
                }
            )

    bitrix_path = run_dir / BITRIX_RECONCILIATION_FILENAME
    bitrix_reconciliation: dict | None = None
    if bitrix_path.exists():
        try:
            bitrix_reconciliation = _read_json_dict(bitrix_path)
            artifact_refs.append(str(bitrix_path.relative_to(storage_dir)))

            recon_run_id = bitrix_reconciliation.get("run_id")
            if recon_run_id and recon_run_id != run_id:
                warnings.append(
                    {
                        "code": "run_id_mismatch",
                        "artifact": BITRIX_RECONCILIATION_FILENAME,
                        "message": (
                            f"Bitrix reconciliation run_id '{recon_run_id}' "
                            f"does not match current run_id '{run_id}'."
                        ),
                    }
                )

            stale = _check_bitrix_staleness(
                bitrix_path=bitrix_path,
                primary_paths=[
                    normalized_path,
                    classified_path,
                    source_diag_path,
                    intake_path,
                ],
                bitrix_reconciliation=bitrix_reconciliation,
            )
            if stale:
                warnings.append(
                    {
                        "code": "stale_artifact",
                        "artifact": BITRIX_RECONCILIATION_FILENAME,
                        "message": stale,
                    }
                )
        except (json.JSONDecodeError, OSError) as exc:
            warnings.append(
                {
                    "code": "malformed_artifact",
                    "artifact": BITRIX_RECONCILIATION_FILENAME,
                    "message": f"Failed to read {BITRIX_RECONCILIATION_FILENAME}: {exc}",
                }
            )

    client_id = "unknown"
    source_block = _build_source_block(source_diag, intake, normalized_events)
    if source_diag:
        for s in source_diag.get("sources", []):
            if isinstance(s, dict) and s.get("client_id"):
                client_id = s["client_id"]
                break
    if client_id == "unknown" and intake:
        for s in intake.get("sources", []):
            if isinstance(s, dict) and s.get("client_id"):
                client_id = s["client_id"]
                break

    kpi = _build_kpi(
        classified_events,
        normalized_events,
        bitrix_reconciliation,
        source_degraded_count=_int(source_block.get("degraded_source_count", 0)),
    )

    operator_summary_path = run_dir / "operator_summary.json"
    operator_summary: dict | None = None
    if operator_summary_path.exists():
        try:
            operator_summary = _read_json_dict(operator_summary_path)
            artifact_refs.append(str(operator_summary_path.relative_to(storage_dir)))
        except (json.JSONDecodeError, OSError) as exc:
            warnings.append(
                {
                    "code": "malformed_artifact",
                    "artifact": "operator_summary.json",
                    "message": f"Failed to read operator_summary.json: {exc}",
                }
            )

    if isinstance(operator_summary, dict):
        cls = operator_summary.get("classification", {})
        if isinstance(cls, dict):
            kpi["latest_n_strategy"] = cls.get("latest_n_strategy", False)
            kpi["threaded_event_count"] = _int(cls.get("threaded_event_count", 0))
            kpi["thread_context_available_count"] = _int(
                cls.get("thread_context_available_count", 0)
            )
            kpi["case_subtype_counts"] = cls.get("case_subtype_counts", {})
            kpi["recommended_queue_counts"] = cls.get("recommended_queue_counts", {})
            kpi["correct_action_counts"] = cls.get("correct_action_counts", {})
            kpi["ai_assist_enabled"] = cls.get("ai_assist_enabled", False)
            kpi["ai_assist_requested_count"] = _int(
                cls.get("ai_assist_requested_count", 0)
            )
            kpi["ai_assist_used_count"] = _int(cls.get("ai_assist_used_count", 0))
            kpi["ai_assist_invalid_count"] = _int(cls.get("ai_assist_invalid_count", 0))
            kpi["ai_assist_degraded_count"] = _int(
                cls.get("ai_assist_degraded_count", 0)
            )

    queues = _build_queues(classified_events, bitrix_reconciliation)

    current_alias = _determine_current_alias(storage_dir, run_id)

    state: dict[str, Any] = {
        "run_id": run_id,
        "status": "ok",
        "read_only": True,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "client_id": client_id,
        "current_alias": current_alias,
        "source": source_block,
        "kpi": kpi,
        "queues": queues,
        "artifact_refs": sorted(set(artifact_refs)),
        "warnings": warnings,
    }

    return state


def write_current_state(
    storage_dir: Path,
    run_id: str,
    state: dict[str, Any],
    logger: logging.Logger,
) -> None:
    runs_root = (storage_dir / "runs").resolve()
    run_dir = (runs_root / run_id).resolve()

    try:
        run_dir.relative_to(runs_root)
    except ValueError:
        raise ValueError(f"Invalid run_id: path traversal detected for '{run_id}'")

    run_dir.mkdir(parents=True, exist_ok=True)

    state_path = run_dir / CURRENT_STATE_FILENAME
    state_path.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(
        "ROP current-state written: run_id=%s path=%s",
        run_id,
        state_path.relative_to(storage_dir),
    )

    interfaces_dir = storage_dir / "interfaces"
    interfaces_dir.mkdir(parents=True, exist_ok=True)

    current_path = interfaces_dir / "rop_current.json"
    current_path.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(
        "ROP interface artifact updated: %s",
        current_path.relative_to(storage_dir),
    )

    latest_path = interfaces_dir / "rop_latest.json"
    latest_data = {
        "run_id": run_id,
        "current_alias": state.get("current_alias", "unknown"),
        "client_id": state.get("client_id", "unknown"),
        "status": state.get("status", "ok"),
        "generated_at_utc": state.get("generated_at_utc"),
        "kpi": state.get("kpi", {}),
        "source": state.get("source", {}),
    }
    latest_path.write_text(
        json.dumps(latest_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(
        "ROP interface artifact updated: %s",
        latest_path.relative_to(storage_dir),
    )

    index_path = interfaces_dir / "rop_index.json"
    index: list[dict[str, Any]] = []
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
            if not isinstance(index, list):
                index = []
        except json.JSONDecodeError, OSError:
            index = []

    existing_entry = None
    for entry in index:
        if isinstance(entry, dict) and entry.get("run_id") == run_id:
            existing_entry = entry
            break

    index_entry = {
        "run_id": run_id,
        "status": state.get("status", "ok"),
        "client_id": state.get("client_id", "unknown"),
        "generated_at_utc": state.get("generated_at_utc"),
        "current_alias": state.get("current_alias", "unknown"),
    }

    if existing_entry:
        existing_entry.update(index_entry)
    else:
        index.append(index_entry)

    index_path.write_text(
        json.dumps(index, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(
        "ROP interface artifact updated: %s",
        index_path.relative_to(storage_dir),
    )


def _build_source_block(
    source_diag: dict | None,
    intake: dict | None,
    normalized_events: list[dict],
) -> dict[str, Any]:
    if source_diag:
        agg = source_diag.get("aggregate", {})
        return {
            "selection_mode": source_diag.get("selection_mode", "unknown"),
            "source_count": _int(agg.get("source_count", 0)),
            "loaded_source_count": _int(agg.get("loaded_source_count", 0)),
            "degraded_source_count": _int(agg.get("degraded_source_count", 0)),
        }

    if intake:
        return {
            "selection_mode": intake.get("selection_mode", "default"),
            "source_count": _int(intake.get("source_count", 0)),
            "loaded_source_count": _int(intake.get("loaded_source_count", 0)),
            "degraded_source_count": _int(intake.get("degraded_source_count", 0)),
        }

    return {
        "selection_mode": "default",
        "source_count": 0,
        "loaded_source_count": 0,
        "degraded_source_count": 0,
    }


def _build_kpi(
    classified_events: list[dict],
    normalized_events: list[dict],
    bitrix_reconciliation: dict | None,
    source_degraded_count: int,
) -> dict[str, Any]:
    normalized_count = len(normalized_events)
    classified_count = len(classified_events)

    high_priority = sum(
        1
        for c in classified_events
        if isinstance(c, dict) and c.get("priority") == "high"
    )

    needs_manual_review = sum(
        1
        for c in classified_events
        if isinstance(c, dict) and (c.get("is_fallback") or c.get("priority") == "high")
    )

    attachment_count = 0
    attachment_preview_available = 0
    attachment_refused = 0

    for evt in normalized_events:
        if not isinstance(evt, dict):
            continue
        atts = evt.get("attachments")
        if isinstance(atts, list):
            for att in atts:
                if isinstance(att, dict):
                    attachment_count += 1
                    if att.get("preview_available") or att.get(
                        "attachment_preview_available"
                    ):
                        attachment_preview_available += 1
                    if att.get("is_refused"):
                        attachment_refused += 1

    for evt in classified_events:
        if not isinstance(evt, dict):
            continue
        if evt.get("attachment_preview_available"):
            attachment_preview_available += 1
        refusal_reasons = evt.get("attachment_refusal_reasons")
        if refusal_reasons and isinstance(refusal_reasons, list):
            attachment_refused += len(refusal_reasons)

    safe_matched_count = 0
    matched_in_bitrix = 0
    weak_match_count = 0
    lost_in_bitrix = 0
    ambiguous_in_bitrix = 0
    duplicate_candidate_count = 0
    connector_degraded = 0
    skipped_count = 0
    manual_review_count = 0
    unreconciled = classified_count

    if isinstance(bitrix_reconciliation, dict):
        raw_aggregate = bitrix_reconciliation.get("aggregate", {})
        if isinstance(raw_aggregate, dict):
            safe_matched_count = _int(raw_aggregate.get("safe_matched_count", 0))
            matched_in_bitrix = _int(raw_aggregate.get("matched_count", 0))
            weak_match_count = _int(raw_aggregate.get("weak_match_count", 0))
            lost_in_bitrix = _int(raw_aggregate.get("not_found_count", 0))
            ambiguous_in_bitrix = _int(raw_aggregate.get("ambiguous_count", 0))
            duplicate_candidate_count = _int(
                raw_aggregate.get("duplicate_candidate_count", 0)
            )
            connector_degraded = _int(
                raw_aggregate.get("connector_degraded_count", 0)
            ) + _int(raw_aggregate.get("error_count", 0))
            skipped_count = _int(raw_aggregate.get("skipped_count", 0))
            manual_review_count = _int(raw_aggregate.get("manual_review_count", 0))
            unreconciled = max(
                0,
                classified_count
                - matched_in_bitrix
                - weak_match_count
                - lost_in_bitrix
                - ambiguous_in_bitrix
                - duplicate_candidate_count
                - connector_degraded
                - skipped_count,
            )

    return {
        "events_total": max(normalized_count, classified_count),
        "normalized_count": normalized_count,
        "classified_count": classified_count,
        "high_priority": high_priority,
        "needs_manual_review": needs_manual_review,
        "source_degraded": source_degraded_count,
        "attachment_count": attachment_count,
        "attachment_preview_available": attachment_preview_available,
        "attachment_refused": attachment_refused,
        "safe_matched_count": safe_matched_count,
        "matched_in_bitrix": matched_in_bitrix,
        "weak_match_count": weak_match_count,
        "lost_in_bitrix": lost_in_bitrix,
        "ambiguous_in_bitrix": ambiguous_in_bitrix,
        "duplicate_candidate_count": duplicate_candidate_count,
        "connector_degraded": connector_degraded,
        "skipped_count": skipped_count,
        "unreconciled": unreconciled,
        "manual_review_count": manual_review_count,
    }


def _build_queues(
    classified_events: list[dict],
    bitrix_reconciliation: dict | None,
) -> dict[str, list[dict[str, Any]]]:
    lost_in_bitrix: list[dict[str, Any]] = []
    needs_review: list[dict[str, Any]] = []
    high_priority: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    weak_matches: list[dict[str, Any]] = []
    matched: list[dict[str, Any]] = []
    unreconciled: list[dict[str, Any]] = []
    degraded: list[dict[str, Any]] = []

    bitrix_by_event: dict[str, dict] = {}
    if bitrix_reconciliation and isinstance(bitrix_reconciliation, dict):
        items = bitrix_reconciliation.get("items", [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    eid = item.get("event_id", "")
                    if eid:
                        bitrix_by_event[eid] = item

    seen_review: set[str] = set()

    for evt in classified_events:
        if not isinstance(evt, dict):
            continue
        eid = evt.get("event_id", "")
        bitrix_item = bitrix_by_event.get(eid)

        queue_entry = {
            "event_id": eid,
            "case_type": evt.get("case_type", ""),
            "priority": evt.get("priority", ""),
            "is_fallback": bool(evt.get("is_fallback")),
        }

        if bitrix_item:
            match_status = bitrix_item.get("bitrix_match_status", "")
            if match_status.startswith("matched_"):
                matched.append({**queue_entry, "bitrix_status": match_status})
            elif match_status == "not_found":
                lost_in_bitrix.append({**queue_entry, "bitrix_status": match_status})
                if eid not in seen_review:
                    needs_review.append(queue_entry)
                    seen_review.add(eid)
            elif match_status == "weak_match":
                weak_matches.append({**queue_entry, "bitrix_status": match_status})
                if eid not in seen_review:
                    needs_review.append(queue_entry)
                    seen_review.add(eid)
            elif match_status in ("ambiguous", "duplicate_candidate"):
                ambiguous.append({**queue_entry, "bitrix_status": match_status})
                if eid not in seen_review:
                    needs_review.append(queue_entry)
                    seen_review.add(eid)
            elif match_status in ("connector_degraded", "error"):
                degraded.append({**queue_entry, "bitrix_status": match_status})
            elif match_status == "skipped":
                pass
            else:
                unreconciled.append(queue_entry)
        else:
            unreconciled.append(queue_entry)

        if evt.get("priority") == "high":
            high_priority.append(queue_entry)

        if evt.get("is_fallback") or evt.get("priority") == "high":
            if eid not in seen_review:
                needs_review.append(queue_entry)
                seen_review.add(eid)

    return {
        "lost_in_bitrix": lost_in_bitrix,
        "needs_review": needs_review,
        "high_priority": high_priority,
        "ambiguous": ambiguous,
        "weak_matches": weak_matches,
        "matched": matched,
        "unreconciled": unreconciled,
        "degraded": degraded,
    }


def _determine_current_alias(storage_dir: Path, run_id: str) -> str:
    runs_dir = storage_dir / "runs"
    if not runs_dir.is_dir():
        return "explicit"

    run_ids = sorted(
        (d.name for d in runs_dir.iterdir() if d.is_dir()),
        key=lambda n: (runs_dir / n).stat().st_mtime,
        reverse=True,
    )

    if run_ids and run_ids[0] == run_id:
        return "latest"
    return "explicit"


def _check_bitrix_staleness(
    bitrix_path: Path,
    primary_paths: list[Path],
    bitrix_reconciliation: dict,
) -> str | None:
    status = bitrix_reconciliation.get("status", "")
    if status == "degraded":
        return (
            "Bitrix reconciliation reported degraded status; "
            "evidence may be incomplete."
        )

    try:
        bitrix_mtime_ns = bitrix_path.stat().st_mtime_ns
        for primary_path in primary_paths:
            if (
                primary_path.exists()
                and primary_path.stat().st_mtime_ns > bitrix_mtime_ns
            ):
                return (
                    f"Bitrix reconciliation artifact is older than "
                    f"{primary_path.name}; evidence may be stale."
                )
    except OSError as exc:
        return f"Failed to check Bitrix reconciliation freshness: {exc}"

    return None


def _read_json_list(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise json.JSONDecodeError("Expected a JSON list", "", 0)
    return data


def _read_json_dict(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise json.JSONDecodeError("Expected a JSON dict", "", 0)
    return data


def _int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0
