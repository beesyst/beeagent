from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MAX_BODY_SHORT = 500
RUN_ARTIFACT_WHITELIST = {
    "operator_summary.json",
    "source_diagnostics.json",
    "intake_metadata.json",
    "normalized_events.json",
    "classified_events.json",
    "rop_review_table.tsv",
}
MODULE_ARTIFACT_WHITELIST = {
    "module_result.json",
    "rop_summary_result.json",
}


# Валидация идентификаторов запусков
def is_valid_run_id(run_id: str) -> bool:
    return bool(RUN_ID_PATTERN.fullmatch(run_id))


# Разрешение пути к данным запуска с защитой от path traversal атак и проверкой валидности идентификатора запуска
def resolve_run_dir(storage_dir: Path, run_id: str) -> Path | None:
    if not is_valid_run_id(run_id):
        return None

    runs_dir = (storage_dir / "runs").resolve()
    run_dir = (runs_dir / run_id).resolve()

    try:
        run_dir.relative_to(runs_dir)
    except ValueError:
        return None

    return run_dir


# Список запусков, доступных в хранилище, с сортировкой по дате создания
def list_runs(storage_dir: Path) -> list[str]:
    runs_dir = storage_dir / "runs"
    if not runs_dir.exists():
        return []

    run_dirs = [item for item in runs_dir.iterdir() if item.is_dir()]
    run_dirs.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return [item.name for item in run_dirs]


# Чтение артефактов запуска с безопасным доступом к данным, фильтрацией чувствительной информации и формированием структурированных представлений для отображения в веб-интерфейсе
def read_json_file(path: Path) -> tuple[Any | None, str | None]:
    if not path.exists():
        return None, "missing"

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file), None
    except json.JSONDecodeError:
        return None, "malformed"
    except OSError:
        return None, "unreadable"


# Чтение TSV файлов с безопасным доступом к данным, фильтрацией чувствительной информации и формированием структурированных представлений для отображения в веб-интерфейсе
def read_tsv_file(path: Path) -> tuple[list[dict[str, str]] | None, str | None]:
    if not path.exists():
        return None, "missing"

    try:
        with path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file, delimiter="\t")
            rows = list(reader)
            return rows, None
    except csv.Error:
        return None, "malformed"
    except OSError:
        return None, "unreadable"


# Чтение артефактов запуска с безопасным доступом к данным
def safe_read_text(path: Path) -> tuple[str | None, str | None]:
    if not path.exists():
        return None, "missing"
    try:
        return path.read_text(encoding="utf-8"), None
    except OSError:
        return None, "unreadable"


# Формирование представлений данных из артефактов запуска для отображения в веб-интерфейсе
def build_run_overview(run_dir: Path) -> dict[str, Any]:
    summary, summary_error = read_json_file(run_dir / "operator_summary.json")
    source_diagnostics, source_error = read_json_file(
        run_dir / "source_diagnostics.json"
    )
    intake_metadata, intake_error = read_json_file(run_dir / "intake_metadata.json")

    classified_events, classified_error = read_json_file(
        run_dir / "classified_events.json"
    )
    normalized_events, normalized_error = read_json_file(
        run_dir / "normalized_events.json"
    )

    available_artifacts: list[str] = []
    for name in sorted(RUN_ARTIFACT_WHITELIST):
        if (run_dir / name).exists():
            available_artifacts.append(name)

    module_artifacts: list[str] = []
    module_dir = run_dir / "module-beeagent-rop"
    for name in sorted(MODULE_ARTIFACT_WHITELIST):
        if (module_dir / name).exists():
            module_artifacts.append(name)

    return {
        "summary": summary if isinstance(summary, dict) else {},
        "source_diagnostics": source_diagnostics
        if isinstance(source_diagnostics, dict)
        else {},
        "intake_metadata": intake_metadata if isinstance(intake_metadata, dict) else {},
        "classified_count": len(classified_events)
        if isinstance(classified_events, list)
        else None,
        "normalized_count": len(normalized_events)
        if isinstance(normalized_events, list)
        else None,
        "errors": {
            "operator_summary": summary_error,
            "source_diagnostics": source_error,
            "intake_metadata": intake_error,
            "classified_events": classified_error,
            "normalized_events": normalized_error,
        },
        "available_artifacts": available_artifacts,
        "module_artifacts": module_artifacts,
    }


# Формирование представлений данных из артефактов запуска для отображения в веб-интерфейсе
def build_rop_dashboard(
    run_dir: Path,
    case_type_filter: str | None,
    priority_filter: str | None,
    fallback_filter: str | None,
    reason_code_filter: str | None,
) -> dict[str, Any]:
    summary_data, summary_error = read_json_file(run_dir / "operator_summary.json")
    classified_data, classified_error = read_json_file(
        run_dir / "classified_events.json"
    )
    normalized_data, normalized_error = read_json_file(
        run_dir / "normalized_events.json"
    )

    rows: list[dict[str, Any]] = []
    errors: list[str] = []

    if summary_error:
        errors.append(f"operator_summary:{summary_error}")
    if classified_error:
        errors.append(f"classified_events:{classified_error}")
    if normalized_error:
        errors.append(f"normalized_events:{normalized_error}")

    normalized_lookup: dict[str, dict[str, Any]] = {}
    if isinstance(normalized_data, list):
        for item in normalized_data:
            if not isinstance(item, dict):
                continue
            event_id = item.get("event_id")
            if isinstance(event_id, str) and event_id:
                normalized_lookup[event_id] = item

    if isinstance(classified_data, list):
        for item in classified_data:
            if not isinstance(item, dict):
                continue

            event_id = _as_text(item.get("event_id"))
            original_event_id = _as_text(item.get("original_event_id")) or event_id
            source_event = normalized_lookup.get(original_event_id, {})

            rows.append(
                {
                    "event_id": event_id,
                    "sender": _as_text(source_event.get("sender")),
                    "subject": _as_text(source_event.get("subject")),
                    "body_short": _body_short(source_event),
                    "attachments": _attachments_summary(
                        source_event.get("attachments")
                    ),
                    "bot_case_type": _as_text(item.get("case_type")),
                    "bot_priority": _as_text(item.get("priority")),
                    "bot_confidence": _as_text(item.get("confidence")),
                    "bot_reason_code": _as_text(item.get("reason_code")),
                    "bot_reasoning": _as_text(item.get("reasoning")),
                    "bot_is_fallback": _bool_text(item.get("is_fallback")),
                }
            )

    case_type_values = sorted(
        {row["bot_case_type"] for row in rows if row["bot_case_type"]}
    )
    priority_values = sorted(
        {row["bot_priority"] for row in rows if row["bot_priority"]}
    )
    reason_code_values = sorted(
        {row["bot_reason_code"] for row in rows if row["bot_reason_code"]}
    )

    filtered_rows = [
        row
        for row in rows
        if _matches_filters(
            row=row,
            case_type_filter=case_type_filter,
            priority_filter=priority_filter,
            fallback_filter=fallback_filter,
            reason_code_filter=reason_code_filter,
        )
    ]

    case_type_counts = dict(
        Counter(row["bot_case_type"] for row in rows if row["bot_case_type"])
    )
    priority_counts = dict(
        Counter(row["bot_priority"] for row in rows if row["bot_priority"])
    )
    reason_code_counts = dict(
        Counter(row["bot_reason_code"] for row in rows if row["bot_reason_code"])
    )
    fallback_count = sum(1 for row in rows if row["bot_is_fallback"] == "true")

    tsv_exists = (run_dir / "rop_review_table.tsv").exists()

    source_block: dict[str, Any] = {}
    classification_block: dict[str, Any] = {}
    if isinstance(summary_data, dict):
        source_value = summary_data.get("source")
        if isinstance(source_value, dict):
            source_block = source_value
        classification_value = summary_data.get("classification")
        if isinstance(classification_value, dict):
            classification_block = classification_value

    return {
        "errors": errors,
        "rows": filtered_rows,
        "total_rows": len(rows),
        "shown_rows": len(filtered_rows),
        "source": source_block,
        "classification": classification_block,
        "case_type_counts": case_type_counts,
        "priority_counts": priority_counts,
        "reason_code_counts": reason_code_counts,
        "fallback_count": fallback_count,
        "filters": {
            "case_type": case_type_filter or "",
            "priority": priority_filter or "",
            "fallback": fallback_filter or "",
            "reason_code": reason_code_filter or "",
        },
        "filter_options": {
            "case_type": case_type_values,
            "priority": priority_values,
            "reason_code": reason_code_values,
        },
        "tsv_exists": tsv_exists,
    }


# Формирование представлений данных из артефактов запуска для отображения в веб-интерфейсе
def _matches_filters(
    row: dict[str, Any],
    case_type_filter: str | None,
    priority_filter: str | None,
    fallback_filter: str | None,
    reason_code_filter: str | None,
) -> bool:
    if case_type_filter and row["bot_case_type"] != case_type_filter:
        return False
    if priority_filter and row["bot_priority"] != priority_filter:
        return False
    if reason_code_filter and row["bot_reason_code"] != reason_code_filter:
        return False
    if fallback_filter:
        normalized_filter = fallback_filter.strip().lower()
        if (
            normalized_filter in {"true", "1", "yes"}
            and row["bot_is_fallback"] != "true"
        ):
            return False
        if (
            normalized_filter in {"false", "0", "no"}
            and row["bot_is_fallback"] != "false"
        ):
            return False
    return True


# Формирование представлений данных из артефактов запуска для отображения в веб-интерфейсе
def _body_short(source_event: dict[str, Any]) -> str:
    for key in ("body_preview", "text_preview", "body"):
        value = source_event.get(key)
        if isinstance(value, str) and value.strip():
            return _sanitize(value)[:MAX_BODY_SHORT]
    return ""


# Формирование представлений данных из артефактов запуска для отображения в веб-интерфейсе
def _attachments_summary(attachments: Any) -> str:
    if not isinstance(attachments, list):
        return ""

    parts: list[str] = []
    for item in attachments:
        if not isinstance(item, dict):
            continue

        filename = _as_text(item.get("filename"))
        if not filename:
            continue

        if filename.lower().endswith(".eml"):
            continue

        content_type = _as_text(item.get("content_type"))
        size_value = item.get("size_bytes")
        if size_value is None:
            size_value = item.get("size")

        meta: list[str] = []
        if content_type:
            meta.append(content_type)
        if size_value is not None:
            meta.append(_as_text(size_value))

        label = filename
        if meta:
            label = f"{label} ({', '.join(meta)})"

        parts.append(_sanitize(label))

    return "; ".join(parts)


# Формирование представлений данных из артефактов запуска для отображения в веб-интерфейсе
def _bool_text(value: Any) -> str:
    return "true" if bool(value) else "false"


# Формирование представлений данных из артефактов запуска для отображения в веб-интерфейсе
def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return _sanitize(str(value))


# Формирование представлений данных из артефактов запуска для отображения в веб-интерфейсе
def _sanitize(value: str) -> str:
    return " ".join(
        value.replace("\t", " ").replace("\n", " ").replace("\r", " ").split()
    )
