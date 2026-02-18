# BeeAgent — AI Сщкз Agent (pre-MVP)

**BeeAgent** — модульный AI-агент для корпоративных клиентов с end-to-end демо-потоком:

**Telegram → запуск агента (OOS Detector) → отчёт → (approval позже) → артефакты в storage**

Проект развивается **маленькими итерациями** (см. `docs/ROADMAP.md`), соблюдая **KISS**: минимум абстракций, максимум ясности.

## Режимы работы (v0)

Сейчас реализован один режим запуска:

* **telegram** — Telegram бот:
  * команды: `/start`, `/help`, `/run_oos`, `/last`
  * inline-кнопки: **Run OOS Scan**, **Show Report**
  * **allowlist**: доступ только одному admin chat_id (через env)

Режим задаётся в `config/settings.yml`:

* `run.mode: telegram`

## Основные возможности (на текущий момент)

* **Telegram bot v0 (UX skeleton)**
  * отвечает на `/start` и показывает меню с кнопками
  * `/help` показывает справку
  * `/run_oos` выполняет mock-скан OOS и сохраняет отчёт
  * `/last` показывает последний отчёт
  * неизвестные команды не валят процесс (`Unknown command. Use /help.`)
* **KISS security**
  * доступ только из одного admin chat_id (allowlist)
* **Артефакты**
  * `storage/reports/last_oos_report.md` — последний отчёт (markdown)
  * `storage/telemetry/telegram_updates.jsonl` — телеметрия событий (опционально)

> В следующих итерациях появятся: доменная модель, mock dataset, LangGraph workflow, run_id + `storage/runs/<run_id>/...`, approve/reject.

## Где использовать

* Показать end-to-end UX через Telegram.
* Быстрые эксперименты с правилами OOS и UX отчёта.
* Подготовка к этапу LangGraph + реальным интеграциям (1C позже).

## Технологический стек

* **Python 3.12+**
* **uv** — менеджер окружений/зависимостей
* **src-layout** (пакет `beeagent_module` в `src/`)
* **PyYAML** — конфиг `config/settings.yml`
* **python-telegram-bot** — Telegram polling bot
* **pytest** — тесты (`tests/`)
* **file-based storage** — артефакты в `storage/`
* **единый лог** — `logs/app.log`

## Управление и запуск

Запуск — через `start.sh` (внутри вызывает `config/start.py`).

### 1) Подготовка секретов (env)

Создай `.env` из шаблона:
```
cp .env.example .env
```

Заполни переменные:

* `TELEGRAM_BOT_TOKEN` — токен Telegram бота
* `CHAT_ID` — admin chat_id (allowlist)

> Важно: секреты не коммитим. `.env` должен быть в `.gitignore`.

### 2) Запуск

```
bash start.sh
```

`start.sh` делает:
* (если нужно) ставит `uv`
* `uv sync`
* `uv run python3 config/start.py`

---

## Конфигурация

Главный конфиг: `config/settings.yml`

### Ключевые параметры

**Run mode**
* `run.mode`: сейчас только `"telegram"`

**Telegram**
* `telegram.enabled`: `true|false`
* `telegram.bot_token_env`: имя переменной окружения для токена (например `TELEGRAM_BOT_TOKEN`)
* `telegram.chat_id_env`: имя переменной окружения для allowlist chat_id (например `CHAT_ID`)
* `telegram.telemetry_enabled`: `true|false` — писать телеметрию в jsonl

**Логирование**
* `logging.level`: `DEBUG/INFO/WARNING/ERROR/CRITICAL`
* `logging.utc`: время в UTC
* `logging.clear_logs`: чистить `logs/app.log` при старте

## Артефакты и storage (v0)

### Последний отчёт

`storage/reports/last_oos_report.md`

Пример:
```
Last OOS report
created_at: 2026-02-18T11:02:30.309645+00:00
alerts_total: 2
- STORE-001 | SKU-1001 | shelf_signal=false
- STORE-002 | SKU-1012 | shelf_signal=false
```

### Телеметрия Telegram (опционально)

`storage/telemetry/telegram_updates.jsonl` — **1 строка = 1 событие**.

Пример строки:

```
{"ts":"2026-02-18T11:02:30.309645+00:00","event":"start","update_id":77,"chat_id":1,"user_id":1,"command":"/start","callback_data":null}
```

## Архитектура (v0)

Док: `docs/ARCHITECTURE.md`

### Компоненты

1. **Bootstrap**

* `config/start.py` — загрузка `.env`, чтение `config/settings.yml`, настройка логов, запуск app

2. **Core**

* `src/beeagent_module/core/settings.py` — загрузка и fail-fast валидация YAML
* `src/beeagent_module/core/paths.py` — пути проекта (`logs/`, `storage/`)
* `src/beeagent_module/core/log.py` — stdout + `logs/app.log`
* `src/beeagent_module/core/app.py` — запуск режима `telegram`

3. **UI**

* `src/beeagent_module/ui/telegram_bot.py` — команды, меню, allowlist, mock-report, телеметрия

## Структура проекта

```
beeagent/
├── pyproject.toml
├── uv.lock
├── start.sh
├── README.ru.md
│
├── config/
│   ├── settings.yml
│   └── start.py
│
├── docs/
│   ├── SPEC.md
│   ├── ROADMAP.md
│   ├── ARCHITECTURE.md
│   ├── DEV_GUIDE.md
│   └── CONTRIBUTING.md
│
├── logs/
│   └── app.log
│
├── storage/
│   ├── reports/
│   │   └── last_oos_report.md
│   └── telemetry/
│       └── telegram_updates.jsonl
│
├── src/
│   └── beeagent_module/
│       ├── core/
│       │   ├── app.py
│       │   ├── log.py
│       │   ├── paths.py
│       │   └── settings.py
│       └── ui/
│           └── telegram_bot.py
│
└── tests/
    ├── test_smoke.py
    └── test_telegram_bot.py
```

## Диагностика и тесты

### Тесты (pytest)

Запуск всех тестов:

```
pytest -q
```

Что покрыто:

* `tests/test_smoke.py` — базовая инициализация settings/logs/storage
* `tests/test_telegram_bot.py` — allowlist, команды/кнопки, `/last`, телеметрия jsonl, unknown command

### Runtime smoke (ручная проверка)

1. Запусти:

```
bash start.sh
```

2. В Telegram (admin chat):

* `/start` — меню с кнопками
* `Run OOS Scan` — приходит отчёт
* `/last` — приходит последний отчёт

3. Проверь артефакты:

* `storage/reports/last_oos_report.md` создан/обновляется
* если включено `telegram.telemetry_enabled: true`:

  * `storage/telemetry/telegram_updates.jsonl` пополняется

## Документация

* `docs/SPEC.md` — спецификация pre-MVP
* `docs/ROADMAP.md` — итерации разработки
* `docs/ARCHITECTURE.md` — архитектура
* `docs/DEV_GUIDE.md` — dev-рутина (запуск/логи/артефакты)
* `docs/CONTRIBUTING.md` — ветки/PR/Conventional Commits/release-please

## Важно про безопасность

* Храни секреты (токены/ключи) **в env**, не в репозитории.
* Не публикуй `logs/app.log`, если там могут быть чувствительные данные.
* Если токен попал в лог/чат — **сразу ревокни** и выпусти новый (BotFather).
