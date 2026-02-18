# SPEC — BeeAgent Iteration 1 (Telegram bot v0)

## Обзор
BeeAgent v0.2.1 — каркас для pre-MVP демонстрации: Telegram UI → mock OOS-агент → отчёт → утверждение.

## Архитектура

### Структура проекта
```
beeagent/
├── config/
│   ├── start.py           # Entry point
│   └── settings.yml       # Source of truth для конфига
├── src/beeagent_module/
│   ├── core/
│   │   ├── app.py         # Выбор режима (telegram)
│   │   ├── log.py         # Логирование (stdout + file)
│   │   ├── paths.py       # Пути к logs/, storage/
│   │   └── settings.py    # Загрузка и валидация YAML
│   └── ui/
│       └── telegram_bot.py # Telegram handlers v0
├── storage/               # Артефакты (reports, telemetry)
├── logs/                  # Базовое логирование (app.log)
└── tests/
    ├── test_smoke.py      # Базовая инициализация
    └── test_telegram_bot.py  # Unit-тесты handlers
```

### Зависимости
- Python 3.12+
- pyyaml >= 6.0.1
- python-dotenv >= 1.0.1
- python-telegram-bot >= 21.7
- pytest >= 8.3.0

## Конфигурация

### settings.yml (источник правды)
```yaml
app:
  name: "BeeAgent"
  env: "dev"

run:
  mode: "telegram"  # единственный поддерживаемый режим (Iteration 1)

telegram:
  enabled: true
  bot_token: "REPLACE_WITH_TELEGRAM_BOT_TOKEN"  # прямое значение
  chat_id: 123456789                            # allowlist: один admin чат
  telemetry_enabled: true                       # запись событий в jsonl

logging:
  clear_logs: true   # перезаписывать logs/app.log при каждом старте
  utc: true          # каноническое время (UTC)
  level: "INFO"      # уровень логирования
```

### Переменные окружения
- `.env` → `dotenv_path` (опционально, для future-проофинга)

### Fail-fast валидация
Обязательные ключи в `settings.py`:
- `app.name` (str), `app.env` (str)
- `run.mode` (str)
- `telegram.enabled` (bool), `telegram.bot_token` (str), `telegram.chat_id` (int), `telegram.telemetry_enabled` (bool)
- `logging.clear_logs` (bool), `logging.utc` (bool), `logging.level` (str)

Если ключ отсутствует или имеет не тот тип → ошибка при старте, без дефолтов.

## Telegram UI (v0)

### Команды
| Команда | Логика | Результат |
|---------|--------|-----------|
| `/start` | Проверяет allowlist → показывает главное меню | Inline-кнопки: Run OOS Scan, Show Report |
| `/help` | Список всех команд | Текст с описанием |
| `/run_oos` | Генерирует mock-отчет → сохраняет в storage | Текст отчёта |
| `/last` | Читает последний отчет из storage | Текстовый отчёт или "No reports yet" |

### Inline-кнопки
- **Run OOS Scan** → вызывает логику `/run_oos` (запись и отправка отчёта)
- **Show Report** → вызывает логику `/last` (чтение последнего отчёта)

### Allowlist (KISS security)
- Один `chat_id` из `settings.yml` считается администратором.
- Сообщение от другого чата → ответ "Access denied: admin chat only." и лог `warning`.
- Неизвестная команда на admin-чате → лог и ответ "Unknown command. Use /help."
- Неизвестная команда на non-admin-чате → лог и allowlist-ответ.

### Mock-отчет
```
Last OOS report
created_at: 2026-02-18T06:51:37.123456+00:00
alerts_total: 2
- STORE-001 | SKU-1001 | shelf_signal=false
- STORE-002 | SKU-1012 | shelf_signal=false
```
Сохраняется в `storage/reports/last_oos_report.md`.

### Телеметрия (опционально)
При `telemetry_enabled: true` событие пишется в `storage/telemetry/telegram_updates.jsonl` как JSON-строка:
```json
{"ts":"2026-02-18T06:51:37.123456+00:00","event":"start","update_id":77,"chat_id":123456789,"user_id":123456789,"command":"/start","callback_data":null}
```

Поля:
- `ts` — ISO 8601 UTC
- `event` — "start", "help", "run_oos", "last", "button", "unknown_command"
- `update_id` — Telegram update ID
- `chat_id`, `user_id` — ID чата и пользователя
- `command` — текст сообщения (если есть)
- `callback_data` — данные кнопки (если есть)

## Запуск

### bash start.sh
1. Проверяет/устанавливает `uv`
2. Синхронизирует зависимости: `uv sync`
3. Запускает `python3 config/start.py`

### Ожидаемый вывод (с `TELEGRAM_BOT_TOKEN` установленным)
```
[run] syncing dependencies...
[run] starting BeeAgent...
2026-02-18 06:51:37 [INFO] - [app] BeeAgent started
2026-02-18 06:51:37 [INFO] - [app] mode=telegram
2026-02-18 06:51:37 [INFO] - [app] telegram mode started
2026-02-18 06:51:37 [INFO] - [app] telegram.enabled=True
2026-02-18 06:51:37 [INFO] - [app] telegram bot polling started
# ждёт входящих сообщений и кнопок...
```

### Без токена
```
RuntimeError: Telegram bot_token is empty in settings
```

## Тестирование

### pytest -q
```
tests/test_smoke.py::test_smoke_startup_initialization
tests/test_telegram_bot.py::test_start_denies_non_admin
tests/test_telegram_bot.py::test_run_oos_then_last_report
tests/test_telegram_bot.py::test_buttons_call_same_handlers
tests/test_telegram_bot.py::test_unknown_command_does_not_crash
tests/test_telegram_bot.py::test_telemetry_writes_jsonl
```

Все тесты — unit-level без Telegram API; используются fake objects для Message, CallbackQuery, Update, Context.

### Smoke тест
Проверяет инициализацию settings, логов и storage создаются корректно.

## DoD (Definition of Done)

- [x] `bash start.sh` стартует без ошибок (при наличии bot_token в settings).
- [x] Бот отвечает на `/start`, `/help`, `/run_oos`, `/last`.
- [x] Inline-кнопки вызывают те же обработчики, что и команды.
- [x] Allowlist: non-admin получает отказ, admin видит меню.
- [x] Неизвестная команда → понятный ответ, без падения.
- [x] Mock-отчет сохраняется в `storage/reports/last_oos_report.md`.
- [x] Телеметрия пишется в `storage/telemetry/telegram_updates.jsonl` при `telemetry_enabled: true`.
- [x] `pytest -q` проходит без ошибок.

## TODO (Iteration 2+)

- Модели доменов (Store, SKU, SalesRow, StockRow, ShelfSignal, Alert, Task, RunMeta).
- Генератор моков для воспроизводимых данных.
- LangGraph workflow для OOS-детектора.
- Buttons для approve/reject задач.
- Export: HTML/XLSX отчёты.
- Data adapter interface для подключения 1С.
