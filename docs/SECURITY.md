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
