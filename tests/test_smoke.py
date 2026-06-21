from pathlib import Path

import pytest

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
web:
  host: "127.0.0.1"
  port: 8000
  open_browser: false
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
  api_url: "https://api.openai.com/v1/responses"
  prompts_path: "config/prompts.yml"
  assistant:
    prompts_key: "oos.llm_assistant_qa"
    items_max: 5
  throttling:
    timeout: 60
    retries: 2

i18n:
  lang: "ru"
  path: "config/i18n/ru.yml"

quiz:
  enabled: true
  path: "config/quiz/pharmacy_quiz.json"

modules:
  registry: []

rop:
  attachments:
    enabled: true
    chars_max: 500
    size_max: 1048576
    types:
      - "text/plain"
  dashboard:
    default_period: "7d"
    periods:
      - today
      - yesterday
      - 7d
      - 30d
      - 365d
      - all
  sources: []
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


# Чек: загрузка настроек с источником mailbox_readonly и проверка наличия полей username_env и password_env
def test_load_settings_accepts_mailbox_readonly_source(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yml"
    settings_file.write_text(
        """
app:
  name: "BeeAgent"
  env: "test"
run:
  mode: "telegram"
web:
  host: "127.0.0.1"
  port: 8000
  open_browser: false
telegram:
  enabled: false
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
  api_url: "https://api.openai.com/v1/responses"
  prompts_path: "config/prompts.yml"
  assistant:
    prompts_key: "oos.llm_assistant_qa"
    items_max: 5
  throttling:
    timeout: 60
    retries: 2

i18n:
  lang: "ru"
  path: "config/i18n/ru.yml"

quiz:
  enabled: true
  path: "config/quiz/pharmacy_quiz.json"

modules:
  registry: []

rop:
  attachments:
    enabled: true
    chars_max: 500
    size_max: 1048576
    types:
      - "text/plain"
  dashboard:
    default_period: "7d"
    periods:
      - today
      - yesterday
      - 7d
      - 30d
      - 365d
      - all
  sources:
    - source_id: "hotline"
      source_type: "mailbox_readonly"
      source_role: "technical_aggregator"
      client_id: "welding"
      display_name: "Hotline mailbox"
      enabled: true
      authority: "read_only"
      items_max: 5
      mailbox:
        host: "imap.example.com"
        port: 993
        use_ssl: true
        folder: "INBOX"
        username_env: "ROP_MAILBOX_USERNAME"
        password_env: "ROP_MAILBOX_PASSWORD"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    settings = load_settings(settings_file)
    source = settings["rop"]["sources"][0]

    assert source["source_type"] == "mailbox_readonly"
    assert source["mailbox"]["username_env"] == "ROP_MAILBOX_USERNAME"


# Чек: загрузка настроек с источником mailbox_readonly и отсутствием полей username_env и password_env должна вызывать RuntimeError
def test_load_settings_rejects_mailbox_without_env_names(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yml"
    settings_file.write_text(
        """
app:
  name: "BeeAgent"
  env: "test"
run:
  mode: "telegram"
web:
  host: "127.0.0.1"
  port: 8000
  open_browser: false
telegram:
  enabled: false
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
  api_url: "https://api.openai.com/v1/responses"
  prompts_path: "config/prompts.yml"
  assistant:
    prompts_key: "oos.llm_assistant_qa"
    items_max: 5
  throttling:
    timeout: 60
    retries: 2

i18n:
  lang: "ru"
  path: "config/i18n/ru.yml"

quiz:
  enabled: true
  path: "config/quiz/pharmacy_quiz.json"

modules:
  registry: []

rop:
  attachments:
    enabled: true
    chars_max: 500
    size_max: 1048576
    types:
      - "text/plain"
  dashboard:
    default_period: "7d"
    periods:
      - today
      - yesterday
      - 7d
      - 30d
      - 365d
      - all
  sources:
    - source_id: "hotline"
      source_type: "mailbox_readonly"
      source_role: "technical_aggregator"
      client_id: "welding"
      display_name: "Hotline mailbox"
      enabled: true
      authority: "read_only"
      items_max: 5
      mailbox:
        host: "imap.example.com"
        port: 993
        use_ssl: true
        folder: "INBOX"
        username_env: ""
        password_env: "ROP_MAILBOX_PASSWORD"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    try:
        load_settings(settings_file)
        raise AssertionError("RuntimeError expected for missing mailbox env names")
    except RuntimeError as exc:
        assert "mailbox.username_env" in str(exc)


# Тест: загрузка настроек с источником mailbox_readonly и отсутствием обязательных source profile полей должна вызывать RuntimeError
@pytest.mark.parametrize(
    ("missing_line", "expected_key"),
    [
        ('      source_role: "technical_aggregator"\n', "rop.sources[0].source_role"),
        ('      client_id: "welding"\n', "rop.sources[0].client_id"),
        ('      display_name: "Hotline mailbox"\n', "rop.sources[0].display_name"),
    ],
)
def test_load_settings_rejects_source_profile_missing_fields(
    tmp_path: Path,
    missing_line: str,
    expected_key: str,
) -> None:
    settings_file = tmp_path / "settings.yml"
    template = (
        """
app:
  name: "BeeAgent"
  env: "test"
run:
  mode: "telegram"
web:
  host: "127.0.0.1"
  port: 8000
  open_browser: false
telegram:
  enabled: false
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
  api_url: "https://api.openai.com/v1/responses"
  prompts_path: "config/prompts.yml"
  assistant:
    prompts_key: "oos.llm_assistant_qa"
    items_max: 5
  throttling:
    timeout: 60
    retries: 2

i18n:
  lang: "ru"
  path: "config/i18n/ru.yml"

quiz:
  enabled: true
  path: "config/quiz/pharmacy_quiz.json"

modules:
  registry: []

rop:
  attachments:
    enabled: true
    chars_max: 500
    size_max: 1048576
    types:
      - "text/plain"
  dashboard:
    default_period: "7d"
    periods:
      - today
      - yesterday
      - 7d
      - 30d
      - 365d
      - all
  sources:
    - source_id: "hotline"
      source_type: "mailbox_readonly"
      source_role: "technical_aggregator"
      client_id: "welding"
      display_name: "Hotline mailbox"
      enabled: true
      authority: "read_only"
      items_max: 5
      mailbox:
        host: "imap.example.com"
        port: 993
        use_ssl: true
        folder: "INBOX"
        username_env: "ROP_MAILBOX_USERNAME"
        password_env: "ROP_MAILBOX_PASSWORD"
    """.strip()
        + "\n"
    )
    settings_file.write_text(
        template.replace(missing_line, "", 1),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError) as exc_info:
        load_settings(settings_file)

    assert expected_key in str(exc_info.value)
