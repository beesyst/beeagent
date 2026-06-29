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
from beeagent_module.interfaces.ui.locale import resolve_locale, t
from beeagent_module.interfaces.ui.read_model import (
    build_config_read_model,
    build_dashboard,
    build_modules_list,
    build_modules_page_layout,
    build_rop_dashboard_read_model,
    build_rop_page_layout,
    build_run_detail,
    build_runs_list,
)


def _product_version() -> str:
    try:
        return version("beeagent")
    except PackageNotFoundError:
        return "unknown"


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
            data = build_dashboard(self._storage_dir)
            return ok_result(data)
        except Exception as exc:
            return error_result_from_exception(exc)

    def list_runs(self) -> AdapterResult | AdapterErrorResult:
        try:
            data = build_runs_list(self._storage_dir)
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
        self, run_id: str | None = None, period: str | None = None
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
            if page_id == "rop_dashboard":
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
                    }
                )
                if tab not in allowed_tabs:
                    tab = "overview"

                run_id = query.get("run_id")
                period = query.get("period")
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
                )
                if "error" in data:
                    return error_result("not_found", data.get("message", "Not found"))

                locale = resolve_locale(query.get("lang"))
                data["locale"] = locale
                data["title"] = t("ROP Dashboard", locale)
                layout = build_rop_page_layout(data, tab=tab, locale=locale)
                data["layout"] = layout
                return ok_result(data)

            if page_id == "modules":
                modules_data = build_modules_list(self._storage_dir)
                modules_data["layout"] = build_modules_page_layout(modules_data)
                return ok_result(modules_data)

            return error_result("unavailable", f"Page '{page_id}' is unavailable")
        except Exception as exc:
            return error_result_from_exception(exc)


def _infer_mime(artifact_id: str) -> str:
    from beeagent_module.interfaces.ui.artifacts import get_artifact_content_type

    return get_artifact_content_type(artifact_id)
