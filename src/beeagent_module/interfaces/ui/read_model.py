from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# Безопасное чтение JSON-файла, в случае ошибки возвращается None
def _read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
    except json.JSONDecodeError, OSError:
        pass
    return None


# Билд read-model для дашборда, списка ран, деталей рана, конфигурации и т.д. на основе файловой структуры и артефактов
def build_dashboard(storage_dir: Path) -> dict[str, Any]:
    runs_dir = storage_dir / "runs"
    run_ids: list[str] = []
    if runs_dir.is_dir():
        run_ids = sorted(
            (d.name for d in runs_dir.iterdir() if d.is_dir()),
            key=lambda n: (runs_dir / n).stat().st_mtime,
            reverse=True,
        )

    latest_run: dict[str, Any] | None = None
    if run_ids:
        latest_id = run_ids[0]
        latest_dir = runs_dir / latest_id
        summary = _read_json(latest_dir / "operator_summary.json")
        if isinstance(summary, dict):
            latest_run = {
                "id": latest_id,
                "run_id": latest_id,
                "status": summary.get("status", "unknown"),
                "summary": summary.get("summary", ""),
                "source_display_name": _nested_get(
                    summary, ("source", "source_display_name"), ""
                ),
            }

    return {
        "total_runs": len(run_ids),
        "recent_run_ids": run_ids[:10],
        "latest_run": latest_run,
        "layout": [],
    }


# Список выполнений сборки read-model
def build_runs_list(storage_dir: Path) -> dict[str, Any]:
    runs_dir = storage_dir / "runs"
    run_ids: list[str] = []
    if runs_dir.is_dir():
        run_ids = sorted(
            (d.name for d in runs_dir.iterdir() if d.is_dir()),
            key=lambda n: (runs_dir / n).stat().st_mtime,
            reverse=True,
        )

    items: list[dict[str, Any]] = []
    for run_id in run_ids:
        run_dir = runs_dir / run_id
        summary = _read_json(run_dir / "operator_summary.json")
        source_diag = _read_json(run_dir / "source_diagnostics.json")

        status = "unknown"
        if isinstance(summary, dict):
            status = summary.get("status", "unknown")

        source_info = {}
        if isinstance(source_diag, dict):
            source_info["selection_mode"] = source_diag.get("selection_mode")

        items.append(
            {
                "id": run_id,
                "run_id": run_id,
                "status": status,
                "source_info": source_info,
            }
        )

    return {
        "runs": items,
        "total_runs": len(items),
        "layout": [],
    }


# Сборка запуска, детальное чтение модели
def build_run_detail(storage_dir: Path, run_id: str) -> dict[str, Any]:
    run_dir = (storage_dir / "runs" / run_id).resolve()
    if not run_dir.is_dir():
        return {"error": "not_found", "run_id": run_id}

    summary = _read_json(run_dir / "operator_summary.json")
    source_diag = _read_json(run_dir / "source_diagnostics.json")
    intake_meta = _read_json(run_dir / "intake_metadata.json")
    normalized = _read_json(run_dir / "normalized_events.json")
    classified = _read_json(run_dir / "classified_events.json")
    attachment_extraction = _read_json(run_dir / "attachment_extraction.json")

    return {
        "run_id": run_id,
        "summary": summary if isinstance(summary, dict) else {},
        "source_diagnostics": source_diag if isinstance(source_diag, dict) else {},
        "intake_metadata": intake_meta if isinstance(intake_meta, dict) else {},
        "normalized_count": len(normalized) if isinstance(normalized, list) else 0,
        "classified_count": len(classified) if isinstance(classified, list) else 0,
        "has_attachment_extraction": attachment_extraction is not None,
        "layout": [],
    }


# Билд модулей для отображения в UI на основе артефакта интерфейса
def build_modules_list(storage_dir: Path) -> dict[str, Any]:
    modules_path = storage_dir / "interfaces" / "modules.json"
    data = _read_json(modules_path)

    rows: list[dict[str, str]] = []
    if isinstance(data, dict):
        registry = data.get("registry")
        if isinstance(registry, list):
            for item in registry:
                if isinstance(item, dict):
                    rows.append(
                        {
                            "id": str(item.get("id", "")),
                            "package": str(item.get("package", "")),
                            "entry": str(item.get("entry", "")),
                            "state": str(item.get("state", "")),
                            "error": str(item.get("error", "")),
                        }
                    )

    return {"modules": rows, "total_modules": len(rows)}


# Билд read-model для ROP dashboard, с поддержкой выбора ран-уровня или последнего рана
def build_rop_dashboard_read_model(
    storage_dir: Path, run_id: str | None = None
) -> dict[str, Any]:
    runs_dir = storage_dir / "runs"
    if not runs_dir.is_dir():
        return {"error": "no_runs", "message": "No runs directory"}

    if run_id is None:
        run_ids = sorted(
            (d.name for d in runs_dir.iterdir() if d.is_dir()),
            key=lambda n: (runs_dir / n).stat().st_mtime,
            reverse=True,
        )
        if not run_ids:
            return {"error": "no_runs", "message": "No runs found"}
        run_id = run_ids[0]

    run_dir = (runs_dir / run_id).resolve()
    if not run_dir.is_dir():
        return {"error": "not_found", "run_id": run_id}

    summary = _read_json(run_dir / "operator_summary.json")
    source_diag = _read_json(run_dir / "source_diagnostics.json")
    intake = _read_json(run_dir / "intake_metadata.json")
    classified = _read_json(run_dir / "classified_events.json")

    result: dict[str, Any] = {
        "run_id": run_id,
        "status": "ok",
        "summary": summary if isinstance(summary, dict) else {},
        "source_diagnostics": source_diag if isinstance(source_diag, dict) else {},
        "intake_metadata": intake if isinstance(intake, dict) else {},
    }

    sources: list[dict[str, Any]] = []
    if isinstance(source_diag, dict):
        diag_sources = source_diag.get("sources", [])
        if isinstance(diag_sources, list):
            for s in diag_sources:
                if isinstance(s, dict):
                    sources.append(
                        {
                            "source_id": s.get("source_id", ""),
                            "source_type": s.get("source_type", ""),
                            "source_role": s.get("source_role", ""),
                            "display_name": s.get(
                                "source_display_name",
                                s.get("display_name", ""),
                            ),
                            "status": s.get("status", ""),
                        }
                    )
    elif isinstance(summary, dict):
        summary_sources = summary.get("sources", [])
        if isinstance(summary_sources, list):
            for s in summary_sources:
                if isinstance(s, dict):
                    sources.append(
                        {
                            "source_id": s.get("source_id", ""),
                            "source_type": s.get("source_type", ""),
                            "source_role": s.get("source_role", ""),
                            "display_name": s.get(
                                "source_display_name",
                                s.get("display_name", ""),
                            ),
                            "status": s.get("status", ""),
                        }
                    )

    result["sources"] = sources

    if isinstance(classified, list):
        result["classified_count"] = len(classified)
        case_types: dict[str, int] = {}
        priorities: dict[str, int] = {}
        fallback_count = 0
        for item in classified:
            if not isinstance(item, dict):
                continue
            ct = item.get("case_type")
            if isinstance(ct, str):
                case_types[ct] = case_types.get(ct, 0) + 1
            pr = item.get("priority")
            if isinstance(pr, str):
                priorities[pr] = priorities.get(pr, 0) + 1
            if item.get("is_fallback"):
                fallback_count += 1
        result["case_type_counts"] = case_types
        result["priority_counts"] = priorities
        result["fallback_count"] = fallback_count
    else:
        result["classified_count"] = 0
        result["case_type_counts"] = {}
        result["priority_counts"] = {}
        result["fallback_count"] = 0

    return result


# Билд read-model для конфигурации ROP source, с поддержкой маскировки чувствительных данных
def build_config_read_model(settings: dict[str, Any]) -> dict[str, Any]:
    raw_sources = settings.get("rop", {}).get("sources", [])
    if not isinstance(raw_sources, list):
        return {"sources": []}

    safe_sources: list[dict[str, Any]] = []
    for source in raw_sources:
        if not isinstance(source, dict):
            continue
        safe_source: dict[str, Any] = {
            "source_id": source.get("source_id", ""),
            "source_type": source.get("source_type", ""),
            "source_role": source.get("source_role", ""),
            "client_id": source.get("client_id", ""),
            "display_name": source.get("display_name", ""),
            "enabled": source.get("enabled", False),
            "authority": source.get("authority", ""),
            "items_max": source.get("items_max", 0),
        }

        mailbox = source.get("mailbox")
        if isinstance(mailbox, dict):
            safe_source["mailbox"] = {
                "host": mailbox.get("host", ""),
                "port": mailbox.get("port", 0),
                "use_ssl": mailbox.get("use_ssl", False),
                "folder": mailbox.get("folder", ""),
                "username_env": mailbox.get("username_env", ""),
            }

        safe_sources.append(safe_source)

    return {"sources": safe_sources}


# Безопасное получение значения вложенного словаря
def _nested_get(d: dict, path: tuple[str, ...], default: Any = None) -> Any:
    for key in path:
        if not isinstance(d, dict):
            return default
        d = d.get(key, {})
    return d if d != {} else default
