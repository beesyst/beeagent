from __future__ import annotations

import logging
from html import escape
from pathlib import Path
from typing import Any

from beeui_module.adapters.envelopes import (
    AdapterErrorResult,
    AdapterResult,
)
from beeui_module.adapters.ids import validate_run_id
from beeui_module.web.app import create_beeui_app
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.routing import APIRoute

from beeagent_module.core.paths import get_project_root
from beeagent_module.interfaces.ui.adapter import BeeAgentUiAdapter


# Утилита для извлечения данных из результата адаптера с дефолтным значением при ошибке
def _result_data(
    result: AdapterResult | AdapterErrorResult,
    default: Any,
) -> Any:
    if isinstance(result, AdapterErrorResult):
        return default
    return result.data


def _result_warnings(
    result: AdapterResult | AdapterErrorResult,
) -> list[dict[str, Any]]:
    if isinstance(result, AdapterErrorResult):
        return []

    warnings = getattr(result, "warnings", []) or []
    serialized: list[dict[str, Any]] = []

    for warning in warnings:
        if isinstance(warning, dict):
            serialized.append(warning)
            continue

        code = getattr(warning, "code", "warning")
        message = getattr(warning, "message", str(warning))
        serialized.append({"code": code, "message": message})

    return serialized


# Утилита для формирования JSON-ответов с данными или ошибками для API маршрутов
def _ok_json(
    data: Any,
    warnings: list[Any] | None = None,
    meta: dict[str, Any] | None = None,
    status_code: int = 200,
) -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "read_only": True,
            "data": data,
            "warnings": warnings or [],
            "meta": meta or {},
        },
        status_code=status_code,
    )


def _error_json(
    code: str,
    message: str | None = None,
    status_code: int = 400,
    error: dict[str, Any] | None = None,
) -> JSONResponse:
    payload_error = dict(error) if error is not None else {"code": code}
    if message:
        payload_error["message"] = message

    return JSONResponse(
        {
            "ok": False,
            "read_only": True,
            "error": payload_error,
            "warnings": [],
            "meta": {},
        },
        status_code=status_code,
    )


# Экранирование artifact-derived значений перед ручной HTML-сборкой
def _html(value: Any) -> str:
    if value is None:
        return ""
    return escape(str(value), quote=True)


# Создание словаря настроек для BeeUI
def build_beeui_settings(agent_settings: dict[str, Any]) -> dict[str, Any]:
    web_cfg = agent_settings.get("web", {})
    log_cfg = agent_settings.get("logging", {})

    return {
        "app": {
            "name": "beeui",
            "environment": agent_settings.get("app", {}).get("env", "dev"),
        },
        "web": {
            "host": web_cfg.get("host", "127.0.0.1"),
            "port": web_cfg.get("port", 8000),
            "open_browser": web_cfg.get("open_browser", False),
            "route_prefix": "",
            "cache_static": 3600,
        },
        "logging": {
            "clear_logs": log_cfg.get("clear_logs", True),
            "utc": log_cfg.get("utc", True),
            "level": log_cfg.get("level", "INFO"),
            "file": "logs/app.log",
        },
        "security": {
            "html_autoescape": True,
            "assets_ext": False,
        },
        "auth": {
            "enabled": False,
        },
        "features": {
            "browser_artifact": False,
            "config_preview": False,
            "config_apply": False,
            "operator_actions": False,
            "api": False,
        },
        "product": {
            "id": "beeagent",
            "title": "BeeAgent",
        },
        "storage": {
            "enabled": True,
            "root": "storage",
        },
    }


# Создание FastAPI приложения с BeeUI и адаптером BeeAgent
def build_beeui_app(
    settings: dict[str, Any],
    logger: logging.Logger,
    storage_dir: Path | None = None,
) -> FastAPI:
    from beeagent_module.core.paths import get_storage_dir as _get_storage_dir

    resolved_storage = storage_dir or _get_storage_dir()
    beeui_settings = build_beeui_settings(settings)

    adapter = BeeAgentUiAdapter(
        storage_dir=resolved_storage,
        settings=settings,
    )

    config_path = get_project_root() / "config" / "beeui.yml"

    app = create_beeui_app(
        settings=beeui_settings,
        product_id="beeagent",
        product_title="BeeAgent",
        adapter=adapter,
        config_path=str(config_path),
    )

    _prune_beeui_routes(app)

    app.state.beeagent_logger = logger
    app.state.beeagent_settings = settings
    app.state.beeagent_storage_dir = resolved_storage

    _register_custom_routes(app, adapter, logger)

    return app


# Регистрация кастомных маршрутов для BeeAgent, не покрываемых базовой консолью BeeUI
def _register_custom_routes(
    app: FastAPI,
    adapter: BeeAgentUiAdapter,
    logger: logging.Logger,
) -> None:
    @app.get("/health", response_class=JSONResponse, include_in_schema=False)
    async def health() -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "app": "beeagent",
                "read_only": True,
            }
        )

    @app.get("/rop", response_class=HTMLResponse, include_in_schema=False)
    async def rop_dashboard_html(request: Request) -> HTMLResponse:
        run_id_param = request.query_params.get("run_id")
        result = adapter.get_rop_dashboard(run_id=run_id_param)
        if isinstance(result, AdapterErrorResult):
            return HTMLResponse(
                content="<h1>ROP Dashboard unavailable</h1><p>No runs found.</p>",
                status_code=404,
            )
        data = _result_data(result, {})
        run_id = data.get("run_id", "N/A")
        kpis = data.get("kpis", {})
        funnel = data.get("funnel", [])
        source_health = data.get("source_health", [])
        class_dist = data.get("classification_distribution", {})
        attachment_summary = data.get("attachment_summary", {})
        recommendations = data.get("recommendations", [])
        attention_events = data.get("attention_events", [])
        evidence_links = data.get("evidence_links", [])
        warnings = data.get("warnings", [])
        available_runs = data.get("available_runs", [])

        html_parts = [
            "<!DOCTYPE html><html><head><meta charset='utf-8'>",
            "<title>ROP Dashboard</title>",
            "<style>"
            "body{font-family:sans-serif;margin:2em;background:#1a1d23;color:#e5e7eb}"
            "a{color:#60a5fa}h2{border-bottom:1px solid #374151;padding-bottom:6px}"
            "table{border-collapse:collapse;width:100%;margin-bottom:1em}"
            "th,td{border:1px solid #374151;padding:8px;text-align:left}"
            "th{background:#374151}.kpi{display:inline-block;margin:8px;padding:12px 20px;"
            "background:#2d3748;border-radius:8px;min-width:120px}"
            ".kpi-val{font-size:1.8em;font-weight:bold;color:#60a5fa}"
            ".kpi-label{font-size:0.85em;color:#9ca3af}"
            ".rec-warn{border-left:4px solid #f59e0b;background:#2d3748;padding:10px 14px;margin:6px 0}"
            ".rec-info{border-left:4px solid #3b82f6;background:#2d3748;padding:10px 14px;margin:6px 0}"
            ".warn{color:#f59e0b}.degraded{color:#ef4444}.ok{color:#22c55e}"
            ".severity-warning{color:#f59e0b}.severity-info{color:#60a5fa}"
            "</style></head><body>",
            "<h1>ROP Dashboard</h1>",
        ]

        # Run selector
        html_parts.append(f"<p>Run: <strong>{_html(run_id)}</strong></p>")
        if len(available_runs) > 1:
            html_parts.append("<p>Available runs:")
            for rid in available_runs:
                if rid == run_id:
                    html_parts.append(f" <strong>{_html(rid)}</strong>")
                else:
                    html_parts.append(
                        f' <a href="/rop?run_id={_html(rid)}">{_html(rid)}</a>'
                    )
            html_parts.append("</p>")

        # Warnings
        if warnings:
            html_parts.append("<h2>Warnings</h2>")
            for w in warnings:
                msg = w.get("message", w.get("code", "Warning"))
                html_parts.append(f'<p class="warn">⚠ {_html(msg)}</p>')

        # KPI cards
        html_parts.append("<h2>KPIs</h2><div>")
        kpi_fields = [
            ("Status", "run_status"),
            ("Sources", "source_count"),
            ("Loaded sources", "loaded_source_count"),
            ("Degraded", "degraded_source_count"),
            ("Fetched", "fetched_count"),
            ("Loaded", "loaded_count"),
            ("Malformed", "malformed_count"),
            ("Normalized", "normalized_count"),
            ("Classified", "classified_count"),
            ("Fallback", "fallback_count"),
            ("High pri", "high_priority_count"),
            ("Medium pri", "medium_priority_count"),
            ("Low pri", "low_priority_count"),
            ("Attachments", "attachment_count"),
            ("Preview", "attachment_preview_count"),
            ("Refused", "attachment_refused_count"),
        ]
        for label, key in kpi_fields:
            val = kpis.get(key, 0)
            html_parts.append(
                f'<div class="kpi"><div class="kpi-val">{_html(val)}</div>'
                f'<div class="kpi-label">{_html(label)}</div></div>'
            )
        html_parts.append("</div>")

        # Processing funnel
        if funnel:
            html_parts.append(
                "<h2>Processing Funnel</h2><table><tr><th>Stage</th><th>Count</th></tr>"
            )
            for stage in funnel:
                html_parts.append(
                    f"<tr><td>{_html(stage.get('stage', ''))}</td>"
                    f"<td>{_html(stage.get('count', 0))}</td></tr>"
                )
            html_parts.append("</table>")

        # Recommendations
        if recommendations:
            html_parts.append("<h2>Recommendations</h2>")
            for rec in recommendations:
                cls = "rec-warn" if rec.get("severity") == "warning" else "rec-info"
                html_parts.append(
                    f'<div class="{cls}">'
                    f'<strong class="severity-{_html(rec.get("severity", "info"))}">'
                    f"{_html(rec.get('severity', 'info').upper())}</strong>: "
                    f"{_html(rec.get('title', ''))} — {_html(rec.get('message', ''))}"
                    f"</div>"
                )

        # Source health
        if source_health:
            html_parts.append(
                "<h2>Source Health</h2><table>"
                "<tr><th>Source</th><th>Type</th><th>Status</th>"
                "<th>Reason</th><th>Fetched</th><th>Loaded</th>"
                "<th>Malformed</th><th>Classified</th><th>Fallback</th></tr>"
            )
            for sh in source_health:
                status = _html(sh.get("status", ""))
                status_class = (
                    "degraded" if sh.get("status") in ("degraded", "error") else "ok"
                )
                html_parts.append(
                    f"<tr><td>{_html(sh.get('display_name', ''))}</td>"
                    f"<td>{_html(sh.get('source_type', ''))}</td>"
                    f'<td class="{status_class}">{status}</td>'
                    f"<td>{_html(sh.get('reason', ''))}</td>"
                    f"<td>{_html(sh.get('fetched_count', 0))}</td>"
                    f"<td>{_html(sh.get('loaded_count', 0))}</td>"
                    f"<td>{_html(sh.get('malformed_count', 0))}</td>"
                    f"<td>{_html(sh.get('classified_count', 0))}</td>"
                    f"<td>{_html(sh.get('fallback_count', 0))}</td></tr>"
                )
            html_parts.append("</table>")

        case_type_counts = class_dist.get("case_type_counts", {})
        priority_counts = class_dist.get("priority_counts", {})
        reason_code_counts = class_dist.get("reason_code_counts", {})
        if case_type_counts:
            html_parts.append(
                "<h2>Case Types</h2><table><tr><th>Type</th><th>Count</th></tr>"
            )
            for ct, count in sorted(case_type_counts.items()):
                html_parts.append(
                    f"<tr><td>{_html(ct)}</td><td>{_html(count)}</td></tr>"
                )
            html_parts.append("</table>")
        if priority_counts:
            html_parts.append(
                "<h2>Priorities</h2><table><tr><th>Priority</th><th>Count</th></tr>"
            )
            for p, count in sorted(priority_counts.items()):
                html_parts.append(
                    f"<tr><td>{_html(p)}</td><td>{_html(count)}</td></tr>"
                )
            html_parts.append("</table>")
        if reason_code_counts:
            html_parts.append(
                "<h2>Reason Codes</h2><table><tr><th>Code</th><th>Count</th></tr>"
            )
            for rc, count in sorted(reason_code_counts.items()):
                html_parts.append(
                    f"<tr><td>{_html(rc)}</td><td>{_html(count)}</td></tr>"
                )
            html_parts.append("</table>")

        # Attachment summary
        if attachment_summary and attachment_summary.get("total_attachments", 0) > 0:
            html_parts.append(
                "<h2>Attachment Summary</h2><table><tr><th>Metric</th><th>Value</th></tr>"
            )
            for key, label in [
                ("total_attachments", "Total"),
                ("preview_available_count", "Preview available"),
                ("refused_count", "Refused"),
                ("blocked_count", "Blocked"),
                ("unsupported_count", "Unsupported"),
                ("oversized_count", "Oversized"),
                ("extraction_error_count", "Extraction errors"),
            ]:
                html_parts.append(
                    f"<tr><td>{label}</td><td>{_html(attachment_summary.get(key, 0))}</td></tr>"
                )
            html_parts.append("</table>")

        if attention_events:
            html_parts.append(
                "<h2>Attention Events</h2><p>Showing up to 50 events needing review.</p>"
                "<table><tr><th>Event ID</th><th>Source</th><th>Sender</th>"
                "<th>Subject</th><th>Type</th><th>Priority</th>"
                "<th>Confidence</th><th>Reason</th><th>Review reason</th></tr>"
            )
            for evt in attention_events:
                html_parts.append(
                    f"<tr><td>{_html(evt.get('event_id', ''))}</td>"
                    f"<td>{_html(evt.get('source_display_name', evt.get('source_id', '')))}</td>"
                    f"<td>{_html(evt.get('sender', ''))}</td>"
                    f"<td>{_html(evt.get('subject', ''))}</td>"
                    f"<td>{_html(evt.get('case_type', ''))}</td>"
                    f"<td>{_html(evt.get('priority', ''))}</td>"
                    f"<td>{_html(evt.get('confidence', ''))}</td>"
                    f"<td>{_html(evt.get('reason_code', ''))}</td>"
                    f"<td>{_html(evt.get('review_reason', ''))}</td></tr>"
                )
            html_parts.append("</table>")

        if evidence_links:
            html_parts.append("<h2>Evidence Links</h2><ul>")
            for link in evidence_links:
                label = _html(link.get("label", link.get("artifact_id", "")))
                if link.get("available"):
                    url = _html(link.get("url", ""))
                    html_parts.append(f'<li><a href="{url}">{label}</a> ✓</li>')
                else:
                    html_parts.append(
                        f"<li>{label} — <span class='warn'>unavailable</span></li>"
                    )
            html_parts.append("</ul>")

        html_parts.append('<p><a href="/">← Back to Dashboard</a></p></body></html>')
        return HTMLResponse(content="\n".join(html_parts))

    @app.get("/modules", response_class=HTMLResponse, include_in_schema=False)
    async def modules_html(request: Request) -> HTMLResponse:
        result = adapter.get_modules_dashboard()
        modules_list: list[dict[str, Any]] = []
        if not isinstance(result, AdapterErrorResult):
            modules_data = result.data.get("modules", [])
            if isinstance(modules_data, list):
                modules_list = [item for item in modules_data if isinstance(item, dict)]

        html_parts = [
            "<!DOCTYPE html><html><head><meta charset='utf-8'>",
            "<title>Modules</title>",
            "<style>body{font-family:sans-serif;margin:2em;background:#1a1d23;color:#e5e7eb}"
            "table{border-collapse:collapse;width:100%}"
            "th,td{border:1px solid #374151;padding:8px;text-align:left}"
            "th{background:#374151}a{color:#60a5fa}</style>",
            "</head><body>",
            "<h1>Module Diagnostics</h1>",
        ]

        if not modules_list:
            html_parts.append("<p>No modules registered.</p>")
        else:
            html_parts.append(
                "<table><tr><th>ID</th><th>Package</th><th>Entry</th>"
                "<th>State</th><th>Error</th></tr>"
            )
            for m in modules_list:
                html_parts.append(
                    f"<tr><td>{_html(m.get('id', ''))}</td>"
                    f"<td>{_html(m.get('package', ''))}</td>"
                    f"<td>{_html(m.get('entry', ''))}</td>"
                    f"<td>{_html(m.get('state', ''))}</td>"
                    f"<td>{_html(m.get('error', ''))}</td></tr>"
                )
            html_parts.append("</table>")

        html_parts.append('<p><a href="/">← Back to Dashboard</a></p></body></html>')
        return HTMLResponse(content="\n".join(html_parts))

    @app.get("/api/modules", include_in_schema=False)
    async def api_modules() -> JSONResponse:
        result = adapter.get_modules_dashboard()
        data = _result_data(result, {})
        return _ok_json(data)

    @app.get("/api/rop/dashboard", include_in_schema=False)
    async def api_rop_dashboard(request: Request) -> JSONResponse:
        run_id = request.query_params.get("run_id")
        result = adapter.get_rop_dashboard(run_id=run_id)
        if isinstance(result, AdapterErrorResult):
            code = result.error.get("code", "error")
            status = 404 if code == "not_found" else 400
            return _error_json(code, status_code=status, error=result.error)

        data = _result_data(result, {})
        return _ok_json(data)

    @app.get(
        "/runs/{run_id}/artifacts",
        response_class=JSONResponse,
        include_in_schema=False,
    )
    async def run_artifacts(run_id: str) -> JSONResponse:
        try:
            validate_run_id(run_id)
        except Exception:
            return _error_json("invalid_run_id", status_code=400)
        result = adapter.list_artifacts(run_id)
        data = _result_data(result, [])
        return _ok_json(data)

    @app.get(
        "/runs/{run_id}/artifacts/{artifact_id}",
        include_in_schema=False,
    )
    async def run_artifact_content(run_id: str, artifact_id: str) -> JSONResponse:
        try:
            validate_run_id(run_id)
        except Exception:
            return _error_json("invalid_run_id", status_code=400)
        result = adapter.read_artifact(run_id, artifact_id)
        if isinstance(result, AdapterErrorResult):
            code = result.error.get("code", "error")
            status = 404 if code == "not_found" else 400
            return _error_json(code, status_code=status, error=result.error)
        data = _result_data(result, {})
        return _ok_json(data)

    @app.get(
        "/api/runs/{run_id}/artifacts",
        include_in_schema=False,
    )
    async def api_run_artifacts(run_id: str) -> JSONResponse:
        try:
            validate_run_id(run_id)
        except Exception:
            return _error_json("invalid_run_id", status_code=400)
        result = adapter.list_artifacts(run_id)
        data = _result_data(result, [])
        return _ok_json(data)

    @app.get(
        "/api/runs/{run_id}/artifacts/{artifact_id}",
        include_in_schema=False,
    )
    async def api_run_artifact_content(run_id: str, artifact_id: str) -> JSONResponse:
        try:
            validate_run_id(run_id)
        except Exception:
            return _error_json("invalid_run_id", status_code=400)
        result = adapter.read_artifact(run_id, artifact_id)
        if isinstance(result, AdapterErrorResult):
            code = result.error.get("code", "error")
            status = 404 if code == "not_found" else 400
            return _error_json(code, status_code=status, error=result.error)
        data = _result_data(result, {})
        return _ok_json(data)

    logger.info("BeeAgent custom routes registered: /health, /rop, /modules, /api/*")


# Удаление маршрутов BeeUI
def _prune_beeui_routes(app: FastAPI) -> None:
    allowed_paths = {
        "/",
        "/api/dashboard",
        "/api/runs",
        "/api/runs/{run_id}",
        "/runs",
        "/runs/{run_id}",
        "/static",
    }
    pruned_routes = []
    for route in app.router.routes:
        if not isinstance(route, APIRoute):
            pruned_routes.append(route)
            continue

        if "POST" in route.methods:
            continue
        if route.path.startswith("/auth/"):
            continue
        if route.path.startswith("/components"):
            continue
        if route.path.startswith("/venues/") or route.path.startswith("/api/venues/"):
            continue
        if route.path in {"/health", "/rop", "/modules"}:
            continue
        if route.path not in allowed_paths and route.path.startswith("/api/"):
            continue

        pruned_routes.append(route)

    app.router.routes = pruned_routes
