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


# Результат данных
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
        result = adapter.get_rop_dashboard()
        if isinstance(result, AdapterErrorResult):
            return HTMLResponse(
                content="<h1>ROP Dashboard unavailable</h1><p>No runs found.</p>",
                status_code=404,
            )
        data = _result_data(result, {})
        run_id = data.get("run_id", "N/A")
        sources = data.get("sources", [])
        case_type_counts = data.get("case_type_counts", {})
        priority_counts = data.get("priority_counts", {})
        fallback_count = data.get("fallback_count", 0)
        classified_count = data.get("classified_count", 0)

        html_parts = [
            "<!DOCTYPE html><html><head><meta charset='utf-8'>",
            "<title>ROP Dashboard</title>",
            "<style>body{font-family:sans-serif;margin:2em;background:#1a1d23;color:#e5e7eb}a{color:#60a5fa}</style>",
            "</head><body>",
            "<h1>ROP Dashboard</h1>",
            f"<p>Run: <strong>{_html(run_id)}</strong></p>",
            f"<p>Classified events: {_html(classified_count)} | Fallback: {_html(fallback_count)}</p>",
        ]

        if case_type_counts:
            html_parts.append("<h2>Case Types</h2><ul>")
            for ct, count in sorted(case_type_counts.items()):
                html_parts.append(f"<li>{_html(ct)}: {_html(count)}</li>")
            html_parts.append("</ul>")

        if priority_counts:
            html_parts.append("<h2>Priorities</h2><ul>")
            for p, count in sorted(priority_counts.items()):
                html_parts.append(f"<li>{_html(p)}: {_html(count)}</li>")
            html_parts.append("</ul>")

        if sources:
            html_parts.append("<h2>Sources</h2><ul>")
            for s in sources:
                sid = s.get("source_id", "?")
                status = s.get("status", "?")
                display = s.get("display_name", sid)
                html_parts.append(
                    f"<li>{_html(display)} ({_html(sid)}) — {_html(status)}</li>"
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
