from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from beeagent_module.core.attachment_extraction import build_attachment_extraction
from beeagent_module.core.input_source import (
    InputSourceError,
    load_rop_source,
    select_rop_sources,
)
from beeagent_module.core.mailbox_selection import (
    build_mailbox_selection_artifact,
    write_mailbox_selection_artifact,
)
from beeagent_module.core.module_registry import ModuleRegistry, build_registry
from beeagent_module.core.module_runtime import execute_module_case
from beeagent_module.core.rop_ai_assist import (
    run_ai_assist_for_event,
    write_ai_assist_artifacts,
)
from beeagent_module.core.runtime_context import generate_run_id, generate_session_id
from beeagent_module.core.thread_index import (
    build_thread_context,
    build_thread_index,
    write_thread_artifacts,
)

AI_ASSIST_MERGE_CASE_TYPE = "ai_assist_merge"
_AI_MERGE_EVENT_KEYS = frozenset(
    {
        "event_id",
        "source_id",
        "source_type",
        "source_role",
        "source_display_name",
        "client_id",
        "sender",
        "subject",
        "case_type",
        "case_subtype",
        "priority",
        "reason_code",
        "confidence",
        "is_fallback",
        "recommended_queue",
        "should_rop_see",
        "correct_action",
        "thread_context_ref",
        "attachment_preview_available",
        "attachment_extraction_status",
    }
)
_AI_MERGED_OUTPUT_KEYS = frozenset(
    {
        "case_type",
        "case_subtype",
        "priority",
        "reason_code",
        "confidence",
        "recommended_queue",
        "should_rop_see",
        "correct_action",
    }
)


def run_rop_operator_case(
    settings: dict,
    storage_dir: Path,
    logger: logging.Logger,
    module_id: str = "beeagent-rop",
    case_type: str = "lead_classification",
    payload: dict[str, Any] | None = None,
    run_id: str | None = None,
    session_id: str | None = None,
    registry: ModuleRegistry | None = None,
) -> dict[str, Any]:
    effective_run_id = run_id or generate_run_id()
    effective_session_id = session_id or generate_session_id()

    if registry is None:
        registry = build_registry(settings=settings, logger=logger)

    if payload is None:
        raise RuntimeError("ROP operator payload is required")
    effective_payload = payload
    run_dir = storage_dir / "runs" / effective_run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    module_status = "error"
    module_summary = "module execution failed"
    operator_status = "degraded"

    try:
        result = execute_module_case(
            registry=registry,
            module_id=module_id,
            case_type=case_type,
            payload=effective_payload,
            storage_dir=storage_dir,
            logger=logger,
            run_id=effective_run_id,
            session_id=effective_session_id,
        )
        module_status = result.status
        module_summary = result.summary
        operator_status = "ok" if result.status == "ok" else "degraded"
    except RuntimeError as exc:
        module_summary = str(exc)

    module_dir = run_dir / f"module-{module_id}"
    artifact_refs = _collect_artifact_refs(
        storage_dir=storage_dir,
        module_dir=module_dir,
        case_type=case_type,
    )

    operator_summary = {
        "run_id": effective_run_id,
        "session_id": effective_session_id,
        "module_id": module_id,
        "case_type": case_type,
        "status": operator_status,
        "module_status": module_status,
        "summary": module_summary,
        "artifact_refs": artifact_refs,
    }

    operator_summary_path = run_dir / "operator_summary.json"
    operator_ref = operator_summary_path.relative_to(storage_dir).as_posix()
    operator_summary["artifact_refs"] = [*artifact_refs, operator_ref]

    operator_summary_path.write_text(
        json.dumps(operator_summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    operator_text = _build_operator_text(
        run_id=effective_run_id,
        module_id=module_id,
        case_type=case_type,
        status=operator_status,
        module_status=module_status,
        summary=module_summary,
        artifact_refs=operator_summary["artifact_refs"],
    )

    logger.info(
        "rop operator flow finished: run_id=%s module_id=%s case_type=%s status=%s module_status=%s",
        effective_run_id,
        module_id,
        case_type,
        operator_status,
        module_status,
    )

    return {
        **operator_summary,
        "operator_text": operator_text,
    }


def _collect_artifact_refs(
    storage_dir: Path,
    module_dir: Path,
    case_type: str,
) -> list[str]:
    refs: list[str] = []
    module_result_path = module_dir / "module_result.json"
    case_result_path = module_dir / f"{case_type}_result.json"

    for path in (module_result_path, case_result_path):
        if path.exists():
            refs.append(path.relative_to(storage_dir).as_posix())

    return refs


def _build_operator_text(
    run_id: str,
    module_id: str,
    case_type: str,
    status: str,
    module_status: str,
    summary: str,
    artifact_refs: list[str],
) -> str:
    artifacts_text = "\n".join(f"- {item}" for item in artifact_refs) or "- none"
    return (
        "ROP operator run v0\n"
        f"run_id: {run_id}\n"
        f"module_id: {module_id}\n"
        f"case_type: {case_type}\n"
        f"status: {status}\n"
        f"module_status: {module_status}\n"
        f"summary: {summary}\n"
        f"artifacts:\n{artifacts_text}"
    )


def _build_batch_operator_text(
    run_id: str,
    module_id: str,
    case_type: str,
    status: str,
    module_status: str,
    summary: str,
    artifact_refs: list[str],
    source: dict | None,
) -> str:
    artifacts_text = "\n".join(f"- {item}" for item in artifact_refs) or "- none"
    source_block = ""
    if isinstance(source, dict):
        if source.get("mode"):
            source_block = (
                f"source_mode: {source.get('mode', '?')}\n"
                f"source_count: {source.get('source_count', '?')}\n"
                f"loaded_sources: {source.get('loaded_source_count', '?')}\n"
                f"degraded_sources: {source.get('degraded_source_count', '?')}\n"
                f"fetched_count: {source.get('fetched_count', '?')}\n"
                f"loaded_count: {source.get('loaded_count', '?')}\n"
                f"malformed_count: {source.get('malformed_count', '?')}\n"
                f"status_reason: {source.get('reason', '?')}\n"
            )
        else:
            source_block = (
                f"source_id: {source.get('source_id', '?')}\n"
                f"source_type: {source.get('source_type', '?')}\n"
                f"source_role: {source.get('source_role', '?')}\n"
                f"source_display_name: {source.get('source_display_name', '?')}\n"
                f"client_id: {source.get('client_id', '?')}\n"
                f"mailbox_folder: {source.get('mailbox_folder', '?')}\n"
                f"loaded_items: {source.get('loaded_item_count', '?')}\n"
                f"fetched_count: {source.get('fetched_count', '?')}\n"
                f"malformed_count: {source.get('malformed_count', '?')}\n"
                f"period: {source.get('period', '?')}\n"
            )
    else:
        source_block = "source: null\n"
    return (
        "ROP batch run v0\n"
        f"run_id: {run_id}\n"
        f"module_id: {module_id}\n"
        f"case_type: {case_type}\n"
        f"status: {status}\n"
        f"module_status: {module_status}\n"
        f"summary: {summary}\n"
        f"{source_block}"
        f"artifacts:\n{artifacts_text}"
    )


def _classify_normalized_events(
    events: list[dict[str, Any]],
    registry: ModuleRegistry,
    module_id: str,
    storage_dir: Path,
    logger: logging.Logger,
    run_id: str,
    session_id: str,
    source_id: str | None,
    thread_context: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    classified_events: list[dict[str, Any]] = []
    classified_count = 0
    already_classified_count = 0
    failed_count = 0

    context_map: dict[str, dict[str, Any]] = {}
    if thread_context and isinstance(thread_context, dict):
        for ctx in thread_context.get("contexts", []):
            if isinstance(ctx, dict):
                eid = ctx.get("event_id", "")
                if eid:
                    context_map[eid] = ctx

    for index, event in enumerate(events):
        if "case_type" in event and "confidence" in event:
            classified_events.append(
                _attach_existing_classification_trace(
                    classified_event=event,
                    source_id=source_id,
                )
            )
            already_classified_count += 1
            logger.debug(
                "event already classified: run_id=%s event_index=%d event_id=%s",
                run_id,
                index,
                event.get("event_id", "?"),
            )
            continue

        try:
            logger.debug(
                "classifying event: run_id=%s event_index=%d event_id=%s",
                run_id,
                index,
                event.get("event_id", "?"),
            )

            filtered_event = _filter_event_for_module(event)

            event_id = event.get("event_id", "")
            event_tc = context_map.get(event_id)
            if event_tc:
                filtered_event["thread_context"] = {
                    "thread_id": event_tc.get("thread_id", ""),
                    "previous_event_ids": event_tc.get("previous_event_ids", []),
                    "previous_case_type": event_tc.get("previous_case_type", ""),
                    "previous_case_subtype": event_tc.get("previous_case_subtype", ""),
                    "participant_overlap": event_tc.get("participant_overlap", False),
                    "thread_context_confidence": event_tc.get(
                        "thread_context_confidence", 0.0
                    ),
                    "reply_or_forward": event_tc.get("reply_or_forward", False),
                }

            result = execute_module_case(
                registry=registry,
                module_id=module_id,
                case_type="lead_classification",
                payload=filtered_event,
                storage_dir=storage_dir,
                logger=logger,
                run_id=run_id,
                session_id=session_id,
            )

            if result.status == "ok" and result.data:
                classified_event = _attach_classification_trace(
                    classified_event=result.data,
                    source_event=event,
                    source_id=source_id,
                )
                classified_events.append(classified_event)
                classified_count += 1
                logger.debug(
                    "event classified successfully: run_id=%s event_id=%s case_type=%s",
                    run_id,
                    event.get("event_id"),
                    classified_event.get("case_type"),
                )
            else:
                fallback = _make_fallback_event(event, source_id)
                classified_events.append(fallback)
                failed_count += 1
                logger.warning(
                    "event classification returned non-ok status: run_id=%s event_id=%s result_status=%s",
                    run_id,
                    event.get("event_id"),
                    result.status,
                )

        except Exception as exc:
            fallback = _make_fallback_event(event, source_id)
            classified_events.append(fallback)
            failed_count += 1
            logger.warning(
                "event classification failed with exception: run_id=%s event_id=%s exception_type=%s",
                run_id,
                event.get("event_id"),
                type(exc).__name__,
            )

    classification_diagnostics = {
        "normalized_count": len(events),
        "classified_count": classified_count + already_classified_count,
        "classification_failed_count": failed_count,
    }

    logger.info(
        "batch classification finished: run_id=%s normalized=%d classified=%d already_classified=%d failed=%d",
        run_id,
        len(events),
        classified_count,
        already_classified_count,
        failed_count,
    )

    return classified_events, classification_diagnostics


def _attach_existing_classification_trace(
    classified_event: dict[str, Any],
    source_id: str | None,
) -> dict[str, Any]:
    enriched = dict(classified_event)

    if not enriched.get("original_event_id"):
        enriched["original_event_id"] = enriched.get("event_id")

    if not enriched.get("source_id"):
        enriched["source_id"] = source_id

    for key in (
        "source_type",
        "source_role",
        "source_display_name",
        "client_id",
    ):
        if key not in enriched:
            enriched[key] = None

    if "is_fallback" not in enriched:
        enriched["is_fallback"] = False

    if not enriched.get("reason_code"):
        enriched["reason_code"] = "preclassified_input"

    return enriched


def _make_fallback_event(
    event: dict[str, Any],
    source_id: str | None,
) -> dict[str, Any]:
    return {
        "event_id": event.get("event_id"),
        "source_id": event.get("source_id") or source_id,
        "source_type": event.get("source_type"),
        "source_role": event.get("source_role"),
        "source_display_name": event.get("source_display_name"),
        "client_id": event.get("client_id"),
        "attachment_extraction_status": event.get("attachment_extraction_status"),
        "attachment_preview_available": event.get("attachment_preview_available"),
        "attachment_text_preview": event.get("attachment_text_preview"),
        "attachment_extraction_refs": event.get("attachment_extraction_refs"),
        "attachment_refusal_reasons": event.get("attachment_refusal_reasons"),
        "case_type": "unknown",
        "priority": "medium",
        "reason_code": "classification_error",
        "confidence": 0.0,
        "is_fallback": True,
        "original_event_id": event.get("event_id"),
        "reasoning": "Per-event classification failed; event was converted to controlled fallback item.",
    }


def _is_blocked_email_attachment(att: dict[str, Any]) -> bool:
    filename = str(att.get("filename") or "").strip().lower()
    content_type = str(att.get("content_type") or "").strip().lower()
    return filename.endswith(".eml") or content_type == "message/rfc822"


def _filter_event_for_module(event: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        "attachments",
        "attachment_extraction_status",
        "attachment_preview_available",
        "attachment_text",
        "attachment_text_preview",
        "attachment_extraction_refs",
        "attachment_refusal_reasons",
        "body",
        "event_id",
        "language_hint",
        "message_id",
        "raw_metadata",
        "received_at",
        "sender",
        "source",
        "subject",
        "thread_id",
    }
    allowed_attachment_keys = {
        "attachment_id",
        "content_id",
        "content_type",
        "filename",
        "is_inline",
        "raw_metadata",
        "size_bytes",
    }

    filtered = {k: v for k, v in event.items() if k in allowed_keys}

    if "attachments" in filtered and isinstance(filtered["attachments"], list):
        normalized_attachments = []
        for att in filtered["attachments"]:
            if not isinstance(att, dict):
                continue
            if _is_blocked_email_attachment(att):
                continue
            normalized_att = {
                k: v for k, v in att.items() if k in allowed_attachment_keys
            }
            if "size" in att and "size_bytes" not in normalized_att:
                size_value = att.get("size")
                if isinstance(size_value, (int, float)):
                    normalized_att["size_bytes"] = size_value
            normalized_attachments.append(normalized_att)
        filtered["attachments"] = normalized_attachments

    if not filtered.get("body"):
        for preview_key in ("body_preview", "text_preview", "attachment_text"):
            preview_value = event.get(preview_key)
            if isinstance(preview_value, str) and preview_value.strip():
                filtered["body"] = preview_value
                break

    return filtered


def _attach_classification_trace(
    classified_event: dict[str, Any],
    source_event: dict[str, Any],
    source_id: str | None,
) -> dict[str, Any]:
    enriched = dict(classified_event)

    if not enriched.get("event_id"):
        enriched["event_id"] = source_event.get("event_id")

    enriched["original_event_id"] = source_event.get("event_id")
    enriched["source_id"] = source_event.get("source_id") or source_id
    enriched["source_type"] = source_event.get("source_type")
    enriched["source_role"] = source_event.get("source_role")
    enriched["source_display_name"] = source_event.get("source_display_name")
    enriched["client_id"] = source_event.get("client_id")

    for key in (
        "attachment_extraction_status",
        "attachment_preview_available",
        "attachment_text_preview",
        "attachment_extraction_refs",
        "attachment_refusal_reasons",
    ):
        if key not in enriched:
            enriched[key] = source_event.get(key)

    return enriched


def _build_source_meta_from_diagnostics(
    source_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source_id": source_diagnostics.get("source_id"),
        "source_type": source_diagnostics.get("source_type"),
        "source_role": source_diagnostics.get("source_role"),
        "source_display_name": source_diagnostics.get("source_display_name"),
        "client_id": source_diagnostics.get("client_id"),
        "authority": source_diagnostics.get("authority"),
        "items_max": source_diagnostics.get("items_max"),
        "mailbox_folder": source_diagnostics.get("mailbox_folder"),
        "fetched_count": source_diagnostics.get("fetched_count"),
        "loaded_count": source_diagnostics.get("loaded_count"),
        "malformed_count": source_diagnostics.get("malformed_count"),
        "status": source_diagnostics.get("status"),
        "reason": source_diagnostics.get("reason"),
    }


def _build_source_meta_from_intake(
    intake_metadata: dict[str, Any],
    source_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source_id": intake_metadata.get("source_id"),
        "source_type": intake_metadata.get("source_type"),
        "source_role": intake_metadata.get("source_role"),
        "source_display_name": intake_metadata.get("source_display_name"),
        "client_id": intake_metadata.get("client_id"),
        "authority": intake_metadata.get("authority"),
        "period": intake_metadata.get("period"),
        "raw_item_count": intake_metadata.get("raw_item_count"),
        "loaded_item_count": intake_metadata.get("loaded_item_count"),
        "fetched_count": source_diagnostics.get("fetched_count"),
        "loaded_count": source_diagnostics.get("loaded_count"),
        "malformed_count": source_diagnostics.get("malformed_count"),
        "mailbox_folder": intake_metadata.get("mailbox_folder"),
        "items_max": intake_metadata.get("items_max"),
        "status": source_diagnostics.get("status"),
        "reason": source_diagnostics.get("reason"),
    }


def _attach_source_metadata_to_event(
    event: dict[str, Any],
    source_meta: dict[str, Any],
) -> dict[str, Any]:
    enriched = dict(event)
    enriched["source_id"] = source_meta.get("source_id")
    enriched["source_type"] = source_meta.get("source_type")
    enriched["source_role"] = source_meta.get("source_role")
    enriched["source_display_name"] = source_meta.get("source_display_name")
    enriched["client_id"] = source_meta.get("client_id")
    return enriched


def _sum_int(values: list[Any]) -> int:
    total = 0
    for value in values:
        if isinstance(value, int):
            total += value
    return total


def run_rop_batch_case(
    settings: dict,
    storage_dir: Path,
    project_root: Path,
    logger: logging.Logger,
    module_id: str = "beeagent-rop",
    case_type: str = "rop_summary",
    run_id: str | None = None,
    session_id: str | None = None,
    registry: ModuleRegistry | None = None,
    mailbox_client_factory: Any | None = None,
    period_override: str | None = None,
    source_id: str | None = None,
    all_sources: bool = False,
) -> dict[str, Any]:

    effective_run_id = run_id or generate_run_id()
    effective_session_id = session_id or generate_session_id()

    run_dir = storage_dir / "runs" / effective_run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    module_status = "error"
    module_summary = "module execution failed"
    operator_status = "degraded"
    artifact_refs: list[str] = []
    source_meta: dict | None = None
    source_rollup: list[dict[str, Any]] = []
    classification_diagnostics: dict[str, Any] = {}
    source_diagnostics: dict[str, Any] = {}
    attachment_extraction_summary: dict[str, Any] | None = None
    thread_context: dict[str, Any] = {}
    enriched_classified: list[dict[str, Any]] = []
    ai_requested_count = 0
    ai_used_count = 0
    ai_invalid_count = 0
    ai_degraded_count = 0
    ai_enabled = False

    try:
        input_sources: list[dict] = settings.get("rop", {}).get("sources", [])
        selected_sources, selection_mode = select_rop_sources(
            input_sources=input_sources,
            source_id=source_id,
            all_sources=all_sources,
        )

        normalized_events: list[dict[str, Any]] = []
        source_diagnostics_items: list[dict[str, Any]] = []
        intake_sources: list[dict[str, Any]] = []
        source_error_messages: list[str] = []

        for selected in selected_sources:
            try:
                events, intake_metadata, source_diag = load_rop_source(
                    source=selected,
                    project_root=project_root,
                    logger=logger,
                    mailbox_client_factory=mailbox_client_factory,
                )
                effective_period = str(
                    period_override or intake_metadata.get("period") or ""
                )
                intake_metadata["period"] = effective_period

                source_meta_item = _build_source_meta_from_intake(
                    intake_metadata=intake_metadata,
                    source_diagnostics=source_diag,
                )
                source_diagnostics_items.append(source_diag)
                intake_sources.append(source_meta_item)

                for event in events:
                    normalized_events.append(
                        _attach_source_metadata_to_event(
                            event=event,
                            source_meta=source_meta_item,
                        )
                    )
            except InputSourceError as exc:
                source_error_messages.append(str(exc))
                degraded_diag = {
                    "source_id": str(selected.get("source_id", "unknown")),
                    "source_type": str(selected.get("source_type", "unknown")),
                    "source_role": str(selected.get("source_role", "")),
                    "client_id": str(selected.get("client_id", "")),
                    "source_display_name": str(selected.get("display_name", "")),
                    "authority": str(selected.get("authority", "")),
                    "mailbox_folder": (
                        selected.get("mailbox", {}).get("folder")
                        if isinstance(selected.get("mailbox"), dict)
                        else None
                    ),
                    "items_max": selected.get("items_max"),
                    "status": "degraded",
                    "reason": "source_load_error",
                    "fetched_count": 0,
                    "loaded_count": 0,
                    "processed_count": 0,
                    "skipped_count": 0,
                    "malformed_count": 0,
                }
                degraded_diag.update(exc.diagnostics)
                degraded_diag["status"] = "degraded"

                source_diagnostics_items.append(degraded_diag)
                intake_sources.append(
                    _build_source_meta_from_diagnostics(degraded_diag)
                )

        source_total = len(source_diagnostics_items)
        loaded_sources = sum(
            1 for item in source_diagnostics_items if item.get("status") == "ok"
        )
        degraded_sources = source_total - loaded_sources
        aggregate_status = "ok" if loaded_sources > 0 else "degraded"
        aggregate_reason = None
        if source_total == 0:
            aggregate_reason = "no_sources_selected"
        elif degraded_sources > 0 and loaded_sources > 0:
            aggregate_reason = "partial_degradation"
        elif loaded_sources == 0:
            aggregate_reason = "all_sources_failed"

        fetched_count = _sum_int(
            [item.get("fetched_count") for item in source_diagnostics_items]
        )
        loaded_count = _sum_int(
            [item.get("loaded_count") for item in source_diagnostics_items]
        )
        malformed_count = _sum_int(
            [item.get("malformed_count") for item in source_diagnostics_items]
        )

        source_diagnostics = {
            "selection_mode": selection_mode,
            "status": aggregate_status,
            "reason": aggregate_reason,
            "aggregate": {
                "source_count": source_total,
                "loaded_source_count": loaded_sources,
                "degraded_source_count": degraded_sources,
                "fetched_count": fetched_count,
                "loaded_count": loaded_count,
                "malformed_count": malformed_count,
            },
            "sources": source_diagnostics_items,
        }

        period_value = str(period_override or "")
        if not period_value:
            for item in intake_sources:
                period_candidate = item.get("period")
                if isinstance(period_candidate, str) and period_candidate:
                    period_value = period_candidate
                    break

        intake_metadata = {
            "selection_mode": selection_mode,
            "period": period_value,
            "raw_item_count": fetched_count,
            "loaded_item_count": loaded_count,
            "fetched_count": fetched_count,
            "loaded_count": loaded_count,
            "malformed_count": malformed_count,
            "source_count": source_total,
            "loaded_source_count": loaded_sources,
            "degraded_source_count": degraded_sources,
            "sources": intake_sources,
        }

        if len(intake_sources) == 1:
            single_source = intake_sources[0]
            source_diagnostics.update(
                {
                    "status": single_source.get("status", aggregate_status),
                    "reason": single_source.get("reason"),
                    "source_id": single_source.get("source_id"),
                    "source_type": single_source.get("source_type"),
                    "source_role": single_source.get("source_role"),
                    "client_id": single_source.get("client_id"),
                    "source_display_name": single_source.get("source_display_name"),
                    "authority": single_source.get("authority"),
                    "mailbox_folder": single_source.get("mailbox_folder"),
                    "items_max": single_source.get("items_max"),
                    "fetched_count": single_source.get("fetched_count"),
                    "loaded_count": single_source.get("loaded_count"),
                    "processed_count": single_source.get("loaded_count"),
                    "malformed_count": single_source.get("malformed_count"),
                }
            )
            intake_metadata.update(
                {
                    "source_id": single_source.get("source_id"),
                    "source_type": single_source.get("source_type"),
                    "source_role": single_source.get("source_role"),
                    "client_id": single_source.get("client_id"),
                    "source_display_name": single_source.get("source_display_name"),
                    "authority": single_source.get("authority"),
                    "mailbox_folder": single_source.get("mailbox_folder"),
                    "items_max": single_source.get("items_max"),
                }
            )
            source_meta = single_source
        else:
            source_meta = {
                "mode": selection_mode,
                "source_count": source_total,
                "loaded_source_count": loaded_sources,
                "degraded_source_count": degraded_sources,
                "fetched_count": fetched_count,
                "loaded_count": loaded_count,
                "malformed_count": malformed_count,
                "status": aggregate_status,
                "reason": aggregate_reason,
            }

        source_rollup = intake_sources

        if loaded_sources == 0:
            error_message = (
                source_error_messages[0]
                if source_error_messages
                else ("all selected sources failed")
            )
            raise InputSourceError(error_message, diagnostics=source_diagnostics)

        diagnostics_path = run_dir / "source_diagnostics.json"
        diagnostics_path.write_text(
            json.dumps(source_diagnostics, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        artifact_refs.append(diagnostics_path.relative_to(storage_dir).as_posix())

        intake_path = run_dir / "intake_metadata.json"
        intake_path.write_text(
            json.dumps(intake_metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        artifact_refs.append(intake_path.relative_to(storage_dir).as_posix())
        logger.info(
            "intake_metadata written: run_id=%s loaded_items=%d source_count=%d mode=%s",
            effective_run_id,
            intake_metadata["loaded_item_count"],
            source_total,
            selection_mode,
        )

        normalized_path = run_dir / "normalized_events.json"
        rop_settings = settings.get("rop")
        if not isinstance(rop_settings, dict):
            raise RuntimeError("Invalid settings.rop, expected mapping")
        attachment_settings = rop_settings.get("attachments")
        if not isinstance(attachment_settings, dict):
            raise RuntimeError("Invalid settings.rop.attachments, expected mapping")

        extraction_artifact, normalized_events = build_attachment_extraction(
            run_id=effective_run_id,
            events=normalized_events,
            attachment_settings=attachment_settings,
        )

        attachment_extraction_path = run_dir / "attachment_extraction.json"
        attachment_extraction_path.write_text(
            json.dumps(extraction_artifact, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        artifact_refs.append(
            attachment_extraction_path.relative_to(storage_dir).as_posix()
        )
        attachment_extraction_summary = {
            "status": extraction_artifact.get("status"),
            "aggregate": extraction_artifact.get("aggregate", {}),
        }

        normalized_path.write_text(
            json.dumps(normalized_events, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        artifact_refs.append(normalized_path.relative_to(storage_dir).as_posix())
        logger.info(
            "normalized_events written: run_id=%s events=%d",
            effective_run_id,
            len(normalized_events),
        )

        mailbox_selection_sources = []
        for s_item in source_diagnostics_items:
            if s_item.get("source_type") == "mailbox_readonly":
                msgs = [
                    {
                        "source_message_id": str(idx),
                        "internal_date": ev.get("date") or ev.get("received_at"),
                        "message_id": ev.get("message_id", ""),
                        "subject": (ev.get("subject") or "")[:200],
                        "_date_fallback": ev.get("_date_fallback", False),
                    }
                    for idx, ev in enumerate(normalized_events)
                    if ev.get("source_id") == s_item.get("source_id")
                ]
                mailbox_selection_sources.append(
                    {
                        "source_id": s_item.get("source_id", ""),
                        "items_max": s_item.get("items_max", 0),
                        "total_available": s_item.get("fetched_count", 0),
                        "messages": msgs,
                    }
                )

        selection_artifact = build_mailbox_selection_artifact(
            run_id=effective_run_id,
            sources=mailbox_selection_sources,
            logger=logger,
        )
        selection_ref = write_mailbox_selection_artifact(
            storage_dir=storage_dir,
            run_id=effective_run_id,
            artifact=selection_artifact,
            logger=logger,
        )
        artifact_refs.append(str(selection_ref.relative_to(storage_dir)))

        if registry is None:
            registry = build_registry(settings=settings, logger=logger)

        thread_index = build_thread_index(
            events=normalized_events,
            logger=logger,
        )
        thread_context = build_thread_context(
            events=normalized_events,
            thread_index=thread_index,
            classified_events=None,
            logger=logger,
        )
        thread_refs = write_thread_artifacts(
            storage_dir=storage_dir,
            run_id=effective_run_id,
            thread_index=thread_index,
            thread_context=thread_context,
            logger=logger,
        )
        artifact_refs.extend(thread_refs)

        classified_events, classification_diagnostics = _classify_normalized_events(
            events=normalized_events,
            registry=registry,
            module_id=module_id,
            storage_dir=storage_dir,
            logger=logger,
            run_id=effective_run_id,
            session_id=effective_session_id,
            source_id=None,
            thread_context=thread_context,
        )

        enriched_classified = _enrich_classified_events(
            classified_events=classified_events,
            thread_context=thread_context,
        )

        ai_cfg = settings.get("rop", {}).get("ai_assist", {})
        ai_enabled = ai_cfg.get("enabled", False) if isinstance(ai_cfg, dict) else False

        ai_requests: list[dict[str, Any]] = []
        ai_decisions: list[dict[str, Any]] = []
        ai_results: list[dict[str, Any]] = []

        if ai_enabled:
            min_conf = float(ai_cfg["ai_confidence_min"])
            events_max = int(ai_cfg["events_max"])

            eligible_events = [
                e
                for e in enriched_classified
                if _is_event_eligible_for_ai_assist(e, min_conf)
            ]
            eligible_events = eligible_events[:events_max]
            ai_requested_count = len(eligible_events)

            for event in eligible_events:
                event_id = event.get("event_id", "")
                tc = None
                for ctx in thread_context.get("contexts", []):
                    if isinstance(ctx, dict) and ctx.get("event_id") == event_id:
                        tc = ctx
                        break

                assist_result = run_ai_assist_for_event(
                    event=event,
                    ai_cfg=ai_cfg,
                    thread_context=tc,
                    min_ai_confidence=min_conf,
                    logger=logger,
                )
                ai_requests.append(assist_result.get("request", {}))
                ai_decisions.append(assist_result.get("decision", {}))
                ai_results.append(assist_result.get("result", {}))

                result_data = assist_result.get("result", {})
                status = result_data.get("ai_assist_status", "")
                if status == "ok":
                    merge_result, merged_event = _merge_ai_result_via_public_contract(
                        registry=registry,
                        module_id=module_id,
                        storage_dir=storage_dir,
                        logger=logger,
                        run_id=effective_run_id,
                        session_id=effective_session_id,
                        event=event,
                        ai_result=result_data,
                    )
                    ai_results[-1] = merge_result

                    if (
                        merge_result.get("ai_assist_status") == "ok"
                        and merged_event is not None
                    ):
                        ai_used_count += 1
                        _apply_public_merged_event(event, merged_event)
                    else:
                        ai_degraded_count += 1
                elif status == "invalid":
                    ai_invalid_count += 1
                elif status in ("degraded", "low_confidence", "blocked"):
                    ai_degraded_count += 1

        ai_refs = write_ai_assist_artifacts(
            storage_dir=storage_dir,
            run_id=effective_run_id,
            requests=ai_requests,
            decisions=ai_decisions,
            results=ai_results,
            counters={
                "ai_assist_enabled": 1 if ai_enabled else 0,
                "ai_assist_requested_count": ai_requested_count,
                "ai_assist_used_count": ai_used_count,
                "ai_assist_invalid_count": ai_invalid_count,
                "ai_assist_degraded_count": ai_degraded_count,
            },
            logger=logger,
        )
        artifact_refs.extend(ai_refs)

        classification_diagnostics["ai_assist_enabled"] = ai_enabled
        classification_diagnostics["ai_assist_requested_count"] = ai_requested_count
        classification_diagnostics["ai_assist_used_count"] = ai_used_count
        classification_diagnostics["ai_assist_invalid_count"] = ai_invalid_count
        classification_diagnostics["ai_assist_degraded_count"] = ai_degraded_count

        classified_path = run_dir / "classified_events.json"
        classified_path.write_text(
            json.dumps(enriched_classified, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        artifact_refs.append(classified_path.relative_to(storage_dir).as_posix())
        logger.info(
            "classified_events written: run_id=%s events=%d classified=%d failed=%d ai_requested=%d",
            effective_run_id,
            len(normalized_events),
            classification_diagnostics["classified_count"],
            classification_diagnostics["classification_failed_count"],
            ai_requested_count,
        )

        payload: dict[str, Any] = {
            "period": intake_metadata.get("period", ""),
            "events": enriched_classified,
        }

        result = execute_module_case(
            registry=registry,
            module_id=module_id,
            case_type=case_type,
            payload=payload,
            storage_dir=storage_dir,
            logger=logger,
            run_id=effective_run_id,
            session_id=effective_session_id,
        )
        module_status = result.status
        module_summary = result.summary
        operator_status = "ok" if result.status == "ok" else "degraded"

        module_dir = run_dir / f"module-{module_id}"
        artifact_refs.extend(
            _collect_artifact_refs(
                storage_dir=storage_dir,
                module_dir=module_dir,
                case_type=case_type,
            )
        )

        if isinstance(classification_diagnostics, dict):
            classification_diagnostics["latest_n_strategy"] = True
            classification_diagnostics["threaded_event_count"] = (
                len(thread_context.get("contexts", []))
                if isinstance(thread_context, dict)
                else 0
            )
            classification_diagnostics["thread_context_available_count"] = (
                sum(
                    1
                    for e in enriched_classified
                    if isinstance(e, dict) and e.get("thread_context_ref")
                )
                if enriched_classified
                else 0
            )

            case_subtype_counts: dict[str, int] = {}
            recommended_queue_counts: dict[str, int] = {}
            correct_action_counts: dict[str, int] = {}
            for e in enriched_classified:
                if isinstance(e, dict):
                    st = e.get("case_subtype")
                    if isinstance(st, str) and st:
                        case_subtype_counts[st] = case_subtype_counts.get(st, 0) + 1
                    rq = e.get("recommended_queue")
                    if isinstance(rq, str) and rq:
                        recommended_queue_counts[rq] = (
                            recommended_queue_counts.get(rq, 0) + 1
                        )
                    ca = e.get("correct_action")
                    if isinstance(ca, str) and ca:
                        correct_action_counts[ca] = correct_action_counts.get(ca, 0) + 1

            classification_diagnostics["case_subtype_counts"] = case_subtype_counts
            classification_diagnostics["recommended_queue_counts"] = (
                recommended_queue_counts
            )
            classification_diagnostics["correct_action_counts"] = correct_action_counts

    except InputSourceError as exc:
        module_summary = str(exc)
        source_diagnostics = {
            "selection_mode": "unknown",
            "status": "degraded",
            "reason": "source_not_loaded",
            "aggregate": {
                "source_count": 0,
                "loaded_source_count": 0,
                "degraded_source_count": 0,
                "fetched_count": 0,
                "loaded_count": 0,
                "malformed_count": 0,
            },
            "sources": [],
            **exc.diagnostics,
        }
        if source_meta is None:
            source_meta = _build_source_meta_from_diagnostics(source_diagnostics)
            source_rollup = [source_meta]
        logger.warning(
            "rop batch flow degraded: run_id=%s reason=%s",
            effective_run_id,
            exc,
        )
    except RuntimeError as exc:
        module_summary = str(exc)
        if not source_diagnostics:
            source_diagnostics = {
                "selection_mode": "unknown",
                "status": "degraded",
                "reason": "source_selection_error",
                "aggregate": {
                    "source_count": 0,
                    "loaded_source_count": 0,
                    "degraded_source_count": 0,
                    "fetched_count": 0,
                    "loaded_count": 0,
                    "malformed_count": 0,
                },
                "sources": [],
            }
        logger.warning(
            "rop batch flow degraded: run_id=%s reason=%s",
            effective_run_id,
            exc,
        )

    diagnostics_path = run_dir / "source_diagnostics.json"
    diagnostics_path.write_text(
        json.dumps(source_diagnostics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    diagnostics_ref = diagnostics_path.relative_to(storage_dir).as_posix()
    if diagnostics_ref not in artifact_refs:
        artifact_refs.append(diagnostics_ref)

    if isinstance(classification_diagnostics, dict):
        classification_diagnostics.setdefault("latest_n_strategy", False)
        classification_diagnostics.setdefault("threaded_event_count", 0)
        classification_diagnostics.setdefault("thread_context_available_count", 0)
        classification_diagnostics.setdefault("ai_assist_enabled", ai_enabled)
        classification_diagnostics.setdefault(
            "ai_assist_requested_count", ai_requested_count
        )
        classification_diagnostics.setdefault("ai_assist_used_count", ai_used_count)
        classification_diagnostics.setdefault(
            "ai_assist_invalid_count", ai_invalid_count
        )
        classification_diagnostics.setdefault(
            "ai_assist_degraded_count", ai_degraded_count
        )
        classification_diagnostics.setdefault("case_subtype_counts", {})
        classification_diagnostics.setdefault("recommended_queue_counts", {})
        classification_diagnostics.setdefault("correct_action_counts", {})

    operator_summary = {
        "run_id": effective_run_id,
        "session_id": effective_session_id,
        "module_id": module_id,
        "case_type": case_type,
        "status": operator_status,
        "module_status": module_status,
        "summary": module_summary,
        "source": source_meta,
        "sources": source_rollup,
        "classification": classification_diagnostics,
        "attachment_extraction": attachment_extraction_summary,
        "artifact_refs": artifact_refs,
    }

    operator_summary_path = run_dir / "operator_summary.json"
    operator_ref = operator_summary_path.relative_to(storage_dir).as_posix()
    operator_summary["artifact_refs"] = [*artifact_refs, operator_ref]

    operator_summary_path.write_text(
        json.dumps(operator_summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    operator_text = _build_batch_operator_text(
        run_id=effective_run_id,
        module_id=module_id,
        case_type=case_type,
        status=operator_status,
        module_status=module_status,
        summary=module_summary,
        artifact_refs=operator_summary["artifact_refs"],
        source=source_meta,
    )

    logger.info(
        "rop batch flow finished: run_id=%s module_id=%s case_type=%s status=%s module_status=%s",
        effective_run_id,
        module_id,
        case_type,
        operator_status,
        module_status,
    )

    return {
        **operator_summary,
        "operator_text": operator_text,
    }


def _enrich_classified_events(
    classified_events: list[dict[str, Any]],
    thread_context: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    context_map: dict[str, dict[str, Any]] = {}
    if thread_context and isinstance(thread_context, dict):
        for ctx in thread_context.get("contexts", []):
            if isinstance(ctx, dict):
                eid = ctx.get("event_id", "")
                if eid:
                    context_map[eid] = ctx

    for event in classified_events:
        if not isinstance(event, dict):
            enriched.append(event)
            continue
        enriched_event = dict(event)

        enriched_event["case_subtype"] = event.get("case_subtype")
        enriched_event["recommended_queue"] = event.get("recommended_queue")
        enriched_event["should_rop_see"] = event.get("should_rop_see")
        enriched_event["correct_action"] = event.get("correct_action")

        eid = event.get("event_id", "")
        tc = context_map.get(eid)
        enriched_event["thread_context_ref"] = tc.get("thread_id") if tc else None

        enriched.append(enriched_event)

    return enriched


def _is_event_eligible_for_ai_assist(
    event: dict[str, Any],
    min_confidence: float,
) -> bool:
    case_type = event.get("case_type", "")
    is_fallback = event.get("is_fallback", False)
    confidence = event.get("confidence", 1.0)
    if isinstance(confidence, (int, float)):
        confidence = float(confidence)
    else:
        confidence = 1.0

    if is_fallback:
        return True

    eligible_case_types = {"unknown", "existing_deal", "follow_up"}
    if case_type in eligible_case_types:
        return True

    if confidence < min_confidence:
        return True

    confident_types = {"spam", "noise", "new_lead"}
    if case_type in confident_types and confidence >= min_confidence:
        return False

    return True


def _merge_ai_result_via_public_contract(
    registry: ModuleRegistry,
    module_id: str,
    storage_dir: Path,
    logger: logging.Logger,
    run_id: str,
    session_id: str,
    event: dict[str, Any],
    ai_result: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    merge_payload = {
        "event": {
            key: value for key, value in event.items() if key in _AI_MERGE_EVENT_KEYS
        },
        "ai_assist_result": {
            "case_type": ai_result.get("final_case_type"),
            "case_subtype": ai_result.get("final_case_subtype"),
            "recommended_queue": ai_result.get("final_recommended_queue"),
            "correct_action": ai_result.get("final_correct_action"),
            "ai_assist_status": ai_result.get("ai_assist_status"),
            "merge_reason": ai_result.get("merge_reason"),
            "warnings": ai_result.get("warnings", []),
        },
    }

    try:
        merge = execute_module_case(
            registry=registry,
            module_id=module_id,
            case_type=AI_ASSIST_MERGE_CASE_TYPE,
            payload=merge_payload,
            storage_dir=storage_dir,
            logger=logger,
            run_id=run_id,
            session_id=session_id,
        )
    except RuntimeError:
        return _preserve_ai_result_without_merge(
            ai_result,
            "module_contract_unavailable",
        ), None

    if merge.status != "ok" or not isinstance(merge.data, dict):
        return _preserve_ai_result_without_merge(
            ai_result,
            "module_contract_invalid",
        ), None

    merged_event = merge.data.get("event")
    if not isinstance(merged_event, dict):
        merged_event = merge.data.get("merged_event")
    if not isinstance(merged_event, dict):
        merged_event = merge.data

    if not isinstance(merged_event, dict):
        return _preserve_ai_result_without_merge(
            ai_result,
            "module_contract_invalid",
        ), None

    result = dict(ai_result)
    result["ai_assist_used"] = True
    result["ai_assist_status"] = "ok"
    result["merge_reason"] = "public_ai_assist_merge_contract_applied"
    result["warnings"] = list(ai_result.get("warnings", []))

    return result, merged_event


def _preserve_ai_result_without_merge(
    ai_result: dict[str, Any],
    status: str,
) -> dict[str, Any]:
    result = dict(ai_result)
    result["ai_assist_used"] = False
    result["ai_assist_status"] = status
    result["merge_reason"] = (
        f"public_ai_assist_merge_contract_{status}_deterministic_result_preserved"
    )
    result["warnings"] = [
        *list(ai_result.get("warnings", [])),
        f"AI assist merge was not applied ({status}); deterministic result preserved",
    ]
    return result


def _apply_public_merged_event(
    event: dict[str, Any],
    merged_event: dict[str, Any],
) -> None:
    for key in _AI_MERGED_OUTPUT_KEYS:
        if key in merged_event:
            event[key] = merged_event[key]

    event["ai_assist_status"] = "ok"
    event["ai_assist_used"] = True
