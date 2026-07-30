# BeeAgent final review

Используй только Bee Dev MCP.

Прочитай:

- `AGENTS.md`
- `.agents/skills/beeagent-review-and-close/SKILL.md`

## Основной target

- Project: `beeagent`
- Instruction worktree: `<INSTRUCTION_WORKTREE>`
- Target worktree: `<TARGET_WORKTREE>`
- Expected branch: `<FEATURE_BRANCH>`
- Base branch: `main`
- Mode: `<MODE>`
- Roadmap context: `<ROADMAP_CONTEXT>`

## Утверждённый Issue

```text
<FULL_APPROVED_ISSUE>
```

## Текущий PR

```text
<CURRENT_PR_OR_NONE>
```

## Implementation and verification evidence

```text
<CURRENT_IMPLEMENTATION_EVIDENCE>
```

## Дополнительные targets

```text
<ADDITIONAL_TARGETS_OR_NONE>
```

Правила:

- Проведи один полный read-only review pass.
- Для дополнительных targets соблюдай указанные `Role`, `Mode` и `Skill`.
- Фактические manifest, diff, files, templates, static assets, package contents и public contracts имеют приоритет над Issue, PR и отчётами.
- Не изменяй файлы и не запускай команды.
- Не добавляй необязательный polish, новые требования или unrelated cleanup.
- Не требуй `uv lock --check`.
- Верни результат строго по review skill.
