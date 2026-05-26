# UI ROADMAP — beeagent (FastAPI / Tabler operator console track)

## Purpose

Этот документ фиксирует отдельный пошаговый план развития UI / Operator Web / Control Panel внутри `beeagent`.

UI roadmap нужен как lightweight planning-артефакт для operator/product layer:

- не размывает `docs/ROADMAP.md` деталями web/frontend задач;
- фиксирует порядок развития BeeAgent Web Console;
- помогает связывать UI Issue → Code → Tests → Artifacts → PR → Merge;
- отделяет dashboard, metrics, auth, API, customer-safe access и bounded controls от core runtime roadmap;
- фиксирует, что BeeAgent core остаётся source of truth, а UI остаётся operator layer.

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

UI в BeeAgent становится отдельным product/operator layer:

- read-only Operator Web Shell уже появился в It22;
- ROP dashboard уже показывает artifacts без ручного чтения JSON/TSV;
- дальше нужны FastAPI backend API, Tabler UI, auth, customer-safe access, control panel, bounded actions;
- UI должен быть пригоден не только для `beeagent-rop`, но и для будущих `beescan`, `merch`, а также потенциально для общего `BeeConsole`;
- эти задачи важны, но не должны засорять core `docs/ROADMAP.md`.

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

## Vision

| Block                   | Statement                                                                                                                                            |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Track identity**      | UI track развивается как operator-facing product layer поверх BeeAgent core, artifacts и module outputs, а не как второй runtime или второй backend. |
| **Primary objective**   | Цель UI — дать оператору и заказчику понятную консоль: что пришло, что важно, что degraded, какие действия возможны и где evidence.                  |
| **Backend rule**        | Backend UI layer должен быть FastAPI-based: routes, JSON API, auth, bounded action endpoints.                                                        |
| **Frontend rule**       | Frontend v1 — Jinja2 + Tabler. Separate React/Tabler или Reflex допускаются позже только поверх stable `/api/*`.                                     |
| **Source of truth**     | UI читает `config/settings.yml` и existing artifacts из `storage/`. UI не становится source of truth для runtime/business state.                     |
| **KISS rule**           | Пока backend contracts меняются, используем FastAPI + Jinja2 + Tabler. Отдельный frontend откладывается до стабилизации API.                         |
| **Safety rule**         | UI read-only по умолчанию. Любые write/control actions проходят через explicit backend action API, validation, confirmation и audit artifacts.       |
| **Artifact rule**       | Все значения в UI должны быть traceable к source artifacts. Missing/partial/corrupted data отображается явно.                                        |
| **Module rule**         | UI не содержит ROP business rules. Domain logic остаётся в `beeagent-rop`; UI показывает outputs/artifacts.                                          |
| **Customer rule**       | Customer-facing link возможен только после auth/session/security hardening. До этого web surface local/private only.                                 |
| **Future console rule** | Future `BeeConsole` может быть React + Tabler client over stable BeeAgent/BeeCap/BeeScan APIs, но не должен создавать второй backend truth.          |

## Architecture direction

Целевая архитектура UI:

```text
Browser
  ↓
BeeAgent FastAPI Web
  ├─ HTML pages: Jinja2 + Tabler
  ├─ JSON API: /api/*
  ├─ Auth/session layer
  ├─ Bounded action routes
  └─ Read-model services
        ↓
BeeAgent core/services/cases
        ↓
storage/runs/*
storage/interfaces/*
config/settings.yml
modules.registry
beeagent-rop outputs
```

Frontend v1:

```text
FastAPI + Jinja2 + Tabler
```

Frontend v2, только после стабилизации API:

```text
React + Tabler over /api/*
```

Admin DB layer, только когда появятся DB-backed entities:

```text
SQLAdmin mounted under /admin
```

Не использовать как core foundation:

```text
Reflex as BeeAgent core
FastUI as main UI foundation
fastapi-admin as main admin platform
```

## Development principles

Каждая UI-итерация должна:

- оставаться внутри одного focused scope;
- работать через canonical BeeAgent web surface;
- использовать existing artifacts/read-models как source of truth;
- не вызывать mailbox/CRM/module/capability execution из GET routes;
- не мутировать `storage/`, config или runtime state без явно заявленного bounded action flow;
- сохранять read-only behavior для dashboard/run/detail/artifact GET routes;
- использовать `config/settings.yml` как source of truth для UI config;
- валидировать новые mandatory config keys fail-fast;
- создавать audit artifacts для bounded write/control actions;
- не раскрывать secrets в HTML/API/logs/artifacts;
- graceful-handle missing/empty/partial/corrupted artifacts;
- закрываться через Issue / PR / tests / artifacts.

Для BeeAgent UI это означает:

- сначала read-only visibility;
- затем stable backend API;
- затем auth;
- затем bounded operator controls;
- затем optional separate frontend;
- не делать React/Reflex до стабилизации backend API;
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
- bounded write/control paths создают audit artifacts;
- новые mandatory config keys читаются из `config/settings.yml`;
- новые mandatory config keys валидируются в `src/beeagent_module/core/settings.py`;
- missing/partial/corrupted artifacts handled gracefully;
- source artifacts явно отражены в payload/view;
- tests и smoke checks выполнены;
- required quality/security checks выполнены по change level;
- `docs/WEB_UI.md` обновлён, если изменился implemented route/API contract;
- `README.ru.md` / `docs/DEV_GUIDE.md` обновлены, если изменился способ запуска/usage.

## Change levels for UI track

UI track использует те же change levels:

- **low-risk** — docs, HTML copy, harmless visual cleanup, tests without route/API/config/runtime change;
- **runtime-risk** — dashboard/read-model/API changes, artifact parsing, route behavior, template rendering, support/admin diagnostics;
- **security-sensitive** — auth, config mutation, operator controls, action API, runtime control artifacts, file/path handling, new dependencies, external exposure.

Правило:

- read-only dashboards обычно `runtime-risk`;
- auth/control/action/config apply/file/path-sensitive changes — `security-sensitive`;
- docs-only и copy/style-only changes — `low-risk`.

## Baseline already achieved

К началу этого UI track baseline считается таким:

- BeeAgent имеет read-only web shell после It22;
- route `/runs` показывает runs;
- route `/runs/<run_id>` показывает run overview;
- route `/runs/<run_id>/rop` показывает ROP dashboard;
- route `/modules` показывает module diagnostics, если artifact доступен;
- web routes читают existing artifacts;
- web routes не запускают ROP run;
- web routes не делают CRM/mailbox actions;
- raw `.eml` и attachment content не должны рендериться;
- path traversal должен блокироваться;
- `beeagent-rop` не меняется из UI задач.

Это baseline. Дальше нужен не “ещё один web”, а controlled evolution toward BeeAgent Web Console.

---

# Этап 0 — Planning and architecture decision

## Итерация UI-0 — UI roadmap and FastAPI/Tabler decision

**Статус:** DONE

### Goal

Зафиксировать UI direction для BeeAgent: FastAPI backend, Jinja2 + Tabler frontend v1, stable `/api/*` как будущий контракт для отдельного frontend.

### Scope

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

### Deliverable

Есть отдельный UI roadmap и принятое архитектурное решение по Web Console.

### Checks

- docs review;
- roadmap consistency review;
- no runtime changes;
- no tests required unless docs tooling exists.

### DoD

- `docs/product/ui_roadmap.md` создан;
- основной `docs/ROADMAP.md` не дублирует UI-track детали;
- UI direction понятен для следующих issues.

---

# Этап 1 — FastAPI + Tabler web foundation

## Итерация UI-1 — FastAPI + Tabler Web Console foundation v0

**Статус:** DONE

### Goal

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

### Scope

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

### Deliverable

`./start.sh web` запускает FastAPI + Jinja2 + Tabler read-only Web Console поверх existing artifacts.

### Change level

`runtime-risk`.

Escalate to `security-sensitive` only if implementation changes file/path semantics, dependency surface beyond FastAPI/Uvicorn/TestClient, auth, secrets, POST actions or external exposure.

### DoD

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

# Этап 2 — ROP operator dashboards

## Итерация UI-2 — ROP multi-source dashboard v1

**Статус:** PLANNED

### Goal

Расширить ROP dashboard под multi-source flow после BeeAgent It24: оператор должен видеть не только один `hotline_mailbox`, а source-aware картину по всем источникам текущего run.

### Depends on

- `BeeAgent It24 — Multi-source mailbox run v0`

### Scope

**Включено:**

- ROP dashboard grouped by source:
  - source_id;
  - source_type;
  - source_role;
  - source_display_name;
  - client_id;
  - mailbox_folder;
  - fetched_count;
  - loaded_count;
  - malformed_count;
  - degraded reason;

- aggregate KPI:
  - total fetched;
  - total loaded;
  - total classified;
  - total failed;
  - fallback count;
  - degraded source count;

- source filters:
  - `source_id`;
  - `source_role`;
  - `case_type`;
  - `priority`;
  - `fallback`;
  - `reason_code`;

- source-level artifact links;
- graceful handling:
  - single-source old runs;
  - multi-source new runs;
  - partial source failure;
  - malformed source diagnostics;

- update API contract for ROP dashboard;
- docs update.

**Не включено:**

- web-triggered multi-source run;
- source-aware dedup editing;
- CRM write-back;
- Bitrix reconciliation UI;
- attachment extraction UI;
- auth;
- operator actions.

### Deliverable

ROP dashboard становится готовым к multi-source mailbox ingestion и показывает source-level status/metrics.

### Artifacts

Expected to read artifacts from It24, for example:

- `storage/runs/<run_id>/source_diagnostics.json`;
- `storage/runs/<run_id>/intake_metadata.json`;
- `storage/runs/<run_id>/normalized_events.json`;
- `storage/runs/<run_id>/classified_events.json`;
- `storage/runs/<run_id>/operator_summary.json`;
- `storage/runs/<run_id>/rop_review_table.tsv`.

If It24 introduces per-source diagnostics files, UI must read the implemented contract from `docs/WEB_UI.md` / `docs/ROADMAP.md`.

### Checks

- `uv run pytest -q`;
- single-source compatibility scenario;
- multi-source run scenario;
- one source degraded scenario;
- source filter checks;
- aggregate metrics checks;
- no mutation;
- no mailbox/CRM calls;
- no secrets in HTML/API/logs.

### DoD

- source-aware ROP dashboard works for old and new runs;
- source status is explicit;
- aggregate metrics do not hide degraded sources;
- dashboard remains read-only;
- docs updated.

## Итерация UI-3 — ROP attachment preview dashboard v1

**Статус:** PLANNED

### Goal

После BeeAgent It25 и beeagent-rop It15 показать attachment preview / extraction status в ROP dashboard без raw attachment content leakage.

### Depends on

- `BeeAgent It25 — Attachment extraction v0`
- `beeagent-rop It15 — Attachment preview classification hardening v1`

### Scope

**Включено:**

- show attachment metadata:
  - filename;
  - content_type;
  - size_bytes;
  - extraction_status;
  - preview_available;
  - refusal_reason;

- show bounded preview only if artifact contract explicitly marks it safe;
- show classification reason codes affected by attachment preview;
- warnings for:
  - unsupported attachment;
  - refused attachment;
  - extraction failure;
  - oversized file;

- source artifact links;
- no raw files served;
- no arbitrary attachment download;
- docs update.

**Не включено:**

- OCR UI;
- full document viewer;
- raw attachment content;
- file upload;
- editing classification;
- CRM write-back.

### Deliverable

Оператор видит, какие письма получили attachment-derived context и где extraction/refusal affected classification.

### Checks

- attachment metadata rendering;
- safe preview rendering;
- refused/unsupported/oversized scenario;
- no raw attachment content served;
- no `.eml` served;
- no mutation;
- no external parser calls from UI.

### DoD

- attachment status is visible and safe;
- raw content is not exposed;
- UI remains artifact-only/read-only.

## Итерация UI-4 — ROP Bitrix reconciliation dashboard v1

**Статус:** PLANNED

### Goal

После BeeAgent It26 показать read-only Bitrix reconciliation evidence в ROP dashboard: найден ли lead/deal/contact, есть ли дубль, кто ответственный, какой статус и где требуется ручная проверка.

### Depends on

- `BeeAgent It26 — Bitrix read-only reconciliation v0`

### Scope

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
- Bitrix auth setup UI.

### Deliverable

ROP dashboard показывает CRM-read-only reconciliation поверх artifacts без ручного открытия Bitrix JSON.

### Checks

- matched scenario;
- unmatched scenario;
- duplicate candidate scenario;
- degraded Bitrix connector scenario;
- no CRM calls from UI;
- no mutation;
- no secrets.

### DoD

- Bitrix reconciliation is visible and explainable;
- UI remains read-only;
- source artifacts remain source of truth.

---

# Этап 3 — Stable backend API

## Итерация UI-5 — Stable BeeAgent Web API contract v1

**Статус:** PLANNED

### Goal

Стабилизировать JSON API contract для будущего separate frontend / BeeConsole без реализации React/Reflex frontend.

### Scope

**Включено:**

- freeze API routes v1:
  - `/api/health`;
  - `/api/runs`;
  - `/api/runs/{run_id}`;
  - `/api/rop/runs/{run_id}/dashboard`;
  - `/api/modules`;
  - `/api/sources`;
  - `/api/artifacts/{run_id}/{artifact_name}` or existing safe artifact route;

- stable response envelope:
  - `ok`;
  - `read_only`;
  - `data`;
  - `warnings`;
  - `source_refs`;

- docs examples;
- fixture payloads for frontend development;
- API tests.

**Не включено:**

- React/Reflex frontend;
- auth/RBAC;
- POST actions;
- DB migration;
- web-triggered runs.

### Deliverable

Future frontend can be built against documented `/api/*` without reading filesystem directly.

### Checks

- API shape tests;
- error envelope tests;
- missing/malformed artifact scenarios;
- no mutation;
- no secrets.

### DoD

- API contract is documented;
- HTML and API use compatible read-models;
- no second backend path is introduced.

---

# Этап 4 — Auth and customer-safe access

## Итерация UI-6 — Web auth boundary v0

**Статус:** PLANNED\*\*

### Goal

Добавить минимальную auth boundary для BeeAgent Web Console, чтобы её можно было безопаснее показывать заказчику/оператору по ссылке в private deployment.

### Change level

**security-sensitive**

### Scope

**Включено:**

- config-driven auth:
  - `web.auth.enabled`;
  - `web.auth.mode`;
  - `web.auth.username_env`;
  - `web.auth.password_env`;

- fail-fast validation for mandatory auth config when enabled;
- login/basic/session mode, выбрать минимальный safe вариант;
- logout if session mode;
- no auth secrets in logs/artifacts;
- protect HTML and API routes;
- local/private deployment note;
- tests.

**Не включено:**

- full RBAC;
- OAuth;
- multi-tenant user DB;
- password reset;
- public internet deployment hardening automation;
- action controls.

### Deliverable

Web Console can require auth before showing runs/dashboard/API.

### Checks

- auth disabled scenario;
- auth enabled success;
- auth enabled failure;
- missing env fail-fast/degraded behavior;
- API protected;
- no password leakage;
- no secrets in logs/HTML/API;
- SAST;
- SCA only if dependencies change.

### DoD

- auth boundary is explicit;
- config is source of truth;
- secrets only from env;
- customer-safe private link becomes possible with deployment hardening notes.

---

# Этап 5 — Operator Control Panel

## Итерация UI-7 — Operator Web Control Panel v0

**Статус:** PLANNED

### Goal

Добавить первый bounded operator control panel для BeeAgent ROP flow: оператор видит доступные действия, может запускать safe read-only/draft-only actions через explicit backend action API, а каждое действие создаёт audit artifact.

### Depends on

- UI-1 FastAPI + Tabler foundation;
- UI-5 stable API preferred;
- UI-6 auth preferred before customer-facing usage;
- BeeAgent It24/It25/It26 as backend evidence layers.

### Scope

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
  - `storage/interfaces/operator_actions/<action_id>.json`;

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

### Artifacts

- `storage/interfaces/operator_actions/<action_id>.json`;
- existing run artifacts if action launches ROP flow.

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
- DAST-style route misuse checks if practical.

### DoD

- control panel does not bypass BeeAgent core;
- every action has explicit status and reason;
- every POST action is audited;
- no hidden mailbox/CRM/capability execution;
- unsupported actions are denied, not hidden as available;
- docs updated.

---

# Этап 6 — Admin/support surfaces

## Итерация UI-8 — Support/Admin diagnostics v0

**Статус:** PLANNED

### Goal

Добавить embedded support/admin diagnostics section для чтения audit/config/module/source diagnostics без отдельной heavy admin platform.

### Scope

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

### Deliverable

Internal support can inspect diagnostics and audit trail without browsing `storage/`.

### Checks

- admin route smoke;
- audit listing;
- modules listing;
- sources listing;
- secret redaction;
- no mutation.

### DoD

- admin/support is read-only;
- no second app/backend;
- no secrets exposed.

## Итерация UI-9 — SQLAdmin evaluation for DB-backed admin only

**Статус:** DEFERRED

### Goal

Оценить SQLAdmin only when BeeAgent introduces DB-backed entities such as users, tenants, projects, saved presets or review decisions.

### Scope

Deferred until DB-backed models exist.

### Not for immediate MVP

Current runtime source of truth is file-based artifacts and config, so SQLAdmin is not useful for current ROP dashboard/control panel.

---

# Этап 7 — Future BeeConsole frontend readiness

## Итерация UI-10 — Frontend contract pack v1

**Статус:** DEFERRED

### Goal

Подготовить stable contract pack для будущего separate frontend without implementing frontend.

### Scope

**Включено:**

- documented API routes;
- response examples;
- fixture payloads;
- error envelope examples;
- frontend dev notes.

**Не включено:**

- React implementation;
- Reflex implementation;
- API gateway;
- DB migration;
- second backend.

### Deliverable

Future `BeeConsole` can consume BeeAgent API without filesystem access.

## Итерация UI-11 — BeeConsole frontend prototype v0

**Статус:** DEFERRED

### Goal

Сделать отдельный frontend prototype only after backend API stabilizes.

### Preferred stack

```text
React + Tabler
```

Alternative prototype only:

```text
Reflex over BeeAgent API
```

### Scope

**Включено:**

- consume `/api/*`;
- no direct filesystem access;
- no business logic duplication;
- no runtime execution outside BeeAgent API.

**Не включено:**

- replacing BeeAgent backend;
- moving orchestration into frontend;
- direct connector/provider calls;
- duplicate source of truth.

### DoD

- frontend is replaceable;
- backend API remains canonical;
- no BeeAgent core logic moves to frontend.

---

# Этап 8 — Deferred product/admin platform

## Итерация UI-12 — Product-grade RBAC and multi-user admin v1

**Статус:** DEFERRED

### Goal

Добавить полноценный user/project/role model only when product deployment requires it.

### Not for immediate MVP

Do not build enterprise RBAC before actual deployment/user model is defined.

## Итерация UI-13 — Database-backed UI index v1

**Статус:** DEFERRED

### Goal

Move from filesystem artifact reads to DB-backed UI index only if storage scanning becomes insufficient.

### Not for immediate MVP

`storage/` remains canonical source of truth until scale/evidence says otherwise.

---

## Working rule for issues

Для UI track действует правило:

- одна UI-итерация = один Issue = один PR;
- не смешивать FastAPI migration, auth, dashboard, controls и frontend split в одной задаче;
- сначала read-only visibility;
- затем stable API;
- затем auth;
- затем bounded controls;
- controls require audit artifacts;
- GET/read-model routes must not mutate state;
- mailbox/CRM/module/capability execution from UI is forbidden unless future iteration explicitly adds bounded action path.

---

## Related documents

Этот документ используется вместе с:

- `docs/ROADMAP.md`;
- `docs/WEB_UI.md`;
- `docs/SDLC.md`;
- `docs/SECURITY.md`;
- `docs/DEV_GUIDE.md`;
- `README.ru.md`.
