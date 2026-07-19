---
name: beeagent-plan-iteration
description: Plan or refine the next substantial BeeAgent iteration, align related roadmaps and contracts, and produce an Issue plus implementation and verification prompts without modifying the repository.
---

# BeeAgent iteration planning workflow

## Use this skill when

Use this workflow when:

* the next BeeAgent iteration has not been approved;
* an existing ROADMAP iteration needs to be checked or refined;
* an Issue must be prepared from current repository state;
* BeeAgent, BeeUI and related module roadmaps may be out of sync.

Do not use this workflow when an Issue and its acceptance criteria are already approved. In that case, proceed directly to implementation.

This workflow is read-only. Do not modify files, switch branches, run tests or execute repository commands.

## Required inputs

Obtain:

* project name;
* exact MCP target;
* expected Git branch;
* expected base branch;
* context mode;
* last known completed iteration, if supplied;
* any product or customer constraints supplied by the user.

Do not infer the target from a branch name.

## Repository resolution

1. Call `list_worktrees` for the project.
2. Locate the exact requested target.
3. Call `get_project_context` for that target and mode.
4. Verify:

   * target;
   * project;
   * branch;
   * expected base branch when available;
   * dirty state.

If the target or branch differs from the expected value, stop and report:

* actual target;
* actual branch;
* expected target;
* expected branch.

If unexpected dirty changes exist, inspect them with `get_review_bundle`.

Do not treat unrelated uncommitted ROADMAP or documentation changes as merged source of truth.

## Required reading

Read completely:

* `AGENTS.md`;
* `docs/ROADMAP.md`;
* `docs/SDLC.md`;
* `docs/SECURITY.md`;
* `docs/DEV_GUIDE.md`;
* `README.ru.md`;
* `.github/ISSUE_TEMPLATE/issue.md`;
* relevant architecture, spec and product-contract documents;
* related project ROADMAPs;
* the UI roadmap and implemented Web UI contract when UI or product sequencing is relevant.

For BeeAgent ROP planning, compare at minimum:

* BeeAgent `docs/ROADMAP.md`;
* `beeagent-rop/docs/ROADMAP.md`;
* `docs/product/ui_roadmap.md`;
* `docs/WEB_UI.md`;
* implemented public BeeAgent/ROP contracts relevant to the proposed work.

When a file is omitted or truncated, repeatedly call `read_project_file` with the returned `next_line` and `next_column` until both are null.

## Establish current state

Determine:

* highest completed substantial BeeAgent iteration;
* current stage direction;
* highest completed related module iteration;
* relevant UI iteration status;
* implemented contracts that may be ahead of or behind ROADMAP wording;
* known blockers or deferred limitations;
* whether the supplied “last completed iteration” matches the repository.

Report inconsistencies explicitly.

Do not silently rewrite related project history.

## Decide whether an iteration is needed

A numbered product iteration must deliver a substantial code-level, runtime-level, contract-level or artifact-level increment.

Documentation should normally accompany the increment, not become the whole numbered iteration.

A process, guidance, CI or repository-maintenance task should normally be a standalone `Chore` outside the numbered product ROADMAP.

Approve a proposed iteration only when:

* it closes a current product or engineering gap;
* it is not already implemented;
* it has one coherent deliverable;
* it respects core/module/UI boundaries;
* it has observable acceptance criteria;
* it can be closed through one focused PR or an explicitly coordinated pair of repository PRs.

Reject or revise an iteration that:

* duplicates implemented behavior;
* is documentation-only without a product increment;
* mixes several independent features;
* moves module business rules into BeeAgent;
* introduces speculative future architecture;
* depends on an undefined contract without recording the dependency.

## Roadmap synchronization

Compare BeeAgent with related roadmaps and contracts.

Classify each difference as:

* synchronized;
* intentional sequencing difference;
* stale documentation;
* blocking contract gap;
* separate follow-up.

Do not force equal iteration numbers across repositories. Synchronize dependencies and contracts, not numbering.

When work is required in another repository:

* keep each repository change in its own branch and PR;
* define the public contract between them;
* do not combine unrelated repository histories.

## Define the iteration

Provide the updated iteration wording in Russian.

Include:

* iteration number and title;
* status;
* goal;
* why it is needed now;
* dependencies;
* included scope;
* excluded scope;
* deliverable;
* config and contract impact;
* expected artifacts;
* change level;
* required tests and checks;
* Definition of Done.

Keep it substantial but bounded.

## Prepare the Issue

Use `.github/ISSUE_TEMPLATE/issue.md`.

Write the Issue in English and fill every applicable section.

Acceptance criteria must be observable and testable.

Explicitly state:

* included and excluded scope;
* source of truth;
* core/module/UI boundary;
* config or contract impact;
* expected artifacts;
* required verification;
* security implications;
* `pyproject.toml.version` must not change unless the Issue is about release/versioning.

## Select the executor

Default to Copilot for a clear, bounded implementation.

Choose Codex only when one or more apply:

* repo-wide analysis is required;
* several subsystems and many files are involved;
* engineering investigation requires extensive command execution;
* an independent technical audit is required;
* local file-by-file context is insufficient;
* the change is highly security-sensitive and needs broad verification.

Explain the choice briefly.

## Prepare implementation prompt

The implementation prompt must instruct the executor to:

* verify the exact branch and dirty state;
* read `AGENTS.md`;
* read the approved Issue and required documents;
* stay inside Issue scope;
* determine the change level;
* preserve source-of-truth and architecture boundaries;
* make minimal KISS changes;
* run proportional required checks;
* inspect relevant logs and artifacts;
* provide exact command results;
* report changed files, security review and limitations;
* confirm `version not changed`.

Do not duplicate all stable repository rules already present in `AGENTS.md`.

## Prepare verification prompt

Create a separate prompt for the executor to perform the final verification and return a review-ready report.

Require:

* exact test commands and results;
* smoke results when applicable;
* logs checked;
* exact artifacts created or updated;
* config and contract verification;
* security checks required by the change level;
* changed-file list;
* unrelated-file check;
* dependency and version confirmation;
* known limitations.

## Naming

Provide one recommended branch name and one Conventional Commit message.

Use the Issue type and existing repository naming rules.

## Output format

Return:

1. `Repository state`
2. `Iteration decision`
3. `Roadmap synchronization`
4. `Updated iteration`
5. `Issue`
6. `Executor`
7. `Implementation prompt`
8. `Verification prompt`
9. `Branch and commit`
10. `Assumptions and limitations`

Do not modify or execute anything.
