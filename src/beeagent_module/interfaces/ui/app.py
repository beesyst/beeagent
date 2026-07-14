from __future__ import annotations

import json as json_mod
import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from beeui_module.adapters.envelopes import (
    AdapterErrorResult,
    AdapterResult,
)
from beeui_module.pages.config import load_beeui_config
from beeui_module.pages.detail import render_beeui_detail_page
from beeui_module.web.app import create_beeui_app
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.routing import Route

from beeagent_module.core.rop_final_decision import (
    find_final_decision,
    load_or_build_final_decisions,
)
from beeagent_module.interfaces.ui.adapter import BeeAgentUiAdapter
from beeagent_module.interfaces.ui.read_model import (
    resolve_recommendation_execution_policy,
)
from beeagent_module.interfaces.ui.locale import (
    reset_current_locale,
    resolve_locale,
    set_current_locale,
    t,
)
from beeagent_module.interfaces.ui.rop_event_detail import (
    build_rop_event_detail_read_model,
)


def _result_data(
    result: AdapterResult | AdapterErrorResult,
    default: Any,
) -> Any:
    if isinstance(result, AdapterErrorResult):
        return default
    return result.data


def _extract_filter_params_from_query(
    query_params: Any,
) -> dict[str, str]:
    """Extract queue filter parameters from query string.

    Shared helper for API routes that need to pass filter params
    to the adapter.
    """
    allowed_filter_keys = frozenset({
        "date_from",
        "date_to",
        "q",
        "sender",
        "subject",
        "case_type",
        "classification",
        "priority",
        "bitrix_status",
        "is_fallback",
        "queue",
        "columns",
        "columns_open",
        "open_dropdowns",
    })
    params: dict[str, str] = {}
    for key in allowed_filter_keys:
        raw = query_params.get(key)
        if raw is not None and isinstance(raw, str) and raw.strip():
            params[key] = raw.strip()
    # Map legacy key
    if "classification" in params and "case_type" not in params:
        params["case_type"] = params.pop("classification")
    return params


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


def build_beeui_settings(agent_settings: dict[str, Any]) -> dict[str, Any]:
    web_cfg = agent_settings.get("web", {})
    log_cfg = agent_settings.get("logging", {})
    web_auth = web_cfg.get("auth", {})
    auth_enabled = bool(web_auth.get("enabled", False))

    beeui_auth: dict[str, Any] = {"enabled": auth_enabled}

    if auth_enabled:
        session_env = web_auth["session_secret_env"]
        app_env = str(agent_settings.get("app", {}).get("env", "dev")).strip().lower()
        beeui_auth["session_secret"] = os.environ.get(session_env, "")
        beeui_auth["cookie_secure"] = app_env not in {"dev", "test", "local"}

        principals = web_auth.get("principals", [])
        resolved_principals = []
        first_token = ""
        first_admin_token = ""
        first_operator_token = ""

        for principal in principals:
            role = str(principal.get("role", "")).strip()
            token = os.environ.get(principal["token_env"], "")
            if not first_token:
                first_token = token
            if role == "admin" and not first_admin_token:
                first_admin_token = token
            if role == "operator" and not first_operator_token:
                first_operator_token = token

            resolved_principals.append(
                {
                    "id": principal.get("id", ""),
                    "username": principal.get("username", ""),
                    "role": role,
                    "token": token,
                }
            )

        if first_token:
            beeui_auth["admin_token"] = first_admin_token or first_token
            beeui_auth["operator_token"] = first_operator_token or first_token
        beeui_auth["principals"] = resolved_principals

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
        "auth": beeui_auth,
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


def build_beeui_app(
    settings: dict[str, Any],
    logger: logging.Logger,
    storage_dir: Path | None = None,
) -> FastAPI:
    from beeagent_module.core.paths import get_project_root
    from beeagent_module.core.paths import get_storage_dir as _get_storage_dir

    resolved_storage = storage_dir or _get_storage_dir()
    beeui_settings = build_beeui_settings(settings)

    adapter = BeeAgentUiAdapter(
        storage_dir=resolved_storage,
        settings=settings,
    )

    config_path = get_project_root() / "config" / "beeui.yml"
    from beeui_module.web import app as beeui_web_app

    resolved_ui_config = load_beeui_config(config_path)
    resolved_templates = Jinja2Templates(
        directory=str(Path(beeui_web_app.__file__).resolve().parent / "templates")
    )
    resolved_templates.env.autoescape = bool(
        beeui_settings["security"]["html_autoescape"]
    )

    app = create_beeui_app(
        settings=beeui_settings,
        ui_config=resolved_ui_config,
        product_id="beeagent",
        product_title="BeeAgent",
        adapter=adapter,
    )
    _register_apexcharts_compat(app)
    _register_rop_html_polish(app)

    app.state.beeagent_logger = logger
    app.state.beeagent_settings = settings
    app.state.beeagent_storage_dir = resolved_storage
    app.state.beeagent_adapter = adapter
    app.state.beeagent_beeui_templates = resolved_templates
    app.state.beeagent_beeui_ui_config = resolved_ui_config
    app.state.beeagent_beeui_route_prefix = beeui_settings["web"]["route_prefix"]

    _setup_beeagent_auth(app, beeui_settings, logger)
    _register_custom_routes(app, adapter, logger)

    return app


def _setup_beeagent_auth(
    app: FastAPI,
    beeui_settings: dict[str, Any],
    logger: logging.Logger,
) -> None:
    auth_cfg = beeui_settings.get("auth", {})
    enabled = bool(auth_cfg.get("enabled", False))

    if not enabled:
        logger.info("Auth is disabled (web.auth.enabled=false)")
        return

    from beeui_module.auth.models import UserRole
    from beeui_module.auth.service import AuthService

    principal_configs: list[dict[str, Any]] = auth_cfg.get("principals", [])
    original_service: AuthService | None = getattr(
        app.state, "beeui_auth_service", None
    )

    if original_service is None:
        raise RuntimeError("BeeUI auth service is required when web.auth.enabled=true")

    if not original_service.enabled:
        raise RuntimeError(
            "BeeUI auth service must be enabled when web.auth.enabled=true"
        )

    session_secret = str(auth_cfg.get("session_secret", ""))
    if not session_secret:
        raise RuntimeError(
            "Non-empty session secret is required when web.auth.enabled=true"
        )

    if not principal_configs:
        raise RuntimeError(
            "Non-empty principals are required when web.auth.enabled=true"
        )

    token_roles: list[tuple[str, UserRole]] = []
    for principal in principal_configs:
        token = str(principal.get("token", ""))
        role_name = str(principal.get("role", "")).strip()
        if not token:
            raise RuntimeError(
                "Non-empty principal tokens are required when web.auth.enabled=true"
            )

        try:
            role = getattr(UserRole, role_name)
        except AttributeError as exc:
            raise RuntimeError(f"Unsupported BeeUI auth role '{role_name}'") from exc

        token_roles.append((token, role))

    class _BeeAgentAuthService(AuthService):
        def _resolve_role(self, token: str) -> UserRole | None:
            import hmac

            for candidate_token, candidate_role in token_roles:
                if hmac.compare_digest(token, candidate_token):
                    return candidate_role
            return None

    primary_token = token_roles[0][0]
    auth_settings = {
        "enabled": True,
        "session_secret": session_secret,
        "admin_token": auth_cfg.get("admin_token") or primary_token,
        "operator_token": auth_cfg.get("operator_token") or primary_token,
        "cookie_secure": bool(auth_cfg.get("cookie_secure", False)),
    }
    app.state.beeui_auth_service = _BeeAgentAuthService(auth_settings)
    logger.info("Auth enabled with %d principal(s)", len(token_roles))

    _register_auth_middleware(app, logger)


_PROTECTED_HTML_PATHS: list[re.Pattern[str]] = [
    re.compile(r"^/$"),
    re.compile(r"^/rop$"),
    re.compile(r"^/rop\?.*"),
    re.compile(r"^/rop/events/"),
    re.compile(r"^/runs$"),
    re.compile(r"^/runs/"),
    re.compile(r"^/modules$"),
]
_PUBLIC_PATHS: list[re.Pattern[str]] = [
    re.compile(r"^/health"),
    re.compile(r"^/static/"),
    re.compile(r"^/auth/"),
    re.compile(r"^/api/bitrix/rop/widget(?:/|$)"),
]


def _is_path_protected(path: str) -> bool:
    for pattern in _PUBLIC_PATHS:
        if pattern.match(path):
            return False
    if path == "/api" or path.startswith("/api/"):
        return True
    for pattern in _PROTECTED_HTML_PATHS:
        if pattern.match(path):
            return True
    return False


def _register_auth_middleware(app: FastAPI, logger: logging.Logger) -> None:
    logger.info("Registering auth middleware for protected routes")

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        if not _is_path_protected(str(request.url.path)):
            return await call_next(request)

        from beeui_module.auth.service import AuthService

        service: AuthService | None = getattr(
            request.app.state, "beeui_auth_service", None
        )
        if service is None or not service.enabled:
            logger.error("BeeUI auth service unavailable for protected route")
            return JSONResponse(
                {
                    "ok": False,
                    "read_only": True,
                    "error": {
                        "code": "auth_unavailable",
                        "message": "Authentication service unavailable",
                    },
                    "warnings": [],
                    "meta": {},
                },
                status_code=503,
            )

        cookie_name = service.cookie_name()
        cookie = request.cookies.get(cookie_name)
        session = service.verify_session(cookie)

        if session is not None:
            return await call_next(request)

        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            from starlette.responses import RedirectResponse

            return RedirectResponse(url="/auth/login", status_code=302)

        return JSONResponse(
            {
                "ok": False,
                "read_only": True,
                "error": {
                    "code": "unauthenticated",
                    "message": "Authentication required",
                },
                "warnings": [],
                "meta": {},
            },
            status_code=401,
        )


def _register_rop_html_polish(app: FastAPI) -> None:
    @app.middleware("http")
    async def rop_html_polish(request: Request, call_next):
        locale = resolve_locale(request.query_params.get("lang"))
        token = set_current_locale(locale)
        try:
            response = await call_next(request)
        finally:
            reset_current_locale(token)

        content_type = response.headers.get("content-type", "")
        path = request.url.path
        # /rop is rendered by BeeUI adapter — no localization pass needed
        if path == "/rop":
            return response

        needs_polish = locale == "ru" and path in {"/", "/runs"}
        if not needs_polish or "text/html" not in content_type:
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        html = body.decode("utf-8")
        html = _localize_product_console_html(html, path, locale)
        headers = dict(response.headers)
        headers.pop("content-length", None)
        return Response(
            content=html,
            status_code=response.status_code,
            headers=headers,
            media_type="text/html",
        )


def _localize_product_console_html(
    html: str,
    path: str,
    locale: str,
) -> str:
    if locale != "ru":
        return html

    replacements: dict[str, list[tuple[str, str]]] = {
        "/": [
            ("<title>Dashboard · ", f"<title>{t('BeeAgent Dashboard', locale)} · "),
            (
                '<h2 class="page-title">Dashboard</h2>',
                f'<h2 class="page-title">{t("BeeAgent Dashboard", locale)}</h2>',
            ),
            (
                '<div class="text-secondary mt-1">Adapter-backed product overview</div>',
                (
                    '<div class="text-secondary mt-1">'
                    f"{t('Read-only operator dashboard', locale)}</div>"
                ),
            ),
            (
                '<h3 class="card-title">Latest run</h3>',
                f'<h3 class="card-title">{t("Latest run", locale)}</h3>',
            ),
            (
                '<h3 class="card-title">KPIs</h3>',
                f'<h3 class="card-title">{t("KPIs", locale)}</h3>',
            ),
            (
                '<h3 class="card-title">Summary</h3>',
                f'<h3 class="card-title">{t("Summary", locale)}</h3>',
            ),
            ("Open run", t("Open run", locale)),
            ("Technical details", t("Technical details", locale)),
        ],
        "/runs": [
            ("<title>Runs · ", f"<title>{t('Runs', locale)} · "),
            (
                '<h2 class="page-title">Runs</h2>',
                f'<h2 class="page-title">{t("Runs", locale)}</h2>',
            ),
            (
                '<div class="text-secondary mt-1">Adapter-backed run list</div>',
                f'<div class="text-secondary mt-1">{t("Run history", locale)}</div>',
            ),
            (
                '<h3 class="card-title">Run list</h3>',
                f'<h3 class="card-title">{t("Run list", locale)}</h3>',
            ),
            ("<th>Run ID</th>", f"<th>{t('Run ID', locale)}</th>"),
            ("<th>Status</th>", f"<th>{t('Status', locale)}</th>"),
            ("<th>Started</th>", f"<th>{t('Started', locale)}</th>"),
            ("<th>Completed</th>", f"<th>{t('Completed', locale)}</th>"),
            (">Open</a>", f">{t('Open', locale)}</a>"),
        ],
    }

    result = html
    for old, new in replacements.get(path, []):
        result = result.replace(old, new)
    return result


def _register_apexcharts_compat(app: FastAPI) -> None:
    async def apexcharts_compat(_: Request) -> Response:
        script = """
(function () {
  'use strict';
  function safeText(value) {
    return String(value == null ? '' : value);
  }
  window.ApexCharts = function (el, config) {
    this.el = el;
    this.config = config || {};
  };
  window.ApexCharts.prototype.render = function () {
    var config = this.config || {};
    var chart = config.chart || {};
    var type = chart.type || 'line';
    var series = Array.isArray(config.series) ? config.series : [];
    var labels = Array.isArray(config.labels) ? config.labels : [];
    var categories = config.xaxis && Array.isArray(config.xaxis.categories)
      ? config.xaxis.categories
      : labels;
    var wrap = document.createElement('div');
    wrap.className = 'beeui-apex-compat';
    wrap.style.minHeight = '220px';
    wrap.style.display = 'flex';
    wrap.style.flexDirection = 'column';
    wrap.style.justifyContent = 'center';
    wrap.style.gap = '0.5rem';
    if (type === 'donut') {
      series.forEach(function (value, index) {
        var row = document.createElement('div');
        row.className = 'd-flex justify-content-between border-bottom py-1';
        var label = document.createElement('span');
        label.className = 'text-secondary';
        label.textContent = safeText(labels[index] || ('Segment ' + (index + 1)));
        var number = document.createElement('strong');
        number.textContent = safeText(value);
        row.appendChild(label);
        row.appendChild(number);
        wrap.appendChild(row);
      });
    } else {
      var points = series.length && Array.isArray(series[0].data) ? series[0].data : [];
      points.forEach(function (value, index) {
        var row = document.createElement('div');
        row.className = 'd-flex align-items-center gap-2';
        var label = document.createElement('span');
        label.className = 'text-secondary small';
        label.style.width = '6rem';
        label.textContent = safeText(categories[index] || (index + 1));
        var barWrap = document.createElement('div');
        barWrap.className = 'progress flex-fill';
        var bar = document.createElement('div');
        bar.className = 'progress-bar';
        bar.style.width = Math.max(4, Math.min(100, Number(value) || 0)) + '%';
        barWrap.appendChild(bar);
        var number = document.createElement('strong');
        number.style.width = '3rem';
        number.textContent = safeText(value);
        row.appendChild(label);
        row.appendChild(barWrap);
        row.appendChild(number);
        wrap.appendChild(row);
      });
    }
    this.el.innerHTML = '';
    this.el.appendChild(wrap);
    return Promise.resolve();
  };
}());
"""
        return Response(script, media_type="application/javascript")

    route = Route(
        "/static/vendor/apexcharts/apexcharts.min.js",
        endpoint=apexcharts_compat,
        methods=["GET"],
    )
    app.router.routes.insert(0, route)


_PATH_TRAVERSAL_RE = re.compile(r"(?:^|/)\.\.(?:/|$)")


def _is_path_traversal(value: str) -> bool:
    return bool(_PATH_TRAVERSAL_RE.search(value))


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
        period = request.query_params.get("period")
        filter_params = _extract_filter_params_from_query(request.query_params)

        try:
            page = max(1, int(request.query_params.get("page", "1")))
        except (ValueError, TypeError):
            page = 1
        try:
            page_size = int(request.query_params.get("page_size", "25"))
            if page_size not in (25, 50, 100):
                page_size = 25
        except (ValueError, TypeError):
            page_size = 25
        sort = request.query_params.get("sort", "received_at")
        order = request.query_params.get("order", "desc")

        result = adapter.get_rop_dashboard(
            run_id=run_id,
            period=period,
            filter_params=filter_params,
            page=page,
            page_size=page_size,
            sort=sort,
            order=order,
        )
        if isinstance(result, AdapterErrorResult):
            code = result.error.get("code", "error")
            status = 404 if code == "not_found" else 400
            return _error_json(code, status_code=status, error=result.error)

        data = _result_data(result, {})
        return _ok_json(data)

    @app.get("/api/rop/events/{event_id}", include_in_schema=False)
    async def api_rop_event_detail(request: Request, event_id: str) -> JSONResponse:
        run_id = request.query_params.get("run_id")
        if not run_id:
            return _error_json(
                "missing_run_id",
                "run_id query parameter is required",
                status_code=400,
            )
        try:
            from beeui_module.adapters.ids import validate_run_id

            validate_run_id(run_id)
        except Exception:
            return _error_json(
                "invalid_run_id",
                "Invalid run_id",
                status_code=400,
            )

        if _is_path_traversal(event_id):
            return _error_json(
                "invalid_event_id",
                "Invalid event_id",
                status_code=400,
            )

        result = build_rop_event_detail_read_model(
            storage_dir=app.state.beeagent_storage_dir,
            run_id=run_id,
            event_id=event_id,
            lang=resolve_locale(request.query_params.get("lang")),
        )
        if not result.get("ok", True) and result.get("error") == "not_found":
            return _error_json(
                "not_found",
                f"Event {event_id} not found in run {run_id}",
                status_code=404,
            )

        warnings_result = result.get("warnings", [])
        return _ok_json(result, warnings=warnings_result)

    @app.get("/rop/events/{event_id}", include_in_schema=False)
    async def rop_event_detail_html(request: Request, event_id: str) -> Response:
        run_id = request.query_params.get("run_id")
        if not run_id:
            return _error_json(
                "missing_run_id",
                "run_id query parameter is required",
                status_code=400,
            )
        try:
            from beeui_module.adapters.ids import validate_run_id

            validate_run_id(run_id)
        except Exception:
            return _error_json(
                "invalid_run_id",
                "Invalid run_id",
                status_code=400,
            )

        if _is_path_traversal(event_id):
            return _error_json(
                "invalid_event_id",
                "Invalid event_id",
                status_code=400,
            )

        locale = resolve_locale(request.query_params.get("lang"))
        token = set_current_locale(locale)
        try:
            query_params = {"run_id": run_id, "event_id": event_id}
            if locale != "en":
                query_params["lang"] = locale

            page_result = adapter.get_page("rop_event_detail", query_params)
            if isinstance(page_result, AdapterErrorResult):
                code = str(page_result.error.get("code", "page_error"))
                status_code = 404 if code == "not_found" else 500
                message = (
                    f"Event {event_id} not found in run {run_id}"
                    if code == "not_found"
                    else str(
                        page_result.error.get(
                            "message", "Failed to build event detail page"
                        )
                    )
                )
                return _error_json(
                    code,
                    message,
                    status_code=status_code,
                    error=page_result.error,
                )

            return render_beeui_detail_page(
                request,
                page_result.data,
                templates=app.state.beeagent_beeui_templates,
                route_prefix=app.state.beeagent_beeui_route_prefix,
                ui_config=app.state.beeagent_beeui_ui_config,
                product_title=app.state.beeui_product["title"],
                product_id=app.state.beeui_product["id"],
            )
        finally:
            reset_current_locale(token)

    _register_bitrix_widget_routes(app, adapter, logger)

    logger.info(
        "BeeAgent custom routes registered: "
        "/health, /api/modules, /api/rop/dashboard, "
        "/api/rop/events/{event_id}, /rop/events/{event_id}, "
        "/api/bitrix/rop/widget, /api/bitrix/rop/widget/events, "
        "/api/bitrix/rop/widget/events/{event_id}"
    )


def _register_bitrix_widget_routes(
    app: FastAPI,
    adapter: BeeAgentUiAdapter,
    logger: logging.Logger,
) -> None:
    def serialize_final_decision(item: dict[str, Any]) -> dict[str, Any]:
        final_case_subtype = item.get("final_case_subtype")
        attention_reason = item.get("attention_reason")
        return {
            "event_id": str(item.get("event_id", "")),
            "final_case_type": str(item.get("final_case_type", "")),
            "final_case_subtype": (
                final_case_subtype if isinstance(final_case_subtype, str) else None
            ),
            "final_queue": str(item.get("final_queue", "")),
            "final_action": str(item.get("final_action", "")),
            "final_decision_source": str(item.get("final_decision_source", "")),
            "final_confidence": item.get("final_confidence"),
            "needs_attention": bool(item.get("needs_attention", False)),
            "attention_reason": (
                attention_reason if isinstance(attention_reason, str) else None
            ),
            "automation_allowed": False,
            "bitrix_write_allowed": False,
        }

    def serialize_final_decisions_payload(
        payload: dict[str, Any],
        max_items: int,
    ) -> dict[str, Any]:
        events = payload.get("events", [])
        if not isinstance(events, list):
            events = []
        serialized_events = [
            serialize_final_decision(event)
            for event in events
            if isinstance(event, dict)
        ][:max_items]
        source_counts: dict[str, int] = {}
        attention_count = 0
        for event in serialized_events:
            source = event["final_decision_source"]
            source_counts[source] = source_counts.get(source, 0) + 1
            if event["needs_attention"]:
                attention_count += 1
        return {
            "summary": {
                "total_events": len(serialized_events),
                "decision_source_counts": source_counts,
                "attention_count": attention_count,
            },
            "events": serialized_events,
        }

    def empty_final_decisions() -> dict[str, Any]:
        return {
            "summary": {
                "total_events": 0,
                "decision_source_counts": {},
                "attention_count": 0,
            },
            "events": [],
        }

    @app.get("/api/bitrix/rop/widget", include_in_schema=False)
    async def bitrix_rop_widget(request: Request) -> JSONResponse:
        settings = getattr(app.state, "beeagent_settings", {})
        widget_cfg = settings.get("bitrix", {}).get("widget", {})
        widget_enabled = (
            widget_cfg.get("enabled", False) if isinstance(widget_cfg, dict) else False
        )

        if not widget_enabled:
            return _ok_json(
                {
                    "summary": {
                        "high_priority": 0,
                        "needs_review": 0,
                        "lost_in_bitrix": 0,
                        "ambiguous": 0,
                        "ai_assisted": 0,
                    },
                    "items": [],
                    "final_decisions": empty_final_decisions(),
                },
                meta={
                    "widget_disabled": True,
                    "message": "Bitrix widget API is disabled in config",
                },
            )

        token_env = widget_cfg.get("token_env", "BITRIX_ROP_WIDGET_TOKEN")
        expected_token = os.environ.get(token_env, "")
        if not expected_token:
            return _error_json(
                "widget_config_error",
                "Widget token env not configured",
                status_code=503,
            )

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return _error_json(
                "unauthorized",
                "Missing or invalid Authorization header",
                status_code=401,
            )

        import hmac

        provided_token = auth_header[7:]
        if not hmac.compare_digest(provided_token, expected_token):
            return _error_json(
                "unauthorized",
                "Invalid widget token",
                status_code=401,
            )

        storage_dir = getattr(app.state, "beeagent_storage_dir", None)
        if storage_dir is None:
            return _error_json("server_error", "Storage unavailable", status_code=503)

        run_id = request.query_params.get("run_id")
        if not run_id:
            runs_dir = storage_dir / "runs"
            if runs_dir.is_dir():
                run_dirs = sorted(
                    (d for d in runs_dir.iterdir() if d.is_dir()),
                    key=lambda d: d.stat().st_mtime,
                    reverse=True,
                )
                if run_dirs:
                    run_id = run_dirs[0].name

        if not run_id:
            return _ok_json(
                {
                    "summary": {
                        "high_priority": 0,
                        "needs_review": 0,
                        "lost_in_bitrix": 0,
                        "ambiguous": 0,
                        "ai_assisted": 0,
                    },
                    "items": [],
                    "final_decisions": empty_final_decisions(),
                },
                warnings=[{"code": "no_runs", "message": "No runs available"}],
            )

        try:
            from beeui_module.adapters.ids import validate_run_id

            validate_run_id(run_id)
        except Exception:
            return _error_json("invalid_run_id", "Invalid run_id", status_code=400)

        max_items = widget_cfg.get("max_items", 50)

        rec_path = storage_dir / "runs" / run_id / "rop_recommendations.json"

        run_dir = storage_dir / "runs" / run_id
        if run_dir.is_dir():
            final_decisions, _ = load_or_build_final_decisions(run_dir)
            final_decisions_payload = serialize_final_decisions_payload(
                final_decisions,
                max_items,
            )
        else:
            final_decisions_payload = empty_final_decisions()

        if not rec_path.exists():
            payload = {
                "summary": {
                    "high_priority": 0,
                    "needs_review": 0,
                    "lost_in_bitrix": 0,
                    "ambiguous": 0,
                    "ai_assisted": 0,
                },
                "items": [],
            }
            payload["final_decisions"] = final_decisions_payload
            return _ok_json(
                payload,
                warnings=[
                    {
                        "code": "no_recommendations",
                        "message": f"No recommendations for run {run_id}",
                    }
                ],
            )

        try:
            rec_data = json_mod.loads(rec_path.read_text(encoding="utf-8"))
        except json_mod.JSONDecodeError, OSError:
            return _error_json(
                "malformed_artifact",
                "Failed to read recommendations artifact",
                status_code=500,
            )

        if not isinstance(rec_data, dict):
            return _error_json(
                "malformed_artifact",
                "Invalid recommendations artifact format",
                status_code=500,
            )

        items_raw = rec_data.get("items", [])
        if not isinstance(items_raw, list):
            items_raw = []

        serializable_items: list[dict[str, Any]] = []
        summary = {
            "high_priority": 0,
            "needs_review": 0,
            "lost_in_bitrix": 0,
            "ambiguous": 0,
            "ai_assisted": 0,
        }

        for item in items_raw[:max_items]:
            recommended_action = str(item.get("recommended_action", ""))
            (
                safe_to_execute,
                requires_human_confirmation,
            ) = resolve_recommendation_execution_policy(recommended_action)
            priority = str(item.get("priority", "medium"))
            if priority == "high":
                summary["high_priority"] += 1
            if requires_human_confirmation:
                summary["needs_review"] += 1
            if item.get("bitrix_status") == "not_found":
                summary["lost_in_bitrix"] += 1
            if item.get("bitrix_status") == "ambiguous":
                summary["ambiguous"] += 1
            if item.get("ai_used"):
                summary["ai_assisted"] += 1

            event_id = str(item.get("event_id", ""))
            evidence_links = item.get("evidence_links", [])
            if not isinstance(evidence_links, list):
                evidence_links = []

            safe_item = {
                "event_id": event_id,
                "title": str(item.get("title", "")),
                "priority": str(item.get("priority", "")),
                "sender": str(item.get("sender", "")),
                "subject": str(item.get("subject", "")),
                "summary": str(item.get("summary", "")),
                "recommended_action": recommended_action,
                "recommended_queue": str(item.get("recommended_queue", "")),
                "target_bitrix_category": str(item.get("target_bitrix_category", "")),
                "bitrix_status": str(item.get("bitrix_status", "")),
                "confidence": float(item.get("confidence", 0.0))
                if isinstance(item.get("confidence"), (int, float))
                else 0.0,
                "ai_used": bool(item.get("ai_used")),
                "reason": str(item.get("reason", "")),
                "safe_to_execute": safe_to_execute,
                "requires_human_confirmation": requires_human_confirmation,
                "evidence_links": [
                    str(link) for link in evidence_links if isinstance(link, str)
                ],
                "detail_url": (
                    f"/api/bitrix/rop/widget/events/{quote(event_id, safe='')}"
                    f"?run_id={quote(run_id, safe='')}"
                ),
            }
            serializable_items.append(safe_item)

        widget_data = {
            "summary": summary,
            "items": serializable_items,
        }

        widget_data["final_decisions"] = final_decisions_payload

        return _ok_json(
            widget_data,
            meta={
                "run_id": run_id,
                "read_only": True,
            },
        )

    @app.get("/api/bitrix/rop/widget/events", include_in_schema=False)
    async def bitrix_rop_widget_events(request: Request) -> JSONResponse:
        return await bitrix_rop_widget(request)

    @app.get("/api/bitrix/rop/widget/events/{event_id}", include_in_schema=False)
    async def bitrix_rop_widget_event_detail(
        request: Request,
        event_id: str,
    ) -> JSONResponse:
        settings = getattr(app.state, "beeagent_settings", {})
        widget_cfg = settings.get("bitrix", {}).get("widget", {})
        widget_enabled = (
            widget_cfg.get("enabled", False) if isinstance(widget_cfg, dict) else False
        )

        if not widget_enabled:
            return _error_json(
                "widget_disabled",
                "Bitrix widget API is disabled in config",
                status_code=503,
            )

        token_env = widget_cfg.get("token_env", "BITRIX_ROP_WIDGET_TOKEN")
        expected_token = os.environ.get(token_env, "")
        if not expected_token:
            return _error_json(
                "widget_config_error",
                "Widget token env not configured",
                status_code=503,
            )

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return _error_json(
                "unauthorized",
                "Missing or invalid Authorization header",
                status_code=401,
            )

        import hmac

        provided_token = auth_header[7:]
        if not hmac.compare_digest(provided_token, expected_token):
            return _error_json(
                "unauthorized",
                "Invalid widget token",
                status_code=401,
            )

        storage_dir = getattr(app.state, "beeagent_storage_dir", None)
        if storage_dir is None:
            return _error_json("server_error", "Storage unavailable", status_code=503)

        run_id = request.query_params.get("run_id")
        if not run_id:
            runs_dir = storage_dir / "runs"
            if runs_dir.is_dir():
                run_dirs = sorted(
                    (d for d in runs_dir.iterdir() if d.is_dir()),
                    key=lambda d: d.stat().st_mtime,
                    reverse=True,
                )
                if run_dirs:
                    run_id = run_dirs[0].name

        if not run_id:
            return _error_json("missing_run_id", "run_id is required", status_code=400)

        try:
            from beeui_module.adapters.ids import validate_run_id

            validate_run_id(run_id)
        except Exception:
            return _error_json("invalid_run_id", "Invalid run_id", status_code=400)

        if _is_path_traversal(event_id):
            return _error_json("invalid_event_id", "Invalid event_id", status_code=400)

        final_decisions, _ = load_or_build_final_decisions(
            storage_dir / "runs" / run_id
        )
        final_decision = find_final_decision(final_decisions, event_id)

        rec_path = storage_dir / "runs" / run_id / "rop_recommendations.json"
        if not rec_path.exists():
            return _error_json(
                "not_found",
                f"No recommendations for run {run_id}",
                status_code=404,
            )

        try:
            rec_data = json_mod.loads(rec_path.read_text(encoding="utf-8"))
        except json_mod.JSONDecodeError, OSError:
            return _error_json(
                "malformed_artifact",
                "Failed to read recommendations artifact",
                status_code=500,
            )

        if not isinstance(rec_data, dict):
            return _error_json(
                "malformed_artifact",
                "Invalid recommendations artifact format",
                status_code=500,
            )

        items_raw = rec_data.get("items", [])
        if not isinstance(items_raw, list):
            items_raw = []

        for item in items_raw:
            if str(item.get("event_id", "")) == event_id:
                evidence_links = item.get("evidence_links", [])
                if not isinstance(evidence_links, list):
                    evidence_links = []

                recommended_action = str(item.get("recommended_action", ""))
                (
                    safe_to_execute,
                    requires_human_confirmation,
                ) = resolve_recommendation_execution_policy(recommended_action)
                safe_item = {
                    "event_id": str(item.get("event_id", "")),
                    "title": str(item.get("title", "")),
                    "summary": str(item.get("summary", "")),
                    "priority": str(item.get("priority", "")),
                    "sender": str(item.get("sender", "")),
                    "subject": str(item.get("subject", "")),
                    "recommended_action": recommended_action,
                    "recommended_queue": str(item.get("recommended_queue", "")),
                    "target_bitrix_category": str(
                        item.get("target_bitrix_category", "")
                    ),
                    "bitrix_status": str(item.get("bitrix_status", "")),
                    "confidence": float(item.get("confidence", 0.0))
                    if isinstance(item.get("confidence"), (int, float))
                    else 0.0,
                    "ai_used": bool(item.get("ai_used")),
                    "reason": str(item.get("reason", "")),
                    "safe_to_execute": safe_to_execute,
                    "requires_human_confirmation": requires_human_confirmation,
                    "evidence_links": [
                        str(link) for link in evidence_links if isinstance(link, str)
                    ],
                }
                return _ok_json(
                    {
                        **safe_item,
                        "final_decision": (
                            serialize_final_decision(final_decision)
                            if final_decision
                            else None
                        ),
                    },
                    meta={
                        "run_id": run_id,
                        "read_only": True,
                    },
                )

        return _error_json(
            "not_found",
            f"Event {event_id} not found in recommendations for run {run_id}",
            status_code=404,
        )

    logger.info("Bitrix widget API routes registered")
