# BeeAgent implementation and test prompt preparation

Используй только Bee Dev MCP.

Прочитай:

- `AGENTS.md`
- `.agents/skills/beeagent-implement-issue/SKILL.md`
- `.agents/skills/beeagent-verify-and-correct/SKILL.md`

## Основной target

- Project: `beeagent`
- Worktree: `<TARGET_WORKTREE>`
- Expected branch: `<FEATURE_BRANCH>`
- Base branch: `main`
- Mode: `<MODE>`
- Roadmap context: `<ROADMAP_CONTEXT>`

## Контекст планирования

```text
<PLANNING_CONTEXT_OR_NONE>
```

## Утверждённый Issue

```text
<FULL_APPROVED_ISSUE>
```

## Дополнительные проекты

```text
<ADDITIONAL_PROJECTS_OR_NONE>
```

Проверь точный target, branch, Issue, repository boundaries и применимые skills.

Не реализуй задачу, не изменяй файлы и не запускай команды.

Подготовь ровно два коротких готовых prompt:

1. `Copilot implementation`
   - реализация Scope и Acceptance Criteria;
   - обязательные проверки по фактическому change level;
   - полный implementation and verification report.

2. `Codex verification and correction`
   - самостоятельная проверка фактического состояния target worktree;
   - проверка всех Acceptance Criteria без отчёта первого executor;
   - только необходимые in-scope исправления;
   - повтор required checks;
   - полный consolidated verification report.

Оба prompt должны:

- быть независимыми и самодостаточными;
- не требовать данных или отчёта другого executor;
- содержать точные worktree, branch и base branch;
- ссылаться на `AGENTS.md` и соответствующий skill;
- содержать Issue source, если он был передан, и одинаковый компактный snapshot утверждённого task contract: Summary, Scope, Excluded, Deliverable, Acceptance Criteria, Change level, required checks и task-specific constraints;
- учитывать только task-specific ограничения;
- не дублировать постоянные repository rules;
- запрещать commit, push, PR и merge;
- не требовать Bee Dev MCP, MCP Mode или read-only behavior от Copilot и Codex.

Верни только два готовых executor-prompts без дополнительного анализа.
