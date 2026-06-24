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


@dataclass
class WebResponse:
    status: int
    content_type: str
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)


def render_error_page(title: str, heading: str, message: str) -> str:
    return render_template(
        "error.html",
        title=title,
        heading=heading,
        message=message,
    )


def render_home_page(storage_dir: Path) -> str:
    return render_template(
        "home.html",
        title="BeeAgent Web Console",
        runs_count=len(list_runs(storage_dir)),
    )


def render_runs_page(storage_dir: Path) -> str:
    return render_template(
        "runs.html",
        title="Runs",
        runs=list_runs(storage_dir),
    )


def get_runs_payload(storage_dir: Path) -> dict[str, Any]:
    runs = list_runs(storage_dir)
    return {
        "runs": [
            {
                "run_id": run_id,
                "html_url": f"/runs/{run_id}",
                "rop_html_url": f"/runs/{run_id}/rop",
                "api_url": f"/api/runs/{run_id}",
            }
            for run_id in runs
        ],
        "total_runs": len(runs),
    }


def render_modules_page(storage_dir: Path) -> str:
    payload = get_modules_payload(storage_dir)
    return render_template(
        "modules.html",
        title="Modules",
        modules_error=payload["error"],
        rows=payload["modules"],
    )


def get_modules_payload(storage_dir: Path) -> dict[str, Any]:
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

    return {
        "error": error,
        "modules": rows,
    }


def render_run_overview_page(run_id: str, storage_dir: Path) -> tuple[int, str]:
    status, payload = get_run_overview_payload(run_id=run_id, storage_dir=storage_dir)
    if status != 200:
        return status, render_error_page(
            title="Bad run_id",
            heading="Invalid run_id",
            message="Run identifier is invalid.",
        )

    return status, render_template(
        "run_overview.html",
        title=f"Run {run_id}",
        run_id=run_id,
        errors=payload["errors"],
        summary=payload["summary"],
        source_diagnostics=payload["source_diagnostics"],
        intake_metadata=payload["intake_metadata"],
        counts=payload["counts"],
        available_artifacts=payload["available_artifacts"],
        module_artifacts=payload["module_artifacts"],
        tsv_exists=payload["tsv_exists"],
    )


def get_run_overview_payload(
    run_id: str,
    storage_dir: Path,
) -> tuple[int, dict[str, Any]]:
    run_dir = resolve_run_dir(storage_dir, run_id)
    if run_dir is None:
        return 400, {"error": "invalid_run_id", "run_id": run_id}

    overview = build_run_overview(run_dir)
    errors = [
        f"{key}:{value}"
        for key, value in overview["errors"].items()
        if value is not None
    ]

    payload = {
        "run_id": run_id,
        "errors": errors,
        "summary": _strip_sensitive_json(overview["summary"]),
        "source_diagnostics": _strip_sensitive_json(overview["source_diagnostics"]),
        "intake_metadata": _strip_sensitive_json(overview["intake_metadata"]),
        "counts": {
            "normalized_count": overview["normalized_count"],
            "classified_count": overview["classified_count"],
        },
        "available_artifacts": [
            {
                "name": item,
                "url": f"/runs/{run_id}/artifact/{item}",
            }
            for item in overview["available_artifacts"]
        ],
        "module_artifacts": [
            {
                "name": item,
                "url": f"/runs/{run_id}/module-artifact/{item}",
            }
            for item in overview["module_artifacts"]
        ],
        "tsv_exists": (run_dir / "rop_review_table.tsv").exists(),
        "tsv_url": f"/runs/{run_id}/tsv",
    }
    return 200, payload


def render_rop_dashboard_page(
    run_id: str,
    storage_dir: Path,
    query: dict[str, list[str]],
) -> tuple[int, str]:
    status, payload = get_rop_dashboard_payload(
        run_id=run_id,
        storage_dir=storage_dir,
        query=query,
    )
    if status != 200:
        return status, render_error_page(
            title="Bad run_id",
            heading="Invalid run_id",
            message="Run identifier is invalid.",
        )

    return status, render_template(
        "rop_dashboard.html",
        title=f"ROP {run_id}",
        run_id=run_id,
        errors=payload["errors"],
        source_aggregate=payload["source_aggregate"],
        sources=payload["sources"],
        source=payload["source"],
        classification=payload["classification"],
        metrics=payload["metrics"],
        case_type_counts=payload["case_type_counts"],
        priority_counts=payload["priority_counts"],
        reason_code_counts=payload["reason_code_counts"],
        filter_options=payload["filter_options"],
        filters=payload["filters"],
        tsv_exists=payload["tsv_exists"],
        rows=payload["rows"],
    )


def get_rop_dashboard_payload(
    run_id: str,
    storage_dir: Path,
    query: dict[str, list[str]],
) -> tuple[int, dict[str, Any]]:
    run_dir = resolve_run_dir(storage_dir, run_id)
    if run_dir is None:
        return 400, {"error": "invalid_run_id", "run_id": run_id}

    dashboard = build_rop_dashboard(
        run_dir=run_dir,
        source_id_filter=_single_query_value(query, "source_id"),
        source_role_filter=_single_query_value(query, "source_role"),
        source_status_filter=_single_query_value(query, "source_status"),
        case_type_filter=_single_query_value(query, "case_type"),
        priority_filter=_single_query_value(query, "priority"),
        fallback_filter=_single_query_value(query, "fallback"),
        reason_code_filter=_single_query_value(query, "reason_code"),
    )

    payload = {
        "run_id": run_id,
        "errors": dashboard["errors"],
        "source_aggregate": dashboard["source_aggregate"],
        "sources": _strip_sensitive_json(dashboard["sources"]),
        "source": _strip_sensitive_json(dashboard["source"]),
        "classification": _strip_sensitive_json(dashboard["classification"]),
        "metrics": {
            "total_rows": dashboard["total_rows"],
            "shown_rows": dashboard["shown_rows"],
            "fallback_count": dashboard["fallback_count"],
        },
        "case_type_counts": dashboard["case_type_counts"],
        "priority_counts": dashboard["priority_counts"],
        "reason_code_counts": dashboard["reason_code_counts"],
        "filter_options": dashboard["filter_options"],
        "filters": dashboard["filters"],
        "tsv_exists": dashboard["tsv_exists"],
        "tsv_url": f"/runs/{run_id}/tsv",
        "rows": _strip_sensitive_json(dashboard["rows"]),
    }
    return 200, payload


def get_tsv_response(run_id: str, storage_dir: Path) -> tuple[int, str, str]:
    run_dir = resolve_run_dir(storage_dir, run_id)
    if run_dir is None:
        return 400, "Invalid run_id", "text/plain; charset=utf-8"
    return _serve_tsv(run_dir=run_dir)


def get_run_artifact_response(
    run_id: str,
    artifact_name: str,
    storage_dir: Path,
    module_artifact: bool,
) -> tuple[int, str, str]:
    run_dir = resolve_run_dir(storage_dir, run_id)
    if run_dir is None:
        return 400, "Invalid run_id", "text/plain; charset=utf-8"

    if module_artifact:
        return _serve_module_artifact(run_dir=run_dir, artifact_name=artifact_name)
    return _serve_run_artifact(run_dir=run_dir, artifact_name=artifact_name)


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
        return _html_response(200, render_home_page(storage_dir))

    if path == "/runs":
        return _html_response(200, render_runs_page(storage_dir))

    if path == "/modules":
        return _html_response(200, render_modules_page(storage_dir))

    if len(parts) >= 2 and parts[0] == "runs":
        run_id = parts[1]

        if len(parts) == 2:
            status, html = render_run_overview_page(
                run_id=run_id, storage_dir=storage_dir
            )
            return _html_response(status, html)

        if len(parts) == 3 and parts[2] == "rop":
            status, html = render_rop_dashboard_page(
                run_id=run_id,
                storage_dir=storage_dir,
                query=query,
            )
            return _html_response(status, html)

        if len(parts) == 3 and parts[2] == "tsv":
            status, content, content_type = get_tsv_response(run_id, storage_dir)
            return _text_response(status, content, content_type)

        if len(parts) == 4 and parts[2] == "artifact":
            status, content, content_type = get_run_artifact_response(
                run_id=run_id,
                artifact_name=parts[3],
                storage_dir=storage_dir,
                module_artifact=False,
            )
            return _text_response(status, content, content_type)

        if len(parts) == 4 and parts[2] == "module-artifact":
            status, content, content_type = get_run_artifact_response(
                run_id=run_id,
                artifact_name=parts[3],
                storage_dir=storage_dir,
                module_artifact=True,
            )
            return _text_response(status, content, content_type)

    if path == "/api/runs":
        return _json_response(200, get_runs_payload(storage_dir))

    if path == "/api/modules":
        return _json_response(200, get_modules_payload(storage_dir))

    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "runs":
        status, payload = get_run_overview_payload(parts[2], storage_dir)
        return _json_response(status, payload)

    if (
        len(parts) >= 5
        and parts[0] == "api"
        and parts[1] == "rop"
        and parts[2] == "runs"
        and parts[4] == "dashboard"
    ):
        status, payload = get_rop_dashboard_payload(parts[3], storage_dir, query)
        return _json_response(status, payload)

    logger.info("web route not found: path=%s", path)
    return _html_response(
        404,
        render_error_page(
            title="Not Found",
            heading="Route not found",
            message="The requested route does not exist.",
        ),
    )


def _json_response(status: int, value: Any) -> WebResponse:
    return WebResponse(
        status=status,
        content_type="application/json; charset=utf-8",
        body=_json_dumps(value).encode("utf-8"),
    )


def _serve_tsv(run_dir: Path) -> tuple[int, str, str]:
    content, error = safe_read_text(run_dir / "rop_review_table.tsv")
    if error:
        return 404, "TSV not found", "text/plain; charset=utf-8"

    return 200, content or "", "text/tab-separated-values; charset=utf-8"


def _serve_run_artifact(run_dir: Path, artifact_name: str) -> tuple[int, str, str]:
    if artifact_name not in RUN_ARTIFACT_WHITELIST:
        return 404, "Artifact not found", "text/plain; charset=utf-8"

    path = run_dir / artifact_name
    content, error = safe_read_text(path)
    if error:
        return 404, "Artifact not found", "text/plain; charset=utf-8"

    content_type = "application/json; charset=utf-8"
    if artifact_name.endswith(".tsv"):
        content_type = "text/tab-separated-values; charset=utf-8"
    elif artifact_name.endswith(".json"):
        data, parse_error = read_json_file(path)
        if parse_error is None:
            content = _json_dumps(_strip_sensitive_json(data))

    return 200, content or "", content_type


def _serve_module_artifact(
    run_dir: Path,
    artifact_name: str,
) -> tuple[int, str, str]:
    if artifact_name not in MODULE_ARTIFACT_WHITELIST:
        return 404, "Artifact not found", "text/plain; charset=utf-8"

    artifact_path = run_dir / "module-beeagent-rop" / artifact_name
    content, error = safe_read_text(artifact_path)
    if error:
        return 404, "Artifact not found", "text/plain; charset=utf-8"

    data, parse_error = read_json_file(artifact_path)
    if parse_error is None:
        content = _json_dumps(_strip_sensitive_json(data))

    return 200, content or "", "application/json; charset=utf-8"


def _single_query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None

    value = values[0].strip()
    return value or None


def _html_response(status: int, html: str) -> WebResponse:
    return WebResponse(
        status=status,
        content_type="text/html; charset=utf-8",
        body=html.encode("utf-8"),
    )


def _text_response(status: int, text: str, content_type: str) -> WebResponse:
    return WebResponse(
        status=status,
        content_type=content_type,
        body=text.encode("utf-8"),
    )


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


def _json_dumps(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)
