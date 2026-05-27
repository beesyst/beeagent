from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from beeagent_module.core.input_source import (
    InputSourceError,
    load_rop_source,
    select_rop_sources,
)
from beeagent_module.core.module_registry import ModuleRegistry, build_registry
from beeagent_module.core.module_runtime import execute_module_case
from beeagent_module.core.runtime_context import generate_run_id, generate_session_id


# Реализация ROP оператора для запуска модульных кейсов и сбора результатов в едином формате
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


# Вспомогательные функции для ROP оператора
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


# Генерация текстового отчета для ROP оператора
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


# Генерация текстового отчета для ROP batch оператора с метаданными источника
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


# Классифицировать нормализованные события через lead_classification модульного кейса
def _classify_normalized_events(
    events: list[dict[str, Any]],
    registry: ModuleRegistry,
    module_id: str,
    storage_dir: Path,
    logger: logging.Logger,
    run_id: str,
    session_id: str,
    source_id: str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    classified_events: list[dict[str, Any]] = []
    classified_count = 0
    already_classified_count = 0
    failed_count = 0

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

            # Filter event to include only fields expected by lead_classification
            filtered_event = _filter_event_for_module(event)

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


# Существующая классификация к событию, если оно уже было классифицировано на этапе нормализации, чтобы сохранить контекст и избежать повторной классификации
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


# Создать fallback item для события, которое не удалось классифицировать
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
        "case_type": "unknown",
        "priority": "medium",
        "reason_code": "classification_error",
        "confidence": 0.0,
        "is_fallback": True,
        "original_event_id": event.get("event_id"),
        "reasoning": "Per-event classification failed; event was converted to controlled fallback item.",
    }


# Хелпер: определение blocked email attachment
def _is_blocked_email_attachment(att: dict[str, Any]) -> bool:
    filename = str(att.get("filename") or "").strip().lower()
    content_type = str(att.get("content_type") or "").strip().lower()
    return filename.endswith(".eml") or content_type == "message/rfc822"


# Фильтровать событие до полей, поддерживаемых модулем
def _filter_event_for_module(event: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        "attachments",
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


# Трассировка классификации к исходному событию для сохранения контекста и связи между этапами обработки
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

    return enriched


# Сбор source metadata для operator_summary из degraded diagnostics
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


# Сбор source metadata для operator_summary из intake metadata и diagnostics для более полной информации о источнике
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


# Метаданные источника к каждому событию для сохранения контекста и возможности анализа по источникам на этапе классификации и в модульных кейсах
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


# Суммирование числовых полей с безопасной обработкой нечисловых значений для агрегации статистики по источникам
def _sum_int(values: list[Any]) -> int:
    total = 0
    for value in values:
        if isinstance(value, int):
            total += value
    return total


# Запуск ROP source handoff: загрузка configured source, нормализация событий и dispatch в модуль
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
    classification_diagnostics: dict[str, Any] | None = None
    source_diagnostics: dict[str, Any] = {}

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

        # Classify each normalized event through lead_classification case
        if registry is None:
            registry = build_registry(settings=settings, logger=logger)

        classified_events, classification_diagnostics = _classify_normalized_events(
            events=normalized_events,
            registry=registry,
            module_id=module_id,
            storage_dir=storage_dir,
            logger=logger,
            run_id=effective_run_id,
            session_id=effective_session_id,
            source_id=None,
        )

        classified_path = run_dir / "classified_events.json"
        classified_path.write_text(
            json.dumps(classified_events, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        artifact_refs.append(classified_path.relative_to(storage_dir).as_posix())
        logger.info(
            "classified_events written: run_id=%s events=%d classified=%d failed=%d",
            effective_run_id,
            len(normalized_events),
            classification_diagnostics["classified_count"],
            classification_diagnostics["classification_failed_count"],
        )

        payload: dict[str, Any] = {
            "period": intake_metadata.get("period", ""),
            "events": classified_events,
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
