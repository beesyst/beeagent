# BeeAgent — AI Agent Framework for Corp (pre-MVP)

**BeeAgent** — каркас (framework) для написания AI-агентов под корпоративные кейсы с end-to-end демо-потоком.

Текущие демо-кейсы: **OOS Detector**, **Promo Scan** и **Quiz Agent** (аптечный квиз v0).

Пайплайн демо (v0):
Telegram → cases (OOS/Promo/Quiz) → adapters (mock) + quiz-spec JSON → LangGraph workflow → report → storage artifacts

Approval (approve/reject) сейчас реализован для кейса OOS (last-run marker + tasks status в /last). Promo Scan в v0 генерирует report + артефакты, но approval для него пока не включён. Quiz Agent v0 сохраняет ответы и результат по chat_id в storage/runs/.

Проект развивается **маленькими итерациями** (см. `docs/ROADMAP.md`), соблюдая **KISS**: минимум абстракций, максимум ясности.

## Режимы работы (v0)

Сейчас реализован один режим запуска (UI transport):

* **telegram** — Telegram бот:
  * команды: `/start`, `/help`, `/run_oos`, `/run_promo`, `/last`, `/quiz_pharmacy`, `/last_quiz`
  * inline-кнопки: **Run OOS Scan**, **Run Promo Scan**, **Show Report (OOS last)**, **Approve Tasks (OOS)**, **Reject Tasks (OOS)**, + **Answer buttons** для Quiz
  * **allowlist**: доступ только одному admin chat_id (через env)

Режим задаётся в `config/settings.yml`:

* `run.mode: telegram`

Важно: **scheduled-run — это не отдельный режим**, а **trigger** выполнения кейса внутри Telegram-процесса:
* `trigger=manual` — когда запускаем `/run_oos` или кнопку
* `trigger=scheduled` — когда запускает scheduler (по интервалу)

В v0 scheduler запускает только OOS case (для демо-потока approval).

Принцип: UI-канал — тонкий слой, который вызывает только `cases/*`.

## Основные возможности (на текущий момент)

* **Telegram bot v0 (UX skeleton)**
  * отвечает на `/start` и показывает меню с кнопками
  * `/help` показывает справку
  * `/run_oos` вызывает OOS case (`cases/oos.py`), который запускает LangGraph workflow и сохраняет артефакты
  * `/last` показывает последний OOS отчёт через case (`get_last_report_case`) + summary по статусу задач и reject reason
  * `/run_promo` возвращает promo-отчёт сразу в ответ (v0), а “last report” для promo пока не ведётся
  * `/quiz_pharmacy` запускает квиз с inline-кнопками ответов; сессия по chat_id; результаты в storage/runs/<run_id>/
  * `/last_quiz` показывает последний результат квиза по chat_id
  * неизвестные команды не валят процесс (`Unknown command. Use /help.`)
  * inline-кнопки: **Run OOS Scan**, **Run Promo Scan**, **Show Report**, **Approve Tasks**, **Reject Tasks**, + **Answer buttons** для Quiz
  * scheduler v0 (опционально): периодический автозапуск OOS в том же процессе бота
    * после scheduled-run бот отправляет admin chat сообщение:
      * `New run ready → Approve/Reject`
      * `Run ID: <run_id>`
      * `Alerts: <N>, Tasks: <N>`
* **KISS security**
  * доступ только из одного admin chat_id (allowlist)
* **Артефакты**
  * `storage/reports/last_oos_report.md` — последний OOS отчёт (markdown) для `/last`
  * `storage/reports/last_run.json` — указатель на последний run_id (v0 используется OOS flow)
  * `storage/telemetry/telegram_updates.jsonl` — телеметрия событий (опционально)
  * `storage/mock/<dataset_id>/dataset.json` — сохранённый mock dataset для прогона
  * `storage/runs/<run_id>/run.json` — meta выполнения (dataset_id/seed/counts + `agent` + `adapter` + `trigger`)
  * `storage/runs/<run_id>/alerts.json` — найденные алерты (Rule A)
  * `storage/runs/<run_id>/tasks_draft.json` — draft задачи (1 task на 1 alert)
  * `storage/runs/<run_id>/tasks_approved.json` — approved/rejected задачи (v0: только для OOS после approve/reject)
  * `storage/runs/<run_id>/steps.json` — observability v0: duration_ms каждого шага workflow
  * `storage/artifacts/<run_id>/report.md` — markdown отчёт
  * `storage/artifacts/<run_id>/report.html` — HTML отчёт

> Сейчас уже есть: LangGraph workflow + run_id + approval (approve/reject) + экспорт отчётов (report.md/report.html) и полный набор run-артефактов в `storage/`.

## Где использовать

* Быстро собрать MVP агента под новый корпоративный кейс (без переписывания “с нуля”).
* Показать end-to-end UX через Telegram (или другой UI-канал в будущем).
* Текущий пример: быстрые эксперименты с правилами OOS и форматом отчёта.
* Подготовка к интеграциям с реальными данными (1C/BI позже).

## Технологический стек

* **Python 3.12+**
* **uv** — менеджер окружений/зависимостей
* **src-layout** (пакет `beeagent_module` в `src/`)
* **PyYAML** — конфиг `config/settings.yml`
* **python-telegram-bot** — Telegram polling bot
* **langgraph** — workflow-оркестрация OOS (6 узлов) и запуск через `.invoke(...)`
* **единый лог** — `logs/app.log`

## Как это работает (framework pipeline v0)

1. `start.sh` → `config/start.py` (bootstrap: env → settings → logging → run mode)
2. `core/app.py` читает `run.mode` и запускает UI-канал (сейчас: Telegram)
3. UI-канал вызывает нужный `cases/*` (сейчас реализованы demo-cases: `cases/oos.py`, `cases/promo.py`)
4. Case выбирает adapter, запускает workflow и получает результат (report + artifacts)

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
* `telegram.telemetry_enabled`: `true|false` — писать телеметрию апдейтов в `storage/telemetry/*.jsonl`

**Mock dataset**
* `mock.seed`: int — seed для детерминированного датасета
* `mock.weeks`: int — длина истории (недель)
* `mock.stores`: int — число магазинов
* `mock.skus`: int — число SKU
* `mock.category`: str — категория (например `"Vitamins"`)

**Data adapter (v0)**
* `data.adapter`: сейчас только `"mock"`
* `data.mock.dataset_id`: `str | null`
  * если `null` — при `/run_oos` dataset генерируется из `mock.*` и сохраняется в `storage/mock/<dataset_id>/dataset.json`
  * если `str` — используется уже существующий dataset в `storage/mock/<dataset_id>/dataset.json`

**Promo (v0)**
* `promo.stock_min`: int — минимальный остаток для promo-кандидатов
* `promo.units_max`: int — максимальные продажи за период

**Scheduler (v0)**
* `scheduler.enabled`: `true|false` — включить периодический автозапуск OOS
* `scheduler.interval`: `int > 0` — интервал в секундах между scheduled-run
* `scheduler.start_run`: `true|false`
  * если `true` — один scheduled-run сразу после старта, затем по интервалу
  * если `false` — только по интервалу

Поведение: после scheduled-run бот отправляет **admin-only** уведомление: `New run ready → Approve/Reject`.

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

### Run-артефакты LangGraph (v0)

Папка: `storage/runs/<run_id>/`

Файлы:
* `run.json` — meta выполнения (dataset_id/seed/counts + `agent` + `adapter` + `trigger`)
* `alerts.json` — алерты Rule A
* `tasks_draft.json` — draft задачи (1 задача на 1 алерт)
* `steps.json` — observability v0: duration_ms каждого шага workflow

### Approval + Export (v0)

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

* `src/beeagent_module/ui/telegram_bot.py` — команды, меню, allowlist, телеметрия; вызывает `cases/*` (не читает storage напрямую)

### Контракт UI (v0)

UI-каналы — тонкий transport-слой.

Контракт:
1) UI вызывает только `cases/*`.
2) `cases/*` запускают `agents/*` и готовят входные параметры.
3) `agents/*` используют `adapters/*` и пишут артефакты в `storage/`.
4) UI не читает `storage/*` напрямую.

Будущие каналы (planned):
- slack
- discord
- whatsapp

## Структура проекта

```
beeagent/
├── config/
│   ├── settings.yml                         # главный конфиг (run.mode, telegram, logging, mock)
│   └── start.py                             # bootstrap: env -> settings -> dirs -> logging -> run_app()
│
├── docs/
│   ├── ARCHITECTURE.md                      # схема модулей (core/ui/cases/adapters/domain/mock/agents/storage)
│   ├── CONTRIBUTING.md                      # правила веток/PR/Conventional Commits/release-please
│   ├── DEV_GUIDE.md                         # как запускать, дебажить, проверять
│   ├── ROADMAP.md                           # план итераций (0–N) и цели pre-MVP
│   └── SPEC.md                              # что считаем “готово” (DoD / MVP-границы)
│
├── logs/
│   └── app.log                              # единый файл логов (level/UTC/clear_logs — из settings.yml)
│
├── src/
│   └── beeagent_module/                     # основной пакет (src-layout)
│       ├── adapters/
│       │   ├── base.py                      # DataAdapter protocol
│       │   ├── factory.py                   # get_adapter(...) по settings.yml 
│       │   └── mock_adapter.py              # MockAdapter (читает storage/mock/<dataset_id>/dataset.json) 
│       │   
│       ├── agents/
│       │   └── oos/                         # demo-agent: OOS Detector (пример workflow)
│       │   │   ├── graph.py                 # nodes + persist_run (storage artifacts)
│       │   │   └── rules.py                 # правила детекции OOS (Rule A и т.п.)
│       │   │
│       ├── cases/
│       │   └── oos.py                       # demo-case: OOS (UI вызывает только cases)
│       │   
│       ├── core/
│       │   ├── app.py                       # запуск режима: читает run.mode и вызывает нужный UI/agent
│       │   ├── log.py                       # настройка логгера (stdout + app.log, UTC/local, очистка при старте)
│       │   ├── paths.py                     # вычисление корня проекта и путей (logs/, storage/)
│       │   ├── secrets.py                   # загрузка секретов из env по ключам из settings.yml 
│       │   └── settings.py                  # загрузка и fail-fast валидация settings.yml
│       │
│       ├── domain/
│       │   ├── models.py                    # доменные dataclass-модели (Store/SKU/SalesRow/...)
│       │   └── serialization.py             # сериализация доменных моделей в JSON (для dataset.json)
│       │
│       ├── mock/
│       │   └── dataset.py                   # генератор/сейв/лоад мок-датасета
│       │
│       └── ui/
│           ├── slack_stub.py                #
│           └── telegram_bot.py              # transport: команды/кнопки/allowlist/telemetry; вызывает cases/*
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
├── tests/
│   ├── test_mock_dataset.py                 # детерминизм dataset + forced anomalies + save/load
│   ├── test_smoke.py                        # базовый smoke: settings/logs/storage init
│   └── test_telegram_bot.py                 # unit-тесты команд/кнопок/allowlist/telemetry
│
├── pyproject.toml                           # зависимости, метаданные пакета, настройки tooling
├── uv.lock                                  # lock-файл зависимостей (uv)
├── start.sh                                 # единая точка запуска (KISS): uv sync -> uv run python3 config/start.py
├── README.ru.md                             # документация на русском
```

## Диагностика и тесты

### Тесты (pytest)

Запуск всех тестов:

```
pytest -q
```

Что покрыто:

* `tests/test_smoke.py` — базовая инициализация settings/logs/storage
* `tests/test_telegram_bot.py` — allowlist, команды/кнопки, `/last` (OOS), телеметрия, scheduler tick (OOS), `/run_promo`
* `tests/test_mock_dataset.py` — детерминизм мок-датасета, forced anomalies, save/load
* `tests/test_adapters_mock.py` — MockAdapter + factory get_adapter
* `tests/test_oos_graph.py` — rule A, сборка графа, workflow, артефакты, детерминизм
* `tests/test_cases_oos.py` — OOS case: run/last/approve + run-артефакты + steps.json
* `tests/test_cases_promo.py` — Promo case: run + run-артефакты + report.md/report.html

### Runtime smoke (ручная проверка)

1. Запусти:

```
bash start.sh
```

2. В Telegram (admin chat):

* `/start` — меню с кнопками
* `Run OOS Scan` — приходит отчёт (manual run)
* `/last` — приходит последний отчёт

3. Если включен scheduler (`scheduler.enabled: true`):
* дождись сообщения: `New run ready → Approve/Reject`
* проверь, что в `storage/runs/<run_id>/run.json` стоит `"trigger": "scheduled"`

4. Проверь артефакты:

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
