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
    "attachment_extraction.json",
    "normalized_events.json",
    "classified_events.json",
    "rop_review_table.tsv",
    "rop_writeback_summary.json",
}
MODULE_ARTIFACT_WHITELIST = {
    "module_result.json",
    "rop_summary_result.json",
}


def is_valid_run_id(run_id: str) -> bool:
    return bool(RUN_ID_PATTERN.fullmatch(run_id))


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


def list_runs(storage_dir: Path) -> list[str]:
    runs_dir = storage_dir / "runs"
    if not runs_dir.exists():
        return []

    run_dirs = [item for item in runs_dir.iterdir() if item.is_dir()]
    run_dirs.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return [item.name for item in run_dirs]


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


def safe_read_text(path: Path) -> tuple[str | None, str | None]:
    if not path.exists():
        return None, "missing"
    try:
        return path.read_text(encoding="utf-8"), None
    except OSError:
        return None, "unreadable"


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


def build_rop_dashboard(
    run_dir: Path,
    source_id_filter: str | None,
    source_role_filter: str | None,
    source_status_filter: str | None,
    case_type_filter: str | None,
    priority_filter: str | None,
    fallback_filter: str | None,
    reason_code_filter: str | None,
) -> dict[str, Any]:
    summary_data, summary_error = read_json_file(run_dir / "operator_summary.json")
    source_diagnostics_data, source_diagnostics_error = read_json_file(
        run_dir / "source_diagnostics.json"
    )
    intake_metadata_data, intake_metadata_error = read_json_file(
        run_dir / "intake_metadata.json"
    )
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
    if source_diagnostics_error:
        errors.append(f"source_diagnostics:{source_diagnostics_error}")
    if intake_metadata_error:
        errors.append(f"intake_metadata:{intake_metadata_error}")
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

    source_rows = _build_source_rows(
        source_diagnostics=source_diagnostics_data,
        intake_metadata=intake_metadata_data,
        summary_data=summary_data,
    )
    source_status_by_id = {
        str(item.get("source_id", "")): str(item.get("status", ""))
        for item in source_rows
        if item.get("source_id")
    }
    only_source = source_rows[0] if len(source_rows) == 1 else None

    if isinstance(classified_data, list):
        for item in classified_data:
            if not isinstance(item, dict):
                continue

            event_id = _as_text(item.get("event_id"))
            original_event_id = _as_text(item.get("original_event_id")) or event_id
            source_event = normalized_lookup.get(original_event_id, {})
            source_id = _as_text(item.get("source_id")) or _as_text(
                source_event.get("source_id")
            )
            source_type = _as_text(item.get("source_type")) or _as_text(
                source_event.get("source_type")
            )
            source_role = _as_text(item.get("source_role")) or _as_text(
                source_event.get("source_role")
            )
            source_display_name = _as_text(item.get("source_display_name")) or _as_text(
                source_event.get("source_display_name")
            )
            client_id = _as_text(item.get("client_id")) or _as_text(
                source_event.get("client_id")
            )

            if only_source is not None:
                source_id = source_id or _as_text(only_source.get("source_id"))
                source_type = source_type or _as_text(only_source.get("source_type"))
                source_role = source_role or _as_text(only_source.get("source_role"))
                source_display_name = source_display_name or _as_text(
                    only_source.get("source_display_name")
                )
                client_id = client_id or _as_text(only_source.get("client_id"))

            source_status = _as_text(source_status_by_id.get(source_id))
            if not source_status and only_source is not None:
                source_status = _as_text(only_source.get("status"))

            rows.append(
                {
                    "event_id": event_id,
                    "source_id": source_id,
                    "source_type": source_type,
                    "source_role": source_role,
                    "source_display_name": source_display_name,
                    "client_id": client_id,
                    "source_status": source_status,
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

    source_classification_counts = Counter(
        row["source_id"] for row in rows if row.get("source_id")
    )
    source_fallback_counts = Counter(
        row["source_id"]
        for row in rows
        if row.get("source_id") and row.get("bot_is_fallback") == "true"
    )
    for source_row in source_rows:
        source_id = _as_text(source_row.get("source_id"))
        source_row["classified_count"] = source_classification_counts.get(source_id, 0)
        source_row["fallback_count"] = source_fallback_counts.get(source_id, 0)

    source_id_values = sorted(
        {
            *{row["source_id"] for row in rows if row["source_id"]},
            *{
                _as_text(source.get("source_id"))
                for source in source_rows
                if source.get("source_id")
            },
        }
    )
    source_role_values = sorted(
        {
            *{row["source_role"] for row in rows if row["source_role"]},
            *{
                _as_text(source.get("source_role"))
                for source in source_rows
                if source.get("source_role")
            },
        }
    )
    source_status_values = sorted(
        {
            *{row["source_status"] for row in rows if row["source_status"]},
            *{
                _as_text(source.get("status"))
                for source in source_rows
                if source.get("status")
            },
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
            source_id_filter=source_id_filter,
            source_role_filter=source_role_filter,
            source_status_filter=source_status_filter,
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

    normalized_count = len(normalized_data) if isinstance(normalized_data, list) else 0
    classified_count = len(classified_data) if isinstance(classified_data, list) else 0
    classification_failed_count = max(normalized_count - classified_count, 0)

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
            classified_count = int(
                classification_value.get("classified_count", classified_count)
            )
            classification_failed_count = int(
                classification_value.get(
                    "classification_failed_count", classification_failed_count
                )
            )

    source_aggregate = _build_source_aggregate(
        source_diagnostics=source_diagnostics_data,
        intake_metadata=intake_metadata_data,
        source_rows=source_rows,
        normalized_count=normalized_count,
        classified_count=classified_count,
        classification_failed_count=classification_failed_count,
        fallback_count=fallback_count,
    )

    return {
        "errors": errors,
        "rows": filtered_rows,
        "total_rows": len(rows),
        "shown_rows": len(filtered_rows),
        "source_aggregate": source_aggregate,
        "sources": source_rows,
        "source": source_block,
        "classification": classification_block,
        "case_type_counts": case_type_counts,
        "priority_counts": priority_counts,
        "reason_code_counts": reason_code_counts,
        "fallback_count": fallback_count,
        "filters": {
            "source_id": source_id_filter or "",
            "source_role": source_role_filter or "",
            "source_status": source_status_filter or "",
            "case_type": case_type_filter or "",
            "priority": priority_filter or "",
            "fallback": fallback_filter or "",
            "reason_code": reason_code_filter or "",
        },
        "filter_options": {
            "source_id": source_id_values,
            "source_role": source_role_values,
            "source_status": source_status_values,
            "case_type": case_type_values,
            "priority": priority_values,
            "reason_code": reason_code_values,
        },
        "tsv_exists": tsv_exists,
    }


def _matches_filters(
    row: dict[str, Any],
    source_id_filter: str | None,
    source_role_filter: str | None,
    source_status_filter: str | None,
    case_type_filter: str | None,
    priority_filter: str | None,
    fallback_filter: str | None,
    reason_code_filter: str | None,
) -> bool:
    if source_id_filter and row["source_id"] != source_id_filter:
        return False
    if source_role_filter and row["source_role"] != source_role_filter:
        return False
    if source_status_filter and row["source_status"] != source_status_filter:
        return False
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


def _body_short(source_event: dict[str, Any]) -> str:
    for key in ("body_preview", "text_preview", "body"):
        value = source_event.get(key)
        if isinstance(value, str) and value.strip():
            return _sanitize(value)[:MAX_BODY_SHORT]
    return ""


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


def _bool_text(value: Any) -> str:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return "true"
        if normalized in {"false", "0", "no", ""}:
            return "false"

    return "true" if bool(value) else "false"


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return _sanitize(str(value))


def _sanitize(value: str) -> str:
    return " ".join(
        value.replace("\t", " ").replace("\n", " ").replace("\r", " ").split()
    )


def _build_source_rows(
    source_diagnostics: Any,
    intake_metadata: Any,
    summary_data: Any,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    diagnostics_sources = []
    if isinstance(source_diagnostics, dict):
        raw_sources = source_diagnostics.get("sources")
        if isinstance(raw_sources, list):
            diagnostics_sources = [
                item for item in raw_sources if isinstance(item, dict)
            ]

    intake_sources = []
    if isinstance(intake_metadata, dict):
        raw_sources = intake_metadata.get("sources")
        if isinstance(raw_sources, list):
            intake_sources = [item for item in raw_sources if isinstance(item, dict)]

    source_map: dict[str, dict[str, Any]] = {}
    for item in diagnostics_sources:
        source_id = _as_text(item.get("source_id"))
        if not source_id:
            continue
        source_map[source_id] = dict(item)

    for item in intake_sources:
        source_id = _as_text(item.get("source_id"))
        if not source_id:
            continue
        merged = dict(source_map.get(source_id, {}))
        merged.update(item)
        source_map[source_id] = merged

    if not source_map:
        single = _build_single_source_row(
            source_diagnostics, intake_metadata, summary_data
        )
        if single:
            source_map[_as_text(single.get("source_id")) or "single_source"] = single

    for source_id, item in source_map.items():
        rows.append(
            {
                "source_id": _as_text(item.get("source_id") or source_id),
                "source_type": _as_text(item.get("source_type")),
                "source_role": _as_text(item.get("source_role")),
                "source_display_name": _as_text(item.get("source_display_name")),
                "client_id": _as_text(item.get("client_id")),
                "authority": _as_text(item.get("authority")),
                "mailbox_folder": _as_text(item.get("mailbox_folder")),
                "status": _as_text(item.get("status")),
                "reason": _as_text(item.get("reason")),
                "items_max": _int_or_zero(item.get("items_max")),
                "fetched_count": _int_or_zero(item.get("fetched_count")),
                "loaded_count": _int_or_zero(item.get("loaded_count")),
                "malformed_count": _int_or_zero(item.get("malformed_count")),
                "classified_count": 0,
                "fallback_count": 0,
            }
        )

    rows.sort(key=lambda item: item.get("source_id", ""))
    return rows


def _build_single_source_row(
    source_diagnostics: Any,
    intake_metadata: Any,
    summary_data: Any,
) -> dict[str, Any] | None:
    candidates = []
    if isinstance(source_diagnostics, dict):
        candidates.append(source_diagnostics)
    if isinstance(intake_metadata, dict):
        candidates.append(intake_metadata)
    if isinstance(summary_data, dict):
        source_value = summary_data.get("source")
        if isinstance(source_value, dict):
            candidates.append(source_value)

    merged: dict[str, Any] = {}
    for item in candidates:
        merged.update(item)

    source_id = _as_text(merged.get("source_id"))
    if not source_id:
        return None

    return merged


def _build_source_aggregate(
    source_diagnostics: Any,
    intake_metadata: Any,
    source_rows: list[dict[str, Any]],
    normalized_count: int,
    classified_count: int,
    classification_failed_count: int,
    fallback_count: int,
) -> dict[str, Any]:
    aggregate: dict[str, Any] = {
        "source_count": len(source_rows),
        "loaded_source_count": sum(
            1 for item in source_rows if item.get("status") == "ok"
        ),
        "degraded_source_count": sum(
            1 for item in source_rows if item.get("status") == "degraded"
        ),
        "fetched_count": sum(
            _int_or_zero(item.get("fetched_count")) for item in source_rows
        ),
        "loaded_count": sum(
            _int_or_zero(item.get("loaded_count")) for item in source_rows
        ),
        "malformed_count": sum(
            _int_or_zero(item.get("malformed_count")) for item in source_rows
        ),
        "normalized_count": normalized_count,
        "classified_count": classified_count,
        "classification_failed_count": classification_failed_count,
        "fallback_count": fallback_count,
    }

    if isinstance(source_diagnostics, dict):
        diagnostics_aggregate = source_diagnostics.get("aggregate")
        if isinstance(diagnostics_aggregate, dict):
            for key in (
                "source_count",
                "loaded_source_count",
                "degraded_source_count",
                "fetched_count",
                "loaded_count",
                "malformed_count",
            ):
                if key in diagnostics_aggregate:
                    aggregate[key] = _int_or_zero(diagnostics_aggregate.get(key))

    if isinstance(intake_metadata, dict):
        for key in (
            "source_count",
            "loaded_source_count",
            "degraded_source_count",
            "fetched_count",
            "loaded_count",
            "malformed_count",
        ):
            if key in intake_metadata:
                aggregate[key] = _int_or_zero(intake_metadata.get(key))

    return aggregate


def _int_or_zero(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0
