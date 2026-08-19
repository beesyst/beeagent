# SECURITY — beeagent

## Purpose

This document defines the practical security rules for `beeagent`.

The goal is to improve code and runtime safety without creating unnecessary bureaucracy.

This is **not** a formal enterprise security program.

It is a lightweight engineering guide for deciding:

- what needs security attention;
- which checks are worth running;
- how to keep secrets and runtime artifacts safe;
- how to align security checks with the SDLC-light workflow.

Use this document together with:

- `docs/SDLC.md`
- `docs/ROADMAP.md`
- `docs/DEV_GUIDE.md`

## Security principles

Security in `beeagent` should follow these principles:

- protect secrets first;
- validate configuration explicitly;
- fail fast on invalid required inputs;
- keep runtime behavior observable but not overexposed;
- avoid hidden defaults for sensitive behavior;
- minimize attack surface;
- prefer simple designs over complex, fragile abstractions;
- apply security checks proportionally to the change.

## What we protect

At minimum, the project should protect:

- API secrets and environment variables;
- module loading boundaries;
- MCP/tool/capability boundaries;
- external connector behavior;
- attachment/file parsing paths;
- artifact integrity and predictability;
- config correctness;
- dependency hygiene;
- authority boundaries between read-only, draft-only and execution-capable paths.

## Security-sensitive areas in beeagent

Changes in these areas should be treated more carefully:

- `config/settings.yml`
- `config/start.py`
- `src/beeagent_module/core/settings.py`
- `src/beeagent_module/core/secrets.py`
- `src/beeagent_module/core/app.py`
- `src/beeagent_module/core/llm.py`
- `src/beeagent_module/ui/*`
- `src/beeagent_module/adapters/*`
- `src/beeagent_module/cases/*`
- future module registry / capability boundary code
- dependency files:
  - `pyproject.toml`
  - `uv.lock`

## Core rules

### 1. Config is source of truth

Required runtime behavior must be controlled by config, not hidden code defaults.

If a new required key is introduced:

- it must be explicitly present in `config/settings.yml`;
- it must be validated in `src/beeagent_module/core/settings.py`;
- the app must fail fast with a clear error if it is missing or invalid.

### 2. Secrets must not leak

Secrets must never appear in:

- logs;
- storage artifacts;
- test snapshots;
- PR screenshots;
- example payloads committed to repo.

Safe practice:

- read secrets only from env or approved secret source;
- load only expected env keys;
- never dump full env or request headers blindly;
- never serialize raw secrets into JSON/JSONL.

### 3. Logs must be useful but safe

Logs should be:

- understandable;
- sufficient for debugging;
- free from secret values.

Avoid logging:

- API secret values;
- raw auth headers;
- full environment dumps;
- unredacted credentials;
- raw sensitive payloads from external systems.

### 4. Artifacts must be reproducible and safe

Artifacts in `storage/` should be:

- predictable;
- useful for debugging;
- consistent with logs;
- free from secrets.

If a new artifact is introduced, ask:

- does it help reproduce runtime behavior?
- does it expose anything sensitive?
- does it need redaction or omission?

### 5. External input is untrusted by default

Treat as untrusted:

- env input;
- CLI args;
- config values;
- tool/MCP responses;
- external workflow responses;
- file contents loaded from disk;
- email and attachment contents;
- restored JSON artifacts.

Validate before use where reasonable.

### 6. Keep the trusted surface small

Do not add complexity unless needed.

Good security in this project usually means:

- fewer moving parts;
- explicit behavior;
- narrow interfaces;
- simple validation;
- limited serialization.

## Security checks in this project

To keep the process simple, use only the checks that fit the change.

## SAST

### What it means here

Static review of source code for risky patterns.

### Use SAST when

Run or consider SAST when a PR changes:

- runtime logic;
- config parsing;
- env/secrets handling;
- module loading;
- capability boundaries;
- file/path handling;
- serialization/deserialization;
- tool-facing logic;
- network-sensitive logic.

### Typical things to look for

- secret leakage to logs;
- unsafe file/path usage;
- missing validation;
- overly broad exception swallowing;
- insecure debug code;
- dangerous dynamic execution;
- fragile parsing of untrusted data.

## SCA

### What it means here

Software Composition Analysis: dependency review.

### Use SCA when

Run or consider SCA when:

- `pyproject.toml` changes;
- `uv.lock` changes;
- a dependency is added, removed, or upgraded.

### Typical things to look for

- known vulnerable packages;
- unnecessary packages;
- overly broad dependency additions;
- packages with risky maintenance history.

## DAST

### What it means here

Dynamic testing of exposed runtime behavior.

### Use DAST when

Run or consider DAST when a change affects:

- network-facing runtime behavior;
- MCP/tool surface;
- external connector behavior;
- request/response handling;
- future web/operator shell endpoints.

### Typical things to look for

- malformed input handling;
- crashes under bad external responses;
- unsafe error paths;
- runtime behavior under invalid requests/responses.

## IAST

### What it means here

Interactive testing with runtime instrumentation or deeper runtime observation.

### Use IAST when

Consider IAST only for higher-risk changes such as:

- execution-capable path;
- complex external connector flow;
- capability boundary enforcement;
- high-risk parsing or restore flows.

### Lightweight rule

IAST is **not default** for everyday work.
Use it only when a change is clearly security-sensitive and runtime-observable.

## Fuzzing

### What it means here

Feeding unexpected or malformed input to fragile code paths.

### Use fuzzing when

Consider fuzzing for code that parses or restores:

- JSON/JSONL;
- config-like data;
- CLI input;
- attachment-derived text;
- external tool responses;
- custom parsing/normalization logic.

### Lightweight rule

Do not fuzz everything.
Use fuzzing only for code that can realistically break on malformed input.

## Security levels for PRs

Use these three practical levels.

### Low-risk

Examples:

- docs only;
- comments only;
- test-only changes;
- formatting;
- non-runtime refactor.

Usually enough:

- normal review;
- targeted tests if needed.

### Runtime-risk

Examples:

- orchestrator behavior;
- settings validation;
- artifact contract;
- case dispatch;
- summary generation;
- session handling.

Usually needed:

- `pytest -q`
- smoke run
- log inspection
- artifact inspection
- SAST mindset review

### Security-sensitive

Examples:

- secrets/env logic;
- module loading;
- external connectors;
- attachment parsing;
- new dependencies;
- execution-capable paths;
- tool/MCP boundary changes;
- restore flows from disk/API.

Usually needed:

- all runtime-risk checks;
- SAST;
- SCA if dependencies changed;
- DAST / IAST / fuzzing only if relevant.

## Minimal security checklist for developers

Before opening PR, check:

- are secrets kept out of logs and artifacts?
- are required config keys validated fail-fast?
- did I avoid hidden defaults for sensitive behavior?
- did I keep the change inside the intended scope?
- did I avoid unnecessary abstraction?
- if dependencies changed, were they reviewed?
- if external input is parsed, is the handling robust enough?
- are artifacts still safe to store and inspect?
- are authority boundaries still explicit?

## Minimal security checklist for reviewers

During review, ask:

- does this change touch secrets, module loading, external input, dependencies, parsing, or file paths?
- does it introduce a new trust boundary?
- are logs still safe?
- are artifacts still safe?
- are required validations explicit?
- is any check from this document missing?
- is the solution simple enough?

## Secure logging rules

Allowed:

- high-level runtime events;
- reason codes;
- artifact paths;
- non-sensitive config choices;
- state transitions.

Not allowed:

- raw secret values;
- full env dumps;
- raw credentials;
- debug prints of sensitive payloads;
- accidental dumps of all config if secrets are included.

## Secure artifact rules

Allowed when useful:

- run metadata;
- effective non-secret config;
- summaries;
- recommendations;
- session state;
- diagnostics;
- read-only evaluation summaries.

Not allowed:

- raw API secrets;
- full auth headers;
- env dumps;
- unsafe snapshots that expose credentials or sensitive client data without need.

## Dependency rules

When dependencies change:

- keep changes intentional and minimal;
- commit both `pyproject.toml` and `uv.lock`;
- review why the package is needed;
- review whether it affects runtime or attack surface.

Do not add dependencies “just in case”.

## Path / file safety rules

When working with files:

- prefer explicit project paths;
- avoid uncontrolled path building from untrusted input;
- validate assumptions before reading stored artifacts;
- do not trust restored JSON blindly;
- do not parse arbitrary attachments without clear bounds.

## Authority boundary rules

When a change affects what the system can do:

- make the boundary explicit;
- separate read-only, draft-only and execution-capable paths;
- do not rely on prompt discipline as the only safety mechanism;
- do not silently escalate permissions;
- make denials and restrictions operator-visible.

## Bitrix write-back boundary (Iteration 37)

BeeAgent has a disabled-by-default, bounded Bitrix CRM write-back path for ROP events.
Rules:

- `BitrixReadonlyClient` stays strictly read-only; its allowlist has no mutation
  methods and includes `crm.activity.list` only for idempotency reconciliation.
- Reconciliation email matching uses the exact `EMAIL` filter (not `%EMAIL` substring, which
  some portals treat as returning all entities) and title search is applied only to entity
  types that have a `title` field (contacts are skipped), so connector errors are not
  produced by invalid filters and clean senders are detected reliably as `not_found`.
  Identity evidence (sender email/phone, Contact/Company and related historical CRM
  relation) is never an executable target: an exact matched Lead/Deal, an exact
  Contact/Company and a Deal resolved through the bounded read-only
  `crm.item.list` (`entityTypeId=2`) `contactId`/`companyId` relation all remain
  identity/candidate evidence with `safe_to_use_as_target=false` and
  `needs_manual_review=true`. Title/subject similarity never authorizes a target.
  After successful bounded Lead and related-Deal searches find no executable target,
  reconciliation emits `identity_only_no_target` with
  `suitable_target_search=completed_no_target`, which may enter the configured Lead-create
  path only for `new_lead` or `irrelevant`.
- Automatic existing-target attachment (Iteration 38) is allowed only for exact trusted
  thread evidence resolved from canonical write-back state:
  - normalized `Message-ID`, `In-Reply-To` (preferred) and bounded `References` ancestry
    are used as exact thread evidence;
  - all resolved exact referenced ancestors must agree on a single trusted Lead/Deal;
    conflicting references fail closed to `ambiguous_thread_target` deferred with zero
    mutation;
  - a confirmed BeeAgent-created Lead (`target_provenance=beeagent_created`) is an
    authoritative thread root; a thread-resolved attachment
    (`target_provenance=thread_resolved`) propagates its target to later replies;
  - legacy records without trusted target provenance are never promoted to thread
    authority (fail closed);
  - matching scope is the same `client_id` (not necessarily the same `source_id`);
  - run-local `thr_*` IDs, classifier/AI output, subject similarity and `RE:`/`FWD:`
    markers never authorize attachment;
  - an independent `new_lead` from a known sender (without exact thread evidence) can
    create a new Lead; `existing_deal`/`duplicate` without a safe exact target remain
    deferred/manual-review;
  - an exact reply in the same batch whose thread root is only planned (not yet
    confirmed) is deferred as recoverable `pending_thread_root` and resolved after the
    root is confirmed.
- Write access lives in a separate `BitrixWriteClient` with the exact mutation allowlist
  (`crm.item.add`, `crm.activity.add`) and a dedicated env-backed write credential
  (`bitrix.writeback.webhook_env`, default `BITRIX_WRITEBACK_WEBHOOK_URL`). When enabled,
  its env name and normalized URL must both differ from the read-only credential.
- Write-back is disabled by default; enabling it requires `bitrix.enabled: true`,
  `bitrix.reconciliation.enabled: true`, non-empty configured customer Lead `stageId`
  values for `new_lead` and `irrelevant`, and the write credential env var. Invalid or
  missing stage config fails fast and means zero mutations.
- Configured stage IDs are validated against Bitrix (`crm.status.list`) before any POST;
  invalid or unavailable stage validation means zero mutations (fail closed). When stage
  validation is unavailable because Bitrix is down, create records stay `pending` and are
  retried on subsequent write-back executions (durable intent is preserved), while a
  config-invalid stage defers records until the stage mapping is corrected.
- Lead creation uses `crm.item.add` with `entityTypeId=1` and bounded deterministic
  `ORIGINATOR_ID`/`ORIGIN_ID` for idempotency. `crm.lead.add`, broad `crm.item.update` and
  `crm.item.delete` are never used. Optional config-driven `bitrix.writeback.source_id`
  sets the Lead `SOURCE_ID` field (e.g. `EMAIL` = «Входящее письмо»). When the event has a
  sender email, the Lead `fm` multifield (`EMAIL`/`WORK`) is populated from it so the
  operator can reply to the original message. When the event carries a sender display
  name, it is written to the Lead `NAME` field.
- Email/activity binding uses the official `crm.activity.add` method (email activity,
  `TYPE_ID=4`) and is gated by `bitrix.writeback.email_attach`. For a trusted thread
  target or a legacy safe existing Lead or Deal, the activity uses that target and its
  recorded responsible without changing the entity responsibility. Before every activity
  POST, including after timeout or malformed response, read-only `crm.activity.list` checks
  the stable origin identity; the resulting activity ID is persisted. Each planned record
  snapshots whether email attachment is required and records its attachment status
  independently from Lead creation: a created/recovered Lead is delivery-complete only when
  a required activity has a valid ID. A missing sender, pending/uncertain result, retry
  exhaustion or terminal attach error stays visibly incomplete according to the bounded
  retry policy. `bitrix.writeback.email_attach_completed` (boolean, validated fail-fast,
  default `true`) sets whether the created email activity is completed (`false` creates it as
  not completed, more visible in the timeline) without weakening the
  idempotency/attachment control.
- Before every create POST the executor reconciles by `ORIGINATOR_ID`/`ORIGIN_ID` lookup so
  an uncertain timeout outcome never produces a duplicate Lead.
- `should_rop_see`, AI/final decisions and `rop_action_drafts.json` never grant execution
  authority. Delivery planning includes every classified event including `irrelevant`.
- Unresolved/ambiguous/inactive/degraded or malformed responsible evidence,
  unsafe/ambiguous/duplicate reconciliation targets, conflicting thread references and
  unresolved `existing_deal`/`duplicate` fail closed to an explicit `deferred` outcome; no
  speculative Lead is created and existing CRM entities are never reassigned. An exact
  active routing match with a positive `user_id` sets a new Lead `ASSIGNED_BY_ID`; when
  configured, `bitrix.writeback.fallback_responsible_user_id` (a positive Bitrix user ID,
  validated fail-fast) is used instead only when routing did not match an active user. The
  fallback is never applied while the Bitrix user directory itself is degraded
  (`connector_degraded` remains deferred) and never overrides an exact matched responsible.
- Durable authoritative write-back intent is persisted to
  `storage/interfaces/rop_writeback_state.json` before the mailbox checkpoint advances.
  With write-back enabled, plan persistence failure blocks checkpoint advancement; with
  write-back disabled it is logged and does not block ingestion. External execution occurs
  only after checkpoint commit. After any execution transition, summaries and action drafts for
  affected original runs are refreshed from canonical state without further Bitrix calls.
- With `bitrix.writeback.enabled: true`, `rop poll` and `rop run` execute pending
  write-back work after durable persistence. A temporary reconciliation outage is retained
  as recoverable deferred state, so the checkpoint can advance and a later poll/run refreshes
  reconciliation from retained artifacts without mailbox re-ingestion. A no-new-mail poll
  performs one bounded recovery pass; retry-exhausted and terminal records remain bounded. With
  write-back enabled, `rop run` cannot claim success when reconciliation or durable plan
  persistence fails before canonical intent exists.
  `rop writeback plan/execute` remains available as a controlled manual path with bounded
  retry for transport/429/5xx and terminal handling for permission/config/invalid-field
  failures. Retry-exhausted records (bounded budget exceeded by transient failures) can be
  re-armed with a fresh retry budget via `rop writeback execute --retry-failed`; terminal
  failures (permission/config/invalid-field) are never retried. Disabled and dry-run modes
  perform zero writes.
- Cross-run stable identity is `client_id + source_id + (message_id → x_email_id → event_id)`.
  The run-local `event_instance_id` is not used as remote business identity.
- Credentials, webhook URLs, raw `.eml`, raw attachment bytes and unbounded Bitrix
  responses never appear in logs, write-back state or write-back summaries.

## Security and SDLC integration

Use security as part of the normal workflow:

1. identify change level
2. implement minimally
3. run required checks
4. inspect logs/artifacts
5. document verification in PR

Do not create separate bureaucracy unless the project actually needs it.

## What not to do

Avoid these patterns:

- hidden required defaults in code;
- logging sensitive runtime state;
- dependency additions without review;
- broad refactors mixed with security-sensitive changes;
- “future-proof” abstractions that increase risk and complexity;
- marking every PR as requiring every type of security testing.

## Practical defaults

To keep this lightweight:

- most PRs need only normal review + tests + smoke + log/artifact check;
- code-heavy runtime PRs also need SAST mindset review;
- dependency PRs need SCA;
- connector/interface PRs may need DAST or deeper runtime review;
- fuzzing is targeted, not mandatory everywhere.

## Summary

Security in `beeagent` should stay practical.

The main rules are:

- protect secrets;
- validate config explicitly;
- keep logs safe;
- keep artifacts safe;
- review dependencies;
- use only the security checks that match the real risk;
- keep everything simple enough to maintain.
