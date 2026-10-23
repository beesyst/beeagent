# ROADMAP – beeagent (SDLC-light, iteration development)

## Purpose

This document records the development route of `beeagent` by stages and iterations.

ROADMAP in the project is used as lightweight SDLC-artifact:

- Sets the direction of development;
- Notes the purpose of each iteration;
- Determines expected behaviour, artifacts and checks;
- helps link Issue → Code → Tests → Artifacts → PR → Merge.

ROADMAP does not replace Issue and PR:

- **Issue** explains exactly what needs to be done in the task;
- **PR** records what was actually done and how it was verified;
- **ROADMAP** shows where the project is going and what is considered ready by iteration.

Iteration closes through PR: and PR is the main location where verification evidence, checks, artifacts and limits of implementation are recorded.

ROADMAP does not duplicate complete process and safety rules:

- The development process and the criteria for change are described in `docs/SDLC.md`;
- secure development rules and security checks are described in `docs/SECURITY.md`.

## Vision

| Block                          | Statement                                                                                                                                                                                                   |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Product identity**           | `beeagent` is developed as explainable, stateful, modular AI orchestration system with visible operator / interface layers, module contracts and reproducible runtime artifacts.                                  |
| **Primary objective**          | The objective of the project is not to be a chit-bot with tulus, but to be managed by a core agent who outlines tasks, modules, approvals, artifacts and external workflow/capabilities.                                      |
| **Execution philosophy**       | The long task, state, batching, retry, checkpoints and policy must live in `beeagent`, not within one MCP/tool call.                                                                                  |
| **Source of truth**            | Runtime behavior must be determined through `config/settings.yml`, clear validation, stable contracts and reproducible artifacts.                                                                            |
| **Decision quality principle** | Any meaningful decision or action must be explained by the logs, config and artifacts.                                                                                                                     |
| **Module principle**           | Business logic must live in separate domain modules (`beeagent-rop`, future `beescan`, `merch`), and core must remain universal.                                                                |
| **Capability principle**       | MCP / n8n / external systems is execution/integration layer rather than domain logic.                                                                                                       |
| **Operator principle**         | The system must be suitable for safe operation through simple UI/transport layers and must not require hidden knowledge of the code.                                                                                 |
| **Product direction**          | Development follows a trajectory: demo skeleton → reusable orchestration core → module platform → first real client module → pilot-ready operator shell → scalable multi-module platform.                        |
| **AI direction**               | AI is allowed only as bounded assistive layer: classification, summarization, recommendation, intent drafting. AI must not replace deterministic contracts, policy, approval and authority boundaries. |
| **KISS rule**                  | New possibilities are added only if they reinforce orchestrator, explainability, reusability, module integration or operator usability without swelling core.                                           |
| **Security rule**              | Secrets, connectors, file parsing, capability execution and artifact contracts only develop through explicit config, fail-fast validation and proportional checks under `docs/SDLC.md` and `docs/SECURITY.md`.   |
| **Interface rule**             | Any agent-facing / operator-facing surface must be read-only or draft-only by default, and execution-capable path must be explicit and bounded.                                                    |
| **Execution authority rule**   | Any execution-capable path must develop through the minimum necessary rights, capability-scoped boundaries and the explicit operator-visible contract.                                                         |

## Development principles

Make small iteration. Each iteration must:

- start with `start.sh` or the corresponding CLI entrypoint;
- write understandable logs;
- Leave the reproducible artifacts in `storage/`, if the task is to do so;
- Do not break the `beeagent_module` package structure;
- Use `config/settings.yml` as a source of truth;
- Validate new mandatory fail-fast keys;
- close through Issue / PR / tests / artifacts;
- pass required quality/security checks from `docs/SDLC.md` and `docs/SECURITY.md`, depending on the type of change;
- Save explicit authority boundary: read-only, draft-only and execution-capable tracks must be clearly separated and verified.

For `beeagent`, this means:

- low-risk changes are made to the basic checks;
- runtime-risk and security-sensitive modifications require enhanced verification;
- The verification level is defined by `docs/SDLC.md` and `docs/SECURITY.md`, rather than ad hoc.

## SDLC workflow for roadmap items

Each iteration must be run over a simplified cycle:

1. **Planning** Iteration described in ROADMAP and described as Issue.

2. **Requirements** For iteration scope, deliverable, artifacts, checks and DoD.

3. **Implementation** Changes are made in a separate branch and only within the current iteration.

4. **Verification** Tests, smoke-check, lair and artifacts, as well as required quality/security checks for the type of change are performed.

5. **Review / PR** PR records changes, tests, artifacts and restrictions.

6. **Merge** Iteration is considered completed after DoD.

## Status values

Allowable iteration status:

- **PLANNED** — planned
- **IN PROGRESS** - Work
- **DONE** Completed
- **DONE (partial)** partially completed, there are conscious restrictions

## Roadmap item format

The historical iteration status `DONE` preserves the existing structure and does not rewrite it in the back for formatting purposes only.

The new iteration and materially refined uncompleted iteration use a compact structure:

- `Goal`
- `Scope`
- `Excluded`
- `Deliverable`
- `Acceptance criteria`
- `Checks`
- `DoD`

ROADMAP captures iteration-level contract.

Detailed implementation requirements, specific files complete payload examples, extended test matrices and verification evidence owned by Issue, implementation handoff and PR.

## Global Definition of Done

Iteration must be considered completed if:

- behavior was verified within the declared scope;
- The new mandatory keys are read from `config/settings.yml`;
- Validation for new mandatory keys added to `src/beeagent_module/core/settings.py`;
- feature operates through the expected entrypoint;
- The logs are recorded;
- artifacts is created where it is expected;
- The tests and manual checks have been carried out;
- required quality/security checks of `docs/SDLC.md` and `docs/SECURITY.md` have been completed;
- Secrets do not enter the logs and artifacts;
- ROADMAP / docs updated when the contract, behavior or artifacts. changed

## Change levels for verification

For lightweight SDLC, the project uses three levels of change:

- **low-risk** — docs, local tests, cosmetics and safe changes without affecting runtime- contract;
- **runtime-risk** — changes in orchestrator/runtime/config validation/artifacts/reporting/CLI/module loading/case dispatch affecting runtime behavior or reproducibility artifacts;
- **security-sensitive** – secrets/env handling, external capabilities, MCP/tool boundaries, file parsing, dependency surface, serialization/deserialization, file/path handling, authority paths and other changes to trust boundary.

For each level, the obligation quality/security checks is defined in:

- `docs/SDLC.md`
- `docs/SECURITY.md`

## Product phases

| Phase                                     | Status      | What it means                                                                                                                                                                                |
| ----------------------------------------- | ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Phase A — Demo skeleton**               | DONE        | A demonstration runtime: Telegram transport, mock data and basic agents/cases, run artifacts, approval, export. have been created                                                                  |
| **Phase B — Reusable orchestration core** | DONE        | BeeAgent stopped being just a demo and got reusable cases/adapters/scheduler/observability/multi-agent baseline.                                                                    |
| **Phase C — Module platform**             | DONE        | Introducing the explicit module contract, registry, runtime context, artifact API and bounded capability layer for external domain modules.                                                             |
| **Phase D — First real client delivery**  | DONE        | The first real domain module (`beeagent-rop`) is integrated; implemented by controlled source flow, operator artifacts, read-only Bitrix evidence and bounded AI adjudication for ROP MVP.      |
| **Phase E — Operator / product shell**    | IN PROGRESS | Read-only BeeUI-backed operator shell, auth boundary, ROP dashboard and widget payload baseline have been implemented; stable API, legacy web removal and bounded operator controls remain in UI roadmap. |
| **Phase F — Multi-module platform**       | FUTURE      | BeeAgent becomes the base for several domain modules (`ROP`, `BeeScan`, `Merch`, etc.) with a single runtime and reusable contracts.                                                           |

## Stages

- **Stage 1 (Iterations 0-4)** pre-MVP framework + launch + transport + mock/demo flow.
- **Stage 2 (Iterations 5-10)** reusable core: cases/adapters/scheduler/observability/multi-agent + quiz + explainable recommendations.
- **Stage 3 (Iterations of 11-14)** module platform v0 (module contract, registry, context, artifact API, capability boundary).
- **Stage 4 (Iterations 15-36)** Integration of the first real domain module (`beeagent-rop`) and development of ROP flow to read-only customer-delivery MVP with source ingestion, artifacts, Bitrix evidence and bounded AI adjudication.
- **Stage 5 (reference):** remaining core-side operator/product contracts; The detailed development of Web Console and operator UI is carried out in `docs/product/ui_roadmap.md`.
- **Stage 6 (reference):** multi-module scaling (`beescan`, `merch`, other modules).

---

## Stage 1 — Pre-MVP (iteration 0–4)

### Iteration 0 — Skeleton and startup (skeleton)

**Status:** DONE

#### Goal

Raise the minimum design frame and the single entrypoint launch.

#### Scope

Includes:

- Basic structure of the project;
- Launch through `start.sh`;
- loading env and settings;
- basic logging;
- The creation of `logs/` and `storage/`.

Not included:

- Real data;
- complex orchestration logic;
- The modular platform.

#### Implemented

- `start.sh` → starts `python3 config/start.py`
- `config/start.py` → upload env + settings + single mode launch (`telegram`)
- `src/beeagent_module/` → a package with the project structure was created
- `beeagent_module/core/log.py` → logging (`stdout + logs/app.log`)
- `beeagent_module/core/paths.py` → paths to `logs/` and `storage/`
- `beeagent_module/core/settings.py` → loading `settings.yml` + fail-fast validation
- `storage/` and `logs/` are created automatically

#### Deliverable

The project is launched through a single entrypoint and writes basic logs.

#### Artifacts

- `logs/app.log`
- `storage/`

#### Checks

- `bash start.sh`
- `pytest -q`

#### DoD

- the project starts without crashing;
- Logging included;
- The directory is created automatically.

### Iteration 1 - Telegram bot v0 (UX skeleton)

**Status:** DONE

#### Goal

Give minimum transport/UI layer through Telegram.

#### Scope

Includes:

- `/start`, `/help`, plus legacy demo report commands command;
- inline- buttons;
- allowlist.

Not included:

- multi-channel UI;
- complex session routing logic.

#### Implemented

- Commands: `/start`, `/help`, plus legacy demo report commands
- inline- buttons: `Run OOS Scan`, `Show Report`
- allowlist (one `chat_id` in config)

#### Deliverable

Telegram transport operates as thin demo/operator layer.

#### Artifacts

- `storage/telemetry/telegram_updates.jsonl` (optional)

#### Checks

- `bash start.sh`
- smoke in Telegram

#### DoD

- the bot starts and responds;
- The menu and buttons are working;
- an unknown command does not crash runtime.

### Iteration 2 - Mock data v0 + domain model

**Status:** DONE

#### Goal

Prepare reproducible mock dataset and basic domain models.

#### Scope

Includes:

- `domain/` models;
- mock data generator;
- mock dataset parameters in `config/settings.yml`.

Not included:

- Real integration;
- customer domain modules.

#### Implemented

- demo flow domain models
- mock dataset: generator
  - 3 stores
  - 1 category
  - 10–30 SKU
  - 4-12 data weeks
  - forced anomalies
- mock dataset in `config/settings.yml`

#### Deliverable

Demo- agents can work on reproducible data.

#### Artifacts

- `storage/mock/<dataset_id>/dataset.json`

#### Checks

- `pytest -q`
- mock generation smoke

#### DoD

- The same seed gives the same result;
- mock dataset is created and read by one function;
- demo scan command creates dataset artifact.

### Iteration 3 — LangGraph workflow v0 (OOS detector, dry-run)

**Status:** DONE

#### Goal

Start end-to-end workflow via LangGraph and Telegram. report

#### Scope

Includes:

- collect_input
- load_data
- detect_oos
- draft_tasks
- render_report
- persist_run

Not included:

- reusable module platform;
- real data integrations.

#### Implemented

- end-to-end OOS workflow through LangGraph
- run persistence
- Telegram report output

#### Deliverable

There's end-to-end run path with artifacts.

#### Artifacts

- `storage/runs/<run_id>/run.json`
- `storage/runs/<run_id>/alerts.json`
- `storage/runs/<run_id>/tasks_draft.json`

#### Checks

- `bash start.sh`
- demo scan command
- artifact inspection

#### DoD

- demo scan command creates `run_id`, writes artifacts and returns the report;
- empty data scenario must be processed without falling.

### Iteration 4 — Approval v0 + export

**Status:** DONE

#### Goal

Add approval path and export report.

#### Scope

Includes:

- approve / reject;
- draft/approved/rejected status;
- report export.

Not included:

- execution authority beyond demo tasks;
- operator shell.

#### Implemented

- `Approve Tasks` / `Reject` buttons
- Status of tasks: `draft / approved / rejected`
- export report:
  - `report.md`
  - `report.html`

#### Deliverable

There's a minimum operator loop: draft → approve/reject → export artifacts.

#### Artifacts

- `storage/runs/<run_id>/tasks_approved.json`
- `storage/artifacts/<run_id>/report.md`
- `storage/artifacts/<run_id>/report.html`

#### Checks

- `pytest -q`
- approve/reject smoke

#### DoD

- approve/reject retained and visible through `/last`;
- without approve the tasks are not considered ready.

---

## Stage 2 — Reusable core (iteration 5–10)

### Purpose of stage

Stage 2 makes `beeagent` not just demo-bot, but reusable orchestration core with UI, case- layers, adapter boundary, observability and several agency scenarios.

Stage focus:

- `cases/*` as application layer;
- `adapters/*` as data boundary;
- scheduler;
- basic observability;
- multi-agent baseline;
- richer user-facing demo paths (`quiz`, explainable recommendations).

By default, this step changes:

- mainly `runtime-risk`;
- transport / file / state handling changes may be `security-sensitive`.

### Iteration 5 — Cases layer v0 + Data Adapter v0

**Status:** DONE

#### Goal

Unlink UI from storage and graph. UI parts to `cases/*`, the graph reads the data via `adapter` only.

#### Scope

Includes:

- `cases/*`;
- `DataAdapter`;
- `MockAdapter`;
- graph uses adapter;
- `data.adapter` in config.

Not included:

- external modules;
- real data integrations.

#### Implemented

- `src/beeagent_module/cases/`
- `cases/oos.py`
- UI no longer reads `storage/runs/*` directly
- `DataAdapter` interface
- `MockAdapter`
- `load_data` node transferred to `adapter.*`
- `data.adapter: "mock"` in config

#### Deliverable

Cases becomes stable application layer, and data boundary becomes apparent.

#### Artifacts

- `storage/runs/<run_id>/run.json` with `adapter` and `trigger`

#### Checks

- `pytest -q`
- transport → case smoke
- adapter-based run smoke

#### DoD

- Telegram-bot works as it used to, but does not read storage directly;
- The graph receives the data via adapter;
- One key `data.adapter` selects the adapter.

### Iteration 6 — Scheduler v0 + mandatory Approval gate

**Status:** DONE

#### Goal

Add controlled periodic run path.

#### Scope

Includes:

- simple scheduler loop;
- scheduled runs;
- mandatory approval gate.

Not included:

- cron/apscheduler;
- distributed background jobs.

#### Implemented

- `scheduler.enabled`
- `scheduler.interval`
- `scheduler.start_run`
- scheduled-run tasks always remain `draft`
- The bot sends a message to approve/reject

#### Deliverable

There's an auto launch without bypassing approval boundary.

#### Artifacts

- `storage/runs/<run_id>/run.json` with `trigger=scheduled|manual`

#### Checks

- scheduler smoke
- draft-only verification
- approve/reject smoke

#### DoD

- At `scheduler.enabled` the bot creates run at intervals;
- without approve, tasks remain draft;
- approve/reject works for the last run.

### Iteration 7 – Mini-observability v0 (timing steps)

**Status:** DONE

#### Goal

See the length of each node and save trace.

#### Scope

Includes:

- `duration_ms` per step;
- step logs;
- `steps.json`.

Not included:

- external tracing platform;
- distributed tracing.

#### Implemented

- step timing in logs
- `storage/runs/<run_id>/steps.json`

#### Deliverable

There's a base observability on workflow. steps.

#### Artifacts

- `storage/runs/<run_id>/steps.json`

#### Checks

- `pytest -q`
- run artifact inspection

#### DoD

- after run appears `steps.json`;
- timing steps are being reproduced.

### Iteration 8 – 2- agent v0 + multi-channel UI readiness

**Status:** DONE

#### Goal

Show platform expansion: new agent = new `cases/*` + `agents/*` + button/team in UI.

#### Scope

Includes:

- Second agent (`promo`);
- Same run/artifact pattern;
- UI readiness docs / stubs.

Not included:

- real second transport integration;
- external modules.

#### Implemented

- `agents/promo/graph.py`
- `cases/promo.py`
- `/run_promo`
- `Run Promo Scan` button
- `ui/slack_stub.py`
- doc contract `UI → cases → agents/adapter/storage`

#### Deliverable

BeeAgent shows reusable multi-agent pattern.

#### Artifacts

- standard run artifacts per agent

#### Checks

- `pytest -q`
- multi-agent smoke

#### DoD

- The second agent starts end-to-end;
- artifacts is created by the same standard;
- transport/case/agent boundary recorded in docs.

### Iteration 9 — Quiz Agent v0 (Pharmacy demo) + WOW UX

**Status:** DONE

#### Goal

Make demo-case: user input → quiz flow → result → artifacts. more interactive

#### Scope

Includes:

- quiz case;
- quiz graph;
- session storage;
- Telegram quiz UX;
- quiz artifacts.

Not included:

- product-grade survey engine;
- multi-tenant quiz platform.

#### Implemented

- `cases/quiz.py`
- `agents/quiz/graph.py`
- `config/quiz/pharmacy_quiz.json`
- `storage/sessions/<chat_id>.json`
- `/quiz_pharmacy`
- `/last_quiz`
- quiz run artifacts

#### Deliverable

There's stateful interactive scenario inside BeeAgent runtime.

#### Artifacts

- `storage/runs/<run_id>/run.json`
- `storage/runs/<run_id>/quiz_answers.json`
- `storage/runs/<run_id>/quiz_result.json`
- `storage/artifacts/<run_id>/report.md`
- `storage/artifacts/<run_id>/report.html`
- `storage/runs/<run_id>/steps.json`

#### Checks

- `bash start.sh`
- full quiz flow
- `pytest -q`

#### DoD

- `/quiz_pharmacy` triggers the quiz and passes to the result;
- sessions and run artifacts retained;
- `/last_quiz` shows the last result.

### Iteration 10 — Explainable Recommendations v0 + LLM summary

**Status:** DONE

#### Goal

Demonstrate a “real AI- agent” with minimal scope: Explainable Recommendations + optional LLM summary.

#### Scope

Includes:

- deterministic recommendation engine;
- LLM summary only for text;
- trace extension;
- recommendation artifacts.

Not included:

- AI-driven execution;
- black-box decision making.

#### Implemented

- recommendation engine over OOS results
- structured recommendations:
  - action
  - reason
  - metrics
  - expected_effect
  - confidence
- LLM summary with fallback
- workflow steps:
  - `build_recommendations`
  - `llm_explain`
- recommendation artifacts

#### Deliverable

BeeAgent can deliver explainable recommendation output over deterministic core.

#### Artifacts

- `storage/runs/<run_id>/recommendations.json`
- `storage/artifacts/<run_id>/report.md`
- `storage/artifacts/<run_id>/report.html`
- `storage/runs/<run_id>/steps.json`

#### Checks

- `bash start.sh`
- demo scan command
- fallback LLM off
- `pytest -q`

#### DoD

- demo scan command reports with recommendations;
- recommendation artifacts is created;
- trace and logs are extended to recommendation path.

---

## Stage 3 — Module platform v0 (iteration 11–14)

### Purpose of stage

Stage 3 turns `beeagent` from a demo/core- skeleton into a modular platform that accepts client domain packages as separate repositories.

Stage focus:

- Visible module contract;
- module registry;
- runtime context/artifact API;
- capability boundary;
- Preparation for `beeagent-rop`.

By default, this step changes:

- mainly `runtime-risk`;
- module loading / capability / file boundary changes — `security-sensitive`.

### Iteration 11 — Module contract v0

**Status:** DONE

#### Goal

Record the minimum internal contract of a module through which BeeAgent core can operate safely and predictably with external domain packages such as `beeagent-rop`.

#### Scope

Includes:

- `ModuleContract` / protocol as internal reusable contract;
- Mandatory `module_id`;
- `supported_case_types()`;
- `handle(context)` with minimum contract-level context shape;
- bounded result shapes for the response of the module;
- Visible contract metadata for `read-only / draft-only / execution-capable` semantics;
- import / dispatch smoke at contract level;
- docs update on module boundary and contract expectations.

Not included:

- module registry / discovery;
- remote loading;
- marketplace;
- hot reload;
- A full runtime context API;
- artifact API;
- capability execution layer;
- Real integration of `beeagent-rop`.

#### Deliverable

`beeagent` provides a clear and tested internal contract for a module independent of one customer and sufficient for the following registry/context/integration. iterations.

#### Artifacts

- docs
- tests
- optional contract diagnostics artifact only if is really needed.

#### Checks

- `pytest -q`
- contract import smoke
- contract dispatch smoke
- manual log check if runtime path touched

#### DoD

- core clearly knows what the contract modular looks like;
- contract is not tied to `beeagent-rop` or another one customer;
- authority semantics (`read-only / draft-only / execution-capable`) is clearly expressed;
- bounded result shape must be tested;
- transport/case/core paths does not break.

### Iteration 12 — Module registry v0

**Status:** DONE

#### Goal

Add a minimum local registry through which BeeAgent can clearly and predict the location, validation and connection of package-based modules such as `beeagent-rop`.

#### Scope

Includes:

- local registry for installed python packages;
- config-driven module declaration;
- config-driven enable/disable modules;
- deterministic active module resolution;
- import + contract validation against `ModuleContract`;
- explicit refusal for missing / disabled / invalid modules;
- diagnostics at loaded / disabled / missing / invalid modules;
- conflict handling for ambiguous module ownership if applicable;
- optional registry diagnostics artifact.

Not included:

- remote registry;
- dynamic marketplace;
- hot reload;
- arbitrary filesystem scanning;
- container orchestration;
- runtime context API;
- artifact API;
- capability boundary;
- real client flow dispatch beyond registry-level smoke.

#### Implemented

- `src/beeagent_module/core/module_registry.py` — `ModuleRegistry`, `ModuleEntry`, `ModuleState`, `build_registry`
- `config/settings.yml` – `modules.registry` (config-driven declaration) block
- `src/beeagent_module/core/settings.py` - fail-fast validation of `modules.*` and each registry element
- `src/beeagent_module/core/app.py` – `build_registry` call at launch
- `tests/test_module_registry.py` – Scenarios: loaded, missing, disabled, invalid, diagnostics artifact, mixed
- `beeagent-rop` announced in registry; the current `RopModule` does not satisfy `ModuleContract` (no `authority`) → state=invalid (expected until iteration 15)

#### Deliverable

BeeAgent can clearly identify locally installed modules, load the valide module, fail explainably in the case of missing/disabled/invalid module and show registry diagnostics.

#### Artifacts

- `storage/interfaces/modules.json` (always-on registry diagnostics artifact)

#### Checks

- registered module scenario — `test_registry_registered_module`
- missing module scenario — `test_registry_missing_module`
- disabled module scenario — `test_registry_disabled_module`
- invalid contract scenario — `test_registry_invalid_contract`
- diagnostics artifact — `test_registry_diagnostics_artifact`
- `uv run pytest -q`
- smoke run
- log verification
- diagnostics artifact verification

#### DoD

- The active module is clearly and predictable;
- module loading is not based on hidden defaults or ad hoc imports;
- missing / disabled / invalid module give explainable error/diagnostics;
- registry semantics is not tied to one customer;
- BeeAgent is prepared for the following iteration runtime context and `beeagent-rop` integration.

### Iteration 13 — Runtime context + artifact API v0

**Status:** DONE

#### Goal

Give the module the minimum safe runtime context and the standard core-managed method to write module-linked artifacts without direct dependence on private internals BeeAgent.

#### Scope

Includes:

- minimal runtime context envelope for module execution;
- `run_id`, `session_id`, `case_type`, `module_id`, `authority`, input payload;
- explicit context propagation from core to module;
- minimal artifact write/read API under core control;
- safe storage path contract for module-linked artifacts;
- standard linkage `run -> module outputs`;
- predictable module artifact location and naming rules;
- tests for context propagation and artifact API behavior.

Not included:

- distributed state store;
- queue framework;
- external DB as source of truth;
- broad storage abstraction platform;
- capability layer;
- full client flow dispatch;
- real production integration with external systems.

#### Deliverable

The module can be run inside BeeAgent runtime with platform-owned context and write module-linked artifacts via explicit core API, without knowing private storage internals.

#### Artifacts

- standard run artifacts
- module-linked artifacts
- optional diagnostics if needed for context/artifact verification

#### Checks

- `pytest -q`
- context propagation smoke
- artifact API smoke
- manual log verification
- manual artifact verification

#### DoD

- The module receives explicit runtime context from core;
- The module writes artifacts through core-managed API, not directly into arbitrary routes;
- linkage `run_id -> module artifacts` is reproducible and understandable by logs/artifacts;
- The decision is not tied to one client and does not carry capability logic before the time.

### Iteration 14 — Capability boundary v0

**Status:** DONE

#### Goal

Segregate module logic and external data/action calls through a single capability layer so that domain modules like `beeagent-rop` can request email / Bitrix / parser / attachment capabilities without direct dependence on transport details, MCP/n8n/system clients and without dilution authority boundaries.

#### Scope

Includes:

- capability call abstraction in core;
- minimal capability request / response contract v0;
- clear boundary `module → capability → MCP/n8n/system`;
- mock/local capability provider for tests;
- explicit result states:
  - `ok`
  - `refused`
  - `timeout`
  - `error`
- explicit refusal / timeout / degraded surface;
- authority-aware capability semantics:
  - `read_only`
  - `draft_only`
  - `execution_capable`
- capability examples aligned with ROP Discovery:
  - `email.search`
  - `email.read`
  - `bitrix.find_lead`
  - `bitrix.read_timeline`
  - `parser.lookup_email`
  - `attachment.extract_text`
- Prohibition of hidden fallback execution path;
- principle: long-running state, retry, batching, checkpoints and policy remain in BeeAgent;
- logs / optional diagnostics for explainability.

Not included:

- production Email connector;
- production Bitrix connector;
- production parser connector;
- production attachment reader/OCR;
- full MCP/n8n transport implementation;
- full workflow engine rewrite;
- Transport long-running state to n8n/MCP/tool layer;
- ad hoc tool/API calls directly from client module logic;
- client-specific ROP business rules in BeeAgent core.

#### Deliverable

BeeAgent receives the minimum capability boundary v0: module can call capability through core-owned abstraction and receive explainable `ok/refused/timeout/error` result without transport details knowledge and without direct access to the outer systems.

#### Artifacts

- logs
- optional `storage/interfaces/capabilities.json`
- tests

#### Checks

- `pytest -q`
- mock capability call scenario
- refusal scenario
- timeout scenario
- unknown capability scenario
- authority boundary scenario
- no hidden fallback scenario
- smoke run
- log verification
- optional diagnostics verification

#### DoD

- module code is not tied directly to the random tool transport;
- capability calls only passes through explicit core abstraction;
- refusal / timeout / error paths explainable on logs/tests;
- hidden fallback execution path is missing;
- long-running state does not leave in n8n/MCP/tool layer;
- The decision is not tied to `beeagent-rop`, but covers future ROP capability needs.

---

## Stage 4 — First real client module integration

### Purpose of stage

Stage 4 connects the first real client module `beeagent-rop` and brings BeeAgent to a condition suitable for Discovery → MVP → Pilot to a particular client.

Stage focus:

- integration of `beeagent-rop`;
- run/session/artifact linkage;
- bounded operator flow;
- client delivery readiness.

By default, this step changes:

- mainly `runtime-risk`;
- capability/file/integration boundaries — `security-sensitive`.

### Iteration 15 — `beeagent-rop` integration smoke v0

**Status:** DONE

#### Goal

Connect `beeagent-rop` to BeeAgent core as the first real external domain module and confirm end-to-end dispatch via registry, runtime context and artifact API.

#### Scope

Includes:

- loading `beeagent-rop` via `modules.registry`;
- Check that registry no longer marks `beeagent-rop` as `invalid`;
- ROP module dispatch through existing core runtime path;
- context passing: `run_id`, `session_id`, `case_type`, `module_id`, `authority`, `payload`;
- artifact linkage through `ArtifactAPI`;
- integration smoke with local package installed;
- registry/runtime diagnostics in logs/artifacts;
- The minimum sample payload for `lead_classification` or `duplicate_resolution`.

Not included:

- production Bitrix connector;
- production email connector;
- n8n/MCP transport implementation;
- attachment deep parsing;
- ROP summary/operator UX;
- pilot hardening;
- Change in business logic `beeagent-rop`;
- client-specific rules in BeeAgent core.

#### Deliverable

BeeAgent can load and call `beeagent-rop` as first real module through the standard registry/runtime path and the result of the call is reproduciblely linked to `run_id` in module-linked artifacts.

#### Artifacts

- `storage/interfaces/modules.json`
- `storage/runs/<run_id>/module-beeagent-rop/module_result.json`
- optional module output artifact from `beeagent-rop`
- `logs/app.log`

#### Checks

- `uv run pytest -q`
- registry integration smoke with installed `beeagent-rop`
- module dispatch smoke via `execute_module_case`
- artifact linkage verification
- log verification
- no secret leakage check

#### DoD

- `beeagent-rop` is loaded as valid module through registry;
- BeeAgent calls `beeagent-rop` end-to-end without hand crutches;
- `ModuleResult` passes through consistency checks in `execute_module_case`;
- linkage `run_id -> module-beeagent-rop -> module_result.json` is visible in artifacts;
- BeeAgent core does not contain ROP-specific business logic;
- production connectors is not connected or summoned.

### Iteration 16 — ROP operator run flow v0

**Status:** DONE

#### Goal

Gather the first comprehensible operator-facing flow for `beeagent-rop` launch through BeeAgent core: the operator must not only see raw module artifacts but also the short explainable output without reading the originals or the inside JSON.

#### Scope

Includes:

- core/case-level launch ROP module through the existing registry/runtime path;
- operator-facing wrapper over `execute_module_case(...)`;
- bounded input payload for the first ROP case smoke, without production connectors;
- readable summary output based on `ModuleResult`;
- artifact linkage:
  - `run_id`;
  - `module_result.json`;
  - operator summary artifact;
- basic degraded output if the module is not loaded, case unsupported or module result is not `ok`;
- Minimum integration with the current UI/transport path where it is already natural for the project;
- tests on successful run and degraded/refusal scenario.

Not included:

- final UI;
- production Email/Bitrix/parser/attachment connectors;
- auto actions in CRM;
- Full ROP business summary;
- recommendation builder;
- manager scoring;
- transport ROP business logic to BeeAgent core.

#### Deliverable

BeeAgent gains its first operator-ready ROP run flow: the installed `beeagent-rop` can run through a core-level path, returning a readable summary and reproducible artifacts sufficient to demonstrate the MVP path to the customer.

#### Artifacts

- `storage/runs/<run_id>/module-beeagent-rop/module_result.json`
- `storage/runs/<run_id>/module-beeagent-rop/<case_type>_result.json`, if the module writes case artifact
- `storage/runs/<run_id>/operator_summary.json` or similar to operator-facing artifact
- logs

#### Checks

- `pytest -q`
- targeted ROP operator flow tests
- run smoke with installed `beeagent-rop`
- degraded scenario: module missing / unsupported case / non-ok result
- manual artifact inspection
- log verification

#### DoD

- ROP flow is launched through BeeAgent-owned path, not ad hoc script;
- operator-facing summary explains what happened, what module/case was caused, what status was received and where artifacts is located;
- linkage `run_id -> module result -> operator summary` reproducible;
- BeeAgent core does not contain ROP business rules;
- production connectors and CRM actions are not added.

### Iteration 17 — ROP input source contract and batch handoff v0

**Status:** DONE

#### Goal

Add to BeeAgent the first platform-level contract ROP input source and batch/operator handoff flow so that `beeagent-rop` will run through core on controlled batch input instead of on demo payload. single.

#### Scope

Includes:

- config-driven ROP input source contract:
  - `rop.sources`;
  - `source_id`;
  - `source_type`;
  - `enabled`;
  - `authority`;
  - `items_max`;
  - source-specific settings without secrets;
- First safe source type:
  - `json_batch` (source_type value);
- controlled sample batch file for dev/smoke;
- loading batch payload from configured source;
- validation of batch shape;
- Normalization of batch items in payload, compatible with `beeagent-rop`;
- Launch `beeagent-rop` through the existing `ModuleRegistry` / `execute_module_case`;
- Main MVP case:
  - `rop_summary` if the module supports;
- fallback/degraded behavior:
  - missing source;
  - no enabled source;
  - multiple enabled sources if v0 allows only one;
  - disabled source;
  - invalid source config;
  - missing batch file;
  - invalid batch shape;
  - missing module;
  - unsupported case type;
  - module non-ok result;
- artifacts:
  - `intake_metadata.json`;
  - `normalized_events.json`;
  - module artifacts;
  - `operator_summary.json`;
- Telegram command or dev/operator path, if this is minimal and does not blow scope up;
- README / DEV_GUIDE / ROADMAP update.

#### Not included:

- IMAP/live mailbox connector;
- `hotline@welding.kz` live access;
- stream/listener;
- production Bitrix/email/1C connectors;
- CRM write-back;
- OCR;
- attachment deep parsing;
- ROP classification/summary/recommendation rules in BeeAgent;
- hardcoded client mailbox;
- broad multi-client abstractions.

#### Deliverable

BeeAgent can launch ROP flow through configurable batch input source and release operator-facing summary with reproducible artifacts without live mailbox dependency.

#### Artifacts

- `storage/runs/<run_id>/intake_metadata.json`
- `storage/runs/<run_id>/normalized_events.json`
- `storage/runs/<run_id>/module-beeagent-rop/module_result.json`
- optional `storage/runs/<run_id>/module-beeagent-rop/rop_summary_result.json`
- `storage/runs/<run_id>/operator_summary.json`
- `storage/interfaces/modules.json`

#### Checks

- `uv run pytest -q`
- targeted ROP source/batch tests
- batch handoff smoke with installed `beeagent-rop`
- degraded/failure scenarios
- manual artifact inspection
- log verification
- no secret leakage check
- SAST mindset review

#### DoD

- source is not studded;
- BeeAgent does not contain ROP classification/summary/recommendation rules;
- source contract is read from config and validated by fail-fast;
- module is called through existing module runtime path;
- `rop_summary` batch smoke passes;
- artifacts is reproducible and understandable;
- degraded paths explainable;
- logs/artifacts does not contain secrets;
- production connectors not added.

### Iteration 18 — ROP mailbox_readonly source and hotline smoke v0

**Status:** DONE

#### Goal

Add to BeeAgent source type `mailbox_readonly` and use `hotline@welding.kz` as the first configurable read-only mailbox source for ROP MVP smoke: BeeAgent must receive the last N letters, safely normalize them into events, call `beeagent-rop` via existing module runtime path and write operator-facing artifacts without destructive mailbox actions and without CRM write-back.

#### Scope

**Includes:**

- new source type:
  - `mailbox_readonly`;
- config-driven source declaration in `rop.sources`;
- `hotline` only as `source_id` / config entry, without a hard code in runtime logic;
- mailbox config without secrets:
  - `host`;
  - `port`;
  - `use_ssl`;
  - `folder`;
  - `username_env`;
  - `password_env`;
  - `items_max`;
- credentials only after env;
- read-only fetch of the last N messages;
- no delete/archive/reply/mark-as-read;
- minimal mailbox adapter with fake mailbox tests;
- normalizer:
  - sender;
  - recipients / cc, if safe;
  - subject;
  - date/message_id;
  - text/plain or safe text body preview;
  - attachment metadata only without reading content;
- sanitized artifacts:
  - `source_diagnostics.json`;
  - `intake_metadata.json`;
  - `normalized_events.json`;
  - module artifacts;
  - `operator_summary.json`;
- dispatch in `beeagent-rop` through `execute_module_case(...)`;
- degraded behavior:
  - missing credentials;
  - invalid source config;
  - auth failure;
  - mailbox unavailable;
  - empty inbox;
  - malformed message;
  - unsupported module/case;
  - module non-ok result;
- docs update.

#### Not included:

- continuous stream/listener/polling;
- checkpoint/seen-message persistence if this is not minimal and safe;
- multi-mailbox routing;
- full source-of-truth mapping;
- employee mailbox ingestion;
- Bitrix/1C connectors;
- CRM write-back;
- OCR;
- attachment deep parsing;
- saving raw `.eml`;
- automatic mailbox actions;
- n8n/MCP implementation;
- ROP business rules in BeeAgent.

#### Deliverable

BeeAgent can perform controlled read-only smoke on mailbox source: receive the last N letters from configured mailbox, normalize them to ROP-compatible events, call `beeagent-rop` and show operator summary with reproducible artifacts.

#### Artifacts

- `storage/runs/<run_id>/source_diagnostics.json`
- `storage/runs/<run_id>/intake_metadata.json`
- `storage/runs/<run_id>/normalized_events.json`
- `storage/runs/<run_id>/module-beeagent-rop/module_result.json`
- optional `storage/runs/<run_id>/module-beeagent-rop/rop_summary_result.json`
- `storage/runs/<run_id>/operator_summary.json`
- `logs/app.log`

#### Checks

- `uv run pytest -q`
- mailbox adapter tests with fake mailbox
- missing credentials scenario
- auth failure scenario
- mailbox unavailable scenario
- empty inbox scenario
- malformed message scenario
- live smoke with `items_max`, if actual credentials is available
- manual artifact inspection
- log verification
- secret leakage check
- SAST
- SCA only if dependencies changed

#### DoD

- mailbox source configurable, not hardcoded;
- mailbox access is read-only;
- credentials are read only from env and never appear in logs/artifacts;
- latest N messages become normalized events;
- attachment content is not parsed, only metadata is captured;
- `beeagent-rop` receives normalized payload through existing module runtime path;
- operator sees result without reading code;
- degraded paths are explainable;
- no destructive mailbox/CRM actions exist;
- BeeAgent core contains no ROP classification/summary/recommendation rules.

### Iteration 19 — ROP live batch classification handoff v0

**Status:** DONE

#### Goal

Make live ROP batch flow semantically useful: After loading `json_batch` or `mailbox_readonly` BeeAgent must first call `beeagent-rop` case `lead_classification` for each normalized event, retain `classified_events.json`, and then call `beeagent-rop` case `rop_summary` already on classified events.

#### Scope

**Includes:**

- batch classification handoff inside existing ROP source flow;
- `beeagent-rop` `lead_classification` call for each normalized event via existing module runtime path;
- classified events collection without adding ROP business rules to BeeAgent;
- artifact:
  - `classified_events.json`;
- Transfer to `rop_summary` is not raw normalized events, but classified events;
- operator summary with classification diagnostics:
  - normalized count;
  - classified count;
  - classification failed count;
  - summary status;
  - artifact refs;
- degraded behavior:
  - per-event classification failure doesn't roll the whole batch;
  - failed event receives controlled fallback item:
    - `case_type: "unknown"`;
    - `priority: "medium"`;
    - `reason_code: "classification_error"`;
    - `confidence: 0.0`;
    - `is_fallback: true`;
- tests on successful handoff and degraded per-event classification;
- repeated live smoke on `folder=welding`, if credentials is available;
- docs update.

#### Not included:

- ROP business rules in BeeAgent;
- Change of classification logic in `beeagent-rop`;
- AI classification;
- Bitrix/1C connectors;
- CRM write-back;
- OCR;
- attachment deep parsing;
- continuous listener/polling;
- multi-mailbox routing;
- automatic actions;
- n8n/MCP implementation.

#### Deliverable

BeeAgent live source flow calls `beeagent-rop` in the correct sequence: normalized events → lead classification → classified events → ROP summary. `rop_summary` receives classified events rather than raw mailbox events.

#### Artifacts

- `storage/runs/<run_id>/source_diagnostics.json`
- `storage/runs/<run_id>/intake_metadata.json`
- `storage/runs/<run_id>/normalized_events.json`
- `storage/runs/<run_id>/classified_events.json`
- `storage/runs/<run_id>/module-beeagent-rop/module_result.json`
- optional `storage/runs/<run_id>/module-beeagent-rop/lead_classification_result.json`
- optional `storage/runs/<run_id>/module-beeagent-rop/rop_summary_result.json`
- `storage/runs/<run_id>/operator_summary.json`
- `logs/app.log`

#### Checks

- `uv run pytest -q`
- targeted ROP batch classification handoff tests
- successful source → classify → summary test
- per-event classification failure scenario
- module missing / unsupported case degraded scenario
- repeated live smoke with `folder=welding`, `items_max=10`, if credentials are available
- manual artifact inspection
- log verification
- secret leakage check
- no ROP business rules in BeeAgent core
- SAST mindset review
- SCA only if dependencies changed

#### DoD

- `rop_summary` receives classified events;
- `classified_events.json` is created and referenced in `operator_summary.json`;
- per-event classification failures are visible and do not crash whole batch;
- BeeAgent core contains no ROP classification rules;
- all domain classification remains inside `beeagent-rop`;
- artifacts are reproducible and explainable;
- no destructive mailbox/CRM actions exist;
- secrets do not appear in logs/artifacts.

### Iteration 20 — ROP CLI and review export v1

**Status:** DONE

#### Goal

Make the normal operator/dev CLI for ROP MVP flow, so that the operator can run BeeAgent ROP pipeline via `./start.sh rop ...` without Telegram, without `test.py` and without the Python- script.

BeeAgent must be capable of one command:

- Start configured ROP source flow;
- receive the last N events from `json_batch` or `mailbox_readonly`;
- Run events through `beeagent-rop` `lead_classification`;
- collect `classified_events.json`;
- Call `rop_summary`;
- Write standard artifacts;
- display a clear terminal summary;
- Export review TSV for reconciliation with person/employer.

#### Scope

**Includes:**

- CLI entrypoint through existing `start.sh`:
  - `./start.sh rop run`;
  - `./start.sh rop summary`;
  - `./start.sh rop export-review`;
- passing arguments from `start.sh` to `config/start.py`;
- CLI dispatch in BeeAgent app/start layer without separate service;
- Save backward compatibility:
  - `./start.sh` operates as it used to be with `run.mode`;
  - `./start.sh telegram` is clearly launching Telegram mode;
- Launch existing `run_rop_batch_case(...)`;
- Read `rop.sources` from `config/settings.yml`;
- source selection through `--source-id`;
- override `items_max` through `--items-max` without change `settings.yml`;
- override `period` through `--period` without change `settings.yml`;
- explicit `--run-id`;
- terminal output:
  - `run_id`;
  - source id/type;
  - loaded/classified/failed counts;
  - module status;
  - summary;
  - artifact paths;
- `summary` command:
  - Read `storage/runs/<run_id>/operator_summary.json`;
  - outputs a brief readable summary;
- `export-review` command:
  - Read `normalized_events.json`;
  - Read `classified_events.json`;
  - Creates `rop_review_table.tsv`;
- TSV columns for human review:
  - `event_id`;
  - `source_id`;
  - `sender`;
  - `subject`;
  - `bot_case_type`;
  - `bot_reason_code`;
  - `bot_confidence`;
  - `bot_is_fallback`;
  - `human_case_type`;
  - `should_rop_see`;
  - `bitrix_status`;
  - `notes`;
  - `correct_action`;
- degraded behavior:
  - source not found;
  - source disabled;
  - no active source;
  - missing mailbox credentials;
  - mailbox unavailable;
  - module missing;
  - partial classification failure;
  - missing run artifacts for `summary` / `export-review`;
- docs update:
  - `docs/ROADMAP.md`;
  - `README.md`;
  - `docs/DEV_GUIDE.md`.

**Excluded:**

- Telegram requirement for ROP CLI;
- Telegram UI changes except to maintain existing behaviour;
- web UI;
- scheduler / listener / polling daemon;
- Bitrix API;
- 1C;
- CRM write-back;
- automatic task creation;
- OCR;
- attachment deep parsing;
- AI classification;
- ROP business rules in BeeAgent;
- classification logic changes to `beeagent-rop`;
- multi-mailbox routing beyond existing `source_id`.

#### Implemented

- `src/beeagent_module/core/cli.py` – CLI handler module with three commands:
  - `handle_rop_run()` – ROP batch launch with in-memory overrides;
  - `handle_rop_summary()` – Show operator summary;
  - `handle_rop_export_review()` is a generation of TSV;
- `config/start.py` is updated for CLI args and dispatch: parsing.
  - `./start.sh` → use `run.mode` from settings;
  - `./start.sh telegram` → explicit Telegram;
  - `./start.sh rop run/summary/export-review` → dispatch to CLI handler;
- `_apply_source_overrides()` – in-memory source override logic for CLI args;
- `_build_review_tsv_rows()` — TSV generation from normalized + classified events;
- `tests/test_cli_rop_commands.py` — targeted tests:
  - backward compat (no args, telegram);
  - rop run with batch source;
  - rop summary with valid artifact;
  - rop export-review with TSV creation;
  - error scenarios (missing source, disabled source, missing artifacts);
- docs update in DEV_GUIDE, README, ROADMAP.

#### Deliverable

The operator may perform ROP MVP flow without Telegram and without `test.py`:

```bash
./start.sh rop run \
  --source-id hotline_mailbox \
  --items-max 20 \
  --run-id live-review-2026-05-15-welding-20 \
  --period 2026-05

./start.sh rop summary \
  --run-id live-review-2026-05-15-welding-20

./start.sh rop export-review \
  --run-id live-review-2026-05-15-welding-20 \
  --format tsv
```

Artifacts:

- `storage/runs/<run_id>/source_diagnostics.json`
- `storage/runs/<run_id>/intake_metadata.json`
- `storage/runs/<run_id>/normalized_events.json`
- `storage/runs/<run_id>/classified_events.json`
- `storage/runs/<run_id>/module-beeagent-rop/module_result.json`
- `storage/runs/<run_id>/module-beeagent-rop/rop_summary_result.json`
- `storage/runs/<run_id>/operator_summary.json`
- `storage/runs/<run_id>/rop_review_table.tsv`
- `logs/app.log`

#### Checks

- `uv run pytest -q`
- targeted CLI tests (argument parsing, overrides, backward compat);
- smoke: `./start.sh rop run --source-id rop_batch_sample --items-max 2 --run-id smoke-rop-cli-json`;
- smoke: `./start.sh rop summary --run-id smoke-rop-cli-json`;
- smoke: `./start.sh rop export-review --run-id smoke-rop-cli-json --format tsv`;
- backward compat: `./start.sh` without args;
- backward compat: `./start.sh telegram`;
- artifact inspection;
- log verification;
- secret leakage check;
- no direct `beeagent_rop` imports in core;
- TSV structure verification.

#### DoD

- `./start.sh` works as it did before (no args → `run.mode` from settings);
- `./start.sh telegram` is clearly launching Telegram mode;
- `./start.sh rop run [args]` starts ROP batch without Telegram;
- CLI overrides (`--source-id`, `--items-max`, `--period`, `--run-id`) applies to in-memory only;
- a disabled source does not silently disable the CLI; it returns a fail-fast error;
- source not found returns fail-fast error;
- `rop summary` reads `operator_summary.json` and releases readable summary;
- `rop run` automatically creates `rop_review_table.tsv` for the current run;
- `rop export-review` remains a manual re-export of `rop_review_table.tsv` for the already existing run;
- The last 5 TSV columns are empty for the operator to be filled in manually;
- CLI uses existing `run_rop_batch_case()`, does not duplicate orchestration;
- `rop.sources` remains source of truth for sources;
- BeeAgent core does not contain ROP business rules;
- artifacts is reproducible and conservative with logs;
- secrets does not enter logs/artifacts;
- docs updated.

### Iteration 21 — Enriched ROP review TSV v1

**Status:** DONE

#### Goal

Make `rop_review_table.tsv` suitable for quick human review / customer validation without the manual opening of `normalized_events.json` and `classified_events.json`.

After `./start.sh rop run`, the operator must receive TSV, which can be inserted immediately into Google Sheets and marked: the email, brief context, attachments, bot decision, explanation and empty fields for human/Bitrix comparison are visible.

#### Scope

**Includes:**

- Increase `rop_review_table.tsv`;
- Save the automatic export of TSV after `./start.sh rop run`;
- Save manual re-export through `./start.sh rop export-review`;
- Add review-useful columns:
  - `body_short`;
  - `attachments`;
  - `bot_priority`;
  - `bot_reasoning`;
  - `bitrix_lead_id`;
  - `bitrix_deal_id`;
  - `bitrix_responsible`;
  - `is_duplicate`;
  - `duplicate_of`;
- Save the current columns:
  - `event_id`;
  - `source_id`;
  - `sender`;
  - `subject`;
  - `bot_case_type`;
  - `bot_reason_code`;
  - `bot_confidence`;
  - `bot_is_fallback`;
  - `human_case_type`;
  - `should_rop_see`;
  - `bitrix_status`;
  - `notes`;
  - `correct_action`;
- `body_short` must be bounded/sanitized preview, not the complete raw body;
- `attachments` must be metadata-only:
  - filename;
  - content_type;
  - size_bytes, if any;
- empty/missing fields must be exported as empty cells;
- TSV must remain tab-separated and pasteable in Google Sheets;
- Update tests on header/order/row values;
- Update README.md / DEV_GUIDE / ROADMAP on the new TSV contract.

**Excluded:**

- Changes in classification in `beeagent-rop`;
- New reason codes;
- Bitrix API;
- CRM write-back;
- OCR;
- attachment content parsing;
- Export raw `.eml`;
- full raw headers export;
- web UI;
- mailbox cursor/pagination;
- config toggle for deactivation of TSV.

#### Deliverable

`./start.sh rop run` creates an extended:

```text
storage/runs/<run_id>/rop_review_table.tsv
```

TSV contains sufficient context for hand-marking 20-50 letters without opening JSON artifacts.

#### Expected TSV columns

```text
event_id
source_id
sender
subject
body_short
attachments
bot_case_type
bot_reason_code
bot_priority
bot_confidence
bot_is_fallback
bot_reasoning
human_case_type
should_rop_see
bitrix_status
notes
bitrix_lead_id
bitrix_deal_id
bitrix_responsible
is_duplicate
duplicate_of
correct_action
```

#### Artifacts

- `storage/runs/<run_id>/rop_review_table.tsv`
- existing:
  - `source_diagnostics.json`
  - `intake_metadata.json`
  - `normalized_events.json`
  - `classified_events.json`
  - `operator_summary.json`
  - module artifacts

#### Checks

- `uv run pytest -q`
- targeted CLI TSV tests;
- TSV header order test;
- TSV row with `body_short`;
- TSV row with attachment metadata;
- missing body/attachments scenario;
- `./start.sh rop run` smoke;
- `./start.sh rop export-review --run-id <run_id> --format tsv` smoke;
- artifact inspection;
- log inspection;
- secret leakage check;
- no raw `.eml` check;
- no direct `beeagent_rop` imports in BeeAgent core;
- SAST/security review for artifact export.

#### DoD

- `rop_review_table.tsv` contains extended review columns;
- TSV remains a valide tab-separated file;
- `body_short` bounded and does not export complete raw body uncontrollably;
- `attachments` metadata-only, without content;
- empty optional fields are exported as empty cells;
- Automatic TSV export after `rop run` is not broken;
- Manual `export-review` is not broken;
- BeeAgent core does not contain ROP business rules;
- `beeagent-rop` does not change;
- secrets/raw `.eml` does not enter artifacts/logs;
- docs updated.

### Iteration 22 — Operator Web Shell v0 with ROP dashboard

**Status:** DONE

#### Goal

Add to BeeAgent the minimum read-only operator web-panel above the existing runtime artifacts so that the operator/contractor can view runs, summary, module outputs and ROP review table without reading JSON/TSV manually.

Iteration must lay reusable web shell for future modules (`beeagent-rop`, `beescan`, `merch`), but module-specific will be the first working screen to be used by ROP dashboard.

#### Why this is needed

After iterations, 18-21 ROP backend path is already operational:

```text
mailbox/json_batch → normalized_events → beeagent-rop classification → classified_events → rop_summary → operator_summary → rop_review_table.tsv
```

But the current result is CLI/artifact-oriented:.

- The operator needs to open JSON/TSV manually;
- It is difficult for the customer to show MVP as a product;
- No single run overview;
- no web- surface, which is then reused for BeeScan/Merch.

The next MVP- is to make the visible operator surface, without adding CRM write-back, Bitrix, OCR or AI.

#### Scope

**Includes:**

- new web entrypoint:
  - `./start.sh web`;

- Minimum web server inside BeeAgent;
- read-only operator web shell;
- server-side HTML templates or simple HTML-rendering implementation without React/Vue/Next;
- Pages:
  - `/` — landing / operator home;
  - `/runs` is a run directory of `storage/runs`;
  - `/runs/<run_id>` is a common run overview;
  - `/runs/<run_id>/rop` – ROP-specific dashboard on existing artifacts;
  - `/modules` is a list of known modules/registry diagnostics, if artifact is available;

- Read only existing artifacts:
  - `operator_summary.json`;
  - `source_diagnostics.json`;
  - `intake_metadata.json`;
  - `normalized_events.json`;
  - `classified_events.json`;
  - `rop_review_table.tsv`;
  - `module-beeagent-rop/module_result.json`;
  - `module-beeagent-rop/rop_summary_result.json`;

- ROP dashboard shows:
  - `run_id`;
  - source id/type;
  - loaded/classified/failed counts;
  - counts to `case_type`;
  - counts to `priority`;
  - fallback count;
  - reason_code distribution;
  - an email table;
  - `sender`;
  - `subject`;
  - `body_short`;
  - `attachments`;
  - `bot_case_type`;
  - `bot_priority`;
  - `bot_confidence`;
  - `bot_reason_code`;
  - `bot_reasoning`;
  - `bot_is_fallback`;

- query filters on `/runs/<run_id>/rop`:
  - `case_type`;
  - `priority`;
  - `fallback`;
  - `reason_code`;

- TSV: download/open link
  - `storage/runs/<run_id>/rop_review_table.tsv`;

- References to the main artifacts;
- graceful degraded UI:
  - missing run;
  - missing artifact;
  - malformed JSON;
  - empty runs;
  - non-ROP run;

- tests on route handlers / HTML content / artifact parsing;
- docs update:
  - `docs/ROADMAP.md`;
  - `README.md`;
  - `docs/DEV_GUIDE.md`.

**Excluded:**

- login/auth;
- multi-user access control;
- web-triggered `rop run`;
- CRM write-back;
- Bitrix;
- 1C;
- OCR;
- attachment content parsing;
- Editing of human labels in UI;
- Save review corrections from UI;
- Complex frontend framework;
- websocket/live updates;
- scheduler/listener;
- production deployment hardening;
- nginx/basic-auth setup automation;
- BeeScan UI;
- ROP business rules in BeeAgent core;
- Change in `beeagent-rop`.

#### Deliverable

The operator may start:

```bash
./start.sh web
```

And open web-panel where you can see the existing BeeAgent runs and the first ROP dashboard on artifacts:

```text
storage/runs/<run_id>/...
```

The dashboard performs no actions, changes no data and writes nothing to CRM. It only reads and displays existing artifacts.

#### Expected routes

```text
/
 /runs
 /runs/<run_id>
 /runs/<run_id>/rop
 /modules
```

#### Expected artifacts read

```text
storage/runs/<run_id>/operator_summary.json
storage/runs/<run_id>/source_diagnostics.json
storage/runs/<run_id>/intake_metadata.json
storage/runs/<run_id>/normalized_events.json
storage/runs/<run_id>/classified_events.json
storage/runs/<run_id>/rop_review_table.tsv
storage/runs/<run_id>/module-beeagent-rop/module_result.json
storage/runs/<run_id>/module-beeagent-rop/rop_summary_result.json
storage/interfaces/modules.json
logs/app.log
```

#### Checks

- `uv run pytest -q`;
- targeted web route tests;
- route `/runs` works with empty and non-empty `storage/runs`;
- route `/runs/<run_id>` works with valid/missing/malformed artifacts;
- route `/runs/<run_id>/rop` renders ROP metrics and email table;
- filters work for `case_type`, `priority`, `fallback`, `reason_code`;
- TSV link is visible if `rop_review_table.tsv` exists;
- no raw `.eml` is served;
- no attachment content is served;
- no secrets appear in HTML;
- no path traversal through `run_id`;
- smoke:
  - create or reuse ROP run;
  - start web;
  - open `/runs`;
  - open `/runs/<run_id>/rop`;

- SAST/security review for artifact reading and path handling;
- SCA only if new dependencies are added.

#### DoD

- `./start.sh web` starts operator web shell;
- existing `./start.sh`, `./start.sh telegram`, `./start.sh rop ...` behavior is not broken;
- web shell reads only `storage/` artifacts;
- no destructive actions exist in web UI;
- no CRM/mailbox actions are exposed;
- run listing is bounded and does not full-scan huge artifacts unnecessarily;
- ROP dashboard gives enough information to review live batch without opening JSON/TSV manually;
- filters are server-side and test-covered;
- path traversal is prevented;
- secrets/raw `.eml`/attachment content are not exposed;
- BeeAgent core does not contain ROP classification rules;
- `beeagent-rop` is not changed;
- docs are updated.

### Iteration 23 — ROP source profile hardening v0

**Status:** DONE

#### Goal

Strengthen config-driven source contract for ROP pipeline so that each input source has a clear business/profile context and this context is reproducible to runtime artifacts, dashboard and downstream flow without changing `beeagent-rop`.

#### Why this is needed

After It18-22 BeeAgent can read `mailbox_readonly`, classify events through `beeagent-rop`, create TSV and display ROP dashboard.

But the current source contract isn't enough to go to multi-source:

```text
hotline + sales + online + parsales
```

The source now describes technical access, but does not record its role:

```text
technical aggregator
sales mailbox
online sales mailbox
employee mailbox
regional mailbox
```

Without this, It24 will lead to unclear artifacts, weak deduplication and manual code corrections when replacing the source.

#### Scope

**Includes:**

- expand `rop.sources[]` contract:
  - `source_role`;
  - `client_id`;
  - `display_name`;

- Add fail-fast validation to `src/beeagent_module/core/settings.py`;
- Update `config/settings.yml` for existing sources;
- hold source profile metadata in artifacts:
  - `source_diagnostics.json`;
  - `intake_metadata.json`;
  - `operator_summary.json`;

- for `mailbox_readonly` clearly record:
  - `mailbox_folder`;
  - `items_max`;
  - `fetched_count`;
  - `loaded_count`;
  - `malformed_count`, if there is already such a counter or it can be added as a minimum;

- maintain compatibility with the current ROP pipeline:
  - `./start.sh rop run`;
  - `./start.sh rop summary`;
  - `./start.sh rop export-review`;
  - `./start.sh web`;

- Update web/dashboard only to the minimum if new source fields is not displayed by the existing generic rendering;
- Add tests for config validation, source metadata propagation and degraded scenarios;
- Update docs:
  - `docs/ROADMAP.md`;
  - `README.md`;
  - `docs/DEV_GUIDE.md`.

**Excluded:**

- web-triggered `rop run`;
- multi-source ingestion;
- source-aware dedup;
- attachment extraction;
- OCR;
- Bitrix;
- 1C;
- CRM write-back;
- mailbox listener/polling;
- Change `beeagent-rop`;
- ROP business rules in BeeAgent core.

#### Deliverable

One ROP source is still running as it was before, but now source profile is a clear runtime contract:

```yaml
source_id: "hotline_mailbox"
source_type: "mailbox_readonly"
source_role: "technical_aggregator"
client_id: "welding"
display_name: "Welding Hotline mailbox"
enabled: true
authority: "read_only"
items_max: 20
```

Artifacts contains business-readable source metadata and is ready for It24 multi-source flow.

#### Expected artifact fields

```text
source_id
source_type
source_role
source_display_name
client_id
authority
mailbox_folder
items_max
fetched_count
loaded_count
malformed_count
```

#### Change level

```text
runtime-risk
```

If mailbox parsing/path/security-sensitive handling is affected deeper than the normal metadata propagation, raise to:

```text
security-sensitive
```

### Iteration 24 — ROP multi-source ingestion artifacts v0

**Status:** DONE

#### Goal

Expand the BeeAgent ROP source flow from one active source to controlled multi-source ingestion: in a single run, BeeAgent must load multiple configured `rop.sources`, preserve per-source diagnostics, combine normalized events, run classification through `beeagent-rop`, build `rop_summary` and write source-aware artifacts without moving ROP business logic into BeeAgent core.

#### Why this is needed

After It18–23, BeeAgent can work with one active source (`hotline_mailbox`) and already has a source profile contract:

```text
source_id
source_type
source_role
client_id
display_name
authority
items_max
```

But the real ROP flow will consist of several sources: `hotline`, `sales`, `online`, `parsales`, regional/cooperative mailbox sources. without multi-source artifacts, the following UI/attachment/Bitrix iteration will be tied to the single-source model and will require remodeling.

#### Scope

**Includes:**

- expand ROP source flow for multi-source run;
- Support loading of several enabled `rop.sources`;
- Save explicit `--source-id` for single-source run;
- Add CLI to the selection mode of all enabled sources, e.g.:
  - `./start.sh rop run --all-sources`;

- Save backward compatibility:
  - If `--source-id` is specified, launch one source;
  - if `--all-sources` is specified to launch all enabled sources;
  - without `--source-id` and without `--all-sources` save the current single active source semantic or clearly documented behavior;

- For each source write diagnostics;
- Add source-aware artifacts:
  - `source_diagnostics.json` as aggregate summary;
  - optional `source_diagnostics/<source_id>.json` or equivalent per-source section;
  - `intake_metadata.json` with per-source rollup;
  - `normalized_events.json` with `source_id`, `source_role`, `client_id`, `source_display_name`;
  - `classified_events.json` with preserved source metadata;
  - `operator_summary.json` with aggregate and per-source metrics;
  - `rop_review_table.tsv` with source columns;

- graceful degraded behavior:
  - One source fell, the others were treated;
  - source disabled;
  - source not found;
  - no enabled sources;
  - malformed source diagnostics;
  - partial classification failure;

- tests on single-source compatibility and multi-source flow;
- docs update.

**Excluded:**

- New production mailbox credentials;
- mailbox listener / polling daemon;
- source-aware dedup logic;
- Bitrix / 1C;
- CRM write-back;
- attachment extraction;
- OCR;
- Change `beeagent-rop`;
- ROP business rules in BeeAgent core;
- web-triggered run;
- auth/control panel.

#### Deliverable

BeeAgent can create one ROP run from several configured sources, save source-aware artifacts and give operator/web layer enough data for UI-2.

#### Implemented

- canonical path `run_rop_batch_case(...)` is extended to multi-source ingestion without parallel orchestrator path;
- CLI supports `./start.sh rop run --all-sources`;
- `--source-id` saves explicit single-source launch;
- legacy single-active semantics is preserved without `--source-id` or `--all-sources`;
- `source_diagnostics.json` contains aggregate block + `sources[]`;
- `intake_metadata.json` contains aggregate counts + per-source rollup in `sources[]`;
- `normalized_events.json` stores source metadata (`source_id`, `source_type`, `source_role`, `source_display_name`, `client_id`) for each event;
- `classified_events.json` retains source traceability fields;
- one degraded source does not block the total run if there is at least one successfully loaded source;
- `rop_review_table.tsv` is extended by source-aware columns.

#### Expected artifacts

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

If per-source diagnostics are implemented as separate files:

```text
storage/runs/<run_id>/sources/<source_id>/source_diagnostics.json
```

#### Change level

```text
runtime-risk
```

Escalate to `security-sensitive` only if the PR changes mailbox parsing/security-sensitive file/path handling or adds dependencies.

### Iteration 25 — ROP attachment extraction artifacts v0

**Status:** DONE

#### Goal

Add controlled attachment extraction artifact layer for ROP source flow: BeeAgent must safely process attachment metadata of the incoming events, create bounded extraction/refusal evidence artifacts and transfer to downstream flow only safe preview/status fields, without saving raw attachment content or adding ROP business logic to core.

#### Why this is needed

After It24 BeeAgent can collect multi-source ROP run and save source-aware artifacts:

```text
source_diagnostics.json
intake_metadata.json
normalized_events.json
classified_events.json
operator_summary.json
rop_review_table.tsv
```

But the attachments are currently only presented as metadata. For the next step `beeagent-rop It15 — Attachment preview classification hardening` the module needs a stable BeeAgent-owned artifact contract:

```text
attachment metadata
extraction_status
preview_available
safe text preview if available
refusal_reason / reason_code
source artifact reference
```

If you skip It25, attachment parsing and refusal semantics, you're going to spread into `beeagent-rop` or UI, which would break the border:

```text
BeeAgent core = source/orchestration/artifacts/safety boundary
beeagent-rop = domain classification/business logic
UI = read-only presentation over artifacts
```

#### Scope

**Includes:**

- Add BeeAgent-owned attachment extraction artifact layer inside existing ROP batch/source flow;
- Save canonical path:
  - `run_rop_batch_case(...)`;

- Process attachment metadata from `normalized_events.json`;
- Add bounded extraction result contract for each attachment:
  - `attachment_id` or deterministic local id;
  - `event_id`;
  - `source_id`;
  - `filename`;
  - `content_type`;
  - `size_bytes`;
  - `extraction_status`;
  - `preview_available`;
  - `text_preview`;
  - `preview_chars`;
  - `reason_code`;
  - `refusal_reason`;
  - `is_supported`;
  - `is_refused`;
  - `is_truncated`;

- Add safe extraction policy v0:
  - maintain only the clearly safe/simple text attachment inputs if content is already available in controlled normalized test/source payload;
  - For unsupported/binary/pdf/docx/xlsx/image formats in v0, return explicit `unsupported` or `metadata_only` unless extractor is safe;
  - oversized attachments returns `refused`;
  - `.eml` and `message/rfc822` remain blocked;

- Add config-driven limits if the current limits are not sufficient:
  - `rop.attachments.enabled`;
  - `rop.attachments.chars_max`;
  - `rop.attachments.size_max`;
  - `rop.attachments.types`.

- the new mandatory config keys to validate fail-fast into `src/beeagent_module/core/settings.py`;
- create a new artifact:
  - `storage/runs/<run_id>/attachment_extraction.json`;

- Add attachment summary/refs to:
  - `operator_summary.json`;
  - `rop_review_table.tsv` if it does not break the current TSV contract;

- Add safe attachment preview fields to normalized/classified downstream payload only as bounded metadata/preview, not raw content;
- Save source traceability:
  - `source_id`;
  - `source_type`;
  - `source_role`;
  - `source_display_name`;
  - `client_id`;

- degraded behavior:
  - unsupported attachment;
  - oversized attachment;
  - blocked `.eml`;
  - missing attachment metadata;
  - malformed attachment item;
  - extraction exception;
  - no attachments;

- tests:
  - text attachment preview success;
  - unsupported PDF/DOCX/XLSX/image metadata-only/refusal;
  - blocked `.eml` / `message/rfc822`;
  - oversized refused;
  - malformed attachment item skipped/degraded;
  - multi-source source traceability preserved;
  - no raw content in artifacts/logs/HTML/API;

- docs update:
  - `docs/ROADMAP.md`;
  - `README.md`;
  - `docs/DEV_GUIDE.md`;
  - `docs/WEB_UI.md` if API/dashboard/read-model refers to a new artifact.

**Excluded:**

- OCR;
- full PDF/DOCX/XLSX parsing if this requires a new heavy dependency or a separate parser policy;
- arbitrary file execution;
- saving raw attachments;
- serving raw attachments from web;
- attachment download routes;
- web UI changes beyond safe artifact link/summary if necessary;
- ROP classification changes;
- changes to `beeagent-rop`;
- Bitrix / 1C;
- CRM write-back;
- mailbox listener/polling;
- source-aware dedup;
- AI document analysis;
- operator actions / POST routes;
- auth/RBAC.

#### Deliverable

After ROP run BeeAgent creates attachment extraction evidence artifact:

```text
storage/runs/<run_id>/attachment_extraction.json
```

Artifact shows for each event/attachment:

```text
what was seen
what was safely previewed
what was refused
why it was refused
which source/event it belongs to
```

Downstream `beeagent-rop` only receives bounded attachment preview/status fields, if available, and does not receive raw attachment content.

#### Expected artifact

```text
storage/runs/<run_id>/attachment_extraction.json
```

Example shape:

```json
{
  "run_id": "rop-run-2026-05-25",
  "status": "ok",
  "aggregate": {
    "event_count": 2,
    "attachment_count": 3,
    "preview_available_count": 1,
    "metadata_only_count": 1,
    "refused_count": 1,
    "unsupported_count": 1,
    "failed_count": 0
  },
  "items": [
    {
      "event_id": "evt-001",
      "source_id": "hotline_mailbox",
      "source_type": "mailbox_readonly",
      "source_role": "technical_aggregator",
      "source_display_name": "Welding Hotline mailbox",
      "client_id": "welding",
      "attachment_id": "evt-001-att-0",
      "filename": "request.txt",
      "content_type": "text/plain",
      "size_bytes": 512,
      "extraction_status": "preview",
      "preview_available": true,
      "text_preview": "Please review attached request...",
      "preview_chars": 33,
      "is_supported": true,
      "is_refused": false,
      "is_truncated": false,
      "reason_code": "text_preview_extracted",
      "refusal_reason": null
    },
    {
      "event_id": "evt-002",
      "source_id": "hotline_mailbox",
      "source_type": "mailbox_readonly",
      "source_role": "technical_aggregator",
      "source_display_name": "Welding Hotline mailbox",
      "client_id": "welding",
      "attachment_id": "evt-002-att-0",
      "filename": "scan.eml",
      "content_type": "message/rfc822",
      "size_bytes": 2048,
      "extraction_status": "refused",
      "preview_available": false,
      "text_preview": "",
      "preview_chars": 0,
      "is_supported": false,
      "is_refused": true,
      "is_truncated": false,
      "reason_code": "blocked_email_attachment",
      "refusal_reason": "email attachments are blocked"
    }
  ]
}
```

#### Expected downstream event fields

If safe preview exists, normalized/classified event payload may include bounded fields such as:

```text
attachment_extraction_status
attachment_preview_available
attachment_text_preview
attachment_extraction_refs
attachment_refusal_reasons
```

These fields must stay bounded and must not contain raw attachment bytes or full raw files.

#### Artifacts

- `storage/runs/<run_id>/attachment_extraction.json`
- existing:
  - `storage/runs/<run_id>/source_diagnostics.json`
  - `storage/runs/<run_id>/intake_metadata.json`
  - `storage/runs/<run_id>/normalized_events.json`
  - `storage/runs/<run_id>/classified_events.json`
  - `storage/runs/<run_id>/operator_summary.json`
  - `storage/runs/<run_id>/rop_review_table.tsv`
  - `storage/runs/<run_id>/module-beeagent-rop/module_result.json`
  - `storage/runs/<run_id>/module-beeagent-rop/rop_summary_result.json`
  - `logs/app.log`

#### Change level

```text
security-sensitive
```

Reason:

- attachment input is untrusted;
- parsing/serialization boundary changes;
- artifact contract changes;
- potential sensitive client data exposure risk;
- file/content safety rules must be explicit.

#### Checks

- `uv run pytest -q`;
- targeted ROP attachment extraction tests;
- source flow smoke with `json_batch` attachment fixtures;
- optional mailbox smoke if credentials are available;
- artifact inspection:
  - `attachment_extraction.json`;
  - `normalized_events.json`;
  - `classified_events.json`;
  - `operator_summary.json`;
  - `rop_review_table.tsv`;

- log verification;
- secret leakage check;
- no raw `.eml` check;
- no `message/rfc822` check in exported previews;
- no raw attachment content / bytes fields in artifacts;
- no web route serves raw attachment content;
- no mailbox/CRM destructive actions;
- no direct `beeagent_rop` imports in BeeAgent core;
- SAST required;
- SCA only if dependencies change;
- DAST/IAST not required unless new network-facing behavior is added;
- fuzzing optional only if a new parser is added.

#### DoD

- `attachment_extraction.json` is created for ROP runs with attachments;
- no-attachment runs remain valid and do not fail;
- unsupported/refused attachments are visible and explainable;
- safe text previews are bounded by config;
- `.eml` / `message/rfc822` attachments remain blocked;
- raw attachment bytes/content are not stored in artifacts/logs/HTML/API;
- source traceability is preserved per attachment;
- downstream event payload contains only bounded safe preview/status fields;
- `beeagent-rop` is not changed;
- BeeAgent core does not contain ROP classification/business rules;
- existing `./start.sh rop run`, `summary`, `export-review`, `web` behavior is not broken;
- tests and docs are updated;
- required security checks are completed;
- `pyproject.toml.version` is not changed.

### Iteration 26 — Bitrix read-only reconciliation artifacts v0

**Status:** DONE

#### Goal

Add controlled read-only Bitrix reconciliation layer for ROP source flow: BeeAgent must be able to check already obtained and classified input events with the current state of Bitrix CRM, create a reproducible artifact `bitrix_reconciliation.json` and show whether the corresponding lead/deal/contact/company has been found without performing any CRM write-back actions.

#### Why this is needed

After It24/It25 BeeAgent already can collect multi-source ROP run and save source-aware / attachment-aware artifacts:

```text
source_diagnostics.json
intake_metadata.json
normalized_events.json
attachment_extraction.json
classified_events.json
operator_summary.json
rop_review_table.tsv
```

After `beeagent-rop It15` domain module can use BeeAgent attachment extraction contract at classification.

But for MVP, the customer needs to see more than just:

```text
email received
→ The bot classified the circulation
→ summary/review table is available
```

a full read-only evidence chain:

```text
email received
→ the bot identified what it is
→ whether this is present in Bitrix is visible
→ whether lead/deal/contact/company was found is visible
→ the responsible person is visible
→ the stage/status in CRM is visible
→ You can see where the loss, take, ambiguity or manual review is.
```

Bitrix in this iteration **is not source of truth for the incoming email- flow**. The source of truth for inbound inquiries is BeeAgent source artifacts from mailbox/json_batch ingestion. Bitrix, which is the CRM-state system against which BeeAgent is checked.

Therefore, `not_found` in Bitrix is not an error of BeeAgent, but an important MVP signal:

```text
important email exists
but Bitrix entity not found
→ possible lost lead / CRM gap / manual review
```

If you miss this iteration, `beeagent-rop` will be further polished without CRM evidence, and UI will show only classification without answering ROP:'s main question.

```text
What about this Bitrix treatment?
```

#### Scope

**Includes:**

- Add BeeAgent-owned Bitrix read-only reconciliation layer;
- Save canonical ROP artifact pipeline;
- Add config-driven Bitrix connector contract to `config/settings.yml`;
- Read Bitrix webhook URL from env only;
- Add fail-fast validation to `src/beeagent_module/core/settings.py` for mandatory Bitrix config keys;
- Bitrix config must not require secret/env at `bitrix.enabled: false`;
- When reconciliation is clearly launched without env is understood by fail-fast error;
- Add a minimum Bitrix REST client / adapter for read-only calls;
- use only allowlisted read-only Bitrix methods:
  - `crm.item.list`;
  - `crm.item.fields` if necessary for diagnosis/fields discovery;
  - `crm.status.list` if required for status/stages;
  - `crm.category.list` if required for deal categories;

- Support system CRM entity types:
  - `1` — lead;
  - `2` — deal;
  - `3` — contact;
  - `4` — company;

- Add CLI/runtime path for reconciliation of the existing ROP run, for example:

```bash
./start.sh rop reconcile-bitrix --run-id <run_id>
```

- Read existing run artifacts:
  - `normalized_events.json`;
  - `classified_events.json`;
  - optional `attachment_extraction.json`;
  - optional `operator_summary.json`;

- perform candidate lookup on Bitrix on accessible safe signals:
  - sender email;
  - phone, if already available in normalized event;
  - subject/title;
  - company/client hints, if already available in event;
  - source_id/source_role;
  - event date, if any;
  - bot_case_type;

- Create artifact:

```text
storage/runs/<run_id>/bitrix_reconciliation.json
```

- Add per-event reconciliation result:
  - `event_id`;
  - `source_id`;
  - `sender`;
  - `subject`;
  - `bot_case_type`;
  - `bitrix_match_status`;
  - `bitrix_entity_type`;
  - `bitrix_entity_type_id`;
  - `bitrix_entity_id`;
  - `bitrix_title`;
  - `bitrix_stage`;
  - `bitrix_responsible_id`;
  - `bitrix_contact_id`;
  - `bitrix_company_id`;
  - `bitrix_match_reason`;
  - `bitrix_confidence`;
  - `needs_manual_review`;
  - `reconciliation_reason`;

- Support the status of reconciliation:
  - `matched_lead`;
  - `matched_deal`;
  - `matched_contact`;
  - `matched_company`;
  - `not_found`;
  - `duplicate_candidate`;
  - `ambiguous`;
  - `skipped`;
  - `connector_degraded`;
  - `error`;

- Add aggregate counts:
  - `event_count`;
  - `matched_count`;
  - `not_found_count`;
  - `duplicate_candidate_count`;
  - `ambiguous_count`;
  - `skipped_count`;
  - `connector_error_count`;

- Add degraded behavior:
  - missing Bitrix env;
  - invalid config;
  - Bitrix auth/permission error;
  - Bitrix API error;
  - timeout;
  - malformed response;
  - pagination failure;
  - partial candidate lookup failure;

- do not break existing ROP artifacts at connector failure;
- Enrich `rop_review_table.tsv` Bitrix fields, if `bitrix_reconciliation.json` exists and `export-review` is restarted;
- Add tests with fake Bitrix responses;
- Update docs:
  - `docs/ROADMAP.md`;
  - `README.md`;
  - `docs/DEV_GUIDE.md`;
  - `docs/SECURITY.md` if security contract. changes

**Excluded:**

- `crm.item.add`;
- `crm.item.update`;
- `crm.item.delete`;
- creating leads;
- creating deals;
- Contacts/companies;
- Change of stages/categories;
- Designation of those responsible;
- Creation of tasks;
- Comments in timeline;
- Automatic merge/dedup in Bitrix;
- CRM write-back;
- Bitrix OAuth application flow;
- Bitrix marketplace/app install flow;
- web-triggered reconciliation;
- Bitrix dashboard UI;
- Bitrix settings UI;
- auth/RBAC;
- operator control panel;
- 1C integration;
- manager scoring;
- classification logic change to `beeagent-rop`;
- ROP business rules in BeeAgent core.

#### Deliverable

BeeAgent can perform read-only reconciliation for the existing ROP run:

```bash
./start.sh rop reconcile-bitrix --run-id <run_id>
```

After execution, artifact: appears

```text
storage/runs/<run_id>/bitrix_reconciliation.json
```

Artifact shows for each classified event:

```text
what arrived
As the bot classified the event
which candidate is found in Bitrix
which entity type is found
What stage/status
Who's responsible
Is there a take/ambiguity
Do you need manual review
Why reconciliation decision is accepted
```

After repeated export-review:

```bash
./start.sh rop export-review --run-id <run_id> --format tsv
```

`rop_review_table.tsv` may fill in Bitrix columns on the basis of `bitrix_reconciliation.json`.

#### Expected config contract

Runtime/config source of truth:

```text
config/settings.yml
```

Expected config block:

```yaml
bitrix:
  enabled: false
  webhook_env: "BITRIX_WEBHOOK_URL"
  timeout: 10
  page_size: 50
  pages_max: 3
  types_entity:
    - 1
    - 2
    - 3
    - 4
  reconciliation:
    enabled: false
    candidate_limit: 20
    window_date: 180
```

Rules:

- `BITRIX_WEBHOOK_URL` value must never be stored in `settings.yml`;
- `BITRIX_WEBHOOK_URL` value must never be written to logs/artifacts/HTML/API;
- `bitrix.enabled: false` must not require env during startup;
- explicit reconciliation invocation must fail clearly if required env is missing;
- no hidden required defaults for sensitive Bitrix behavior.

#### Expected artifact

```text
storage/runs/<run_id>/bitrix_reconciliation.json
```

Example shape:

```json
{
  "run_id": "rop-run-2026-06-18",
  "status": "ok",
  "read_only": true,
  "connector": {
    "system": "bitrix",
    "portal_url": "https://my.welding.kz",
    "auth_source": "env:BITRIX_WEBHOOK_URL",
    "allowed_methods": [
      "crm.item.list",
      "crm.item.fields",
      "crm.status.list",
      "crm.category.list"
    ]
  },
  "aggregate": {
    "event_count": 20,
    "matched_count": 9,
    "not_found_count": 6,
    "duplicate_candidate_count": 2,
    "ambiguous_count": 2,
    "skipped_count": 1,
    "connector_error_count": 0
  },
  "items": [
    {
      "event_id": "evt-001",
      "source_id": "hotline_mailbox",
      "sender": "client@example.com",
      "subject": "Request for welding machine price",
      "bot_case_type": "new_lead",
      "bitrix_match_status": "matched_lead",
      "bitrix_entity_type": "lead",
      "bitrix_entity_type_id": 1,
      "bitrix_entity_id": 253,
      "bitrix_title": "Request for welding machine price",
      "bitrix_stage": "NEW",
      "bitrix_responsible_id": 6,
      "bitrix_contact_id": null,
      "bitrix_company_id": null,
      "bitrix_match_reason": "sender_email_exact",
      "bitrix_confidence": 0.95,
      "needs_manual_review": false,
      "reconciliation_reason": "Exact sender email candidate found in Bitrix lead list."
    },
    {
      "event_id": "evt-002",
      "source_id": "online_mailbox",
      "sender": "buyer@example.com",
      "subject": "KP for welding electrodes",
      "bot_case_type": "new_lead",
      "bitrix_match_status": "not_found",
      "bitrix_entity_type": "",
      "bitrix_entity_type_id": null,
      "bitrix_entity_id": null,
      "bitrix_title": "",
      "bitrix_stage": "",
      "bitrix_responsible_id": null,
      "bitrix_contact_id": null,
      "bitrix_company_id": null,
      "bitrix_match_reason": "no_candidate_found",
      "bitrix_confidence": 0.0,
      "needs_manual_review": true,
      "reconciliation_reason": "No Bitrix candidate was found for this classified event."
    }
  ],
  "warnings": []
}
```

#### Matching behavior v0

Matching must be simple, bounded and explainable.

Allowed matching signals:

```text
sender email
phone if already normalized
subject/title
company/client hints if already normalized
source_id/source_role
event date if already available
bot_case_type
```

Recommended v0 behavior:

```text
exact email/phone match
→ high-confidence candidate

company/contact-only match
→ matched_contact or matched_company, often manual review

title/subject weak match
→ lower-confidence candidate

multiple strong candidates
→ duplicate_candidate

multiple weak candidates
→ ambiguous

no candidate
→ not_found

connector/API failure
→ connector_degraded or error
```

Important rule:

```text
not_found != connector failure
```

`not_found` means Bitrix was reachable, but no candidate was found.

#### Expected TSV impact

Existing `rop_review_table.tsv` already has Bitrix placeholder fields. After reconciliation and repeated export, these fields should be populated when possible:

```text
bitrix_status
bitrix_lead_id
bitrix_deal_id
bitrix_responsible
```

Optional future-compatible fields may remain empty in v0 if TSV contract already includes them.

If `bitrix_reconciliation.json` is missing:

```text
rop export-review
→ still works
→ Bitrix columns remain empty
```

#### Artifacts

New artifact:

```text
storage/runs/<run_id>/bitrix_reconciliation.json
```

Existing artifacts read:

```text
storage/runs/<run_id>/normalized_events.json
storage/runs/<run_id>/classified_events.json
storage/runs/<run_id>/attachment_extraction.json
storage/runs/<run_id>/operator_summary.json
```

Existing artifacts optionally updated/generated:

```text
storage/runs/<run_id>/rop_review_table.tsv
```

Logs:

```text
logs/app.log
```

Docs:

```text
docs/ROADMAP.md
README.md
docs/DEV_GUIDE.md
docs/SECURITY.md
```

#### Change level

```text
security-sensitive
```

Reason:

- external connector boundary;
- env/secret handling;
- Bitrix REST API integration;
- external JSON response parsing;
- stored artifact contract change;
- CRM authority boundary;
- future write-back risk must be explicitly blocked in v0.

#### Checks

- `uv run pytest -q`;
- targeted Bitrix reconciliation tests;
- targeted config validation tests;
- targeted ROP CLI tests;
- fake Bitrix client tests;
- fake Bitrix API error tests;
- artifact inspection:
  - `bitrix_reconciliation.json`;
  - `rop_review_table.tsv`;

- log verification;
- secret leakage check;
- no webhook URL in logs/artifacts;
- no raw auth headers in logs/artifacts;
- no CRM write methods in adapter/client allowlist;
- no `crm.item.add`;
- no `crm.item.update`;
- no `crm.item.delete`;
- no task/timeline write methods;
- no destructive mailbox/CRM actions;
- no direct `beeagent_rop` imports in BeeAgent core beyond existing module runtime path;
- SAST required;
- SCA only if dependencies change;
- DAST-style route/runtime misuse checks if any network-facing path changes;
- IAST not required;
- fuzzing optional only for fragile JSON/TSV parsing, not mandatory.

Required automated scenarios:

```text
config disabled does not require Bitrix env
explicit reconciliation without env fails clearly
invalid Bitrix config fails fast
fake matched lead
fake matched deal
fake matched contact only
fake matched company only
not found
duplicate candidate
ambiguous candidate
connector degraded
Bitrix API error
permission denied
timeout / transport error
malformed JSON response
pagination next handling if implemented
TSV enrichment when reconciliation artifact exists
TSV remains valid when reconciliation artifact is missing
no webhook URL in artifact/logs
no write method called
```

Recommended smoke:

```bash
./start.sh rop run \
  --source-id rop_batch_sample \
  --items-max 2 \
  --run-id smoke-bitrix-recon-input

./start.sh rop reconcile-bitrix \
  --run-id smoke-bitrix-recon-input

./start.sh rop export-review \
  --run-id smoke-bitrix-recon-input \
  --format tsv
```

Live Bitrix smoke is optional and must only be run if credentials are available and explicit approval is given.

#### DoD

- `bitrix` config block exists in `config/settings.yml`;
- new required config keys are validated fail-fast in `src/beeagent_module/core/settings.py`;
- Bitrix webhook URL is read only from env;
- webhook URL does not appear in logs/artifacts/tests;
- read-only Bitrix client/adapter exists;
- only allowlisted read-only Bitrix methods are callable;
- CRM write methods are absent from v0 path;
- `./start.sh rop reconcile-bitrix --run-id <run_id>` works;
- `bitrix_reconciliation.json` is created for a valid ROP run;
- each classified event receives a reconciliation result or explicit skipped/degraded status;
- `not_found` is represented as a valid CRM gap signal;
- connector failure is represented separately from `not_found`;
- existing ROP pipeline remains backward-compatible;
- `rop export-review` works with and without `bitrix_reconciliation.json`;
- Bitrix columns in TSV are populated when reconciliation data exists;
- tests cover success, not found, duplicates, ambiguity and degraded connector cases;
- no `beeagent-rop` code is changed;
- BeeAgent core does not contain ROP classification/business rules;
- docs are updated;
- required security checks are completed;
- `pyproject.toml.version` is not changed.

### Iteration 27 — ROP MVP Current State Index + Bitrix Evidence Board v0

**Status:** DONE

#### Goal

Add BeeAgent-owned current-state/index layer for ROP MVP: the system must be able to collect the current operator painting for the last or clearly selected ROP run, combine source/classification/attachment/Bitrix evidence into one stable read-model artifact and give it to Web Console / BeeUI without the need to manually open several JSON/TSV files.

The iteration must turn the set of run artifacts:

```text
source_diagnostics.json
intake_metadata.json
normalized_events.json
attachment_extraction.json
classified_events.json
bitrix_reconciliation.json
operator_summary.json
rop_review_table.tsv
```

to comprehensible current-state snapshot:

```text
what arrived
which is classified
What's important
What was found in Bitrix
What's lost in Bitrix
that ambiguous/duplicate
which requires a manual review
which evidence artifacts to open
```

#### Why this is needed

After It26, BeeAgent can already perform Bitrix read-only reconciliation and create `bitrix_reconciliation.json`.

But the result is still run/artifact-oriented:.

- The operator must know `run_id`;
- UI depends on scattered artifacts;
- No single latest/current alias;
- no stable read-model for MVP demo;
- optional artifacts like `bitrix_reconciliation.json` could be missing/stale/degraded;
- Bitrix evidence has not yet been turned into ROP. work queues

For MVP, the customer needs a compact operational view rather than “JSON artifacts”:

```text
important inquiries
leads lost in Bitrix
ambiguous/dedup candidates
manual verification
evidence links
```

Iteration is needed because it closes the gap between backend artifacts and customer-visible MVP dashboard.

#### Scope

**Includes:**

- Add BeeAgent-owned current-state builder for ROP run;
- Read only existing ROP artifacts of `storage/runs/<run_id>/...`;
- create per-run artifact:

```text
storage/runs/<run_id>/rop_current_state.json
```

- Create/update interface artifacts:

```text
storage/interfaces/rop_current.json
storage/interfaces/rop_latest.json
storage/interfaces/rop_index.json
```

- Add CLI command:

```bash
./start.sh rop current --run-id <run_id>
```

- Update current-state after successful `rop run`;

- Update current-state after successful `reconcile-bitrix`;

- do not create a false success state after failed `reconcile-bitrix`;

- Add latest/current alias semantics:
  - latest ROP run;
  - selected/current run;
  - current client/source context;
  - technical `run_id` as evidence, not primary operator concept;

- build KPI/read-model:
  - total events;
  - normalized events;
  - classified events;
  - high priority;
  - needs manual review;
  - source degraded;
  - attachment preview/refused counts;
  - Bitrix matched;
  - Bitrix not found / lost in Bitrix;
  - Bitrix ambiguous/duplicate;
  - Bitrix connector degraded;
  - unreconciled/no Bitrix artifact;

- build operator queues:
  - `lost_in_bitrix`;
  - `needs_review`;
  - `high_priority`;
  - `ambiguous`;
  - `matched`;
  - `unreconciled`;
  - `degraded`;

- Add evidence references:
  - normalized event;
  - classified event;
  - attachment extraction;
  - Bitrix reconciliation item;
  - TSV review artifact;
  - operator summary;

- read artifact availability/freshness:
  - artifact exists/missing;
  - artifact malformed;
  - artifact run_id mismatch;
  - optional artifact older than primary classification/operator artifacts, if detectable;
  - warning for stale optional Bitrix evidence;

- Update BeeAgent UI adapter/read-model:
  - `/rop`;
  - `/api/rop/dashboard`;
  - `/runs/<run_id>`;
  - artifact links where applicable;

- Insert Bitrix tab/section in ROP dashboard read-model if current-state contains Bitrix evidence;

- Add artifact allowlist entries:
  - `rop_current_state_json`;
  - `bitrix_reconciliation_json`;

- graceful degraded behavior:
  - missing current-state artifacts;
  - missing Bitrix reconciliation;
  - stale Bitrix reconciliation;
  - malformed Bitrix artifact;
  - missing classified events;
  - missing operator summary;
  - no runs;
  - invalid/path-traversal run_id;

- tests for builder, CLI, artifacts, UI read-model and security boundaries;

- docs update:
  - `docs/ROADMAP.md`;
  - `README.md`;
  - `docs/WEB_UI.md`;
  - `docs/DEV_GUIDE.md`, if command/API behavior changes.

**Excluded:**

- Bitrix write-back;
- `crm.item.add`;
- `crm.item.update`;
- task creation;
- timeline comments;
- manager scoring;
- 1C integration;
- mailbox listener/polling;
- web-triggered ROP run;
- auth/RBAC;
- Control Panel;
- operator POST actions;
- editing review labels in UI;
- changes to `beeagent-rop`;
- ROP business rules in BeeAgent core;
- AI recommendation generation;
- new dependencies unless strictly required.

#### Deliverable

BeeAgent can build and expose a stable current-state ROP read-model:

```bash
./start.sh rop current --run-id <run_id>
```

Expected artifacts:

```text
storage/runs/<run_id>/rop_current_state.json
storage/interfaces/rop_current.json
storage/interfaces/rop_latest.json
storage/interfaces/rop_index.json
```

The Web Console / BeeUI ROP dashboard can open `/rop` without requiring the operator to manually know a `run_id`, and it can show latest/current ROP state with Bitrix evidence queues and safe artifact links.

#### Expected current-state artifact

```json
{
  "run_id": "live-review-2026-06-19",
  "status": "ok",
  "read_only": true,
  "generated_at_utc": "2026-06-19T00:00:00Z",
  "client_id": "welding",
  "current_alias": "latest",
  "source": {
    "selection_mode": "single_explicit",
    "source_count": 1,
    "loaded_source_count": 1,
    "degraded_source_count": 0
  },
  "kpi": {
    "events_total": 20,
    "normalized_count": 20,
    "classified_count": 20,
    "high_priority": 4,
    "needs_manual_review": 6,
    "source_degraded": 0,
    "attachment_count": 3,
    "attachment_preview_available": 1,
    "attachment_refused": 1,
    "matched_in_bitrix": 8,
    "lost_in_bitrix": 5,
    "ambiguous_in_bitrix": 3,
    "connector_degraded": 0,
    "unreconciled": 0
  },
  "queues": {
    "lost_in_bitrix": [],
    "needs_review": [],
    "high_priority": [],
    "ambiguous": [],
    "matched": [],
    "unreconciled": [],
    "degraded": []
  },
  "artifact_refs": [
    {
      "artifact_id": "operator_summary_json",
      "path": "runs/<run_id>/operator_summary.json",
      "exists": true,
      "status": "ok"
    },
    {
      "artifact_id": "bitrix_reconciliation_json",
      "path": "runs/<run_id>/bitrix_reconciliation.json",
      "exists": true,
      "status": "ok"
    }
  ],
  "warnings": []
}
```

#### Current-state behavior

Rules:

```text
missing Bitrix reconciliation
→ do not count as lost_in_bitrix
→ mark as unreconciled/no_bitrix_evidence

Bitrix not_found
→ count as lost_in_bitrix
→ needs_manual_review=true

Bitrix ambiguous / duplicate_candidate
→ count as ambiguous_in_bitrix
→ needs_manual_review=true

Bitrix matched_*
→ count as matched_in_bitrix

Bitrix connector_degraded / error
→ count as connector_degraded
→ do not treat as not_found

optional Bitrix artifact appears stale/malformed/mismatched
→ show warning
→ do not silently trust it as current evidence
```

Important rule:

```text
not_found != connector failure
missing/stale artifact != not_found
```

#### BeeUI / Web Console impact

The BeeAgent UI adapter should use current-state artifacts as the primary source for `/rop` and `/api/rop/dashboard` when available.

Expected ROP dashboard sections:

- Overview;
- Queue;
- Sources;
- Attachments;
- Bitrix;
- Evidence.

Bitrix tab should no longer be reserved-only when current-state/Bitrix evidence exists.

BeeUI must remain generic:

```text
BeeUI renders.
BeeAgent adapter decides.
```

No ROP-specific business logic should be added to BeeUI generic framework.

#### Expected UI blocks

Use existing adapter-backed `layout[]` block types:

- `state_grid`;
- `kpi_grid`;
- `event_table`;
- `status_table`;
- `attention_list`;
- `artifact_links`;
- `group`;
- `degraded`.

#### Artifacts

New:

```text
storage/runs/<run_id>/rop_current_state.json
storage/interfaces/rop_current.json
storage/interfaces/rop_latest.json
storage/interfaces/rop_index.json
```

Existing artifacts read:

```text
storage/runs/<run_id>/source_diagnostics.json
storage/runs/<run_id>/intake_metadata.json
storage/runs/<run_id>/attachment_extraction.json
storage/runs/<run_id>/normalized_events.json
storage/runs/<run_id>/classified_events.json
storage/runs/<run_id>/bitrix_reconciliation.json
storage/runs/<run_id>/operator_summary.json
storage/runs/<run_id>/rop_review_table.tsv
```

#### Change level

```text
security-sensitive
```

Reason:

- artifact restore/parsing;
- file/path handling;
- UI/API exposure of client operational data;
- artifact allowlist update;
- malformed/stale artifact handling;
- read-only Web/API behavior.

No new external connector is added in this iteration.

#### Checks

Required:

```bash
uv run pytest -q
uv run pytest -q -k "rop or web or ui"
```

Targeted tests:

```text
current-state builder with normal run
current-state builder without Bitrix artifact
current-state builder with matched Bitrix artifact
current-state builder with not_found Bitrix artifact
current-state builder with ambiguous/duplicate Bitrix artifact
current-state builder with connector_degraded Bitrix artifact
current-state builder with stale/malformed Bitrix artifact
current-state builder rejects path traversal run_id
CLI rop current creates per-run and interface artifacts
rop run updates current-state
successful reconcile-bitrix updates current-state
failed reconcile-bitrix does not create false success state
/api/rop/dashboard includes current-state/Bitrix KPI fields
/rop renders degraded state when current-state is missing
artifact allowlist includes rop_current_state_json and bitrix_reconciliation_json
secrets/raw .eml/attachment content are not exposed
```

Smoke:

```bash
uv run python config/start.py rop run \
  --source-id rop_batch_sample \
  --items-max 2 \
  --run-id smoke-it27-current

uv run python config/start.py rop current \
  --run-id smoke-it27-current

uv run python config/start.py rop summary \
  --run-id smoke-it27-current

uv run python config/start.py web --host 127.0.0.1 --port 8780 --no-open
```

Optional live Bitrix smoke only if credentials are available and explicitly approved.

Security checks:

- SAST required;
- SCA only if dependencies change;
- lightweight DAST-style route/runtime misuse checks for `/rop`, `/api/rop/dashboard`, artifact routes;
- IAST not required;
- fuzzing optional only for malformed artifact restore tests.

#### DoD

- `rop_current_state.json` is created for a valid ROP run;
- `storage/interfaces/rop_current.json`, `rop_latest.json`, `rop_index.json` are created/updated;
- `/rop` can show latest/current ROP state without requiring manual run_id;
- current-state distinguishes:
  - Bitrix `not_found`;
  - missing Bitrix artifact;
  - stale/malformed Bitrix artifact;
  - connector degraded/error;

- lost-in-Bitrix queue is based only on valid Bitrix `not_found`, not on missing/degraded evidence;
- Bitrix matched/ambiguous/duplicate/manual-review queues are visible in current-state;
- UI/API expose only read-only data;
- no POST/write/action route is added;
- no Bitrix write-back exists;
- no `beeagent-rop` code is changed;
- BeeAgent core does not contain ROP classification/business rules;
- artifact access remains allowlisted;
- path traversal is blocked;
- secrets/raw `.eml`/attachment content are not exposed;
- tests and docs are updated;
- required security checks are completed;
- `pyproject.toml.version` is not changed.

### Iteration 27.1 — ROP Business Dashboard UX + Period Analytics v0

**Status:** DONE

#### Goal

Make ROP dashboard in BeeAgent a product for ROP: replace technical run/artifact overview by business-facing dashboard with periods, business metrics, chart-ready series, Bitrix evidence, operator queues and deterministic recommendations based on existing ROP artifacts/current-state.

Iteration must use the already closed BeeUI It13.6:

```text
chart
data_table
kpi_grid
state_grid
attention_list
artifact_links
group
degraded
```

BeeUI remains generic renderer:

```text
BeeUI renders.
BeeAgent adapter decides.
```

BeeAgent must give normalized ROP dashboard read-model and `layout[]` but must not transfer classification, customer rules or Bitrix write-back. to core

#### Why this is needed

After It27 BeeAgent creates current-state artifacts:

```text
storage/runs/<run_id>/rop_current_state.json
storage/interfaces/rop_current.json
storage/interfaces/rop_latest.json
storage/interfaces/rop_index.json
```

But the current `/rop` UI still looks like debug/interface layer:

```text
run_id list
n/a values
generic metrics
empty Bitrix unavailable card
```

For MVP the customer and the OPP need not a list of technical run_id but an operating painting:

```text
what arrived during the period
how many leads were processed
What sources are working?
What are the important messages
What addresses are not found in Bitrix
where ambiguous / duplicates
That ROP must be tested first.
which evidence artifacts to open
```

Iteration closes the gap between backend current-state artifacts and customer-facing ROP dashboard.

#### Scope

**Included**

- Add BeeAgent-owned ROP dashboard read-model builder above existing It27 artifacts;
- Use `rop_current_state.json`, `rop_index.json`, `rop_latest.json`, `operator_summary.json`, `classified_events.json`, `bitrix_reconciliation.json`, `attachment_extraction.json`, `rop_review_table.tsv`;
- Add period support:
  - `today`;
  - `yesterday`;
  - `7d`;
  - `30d`;
  - `365d`;
  - `all`;
- Add config/source-of-truth for dashboard period behavior in `config/settings.yml`, if no such block is available:

```yaml
rop:
  dashboard:
    default_period: "7d"
    periods:
      - today
      - yesterday
      - 7d
      - 30d
      - 365d
      - all
```

- Validate the new keys fail-fast in `src/beeagent_module/core/settings.py`;
- default period must be clearly specified in config and not hidden in the code;
- Add CLI command for the explicit generation of dashboard read-model:

```bash
./start.sh rop dashboard --period 7d
```

- After successful `rop run` / `rop current` update dashboard artifact for default period;
- after successful `reconcile-bitrix` update dashboard artifact;
- failed `reconcile-bitrix` must not create a false Bitrix success state;
- Create/update interface artifact:

```text
storage/interfaces/rop_dashboard.json
```

- artifact must contain dashboard payload on supported periods or default period on the explicit `period`;
- GET routes must not mutate storage;
- `/rop` must read prepared dashboard/current-state artifacts and the business dashboard list;
- `/api/rop/dashboard?period=7d` must give read-only payload;
- Save backward compatibility old API fields if they are already used by tests/UI.

#### Business KPI

ROP dashboard must display business-facing KPI:

```text
processed_events
processed_emails
new_leads
existing_clients
follow_ups
high_priority
needs_review
lost_in_bitrix
ambiguous_or_duplicate
unreconciled
source_degraded
attachment_refused
bitrix_errors
```

If part of the fields cannot be obtained from the current artifacts, the field must be clearly `0` or `n/a` with warning, but must not mask itself as a full-fledged analyst.

#### Time period behavior

Allowed query values:

```text
period=today
period=yesterday
period=7d
period=30d
period=365d
period=all
```

Dashboard payload must contain:

```json
{
  "period": "7d",
  "period_start_utc": "2026-06-13T00:00:00Z",
  "period_end_utc": "2026-06-20T23:59:59Z",
  "time_basis": "event_timestamp",
  "warnings": []
}
```

Allowed `time_basis`:

```text
event_timestamp
run_generated_at
run_mtime_fallback
mixed
unknown
```

Rules:

```text
event timestamp available
→ use event_timestamp

event timestamp missing but current-state generated_at exists
→ use run_generated_at and add warning if needed

generated_at missing
→ use run directory mtime fallback and add warning time_basis_fallback

missing time basis
→ include item only for period=all or degrade explicitly
```

#### Charts / series

If BeeUI It13.6 chart block is available, BeeAgent adapter must give chart blocks to `layout[]`.

Expected chart blocks:

```text
Processed events over time
Lead classification distribution
Bitrix evidence distribution
Source contribution by source_id/source_role
```

Example chart-ready API shape:

```json
{
  "series": {
    "processed_by_day": {
      "labels": ["2026-06-14", "2026-06-15"],
      "series": [
        { "name": "Processed", "data": [12, 18] },
        { "name": "High priority", "data": [2, 4] }
      ]
    },
    "classification_distribution": {
      "labels": ["new_lead", "follow_up", "other"],
      "series": [8, 5, 2]
    },
    "bitrix_distribution": {
      "labels": ["matched", "lost", "ambiguous", "unreconciled"],
      "series": [7, 3, 2, 4]
    }
  }
}
```

#### Data tables / queues

Use BeeUI `data_table` for operator queues:

- High-priority queue;
- Needs review queue;
- Lost in Bitrix queue;
- Ambiguous / duplicate queue;
- Unreconciled queue;
- Source degraded queue;
- Evidence table.

Expected row fields:

```text
event_id
source_id
source_display_name
sender
subject
bot_case_type
bot_priority
bitrix_status
reason
recommended_next_step
run_id
evidence_href
```

#### ROP recommendations

Add deterministic ROP recommendations based on existing artifacts/current-state.

It's not AI- recommendations or client-specific classification logic.

Rules:

```text
high_priority > 0
→ recommend immediate review/call for high-priority cases

lost_in_bitrix > 0
→ recommend checking CRM gap / manual lead review

ambiguous_or_duplicate > 0
→ recommend resolving duplicate/ambiguous Bitrix matches

unreconciled > 0 and Bitrix artifact missing
→ recommend running read-only Bitrix reconciliation

connector_degraded > 0
→ recommend checking Bitrix connector

source_degraded > 0
→ recommend checking source/mailbox ingestion

attachment_refused > 0
→ recommend manual review of refused attachment metadata
```

Expected recommendation item:

```json
{
  "severity": "warning",
  "title": "Review lost Bitrix leads",
  "detail": "3 classified events were not found in Bitrix.",
  "reason_code": "lost_in_bitrix",
  "count": 3,
  "read_only": true,
  "action_type": "manual_review",
  "evidence_href": "/rop?tab=bitrix&period=7d"
}
```

#### Bitrix Evidence Board behavior

Bitrix tab/section must be useful even when Bitrix artifact is missing.

Rules:

```text
valid Bitrix evidence exists
→ show matched/lost/ambiguous/duplicate tables and chart

Bitrix artifact missing
→ show status "Not reconciled"
→ show unreconciled count
→ show next step: run read-only reconcile-bitrix
→ do not call it "Bitrix unavailable" unless connector failure is actually known

Bitrix connector degraded/error
→ show connector degraded state
→ do not treat as not_found

Bitrix not_found
→ count as lost_in_bitrix

missing/stale/malformed Bitrix artifact
→ warning, no false lost_in_bitrix count
```

Important invariant:

```text
not_found != connector failure
missing/stale Bitrix artifact != not_found
```

#### UI layout expectation

`/rop` should become a product dashboard, not a debug run list.

Expected tabs:

```text
Overview
Queue
Sources
Attachments
Bitrix
Evidence
```

Overview should show:

- period selector;
- business KPI cards;
- charts;
- top recommendations;
- compact current state;
- key evidence links.

Technical run list may remain only as compact selector or Evidence/Debug area, not the main content.

#### API expectation

`GET /api/rop/dashboard?period=7d`

Expected payload:

```json
{
  "run_id": "smoke-it27-current",
  "selected_run_id": "smoke-it27-current",
  "period": "7d",
  "time_basis": "run_generated_at",
  "read_only": true,
  "business_kpi": {
    "processed_events": 2,
    "processed_emails": 2,
    "new_leads": 1,
    "existing_clients": 0,
    "follow_ups": 1,
    "high_priority": 1,
    "needs_review": 0,
    "lost_in_bitrix": 0,
    "ambiguous_or_duplicate": 0,
    "unreconciled": 2,
    "source_degraded": 0,
    "attachment_refused": 0,
    "bitrix_errors": 0
  },
  "series": {},
  "queues": {},
  "rop_recommendations": [],
  "evidence_links": [],
  "warnings": []
}
```

Backward-compatible fields should remain if currently exposed:

```text
available_runs
kpis
funnel
source_health
classification_distribution
recommendations
current_state_kpi
current_state_queues
bitrix
```

#### Artifacts

New / updated:

```text
storage/interfaces/rop_dashboard.json
```

Existing read:

```text
storage/interfaces/rop_current.json
storage/interfaces/rop_latest.json
storage/interfaces/rop_index.json
storage/runs/<run_id>/rop_current_state.json
storage/runs/<run_id>/operator_summary.json
storage/runs/<run_id>/classified_events.json
storage/runs/<run_id>/attachment_extraction.json
storage/runs/<run_id>/bitrix_reconciliation.json
storage/runs/<run_id>/rop_review_table.tsv
```

#### Config / contract impact

Expected:

- `config/settings.yml` changes if `rop.dashboard` does not already exist;
- fail-fast validation in `src/beeagent_module/core/settings.py`;
- artifact contract change:
  - `storage/interfaces/rop_dashboard.json`;

- API contract change:
  - `/api/rop/dashboard?period=...`;

- UI adapter/read-model behavior change;
- docs update required.

#### Excluded

- Bitrix write-back;
- `crm.item.add`;
- `crm.item.update`;
- task creation;
- timeline comments;
- manager scoring;
- 1C integration;
- mailbox listener/polling;
- web-triggered ROP run;
- auth/RBAC;
- Control Panel;
- POST/operator actions;
- editing review labels in UI;
- changes to `beeagent-rop`;
- AI recommendation generation;
- arbitrary ApexCharts options;
- BeeUI core changes, unless a real incompatibility is found;
- DataTables/List.js runtime.

#### Change level

```text
security-sensitive
```

Reason:

- artifact restore/parsing;
- file/path handling;
- UI/API exposure of client operational data;
- serialization into BeeUI `chart` and `data_table` blocks;
- config validation if `rop.dashboard` is added;
- malformed/stale artifact handling;
- read-only Web/API behavior.

No new external connector is added in this iteration.

#### Checks

Required:

```bash
uv run pytest -q
uv run pytest -q -k "rop or web or ui"
```

Targeted tests:

```text
settings validation for rop.dashboard.default_period
settings validation for allowed dashboard periods
dashboard builder with normal current-state
dashboard builder with no Bitrix artifact
dashboard builder with valid Bitrix matched/not_found/ambiguous/degraded data
dashboard builder with stale/malformed Bitrix artifact
period parser accepts today/yesterday/7d/30d/365d/all
period parser rejects unsafe/unknown values
time_basis fallback is explicit
business_kpi is present in API
chart-ready series are present
data_table queue blocks are present in layout
deterministic recommendations are generated
missing Bitrix artifact produces Not reconciled state, not Bitrix unavailable
lost_in_bitrix uses only valid Bitrix not_found
/rop renders business overview, not primary debug run list
/api/rop/dashboard?period=7d works
GET routes do not mutate storage
path traversal run_id/query attempts are rejected/degraded
artifact links remain allowlisted
secrets/raw .eml/attachment content are not exposed
```

Smoke:

```bash
uv run python config/start.py rop run \
  --source-id rop_batch_sample \
  --items-max 2 \
  --run-id smoke-it27-1-business-dashboard

uv run python config/start.py rop current \
  --run-id smoke-it27-1-business-dashboard

uv run python config/start.py rop dashboard \
  --period 7d

uv run python config/start.py web \
  --host 127.0.0.1 \
  --port 8780 \
  --no-open
```

Manual browser/API checks:

```text
GET /rop
GET /rop?period=today
GET /rop?period=7d
GET /rop?tab=bitrix&period=7d
GET /api/rop/dashboard?period=7d
GET /api/rop/dashboard?period=invalid
```

Security checks:

```text
SAST required
SCA only if dependencies change
lightweight DAST-style route/API misuse checks required for /rop and /api/rop/dashboard
IAST not required
fuzzing optional only for malformed artifact restore tests
```

Secret/content grep:

```bash
grep -R "https://.*bitrix\|/rest/[0-9]\|password\|secret\|token\|raw_eml\|message/rfc822\|attachment_content\|content_bytes" \
  logs storage/runs/smoke-it27-1-business-dashboard storage/interfaces -n || true
```

#### DoD

- `/rop` reads like a ROP business dashboard, not a debug artifact browser;
- period selector works for supported periods;
- `storage/interfaces/rop_dashboard.json` is created/updated;
- `/api/rop/dashboard?period=7d` includes `business_kpi`, `series`, `queues`, `rop_recommendations`;
- chart blocks are returned for BeeUI when chart data exists;
- data_table blocks are returned for operator queues;
- Bitrix Board shows useful states:
  - matched;
  - lost/not_found;
  - ambiguous/duplicate;
  - unreconciled;
  - connector degraded;
  - missing/stale artifact warning;
- `not_found`, missing evidence and connector failure are not confused;
- recommendations are deterministic and read-only;
- technical run list is not the primary Overview content;
- GET routes do not mutate storage;
- no POST/write/action route is added;
- no Bitrix write-back exists;
- no `beeagent-rop` code is changed;
- BeeAgent core does not contain ROP classification rules;
- config/source-of-truth is explicit if new dashboard keys are added;
- path traversal is blocked;
- secrets/raw `.eml`/attachment content are not exposed;
- tests and docs are updated;
- required security checks are completed;
- `pyproject.toml.version` is not changed.

#### Implemented

- `src/beeagent_module/cases/rop_dashboard.py` is a new module:
  - `ALLOWED_PERIODS` is a constant with supported periods;
  - `parse_period(period)` is a period parsing in `{period, period_start_utc, period_end_utc, time_basis}`;
  - `validate_period(period)` is the period validation against ALLOWED_PERIODS;
  - `build_rop_dashboard(storage_dir, period, logger, run_id=None)` is the construction of dashboard read-model;
  - `write_rop_dashboard(storage_dir, dashboard, logger)` is a record of the `storage/interfaces/rop_dashboard.json` artifact;
- `config/settings.yml` – `rop.dashboard` unit added:
  - `default_period: "7d"`;
  - `periods: [today, yesterday, 7d, 30d, 365d, all]`;
- `src/beeagent_module/core/settings.py`:
  - Mandatory `rop.dashboard.default_period` and `rop.dashboard.periods` keys added;
  - `_validate_rop_dashboard_settings()` - fail-fast validation:
    - `default_period` — non-empty string, must be in allowlist;
    - `periods` is non-empty list, each element in allowlist;
    - `default_period` must be in `periods`;
- `src/beeagent_module/core/cli.py`:
  - `handle_rop_dashboard(args, settings, logger)` - CLI handler added;
  - `dashboard` subparser with `--period` and `--run-id`;
  - after the successful `rop run` is automatically built dashboard for default period;
  - after successful `rop current` is automatically built dashboard;
  - after successful `reconcile-bitrix` is automatically built dashboard;
- Dashboard read-model contains:
  - `business_kpi` — processed_events, new_leads, existing_clients, follow_ups, high_priority, needs_review, lost_in_bitrix, ambiguous_or_duplicate, unreconciled, source_degraded, attachment_refused;
  - `series` — processed_by_day, classification_distribution, bitrix_distribution, source_contribution;
  - `queues` — high_priority, needs_review, lost_in_bitrix, unreconciled;
  - `rop_recommendations` - deterministic Recommendations on high_priority, lost_in_bitrix, ambiguous/duplicate, unreconciled, source_degraded, attachment_refused;
  - `evidence_links` is a reference to all allowlisted artifact_id for this run;
- Dashboard supports period filtering: `today`, `yesterday`, `7d`, `30d`, `365d`, `all`;
- `src/beeagent_module/interfaces/ui/read_model.py`:
  - `build_rop_dashboard_read_model` already uses `beeagent_module.cases.rop_dashboard.parse_period/validate_period`;
  - `/api/rop/dashboard?period=7d` gives `business_kpi`, `series`, `queues`, `rop_recommendations`;
  - `/rop` Overview – business KPI cards, charts, recommendations, compact run selector;
- CLI entrypoint:

```bash
./start.sh rop dashboard --period 7d
./start.sh rop dashboard --period today --run-id <run_id>
./start.sh rop dashboard --period all
```

- Artifact: `storage/interfaces/rop_dashboard.json`;
- Dashboard is automatically updated after `rop run`, `rop current` and `reconcile-bitrix`;
- `./start.sh web` – `/rop` and `/api/rop/dashboard` support `period` query parameter;
- Tests: `tests/test_rop_dashboard.py` — period parsing, build, write, no-bitrix, empty, settings validation;
- Docs: `docs/ROADMAP.md`, `README.md`, `docs/WEB_UI.md`, `docs/DEV_GUIDE.md` updated.

### Iteration 28 — ROP MVP handoff / readiness pack v0

**Status:** DONE

#### Goal

Gather the current ROP MVP evidence chain in a single-sell handoff/readiness pack to demonstrate to the customer: BeeAgent must produce customer/demo-ready artifacts explaining what was processed and classified, what was found/not found in Bitrix, which queues require ROP attention, what limitations remain and which evidence artifacts support the conclusion.

#### Why this is needed

After It24-It27.1 BeeAgent can already:

```text
multi-source ingestion
→ attachment extraction evidence
→ beeagent-rop classification
→ Bitrix read-only reconciliation
→ current-state index
→ business dashboard with periods/queues/recommendations
```

But the result is still distributed by the number of artifacts and UI- sections:

```text
classified_events.json
attachment_extraction.json
bitrix_reconciliation.json
rop_current_state.json
rop_dashboard.json
rop_review_table.tsv
operator_summary.json
/rop dashboard
```

For MVP the customer needs a single handoff artifact: instead of a technical JSON set.

```text
Here's the current picture.
That's what the bot found.
That's what didn't get into Bitrix.
here is who needs to take action
Here's evidence
here are the constraints
Here's what's ready for demo.
That's what's not production/write-back.
```

This iteration closes the MVP handoff layer without adding CRM write-back, new connectors, AI- recommendations or domain rules to BeeAgent core.

#### Scope

**Includes:**

- Add BeeAgent-owned MVP pack builder above existing ROP artifacts;

- read only existing artifacts:
  - `operator_summary.json`;
  - `source_diagnostics.json`;
  - `intake_metadata.json`;
  - `normalized_events.json`;
  - `classified_events.json`;
  - `attachment_extraction.json`;
  - `bitrix_reconciliation.json`;
  - `rop_current_state.json`;
  - `rop_review_table.tsv`;
  - `storage/interfaces/rop_dashboard.json`;

- Add CLI command:

```bash
./start.sh rop mvp-pack --run-id <run_id> --period 7d
```

- create per-run artifacts:

```text
storage/runs/<run_id>/rop_mvp_pack.json
storage/runs/<run_id>/rop_mvp_report.md
```

- Create/update interface artifact:

```text
storage/interfaces/rop_mvp_latest.json
```

- include in pack:
  - run identity;
  - selected period;
  - source coverage;
  - configured/enabled/loaded/degraded sources;
  - processed events/emails;
  - new leads;
  - existing/follow-up cases;
  - high-priority queue;
  - needs-review queue;
  - lost-in-Bitrix queue;
  - ambiguous/duplicate queue;
  - unreconciled queue;
  - attachment refused/unsupported summary;
  - source degraded summary;
  - deterministic first actions for ROP;
  - evidence links;
  - demo readiness status;
  - known limitations;
  - explicit non-production/write-back status;

- Use existing `rop.sources[]` as source of truth for configured source coverage;

- Do not hard-code Welding mailbox names;

- if expected source coverage is not given in config, not to make up missing sources, but to show only configured/enabled/loaded/degraded coverage;

- Add safe artifact links for MVP pack/report in UI Evidence area if available;

- Add artifacts allowlist entries if needed;

- graceful degraded behavior:
  - missing dashboard artifact;
  - missing current-state artifact;
  - missing Bitrix artifact;
  - stale/malformed optional artifact;
  - missing TSV;
  - no runs;
  - invalid/path-traversal run_id;

- tests for builder, CLI, artifacts, report rendering, UI allowlist and security boundaries;

- docs update:
  - `docs/ROADMAP.md`;
  - `README.md`;
  - `docs/DEV_GUIDE.md`;
  - `docs/WEB_UI.md`, if UI/API/artifact links change.

**Excluded:**

- Bitrix write-back;
- `crm.item.add`;
- `crm.item.update`;
- task creation;
- timeline comments;
- manager scoring;
- 1C integration;
- open registry checks;
- mailbox listener/polling;
- web-triggered ROP run;
- auth/RBAC;
- Control Panel;
- POST/operator actions;
- editing review labels in UI;
- OCR/PDF/DOCX/XLSX deep parsing;
- AI recommendation generation;
- changes to `beeagent-rop`;
- ROP classification/business rules in BeeAgent core;
- removal of legacy `src/beeagent_module/web`.

#### Deliverable

BeeAgent can build a customer/demo-ready MVP handoff pack for a selected ROP run:

```bash
./start.sh rop mvp-pack \
  --run-id mvp-welding-2026-06-22 \
  --period 7d
```

Expected artifacts:

```text
storage/runs/<run_id>/rop_mvp_pack.json
storage/runs/<run_id>/rop_mvp_report.md
storage/interfaces/rop_mvp_latest.json
```

The pack/report should let the team demonstrate the MVP without asking the customer to inspect raw JSON/TSV files.

#### Expected pack shape

```json
{
  "run_id": "mvp-welding-2026-06-22",
  "period": "7d",
  "status": "ready_with_limitations",
  "read_only": true,
  "generated_at_utc": "2026-06-22T00:00:00Z",
  "client_id": "welding",
  "source_coverage": {
    "configured_sources": 2,
    "enabled_sources": 2,
    "loaded_sources": 1,
    "degraded_sources": 1,
    "warnings": []
  },
  "business_summary": {
    "processed_events": 50,
    "processed_emails": 50,
    "new_leads": 12,
    "existing_clients": 18,
    "follow_ups": 8,
    "high_priority": 6,
    "needs_review": 10,
    "lost_in_bitrix": 4,
    "ambiguous_or_duplicate": 3,
    "unreconciled": 0,
    "source_degraded": 1,
    "attachment_refused": 2,
    "bitrix_errors": 0
  },
  "queues": {
    "first_actions": [],
    "high_priority": [],
    "needs_review": [],
    "lost_in_bitrix": [],
    "ambiguous_or_duplicate": [],
    "unreconciled": []
  },
  "demo_readiness": {
    "status": "ready_with_limitations",
    "ready_items": [],
    "limitations": [],
    "blockers": []
  },
  "evidence_links": [],
  "warnings": []
}
```

#### Report behavior

`rop_mvp_report.md` should be human-readable and customer-demo oriented.

Expected sections:

```text
# ROP MVP Handoff Report

## Executive summary
## Period and run
## Source coverage
## Business KPI
## First actions for ROP
## Queues
## Bitrix evidence
## Attachment evidence
## Evidence artifacts
## Known limitations
## Not included in MVP
## Recommended next step
```

The report must not include secrets, raw `.eml`, raw attachment content or Bitrix webhook URLs.

#### Artifacts

New:

```text
storage/runs/<run_id>/rop_mvp_pack.json
storage/runs/<run_id>/rop_mvp_report.md
storage/interfaces/rop_mvp_latest.json
```

Existing read:

```text
storage/interfaces/rop_dashboard.json
storage/interfaces/rop_current.json
storage/interfaces/rop_latest.json
storage/interfaces/rop_index.json
storage/runs/<run_id>/rop_current_state.json
storage/runs/<run_id>/operator_summary.json
storage/runs/<run_id>/source_diagnostics.json
storage/runs/<run_id>/intake_metadata.json
storage/runs/<run_id>/normalized_events.json
storage/runs/<run_id>/classified_events.json
storage/runs/<run_id>/attachment_extraction.json
storage/runs/<run_id>/bitrix_reconciliation.json
storage/runs/<run_id>/rop_review_table.tsv
```

#### Change level

```text
security-sensitive
```

Reason:

- artifact restore/parsing;
- file/path handling;
- Markdown/JSON serialization of customer operational data;
- UI/API exposure of handoff artifacts;
- artifact allowlist update;
- malformed/stale artifact handling.

No new external connector is added in this iteration.

#### Checks

Required:

```bash
uv run pytest -q
uv run pytest -q -k "rop or web or ui"
```

Targeted tests:

```text
MVP pack builder with full artifact set
MVP pack builder without Bitrix artifact
MVP pack builder with connector degraded Bitrix artifact
MVP pack builder with missing/malformed dashboard artifact
MVP pack builder with missing TSV
source coverage from configured rop.sources
no hardcoded Welding source names
CLI rop mvp-pack creates per-run artifacts
CLI rop mvp-pack updates storage/interfaces/rop_mvp_latest.json
Markdown report contains expected sections
Markdown report does not contain secrets/raw .eml/raw attachment content
artifact allowlist includes rop_mvp_pack_json and rop_mvp_report_md if UI links are added
/rop Evidence area shows MVP pack/report links if available
GET routes do not mutate storage
invalid/path-traversal run_id rejected/degraded
```

Smoke:

```bash
uv run python config/start.py rop run \
  --source-id rop_batch_sample \
  --items-max 2 \
  --run-id smoke-it28-mvp-pack

uv run python config/start.py rop current \
  --run-id smoke-it28-mvp-pack

uv run python config/start.py rop dashboard \
  --period 7d \
  --run-id smoke-it28-mvp-pack

uv run python config/start.py rop mvp-pack \
  --period 7d \
  --run-id smoke-it28-mvp-pack
```

Security checks:

```text
SAST required
SCA only if dependencies change
lightweight DAST-style route/API misuse checks if UI artifact links/routes change
IAST not required
fuzzing optional only for malformed artifact restore tests
```

Secret/content grep:

```bash
grep -R "https://.*bitrix\|/rest/[0-9]\|password\|secret\|token\|raw_eml\|message/rfc822\|attachment_content\|content_bytes" \
  logs storage/runs/smoke-it28-mvp-pack storage/interfaces -n || true
```

#### DoD

- `rop_mvp_pack.json` is created for a valid ROP run;
- `rop_mvp_report.md` is created for a valid ROP run;
- `storage/interfaces/rop_mvp_latest.json` is updated after successful `rop mvp-pack`;
- pack summarizes business state, queues, Bitrix evidence, attachment evidence, source coverage, first actions and limitations;
- source coverage is derived from `config/settings.yml -> rop.sources[]`, not hardcoded mailbox names;
- missing Bitrix evidence is not confused with `not_found`;
- connector degraded/error is not confused with `lost_in_bitrix`;
- report is readable without opening raw JSON artifacts;
- GET routes remain read-only;
- no POST/write/action route is added;
- no Bitrix write-back exists;
- no `beeagent-rop` code is changed;
- BeeAgent core does not contain ROP classification/business rules;
- artifact access remains allowlisted;
- path traversal is blocked;
- secrets/raw `.eml`/raw attachment content are not exposed;
- tests and docs are updated;
- required security checks are completed;
- `pyproject.toml.version` is not changed.

### Iteration 29 — ROP Bitrix match quality gate and action drafts v0

**Status:** DONE

#### Goal

Make Bitrix reconciliation safe for MVP: weak/ambiguous Bitrix candidates must not be considered successful match, `not_found` must be separated from connector failure, and BeeAgent must form read-only action drafts for ROP above existing classification + Bitrix evidence.

#### Why this is needed

After It26-It28 BeeAgent already knows how to build a full ROP evidence chain:

```text
mailbox/json_batch
→ normalized_events.json
→ attachment_extraction.json
→ beeagent-rop classification
→ classified_events.json
→ Bitrix read-only reconciliation
→ current-state/dashboard/MVP pack
```

A manual test of live batch showed that classification path is already useful enough for MVP, but Bitrix evidence remains a risky area:

```text
weak/wrong Bitrix candidate
→ It looks like found/matched.
→ ROP may go to the wrong lead/deal
```

For MVP this is worse than `not_found`:

```text
not_found = honest CRM gap
wrong/weak match = dangerous false confidence
```

So before AI assist and before any Bitrix write-back, you have to enter explicit match quality gate:

```text
strong evidence only → matched_*
weak evidence → weak_match / ambiguous / manual_review
connector failure → connector_degraded / error
no candidate → not_found
```

This iteration remains in `beeagent`, because Bitrix connector, reconciliation artifacts, dashboard/current-state/MVP pack and action drafts belong to BeeAgent orchestration layer. `beeagent-rop` continues to be responsible for the classification semantics. domain.

#### Scope

**Includes:**

- Strengthen BeeAgent-owned Bitrix reconciliation quality gate;
- Save read-only Bitrix boundary;
- do not count weak/subject-only/random candidate as successful match;
- Add/specify reconciliation status:

```text
matched_lead
matched_deal
matched_contact
matched_company
not_found
ambiguous
duplicate_candidate
weak_match
skipped
connector_degraded
error
```

- Add explicit match quality fields to `bitrix_reconciliation.json`:

```text
bitrix_match_status
bitrix_match_quality
bitrix_confidence
needs_manual_review
safe_to_use_as_target
bitrix_match_reason
reconciliation_reason
candidate_count
candidate_summary
```

- Rule:

```text
weak subject/title-only match
or random low-evidence phone/title candidate
or multiple weak candidates
→ weak_match or ambiguous
→ needs_manual_review=true
→ safe_to_use_as_target=false
→ not counted as successful matched
```

- Save invariant:

```text
not_found != connector failure
missing Bitrix artifact != not_found
weak_match != matched
ambiguous != matched
```

- Add aggregate counts to `bitrix_reconciliation.json`:

```text
event_count
safe_matched_count
matched_count
weak_match_count
not_found_count
ambiguous_count
duplicate_candidate_count
skipped_count
connector_degraded_count
error_count
manual_review_count
```

- Add BeeAgent-owned action draft artifact:

```text
storage/runs/<run_id>/rop_action_drafts.json
```

- action drafts is built only from existing artifacts:
  - `normalized_events.json`;
  - `classified_events.json`;
  - `bitrix_reconciliation.json`;
  - optional `attachment_extraction.json`;
  - optional `rop_current_state.json`;

- action draft must be read-only/draft-only and not CRM write-back;

- action draft item must contain:

```text
action_draft_id
event_id
run_id
source_id
bot_case_type
bitrix_match_status
queue
recommended_action
recommended_next_step
priority
reason_code
needs_manual_review
safe_to_use_as_target
target_entity_type
target_entity_id
evidence_refs
read_only
```

- recommended action mapping v0:

```text
new_lead + not_found
→ lost_in_bitrix / check CRM gap / create lead manually

new_lead + matched_lead
→ review existing lead / update manually if needed

existing_deal + matched_deal
→ review deal / add comment or document manually

existing_deal + weak_match|ambiguous
→ choose correct Bitrix entity manually

ambiguous|duplicate_candidate
→ resolve candidate manually

irrelevant
→ ignore

connector_degraded|error
→ check Bitrix connector

missing Bitrix evidence
→ run read-only reconciliation
```

- Add CLI command:

```bash
./start.sh rop action-drafts --run-id <run_id>
```

- automatically update `rop_action_drafts.json` after successful `reconcile-bitrix`;
- do not create a false success state after failed `reconcile-bitrix`;
- `rop export-review` must enrich TSV, if there are `bitrix_reconciliation.json` and/or `rop_action_drafts.json`;
- Save backward compatibility old TSV columns;
- Add new TSV columns if not yet available:

```text
bitrix_match_status
bitrix_match_quality
bitrix_confidence
needs_manual_review
safe_to_use_as_target
recommended_action
recommended_next_step
action_queue
action_draft_id
```

- Update current-state/dashboard/MVP pack read-model minimum:
  - `weak_match` is visible as manual-review/ambiguous risk;
  - `safe_matched_count` is separated from just `matched_count`;
  - action drafts is available on Evidence / First actions;
  - `lost_in_bitrix` is considered only for valid `not_found`, not for missing/degraded Bitrix evidence;

- Add artifact allowlist entry if UI/Evidence links refers to a new artifact:

```text
rop_action_drafts_json
```

- graceful degraded behavior:
  - missing Bitrix artifact;
  - malformed Bitrix artifact;
  - stale/mismatched run_id;
  - missing classified events;
  - empty candidates;
  - connector degraded/error;
  - path traversal attempt through run_id;

- tests for reconciliation quality gate, action drafts, TSV enrichment, current/dashboard/MVP pack read-model impact and security boundaries;

- docs update:
  - `docs/ROADMAP.md`;
  - `README.md`;
  - `docs/DEV_GUIDE.md`;
  - `docs/WEB_UI.md` if UI/API artifact links changes.

**Excluded:**

- Bitrix write-back;
- `crm.item.add`;
- `crm.item.update`;
- `crm.item.delete`;
- task creation;
- timeline comments;
- lead creation;
- deal update;
- auto-assign responsible;
- automatic CRM actions;
- AI classification;
- AI recommendation generation;
- changes to `beeagent-rop`;
- ROP classification/business rules in BeeAgent core;
- OCR;
- PDF/DOCX/XLSX deep parsing;
- 1C integration;
- manager scoring;
- mailbox listener/polling;
- web-triggered ROP run;
- POST/operator action routes;
- auth/RBAC;
- Control Panel.

#### Deliverable

BeeAgent can run safer Bitrix reconciliation and produce explicit ROP action drafts:

```bash
./start.sh rop reconcile-bitrix --run-id <run_id>

./start.sh rop action-drafts --run-id <run_id>

./start.sh rop export-review --run-id <run_id> --format tsv
```

Expected artifacts:

```text
storage/runs/<run_id>/bitrix_reconciliation.json
storage/runs/<run_id>/rop_action_drafts.json
storage/runs/<run_id>/rop_review_table.tsv
```

The dashboard/current-state/MVP pack can distinguish:

```text
safe matched
weak match
ambiguous
duplicate candidate
not found
connector degraded
missing Bitrix evidence
```

#### Expected `bitrix_reconciliation.json` behavior

Strong exact evidence:

```json
{
  "event_id": "evt-001",
  "bitrix_match_status": "matched_lead",
  "bitrix_match_quality": "strong",
  "bitrix_confidence": 0.95,
  "needs_manual_review": false,
  "safe_to_use_as_target": true,
  "bitrix_match_reason": "sender_email_exact",
  "reconciliation_reason": "Exact sender email candidate found in Bitrix lead list."
}
```

Weak title/subject-only candidate:

```json
{
  "event_id": "evt-002",
  "bitrix_match_status": "weak_match",
  "bitrix_match_quality": "weak",
  "bitrix_confidence": 0.45,
  "needs_manual_review": true,
  "safe_to_use_as_target": false,
  "bitrix_match_reason": "subject_title_weak",
  "reconciliation_reason": "Only weak title/subject candidate was found; candidate is not safe for automatic targeting."
}
```

No candidate while connector is healthy:

```json
{
  "event_id": "evt-003",
  "bitrix_match_status": "not_found",
  "bitrix_match_quality": "none",
  "bitrix_confidence": 0.0,
  "needs_manual_review": true,
  "safe_to_use_as_target": false,
  "bitrix_match_reason": "no_candidate_found",
  "reconciliation_reason": "Bitrix was reachable, but no candidate was found."
}
```

Connector failure:

```json
{
  "event_id": "evt-004",
  "bitrix_match_status": "connector_degraded",
  "bitrix_match_quality": "degraded",
  "bitrix_confidence": 0.0,
  "needs_manual_review": true,
  "safe_to_use_as_target": false,
  "bitrix_match_reason": "connector_error",
  "reconciliation_reason": "Bitrix connector failed; result must not be treated as not_found."
}
```

#### Expected `rop_action_drafts.json`

```json
{
  "run_id": "mvp-welding-live-hardening-20260624-0735",
  "status": "ok",
  "read_only": true,
  "draft_only": true,
  "generated_at_utc": "2026-06-24T00:00:00Z",
  "aggregate": {
    "action_count": 20,
    "manual_review_count": 8,
    "safe_target_count": 5,
    "lost_in_bitrix_count": 3,
    "ambiguous_count": 2,
    "connector_degraded_count": 0
  },
  "items": [
    {
      "action_draft_id": "evt-001-action",
      "event_id": "evt-001",
      "run_id": "mvp-welding-live-hardening-20260624-0735",
      "source_id": "hotline_mailbox",
      "bot_case_type": "new_lead",
      "bitrix_match_status": "not_found",
      "queue": "lost_in_bitrix",
      "recommended_action": "check_crm_gap",
      "recommended_next_step": "Review as a possible lost lead in Bitrix and create/update CRM manually if confirmed.",
      "priority": "high",
      "reason_code": "new_lead_not_found_in_bitrix",
      "needs_manual_review": true,
      "safe_to_use_as_target": false,
      "target_entity_type": "",
      "target_entity_id": null,
      "evidence_refs": [
        "classified_events_json",
        "bitrix_reconciliation_json",
        "rop_review_table_tsv"
      ],
      "read_only": true
    }
  ],
  "warnings": []
}
```

#### Current-state / dashboard / MVP pack behavior

Rules:

```text
matched_in_bitrix / safe matched
→ count only safe_to_use_as_target=true or strong matched_* according to v0 rules

weak_match
→ not successful matched
→ needs_review / ambiguous queue

ambiguous / duplicate_candidate
→ ambiguous_or_duplicate queue

not_found
→ lost_in_bitrix only when Bitrix evidence is valid and connector is healthy

connector_degraded / error
→ bitrix_errors / degraded
→ not lost_in_bitrix

missing Bitrix artifact
→ unreconciled
→ not lost_in_bitrix

missing action drafts
→ dashboard remains valid and shows no action draft artifact
```

#### Artifacts

New:

```text
storage/runs/<run_id>/rop_action_drafts.json
```

Updated:

```text
storage/runs/<run_id>/bitrix_reconciliation.json
storage/runs/<run_id>/rop_review_table.tsv
storage/runs/<run_id>/rop_current_state.json
storage/interfaces/rop_current.json
storage/interfaces/rop_latest.json
storage/interfaces/rop_index.json
storage/interfaces/rop_dashboard.json
storage/runs/<run_id>/rop_mvp_pack.json
storage/runs/<run_id>/rop_mvp_report.md
storage/interfaces/rop_mvp_latest.json
```

Existing read:

```text
storage/runs/<run_id>/normalized_events.json
storage/runs/<run_id>/classified_events.json
storage/runs/<run_id>/attachment_extraction.json
storage/runs/<run_id>/operator_summary.json
storage/runs/<run_id>/bitrix_reconciliation.json
```

#### Config / contract impact

Expected:

```text
No new required config key unless implementation proves it is needed.
```

Source of truth remains:

```text
config/settings.yml -> bitrix.*
config/settings.yml -> rop.sources[]
existing ROP run artifacts in storage/runs/<run_id>/
```

If a new config key is proposed, it must be justified first and validated fail-fast in:

```text
src/beeagent_module/core/settings.py
```

#### Change level

```text
security-sensitive
```

Reason:

- external connector reconciliation logic;
- CRM evidence quality gate;
- artifact restore/parsing;
- file/path handling;
- serialization of customer operational data;
- UI/API exposure of match/action evidence;
- future write-back safety boundary.

No dependency change is expected.

#### Checks

Required:

```bash
uv run pytest -q
uv run pytest -q -k "rop or bitrix or web or ui"
```

Targeted tests:

```text
Bitrix strong exact email/phone match stays matched_*
weak subject/title-only candidate becomes weak_match
multiple weak candidates become ambiguous
multiple strong candidates become duplicate_candidate
not_found is emitted only when connector is healthy and no candidate exists
connector_degraded/error is not counted as not_found
weak_match is not counted as successful safe match
safe_to_use_as_target=false for weak_match/ambiguous/duplicate/not_found/degraded
safe_to_use_as_target=true only for strong safe matched target
action drafts generated from classified events + Bitrix reconciliation
new_lead + not_found creates lost_in_bitrix action draft
existing_deal + matched_deal creates review_deal action draft
weak_match/ambiguous creates choose_correct_entity action draft
irrelevant creates ignore action draft
connector_degraded creates connector_check action draft
TSV enrichment includes bitrix_match_status and recommended_action fields
current-state uses valid not_found only for lost_in_bitrix
dashboard exposes weak/ambiguous/safe matched counts
MVP pack includes first actions/action draft evidence when available
missing Bitrix artifact remains unreconciled, not lost_in_bitrix
malformed Bitrix/action artifact degrades safely
invalid/path-traversal run_id is rejected/degraded
```

Smoke:

```bash
uv run python config/start.py rop run \
  --source-id rop_batch_sample \
  --items-max 2 \
  --run-id smoke-it29-bitrix-quality

uv run python config/start.py rop reconcile-bitrix \
  --run-id smoke-it29-bitrix-quality

uv run python config/start.py rop action-drafts \
  --run-id smoke-it29-bitrix-quality

uv run python config/start.py rop export-review \
  --run-id smoke-it29-bitrix-quality \
  --format tsv

uv run python config/start.py rop current \
  --run-id smoke-it29-bitrix-quality

uv run python config/start.py rop dashboard \
  --period 7d \
  --run-id smoke-it29-bitrix-quality

uv run python config/start.py rop mvp-pack \
  --period 7d \
  --run-id smoke-it29-bitrix-quality
```

Optional live smoke only with explicit approval and available credentials:

```bash
RUN_ID="mvp-welding-live-hardening-20260624-0735"

uv run python config/start.py rop reconcile-bitrix --run-id "$RUN_ID"
uv run python config/start.py rop action-drafts --run-id "$RUN_ID"
uv run python config/start.py rop export-review --run-id "$RUN_ID" --format tsv
uv run python config/start.py rop current --run-id "$RUN_ID"
uv run python config/start.py rop dashboard --period 7d --run-id "$RUN_ID"
uv run python config/start.py rop mvp-pack --period 7d --run-id "$RUN_ID"
```

Security checks:

```text
SAST required
SCA only if dependencies change
lightweight DAST-style route/API misuse checks required if /rop, /api/rop/dashboard or artifact links change
IAST not required
fuzzing optional only for malformed artifact restore tests
```

Secret/content grep:

```bash
grep -R "https://.*bitrix\|/rest/[0-9]\|password\|secret\|token\|raw_eml\|message/rfc822\|attachment_content\|content_bytes" \
  logs storage/runs/smoke-it29-bitrix-quality storage/interfaces -n || true
```

#### DoD

- weak Bitrix candidates are not treated as successful matched results;
- `weak_match` status exists and is visible in artifacts;
- `safe_to_use_as_target` is false for weak/ambiguous/duplicate/not_found/degraded results;
- `not_found` is emitted only when Bitrix connector is healthy and no candidate exists;
- connector failure is represented separately from `not_found`;
- `rop_action_drafts.json` is created for a valid ROP run with Bitrix evidence;
- action drafts are read-only/draft-only and do not execute CRM changes;
- `rop export-review` enriches TSV with Bitrix match quality and recommended action fields when artifacts exist;
- current-state/dashboard/MVP pack distinguish safe matched, weak match, ambiguous, not found, connector degraded and missing evidence;
- no Bitrix write-back exists;
- no POST/write/action route is added;
- no `beeagent-rop` code is changed;
- BeeAgent core does not contain ROP classification/business rules;
- artifact access remains allowlisted;
- path traversal is blocked;
- secrets/raw `.eml`/raw attachment content are not exposed;
- tests and docs are updated;
- required security checks are completed;
- `pyproject.toml.version` is not changed.

### Iteration 30 — ROP execution MVP: latest-N, thread artifacts and bounded AI assist execution v0

**Status:** DONE

#### Goal

Bring BeeAgent ROP flow to execution-level MVP after `beeagent-rop It19.1` is closed: BeeAgent must correctly select the last N messages, build bounded thread artifacts, transfer `thread_context` to `beeagent-rop`, store subtype/queue/action enrichment in batch artifacts and add BeeAgent-owned bounded AI assist execution path for controversial events.

Iteration must connect the already ready domain contracts `beeagent-rop` to the real BeeAgent runtime:

```text
mailbox/json sources
→ latest-N selection
→ normalized_events.json
→ mail_thread_index.json
→ mail_thread_context.json
→ beeagent-rop lead_classification with thread_context
→ classified_events.json with subtype/queue/action fields
→ bounded AI assist request/provider/decision artifacts
→ operator/current/dashboard/MVP artifacts updated where existing builders support it
```

#### Why this is needed

After It29, BeeAgent can build the ROP evidence chain through the Bitrix match quality gate and read-only action drafts:

```text
source ingestion
→ attachment extraction
→ classification
→ Bitrix reconciliation
→ current-state/dashboard/MVP pack
→ action drafts
```

After `beeagent-rop It19` the module returns the more useful domain semantics:

```text
case_subtype
recommended_queue
should_rop_see
correct_action
```

After `beeagent-rop It19.1` public module path no longer loses `thread_context`.

But BeeAgent still has to close runtime gap:

```text
latest mailbox batch
→ deterministic thread evidence
→ bounded context into module
→ AI assist execution through BeeAgent-owned provider boundary
→ reproducible AI/thread artifacts
```

Without It30 BeeAgent can't move on to customer-facing MVP, because ROP will see classification and Bitrix evidence without thread-aware context and without controlled AI-assist for ambiguous/fallback cases.

#### Depends on

Required:

```text
beeagent-rop It19 — ROP case subtype taxonomy and reviewed TSV evaluation fixtures v1
beeagent-rop It19.1 — Thread context module plumbing hotfix
BeeAgent It29 — ROP Bitrix match quality gate and action drafts v0
```

Important implementation rule:

```text
Do not import private beeagent-rop internals from BeeAgent.
```

If the installed `beeagent-rop` package exposes a public AI assist module case/API, BeeAgent may use it through the public module/package contract.

If a public AI assist merge path is not available yet, BeeAgent must degrade safely:

```text
ai_assist_status = "module_contract_unavailable"
ai_assist_used = false
final classification remains deterministic
AI request/decision artifacts remain available for review
no crash
no private imports
```

#### Scope

**Includes:**

##### 1. Correct latest-N mailbox selection

Fix mailbox source selection so:

```text
items_max=N means newest N messages per source
```

Rules:

- do not rely on raw IMAP search order;
- sort by reliable mailbox/internal date descending;
- use UID/order fallback only when date is missing;
- record warning when fallback ordering is used;
- apply `items_max` after sorting;
- keep selection deterministic per source;
- no raw body or raw `.eml` in selection artifacts;
- no secrets in logs/artifacts.

Add artifact:

```text
storage/runs/<run_id>/mailbox_selection.json
```

Expected shape:

```json
{
  "run_id": "run-id",
  "strategy": "latest_n_by_internaldate_desc",
  "sources": [
    {
      "source_id": "hotline_mailbox",
      "items_max": 50,
      "selected_count": 50,
      "available_count": 120,
      "messages": [
        {
          "source_message_id": "uid-123",
          "internal_date": "2026-06-27T10:15:00Z",
          "message_id": "<bounded-message-id>",
          "subject": "bounded subject",
          "selected": true
        }
      ],
      "warnings": []
    }
  ],
  "warnings": []
}
```

##### 2. Build thread index artifact

Add BeeAgent-owned thread index artifact:

```text
storage/runs/<run_id>/mail_thread_index.json
```

Thread matching order:

```text
1. Message-ID / In-Reply-To / References
2. Same normalized subject within same source/client when reply/forward markers exist
3. Fallback single-event thread
```

Rules:

- BeeAgent builds thread evidence;
- `beeagent-rop` must not reconstruct raw mailbox threads;
- no raw `.eml`;
- no raw headers beyond bounded IDs needed for evidence;
- no attachment content.

Expected shape:

```json
{
  "run_id": "run-id",
  "threads": [
    {
      "thread_id": "thr_001",
      "source_ids": ["hotline_mailbox"],
      "event_ids": ["evt-1", "evt-2"],
      "message_ids": ["<msg1>", "<msg2>"],
      "subject_normalized": "shipping no 1",
      "participants": ["bounded@example.local"],
      "latest_event_id": "evt-2",
      "latest_at": "2026-06-27T10:20:00Z",
      "evidence": {
        "message_id_link": true,
        "references_link": true,
        "subject_fallback": false
      }
    }
  ],
  "warnings": []
}
```

##### 3. Build bounded thread context artifact

Add artifact:

```text
storage/runs/<run_id>/mail_thread_context.json
```

Rules:

- bounded summaries only;
- no raw mailbox thread reconstruction inside artifacts;
- no raw email body;
- no raw attachments;
- no secrets;
- context may support ambiguous cases;
- context must not override confident spam/noise/tender decisions inside BeeAgent.

Expected shape:

```json
{
  "run_id": "run-id",
  "contexts": [
    {
      "event_id": "evt-2",
      "thread_id": "thr_001",
      "reply_or_forward": true,
      "previous_event_ids": ["evt-1"],
      "previous_case_type": "existing_deal",
      "previous_case_subtype": "existing_deal_logistics",
      "participant_overlap": true,
      "previous_subject": "bounded previous subject",
      "previous_summary": "bounded summary, no raw email",
      "thread_context_confidence": 0.78,
      "reason_codes": ["reply_chain", "previous_existing_deal"]
    }
  ],
  "warnings": []
}
```

##### 4. Pass `thread_context` into `beeagent-rop`

For each normalized event:

```text
event
+ bounded thread_context if available
→ RopModule.handle(case_type="lead_classification")
```

Expected module output fields remain module-owned:

```text
case_type
priority
confidence
reason_code
reasoning
is_fallback
case_subtype
recommended_queue
should_rop_see
correct_action
```

Rules:

- BeeAgent only passes context and persists returned fields;
- BeeAgent does not implement ROP subtype rules;
- malformed thread context must degrade safely;
- classification must not crash the whole batch.

##### 5. Produce enriched `classified_events.json`

Update existing artifact:

```text
storage/runs/<run_id>/classified_events.json
```

Each item should include optional enrichment fields when returned by `beeagent-rop`:

```json
{
  "event_id": "evt-001",
  "case_type": "existing_deal",
  "case_subtype": "existing_deal_logistics",
  "recommended_queue": "logistics",
  "should_rop_see": true,
  "correct_action": "check_bitrix",
  "priority": "medium",
  "confidence": 0.72,
  "reason_code": "thread_context_existing_deal_candidate",
  "reasoning": "bounded explanation",
  "is_fallback": true,
  "thread_context_ref": "thr_001",
  "source_id": "hotline_mailbox",
  "sender": "bounded sender",
  "subject": "bounded subject"
}
```

Rules:

- preserve backward compatibility;
- append optional fields only;
- no raw `.eml`;
- no raw attachment content;
- no secrets.

##### 6. Add BeeAgent-owned bounded AI assist execution

Add config block if missing:

```yaml
rop:
  ai_assist:
    enabled: false
    provider: openai_compatible
    model_env: ROP_AI_MODEL
    api_key_env: CUSTOM_AI_API_KEY
    base_url_env: ROP_AI_BASE_URL
    max_events_per_run: 20
    request_timeout_seconds: 30
    min_ai_confidence: 0.70
    dry_run: false
```

Rules:

- default disabled;
- when enabled, required envs must fail fast if missing;
- secrets must never appear in HTML/API/logs/artifacts;
- ROP AI assist must not silently use unrelated `llm.enabled`;
- implementation may reuse existing HTTP/LLM helper code only if config source of truth remains `rop.ai_assist`;
- AI runs only for eligible ambiguous/fallback events;
- AI provider returns structured JSON only;
- invalid model output degrades safely;
- AI cannot execute CRM/mailbox/Bitrix actions;
- AI cannot create write-back payloads;
- AI cannot override safe deterministic guards;
- AI merge must use a public `beeagent-rop` contract if available;
- if public merge contract is unavailable, record degraded status and keep deterministic classification.

##### 7. Add AI assist artifacts

Add artifacts:

```text
storage/runs/<run_id>/rop_ai_assist_requests.json
storage/runs/<run_id>/rop_ai_assist_decisions.json
storage/runs/<run_id>/rop_ai_assist_results.json
```

Request artifact must be redacted/safe:

```json
{
  "event_id": "evt-001",
  "eligible": true,
  "request_preview": {
    "subject": "bounded",
    "body_preview": "bounded",
    "attachment_preview": "bounded",
    "thread_context_summary": "bounded"
  },
  "provider": "openai_compatible",
  "model": "redacted-or-model-name-if-not-secret"
}
```

Decision artifact:

```json
{
  "event_id": "evt-001",
  "status": "ok",
  "ai_case_type": "existing_deal",
  "case_subtype": "existing_deal_logistics",
  "recommended_queue": "logistics",
  "correct_action": "check_bitrix",
  "should_rop_see": true,
  "ai_confidence": 0.82,
  "ai_reason_code": "business_thread_context",
  "risk_flags": []
}
```

Result artifact:

```json
{
  "event_id": "evt-001",
  "ai_assist_used": true,
  "ai_assist_status": "ok",
  "final_case_type": "existing_deal",
  "final_case_subtype": "existing_deal_logistics",
  "final_recommended_queue": "logistics",
  "final_correct_action": "check_bitrix",
  "merge_reason": "validated_ai_assist_for_fallback_case",
  "warnings": []
}
```

If public `beeagent-rop` merge contract is unavailable:

```json
{
  "event_id": "evt-001",
  "ai_assist_used": false,
  "ai_assist_status": "module_contract_unavailable",
  "final_case_type": "existing_deal",
  "merge_reason": "deterministic_result_preserved",
  "warnings": ["Public beeagent-rop AI assist merge contract is not available."]
}
```

##### 8. Update existing operator artifacts where the pipeline already supports it

Update existing summaries/read-models only minimally:

```text
operator_summary.json
rop_current_state.json
storage/interfaces/rop_dashboard.json
rop_mvp_pack.json
rop_mvp_report.md
```

Add counters if relevant:

```text
latest_n_strategy
threaded_event_count
thread_context_available_count
case_subtype_counts
recommended_queue_counts
correct_action_counts
ai_assist_enabled
ai_assist_requested_count
ai_assist_used_count
ai_assist_invalid_count
ai_assist_degraded_count
```

Rules:

- do not redesign UI in It30;
- do not add auth;
- do not add row detail routes;
- do not add Bitrix write-back;
- preserve existing dashboard/API behavior.

**Excluded:**

- changes to `beeagent-rop`;
- new ROP business rules in BeeAgent;
- new subtype taxonomy in BeeAgent;
- CRM/Bitrix write-back;
- `crm.item.add`;
- `crm.item.update`;
- timeline comments;
- task creation;
- mailbox delete/archive/reply/mark-as-read;
- OCR;
- raw PDF/DOCX/XLSX parsing;
- raw `.eml` persistence/rendering;
- raw attachment storage;
- web-triggered ROP run;
- UI auth/session;
- UI row detail;
- Sender/Subject UI polish;
- BeeUI core changes;
- new generic BeeUI components;
- separate frontend;
- manager scoring;
- 1C integration.

#### Deliverable

BeeAgent can run ROP execution MVP with deterministic latest-N selection, thread evidence and bounded AI assist artifacts:

```bash
uv run python config/start.py rop run \
  --source-id rop_batch_sample \
  --items-max 2 \
  --run-id smoke-it30-rop-execution

uv run python config/start.py rop current \
  --run-id smoke-it30-rop-execution

uv run python config/start.py rop dashboard \
  --period 7d \
  --run-id smoke-it30-rop-execution

uv run python config/start.py rop mvp-pack \
  --period 7d \
  --run-id smoke-it30-rop-execution
```

Expected new artifacts:

```text
storage/runs/<run_id>/mailbox_selection.json
storage/runs/<run_id>/mail_thread_index.json
storage/runs/<run_id>/mail_thread_context.json
storage/runs/<run_id>/rop_ai_assist_requests.json
storage/runs/<run_id>/rop_ai_assist_decisions.json
storage/runs/<run_id>/rop_ai_assist_results.json
```

Updated existing artifacts:

```text
storage/runs/<run_id>/classified_events.json
storage/runs/<run_id>/operator_summary.json
storage/runs/<run_id>/rop_current_state.json
storage/interfaces/rop_dashboard.json
storage/runs/<run_id>/rop_mvp_pack.json
storage/runs/<run_id>/rop_mvp_report.md
```

#### Config / contract impact

Expected:

```text
config/settings.yml may add rop.ai_assist
src/beeagent_module/core/settings.py validates rop.ai_assist fail-fast
artifact contract changes
CLI/runtime behavior changes
module integration behavior changes
docs update required
```

Source of truth:

```text
config/settings.yml → rop.sources[]
config/settings.yml → rop.ai_assist
storage/runs/<run_id>/* → run evidence
beeagent-rop public module contract → ROP classification semantics
```

#### Change level

```text
security-sensitive
```

Reason:

- AI provider execution;
- env/secret handling;
- external provider call;
- structured model output validation;
- mailbox selection behavior;
- artifact restore/parsing/serialization;
- module/capability boundary;
- future action/write-back safety boundary.

No dependency change is expected. SCA is required only if dependencies change.

#### Checks

Required:

```bash
uv run pytest -q
uv run pytest -q -k "rop or mailbox or thread or ai or web or ui"
```

Targeted tests:

```text
latest-N selects newest messages, not oldest
latest-N works per source
missing date fallback records warning
mailbox_selection.json is created and safe
thread index from Message-ID/References
thread index subject fallback
single-event thread fallback
mail_thread_index.json shape
mail_thread_context.json shape
thread_context passed into beeagent-rop payload
malformed thread_context degrades safely
classified_events.json includes case_subtype/recommended_queue/should_rop_see/correct_action when returned by module
AI assist disabled by default
AI assist enabled with missing env fails fast
AI eligible fallback event creates request artifact
confident spam/noise does not trigger AI
confident new_lead does not trigger AI
AI provider invalid output degrades safely
AI output with executable/write-back instruction is rejected
AI result preserves deterministic classification when module merge contract is unavailable
AI artifacts contain no secrets
operator/current/dashboard/MVP counters update without UI redesign
no GET mutation
no mailbox destructive actions
no CRM/Bitrix mutation
path traversal run_id rejected/degraded
```

Smoke:

```bash
uv run python config/start.py rop run \
  --source-id rop_batch_sample \
  --items-max 2 \
  --run-id smoke-it30-rop-execution

uv run python config/start.py rop current \
  --run-id smoke-it30-rop-execution

uv run python config/start.py rop dashboard \
  --period 7d \
  --run-id smoke-it30-rop-execution

uv run python config/start.py rop mvp-pack \
  --period 7d \
  --run-id smoke-it30-rop-execution
```

Optional AI smoke only with explicit test env:

```bash
ROP_AI_MODEL="test-model"
CUSTOM_AI_API_KEY="test-key"
ROP_AI_BASE_URL="http://127.0.0.1:<fake-provider-port>"
uv run python config/start.py rop run \
  --source-id rop_batch_sample \
  --items-max 2 \
  --run-id smoke-it30-ai-enabled
```

Security checks:

```bash
grep -R "CUSTOM_AI_API_KEY\|OPENAI_API_KEY\|password\|secret\|token\|raw_eml\|message/rfc822\|attachment_content\|content_bytes" \
  logs storage/runs/smoke-it30-rop-execution storage/interfaces -n || true
```

Also verify:

```text
SAST required
SCA only if dependencies change
DAST-style CLI/runtime misuse checks for malformed artifacts and invalid run_id
IAST not required
fuzzing optional for malformed AI decision / thread context payloads
```

#### DoD

- latest-N mailbox selection is deterministic and evidenced;
- `mailbox_selection.json` is created;
- `mail_thread_index.json` is created;
- `mail_thread_context.json` is created;
- bounded `thread_context` reaches `beeagent-rop` public module path;
- `classified_events.json` preserves subtype/queue/action fields from `beeagent-rop`;
- AI assist is disabled by default;
- AI assist config is explicit and fail-fast when enabled;
- AI provider execution is BeeAgent-owned;
- AI output is structured and validated;
- invalid/malicious AI output degrades safely;
- no private `beeagent-rop` internals are imported by BeeAgent;
- missing public AI merge contract degrades safely;
- no CRM/Bitrix/mailbox mutation exists;
- no POST/write/action route is added;
- no raw `.eml`/raw attachment content/secrets appear in logs/artifacts/API/HTML;
- existing ROP CLI/web paths remain backward-compatible;
- tests and docs are updated;
- required security checks are completed;
- `pyproject.toml.version` is not changed.

### Iteration 31 — ROP Review Workbench v0

**Status:** DONE

#### Goal

Make BeeUI-backed ROP console suitable for manual verification of a specific email: The operator must open the Queue event and see sender, subject, bounded body preview, attachments metadata, classification evidence, thread context, AI assist evidence, Bitrix evidence, action draft evidence and evidence links each `event_id`.

Target flow:

```text
/rop?tab=queue
→ View details
→ /rop/events/{event_id}?run_id=<run_id>
→ read-only review card
```

#### Why this is needed

After It30 and UI-6 BeeAgent already shows aggregate evidence:

```text
latest-N
threads
AI assist
Bitrix/current-state
operator recommendations
```

But MVP review loop is still incomplete:

```text
the bot classified the email
→ ROP cannot conveniently open a specific email
→ cannot see a proper sender/subject/body preview
→ cannot cross-check classification/thread/AI/Bitrix/action evidence in one place
→ It's impossible to understand quickly, classification error, thread context, AI assist or Bitrix matching
```

Without event-level review, it is pointless to make Bitrix write-back, operator POST actions or the large AI provider platform: first need a safe read-only workbench to test the solutions.

#### Depends on

- BeeAgent It30 — latest-N, thread artifacts and bounded AI assist execution;
- UI-6 — enriched ROP dashboard/read-model;
- UI-7 — BeeUI-backed auth boundary;
- existing BeeUI adapter-backed custom page support;
- existing artifacts:
  - `normalized_events.json`;
  - `classified_events.json`;
  - `attachment_extraction.json`;
  - `mail_thread_context.json`;
  - `rop_ai_assist_results.json`;
  - `bitrix_reconciliation.json`;
  - `rop_action_drafts.json`;
  - `rop_review_table.tsv`;
  - `operator_summary.json`.

#### Change level

```text
security-sensitive
```

Reason:

- email-derived sender/subject/body exposure in HTML/API;
- new event-detail API/HTML routes;
- artifact parsing and join logic across multiple evidence artifacts;
- bounded body preview contract;
- path/query validation for `run_id` and `event_id`;
- untrusted email/AI/Bitrix values rendered in HTML;
- strict read-only/no-mutation boundary must be preserved.

SCA is not required unless dependencies change.

#### Scope

**Includes:**

##### 1. Fix Queue sender/subject mapping

Fix ROP Queue read-model so Queue rows do not show `Unknown Sender` / `n/a` when normalized/classified artifacts contain real values.

Sender fallback order:

```text
normalized_event.sender
normalized_event.from_email
normalized_event.from
classified_event.sender
classified_event.from_email
classified_event.from
row.sender
"Unknown Sender"
```

Subject fallback order:

```text
normalized_event.subject
classified_event.subject
row.subject
"n/a"
```

Rules:

- JSON artifacts are primary source;
- TSV is fallback only;
- empty strings and placeholder values must not overwrite real values;
- HTML escaping is mandatory.

##### 2. Add bounded email body preview to normalized event contract

Add safe body preview fields to `normalized_events.json` where possible:

```json
{
  "body_preview": "bounded sanitized email text",
  "body_preview_chars": 4000,
  "body_preview_truncated": true,
  "body_preview_source": "text_plain"
}
```

Config:

```yaml
rop:
  email_preview:
    body_chars_max: 4000
```

Validation in:

```text
src/beeagent_module/core/settings.py
```

Rules:

- default/source of truth value lives in `config/settings.yml`;
- value must be int;
- value must be `>= 200`;
- hard cap in code: `10000`;
- no raw `.eml`;
- no raw MIME;
- no attachment content;
- no script/style HTML;
- normalize whitespace;
- strip control chars;
- safely truncate;
- old runs without `body_preview` use `body_short` or empty unavailable state in read-model without mutating storage.

##### 3. Add event detail read-model builder

Add event detail read-model builder, preferably in:

```text
src/beeagent_module/interfaces/ui/rop_event_detail.py
```

Expected function:

```python
build_rop_event_detail_read_model(storage_dir, run_id, event_id, *, lang="en") -> dict
```

Builder reads and joins:

```text
normalized_events.json
classified_events.json
attachment_extraction.json
mail_thread_context.json
rop_ai_assist_results.json
bitrix_reconciliation.json
rop_action_drafts.json
rop_review_table.tsv
operator_summary.json
```

Rules:

- normalized event is primary source for message fields;
- classified event is primary source for classification fields;
- optional missing artifacts produce warnings, not crash;
- malformed optional artifacts produce warnings, not crash;
- missing event returns safe 404;
- no storage mutation from GET/read-model paths.

##### 4. Add event detail API route

Add read-only JSON route:

```text
GET /api/rop/events/{event_id}?run_id=<run_id>
```

Response envelope:

```json
{
  "ok": true,
  "read_only": true,
  "data": {
    "run_id": "run-id",
    "event_id": "evt-001",
    "source": {},
    "message": {},
    "classification": {},
    "thread": {},
    "ai_assist": {},
    "bitrix": {},
    "action_draft": {},
    "attachments": [],
    "evidence_links": [],
    "warnings": []
  },
  "warnings": [],
  "meta": {}
}
```

Expected `data.message`:

```json
{
  "sender": "client@example.com",
  "recipients": ["sales@example.com"],
  "cc": [],
  "subject": "Request for welding equipment",
  "received_at": "2026-06-29T10:15:00Z",
  "body_preview": "bounded text",
  "body_preview_truncated": true,
  "body_preview_chars": 4000
}
```

##### 5. Add event detail HTML route

Add BeeUI-backed HTML route:

```text
GET /rop/events/{event_id}?run_id=<run_id>
```

The page must use BeeUI shell/layout primitives via BeeAgent adapter/read-model. Do not add product-owned legacy Jinja templates.

The page should show:

```text
Header:
  event_id
  sender
  subject
  source
  received_at
  priority badge
  case_type badge

Message:
  bounded body preview
  body truncated marker
  recipients/cc

Classification:
  case_type
  case_subtype
  recommended_queue
  should_rop_see
  correct_action
  priority
  confidence
  reason_code
  reasoning
  fallback status

Thread:
  thread_id
  previous events
  previous case type/subtype
  thread confidence
  reason codes

AI Assist:
  status
  used/not used
  confidence
  final case type/subtype
  merge reason
  warnings

Bitrix:
  match status
  match quality
  confidence
  safe_to_use_as_target
  entity type/id/title/stage
  manual review flag

Action Draft:
  queue
  recommended_action
  recommended_next_step
  draft/read-only status

Attachments:
  filename
  content_type
  size
  extraction_status
  preview/refusal metadata only

Evidence:
  allowlisted artifact links
```

##### 6. Add detail links from Queue

Each Queue / attention event row must include:

```text
View details
```

URL:

```text
/rop/events/{event_id}?run_id=<run_id>&lang=<lang>
```

Also add `detail_href` to `/api/rop/dashboard` rows where practical:

```json
{
  "event_id": "evt-001",
  "sender": "client@example.com",
  "subject": "Request",
  "detail_href": "/rop/events/evt-001?run_id=run-id"
}
```

##### 7. RU localization polish

Add RU labels through existing BeeAgent locale helper:

```text
Sender / Client          → Sender / client
Subject / Request → Subject / Request
View details             → Open email
Message body             → Email body
Body preview             → Email preview
Classification → Classification
Thread context           → Thread context
AI Assist                → AI- assistant
Bitrix evidence          → Bitrix data
Action draft             → Action draft
Recommended queue        → Recommended queue
Correct action           → Correct action
Should ROP see           → Show to the sales manager
Match quality            → Match quality
Safe target              → Safe target
Manual review required   → Manual review required
Evidence artifacts → Artifacts evidence
Back to queue            → Back to queue
```

Rules:

- `?lang=ru` is preserved in detail links;
- invalid lang falls back safely;
- API may remain language-neutral;
- HTML labels must support RU.

##### 8. Preserve auth/read-only boundary

When `web.auth.enabled=true`, new routes must be protected by the existing UI-7 BeeUI auth boundary.

Rules:

- no GET mutation;
- no POST/operator action routes;
- no web-triggered `rop run`;
- no mailbox calls;
- no CRM/Bitrix calls;
- no module/capability execution;
- no AI provider calls;
- no raw `.eml`;
- no raw attachment content;
- no arbitrary artifact browsing;
- no secrets in HTML/API/logs/artifacts.

**Excluded:**

- Bitrix write-back;
- `crm.item.add`;
- `crm.item.update`;
- timeline comments;
- task creation;
- mailbox archive/delete/reply/mark-as-read;
- operator POST actions;
- saving human review decisions;
- editing labels in UI;
- new AI provider profiles;
- new classification taxonomy;
- changes to `beeagent-rop`;
- BeeUI core changes unless a blocking generic renderer/auth bug exists;
- legacy web removal;
- OCR / PDF / DOCX / XLSX deep parsing;
- attachment download or raw viewer.

#### Deliverable

BeeAgent exposes a read-only event review workbench:

```text
/rop?tab=queue
→ /rop/events/{event_id}?run_id=<run_id>
→ /api/rop/events/{event_id}?run_id=<run_id>
```

The operator can inspect a single event with message preview, classification, thread, AI assist, Bitrix and action draft evidence without opening raw JSON/TSV artifacts manually.

#### Expected routes

New HTML:

```text
/rop/events/{event_id}
```

New API:

```text
/api/rop/events/{event_id}
```

Existing routes must remain:

```text
/rop
/api/rop/dashboard
/runs/{run_id}/artifacts/{artifact_id}
/api/runs/{run_id}/artifacts/{artifact_id}
```

#### Expected artifact changes

Updated artifact for new runs:

```text
storage/runs/<run_id>/normalized_events.json
```

May include:

```json
{
  "body_preview": "bounded sanitized body",
  "body_preview_chars": 4000,
  "body_preview_truncated": true,
  "body_preview_source": "text_plain"
}
```

No new required run artifact is needed. It31 is mainly read-model/API/UI over existing artifacts plus bounded body preview extension.

#### Config / contract impact

Expected config addition:

```yaml
rop:
  email_preview:
    body_chars_max: 4000
```

Source of truth:

```text
config/settings.yml -> rop.email_preview.body_chars_max
storage/runs/<run_id>/normalized_events.json -> bounded event message preview
storage/runs/<run_id>/* -> event evidence
BeeAgent UI read-model -> event detail API/HTML
```

#### Checks

Required:

```bash
uv run pytest -q
uv run pytest -q -k "rop or ui or web"
```

Targeted tests:

```text
Queue sender uses normalized_events sender
Queue sender does not show Unknown Sender when sender exists
Queue subject uses normalized_events subject
Queue subject does not show n/a when subject exists

body_preview is added and bounded for normalized events
body_preview truncates over limit
body_preview strips unsafe HTML/script/style
body_preview does not include raw .eml/MIME/attachment content

/api/rop/events/{event_id}?run_id=<run_id> returns event detail
/rop/events/{event_id}?run_id=<run_id> renders HTML detail
missing event returns safe 404
missing run returns safe 404
path traversal run_id is rejected
path traversal event_id is rejected

event detail includes classification fields
event detail includes subtype/queue/should_rop_see/correct_action
event detail includes thread context when available
event detail includes AI assist result when available
event detail includes Bitrix evidence when available
event detail includes action draft when available
event detail handles missing optional artifacts with warnings

Queue rows include detail_href
?lang=ru is preserved in detail links
/rop/events/{event_id}?lang=ru renders RU labels

auth enabled protects new HTML/API routes
GET routes do not mutate storage
HTML escapes sender/subject/body/reasoning
API/HTML do not expose secrets
API/HTML do not expose raw .eml
API/HTML do not expose attachment content
```

Smoke:

```bash
uv run python config/start.py rop run \
  --source-id rop_batch_sample \
  --items-max 2 \
  --run-id smoke-it31-review-workbench

uv run python config/start.py rop current \
  --run-id smoke-it31-review-workbench

uv run python config/start.py rop dashboard \
  --period 7d \
  --run-id smoke-it31-review-workbench

uv run python config/start.py web \
  --host 127.0.0.1 \
  --port 8780 \
  --no-open
```

Manual checks:

```text
GET /rop?run_id=smoke-it31-review-workbench&tab=queue
GET /rop/events/<event_id>?run_id=smoke-it31-review-workbench
GET /rop/events/<event_id>?run_id=smoke-it31-review-workbench&lang=ru
GET /api/rop/events/<event_id>?run_id=smoke-it31-review-workbench
```

Security/static checks:

```bash
rg -n "raw_eml|message/rfc822|attachment_content|content_bytes|payload_bytes" src/beeagent_module/interfaces/ui tests || true

rg -n "BITRIX_WEBHOOK|CUSTOM_AI_API_KEY|OPENAI_API_KEY|password|secret|token" logs storage/runs storage/interfaces || true

rg -n "POST|delete|archive|mark-as-read|reply|write-back|crm\.item\.add|crm\.item\.update|timeline" src/beeagent_module/interfaces/ui tests || true

git diff -- pyproject.toml uv.lock
```

SAST mindset review required.

SCA is not required unless dependencies change.

#### DoD

- Queue shows real sender instead of `Unknown Sender` when available;
- Queue shows real subject instead of `n/a` when available;
- each Queue row has a detail link;
- `/rop/events/{event_id}` works;
- `/api/rop/events/{event_id}` works;
- detail page shows bounded body preview;
- detail page shows classification/subtype/queue/action;
- detail page shows thread context when available;
- detail page shows AI assist evidence when available;
- detail page shows Bitrix evidence when available;
- detail page shows action draft when available;
- `?lang=ru` covers new labels;
- missing/malformed optional artifacts produce warnings, not crashes;
- auth-enabled mode protects new routes;
- no GET mutation;
- no POST/write/action routes;
- no CRM/Bitrix/mailbox mutation;
- no raw `.eml`;
- no raw attachment content;
- no secrets in HTML/API/logs/artifacts;
- path traversal is blocked;
- tests and docs are updated;
- `pyproject.toml.version` unchanged;
- `beeagent-rop` unchanged.

### Iteration 32 — ROP Customer Delivery MVP: evaluation gate, routing map, recommendations and Bitrix widget API

**Status:** DONE

#### Goal

Collect the final customer-delivery layer for ROP MVP: BeeAgent must be able to evaluate the quality of the reviewed TSV classification, build context/routing evidence, form read-only/draft-only recommendations, show them to Web UI and pass them through the Bitrix widget API protected without CRM/mailbox write-back.

Target flow:

```text
ROP run artifacts
→ context enrichment
→ evaluation gate
→ Bitrix match scoring
→ routing map
→ rop_recommendations.json
→ Web UI recommendations tab
→ Bitrix widget API
→ customer acceptance / real-mail review
```

#### Why this is needed

After It31, BeeAgent can already:

```text
mailbox/json source
→ normalized events with bounded body preview
→ thread context
→ beeagent-rop classification
→ AI assist evidence
→ Bitrix reconciliation
→ action drafts
→ ROP dashboard
→ event-level review workbench
```

But the customer still lacks delivery layer: to deliver.

- No formal quality gate for reviewed TSV;
- There is no separate `rop_evaluation.json` that shows whether we have reached acceptance targets;
- existing-deal emails in a weak context may look like `irrelevant/ignore`, although they must go to `manual_review` or AI fallback;
- Bitrix matching still requires the final scoring/threshold contract so that one sender with multiple leads/deals doesn't turn everything into `ambiguous`;
- no single routing map:

```text
case_type + case_subtype + recommended_queue + correct_action + bitrix_match_status
→ queue/category/action draft/recommendation
```

- No customer-facing recommendations artifact;
- Web UI shows evidence, but does not have a separate tab with valuable recommendations;
- Bitrix does not yet receive read-only widget payload with recommendations.

Iteration specifically covers the handoff layer:

```text
What has been processed
which is classified
what remains debatable
what the sales manager needs to review
Where it must go like draft routing
as seen in Web UI
as seen in Bitrix widget API
```

#### Change level

```text
security-sensitive
```

Reason:

- email-derived and CRM-derived operational data exposed through new Web/API surfaces;
- Bitrix widget token/auth boundary;
- AI provider profile/env handling;
- artifact parsing/serialization;
- routing/recommendation artifacts may influence future CRM actions;
- strict read-only/draft-only boundary must be preserved.

#### Scope

**Includes:**

##### 1. Classification evaluation gate

Add CLI command:

```bash
./start.sh rop evaluate-review --run-id <run_id>
```

and/or:

```bash
./start.sh rop evaluate-review --tsv storage/runs/<run_id>/rop_review_table.tsv
```

Create artifact:

```text
storage/runs/<run_id>/rop_evaluation.json
```

metrics:

```text
case_type_accuracy
case_subtype_accuracy
recommended_queue_accuracy
correct_action_accuracy
should_rop_see_accuracy
fallback_rate
ai_fallback_rate
manual_review_rate
critical_false_negative_rate
existing_deal_as_irrelevant_count
bitrix_ambiguous_rate
```

Rules:

- evaluator must be tolerant to missing optional human columns;
- missing human labels produce `not_evaluable` metric state, not crash;
- acceptance target is reported in artifact, not hidden in tests;
- quality target is a readiness gate, not a hardcoded runtime rule.

Acceptance target:

```text
case_type_accuracy >= 0.90
critical_false_negative_rate <= 0.05
existing_deal_as_irrelevant_count == 0
  or all such cases are routed to manual_review / AI fallback
```

##### 2. Context enrichment artifact

Add artifact:

```text
storage/runs/<run_id>/rop_context_enrichment.json
```

It must combine safe evidence:

```text
event
thread_context
previous_event_classification
Bitrix candidate context
sender history within current run
subject/thread similarity
source metadata
```

Rules:

- BeeAgent does not overwrite module-owned classification silently;
- if classifier says `irrelevant`, but thread/Bitrix/sender evidence indicates possible existing deal, delivery layer must route the event to `manual_review` or AI fallback;
- final recommendation/action must not become `ignore` when existing-deal evidence is present;
- all overrides must be explicit and traceable as delivery safety routing, not hidden classification mutation.

##### 3. Bitrix ambiguity scoring hardening

Strengthen existing Bitrix reconciliation scoring so `ambiguous` is not the default for all emails from one sender.

Allowed scoring signals:

```text
sender email exact
phone exact
thread_id / previous entity
subject similarity
deal title similarity
date window
active/open stage boost
closed/lost stage penalty
source_role
case_subtype
```

Rules:

```text
score >= strong_threshold + clear winner
→ matched_lead / matched_deal

weak_threshold <= score < strong_threshold
→ weak_match

several close candidates
→ ambiguous

several strong candidates
→ duplicate_candidate

no candidate + connector ok
→ not_found

connector failed
→ connector_degraded / error
```

Required invariant:

```text
not_found != connector failure
weak_match != matched
ambiguous != matched
missing Bitrix artifact != not_found
```

If thresholds become configurable, source of truth must be:

```text
config/settings.yml -> bitrix.reconciliation.scoring
```

and keys must be validated fail-fast.

##### 4. AI provider profiles

Replace or extend current `rop.ai_assist` contract with explicit provider profiles:

```yaml
rop:
  ai_assist:
    enabled: false
    profile: openai
    max_events_per_run: 20
    request_timeout_seconds: 30
    min_ai_confidence: 0.70
    dry_run: false
    profiles:
      openai:
        provider: openai_compatible
        base_url_env: ROP_AI_OPENAI_BASE_URL
        api_key_env: OPENAI_API_KEY
        model_env: ROP_AI_OPENAI_MODEL
      deepseek:
        provider: openai_compatible
        base_url_env: ROP_AI_DEEPSEEK_BASE_URL
        api_key_env: DEEPSEEK_API_KEY
        model_env: ROP_AI_DEEPSEEK_MODEL
      lmstudio:
        provider: openai_compatible
        base_url_env: ROP_AI_LMSTUDIO_BASE_URL
        api_key_env: LMSTUDIO_API_KEY
        model_env: ROP_AI_LMSTUDIO_MODEL
      custom:
        provider: openai_compatible
        base_url_env: ROP_AI_BASE_URL
        api_key_env: CUSTOM_AI_API_KEY
        model_env: ROP_AI_MODEL
```

Rules:

- default disabled;
- when enabled and not dry-run, selected profile envs must fail fast if missing;
- no hidden fallback to generic `llm.*`;
- no provider secrets in logs/artifacts/API/HTML;
- all providers are openai-compatible transport profiles;
- AI runs only for eligible fallback/manual-review/ambiguous/weak/low-confidence cases;
- confident deterministic results must not trigger AI;
- AI output must remain structured, validated and non-executing;
- AI cannot execute or request CRM/mailbox/Bitrix write-back;
- merge must use public `beeagent-rop` contract if available;
- if public merge is unavailable, deterministic result is preserved and degraded status is recorded.

##### 5. ROP routing map

Add config/artifact-backed routing map.

Source of truth:

```yaml
rop:
  routing:
    queues:
      sales:
        bitrix_category: sales
      tender:
        bitrix_category: tenders
      logistics:
        bitrix_category: logistics
      finance:
        bitrix_category: finance
      procurement:
        bitrix_category: procurement
      manual_review:
        bitrix_category: manual_review
```

Create/update interface artifact:

```text
storage/interfaces/rop_routing_map.json
```

Routing input:

```text
case_type
case_subtype
recommended_queue
correct_action
bitrix_match_status
bitrix_match_quality
safe_to_use_as_target
context_enrichment flags
```

Routing examples:

```text
new_lead + not_found
→ queue=sales
→ action=create_lead_draft
→ target_category=sales

new_lead + tender
→ queue=tender
→ action=create_tender_lead_draft
→ target_category=tenders

existing_deal + logistics + safe matched deal
→ queue=logistics
→ action=attach_to_deal_draft

existing_deal + invoice
→ queue=finance
→ action=attach_finance_note_draft

weak_match / ambiguous / duplicate_candidate
→ queue=manual_review
→ action=choose_correct_entity

possible_existing_deal_but_context_weak
→ queue=manual_review
→ action=manual_review_required
```

Rules:

- routing is draft-only;
- no CRM write-back;
- no mailbox action;
- no hidden client-specific hardcoding outside config and explicit ROP delivery mapping.

##### 6. Recommendations artifact

Create artifact:

```text
storage/runs/<run_id>/rop_recommendations.json
```

Recommended CLI command:

```bash
./start.sh rop recommendations --run-id <run_id>
```

Recommendation item shape:

```json
{
  "event_id": "evt-001",
  "title": "Review new request",
  "summary": "Client requested pricing for welding equipment.",
  "recommended_action": "create_lead_draft",
  "recommended_queue": "sales",
  "target_bitrix_category": "sales",
  "priority": "high",
  "reason": "New classified request was not found in Bitrix.",
  "confidence": 0.91,
  "ai_used": false,
  "bitrix_status": "not_found",
  "safe_to_execute": false,
  "requires_human_confirmation": true,
  "evidence_links": []
}
```

Allowed recommendation actions:

```text
create_lead_draft
create_tender_lead_draft
attach_to_existing_deal
attach_logistics_note
attach_finance_note
attach_procurement_note
choose_correct_bitrix_entity
check_duplicate
ignore
manual_review_required
check_bitrix_connector
```

Rules:

- `safe_to_execute=false` for every item in It32;
- `requires_human_confirmation=true` for every non-ignore item;
- recommendations must be derived from artifacts/routing map, not from new CRM calls;
- missing Bitrix evidence must produce `unreconciled/manual_review`, not `not_found`.

##### 7. Bitrix widget API

Add read-only endpoints:

```text
GET /api/bitrix/rop/widget
GET /api/bitrix/rop/widget/events
GET /api/bitrix/rop/widget/events/{event_id}
```

Config:

```yaml
bitrix:
  widget:
    enabled: false
    token_env: BITRIX_ROP_WIDGET_TOKEN
    default_period: "7d"
    max_items: 50
```

Rules:

- default disabled;
- when enabled, `BITRIX_ROP_WIDGET_TOKEN` must exist;
- token must be provided through header, not logged query params;
- no token value in logs/artifacts/API/HTML;
- routes read existing artifacts only;
- routes must not call Bitrix REST API;
- routes must not mutate storage;
- routes must not execute module/capability/AI/mailbox actions;
- if `web.auth.enabled=true`, existing auth boundary remains for normal Web/API routes; widget token is the explicit integration boundary for widget endpoints.

Expected widget payload:

```json
{
  "ok": true,
  "read_only": true,
  "data": {
    "summary": {
      "high_priority": 4,
      "needs_review": 7,
      "lost_in_bitrix": 3,
      "ambiguous": 2,
      "ai_assisted": 5
    },
    "items": [
      {
        "event_id": "evt-001",
        "priority": "high",
        "sender": "client@example.com",
        "subject": "Request for welding machine",
        "summary": "Client asks for a quotation.",
        "recommended_action": "create_lead_draft",
        "recommended_queue": "sales",
        "target_bitrix_category": "sales",
        "bitrix_status": "not_found",
        "confidence": 0.91,
        "ai_used": false,
        "reason": "New request was not found in Bitrix.",
        "detail_url": "/api/bitrix/rop/widget/events/evt-001"
      }
    ]
  },
  "warnings": [],
  "meta": {}
}
```

##### 8. Web UI recommendations parity

Add the following tab:

```text
/rop?tab=recommendations
```

Update `config/beeui.yml` page tabs if needed.

Web UI must show the same recommendation data as Bitrix widget:

```text
title
summary
recommended_action
recommended_queue
target_bitrix_category
priority
confidence
ai_used
bitrix_status
reason
detail link
evidence links
safe_to_execute
requires_human_confirmation
```

Rules:

- Web UI remains read-only;
- no POST/action route;
- no config editing;
- no widget token rendering;
- no raw `.eml`;
- no raw attachment content.

#### Excluded

Do not do in It32:

```text
automatic crm.item.add
automatic crm.item.update
automatic timeline comments
automatic Bitrix tasks
mailbox delete/archive/reply/mark-as-read
web-triggered ROP run
operator POST actions
saving human review decisions
OCR
PDF/DOCX/XLSX deep parsing
React frontend
legacy web removal
SQLAdmin
1C
manager scoring
production listener
```

Write-back remains only draft/read-only:

```text
safe_to_execute=false
requires_human_confirmation=true
```

#### Deliverable

BeeAgent can build a customer-delivery read-only recommendation layer:

```bash
./start.sh rop evaluate-review --run-id <run_id>
./start.sh rop recommendations --run-id <run_id>
./start.sh rop dashboard --period 7d --run-id <run_id>
./start.sh rop mvp-pack --period 7d --run-id <run_id>
```

Expected artifacts:

```text
storage/runs/<run_id>/rop_context_enrichment.json
storage/runs/<run_id>/rop_evaluation.json
storage/runs/<run_id>/rop_recommendations.json
storage/interfaces/rop_routing_map.json
```

Updated artifacts/read-models:

```text
storage/runs/<run_id>/bitrix_reconciliation.json
storage/runs/<run_id>/rop_action_drafts.json
storage/runs/<run_id>/rop_current_state.json
storage/interfaces/rop_dashboard.json
storage/runs/<run_id>/rop_mvp_pack.json
storage/runs/<run_id>/rop_mvp_report.md
```

New API:

```text
/api/bitrix/rop/widget
/api/bitrix/rop/widget/events
/api/bitrix/rop/widget/events/{event_id}
```

New Web tab:

```text
/rop?tab=recommendations
```

#### Config / contract impact

Expected config changes:

```text
config/settings.yml -> rop.ai_assist profile/profiles
config/settings.yml -> rop.routing
config/settings.yml -> bitrix.widget
optional config/settings.yml -> bitrix.reconciliation.scoring
config/beeui.yml -> ROP recommendations tab
```

New required config keys must be validated fail-fast in:

```text
src/beeagent_module/core/settings.py
```

Artifact contract changes:

```text
storage/runs/<run_id>/rop_context_enrichment.json
storage/runs/<run_id>/rop_evaluation.json
storage/runs/<run_id>/rop_recommendations.json
storage/interfaces/rop_routing_map.json
```

CLI/runtime changes:

```text
./start.sh rop evaluate-review
./start.sh rop recommendations
```

API/UI changes:

```text
GET /api/bitrix/rop/widget
GET /api/bitrix/rop/widget/events
GET /api/bitrix/rop/widget/events/{event_id}
GET /rop?tab=recommendations
```

#### Checks

Required:

```bash
uv run pytest -q
uv run pytest -q -k "rop or bitrix or ai or widget or ui"
```

Targeted tests:

```text
evaluate-review creates rop_evaluation.json
evaluate-review handles missing optional human columns
evaluation calculates case_type_accuracy
evaluation calculates critical_false_negative_rate
evaluation detects existing_deal_as_irrelevant_count
context enrichment creates rop_context_enrichment.json
possible existing deal is not routed to ignore
existing_deal weak context goes to manual_review or AI fallback eligibility
Bitrix strong candidate selects clear winner
Bitrix weak candidate becomes weak_match
Bitrix several close candidates become ambiguous
Bitrix connector failure is not not_found
ambiguous is not default for same sender
OpenAI profile config validates
DeepSeek profile config validates
LM Studio profile config validates
selected AI profile missing env fails fast when enabled and not dry-run
AI runs only for eligible events
AI invalid output is rejected/degraded
AI cannot request write-back execution
routing map config validates
storage/interfaces/rop_routing_map.json is created
rop_recommendations.json is created
recommendations are read-only/draft-only
safe_to_execute is false
requires_human_confirmation is true for non-ignore recommendations
Bitrix widget disabled returns safe disabled response
Bitrix widget enabled requires token
Bitrix widget rejects missing/invalid token
Bitrix widget payload works
Bitrix widget event detail works
Web UI recommendations tab renders
Widget/Web UI use same recommendation source data
GET routes do not mutate storage
no CRM write method called
no mailbox destructive action called
```

Smoke:

```bash
uv run python config/start.py rop run \
  --source-id rop_batch_sample \
  --items-max 20 \
  --run-id smoke-it32-delivery

uv run python config/start.py rop reconcile-bitrix \
  --run-id smoke-it32-delivery

uv run python config/start.py rop action-drafts \
  --run-id smoke-it32-delivery

uv run python config/start.py rop current \
  --run-id smoke-it32-delivery

uv run python config/start.py rop dashboard \
  --period 7d \
  --run-id smoke-it32-delivery

uv run python config/start.py rop recommendations \
  --run-id smoke-it32-delivery

uv run python config/start.py rop evaluate-review \
  --run-id smoke-it32-delivery

uv run python config/start.py rop mvp-pack \
  --period 7d \
  --run-id smoke-it32-delivery

uv run python config/start.py web \
  --host 127.0.0.1 \
  --port 8780 \
  --no-open
```

Manual:

```text
GET /rop?tab=recommendations&run_id=smoke-it32-delivery
GET /api/bitrix/rop/widget
GET /api/bitrix/rop/widget/events
GET /api/bitrix/rop/widget/events/<event_id>
```

Security/static checks:

```bash
rg -n "crm\.item\.add|crm\.item\.update|crm\.item\.delete|crm\.timeline|task\.item\.add" src tests || true

rg -n "BITRIX_WEBHOOK|BITRIX_ROP_WIDGET_TOKEN|ROP_AI_.*KEY|OPENAI_API_KEY|password|secret|token" \
  logs storage/runs storage/interfaces || true

rg -n "raw_eml|message/rfc822|attachment_content|content_bytes|payload_bytes" \
  storage/runs storage/interfaces src tests || true

git diff -- pyproject.toml uv.lock
```

SAST required.

SCA only if dependencies change.

DAST-style route/API misuse checks required for:

```text
/rop?tab=recommendations
/api/bitrix/rop/widget
/api/bitrix/rop/widget/events
/api/bitrix/rop/widget/events/{event_id}
```

IAST not required.

Fuzzing optional for malformed reviewed TSV / malformed recommendation artifacts.

#### DoD

- `rop_evaluation.json` is created;
- evaluation reports acceptance/readiness metrics;
- evaluation distinguishes not-evaluable metrics from failed metrics;
- existing-deal-as-irrelevant risk is visible and routed to manual review / AI fallback eligibility;
- `rop_context_enrichment.json` is created;
- Bitrix scoring no longer treats all same-sender candidates as `ambiguous` by default;
- weak Bitrix candidates are not treated as safe matched targets;
- AI provider profiles exist and validate fail-fast;
- AI remains disabled by default;
- AI runs only for eligible events;
- AI output cannot execute or request write-back;
- routing map is config/artifact-backed;
- `storage/interfaces/rop_routing_map.json` is created;
- `rop_recommendations.json` is created;
- recommendations are visible in Web UI;
- recommendations are available through Bitrix widget API;
- widget endpoints are protected by token/auth boundary;
- widget routes read existing artifacts only;
- no CRM/mailbox/Bitrix mutation exists;
- no POST/write/operator action route is added;
- no raw `.eml` / raw attachment content / secrets appear in logs/artifacts/API/HTML;
- `beeagent-rop` is not changed unless a public contract blocker is explicitly documented;
- BeeAgent core does not contain ROP classification rules;
- docs are updated;
- tests and required security checks are completed;
- `pyproject.toml.version` is not changed.

### Iteration 33 — ROP real-mail normalization and classification polish for forwarded mailbox traffic

**Status:** DONE

#### Goal

Correct pilot-blocking errors on real mailbox traffic: BeeAgent must normalize forwarded/spam/reply mailbox wrappers into clear transport/evidence fields, and `beeagent-rop` must use these fields as weak transport signals, without confusing labels technical mailboxes with business classification.

Target flow:

```text
mailbox/json source
→ forwarded wrapper extraction
→ clean_subject + transport_labels + original sender/date fields
→ normalized_events.json
→ beeagent-rop lead_classification using clean/original fields
→ classified_events.json with corrected tender/spam/existing-deal behavior
→ rop_review_table.tsv for human/customer validation
→ recommendations/current/dashboard remain delivery layer
```

#### Why this is needed

After It32 BeeAgent already has customer-delivery layer:

```text
evaluation gate
context enrichment
routing map
recommendations
Bitrix widget API
Web UI recommendations tab
```

But real-mail pilot batch showed the system problem below delivery layer:

```text
[AUTO-FWD] / FWD / RE / *** SPAM ***
```

Now they may be mistaken for business evidence:.

```text
FWD → reply/existing-deal/manual-review
SPAM → ignore
AUTO-FWD → business signal
```

It's not right.

Model required:

```text
AUTO-FWD / FWD / RE / SPAM = transport labels
clean_subject + original_sender + body + attachments + Bitrix/thread evidence = business evidence
```

Without this, iteration MVP will make mistakes on real emails sent from the aggregation mailbox:

- Good tenders may not go to tender queue;
- SPAM-marked business emails may be ignored;
- supplier/marketing distributions can reach manual_review;
- Weak FWD/RE signs can create false existing_deal;
- ROP will see noise instead of a useful queue.

#### Depends on

Required:

```text
BeeAgent It32 — ROP Customer Delivery MVP
beeagent-rop current public lead_classification contract
```

Companion work:

```text
beeagent-rop — classification polish using clean/original normalized fields
```

Important boundary:

```text
BeeAgent normalizes transport/mailbox evidence.
beeagent-rop owns ROP business classification.
BeeAgent delivery layer may route weak/conflicting evidence to manual_review but must not reimplement the classifier.
```

#### Scope

**Includes in BeeAgent:**

##### 1. Forwarded wrapper normalization

Extract safe original forwarded headers from email body when present:

```text
Email:
Original sender:
Original address of receipt:
Date:
X-Email-ID:
```

Populate normalized event fields:

```text
original_sender
original_recipient
original_message_date
x_email_id
forwarded_wrapper
date_source
```

Rules:

- wrapper extraction must be bounded and safe;
- no raw `.eml`;
- no raw MIME;
- no raw attachment content;
- malformed forwarded wrapper must degrade safely;
- existing sender/subject fields remain backward-compatible display fields.

##### 2. Clean subject and transport labels

Add normalized event fields:

```text
clean_subject
transport_labels
spam_label_present
reply_label_present
forwarded_wrapper
```

Technical prefixes to strip into `transport_labels`:

```text
[AUTO-FWD]
FWD:
FW:
RE:
*** SPAM ***
```

Example:

```text
subject = "[AUTO-FWD] FWD: *** SPAM *** OEM submerged-arc welding machine supplied"
clean_subject = "OEM submerged-arc welding machine supplied"
transport_labels = ["auto_fwd", "fwd", "spam"]
spam_label_present = true
reply_label_present = false
forwarded_wrapper = true
```

Rules:

- `subject` remains raw-safe display field;
- `clean_subject` is used for classification payload;
- transport labels are not business labels;
- empty or malformed subject must not crash normalization.

##### 3. Original date source

If forwarded body contains original date:

```text
Date: Tue, 9 Jun 2026 11:54:27 +0800
```

write:

```text
original_message_date
date_source = original_forwarded_date
```

Rules:

- keep `received_at` / mailbox date as mailbox-level evidence;
- use original forwarded date where safely parsed;
- fallback order must be explicit;
- date parse failure must degrade with warning, not crash.

##### 4. Classification payload handoff

Pass normalized/original fields into `beeagent-rop` `lead_classification` payload:

```text
clean_subject
transport_labels
spam_label_present
reply_label_present
forwarded_wrapper
original_sender
original_recipient
original_message_date
date_source
x_email_id
```

Rules:

- do not import private `beeagent-rop` internals;
- use existing public module runtime path;
- preserve backward compatibility for modules that ignore the new fields.

##### 5. Review TSV enrichment

Extend `rop_review_table.tsv` with review-useful normalized mail fields:

```text
clean_subject
transport_labels
spam_label_present
reply_label_present
forwarded_wrapper
original_sender
original_recipient
original_message_date
date_source
x_email_id
```

Rules:

- TSV remains tab-separated and Google Sheets pasteable;
- optional/missing fields export as empty cells;
- no raw `.eml`;
- no raw attachment content;
- no secrets.

##### 6. Source/operator artifacts

Update existing artifacts where useful:

```text
normalized_events.json
classified_events.json
operator_summary.json
source_diagnostics.json
rop_review_table.tsv
```

Add counters/warnings if minimal and useful:

```text
forwarded_wrapper_count
spam_label_count
transport_label_count
original_date_used_count
date_fallback_count
```

Do not create a new artifact unless it materially improves evidence.

##### 7. Delivery safety remains in BeeAgent

BeeAgent delivery layer may use enriched evidence only for delivery safety:

```text
possible existing deal + weak/conflicting evidence
→ manual_review / AI fallback eligibility
```

Rules:

- do not silently rewrite module classification;
- do not implement ROP tender/supplier/logistics/finance rules in BeeAgent;
- routing/recommendations stay read-only/draft-only.

**Included in companion `beeagent-rop` work:**

- use `clean_subject` instead of raw `subject` for semantic classification when available;
- use `original_sender` instead of wrapper sender when available;
- treat `AUTO-FWD`, `FWD`, `RE`, `SPAM` as weak transport signals;
- tender/procedure/lot/protocol markers route to tender queue;
- `spam_label_present=true` does not automatically mean `ignore`;
- supplier/bulk/marketing/newsletter spam can become irrelevant/ignore;
- SPAM + business markers must still classify normally, possibly with confidence penalty/manual review;
- reduce marketing/newsletter manual_review false positives;
- reduce existing_deal false positives;
- require stronger evidence for `existing_deal`.

**Excluded:**

- CRM/Bitrix write-back;
- mailbox delete/archive/reply/mark-as-read;
- production listener/polling;
- OCR;
- PDF/DOCX/XLSX deep parsing;
- raw `.eml` persistence;
- raw attachment persistence;
- new AI provider work;
- new Bitrix widget routes;
- Web POST/operator actions;
- saving human review decisions;
- BeeUI core changes;
- reimplementing `beeagent-rop` classifier in BeeAgent;
- hardcoding Welding-specific classifications in BeeAgent.

#### Deliverable

BeeAgent produces richer normalized/review artifacts for forwarded mailbox traffic, and the ROP classification path receives clean/original fields without treating mailbox transport labels as business labels.

Expected BeeAgent artifacts after a ROP run:

```text
storage/runs/<run_id>/normalized_events.json
storage/runs/<run_id>/classified_events.json
storage/runs/<run_id>/operator_summary.json
storage/runs/<run_id>/rop_review_table.tsv
```

`normalized_events.json` event example:

```json
{
  "event_id": "evt-001",
  "sender": "wrapper@example.com",
  "subject": "[AUTO-FWD] FWD: *** SPAM *** OEM submerged-arc welding machine supplied",
  "clean_subject": "OEM submerged-arc welding machine supplied",
  "transport_labels": ["auto_fwd", "fwd", "spam"],
  "forwarded_wrapper": true,
  "spam_label_present": true,
  "reply_label_present": false,
  "original_sender": "gina.shi@morrowwelding.com",
  "original_recipient": "online@welding.kz",
  "original_message_date": "2026-06-09T11:54:27+08:00",
  "date_source": "original_forwarded_date",
  "x_email_id": "bounded-id"
}
```

#### Acceptance on current 20-mail pilot batch

Expected behavior after BeeAgent + `beeagent-rop` companion fixes:

```text
ETS Tender → tender / review_tender
DIGTP procedure → tender / review_tender
Mir-svarki request details/doc → tender/manual_review, not plain sales
K-MAX marketing → ignore
Robotiq webinar → ignore
Edukz HR newsletter → ignore
Molina cosmetics spam → ignore
SZGH supplier promo → ignore
Dawson logistics thread → existing_deal_logistics or manual_review
Pentagon freight invoices → existing_deal_logistics or manual_review
SAP/Qarmet delivery expiry → existing_deal_logistics or manual_review
1C delivery report bulk → ignore or manual_review, not confident existing_deal
```

#### Config / contract impact

Expected:

```text
No new required BeeAgent config key unless implementation proves one is needed.
```

Existing source of truth remains:

```text
config/settings.yml -> rop.sources[]
config/settings.yml -> rop.email_preview.body_chars_max
storage/runs/<run_id>/normalized_events.json -> normalized event contract
beeagent-rop public lead_classification payload -> business classification input
```

If a new config key is proposed, it must be justified first and validated fail-fast in:

```text
src/beeagent_module/core/settings.py
```

#### Artifact contract impact

Updated:

```text
storage/runs/<run_id>/normalized_events.json
storage/runs/<run_id>/rop_review_table.tsv
storage/runs/<run_id>/operator_summary.json
```

May be updated:

```text
storage/runs/<run_id>/classified_events.json
storage/runs/<run_id>/rop_context_enrichment.json
storage/runs/<run_id>/rop_recommendations.json
```

#### Change level

```text
security-sensitive
```

Reason:

- email-derived input parsing;
- forwarded wrapper parsing;
- subject/body normalization;
- date parsing from untrusted email body;
- artifact contract change;
- classification payload contract change;
- sensitive client email data serialized into artifacts/TSV/UI;
- no raw `.eml` / attachment content / secrets must leak.

No dependency change is expected.

#### Checks

Required:

```bash
uv run pytest -q
uv run pytest -q -k "rop or mailbox or input_source or review or classification"
```

Targeted BeeAgent tests:

```text
clean_subject strips AUTO-FWD/FWD/FW/RE/SPAM prefixes
transport_labels captures auto_fwd/fwd/fw/re/spam
subject remains raw-safe display field
forwarded wrapper extracts original_sender/original_recipient/original_message_date/x_email_id
original forwarded date is preferred when safely parsed
date fallback records date_source
malformed forwarded wrapper degrades safely
SPAM label does not force BeeAgent ignore
FWD label alone does not force reply/existing-deal/manual_review in BeeAgent
classification payload includes clean/original fields
rop_review_table.tsv includes clean/original/transport fields
TSV remains valid tab-separated output
no raw .eml appears in artifacts/logs
no attachment content appears in artifacts/logs
no secrets appear in artifacts/logs
```

Companion `beeagent-rop` tests:

```text
classification uses clean_subject when present
classification uses original_sender when present
tender/procedure/lot/protocol markers route to tender queue
SPAM + business markers is not automatically ignored
SPAM + supplier/bulk/marketing markers can become irrelevant/ignore
FWD/RE alone does not create existing_deal
existing_deal requires Bitrix/thread/order/invoice/shipping/customer evidence
marketing/newsletter false positives reduced
current 20-mail reviewed fixture meets expected acceptance behavior
```

Smoke:

```bash
uv run python config/start.py rop run \
  --source-id rop_batch_sample \
  --items-max 20 \
  --run-id smoke-it33-real-mail-normalization

uv run python config/start.py rop export-review \
  --run-id smoke-it33-real-mail-normalization \
  --format tsv

uv run python config/start.py rop evaluate-review \
  --run-id smoke-it33-real-mail-normalization

uv run python config/start.py rop recommendations \
  --run-id smoke-it33-real-mail-normalization
```

Optional live smoke only with explicit approval and available mailbox credentials:

```bash
uv run python config/start.py rop run \
  --source-id hotline_mailbox \
  --items-max 20 \
  --run-id live-it33-forwarded-mailbox-20
```

Security/static checks:

```bash
rg -n "raw_eml|message/rfc822|attachment_content|content_bytes|payload_bytes" \
  storage/runs storage/interfaces src tests || true

rg -n "BITRIX_WEBHOOK|ROP_AI_.*KEY|OPENAI_API_KEY|password|secret|token" \
  logs storage/runs storage/interfaces || true

rg -n "crm\.item\.add|crm\.item\.update|crm\.item\.delete|crm\.timeline|task\.item\.add" \
  src tests || true
```

SAST required.

SCA only if dependencies change.

Fuzzing optional for forwarded-wrapper/date/subject parsing if parser complexity grows.

#### DoD

- `normalized_events.json` includes `clean_subject`;
- `normalized_events.json` includes `transport_labels`;
- `normalized_events.json` includes `spam_label_present`, `reply_label_present`, `forwarded_wrapper`;
- forwarded body wrapper fields are extracted when safely available;
- original forwarded date is captured as `original_message_date` with explicit `date_source`;
- classification payload includes clean/original/transport fields;
- `rop_review_table.tsv` exposes clean/original/transport fields for human review;
- `AUTO-FWD`, `FWD`, `RE`, `SPAM` are not treated as decisive business labels in BeeAgent;
- SPAM label does not automatically force ignore;
- FWD/RE label alone does not automatically force existing_deal/manual_review;
- companion `beeagent-rop` classification uses clean/original fields and treats transport labels as weak signals;
- tender queue behavior is fixed in `beeagent-rop`;
- supplier/marketing/newsletter noise false positives are reduced in `beeagent-rop`;
- existing_deal false positives are reduced in `beeagent-rop`;
- current 20-mail pilot batch reaches the expected acceptance behavior;
- no CRM/mailbox/Bitrix mutation exists;
- no raw `.eml` / raw attachment content / secrets appear in logs/artifacts/API/HTML;
- tests and docs are updated;
- required security checks are completed;
- `pyproject.toml.version` is not changed.

### Iteration 34 — ROP OpenAI adjudicator execution v0

**Status:** DONE

#### Goal

Add to BeeAgent the real AI adjudication execution layer for disputed ROP classifications: BeeAgent must only call OpenAI for ambiguous/fallback/low-confidence events, receive strict structured JSON, validate the result, safe merge/degrade final decision and record the reproducible AI evidence artifacts without CRM/mailbox/Bitrix write-back.

#### Why this is needed

After It33 real-mail normalization improved the quality of mailbox artifacts, but pilot traffic showed the limit deterministic rules:

```text
deterministic classifier
→ It works well on the obvious RFQ/tender/finance/noise cases
→ It breaks into the grey area: supplier promo vs existing deal, newsletter vs business thread, spam label + RFQ, logistics reply hidden as ignore
```

You can't add `if/else` to every email forever. MVP requires bounded AI adjudicator:

```text
deterministic rules captures the obvious
conflict/eligibility gate selects the grey area
OpenAI adjudicator only resolves disputed cases
invalid/low-confidence AI → manual_review or deterministic fallback
all outputs are visible in TSV/artifacts
no automatic CRM actions
```

#### Scope

**Includes in BeeAgent**

- OpenAI provider execution through BeeAgent-owned provider layer;
- Responses API / structured JSON output;
- config-driven AI adjudicator settings;
- env/secret handling;
- fail-fast validation when AI adjudicator is enabled;
- bounded/sanitized AI request payload;
- timeout/error/invalid JSON handling;
- deterministic result preservation on provider failure;
- AI result validation against allowed ROP taxonomy/config/contract;
- `ai_used`, `ai_provider`, `ai_model`, `ai_confidence`, `ai_reason`, `ai_risk_flags`, `ai_error`;
- deterministic-vs-AI comparison fields in TSV;
- AI evidence artifacts:
  - `rop_ai_adjudicator_requests.json`;
  - `rop_ai_adjudicator_decisions.json`;
  - `rop_ai_adjudicator_results.json`;

- fake provider tests;
- smoke with AI disabled and fake AI enabled;
- docs update.

**Excluded**

- changes to `beeagent-rop`, unless a public contract is already available and can be used without private imports;
- private imports from `beeagent-rop`;
- new deterministic ROP rules in BeeAgent;
- CRM/Bitrix write-back;
- mailbox delete/archive/reply/mark-as-read;
- OCR;
- RAG;
- attachment content parsing;
- web-triggered run;
- POST/operator actions;
- saving human review decisions;
- customer-specific sender/domain hardcoding.

#### Deliverable

BeeAgent can run ROP classification with AI adjudication enabled:

```bash
uv run python config/start.py rop run \
  --source-id hotline_mailbox \
  --items-max 20 \
  --run-id mvp-ai-smoke-001-20
```

Before run:

```text
1. Set OPENAI_API_KEY in .env
2. Set rop.ai_assist.enabled: true
3. Set rop.ai_assist.adjudicator.enabled: true
4. Keep exactly one ai.profiles.*.enabled = true
```

Expected behavior:

```text
AI is disabled by default.
AI is called only for eligible ambiguous/fallback/low-confidence events.
AI is not called for every email.
Provider failures do not crash the run.
Invalid AI output does not crash the run.
TSV shows deterministic and AI decisions.
Artifacts show what AI saw, what it returned, and how final result was merged/degraded.
```

#### Config / contract impact

Expected config source of truth:

```yaml
rop:
  ai_assist:
    enabled: false
    adjudicator:
      enabled: false
      timeout: 20
      input_chars_max: 8000
      confidence_accept_min: 0.70
      events_max: 20
      prompt_key: "rop.ai_adjudicator"

ai:
  prompts:
    path: "config/prompts.yml"
    store: false
  profiles:
    openai:
      enabled: true
      provider: openai_responses
      api_key_env: OPENAI_API_KEY
      base_url: "https://api.openai.com/v1"
      model: "gpt-5.4-mini"
```

If existing `rop.ai_assist` already exists, prefer extending/reusing it instead of creating a conflicting second source of truth.

#### Change level

```text
security-sensitive
```

Reason:

- external AI provider call;
- env/secret handling;
- email-derived input sent to provider;
- structured model output parsing/validation;
- artifact serialization of customer operational data;
- future action/write-back boundary must stay blocked.

#### DoD

- AI adjudicator is disabled by default;
- enabling AI without required env fails fast;
- OpenAI provider execution exists in BeeAgent;
- OpenAI API key is never stored in artifacts/logs/API/HTML;
- only bounded/sanitized payload is sent;
- strict JSON response is required and validated;
- invalid/timeout/error result degrades safely;
- AI is called only for eligible grey-zone events;
- AI is not called for every event;
- deterministic result is preserved when AI fails;
- TSV contains deterministic and AI comparison columns;
- AI artifacts are created and safe;
- no CRM/mailbox/Bitrix mutation exists;
- no `beeagent-rop` private internals are imported;
- BeeAgent core does not add ROP business classification rules;
- tests, smoke, docs and required security checks are completed;
- `pyproject.toml.version` is not changed.

#### Implementation notes (It34)

Config:

- `rop.ai_assist.adjudicator` – config block inside the existing `rop.ai_assist` does not create the second source of truth;
- `ai.prompts` and `ai.profiles` are shared BeeAgent AI source of truth for prompt/provider/model config;
- AI disabled by default.

New module:

- `src/beeagent_module/core/rop_ai_adjudicator.py` — OpenAI Responses API execution, bounded payload, JSON schema validation, deterministic fallback, safe artifacts;
- `call_openai_responses_api()` – HTTP call to `/v1/responses` with `json_object` format;
- `run_adjudicator_for_event()` — per-event adjudication: eligibility → prompt → API → parse → validate → merge/degrade;
- `run_adjudicator_batch()` – batch wrapper with `max_events_per_run`;
- `write_adjudicator_artifacts()` — `rop_ai_adjudicator_requests.json`, `rop_ai_adjudicator_decisions.json`, `rop_ai_adjudicator_results.json`.

Integration:

- `run_rop_batch_case()` in `rop_operator.py` calls `run_adjudicator_batch()` after AI assist, to summary;
- adjudicator counters is recorded in `classification_diagnostics`.

TSV:

- 13 new columns: `ai_used`, `ai_provider`, `ai_model`, `ai_confidence`, `ai_reason`, `ai_risk_flags`, `ai_error`, `deterministic_case_type`, `deterministic_case_subtype`, `deterministic_recommended_queue`, `deterministic_correct_action`, `deterministic_confidence`, `deterministic_reason_code`.

Tests:

- `tests/test_rop_ai_adjudicator.py` - 41 test: eligibility, prompt building, JSON parsing, validation, provider call, per-event adjudication, batch, artifacts, config validation.

### Iteration 35 — ROP duplicate runtime integration and reviewed classifier rollout v1

**Status:** DONE

#### Goal

Connect released duplicate-aware `beeagent-rop` classification contract to the real ROP batch path so that current-batch duplicates is defined by domain- module, stored in artifacts/final decisions and visible to ROP Queue/Event Detail without duplication of business matching logic to BeeAgent.

#### Scope

Includes:

- consume released `beeagent-rop` contract from Iteration 20;
- Save BeeAgent responsibility for orchestration/context/artifacts/UI only;
- build deterministic bounded duplicate candidate context from the already loaded events of the current ROP batch;
- Limit duplicate candidates to the same client scope;
- To compare the current event with the previous canonical candidates only;
- use source timestamp with deterministic fallback/tie-break for stable canonical ordering;
- Do not compare event to yourself;
- do not convert the duplicate already discovered into a new canonical original;
- Transfer candidate context to public `lead_classification` module call;
- do not implement sender/subject/body similarity thresholds in BeeAgent;
- Accept module-returned `case_type=duplicate` and structured duplicate evidence;
- Keep base classification / duplicate candidate / confidence / reason traceability in ROP artifacts;
- Guarantee that final decision retains confident deterministic `duplicate`;
- explicit skip/preserve behavior for duplicate in AI adjudicator path;
- ensure that summary/current-state/dashboard does not lose duplicate;
- Show duplicate in Queue;
- ensure that `Duplicate` appears in Classification filter if duplicate rows is available;
- Show bounded duplicate evidence in Event Detail;
- Add integration fixtures/smoke to exact duplicate, near duplicate, non-duplicate and cross-source same-client scenario;
- Check reviewed classifier outcomes after module dependency has been updated;
- Update docs and dependency pin only to the actual version of `beeagent-rop`.

#### Excluded

- new duplicate matching rules in BeeAgent;
- Change domain thresholds;
- cross-run persistent duplicate database/index;
- historical mailbox duplicate search;
- live CRM/Bitrix entity-resolution as duplicate source;
- Bitrix merge/write-back;
- automatic deletion/suppression of duplicate emails;
- change AI in the main classifier;
- AI safety merge weakening for reviewed supplier false positives;
- mailbox connector redesign;
- attachment parser/OCR changes;
- New database/storage subsystem;
- New config surface needless;
- BeeAgent `pyproject.toml.version` change.

#### Deliverable

ROP runtime transmits current-batch candidate context to `beeagent-rop`, receives domain-owned duplicate-aware classification, saves audit evidence and shows `duplicate` as a complete classification to Queue/Event Detail.

#### Acceptance criteria

- production ROP batch actually uses duplicate-aware module contract;
- The second exact duplicate in the current client-scoped batch receives `case_type=duplicate`;
- canonical first occurrence does not become duplicate its subsequent repetition;
- near duplicate is defined by module result only;
- unrelated similar emails does not receive false duplicate;
- candidates of the other client scope is not comparable;
- duplicate candidate/confidence/reason is available on artifacts;
- base semantic classification is available for audit;
- `rop_final_decisions.json` retains deterministic duplicate;
- AI adjudicator does not turn confident duplicate into invalid/manual-review result;
- Queue shows duplicate rows;
- Classification filter automatically contains Duplicate if there is such rows;
- Event Detail explains where the candidate match was found;
- existing new-lead/existing-deal/irrelevant flows remains backward-compatible;
- reviewed It20 scenarios passes BeeAgent integration regression.

#### Checks

- `uv run pytest -q`;
- targeted ROP batch integration tests;
- module contract integration smoke;
- exact duplicate current-batch test;
- canonical ordering test;
- near-duplicate test;
- non-duplicate false-positive test;
- client-scope isolation test;
- multi-source same-client test where applicable;
- AI-adjudicator duplicate preservation test;
- final-decision artifact test;
- dashboard/Queue/Event Detail read-model tests;
- ROP runtime smoke through intended entrypoint;
- inspect `classified_events.json`;
- inspect `rop_final_decisions.json`;
- inspect relevant Queue/Event Detail output;
- inspect `logs/app.log`;
- SAST;
- SCA for the updated `beeagent-rop` dependency release;
- DAST/IAST/fuzzing not required for this scope;
- no secrets/raw email payloads added to committed fixtures;
- BeeAgent version unchanged.

#### DoD

- duplicate engine is no longer disconnected from production ROP flow;
- BeeAgent only supplies deterministic candidate context and does not own duplicate semantics;
- later duplicate occurrence is distinguishable from canonical original;
- `duplicate` reaches artifacts, final decision and operator UI;
- reviewed classifier improvements from `beeagent-rop` are consumed successfully;
- no cross-run/CRM overengineering is introduced;
- no automatic destructive duplicate action is added;
- AI safety boundaries remain intact;
- runtime, artifact and UI checks are green;
- dependency points to an actually released compatible module version;
- docs are updated;
- BeeAgent version is not changed;
- PR is ready to close Iteration 35.

#### Implementation notes (It35)

Canonical ordering:

- events is processed in deterministic in `(received_at/date/event_date/timestamp ASC with UTC normalization, event_id tie-break)` within `_classify_normalized_events`, so earliest event becomes canonical original, and the later exact/near re-tried `case_type=duplicate` relative to it;
- BeeAgent assigns to each normalized processing item additive `event_instance_id` within run; public transport/business `event_id` remains unchanged module contract, and selector is used only for artifact joins and Queue/Event Detail navigation, so the repeated Message-ID does not cough up downstream;
- duplicate candidates is built only from canonical events of the current batch; in canonical pool only confirmed `case_type=duplicate` events are excluded, and successful semantic/fallback module classifications remains candidates independently of `is_fallback`; BeeAgent-generated processing failure/non-ok events in pool do not occur (they go through controlled fallback outside pool); scope is limited to `client_id`, self-match is excluded;
- candidate records are passed to public `lead_classification` contract through `payload.duplicate_candidates` (bounded keys: `existing_lead_id`, `sender`, `subject`, `body`, `event_id`, `thread_id`, `message_id`, `raw_metadata`), ordered by source timestamp with `event_id` tie-break;
- matching thresholds/reason semantics remains in `beeagent-rop` (`EntityResolutionService`), BeeAgent does not duplicate duplicate logic.

Runtime integration (`rop_operator.py`):

- `_build_duplicate_candidates(...)`, `_duplicate_candidate_from_event(...)`, `_is_eligible_canonical_source(...)`, `_event_source_sort_key(...)`;
- `_classify_normalized_events` supports canonical pool and transmits `duplicate_candidates` to per-event `lead_classification`;
- `classification_diagnostics["duplicate_count"]` in `operator_summary.json`;
- legacy AI assist (`_is_event_eligible_for_ai_assist`) and AI adjudicator (`_is_event_eligible_for_adjudicator`) are clearly skip deterministic `duplicate`.

Artifacts / final decisions:

- `classified_events.json` retains module-returned `base_classification` and `duplicate` (bounded candidate/confidence/reason evidence);
- `rop_final_decisions.json` adds `base_classification` and `duplicate` to each final decision event (None, when there is no duplicate context); deterministic confident duplicate retained as `deterministic_case_type/final_case_type=duplicate`, `final_decision_source=deterministic`, without AI invalidation;
- `_is_final_decisions_payload` validates the new optional fields (backward-compatible).

UI:

- Queue (`rop_dashboard._build_queues`, `rop_current_state._build_queues`) adds `case_type=duplicate` rows to `needs_review`;
- `rop_current_state._build_kpi` accounts for duplicates in `needs_manual_review`;
- Classification filter automatically contains `Duplicate` with duplicate rows (`_build_filter_options`);
- Event Detail (`rop_event_detail`) shows bounded duplicate evidence: candidate event/existing_lead id, confidence, reason_code/path, matched_fields, reasoning, `base_case_type`.

Reason catalog:

- display has been added for the new public reason code `duplicate_candidate_confirmed` (It20 reviewed classifier rollout), coverage test green.

Dependency model:

- BeeAgent consumes `beeagent-rop==0.19.2` from the declared private sibling `uv` source (`[tool.uv.sources] beeagent-rop = { path = "../beeagent-rop", editable = true }`); `uv sync --frozen` succeeds and the installed module reports version 0.19.2.
- Registry/PyPI publication is not a prerequisite of the current private-module dependency model; the local editable source is the working resolution and is intentionally kept for development.
- No dependency/version change is introduced by this iteration; `pyproject.toml` and `uv.lock` are untouched.

### Iteration 36 — ROP multi-mailbox recipient routing and Bitrix responsible draft v0

**Status:** DONE

#### Goal

The extension of production ROP polling from one mailbox source to several configured mailbox sources and the retention of the address of each email to Bitrix draft layer: BeeAgent must deter business recipient from the existing mailbox evidence, allow recipient email in active Bitrix user via read-only lookup and show proposed responsible in artifacts/action draft/Event Detail without CRM write-back and without change business-classification semantics in `beeagent-rop`.

Target flow:

```text
enabled mailbox sources
→ per-source UID poll/checkpoint
→ normalized event with source_id / To / Cc / original_recipient
→ deterministic recipient attribution
→ beeagent-rop classification
→ read-only Bitrix user resolution
→ rop_recipient_routing.json
→ action draft / Event Detail proposed responsible
→ no CRM mutation
```

#### Scope

Includes:

- Save existing `rop.sources[]` as the only source of truth for mailbox sources;
- Expand `rop.mailbox_poll` to controlled all-enabled-sources mode with backward-compatible single-source mode;
- Do not add a separate duplicate mailbox source IDs list;
- Support optional CLI source override for safe per-source poll/rebaseline;
- perform production poll independently for each enabled `mailbox_readonly` / `read_only` source;
- Save per-source UIDVALIDITY / last_processed_uid checkpoint semantics;
- Save at-least-once invariant: checkpoint of the specific source only moves after successful ROP pipeline and mandatory postprocessing for this source;
- failure of one mailbox source must not stop the attempt to treat the remaining selected sources;
- successful source checkpoints does not roll back because of failure of the other source;
- the new source without checkpoint only receives its baseline without changing checkpoint already existing sources;
- Use existing normalized fields `source_id`, `source_role`, `source_display_name`, `client_id`, `to`, `cc`, `original_recipient`, `forwarded_wrapper`;
- Add optional source routing fallback `routing.email_recipient` for mailbox source;
- `routing.email_recipient` is business recipient fallback and must not be taken from IMAP username/env;
- deterministic recipient attribution precedence:
  - `original_recipient`;
  - `to`;
  - configured source recipient fallback;
  - unresolved;

- Several recipient candidates on one evidence level → `ambiguous`, without choosing the first;
- `cc` may be retained as evidence, but not used for automatic responsible selection;
- Add BeeAgent-owned read-only Bitrix user lookup through exact normalized email;
- expand existing `BitrixReadonlyClient` only read-only method/capability, without adding CRM writes;
- active exact email match only; No fuzzy user matches;
- Bitrix user directory must be loaded bounded in a manner that is not requested separately for each email;
- create artifact:
  - `storage/runs/<run_id>/rop_recipient_routing.json`;

- artifact must retain `event_id` + `event_instance_id`, source provenance, recipient status/evidence and proposed Bitrix responsible;
- statuses must clearly distinguish at least:
  - `resolved`;
  - `ambiguous`;
  - `unresolved`;
  - `matched`;
  - `not_found`;
  - `connector_degraded`;

- Enrich `rop_action_drafts.json` proposed recipient/responsible evidence;
- Save action drafts `read_only=true` / `draft_only=true`;
- Minimum display source / recipient / proposed responsible in existing ROP Event Detail;
- Keep the existing `beeagent-rop` classification/subtype/queue/action semantics unchanged;
- Update ROADMAP/README/DEV_GUIDE/WEB_UI where config/artifact/UI contracts. changes

#### Excluded

- changes to `beeagent-rop`;
- new ROP classification rules in BeeAgent;
- `crm.item.add`;
- `crm.item.update`;
- `crm.item.delete`;
- lead/deal/task creation;
- automatic responsible assignment in Bitrix;
- execution-capable Bitrix adapter;
- automatic timeline comments;
- mailbox delete/archive/reply/mark-as-read;
- fuzzy email/user matching;
- Bitrix user ID stored as source-of-truth config;
- using IMAP username as business recipient;
- use of `Cc` for automatic responsible selection;
- automatic inference of deliberate human reassignment from email forwarding;
- responsible reassignment / override workflow;
- assumption that existing `rop.routing.queues.*.bitrix_category` is a real Bitrix `categoryId`;
- CRM stage/category/custom-field mapping for write-back;
- new `region_code` contract without a concrete downstream requirement;
- new BeeUI generic components;
- broad Queue/filter redesign;
- 1C integration;
- dependency changes unless implementation proves they are required.

#### Deliverable

BeeAgent production ROP poll can process all enabled mailbox sources independently and preserve recipient provenance through the draft layer.

For every processed event BeeAgent can show:

```text
source mailbox
business recipient
recipient evidence source
recipient resolution status
proposed Bitrix responsible user
responsible match status
```

Expected new artifact:

```text
storage/runs/<run_id>/rop_recipient_routing.json
```

Existing draft/UI artifacts remain non-executing.

#### Acceptance criteria

- existing single-source mailbox poll remains backward-compatible;
- all-sources poll processes all enabled read-only mailbox sources;
- one mailbox failure does not prevent other selected sources from being processed;
- failed source checkpoint is not advanced;
- successful source checkpoint is advanced only after full source flow succeeds;
- adding a new source does not reset existing source checkpoints;
- per-source rebaseline does not require resetting unrelated sources;
- direct mail can resolve recipient from `To`;
- forwarded mail can resolve recipient from `original_recipient`;
- configured source recipient is used only as fallback;
- multiple recipients are not silently reduced to the first address;
- `Cc` never assigns responsible;
- malformed/missing recipient evidence degrades to explicit unresolved/ambiguous status;
- Bitrix user lookup uses exact normalized email only;
- inactive user is not accepted as responsible;
- no matching user produces explicit `not_found`;
- multiple exact eligible users produce explicit `ambiguous`;
- Bitrix connector failure produces explicit degraded state;
- recipient/user lookup is not executed once per email;
- `rop_recipient_routing.json` is bounded and contains `event_instance_id`;
- action drafts contain proposed recipient/responsible evidence;
- Event Detail exposes source, recipient and proposed responsible;
- `automation_allowed` and `bitrix_write_allowed` remain false;
- no CRM/mailbox mutation exists;
- `beeagent-rop` public contract remains unchanged.

#### Known limitation

Deliberate human reassignment by forwarding an email from one business mailbox to another cannot be reliably distinguished from ordinary transport forwarding using email headers alone. It36 therefore preserves deterministic `original_recipient` precedence; proposed responsible remains read-only/draft-only and may require operator correction for this edge case. Automatic reassignment inference and a responsible override/reassignment workflow are outside It36 and require a separate explicit workflow/policy contract.

#### Checks

Required:

```bash
uv run pytest -q
uv run pytest -q -k "rop or mailbox or bitrix or ui or web"
```

Targeted verification:

```text
mailbox_poll single-source backward compatibility
mailbox_poll all enabled sources
multi-source no-new-message behavior
one source failure + one source success
successful-source checkpoint commit
failed-source checkpoint preservation
postprocessing failure does not advance affected checkpoint
new source baseline preserves existing checkpoints
per-source rebaseline
UIDVALIDITY failure isolated to affected source

recipient original_recipient precedence
recipient To fallback
configured source recipient fallback
multiple To recipients -> ambiguous
Cc ignored for responsibility
missing/malformed recipient -> unresolved
recipient email normalization

Bitrix exact active user match
Bitrix inactive user rejected
Bitrix no user -> not_found
Bitrix duplicate exact users -> ambiguous
Bitrix permission/transport/error -> connector_degraded
bounded user pagination/directory lookup
no per-event Bitrix user API loop

rop_recipient_routing.json contract
event_instance_id preserved
action draft responsible enrichment
Event Detail recipient/responsible evidence
missing/malformed optional routing artifact degrades safely
HTML/API escaping
no write method callable
```

Security:

```text
SAST required
SCA only if dependencies change
DAST-style connector misuse/error checks required for changed Bitrix runtime behavior
IAST not required
fuzzing not required unless a new custom email parser is introduced
```

Optional live read-only smoke only when the required mailbox/Bitrix credentials and permissions are available.

#### DoD

- production mailbox poll is no longer limited to one configured mailbox;
- checkpoint semantics remain independent and safe per source;
- partial mailbox degradation does not discard successful source work;
- BeeAgent preserves actual recipient evidence through forwarding;
- recipient attribution is deterministic and explainable;
- Bitrix responsible resolution is exact-email/read-only;
- Bitrix remains identity source of truth; Bitrix user IDs are not hardcoded into mailbox config;
- `rop_recipient_routing.json` exists and is safe to inspect;
- proposed responsible is visible in action draft and Event Detail;
- all outputs remain read-only/draft-only;
- no Bitrix write-back is introduced;
- no mailbox destructive action is introduced;
- no new ROP business rules are added to BeeAgent;
- `beeagent-rop` is unchanged;
- no secrets/raw `.eml`/raw attachment content are exposed;
- tests/docs/security checks are completed;
- `pyproject.toml.version` is not changed.

### Iteration 37 — Controlled Bitrix CRM write-back v0

**Status:** DONE

#### Goal

Translate the existing read-only/draft Bitrix flow to the restricted production write-back: each classified ROP- event must receive an explicit Bitrix delivery decision, new ledes to be created through `crm.item.add`, emails on securely found existing CRM entities attached to them without creating a duplicate, and the responsible person to be identified from the already implemented recipient routing.

`should_rop_see` field must not permit or prohibit Bitrix. shipment

#### Scope

- to implement write-back only in `beeagent`, unchanged `beeagent-rop`;
- Retain the existing `BitrixReadonlyClient` strictly read-only;
- Add a separate bounded execution-capable Bitrix boundary with a separate write credential;
- Add config-driven `bitrix.writeback` policy and fail-fast validation;
- Keep Bitrix `stageId` as variable config rather than hardcoded business value;
- Insert `irrelevant` in read-only reconciliation and delivery planning;
- Use existing safe reconciliation result to select existing CRM target;
- allow safe Deal target only after exact sender email/phone → Contact/Company → bounded read-only `crm.item.list` relation lookup (`entityTypeId=2`, `contactId`/ `companyId`): One Deal strong/safe, multiple/none/error fail closed; title/subject never authorizes Deal targeting;
- Consider Contact/Company only identity evidence: after successful exact Lead and related-Deal searches without executable target `identity_only_no_target` allows configured create only for `new_lead`/`irrelevant`;
- Use existing `rop_recipient_routing.json` for exact responsible resolution;
- `new_lead` and `irrelevant` without safe existing target be created as Lead through `crm.item.add`, `entityTypeId=1`;
- `existing_deal` / `duplicate` and any safe existing target process through attach-existing path without creating a new Lead;
- unsafe/ambiguous target or responsible translate to explicit pending/deferred state without silent drop;
- Use deterministic cross-run event identity for idempotency;
- Save durable write-back intent to mailbox checkpoint commit;
- Add bounded retry/recovery for retryable and uncertain Bitrix failures;
- Save per-run write-back state/results without credentials, raw `.eml` and raw attachments;
- Add controlled CLI/runtime path for pending write-back execution;
- Simulate operator-facing draft semantics with execution plan;
- Update tests and documentation.

#### Excluded

- classification, duplicate thresholds or taxonomy in `beeagent-rop`;
- use of deprecated `crm.lead.add`;
- broad `crm.item.update` / `crm.item.delete`;
- automatic reassignment of existing CRM entity;
- fuzzy responsible or CRM-target matching;
- using `should_rop_see` as execution gate;
- using `rop.routing.queues.*.bitrix_category` as Bitrix stage ID;
- hardcoded customer stage names/IDs;
- raw `.eml` persistence in BeeAgent artifacts;
- arbitrary custom-field upload instead of the official email-binding contract;
- Bitrix write actions of GET/UI routes;
- operator control panel and config editor;
- dependency changes without separate justification.

#### Deliverable

BeeAgent has disabled-by-default, idempotent and auditable Bitrix write-back flow: each processed event receives `create_lead`, `attach_existing` or explicit deferred outcome; successful new Lead receives configured stage and exact mapped responsible; repeated processing the same email does not create the second CRM object or the second email attachment.

#### Acceptance criteria

- `should_rop_see=false` does not exclude an event from Bitrix delivery planning;
- `irrelevant` without existing target is created as Lead in configured classification stage;
- `new_lead` is created by `crm.item.add` with `entityTypeId=1`;
- safe existing lead/deal receives email attachment and does not create a new Lead;
- ambiguous/unsafe existing target is never automatically selected;
- unresolved/ambiguous responsible is not replaced by Bitrix caller default;
- configured stage IDs are validated to POST;
- repeated run/poll of one email does not create duplicate Lead;
- uncertain POST outcome reconciles before retry;
- Bitrix outage does not lose pending work and does not require mailbox ingestion to be repeated;
- read-only Bitrix client does not receive write methods;
- credentials/raw email/raw attachments does not enter logs/artifacts;
- `beeagent-rop` public contract remains unchanged.

#### Checks

- `uv run pytest -q`;
- targeted settings, reconciliation, recipient-routing, write-back planner and executor tests;
- create-lead, irrelevant, existing-target, duplicate, ambiguous and degraded scenarios;
- idempotent replay and ambiguous-timeout recovery;
- mailbox checkpoint versus durable-intent regression;
- 400/401/403/429/5xx/timeout/malformed-response scenarios;
- dry-run/disabled mode with zero Bitrix mutations;
- controlled Bitrix test-portal smoke after stage IDs and email-binding API are confirmed;
- logs/artifacts review for secret and raw-content leakage;
- SAST;
- DAST-style external connector misuse/error checks;
- SCA only if dependency files unexpectedly change.

#### DoD

- production write-back authority is only located in BeeAgent server-side policy;
- all classified events enter the delivery plan without `should_rop_see` filtering;
- create versus attach behavior is deterministic and explainable;
- durable pending state survives restart/retry;
- mailbox checkpoint semantics no longer depend on Bitrix availability after durable intent persistence;
- CRM creation and email attachment are idempotent;
- stage/responsible/target failures fail closed;
- exact official Bitrix email-binding contract is documented and tested;
- no unnecessary write methods are exposed;
- no changes are required in `beeagent-rop`;
- dependencies and `uv.lock` remain unchanged unless separately approved;
- `pyproject.toml.version` is not changed;
- tests, smoke evidence, logs/artifacts and documentation are ready for PR review.

#### Implemented (v0, Issue #199)

- `bitrix.writeback` config (disabled by default) with fail-fast validation; `email_attach` (email-activity binding for created ledes) and `source_id` (Lead SOURCE_ID);
- Individual `BitrixWriteClient` with exact mutation allowlist `crm.item.add` / `crm.activity.add` and separate env credential; `BitrixReadonlyClient` remains strictly read-only, and `crm.activity.list` is used only for idempotency lookup;
- `irrelevant` is included in read-only reconciliation;
- safe existing Deal becomes reachable only through exact Contact/Company communication evidence and bounded read-only generic Deal relation lookup; title/subject remains unsafe;
- exact Contact/Company without an executable Lead/Deal remains identity-only evidence; `identity_only_no_target` may enter configured create only for `new_lead`/`irrelevant`;
- authoritative write-back planner/executor with outcomes `create_lead` / `attach_existing` / `deferred`, canonical durable state `storage/interfaces/rop_writeback_state.json`, idempotent `crm.item.add` (`entityTypeId=1`) with bounded `ORIGINATOR_ID`/`ORIGIN_ID`, recovery uncertain POST to idempotency lookup, bounded retry and fail-closed stage/ responsible/target processing;
- Attaching the email to the created or safe existing Lead/Deal via the official `crm.activity.add` (email activity, `TYPE_ID=4`) at `bitrix.writeback.email_attach: true`; Before each activity POST, including timeout or malformed response, read-only `crm.activity.list` checks stable origin identity and returned activity ID retains canonical state;
- durable intent persist is going to mailbox checkpoint advancement; normal poll ordering – durable intent → checkpoint → external execution → original per-run projection refresh, while temporary reconciliation outage remains recoverable deferred state for later poll/run without mailbox re-ingestion;
- CLI `rop writeback plan/execute`;
- per-run the operating projection `rop_writeback_summary.json` and read-only action drafts refresh are made of canonical state for each original run after execution/recovery; `rop run` cannot report success if reconciliation or durable plan persistence have not created intent.

Official binding contract: Bitrix documents email activity through [`crm.activity.add`](https://apidocs.bitrix24.com/api-reference/crm/timeline/activities/activity-base/crm-activity-add.html) with `TYPE_ID=4`, `OWNER_TYPE_ID`, `OWNER_ID`, `COMMUNICATIONS` and `RESPONSIBLE_ID`; It [`crm.activity.list`](https://apidocs.bitrix24.com/api-reference/crm/timeline/activities/activity-base/crm-activity-list.html) supports field filters for remote idempotency reconciliation. Safe existing Lead/Deal receives exactly one activity to source stable email identity without `crm.item.add` and remains mandatory responsible target entity. Existing-target live smoke before production enablement; before it Iteration 37 is not DONE.

### Iteration 38 — Thread-aware Bitrix email write-back hardening v1

**Status:** DONE

#### Goal

Make Bitrix write-back thread-aware: a continuation of the already known email- correspondence must be attached to the exact Lead/Deal of the previous email, and the new independent request of the existing client must not automatically be attached to the old CRM entity simply because of the coincidence of sender email/phone.

At the same time, improve bounded email body normalization for Bitrix email activity: delete DOCTYPE/HTML markup and save the reading/translation lines without raw HTML, raw `.eml` or attachment content.

#### Scope

- implement only the changes in `beeagent`;
- Keep `beeagent-rop` public contract unchanged;
- Use existing normalized `Message-ID`, `In-Reply-To` and `References` as exact thread evidence;
- Add BeeAgent-owned cross-run thread-to-CRM target resolution above existing durable write-back state;
- Do not create a separate thread database if existing `storage/interfaces/rop_writeback_state.json` is sufficient;
- Select customer identity and CRM target authority:
  - sender email/phone defines identity/candidate evidence;
  - identity evidence alone does not permit `attach_existing`;
- Allow automatic existing-target attach only at exact trusted target evidence;
- Use confirmed previous BeeAgent-created Lead as authoritative thread root;
- legacy `attach_existing` records without trusted target provenance must not be used as automatic thread authority;
- If `In-Reply-To` / `References` is clearly resolve in one existing Lead/Deal — attach the email there without creating a new Lead;
- if thread references indicates conflicting targets - fail closed to ambiguous/deferred;
- If exact thread target is missing:
  - `new_lead` / `irrelevant` use normal configured create path;
  - `existing_deal` / `duplicate` without another safe target remain deferred/manual-review;
- same sender email/phone must not block the creation of a new independent `new_lead`;
- Save existing responsible of the existing CRM entity;
- Save write-back idempotency, retry/recovery and durable-intent-before-checkpoint semantics;
- Add bounded target-resolution provenance to reconciliation/write-back artifacts/state;
- improve body preview normalization:
  - Delete `<!DOCTYPE ...>`, comments, script/style and HTML tags;
  - convert safe structural HTML boundaries (`br`, paragraph/block/list boundaries) into line breaks;
  - Retain line breaks plain-text emails;
  - Normalize excessive whitespace without slamming a single email into one line;
  - Save existing `rop.email_preview.body_chars_max`;
  - Do not add a new parsing dependency;
- Update tests and documentation.

#### Excluded

- classification/taxonomy/duplicate logic changes to `beeagent-rop`;
- `existing_deal`, AI output, `RE:`, `FWD:` or subject similarity as CRM mutation authority;
- fuzzy automatic thread-to-CRM matching;
- automatic attach to historical Lead/Deal only on sender email/phone;
- arbitrary historical Bitrix email-thread backfill;
- Automatic restoration of thread binding for letters that BeeAgent has never previously linked to CRM target;
- manual CRM target mapping UI;
- CRM reassignment;
- `crm.item.update` / `crm.item.delete`;
- Extension of Bitrix write-method allowlist;
- raw `.eml` persistence;
- raw MIME/HTML rendering;
- attachment content rendering;
- full browser-quality HTML rendering;
- New HTML/parser dependency;
- Changes to BeeUI;
- version bump.

#### Deliverable

BeeAgent distinguishes between identity client and identity correspondence. For email thread, whose ancestor already has trusted BeeAgent CRM binding, the next exact reply is automatically attached to the same Lead/Deal. New independent request of the same sender could create a new Lead.

Email activity description in Bitrix contains bounded readable plain text without DOCTYPE/HTML tags and without loss of normal paragraphs/line breaks.

#### Acceptance criteria

- existing Lead with the same sender email is not safe CRM target per se;
- existing Lead/Deal with exact phone/email identity alone does not receive `safe_to_use_as_target=true`;
- new independent `new_lead` of sender, already present in the old Lead, could create a new Lead;
- first email `A` may create Lead `L1`;
- later email `B` with exact `In-Reply-To`/`References` to `A` attaches to `L1`;
- reply attachment does not call `crm.item.add`;
- chained replies `A → B → C` preserve the same CRM target;
- two independent threads from the same sender may resolve to two different Leads;
- conflicting thread references never choose a target automatically;
- missing/malformed thread headers degrade safely and never authorize mutation;
- run-local `thr_*` IDs are not used as durable CRM target identity;
- legacy write-back records without trusted target provenance are not silently promoted to automatic thread authority;
- classifier `existing_deal`, AI output, subject similarity and `RE:`/`FWD:` markers alone cannot authorize CRM attachment;
- existing target responsible is not reassigned;
- replay does not create duplicate Lead or duplicate email activity;
- durable intent remains persisted before mailbox checkpoint advancement;
- HTML `DOCTYPE`, script/style and markup do not appear in Bitrix body preview;
- safe HTML block boundaries become readable line breaks;
- plain-text line breaks are preserved;
- body preview remains bounded by existing configured limit;
- no raw `.eml`, attachment content, credentials or webhook URLs appear in artifacts/logs;
- `beeagent-rop` remains unchanged.

#### Checks

- `uv run pytest -q`;
- targeted `test_rop_input_source.py`;
- targeted `test_bitrix_reconciliation.py`;
- targeted `test_rop_writeback.py`;
- targeted mailbox poll/checkpoint tests;
- independent same-sender new-request regression;
- exact cross-run reply-to-existing-Lead regression;
- multi-reply chain regression;
- same sender with two independent threads regression;
- conflicting References regression;
- malformed/missing thread-header regression;
- replay/idempotency regression;
- legacy state without target provenance regression;
- HTML DOCTYPE removal regression;
- HTML paragraph/`br` readability regression;
- plain-text line-break preservation regression;
- script/style/entity/bounded-preview security regressions;
- `uv run python -B -m compileall -q src tests`;
- `git diff --check`;
- SAST required;
- DAST-style controlled Bitrix test-portal smoke required;
- SCA only if dependency files unexpectedly change;
- IAST not required;
- fuzzing optional; malformed/adversarial thread-header and HTML normalization tests are required.

#### DoD

- customer identity no longer doubles as CRM target authority;
- exact cross-run RFC thread evidence can resolve a trusted CRM target;
- continued correspondence attaches to the correct Lead/Deal;
- an independent new request from a regular customer can create a new Lead;
- ambiguous or untrusted target evidence fails closed;
- write-back remains idempotent and auditable;
- existing mailbox checkpoint/recovery semantics remain intact;
- email activity body is readable bounded plain text;
- no new parser dependency is added;
- no Bitrix mutation method is added;
- `beeagent-rop` remains unchanged;
- `pyproject.toml.version` is not changed;
- tests, security checks, live controlled Bitrix smoke and docs are ready for PR review.

#### Implemented (v1, Issue #203)

- customer identity (sender email/phone, Contact/Company and related historical CRM relation) is no longer automatic execution target: reconciliation never emits `safe_to_use_as_target=true` for identity-only Lead/Deal matches; Such matches remains strong identity/candidate evidence (`matched_*` c `safe_to_use_as_target=false` and `needs_manual_review=true`);
- cross-run exact thread-to-CRM resolution above existing `storage/interfaces/rop_writeback_state.json` without separate thread database: exact `In-Reply-To` (preferred) and bounded `References` ancestry are required to agree on one trusted target, otherwise `ambiguous_thread_target` deferred with zero mutation;
- bounded target provenance in write-back state: confirmed BeeAgent-created Lead (`target_provenance=beeagent_created`) is authoritative thread root; thread-resolved attach (`target_provenance=thread_resolved`) distributes target along the chain; legacy records without trusted provenance are not thread authority (fail closed)
- matching scope – same `client_id`, not necessarily same `source_id`;
- exact reply with thread references is attached to the same Lead/Deal without a new `crm.item.add`; `A → B → C` stores target; Two independents of one sender may regress into different Leadss; independent `new_lead` from the famous sender could create a new Lead;
- `existing_deal`/`duplicate` without safe exact target remain deferred/manual-review; run-local `thr_*` is never used as durable CRM identity; classifier/AI/ subject/`RE:`/`FWD:` markers alone does not authorize attach; existing target responsible retained (without reassignment);
- same-run reply to planned create at the same batch receives recoverable `pending_thread_root` deferred and re-enlists upon confirmation of root;
- bounded body preview normalization: removal of `<!DOCTYPE ...>`/comments/script/style/ HTML tags, safe structural HTML boundaries (`p`/`div`/`br`/`li`/list/table...) become readable line breaks, plain-text line breaks are preserved, excessive whitespace bounded, the existing `rop.email_preview.body_chars_max` is preserved, without a new parsing dependency;
- bounded thread headers (`in_reply_to`/`references`) and target-resolution provenance are added to classified events and write-back state/summaries;
- optional `bitrix.writeback.user_id_fallback` appoints the responsible person only at `responsible.status=not_found`; matched, ambiguous, degraded, unresolved and not-attempted remain deferred; optional `bitrix.writeback.email_completed` (boolean, default `true`) asks if the email- activity created is complete (`false` = email incomplete / visible on timeline);
- `beeagent-rop` public contract did not change; dependencies/`uv.lock` has not changed.

Live controlled Bitrix test-portal smoke (A creates L1 → reply B is attached to L1 → independent C creates L2 → reply D is attached to L2) remains mandatory prior to production enablement; before it Iteration 38 is not considered in its entirety DONE.

### Iteration 39 — ROP conversation identity and AI decision hardening v2

**Status:** DONE

#### Goal

Correct the systemic causes of reviewed classification mismatches and broken Bitrix email threads: BeeAgent must use AI as the second semantic verification echelon for business-impacting decisions, stop counting on operator `manual_review` as normal classification path and build cross-run/cross-mailbox conversation evidence without weakening trusted CRM target boundary It38.

#### Scope

- consume hardened `beeagent-rop` reviewed classification behavior;
- expand AI adjudicator eligibility to business-impacting `new_lead` / `existing_deal`;
- Save skip for confirmed duplicate and clearly secure strong-noise cases;
- pass AI bounded body, attachment, thread and relevant Bitrix context;
- Make `ai_reason_code` mandatory for newly generated valid AI decisions;
- Save compatibility rendering historical AI artifacts;
- Replace single global confidence-only merge with bounded class/evidence-aware merge;
- do not use semantic `manual_review` as normal terminal operator queue;
- provider/validation failure retains deterministic semantic result with diagnostics;
- Save fail-closed `deferred` for unsafe CRM target/execution;
- Enter BeeAgent-owned conversation relation separately from domain `case_type`;
- Save exact RFC It38 `Message-ID` / `In-Reply-To` / `References` authority;
- Support exact cross-source conversation binding within one `client_id`;
- Implement controlled Bitrix outbound-correlation evidence check;
- use Bitrix outbound bridge only if exact stable correlation evidence is available;
- weak sender/subject/time matching to be used as candidate evidence only;
- expand Event Detail to full cross-run conversation timeline;
- Clearly display deterministic decision, AI proposal and final decision.

#### Excluded

- automatic `existing_deal` solely because a CRM target was found;
- fuzzy sender/subject matching as CRM mutation authority;
- weakening It38 trusted-target rules;
- arbitrary historical Bitrix thread guessing;
- new thread database unless existing artifacts/state prove insufficient;
- new Bitrix mutation methods;
- raw `.eml` or raw attachment persistence;
- BeeUI domain logic;
- claim of 100% accuracy on arbitrary future mail;
- version bump.

#### Deliverable

ROP runtime receives a two-tiered semantic classification pipeline and separate conversation layer. Reviewed classifications passes regression gate, Bitrix/RFC continuation saves trusted CRM binding where there is exact evidence, and Event Detail shows a complete correspondence history.

#### Acceptance criteria

- all 8 reviewed integration scenarios reach expected final semantic type;
- high-confidence deterministic `new_lead` is no longer automatically exempt from AI verification when business-impacting;
- strong explicit irrelevant/noise may remain AI-free;
- valid new AI artifacts always carry known `ai_reason_code`;
- historical missing reason codes remain backward-compatible;
- new artifacts do not silently report a missing reason as merely legacy;
- normal semantic processing does not terminate in an unconsumed `manual_review` queue;
- provider failure preserves a deterministic result and explicit diagnostics;
- unsafe CRM targets still fail closed as deferred;
- semantic `case_type` is not overwritten solely because a conversation/CRM target exists;
- exact RFC replies across different mailbox sources resolve within the same client scope;
- Bitrix-generated broken-thread replies auto-link only when exact outbound correlation evidence is proven;
- weak subject/sender/time correlation never authorizes CRM mutation;
- Event Detail shows all known messages in the conversation across runs/sources;
- deterministic, AI proposal and final decision are visually distinguishable;
- existing It38 security and idempotency guarantees remain green.

#### Checks

- `uv run pytest -q`;
- targeted AI eligibility and merge tests;
- all 8 reviewed BeeAgent integration regressions;
- provider timeout/error/invalid-output regressions;
- missing/unknown `ai_reason_code` regressions;
- RFC A -> B -> C thread regression;
- cross-mailbox exact-reference regression;
- two independent threads from the same sender regression;
- Bitrix outbound correlation controlled smoke;
- same conversation answered from a different employee mailbox smoke;
- weak-candidate never-authorizes-writeback regression;
- Event Detail conversation timeline tests;
- artifact/log inspection;
- secret/raw-mail leakage checks;
- SAST;
- DAST-style Bitrix/runtime checks;
- SCA only if dependencies change;
- malformed thread/reference tests.

#### DoD

- reviewed classification integration baseline is 8/8;
- AI acts as a real second verification echelon for business-impacting decisions;
- no dead operator semantic-review queue remains in the normal pipeline;
- execution uncertainty remains fail-closed;
- semantic classification and conversation membership are separate concepts;
- RFC exact thread authority remains intact;
- cross-mailbox exact continuation works;
- Bitrix outbound bridge is used only with proven exact evidence;
- no fuzzy CRM targeting is introduced;
- conversation timeline is usable from Event Detail;
- logs/artifacts remain bounded and secret-safe;
- docs/security contracts are updated where behavior changes;
- required checks are green;
- `pyproject.toml.version` is not changed.

#### Implemented (v2, Issue #206)

- deterministic classifier remains the first semantic echelon; AI adjudicator extended to business-impacting deterministic `new_lead` / `existing_deal` (high confidence no longer exempt); confirmed duplicate (`case_type=duplicate`) protected from AI reclassification; AI = the actual second semantic echelon: eligibility minimal — possible duplicate → eligible, confirmed duplicate (`case_type=duplicate`) → skip, all other semantic events AI-eligible; transport labels (SPAM/FWD/RE, including `spam_label_present`) - weak transport evidence and never gate semantic verifier (mail-server spam label does not allow the wrong deterministic irrelevant to bypass AI); marker signals remains bounded evidence in prompt/audit but is not the second semantic classifier with veto authority after AI (valid high-confidence AI semantic decision becomes final except for structural impossible combinations); body the context in prompt is limited to config (`rop.email_preview.body_chars_max`) inside absolute `input_chars_max`;
- `ai_reason_code` is mandatory for the new valid AI decision: missing/unknown reason code - validation diagnostic with deterministic result (not `legacy`); historical artifacts without `ai_reason_code` remain backward-compatible readable; class/evidence-aware merge policy instead of confidence-only: valid + high confidence + no conflict → AI applied; conflict / unresolved (`manual_review` queue) / invalid / low confidence / provider failure → deterministic result preserved with explicit diagnostics; `manual_review` is not normal terminal semantic queue; provider timeout/error/ invalid output retains deterministic classification + diagnostics;
- unsafe/ambiguous CRM target remains `deferred` and fail-closed; weak sender/subject/time evidence never authorizes `attach_existing`;
- BeeAgent-owned conversation relation separate from domain `case_type`: `rop_conversation.json` (per-run conversations, roles root/reply/continuation, exact RFC authority, same `client_id` across sources); exact continuation through `source_id` operates within one `client_id`; The two independents of one sender remain separate; semantic `case_type` is not removed from conversation/CRM membership;
- controlled read-only Bitrix outbound-correlation evidence check (`bitrix_outbound_correlation.json`): exact stable outbound identifier (email Message-ID from outbound activity) + subsequent inbound RFC ancestry → exact conversation bridge; bridge authorises `attach_existing` (`target_provenance=bitrix_outbound_exact`) only when canonical CRM entity identity (entity type/type-id/entity-id) coincides with canonical trusted CRM target of write-back state (provenances `beeagent_created`/`thread_resolved`); outbound activity `RESPONSIBLE_ID` – diagnostic evidence, not part of trusted identity and cannot replace trusted responsible; without exact identifier, without RFC ancestry coincidence or trusted-target coincidence candidate-only/deferred (`outbound_candidate_untrusted`) without mutation authority; The tested `bitrix_outbound_exact` becomes trusted thread root for the following RFC hop; The actual Bitrix Message-ID is read from `SETTINGS.MESSAGE_HEADERS.<Message-Id>` (case-insensitive header name) and legacy locations (`SETTINGS.MESSAGE_ID`, `SETTINGS.EMAIL_MESSAGE_ID`, top-level `MESSAGE_ID`); outbound evidence collection bounded/paginated: `crm.activity.list` paginates via cursor `next` within `bitrix.pages_max`, same Message-ID conflict is found throughout bounded result set (including cross-page), malformed top-level response / malformed cursor / malformed result → fail-closed (`BitrixMalformedResponse`, without bridge, without mutation), `call()` requires object top-level JSON (list/null/string → `BitrixMalformedResponse`), read-only method allowlist does not contain mutation methods;
- Event Detail: `deterministic` section (deterministic case_type/queue/action/confidence/ reason), `conversation` section (cross-run/cross-source timeline of all known conversation messages with write-back CRM outcome), selected AI proposal (`ai_adjudicator`) and final semantic result (`final_decision`); deterministic/AI/final/conversation is visible;
- It38 exact `Message-ID`/`In-Reply-To`/bounded `References` authority and trusted-target/idempotency guarantees are maintained.

#### Verification (Issue #206)

- reviewed classification integration gate: 8/8 reviewed scenarios reaches the expected final semantic type (`run-9cd9d1ae99e9`, `run-844530c057e6`, `run-ce974a9b8582` → `irrelevant`; `run-41d2bcf42389`, `run-d96b18d8fc70` → `new_lead`; `run-a7c20bc709ba`, `run-0036f2c6d9ee`, `run-8bf12d19f51e` → `irrelevant`);
- targeted AI eligibility, validation/reason-code, class/evidence-aware merge, provider failure, strong-noise skip, confirmed-duplicate skip, possible-duplicate unresolved base-preserved, low-confidence conflict, RFC A→B→C, cross-source exact reply, two independent threads same sender, subject-similarity never-authorizes, conflicting/malformed RFC, outbound exact bridge, candidate-only fail-closed, untrusted outbound candidate → deferred/zero mutation, trusted-entity outbound bridge → attach (activity responsible mismatch diagnostic only), numeric-string Bitrix IDs/DIRECTION, DIRECTION inbound/missing/malformed rejected, duplicate outbound Message-ID conflict → no bridge, stale bridge without current RFC ancestry → no bridge, proven bridge next-hop C continuation, conversation timeline, Event Detail deterministic/AI/final/conversation distinction;
- correction run (final review blockers): trusted-canonical-entity authority for `bitrix_outbound_exact` (authorize `attach_existing` when canonical CRM entity identity entity type/type-id/entity-id matches trusted CRM target from write-back state; outbound activity responsible - diagnostic only and cannot replace trusted responsible; other than `outbound_candidate_untrusted` deferred/zero mutation); strictly fail-closed outbound proof (`DIRECTION=2` required, numeric strings accepted, Message-ID presence is not proof of direction, same-Message-ID conflict → no bridge); restored bridge re-validated v. current RFC ancestry; proven `bitrix_outbound_exact` becomes trusted thread root for the following RFC hop; bounded AI context from canonical attachment extraction evidence only (nested `attachments[].text_preview` is not authority); `input_chars_max` is the absolute boundary (other than degraded `prompt_budget_exceeded` without provider call); `manual_review` is removed from the schema for new AI- decisions and normalized in final routing as `unresolved`/`no_action`/attention (`semantic_unresolved_no_operator_queue`); exact RFC trusted-target ambiguity uses the complete trusted identity (entity_type/type-id/entity-id/responsible); confirmed: format-only churn is missing in diff against main (no except-syntax churn and reflows; All hunks Issue-required);
- final-review echelon hardening (Pass 6): AI = the real second semantic echelon - eligibility is simplified (possible-duplicate → eligible; confirmed duplicate → skip; All other semantic events eligible), marker-veto is removed from `_ai_output_conflicts_with_marker_signals` (only structurally impossible combinations of veto), body context budget from `rop.email_preview.body_chars_max` inside absolute `input_chars_max`; Bitrix outbound correlation hardened: top-level non-object JSON → `BitrixMalformedResponse`, bounded pagination (`bitrix.pages_max`) with cross-page same-Message-ID ambiguity, malformed cursor/result → fail-closed without bridge;
- final-review AI-echelon correction (Pass 7): structured spam-label gate - `_is_strong_explicit_irrelevant` removed completely; `_is_event_eligible_for_adjudicator` is minimal (possible duplicate → eligible; Other than `case_type != "duplicate"`); SPAM/FWD/RE labels transport (including `spam_label_present`) is weak transport evidence and never bypass AI semantic verifier;
- new regression coverage (Pass 6+7): late-RFQ (beyond the first 500 characters) deterministic high-confidence ignore remains AI-eligible and valid high-confidence AI `new_lead` may become final, including at `spam_label_present=true`; valid high-confidence AI semantic correction is not vetoed generic marker lists; configured `body_chars_max` honored (content >1600 characters reach AI with sufficient `input_chars_max`); reviewed buyer-RFQ gate and spam-labelled RFQ gate exercise the second semantic echelon (valid AI decision → `final_decision_source=ai_adjudicator`); confirmed duplicate skip (eligibility + provider-skip); Bitrix pagination: exact Message-ID on page 2, cross-page conflict → no bridge, malformed `next`/result → fail-closed, `pages_max` respected, top-level list/null/string → `BitrixMalformedResponse`;
- CRM-identity/write-back boundary correction (Pass 8): non-authoritative Bitrix identity/candidate evidence (`safe_to_use_as_target=false`: `weak_match`, `ambiguous`, `duplicate_candidate`, `matched_*`) cannot veto independent final `new_lead`; `_decide_delivery` uses normal configured create path for CREATE_CASE_TYPES (`new_lead`, `irrelevant`) for candidate-only CRM evidence without trusted exact RFC target; `bitrix_match_status=duplicate_candidate` remains CRM reconciliation evidence, not semantic `case_type=duplicate`; exact trusted RFC/outbound target continues to authorise `attach_existing` (first priority), conflicting exact RFC targets / unresolved responsible / connector errors / malformed prerequisites - fail-closed; semantic `existing_deal` / `duplicate` without trusted target - non-creating/deferred; replay/origin idempotency and `pending_thread_root` retained; action-draft projection (`_map_action_v0`) for final `new_lead` + candidate evidence shows independent `create_lead` (reason `new_lead_crm_duplicate_candidate`/`new_lead_crm_weak_match`/`new_lead_crm_ambiguous`) not "resolve_duplicate_candidate"; Event Detail/read-model shows semantic final, conversation, Bitrix evidence and delivery outcome separately;
- new regression coverage (Pass 8): new_lead + `ambiguous`/`weak_match`/`duplicate_candidate` → `create_lead` (without attach, without choosing candidate, c the real `crm.item.add` at execute); new_lead + existing Bitrix `matched_lead` ()`safe_to_use_as_target=false`) → `create_lead` (never attach); existing_deal + `duplicate_candidate` → deferred `duplicate_target`; semantic `duplicate` + `duplicate_candidate` → deferred (never create); action-draft queue/reason for new_lead - candidate evidence → `create_lead`; Event Detail final `new_lead` and Bitrix `duplicate_candidate` – separate fields;
- live Bitrix outbound-correlation regression fix: is the real outbound Message-ID of `SETTINGS.MESSAGE_HEADERS.<Message-Id>` (case-insensitive header name; legacy `SETTINGS.MESSAGE_ID` / `SETTINGS.EMAIL_MESSAGE_ID` / top-level `MESSAGE_ID` retained); outbound bridge authorization — canonical CRM entity identity (entity type/type-id/entity-id); outbound activity `RESPONSIBLE_ID` - diagnostic only (the staff member who sent the email may differ from responsible itself Lead) and cannot replace trusted responsible; exact bridge → `attach_existing` with `target_provenance=bitrix_outbound_exact` and canonical trusted responsible; trusted responsible ambiguity / OWNER mismatch / cross-client / untrusted OWNER / wrong direction / no RFC ancestry — fail-closed;
- `uv run pytest -q` → 1674 passed (exit 0); runtime smoke through ROP batch entrypoint (json_batch) creates `rop_conversation.json` + `rop_final_decisions.json`; logs bounded and secret-safe (no `OPENAI_API_KEY`/raw body in log); controlled live Bitrix outbound-correlation smoke Not implemented (no reconfigured test portal/webhuk in the current environment); positive/negative equivalent scenarios are covered by mock-level integration tests (pagination/bridge/authority, deferred/zero mutation);
- `pyproject.toml.version` is unchanged; dependencies/`uv.lock` has not been changed; `beeagent-rop` did not change (public contract consumption only).

### Iteration 40 — Secure ROP attachment lifecycle and AI-assisted document understanding v1

**Status:** DONE

#### Goal

Add production-safe end-to-end lifecycle for email attachments in ROP: BeeAgent. It must preserve accepted MIME- attachments as opaque untrusted files until mailbox checkpoint, allow an authorized operator to download the original file safely from Event Detail, deliver physical attachments with the corresponding email activity to Bitrix and, when config policy is enabled, obtain bounded semantic context from supported documents through configured AI provider to improve the existing ROP classification.

Attachment retention/delivery and attachment semantic analysis must be independent of: AI/content analysis deactivation must not remove an attachment, hide download or prohibit Bitrix delivery.

AI document understanding is not malware scanner, sandbox or execution authority.

#### Scope

**Includes:**

- Implement changes to `beeagent`;
- Save `beeagent-rop` public attachment/classification contract unchanged;
- Save BeeUI generic presentation contract without product-specific changes;
- Broaden mailbox ingestion so that accepted MIME attachment bytes does not lose after normalization;
- Keep raw attachment bytes only in dedicated bounded opaque attachment store, separate from normal JSON artifacts;
- Use generated attachment IDs / content hashes instead of untrusted filenames for filesystem paths;
- Save bounded attachment manifest metadata:
  - attachment_id;
  - event identity;
  - original bounded filename;
  - declared content type;
  - size;
  - SHA-256;
  - storage status;
  - analysis status;
  - preview availability;
  - refusal/degradation reason;
- No raw attachment bytes in `normalized_events.json`, classification artifacts, write-back summaries, logs, HTML or JSON APIs;
- Save accepted attachment blobs to mailbox checkpoint advancement;
- at storage failure for attachment, which policy requires to be retained, not promoted checkpoint;
- Add config-driven storage bounds:
  - per-file size;
  - aggregate per-message attachment size;
  - attachment count;
- Save `rop.attachments.enabled` as operator-visible switch semantic attachment analysis:
  - `true` - perform bounded analysis for supported files;
  - `false` — zero attachment content analysis / zero file egress to AI provider;
- at `rop.attachments.enabled: false` continue:
  - Save accepted attachments;
  - Show metadata;
  - Allow authenticated download;
  - Transfer files to Bitrix when write-back/file delivery policy permits;
- Save existing `rop.attachments.chars_max`, `size_max` and `types` as bounded analysis policy or migrate with explicit backward-compatible validation if implementation requires clearer naming;
- Support common business formats for semantic analysis where the configured provider capability is explicitly supported and verified, including target coverage for:
  - `text/plain`;
  - `text/csv`;
  - PDF;
  - DOCX;
  - DOC where provider support exists;
  - JPEG;
  - PNG;
- unsupported provider/file combinations must remain stored/downloadable/deliverable with explicit `analysis_status`, without local unsafe fallback parser;
- do not add local PDF/DOC/DOCX/image deep parser to BeeAgent main process to v1;
- Transfer attachment bytes to the outer AI provider only through explicit configured/validated file-capable provider path;
- Consider attachment contents untrusted data and never treat instructions inside a document as agent/tool instructions;
- AI attachment result must be bounded, schema-validated and converted to existing attachment extraction evidence (`attachment_text_preview`, status/refusal fields);
- The existing `beeagent-rop` attachment-aware classification must consume this context without filesystem/provider access;
- existing BeeAgent AI adjudicator may use resulting bounded attachment context through the current semantic decision path;
- provider/analysis failure must not remove a file or block deterministic classification; failure must be explicit degraded evidence;
- Add BeeAgent-owned authenticated download route for event attachments;
- download must be permitted only through safe manifest lookup, without arbitrary path access;
- download must use forced attachment response and anti-sniff/no-store security headers;
- Event Detail must display attachment metadata, analysis status and safe internal download link;
- product-specific attachment route/read-model must remain on BeeAgent side; BeeUI only renders normalized data;
- Save current `bitrix.writeback.email_attach` semantics as email-activity binding;
- Add a separate config policy for physical file attachment delivery to Bitrix;
- The physical attachments must be delivered to the same trusted/new Lead/Deal email activity without weakening existing It37-39 CRM target authority;
- file delivery state/idempotency must be kept separately from current email-activity attachment status;
- replay of one email must not create duplicate Lead, duplicate email activity or uncontrolled duplicate file delivery;
- Bitrix physical-file REST contract must be confirmed by controlled test-portal smoke before production enablement;
- if physical-file binding requires additional Bitrix mutation method, expand write allowlist only exact required method;
- Update config validation, artifacts, docs and tests;
- reconcile `docs/product/ui_roadmap.md` UI-10 with the new BeeAgent-owned secure download contract;
- Do not change `pyproject.toml.version`.

#### Excluded

- Consider AI malware/antivirus scanner;
- claim that an AI-read file is safe to execute/open;
- executing attachment content;
- macros/scripts execution;
- local office application invocation;
- arbitrary shell/converter execution;
- broad local PDF/DOC/DOCX parsing stack in v1;
- browser inline PDF/Office/image viewer;
- arbitrary filesystem download route;
- using original filename as storage path;
- unbounded attachment storage;
- unbounded provider upload;
- attachment bytes in JSON artifacts/logs/API payloads;
- raw `.eml` / `message/rfc822` nested attachment processing in v1;
- OCR/local computer-vision pipeline separate from configured provider support;
- new classification rules in BeeAgent;
- changes to `beeagent-rop`;
- product-specific changes in `beeui`;
- weakening It37–39 trusted CRM target, responsible, thread, retry or idempotency boundaries;
- broad Bitrix write-method access;
- malware sandbox / antivirus verdict;
- attachment retention/admin management UI;
- automatic deletion/pruning policy unless an existing storage lifecycle requires it;
- version bump.

#### Deliverable

ROP receives end-to-end attachment lifecycle:

```text
mailbox MIME
→ bounded opaque BeeAgent attachment storage
→ safe manifest
→ optional AI semantic analysis
→ existing attachment-aware classification
→ authenticated ROP download
→ idempotent physical Bitrix attachment delivery
```

The operator can open Event Detail and download the source accepted attachment. in Bitrix the corresponding Lead/Deal email activity contains the physical attachments. With analysis BeeAgent on it receives bounded document context and uses existing ROP classification path; When analysis is off, the files continue to be stored, downloaded and delivered to Bitrix without provider file calls.

#### Acceptance criteria

- live-like mailbox PDF attachment bytes survive mailbox normalization and are persisted as an opaque blob;
- DOCX, DOC, TXT, JPEG and PNG attachments within configured retention policy are preserved as opaque files regardless of AI analysis support;
- attachment original filename is metadata only and never controls filesystem location;
- SHA-256 and stable generated attachment identity are recorded;
- `normalized_events.json` and other normal JSON artifacts contain no raw attachment bytes;
- accepted attachment storage is durable before mailbox checkpoint advancement;
- required attachment persistence failure prevents checkpoint advancement;
- configured file/count/aggregate limits are enforced before unbounded storage allocation;
- oversized/refused/blocked files produce explicit bounded metadata status;
- `rop.attachments.enabled: false` results in zero attachment content analysis/provider file calls while preserved files remain downloadable and eligible for Bitrix delivery;
- `rop.attachments.enabled: true` analyzes only explicitly supported configured file types/sizes;
- supported provider analysis produces bounded validated attachment context through the existing attachment extraction contract;
- unsupported provider/file type degrades explicitly and never triggers an unsafe local parser fallback;
- AI/document text cannot grant tool, mailbox or CRM execution authority;
- attachment provider failure preserves deterministic processing and explicit diagnostics;
- existing `beeagent-rop` package requires no implementation change;
- Event Detail displays attachment filename, type, size, storage status, analysis status and download action;
- download requires existing BeeAgent authentication/authorization;
- invalid run/event/attachment IDs fail closed;
- path traversal and arbitrary filesystem paths cannot retrieve files;
- download uses forced attachment semantics, no inline rendering, no MIME sniffing and no public caching;
- a ROP-scoped principal cannot use the attachment route to read unrelated module/run files;
- physical file delivery to Bitrix uses the same trusted/new target selected by existing write-back authority;
- physical attachment delivery never creates a new CRM target by itself;
- current `bitrix.writeback.email_attach` behavior remains backward-compatible for email activity creation;
- physical file delivery has an explicit separate config switch/status;
- replay does not create duplicate Lead/email activity and does not cause uncontrolled duplicate file delivery;
- Bitrix temporary failure can be retried from durable local attachment storage without mailbox re-ingestion;
- exact physical Bitrix file-binding behavior is verified on a controlled test portal before production enablement;
- no credential, webhook URL, raw `.eml` or attachment bytes appear in logs/HTML/JSON APIs;
- `beeui` requires no product-specific implementation;
- `pyproject.toml.version` is unchanged.

#### Checks

- `uv run pytest -q`;
- targeted `tests/test_rop_input_source.py`;
- targeted settings/config validation tests;
- targeted attachment extraction/storage tests;
- targeted mailbox poll/checkpoint tests;
- targeted ROP operator/classification integration tests;
- targeted `tests/test_rop_writeback.py`;
- targeted BeeAgent Web/Event Detail/auth/scope tests;
- MIME fixtures for TXT/PDF/DOCX/DOC/JPEG/PNG;
- malformed filename/path traversal fixtures;
- oversized file, aggregate size and files-count boundary tests;
- same filename/different content and different filename/same content scenarios;
- truncated/malformed MIME scenario;
- disabled-analysis zero-provider-call regression;
- provider unsupported/timeout/error/invalid-result regressions;
- attachment prompt-injection style fixture proving document instructions do not grant execution authority;
- download unauthenticated/forbidden/not-found/path-traversal checks;
- response header check for forced download / nosniff / no-store;
- mailbox checkpoint does not advance after required attachment storage failure;
- replay/idempotency regressions;
- controlled live-like mailbox smoke with synthetic business attachments;
- controlled Bitrix test-portal smoke proving the physical attachment can be opened/downloaded from the resulting Lead/Deal activity;
- controlled AI provider file-input smoke for each format claimed as supported by the configured production profile;
- logs/artifact inspection;
- `uv run python -B -m compileall -q src tests`;
- `git diff --check`;
- SAST required;
- DAST-style attachment download and Bitrix connector checks required;
- SCA required only if dependency files change;
- malformed/adversarial MIME, filename and path fuzz-style tests required;
- IAST not required.

#### DoD

- mailbox attachment bytes are no longer lost after ingestion;
- accepted attachments are durably stored before checkpoint advancement;
- attachment retention/delivery is independent from AI analysis;
- operator can safely download an accepted original attachment from ROP Event Detail;
- physical attachments are available from the correct Bitrix Lead/Deal email activity;
- attachment delivery preserves existing trusted-target/idempotency boundaries;
- AI can enrich classification from supported documents without becoming malware or execution authority;
- unsupported or failed analysis degrades safely;
- no arbitrary local deep parser stack is introduced;
- no arbitrary file-serving route exists;
- raw attachment bytes remain outside normal artifacts/logs/HTML/JSON APIs;
- `beeagent-rop` and `beeui` require no implementation changes;
- config and security contracts are explicit and validated;
- tests, controlled provider/Bitrix smoke, security checks and docs are ready for PR review;
- `pyproject.toml.version` is unchanged.

#### Verification (Issue #209)

- mailbox normalization now saves accepted MIME attachment bytes under private key `_raw_attachments` (to `normalized_events.json`); bytes does not enter normal JSON artifacts/logs/HTML/API;
- dedicated bounded opaque attachment store: `storage/attachments/<run_id>/<blob_id>.bin` + `attachment_manifest.json` (generated `att-<sha256[:24]>` blob ids, filename only metadata, SHA-256 + exact size in manifest, no raw bytes); required persistence failure raises `AttachmentStoreError` → batch degraded → mailbox checkpoint is not moving;
- config-driven storage bounds: `rop.attachments.storage.{enabled,file_max,message_max,files_message_max}` (validated fail-fast; count and bounded encoded-size preflight apply before decoded payload retention, then exact file/aggregate limits apply immediately after decode); oversized/count/aggregate/blocked (`.eml`/`message/rfc822`) — explicit manifest `storage_status`;
- `rop.attachments.enabled:false` → zero provider calls (analysis artifact `analysis_status=disabled`), retention/download/Bitrix delivery is independent and continues to operate;
- bounded AI document understanding: `rop.attachments.analysis.{provider,file_capable,chars_max}`; PDF/DOCX use the provider file-upload reference contract (file uploaded via the provider Files API, then `input_file` referenced by `file_id`, temporary file deleted after the response) and JPEG/PNG use `input_image` data URLs; binary analysis enabled (`file_capable:true`) only after controlled provider smokes prove the configured profile for PDF/DOCX/JPEG/PNG; unsupported type/size/provider/file-input → explicit `analysis_status=unsupported`, no local parser fallback; provider failure/timeout/invalid output → `failed` + deterministic path preserved; output schema-validated and bounded; document instructions does not give tool/mailbox/CRM authority;
- AI preview integrated into existing attachment extraction contract: `attachment_text_preview` / `attachment_preview_available` / status/refusal fields (for `beeagent-rop` unchanged by package);
- authenticated download route `GET /rop/attachments/{attachment_id}/download?run_id=...&event_id=...`: The existing BeeUI session auth + authorization scopes, lookup only for safe manifest attachment ID, invalid/traversal/unrelated → fail closed, forced `attachment` + `X-Content-Type-Options: nosniff` + `Cache-Control: no-store`, `application/octet-stream` (no inline render);
- Event Detail shows filename/content_type/size/storage_status/analysis_status/sha256/safe download link; attachment manifest and analysis are added to evidence artifacts and allowlists;
- Bitrix physical file delivery: a separate disabled-by-default switch `bitrix.writeback.file_attach` (bool, validated), separate `file_attach_status`/`file_attach_attempts`/`last_file_attach_error_code`/`attachment_refs` in write-back state; The files are read from durable attachment store to manifest refs (retry without mailbox re-ingestion); Only the already selected trusted/new CRM target (email activity) is used, the delivery does not choose target; `email_attach` backward-compatible; timeout/malformed file updates fail closed as `reconciliation_required` and replay never resends them blindly; write allowlist extended exactly to `crm.activity.update` (FILES/fileData);
- `beeagent-rop` did not change; `beeui` did not change (generic renderer, download contract BeeAgent-owned);
- local verification is recorded only after fresh targeted and full-suite commands complete for this correction run;
- controlled AI provider smoke for TXT/CSV/PDF/DOCX/JPEG/PNG is run on configured production profile: and all six formats produce successful bounded analysis and attachment-aware classification; controlled Bitrix test-portal attachment smoke remains NOT VERIFIABLE in the current environment because only production portal is available and blocker remains for full DoD;
- `pyproject.toml.version` is unchanged; dependencies/`uv.lock` unchanged.

### Iteration 41 — Canonical local document extraction and ROP Docling migration v1

**Status:** DONE

#### Goal

Record BeeAgent-owned `document.extract` contract, accept Docling as canonical local document engine and transfer the existing ROP attachment semantic path from provider-based file reading to local bounded text extraction without changing attachment storage, download, Bitrix delivery or public `beeagent-rop` classification contract.

#### Scope

- Add a stable BeeAgent `document.extract` result contract without Docling-specific types;
- Use `docling==2.122.0` as the only canonical document engine v1;
- Run untrusted document conversion through bounded local worker boundary, not directly to ROP domain module;
- Read only BeeAgent-resolved attachment blobs of existing opaque attachment store;
- Prohibit arbitrary URL/path input and the use of original filename as filesystem identity;
- Support initial allowlist: TXT, CSV, PDF, DOCX, XLSX, JPEG and PNG;
- Use local Docling OCR path for JPEG/PNG and scanned PDF;
- Transform successful extraction into existing `attachment_extraction.json` / `attachment_text_preview` contract;
- Save `attachment_extraction_status`, preview/status/refusal fields and existing public ROP module payload;
- Replace `rop.attachments.analysis` provider/file-capable config with explicit local extraction config;
- Save `rop.attachments.enabled`, storage limits, type allowlist and independent retention/download/Bitrix behavior;
- Transfer AI adjudicator only to bounded extracted text and existing semantic evidence;
- Save historical It40 artifact readability where compatibility requires it;
- Update settings validation, docs, dependency declarations and tests.

#### Excluded

- changes `beeagent-rop` classification rules or public output shape;
- Changes to BeeUI generic contracts;
- AI file upload, `input_file`, `input_image` or binary provider fallback;
- second document engine or Tika/Marker/MarkItDown fallback;
- full Secure Execution Runtime / execution-node framework;
- arbitrary shell/converter execution;
- `.eml` / `message/rfc822` nested parsing;
- legacy DOC/PPT, broad Docling format enablement, audio/video or email parsing;
- malware/antivirus verdicts;
- CRM/Bitrix authority changes;
- AI eligibility/merge redesign;
- version bump.

#### Deliverable

ROP attachment pipeline becomes:

`opaque attachment store → document.extract → Docling local text → existing attachment extraction evidence → beeagent-rop deterministic classification → bounded text-only AI adjudicator → existing Bitrix flow`.

No attachment binary is sent to the AI provider for document reading.

#### Acceptance criteria

- TXT, CSV, PDF, DOCX, XLSX, JPEG and PNG sanitized fixtures extract locally through the canonical Docling path;
- scanned PDF and image fixtures prove local OCR behavior;
- extraction result is bounded, explainable and contains engine/status/reason/text/truncation metadata;
- malformed, encrypted, unsupported or failed documents degrade explicitly without crashing ROP;
- original filenames never control filesystem paths or Docling source paths;
- `attachment_extraction.json` and public `beeagent-rop` preview/status/refusal fields remain backward-compatible;
- reviewed RFQ, supplier, finance and existing-deal attachment scenarios keep expected classifications;
- `rop.attachments.enabled:false` performs zero document parsing while storage/download/Bitrix delivery continue;
- new runtime makes zero provider file-upload/image-input calls for attachment reading;
- AI adjudicator receives only bounded extracted text, never raw binary/base64/provider file references;
- document content cannot create tool/mailbox/CRM authority;
- existing attachment download and Bitrix file delivery/idempotency regressions remain green;
- runtime extraction is offline-capable after required local Docling assets are prepared;
- `beeagent-rop` and `beeui` require no implementation change;
- `pyproject.toml.version` is unchanged.

#### Checks

- `uv run pytest -q`;
- targeted document extraction contract and Docling adapter tests;
- real local sanitized TXT/CSV/PDF/DOCX/XLSX/JPEG/PNG extraction fixtures;
- scanned PDF/image OCR smoke;
- malformed/corrupt/unsupported/refused/oversized document tests;
- ROP attachment extraction and attachment-aware classification regressions;
- AI adjudicator request tests proving text-only attachment evidence;
- regression proving no provider Files API / `input_file` / `input_image` attachment path;
- mailbox checkpoint/storage/download regressions;
- Bitrix physical attachment delivery/idempotency regressions;
- controlled ROP batch smoke and artifact/log inspection;
- Python 3.14 Docling installation/runtime acceptance;
- `uv run python -B -m compileall -q src tests`;
- `git diff --check`;
- SAST;
- SCA for Docling and its locked transitive dependency surface;
- bounded malformed/parser stress tests;
- DAST/IAST not required unless the implementation unexpectedly adds a new network-facing or execution boundary.

#### DoD

- BeeAgent owns a stable product-neutral document extraction contract;
- Docling is the only canonical document reader in the ROP attachment path;
- AI is no longer used to read attachment files;
- AI remains only a bounded semantic adjudication layer over text/evidence;
- existing ROP domain contract remains unchanged;
- attachment retention/download/Bitrix delivery behavior remains intact;
- parser failures do not crash orchestration or lose stored attachments;
- runtime document extraction does not require customer-file egress;
- dependency/security review is recorded;
- docs and config reflect the new source of truth;
- required tests and controlled smokes are green;
- `pyproject.toml.version` is not changed.

#### Implementation (It41)

- Added BeeAgent-owned `document.extract` contract: `DocumentExtractionResult` to `src/beeagent_module/core/document_extraction.py` (status, reason_code, engine, bounded text, text_length, is_truncated, content_type, ocr_used, page_count) without Docling- specific types.
- Docling `==2.122.0` is the only canonical document engine v1; `onnxruntime==1.29.0` is also added as ONNX inference runtime for local RapidOCR (not the second document engine).
- Untrusted documents are processed via bounded local subprocess worker (`document_extraction_worker.py`) with timeout; Docling falls/depends in isolation from ROP orchestration.
- Entrys are permitted only from BeeAgent attachment manifest/store (`resolve_attachment_blob_path`); Arbitrary URL/path and original filename as filesystem identity are prohibited - the format hint is removed only from allowlisted content type.
- Initial allowlist: TXT, CSV, PDF, DOCX, XLSX, JPEG, PNG; JPEG/PNG and scanned PDF use local Docling OCR path; OCR backend is clearly chosen as RapidOCR (`RapidOcrOptions(backend="onnxruntime")` in `docling_reader.py`) and not Docling auto-select; `onnxruntime` — inference runtime RapidOCR; cyrillic/Russian recognition uses provisioned PP-OCRv5 cyrillic rec/det/dict assets, English regression remains green on the same RapidOCR path.
- Successful extraction feeding in existing `attachment_extraction.json` / `attachment_text_preview` contract; public ROP preview/status/refusal fields retained.
- `rop.attachments.analysis` provider-confession replaced by explicit local `rop.attachments.extraction` (engine, chars_max, pages_max, timeout_seconds, ocr_enabled) with fail-fast validation.
- The total three-budget attachment text contract: `rop.attachments.chars_max=1000` is public/deterministic preview for `beeagent-rop`; `rop.ai_assist.adjudicator.attachment_chars_max=2000` – text-only attachment evidence for AI adjudicator; `rop.attachments.extraction.chars_max=3000` – maximum bounded Docling extracted text. Settings fail-fast has been validated by `0 < attachments.chars_max <= ai_assist.adjudicator.attachment_chars_max <= attachments.extraction.chars_max`.
- Provider Files API / `input_file` / `input_image` / base64 attachment path removed from runtime; AI adjudicator remains text-only.
- Local Docling model assets (layout model + RapidOCR PP-OCRv5 cyrillic rec/det/dict) is clearly prepared via `config/start.py docling-assets-prepare`; runtime works offline (`HF_HUB_OFFLINE=1`) and does not download models silently; missing assets — explicit degraded.
- `beeagent-rop` and `beeui` have not changed; `pyproject.toml.version` hasn't changed.

### Iteration 42 — Responsible-aware Bitrix lead stage routing v1

**Status:** DONE

#### Goal

Clarify the existing BeeAgent-owned Bitrix write-back policy: new Lead with the exact responsibility must be created in customer stage "Leed assigned", and Lead for which recipient routing returned `responsible.status=not_found` and applied configured fallback responsible must retain stage "New".

The change must use the already existing `matched` / `fallback` partition and must not affect classification, recipient matching, trusted CRM target authority, idempotency or BeeUI.

#### Scope

- implement only the changes in `beeagent`;
- Save `bitrix.writeback.stages.new_lead` as stage for fallback new Lead (`NEW` / "New" in the current customer config);
- add the explicit config key `bitrix.writeback.stages.new_lead_assigned` for the customer stage “Lead assigned”;
- for `case_type=new_lead` and exact active `responsible.status=matched` use:
  - Found `responsible.user_id`;
  - `stages.new_lead_assigned`;
- for `case_type=new_lead` and `responsible.status=not_found` at configured valid `user_id_fallback` use:
  - `user_id_fallback`;
  - existing `stages.new_lead`;
- Save fail-closed behavior for `ambiguous`, `connector_degraded`, `unresolved`, `not_attempted`, inactive or malformed responsible evidence;
- Save `irrelevant` stage behavior unchanged;
- Save trusted `attach_existing` behavior without stage/reassignment mutation of the existing CRM entity;
- Validate the new required stage key fail-fast at enabled write-back;
- Check configured stage using the existing `crm.status.list` validation path to mutation;
- Save existing durable write-back state, idempotency, retry/recovery and checkpoint semantics;
- Update targeted regression tests and contract documentation.

#### Excluded

- Changes to `beeagent-rop`;
- Changes to `beeui`;
- Appendix Bitrix write-back settings or CRM controls in ROP Web Console;
- change recipient attribution or responsible matching;
- change eligibility `user_id_fallback`;
- Change classification, subtype, duplicate or AI semantics;
- change `irrelevant` / JUNK behavior;
- Modification of the stage or responsible existing trusted Lead/Deal;
- `crm.item.update`, `crm.item.delete` or new Bitrix mutation methods;
- hardcoded customer stage IDs, Bitrix user IDs or display labels in Python runtime;
- New dependencies;
- version bump.

#### Deliverable

BeeAgent write-back planner deterministic stage of a new Lead based on the responsible outcome: already confirmed

```text
new_lead + matched
→ configured new_lead_assigned stage
→ matched Bitrix user

new_lead + not_found + fallback
→ configured new_lead stage
→ fallback Bitrix user
```

Existing executor continues to perform the same bounded `crm.item.add` contract with planner-provided `STAGE_ID` and `ASSIGNED_BY_ID`.

#### Acceptance criteria

- exact active matched responsible for `new_lead` creates Lead with `STAGE_ID=bitrix.writeback.stages.new_lead_assigned`;
- matched Lead receives exact matched `ASSIGNED_BY_ID`;
- `responsible.status=not_found` with valid `user_id_fallback` creates Lead with `STAGE_ID=bitrix.writeback.stages.new_lead`;
- fallback Lead receives configured fallback `ASSIGNED_BY_ID`;
- fallback never overriding exact matched responsible;
- ambiguous, degraded, unresolved and not-attempted responsible evidence remain `deferred` without create;
- `irrelevant` retains existing configured stage behavior;
- trusted existing Lead/Deal attachment does not cause a new Lead create, stage change or responsible reassignment;
- missing/empty `new_lead_assigned` at enabled write-back rejected fail-fast;
- unknown stage config keys remains rejected;
- invalid configured assigned stage leads to zero mutation;
- stage validation outage retains existing recoverable fail-closed behavior;
- replay/repeated execute does not create duplicate Lead and does not repeat stage/responsible mutation;
- a new Bitrix write method is not added;
- public `beeagent-rop` contract does not change;
- BeeUI contract does not change;
- actual customer Bitrix STATUS_ID for "Lide assigned" confirmed to production enablement;
- configured fallback user ID is confirmed as active customer user `ROBOT WG` to production enablement;
- `pyproject.toml.version` remains unchanged.

#### Checks

- `uv run pytest -q tests/test_rop_writeback.py`;
- `uv run pytest -q`;
- `uv run python -B -m compileall -q src tests`;
- `git diff --check`;
- targeted planner tests: matched stage, fallback stage, unresolved/degraded responsible, irrelevant stage, trusted attach-existing;
- targeted executor tests: exact `STAGE_ID` + `ASSIGNED_BY_ID` combinations;
- settings validation tests for `new_lead_assigned`;
- invalid assigned-stage regression proving zero mutation;
- replay/idempotency regression;
- read-only Bitrix verification of the exact customer STATUS_ID for "Lide assigned";
- read-only Bitrix verification that configured `user_id_fallback` is the intended active `ROBOT WG` user;
- controlled Bitrix smoke with one matched new Lead and one fallback new Lead before production enablement;
- log and write-back artifact inspection;
- SAST;
- DAST-style external connector behavior/error review;
- SCA only if dependency files unexpectedly change;
- IAST not required;
- fuzzing not required because no parser or new serialization surface is introduced.

#### DoD

- matched and fallback new Leads reach different configured customer stages according to the approved rule;
- existing responsible routing remains the only source of responsible outcome;
- fallback remains limited to `not_found`;
- all other unresolved responsible states remain fail closed;
- existing trusted-target, idempotency, retry and durable-intent guarantees remain intact;
- existing CRM entities are not restaged or reassigned;
- configuration is explicit and fail-fast validated;
- actual customer stage/user identifiers are verified rather than guessed;
- no `beeagent-rop` or BeeUI implementation change is required;
- docs and tests reflect the actual contract;
- required security/runtime checks are green;
- `pyproject.toml.version` is unchanged.

#### Implementation (It42)

- Added explicit config key `bitrix.writeback.stages.new_lead_assigned` (customer stage "Lide appointed"); value confirmed read-only Bitrix verification: STATUS_ID `2` = "Lide assigned", `user_id_fallback=167` = active ROBOT WG (system@welding.kz), without guessing display labels.
- `_create_lead_delivery` planner in `src/beeagent_module/cases/rop_writeback.py` now chooses stage key deterministic from responsible outcome: already confirmed `new_lead + matched` → `stages.new_lead_assigned` + exact matched `user_id`; `new_lead + not_found` + valid `user_id_fallback` → existing `stages.new_lead` + fallback user; `irrelevant` → existing `stages.irrelevant`. KISS: direct responsible-aware sample stage key, without generic stage-routing framework.
- Fail-closed behavior retained: `ambiguous`/`connector_degraded`/`unresolved`/`not_attempted`, inactive or malformed responsible evidence remain `deferred` (`responsible_unresolved`) without create; fallback never override exact matched responsible; trusted `attach_existing` does not create Lead or restage/reassign of the existing CRM entity.
- Executor never changed: Continues to perform the same bounded `crm.item.add` (`entityTypeId=1`) with planner-provided `STAGE_ID`/`ASSIGNED_BY_ID`; mutation allowlist has not expanded.
- Settings fail-fast validation (`src/beeagent_module/core/settings.py`) now permits `new_lead_assigned` as the famous stage key and demands the empty `new_lead_assigned` at `bitrix.writeback.enabled=true`; unknown stage keys remains rejected.
- Stage pre-validation through the existing `crm.status.list` (`_validate_stages_against_bitrix`) now covers `new_lead_assigned`; invalid assigned stage → zero mutation; stage-validation outage retains recoverable fail-closed `pending` behavior.
- Durable state, retry/recovery, checkpoint and idempotency semantics are maintained unchanged.
- Added focused regressions: settings validation for `new_lead_assigned` (missing/empty at enabled), planner matched/fallback/unresolved/degraded/irrelevant/trusted-attach stage selection, executor exact `STAGE_ID`+`ASSIGNED_BY_ID` for matched and fallback, invalid assigned stage → zero writes, replay/idempotency.
- `beeagent-rop` and `beeui` have not changed; No new dependencies; `pyproject.toml.version` hasn't changed.

### Iteration 43 — Bounded isolated Solana capability for BeeDrill

**Status:** DONE

#### Goal

Add a minimum BeeAgent-owned execution path for the second real domain module - BeeDrill - so that the module can request one bounded isolated Solana lifecycle via host-provided capability boundary without direct process/RPC authority.

#### Scope

Includes:

- consumption approved BeeSDK `ModuleContext` capability injection contract;
- BeeAgent-owned scoped `CapabilityCaller`;
- host binding:
  - `module_id`;
  - `run_id`;
  - `session_id`;
  - `case_type`;
  - authority;

- explicit module/case/capability policy;
- one capability:

```text
solana.isolated_lifecycle
```

- 1 approved isolated target profile:

```text
surfpool_local
```

- Surfpool startup;
- machine-verifiable readiness;
- One fixed host-selected read-only Solana RPC smoke;
- bounded timeout;
- shutdown;
- forced cleanup when required;
- process reaping;
- bounded `ok/refused/timeout/error` result;
- real BeeDrill/BeeAgent/Surfpool integration smoke.

#### Excluded

- arbitrary subprocess capability;
- module-controlled executable/path/argv;
- module-controlled RPC endpoint or method;
- generic Solana provider abstraction;
- generic sandbox/execution framework;
- mainnet or production mutation;
- production private keys;
- BeeDrill domain logic;
- attack/detector/containment behavior from later BeeDrill iterations.

#### Deliverable

One real host-owned lifecycle:

```text
BeeDrill bounded request
→ BeeAgent scoped CapabilityCaller
→ solana.isolated_lifecycle
→ Surfpool start
→ ready
→ bounded RPC
→ stop
→ clean
→ bounded CapabilityResult
```

#### Acceptance criteria

- capability caller is injected by BeeAgent;
- module cannot override host identity or authority;
- only approved module/case/capability combinations are allowed;
- forbidden targets and unexpected execution-shaped fields are refused;
- no mainnet fallback exists;
- Surfpool starts reproducibly;
- startup/readiness/RPC failures are explicit;
- readiness and runtime are bounded by timeout;
- shutdown and forced cleanup are bounded;
- no tested success/failure path leaves an orphan managed process;
- no production key is required;
- BeeDrill remains `READ_ONLY`;
- capability result does not grant new module authority;
- no generic execution framework is introduced.

#### Checks

```text
targeted capability/runtime tests
full pytest
allowed capability
unknown capability
wrong module/case refusal
forbidden target refusal
untrusted payload refusal
startup failure
early process exit
readiness failure
timeout
RPC failure
successful real lifecycle
shutdown failure
forced cleanup
no orphan process
BeeDrill/BeeAgent integration smoke
log/artifact inspection
SAST
SCA if dependency surface changes
```

#### DoD

BeeAgent provides BeeDrill with one real bounded isolated Solana execution capability while retaining complete ownership of process lifecycle, RPC target selection, policy, authority, timeout and cleanup.

### Iteration 44 — Bounded BeeDrill reference-target baseline capability

**Status:** DONE

#### Goal

Extend the existing BeeDrill isolated-Solana host boundary with the smallest bounded capability required to prepare, inspect and reproduce the BeeDrill reference target for BeeDrill Iteration 5.

#### Scope

Included:

- reuse of the existing BeeDrill-scoped host `CapabilityCaller`;
- one additional bounded capability: `solana.reference_target_baseline`;
- explicit scope to the BeeDrill reference-target baseline case;
- fixed `surfpool_local` execution target;
- fixed allowlisted BeeDrill reference target identity;
- host-side resolution of the approved BeeDrill target resource;
- isolated Surfpool startup/readiness;
- bounded target preparation/deployment and initialization;
- bounded state/control observation;
- canonical reset or fresh-state reproduction;
- bounded timeout and failure evidence;
- shutdown, forced cleanup and process reaping;
- real BeeDrill/BeeAgent/reference-target integration smoke.

#### Excluded

- arbitrary program or filesystem path supplied by the module;
- arbitrary executable or argv;
- arbitrary RPC endpoint or method;
- generic transaction submission API;
- generic Solana provider/framework;
- Iteration 6 attack semantics or gross-loss evidence;
- detector verdicts;
- containment verdicts or production response;
- mainnet/production mutation;
- production private keys;
- BeeSDK contract changes.

#### Deliverable

One host-owned path:

```text
BeeDrill bounded baseline request
→ BeeAgent policy
→ local Surfpool
→ fixed reference target preparation
→ bounded state evidence
→ reset/reproduction
→ cleanup
→ CapabilityResult
```

#### Acceptance criteria

- only the approved BeeDrill module/case/capability combination is accepted;
- target profile and target identity are fixed/allowlisted;
- module input cannot supply executable, argv, program path, RPC target/method or credentials;
- target resource resolution is host-owned;
- preparation/init failures are explicit;
- bounded baseline state evidence is returned;
- repeated fresh runs produce equivalent relevant target state;
- timeout and cleanup remain bounded;
- no tested path leaves an orphan managed process;
- no mainnet fallback exists;
- BeeDrill remains `READ_ONLY`;
- capability evidence does not grant module authority;
- existing `beeagent-rop` behavior remains compatible;
- existing `solana.isolated_lifecycle` behavior remains compatible.

#### Checks

```text
targeted capability/runtime tests
full pytest
approved module/case/capability
wrong module/case/capability refusal
forbidden target refusal
execution-shaped payload refusal
target-resource resolution failure
target preparation/init failure
state-observation failure
reset/reproduction
timeout
cleanup
no orphan process
real BeeDrill/reference-target smoke
beeagent-rop module integration regression
log/artifact inspection
SAST
SCA only if dependency surface changes
git diff --check
```

#### DoD

BeeAgent can safely prepare and reproduce the BeeDrill reference target inside the fixed isolated Solana environment while retaining complete ownership of runtime execution, RPC, target resolution, authority, timeout and cleanup.

### Iteration 44.1 — Bounded BeeDrill reference-target attack capability

**Status:** DONE

#### Goal

Add the minimum host-owned path required by BeeDrill Iteration 6 to carry out one fixed economic attack on `reference_vault` in isolation Surfpool and to obtain the verified attack evidence.

#### Scope

- One new BeeDrill-scoped case/capability pair for a fixed attack;
- reuse existing scoped `CapabilityCaller`, offline Surfpool lifecycle, target-resource resolution, timeout and cleanup;
- only `surfpool_local` and `reference_vault`;
- host-owned preparation, deployment, canonical initialization, attack transaction and state observation;
- bounded evidence: fixed identities, transaction signature(s), slot/timing reference, balances/state before and after, gross loss in integer lamports;
- explicit `ok/refused/timeout/error` outcomes;
- negative policy, timeout, cleanup and evidence tests;
- cross-repository integration smoke after access to BeeDrill consumer.

#### Excluded

- generic transaction submission API;
- arbitrary program/executable/path/argv;
- module-controlled RPC target, method, raw transaction or credentials;
- mainnet/production mutation;
- detector, containment, metrics or verdict behavior;
- BeeSDK contract/dependency changes;
- new Solana framework.

#### Deliverable

One bounded capability performing only allowlisted reference-vault attack and returning machine-verifiable attack/economic evidence without execution authority BeeDrill. transmission

#### Acceptance criteria

- capability permitted for exact BeeDrill module/case/authority/payload scope only;
- The attack changes the state of the isolated reference target;
- evidence contains the proven state transition and gross loss;
- the repeated fresh run retains the equivalent security outcome;
- malformed/forbidden intent failed to host execution;
- failure, timeout and cleanup outcomes are visible;
- no mainnet fallback, secrets or orphan processes;
- The existing lifecycle and baseline capabilities remain compatible.

#### Checks

- targeted isolated-Solana capability tests;
- full `pytest -q`;
- allowed and forbidden scope/payload tests;
- attack success, transaction/state evidence, economic-delta and replay tests;
- preparation, transaction, observation, timeout and cleanup failure tests;
- real isolated integration smoke;
- log/artifact inspection;
- SAST; SCA only when dependency surface. is changed

#### DoD

BeeAgent is safe to perform only the fixed BeeDrill reference-target attack in approved isolated environment and returns bounded evidence, by retaining host ownership execution, RPC, policy, authority, timeout and cleanup.

### Iteration 44.2 — Bounded BeeDrill reference-target detection capability

**Status:** DONE

#### Goal

Provide the smallest BeeAgent-owned execution path required by BeeDrill Iteration 7 to observe the fixed `reference_vault` attack through an independent technical reference monitor and return bounded detection evidence.

#### Scope

Included:

- reuse of the existing BeeDrill-scoped `CapabilityCaller`;
- one additional bounded capability: `solana.reference_target_detection`;
- exact scope to the BeeDrill reference-target detection case;
- fixed `surfpool_local` and `reference_vault`;
- reuse of existing reference-target preparation, fixed attack execution, RPC, timeout and cleanup behavior;
- one independent host-owned reference monitor for the fixed `vault_outflow_signal`;
- attack-start slot reference;
- first valid detection slot when observed;
- explicit bounded `observed` / `not_observed` detection evidence;
- explicit timeout/error outcomes distinct from successful observation with no detection;
- fresh-state repeatability;
- real BeeDrill/BeeAgent integration smoke.

#### Excluded

- generic detector framework;
- broad Solana subscription API exposed to modules;
- arbitrary RPC endpoint or method;
- arbitrary executable, argv, path or transaction;
- module-controlled detector rules;
- MTTD calculation;
- containment or verdict behavior;
- SIEM/PagerDuty integration;
- production/mainnet mutation;
- production credentials;
- BeeSDK contract changes;
- changes to existing lifecycle, baseline or attack capability semantics.

#### Deliverable

One host-owned bounded capability that executes the fixed reference attack while an independent reference monitor observes the fixed detector signal and returns machine-verifiable detection timing evidence.

#### Acceptance criteria

- only the exact BeeDrill module/case/capability/authority/payload scope is accepted;
- monitor observation is independent from the attack executor's success assertion;
- target and detector signal are fixed and host-controlled;
- real detection produces bounded attack-start and detection slot evidence;
- a completed observation window without a signal is represented as `not_observed`;
- detector/runtime failure and timeout are distinct from `not_observed`;
- module input cannot choose RPC target/method, detector rule, executable, argv, path, transaction or credentials;
- fresh runs preserve equivalent security-relevant detection behavior;
- timeout and cleanup are bounded;
- no tested path leaves an orphan managed process;
- no production/mainnet fallback or production secret is introduced;
- existing lifecycle, baseline and attack capabilities remain compatible.

#### Checks

```text
targeted capability/runtime tests
full pytest
approved module/case/capability
wrong module/case/capability refusal
forbidden payload refusal
real detection produced
completed observation with detection absent
delayed observation
detector observation failure
timeout
cleanup
no orphan process
fresh-state replay
BeeDrill cross-repository integration smoke
log/artifact inspection
SAST
SCA only if dependency surface changes
git diff --check
```

#### DoD

BeeAgent can independently observe the fixed BeeDrill reference attack and return bounded detection evidence while retaining complete ownership of execution, RPC, policy, authority, timing bounds and cleanup.

### Iteration 44.3 — Bounded BeeDrill reference-target containment capability

**Status:** DONE

#### Goal

Add the smallest BeeAgent-owned execution path required by BeeDrill Iteration 9 to exercise broken and fixed containment conditions for the existing `reference_vault` attack and return bounded machine-verifiable containment and economic evidence.

#### Scope

- reuse the existing BeeDrill-scoped `CapabilityCaller`;
- add one bounded capability: `solana.reference_target_containment`;
- scope it only to the BeeDrill `reference_target_containment_replay` case;
- reuse the fixed `surfpool_local` target, reference-target preparation, unsafe-withdraw operation, reference detector, RPC boundary, timeout and cleanup;
- accept only the fixed target identity plus a bounded host-validated defense condition: `broken` or `fixed`;
- execute the same fixed two-attempt unsafe-withdraw sequence for both conditions;
- observe the detector after the first attack;
- invoke the existing breaker/control path after detection;
- verify whether the second identical unsafe operation succeeds or is rejected;
- return bounded state, slot, containment-status and economic evidence;
- keep refusal, timeout and runtime error distinct from completed failed containment;
- preserve fresh-state repeatability.

#### Excluded

- generic containment framework;
- arbitrary instruction, transaction or command submission;
- caller-selected executable, argv, filesystem path, RPC endpoint or RPC method;
- caller-controlled Solana instruction code;
- production/mainnet mutation;
- production credentials;
- BeeDrill metrics or verdict computation;
- generic incident-response automation;
- BeeSDK contract changes;
- new runtime dependencies unless separately proven necessary.

#### Deliverable

One host-owned bounded capability that can machine-evidence both ineffective and effective containment for the fixed reference attack without transferring execution authority to BeeDrill.

#### Acceptance criteria

- only the exact BeeDrill module/case/capability/authority scope is accepted;
- only `surfpool_local`, `reference_vault` and the bounded `broken`/`fixed` defense condition are accepted;
- both phases begin from the canonical reference-target economic state;
- the same fixed attack operation is used before and after the defensive correction;
- detection is machine-observed rather than inferred from attack success;
- broken containment allows the subsequent identical unsafe operation and produces higher residual loss;
- fixed containment causes the subsequent identical unsafe operation to be rejected and preserves more capital;
- containment failure/success is derived from target effect and bounded state evidence;
- slot ordering is internally consistent;
- malformed or execution-shaped input is refused before execution;
- timeout and cleanup remain bounded;
- no tested path leaves an orphan managed process;
- no production/mainnet fallback or production secret is introduced;
- existing lifecycle, baseline, attack and detection capabilities remain compatible.

#### Checks

```text
targeted capability/runtime tests
full pytest
approved module/case/capability
wrong module/case/capability refusal
invalid defense condition refusal
execution-shaped payload refusal
broken containment run
fixed containment run
detection-before-containment evidence
second-attack allowed/rejected evidence
economic-state comparison
slot ordering
preparation/transaction/observation failures
timeout
cleanup
no orphan process
fresh-state replay
real BeeDrill cross-repository integration smoke
log/artifact inspection
SAST
SCA only if dependency surface changes
git diff --check
```

#### DoD

BeeAgent can safely execute and evidence the fixed BeeDrill containment experiment in the approved isolated environment while retaining complete ownership of execution, RPC, policy, authority, timeout and cleanup.

### Iteration 44.4 — Bounded BeeDrill oracle-manipulation capability

**Status:** SUPERSEDED (CLOSED)

#### Goal

Add the smallest BeeAgent-owned execution path required by BeeDrill Iteration 10 to execute and evidence one fixed oracle-manipulation security regression in the approved isolated Solana environment.

#### Scope

- reuse the existing BeeDrill-scoped `CapabilityCaller`;
- add one bounded capability: `solana.reference_oracle_manipulation`;
- scope it only to `reference_oracle_manipulation_replay`;
- allow only `surfpool_local` and `reference_oracle_market`;
- accept only the host-validated `broken` or `fixed` defense condition;
- resolve the approved BeeDrill package-owned reference target host-side;
- reuse existing Surfpool startup/readiness, RPC, timeout and cleanup infrastructure;
- prepare the fixed canonical oracle-market state;
- execute the fixed oracle-price manipulation;
- execute the fixed first unsafe borrow;
- independently observe the fixed oracle-price-deviation detector signal;
- invoke the fixed borrow-containment control after detection;
- execute the identical second borrow attempt;
- prove whether that second borrow succeeded or was rejected from transaction and target state;
- return bounded oracle, debt, reserve, timing, containment and economic evidence;
- preserve explicit `ok/refused/timeout/error` outcomes and fresh-state replay.

#### Excluded

- generic oracle/provider capability;
- live Pyth/Switchboard/network oracle data;
- module-controlled price, borrow amount or detector rule;
- arbitrary transaction, instruction, executable, argv, path, RPC endpoint or RPC method;
- production/mainnet mutation;
- production credentials;
- BeeDrill metric or verdict calculation;
- new execution framework;
- BeeSDK contract changes;
- new runtime dependencies unless separately proven necessary.

#### Deliverable

One host-owned bounded path:

```text
BeeDrill fixed oracle scenario
→ BeeAgent policy
→ local Surfpool
→ reference_oracle_market
→ fixed price manipulation
→ fixed unsafe borrow
→ independent detection
→ broken/fixed containment
→ second borrow succeeds/rejects
→ bounded evidence
→ cleanup
```

#### Acceptance criteria

- only the exact BeeDrill module/case/capability/authority scope is accepted;
- target, attack values, detector rule and execution mechanism are host-controlled;
- arbitrary execution-shaped or oracle-parameter input is refused before execution;
- both defense phases start from equivalent canonical target state;
- real target state proves the oracle price changed from canonical to manipulated value;
- real target state proves the first unsafe borrow occurred;
- detection is observed independently from the attack executor's success assertion;
- broken containment allows the second identical unsafe borrow;
- fixed containment produces a confirmed rejection of the second identical borrow;
- debt/reserve evidence proves the economic difference between phases;
- slot ordering is internally consistent;
- failure, timeout and cleanup outcomes are explicit;
- no tested path leaves an orphan managed process;
- no production/mainnet fallback or production secret is introduced;
- existing BeeDrill lifecycle/reference-vault capabilities remain compatible.

#### Checks

```text
targeted capability/runtime tests
full pytest
approved and forbidden scope tests
invalid target/defense/payload refusal
execution-shaped payload refusal
canonical-state preparation
oracle manipulation state evidence
first-borrow state evidence
independent detector observation
broken containment replay
fixed containment replay
second-borrow success/rejection proof
economic evidence consistency
slot ordering
preparation/build/deployment/transaction/observation failures
timeout
cleanup and no orphan process
fresh-state replay
real BeeDrill cross-repository integration smoke
log/artifact inspection
SAST
SCA only if dependency surface changes
git diff --check
```

#### DoD

BeeAgent can safely execute and machine-evidence the fixed BeeDrill oracle-manipulation regression while retaining complete ownership of execution, RPC, policy, authority, target resolution, timeout and cleanup.

### Iteration 44.5 — BeeDrill regression outcome and CI runner host support

**Status:** DONE

#### Goal

Provide the minimal host-side behavior required by BeeDrill Iteration 11 so completed security-control regressions are returned as observable evidence rather than execution errors, and expose the approved BeeDrill scenarios through a bounded CI-friendly host command.

#### Scope

Included:

- reuse of the existing BeeDrill-scoped `CapabilityCaller`, module registry, `execute_module_case(...)`, ArtifactAPI and isolated Solana runtime;
- change reference-vault and oracle containment execution to observe the actual second-operation outcome;
- distinguish confirmed target rejection, confirmed operation success and infrastructure/runtime failure;
- preserve the fixed target, attack, detector and defense-condition inputs;
- return bounded internally consistent evidence for either observed containment outcome;
- add a BeeDrill CLI namespace through the canonical BeeAgent entrypoint;
- allow only the two approved Iteration 11 regression scenarios;
- map each scenario to its fixed case type and payload host-side;
- expose stable machine-readable run metadata and artifact references;
- provide deterministic process exit behavior from BeeDrill-provided security verdicts;
- preserve fresh-state Surfpool lifecycle, timeout and cleanup.

#### Excluded

- BeeAgent security verdict calculation;
- arbitrary module/case/capability/payload execution;
- generic module-runner CLI;
- caller-selected target, RPC endpoint, instruction, transaction, executable, argv or path;
- new Solana execution framework;
- third BeeDrill scenario;
- mainnet or production mutation;
- production credentials;
- BeeSDK contract changes;
- new runtime dependencies.

#### Deliverable

One bounded host path:

```text
./start.sh beedrill run --scenario <approved-scenario>
→ existing BeeAgent module runtime
→ BeeDrill
→ scoped Solana capability
→ actual target outcome evidence
→ BeeDrill security verdict
→ host artifacts
→ machine-readable summary
→ stable exit code
```

#### Acceptance criteria

- successful and rejected second operations are both observable completed target outcomes;
- confirmed target rejection is never confused with RPC/runtime failure;
- a target operation that unexpectedly succeeds under the fixed condition is returned as valid bounded evidence rather than host ERROR;
- timeout, RPC failure, build/deployment failure and cleanup failure remain explicit non-security failures;
- only the approved BeeDrill module, scenario cases and fixed payloads are executable through the CLI;
- CLI input cannot provide arbitrary execution-shaped values;
- CLI reuses `execute_module_case(...)` rather than adding a second module runtime;
- BeeAgent does not derive or override BeeDrill security verdicts;
- PASS, FAIL, CLI misuse and infrastructure/incomplete outcomes have stable distinct exit behavior;
- module and scenario artifacts remain under the existing host-owned run artifact boundary;
- repeated invocations start from fresh/equivalent isolated state;
- no production/mainnet fallback is introduced;
- existing BeeDrill lifecycle/baseline/attack/detection behavior and ROP behavior remain compatible.

#### Checks

```text
targeted isolated-Solana capability tests
actual second-operation success observation
actual confirmed target-rejection observation
unexpected fixed-control failure returned as evidence
RPC/network failure not treated as target rejection
timeout and cleanup regressions
approved CLI scenario selection
unknown/forbidden scenario refusal
execution-shaped CLI/input refusal
exit-code mapping
machine-readable summary
module-result and scenario-artifact inspection
fresh-state repeatability
real BeeDrill/BeeAgent integration smoke
full pytest
compile/import checks as applicable
SAST
SCA only if dependency surface unexpectedly changes
git diff --check
```

#### DoD

BeeAgent can host the BeeDrill regression command without owning security verdict semantics: it executes only approved isolated operations, reports their actual observable outcomes, preserves explicit runtime failures, and exposes enough stable run metadata for BeeDrill security PASS/FAIL to control CI.

### Iteration 44.6 — BeeDrill isolated-execution environment hardening

**Status:** DONE

#### Goal

Close the demonstrated BeeAgent-owned environment-isolation gap in the existing BeeDrill Solana execution path without changing its capability contract or execution scope.

#### Scope

Included:

- replace full host-environment inheritance for BeeDrill Surfpool execution with a bounded child environment;
- stop forwarding the complete `os.environ` to reference-target build commands;
- provide only the environment values proven necessary for the existing Surfpool/Solana toolchain;
- preserve host-owned absolute executable resolution and existing fixed argv;
- verify that unrelated and secret-like environment variables are unavailable to BeeDrill child processes;
- preserve current local RPC, target allowlists, timeouts, cleanup and result semantics;
- verify existing cleanup behavior under failure without redesigning process management unless a real descendant-process failure is reproduced.

#### Excluded

- new capability names;
- new RPC endpoints;
- generic subprocess API;
- generic sandbox framework;
- BeeDrill domain/evidence/verdict changes;
- BeeSDK changes;
- production credentials;
- production/mainnet execution;
- new runtime dependencies.

#### Deliverable

The existing BeeDrill isolated-Solana execution path runs with a bounded child-process environment rather than inheriting unrelated BeeAgent host secrets.

#### Acceptance criteria

- Surfpool does not inherit the complete BeeAgent environment;
- build/deployment subprocesses do not receive the complete `os.environ`;
- injected sentinel secrets and unrelated environment values are absent from captured child environments;
- the minimal required toolchain environment is explicitly tested;
- both approved BeeDrill scenarios continue to run against the fixed local Surfpool target;
- existing fixed RPC and target allowlists remain unchanged;
- timeout and forced-cleanup semantics remain unchanged;
- no production key or unrelated credential is required or propagated;
- no secret appears in logs or artifacts;
- BeeDrill remains `READ_ONLY`;
- no shared BeeSDK contract changes;
- no dependency or lockfile changes beyond the approved `beedrill==0.11.1` alignment.

#### Checks

```text
targeted subprocess-environment tests
sentinel-secret exclusion tests
existing target/RPC refusal tests
existing timeout and cleanup regressions
full pytest
compile/import checks as applicable
both real BeeDrill CLI scenario smokes
log and artifact inspection
SAST
SCA only if dependency surface unexpectedly changes
git diff --check
```

#### DoD

BeeAgent continues to provide the same bounded BeeDrill execution capabilities while child processes receive only the environment necessary for the approved isolated Solana workflow and unrelated host secrets remain outside that execution boundary.

### Iteration 44.7 — Bounded BeeDrill SPL Token containment capability

**Status:** DONE

#### Goal

Provide the smallest BeeAgent-owned execution path required by BeeDrill Iteration 13 to validate one real external Solana security-control surface using the canonical SPL Token program in the approved isolated environment.

#### Scope

Included:

- one BeeDrill-scoped capability: `solana.spl_token_freeze_containment`;
- exact scope to `spl_token_freeze_containment_replay`;
- fixed `surfpool_local` execution target;
- host-pinned SPL Token program identity;
- reproducible ephemeral token state created entirely inside the isolated environment;
- one fixed two-transfer attack sequence;
- host-observed detection evidence after the first transfer;
- broken containment where the freeze control is not activated;
- fixed containment using the SPL Token account-freeze control;
- machine verification of the frozen state and second-transfer outcome;
- integer token-balance economic evidence;
- existing bounded environment, RPC, timeout and cleanup behavior;
- bounded evidence returned through the existing `CapabilityResult` contract;
- CI-friendly execution through the existing BeeDrill host command once the coordinated BeeDrill case is available.

#### Excluded

- generic SPL Token adapter or token framework;
- arbitrary Solana program selection;
- arbitrary instructions, transactions, executable paths or RPC endpoints;
- arbitrary mint/account/private-key input;
- external code download or runtime package installation;
- full DeFi protocol integration;
- mainnet or production mutation;
- production credentials;
- BeeDrill evidence, metric or verdict logic;
- BeeSDK changes;
- new runtime dependencies unless a separate demonstrated blocker is approved.

#### Deliverable

One bounded external-target capability that demonstrates a real SPL Token containment control in isolated Surfpool and returns machine-verifiable attack, detection, containment and economic evidence without transferring execution authority to BeeDrill.

#### Acceptance criteria

- only the exact BeeDrill module/case/capability/authority scope is accepted;
- scenario payload cannot choose the executable, program id, RPC endpoint, path, account keys or transaction instructions;
- the expected SPL Token program identity is resolved and verified host-side;
- both phases begin from equivalent fresh isolated state;
- the first fixed transfer succeeds in both phases and produces observable economic loss;
- detection is based on observed local program/account state rather than a hard-coded success flag;
- broken containment leaves the account transferable and the identical second transfer succeeds;
- fixed containment applies the real account-freeze control, confirms frozen state and the identical second transfer is rejected by the target program;
- evidence contains bounded slots, transaction identifiers, account/control state and integer balance deltas sufficient for BeeDrill evaluation;
- unavailable or inconsistent external target state fails closed;
- timeout and cleanup remain bounded;
- unrelated host environment values and secrets remain unavailable to child execution;
- existing BeeDrill reference regressions remain compatible;
- no production/mainnet endpoint, credential or private key is used;
- dependency and lockfile surfaces remain unchanged unless a separately approved blocker proves otherwise.

#### Checks

```text
exact capability/case/payload allowlist tests
execution-shaped and unexpected-field refusal tests
host-pinned external-program identity tests
broken SPL Token replay
fixed SPL Token freeze replay
second-transfer accepted/rejected proof
balance/state/slot evidence checks
target-unavailable fail-closed test
timeout and cleanup regressions
bounded child-environment / sentinel-secret regression
existing BeeDrill scenario regressions
real BeeDrill/BeeAgent/Surfpool integration smoke
full pytest
log and artifact inspection
SAST
SCA only if dependency surface changes
git diff --check
```

#### DoD

BeeAgent can execute and evidence one real external SPL Token containment experiment for BeeDrill inside the approved isolated Solana boundary, while retaining ownership of program selection, transactions, RPC, authority, credentials, process lifecycle, timeout and cleanup; no generic protocol execution surface or BeeSDK change is introduced.

### Iteration 44.8 — Aggregate BeeDrill regression suite host gate

**Status:** DONE

#### Goal

Add the minimal BeeAgent-owned orchestration required for BeeDrill Iteration 15 to execute all approved security regressions through one CI-friendly command.

#### Scope

- add `./start.sh beedrill check`;
- reuse the existing BeeDrill scenario allowlist and per-scenario module runtime;
- preserve individual `beedrill run --scenario ...`;
- execute all approved scenarios in fixed deterministic order;
- allocate independent run/session identity per scenario;
- preserve fresh isolated execution through existing capabilities;
- aggregate host execution status and BeeDrill-provided security verdicts;
- persist one bounded suite summary through the existing host artifact lifecycle;
- emit concise human-readable terminal output;
- implement stable suite exit-code precedence;
- document a minimal CI/PR-gate example.

#### Excluded

- BeeAgent security verdict calculation;
- new Solana capability;
- arbitrary scenario discovery;
- arbitrary module/capability/payload execution;
- new RPC or process authority;
- new dependency;
- BeeSDK change;
- AI;
- Web UI;
- hosted CI infrastructure.

#### Deliverable

One host command executes the fixed BeeDrill regression suite and returns deterministic aggregate status, artifact references and CI exit behavior.

#### Acceptance criteria

- the existing allowlist is the only source for executable BeeDrill regression cases;
- `supported_case_types()` is not used as dynamic suite discovery;
- every scenario uses `execute_module_case(...)`;
- existing individual command output and exit semantics remain compatible;
- aggregate status never overrides or recalculates a BeeDrill security verdict;
- runtime non-success remains distinct from completed security FAIL;
- incomplete/runtime outcomes take exit-code precedence over completed FAIL;
- all safely runnable scenarios are attempted even after an earlier independent failure;
- aggregate artifact references canonical individual run artifacts;
- no raw evidence duplication or arbitrary path input is introduced;
- CI relies on process status rather than parsing terminal prose;
- no execution, RPC, credential or authority boundary is widened.

#### Checks

```text
CLI validation
existing individual run regression
fixed scenario order
all PASS
one/multiple FAIL
refused / timeout / runtime error
mixed FAIL + incomplete
stable counts/status/schema
stable exit mapping
suite artifact references
fresh run/session identities
full pytest
real three-scenario integration smoke
CI gate smoke
log/artifact inspection
SAST
SCA only if dependencies change
git diff --check
```

#### DoD

BeeAgent provides one bounded aggregate BeeDrill regression gate without introducing a second runtime, security-verdict logic, new execution authority or new shared contracts.

### Iteration 44.9 — BeeDrill evidence-grounded AI assist host integration

**Status:** DONE

#### Goal

Add the minimal BeeAgent-owned AI host path required by BeeDrill Iteration 16 while keeping `./start.sh beedrill check` as the single operator command and keeping deterministic BeeDrill results independent of AI.

#### Scope

- add BeeAgent configuration:

```yaml
beedrill:
  ai_assist:
    enabled: false
    timeout: 20
    input_chars_max: 6000
    output_chars_max: 4000
    prompt_key: "beedrill.result_explanation"
```

- validate the new configuration through the normal BeeAgent settings path;
- preserve:

```text
./start.sh beedrill check
```

as the only BeeDrill suite command needed for this feature;

- do not introduce `check --ai`;
- when `beedrill.ai_assist.enabled=false`, perform zero AI provider calls;
- when enabled, run optional AI assistance only after the deterministic BeeDrill suite result and canonical deterministic suite artifact exist;
- do not invoke AI when the aggregate suite is `INCOMPLETE`;
- consume only BeeDrill-provided bounded `explanation_facts`;
- do not parse scenario-specific BeeDrill artifacts to infer detector, containment, metric or verdict semantics;
- reuse existing BeeAgent `ai.profiles` and `ai.prompts`;
- preserve BeeAgent ownership of provider, model, credentials, timeout and egress;
- reuse or minimally extract domain-neutral provider transport where needed rather than coupling BeeDrill to ROP adjudication semantics;
- preserve existing ROP AI behavior and schemas;
- perform at most one provider call for one completed BeeDrill suite;
- use a BeeDrill-specific strict structured output schema;
- keep AI analysis structurally separate from deterministic suite truth;
- persist one bounded host-owned AI artifact, for example:

```text
beedrill_ai_assist.json
```

- record source suite/scenario provenance plus provider/model identity without credentials;
- provider/config/response failures affect AI-assist status only and never rewrite deterministic BeeDrill PASS/FAIL or process exit semantics;
- align the BeeAgent optional BeeDrill package pin to the actual released BeeDrill version after the BeeDrill implementation is released.

#### Excluded

- BeeAgent-generated security verdicts;
- recalculation of BeeDrill metrics;
- interpretation of raw scenario evidence;
- AI calls for incomplete results;
- `--ai` / `--no-ai` CLI overrides;
- fallback provider selection;
- arbitrary AI tool/capability access;
- Solana execution initiated by AI;
- new scenario execution capability;
- generic AI-agent framework;
- new BeeSDK contract;
- Web UI;
- production/mainnet mutation.

#### Deliverable

The same command:

```text
./start.sh beedrill check
```

behaves according to BeeAgent configuration:

```text
beedrill.ai_assist.enabled=false
→ deterministic suite only
→ zero AI calls

beedrill.ai_assist.enabled=true
→ deterministic suite
→ deterministic artifact/result finalized
→ optional evidence-grounded AI assistance
→ deterministic exit status preserved
```

#### Acceptance criteria

- default configuration disables BeeDrill AI assistance;
- disabled configuration produces zero AI provider calls;
- enabled configuration plus completed suite performs at most one AI request;
- enabled configuration plus incomplete suite performs zero AI requests;
- deterministic suite execution does not require an AI provider;
- deterministic suite artifact is created independently from AI output;
- deterministic exit semantics remain `0=PASS`, `1=completed security FAIL`, `2=invalid invocation`, `3=INCOMPLETE/runtime failure`;
- AI failure cannot turn PASS into FAIL, FAIL into PASS or a completed result into INCOMPLETE;
- BeeAgent consumes only BeeDrill `explanation_facts`;
- no scenario-specific BeeDrill evaluation logic is duplicated in BeeAgent;
- provider/model are selected from existing BeeAgent AI profiles;
- prompt is selected through the existing BeeAgent prompt configuration;
- no API key or credential appears in requests artifacts/logs beyond what is required for provider transport;
- request and response sizes are bounded;
- structured response is validated before persistence/use;
- AI output does not contain an authoritative security-verdict field;
- FAIL output may contain remediation hypotheses;
- PASS output may contain a concise explanation of validated controls;
- remediation is explicitly marked unverified until deterministic replay;
- provider/model identity and deterministic-run provenance are recorded;
- ROP AI behavior remains regression-compatible;
- no BeeSDK change is introduced;
- no new third-party runtime dependency is introduced unless separately approved.

#### Checks

```text
settings validation
AI disabled / zero-call regression
AI enabled / completed-suite path
AI enabled / incomplete-suite zero-call path
existing beedrill check regression
all PASS
completed FAIL
runtime incomplete
same deterministic exit with AI on/off
bounded request
secret sentinel
prompt-injection-shaped facts
valid structured response
invalid schema
provider timeout
provider error/refusal
oversized response
artifact provenance
artifact write failure after deterministic result
ROP AI regression
BeeAgent targeted tests
BeeAgent full pytest
real deterministic BeeDrill suite smoke
controlled AI-provider smoke
log/artifact inspection
SAST
SCA if BeeDrill dependency pin changes
git diff --check
```

#### DoD

BeeAgent provides optional configuration-driven BeeDrill AI explanation through the existing host command without becoming a BeeDrill verdict authority, without exposing raw BeeDrill evidence to provider-specific code, without changing deterministic suite behavior and without introducing a second operator command.

### Iteration 44.10 — Release-backed BeeDrill bootstrap for standalone BeeAgent checkout

**Status:** DONE

#### Goal

Remove the sibling-repository requirement from the normal BeeDrill user/judge flow so a clean BeeAgent checkout can resolve BeeSDK and the enabled BeeDrill module automatically through the existing `./start.sh` bootstrap.

Target user flow:

```text
git clone BeeAgent
→ ./start.sh beedrill check
→ BeeAgent resolves BeeSDK
→ enabled BeeDrill extra is resolved automatically
→ BeeDrill module loads
→ security regression suite executes
```

The iteration must preserve the existing configuration-driven module model:

```text
modules.registry[].enabled
+
modules.registry[].install_extra
→ runtime dependency selection
```

No second module installer or setup framework is introduced.

#### Scope

Included:

- replace the normal-user sibling-only BeeSDK dependency source with a reproducible release-backed source;
- replace the normal-user sibling-only BeeDrill optional dependency source with a reproducible release-backed source;
- use already released, explicitly pinned BeeSDK and BeeDrill versions;
- use immutable/reproducible release references rather than a moving branch;
- update `uv.lock` consistently with the approved dependency-source change;
- preserve the existing BeeAgent base bootstrap:
  - install/bootstrap `uv` when needed;
  - base environment sync;
  - settings loading;
  - enabled-module extra resolution;
  - second locked sync;
- preserve `modules.registry[].enabled` as the runtime module-availability control;
- preserve `install_extra: "beedrill"` as the BeeDrill installation profile;
- preserve disabled-module behavior;
- verify that a clean BeeAgent checkout with no sibling `beesdk/` or `beedrill/` directory can execute the BeeDrill suite;
- document the distinction between:
  - normal user/judge release-backed installation;
  - coordinated local multi-repository development;
- reconcile BeeAgent documentation with the actual tracked BeeDrill module configuration.

#### Excluded

- new module installer framework;
- interactive setup wizard;
- automatic configuration mutation;
- dynamic plugin downloads;
- arbitrary package names from user input;
- arbitrary Git URLs from configuration;
- new module registry contract;
- new BeeSDK public contract;
- new BeeDrill execution capability;
- new Solana scenarios;
- custom protocol integration;
- BeeDrill verdict changes;
- Web UI;
- production/mainnet mutation;
- unrelated ROP dependency/source redesign unless clean-checkout verification proves it is a direct blocker.

#### Deliverable

A normal BeeAgent checkout no longer requires manually prepared sibling `beesdk/` and `beedrill/` repositories to run the enabled BeeDrill module.

The existing command remains:

```text
./start.sh beedrill check
```

and the existing bootstrap automatically resolves the dependencies required by that configured module.

#### Acceptance criteria

- clean BeeAgent checkout contains no required sibling `../beesdk` directory;
- clean BeeAgent checkout contains no required sibling `../beedrill` directory;
- BeeSDK resolves from an explicitly pinned reproducible release source;
- BeeDrill resolves from an explicitly pinned reproducible release source when the BeeDrill module profile is enabled;
- no moving `main`, branch-head or unpinned dependency source is used;
- `uv.lock` records the reproducible resolved dependency state;
- normal `./start.sh` still owns bootstrap and dependency synchronization;
- no separate BeeDrill install command is required;
- the existing module registry remains the source of truth for module availability;
- enabled BeeDrill causes its existing optional dependency profile to be installed;
- disabled BeeDrill does not require the BeeDrill module at runtime;
- `./start.sh beedrill check` loads `BeeDrillModule` through the existing module registry and runtime;
- the three approved BeeDrill scenarios remain unchanged;
- suite exit semantics remain:
  - `0=PASS`;
  - `1=completed security FAIL`;
  - `2=invalid invocation`;
  - `3=INCOMPLETE/runtime failure`;
- no BeeDrill security verdict is calculated or overridden by BeeAgent;
- existing authority, capability, RPC and Surfpool boundaries remain unchanged;
- no new runtime dependency package is added beyond changing the approved source of already required BeeSDK/BeeDrill packages;
- BeeSDK public contracts remain unchanged;
- documentation clearly separates normal release-backed use from coordinated local source development.

#### Checks

```text
dependency-source / lockfile review
clean BeeAgent checkout with no sibling beesdk
clean BeeAgent checkout with no sibling beedrill
base ./start.sh bootstrap
enabled BeeDrill extra resolution
BeeDrill module registry load
./start.sh beedrill check
three-scenario PASS smoke
suite exit-code verification
artifact verification
disabled-module regression
existing module-registry regression
existing BeeDrill individual-run regression
full BeeAgent pytest
compile/import checks as applicable
SCA
dependency provenance review
no unpinned Git/source reference
secret/log/artifact inspection
git diff --check
```

#### DoD

A judge or developer can obtain BeeAgent, run its normal bootstrap and execute the configured BeeDrill security-regression suite without manually cloning BeeSDK or BeeDrill as sibling repositories, while all existing module, execution, authority and deterministic-verdict boundaries remain unchanged.

### Iteration 44.11 — BeeDrill Native Bootstrap and Isolated Runtime Recovery

**Status:** DONE

#### Goal

Restore reliable BeeDrill execution for clean BeeAgent checkouts by preparing verified native Solana tooling automatically, preserving secure process boundaries and removing protocol-specific LobsterPay integration from BeeAgent core.

#### Scope

- restore the verified main-based native readiness and runtime recovery;
- retain the existing pinned BeeSDK/BeeDrill dependency-resolution model;
- automatically prepare approved Surfpool, Solana CLI, SBF builder and Rust tools on supported Linux;
- verify official download sources, file sizes, SHA-256 digests and safe extraction;
- use a bounded, atomic, locked user-local native tool cache;
- preserve the restricted child HOME/PATH and prevent unrelated credential forwarding;
- apply bounded build/deploy timeouts and process-group cleanup;
- return allowlisted diagnostic reasons for unsuccessful execution;
- preserve the three existing BeeDrill regression paths and suite ordering;
- preserve host-owned capability, RPC, execution and artifact boundaries;
- remove LobsterPay-specific executor, ABI/account mapping and CLI dispatch;
- preserve BeeAgent-ROP, BeeSDK, module registry and AI-assist compatibility.

#### Excluded

- new developer-owned Solana program execution;
- LobsterPay-specific runtime integration;
- generic protocol adapter or transaction interpreter;
- dynamic plugins or arbitrary execution inputs;
- new BeeSDK contracts;
- production/mainnet execution;
- operating-system package installation;
- new dependencies, lockfile updates or version bump;
- unrelated BeeAgent-ROP changes or UI development.

#### Deliverable

The existing BeeAgent entrypoint prepares the approved native dependencies and runs the bounded BeeDrill suite:

```text
./start.sh beedrill check
→ native toolchain readiness
→ scoped BeeDrill runtime
→ three isolated Solana regressions
→ observed host evidence
→ BeeDrill security verdicts
→ aggregate ArtifactAPI output
→ CI exit status
```

Unsupported native environments must report INCOMPLETE, not a completed security FAIL.

#### Acceptance criteria

- the exact recovery implementation is present on the intended BeeAgent feature branch;
- protocol-specific LobsterPay code and external execution dispatch are absent;
- native toolchain identities, download digests and artifact sizes are pinned and verified;
- archive extraction, cache locking, integrity and cleanup are bounded;
- warm-cache reuse does not unnecessarily modify verified files;
- child environments exclude unrelated host credentials;
- unsupported environments and native preparation failures are explicitly diagnosed;
- invalid or disabled BeeDrill execution does not provision native tools;
- BeeAgent retains authority over all RPC, signing, process and isolation behavior;
- BeeAgent never calculates or overrides BeeDrill security verdicts;
- `PASS=0`, `FAIL=1`, `INVALID_CLI=2`, `INCOMPLETE=3`;
- the original three-scenario aggregate schema and ordering are preserved;
- BeeAgent, BeeDrill and BeeAgent-ROP remain compatible;
- actual scenario evidence and package/import checks pass;
- clean-clone suite and cold native preparation are verified as separate tests;
- independent Max reproduction is pending until performed;
- no unrelated configuration, dependency or version change is introduced.

#### Checks

```text
native artifact provenance
SHA-256 / download / redirect verification
archive traversal and extraction bounds
corrupt cache / unsupported platform
cold native installation
warm-cache reuse
restricted HOME/PATH and secret handling
module registry / disabled-module checks
capability / authority allowlists
timeout / process-group cleanup
three real Solana regressions
ineffective fixed containment → FAIL
effective containment → PASS
RPC failure → INCOMPLETE
invalid CLI → 2
suite aggregate/artifact verification
full BeeAgent pytest
full BeeDrill pytest
BeeAgent-ROP compatibility
clean-clone reproduction
package build/import/public contracts
SAST/security-sensitive review
git diff --check
```

#### Evidence

- BeeAgent: 2,225 passed.
- BeeDrill: 586 passed.
- BeeAgent-ROP: 483 passed.
- Real Solana suite: 3/3 PASS.
- Ineffective completed SPL freeze control: FAIL, exit 1.
- Effective containment: PASS, exit 0.
- Runtime failure: INCOMPLETE, exit 3.
- Invalid CLI: exit 2.
- Native cold preparation: 264.06 seconds.
- Native cache reuse: 0.69 seconds.
- Clean clone with exact corrected sources: 3/3 PASS using an existing native cache.
- Independent Max reproduction: pending.

Evidence and provenance:

`/home/bee/Pro/beeagent/storage/mvp-correction-20261008/`

These are implementation verification results, not an independent external-developer acceptance test.

#### DoD

BeeAgent can prepare the supported native Solana environment and execute the original BeeDrill security-regression corpus through the existing runtime without new protocol-specific core logic, authority escalation, secret leakage or regression to ROP functionality.

Final closure requires adopted Issue scope, completed review and truthful reporting of independent developer validation.

#### Product decision

The external developer-owned pause/freeze execution capability was not implemented in this recovery.

A generic transaction/account binding interpreter requires a separate security-sensitive design and product GO/NO-GO decision.

Any future BeeDrill product integration must preserve BeeAgent ownership of isolated execution, runtime authority, RPC, ephemeral signers, timeouts and artifacts. BeeDrill retains domain evaluation and deterministic security verdicts.

### Iteration 44.12 — Generic Isolated Project Test Execution

**Status:** DONE

#### Goal

Provide the minimal reusable BeeAgent-hosted isolated native-test execution capability for BeeDrill Test Regression Diff, without embedding external protocol logic or security verdicts into BeeAgent.

#### Scope

- Extend the existing BeeAgent CLI with `beedrill diff`.
- Accept two external LiteSVM project roots: baseline and candidate.
- Validate canonical project paths, one supported regular-file layout and preinstalled test dependencies.
- Use one fixed, host-selected native-test workflow for the MVP.
- Execute untrusted project tests in separate disposable, security-reviewed isolated environments.
- Reuse existing runtime, process, timeout, cleanup and artifact infrastructure where applicable.
- Capture host-observed execution provenance, test identities and bounded process outcomes.
- Record independent transaction/state observations only when an approved host observer actually provides them.
- Pass bounded evidence to BeeDrill using existing public module/BeeSDK contracts.
- Preserve existing CLI commands, module registry, ROP, AI assist and CI behavior.

#### Excluded

- Transfer Switch-specific executors, Program IDs, ABI, PDAs, account mappings, instruction builders, policies or security packs.
- Domain test-regression classification or security verdict calculation inside BeeAgent.
- Independent BeeDrill CLI/runtime.
- Arbitrary test commands from project configuration.
- Running untrusted Cargo, Node or Anchor code directly on the host, or executing project metadata commands, installers or lifecycle hooks.
- Generic transaction interpreters, execution DSLs or plugin frameworks.
- Production/mainnet execution, production secrets and unrestricted network access.
- BeeSDK interface changes without demonstrated necessity.

#### Deliverable

```bash
./start.sh beedrill diff \
  --baseline <project-path> \
  --candidate <project-path>
```

BeeAgent owns CLI dispatch, approved isolated execution, host-generated runner evidence, artifact persistence and cleanup.

BeeDrill owns deterministic evidence interpretation and test-regression classification.

#### Acceptance criteria

- CLI entrypoint is integrated with the existing BeeAgent dispatch.
- Supported project tests can execute without modifying BeeAgent for that project.
- The isolation mechanism is available, verified and fail-closed before external code executes.
- Baseline and candidate run independently using comparable test conditions.
- No project input grants arbitrary host execution, signing, filesystem or RPC authority.
- Program-specific transaction construction remains outside BeeAgent core.
- Host-generated runner provenance and bounded process outcomes are recorded correctly.
- Test assertions, exit status, stdout and project-generated reports never become a security verdict.
- BeeDrill receives bounded evidence through an approved module/shared contract.
- The host does not calculate security verdicts.
- Missing isolation, dependencies, unsupported frameworks and execution errors remain non-successful outcomes.
- Existing three scenarios, CLI exit codes, optional modules and ROP remain compatible.
- A second compatible project requires no protocol-specific host code changes.

#### Checks

- CLI argument validation and compatibility.
- Supported/unsupported LiteSVM project detection.
- Canonical paths, symlink traversal and malformed input rejection.
- Fixed runner and execution-authority validation.
- Sandbox isolation, filesystem/network/secret boundaries.
- Timeout, cancellation and cleanup.
- Baseline/candidate environment reproducibility.
- Provenance and evidence-integrity checks.
- Real Transfer Switch original/modified test execution with trustworthy process outcomes.
- Full BeeAgent pytest, build and security checks.
- BeeDrill regression suite and cross-repository E2E.
- `git diff --check`.

#### DoD

BeeAgent safely executes the supported external test workflow, supplies bounded host evidence to BeeDrill, preserves all existing host behavior and contains no third-party protocol-specific integration or security verdict.

**DONE requires successful isolated execution, working CLI, test-regression evidence and independent final review. Independent security PASS/FAIL requires a separately approved invariant and host observer.**

### Iteration 44.13 — Single-Project Isolated Security Test Execution and Onboarding

**Status:** DONE

#### Goal

Allow BeeDrill to execute one supported external Solana LiteSVM security-sensitive test directly from a normal single-project checkout, without manually prepared baseline/candidate snapshots or protocol-specific BeeAgent code.

#### Scope

- Add `beedrill check --project <absolute-path>` to the existing CLI.
- Preserve the current no-argument `beedrill check` regression suite.
- Reuse the existing isolated LiteSVM execution infrastructure.
- Add a narrowly scoped host capability for one project.
- Build a bounded temporary test workspace from an ordinary supported checkout.
- Exclude `.git`, unrelated files, local secrets and unsupported artifacts.
- Validate filesystem boundaries, symlinks, file types, sizes and staging limits.
- Reuse the approved host-selected test workflow and verified isolation.
- Reuse the existing Node.js runner without introducing another framework.
- Resolve a supported Node executable through a verified host-controlled mechanism when portability requires it.
- Preserve Bubblewrap, cgroup limits, no-network execution, environment isolation, timeout and cleanup.
- Pass bounded host execution evidence to BeeDrill through existing BeeSDK contracts.
- Update Quick Start documentation and supported-project requirements.

#### Excluded

- Arbitrary project-selected commands, scripts or installers on the host.
- General Anchor/Cargo/Node build orchestration or arbitrary dependency installation.
- Additional test runners, new container backends or new sandbox frameworks.
- Transfer Switch-specific code, ABI mapping or transaction builders.
- Protocol-specific security verdicts inside BeeAgent.
- Production/mainnet execution, production secrets and unrestricted network access.
- BeeSDK changes without a demonstrated contract gap.
- Web UI or unrelated runtime refactoring.

#### Deliverable

`./start.sh beedrill check --project <absolute-path>`

The command executes one supported external test in verified isolation, supplies bounded evidence to BeeDrill, and returns an actionable CI exit status.

Existing `check`, `run` and `diff` entrypoints continue to work.

#### Acceptance criteria

- A supported ordinary checkout requires no manually created baseline/candidate directories.
- One existing security-sensitive test executes against a real program.
- The host never invokes untrusted project execution outside verified isolation.
- Missing supported dependencies or artifacts produce an explicit non-successful outcome.
- Filesystem traversal, external symlinks and unsupported content cannot escape the staging boundary.
- Isolation availability, memory limits and cleanup are verified fail-closed.
- Test identity, runner identity, execution result and bounded provenance are collected.
- Infrastructure failures are not presented as successful test outcomes.
- BeeDrill alone classifies domain-level test outcomes.
- Existing BeeAgent CLI, modules, ROP, optional AI and CI remain compatible.
- Positive and negative E2E results are reproduced on an external supported project.
- A clean GitHub installation works using only documented prerequisites.

#### Checks

- CLI dispatch and invalid-argument tests.
- Normal checkout, `.git` exclusion and temporary staging tests.
- Path traversal, symlink, special-file and resource-limit negative tests.
- Missing runtime, dependencies, artifacts and unsupported-layout tests.
- Fixed runner identity and prohibited project-command tests.
- Sandbox, network, environment, secrets, timeout and cleanup verification.
- Runner outcome and provenance-integrity tests.
- Full BeeAgent tests, build/import and security checks.
- Existing BeeDrill `check`, `run`, `diff` and ROP regression tests.
- Real external-program E2E and clean-clone onboarding.
- `git diff --check`.

#### DoD

BeeAgent executes one supported external LiteSVM security-sensitive test from a single project checkout through the existing approved isolation boundary, provides truthful bounded evidence to BeeDrill, and preserves current runtime behavior.

Any preparation mechanism not proven safe and reproducible remains unsupported rather than bypassing isolation.

### Iteration 45 — Unified AI Profile Selection v1

**Status:** DONE

#### Goal

Enter a single AI- profile selection contract in BeeAgent Core: global default profile and independent overrides for ROP, BeeDrill and BeeScan.

Ensure the modular independence of AI- providers, eliminate duplication of profiles and preserve existing runtime/security contracts.

#### Scope

- Implement one shared AI profile resolver above `config/settings.yml`.
- Add `ai.default_profile` and optional module-level `ai_profile`.
- Use priority: module override → global default.
- Connect ROP adjudicator existing ROP AI assist, BeeDrill AI assist and BeeScan investigation.
- Save legacy single-enabled-profile config in the absence of `ai.default_profile`.
- Reject conflicting choice regimes without implicit fallback.
- Validate profile names, providers, models, URL and credentials. links
- Require credentials only under the current contract of the active AI- consumer.
- Save BeeScan HTTPS restrictions, host authorization and fail-closed behavior.
- Save bounded AI requests, deterministic fallbacks and secure provider/model provenance.
- Update documentation and contract/regression tests.

#### Excluded

- New AI framework dependencies, provider routers and automatic failover.
- AI model selection for price, latency or tasks.
- New prompts, AI agents, domain rules and capability permissions.
- Modifications BeeScan security semantics or beeagent-rop classification rules.
- BeeSDK, BeeUI, Web Console, a new secrets system and new services.
- Unrelated refactoring and dependency updates.

#### Deliverable

BeeAgent Core provides a single tested AI profile resolver.

ROP may inherit global OpenRouter; BeeDrill is the independent choice of OpenAI; BeeScan — choose DeepSeek. independently

Legacy configuration continues to operate, the new scheme has a clear documented migration path.

#### Acceptance criteria

- All active AI consumers uses shared resolver.
- Default/override precedence is single and covered with tests.
- ROP, BeeDrill and BeeScan may use different profiles simultaneously.
- Old single-enabled contract retained.
- Unknown, conflicting and incorrect profiles are rejected.
- Disabled/dry-run does not create new credentials requirements or external calls.
- Provider transport and deterministic fallback remain compatible.
- BeeScan authority, HTTPS and evidence boundaries are not weakened.
- Provider/model provenance is correct, secrets is not open.
- There are no new dependencies or changes in public contracts for domain packages.

#### Checks

- Legacy/default/override compatibility matrix.
- OpenAI Responses, OpenRouter and direct DeepSeek mocked tests.
- Missing key, unknown profile, malformed URL/model, conflicting selection tests.
- ROP adjudicator and ROP AI assist regression.
- BeeDrill AI assist regression.
- BeeScan BS-8 and BS-7 authorization/investigation regressions.
- Full frozen pytest, build, Ruff/security checks, `git diff --check`.
- Local mocked-provider smoke and logs/artifacts. verification
- Dependency/version/unrelated-file checks.

#### DoD

All active AI- users use a single profile contract, independent overrides is working, legacy config is compatible, the wrong configuration does not lead to a hidden choice of the provider, and the complete set of local checks passes.

**No automatic fallback, authority expansion, new AI framework dependency or version bump.**

---

## Stage 5 - Operator / product shell v1 (reference)

### Purpose of stage

Stage 5 adds the minimum operator/client-facing shell above the already existing orchestrator and module contracts.

Stage focus:

- bounded operator UI / chat flow;
- run overview;
- module summaries;
- stable backend contracts;
- minimal safe actions.

### Expected direction

Stage must take small steps:

- First read-only operator/client summaries;
- Then stable backend/API contracts;
- Then minimal safe actions;
- only then the wider UI.

### Expected size

Direction: **3-5 iterations**.

---

## Stage 6 – Multi-module scaling v0 (reference)

### Purpose of stage

Stage 6 expands `beeagent` from the first client module to the platform of multiple domain modules.

Stage focus:

- `beescan`;
- `merch`;
- shared module diagnostics;
- better tenant/module separation;
- reusable capability policies.

### Expected direction

Stage must take small steps:

- First, the second real module;
- then shared module diagnostics;
- Then common operator/product contracts;
- then more mature multi-module platform.

### Expected size

Direction: **4-6 iterations**.

---

## Related process documents

ROADMAP is used to perform iterations together with:

- `docs/DEV_GUIDE.md` — how to launch the project and how to work with AI/Copilot in the project;
- `docs/SDLC.md` — lightweight process, change levels, required quality/security checks, DoD flow;
- `docs/SECURITY.md` is secure development rules and security checks for different types of changes.
