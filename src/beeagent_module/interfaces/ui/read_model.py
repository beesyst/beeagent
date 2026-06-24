from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from beeagent_module.cases.rop_dashboard import build_rop_dashboard
from beeagent_module.interfaces.ui.locale import t

ATTENTION_EVENTS_MAX = 50
ALLOWED_EVIDENCE_IDS: tuple[str, ...] = (
    "operator_summary_json",
    "source_diagnostics_json",
    "intake_metadata_json",
    "attachment_extraction_json",
    "normalized_events_json",
    "classified_events_json",
    "rop_review_table_tsv",
    "rop_current_state_json",
    "bitrix_reconciliation_json",
    "module_result_json",
    "rop_summary_result_json",
    "steps_json",
    "rop_mvp_pack_json",
    "rop_mvp_report_md",
)
EVIDENCE_LABELS: dict[str, str] = {
    "operator_summary_json": "Operator summary",
    "source_diagnostics_json": "Source diagnostics",
    "intake_metadata_json": "Intake metadata",
    "attachment_extraction_json": "Attachment extraction",
    "normalized_events_json": "Normalized events",
    "classified_events_json": "Classified events",
    "rop_review_table_tsv": "Review TSV",
    "rop_current_state_json": "ROP current state",
    "bitrix_reconciliation_json": "Bitrix reconciliation",
    "module_result_json": "Module result",
    "rop_summary_result_json": "ROP summary result",
    "steps_json": "Steps",
    "rop_mvp_pack_json": "ROP MVP pack (JSON)",
    "rop_mvp_report_md": "ROP MVP report (Markdown)",
}


def _read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
    except json.JSONDecodeError, OSError:
        pass
    return None


def _resolve_run_dir(storage_dir: Path, run_id: str) -> tuple[Path | None, str]:
    runs_dir = (storage_dir / "runs").resolve()
    run_dir = (runs_dir / run_id).resolve()

    try:
        run_dir.relative_to(runs_dir)
    except ValueError:
        return None, "invalid_run_id"

    if not run_dir.is_dir():
        return None, "not_found"

    return run_dir, ""


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
    modules_count = 0
    rop_classified = 0
    needs_review = 0
    degraded_count = 0
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
        classified = _read_json(latest_dir / "classified_events.json")
        if isinstance(classified, list):
            rop_classified = len(classified)
            needs_review = sum(
                1
                for c in classified
                if isinstance(c, dict)
                and (c.get("is_fallback") or c.get("priority") == "high")
            )
        source_diag = _read_json(latest_dir / "source_diagnostics.json")
        if isinstance(source_diag, dict):
            agg = source_diag.get("aggregate", {})
            if isinstance(agg, dict):
                degraded_count = _int(agg.get("degraded_source_count", 0))

    modules_path = storage_dir / "interfaces" / "modules.json"
    modules_data = _read_json(modules_path)
    if isinstance(modules_data, dict):
        registry = modules_data.get("registry", [])
        if isinstance(registry, list):
            modules_count = len(registry)

    kpi_items = [
        {"label": "Total Runs", "value": len(run_ids)},
        {"label": "Loaded Modules", "value": modules_count},
        {
            "label": "Latest Run Status",
            "value": latest_run["status"] if latest_run else "none",
        },
        {"label": "ROP Classified Cases", "value": rop_classified},
        {"label": "Needs Review", "value": needs_review},
        {"label": "Degraded Sources", "value": degraded_count},
    ]

    summary = {
        "total_runs": len(run_ids),
        "loaded_modules": modules_count,
        "rop_classified": rop_classified,
        "needs_review": needs_review,
        "degraded_sources": degraded_count,
    }
    if latest_run:
        summary["latest_run_id"] = latest_run["run_id"]
        summary["latest_run_status"] = latest_run["status"]

    return {
        "total_runs": len(run_ids),
        "recent_run_ids": run_ids[:10],
        "latest_run": latest_run,
        "kpi_items": kpi_items,
        "summary": summary,
        "layout": [],
    }


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


def build_run_detail(storage_dir: Path, run_id: str) -> dict[str, Any]:
    run_dir, error = _resolve_run_dir(storage_dir, run_id)
    if run_dir is None:
        return {"error": error, "run_id": run_id}

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


def build_modules_page_layout(
    data: dict[str, Any],
    locale: str = "en",
) -> list[dict[str, Any]]:
    rows = data.get("modules", [])
    if not rows:
        return [
            {
                "type": "attention_list",
                "size": "XL",
                "title": "Modules",
                "items": [
                    {
                        "label": "No modules",
                        "message": "No modules registered.",
                        "severity": "info",
                    }
                ],
            }
        ]

    table_rows: list[list[str]] = []
    for item in rows:
        table_rows.append(
            [
                str(item.get("id", "")),
                str(item.get("package", "")),
                str(item.get("entry", "")),
                str(item.get("state", "")),
                str(item.get("error", "")),
            ]
        )

    return [
        {
            "type": "status_table",
            "size": "XL",
            "title": t("Modules Overview", locale),
            "columns": ["ID", "Package", "Entry", "State", "Error"],
            "rows": table_rows,
        }
    ]


def _list_run_ids(runs_dir: Path) -> list[str]:
    if not runs_dir.is_dir():
        return []
    return sorted(
        (d.name for d in runs_dir.iterdir() if d.is_dir()),
        key=lambda n: (runs_dir / n).stat().st_mtime,
        reverse=True,
    )


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
        kpis["attachment_blocked_count"] = _int(
            agg.get("blocked_count", agg.get("refused_count", 0))
        )
    else:
        kpis["attachment_count"] = 0
        kpis["attachment_preview_count"] = 0
        kpis["attachment_refused_count"] = 0
        kpis["attachment_blocked_count"] = 0

    kpis["review_tsv_available"] = (run_dir / "rop_review_table.tsv").is_file()

    return kpis


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


def _build_source_health(
    source_diag: dict | None,
    intake: dict | None,
    classified: list | None,
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
        default["blocked_count"] = _int(
            agg.get("blocked_count", agg.get("refused_count", 0))
        )
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


def _event_timestamp(evt: dict[str, Any]) -> datetime | None:
    for key in ("event_date", "received_at", "timestamp", "created_at", "date"):
        raw = evt.get(key)
        if isinstance(raw, str) and raw.strip():
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                continue
    return None


def _int(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def build_rop_dashboard_read_model(
    storage_dir: Path,
    run_id: str | None = None,
    period: str | None = None,
    default_period: str | None = None,
    configured_periods: list[str] | None = None,
) -> dict[str, Any]:
    runs_dir = storage_dir / "runs"
    if not runs_dir.is_dir():
        return {"error": "no_runs", "message": "No runs directory"}

    run_ids = _list_run_ids(runs_dir)
    if run_id is None:
        if not run_ids:
            return {"error": "no_runs", "message": "No runs found"}
        run_id = run_ids[0]

    run_dir, error = _resolve_run_dir(storage_dir, run_id)
    if run_dir is None:
        return {"error": error, "run_id": run_id}

    summary = _read_json(run_dir / "operator_summary.json")
    source_diag = _read_json(run_dir / "source_diagnostics.json")
    intake = _read_json(run_dir / "intake_metadata.json")
    normalized = _read_json(run_dir / "normalized_events.json")
    classified = _read_json(run_dir / "classified_events.json")
    attachment_extraction = _read_json(run_dir / "attachment_extraction.json")
    current_state = _read_json(run_dir / "rop_current_state.json")
    bitrix_reconciliation = _read_json(run_dir / "bitrix_reconciliation.json")

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
    if current_state is None:
        warnings.append(
            {"code": "missing_artifact", "artifact": "rop_current_state.json"}
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

    current_state_kpi: dict[str, Any] = {}
    current_state_queues: dict[str, Any] = {}
    bitrix_state: dict[str, Any] = {}
    if isinstance(current_state, dict):
        kpi_data = current_state.get("kpi", {})
        if isinstance(kpi_data, dict):
            current_state_kpi = kpi_data
        queues = current_state.get("queues", {})
        if isinstance(queues, dict):
            current_state_queues = queues

    if isinstance(bitrix_reconciliation, dict):
        bitrix_agg = bitrix_reconciliation.get("aggregate", {})
        bitrix_state = {
            "status": bitrix_reconciliation.get("status", "unknown"),
            "matched_count": _int(bitrix_agg.get("matched_count", 0)),
            "not_found_count": _int(bitrix_agg.get("not_found_count", 0)),
            "ambiguous_count": _int(bitrix_agg.get("ambiguous_count", 0)),
            "duplicate_candidate_count": _int(
                bitrix_agg.get("duplicate_candidate_count", 0)
            ),
            "connector_error_count": _int(bitrix_agg.get("connector_error_count", 0)),
        }
    else:
        bitrix_state = {"status": "unreconciled"}

    effective_period = period or default_period
    allowed_periods = set(configured_periods or [])
    if period and allowed_periods and period not in allowed_periods:
        warnings.append(
            {
                "code": "invalid_period",
                "message": (
                    f"Invalid period '{period}', using default period "
                    f"'{default_period}'."
                ),
            }
        )
        effective_period = default_period

    dashboard_payload: dict[str, Any] = {}
    if effective_period:
        try:
            dashboard_payload = build_rop_dashboard(
                storage_dir=storage_dir,
                period=effective_period,
                logger=logging.getLogger("beeagent.ui.rop_dashboard"),
                run_id=run_id,
            )
        except ValueError:
            warnings.append(
                {
                    "code": "invalid_period",
                    "message": f"Invalid period '{effective_period}'",
                }
            )

    for warning in dashboard_payload.get("warnings", []):
        if isinstance(warning, dict):
            warnings.append(warning)

    business_kpi = dashboard_payload.get("business_kpi", {})
    if not isinstance(business_kpi, dict):
        business_kpi = {}
    series = dashboard_payload.get("series", {})
    if not isinstance(series, dict):
        series = {}
    queues = dashboard_payload.get("queues", {})
    if not isinstance(queues, dict):
        queues = {}
    rop_recommendations = dashboard_payload.get("rop_recommendations", [])
    if not isinstance(rop_recommendations, list):
        rop_recommendations = []

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
        "current_state_available": isinstance(current_state, dict),
        "current_state_kpi": current_state_kpi,
        "current_state_queues": current_state_queues,
        "bitrix": bitrix_state,
        "business_kpi": business_kpi,
        "series": series,
        "queues": queues,
        "rop_recommendations": rop_recommendations,
        "configured_periods": list(configured_periods or []),
        "default_period": default_period,
        "updated_at": dashboard_payload.get("generated_at_utc")
        if dashboard_payload
        else None,
        "period": dashboard_payload.get("period") if dashboard_payload else None,
        "period_start_utc": dashboard_payload.get("period_start_utc")
        if dashboard_payload
        else None,
        "period_end_utc": dashboard_payload.get("period_end_utc")
        if dashboard_payload
        else None,
        "time_basis": dashboard_payload.get("time_basis", "unknown")
        if dashboard_payload
        else "unknown",
    }

    result["summary"] = summary if isinstance(summary, dict) else {}
    result["source_diagnostics"] = source_diag if isinstance(source_diag, dict) else {}
    result["intake_metadata"] = intake if isinstance(intake, dict) else {}

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


def _nested_get(d: dict, path: tuple[str, ...], default: Any = None) -> Any:
    for key in path:
        if not isinstance(d, dict):
            return default
        d = d.get(key, {})
    return d if d != {} else default


def build_rop_page_layout(
    data: dict[str, Any],
    tab: str,
    locale: str = "en",
) -> list[dict[str, Any]]:
    if tab == "queue":
        return _build_rop_queue_layout(data, locale=locale)
    if tab == "sources":
        return _build_rop_sources_layout(data, locale=locale)
    if tab == "attachments":
        return _build_rop_attachments_layout(data, locale=locale)
    if tab == "evidence":
        return _build_rop_evidence_layout(data, locale=locale)
    if tab == "bitrix":
        return _build_rop_bitrix_layout(data, locale=locale)
    return _build_rop_overview_layout(data, locale=locale)


_PERIOD_LABELS: dict[str, str] = {
    "today": "Today",
    "yesterday": "Yesterday",
    "7d": "Last 7 days",
    "30d": "Last 30 days",
    "90d": "Last 3 months",
    "365d": "Last year",
    "all": "All time",
}
_OVERVIEW_PERIODS: tuple[str, ...] = (
    "today",
    "yesterday",
    "7d",
    "30d",
    "90d",
    "365d",
    "all",
)


def _period_label(period: str) -> str:
    return _PERIOD_LABELS.get(period, period)


def _overview_cell(value: object, tone: str = "") -> dict[str, str]:
    cell = {"label": str(value)}
    if tone:
        cell["tone"] = tone
    return cell


def _period_link_items(current_period: str, current_tab: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for period_value in _OVERVIEW_PERIODS:
        label = _period_label(period_value)
        if period_value == current_period:
            label = f"{label} (current)"
        items.append(
            {
                "label": label,
                "href": f"/rop?tab={current_tab}&period={period_value}",
            }
        )
    return items


def _initials(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "?"
    if "@" in text:
        text = text.split("@", 1)[0]
    parts = [part for part in text.replace(".", " ").replace("_", " ").split() if part]
    if not parts:
        return text[:1].upper()
    return "".join(part[:1].upper() for part in parts[:2])


def _bitrix_status_tone(status: object) -> str:
    value = str(status or "").lower()
    if value.startswith("matched"):
        return "success"
    if value in ("not_found", "ambiguous", "duplicate_candidate"):
        return "warning"
    if value in ("connector_degraded", "error"):
        return "danger"
    if value in ("unreconciled", "skipped", ""):
        return "info"
    return "unknown"


def _readable_quality_note(warning: dict[str, Any]) -> str:
    code = warning.get("code", "")
    if code == "time_basis_fallback":
        return (
            "Some leads had no source timestamp; dashboard used run time for "
            "period filtering."
        )
    if code == "degraded_sources":
        return "One or more sources reported degraded intake health."
    message = warning.get("message")
    return str(message) if message else "Review diagnostics for data quality notes."


def _chart_block(
    title: str,
    kind: str,
    chart_data: dict[str, Any],
) -> dict[str, Any]:
    block: dict[str, Any] = {
        "type": "chart",
        "size": "M",
        "title": title,
        "kind": kind,
        "series": chart_data.get("series", []),
        "empty_message": "No chart data for this period",
    }
    if kind == "donut":
        block["labels"] = chart_data.get("labels", [])
    else:
        block["categories"] = chart_data.get("labels", [])
    return block


_CHART_LABEL_MAP: dict[str, str] = {
    "new_lead": "New leads",
    "existing_client": "Existing clients",
    "existing_deal": "Existing deals",
    "existing_lead": "Existing leads",
    "follow_up": "Follow-ups",
    "reminder": "Reminders",
    "needs_review": "Needs review",
    "high_priority": "High priority",
    "matched": "Matched in Bitrix",
    "lost": "Lost in Bitrix",
    "ambiguous": "Ambiguous / duplicate",
    "unreconciled": "Not reconciled",
    "duplicate_candidate": "Duplicate candidate",
    "not_found": "Not found in Bitrix",
    "other": "Other",
}


def _humanize_label(raw: str) -> str:
    return _CHART_LABEL_MAP.get(raw, raw.replace("_", " ").title())


def _non_zero_segments(values: list[Any]) -> int:
    total = 0
    for value in values:
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value:
            total += 1
    return total


def _series_total(values: list[Any]) -> int:
    total = 0
    for value in values:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            total += int(value)
    return total


def _breakdown_block(
    title: str,
    labels: list[Any],
    values: list[Any],
    *,
    size: str = "M",
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for label, value in zip(labels, values, strict=False):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            items.append(
                {
                    "label": _humanize_label(str(label)),
                    "value": int(value),
                }
            )
    if not items:
        items.append({"label": "This period", "value": "No chart data"})
    return {
        "type": "state_grid",
        "size": size,
        "title": title,
        "items": items,
    }


def _chart_series_total(series_items: Any) -> int:
    if not isinstance(series_items, list):
        return 0
    total = 0
    for item in series_items:
        if not isinstance(item, dict):
            continue
        data = item.get("data", [])
        if isinstance(data, list):
            total += _series_total(data)
    return total


def _as_chart_series(chart_data: Any) -> list[dict[str, Any]]:
    if not isinstance(chart_data, dict):
        return []
    series_items = chart_data.get("series", [])
    return series_items if isinstance(series_items, list) else []


def _as_chart_labels(chart_data: Any) -> list[Any]:
    if not isinstance(chart_data, dict):
        return []
    labels = chart_data.get("labels", [])
    return labels if isinstance(labels, list) else []


def _parse_utc_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _day_label(value: datetime) -> str:
    return value.date().isoformat()


def _period_day_labels(period: str, period_end_utc: Any) -> list[str]:
    end = _parse_utc_datetime(period_end_utc) or datetime.now(timezone.utc)
    if period == "yesterday":
        return [_day_label(end - timedelta(days=1))]
    if period == "today":
        return [_day_label(end)]
    if period == "7d":
        days = 7
    elif period == "30d":
        days = 30
    else:
        return []
    start = end - timedelta(days=days - 1)
    return [_day_label(start + timedelta(days=offset)) for offset in range(days)]


def _bucket_daily_chart_series(
    chart_data: Any,
    *,
    period: str,
    period_end_utc: Any,
) -> tuple[list[str], list[dict[str, Any]]]:
    labels = [str(label) for label in _as_chart_labels(chart_data)]
    series_items = _as_chart_series(chart_data)
    target_labels = _period_day_labels(period, period_end_utc) or labels
    if not target_labels:
        return [], series_items

    label_index = {label: index for index, label in enumerate(labels)}
    bucketed: list[dict[str, Any]] = []
    for item in series_items:
        if not isinstance(item, dict):
            continue
        source_values = item.get("data", [])
        if not isinstance(source_values, list):
            source_values = []
        values: list[int] = []
        for label in target_labels:
            source_index = label_index.get(label)
            if source_index is None or source_index >= len(source_values):
                values.append(0)
            else:
                values.append(_int(source_values[source_index]))
        bucketed.append(
            {
                "name": _humanize_label(str(item.get("name", "Processed"))),
                "data": values,
            }
        )
    return target_labels, bucketed


def _source_display_labels(source_health: list[Any]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for item in source_health:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("source_id", "")).strip()
        display_name = str(
            item.get("display_name") or item.get("source_display_name") or ""
        ).strip()
        if source_id and display_name:
            labels[source_id] = display_name
    return labels


def _period_href(tab: str, period: str) -> str:
    return f"/rop?tab={tab}&period={period}"


def _collect_priority_queue_preview(
    queues: dict[str, Any],
    current_period: str,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    order = (
        "high_priority",
        "needs_review",
        "ambiguous",
        "lost_in_bitrix",
        "unreconciled",
        "degraded",
    )
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for bucket in order:
        items = queues.get(bucket, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            event_id = str(item.get("event_id", ""))
            if event_id and event_id in seen:
                continue
            if event_id:
                seen.add(event_id)
            subject = item.get("subject") or (
                f"Lead event {event_id}" if event_id else "Lead event"
            )
            sender = (
                item.get("sender")
                or item.get("source_display_name")
                or item.get("source_id")
                or "Unknown sender"
            )
            priority = item.get("bot_priority") or item.get("priority") or bucket
            next_step = item.get("recommended_next_step") or "Open Queue"
            evidence_href = item.get("evidence_href") or _period_href(
                "queue", current_period
            )
            rows.append(
                {
                    "priority": {
                        "label": _humanize_label(str(priority)),
                        "tone": "danger"
                        if priority == "high" or bucket == "high_priority"
                        else "warning"
                        if bucket in {"needs_review", "ambiguous", "lost_in_bitrix"}
                        else "info",
                    },
                    "sender": sender,
                    "subject": subject,
                    "reason": _humanize_label(
                        str(item.get("reason") or item.get("review_reason", bucket))
                    ),
                    "next_step": next_step.replace("_", " "),
                    "evidence": {"label": "Open", "href": evidence_href},
                }
            )
            if len(rows) >= limit:
                return rows
    return rows


def _build_rop_overview_layout(
    data: dict[str, Any], locale: str = "en"
) -> list[dict[str, Any]]:
    _ = locale
    business_kpi = data.get("business_kpi", {})
    if not isinstance(business_kpi, dict):
        business_kpi = {}
    kpis = data.get("kpis", {})
    series = data.get("series", {})
    if not isinstance(series, dict):
        series = {}
    source_health = data.get("source_health", [])
    if not isinstance(source_health, list):
        source_health = []
    warnings_list = data.get("warnings", [])
    if not isinstance(warnings_list, list):
        warnings_list = []
    current_period = data.get("period", "")
    period_hint = _period_label(current_period) if current_period else ""
    updated_at = data.get("updated_at") or data.get("generated_at_utc") or ""

    layout: list[dict[str, Any]] = []

    total_leads = business_kpi.get("processed_events", 0)
    new_leads = business_kpi.get("new_leads", 0)
    high_priority = business_kpi.get("high_priority", 0)
    needs_review = business_kpi.get("needs_review", 0)
    lost_in_bitrix = business_kpi.get("lost_in_bitrix", 0)
    unreconciled = business_kpi.get("unreconciled", 0)
    ambiguous_or_duplicate = business_kpi.get("ambiguous_or_duplicate", 0)
    bitrix_errors = business_kpi.get("bitrix_errors", 0)

    source_count = kpis.get("source_count", 0)
    degraded_sources = kpis.get("degraded_source_count", 0)
    classified_count = kpis.get("classified_count", 0)
    loaded_count = kpis.get("loaded_count", 0)
    source_summary = (
        f"{source_count} / {degraded_sources} degraded"
        if degraded_sources
        else f"{source_count} connected"
    )
    bitrix_summary = (
        f"{unreconciled} not reconciled"
        if unreconciled
        else ("OK" if not lost_in_bitrix else f"{lost_in_bitrix} lost")
    )
    readable_warnings = [
        _readable_quality_note(w) for w in warnings_list if isinstance(w, dict)
    ]
    data_quality = readable_warnings[0] if readable_warnings else "OK"
    period_emails = _int(
        business_kpi.get(
            "processed_emails",
            business_kpi.get("processed_events", kpis.get("loaded_count", 0)),
        )
    )
    todays_emails = period_emails
    if current_period == "today":
        todays_emails = period_emails

    action_required_count = (
        _int(high_priority)
        + _int(needs_review)
        + _int(ambiguous_or_duplicate)
        + _int(unreconciled)
        + _int(business_kpi.get("source_degraded", degraded_sources))
        + _int(business_kpi.get("attachment_refused", 0))
        + _int(bitrix_errors)
    )
    action_required_ratio = int(
        min(100, round((action_required_count / max(_int(total_leads), 1)) * 100))
    )
    bitrix_gap_count = (
        _int(unreconciled) + _int(lost_in_bitrix) + _int(ambiguous_or_duplicate)
    )
    data_quality_count = (
        _int(business_kpi.get("source_degraded", degraded_sources))
        + _int(business_kpi.get("attachment_refused", 0))
        + _int(bitrix_errors)
        + len(readable_warnings)
    )
    configured_periods = data.get("configured_periods", [])
    configured_values = (
        {str(value) for value in configured_periods}
        if isinstance(configured_periods, list)
        else set()
    )
    period_actions = [
        item
        for item in _period_link_items(current_period, "overview")
        if item["href"].rsplit("=", 1)[-1] in configured_values
    ]
    queue_href = _period_href("queue", current_period)
    bitrix_href = _period_href("bitrix", current_period)
    evidence_href = _period_href("evidence", current_period)

    processed_by_day = series.get("processed_by_day", {})
    workload_labels, workload_series = _bucket_daily_chart_series(
        processed_by_day,
        period=str(current_period or ""),
        period_end_utc=data.get("period_end_utc"),
    )
    source_label_map = _source_display_labels(source_health)

    layout.append(
        {
            "type": "operator_hero",
            "width": 6,
            "title": "ROP Control Center",
            "subtitle": "Inbound email intake, lead quality and Bitrix reconciliation",
            "status": period_hint,
            "items": [
                {"label": "TODAY'S EMAILS", "value": todays_emails},
                {"label": "NEW LEADS", "value": new_leads},
                {"label": "Period", "value": period_hint},
                {"label": "Sources", "value": source_summary},
                {"label": "Bitrix", "value": bitrix_summary},
                {"label": "Data quality", "value": data_quality},
            ],
            "primary_links": period_actions
            + [
                {"label": "Open Queue", "href": queue_href},
                {"label": "Open Bitrix", "href": bitrix_href},
            ],
        }
    )
    layout.append(
        {
            "type": "chart",
            "width": 3,
            "title": "Email Workload",
            "subtitle": (f"{period_emails} processed inbound items in selected period"),
            "kind": "area",
            "series": workload_series
            or [{"name": "Processed", "data": [period_emails]}],
            "categories": workload_labels or [period_hint or "Selected period"],
            "height": 180,
            "empty_message": "No chart data for this period",
        }
    )
    layout.append(
        {
            "type": "chart",
            "width": 3,
            "title": "Action Required",
            "subtitle": (
                f"{action_required_count} items need review · "
                f"{action_required_ratio}% action ratio"
            ),
            "kind": "donut",
            "series": [
                action_required_count,
                max(_int(total_leads) - action_required_count, 0),
            ],
            "labels": ["Needs attention", "Clear"],
            "height": 180,
            "empty_message": "No chart data for this period",
        }
    )

    small_cards = [
        {
            "type": "venue_card",
            "width": 3,
            "title": "Urgent leads",
            "subtitle": "Open now",
            "status": str(high_priority),
            "items": [{"label": "Count", "value": high_priority}],
            "links": [{"label": "Open Queue", "href": queue_href}],
        },
        {
            "type": "venue_card",
            "width": 3,
            "title": "Needs review",
            "subtitle": "Operator queue",
            "status": str(needs_review),
            "items": [{"label": "Count", "value": needs_review}],
            "links": [{"label": "Open Queue", "href": queue_href}],
        },
        {
            "type": "venue_card",
            "width": 3,
            "title": "Bitrix gaps",
            "subtitle": "Check CRM evidence",
            "status": str(bitrix_gap_count),
            "items": [{"label": "Count", "value": bitrix_gap_count}],
            "links": [{"label": "Open Bitrix", "href": bitrix_href}],
        },
        {
            "type": "venue_card",
            "width": 3,
            "title": "Data quality",
            "subtitle": "Timestamp/source/attachment issues",
            "status": str(data_quality_count),
            "items": [{"label": "Issues", "value": data_quality_count}],
            "links": [{"label": "Open Evidence", "href": evidence_href}],
        },
    ]
    layout.extend(small_cards)

    layout.append(
        {
            "type": "chart",
            "size": "M",
            "title": "Email intake trend",
            "kind": "area",
            "series": workload_series
            or [{"name": "Processed", "data": [period_emails]}],
            "categories": workload_labels or [period_hint or "Selected period"],
            "height": 240,
            "empty_message": "No chart data for this period",
        }
    )

    outcome_labels = [
        "New leads",
        "Existing clients",
        "Follow-ups",
        "Needs review",
        "High priority",
    ]
    outcome_values = [
        _int(new_leads),
        _int(business_kpi.get("existing_clients", 0)),
        _int(business_kpi.get("follow_ups", 0)),
        _int(needs_review),
        _int(high_priority),
    ]
    layout.append(
        {
            "type": "chart",
            "size": "M",
            "title": "Lead outcome mix",
            "kind": "bar",
            "series": [{"name": "Leads", "data": outcome_values}],
            "categories": outcome_labels,
            "height": 240,
            "empty_message": "No chart data for this period",
        }
    )

    bitrix_labels = [
        "Matched in Bitrix",
        "Lost in Bitrix",
        "Ambiguous / duplicate",
        "Not reconciled",
    ]
    bitrix_values = [
        _int(business_kpi.get("matched_in_bitrix", 0)),
        _int(lost_in_bitrix),
        _int(ambiguous_or_duplicate),
        _int(unreconciled),
    ]
    layout.append(
        {
            "type": "chart",
            "size": "M",
            "title": "Bitrix reconciliation",
            "kind": "bar",
            "series": [{"name": "Leads", "data": bitrix_values}],
            "categories": bitrix_labels,
            "height": 240,
            "empty_message": "No chart data for this period",
        }
    )

    source_data = series.get("source_contribution", {})
    source_labels = _as_chart_labels(source_data)
    source_values = (
        source_data.get("series", []) if isinstance(source_data, dict) else []
    )
    source_categories = [
        source_label_map.get(str(label), _humanize_label(str(label)))
        for label in source_labels
    ]
    layout.append(
        {
            "type": "chart",
            "size": "M",
            "title": "Source contribution",
            "kind": "bar",
            "series": [{"name": "Leads", "data": source_values or [0]}],
            "categories": source_categories or ["No data"],
            "height": 240,
            "empty_message": "No chart data for this period",
        }
    )

    queues = data.get("queues", {})
    if not isinstance(queues, dict):
        queues = {}
    preview_rows = _collect_priority_queue_preview(queues, current_period)
    layout.append(
        {
            "type": "data_table",
            "size": "XL",
            "title": "Priority review queue",
            "compact": True,
            "mobile": "md",
            "columns": [
                {"key": "priority", "label": "Priority/status", "cell": "badge"},
                {"key": "sender", "label": "Sender / source", "cell": "text"},
                {"key": "subject", "label": "Subject", "cell": "text"},
                {"key": "reason", "label": "Reason", "cell": "muted"},
                {
                    "key": "next_step",
                    "label": "Recommended next step",
                    "cell": "muted",
                },
                {"key": "evidence", "label": "Open", "cell": "link"},
            ],
            "rows": preview_rows,
        }
    )

    return layout


def _build_rop_queue_layout(
    data: dict[str, Any], locale: str = "en"
) -> list[dict[str, Any]]:
    attention_events = data.get("attention_events", [])
    queues = data.get("queues", {})
    if not isinstance(queues, dict):
        queues = {}

    queue_specs = (
        "high_priority",
        "needs_review",
        "lost_in_bitrix",
        "ambiguous",
        "degraded",
        "unreconciled",
    )
    queue_rows: list[dict[str, Any]] = []
    seen_event_ids: set[str] = set()
    for key in queue_specs:
        rows_source = queues.get(key, [])
        if not isinstance(rows_source, list):
            continue
        for item in rows_source:
            if not isinstance(item, dict):
                continue
            event_id = str(item.get("event_id", ""))
            if event_id and event_id in seen_event_ids:
                continue
            if event_id:
                seen_event_ids.add(event_id)
            queue_rows.append(item)

    if queue_rows:
        return [_queue_table("ROP Work Queue", queue_rows)]

    if not attention_events:
        return [
            {
                "type": "state_grid",
                "size": "XL",
                "title": t("Operator Queue", locale),
                "items": [
                    {
                        "label": "No events",
                        "value": "Queue is empty",
                        "status": "clear",
                    }
                ],
            }
        ]

    q_items: list[dict[str, Any]] = []
    for evt in attention_events:
        reasons: list[str] = []
        if evt.get("priority") == "high":
            reasons.append("High priority")
        if evt.get("is_fallback"):
            reasons.append("Fallback")
        conf = evt.get("confidence")
        if isinstance(conf, (int, float)) and conf < 0.7:
            reasons.append(f"Low conf ({conf:.2f})")

        q_items.append(
            {
                "label": evt.get("event_id", ""),
                "value": f"{evt.get('source_display_name', evt.get('source_id', ''))} | "
                f"{evt.get('sender', '')} | {evt.get('subject', '')} | "
                f"Type: {evt.get('case_type', '')} | Priority: {evt.get('priority', '')} | "
                f"Reason: {'; '.join(reasons) if reasons else evt.get('review_reason', 'Needs review')}",
                "status": "urgent"
                if evt.get("priority") == "high"
                else ("review" if evt.get("is_fallback") else ""),
            }
        )

    return [
        {
            "type": "state_grid",
            "size": "XL",
            "title": t("Operator Queue", locale),
            "items": q_items,
        }
    ]


def _queue_table(title: str, rows_source: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for item in rows_source[:50]:
        if not isinstance(item, dict):
            continue
        event_id = str(item.get("event_id", ""))
        priority = item.get("bot_priority") or item.get("priority", "n/a")
        bitrix_status = item.get("bitrix_status", "unreconciled")
        evidence_href = item.get("evidence_href") or (
            f"/rop?tab=evidence#event-{event_id}" if event_id else "/rop?tab=evidence"
        )
        rows.append(
            {
                "priority": {
                    "label": priority,
                    "tone": "danger" if priority == "high" else "secondary",
                },
                "client": {
                    "title": item.get("sender", "") or "Unknown sender",
                    "subtitle": item.get("source_display_name")
                    or item.get("source_id", ""),
                    "initials": _initials(item.get("sender", "")),
                    "color": "red" if priority == "high" else "blue",
                },
                "subject": item.get("subject", ""),
                "classification": item.get("bot_case_type")
                or item.get("case_type", ""),
                "bitrix_status": {
                    "label": bitrix_status,
                    "status": _bitrix_status_tone(bitrix_status),
                },
                "reason": item.get("reason") or item.get("review_reason", ""),
                "next_step": item.get("recommended_next_step", ""),
                "evidence": {
                    "label": "Evidence",
                    "href": evidence_href,
                },
            }
        )

    return {
        "type": "data_table",
        "size": "XL",
        "title": title,
        "striped": True,
        "mobile": "md",
        "columns": [
            {"key": "priority", "label": "Priority", "cell": "badge"},
            {"key": "client", "label": "Sender / Client", "cell": "avatar_text"},
            {"key": "subject", "label": "Subject / Request", "cell": "text"},
            {"key": "classification", "label": "Classification", "cell": "text"},
            {"key": "bitrix_status", "label": "Bitrix status", "cell": "status"},
            {"key": "reason", "label": "Reason", "cell": "muted"},
            {"key": "next_step", "label": "Recommended next step", "cell": "muted"},
            {"key": "evidence", "label": "Evidence link", "cell": "link"},
        ],
        "rows": rows,
    }


def _build_rop_sources_layout(
    data: dict[str, Any], locale: str = "en"
) -> list[dict[str, Any]]:
    source_health = data.get("source_health", [])

    if not source_health:
        return [
            {
                "type": "state_grid",
                "size": "XL",
                "title": t("Source Health", locale),
                "items": [
                    {
                        "label": "No sources",
                        "value": "No source data available",
                        "status": "empty",
                    }
                ],
            }
        ]

    columns = [
        "Source",
        "Type",
        "Status",
        "Reason",
        "Fetched",
        "Loaded",
        "Malformed",
        "Classified",
    ]
    rows: list[list[str]] = []
    for sh in source_health:
        rows.append(
            [
                sh.get("display_name", sh.get("source_id", "")),
                sh.get("source_type", ""),
                sh.get("status", ""),
                sh.get("reason", "") or "",
                str(sh.get("fetched_count", 0)),
                str(sh.get("loaded_count", 0)),
                str(sh.get("malformed_count", 0)),
                str(sh.get("classified_count", 0)),
            ]
        )

    return [
        {
            "type": "status_table",
            "size": "XL",
            "title": "Source Health Details",
            "columns": columns,
            "rows": rows,
        }
    ]


def _build_rop_attachments_layout(
    data: dict[str, Any],
    locale: str = "en",
) -> list[dict[str, Any]]:
    att_summary = data.get("attachment_summary", {})

    if not att_summary or att_summary.get("total_attachments", 0) == 0:
        return [
            {
                "type": "state_grid",
                "size": "XL",
                "title": t("Attachment Processing", locale),
                "items": [
                    {
                        "label": "No attachments",
                        "value": "No attachment data available",
                        "status": "empty",
                    }
                ],
            }
        ]

    kpi_items: list[dict[str, Any]] = [
        {
            "label": "Total Attachments",
            "value": att_summary.get("total_attachments", 0),
        },
        {
            "label": "Preview Available",
            "value": att_summary.get("preview_available_count", 0),
        },
        {"label": "Refused", "value": att_summary.get("refused_count", 0)},
        {"label": "Blocked", "value": att_summary.get("blocked_count", 0)},
        {"label": "Unsupported", "value": att_summary.get("unsupported_count", 0)},
        {
            "label": "Extraction Errors",
            "value": att_summary.get("extraction_error_count", 0),
        },
    ]

    return [
        {
            "type": "kpi_grid",
            "size": "XL",
            "title": t("Attachment Processing", locale),
            "items": kpi_items,
        }
    ]


def _build_rop_evidence_layout(
    data: dict[str, Any],
    locale: str = "en",
) -> list[dict[str, Any]]:
    evidence_links = data.get("evidence_links", [])

    if not evidence_links:
        return [
            {
                "type": "quick_links",
                "size": "XL",
                "title": t("Evidence & Exports", locale),
                "items": [],
            }
        ]

    link_items: list[dict[str, Any]] = []
    for link in evidence_links:
        if link.get("available"):
            link_items.append(
                {
                    "label": link.get("label", link.get("artifact_id", "")),
                    "href": link.get("url", ""),
                }
            )

    return [
        {
            "type": "quick_links",
            "size": "XL",
            "title": t("Evidence & Exports", locale),
            "items": link_items,
        }
    ]


def _build_rop_bitrix_layout(
    data: dict[str, Any],
    locale: str = "en",
) -> list[dict[str, Any]]:
    _ = locale
    current_state_kpi = data.get("current_state_kpi", {})
    if not isinstance(current_state_kpi, dict):
        current_state_kpi = {}
    current_state_queues = data.get("current_state_queues", {})
    if not isinstance(current_state_queues, dict):
        current_state_queues = {}
    bitrix_state = data.get("bitrix", {})
    if not isinstance(bitrix_state, dict):
        bitrix_state = {}
    evidence_links = data.get("evidence_links", [])
    business_kpi = data.get("business_kpi", {})
    if not isinstance(business_kpi, dict):
        business_kpi = {}
    period_queues = data.get("queues", {})
    if not isinstance(period_queues, dict):
        period_queues = {}

    bitrix_available = any(
        link.get("artifact_id") == "bitrix_reconciliation_json"
        and link.get("available")
        for link in evidence_links
        if isinstance(link, dict)
    )

    if not bitrix_available:
        return [
            {
                "type": "state_grid",
                "size": "XL",
                "title": "Bitrix Evidence Board",
                "items": [
                    {
                        "label": "Not reconciled",
                        "value": (
                            "Bitrix reconciliation artifact is not available for this run. "
                            "Run read-only reconcile-bitrix to create CRM evidence."
                        ),
                        "status": "read-only",
                    }
                ],
            }
        ]

    ambiguous_count = _int(current_state_kpi.get("ambiguous_in_bitrix", 0))
    if "bitrix_errors" in business_kpi:
        connector_degraded_count = _int(business_kpi.get("bitrix_errors", 0))
    else:
        connector_degraded_count = _int(
            current_state_kpi.get(
                "connector_degraded",
                bitrix_state.get("connector_error_count", 0),
            )
        )

    layout: list[dict[str, Any]] = [
        {
            "type": "kpi_grid",
            "size": "XL",
            "columns": 3,
            "title": "Bitrix Evidence Board",
            "items": [
                {
                    "label": "Bitrix Status",
                    "value": bitrix_state.get("status", "unknown"),
                },
                {
                    "label": "Matched",
                    "value": business_kpi.get("matched_in_bitrix", 0),
                },
                {
                    "label": "Lost in Bitrix",
                    "value": business_kpi.get("lost_in_bitrix", 0),
                },
                {
                    "label": "Ambiguous",
                    "value": business_kpi.get(
                        "ambiguous_or_duplicate", ambiguous_count
                    ),
                },
                {
                    "label": "Connector Degraded",
                    "value": connector_degraded_count,
                },
                {
                    "label": "Unreconciled",
                    "value": business_kpi.get("unreconciled", 0),
                },
            ],
        }
    ]

    queue_specs = [
        ("lost_in_bitrix", "Lost in Bitrix"),
        ("ambiguous", "Ambiguous"),
        ("degraded", "Connector Degraded"),
        ("unreconciled", "Unreconciled"),
        ("matched", "Matched"),
    ]
    for queue_id, title in queue_specs:
        if queue_id in period_queues:
            queue_items = period_queues.get(queue_id, [])
        else:
            queue_items = current_state_queues.get(queue_id, [])
        if not isinstance(queue_items, list):
            queue_items = []

        rows: list[list[str]] = []
        for item in queue_items[:50]:
            if not isinstance(item, dict):
                continue
            rows.append(
                [
                    str(item.get("event_id", "")),
                    str(item.get("bot_case_type") or item.get("case_type", "")),
                    str(item.get("bot_priority") or item.get("priority", "")),
                    str(item.get("bitrix_status", "")),
                ]
            )

        layout.append(
            {
                "type": "status_table",
                "size": "XL",
                "title": title,
                "columns": ["Event ID", "Case Type", "Priority", "Bitrix Status"],
                "rows": rows,
            }
        )

    return layout
