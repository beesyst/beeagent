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

Эта итерация реализуется в `beeagent`, не в `beeui`, потому что latest-N, thread context, AI assist interpretation and ROP operator recommendations являются product-specific BeeAgent ROP read-model. BeeUI должен только рендерить generic layout blocks.

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
- UI читает AI assist artifacts, thread artifacts and mailbox selection artifacts;
- меняется ROP dashboard read-model and API payload;
- значения из email/thread/AI artifacts считаются untrusted input;
- нужно подтвердить отсутствие raw `.eml`, raw attachment content, secrets, provider tokens and AI secret leakage.

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

- расширить `BeeAgentUiAdapter.get_page("rop_dashboard", query)` / related adapter path так, чтобы `/rop` получал новые sections через existing BeeUI `layout[]`, а не через BeeAgent-owned templates.

- добавить latest-N/source selection summary:

```text
latest_selection:
  run_id
  strategy
  selected_count
  source_count
  sources[]
  newest_message_at
  oldest_message_at
  warnings[]
  evidence_artifact_id
```

- добавить thread summary:

```text
thread_summary:
  thread_count
  events_with_thread_context
  reply_or_forward_count
  linked_by_references_count
  linked_by_subject_fallback_count
  source_client_scoped_fallback_count
  warnings[]
  evidence_artifact_ids[]
```

- добавить bounded thread table / thread groups, максимум 50 строк:

```text
threads[]:
  thread_id
  event_count
  source_id
  client_id
  latest_subject
  latest_sender
  previous_event_ids_count
  has_reply_or_forward
  previous_case_type
  previous_case_subtype
  confidence
  review_reason
```

- добавить AI assist summary:

```text
ai_assist_summary:
  evidence_available
  enabled_if_known
  eligible_count
  request_count
  decision_count
  result_count
  ok_count
  used_count
  low_confidence_count
  invalid_output_count
  provider_unavailable_count
  module_contract_unavailable_count
  blocked_count
  degraded_count
  status_counts
  warnings[]
  evidence_artifact_ids[]
```

- добавить AI assist event table, максимум 50 строк:

```text
ai_assist_events[]:
  event_id
  source_id
  sender
  subject
  deterministic_case_type
  ai_status
  ai_used
  ai_confidence
  final_case_type
  final_priority
  reason_code
  review_reason
```

- расширить deterministic recommendations.

Recommendations должны строиться без LLM и без runtime execution, только из existing artifacts:

```text
if latest_selection.selected_count == 0:
  Show empty/latest-N recommendation.

if thread_summary.events_with_thread_context > 0:
  Review threaded conversations first.

if ai_assist_summary.degraded_count > 0:
  Review AI degraded events.

if ai_assist_summary.module_contract_unavailable_count > 0:
  Check ai_assist_merge module contract.

if ai_assist_summary.low_confidence_count > 0:
  Review low-confidence AI assist events manually.

if high_priority_count > 0:
  Review high-priority events.

if fallback_count > 0:
  Review fallback classifications.

if degraded_source_count > 0:
  Check degraded sources.

if review_tsv_available:
  Open/export review TSV for human review.
```

- расширить attention/operator queue так, чтобы `review_reason` мог учитывать:
  - high priority;
  - fallback classification;
  - AI degraded;
  - AI low confidence;
  - AI merge unavailable;
  - thread context present;
  - missing classification;
  - source degraded;
  - attachment refused/blocked.

- добавить RU labels для новых UI sections через existing locale helper:

```text
Latest selection
Threads
AI Assist
AI status
Selected emails
Threaded conversations
Review AI degraded events
Review threaded conversations
Module contract unavailable
Low confidence
Evidence
```

- сохранить `?lang=ru` behavior:
  - invalid lang falls back safely;
  - `lang` сохраняется в `/rop` tab/run links where practical;
  - API payload remains language-neutral where practical, or returns labels only in presentation/layout metadata.

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

- расширить `/api/rop/dashboard` payload, сохранив backward-compatible existing fields.

New fields:

```text
latest_selection
thread_summary
threads
ai_assist_summary
ai_assist_events
recommendations
attention_events
evidence_links
warnings
```

- добавить evidence links for It30 artifacts:

```text
mailbox_selection_json
mail_thread_index_json
mail_thread_context_json
rop_ai_assist_requests_json
rop_ai_assist_decisions_json
rop_ai_assist_results_json
```

- graceful handling:
  - missing It30 artifacts → visible warning / empty section;
  - malformed It30 artifact → warning, not crash;
  - old runs before It30 → dashboard still renders;
  - AI assist disabled → explicit empty/disabled state;
  - AI assist artifacts missing → explicit unavailable state;
  - no threads → empty state;
  - no latest-N selection artifact → warning, not crash.

- preserve read-only/security boundary:
  - no GET mutation;
  - no POST routes;
  - no web-triggered `rop run`;
  - no mailbox calls from UI;
  - no CRM/Bitrix calls from UI;
  - no module/capability execution from UI;
  - no AI provider calls from UI;
  - no raw `.eml`;
  - no raw attachment content;
  - no arbitrary storage browsing;
  - no secrets in HTML/API/logs.

- обновить tests:
  - latest selection summary;
  - thread summary;
  - thread groups/table;
  - AI assist summary;
  - AI assist events;
  - operator recommendations;
  - RU labels;
  - `/rop?lang=ru`;
  - `/rop?tab=threads`;
  - `/rop?tab=ai_assist`;
  - `/api/rop/dashboard` payload shape;
  - old run without It30 artifacts;
  - missing/malformed It30 artifacts;
  - artifact allowlist access for new artifact IDs;
  - non-allowlisted artifact rejection still works;
  - no GET mutation;
  - no raw `.eml` / raw attachment content / secrets in HTML/API.

- обновить docs:
  - `docs/product/ui_roadmap.md`;
  - `docs/WEB_UI.md`;
  - `README.ru.md`;
  - `docs/DEV_GUIDE.md`, если меняется usage/smoke flow.

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

BeeUI-backed `/rop` becomes the operator-facing surface for It30 evidence.

Operator can answer from one screen:

```text
1. Какие последние письма попали в обработку?
2. Из каких источников они пришли?
3. Какие письма связаны в цепочки?
4. Где thread context мог повлиять на классификацию?
5. Где AI assist помог?
6. Где AI assist degraded / low confidence / unavailable?
7. Какие события РОП должен проверить первыми?
8. Какие artifacts подтверждают вывод?
```

`/api/rop/dashboard` returns the same enriched read-only model.

No new runtime artifacts are required. This iteration reads existing artifacts and exposes them safely through BeeAgent UI read-model and BeeUI rendering.

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

#### Expected `/api/rop/dashboard` payload extension

```json
{
  "ok": true,
  "read_only": true,
  "data": {
    "selected_run_id": "run-id",
    "latest_selection": {
      "selected_count": 20,
      "strategy": "latest_n",
      "source_count": 1,
      "sources": []
    },
    "thread_summary": {
      "thread_count": 7,
      "events_with_thread_context": 5,
      "reply_or_forward_count": 3
    },
    "threads": [],
    "ai_assist_summary": {
      "evidence_available": true,
      "eligible_count": 10,
      "ok_count": 6,
      "used_count": 4,
      "degraded_count": 2,
      "status_counts": {}
    },
    "ai_assist_events": [],
    "recommendations": [],
    "attention_events": [],
    "evidence_links": [],
    "warnings": []
  },
  "warnings": [],
  "meta": {}
}
```

Existing UI-5 fields must remain available where practical:

```text
kpis
business_kpi
series
funnel
source_health
classification_distribution
attachment_summary
run_id
summary
sources
classified_count
case_type_counts
priority_counts
fallback_count
```

#### Expected HTML behavior

`GET /rop` renders BeeUI adapter-backed ROP dashboard with tabs:

```text
Overview
Queue
Threads
AI Assist
Sources
Attachments
Evidence
Bitrix
```

`GET /rop?lang=ru` renders Russian labels for all new UI-6 sections.

`GET /rop?tab=threads` shows thread summary/table.

`GET /rop?tab=ai_assist` shows AI assist summary/table.

`GET /rop?tab=evidence` includes It30 artifact links.

All sections must render from BeeAgent adapter/read-model/layout and BeeUI generic blocks. BeeAgent must not add product-owned Jinja templates for this iteration.

#### Checks

- `uv run pytest -q`;

- targeted BeeUI/ROP dashboard tests;

- targeted artifact allowlist tests;

- targeted locale tests;

- `uv run python config/start.py routes`;

- route/API smoke:
  - `/`;
  - `/rop`;
  - `/rop?lang=ru`;
  - `/rop?tab=threads`;
  - `/rop?tab=ai_assist`;
  - `/rop?tab=evidence`;
  - `/api/rop/dashboard`;
  - `/api/rop/dashboard?run_id=<run_id>`;
  - `/runs/<run_id>/artifacts/mailbox_selection_json`;
  - `/runs/<run_id>/artifacts/mail_thread_index_json`;
  - `/runs/<run_id>/artifacts/mail_thread_context_json`;
  - `/runs/<run_id>/artifacts/rop_ai_assist_results_json`;

- fixture scenarios:
  - full It30 run;
  - old run without It30 artifacts;
  - AI assist disabled;
  - AI assist degraded;
  - module contract unavailable;
  - low confidence AI result;
  - threaded messages;
  - no thread context;
  - missing/malformed It30 artifacts.

Security/static checks:

```bash
rg -n "raw_eml|raw_message|attachment_content|content_bytes|payload_bytes|message/rfc822" src/beeagent_module/interfaces/ui tests || true
rg -n "CUSTOM_AI_API_KEY|OPENAI_API_KEY|password|secret|token" storage/runs storage/interfaces logs || true
rg -n "beeagent_rop\.(domain|services|cases)" src/beeagent_module || true
rg -n "POST|delete|archive|mark-as-read|reply|write-back" src/beeagent_module/interfaces/ui tests || true
git diff -- pyproject.toml uv.lock
```

SAST mindset review required.

SCA is not required unless dependencies change.

DAST-style route misuse checks required for artifact route IDs and tab/lang/run_id query params.

IAST is not required.

Fuzzing is not required; malformed JSON fixture tests are enough.

#### DoD

- `/rop` exposes latest-N/source selection evidence;
- `/rop` exposes thread summary and thread groups/table;
- `/rop` exposes AI assist summary and event-level AI status;
- `/rop?lang=ru` renders RU labels for all new UI-6 sections;
- `/rop?tab=threads` and `/rop?tab=ai_assist` work;
- `/api/rop/dashboard` exposes new read-only fields while preserving existing UI-5 fields where practical;
- It30 artifact links are visible in evidence section;
- new It30 artifacts are allowlisted safely;
- old runs without It30 artifacts still render;
- missing/malformed It30 artifacts produce warnings, not crashes;
- dashboard remains read-only;
- UI does not call mailbox, CRM, Bitrix, module execution, capability execution or AI providers;
- no raw `.eml`, raw attachment content, provider secrets or env values appear in HTML/API/logs/artifacts;
- no BeeAgent-owned Jinja templates are added for `/rop`;
- no changes to `beeagent-rop`;
- no dependency changes unless explicitly justified;
- `pyproject.toml.version` not changed;
- tests and docs updated.

#### Status notes (final — 2026-06-29)

- `build_rop_dashboard_read_model` extended with `_build_latest_selection`, `_build_thread_summary`, `_build_threads`, `_build_ai_assist_summary`, `_build_ai_assist_events`, `_build_it30_recommendations`;
- New safe artifact IDs already present in `ARTIFACT_ALLOWLIST` (UI-4/UI-5 baseline): `mailbox_selection_json`, `mail_thread_index_json`, `mail_thread_context_json`, `rop_ai_assist_requests_json`, `rop_ai_assist_decisions_json`, `rop_ai_assist_results_json`;
- `/rop` tabs extended with `threads` and `ai_assist` in `config/beeui.yml`, `adapter.py` allowed_tabs, and `build_rop_page_layout` dispatch;
- `/api/rop/dashboard` extended with `latest_selection`, `thread_summary`, `threads`, `ai_assist_summary`, `ai_assist_events` — all present in result dict and populated via helpers;
- RU labels added in `locale.py` for all new UI-6 sections (42 new EN labels + 42 RU translations);
- `_build_rop_threads_layout` and `_build_rop_ai_assist_layout` render BeeUI `kpi_grid`, `state_grid`, `status_table` blocks;
- Old runs without It30 artifacts render warnings/empty states — not crashes;
- Malformed It30 artifacts produce warnings (`_read_json` returns `None`, warnings added, empty sections render);
- Tests: 14 new tests in `TestUi6It30` class covering full It30 fixture, API fields, tab routes, RU locale, old runs, malformed artifacts, allowlist, no GET mutation, no secrets/raw content;
- Route/API smoke: `uv run python config/start.py routes` passes, 30 routes registered;
- Full `pytest -q`: 572 passed (was 558 after UI-5);
- No secrets/raw content exposure confirmed by test `test_no_secrets_in_html_it30` and `test_no_raw_eml_in_it30_html`;
- `pyproject.toml.version` unchanged;
- `beeagent-rop` not changed;
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

Эти данные уже нельзя безопасно показывать по private/customer link без auth boundary.

Удаление legacy web важно, но это cleanup. Для MVP приоритет выше у customer-safe/private access:

```text
UI-7 auth boundary
→ UI-8 remove legacy web
→ UI-9 attachment-aware dashboard
→ UI-10 Bitrix reconciliation dashboard
```

Главное правило сохраняется:

```text
BeeUI renders and owns generic auth/session primitives.
BeeAgent owns product config, policy and route integration.
beeagent-rop remains domain-only.
```

Эта итерация реализуется в `beeagent`, но не должна дублировать BeeUI auth internals. BeeAgent должен использовать существующий BeeUI auth/session layer. Если нужного generic BeeUI hook нет, нужно остановиться и явно зафиксировать BeeUI prerequisite, а не писать собственную session/cookie реализацию в BeeAgent.

#### Depends on

- UI-6 — Expose latest-N, threads, AI assist, RU labels, operator recommendations;
- BeeUI Iteration 13 — Auth/session/CSRF boundary;
- BeeUI Iteration 13.7 — Locale-aware shell labels and query-preserving navigation;
- existing BeeUI embedded app integration in `src/beeagent_module/interfaces/ui/app.py`.

#### Change level

```text
security-sensitive
```

Причина:

- auth/session boundary;
- role/principal config;
- secrets through environment variables;
- HTML/API route protection;
- signed session/cookie behavior delegated to BeeUI;
- artifact/API exposure changes from public-local to authenticated mode;
- customer/private deployment readiness.

#### Scope

**Включено:**

- добавить config-driven BeeAgent web auth policy в `config/settings.yml`:

```yaml
web:
  host: "127.0.0.1"
  port: 8000
  open_browser: true
  auth:
    enabled: false
    mode: beeui_session
    session_secret_env: BEEAGENT_WEB_SESSION_SECRET
    principals:
      - id: admin_1
        username: admin1
        role: admin
        token_env: BEEAGENT_WEB_ADMIN1_TOKEN
      - id: admin_2
        username: admin2
        role: admin
        token_env: BEEAGENT_WEB_ADMIN2_TOKEN
```

- config stores only:
  - auth mode;
  - role/principal metadata;
  - env variable names.

- env stores secrets only:
  - `BEEAGENT_WEB_SESSION_SECRET`;
  - `BEEAGENT_WEB_ADMIN1_TOKEN`;
  - `BEEAGENT_WEB_ADMIN2_TOKEN`.

- validate auth config fail-fast when `web.auth.enabled: true`:
  - `mode` is supported;
  - `session_secret_env` is present;
  - session secret env value exists and is non-empty;
  - `principals[]` is non-empty;
  - each principal has safe `id`;
  - each principal has safe `username`;
  - each principal has allowed `role`;
  - each principal has `token_env`;
  - each token env value exists and is non-empty;
  - duplicate usernames/ids are rejected;
  - secret values are not logged.

- integrate BeeAgent app composition with BeeUI auth/session layer:
  - pass auth config/policy to BeeUI if supported;
  - protect BeeAgent HTML routes when enabled;
  - protect BeeAgent read-only API routes when enabled;
  - keep `/health` public but minimal/sanitized;
  - keep static assets public;
  - keep login/logout/auth helper routes controlled by BeeUI.

- protected HTML routes when auth enabled:

```text
/
 /rop
 /runs
 /runs/{run_id}
 /runs/{run_id}/artifacts
 /runs/{run_id}/artifacts/{artifact_id}
 /modules
```

- protected API routes when auth enabled:

```text
/api/dashboard
/api/rop/dashboard
/api/runs
/api/runs/{run_id}
/api/runs/{run_id}/artifacts
/api/runs/{run_id}/artifacts/{artifact_id}
/api/modules
```

- support roles:

```text
viewer
operator
admin
```

- UI-7 remains read-only:
  - all authenticated roles can view read-only routes;
  - `admin` is reserved for future config/admin/actions;
  - no POST/action/config apply is added in this iteration.

- unauthenticated HTML route behavior:
  - redirect to BeeUI login page or render BeeUI unauthenticated page, depending on existing BeeUI contract.

- unauthenticated API route behavior:
  - return `401` safe JSON envelope;
  - no internal exception details.

- preserve locale/navigation behavior:
  - `?lang=ru` continues to work after login/session;
  - query-preserving tab links remain safe.

- preserve read-only/security boundary:
  - no GET mutation;
  - no POST routes;
  - no web-triggered ROP run;
  - no mailbox calls;
  - no CRM/Bitrix calls;
  - no module/capability execution;
  - no AI provider calls;
  - no raw `.eml`;
  - no raw attachment content;
  - no arbitrary storage browsing;
  - no secrets in HTML/API/logs/artifacts.

- update tests:
  - auth disabled keeps current local behavior;
  - auth enabled without session secret fails fast;
  - auth enabled without principal token fails fast;
  - duplicate principals fail fast;
  - invalid role fails fast;
  - unauthenticated HTML protected route is blocked;
  - unauthenticated API protected route returns `401`;
  - authenticated admin can access `/rop`;
  - authenticated admin can access `/api/rop/dashboard`;
  - `/health` remains public and sanitized;
  - static assets remain accessible;
  - no secrets in HTML/API/logs;
  - no GET mutation.

- update docs:
  - `docs/product/ui_roadmap.md`;
  - `docs/WEB_UI.md`;
  - `README.ru.md`;
  - `docs/DEV_GUIDE.md`;
  - `docs/SECURITY.md` if auth deployment/security notes materially change.

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
- ROP business logic changes;
- dependency changes unless existing BeeUI auth API requires none.

#### Deliverable

BeeAgent Web Console can run in two explicit modes:

```text
web.auth.enabled: false
  → local/dev read-only mode, current behavior preserved

web.auth.enabled: true
  → BeeUI-backed login/session boundary protects BeeAgent HTML/API routes
```

Two admin users can be configured without storing secrets in YAML:

```yaml
principals:
  - id: admin_1
    username: admin1
    role: admin
    token_env: BEEAGENT_WEB_ADMIN1_TOKEN
  - id: admin_2
    username: admin2
    role: admin
    token_env: BEEAGENT_WEB_ADMIN2_TOKEN
```

Real secrets live only in environment variables.

#### Expected config/env behavior

`config/settings.yml`:

```yaml
web:
  auth:
    enabled: true
    mode: beeui_session
    session_secret_env: BEEAGENT_WEB_SESSION_SECRET
    principals:
      - id: admin_1
        username: admin1
        role: admin
        token_env: BEEAGENT_WEB_ADMIN1_TOKEN
      - id: admin_2
        username: admin2
        role: admin
        token_env: BEEAGENT_WEB_ADMIN2_TOKEN
```

`.env` example:

```text
BEEAGENT_WEB_SESSION_SECRET=<long-random-secret>
BEEAGENT_WEB_ADMIN1_TOKEN=<long-random-token-1>
BEEAGENT_WEB_ADMIN2_TOKEN=<long-random-token-2>
```

No token/session secret values may appear in:

```text
HTML
API responses
logs/app.log
storage/*

Real secrets live only in environment variables.

docs examples with real values
```

#### Expected route behavior

Auth disabled:

```text
GET /rop
→ 200
```

Auth enabled, unauthenticated:

```text
GET /rop
→ 302 to login or 401 unauthenticated page, depending on BeeUI contract

GET /api/rop/dashboard
→ 401 JSON envelope
```

Auth enabled, authenticated admin:

```text
GET /rop
→ 200

GET /api/rop/dashboard
→ 200
```

Public minimal routes:

```text
GET /health
→ 200 sanitized health response

GET /static/...
→ 200
```

#### Checks

- `uv run pytest -q`;
- targeted BeeUI/BeeAgent auth integration tests;
- targeted settings validation tests;
- `uv run python config/start.py routes`;

Smoke:

```text
/health
/
 /rop
 /rop?lang=ru
 /rop?tab=threads&lang=ru
 /runs
 /modules
 /api/rop/dashboard
 /runs/<run_id>/artifacts/mailbox_selection_json
```

Auth scenarios:

```text
auth disabled
auth enabled with missing session secret
auth enabled with missing admin token
auth enabled with duplicate principal id
auth enabled with duplicate username
auth enabled with invalid role
unauthenticated HTML protected route
unauthenticated API protected route
authenticated admin HTML route
authenticated admin API route
```

Security/static checks:

```bash
rg -n "BEEAGENT_WEB_SESSION_SECRET|BEEAGENT_WEB_ADMIN1_TOKEN|BEEAGENT_WEB_ADMIN2_TOKEN" logs storage || true
rg -n "token|secret|password" logs/app.log storage/interfaces storage/runs || true
rg -n "POST|delete|archive|mark-as-read|reply|write-back" src/beeagent_module/interfaces/ui tests || true
rg -n "beeagent_rop\.(domain|services|cases)" src/beeagent_module || true
git diff -- pyproject.toml uv.lock
```

SAST mindset review required.

SCA is not required unless dependencies change.

DAST-style route misuse checks required for protected HTML/API routes, artifact routes, `lang`, `tab`, and `run_id` query params.

#### DoD

- BeeAgent has explicit `web.auth` config contract.
- Auth-disabled local/dev mode preserves current behavior.
- Auth-enabled mode fails fast when required env secrets are missing.
- Auth-enabled mode protects BeeAgent HTML routes.
- Auth-enabled mode protects BeeAgent read-only API routes.
- `/health` remains public and sanitized.
- Static assets remain accessible.
- Two admin principals can be configured via env-backed tokens.
- Secrets are never stored in YAML.
- Secrets do not appear in HTML/API/logs/artifacts.
- BeeAgent does not implement its own session/cookie/security primitives when BeeUI provides them.
- No POST/operator/config/action routes are added.
- No mailbox/CRM/Bitrix/module/capability/AI execution is added.
- `beeagent-rop` is unchanged.
- `pyproject.toml.version` is unchanged.
- Tests and docs are updated.

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

По 100-run acceptance classifier/AI этап достаточно стабилен:

```text
loaded=100
normalized=100
classified=100
failed=0
ai_adjudicator eligible=29
ai_adjudicator used=29
ai_adjudicator degraded=21
run status=ok
```

Дальше не нужно возвращаться в classifier loop. Нужно сделать operator-facing слой:

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

* UI-7 — BeeUI-backed auth boundary for BeeAgent console;
* BeeAgent ROP AI adjudicator artifacts:

  * `rop_ai_adjudicator_requests.json`;
  * `rop_ai_adjudicator_decisions.json`;
  * `rop_ai_adjudicator_results.json`;
* existing ROP artifacts:

  * `classified_events.json`;
  * `operator_summary.json`;
  * `rop_current_state.json`;
  * `rop_recommendations.json`, if already generated;
* existing Bitrix widget config:

  * `config/settings.yml` → `bitrix.widget`.

#### Change level

```text
security-sensitive
```

Причина:

* меняется operator-visible read-model;
* добавляется/нормализуется artifact contract;
* расширяется UI/API/widget payload;
* используются email-derived, AI-derived and recommendation-derived данные;
* Bitrix widget boundary должен оставаться token-protected/read-only;
* нужно подтвердить отсутствие raw email, attachment content, secrets, provider tokens and CRM write-back.

SCA не требуется, если зависимости не меняются.

#### Scope

**Включено:**

* добавить current AI adjudicator artifacts в ROP artifact allowlist:

```text
rop_ai_adjudicator_requests_json
rop_ai_adjudicator_decisions_json
rop_ai_adjudicator_results_json
```

mapping:

```text
rop_ai_adjudicator_requests_json  -> rop_ai_adjudicator_requests.json
rop_ai_adjudicator_decisions_json -> rop_ai_adjudicator_decisions.json
rop_ai_adjudicator_results_json   -> rop_ai_adjudicator_results.json
```

* сделать `rop_ai_adjudicator_results.json` current source of truth для AI tab/read-model;
* legacy `rop_ai_assist_*` оставить только как legacy evidence/fallback;
* исправить AI tab:

  * не показывать “AI assistant not used”, если `rop_ai_adjudicator_results.json` существует и содержит результаты;
  * показывать adjudicator summary, status counts, model counts and per-event decisions;
* исправить AI counters в read-model/API:

  * `ai_adjudicator_eligible`;
  * `ai_adjudicator_used`;
  * `ai_adjudicator_ok`;
  * `ai_adjudicator_degraded`;
  * `ai_adjudicator_low_confidence_preserve`;
  * `ai_adjudicator_manual_review_degrade`;
  * `ai_adjudicator_errors`;
* добавить normalized final decision projection для каждого classified event:

```text
final_case_type
final_case_subtype
final_queue
final_action
final_decision_source
final_confidence
needs_attention
attention_reason
automation_allowed
bitrix_write_allowed
```

* для MVP всегда выставлять:

```text
bitrix_write_allowed = false
```

* `automation_allowed` разрешает только внутреннюю routing/display автоматизацию, не CRM/mailbox mutations;
* низкая уверенность AI не должна превращаться в ручную классификацию РОПом:

  * сохранять финальную очередь из AI или deterministic/fallback policy;
  * выставлять `needs_attention=true`;
  * объяснять причину в `attention_reason`;
* `manual_review` использовать только как technical exception/fallback, если нет безопасной финальной очереди;
* добавить artifact-level projection, если это не создаёт дублирование source of truth:

```text
storage/runs/<run_id>/rop_final_decisions.json
```

* структура `rop_final_decisions.json`:

```json
{
  "run_id": "mvp-ai-acceptance-final-100",
  "policy_version": "rop_final_decision_v1",
  "source_artifacts": [
    "classified_events.json",
    "rop_ai_adjudicator_results.json"
  ],
  "counters": {
    "total": 100,
    "ai_adjudicator_used": 29,
    "needs_attention": 0,
    "bitrix_write_allowed": 0
  },
  "decisions": []
}
```

* если `rop_final_decisions.json` отсутствует у старого run, UI может построить projection on read из existing artifacts и показать warning;
* auto-generate/update `rop_recommendations.json` after ROP run, если существующий recommendations builder уже есть;
* recommendations tab должен использовать actual recommendation artifact/read-model, а не показывать “run rop recommendations manually” для свежего run;
* обновить queue tab:

  * показывать `final_queue`, `final_action`, `final_decision_source`, `final_confidence`, `needs_attention`, `bitrix_status`;
  * “Open” должен вести на event detail:

```text
/rop/events/{event_id}?run_id=<run_id>&lang=ru
```

а не на `classified_events_json`;

* обновить event detail:

  * показать final decision;
  * показать deterministic before AI;
  * показать AI adjudicator decision/reason/status;
  * показать attention flags;
  * показать safe recommendations;
  * показать evidence links;
* обновить overview metrics:

  * processed;
  * AI decided;
  * new leads;
  * tenders;
  * logistics;
  * finance;
  * ignored;
  * needs attention;
  * errors;
* убрать/переименовать misleading counter “168 actions required” для 100-email run;
* обновить Bitrix widget payload routes так, чтобы они читали тот же final decision/recommendations read-model:

  * `/api/bitrix/rop/widget`;
  * `/api/bitrix/rop/widget/events`;
  * `/api/bitrix/rop/widget/events/{event_id}`;
* widget payload должен оставаться:

  * read-only;
  * token-protected through existing `bitrix.widget.token_env`;
  * без Bitrix REST calls;
  * без CRM/mailbox/module/capability mutations;
* widget payload должен включать:

  * `final_queue`;
  * `final_action`;
  * `final_decision_source`;
  * `final_confidence`;
  * `needs_attention`;
  * `attention_reason`;
  * `recommended_action`;
  * `target_bitrix_category`;
  * `safe_to_execute`;
  * `requires_human_confirmation`;
  * `bitrix_write_allowed`;
  * `detail_url`;
* `safe_to_execute` в текущем scope должен оставаться `false` для non-ignore/write-like actions;
* `requires_human_confirmation` должен оставаться `true` для потенциальных CRM/write-like actions;
* update docs:

  * `docs/product/ui_roadmap.md`;
  * `docs/WEB_UI.md`;
  * `README.ru.md` / `docs/DEV_GUIDE.md`, если меняется usage/smoke flow.

**Не включено:**

* изменения в `beeagent-rop`;
* новые deterministic classifier rules;
* изменение OpenAI prompt без прямого read-model bug;
* 300-run acceptance;
* CRM/Bitrix write-back;
* `crm.item.add`;
* `crm.item.update`;
* `crm.timeline.comment.add`;
* mailbox delete/archive/reply/mark-as-read;
* web-triggered ROP run;
* widget-triggered ROP run;
* operator POST actions;
* auth/RBAC changes;
* Bitrix placement install;
* `placement.bind`;
* OAuth/OIDC Bitrix app lifecycle;
* separate frontend;
* dependency changes;
* удаление legacy `src/beeagent_module/web`.

#### Deliverable

После итерации Web UI и Bitrix widget payload используют одну финальную модель решений.

Оператор видит:

```text
1. Что BeeAgent решил по каждому письму.
2. Кто принял решение: deterministic или AI adjudicator.
3. Почему решение принято.
4. Какая финальная очередь.
5. Какое рекомендованное действие.
6. Где нужна повышенная внимательность.
7. Почему Bitrix write-back пока запрещён.
8. Какие artifacts подтверждают вывод.
```

Bitrix widget получает тот же payload без собственной бизнес-логики.

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

If the run path is updated in scope:

```text
storage/runs/<run_id>/rop_final_decisions.json
storage/runs/<run_id>/rop_recommendations.json
```

`rop_recommendations.json` may be reused if existing implementation already writes it.

No raw email, raw attachment content, env values, provider tokens, Bitrix webhook URL or mailbox password may be written to these artifacts.

#### Expected `/api/rop/dashboard` payload extension

```json
{
  "ai_adjudicator_summary": {
    "evidence_available": true,
    "eligible_count": 29,
    "used_count": 29,
    "ok_count": 8,
    "degraded_count": 21,
    "low_confidence_preserve_count": 0,
    "manual_review_degrade_count": 21,
    "error_count": 0,
    "status_counts": {},
    "model_counts": {}
  },
  "final_decision_summary": {
    "total": 100,
    "deterministic_count": 71,
    "ai_adjudicator_count": 29,
    "fallback_policy_count": 0,
    "needs_attention_count": 21,
    "bitrix_write_allowed_count": 0
  },
  "final_decisions": []
}
```

Existing UI-6 fields must remain available where practical.

#### Expected HTML behavior

`GET /rop?tab=ai_assist&lang=ru` shows current AI adjudicator evidence.

`GET /rop?tab=queue&lang=ru` shows final decision queue, not artifact links.

`GET /rop/events/{event_id}?run_id=<run_id>&lang=ru` shows event detail with final decision, deterministic evidence, AI adjudicator evidence and recommendations.

`GET /rop?tab=recommendations&lang=ru` shows generated recommendations for the selected run when artifact exists.

#### Expected Bitrix widget API behavior

`GET /api/bitrix/rop/widget` returns read-only final decision/recommendation summary.

`GET /api/bitrix/rop/widget/events` returns bounded event list for widget.

`GET /api/bitrix/rop/widget/events/{event_id}` returns event detail payload.

Routes remain token-protected through `bitrix.widget.token_env`.

No Bitrix REST call is made from these routes.

#### Checks

* `uv run pytest -q`;
* targeted ROP final decision tests;
* targeted AI adjudicator read-model tests;
* targeted recommendations tests;
* targeted widget payload tests;
* `uv run python config/start.py routes`;

Route/API smoke:

```text
/rop
/rop?lang=ru
/rop?tab=queue&lang=ru
/rop?tab=ai_assist&lang=ru
/rop?tab=recommendations&lang=ru
/rop/events/<event_id>?run_id=<run_id>&lang=ru
/api/rop/dashboard?run_id=<run_id>
/api/rop/events/<event_id>?run_id=<run_id>
/api/bitrix/rop/widget
/api/bitrix/rop/widget/events
/api/bitrix/rop/widget/events/<event_id>
```

Security/static checks:

```bash
rg -n "raw_eml|raw_message|attachment_content|content_bytes|payload_bytes|message/rfc822" src/beeagent_module/interfaces/ui tests || true
rg -n "BEEAGENT_WEB_|OPENAI_API_KEY|CUSTOM_AI_API_KEY|BITRIX_WEBHOOK|ROP_MAILBOX_PASSWORD|password|secret|token" storage/runs storage/interfaces logs || true
rg -n "crm.item.add|crm.item.update|timeline.comment|mailbox delete|archive|mark-as-read|reply|write-back" src tests || true
rg -n "beeagent_rop\.(domain|services|cases)" src/beeagent_module || true
git diff -- pyproject.toml uv.lock
```

#### DoD

* ROP AI tab uses `rop_ai_adjudicator_*` as current source of truth.
* Legacy `rop_ai_assist_*` is not primary AI status.
* ROP dashboard exposes normalized final decision fields.
* Queue tab links to event detail, not artifact viewer.
* Recommendations tab is populated from run artifact/read-model when available.
* Fresh ROP runs generate or update recommendation/final-decision artifacts if runtime path is in scope.
* Bitrix widget API uses the same final decision/recommendations read-model.
* Widget routes remain read-only and token-protected.
* `bitrix_write_allowed` is always false for MVP.
* No CRM/Bitrix/mailbox/module/capability write action is added.
* No raw `.eml`, raw attachment content, provider secret, env value, Bitrix webhook or mailbox password appears in HTML/API/logs/artifacts.
* Missing/malformed adjudicator/recommendation artifacts produce warnings, not crashes.
* `beeagent-rop` unchanged.
* Dependencies unchanged unless explicitly justified.
* `pyproject.toml.version` unchanged.
* Tests and docs updated.

#### Status notes

- AI adjudicator artifacts allowlisted (`rop_ai_adjudicator_requests_json`, `rop_ai_adjudicator_decisions_json`, `rop_ai_adjudicator_results_json`);
- `rop_final_decisions.json` artifact-first read-model with computed read-only fallback;
- AI Adjudicator summary and Final Decisions summary in `/rop?tab=ai_assist`;
- Event detail page `/rop/events/{event_id}` shows AI Adjudicator and Final Decision sections;
- `/api/rop/dashboard` exposes `ai_adjudicator_summary`, nested `final_decisions` and compatibility alias `final_decision_summary`;
- Bitrix widget API includes bounded `final_decisions` with summary recalculated by `max_items`;
- Final decision policy v1 implemented: AI ok / low_confidence_preserve / manual_review_degrade / deterministic / fallback_policy;
- `bitrix_write_allowed` always `false` for MVP.

### Итерация UI-8.1 — Web Console UX increment: Queue, filters, sort, pagination, locale, charts, Event Detail

**Статус:** IN PROGRESS

#### Goal

Завершить Web Console UX increment: реализовать полноценный Queue tab с серверными фильтрами, multi-select dropdown, сортировкой, пагинацией, унифицированным URL/query builder, unified adapter-level contract для HTML/API parsing и валидации, исправлением date sorting, устранением дублей локали, charts и полным Event Detail page.

#### Почему это нужно

UI-8 реализовал final decision read-model, но Queue tab и общий UX Web Console требуют доработки для эффективной операторской работы:
- URL/query параметры формируются вручную без единого builder;
- HTML/API parsing и валидация размазаны между adapter и read-model;
- page number не всегда берётся из canonical `paginate_items()`;
- date sorting ставит missing/malformed даты в начало;
- RU locale содержит дублирующиеся ключи `Period` и `Sources`;
- нет regression-тестов на специальные символы, round-trip, HTML/API parity, invalid ввод.

#### Depends on

- UI-8 — ROP final decision read-model + recommendations + Bitrix widget payload MVP;
- review/pr152 branch changes.

#### Change level

```text
security-sensitive
```

Причина:

- URL query builder влияет на формирование всех HTML ссылок в Queue/Overview/Event Detail;
- adapter-level contract меняет поведение парсинга и валидации query-параметров;
- sorting logic меняет порядок отображения операторских данных;
- locale изменения влияют на отображение RU-интерфейса;
- добавляются regression-тесты на invalid/special-char input;
- полный набор security checks на точном committed tree.

#### Scope

**Включено:**

- создать единый URL/query builder через `urllib.parse.urlencode`;
- перевести registry dependency BeeUI на `beeui>=0.22,<0.30`, удалить local editable source и подтвердить transition обязательными frozen/SCA checks;
- использовать его во всех ROP filter/column/sort/pagination/reset/period/KPI links;
- сохранить явный `run_id`, `tab`, `period`, `lang` и канонический filter state в каждом URL;
- объединить HTML/API parsing и валидацию в одном adapter-level contract;
- валидировать queue, columns, dropdown state, booleans, dates, enums, page/page_size и атомарную пару sort/order;
- невалидный ввод не должен молча расширять выборку;
- использовать каноническую страницу из `paginate_items()` во всех rows, labels, links и API metadata;
- исправить date sorting: missing/malformed dates всегда после валидных при asc и desc;
- убрать дубли `Period` и `Sources` в RU locale;
- ввести отдельные semantic keys для Latest Selection;
- добавить regression tests: special-character query round-trip, сохранение выбранного run_id, HTML/API parity, unknown queue, invalid columns/dropdowns/sort/order, page=-1/non-int/999, mixed valid/missing dates и locale contexts;
- синхронизировать `docs/WEB_UI.md`, `README.ru.md` и `docs/DEV_GUIDE.md` с фактическими filters/sort/pagination/API semantics, attention cap и additive contracts;
- классифицировать итог как security-sensitive и выполнить полный набор проверок на точном committed tree.

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

Web Console Queue tab с единым URL builder, adapter-level validation, canonical pagination, исправленным date sorting, корректной RU локалью, полным набором regression тестов и синхронизированной документацией.

#### Checks

- frozen sync/tree после registry dependency transition;
- full pytest suite;
- targeted regression tests;
- routes smoke;
- web smoke (`./start.sh web`);
- required SCA для `beeui>=0.22,<0.30` registry dependency;
- SAST / manual review;
- DAST / manual query abuse;
- logs/artifacts/no-secret/no-mutation.

#### DoD

- Единый URL builder через `urllib.parse.urlencode` используется во всех ROP links;
- adapter-level contract валидирует все query-параметры до передачи в read_model;
- canonical `paginate_items()` page используется в rows, labels, pagination links и API metadata;
- missing/malformed dates всегда после валидных при asc и desc;
- RU locale не содержит дубли `Period` и `Sources`;
- semantic keys для Latest Selection изолированы от общих Period/Sources;
- regression тесты покрывают special chars, run_id round-trip, HTML/API parity, invalid ввод;
- документация синхронизирована;
- security checks выполнены на точном committed tree.

### Итерация UI-9 — Remove legacy BeeAgent web after BeeUI MVP parity

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

### Итерация UI-10 — Attachment-aware ROP dashboard

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

### Итерация UI-11 — ROP Bitrix reconciliation dashboard

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

### Итерация UI-12 — Stable BeeAgent Web API contract v1

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

### Итерация UI-13 — Web auth boundary v0

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

### Итерация UI-14 — Operator Web Control Panel v0

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

#### Deliverable

Operator can use Web Control Panel for bounded BeeAgent actions without hidden execution paths.

#### Checks

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

### Итерация UI-15 — Support/Admin diagnostics v0

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

### Итерация UI-16 — SQLAdmin evaluation for DB-backed admin only

**Статус:** DEFERRED

#### Goal

Оценить SQLAdmin only when BeeAgent introduces DB-backed entities such as users, tenants, projects, saved presets or review decisions.

#### Scope

Deferred until DB-backed models exist.

#### Not for immediate MVP

Current runtime source of truth is file-based artifacts and config, so SQLAdmin is not useful for current ROP dashboard/control panel.

## Итерация UI-16 — Standalone BeeUI / separate frontend readiness

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
