# BeeAgent — модульная агентная платформа с explainable orchestration

**BeeAgent** — модульная AI-платформа для корпоративных сценариев, в которой core отвечает за orchestration, state, approvals, artifacts, module loading и bounded execution/integration paths.

Проект развивается не как “чат-бот с тулзами”, а как **stateful orchestrator** с явными границами между:

- **core** — runtime, state, logs, artifacts, config, module loading;
- **modules** — доменная бизнес-логика (`beeagent-rop`, в будущем `beescan`, `merch`);
- **capabilities** — bounded integration/execution layer (MCP / n8n / внешние systems);
- **UI / transport** — Telegram сейчас, позже web / Bitrix / другие интерфейсы.

Текущий demo baseline уже существует, но теперь основной вектор развития — **module platform + first real client delivery**.

## Ключевая идея

Правильная схема работы BeeAgent:

`UI / transport → BeeAgent core → module → capability / MCP / n8n → systems`

Где:

- **BeeAgent core** держит runtime state, session/run context, approvals, artifacts и policy;
- **module** решает конкретный бизнес-кейс;
- **capability layer** даёт модулю bounded доступ к внешним данным и действиям;
- **systems** — CRM, email, 1С, workflows и другие внешние системы.

## Что уже есть сейчас

На текущем этапе BeeAgent уже умеет:

- запускаться через единый entrypoint `start.sh`;
- работать через Telegram transport;
- запускать demo-cases через `cases/*`;
- использовать mock/adapters как data boundary;
- исполнять workflow через LangGraph;
- сохранять run artifacts в `storage/`;
- вести logs в `logs/app.log`;
- поддерживать approval / reject в demo-потоке;
- хранить step timings / basic observability;
- держать несколько demo-agents (`oos`, `promo`, `quiz`);
- выдавать explainable recommendations поверх deterministic path.

## Текущий фокус проекта

Сейчас основной фокус:

1. превратить BeeAgent в **реально модульную платформу**;
2. ввести:
   - module contract
   - module registry
   - runtime context
   - artifact API
   - capability boundary
3. подключить первый реальный доменный модуль:
   - `beeagent-rop`

## Режимы работы

Сейчас реализован один runtime transport:

- **telegram** — Telegram бот / transport слой

Он используется как тонкий UI-слой и не должен содержать клиентскую бизнес-логику.

Режим задаётся в `config/settings.yml`:

```
run:
  mode: "telegram"
```

## Что такое модуль у нас

Модуль — это отдельный Python package, который подключается к BeeAgent как локальная зависимость.

Примеры:

- `beeagent-rop`
- `beescan` (planned)
- `beeagent-merch` (planned)

BeeAgent core не должен вшивать в себя клиентскую бизнес-логику.
Она должна жить в модуле.

## Что такое capability у нас

Capability — это bounded integration / execution layer.

Сюда относятся:

- MCP tools
- n8n workflows
- внешние APIs / systems
- другие подключаемые execution/data surfaces

Важно:

- доменная логика **не живёт** в MCP/n8n;
- MCP/n8n — это integration layer;
- long-running state не должен уезжать в один внешний tool call.

## Архитектурные принципы

### 1. Config is source of truth

Runtime behavior определяется через `config/settings.yml`.

### 2. Explainability first

Значимое решение должно быть объяснимо через:

- config
- logs
- artifacts

### 3. KISS

Минимум абстракций, максимум ясности.

### 4. Thin UI

UI не должен обходить cases/modules/core.

### 5. Module boundary

Клиентская бизнес-логика живёт в модуле, а не в core.

### 6. Bounded AI

AI используется как assistive layer, а не как неограниченный black box.

## Технологический стек

- **Python 3.12+**
- **uv** — управление окружением и зависимостями
- **src-layout**
- **PyYAML** — конфиг
- **python-telegram-bot** — Telegram transport
- **LangGraph** — orchestration/workflow baseline
- **file-based artifacts** — `storage/`
- **единый лог** — `logs/app.log`

## Структура проекта

```
beeagent/
├── config/
│   ├── start.py
│   ├── settings.yml
│   ├── prompts.yml
│   └── i18n/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEV_GUIDE.md
│   ├── ROADMAP.md
│   ├── SDLC.md
│   ├── SECURITY.md
│   └── SPEC.md
├── logs/
│   └── app.log
├── src/
│   └── beeagent_module/
│       ├── core/
│       ├── cases/
│       ├── agents/
│       ├── adapters/
│       ├── domain/
│       ├── mock/
│       └── ui/
├── storage/
├── tests/
├── pyproject.toml
├── start.sh
└── uv.lock
```

## Как это работает сейчас

1. `start.sh`
2. `config/start.py`
3. `core/app.py`
4. запускается transport (`telegram`)
5. transport вызывает `cases/*`
6. case запускает workflow / agent path
7. результат сохраняется в `storage/`
8. UI показывает summary / report / approve-reject flow

## Запуск

### 1. Подготовить `.env`

```
cp .env.example .env
```

Заполнить нужные переменные:

- `TELEGRAM_BOT_TOKEN`
- `CHAT_ID`
- `OPENAI_API_KEY` (если включён LLM)

### 2. Запуск

```
bash start.sh
```

`start.sh` делает:

- проверку наличия `uv`
- `uv sync`
- `uv run python3 config/start.py`

## Основные команды

Обычный запуск:

```
bash start.sh
```

Тесты:

```
uv run pytest -q
```

## Конфигурация

Главный конфиг:

- `config/settings.yml`

Ключевые блоки на текущем этапе:

- `app`
- `run`
- `telegram`
- `logging`
- `mock`
- `data`
- `scheduler`
- `approval`
- `promo`
- `recommendations`
- `llm`
- `i18n`
- `quiz`

В ближайших итерациях туда добавятся module-related sections.

## Артефакты

На текущем этапе BeeAgent пишет runtime artifacts в `storage/`, в частности:

- `storage/runs/<run_id>/...`
- `storage/artifacts/<run_id>/...`
- `storage/reports/...`
- `storage/mock/...`
- `storage/sessions/...`
- `storage/telemetry/...`

Точный текущий контракт смотри в:

- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`

## Документация

Основные документы проекта:

- `docs/ROADMAP.md` — этапы и итерации
- `docs/ARCHITECTURE.md` — архитектурные границы core/module/capability/UI
- `docs/SDLC.md` — процесс разработки и уровни изменений
- `docs/SECURITY.md` — secure development rules
- `docs/DEV_GUIDE.md` — запуск, проверки, dev flow
- `docs/SPEC.md` — текущая прикладная спецификация

## Важно про безопасность

- секреты хранятся в env, а не в репозитории;
- новые обязательные ключи должны валидироваться fail-fast;
- transport / module / capability boundaries нельзя размывать ad hoc;
- file parsing, external connectors и execution paths требуют более внимательной проверки;
- логи и artifacts не должны утекать в sensitive data.

## Статус проекта

BeeAgent уже вышел из состояния “только демо” и сейчас находится в переходе к:

- **module platform v0**
- **первому реальному клиентскому модулю**
- **Discovery → MVP → Pilot delivery path**

Первый реальный модуль в работе:

- `beeagent-rop`
