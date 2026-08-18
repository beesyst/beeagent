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

- `BitrixReadonlyClient` stays strictly read-only and its allowlist is never widened.
- Reconciliation email matching uses the exact `EMAIL` filter (not `%EMAIL` substring, which
  some portals treat as returning all entities) and title search is applied only to entity
  types that have a `title` field (contacts are skipped), so connector errors are not
  produced by invalid filters and clean senders are detected reliably as `not_found`.
- Write access lives in a separate `BitrixWriteClient` with its own allowlist
  (`crm.item.add` only) and a dedicated env-backed write credential
  (`bitrix.writeback.webhook_env`, default `BITRIX_WRITEBACK_WEBHOOK_URL`), separate from
  the read-only `BITRIX_WEBHOOK_URL` by default.
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
- Email/activity binding for newly created Leads uses the official `crm.activity.add`
  method (email activity, `TYPE_ID=4`) and is gated by `bitrix.writeback.attach_email`
  (default false). A failed attach is retried on subsequent write-back executions until it
  succeeds or `attach_email` is disabled; the last attach error is recorded in
  `last_attach_error_code`. Attaching inbound email to pre-existing entities found by
  reconciliation (`attach_existing`) remains explicitly deferred
  (`email_binding_contract_unconfirmed`) until that path is implemented.
- Before every create POST the executor reconciles by `ORIGINATOR_ID`/`ORIGIN_ID` lookup so
  an uncertain timeout outcome never produces a duplicate Lead.
- `should_rop_see`, AI/final decisions and `rop_action_drafts.json` never grant execution
  authority. Delivery planning includes every classified event including `irrelevant`.
- Unresolved/ambiguous/inactive responsible, unsafe/ambiguous/duplicate reconciliation
  targets and unresolved `existing_deal`/`duplicate` fail closed to an explicit
  `deferred` outcome; no speculative Lead is created and existing CRM entities are never
  reassigned. When `bitrix.writeback.fallback_responsible_user_id` is configured (int > 0),
  an unresolved responsible uses that user as the Lead `ASSIGNED_BY_ID` fallback instead of
  deferring; the record keeps an auditable `responsible_status="fallback"` with reason
  `fallback_responsible_configured`.
- Durable authoritative write-back intent is persisted to
  `storage/interfaces/rop_writeback_state.json` before the mailbox checkpoint advances.
  With write-back enabled, plan persistence failure blocks checkpoint advancement; with
  write-back disabled it is logged and does not block ingestion.
- With `bitrix.writeback.enabled: true`, `rop poll` and `rop run` execute pending
  write-back work automatically after the durable plan is persisted. If Bitrix is
  unavailable during execution, affected records stay `pending`/`uncertain` in the durable
  state and are retried on subsequent executions, so ingested emails are never lost.
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
