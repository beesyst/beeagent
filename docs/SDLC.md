# SDLC — beeagent

## Purpose

This document defines the lightweight SDLC used in `beeagent`.

The goal is to keep development:

- disciplined;
- reproducible;
- easy to follow;
- safe enough for real engineering work;
- free from unnecessary bureaucracy.

`beeagent` uses a practical workflow:

`ROADMAP → Issue → branch → code → tests → artifacts → PR → merge`

This document does not replace `docs/ROADMAP.md`.

- `ROADMAP` defines where the project goes by stages and iterations.
- `Issue` defines one concrete task.
- `PR` proves what was actually delivered and how it was verified.
- `SDLC` defines the working rules for moving changes through the project.

## Core principles

Development in `beeagent` should follow these rules:

- make small, iteration-sized changes;
- stay inside the current scope;
- use `config/settings.yml` as runtime source of truth;
- validate new required config keys fail-fast;
- prefer simple solutions over flexible but unnecessary abstractions;
- keep logs understandable;
- keep artifacts reproducible;
- do not leak secrets into logs or storage;
- keep authority boundaries explicit;
- close work through PR, not only through comments.

## Workflow

### 1. ROADMAP

`docs/ROADMAP.md` defines:

- stage;
- iteration;
- goal;
- scope;
- deliverable;
- artifacts;
- checks;
- DoD.

Before coding, the task should be mapped to the current iteration.

### 2. Issue

Each task should be described in an issue.

The issue should contain at least:

- summary;
- context;
- scope;
- deliverable;
- acceptance criteria;
- tests;
- artifacts;
- notes.

The issue explains **what must be done**.

### 3. Branch

All implementation work should be done in a separate branch.

Recommended naming:

- `feature/<short-name>`
- `fix/<short-name>`
- `docs/<short-name>`
- `chore/<short-name>`

If useful, include iteration number:

- `feature/iter-11-module-contract`
- `feature/iter-15-rop-integration`

### 4. Code

Implementation rules:

- stay within the current iteration scope;
- do not mix unrelated features in one PR;
- do not add “future architecture” without current need;
- do not hide required runtime values inside code;
- do not weaken existing boundaries without reason;
- do not remove existing checks without reason.

Preferred style:

- KISS;
- minimal changes;
- predictable behavior;
- PEP 8;
- explicit validation.

### 5. Tests

Every change should be verified at the level appropriate for its risk.

Common checks:

- automated tests (`pytest -q`);
- smoke run through the expected entrypoint;
- manual log inspection;
- manual artifact inspection.

If the change affects runtime behavior, config contract, module loading, case dispatch, MCP/tool boundaries, file parsing, or dependencies, security/quality checks may also be required. See `docs/SECURITY.md`.

### 6. Artifacts

When applicable, the result of the change should be visible through project artifacts.

Typical places:

- `logs/app.log`
- `storage/runs/<run_id>/...`
- `storage/artifacts/<run_id>/...`
- `storage/sessions/...`
- `storage/telemetry/...`
- `storage/interfaces/...`

Artifacts should be:

- reproducible;
- understandable;
- aligned with logs;
- aligned with the current iteration.

### 7. Pull Request

A PR is the main evidence that the task is ready.

The PR should contain:

- summary;
- related issue;
- iteration reference;
- scope;
- changes;
- tests;
- artifacts;
- checklist;
- notes for reviewer.

The PR explains **what was actually delivered and verified**.

### 8. Merge

A task or iteration item is considered completed only after:

- scope is satisfied;
- required checks are completed;
- artifacts/logs are consistent;
- PR is reviewed;
- changes are merged.

## Definition of Done

A task is considered done when:

- behavior is implemented within the declared scope;
- config is read from `config/settings.yml`;
- new required keys are validated fail-fast in `src/beeagent_module/core/settings.py`;
- the feature runs through the intended entrypoint;
- logs are written and remain understandable;
- artifacts are written when expected;
- tests and manual checks are completed;
- secrets do not leak into logs or artifacts;
- authority boundaries remain explicit;
- docs are updated if behavior, contract, artifacts, or checks changed;
- the result is documented in PR and ready for merge.

## Minimal required checks

These are the default checks unless the task clearly does not need some of them.

### Base checks

- `pytest -q`
- `bash start.sh` or the relevant entrypoint
- manual inspection of `logs/app.log`
- manual inspection of relevant files in `storage/`

### Entry-point related checks

If the change affects entrypoint behavior, also run the affected command, for example:

- `uv run python3 config/start.py`
- `uv run python3 config/start.py shell`
- `uv run python3 config/start.py draft`
- `uv run python3 config/start.py mcp`

### Artifact-related checks

If artifacts change, verify:

- file exists where expected;
- structure is correct;
- JSON / JSONL fields are consistent;
- artifacts match logs and scenario.

## Change levels

To avoid bureaucracy, use only three change levels.

### Low-risk

Use this when the change is mostly local and does not affect sensitive runtime behavior.

Examples:

- docs;
- comments;
- non-runtime refactor;
- test-only additions;
- small UI text changes.

Usually required:

- automated tests if applicable;
- targeted smoke check if applicable.

### Runtime-risk

Use this when the change affects normal application behavior.

Examples:

- config parsing;
- orchestrator logic;
- cases/adapters;
- module registry;
- artifact contracts;
- session handling;
- summaries and recommendations.

Usually required:

- `pytest -q`
- smoke run
- log inspection
- artifact inspection

### Security-sensitive

Use this when the change affects trust boundaries or sensitive paths.

Examples:

- env secrets;
- MCP/tool boundaries;
- external connectors;
- file/path handling;
- attachment parsing;
- serialization/deserialization;
- new dependencies;
- execution-capable paths;
- authority boundaries.

Usually required:

- all runtime-risk checks;
- security checks from `docs/SECURITY.md` as applicable.

## Security-aware development rule

Not every task needs every security practice.

Use only what matches the change:

- SAST for code changes;
- SCA for dependency changes;
- DAST for network-facing behavior;
- IAST for high-risk runtime instrumentation cases;
- fuzzing for parsers, serializers, or fragile input handling.

The goal is not to “tick every box”.
The goal is to apply the right check for the right type of change.

See `docs/SECURITY.md`.

## Roadmap update rules

`docs/ROADMAP.md` should be updated when:

- iteration status changes;
- goal/scope/deliverable changes;
- DoD changes;
- artifact contract changes;
- checks change;
- stage wording becomes outdated.

Do not update ROADMAP for tiny internal implementation details that do not affect iteration contract.

## Docs update rules

Update docs when the contract changes.

Usually check whether these files need updates:

- `docs/ROADMAP.md`
- `docs/DEV_GUIDE.md`
- `docs/SECURITY.md`
- `README.ru.md`

Update them if one of the following changed:

- config contract;
- runtime behavior;
- entrypoint usage;
- module contract;
- artifact structure;
- verification flow;
- security expectations.

## PR rules

Each PR should include:

- summary;
- related issue;
- iteration reference;
- scope;
- changes;
- tests;
- artifacts;
- checklist;
- notes.

Good rule:

- **Issue** explains the task.
- **PR** explains the delivery.
- **ROADMAP** explains the iteration-level target.

## Issue rules

Each issue should stay lightweight but useful.

It should answer:

- what needs to be done;
- why it matters;
- what is in scope;
- what result is expected;
- how it should be verified.

Do not turn the issue into a full implementation diary.

## Comments and evidence

Issue comments are allowed and useful for:

- intermediate findings;
- links to runs and artifacts;
- quick verification notes;
- clarifications.

But comments do not replace the PR.

Main evidence for closing work should stay in the PR.

## KISS rule for process

To keep the process simple:

- one task = one issue when practical;
- one iteration item = one focused PR when practical;
- do not mix several roadmap iterations in one PR;
- do not require documents that nobody will read;
- do not add process steps unless they help quality or safety.

## Typical developer flow

A normal development cycle in `beeagent` looks like this:

1. open `docs/ROADMAP.md`
2. select the current iteration
3. create or refine the issue
4. create a branch
5. implement the change
6. run required tests/checks
7. inspect logs and artifacts
8. update docs if needed
9. open PR
10. merge after review and DoD satisfaction

## Review checklist mindset

A reviewer should be able to answer:

- does this stay inside the iteration scope?
- is config still the source of truth?
- are required keys validated fail-fast?
- are logs/artifacts understandable?
- are secrets safe?
- are authority boundaries still explicit?
- are tests/checks appropriate for the risk?
- is the solution simple enough?
- is the PR enough to prove readiness?

## Summary

`beeagent` uses a lightweight but real SDLC.

The key discipline is:

- small scoped iterations;
- config as source of truth;
- fail-fast validation;
- reproducible artifacts;
- understandable logs;
- evidence in PR;
- security checks only where they actually matter.