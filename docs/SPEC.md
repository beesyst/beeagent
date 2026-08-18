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

- каждое классифицированное событие (включая `irrelevant` и события с
  `should_rop_see=false`) попадает в delivery planning;
- каждый processed event получает outcome `create_lead`, `attach_existing` или
  `deferred`;
- новые eligible Lead создаются через `crm.item.add` с `entityTypeId=1` в configured
  customer `stageId` и с exact matched active responsible из `rop_recipient_routing.json`;
  optional config-driven `source_id` задаёт Lead `SOURCE_ID` (например `EMAIL` =
  «Входящее письмо»);
- при `bitrix.writeback.attach_email: true` к созданному лиду через официальный
  `crm.activity.add` прикрепляется email-активность (`TYPE_ID=4`) с bounded subject/
  body/отправителем;
- безопасно найденный существующий Lead/Deal обрабатывается через attach-existing path
  без создания нового Lead; email/activity binding для существующих сущностей остаётся
  явным `deferred` (`email_binding_contract_unconfirmed`);
- unresolved `existing_deal`/`duplicate`, ambiguous/unsafe target и unresolved responsible
  fail closed в `deferred` без спекулятивного создания;
- стабильная cross-run идентичность — `client_id + source_id +
  (message_id → x_email_id → event_id)`, `event_instance_id` не является remote business
  identity;
- `rop_action_drafts.json` — read-only/draft-only артефакт и не является execution
  authority;
- authoritative write-back intent durable сохраняется до advancement mailbox checkpoint.

Артефакты:

- `storage/interfaces/rop_writeback_state.json` — canonical durable write-back state;
- `storage/runs/<run_id>/rop_writeback_summary.json` — read-only per-run projection.

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
