import os


def get_required_secret(env_key: str) -> str:
    value = os.getenv(env_key)
    if value is None or not value.strip():
        raise RuntimeError(f"Missing required secret in env: {env_key}")
    return value.strip()


def get_required_int(env_key: str) -> int:
    raw = get_required_secret(env_key)
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid int in env {env_key}: {raw!r}") from exc


def load_secrets(settings: dict) -> dict:
    telegram_cfg = settings.get("telegram", {})
    secrets: dict[str, object] = {}

    bot_token_env = telegram_cfg.get("bot_token_env")
    if bot_token_env:
        secrets["telegram_bot_token"] = get_required_secret(bot_token_env)

    chat_id_env = telegram_cfg.get("chat_id_env")
    if chat_id_env:
        secrets["telegram_chat_id"] = get_required_int(chat_id_env)

    return secrets
