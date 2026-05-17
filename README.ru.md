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
- писать operator-facing artifact `operator_summary.json`;
- запускать ROP flow через configurable `json_batch` input source и писать intake/normalized/operator artifacts;
- запускать ROP flow через configurable `mailbox_readonly` source для controlled read-only mailbox smoke;
- после source normalization классифицировать каждое ROP event через `beeagent-rop` case `lead_classification`;
- сохранять batch-level classification artifact `classified_events.json`;
- передавать в `beeagent-rop` case `rop_summary` уже classified events, а не raw normalized events;
- писать source-level diagnostics artifact `source_diagnostics.json`.

## Текущий фокус проекта

BeeAgent уже прошёл этап **module platform v0**:

- module contract v0 введён;
- module registry v0 введён;
- runtime context v0 введён;
- artifact API v0 введён;
- capability boundary v0 введён;
- `beeagent-rop` подключён как первый реальный package-based модуль через registry/runtime path.

Итерация 17 добавила:

- config-driven `rop.sources` contract в `config/settings.yml`;
- `json_batch` source type с load/validate/normalize flow;
- `run_rop_batch_case(...)` — BeeAgent-owned batch handoff case без отдельного `run.mode`;
- артефакты `intake_metadata.json` и `normalized_events.json` per run;
- sample batch file `storage/mock/rop_batch_sample.json`.

Итерация 18 добавила:

- `mailbox_readonly` source type в existing `rop.sources` contract;
- read-only mailbox ingestion через stdlib `imaplib` без destructive mailbox actions;
- `source_diagnostics.json` для explainable degraded/ok source behavior;
- safe mailbox normalization в operator-facing artifacts без raw `.eml` и без attachment content.

Итерация 19 добавила:

- per-event classification handoff внутри ROP source flow;
- вызов `beeagent-rop` case `lead_classification` для каждого normalized event;
- artifact `classified_events.json`;
- вызов `beeagent-rop` case `rop_summary` уже по classified events;
- classification diagnostics в `operator_summary.json`;
- controlled fallback для per-event classification failure без падения всего batch.

Добавлено:

- ROP CLI entrypoint: `./start.sh rop run/summary/export-review`;
- in-memory source overrides через CLI args: `--source-id`, `--items-max`, `--period`, `--run-id`;
- `rop run` запускает ROP batch pipeline без Telegram и автоматически экспортирует TSV для human review;
- `rop summary` показывает readable summary для готового run;
- `rop export-review` остаётся ручным повторным экспортом TSV для уже существующего run без raw тел писем;
- backward compatibility: `./start.sh` и `./start.sh telegram` работают как раньше.

Текущий фокус:

1. использовать `json_batch` как controlled offline/batch MVP path;
2. использовать `mailbox_readonly` как controlled read-only mailbox smoke path для `hotline`;
3. строить ROP summary только после per-event `lead_classification`;
4. не превращать mailbox smoke в production listener/stream без отдельной итерации;
5. сохранить границу: BeeAgent отвечает за source/orchestration/artifacts, `beeagent-rop` — за ROP business logic.

## Режимы работы и CLI

Сейчас основной runtime mode:

- **telegram** — Telegram bot / transport layer.

`run.mode` отвечает за то, какой transport/runtime запускается при старте приложения.  
Он не выбирает доменный модуль и не должен превращаться в список клиентских сценариев.

Режим задаётся в `config/settings.yml`:

```
run:
  mode: "telegram"
```

### Entrypoint

```bash
# Использует run.mode из settings.yml
./start.sh

# Явный Telegram mode
./start.sh telegram

# ROP CLI для batch pipeline
./start.sh rop run [--source-id SOURCE] [--items-max N] [--period YYYY-MM] [--run-id ID]
./start.sh rop summary --run-id ID
./start.sh rop export-review --run-id ID [--format tsv]
```

### ROP CLI (v1, Iteration 20)

Для запуска ROP flow без Telegram можно использовать CLI:

```
# Запустить ROP batch через default enabled source из config/settings.yml.
# Сейчас это может быть hotline_mailbox, если он включён в rop.sources.
./start.sh rop run --items-max 20 --period 2026-05

# Запустить ROP batch через конкретный source_id.
./start.sh rop run \
  --source-id hotline_mailbox \
  --items-max 20 \
  --period 2026-05 \
  --run-id live-review-2026-05-15

# Показать summary по готовому run.
./start.sh rop summary --run-id live-review-2026-05-15

# Повторно экспортировать TSV для human review по готовому run.
# Обычно не требуется, потому что rop run уже создаёт rop_review_table.tsv автоматически.
./start.sh rop export-review --run-id live-review-2026-05-15 --format tsv
```

После `rop run` создаётся:

```
storage/runs/<run_id>/rop_review_table.tsv
```

Этот TSV можно открыть или скопировать в Google Sheets для human review.

Для dev-запуска через `rop_batch_sample` нужно вручную включить этот source в `config/settings.yml`:

```
rop:
  sources:
    - source_id: "rop_batch_sample"
      enabled: true
```

По умолчанию `rop_batch_sample` может быть выключен, чтобы случайно не заменить live/source smoke path.

Параметры:

- `--source-id` — выбрать источник данных из `rop.sources`
- `--items-max` — override max items для источника
- `--period` — override period для batch источника
- `--run-id` — explicit run_id (если не указан, генерируется)
- `--format` — формат export (пока только `tsv`)

CLI overrides применяются только в памяти, не меняют `config/settings.yml`.

### ROP в Telegram

Если оставить `run.mode: "telegram"`, ROP также доступен как Telegram command:

```
/run_rop
```

Результат выводится как readable summary в Telegram.

### Разница: Telegram vs CLI

| Aspect        | Telegram                          | CLI                                                           |
| ------------- | --------------------------------- | ------------------------------------------------------------- |
| Transport     | Telegram bot                      | Console                                                       |
| Approval      | Interactive buttons               | No approval (CLI для MVP)                                     |
| Ideal for     | Interactive operator              | Batch processing, scripts                                     |
| Config        | `run.mode: "telegram"`            | CLI args override                                             |
| Artifacts     | Standard: `operator_summary.json` | Standard: same                                                |
| Review export | Не основной путь                  | Auto TSV on `rop run`; manual rerun через `rop export-review` |

ROP запускается не отдельным `run.mode`, а как operator action внутри transport:

```
/run_rop
```

То есть:

- `telegram` — слой взаимодействия с оператором;
- `/run_rop` — команда внутри Telegram;
- `./start.sh rop run` — команда в CLI;
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

На текущем этапе есть два ROP input path:

1. `/run_rop` — operator command с explicit demo payload;
2. `run_rop_batch_case(...)` — controlled source path через `rop.sources`, `json_batch` и `mailbox_readonly`.

`run_rop_batch_case(...)` выполняет batch pipeline:

```
configured source
→ source_diagnostics.json
→ intake_metadata.json
→ normalized_events.json
→ beeagent-rop lead_classification per event
→ classified_events.json
→ beeagent-rop rop_summary
→ operator_summary.json
→ rop_review_table.tsv, если flow запущен через ROP CLI
```

`run_rop_batch_case(...)` не является отдельным `run.mode`: `run.mode` остаётся transport/runtime selector.

Production Bitrix / 1C / CRM input path пока не входит в scope.
Email ingestion сейчас ограничен `mailbox_readonly` smoke: read-only fetch latest N messages без polling/listener, OCR, attachment deep parsing, raw `.eml` persistence и CRM write-back.

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

ROP operator flow доступен двумя путями:

```bash
# Telegram operator command
/run_rop

# CLI batch flow без Telegram
./start.sh rop run --items-max 20 --period 2026-05
```

Для CLI batch flow после успешного запуска создаётся `rop_review_table.tsv`:

```text
storage/runs/<run_id>/rop_review_table.tsv
```

Тесты:

```
uv run pytest -q
```

Локальный smoke operator flow можно выполнять через:

- `./start.sh rop run`;
- `./start.sh rop summary --run-id <run_id>`;
- `./start.sh rop export-review --run-id <run_id> --format tsv`;
- тесты;
- прямой вызов `run_rop_operator_case(...)` только в dev-сценариях.

Отдельный `run.mode: "rop_operator_v0"` больше не используется.

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
- `rop`

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

ROP input sources задаются отдельно через `rop.sources`.

Пример controlled batch source:

```
rop:
  sources:
    - source_id: "rop_batch_sample"
      source_type: "json_batch"
      enabled: true
      authority: "read_only"
      items_max: 100
      batch:
        path: "storage/mock/rop_batch_sample.json"
        period: "2026-05"
```

Пример controlled read-only mailbox source:

```
rop:
  sources:
    - source_id: "hotline_mailbox"
      source_type: "mailbox_readonly"
      enabled: false
      authority: "read_only"
      items_max: 10
      mailbox:
        host: "imap.example.com"
        port: 993
        use_ssl: true
        folder: "INBOX"
        username_env: "ROP_MAILBOX_USERNAME"
        password_env: "ROP_MAILBOX_PASSWORD"
```

Для `mailbox_readonly` в config хранятся только имена env-переменных.
Сами credentials должны лежать в `.env` / runtime env и не должны попадать в logs или artifacts.

`mailbox_readonly` используется только для read-only smoke:

- fetch latest N messages;
- no delete;
- no archive;
- no reply;
- no mark-as-read;
- no raw `.eml` persistence;
- attachment metadata only, без чтения content.

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
- `storage/runs/<run_id>/module-beeagent-rop/<case_type>_result.json`

Для ROP source flow дополнительно пишутся:

- `storage/runs/<run_id>/source_diagnostics.json`
- `storage/runs/<run_id>/intake_metadata.json`
- `storage/runs/<run_id>/normalized_events.json`
- `storage/runs/<run_id>/classified_events.json`
- `storage/runs/<run_id>/module-beeagent-rop/rop_summary_result.json`, если выполняется `rop_summary`
- `storage/runs/<run_id>/rop_review_table.tsv`, если flow запущен через ROP CLI или выполнена команда `rop export-review`

`classified_events.json` — BeeAgent-owned batch artifact, который содержит результаты per-event `lead_classification` и используется как input для `rop_summary`.
`rop_review_table.tsv` — BeeAgent-owned review artifact для ручной сверки с человеком / заказчиком. Он строится из `normalized_events.json` и `classified_events.json`, не содержит raw `.eml` и предназначен для загрузки в Google Sheets или аналогичную таблицу.

Важно: per-event `lead_classification_result.json` внутри `module-beeagent-rop/` может перезаписываться существующим module runtime path. Batch-level evidence для классификации находится в `classified_events.json`.

`operator_summary.json` — BeeAgent-level operator artifact.
`source_diagnostics.json` — BeeAgent-owned source status / degraded diagnostics artifact.
`intake_metadata.json` и `normalized_events.json` — BeeAgent-owned input/source artifacts.
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
- **first client/operator flow** — DONE;
- **controlled batch MVP path** — DONE;
- **live read-only mailbox smoke** — DONE;
- **ROP live batch classification handoff** — DONE;
- **ROP CLI and review export** — DONE.

Первый реальный модуль:

- `beeagent-rop`

Текущий практический результат:

- `beeagent-rop` загружается через registry;
- BeeAgent может вызвать `beeagent-rop` через `execute_module_case(...)`;
- Telegram command `/run_rop` запускает первый ROP operator flow;
- `run_rop_batch_case(...)` запускает ROP source flow через configurable `rop.sources`;
- `mailbox_readonly` получает последние N писем из configured mailbox source в read-only режиме;
- BeeAgent пишет `source_diagnostics.json`, `intake_metadata.json`, `normalized_events.json`, `classified_events.json`, `operator_summary.json` и `rop_review_table.tsv` при CLI run/export;
- linkage `run → intake/normalized artifacts → operator_summary → module outputs` виден в artifacts;
- production Bitrix/email/attachment connectors пока не входят в scope;
- live mailbox ingestion не делает destructive mailbox actions и не сохраняет raw `.eml`;
- CRM write-back пока не входит в scope.
