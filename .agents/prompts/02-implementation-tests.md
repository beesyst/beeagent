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

   * реализация Scope и Acceptance Criteria;
   * обязательные проверки по фактическому change level;
   * полный implementation and verification report.

2. `Codex verification and correction`

   * независимая проверка текущей реализации;
   * только необходимые исправления;
   * полный consolidated verification report;
   * placeholders для implementation evidence и review findings.

Оба prompt должны:

* содержать точные worktree, branch и base branch;
* ссылаться на `AGENTS.md` и соответствующий skill;
* включать полный утверждённый Issue;
* учитывать только task-specific ограничения;
* не дублировать постоянные repository rules;
* запрещать commit, push, PR и merge;
* не требовать Bee Dev MCP, MCP Mode или read-only behavior от Copilot и Codex.

Верни только два готовых executor-prompts без дополнительного анализа.