from pathlib import Path

import pytest

from beeagent_module.core.log import get_logger, setup_logging
from beeagent_module.core.paths import ensure_dirs, get_app_log_path, get_storage_dir
from beeagent_module.core.settings import load_settings


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
  auth:
    enabled: false
    mode: beeui_session
    session_secret_env: BEEAGENT_WEB_SESSION_SECRET
    principals: []
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

i18n:
  lang: "ru"
  path: "config/i18n/ru.yml"

quiz:
  enabled: true
  path: "config/quiz/pharmacy_quiz.json"

modules:
  registry: []

rop:
  mailbox_poll:
    enabled: false
    source_id: "hotline"
  email_preview:
    body_chars_max: 4000
  attachments:
    enabled: true
    chars_max: 500
    size_max: 1048576
    types:
      - "text/plain"
    storage:
      enabled: true
      file_max_bytes: 10485760
      message_aggregate_max_bytes: 20971520
      files_max_per_message: 20
    analysis:
      provider: ""
      file_capable: false
      max_chars: 2000
  dashboard:
    default_period: "7d"
    periods:
      - today
      - yesterday
      - 7d
      - 30d
      - 365d
      - all
  ai_assist:
    enabled: false
    events_max: 20
    request_timeout: 30
    ai_confidence_min: 0.70
    dry_run: false
    adjudicator:
      enabled: false
      timeout: 20
      input_chars_max: 8000
      confidence_accept_min: 0.70
      events_max: 20
      prompt_key: "rop.ai_adjudicator"
  routing:
    queues:
      sales:
        bitrix_category: sales
      tender:
        bitrix_category: tenders
      logistics:
        bitrix_category: logistics
      finance:
        bitrix_category: finance
      procurement:
        bitrix_category: procurement
      manual_review:
        bitrix_category: manual_review
  sources: []
ai:
  prompts:
    path: "config/prompts.yml"
    store: false
  profiles:
    openai:
      enabled: true
      provider: openai_responses
      api_key_env: OPENAI_API_KEY
      base_url: "https://api.openai.com/v1"
      model: "gpt-5.4-mini"
    deepseek:
      enabled: false
      provider: openai_compatible
      api_key_env: DEEPSEEK_API_KEY
      base_url: "https://api.deepseek.com/v1"
      model: "deepseek-chat"
    lmstudio:
      enabled: false
      provider: openai_compatible
      api_key_env: LMSTUDIO_API_KEY
      base_url: "http://127.0.0.1:1234/v1"
      model: "local-model"
    custom:
      enabled: false
      provider: openai_compatible
      api_key_env: CUSTOM_AI_API_KEY
      base_url: "https://example.test/v1"
      model: "custom-model"
bitrix:
  enabled: false
  webhook_env: BITRIX_WEBHOOK_URL
  timeout: 10
  page_size: 50
  pages_max: 3
  types_entity:
    - 1
    - 2
    - 3
    - 4
  reconciliation:
    enabled: false
    candidate_limit: 20
    window_date: 180
    correlation:
      enabled: true
      window_days: 180
  widget:
    enabled: false
    token_env: BITRIX_ROP_WIDGET_TOKEN
    default_period: "7d"
    max_items: 50
  embedded_app:
    enabled: false
    portal_origin: ""
    default_role: "viewer"
    request_timeout: 10
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


def test_storage_dir_is_canonical_for_a_regular_local_directory(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()

    storage_dir = get_storage_dir(project_root)

    assert storage_dir == (project_root / "storage").resolve()
    assert not storage_dir.exists()

    ensure_dirs(project_root)

    assert storage_dir.is_dir()
    assert (storage_dir / ".gitkeep").is_file()


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
  auth:
    enabled: false
    mode: beeui_session
    session_secret_env: BEEAGENT_WEB_SESSION_SECRET
    principals: []
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

i18n:
  lang: "ru"
  path: "config/i18n/ru.yml"

quiz:
  enabled: true
  path: "config/quiz/pharmacy_quiz.json"

modules:
  registry: []

rop:
  mailbox_poll:
    enabled: false
    source_id: "hotline"
  email_preview:
    body_chars_max: 4000
  attachments:
    enabled: true
    chars_max: 500
    size_max: 1048576
    types:
      - "text/plain"
    storage:
      enabled: true
      file_max_bytes: 10485760
      message_aggregate_max_bytes: 20971520
      files_max_per_message: 20
    analysis:
      provider: ""
      file_capable: false
      max_chars: 2000
  dashboard:
    default_period: "7d"
    periods:
      - today
      - yesterday
      - 7d
      - 30d
      - 365d
      - all
  ai_assist:
    enabled: false
    events_max: 20
    request_timeout: 30
    ai_confidence_min: 0.70
    dry_run: false
    adjudicator:
      enabled: false
      timeout: 20
      input_chars_max: 8000
      confidence_accept_min: 0.70
      events_max: 20
      prompt_key: "rop.ai_adjudicator"
  routing:
    queues:
      sales:
        bitrix_category: sales
      tender:
        bitrix_category: tenders
      logistics:
        bitrix_category: logistics
      finance:
        bitrix_category: finance
      procurement:
        bitrix_category: procurement
      manual_review:
        bitrix_category: manual_review
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

ai:
  prompts:
    path: "config/prompts.yml"
    store: false
  profiles:
    openai:
      enabled: true
      provider: openai_responses
      api_key_env: OPENAI_API_KEY
      base_url: "https://api.openai.com/v1"
      model: "gpt-5.4-mini"
    deepseek:
      enabled: false
      provider: openai_compatible
      api_key_env: DEEPSEEK_API_KEY
      base_url: "https://api.deepseek.com/v1"
      model: "deepseek-chat"
    lmstudio:
      enabled: false
      provider: openai_compatible
      api_key_env: LMSTUDIO_API_KEY
      base_url: "http://127.0.0.1:1234/v1"
      model: "local-model"
    custom:
      enabled: false
      provider: openai_compatible
      api_key_env: CUSTOM_AI_API_KEY
      base_url: "https://example.test/v1"
      model: "custom-model"

bitrix:
  enabled: false
  webhook_env: BITRIX_WEBHOOK_URL
  timeout: 10
  page_size: 50
  pages_max: 3
  types_entity:
    - 1
    - 2
    - 3
    - 4
  reconciliation:
    enabled: false
    candidate_limit: 20
    window_date: 180
    correlation:
      enabled: true
      window_days: 180
  widget:
    enabled: false
    token_env: BITRIX_ROP_WIDGET_TOKEN
    default_period: "7d"
    max_items: 50
  embedded_app:
    enabled: false
    portal_origin: ""
    default_role: "viewer"
    request_timeout: 10

""".strip()
        + "\n",
        encoding="utf-8",
    )

    settings = load_settings(settings_file)
    source = settings["rop"]["sources"][0]

    assert source["source_type"] == "mailbox_readonly"
    assert source["mailbox"]["username_env"] == "ROP_MAILBOX_USERNAME"


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
  auth:
    enabled: false
    mode: beeui_session
    session_secret_env: BEEAGENT_WEB_SESSION_SECRET
    principals: []
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

i18n:
  lang: "ru"
  path: "config/i18n/ru.yml"

quiz:
  enabled: true
  path: "config/quiz/pharmacy_quiz.json"

modules:
  registry: []

rop:
  mailbox_poll:
    enabled: false
    source_id: "hotline"
  email_preview:
    body_chars_max: 4000
  attachments:
    enabled: true
    chars_max: 500
    size_max: 1048576
    types:
      - "text/plain"
    storage:
      enabled: true
      file_max_bytes: 10485760
      message_aggregate_max_bytes: 20971520
      files_max_per_message: 20
    analysis:
      provider: ""
      file_capable: false
      max_chars: 2000
  dashboard:
    default_period: "7d"
    periods:
      - today
      - yesterday
      - 7d
      - 30d
      - 365d
      - all
  ai_assist:
    enabled: false
    events_max: 20
    request_timeout: 30
    ai_confidence_min: 0.70
    dry_run: false
    adjudicator:
      enabled: false
      timeout: 20
      input_chars_max: 8000
      confidence_accept_min: 0.70
      events_max: 20
      prompt_key: "rop.ai_adjudicator"
  routing:
    queues:
      sales:
        bitrix_category: sales
      tender:
        bitrix_category: tenders
      logistics:
        bitrix_category: logistics
      finance:
        bitrix_category: finance
      procurement:
        bitrix_category: procurement
      manual_review:
        bitrix_category: manual_review
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

ai:
  prompts:
    path: "config/prompts.yml"
    store: false
  profiles:
    openai:
      enabled: true
      provider: openai_responses
      api_key_env: OPENAI_API_KEY
      base_url: "https://api.openai.com/v1"
      model: "gpt-5.4-mini"
    deepseek:
      enabled: false
      provider: openai_compatible
      api_key_env: DEEPSEEK_API_KEY
      base_url: "https://api.deepseek.com/v1"
      model: "deepseek-chat"
    lmstudio:
      enabled: false
      provider: openai_compatible
      api_key_env: LMSTUDIO_API_KEY
      base_url: "http://127.0.0.1:1234/v1"
      model: "local-model"
    custom:
      enabled: false
      provider: openai_compatible
      api_key_env: CUSTOM_AI_API_KEY
      base_url: "https://example.test/v1"
      model: "custom-model"

bitrix:
  enabled: false
  webhook_env: BITRIX_WEBHOOK_URL
  timeout: 10
  page_size: 50
  pages_max: 3
  types_entity:
    - 1
    - 2
    - 3
    - 4
  reconciliation:
    enabled: false
    candidate_limit: 20
    window_date: 180
  widget:
    enabled: false
    token_env: BITRIX_ROP_WIDGET_TOKEN
    default_period: "7d"
    max_items: 50
  embedded_app:
    enabled: false
    portal_origin: ""
    default_role: "viewer"
    request_timeout: 10

""".strip()
        + "\n",
        encoding="utf-8",
    )

    try:
        load_settings(settings_file)
        raise AssertionError("RuntimeError expected for missing mailbox env names")
    except RuntimeError as exc:
        assert "mailbox.username_env" in str(exc)


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
  auth:
    enabled: false
    mode: beeui_session
    session_secret_env: BEEAGENT_WEB_SESSION_SECRET
    principals: []
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

i18n:
  lang: "ru"
  path: "config/i18n/ru.yml"

quiz:
  enabled: true
  path: "config/quiz/pharmacy_quiz.json"

modules:
  registry: []

rop:
  mailbox_poll:
    enabled: false
    source_id: "hotline"
  email_preview:
    body_chars_max: 4000
  attachments:
    enabled: true
    chars_max: 500
    size_max: 1048576
    types:
      - "text/plain"
    storage:
      enabled: true
      file_max_bytes: 10485760
      message_aggregate_max_bytes: 20971520
      files_max_per_message: 20
    analysis:
      provider: ""
      file_capable: false
      max_chars: 2000
  dashboard:
    default_period: "7d"
    periods:
      - today
      - yesterday
      - 7d
      - 30d
      - 365d
      - all
  ai_assist:
    enabled: false
    events_max: 20
    request_timeout: 30
    ai_confidence_min: 0.70
    dry_run: false
    adjudicator:
      enabled: false
      timeout: 20
      input_chars_max: 8000
      confidence_accept_min: 0.70
      events_max: 20
      prompt_key: "rop.ai_adjudicator"
  routing:
    queues:
      sales:
        bitrix_category: sales
      tender:
        bitrix_category: tenders
      logistics:
        bitrix_category: logistics
      finance:
        bitrix_category: finance
      procurement:
        bitrix_category: procurement
      manual_review:
        bitrix_category: manual_review
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

ai:
  prompts:
    path: "config/prompts.yml"
    store: false
  profiles:
    openai:
      enabled: true
      provider: openai_responses
      api_key_env: OPENAI_API_KEY
      base_url: "https://api.openai.com/v1"
      model: "gpt-5.4-mini"
    deepseek:
      enabled: false
      provider: openai_compatible
      api_key_env: DEEPSEEK_API_KEY
      base_url: "https://api.deepseek.com/v1"
      model: "deepseek-chat"
    lmstudio:
      enabled: false
      provider: openai_compatible
      api_key_env: LMSTUDIO_API_KEY
      base_url: "http://127.0.0.1:1234/v1"
      model: "local-model"
    custom:
      enabled: false
      provider: openai_compatible
      api_key_env: CUSTOM_AI_API_KEY
      base_url: "https://example.test/v1"
      model: "custom-model"
bitrix:
  enabled: false
  webhook_env: BITRIX_WEBHOOK_URL
  timeout: 10
  page_size: 50
  pages_max: 3
  types_entity:
    - 1
    - 2
    - 3
    - 4
  reconciliation:
    enabled: false
    candidate_limit: 20
    window_date: 180
  widget:
    enabled: false
    token_env: BITRIX_ROP_WIDGET_TOKEN
    default_period: "7d"
    max_items: 50
  embedded_app:
    enabled: false
    portal_origin: ""
    default_role: "viewer"
    request_timeout: 10
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
