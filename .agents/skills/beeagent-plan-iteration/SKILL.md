---
name: beeagent-plan-iteration
description: Inspect the current BeeAgent implementation through Bee Dev MCP, validate the necessity and repository ownership of a bounded task, select and reconcile the relevant roadmap, and prepare a copy-ready iteration or standalone task plus complete Issues without modifying repositories.
---

# BeeAgent iteration planning workflow

## Purpose

Use this workflow when:

* the next BeeAgent iteration is not yet approved;
* an existing roadmap item must be validated or refined;
* a proposed task must be checked against the current implementation;
* an Issue must be prepared from the current repository state;
* BeeAgent, BeeUI or domain-module contracts require alignment.

Do not use this workflow when a complete Issue has already been approved.

This workflow is read-only.

Use only Bee Dev MCP for repository inspection.

Do not:

* modify files;
* switch branches;
* run shell or Git commands;
* run tests;
* create commits;
* prepare implementation or verification prompts.

## Required inputs

The external prompt `.agents/prompts/01-planning.md` passes:

* `MAIN_WORKTREE` — absolute path to the primary repository worktree;
* `MODE` — Bee Dev MCP context mode; pass it unchanged to applicable MCP calls;
* `ROADMAP_CONTEXT` — known iteration, proposed standalone task or `none`;
* `TASK_OR_IDEA` — proposed work;
* `CONTEXT_OR_NONE` — additional context or `none`;
* `ADDITIONAL_PROJECTS_OR_NONE` — related repositories or `none`.

The external prompt also declares the expected project, branch and base branch.

Treat repository paths, project names and expected branches as exact input values.

## ROADMAP_CONTEXT semantics

Handle three variants.

### Variant A — Known numbered iteration

Examples:

```text
Iteration 16 in docs/ROADMAP.md
```

```text
Iteration UI-8.2 in docs/product/ui_roadmap.md
```

This is a user-supplied iteration reference that must be validated.

It may describe:

* an existing roadmap item;
* a proposed next item that has not yet been inserted.

Validate:

* whether the roadmap file exists;
* whether the roadmap file is correct for the task type;
* if the iteration exists, its status and current scope;
* if it does not exist, whether its number is unique and valid at the intended insertion point;
* whether the proposed stage and scope match the task;
* whether the task is already implemented or covered elsewhere.

The absence of a proposed next iteration from the roadmap is not itself an error.

If the reference is valid, use it.

If it is stale, duplicated, already completed, assigned to the wrong roadmap or otherwise inconsistent, explain the correction and select the correct roadmap, stage and iteration number.

### Variant B — Proposed standalone task

Example:

```text
Standalone Fix outside a numbered iteration; validate against current docs/ROADMAP.md
```

Validate that the task is genuinely small enough for standalone handling.

If it creates a substantial product, runtime, contract, artifact, integration or workflow increment, reject the standalone classification and propose a numbered iteration.

### Variant C — No known iteration

Canonical value:

```text
none
```

Determine independently:

* whether the task needs a numbered iteration;
* which roadmap is primary;
* which stage fits;
* what iteration number should be used;
* where the item belongs;
* whether an existing item should be reused or refined instead.

Do not require the value `unknown`.

## Resolve repositories through Bee Dev MCP

Resolve `MAIN_WORKTREE` before planning.

1. Call `list_worktrees` for the declared project.
2. Match `MAIN_WORKTREE` by exact absolute `path`.
3. Use the MCP `target` returned for that exact path.
4. Call `get_project_context` with that target and `MODE`.
5. Verify:

   * project;
   * path;
   * branch;
   * HEAD;
   * dirty state.

For every entry in `ADDITIONAL_PROJECTS_OR_NONE`, repeat the same exact-path resolution.

Do not:

* infer an MCP target from a branch name;
* substitute the main worktree for another requested worktree;
* assume that two repositories share a branch or iteration number;
* execute shell or Git commands.

If the exact worktree cannot be resolved, report the mismatch and stop planning for that target.

If the actual branch differs from the declared expected branch, report both values and do not prepare an Issue for that implementation target.

A dirty worktree is not automatically a blocker.

When dirty changes affect relevant roadmaps, architecture, implementation, configuration or public contracts, inspect the current MCP snapshot and distinguish:

* committed state;
* unstaged changes;
* untracked files.

Do not treat uncommitted content as merged project history without explicitly identifying it.

## Complete reading rule

Repository inspection is incomplete while required content is truncated, omitted or has continuation metadata.

For files:

* continue with the exact `next_line` and `next_column`;
* finish only when both are null.

For review manifests or bundles, when required:

* continue with the exact `next_cursor`;
* finish only when `has_more=false`;
* require a consistent snapshot.

Read files listed as omitted directly through `read_project_file`.

Do not base a planning decision on partial or truncated content.

If mandatory repository information cannot be retrieved, return:

```text
PLANNING INCOMPLETE
```

Explain what could not be inspected.

Do not invent missing repository facts.

## Targeted discovery

Do not read every project file without purpose.

Use this sequence:

1. Identify the task type from `TASK_OR_IDEA`.
2. Inspect repository state and relevant dirty changes.
3. Identify candidate roadmap files.
4. Read the candidate roadmap sections completely.
5. Read repository guidance and process/security rules.
6. Read architecture and public contracts relevant to the task.
7. Inspect existing implementation and tests relevant to the proposal.
8. Compare completed, planned, future and deferred neighbouring items.
9. Inspect additional repositories only to the depth required by their declared role.
10. Determine whether companion repository changes are actually necessary.

Read at minimum in the primary repository:

* `AGENTS.md`;
* the selected primary roadmap;
* `docs/SDLC.md`;
* `docs/SECURITY.md`;
* `.github/ISSUE_TEMPLATE/issue.md`;
* relevant architecture or product-contract documents;
* relevant implementation and tests.

When UI scope is involved, normally also inspect:

* `docs/product/ui_roadmap.md`;
* `docs/WEB_UI.md`;
* relevant UI adapter, read-model, route and contract files.

For cross-repository tasks, also inspect:

* the companion repository roadmap;
* its repository guidance;
* its SDLC/security rules when present;
* relevant public integration contracts;
* relevant existing implementation and tests.

The presence of a repository in `ADDITIONAL_PROJECTS_OR_NONE` does not authorize planning changes there.

Treat additional repositories as read-only contract context unless a change is proven necessary.

## Primary roadmap selection

Explicitly distinguish:

* **Primary product roadmap** — where the product increment belongs;
* **Implementation repository** — where code or assets must change;
* **Companion roadmap** — another repository roadmap affected by a substantial reusable increment.

These may be different.

### BeeAgent core roadmap

Use:

```text
docs/ROADMAP.md
```

when the primary result concerns:

* BeeAgent core;
* orchestration or runtime;
* state or session handling;
* artifact lifecycle;
* module platform;
* capability boundaries;
* shared provider execution;
* transports as a system layer;
* general backend behavior;
* security or authority boundaries;
* general configuration and runtime contracts.

### BeeAgent UI roadmap

Use:

```text
docs/product/ui_roadmap.md
```

when the primary result concerns:

* BeeAgent Web Console;
* operator workflow;
* navigation;
* UI states;
* UI actions;
* runtime feedback in the interface;
* BeeUI adoption inside BeeAgent;
* BeeAgent-specific UI projections;
* dashboard, queue, event detail or filtering;
* ROP operator UI;
* other BeeAgent product UI increments.

### Domain-module roadmap

Use the relevant domain-module roadmap when the primary result concerns:

* domain taxonomy;
* classification;
* client-specific rules;
* domain fixtures;
* domain AI eligibility or validation;
* domain-specific recommendations or summaries;
* another contract owned by that module.

Do not move domain business logic into BeeAgent core.

### Companion project roadmap

A companion project such as BeeUI may own a reusable implementation required by a BeeAgent product increment.

In that case:

* the BeeAgent product requirement remains in the appropriate BeeAgent roadmap;
* the reusable companion implementation belongs to the companion repository;
* reference the companion roadmap only when that companion change is itself a substantial increment;
* create separate Issues for separate implementation repositories.

Do not transfer BeeAgent-specific product requirements into generic BeeUI merely because rendering code lives there.

Related repositories do not need matching iteration numbers.

Synchronize contracts, versions, dependencies and merge order — not numbering.

## Establish current state

Determine:

* the highest completed relevant iteration in the selected primary roadmap;
* neighbouring completed and planned items;
* current stage direction;
* relevant implementation that may be ahead of or behind roadmap wording;
* relevant domain-module status;
* relevant BeeUI status;
* active public contracts;
* known blockers and deferred limitations;
* whether `ROADMAP_CONTEXT` matches the current repository;
* whether the proposed task is already implemented;
* whether an existing planned item already covers it.

Report inconsistencies explicitly.

Do not silently rewrite completed history.

ROADMAP status alone does not prove implementation.

Compare roadmap wording with current:

* code;
* configuration;
* public contracts;
* tests;
* artifacts;
* documentation.

## Decide whether an iteration is justified

### Numbered iteration

A task normally requires a numbered iteration if it creates or substantially changes any of the following:

* runtime behavior;
* operator or user workflow;
* public or internal contract;
* API contract;
* artifact contract;
* security or authority boundary;
* cross-repository integration;
* reusable UI component or generic renderer;
* dependency or bundled static asset;
* locale or theme integration as part of new behavior;
* substantial state handling;
* new read-model;
* new action flow;
* new testable product capability;
* measurable architecture-debt elimination;
* a focused product increment that naturally requires an Issue and PR.

Documentation should normally accompany the technical increment rather than become a separate numbered iteration.

A focused UI improvement is not automatically a standalone task.

### Standalone task

Standalone is appropriate only for genuinely small work such as:

* typo correction;
* formatting;
* minor documentation correction;
* narrow local bugfix without contract change;
* housekeeping;
* small repository-maintenance work;
* a local change that creates no new behavior or architectural responsibility.

A standalone task never receives an iteration number.

If the user marks a substantial task as standalone, reject that classification and propose a numbered iteration.

If the user proposes an iteration for work already implemented or already covered, do not create a duplicate.

Choose one decision:

```text
reuse
refine
replace
insert
standalone
reject as unnecessary
```

Meanings:

* `reuse` — an existing item already covers the task without material changes;
* `refine` — an existing item should be clarified or bounded;
* `replace` — stale future scope should be replaced by the current requirement;
* `insert` — a new numbered item is justified;
* `standalone` — the task is truly outside numbered product flow;
* `reject as unnecessary` — no implementation task is justified.

Explicitly justify the selected decision.

### Approval criteria

Approve a numbered iteration only when it:

* closes a current gap;
* is not already implemented;
* has one coherent deliverable;
* respects core, module and UI ownership;
* has observable acceptance criteria;
* uses current public contracts or explicitly records a required new contract;
* fits one focused PR or an explicitly coordinated set of repository PRs.

Reject or revise proposals that:

* duplicate existing behavior;
* mix independent features;
* move domain rules into BeeAgent core;
* move BeeAgent-specific product behavior into generic BeeUI;
* introduce speculative architecture;
* create a second source of truth;
* depend on an undefined contract without recording ownership and sequencing;
* combine unrelated repository changes in one Issue.

## Evaluate solution options

When more than one reasonable implementation boundary exists, provide no more than three concrete options.

For each option state:

* repository ownership;
* implementation outline;
* advantages;
* disadvantages;
* compatibility impact;
* dependency or sequencing impact.

Recommend one option using:

* KISS;
* current public contracts;
* smallest complete change;
* no duplicate source of truth;
* no speculative architecture;
* minimum cross-repository coupling.

Do not create artificial alternatives.

If only one valid solution exists, state that directly.

## Roadmap synchronization

For every relevant roadmap or contract difference, classify it as:

* synchronized;
* intentional sequencing difference;
* stale documentation;
* blocking contract gap;
* separate follow-up.

When another repository requires changes:

* define the public contract;
* assign ownership;
* identify dependency direction;
* identify implementation and merge order;
* keep each repository in its own branch, worktree, Issue and PR.

Do not force equal iteration numbers across repositories.

## Roadmap reconciliation

Before creating a new iteration:

1. Identify neighbouring `DONE`, `PLANNED`, `FUTURE` and `DEFERRED` items.
2. Check whether an existing item already covers the proposed scope.
3. Detect stale, duplicated or contradictory future scope.
4. Determine the correct stage.
5. Determine the correct insertion position.
6. Verify iteration ID uniqueness.
7. Check references and dependencies to affected items.
8. Decide whether any future items must be removed, refined or renumbered.

Do not automatically append a new iteration to the end of the file.

Do not treat the visually highest number as the sole source of truth.

Do not reuse a retired iteration ID when doing so would create reference drift.

## Iteration numbering

Use minimally disruptive numbering.

Rules:

1. Never renumber `DONE` history.
2. Never change completed iteration IDs.
3. For a direct continuation of an existing increment, a decimal follow-up such as `UI-8.2` may be used when it preserves logical grouping and avoids unnecessary renumbering.
4. Do not force decimal numbering. Use the next available whole number when the task is an independent product increment.
5. A standalone task never receives an iteration number.
6. If renumbering is necessary, change only not-yet-completed items:

   * `PLANNED`;
   * `FUTURE`;
   * `DEFERRED`.
7. Prefer retiring a stale future ID with a short note over mass renumbering when existing references may already use that ID.
8. No duplicate iteration IDs may remain.
9. Show the exact removal, retirement or renumbering map when roadmap changes are required.

Example:

```text
UI-13 → retired because its auth scope was already delivered by UI-7
UI-16 (second occurrence) → UI-17
```

The example is illustrative only.

Use actual repository evidence for the final decision.

## Cross-repository planning

If a task requires changes in more than one repository:

* define separate implementation targets;
* create one complete Issue per implementation repository;
* do not combine independent repository implementations in one Issue;
* specify dependencies;
* specify implementation and merge order;
* identify prerequisite and dependent Issues;
* specify the intended worktree or repository for every Issue.

Use this rule:

```text
one implementation repository
= one Issue
= one target worktree
= one feature branch
= one PR
```

A single product iteration may therefore require multiple coordinated Issues.

The prompt:

```text
.agents/prompts/02-implementation-tests.md
```

must be run separately for each Issue and its corresponding target worktree.

One run of `02-implementation-tests.md` serves exactly one implementation target.

Do not plan companion changes merely because a companion repository was supplied.

Prove that the existing public contract is insufficient before assigning a companion implementation.

## Implementation plan

For each implementation target, specify:

* repository;
* primary responsibility;
* current implementation to reuse;
* files or layers likely to change, based on inspected structure;
* contracts to add or change;
* configuration impact;
* dependency impact;
* expected artifacts or outputs;
* backward-compatibility requirements;
* security and authority constraints;
* tests;
* smoke checks;
* documentation;
* implementation order;
* completion criteria.

Do not invent exact file names without confirming them through repository inspection.

When an exact file is uncertain, identify the confirmed layer or component and mark the file location as an implementation detail to verify.

The plan must be concrete enough for the next workflow to prepare implementation and verification prompts.

## Define the iteration or standalone task

Provide the planning result in Russian.

### Numbered iteration

Include:

* iteration number and title;
* exact roadmap file;
* stage;
* status — always `PLANNED`;
* goal;
* why the task is needed now;
* dependencies;
* included scope;
* excluded scope;
* deliverable;
* source of truth;
* repository ownership;
* configuration and contract impact;
* expected artifacts or outputs;
* change level;
* required checks;
* Definition of Done.

Also produce a copy-ready roadmap fragment that:

* uses the exact selected iteration number;
* identifies the correct stage and insertion point;
* matches neighbouring roadmap structure;
* matches the roadmap language and heading style;
* contains enough detail for a subsequent Issue;
* includes scope, deliverables, contracts, security, tests, documentation and acceptance criteria;
* does not create speculative future architecture.

The main iteration content must be in Russian.

Section headings may remain in English when that matches the local roadmap style.

### Standalone task

Do not invent an iteration number.

Include the relevant fields:

* title;
* classification as standalone;
* reason it is outside numbered product flow;
* included and excluded scope;
* deliverable;
* repository ownership;
* contract or configuration impact;
* change level;
* required checks;
* Definition of Done.

Do not produce a fake roadmap fragment for a standalone task.

### Reuse, refine, replace or reject

When the decision is not `insert`:

* identify the exact existing roadmap item, if any;
* explain what must be reused, refined or replaced;
* provide a copy-ready replacement fragment only when roadmap wording must change;
* do not generate a new iteration unnecessarily.

Documentation belongs inside a technical increment unless the task is genuinely documentation-only and standalone.

## Prepare complete Issues

For every implementation target, produce a complete copy-ready Issue in English.

Use the target repository’s Issue template when available.

For BeeAgent, preserve the structure of:

```text
.github/ISSUE_TEMPLATE/issue.md
```

When the template mentions only `docs/ROADMAP.md`, adapt the Roadmap / iteration section in the generated Issue so it explicitly states the actual selected roadmap file.

Do not modify the template during planning.

Each Issue must include:

* title;
* summary;
* type;
* exact roadmap file;
* exact iteration or standalone classification;
* exact stage when applicable;
* repository scope;
* context and current limitation;
* expected behavior;
* included scope;
* excluded scope;
* deliverable;
* implementation requirements;
* source of truth;
* public contracts;
* configuration impact;
* artifact or output impact;
* security and authority constraints;
* backward compatibility;
* automated tests;
* smoke and runtime checks;
* documentation;
* acceptance criteria;
* dependencies;
* expected implementation evidence;
* Definition of Done.

Do not use vague requirements such as:

```text
implement as needed
update relevant tests
follow best practices
```

Requirements must be observable and testable.

The roadmap item and its Issue or Issues must be mutually consistent:

* Issues must not silently expand roadmap scope;
* roadmap scope must be represented in the Issues;
* acceptance criteria must align;
* repository ownership must align;
* dependency order must align;
* excluded scope must align.

When multiple Issues are needed, label them clearly by repository and implementation order.

## Execution complexity notes

Record only task-specific factors that may affect later executor selection, such as:

* cross-repository coordination;
* broad repository investigation;
* security-sensitive boundaries;
* dependency or release sequencing;
* migration or compatibility complexity.

Do not select Copilot or Codex.

Executor selection belongs to:

```text
.agents/prompts/02-implementation-tests.md
```

## Task-specific implementation constraints

Identify constraints that must be passed to implementation, such as:

* repository ownership;
* required public contract;
* merge order;
* compatibility requirements;
* source of truth;
* forbidden unrelated changes;
* dependency restrictions;
* artifact or configuration impact;
* authority restrictions;
* versioning restrictions.

Do not prepare an implementation prompt.

## Task-specific verification constraints

Define verification requirements derived from the task:

* change level;
* targeted automated scenarios;
* compatibility checks;
* route, CLI, package or runtime smoke;
* artifact checks;
* log checks;
* security checks required by the changed boundary;
* cross-repository contract checks;
* dependency and version checks;
* forbidden mutation or leakage checks.

Do not prepare a verification, correction or review prompt.

## Naming

For each implementation target, provide:

* repository;
* recommended branch name;
* recommended Conventional Commit title.

Use existing repository conventions.

Do not propose a version bump unless the task is explicitly about release or versioning.

For ordinary work, require:

```text
version not changed
```

## Phase boundary

This skill performs planning only.

Do not prepare:

* Copilot prompts;
* Codex prompts;
* implementation prompts;
* test-execution prompts;
* verification prompts;
* correction prompts;
* final-review prompts;
* PR bodies.

Implementation and verification prompt preparation belongs exclusively to:

```text
.agents/prompts/02-implementation-tests.md
```

Final read-only review belongs exclusively to:

```text
.agents/prompts/03-final-review.md
```

## Output format

Return these sections:

```text
## Executive verdict

## Repository state

## Current implementation and contracts

## Roadmap selection

## Roadmap reconciliation

## Necessity verdict

## Architecture and repository ownership

## Implementation plan

## Iteration numbering and insertion

## Copy-ready roadmap iteration or standalone task

## Copy-ready Issue
```

For multiple Issues, use:

```text
## Copy-ready Issues
```

Then return:

```text
## Implementation order

## Verification and security

## Branch and commit naming

## Planning handoff
```

Add this section only when needed:

```text
## Assumptions or blockers
```

### Section rules

For a numbered iteration, the section:

```text
## Copy-ready roadmap iteration or standalone task
```

must contain the complete copy-ready roadmap fragment.

For a standalone decision, it must contain the complete copy-ready standalone task and explicitly state that no roadmap insertion is required.

For `reuse`, `refine`, `replace` or `reject as unnecessary`, it must contain the exact applicable decision and any required replacement roadmap wording.

### Planning handoff

Return a short human-readable block:

```text
Primary product repository:
Primary roadmap:
Stage:
Iteration:
Decision:
Implementation targets:
Issue count:
Execution order:
Required separate prompt-02 runs:
Task-specific implementation constraints:
Task-specific verification constraints:
```

For standalone work, use:

```text
Iteration: none
```

For rejected work, state:

```text
Implementation targets: none
Issue count: 0
Required separate prompt-02 runs: 0
```

Do not create:

* YAML handoff files;
* JSON schemas;
* separate planning artifacts;
* automatic roadmap edits;
* automatic Issues;
* automatic branches or commits.

Do not modify or execute anything.
