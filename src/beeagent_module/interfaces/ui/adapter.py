from __future__ import annotations

from collections.abc import Mapping
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from beeui_module.adapters.envelopes import (
    AdapterErrorResult,
    AdapterMetadata,
    AdapterResult,
    AdapterWarning,
    error_result,
    error_result_from_exception,
    ok_result,
)
from beeui_module.adapters.ids import validate_run_id

from beeagent_module.interfaces.ui.artifacts import (
    is_artifact_id_allowed,
    list_available_artifact_ids,
    resolve_artifact_path,
)
from beeagent_module.interfaces.ui.bounded_read import read_artifact_preview
from beeagent_module.interfaces.ui.locale import get_current_locale, resolve_locale, t
from beeagent_module.interfaces.ui.read_model import (
    build_config_read_model,
    build_dashboard,
    build_modules_list,
    build_modules_page_layout,
    normalize_rop_recommendation_hrefs,
    build_rop_dashboard_read_model,
    build_rop_page_layout,
    build_run_detail,
    build_runs_list,
)
from beeagent_module.interfaces.ui.rop_event_detail import (
    build_rop_event_detail_page_model,
)
from beeagent_module.cases.rop_dashboard import (
    ALLOWED_PERIODS,
    ALLOWED_PAGE_SIZES,
    ALLOWED_SORT_FIELDS,
    DEFAULT_PAGE_SIZE,
    validate_filter_params,
    validate_pagination_params,
)


def _product_version() -> str:
    try:
        return version("beeagent")
    except PackageNotFoundError:
        return "unknown"


def extract_rop_query_params(
    query: Mapping[str, str],
) -> tuple[dict[str, str], dict[str, Any], list[str]]:
    """Extract and validate filter + pagination + sort parameters.

    Returns (filter_params, pagination_params, errors).
    Invalid input produces error messages instead of silently expanding selection.
    """
    errors: list[str] = []

    allowed_query_keys = frozenset({
        "tab", "run_id", "event_id", "period", "lang", "page", "page_size", "sort", "order",
        "date_from", "date_to", "q", "sender", "subject", "case_type",
        "classification", "priority", "bitrix_status", "is_fallback", "queue",
        "columns", "columns_open", "open_dropdowns",
    })
    for key in query:
        if key not in allowed_query_keys:
            errors.append(f"Unknown query parameter: '{key}'")

    period = query.get("period")
    if period and period not in ALLOWED_PERIODS:
        errors.append(f"Invalid period '{period}'")

    # ── Filter params ──
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
    filter_params: dict[str, str] = {}
    for key in allowed_filter_keys:
        raw = query.get(key)
        if raw is not None and isinstance(raw, str) and raw.strip():
            filter_params[key] = raw.strip()
    # Map legacy key
    if "classification" in filter_params and "case_type" not in filter_params:
        filter_params["case_type"] = filter_params.pop("classification")

    # Validate filter params
    filter_errors = validate_filter_params(filter_params)
    errors.extend(filter_errors)

    # ── Pagination params ──
    page_raw = query.get("page")
    page_size_raw = query.get("page_size")
    sort_raw = query.get("sort")
    order_raw = query.get("order")

    pag_errors = validate_pagination_params(page_raw, page_size_raw, sort_raw, order_raw)
    errors.extend(pag_errors)

    # Parse pagination with safe defaults (only if no validation errors)
    if not any("page" in e for e in pag_errors):
        try:
            page = max(1, int(page_raw or "1"))
        except (ValueError, TypeError):
            page = 1
    else:
        page = 1

    if not any("page_size" in e for e in pag_errors):
        try:
            page_size = int(page_size_raw or str(DEFAULT_PAGE_SIZE))
            if page_size not in ALLOWED_PAGE_SIZES:
                page_size = DEFAULT_PAGE_SIZE
        except (ValueError, TypeError):
            page_size = DEFAULT_PAGE_SIZE
    else:
        page_size = DEFAULT_PAGE_SIZE

    if not any("sort" in e for e in pag_errors):
        sort = sort_raw if sort_raw in ALLOWED_SORT_FIELDS else "received_at"
    else:
        sort = "received_at"

    if not any("order" in e for e in pag_errors):
        order = order_raw if order_raw in ("asc", "desc") else "desc"
    else:
        order = "desc"

    pagination_params: dict[str, Any] = {
        "page": page,
        "page_size": page_size,
        "sort": sort,
        "order": order,
    }

    return filter_params, pagination_params, errors


class BeeAgentUiAdapter:
    def __init__(
        self,
        storage_dir: Path,
        settings: dict[str, Any],
    ) -> None:
        self._storage_dir = storage_dir
        self._settings = settings

        self.metadata = AdapterMetadata(
            product_id="beeagent",
            title="BeeAgent",
            version=_product_version(),
            capabilities=("read_only",),
            supported_pages=("/", "/runs", "/rop", "/modules"),
        )

    def get_dashboard(self) -> AdapterResult | AdapterErrorResult:
        try:
            data = build_dashboard(
                self._storage_dir,
                locale=get_current_locale(),
            )
            return ok_result(data)
        except Exception as exc:
            return error_result_from_exception(exc)

    def list_runs(self) -> AdapterResult | AdapterErrorResult:
        try:
            data = build_runs_list(
                self._storage_dir,
                locale=get_current_locale(),
            )
            return ok_result(data)
        except Exception as exc:
            return error_result_from_exception(exc)

    def get_run(self, run_id: str) -> AdapterResult | AdapterErrorResult:
        try:
            validate_run_id(run_id)
            data = build_run_detail(self._storage_dir, run_id)
            if "error" in data:
                return error_result("not_found", f"Run {run_id} not found")
            return ok_result(data)
        except Exception as exc:
            return error_result_from_exception(exc)

    def list_artifacts(self, run_id: str) -> AdapterResult | AdapterErrorResult:
        try:
            items = list_available_artifact_ids(self._storage_dir, run_id)
            return ok_result(items)
        except Exception as exc:
            return error_result_from_exception(exc)

    def read_artifact(
        self, run_id: str, artifact_id: str
    ) -> AdapterResult | AdapterErrorResult:
        try:
            if not is_artifact_id_allowed(artifact_id):
                return error_result(
                    "invalid_id", f"Artifact '{artifact_id}' is not allowlisted"
                )

            artifact_path = resolve_artifact_path(
                self._storage_dir, run_id, artifact_id
            )
            if artifact_path is None:
                return error_result(
                    "not_found",
                    f"Artifact '{artifact_id}' not found for run {run_id}",
                )

            text, warning, error = read_artifact_preview(artifact_id, artifact_path)
            if error:
                return error_result("unavailable", error)

            warnings: list[AdapterWarning] = []
            if warning:
                warnings.append(AdapterWarning(code="preview_warning", message=warning))

            return ok_result(
                {
                    "artifact_id": artifact_id,
                    "run_id": run_id,
                    "content": text or "",
                    "content_type": _infer_mime(artifact_id),
                },
                warnings=warnings,
            )
        except Exception as exc:
            return error_result_from_exception(exc)

    def get_config_read_model(self) -> AdapterResult | AdapterErrorResult:
        try:
            data = build_config_read_model(self._settings)
            return ok_result(data)
        except Exception as exc:
            return error_result_from_exception(exc)

    def validate_config_candidate(
        self, candidate: dict[str, Any]
    ) -> AdapterResult | AdapterErrorResult:
        return error_result(
            "unavailable",
            "Config preview is unavailable in BeeAgent UI-4 read-only mode",
        )

    def apply_config_candidate(
        self,
        candidate: dict[str, Any],
        expected_hash: str | None = None,
        actor: dict[str, str] | None = None,
    ) -> AdapterResult | AdapterErrorResult:
        return error_result(
            "permission_denied",
            "Config apply is disabled in BeeAgent UI-4 read-only mode",
        )

    def list_actions(self) -> AdapterResult | AdapterErrorResult:
        return error_result(
            "unavailable",
            "Operator actions are unavailable in BeeAgent UI-4 read-only mode",
        )

    def preview_action(
        self, action_id: str, payload: dict[str, Any]
    ) -> AdapterResult | AdapterErrorResult:
        return error_result(
            "unavailable",
            "Operator actions are unavailable in BeeAgent UI-4 read-only mode",
        )

    def execute_action(
        self,
        action_id: str,
        payload: dict[str, Any],
        actor: dict[str, str] | None = None,
    ) -> AdapterResult | AdapterErrorResult:
        return error_result(
            "permission_denied",
            "Operator actions execution is disabled in BeeAgent UI-4 read-only mode",
        )

    def get_modules_dashboard(self) -> AdapterResult | AdapterErrorResult:
        try:
            data = build_modules_list(self._storage_dir)
            return ok_result(data)
        except Exception as exc:
            return error_result_from_exception(exc)

    def get_rop_dashboard(
        self,
        run_id: str | None = None,
        period: str | None = None,
        filter_params: dict[str, str] | None = None,
        page: int = 1,
        page_size: int = 25,
        sort: str = "received_at",
        order: str = "desc",
    ) -> AdapterResult | AdapterErrorResult:
        try:
            if run_id is not None:
                try:
                    validate_run_id(run_id)
                except Exception:
                    return error_result("invalid_run_id", "Invalid run_id")

            default_period = self._settings["rop"]["dashboard"]["default_period"]
            configured_periods = self._settings["rop"]["dashboard"]["periods"]
            data = build_rop_dashboard_read_model(
                self._storage_dir,
                run_id,
                period=period,
                default_period=default_period,
                configured_periods=configured_periods,
                filter_params=filter_params,
                page=page,
                page_size=page_size,
                sort=sort,
                order=order,
            )
            if "error" in data:
                return error_result("not_found", data.get("message", "Not found"))
            return ok_result(data)
        except Exception as exc:
            return error_result_from_exception(exc)

    def get_page(
        self, page_id: str, query: Mapping[str, str]
    ) -> AdapterResult | AdapterErrorResult:
        try:
            if page_id in {"rop", "rop_dashboard"}:
                tab = query.get("tab", "overview")
                allowed_tabs = frozenset(
                    {
                        "overview",
                        "queue",
                        "sources",
                        "attachments",
                        "evidence",
                        "bitrix",
                        "threads",
                        "ai_assist",
                        "recommendations",
                    }
                )
                if tab not in allowed_tabs:
                    tab = "overview"

                run_id = query.get("run_id")
                period = query.get("period")
                if tab == "queue":
                    # Queue always starts from the full dataset; its validated
                    # date range is the only time constraint for operator work.
                    period = "all"
                if run_id is not None:
                    try:
                        validate_run_id(run_id)
                    except Exception:
                        return error_result("invalid_run_id", "Invalid run_id")

                # Extract and validate filter + pagination + sort params atomically
                filter_params, pagination_params, param_errors = extract_rop_query_params(query)
                if param_errors:
                    return error_result(
                        "invalid_params",
                        "; ".join(param_errors),
                    )

                default_period = self._settings["rop"]["dashboard"]["default_period"]
                configured_periods = self._settings["rop"]["dashboard"]["periods"]
                data = build_rop_dashboard_read_model(
                    self._storage_dir,
                    run_id,
                    period=period,
                    default_period=default_period,
                    configured_periods=configured_periods,
                    filter_params=filter_params,
                    page=pagination_params["page"],
                    page_size=pagination_params["page_size"],
                    sort=pagination_params["sort"],
                    order=pagination_params["order"],
                )
                if "error" in data:
                    return error_result("not_found", data.get("message", "Not found"))

                locale = resolve_locale(query.get("lang"))
                data["rop_recommendations"] = normalize_rop_recommendation_hrefs(
                    data.get("rop_recommendations", []),
                    run_id=str(data.get("run_id", "")),
                    period=data.get("period"),
                    locale=locale,
                )
                data["locale"] = locale
                data["title"] = t("ROP Dashboard", locale)
                layout = build_rop_page_layout(data, tab=tab, locale=locale)
                data["layout"] = layout
                return ok_result(data)

            if page_id == "modules":
                locale = resolve_locale(query.get("lang"))
                modules_data = build_modules_list(self._storage_dir)
                modules_data["layout"] = build_modules_page_layout(modules_data, locale=locale)
                return ok_result(modules_data)

            if page_id == "rop_event_detail":
                run_id = query.get("run_id")
                event_id = query.get("event_id")
                if not run_id or not event_id:
                    return error_result(
                        "missing_params",
                        "run_id and event_id are required",
                    )
                try:
                    validate_run_id(run_id)
                except Exception:
                    return error_result("invalid_run_id", "Invalid run_id")

                locale = resolve_locale(query.get("lang"))
                filter_params, pagination_params, param_errors = extract_rop_query_params(query)
                if param_errors:
                    return error_result("invalid_params", "; ".join(param_errors))
                data = build_rop_event_detail_page_model(
                    self._storage_dir,
                    run_id,
                    event_id,
                    lang=locale,
                    period=query.get("period"),
                    filter_params=filter_params,
                    page=pagination_params["page"],
                    page_size=pagination_params["page_size"],
                    sort=pagination_params["sort"],
                    order=pagination_params["order"],
                )
                if not data.get("ok", True) and data.get("error") == "not_found":
                    return error_result("not_found", "Event not found")
                return ok_result(data)

            return error_result("unavailable", f"Page '{page_id}' is unavailable")
        except Exception as exc:
            return error_result_from_exception(exc)


def _infer_mime(artifact_id: str) -> str:
    from beeagent_module.interfaces.ui.artifacts import get_artifact_content_type

    return get_artifact_content_type(artifact_id)
