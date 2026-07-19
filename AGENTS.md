# AGENTS.md — BeeAgent repository guidance

## Purpose

This file contains stable repository-wide instructions for AI coding and review agents working in `beeagent`.

Keep task-specific requirements in the approved Issue. Keep detailed workflows in `.agents/skills/`.

## Instruction precedence

Use this order:

1. Current explicit task instructions and approved Issue acceptance criteria.
2. This `AGENTS.md`.
3. Current repository contracts and project documentation.
4. Implementation reports, PR comments and previous prompts as supporting evidence only.

When instructions conflict materially, stop and report the conflict. Do not silently choose a broader scope.

The current worktree, code, diff, tests and artifacts take precedence over stale implementation reports.

## Mandatory reading

Before changing or reviewing the repository, read:

* `AGENTS.md`;
* the relevant section of `docs/ROADMAP.md`;
* `docs/SDLC.md`;
* `docs/SECURITY.md`;
* `docs/DEV_GUIDE.md`;
* `README.ru.md`;
* the approved Issue or its acceptance criteria;
* `.github/ISSUE_TEMPLATE/issue.md` when preparing an Issue;
* `.github/PULL_REQUEST_TEMPLATE/pr.md` when preparing or closing a PR.

Read additional documents when relevant:

* architecture or platform contract:

  * `docs/ARCHITECTURE.md`;
  * `docs/SPEC.md`;
* Web UI or API:

  * `docs/WEB_UI.md`;
  * `docs/product/ui_roadmap.md`;
  * `config/beeui.yml`;
* ROP integration:

  * the related `beeagent-rop` ROADMAP;
  * only public `beeagent-rop` contracts used by BeeAgent;
* runtime or config:

  * `config/start.py`;
  * `config/settings.yml`;
  * `src/beeagent_module/core/settings.py`;
* dependencies:

  * `pyproject.toml`;
  * `uv.lock`.

When a tool omits or truncates a file, continue reading from the returned cursor until the complete file has been read.

Do not assume that a ROADMAP status proves implementation. Compare ROADMAP statements with current code, contracts, artifacts and tests.

## Architecture boundary

Canonical flow:

```text
UI / transport
→ BeeAgent core
→ domain module
→ capability / MCP / n8n / connector
→ external system
```

BeeAgent owns:

* orchestration;
* run, session and job state;
* config loading and validation;
* module contract and registry;
* artifact lifecycle;
* capability boundary;
* approvals, authority and policy;
* transport and UI integration;
* shared provider execution;
* logs and observability.

Domain modules such as `beeagent-rop` own:

* domain models and taxonomy;
* client-specific classification;
* business rules;
* duplicate resolution;
* domain fixtures;
* domain summary and recommendation semantics;
* bounded domain AI contracts.

BeeUI owns generic rendering, layout, session and UI primitives.

BeeAgent adapters and read-models decide what product data BeeUI receives.

Do not:

* move ROP or Welding business rules into BeeAgent core;
* import private `beeagent-rop` internals;
* create a second runtime inside a module;
* put orchestration or business decisions in UI templates;
* bypass the capability or authority boundary;
* add external mutations without explicit Issue scope.

## Sources of truth

Use these sources of truth:

* runtime configuration:

  * `config/settings.yml`;
* UI navigation, pages, tabs and locale:

  * `config/beeui.yml`;
* AI prompts:

  * `config/prompts.yml`;
* required config validation:

  * `src/beeagent_module/core/settings.py`;
* runtime evidence:

  * bounded artifacts under `storage/`;
* domain classification semantics:

  * public domain-module contracts and tested fixtures;
* iteration scope:

  * approved Issue aligned with the current ROADMAP.

Rules:

* no hidden defaults for required behavior;
* no second source of truth;
* new required config keys must be explicit and fail fast;
* CLI overrides remain in-memory unless the Issue explicitly changes that contract;
* artifacts are evidence and read-model inputs, not editable configuration;
* real secrets live only in environment variables.

## Development workflow

Use:

```text
ROADMAP
→ Issue
→ branch
→ code
→ tests
→ artifacts
→ PR
→ merge
```

Rules:

* one task should use one focused branch and one PR;
* do not merge a feature branch into local `main` before PR review;
* process/tooling work does not need a numbered product iteration unless it delivers a product increment;
* verify the actual branch and dirty state before work;
* do not carry unrelated dirty files into the task;
* stage only intended files;
* do not use `git add .` when a bounded file list is known;
* after an approved squash merge, update local `main` before deleting the local branch.

Use:

* `.agents/skills/beeagent-plan-iteration/SKILL.md` when the next iteration or Issue still needs to be selected or refined;
* `.agents/skills/beeagent-review-and-close/SKILL.md` after implementation is ready for independent review.

When an Issue is already approved, skip iteration planning and proceed directly to implementation.

## Implementation rules

* Stay strictly inside the approved Issue.
* Prefer the smallest complete solution.
* Follow KISS.
* Do not perform unrelated refactors.
* Do not add speculative architecture for future work.
* Do not create a new abstraction, service, helper or test file without a concrete need.
* Preserve backward compatibility unless the Issue explicitly declares a breaking change.
* Do not remove or weaken existing validation without a documented reason.
* Do not duplicate existing logic.
* Follow PEP 8.
* Do not add new code comments unless the Issue explicitly requires them.
* Keep logs, runtime messages, JSON fields and artifact fields in English.
* Keep logs understandable and free of secrets or unnecessary customer data.
* Use bounded and sanitized representations of untrusted inputs.
* Keep read-only, draft-only and execution-capable authority explicit.
* Do not modify `pyproject.toml.version` in ordinary feature, fix, docs or chore work.
* Do not touch release metadata unless the Issue is explicitly about a release.
* Change dependencies only when required by the Issue.
* When dependencies change, update both dependency declarations and `uv.lock`.
* When dependencies do not change, do not modify `uv.lock`.

## Documentation and contract rules

Update documentation when the change modifies:

* runtime behavior;
* config contract;
* CLI or entrypoint;
* module or capability contract;
* API or UI contract;
* artifact shape;
* authority or security boundary.

Do not update unrelated documents merely to increase the file count.

When JSON, JSONL, TSV or API fields change:

* document the source of truth;
* preserve existing fields when backward compatibility is required;
* provide an example shape where useful;
* update tests that validate the public contract.

## Verification

First determine the change level using `docs/SDLC.md` and `docs/SECURITY.md`:

* `low-risk`;
* `runtime-risk`;
* `security-sensitive`.

Base repository checks:

```bash
git status --short
git diff --check
```

For code or runtime changes, run targeted tests and:

```bash
uv run pytest -q
```

Run smoke, log and artifact checks only when the changed behavior requires them.

Apply security checks proportionally:

* SAST mindset review for code and runtime changes;
* SCA when dependencies change;
* DAST-style checks for network-facing routes or connectors;
* targeted malformed-input tests or fuzzing for parsers when justified;
* IAST only when the risk and available runtime justify it.

For a docs/process-only change:

* do not create artificial runtime tests;
* inspect paths, Markdown/frontmatter and repository diff;
* `git diff --check` is required;
* the full test suite may be run as regression evidence but does not justify adding test-only scaffolding.

Never claim that a check passed unless its exact command and result are available.

When operating through Bee Dev MCP, remember that it is read-only. It can inspect worktrees, files and diffs, but it cannot execute tests or modify the repository.

## Security rules

* Treat email, attachment metadata, restored artifacts, API payloads, config and CLI input as untrusted.
* Never expose secrets, auth headers, tokens, passwords or full environment dumps.
* Do not store raw `.eml`, raw MIME, attachment bytes or unrestricted external payloads unless a security-reviewed Issue explicitly requires it.
* Validate user-controlled identifiers and paths.
* Keep artifact access allowlisted and bounded.
* Do not introduce CRM, mailbox, Bitrix or other external mutations through read-only routes.
* AI output is untrusted input and must not create execution authority.
* Preserve deterministic and manual-review safety paths when provider execution fails.

## Review rules

Review the actual target worktree relative to its declared base branch.

Inspect:

* committed changes;
* staged changes;
* unstaged changes;
* untracked files;
* deleted files;
* renamed files;
* complete contents of changed files;
* relevant project contracts;
* supplied test, log and artifact evidence.

Prioritize real blockers:

* missing acceptance criteria;
* incorrect behavior;
* security or authority violation;
* core/module/UI boundary violation;
* broken config or source-of-truth contract;
* unsafe path, parsing or serialization behavior;
* incompatible API or artifact contract;
* missing required verification;
* unrelated scope that would enter the PR;
* unintended version or dependency changes.

Do not turn optional polish, naming preference or speculative follow-up into a blocker.

Perform one complete review pass and consolidate all blockers into one correction request.

On re-review:

* verify all previous findings;
* verify the original acceptance criteria;
* check regressions caused by the correction;
* do not open a new round of unrelated optional improvements.

Use only one final verdict:

```text
APPROVED
```

or:

```text
CHANGES REQUIRED
```

When approved, explicitly state:

```text
Правки не нужны.
```

Then prepare the PR body from the repository template.

## Required implementation report

The implementation agent must provide:

1. files read;
2. change level;
3. source of truth after change;
4. core/module/UI boundary assessment;
5. changed files;
6. exact tests and command results;
7. smoke results when applicable;
8. logs and artifacts checked;
9. security review;
10. known limitations;
11. confirmation:

```text
version not changed
```

Do not substitute a narrative summary for exact verification evidence.
