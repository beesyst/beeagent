---
name: beeagent-plan-iteration
description: Inspect the current BeeAgent implementation through Bee Dev MCP, critically validate task necessity and repository ownership, reconcile the correct roadmap, and prepare a compact roadmap item or standalone task plus complete copy-ready Issues without modifying repositories.
---

# BeeAgent iteration planning workflow

## Purpose

Use this workflow when:

* a BeeAgent task or product idea has not yet been approved;
* an existing roadmap item must be validated, refined or replaced;
* a proposed iteration may be stale relative to current implementation;
* the next meaningful increment must be selected;
* ownership between BeeAgent, BeeUI and a domain module is unclear;
* coordinated repository changes may be required;
* a complete Issue must be prepared from repository evidence.

Do not use this workflow when a complete Issue has already been approved and the task is ready for `.agents/prompts/02-implementation-tests.md`.

Planning must determine:

* what exists now;
* what is actually missing;
* whether work is necessary now;
* whether the proposed solution is correct;
* which roadmap owns the increment;
* which repositories must change;
* what must remain excluded;
* what context prompt 02 needs.

This workflow is read-only.

Use only Bee Dev MCP for repository inspection.

Do not:

* modify files;
* switch branches;
* run shell or Git commands;
* run tests;
* create Issues, branches, commits or PRs;
* prepare implementation, verification, correction or review prompts;
* prepare PR bodies.

## Repository guidance

Read and follow `AGENTS.md`.

`AGENTS.md` owns stable repository-wide rules, including:

* Bee Dev MCP usage;
* exact target resolution;
* complete reading;
* architecture boundaries;
* sources of truth;
* implementation and security rules;
* verification policy;
* dependency and version restrictions.

Do not repeat all of `AGENTS.md`, `docs/SDLC.md` or `docs/SECURITY.md` in planning output or Issues.

This skill owns only:

* the planning decision algorithm;
* roadmap reconciliation;
* necessity and ownership decisions;
* roadmap and Issue output contracts;
* the planning handoff.

## Required inputs

The external prompt `.agents/prompts/01-planning.md` provides:

* `MAIN_WORKTREE`;
* `MODE`;
* `ROADMAP_CONTEXT`;
* `TASK_OR_IDEA`;
* `CONTEXT_OR_NONE`;
* `ADDITIONAL_PROJECTS_OR_NONE`;
* declared project;
* expected branch;
* base branch.

Treat paths, project names, branches, modes and repository roles as exact input values.

Pass `MODE` unchanged to applicable Bee Dev MCP calls.

Do not silently substitute another:

* worktree;
* repository;
* branch;
* roadmap;
* mode.

## Core planning rules

### Evidence before agreement

Treat the user’s task, roadmap reference and implementation reports as hypotheses.

Validate material assumptions against current:

* code;
* tests;
* configuration;
* public contracts;
* artifacts;
* routes and APIs;
* repository documentation;
* dirty changes.

Current repository files and contracts are authoritative.

Reports, screenshots and earlier planning outputs are supporting evidence only.

Do not automatically accept:

* the proposed iteration ID;
* the proposed roadmap or stage;
* the proposed repository;
* the proposed solution;
* the proposed urgency;
* the assumption that new work is required.

### Critical planning

Answer:

* What is the current behavior?
* What gap remains?
* Is it important now?
* Is it already implemented?
* Does another item cover it?
* Is the proposed repository correct?
* Is a smaller complete solution available?
* What must not be built?
* What should the project prioritize next?

When the user’s framing is wrong:

1. show the mismatch using repository evidence;
2. preserve the underlying product intent where possible;
3. correct roadmap, scope, numbering or ownership;
4. provide a usable corrected planning result.

### KISS

Recommend the smallest complete increment that closes the verified gap.

Avoid:

* optional polish;
* unrelated cleanup;
* broad refactoring;
* speculative architecture;
* unnecessary services or runtimes;
* second sources of truth;
* premature abstractions;
* unnecessary dependencies;
* unnecessary cross-repository changes;
* future work hidden inside current scope.

### Roadmap and Issue separation

The roadmap is a compact iteration-level contract.

The Issue is the detailed execution contract.

Do not turn the roadmap into a full implementation specification.

Do not make the Issue so vague that implementation must repeat planning.

## ROADMAP_CONTEXT

`ROADMAP_CONTEXT` is a hypothesis to validate, not an instruction to approve the referenced item.

### Known numbered iteration

Examples:

```
Iteration 16 in docs/ROADMAP.md

Iteration UI-8.4 in docs/product/ui_roadmap.md
```

Validate:

* roadmap existence and ownership;
* iteration existence and uniqueness;
* status and scope;
* neighbouring completed and unfinished items;
* implementation evidence;
* overlapping or duplicate scope;
* whether the task still belongs to that item.

If the referenced iteration is `DONE`:

* preserve completed history;
* never return it to `PLANNED`;
* never create another item with the same ID;
* determine whether the request is already implemented;
* use a new unique ID only for genuine follow-up work.

Use a decimal ID only for a direct continuation.

Use the next appropriate independent ID for independent work.

The absence of a proposed item from the roadmap is not itself an error.

### Proposed standalone task

Standalone is appropriate only when the work:

* is narrow and local;
* creates no substantial product capability;
* introduces no public contract;
* does not materially change runtime or operator workflow;
* does not create a new artifact or configuration contract;
* does not expand authority;
* does not require coordinated releases.

Reject standalone classification when the task creates a substantial product, runtime, integration or reusable UI increment.

### No known iteration

Canonical value:

```
none
```

Determine independently:

* whether work is required;
* whether an existing item should be reused;
* whether an unfinished item should be refined or replaced;
* whether a new iteration is justified;
* whether the task is standalone;
* which roadmap and stage own it;
* which unique ID fits;
* whether the idea should be deferred or rejected.

Do not require `unknown`.

## Resolve repositories

Resolve the exact primary worktree before planning.

For each declared repository:

1. call `list_worktrees`;
2. match the exact absolute worktree path;
3. use the returned MCP target;
4. call `get_project_context` with the supplied mode;
5. verify project, path, branch, HEAD and dirty state.

Do not:

* infer targets from branch names;
* substitute a main worktree;
* inspect a similar-looking unrelated worktree;
* assume repositories share numbering or release cadence.

If the primary worktree cannot be resolved, return:

```
PLANNING INCOMPLETE
```

Explain the mismatch and stop.

If a required additional repository cannot be resolved, return `PLANNING INCOMPLETE` when ownership or contract decisions depend on it.

If the actual branch differs from the expected branch:

* report both values;
* do not prepare an implementation Issue for that target;
* continue only with read-only analysis that remains valid.

## Dirty worktrees

A dirty worktree is not automatically a blocker.

When relevant, inspect and distinguish:

* committed state;
* staged changes;
* unstaged changes;
* untracked files;
* deleted or renamed files.

Do not present uncommitted work as merged history.

State when a conclusion depends on uncommitted content.

When dirty work overlaps the task:

* identify the overlap;
* avoid duplicate planning;
* decide whether the task should incorporate, replace or wait for it;
* add reconciliation constraints to the Issue when needed.

## Complete reading

Inspection is incomplete while mandatory content is truncated, omitted or paginated.

For files:

* continue with exact `next_line` and `next_column`;
* finish only when both are null.

For manifests and review bundles:

* continue with exact `next_cursor`;
* keep the same `snapshot_id`;
* finish only when `has_more=false`;
* treat `truncated=true` as incomplete.

Read relevant omitted files directly with `read_project_file`.

If mandatory evidence cannot be read, return:

```
PLANNING INCOMPLETE
```

State:

* what is missing;
* why it is required;
* which decision cannot be made.

Do not invent repository facts.

## Discovery workflow

Use this sequence:

1. parse `TASK_OR_IDEA`;
2. resolve declared worktrees;
3. inspect relevant dirty state;
4. identify candidate roadmaps;
5. read the referenced item and neighbours;
6. read repository guidance and applicable SDLC/security rules;
7. inspect relevant architecture and public contracts;
8. inspect current implementation and tests;
9. compare roadmap, code, contracts, tests and artifacts;
10. inspect additional repositories only as required;
11. identify the actual gap;
12. determine roadmap and repository ownership;
13. determine whether companion changes are necessary;
14. assess necessity and timing;
15. choose the planning decision;
16. prepare roadmap output, Issues and handoff.

Do not read repositories indiscriminately.

## Required inspection

Read at minimum in the primary repository:

* `AGENTS.md`;
* the candidate roadmap and neighbouring items;
* `docs/SDLC.md`;
* `docs/SECURITY.md`;
* `.github/ISSUE_TEMPLATE/issue.md`;
* relevant architecture or contract documentation;
* relevant implementation;
* relevant tests.

Read as applicable:

* `README.ru.md`;
* `docs/ARCHITECTURE.md`;
* `docs/DEV_GUIDE.md`;
* `docs/SPEC.md`;
* `docs/WEB_UI.md`;
* `docs/product/ui_roadmap.md`;
* `config/settings.yml`;
* `config/beeui.yml`;
* `config/prompts.yml`;
* `pyproject.toml`;
* CLI and entrypoints;
* artifacts and schemas;
* adapters and read-models;
* routes and APIs;
* module public contracts;
* capability and provider boundaries.

For BeeAgent UI work, inspect:

* `docs/product/ui_roadmap.md`;
* `docs/WEB_UI.md`;
* BeeAgent UI configuration;
* affected adapters and read-models;
* routes and artifact allowlists;
* relevant tests;
* BeeUI dependency and required public contracts.

For domain-module work, inspect:

* repository guidance;
* relevant roadmap;
* public contracts;
* relevant implementation, fixtures and tests.

For BeeUI as an additional repository, inspect only enough to determine:

* whether the generic capability already exists;
* whether its public contract is sufficient;
* whether BeeUI must change;
* compatibility and release order.

An additional repository is contract-only until a required change is proven.

## Current state and actual gap

Determine:

* current stage;
* completed neighbouring items;
* active planned work;
* future and deferred scope;
* stale or duplicate roadmap items;
* current implementation and contracts;
* tests and artifacts;
* blockers and limitations;
* implementation-roadmap drift;
* whether the task is already delivered;
* whether another item covers it.

Roadmap status is not implementation evidence.

Classify relevant drift as:

```
implementation ahead of roadmap
roadmap ahead of implementation
stale future scope
duplicated scope
duplicated iteration ID
completed-history documentation debt
blocking contract gap
intentional sequencing difference
separate follow-up
```

Do not create a feature solely to repair stale documentation.

State the verified gap using:

* current behavior;
* required behavior;
* evidence of absence or insufficiency;
* product, operator or architecture impact;
* why it matters now.

Separate real gaps from:

* documentation drift;
* local defects;
* contract mismatches;
* future ideas;
* optional polish.

## Necessity verdict

Return exactly one:

```
necessary now
necessary after prerequisite
useful but defer
already covered
already implemented
standalone maintenance
not justified
```

Consider:

* product or operator value;
* roadmap direction;
* prerequisite readiness;
* existing contracts;
* sequencing;
* architecture debt;
* delivery coherence;
* cross-repository cost.

Do not approve work only because it is technically possible.

Provide concise evidence-based project-development advice when useful.

## Roadmap ownership

### BeeAgent core roadmap

Use:

```
docs/ROADMAP.md
```

for:

* orchestration and runtime;
* run or session state;
* configuration and validation;
* artifact lifecycle;
* module platform;
* capability and provider execution;
* approval, policy and authority;
* transports and external connectors;
* CLI and source ingestion;
* shared backend services;
* general non-UI security boundaries.

### BeeAgent UI roadmap

Use:

```
docs/product/ui_roadmap.md
```

for:

* BeeAgent Web Console;
* operator workflows;
* dashboards and navigation;
* queues, filters, sorting and pagination;
* event details;
* product-specific UI read-models and adapters;
* BeeAgent use of BeeUI;
* ROP operator UI;
* Bitrix widget presentation;
* operator-visible actions and projections.

Backend work may still belong to the UI roadmap when the main deliverable is operator-facing.

### Domain-module roadmap

Use the domain repository roadmap for:

* taxonomy and classification;
* business rules;
* domain validation and fixtures;
* domain AI eligibility and merge rules;
* domain summaries and recommendations;
* domain reason codes or outcomes.

Do not move domain logic into BeeAgent core.

### Companion BeeUI roadmap

When a BeeAgent UI requirement needs a new reusable BeeUI capability:

* keep the product requirement in BeeAgent’s UI roadmap;
* put the generic capability in `beeui/docs/ROADMAP.md`;
* create separate repository Issues;
* define implementation, merge, release and dependency order;
* do not synchronize iteration IDs.

## Repository ownership

Apply the full architecture rules from `AGENTS.md`.

Verify that:

### BeeAgent owns

* orchestration and runtime state;
* configuration and validation;
* module loading;
* capability and provider execution;
* artifact lifecycle;
* product adapters and read-models;
* product labels, metrics and queries;
* product navigation and artifact allowlists;
* product actions and authority;
* transports and external-system orchestration.

### Domain modules own

* taxonomy and domain models;
* classification and business rules;
* domain validation and fixtures;
* domain AI rules;
* domain summaries and recommendations.

### BeeUI owns

* generic rendering and layouts;
* reusable components;
* templates and static assets;
* generic adapter and route mechanisms;
* embedded integration;
* generic session and CSRF transport;
* generic escaping, links, locale and theme behavior.

Do not:

* duplicate domain taxonomy in BeeAgent;
* import private module internals;
* move product semantics into BeeUI;
* make BeeUI read BeeAgent storage;
* duplicate BeeUI primitives in BeeAgent;
* put business decisions in templates;
* create a second source of truth;
* hide multiple repository implementations inside one Issue.

## Planning decision

Choose exactly one:

```
reuse
refine
replace
insert
standalone
reject as unnecessary
```

### Reuse

Use when an unfinished item already covers the verified task without material roadmap changes.

Identify the exact roadmap, stage and iteration.

Do not generate duplicate roadmap wording.

### Refine

Use when an unfinished item is directionally correct but needs clearer scope, ownership, compatibility, acceptance criteria or checks.

Do not refine completed history.

### Replace

Use when unfinished future scope is stale or based on an incorrect architecture boundary.

Show the replaced item, reason, replacement and downstream impact.

### Insert

Use when no existing item covers a verified coherent gap.

A new item must:

* close a current gap;
* have one coherent deliverable;
* respect ownership;
* have observable acceptance criteria;
* fit focused repository Issues;
* match current project direction.

### Standalone

Use only for genuinely small maintenance outside numbered product flow.

### Reject as unnecessary

Use when:

* behavior already exists;
* another task covers it;
* the proposal duplicates a source of truth;
* no task remains in the proposed repository;
* the idea is premature or speculative;
* the architecture is unnecessary.

Explain the simpler alternative where applicable.

## Iteration versus standalone

A numbered iteration is normally required for substantial changes to:

* runtime or operator workflow;
* public or integration contracts;
* APIs, artifacts or configuration;
* module or capability boundaries;
* provider execution or authority;
* product read-models or actions;
* reusable UI behavior;
* external connector integration;
* cross-repository contracts;
* another testable product capability.

Standalone is normally appropriate for:

* typo or formatting fixes;
* narrow documentation alignment;
* small test corrections;
* housekeeping;
* a narrow local bug without contract impact;
* small skill maintenance;
* small packaging fixes without new behavior.

Documentation should normally accompany technical work rather than become a separate iteration.

## Solution options

Present no more than three materially valid options.

For each option state:

* repository and roadmap ownership;
* implementation boundary;
* contracts reused or changed;
* advantages and disadvantages;
* compatibility impact;
* dependency and sequencing impact;
* main risk.

Recommend one using:

* smallest complete solution;
* strongest contract reuse;
* correct ownership;
* no second source of truth;
* minimum coupling and migration;
* proportionate verification;
* no speculative architecture.

Do not manufacture alternatives.

If one valid solution exists, say so.

## Roadmap reconciliation and numbering

Before changing a roadmap:

1. inspect the referenced item;
2. inspect neighbouring completed and unfinished items;
3. check overlapping and duplicate scope;
4. check duplicate IDs;
5. compare implementation with roadmap claims;
6. select roadmap, stage and insertion point;
7. preserve completed history;
8. decide whether unfinished items need refinement, retirement or renumbering;
9. check references and dependencies.

Rules:

* never change or renumber `DONE` IDs;
* never reuse a completed ID;
* never leave duplicate IDs;
* use decimal numbering only for direct continuation;
* use the next suitable whole number for independent work;
* renumber unfinished items only when unavoidable;
* prefer retiring stale future scope over mass renumbering;
* preserve established prefixes such as `UI-`;
* do not synchronize IDs across repositories;
* show an exact retirement or renumbering map when required.

Do not automatically append to the end of a roadmap.

## Cross-repository planning

Use:

```
one implementation repository
= one Issue
= one target worktree
= one feature branch
= one PR
```

For every implementation target define:

* responsibility;
* public contract;
* dependency direction;
* prerequisites;
* implementation and merge order;
* release or dependency-update order;
* compatibility requirements;
* verification and completion condition.

Do not assign companion work without proving the current public contract insufficient.

When BeeAgent consumes a BeeUI change:

1. implement and verify BeeUI;
2. merge BeeUI;
3. make an approved BeeUI revision available;
4. update BeeAgent to the actual available version or revision;
5. update dependency files only inside the approved BeeAgent Issue;
6. run BeeAgent integration and UI smoke.

Do not invent future versions.

Run `.agents/prompts/02-implementation-tests.md` separately for every repository Issue.

## Implementation plan

For each implementation target provide:

* repository and responsibility;
* current implementation to reuse;
* verified layers likely to change;
* behavior and contracts to change;
* source of truth;
* configuration, artifact, route, API or dependency impact;
* compatibility requirements;
* security and authority constraints;
* automated scenarios;
* smoke and inspection requirements;
* documentation;
* implementation order;
* completion criteria.

Do not invent exact file paths.

When a file is unconfirmed, name the verified layer and require the executor to confirm the concrete location.

Do not turn the plan into an executor prompt.

## Roadmap output contract

For a numbered item, provide a compact copy-ready fragment with exactly these iteration headings:

```
Goal
Scope
Excluded
Deliverable
Acceptance criteria
Checks
DoD
```

Use this form:

```
## Этап <номер> — <English stage title>

### Итерация <ID> — <English iteration title>

**Статус:** PLANNED

#### Goal

<Russian content>

#### Scope

<Russian content>

#### Excluded

<Russian content>

#### Deliverable

<Russian content>

#### Acceptance criteria

<Russian content>

#### Checks

<Russian content>

#### DoD

<Russian content>
```

Rules:

* stage and iteration titles are English;
* body is Russian;
* technical identifiers remain unchanged;
* include only iteration-level information;
* put implementation detail in the Issue;
* target 40–60 lines;
* absolute maximum 80 lines;
* do not add extra iteration headings;
* do not repeat an existing stage heading when only an iteration block must be inserted.

For `reuse`, do not generate a duplicate fragment.

For `refine` or `replace`, provide the complete replacement fragment.

For `reject as unnecessary`, provide no fake iteration.

## Standalone output contract

For standalone work provide:

```
Title:
Classification: standalone
Reason:
Scope:
Excluded:
Deliverable:
Checks:
DoD:
Roadmap insertion required: no
```

Use Russian except for technical identifiers.

Do not invent an iteration number.

## Issue preparation

Prepare one complete Issue in English per implementation repository.

Read and follow the target repository’s actual:

```
.github/ISSUE_TEMPLATE/issue.md
```

Rules:

* preserve the actual heading order;
* fill relevant sections;
* use the actual roadmap file;
* use observable and testable requirements;
* keep Issue scope aligned with the roadmap;
* do not duplicate all stable rules from `AGENTS.md`;
* include only task-specific implementation and verification constraints.

For standalone work state:

```
Iteration: none
```

When the selected roadmap is `docs/product/ui_roadmap.md`, state that exact path even if the template mentions only `docs/ROADMAP.md`.

The Issue must cover as applicable:

* current limitation and why now;
* included and excluded scope;
* deliverable;
* source of truth;
* contracts and compatibility;
* configuration, API, route, artifact or module impact;
* security and authority constraints;
* automated and smoke scenarios;
* documentation;
* dependencies and sequencing;
* Acceptance Criteria;
* Definition of Done;
* `version not changed`.

Do not use vague requirements such as:

```
implement as needed
update relevant tests
follow best practices
handle edge cases
make it robust
```

Use one change level from current SDLC:

```
low-risk
runtime-risk
security-sensitive
```

Select proportional checks from `docs/SDLC.md` and `docs/SECURITY.md`.

Without an approved dependency change:

* do not plan dependency or lockfile changes;
* require final changed-file inventory to confirm they remain untouched.

Never require:

```
uv lock --check
```

Do not propose a version bump unless the task is explicitly release-related.

## Planning handoff constraints

Provide concise task-specific implementation constraints, including only applicable:

* ownership;
* existing implementation to reuse;
* public contract;
* source of truth;
* compatibility;
* forbidden changes or mutations;
* configuration and artifact rules;
* dependency restrictions;
* release order;
* version restriction;
* dirty-worktree reconciliation.

Provide concise task-specific verification constraints, including only applicable:

* expected change level;
* Acceptance Criteria scenarios;
* targeted and full tests;
* CLI, route, API or browser smoke;
* artifact and log checks;
* malformed-input and no-mutation checks;
* leakage and security checks;
* dependency status;
* cross-repository contract checks.

Do not prepare implementation, verification or correction prompts.

Record only material executor complexity factors:

* repository count;
* architecture layers;
* security sensitivity;
* external connectors;
* browser code;
* dependency or asset changes;
* migration and compatibility;
* release sequencing.

Do not select Copilot or Codex.

## Naming

For each implementation repository provide:

* recommended branch name;
* recommended Conventional Commit title.

Follow current repository conventions.

Do not propose commit operations, push commands, tags or invented release numbers.

For ordinary work state:

```
version not changed
```

## Output format

Return these sections in order:

```
## Executive verdict
## Repository state
## Current implementation and contracts
## Roadmap selection
## Roadmap reconciliation
## Necessity verdict
## Architecture and repository ownership
## Solution options and recommendation
## Implementation plan
## Iteration numbering and insertion
## Copy-ready roadmap iteration or standalone task
## Copy-ready Issue
```

Use `## Copy-ready Issues` for multiple repositories.

Then return:

```
## Implementation order
## Verification and security
## Branch and commit naming
## Project-development recommendations
## Planning handoff
```

Add `## Assumptions or blockers` only when needed.

Write:

* planning analysis in Russian;
* roadmap body in Russian;
* roadmap stage and iteration titles in English;
* Issues in English;
* technical identifiers unchanged.

Keep analysis concise and avoid repeating the same evidence across sections.

Do not claim Bee Dev MCP ran tests.

## Planning handoff

Return:

```
Primary product repository:
Primary roadmap:
Stage:
Iteration:
Decision:
Necessity verdict:
Implementation targets:
Issue count:
Execution order:
Required separate prompt-02 runs:
Source of truth:
Public contracts:
Compatibility requirements:
Task-specific implementation constraints:
Task-specific verification constraints:
Executor complexity factors:
Version status:
```

For standalone work:

```
Iteration: none
```

For rejected work:

```
Implementation targets: none
Issue count: 0
Required separate prompt-02 runs: 0
```

Do not create:

* planning artifact files;
* automatic roadmap edits;
* automatic Issues;
* branches;
* commits;
* PRs.

Do not modify or execute anything.
