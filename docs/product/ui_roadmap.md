# UI ROADMAP — beeagent (BeeUI operator console track)

## Purpose

This document records a separate step-by-step development plan for UI / Operator Web / Control Panel inside `beeagent`.

UI roadmap is needed as lightweight planning-artifact for operator/product layer:

- does not leak `docs/ROADMAP.md` with web/frontend task parts;
- Record BeeAgent Web Console transition to BeeUI;
- helps link UI iteration → Issue → Code → Tests → Artifacts → PR → Merge;
- Segregates dashboard, metrics, auth, API, customer-safe access and bounded controls from core runtime roadmap;
- Notes that BeeAgent core remains source of truth, and UI remains interface/operator layer;
- Notes that BeeUI is canonical web framework layer for new web works.

This document does not replace:

- `docs/ROADMAP.md` is the main roadmap to core/runtime/module/capability;
- `docs/SDLC.md` — process / checks / DoD;
- `docs/SECURITY.md` — secure development rules;
- `docs/WEB_UI.md` is the actual implemented web/API contract;
- Issue and PR are specific tasks and verification evidence.

Rule:

- `docs/ROADMAP.md` captures core-level development BeeAgent;
- `docs/product/ui_roadmap.md` captures UI/operator-web track;
- `docs/WEB_UI.md` captures the relevant implemented route/API/UI contract;
- one UI-iteration = one coherent product increment;
- One implementation repository = one Issue = one target worktree/branch = one PR;
- If one UI-iteration requires changes in several repositories, for each repository, a separate Issue and PR is created with the explicit dependency and merge order;
- one UI-iteration must not mix independent product increments.

## Why UI track is separate

UI in BeeAgent is a separate product/operator layer:

- BeeAgent core is responsible for runtime, orchestration, modules, artifacts, config, capability boundary;
- `beeagent-rop` is responsible for ROP domain logic: classification, duplicate/summary/recommendation;
- UI is responsible for operator-visible read-model, dashboards, artifacts, source links and bounded controls later;
- web UI must be suitable not only for `beeagent-rop`, but also for future `beescan`, `merch`, MCP/API/operator surfaces;
- UI- tasks are important, but must not clog core `docs/ROADMAP.md`.

UI track develops separately, but strictly follows the same SDLC-light process:

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

Web UI should be done in `beeagent`, not in `beeagent-rop`.

`beeagent-rop` – domain module. Its role is:

```text
inbound event
→ classification
→ duplicate/summary/recommendation
```

`beeagent` – runtime/orchestration/operator shell. Its role is:

```text
sources
→ artifacts
→ module dispatch
→ operator-visible UI/API
```

BeeUI is therefore integrated into `beeagent`.

`beeagent-rop` must not contain:

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

Old package:

```text
src/beeagent_module/web
```

is legacy/frozen surface after BeeUI cutover.

Rule:

- new web features not to add to `src/beeagent_module/web`;
- BeeUI integration do it through `src/beeagent_module/interfaces/ui`;
- legacy web delete after BeeUI MVP parity confirmation;
- `./start.sh web` must remain canonical entrypoint.

## Vision

| Block                   | Statement                                                                                                                                                                 |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Track identity**      | UI track develops as operator-facing interface layer above BeeAgent core, artifacts and module outputs, not as runtime or backend.                                        |
| **Primary objective**   | The purpose of UI is to give the operator and customer a clear console: that came that it was important that degraded, what actions is possible later and where evidence. |
| **BeeUI rule**          | BeeUI is canonical web framework layer for BeeAgent. BeeAgent gives adapter/read-model/artifacts, BeeUI rendezvous.                                                       |
| **Backend rule**        | Backend UI layer remains FastAPI-based through BeeUI embedded app. BeeAgent does not duplicate BeeUI templates/static/common UI.                                          |
| **Frontend rule**       | Frontend v1 - BeeUI server-rendered UI. Separate React/Tabler allowed later only above stable BeeUI/BeeAgent API.                                                         |
| **Source of truth**     | UI reads `config/settings.yml` and existing artifacts from `storage/`. UI does not become source of truth for runtime/business state.                                     |
| **Safety rule**         | UI read-only default. Any write/control actions passes through explicit product-owned backend action API, validation, confirmation and audit.                             |
| **Artifact rule**       | All UI values must be traceable to source artifacts. Missing/partial/corrupted data be shown clearly.                                                                     |
| **Module rule**         | UI does not contain ROP business rules. Domain logic remaining in `beeagent-rop`; UI shows outputs/artifacts.                                                             |
| **Customer rule**       | Customer-facing link is possible only through the existing auth/session boundary and after deployment/security hardening, which corresponds to the environment.           |
| **Future console rule** | Future standalone BeeUI or separate frontend may be connected to stable BeeAgent/BeeUI API, but must not create the second backend truth.                                 |

## Architecture direction

Target architecture UI:

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

Each UI-iteration must:

- Stay inside one coherent product scope;
- operating through canonical BeeAgent web entrypoint;
- Use BeeUI for rendering/common UI;
- Use BeeAgent `interfaces/ui` adapter/read-model as product boundary;
- use existing artifacts/read-models as source of truth;
- do not call mailbox/CRM/module/capability execution of GET routes;
- do not mutate `storage/`, config or runtime state without the explicit bounded action flow;
- Save read-only behavior for dashboard/run/detail/artifact GET routes;
- Use `config/settings.yml` as source of truth for runtime config;
- Use `config/beeui.yml` as source of truth for UI schema/layout;
- Validate new mandatory config keys fail-fast;
- Create audit artifacts for bounded write/control actions later;
- do not disclose secrets in HTML/API/logs/artifacts;
- graceful-handle missing/empty/partial/corrupted artifacts;
- close through Issue / PR / tests / artifacts;
- create a separate Issue and PR for each implementation repository.

For the current BeeAgent UI track this means:

- BeeUI migration, auth boundary, final-decision UX, canonical Queue baseline and embedded Bitrix ROP console are in UI-4-UI-8.5;
- The next product increment is UI-9 legacy web removal after parity confirmation;
- Then complete event-level attachment and Bitrix reconciliation UX;
- Then stabilize API contract;
- Then add bounded operator controls above the existing auth boundary;
- Then add support/admin surfaces;
- standalone/separate frontend remains deferred;
- Do not make control panel to explicit action/audit contract.

## Status values

Permissible status of UI-iterations:

- **PLANNED** — planned
- **IN PROGRESS** - Work
- **DONE** Completed
- **DONE (partial)** partially completed, with restrictions
- **DEFERRED** - Postponed to evidence/ contract stability
- **RETIRED** — The future item is removed as out of date or already covered by iteration; ID not reused

## Roadmap item format

The historical iteration status `DONE` preserves the existing structure and does not rewrite it in the back for formatting purposes only.

The new iteration and materially refined uncompleted iteration use a compact structure:

- `Goal`
- `Depends on` if there are real prerequisites
- `Change level`
- `Scope`
- `Excluded`
- `Deliverable`
- `Acceptance criteria`
- `Checks`
- `DoD`

ROADMAP captures iteration-level product contract.

Specific files complete with payload examples, detailed implementation requirements, extended test matrices and verification evidence belong to Issue, implementation handoff and PR.

The target size of the new iteration is 40-60, with a maximum of 80 lines without justified need.

## Global Definition of Done

UI-iteration must be considered completed if:

- behavior was verified within the declared scope;
- route/API contract is covered by tests;
- HTML/API output does not reveal secrets;
- GET/read-only routes does not mutate artifacts/config/runtime state;
- bounded write/control paths creates audit artifacts, if they are in scope;
- The new mandatory config keys is read from `config/settings.yml` or `config/beeui.yml`;
- the new mandatory config keys must be validated fail-fast;
- missing/partial/corrupted artifacts handled gracefully;
- source artifacts is clearly reflected in payload/view;
- tests and smoke checks have been completed;
- required quality/security checks is complete with change level;
- `docs/WEB_UI.md` updated if implemented route/API contract changed;
- `README.md` / `docs/DEV_GUIDE.md` updated if the mode of launch/usage has changed;
- `pyproject.toml.version` does not change in the normal UI feature PR;
- if increment cross-repository, each implementation repository is closed separately Issue and PR in the correct merge order.

## Change levels for UI track

UI track uses the same change levels:

- **low-risk** — docs, harmless copy/style cleanup, tests without route/API/config/runtime change;
- **runtime-risk** — dashboard/read-model/API changes, artifact parsing, route behavior, template rendering, BeeUI adapter payloads;
- **security-sensitive** — auth, config mutation, operator controls, action API, runtime control artifacts, file/path handling, new dependencies, external exposure.

Rule:

- read-only dashboards is usually `runtime-risk`;
- BeeUI dependency/migration with file/path/artifact browser usually `security-sensitive`;
- auth/control/action/config apply/file/path-sensitive changes — `security-sensitive`;
- docs-only and copy/style-only changes — `low-risk`.

## Baseline already achieved

At the beginning of BeeUI migration baseline was considered as:

- BeeAgent had legacy read-only Web Console after previous UI work;
- route `/runs` showed runs;
- route `/runs/<run_id>` showed run overview;
- route `/runs/<run_id>/rop` showed ROP dashboard;
- route `/modules` showed module diagnostics if artifact is available;
- web routes read existing artifacts;
- web routes did not launch ROP run;
- web routes did not make CRM/mailbox actions;
- raw `.eml` and attachment content were not to be ran;
- path traversal was to be locked;
- `beeagent-rop` was not changed by UI- tasks;
- It24 multi-source artifacts has already been displayed in legacy ROP dashboard;
- BeeAgent It25 attachment extraction artifacts existed;
- `beeagent-rop It15` consuming attachment metadata was completed.

This is the historical baseline. New web work now goes through BeeUI-backed `interfaces/ui`, and legacy web is to be disposed of by UI-9.

---

## Stage 0 — Planning and architecture decision

### Iteration UI-0 — UI roadmap and FastAPI/Tabler decision

**Status:** DONE

#### Goal

Record UI direction for BeeAgent: FastAPI backend, Jinja2 + Tabler frontend v1, stable `/api/*` as a future contract for a separate frontend.

#### Scope

**Includes:**

- Create `docs/product/ui_roadmap.md`;

- fix UI architecture decision:
  - FastAPI web backend;
  - Jinja2 server-side templates;
  - Tabler UI kit;
  - stable JSON API;
  - no Reflex as BeeAgent core;
  - no separate frontend until API stabilizes;
  - SQLAdmin only later for DB-backed admin models;

- Update `docs/ROADMAP.md` with the minimum UI track reference;

- Update `docs/WEB_UI.md` if current baseline needs to be recorded;

- determine the order of UI-terations relative to BeeAgent It24-It27.

**Excluded:**

- Code changes;
- FastAPI migration;
- Tabler integration;
- auth;
- actions;
- separate frontend.

#### Deliverable

There is a separate UI roadmap and an architectural decision on Web Console.

#### Checks

- docs review;
- roadmap consistency review;
- no runtime changes;
- no tests required unless docs tooling exists.

#### DoD

- `docs/product/ui_roadmap.md` is created;
- `docs/ROADMAP.md` does not duplicate UI-track parts;
- UI direction understood for the following issues.

---

## Stage 1 — FastAPI + Tabler web foundation

### Iteration UI-1 — FastAPI + Tabler Web Console foundation v0

**Status:** DONE

#### Goal

Transfer the current read-only BeeAgent Web Shell from `http.server` to FastAPI-based Web Console from Jinja2 + vendored Tabler static assets, while saving the current read-only route semantics, artifact source-of-truth and security boundary.

#### Why this is needed

UI-0 recorded the architectural decision:

- FastAPI backend;
- Jinja2 templates;
- Tabler UI kit;
- stable `/api/*`;
- no Reflex as BeeAgent core;
- no separate frontend until API stabilizes;
- SQLAdmin only later for DB-backed admin.

Now we don't need docs-only PR, but runtime foundation, which will build on:

- multi-source dashboard;
- attachment-aware dashboard;
- Bitrix reconciliation dashboard;
- auth;
- bounded operator controls;
- future BeeConsole.

#### Scope

**Includes:**

- Replace stdlib `http.server` web runtime with FastAPI app inside `src/beeagent_module/web`;
- Save `./start.sh web`;
- Use existing `web.host`, `web.port`, `web.open_browser`;
- Add/save Jinja2 templates;
- connect vendored Tabler assets from `src/beeagent_module/web/static/vendor/tabler/`;
- Save HTML routes:
  - `/`;
  - `/runs`;
  - `/runs/{run_id}`;
  - `/runs/{run_id}/rop`;
  - `/modules`;

- Add read-only API routes:
  - `/api/runs`;
  - `/api/runs/{run_id}`;
  - `/api/rop/runs/{run_id}/dashboard`;
  - `/api/modules`;

- Save artifact-only read behavior;
- Save path traversal protection;
- Save no raw `.eml` / no attachment content behavior;
- Provide no GET mutation;
- Add FastAPI TestClient tests;
- Update:
  - `docs/WEB_UI.md`;
  - `README.md`;
  - `docs/DEV_GUIDE.md`;
  - `docs/product/ui_roadmap.md` status notes;
  - `docs/ROADMAP.md` is only the minimum reference to UI track, without duplication.

**Excluded:**

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

`./start.sh web` starts FastAPI + Jinja2 + Tabler read-only Web Console above existing artifacts.

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

## Stage 2 — BeeUI operator console and ROP surfaces

### Iteration UI-2 — ROP multi-source dashboard v1

**Status:** DONE

#### Goal

To expand BeeAgent Web Console ROP dashboard under multi-source ROP run after BeeAgent It24:, the operator must see aggregate and per-source the picture for all sources of the current run, including source status, degraded reasons, loaded/classified counts and source-aware event table.

#### Why this is needed

After `BeeAgent It24 — ROP multi-source ingestion artifacts v0` BeeAgent can launch one ROP run for several configured `rop.sources[]` and write source-aware artifacts:

- `source_diagnostics.json`;
- `intake_metadata.json`;
- `normalized_events.json`;
- `classified_events.json`;
- `operator_summary.json`;
- `rop_review_table.tsv`.

But the current Web Console/ROP dashboard does not yet show multi-source the painting:

- degraded source could be lost to aggregate count;
- The operator does not see which source gave which events;
- The filters do not allow the review to be quickly reduced to `source_id` / `source_role`;
- API payload is not sufficiently suitable for the future stable `/api/*`;
- single-source and multi-source runs must be shown equally predictable.

#### Depends on

- `BeeAgent It24 — ROP multi-source ingestion artifacts v0`

#### Scope

**Includes:**

- expand ROP dashboard read-model under It24 artifact contract;

- Show aggregate source KPIs:
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

- Add per-source summary table:
  - `source_id`;
  - `source_type`;
  - `source_role`;
  - `source_display_name`;
  - `client_id`;
  - `authority`;
  - `mailbox_folder`, if any;
  - `status`;
  - `reason`;
  - `items_max`;
  - `fetched_count`;
  - `loaded_count`;
  - `malformed_count`;
  - `classified_count` if possible from classified events;
  - `fallback_count` if possible from classified events;

- expand ROP event table source-aware in columns:
  - `source_id`;
  - `source_type`;
  - `source_role`;
  - `source_display_name`;
  - `client_id`;

- Add/expand filters:
  - `source_id`;
  - `source_role`;
  - `source_status`;
  - `case_type`;
  - `priority`;
  - `fallback`;
  - `reason_code`;

- Update `/api/rop/runs/{run_id}/dashboard` payload:
  - Save backward-compatible fields where this is reasonable;
  - Add `source_aggregate`;
  - Add `sources`;
  - Add source-aware filter options;
  - Add source fields to `rows`;

- graceful handling:
  - old single-source runs;
  - new multi-source runs;
  - missing `aggregate`;
  - missing `sources[]`;
  - one degraded source;
  - malformed source diagnostics;
  - empty source;
  - non-ROP run;

- Save read-only behavior:
  - no GET mutation;
  - no mailbox/CRM/module/capability calls;
  - no web-triggered `rop run`;

- Save sanitization:
  - no raw `.eml`;
  - no `message/rfc822`;
  - no attachment content;
  - no secrets in HTML/API;

- Add/update tests:
  - single-source compatibility;
  - multi-source dashboard rendering;
  - source filters;
  - degraded source visibility;
  - API payload shape;
  - no mutation;
  - sanitization;

- Update docs:
  - `docs/WEB_UI.md`;
  - `docs/product/ui_roadmap.md`;
  - `README.md` / `docs/DEV_GUIDE.md`, if usage/contract. changes

**Excluded:**

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

`/runs/{run_id}/rop` and `/api/rop/runs/{run_id}/dashboard` show source-aware ROP dashboard for old single-source and new multi-source runs.

The operator sees:

- aggregate multi-source health;
- per-source status/degraded reasons;
- source-aware event table;
- source filters;
- classification/fallback metrics without hiding failed/degraded sources.

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

- `/runs/{run_id}/rop` extended to source-aware read-model:
  - aggregate source KPI card;
  - per-source summary table;
  - source-aware event columns;
  - source filters (`source_id`, `source_role`, `source_status`).

- `/api/rop/runs/{run_id}/dashboard` is extended by fields:
  - `source_aggregate`;
  - `sources`;
  - source-aware `filter_options`;
  - source-aware `rows` fields.

- backward compatibility retained for old single-source runs.
- read-only/security boundary retained: no GET mutation, no mailbox/CRM/module/capability execution from GET routes, sanitization retained.

### Iteration UI-3 — UI roadmap and BeeUI migration decision

**Status:** DONE

#### Goal

Record a separate UI/operator-web track for BeeAgent and make an architectural decision: BeeUI becomes canonical web framework layer, legacy `src/beeagent_module/web` to be removed after BeeUI MVP parity.

#### Scope

**Includes:**

- Update `docs/product/ui_roadmap.md`;
- Record BeeUI migration direction;
- fix target structure:

```text
src/beeagent_module/interfaces/ui
```

- Record that web UI belongs to `beeagent`, not `beeagent-rop`;
- Record that `beeagent-rop` does not contain web routes/templates;
- Record BeeUI-only direction for new web work;
- legacy `src/beeagent_module/web` marked deprecated/frozen;
- Describe UI-1/UI-2 BeeUI migration path;
- fix Python 3.14 / dependency hygiene prerequisite.

**Excluded:**

- Code changes;
- dependency `beeui`;
- route switch;
- legacy web removed;
- config/actions/auth;
- changes to `beeagent-rop`.

#### Deliverable

There's an updated UI roadmap and an architectural decision on BeeUI migration.

#### Checks

- docs review;
- roadmap consistency review;
- no runtime changes;
- no tests required unless docs tooling exists.

#### DoD

- `docs/product/ui_roadmap.md` updated;
- `docs/ROADMAP.md` does not duplicate UI-track parts;
- The team realizes that the new web work only goes through BeeUI adapter;
- legacy web no longer develops feature-wise.

### Iteration UI-4 — BeeUI canonical ROP operator console MVP

**Status:** DONE

#### Goal

Connect `beeui` as canonical BeeAgent web surface and give minimum read-only ROP operator console above existing BeeAgent ROP artifacts.

#### Why this is needed

After BeeAgent It24/It25 and `beeagent-rop It15` backend/artifact/domain path already creates enough evidence for MVP:

```text
multi-source mailbox/json_batch
→ attachment extraction artifacts
→ normalized events
→ beeagent-rop classification
→ classified events
→ ROP summary
→ operator-visible artifacts
```

But legacy web shouldn't develop any further. BeeAgent must switch to reusable BeeUI layer to avoid copying Tabler/Jinja/static/dashboard/artifact browser logic by product.

UI-4 is the first runtime/code increment after BeeUI migration decision: `./start.sh web` must launch BeeUI-backed BeeAgent console, not legacy `src/beeagent_module/web`.

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

Reason:

- new dependency surface;
- embedded web app integration;
- artifact browser / file/path boundary;
- route behavior change;
- package/static/templates boundary;
- user-controlled route params;
- HTML/API exposure.

#### Scope

**Includes:**

- Add dependency:

```toml
beeui>=0.13,<0.30
```

- Add local editable `beeui` source for dev, if BeeUI is used as a neighbouring local repo:

```toml
[tool.uv.sources]
beeui = { path = "../beeui", editable = true }
```

- create BeeAgent-side UI package:

```text
src/beeagent_module/interfaces/ui/
  __init__.py
  app.py
  adapter.py
  read_model.py
  artifacts.py
  bounded_read.py
```

- Add thin CLI entrypoint:

```text
src/beeagent_module/cli/web.py
```

- Switch `config/start.py web` to `src/beeagent_module/cli/web.py`;
- Save canonical launch:

```bash
./start.sh web
```

- Add support for web CLI overrides:

```bash
./start.sh web --host 127.0.0.1 --port 8780 --no-open
```

- Add route listing diagnostic if this does not inflate scope:

```bash
./start.sh routes
```

- Add `config/beeui.yml` as source of truth for BeeUI navigation/pages/blocks;
- implement BeeAgent app composition through BeeUI embedded API;
- Implement `BeeAgentUiAdapter`;
- Use BeeUI adapter / page / block registry style, rather than hardcoded product UI inside core;
- legacy `src/beeagent_module/web` should be left as code fallback only to UI-9, but not developed;
- Implement read-only dashboard;
- Implement runs list;
- Implement run detail;
- Implement ROP dashboard read-model;
- Implement modules/registry diagnostics read-model;
- Implement allowlisted artifact browser;
- hold safe ROP source parameters in config read-model;
- Prohibit arbitrary storage browsing;
- bounded JSON/JSONL/text/TSV preview;
- path traversal protection;
- no raw `.eml`;
- no raw attachment content;
- no secrets in HTML/API/logs;
- attachment aggregate counts can only be shown if they are already available in existing artifacts;
- detailed attachment-aware dashboard should be retained for a separate UI-iteration;
- docs update:
  - `docs/WEB_UI.md`;
  - `docs/product/ui_roadmap.md`;
  - `README.md`;
  - `docs/DEV_GUIDE.md`;
  - `docs/SECURITY.md` only if security rules materially change.

**Excluded:**

- legacy `src/beeagent_module/web` removed;
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

### Iteration UI-5 — Rich ROP dashboard parity + operator intelligence v1

**Status:** DONE

#### Goal

Bring BeeUI-backed ROP dashboard to full operating panel level: return parity to legacy Web Console and add operator intelligence to the existing ROP artifacts - KPI, source health, processing funnel, attention items, deterministic recommendations, review events table and evidence links.

#### Why this is needed

UI-4 performed an important infrastructure task: `./start.sh web` now starts BeeUI-backed console, and the new web work must go through `src/beeagent_module/interfaces/ui`.

However, UI-4 was foundation/cutover rather than a complete product dashboard. The current BeeUI ROP screen is too limited:

- not a small KPI;
- not fully processing funnel;
- source health is visible limited;
- No operator recommendations;
- There is no convenient event table for review;
- attachment status is not sufficiently visible;
- artifact evidence is not assembled in an understandable block;
- The main dashboard and ROP- section do not give the operator a quick answer: I don't know what happened, what was processed, where the problem and what to do next.

Remove legacy `src/beeagent_module/web` until dashboard parity is recovered early. BeeUI ROP dashboard must first become as good as legacy and more useful for MVP review.

#### Product direction

The main dashboard `/` remains the total BeeAgent operator dashboard:

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

ROP dashboard `/rop` - module/operator section for `beeagent-rop`, but implementation remains in `beeagent`, because UI belongs to BeeAgent operator layer.

Future modules must be connected and disabled via module registry / artifacts without turning UI into ROP-only application.

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

Reason:

- change dashboard/read-model/API payloads;
- Changed HTML rendering for operator dashboard;
- UI reads and aggregates existing artifacts;
- New deterministic recommendations are emerging;
- route/API behavior changes but without new dependencies, auth, POST/actions, file/path contract changes or external execution.

Escalate to `security-sensitive` only if implementation changes dependency surface, file/path handling, artifact allowlist semantics, auth, POST/actions, external exposure, mailbox/CRM/capability execution, or raw attachment rendering.

#### Scope

**Includes:**

- expand BeeAgent ROP read-model to:

```text
src/beeagent_module/interfaces/ui/read_model.py
```

- expand BeeAgent ROP HTML/API rendering to:

```text
src/beeagent_module/interfaces/ui/app.py
```

- Save BeeUI-backed route surface from UI-4;
- Make `/rop` complete operator intelligence page;
- Support latest run by default;
- Support selected run through:

```text
/rop?run_id=<run_id>
/api/rop/dashboard?run_id=<run_id>
```

- Add references from `/runs` or run detail to `/rop?run_id=<run_id>`, if this can be done without extending scope;
- Add ROP KPI cards/read-model:

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

- Add processing funnel:

```text
configured_sources
→ enabled_sources
→ fetched_items
→ loaded_items
→ normalized_events
→ classified_events
→ review_candidates
```

- Add source health table:

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

- Add classification distribution:

```text
case_type_counts
priority_counts
reason_code_counts
fallback_count
```

- Add deterministic recommendations / operator attention block.

Recommendations constructed without LLM, only from artifacts:

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

- Add events needing review table, maximum 50 lines:

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

- Add attachment summary to aggregate level without raw content:

```text
total_attachments
preview_available_count
refused_count
blocked_count
unsupported_count
oversized_count
extraction_error_count
```

- Add evidence/artifact links block:

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

- expand `/api/rop/dashboard` read-model with new fields:

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

- Save backward compatibility where practical:
  - Old single-source runs;
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

- Save read-only/security boundary:
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

- Update tests:
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

- Update docs:
  - `docs/product/ui_roadmap.md`;
  - `docs/WEB_UI.md`;
  - `README.md`;
  - `docs/DEV_GUIDE.md` if usage or route behavior changes.

**Excluded:**

- legacy `src/beeagent_module/web` removed;
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
1. How many events have come?
2. How much was actually processed?
3. What sources are degraded?
4. What events require attention?
5. What do we do next?
6. Which artifacts confirm the conclusion?
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

- `build_rop_dashboard_read_model` extended to `read_model.py`:
  - helper- functionality added for KPIs, funnel, source health, classification distribution, attachment summary, recommendations, attention events, evidence links;
  - Saved by backward compatibility for legacy single-source runs and old fields (`sources`, `classified_count`, `case_type_counts`, `priority_counts`, `fallback_count`, `normalized_count`, `has_attachment_extraction`);
  - missing/malformed artifacts does not cause crash but generates warning;
  - deterministic recommendations without LLM;
  - attention events capped to 50 lines;
  - evidence links uses allowlist from `artifacts.py`.

- `/rop` transferred to BeeUI shared shell:
  - Rendering through Jinja2-shablon `beeagent_page.html`, expanding `base.html`;
  - Left sidebar with navigation (Dashboard, Runs, ROP Dashboard, Modules);
  - Tabler--compatible layout: card, datagrid, badges, alert, list-group;
  - All artifact-derived values must be shielded.

- `/rop` layout completely reprocessed:
  - Row 1: Run Overview (datagrid) + KPI mini-cards (Connected Sources, Loaded Items, Classified Cases, Need Review, High-Priority Cases, Attachments/Preview);
  - Row 2: Recommendations, Evidence & Exports (list-group with available/unavailable), Source Health (compact table);
  - Row 3: Processing Funnel + Source Details (if >1 source);
  - Row 4: Classification Breakdown (Case Types, Priorities, Reason Codes in 3 columns);
  - Row 5: Operator Queue (full table, max 50);
  - Row 6: Attachment Processing (KPI mini-cards).

- `/runs/{run_id}/artifacts/{artifact_id}` now HTML artifact viewer:
  - breadcrumb (Dashboard → Runs → Run → Artifact);
  - TSV → HTML table;
  - JSON → pretty block + "Open as JSON" link;
  - Errors/warnings in alert;
  - HTML- shielding.

- `/api/runs/{run_id}/artifacts/{artifact_id}` saved as JSON envelope.

- `/modules` transferred to BeeUI shell.

- `config/beeui.yml` navigation updated under UI-5.

- Tests: 56 tests in `test_beeui_console.py` (there was 50):
  - Added: `test_rop_renders_within_shell`, `test_artifact_viewer_html_returns_html_not_json`, `test_artifact_viewer_api_still_json`, `test_tsv_artifact_viewer_renders_table`, `test_json_artifact_viewer_readable`, `test_artifact_viewer_missing_artifact_shows_error`.

- `pyproject.toml.version` is unchanged.

- `beeagent-rop` is unchanged.

- legacy web is unchanged.

- dependencies unchanged.

- CDN not added.

- raw content does not open.

#### UI-5 post-DONE polish — BeeUI 13.1 platform overview dashboard

**Status:** DONE

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

### Iteration UI-6 — Expose latest-N, threads, AI assist, RU labels, operator recommendations

**Status:** DONE

#### Goal

Make the results of BeeAgent It30 visible and useful in BeeUI-backed ROP console: show latest-N/source selection evidence, thread context, AI assist evidence, RU labels and deterministic operator recommendations on `/rop` and `/api/rop/dashboard`.

#### Why this is needed

BeeAgent It30 has already added runtime/artifact-level layer for ROP MVP:

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

But if these data are left only in `storage/runs/<run_id>/...`, ROP does not benefit from the product:

- It's not clear which emails actually came into the last box;
- You can't see where the email is part of the chain;
- You can't see where AI assist helped, degraded or was missed;
- It is not apparent which events require manual verification precisely because of thread/AI/fallback context;
- Russian-speaking operator sees a partial set of RU labels;
- evidence is in artifacts, but not collected in operator-facing view.

UI-6 converts It30 from backend evidence layer to operator-visible MVP increment.

The main rule remains:

```text
BeeUI renders.
BeeAgent decides/orchestrates.
beeagent-rop classifies.
```

This iteration is implemented in `beeagent`, not in `beeui`, because latest-N, thread context, AI assist interpretation and ROP operator recommendations are product-specific BeeAgent ROP read-model. BeeUI only to hold generic layout blocks.

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

Reason:

- Extension of HTML/API exposure for artifact-derived data;
- Add new allowlisted artifact IDs to UI artifact browser;
- UI reads AI assist artifacts, thread artifacts and mailbox selection artifacts;
- changes ROP dashboard read-model and API payload;
- email/thread/AI artifacts values are untrusted input;
- The absence of raw `.eml`, raw attachment content, secrets, provider tokens and AI secret leakage. must be confirmed.

SCA is not required if `pyproject.toml` / `uv.lock` does not change.

#### Scope

**Includes:**

- expand BeeAgent UI artifact allowlist with safe It30 artifacts:

```text
mailbox_selection_json          -> mailbox_selection.json
mail_thread_index_json          -> mail_thread_index.json
mail_thread_context_json        -> mail_thread_context.json
rop_ai_assist_requests_json     -> rop_ai_assist_requests.json
rop_ai_assist_decisions_json    -> rop_ai_assist_decisions.json
rop_ai_assist_results_json      -> rop_ai_assist_results.json
```

- ensure that artifact preview remains bounded/redacted:
  - no raw `.eml`;
  - no raw attachment content;
  - no provider credentials;
  - no env values;
  - no secret-like fields;
  - no arbitrary storage browsing.

- expand ROP dashboard read-model to:

```text
src/beeagent_module/interfaces/ui/read_model.py
```

- Expand `BeeAgentUiAdapter.get_page("rop_dashboard", query)` / related adapter path so that `/rop` receives new sections through existing BeeUI `layout[]`, rather than through BeeAgent-owned templates;
- Add latest-N/source selection summary;
- Add thread summary;
- Add bounded thread table / thread groups, maximum 50 lines;
- Add AI assist summary;
- Add AI assist event table, maximum 50 lines;
- expand deterministic recommendations without LLM and runtime execution;
- Increase attention/operator queue;
- Add RU labels for new UI sections via existing locale helper;
- Save `?lang=ru` behavior;
- Update `config/beeui.yml` tabs for `/rop`.

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

`bitrix` remains read-only/reserved/evidence-only within this iteration.

- expand `/api/rop/dashboard` payload, save backward-compatible existing fields;
- Add evidence links for It30 artifacts;
- graceful handling for missing/malformed/old-run scenarios;
- Save read-only/security boundary;
- Update targeted tests and docs.

**Excluded:**

- Changes in `beeagent-rop`;
- New AI provider calls from UI;
- Change runtime AI assist execution logic;
- change `run_rop_batch_case(...)` behavior;
- The change of It30 artifact generation contract except fixtures test tests;
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

BeeUI-backed `/rop` becomes operator-facing surface for It30 evidence.

`/api/rop/dashboard` returns the same enriched read-only model.

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

### Iteration UI-7 — BeeUI-backed auth boundary for BeeAgent console

**Status:** DONE

#### Goal

Add a minimum auth/session boundary for BeeUI-backed BeeAgent Web Console, so that `/`, `/rop`, `/runs`, `/modules`, artifact browser and read-only API cannot be opened without explicit authentication when `web.auth.enabled: true` cannot be opened.

#### Why this is needed

After UI-6, BeeAgent Web Console started showing operator-facing ROP evidence:

```text
latest-N mailbox selection
thread context
AI assist evidence
source/client metadata
artifact links
operator recommendations
```

This data cannot be shown safely on private/customer link without auth boundary.

At the time of the planning, UI-7 auth boundary had a higher priority than legacy cleanup. After UI-7 was completed, development continued through UI-8 and UI-8.1, while the removal of legacy web remained a separate future iteration of UI-9.

The main rule is:

```text
BeeUI renders and owns generic auth/session primitives.
BeeAgent owns product config, policy and route integration.
beeagent-rop remains domain-only.
```

This iteration is implemented in `beeagent`, but must not duplicate BeeUI auth internals. BeeAgent must use the existing BeeUI auth/session layer.

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

**Includes:**

- Add config-driven BeeAgent web auth policy to `config/settings.yml`;
- Keep only auth mode, principal metadata and env variable names in config;
- Keep secrets only in env;
- Validate auth config fail-fast;
- Integration of BeeAgent app composition with BeeUI auth/session layer;
- Protect BeeAgent HTML and read-only API routes at auth enabled;
- Keep `/health` public and sanitized;
- Keep static assets public;
- Support the roles of `viewer`, `operator`, `admin`;
- Save read-only behavior for all roles in UI-7;
- Return safe unauthenticated HTML/API response;
- Save locale/navigation behavior;
- Save no-mutation/no-secret/no-external-execution boundary;
- Update tests and docs.

**Excluded:**

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

BeeAgent Web Console operates in two distinct modes:

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

### Iteration UI-8 — ROP final decision read-model + recommendations + Bitrix widget payload MVP

**Status:** DONE

#### Goal

Move the BeeUI-backed ROP console and Bitrix widget payload to the final decision model: the deterministic classifier and AI adjudicator produce the final `final_decision`, Web UI shows a clear queue and recommendations, and the Bitrix widget receives the same read-model without separate business logic.

#### Why this is needed

After UI-7 Web Console is protected by auth boundary and is already available as private operator console. but the current ROP UI still partly shows an outmoded model:

```text
AI Assist tab reads legacy rop_ai_assist, although the current source of truth is rop_ai_adjudicator.
Recommendations tab is empty if rop recommendations. is not started separately
Queue tab shows a list of events, but not the final working model of the solution.
Bitrix tab/widget does not receive a full final decision payload.
```

100-run acceptance classifier/AI stage is stable enough. Then you need operator-facing layer:

```text
classified_events
+ rop_ai_adjudicator_results
+ routing config
→ final_decision projection
→ recommendations
→ Web UI
→ Bitrix widget payload
```

The product- rule:

```text
ROP does not confirm the classification by hand.
BeeAgent shows the final decision and the flags of attention.
ROP manages the work queue rather than choosing sales/tender/logistics/ignore from scratch.
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

**Includes:**

- Add current AI adjudicator artifacts to ROP artifact allowlist;
- do `rop_ai_adjudicator_results.json` current source of truth for AI tab/read-model;
- Leave legacy `rop_ai_assist_*` only as legacy evidence/fallback;
- correct AI tab and counters;
- Add normalized final decision projection;
- for MVP always display `bitrix_write_allowed=false`;
- Limit `automation_allowed` to internal routing/display automation;
- use `manual_review` only as technical exception/fallback;
- Add or reuse `rop_final_decisions.json`;
- Support computed read-only fallback for old runs;
- Generate or reuse `rop_recommendations.json`;
- Update queue, event detail, overview metrics and Bitrix widget payload;
- Save widget read-only/token-protected/no-Bitrix-REST boundary;
- Update docs and tests.

**Excluded:**

- Changes in `beeagent-rop`;
- New deterministic classifier rules;
- change OpenAI prompt without direct read-model bug;
- CRM/Bitrix write-back;
- mailbox mutations;
- web-triggered ROP run;
- operator POST actions;
- auth/RBAC changes;
- Bitrix placement install;
- OAuth/OIDC Bitrix app lifecycle;
- separate frontend;
- dependency changes;
- legacy `src/beeagent_module/web` removed.

#### Deliverable

Web UI and Bitrix widget payload use one final solution model.

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

### Iteration UI-8.1 — Web Console UX increment: Queue, filters, sort, pagination, locale, charts, Event Detail

**Status:** DONE

#### Goal

Finalize Web Console UX increment: to implement a full Queue tab with server filters, multi-select dropdown, sorting, pagination, harmonized URL/query builder, unified adapter-level contract for HTML/API parsing and validation, correct date sorting, elimination of lox, charts and complete Event Detail page.

#### Why this is needed

UI-8 implemented final decision read-model, but Queue tab and the total UX Web Console required improvement:

- URL/query parameters were formed manually;
- HTML/API parsing and validation were scattered;
- page number did not always come from canonical `paginate_items()`;
- date sorting misprocessed missing/malformed dates;
- RU locale contained duplicate keys;
- No regression- tests on special-character and invalid input.

#### Depends on

- UI-8 — ROP final decision read-model + recommendations + Bitrix widget payload MVP;
- implementation work from `review/pr152`.

#### Change level

```text
security-sensitive
```

#### Scope

**Includes:**

- single URL/query builder through `urllib.parse.urlencode`;
- registry dependency BeeUI `beeui>=0.22,<0.30`;
- local editable source removed;
- canonical query-state preservation;
- unified adapter-level parsing and validation;
- canonical pagination;
- date sorting fix;
- RU locale cleanup;
- regression tests;
- documentation synchronization;
- security checks on exact committed tree.

**Excluded:**

- Changes in `beeagent-rop`;
- Changes in BeeUI;
- legacy `src/beeagent_module/web` removed;
- auth/RBAC changes;
- CRM/Bitrix write-back;
- web-triggered ROP run;
- New runtime artifacts;
- local editable BeeUI dependency.

#### Deliverable

Web Console Queue tab with a single URL builder, adapter-level validation, canonical pagination, corrected date sorting, correct RU local, regression tests and synchronized documentation.

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

- A single URL builder is used in all ROP links;
- adapter-level contract has a query parameters validation;
- canonical pagination is used in HTML/API;
- missing/malformed dates always after valid dates;
- RU locale does not contain duplicate keys;
- regression tests covers special chars, round-trip, parity and invalid input;
- documentation synchronized;
- security checks completed.

### Iteration UI-8.2 — Tabler Datepicker integration for ROP Queue date-range filtering

**Status:** DONE

#### Goal

Translate the `Date range` filter on the ROP Queue tab from browser-native `input[type=date]` to generic Tabler Datepicker contract provided by BeeUI, without changing the existing server-side semantics `date_from` / `date_to`.

#### Why this is needed

UI-8.1 completed Queue filtering, sorting, pagination and query validation, but the current `date_range` was visually implemented by two browser-native date controls.

These fields function functionally, but do not use Tabler Datepicker/Litepicker and are visually dependent on the realization of a particular browser.

Presentation layer belongs to BeeUI. BeeAgent must not add its own templates, CSS or JavaScript to correct generic of the component.

#### Depends on

- UI-8.1 — current Queue filtering/query baseline;
- BeeUI Iteration 13.10 — generic Tabler Datepicker contract;
- published BeeUI release containing Iteration 13.10;
- current BeeAgent adapter-level validation for `date_from` and `date_to`.

#### Change level

```text
security-sensitive
```

Reasons:

- Update BeeUI dependency and lockfile;
- Change browser-facing Queue behavior;
- SCA dependency review required;
- DAST-style verification of query parameters and route behavior. required

#### Scope

**Includes:**

- Update BeeUI dependency minimum to the first published version of Iteration 13.10;
- Update `uv.lock` through the regular registry dependency flow;
- use generic BeeUI `filter_form.date_range` without BeeAgent-local template/JS/CSS;
- Save query parameters:
  - `date_from`;
  - `date_to`;

- Maintain support for:
  - Lower limit only;
  - Only the upper limit;
  - both boundaries;
  - cleaning of the range;

- Keep the format `YYYY-MM-DD`;
- Save inclusive server-side filtering;
- Save rejection for malformed and reversed ranges;
- Save Queue `period=all` baseline;
- Save query state in:
  - sorting links;
  - pagination links;
  - reset behavior;
  - Event Detail links and back navigation;

- Add product-level HTML/integration regression tests;
- Check RU/EN rendering;
- Update:
  - `docs/product/ui_roadmap.md`;
  - `docs/WEB_UI.md`;
  - `docs/DEV_GUIDE.md`;
  - `README.md` if user-facing changes the description.

**Excluded:**

- BeeAgent-local Datepicker template;
- BeeAgent-local Litepicker JavaScript or CSS;
- change `date_from` / `date_to` contract;
- combined `date_range` query parameter;
- change timezone or inclusive-bound semantics;
- Change ROP classification;
- Changes in `beeagent-rop`;
- New runtime artifacts;
- config changes;
- API envelope changes;
- auth/RBAC/CSRF changes;
- POST routes;
- web-triggered ROP execution;
- CRM/Bitrix write-back;
- local editable BeeUI dependency;
- version change.

#### Deliverable

ROP Queue uses the generic BeeUI Tabler Datepicker component. released user can choose the starting date, the end date or both borders over the calendar, while BeeAgent continues to receive and validate the previous `date_from` / `date_to` GET parameters.

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

### Iteration UI-8.3 — Canonical ROP Queue table toolbar and shared table presentation

**Status:** DONE

#### Goal

Adopt the BeeUI canonical Tabler table and functional toolbar contract for the ROP Queue without changing filtering, sorting, pagination or read-only behavior.

#### Scope

Included:

- replace the Queue `filter_form + data_table` layout with one `data_table` containing a functional toolbar;
- preserve date, search, classification, priority, Bitrix status, column visibility, sorting and pagination behavior;
- place the column chooser under an ellipsis action immediately after search;
- remove visible `Date range` and `Search` labels while preserving accessible field names;
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

### Iteration UI-8.4 — Locale-aware ROP decision explanations

**Status:** DONE

#### Goal

Make the reasons for the classification, decision AI of the arbitrator and the final attention deterministic in RU/EN without additional AI- calls and without storage of separate AI- explanations for each language.

Iteration is performed after UI-8.3 and up to UI-8.5, as embedded Bitrix widgets will also use `attention_reason`.

#### Scope

- Use the existing `ClassificationReasonCode` as a source of localized classification cause;
- To expand AI adjudicator output to stable `reason_code` and bounded `evidence_codes`;
- Save raw AI reason only as audit/backward-compatible evidence;
- expand final decision projection by `attention_reason_code` and `attention_evidence_codes` fields;
- Add BeeAgent-owned RU/EN reason catalog;
- Add locale-aware display fields to Event Detail read-model and API;
- Use the current `lang` for the formation of display values;
- Ensure that backward-compatible reads the old adjudicator and final-decision artifacts;
- Show localized legacy fallback without provider calls and change artifacts;
- Save BeeUI generic renderer without ROP-specific semantics;
- change level: `security-sensitive`;
- Update UI contract documentation and tests.

#### Excluded

- Second AI- call for translation or generation of another language;
- runtime translation of GET routes;
- Individual RU/EN AI decisions;
- classification taxonomy or rules change to `beeagent-rop`;
- ROP-specific localization in BeeUI;
- New config keys;
- dependency or lockfile changes;
- CRM/Bitrix write-back;
- mailbox actions;
- change auth or authority policy;
- Translation of all historical raw artifact previews.

#### Deliverable

One ROP run contains a single set of semantic reason codes. Event Detail showing `Reason`, `AI adjudicator reason` and `Attention reason` in the selected interface language, retaining raw evidence and backward compatibility.

#### Acceptance criteria

- `lang=ru` shows three main reasons in Russian;
- `lang=en` shows the same semantic reasons in English;
- The change of language does not cause AI provider, mailbox, Bitrix or module execution;
- One eligible event still causes adjudicator provider not more than once;
- the new adjudicator artifacts contains validated reason/evidence codes;
- the new final-decision artifacts contains structured attention reason fields;
- Old artifacts continues to open without mutation and crash;
- unknown or legacy reasons give explicit localized fallback and warning;
- raw AI reason is not primary HTML display value;
- API stores raw fields and adds codes and localized display fields;
- BeeUI and `beeagent-rop` do not change.

#### Checks

- targeted adjudicator schema and validation tests;
- catalog coverage for all current `ClassificationReasonCode`;
- RU/EN Event Detail HTML and API tests;
- old/new/malformed artifact compatibility tests;
- single-provider-call regression test;
- unknown-code and legacy fallback tests;
- HTML escaping and bounded evidence tests;
- GET no-mutation checks;
- route smoke for Event Detail;
- full `uv run pytest -q`;
- route listing;
- SAST and DAST-style locale/artifact misuse review.

#### DoD

- structured reason contract was implemented in `beeagent`;
- All three Event Detail reason values follow the chosen locale;
- Additional AI token costs for localization is not available;
- UI-8.5 may use structured `attention_reason_code`;
- old runs remains readable;
- GET routes remains read-only;
- secrets, raw email and attachment content are not disclosed;
- dependencies and lockfile remain unchanged;
- `pyproject.toml.version` is unchanged;
- tests and documentation updated.

### Iteration UI-8.5 — Embedded Bitrix ROP Console with SSO

**Status:** DONE

#### Goal

Open existing BeeAgent ROP Web Console inside Bitrix24 as Server-Side Local Application with User Interface and automatically create a limited BeeUI session from the tested Bitrix OAuth user context.

#### Scope

- Use the existing `/rop` Web UI without the second frontend and without the new ROP projections;
- Add one-time handler `/bitrix/rop/install` for Local Application reference to one Bitrix portal;
- Add `POST /bitrix/rop/launch` for application launch context processing;
- Take bounded `AUTH_ID`, `AUTH_EXPIRES`, `DOMAIN` and `member_id`;
- Check `DOMAIN` with portal origin set-up;
- Check `member_id` with installation state automatically saved;
- Check `AUTH_ID` through current-user REST call to the Bitrix portal set-up;
- Reject inactive, invalid, expired and cross-portal launches;
- Use Bitrix24 application access without Bitrix user ID BeeAgent list;
- To appoint least-privileged BeeUI role as the tested user;
- Create bounded BeeUI session and perform `303 Redirect` on `/rop`;
- Support iframe-compatible secure session cookie;
- Allow framing only to the adjusted Bitrix portal;
- Save Overview, Queue, Threads, AI Assist, Sources, Attachments, Evidence, Bitrix and Recommendations;
- Save Event Detail, filters, sorting, pagination and allowlisted artifact links;
- Save existing `/api/bitrix/rop/widget*` routes backward-compatible;
- Update dependency prior to the release of BeeUI contract with external-principal session and controlled embedding;
- Update tests and documentation.

#### Excluded

- Two separate Sales Pulse / Risk Control widget;
- new ROP read-model or new KPI projections;
- per-user Bitrix ID lists in `settings.yml`;
- Save `AUTH_ID` or `REFRESH_ID`;
- background OAuth token refresh;
- Bitrix events and subscriptions;
- CRM/Bitrix write-back;
- Automatic registration of Local Application;
- separate frontend or separate application service;
- Changes in `beeagent-rop`;
- ROP classification or recommendation changes.

#### Deliverable

The administrator registers `BeeAgent — ROP` as Local Application. allowed user opens an application from Bitrix24 and without a repetition BeeAgent login receives the existing read-only `/rop` console inside iframe.

#### Acceptance criteria

- Local Application install and launch handlers are available only on HTTPS deployment;
- portal binding is created once and does not contain OAuth secrets;
- copied `/rop` URL without valid BeeUI session does not provide access;
- valid launch defines the current user via Bitrix REST;
- BeeAgent settings do not contain Bitrix user ID lists;
- invalid domain, member, token, user or launch payload are rejected;
- `AUTH_ID` and `REFRESH_ID` are missing from URL, HTML, logs and artifacts;
- session cookie works at supported Bitrix iframe browser;
- framing permitted only configured portal origin;
- The existing ROP navigation operates without functional regression;
- existing widget APIs remains compatible;
- GET routes remains read-only;
- BeeUI is used through the published public contract;
- `beeagent-rop` does not change.

#### Checks

- targeted settings, install, launch, OAuth verification and session tests;
- malformed, expired, cross-portal and inactive-user scenarios;
- cookie, CSP, `X-Frame-Options`, cache and referrer header tests;
- no-token-leakage and no-GET-mutation tests;
- existing ROP tabs, Event Detail and artifact-link regression tests;
- existing widget API compatibility tests;
- `uv run pytest -q`;
- `./start.sh routes`;
- HTTPS route smoke;
- Chrome/Edge manual smoke inside the real Bitrix Local Application.

#### DoD

- BeeUI prerequisite is released and connected;
- Local Application installation and launch flow are sold in `beeagent`;
- verified Bitrix user receives bounded BeeUI session with configured `viewer` or trusted Local App `operator` role; embedded `admin` is excluded;
- all the existing ROP console works inside Bitrix iframe;
- user access is controlled by Bitrix24, not duplicated BeeAgent user list;
- OAuth secrets is not retained or disclosed;
- iframe and session policies tested;
- documentation synced;
- `beeagent-rop` unchanged;
- `pyproject.toml.version` unchanged.

### Iteration UI-8.6 — Principal-bound Web auth and scoped console access

**Status:** DONE

#### Status notes

- implemented by central authorization policy in `src/beeagent_module/core/authorization.py` (model: identity = exact username + token, authority = role, resource access = scopes);
- `web.auth.principals[]` received mandatory explicit `scopes` (`*`, `dashboard`, `rop`, `runs`, `modules`), with fail-fast validation (missing/empty/invalid/duplicate, wildcard-only rule);
- local login is tied to exact configured `username + token`; successful session receives canonical configured principal id;
- On startup, different principals with the same resolved token value are rejected without secret being disclosed;
- server-side authorization is used for HTML/API/resource routes: unauthenticated HTML → login redirect, unauthenticated API → 401, authenticated unauthorized → 403, unknown protected surface → default-deny;
- ROP-only principal only sees `/rop`, Event Detail, `/api/rop/*` and bounded ROP-owned evidence; navigation visibility reflects authorization through BeeUI `navigation_visibility_resolver`;
- ROP-only principal after login reaches `/rop`; verified Bitrix external principal remains bounded ROP-only with configured `viewer` or trusted Local App `operator` role; embedded `admin` is excluded;
- **dependency blocker**: BeeUI Iteration 13.14 `navigation_visibility_resolver` is contained in `beeui 0.26.0`, but release is not yet published in PyPI (only `<=0.25.1` is available), and `beeagent-rop` is not published in registry; registry lock update is not possible until both packages are published. Implementation and verification are done on local beeui 0.26.0 (venv, not pyproject). production rollout requires the publication of `beeui 0.26.0` and `beeagent-rop` in registry, followed by `beeui>=0.26.0,<0.30` + registry `beeagent-rop` lock;
- rollout requires invalidation/rotation old sessions/credentials (`./start.sh auth rotate all --logout-all` / principal token rotation);
- `pyproject.toml.version` unchanged.

#### Goal

Correct BeeAgent Web authentication identity contract and add server-side scoped authorization for multi-module Web Console: local principal must enter only by its `username + token` pair and access to Dashboard, ROP, Runs, Modules and future module surfaces must be determined separately through explicit principal scopes.

#### Scope

**Includes:**

- Save BeeUI-backed session/cookie implementation;
- Tie local login to exact configured `username + token`;
- use canonical configured principal identity in signed session;
- expand `web.auth.principals[]` explicit `scopes`;
- Save `role` only as authority level: `viewer`, `operator`, `admin`;
- use scopes as resource access dimension;
- Support wildcard `*` for explicitly configured full-access principals;
- Validate scopes fail-fast;
- Reject duplicate resolved principal token values without secrets being disclosed;
- Add server-side authorization for protected HTML/API/resource routes;
- default-deny unknown protected surfaces for non-wildcard principals;
- Provide ROP-only access to `/rop`, Event Detail, ROP API and bounded ROP evidence;
- Prohibit ROP-only principal total Dashboard, Runs, Modules and unrelated module artifacts;
- Use generic BeeUI request-scoped navigation visibility contract;
- Hide the unaffordable navigation items;
- direct ROP-only principal after login to the authorized ROP surface;
- Save Bitrix verified external-principal flow as ROP-only configured viewer/operator access, without browser-controlled role or embedded admin;
- Save auth-disabled loopback development mode;
- Update tests and documentation.

#### Excluded

- password database;
- user registration;
- password reset;
- OAuth/OIDC for local login;
- tenant model;
- product roles `rop` / `beescan`;
- ROP-specific behavior inside BeeUI;
- operator POST actions;
- admin/config actions;
- CRM/Bitrix write-back;
- changes to `beeagent-rop`.

#### Deliverable

BeeAgent uses the model:

```text
principal identity = exact username + token
authority = role
resource access = scopes
```

`admin + scopes=["*"]` saves the complete Web Console access, and `viewer + scopes=["rop"]` sees and can read only ROP surface and permitted ROP evidence.

#### Acceptance criteria

- valid token with wrong username is not authenticated;
- valid username with wrong token is not authenticated;
- successful local session contains canonical configured principal identity;
- duplicate token values fail fast;
- scopes is mandatory and validated;
- ROP-only navigation does not contain Dashboard, Runs and Modules;
- direct unauthorized HTML/API requests is given by server-side denial;
- ROP-only principal cannot list or read unrelated module runs/artifacts;
- admin wildcard principal retains existing access;
- unknown future protected surface does not automatically become available scoped principal;
- Bitrix embedded verified user continues to open `/rop` without local user list;
- unauthenticated and forbidden remain different states;
- secrets does not appear in HTML, API, logs or artifacts;
- auth-disabled loopback mode remains compatible.

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

### Iteration UI-8.7 — Fast ROP Web console: bounded reads and progressive navigation v1

**Status:** DONE

#### Goal

Make BeeUI-backed ROP Web Console bounded responsive: Remove historical reconstruction from normal HTTP read path and connect BeeUI responsive page-tabs contract released by maintaining the existing ROP URLs, query semantics, authorization and Bitrix embedding.

#### Scope

- use existing ROP artifacts as canonical product source of truth;
- Create or reuse product-owned materialized Web projection for expensive historical aggregates;
- Update projection with change relevant ROP state;
- provide regeneration projection for existing production runs via supported BeeAgent runtime/build path;
- Remove `aggregate_runs=True` historical reconstruction from normal `/rop` HTTP GET path;
- do not list or reread all historical runs on each Web request;
- build only requested ROP tab;
- Do not build unrelated heavy tab projections;
- Queue filtering, sorting and pagination perform once;
- Save server-side query authority;
- Save existing Queue parameters and filtering semantics;
- Save existing Overview period semantics;
- Save current artifact/evidence links;
- after release BeeUI Iteration 13.15 update BeeUI registry dependency to actually accessible revision;
- Insert `progressive: true` for ROP page tabs;
- Use supported `fill_icons` or equivalent released icon-tabs contract;
- To appoint controlled BeeUI icons all ROP tabs;
- Save canonical `/rop?tab=...` hrefs;
- Save `period`, `run_id` and `lang`;
- Save direct links, refresh and Back/Forward;
- Check Overview charts after progressive transition;
- Check Queue Datepicker/live table after progressive transition;
- Check Bitrix iframe;
- Add deterministic performance regressions;
- Update product UI documentation.

#### Excluded

- Changes in `beeagent-rop`;
- ROP classification/business-rule changes;
- product-owned JavaScript;
- product-owned BeeUI templates;
- SPA;
- React/Vue/Svelte;
- Redis;
- PostgreSQL;
- Elasticsearch;
- generic cache inside BeeUI;
- client-side ROP dataset filtering;
- infinite scroll;
- server hardware upgrade as primary solution;
- auth/scopes redesign;
- Bitrix write-back;
- version bump.

#### Deliverable

ROP Web Console no longer reconstructs historical ROP state for each GET and uses released BeeUI progressive navigation.

Operator receives bounded server-side reads and application-like tab navigation without the second frontend.

#### Corrected projection lifecycle

- normal ROP lifecycle refresh updates only entry of the changed run and existing bounded index; It does not perform the complete historical rebuild of the entire Web catalog;
- If derived index is missing or malformed, normal refresh retains explicit fail-closed and requires a clear bootstrap;
- normal `./start.sh rop dashboard --period 7d` refreshes only the effective run in the bounded catalog. Explicit full bootstrap/regeneration is `./start.sh rop dashboard --period 7d --rebuild-web-projection`; it prepares historical artifacts once, materializes bounded recent run entries and publishes the index only after entries are ready;
- `total_runs` remains materialized scalar, and `run_ids` remains bounded recent catalog;
- The status remains `IN PROGRESS` to deployment and production TTFB/smoke verification corrected lifecycle.

#### Acceptance criteria

- normal `/rop` GET does not call historical `_aggregate_period_events()` path;
- normal ROP Web request does not perform O(number-of-runs) artifact parsing;
- The increase in the number of historical runs does not result in a proportional increase in the number of files read by one request;
- requested tab does not build unrelated tab projections;
- Queue filtering/sorting/pagination is performed once;
- existing filter/search/sort/page/date semantics retained;
- existing tab IDs and canonical URLs retained;
- existing API/read-model semantics retained where practical;
- materialized projection is derived state, not the new business source of truth;
- projection can be regenerate from canonical artifacts;
- missing/malformed derived state must be treated with a clear recoverably;
- BeeAgent uses the actual BeeUI 13.15 contract;
- successful ROP tab transition is not reload- full document;
- refresh/direct links is working;
- Back/Forward is working;
- Overview charts operates after transition;
- Queue Datepicker, search, filters, sorting and pagination operate after transition;
- RU/EN is working;
- Bitrix embedded console is working;
- progressive failure fallback- is on canonical GET;
- GET routes remains read-only;
- authorization remains server-side;
- no BeeAgent-owned navigation JavaScript;
- `beeagent-rop` unchanged.

#### Checks

- full `uv run pytest -q`;
- targeted ROP read-model tests;
- synthetic many-run performance regression;
- no historical-run enumeration regression;
- per-tab builder isolation tests;
- Queue filter/search/sort/page parity;
- projection refresh/regeneration tests;
- missing/malformed projection tests;
- dependency/SCA review for BeeUI update;
- ROP tab config tests;
- RU/EN;
- route-prefix;
- Bitrix iframe;
- Overview → Queue;
- Queue → Overview;
- Queue → Threads;
- Back/Forward;
- refresh/direct link;
- Datepicker after transition;
- live table after transition;
- chart after transition;
- local and production before/after TTFB measurements;
- SAST;
- DAST-style route/query/navigation misuse checks.

#### DoD

- expensive historical reconstruction removed from normal HTTP read path;
- product Web projection lifecycle deterministic and documented;
- ROP GET cost bounded by requested view rather than total historical run count;
- ROP tabs use released BeeUI progressive contract;
- controlled tab icons configured;
- existing URLs/query/auth behavior preserved;
- Bitrix embedding verified;
- performance regressions covered;
- no second frontend introduced;
- no external DB/cache service introduced;
- `beeagent-rop` unchanged;
- tests and production smoke green;
- `pyproject.toml.version` unchanged.

### Iteration UI-8.8 — ROP sender blacklist management v2

**Status:** DONE

#### Goal

Add a black list of e-mail senders in ROP Web Console and Bitrix embedded console controlled by the operator so that new messages from the designated original senders are deterministic to effective classification `irrelevant`, while retaining semantic classification evidence and using the existing Bitrix write-back path.

#### Scope

- Add canonical durable state `storage/interfaces/rop_sender_blacklist.json`;
- Implement bounded load/list/add/remove/match contract;
- Use exact normalized sender e-mail;
- use existing forwarded-mail normalization and original sender precedence;
- Do not repeat MIME/forward-wrapper parsing;
- Apply explicit BeeAgent sender-policy override after semantic/AI classification;
- at match display effective `case_type=irrelevant`;
- Keep base classification evidence separate from policy override;
- Fix auditable reason `sender_blacklisted`;
- Ensure the use of effective result downstream UI/write-back paths;
- Add ROP tab `blacklist` / `Blacklist`;
- Show description: `All emails from these mailboxes will be classified as Irrelevant.`;
- Show canonical e-mail table;
- Add `Add email`;
- Add structured Name/Title/Email/Role CRUD with inline edit, direct bounded Add/Save/Delete, e-mail search, canonical pagination and CSV export; CSV import excluded;
- viewer retained read-only;
- blacklist mutations requires `operator` + `rop` scope;
- Insert BeeUI bounded operator actions only with product callbacks/authorization;
- Allow Bitrix embedded `default_role=operator`;
- Save external Bitrix principal scope `rop`;
- settings deployment on operator only where Bitrix Local App audience is trusted;
- Create bounded audit evidence for mutation attempts;
- Use existing `irrelevant` Bitrix delivery/write-back path;
- Update relevant Web UI/security/config/product-roadmap docs;
- Update BeeUI dependency to actual release containing BeeUI Iteration 13.16.

#### Excluded

- Changes to `beeagent-rop`;
- hardcoded sender/domain rules in domain module;
- domain blacklist;
- subject keyword blacklist;
- regex/wildcards;
- native Bitrix Lead/card button;
- CSV import and unrelated bulk import/export;
- checkbox `send/do not send to Bitrix`;
- silent drop before Bitrix;
- changing/deleting historical Bitrix entities;
- retroactive reclassification of historical runs;
- viewer write authority;
- embedded admin role;
- arbitrary config editing;
- DB introduction;
- per-Bitrix-user/per-group role mapping;
- general Operator Control Panel UI-14;
- unrelated UI-8.8 performance work.

#### Deliverable

ROP Web Console and the same console inside Bitrix Local App have a new `Blacklist` tab where authorized ROP operator can add or remove exact sender e-mail.

New messages from blacklisted effective/original sender are received:

```text
effective case_type = irrelevant
policy reason = sender_blacklisted
```

with the reference semantic classification evidence. retained

Existing Bitrix irrelevant/JUNK write-back behavior is used without new delivery branch.

#### Acceptance criteria

- missing blacklist state initializes as empty state;
- malformed existing state does not silently become empty;
- blacklist writes are atomic/concurrency-safe;
- email normalization is deterministic;
- invalid email is rejected;
- duplicate add is idempotent;
- remove of existing entry succeeds;
- direct blacklist mutations use the protected product action boundary and do not require a browser preview or confirmation;
- direct sender match produces effective `irrelevant`;
- forwarded message matches original sender rather than technical forwarder when canonical original-sender evidence exists;
- test scenario George → Kevin → automatic forward → `technical-forwarder@example.com` matches George;
- malformed/missing original-sender evidence safely falls back to canonical current sender;
- no raw MIME reparsing is introduced;
- base semantic classification remains auditable;
- `sender_blacklisted` override has precedence over AI result;
- downstream UI and Bitrix write-back consume the same effective classification;
- blacklist affects future/new processing only;
- historical run artifacts are not rewritten;
- existing Bitrix entities are not retroactively changed;
- `irrelevant` follows existing configured write-back path;
- blacklist tab is available in ordinary Web Console;
- blacklist tab is available through the existing Bitrix embedded console;
- viewer can read but cannot mutate;
- viewer POST attempt is denied server-side;
- operator without `rop` scope is denied;
- operator with `rop` scope and valid CSRF can execute only known blacklist actions;
- unknown action id is denied;
- enabling `/api/actions/*` does not accidentally grant ROP authority to unrelated future actions;
- external Bitrix principal remains ROP-scoped;
- embedded `admin` is not introduced;
- each mutation attempt produces bounded audit evidence;
- auth tokens, session cookies, raw e-mail body and Bitrix credentials are absent from audit/logs;
- RU/EN labels work;
- existing ROP tabs remain backward-compatible.

#### Checks

```text
uv run pytest -q
```

Targeted tests:

- blacklist state missing/valid/malformed;
- deterministic normalization;
- duplicate add;
- remove;
- atomic/lost-update safety;
- direct sender match;
- forwarded original sender match;
- fallback current sender;
- base classification preservation;
- policy override precedence;
- AI cannot promote blacklisted sender;
- downstream classification/write-back consistency;
- existing `irrelevant` Bitrix plan;
- Web blacklist read-model;
- add/remove action preview;
- add/remove action execute;
- viewer denial;
- operator + wrong scope denial;
- operator + `rop` scope success;
- unknown action denial;
- CSRF failure;
- Bitrix embedded viewer/operator config validation;
- external principal remains `rop` scoped;
- route-prefix/iframe smoke;
- RU/EN rendering;
- existing ROP route regression;
- existing Bitrix write-back regression.

Security checks:

- SAST review for state mutation/action/auth paths;
- DAST-style POST route checks;
- malformed input;
- XSS/email display escaping;
- no raw MIME/body/token leakage;
- state path is fixed/controlled;
- no arbitrary filesystem path;
- dependency SCA after BeeUI dependency update.

Full integration smoke:

```text
blacklist sender
→ new mailbox run
→ semantic classification executes
→ policy override records sender_blacklisted
→ effective irrelevant
→ ROP UI reflects irrelevant
→ Bitrix delivery plan uses existing irrelevant path
```

#### DoD

- BeeUI prerequisite released and consumed by BeeAgent;
- blacklist state has one canonical source of truth;
- forwarded original sender is respected;
- no second forwarding parser exists;
- no `beeagent-rop` changes required;
- Web and Bitrix embedded console share the same blacklist UI;
- viewer remains read-only;
- Bitrix external operator remains ROP-scoped;
- effective `irrelevant` reaches existing Bitrix write-back;
- no delivery toggle/domain/keyword scope creep;
- automated and integration checks pass;
- docs/ROADMAP contracts reconciled;
- no manual BeeAgent package version bump;
- PR reviewed and merged.

### Iteration UI-8.9 — Request-ready ROP Web projection v2

**Status:** PLANNED

#### Goal

Twist ROP Web read path after UI-8.7 to request-ready materialized read model, so that the normal `/rop` and `/api/rop/dashboard` GET read only bounded manifest and one requested semantic view, do not paralyze the projection v1, global writeback state or unrelated raw run artifacts, and provide a subsecond operator response to production-like volume.

#### Scope

- Enter derived ROP Web projection schema v2;
- Save the small bounded manifest for `latest_run_id`, `run_ids`, `total_runs` and generation/revision metadata;
- Allow scoped `run_id` access only through validated manifest membership, without reading semantic view payload;
- materialize request-ready semantic views for `overview`, `queue`, `threads`, `ai_assist`, `sources`, `attachments`, `evidence`, `bitrix`, `recommendations` and dashboard API;
- Segregate projection to semantic view, and period variants to be stored only where period is part of public behavior;
- materialize Queue as one canonical compact row set without physical duplication of one event between overlapping queue buckets;
- Save queue membership as bounded row metadata and current filter/sort/pagination semantics;
- materialize for Overview the necessary totals, series and bounded priority preview without the transmission of full Queue collections;
- Apply trusted writeback overlay until affected projection generation is published, not during normal GET;
- Remove normal GET raw run-artifact reconstruction for tab-specific summaries;
- HTML `get_page("rop", ...)` must return BeeUI presentation-minimal payload after `layout[]` has been built and not the complete multi-megabyte semantic read-model;
- dashboard API retains the current public response semantics, while synchronous read-model work is performed outside async event loop;
- normal GET must read only validated manifest and one requested view;
- normal lifecycle refresh updates only affected run generation/views;
- explicit `rop dashboard` retained as supported bootstrap/regeneration path;
- publication remains atomic: immutable validated views first, manifest last;
- failed projection publication retains the previous valid generation;
- projection remains derived and does not change authority/durability canonical run artifacts or `rop_writeback_state.json`;
- normal GET does not perform implicit migration, repair, regeneration or fallback to historical reconstruction;
- Save the existing `/rop` URLs, query parameters, BeeUI `layout[]` semantics and dashboard API compatibility;
- Update Web/projection lifecycle, migration and performance verification documentation.

#### Excluded

- changes `beeagent-rop` domain contracts or classification semantics;
- changes generic BeeUI or `beeui.js`;
- frontend prefetch/cache as a way to hide server latency;
- SPA/React/HTMX/Turbo;
- Redis, PostgreSQL, SQLite, Elasticsearch, or separate cache service;
- Mandatory process-local parsed-view cache;
- Nginx response caching;
- pre-rendered HTML projection;
- client-side ROP dataset filtering;
- increase Uvicorn worker count as the main performance fix;
- dependency or package version changes.

#### Deliverable

BeeAgent Web runtime uses validated request-ready projection v2, where one ROP Web/API GET allows run through a small manifest, reads exactly one required semantic view and performs only bounded request-specific filtering/layout work without historical reconstruction, global writeback scan or unrelated raw artifact reads.

#### Acceptance criteria

- `/rop` and `/api/rop/dashboard` GET are not enumerates historical runs and do not build dashboard;
- explicit scoped `run_id` authorization reads only bounded manifest metadata;
- one requested tab/period does not require parsing other periods or semantic views;
- normal GET does not read `rop_writeback_state.json`, v1 multi-period per-run projection or unrelated raw run artifacts;
- Overview does not read full Queue dataset for totals or preview;
- Queue uses one canonical deduplicated row set and stores current search/filter/sort/pagination/date/columns behavior;
- Threads and other tabs read only their own request-ready view;
- BeeAgent HTML adapter does not transmit BeeUI unused multi-megabyte semantic collections;
- malformed/missing manifest or requested view fail closed without projection mutation;
- failed publication stores previous valid generation and does not change canonical artifacts/writeback state;
- selected-run anchor semantics remains compatible with UI-8.7;
- warm production-like LOCAL p50 <=300 ms and p95 <=500 ms for Overview, Queue first page, Threads and dashboard API;
- production HTTPS p95 <=1.0 s for the same primary routes;
- The first authenticated LOCAL primary ROP request after Web process restart <=1.5 s and does not start reconstruction;
- warm browser progressive tab transition p95 < 1.0 s after passing server-side gate.

#### Checks

- targeted projection lifecycle, manifest/view parser and read-model tests;
- full `uv run pytest -q`;
- deterministic I/O-boundary tests proving each GET reads only its manifest/requested view;
- tests proving GET does not read history, global writeback, v1 projection or unrelated raw artifacts;
- explicit/implicit `run_id` scoped authorization tests;
- malformed/missing manifest/view, unsafe identifier and path-resolution tests;
- atomic publication, interrupted publication and previous-generation recovery tests;
- incremental refresh and explicit bootstrap smoke;
- HTML adapter payload-boundary regression tests;
- async dashboard API concurrency regression;
- LOCAL/HTTPS cold and warm p50/p95 benchmark;
- browser Back/Forward/F5/filter/sort/pagination/date/locale smoke;
- Bitrix Local App iframe smoke;
- SAST, targeted DAST-style auth/route checks and malformed/fuzz-style projection parser coverage;
- application-log review without raw payload, token or secret leakage.

#### DoD

- request-ready projection v2 is the normal ROP Web/API read path;
- HTTP GET remains read-only and never repairs or regenerates projection;
- incremental refresh and explicit bootstrap publish valid generations atomically;
- scoped authorization uses bounded manifest metadata only;
- HTML adapter returns bounded presentation-ready data;
- canonical run/writeback artifacts remain authoritative;
- current ROP URL/query/BeeUI/API contracts remain compatible;
- recorded LOCAL, HTTPS, cold-start and browser performance gates pass;
- tests and required security checks pass;
- docs describe v2 lifecycle, migration and production verification;
- UI-8.7 remains DONE;
- UI-9 starts only after UI-8.9 performance acceptance is complete.

### Iteration UI-9 — Remove legacy BeeAgent web after BeeUI parity

**Status:** PLANNED

#### Goal

Remove legacy `src/beeagent_module/web` and leave BeeUI the only web framework layer for BeeAgent.

#### Why this is needed

After UI-4-UI-8.5 BeeAgent has BeeUI-backed operator console, auth boundary, final-decision read-model, canonical Queue UX, Event Detail, artifact browser, read-only API and embedded Bitrix widget routes.

Old package-local web shell:

```text
src/beeagent_module/web
```

Continues to duplicate:

- routes;
- templates;
- static assets;
- artifact sanitization;
- dashboard rendering;
- API behavior.

Duplication creates risk of drift and saves the second web surface without food need.

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

Reason:

- legacy web package is removed;
- change imports/tests/docs;
- route ownership and package-data boundaries are finalized;
- file/path/artifact access must remain safe.

#### Scope

**Includes:**

- Delete:

```text
src/beeagent_module/web/
```

- Delete legacy templates/static/routes;
- Delete stale imports, tests and docs references;
- Leave `./start.sh web` canonical;
- Leave app composition in:

```text
src/beeagent_module/interfaces/ui/app.py
```

- Leave adapter/read-model/artifact allowlist in:

```text
src/beeagent_module/interfaces/ui/
```

- Remove legacy package-data from `pyproject.toml`;
- Save only the relevant BeeAgent-side UI package data;
- Update:
  - `docs/WEB_UI.md`;
  - `docs/product/ui_roadmap.md`;
  - `README.md`;
  - `docs/DEV_GUIDE.md`;
- Implement BeeUI-only route/API tests;
- Check the absence of stale import `beeagent_module.web`;
- Remove legacy import and compatibility start path from `src/beeagent_module/core/app.py`;
- To confirm that canonical `config/start.py web` only uses `beeagent_module.cli.web.run_web`;
- Check package install/import.

**Excluded:**

- config/admin/actions;
- POST routes;
- New auth/RBAC changes;
- operator control panel;
- CRM/Bitrix write-back;
- web-triggered ROP run;
- standalone BeeUI service;
- Changes in `beeagent-rop`;
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

### Iteration UI-10 — Attachment detail integration for ROP Queue and Event Detail

**Status:** PLANNED

#### Goal

Add to the existing aggregate Attachment tab event-level submission: Show safe attachment metadata, extraction/refusal evidence and bounded preview in ROP Queue and Event Detail without raw attachment content leakage.

#### Depends on

- UI-8.3 — current canonical Queue toolbar/table baseline;
- UI-9 — BeeUI-only architecture;
- BeeAgent It25 — Attachment extraction artifacts;
- `beeagent-rop It15 — Use BeeAgent attachment extraction contract in classification`.

#### Scope

**Includes:**

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
- Save existing aggregate attachment KPI and not re-implement them;
- no raw files served;
- no arbitrary attachment download;
- Link attachment items to `event_id`;
- Show per-attachment metadata in Event Detail;
- Add safe attachment status indicator to Queue;
- Show bounded preview only at explicit `preview_available=true`;
- Reference existing `attachment_extraction_json` evidence artifact;
- tests and docs update.

**Excluded:**

- OCR UI;
- full document viewer;
- raw attachment content;
- file upload;
- editing classification;
- CRM write-back;
- web-triggered extraction;
- external parser calls from UI;
- changes to `beeagent-rop`;
- inline raw attachment rendering. Agreed with BeeAgent It40: BeeAgent owns authenticated secure download (`GET /rop/attachments/{attachment_id}/download`, safe manifest lookup, forced attachment + nosniff + no-store); UI-10 does not rendezvous raw content or create arbitrary file-serving routes - download link is safe internal link to BeeAgent-owned contract.

#### Deliverable

The operator sees which emails attachment-derived context were received, where extraction/refusal affected classification is required, and where attention is needed.

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
- raw content not exposed inline;
- UI remains artifact-only/read-only;
- safe BeeAgent-owned download links are rendered when the read-model provides them (authenticated forced-download contract from BeeAgent It40), never inline rendering;
- source artifacts remain traceable.

### Iteration UI-11 — ROP Bitrix reconciliation detail and filtering

**Status:** PLANNED

#### Goal

Supplement the existing Bitrix Evidence Board event-level reconciliation details, filters and Queue/Event Detail: link to show CRM entity, match quality, responsible, status and cause manual review.

#### Depends on

- UI-8 — final decision and Bitrix widget payload baseline;
- UI-8.3 — current canonical Queue and Event Detail baseline;
- UI-8.5 — embedded Bitrix widget/read-model baseline;
- UI-9 — BeeUI-only architecture;
- `BeeAgent It26 — Bitrix read-only reconciliation artifacts`.

#### Scope

**Includes:**

- Save the existing Bitrix Evidence Board and aggregate KPI;
- Add event-level reconciliation fields:
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
- Add filters on match status, quality, responsible and manual review;
- Add links between Queue, Bitrix tab and Event Detail;
- per-event reconciliation fields;
- matched/unmatched/duplicate/responsible/status/review filters;
- Queue and Event Detail integration;
- source artifact links;
- no Bitrix API call from UI;
- no CRM mutation;
- docs and tests update.

**Excluded:**

- CRM write-back;
- task creation;
- lead creation;
- manager scoring;
- automatic dedup merge;
- Bitrix auth setup UI;
- changes to `beeagent-rop`.

#### Deliverable

ROP dashboard shows CRM read-only reconciliation above artifacts without the manual opening of Bitrix JSON.

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

## Stage 3 — Stable backend API

### Iteration UI-12 — Stable BeeAgent Web API contract v1

**Status:** PLANNED

#### Goal

Stabilize JSON API contract for future separate frontend / standalone BeeUI / BeeConsole without implementing a separate frontend.

#### Depends on

- UI-8.5 — current HTML/API/widget route baseline;
- UI-9 — BeeUI-only route ownership;
- UI-10 and UI-11 must be either completed or explicitly excluded from v1 before API freeze.

#### Scope

**Includes:**

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

**Excluded:**

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

### Iteration UI-13 — Auth boundary duplicate

**Status:** RETIRED

#### Reason

The originally planned UI-13 auth scope is fully covered by UI-7. iteration.

UI-13 is removed from active plan and must not be reused to avoid creating drift in existing roadmap/Issue references.

---

## Stage 4 — Operator Control Panel

### Iteration UI-14 — Operator Web Control Panel v0

**Status:** PLANNED

#### Goal

Add the first bounded operator control panel for BeeAgent ROP flow: the operator sees the actions available, can start the clearly authorized read-only/draft-only actions through explicit backend action API, and every action taken or rejected creates audit artifact.

#### Depends on

- UI-7 auth boundary already completed and must be reused;
- UI-9 — BeeUI-only route ownership;
- UI-12 — stable BeeAgent Web API contract v1;
- existing BeeAgent backend action/case boundaries;
- existing ROP source, artifact and authority contracts.

#### Scope

**Includes:**

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
- Use the existing BeeUI CSRF boundary for each state-changing POST;
- Prohibit action execution without valid auth, role, CSRF, confirmation and server-side authority check;
- audit artifacts for every accepted/rejected action:

```text
storage/interfaces/operator_actions/<action_id>.json
```

- confirmation step;
- server-side auth/role/authority enforcement;
- no mailbox destructive action;
- no CRM write-back;
- docs update.

**Excluded:**

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

## Stage 5 — Admin/support surfaces

### Iteration UI-15 — Support/Admin diagnostics v0

**Status:** PLANNED

#### Goal

Add embedded support/admin diagnostics section to read audit/config/module/source diagnostics without a separate heavy admin platform.

#### Depends on

- UI-7 auth boundary;
- UI-14 action audit artifacts if action diagnostics are included.

#### Scope

**Includes:**

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

**Excluded:**

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

## Stage 6 — Deferred product/admin platform

### Iteration UI-16 — SQLAdmin evaluation for DB-backed admin only

**Status:** DEFERRED

#### Goal

Evaluate SQLAdmin only when BeeAgent introduces DB-backed entities such as users, tenants, projects, saved presets or review decisions.

#### Scope

Deferred until DB-backed models exist.

#### Not for immediate MVP

Current runtime source of truth is file-based artifacts and config, so SQLAdmin is not useful for the current ROP dashboard/control panel.

### Iteration UI-17 — Standalone BeeUI / separate frontend readiness

**Status:** DEFERRED

#### Goal

Prepare BeeAgent for future standalone BeeUI or separate frontend only after embedded BeeUI and stable API are proven.

#### Depends on

- UI-12 stable API contract;
- proven embedded BeeUI operation;
- explicit product need for a separate deployment or frontend.

#### Scope

**Includes later:**

- documented API routes;
- response examples;
- fixture payloads;
- error envelope examples;
- auth integration expectations;
- frontend/standalone dev notes.

**Not included now:**

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

For UI track, there is a rule:

- one UI-iteration = one coherent product increment;
- One implementation repository = one Issue = one target worktree/branch = one PR;
- If UI-iteration requires changes to BeeAgent and BeeUI, prepare a separate Issue and PR for each repository;
- cross-repository Issues must have explicit dependency and merge order;
- One `.agents/prompts/02-implementation-tests.md` launch only serves one Issue and one implementation target;
- Do not mix BeeUI migration, auth, dashboard-specific features, controls and frontend split in one task;
- Current future work: sequence
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

This document must be used together with:

- `docs/ROADMAP.md`;
- `docs/WEB_UI.md`;
- `docs/SDLC.md`;
- `docs/SECURITY.md`;
- `docs/DEV_GUIDE.md`;
- `README.md`;
- BeeUI docs:
  - `beeui/docs/ROADMAP.md`;
  - `beeui/docs/INTEGRATION.md`;
  - `beeui/docs/API_CONTRACT.md`;
  - `beeui/docs/WEB_UI.md`;
  - `beeui/docs/COMPONENTS.md`.
