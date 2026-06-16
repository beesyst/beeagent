from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from beeui_module.adapters.envelopes import (
    AdapterErrorResult,
    AdapterResult,
)
from beeui_module.adapters.ids import validate_run_id
from beeui_module.web.app import create_beeui_app
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

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
            "browser_artifact": True,
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





# Создание FastAPI-приложения BeeUI для BeeAgent
def build_beeui_app(
    settings: dict[str, Any],
    logger: logging.Logger,
    storage_dir: Path | None = None,
) -> FastAPI:
    from beeagent_module.core.paths import get_project_root, get_storage_dir as _get_storage_dir

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

    app.state.beeagent_logger = logger
    app.state.beeagent_settings = settings
    app.state.beeagent_storage_dir = resolved_storage
    app.state.beeagent_adapter = adapter

    _register_custom_routes(app, adapter, logger)

    return app


# Регистрация BeeAgent-specific API маршрутов
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

    logger.info("BeeAgent custom routes registered: /health, /api/modules, /api/rop/dashboard")
