import os
from pathlib import Path

import yaml

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
    ("recommendations", "enabled"),
    ("recommendations", "items_max"),
    ("llm", "enabled"),
    ("llm", "provider"),
    ("llm", "model"),
    ("llm", "api_key_env"),
    ("llm", "api_url"),
    ("llm", "prompts_path"),
    ("llm", "assistant", "prompts_key"),
    ("llm", "assistant", "items_max"),
    ("llm", "throttling", "timeout"),
    ("llm", "throttling", "retries"),
    ("i18n", "lang"),
    ("i18n", "path"),
    ("quiz", "enabled"),
    ("quiz", "path"),
    ("modules", "registry"),
    ("rop", "attachments", "enabled"),
    ("rop", "attachments", "chars_max"),
    ("rop", "attachments", "size_max"),
    ("rop", "attachments", "types"),
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

    if not isinstance(
        _get_nested_value(settings, ("recommendations", "enabled")), bool
    ):
        raise RuntimeError("Invalid type for recommendations.enabled, expected bool")

    recommendations_items_max = _get_nested_value(
        settings, ("recommendations", "items_max")
    )
    if not isinstance(recommendations_items_max, int):
        raise RuntimeError("Invalid type for recommendations.items_max, expected int")
    if recommendations_items_max <= 0:
        raise RuntimeError("Invalid value for recommendations.items_max, expected > 0")

    if not isinstance(_get_nested_value(settings, ("llm", "enabled")), bool):
        raise RuntimeError("Invalid type for llm.enabled, expected bool")

    if not isinstance(_get_nested_value(settings, ("llm", "provider")), str):
        raise RuntimeError("Invalid type for llm.provider, expected string")

    if not isinstance(_get_nested_value(settings, ("llm", "model")), str):
        raise RuntimeError("Invalid type for llm.model, expected string")

    if not isinstance(_get_nested_value(settings, ("llm", "api_key_env")), str):
        raise RuntimeError("Invalid type for llm.api_key_env, expected string")

    if not isinstance(_get_nested_value(settings, ("llm", "api_url")), str):
        raise RuntimeError("Invalid type for llm.api_url, expected string")

    if not isinstance(_get_nested_value(settings, ("llm", "prompts_path")), str):
        raise RuntimeError("Invalid type for llm.prompts_path, expected string")

    if not isinstance(
        _get_nested_value(settings, ("llm", "assistant", "prompts_key")), str
    ):
        raise RuntimeError(
            "Invalid type for llm.assistant.prompts_key, expected string"
        )

    assistant_items_max = _get_nested_value(settings, ("llm", "assistant", "items_max"))
    if not isinstance(assistant_items_max, int):
        raise RuntimeError("Invalid type for llm.assistant.items_max, expected int")
    if assistant_items_max <= 0:
        raise RuntimeError("Invalid value for llm.assistant.items_max, expected > 0")

    throttling_timeout = _get_nested_value(settings, ("llm", "throttling", "timeout"))
    if not isinstance(throttling_timeout, int):
        raise RuntimeError("Invalid type for llm.throttling.timeout, expected int")
    if throttling_timeout <= 0:
        raise RuntimeError("Invalid value for llm.throttling.timeout, expected > 0")

    throttling_retries = _get_nested_value(settings, ("llm", "throttling", "retries"))
    if not isinstance(throttling_retries, int):
        raise RuntimeError("Invalid type for llm.throttling.retries, expected int")
    if throttling_retries < 0:
        raise RuntimeError("Invalid value for llm.throttling.retries, expected >= 0")

    llm_provider = _get_nested_value(settings, ("llm", "provider"))
    if llm_provider != "openai":
        raise RuntimeError("Unsupported llm.provider, expected 'openai'")

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

    _validate_rop_dashboard_settings(settings)

    _validate_bitrix_settings(settings)
    _validate_bitrix_widget_settings(settings)

    _validate_web_auth_settings(settings)


def _validate_web_auth_settings(settings: dict) -> None:
    import re

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

    if ai_cfg.get("enabled"):
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


def _validate_rop_ai_adjudicator_settings(settings: dict) -> None:
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
