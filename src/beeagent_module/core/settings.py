import os
import re
from pathlib import Path

import yaml

from beeagent_module.core.authorization import SCOPE_WILDCARD

REQUIRED_KEYS = (
    ("app", "name"),
    ("app", "env"),
    ("run", "mode"),
    ("web", "host"),
    ("web", "port"),
    ("web", "open_browser"),
    ("telegram", "enabled"),
    ("telegram", "bot_token_env"),
    ("telegram", "chat_id_env"),
    ("telegram", "telemetry_enabled"),
    ("logging", "clear_logs"),
    ("logging", "utc"),
    ("logging", "level"),
    ("mock", "seed"),
    ("mock", "weeks"),
    ("mock", "stores"),
    ("mock", "skus"),
    ("mock", "category"),
    ("data", "adapter"),
    ("scheduler", "enabled"),
    ("scheduler", "interval"),
    ("scheduler", "start_run"),
    ("approval", "reject_reason"),
    ("promo", "stock_min"),
    ("promo", "units_max"),
    ("i18n", "lang"),
    ("i18n", "path"),
    ("quiz", "enabled"),
    ("quiz", "path"),
    ("modules", "registry"),
    ("rop", "attachments", "enabled"),
    ("rop", "attachments", "chars_max"),
    ("rop", "attachments", "size_max"),
    ("rop", "attachments", "types"),
    ("rop", "attachments", "storage", "enabled"),
    ("rop", "attachments", "storage", "file_max"),
    ("rop", "attachments", "storage", "message_max"),
    ("rop", "attachments", "storage", "files_message_max"),
    ("rop", "attachments", "extraction", "engine"),
    ("rop", "attachments", "extraction", "chars_max"),
    ("rop", "attachments", "extraction", "pages_max"),
    ("rop", "attachments", "extraction", "timeout_seconds"),
    ("rop", "attachments", "extraction", "ocr_enabled"),
    ("rop", "ai_assist", "adjudicator", "attachment_chars_max"),
    ("rop", "email_preview", "body_chars_max"),
    ("rop", "sources"),
    ("rop", "dashboard", "default_period"),
    ("rop", "dashboard", "periods"),
    ("web", "auth", "enabled"),
    ("web", "auth", "mode"),
    ("web", "auth", "session_secret_env"),
    ("web", "auth", "principals"),
    ("ai", "prompts", "path"),
    ("ai", "prompts", "store"),
    ("ai", "profiles"),
    ("rop", "routing"),
    ("bitrix", "widget", "enabled"),
    ("bitrix", "widget", "token_env"),
    ("bitrix", "widget", "default_period"),
    ("bitrix", "widget", "max_items"),
    ("bitrix", "embedded_app", "enabled"),
    ("bitrix", "embedded_app", "portal_origin"),
    ("bitrix", "embedded_app", "default_role"),
    ("bitrix", "embedded_app", "request_timeout"),
)
_REQUIRED_ROP_ROUTING_QUEUES: tuple[str, ...] = (
    "sales",
    "tender",
    "logistics",
    "finance",
    "procurement",
    "manual_review",
)
_SUPPORTED_AI_PROVIDERS: frozenset[str] = frozenset(
    {"openai_responses", "openai_compatible"}
)
_ROP_AI_ADJUDICATOR_ENV = "BEEAGENT_ROP_AI_ADJUDICATOR_ENABLED"
_ENV_TRUE_VALUES: frozenset[str] = frozenset({"1", "true", "yes", "on", "enabled"})
_ENV_FALSE_VALUES: frozenset[str] = frozenset({"0", "false", "no", "off", "disabled"})

_HTTPS_ORIGIN_RE = re.compile(
    r"^https://[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?(?::[0-9]{1,5})?$"
)
_ALLOWED_EMBEDDED_ROLES: frozenset[str] = frozenset({"viewer", "operator", "admin"})
_EMBEDDED_REQUEST_TIMEOUT_MIN = 1
_EMBEDDED_REQUEST_TIMEOUT_MAX = 60


def is_valid_https_origin(value: str) -> bool:
    if not isinstance(value, str) or not value:
        return False
    return bool(_HTTPS_ORIGIN_RE.fullmatch(value))


def load_settings(settings_path: Path) -> dict:
    if not settings_path.exists():
        raise RuntimeError(f"Settings file not found: {settings_path}")

    with settings_path.open("r", encoding="utf-8") as file:
        content = yaml.safe_load(file)

    if not isinstance(content, dict):
        raise RuntimeError("Settings file must contain a top-level mapping")

    validate_settings(content)
    return content


def validate_settings(settings: dict) -> None:
    apply_runtime_settings_overrides(settings)
    missing_keys: list[str] = []

    for key_path in REQUIRED_KEYS:
        value = _get_nested_value(settings, key_path)
        if value is None:
            missing_keys.append(".".join(key_path))

    if missing_keys:
        missing_text = ", ".join(missing_keys)
        raise RuntimeError(f"Missing required settings keys: {missing_text}")

    if not isinstance(_get_nested_value(settings, ("app", "name")), str):
        raise RuntimeError("Invalid type for app.name, expected string")

    if not isinstance(_get_nested_value(settings, ("app", "env")), str):
        raise RuntimeError("Invalid type for app.env, expected string")

    if not isinstance(_get_nested_value(settings, ("run", "mode")), str):
        raise RuntimeError("Invalid type for run.mode, expected string")

    if not isinstance(_get_nested_value(settings, ("web", "host")), str):
        raise RuntimeError("Invalid type for web.host, expected string")

    web_port = _get_nested_value(settings, ("web", "port"))
    if not isinstance(web_port, int):
        raise RuntimeError("Invalid type for web.port, expected int")
    if web_port <= 0 or web_port > 65535:
        raise RuntimeError("Invalid value for web.port, expected 1..65535")

    if not isinstance(_get_nested_value(settings, ("web", "open_browser")), bool):
        raise RuntimeError("Invalid type for web.open_browser, expected bool")

    _validate_web_auth_settings(settings)

    if not isinstance(_get_nested_value(settings, ("telegram", "enabled")), bool):
        raise RuntimeError("Invalid type for telegram.enabled, expected bool")

    if not isinstance(_get_nested_value(settings, ("telegram", "bot_token_env")), str):
        raise RuntimeError("Invalid type for telegram.bot_token_env, expected string")

    if not isinstance(_get_nested_value(settings, ("telegram", "chat_id_env")), str):
        raise RuntimeError("Invalid type for telegram.chat_id_env, expected string")

    if not isinstance(
        _get_nested_value(settings, ("telegram", "telemetry_enabled")), bool
    ):
        raise RuntimeError("Invalid type for telegram.telemetry_enabled, expected bool")

    if not isinstance(_get_nested_value(settings, ("logging", "clear_logs")), bool):
        raise RuntimeError("Invalid type for logging.clear_logs, expected bool")

    if not isinstance(_get_nested_value(settings, ("logging", "utc")), bool):
        raise RuntimeError("Invalid type for logging.utc, expected bool")

    if not isinstance(_get_nested_value(settings, ("logging", "level")), str):
        raise RuntimeError("Invalid type for logging.level, expected string")

    if not isinstance(_get_nested_value(settings, ("mock", "seed")), int):
        raise RuntimeError("Invalid type for mock.seed, expected int")

    if not isinstance(_get_nested_value(settings, ("mock", "weeks")), int):
        raise RuntimeError("Invalid type for mock.weeks, expected int")

    if not isinstance(_get_nested_value(settings, ("mock", "stores")), int):
        raise RuntimeError("Invalid type for mock.stores, expected int")

    if not isinstance(_get_nested_value(settings, ("mock", "skus")), int):
        raise RuntimeError("Invalid type for mock.skus, expected int")

    if not isinstance(_get_nested_value(settings, ("mock", "category")), str):
        raise RuntimeError("Invalid type for mock.category, expected string")

    if not isinstance(_get_nested_value(settings, ("data", "adapter")), str):
        raise RuntimeError("Invalid type for data.adapter, expected string")

    adapter_name = _get_nested_value(settings, ("data", "adapter"))
    if adapter_name != "mock":
        raise RuntimeError("Unsupported data.adapter, expected 'mock'")

    dataset_id = _get_nested_value(settings, ("data", "mock", "dataset_id"))
    if dataset_id is not None and not isinstance(dataset_id, str):
        raise RuntimeError(
            "Invalid type for data.mock.dataset_id, expected string or null"
        )

    if not isinstance(_get_nested_value(settings, ("scheduler", "enabled")), bool):
        raise RuntimeError("Invalid type for scheduler.enabled, expected bool")

    interval = _get_nested_value(settings, ("scheduler", "interval"))
    if not isinstance(interval, int):
        raise RuntimeError("Invalid type for scheduler.interval, expected int")
    if interval <= 0:
        raise RuntimeError("Invalid value for scheduler.interval, expected > 0")

    if not isinstance(_get_nested_value(settings, ("scheduler", "start_run")), bool):
        raise RuntimeError("Invalid type for scheduler.start_run, expected bool")

    if not isinstance(_get_nested_value(settings, ("approval", "reject_reason")), str):
        raise RuntimeError("Invalid type for approval.reject_reason, expected string")

    promo_stock_min = _get_nested_value(settings, ("promo", "stock_min"))
    if not isinstance(promo_stock_min, int):
        raise RuntimeError("Invalid type for promo.stock_min, expected int")
    if promo_stock_min < 0:
        raise RuntimeError("Invalid value for promo.stock_min, expected >= 0")

    promo_units_max = _get_nested_value(settings, ("promo", "units_max"))
    if not isinstance(promo_units_max, int):
        raise RuntimeError("Invalid type for promo.units_max, expected int")
    if promo_units_max < 0:
        raise RuntimeError("Invalid value for promo.units_max, expected >= 0")

    if not isinstance(_get_nested_value(settings, ("i18n", "lang")), str):
        raise RuntimeError("Invalid type for i18n.lang, expected string")

    if not isinstance(_get_nested_value(settings, ("i18n", "path")), str):
        raise RuntimeError("Invalid type for i18n.path, expected string")

    if not isinstance(_get_nested_value(settings, ("quiz", "enabled")), bool):
        raise RuntimeError("Invalid type for quiz.enabled, expected bool")

    if not isinstance(_get_nested_value(settings, ("quiz", "path")), str):
        raise RuntimeError("Invalid type for quiz.path, expected string")

    registry = _get_nested_value(settings, ("modules", "registry"))
    if not isinstance(registry, list):
        raise RuntimeError("Invalid type for modules.registry, expected list")

    for idx, item in enumerate(registry):
        if not isinstance(item, dict):
            raise RuntimeError(
                f"Invalid type for modules.registry[{idx}], expected mapping"
            )
        for key in ("id", "package", "entry"):
            if not isinstance(item.get(key), str):
                raise RuntimeError(
                    f"Invalid or missing modules.registry[{idx}].{key}, expected string"
                )
        if not isinstance(item.get("enabled"), bool):
            raise RuntimeError(
                f"Invalid or missing modules.registry[{idx}].enabled, expected bool"
            )

    _validate_ai_prompts_settings(settings)
    _validate_ai_profiles_settings(settings)
    _validate_rop_email_preview_settings(settings)
    _validate_rop_ai_assist_settings(settings)
    _validate_rop_ai_adjudicator_settings(settings)
    _validate_rop_routing_settings(settings)

    mailbox_poll = _get_nested_value(settings, ("rop", "mailbox_poll"))
    if not isinstance(mailbox_poll, dict):
        raise RuntimeError("Invalid type for rop.mailbox_poll, expected mapping")
    if not isinstance(mailbox_poll.get("enabled"), bool):
        raise RuntimeError("Invalid type for rop.mailbox_poll.enabled, expected bool")
    if "all_sources" in mailbox_poll:
        raise RuntimeError("Unsupported rop.mailbox_poll.all_sources; use sources_all")
    poll_sources_all = mailbox_poll.get("sources_all", False)
    if not isinstance(poll_sources_all, bool):
        raise RuntimeError(
            "Invalid type for rop.mailbox_poll.sources_all, expected bool"
        )
    poll_source_id = mailbox_poll.get("source_id")
    if poll_sources_all is not True and (
        not isinstance(poll_source_id, str) or not poll_source_id.strip()
    ):
        raise RuntimeError(
            "Invalid rop.mailbox_poll.source_id, expected non-empty string"
        )

    input_sources = _get_nested_value(settings, ("rop", "sources"))
    if not isinstance(input_sources, list):
        raise RuntimeError("Invalid type for rop.sources, expected list")

    attachments_cfg = _get_nested_value(settings, ("rop", "attachments"))
    if not isinstance(attachments_cfg, dict):
        raise RuntimeError("Invalid type for rop.attachments, expected mapping")

    if not isinstance(attachments_cfg.get("enabled"), bool):
        raise RuntimeError("Invalid type for rop.attachments.enabled, expected bool")

    chars_max = attachments_cfg.get("chars_max")
    if not isinstance(chars_max, int) or chars_max <= 0:
        raise RuntimeError("Invalid rop.attachments.chars_max, expected int > 0")

    size_max = attachments_cfg.get("size_max")
    if not isinstance(size_max, int) or size_max <= 0:
        raise RuntimeError("Invalid rop.attachments.size_max, expected int > 0")

    allowed_types = attachments_cfg.get("types")
    if not isinstance(allowed_types, list) or not allowed_types:
        raise RuntimeError("Invalid rop.attachments.types, expected non-empty list")

    for idx, item in enumerate(allowed_types):
        if not isinstance(item, str) or not item.strip():
            raise RuntimeError(
                f"Invalid rop.attachments.types[{idx}], expected non-empty string"
            )

    storage_cfg = attachments_cfg.get("storage")
    if not isinstance(storage_cfg, dict):
        raise RuntimeError("Invalid type for rop.attachments.storage, expected mapping")
    if not isinstance(storage_cfg.get("enabled"), bool):
        raise RuntimeError(
            "Invalid type for rop.attachments.storage.enabled, expected bool"
        )
    for storage_key in (
        "file_max",
        "message_max",
        "files_message_max",
    ):
        storage_value = storage_cfg.get(storage_key)
        if not isinstance(storage_value, int) or storage_value <= 0:
            raise RuntimeError(
                f"Invalid rop.attachments.storage.{storage_key}, expected int > 0"
            )
    if (
        attachments_cfg.get("enabled") is True
        and storage_cfg.get("enabled") is not True
    ):
        raise RuntimeError(
            "rop.attachments.enabled=true requires rop.attachments.storage.enabled=true; "
            "local document extraction reads files from the attachment store"
        )

    extraction_cfg = attachments_cfg.get("extraction")
    if not isinstance(extraction_cfg, dict):
        raise RuntimeError(
            "Invalid type for rop.attachments.extraction, expected mapping"
        )
    extraction_engine = extraction_cfg.get("engine")
    if not isinstance(extraction_engine, str) or not extraction_engine.strip():
        raise RuntimeError(
            "Invalid rop.attachments.extraction.engine, expected non-empty string"
        )
    if extraction_engine != "docling":
        raise RuntimeError(
            "Unsupported rop.attachments.extraction.engine, expected 'docling'"
        )
    for extraction_key in ("chars_max", "pages_max", "timeout_seconds"):
        extraction_value = extraction_cfg.get(extraction_key)
        if not isinstance(extraction_value, int) or extraction_value <= 0:
            raise RuntimeError(
                f"Invalid rop.attachments.extraction.{extraction_key}, expected int > 0"
            )
    if not isinstance(extraction_cfg.get("ocr_enabled"), bool):
        raise RuntimeError(
            "Invalid type for rop.attachments.extraction.ocr_enabled, expected bool"
        )

    extraction_chars_max = extraction_cfg.get("chars_max")
    adjudicator_cfg = _get_nested_value(settings, ("rop", "ai_assist", "adjudicator"))
    adjudicator_attachment_chars_max = (
        adjudicator_cfg.get("attachment_chars_max")
        if isinstance(adjudicator_cfg, dict)
        else None
    )
    if (
        isinstance(adjudicator_attachment_chars_max, int)
        and adjudicator_attachment_chars_max > 0
    ):
        if chars_max > adjudicator_attachment_chars_max:
            raise RuntimeError(
                "Invalid rop.attachments.chars_max: expected "
                "attachments.chars_max <= ai_assist.adjudicator.attachment_chars_max"
            )
        if adjudicator_attachment_chars_max > extraction_chars_max:
            raise RuntimeError(
                "Invalid rop.ai_assist.adjudicator.attachment_chars_max: expected "
                "attachment_chars_max <= attachments.extraction.chars_max"
            )

    _VALID_SOURCE_TYPES = {"json_batch", "mailbox_readonly"}
    _VALID_AUTHORITY_VALUES = {"read_only", "draft_only", "execution_capable"}

    for idx, source in enumerate(input_sources):
        if not isinstance(source, dict):
            raise RuntimeError(f"Invalid type for rop.sources[{idx}], expected mapping")
        for key in (
            "source_id",
            "source_type",
            "source_role",
            "client_id",
            "display_name",
            "authority",
        ):
            value = source.get(key)
            if not isinstance(value, str) or not value.strip():
                raise RuntimeError(
                    f"Invalid or missing rop.sources[{idx}].{key}, expected non-empty string"
                )
        if not isinstance(source.get("enabled"), bool):
            raise RuntimeError(
                f"Invalid or missing rop.sources[{idx}].enabled, expected bool"
            )
        items_max = source.get("items_max")
        if not isinstance(items_max, int) or items_max <= 0:
            raise RuntimeError(
                f"Invalid or missing rop.sources[{idx}].items_max, expected int > 0"
            )
        source_type = source.get("source_type", "")
        if source_type not in _VALID_SOURCE_TYPES:
            raise RuntimeError(
                f"Unsupported rop.sources[{idx}].source_type '{source_type}', "
                f"expected one of: {sorted(_VALID_SOURCE_TYPES)}"
            )
        if source.get("authority") not in _VALID_AUTHORITY_VALUES:
            raise RuntimeError(
                f"Invalid rop.sources[{idx}].authority, "
                f"expected one of: {sorted(_VALID_AUTHORITY_VALUES)}"
            )
        if source_type == "json_batch":
            batch = source.get("batch")
            if not isinstance(batch, dict):
                raise RuntimeError(
                    f"Missing or invalid rop.sources[{idx}].batch, expected mapping"
                )
            if not isinstance(batch.get("path"), str):
                raise RuntimeError(
                    f"Missing rop.sources[{idx}].batch.path, expected string"
                )
            if not isinstance(batch.get("period"), str):
                raise RuntimeError(
                    f"Missing rop.sources[{idx}].batch.period, expected string"
                )
        if source_type == "mailbox_readonly":
            if source.get("authority") != "read_only":
                raise RuntimeError(
                    f"Invalid rop.sources[{idx}].authority for mailbox_readonly, expected 'read_only'"
                )
            mailbox = source.get("mailbox")
            if not isinstance(mailbox, dict):
                raise RuntimeError(
                    f"Missing or invalid rop.sources[{idx}].mailbox, expected mapping"
                )
            host = mailbox.get("host")
            host_env = mailbox.get("host_env")
            has_host_env = isinstance(host_env, str) and bool(host_env)
            has_host = isinstance(host, str) and bool(host)
            if not (has_host_env or has_host):
                raise RuntimeError(
                    f"Missing rop.sources[{idx}].mailbox.host_env or rop.sources[{idx}].mailbox.host, expected non-empty string"
                )
            folder = mailbox.get("folder")
            folder_env = mailbox.get("folder_env")
            has_folder_env = isinstance(folder_env, str) and bool(folder_env)
            has_folder = isinstance(folder, str) and bool(folder)
            if not (has_folder_env or has_folder):
                raise RuntimeError(
                    f"Missing rop.sources[{idx}].mailbox.folder_env or rop.sources[{idx}].mailbox.folder, expected non-empty string"
                )
            for key in ("username_env", "password_env"):
                value = mailbox.get(key)
                if not isinstance(value, str) or not value:
                    raise RuntimeError(
                        f"Missing rop.sources[{idx}].mailbox.{key}, expected non-empty string"
                    )
            port = mailbox.get("port")
            if not isinstance(port, int) or port <= 0:
                raise RuntimeError(
                    f"Missing or invalid rop.sources[{idx}].mailbox.port, expected int > 0"
                )
            if not isinstance(mailbox.get("use_ssl"), bool):
                raise RuntimeError(
                    f"Missing or invalid rop.sources[{idx}].mailbox.use_ssl, expected bool"
                )
        routing = source.get("routing")
        if routing is not None:
            if not isinstance(routing, dict):
                raise RuntimeError(
                    f"Invalid type for rop.sources[{idx}].routing, expected mapping"
                )
            unsupported_routing_keys = sorted(set(routing) - {"email_recipient"})
            if unsupported_routing_keys:
                raise RuntimeError(
                    f"Unsupported rop.sources[{idx}].routing keys: "
                    + ", ".join(unsupported_routing_keys)
                )
            email_recipient = routing.get("email_recipient")
            if email_recipient is not None:
                if not isinstance(email_recipient, str) or not email_recipient.strip():
                    raise RuntimeError(
                        f"Invalid or missing rop.sources[{idx}].routing.email_recipient, expected non-empty string"
                    )
                if not _is_single_plain_email(email_recipient):
                    raise RuntimeError(
                        f"Invalid rop.sources[{idx}].routing.email_recipient, expected a single email address"
                    )

    if mailbox_poll["enabled"]:
        if poll_sources_all is True:
            mailbox_sources = [
                source
                for source in input_sources
                if source.get("enabled") is True
                and source.get("source_type") == "mailbox_readonly"
                and source.get("authority") == "read_only"
            ]
            if not mailbox_sources:
                raise RuntimeError(
                    "rop.mailbox_poll.sources_all requires at least one enabled "
                    "read_only mailbox_readonly source in rop.sources"
                )
        else:
            poll_source = next(
                (
                    source
                    for source in input_sources
                    if source.get("source_id") == poll_source_id
                ),
                None,
            )
            if poll_source is None:
                raise RuntimeError(
                    "rop.mailbox_poll.source_id not found in rop.sources"
                )
            if poll_source.get("enabled") is not True:
                raise RuntimeError("rop.mailbox_poll source must be enabled")
            if poll_source.get("source_type") != "mailbox_readonly":
                raise RuntimeError("rop.mailbox_poll source must be mailbox_readonly")
            if poll_source.get("authority") != "read_only":
                raise RuntimeError(
                    "rop.mailbox_poll source authority must be read_only"
                )

    _validate_rop_dashboard_settings(settings)

    _validate_bitrix_settings(settings)
    _validate_bitrix_widget_settings(settings)
    _validate_bitrix_embedded_app_settings(settings)

    _validate_web_auth_settings(settings)


def _is_single_plain_email(value: str) -> bool:
    if value != value.strip() or any(ch.isspace() for ch in value):
        return False
    if "," in value or ";" in value or value.count("@") != 1:
        return False
    local, domain = value.split("@")
    return bool(local and domain)


def apply_runtime_settings_overrides(settings: dict) -> dict:
    _apply_rop_ai_adjudicator_env_override(settings)
    return settings


def get_rop_ai_adjudicator_runtime_state(settings: dict) -> dict[str, bool]:
    apply_runtime_settings_overrides(settings)
    adj_cfg = _get_nested_value(settings, ("rop", "ai_assist", "adjudicator"))
    if not isinstance(adj_cfg, dict):
        return {
            "enabled": False,
            "env_override_present": False,
            "yaml_enabled": False,
        }
    return {
        "enabled": adj_cfg.get("enabled") is True,
        "env_override_present": bool(adj_cfg.get("_env_override_present", False)),
        "yaml_enabled": adj_cfg.get("_yaml_enabled", False) is True,
    }


def _validate_web_auth_settings(settings: dict) -> None:
    web_auth = _get_nested_value(settings, ("web", "auth"))
    if web_auth is None:
        return
    if not isinstance(web_auth, dict):
        raise RuntimeError("Invalid type for web.auth, expected mapping")

    enabled = web_auth.get("enabled")
    if not isinstance(enabled, bool):
        raise RuntimeError("Invalid type for web.auth.enabled, expected bool")

    mode = web_auth.get("mode")
    if not isinstance(mode, str) or not mode.strip():
        raise RuntimeError(
            "Invalid or missing web.auth.mode, expected non-empty string"
        )
    if mode != "beeui_session":
        raise RuntimeError("Unsupported web.auth.mode, expected 'beeui_session'")

    session_secret_env = web_auth.get("session_secret_env")
    if not isinstance(session_secret_env, str) or not session_secret_env.strip():
        raise RuntimeError(
            "Invalid or missing web.auth.session_secret_env, expected non-empty string"
        )

    principals = web_auth.get("principals")
    if not isinstance(principals, list):
        raise RuntimeError("Invalid type for web.auth.principals, expected list")

    host = str(_get_nested_value(settings, ("web", "host")) or "").strip().lower()
    is_loopback = host == "localhost"
    if not is_loopback:
        try:
            import ipaddress

            is_loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            is_loopback = False

    if not enabled and not is_loopback:
        raise RuntimeError(
            "Unsafe web.auth config: web.auth.enabled=false is allowed only "
            "for loopback web.host"
        )

    _ALLOWED_ROLES = frozenset({"viewer", "operator", "admin"})
    _SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_]+$")
    _SAFE_SCOPE_RE = re.compile(r"^[a-z][a-z0-9_-]*$")

    if enabled:
        session_secret = os.getenv(session_secret_env, "")
        if not session_secret:
            raise RuntimeError(
                f"Missing required env var '{session_secret_env}' "
                f"for web.auth.session_secret_env when web.auth.enabled=true"
            )

        if not principals:
            raise RuntimeError(
                "web.auth.principals must be non-empty when web.auth.enabled=true"
            )

        seen_ids: list[str] = []
        seen_usernames: list[str] = []
        seen_token_envs: list[str] = []
        seen_token_values: list[str] = []

        for idx, principal in enumerate(principals):
            if not isinstance(principal, dict):
                raise RuntimeError(
                    f"Invalid type for web.auth.principals[{idx}], expected mapping"
                )

            principal_id = principal.get("id")
            if not isinstance(principal_id, str) or not _SAFE_ID_RE.match(principal_id):
                raise RuntimeError(
                    f"Invalid web.auth.principals[{idx}].id, "
                    f"expected non-empty alphanumeric string"
                )

            username = principal.get("username")
            if not isinstance(username, str) or not _SAFE_ID_RE.match(username):
                raise RuntimeError(
                    f"Invalid web.auth.principals[{idx}].username, "
                    f"expected non-empty alphanumeric string"
                )

            role = principal.get("role")
            if not isinstance(role, str) or role not in _ALLOWED_ROLES:
                raise RuntimeError(
                    f"Invalid web.auth.principals[{idx}].role '{role}', "
                    f"expected one of: {sorted(_ALLOWED_ROLES)}"
                )

            token_env = principal.get("token_env")
            if not isinstance(token_env, str) or not token_env.strip():
                raise RuntimeError(
                    f"Invalid or missing web.auth.principals[{idx}].token_env, "
                    f"expected non-empty string"
                )

            token_value = os.getenv(token_env, "")
            if not token_value:
                raise RuntimeError(
                    f"Missing required env var '{token_env}' "
                    f"for web.auth.principals[{idx}].token_env "
                    f"when web.auth.enabled=true"
                )

            scopes = principal.get("scopes")
            if not isinstance(scopes, list) or not scopes:
                raise RuntimeError(
                    f"Invalid or missing web.auth.principals[{idx}].scopes, "
                    f"expected non-empty list"
                )
            seen_scopes: list[str] = []
            for scope_idx, scope in enumerate(scopes):
                if not isinstance(scope, str) or (
                    scope != SCOPE_WILDCARD and not _SAFE_SCOPE_RE.fullmatch(scope)
                ):
                    raise RuntimeError(
                        f"Invalid web.auth.principals[{idx}].scopes[{scope_idx}] "
                        f"'{scope}', expected safe lowercase scope identifier or '*'"
                    )
                if scope in seen_scopes:
                    raise RuntimeError(
                        f"Duplicate web.auth.principals[{idx}].scopes '{scope}'"
                    )
                seen_scopes.append(scope)
            scope_set = frozenset(scopes)
            if SCOPE_WILDCARD in scope_set and scope_set != {SCOPE_WILDCARD}:
                raise RuntimeError(
                    f"Invalid web.auth.principals[{idx}].scopes, "
                    f"wildcard '{SCOPE_WILDCARD}' must be the only scope"
                )

            if principal_id in seen_ids:
                raise RuntimeError(f"Duplicate web.auth.principals id '{principal_id}'")
            seen_ids.append(principal_id)

            if username in seen_usernames:
                raise RuntimeError(
                    f"Duplicate web.auth.principals username '{username}'"
                )
            seen_usernames.append(username)

            if token_env in seen_token_envs:
                raise RuntimeError(
                    f"Duplicate web.auth.principals token_env '{token_env}'"
                )
            seen_token_envs.append(token_env)

            if token_value in seen_token_values:
                raise RuntimeError(
                    f"Duplicate resolved token value for web.auth.principals[{idx}]"
                )
            seen_token_values.append(token_value)


def _validate_rop_email_preview_settings(settings: dict) -> None:
    preview_cfg = _get_nested_value(settings, ("rop", "email_preview"))
    if preview_cfg is None:
        return
    if not isinstance(preview_cfg, dict):
        raise RuntimeError("Invalid type for rop.email_preview, expected mapping")

    body_chars_max = preview_cfg.get("body_chars_max")
    if not isinstance(body_chars_max, int):
        raise RuntimeError(
            "Invalid type for rop.email_preview.body_chars_max, expected int"
        )
    if body_chars_max < 200:
        raise RuntimeError(
            "Invalid value for rop.email_preview.body_chars_max, expected >= 200"
        )
    if body_chars_max > 10000:
        raise RuntimeError(
            "Invalid value for rop.email_preview.body_chars_max, hard cap is 10000"
        )


def _validate_ai_prompts_settings(settings: dict) -> None:
    prompts_cfg = _get_nested_value(settings, ("ai", "prompts"))
    if not isinstance(prompts_cfg, dict):
        raise RuntimeError("Invalid type for ai.prompts, expected mapping")

    prompts_path = prompts_cfg.get("path")
    if not isinstance(prompts_path, str) or not prompts_path.strip():
        raise RuntimeError(
            "Invalid or missing ai.prompts.path, expected non-empty string"
        )

    if not Path(prompts_path).exists():
        raise RuntimeError(f"Prompts file not found: {prompts_path}")

    if not isinstance(prompts_cfg.get("store"), bool):
        raise RuntimeError("Invalid type for ai.prompts.store, expected bool")


def _validate_ai_profiles_settings(settings: dict) -> None:
    profiles_cfg = _get_nested_value(settings, ("ai", "profiles"))
    if not isinstance(profiles_cfg, dict) or not profiles_cfg:
        raise RuntimeError("Invalid or missing ai.profiles, expected non-empty mapping")

    for profile_name, profile_cfg in profiles_cfg.items():
        if not isinstance(profile_cfg, dict):
            raise RuntimeError(
                f"Invalid type for ai.profiles.{profile_name}, expected mapping"
            )

        if not isinstance(profile_cfg.get("enabled"), bool):
            raise RuntimeError(
                f"Invalid type for ai.profiles.{profile_name}.enabled, expected bool"
            )

        provider = profile_cfg.get("provider")
        if not isinstance(provider, str) or not provider.strip():
            raise RuntimeError(
                f"Invalid or missing ai.profiles.{profile_name}.provider, expected non-empty string"
            )
        if provider not in _SUPPORTED_AI_PROVIDERS:
            raise RuntimeError(
                f"Unsupported ai.profiles.{profile_name}.provider '{provider}', expected one of: {sorted(_SUPPORTED_AI_PROVIDERS)}"
            )

        for key in ("api_key_env", "base_url", "model"):
            value = profile_cfg.get(key)
            if not isinstance(value, str):
                raise RuntimeError(
                    f"Invalid type for ai.profiles.{profile_name}.{key}, expected string"
                )


def _require_one_enabled_ai_profile(
    settings: dict,
    *,
    reason: str,
    require_api_key: bool,
) -> dict:
    profiles_cfg = _get_nested_value(settings, ("ai", "profiles"))
    if not isinstance(profiles_cfg, dict) or not profiles_cfg:
        raise RuntimeError("Invalid or missing ai.profiles, expected non-empty mapping")

    enabled_profiles = [
        (profile_name, profile_cfg)
        for profile_name, profile_cfg in profiles_cfg.items()
        if isinstance(profile_cfg, dict) and profile_cfg.get("enabled") is True
    ]
    if len(enabled_profiles) != 1:
        raise RuntimeError(
            f"Exactly one ai.profiles.*.enabled must be true when {reason}"
        )

    profile_name, profile_cfg = enabled_profiles[0]
    for key in ("provider", "api_key_env", "base_url", "model"):
        value = profile_cfg.get(key)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(
                f"Invalid or missing ai.profiles.{profile_name}.{key}, expected non-empty string when {reason}"
            )

    if require_api_key:
        api_key_env = profile_cfg["api_key_env"]
        if not os.getenv(api_key_env, "").strip():
            raise RuntimeError(
                f"Missing required env var '{api_key_env}' when {reason}"
            )

    return profile_cfg


def _validate_rop_ai_assist_settings(settings: dict) -> None:
    ai_cfg = _get_nested_value(settings, ("rop", "ai_assist"))
    if ai_cfg is None:
        return
    if not isinstance(ai_cfg, dict):
        raise RuntimeError("Invalid type for rop.ai_assist, expected mapping")

    old_keys = {
        "max_events_per_run",
        "request_timeout_seconds",
        "min_ai_confidence",
    }
    found_old_keys = sorted(old_keys.intersection(ai_cfg))
    if found_old_keys:
        raise RuntimeError(
            "Unsupported old rop.ai_assist config keys: " + ", ".join(found_old_keys)
        )

    unsupported_transport_keys = {
        "provider",
        "model_env",
        "api_key_env",
        "base_url_env",
    }
    found_transport_keys = sorted(unsupported_transport_keys.intersection(ai_cfg))
    if found_transport_keys:
        raise RuntimeError(
            "Unsupported top-level rop.ai_assist transport keys: "
            + ", ".join(found_transport_keys)
        )

    if not isinstance(ai_cfg.get("enabled"), bool):
        raise RuntimeError("Invalid type for rop.ai_assist.enabled, expected bool")

    events_max = ai_cfg.get("events_max")
    if not isinstance(events_max, int) or events_max <= 0:
        raise RuntimeError("Invalid rop.ai_assist.events_max, expected int > 0")

    request_timeout = ai_cfg.get("request_timeout")
    if not isinstance(request_timeout, int) or request_timeout <= 0:
        raise RuntimeError("Invalid rop.ai_assist.request_timeout, expected int > 0")

    ai_confidence_min = ai_cfg.get("ai_confidence_min")
    if not isinstance(ai_confidence_min, (int, float)):
        raise RuntimeError("Invalid rop.ai_assist.ai_confidence_min, expected float")
    if ai_confidence_min < 0.0 or ai_confidence_min > 1.0:
        raise RuntimeError("Invalid rop.ai_assist.ai_confidence_min, expected 0.0..1.0")

    dry_run = ai_cfg.get("dry_run")
    if not isinstance(dry_run, bool):
        raise RuntimeError("Invalid type for rop.ai_assist.dry_run, expected bool")

    adjudicator_state = get_rop_ai_adjudicator_runtime_state(settings)
    legacy_ai_assist_requested = bool(
        ai_cfg.get("enabled")
        and not adjudicator_state["enabled"]
        and not adjudicator_state["env_override_present"]
        and not adjudicator_state["yaml_enabled"]
    )
    if legacy_ai_assist_requested:
        _require_one_enabled_ai_profile(
            settings,
            reason="rop.ai_assist.enabled=true",
            require_api_key=not dry_run,
        )


_ALLOWED_DASHBOARD_PERIODS: frozenset[str] = frozenset(
    {
        "today",
        "yesterday",
        "7d",
        "30d",
        "90d",
        "365d",
        "all",
    }
)


def _validate_rop_dashboard_settings(settings: dict) -> None:
    dash_cfg = _get_nested_value(settings, ("rop", "dashboard"))
    if dash_cfg is None:
        return
    if not isinstance(dash_cfg, dict):
        raise RuntimeError("Invalid type for rop.dashboard, expected mapping")

    default_period = dash_cfg.get("default_period")
    if not isinstance(default_period, str) or not default_period.strip():
        raise RuntimeError(
            "Invalid or missing rop.dashboard.default_period, expected non-empty string"
        )
    if default_period not in _ALLOWED_DASHBOARD_PERIODS:
        raise RuntimeError(
            f"Invalid rop.dashboard.default_period '{default_period}', "
            f"expected one of: {sorted(_ALLOWED_DASHBOARD_PERIODS)}"
        )

    periods = dash_cfg.get("periods")
    if not isinstance(periods, list) or not periods:
        raise RuntimeError(
            "Invalid or missing rop.dashboard.periods, expected non-empty list"
        )
    for idx, period in enumerate(periods):
        if not isinstance(period, str) or period not in _ALLOWED_DASHBOARD_PERIODS:
            raise RuntimeError(
                f"Invalid rop.dashboard.periods[{idx}] '{period}', "
                f"expected one of: {sorted(_ALLOWED_DASHBOARD_PERIODS)}"
            )

    if default_period not in periods:
        raise RuntimeError(
            f"rop.dashboard.default_period '{default_period}' must be "
            f"included in rop.dashboard.periods"
        )


def _validate_bitrix_settings(settings: dict) -> None:
    bitrix_cfg = _get_nested_value(settings, ("bitrix",))
    if bitrix_cfg is None:
        return
    if not isinstance(bitrix_cfg, dict):
        raise RuntimeError("Invalid type for bitrix, expected mapping")

    old_keys = {
        "webhook_url_env",
        "timeout_seconds",
        "max_pages",
        "entity_types",
    }
    old_recon_keys = {"date_window_days"}
    found_old_keys = sorted(old_keys.intersection(bitrix_cfg))
    if found_old_keys:
        raise RuntimeError(
            "Unsupported old bitrix config keys: " + ", ".join(found_old_keys)
        )

    if not isinstance(bitrix_cfg.get("enabled"), bool):
        raise RuntimeError("Invalid type for bitrix.enabled, expected bool")

    webhook_env = bitrix_cfg.get("webhook_env")
    if not isinstance(webhook_env, str) or not webhook_env.strip():
        raise RuntimeError(
            "Invalid or missing bitrix.webhook_env, expected non-empty string"
        )

    timeout = bitrix_cfg.get("timeout")
    if not isinstance(timeout, int) or timeout <= 0:
        raise RuntimeError("Invalid bitrix.timeout, expected int > 0")

    page_size = bitrix_cfg.get("page_size")
    if not isinstance(page_size, int) or page_size <= 0:
        raise RuntimeError("Invalid bitrix.page_size, expected int > 0")

    pages_max = bitrix_cfg.get("pages_max")
    if not isinstance(pages_max, int) or pages_max <= 0:
        raise RuntimeError("Invalid bitrix.pages_max, expected int > 0")

    entity_types = bitrix_cfg.get("types_entity")
    if not isinstance(entity_types, list) or not entity_types:
        raise RuntimeError("Invalid bitrix.types_entity, expected non-empty list")
    valid_entity_types = {1, 2, 3, 4}
    for idx, et in enumerate(entity_types):
        if not isinstance(et, int) or et not in valid_entity_types:
            raise RuntimeError(
                f"Invalid bitrix.types_entity[{idx}], expected one of "
                f"{sorted(valid_entity_types)}"
            )

    recon_cfg = bitrix_cfg.get("reconciliation")
    if not isinstance(recon_cfg, dict):
        raise RuntimeError("Invalid type for bitrix.reconciliation, expected mapping")
    found_old_recon_keys = sorted(old_recon_keys.intersection(recon_cfg))
    if found_old_recon_keys:
        raise RuntimeError(
            "Unsupported old bitrix.reconciliation config keys: "
            + ", ".join(found_old_recon_keys)
        )

    if not isinstance(recon_cfg.get("enabled"), bool):
        raise RuntimeError(
            "Invalid type for bitrix.reconciliation.enabled, expected bool"
        )
    if recon_cfg.get("enabled") and not bitrix_cfg.get("enabled"):
        raise RuntimeError(
            "Invalid bitrix config: bitrix.reconciliation.enabled requires "
            "bitrix.enabled: true"
        )

    candidate_limit = recon_cfg.get("candidate_limit")
    if not isinstance(candidate_limit, int) or candidate_limit <= 0:
        raise RuntimeError(
            "Invalid bitrix.reconciliation.candidate_limit, expected int > 0"
        )

    window_date = recon_cfg.get("window_date")
    if not isinstance(window_date, int) or window_date <= 0:
        raise RuntimeError(
            "Invalid bitrix.reconciliation.window_date, expected int > 0"
        )

    corr_cfg = recon_cfg.get("correlation")
    if not isinstance(corr_cfg, dict):
        raise RuntimeError(
            "Invalid or missing bitrix.reconciliation.correlation, expected mapping"
        )
    if not isinstance(corr_cfg.get("enabled"), bool):
        raise RuntimeError(
            "Invalid type for bitrix.reconciliation.correlation.enabled, expected bool"
        )
    corr_window_days = corr_cfg.get("window_days")
    if (
        not isinstance(corr_window_days, int)
        or isinstance(corr_window_days, bool)
        or corr_window_days <= 0
    ):
        raise RuntimeError(
            "Invalid bitrix.reconciliation.correlation.window_days, expected int > 0"
        )

    writeback_cfg = bitrix_cfg.get("writeback")
    if writeback_cfg is not None:
        if not isinstance(writeback_cfg, dict):
            raise RuntimeError("Invalid type for bitrix.writeback, expected mapping")
        if not isinstance(writeback_cfg.get("enabled"), bool):
            raise RuntimeError(
                "Invalid type for bitrix.writeback.enabled, expected bool"
            )
        writeback_env = writeback_cfg.get("webhook_env")
        if not isinstance(writeback_env, str) or not writeback_env.strip():
            raise RuntimeError(
                "Invalid or missing bitrix.writeback.webhook_env, "
                "expected non-empty string"
            )
        writeback_timeout = writeback_cfg.get("timeout")
        if not isinstance(writeback_timeout, int) or writeback_timeout <= 0:
            raise RuntimeError("Invalid bitrix.writeback.timeout, expected int > 0")
        if "retry_attempts_max" in writeback_cfg:
            raise RuntimeError(
                "Unsupported bitrix.writeback.retry_attempts_max; "
                "use bitrix.writeback.attempts_retry_max"
            )
        attempts_retry_max = writeback_cfg.get("attempts_retry_max")
        if not isinstance(attempts_retry_max, int) or attempts_retry_max <= 0:
            raise RuntimeError(
                "Invalid bitrix.writeback.attempts_retry_max, expected int > 0"
            )
        if not isinstance(writeback_cfg.get("dry_run"), bool):
            raise RuntimeError(
                "Invalid type for bitrix.writeback.dry_run, expected bool"
            )
        if "attach_email" in writeback_cfg:
            raise RuntimeError(
                "Unsupported bitrix.writeback.attach_email; "
                "use bitrix.writeback.email_attach"
            )
        email_attach = writeback_cfg.get("email_attach")
        if not isinstance(email_attach, bool):
            raise RuntimeError(
                "Invalid type for bitrix.writeback.email_attach, expected bool"
            )
        file_attach = writeback_cfg.get("file_attach")
        if not isinstance(file_attach, bool):
            raise RuntimeError(
                "Invalid type for bitrix.writeback.file_attach, expected bool"
            )
        if "email_attach_completed" in writeback_cfg:
            raise RuntimeError(
                "Unsupported bitrix.writeback.email_attach_completed; "
                "use bitrix.writeback.email_completed"
            )
        if "email_activity_completed" in writeback_cfg:
            raise RuntimeError(
                "Unsupported bitrix.writeback.email_activity_completed; "
                "use bitrix.writeback.email_completed"
            )
        email_completed = writeback_cfg.get("email_completed")
        if email_completed is not None and not isinstance(email_completed, bool):
            raise RuntimeError(
                "Invalid bitrix.writeback.email_completed, expected boolean"
            )
        source_id_value = writeback_cfg.get("source_id")
        if source_id_value is not None and not isinstance(source_id_value, str):
            raise RuntimeError(
                "Invalid type for bitrix.writeback.source_id, expected string or null"
            )
        if "fallback_responsible_user_id" in writeback_cfg:
            raise RuntimeError(
                "Unsupported bitrix.writeback.fallback_responsible_user_id; "
                "use bitrix.writeback.user_id_fallback"
            )
        fallback_id = writeback_cfg.get("user_id_fallback")
        if fallback_id is not None:
            if (
                isinstance(fallback_id, bool)
                or not isinstance(fallback_id, int)
                or fallback_id <= 0
            ):
                raise RuntimeError(
                    "Invalid bitrix.writeback.user_id_fallback, "
                    "expected positive int or null"
                )
        stages_cfg = writeback_cfg.get("stages")
        if not isinstance(stages_cfg, dict):
            raise RuntimeError(
                "Invalid type for bitrix.writeback.stages, expected mapping"
            )
        unsupported_stage_keys = sorted(set(stages_cfg) - {"new_lead", "irrelevant"})
        if unsupported_stage_keys:
            raise RuntimeError(
                "Unsupported bitrix.writeback.stages keys: "
                + ", ".join(unsupported_stage_keys)
            )
        if writeback_cfg.get("enabled"):
            if writeback_env.strip() == webhook_env.strip():
                raise RuntimeError(
                    "bitrix.writeback.webhook_env must differ from "
                    "bitrix.webhook_env when bitrix.writeback.enabled=true"
                )
            if not bitrix_cfg.get("enabled"):
                raise RuntimeError(
                    "Invalid bitrix config: bitrix.writeback.enabled requires "
                    "bitrix.enabled: true"
                )
            if not recon_cfg.get("enabled"):
                raise RuntimeError(
                    "Invalid bitrix config: bitrix.writeback.enabled requires "
                    "bitrix.reconciliation.enabled: true"
                )
            for stage_key in ("new_lead", "irrelevant"):
                stage_value = stages_cfg.get(stage_key)
                if not isinstance(stage_value, str) or not stage_value.strip():
                    raise RuntimeError(
                        f"Invalid bitrix.writeback.stages.{stage_key}, "
                        "expected non-empty string when "
                        "bitrix.writeback.enabled=true"
                    )
            if not os.environ.get(writeback_env):
                raise RuntimeError(
                    f"Missing required env var '{writeback_env}' for "
                    "bitrix.writeback.webhook_env when bitrix.writeback.enabled=true"
                )
            read_webhook_url = os.environ.get(webhook_env, "").rstrip("/")
            write_webhook_url = os.environ.get(writeback_env, "").rstrip("/")
            if read_webhook_url and read_webhook_url == write_webhook_url:
                raise RuntimeError(
                    "Bitrix read and write webhook credentials must be distinct "
                    "when bitrix.writeback.enabled=true"
                )


def _validate_rop_routing_settings(settings: dict) -> None:
    routing_cfg = _get_nested_value(settings, ("rop", "routing"))
    if routing_cfg is None:
        return
    if not isinstance(routing_cfg, dict):
        raise RuntimeError("Invalid type for rop.routing, expected mapping")

    queues = routing_cfg.get("queues")
    if not isinstance(queues, dict) or not queues:
        raise RuntimeError(
            "Invalid or missing rop.routing.queues, expected non-empty mapping"
        )

    missing_queues = [
        queue_name
        for queue_name in _REQUIRED_ROP_ROUTING_QUEUES
        if queue_name not in queues
    ]
    if missing_queues:
        raise RuntimeError(
            "Missing required rop.routing.queues: " + ", ".join(missing_queues)
        )

    for queue_name, queue_cfg in queues.items():
        if not isinstance(queue_cfg, dict):
            raise RuntimeError(
                f"Invalid type for rop.routing.queues.{queue_name}, expected mapping"
            )
        bitrix_category = queue_cfg.get("bitrix_category")
        if not isinstance(bitrix_category, str) or not bitrix_category.strip():
            raise RuntimeError(
                f"Invalid or missing rop.routing.queues.{queue_name}.bitrix_category, "
                "expected non-empty string"
            )


def _validate_bitrix_widget_settings(settings: dict) -> None:
    widget_cfg = _get_nested_value(settings, ("bitrix", "widget"))
    if widget_cfg is None:
        return
    if not isinstance(widget_cfg, dict):
        raise RuntimeError("Invalid type for bitrix.widget, expected mapping")

    if not isinstance(widget_cfg.get("enabled"), bool):
        raise RuntimeError("Invalid type for bitrix.widget.enabled, expected bool")

    token_env = widget_cfg.get("token_env")
    if not isinstance(token_env, str) or not token_env.strip():
        raise RuntimeError(
            "Invalid or missing bitrix.widget.token_env, expected non-empty string"
        )

    default_period = widget_cfg.get("default_period")
    if not isinstance(default_period, str) or not default_period.strip():
        raise RuntimeError(
            "Invalid or missing bitrix.widget.default_period, expected non-empty string"
        )
    if default_period not in _ALLOWED_DASHBOARD_PERIODS:
        raise RuntimeError(
            f"Invalid bitrix.widget.default_period '{default_period}', "
            f"expected one of: {sorted(_ALLOWED_DASHBOARD_PERIODS)}"
        )

    max_items = widget_cfg.get("max_items")
    if not isinstance(max_items, int) or max_items <= 0:
        raise RuntimeError("Invalid bitrix.widget.max_items, expected int > 0")

    if widget_cfg.get("enabled"):
        token_value = os.getenv(token_env, "")
        if not token_value:
            raise RuntimeError(
                f"Missing required env var '{token_env}' "
                f"when bitrix.widget.enabled=true"
            )


def _validate_bitrix_embedded_app_settings(settings: dict) -> None:
    emb_cfg = _get_nested_value(settings, ("bitrix", "embedded_app"))
    if emb_cfg is None:
        return
    if not isinstance(emb_cfg, dict):
        raise RuntimeError("Invalid type for bitrix.embedded_app, expected mapping")

    if not isinstance(emb_cfg.get("enabled"), bool):
        raise RuntimeError(
            "Invalid type for bitrix.embedded_app.enabled, expected bool"
        )

    portal_origin = emb_cfg.get("portal_origin")
    if not isinstance(portal_origin, str):
        raise RuntimeError(
            "Invalid type for bitrix.embedded_app.portal_origin, expected string"
        )

    default_role = emb_cfg.get("default_role")
    if not isinstance(default_role, str) or not default_role.strip():
        raise RuntimeError(
            "Invalid or missing bitrix.embedded_app.default_role, "
            "expected non-empty string"
        )
    if default_role not in _ALLOWED_EMBEDDED_ROLES:
        raise RuntimeError(
            "Invalid bitrix.embedded_app.default_role, expected one of: "
            + ", ".join(sorted(_ALLOWED_EMBEDDED_ROLES))
        )

    request_timeout = emb_cfg.get("request_timeout")
    if (
        not isinstance(request_timeout, int)
        or request_timeout < _EMBEDDED_REQUEST_TIMEOUT_MIN
        or request_timeout > _EMBEDDED_REQUEST_TIMEOUT_MAX
    ):
        raise RuntimeError(
            "Invalid bitrix.embedded_app.request_timeout, "
            f"expected int in {_EMBEDDED_REQUEST_TIMEOUT_MIN}.."
            f"{_EMBEDDED_REQUEST_TIMEOUT_MAX}"
        )

    if not emb_cfg.get("enabled"):
        return

    if not is_valid_https_origin(portal_origin):
        raise RuntimeError(
            "Invalid bitrix.embedded_app.portal_origin, "
            "expected exact HTTPS origin when enabled"
        )
    if default_role != "viewer":
        raise RuntimeError(
            "Invalid bitrix.embedded_app.default_role, "
            "only 'viewer' is supported in the current scope"
        )
    if _get_nested_value(settings, ("web", "auth", "enabled")) is not True:
        raise RuntimeError(
            "bitrix.embedded_app.enabled requires web.auth.enabled: true"
        )


def _validate_rop_ai_adjudicator_settings(settings: dict) -> None:
    apply_runtime_settings_overrides(settings)
    adj_cfg = _get_nested_value(settings, ("rop", "ai_assist", "adjudicator"))
    if adj_cfg is None:
        return
    if not isinstance(adj_cfg, dict):
        raise RuntimeError(
            "Invalid type for rop.ai_assist.adjudicator, expected mapping"
        )

    if not isinstance(adj_cfg.get("enabled"), bool):
        raise RuntimeError(
            "Invalid type for rop.ai_assist.adjudicator.enabled, expected bool"
        )

    ai_assist_cfg = _get_nested_value(settings, ("rop", "ai_assist"))
    if not isinstance(ai_assist_cfg, dict):
        raise RuntimeError("Invalid type for rop.ai_assist, expected mapping")
    if adj_cfg.get("enabled") and ai_assist_cfg.get("enabled") is not True:
        raise RuntimeError(
            "Invalid rop.ai_assist config: rop.ai_assist.adjudicator.enabled requires rop.ai_assist.enabled: true"
        )

    timeout = adj_cfg.get("timeout")
    if not isinstance(timeout, int) or timeout <= 0:
        raise RuntimeError(
            "Invalid rop.ai_assist.adjudicator.timeout, expected int > 0"
        )

    max_chars = adj_cfg.get("input_chars_max")
    if not isinstance(max_chars, int) or max_chars <= 0:
        raise RuntimeError(
            "Invalid rop.ai_assist.adjudicator.input_chars_max, expected int > 0"
        )

    attachment_chars_max = adj_cfg.get("attachment_chars_max")
    if not isinstance(attachment_chars_max, int) or attachment_chars_max <= 0:
        raise RuntimeError(
            "Invalid rop.ai_assist.adjudicator.attachment_chars_max, expected int > 0"
        )

    min_conf = adj_cfg.get("confidence_accept_min")
    if not isinstance(min_conf, (int, float)):
        raise RuntimeError(
            "Invalid rop.ai_assist.adjudicator.confidence_accept_min, expected float"
        )
    if min_conf < 0.0 or min_conf > 1.0:
        raise RuntimeError(
            "Invalid rop.ai_assist.adjudicator.confidence_accept_min, expected 0.0..1.0"
        )

    max_events = adj_cfg.get("events_max")
    if not isinstance(max_events, int) or max_events <= 0:
        raise RuntimeError(
            "Invalid rop.ai_assist.adjudicator.events_max, expected int > 0"
        )

    prompt_key = adj_cfg.get("prompt_key")
    if not isinstance(prompt_key, str) or not prompt_key.strip():
        raise RuntimeError(
            "Invalid or missing rop.ai_assist.adjudicator.prompt_key, expected non-empty string"
        )

    if adj_cfg.get("enabled"):
        profile_cfg = _require_one_enabled_ai_profile(
            settings,
            reason="rop.ai_assist.adjudicator.enabled=true",
            require_api_key=True,
        )
        if profile_cfg.get("provider") != "openai_responses":
            raise RuntimeError(
                "Invalid ai.profiles config for rop.ai_assist.adjudicator.enabled=true, expected openai_responses"
            )


def _get_nested_value(settings: dict, key_path: tuple[str, ...]):
    current = settings
    for key in key_path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _parse_optional_bool_env(var_name: str) -> bool | None:
    raw_value = os.getenv(var_name)
    if raw_value is None:
        return None

    normalized = raw_value.strip().casefold()
    if normalized in _ENV_TRUE_VALUES:
        return True
    if normalized in _ENV_FALSE_VALUES:
        return False

    raise RuntimeError(f"Invalid {var_name} value: {raw_value}")


def _apply_rop_ai_adjudicator_env_override(settings: dict) -> None:
    ai_cfg = _get_nested_value(settings, ("rop", "ai_assist"))
    if not isinstance(ai_cfg, dict):
        return

    override_value = _parse_optional_bool_env(_ROP_AI_ADJUDICATOR_ENV)
    adj_cfg = ai_cfg.get("adjudicator")
    if not isinstance(adj_cfg, dict):
        if override_value is None:
            return
        return

    prev_override_present = bool(adj_cfg.get("_env_override_present", False))
    if prev_override_present:
        yaml_enabled = adj_cfg.get("_yaml_enabled", adj_cfg.get("enabled"))
    else:
        yaml_enabled = adj_cfg.get("enabled")
    if isinstance(yaml_enabled, bool):
        adj_cfg["_yaml_enabled"] = yaml_enabled
    else:
        adj_cfg["_yaml_enabled"] = False

    adj_cfg["_env_override_present"] = override_value is not None
    if override_value is not None:
        adj_cfg["enabled"] = override_value
    else:
        adj_cfg["enabled"] = bool(adj_cfg["_yaml_enabled"])
