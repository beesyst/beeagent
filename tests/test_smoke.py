from pathlib import Path

from beeagent_module.core.log import get_logger, setup_logging
from beeagent_module.core.paths import ensure_dirs, get_app_log_path, get_storage_dir
from beeagent_module.core.settings import load_settings


# Русский комментарий
def test_smoke_startup_initialization(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yml"
    settings_file.write_text(
        """
app:
  name: "BeeAgent"
  env: "test"
run:
  mode: "telegram"
telegram:
  enabled: true
  bot_token_env: "TELEGRAM_BOT_TOKEN"

logging:
  clear_logs: true
  utc: true
  level: "INFO"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    settings = load_settings(settings_file)
    ensure_dirs(tmp_path)

    log_path = get_app_log_path(tmp_path)

    log_cfg = settings["logging"]
    setup_logging(
        log_path=log_path,
        level=log_cfg["level"],
        clear_logs=log_cfg["clear_logs"],
        utc=log_cfg["utc"],
    )

    logger = get_logger("app")
    logger.info("smoke test log entry")

    assert get_storage_dir(tmp_path).exists()
    assert log_path.exists()
