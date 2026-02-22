from pathlib import Path
from typing import Any

import yaml

from beeagent_module.core.paths import get_project_root


# Загрузка словаря переводов из YAML-файла
def load_translations(path: str | Path) -> dict[str, Any]:
    file_path = _resolve_config_path(path)
    if not file_path.exists():
        raise RuntimeError(f"Translations file not found: {file_path}")

    with file_path.open("r", encoding="utf-8") as file:
        content = yaml.safe_load(file)

    if not isinstance(content, dict):
        raise RuntimeError("Translations file must contain a top-level mapping")

    return content


# Получение перевода по ключу с fail-fast при отсутствии
def t(translations: dict[str, Any], key: str, **vars: Any) -> str:
    value = _get_nested_value(translations, tuple(key.split(".")))
    if not isinstance(value, str):
        raise RuntimeError(f"Translation key not found: {key}")

    try:
        return value.format(**vars)
    except KeyError as exc:
        missing_var = exc.args[0]
        raise RuntimeError(
            f"Missing translation variable '{missing_var}' for key: {key}"
        ) from exc


# Резолв относительного пути от корня проекта
def _resolve_config_path(path: str | Path) -> Path:
    path_value = Path(path)
    if path_value.is_absolute():
        return path_value
    return get_project_root() / path_value


# Получение вложенного значения по пути ключей
def _get_nested_value(payload: dict[str, Any], key_path: tuple[str, ...]) -> Any:
    current: Any = payload
    for key in key_path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current
