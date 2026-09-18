# SPEC — BeeAgent

## 0. Термины

- Репозиторий: `beeagent`
- Python-пакет (import): `beeagent_module`
- Core: общее ядро оркестрации BeeAgent
- Module: отдельный доменный модуль, подключаемый к BeeAgent (`beeagent-rop`, будущие `beescan`, `merch`)
- Case: прикладной сценарий, который вызывается transport/UI слоем
- Agent: workflow/graph под конкретный сценарий
- Adapter: слой доступа к данным
- Capability: внешний исполняемый или интеграционный вызов (MCP, n8n, API, system)
- Transport/UI: тонкий слой взаимодействия (`telegram`, позже web и др.)
- Run: один воспроизводимый запуск сценария с `run_id`
- Artifact: файл в `storage/`, который фиксирует результат, шаги или состояние запуска
- Authority: граница прав (`read-only`, `draft-only`, `execution-capable`)

## 1. Цель

Сделать `BeeAgent` как explainable, stateful, modular AI orchestration system, а не как “чат-бот с тулзами”.

Система должна уметь:

- запускать и сопровождать сценарии через единое core;
- работать с transport/UI слоями без вшивания бизнес-логики в UI;
- подключать отдельные доменные модули как python-пакеты;
- хранить state, artifacts, approvals, summaries и trace внутри BeeAgent;
- использовать AI как bounded assistive layer, а не как black-box замену deterministic logic;
- использовать MCP / n8n / внешние systems как capability layer, а не как место жизни доменной логики.

## 2. Принципы разработки

- KISS: минимум лишних абстракций, максимум ясных contracts
- Core должен оставаться универсальным, доменная логика живёт в модулях
- `config/settings.yml` — runtime source of truth
- Новые обязательные ключи валидируются fail-fast
- Логи должны быть понятными
- Артефакты должны быть воспроизводимыми
- Secrets не должны попадать в logs/storage
- Long-running state должен жить в BeeAgent, а не внутри одного tool/MCP вызова
- UI должен быть thin layer
- Capability boundary должен быть явным
- Execution-capable paths должны быть bounded и operator-visible

## 3. Архитектурная схема

Базовая схема системы:

`UI/Transport → BeeAgent core → module/case → capability layer (MCP / n8n / API / systems)`

Где:

- `UI/Transport` отвечает только за вход/выход;
- `BeeAgent core` отвечает за orchestration, state, approvals, artifacts, policy;
- `module` отвечает за доменную логику;
- `capability layer` отвечает за внешние действия и интеграции.

## 4. Что живёт в core, а что не живёт

### 4.1 Что должно жить в `beeagent`

- module contract
- module registry
- runtime context
- artifact API
- case dispatch
- agent/workflow orchestration
- logging
- settings validation
- transport handling
- approval/state/session logic
- capability abstraction
- bounded authority logic

### 4.2 Что не должно жить в `beeagent`

- клиентская бизнес-логика РОПа
- welding-specific lead rules
- client-specific duplicate heuristics
- client-specific email semantics
- merchandising-specific business rules
- beescan-specific business rules

Это должно жить в отдельных модулях.

## 5. Модульная модель

### 5.1 Модуль

Модуль — это отдельный python-пакет, который подключается к BeeAgent как локальная зависимость.

Примеры:

- `beeagent-rop`
- `beescan`
- `beeagent-merch` / `beeagent-merchandising`

### 5.2 Что должен уметь модуль

Модуль должен:

- иметь `module_id`
- объявлять поддерживаемые `case_type`
- принимать `ModuleContext`
- возвращать bounded result
- использовать BeeAgent artifact/runtime contracts
- не ломать authority boundary

For BeeDrill's `isolated_solana_smoke`, BeeAgent injects a caller bound to the
host-generated run, session, module, case and read-only module authority. The
caller accepts only `solana.isolated_lifecycle` with the fixed
`surfpool_local` intent, then owns the offline Surfpool process, fixed local
read-only RPC check and cleanup. The returned capability evidence reports the
host-applied execution-capable authority without changing the module authority.

For BeeDrill's `reference_target_baseline`, the same host-bound caller accepts
only `solana.reference_target_baseline` with the fixed `surfpool_local` and
`reference_vault` payload. BeeAgent resolves the public BeeDrill package
resource itself and returns only bounded canonical economic/control evidence.

For BeeDrill's `reference_target_attack`, the same caller accepts only
`solana.reference_target_attack` with that exact fixed payload and only from the
read-only BeeDrill attack case. BeeAgent owns the offline Surfpool lifecycle,
target preparation and fixed attack transaction. On success it returns exact
target and initial-state identities, a bounded transaction signature, a local
slot reference, fixed before/after lamport balances, unsafe-withdraw transition
counts and integer gross loss. It returns explicit refusal, timeout or error
otherwise; it never accepts module-supplied RPC, executable, path, raw
transaction or credential fields.

### 5.3 Что не должен делать модуль

Модуль не должен:

- напрямую управлять transport/UI;
- хранить свой отдельный runtime вне BeeAgent;
- напрямую подменять core orchestration;
- тихо выполнять внешние действия в обход capability layer;
- создавать hidden execution path.

## 6. Capability layer

BeeAgent работает через capability layer для внешних действий.

Примеры capabilities:

- MCP tool call
- n8n workflow trigger
- API call
- file/system operation

### Правило

- доменная логика не живёт в capability layer;
- capability layer не хранит основной state long-running задачи;
- ошибки, timeout, refusal должны быть явными и воспроизводимыми.

## 7. Транспорт / UI

### v0 / текущий baseline

- Telegram

### позже

- web/operator shell
- другие transport/UI surfaces

### Правило

Transport/UI:

- вызывает cases/module flows;
- не читает storage напрямую;
- не хранит бизнес-логику;
- не подменяет orchestration.

## 8. Конфигурация

### Источник правды

`config/settings.yml`

### Правила

- required keys должны быть явно заданы;
- новые обязательные ключи валидируются в `src/beeagent_module/core/settings.py`;
- без hidden defaults для важных runtime paths.

## 9. Артефакты

Все значимые результаты должны быть воспроизводимы через artifacts в `storage/`.

Типовые артефакты:

- `storage/runs/<run_id>/run.json`
- `storage/runs/<run_id>/steps.json`
- `storage/runs/<run_id>/...` case/module-specific artifacts
- `storage/artifacts/<run_id>/report.*`
- `storage/sessions/...`
- `storage/telemetry/...`

### Требования

Артефакты должны быть:

- понятными;
- согласованными с логами;
- пригодными для ручной проверки;
- безопасными по содержимому.

## 10. Authority model

### Базовые режимы

- `read-only`
- `draft-only`
- `execution-capable`

### Правило

По умолчанию всё должно быть `read-only` или `draft-only`.

Если появляется execution-capable path, он должен быть:

- явным;
- ограниченным;
- проверяемым;
- видимым оператору;
- не скрытым в prompt или случайном code path.

### Bitrix write-back v0 (ROP, Iteration 37)

BeeAgent имеет disabled-by-default bounded Bitrix CRM write-back для ROP-событий.

Поведение:

- каждое классифицированное событие (включая `irrelevant` и события с `should_rop_see=false`) попадает в delivery planning;
- каждый processed event получает outcome `create_lead`, `attach_existing` или `deferred`;
- новые eligible Lead создаются через `crm.item.add` с `entityTypeId=1` в configured customer `stageId` и с exact matched active responsible из `rop_recipient_routing.json`; optional `bitrix.writeback.user_id_fallback` (валидируемый положительный Bitrix user ID) назначается ответственным только при `responsible.status=not_found`; matched, ambiguous, `connector_degraded`, unresolved и not-attempted остаются deferred; optional config-driven `source_id` задаёт Lead `SOURCE_ID` (например `EMAIL` = «Входящее письмо»);
- при `bitrix.writeback.email_attach: true` через официальный `crm.activity.add` прикрепляется email-активность (`TYPE_ID=4`) с bounded subject/body/отправителем; trusted exact thread target получает activity с existing target owner/responsible без reassignment CRM entity; `bitrix.writeback.email_completed` (boolean, валидируется fail-fast, по умолчанию `true`) задаёт, завершена ли создаваемая email-активность (`false` создаёт её незавершённой — заметнее в таймлайне);
- planned record snapshots whether email attachment is required. For `create_lead`, a created/recovered CRM entity is delivery-complete only after the required activity has a valid ID; pending, uncertain, exhausted, terminal or sender-unavailable attachment remains an explicit incomplete delivery state;
- trusted exact thread target обрабатывается через idempotent attach-existing path без создания нового Lead; before every activity POST executor uses read-only `crm.activity.list` with the stable origin identity, including after timeout or malformed response, and persists the returned activity ID;
- exact sender email/phone may identify an existing Deal only through an exact matched Contact/Company and bounded read-only `crm.item.list` (`entityTypeId=2`) relation filter on `contactId`/`companyId`; identity evidence (sender email/phone, Contact/Company, related historical CRM relation) is never an executable target — an exact matched Lead/Deal, an exact Contact/Company and a related Deal stay identity/candidate evidence with `safe_to_use_as_target=false`, and title/subject similarity is never automatic Deal authority;
- automatic existing-target attachment is allowed only for exact trusted thread evidence (Iteration 38): normalized `Message-ID`, `In-Reply-To` (preferred) and bounded `References` resolve against canonical write-back state; all resolved exact referenced ancestors must agree on one trusted Lead/Deal; a confirmed BeeAgent-created Lead (`target_provenance=beeagent_created`) is an authoritative thread root, a thread-resolved attachment (`target_provenance=thread_resolved`) propagates the target, legacy records without trusted provenance are never authority, and conflicting exact references fail closed to `ambiguous_thread_target` deferred with zero mutation;
- an exact Contact/Company is identity evidence, not an executable target. Only after the bounded exact Lead search and related-Deal lookup complete without a target does `identity_only_no_target` with `suitable_target_search=completed_no_target` permit the normal configured `new_lead`/`irrelevant` create path. An independent `new_lead` from a known sender (without exact thread evidence) can create a new Lead; `existing_deal`/`duplicate` without a safe exact target remain deferred/manual-review; run-local `thr_*` IDs, classifier/AI output, subject similarity and `RE:`/`FWD:` markers never authorize attachment; existing target responsible is never reassigned;
- email activity body preview является bounded readable plain text: `<!DOCTYPE ...>`, comments, script/style и HTML tags удаляются, safe structural HTML boundaries (`p`/`div`/`br`/`li`/list/table...) становятся читаемыми line breaks, plain-text line breaks сохраняются, excessive whitespace bounded, прежний `rop.email_preview.body_chars_max` сохранён, без новой parsing dependency;
- `BitrixReadonlyClient` не содержит mutation methods; `crm.activity.list` остаётся read-only idempotency lookup, а `BitrixWriteClient` ограничен только
  `crm.item.add` и `crm.activity.add`;
- при enabled write-back dedicated write credential обязан отличаться от read credential и по env name, и по normalized webhook URL;
- unresolved `existing_deal`/`duplicate`, ambiguous/unsafe target и unresolved responsible fail closed в `deferred` без спекулятивного создания;
- стабильная cross-run идентичность — `client_id + source_id + (message_id → x_email_id → event_id)`, `event_instance_id` не является remote business
  identity;
- authoritative write-back intent durable сохраняется до mailbox checkpoint; ordering для poll: durable intent → checkpoint → external execution → original per-run projection refresh. Temporary reconciliation outage сохраняется как recoverable deferred state и повторно сверяется из retained run artifacts без mailbox re-ingestion.

Артефакты:

- `storage/interfaces/rop_writeback_state.json` — canonical durable write-back state;
- `storage/runs/<run_id>/rop_writeback_summary.json` — read-only per-run projection, refreshed for each original affected run after execution/recovery.

With write-back enabled, `rop run` must durably persist the reconciliation-backed plan before it can report success. A projection or post-persistence executor failure never erases canonical intent and remains recoverable through later run, poll or controlled manual execution.

## 11. Стек

Текущий стек:

- Python 3.14+
- `uv`
- `PyYAML`
- `python-dotenv`
- `python-telegram-bot`
- `langgraph`
- `pytest`

Дополнительные зависимости добавляются только по реальной необходимости.

## 12. Запуск

### Основной запуск

`start.sh` запускает `uv sync` и затем `uv run python3 config/start.py`

### Правило

- основной runtime запускается из репозитория `beeagent`
- модули подключаются как локальные зависимости через `uv`
- модуль не поднимает свой отдельный runtime по умолчанию

## 13. Критерии зрелости core

BeeAgent считается развиваемым в правильную сторону, если:

- transport слой тонкий;
- core не захламляется клиентской логикой;
- модули подключаются по стабильному контракту;
- capability boundary явный;
- artifacts и logs объясняют поведение;
- AI не размывает deterministic path;
- delivery нового модуля не требует переписывать core.

## 14. Ближайшее направление

Ближайшая цель:

- завершить module platform v0;
- подключить `beeagent-rop` как первый реальный доменный модуль;
- провести клиента через Discovery → MVP → Pilot;
- не сломать универсальность core.
