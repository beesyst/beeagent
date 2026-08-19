# DEV_GUIDE — разработка модуля, тесты, интеграция с BeeAgent

## Purpose

Этот документ описывает:

- как разрабатывать `beeagent-rop`;
- как работать с окружением и зависимостями через `uv`;
- как гонять тесты;
- как держать границу между модулем и BeeAgent core;
- как подключать модуль к `beeagent`;
- как вести разработку в рамках текущего SDLC-light процесса.

## Related project docs

Этот документ используется вместе с:

- `docs/ROADMAP.md` — этапы, итерации, scope, artifacts, checks, DoD;
- `docs/SDLC.md` — lightweight process, change levels, required checks, PR flow;
- `docs/SECURITY.md` — secure development rules и security checks по типу изменения.

Правило:

> `DEV_GUIDE` не заменяет `ROADMAP`, `SDLC` и `SECURITY`, а помогает быстро и безопасно разрабатывать модуль.

## Требования

- Python 3.14+
- `uv`

## One-shot mailbox polling

Production mailbox polling is a one-shot command: `./start.sh rop poll`.
Its mutable UID checkpoint is `storage/interfaces/rop_mailbox_checkpoint.json`; it is
runtime storage, not configuration or Git state. Use `./start.sh rop poll --rebaseline`
only for explicit operator recovery. Scheduling belongs to an external systemd timer,
not to a BeeAgent loop.

Polling mode is controlled by `rop.mailbox_poll` in `config/settings.yml`:

- `source_id` — default single-source mode (backward-compatible);
- `sources_all: true` — poll every enabled read-only `mailbox_readonly` source independently.

Optional CLI overrides:

- `./start.sh rop poll --source-id <id>` — poll only that source (also for per-source rebaseline);
- `./start.sh rop poll --all-sources` — poll all enabled read-only mailbox sources;
- `./start.sh rop poll --rebaseline [--source-id <id>]` — reset baseline for the selected source(s).

Per-source semantics:

- each enabled source has its own `UIDVALIDITY` / `last_processed_uid` checkpoint entry;
- a source checkpoint advances only after its full ROP pipeline and postprocessing succeed;
- one source failure never blocks the other selected sources and never rolls back successful checkpoints;
- a new source without a checkpoint receives its own baseline without resetting existing sources;
- an explicit per-source rebaseline does not reset unrelated sources.

When Bitrix reconciliation is enabled, the poll persists durable ROP write-back intent
(`storage/interfaces/rop_writeback_state.json` via `build_writeback_plan`) before the source
checkpoint advances. With `bitrix.writeback.enabled: true` plan persistence failure blocks
checkpoint advancement; otherwise it is logged without blocking ingestion. The required
ordering is durable intent → checkpoint → external execution → original per-run projection
refresh. A temporary reconciliation
outage persists a recoverable deferred record, advances the checkpoint after that persistence
and is refreshed from retained run artifacts during a later poll/run without mailbox
re-ingestion. A no-new-mail poll performs at most one bounded recovery pass. `rop writeback
plan/execute` remains the controlled manual path.

## Controlled Bitrix write-back (Iteration 37)

Write-back is disabled by default (`bitrix.writeback.enabled: false`) and performs zero
writes until it is explicitly enabled with a dedicated env credential and configured
customer Lead `stageId` values.

When enabled, pending write-back work is executed automatically as part of `rop poll` and
`rop run` (after the durable plan is persisted), in addition to the explicit CLI commands.
When write-back is enabled, `rop run` fails explicitly if reconciliation or plan persistence
cannot create canonical intent; action-draft projection and post-persistence executor failures
remain visible and recoverable from that intent:

- `./start.sh rop writeback plan --run-id <id>` — build the authoritative execution plan
  from final classification, read-only reconciliation and recipient routing; persists the
  canonical `storage/interfaces/rop_writeback_state.json` and the per-run
  `rop_writeback_summary.json` projection. Zero writes.
- `./start.sh rop writeback execute [--run-id <id>] [--dry-run] [--retry-failed]` — execute
  pending write-back work per server-side `bitrix.writeback` policy (bounded retry,
  idempotent create via `crm.item.add`, `entityTypeId=1`, fail-closed
  stage/responsible/target validation). `--dry-run` performs zero writes.
  `--retry-failed` re-arms retry-exhausted create or attachment work with a fresh retry
  budget (terminal permission/config/invalid-field attachment failures are never retried).

Per-event outcomes are `create_lead`, `attach_existing` or `deferred`. `rop_action_drafts.json`
remains a read-only/draft-only artifact and is not execution authority.

`BitrixReadonlyClient` remains strictly read-only; `crm.activity.list` is used only for
activity idempotency reconciliation. `BitrixWriteClient` permits only the required mutation
methods `crm.item.add` and `crm.activity.add`; it does not permit `crm.item.update`,
`crm.item.delete`, `crm.lead.add` or arbitrary method execution.

For a safe existing Deal, reconciliation first requires exact sender email/phone evidence for
Contact or Company, then performs bounded read-only `crm.item.list` with `entityTypeId=2` and
the official `contactId`/`companyId` relation field. One related Deal is safe; zero/multiple,
malformed or connector results are never safe, and title/subject similarity remains review-only.
Contact/Company is never an activity owner or execution target. A completed exact Lead and
related-Deal search with no target is persisted as `identity_only_no_target` with
`suitable_target_search=completed_no_target`; only `new_lead` and `irrelevant` may then use
the normal configured create path.

`fallback_responsible_user_id` is unsupported. A Lead create is allowed only after
`rop_recipient_routing.json` reports an exact active responsible match with a positive
`user_id`; unresolved, inactive, ambiguous, degraded or malformed routing evidence fails
closed to `deferred` (`responsible_unresolved`).

## Установка (dev)

В корне модуля:

```bash
uv sync
```

Запуск выполняй через `uv run`, активация venv не нужна.

## Управление зависимостями (`uv`)

Источник правды по зависимостям:

- `pyproject.toml`
- `uv.lock`

Правило проекта:

> После изменения зависимостей коммить и `pyproject.toml`, и `uv.lock`.

### Базовые команды

| Что сделать                    | Команда              |
| ------------------------------ | -------------------- |
| Поставить зависимости          | `uv sync`            |
| Запустить тесты                | `uv run pytest -q`   |
| Добавить зависимость           | `uv add <pkg>`       |
| Добавить dev-зависимость       | `uv add --dev <pkg>` |
| Удалить зависимость            | `uv remove <pkg>`    |
| Посмотреть дерево зависимостей | `uv tree`            |

## Что такое `beeagent-rop`

`beeagent-rop` — это **не отдельный runtime** и не отдельный UI.

Это доменный модуль для BeeAgent, который отвечает за:

- inbound event understanding;
- lead classification;
- duplicate resolution;
- attachment-aware triage;
- ROP summary;
- bounded recommendations;
- bounded AI assist contract for ambiguous/fallback classification (It17+).

Правило:

> Модуль не должен брать на себя orchestration, session management, общий artifact lifecycle и capability transport. Это зона BeeAgent core.

## Где проходит граница модуля

### Это зона `beeagent-rop`

- `contracts.py`
- `domain/*`
- `services/*`
- `cases/*`
- client-specific fixture logic
- classification rules
- duplicate/entity resolution
- attachment-aware logic
- rop summary
- client-facing recommendation draft
- AI assist contract: eligibility, request builder, decision validation, merge (It17+)
- human-reviewed taxonomy contract (It18+)
- thread context contract (It18+)

### Это зона `beeagent`

- module contract
- module registry
- run/session context
- artifact API
- transport/UI
- capability abstraction
- approvals / policy / authority boundaries
- общий orchestration flow

Правило:

> Если изменение нужно только для логики РОП/клиента, оно должно жить в `beeagent-rop`. Если оно нужно для всех модулей — тогда это кандидат в core.

## Как тестировать модуль

Основной способ:

```bash
uv run pytest -q
```

### Что должно тестироваться внутри модуля

- domain contracts;
- classification cases;
- duplicate cases;
- attachment-aware cases;
- summary generation;
- recommendation generation;
- AI assist eligibility, request builder, decision validation, merge;
- human review taxonomy validation;
- thread context validation and classification integration;
- fixture-based edge cases.

### Что не должно тестироваться как responsibility модуля

- Telegram UI;
- общий run lifecycle BeeAgent;
- module registry;
- MCP transport;
- n8n execution engine.

Это тестируется в `beeagent`.

## Fixture-driven разработка

Для `beeagent-rop` fixture-driven подход обязателен.

Почему:

- клиентские кейсы грязные;
- входящий поток нестабилен;
- правила надо проверять не “в голове”, а на воспроизводимых примерах.

### Практика

Для каждой значимой итерации полезно иметь fixture-наборы:

- новый лид;
- existing deal;
- duplicate;
- irrelevant / spam;
- ambiguous case;
- attachment-heavy case;
- “смотри вложение” case;
- dirty input case.

Для inbound contract baseline Iteration 2 fixture-источник живёт в `tests/fixtures/inbound_email_v0/`.
Такие fixtures должны содержать только санитизированный input и ожидаемый normalized result без classification labels.

Для Iteration 3 explainable classification fixture-источник живёт в `tests/fixtures/lead_classification_v1/`.
Такие fixtures должны содержать нормализуемый inbound input и ожидаемый classification result c `case_type`, `priority`, `reason_code` и `is_fallback`.

Для Iteration 4 duplicate resolution fixture-источник живёт в `tests/fixtures/duplicate_resolution_v1/`.
Такие fixtures должны содержать inbound input, доступные `existing_records` и ожидаемый duplicate result c `candidate`, `confidence`, `reason_code`, `reason_path` и fallback semantics.

Для Iteration 5 attachment reader decision fixture-источник живёт в `tests/fixtures/attachment_reader_v0/`.
Такие fixtures должны содержать attachment metadata input и ожидаемый `AttachmentReadResult` c `status`, `reason_code`, `is_supported`, `is_refused`, `needs_manual_review`.
Fixture-примеры покрывают: PDF supported, DOCX supported, XLSX metadata_only, JPG unsupported (no OCR), inline/logo skipped, unknown content type unsupported, oversized refused.

Для Iteration 7 attachment-aware classification fixture-источник живёт в `tests/fixtures/attachment_aware_classification_v1/`.
Такие fixtures должны содержать нормализуемый inbound input с вложениями и ожидаемый classification result.
Attachment context поступает через:

- `attachment.filename` — имя файла;
- `attachment.raw_metadata.text_preview` / `attachment_text` / `summary` — legacy preview keys;
- BeeAgent It25-like downstream keys в `event.raw_metadata` и `attachment.raw_metadata`:
  `attachment_extraction_status`, `attachment_preview_available`,
  `attachment_text_preview`, `attachment_refusal_reasons`,
  `extraction_status`, `preview_available`, `text_preview`,
  `reason_code`, `refusal_reason`.
  Classifier не читает файлы, не генерирует `attachment_extraction.json` и не выполняет OCR — только работает с уже переданными в payload безопасными preview/status/refusal данными.
  Fixture-примеры покрывают: weak body + request filename → new_lead; weak body + invoice filename → existing_deal; text_preview с заявкой → new_lead; text_preview со счётом → existing_deal; refused/unreadable attachment → safe fallback/manual-review.

Для Iteration 8 ROP summary v1 fixture-источник живёт в `tests/fixtures/rop_summary_v1/`.
Такие fixtures должны содержать список classified inbound items и ожидаемый `SummaryResult` с `total_leads`, `counts` и highlighted `items`.
Входной контракт элемента: `event_id`, `case_type`, `priority`, `is_fallback`, `is_attachment_aware`.
Fixture-примеры покрывают: empty input; mixed flow (new_lead/existing_deal/duplicate/irrelevant); high-priority new lead; fallback/low-confidence → needs_manual_review; duplicate highlighted; attachment-aware item.

Для Iteration 9 recommendation builder v0 fixture-источник живёт в `tests/fixtures/recommendation_builder_v0/`.
Такие fixtures должны содержать список classified events и ожидаемый список `RecommendationResult`.
Входной контракт элемента: `event_id`, `case_type`, `priority`, `confidence`, `is_fallback`, `is_attachment_aware`, `reason_code`.
Fixture-примеры покрывают: empty input; new_lead_next_step; existing_deal_follow_up; duplicate_review; irrelevant_no_action; manual_review_required; attachment_aware_review; mixed_recommendations.

Для Iteration 10 BeeAgent integration contract smoke v0 fixture-источник живёт в `tests/fixtures/integration_smoke_v0/`.

Для Iteration 17 AI assist v1 fixture-источник живёт в `tests/fixtures/ai_assist_v1/`.
Такие fixtures должны содержать deterministic classification result, expected AI assist eligibility, optional AI decision и expected merge outcome.
Fixture-примеры покрывают: fallback reply eligible; fallback low signal eligible; ambiguous existing deal eligible; confidential spam not eligible; confident new_lead not eligible; confident existing_deal not eligible; invalid AI decision degraded; AI low confidence degraded; spam cannot be AI-promoted; tender/RFQ remains deterministic; refused attachment with weak body; AI decision with CRM action rejected.
Такие fixtures должны содержать BeeAgent-compatible payload для `RopModule.handle(...)` и ожидаемую shape-структуру `rop_summary` результата.
Smoke-примеры покрывают: `rop_summary` output shape (`period`, `total_leads`, `counts`, `items`, `recommendations`), artifact write через `context.artifact_api.write_json(...)`, unsupported `case_type`, missing/non-list `events`, artifact write failure без crash.

Для Iteration 19 ROP case subtype taxonomy v1 fixture-источник живёт в `tests/fixtures/reviewed_tsv_subtype_v1/`.
Такие fixtures должны содержать inbound event input, expected classification result включая `case_subtype`, `recommended_queue`, `should_rop_see`, `correct_action` и `reviewed_expected.json` с ожидаемыми evaluation counts.
Fixture-примеры покрывают: ETS/SAP tender → `new_lead_tender`; RFQ/quotation → `new_lead_rfq`; WARUITE shipping → `existing_deal_logistics`; Pentagon freight/invoice → `existing_deal_invoice`; ESAB lot clarification → `existing_deal_procurement`; Qarmet delivery deadline → `existing_deal_logistics`; Voestalpine product order → `existing_deal_procurement`; supplier promo → `supplier_offer`; Facebook/WPK/HR → `service_notification`; Kemppi order confirmation → `existing_deal_invoice`; finance reconciliation → `finance_document`; bulk newsletter → `spam_or_bulk`; internal memo → `internal_employee_correspondence`; document request → `existing_deal_document`; malformed subtype → degraded validation path.
Subtype resolver детерминирован и explainable: использует `case_type`, `reason_code`, subject/body markers для выбора subtype без дублирования `rules.py`.

Для Iteration 18 human-reviewed taxonomy v1 fixture-источник живёт в `tests/fixtures/human_review_taxonomy_v1/`.
Такие fixtures должны содержать human review payload и ожидаемый validation result.
Fixture-примеры покрывают: confirmed new_lead; confirmed existing_deal; confirmed irrelevant; confirmed duplicate; manual_review/ambiguous; false_positive; false_negative; deferred review; malformed/missing label; malformed/invalid label; malformed/invalid status.
Human review labels не влияют на live production classification и используются только как fixture/evaluation evidence.

Для Iteration 18 thread context v1 fixture-источник живёт в `tests/fixtures/thread_context_v1/`.
Такие fixtures должны содержать thread context payload, ожидаемый validation result и expected_supportive флаг для ambiguous existing-deal helper.
Fixture-примеры покрывают: reply chain с previous existing_deal; forward-only weak; supplier noise with thread context (не должен promote); tender/RFQ with thread context (детерминированный new_lead); weak continuation без CRM; CRM hint with reply; malformed payloads; empty thread_id.

Для Iteration 12 live mailbox fixture hardening v1 fixture-источник живёт в `tests/fixtures/live_mailbox_hardening_v1/`.
Такие fixtures должны содержать только sanitized/signal-reduced payload и expected outcomes по live mailbox scenario groups.
Минимальный набор групп: supplier promo, tender/procurement notifications, HR/service noise, operational documents, attachment-only manual-review cases, spam-like sales.
Fixture-контракт должен быть explainable: `input` -> deterministic rules -> `expected` без AI-only path.

Для Iteration 13 human-reviewed live classification hardening v1 fixture-источник живёт в `tests/fixtures/live_human_review_v1/`.
Такие fixtures должны содержать только sanitized human-reviewed payload и expected deterministic outcomes по first-pass live review.
Минимальный набор групп: supplier promo, HR/service noise, finance/accounting documents, logistics notifications, tender/procurement, client continuation, attachment-only manual-review, duplicate-candidate finance noise.
Fixture-контракт должен оставаться explainable: `input` -> deterministic rules -> `expected`, а кейсы с открытым бизнес-вопросом должны явно помечаться через `review_status = needs_business_confirmation`.

Санитизация для live mailbox fixtures обязательна:

- только synthetic senders в домене `example.test`;
- без реальных телефонов и live URL;
- без raw `.eml` и full raw message bodies;
- без секретов/токенов/паролей.

Ожидаемое поведение artifact в module-side integration smoke:

- если `context.artifact_api` передан, модуль вызывает `write_json("<case_type>_result.json", ...)`;
- ошибка записи артефакта не должна ронять `RopModule.handle(...)`;
- structured module result остаётся основным output path.

Output shape `rop_summary` (с Iteration 9) включает ключ `recommendations`:

```json
{
  "period": "2026-05",
  "total_leads": 2,
  "counts": {"new_lead": 1, "existing_deal": 1},
  "items": [...],
  "recommendations": [
    {
      "title": "New lead: qualify and contact",
      "body": "High priority new lead. ROP should contact and qualify this lead promptly.",
      "status": "draft",
      "reason_code": "new_lead_next_step",
      "target_event_id": "evt-001",
      "source_case_type": "new_lead",
      "confidence": 0.92
    }
  ]
}
```

Правило:

> Если логика меняется, должен быть fixture или тест, который объясняет, зачем именно она поменялась.

## AI в модуле

AI допустим только как bounded assistive layer.

### Разрешено

- classification assist;
- summary drafting;
- recommendation drafting;
- enrichment поверх контролируемого pipeline.

### Не разрешено

- подменять deterministic rules там, где они обязательны;
- оставлять critical decision полностью на black-box AI;
- скрывать за AI отсутствие нормального contract/rule path.

Правило:

> Сначала deterministic path, потом bounded AI assist поверх него, а не наоборот.

## Подключение модуля к BeeAgent

`beeagent-rop` живёт как отдельная репа и ставится в `beeagent` как editable package.

Из `beeagent`:

```
uv add --editable ../beeagent-rop
```

После этого BeeAgent может импортировать пакет `beeagent_rop`.

### Рабочая модель

- разработка доменной логики — в `beeagent-rop`
- orchestration/integration changes — в `beeagent`
- интеграционные проверки — запускать уже из `beeagent`

## Логи и артефакты

Сам модуль не должен хаотично писать свои файлы куда попало.

Правильная модель:

- unit/fixture tests живут внутри `beeagent-rop`;
- production artifacts модуля пишутся через BeeAgent artifact API;
- linkage идёт через `run_id`, `module_id`, `case_type`.

Правило:

> Если модуль начал сам себе придумывать свой runtime storage lifecycle в обход BeeAgent, это архитектурная ошибка.

## SDLC-light workflow

1. открыть `docs/ROADMAP.md`
2. выбрать текущую итерацию
3. создать issue
4. определить `change level`
5. создать ветку
6. внести изменения
7. прогнать:
   - `uv run pytest -q`
   - нужные fixture tests

8. проверить, что логика не вылезла за scope
9. оформить PR
10. после review — merge

## Change levels

### low-risk

- docs
- naming cleanup
- local tests
- harmless refactor

### runtime-risk

- classification logic
- duplicate logic
- summary generation
- result contracts
- module integration surface
- fixture-driven behavior changes

### security-sensitive

- attachment parsing
- email/file input handling
- file/path handling
- external connectors
- secret/env handling
- serialization/deserialization
- trust-boundary changes

## Что проверять перед PR

Минимум:

```
uv run pytest -q
```

Плюс:

- проверить fixture coverage по своей итерации;
- проверить, что deterministic path остался explainable;
- проверить, что изменение не тащит client-specific костыли в общий contract без причины.

### Типовой checklist

- кейсы клиента покрыты тестами;
- classification/reason path объясним;
- duplicate logic воспроизводима;
- attachment path bounded и безопасен;
- AI не размывает deterministic contract;
- изменение не вылезло за scope текущей итерации;
- required checks по change level действительно выполнены.

## Copilot / AI prompt template (beeagent-rop)

```
Нужно внести изменения в проект `beeagent-rop` (НЕ только в текущий файл).

### Контекст

- Проект: `beeagent-rop` (`Python 3.14+`, `uv`)
- Это отдельный доменный модуль для BeeAgent
- Архитектура: модуль живёт отдельно от `beeagent`, подключается как package-based module и не является отдельным runtime или MCP server
- SDLC-light: `ROADMAP → Issue → branch → code → tests → artifacts → PR → merge`
- Источник правды:
  - domain contracts
  - business rules
  - fixture cases
  - `docs/ROADMAP.md`
  - `docs/SDLC.md`
  - `docs/SECURITY.md`
- Итерация закрывается через `PR`, поэтому изменения должны быть проверяемыми, воспроизводимыми и согласованными с fixture/tests/artifacts

### Правила

- Сначала прочитай все перечисленные файлы, потом предлагай и вноси правки.
- Если по ходу нужен ещё файл — добавь его в список и тоже прочитай.
- Сначала соотнеси задачу с текущей итерацией из `docs/ROADMAP.md`; не выходи за её scope.
- Сначала определи `change level`:
  - `low-risk`
  - `runtime-risk`
  - `security-sensitive`
- Для выбранного `change level` определи required checks по `docs/SDLC.md` и `docs/SECURITY.md`.
- Делай только минимально необходимые изменения по KISS. Не рефактори вне задачи.
- Тесты должны быть минимальными и пропорциональными изменению: покрывай acceptance criteria и публичное поведение, не создавай новые test-файлы/test-helpers без явной необходимости.
- Не меняй чужой scope итерации и не протаскивай “на будущее” недоделанную архитектуру.
- Не убирай существующие проверки без явной причины.
- Не тащи orchestration/runtime/module-registry/capability-transport логику в `beeagent-rop`, если она должна жить в `beeagent`.
- Если видишь, что изменение относится к `beeagent` core, а не к доменному модулю, прямо укажи это в ответе.

### Source of truth rules

- Источник правды в модуле:
  - domain contracts;
  - fixture cases;
  - agreed business rules;
  - явные deterministic paths;
  - bounded AI assist only where justified.
- Не создавай hidden behavior, который нельзя объяснить через input → rules → result.
- Не подменяй обязательные deterministic paths чистым AI output.
- Если добавляешь новый rule/config-like contract внутри модуля, сначала объясни:
  - где он должен жить;
  - почему он относится к модулю, а не к `beeagent`;
  - почему это не создаёт второй source of truth для core runtime.

### Core / module boundary rules

- `beeagent-rop` отвечает за:
  - inbound event understanding;
  - lead classification;
  - new vs existing deal logic;
  - duplicate resolution;
  - attachment-aware triage;
  - rop summary;
  - bounded recommendations;
  - fixture-driven client behavior.
- `beeagent-rop` НЕ должен без причины брать на себя:
  - orchestration;
  - run/session lifecycle;
  - global artifact management;
  - module registry;
  - MCP/tool transport;
  - global approvals / authority / policy.
- Если задача требует изменения общих contracts платформы — это `beeagent`, а не `beeagent-rop`.

### Docs / contracts / artifacts

- Если меняется module behavior, contract, fixture contract, result shape или docs-contract, проверь, нужно ли обновить:
  - `docs/ROADMAP.md`
  - `README.md`
  - `docs/DEV_GUIDE.md`
  - `docs/SDLC.md`
  - `docs/SECURITY.md`
- Если меняется shape результата, покажи пример объекта результата.
- Если меняются fixture contracts, покажи пример fixture input/output.
- После работы дай короткий чеклист для PR/отчёта.

### Code style / execution rules

- Соблюдай PEP 8: имена, длина строк, структура.
- Не добавляй никаких комментариев.
- Логи, имена полей, JSON/JSONL, runtime messages — на английском языке.
- Все команды запуска и тестов указывай через `uv run`, если это применимо.
- Не предлагай hidden side effects во внешних системах без явной задачи на это.

### AI / deterministic rules

- Сначала deterministic path, потом bounded AI assist поверх него.
- Если AI используется:
  - явно укажи, где именно;
  - что остаётся deterministic;
  - каков fallback path;
  - как результат будет проверяемым.
- Не делай black-box решение единственным путём для критичной классификации.

### Release / versioning rules

- Не меняй `version` в `pyproject.toml`, не трогай release metadata, changelog, tags и release-related файлы, если задача явно не про релиз/версионирование.
- Version bump не делается в обычном feature/fix/docs PR.
- Если добавляешь зависимости, обнови только dependency declarations и укажи required SCA checks; версию пакета не меняй без явного указания задачи.

### Формат ответа

Ответ строго в формате:

1. `Что прочитал`
2. `План`
3. `Change level`
4. `Required checks`
5. `Source of truth after change`
6. `Граница core/module`
7. `Было`
8. `Стало`
9. `Почему`
10. `Чеклист`
11. `Что написать в PR`

### Дополнительно к формату

- Без diff
- Без лишних рассуждений
- Если нужна новая функция/класс — укажи точное место вставки (до/после какого блока)
- Для тестов перечисли, какие именно тесты нужно добавить/обновить
- Для каждого нового правила/контракта укажи:
  - где он живёт;
  - почему именно там;
  - почему это относится к модулю, а не к `beeagent`
- Для PR кратко перечисли, что должно попасть в:
  - `Summary`
  - `Tests`
  - `Artifacts`
  - `Security review`
- Отдельно явно укажи:
  - менялся ли `pyproject.toml.version`
  - если задача не про релиз, ответ должен быть `version not changed`

### Задача

<опиши задачу одной фразой>

### Итерация

<укажи номер и название итерации из `docs/ROADMAP.md`>

### Issue context

<вставь кратко Summary / Scope / Deliverable / Acceptance Criteria из issue>

### Файлы

Обязательно прочитай:

- `docs/ROADMAP.md`
- `docs/SDLC.md`
- `docs/SECURITY.md`
- `docs/DEV_GUIDE.md`
- `README.md`
- `pyproject.toml`
- `src/beeagent_rop/module.py`
- `src/beeagent_rop/contracts.py`
- `src/beeagent_rop/domain/models.py`
- `src/beeagent_rop/domain/enums.py`
- `src/beeagent_rop/domain/rules.py`

Если нужно, добавь и прочитай также:

- `src/beeagent_rop/cases/*`
- `src/beeagent_rop/services/*`
- `src/beeagent_rop/adapters/*`
- `tests/*`

### Ожидаемый результат

- `uv run pytest -q` проходит
- ключевые fixture/case scenarios покрыты тестами
- deterministic path остаётся explainable
- AI, если используется, остаётся bounded и имеет fallback path
- изменение не ломает границу между модулем и BeeAgent core
- required checks для данного `change level` определены и перечислены
- изменение готово к оформлению в PR по текущей итерации
```

## Чего не делать

- не тащи client-specific логику в `beeagent` core без причины;
- не подменяй обязательные rules чистым AI output;
- не делай hidden write-back в внешние системы;
- не строй второй runtime внутри модуля;
- не закрывай итерацию без fixture-based tests;
- не смешивай scope нескольких итераций в одном PR;
- не допускай небезопасный file parsing.

## Быстрый рабочий сценарий

1. открыть `docs/ROADMAP.md`
2. выбрать текущую итерацию
3. открыть issue
4. определить `change level`
5. создать ветку
6. внести изменения
7. прогнать:
   - `uv run pytest -q`

8. проверить fixture coverage
9. оформить PR
10. после review — merge

## Bitrix24 Local Application registration (UI-8.5)

Чтобы открыть read-only ROP Web Console внутри Bitrix24 как Server-Side Local Application with User Interface:

1. Настроить `config/settings.yml`:

```yaml
web:
  auth:
    enabled: true
    mode: beeui_session
    session_secret_env: BEEAGENT_WEB_SESSION_SECRET
    principals:
      - id: admin_1
        username: admin1
        role: admin
        scopes: ["*"]
        token_env: BEEAGENT_WEB_ADMIN1_TOKEN
bitrix:
  embedded_app:
    enabled: true
    portal_origin: "https://<your-portal>.bitrix24.ru"
    default_role: "viewer"
    request_timeout: 10
```

2. Обеспечить HTTPS deployment BeeAgent web console (`./start.sh web` за trusted HTTPS-прокси, который настраивает scheme ASGI запроса на `https`). Install/launch handlers требуют HTTPS; HTTPS определяется по scheme ASGI запроса, а не по заголовку клиента (`X-Forwarded-Proto` не доверяется).

3. Зарегистрировать Local Application в Bitrix24 вручную:

| Поле                         | Значение                                     |
| ---------------------------- | -------------------------------------------- |
| Name                         | BeeAgent — ROP                               |
| Handler                      | `https://<beeagent-host>/bitrix/rop/launch`  |
| Initial installation handler | `https://<beeagent-host>/bitrix/rop/install` |
| Uses API only                | false                                        |

3a. В правах приложения обязательно указать **`user`** (Пользователи) — без него `user.current` при входе отклоняется (`insufficient_scope`). После изменения прав приложение нужно переустановить.

4. Установить приложение на портале. Bitrix пришлёт `POST /bitrix/rop/install` с `member_id`, `AUTH_ID`, `AUTH_EXPIRES` и др.; BeeAgent проверит expiry и active Bitrix current user через `user.current`, после чего атомарно сохранит one-time binding в `storage/interfaces/bitrix_rop_app.json` (без OAuth credentials).

5. Пользователь открывает приложение из Bitrix24. Bitrix пришлёт `AUTH_ID`, `AUTH_EXPIRES`, `REFRESH_ID`, `member_id`, `PLACEMENT`, `status` (поля `DOMAIN` Bitrix не шлёт — привязка по `member_id`, домен из config). Запрос приходит на `POST /bitrix/rop/launch` или на `POST /bitrix/rop/install` (в этом случае install тоже выполняет launch flow и редиректит); GET на `/bitrix/rop/launch` отклоняется (`405`) и никогда не обрабатывает OAuth значения. BeeAgent проверит current user через Bitrix REST и создаст bounded BeeUI viewer session, после чего вернёт `303` на `/rop` внутри iframe.

Ограничения:

- access управляется Bitrix24; BeeAgent не хранит список Bitrix user ID;
- OAuth credentials не сохраняются и не логируются;
- existing local BeeAgent login сохраняется.

## Резюме

`beeagent-rop` развивается как отдельный explainable доменный модуль.

Ключевая дисциплина:

- доменная логика живёт в модуле;
- orchestration живёт в BeeAgent;
- fixture-driven разработка обязательна;
- deterministic path важнее black-box магии;
- изменения должны быть объяснимыми, тестируемыми и bounded.
