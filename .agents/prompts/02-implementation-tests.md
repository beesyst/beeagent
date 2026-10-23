# BeeAgent implementation and test prompt preparation

Use only BeeMCP.

Read:

- `AGENTS.md`
- `.agents/skills/beeagent-implement-issue/SKILL.md`
- `.agents/skills/beeagent-verify-and-correct/SKILL.md`

## Main target

- Project: `beeagent`
- Worktree: `<TARGET_WORKTREE>`
- Expected branch: `<FEATURE_BRANCH>`
- Base branch: `main`
- Mode: `<MODE>`
- Roadmap context: `<ROADMAP_CONTEXT>`

## Planning context

```text
<PLANNING_CONTEXT_OR_NONE>
```

## Approved Issue

```text
<FULL_APPROVED_ISSUE>
```

## Supplementary projects

```text
<ADDITIONAL_PROJECTS_OR_NONE>
```

Check the exact target, branch, Issue, repository boundaries and the applicable skills.

Do not implement the task, modify files or run commands.

Prepare exactly two short, ready-to-use prompts:

1. `Copilot implementation`
   - implement the Scope and Acceptance Criteria;
   - run mandatory checks for the actual change level;
   - return a complete implementation and verification report.

2. `Codex verification and correction`
   - independently inspect the actual target worktree state;
   - verify all Acceptance Criteria without relying on the first executor’s report;
   - apply only necessary in-scope corrections;
   - rerun required checks;
   - return a complete consolidated verification report.

Both prompts must:

- be independent and self-contained;
- require no data or report from another executor;
- contain the exact worktree, branch and base branch;
- reference `AGENTS.md` and the corresponding skill;
- include the Issue source, when supplied, and the same compact approved task contract snapshot: Summary, Scope, Excluded, Deliverable, Acceptance Criteria, Change level, required checks and task-specific constraints;
- account only for task-specific restrictions;
- avoid duplicating stable repository rules;
- prohibit commits, pushes, PR creation and merges;
- require no BeeMCP, MCP mode or read-only behavior from Copilot and Codex.

Return only the two ready-to-use executor prompts, without additional analysis.
