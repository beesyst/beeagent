# UI ROADMAP — beeagent (BeeUI operator console track)

## Purpose

Этот документ фиксирует отдельный пошаговый план развития UI / Operator Web / Control Panel внутри `beeagent`.

UI roadmap нужен как lightweight planning-артефакт для operator/product layer:

- не размывает `docs/ROADMAP.md` деталями web/frontend задач;
- фиксирует порядок перехода BeeAgent Web Console на BeeUI;
- помогает связывать UI iteration → Issue → Code → Tests → Artifacts → PR → Merge;
- отделяет dashboard, metrics, auth, API, customer-safe access и bounded controls от core runtime roadmap;
- фиксирует, что BeeAgent core остаётся source of truth, а UI остаётся interface/operator layer;
- фиксирует, что BeeUI является canonical web framework layer для новых web работ.

Этот документ не заменяет:

- `docs/ROADMAP.md` — главный roadmap по core/runtime/module/capability;
- `docs/SDLC.md` — process / checks / DoD;
- `docs/SECURITY.md` — secure development rules;
- `docs/WEB_UI.md` — фактический implemented web/API contract;
- Issue и PR — конкретная задача и verification evidence.

Правило:

- `docs/ROADMAP.md` фиксирует core-level развитие BeeAgent;
- `docs/product/ui_roadmap.md` фиксирует UI/operator-web track;
- `docs/WEB_UI.md` фиксирует актуальный реализованный route/API/UI contract;
- одна UI-итерация = один coherent product increment;
- один implementation repository = один Issue = один target worktree/branch = один PR;
- если одна UI-итерация требует изменений в нескольких репозиториях, для каждого repository создаётся отдельный Issue и PR с явными dependency и merge order;
- одна UI-итерация не должна смешивать независимые product increments.

## Why UI track is separate

UI в BeeAgent является отдельным product/operator layer:

- BeeAgent core отвечает за runtime, orchestration, modules, artifacts, config, capability boundary;
- `beeagent-rop` отвечает за ROP domain logic: classification, duplicate/summary/recommendation;
- UI отвечает за operator-visible read-model, dashboards, artifacts, source links и bounded controls later;
- web UI должен быть пригоден не только для `beeagent-rop`, но и для будущих `beescan`, `merch`, MCP/API/operator surfaces;
- UI-задачи важны, но не должны засорять core `docs/ROADMAP.md`.

UI track развивается отдельно, но строго по тому же SDLC-light процессу:

- KISS;
- small scoped iterations;
- config as source of truth;
- fail-fast validation;
- reproducible artifacts;
- explainable logs;
- read-only by default;
- bounded controls only after explicit backend contract;
- no hidden runtime/module/capability execution from UI;
- no secrets in HTML/API/logs/artifacts.

## UI ownership decision

Web UI нужно делать в `beeagent`, не в `beeagent-rop`.

`beeagent-rop` — доменный модуль. Его задача:

```text
inbound event
→ classification
→ duplicate/summary/recommendation
```

`beeagent` — runtime/orchestration/operator shell. Его задача:

```text
sources
→ artifacts
→ module dispatch
→ operator-visible UI/API
```

Поэтому BeeUI интегрируется в `beeagent`.

`beeagent-rop` не должен содержать:

- FastAPI routes;
- Jinja templates;
- BeeUI adapter;
- web static assets;
- artifact browser;
- operator dashboard;
- UI actions.

## BeeUI migration decision

Canonical UI direction:

```text
BeeAgent
  → interfaces/ui adapter/read-model/artifacts
  → BeeUI
  → FastAPI + Jinja2 + Tabler-compatible rendering
```

Старый пакет:

```text
src/beeagent_module/web
```

считается legacy/frozen surface после BeeUI cutover.

Правило:

- новые web features не добавлять в `src/beeagent_module/web`;
- BeeUI integration делать через `src/beeagent_module/interfaces/ui`;
- legacy web удалить после подтверждения BeeUI MVP parity;
- `./start.sh web` должен оставаться canonical entrypoint.

## Vision

| Block                   | Statement                                                                                                                                              |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Track identity**      | UI track развивается как operator-facing interface layer поверх BeeAgent core, artifacts и module outputs, а не как второй runtime или второй backend. |
| **Primary objective**   | Цель UI — дать оператору и заказчику понятную консоль: что пришло, что важно, что degraded, какие actions возможны later и где evidence.               |
| **BeeUI rule**          | BeeUI является canonical web framework layer для BeeAgent. BeeAgent отдаёт adapter/read-model/artifacts, BeeUI рендерит.                               |
| **Backend rule**        | Backend UI layer остаётся FastAPI-based через BeeUI embedded app. BeeAgent не дублирует BeeUI templates/static/common UI.                              |
| **Frontend rule**       | Frontend v1 — BeeUI server-rendered UI. Separate React/Tabler допускается позже только поверх stable BeeUI/BeeAgent API.                               |
| **Source of truth**     | UI читает `config/settings.yml` и existing artifacts из `storage/`. UI не становится source of truth для runtime/business state.                       |
| **Safety rule**         | UI read-only по умолчанию. Любые write/control actions проходят через explicit product-owned backend action API, validation, confirmation и audit.     |
| **Artifact rule**       | Все значения в UI должны быть traceable к source artifacts. Missing/partial/corrupted data отображается явно.                                          |
| **Module rule**         | UI не содержит ROP business rules. Domain logic остаётся в `beeagent-rop`; UI показывает outputs/artifacts.                                            |
| **Customer rule**       | Customer-facing link возможен только через существующую auth/session boundary и после deployment/security hardening, соответствующего окружению.       |
| **Future console rule** | Future standalone BeeUI или separate frontend может подключаться к stable BeeAgent/BeeUI API, но не должен создавать второй backend truth.             |

## Architecture direction

Целевая архитектура UI:

```text
Browser
  ↓
BeeUI FastAPI app
  ├─ HTML pages: Jinja2 + Tabler-compatible blocks
  ├─ JSON API
  ├─ Artifact browser
  ├─ Auth/session layer
  ├─ Bounded action shell later
  └─ Product adapter boundary
        ↓
BeeAgent interfaces/ui
  ├─ BeeAgentUiAdapter
  ├─ read_model.py
  ├─ artifacts.py
  ├─ bounded_read.py
  └─ config/action/admin later
        ↓
BeeAgent core/services/cases
        ↓
storage/runs/*
storage/interfaces/*
config/settings.yml
modules.registry
beeagent-rop outputs
```

Target source layout:

```text
src/beeagent_module/
  cli/
    web.py

  core/
    app.py
    settings.py
    paths.py
    module_registry.py
    artifact_api.py
    capability.py
    ...

  interfaces/
    ui/
      __init__.py
      app.py
      adapter.py
      read_model.py
      artifacts.py
      bounded_read.py
      config.py      # later
      admin.py       # later
      actions.py     # later

    mcp/
      __init__.py
      server.py      # later

    telegram/
      ...            # later, if transport is extracted

  cases/
    ...
```

Do not use as target:

```text
src/beeagent_module/ui
src/beeagent_module/web as canonical future UI
src/beeagent_module/ui/mcp_server.py
beeagent-rop web routes/templates
```

## Responsibility split

| Layer                           | Responsibility                                                                                   |
| ------------------------------- | ------------------------------------------------------------------------------------------------ |
| `beeagent_module.core`          | runtime, config validation, module registry, artifact API, capability boundary, authority policy |
| `beeagent_module.cases`         | BeeAgent-owned application flows, including ROP orchestration wrappers                           |
| `beeagent_module.interfaces.ui` | BeeAgent product adapter/read-model/artifact allowlist for BeeUI                                 |
| `beeui`                         | rendering, navigation, layout blocks, artifact browser, HTML/API shell, generic auth/session     |
| `beeagent-rop`                  | domain classification/duplicate/summary/recommendation logic                                     |

Canonical rule:

```text
BeeUI renders.
BeeAgent decides/orchestrates.
beeagent-rop classifies.
```

## Source of truth

Runtime/config source of truth:

```text
config/settings.yml
```

BeeUI UI schema source of truth:

```text
config/beeui.yml
```

Artifact source of truth:

```text
storage/runs/<run_id>/*
storage/interfaces/*
```

ROP source configuration source of truth:

```text
config/settings.yml
→ rop.sources[]
```

UI must expose ROP source parameters read-only where useful, but must not create a second source of truth.

Safe ROP source fields that UI may show:

```text
source_id
source_type
source_role
client_id
display_name
enabled
authority
items_max
mailbox.host
mailbox.port
mailbox.use_ssl
mailbox.folder
mailbox.username_env
```

UI must not show:

```text
mailbox.password
mailbox password env value
raw .env values
raw message content
raw .eml
raw attachments
secret values
```

## Development principles

Каждая UI-итерация должна:

- оставаться внутри одного coherent product scope;
- работать через canonical BeeAgent web entrypoint;
- использовать BeeUI для rendering/common UI;
- использовать BeeAgent `interfaces/ui` adapter/read-model as product boundary;
- использовать existing artifacts/read-models как source of truth;
- не вызывать mailbox/CRM/module/capability execution из GET routes;
- не мутировать `storage/`, config или runtime state без явно заявленного bounded action flow;
- сохранять read-only behavior для dashboard/run/detail/artifact GET routes;
- использовать `config/settings.yml` как source of truth для runtime config;
- использовать `config/beeui.yml` как source of truth для UI schema/layout;
- валидировать новые mandatory config keys fail-fast;
- создавать audit artifacts для bounded write/control actions later;
- не раскрывать secrets в HTML/API/logs/artifacts;
- graceful-handle missing/empty/partial/corrupted artifacts;
- закрываться через Issue / PR / tests / artifacts;
- создавать отдельный Issue и PR для каждого implementation repository.

Для текущего BeeAgent UI track это означает:

- BeeUI migration, auth boundary, final-decision UX, canonical Queue baseline и embedded Bitrix ROP console выполнены в UI-4–UI-8.5;
- следующий product increment — UI-9 legacy web removal после подтверждения parity;
- затем завершить event-level attachment и Bitrix reconciliation UX;
- затем стабилизировать API contract;
- затем добавлять bounded operator controls поверх существующей auth boundary;
- затем добавлять support/admin surfaces;
- standalone/separate frontend остаётся deferred;
- не делать control panel до explicit action/audit contract.

## Status values

Допустимые статусы UI-итераций:

- **PLANNED** — запланировано
- **IN PROGRESS** — в работе
- **DONE** — завершено
- **DONE (partial)** — завершено частично, есть ограничения
- **DEFERRED** — отложено до появления evidence/стабилизации контрактов
- **RETIRED** — будущий item снят как устаревший или уже покрытый выполненной итерацией; ID не переиспользуется

## Roadmap item format

Исторические итерации со статусом `DONE` сохраняют существующую структуру и не переписываются задним числом только ради форматирования.

Новые итерации и materially refined незавершённые итерации используют компактную структуру:

- `Goal`
- `Depends on`, если есть реальные prerequisites
- `Change level`
- `Scope`
- `Excluded`
- `Deliverable`
- `Acceptance criteria`
- `Checks`
- `DoD`

ROADMAP фиксирует iteration-level product contract.

Конкретные файлы, полные payload examples, подробные implementation requirements, расширенные test matrices и verification evidence принадлежат Issue, implementation handoff и PR.

Целевой размер новой итерации — 40–60 строк, максимум 80 строк без обоснованной необходимости.

## Global Definition of Done

UI-итерация считается завершённой, если:

- поведение реализовано в рамках заявленного scope;
- route/API contract покрыт тестами;
- HTML/API output не раскрывает secrets;
- GET/read-only routes не мутируют artifacts/config/runtime state;
- bounded write/control paths создают audit artifacts, если они есть в scope;
- новые mandatory config keys читаются из `config/settings.yml` или `config/beeui.yml`;
- новые mandatory config keys валидируются fail-fast;
- missing/partial/corrupted artifacts handled gracefully;
- source artifacts явно отражены в payload/view;
- tests и smoke checks выполнены;
- required quality/security checks выполнены по change level;
- `docs/WEB_UI.md` обновлён, если изменился implemented route/API contract;
- `README.ru.md` / `docs/DEV_GUIDE.md` обновлены, если изменился способ запуска/usage;
- `pyproject.toml.version` не меняется в обычных UI feature PR;
- если increment cross-repository, каждый implementation repository закрыт отдельным Issue и PR в правильном merge order.

## Change levels for UI track

UI track использует те же change levels:

- **low-risk** — docs, harmless copy/style cleanup, tests without route/API/config/runtime change;
- **runtime-risk** — dashboard/read-model/API changes, artifact parsing, route behavior, template rendering, BeeUI adapter payloads;
- **security-sensitive** — auth, config mutation, operator controls, action API, runtime control artifacts, file/path handling, new dependencies, external exposure.

Правило:

- read-only dashboards обычно `runtime-risk`;
- BeeUI dependency/migration с file/path/artifact browser обычно `security-sensitive`;
- auth/control/action/config apply/file/path-sensitive changes — `security-sensitive`;
- docs-only and copy/style-only changes — `low-risk`.

## Baseline already achieved

К началу BeeUI migration baseline считался таким:

- BeeAgent имел legacy read-only Web Console after previous UI work;
- route `/runs` показывал runs;
- route `/runs/<run_id>` показывал run overview;
- route `/runs/<run_id>/rop` показывал ROP dashboard;
- route `/modules` показывал module diagnostics, если artifact доступен;
- web routes читали existing artifacts;
- web routes не запускали ROP run;
- web routes не делали CRM/mailbox actions;
- raw `.eml` и attachment content не должны были рендериться;
- path traversal должен был блокироваться;
- `beeagent-rop` не менялся из UI-задач;
- It24 multi-source artifacts уже отображались в legacy ROP dashboard;
- BeeAgent It25 attachment extraction artifacts существовали;
- `beeagent-rop It15` consuming attachment metadata был завершён.

Это исторический baseline. Новый web work теперь идёт через BeeUI-backed `interfaces/ui`, а legacy web подлежит удалению в UI-9.

---

## Этап 0 — Planning and architecture decision

### Итерация UI-0 — UI roadmap and FastAPI/Tabler decision

**Статус:** DONE

#### Goal

Зафиксировать UI direction для BeeAgent: FastAPI backend, Jinja2 + Tabler frontend v1, stable `/api/*` как будущий контракт для отдельного frontend.

#### Scope

**Включено:**

- создать `docs/product/ui_roadmap.md`;

- зафиксировать UI architecture decision:
  - FastAPI web backend;
  - Jinja2 server-side templates;
  - Tabler UI kit;
  - stable JSON API;
  - no Reflex as BeeAgent core;
  - no separate frontend until API stabilizes;
  - SQLAdmin only later for DB-backed admin models;

- обновить `docs/ROADMAP.md` минимальной ссылкой на UI track;

- обновить `docs/WEB_UI.md`, если нужно зафиксировать current baseline;

- определить порядок UI-итераций относительно BeeAgent It24–It27.

**Не включено:**

- кодовые изменения;
- FastAPI migration;
- Tabler integration;
- auth;
- actions;
- separate frontend.

#### Deliverable

Есть отдельный UI roadmap и принятое архитектурное решение по Web Console.

#### Checks

- docs review;
- roadmap consistency review;
- no runtime changes;
- no tests required unless docs tooling exists.

#### DoD

- `docs/product/ui_roadmap.md` создан;
- основной `docs/ROADMAP.md` не дублирует UI-track детали;
- UI direction понятен для следующих issues.

---

## Этап 1 — FastAPI + Tabler web foundation

### Итерация UI-1 — FastAPI + Tabler Web Console foundation v0

**Статус:** DONE

#### Goal

Перевести текущий read-only BeeAgent Web Shell с `http.server` на FastAPI-based Web Console с Jinja2 + vendored Tabler static assets, сохранив текущие read-only route semantics, artifact source-of-truth и security boundary.

#### Почему это нужно

UI-0 зафиксировал архитектурное решение:

- FastAPI backend;
- Jinja2 templates;
- Tabler UI kit;
- stable `/api/*`;
- no Reflex as BeeAgent core;
- no separate frontend until API stabilizes;
- SQLAdmin only later for DB-backed admin.

Теперь нужен не docs-only PR, а runtime foundation, на котором дальше будут строиться:

- multi-source dashboard;
- attachment-aware dashboard;
- Bitrix reconciliation dashboard;
- auth;
- bounded operator controls;
- future BeeConsole.

#### Scope

**Включено:**

- заменить stdlib `http.server` web runtime на FastAPI app inside `src/beeagent_module/web`;
- сохранить `./start.sh web`;
- использовать существующие `web.host`, `web.port`, `web.open_browser`;
- добавить/сохранить Jinja2 templates;
- подключить vendored Tabler assets из `src/beeagent_module/web/static/vendor/tabler/`;
- сохранить HTML routes:
  - `/`;
  - `/runs`;
  - `/runs/{run_id}`;
  - `/runs/{run_id}/rop`;
  - `/modules`;

- добавить read-only API routes:
  - `/api/runs`;
  - `/api/runs/{run_id}`;
  - `/api/rop/runs/{run_id}/dashboard`;
  - `/api/modules`;

- сохранить artifact-only read behavior;
- сохранить path traversal protection;
- сохранить no raw `.eml` / no attachment content behavior;
- обеспечить no GET mutation;
- добавить FastAPI TestClient tests;
- обновить:
  - `docs/WEB_UI.md`;
  - `README.ru.md`;
  - `docs/DEV_GUIDE.md`;
  - `docs/product/ui_roadmap.md` status notes;
  - `docs/ROADMAP.md` только минимальной ссылкой на UI track, без дублирования.

**Не включено:**

- auth;
- RBAC;
- POST actions;
- web-triggered `rop run`;
- CRM/mailbox actions;
- config editing;
- attachment extraction;
- Bitrix;
- React;
- Reflex;
- SQLAdmin;
- Node/npm pipeline in `./start.sh`;
- changes to `beeagent-rop`;
- ROP business rules in BeeAgent core.

#### Deliverable

`./start.sh web` запускает FastAPI + Jinja2 + Tabler read-only Web Console поверх existing artifacts.

#### Change level

`runtime-risk`.

Escalate to `security-sensitive` only if implementation changes file/path semantics, dependency surface beyond FastAPI/Uvicorn/TestClient, auth, secrets, POST actions or external exposure.

#### DoD

- UI-0 architecture decision reflected in docs;
- UI-1 runtime foundation implemented;
- `./start.sh web` works;
- existing CLI/Telegram/ROP entrypoints not broken;
- HTML routes work;
- API routes work;
- no raw `.eml`, attachment content, secrets in HTML/API;
- GET routes do not mutate state;
- tests and docs updated;
- `pyproject.toml.version` not changed.

#### Status notes

- canonical FastAPI app implemented in `src/beeagent_module/web`;
- Jinja2 + vendored Tabler static assets wired into packaged web UI;
- HTML routes preserved for `/`, `/runs`, `/runs/{run_id}`, `/runs/{run_id}/rop`, `/modules`;
- read-only JSON API added for `/api/runs`, `/api/runs/{run_id}`, `/api/rop/runs/{run_id}/dashboard`, `/api/modules`;
- `docs/WEB_UI.md` now fixes the implemented contract.

---

## Этап 2 — BeeUI operator console and ROP surfaces

### Итерация UI-2 — ROP multi-source dashboard v1

**Статус:** DONE

#### Goal

Расширить BeeAgent Web Console ROP dashboard под multi-source ROP run после BeeAgent It24: оператор должен видеть aggregate и per-source картину по всем источникам текущего run, включая source status, degraded reasons, loaded/classified counts и source-aware event table.

#### Почему это нужно

После `BeeAgent It24 — ROP multi-source ingestion artifacts v0` BeeAgent умеет запускать один ROP run по нескольким configured `rop.sources[]` и пишет source-aware artifacts:

- `source_diagnostics.json`;
- `intake_metadata.json`;
- `normalized_events.json`;
- `classified_events.json`;
- `operator_summary.json`;
- `rop_review_table.tsv`.

Но текущий Web Console/ROP dashboard ещё недостаточно показывает multi-source картину:

- degraded source может потеряться за aggregate count;
- оператор не видит, какой source дал какие события;
- фильтры не позволяют быстро сузить review по `source_id` / `source_role`;
- API payload недостаточно удобен для будущего stable `/api/*`;
- single-source и multi-source runs должны отображаться одинаково предсказуемо.

#### Depends on

- `BeeAgent It24 — ROP multi-source ingestion artifacts v0`

#### Scope

**Включено:**

- расширить ROP dashboard read-model под It24 artifact contract;

- показать aggregate source KPIs:
  - total source count;
  - loaded source count;
  - degraded source count;
  - total fetched;
  - total loaded;
  - total malformed;
  - total normalized;
  - total classified;
  - classification failed count;
  - fallback count;

- добавить per-source summary table:
  - `source_id`;
  - `source_type`;
  - `source_role`;
  - `source_display_name`;
  - `client_id`;
  - `authority`;
  - `mailbox_folder`, если есть;
  - `status`;
  - `reason`;
  - `items_max`;
  - `fetched_count`;
  - `loaded_count`;
  - `malformed_count`;
  - `classified_count`, если можно вывести из classified events;
  - `fallback_count`, если можно вывести из classified events;

- расширить ROP event table source-aware колонками:
  - `source_id`;
  - `source_type`;
  - `source_role`;
  - `source_display_name`;
  - `client_id`;

- добавить/расширить filters:
  - `source_id`;
  - `source_role`;
  - `source_status`;
  - `case_type`;
  - `priority`;
  - `fallback`;
  - `reason_code`;

- обновить `/api/rop/runs/{run_id}/dashboard` payload:
  - сохранить backward-compatible поля, где это разумно;
  - добавить `source_aggregate`;
  - добавить `sources`;
  - добавить source-aware filter options;
  - добавить source fields в `rows`;

- graceful handling:
  - old single-source runs;
  - new multi-source runs;
  - missing `aggregate`;
  - missing `sources[]`;
  - one degraded source;
  - malformed source diagnostics;
  - empty source;
  - non-ROP run;

- сохранить read-only behavior:
  - no GET mutation;
  - no mailbox/CRM/module/capability calls;
  - no web-triggered `rop run`;

- сохранить sanitization:
  - no raw `.eml`;
  - no `message/rfc822`;
  - no attachment content;
  - no secrets in HTML/API;

- добавить/обновить tests:
  - single-source compatibility;
  - multi-source dashboard rendering;
  - source filters;
  - degraded source visibility;
  - API payload shape;
  - no mutation;
  - sanitization;

- обновить docs:
  - `docs/WEB_UI.md`;
  - `docs/product/ui_roadmap.md`;
  - `README.ru.md` / `docs/DEV_GUIDE.md`, если меняется usage/contract.

**Не включено:**

- web-triggered `rop run`;
- source-aware dedup editing;
- human review editing;
- CRM write-back;
- Bitrix reconciliation UI;
- attachment extraction UI;
- auth;
- RBAC;
- POST actions;
- operator control panel;
- mailbox listener/polling;
- changes to `beeagent-rop`;
- ROP business rules in BeeAgent core.

#### Deliverable

`/runs/{run_id}/rop` и `/api/rop/runs/{run_id}/dashboard` показывают source-aware ROP dashboard для old single-source и new multi-source runs.

Оператор видит:

- aggregate multi-source health;
- per-source status/degraded reasons;
- source-aware event table;
- source filters;
- classification/fallback metrics без скрытия failed/degraded sources.

#### Expected artifacts read

```text
storage/runs/<run_id>/source_diagnostics.json
storage/runs/<run_id>/intake_metadata.json
storage/runs/<run_id>/normalized_events.json
storage/runs/<run_id>/classified_events.json
storage/runs/<run_id>/operator_summary.json
storage/runs/<run_id>/rop_review_table.tsv
storage/runs/<run_id>/module-beeagent-rop/module_result.json
storage/runs/<run_id>/module-beeagent-rop/rop_summary_result.json
```

#### Change level

```text
runtime-risk
```

Escalate to `security-sensitive` only if implementation changes file/path handling, auth, secrets, POST/actions, external exposure, dependencies, or mailbox/CRM/capability execution.

#### Checks

- `uv run pytest -q`;
- targeted Web Console tests;
- single-source compatibility scenario;
- multi-source run scenario;
- one source degraded scenario;
- source filter checks;
- aggregate metrics checks;
- API payload shape checks;
- no GET mutation;
- no mailbox/CRM/module/capability calls from web routes;
- no raw `.eml` / attachment content / secrets in HTML/API;
- path traversal still blocked;
- smoke:
  - create/reuse multi-source run;
  - `./start.sh web`;
  - open `/runs/{run_id}/rop`;
  - open `/api/rop/runs/{run_id}/dashboard`.

#### DoD

- source-aware ROP dashboard works for old and new runs;
- source status and degraded reasons are explicit;
- aggregate metrics do not hide degraded sources;
- `source_id` / `source_role` filters work;
- event table preserves source traceability;
- JSON API exposes source-aware read-model;
- dashboard remains read-only;
- no mailbox/CRM/module/capability execution from GET routes;
- no secrets/raw `.eml`/attachment content in HTML/API;
- tests and docs updated;
- `pyproject.toml.version` not changed.

#### Status notes

- `/runs/{run_id}/rop` расширен под source-aware read-model:
  - aggregate source KPI card;
  - per-source summary table;
  - source-aware event columns;
  - source filters (`source_id`, `source_role`, `source_status`).

- `/api/rop/runs/{run_id}/dashboard` расширен полями:
  - `source_aggregate`;
  - `sources`;
  - source-aware `filter_options`;
  - source-aware `rows` fields.

- backward compatibility сохранена для old single-source runs.
- read-only/security boundary сохранены: no GET mutation, no mailbox/CRM/module/capability execution from GET routes, sanitization сохранена.

### Итерация UI-3 — UI roadmap and BeeUI migration decision

**Статус:** DONE

#### Goal

Зафиксировать отдельный UI/operator-web track для BeeAgent и принять архитектурное решение: BeeUI становится canonical web framework layer, legacy `src/beeagent_module/web` подлежит удалению после BeeUI MVP parity.

#### Scope

**Включено:**

- актуализировать `docs/product/ui_roadmap.md`;
- зафиксировать BeeUI migration direction;
- зафиксировать target structure:

```text
src/beeagent_module/interfaces/ui
```

- зафиксировать, что web UI принадлежит `beeagent`, не `beeagent-rop`;
- зафиксировать, что `beeagent-rop` не содержит web routes/templates;
- зафиксировать BeeUI-only direction for new web work;
- legacy `src/beeagent_module/web` пометить как deprecated/frozen;
- описать UI-1/UI-2 BeeUI migration path;
- зафиксировать Python 3.14 / dependency hygiene prerequisite.

**Не включено:**

- кодовые изменения;
- dependency `beeui`;
- route switch;
- удаление legacy web;
- config/actions/auth;
- changes to `beeagent-rop`.

#### Deliverable

Есть обновлённый UI roadmap и принятое архитектурное решение по BeeUI migration.

#### Checks

- docs review;
- roadmap consistency review;
- no runtime changes;
- no tests required unless docs tooling exists.

#### DoD

- `docs/product/ui_roadmap.md` обновлён;
- основной `docs/ROADMAP.md` не дублирует UI-track детали;
- команда понимает, что новый web work идёт только через BeeUI adapter;
- legacy web больше не развивается feature-wise.

### Итерация UI-4 — BeeUI canonical ROP operator console MVP

**Статус:** DONE

#### Goal

Подключить `beeui` как canonical BeeAgent web surface и дать минимальный read-only ROP operator console поверх существующих BeeAgent ROP artifacts.

#### Почему это нужно

После BeeAgent It24/It25 и `beeagent-rop It15` backend/artifact/domain path уже создаёт достаточно evidence для MVP:

```text
multi-source mailbox/json_batch
→ attachment extraction artifacts
→ normalized events
→ beeagent-rop classification
→ classified events
→ ROP summary
→ operator-visible artifacts
```

Но legacy web не должен дальше развиваться. BeeAgent должен перейти на reusable BeeUI layer, чтобы не копировать Tabler/Jinja/static/dashboard/artifact browser logic по продуктам.

UI-4 является первым runtime/code increment после BeeUI migration decision: `./start.sh web` должен запускать BeeUI-backed BeeAgent console, а не legacy `src/beeagent_module/web`.

#### Depends on

- BeeUI product adapter / embedded mount capabilities;
- `beeui>=0.13,<0.30`;
- BeeAgent It24 multi-source artifacts;
- BeeAgent It25 attachment extraction artifacts;
- `beeagent-rop It15` consuming attachment metadata;
- Technical prerequisite before UI-4 — Python 3.14 and dependency hygiene.

#### Change level

```text
security-sensitive
```

Причина:

- new dependency surface;
- embedded web app integration;
- artifact browser / file/path boundary;
- route behavior change;
- package/static/templates boundary;
- user-controlled route params;
- HTML/API exposure.

#### Scope

**Включено:**

- добавить dependency:

```toml
beeui>=0.13,<0.30
```

- добавить local editable `beeui` source for dev, если BeeUI используется как соседний local repo:

```toml
[tool.uv.sources]
beeui = { path = "../beeui", editable = true }
```

- создать BeeAgent-side UI package:

```text
src/beeagent_module/interfaces/ui/
  __init__.py
  app.py
  adapter.py
  read_model.py
  artifacts.py
  bounded_read.py
```

- добавить thin CLI entrypoint:

```text
src/beeagent_module/cli/web.py
```

- переключить `config/start.py web` на `src/beeagent_module/cli/web.py`;
- сохранить canonical запуск:

```bash
./start.sh web
```

- добавить support for web CLI overrides:

```bash
./start.sh web --host 127.0.0.1 --port 8780 --no-open
```

- добавить route listing diagnostic, если это не раздувает scope:

```bash
./start.sh routes
```

- добавить `config/beeui.yml` как source of truth для BeeUI navigation/pages/blocks;
- реализовать BeeAgent app composition через BeeUI embedded API;
- реализовать `BeeAgentUiAdapter`;
- использовать BeeUI adapter / page / block registry style, а не hardcoded product UI внутри core;
- legacy `src/beeagent_module/web` оставить как code fallback only до UI-9, но не развивать;
- реализовать read-only dashboard;
- реализовать runs list;
- реализовать run detail;
- реализовать ROP dashboard read-model;
- реализовать modules/registry diagnostics read-model;
- реализовать allowlisted artifact browser;
- протянуть safe ROP source parameters в config read-model;
- запретить arbitrary storage browsing;
- bounded JSON/JSONL/text/TSV preview;
- path traversal protection;
- no raw `.eml`;
- no raw attachment content;
- no secrets in HTML/API/logs;
- attachment aggregate counts можно показать только если они уже доступны в existing artifacts;
- detailed attachment-aware dashboard оставить для отдельной UI-итерации;
- docs update:
  - `docs/WEB_UI.md`;
  - `docs/product/ui_roadmap.md`;
  - `README.ru.md`;
  - `docs/DEV_GUIDE.md`;
  - `docs/SECURITY.md` only if security rules materially change.

**Не включено:**

- удаление legacy `src/beeagent_module/web`;
- config apply;
- admin/actions;
- auth/RBAC;
- POST routes;
- web-triggered ROP run;
- CRM write-back;
- Bitrix actions;
- mailbox actions;
- attachment parsing/OCR;
- full attachment-aware dashboard;
- changing `beeagent-rop`;
- changing ROP business rules;
- stable API v1 freeze;
- standalone BeeUI service.

#### Required adapter methods

Minimum BeeAgent-side adapter methods:

```python
class BeeAgentUiAdapter:
    def get_dashboard(self): ...
    def list_runs(self): ...
    def get_run(self, run_id: str): ...
    def list_artifacts(self, run_id: str): ...
    def read_artifact(self, run_id: str, artifact_id: str): ...
    def get_config_read_model(self): ...
```

If BeeUI supports product-specific dashboard methods, BeeAgent may additionally implement:

```python
def get_module_dashboard(self, module_id: str): ...
def get_rop_dashboard(self, run_id: str | None = None): ...
```

If BeeUI does not expose `get_rop_dashboard`, ROP page can be implemented in BeeAgent `interfaces/ui/app.py` as a thin product-specific route using BeeUI primitives and BeeAgent adapter/read-model.

#### Config source of truth

Runtime web bind settings remain:

```text
config/settings.yml
→ web.host
→ web.port
→ web.open_browser
```

BeeUI layout/navigation/pages source of truth:

```text
config/beeui.yml
```

ROP source configuration source of truth remains:

```text
config/settings.yml
→ rop.sources[]
```

UI must not create a second source of truth for ROP sources.

#### Minimal `config/beeui.yml`

```yaml
app:
  title: BeeAgent
  product: beeagent
  logo_text: BeeAgent
  theme:
    mode: dark
    primary: yellow
    base: gray
    font: sans-serif
    radius: 1
    density: default
  layout:
    type: vertical
    container: xl
    sidebar:
      variant: dark
      collapsed: false
    navbar:
      enabled: false
      variant: default
      sticky: false

navigation:
  - title: BeeAgent
    children:
      - title: Dashboard
        path: /
        icon: dashboard
      - title: Runs
        path: /runs
        icon: list
      - title: ROP
        path: /rop
        icon: list-details
      - title: Modules
        path: /modules
        icon: puzzle

data_sources: {}

blocks: {}

pages:
  - id: dashboard
    path: /
    title: Dashboard
    subtitle: BeeAgent operator dashboard
    blocks:
      - id: beeagent_kpi
        enabled: true
      - id: latest_run
        enabled: true
      - id: attention
        enabled: true

  - id: runs
    path: /runs
    title: Runs
    subtitle: Run history
    blocks:
      - id: runs_table
        enabled: true

  - id: rop
    path: /rop
    title: ROP
    subtitle: Read-only ROP operator dashboard
    blocks:
      - id: rop_kpi
        enabled: true
      - id: rop_sources
        enabled: true
      - id: rop_events
        enabled: true
      - id: artifact_links
        enabled: true

  - id: modules
    path: /modules
    title: Modules
    subtitle: Module registry diagnostics
    blocks:
      - id: modules_table
        enabled: true
```

#### ROP artifacts allowlist

For BeeAgent ROP MVP, UI artifact allowlist should include only known safe artifacts:

```text
run_json                         -> run.json
operator_summary_json            -> operator_summary.json
source_diagnostics_json          -> source_diagnostics.json
intake_metadata_json             -> intake_metadata.json
normalized_events_json           -> normalized_events.json
classified_events_json           -> classified_events.json
attachment_extraction_json       -> attachment_extraction.json
rop_review_table_tsv             -> rop_review_table.tsv
module_result_json               -> module-beeagent-rop/module_result.json
rop_summary_result_json          -> module-beeagent-rop/rop_summary_result.json
lead_classification_result_json  -> module-beeagent-rop/lead_classification_result.json
steps_json                       -> steps.json
```

Do not allow UI to read:

```text
raw .eml
raw attachments
arbitrary files
logs with secrets
env/config secrets
mailbox password values
provider tokens
mailbox source content beyond normalized/sanitized artifacts
```

#### ROP dashboard should show

```text
- latest ROP run;
- run_id;
- source count;
- loaded/classified/failed count;
- counts by source_id;
- counts by source_role;
- counts by source_status;
- counts by case_type;
- counts by priority;
- fallback/manual-review count;
- attachment aggregate counts only if already available in existing artifacts;
- top attention items;
- table of classified events:
  - event_id;
  - source_id;
  - source_role;
  - sender;
  - subject;
  - body_short;
  - attachments;
  - case_type;
  - priority;
  - confidence;
  - reason_code;
  - reasoning;
  - is_fallback;
- source artifact links.
```

#### ROP source parameters to surface read-only

UI should show or expose through config read-model:

```text
rop.sources[].source_id
rop.sources[].source_type
rop.sources[].source_role
rop.sources[].client_id
rop.sources[].display_name
rop.sources[].enabled
rop.sources[].authority
rop.sources[].items_max
rop.sources[].mailbox.host
rop.sources[].mailbox.port
rop.sources[].mailbox.use_ssl
rop.sources[].mailbox.folder
rop.sources[].mailbox.username_env
```

Do not show env values:

```text
ROP_MAILBOX_USERNAME actual value
ROP_MAILBOX_PASSWORD actual value
```

#### Expected routes

Canonical BeeUI-backed route surface:

```text
/
/health
/runs
/runs/{run_id}
/runs/{run_id}/artifacts
/runs/{run_id}/artifacts/{artifact_id}
/rop
/modules

/api/dashboard
/api/runs
/api/runs/{run_id}
/api/runs/{run_id}/artifacts
/api/runs/{run_id}/artifacts/{artifact_id}
/api/modules
/api/rop/dashboard
```

Optional compatibility routes can exist only for transition and must not receive new feature work.

#### Checks

- `uv run pytest -q`;
- `./start.sh web --host 127.0.0.1 --port 8780 --no-open`;
- `./start.sh routes`, if implemented;
- `/` returns 200;
- `/health` returns 200;
- `/runs` returns 200;
- `/runs/{run_id}` returns 200 for fixture/smoke run;
- `/runs/{run_id}/artifacts` returns 200;
- `/runs/{run_id}/artifacts/{artifact_id}` returns 200 for allowlisted artifact;
- `/rop` returns 200;
- `/modules` returns 200;
- `/api/dashboard` returns 200;
- `/api/rop/dashboard` returns 200;
- invalid `run_id` rejected;
- invalid `artifact_id` rejected;
- path traversal rejected;
- raw path artifact id rejected;
- non-allowlisted artifact rejected;
- oversized JSON bounded;
- JSONL/TSV bounded;
- malformed JSON warning, not crash;
- GET routes do not mutate storage/config/runtime;
- no mailbox/CRM/provider calls;
- no module/capability execution from GET routes;
- no secrets in HTML/API/logs;
- no external CDN/scripts/tracking introduced;
- SAST;
- SCA because dependency files change;
- DAST-style route misuse checks where practical.

#### DoD

- `./start.sh web` starts BeeUI-backed BeeAgent console;
- `./start.sh web --host ... --port ... --no-open` works;
- BeeUI is canonical route surface for new web work;
- ROP dashboard is useful for MVP review;
- artifact browser is allowlisted and bounded;
- ROP source parameters are visible as safe read-only config/read-model data;
- legacy web receives no new feature work;
- docs updated;
- `pyproject.toml.version` unchanged;
- `beeagent-rop` unchanged.

### Итерация UI-5 — Rich ROP dashboard parity + operator intelligence v1

**Статус:** DONE

#### Goal

Довести BeeUI-backed ROP dashboard до уровня полноценной операторской панели: вернуть parity с legacy Web Console и добавить operator intelligence поверх существующих ROP artifacts — KPI, source health, processing funnel, attention items, deterministic recommendations, review events table и evidence links.

#### Почему это нужно

UI-4 выполнил важную инфраструктурную задачу: `./start.sh web` теперь запускает BeeUI-backed console, а новый web work должен идти через `src/beeagent_module/interfaces/ui`.

Но UI-4 был foundation/cutover, а не полноценный продуктовый dashboard. Текущий BeeUI ROP экран слишком бедный:

- мало KPI;
- нет полноценной processing funnel;
- source health виден ограниченно;
- нет операторских рекомендаций;
- нет удобной таблицы событий для review;
- attachment status виден недостаточно;
- artifact evidence не собран в понятный блок;
- главный dashboard и ROP-раздел не дают оператору быстрого ответа: что пришло, что обработано, где проблема и что делать дальше.

Удалять legacy `src/beeagent_module/web` до восстановления dashboard parity преждевременно. Сначала BeeUI ROP dashboard должен стать не хуже legacy и полезнее для MVP review.

#### Product direction

Главный dashboard `/` остаётся общим BeeAgent operator dashboard:

```text
BeeAgent Console
  → global overview
  → runs
  → modules
  → module/operator sections
      → ROP
      → BeeScan later
      → Merch later
```

ROP dashboard `/rop` — module/operator section для `beeagent-rop`, но реализация остаётся в `beeagent`, потому что UI принадлежит BeeAgent operator layer.

Будущие модули должны подключаться и отключаться через module registry / artifacts без превращения UI в ROP-only приложение.

#### Depends on

- UI-4 — BeeUI canonical ROP operator console MVP;
- BeeAgent It24 — ROP multi-source ingestion artifacts;
- BeeAgent It25 — ROP attachment extraction artifacts;
- `beeagent-rop It15` — classification uses BeeAgent attachment extraction contract;
- existing artifacts:
  - `operator_summary.json`;
  - `source_diagnostics.json`;
  - `intake_metadata.json`;
  - `attachment_extraction.json`;
  - `normalized_events.json`;
  - `classified_events.json`;
  - `rop_review_table.tsv`;
  - `module-beeagent-rop/module_result.json`;
  - `module-beeagent-rop/rop_summary_result.json`;
  - `steps.json`.

#### Change level

```text
runtime-risk
```

Причина:

- меняются dashboard/read-model/API payloads;
- меняется HTML rendering для operator dashboard;
- UI читает и агрегирует existing artifacts;
- появляются новые deterministic recommendations;
- route/API behavior меняется, но без новых dependencies, auth, POST/actions, file/path contract changes или external execution.

Escalate to `security-sensitive` only if implementation changes dependency surface, file/path handling, artifact allowlist semantics, auth, POST/actions, external exposure, mailbox/CRM/capability execution, or raw attachment rendering.

#### Scope

**Включено:**

- расширить BeeAgent ROP read-model в:

```text
src/beeagent_module/interfaces/ui/read_model.py
```

- расширить BeeAgent ROP HTML/API rendering в:

```text
src/beeagent_module/interfaces/ui/app.py
```

- сохранить BeeUI-backed route surface from UI-4;
- сделать `/rop` полноценной operator intelligence page;
- поддержать latest run по умолчанию;
- поддержать selected run через:

```text
/rop?run_id=<run_id>
/api/rop/dashboard?run_id=<run_id>
```

- добавить ссылки из `/runs` или run detail на `/rop?run_id=<run_id>`, если это можно сделать без расширения scope;
- добавить ROP KPI cards/read-model:

```text
total_runs
selected_run_id
run_status
source_count
loaded_source_count
degraded_source_count
fetched_count
loaded_count
malformed_count
normalized_count
classified_count
classification_failed_count
fallback_count
high_priority_count
medium_priority_count
low_priority_count
attachment_count
attachment_preview_count
attachment_refused_count
attachment_blocked_count
review_tsv_available
```

- добавить processing funnel:

```text
configured_sources
→ enabled_sources
→ fetched_items
→ loaded_items
→ normalized_events
→ classified_events
→ review_candidates
```

- добавить source health table:

```text
source_id
display_name
source_type
source_role
client_id
authority
status
reason
items_max
fetched_count
loaded_count
malformed_count
classified_count
fallback_count
```

- добавить classification distribution:

```text
case_type_counts
priority_counts
reason_code_counts
fallback_count
```

- добавить deterministic recommendations / operator attention block.

Recommendations строятся без LLM, только из artifacts:

```text
if high_priority_count > 0:
  Review high-priority events.

if fallback_count > 0:
  Review fallback classifications.

if degraded_source_count > 0:
  Check degraded sources.

if malformed_count > 0:
  Investigate malformed source items.

if loaded_count > 0 and classified_count == 0:
  Classification produced no output.

if attachment_refused_count > 0 or attachment_blocked_count > 0:
  Review blocked/refused attachments.

if review_tsv_available:
  Open/export review TSV for human review.
```

- добавить events needing review table, максимум 50 строк:

```text
event_id
source_id
source_display_name
sender
subject
case_type
priority
confidence
reason_code
is_fallback
attachment_count
review_reason
```

- добавить attachment summary на aggregate уровне без raw content:

```text
total_attachments
preview_available_count
refused_count
blocked_count
unsupported_count
oversized_count
extraction_error_count
```

- добавить evidence/artifact links block:

```text
operator_summary_json
source_diagnostics_json
intake_metadata_json
attachment_extraction_json
normalized_events_json
classified_events_json
rop_review_table_tsv
module_result_json
rop_summary_result_json
steps_json
```

- расширить `/api/rop/dashboard` read-model новыми полями:

```text
kpis
funnel
source_health
classification_distribution
attachment_summary
recommendations
attention_events
evidence_links
available_runs
selected_run_id
```

- сохранить backward compatibility where practical:
  - старые single-source runs;
  - missing `attachment_extraction.json`;
  - missing `source_diagnostics.json`;
  - missing `intake_metadata.json`;
  - malformed JSON artifacts;
  - empty runs;
  - non-ROP runs.

- graceful handling:
  - missing artifact → visible warning / empty block;
  - malformed artifact → warning, not crash;
  - partial run → dashboard still renders;
  - no runs → clear empty state.

- сохранить read-only/security boundary:
  - no GET mutation;
  - no POST routes;
  - no web-triggered ROP run;
  - no mailbox calls;
  - no CRM/Bitrix calls;
  - no module/capability execution from UI;
  - no raw `.eml`;
  - no raw attachment content;
  - no arbitrary storage browsing;
  - no secrets in HTML/API/logs.

- обновить tests:
  - ROP KPI read-model;
  - processing funnel;
  - recommendations;
  - source health;
  - attention events;
  - attachment summary;
  - evidence links;
  - selected run via `run_id`;
  - missing/malformed artifacts;
  - HTML escaping;
  - API payload shape;
  - no GET mutation;
  - no POST routes.

- обновить docs:
  - `docs/product/ui_roadmap.md`;
  - `docs/WEB_UI.md`;
  - `README.ru.md`;
  - `docs/DEV_GUIDE.md`, если usage или route behavior меняется.

**Не включено:**

- удаление legacy `src/beeagent_module/web`;
- auth/RBAC;
- POST/operator actions;
- web-triggered `rop run`;
- mailbox execution;
- CRM/Bitrix execution;
- capability/MCP/n8n execution;
- config editing;
- full attachment-aware dashboard with per-file detail viewer;
- OCR/parsing from UI;
- raw attachment download;
- human review editing;
- manager scoring;
- Bitrix reconciliation UI;
- stable API v1 freeze;
- separate React/Reflex frontend;
- changes to `beeagent-rop`;
- ROP classification/business logic changes.

#### Deliverable

BeeUI-backed `/rop` becomes a useful ROP operator dashboard.

Operator can answer from one screen:

```text
1. Сколько событий пришло?
2. Сколько реально обработано?
3. Какие источники degraded?
4. Какие события требуют внимания?
5. Что делать дальше?
6. Какие artifacts подтверждают вывод?
```

`/api/rop/dashboard` returns a richer read-only operator intelligence payload based on existing artifacts.

No new runtime artifacts are required.

#### Expected artifacts read

```text
storage/runs/<run_id>/operator_summary.json
storage/runs/<run_id>/source_diagnostics.json
storage/runs/<run_id>/intake_metadata.json
storage/runs/<run_id>/attachment_extraction.json
storage/runs/<run_id>/normalized_events.json
storage/runs/<run_id>/classified_events.json
storage/runs/<run_id>/rop_review_table.tsv
storage/runs/<run_id>/module-beeagent-rop/module_result.json
storage/runs/<run_id>/module-beeagent-rop/rop_summary_result.json
storage/runs/<run_id>/steps.json
```

#### Expected `/api/rop/dashboard` payload shape

```json
{
  "ok": true,
  "read_only": true,
  "data": {
    "selected_run_id": "run-id",
    "available_runs": [],
    "kpis": {},
    "funnel": [],
    "source_health": [],
    "classification_distribution": {},
    "attachment_summary": {},
    "recommendations": [],
    "attention_events": [],
    "evidence_links": [],
    "warnings": []
  },
  "warnings": [],
  "meta": {}
}
```

#### Checks

- `uv run pytest -q`;

- targeted BeeUI/ROP dashboard tests;

- `uv run python config/start.py routes`;

- route/API smoke:
  - `/`;
  - `/runs`;
  - `/rop`;
  - `/rop?run_id=<run_id>`;
  - `/api/rop/dashboard`;
  - `/api/rop/dashboard?run_id=<run_id>`;

- single-source run fixture;

- multi-source run fixture;

- degraded source fixture;

- fallback classification fixture;

- high priority events fixture;

- attachment extraction fixture;

- missing artifact fixture;

- malformed artifact fixture;

- no GET mutation;

- no POST routes;

- no mailbox/CRM/module/capability execution from UI;

- no secrets in HTML/API/logs;

- no raw `.eml`;

- no raw attachment content;

- HTML escaping for artifact-derived values;

- SAST mindset review.

SCA is not required unless `pyproject.toml` / `uv.lock` changes.

#### DoD

- `/rop` is visibly richer than UI-4 foundation screen;
- `/rop` supports selected run by `run_id`;
- ROP KPIs are shown;
- processing funnel is shown;
- source health table is shown;
- deterministic recommendations are shown;
- attention events table is shown;
- attachment aggregate summary is shown if artifact exists;
- evidence links are shown;
- `/api/rop/dashboard` exposes the same read-model;
- old/single-source runs still render;
- missing/malformed artifacts do not crash UI;
- dashboard remains read-only;
- no mailbox/CRM/module/capability execution from GET routes;
- no secrets/raw `.eml`/raw attachment content in HTML/API;
- tests and docs updated;
- `pyproject.toml.version` not changed.

#### Status notes (final)

- `build_rop_dashboard_read_model` расширен в `read_model.py`:
  - добавлены helper-функции для KPIs, funnel, source health, classification distribution, attachment summary, recommendations, attention events, evidence links;
  - сохранена backward compatibility для legacy single-source runs и старых полей (`sources`, `classified_count`, `case_type_counts`, `priority_counts`, `fallback_count`, `normalized_count`, `has_attachment_extraction`);
  - missing/malformed artifacts не вызывают crash, а генерируют warning;
  - deterministic recommendations без LLM;
  - attention events capped до 50 строк;
  - evidence links используют allowlist из `artifacts.py`.

- `/rop` переведён на BeeUI shared shell:
  - рендеринг через Jinja2-шаблон `beeagent_page.html`, расширяющий `base.html`;
  - левый sidebar с навигацией (Dashboard, Runs, ROP Dashboard, Modules);
  - Tabler-совместимая вёрстка: card, datagrid, badges, alert, list-group;
  - все artifact-derived значения экранируются.

- `/rop` layout полностью переработан:
  - Row 1: Run Overview (datagrid) + KPI mini-cards (Connected Sources, Loaded Items, Classified Cases, Need Review, High-Priority Cases, Attachments/Preview);
  - Row 2: Recommendations, Evidence & Exports (list-group с available/unavailable), Source Health (compact table);
  - Row 3: Processing Funnel + Source Details (если >1 источника);
  - Row 4: Classification Breakdown (Case Types, Priorities, Reason Codes в 3 колонки);
  - Row 5: Operator Queue (полная таблица, max 50);
  - Row 6: Attachment Processing (KPI mini-cards).

- `/runs/{run_id}/artifacts/{artifact_id}` теперь HTML artifact viewer:
  - breadcrumb (Dashboard → Runs → Run → Artifact);
  - TSV → HTML table;
  - JSON → pretty block + "Open as JSON" link;
  - ошибки/предупреждения в alert;
  - экранирование HTML-значений.

- `/api/runs/{run_id}/artifacts/{artifact_id}` сохранён как JSON envelope.

- `/modules` переведён на BeeUI shell.

- `config/beeui.yml` navigation обновлён под UI-5.

- Tests: 56 тестов в `test_beeui_console.py` (было 50):
  - добавлены: `test_rop_renders_within_shell`, `test_artifact_viewer_html_returns_html_not_json`, `test_artifact_viewer_api_still_json`, `test_tsv_artifact_viewer_renders_table`, `test_json_artifact_viewer_readable`, `test_artifact_viewer_missing_artifact_shows_error`.

- `pyproject.toml.version` не изменён.

- `beeagent-rop` не изменён.

- legacy web не изменён.

- зависимости не изменены.

- CDN не добавлены.

- raw content не раскрывается.

#### UI-5 post-DONE polish — BeeUI 13.1 platform overview dashboard

**Статус:** DONE

What was added:

- `config/beeui.yml`: locale seed (`app.locale.default: en`, `app.locale.available: [en, ru]`);
- `src/beeagent_module/interfaces/ui/locale.py`: locale helper — resolve locale from `?lang=`, translate product labels (en/ru);
- `/` dashboard: enriched `build_dashboard()` with KPI items (Total Runs, Loaded Modules, Latest Run Status, ROP Classified Cases, Needs Review, Degraded Sources), summary dict, Quick Links card, customer-facing layout via overridden `product_dashboard.html` template;
- `/rop`: Tabler URL tabs (`ul.nav.nav-tabs.card-header-tabs`) for run switching (max 5 visible + dropdown for overflow), locale-aware labels in all sections, `col-lg-6` layout for Run Overview + 2x3 KPI grid, locale preserved in `?lang=` across tab links;
- locale-aware labels for all product UI sections on `/rop` and `/`;
- backward-compatible API: `/api/rop/dashboard` unchanged;
- artifact browser: browser route HTML, API route JSON, TSV as table, JSON pretty-escaped, raw `.eml` blocked;
- tests: 30+ new tests for locale, dashboard, Tabler URL tabs, backward-compatible API, artifact split;
- `beeagent_module.interfaces.ui/templates/*.html` added to `pyproject.toml` package-data.

### Итерация UI-6 — Expose latest-N, threads, AI assist, RU labels, operator recommendations

**Статус:** DONE

#### Goal

Сделать результаты BeeAgent It30 видимыми и полезными в BeeUI-backed ROP console: показать latest-N/source selection evidence, thread context, AI assist evidence, RU labels и deterministic operator recommendations в `/rop` и `/api/rop/dashboard`.

#### Почему это нужно

BeeAgent It30 уже добавила runtime/artifact-level слой для ROP MVP:

```text
mailbox/latest-N selection
→ mailbox_selection.json
→ mail_thread_index.json
→ mail_thread_context.json
→ bounded thread_context handoff
→ classified_events.json with optional ROP business fields
→ bounded AI assist evidence
→ public ai_assist_merge module boundary
```

Но если эти данные остаются только в `storage/runs/<run_id>/...`, РОП не получает продуктовой пользы:

- непонятно, какие письма реально попали в последнюю пачку;
- не видно, где письмо является частью цепочки;
- не видно, где AI assist помог, деградировал или был пропущен;
- не видно, какие события требуют ручной проверки именно из-за thread/AI/fallback context;
- русскоязычный оператор видит неполный набор RU labels;
- evidence есть в artifacts, но не собрано в operator-facing view.

UI-6 превращает It30 из backend evidence layer в operator-visible MVP increment.

Главное правило сохраняется:

```text
BeeUI renders.
BeeAgent decides/orchestrates.
beeagent-rop classifies.
```

Эта итерация реализуется в `beeagent`, не в `beeui`, потому что latest-N, thread context, AI assist interpretation и ROP operator recommendations являются product-specific BeeAgent ROP read-model. BeeUI должен только рендерить generic layout blocks.

#### Depends on

- UI-5 — Rich ROP dashboard parity + operator intelligence v1;
- BeeAgent It30 — latest-N fix + thread artifacts + AI providers/execution;
- existing BeeUI adapter-backed custom page support;
- existing BeeUI chart/data table/layout blocks where useful;
- existing artifacts:
  - `mailbox_selection.json`;
  - `mail_thread_index.json`;
  - `mail_thread_context.json`;
  - `classified_events.json`;
  - `rop_ai_assist_requests.json`;
  - `rop_ai_assist_decisions.json`;
  - `rop_ai_assist_results.json`;
  - `operator_summary.json`;
  - `source_diagnostics.json`;
  - `intake_metadata.json`;
  - `attachment_extraction.json`;
  - `rop_review_table.tsv`;
  - `rop_current_state.json`;
  - `rop_dashboard.json`.

#### Change level

```text
security-sensitive
```

Причина:

- расширяется HTML/API exposure для artifact-derived данных;
- добавляются новые allowlisted artifact IDs в UI artifact browser;
- UI читает AI assist artifacts, thread artifacts и mailbox selection artifacts;
- меняется ROP dashboard read-model и API payload;
- значения из email/thread/AI artifacts считаются untrusted input;
- нужно подтвердить отсутствие raw `.eml`, raw attachment content, secrets, provider tokens и AI secret leakage.

SCA не требуется, если `pyproject.toml` / `uv.lock` не меняются.

#### Scope

**Включено:**

- расширить BeeAgent UI artifact allowlist безопасными It30 artifacts:

```text
mailbox_selection_json          -> mailbox_selection.json
mail_thread_index_json          -> mail_thread_index.json
mail_thread_context_json        -> mail_thread_context.json
rop_ai_assist_requests_json     -> rop_ai_assist_requests.json
rop_ai_assist_decisions_json    -> rop_ai_assist_decisions.json
rop_ai_assist_results_json      -> rop_ai_assist_results.json
```

- убедиться, что artifact preview остаётся bounded/redacted:
  - no raw `.eml`;
  - no raw attachment content;
  - no provider credentials;
  - no env values;
  - no secret-like fields;
  - no arbitrary storage browsing.

- расширить ROP dashboard read-model в:

```text
src/beeagent_module/interfaces/ui/read_model.py
```

- расширить `BeeAgentUiAdapter.get_page("rop_dashboard", query)` / related adapter path так, чтобы `/rop` получал новые sections через existing BeeUI `layout[]`, а не через BeeAgent-owned templates;
- добавить latest-N/source selection summary;
- добавить thread summary;
- добавить bounded thread table / thread groups, максимум 50 строк;
- добавить AI assist summary;
- добавить AI assist event table, максимум 50 строк;
- расширить deterministic recommendations без LLM и runtime execution;
- расширить attention/operator queue;
- добавить RU labels для новых UI sections через existing locale helper;
- сохранить `?lang=ru` behavior;
- обновить `config/beeui.yml` tabs for `/rop`.

Expected tabs:

```text
overview
queue
threads
ai_assist
sources
attachments
evidence
bitrix
```

`bitrix` остаётся read-only/reserved/evidence-only в рамках этой итерации.

- расширить `/api/rop/dashboard` payload, сохранив backward-compatible existing fields;
- добавить evidence links for It30 artifacts;
- graceful handling для missing/malformed/old-run scenarios;
- сохранить read-only/security boundary;
- обновить targeted tests и docs.

**Не включено:**

- изменения в `beeagent-rop`;
- новые AI provider calls from UI;
- изменение runtime AI assist execution logic;
- изменение `run_rop_batch_case(...)` behavior;
- изменение It30 artifact generation contract, кроме тестовых fixtures;
- web-triggered `rop run`;
- POST/write actions;
- auth/RBAC;
- CRM/Bitrix write-back;
- mailbox delete/archive/reply/mark-as-read;
- attachment download or raw attachment viewer;
- OCR/deep attachment parsing;
- stable API v1 freeze;
- separate React/Reflex frontend;
- new BeeUI features, unless a blocking generic BeeUI renderer bug is discovered;
- dependency changes.

#### Deliverable

BeeUI-backed `/rop` становится operator-facing surface для It30 evidence.

`/api/rop/dashboard` возвращает тот же enriched read-only model.

No new runtime artifacts are required.

#### Expected artifacts read

```text
storage/runs/<run_id>/mailbox_selection.json
storage/runs/<run_id>/mail_thread_index.json
storage/runs/<run_id>/mail_thread_context.json
storage/runs/<run_id>/rop_ai_assist_requests.json
storage/runs/<run_id>/rop_ai_assist_decisions.json
storage/runs/<run_id>/rop_ai_assist_results.json
storage/runs/<run_id>/classified_events.json
storage/runs/<run_id>/source_diagnostics.json
storage/runs/<run_id>/intake_metadata.json
storage/runs/<run_id>/attachment_extraction.json
storage/runs/<run_id>/operator_summary.json
storage/runs/<run_id>/rop_review_table.tsv
storage/runs/<run_id>/rop_current_state.json
storage/interfaces/rop_dashboard.json
```

#### Checks

- `uv run pytest -q`;
- targeted BeeUI/ROP dashboard tests;
- targeted artifact allowlist tests;
- targeted locale tests;
- `uv run python config/start.py routes`;
- route/API smoke for `/rop`, threads, AI assist, evidence and artifact routes;
- full It30, old-run, disabled, degraded, low-confidence, malformed and threaded-message fixtures;
- SAST mindset review;
- DAST-style route misuse checks for artifact IDs and query parameters.

#### DoD

- `/rop` exposes latest-N/source selection evidence;
- `/rop` exposes thread summary and thread groups/table;
- `/rop` exposes AI assist summary and event-level AI status;
- `/rop?lang=ru` renders RU labels;
- `/api/rop/dashboard` exposes new read-only fields while preserving existing UI-5 fields where practical;
- It30 artifact links are visible;
- old and malformed runs do not crash;
- dashboard remains read-only;
- UI does not call mailbox, CRM, Bitrix, module execution, capability execution or AI providers;
- no raw `.eml`, raw attachment content, provider secrets or env values appear;
- no BeeAgent-owned Jinja templates are added for `/rop`;
- no changes to `beeagent-rop`;
- no dependency changes unless explicitly justified;
- `pyproject.toml.version` not changed;
- tests and docs updated.

#### Status notes — 2026-06-29

- `build_rop_dashboard_read_model` extended with UI-6 helpers;
- safe artifact IDs added to `ARTIFACT_ALLOWLIST`;
- `/rop` tabs extended with `threads` and `ai_assist`;
- `/api/rop/dashboard` extended with latest selection, threads and AI assist evidence;
- RU labels added;
- old/malformed runs render warnings and empty states;
- tests added for full It30, API, routes, locale, old runs, malformed artifacts, allowlist, no mutation and no secret/raw-content exposure;
- route smoke passed;
- full `pytest -q`: 572 passed;
- `pyproject.toml.version` unchanged;
- `beeagent-rop` unchanged;
- `uv.lock` unchanged.

### Итерация UI-7 — BeeUI-backed auth boundary for BeeAgent console

**Статус:** DONE

#### Goal

Добавить минимальную auth/session boundary для BeeUI-backed BeeAgent Web Console, чтобы `/`, `/rop`, `/runs`, `/modules`, artifact browser и read-only API нельзя было открыть без явной аутентификации, когда `web.auth.enabled: true`.

#### Почему это нужно

После UI-6 BeeAgent Web Console стала показывать operator-facing ROP evidence:

```text
latest-N mailbox selection
thread context
AI assist evidence
source/client metadata
artifact links
operator recommendations
```

Эти данные нельзя безопасно показывать по private/customer link без auth boundary.

На момент планирования UI-7 auth boundary имела более высокий приоритет, чем legacy cleanup. После завершения UI-7 развитие продолжилось через UI-8 и UI-8.1, а удаление legacy web осталось отдельной будущей итерацией UI-9.

Главное правило:

```text
BeeUI renders and owns generic auth/session primitives.
BeeAgent owns product config, policy and route integration.
beeagent-rop remains domain-only.
```

Эта итерация реализуется в `beeagent`, но не должна дублировать BeeUI auth internals. BeeAgent должен использовать существующий BeeUI auth/session layer.

#### Depends on

- UI-6 — Expose latest-N, threads, AI assist, RU labels, operator recommendations;
- BeeUI Iteration 13 — Auth/session/CSRF boundary;
- BeeUI Iteration 13.7 — Locale-aware shell labels and query-preserving navigation;
- existing BeeUI embedded app integration in `src/beeagent_module/interfaces/ui/app.py`.

#### Change level

```text
security-sensitive
```

#### Scope

**Включено:**

- добавить config-driven BeeAgent web auth policy в `config/settings.yml`;
- хранить в config только auth mode, principal metadata и env variable names;
- хранить secrets только в env;
- валидировать auth config fail-fast;
- интегрировать BeeAgent app composition с BeeUI auth/session layer;
- защищать BeeAgent HTML и read-only API routes при auth enabled;
- оставить `/health` публичным и sanitized;
- оставить static assets публичными;
- поддержать роли `viewer`, `operator`, `admin`;
- сохранить read-only behavior для всех ролей в UI-7;
- возвращать safe unauthenticated HTML/API response;
- сохранить locale/navigation behavior;
- сохранить no-mutation/no-secret/no-external-execution boundary;
- обновить tests и docs.

**Не включено:**

- custom session/cookie implementation inside BeeAgent;
- custom password hashing inside BeeAgent;
- user registration;
- password reset;
- OAuth/SSO;
- user database;
- multi-tenant RBAC;
- public SaaS auth model;
- config apply;
- admin panel;
- operator actions;
- POST routes;
- CSRF changes beyond using BeeUI existing behavior;
- web-triggered ROP run;
- mailbox delete/archive/reply/mark-as-read;
- CRM/Bitrix write-back;
- changes to `beeagent-rop`;
- ROP business logic changes.

#### Deliverable

BeeAgent Web Console работает в двух явных режимах:

```text
web.auth.enabled: false
  → local/dev read-only mode

web.auth.enabled: true
  → BeeUI-backed login/session boundary protects BeeAgent HTML/API routes
```

#### Checks

- `uv run pytest -q`;
- targeted BeeUI/BeeAgent auth integration tests;
- targeted settings validation tests;
- `uv run python config/start.py routes`;
- auth-disabled, fail-fast, unauthenticated and authenticated scenarios;
- public `/health` and static routes;
- no secrets in HTML/API/logs;
- no GET mutation;
- SAST mindset review;
- DAST-style protected-route misuse checks.

#### DoD

- explicit `web.auth` config contract exists;
- auth-disabled mode preserves local behavior;
- auth-enabled mode fails fast for missing required env secrets;
- HTML/API routes are protected;
- `/health` remains public and sanitized;
- static assets remain accessible;
- principals use env-backed tokens;
- secrets do not appear in YAML, HTML, API, logs or artifacts;
- BeeAgent reuses BeeUI auth/session primitives;
- no operator/action routes are added;
- no external execution is added;
- `beeagent-rop` unchanged;
- `pyproject.toml.version` unchanged;
- tests and docs updated.

### Итерация UI-8 — ROP final decision read-model + recommendations + Bitrix widget payload MVP

**Статус:** DONE

#### Goal

Перевести BeeUI-backed ROP console и Bitrix widget payload на финальную модель решений: deterministic classifier и AI adjudicator формируют готовое `final_decision`, Web UI показывает понятную очередь и рекомендации, а Bitrix widget получает тот же read-model без отдельной бизнес-логики.

#### Почему это нужно

После UI-7 Web Console защищена auth boundary и уже пригодна как private operator console. Но текущий ROP UI всё ещё частично показывает устаревшую модель:

```text
AI Assist tab читает legacy rop_ai_assist, хотя текущий источник правды — rop_ai_adjudicator.
Recommendations tab пустой, если отдельно не запускать rop recommendations.
Queue tab показывает список событий, но не финальную рабочую модель решения.
Bitrix tab/widget не получает полноценный final decision payload.
```

По 100-run acceptance classifier/AI этап достаточно стабилен. Дальше нужен operator-facing слой:

```text
classified_events
+ rop_ai_adjudicator_results
+ routing config
→ final_decision projection
→ recommendations
→ Web UI
→ Bitrix widget payload
```

Главное product-правило:

```text
РОП не подтверждает классификацию вручную.
BeeAgent показывает финальное решение и флаги внимания.
РОП управляет рабочей очередью, а не выбирает sales/tender/logistics/ignore с нуля.
```

#### Depends on

- UI-7 — BeeUI-backed auth boundary for BeeAgent console;
- BeeAgent ROP AI adjudicator artifacts;
- existing ROP artifacts;
- existing Bitrix widget config.

#### Change level

```text
security-sensitive
```

#### Scope

**Включено:**

- добавить current AI adjudicator artifacts в ROP artifact allowlist;
- сделать `rop_ai_adjudicator_results.json` current source of truth для AI tab/read-model;
- оставить legacy `rop_ai_assist_*` только как legacy evidence/fallback;
- исправить AI tab и counters;
- добавить normalized final decision projection;
- для MVP всегда выставлять `bitrix_write_allowed=false`;
- ограничить `automation_allowed` внутренней routing/display автоматизацией;
- использовать `manual_review` только как technical exception/fallback;
- добавить или переиспользовать `rop_final_decisions.json`;
- поддержать computed read-only fallback для старых runs;
- генерировать или переиспользовать `rop_recommendations.json`;
- обновить queue, event detail, overview metrics и Bitrix widget payload;
- сохранить widget read-only/token-protected/no-Bitrix-REST boundary;
- обновить docs и tests.

**Не включено:**

- изменения в `beeagent-rop`;
- новые deterministic classifier rules;
- изменение OpenAI prompt без прямого read-model bug;
- CRM/Bitrix write-back;
- mailbox mutations;
- web-triggered ROP run;
- operator POST actions;
- auth/RBAC changes;
- Bitrix placement install;
- OAuth/OIDC Bitrix app lifecycle;
- separate frontend;
- dependency changes;
- удаление legacy `src/beeagent_module/web`.

#### Deliverable

Web UI и Bitrix widget payload используют одну финальную модель решений.

#### Expected artifacts read

```text
storage/runs/<run_id>/classified_events.json
storage/runs/<run_id>/rop_ai_adjudicator_requests.json
storage/runs/<run_id>/rop_ai_adjudicator_decisions.json
storage/runs/<run_id>/rop_ai_adjudicator_results.json
storage/runs/<run_id>/operator_summary.json
storage/runs/<run_id>/rop_current_state.json
storage/runs/<run_id>/rop_recommendations.json
storage/runs/<run_id>/bitrix_reconciliation.json
```

#### Expected artifacts written

```text
storage/runs/<run_id>/rop_final_decisions.json
storage/runs/<run_id>/rop_recommendations.json
```

#### Checks

- `uv run pytest -q`;
- targeted final-decision, AI adjudicator, recommendations and widget payload tests;
- route listing;
- route/API smoke;
- security/static checks;
- no write-back, raw content or secret leakage.

#### DoD

- AI tab uses current adjudicator artifacts;
- ROP dashboard exposes normalized final decisions;
- Queue links to event detail;
- Recommendations are populated from artifact/read-model;
- Bitrix widget uses the same read-model;
- widget remains read-only and token-protected;
- `bitrix_write_allowed=false`;
- no external mutations;
- malformed/missing artifacts produce warnings;
- `beeagent-rop` unchanged;
- dependencies unchanged unless justified;
- version unchanged;
- tests and docs updated.

#### Status notes

- AI adjudicator artifacts allowlisted;
- `rop_final_decisions.json` artifact-first read-model with computed read-only fallback;
- AI Adjudicator and Final Decisions summaries available;
- Event Detail shows AI Adjudicator and Final Decision sections;
- `/api/rop/dashboard` exposes adjudicator and final-decision fields;
- Bitrix widget API includes bounded final decisions;
- Final decision policy v1 implemented;
- `bitrix_write_allowed` always `false` for MVP.

### Итерация UI-8.1 — Web Console UX increment: Queue, filters, sort, pagination, locale, charts, Event Detail

**Статус:** DONE

#### Goal

Завершить Web Console UX increment: реализовать полноценный Queue tab с серверными фильтрами, multi-select dropdown, сортировкой, пагинацией, унифицированным URL/query builder, unified adapter-level contract для HTML/API parsing и валидации, исправлением date sorting, устранением дублей локали, charts и полным Event Detail page.

#### Почему это нужно

UI-8 реализовал final decision read-model, но Queue tab и общий UX Web Console требовали доработки:

- URL/query параметры формировались вручную;
- HTML/API parsing и валидация были размазаны;
- page number не всегда брался из canonical `paginate_items()`;
- date sorting некорректно обрабатывал missing/malformed даты;
- RU locale содержала дублирующиеся ключи;
- отсутствовали regression-тесты на special-character и invalid input.

#### Depends on

- UI-8 — ROP final decision read-model + recommendations + Bitrix widget payload MVP;
- implementation work from `review/pr152`.

#### Change level

```text
security-sensitive
```

#### Scope

**Включено:**

- единый URL/query builder через `urllib.parse.urlencode`;
- registry dependency BeeUI `beeui>=0.22,<0.30`;
- удаление local editable source;
- canonical query-state preservation;
- unified adapter-level parsing and validation;
- canonical pagination;
- date sorting fix;
- RU locale cleanup;
- regression tests;
- documentation synchronization;
- security checks on exact committed tree.

**Не включено:**

- изменения в `beeagent-rop`;
- изменения в BeeUI;
- удаление legacy `src/beeagent_module/web`;
- auth/RBAC changes;
- CRM/Bitrix write-back;
- web-triggered ROP run;
- новые runtime artifacts;
- local editable BeeUI dependency.

#### Deliverable

Web Console Queue tab с единым URL builder, adapter-level validation, canonical pagination, исправленным date sorting, корректной RU локалью, regression tests и синхронизированной документацией.

#### Checks

- frozen sync/tree after registry dependency transition;
- full pytest suite;
- targeted regression tests;
- routes smoke;
- web smoke;
- required SCA;
- SAST/manual review;
- DAST/manual query abuse;
- logs/artifacts/no-secret/no-mutation.

#### DoD

- единый URL builder используется во всех ROP links;
- adapter-level contract валидирует query parameters;
- canonical pagination используется в HTML/API;
- missing/malformed dates всегда после valid dates;
- RU locale не содержит duplicate keys;
- regression tests покрывают special chars, round-trip, parity и invalid input;
- documentation synchronized;
- security checks completed.

### Итерация UI-8.2 — Tabler Datepicker integration for ROP Queue date-range filtering

**Статус:** DONE

#### Goal

Перевести фильтр `Диапазон дат` на вкладке ROP Queue с browser-native `input[type=date]` на generic Tabler Datepicker contract, предоставляемый BeeUI, без изменения существующей server-side семантики `date_from` / `date_to`.

#### Почему это нужно

UI-8.1 завершил Queue filtering, sorting, pagination и query validation, но текущий `date_range` визуально реализован двумя browser-native date controls.

Эти поля функционально работают, однако не используют Tabler Datepicker/Litepicker и визуально зависят от реализации конкретного браузера.

Presentation layer принадлежит BeeUI. BeeAgent не должен добавлять собственные templates, CSS или JavaScript для исправления generic компонента.

#### Depends on

- UI-8.1 — current Queue filtering/query baseline;
- BeeUI Iteration 13.10 — generic Tabler Datepicker contract;
- published BeeUI release containing Iteration 13.10;
- current BeeAgent adapter-level validation for `date_from` and `date_to`.

#### Change level

```text
security-sensitive
```

Причины:

- обновляется BeeUI dependency и lockfile;
- меняется browser-facing Queue behavior;
- требуется SCA dependency review;
- требуется DAST-style проверка query parameters и route behavior.

#### Scope

**Включено:**

- обновить BeeUI dependency minimum до первой опубликованной версии, содержащей Iteration 13.10;
- обновить `uv.lock` через обычный registry dependency flow;
- использовать generic BeeUI `filter_form.date_range` без BeeAgent-local template/JS/CSS;
- сохранить query parameters:
  - `date_from`;
  - `date_to`;

- сохранить поддержку:
  - только нижней границы;
  - только верхней границы;
  - обеих границ;
  - очистки диапазона;

- сохранить формат `YYYY-MM-DD`;
- сохранить inclusive server-side filtering;
- сохранить rejection для malformed и reversed ranges;
- сохранить Queue `period=all` baseline;
- сохранить query state в:
  - sorting links;
  - pagination links;
  - reset behavior;
  - Event Detail links и back navigation;

- добавить product-level HTML/integration regression tests;
- проверить RU/EN rendering;
- обновить:
  - `docs/product/ui_roadmap.md`;
  - `docs/WEB_UI.md`;
  - `docs/DEV_GUIDE.md`;
  - `README.ru.md`, если user-facing описание меняется.

**Не включено:**

- BeeAgent-local Datepicker template;
- BeeAgent-local Litepicker JavaScript или CSS;
- изменение `date_from` / `date_to` contract;
- combined `date_range` query parameter;
- изменение timezone или inclusive-bound semantics;
- изменение ROP classification;
- изменения в `beeagent-rop`;
- новые runtime artifacts;
- config changes;
- API envelope changes;
- auth/RBAC/CSRF changes;
- POST routes;
- web-triggered ROP execution;
- CRM/Bitrix write-back;
- local editable BeeUI dependency;
- version change.

#### Deliverable

ROP Queue использует выпущенный generic BeeUI Tabler Datepicker component. Пользователь может выбрать начальную дату, конечную дату или обе границы через календарь, а BeeAgent продолжает получать и валидировать прежние `date_from` / `date_to` GET parameters.

#### Source of truth

- date filter semantics and validation:
  - `src/beeagent_module/interfaces/ui/adapter.py`;
  - `src/beeagent_module/cases/rop_dashboard.py`;

- ROP Queue declarative read-model:
  - `src/beeagent_module/interfaces/ui/read_model.py`;

- generic rendering:
  - released BeeUI `filter_form.date_range` contract;

- product UI behavior:
  - `docs/WEB_UI.md`;
  - `docs/product/ui_roadmap.md`.

#### Contract impact

- existing public query contract remains backward-compatible;
- no API or artifact schema changes;
- BeeUI dependency minimum changes;
- rendered HTML changes from native date inputs to the BeeUI Tabler Datepicker markup;
- server-side validation remains authoritative.

#### Expected artifacts or outputs

No new BeeAgent runtime artifacts.

Expected repository outputs:

- updated BeeUI dependency declaration;
- updated `uv.lock`;
- Queue HTML/integration regression tests;
- synchronized UI documentation.

#### Checks

Automated:

```bash
uv run pytest -q
```

Targeted checks must cover:

- `date_from` only;
- `date_to` only;
- both valid bounds;
- equal bounds;
- reversed bounds;
- malformed date;
- Queue filtering remains inclusive;
- generated HTML preserves `name="date_from"` and `name="date_to"`;
- generated HTML contains the BeeUI Tabler Datepicker markup;
- RU and EN locales;
- no CDN or external assets in rendered Queue page;
- GET routes do not mutate runtime state or artifacts.

---

### Итерация UI-8.3 — Canonical ROP Queue table toolbar and shared table presentation

**Статус:** DONE

#### Goal

Adopt the BeeUI canonical Tabler table and functional toolbar contract for the ROP Queue without changing filtering, sorting, pagination or read-only behavior.

#### Scope

Included:

- replace the Queue `filter_form + data_table` layout with one `data_table` containing a functional toolbar;
- preserve date, search, classification, priority, Bitrix status, column visibility, sorting and pagination behavior;
- place the column chooser under an ellipsis action immediately after search;
- remove visible `Диапазон дат` and `Поиск` labels while preserving accessible field names;
- remove the Queue Apply button;
- retain automatic date filtering after selecting or clearing either date;
- use canonical Tabler dropdown buttons for Classification, Priority and Bitrix Status;
- use a standard Tabler button for Reset;
- use the shared BeeUI table presentation for all BeeAgent adapter-backed tables;
- keep functional search/filter toolbar exclusive to ROP Queue unless another page explicitly opts in later;
- update product UI tests and documentation;
- update the BeeUI dependency only after the required BeeUI release is published.

Excluded:

- changes to ROP classification logic;
- changes to filter values or query parameter names;
- changes to event ordering or pagination semantics;
- changes to Bitrix reconciliation;
- write actions;
- product-specific Jinja templates;
- legacy web removal;
- unrelated UI redesign.

#### Deliverable

The ROP Queue is rendered as a single canonical Tabler table card with an embedded functional toolbar, while all existing product behavior and query-state contracts remain unchanged.

Other BeeAgent tables use the same canonical table presentation without receiving Queue controls.

#### Acceptance criteria

- Queue returns one table block rather than separate filter and table cards.
- Search works through the existing `q` GET parameter.
- Date fields use `date_from` and `date_to`.
- Selecting or clearing a date refreshes the table automatically.
- Classification, Priority and Bitrix Status retain existing URL-driven behavior.
- Column visibility retains existing state and links.
- The column chooser is opened through the ellipsis action.
- Reset clears product filters through the existing safe reset URL.
- Apply is absent from Queue.
- Sorting, pagination, `run_id`, `period` and `lang` are preserved.
- Empty and degraded Queue states use the same table shell.
- Other BeeAgent tables do not show search, filter or column controls.
- No ROP-specific rendering logic is added to BeeUI.
- The route remains read-only.
- No source artifacts are modified by GET requests.

#### Checks

- `uv run pytest -q`
- ROP Queue HTML route smoke
- query-state tests for every supported filter
- combined-filter tests
- sorting and pagination tests
- empty/degraded Queue tests
- HTML escaping and unsafe-link tests
- dependency/lock review
- visual review in Russian and English locales
- light, dark and responsive layout review

#### Definition of Done

- BeeUI dependency points to a release containing Iteration 13.11;
- Queue uses one canonical table card;
- all previous GET behavior is preserved;
- other tables remain toolbar-free;
- tests and route smoke pass;
- product UI documentation is updated;
- unrelated existing `uv.lock` changes are not overwritten or mixed into the implementation.

### Итерация UI-8.4 — Locale-aware ROP decision explanations

**Статус:** DONE

#### Goal

Сделать причины классификации, решения AI арбитра и итогового внимания детерминированно локализуемыми в RU/EN без дополнительных AI-вызовов и без хранения отдельных AI-объяснений для каждого языка.

Итерация выполняется после UI-8.3 и до UI-8.5, поскольку embedded Bitrix widgets также будут использовать `attention_reason`.

#### Scope

- использовать существующий `ClassificationReasonCode` как источник локализуемой причины классификации;
- расширить AI adjudicator output стабильным `reason_code` и bounded `evidence_codes`;
- сохранить raw AI reason только как audit/backward-compatible evidence;
- расширить final decision projection полями `attention_reason_code` и `attention_evidence_codes`;
- добавить BeeAgent-owned RU/EN reason catalog;
- добавить locale-aware display fields в Event Detail read-model и API;
- использовать текущий `lang` для формирования display values;
- обеспечить backward-compatible чтение старых adjudicator и final-decision artifacts;
- показывать локализованный legacy fallback без provider calls и без изменения artifacts;
- сохранить BeeUI generic renderer без ROP-specific semantics;
- change level: `security-sensitive`;
- обновить UI contract documentation и tests.

#### Excluded

- второй AI-вызов для перевода или генерации другого языка;
- runtime translation из GET routes;
- отдельные RU/EN AI decisions;
- изменение classification taxonomy или rules в `beeagent-rop`;
- ROP-specific localization в BeeUI;
- новые config keys;
- dependency или lockfile changes;
- CRM/Bitrix write-back;
- mailbox actions;
- изменение auth или authority policy;
- перевод всех исторических raw artifact previews.

#### Deliverable

Один ROP run содержит единый набор semantic reason codes. Event Detail показывает `Причина`, `Причина AI арбитра` и `Причина внимания` на выбранном языке интерфейса, сохраняя raw evidence и backward compatibility.

#### Acceptance criteria

- `lang=ru` показывает три основные причины на русском языке;
- `lang=en` показывает те же semantic reasons на английском языке;
- переключение языка не вызывает AI provider, mailbox, Bitrix или module execution;
- один eligible event по-прежнему вызывает adjudicator provider не более одного раза;
- новые adjudicator artifacts содержат validated reason/evidence codes;
- новые final-decision artifacts содержат structured attention reason fields;
- старые artifacts продолжают открываться без mutation и crash;
- неизвестные или legacy reasons дают explicit localized fallback и warning;
- raw AI reason не является primary HTML display value;
- API сохраняет raw fields и добавляет codes и localized display fields;
- BeeUI и `beeagent-rop` не меняются.

#### Checks

- targeted adjudicator schema and validation tests;
- catalog coverage для всех текущих `ClassificationReasonCode`;
- RU/EN Event Detail HTML и API tests;
- old/new/malformed artifact compatibility tests;
- single-provider-call regression test;
- unknown-code и legacy fallback tests;
- HTML escaping и bounded evidence tests;
- GET no-mutation checks;
- route smoke для Event Detail;
- full `uv run pytest -q`;
- route listing;
- SAST и DAST-style locale/artifact misuse review.

#### DoD

- structured reason contract реализован в `beeagent`;
- все три Event Detail reason values следуют выбранному locale;
- дополнительные AI token costs для локализации отсутствуют;
- UI-8.5 может использовать structured `attention_reason_code`;
- old runs остаются читаемыми;
- GET routes остаются read-only;
- secrets, raw email и attachment content не раскрываются;
- dependencies и lockfile не изменены;
- `pyproject.toml.version` не изменён;
- tests и documentation обновлены.

### Итерация UI-8.5 — Embedded Bitrix ROP Console with SSO

**Статус:** DONE

#### Goal

Открыть существующую BeeAgent ROP Web Console внутри Bitrix24 как Server-Side Local Application with User Interface и автоматически создавать ограниченную BeeUI session из проверенного Bitrix OAuth user context.

#### Scope

- использовать существующую `/rop` Web UI без второго frontend и без новых ROP projections;
- добавить one-time handler `/bitrix/rop/install` для привязки Local Application к одному Bitrix portal;
- добавить `POST /bitrix/rop/launch` для обработки application launch context;
- принимать bounded `AUTH_ID`, `AUTH_EXPIRES`, `DOMAIN` и `member_id`;
- сверять `DOMAIN` с настроенным portal origin;
- сверять `member_id` с автоматически сохранённой installation state;
- проверять `AUTH_ID` через current-user REST call к настроенному Bitrix portal;
- отклонять inactive, invalid, expired и cross-portal launches;
- использовать доступ к приложению, настроенный в Bitrix24, без списка Bitrix user ID в BeeAgent;
- назначать проверенному пользователю least-privileged BeeUI role;
- создавать bounded BeeUI session и выполнять `303 Redirect` на `/rop`;
- поддержать iframe-compatible secure session cookie;
- разрешать framing только настроенному Bitrix portal;
- сохранить Overview, Queue, Threads, AI Assist, Sources, Attachments, Evidence, Bitrix и Recommendations;
- сохранить Event Detail, filters, sorting, pagination и allowlisted artifact links;
- сохранить существующие `/api/bitrix/rop/widget*` routes backward-compatible;
- обновить dependency до выпущенного BeeUI contract с external-principal session и controlled embedding;
- обновить tests и documentation.

#### Excluded

- два отдельных Sales Pulse / Risk Control widget;
- новый ROP read-model или новые KPI projections;
- per-user Bitrix ID lists в `settings.yml`;
- сохранение `AUTH_ID` или `REFRESH_ID`;
- background OAuth token refresh;
- Bitrix events и subscriptions;
- CRM/Bitrix write-back;
- автоматическая регистрация Local Application;
- отдельный frontend или отдельный application service;
- изменения в `beeagent-rop`;
- ROP classification или recommendation changes.

#### Deliverable

Администратор регистрирует `BeeAgent — ROP` как Local Application. Разрешённый пользователь открывает приложение из Bitrix24 и без повторного BeeAgent login получает существующую read-only `/rop` console внутри iframe.

#### Acceptance criteria

- Local Application install и launch handlers доступны только по HTTPS deployment;
- portal binding создаётся один раз и не содержит OAuth secrets;
- copied `/rop` URL без valid BeeUI session не предоставляет доступ;
- valid launch определяет текущего пользователя через Bitrix REST;
- настройки BeeAgent не содержат списков Bitrix user ID;
- invalid domain, member, token, user или launch payload отклоняется;
- `AUTH_ID` и `REFRESH_ID` отсутствуют в URL, HTML, logs и artifacts;
- session cookie работает в supported Bitrix iframe browser;
- framing разрешено только configured portal origin;
- существующая ROP navigation работает без функциональной регрессии;
- existing widget APIs остаются совместимыми;
- GET routes остаются read-only;
- BeeUI используется через опубликованный public contract;
- `beeagent-rop` не меняется.

#### Checks

- targeted settings, install, launch, OAuth verification и session tests;
- malformed, expired, cross-portal и inactive-user scenarios;
- cookie, CSP, `X-Frame-Options`, cache и referrer header tests;
- no-token-leakage и no-GET-mutation tests;
- existing ROP tabs, Event Detail и artifact-link regression tests;
- existing widget API compatibility tests;
- `uv run pytest -q`;
- `./start.sh routes`;
- HTTPS route smoke;
- Chrome/Edge manual smoke inside the real Bitrix Local Application.

#### DoD

- BeeUI prerequisite выпущен и подключён;
- Local Application installation и launch flow реализован в `beeagent`;
- verified Bitrix user получает bounded BeeUI viewer session;
- вся существующая ROP console работает внутри Bitrix iframe;
- user access управляется Bitrix24, а не duplicated BeeAgent user list;
- OAuth secrets не сохраняются и не раскрываются;
- iframe и session policies протестированы;
- documentation синхронизирована;
- `beeagent-rop` unchanged;
- `pyproject.toml.version` unchanged.

### Итерация UI-8.6 — Principal-bound Web auth and scoped console access

**Статус:** PLANNED

#### Goal

Исправить BeeAgent Web authentication identity contract и добавить server-side scoped authorization для multi-module Web Console: local principal должен входить только по своей паре `username + token`, а доступ к Dashboard, ROP, Runs, Modules и будущим module surfaces должен определяться отдельно через explicit principal scopes.

#### Scope

**Включено:**

- сохранить BeeUI-backed session/cookie implementation;
- привязать local login к exact configured `username + token`;
- использовать canonical configured principal identity в signed session;
- расширить `web.auth.principals[]` explicit `scopes`;
- сохранить `role` только как authority level: `viewer`, `operator`, `admin`;
- использовать scopes как resource access dimension;
- поддержать wildcard `*` для explicitly configured full-access principals;
- валидировать scopes fail-fast;
- отклонять duplicate resolved principal token values без раскрытия secrets;
- добавить server-side authorization для protected HTML/API/resource routes;
- default-deny неизвестные protected surfaces для non-wildcard principals;
- обеспечить ROP-only access к `/rop`, Event Detail, ROP API и bounded ROP evidence;
- запретить ROP-only principal общий Dashboard, Runs, Modules и unrelated module artifacts;
- использовать generic BeeUI request-scoped navigation visibility contract;
- скрывать недоступные navigation items;
- направлять ROP-only principal после login на разрешённую ROP surface;
- сохранить Bitrix verified external-principal flow как ROP-only viewer access;
- сохранить auth-disabled loopback development mode;
- обновить tests и documentation.

#### Excluded

- password database;
- user registration;
- password reset;
- OAuth/OIDC для local login;
- tenant model;
- product roles `rop` / `beescan`;
- ROP-specific behavior inside BeeUI;
- operator POST actions;
- admin/config actions;
- CRM/Bitrix write-back;
- changes to `beeagent-rop`.

#### Deliverable

BeeAgent использует модель:

```text
principal identity = exact username + token
authority = role
resource access = scopes
```

`admin + scopes=["*"]` сохраняет полный Web Console access, а `viewer + scopes=["rop"]` видит и может читать только ROP surface и разрешённое ROP evidence.

#### Acceptance criteria

- valid token с неправильным username не аутентифицируется;
- valid username с неправильным token не аутентифицируется;
- successful local session содержит canonical configured principal identity;
- duplicate token values fail fast;
- scopes обязательны и валидируются;
- ROP-only navigation не содержит Dashboard, Runs и Modules;
- direct unauthorized HTML/API requests получают server-side denial;
- ROP-only principal не может перечислять или читать unrelated module runs/artifacts;
- admin wildcard principal сохраняет существующий доступ;
- unknown future protected surface не становится автоматически доступной scoped principal;
- Bitrix embedded verified user продолжает открывать `/rop` без local user list;
- unauthenticated и forbidden остаются разными состояниями;
- secrets не появляются в HTML, API, logs или artifacts;
- auth-disabled loopback mode остаётся совместимым.

#### Checks

- full `uv run pytest -q`;
- targeted settings/auth/session tests;
- correct username + token login;
- wrong username + valid token;
- valid username + wrong token;
- another principal username + valid token;
- duplicate resolved token values;
- missing/invalid/duplicate scopes;
- admin wildcard HTML/API access;
- ROP-only allowed route matrix;
- ROP-only forbidden route matrix;
- direct URL bypass attempts;
- ROP artifact access versus unrelated run/artifact denial;
- unknown protected route default-deny;
- Bitrix embedded ROP session regression;
- login/logout/session rotation regression;
- RU/EN navigation regression;
- route-prefix/navigation regression where applicable;
- no-secret logging review;
- SAST;
- DAST-style auth/authorization misuse checks;
- SCA when BeeUI dependency/lockfile is updated.

#### DoD

- local principal identity is cryptographically bound to its configured credential;
- role and resource scope are separate concepts;
- server-side authorization is authoritative;
- navigation visibility mirrors, but never replaces, authorization;
- multi-module default is least privilege;
- existing admin and Bitrix ROP flows remain supported;
- BeeUI contains no BeeAgent/ROP/BeeScan semantics;
- required BeeUI release is consumed through the registry dependency;
- tests and docs are synchronized;
- rollout documentation requires session invalidation;
- `pyproject.toml.version` is unchanged.

### Итерация UI-9 — Remove legacy BeeAgent web after BeeUI parity

**Статус:** PLANNED

#### Goal

Удалить legacy `src/beeagent_module/web` и оставить BeeUI единственным web framework layer для BeeAgent.

#### Почему это нужно

После UI-4–UI-8.5 BeeAgent имеет BeeUI-backed operator console, auth boundary, final-decision read-model, canonical Queue UX, Event Detail, artifact browser, read-only API и embedded Bitrix widget routes.

Старый package-local web shell:

```text
src/beeagent_module/web
```

продолжает дублировать:

- routes;
- templates;
- static assets;
- artifact sanitization;
- dashboard rendering;
- API behavior.

Дублирование создаёт risk of drift и сохраняет второй web surface без продуктовой необходимости.

#### Depends on

- UI-8.5 — current BeeUI-backed Web Console and embedded widget baseline;
- UI-7 — auth boundary;
- one successful ROP run smoke;
- one web smoke on real or synthetic ROP artifacts;
- artifact browser parity;
- route/API parity for required pages;
- confirmation that no current runtime path imports `beeagent_module.web`.

#### Change level

```text
security-sensitive
```

Причина:

- удаляется legacy web package;
- меняются imports/tests/docs;
- route ownership and package-data boundaries are finalized;
- file/path/artifact access must remain safe.

#### Scope

**Включено:**

- удалить:

```text
src/beeagent_module/web/
```

- удалить legacy templates/static/routes;
- удалить stale imports, tests and docs references;
- оставить `./start.sh web` canonical;
- оставить app composition в:

```text
src/beeagent_module/interfaces/ui/app.py
```

- оставить adapter/read-model/artifact allowlist в:

```text
src/beeagent_module/interfaces/ui/
```

- удалить legacy package-data из `pyproject.toml`;
- сохранить только актуальные BeeAgent-side UI package data;
- обновить:
  - `docs/WEB_UI.md`;
  - `docs/product/ui_roadmap.md`;
  - `README.ru.md`;
  - `docs/DEV_GUIDE.md`;
- выполнить BeeUI-only route/API tests;
- проверить отсутствие stale import `beeagent_module.web`;
- удалить legacy import и compatibility start path из `src/beeagent_module/core/app.py`;
- подтвердить, что canonical `config/start.py web` использует только `beeagent_module.cli.web.run_web`;
- проверить package install/import.

**Не включено:**

- config/admin/actions;
- POST routes;
- новые auth/RBAC changes;
- operator control panel;
- CRM/Bitrix write-back;
- web-triggered ROP run;
- standalone BeeUI service;
- изменения в `beeagent-rop`;
- ROP business rules.

#### Final structure after UI-9

```text
src/beeagent_module/
  cli/
    web.py

  interfaces/
    ui/
      __init__.py
      app.py
      adapter.py
      read_model.py
      artifacts.py
      bounded_read.py

  core/
  cases/
  adapters/
```

#### Checks

- `uv run pytest -q`;
- `./start.sh web --host 127.0.0.1 --port 8780 --no-open`;
- `./start.sh routes`;
- no `src/beeagent_module/web` package;
- no stale import `beeagent_module.web`;
- HTML/API route smoke;
- auth-enabled and auth-disabled smoke;
- artifact browser smoke;
- no GET mutation;
- no secrets;
- no path traversal;
- no raw attachments;
- no external mutations;
- package install/import smoke;
- SAST;
- SCA if dependency/package metadata changes.

#### DoD

- `src/beeagent_module/web` removed;
- BeeUI owns rendering/layout/common UI;
- BeeAgent owns product adapter/read-model/artifact allowlist;
- `./start.sh web` remains canonical;
- route/API/auth/artifact parity covered by tests;
- docs reflect BeeUI-only architecture;
- `pyproject.toml.version` unchanged.

### Итерация UI-10 — Attachment detail integration for ROP Queue and Event Detail

**Статус:** PLANNED

#### Goal

Дополнить существующий aggregate Attachment tab event-level представлением: показать безопасные attachment metadata, extraction/refusal evidence и bounded preview в ROP Queue и Event Detail без raw attachment content leakage.

#### Depends on

- UI-8.3 — current canonical Queue toolbar/table baseline;
- UI-9 — BeeUI-only architecture;
- BeeAgent It25 — Attachment extraction artifacts;
- `beeagent-rop It15 — Use BeeAgent attachment extraction contract in classification`.

#### Scope

**Включено:**

- show attachment metadata:
  - filename;
  - content_type;
  - size_bytes;
  - extraction_status;
  - preview_available;
  - refusal_reason;
  - reason_code;
  - is_refused if present;
- show bounded preview only if artifact contract explicitly marks it safe;
- show classification reason codes affected by attachment preview;
- warnings for unsupported, refused, blocked, oversized and failed extraction scenarios;
- source artifact links;
- integrate with ROP Queue and Event Detail;
- сохранить существующие aggregate attachment KPI и не реализовывать их повторно;
- no raw files served;
- no arbitrary attachment download;
- связать attachment items с `event_id`;
- показать per-attachment metadata в Event Detail;
- добавить безопасный attachment status indicator в Queue;
- показывать bounded preview только при explicit `preview_available=true`;
- ссылаться на существующий `attachment_extraction_json` evidence artifact;
- tests and docs update.

**Не включено:**

- OCR UI;
- full document viewer;
- raw attachment content;
- file upload;
- editing classification;
- CRM write-back;
- web-triggered extraction;
- external parser calls from UI;
- changes to `beeagent-rop`.

#### Deliverable

Оператор видит, какие письма получили attachment-derived context, где extraction/refusal affected classification и где требуется повышенное внимание.

#### Checks

- attachment metadata rendering;
- safe preview rendering;
- refused/unsupported/oversized scenario;
- `.eml` and `message/rfc822` blocked scenarios;
- no raw attachment content served;
- no mutation;
- no external parser calls from UI;
- malformed artifact warning, not crash;
- `uv run pytest -q`.

#### DoD

- attachment status visible and safe;
- raw content not exposed;
- UI remains artifact-only/read-only;
- source artifacts remain traceable.

### Итерация UI-11 — ROP Bitrix reconciliation detail and filtering

**Статус:** PLANNED

#### Goal

Дополнить существующий Bitrix Evidence Board event-level reconciliation details, filters и связью с Queue/Event Detail: показать найденную CRM entity, match quality, ответственного, статус и причины manual review.

#### Depends on

- UI-8 — final decision and Bitrix widget payload baseline;
- UI-8.3 — current canonical Queue and Event Detail baseline;
- UI-8.5 — embedded Bitrix widget/read-model baseline;
- UI-9 — BeeUI-only architecture;
- `BeeAgent It26 — Bitrix read-only reconciliation artifacts`.

#### Scope

**Включено:**

- сохранить существующий Bitrix Evidence Board и aggregate KPI;
- добавить event-level reconciliation fields:
  - entity type;
  - entity id;
  - match status;
  - match quality;
  - confidence;
  - responsible;
  - stage/status;
  - safe_to_use_as_target;
  - needs_manual_review;
  - reconciliation reason;
- добавить фильтры по match status, quality, responsible и manual review;
- добавить ссылки между Queue, Bitrix tab и Event Detail;
- per-event reconciliation fields;
- matched/unmatched/duplicate/responsible/status/review filters;
- Queue and Event Detail integration;
- source artifact links;
- no Bitrix API call from UI;
- no CRM mutation;
- docs and tests update.

**Не включено:**

- CRM write-back;
- task creation;
- lead creation;
- manager scoring;
- automatic dedup merge;
- Bitrix auth setup UI;
- changes to `beeagent-rop`.

#### Deliverable

ROP dashboard показывает CRM read-only reconciliation поверх artifacts без ручного открытия Bitrix JSON.

#### Checks

- matched, unmatched and duplicate scenarios;
- degraded Bitrix connector scenario;
- no CRM calls from UI;
- no mutation;
- no secrets;
- `uv run pytest -q`.

#### DoD

- Bitrix reconciliation visible and explainable;
- UI remains read-only;
- source artifacts remain source of truth.

---

## Этап 3 — Stable backend API

### Итерация UI-12 — Stable BeeAgent Web API contract v1

**Статус:** PLANNED

#### Goal

Стабилизировать JSON API contract для future separate frontend / standalone BeeUI / BeeConsole без реализации отдельного frontend.

#### Depends on

- UI-8.5 — current HTML/API/widget route baseline;
- UI-9 — BeeUI-only route ownership;
- UI-10 and UI-11 must be either completed or explicitly excluded from v1 before API freeze.

#### Scope

**Включено:**

- freeze supported API routes v1:
  - `/api/health`;
  - `/api/dashboard`;
  - `/api/runs`;
  - `/api/runs/{run_id}`;
  - `/api/runs/{run_id}/artifacts`;
  - `/api/runs/{run_id}/artifacts/{artifact_id}`;
  - `/api/rop/dashboard`;
  - `/api/rop/events/{event_id}`;
  - `/api/modules`;
  - `/api/config/read-model`, only if an implemented safe read-model exists;
  - read-only Bitrix widget routes where they belong to the supported external contract;

- stable success envelope;

- stable error envelope;

- compatibility policy;

- auth behavior documentation;

- docs examples;

- fixture payloads for frontend development;

- API contract tests.

Example envelope:

```json
{
  "ok": true,
  "api": "beeagent-ui.v1",
  "read_only": true,
  "data": {},
  "warnings": [],
  "source_refs": [],
  "meta": {}
}
```

**Не включено:**

- React/Reflex frontend;
- new auth/RBAC behavior;
- POST actions;
- DB migration;
- web-triggered runs;
- standalone BeeUI service;
- second backend.

#### Deliverable

Future frontend or standalone BeeUI can consume BeeAgent API without reading filesystem directly and without creating a second backend truth.

#### Checks

- API shape tests;
- success/error envelope tests;
- auth-enabled and auth-disabled behavior;
- missing/malformed artifact scenarios;
- compatibility tests;
- no mutation;
- no secrets;
- `uv run pytest -q`.

#### DoD

- API contract documented;
- supported routes and envelopes frozen;
- HTML and API use compatible read-models;
- auth behavior documented;
- no second backend path introduced.

### Итерация UI-13 — Auth boundary duplicate

**Статус:** RETIRED

#### Reason

Первоначально запланированный UI-13 auth scope полностью покрыт выполненной итерацией UI-7.

UI-13 удалён из active plan и не должен переиспользоваться, чтобы не создавать drift в существующих roadmap/Issue references.

---

## Этап 4 — Operator Control Panel

### Итерация UI-14 — Operator Web Control Panel v0

**Статус:** PLANNED

#### Goal

Добавить первый bounded operator control panel для BeeAgent ROP flow: оператор видит доступные действия, может запускать явно разрешённые read-only/draft-only actions через explicit backend action API, а каждое принятое или отклонённое действие создаёт audit artifact.

#### Depends on

- UI-7 auth boundary already completed and must be reused;
- UI-9 — BeeUI-only route ownership;
- UI-12 — stable BeeAgent Web API contract v1;
- existing BeeAgent backend action/case boundaries;
- existing ROP source, artifact and authority contracts.

#### Scope

**Включено:**

- Control Panel page:
  - `/control`;
  - `/api/operator/actions`;
- action catalog:
  - `view_runs`;
  - `view_rop_dashboard`;
  - `export_review_tsv`;
  - `run_rop_source_flow`;
  - unsupported future actions as denied/not implemented;
- action statuses:
  - `allowed`;
  - `blocked`;
  - `denied`;
- action preview:
  - source_id;
  - items_max;
  - expected authority;
  - expected artifacts;
- bounded POST action for ROP run only if explicitly allowed by config:
  - `operator_controls.enabled`;
  - `operator_controls.allow`;
- использовать существующую BeeUI CSRF boundary для каждого state-changing POST;
- запретить action execution без valid auth, role, CSRF, confirmation и server-side authority check;
- audit artifacts for every accepted/rejected action:

```text
storage/interfaces/operator_actions/<action_id>.json
```

- confirmation step;
- server-side auth/role/authority enforcement;
- no mailbox destructive action;
- no CRM write-back;
- docs update.

**Не включено:**

- arbitrary command execution;
- arbitrary YAML config editor;
- CRM write-back;
- Bitrix lead creation;
- mailbox delete/archive/reply;
- attachment upload;
- manual arbitrary tool/capability execution;
- scheduler/listener;
- new authentication mechanism;
- execution authority granted only by UI or AI output.

#### Deliverable

Operator can use Web Control Panel for bounded BeeAgent actions without hidden execution paths.

#### Checks

- actions read-model;
- allowed/blocked/denied rendering;
- preview route;
- confirmed ROP action if enabled;
- rejected action audit;
- forbidden action denied;
- unauthenticated and unauthorized action denial;
- no mutation on GET routes;
- audit artifact created for accepted/rejected POST;
- no secrets in audit/logs/HTML/API;
- SAST/security review;
- DAST-style route misuse checks;
- `uv run pytest -q`.

#### DoD

- control panel does not bypass BeeAgent core;
- existing UI-7 auth boundary is reused;
- every action has explicit status and reason;
- every POST action is authenticated, authorized, confirmed and audited;
- no hidden mailbox/CRM/capability execution;
- unsupported actions are denied;
- docs updated.

---

## Этап 5 — Admin/support surfaces

### Итерация UI-15 — Support/Admin diagnostics v0

**Статус:** PLANNED

#### Goal

Добавить embedded support/admin diagnostics section для чтения audit/config/module/source diagnostics без отдельной heavy admin platform.

#### Depends on

- UI-7 auth boundary;
- UI-14 action audit artifacts if action diagnostics are included.

#### Scope

**Включено:**

- routes:
  - `/admin`;
  - `/admin/actions`;
  - `/admin/modules`;
  - `/admin/sources`;

- read-only listing:
  - operator action audit;
  - modules diagnostics;
  - source diagnostics;
  - config summary with secrets redacted;

- admin-role protection through existing auth boundary;

- graceful corrupted/missing audit artifacts;

- no mutation.

**Не включено:**

- SQLAdmin;
- DB-backed CRUD;
- user management;
- secrets editing;
- config apply;
- runtime control;
- new auth mechanism.

#### Deliverable

Internal support can inspect diagnostics and audit trail without browsing `storage/`.

#### Checks

- admin auth/role checks;
- admin route smoke;
- audit listing;
- modules listing;
- sources listing;
- secret redaction;
- no mutation;
- `uv run pytest -q`.

#### DoD

- admin/support is read-only;
- existing auth boundary reused;
- no second app/backend;
- no secrets exposed.

---

## Этап 6 — Deferred product/admin platform

### Итерация UI-16 — SQLAdmin evaluation for DB-backed admin only

**Статус:** DEFERRED

#### Goal

Оценить SQLAdmin only when BeeAgent introduces DB-backed entities such as users, tenants, projects, saved presets or review decisions.

#### Scope

Deferred until DB-backed models exist.

#### Not for immediate MVP

Current runtime source of truth is file-based artifacts and config, so SQLAdmin is not useful for the current ROP dashboard/control panel.

### Итерация UI-17 — Standalone BeeUI / separate frontend readiness

**Статус:** DEFERRED

#### Goal

Подготовить BeeAgent к future standalone BeeUI or separate frontend only after embedded BeeUI and stable API are proven.

#### Depends on

- UI-12 stable API contract;
- proven embedded BeeUI operation;
- explicit product need for a separate deployment or frontend.

#### Scope

**Включено later:**

- documented API routes;
- response examples;
- fixture payloads;
- error envelope examples;
- auth integration expectations;
- frontend/standalone dev notes.

**Не включено now:**

- React implementation;
- Reflex implementation;
- API gateway;
- DB migration;
- second backend;
- standalone deployment.

#### Deliverable

Future `BeeConsole` / standalone BeeUI can consume BeeAgent API without filesystem access and without creating a second backend source of truth.

---

## What not to do now

Do not add speculative config/admin/actions outside their selected iteration.

Bounded actions require:

```text
POST routes
existing auth/session/CSRF
server-side authority
confirmation
audit artifacts
explicit action contract
```

Do not add CRM/Bitrix/mailbox write-back without a separate security-sensitive product iteration.

Current safe ROP launch remains CLI unless UI-14 explicitly introduces a bounded and audited action:

```bash
./start.sh rop run --all-sources --items-max 20 --run-id ...
```

GET/read-model UI remains read-only:

```text
run artifacts
→ dashboard
→ review
```

Do not put BeeUI into `beeagent-rop`.

`beeagent-rop` must remain a clean package-based domain module.

Do not add BeeAgent- or ROP-specific behavior to generic BeeUI components.

## Working rule for issues

Для UI track действует правило:

- одна UI-итерация = один coherent product increment;
- один implementation repository = один Issue = один target worktree/branch = один PR;
- если UI-итерация требует изменений в BeeAgent и BeeUI, подготовить отдельный Issue и PR для каждого repository;
- cross-repository Issues должны иметь explicit dependency и merge order;
- один запуск `.agents/prompts/02-implementation-tests.md` обслуживает только один Issue и один implementation target;
- не смешивать BeeUI migration, auth, dashboard-specific features, controls и frontend split в одной задаче;
- текущая последовательность future work:
  - UI-9 legacy web removal;
  - UI-10 attachment event-level integration;
  - UI-11 Bitrix reconciliation detail and filtering;
  - UI-12 stable API;
  - UI-14 bounded controls through existing auth boundary;
  - UI-15 support/admin diagnostics;
  - UI-16/UI-17 deferred platform work;
- existing UI-7 auth boundary must be reused;
- controls require explicit backend contract, confirmation and audit artifacts;
- GET/read-model routes must not mutate state;
- mailbox/CRM/module/capability execution from UI is forbidden unless a future iteration explicitly adds a bounded server-side action path;
- product roadmap ownership and implementation repository ownership may differ;
- companion repository changes are planned only when the existing public contract is insufficient.

## Related documents

Этот документ используется вместе с:

- `docs/ROADMAP.md`;
- `docs/WEB_UI.md`;
- `docs/SDLC.md`;
- `docs/SECURITY.md`;
- `docs/DEV_GUIDE.md`;
- `README.ru.md`;
- BeeUI docs:
  - `beeui/docs/ROADMAP.md`;
  - `beeui/docs/INTEGRATION.md`;
  - `beeui/docs/API_CONTRACT.md`;
  - `beeui/docs/WEB_UI.md`;
  - `beeui/docs/COMPONENTS.md`.
