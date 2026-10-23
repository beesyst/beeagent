# SPEC — BeeAgent

## 0. Terms

- Repository: `beeagent`
- Python package (import): `beeagent_module`
- Core: BeeAgent’s shared orchestration core
- Module: a separate domain module connected to BeeAgent (`beeagent-rop`, with `beescan` and `merch` planned)
- Case: an application scenario invoked by the transport/UI layer
- Agent: workflow/graph for a specific scenario
- Adapter: Data access layer
- Capability: an external execution or integration call (MCP, n8n, API, system)
- Transport/UI: thin layer of interaction (`telegram`, later web, etc.)
- Run: one reproducible scenario execution with a `run_id`
- Artifact: a file in `storage/` recording a run’s result, steps or state
- Authority: Rights boundary (`read-only`, `draft-only`, `execution-capable`)

## 1. Purpose

Build `BeeAgent` as an explainable, stateful, modular AI orchestration system rather than a “chatbot with tools”.

The system must be capable of:

- start and manage scenarios through a single core;
- work with transport/UI layers without embedding business logic in the UI;
- connect separate domain modules as Python packages;
- store state, artifacts, approvals, summaries and traces inside BeeAgent;
- use AI as a bounded assistive layer rather than a black-box replacement for deterministic logic;
- use MCP / n8n / external systems as a capability layer rather than a home for domain logic.

## 2. Development principles

- KISS: minimum excess abstractions, maximum clear contracts
- Core must remain universal, domain logic lives in modules
- `config/settings.yml` — runtime source of truth
- New required keys are validated fail-fast
- Logs must be understandable
- Artifacts must be reproducible
- Secrets must not enter logs/storage
- Long-running state must live in BeeAgent rather than within one tool/MCP call
- UI must be a thin layer
- The capability boundary must be explicit
- Execution-capable paths must be bounded and operator-visible

## 3. Architecture

System reference diagram:

`UI/Transport → BeeAgent core → module/case → capability layer (MCP / n8n / API / systems)`

Where:

- `UI/Transport` is responsible for entry/exit only;
- `BeeAgent core` is responsible for orchestration, state, approvals, artifacts, policy;
- `module` is responsible for domain logic;
- `capability layer` is responsible for external activities and integration.

## 4. What belongs in the core and what does not

### 4.1 What must live in `beeagent`

- module contract
- module registry
- runtime context
- artifact API
- case dispatch
- agent/workflow orchestration
- logging
- settings validation
- transport handling
- approval/state/session logic
- capability abstraction
- bounded authority logic

### 4.2 What must not live in `beeagent`

- client-specific ROP business logic
- welding-specific lead rules
- client-specific duplicate heuristics
- client-specific email semantics
- merchandising-specific business rules
- beescan-specific business rules

This must live in separate modules.

## 5. Modular Model

### 5.1 Module

A module is a separate Python package connected to BeeAgent as a local dependency.

Examples:

- `beeagent-rop`
- `beescan`
- `beeagent-merch` / `beeagent-merchandising`

### 5.2 What a module must be able to do

The module must:

- have `module_id`
- declare supported `case_type` values
- receive `ModuleContext`
- return a bounded result
- use BeeAgent artifact/runtime contracts
- preserve the authority boundary

For BeeDrill's `isolated_solana_smoke`, BeeAgent injects a caller bound to the host-generated run, session, module, case and read-only module authority. The caller accepts only `solana.isolated_lifecycle` with the fixed `surfpool_local` intent, then owns the offline Surfpool process, fixed local read-only RPC check and cleanup. The returned capability evidence reports the host-applied execution-capable authority without changing the module authority.

For BeeDrill's `reference_target_baseline`, the same host-bound caller accepts only `solana.reference_target_baseline` with the fixed `surfpool_local` and `reference_vault` payload. BeeAgent resolves the public BeeDrill package resource itself and returns only bounded canonical economic/control evidence.

For BeeDrill's `reference_target_attack`, the same caller accepts only `solana.reference_target_attack` with that exact fixed payload and only from the read-only BeeDrill attack case. BeeAgent owns the offline Surfpool lifecycle, target preparation and fixed attack transaction. On success it returns exact target and initial-state identities, a bounded transaction signature, a local slot reference, fixed before/after lamport balances, unsafe-withdraw transition counts and integer gross loss. It returns explicit refusal, timeout or error otherwise; it never accepts module-supplied RPC, executable, path, raw transaction or credential fields.

For BeeDrill's `reference_target_detection`, the same caller accepts only `solana.reference_target_detection` with the fixed `surfpool_local` and `reference_vault` payload from the read-only detection case. BeeAgent installs the fixed `reference_vault_outflow_monitor` before the attack, independently observes `vault_outflow_signal` through the fixed local RPC state read, and returns only detector identity, signal identity, observation status, attack-start slot, and (when observed) first-detection slot. A completed monitoring window without the signal is `not_observed`; runtime and timeout outcomes remain capability errors rather than no-alert evidence.

### 5.3 What a module must not do

The module must not:

- directly control transport/UI;
- maintain its own separate runtime outside BeeAgent;
- directly replace core orchestration;
- silently perform external actions bypassing capability layer;
- create a hidden execution path.

## 6. Capability layer

BeeAgent works via capability layer for external action.

Capability examples:

- MCP tool call
- n8n workflow trigger
- API call
- file/system operation

### Rule

- domain logic does not live in capability layer;
- the capability layer does not store the primary state of a long-running task;
- errors, timeout, refusal must be visible and reproducible.

## 7. Transport / UI

### v0 / Current baseline

- Telegram

### later

- web/operator shell
- Other transport/UI surfaces

### Rule

Transport/UI:

- invokes cases/module flows;
- does not read storage directly;
- Does not store business logic;
- does not replace orchestration.

## 8. Settings

### Source of Truth

`config/settings.yml`

### Rules

- required keys must be explicitly specified;
- new required keys are validated in `src/beeagent_module/core/settings.py`;
- without hidden defaults for important runtime paths.

## 9. Artifacts

All significant results must be reproducible through artifacts in `storage/`.

Typical artifacts:

- `storage/runs/<run_id>/run.json`
- `storage/runs/<run_id>/steps.json`
- `storage/runs/<run_id>/...` case/module-specific artifacts
- `storage/artifacts/<run_id>/report.*`
- `storage/sessions/...`
- `storage/telemetry/...`

### Requirements

The artifacts must be:

- understandable;
- consistent with logs;
- suitable for manual inspection;
- safe in their contents.

## 10. Authority model

### Basic modes

- `read-only`
- `draft-only`
- `execution-capable`

### Rule

By default, everything must be `read-only` or `draft-only`.

If execution-capable path appears, it must be:

- explicit;
- bounded;
- verifiable;
- visible to the operator;
- not hidden in prompt or accidental code path.

### Bitrix write-back v0 (ROP, Iteration 37)

BeeAgent has disabled-by-default bounded Bitrix CRM write-back for ROP events.

Behavior:

- Each classified event (including `irrelevant` and `should_rop_see=false`) falls into delivery planning;
- Each processed event receives outcome `create_lead`, `attach_existing` or `deferred`;
- new eligible Leads are created through `crm.item.add` with `entityTypeId=1` in the configured customer `stageId`, using the exact matched active responsible user from `rop_recipient_routing.json`; optional `bitrix.writeback.user_id_fallback` (a validated positive Bitrix user ID) is assigned as responsible only when `responsible.status=not_found`; matched, ambiguous, `connector_degraded`, unresolved and not-attempted remain deferred; optional config-driven `source_id` sets the Lead `SOURCE_ID` (for example, `EMAIL` = “Incoming email”);
- when `bitrix.writeback.email_attach: true`, an email activity (`TYPE_ID=4`) with bounded subject/body/sender is attached through the official `crm.activity.add`; a trusted exact thread target receives the activity with the existing target owner/responsible user without reassigning the CRM entity; `bitrix.writeback.email_completed` (boolean, validated fail-fast, default `true`) determines whether the created email activity is completed (`false` creates it as incomplete, making it more visible in the timeline);
- planned record snapshots whether email attachment is required. For `create_lead`, a created/recovered CRM entity is delivery-complete only after the required activity has a valid ID; pending, uncertain, exhausted, terminal or sender-unavailable attachment remains an explicit incomplete delivery state;
- trusted exact thread target is processed through idempotent attach-existing path without creating a new Lead; before every activity POST executor uses read-only `crm.activity.list` with the stable origin identity, including after timeout or malformed response, and persists the returned activity ID;
- exact sender email/phone may identify an existing Deal only through an exact matched Contact/Company and bounded read-only `crm.item.list` (`entityTypeId=2`) relation filter on `contactId`/`companyId`; identity evidence (sender email/phone, Contact/Company, related historical CRM relation) is never an executable target — an exact matched Lead/Deal, an exact Contact/Company and a related Deal stay identity/candidate evidence with `safe_to_use_as_target=false`, and title/subject similarity is never automatic Deal authority;
- automatic existing-target attachment is allowed only for exact trusted thread evidence (Iteration 38): normalized `Message-ID`, `In-Reply-To` (preferred) and bounded `References` resolve against canonical write-back state; all resolved exact referenced ancestors must agree on one trusted Lead/Deal; a confirmed BeeAgent-created Lead (`target_provenance=beeagent_created`) is an authoritative thread root, a thread-resolved attachment (`target_provenance=thread_resolved`) propagates the target, legacy records without trusted provenance are never authority, and conflicting exact references fail closed to `ambiguous_thread_target` deferred with zero mutation;
- an exact Contact/Company is identity evidence, not an executable target. Only after the bounded exact Lead search and related-Deal lookup complete without a target does `identity_only_no_target` with `suitable_target_search=completed_no_target` permit the normal configured `new_lead`/`irrelevant` create path. An independent `new_lead` from a known sender (without exact thread evidence) can create a new Lead; `existing_deal`/`duplicate` without a safe exact target remain deferred/manual-review; run-local `thr_*` IDs, classifier/AI output, subject similarity and `RE:`/`FWD:` markers never authorize attachment; existing target responsible is never reassigned;
- the email activity body preview is bounded readable plain text: `<!DOCTYPE ...>`, comments, script/style and HTML tags are removed, safe structural HTML boundaries (`p`/`div`/`br`/`li`/list/table...) become readable line breaks, plain-text line breaks are preserved, excessive whitespace is bounded, and the existing `rop.email_preview.body_chars_max` is preserved without a new parsing dependency;
- `BitrixReadonlyClient` does not contain mutation methods; `crm.activity.list` remains read-only idempotency lookup, while `BitrixWriteClient` is limited only to `crm.item.add` and `crm.activity.add`;
- when write-back is enabled, the dedicated write credential must differ from the read credential in both env name and normalized webhook URL;
- unresolved `existing_deal`/`duplicate`, ambiguous/unsafe targets and unresolved responsible users fail closed to `deferred` without speculative creation;
- the stable cross-run identity is `client_id + source_id + (message_id → x_email_id → event_id)`; `event_instance_id` is not a remote business identity;
- authoritative write-back intent is durably persisted before the mailbox checkpoint; poll ordering is: durable intent → checkpoint → external execution → original per-run projection refresh. A temporary reconciliation outage is retained as recoverable deferred state and reconciled again from retained run artifacts without mailbox re-ingestion.

Artifacts:

- `storage/interfaces/rop_writeback_state.json` — canonical durable write-back state;
- `storage/runs/<run_id>/rop_writeback_summary.json` — read-only per-run projection, refreshed for each original affected run after execution/recovery.

With write-back enabled, `rop run` must durably persist the reconciliation-backed plan before it can report success. A projection or post-persistence executor failure never erases canonical intent and remains recoverable through later run, poll or controlled manual execution.

## 11. Stack

Current stack:

- Python 3.14+
- `uv`
- `PyYAML`
- `python-dotenv`
- `python-telegram-bot`
- `langgraph`
- `pytest`

Additional dependencies are added only when actually needed.

## 12. Launch

### Main launch

`start.sh` starts `uv sync` and then `uv run python3 config/start.py`

### Rule

- the primary runtime starts from the `beeagent` repository
- modules are connected as local dependencies through `uv`
- the module does not start its own separate runtime by default

## 13. Core maturity criteria

BeeAgent is developing in the right direction if:

- the transport layer is thin;
- core is not cluttered with client-specific logic;
- modules connect through a stable contract;
- the capability boundary is explicit;
- artifacts and logs explain the behavior;
- AI does not blur the deterministic path;
- delivering a new module does not require rewriting the core.

## 14. Next direction

Immediate objective:

- complete module platform v0;
- connect `beeagent-rop` as the first real domain module;
- guide the client through Discovery → MVP → Pilot;
- do not break the universality of core.
