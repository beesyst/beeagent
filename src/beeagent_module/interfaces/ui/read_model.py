from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ATTENTION_EVENTS_MAX = 50
ALLOWED_EVIDENCE_IDS: tuple[str, ...] = (
    "operator_summary_json",
    "source_diagnostics_json",
    "intake_metadata_json",
    "attachment_extraction_json",
    "normalized_events_json",
    "classified_events_json",
    "rop_review_table_tsv",
    "module_result_json",
    "rop_summary_result_json",
    "steps_json",
)
EVIDENCE_LABELS: dict[str, str] = {
    "operator_summary_json": "Operator summary",
    "source_diagnostics_json": "Source diagnostics",
    "intake_metadata_json": "Intake metadata",
    "attachment_extraction_json": "Attachment extraction",
    "normalized_events_json": "Normalized events",
    "classified_events_json": "Classified events",
    "rop_review_table_tsv": "Review TSV",
    "module_result_json": "Module result",
    "rop_summary_result_json": "ROP summary result",
    "steps_json": "Steps",
}


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


# Листинг разрешенных параметров командной строки для веб-конфигурации
def _list_run_ids(runs_dir: Path) -> list[str]:
    if not runs_dir.is_dir():
        return []
    return sorted(
        (d.name for d in runs_dir.iterdir() if d.is_dir()),
        key=lambda n: (runs_dir / n).stat().st_mtime,
        reverse=True,
    )


# Билд множества паттернов ключей, указывающих на чувствительные данные, которые следует редактировать
def _build_kpis(
    run_id: str,
    run_ids: list[str],
    summary: dict | None,
    source_diag: dict | None,
    intake: dict | None,
    normalized: list | None,
    classified: list | None,
    attachment_extraction: dict | None,
    run_dir: Path,
) -> dict[str, Any]:
    kpis: dict[str, Any] = {
        "selected_run_id": run_id,
        "total_runs": len(run_ids),
        "run_status": (summary or {}).get("status", "unknown"),
    }

    if isinstance(source_diag, dict):
        agg = source_diag.get("aggregate", {})
        kpis["source_count"] = _int(agg.get("source_count"))
        kpis["loaded_source_count"] = _int(agg.get("loaded_source_count"))
        kpis["degraded_source_count"] = _int(agg.get("degraded_source_count"))
    else:
        kpis["source_count"] = 0
        kpis["loaded_source_count"] = 0
        kpis["degraded_source_count"] = 0

    if isinstance(intake, dict):
        kpis["fetched_count"] = _int(
            intake.get("fetched_count", intake.get("loaded_item_count", 0))
        )
        kpis["loaded_count"] = _int(intake.get("loaded_item_count", 0))
        malformed = 0
        srcs = intake.get("sources")
        if isinstance(srcs, list):
            for s in srcs:
                if isinstance(s, dict):
                    malformed += _int(s.get("malformed_count", 0))
        kpis["malformed_count"] = malformed
    else:
        kpis["fetched_count"] = 0
        kpis["loaded_count"] = 0
        kpis["malformed_count"] = 0

    kpis["normalized_count"] = len(normalized) if isinstance(normalized, list) else 0

    if isinstance(classified, list):
        kpis["classified_count"] = len(classified)
        high_pri = sum(
            1 for c in classified if isinstance(c, dict) and c.get("priority") == "high"
        )
        med_pri = sum(
            1
            for c in classified
            if isinstance(c, dict) and c.get("priority") == "medium"
        )
        low_pri = sum(
            1 for c in classified if isinstance(c, dict) and c.get("priority") == "low"
        )
        fallback = sum(
            1 for c in classified if isinstance(c, dict) and c.get("is_fallback")
        )
        kpis["high_priority_count"] = high_pri
        kpis["medium_priority_count"] = med_pri
        kpis["low_priority_count"] = low_pri
        kpis["fallback_count"] = fallback
        kpis["classification_failed_count"] = 0
    else:
        kpis["classified_count"] = 0
        kpis["high_priority_count"] = 0
        kpis["medium_priority_count"] = 0
        kpis["low_priority_count"] = 0
        kpis["fallback_count"] = 0
        kpis["classification_failed_count"] = 0

    if isinstance(attachment_extraction, dict):
        agg = attachment_extraction.get("aggregate", {})
        kpis["attachment_count"] = _int(agg.get("attachment_count", 0))
        kpis["attachment_preview_count"] = _int(agg.get("preview_available_count", 0))
        kpis["attachment_refused_count"] = _int(agg.get("refused_count", 0))
        kpis["attachment_blocked_count"] = _int(agg.get("refused_count", 0))
    else:
        kpis["attachment_count"] = 0
        kpis["attachment_preview_count"] = 0
        kpis["attachment_refused_count"] = 0
        kpis["attachment_blocked_count"] = 0

    kpis["review_tsv_available"] = (run_dir / "rop_review_table.tsv").is_file()

    return kpis


# Импорт функций для чтения модели и разрешения артефактов
def _build_funnel(
    source_diag: dict | None,
    intake: dict | None,
    normalized: list | None,
    classified: list | None,
    kpis: dict[str, Any],
) -> list[dict[str, Any]]:
    funnel: list[dict[str, Any]] = []

    if isinstance(source_diag, dict):
        agg = source_diag.get("aggregate", {})
        funnel.append(
            {"stage": "Configured Sources", "count": _int(agg.get("source_count", 0))}
        )
        funnel.append(
            {
                "stage": "Enabled Sources",
                "count": _int(agg.get("loaded_source_count", 0)),
            }
        )
    else:
        funnel.append({"stage": "Configured Sources", "count": 0})
        funnel.append({"stage": "Enabled Sources", "count": 0})

    if isinstance(intake, dict):
        funnel.append(
            {
                "stage": "Fetched Items",
                "count": _int(
                    intake.get("fetched_count", intake.get("loaded_item_count", 0))
                ),
            }
        )
        funnel.append(
            {"stage": "Loaded Items", "count": _int(intake.get("loaded_item_count", 0))}
        )
    else:
        funnel.append({"stage": "Fetched Items", "count": 0})
        funnel.append({"stage": "Loaded Items", "count": 0})

    funnel.append(
        {"stage": "Normalized Events", "count": kpis.get("normalized_count", 0)}
    )
    funnel.append(
        {"stage": "Classified Events", "count": kpis.get("classified_count", 0)}
    )

    review_candidates = kpis.get("fallback_count", 0) + kpis.get(
        "high_priority_count", 0
    )
    funnel.append({"stage": "Review Candidates", "count": review_candidates})

    return funnel


# Билд рекомендаций на основе KPI и артефактов для отображения в UI
def _build_source_health(
    source_diag: dict | None,
    intake: dict | None,
    classified: list | None,
    run_dir: Path,
) -> list[dict[str, Any]]:
    health: list[dict[str, Any]] = []
    diag_sources: list[dict] = []

    if isinstance(source_diag, dict):
        diag_sources = source_diag.get("sources", [])
        if not isinstance(diag_sources, list):
            diag_sources = []

    if not diag_sources and isinstance(intake, dict):
        intake_sources = intake.get("sources", [])
        if isinstance(intake_sources, list):
            for s in intake_sources:
                if isinstance(s, dict):
                    diag_sources.append(
                        {
                            "source_id": s.get("source_id", ""),
                            "display_name": s.get("source_id", ""),
                            "source_type": s.get("source_type", ""),
                            "source_role": s.get("source_role", ""),
                            "client_id": s.get("client_id", ""),
                            "authority": s.get("authority", ""),
                            "status": s.get("status", "ok"),
                            "reason": None,
                            "items_max": s.get("items_max", 0),
                            "fetched_count": s.get("fetched_count", 0),
                            "loaded_count": s.get("loaded_count", 0),
                            "malformed_count": s.get("malformed_count", 0),
                        }
                    )

    per_source_classified: dict[str, int] = {}
    per_source_fallback: dict[str, int] = {}
    if isinstance(classified, list):
        for item in classified:
            if not isinstance(item, dict):
                continue
            sid = item.get("source_id", "")
            if sid:
                per_source_classified[sid] = per_source_classified.get(sid, 0) + 1
                if item.get("is_fallback"):
                    per_source_fallback[sid] = per_source_fallback.get(sid, 0) + 1

    for s in diag_sources:
        if not isinstance(s, dict):
            continue
        sid = s.get("source_id", "")
        health.append(
            {
                "source_id": sid,
                "display_name": s.get("source_display_name")
                or s.get("display_name")
                or sid,
                "source_type": s.get("source_type", ""),
                "source_role": s.get("source_role", ""),
                "client_id": s.get("client_id", ""),
                "authority": s.get("authority", ""),
                "status": s.get("status", "unknown"),
                "reason": s.get("reason") or s.get("degraded_reason"),
                "items_max": _int(s.get("items_max", 0)),
                "fetched_count": _int(s.get("fetched_count", 0)),
                "loaded_count": _int(s.get("loaded_count", 0)),
                "malformed_count": _int(s.get("malformed_count", 0)),
                "classified_count": per_source_classified.get(sid, 0),
                "fallback_count": per_source_fallback.get(sid, 0),
            }
        )

    return health


# Билд распределения классификаций для отображения в UI
def _build_classification_distribution(classified: list | None) -> dict[str, Any]:
    dist: dict[str, Any] = {
        "case_type_counts": {},
        "priority_counts": {},
        "reason_code_counts": {},
        "fallback_count": 0,
    }
    if not isinstance(classified, list):
        return dist

    for item in classified:
        if not isinstance(item, dict):
            continue
        ct = item.get("case_type")
        if isinstance(ct, str):
            dist["case_type_counts"][ct] = dist["case_type_counts"].get(ct, 0) + 1
        pr = item.get("priority")
        if isinstance(pr, str):
            dist["priority_counts"][pr] = dist["priority_counts"].get(pr, 0) + 1
        rc = item.get("reason_code")
        if isinstance(rc, str):
            dist["reason_code_counts"][rc] = dist["reason_code_counts"].get(rc, 0) + 1
        if item.get("is_fallback"):
            dist["fallback_count"] += 1

    return dist


# Импорт функций для чтения модели и разрешения артефактов
def _build_attachment_summary(attachment_extraction: dict | None) -> dict[str, Any]:
    default: dict[str, Any] = {
        "total_attachments": 0,
        "preview_available_count": 0,
        "refused_count": 0,
        "blocked_count": 0,
        "unsupported_count": 0,
        "oversized_count": 0,
        "extraction_error_count": 0,
    }
    if not isinstance(attachment_extraction, dict):
        return default

    agg = attachment_extraction.get("aggregate")
    if isinstance(agg, dict):
        default["total_attachments"] = _int(agg.get("attachment_count", 0))
        default["preview_available_count"] = _int(agg.get("preview_available_count", 0))
        default["refused_count"] = _int(agg.get("refused_count", 0))
        default["blocked_count"] = _int(agg.get("refused_count", 0))
        default["unsupported_count"] = _int(agg.get("unsupported_count", 0))
        default["extraction_error_count"] = _int(agg.get("failed_count", 0))
    else:
        items = attachment_extraction.get("items")
        if isinstance(items, list):
            total = len(items)
            preview = sum(
                1 for i in items if isinstance(i, dict) and i.get("preview_available")
            )
            refused = sum(
                1 for i in items if isinstance(i, dict) and i.get("is_refused")
            )
            default["total_attachments"] = total
            default["preview_available_count"] = preview
            default["refused_count"] = refused
            default["blocked_count"] = refused

    return default


# Импорт функций для чтения модели и разрешения артефактов
def _build_recommendations(kpis: dict[str, Any]) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []

    hp = kpis.get("high_priority_count", 0)
    if hp > 0:
        recs.append(
            {
                "code": "review_high_priority",
                "severity": "warning",
                "title": "Review high-priority events",
                "message": f"{hp} high-priority classified events need operator review.",
                "count": hp,
            }
        )

    fb = kpis.get("fallback_count", 0)
    if fb > 0:
        recs.append(
            {
                "code": "review_fallback",
                "severity": "warning",
                "title": "Review fallback classifications",
                "message": f"{fb} events were classified via fallback. Manual review recommended.",
                "count": fb,
            }
        )

    deg = kpis.get("degraded_source_count", 0)
    if deg > 0:
        recs.append(
            {
                "code": "check_degraded_sources",
                "severity": "warning",
                "title": "Check degraded sources",
                "message": f"{deg} source(s) reported degradation. Investigate source health.",
                "count": deg,
            }
        )

    mal = kpis.get("malformed_count", 0)
    if mal > 0:
        recs.append(
            {
                "code": "investigate_malformed",
                "severity": "warning",
                "title": "Investigate malformed source items",
                "message": f"{mal} malformed item(s) detected during intake.",
                "count": mal,
            }
        )

    loaded = kpis.get("loaded_count", 0)
    classified_c = kpis.get("classified_count", 0)
    if loaded > 0 and classified_c == 0:
        recs.append(
            {
                "code": "classification_no_output",
                "severity": "info",
                "title": "Classification produced no output",
                "message": f"{loaded} items loaded but 0 classified. Check module diagnostics.",
                "count": 0,
            }
        )

    refused = kpis.get("attachment_refused_count", 0)
    blocked = kpis.get("attachment_blocked_count", 0)
    if refused > 0 or blocked > 0:
        total_attn = max(refused, blocked)
        recs.append(
            {
                "code": "review_blocked_attachments",
                "severity": "info",
                "title": "Review blocked/refused attachments",
                "message": f"{total_attn} attachment(s) were refused or blocked during extraction.",
                "count": total_attn,
            }
        )

    if kpis.get("review_tsv_available"):
        recs.append(
            {
                "code": "open_review_tsv",
                "severity": "info",
                "title": "Open review TSV",
                "message": "Review TSV is available for human review export.",
                "count": 0,
            }
        )

    return recs


# Импорт функций для чтения модели и разрешения артефактов
def _build_attention_events(
    classified: list | None,
    normalized: list | None,
    source_health: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not isinstance(classified, list):
        return events

    norm_by_id: dict[str, dict] = {}
    if isinstance(normalized, list):
        for n in normalized:
            if isinstance(n, dict):
                eid = n.get("event_id") or n.get("original_event_id")
                if eid:
                    norm_by_id[eid] = n

    src_display: dict[str, str] = {}
    for sh in source_health:
        if isinstance(sh, dict):
            src_display[sh.get("source_id", "")] = sh.get("display_name", "")

    def _sort_key(item: dict) -> tuple:
        pri = item.get("priority", "")
        pri_order = 0 if pri == "high" else (1 if pri == "medium" else 2)
        is_fb = 0 if item.get("is_fallback") else 1
        conf = item.get("confidence")
        low_conf = (
            0
            if (isinstance(conf, (int, float)) and conf is not None and conf < 0.7)
            else 1
        )
        return (pri_order, is_fb, low_conf)

    candidates = [c for c in classified if isinstance(c, dict)]
    candidates.sort(key=_sort_key)

    for item in candidates[:ATTENTION_EVENTS_MAX]:
        if not isinstance(item, dict):
            continue
        eid = item.get("event_id", "")
        norm = norm_by_id.get(eid, {})
        sid = item.get("source_id", "") or norm.get("source_id", "")

        reasons: list[str] = []
        if item.get("priority") == "high":
            reasons.append("High priority")
        if item.get("is_fallback"):
            reasons.append("Fallback classification")
        conf = item.get("confidence")
        if isinstance(conf, (int, float)) and conf is not None and conf < 0.7:
            reasons.append(f"Low confidence ({conf:.2f})")
        if not reasons:
            reasons.append("Needs review")

        evt = {
            "event_id": eid,
            "source_id": sid,
            "source_display_name": src_display.get(sid, ""),
            "sender": norm.get("sender", item.get("sender", "")),
            "subject": norm.get("subject", item.get("subject", "")),
            "case_type": item.get("case_type", ""),
            "priority": item.get("priority", ""),
            "confidence": conf,
            "reason_code": item.get("reason_code", ""),
            "is_fallback": bool(item.get("is_fallback")),
            "attachment_count": _int(
                norm.get("attachment_count", item.get("attachment_count", 0))
            ),
            "review_reason": "; ".join(reasons),
        }
        events.append(evt)

    return events


# Импорт функций для чтения модели и разрешения артефактов
def _build_evidence_links(run_id: str) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for aid in ALLOWED_EVIDENCE_IDS:
        links.append(
            {
                "artifact_id": aid,
                "label": EVIDENCE_LABELS.get(aid, aid),
                "available": False,
                "url": f"/runs/{run_id}/artifacts/{aid}",
            }
        )
    return links


# Безопасное преобразование в int, возвращает 0 при ошибке или неподходящем типе
def _int(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


# Билд полной read-model для ROP Dashboard на основе всех доступных артефактов и данных, с обработкой ошибок и отсутствующих данных
def build_rop_dashboard_read_model(
    storage_dir: Path, run_id: str | None = None
) -> dict[str, Any]:
    runs_dir = storage_dir / "runs"
    if not runs_dir.is_dir():
        return {"error": "no_runs", "message": "No runs directory"}

    run_ids = _list_run_ids(runs_dir)
    if run_id is None:
        if not run_ids:
            return {"error": "no_runs", "message": "No runs found"}
        run_id = run_ids[0]

    run_dir = (runs_dir / run_id).resolve()
    if not run_dir.is_dir():
        return {"error": "not_found", "run_id": run_id}

    summary = _read_json(run_dir / "operator_summary.json")
    source_diag = _read_json(run_dir / "source_diagnostics.json")
    intake = _read_json(run_dir / "intake_metadata.json")
    normalized = _read_json(run_dir / "normalized_events.json")
    classified = _read_json(run_dir / "classified_events.json")
    attachment_extraction = _read_json(run_dir / "attachment_extraction.json")

    warnings: list[dict[str, Any]] = []
    if summary is None:
        warnings.append(
            {"code": "missing_artifact", "artifact": "operator_summary.json"}
        )
    if source_diag is None:
        warnings.append(
            {"code": "missing_artifact", "artifact": "source_diagnostics.json"}
        )
    if intake is None:
        warnings.append(
            {"code": "missing_artifact", "artifact": "intake_metadata.json"}
        )
    if normalized is None:
        warnings.append(
            {"code": "missing_artifact", "artifact": "normalized_events.json"}
        )
    if classified is None:
        warnings.append(
            {"code": "missing_artifact", "artifact": "classified_events.json"}
        )

    kpis = _build_kpis(
        run_id=run_id,
        run_ids=run_ids,
        summary=summary if isinstance(summary, dict) else None,
        source_diag=source_diag if isinstance(source_diag, dict) else None,
        intake=intake if isinstance(intake, dict) else None,
        normalized=normalized if isinstance(normalized, list) else None,
        classified=classified if isinstance(classified, list) else None,
        attachment_extraction=attachment_extraction
        if isinstance(attachment_extraction, dict)
        else None,
        run_dir=run_dir,
    )

    funnel = _build_funnel(
        source_diag=source_diag if isinstance(source_diag, dict) else None,
        intake=intake if isinstance(intake, dict) else None,
        normalized=normalized if isinstance(normalized, list) else None,
        classified=classified if isinstance(classified, list) else None,
        kpis=kpis,
    )

    source_health = _build_source_health(
        source_diag=source_diag if isinstance(source_diag, dict) else None,
        intake=intake if isinstance(intake, dict) else None,
        classified=classified if isinstance(classified, list) else None,
        run_dir=run_dir,
    )

    degraded_count = kpis.get("degraded_source_count", 0)
    if degraded_count > 0:
        warnings.append(
            {
                "code": "degraded_sources",
                "count": degraded_count,
                "message": f"{degraded_count} source(s) reported degradation.",
            }
        )

    classification_distribution = _build_classification_distribution(
        classified if isinstance(classified, list) else None
    )

    attachment_summary = _build_attachment_summary(
        attachment_extraction if isinstance(attachment_extraction, dict) else None
    )

    recommendations = _build_recommendations(kpis)

    attention_events = _build_attention_events(
        classified=classified if isinstance(classified, list) else None,
        normalized=normalized if isinstance(normalized, list) else None,
        source_health=source_health,
    )

    evidence_links = _build_evidence_links(run_id)
    for link in evidence_links:
        aid = link["artifact_id"]
        from beeagent_module.interfaces.ui.artifacts import resolve_artifact_path

        path = resolve_artifact_path(storage_dir, run_id, aid)
        link["available"] = path is not None

    result: dict[str, Any] = {
        "run_id": run_id,
        "selected_run_id": run_id,
        "available_runs": run_ids,
        "status": "ok",
        "kpis": kpis,
        "funnel": funnel,
        "source_health": source_health,
        "classification_distribution": classification_distribution,
        "attachment_summary": attachment_summary,
        "recommendations": recommendations,
        "attention_events": attention_events,
        "evidence_links": evidence_links,
        "warnings": warnings,
    }

    # Preserve backward-compatible fields
    result["summary"] = summary if isinstance(summary, dict) else {}
    result["source_diagnostics"] = source_diag if isinstance(source_diag, dict) else {}
    result["intake_metadata"] = intake if isinstance(intake, dict) else {}

    # sources (legacy format)
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
                                "source_display_name", s.get("display_name", "")
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
                                "source_display_name", s.get("display_name", "")
                            ),
                            "status": s.get("status", ""),
                        }
                    )
    result["sources"] = sources

    result["classified_count"] = kpis.get("classified_count", 0)
    result["case_type_counts"] = classification_distribution.get("case_type_counts", {})
    result["priority_counts"] = classification_distribution.get("priority_counts", {})
    result["fallback_count"] = kpis.get("fallback_count", 0)
    result["normalized_count"] = kpis.get("normalized_count", 0)
    result["has_attachment_extraction"] = attachment_extraction is not None

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
