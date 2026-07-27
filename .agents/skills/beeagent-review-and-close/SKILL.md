---
name: beeagent-review-and-close
description: Perform a complete read-only BeeAgent review against an approved Issue, using the exact worktree and base branch, then return one consolidated verdict and PR close package.
---

# BeeAgent review and close workflow

## Purpose

Use this workflow after implementation is complete and the user has supplied:

* an approved Issue or acceptance criteria;
* implementation evidence;
* exact worktree information;
* expected branch and base branch.

This workflow is read-only.

Do not:

* modify files;
* run repository commands;
* switch branches;
* create commits;
* push;
* create or merge a PR.

## Required inputs

Obtain:

* project;
* expected worktree path;
* expected branch;
* expected base branch;
* mode;
* full Issue;
* implementation evidence;
* related repository context when explicitly requested;
* previous blocking findings for re-review.

## Working contract

Read every declared file completely before forming findings. Keep a file inventory; when another file becomes necessary, add it to the inventory and read it completely before evaluating it.

Map the review to the supplied current roadmap iteration and evaluate only its approved scope. Determine `low-risk`, `runtime-risk` or `security-sensitive` from the Issue and changed files, and derive required evidence from `docs/SDLC.md` and `docs/SECURITY.md`.

Require the smallest complete KISS change. Treat unrelated refactoring, formatter churn, newly introduced first-party production/test comments, explanatory docstrings, `TODO`, `FIXME`, `NOTE` or decorative separators as blocking findings. Preserve required license, provenance and security annotations and unrelated existing comments.

Require proportional tests for acceptance criteria and public behavior, existing test files and helpers unless a new one is demonstrably necessary, and preservation of every existing check unless an explicit task-specific reason authorizes its removal. Confirm client-specific and domain business logic remain outside BeeAgent core; report when requested work belongs to a domain module.

Before returning a verdict, inspect the final diff for prohibited comments and unrelated formatting.

The worktree path, MCP target and Git branch are separate identifiers.

## Phase 1 — Resolve the exact target

1. Call `list_worktrees` for the project.
2. Find the entry whose `path` exactly matches the expected worktree path.
3. Use the returned MCP `target`.
4. Call `get_project_context` for that target and mode.
5. Verify:

   * project;
   * path;
   * branch;
   * HEAD;
   * dirty state.

If the exact path or mandatory metadata is unavailable, return `ПРОВЕРКА НЕ ЗАВЕРШЕНА`.

If the project or branch differs from the expected value, report expected and actual values and do not issue a code verdict.

Do not infer an MCP target from a branch name.

Do not substitute the main worktree for a requested feature worktree.

## Phase 2 — Read the complete manifest and diff

### Review manifest

1. Call `get_review_manifest` with an empty cursor.
2. Append each returned `content` page.
3. Continue with the exact `next_cursor` while `has_more=true`.
4. Require the same `snapshot_id` on every page.
5. Parse the combined content as one JSON manifest.

Verify:

* project;
* target;
* branch;
* HEAD;
* expected base branch;
* dirty state;
* committed files;
* staged files;
* unstaged files;
* untracked files;
* deleted files;
* renamed files;
* omitted or redacted paths.

### Review diff

1. Call `get_review_bundle_page` with an empty cursor.
2. Append each returned `content` page.
3. Continue with the exact `next_cursor` while `has_more=true`.
4. Require the same snapshot as the manifest.
5. Finish only when:

   * `has_more=false`;
   * `next_cursor=null`;
   * `truncated=false`.

Do not use compatibility `get_review_bundle` as a substitute.

If pagination fails, the snapshot changes or the diff is truncated, return `ПРОВЕРКА НЕ ЗАВЕРШЕНА`.

The manifest is the authoritative file inventory. The complete diff is evidence of the changes.

## Phase 3 — Resolve review instructions

Read `AGENTS.md` and this skill from the primary target.

If they are absent because the feature worktree predates their introduction, use the explicitly supplied canonical `beeagent/main` worktree:

1. resolve it through `list_worktrees`;

2. verify its exact path and `main` branch through `get_project_context`;

3. read:

   * `AGENTS.md`;
   * `.agents/skills/beeagent-review-and-close/SKILL.md`;

4. use them only as review instructions;

5. continue reviewing code exclusively from the original target.

Their absence from a legacy feature worktree is not a finding.

Do not silently choose another instruction source.

## Phase 4 — Read required files

Use `read_project_file`.

When it returns `next_line` or `next_column`, continue with those exact values until both are null.

Read completely:

* `AGENTS.md`;
* this skill;
* `.github/PULL_REQUEST_TEMPLATE/pr.md`;
* relevant ROADMAP section;
* `docs/SDLC.md`;
* `docs/SECURITY.md`;
* relevant architecture, UI, API, configuration and module contracts;
* every changed and untracked text file;
* relevant tests;
* directly related unchanged imports, schemas, configuration, contracts and callers.

For deleted files:

* inspect the complete diff;
* inspect affected current imports, contracts and callers.

For renamed files:

* inspect old and new paths in the manifest and diff;
* read the destination file completely;
* verify updated references.

If a required relevant file is omitted, redacted or unreadable through the available safe MCP interface, return `ПРОВЕРКА НЕ ЗАВЕРШЕНА`.

Do not issue a verdict from partial file content.

## Phase 5 — Related repository context

When a related repository is explicitly supplied:

1. resolve its exact path through `list_worktrees`;
2. verify its expected branch through `get_project_context`;
3. read only the public contracts required to review the primary target;
4. do not perform an independent review of the related repository;
5. do not include unrelated related-repository state in the primary verdict.

If the primary implementation depends on code or a public contract absent from the expected related branch, report a blocking cross-repository dependency.

For BeeAgent UI work:

* BeeAgent owns product adapters, read-models and product semantics.
* BeeUI owns generic rendering and reusable UI primitives.
* Domain business rules belong in the domain module.
* Product-specific behavior must not be added to generic BeeUI components.

## Phase 6 — Evidence and acceptance criteria

Follow the instruction and evidence precedence defined in `AGENTS.md`.

The implementation report is supporting evidence, not the source of truth.

Bee Dev MCP cannot execute tests.

When the approved Issue has no dependency change, do not inspect, regenerate, modify or separately validate `uv.lock`. When it explicitly requires a dependency change, inspect only the necessary minimal registry lock diff. Never request, evaluate or treat `uv lock --check` or any dedicated lockfile validation as merge evidence, and do not treat unrelated lock noise as an independent finding.

Treat supplied command output as reported evidence and never claim MCP ran the commands.

Evaluate every acceptance criterion as:

* satisfied;
* partially satisfied;
* not satisfied;
* not verifiable;
* not applicable.

Check as applicable:

* observable behavior;
* runtime compatibility;
* UI and API contracts;
* configuration source of truth;
* fail-fast validation;
* architecture ownership;
* backward compatibility;
* artifact schema;
* authority and security boundaries;
* documentation;
* required tests, smoke, logs and artifacts;
* version declarations.

`Not verifiable` is a blocker only when the Issue, SDLC or security rules require that evidence for merge readiness.

## Phase 7 — Blocking findings

A blocker must affect readiness of the current Issue.

Examples:

* unmet acceptance criteria;
* incorrect or unsafe behavior;
* security or authority bypass;
* core, module or UI ownership violation;
* conflicting source of truth;
* missing fail-fast validation;
* incompatible public contract;
* missing required verification;
* unrelated changes entering the PR;
* unintended dependency or version changes;
* documentation contradicting public behavior;
* missing required cross-repository dependency.
* newly introduced first-party production/test comments, explanatory docstrings, `TODO`, `FIXME`, `NOTE` or decorative separators;
* unrelated formatter churn or refactoring.

Do not make blockers from:

* optional polish;
* personal style preferences;
* speculative future architecture;
* unrelated cleanup;
* requirements absent from the Issue;
* MCP limitations themselves.

Find and consolidate all real blockers before returning the verdict.

## Phase 8 — Completeness gate

Before issuing a code verdict, confirm:

* exact target and branch verified;
* expected base branch verified;
* complete manifest consumed;
* complete non-truncated diff consumed;
* manifest and diff use the same snapshot;
* changed and untracked files fully inventoried;
* required changed files fully read;
* deleted and renamed paths inspected;
* relevant unchanged contracts read;
* requested related-repository context evaluated;
* every acceptance criterion evaluated;
* verification evidence evaluated;
* version scope checked;
* all blockers consolidated.

If any mandatory inspection remains incomplete, return:

```text
ПРОВЕРКА НЕ ЗАВЕРШЕНА
```

Include:

* completed inspection;
* exact missing tool, metadata, file or continuation;
* reason no code verdict was issued.

Do not include:

* implementation findings based on partial inspection;
* correction prompt;
* PR body;
* code verdict.

## Phase 9 — Verdict

Return exactly one completed-review verdict:

```text
ОДОБРЕНО ДЛЯ PR
```

or:

```text
ТРЕБУЮТСЯ ИЗМЕНЕНИЯ
```

### ОДОБРЕНО ДЛЯ PR

Use only when no blockers remain.

State exactly:

```text
Правки не нужны.
```

Then provide:

1. acceptance-criteria coverage;
2. files reviewed;
3. supplied verification evidence;
4. non-blocking limitations;
5. reviewed branch;
6. recommended squash commit;
7. completed PR body using the repository template;
8. merge readiness.

Do not claim MCP ran tests.

### ТРЕБУЮТСЯ ИЗМЕНЕНИЯ

Provide every blocker in this format:

```text
### <Finding title>

Файл:
`path/to/file`

Было:
<current incorrect behavior>

Стало:
<required behavior within the Issue>

Почему:
<evidence and impact>
```

Then provide one consolidated correction prompt.

Do not prepare a final PR body while blockers remain.

## Consolidated correction prompt

The correction prompt is an executor prompt for Copilot or Codex, not a continuation of the Bee Dev MCP review.

Select and name the executor:

* Copilot for localized, clearly specified corrections;
* Codex for broad diagnosis, multi-subsystem changes or security-sensitive corrections.

The prompt must authorize the executor to modify files and run repository checks in the exact target worktree using its available local tools.

Do not copy reviewer-only restrictions into the correction prompt, including:

* `Use only Bee Dev MCP`;
* read-only mode;
* MCP target identifiers;
* review mode.

The correction prompt must be concise, complete and ready for direct use by Copilot or Codex.

Use one controlled structure for every correction prompt:

```text
Executor: <Copilot or Codex>

Project: beeagent
Instruction worktree: <exact instruction worktree>
Target worktree: <exact target worktree>
Expected branch: <feature branch>
Base branch: <base branch>

Read instructions from:

- <instruction worktree>/AGENTS.md
- <instruction worktree>/.agents/skills/beeagent-verify-and-correct/SKILL.md

Use the instruction worktree only for reading instructions.
Inspect, modify and verify files only in the target worktree.
Do not modify the instruction worktree.

Fix only the blocking findings from the current final review.
Preserve all already working behavior within the approved Issue.

For every blocker use:

### <Finding title>

Файл:
`<path>`

Было:
<current incorrect behavior>

Стало:
<exact required behavior>

Почему:
<acceptance criterion, contract violation or concrete impact>

Requirements:

- make only minimal in-scope corrections;
- follow KISS and PEP 8;
- reuse existing configuration, contracts, helpers and parameters;
- do not hardcode values that belong to an existing source of truth;
- do not add unnecessary defaults, abstractions or comments;
- do not duplicate existing logic;
- use existing test files and helpers where practical;
- do not treat unrelated `uv.lock` noise as a finding;
- do not report `except json_mod.JSONDecodeError, OSError:` as invalid solely because additional parentheses are absent;
- do not add optional polish, preventive closing patches or another review round “just in case”.

Required verification:

- targeted regression tests for every blocker;
- full tests required by the actual change level;
- applicable entrypoint, route or runtime smoke;
- applicable security and contract checks;
- `git diff --check`;
- dependency and version verification;
- unrelated-file check.

Return one consolidated report according to `beeagent-verify-and-correct`.

For every implemented correction report:

Файл → Было → Стало → Почему

Include exact changed files, commands and results, security review, dependency status, artifact/storage impact and known limitations.

End with:

version not changed

Do not commit, push, create or update a PR, or merge.
```

The prompt must include every blocking finding from the completed review.

Do not copy the full Issue, the full review report or stable repository rules into the correction prompt.

Do not introduce requirements, cleanup or improvements that are not necessary to close the current blockers.

## Re-review

For re-review:

1. obtain a new complete manifest and paginated diff;
2. verify the same path, branch and base;
3. verify every previous blocker;
4. evaluate the original acceptance criteria again;
5. inspect regressions introduced by corrections;
6. return `ОДОБРЕНО ДЛЯ PR` or only the remaining blockers.

Do not introduce unrelated optional findings.

## Output format

For a completed review:

1. `Verdict`
2. `Blocking findings`
3. `Acceptance Criteria coverage`
4. `Files reviewed`
5. `Verification evidence`
6. `Unverified limitations`
7. `Close decision`
8. `PR body` when approved
9. `Consolidated correction prompt` when changes are required

For incomplete inspection:

1. `ПРОВЕРКА НЕ ЗАВЕРШЕНА`
2. `Completed inspection`
3. `Missing inspection data`
4. `Reason no code verdict was issued`
