"""
ROP MVP handoff / readiness pack builder v0.

BeeAgent-owned: consolidates existing ROP artifacts into customer/demo-ready
JSON and Markdown report artifacts. No write-back, no new connectors,
no changes to beeagent-rop.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_PACK_ARTIFACT = "rop_mvp_pack.json"
_REPORT_ARTIFACT = "rop_mvp_report.md"
_LATEST_INTERFACE = "rop_mvp_latest.json"


def _int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _read_json_dict(path: Path) -> dict[str, Any] | None:
    data = _read_json(path)
    return data if isinstance(data, dict) else None


def _read_json_list(path: Path) -> list[dict[str, Any]] | None:
    data = _read_json(path)
    return data if isinstance(data, list) else None


def _resolve_run_dir(storage_dir: Path, run_id: str) -> Path:
    """Resolve and validate run directory, blocking path traversal."""
    runs_root = (storage_dir / "runs").resolve()
    run_dir = (runs_root / run_id).resolve()
    try:
        run_dir.relative_to(runs_root)
    except ValueError:
        raise ValueError(f"Invalid run_id: path traversal detected for '{run_id}'")
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")
    return run_dir


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Source coverage builder (from config, not hardcoded)
# ---------------------------------------------------------------------------


def _build_source_coverage(settings: dict) -> dict[str, Any]:
    """Read source coverage from config/settings.yml -> rop.sources[]."""
    raw_sources = settings.get("rop", {}).get("sources", [])
    if not isinstance(raw_sources, list):
        return {
            "configured": 0,
            "enabled": 0,
            "loaded": 0,
            "degraded": 0,
            "sources": [],
            "warning": "rop.sources not configured",
        }

    sources_info: list[dict[str, Any]] = []
    enabled_count = 0
    for s in raw_sources:
        if not isinstance(s, dict):
            continue
        enabled = bool(s.get("enabled", False))
        if enabled:
            enabled_count += 1
        sources_info.append(
            {
                "source_id": s.get("source_id", ""),
                "source_type": s.get("source_type", ""),
                "source_role": s.get("source_role", ""),
                "client_id": s.get("client_id", ""),
                "display_name": s.get("display_name", ""),
                "authority": s.get("authority", ""),
                "enabled": enabled,
            }
        )

    return {
        "configured": len(raw_sources),
        "enabled": enabled_count,
        "sources": sources_info,
    }


def _enrich_source_coverage_from_diag(
    coverage: dict[str, Any],
    source_diag: dict[str, Any] | None,
) -> dict[str, Any]:
    """Overlay runtime source diagnostics on top of config coverage."""
    if not isinstance(source_diag, dict):
        coverage["warning"] = "source_diagnostics.json not available; showing config-only coverage"
        return coverage

    agg = source_diag.get("aggregate", {})
    if isinstance(agg, dict):
        coverage["loaded"] = _int(agg.get("loaded_source_count", 0))
        coverage["degraded"] = _int(agg.get("degraded_source_count", 0))

    diag_sources = source_diag.get("sources", [])
    if isinstance(diag_sources, list):
        diag_map: dict[str, dict] = {}
        for ds in diag_sources:
            if isinstance(ds, dict):
                sid = ds.get("source_id", "")
                if sid:
                    diag_map[sid] = ds

        for s in coverage.get("sources", []):
            sid = s.get("source_id", "")
            ds = diag_map.get(sid)
            if isinstance(ds, dict):
                s["runtime_status"] = ds.get("status", "unknown")
                s["runtime_reason"] = ds.get("reason") or ds.get("degraded_reason")
                if ds.get("fetched_count") is not None:
                    s["fetched_count"] = _int(ds.get("fetched_count", 0))
                if ds.get("loaded_count") is not None:
                    s["loaded_count"] = _int(ds.get("loaded_count", 0))
            else:
                s["runtime_status"] = "not_loaded"

    # Infer loaded from runtime data
    loaded = sum(
        1
        for s in coverage.get("sources", [])
        if s.get("runtime_status") == "ok"
    )
    coverage["loaded"] = max(coverage.get("loaded", 0), loaded)

    # Degraded count from runtime data
    degraded = sum(
        1
        for s in coverage.get("sources", [])
        if s.get("runtime_status") in ("degraded", "error")
    )
    coverage["degraded"] = max(coverage.get("degraded", 0), degraded)

    return coverage


# ---------------------------------------------------------------------------
# Business summary builder
# ---------------------------------------------------------------------------


def _build_business_summary(
    current_state: dict[str, Any] | None,
    dashboard: dict[str, Any] | None,
    classified_events: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    kpi: dict[str, Any] = {}

    # Prefer dashboard business_kpi when available
    if isinstance(dashboard, dict):
        bkpi = dashboard.get("business_kpi", {})
        if isinstance(bkpi, dict):
            kpi.update(bkpi)

    # Fall back to current_state KPI
    if isinstance(current_state, dict):
        ckpi = current_state.get("kpi", {})
        if isinstance(ckpi, dict):
            for key in ("events_total", "normalized_count", "classified_count",
                        "high_priority", "needs_manual_review",
                        "matched_in_bitrix", "lost_in_bitrix",
                        "ambiguous_in_bitrix", "unreconciled",
                        "source_degraded", "attachment_count",
                        "attachment_refused"):
                if key not in kpi and key in ckpi:
                    kpi[key] = ckpi[key]

    # Compute from classified events if nothing else available
    if not kpi and isinstance(classified_events, list):
        kpi["classified_count"] = len(classified_events)
        kpi["high_priority"] = sum(
            1 for c in classified_events
            if isinstance(c, dict) and c.get("priority") == "high"
        )

    return kpi


# ---------------------------------------------------------------------------
# Queue builders (from current_state or classified events)
# ---------------------------------------------------------------------------


def _build_queues(
    current_state: dict[str, Any] | None,
    classified_events: list[dict[str, Any]] | None,
) -> dict[str, list[dict[str, Any]]]:
    """Build queue summaries from existing artifacts."""
    queues: dict[str, list[dict[str, Any]]] = {
        "high_priority": [],
        "needs_review": [],
        "lost_in_bitrix": [],
        "ambiguous_or_duplicate": [],
        "unreconciled": [],
        "matched": [],
        "degraded": [],
    }

    if isinstance(current_state, dict):
        cq = current_state.get("queues", {})
        if isinstance(cq, dict):
            for key in queues:
                raw = cq.get(key)
                if isinstance(raw, list):
                    queues[key] = raw

    # If no current_state, build minimal from classified events
    if not isinstance(current_state, dict) and isinstance(classified_events, list):
        for evt in classified_events:
            if not isinstance(evt, dict):
                continue
            entry = {
                "event_id": evt.get("event_id", ""),
                "case_type": evt.get("case_type", ""),
                "priority": evt.get("priority", ""),
                "is_fallback": bool(evt.get("is_fallback")),
            }
            if evt.get("priority") == "high":
                queues["high_priority"].append(entry)
            if evt.get("is_fallback") or evt.get("priority") == "high":
                queues["needs_review"].append(entry)
            queues["unreconciled"].append(entry)

    return queues


# ---------------------------------------------------------------------------
# Attachment summary
# ---------------------------------------------------------------------------


def _build_attachment_summary(
    attachment_extraction: dict[str, Any] | None,
) -> dict[str, Any]:
    default: dict[str, Any] = {
        "total_attachments": 0,
        "preview_available": 0,
        "refused": 0,
        "unsupported": 0,
        "oversized": 0,
    }
    if not isinstance(attachment_extraction, dict):
        return default

    agg = attachment_extraction.get("aggregate", {})
    if isinstance(agg, dict):
        default["total_attachments"] = _int(agg.get("attachment_count", 0))
        default["preview_available"] = _int(agg.get("preview_available_count", 0))
        default["refused"] = _int(agg.get("refused_count", 0))
        default["unsupported"] = _int(agg.get("unsupported_count", 0))
    return default


# ---------------------------------------------------------------------------
# First actions for ROP
# ---------------------------------------------------------------------------


def _build_first_actions(queues: dict[str, Any],
                         business_summary: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    hp = len(queues.get("high_priority", []))
    if hp > 0:
        actions.append({
            "priority": "high",
            "action": f"Review {hp} high-priority classified events",
            "type": "manual_review",
        })
    lost = len(queues.get("lost_in_bitrix", []))
    if lost > 0:
        actions.append({
            "priority": "medium",
            "action": f"Reconcile {lost} events not found in Bitrix",
            "type": "reconciliation",
        })
    ambiguous = len(queues.get("ambiguous_or_duplicate", []))
    if ambiguous > 0:
        actions.append({
            "priority": "medium",
            "action": f"Resolve {ambiguous} ambiguous/duplicate Bitrix matches",
            "type": "manual_review",
        })
    unreconciled = len(queues.get("unreconciled", []))
    if unreconciled > 0:
        actions.append({
            "priority": "low",
            "action": f"Run Bitrix reconciliation for {unreconciled} unreconciled events",
            "type": "reconciliation",
        })
    refused = business_summary.get("attachment_refused", 0)
    if refused > 0:
        actions.append({
            "priority": "low",
            "action": f"Review {refused} refused/unsupported attachments",
            "type": "manual_review",
        })
    source_degraded = business_summary.get("source_degraded", 0)
    if source_degraded > 0:
        actions.append({
            "priority": "medium",
            "action": f"Investigate {source_degraded} degraded source(s)",
            "type": "investigation",
        })
    if not actions:
        actions.append({
            "priority": "info",
            "action": "All indicators nominal; proceed to next ROP cycle",
            "type": "monitoring",
        })
    return actions


# ---------------------------------------------------------------------------
# Evidence links (safe, no secrets)
# ---------------------------------------------------------------------------


def _build_evidence_links(storage_dir: Path, run_id: str) -> list[dict[str, Any]]:
    """Build safe evidence links from available run-level artifacts."""
    evidence_ids = (
        "operator_summary_json",
        "source_diagnostics_json",
        "intake_metadata_json",
        "attachment_extraction_json",
        "normalized_events_json",
        "classified_events_json",
        "rop_review_table_tsv",
        "rop_current_state_json",
        "bitrix_reconciliation_json",
    )
    links: list[dict[str, Any]] = []
    for aid in evidence_ids:
        links.append({
            "artifact_id": aid,
            "label": aid.replace("_", " ").title(),
            "href": f"/runs/{run_id}/artifacts/{aid}",
            "available": False,
        })
    return links


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_rop_mvp_pack(
    storage_dir: Path,
    run_id: str,
    period: str,
    settings: dict,
    logger: logging.Logger,
) -> dict[str, Any]:
    """Build the MVP handoff/readiness pack for a given run.

    Returns the pack dict (also written to disk). The pack is always
    read-only and explicitly flagged as non-production.
    """
    logger.info("ROP MVP pack: building for run_id=%s period=%s", run_id, period)

    run_dir = _resolve_run_dir(storage_dir, run_id)

    # --- Read existing artifacts (best-effort) ---
    current_state = _read_json_dict(run_dir / "rop_current_state.json")
    source_diag = _read_json_dict(run_dir / "source_diagnostics.json")
    intake = _read_json_dict(run_dir / "intake_metadata.json")
    normalized_events = _read_json_list(run_dir / "normalized_events.json")
    classified_events = _read_json_list(run_dir / "classified_events.json")
    attachment_extraction = _read_json_dict(run_dir / "attachment_extraction.json")
    bitrix_reconciliation = _read_json_dict(run_dir / "bitrix_reconciliation.json")
    operator_summary = _read_json_dict(run_dir / "operator_summary.json")

    # Dashboard from interfaces (may exist without current run)
    interfaces_dir = storage_dir / "interfaces"
    dashboard = _read_json_dict(interfaces_dir / "rop_dashboard.json")

    warnings: list[str] = []

    # --- Source coverage from config enriched with diagnostics ---
    source_coverage = _build_source_coverage(settings)
    source_coverage = _enrich_source_coverage_from_diag(source_coverage, source_diag)
    loaded = _int(source_coverage.get("loaded", 0))
    degraded = _int(source_coverage.get("degraded", 0))
    if loaded == 0:
        warnings.append("No sources loaded; coverage data reflects config only")
    if degraded > 0:
        warnings.append(f"{degraded} source(s) reported degradation")

    # --- Client ID ---
    client_id = "unknown"
    if isinstance(current_state, dict):
        cid = current_state.get("client_id")
        if isinstance(cid, str) and cid:
            client_id = cid
    if client_id == "unknown" and isinstance(source_diag, dict):
        for s in source_diag.get("sources", []):
            if isinstance(s, dict) and s.get("client_id"):
                client_id = s["client_id"]
                break
    if client_id == "unknown" and isinstance(intake, dict):
        for s in intake.get("sources", []):
            if isinstance(s, dict) and s.get("client_id"):
                client_id = s["client_id"]
                break

    # --- Business summary ---
    business_summary = _build_business_summary(
        current_state, dashboard, classified_events,
    )

    # --- Queues ---
    queues = _build_queues(current_state, classified_events)

    # --- Attachment summary ---
    attachment_summary = _build_attachment_summary(attachment_extraction)

    # --- First actions ---
    first_actions = _build_first_actions(queues, business_summary)

    # --- Bitrix evidence status ---
    bitrix_status = "unreconciled"
    if isinstance(bitrix_reconciliation, dict):
        bitrix_status = bitrix_reconciliation.get("status", "unreconciled")

    # --- Demo readiness ---
    demo_readiness = _build_demo_readiness(
        warnings=warnings,
        source_coverage=source_coverage,
        business_summary=business_summary,
        bitrix_status=bitrix_status,
    )

    # --- Evidence links (safe, no secrets) ---
    evidence_links = _build_evidence_links(storage_dir, run_id)

    # --- Known limitations ---
    limitations = _build_limitations(
        bitrix_reconciliation=bitrix_reconciliation,
        attachment_extraction=attachment_extraction,
    )

    # Assemble pack
    pack: dict[str, Any] = {
        "run_id": run_id,
        "period": period,
        "status": demo_readiness["status"],
        "read_only": True,
        "non_production": True,
        "generated_at_utc": _now_utc(),
        "client_id": client_id,
        "source_coverage": source_coverage,
        "business_summary": business_summary,
        "queues": {
            "high_priority_count": len(queues.get("high_priority", [])),
            "needs_review_count": len(queues.get("needs_review", [])),
            "lost_in_bitrix_count": len(queues.get("lost_in_bitrix", [])),
            "ambiguous_or_duplicate_count": len(
                queues.get("ambiguous_or_duplicate", [])
            ),
            "unreconciled_count": len(queues.get("unreconciled", [])),
            "matched_count": len(queues.get("matched", [])),
            "degraded_count": len(queues.get("degraded", [])),
        },
        "attachment_summary": attachment_summary,
        "first_actions": first_actions,
        "demo_readiness": demo_readiness,
        "evidence_links": evidence_links,
        "limitations": limitations,
        "warnings": warnings,
    }

    logger.info(
        "ROP MVP pack built: run_id=%s status=%s client_id=%s warnings=%d",
        run_id,
        pack["status"],
        client_id,
        len(warnings),
    )
    return pack


# ---------------------------------------------------------------------------
# Demo readiness
# ---------------------------------------------------------------------------


def _build_demo_readiness(
    warnings: list[str],
    source_coverage: dict[str, Any],
    business_summary: dict[str, Any],
    bitrix_status: str,
) -> dict[str, Any]:
    ready_items: list[str] = []
    limitations: list[str] = []
    blockers: list[str] = []

    loaded = _int(source_coverage.get("loaded", 0))
    degraded = _int(source_coverage.get("degraded", 0))

    if loaded > 0:
        ready_items.append(f"{loaded} source(s) loaded successfully")
    if not warnings:
        ready_items.append("All artifacts are consistent")
    if business_summary:
        classified = business_summary.get("classified_count", 0)
        if classified > 0:
            ready_items.append(f"{classified} events classified")
    if bitrix_status == "ok":
        ready_items.append("Bitrix reconciliation completed")

    if degraded > 0:
        limitations.append(f"{degraded} source(s) degraded")
    if bitrix_status != "ok" and bitrix_status != "unreconciled":
        limitations.append(f"Bitrix status: {bitrix_status}")

    if loaded == 0:
        blockers.append("No sources loaded — check ingestion pipeline")
    if source_coverage.get("configured", 0) == 0:
        blockers.append("No sources configured in settings")

    if blockers:
        status = "blocked"
    elif limitations:
        status = "ready_with_limitations"
    else:
        status = "ready"

    return {
        "status": status,
        "ready_items": ready_items,
        "limitations": limitations,
        "blockers": blockers,
    }


# ---------------------------------------------------------------------------
# Known limitations
# ---------------------------------------------------------------------------


def _build_limitations(
    bitrix_reconciliation: dict[str, Any] | None,
    attachment_extraction: dict[str, Any] | None,
) -> list[str]:
    limitations: list[str] = [
        "Read-only snapshot; no Bitrix write-back",
        "No CRM task creation",
        "No manager scoring",
        "No 1C integration",
        "No OCR/deep document parsing",
        "No AI recommendations for next actions",
        "No open registries integration",
    ]

    if not isinstance(bitrix_reconciliation, dict):
        limitations.append("Bitrix reconciliation not yet run")
    if not isinstance(attachment_extraction, dict):
        limitations.append("Attachment extraction not yet run")

    return limitations


# ---------------------------------------------------------------------------
# Markdown report builder
# ---------------------------------------------------------------------------


def build_mvp_report_markdown(pack: dict[str, Any]) -> str:
    """Build a human-readable Markdown report from the MVP pack."""
    lines: list[str] = []
    _md = lines.append

    _md("# ROP MVP Handoff Report")
    _md("")
    _md(f"**Generated at (UTC):** {pack.get('generated_at_utc', '?')}")
    _md(f"**Status:** {pack.get('status', '?')}")
    _md(f"**Read-only:** {pack.get('read_only', False)}")
    _md(f"**Non-production snapshot:** {pack.get('non_production', True)}")
    _md("")

    # --- Executive summary ---
    _md("## Executive Summary")
    _md("")
    ds = pack.get("demo_readiness", {})
    _md(f"- **Demo readiness:** {ds.get('status', '?')}")
    for item in ds.get("ready_items", []):
        _md(f"  - ✅ {item}")
    for lim in ds.get("limitations", []):
        _md(f"  - ⚠️ {lim}")
    for blocker in ds.get("blockers", []):
        _md(f"  - 🚫 {blocker}")
    _md("")

    # --- Period and run ---
    _md("## Period and Run")
    _md("")
    _md(f"- **Run ID:** `{pack.get('run_id', '?')}`")
    _md(f"- **Period:** `{pack.get('period', '?')}`")
    _md(f"- **Client ID:** `{pack.get('client_id', '?')}`")
    _md("")

    # --- Source coverage ---
    _md("## Source Coverage")
    _md("")
    sc = pack.get("source_coverage", {})
    _md(f"- **Configured sources:** {sc.get('configured', 0)}")
    _md(f"- **Enabled sources:** {sc.get('enabled', 0)}")
    _md(f"- **Loaded sources:** {sc.get('loaded', 0)}")
    _md(f"- **Degraded sources:** {sc.get('degraded', 0)}")
    for s in sc.get("sources", []):
        if isinstance(s, dict):
            status = s.get("runtime_status", "configured")
            icon = "✅" if status == "ok" else "⚠️" if status in ("degraded",) else "❌"
            _md(
                f"  - {icon} `{s.get('source_id', '?')}` — {s.get('display_name', '?')} "
                f"({s.get('source_type', '?')}) status={status}"
            )
    warning = sc.get("warning")
    if warning:
        _md(f"  - ⚠️ *{warning}*")
    _md("")

    # --- Business KPI ---
    _md("## Business KPI")
    _md("")
    bkpi = pack.get("business_summary", {})
    if bkpi:
        _md(f"- **Processed events:** {bkpi.get('processed_events', bkpi.get('classified_count', 0))}")
        _md(f"- **High priority:** {bkpi.get('high_priority', 0)}")
        _md(f"- **Needs review:** {bkpi.get('needs_review', bkpi.get('needs_manual_review', 0))}")
        _md(f"- **Matched in Bitrix:** {bkpi.get('matched_in_bitrix', 0)}")
        _md(f"- **Lost in Bitrix:** {bkpi.get('lost_in_bitrix', 0)}")
        _md(f"- **Ambiguous/duplicate:** {bkpi.get('ambiguous_in_bitrix', 0)}")
        _md(f"- **Unreconciled:** {bkpi.get('unreconciled', 0)}")
        _md(f"- **Source degraded:** {bkpi.get('source_degraded', 0)}")
        _md(f"- **Attachment refused:** {bkpi.get('attachment_refused', 0)}")
    else:
        _md("- No KPI data available")
    _md("")

    # --- First actions for ROP ---
    _md("## First Actions for ROP")
    _md("")
    actions = pack.get("first_actions", [])
    if actions:
        for action in actions:
            prio = action.get("priority", "?")
            icon = "🔴" if prio == "high" else "🟡" if prio == "medium" else "🟢"
            _md(f"- {icon} **[{prio}]** {action.get('action', '')} *(type: {action.get('type', '?')})*")
    else:
        _md("- No actions identified")
    _md("")

    # --- Queues summary ---
    _md("## Queues")
    _md("")
    q = pack.get("queues", {})
    _md(f"- **High-priority queue:** {q.get('high_priority_count', 0)}")
    _md(f"- **Needs review:** {q.get('needs_review_count', 0)}")
    _md(f"- **Lost in Bitrix:** {q.get('lost_in_bitrix_count', 0)}")
    _md(f"- **Ambiguous/duplicate:** {q.get('ambiguous_or_duplicate_count', 0)}")
    _md(f"- **Unreconciled:** {q.get('unreconciled_count', 0)}")
    _md(f"- **Matched:** {q.get('matched_count', 0)}")
    _md(f"- **Degraded:** {q.get('degraded_count', 0)}")
    _md("")

    # --- Bitrix evidence ---
    _md("## Bitrix Evidence")
    _md("")
    bkpi = pack.get("business_summary", {})
    total_bitrix = (
        bkpi.get("matched_in_bitrix", 0)
        + bkpi.get("lost_in_bitrix", 0)
        + bkpi.get("ambiguous_in_bitrix", 0)
        + bkpi.get("bitrix_errors", 0)
    )
    bitrix_status = "reconciled" if total_bitrix > 0 else "unreconciled"
    _md(f"- **Status:** {bitrix_status}")
    _md(f"- **Matched in Bitrix:** {bkpi.get('matched_in_bitrix', 0)}")
    _md(f"- **Lost in Bitrix:** {bkpi.get('lost_in_bitrix', 0)}")
    _md(f"- **Ambiguous/duplicate:** {bkpi.get('ambiguous_in_bitrix', 0)}")
    _md(f"- **Unreconciled:** {bkpi.get('unreconciled', 0)}")
    _md(f"- **Bitrix errors:** {bkpi.get('bitrix_errors', 0)}")
    limitations_list = pack.get("limitations", [])
    if any("Bitrix reconciliation not yet run" in lim for lim in limitations_list):
        _md("")
        _md("⚠️ **Note:** Bitrix reconciliation has not been run for this period. "
            "Run `rop reconcile-bitrix` to enable Bitrix evidence.")
    _md("")

    # --- Attachment evidence ---
    _md("## Attachment Evidence")
    _md("")
    attn = pack.get("attachment_summary", {})
    _md(f"- **Total attachments:** {attn.get('total_attachments', 0)}")
    _md(f"- **Preview available:** {attn.get('preview_available', 0)}")
    _md(f"- **Refused/unsupported:** {attn.get('refused', 0)}")
    _md("")

    # --- Evidence artifacts ---
    _md("## Evidence Artifacts")
    _md("")
    links = pack.get("evidence_links", [])
    if links:
        for link in links:
            _md(f"- `{link.get('artifact_id', '?')}` — {link.get('label', '?')}")
    _md("")

    # --- Known limitations ---
    _md("## Known Limitations")
    _md("")
    for lim in pack.get("limitations", []):
        _md(f"- {lim}")
    _md("")

    # --- Not included in MVP ---
    _md("## Not Included in MVP")
    _md("")
    not_included = [
        "Bitrix write-back (CRM write methods, task creation)",
        "Manager scoring",
        "1C integration",
        "Open registries",
        "Web-triggered ROP run",
        "Auth/RBAC",
        "Control Panel",
        "OCR/deep document parsing",
        "AI recommendations for next actions",
    ]
    for item in not_included:
        _md(f"- {item}")
    _md("")

    # --- Recommended next step ---
    _md("## Recommended Next Step")
    _md("")
    if pack.get("status") == "ready":
        _md("Proceed to pilot: run live ROP cycle with Bitrix reconciliation enabled.")
    elif pack.get("status") == "ready_with_limitations":
        _md(
            "Address limitations above, then proceed to pilot. "
            "Consider enabling Bitrix reconciliation and investigating degraded sources."
        )
    else:
        _md("Resolve blockers before proceeding to pilot.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Disk I/O
# ---------------------------------------------------------------------------


def write_mvp_pack_artifacts(
    storage_dir: Path,
    run_id: str,
    pack: dict[str, Any],
    logger: logging.Logger,
) -> dict[str, Path]:
    """Write MVP pack JSON, Markdown report, and update interface file."""
    runs_root = (storage_dir / "runs").resolve()
    run_dir = (runs_root / run_id).resolve()
    try:
        run_dir.relative_to(runs_root)
    except ValueError:
        raise ValueError(f"Invalid run_id: path traversal detected for '{run_id}'")

    run_dir.mkdir(parents=True, exist_ok=True)

    # JSON pack
    pack_path = run_dir / _PACK_ARTIFACT
    pack_path.write_text(
        json.dumps(pack, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(
        "ROP MVP pack written: %s",
        str(pack_path.relative_to(storage_dir)),
    )

    # Markdown report
    report_md = build_mvp_report_markdown(pack)
    report_path = run_dir / _REPORT_ARTIFACT
    report_path.write_text(report_md, encoding="utf-8")
    logger.info(
        "ROP MVP report written: %s",
        str(report_path.relative_to(storage_dir)),
    )

    # Interface file (latest)
    interfaces_dir = (storage_dir / "interfaces").resolve()
    interfaces_dir.mkdir(parents=True, exist_ok=True)
    latest_path = interfaces_dir / _LATEST_INTERFACE
    latest_data = {
        "run_id": run_id,
        "period": pack.get("period"),
        "status": pack.get("status"),
        "read_only": True,
        "non_production": True,
        "generated_at_utc": pack.get("generated_at_utc"),
        "client_id": pack.get("client_id"),
        "source_coverage": {
            "configured": pack.get("source_coverage", {}).get("configured", 0),
            "enabled": pack.get("source_coverage", {}).get("enabled", 0),
            "loaded": pack.get("source_coverage", {}).get("loaded", 0),
            "degraded": pack.get("source_coverage", {}).get("degraded", 0),
        },
        "business_summary": {
            "classified_count": pack.get("business_summary", {}).get(
                "classified_count", 0
            ),
            "high_priority": pack.get("business_summary", {}).get(
                "high_priority", 0
            ),
            "lost_in_bitrix": pack.get("business_summary", {}).get(
                "lost_in_bitrix", 0
            ),
            "unreconciled": pack.get("business_summary", {}).get(
                "unreconciled", 0
            ),
        },
        "demo_readiness": pack.get("demo_readiness", {}),
        "warnings": pack.get("warnings", []),
    }
    latest_path.write_text(
        json.dumps(latest_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(
        "ROP MVP interface updated: %s",
        str(latest_path.relative_to(storage_dir)),
    )

    return {
        "pack": pack_path,
        "report": report_path,
        "latest": latest_path,
    }
