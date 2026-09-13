from __future__ import annotations

import logging
from collections.abc import Mapping
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

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

from beeagent_module.cases.rop_dashboard import (
    ALLOWED_PAGE_SIZES,
    ALLOWED_PERIODS,
    ALLOWED_SORT_FIELDS,
    DEFAULT_PAGE_SIZE,
    validate_filter_params,
    validate_pagination_params,
)
from beeagent_module.core.authorization import (
    SCOPE_ROP_BLACKLIST_WRITE,
    SCOPE_ROP_SOURCES_WRITE,
    has_rop_capability_authority,
)
from beeagent_module.core.rop_sender_blacklist import (
    SenderBlacklistError,
    add_sender_blacklist_entry,
    load_sender_blacklist_entries,
    normalize_sender_email,
    remove_sender_blacklist_email,
    update_sender_blacklist_entry,
    write_sender_blacklist_audit,
)
from beeagent_module.core.rop_sources import (
    RopSourcesError,
    add_mailbox_source,
    credential_env_names,
    load_rop_source_connection_health,
    load_rop_sources,
    record_rop_source_connection_health,
    remove_rop_source,
    remove_rop_source_connection_health,
    set_rop_source_enabled,
    update_mailbox_source,
    update_rop_source_display_name,
    write_rop_sources_audit,
)
from beeagent_module.adapters.mailbox import (
    ImapReadonlyMailboxClient,
    MailboxAuthError,
    MailboxUnavailableError,
)
from beeagent_module.core.env_sync import (
    read_selected_env_values,
    remove_selected_env_values,
    update_selected_env_values,
)
from beeagent_module.core.paths import get_project_root
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
    build_rop_page_layout,
    build_rop_tab_read_model,
    build_run_detail,
    build_runs_list,
    normalize_rop_recommendation_hrefs,
)
from beeagent_module.interfaces.ui.rop_event_detail import (
    build_rop_event_detail_page_model,
)


logger = logging.getLogger(__name__)


def _product_version() -> str:
    try:
        return version("beeagent")
    except PackageNotFoundError:
        return "unknown"


def _blacklist_entry_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: payload.get(key, "User" if key == "role" else "")
        for key in ("name", "title", "email", "role")
    }


def _blacklist_audit_email(payload: dict[str, Any]) -> str | None:
    try:
        return normalize_sender_email(payload.get("email"))
    except SenderBlacklistError:
        return None


def _validate_blacklist_payload(action_id: str, payload: dict[str, Any]) -> None:
    expected = (
        {"email"}
        if action_id in {"rop_sender_blacklist_add", "rop_sender_blacklist_remove"}
        else {"name", "title", "email", "role"}
    )
    if action_id == "rop_sender_blacklist_update":
        expected = {"original_email", *expected}
    if not isinstance(payload, dict) or (
        set(payload) != expected
        and not (
            action_id == "rop_sender_blacklist_add"
            and set(payload) == {"name", "title", "email", "role"}
        )
    ):
        raise SenderBlacklistError("Action payload is invalid")
    normalize_sender_email(payload.get("email"))
    if action_id == "rop_sender_blacklist_update":
        normalize_sender_email(payload.get("original_email"))


def _blacklist_fields(
    locale: str, entry: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    entry = entry or {"name": "", "title": "", "email": "", "role": "User"}
    return [
        {
            "name": "name",
            "type": "text",
            "label": t("Name", locale),
            "required": False,
            "max_length": 128,
            "value": entry["name"],
        },
        {
            "name": "title",
            "type": "text",
            "label": t("Title", locale),
            "required": False,
            "max_length": 128,
            "value": entry["title"],
        },
        {
            "name": "email",
            "type": "email",
            "label": t("Email", locale),
            "required": True,
            "max_length": 254,
            "value": entry["email"],
        },
        {
            "name": "role",
            "type": "text",
            "label": t("Role", locale),
            "required": False,
            "max_length": 64,
            "value": entry["role"],
        },
    ]


def _blacklist_pagination(
    query: Mapping[str, str],
    page: int,
    pages: int,
    page_size: int,
    count: int,
    locale: str,
) -> dict[str, Any]:
    def href(target_page: int, target_size: int = page_size) -> str:
        values = {
            "tab": query.get("tab", "blacklist"),
            "page": str(target_page),
            "page_size": str(target_size),
        }
        if query.get("lang"):
            values["lang"] = query["lang"]
        if query.get("q"):
            values["q"] = query["q"]
        return "/rop?" + urlencode(values)

    return {
        "label": f"{count} " + ("записей" if locale == "ru" else "entries"),
        "pages": [
            {
                "number": number,
                "label": str(number),
                "href": href(number),
                "active": number == page,
            }
            for number in range(1, pages + 1)
        ],
        "previous": {"href": href(page - 1)} if page > 1 else None,
        "next": {"href": href(page + 1)} if page < pages else None,
        "page_size": {
            "label": "",
            "current": str(page_size),
            "options": [
                {"value": str(size), "label": str(size), "href": href(1, size)}
                for size in (25, 50, 100)
            ],
        },
    }


def _source_fields(
    locale: str,
    source: dict[str, Any] | None = None,
    adding: bool = False,
    username: str = "",
) -> list[dict[str, Any]]:
    source = source or {}
    mailbox = (
        source.get("mailbox", {}) if isinstance(source.get("mailbox"), dict) else {}
    )
    fields = [
        {
            "name": "display_name",
            "type": "text",
            "label": t("Source name", locale),
            "required": True,
            "max_length": 128,
            "value": source.get("display_name", ""),
        },
        {
            "name": "host",
            "type": "text",
            "label": t("Mail server", locale),
            "required": True,
            "max_length": 253,
            "value": mailbox.get("host", ""),
        },
        {
            "name": "folder",
            "type": "text",
            "label": t("Folder", locale),
            "required": True,
            "max_length": 128,
            "value": mailbox.get("folder", "INBOX"),
        },
        {
            "name": "username",
            "type": "text",
            "label": t("Username", locale),
            "required": True,
            "max_length": 254,
            "value": username,
        },
        {
            "name": "password",
            "type": "password",
            "label": t("Password", locale),
            "required": adding,
            "max_length": 1024,
            "value": "",
        },
    ]
    if not adding:
        fields[-1]["column_key"] = "masked_value"
    if adding:
        fields.append(
            {
                "name": "enabled",
                "type": "radio",
                "label": t("Status", locale),
                "required": True,
                "value": "true",
                "options": [
                    {"value": "true", "label": t("Enabled", locale)},
                    {"value": "false", "label": t("Disabled", locale)},
                ],
            }
        )
    return fields


def _source_credentials(project_root: Path, source: dict[str, Any]) -> tuple[str, str]:
    mailbox = source.get("mailbox")
    if not isinstance(mailbox, dict):
        return "", "—"
    username_env = mailbox.get("username_env")
    password_env = mailbox.get("password_env")
    if not isinstance(username_env, str) or not isinstance(password_env, str):
        return "", "—"
    values = read_selected_env_values(
        project_root / ".env", {username_env, password_env}
    )
    return values.get(username_env, ""), "********" if values.get(password_env) else "—"


def _source_processed_totals(
    storage_dir: Path, settings: dict[str, Any]
) -> dict[str, int] | None:
    dashboard = settings.get("rop", {}).get("dashboard", {})
    if not isinstance(dashboard, dict):
        return None
    periods = dashboard.get("periods")
    if not isinstance(periods, list) or "all" not in periods:
        return None
    try:
        data = build_rop_tab_read_model(
            storage_dir,
            tab="overview",
            period="all",
            default_period=dashboard.get("default_period"),
            configured_periods=periods,
        )
    except Exception:
        return None
    if not isinstance(data, dict) or data.get("error"):
        return None
    series = data.get("series")
    contribution = (
        series.get("source_contribution") if isinstance(series, dict) else None
    )
    if not isinstance(contribution, dict):
        return {}
    labels = contribution.get("labels")
    values = contribution.get("series")
    if (
        not isinstance(labels, list)
        or not isinstance(values, list)
        or len(labels) != len(values)
    ):
        return None
    totals: dict[str, int] = {}
    for source_id, value in zip(labels, values, strict=True):
        if not isinstance(source_id, str) or not source_id:
            return None
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return None
        totals[source_id] = value
    return totals


def _check_mailbox_source_access(
    project_root: Path, storage_dir: Path, source: dict[str, Any]
) -> tuple[str, str]:
    source_id = source.get("source_id")
    mailbox = source.get("mailbox")
    if (
        not isinstance(source_id, str)
        or source.get("source_type") != "mailbox_readonly"
        or not isinstance(mailbox, dict)
    ):
        raise RopSourcesError("Mailbox source was not found")
    username_env = mailbox.get("username_env")
    password_env = mailbox.get("password_env")
    if not isinstance(username_env, str) or not isinstance(password_env, str):
        raise RopSourcesError("Mailbox source is invalid")
    credentials = read_selected_env_values(
        project_root / ".env", {username_env, password_env}
    )
    username = credentials.get(username_env, "").strip()
    password = credentials.get(password_env, "").strip()
    if not username or not password:
        status, reason = "failed", "missing_credentials"
    else:
        try:
            ImapReadonlyMailboxClient(
                host=str(mailbox["host"]),
                port=int(mailbox["port"]),
                use_ssl=bool(mailbox["use_ssl"]),
                username=username,
                password=password,
            ).check_access(str(mailbox["folder"]), timeout_seconds=10.0)
            status, reason = "connected", "ok"
        except MailboxAuthError:
            status, reason = "failed", "auth_failure"
        except MailboxUnavailableError, OSError:
            status, reason = "failed", "mailbox_unavailable"
    record_rop_source_connection_health(storage_dir, source_id, status, reason)
    return status, reason


def _available_source_count(
    project_root: Path, storage_dir: Path, settings: dict[str, Any]
) -> int:
    health = load_rop_source_connection_health(storage_dir)
    count = 0
    for source in load_rop_sources(project_root, settings):
        source_id = source.get("source_id")
        if (
            source.get("enabled") is True
            and isinstance(source_id, str)
            and health.get(source_id, {}).get("status") == "connected"
        ):
            count += 1
    return count


def _connection_action_icon(health: dict[str, str] | None) -> str:
    status = health.get("status") if isinstance(health, dict) else None
    if status == "connected":
        return "plug-connected"
    if status == "failed":
        return "plug-connected-x"
    return "check"


def _connection_action_tone(health: dict[str, str] | None) -> str:
    status = health.get("status") if isinstance(health, dict) else None
    if status == "connected":
        return "green"
    if status == "failed":
        return "red"
    return "secondary"


def _connection_action_label(locale: str, health: dict[str, str] | None) -> str:
    if not isinstance(health, dict):
        return t("Check connection", locale)
    if health.get("status") == "connected":
        return t("Source available. Check again", locale)
    reason = health.get("reason_code")
    if reason == "missing_credentials":
        return t("Credentials are not configured. Check again", locale)
    if reason == "auth_failure":
        return t("Authentication failed. Check again", locale)
    return t("Source unavailable. Check again", locale)


def _source_payload_text(
    payload: dict[str, Any], name: str, maximum: int, *, required: bool = True
) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or len(value) > maximum:
        raise RopSourcesError("Source payload is invalid")
    if required and not value:
        raise RopSourcesError("Source payload is invalid")
    if any(character in value for character in ("\r", "\n", "\x00")):
        raise RopSourcesError("Source payload is invalid")
    return value


def _validate_source_payload(action_id: str, payload: dict[str, Any]) -> None:
    expected = {
        "rop_source_add": {
            "display_name",
            "host",
            "folder",
            "username",
            "password",
            "enabled",
        },
        "rop_source_update": set(),
        "rop_source_remove": {"source_id"},
        "rop_source_set_enabled": {"source_id", "enabled"},
        "rop_source_check_connection": {"source_id"},
    }.get(action_id)
    if not isinstance(payload, dict) or expected is None:
        raise RopSourcesError("Source payload is invalid")
    if action_id == "rop_source_update":
        keys = set(payload)
        if keys not in (
            {"source_id", "display_name"},
            {"source_id", "display_name", "host", "folder", "username", "password"},
        ):
            raise RopSourcesError("Source payload is invalid")
    elif set(payload) != expected:
        raise RopSourcesError("Source payload is invalid")
    if action_id in {"rop_source_add", "rop_source_update"}:
        _source_payload_text(payload, "display_name", 128)
        if "host" in payload:
            _source_payload_text(payload, "host", 253)
            _source_payload_text(payload, "folder", 128)
            _source_payload_text(payload, "username", 254)
            _source_payload_text(
                payload,
                "password",
                1024,
                required=action_id == "rop_source_add",
            )
    if action_id == "rop_source_add" and payload["enabled"] not in {"true", "false"}:
        raise RopSourcesError("Source payload is invalid")
    if action_id == "rop_source_set_enabled" and not isinstance(
        payload["enabled"], bool
    ):
        raise RopSourcesError("Source payload is invalid")


def extract_rop_query_params(
    query: Mapping[str, str],
) -> tuple[dict[str, str], dict[str, Any], list[str]]:
    """Extract and validate filter + pagination + sort parameters.

    Returns (filter_params, pagination_params, errors).
    Invalid input produces error messages instead of silently expanding selection.
    """
    errors: list[str] = []

    allowed_query_keys = frozenset(
        {
            "tab",
            "run_id",
            "event_id",
            "event_instance_id",
            "period",
            "lang",
            "page",
            "page_size",
            "sort",
            "order",
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
            "has_attachments",
            "queue",
            "columns",
            "columns_open",
            "open_dropdowns",
        }
    )
    for key in query:
        if key not in allowed_query_keys:
            errors.append(f"Unknown query parameter: '{key}'")

    period = query.get("period")
    if period and period not in ALLOWED_PERIODS:
        errors.append(f"Invalid period '{period}'")

    # ── Filter params ──
    allowed_filter_keys = frozenset(
        {
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
            "has_attachments",
            "queue",
            "columns",
            "columns_open",
            "open_dropdowns",
        }
    )
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

    pag_errors = validate_pagination_params(
        page_raw, page_size_raw, sort_raw, order_raw
    )
    errors.extend(pag_errors)

    # Parse pagination with safe defaults (only if no validation errors)
    if not any("page" in e for e in pag_errors):
        try:
            page = max(1, int(page_raw or "1"))
        except ValueError, TypeError:
            page = 1
    else:
        page = 1

    if not any("page_size" in e for e in pag_errors):
        try:
            page_size = int(page_size_raw or str(DEFAULT_PAGE_SIZE))
            if page_size not in ALLOWED_PAGE_SIZES:
                page_size = DEFAULT_PAGE_SIZE
        except ValueError, TypeError:
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
            capabilities=("bounded_actions", "read_only"),
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
            logger.exception("BeeAgent dashboard adapter failed")
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
            data = build_config_read_model(self._settings, get_project_root())
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
        if action_id in {
            "rop_source_add",
            "rop_source_update",
            "rop_source_remove",
            "rop_source_set_enabled",
            "rop_source_check_connection",
        }:
            return ok_result({})
        if action_id not in {
            "rop_sender_blacklist_add",
            "rop_sender_blacklist_update",
            "rop_sender_blacklist_remove",
        }:
            return error_result("permission_denied", "Unknown operator action")
        try:
            _validate_blacklist_payload(action_id, payload)
            return ok_result({})
        except SenderBlacklistError as exc:
            return error_result("invalid_input", str(exc))

    def execute_action(
        self,
        action_id: str,
        payload: dict[str, Any],
        actor: dict[str, str] | None = None,
    ) -> AdapterResult | AdapterErrorResult:
        if action_id in {
            "rop_source_add",
            "rop_source_update",
            "rop_source_remove",
            "rop_source_set_enabled",
            "rop_source_check_connection",
        }:
            return self._execute_rop_source_action(action_id, payload, actor)
        if action_id not in {
            "rop_sender_blacklist_add",
            "rop_sender_blacklist_update",
            "rop_sender_blacklist_remove",
        }:
            return error_result("permission_denied", "Unknown operator action")
        actor_id = actor.get("user_id") if isinstance(actor, dict) else None
        email = _blacklist_audit_email(payload)
        if not isinstance(actor, dict) or actor.get("role") not in {
            "operator",
            "admin",
        }:
            write_sender_blacklist_audit(
                self._storage_dir,
                action_id=action_id,
                actor_id=actor_id if isinstance(actor_id, str) else None,
                outcome="permission_denied",
                email=email,
            )
            return error_result(
                "permission_denied", "ROP operator or admin role is required"
            )
        principals = self._settings.get("web", {}).get("auth", {}).get("principals", [])
        scopes = next(
            (
                item.get("scopes", [])
                for item in principals
                if isinstance(item, dict) and item.get("id") == actor_id
            ),
            [],
        )
        if not isinstance(scopes, list) or not has_rop_capability_authority(
            str(actor.get("role") or ""), scopes, SCOPE_ROP_BLACKLIST_WRITE
        ):
            write_sender_blacklist_audit(
                self._storage_dir,
                action_id=action_id,
                actor_id=actor_id if isinstance(actor_id, str) else None,
                outcome="permission_denied",
                email=email,
            )
            return error_result(
                "permission_denied", "ROP blacklist write scope is required"
            )
        try:
            _validate_blacklist_payload(action_id, payload)
            email = normalize_sender_email(payload.get("email"))
            if action_id == "rop_sender_blacklist_add":
                entry, changed = add_sender_blacklist_entry(
                    self._storage_dir, _blacklist_entry_payload(payload)
                )
                email = entry["email"]
            elif action_id == "rop_sender_blacklist_update":
                entry, changed = update_sender_blacklist_entry(
                    self._storage_dir,
                    payload["original_email"],
                    _blacklist_entry_payload(payload),
                )
                email = entry["email"]
            else:
                email, changed = remove_sender_blacklist_email(self._storage_dir, email)
            write_sender_blacklist_audit(
                self._storage_dir,
                action_id=action_id,
                actor_id=actor_id if isinstance(actor_id, str) else None,
                outcome="changed" if changed else "unchanged",
                email=email,
            )
            return ok_result({"changed": changed})
        except SenderBlacklistError as exc:
            write_sender_blacklist_audit(
                self._storage_dir,
                action_id=action_id,
                actor_id=actor_id if isinstance(actor_id, str) else None,
                outcome="invalid_input",
                email=email,
            )
            return error_result("invalid_input", str(exc))

    def _execute_rop_source_action(
        self, action_id: str, payload: dict[str, Any], actor: dict[str, str] | None
    ) -> AdapterResult | AdapterErrorResult:
        actor_id = actor.get("user_id") if isinstance(actor, dict) else None
        source_id = (
            payload.get("source_id")
            if isinstance(payload.get("source_id"), str)
            else None
        )
        principals = self._settings.get("web", {}).get("auth", {}).get("principals", [])
        scopes = next(
            (
                item.get("scopes", [])
                for item in principals
                if isinstance(item, dict) and item.get("id") == actor_id
            ),
            [],
        )
        if (
            not isinstance(actor, dict)
            or not isinstance(scopes, list)
            or not has_rop_capability_authority(
                str(actor.get("role") or ""), scopes, SCOPE_ROP_SOURCES_WRITE
            )
        ):
            write_rop_sources_audit(
                self._storage_dir,
                action_id=action_id,
                actor_id=actor_id if isinstance(actor_id, str) else None,
                source_id=source_id,
                outcome="permission_denied",
            )
            return error_result(
                "permission_denied", "ROP sources write scope is required"
            )
        try:
            root = get_project_root()
            _validate_source_payload(action_id, payload)
            if action_id == "rop_source_add":
                source = {
                    "display_name": payload["display_name"],
                    "host": payload["host"],
                    "folder": payload["folder"],
                    "enabled": payload["enabled"] == "true",
                }

                def persist_new_source_credentials(entry: dict[str, Any]) -> None:
                    mailbox = entry["mailbox"]
                    try:
                        update_selected_env_values(
                            root / ".env",
                            {
                                mailbox["username_env"]: payload["username"],
                                mailbox["password_env"]: payload["password"],
                            },
                            section="# ROP mailbox",
                        )
                    except ValueError as exc:
                        raise RopSourcesError(
                            "Mailbox credentials are invalid"
                        ) from exc

                _entry, changed = add_mailbox_source(
                    root, self._settings, source, persist_new_source_credentials
                )
                source_id = _entry["source_id"]
            elif action_id == "rop_source_update":
                source_id = payload.get("source_id")
                if not isinstance(source_id, str):
                    raise RopSourcesError("Source ID is invalid")
                current = next(
                    (
                        item
                        for item in load_rop_sources(root, self._settings)
                        if item["source_id"] == source_id
                    ),
                    None,
                )
                if current is None:
                    raise RopSourcesError("ROP source was not found")
                if current["source_type"] == "mailbox_readonly":
                    mailbox = current["mailbox"]
                    existing_credentials = read_selected_env_values(
                        root / ".env", {mailbox["username_env"]}
                    )
                    credentials_changed = payload[
                        "username"
                    ] != existing_credentials.get(mailbox["username_env"], "") or bool(
                        payload["password"]
                    )

                    def persist_updated_source_credentials(
                        _entry: dict[str, Any],
                    ) -> None:
                        updates = {mailbox["username_env"]: payload["username"]}
                        if payload["password"]:
                            updates[mailbox["password_env"]] = payload["password"]
                        try:
                            update_selected_env_values(root / ".env", updates)
                        except ValueError as exc:
                            raise RopSourcesError(
                                "Mailbox credentials are invalid"
                            ) from exc

                    _entry, changed = update_mailbox_source(
                        root,
                        self._settings,
                        source_id,
                        payload,
                        persist_updated_source_credentials,
                    )
                    changed = changed or credentials_changed
                    _check_mailbox_source_access(root, self._storage_dir, _entry)
                else:
                    _entry, changed = update_rop_source_display_name(
                        root,
                        self._settings,
                        source_id,
                        payload.get("display_name"),
                    )
            elif action_id == "rop_source_set_enabled":
                source_id = payload.get("source_id")
                if not isinstance(source_id, str):
                    raise RopSourcesError("Source ID is invalid")
                _entry, changed = set_rop_source_enabled(
                    root,
                    self._settings,
                    source_id,
                    payload.get("enabled"),
                )
            elif action_id == "rop_source_check_connection":
                source_id = payload.get("source_id")
                if not isinstance(source_id, str):
                    raise RopSourcesError("Source ID is invalid")
                current = next(
                    (
                        item
                        for item in load_rop_sources(root, self._settings)
                        if item["source_id"] == source_id
                    ),
                    None,
                )
                if (
                    not isinstance(current, dict)
                    or current.get("source_type") != "mailbox_readonly"
                ):
                    raise RopSourcesError("Mailbox source was not found")
                _check_mailbox_source_access(root, self._storage_dir, current)
                changed = True
            else:
                source_id = payload.get("source_id")
                if not isinstance(source_id, str):
                    raise RopSourcesError("Source ID is invalid")
                current = next(
                    (
                        item
                        for item in load_rop_sources(root, self._settings)
                        if item["source_id"] == source_id
                    ),
                    None,
                )
                _entry, changed = remove_rop_source(root, self._settings, source_id)
                if changed and isinstance(current, dict):
                    mailbox = current.get("mailbox")
                    if isinstance(mailbox, dict) and (
                        mailbox.get("username_env"),
                        mailbox.get("password_env"),
                    ) == credential_env_names(source_id):
                        remove_selected_env_values(
                            root / ".env",
                            {mailbox["username_env"], mailbox["password_env"]},
                        )
                    try:
                        remove_rop_source_connection_health(
                            self._storage_dir, source_id
                        )
                    except OSError:
                        logger.warning(
                            "ROP source connection health cleanup failed: source_id=%s",
                            source_id,
                        )
            write_rop_sources_audit(
                self._storage_dir,
                action_id=action_id,
                actor_id=actor_id if isinstance(actor_id, str) else None,
                source_id=source_id,
                outcome="changed" if changed else "unchanged",
            )
            return ok_result(
                {
                    "changed": changed,
                    **(
                        {"source_id": source_id}
                        if action_id == "rop_source_add"
                        else {}
                    ),
                }
            )
        except RopSourcesError as exc:
            write_rop_sources_audit(
                self._storage_dir,
                action_id=action_id,
                actor_id=actor_id if isinstance(actor_id, str) else None,
                source_id=source_id,
                outcome="invalid_input",
            )
            return error_result("invalid_input", str(exc))

    def _sources_layout(
        self, query: Mapping[str, str], locale: str
    ) -> list[dict[str, Any]]:
        sources = load_rop_sources(get_project_root(), self._settings)
        health = load_rop_source_connection_health(self._storage_dir)
        processed_totals = _source_processed_totals(self._storage_dir, self._settings)
        query_text = query.get("q", "").strip().lower()
        if len(query_text) > 254:
            raise RopSourcesError("Search query is invalid")
        sources = [
            source
            for source in sources
            if not query_text
            or any(
                query_text in str(source.get(key, "")).lower()
                for key in (
                    "source_id",
                    "display_name",
                    "source_type",
                    "client_id",
                    "authority",
                )
            )
            or (
                isinstance(source.get("mailbox"), dict)
                and query_text
                in " ".join(
                    str(source["mailbox"].get(key, "")).lower()
                    for key in ("host", "folder")
                )
            )
        ]
        page_size_text = query.get("page_size", "25")
        if page_size_text not in {"25", "50", "100"}:
            raise RopSourcesError("Page size is invalid")
        page_text = query.get("page", "1")
        if not page_text.isdecimal() or int(page_text) < 1:
            raise RopSourcesError("Page is invalid")
        page_size = int(page_size_text)
        page_count = max(1, (len(sources) + page_size - 1) // page_size)
        page = min(int(page_text), page_count)
        page_sources = sources[(page - 1) * page_size : page * page_size]
        rows = []
        for source in page_sources:
            mailbox = (
                source.get("mailbox", {})
                if isinstance(source.get("mailbox"), dict)
                else {}
            )
            username, password_mask = _source_credentials(get_project_root(), source)
            editable = (
                _source_fields(locale, source, username=username)
                if source["source_type"] == "mailbox_readonly"
                else [
                    {
                        "name": "display_name",
                        "type": "text",
                        "label": t("Source name", locale),
                        "required": True,
                        "max_length": 128,
                        "value": source["display_name"],
                    }
                ]
            )
            rows.append(
                {
                    "display_name": {"label": source["display_name"]},
                    "host": {"label": mailbox.get("host", "—")},
                    "folder": {"label": mailbox.get("folder", "—")},
                    "username": {"label": username if mailbox else "—"},
                    "masked_value": {"label": password_mask if mailbox else "—"},
                    "status": {
                        "checked": source["enabled"],
                        "label": t("Status", locale),
                        "field": "enabled",
                        "action_id": "rop_source_set_enabled",
                        "args": {"source_id": source["source_id"]},
                    },
                    "processed_total": {
                        "label": (
                            str(processed_totals.get(source["source_id"], 0))
                            if processed_totals is not None
                            else "—"
                        )
                    },
                    "actions": (
                        [
                            {
                                "action_id": "rop_source_check_connection",
                                "label": _connection_action_label(
                                    locale,
                                    health.get(source["source_id"]),
                                ),
                                "icon": _connection_action_icon(
                                    health.get(source["source_id"])
                                ),
                                "tone": _connection_action_tone(
                                    health.get(source["source_id"])
                                ),
                                "flow": "direct_execute",
                                "args": {"source_id": source["source_id"]},
                            }
                        ]
                        if source["source_type"] == "mailbox_readonly"
                        else []
                    )
                    + [
                        {
                            "action_id": "rop_source_update",
                            "label": t("Edit", locale),
                            "icon": "edit",
                            "flow": "direct_execute",
                            "inline_edit": True,
                            **(
                                {"pending_action_id": ("rop_source_check_connection")}
                                if source["source_type"] == "mailbox_readonly"
                                else {}
                            ),
                            "args": {"source_id": source["source_id"]},
                            "fields": editable,
                        },
                        {
                            "action_id": "rop_source_remove",
                            "label": t("Delete", locale),
                            "icon": "trash",
                            "flow": "direct_execute",
                            "confirmation": t("Delete", locale),
                            "args": {"source_id": source["source_id"]},
                        },
                    ],
                }
            )
        hidden = {"tab": "sources", "page_size": page_size_text}
        if query.get("lang"):
            hidden["lang"] = query["lang"]
        return [
            {
                "type": "data_table",
                "id": "rop-sources",
                "title": t("ROP sources", locale),
                "description": t(
                    "Configured ROP sources and their current processing status.",
                    locale,
                ),
                "toolbar": {
                    "hidden": hidden,
                    "fields": [
                        {
                            "name": "q",
                            "type": "text",
                            "label": t("Search", locale),
                            "value": query_text,
                        }
                    ],
                    "actions": [
                        {"href": "/rop/sources.csv", "label": t("Downloads", locale)},
                        {
                            "action_id": "rop_source_add",
                            "label": t("Add", locale),
                            "flow": "direct_execute",
                            "follow_up_action_id": "rop_source_check_connection",
                            "follow_up_match_arg": "source_id",
                            "fields": _source_fields(locale, adding=True),
                        },
                    ],
                },
                "columns": [
                    {
                        "key": "display_name",
                        "label": t("Source name", locale),
                        "cell": "text",
                    },
                    {
                        "key": "host",
                        "label": t("Mail server", locale),
                        "cell": "text",
                    },
                    {"key": "folder", "label": t("Folder", locale), "cell": "text"},
                    {"key": "username", "label": t("Username", locale), "cell": "text"},
                    {
                        "key": "masked_value",
                        "label": t("Password", locale),
                        "cell": "text",
                    },
                    {"key": "status", "label": t("Status", locale), "cell": "toggle"},
                    {
                        "key": "processed_total",
                        "label": t("Processed total", locale),
                        "cell": "text",
                    },
                    {"key": "actions", "label": "", "cell": "actions"},
                ],
                "rows": rows,
                "pagination": _blacklist_pagination(
                    {**query, "tab": "sources"},
                    page,
                    page_count,
                    page_size,
                    len(sources),
                    locale,
                ),
            }
        ]

    def get_modules_dashboard(self) -> AdapterResult | AdapterErrorResult:
        try:
            data = build_modules_list(self._storage_dir)
            return ok_result(data)
        except Exception as exc:
            return error_result_from_exception(exc)

    def get_rop_dashboard(
        self,
        tab: str = "overview",
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
            data = build_rop_tab_read_model(
                self._storage_dir,
                tab=tab,
                run_id=run_id,
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
                return error_result(
                    str(data.get("error") or "error"),
                    str(data.get("message") or "ROP read-model unavailable"),
                )
            if tab == "overview":
                data.setdefault("kpis", {})["available_source_count"] = (
                    _available_source_count(
                        get_project_root(), self._storage_dir, self._settings
                    )
                )
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
                        "blacklist",
                    }
                )
                if tab not in allowed_tabs:
                    tab = "overview"

                if tab == "blacklist":
                    locale = resolve_locale(query.get("lang"))
                    try:
                        entries = load_sender_blacklist_entries(self._storage_dir)
                    except SenderBlacklistError as exc:
                        return error_result("state_malformed", str(exc))
                    query_text = query.get("q", "").strip().lower()
                    if len(query_text) > 254:
                        return error_result("invalid_params", "Search query is invalid")
                    entries = [
                        entry for entry in entries if query_text in entry["email"]
                    ]
                    page_size = query.get("page_size", "25")
                    if page_size not in {"25", "50", "100"}:
                        return error_result("invalid_params", "Page size is invalid")
                    requested_page = query.get("page", "1")
                    if not requested_page.isdecimal() or int(requested_page) < 1:
                        return error_result("invalid_params", "Page is invalid")
                    page_size_int = int(page_size)
                    page_count = max(
                        1, (len(entries) + page_size_int - 1) // page_size_int
                    )
                    current_page = min(int(requested_page), page_count)
                    page_entries = entries[
                        (current_page - 1) * page_size_int : current_page
                        * page_size_int
                    ]
                    rows = [
                        {
                            "name": {"label": entry["name"]},
                            "title": {"label": entry["title"]},
                            "email": {"label": entry["email"]},
                            "role": {"label": entry["role"]},
                            "actions": [
                                {
                                    "action_id": "rop_sender_blacklist_update",
                                    "label": t("Edit", locale),
                                    "icon": "edit",
                                    "flow": "direct_execute",
                                    "inline_edit": True,
                                    "args": {"original_email": entry["email"]},
                                    "fields": _blacklist_fields(locale, entry),
                                },
                                {
                                    "action_id": "rop_sender_blacklist_remove",
                                    "label": t("Remove", locale),
                                    "icon": "trash",
                                    "flow": "direct_execute",
                                    "args": {"email": entry["email"]},
                                },
                            ],
                        }
                        for entry in page_entries
                    ]
                    return ok_result(
                        {
                            "layout": [
                                {
                                    "type": "data_table",
                                    "title": t("Sender blacklist", locale),
                                    "description": t(
                                        "All messages from these addresses will be sent to the Irrelevant classification.",
                                        locale,
                                    ),
                                    "id": "rop-blacklist",
                                    "toolbar": {
                                        "hidden": {
                                            "tab": "blacklist",
                                            "page_size": page_size,
                                            **(
                                                {"lang": query["lang"]}
                                                if query.get("lang")
                                                else {}
                                            ),
                                        },
                                        "fields": [
                                            {
                                                "name": "q",
                                                "type": "text",
                                                "label": t("Email", locale),
                                                "value": query_text,
                                                "placeholder": t("Search", locale),
                                            }
                                        ],
                                        "actions": [
                                            {
                                                "href": "/rop/blacklist.csv"
                                                + (
                                                    "?" + urlencode({"q": query_text})
                                                    if query_text
                                                    else ""
                                                ),
                                                "label": t("Downloads", locale),
                                            },
                                            {
                                                "action_id": "rop_sender_blacklist_add",
                                                "label": t("Add", locale),
                                                "flow": "direct_execute",
                                                "fields": _blacklist_fields(locale),
                                            },
                                        ],
                                    },
                                    "columns": [
                                        {
                                            "key": "name",
                                            "label": t("Name", locale),
                                            "cell": "text",
                                        },
                                        {
                                            "key": "title",
                                            "label": t("Title", locale),
                                            "cell": "text",
                                        },
                                        {
                                            "key": "email",
                                            "label": t("Email", locale),
                                            "cell": "text",
                                        },
                                        {
                                            "key": "role",
                                            "label": t("Role", locale),
                                            "cell": "text",
                                        },
                                        {
                                            "key": "actions",
                                            "label": "",
                                            "cell": "actions",
                                        },
                                    ],
                                    "rows": rows,
                                    "pagination": _blacklist_pagination(
                                        query,
                                        current_page,
                                        page_count,
                                        page_size_int,
                                        len(entries),
                                        locale,
                                    ),
                                }
                            ]
                        }
                    )

                if tab == "sources":
                    locale = resolve_locale(query.get("lang"))
                    try:
                        return ok_result(
                            {
                                "layout": self._sources_layout(query, locale),
                                "locale": locale,
                                "title": t("ROP sources", locale),
                            }
                        )
                    except RopSourcesError as exc:
                        return error_result("invalid_params", str(exc))

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
                filter_params, pagination_params, param_errors = (
                    extract_rop_query_params(query)
                )
                if param_errors:
                    return error_result(
                        "invalid_params",
                        "; ".join(param_errors),
                    )

                default_period = self._settings["rop"]["dashboard"]["default_period"]
                configured_periods = self._settings["rop"]["dashboard"]["periods"]
                data = build_rop_tab_read_model(
                    self._storage_dir,
                    tab=tab,
                    run_id=run_id,
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
                    return error_result(
                        str(data.get("error") or "error"),
                        str(data.get("message") or "ROP read-model unavailable"),
                    )

                locale = resolve_locale(query.get("lang"))
                if tab == "overview":
                    data.setdefault("kpis", {})["available_source_count"] = (
                        _available_source_count(
                            get_project_root(), self._storage_dir, self._settings
                        )
                    )
                data["rop_recommendations"] = normalize_rop_recommendation_hrefs(
                    data.get("rop_recommendations", []),
                    run_id=str(data.get("run_id", "")),
                    period=data.get("period"),
                    locale=locale,
                )
                data["locale"] = locale
                data["title"] = t("ROP Dashboard", locale)
                layout = build_rop_page_layout(data, tab=tab, locale=locale)
                return ok_result(
                    {
                        "layout": layout,
                        "locale": locale,
                        "title": data["title"],
                        "run_id": data.get("run_id"),
                        "selected_run_id": data.get("selected_run_id"),
                        "period": data.get("period"),
                    }
                )

            if page_id == "modules":
                locale = resolve_locale(query.get("lang"))
                modules_data = build_modules_list(self._storage_dir)
                modules_data["layout"] = build_modules_page_layout(
                    modules_data, locale=locale
                )
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
                filter_params, pagination_params, param_errors = (
                    extract_rop_query_params(query)
                )
                if param_errors:
                    return error_result("invalid_params", "; ".join(param_errors))
                data = build_rop_event_detail_page_model(
                    self._storage_dir,
                    run_id,
                    event_id,
                    event_instance_id=query.get("event_instance_id"),
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
            logger.exception("BeeAgent UI page adapter failed: page_id=%s", page_id)
            return error_result_from_exception(exc)


def _infer_mime(artifact_id: str) -> str:
    from beeagent_module.interfaces.ui.artifacts import get_artifact_content_type

    return get_artifact_content_type(artifact_id)
