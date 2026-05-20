from __future__ import annotations

import argparse
import csv
import json
import logging
from typing import Any

from beeagent_module.cases.rop_operator import run_rop_batch_case
from beeagent_module.core.paths import get_project_root, get_storage_dir

REVIEW_BODY_SHORT_MAX_CHARS = 500


# CLI handler для ROP
class RopCliError(Exception):
    pass


# Обработчик CLI для ROP: поддерживает команды 'run', 'summary' и 'export-review' с соответствующими аргументами
def handle_rop_run(
    args: argparse.Namespace,
    settings: dict,
    logger: logging.Logger,
) -> None:
    storage_dir = get_storage_dir()
    project_root = get_project_root()

    effective_settings = _apply_source_overrides(
        settings=settings,
        source_id=args.source_id,
        items_max=args.items_max,
        logger=logger,
    )

    run_id = args.run_id

    logger.info(
        "ROP CLI: starting run with overrides source_id=%s items_max=%s",
        args.source_id or "default",
        args.items_max or "default",
    )

    try:
        result = run_rop_batch_case(
            settings=effective_settings,
            storage_dir=storage_dir,
            project_root=project_root,
            logger=logger,
            run_id=run_id,
            period_override=args.period,
        )

        operator_text = result.get("operator_text", "")
        print("\n" + operator_text + "\n")

        effective_run_id = str(result.get("run_id") or run_id or "")
        try:
            tsv_output_path = _export_review_tsv_for_run(
                storage_dir=storage_dir,
                run_id=effective_run_id,
                logger=logger,
            )
        except Exception as exc:
            logger.error(
                "ROP CLI: review TSV export failed for run_id=%s: %s",
                effective_run_id,
                exc,
            )
            raise RopCliError(
                f"ROP run completed but review TSV export failed: {exc}"
            ) from exc

        print("Paste this TSV into Google Sheets for human review.")

        logger.info(
            "ROP CLI: run completed successfully: run_id=%s status=%s",
            result.get("run_id"),
            result.get("status"),
        )

    except Exception as exc:
        logger.error("ROP CLI: run failed: %s", exc)
        raise RopCliError(f"ROP run failed: {exc}") from exc


# Handler для команды 'rop summary': читает operator_summary.json для указанного run_id и выводит читаемый текст в терминал
def handle_rop_summary(
    args: argparse.Namespace,
    logger: logging.Logger,
) -> None:
    storage_dir = get_storage_dir()
    run_id = args.run_id

    summary_path = storage_dir / "runs" / run_id / "operator_summary.json"

    if not summary_path.exists():
        raise RopCliError(
            f"operator_summary.json not found for run_id={run_id} at {summary_path}"
        )

    try:
        with summary_path.open("r", encoding="utf-8") as f:
            summary_data = json.load(f)
    except json.JSONDecodeError as exc:
        raise RopCliError(f"Failed to parse operator_summary.json: {exc}") from exc

    summary_text = _build_summary_text(summary_data)
    print("\n" + summary_text + "\n")

    logger.info("ROP CLI: summary displayed for run_id=%s", run_id)


# Handler для команды 'rop export-review': читает normalized_events.json и classified_events.json для указанного run_id, строит TSV и сохраняет его для загрузки в таблицу для ручного обзора оператором
def handle_rop_export_review(
    args: argparse.Namespace,
    logger: logging.Logger,
) -> None:
    storage_dir = get_storage_dir()
    run_id = args.run_id
    format_type = args.format

    if format_type != "tsv":
        raise RopCliError(
            f"Unsupported format for v1: {format_type}. Only 'tsv' is supported."
        )

    _export_review_tsv_for_run(storage_dir=storage_dir, run_id=run_id, logger=logger)


# Применение CLI-переопределений к конфигурации источников данных для ROP: позволяет указать source_id для выбора конкретного источника
def _apply_source_overrides(
    settings: dict,
    source_id: str | None,
    items_max: int | None,
    logger: logging.Logger,
) -> dict:
    import copy

    effective = copy.deepcopy(settings)

    sources = effective.get("rop", {}).get("sources", [])
    if not sources:
        raise RopCliError("rop.sources is not configured")

    if source_id:
        selected_source: dict[str, Any] | None = None

        for source in sources:
            if source.get("source_id") == source_id:
                selected_source = source
                break

        if selected_source is None:
            raise RopCliError(f"Source not found in rop.sources: source_id={source_id}")

        if not selected_source.get("enabled", False):
            raise RopCliError(
                f"Source is disabled in rop.sources: source_id={source_id}"
            )

        for source in sources:
            source["enabled"] = source is selected_source

        if items_max is not None:
            selected_source["items_max"] = items_max

        logger.debug(
            "CLI override applied: source_id=%s items_max=%s",
            source_id,
            items_max,
        )
    else:
        for source in sources:
            if source.get("enabled", False):
                if items_max is not None:
                    source["items_max"] = items_max

    return effective


# Экспорт TSV для ручного обзора оператором: читает normalized/classified артефакты конкретного run и сохраняет rop_review_table.tsv
def _export_review_tsv_for_run(
    storage_dir: Any,
    run_id: str,
    logger: logging.Logger,
) -> str:
    normalized_path = storage_dir / "runs" / run_id / "normalized_events.json"
    classified_path = storage_dir / "runs" / run_id / "classified_events.json"
    tsv_output_path = storage_dir / "runs" / run_id / "rop_review_table.tsv"

    if not normalized_path.exists():
        raise RopCliError(f"normalized_events.json not found for run_id={run_id}")
    if not classified_path.exists():
        raise RopCliError(f"classified_events.json not found for run_id={run_id}")

    try:
        with normalized_path.open("r", encoding="utf-8") as f:
            normalized_events = json.load(f)
        with classified_path.open("r", encoding="utf-8") as f:
            classified_events = json.load(f)
    except json.JSONDecodeError as exc:
        raise RopCliError(f"Failed to parse JSON artifacts: {exc}") from exc

    tsv_rows = _build_review_tsv_rows(normalized_events, classified_events)

    try:
        with tsv_output_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=_tsv_columns(),
                delimiter="\t",
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(tsv_rows)
    except Exception as exc:
        raise RopCliError(f"Failed to write TSV: {exc}") from exc

    print(f"\nReview TSV exported: {tsv_output_path}")
    logger.info(
        "ROP CLI: review TSV exported for run_id=%s path=%s rows=%d",
        run_id,
        tsv_output_path,
        len(tsv_rows),
    )
    return tsv_output_path.as_posix()


# Билд читаемого текста для operator_summary.json, включая основные поля и блоки source и classification, а также список артефактов
def _build_summary_text(summary_data: dict[str, Any]) -> str:
    run_id = summary_data.get("run_id", "?")
    module_id = summary_data.get("module_id", "?")
    case_type = summary_data.get("case_type", "?")
    status = summary_data.get("status", "?")
    module_status = summary_data.get("module_status", "?")
    summary = summary_data.get("summary", "")
    source = summary_data.get("source", {}) or {}
    classification = summary_data.get("classification", {}) or {}
    artifact_refs = summary_data.get("artifact_refs", [])

    source_block = ""
    if isinstance(source, dict) and source:
        source_block = (
            f"source_id: {source.get('source_id', '?')}\n"
            f"source_type: {source.get('source_type', '?')}\n"
            f"loaded_items: {source.get('loaded_item_count', '?')}\n"
            f"period: {source.get('period', '?')}\n"
        )

    classification_block = ""
    if isinstance(classification, dict) and classification:
        classification_block = (
            f"normalized_count: {classification.get('normalized_count', '?')}\n"
            f"classified_count: {classification.get('classified_count', '?')}\n"
            f"classification_failed_count: {classification.get('classification_failed_count', '?')}\n"
        )

    artifacts_text = "\n".join(f"- {item}" for item in artifact_refs) or "- none"

    text = (
        "ROP operator summary\n"
        f"run_id: {run_id}\n"
        f"module_id: {module_id}\n"
        f"case_type: {case_type}\n"
        f"status: {status}\n"
        f"module_status: {module_status}\n"
        f"summary: {summary}\n"
    )

    if source_block:
        text += f"{source_block}"
    if classification_block:
        text += f"{classification_block}"

    text += f"artifacts:\n{artifacts_text}"

    return text


# Возврат списка имен колонок для TSV, соответствующих полям из normalized_events и classified_events, а также дополнительным полям для ручного обзора оператором
def _safe_tsv_value(value: Any) -> str:
    if value is None or value == "":
        return ""

    text = str(value)
    text = text.replace("\t", " ").replace("\n", " ").replace("\r", " ")
    text = " ".join(text.split())
    return text


# Билд короткого превью текста для TSV, используя body_preview, text_preview или body из normalized_events, обрезая до REVIEW_BODY_SHORT_MAX_CHARS и очищая от табов и новых строк
def _build_body_short(normalized_evt: dict) -> str:
    preview = normalized_evt.get("body_preview")
    if preview and isinstance(preview, str) and preview.strip():
        return _safe_tsv_value(preview[:REVIEW_BODY_SHORT_MAX_CHARS])

    preview = normalized_evt.get("text_preview")
    if preview and isinstance(preview, str) and preview.strip():
        return _safe_tsv_value(preview[:REVIEW_BODY_SHORT_MAX_CHARS])

    body = normalized_evt.get("body")
    if body and isinstance(body, str) and body.strip():
        return _safe_tsv_value(body[:REVIEW_BODY_SHORT_MAX_CHARS])

    return ""


# Билд компактного текстового описания вложений для TSV, используя filename, content_type и size_bytes из normalized_events.attachments, формируя строки вида "filename (content_type, size_bytes)" и объединяя несколько вложений через "; "
def _build_attachment_summary(attachments: Any) -> str:
    if not attachments or not isinstance(attachments, list):
        return ""

    summaries = []
    for att in attachments:
        if not isinstance(att, dict):
            continue

        filename = _safe_tsv_value(att.get("filename", ""))
        content_type = _safe_tsv_value(att.get("content_type", ""))
        size_bytes = att.get("size_bytes")

        if not filename:
            continue

        parts = [filename]
        meta = []

        if content_type:
            meta.append(content_type)

        if size_bytes is not None:
            try:
                size_int = int(size_bytes)
                meta.append(str(size_int))
            except (ValueError, TypeError):
                pass

        summary = " ".join(parts)
        if meta:
            summary += f" ({', '.join(meta)})"
        summaries.append(_safe_tsv_value(summary))

    return _safe_tsv_value("; ".join(summaries))


# Возврат списка имен колонок для TSV, соответствующих полям из normalized_events и classified_event
def _tsv_columns() -> list[str]:
    return [
        "event_id",
        "source_id",
        "sender",
        "subject",
        "body_short",
        "attachments",
        "bot_case_type",
        "bot_reason_code",
        "bot_priority",
        "bot_confidence",
        "bot_is_fallback",
        "bot_reasoning",
        "human_case_type",
        "should_rop_see",
        "bitrix_status",
        "notes",
        "bitrix_lead_id",
        "bitrix_deal_id",
        "bitrix_responsible",
        "is_duplicate",
        "duplicate_of",
        "correct_action",
    ]


# Билд строк для TSV из normalized_events и classified_events, объединяя данные по event_id и добавляя поля для ручного обзора оператором
def _build_review_tsv_rows(
    normalized_events: list[dict],
    classified_events: list[dict],
) -> list[dict[str, str]]:
    normalized_lookup = {evt.get("event_id"): evt for evt in normalized_events}

    rows: list[dict[str, str]] = []

    for classified_evt in classified_events:
        event_id = classified_evt.get("event_id", "")
        original_event_id = classified_evt.get("original_event_id", event_id)
        normalized_evt = normalized_lookup.get(original_event_id, {})

        body_short = _build_body_short(normalized_evt)
        attachments_summary = _build_attachment_summary(
            normalized_evt.get("attachments")
        )
        bot_priority = classified_evt.get("priority", "")
        bot_reasoning = classified_evt.get("reasoning", "")
        is_duplicate = classified_evt.get("is_duplicate")
        duplicate_of = classified_evt.get("duplicate_of", "")

        row = {
            "event_id": _safe_tsv_value(event_id),
            "source_id": _safe_tsv_value(classified_evt.get("source_id", "")),
            "sender": _safe_tsv_value(normalized_evt.get("sender", "")),
            "subject": _safe_tsv_value(normalized_evt.get("subject", "")),
            "body_short": body_short,
            "attachments": _safe_tsv_value(attachments_summary),
            "bot_case_type": _safe_tsv_value(classified_evt.get("case_type", "")),
            "bot_reason_code": _safe_tsv_value(classified_evt.get("reason_code", "")),
            "bot_priority": _safe_tsv_value(bot_priority),
            "bot_confidence": _safe_tsv_value(classified_evt.get("confidence", "")),
            "bot_is_fallback": _safe_tsv_value(
                str(classified_evt.get("is_fallback", False)).lower()
            ),
            "bot_reasoning": _safe_tsv_value(bot_reasoning),
            "human_case_type": "",
            "should_rop_see": "",
            "bitrix_status": "",
            "notes": "",
            "bitrix_lead_id": "",
            "bitrix_deal_id": "",
            "bitrix_responsible": "",
            "is_duplicate": (
                _safe_tsv_value(str(is_duplicate).lower())
                if is_duplicate is not None
                else ""
            ),
            "duplicate_of": _safe_tsv_value(duplicate_of),
            "correct_action": "",
        }
        rows.append(row)

    return rows


# Применение CLI-переопределений к конфигурации источников данных для ROP: позволяет указать source_id для выбора конкретного источника, а также items_max и period для ограничения количества обрабатываемых событий и периода для batch-источников
def create_rop_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="start.py rop",
        description="ROP CLI entrypoint for batch processing",
    )

    subparsers = parser.add_subparsers(dest="rop_command", required=True)

    run_parser = subparsers.add_parser("run", help="Run ROP batch pipeline")
    run_parser.add_argument(
        "--source-id",
        type=str,
        default=None,
        help="Override source_id from rop.sources (optional)",
    )
    run_parser.add_argument(
        "--items-max",
        type=int,
        default=None,
        help="Override items_max for selected source (optional)",
    )
    run_parser.add_argument(
        "--period",
        type=str,
        default=None,
        help="Override period for batch source (optional)",
    )
    run_parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Explicit run_id (optional, generated if not provided)",
    )

    summary_parser = subparsers.add_parser("summary", help="Display run summary")
    summary_parser.add_argument(
        "--run-id",
        type=str,
        required=True,
        help="run_id to display summary for",
    )

    export_parser = subparsers.add_parser(
        "export-review", help="Export TSV for human review"
    )
    export_parser.add_argument(
        "--run-id",
        type=str,
        required=True,
        help="run_id to export review for",
    )
    export_parser.add_argument(
        "--format",
        type=str,
        choices=["tsv"],
        default="tsv",
        help="Export format (default: tsv)",
    )

    return parser
