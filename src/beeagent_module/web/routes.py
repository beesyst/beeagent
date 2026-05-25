from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from beeagent_module.web.artifacts import (
    MODULE_ARTIFACT_WHITELIST,
    RUN_ARTIFACT_WHITELIST,
    build_rop_dashboard,
    build_run_overview,
    list_runs,
    read_json_file,
    resolve_run_dir,
    safe_read_text,
)
from beeagent_module.web.render import render_template

_DROP = object()


# Результат обработки веб-запроса
@dataclass
class WebResponse:
    status: int
    content_type: str
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)


# Обработка входящего HTTP запроса и маршрутизация его к соответствующим обработчикам
def handle_request(
    method: str,
    raw_path: str,
    storage_dir: Path,
    logger: logging.Logger,
) -> WebResponse:
    if method != "GET":
        return _text_response(405, "Method Not Allowed", "text/plain; charset=utf-8")

    parsed = urlsplit(raw_path)
    path = parsed.path
    query = parse_qs(parsed.query)
    parts = [part for part in path.split("/") if part]

    if path == "/":
        return _html_response(
            200,
            render_template(
                "home.html",
                title="BeeAgent Web",
                runs_count=len(list_runs(storage_dir)),
            ),
        )

    if path == "/runs":
        return _runs_response(storage_dir)

    if path == "/modules":
        return _modules_response(storage_dir)

    if path == "/static/css/web.css":
        return _serve_static_css()

    if len(parts) >= 2 and parts[0] == "runs":
        run_id = parts[1]
        run_dir = resolve_run_dir(storage_dir, run_id)
        if run_dir is None:
            return _html_response(
                400,
                render_template(
                    "error.html",
                    title="Bad run_id",
                    heading="Invalid run_id",
                    message="Run identifier is invalid.",
                ),
            )

        if len(parts) == 2:
            return _run_overview_response(run_id=run_id, run_dir=run_dir)

        if len(parts) == 3 and parts[2] == "rop":
            return _rop_dashboard_response(run_id=run_id, run_dir=run_dir, query=query)

        if len(parts) == 3 and parts[2] == "tsv":
            return _serve_tsv(run_dir=run_dir)

        if len(parts) == 4 and parts[2] == "artifact":
            return _serve_run_artifact(run_dir=run_dir, artifact_name=parts[3])

        if len(parts) == 4 and parts[2] == "module-artifact":
            return _serve_module_artifact(run_dir=run_dir, artifact_name=parts[3])

    logger.info("web route not found: path=%s", path)
    return _html_response(
        404,
        render_template(
            "error.html",
            title="Not Found",
            heading="Route not found",
            message="The requested route does not exist.",
        ),
    )


# Обработка запросов, рендеринг шаблонов и формирования ответов
def _runs_response(storage_dir: Path) -> WebResponse:
    runs = list_runs(storage_dir)
    return _html_response(
        200,
        render_template(
            "runs.html",
            title="Runs",
            runs=runs,
        ),
    )


# Рендеринг страницы обзора выполнения с диагностикой, метаданными и списком артефактов
def _run_overview_response(run_id: str, run_dir: Path) -> WebResponse:
    overview = build_run_overview(run_dir)
    errors = [
        f"{key}:{value}"
        for key, value in overview["errors"].items()
        if value is not None
    ]

    return _html_response(
        200,
        render_template(
            "run_overview.html",
            title=f"Run {run_id}",
            run_id=run_id,
            errors=errors,
            summary=overview["summary"],
            source_diagnostics=overview["source_diagnostics"],
            intake_metadata=overview["intake_metadata"],
            counts={
                "normalized_count": overview["normalized_count"],
                "classified_count": overview["classified_count"],
            },
            available_artifacts=overview["available_artifacts"],
            module_artifacts=overview["module_artifacts"],
            tsv_exists=(run_dir / "rop_review_table.tsv").exists(),
        ),
    )


# Рендеринг ROP дашборда с фильтрацией, метриками и доступом к артефактам для анализа результатов классификации и принятия решений по кейсам
def _rop_dashboard_response(
    run_id: str,
    run_dir: Path,
    query: dict[str, list[str]],
) -> WebResponse:
    dashboard = build_rop_dashboard(
        run_dir=run_dir,
        case_type_filter=_single_query_value(query, "case_type"),
        priority_filter=_single_query_value(query, "priority"),
        fallback_filter=_single_query_value(query, "fallback"),
        reason_code_filter=_single_query_value(query, "reason_code"),
    )

    return _html_response(
        200,
        render_template(
            "rop_dashboard.html",
            title=f"ROP {run_id}",
            run_id=run_id,
            errors=dashboard["errors"],
            source=dashboard["source"],
            classification=dashboard["classification"],
            metrics={
                "total_rows": dashboard["total_rows"],
                "shown_rows": dashboard["shown_rows"],
                "fallback_count": dashboard["fallback_count"],
            },
            case_type_counts=dashboard["case_type_counts"],
            priority_counts=dashboard["priority_counts"],
            reason_code_counts=dashboard["reason_code_counts"],
            filter_options=dashboard["filter_options"],
            filters=dashboard["filters"],
            tsv_exists=dashboard["tsv_exists"],
            rows=dashboard["rows"],
        ),
    )


# Рендеринг страницы со списком модулей, их состоянием и ошибками для диагностики проблем с загрузкой и выполнением модулей в рамках обработки кейсов
def _modules_response(storage_dir: Path) -> WebResponse:
    modules_path = storage_dir / "interfaces" / "modules.json"
    data, error = read_json_file(modules_path)

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

    return _html_response(
        200,
        render_template(
            "modules.html",
            title="Modules",
            modules_error=error,
            rows=rows,
        ),
    )


# Рендеринг HTML шаблонов с помощью Jinja2
def _serve_static_css() -> WebResponse:
    css_path = Path(__file__).resolve().parent / "static" / "css" / "web.css"
    content, error = safe_read_text(css_path)
    if error:
        return _text_response(
            404,
            "Static asset not found",
            "text/plain; charset=utf-8",
        )
    return _text_response(200, content or "", "text/css; charset=utf-8")


# Рендеринг ROP дашборда с фильтрацией, метриками и доступом к артефактам для анализа результатов классификации и принятия решений по кейсам
def _serve_tsv(run_dir: Path) -> WebResponse:
    content, error = safe_read_text(run_dir / "rop_review_table.tsv")
    if error:
        return _text_response(404, "TSV not found", "text/plain; charset=utf-8")

    return _text_response(
        200, content or "", "text/tab-separated-values; charset=utf-8"
    )


# Рендеринг страницы обзора выполнения с диагностикой, метаданными и списком артефактов
def _serve_run_artifact(run_dir: Path, artifact_name: str) -> WebResponse:
    if artifact_name not in RUN_ARTIFACT_WHITELIST:
        return _text_response(404, "Artifact not found", "text/plain; charset=utf-8")

    path = run_dir / artifact_name
    content, error = safe_read_text(path)
    if error:
        return _text_response(404, "Artifact not found", "text/plain; charset=utf-8")

    content_type = "application/json; charset=utf-8"
    if artifact_name.endswith(".tsv"):
        content_type = "text/tab-separated-values; charset=utf-8"
    elif artifact_name.endswith(".json"):
        data, parse_error = read_json_file(path)
        if parse_error is None:
            content = _json_dumps(_strip_sensitive_json(data))

    return _text_response(200, content or "", content_type)


# Рендеринг страницы со списком модулей, их состоянием и ошибками для диагностики проблем с загрузкой и выполнением модулей в рамках обработки кейсов
def _serve_module_artifact(run_dir: Path, artifact_name: str) -> WebResponse:
    if artifact_name not in MODULE_ARTIFACT_WHITELIST:
        return _text_response(404, "Artifact not found", "text/plain; charset=utf-8")

    artifact_path = run_dir / "module-beeagent-rop" / artifact_name
    content, error = safe_read_text(artifact_path)
    if error:
        return _text_response(404, "Artifact not found", "text/plain; charset=utf-8")

    data, parse_error = read_json_file(artifact_path)
    if parse_error is None:
        content = _json_dumps(_strip_sensitive_json(data))

    return _text_response(200, content or "", "application/json; charset=utf-8")


# Доступ к данным, фильтрация чувствительной информации и формирование ответов для рендеринга шаблонов и предоставления доступа к артефактам
def _single_query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None

    value = values[0].strip()
    return value or None


# Формирование ответов, рендеринг шаблонов и безопасный доступ к данным с фильтрацией чувствительной информации
def _html_response(status: int, html: str) -> WebResponse:
    return WebResponse(
        status=status,
        content_type="text/html; charset=utf-8",
        body=html.encode("utf-8"),
    )


# Формирование ответов, рендеринг шаблонов и безопасный доступ к данным с фильтрацией чувствительной информации
def _text_response(status: int, text: str, content_type: str) -> WebResponse:
    return WebResponse(
        status=status,
        content_type=content_type,
        body=text.encode("utf-8"),
    )


# Фильтрация чувствительной информации из JSON данных для безопасного отображения в веб-интерфейсе и предоставления доступа к артефактам без риска раскрытия конфиденциальных данных
def _strip_sensitive_json(value: Any) -> Any:
    blocked_keys = {
        "raw_eml",
        "raw_message",
        "attachment_content",
        "content",
        "content_bytes",
        "payload_bytes",
    }

    if isinstance(value, dict):
        if _is_blocked_attachment_entry(value):
            return _DROP

        clean: dict[str, Any] = {}
        for key, item in value.items():
            if key in blocked_keys:
                continue
            cleaned_item = _strip_sensitive_json(item)
            if cleaned_item is _DROP:
                continue
            clean[key] = cleaned_item
        return clean
    if isinstance(value, list):
        cleaned_list: list[Any] = []
        for item in value:
            cleaned_item = _strip_sensitive_json(item)
            if cleaned_item is _DROP:
                continue
            cleaned_list.append(cleaned_item)
        return cleaned_list
    return value


# Идентификация JSON объектов, представляющих вложения с потенциально чувствительным содержимым
def _is_blocked_attachment_entry(value: dict[str, Any]) -> bool:
    attachment_like = any(
        key in value for key in ("filename", "content_type", "size", "size_bytes")
    )
    if not attachment_like:
        return False

    filename = value.get("filename")
    if isinstance(filename, str) and filename.lower().endswith(".eml"):
        return True

    content_type = value.get("content_type")
    if (
        isinstance(content_type, str)
        and content_type.strip().lower() == "message/rfc822"
    ):
        return True

    return False


# Формирование ответов, рендеринг шаблонов и безопасный доступ к данным с фильтрацией чувствительной информации
def _json_dumps(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)
