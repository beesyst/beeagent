---
name: Issue
about: "Use title prefixes: Feature:, Fix:, Bug:, Docs:, Chore:, Idea:"
title: "Feature: <short title>"
labels: []
assignees: []
---

### Summary

One sentence: what needs to be done (or explored).

### Type

Select one primary type:

- [ ] Feature
- [ ] Fix
- [ ] Docs
- [ ] Chore
- [ ] Idea

### Roadmap / iteration

- Iteration:
- Stage:
- Goal from `docs/ROADMAP.md`:

If this is not tied to a roadmap iteration, explain why.

### Context

Why this matters. Links, screenshots, references.

Include:

- current problem / limitation;
- why now;
- related issue / PR / roadmap item / artifact if any.

### Scope

What is included / excluded.

**Included**

- ...
- ...

**Excluded**

- ...
- ...

### Deliverable

What should exist when this is done (behavior, file, doc, etc.).

Examples:

- new runtime behavior;
- updated config contract;
- updated module contract;
- new artifact in `storage/`;
- updated capability / integration behavior;
- updated transport/UI behavior;
- documentation update.

### Acceptance Criteria

What must be true for this task to be considered done.

- ...
- ...
- ...

Keep criteria observable and testable.

### Change level

Choose one:

- [ ] low-risk
- [ ] runtime-risk
- [ ] security-sensitive

> Use `docs/SDLC.md` / `docs/SECURITY.md` to classify the task.

### Config / Contract impact

Mark what is expected:

- [ ] no config or contract change expected
- [ ] `config/settings.yml` may change
- [ ] new required keys must be validated fail-fast
- [ ] module contract may change
- [ ] artifact contract may change
- [ ] capability / integration contract may change
- [ ] CLI/runtime/transport behavior may change
- [ ] docs update likely required

If known already, list affected keys/files/contracts:

- `...`
- `...`

### Tests

What must be checked:

**Automated**

- [ ] unit/integration tests
- [ ] `pytest -q`

**Smoke / runtime**

- [ ] smoke checks through expected entrypoint
- [ ] log verification
- [ ] artifact verification

**Quality / security**

Mark what is expected for this task:

- [ ] SAST
- [ ] SCA
- [ ] DAST
- [ ] IAST
- [ ] fuzzing
- [ ] some checks are not applicable

Describe the required scenarios briefly:

- ...
- ...
- ...

### Artifacts

What files / outputs should appear or be updated in tests, docs, integration outputs, or BeeAgent artifacts.

Examples:

- `logs/app.log`
- `tests/...`
- `docs/ROADMAP.md`
- `docs/ARCHITECTURE.md`
- `docs/SDLC.md`
- `docs/SECURITY.md`
- `storage/runs/<run_id>/...`
- `storage/artifacts/<run_id>/...`
- `storage/reports/...`
- `storage/interfaces/...` if integration/module diagnostics are affected

### Security notes

Fill if relevant:

- external connector involved:
- email / attachment input involved:
- file/path handling involved:
- dependency changes involved:
- serialization/parsing involved:
- module / capability boundary involved:

### Definition of Done

Task is done when:

- [ ] behavior is implemented within the declared scope
- [ ] expected entrypoint/runtime behavior works
- [ ] tests are green
- [ ] logs are understandable
- [ ] artifacts are created/updated and consistent if applicable
- [ ] no secrets leak into logs/artifacts
- [ ] checks required for this task by `docs/SDLC.md` / `docs/SECURITY.md` are completed
- [ ] docs are updated if contract/behavior/artifacts changed
- [ ] result is ready to be closed through PR

### Notes

Constraints, assumptions, extra links.

Use this section for:

- follow-up ideas;
- explicit non-goals;
- migration notes;
- reviewer hints;
- implementation constraints.
