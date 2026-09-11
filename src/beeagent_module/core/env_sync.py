from __future__ import annotations

import os
import re
import secrets
import stat
from pathlib import Path
from typing import Any

import yaml


_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_ENV_VALUE_MAX_LENGTH = 4096


def sync_env_with_example(project_root: Path) -> None:
    env_path = project_root / ".env"
    example_path = project_root / ".env.example"

    if not example_path.exists():
        return

    example_text = example_path.read_text(encoding="utf-8")
    example_keys = _parse_dotenv_keys_in_order(example_text)

    if not env_path.exists():
        _safe_write(env_path, example_text)
        return

    existing_content = env_path.read_text(encoding="utf-8")
    existing_keys = _parse_dotenv_key_set(existing_content)
    missing_keys = [key for key in example_keys if key not in existing_keys]

    if not missing_keys:
        return

    content = existing_content.rstrip("\n") + "\n"
    for key in missing_keys:
        content += f"{key}=\n"

    _safe_write(env_path, content)


def ensure_bootstrap_env(
    project_root: Path,
    settings_path: Path,
    env_path: Path,
    quiet: bool = True,
) -> dict[str, str]:
    del project_root

    bootstrap_cfg = _read_internal_secret_bootstrap_config(settings_path)
    session_secret_env = bootstrap_cfg.get("session_secret_env")
    principals = bootstrap_cfg.get("principals")
    widget_token_env = bootstrap_cfg.get("widget_token_env")

    if not isinstance(principals, list):
        raise RuntimeError("Invalid type for web.auth.principals, expected list")

    env_lines = _read_env_lines(env_path)
    env_map = _parse_env_map(env_lines)
    principal_envs = _collect_principal_envs(principals) if principals else []

    all_env_names = _unique_env_names(
        [
            session_secret_env,
            *principal_envs,
            widget_token_env,
        ]
    )
    if not all_env_names:
        return {}

    generated: dict[str, str] = {}
    final_values: dict[str, str] = {}

    for env_name in all_env_names:
        runtime_value = os.environ.get(env_name, "").strip()
        if runtime_value:
            final_values[env_name] = runtime_value
            continue

        file_value = env_map.get(env_name, "").strip()
        if file_value:
            final_values[env_name] = file_value
            continue

        value = _generate_secret(env_name, session_secret_env=session_secret_env)
        generated[env_name] = value
        final_values[env_name] = value

    if generated:
        _update_env_file(env_path, env_lines, generated)

    for env_name, value in final_values.items():
        os.environ[env_name] = value

    if not quiet:
        for env_name in all_env_names:
            if env_name in generated:
                print(f"{env_name}=<generated>")

    return generated


def read_selected_env_values(env_path: Path, names: set[str]) -> dict[str, str]:
    normalized_names = _validate_selected_env_names(names)
    values = _parse_env_map(_read_env_lines(env_path))
    result: dict[str, str] = {}
    for name in normalized_names:
        result[name] = os.environ.get(name, values.get(name, ""))
    return result


def update_selected_env_values(
    env_path: Path,
    updates: dict[str, str],
    *,
    section: str | None = None,
) -> None:
    if not isinstance(updates, dict) or not updates:
        raise ValueError("Environment updates are required")
    names = _validate_selected_env_names(set(updates))
    normalized: dict[str, str] = {}
    for name in names:
        value = updates[name]
        if (
            not isinstance(value, str)
            or not value
            or len(value) > _ENV_VALUE_MAX_LENGTH
            or any(character in value for character in ("\r", "\n", "\x00"))
        ):
            raise ValueError("Environment value is invalid")
        normalized[name] = value
    _update_env_file(env_path, _read_env_lines(env_path), normalized, section=section)
    for name, value in normalized.items():
        os.environ[name] = value


def remove_selected_env_values(env_path: Path, names: set[str]) -> None:
    normalized_names = _validate_selected_env_names(names)
    _safe_write(
        env_path,
        "".join(
            line
            for line in _read_env_lines(env_path)
            if line.rstrip("\n").rstrip("\r").split("=", 1)[0].strip()
            not in normalized_names
        ),
    )


def _validate_selected_env_names(names: set[str]) -> list[str]:
    if not names or len(names) > 20:
        raise ValueError("Environment names are invalid")
    normalized = sorted(names)
    if any(
        not isinstance(name, str) or not _ENV_NAME.fullmatch(name)
        for name in normalized
    ):
        raise ValueError("Environment names are invalid")
    return normalized


def _iter_dotenv_keys(text: str):
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key:
            yield key


def _parse_dotenv_keys_in_order(text: str) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for key in _iter_dotenv_keys(text):
        if key in seen:
            continue
        seen.add(key)
        keys.append(key)
    return keys


def _parse_dotenv_key_set(text: str) -> set[str]:
    return set(_iter_dotenv_keys(text))


def _read_internal_secret_bootstrap_config(settings_path: Path) -> dict[str, Any]:
    if not settings_path.exists():
        raise RuntimeError(f"Settings file not found: {settings_path}")

    with settings_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if not isinstance(data, dict):
        raise RuntimeError("Settings file must contain a top-level mapping")

    web_cfg = data.get("web", {})
    auth_cfg: dict[str, Any] = {}
    if isinstance(web_cfg, dict):
        raw_auth_cfg = web_cfg.get("auth", {})
        if isinstance(raw_auth_cfg, dict):
            auth_cfg = raw_auth_cfg

    bitrix_cfg = data.get("bitrix", {})
    widget_cfg: dict[str, Any] = {}
    if isinstance(bitrix_cfg, dict):
        raw_widget_cfg = bitrix_cfg.get("widget", {})
        if isinstance(raw_widget_cfg, dict):
            widget_cfg = raw_widget_cfg

    auth_enabled = auth_cfg.get("enabled") is True
    session_secret_env = auth_cfg.get("session_secret_env") if auth_enabled else None
    principals = auth_cfg.get("principals") if auth_enabled else []
    if auth_enabled and (
        not isinstance(session_secret_env, str) or not session_secret_env.strip()
    ):
        raise RuntimeError("Invalid or missing web.auth.session_secret_env")

    widget_token_env = widget_cfg.get("token_env")
    if isinstance(widget_token_env, str):
        widget_token_env = widget_token_env.strip()
    else:
        widget_token_env = ""

    return {
        "session_secret_env": session_secret_env,
        "principals": principals,
        "widget_token_env": widget_token_env,
    }


def _unique_env_names(env_names: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for env_name in env_names:
        if not isinstance(env_name, str):
            continue
        normalized = env_name.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _collect_principal_envs(principals: list[Any]) -> list[str]:
    names: list[str] = []
    for idx, principal in enumerate(principals):
        if not isinstance(principal, dict):
            raise RuntimeError(
                f"Invalid type for web.auth.principals[{idx}], expected mapping"
            )
        token_env = principal.get("token_env")
        if not isinstance(token_env, str) or not token_env.strip():
            raise RuntimeError(
                f"Invalid or missing web.auth.principals[{idx}].token_env"
            )
        names.append(token_env.strip())
    return names


def _generate_secret(env_name: str, session_secret_env: str | None) -> str:
    if session_secret_env and env_name == session_secret_env:
        return secrets.token_urlsafe(64)
    return secrets.token_urlsafe(32)


def _read_env_lines(env_path: Path) -> list[str]:
    if not env_path.exists():
        return []
    return env_path.read_text(encoding="utf-8").splitlines(keepends=True)


def _parse_env_map(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        stripped = line.rstrip("\n").rstrip("\r")
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _update_env_file(
    env_path: Path,
    lines: list[str],
    updates: dict[str, str],
    *,
    section: str | None = None,
) -> None:
    new_lines: list[str] = []
    found_keys: set[str] = set()

    for line in lines:
        stripped = line.rstrip("\n").rstrip("\r")
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue

        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            new_lines.append(f"{key}={updates[key]}\n")
            found_keys.add(key)
        else:
            new_lines.append(line)

    missing = [key for key in updates if key not in found_keys]
    if missing:
        additions = [f"{key}={updates[key]}\n" for key in missing]
        section_index = (
            next(
                (
                    index
                    for index, line in enumerate(new_lines)
                    if line.strip() == section
                ),
                None,
            )
            if isinstance(section, str) and section.startswith("#")
            else None
        )
        if section_index is None:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines.append("\n")
            new_lines.extend(additions)
        else:
            insertion_index = next(
                (
                    index
                    for index in range(section_index + 1, len(new_lines))
                    if new_lines[index].lstrip().startswith("#")
                ),
                len(new_lines),
            )
            new_lines[insertion_index:insertion_index] = additions

    _safe_write(env_path, "".join(new_lines))


def _safe_write(path: Path, content: str) -> None:
    target = path
    if path.is_symlink():
        try:
            target = path.resolve(strict=True)
        except OSError as exc:
            raise RuntimeError(
                "Environment file symlink target is unavailable"
            ) from exc
        if not target.is_file():
            raise RuntimeError("Environment file symlink target is invalid")
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    existing_mode = None
    existing_gid = None

    if os.name == "posix" and target.exists():
        existing_stat = target.stat()
        existing_mode = stat.S_IMODE(existing_stat.st_mode)
        existing_gid = existing_stat.st_gid

    target.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        fd = os.open(
            tmp_path,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            stat.S_IRUSR | stat.S_IWUSR,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(content)
            if existing_gid is not None:
                os.fchown(tmp_file.fileno(), -1, existing_gid)
            if existing_mode is not None:
                os.fchmod(tmp_file.fileno(), existing_mode)
    else:
        tmp_path.write_text(content, encoding="utf-8")

    tmp_path.replace(target)
