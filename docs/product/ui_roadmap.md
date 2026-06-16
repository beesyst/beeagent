# UI ROADMAP — beeagent (BeeUI operator console track)

## Purpose

Этот документ фиксирует отдельный пошаговый план развития UI / Operator Web / Control Panel внутри `beeagent`.

UI roadmap нужен как lightweight planning-артефакт для operator/product layer:

- не размывает `docs/ROADMAP.md` деталями web/frontend задач;
- фиксирует порядок перехода BeeAgent Web Console на BeeUI;
- помогает связывать UI Issue → Code → Tests → Artifacts → PR → Merge;
- отделяет dashboard, metrics, auth, API, customer-safe access и bounded controls от core runtime roadmap;
- фиксирует, что BeeAgent core остаётся source of truth, а UI остаётся interface/operator layer;
- фиксирует, что BeeUI становится canonical web framework layer для новых web работ.

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
- каждая UI-итерация реализуется отдельным Issue и PR;
- одна UI-итерация = одно focused изменение.

## Why UI track is separate

UI в BeeAgent является отдельным product/operator layer:

- BeeAgent core отвечает за runtime, orchestration, modules, artifacts, config, capability boundary;
- `beeagent-rop` отвечает за ROP domain logic: classification, duplicate/summary/recommendation;
- UI отвечает за operator-visible read-model, dashboards, artifacts, source links, bounded controls later;
- web UI должен быть пригоден не только для `beeagent-rop`, но и для будущих `beescan`, `merch`, MCP/API/operator surfaces;
- UI задачи важны, но не должны засорять core `docs/ROADMAP.md`.

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

Новый canonical UI direction:

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

считается legacy/frozen surface после BeeUI cutover planning.

Правило:

- новые web features не добавлять в `src/beeagent_module/web`;
- BeeUI integration делать через `src/beeagent_module/interfaces/ui`;
- legacy web удалить после BeeUI MVP parity;
- `./start.sh web` должен остаться canonical entrypoint.

## Vision

| Block                   | Statement                                                                                                                                              |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Track identity**      | UI track развивается как operator-facing interface layer поверх BeeAgent core, artifacts и module outputs, а не как второй runtime или второй backend. |
| **Primary objective**   | Цель UI — дать оператору и заказчику понятную консоль: что пришло, что важно, что degraded, какие actions возможны later и где evidence.               |
| **BeeUI rule**          | BeeUI становится canonical web framework layer для BeeAgent. BeeAgent отдаёт adapter/read-model/artifacts, BeeUI рендерит.                             |
| **Backend rule**        | Backend UI layer остаётся FastAPI-based через BeeUI embedded app. BeeAgent не дублирует BeeUI templates/static/common UI.                              |
| **Frontend rule**       | Frontend v1 — BeeUI server-rendered UI. Separate React/Tabler допускается позже только поверх stable BeeUI/BeeAgent API.                               |
| **Source of truth**     | UI читает `config/settings.yml` и existing artifacts из `storage/`. UI не становится source of truth для runtime/business state.                       |
| **Safety rule**         | UI read-only по умолчанию. Любые write/control actions проходят через explicit product-owned backend action API, validation, confirmation и audit.     |
| **Artifact rule**       | Все значения в UI должны быть traceable к source artifacts. Missing/partial/corrupted data отображается явно.                                          |
| **Module rule**         | UI не содержит ROP business rules. Domain logic остаётся в `beeagent-rop`; UI показывает outputs/artifacts.                                            |
| **Customer rule**       | Customer-facing link возможен только после auth/session/security hardening. До этого web surface local/private only.                                   |
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
  ├─ Auth/session layer later
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
| `beeui`                         | rendering, navigation, layout blocks, artifact browser, HTML/API shell, auth shell later         |
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

- оставаться внутри одного focused scope;
- работать через canonical BeeAgent web entrypoint;
- использовать BeeUI для rendering/common UI;
- использовать BeeAgent interfaces/ui adapter/read-model as product boundary;
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
- закрываться через Issue / PR / tests / artifacts.

Для BeeAgent UI это означает:

- сначала BeeUI migration;
- затем attachment-aware ROP dashboard;
- затем Bitrix reconciliation dashboard;
- затем stable API contract;
- затем auth;
- затем bounded operator controls;
- затем optional standalone/separate frontend;
- не делать control panel до explicit action/audit contract.

## Status values

Допустимые статусы UI-итераций:

- **PLANNED** — запланировано
- **IN PROGRESS** — в работе
- **DONE** — завершено
- **DONE (partial)** — завершено частично, есть ограничения
- **DEFERRED** — отложено до появления evidence/стабилизации контрактов

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
- `pyproject.toml.version` не меняется в обычных UI feature PR.

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

К началу BeeUI migration baseline считается таким:

- BeeAgent имеет legacy read-only Web Console after previous UI work;
- route `/runs` показывает runs;
- route `/runs/<run_id>` показывает run overview;
- route `/runs/<run_id>/rop` показывает ROP dashboard;
- route `/modules` показывает module diagnostics, если artifact доступен;
- web routes читают existing artifacts;
- web routes не запускают ROP run;
- web routes не делают CRM/mailbox actions;
- raw `.eml` и attachment content не должны рендериться;
- path traversal должен блокироваться;
- `beeagent-rop` не меняется из UI задач;
- It24 multi-source artifacts уже отображаются в legacy ROP dashboard;
- BeeAgent It25 attachment extraction artifacts существуют;
- `beeagent-rop It15` consuming attachment metadata is done.

Это baseline. Дальше нужен не дальнейший рост legacy web, а controlled migration to BeeUI.

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

### Почему это нужно

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

### Status notes

- canonical FastAPI app implemented in `src/beeagent_module/web`;
- Jinja2 + vendored Tabler static assets wired into packaged web UI;
- HTML routes preserved for `/`, `/runs`, `/runs/{run_id}`, `/runs/{run_id}/rop`, `/modules`;
- read-only JSON API added for `/api/runs`, `/api/runs/{run_id}`, `/api/rop/runs/{run_id}/dashboard`, `/api/modules`;
- `docs/WEB_UI.md` now fixes the implemented contract.

---

## Этап 2 — ROP operator dashboards

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

Но текущий Web Console/R0P dashboard ещё недостаточно показывает multi-source картину:

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
- legacy `src/beeagent_module/web` оставить как code fallback only до UI-5, но не развивать;
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
- detailed attachment-aware dashboard оставить для UI-6;
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

#### UI-5 post-DONE polish (BeeUI 13.1 platform overview dashboard)

**Статус:** DONE (добавлено post-merge после UI-5)

What was added:

- `config/beeui.yml`: locale seed (`app.locale.default: en`, `app.locale.available: [en, ru]`);
- `src/beeagent_module/interfaces/ui/locale.py`: locale helper — resolve locale from `?lang=`, translate product labels (en/ru);
- `/` dashboard: enriched `build_dashboard()` with KPI items (Total Runs, Loaded Modules, Latest Run Status, ROP Classified Cases, Needs Review, Degraded Sources), summary dict, Quick Links card, customer-facing layout via overridden `product_dashboard.html` template;
- `/rop`: Tabler URL tabs (`ul.nav.nav-tabs.card-header-tabs`) for run switching (max 5 visible + dropdown for overflow), locale-aware labels in all sections, `col-lg-6` layout for Run Overview + 2x3 KPI grid, locale preserved in `?lang=` across tab links;
- Locale-aware labels for all product UI sections on `/rop` and `/`;
- Backward-compatible API: `/api/rop/dashboard` unchanged;
- Artifact browser: browser route HTML, API route JSON, TSV as table, JSON pretty-escaped, raw `.eml` blocked;
- Tests: 30+ new tests for locale, dashboard, Tabler URL tabs, backward-compatible API, artifact split;
- `beeagent_module.interfaces.ui/templates/*.html` added to `pyproject.toml` package-data.

### Итерация UI-6 — Remove legacy BeeAgent web after BeeUI MVP parity

**Статус:** PLANNED

#### Goal

Удалить legacy `src/beeagent_module/web` и оставить BeeUI единственным web framework layer для BeeAgent.

#### Почему это нужно

После UI-4 BeeAgent будет иметь BeeUI-backed operator console. Старый package-local web shell:

```text
src/beeagent_module/web
```

будет дублировать:

- routes;
- templates;
- static assets;
- artifact sanitization;
- dashboard rendering;
- API behavior.

Дублирование создаёт risk of drift. После route/API smoke нужно удалить legacy web.

#### Depends on

- BeeAgent UI-4;
- one successful ROP run smoke;
- one web smoke on real/synthetic ROP artifacts;
- artifact browser parity;
- route/API parity for required MVP pages.

#### Change level

```text
security-sensitive
```

Причина:

- удаляется legacy web package;
- меняются imports/tests/docs;
- route ownership changes;
- package data changes;
- file/path/artifact access must remain safe.

#### Scope

**Включено:**

- удалить:

```text
src/beeagent_module/web/
```

- удалить legacy templates/static/routes;
- удалить stale imports/tests/docs references;
- оставить `./start.sh web` canonical;
- оставить app composition в:

```text
src/beeagent_module/interfaces/ui/app.py
```

- оставить adapter/read-model/artifact allowlist в:

```text
src/beeagent_module/interfaces/ui/
```

- удалить legacy package-data from `pyproject.toml`:

```toml
[tool.setuptools.package-data]
"beeagent_module.web" = [...]
```

- оставить only relevant package data if BeeAgent-side UI package needs it;
- update `docs/WEB_UI.md`;
- update `docs/product/ui_roadmap.md`;
- update `README.ru.md`;
- update `docs/DEV_GUIDE.md`;
- route/API tests on BeeUI-only web;
- check no stale imports:

```text
beeagent_module.web
```

- check no stale artifact/browser routes from legacy web;
- check package install/import works.

**Не включено:**

- config/admin/actions;
- POST routes;
- auth/RBAC;
- operator control panel;
- Bitrix;
- CRM write-back;
- web-triggered ROP run;
- BeeUI standalone service;
- changes to `beeagent-rop`;
- ROP business rules.

#### Final structure after UI-5

```text
src/beeagent_module/
  cli/
    web.py               # optional if extracted

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
- `./start.sh web --host 127.0.0.1 --port 8780 --no-open` if supported;
- `./start.sh routes` if route command exists;
- no `src/beeagent_module/web` package;
- no stale import `beeagent_module.web`;
- `/` works;
- `/health` works;
- `/runs` works;
- `/runs/{run_id}` works;
- `/runs/{run_id}/artifacts` works;
- `/runs/{run_id}/artifacts/{artifact_id}` works;
- `/rop` works;
- `/modules` works;
- `/api/dashboard` works;
- `/api/rop/dashboard` works;
- GET routes read-only;
- no secrets;
- no path traversal;
- no raw attachments;
- no mailbox/CRM actions;
- no module/capability execution from GET routes;
- package install/import smoke;
- SAST;
- SCA if dependency/package metadata changes.

#### DoD

- `src/beeagent_module/web` removed;
- BeeUI owns rendering/layout/common UI;
- BeeAgent owns product adapter/read-model/artifact allowlist;
- `./start.sh web` remains canonical;
- route/API parity covered by tests;
- docs reflect BeeUI-only architecture;
- `pyproject.toml.version` unchanged.

---

## Этап 2 — ROP operator dashboards on BeeUI

### Итерация UI-7 — Attachment-aware ROP dashboard

**Статус:** PLANNED

#### Goal

Показать attachment preview / extraction status / refusal status в BeeUI-backed ROP dashboard без raw attachment content leakage.

#### Depends on

- BeeAgent It25 — Attachment extraction artifacts;
- `beeagent-rop It15 — Use BeeAgent attachment extraction contract in classification`;
- BeeAgent UI-4 or UI-5.

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

- warnings for:
  - unsupported attachment;
  - refused attachment;
  - blocked `.eml`;
  - `message/rfc822`;
  - extraction failure;
  - oversized file;

- source artifact links;

- integrate with ROP event table;

- aggregate attachment KPIs:
  - attachment_count;
  - preview_available_count;
  - refused_count;
  - unsupported_count;
  - extraction_error_count;

- no raw files served;

- no arbitrary attachment download;

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

Оператор видит, какие письма получили attachment-derived context, где extraction/refusal affected classification, и где нужна manual review.

#### Checks

- attachment metadata rendering;
- safe preview rendering;
- refused/unsupported/oversized scenario;
- `.eml` blocked scenario;
- `message/rfc822` blocked scenario;
- no raw attachment content served;
- no mutation;
- no external parser calls from UI;
- malformed attachment artifact warning, not crash;
- `uv run pytest -q`.

#### DoD

- attachment status is visible and safe;
- raw content is not exposed;
- UI remains artifact-only/read-only;
- source artifacts remain traceable.

### Итерация UI-8 — ROP Bitrix reconciliation dashboard

**Статус:** PLANNED

#### Goal

После BeeAgent It26 показать read-only Bitrix reconciliation evidence в BeeUI-backed ROP dashboard: найден ли lead/deal/contact, есть ли дубль, кто ответственный, какой статус и где требуется ручная проверка.

#### Depends on

- `BeeAgent It26 — Bitrix read-only reconciliation artifacts`;
- BeeAgent UI-4 or UI-5.

#### Scope

**Включено:**

- Bitrix reconciliation summary:
  - matched lead/deal/contact count;
  - unmatched count;
  - duplicate candidates;
  - needs manual review;
  - responsible manager if available;
  - Bitrix status if available;

- per-event reconciliation columns;

- filters:
  - matched/unmatched;
  - duplicate;
  - responsible;
  - status;
  - needs_review;

- source artifact links;

- no Bitrix API call from UI;

- no CRM mutation;

- docs update.

**Не включено:**

- CRM write-back;
- task creation;
- lead creation;
- manager scoring;
- automatic dedup merge;
- Bitrix auth setup UI;
- changes to `beeagent-rop`.

#### Deliverable

ROP dashboard показывает CRM-read-only reconciliation поверх artifacts без ручного открытия Bitrix JSON.

#### Checks

- matched scenario;
- unmatched scenario;
- duplicate candidate scenario;
- degraded Bitrix connector scenario;
- no CRM calls from UI;
- no mutation;
- no secrets;
- `uv run pytest -q`.

#### DoD

- Bitrix reconciliation is visible and explainable;
- UI remains read-only;
- source artifacts remain source of truth.

---

## Этап 3 — Stable backend API

### Итерация UI-9 — Stable BeeAgent Web API contract v1

**Статус:** PLANNED

#### Goal

Стабилизировать JSON API contract для future separate frontend / standalone BeeUI / BeeConsole без реализации React/Reflex frontend.

#### Scope

**Включено:**

- freeze API routes v1:
  - `/api/health`;
  - `/api/dashboard`;
  - `/api/runs`;
  - `/api/runs/{run_id}`;
  - `/api/runs/{run_id}/artifacts`;
  - `/api/runs/{run_id}/artifacts/{artifact_id}`;
  - `/api/rop/dashboard`;
  - `/api/modules`;
  - `/api/config/read-model`;

- stable response envelope:

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

- stable error envelope;
- docs examples;
- fixture payloads for frontend development;
- API tests.

**Не включено:**

- React/Reflex frontend;
- auth/RBAC;
- POST actions;
- DB migration;
- web-triggered runs;
- standalone BeeUI service.

#### Deliverable

Future frontend or standalone BeeUI can consume BeeAgent API without reading filesystem directly.

#### Checks

- API shape tests;
- error envelope tests;
- missing/malformed artifact scenarios;
- no mutation;
- no secrets;
- `uv run pytest -q`.

#### DoD

- API contract is documented;
- HTML and API use compatible read-models;
- no second backend path is introduced.

---

## Этап 4 — Auth and customer-safe access

### Итерация UI-10 — Web auth boundary v0

**Статус:** PLANNED

#### Goal

Добавить минимальную auth/session boundary для BeeAgent Web Console через BeeUI, чтобы её можно было безопаснее показывать заказчику/оператору по ссылке в private deployment.

#### Change level

```text
security-sensitive
```

#### Scope

**Включено:**

- use BeeUI auth/session boundary if available;

- config-driven auth:
  - `web.auth.enabled`;
  - `web.auth.mode`;
  - `web.auth.username_env` or token env;
  - `web.auth.password_env` or token env;
  - session secret env;

- fail-fast validation for mandatory auth config when enabled;

- login/logout if session mode;

- API protection;

- no auth secrets in logs/artifacts;

- protect HTML and API routes;

- local/private deployment note;

- tests.

**Не включено:**

- full RBAC;
- OAuth;
- multi-tenant user DB;
- password reset;
- public internet deployment automation;
- action controls.

#### Deliverable

Web Console can require auth before showing runs/dashboard/API.

#### Checks

- auth disabled explicit local mode;
- auth enabled success;
- auth enabled failure;
- missing env fail-fast;
- API protected;
- no password leakage;
- no secrets in logs/HTML/API;
- SAST;
- SCA only if dependencies change;
- `uv run pytest -q`.

#### DoD

- auth boundary is explicit;
- config is source of truth;
- secrets only from env;
- customer-safe private link becomes possible with deployment hardening notes.

---

## Этап 5 — Operator Control Panel

### Итерация UI-11 — Operator Web Control Panel v0

**Статус:** PLANNED

#### Goal

Добавить первый bounded operator control panel для BeeAgent ROP flow: оператор видит доступные действия, может запускать safe read-only/draft-only actions через explicit backend action API, а каждое действие создаёт audit artifact.

#### Depends on

- UI-8 stable API preferred;
- UI-9 auth preferred before customer-facing usage;
- BeeAgent It24/It25/It26 as backend evidence layers.

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
  - future placeholders as denied/not_implemented;

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

- audit artifacts for every accepted/rejected action:

```text
storage/interfaces/operator_actions/<action_id>.json
```

- confirmation step;
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
- manual tool/capability execution;
- role-based multi-user admin;
- scheduler/listener.

### Deliverable

Operator can use Web Control Panel for bounded BeeAgent actions without hidden execution paths.

### Checks

- actions read-model;
- allowed/blocked/denied rendering;
- preview route;
- confirmed ROP run action if enabled;
- rejected action audit;
- forbidden action denied;
- no mutation on GET routes;
- audit artifact created for POST;
- no secrets in audit/logs/HTML/API;
- SAST/security review;
- DAST-style route misuse checks if practical;
- `uv run pytest -q`.

#### DoD

- control panel does not bypass BeeAgent core;
- every action has explicit status and reason;
- every POST action is audited;
- no hidden mailbox/CRM/capability execution;
- unsupported actions are denied, not hidden as available;
- docs updated.

---

## Этап 6 — Admin/support surfaces

### Итерация UI-12 — Support/Admin diagnostics v0

**Статус:** PLANNED

#### Goal

Добавить embedded support/admin diagnostics section для чтения audit/config/module/source diagnostics без отдельной heavy admin platform.

#### Scope

**Включено:**

- route:
  - `/admin`;
  - `/admin/actions`;
  - `/admin/modules`;
  - `/admin/sources`;

- read-only listing:
  - operator action audit;
  - modules diagnostics;
  - source diagnostics;
  - config summary with secrets redacted;

- graceful corrupted/missing audit artifacts;

- no mutation.

**Не включено:**

- SQLAdmin;
- DB-backed CRUD;
- user management;
- secrets editing;
- config apply;
- runtime control.

#### Deliverable

Internal support can inspect diagnostics and audit trail without browsing `storage/`.

#### Checks

- admin route smoke;
- audit listing;
- modules listing;
- sources listing;
- secret redaction;
- no mutation;
- `uv run pytest -q`.

#### DoD

- admin/support is read-only;
- no second app/backend;
- no secrets exposed.

---

## Этап 7 — Deferred product/admin platform

### Итерация UI-13 — SQLAdmin evaluation for DB-backed admin only

**Статус:** DEFERRED

#### Goal

Оценить SQLAdmin only when BeeAgent introduces DB-backed entities such as users, tenants, projects, saved presets or review decisions.

#### Scope

Deferred until DB-backed models exist.

#### Not for immediate MVP

Current runtime source of truth is file-based artifacts and config, so SQLAdmin is not useful for current ROP dashboard/control panel.

## Итерация UI-13 — Standalone BeeUI / separate frontend readiness

**Статус:** DEFERRED

#### Goal

Подготовить BeeAgent к future standalone BeeUI or separate frontend only after embedded BeeUI and stable API are proven.

#### Scope

**Включено later:**

- documented API routes;
- response examples;
- fixture payloads;
- error envelope examples;
- frontend/standalone dev notes.

**Не включено now:**

- React implementation;
- Reflex implementation;
- API gateway;
- DB migration;
- second backend;
- standalone deployment.

#### Deliverable

Future `BeeConsole` / standalone BeeUI can consume BeeAgent API without filesystem access.

---

## What not to do now

Do not add config/admin/actions in the BeeUI migration sprint.

This would immediately require:

```text
POST routes
auth/session/CSRF
audit artifacts
settings mutation
operator authority
```

This is separate security-sensitive scope after MVP.

Do not add web-triggered ROP run now.

Current safe launch remains CLI:

```bash
./start.sh rop run --all-sources --items-max 20 --run-id ...
```

UI should remain read-only:

```text
run artifacts
→ dashboard
→ review
```

Do not put BeeUI into `beeagent-rop`.

`beeagent-rop` must remain a clean package-based domain module.

## Working rule for issues

Для UI track действует правило:

- одна UI-итерация = один Issue = один PR;
- не смешивать BeeUI migration, auth, dashboard-specific features, controls и frontend split в одной задаче;
- сначала BeeUI read-only visibility;
- затем remove legacy;
- затем attachment/Bitrix dashboards;
- затем stable API;
- затем auth;
- затем bounded controls;
- controls require audit artifacts;
- GET/read-model routes must not mutate state;
- mailbox/CRM/module/capability execution from UI is forbidden unless future iteration explicitly adds bounded action path.

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
