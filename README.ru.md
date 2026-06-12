# BeeAgent — модульная агентная платформа с explainable orchestration

**BeeAgent** — модульная AI-платформа для корпоративных сценариев, в которой core отвечает за orchestration, state, approvals, artifacts, module loading и bounded execution/integration paths.

Проект развивается не как “чат-бот с тулзами”, а как **stateful orchestrator** с явными границами между:

- **core** — runtime, state, logs, artifacts, config, module loading;
- **modules** — доменная бизнес-логика (`beeagent-rop`, в будущем `beescan`, `merch`);
- **capabilities** — bounded integration/execution layer (MCP / n8n / внешние systems);
- **UI / transport** — Telegram и read-only Web Console сейчас, позже Bitrix / другие интерфейсы.

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
- запускать BeeUI-backed read-only Operator Web Console через `./start.sh web`;
- использовать BeeUI поверх FastAPI/Jinja2/Tabler как canonical web layer;
- читать existing artifacts через BeeAgent UI adapter/read-model/artifact allowlist;
- использовать локальные BeeUI/static assets без CDN и npm runtime;
- показывать список runs, run overview, module diagnostics и ROP dashboard поверх existing artifacts;
- отдавать read-only JSON API поверх existing artifacts;
- сохранять allowlist-based artifact access, bounded previews и sanitization;
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
- запускать ROP source flow через explicit `--source-id` или все enabled sources через `--all-sources`;
- писать aggregate/per-source diagnostics для multi-source run;
- сохранять source metadata в normalized/classified/operator/TSV artifacts;
- показывать partial degradation одного source без падения всего run, если хотя бы один source успешно загрузился.

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
- `rop export-review` остаётся ручным повторным экспортом TSV для уже существующего run без raw `.eml`, raw email bodies и attachment content;
- backward compatibility: `./start.sh` и `./start.sh telegram` работают как раньше;
- расширенный `rop_review_table.tsv` для human review;
- `body_short`, `attachments`, `bot_priority`, `bot_reasoning`;
- Bitrix/duplicate placeholder columns для будущей сверки;
- sanitized/bounded TSV export без raw `.eml` и attachment content;
- BeeUI-backed read-only Operator Web Console через `./start.sh web`;
- BeeUI embedded app как canonical web layer поверх FastAPI/Jinja2/Tabler;
- HTML routes `/`, `/health`, `/runs`, `/runs/<run_id>`, `/rop`, `/modules`;
- JSON API routes `/api/dashboard`, `/api/runs`, `/api/runs/<run_id>`, `/api/rop/dashboard`, `/api/modules`;
- artifact JSON routes `/runs/<run_id>/artifacts`, `/runs/<run_id>/artifacts/<artifact_id>`, `/api/runs/<run_id>/artifacts`, `/api/runs/<run_id>/artifacts/<artifact_id>`;
- allowlisted artifact access по `artifact_id` с bounded/redacted JSON preview;
- protection from path traversal and raw `.eml` / `message/rfc822` exposure.

Итерация 24 добавила:

- explicit multi-source ingestion в BeeAgent core без изменений `beeagent-rop`;
- `./start.sh rop run --all-sources` для запуска всех enabled sources;
- `selection_mode` для фиксации default / explicit single-source / all-sources режима;
- `aggregate` + `sources[]` в source/intake artifacts;
- source traceability в `normalized_events.json`, `classified_events.json` и `rop_review_table.tsv`;
- partial degradation одного source без падения всего run, если хотя бы один source успешно загрузился.

Текущий фокус:

1. использовать `rop.sources` как source of truth для single-source и multi-source ROP ingestion;
2. запускать ROP MVP pipeline через CLI (`--source-id` или `--all-sources`), а результат смотреть через Operator Web Console;
3. использовать `source_diagnostics.json`, `intake_metadata.json`, dashboard/TSV для human review и фиксации ошибок классификации/source degradation;
4. не превращать mailbox smoke в production listener/stream без отдельной итерации;
5. сохранить границу: BeeAgent отвечает за source/orchestration/artifacts/UI, `beeagent-rop` — за ROP business logic.

## Режимы работы и CLI

Сейчас основной runtime mode:

- **telegram** — Telegram bot / transport layer.
- **web** — read-only operator web console поверх existing artifacts.

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

# Явный Web mode (read-only dashboard)
./start.sh web

# ROP CLI для batch pipeline
./start.sh rop run [--source-id SOURCE | --all-sources] [--items-max N] [--period YYYY-MM] [--run-id ID]
./start.sh rop summary --run-id ID
./start.sh rop export-review --run-id ID [--format tsv]
```

### Operator Web Console v0 (UI-4 BeeUI-backed)

Read-only web console запускается отдельной командой:

```bash
./start.sh web
```

CLI overrides:

```bash
./start.sh web --host 127.0.0.1 --port 8780 --no-open
```

Route listing diagnostic:

```bash
./start.sh routes
```

Web Console построен на BeeUI как canonical web layer поверх FastAPI + Jinja2 + Tabler.

Доступные HTML маршруты:

- `/` — dashboard
- `/health` — health check
- `/runs` — run history
- `/runs/<run_id>` — run detail
- `/rop` — ROP operator dashboard
- `/modules` — module diagnostics

JSON API маршруты:

- `/api/dashboard`
- `/api/runs`
- `/api/runs/<run_id>`
- `/api/modules`
- `/api/rop/dashboard`

Artifact JSON маршруты:

- `/runs/<run_id>/artifacts`
- `/runs/<run_id>/artifacts/<artifact_id>`
- `/api/runs/<run_id>/artifacts`
- `/api/runs/<run_id>/artifacts/<artifact_id>`

Web console только читает existing artifacts из `storage/runs/<run_id>/...` и `storage/interfaces/modules.json`.
Доступ к артефактам идёт по allowlisted `artifact_id`, а не по произвольным именам файлов.
Artifact routes возвращают bounded/redacted JSON preview.
Источник правды для bind/runtime настроек остаётся `config/settings.yml` → `web.host`, `web.port`, `web.open_browser`.

В scope v0 не входят:

- login/auth;
- web-triggered `rop run`;
- POST/write actions;
- mailbox/CRM actions;
- attachment content parsing;
- production deployment hardening.

### ROP CLI

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

# Запуск всех enabled источников за один run
./start.sh rop run --all-sources --items-max 20 --period 2026-05

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
- `--all-sources` — запустить все enabled источники из `rop.sources`
- `--items-max` — override max items для источника
- `--period` — override period для batch источника
- `--run-id` — explicit run_id (если не указан, генерируется)
- `--format` — формат export (пока только `tsv`)

CLI overrides применяются только в памяти, не меняют `config/settings.yml`.
`--source-id` и `--all-sources` взаимоисключающие.

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

- **Python 3.14+**
- **uv** — управление окружением и зависимостями
- **src-layout**
- **PyYAML** — конфиг
- **python-telegram-bot** — Telegram transport
- **LangGraph** — orchestration/workflow baseline
- **BeeUI** — canonical Web Console layer
- **FastAPI** — runtime foundation для BeeUI-backed Web Console
- **Uvicorn** — ASGI runtime для Web Console
- **Jinja2** — template/runtime layer, используемый через BeeUI и legacy frozen web shell
- **Tabler assets** — локальные UI assets через BeeUI и legacy frozen web shell, без CDN и npm runtime
- **file-based artifacts** — `storage/`
- **единый лог** — `logs/app.log`

## Структура проекта

```
beeagent/
├── config/
│   ├── start.py
│   ├── beeui.yml
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
│       ├── cli/
│       ├── core/
│       ├── cases/
│       ├── agents/
│       ├── adapters/
│       ├── domain/
│       ├── interfaces/ui/
│       ├── mock/
│       └── web/        # legacy frozen web shell
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

Для web console текущий путь такой:

1. `start.sh web`;
2. `config/start.py`;
3. `beeagent_module.cli.web.run_web`;
4. `interfaces/ui/app.py`;
5. embedded BeeUI app;
6. BeeAgent UI adapter/read-model/artifact allowlist;
7. existing artifacts из `storage/`;
8. read-only HTML/API operator view без мутаций.

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
configured source(s)
→ source_diagnostics.json
→ intake_metadata.json
→ attachment_extraction.json
→ normalized_events.json
→ beeagent-rop lead_classification per event
→ classified_events.json
→ beeagent-rop rop_summary
→ operator_summary.json
→ rop_review_table.tsv, если flow запущен через ROP CLI
```

Для multi-source run `source_diagnostics.json` и `intake_metadata.json` содержат aggregate block и `sources[]` с per-source rollup.

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
- инициализацию `.env` из `.env.example`, если `.env` отсутствует;
- `uv sync --frozen`;
- `uv run --frozen python3 config/start.py "$@"`.

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
      source_role: "batch_sample"
      client_id: "welding"
      display_name: "ROP Batch Sample"
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
      source_role: "technical_aggregator"
      client_id: "welding"
      display_name: "Welding Hotline mailbox"
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

Обязательный source profile contract для каждого `rop.sources[]`:

- `source_role`
- `client_id`
- `display_name`

Эти поля валидируются fail-fast в `core/settings.py` и прокидываются в BeeAgent-owned artifacts как `source_role`, `client_id`, `source_display_name`.

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

Для multi-source run:

- `source_diagnostics.json` содержит `selection_mode`, `aggregate` и `sources[]`;
- `intake_metadata.json` содержит aggregate counts и `sources[]`;
- `normalized_events.json` и `classified_events.json` сохраняют source traceability per event;
- `operator_summary.json` содержит aggregate source summary и per-source rollup;
- `rop_review_table.tsv` содержит source-aware columns.

`classified_events.json` — BeeAgent-owned batch artifact, который содержит результаты per-event `lead_classification` и используется как input для `rop_summary`.
`rop_review_table.tsv` — BeeAgent-owned review artifact для ручной сверки с человеком / заказчиком. Он строится из `normalized_events.json` и `classified_events.json`, не содержит raw `.eml` и предназначен для загрузки в Google Sheets или аналогичную таблицу.

**Структура `rop_review_table.tsv` (v1):**

`rop_review_table.tsv` содержит 26 tab-separated колонок для быстрой human review:

| Column                | Source            | Description                                                                         |
| --------------------- | ----------------- | ----------------------------------------------------------------------------------- |
| `event_id`            | normalized_events | Уникальный ID события                                                               |
| `source_id`           | intake_metadata   | Источник данных (rop_batch_sample, hotline_mailbox)                                 |
| `source_type`         | intake_metadata   | Тип источника (`json_batch`, `mailbox_readonly`)                                    |
| `source_role`         | intake_metadata   | Роль источника в клиентском контексте (technical_aggregator, sales_mailbox и т.д.)  |
| `source_display_name` | intake_metadata   | Человекочитаемое имя источника для UI/оператора                                     |
| `client_id`           | intake_metadata   | Клиент/тенант, к которому привязан источник                                         |
| `sender`              | normalized_events | Email отправителя письма                                                            |
| `subject`             | normalized_events | Тема письма                                                                         |
| `body_short`          | normalized_events | Preview тела письма (≤500 chars, tab/newline-safe)                                  |
| `attachments`         | normalized_events | Метаданные вложений (формат: "file1.pdf (application/pdf, 1024); file2.jpg (...)" ) |
| `bot_case_type`       | classified_events | Решение бота (new_lead, existing_deal, lead_classification, duplicate_resolution)   |
| `bot_reason_code`     | classified_events | Код причины решения бота                                                            |
| `bot_priority`        | classified_events | Приоритет (high, medium, low)                                                       |
| `bot_confidence`      | classified_events | Confidence score (0.0 – 1.0)                                                        |
| `bot_is_fallback`     | classified_events | Fallback решение (true/false)                                                       |
| `bot_reasoning`       | classified_events | Объяснение решения бота (если доступно)                                             |
| `human_case_type`     | rop_review        | Ручное переопределение case_type (пусто по умолчанию)                               |
| `should_rop_see`      | rop_review        | Человек указал, что ROP должен это видеть (yes/no/maybe)                            |
| `bitrix_status`       | rop_review        | Статус интеграции с Bitrix (зарезервировано для будущего)                           |
| `notes`               | rop_review        | Заметки оператора                                                                   |
| `bitrix_lead_id`      | rop_review        | Bitrix lead ID (зарезервировано для будущего)                                       |
| `bitrix_deal_id`      | rop_review        | Bitrix deal ID (зарезервировано для будущего)                                       |
| `bitrix_responsible`  | rop_review        | Ответственный в Bitrix (зарезервировано для будущего)                               |
| `is_duplicate`        | rop_review        | Это дубликат (true/false)                                                           |
| `duplicate_of`        | rop_review        | ID оригинального события (если дубликат)                                            |
| `correct_action`      | rop_review        | Правильное действие (для корректировки обучения)                                    |

Пустые опциональные поля экспортируются как пустые ячейки (не null). TSV остаётся pasteable в Google Sheets без дополнительной обработки.

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
- `docs/WEB_UI.md` — implemented Web Console contract
- `docs/product/ui_roadmap.md` — UI roadmap / Web Console direction

## Важно про безопасность

- секреты хранятся в env, а не в репозитории;
- новые обязательные ключи должны валидироваться fail-fast;
- transport / module / capability boundaries нельзя размывать ad hoc;
- file parsing, external connectors и execution paths требуют более внимательной проверки;
- логи и artifacts не должны утекать в sensitive data;
- v0 должен оставаться read-only;
- default bind host — `127.0.0.1`;
- external exposure требует отдельной deployment/auth hardening итерации;
- artifact routes должны оставаться whitelist-based;
- path traversal должен блокироваться;
- raw `.eml`, attachment content и secret-like payload не должны рендериться в HTML или JSON artifact output.

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
- **ROP CLI and review export** — DONE;
- **Enriched ROP review TSV** — DONE;
- **ROP multi-source ingestion artifacts** — DONE;
- **Operator Web Console v0 with ROP dashboard** — DONE;
- **BeeUI-backed Web Console foundation** — DONE.

Первый реальный модуль:

- `beeagent-rop`

Текущий практический результат:

- `beeagent-rop` загружается через registry;
- BeeAgent может вызвать `beeagent-rop` через `execute_module_case(...)`;
- Telegram command `/run_rop` запускает первый ROP operator flow;
- `run_rop_batch_case(...)` запускает ROP source flow через configurable `rop.sources`;
- `run_rop_batch_case(...)` поддерживает explicit single-source и all enabled sources mode;
- `./start.sh rop run --all-sources` запускает multi-source ingestion;
- `mailbox_readonly` получает последние N писем из configured mailbox source в read-only режиме;
- BeeAgent пишет `source_diagnostics.json`, `intake_metadata.json`, `normalized_events.json`, `classified_events.json`, `operator_summary.json` и `rop_review_table.tsv` при CLI run/export;
- multi-source runs сохраняют aggregate/per-source diagnostics и source traceability;
- partial degraded source виден в artifacts и не скрывается aggregate метриками;
- linkage `run → intake/normalized artifacts → operator_summary → module outputs` виден в artifacts;
- production Bitrix/email/attachment connectors пока не входят в scope;
- live mailbox ingestion не делает destructive mailbox actions и не сохраняет raw `.eml`;
- CRM write-back пока не входит в scope;
- `./start.sh web` запускает BeeUI-backed read-only Operator Web Console;
- web console показывает runs, run overview, module diagnostics и ROP dashboard;
- ROP dashboard показывает latest/selected run summary, classification counts, priority/case type distributions and source status summary where artifacts are available;
- web console отдаёт read-only `/api/*` поверх existing artifacts;
- web console использует BeeUI поверх FastAPI/Jinja2/локальных Tabler assets;
- web console читает existing artifacts и не запускает mailbox/CRM/module/capability actions.
