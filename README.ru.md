# BeeAgent — AI Corp Agent (pre-MVP)

**BeeAgent** — модульный AI-агент для корпоративных клиентов с end-to-end демо-потоком:

Telegram → запуск агента (OOS Detector через LangGraph) → отчёт → approval (approve/reject) → артефакты в storage

Проект развивается **маленькими итерациями** (см. `docs/ROADMAP.md`), соблюдая **KISS**: минимум абстракций, максимум ясности.

## Режимы работы (v0)

Сейчас реализован один режим запуска:

* **telegram** — Telegram бот:
  * команды: `/start`, `/help`, `/run_oos`, `/last`
  * inline-кнопки: **Run OOS Scan**, **Show Report**, **Approve Tasks**, **Reject Tasks**
  * **allowlist**: доступ только одному admin chat_id (через env)

Режим задаётся в `config/settings.yml`:

* `run.mode: telegram`

## Основные возможности (на текущий момент)

* **Telegram bot v0 (UX skeleton)**
  * отвечает на `/start` и показывает меню с кнопками
  * `/help` показывает справку
  * `/run_oos` выполняет OOS-скан через LangGraph (mock dataset), сохраняет run-артефакты и отправляет отчёт
  * `/last` показывает последний отчёт + summary по статусу задач
  * неизвестные команды не валят процесс (`Unknown command. Use /help.`)
  * inline-кнопки: **Run OOS Scan**, **Show Report**, **Approve Tasks**, **Reject Tasks**
* **KISS security**
  * доступ только из одного admin chat_id (allowlist)
* **Артефакты**
  * `storage/reports/last_oos_report.md` — последний отчёт (markdown) для `/last`
  * `storage/reports/last_run.json` — указатель на последний run_id
  * `storage/telemetry/telegram_updates.jsonl` — телеметрия событий (опционально)
  * `storage/mock/<dataset_id>/dataset.json` — сохранённый mock dataset для прогона
  * `storage/runs/<run_id>/run.json` — meta выполнения (dataset_id/seed/counts)
  * `storage/runs/<run_id>/alerts.json` — найденные алерты (Rule A)
  * `storage/runs/<run_id>/tasks_draft.json` — draft задачи (1 task на 1 alert)
  * `storage/runs/<run_id>/tasks_approved.json` — approved/rejected задачи
  * `storage/artifacts/<run_id>/report.md` — markdown отчёт
  * `storage/artifacts/<run_id>/report.html` — HTML отчёт

> Сейчас уже есть: LangGraph workflow + run_id + approval (approve/reject) + экспорт отчётов (report.md/report.html) и полный набор run-артефактов в `storage/`.

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
* **langgraph** — workflow-оркестрация OOS (6 узлов) и запуск через `.invoke(...)`
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

**Mock dataset**
* `mock.seed`: int — seed для детерминированного датасета
* `mock.weeks`: int — длина истории (недель)
* `mock.stores`: int — число магазинов
* `mock.skus`: int — число SKU
* `mock.category`: str — категория (например `"Vitamins"`)

**Approval**
* `approval.reject_reason`: str — причина для reject

> Примечание: при `/run_oos` BeeAgent генерирует и сохраняет датасет в `storage/mock/<dataset_id>/dataset.json`.

**Логирование**
* `logging.level`: `DEBUG/INFO/WARNING/ERROR/CRITICAL`
* `logging.utc`: время в UTC
* `logging.clear_logs`: чистить `logs/app.log` при старте

## Артефакты и storage (v0)

### Последний отчёт

`storage/reports/last_oos_report.md`

Пример:
```
📊 OOS Detection Report
Run ID: run-1234567890ab
Dataset: seed-42-w4-s3-k12-vitamins

🚨 Alerts: 2
  - High severity: 2
  - Affected stores: 2
  - Affected SKUs: 2

✅ Tasks: 2

Tasks status: draft=2, approved=0, rejected=0
```

### Run-артефакты LangGraph (Iteration 3)

Папка: `storage/runs/<run_id>/`

Файлы:
* `run.json` — meta выполнения (run_id, created_at, dataset_id, seed, alerts_count, tasks_count)
* `alerts.json` — алерты Rule A
* `tasks_draft.json` — draft задачи (1 задача на 1 алерт)

### Approval + Export (Iteration 4)

Папки:
* `storage/runs/<run_id>/tasks_approved.json`
* `storage/artifacts/<run_id>/report.md`
* `storage/artifacts/<run_id>/report.html`
* `storage/reports/last_run.json`

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

* `src/beeagent_module/ui/telegram_bot.py` — команды, меню, allowlist, запуск LangGraph workflow (/run_oos), телеметрия

## Структура проекта

```
beeagent/
├── pyproject.toml                           # зависимости, метаданные пакета, настройки tooling
├── uv.lock                                  # lock-файл зависимостей (uv)
├── start.sh                                 # единая точка запуска (KISS): uv sync -> uv run python3 config/start.py
├── README.ru.md                             # документация на русском
│
├── config/
│   ├── settings.yml                         # главный конфиг (run.mode, telegram, logging, mock)
│   └── start.py                             # bootstrap: env -> settings -> dirs -> logging -> run_app()
│
├── docs/
│   ├── ARCHITECTURE.md                      # схема модулей (core/ui/domain/mock/agents/storage)
│   ├── CONTRIBUTING.md                      # 
│   ├── DEV_GUIDE.md                         # как запускать, дебажить, проверять
│   ├── ROADMAP.md                           # план итераций (0–N) и цели pre-MVP
│   └── SPEC.md                              # что считаем “готово” (DoD / MVP-границы)
│
├── logs/
│   └── app.log                              # единый файл логов (level/UTC/clear_logs — из settings.yml)
│
├── src/
│   └── beeagent_module/                     # основной пакет (src-layout)
│       ├── core/
│       │   ├── app.py                       # запуск режима: читает run.mode и вызывает нужный UI/agent
│       │   ├── log.py                       # настройка логгера (stdout + app.log, UTC/local, очистка при старте)
│       │   ├── paths.py                     # вычисление корня проекта и путей (logs/, storage/)
│       │   ├── secrets.py                   # 
│       │   └── settings.py                  # загрузка и fail-fast валидация settings.yml
│       │
│       ├── domain/
│       │   ├── models.py                    # доменные dataclass-модели (Store/SKU/SalesRow/...)
│       │   └── serialization.py             # сериализация доменных моделей в JSON (для dataset.json)
│       │
│       ├── mock/
│       │   └── dataset.py                   # генератор/сейв/лоад мок-датасета (итерация 2)
│       │
│       └── ui/
│           └── telegram_bot.py              # команды/кнопки Telegram + allowlist + telemetry + мок-репорт
│ 
├── storage/
│   ├── artifacts/
│   │   └── <run_id>/                        # report.md/report.html
│   ├── mock/
│   │   └── <dataset_id>/dataset.json        # появляется при /run_oos, dataset_id детерминирован из mock params
│   ├── reports/
│   │   ├── last_oos_report.md               # последний Telegram-отчёт (для /last)
│   │   └── last_run.json                    # маркер последнего run_id
│   ├── runs/
│   │   └── <run_id>/                        # run.json/alerts.json/tasks_draft.json/tasks_approved.json
│   └── telemetry/
│       └── telegram_updates.jsonl           # телеметрия событий Telegram (опционально)
│
└── tests/
    ├── test_mock_dataset.py                 # детерминизм dataset + forced anomalies + save/load
    ├── test_smoke.py                        # базовый smoke: settings/logs/storage init
    └── test_telegram_bot.py                 # unit-тесты команд/кнопок/allowlist/telemetry
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
* `tests/test_mock_dataset.py` — детерминизм мок-датасета, forced anomalies, save/load
* `tests/test_oos_graph.py` — rule A, сборка графа, запуск workflow, создание артефактов, детерминизм по seed

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
