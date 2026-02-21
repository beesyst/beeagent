from pathlib import Path

from beeagent_module.core.log import get_logger, setup_logging
from beeagent_module.core.paths import ensure_dirs, get_app_log_path, get_storage_dir
from beeagent_module.core.settings import load_settings


# Чек: базовая инициализация настроек, логов и storage.
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
  chat_id_env: "CHAT_ID"
  telemetry_enabled: false

logging:
  clear_logs: true
  utc: true
  level: "INFO"

mock:
  seed: 1
  weeks: 2
  stores: 1
  skus: 2
  category: "Vitamins"

data:
  adapter: "mock"
  mock:
    dataset_id:

scheduler:
  enabled: false
  interval: 60
  start_run: false

approval:
  reject_reason: "Rejected by operator"

promo:
  stock_min: 1
  units_max: 0

recommendations:
  enabled: true
  items_max: 10

llm:
  enabled: false
  provider: "openai"
  model: "gpt-4o-mini"
  api_key_env: "OPENAI_API_KEY"

quiz:
  enabled: true
  path: "config/quiz/pharmacy_quiz.json"
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
