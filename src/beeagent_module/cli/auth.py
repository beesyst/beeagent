from __future__ import annotations

import os
import secrets
import stat
import sys
from pathlib import Path
from typing import Any

import yaml


def ensure_auth_env(
    project_root: Path,
    settings_path: Path,
    env_path: Path,
    rotate: str | None = None,
    quiet: bool = False,
) -> dict[str, str]:
    del project_root

    auth_cfg = _read_raw_web_auth(settings_path)
    if auth_cfg.get("enabled") is not True:
        return {}

    session_secret_env = auth_cfg.get("session_secret_env")
    principals = auth_cfg.get("principals")

    if not isinstance(session_secret_env, str) or not session_secret_env.strip():
        raise RuntimeError("Invalid or missing web.auth.session_secret_env")
    if not isinstance(principals, list):
        raise RuntimeError("Invalid type for web.auth.principals, expected list")

    env_lines = _read_env_lines(env_path)
    env_map = _parse_env_map(env_lines)
    principal_envs = _collect_principal_envs(principals)
    rotation_targets = _resolve_rotation_targets(
        rotate=rotate,
        session_secret_env=session_secret_env,
        principals=principals,
    )

    generated: dict[str, str] = {}
    final_values: dict[str, str] = {}

    all_env_names = [session_secret_env, *principal_envs]
    for env_name in all_env_names:
        if env_name in rotation_targets:
            value = _generate_secret(env_name, session_secret_env=session_secret_env)
            generated[env_name] = value
            final_values[env_name] = value
            continue

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
    elif env_path.exists() and os.name == "posix":
        env_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    for env_name, value in final_values.items():
        os.environ[env_name] = value

    if not quiet:
        for env_name in all_env_names:
            if env_name in generated:
                print(f"{env_name}={generated[env_name]}")

    return generated


def handle_auth_cli(cli_args: list[str], project_root: Path) -> int:
    if not cli_args or cli_args[0] != "rotate":
        _print_usage()
        return 2

    rotate_args = cli_args[1:]
    if not rotate_args:
        _print_usage()
        return 2

    target = rotate_args[0]
    extra_args = rotate_args[1:]

    logout_all = "--logout-all" in extra_args
    remaining = [a for a in extra_args if a != "--logout-all"]
    if remaining:
        _print_usage()
        return 2

    if logout_all and target != "all":
        print(
            "Error: --logout-all is only supported with 'all' target", file=sys.stderr
        )
        return 1

    settings_path = project_root / "config" / "settings.yml"
    auth_cfg = _read_auth_config(settings_path)
    if auth_cfg is None:
        return 1

    return _do_rotate(
        auth_cfg=auth_cfg,
        project_root=project_root,
        target=target,
        logout_all=logout_all,
    )


def ensure_web_auth_env(project_root: Path, settings_path: Path) -> None:
    env_path = project_root / ".env"
    generated = ensure_auth_env(
        project_root=project_root,
        settings_path=settings_path,
        env_path=env_path,
        quiet=True,
    )
    for env_name in generated:
        print(f"[init] {env_name}=<generated>")


def _read_auth_config(settings_path: Path) -> dict[str, Any] | None:
    if not settings_path.exists():
        print("Error: settings.yml not found", file=sys.stderr)
        return None

    with settings_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        print("Error: settings.yml must contain a top-level mapping", file=sys.stderr)
        return None

    web_cfg = data.get("web", {})
    if not isinstance(web_cfg, dict):
        return {"session_secret_env": None, "principals": []}

    auth_cfg = web_cfg.get("auth", {})
    if not isinstance(auth_cfg, dict):
        return {"session_secret_env": None, "principals": []}

    return {
        "session_secret_env": auth_cfg.get("session_secret_env"),
        "principals": auth_cfg.get("principals", []),
    }


def _read_raw_web_auth(settings_path: Path) -> dict[str, Any]:
    if not settings_path.exists():
        raise RuntimeError(f"Settings file not found: {settings_path}")

    with settings_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if not isinstance(data, dict):
        raise RuntimeError("Settings file must contain a top-level mapping")

    web_cfg = data.get("web", {})
    if not isinstance(web_cfg, dict):
        return {}

    auth_cfg = web_cfg.get("auth", {})
    if not isinstance(auth_cfg, dict):
        return {}

    return auth_cfg


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


def _resolve_rotation_targets(
    rotate: str | None,
    session_secret_env: str,
    principals: list[Any],
) -> set[str]:
    if rotate is None:
        return set()

    target = rotate.strip()
    if not target:
        return set()

    if target == "session":
        return {session_secret_env}

    if target == "all":
        targets = {session_secret_env}
        for principal in principals:
            if not isinstance(principal, dict):
                continue
            token_env = principal.get("token_env")
            if isinstance(token_env, str) and token_env.strip():
                targets.add(token_env.strip())
        return targets

    for principal in principals:
        if not isinstance(principal, dict):
            continue
        principal_id = str(principal.get("id", "")).strip()
        username = str(principal.get("username", "")).strip()
        if target in {principal_id, username}:
            token_env = principal.get("token_env")
            if not isinstance(token_env, str) or not token_env.strip():
                raise RuntimeError(
                    f"Invalid or missing token_env for principal '{target}'"
                )
            return {token_env.strip()}

    raise RuntimeError(f"Unsupported rotate target: {target}")


def _generate_secret(env_name: str, session_secret_env: str) -> str:
    if env_name == session_secret_env:
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


def _update_env_file(env_path: Path, lines: list[str], updates: dict[str, str]) -> None:
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

    for key, value in updates.items():
        if key not in found_keys:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines.append("\n")
            new_lines.append(f"{key}={value}\n")

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("".join(new_lines), encoding="utf-8")

    if os.name == "posix":
        env_path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _do_rotate(
    auth_cfg: dict[str, Any],
    project_root: Path,
    target: str,
    logout_all: bool,
) -> int:
    if logout_all and target != "all":
        print(
            "Error: --logout-all is only supported with 'all' target", file=sys.stderr
        )
        return 1

    session_secret_env = auth_cfg.get("session_secret_env")
    principals = auth_cfg.get("principals", [])

    if not isinstance(principals, list):
        principals = []

    env_path = project_root / ".env"
    env_lines = _read_env_lines(env_path)

    if target == "session":
        return _rotate_session(session_secret_env, env_path, env_lines)

    if target == "all":
        return _rotate_all(
            principals, session_secret_env, env_path, env_lines, logout_all
        )

    return _rotate_single(target, principals, env_path, env_lines)


def _find_principal(principals: list[Any], target: str) -> dict[str, Any] | None:
    for p in principals:
        if not isinstance(p, dict):
            continue
        if p.get("id") == target or p.get("username") == target:
            return p
    return None


def _available_principals(principals: list[Any]) -> list[str]:
    result: list[str] = []
    for p in principals:
        if not isinstance(p, dict):
            continue
        pid = p.get("id", "?")
        username = p.get("username", "?")
        result.append(f"  id={pid} / username={username}")
    return result


def _rotate_single(
    target: str, principals: list[Any], env_path: Path, env_lines: list[str]
) -> int:
    principal = _find_principal(principals, target)
    if principal is None:
        available = _available_principals(principals)
        msg = (
            f"Error: Unknown principal '{target}'.\n"
            "Available configured principals (id / username):\n" + "\n".join(available)
        )
        print(msg, file=sys.stderr)
        return 1

    token_env = principal.get("token_env")
    if not isinstance(token_env, str) or not token_env.strip():
        print(
            f"Error: Principal '{target}' has no token_env configured", file=sys.stderr
        )
        return 1

    new_token: str = secrets.token_urlsafe(32)
    _update_env_file(env_path, env_lines, {token_env: new_token})

    print(new_token)
    print(
        "Restart required for the running web app to use rotated secrets.", flush=True
    )
    return 0


def _rotate_all(
    principals: list[Any],
    session_secret_env: Any,
    env_path: Path,
    env_lines: list[str],
    logout_all: bool,
) -> int:
    valid_principals = [p for p in principals if isinstance(p, dict)]
    if not valid_principals:
        print("Error: No principals configured in settings.yml", file=sys.stderr)
        return 1

    updates: dict[str, str] = {}

    for p in valid_principals:
        token_env = p.get("token_env")
        if isinstance(token_env, str) and token_env.strip():
            updates[token_env] = secrets.token_urlsafe(32)

    if logout_all:
        if isinstance(session_secret_env, str) and session_secret_env.strip():
            updates[session_secret_env] = secrets.token_urlsafe(64)

    _update_env_file(env_path, env_lines, updates)

    for p in valid_principals:
        token_env = p.get("token_env")
        if isinstance(token_env, str) and token_env.strip():
            username = p.get("username", "?")
            print(f"{username}: {updates[token_env]}")

    if logout_all:
        print(
            "Session secret rotated. All existing browser sessions are invalidated after restart."
        )

    print(
        "Restart required for the running web app to use rotated secrets.", flush=True
    )
    return 0


def _rotate_session(
    session_secret_env: Any, env_path: Path, env_lines: list[str]
) -> int:
    if not isinstance(session_secret_env, str) or not session_secret_env.strip():
        print(
            "Error: No session_secret_env configured in settings.yml", file=sys.stderr
        )
        return 1

    new_secret: str = secrets.token_urlsafe(64)
    _update_env_file(env_path, env_lines, {session_secret_env: new_secret})

    print(
        "Warning: Session secret rotated. All existing browser sessions are invalidated after restart."
    )
    print(
        "Restart required for the running web app to use rotated secrets.", flush=True
    )
    return 0


def _print_usage() -> None:
    print(
        "Usage:\n"
        "  start.sh auth rotate <principal-id-or-username>\n"
        "  start.sh auth rotate all [--logout-all]\n"
        "  start.sh auth rotate session",
        file=sys.stderr,
    )
