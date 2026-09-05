from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from beeagent_module.cases.rop_dashboard import (
    ALLOWED_BITRIX_STATUSES,
    ALLOWED_PAGE_SIZES,
    ALLOWED_QUEUE_IDS,
    DEFAULT_PAGE_SIZE,
    _event_needs_review,
    _list_rop_run_ids,
    apply_queue_filters,
    build_rop_dashboard,
    paginate_items,
    read_rop_web_projection_v2_view,
    rop_web_projection_entry_path,
    rop_web_projection_index,
    rop_web_projection_v2_manifest,
    sort_queue_items,
)
from beeagent_module.core.rop_final_decision import load_or_build_final_decisions
from beeagent_module.interfaces.ui.locale import case_type_label, t
from beeagent_module.interfaces.ui.url_builder import build_rop_event_url, build_rop_url

ATTENTION_EVENTS_MAX = 500
ALLOWED_EVIDENCE_IDS: tuple[str, ...] = (
    "operator_summary_json",
    "source_diagnostics_json",
    "intake_metadata_json",
    "attachment_extraction_json",
    "attachment_manifest_json",
    "attachment_analysis_json",
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
    "mailbox_selection_json",
    "mail_thread_index_json",
    "mail_thread_context_json",
    "rop_ai_assist_requests_json",
    "rop_ai_assist_decisions_json",
    "rop_ai_assist_results_json",
    "rop_ai_adjudicator_requests_json",
    "rop_ai_adjudicator_decisions_json",
    "rop_ai_adjudicator_results_json",
    "rop_final_decisions_json",
)
EVIDENCE_LABELS: dict[str, str] = {
    "operator_summary_json": "Operator summary",
    "source_diagnostics_json": "Source diagnostics",
    "intake_metadata_json": "Intake metadata",
    "attachment_extraction_json": "Attachment extraction",
    "attachment_manifest_json": "Attachment manifest",
    "attachment_analysis_json": "Attachment analysis",
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
    "mailbox_selection_json": "Mailbox selection",
    "mail_thread_index_json": "Mail thread index",
    "mail_thread_context_json": "Mail thread context",
    "rop_ai_assist_requests_json": "ROP AI assist requests",
    "rop_ai_assist_decisions_json": "ROP AI assist decisions",
    "rop_ai_assist_results_json": "ROP AI assist results",
    "rop_ai_adjudicator_requests_json": "ROP AI adjudicator requests",
    "rop_ai_adjudicator_decisions_json": "ROP AI adjudicator decisions",
    "rop_ai_adjudicator_results_json": "ROP AI adjudicator results",
    "rop_final_decisions_json": "ROP final decisions",
}

_TRUSTED_ATTACH_PROVENANCES = frozenset({"thread_resolved", "bitrix_outbound_exact"})
def _trusted_attach_operational_case_types(
    storage_dir: Path,
) -> dict[tuple[str, str, str, str], str]:
    result: dict[tuple[str, str, str, str], str] = {}
    path = storage_dir / "interfaces" / "rop_writeback_state.json"
    if not path.exists():
        return result
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError, TypeError:
        return result
    if not isinstance(data, dict):
        return result
    events = data.get("events")
    if not isinstance(events, dict):
        return result
    for record in events.values():
        if not isinstance(record, dict):
            continue
        if record.get("outcome") != "attach_existing":
            continue
        provenance = record.get("target_provenance")
        if (
            not isinstance(provenance, str)
            or provenance not in _TRUSTED_ATTACH_PROVENANCES
        ):
            continue
        event_id = record.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            continue
        key = (
            str(record.get("last_run_id") or ""),
            str(record.get("source_id") or ""),
            event_id,
            str(record.get("event_instance_id") or ""),
        )
        result[key] = "existing_deal"
    return result


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


def build_dashboard(storage_dir: Path, locale: str = "en") -> dict[str, Any]:
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
                1 for c in classified if isinstance(c, dict) and _event_needs_review(c)
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
        {"label": t("Total Runs", locale), "value": len(run_ids)},
        {"label": t("Loaded Modules", locale), "value": modules_count},
        {
            "label": t("Latest Run Status", locale),
            "value": latest_run["status"] if latest_run else "none",
        },
        {"label": t("ROP Classified Cases", locale), "value": rop_classified},
        {"label": t("Needs Review", locale), "value": needs_review},
        {"label": t("Degraded Sources", locale), "value": degraded_count},
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
        "title": t("BeeAgent Dashboard", locale),
        "subtitle": t("Read-only operator dashboard", locale),
        "total_runs": len(run_ids),
        "recent_run_ids": run_ids[:10],
        "latest_run": latest_run,
        "kpi_items": kpi_items,
        "summary": summary,
        "layout": [],
    }


def build_runs_list(storage_dir: Path, locale: str = "en") -> dict[str, Any]:
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
        "title": t("Runs", locale),
        "subtitle": t("Run history", locale),
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
                "title": t("Modules", locale),
                "items": [
                    {
                        "label": t("No modules", locale),
                        "message": t("No modules registered.", locale),
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
            "columns": [
                t("ID", locale),
                t("Package", locale),
                t("Entry", locale),
                t("State", locale),
                t("Error", locale),
            ],
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
    total_runs: int,
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
        "total_runs": total_runs,
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

    if isinstance(classified, list):
        review_candidates = sum(
            1 for c in classified if isinstance(c, dict) and _event_needs_review(c)
        )
    else:
        review_candidates = 0
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


def _build_it30_recommendations(
    latest_selection: dict[str, Any],
    thread_summary: dict[str, Any],
    ai_assist_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []

    selected_count = latest_selection.get("selected_count", 0)
    if selected_count == 0:
        recs.append(
            {
                "code": "empty_latest_selection",
                "severity": "info",
                "title": "No latest-N selection data",
                "message": "No emails were selected in the latest batch. Check source diagnostics.",
                "count": 0,
            }
        )

    events_with_thread = thread_summary.get("events_with_thread_context", 0)
    if events_with_thread > 0:
        recs.append(
            {
                "code": "review_threaded_conversations",
                "severity": "info",
                "title": "Review threaded conversations",
                "message": (
                    f"{events_with_thread} event(s) have thread context. "
                    "Review threaded conversations first."
                ),
                "count": events_with_thread,
            }
        )

    degraded_ai = ai_assist_summary.get("degraded_count", 0)
    if degraded_ai > 0:
        recs.append(
            {
                "code": "review_ai_degraded",
                "severity": "warning",
                "title": "Review AI degraded events",
                "message": (
                    f"{degraded_ai} AI assist event(s) were degraded. "
                    "Manual review recommended."
                ),
                "count": degraded_ai,
            }
        )

    module_unavailable = ai_assist_summary.get("module_contract_unavailable_count", 0)
    if module_unavailable > 0:
        recs.append(
            {
                "code": "check_ai_merge_contract",
                "severity": "info",
                "title": "Check ai_assist_merge module contract",
                "message": (
                    f"{module_unavailable} event(s) could not use AI assist "
                    "due to unavailable module contract."
                ),
                "count": module_unavailable,
            }
        )

    low_conf_ai = ai_assist_summary.get("low_confidence_count", 0)
    if low_conf_ai > 0:
        recs.append(
            {
                "code": "review_low_confidence_ai",
                "severity": "warning",
                "title": "Review low-confidence AI assist events",
                "message": (
                    f"{low_conf_ai} AI assist result(s) had low confidence. "
                    "Manual review recommended."
                ),
                "count": low_conf_ai,
            }
        )

    return recs


def _resolve_sender(
    norm: dict[str, Any] | None,
    classified_item: dict[str, Any],
) -> str:
    for key in ("sender", "from_email", "from"):
        value = norm.get(key) if norm else None
        if isinstance(value, str) and value.strip() and "Unknown" not in value:
            return value
    for key in ("sender", "from_email", "from"):
        value = classified_item.get(key)
        if isinstance(value, str) and value.strip() and "Unknown" not in value:
            return value
    return "Unknown Sender"


def _resolve_subject(
    norm: dict[str, Any] | None,
    classified_item: dict[str, Any],
) -> str:
    for key in ("subject",):
        value = norm.get(key) if norm else None
        if isinstance(value, str) and value.strip() and value not in ("n/a", ""):
            return value
    value = classified_item.get("subject")
    if isinstance(value, str) and value.strip() and value not in ("n/a", ""):
        return value
    return "n/a"


def _build_attention_events(
    classified: list | None,
    normalized: list | None,
    source_health: list[dict[str, Any]],
    locale: str = "en",
    run_id: str = "",
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not isinstance(classified, list):
        return events

    norm_by_id: dict[tuple[str, str], dict] = {}
    if isinstance(normalized, list):
        for n in normalized:
            if isinstance(n, dict):
                eid = n.get("event_id") or n.get("original_event_id")
                if eid:
                    norm_by_id[(str(eid), str(n.get("event_instance_id") or ""))] = n

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
        event_instance_id = str(item.get("event_instance_id") or "")
        norm = norm_by_id.get((str(eid), event_instance_id), {})
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

        sender = _resolve_sender(norm, item)
        subject = _resolve_subject(norm, item)

        raw_date = (
            item.get("event_date")
            or item.get("received_at")
            or norm.get("event_date")
            or norm.get("received_at", "")
        )

        evt = {
            "event_id": eid,
            "event_instance_id": event_instance_id,
            "run_id": run_id,
            "source_id": sid,
            "source_display_name": src_display.get(sid, ""),
            "sender": sender,
            "subject": subject,
            "case_type": item.get("case_type", ""),
            "priority": item.get("priority", ""),
            "date": raw_date,
            "confidence": conf,
            "reason_code": item.get("reason_code", ""),
            "is_fallback": bool(item.get("is_fallback")),
            "attachment_count": _int(
                norm.get("attachment_count", item.get("attachment_count", 0))
            ),
            "review_reason": "; ".join(reasons),
            "detail_href": _rop_event_detail_href(
                str(eid), run_id, locale, event_instance_id=event_instance_id
            )
            if eid and run_id
            else None,
        }
        for key in (
            "recommended_queue",
            "recommended_next_step",
            "correct_action",
            "should_rop_see",
        ):
            if key in item:
                evt[key] = item[key]
        events.append(evt)

    return events


def _canonical_queue_rows(
    queues: dict[str, Any],
    attention_events: list[dict[str, Any]],
    filter_params: dict[str, str],
) -> list[dict[str, Any]]:
    queue_filter = filter_params.get("queue", "").strip()
    queue_ids: tuple[str, ...] = (
        (queue_filter,) if queue_filter in ALLOWED_QUEUE_IDS else ALLOWED_QUEUE_IDS
    )
    rows: list[dict[str, Any]] = []
    seen_identities: set[tuple[str, str, str, str]] = set()
    for queue_id in queue_ids:
        source_rows = queues.get(queue_id, [])
        if not isinstance(source_rows, list):
            continue
        for item in source_rows:
            if not isinstance(item, dict):
                continue
            event_id = str(item.get("event_id", ""))
            identity = (
                str(item.get("run_id") or ""),
                str(item.get("source_id") or ""),
                event_id,
                str(item.get("event_instance_id") or ""),
            )
            if event_id and identity in seen_identities:
                continue
            if event_id:
                seen_identities.add(identity)
            rows.append(item)

    if rows or queue_filter in ALLOWED_QUEUE_IDS:
        return rows
    return [item for item in attention_events if isinstance(item, dict)]


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


def _safe_load_json(value: Any) -> dict[str, Any] | list[Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return value
    return None


def _safe_list(value: Any, default: list | None = None) -> list:
    if isinstance(value, list):
        return value
    return default if default is not None else []


def _safe_dict(value: Any, default: dict | None = None) -> dict:
    if isinstance(value, dict):
        return value
    return default if default is not None else {}


def _artifact_items(
    payload: dict[str, Any] | None, keys: tuple[str, ...]
) -> list[dict]:
    if not isinstance(payload, dict):
        return []

    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _build_latest_selection(
    mailbox_selection: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(mailbox_selection, dict):
        return {
            "selected_count": 0,
            "strategy": "unknown",
            "source_count": 0,
            "sources": [],
            "newest_message_at": None,
            "oldest_message_at": None,
            "warnings": ["mailbox_selection.json not available"],
            "evidence_artifact_id": "mailbox_selection_json",
        }

    sources_raw = mailbox_selection.get("sources", [])
    sources: list[dict[str, Any]] = []
    selected_total = 0
    message_times: list[str] = []

    if isinstance(sources_raw, list):
        for source in sources_raw:
            if not isinstance(source, dict):
                continue

            selected_count = _int(source.get("selected_count", 0))
            selected_total += selected_count

            messages = source.get("messages", [])
            if isinstance(messages, list):
                for message in messages:
                    if not isinstance(message, dict):
                        continue
                    timestamp = (
                        message.get("internal_date")
                        or message.get("internaldate")
                        or message.get("received_at")
                        or message.get("date")
                        or message.get("timestamp")
                    )
                    if isinstance(timestamp, str) and timestamp:
                        message_times.append(timestamp)

            sources.append(
                {
                    "source_id": source.get("source_id", ""),
                    "display_name": (
                        source.get("source_display_name")
                        or source.get("display_name")
                        or source.get("source_id", "")
                    ),
                    "selected_count": selected_count,
                    "available_count": _int(source.get("available_count", 0)),
                }
            )

    selected_count = _int(mailbox_selection.get("selected_count", 0))
    if selected_count == 0:
        selected_count = selected_total

    source_count = _int(mailbox_selection.get("source_count", 0))
    if source_count == 0:
        source_count = len(sources)

    newest_message_at = mailbox_selection.get("newest_message_at")
    oldest_message_at = mailbox_selection.get("oldest_message_at")
    if message_times:
        newest_message_at = newest_message_at or max(message_times)
        oldest_message_at = oldest_message_at or min(message_times)

    warnings_raw = mailbox_selection.get("warnings", [])
    warnings = [w for w in warnings_raw if isinstance(w, str)]

    return {
        "selected_count": selected_count,
        "strategy": str(mailbox_selection.get("strategy", "unknown")),
        "source_count": source_count,
        "sources": sources,
        "newest_message_at": newest_message_at,
        "oldest_message_at": oldest_message_at,
        "warnings": warnings,
        "evidence_artifact_id": "mailbox_selection_json",
    }


def _build_thread_summary(
    thread_index: dict[str, Any] | None,
    thread_context: dict[str, Any] | None,
    classified: list | None,
) -> dict[str, Any]:
    warnings_list: list[str] = []
    evidence_ids: list[str] = []

    idx_threads = _safe_list(
        thread_index.get("threads") if isinstance(thread_index, dict) else None, []
    )
    contexts = _safe_list(
        thread_context.get("contexts") if isinstance(thread_context, dict) else None,
        [],
    )

    if thread_index is None:
        warnings_list.append("mail_thread_index.json not available")
    else:
        evidence_ids.append("mail_thread_index_json")

    if thread_context is None:
        warnings_list.append("mail_thread_context.json not available")
    else:
        evidence_ids.append("mail_thread_context_json")

    thread_ids: set[str] = set()
    events_with_thread: set[str] = set()
    reply_or_forward = 0
    linked_by_refs = 0
    linked_by_subject = 0
    source_client_scoped = 0

    for thread in idx_threads:
        if isinstance(thread, dict) and thread.get("thread_id"):
            thread_ids.add(str(thread["thread_id"]))

    for ctx in contexts:
        if not isinstance(ctx, dict):
            continue

        thread_id = ctx.get("thread_id")
        event_id = ctx.get("event_id")

        if thread_id:
            thread_ids.add(str(thread_id))
        if event_id and thread_id:
            events_with_thread.add(str(event_id))

        if ctx.get("reply_or_forward") or ctx.get("is_reply_or_forward"):
            reply_or_forward += 1

        reason_codes = ctx.get("reason_codes", [])
        if not isinstance(reason_codes, list):
            reason_codes = []

        connection = (
            ctx.get("thread_connection")
            or ctx.get("connection")
            or ctx.get("link_reason")
            or ctx.get("match_strategy")
        )
        if connection in ("references", "message_references"):
            linked_by_refs += 1
        elif connection in ("subject_fallback", "subject"):
            linked_by_subject += 1
        elif connection in ("source_client_scoped", "source_client"):
            source_client_scoped += 1
        else:
            if any(
                code in ("message_id_chain", "references_chain")
                for code in reason_codes
            ):
                linked_by_refs += 1
            elif "subject_match" in reason_codes:
                linked_by_subject += 1

    if not contexts and isinstance(classified, list):
        for item in classified:
            if not isinstance(item, dict):
                continue
            if item.get("thread_id"):
                events_with_thread.add(str(item.get("event_id", "")))
                thread_ids.add(str(item["thread_id"]))

    for artifact in (thread_index, thread_context):
        if not isinstance(artifact, dict):
            continue
        raw_warnings = artifact.get("warnings", [])
        if isinstance(raw_warnings, list):
            for warning in raw_warnings:
                if isinstance(warning, str):
                    warnings_list.append(warning)

    return {
        "thread_count": len(thread_ids),
        "events_with_thread_context": len(events_with_thread),
        "reply_or_forward_count": reply_or_forward,
        "linked_by_references_count": linked_by_refs,
        "linked_by_subject_fallback_count": linked_by_subject,
        "source_client_scoped_fallback_count": source_client_scoped,
        "warnings": warnings_list,
        "evidence_artifact_ids": evidence_ids,
    }


def _build_threads_from_index(
    thread_index: dict[str, Any] | None,
    classified: list | None,
    normalized: list | None,
) -> list[dict[str, Any]]:
    if not isinstance(thread_index, dict):
        return []

    idx_threads = _safe_list(thread_index.get("threads"), [])
    if not idx_threads:
        return []

    classified_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(classified, list):
        for item in classified:
            if isinstance(item, dict) and item.get("event_id"):
                classified_by_id[str(item["event_id"])] = item

    normalized_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(normalized, list):
        for item in normalized:
            if isinstance(item, dict) and item.get("event_id"):
                normalized_by_id[str(item["event_id"])] = item

    threads: list[dict[str, Any]] = []
    for raw_thread in idx_threads[:50]:
        if not isinstance(raw_thread, dict):
            continue

        thread_id = str(raw_thread.get("thread_id") or "")
        if not thread_id:
            continue

        raw_event_ids = raw_thread.get("event_ids", [])
        event_ids = []
        if isinstance(raw_event_ids, list):
            event_ids = [str(value) for value in raw_event_ids if value]
        if not event_ids:
            continue

        latest_event_id = event_ids[-1]
        latest_normalized = normalized_by_id.get(latest_event_id)
        latest_classified = classified_by_id.get(latest_event_id)
        latest_timestamp = _event_timestamp(
            latest_normalized or latest_classified or {}
        )

        for event_id in event_ids:
            normalized_item = normalized_by_id.get(event_id)
            classified_item = classified_by_id.get(event_id)
            candidate = normalized_item or classified_item
            candidate_ts = (
                _event_timestamp(candidate) if isinstance(candidate, dict) else None
            )
            if latest_timestamp is None:
                if candidate_ts is not None:
                    latest_timestamp = candidate_ts
                    latest_event_id = event_id
                    latest_normalized = normalized_item
                    latest_classified = classified_item
                continue
            if candidate_ts is not None and candidate_ts >= latest_timestamp:
                latest_timestamp = candidate_ts
                latest_event_id = event_id
                latest_normalized = normalized_item
                latest_classified = classified_item

        if latest_normalized is None:
            latest_normalized = normalized_by_id.get(latest_event_id)
        if latest_classified is None:
            latest_classified = classified_by_id.get(latest_event_id)

        previous_case_type = None
        previous_case_subtype = None
        for previous_id in reversed(event_ids[:-1]):
            previous = classified_by_id.get(previous_id)
            if previous:
                previous_case_type = previous.get("case_type") or previous_case_type
                previous_case_subtype = (
                    previous.get("case_subtype") or previous_case_subtype
                )
                if previous_case_type or previous_case_subtype:
                    break

        evidence = _safe_dict(raw_thread.get("evidence"), {})
        review_reasons: list[str] = []
        if latest_classified:
            if latest_classified.get("priority") == "high":
                review_reasons.append("High priority")
            if latest_classified.get("is_fallback"):
                review_reasons.append("Fallback")
        if evidence.get("references_link"):
            review_reasons.append("Linked by references")
        if evidence.get("subject_fallback"):
            review_reasons.append("Linked by subject")

        threads.append(
            {
                "thread_id": thread_id,
                "event_count": len(event_ids),
                "source_id": str(
                    (latest_normalized or {}).get(
                        "source_id", (latest_classified or {}).get("source_id", "")
                    )
                ),
                "client_id": str(
                    (latest_normalized or {}).get(
                        "client_id", (latest_classified or {}).get("client_id", "")
                    )
                ),
                "latest_subject": str(
                    (latest_normalized or {}).get(
                        "subject",
                        (latest_classified or {}).get(
                            "subject", evidence.get("subject_fallback", "")
                        ),
                    )
                ),
                "latest_sender": str(
                    (latest_normalized or {}).get(
                        "sender", (latest_classified or {}).get("sender", "")
                    )
                ),
                "previous_event_ids_count": max(len(event_ids) - 1, 0),
                "has_reply_or_forward": False,
                "previous_case_type": previous_case_type,
                "previous_case_subtype": previous_case_subtype,
                "confidence": (latest_classified or {}).get("confidence"),
                "review_reason": "; ".join(review_reasons) if review_reasons else None,
            }
        )

    return threads


def _build_threads(
    thread_index: dict[str, Any] | None,
    thread_context: dict[str, Any] | None,
    classified: list | None,
    normalized: list | None,
) -> list[dict[str, Any]]:
    if not isinstance(thread_context, dict):
        return _build_threads_from_index(thread_index, classified, normalized)

    contexts = thread_context.get("contexts", [])
    if not isinstance(contexts, list):
        return _build_threads_from_index(thread_index, classified, normalized)
    if not contexts:
        return _build_threads_from_index(thread_index, classified, normalized)

    classified_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(classified, list):
        for item in classified:
            if isinstance(item, dict) and item.get("event_id"):
                classified_by_id[str(item["event_id"])] = item

    normalized_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(normalized, list):
        for item in normalized:
            if isinstance(item, dict) and item.get("event_id"):
                normalized_by_id[str(item["event_id"])] = item

    grouped: dict[str, list[dict[str, Any]]] = {}
    for ctx in contexts:
        if not isinstance(ctx, dict):
            continue
        thread_id = str(ctx.get("thread_id") or "")
        if not thread_id:
            continue
        grouped.setdefault(thread_id, []).append(ctx)

    threads: list[dict[str, Any]] = []
    for thread_id, items in list(grouped.items())[:50]:
        event_ids: list[str] = []
        previous_ids: set[str] = set()
        latest_event: dict[str, Any] | None = None
        latest_normalized: dict[str, Any] | None = None
        source_id = ""
        client_id = ""
        has_reply_or_forward = False
        latest_timestamp: datetime | None = None

        for ctx in items:
            event_id = str(ctx.get("event_id") or "")
            if event_id:
                event_ids.append(event_id)

            raw_previous = ctx.get("previous_event_ids", [])
            if isinstance(raw_previous, list):
                previous_ids.update(str(value) for value in raw_previous if value)

            source_id = source_id or str(ctx.get("source_id") or "")
            client_id = client_id or str(ctx.get("client_id") or "")

            if ctx.get("reply_or_forward") or ctx.get("is_reply_or_forward"):
                has_reply_or_forward = True

            normalized_item = normalized_by_id.get(event_id)
            classified_item = classified_by_id.get(event_id)
            candidate = normalized_item or classified_item
            candidate_ts = (
                _event_timestamp(candidate) if isinstance(candidate, dict) else None
            )
            if latest_timestamp is None or (
                candidate_ts is not None and candidate_ts >= latest_timestamp
            ):
                latest_timestamp = candidate_ts or latest_timestamp
                latest_event = classified_item or latest_event
                latest_normalized = normalized_item or latest_normalized

        if latest_event is None:
            for event_id in reversed(event_ids):
                if event_id in classified_by_id:
                    latest_event = classified_by_id[event_id]
                    break
        if latest_normalized is None:
            for event_id in reversed(event_ids):
                if event_id in normalized_by_id:
                    latest_normalized = normalized_by_id[event_id]
                    break

        previous_case_type = None
        previous_case_subtype = None
        for previous_id in previous_ids:
            previous = classified_by_id.get(previous_id)
            if previous:
                previous_case_type = previous.get("case_type") or previous_case_type
                previous_case_subtype = (
                    previous.get("case_subtype") or previous_case_subtype
                )

        review_reasons: list[str] = []
        if latest_event:
            if latest_event.get("priority") == "high":
                review_reasons.append("High priority")
            if latest_event.get("is_fallback"):
                review_reasons.append("Fallback")
        if has_reply_or_forward:
            review_reasons.append("Thread context")

        total_event_ids = {event_id for event_id in event_ids if event_id}
        total_event_ids.update(previous_ids)

        threads.append(
            {
                "thread_id": thread_id,
                "event_count": len(total_event_ids),
                "source_id": source_id
                or str(
                    (latest_normalized or {}).get(
                        "source_id", (latest_event or {}).get("source_id", "")
                    )
                ),
                "client_id": client_id
                or str((latest_normalized or {}).get("client_id", "")),
                "latest_subject": str(
                    (latest_normalized or {}).get(
                        "subject", (latest_event or {}).get("subject", "")
                    )
                ),
                "latest_sender": str(
                    (latest_normalized or {}).get(
                        "sender", (latest_event or {}).get("sender", "")
                    )
                ),
                "previous_event_ids_count": len(previous_ids),
                "has_reply_or_forward": has_reply_or_forward,
                "previous_case_type": previous_case_type,
                "previous_case_subtype": previous_case_subtype,
                "confidence": (latest_event or {}).get("confidence"),
                "review_reason": "; ".join(review_reasons) if review_reasons else None,
            }
        )

    return threads


def _first_int(mapping: dict[str, Any], keys: tuple[str, ...]) -> int:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value)
    return 0


def _first_int_with_presence(
    mapping: dict[str, Any],
    keys: tuple[str, ...],
) -> tuple[int, bool]:
    for key in keys:
        if key not in mapping:
            continue
        value = mapping.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value), True
        return 0, True
    return 0, False


def _build_ai_assist_summary(
    requests: dict[str, Any] | None,
    decisions: dict[str, Any] | None,
    results: dict[str, Any] | None,
) -> dict[str, Any]:
    warnings_list: list[str] = []
    evidence_ids: list[str] = []

    req_counters = _safe_dict(
        requests.get("counters") if isinstance(requests, dict) else None, {}
    )
    dec_counters = _safe_dict(
        decisions.get("counters") if isinstance(decisions, dict) else None, {}
    )
    res_counters = _safe_dict(
        results.get("counters") if isinstance(results, dict) else None, {}
    )

    evidence_available = False

    if isinstance(requests, dict):
        evidence_ids.append("rop_ai_assist_requests_json")
        evidence_available = True
    else:
        warnings_list.append("rop_ai_assist_requests.json not available")

    if isinstance(decisions, dict):
        evidence_ids.append("rop_ai_assist_decisions_json")
        evidence_available = True
    else:
        warnings_list.append("rop_ai_assist_decisions.json not available")

    if isinstance(results, dict):
        evidence_ids.append("rop_ai_assist_results_json")
        evidence_available = True
    else:
        warnings_list.append("rop_ai_assist_results.json not available")

    request_items = _artifact_items(requests, ("requests", "items", "events"))
    decision_items = _artifact_items(decisions, ("decisions", "items", "events"))
    result_items = _artifact_items(results, ("results", "items", "events"))

    eligible = _first_int(
        req_counters | dec_counters | res_counters,
        ("eligible_count", "ai_assist_eligible_count"),
    )
    if eligible == 0:
        eligible = len(request_items)
    request_count = _first_int(
        req_counters | dec_counters | res_counters,
        ("request_count", "ai_assist_requested_count", "requested_count"),
    )
    if request_count == 0:
        request_count = len(request_items)
    decision_count = _first_int(
        dec_counters | req_counters | res_counters,
        ("decision_count", "ai_assist_decision_count", "decided_count"),
    )
    if decision_count == 0:
        decision_count = len(decision_items)
    result_count = _first_int(
        res_counters | req_counters | dec_counters,
        ("result_count", "ai_assist_result_count", "results_count"),
    )
    if result_count == 0:
        result_count = len(result_items)
    ok_count = _first_int(
        res_counters,
        ("ok_count", "ai_assist_ok_count", "valid_count"),
    )
    if ok_count == 0:
        ok_count = sum(
            1
            for item in result_items
            if str(item.get("ai_assist_status", item.get("status", ""))) == "ok"
        )
    used_count, used_present = _first_int_with_presence(
        res_counters,
        ("used_count", "ai_assist_used_count"),
    )
    if not used_present:
        used_count = sum(
            1
            for item in result_items
            if bool(item.get("ai_assist_used", item.get("used", False)))
        )
        if used_count == 0 and not result_items:
            used_count = ok_count

    low_confidence = _first_int(
        res_counters,
        ("low_confidence_count", "ai_assist_low_confidence_count"),
    )
    if low_confidence == 0:
        low_confidence = sum(
            1
            for item in result_items
            if str(item.get("ai_assist_status", item.get("status", "")))
            == "low_confidence"
        )
    invalid_output = _first_int(
        res_counters,
        ("invalid_output_count", "ai_assist_invalid_output_count"),
    )
    if invalid_output == 0:
        invalid_output = sum(
            1
            for item in result_items
            if str(item.get("ai_assist_status", item.get("status", "")))
            in ("invalid", "invalid_output")
        )
    provider_unavailable = _first_int(
        res_counters,
        ("provider_unavailable_count", "ai_assist_provider_unavailable_count"),
    )
    if provider_unavailable == 0:
        provider_unavailable = sum(
            1
            for item in result_items
            if str(item.get("ai_assist_status", item.get("status", "")))
            == "provider_unavailable"
        )
    module_unavailable = _first_int(
        res_counters,
        (
            "module_contract_unavailable_count",
            "ai_assist_module_contract_unavailable_count",
        ),
    )
    if module_unavailable == 0:
        module_unavailable = sum(
            1
            for item in result_items
            if str(item.get("ai_assist_status", item.get("status", "")))
            == "module_contract_unavailable"
        )
    blocked = _first_int(
        res_counters,
        ("blocked_count", "ai_assist_blocked_count"),
    )
    if blocked == 0:
        blocked = sum(
            1
            for item in result_items
            if str(item.get("ai_assist_status", item.get("status", ""))) == "blocked"
        )
    explicit_degraded, degraded_present = _first_int_with_presence(
        res_counters,
        ("degraded_count", "ai_assist_degraded_count"),
    )
    degraded = max(
        explicit_degraded if degraded_present else 0,
        low_confidence
        + invalid_output
        + provider_unavailable
        + module_unavailable
        + blocked,
    )

    status_counts: dict[str, int] = {}
    raw_statuses = res_counters.get("status_counts", {})
    if isinstance(raw_statuses, dict):
        for k, v in raw_statuses.items():
            status_counts[str(k)] = _int(v)
    if not status_counts:
        counter_statuses = {
            "ok": ("ok_count", "ai_assist_ok_count"),
            "low_confidence": (
                "low_confidence_count",
                "ai_assist_low_confidence_count",
            ),
            "invalid_output": (
                "invalid_output_count",
                "ai_assist_invalid_output_count",
            ),
            "provider_unavailable": (
                "provider_unavailable_count",
                "ai_assist_provider_unavailable_count",
            ),
            "module_contract_unavailable": (
                "module_contract_unavailable_count",
                "ai_assist_module_contract_unavailable_count",
            ),
            "blocked": ("blocked_count", "ai_assist_blocked_count"),
            "degraded": ("degraded_count", "ai_assist_degraded_count"),
        }
        for status_key, counter_keys in counter_statuses.items():
            value, present = _first_int_with_presence(res_counters, counter_keys)
            if present and value > 0:
                status_counts[status_key] = value

    return {
        "evidence_available": evidence_available,
        "enabled_if_known": requests.get("enabled")
        if isinstance(requests, dict)
        else None,
        "eligible_count": eligible,
        "request_count": request_count,
        "decision_count": decision_count,
        "result_count": result_count,
        "ok_count": ok_count,
        "used_count": used_count,
        "low_confidence_count": low_confidence,
        "invalid_output_count": invalid_output,
        "provider_unavailable_count": provider_unavailable,
        "module_contract_unavailable_count": module_unavailable,
        "blocked_count": blocked,
        "degraded_count": degraded,
        "status_counts": status_counts,
        "warnings": warnings_list,
        "evidence_artifact_ids": evidence_ids,
    }


def _build_ai_adjudicator_summary(
    adjudicator_results: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build summary from rop_ai_adjudicator_results.json."""
    if not isinstance(adjudicator_results, dict):
        return {
            "available": False,
            "total_events": 0,
            "ai_used_count": 0,
            "status_counts": {},
            "warnings": ["rop_ai_adjudicator_results.json not available"],
        }

    results = adjudicator_results.get("results", [])
    if not isinstance(results, list):
        results = []

    counters = adjudicator_results.get("counters", {})
    if not isinstance(counters, dict):
        counters = {}

    total = len(results)
    ai_used = sum(1 for r in results if isinstance(r, dict) and r.get("ai_used"))
    status_counts: dict[str, int] = {}
    for r in results:
        if isinstance(r, dict):
            s = str(r.get("ai_status", "unknown"))
            status_counts[s] = status_counts.get(s, 0) + 1

    summary = {
        "available": True,
        "total_events": total,
        "ai_used_count": ai_used,
        "eligible_count": counters.get("adjudicator_eligible_count", 0),
        "used_count": counters.get("adjudicator_used_count", 0),
        "degraded_count": counters.get("adjudicator_degraded_count", 0),
        "status_counts": status_counts,
    }

    for key in (
        "adjudicator_enabled",
        "adjudicator_eligible_count",
        "adjudicator_used_count",
        "adjudicator_degraded_count",
    ):
        if key in counters:
            summary[key] = counters[key]

    return summary


def _build_ai_assist_events(
    classified: list | None,
    normalized: list | None,
    requests: dict[str, Any] | None,
    decisions: dict[str, Any] | None,
    results: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(classified, list):
        return []

    normalized_by_eid: dict[str, dict] = {}
    req_by_eid: dict[str, dict] = {}
    dec_by_eid: dict[str, dict] = {}
    res_by_eid: dict[str, dict] = {}

    if isinstance(normalized, list):
        for normalized_item in normalized:
            if isinstance(normalized_item, dict) and normalized_item.get("event_id"):
                normalized_by_eid[str(normalized_item["event_id"])] = normalized_item

    for request_item in _artifact_items(requests, ("requests", "items", "events")):
        if request_item.get("event_id"):
            req_by_eid[str(request_item["event_id"])] = request_item

    for decision_item in _artifact_items(decisions, ("decisions", "items", "events")):
        if decision_item.get("event_id"):
            dec_by_eid[str(decision_item["event_id"])] = decision_item

    for result_item in _artifact_items(results, ("results", "items", "events")):
        if result_item.get("event_id"):
            res_by_eid[str(result_item["event_id"])] = result_item

    events: list[dict[str, Any]] = []
    for item in classified[:50]:
        if not isinstance(item, dict):
            continue
        eid = item.get("event_id", "")
        if not eid:
            continue

        req = req_by_eid.get(eid, {})
        dec = dec_by_eid.get(eid, {})
        res = res_by_eid.get(eid, {})
        norm = normalized_by_eid.get(eid, {})

        if not req and not dec and not res:
            continue

        ai_status = "not_requested"
        ai_used = False
        ai_confidence = None

        if res:
            ai_status = str(res.get("ai_assist_status", res.get("status", "unknown")))
            ai_used = bool(res.get("ai_assist_used", res.get("used", False)))
            ai_confidence = (
                res.get("ai_assist_confidence")
                or res.get("ai_confidence")
                or res.get("confidence")
            )
        elif dec:
            ai_status = str(dec.get("status", dec.get("decision", "undecided")))
        elif req:
            ai_status = "requested"

        review_reasons: list[str] = []
        if item.get("priority") == "high":
            review_reasons.append("High priority")
        if item.get("is_fallback"):
            review_reasons.append("Fallback")
        if ai_status in ("low_confidence", "degraded"):
            review_reasons.append(f"AI {ai_status}")
        if ai_status == "provider_unavailable":
            review_reasons.append("AI provider unavailable")
        if ai_status == "module_contract_unavailable":
            review_reasons.append("AI merge unavailable")
        if ai_used is False and ai_status not in ("not_requested", "requested"):
            review_reasons.append("AI result not used")
        if not review_reasons:
            if item.get("priority") == "high":
                review_reasons.append("Needs review")

        events.append(
            {
                "event_id": eid,
                "source_id": item.get("source_id", ""),
                "sender": item.get("sender") or norm.get("sender", ""),
                "subject": item.get("subject") or norm.get("subject", ""),
                "deterministic_case_type": item.get("case_type", ""),
                "ai_status": ai_status,
                "ai_used": ai_used,
                "ai_confidence": ai_confidence,
                "final_case_type": res.get("final_case_type", item.get("case_type", ""))
                if res
                else item.get("case_type", ""),
                "final_priority": res.get("final_priority", item.get("priority", ""))
                if res
                else item.get("priority", ""),
                "reason_code": item.get("reason_code", ""),
                "review_reason": "; ".join(review_reasons) if review_reasons else None,
            }
        )

    return events


def _event_timestamp(evt: dict[str, Any]) -> datetime | None:
    for key in ("event_date", "received_at", "timestamp", "created_at", "date"):
        raw = evt.get(key)
        if isinstance(raw, str) and raw.strip():
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                continue
    return None


def _build_filter_options(
    classified: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build distinct filter option values from classified events."""
    case_types: set[str] = set()
    priorities: set[str] = set()
    bitrix_statuses: set[str] = set()

    for evt in classified:
        if not isinstance(evt, dict):
            continue
        ct = evt.get("case_type") or evt.get("bot_case_type")
        if isinstance(ct, str) and ct:
            case_types.add(ct)
        pr = evt.get("priority") or evt.get("bot_priority")
        if isinstance(pr, str) and pr:
            priorities.add(pr)
        bs = evt.get("bitrix_status")
        if isinstance(bs, str) and bs:
            bitrix_statuses.add(bs)

    return {
        "case_types": sorted(case_types),
        "priorities": sorted(priorities),
        "bitrix_statuses": sorted(bitrix_statuses),
    }


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
    filter_params: dict[str, str] | None = None,
    page: int = 1,
    page_size: int = 25,
    sort: str = "received_at",
    order: str = "desc",
) -> dict[str, Any]:
    runs_dir = storage_dir / "runs"
    if not runs_dir.is_dir():
        return {"error": "no_runs", "message": "No runs directory"}

    run_ids = _list_run_ids(runs_dir)
    if run_id is None:
        rop_run_ids = _list_rop_run_ids(runs_dir)
        if not rop_run_ids:
            return {"error": "no_runs", "message": "No runs found"}
        run_id = rop_run_ids[0]

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
    mailbox_selection = _read_json(run_dir / "mailbox_selection.json")
    thread_index = _read_json(run_dir / "mail_thread_index.json")
    thread_context = _read_json(run_dir / "mail_thread_context.json")
    ai_requests = _read_json(run_dir / "rop_ai_assist_requests.json")
    ai_decisions = _read_json(run_dir / "rop_ai_assist_decisions.json")
    ai_results = _read_json(run_dir / "rop_ai_assist_results.json")
    ai_adjudicator_results = _read_json(run_dir / "rop_ai_adjudicator_results.json")

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

    if mailbox_selection is None:
        warnings.append(
            {"code": "missing_artifact", "artifact": "mailbox_selection.json"}
        )
    if thread_index is None:
        warnings.append(
            {"code": "missing_artifact", "artifact": "mail_thread_index.json"}
        )
    if thread_context is None:
        warnings.append(
            {"code": "missing_artifact", "artifact": "mail_thread_context.json"}
        )
    if ai_requests is None:
        warnings.append(
            {"code": "missing_artifact", "artifact": "rop_ai_assist_requests.json"}
        )
    if ai_decisions is None:
        warnings.append(
            {"code": "missing_artifact", "artifact": "rop_ai_assist_decisions.json"}
        )
    if ai_results is None:
        warnings.append(
            {"code": "missing_artifact", "artifact": "rop_ai_assist_results.json"}
        )
    if ai_adjudicator_results is None:
        warnings.append(
            {"code": "missing_artifact", "artifact": "rop_ai_adjudicator_results.json"}
        )

    kpis = _build_kpis(
        run_id=run_id,
        total_runs=len(run_ids),
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

    latest_selection = _build_latest_selection(
        mailbox_selection if isinstance(mailbox_selection, dict) else None,
    )

    thread_summary_result = _build_thread_summary(
        thread_index if isinstance(thread_index, dict) else None,
        thread_context if isinstance(thread_context, dict) else None,
        classified if isinstance(classified, list) else None,
    )

    thread_list = _build_threads(
        thread_index if isinstance(thread_index, dict) else None,
        thread_context if isinstance(thread_context, dict) else None,
        classified if isinstance(classified, list) else None,
        normalized if isinstance(normalized, list) else None,
    )

    ai_assist_summary = _build_ai_assist_summary(
        ai_requests if isinstance(ai_requests, dict) else None,
        ai_decisions if isinstance(ai_decisions, dict) else None,
        ai_results if isinstance(ai_results, dict) else None,
    )

    ai_adjudicator_summary = _build_ai_adjudicator_summary(
        ai_adjudicator_results if isinstance(ai_adjudicator_results, dict) else None,
    )

    final_decisions, final_decisions_source = load_or_build_final_decisions(run_dir)
    final_decision_summary = final_decisions["summary"]
    if final_decisions_source == "computed":
        warnings.append(
            {
                "code": "missing_or_malformed_artifact",
                "artifact": "rop_final_decisions.json",
            }
        )

    ai_assist_events = _build_ai_assist_events(
        classified if isinstance(classified, list) else None,
        normalized if isinstance(normalized, list) else None,
        ai_requests if isinstance(ai_requests, dict) else None,
        ai_decisions if isinstance(ai_decisions, dict) else None,
        ai_results if isinstance(ai_results, dict) else None,
    )

    rec_extras = _build_it30_recommendations(
        latest_selection,
        thread_summary_result,
        ai_assist_summary,
    )
    recommendations.extend(rec_extras)

    attention_events = _build_attention_events(
        classified=classified if isinstance(classified, list) else None,
        normalized=normalized if isinstance(normalized, list) else None,
        source_health=source_health,
        locale="en",
        run_id=run_id,
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

    # Point 5: If date range is explicitly set in filter params, load all events
    # so date_from/date_to can filter across any period
    if filter_params and (
        filter_params.get("date_from") or filter_params.get("date_to")
    ):
        effective_period = "all"

    dashboard_payload: dict[str, Any] = {}
    if effective_period:
        try:
            dashboard_payload = build_rop_dashboard(
                storage_dir=storage_dir,
                period=effective_period,
                logger=logging.getLogger("beeagent.ui.rop_dashboard"),
                run_id=run_id,
                aggregate_runs=True,
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
    attach_overrides = _trusted_attach_operational_case_types(storage_dir)
    if attach_overrides:
        for _queue_items in queues.values():
            if not isinstance(_queue_items, list):
                continue
            for item in _queue_items:
                if not isinstance(item, dict):
                    continue
                if item.get("semantic_case_type"):
                    continue
                key = (
                    str(item.get("run_id") or ""),
                    str(item.get("source_id") or ""),
                    str(item.get("event_id") or ""),
                    str(item.get("event_instance_id") or ""),
                )
                operational = attach_overrides.get(key)
                if operational:
                    item["semantic_case_type"] = str(
                        item.get("bot_case_type") or item.get("case_type") or ""
                    )
                    item["case_type"] = operational
                    item["bot_case_type"] = operational
    rop_recommendations = dashboard_payload.get("rop_recommendations", [])
    if not isinstance(rop_recommendations, list):
        rop_recommendations = []

    canonical_queue_rows = _canonical_queue_rows(
        queues, attention_events, filter_params or {}
    )
    filtered_queue_rows = apply_queue_filters(
        canonical_queue_rows, None, filter_params or {}
    )
    sorted_queue_rows = sort_queue_items(filtered_queue_rows, sort=sort, order=order)
    paginated_queue_rows, pagination = paginate_items(
        sorted_queue_rows, page=page, page_size=page_size
    )
    pagination["total_items"] = pagination["total"]
    pagination["showing_from"] = pagination["start"]
    pagination["showing_to"] = pagination["end"]

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
        "latest_selection": latest_selection,
        "thread_summary": thread_summary_result,
        "threads": thread_list,
        "ai_assist_summary": ai_assist_summary,
        "ai_assist_events": ai_assist_events,
        "ai_adjudicator_summary": ai_adjudicator_summary,
        "final_decisions": final_decisions,
        "final_decision_summary": final_decision_summary,
        "warnings": warnings,
        "current_state_available": isinstance(current_state, dict),
        "current_state_kpi": current_state_kpi,
        "current_state_queues": current_state_queues,
        "bitrix": bitrix_state,
        "business_kpi": business_kpi,
        "series": series,
        "queues": queues,
        "queue_rows": paginated_queue_rows,
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
        "filter_params": dict(filter_params) if filter_params else {},
        "page": pagination["page"],
        "page_size": pagination["page_size"],
        "pagination": pagination,
        "sort": sort,
        "order": order,
    }

    # Build filter options from period-filtered queue data for the filter form
    # Point 8: use displayed data (queues) rather than raw unfiltered classified
    if dashboard_payload and isinstance(dashboard_payload, dict):
        queue_items: list[dict[str, Any]] = []
        for q_items in dashboard_payload.get("queues", {}).values():
            if isinstance(q_items, list):
                for item in q_items:
                    if isinstance(item, dict):
                        queue_items.append(item)
        if queue_items:
            filter_options = _build_filter_options(queue_items)
        else:
            filter_options = _build_filter_options(
                classified if isinstance(classified, list) else [],
            )
    else:
        filter_options = _build_filter_options(
            classified if isinstance(classified, list) else [],
        )
    result["filter_options"] = filter_options

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


def build_rop_tab_read_model(
    storage_dir: Path,
    tab: str,
    run_id: str | None = None,
    period: str | None = None,
    default_period: str | None = None,
    configured_periods: list[str] | None = None,
    filter_params: dict[str, str] | None = None,
    page: int = 1,
    page_size: int = 25,
    sort: str = "received_at",
    order: str = "desc",
) -> dict[str, Any]:
    requested_tab = "overview" if tab == "api" else tab
    manifest = rop_web_projection_v2_manifest(storage_dir)
    if manifest is None:
        return {
            "error": "web_projection_unavailable",
            "message": (
                "ROP Web projection manifest is missing or malformed; "
                "regenerate it with the supported ROP dashboard command"
            ),
        }
    latest_run_id = manifest["latest_run_id"]
    projection_runs = manifest["run_ids"]
    total_runs = manifest["total_runs"]
    selected_run_id = run_id or latest_run_id
    if selected_run_id not in projection_runs:
        return {"error": "not_found", "run_id": selected_run_id}

    request_filter_params = dict(filter_params or {})
    request_page = page
    request_page_size = page_size
    request_sort = sort
    request_order = order
    effective_period = period or default_period
    if tab == "api" and (
        request_filter_params.get("date_from") or request_filter_params.get("date_to")
    ):
        effective_period = "all"
    allowed_periods = set(configured_periods or [])
    warnings: list[dict[str, Any]] = []
    if effective_period not in allowed_periods:
        warnings.append({"code": "invalid_period", "period": effective_period})
        effective_period = default_period
    if requested_tab == "queue":
        view_id = "queue"
        view_period = None
    elif tab == "api":
        view_id = "api"
        view_period = effective_period
    elif requested_tab == "overview":
        view_id = requested_tab
        view_period = effective_period
    elif requested_tab in {
        "sources",
    }:
        view_id = requested_tab
        view_period = None
    else:
        return {
            "error": "web_projection_unavailable",
            "message": "ROP view is unavailable",
        }

    payload = read_rop_web_projection_v2_view(
        storage_dir=storage_dir,
        manifest=manifest,
        run_id=selected_run_id,
        view_id=view_id,
        period=view_period,
    )
    if payload is None:
        return {
            "error": "web_projection_unavailable",
            "message": (
                "ROP Web projection view is missing or malformed; "
                "regenerate it with the supported ROP dashboard command"
            ),
        }

    result: dict[str, Any] = {
        "run_id": selected_run_id,
        "selected_run_id": selected_run_id,
        "available_runs": projection_runs,
        "total_runs": total_runs,
        "status": "ok",
        "configured_periods": list(configured_periods or []),
        "default_period": default_period,
        "filter_params": request_filter_params,
        "page": request_page,
        "page_size": request_page_size,
        "sort": request_sort,
        "order": request_order,
    }
    result.update(payload)
    result.update(
        {
            "filter_params": request_filter_params,
            "page": request_page,
            "page_size": request_page_size,
            "sort": request_sort,
            "order": request_order,
        }
    )
    existing_warnings = result.get("warnings", [])
    if isinstance(existing_warnings, list):
        warnings.extend(item for item in existing_warnings if isinstance(item, dict))
    result["warnings"] = warnings

    if requested_tab == "queue" or tab == "api":
        canonical_rows = (
            result.get("queue_rows", [])
            if requested_tab == "queue"
            else result.get("canonical_queue_rows", [])
        )
        if not isinstance(canonical_rows, list):
            return {
                "error": "web_projection_unavailable",
                "message": "ROP Web projection queue view is malformed",
            }
        queue_filter = str((filter_params or {}).get("queue", "")).strip()
        if queue_filter:
            canonical_rows = [
                row
                for row in canonical_rows
                if isinstance(row, dict)
                and queue_filter in row.get("queue_memberships", [])
            ]
        filtered_rows = apply_queue_filters(canonical_rows, None, filter_params or {})
        sorted_rows = sort_queue_items(filtered_rows, sort=sort, order=order)
        queue_rows, pagination = paginate_items(
            sorted_rows, page=page, page_size=page_size
        )
        pagination["total_items"] = pagination["total"]
        pagination["showing_from"] = pagination["start"]
        pagination["showing_to"] = pagination["end"]
        result["queue_rows"] = queue_rows
        result["pagination"] = pagination
        result["page"] = pagination["page"]
        result["page_size"] = pagination["page_size"]
        result.pop("canonical_queue_rows", None)
    return result


def _build_rop_tab_read_model_legacy(
    storage_dir: Path,
    tab: str,
    run_id: str | None = None,
    period: str | None = None,
    default_period: str | None = None,
    configured_periods: list[str] | None = None,
    filter_params: dict[str, str] | None = None,
    page: int = 1,
    page_size: int = 25,
    sort: str = "received_at",
    order: str = "desc",
) -> dict[str, Any]:
    requested_tab = "overview" if tab == "api" else tab
    runs_dir = storage_dir / "runs"
    if not runs_dir.is_dir():
        return {"error": "no_runs", "message": "No runs directory"}

    warnings: list[dict[str, Any]] = []
    projection = rop_web_projection_index(storage_dir)
    if projection is None:
        return {
            "error": "web_projection_unavailable",
            "message": (
                "ROP Web projection index is missing or malformed; "
                "regenerate it with the supported ROP dashboard command"
            ),
        }

    latest_run_id = projection["latest_run_id"]
    projection_runs = projection["run_ids"]
    total_runs = projection["total_runs"]

    if not isinstance(latest_run_id, str) or not latest_run_id:
        return {
            "error": "web_projection_unavailable",
            "message": (
                "ROP Web projection index is missing or malformed; "
                "regenerate it with the supported ROP dashboard command"
            ),
        }
    selected_run_id = run_id if run_id is not None else latest_run_id

    run_dir, error = _resolve_run_dir(storage_dir, selected_run_id)
    if run_dir is None:
        return {"error": error, "run_id": selected_run_id}

    effective_period = period or default_period
    allowed_periods = set(configured_periods or [])
    if effective_period not in allowed_periods:
        warnings.append({"code": "invalid_period", "period": effective_period})
        effective_period = default_period
    if filter_params and (
        filter_params.get("date_from") or filter_params.get("date_to")
    ):
        effective_period = "all"

    dashboard_payload: dict[str, Any] = {}
    projection_entry = _read_json(
        rop_web_projection_entry_path(storage_dir, selected_run_id)
    )
    if (
        not isinstance(projection_entry, dict)
        or projection_entry.get("schema_version") != 1
        or projection_entry.get("run_id") != selected_run_id
    ):
        return {
            "error": "web_projection_unavailable",
            "message": (
                "ROP Web projection entry is missing or malformed; "
                "regenerate it with the supported ROP dashboard command"
            ),
        }

    entries = projection_entry.get("dashboards")
    entry = entries.get(effective_period) if isinstance(entries, dict) else None
    if not isinstance(entry, dict):
        return {
            "error": "web_projection_unavailable",
            "message": (
                "ROP Web projection period is unavailable; "
                "regenerate it with the supported ROP dashboard command"
            ),
        }

    dashboard_payload = entry

    for warning in dashboard_payload.get("warnings", []):
        if isinstance(warning, dict):
            warnings.append(warning)

    queues = dashboard_payload.get("queues", {})
    if not isinstance(queues, dict):
        queues = {}
    attach_overrides = _trusted_attach_operational_case_types(storage_dir)
    if attach_overrides:
        for queue_items in queues.values():
            if not isinstance(queue_items, list):
                continue
            for item in queue_items:
                if not isinstance(item, dict) or item.get("semantic_case_type"):
                    continue
                key = (
                    str(item.get("run_id") or ""),
                    str(item.get("source_id") or ""),
                    str(item.get("event_id") or ""),
                    str(item.get("event_instance_id") or ""),
                )
                operational = attach_overrides.get(key)
                if operational:
                    item["semantic_case_type"] = str(
                        item.get("bot_case_type") or item.get("case_type") or ""
                    )
                    item["case_type"] = operational
                    item["bot_case_type"] = operational
    business_kpi = dashboard_payload.get("business_kpi", {})
    if not isinstance(business_kpi, dict):
        business_kpi = {}
    series = dashboard_payload.get("series", {})
    if not isinstance(series, dict):
        series = {}

    result: dict[str, Any] = {
        "run_id": selected_run_id,
        "selected_run_id": selected_run_id,
        "available_runs": projection_runs or [selected_run_id],
        "total_runs": total_runs,
        "status": "ok",
        "warnings": warnings,
        "business_kpi": business_kpi,
        "series": series,
        "queues": queues,
        "rop_recommendations": dashboard_payload.get("rop_recommendations", []),
        "configured_periods": list(configured_periods or []),
        "default_period": default_period,
        "updated_at": dashboard_payload.get("generated_at_utc"),
        "period": dashboard_payload.get("period"),
        "period_start_utc": dashboard_payload.get("period_start_utc"),
        "period_end_utc": dashboard_payload.get("period_end_utc"),
        "time_basis": dashboard_payload.get("time_basis", "unknown"),
        "filter_params": dict(filter_params or {}),
        "page": page,
        "page_size": page_size,
        "sort": sort,
        "order": order,
    }

    if requested_tab in {"overview", "queue"}:
        current_state = _read_json(run_dir / "rop_current_state.json")
        if isinstance(current_state, dict):
            result["current_state_kpi"] = current_state.get("kpi", {})
            result["current_state_queues"] = current_state.get("queues", {})
        if requested_tab == "overview":
            summary = _read_json(run_dir / "operator_summary.json")
            source_diag = _read_json(run_dir / "source_diagnostics.json")
            intake = _read_json(run_dir / "intake_metadata.json")
            normalized = _read_json(run_dir / "normalized_events.json")
            classified = _read_json(run_dir / "classified_events.json")
            extraction = _read_json(run_dir / "attachment_extraction.json")
            result["kpis"] = _build_kpis(
                run_id=selected_run_id,
                total_runs=total_runs,
                summary=summary if isinstance(summary, dict) else None,
                source_diag=source_diag if isinstance(source_diag, dict) else None,
                intake=intake if isinstance(intake, dict) else None,
                normalized=normalized if isinstance(normalized, list) else None,
                classified=classified if isinstance(classified, list) else None,
                attachment_extraction=extraction
                if isinstance(extraction, dict)
                else None,
                run_dir=run_dir,
            )
            result["funnel"] = _build_funnel(
                source_diag if isinstance(source_diag, dict) else None,
                intake if isinstance(intake, dict) else None,
                normalized if isinstance(normalized, list) else None,
                classified if isinstance(classified, list) else None,
                result["kpis"],
            )
            result["source_health"] = _build_source_health(
                source_diag if isinstance(source_diag, dict) else None,
                intake if isinstance(intake, dict) else None,
                classified if isinstance(classified, list) else None,
            )
            sources = []
            if isinstance(source_diag, dict):
                for source in source_diag.get("sources", []):
                    if isinstance(source, dict):
                        sources.append(
                            {
                                "source_id": source.get("source_id", ""),
                                "source_type": source.get("source_type", ""),
                                "source_role": source.get("source_role", ""),
                                "display_name": source.get(
                                    "source_display_name",
                                    source.get("display_name", ""),
                                ),
                                "status": source.get("status", ""),
                            }
                        )
            result["sources"] = sources
            result["classification_distribution"] = _build_classification_distribution(
                classified if isinstance(classified, list) else None
            )
            result["classified_count"] = result["kpis"].get("classified_count", 0)
            result["case_type_counts"] = result["classification_distribution"].get(
                "case_type_counts", {}
            )
            result["priority_counts"] = result["classification_distribution"].get(
                "priority_counts", {}
            )
            result["fallback_count"] = result["kpis"].get("fallback_count", 0)
            result["normalized_count"] = result["kpis"].get("normalized_count", 0)
            adjudicator = _read_json(run_dir / "rop_ai_adjudicator_results.json")
            result["ai_adjudicator_summary"] = _build_ai_adjudicator_summary(
                adjudicator if isinstance(adjudicator, dict) else None
            )
            final_decisions, final_source = load_or_build_final_decisions(run_dir)
            result["final_decisions"] = final_decisions
            result["final_decision_summary"] = final_decisions["summary"]
            if final_source == "computed":
                warnings.append(
                    {
                        "code": "missing_or_malformed_artifact",
                        "artifact": "rop_final_decisions.json",
                    }
                )
            result["attachment_summary"] = _build_attachment_summary(
                extraction if isinstance(extraction, dict) else None
            )
            result["recommendations"] = _build_recommendations(result["kpis"])
            result["attention_events"] = _build_attention_events(
                classified if isinstance(classified, list) else None,
                normalized if isinstance(normalized, list) else None,
                result["source_health"],
                locale="en",
                run_id=selected_run_id,
            )
            selection = _read_json(run_dir / "mailbox_selection.json")
            result["latest_selection"] = _build_latest_selection(
                selection if isinstance(selection, dict) else None
            )
            evidence_links = _build_evidence_links(selected_run_id)
            from beeagent_module.interfaces.ui.artifacts import resolve_artifact_path

            for link in evidence_links:
                link["available"] = (
                    resolve_artifact_path(
                        storage_dir, selected_run_id, link["artifact_id"]
                    )
                    is not None
                )
            result["evidence_links"] = evidence_links
    if tab == "api":
        classified = _read_json(run_dir / "classified_events.json")
        normalized = _read_json(run_dir / "normalized_events.json")
        thread_index = _read_json(run_dir / "mail_thread_index.json")
        thread_context = _read_json(run_dir / "mail_thread_context.json")
        result["thread_summary"] = _build_thread_summary(
            thread_index if isinstance(thread_index, dict) else None,
            thread_context if isinstance(thread_context, dict) else None,
            classified if isinstance(classified, list) else None,
        )
        result["threads"] = _build_threads(
            thread_index if isinstance(thread_index, dict) else None,
            thread_context if isinstance(thread_context, dict) else None,
            classified if isinstance(classified, list) else None,
            normalized if isinstance(normalized, list) else None,
        )
        requests = _read_json(run_dir / "rop_ai_assist_requests.json")
        decisions = _read_json(run_dir / "rop_ai_assist_decisions.json")
        ai_results = _read_json(run_dir / "rop_ai_assist_results.json")
        result["ai_assist_summary"] = _build_ai_assist_summary(
            requests if isinstance(requests, dict) else None,
            decisions if isinstance(decisions, dict) else None,
            ai_results if isinstance(ai_results, dict) else None,
        )
        result["ai_assist_events"] = _build_ai_assist_events(
            classified if isinstance(classified, list) else None,
            normalized if isinstance(normalized, list) else None,
            requests if isinstance(requests, dict) else None,
            decisions if isinstance(decisions, dict) else None,
            ai_results if isinstance(ai_results, dict) else None,
        )
    if requested_tab == "queue" or tab == "api":
        attention_events: list[dict[str, Any]] = []
        if not queues:
            classified = _read_json(run_dir / "classified_events.json")
            normalized = _read_json(run_dir / "normalized_events.json")
            attention_events = _build_attention_events(
                classified if isinstance(classified, list) else None,
                normalized if isinstance(normalized, list) else None,
                [],
                locale="en",
                run_id=selected_run_id,
            )
        canonical_rows = _canonical_queue_rows(
            queues, attention_events, filter_params or {}
        )
        filtered_rows = apply_queue_filters(canonical_rows, None, filter_params or {})
        sorted_rows = sort_queue_items(filtered_rows, sort=sort, order=order)
        queue_rows, pagination = paginate_items(
            sorted_rows, page=page, page_size=page_size
        )
        pagination["total_items"] = pagination["total"]
        pagination["showing_from"] = pagination["start"]
        pagination["showing_to"] = pagination["end"]
        result["queue_rows"] = queue_rows
        result["pagination"] = pagination
        result["filter_options"] = _build_filter_options(canonical_rows)
        result["page"] = pagination["page"]
        result["page_size"] = pagination["page_size"]

    if requested_tab == "sources":
        source_diag = _read_json(run_dir / "source_diagnostics.json")
        intake = _read_json(run_dir / "intake_metadata.json")
        classified = _read_json(run_dir / "classified_events.json")
        result["source_health"] = _build_source_health(
            source_diag if isinstance(source_diag, dict) else None,
            intake if isinstance(intake, dict) else None,
            classified if isinstance(classified, list) else None,
        )

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
            host = mailbox.get("host", "")
            host_env = mailbox.get("host_env", "")
            if (not isinstance(host, str) or not host) and isinstance(host_env, str):
                host = os.environ.get(host_env, "")

            folder = mailbox.get("folder", "")
            folder_env = mailbox.get("folder_env", "")
            if (not isinstance(folder, str) or not folder) and isinstance(
                folder_env, str
            ):
                folder = os.environ.get(folder_env, "")

            safe_source["mailbox"] = {
                "host": host,
                "host_env": host_env,
                "port": mailbox.get("port", 0),
                "use_ssl": mailbox.get("use_ssl", False),
                "folder": folder,
                "folder_env": folder_env,
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



def _period_label(period: str, locale: str = "en") -> str:
    return t(_PERIOD_LABELS.get(period, period), locale)


def _format_date_display(ts_str: str | None, locale: str = "en") -> str:
    """Format an ISO timestamp as DD.MM.YYYY (date only, no time)."""
    if not ts_str or not isinstance(ts_str, str):
        return t("n/a", locale)
    dt = _parse_utc_datetime(ts_str)
    if dt is None:
        return ts_str
    return f"{dt.day:02d}.{dt.month:02d}.{dt.year}"


def _overview_cell(value: object, tone: str = "") -> dict[str, str]:
    cell = {"label": str(value)}
    if tone:
        cell["tone"] = tone
    return cell


def _period_link_items(
    current_period: str,
    current_tab: str,
    locale: str = "en",
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for period_value in _OVERVIEW_PERIODS:
        label = _period_label(period_value, locale)
        if period_value == current_period:
            label = f"{label} ({t('current', locale)})"
        items.append(
            {
                "period": period_value,
                "active": period_value == current_period,
                "label": label,
                "href": _rop_href(
                    tab=current_tab,
                    period=period_value,
                    locale=locale,
                    run_id=run_id,
                ),
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
    if value in ("identity_only_no_target", "unreconciled", "skipped", ""):
        return "info"
    return "unknown"


def _bitrix_status_label(status: object, locale: str) -> str:
    value = str(status or "").lower()
    if value.startswith("matched_"):
        return t("Matched in Bitrix", locale)
    label_keys = {
        "not_found": "Not found in Bitrix",
        "weak_match": "Needs clarification",
        "ambiguous": "Needs clarification",
        "duplicate_candidate": "Possible duplicate",
        "identity_only_no_target": "Contact without lead/deal",
        "unreconciled": "Reconciliation not run",
        "connector_degraded": "Bitrix connection error",
        "error": "Bitrix reconciliation error",
        "skipped": "Reconciliation not required",
    }
    return t(label_keys.get(value, value.replace("_", " ").title()), locale)


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


def _humanize_label(raw: str, locale: str = "en") -> str:
    return t(_CHART_LABEL_MAP.get(raw, raw.replace("_", " ").title()), locale)


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
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _day_label(value: datetime) -> str:
    return value.date().isoformat()


def _period_day_labels(period: str, period_end_utc: Any) -> list[str]:
    end = _parse_utc_datetime(period_end_utc) or datetime.now(UTC)
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
    locale: str = "en",
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
                "name": _humanize_label(str(item.get("name", "Processed")), locale),
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


def _rop_href(
    *,
    tab: str,
    period: str | None = None,
    locale: str = "en",
    run_id: str | None = None,
) -> str:
    return build_rop_url(tab=tab, period=period, lang=locale, run_id=run_id)


def _rop_event_detail_href(
    event_id: str,
    run_id: str,
    locale: str = "en",
    period: str | None = None,
    filter_params: dict[str, str] | None = None,
    page: int | None = None,
    page_size: int | None = None,
    sort: str | None = None,
    order: str | None = None,
    event_instance_id: str | None = None,
) -> str:
    return build_rop_event_url(
        event_id,
        run_id,
        event_instance_id=event_instance_id,
        lang=locale,
        period=period,
        filter_params=filter_params,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
    )


def normalize_rop_recommendation_hrefs(
    recommendations: list[dict[str, Any]],
    *,
    run_id: str,
    period: str | None,
    locale: str,
) -> list[dict[str, Any]]:
    target_tabs = {
        "/rop?tab=queue": "queue",
        "/rop?tab=bitrix": "queue",
        "/rop?tab=evidence": "queue",
        "/rop?tab=sources": "sources",
        "/rop?tab=attachments": "queue",
    }
    normalized: list[dict[str, Any]] = []
    for recommendation in recommendations:
        item = dict(recommendation)
        raw_href = str(item.get("evidence_href", ""))
        target_tab = target_tabs.get(raw_href)
        if target_tab:
            filter_params: dict[str, str] = {}
            bitrix_status_filter = item.get("bitrix_status_filter")
            if target_tab == "queue" and isinstance(bitrix_status_filter, str):
                filter_params["bitrix_status"] = bitrix_status_filter
            elif raw_href in {"/rop?tab=bitrix", "/rop?tab=evidence"}:
                filter_params["bitrix_status"] = (
                    "not_found,ambiguous,duplicate_candidate,unreconciled"
                )
            item["evidence_href"] = build_rop_url(
                tab=target_tab,
                run_id=run_id,
                period=period,
                lang=locale,
                filter_params=filter_params or None,
            )
        normalized.append(item)
    return normalized


def _build_rop_overview_layout(
    data: dict[str, Any], locale: str = "en"
) -> list[dict[str, Any]]:
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
    current_period = data.get("period", "")
    period_hint = _period_label(current_period, locale) if current_period else ""
    total_leads = business_kpi.get("processed_events", 0)
    new_leads = business_kpi.get("new_leads", 0)
    high_priority = business_kpi.get("high_priority", 0)
    needs_review = business_kpi.get("needs_review", 0)
    lost_in_bitrix = business_kpi.get("lost_in_bitrix", 0)
    identity_only_no_target = business_kpi.get("identity_only_no_target", 0)
    unreconciled = business_kpi.get("unreconciled", 0)
    ambiguous_or_duplicate = business_kpi.get("ambiguous_or_duplicate", 0)
    source_count = kpis.get("source_count", 0)
    degraded_sources = kpis.get("degraded_source_count", 0)
    source_summary = (
        t("{count} / {degraded} degraded", locale).format(count=source_count, degraded=degraded_sources)
        if degraded_sources else t("{count} connected", locale).format(count=source_count)
    )
    bitrix_summary = t("{count} not reconciled", locale).format(count=unreconciled) if unreconciled else (t("OK", locale) if not lost_in_bitrix else t("{count} lost", locale).format(count=lost_in_bitrix))
    period_emails = _int(business_kpi.get("processed_emails", business_kpi.get("processed_events", kpis.get("loaded_count", 0))))
    todays_emails = period_emails
    layout: list[dict[str, Any]] = []
    bitrix_gap_count = (
        _int(unreconciled) + _int(lost_in_bitrix) + _int(ambiguous_or_duplicate)
    )
    configured_periods = data.get("configured_periods", [])
    configured_values = (
        {str(value) for value in configured_periods}
        if isinstance(configured_periods, list)
        else set()
    )
    period_actions = [
        item
        for item in _period_link_items(
            current_period, "overview", locale, str(data.get("run_id", ""))
        )
        if item["period"] in configured_values
    ]
    # Build date range from current period so Queue shows same period as Overview
    period_start_utc = data.get("period_start_utc")
    period_end_utc = data.get("period_end_utc")
    _parsed_start = _parse_utc_datetime(period_start_utc) if period_start_utc else None
    _parsed_end = _parse_utc_datetime(period_end_utc) if period_end_utc else None
    date_from_str = _day_label(_parsed_start) if _parsed_start else ""
    date_to_str = _day_label(_parsed_end) if _parsed_end else ""
    # Build date filter params for Queue links
    date_filter: dict[str, str] = {}
    if date_from_str:
        date_filter["date_from"] = date_from_str
    if date_to_str:
        date_filter["date_to"] = date_to_str

    # Filtered Queue hrefs for each overview card
    queue_urgent_href = build_rop_url(
        tab="queue",
        period=current_period,
        lang=locale,
        run_id=str(data.get("run_id", "")),
        filter_params={**date_filter, "priority": "high"}
        if date_filter
        else {"priority": "high"},
    )
    queue_needs_review_href = build_rop_url(
        tab="queue",
        period=current_period,
        lang=locale,
        run_id=str(data.get("run_id", "")),
        filter_params={**date_filter, "queue": "needs_review"}
        if date_filter
        else {"queue": "needs_review"},
    )
    queue_bitrix_gaps_href = build_rop_url(
        tab="queue",
        period=current_period,
        lang=locale,
        run_id=str(data.get("run_id", "")),
        filter_params={
            **date_filter,
            "bitrix_status": "not_found,ambiguous,duplicate_candidate,unreconciled",
        }
        if date_filter
        else {"bitrix_status": "not_found,ambiguous,duplicate_candidate,unreconciled"},
    )

    processed_by_day = series.get("processed_by_day", {})
    workload_labels, workload_series = _bucket_daily_chart_series(
        processed_by_day,
        period=str(current_period or ""),
        period_end_utc=data.get("period_end_utc"),
        locale=locale,
    )
    source_label_map = _source_display_labels(source_health)

    classification_series = series.get("classification_distribution", {})
    raw_labels = (
        classification_series.get("labels", [])
        if isinstance(classification_series, dict)
        else []
    )
    raw_values = (
        classification_series.get("series", [])
        if isinstance(classification_series, dict)
        else []
    )
    outcome_labels: list[str] = []
    outcome_values: list[int] = []
    if isinstance(raw_labels, list) and isinstance(raw_values, list):
        for raw_label, raw_value in zip(raw_labels, raw_values, strict=False):
            if not isinstance(raw_label, str) or isinstance(raw_value, bool):
                continue
            if not isinstance(raw_value, (int, float)):
                continue
            outcome_labels.append(case_type_label(raw_label, locale))
            outcome_values.append(int(raw_value))

    layout.append(
        {
            "type": "operator_hero",
            "width": 6,
            "title": t("ROP Control Center", locale),
            "subtitle": t(
                "Inbound email intake, lead quality and Bitrix reconciliation",
                locale,
            ),
            "status": "",
            "items": [
                {
                    "label": (
                        t("TODAY'S EMAILS", locale)
                        if current_period == "today"
                        else t("Yesterday's emails", locale)
                        if current_period == "yesterday"
                        else t("Emails in period", locale)
                    ),
                    "value": todays_emails,
                    "progress": min(
                        100,
                        max(8 if _int(todays_emails) else 0, _int(todays_emails) * 20),
                    ),
                    "progress_tone": "bg-primary",
                },
                {
                    "label": t("NEW LEADS", locale),
                    "value": new_leads,
                    "progress": min(
                        100, max(8 if _int(new_leads) else 0, _int(new_leads) * 20)
                    ),
                    "progress_tone": "bg-success",
                },
                {"label": t("Sources", locale), "value": source_summary},
                {"label": t("Bitrix", locale), "value": bitrix_summary},
            ],
            "primary_links": period_actions,
        }
    )
    layout.append(
        {
            "type": "chart",
            "width": 6,
            "title": t("Classification mix", locale),
            "subtitle": t(
                "{count} total leads in selected period",
                locale,
            ).format(count=total_leads),
            "chart_id": "chart-rop-outcome-mix",
            "kind": "donut",
            "series": outcome_values,
            "labels": outcome_labels,
            "colors": [
                "#6366f1",
                "#0ea5e9",
                "#10b981",
                "#f59e0b",
                "#ef4444",
                "#8b5cf6",
                "#14b8a6",
                "#64748b",
            ],
            "height": 260,
            "empty_message": t("No chart data for this period", locale),
        }
    )

    small_cards = [
        {
            "type": "venue_card",
            "width": 6,
            "compact": True,
            "title": t("Urgent leads", locale),
            "subtitle": t("High-priority emails", locale),
            "status": str(high_priority),
            "items": [{"label": t("Count", locale), "value": high_priority}],
            "links": [{"label": t("Open Queue", locale), "href": queue_urgent_href}],
        },
        {
            "type": "venue_card",
            "width": 3,
            "compact": True,
            "title": t("Needs review", locale),
            "subtitle": t("Fallback classifications", locale),
            "status": str(needs_review),
            "items": [{"label": t("Count", locale), "value": needs_review}],
            "links": [
                {"label": t("Open Queue", locale), "href": queue_needs_review_href}
            ],
        },
        {
            "type": "venue_card",
            "width": 3,
            "compact": True,
            "title": t("Bitrix problems", locale),
            "subtitle": t("Emails with Bitrix problems", locale),
            "status": str(bitrix_gap_count),
            "items": [{"label": t("Count", locale), "value": bitrix_gap_count}],
            "links": [
                {"label": t("Open Queue", locale), "href": queue_bitrix_gaps_href},
            ],
        },
    ]
    layout.extend(small_cards)

    # Order: Classification mix, Email Workload, Bitrix reconciliation,
    # Source contribution

    layout.append(
        {
            "type": "chart",
            "width": 6,
            "title": t("Email Workload", locale),
            "subtitle": t(
                "{count} processed inbound items in selected period",
                locale,
            ).format(count=period_emails),
            "chart_id": "chart-rop-email-workload",
            "kind": "area",
            "series": workload_series
            or [{"name": t("Processed", locale), "data": [period_emails]}],
            "categories": workload_labels
            or [period_hint or t("Selected period", locale)],
            "colors": ["#4f46e5", "#818cf8"],
            "height": 240,
            "empty_message": t("No chart data for this period", locale),
        }
    )

    bitrix_labels = [
        t("Matched in Bitrix", locale),
        t("Lost in Bitrix", locale),
        t("Needs clarification", locale),
        t("Contact without lead/deal", locale),
        t("Not reconciled", locale),
    ]
    bitrix_values = [
        _int(business_kpi.get("matched_in_bitrix", 0)),
        _int(lost_in_bitrix),
        _int(ambiguous_or_duplicate),
        _int(identity_only_no_target),
        _int(unreconciled),
    ]
    layout.append(
        {
            "type": "chart",
            "width": 6,
            "title": t("Bitrix reconciliation", locale),
            "chart_id": "chart-rop-bitrix",
            "kind": "bar",
            "series": [{"name": t("Leads", locale), "data": bitrix_values}],
            "categories": bitrix_labels,
            "colors": ["#0d9488", "#f43f5e", "#f59e0b", "#64748b"],
            "height": 260,
            "empty_message": t("No chart data for this period", locale),
        }
    )

    source_data = series.get("source_contribution", {})
    source_labels = _as_chart_labels(source_data)
    source_values = (
        source_data.get("series", []) if isinstance(source_data, dict) else []
    )
    source_categories = [
        source_label_map.get(str(label), _humanize_label(str(label), locale))
        for label in source_labels
    ]
    layout.append(
        {
            "type": "chart",
            "width": 12,
            "title": t("Source contribution", locale),
            "chart_id": "chart-rop-source-contribution",
            "kind": "bar",
            "series": [{"name": t("Leads", locale), "data": source_values or [0]}],
            "categories": source_categories or [t("No data", locale)],
            "colors": ["#6366f1"],
            "height": 240,
            "empty_message": t("No chart data for this period", locale),
        }
    )
    return layout


def _build_rop_queue_layout(
    data: dict[str, Any], locale: str = "en"
) -> list[dict[str, Any]]:
    attention_events = data.get("attention_events", [])
    if not isinstance(attention_events, list):
        attention_events = []
    queues = data.get("queues", {})
    if not isinstance(queues, dict):
        queues = {}
    run_id = data.get("run_id", "")
    filter_params = data.get("filter_params", {})
    if not isinstance(filter_params, dict):
        filter_params = {}
    page = data.get("page", 1)
    page_size = data.get("page_size", DEFAULT_PAGE_SIZE)
    sort = data.get("sort", "received_at")
    order = data.get("order", "desc")
    current_period = data.get("period", "")
    filter_options = data.get("filter_options", {})
    if not isinstance(filter_options, dict):
        filter_options = {}

    queue_rows = data.get("queue_rows")
    if not isinstance(queue_rows, list):
        queue_rows = _canonical_queue_rows(queues, attention_events, filter_params)

    toolbar = _build_queue_toolbar(
        filter_params=filter_params,
        current_period=current_period,
        filter_options=filter_options,
        locale=locale,
        run_id=run_id,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
    )

    if not queue_rows:
        return [
            _empty_queue_table(
                locale=locale,
                run_id=run_id,
                current_period=current_period,
                filter_params=filter_params,
                page=page,
                page_size=page_size,
                sort=sort,
                order=order,
                toolbar=toolbar,
            ),
        ]

    pagination_info = data.get("pagination")
    if not isinstance(pagination_info, dict):
        filtered_rows = apply_queue_filters(queue_rows, None, filter_params)
        filtered_rows = sort_queue_items(filtered_rows, sort=sort, order=order)
        paginated_rows, pagination_info = paginate_items(
            filtered_rows, page=page, page_size=page_size
        )
    else:
        paginated_rows = queue_rows
        filtered_rows = queue_rows

    return [
        _queue_table(
            t("ROP Work Queue", locale),
            paginated_rows,
            run_id=run_id,
            locale=locale,
            total_count=_int(pagination_info.get("total", len(filtered_rows))),
            page=pagination_info["page"],
            page_size=pagination_info["page_size"],
            total_pages=pagination_info["total_pages"],
            sort=sort,
            order=order,
            filter_params=filter_params,
            current_period=current_period,
            toolbar=toolbar,
        ),
    ]


def _build_queue_toolbar(
    filter_params: dict[str, str],
    current_period: str,
    filter_options: dict[str, Any],
    locale: str = "en",
    run_id: str = "",
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    sort: str = "received_at",
    order: str = "desc",
) -> dict[str, Any]:
    case_type_options: list[dict[str, str]] = []
    for ct in filter_options.get("case_types", []):
        case_type_options.append({"value": ct, "label": case_type_label(ct, locale)})

    priority_options: list[dict[str, str]] = []
    for pr in filter_options.get("priorities", []):
        priority_options.append({"value": pr, "label": t(pr.title(), locale)})

    raw_bitrix_statuses = filter_options.get("bitrix_statuses", [])
    if not raw_bitrix_statuses:
        raw_bitrix_statuses = list(ALLOWED_BITRIX_STATUSES)
    bitrix_status_options: list[dict[str, str]] = []
    for bs in raw_bitrix_statuses:
        bitrix_status_options.append(
            {"value": bs, "label": _bitrix_status_label(bs, locale)}
        )

    def _make_checkboxes(
        param_name: str,
        label: str,
        options: list[dict[str, str]],
    ) -> dict[str, Any]:
        current_raw = filter_params.get(param_name, "")
        selected = {v.strip() for v in current_raw.split(",") if v.strip()}
        choices: list[dict[str, Any]] = []
        for opt in options:
            val = opt["value"]
            checked = val in selected
            if checked:
                new_set = selected - {val}
            else:
                new_set = selected | {val}
            new_val = ",".join(sorted(new_set))
            toggle_params = dict(filter_params)
            if new_val:
                toggle_params[param_name] = new_val
            elif param_name in toggle_params:
                del toggle_params[param_name]
            toggle_href = build_rop_url(
                tab="queue",
                period=current_period,
                lang=locale,
                run_id=run_id,
                page=1,
                page_size=page_size,
                sort=sort,
                order=order,
                filter_params=toggle_params,
            )
            choices.append(
                {
                    "value": val,
                    "label": opt["label"],
                    "checked": checked,
                    "toggle_href": toggle_href,
                }
            )
        return {
            "type": "checkboxes",
            "name": param_name,
            "label": label,
            "choices": choices,
            "selected_count": len(selected),
        }

    fields: list[dict[str, Any]] = [
        {
            "type": "date_range",
            "name": "date",
            "label": "",
            "from_value": filter_params.get("date_from", ""),
            "to_value": filter_params.get("date_to", ""),
            "from_label": t("From", locale),
            "to_label": t("To", locale),
        },
        {
            "type": "text",
            "name": "q",
            "label": "",
            "value": filter_params.get("q", ""),
            "placeholder": t("Search by sender or subject...", locale),
        },
    ]

    if case_type_options:
        fields.append(
            _make_checkboxes(
                "case_type", t("Classification", locale), case_type_options
            )
        )
    if priority_options:
        fields.append(
            _make_checkboxes("priority", t("Priority", locale), priority_options)
        )
    if bitrix_status_options:
        fields.append(
            _make_checkboxes(
                "bitrix_status", t("Bitrix status", locale), bitrix_status_options
            )
        )

    current_columns = filter_params.get("columns", "")
    selected_set = (
        {k.strip() for k in current_columns.split(",") if k.strip()}
        if current_columns
        else set()
    )

    all_columns = [
        ("priority", "Priority"),
        ("client", "Sender"),
        ("subject", "Subject"),
        ("date", "Date"),
        ("classification", "Classification"),
        ("bitrix_status", "Bitrix status"),
    ]

    if not selected_set:
        selected_set = {key for key, _ in all_columns}

    column_toggles: list[dict[str, Any]] = []
    for key, label in all_columns:
        visible = key in selected_set
        if visible:
            new_set = selected_set - {key}
        else:
            new_set = selected_set | {key}
        new_columns_str = ",".join(sorted(new_set))
        toggle_params = dict(filter_params)
        if new_columns_str and new_columns_str != ",".join(k for k, _ in all_columns):
            toggle_params["columns"] = new_columns_str
        elif "columns" in toggle_params:
            del toggle_params["columns"]
        toggle_href = build_rop_url(
            tab="queue",
            period=current_period,
            lang=locale,
            run_id=run_id,
            page=page,
            page_size=page_size,
            sort=sort,
            order=order,
            filter_params=toggle_params,
        )
        column_toggles.append(
            {
                "key": key,
                "label": t(label, locale),
                "visible": visible,
                "toggle_href": toggle_href,
            }
        )

    hidden: dict[str, str] = {"tab": "queue"}
    if run_id:
        hidden["run_id"] = run_id
    if current_period:
        hidden["period"] = current_period
    if locale != "en":
        hidden["lang"] = locale
    if page > 1:
        hidden["page"] = "1"
    if page_size != DEFAULT_PAGE_SIZE:
        hidden["page_size"] = str(page_size)
    if sort != "received_at" or order != "desc":
        hidden["sort"] = sort
        hidden["order"] = order
    for key in ("case_type", "priority", "bitrix_status", "columns"):
        val = filter_params.get(key, "")
        if val:
            hidden[key] = val

    reset_href = build_rop_url(
        tab="queue",
        run_id=run_id,
        period=current_period,
        lang=locale,
    )

    return {
        "fields": fields,
        "hidden": hidden,
        "column_toggles": column_toggles,
        "reset": {
            "label": t("Reset", locale),
            "href": reset_href,
        },
    }


def _sort_href(
    base_href: str,
    current_sort: str,
    new_sort: str,
    current_order: str,
    filter_params: dict[str, str],
    page: int = 1,
    *,
    run_id: str = "",
    period: str = "",
    locale: str = "en",
    page_size: int = DEFAULT_PAGE_SIZE,
) -> str:
    if new_sort == current_sort:
        new_order = "asc" if current_order == "desc" else "desc"
    else:
        new_order = "desc"
    return build_rop_url(
        tab="queue",
        run_id=run_id,
        period=period,
        lang=locale,
        page_size=page_size,
        page=page,
        sort=new_sort,
        order=new_order,
        filter_params=filter_params,
    )


def _queue_page_size_options(
    *,
    run_id: str,
    locale: str,
    current_period: str,
    filter_params: dict[str, str],
    page_size: int,
    sort: str,
    order: str,
) -> list[dict[str, Any]]:
    return [
        {
            "value": str(option_size),
            "label": str(option_size),
            "active": option_size == page_size,
            "href": build_rop_url(
                tab="queue",
                run_id=run_id,
                period=current_period,
                lang=locale,
                page=1,
                page_size=option_size,
                sort=sort,
                order=order,
                filter_params=filter_params,
                extra={"page_size": str(option_size)},
            ),
        }
        for option_size in ALLOWED_PAGE_SIZES
    ]


def _queue_table(
    title: str,
    rows_source: list[dict[str, Any]],
    run_id: str = "",
    locale: str = "en",
    total_count: int = 0,
    page: int = 1,
    page_size: int = 25,
    total_pages: int = 1,
    sort: str = "received_at",
    order: str = "desc",
    filter_params: dict[str, str] | None = None,
    current_period: str = "",
    toolbar: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if filter_params is None:
        filter_params = {}

    base_href = _rop_href(
        tab="queue", period=current_period, locale=locale, run_id=run_id
    )

    rows = []
    for item in rows_source:
        if not isinstance(item, dict):
            continue
        event_id = str(item.get("event_id", ""))
        priority = item.get("bot_priority") or item.get("priority", "n/a")
        bitrix_status = item.get("bitrix_status", "unreconciled")
        raw_date = (
            item.get("date") or item.get("received_at") or item.get("event_date", "")
        )
        date_display = (
            _format_date_display(raw_date, locale) if raw_date else t("n/a", locale)
        )
        detail_href = item.get("detail_href")
        item_run_id = str(item.get("run_id") or run_id)
        if event_id and item_run_id:
            detail_href = _rop_event_detail_href(
                event_id,
                item_run_id,
                locale,
                current_period,
                filter_params,
                page,
                page_size,
                sort,
                order,
                str(item.get("event_instance_id") or ""),
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
                "date": date_display,
                "classification": case_type_label(
                    item.get("bot_case_type") or item.get("case_type", ""),
                    locale,
                ),
                "bitrix_status": {
                    "label": _bitrix_status_label(bitrix_status, locale),
                    "status": _bitrix_status_tone(bitrix_status),
                },
                "detail_href": detail_href if event_id else None,
            }
        )

    # Build columns with sortable headers
    columns = [
        {
            "key": "priority",
            "label": t("Priority", locale),
            "cell": "badge",
            "sortable": True,
            "sort_href": _sort_href(
                base_href,
                sort,
                "priority",
                order,
                filter_params,
                page,
                run_id=run_id,
                period=current_period,
                locale=locale,
                page_size=page_size,
            ),
            "sort_active": sort == "priority",
            "sort_direction": order if sort == "priority" else "",
        },
        {
            "key": "client",
            "label": t("Sender", locale),
            "cell": "avatar_text",
            "sortable": True,
            "sort_href": _sort_href(
                base_href,
                sort,
                "sender",
                order,
                filter_params,
                page,
                run_id=run_id,
                period=current_period,
                locale=locale,
                page_size=page_size,
            ),
            "sort_active": sort == "sender",
            "sort_direction": order if sort == "sender" else "",
        },
        {
            "key": "subject",
            "label": t("Subject", locale),
            "cell": "text",
            "sortable": True,
            "sort_href": _sort_href(
                base_href,
                sort,
                "subject",
                order,
                filter_params,
                page,
                run_id=run_id,
                period=current_period,
                locale=locale,
                page_size=page_size,
            ),
            "sort_active": sort == "subject",
            "sort_direction": order if sort == "subject" else "",
        },
        {
            "key": "date",
            "label": t("Date", locale),
            "cell": "text",
            "sortable": True,
            "sort_href": _sort_href(
                base_href,
                sort,
                "received_at",
                order,
                filter_params,
                page,
                run_id=run_id,
                period=current_period,
                locale=locale,
                page_size=page_size,
            ),
            "sort_active": sort == "received_at",
            "sort_direction": order if sort == "received_at" else "",
        },
        {
            "key": "classification",
            "label": t("Classification", locale),
            "cell": "text",
            "sortable": True,
            "sort_href": _sort_href(
                base_href,
                sort,
                "case_type",
                order,
                filter_params,
                page,
                run_id=run_id,
                period=current_period,
                locale=locale,
                page_size=page_size,
            ),
            "sort_active": sort == "case_type",
            "sort_direction": order if sort == "case_type" else "",
        },
        {
            "key": "bitrix_status",
            "label": t("Bitrix status", locale),
            "cell": "status",
            "sortable": True,
            "sort_href": _sort_href(
                base_href,
                sort,
                "bitrix_status",
                order,
                filter_params,
                page,
                run_id=run_id,
                period=current_period,
                locale=locale,
                page_size=page_size,
            ),
            "sort_active": sort == "bitrix_status",
            "sort_direction": order if sort == "bitrix_status" else "",
        },
    ]

    # Build pagination
    pagination_label = f"/ {total_count}"

    pagination_pages: list[dict[str, Any]] = []
    for p in range(1, total_pages + 1):
        href = build_rop_url(
            tab="queue",
            period=current_period,
            lang=locale,
            run_id=run_id,
            page=p,
            page_size=page_size,
            sort=sort,
            order=order,
            filter_params=filter_params,
        )
        pagination_pages.append(
            {
                "label": str(p),
                "href": href,
                "active": p == page,
            }
        )

    # Filter columns based on `columns` param (comma-separated list of keys to show)
    selected_columns_str = filter_params.get("columns", "")
    if selected_columns_str:
        selected_keys = {
            k.strip() for k in selected_columns_str.split(",") if k.strip()
        }
        columns = [c for c in columns if c["key"] in selected_keys]

    # Add detail column if any row has a detail link
    has_detail = any(row.get("detail_href") for row in rows)
    if has_detail:
        columns.append(
            {
                "key": "detail",
                "label": t("Detail", locale),
                "cell": "link",
            }
        )
        for row in rows:
            if row.get("detail_href"):
                row["detail"] = {
                    "label": t("View details", locale),
                    "href": row["detail_href"],
                }

    page_size_options = _queue_page_size_options(
        run_id=run_id,
        locale=locale,
        current_period=current_period,
        filter_params=filter_params,
        page_size=page_size,
        sort=sort,
        order=order,
    )
    result: dict[str, Any] = {
        "type": "data_table",
        "id": "rop-queue",
        "size": "XL",
        "title": title,
        "striped": True,
        "mobile": "md",
        "columns": columns,
        "rows": rows,
        "pagination": {
            "label": pagination_label,
            "page": page,
            "total": total_count,
            "start": (page - 1) * page_size + 1 if total_count > 0 else 0,
            "end": min(page * page_size, total_count),
            "pages": pagination_pages,
            "page_size": {
                "current": str(page_size),
                "options": page_size_options,
            },
        },
    }
    if toolbar:
        result["toolbar"] = toolbar
    return result


def _empty_queue_table(
    locale: str = "en",
    run_id: str = "",
    current_period: str = "",
    filter_params: dict[str, str] | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    sort: str = "received_at",
    order: str = "desc",
    toolbar: dict[str, Any] | None = None,
) -> dict[str, Any]:
    columns = [
        {"key": "priority", "label": t("Priority", locale), "cell": "badge"},
        {"key": "client", "label": t("Sender", locale), "cell": "avatar_text"},
        {"key": "subject", "label": t("Subject", locale), "cell": "text"},
        {"key": "date", "label": t("Date", locale), "cell": "text"},
        {"key": "classification", "label": t("Classification", locale), "cell": "text"},
        {"key": "bitrix_status", "label": t("Bitrix status", locale), "cell": "status"},
    ]
    if filter_params is None:
        filter_params = {}
    selected_columns = {
        key.strip()
        for key in filter_params.get("columns", "").split(",")
        if key.strip()
    }
    if selected_columns:
        columns = [column for column in columns if column["key"] in selected_columns]
    _, pagination = paginate_items([], page=page, page_size=page_size)
    result: dict[str, Any] = {
        "type": "data_table",
        "id": "rop-queue",
        "size": "XL",
        "title": t("ROP Work Queue", locale),
        "striped": True,
        "mobile": "md",
        "columns": columns,
        "rows": [],
        "pagination": {
            "label": "/ 0",
            "page": pagination["page"],
            "total": 0,
            "start": 0,
            "end": 0,
            "pages": [
                {
                    "label": "1",
                    "href": build_rop_url(
                        tab="queue",
                        run_id=run_id,
                        period=current_period,
                        lang=locale,
                        page=pagination["page"],
                        page_size=pagination["page_size"],
                        sort=sort,
                        order=order,
                        filter_params=filter_params,
                    ),
                    "active": True,
                }
            ],
            "page_size": {
                "current": str(pagination["page_size"]),
                "options": _queue_page_size_options(
                    run_id=run_id,
                    locale=locale,
                    current_period=current_period,
                    filter_params=filter_params,
                    page_size=pagination["page_size"],
                    sort=sort,
                    order=order,
                ),
            },
        },
    }
    if toolbar:
        result["toolbar"] = toolbar
    return result


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
                        "label": t("No sources", locale),
                        "value": t("No source data available", locale),
                        "status": "empty",
                    }
                ],
            }
        ]

    columns = [
        t("Source", locale),
        t("Type", locale),
        t("Status", locale),
        t("Reason", locale),
        t("Fetched", locale),
        t("Loaded", locale),
        t("Malformed", locale),
        t("Classified", locale),
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
            "title": t("Source Health Details", locale),
            "columns": columns,
            "rows": rows,
        }
    ]
