# ROADMAP — beeagent (SDLC-light, итерации разработки)

## Purpose

Этот документ фиксирует маршрут разработки `beeagent` по этапам и итерациям.

ROADMAP в проекте используется как lightweight SDLC-артефакт:

- задаёт направление разработки;
- фиксирует цель каждой итерации;
- определяет ожидаемое поведение, артефакты и проверки;
- помогает связывать Issue → Code → Tests → Artifacts → PR → Merge.

ROADMAP не заменяет Issue и PR:

- **Issue** объясняет, что именно нужно сделать в рамках задачи;
- **PR** фиксирует, что реально было сделано и как это проверялось;
- **ROADMAP** показывает, куда идёт проект и что считается готовностью по итерациям.

Итерация закрывается через PR: именно PR является основным местом, где фиксируются verification evidence, checks, artifacts и ограничения реализации.

ROADMAP не дублирует полные правила процесса и безопасности:

- процесс разработки и критерии прохождения изменений описываются в `docs/SDLC.md`;
- secure development rules и security checks описываются в `docs/SECURITY.md`.

## Vision

| Block                          | Statement                                                                                                                                                                                                   |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Product identity**           | `beeagent` развивается как explainable, stateful, modular AI orchestration system с явными operator / interface layers, module contracts и reproducible runtime artifacts.                                  |
| **Primary objective**          | Цель проекта — быть не “чат-ботом с тулзами”, а управляемым агентным ядром, которое оркестрирует задачи, модули, approvals, artifacts и внешние workflow/capabilities.                                      |
| **Execution philosophy**       | Длинная задача, state, batching, retry, checkpoints и policy должны жить в `beeagent`, а не внутри одного MCP/tool вызова.                                                                                  |
| **Source of truth**            | Runtime behavior должен определяться через `config/settings.yml`, явную валидацию, stable contracts и воспроизводимые artifacts.                                                                            |
| **Decision quality principle** | Любое значимое решение или действие должно быть объяснимо по логам, config и artifacts.                                                                                                                     |
| **Module principle**           | Бизнес-логика должна жить в отдельных доменных модулях (`beeagent-rop`, будущие `beescan`, `merch`), а core должен оставаться универсальным.                                                                |
| **Capability principle**       | MCP / n8n / внешние systems — это execution/integration layer, а не место, где живёт доменная логика.                                                                                                       |
| **Operator principle**         | Система должна быть удобна для безопасной эксплуатации через простые UI/transport слои и не требовать скрытого знания кода.                                                                                 |
| **Product direction**          | Развитие идёт по траектории: demo skeleton → reusable orchestration core → module platform → first real client module → pilot-ready operator shell → scalable multi-module platform.                        |
| **AI direction**               | AI допускается только как bounded assistive layer: classification, summarization, recommendation, intent drafting. AI не должен подменять deterministic contracts, policy, approval и authority boundaries. |
| **KISS rule**                  | Новые возможности добавляются только если они усиливают orchestrator, explainability, reusability, module integration или operator usability без раздувания core.                                           |
| **Security rule**              | Secrets, connectors, file parsing, capability execution и artifact contracts развиваются только через explicit config, fail-fast validation и proportional checks по `docs/SDLC.md` и `docs/SECURITY.md`.   |
| **Interface rule**             | Любой agent-facing / operator-facing surface должен быть read-only или draft-only по умолчанию, а execution-capable path должен быть explicit и bounded.                                                    |
| **Execution authority rule**   | Любой execution-capable path должен развиваться через минимально необходимые права, capability-scoped boundaries и явный operator-visible contract.                                                         |

## Development principles

Делаем маленькие итерации. Каждая итерация должна:

- запускаться через `start.sh` или соответствующий CLI entrypoint;
- писать понятные логи;
- оставлять воспроизводимые артефакты в `storage/`, если это предполагается задачей;
- не ломать структуру пакета `beeagent_module`;
- использовать `config/settings.yml` как источник правды;
- валидировать новые обязательные ключи fail-fast;
- закрываться через Issue / PR / tests / artifacts;
- проходить required quality/security checks из `docs/SDLC.md` и `docs/SECURITY.md` в зависимости от типа изменения;
- сохранять explicit authority boundary: read-only, draft-only и execution-capable пути должны быть разделены явно и проверяемо.

Для `beeagent` это означает:

- low-risk изменения проходят базовые checks;
- runtime-risk и security-sensitive изменения требуют усиленной проверки;
- уровень проверки определяется по `docs/SDLC.md` и `docs/SECURITY.md`, а не ad hoc.

## SDLC workflow for roadmap items

Каждая итерация проходит по упрощённому циклу:

1. **Planning**  
   Итерация описана в ROADMAP и оформлена как Issue.

2. **Requirements**  
   Для итерации определены scope, deliverable, артефакты, проверки и DoD.

3. **Implementation**  
   Изменения вносятся в отдельной ветке и только в рамках текущей итерации.

4. **Verification**  
   Выполняются тесты, smoke-check, проверка логов и артефактов, а также required quality/security checks для данного типа изменения.

5. **Review / PR**  
   В PR фиксируются изменения, тесты, артефакты и ограничения.

6. **Merge**  
   Итерация считается завершённой после выполнения DoD.

## Status values

Допустимые статусы итераций:

- **PLANNED** — запланировано
- **IN PROGRESS** — в работе
- **DONE** — завершено
- **DONE (partial)** — завершено частично, есть осознанные ограничения

## Global Definition of Done

Итерация считается завершённой, если:

- поведение реализовано в рамках заявленного scope;
- новые обязательные ключи читаются из `config/settings.yml`;
- валидация для новых обязательных ключей добавлена в `src/beeagent_module/core/settings.py`;
- feature работает через ожидаемый entrypoint;
- логи записываются;
- артефакты создаются там, где это ожидается;
- тесты и ручные проверки выполнены;
- required quality/security checks из `docs/SDLC.md` и `docs/SECURITY.md` выполнены;
- секреты не попадают в логи и артефакты;
- ROADMAP / docs обновлены, если менялся контракт, поведение или артефакты.

## Change levels for verification

Для lightweight SDLC в проекте используются три уровня изменений:

- **low-risk** — docs, локальные тесты, косметические и безопасные изменения без влияния на runtime-контракт;
- **runtime-risk** — изменения orchestrator/runtime/config validation/artifacts/reporting/CLI/module loading/case dispatch, влияющие на runtime behavior или воспроизводимость артефактов;
- **security-sensitive** — изменения secrets/env handling, external capabilities, MCP/tool boundaries, file parsing, dependency surface, serialization/deserialization, file/path handling, authority paths и другие изменения на trust boundary.

Для каждого уровня обязательность quality/security checks определяется в:

- `docs/SDLC.md`
- `docs/SECURITY.md`

## Product phases

| Phase                                     | Status      | What it means                                                                                                                      |
| ----------------------------------------- | ----------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| **Phase A — Demo skeleton**               | DONE        | Сформирован демонстрационный runtime: Telegram transport, mock data, базовые agents/cases, run artifacts, approval, export.        |
| **Phase B — Reusable orchestration core** | DONE        | BeeAgent перестал быть только демо-кейсом и получил reusable cases/adapters/scheduler/observability/multi-agent baseline.          |
| **Phase C — Module platform**             | IN PROGRESS | Вводится явный module contract, registry, runtime context, artifact API и bounded capability layer для внешних доменных модулей.   |
| **Phase D — First real client delivery**  | PLANNED     | Подключается первый реальный доменный модуль (`beeagent-rop`), делается Discovery → MVP → Pilot flow под клиента.                  |
| **Phase E — Operator / product shell**    | PLANNED     | Появляются operator-facing и client-facing controlled interfaces: summaries, status, bounded actions, stable backend contracts.    |
| **Phase F — Multi-module platform**       | FUTURE      | BeeAgent становится базой для нескольких доменных модулей (`ROP`, `BeeScan`, `Merch` и др.) с единым runtime и reusable contracts. |

## Stages

- **Этап 1 (Итерации 0–4):** pre-MVP каркас + запуск + transport + mock/demo flow.
- **Этап 2 (Итерации 5–10):** reusable core: cases/adapters/scheduler/observability/multi-agent + quiz + explainable recommendations.
- **Этап 3 (Итерации 11–14):** module platform v0 (module contract, registry, context, artifact API, capability boundary).
- **Этап 4 (Итерации 15–18):** интеграция первого реального доменного модуля (`beeagent-rop`) и client-ready orchestration flow.
- **Этап 5 (ориентир):** operator/product shell v1.
- **Этап 6 (ориентир):** multi-module scaling (`beescan`, `merch`, другие модули).

---

## Этап 1 — Pre-MVP (итерации 0–4)

### Итерация 0 — Каркас и запуск (skeleton)

**Статус:** DONE

#### Goal

Поднять минимальный каркас проекта и единый entrypoint запуска.

#### Scope

Включено:

- базовая структура проекта;
- запуск через `start.sh`;
- загрузка env и settings;
- базовое логирование;
- создание `logs/` и `storage/`.

Не включено:

- реальные данные;
- сложная orchestration logic;
- модульная платформа.

#### Реализовано

- `start.sh` → запускает `python3 config/start.py`
- `config/start.py` → загрузка env + settings + запуск одного режима (`telegram`)
- `src/beeagent_module/` → создан пакет со структурой проекта
- `beeagent_module/core/log.py` → логирование (`stdout + logs/app.log`)
- `beeagent_module/core/paths.py` → пути к `logs/` и `storage/`
- `beeagent_module/core/settings.py` → загрузка `settings.yml` + fail-fast валидация
- `storage/` и `logs/` создаются автоматически

#### Deliverable

Проект запускается через единый entrypoint и пишет базовые логи.

#### Artifacts

- `logs/app.log`
- `storage/`

#### Checks

- `bash start.sh`
- `pytest -q`

#### DoD

- проект стартует без падения;
- логирование включено;
- директории создаются автоматически.

### Итерация 1 — Telegram bot v0 (UX скелет)

**Статус:** DONE

#### Goal

Дать минимальный transport/UI слой через Telegram.

#### Scope

Включено:

- команды `/start`, `/help`, `/run_oos`, `/last`;
- inline-кнопки;
- allowlist.

Не включено:

- multi-channel UI;
- сложная session routing logic.

#### Реализовано

- команды: `/start`, `/help`, `/run_oos`, `/last`
- inline-кнопки: `Run OOS Scan`, `Show Report`
- allowlist (один `chat_id` в config)

#### Deliverable

Telegram transport работает как thin demo/operator layer.

#### Artifacts

- `storage/telemetry/telegram_updates.jsonl` (optional)

#### Checks

- `bash start.sh`
- smoke в Telegram

#### DoD

- бот запускается и отвечает;
- меню и кнопки работают;
- неизвестная команда не валит runtime.

### Итерация 2 — Mock data v0 + доменная модель

**Статус:** DONE

#### Goal

Подготовить воспроизводимый mock dataset и базовые доменные модели.

#### Scope

Включено:

- `domain/` модели;
- генератор mock data;
- параметры mock dataset в `config/settings.yml`.

Не включено:

- реальные интеграции;
- клиентские доменные модули.

#### Реализовано

- доменные модели для demo flow
- генератор mock dataset:
  - 3 stores
  - 1 category
  - 10–30 SKU
  - 4–12 недель данных
  - forced anomalies
- конфиг параметров mock dataset в `config/settings.yml`

#### Deliverable

Demo-агенты могут работать на воспроизводимых данных.

#### Artifacts

- `storage/mock/<dataset_id>/dataset.json`

#### Checks

- `pytest -q`
- mock generation smoke

#### DoD

- одинаковый seed даёт одинаковый результат;
- mock dataset создаётся и читается одной функцией;
- `/run_oos` создаёт dataset artifact.

### Итерация 3 — LangGraph workflow v0 (OOS detector, dry-run)

**Статус:** DONE

#### Goal

Запустить end-to-end workflow через LangGraph и отчёт в Telegram.

#### Scope

Включено:

- collect_input
- load_data
- detect_oos
- draft_tasks
- render_report
- persist_run

Не включено:

- reusable module platform;
- real data integrations.

#### Реализовано

- end-to-end OOS workflow через LangGraph
- run persistence
- Telegram report output

#### Deliverable

Есть end-to-end run path с artifacts.

#### Artifacts

- `storage/runs/<run_id>/run.json`
- `storage/runs/<run_id>/alerts.json`
- `storage/runs/<run_id>/tasks_draft.json`

#### Checks

- `bash start.sh`
- `/run_oos`
- artifact inspection

#### DoD

- `/run_oos` создаёт `run_id`, пишет артефакты и возвращает отчёт;
- empty data scenario обрабатывается без падения.

### Итерация 4 — Approval v0 + export

**Статус:** DONE

#### Goal

Добавить approval path и экспорт отчёта.

#### Scope

Включено:

- approve / reject;
- draft/approved/rejected статусы;
- report export.

Не включено:

- execution authority beyond demo tasks;
- operator shell.

#### Реализовано

- кнопки `Approve Tasks` / `Reject`
- статусы задач: `draft / approved / rejected`
- экспорт отчёта:
  - `report.md`
  - `report.html`

#### Deliverable

Есть минимальный operator loop: draft → approve/reject → export artifacts.

#### Artifacts

- `storage/runs/<run_id>/tasks_approved.json`
- `storage/artifacts/<run_id>/report.md`
- `storage/artifacts/<run_id>/report.html`

#### Checks

- `pytest -q`
- approve/reject smoke

#### DoD

- approve/reject сохраняются и видны через `/last`;
- без approve задачи не считаются готовыми.

---

## Этап 2 — Reusable core (итерации 5–10)

### Purpose of stage

Этап 2 делает `beeagent` не просто demo-ботом, а reusable orchestration core с отделением UI, case-слоя, adapter boundary, observability и несколькими агентными сценариями.

Фокус этапа:

- `cases/*` как application layer;
- `adapters/*` как data boundary;
- scheduler;
- basic observability;
- multi-agent baseline;
- richer user-facing demo paths (`quiz`, explainable recommendations).

Изменения этого этапа по умолчанию:

- в основном `runtime-risk`;
- transport / file / state handling changes могут быть `security-sensitive`.

### Итерация 5 — Cases layer v0 + Data Adapter v0

**Статус:** DONE

#### Goal

Отвязать UI от деталей storage и graph. UI вызывает `cases/*`, граф читает данные только через `adapter`.

#### Scope

Включено:

- `cases/*`;
- `DataAdapter`;
- `MockAdapter`;
- graph uses adapter;
- `data.adapter` в config.

Не включено:

- external modules;
- real data integrations.

#### Реализовано

- `src/beeagent_module/cases/`
- `cases/oos.py`
- UI больше не читает `storage/runs/*` напрямую
- `DataAdapter` интерфейс
- `MockAdapter`
- `load_data` node переведён на `adapter.*`
- `data.adapter: "mock"` в config

#### Deliverable

Cases становятся стабильным application layer, а data boundary становится явной.

#### Artifacts

- `storage/runs/<run_id>/run.json` с `adapter` и `trigger`

#### Checks

- `pytest -q`
- transport → case smoke
- adapter-based run smoke

#### DoD

- Telegram-бот работает как раньше, но не читает storage напрямую;
- граф получает данные через adapter;
- один ключ `data.adapter` выбирает адаптер.

### Итерация 6 — Scheduler v0 + Approval gate “обязателен”

**Статус:** DONE

#### Goal

Добавить controlled periodic run path.

#### Scope

Включено:

- простой scheduler loop;
- scheduled runs;
- mandatory approval gate.

Не включено:

- cron/apscheduler;
- distributed background jobs.

#### Реализовано

- `scheduler.enabled`
- `scheduler.interval`
- `scheduler.start_run`
- scheduled-run задачи всегда остаются `draft`
- бот отправляет сообщение на approve/reject

#### Deliverable

Есть автозапуск без обхода approval boundary.

#### Artifacts

- `storage/runs/<run_id>/run.json` с `trigger=scheduled|manual`

#### Checks

- scheduler smoke
- draft-only verification
- approve/reject smoke

#### DoD

- при `scheduler.enabled` бот создаёт run по интервалу;
- без approve задачи остаются draft;
- approve/reject работает для последнего run.

### Итерация 7 — Mini-observability v0 (timing шагов)

**Статус:** DONE

#### Goal

Видеть длительность каждого node и сохранять trace.

#### Scope

Включено:

- `duration_ms` per step;
- step logs;
- `steps.json`.

Не включено:

- external tracing platform;
- distributed tracing.

#### Реализовано

- step timing в логах
- `storage/runs/<run_id>/steps.json`

#### Deliverable

Есть базовая observability по шагам workflow.

#### Artifacts

- `storage/runs/<run_id>/steps.json`

#### Checks

- `pytest -q`
- run artifact inspection

#### DoD

- после run появляется `steps.json`;
- timing шагов воспроизводим.

### Итерация 8 — 2-й агент v0 + multi-channel UI readiness

**Статус:** DONE

#### Goal

Показать расширяемость платформы: новый агент = новый `cases/*` + `agents/*` + кнопка/команда в UI.

#### Scope

Включено:

- второй агент (`promo`);
- тот же run/artifact pattern;
- UI readiness docs / stubs.

Не включено:

- real second transport integration;
- external modules.

#### Реализовано

- `agents/promo/graph.py`
- `cases/promo.py`
- `/run_promo`
- кнопка `Run Promo Scan`
- `ui/slack_stub.py`
- doc contract `UI → cases → agents/adapter/storage`

#### Deliverable

BeeAgent показывает reusable multi-agent pattern.

#### Artifacts

- standard run artifacts per agent

#### Checks

- `pytest -q`
- multi-agent smoke

#### DoD

- второй агент запускается end-to-end;
- артефакты создаются по тому же стандарту;
- transport/case/agent boundary зафиксирован в docs.

### Итерация 9 — Quiz Agent v0 (Pharmacy demo) + WOW UX

**Статус:** DONE

#### Goal

Сделать более интерактивный demo-case: user input → quiz flow → result → artifacts.

#### Scope

Включено:

- quiz case;
- quiz graph;
- session storage;
- Telegram quiz UX;
- quiz artifacts.

Не включено:

- product-grade survey engine;
- multi-tenant quiz platform.

#### Реализовано

- `cases/quiz.py`
- `agents/quiz/graph.py`
- `config/quiz/pharmacy_quiz.json`
- `storage/sessions/<chat_id>.json`
- `/quiz_pharmacy`
- `/last_quiz`
- quiz run artifacts

#### Deliverable

Есть stateful interactive scenario внутри BeeAgent runtime.

#### Artifacts

- `storage/runs/<run_id>/run.json`
- `storage/runs/<run_id>/quiz_answers.json`
- `storage/runs/<run_id>/quiz_result.json`
- `storage/artifacts/<run_id>/report.md`
- `storage/artifacts/<run_id>/report.html`
- `storage/runs/<run_id>/steps.json`

#### Checks

- `bash start.sh`
- full quiz flow
- `pytest -q`

#### DoD

- `/quiz_pharmacy` запускает квиз и проходит до результата;
- сессии и run artifacts сохраняются;
- `/last_quiz` показывает последний результат.

### Итерация 10 — Explainable Recommendations v0 + LLM summary

**Статус:** DONE

#### Goal

Показать “реального AI-агента” на минимальном объёме: объяснимые рекомендации + optional LLM summary.

#### Scope

Включено:

- deterministic recommendation engine;
- LLM summary only for text;
- trace extension;
- recommendation artifacts.

Не включено:

- AI-driven execution;
- black-box decision making.

#### Реализовано

- recommendation engine over OOS results
- structured recommendations:
  - action
  - reason
  - metrics
  - expected_effect
  - confidence
- LLM summary with fallback
- workflow steps:
  - `build_recommendations`
  - `llm_explain`
- recommendation artifacts

#### Deliverable

BeeAgent умеет выдавать explainable recommendation output поверх deterministic core.

#### Artifacts

- `storage/runs/<run_id>/recommendations.json`
- `storage/artifacts/<run_id>/report.md`
- `storage/artifacts/<run_id>/report.html`
- `storage/runs/<run_id>/steps.json`

#### Checks

- `bash start.sh`
- `/run_oos`
- fallback LLM off
- `pytest -q`

#### DoD

- `/run_oos` выдаёт отчёт с рекомендациями;
- recommendation artifacts создаются;
- trace и logs расширены под recommendation path.

---

## Этап 3 — Module platform v0 (итерации 11–14)

### Purpose of stage

Этап 3 переводит `beeagent` из demo/core-каркаса в модульную платформу, к которой можно подключать клиентские доменные пакеты как отдельные репозитории.

Фокус этапа:

- явный module contract;
- module registry;
- runtime context/artifact API;
- capability boundary;
- подготовка к `beeagent-rop`.

Изменения этого этапа по умолчанию:

- в основном `runtime-risk`;
- module loading / capability / file boundary changes — `security-sensitive`.

### Итерация 11 — Module contract v0

**Статус:** DONE

#### Goal

Зафиксировать минимальный внутренний контракт модуля, через который BeeAgent core сможет безопасно и предсказуемо работать с внешними доменными пакетами вроде `beeagent-rop`.

#### Scope

Включено:

- `ModuleContract` / protocol как internal reusable contract;
- обязательный `module_id`;
- `supported_case_types()`;
- `handle(context)` с минимальным contract-level context shape;
- bounded result shapes для ответа модуля;
- явные contract metadata для `read-only / draft-only / execution-capable` semantics;
- import / dispatch smoke на contract уровне;
- docs update по module boundary и contract expectations.

Не включено:

- module registry / discovery;
- remote loading;
- marketplace;
- hot reload;
- полноценный runtime context API;
- artifact API;
- capability execution layer;
- реальная интеграция `beeagent-rop`.

#### Deliverable

В `beeagent` появляется явный и тестируемый внутренний контракт модуля, независимый от одного клиента и достаточный для следующих итераций registry/context/integration.

#### Artifacts

- docs
- tests
- optional contract diagnostics artifact only if действительно нужен

#### Checks

- `pytest -q`
- contract import smoke
- contract dispatch smoke
- manual log check if runtime path touched

#### DoD

- core явно знает, как выглядит модульный contract;
- contract не завязан на `beeagent-rop` или другого одного клиента;
- authority semantics (`read-only / draft-only / execution-capable`) выражены явно;
- bounded result shape проверяется тестами;
- transport/case/core paths не ломаются.

### Итерация 12 — Module registry v0

**Статус:** DONE

#### Goal

Добавить минимальный локальный registry, через который BeeAgent сможет явно и предсказуемо находить, валидировать и подключать установленные package-based модули вроде `beeagent-rop`.

#### Scope

Включено:

- local registry для installed python packages;
- config-driven module declaration;
- config-driven enable/disable modules;
- deterministic active module resolution;
- import + contract validation against `ModuleContract`;
- explicit refusal for missing / disabled / invalid modules;
- diagnostics по loaded / disabled / missing / invalid modules;
- conflict handling for ambiguous module ownership if applicable;
- optional registry diagnostics artifact.

Не включено:

- remote registry;
- dynamic marketplace;
- hot reload;
- arbitrary filesystem scanning;
- container orchestration;
- runtime context API;
- artifact API;
- capability boundary;
- реальный client flow dispatch beyond registry-level smoke.

#### Реализовано

- `src/beeagent_module/core/module_registry.py` — `ModuleRegistry`, `ModuleEntry`, `ModuleState`, `build_registry`
- `config/settings.yml` — блок `modules.registry` (config-driven declaration)
- `src/beeagent_module/core/settings.py` — fail-fast валидация `modules.*` и каждого элемента registry
- `src/beeagent_module/core/app.py` — вызов `build_registry` при старте
- `tests/test_module_registry.py` — сценарии: loaded, missing, disabled, invalid, diagnostics artifact, mixed
- `beeagent-rop` объявлен в registry; текущий `RopModule` не удовлетворяет `ModuleContract` (нет `authority`) → state=invalid (ожидаемо до итерации 15)

#### Deliverable

BeeAgent умеет по конфигу явно определить локально установленные модули, загрузить валидный модуль, отказать explainably в случае missing/disabled/invalid module и показать registry diagnostics.

#### Artifacts

- `storage/interfaces/modules.json` (always-on registry diagnostics artifact)

#### Checks

- registered module scenario — `test_registry_registered_module`
- missing module scenario — `test_registry_missing_module`
- disabled module scenario — `test_registry_disabled_module`
- invalid contract scenario — `test_registry_invalid_contract`
- diagnostics artifact — `test_registry_diagnostics_artifact`
- `uv run pytest -q`
- smoke run
- log verification
- diagnostics artifact verification

#### DoD

- активный модуль определяется явно и предсказуемо;
- module loading не опирается на hidden defaults или ad hoc imports;
- missing / disabled / invalid module дают explainable error/diagnostics;
- registry semantics не завязаны на одного клиента;
- BeeAgent подготовлен к следующей итерации runtime context и к интеграции `beeagent-rop`.

### Итерация 13 — Runtime context + artifact API v0

**Статус:** PLANNED

#### Goal

Дать модулю минимальный безопасный runtime context и стандартный core-managed способ писать module-linked artifacts без прямой зависимости от private internals BeeAgent.

#### Scope

Включено:

- minimal runtime context envelope для module execution;
- `run_id`, `session_id`, `case_type`, `module_id`, `authority`, input payload;
- explicit context propagation from core to module;
- minimal artifact write/read API under core control;
- safe storage path contract for module-linked artifacts;
- standard linkage `run -> module outputs`;
- predictable module artifact location and naming rules;
- tests for context propagation and artifact API behavior.

Не включено:

- distributed state store;
- queue framework;
- external DB as source of truth;
- broad storage abstraction platform;
- capability layer;
- full client flow dispatch;
- real production integration with external systems.

#### Deliverable

Модуль может выполняться внутри BeeAgent runtime с platform-owned context и писать module-linked artifacts через explicit core API, не зная private storage internals.

#### Artifacts

- standard run artifacts
- module-linked artifacts
- optional diagnostics if needed for context/artifact verification

#### Checks

- `pytest -q`
- context propagation smoke
- artifact API smoke
- manual log verification
- manual artifact verification

#### DoD

- модуль получает explicit runtime context от core;
- модуль пишет artifacts через core-managed API, а не напрямую в произвольные пути;
- linkage `run_id -> module artifacts` воспроизводимо и понятно по logs/artifacts;
- решение не завязано на одного клиента и не тащит capability logic раньше времени.

### Итерация 14 — Capability boundary v0

**Статус:** PLANNED

#### Goal

Разделить module logic и внешние tool/MCP/n8n calls через единый capability layer.

#### Scope

Включено:

- capability call abstraction;
- clear boundary `module → capability → MCP/n8n/system`;
- explicit errors / timeout / refusal surface;
- запрет на hidden fallback execution path;
- принцип: long-running state остаётся в BeeAgent.

Не включено:

- full workflow engine rewrite;
- перенос long-running state в n8n;
- ad hoc tool calls прямо из client module logic без abstraction.

#### Deliverable

Модуль может вызывать внешние capabilities без знания transport details и без размывания core authority boundaries.

#### Artifacts

- logs
- optional capability diagnostics

#### Checks

- `pytest -q`
- mock capability call scenario
- refusal / timeout scenario

#### DoD

- module code не завязан напрямую на случайный tool transport;
- long-running state не уезжает в n8n/MCP layer.

---

## Этап 4 — First real client module integration (итерации 15–18)

### Purpose of stage

Этап 4 подключает первый реальный клиентский модуль `beeagent-rop` и доводит BeeAgent до состояния, пригодного для Discovery → MVP → Pilot под конкретного клиента.

Фокус этапа:

- integration of `beeagent-rop`;
- run/session/artifact linkage;
- bounded operator flow;
- client delivery readiness.

Изменения этого этапа по умолчанию:

- в основном `runtime-risk`;
- capability/file/integration boundaries — `security-sensitive`.

### Итерация 15 — `beeagent-rop` integration v0

**Статус:** PLANNED

#### Goal

Подключить `beeagent-rop` к core через module contract и registry.

#### Scope

Включено:

- module loading;
- ROP module dispatch;
- context passing;
- artifact linkage;
- first installed local module path.

Не включено:

- production Bitrix connector;
- pilot hardening.

#### Deliverable

BeeAgent умеет вызывать модуль РОП как первый реальный внешний доменный модуль.

#### Artifacts

- standard run artifacts
- module-linked artifacts

#### Checks

- `pytest -q`
- integration smoke with installed module

#### DoD

- BeeAgent вызывает модуль РОП end-to-end без ручных костылей;
- linkage `run -> rop module outputs` видна в artifacts.

### Итерация 16 — Client operator flow v0

**Статус:** PLANNED

#### Goal

Собрать первый понятный operator/client flow для работы с ROP module.

#### Scope

Включено:

- запуск клиентского case;
- summary output;
- artifact linkage;
- basic operator-facing output;
- first bounded chat/operator interaction path.

Не включено:

- final UI;
- auto actions в клиентской CRM.

#### Deliverable

Есть первый run flow, который можно показывать как клиентский MVP path.

#### Artifacts

- `storage/runs/<run_id>/...`
- module summary artifacts

#### Checks

- `pytest -q`
- run smoke with installed ROP module
- manual artifact inspection

#### DoD

- ROP flow запускается и выдаёт explainable result;
- operator может понять, что произошло, без чтения кода.

### Итерация 17 — Discovery/MVP handoff hardening v0

**Статус:** PLANNED

#### Goal

Подготовить BeeAgent core к первому клиентскому циклу: Discovery → MVP → Pilot.

#### Scope

Включено:

- stable run/session/artifact contracts;
- fix critical integration edges;
- docs update for delivery flow;
- better degraded/refusal behavior.

Не включено:

- broad multi-client abstractions;
- full product shell.

#### Deliverable

BeeAgent core готов поддерживать первый клиентский delivery cycle без хаоса в runtime.

#### Artifacts

- stable run artifacts
- updated docs

#### Checks

- `pytest -q`
- degraded/failure scenarios
- client-flow smoke

#### DoD

- core стабилен для первой поставки клиентского модуля;
- критические точки отказа explainable.

### Итерация 18 — Pilot support baseline

**Статус:** PLANNED

#### Goal

Сделать минимальный support-ready baseline для пилота клиентского модуля.

#### Scope

Включено:

- diagnostics для module integration;
- clearer logs / reason codes;
- operator-visible failure points;
- basic weekly reporting support via artifacts/logs.

Не включено:

- full product shell;
- advanced dashboards;
- broad tenant support.

#### Deliverable

Пилот можно сопровождать без ручного чтения исходников и ad hoc дебага.

#### Artifacts

- logs
- diagnostics artifacts if needed
- module-linked run artifacts

#### Checks

- `pytest -q`
- degraded/failure scenarios
- manual inspection of logs and artifacts

#### DoD

- critical точки отказа explainable для команды разработки и сопровождения;
- weekly pilot work можно вести по артефактам и понятным статусам.

---

## Этап 5 — Operator / product shell v1 (ориентир)

### Purpose of stage

Этап 5 добавляет минимальный operator/client-facing shell поверх уже существующего orchestrator и module contracts.

Фокус этапа:

- bounded operator UI / chat flow;
- run overview;
- module summaries;
- stable backend contracts;
- minimal safe actions.

### Expected direction

Этап должен идти малыми шагами:

- сначала read-only operator/client summaries;
- затем stable backend/API contracts;
- затем minimal safe actions;
- только потом более широкий UI.

### Expected size

Ориентир: **3–5 итераций**.

---

## Этап 6 — Multi-module scaling v0 (ориентир)

### Purpose of stage

Этап 6 расширяет `beeagent` от первого клиентского модуля к платформе из нескольких доменных модулей.

Фокус этапа:

- `beescan`;
- `merch`;
- shared module diagnostics;
- better tenant/module separation;
- reusable capability policies.

### Expected direction

Этап должен идти малыми шагами:

- сначала второй реальный модуль;
- потом общие module diagnostics;
- потом common operator/product contracts;
- затем более зрелая multi-module platform.

### Expected size

Ориентир: **4–6 итераций**.

---

## Related process documents

Для выполнения итераций вместе с этим ROADMAP используются:

- `docs/DEV_GUIDE.md` — как запускать проект и как работать с AI/Copilot в рамках проекта;
- `docs/SDLC.md` — lightweight process, change levels, required quality/security checks, DoD flow;
- `docs/SECURITY.md` — secure development rules и security checks для разных типов изменений.
