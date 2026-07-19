---
name: beeagent-review-and-close
description: Review a BeeAgent implementation against its Issue using an exact worktree and base branch, consolidate all blockers in one pass, and prepare the PR close package when approved.
---

# BeeAgent review and close workflow

## Use this skill when

Use this workflow after an implementation agent has completed work and supplied:

* the Issue or acceptance criteria;
* an implementation report;
* test results;
* optional reviewer comments;
* the exact worktree target to inspect.

This workflow is read-only. Do not modify files, switch branches, run tests, create commits, push or merge.

## Required inputs

Obtain:

* project name;
* exact MCP target;
* expected branch;
* expected base branch;
* context mode;
* full Issue or acceptance criteria;
* implementation report;
* previous findings for re-review, if applicable.

The MCP target identifies a local project directory or worktree. It is not the Git branch name.

## Resolve the exact worktree

1. Call `list_worktrees` for the project.
2. Find the exact requested target.
3. If the target does not exist, stop.
4. Call `get_review_bundle` for the exact target and selected mode.
5. Verify:

   * target;
   * project;
   * branch;
   * base branch.

If any value differs from the expected value, stop and report the actual and expected values.

Do not review the main worktree when the requested implementation lives in a separate worktree.

## Read repository guidance

Read completely:

* `AGENTS.md`;
* this skill;
* the supplied Issue;
* relevant ROADMAP section;
* `docs/SDLC.md`;
* `docs/SECURITY.md`;
* relevant architecture, config, API, UI and related-module contracts.

Use `mode="A"` for normal focused review.

Use `mode="C"` when the Issue is architectural, cross-subsystem, security-sensitive or requires broad source inspection.

The context mode supplies project context. It does not replace `get_review_bundle`.

## Inspect the complete change set

Use `get_review_bundle` as the source for changes relative to the base branch.

Inspect:

* committed changes;
* staged changes;
* unstaged changes;
* untracked files;
* deleted files;
* renamed files;
* complete diff;
* complete contents of changed files;
* relevant unchanged contract files;
* related project context when required.

For every omitted or truncated changed/context file, use `read_project_file` with the returned cursor until the complete file has been read.

Do not review only the implementation agent’s file list. Verify the actual worktree.

Do not assume that an untracked file is harmless.

Do not inspect `uv.lock` line by line unless dependency changes are in scope. Verify only whether its presence is expected and whether dependency declarations changed consistently.

## Evaluate against the Issue

For every acceptance criterion, classify it as:

* satisfied;
* partially satisfied;
* not satisfied;
* not verifiable from available evidence;
* not applicable.

Check:

* behavior;
* public contracts;
* config source of truth;
* fail-fast validation;
* core/module/UI boundary;
* backward compatibility;
* artifact shape and linkage;
* logs and diagnostics;
* authority boundary;
* secret and customer-data safety;
* documentation;
* tests and required security checks;
* version and dependency scope.

The actual diff and repository state take precedence over the implementation report.

## Verification evidence

Bee Dev MCP cannot run commands.

Treat supplied command output as reported verification evidence.

Verify that:

* commands match the project and Issue;
* targeted tests cover the acceptance criteria;
* the full suite was run when required;
* smoke checks use the expected entrypoint;
* claimed artifacts correspond to implemented paths and contracts;
* claimed security checks address the real change level;
* no required evidence is missing.

Do not state that you independently executed tests.

Missing required verification evidence is a blocker when the Issue or SDLC requires it.

## Blocking findings

A blocking finding must affect current Issue readiness.

Examples:

* acceptance criterion not implemented;
* incorrect or unsafe behavior;
* data loss or silent fallback;
* security or authority violation;
* core/module/UI boundary violation;
* conflicting config sources of truth;
* missing fail-fast validation;
* broken public API or artifact contract;
* missing required test or verification evidence;
* unrelated change that would enter the PR;
* unintended dependency or version change;
* documentation contradicting the implemented contract.

Do not use as blockers:

* optional polish;
* personal style preference;
* future architecture;
* unrelated refactor opportunities;
* speculative improvements;
* a new requirement not present in the Issue.

Find all blockers before returning the verdict.

Do not release findings one at a time.

## Verdict

Return exactly one verdict:

```text
APPROVED
```

or:

```text
CHANGES REQUIRED
```

### APPROVED

Use only when no real blockers remain.

State:

```text
Правки не нужны.
```

Then provide:

* acceptance-criteria coverage;
* files reviewed;
* verification evidence;
* unverified limitations;
* branch name;
* recommended squash commit;
* completed PR body using `.github/PULL_REQUEST_TEMPLATE/pr.md`;
* whether the PR can be closed through merge.

Do not claim that MCP executed tests.

### CHANGES REQUIRED

Provide:

* every real blocking finding;
* exact affected path and behavior;
* evidence from the diff or contract;
* expected corrected behavior;
* one consolidated correction prompt for Copilot or Codex.

Use the format:

```text
Было
Стало
Почему
```

Do not prepare a final PR body while blockers remain.

## Consolidated correction prompt

The correction prompt must:

* preserve the original Issue scope;
* address every blocker in one pass;
* name affected files or insertion points when known;
* forbid unrelated refactors;
* require targeted regression tests;
* require the previously missing verification;
* require one final complete report;
* preserve version and dependency constraints.

Do not create a separate closing patch for optional improvements.

## Re-review

On re-review:

1. obtain a new `get_review_bundle`;
2. verify the same target, branch and base;
3. check every previous blocker;
4. re-check the original acceptance criteria;
5. inspect regression changes introduced by the corrections;
6. return only:

   * `APPROVED`; or
   * the remaining real blockers.

Do not start a new round of optional findings.

## Output format

Return:

1. `Verdict`
2. `Blocking findings`
3. `Acceptance Criteria coverage`
4. `Files reviewed`
5. `Verification evidence`
6. `Unverified limitations`
7. `Close decision`
8. `PR body` when approved
9. `Consolidated correction prompt` when changes are required