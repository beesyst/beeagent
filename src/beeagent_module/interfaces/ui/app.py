from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from beeui_module.adapters.envelopes import (
    AdapterErrorResult,
    AdapterResult,
)
from beeui_module.web.app import create_beeui_app
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.routing import Route

from beeagent_module.interfaces.ui.adapter import BeeAgentUiAdapter


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

    app = create_beeui_app(
        settings=beeui_settings,
        product_id="beeagent",
        product_title="BeeAgent",
        adapter=adapter,
        config_path=str(config_path),
    )
    _register_apexcharts_compat(app)
    _register_rop_html_polish(app)

    app.state.beeagent_logger = logger
    app.state.beeagent_settings = settings
    app.state.beeagent_storage_dir = resolved_storage
    app.state.beeagent_adapter = adapter

    _register_custom_routes(app, adapter, logger)

    return app


def _register_rop_html_polish(app: FastAPI) -> None:
    @app.middleware("http")
    async def rop_html_polish(request: Request, call_next):
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if request.url.path != "/rop" or "text/html" not in content_type:
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        html = body.decode("utf-8")
        html = _replace_period_buttons_with_dropdown(html)
        html = _replace_rop_chart_ids(html)
        html = _polish_rop_overview_cards(html)
        headers = dict(response.headers)
        headers.pop("content-length", None)
        return Response(
            content=html,
            status_code=response.status_code,
            headers=headers,
            media_type="text/html",
        )


_PERIOD_BUTTON_RE = re.compile(
    r'\s*<a href="(?P<href>/rop\?tab=[^"]+?&amp;period=(?P<period>[^"]+))" '
    r'class="btn btn-outline-primary btn-sm me-1">'
    r"(?P<label>Today|Yesterday|Last 7 days|Last 30 days|Last 3 months|Last year|All time)"
    r"(?P<current> \(current\))?</a>"
)

_ROP_CHART_IDS: dict[str, str] = {
    "Email Workload": "chart-rop-email-workload",
    "Action Required": "chart-rop-action-required",
    "Email intake trend": "chart-rop-email-intake",
    "Lead outcome mix": "chart-rop-outcome-mix",
    "Bitrix reconciliation": "chart-rop-bitrix",
    "Source contribution": "chart-rop-source-contribution",
}


def _replace_period_buttons_with_dropdown(html: str) -> str:
    matches = list(_PERIOD_BUTTON_RE.finditer(html))
    if not matches:
        return html

    active_label = "Select period"
    items: list[str] = []
    for match in matches:
        label = match.group("label")
        href = match.group("href")
        is_active = bool(match.group("current"))
        if is_active:
            active_label = label
        active_class = " active" if is_active else ""
        aria_current = ' aria-current="true"' if is_active else ""
        items.append(
            f'<a class="dropdown-item{active_class}" href="{href}"{aria_current}>'
            f"{label}</a>"
        )

    dropdown = (
        '<div class="dropdown me-1 d-inline-block">'
        '<button class="btn btn-outline-primary btn-sm dropdown-toggle" '
        'type="button" data-bs-toggle="dropdown" aria-expanded="false">'
        f"{active_label}</button>"
        '<div class="dropdown-menu dropdown-menu-end">'
        + "".join(items)
        + "</div></div>"
    )
    return html[: matches[0].start()] + dropdown + html[matches[-1].end() :]


def _replace_rop_chart_ids(html: str) -> str:
    result = html
    for title, chart_id in _ROP_CHART_IDS.items():
        pattern = re.compile(
            r'(<h3 class="card-title mb-0">'
            + re.escape(title)
            + r"</h3>.*?id=\")(?P<old>beeui-chart-[^\"]+)(\")",
            re.DOTALL,
        )
        match = pattern.search(result)
        if not match:
            continue
        old_id = match.group("old")
        result = result.replace(old_id, chart_id)
    return result


_ROP_HERO_METRIC_RE = re.compile(
    r'(<div class="datagrid-title">(?P<label>TODAY&#39;S EMAILS|NEW LEADS)</div>\s*'
    r'<div class="datagrid-content">(?P<value>.*?)</div>)',
    re.DOTALL,
)


def _polish_rop_overview_cards(html: str) -> str:
    def metric_repl(match: re.Match[str]) -> str:
        label = match.group("label")
        value_text = re.sub(r"<.*?>", "", match.group("value"))
        try:
            value = max(0, int(value_text.strip()))
        except ValueError:
            value = 0
        width = min(100, max(8 if value else 0, value * 20))
        tone = "bg-primary" if label == "TODAY&#39;S EMAILS" else "bg-success"
        return (
            match.group(1)
            + '<div class="progress progress-sm mt-2">'
            + f'<div class="progress-bar {tone}" style="width: {width}%"></div>'
            + "</div>"
        )

    result = _ROP_HERO_METRIC_RE.sub(metric_repl, html)
    result = result.replace("Chart render error", "No chart data for this period")
    for title in ("Urgent leads", "Needs review", "Bitrix gaps", "Data quality"):
        title_html = f'<h3 class="card-title mb-0">{title}</h3>'
        title_index = result.find(title_html)
        if title_index < 0:
            continue
        card_index = result.rfind('<div class="card">', 0, title_index)
        if card_index < 0:
            continue
        result = (
            result[:card_index]
            + '<div class="card card-sm">'
            + result[card_index + len('<div class="card">') :]
        )
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
        result = adapter.get_rop_dashboard(run_id=run_id, period=period)
        if isinstance(result, AdapterErrorResult):
            code = result.error.get("code", "error")
            status = 404 if code == "not_found" else 400
            return _error_json(code, status_code=status, error=result.error)

        data = _result_data(result, {})
        return _ok_json(data)

    logger.info(
        "BeeAgent custom routes registered: /health, /api/modules, /api/rop/dashboard"
    )
