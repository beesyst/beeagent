from pathlib import Path

import yaml

REQUIRED_KEYS = (
    ("app", "name"),
    ("app", "env"),
    ("run", "mode"),
    ("telegram", "enabled"),
    ("telegram", "bot_token_env"),
    ("telegram", "chat_id_env"),
    ("telegram", "telemetry_enabled"),
    ("logging", "clear_logs"),
    ("logging", "utc"),
    ("logging", "level"),
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


# Возврат вложенного значения по пути ключей или None.
def _get_nested_value(settings: dict, key_path: tuple[str, ...]):
    current = settings
    for key in key_path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current
