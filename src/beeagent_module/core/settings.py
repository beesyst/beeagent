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
    ("rop", "sources"),
)


# Загрузка YAML-настройки и валидация обязательных ключей.
def load_settings(settings_path: Path) -> dict:
    if not settings_path.exists():
        raise RuntimeError(f"Settings file not found: {settings_path}")

    with settings_path.open("r", encoding="utf-8") as file:
        content = yaml.safe_load(file)

    if not isinstance(content, dict):
        raise RuntimeError("Settings file must contain a top-level mapping")

    validate_settings(content)
    return content


# Чек обязательных ключей и типов настроек.
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
            for key in ("host", "folder", "username_env", "password_env"):
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


# Возврат вложенного значения по пути ключей или None.
def _get_nested_value(settings: dict, key_path: tuple[str, ...]):
    current = settings
    for key in key_path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current
