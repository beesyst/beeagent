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
- выдавать explainable recommendations поверх deterministic path;
- иметь internal module contract v0 для внешних доменных модулей;
- загружать package-based модули через config-driven registry;
- передавать модулю runtime context через core execution path;
- давать модулю core-managed artifact API для module-linked artifacts;
- иметь capability boundary v0 для bounded external calls;
- вызывать первый реальный внешний модуль `beeagent-rop` через registry/runtime path;
- запускать первый ROP operator flow через Telegram command `/run_rop`;
- писать operator-facing artifact `operator_summary.json`.

## Текущий фокус проекта

BeeAgent уже прошёл этап **module platform v0**:

- module contract v0 введён;
- module registry v0 введён;
- runtime context v0 введён;
- artifact API v0 введён;
- capability boundary v0 введён;
- `beeagent-rop` подключён как первый реальный package-based модуль через registry/runtime path.

Текущий фокус:

1. стабилизировать `beeagent-rop` operator flow после первого Telegram path `/run_rop`;
2. улучшить operator-facing summary и artifacts для Discovery → MVP → Pilot;
3. подготовить controlled client input path вместо demo payload;
4. не переносить клиентскую бизнес-логику в BeeAgent core.

## Режимы работы

Сейчас основной runtime mode:

- **telegram** — Telegram bot / transport layer.

`run.mode` отвечает за то, какой transport/runtime запускается при старте приложения.  
Он не выбирает доменный модуль и не должен превращаться в список клиентских сценариев.

Режим задаётся в `config/settings.yml`:

```
run:
  mode: "telegram"
```

ROP запускается не отдельным `run.mode`, а как operator action внутри transport:

```
/run_rop
```

То есть:

- `telegram` — слой взаимодействия с оператором;
- `/run_rop` — команда внутри Telegram;
- `beeagent-rop` — доменный модуль;
- `run_rop_operator_case(...)` — BeeAgent-owned case wrapper, который вызывает модуль и собирает operator-facing output.

## Что такое модуль у нас

Модуль — это отдельный Python package, который подключается к BeeAgent как локальная зависимость.

Примеры:

- `beeagent-rop`
- `beescan` (planned)
- `beeagent-merch` (planned)

BeeAgent core не должен вшивать в себя клиентскую бизнес-логику.
Она должна жить в модуле.

На текущем этапе в core уже введён минимальный internal module contract v0.

Он фиксирует базовые platform-level expectations для доменного модуля:

- `module_id`
- `supported_case_types()`
- `handle(context)`
- bounded authority semantics:
  - `read_only`
  - `draft_only`
  - `execution_capable`

Registry v0, runtime context v0, artifact API v0 и capability boundary v0 уже введены в core.

На текущем этапе первый реальный модуль `beeagent-rop` уже может:

- загружаться через `modules.registry`;
- проходить `ModuleContract` compatibility check;
- вызываться через `execute_module_case(...)`;
- получать `ModuleContext`;
- писать module-linked artifacts через `ArtifactAPI`;
- возвращать canonical `ModuleResult` в BeeAgent runtime.

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

Базовый runtime-flow остаётся таким:

1. `start.sh`
2. `config/start.py`
3. `core/app.py`
4. запускается transport (`telegram`)
5. transport принимает operator command
6. command вызывает соответствующий `case`
7. case запускает workflow / module runtime path
8. результат сохраняется в `storage/`
9. UI показывает summary / report / operator-facing output

Для внешних доменных модулей добавлен module execution path:

1. `config/settings.yml` объявляет модуль в `modules.registry`;
2. `core/app.py` строит registry и пишет diagnostics artifact;
3. `ModuleRegistry` загружает package-based модуль;
4. `execute_module_case(...)` создаёт runtime context;
5. BeeAgent передаёт модулю `ModuleContext`;
6. модуль выполняет доменную логику;
7. модуль пишет свои outputs через `ArtifactAPI`;
8. BeeAgent пишет canonical `module_result.json`.

Пример текущего первого реального модуля:

- `beeagent-rop`

Для ROP operator flow текущий путь такой:

1. оператор запускает команду `/run_rop` в Telegram;
2. Telegram handler вызывает `run_rop_operator_case(...)`;
3. BeeAgent строит module registry из `modules.registry`;
4. `execute_module_case(...)` вызывает `beeagent-rop`;
5. модуль возвращает `ModuleResult`;
6. BeeAgent пишет module-linked artifacts;
7. operator wrapper пишет `operator_summary.json`;
8. Telegram возвращает оператору readable `operator_text`.

На текущем этапе `/run_rop` использует explicit demo payload.
Production email / Bitrix / CRM input path пока не входит в scope.

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

- проверку наличия `uv`;
- `uv sync`;
- `uv run python3 config/start.py`.

## Основные команды

Обычный запуск:

```
bash start.sh
```

При текущем config:

```
run:
  mode: "telegram"
```

BeeAgent стартует Telegram transport. Если `telegram.enabled: false`, приложение корректно инициализирует registry, пишет diagnostics artifact и не запускает polling.

ROP operator flow запускается через Telegram command:

```
/run_rop
```

Тесты:

```
uv run pytest -q
```

Локальный smoke operator flow можно выполнять через тесты или прямой вызов `run_rop_operator_case(...)` в dev-сценариях. Отдельный `run.mode: "rop_operator_v0"` больше не используется.

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
- `modules`

`run.mode` сейчас выбирает runtime/transport, а не доменный модуль:

```
run:
  mode: "telegram"
```

Доменные модули подключаются отдельно через `modules.registry`.

Пример:

```
modules:
  registry:
    - id: "beeagent-rop"
      package: "beeagent_rop"
      entry: "RopModule"
      enabled: true
```

## Артефакты

На текущем этапе BeeAgent пишет runtime artifacts в `storage/`, в частности:

- `storage/runs/<run_id>/...`
- `storage/runs/<run_id>/module-<module_id>/...`
- `storage/runs/<run_id>/module-<module_id>/module_result.json`
- `storage/artifacts/<run_id>/...`
- `storage/reports/...`
- `storage/mock/...`
- `storage/sessions/...`
- `storage/telemetry/...`
- `storage/interfaces/modules.json`
- optional `storage/interfaces/capabilities.json`

Для `beeagent-rop` текущий ROP operator flow пишет:

- `storage/runs/<run_id>/operator_summary.json`
- `storage/runs/<run_id>/module-beeagent-rop/module_result.json`
- `storage/runs/<run_id>/module-beeagent-rop/lead_classification_result.json`

`operator_summary.json` — BeeAgent-level operator artifact.
`module_result.json` и `<case_type>_result.json` — module-linked artifacts.

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

BeeAgent уже вышел из состояния “только демо”.

Текущий статус:

- **demo skeleton** — DONE;
- **reusable orchestration core** — DONE;
- **module platform v0** — DONE;
- **first real client module integration** — DONE;
- **first client/operator flow** — IN PROGRESS.

Первый реальный модуль:

- `beeagent-rop`

Текущий практический результат:

- `beeagent-rop` загружается через registry;
- BeeAgent может вызвать `beeagent-rop` через `execute_module_case(...)`;
- Telegram command `/run_rop` запускает первый ROP operator flow;
- linkage `run → operator_summary → module outputs` виден в artifacts;
- production Bitrix/email/attachment connectors пока не входят в scope;
- CRM write-back пока не входит в scope.
