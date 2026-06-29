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

| Phase                                     | Status  | What it means                                                                                                                      |
| ----------------------------------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| **Phase A — Demo skeleton**               | DONE    | Сформирован демонстрационный runtime: Telegram transport, mock data, базовые agents/cases, run artifacts, approval, export.        |
| **Phase B — Reusable orchestration core** | DONE    | BeeAgent перестал быть только демо-кейсом и получил reusable cases/adapters/scheduler/observability/multi-agent baseline.          |
| **Phase C — Module platform**             | DONE    | Вводится явный module contract, registry, runtime context, artifact API и bounded capability layer для внешних доменных модулей.   |
| **Phase D — First real client delivery**  | PLANNED | Подключается первый реальный доменный модуль (`beeagent-rop`), делается Discovery → MVP → Pilot flow под клиента.                  |
| **Phase E — Operator / product shell**    | PLANNED | Появляются operator-facing и client-facing controlled interfaces: summaries, status, bounded actions, stable backend contracts.    |
| **Phase F — Multi-module platform**       | FUTURE  | BeeAgent становится базой для нескольких доменных модулей (`ROP`, `BeeScan`, `Merch` и др.) с единым runtime и reusable contracts. |

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

**Статус:** DONE

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

**Статус:** DONE

#### Goal

Разделить module logic и внешние data/action calls через единый capability layer, чтобы доменные модули вроде `beeagent-rop` могли запрашивать email / Bitrix / parser / attachment capabilities без прямой зависимости от transport details, MCP/n8n/system clients и без размывания authority boundaries.

#### Scope

Включено:

- capability call abstraction в core;
- minimal capability request / response contract v0;
- clear boundary `module → capability → MCP/n8n/system`;
- mock/local capability provider for tests;
- explicit result states:
  - `ok`
  - `refused`
  - `timeout`
  - `error`
- explicit refusal / timeout / degraded surface;
- authority-aware capability semantics:
  - `read_only`
  - `draft_only`
  - `execution_capable`
- capability examples aligned with ROP Discovery:
  - `email.search`
  - `email.read`
  - `bitrix.find_lead`
  - `bitrix.read_timeline`
  - `parser.lookup_email`
  - `attachment.extract_text`
- запрет на hidden fallback execution path;
- принцип: long-running state, retry, batching, checkpoints и policy остаются в BeeAgent;
- logs / optional diagnostics для explainability.

Не включено:

- production Email connector;
- production Bitrix connector;
- production parser connector;
- production attachment reader/OCR;
- full MCP/n8n transport implementation;
- full workflow engine rewrite;
- перенос long-running state в n8n/MCP/tool layer;
- ad hoc tool/API calls прямо из client module logic;
- client-specific ROP business rules в BeeAgent core.

#### Deliverable

BeeAgent получает минимальный capability boundary v0: модуль может вызвать capability через core-owned abstraction и получить explainable `ok/refused/timeout/error` result без знания transport details и без прямого доступа к внешним systems.

#### Artifacts

- logs
- optional `storage/interfaces/capabilities.json`
- tests

#### Checks

- `pytest -q`
- mock capability call scenario
- refusal scenario
- timeout scenario
- unknown capability scenario
- authority boundary scenario
- no hidden fallback scenario
- smoke run
- log verification
- optional diagnostics verification

#### DoD

- module code не завязан напрямую на случайный tool transport;
- capability calls проходят только через explicit core abstraction;
- refusal / timeout / error paths explainable по logs/tests;
- hidden fallback execution path отсутствует;
- long-running state не уезжает в n8n/MCP/tool layer;
- решение не завязано на `beeagent-rop`, но покрывает будущие ROP capability needs.

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

### Итерация 15 — `beeagent-rop` integration smoke v0

**Статус:** DONE

#### Goal

Подключить установленный `beeagent-rop` к BeeAgent core как первый реальный внешний доменный модуль и подтвердить end-to-end dispatch через registry, runtime context и artifact API.

#### Scope

Включено:

- загрузка `beeagent-rop` через `modules.registry`;
- проверка, что registry больше не помечает `beeagent-rop` как `invalid`;
- ROP module dispatch через existing core runtime path;
- context passing: `run_id`, `session_id`, `case_type`, `module_id`, `authority`, `payload`;
- artifact linkage через `ArtifactAPI`;
- integration smoke с установленным local package;
- registry/runtime diagnostics в logs/artifacts;
- минимальный sample payload для `lead_classification` или `duplicate_resolution`.

Не включено:

- production Bitrix connector;
- production email connector;
- n8n/MCP transport implementation;
- attachment deep parsing;
- ROP summary/operator UX;
- pilot hardening;
- изменение бизнес-логики `beeagent-rop`;
- client-specific rules в BeeAgent core.

#### Deliverable

BeeAgent умеет загрузить и вызвать `beeagent-rop` как first real module через стандартный registry/runtime path, а результат вызова воспроизводимо связан с `run_id` в module-linked artifacts.

#### Artifacts

- `storage/interfaces/modules.json`
- `storage/runs/<run_id>/module-beeagent-rop/module_result.json`
- optional module output artifact from `beeagent-rop`
- `logs/app.log`

#### Checks

- `uv run pytest -q`
- registry integration smoke with installed `beeagent-rop`
- module dispatch smoke via `execute_module_case`
- artifact linkage verification
- log verification
- no secret leakage check

#### DoD

- `beeagent-rop` загружается как valid module через registry;
- BeeAgent вызывает `beeagent-rop` end-to-end без ручных костылей;
- `ModuleResult` проходит consistency checks в `execute_module_case`;
- linkage `run_id -> module-beeagent-rop -> module_result.json` видна в artifacts;
- BeeAgent core не содержит ROP-specific business logic;
- production connectors не подключены и не вызываются.

### Итерация 16 — ROP operator run flow v0

**Статус:** DONE

#### Goal

Собрать первый понятный operator-facing flow для запуска `beeagent-rop` через BeeAgent core: оператор должен видеть не только raw module artifacts, но и краткий explainable результат запуска без чтения исходников или внутренних JSON.

#### Scope

Включено:

- core/case-level запуск ROP module через существующий registry/runtime path;
- operator-facing wrapper над `execute_module_case(...)`;
- bounded input payload для первого ROP case smoke, без production connectors;
- readable summary output на основе `ModuleResult`;
- artifact linkage:
  - `run_id`;
  - `module_result.json`;
  - operator summary artifact;
- basic degraded output, если модуль не загружен, case unsupported или module result не `ok`;
- минимальная интеграция с текущим UI/transport path там, где это уже естественно для проекта;
- tests на successful run и degraded/refusal scenario.

Не включено:

- final UI;
- production Email/Bitrix/parser/attachment connectors;
- auto actions в CRM;
- полноценная ROP business summary;
- recommendation builder;
- manager scoring;
- перенос ROP business logic в BeeAgent core.

#### Deliverable

BeeAgent получает первый operator-ready ROP run flow: установленный `beeagent-rop` можно запустить через core-level path, получить readable summary и воспроизводимые artifacts, достаточные для демонстрации клиентского MVP path.

#### Artifacts

- `storage/runs/<run_id>/module-beeagent-rop/module_result.json`
- `storage/runs/<run_id>/module-beeagent-rop/<case_type>_result.json`, если модуль пишет case artifact
- `storage/runs/<run_id>/operator_summary.json` или аналогичный operator-facing artifact
- logs

#### Checks

- `pytest -q`
- targeted ROP operator flow tests
- run smoke with installed `beeagent-rop`
- degraded scenario: module missing / unsupported case / non-ok result
- manual artifact inspection
- log verification

#### DoD

- ROP flow запускается через BeeAgent-owned path, а не ad hoc script;
- operator-facing summary объясняет, что произошло, какой модуль/case был вызван, какой статус получен и где лежат artifacts;
- linkage `run_id -> module result -> operator summary` воспроизводимо;
- BeeAgent core не содержит ROP business rules;
- production connectors и CRM actions не добавлены.

### Итерация 17 — ROP input source contract and batch handoff v0

**Статус:** DONE

#### Goal

Добавить в BeeAgent первый platform-level контракт ROP input source и batch/operator handoff flow, чтобы `beeagent-rop` запускался через core на controlled batch input, а не на одиночном demo payload.

#### Scope

Включено:

- config-driven ROP input source contract:
  - `rop.sources`;
  - `source_id`;
  - `source_type`;
  - `enabled`;
  - `authority`;
  - `items_max`;
  - source-specific settings без secrets;
- первый безопасный source type:
  - `json_batch` (source_type value);
- controlled sample batch file для dev/smoke;
- загрузка batch payload из configured source;
- валидация batch shape;
- нормализация batch items в payload, совместимый с `beeagent-rop`;
- запуск `beeagent-rop` через существующий `ModuleRegistry` / `execute_module_case`;
- основной MVP case:
  - `rop_summary`, если модуль поддерживает;
- fallback/degraded behavior:
  - missing source;
  - no enabled source;
  - multiple enabled sources, если v0 разрешает только один;
  - disabled source;
  - invalid source config;
  - missing batch file;
  - invalid batch shape;
  - missing module;
  - unsupported case type;
  - module non-ok result;
- artifacts:
  - `intake_metadata.json`;
  - `normalized_events.json`;
  - module artifacts;
  - `operator_summary.json`;
- Telegram command или dev/operator path, если это минимально и не раздувает scope;
- README / DEV_GUIDE / ROADMAP update.

#### Не включено:

- IMAP/live mailbox connector;
- `hotline@welding.kz` live access;
- stream/listener;
- production Bitrix/email/1C connectors;
- CRM write-back;
- OCR;
- attachment deep parsing;
- ROP classification/summary/recommendation rules в BeeAgent;
- hardcoded client mailbox;
- broad multi-client abstractions.

#### Deliverable

BeeAgent умеет запускать ROP flow через configurable batch input source и выдавать operator-facing summary с reproducible artifacts без live mailbox dependency.

#### Artifacts

- `storage/runs/<run_id>/intake_metadata.json`
- `storage/runs/<run_id>/normalized_events.json`
- `storage/runs/<run_id>/module-beeagent-rop/module_result.json`
- optional `storage/runs/<run_id>/module-beeagent-rop/rop_summary_result.json`
- `storage/runs/<run_id>/operator_summary.json`
- `storage/interfaces/modules.json`

#### Checks

- `uv run pytest -q`
- targeted ROP source/batch tests
- batch handoff smoke with installed `beeagent-rop`
- degraded/failure scenarios
- manual artifact inspection
- log verification
- no secret leakage check
- SAST mindset review

#### DoD

- source не захардкожен;
- BeeAgent не содержит ROP classification/summary/recommendation rules;
- source contract читается из config и валидируется fail-fast;
- module вызывается через existing module runtime path;
- `rop_summary` batch smoke проходит;
- artifacts воспроизводимы и понятны;
- degraded paths explainable;
- logs/artifacts не содержат secrets;
- production connectors не добавлены.

### Итерация 18 — ROP mailbox_readonly source and hotline smoke v0

**Статус:** DONE

#### Goal

Добавить в BeeAgent source type `mailbox_readonly` и использовать `hotline@welding.kz` как первый configurable read-only mailbox source для ROP MVP smoke: BeeAgent должен получить последние N писем, безопасно нормализовать их в events, вызвать `beeagent-rop` через existing module runtime path и записать operator-facing artifacts без destructive mailbox actions и без CRM write-back.

#### Scope

**Включено:**

- новый source type:
  - `mailbox_readonly`;
- config-driven source declaration в `rop.sources`;
- `hotline` только как `source_id` / config entry, без хардкода в runtime logic;
- mailbox config без secrets:
  - `host`;
  - `port`;
  - `use_ssl`;
  - `folder`;
  - `username_env`;
  - `password_env`;
  - `items_max`;
- credentials только через env;
- read-only fetch последних N сообщений;
- no delete/archive/reply/mark-as-read;
- minimal mailbox adapter с fake mailbox tests;
- normalizer:
  - sender;
  - recipients / cc, если безопасно;
  - subject;
  - date/message_id;
  - text/plain или safe text body preview;
  - attachment metadata только без чтения content;
- sanitized artifacts:
  - `source_diagnostics.json`;
  - `intake_metadata.json`;
  - `normalized_events.json`;
  - module artifacts;
  - `operator_summary.json`;
- dispatch в `beeagent-rop` через `execute_module_case(...)`;
- degraded behavior:
  - missing credentials;
  - invalid source config;
  - auth failure;
  - mailbox unavailable;
  - empty inbox;
  - malformed message;
  - unsupported module/case;
  - module non-ok result;
- docs update.

#### Не включено:

- continuous stream/listener/polling;
- checkpoint/seen-message persistence, если это не минимально и безопасно;
- multi-mailbox routing;
- full source-of-truth mapping;
- employee mailbox ingestion;
- Bitrix/1C connectors;
- CRM write-back;
- OCR;
- attachment deep parsing;
- saving raw `.eml`;
- automatic mailbox actions;
- n8n/MCP implementation;
- ROP business rules в BeeAgent.

#### Deliverable

BeeAgent умеет выполнить controlled read-only smoke на mailbox source: получить последние N писем из configured mailbox, нормализовать их в ROP-compatible events, вызвать `beeagent-rop` и показать operator summary с воспроизводимыми artifacts.

#### Artifacts

- `storage/runs/<run_id>/source_diagnostics.json`
- `storage/runs/<run_id>/intake_metadata.json`
- `storage/runs/<run_id>/normalized_events.json`
- `storage/runs/<run_id>/module-beeagent-rop/module_result.json`
- optional `storage/runs/<run_id>/module-beeagent-rop/rop_summary_result.json`
- `storage/runs/<run_id>/operator_summary.json`
- `logs/app.log`

#### Checks

- `uv run pytest -q`
- mailbox adapter tests with fake mailbox
- missing credentials scenario
- auth failure scenario
- mailbox unavailable scenario
- empty inbox scenario
- malformed message scenario
- live smoke with `items_max`, если реальные credentials доступны
- manual artifact inspection
- log verification
- secret leakage check
- SAST
- SCA only if dependencies changed

#### DoD

- mailbox source configurable, not hardcoded;
- mailbox access is read-only;
- credentials are read only from env and never appear in logs/artifacts;
- latest N messages become normalized events;
- attachment content is not parsed, only metadata is captured;
- `beeagent-rop` receives normalized payload through existing module runtime path;
- operator sees result without reading code;
- degraded paths are explainable;
- no destructive mailbox/CRM actions exist;
- BeeAgent core contains no ROP classification/summary/recommendation rules.

### Итерация 19 — ROP live batch classification handoff v0

**Статус:** DONE

#### Goal

Сделать live ROP batch flow семантически полезным: после загрузки `json_batch` или `mailbox_readonly` BeeAgent должен сначала вызвать `beeagent-rop` case `lead_classification` для каждого normalized event, сохранить `classified_events.json`, а затем вызвать `beeagent-rop` case `rop_summary` уже по classified events.

#### Scope

**Включено:**

- batch classification handoff внутри existing ROP source flow;
- вызов `beeagent-rop` `lead_classification` для каждого normalized event через existing module runtime path;
- сбор classified events без добавления ROP business rules в BeeAgent;
- artifact:
  - `classified_events.json`;
- передача в `rop_summary` не raw normalized events, а classified events;
- operator summary с classification diagnostics:
  - normalized count;
  - classified count;
  - classification failed count;
  - summary status;
  - artifact refs;
- degraded behavior:
  - per-event classification failure не валит весь batch;
  - failed event получает controlled fallback item:
    - `case_type: "unknown"`;
    - `priority: "medium"`;
    - `reason_code: "classification_error"`;
    - `confidence: 0.0`;
    - `is_fallback: true`;
- tests на successful handoff и degraded per-event classification;
- repeated live smoke на `folder=welding`, если credentials доступны;
- docs update.

#### Не включено:

- ROP business rules в BeeAgent;
- изменение логики классификации в `beeagent-rop`;
- AI classification;
- Bitrix/1C connectors;
- CRM write-back;
- OCR;
- attachment deep parsing;
- continuous listener/polling;
- multi-mailbox routing;
- automatic actions;
- n8n/MCP implementation.

#### Deliverable

BeeAgent live source flow вызывает `beeagent-rop` в правильной последовательности: normalized events → lead classification → classified events → ROP summary. `rop_summary` получает classified events, а не raw mailbox events.

#### Artifacts

- `storage/runs/<run_id>/source_diagnostics.json`
- `storage/runs/<run_id>/intake_metadata.json`
- `storage/runs/<run_id>/normalized_events.json`
- `storage/runs/<run_id>/classified_events.json`
- `storage/runs/<run_id>/module-beeagent-rop/module_result.json`
- optional `storage/runs/<run_id>/module-beeagent-rop/lead_classification_result.json`
- optional `storage/runs/<run_id>/module-beeagent-rop/rop_summary_result.json`
- `storage/runs/<run_id>/operator_summary.json`
- `logs/app.log`

#### Checks

- `uv run pytest -q`
- targeted ROP batch classification handoff tests
- successful source → classify → summary test
- per-event classification failure scenario
- module missing / unsupported case degraded scenario
- repeated live smoke with `folder=welding`, `items_max=10`, if credentials are available
- manual artifact inspection
- log verification
- secret leakage check
- no ROP business rules in BeeAgent core
- SAST mindset review
- SCA only if dependencies changed

#### DoD

- `rop_summary` receives classified events;
- `classified_events.json` is created and referenced in `operator_summary.json`;
- per-event classification failures are visible and do not crash whole batch;
- BeeAgent core contains no ROP classification rules;
- all domain classification remains inside `beeagent-rop`;
- artifacts are reproducible and explainable;
- no destructive mailbox/CRM actions exist;
- secrets do not appear in logs/artifacts.

### Итерация 20 — ROP CLI and review export v1

**Статус:** DONE

#### Goal

Сделать нормальный operator/dev CLI для ROP MVP flow, чтобы оператор мог запускать BeeAgent ROP pipeline через `./start.sh rop ...` без Telegram, без `test.py` и без ручного Python-скрипта.

BeeAgent должен уметь одной командой:

- запустить configured ROP source flow;
- получить последние N событий из `json_batch` или `mailbox_readonly`;
- прогнать события через `beeagent-rop` `lead_classification`;
- собрать `classified_events.json`;
- вызвать `rop_summary`;
- записать standard artifacts;
- вывести понятный terminal summary;
- экспортировать review TSV для сверки с человеком / заказчиком.

#### Scope

**Включено:**

- CLI entrypoint через existing `start.sh`:
  - `./start.sh rop run`;
  - `./start.sh rop summary`;
  - `./start.sh rop export-review`;
- проброс аргументов из `start.sh` в `config/start.py`;
- CLI dispatch в BeeAgent app/start layer без отдельного сервиса;
- сохранение backward compatibility:
  - `./start.sh` работает как раньше через `run.mode`;
  - `./start.sh telegram` явно запускает Telegram mode;
- запуск existing `run_rop_batch_case(...)`;
- чтение `rop.sources` из `config/settings.yml`;
- выбор source через `--source-id`;
- override `items_max` через `--items-max` без изменения `settings.yml`;
- override `period` через `--period` без изменения `settings.yml`;
- explicit `--run-id`;
- terminal output:
  - `run_id`;
  - source id/type;
  - loaded/classified/failed counts;
  - module status;
  - summary;
  - artifact paths;
- команда `summary`:
  - читает `storage/runs/<run_id>/operator_summary.json`;
  - выводит краткий readable summary;
- команда `export-review`:
  - читает `normalized_events.json`;
  - читает `classified_events.json`;
  - создаёт `rop_review_table.tsv`;
- TSV columns для human review:
  - `event_id`;
  - `source_id`;
  - `sender`;
  - `subject`;
  - `bot_case_type`;
  - `bot_reason_code`;
  - `bot_confidence`;
  - `bot_is_fallback`;
  - `human_case_type`;
  - `should_rop_see`;
  - `bitrix_status`;
  - `notes`;
  - `correct_action`;
- degraded behavior:
  - source not found;
  - source disabled;
  - no active source;
  - missing mailbox credentials;
  - mailbox unavailable;
  - module missing;
  - partial classification failure;
  - missing run artifacts for `summary` / `export-review`;
- docs update:
  - `docs/ROADMAP.md`;
  - `README.ru.md`;
  - `docs/DEV_GUIDE.md`.

**Не включено:**

- Telegram requirement for ROP CLI;
- Telegram UI changes, кроме сохранения существующего поведения;
- web UI;
- scheduler / listener / polling daemon;
- Bitrix API;
- 1C;
- CRM write-back;
- automatic task creation;
- OCR;
- attachment deep parsing;
- AI classification;
- ROP business rules в BeeAgent;
- изменения classification logic в `beeagent-rop`;
- multi-mailbox routing beyond existing `source_id`.

#### Реализовано

- `src/beeagent_module/core/cli.py` — CLI handler module с тремя командами:
  - `handle_rop_run()` — запуск ROP batch с in-memory overrides;
  - `handle_rop_summary()` — показ operator summary;
  - `handle_rop_export_review()` — генерация TSV;
- `config/start.py` — обновлен для парсинга CLI args и dispatch:
  - `./start.sh` → use `run.mode` from settings;
  - `./start.sh telegram` → explicit Telegram;
  - `./start.sh rop run/summary/export-review` → dispatch to CLI handler;
- `_apply_source_overrides()` — in-memory source override logic для CLI args;
- `_build_review_tsv_rows()` — TSV generation from normalized + classified events;
- `tests/test_cli_rop_commands.py` — targeted tests:
  - backward compat (no args, telegram);
  - rop run with batch source;
  - rop summary with valid artifact;
  - rop export-review with TSV creation;
  - error scenarios (missing source, disabled source, missing artifacts);
- docs update в DEV_GUIDE, README, ROADMAP.

#### Deliverable

Оператор может выполнить ROP MVP flow без Telegram и без `test.py`:

```bash
./start.sh rop run \
  --source-id hotline_mailbox \
  --items-max 20 \
  --run-id live-review-2026-05-15-welding-20 \
  --period 2026-05

./start.sh rop summary \
  --run-id live-review-2026-05-15-welding-20

./start.sh rop export-review \
  --run-id live-review-2026-05-15-welding-20 \
  --format tsv
```

Artifacts:

- `storage/runs/<run_id>/source_diagnostics.json`
- `storage/runs/<run_id>/intake_metadata.json`
- `storage/runs/<run_id>/normalized_events.json`
- `storage/runs/<run_id>/classified_events.json`
- `storage/runs/<run_id>/module-beeagent-rop/module_result.json`
- `storage/runs/<run_id>/module-beeagent-rop/rop_summary_result.json`
- `storage/runs/<run_id>/operator_summary.json`
- `storage/runs/<run_id>/rop_review_table.tsv`
- `logs/app.log`

#### Checks

- `uv run pytest -q`
- targeted CLI tests (argument parsing, overrides, backward compat);
- smoke: `./start.sh rop run --source-id rop_batch_sample --items-max 2 --run-id smoke-rop-cli-json`;
- smoke: `./start.sh rop summary --run-id smoke-rop-cli-json`;
- smoke: `./start.sh rop export-review --run-id smoke-rop-cli-json --format tsv`;
- backward compat: `./start.sh` without args;
- backward compat: `./start.sh telegram`;
- artifact inspection;
- log verification;
- secret leakage check;
- no direct `beeagent_rop` imports in core;
- TSV structure verification.

#### DoD

- `./start.sh` работает как раньше (no args → `run.mode` from settings);
- `./start.sh telegram` явно запускает Telegram mode;
- `./start.sh rop run [args]` запускает ROP batch без Telegram;
- CLI overrides (`--source-id`, `--items-max`, `--period`, `--run-id`) применяются in-memory только;
- disabled source не включается silent CLI, вернёт fail-fast error;
- source not found вернёт fail-fast error;
- `rop summary` читает `operator_summary.json` и выводит readable summary;
- `rop run` автоматически создаёт `rop_review_table.tsv` для текущего run;
- `rop export-review` остаётся ручным повторным экспортом `rop_review_table.tsv` для уже существующего run;
- последние 5 TSV колонок пусты для оператора заполнять вручную;
- CLI использует existing `run_rop_batch_case()`, не дублирует orchestration;
- `rop.sources` остаётся source of truth для источников;
- BeeAgent core не содержит ROP business rules;
- artifacts создаются воспроизводимо и консистентны с логами;
- secrets не попадают в logs/artifacts;
- docs обновлены.
- override `items_max` через `--items-max` без изменения `settings.yml`;
- override `period` через `--period` без изменения `settings.yml`;
- explicit `--run-id`;
- terminal output:
  - `run_id`;
  - source id/type;
  - loaded/classified/failed counts;
  - module status;
  - summary;
  - artifact paths;
- команда `summary`:
  - читает `storage/runs/<run_id>/operator_summary.json`;
  - выводит краткий readable summary;
- команда `export-review`:
  - читает `normalized_events.json`;
  - читает `classified_events.json`;
  - создаёт `rop_review_table.tsv`;
- TSV columns для human review:
  - `event_id`;
  - `source_id`;
  - `sender`;
  - `subject`;
  - `bot_case_type`;
  - `bot_reason_code`;
  - `bot_confidence`;
  - `bot_is_fallback`;
  - `human_case_type`;
  - `should_rop_see`;
  - `bitrix_status`;
  - `notes`;
  - `correct_action`;
- degraded behavior:
  - source not found;
  - source disabled;
  - no active source;
  - missing mailbox credentials;
  - mailbox unavailable;
  - module missing;
  - partial classification failure;
  - missing run artifacts for `summary` / `export-review`;
- docs update:
  - `docs/ROADMAP.md`;
  - `README.ru.md`;
  - `docs/DEV_GUIDE.md`.

**Не включено:**

- Telegram requirement for ROP CLI;
- Telegram UI changes, кроме сохранения существующего поведения;
- web UI;
- scheduler / listener / polling daemon;
- Bitrix API;
- 1C;
- CRM write-back;
- automatic task creation;
- OCR;
- attachment deep parsing;
- AI classification;
- ROP business rules в BeeAgent;
- изменения classification logic в `beeagent-rop`;
- multi-mailbox routing beyond existing `source_id`.

#### Deliverable

Оператор может выполнить ROP MVP flow без Telegram и без `test.py`:

```bash
./start.sh rop run \
  --source-id hotline_mailbox \
  --items-max 20 \
  --run-id live-review-2026-05-15-welding-20 \
  --period 2026-05
```

После запуска появляются стандартные artifacts:

```text
storage/runs/<run_id>/source_diagnostics.json
storage/runs/<run_id>/intake_metadata.json
storage/runs/<run_id>/normalized_events.json
storage/runs/<run_id>/classified_events.json
storage/runs/<run_id>/module-beeagent-rop/module_result.json
storage/runs/<run_id>/module-beeagent-rop/rop_summary_result.json
storage/runs/<run_id>/operator_summary.json
```

И отдельной командой можно получить TSV для human review:

```bash
./start.sh rop export-review \
  --run-id live-review-2026-05-15-welding-20 \
  --format tsv
```

Artifact:

```text
storage/runs/<run_id>/rop_review_table.tsv
```

#### Expected commands

```bash
./start.sh
```

Сохраняет текущее поведение: использует `run.mode` из `config/settings.yml`.

```bash
./start.sh telegram
```

Явно запускает Telegram transport.

```bash
./start.sh rop run \
  --source-id hotline_mailbox \
  --items-max 20 \
  --run-id live-review-2026-05-15-welding-20 \
  --period 2026-05
```

Запускает ROP source flow.

```bash
./start.sh rop summary \
  --run-id live-review-2026-05-15-welding-20
```

Показывает summary по готовому run.

```bash
./start.sh rop export-review \
  --run-id live-review-2026-05-15-welding-20 \
  --format tsv
```

Создаёт review TSV.

#### Artifacts

- `storage/runs/<run_id>/source_diagnostics.json`
- `storage/runs/<run_id>/intake_metadata.json`
- `storage/runs/<run_id>/normalized_events.json`
- `storage/runs/<run_id>/classified_events.json`
- `storage/runs/<run_id>/module-beeagent-rop/module_result.json`
- `storage/runs/<run_id>/module-beeagent-rop/rop_summary_result.json`
- `storage/runs/<run_id>/operator_summary.json`
- `storage/runs/<run_id>/rop_review_table.tsv`
- `logs/app.log`

#### Checks

- `uv run pytest -q`
- targeted CLI tests:
  - `./start.sh` backward compatibility;
  - `./start.sh telegram`;
  - `./start.sh rop run` with `json_batch`;
  - `./start.sh rop summary`;
  - `./start.sh rop export-review`;
  - missing run id;
  - missing artifacts;
  - source not found;
  - disabled source;
  - missing mailbox credentials;

- live smoke with `mailbox_readonly`, if credentials are available:
  - `folder=welding`;
  - `items_max=20`;

- artifact inspection;
- log verification;
- secret leakage check;
- no raw `.eml` artifacts;
- no CRM/destructive mailbox actions;
- SAST mindset review;
- SCA only if dependencies changed.

#### DoD

- `test.py` больше не нужен для обычного ROP run;
- ROP можно запустить через `./start.sh rop run`;
- Telegram credentials не нужны для ROP CLI;
- `run.mode: telegram` не мешает CLI override;
- existing `./start.sh` behavior не сломан;
- CLI использует existing `run_rop_batch_case(...)`, а не дублирует orchestration;
- `rop.sources` остаётся source of truth для источников;
- CLI overrides не создают второй source of truth;
- BeeAgent core не содержит ROP business rules;
- artifacts создаются воспроизводимо;
- `rop_review_table.tsv` пригоден для human review / customer validation;
- secrets не попадают в logs/artifacts;
- docs обновлены.

### Итерация 21 — Enriched ROP review TSV v1

**Статус:** DONE

#### Goal

Сделать `rop_review_table.tsv` пригодным для быстрой human review / customer validation без ручного открытия `normalized_events.json` и `classified_events.json`.

После `./start.sh rop run` оператор должен получить TSV, который можно сразу вставить в Google Sheets и разметить: видно письмо, краткий контекст, вложения, решение бота, объяснение и пустые поля для human/Bitrix сверки.

#### Scope

**Включено:**

- расширить `rop_review_table.tsv`;
- сохранить автоматический экспорт TSV после `./start.sh rop run`;
- сохранить ручной повторный экспорт через `./start.sh rop export-review`;
- добавить review-useful columns:
  - `body_short`;
  - `attachments`;
  - `bot_priority`;
  - `bot_reasoning`;
  - `bitrix_lead_id`;
  - `bitrix_deal_id`;
  - `bitrix_responsible`;
  - `is_duplicate`;
  - `duplicate_of`;
- сохранить текущие колонки:
  - `event_id`;
  - `source_id`;
  - `sender`;
  - `subject`;
  - `bot_case_type`;
  - `bot_reason_code`;
  - `bot_confidence`;
  - `bot_is_fallback`;
  - `human_case_type`;
  - `should_rop_see`;
  - `bitrix_status`;
  - `notes`;
  - `correct_action`;
- `body_short` должен быть bounded/sanitized preview, а не полный raw body;
- `attachments` должны быть metadata-only:
  - filename;
  - content_type;
  - size_bytes, если есть;
- пустые/отсутствующие поля должны экспортироваться как пустые ячейки;
- TSV должен оставаться tab-separated и pasteable в Google Sheets;
- обновить tests на header/order/row values;
- обновить README.ru.md / DEV_GUIDE / ROADMAP по новому TSV contract.

**Не включено:**

- изменения классификации в `beeagent-rop`;
- новые reason codes;
- Bitrix API;
- CRM write-back;
- OCR;
- attachment content parsing;
- экспорт raw `.eml`;
- экспорт full raw headers;
- web UI;
- mailbox cursor/pagination;
- config toggle для отключения TSV.

#### Deliverable

`./start.sh rop run` создаёт расширенный:

```text
storage/runs/<run_id>/rop_review_table.tsv
```

TSV содержит достаточно контекста для ручной разметки 20–50 писем без открытия JSON artifacts.

#### Expected TSV columns

```text
event_id
source_id
sender
subject
body_short
attachments
bot_case_type
bot_reason_code
bot_priority
bot_confidence
bot_is_fallback
bot_reasoning
human_case_type
should_rop_see
bitrix_status
notes
bitrix_lead_id
bitrix_deal_id
bitrix_responsible
is_duplicate
duplicate_of
correct_action
```

#### Artifacts

- `storage/runs/<run_id>/rop_review_table.tsv`
- existing:
  - `source_diagnostics.json`
  - `intake_metadata.json`
  - `normalized_events.json`
  - `classified_events.json`
  - `operator_summary.json`
  - module artifacts

#### Checks

- `uv run pytest -q`
- targeted CLI TSV tests;
- TSV header order test;
- TSV row with `body_short`;
- TSV row with attachment metadata;
- missing body/attachments scenario;
- `./start.sh rop run` smoke;
- `./start.sh rop export-review --run-id <run_id> --format tsv` smoke;
- artifact inspection;
- log inspection;
- secret leakage check;
- no raw `.eml` check;
- no direct `beeagent_rop` imports in BeeAgent core;
- SAST/security review for artifact export.

#### DoD

- `rop_review_table.tsv` содержит расширенные review columns;
- TSV остаётся валидным tab-separated файлом;
- `body_short` bounded и не экспортирует полный сырой body бесконтрольно;
- `attachments` metadata-only, без content;
- пустые optional fields экспортируются как пустые ячейки;
- автоматический TSV export после `rop run` не сломан;
- ручной `export-review` не сломан;
- BeeAgent core не содержит ROP business rules;
- `beeagent-rop` не меняется;
- secrets/raw `.eml` не попадают в artifacts/logs;
- docs обновлены.

### Итерация 22 — Operator Web Shell v0 with ROP dashboard

**Статус:** DONE

#### Goal

Добавить в BeeAgent минимальную read-only операторскую web-панель поверх существующих runtime artifacts, чтобы оператор/заказчик мог смотреть runs, summary, module outputs и ROP review table без чтения JSON/TSV вручную.

Итерация должна заложить reusable web shell для будущих модулей (`beeagent-rop`, `beescan`, `merch`), но первым рабочим module-specific экраном будет ROP dashboard.

#### Почему это нужно

После итераций 18–21 ROP backend path уже работает:

```text
mailbox/json_batch → normalized_events → beeagent-rop classification → classified_events → rop_summary → operator_summary → rop_review_table.tsv
```

Но текущий результат остаётся CLI/artifact-oriented:

- оператору нужно открывать JSON/TSV вручную;
- заказчику сложно показать MVP как продукт;
- нет единого run overview;
- нет web-поверхности, которая потом переиспользуется для BeeScan/Merch.

Следующий MVP-инкремент — сделать видимую operator surface, не добавляя CRM write-back, Bitrix, OCR или AI.

#### Scope

**Включено:**

- новый web entrypoint:
  - `./start.sh web`;

- минимальный web server внутри BeeAgent;
- read-only operator web shell;
- server-side HTML templates или простая HTML-rendering реализация без React/Vue/Next;
- страницы:
  - `/` — landing / operator home;
  - `/runs` — список run директории из `storage/runs`;
  - `/runs/<run_id>` — общий run overview;
  - `/runs/<run_id>/rop` — ROP-specific dashboard по existing artifacts;
  - `/modules` — список известных модулей/registry diagnostics, если artifact доступен;

- чтение только existing artifacts:
  - `operator_summary.json`;
  - `source_diagnostics.json`;
  - `intake_metadata.json`;
  - `normalized_events.json`;
  - `classified_events.json`;
  - `rop_review_table.tsv`;
  - `module-beeagent-rop/module_result.json`;
  - `module-beeagent-rop/rop_summary_result.json`;

- ROP dashboard показывает:
  - `run_id`;
  - source id/type;
  - loaded/classified/failed counts;
  - counts по `case_type`;
  - counts по `priority`;
  - fallback count;
  - reason_code distribution;
  - таблицу писем;
  - `sender`;
  - `subject`;
  - `body_short`;
  - `attachments`;
  - `bot_case_type`;
  - `bot_priority`;
  - `bot_confidence`;
  - `bot_reason_code`;
  - `bot_reasoning`;
  - `bot_is_fallback`;

- query filters на `/runs/<run_id>/rop`:
  - `case_type`;
  - `priority`;
  - `fallback`;
  - `reason_code`;

- ссылка скачать/открыть TSV:
  - `storage/runs/<run_id>/rop_review_table.tsv`;

- ссылки на основные artifacts;
- graceful degraded UI:
  - missing run;
  - missing artifact;
  - malformed JSON;
  - empty runs;
  - non-ROP run;

- tests на route handlers / HTML content / artifact parsing;
- docs update:
  - `docs/ROADMAP.md`;
  - `README.ru.md`;
  - `docs/DEV_GUIDE.md`.

**Не включено:**

- login/auth;
- multi-user access control;
- web-triggered `rop run`;
- CRM write-back;
- Bitrix;
- 1C;
- OCR;
- attachment content parsing;
- редактирование human labels в UI;
- сохранение review правок из UI;
- сложный frontend framework;
- websocket/live updates;
- scheduler/listener;
- production deployment hardening;
- nginx/basic-auth setup automation;
- BeeScan UI;
- ROP business rules в BeeAgent core;
- изменения в `beeagent-rop`.

#### Deliverable

Оператор может запустить:

```bash
./start.sh web
```

И открыть web-панель, где видны существующие BeeAgent runs и первый ROP dashboard по artifacts:

```text
storage/runs/<run_id>/...
```

Dashboard не выполняет действий, не меняет данные и не пишет в CRM. Он только читает и отображает существующие artifacts.

#### Expected routes

```text
/
 /runs
 /runs/<run_id>
 /runs/<run_id>/rop
 /modules
```

#### Expected artifacts read

```text
storage/runs/<run_id>/operator_summary.json
storage/runs/<run_id>/source_diagnostics.json
storage/runs/<run_id>/intake_metadata.json
storage/runs/<run_id>/normalized_events.json
storage/runs/<run_id>/classified_events.json
storage/runs/<run_id>/rop_review_table.tsv
storage/runs/<run_id>/module-beeagent-rop/module_result.json
storage/runs/<run_id>/module-beeagent-rop/rop_summary_result.json
storage/interfaces/modules.json
logs/app.log
```

#### Checks

- `uv run pytest -q`;
- targeted web route tests;
- route `/runs` works with empty and non-empty `storage/runs`;
- route `/runs/<run_id>` works with valid/missing/malformed artifacts;
- route `/runs/<run_id>/rop` renders ROP metrics and email table;
- filters work for `case_type`, `priority`, `fallback`, `reason_code`;
- TSV link is visible if `rop_review_table.tsv` exists;
- no raw `.eml` is served;
- no attachment content is served;
- no secrets appear in HTML;
- no path traversal through `run_id`;
- smoke:
  - create or reuse ROP run;
  - start web;
  - open `/runs`;
  - open `/runs/<run_id>/rop`;

- SAST/security review for artifact reading and path handling;
- SCA only if new dependencies are added.

#### DoD

- `./start.sh web` starts operator web shell;
- existing `./start.sh`, `./start.sh telegram`, `./start.sh rop ...` behavior is not broken;
- web shell reads only `storage/` artifacts;
- no destructive actions exist in web UI;
- no CRM/mailbox actions are exposed;
- run listing is bounded and does not full-scan huge artifacts unnecessarily;
- ROP dashboard gives enough information to review live batch without opening JSON/TSV manually;
- filters are server-side and test-covered;
- path traversal is prevented;
- secrets/raw `.eml`/attachment content are not exposed;
- BeeAgent core does not contain ROP classification rules;
- `beeagent-rop` is not changed;
- docs are updated.

### Итерация 23 — ROP source profile hardening v0

**Статус:** DONE

#### Goal

Усилить config-driven source contract для ROP pipeline, чтобы каждый источник входящих данных имел явный business/profile контекст и этот контекст воспроизводимо попадал в runtime artifacts, dashboard и downstream flow без изменения `beeagent-rop`.

#### Почему это нужно

После It18–22 BeeAgent умеет читать `mailbox_readonly`, классифицировать события через `beeagent-rop`, создавать TSV и показывать ROP dashboard.

Но текущий source contract недостаточен для перехода к multi-source:

```text
hotline + sales + online + parsales
```

Сейчас источник описывает технический доступ, но не фиксирует его роль:

```text
technical aggregator
sales mailbox
online sales mailbox
employee mailbox
regional mailbox
```

Без этого It24 приведёт к неясным artifacts, слабой дедупликации и ручным правкам кода при замене источника.

#### Scope

**Включено:**

- расширить `rop.sources[]` contract:
  - `source_role`;
  - `client_id`;
  - `display_name`;

- добавить fail-fast validation в `src/beeagent_module/core/settings.py`;
- обновить `config/settings.yml` для существующих sources;
- протянуть source profile metadata в artifacts:
  - `source_diagnostics.json`;
  - `intake_metadata.json`;
  - `operator_summary.json`;

- для `mailbox_readonly` явно фиксировать:
  - `mailbox_folder`;
  - `items_max`;
  - `fetched_count`;
  - `loaded_count`;
  - `malformed_count`, если уже есть такой счётчик или его можно добавить минимально;

- сохранить совместимость с текущим ROP pipeline:
  - `./start.sh rop run`;
  - `./start.sh rop summary`;
  - `./start.sh rop export-review`;
  - `./start.sh web`;

- обновить web/dashboard только минимально, если новые source fields не отображаются существующим generic rendering;
- добавить tests для config validation, source metadata propagation и degraded scenarios;
- обновить docs:
  - `docs/ROADMAP.md`;
  - `README.ru.md`;
  - `docs/DEV_GUIDE.md`.

**Не включено:**

- web-triggered `rop run`;
- multi-source ingestion;
- source-aware dedup;
- attachment extraction;
- OCR;
- Bitrix;
- 1C;
- CRM write-back;
- mailbox listener/polling;
- изменение `beeagent-rop`;
- ROP business rules в BeeAgent core.

#### Deliverable

Один ROP source всё ещё запускается как раньше, но теперь source profile является явным runtime contract:

```yaml
source_id: "hotline_mailbox"
source_type: "mailbox_readonly"
source_role: "technical_aggregator"
client_id: "welding"
display_name: "Welding Hotline mailbox"
enabled: true
authority: "read_only"
items_max: 20
```

Artifacts содержат business-readable source metadata и готовы к It24 multi-source flow.

#### Expected artifact fields

```text
source_id
source_type
source_role
source_display_name
client_id
authority
mailbox_folder
items_max
fetched_count
loaded_count
malformed_count
```

#### Change level

```text
runtime-risk
```

Если затрагивается mailbox parsing/path/security-sensitive handling глубже обычной metadata propagation — поднять до:

```text
security-sensitive
```

### Итерация 24 — ROP multi-source ingestion artifacts v0

**Статус:** DONE

#### Goal

Расширить BeeAgent ROP source flow с single active source до controlled multi-source ingestion: BeeAgent должен уметь за один run загрузить несколько configured `rop.sources`, сохранить per-source diagnostics, объединить normalized events, прогнать классификацию через `beeagent-rop`, построить `rop_summary` и записать source-aware artifacts без переноса ROP business logic в BeeAgent core.

#### Почему это нужно

После It18–23 BeeAgent умеет работать с одним активным source (`hotline_mailbox`) и уже имеет source profile contract:

```text
source_id
source_type
source_role
client_id
display_name
authority
items_max
```

Но реальный ROP поток будет состоять из нескольких источников: `hotline`, `sales`, `online`, `parsales`, региональные/сотруднические mailbox sources. Без multi-source artifacts следующие UI/attachment/Bitrix итерации будут завязаны на single-source модель и потребуют переделки.

#### Scope

**Включено:**

- расширить ROP source flow для multi-source run;
- поддержать загрузку нескольких enabled `rop.sources`;
- сохранить explicit `--source-id` для single-source run;
- добавить CLI режим выбора всех enabled sources, например:
  - `./start.sh rop run --all-sources`;

- сохранить backward compatibility:
  - если `--source-id` указан — запускать один source;
  - если `--all-sources` указан — запускать все enabled sources;
  - без `--source-id` и без `--all-sources` сохранить текущую single active source семантику или явно documented behavior;

- для каждого source писать diagnostics;
- добавить source-aware artifacts:
  - `source_diagnostics.json` как aggregate summary;
  - optional `source_diagnostics/<source_id>.json` или equivalent per-source section;
  - `intake_metadata.json` с per-source rollup;
  - `normalized_events.json` с `source_id`, `source_role`, `client_id`, `source_display_name`;
  - `classified_events.json` с preserved source metadata;
  - `operator_summary.json` с aggregate and per-source metrics;
  - `rop_review_table.tsv` с source columns;

- graceful degraded behavior:
  - один source упал, остальные обработались;
  - source disabled;
  - source not found;
  - no enabled sources;
  - malformed source diagnostics;
  - partial classification failure;

- tests на single-source compatibility и multi-source flow;
- docs update.

**Не включено:**

- новые production mailbox credentials;
- mailbox listener / polling daemon;
- source-aware dedup logic;
- Bitrix / 1C;
- CRM write-back;
- attachment extraction;
- OCR;
- изменение `beeagent-rop`;
- ROP business rules в BeeAgent core;
- web-triggered run;
- auth/control panel.

#### Deliverable

BeeAgent может создать один ROP run из нескольких configured sources, сохранить source-aware artifacts и дать operator/web layer достаточно данных для UI-2.

#### Реализовано

- canonical path `run_rop_batch_case(...)` расширен до multi-source ingestion без parallel orchestrator path;
- CLI поддерживает `./start.sh rop run --all-sources`;
- `--source-id` сохраняет explicit single-source запуск;
- без `--source-id` и без `--all-sources` сохранена legacy single-active semantics;
- `source_diagnostics.json` содержит aggregate блок + `sources[]`;
- `intake_metadata.json` содержит aggregate counts + per-source rollup в `sources[]`;
- `normalized_events.json` сохраняет source metadata (`source_id`, `source_type`, `source_role`, `source_display_name`, `client_id`) для каждого события;
- `classified_events.json` сохраняет source traceability fields;
- one degraded source не блокирует общий run, если есть хотя бы один успешно загруженный source;
- `rop_review_table.tsv` расширен source-aware колонками.

#### Expected artifacts

```text
storage/runs/<run_id>/source_diagnostics.json
storage/runs/<run_id>/intake_metadata.json
storage/runs/<run_id>/normalized_events.json
storage/runs/<run_id>/classified_events.json
storage/runs/<run_id>/operator_summary.json
storage/runs/<run_id>/rop_review_table.tsv
storage/runs/<run_id>/module-beeagent-rop/module_result.json
storage/runs/<run_id>/module-beeagent-rop/rop_summary_result.json
```

If per-source diagnostics are implemented as separate files:

```text
storage/runs/<run_id>/sources/<source_id>/source_diagnostics.json
```

#### Change level

```text
runtime-risk
```

Escalate to `security-sensitive` only if the PR changes mailbox parsing/security-sensitive file/path handling or adds dependencies.

### Итерация 25 — ROP attachment extraction artifacts v0

**Статус:** DONE

#### Goal

Добавить controlled attachment extraction artifact layer для ROP source flow: BeeAgent должен безопасно обработать attachment metadata из входящих событий, создать bounded extraction/refusal evidence artifacts и передать в downstream flow только safe preview/status fields, не сохраняя raw attachment content и не добавляя ROP business logic в core.

#### Почему это нужно

После It24 BeeAgent умеет собирать multi-source ROP run и сохранять source-aware artifacts:

```text
source_diagnostics.json
intake_metadata.json
normalized_events.json
classified_events.json
operator_summary.json
rop_review_table.tsv
```

Но вложения пока представлены только как metadata. Для следующего шага `beeagent-rop It15 — Attachment preview classification hardening` модулю нужен стабильный BeeAgent-owned artifact contract:

```text
attachment metadata
extraction_status
preview_available
safe text preview if available
refusal_reason / reason_code
source artifact reference
```

Если пропустить It25, attachment parsing и refusal semantics начнут расползаться в `beeagent-rop` или UI, что нарушит границу:

```text
BeeAgent core = source/orchestration/artifacts/safety boundary
beeagent-rop = domain classification/business logic
UI = read-only presentation over artifacts
```

#### Scope

**Включено:**

- добавить BeeAgent-owned attachment extraction artifact layer внутри existing ROP batch/source flow;
- сохранить canonical path:
  - `run_rop_batch_case(...)`;

- обработать attachment metadata из `normalized_events.json`;
- добавить bounded extraction result contract для каждого attachment:
  - `attachment_id` или deterministic local id;
  - `event_id`;
  - `source_id`;
  - `filename`;
  - `content_type`;
  - `size_bytes`;
  - `extraction_status`;
  - `preview_available`;
  - `text_preview`;
  - `preview_chars`;
  - `reason_code`;
  - `refusal_reason`;
  - `is_supported`;
  - `is_refused`;
  - `is_truncated`;

- добавить safe extraction policy v0:
  - поддерживать только явно безопасные/простые текстовые attachment inputs, если content уже доступен в controlled normalized test/source payload;
  - для unsupported/binary/pdf/docx/xlsx/image formats в v0 возвращать explicit `unsupported` или `metadata_only`, если нет безопасного extractor;
  - oversized attachments возвращают `refused`;
  - `.eml` и `message/rfc822` остаются blocked;

- добавить config-driven limits, если текущих лимитов недостаточно:
  - `rop.attachments.enabled`;
  - `rop.attachments.chars_max`;
  - `rop.attachments.size_max`;
  - `rop.attachments.types`.

- новые обязательные config keys валидировать fail-fast в `src/beeagent_module/core/settings.py`;
- создать новый artifact:
  - `storage/runs/<run_id>/attachment_extraction.json`;

- добавить attachment summary/refs в:
  - `operator_summary.json`;
  - `rop_review_table.tsv`, если это не ломает текущий TSV contract;

- добавить safe attachment preview fields в normalized/classified downstream payload only as bounded metadata/preview, не raw content;
- сохранить source traceability:
  - `source_id`;
  - `source_type`;
  - `source_role`;
  - `source_display_name`;
  - `client_id`;

- degraded behavior:
  - unsupported attachment;
  - oversized attachment;
  - blocked `.eml`;
  - missing attachment metadata;
  - malformed attachment item;
  - extraction exception;
  - no attachments;

- tests:
  - text attachment preview success;
  - unsupported PDF/DOCX/XLSX/image metadata-only/refusal;
  - blocked `.eml` / `message/rfc822`;
  - oversized refused;
  - malformed attachment item skipped/degraded;
  - multi-source source traceability preserved;
  - no raw content in artifacts/logs/HTML/API;

- docs update:
  - `docs/ROADMAP.md`;
  - `README.ru.md`;
  - `docs/DEV_GUIDE.md`;
  - `docs/WEB_UI.md`, если API/dashboard/read-model начинает ссылаться на новый artifact.

**Не включено:**

- OCR;
- full PDF/DOCX/XLSX parsing, если это требует новой heavy dependency или отдельной parser policy;
- arbitrary file execution;
- saving raw attachments;
- serving raw attachments from web;
- attachment download routes;
- web UI changes beyond safe artifact link/summary if necessary;
- ROP classification changes;
- changes to `beeagent-rop`;
- Bitrix / 1C;
- CRM write-back;
- mailbox listener/polling;
- source-aware dedup;
- AI document analysis;
- operator actions / POST routes;
- auth/RBAC.

#### Deliverable

После ROP run BeeAgent создаёт attachment extraction evidence artifact:

```text
storage/runs/<run_id>/attachment_extraction.json
```

Artifact показывает по каждому event/attachment:

```text
what was seen
what was safely previewed
what was refused
why it was refused
which source/event it belongs to
```

Downstream `beeagent-rop` получает только bounded attachment preview/status fields, если они доступны, и не получает raw attachment content.

#### Expected artifact

```text
storage/runs/<run_id>/attachment_extraction.json
```

Example shape:

```json
{
  "run_id": "rop-run-2026-05-25",
  "status": "ok",
  "aggregate": {
    "event_count": 2,
    "attachment_count": 3,
    "preview_available_count": 1,
    "metadata_only_count": 1,
    "refused_count": 1,
    "unsupported_count": 1,
    "failed_count": 0
  },
  "items": [
    {
      "event_id": "evt-001",
      "source_id": "hotline_mailbox",
      "source_type": "mailbox_readonly",
      "source_role": "technical_aggregator",
      "source_display_name": "Welding Hotline mailbox",
      "client_id": "welding",
      "attachment_id": "evt-001-att-0",
      "filename": "request.txt",
      "content_type": "text/plain",
      "size_bytes": 512,
      "extraction_status": "preview",
      "preview_available": true,
      "text_preview": "Please review attached request...",
      "preview_chars": 33,
      "is_supported": true,
      "is_refused": false,
      "is_truncated": false,
      "reason_code": "text_preview_extracted",
      "refusal_reason": null
    },
    {
      "event_id": "evt-002",
      "source_id": "hotline_mailbox",
      "source_type": "mailbox_readonly",
      "source_role": "technical_aggregator",
      "source_display_name": "Welding Hotline mailbox",
      "client_id": "welding",
      "attachment_id": "evt-002-att-0",
      "filename": "scan.eml",
      "content_type": "message/rfc822",
      "size_bytes": 2048,
      "extraction_status": "refused",
      "preview_available": false,
      "text_preview": "",
      "preview_chars": 0,
      "is_supported": false,
      "is_refused": true,
      "is_truncated": false,
      "reason_code": "blocked_email_attachment",
      "refusal_reason": "email attachments are blocked"
    }
  ]
}
```

#### Expected downstream event fields

If safe preview exists, normalized/classified event payload may include bounded fields such as:

```text
attachment_extraction_status
attachment_preview_available
attachment_text_preview
attachment_extraction_refs
attachment_refusal_reasons
```

These fields must stay bounded and must not contain raw attachment bytes or full raw files.

#### Artifacts

- `storage/runs/<run_id>/attachment_extraction.json`
- existing:
  - `storage/runs/<run_id>/source_diagnostics.json`
  - `storage/runs/<run_id>/intake_metadata.json`
  - `storage/runs/<run_id>/normalized_events.json`
  - `storage/runs/<run_id>/classified_events.json`
  - `storage/runs/<run_id>/operator_summary.json`
  - `storage/runs/<run_id>/rop_review_table.tsv`
  - `storage/runs/<run_id>/module-beeagent-rop/module_result.json`
  - `storage/runs/<run_id>/module-beeagent-rop/rop_summary_result.json`
  - `logs/app.log`

#### Change level

```text
security-sensitive
```

Reason:

- attachment input is untrusted;
- parsing/serialization boundary changes;
- artifact contract changes;
- potential sensitive client data exposure risk;
- file/content safety rules must be explicit.

#### Checks

- `uv run pytest -q`;
- targeted ROP attachment extraction tests;
- source flow smoke with `json_batch` attachment fixtures;
- optional mailbox smoke if credentials are available;
- artifact inspection:
  - `attachment_extraction.json`;
  - `normalized_events.json`;
  - `classified_events.json`;
  - `operator_summary.json`;
  - `rop_review_table.tsv`;

- log verification;
- secret leakage check;
- no raw `.eml` check;
- no `message/rfc822` check in exported previews;
- no raw attachment content / bytes fields in artifacts;
- no web route serves raw attachment content;
- no mailbox/CRM destructive actions;
- no direct `beeagent_rop` imports in BeeAgent core;
- SAST required;
- SCA only if dependencies change;
- DAST/IAST not required unless new network-facing behavior is added;
- fuzzing optional only if a new parser is added.

#### DoD

- `attachment_extraction.json` is created for ROP runs with attachments;
- no-attachment runs remain valid and do not fail;
- unsupported/refused attachments are visible and explainable;
- safe text previews are bounded by config;
- `.eml` / `message/rfc822` attachments remain blocked;
- raw attachment bytes/content are not stored in artifacts/logs/HTML/API;
- source traceability is preserved per attachment;
- downstream event payload contains only bounded safe preview/status fields;
- `beeagent-rop` is not changed;
- BeeAgent core does not contain ROP classification/business rules;
- existing `./start.sh rop run`, `summary`, `export-review`, `web` behavior is not broken;
- tests and docs are updated;
- required security checks are completed;
- `pyproject.toml.version` is not changed.

### Итерация 26 — Bitrix read-only reconciliation artifacts v0

**Статус:** DONE

#### Goal

Добавить controlled read-only Bitrix reconciliation layer для ROP source flow: BeeAgent должен уметь сверять уже полученные и классифицированные входящие события с текущим состоянием Bitrix CRM, создавать воспроизводимый artifact `bitrix_reconciliation.json` и показывать, найден ли соответствующий lead/deal/contact/company, не выполняя никаких CRM write-back действий.

#### Почему это нужно

После It24/It25 BeeAgent уже умеет собирать multi-source ROP run и сохранять source-aware / attachment-aware artifacts:

```text
source_diagnostics.json
intake_metadata.json
normalized_events.json
attachment_extraction.json
classified_events.json
operator_summary.json
rop_review_table.tsv
```

После `beeagent-rop It15` доменный модуль умеет использовать BeeAgent attachment extraction contract при classification.

Но для MVP заказчику нужно видеть не только:

```text
письмо пришло
→ бот классифицировал обращение
→ есть summary/review table
```

а полный read-only evidence chain:

```text
письмо пришло
→ бот понял, что это
→ видно, есть ли это в Bitrix
→ видно, lead/deal/contact/company найден или нет
→ видно, кто ответственный
→ видно, какая стадия/статус в CRM
→ видно, где потеря, дубль, ambiguity или manual review
```

Bitrix в этой итерации **не является source of truth для входящего email-потока**. Источник истины по входящим обращениям — BeeAgent source artifacts из mailbox/json_batch ingestion. Bitrix является CRM-state system, с которой BeeAgent сверяется.

Поэтому `not_found` в Bitrix — это не ошибка BeeAgent, а важный MVP-сигнал:

```text
important email exists
but Bitrix entity not found
→ possible lost lead / CRM gap / manual review
```

Если пропустить эту итерацию, дальнейшая полировка `beeagent-rop` будет выполняться без CRM evidence, а UI будет показывать только классификацию без ответа на главный вопрос РОПа:

```text
Что с этим обращением в Bitrix?
```

#### Scope

**Включено:**

- добавить BeeAgent-owned Bitrix read-only reconciliation layer;
- сохранить canonical ROP artifact pipeline;
- добавить config-driven Bitrix connector contract в `config/settings.yml`;
- читать Bitrix webhook URL только из env;
- добавить fail-fast validation в `src/beeagent_module/core/settings.py` для обязательных Bitrix config keys;
- Bitrix config не должен требовать secret/env при `bitrix.enabled: false`;
- при явном запуске reconciliation без нужного env — понятный fail-fast error;
- добавить минимальный Bitrix REST client / adapter для read-only вызовов;
- использовать только allowlisted read-only Bitrix methods:
  - `crm.item.list`;
  - `crm.item.fields`, если нужно для диагностики/fields discovery;
  - `crm.status.list`, если нужно для статусов/stages;
  - `crm.category.list`, если нужно для deal categories;

- поддержать системные CRM entity types:
  - `1` — lead;
  - `2` — deal;
  - `3` — contact;
  - `4` — company;

- добавить CLI/runtime path для reconciliation существующего ROP run, например:

```bash
./start.sh rop reconcile-bitrix --run-id <run_id>
```

- читать existing run artifacts:
  - `normalized_events.json`;
  - `classified_events.json`;
  - optional `attachment_extraction.json`;
  - optional `operator_summary.json`;

- выполнять candidate lookup в Bitrix по доступным безопасным сигналам:
  - sender email;
  - phone, если уже есть в normalized event;
  - subject/title;
  - company/client hints, если уже есть в event;
  - source_id/source_role;
  - event date, если есть;
  - bot_case_type;

- создавать artifact:

```text
storage/runs/<run_id>/bitrix_reconciliation.json
```

- добавить per-event reconciliation result:
  - `event_id`;
  - `source_id`;
  - `sender`;
  - `subject`;
  - `bot_case_type`;
  - `bitrix_match_status`;
  - `bitrix_entity_type`;
  - `bitrix_entity_type_id`;
  - `bitrix_entity_id`;
  - `bitrix_title`;
  - `bitrix_stage`;
  - `bitrix_responsible_id`;
  - `bitrix_contact_id`;
  - `bitrix_company_id`;
  - `bitrix_match_reason`;
  - `bitrix_confidence`;
  - `needs_manual_review`;
  - `reconciliation_reason`;

- поддержать статусы reconciliation:
  - `matched_lead`;
  - `matched_deal`;
  - `matched_contact`;
  - `matched_company`;
  - `not_found`;
  - `duplicate_candidate`;
  - `ambiguous`;
  - `skipped`;
  - `connector_degraded`;
  - `error`;

- добавить aggregate counts:
  - `event_count`;
  - `matched_count`;
  - `not_found_count`;
  - `duplicate_candidate_count`;
  - `ambiguous_count`;
  - `skipped_count`;
  - `connector_error_count`;

- добавить degraded behavior:
  - missing Bitrix env;
  - invalid config;
  - Bitrix auth/permission error;
  - Bitrix API error;
  - timeout;
  - malformed response;
  - pagination failure;
  - partial candidate lookup failure;

- не ломать existing ROP artifacts при connector failure;
- обогатить `rop_review_table.tsv` Bitrix fields, если `bitrix_reconciliation.json` существует и `export-review` запускается повторно;
- добавить tests с fake Bitrix responses;
- обновить docs:
  - `docs/ROADMAP.md`;
  - `README.ru.md`;
  - `docs/DEV_GUIDE.md`;
  - `docs/SECURITY.md`, если меняется security contract.

**Не включено:**

- `crm.item.add`;
- `crm.item.update`;
- `crm.item.delete`;
- создание лидов;
- создание сделок;
- создание контактов/компаний;
- изменение стадий/категорий;
- назначение ответственных;
- создание задач;
- комментарии в timeline;
- автоматический merge/dedup в Bitrix;
- CRM write-back;
- Bitrix OAuth application flow;
- Bitrix marketplace/app install flow;
- web-triggered reconciliation;
- Bitrix dashboard UI;
- Bitrix settings UI;
- auth/RBAC;
- operator control panel;
- 1C integration;
- manager scoring;
- изменение classification logic в `beeagent-rop`;
- ROP business rules в BeeAgent core.

#### Deliverable

BeeAgent умеет выполнить read-only reconciliation для существующего ROP run:

```bash
./start.sh rop reconcile-bitrix --run-id <run_id>
```

После выполнения появляется artifact:

```text
storage/runs/<run_id>/bitrix_reconciliation.json
```

Artifact показывает по каждому classified event:

```text
что пришло
как бот классифицировал событие
какой candidate найден в Bitrix
какой entity type найден
какая стадия/статус
кто ответственный
есть ли дубль/ambiguity
нужно ли manual review
почему принято reconciliation decision
```

После повторного export-review:

```bash
./start.sh rop export-review --run-id <run_id> --format tsv
```

`rop_review_table.tsv` может заполнять Bitrix columns на основе `bitrix_reconciliation.json`.

#### Expected config contract

Runtime/config source of truth:

```text
config/settings.yml
```

Expected config block:

```yaml
bitrix:
  enabled: false # true/false - включить/выключить Bitrix connector
  webhook_env: "BITRIX_WEBHOOK_URL" # имя env переменной с полным HTTPS URL входящего Bitrix webhook
  timeout: 10 # таймаут HTTP-запроса к Bitrix REST API (сек)
  page_size: 50 # размер страницы для Bitrix list-запросов
  pages_max: 3 # максимальное число страниц пагинации
  types_entity: # типы сущностей Bitrix для поиска (1=lead,2=deal,3=contact,4=company)
    - 1
    - 2
    - 3
    - 4
  reconciliation:
    enabled: false # true/false - включить/выключить reconciliation по умолчанию
    candidate_limit: 20 # максимальное число кандидатов на одно событие
    window_date: 180 # окно поиска по дате события (дней назад)
```

Rules:

- `BITRIX_WEBHOOK_URL` value must never be stored in `settings.yml`;
- `BITRIX_WEBHOOK_URL` value must never be written to logs/artifacts/HTML/API;
- `bitrix.enabled: false` must not require env during startup;
- explicit reconciliation invocation must fail clearly if required env is missing;
- no hidden required defaults for sensitive Bitrix behavior.

#### Expected artifact

```text
storage/runs/<run_id>/bitrix_reconciliation.json
```

Example shape:

```json
{
  "run_id": "rop-run-2026-06-18",
  "status": "ok",
  "read_only": true,
  "connector": {
    "system": "bitrix",
    "portal_url": "https://my.welding.kz",
    "auth_source": "env:BITRIX_WEBHOOK_URL",
    "allowed_methods": [
      "crm.item.list",
      "crm.item.fields",
      "crm.status.list",
      "crm.category.list"
    ]
  },
  "aggregate": {
    "event_count": 20,
    "matched_count": 9,
    "not_found_count": 6,
    "duplicate_candidate_count": 2,
    "ambiguous_count": 2,
    "skipped_count": 1,
    "connector_error_count": 0
  },
  "items": [
    {
      "event_id": "evt-001",
      "source_id": "hotline_mailbox",
      "sender": "client@example.com",
      "subject": "Request for welding machine price",
      "bot_case_type": "new_lead",
      "bitrix_match_status": "matched_lead",
      "bitrix_entity_type": "lead",
      "bitrix_entity_type_id": 1,
      "bitrix_entity_id": 253,
      "bitrix_title": "Request for welding machine price",
      "bitrix_stage": "NEW",
      "bitrix_responsible_id": 6,
      "bitrix_contact_id": null,
      "bitrix_company_id": null,
      "bitrix_match_reason": "sender_email_exact",
      "bitrix_confidence": 0.95,
      "needs_manual_review": false,
      "reconciliation_reason": "Exact sender email candidate found in Bitrix lead list."
    },
    {
      "event_id": "evt-002",
      "source_id": "online_mailbox",
      "sender": "buyer@example.com",
      "subject": "КП на сварочные электроды",
      "bot_case_type": "new_lead",
      "bitrix_match_status": "not_found",
      "bitrix_entity_type": "",
      "bitrix_entity_type_id": null,
      "bitrix_entity_id": null,
      "bitrix_title": "",
      "bitrix_stage": "",
      "bitrix_responsible_id": null,
      "bitrix_contact_id": null,
      "bitrix_company_id": null,
      "bitrix_match_reason": "no_candidate_found",
      "bitrix_confidence": 0.0,
      "needs_manual_review": true,
      "reconciliation_reason": "No Bitrix candidate was found for this classified event."
    }
  ],
  "warnings": []
}
```

#### Matching behavior v0

Matching must be simple, bounded and explainable.

Allowed matching signals:

```text
sender email
phone if already normalized
subject/title
company/client hints if already normalized
source_id/source_role
event date if already available
bot_case_type
```

Recommended v0 behavior:

```text
exact email/phone match
→ high-confidence candidate

company/contact-only match
→ matched_contact or matched_company, often manual review

title/subject weak match
→ lower-confidence candidate

multiple strong candidates
→ duplicate_candidate

multiple weak candidates
→ ambiguous

no candidate
→ not_found

connector/API failure
→ connector_degraded or error
```

Important rule:

```text
not_found != connector failure
```

`not_found` means Bitrix was reachable, but no candidate was found.

#### Expected TSV impact

Existing `rop_review_table.tsv` already has Bitrix placeholder fields. After reconciliation and repeated export, these fields should be populated when possible:

```text
bitrix_status
bitrix_lead_id
bitrix_deal_id
bitrix_responsible
```

Optional future-compatible fields may remain empty in v0 if TSV contract already includes them.

If `bitrix_reconciliation.json` is missing:

```text
rop export-review
→ still works
→ Bitrix columns remain empty
```

#### Artifacts

New artifact:

```text
storage/runs/<run_id>/bitrix_reconciliation.json
```

Existing artifacts read:

```text
storage/runs/<run_id>/normalized_events.json
storage/runs/<run_id>/classified_events.json
storage/runs/<run_id>/attachment_extraction.json
storage/runs/<run_id>/operator_summary.json
```

Existing artifacts optionally updated/generated:

```text
storage/runs/<run_id>/rop_review_table.tsv
```

Logs:

```text
logs/app.log
```

Docs:

```text
docs/ROADMAP.md
README.ru.md
docs/DEV_GUIDE.md
docs/SECURITY.md
```

#### Change level

```text
security-sensitive
```

Reason:

- external connector boundary;
- env/secret handling;
- Bitrix REST API integration;
- external JSON response parsing;
- stored artifact contract change;
- CRM authority boundary;
- future write-back risk must be explicitly blocked in v0.

#### Checks

- `uv run pytest -q`;
- targeted Bitrix reconciliation tests;
- targeted config validation tests;
- targeted ROP CLI tests;
- fake Bitrix client tests;
- fake Bitrix API error tests;
- artifact inspection:
  - `bitrix_reconciliation.json`;
  - `rop_review_table.tsv`;

- log verification;
- secret leakage check;
- no webhook URL in logs/artifacts;
- no raw auth headers in logs/artifacts;
- no CRM write methods in adapter/client allowlist;
- no `crm.item.add`;
- no `crm.item.update`;
- no `crm.item.delete`;
- no task/timeline write methods;
- no destructive mailbox/CRM actions;
- no direct `beeagent_rop` imports in BeeAgent core beyond existing module runtime path;
- SAST required;
- SCA only if dependencies change;
- DAST-style route/runtime misuse checks if any network-facing path changes;
- IAST not required;
- fuzzing optional only for fragile JSON/TSV parsing, not mandatory.

Required automated scenarios:

```text
config disabled does not require Bitrix env
explicit reconciliation without env fails clearly
invalid Bitrix config fails fast
fake matched lead
fake matched deal
fake matched contact only
fake matched company only
not found
duplicate candidate
ambiguous candidate
connector degraded
Bitrix API error
permission denied
timeout / transport error
malformed JSON response
pagination next handling if implemented
TSV enrichment when reconciliation artifact exists
TSV remains valid when reconciliation artifact is missing
no webhook URL in artifact/logs
no write method called
```

Recommended smoke:

```bash
./start.sh rop run \
  --source-id rop_batch_sample \
  --items-max 2 \
  --run-id smoke-bitrix-recon-input

./start.sh rop reconcile-bitrix \
  --run-id smoke-bitrix-recon-input

./start.sh rop export-review \
  --run-id smoke-bitrix-recon-input \
  --format tsv
```

Live Bitrix smoke is optional and must only be run if credentials are available and explicit approval is given.

#### DoD

- `bitrix` config block exists in `config/settings.yml`;
- new required config keys are validated fail-fast in `src/beeagent_module/core/settings.py`;
- Bitrix webhook URL is read only from env;
- webhook URL does not appear in logs/artifacts/tests;
- read-only Bitrix client/adapter exists;
- only allowlisted read-only Bitrix methods are callable;
- CRM write methods are absent from v0 path;
- `./start.sh rop reconcile-bitrix --run-id <run_id>` works;
- `bitrix_reconciliation.json` is created for a valid ROP run;
- each classified event receives a reconciliation result or explicit skipped/degraded status;
- `not_found` is represented as a valid CRM gap signal;
- connector failure is represented separately from `not_found`;
- existing ROP pipeline remains backward-compatible;
- `rop export-review` works with and without `bitrix_reconciliation.json`;
- Bitrix columns in TSV are populated when reconciliation data exists;
- tests cover success, not found, duplicates, ambiguity and degraded connector cases;
- no `beeagent-rop` code is changed;
- BeeAgent core does not contain ROP classification/business rules;
- docs are updated;
- required security checks are completed;
- `pyproject.toml.version` is not changed.

### Итерация 27 — ROP MVP Current State Index + Bitrix Evidence Board v0

**Статус:** DONE

#### Goal

Добавить BeeAgent-owned current-state/index слой для ROP MVP: система должна уметь собрать текущую операторскую картину по последнему или явно выбранному ROP run, объединить source/classification/attachment/Bitrix evidence в один стабильный read-model artifact и отдать его Web Console / BeeUI без необходимости вручную открывать несколько JSON/TSV файлов.

Итерация должна превратить набор run artifacts:

```text
source_diagnostics.json
intake_metadata.json
normalized_events.json
attachment_extraction.json
classified_events.json
bitrix_reconciliation.json
operator_summary.json
rop_review_table.tsv
```

в понятный current-state snapshot:

```text
что пришло
что классифицировано
что важно
что найдено в Bitrix
что потеряно в Bitrix
что ambiguous/duplicate
что требует ручного разбора
какие evidence artifacts открыть
```

#### Почему это нужно

После It26 BeeAgent уже умеет выполнять Bitrix read-only reconciliation и создавать `bitrix_reconciliation.json`.

Но результат всё ещё run/artifact-oriented:

- оператор должен знать `run_id`;
- UI зависит от scattered artifacts;
- нет единого latest/current alias;
- нет стабильного read-model для MVP demo;
- optional artifacts вроде `bitrix_reconciliation.json` могут быть missing/stale/degraded;
- Bitrix evidence пока не превращено в рабочие очереди РОПа.

Для MVP заказчику нужно видеть не “JSON артефакты”, а компактную операционную картину:

```text
важные обращения
потерянные в Bitrix лиды
ambiguous/dedup candidates
ручная проверка
evidence links
```

Итерация нужна, потому что она закрывает разрыв между backend artifacts и customer-visible MVP dashboard.

#### Scope

**Включено:**

- добавить BeeAgent-owned current-state builder для ROP run;
- читать только existing ROP artifacts из `storage/runs/<run_id>/...`;
- создать per-run artifact:

```text
storage/runs/<run_id>/rop_current_state.json
```

- создать/update interface artifacts:

```text
storage/interfaces/rop_current.json
storage/interfaces/rop_latest.json
storage/interfaces/rop_index.json
```

- добавить CLI command:

```bash
./start.sh rop current --run-id <run_id>
```

- обновлять current-state после successful `rop run`;

- обновлять current-state после successful `reconcile-bitrix`;

- не создавать ложный success state после failed `reconcile-bitrix`;

- добавить latest/current alias semantics:
  - latest ROP run;
  - selected/current run;
  - current client/source context;
  - technical `run_id` as evidence, not primary operator concept;

- построить KPI/read-model:
  - total events;
  - normalized events;
  - classified events;
  - high priority;
  - needs manual review;
  - source degraded;
  - attachment preview/refused counts;
  - Bitrix matched;
  - Bitrix not found / lost in Bitrix;
  - Bitrix ambiguous/duplicate;
  - Bitrix connector degraded;
  - unreconciled/no Bitrix artifact;

- построить operator queues:
  - `lost_in_bitrix`;
  - `needs_review`;
  - `high_priority`;
  - `ambiguous`;
  - `matched`;
  - `unreconciled`;
  - `degraded`;

- добавить evidence references:
  - normalized event;
  - classified event;
  - attachment extraction;
  - Bitrix reconciliation item;
  - TSV review artifact;
  - operator summary;

- фиксировать artifact availability/freshness:
  - artifact exists/missing;
  - artifact malformed;
  - artifact run_id mismatch;
  - optional artifact older than primary classification/operator artifacts, if detectable;
  - warning for stale optional Bitrix evidence;

- обновить BeeAgent UI adapter/read-model:
  - `/rop`;
  - `/api/rop/dashboard`;
  - `/runs/<run_id>`;
  - artifact links where applicable;

- включить Bitrix tab/section in ROP dashboard read-model, если current-state содержит Bitrix evidence;

- добавить artifact allowlist entries:
  - `rop_current_state_json`;
  - `bitrix_reconciliation_json`;

- graceful degraded behavior:
  - missing current-state artifacts;
  - missing Bitrix reconciliation;
  - stale Bitrix reconciliation;
  - malformed Bitrix artifact;
  - missing classified events;
  - missing operator summary;
  - no runs;
  - invalid/path-traversal run_id;

- tests for builder, CLI, artifacts, UI read-model and security boundaries;

- docs update:
  - `docs/ROADMAP.md`;
  - `README.ru.md`;
  - `docs/WEB_UI.md`;
  - `docs/DEV_GUIDE.md`, if command/API behavior changes.

**Не включено:**

- Bitrix write-back;
- `crm.item.add`;
- `crm.item.update`;
- task creation;
- timeline comments;
- manager scoring;
- 1C integration;
- mailbox listener/polling;
- web-triggered ROP run;
- auth/RBAC;
- Control Panel;
- operator POST actions;
- editing review labels in UI;
- changes to `beeagent-rop`;
- ROP business rules in BeeAgent core;
- AI recommendation generation;
- new dependencies unless strictly required.

#### Deliverable

BeeAgent can build and expose a stable current-state ROP read-model:

```bash
./start.sh rop current --run-id <run_id>
```

Expected artifacts:

```text
storage/runs/<run_id>/rop_current_state.json
storage/interfaces/rop_current.json
storage/interfaces/rop_latest.json
storage/interfaces/rop_index.json
```

The Web Console / BeeUI ROP dashboard can open `/rop` without requiring the operator to manually know a `run_id`, and it can show latest/current ROP state with Bitrix evidence queues and safe artifact links.

#### Expected current-state artifact

```json
{
  "run_id": "live-review-2026-06-19",
  "status": "ok",
  "read_only": true,
  "generated_at_utc": "2026-06-19T00:00:00Z",
  "client_id": "welding",
  "current_alias": "latest",
  "source": {
    "selection_mode": "single_explicit",
    "source_count": 1,
    "loaded_source_count": 1,
    "degraded_source_count": 0
  },
  "kpi": {
    "events_total": 20,
    "normalized_count": 20,
    "classified_count": 20,
    "high_priority": 4,
    "needs_manual_review": 6,
    "source_degraded": 0,
    "attachment_count": 3,
    "attachment_preview_available": 1,
    "attachment_refused": 1,
    "matched_in_bitrix": 8,
    "lost_in_bitrix": 5,
    "ambiguous_in_bitrix": 3,
    "connector_degraded": 0,
    "unreconciled": 0
  },
  "queues": {
    "lost_in_bitrix": [],
    "needs_review": [],
    "high_priority": [],
    "ambiguous": [],
    "matched": [],
    "unreconciled": [],
    "degraded": []
  },
  "artifact_refs": [
    {
      "artifact_id": "operator_summary_json",
      "path": "runs/<run_id>/operator_summary.json",
      "exists": true,
      "status": "ok"
    },
    {
      "artifact_id": "bitrix_reconciliation_json",
      "path": "runs/<run_id>/bitrix_reconciliation.json",
      "exists": true,
      "status": "ok"
    }
  ],
  "warnings": []
}
```

#### Current-state behavior

Rules:

```text
missing Bitrix reconciliation
→ do not count as lost_in_bitrix
→ mark as unreconciled/no_bitrix_evidence

Bitrix not_found
→ count as lost_in_bitrix
→ needs_manual_review=true

Bitrix ambiguous / duplicate_candidate
→ count as ambiguous_in_bitrix
→ needs_manual_review=true

Bitrix matched_*
→ count as matched_in_bitrix

Bitrix connector_degraded / error
→ count as connector_degraded
→ do not treat as not_found

optional Bitrix artifact appears stale/malformed/mismatched
→ show warning
→ do not silently trust it as current evidence
```

Important rule:

```text
not_found != connector failure
missing/stale artifact != not_found
```

#### BeeUI / Web Console impact

The BeeAgent UI adapter should use current-state artifacts as the primary source for `/rop` and `/api/rop/dashboard` when available.

Expected ROP dashboard sections:

- Overview;
- Queue;
- Sources;
- Attachments;
- Bitrix;
- Evidence.

Bitrix tab should no longer be reserved-only when current-state/Bitrix evidence exists.

BeeUI must remain generic:

```text
BeeUI renders.
BeeAgent adapter decides.
```

No ROP-specific business logic should be added to BeeUI generic framework.

#### Expected UI blocks

Use existing adapter-backed `layout[]` block types:

- `state_grid`;
- `kpi_grid`;
- `event_table`;
- `status_table`;
- `attention_list`;
- `artifact_links`;
- `group`;
- `degraded`.

#### Artifacts

New:

```text
storage/runs/<run_id>/rop_current_state.json
storage/interfaces/rop_current.json
storage/interfaces/rop_latest.json
storage/interfaces/rop_index.json
```

Existing artifacts read:

```text
storage/runs/<run_id>/source_diagnostics.json
storage/runs/<run_id>/intake_metadata.json
storage/runs/<run_id>/attachment_extraction.json
storage/runs/<run_id>/normalized_events.json
storage/runs/<run_id>/classified_events.json
storage/runs/<run_id>/bitrix_reconciliation.json
storage/runs/<run_id>/operator_summary.json
storage/runs/<run_id>/rop_review_table.tsv
```

#### Change level

```text
security-sensitive
```

Reason:

- artifact restore/parsing;
- file/path handling;
- UI/API exposure of client operational data;
- artifact allowlist update;
- malformed/stale artifact handling;
- read-only Web/API behavior.

No new external connector is added in this iteration.

#### Checks

Required:

```bash
uv run pytest -q
uv run pytest -q -k "rop or web or ui"
```

Targeted tests:

```text
current-state builder with normal run
current-state builder without Bitrix artifact
current-state builder with matched Bitrix artifact
current-state builder with not_found Bitrix artifact
current-state builder with ambiguous/duplicate Bitrix artifact
current-state builder with connector_degraded Bitrix artifact
current-state builder with stale/malformed Bitrix artifact
current-state builder rejects path traversal run_id
CLI rop current creates per-run and interface artifacts
rop run updates current-state
successful reconcile-bitrix updates current-state
failed reconcile-bitrix does not create false success state
/api/rop/dashboard includes current-state/Bitrix KPI fields
/rop renders degraded state when current-state is missing
artifact allowlist includes rop_current_state_json and bitrix_reconciliation_json
secrets/raw .eml/attachment content are not exposed
```

Smoke:

```bash
uv run python config/start.py rop run \
  --source-id rop_batch_sample \
  --items-max 2 \
  --run-id smoke-it27-current

uv run python config/start.py rop current \
  --run-id smoke-it27-current

uv run python config/start.py rop summary \
  --run-id smoke-it27-current

uv run python config/start.py web --host 127.0.0.1 --port 8780 --no-open
```

Optional live Bitrix smoke only if credentials are available and explicitly approved.

Security checks:

- SAST required;
- SCA only if dependencies change;
- lightweight DAST-style route/runtime misuse checks for `/rop`, `/api/rop/dashboard`, artifact routes;
- IAST not required;
- fuzzing optional only for malformed artifact restore tests.

#### DoD

- `rop_current_state.json` is created for a valid ROP run;
- `storage/interfaces/rop_current.json`, `rop_latest.json`, `rop_index.json` are created/updated;
- `/rop` can show latest/current ROP state without requiring manual run_id;
- current-state distinguishes:
  - Bitrix `not_found`;
  - missing Bitrix artifact;
  - stale/malformed Bitrix artifact;
  - connector degraded/error;

- lost-in-Bitrix queue is based only on valid Bitrix `not_found`, not on missing/degraded evidence;
- Bitrix matched/ambiguous/duplicate/manual-review queues are visible in current-state;
- UI/API expose only read-only data;
- no POST/write/action route is added;
- no Bitrix write-back exists;
- no `beeagent-rop` code is changed;
- BeeAgent core does not contain ROP classification/business rules;
- artifact access remains allowlisted;
- path traversal is blocked;
- secrets/raw `.eml`/attachment content are not exposed;
- tests and docs are updated;
- required security checks are completed;
- `pyproject.toml.version` is not changed.

### Итерация 27.1 — ROP Business Dashboard UX + Period Analytics v0

**Статус:** DONE

#### Goal

Сделать ROP dashboard в BeeAgent продуктово полезным для РОПа: заменить технический run/artifact overview на business-facing dashboard с периодами, бизнес-метриками, chart-ready series, Bitrix evidence, operator queues и deterministic рекомендациями на основе existing ROP artifacts/current-state.

Итерация должна использовать уже закрытый BeeUI It13.6:

```text
chart
data_table
kpi_grid
state_grid
attention_list
artifact_links
group
degraded
```

BeeUI остаётся generic renderer:

```text
BeeUI renders.
BeeAgent adapter decides.
```

BeeAgent должен отдавать нормализованный ROP dashboard read-model и `layout[]`, но не должен переносить в core классификацию, клиентские правила или Bitrix write-back.

#### Почему это нужно

После It27 BeeAgent создаёт current-state artifacts:

```text
storage/runs/<run_id>/rop_current_state.json
storage/interfaces/rop_current.json
storage/interfaces/rop_latest.json
storage/interfaces/rop_index.json
```

Но текущий `/rop` UI всё ещё выглядит как debug/interface layer:

```text
run_id list
n/a values
generic metrics
empty Bitrix unavailable card
```

Для MVP заказчику и РОПу нужен не список технических run_id, а операционная картина:

```text
что пришло за период
сколько лидов обработано
какие источники работают
какие обращения важные
какие обращения не найдены в Bitrix
где ambiguous / duplicates
что РОП должен проверить первым
какие evidence artifacts открыть
```

Итерация закрывает разрыв между backend current-state artifacts и customer-facing ROP dashboard.

#### Scope

**Включено**

- добавить BeeAgent-owned ROP dashboard read-model builder поверх existing It27 artifacts;
- использовать `rop_current_state.json`, `rop_index.json`, `rop_latest.json`, `operator_summary.json`, `classified_events.json`, `bitrix_reconciliation.json`, `attachment_extraction.json`, `rop_review_table.tsv`;
- добавить period support:
  - `today`;
  - `yesterday`;
  - `7d`;
  - `30d`;
  - `365d`;
  - `all`;
- добавить config/source-of-truth для dashboard period behavior в `config/settings.yml`, если такого блока ещё нет:

```yaml
rop:
  dashboard:
    default_period: "7d"
    periods:
      - today
      - yesterday
      - 7d
      - 30d
      - 365d
      - all
```

- валидировать новые keys fail-fast в `src/beeagent_module/core/settings.py`;
- default period должен быть явно задан в config, а не скрыт в коде;
- добавить CLI command для явной генерации dashboard read-model:

```bash
./start.sh rop dashboard --period 7d
```

- после successful `rop run` / `rop current` обновлять dashboard artifact для default period;
- после successful `reconcile-bitrix` обновлять dashboard artifact;
- failed `reconcile-bitrix` не должен создавать ложный Bitrix success state;
- создать/update interface artifact:

```text
storage/interfaces/rop_dashboard.json
```

- artifact должен содержать dashboard payload по supported periods или по default period с явным `period`;
- GET routes не должны мутировать storage;
- `/rop` должен читать prepared dashboard/current-state artifacts и рендерить business dashboard;
- `/api/rop/dashboard?period=7d` должен отдавать read-only payload;
- сохранить backward compatibility старых API fields, если они уже используются тестами/UI.

#### Business KPI

ROP dashboard должен показывать business-facing KPI:

```text
processed_events
processed_emails
new_leads
existing_clients
follow_ups
high_priority
needs_review
lost_in_bitrix
ambiguous_or_duplicate
unreconciled
source_degraded
attachment_refused
bitrix_errors
```

Если часть полей невозможно получить из текущих artifacts, поле должно быть явно `0` или `n/a` с warning, но не должно маскироваться под полноценную аналитику.

#### Time period behavior

Allowed query values:

```text
period=today
period=yesterday
period=7d
period=30d
period=365d
period=all
```

Dashboard payload должен содержать:

```json
{
  "period": "7d",
  "period_start_utc": "2026-06-13T00:00:00Z",
  "period_end_utc": "2026-06-20T23:59:59Z",
  "time_basis": "event_timestamp",
  "warnings": []
}
```

Allowed `time_basis`:

```text
event_timestamp
run_generated_at
run_mtime_fallback
mixed
unknown
```

Rules:

```text
event timestamp available
→ use event_timestamp

event timestamp missing but current-state generated_at exists
→ use run_generated_at and add warning if needed

generated_at missing
→ use run directory mtime fallback and add warning time_basis_fallback

missing time basis
→ include item only for period=all or degrade explicitly
```

#### Charts / series

Если BeeUI It13.6 chart block доступен, BeeAgent adapter должен отдавать chart blocks в `layout[]`.

Expected chart blocks:

```text
Processed events over time
Lead classification distribution
Bitrix evidence distribution
Source contribution by source_id/source_role
```

Example chart-ready API shape:

```json
{
  "series": {
    "processed_by_day": {
      "labels": ["2026-06-14", "2026-06-15"],
      "series": [
        { "name": "Processed", "data": [12, 18] },
        { "name": "High priority", "data": [2, 4] }
      ]
    },
    "classification_distribution": {
      "labels": ["new_lead", "follow_up", "other"],
      "series": [8, 5, 2]
    },
    "bitrix_distribution": {
      "labels": ["matched", "lost", "ambiguous", "unreconciled"],
      "series": [7, 3, 2, 4]
    }
  }
}
```

#### Data tables / queues

Использовать BeeUI `data_table` для operator queues:

- High-priority queue;
- Needs review queue;
- Lost in Bitrix queue;
- Ambiguous / duplicate queue;
- Unreconciled queue;
- Source degraded queue;
- Evidence table.

Expected row fields:

```text
event_id
source_id
source_display_name
sender
subject
bot_case_type
bot_priority
bitrix_status
reason
recommended_next_step
run_id
evidence_href
```

#### ROP recommendations

Добавить deterministic ROP recommendations на основе existing artifacts/current-state.

Это не AI-рекомендации и не client-specific classification logic.

Rules:

```text
high_priority > 0
→ recommend immediate review/call for high-priority cases

lost_in_bitrix > 0
→ recommend checking CRM gap / manual lead review

ambiguous_or_duplicate > 0
→ recommend resolving duplicate/ambiguous Bitrix matches

unreconciled > 0 and Bitrix artifact missing
→ recommend running read-only Bitrix reconciliation

connector_degraded > 0
→ recommend checking Bitrix connector

source_degraded > 0
→ recommend checking source/mailbox ingestion

attachment_refused > 0
→ recommend manual review of refused attachment metadata
```

Expected recommendation item:

```json
{
  "severity": "warning",
  "title": "Review lost Bitrix leads",
  "detail": "3 classified events were not found in Bitrix.",
  "reason_code": "lost_in_bitrix",
  "count": 3,
  "read_only": true,
  "action_type": "manual_review",
  "evidence_href": "/rop?tab=bitrix&period=7d"
}
```

#### Bitrix Evidence Board behavior

Bitrix tab/section must be useful even when Bitrix artifact is missing.

Rules:

```text
valid Bitrix evidence exists
→ show matched/lost/ambiguous/duplicate tables and chart

Bitrix artifact missing
→ show status "Not reconciled"
→ show unreconciled count
→ show next step: run read-only reconcile-bitrix
→ do not call it "Bitrix unavailable" unless connector failure is actually known

Bitrix connector degraded/error
→ show connector degraded state
→ do not treat as not_found

Bitrix not_found
→ count as lost_in_bitrix

missing/stale/malformed Bitrix artifact
→ warning, no false lost_in_bitrix count
```

Important invariant:

```text
not_found != connector failure
missing/stale Bitrix artifact != not_found
```

#### UI layout expectation

`/rop` should become a product dashboard, not a debug run list.

Expected tabs:

```text
Overview
Queue
Sources
Attachments
Bitrix
Evidence
```

Overview should show:

- period selector;
- business KPI cards;
- charts;
- top recommendations;
- compact current state;
- key evidence links.

Technical run list may remain only as compact selector or Evidence/Debug area, not the main content.

#### API expectation

`GET /api/rop/dashboard?period=7d`

Expected payload:

```json
{
  "run_id": "smoke-it27-current",
  "selected_run_id": "smoke-it27-current",
  "period": "7d",
  "time_basis": "run_generated_at",
  "read_only": true,
  "business_kpi": {
    "processed_events": 2,
    "processed_emails": 2,
    "new_leads": 1,
    "existing_clients": 0,
    "follow_ups": 1,
    "high_priority": 1,
    "needs_review": 0,
    "lost_in_bitrix": 0,
    "ambiguous_or_duplicate": 0,
    "unreconciled": 2,
    "source_degraded": 0,
    "attachment_refused": 0,
    "bitrix_errors": 0
  },
  "series": {},
  "queues": {},
  "rop_recommendations": [],
  "evidence_links": [],
  "warnings": []
}
```

Backward-compatible fields should remain if currently exposed:

```text
available_runs
kpis
funnel
source_health
classification_distribution
recommendations
current_state_kpi
current_state_queues
bitrix
```

#### Artifacts

New / updated:

```text
storage/interfaces/rop_dashboard.json
```

Existing read:

```text
storage/interfaces/rop_current.json
storage/interfaces/rop_latest.json
storage/interfaces/rop_index.json
storage/runs/<run_id>/rop_current_state.json
storage/runs/<run_id>/operator_summary.json
storage/runs/<run_id>/classified_events.json
storage/runs/<run_id>/attachment_extraction.json
storage/runs/<run_id>/bitrix_reconciliation.json
storage/runs/<run_id>/rop_review_table.tsv
```

#### Config / contract impact

Expected:

- `config/settings.yml` changes if `rop.dashboard` does not already exist;
- fail-fast validation in `src/beeagent_module/core/settings.py`;
- artifact contract change:
  - `storage/interfaces/rop_dashboard.json`;

- API contract change:
  - `/api/rop/dashboard?period=...`;

- UI adapter/read-model behavior change;
- docs update required.

#### Не включено

- Bitrix write-back;
- `crm.item.add`;
- `crm.item.update`;
- task creation;
- timeline comments;
- manager scoring;
- 1C integration;
- mailbox listener/polling;
- web-triggered ROP run;
- auth/RBAC;
- Control Panel;
- POST/operator actions;
- editing review labels in UI;
- changes to `beeagent-rop`;
- AI recommendation generation;
- arbitrary ApexCharts options;
- BeeUI core changes, unless a real incompatibility is found;
- DataTables/List.js runtime.

#### Change level

```text
security-sensitive
```

Reason:

- artifact restore/parsing;
- file/path handling;
- UI/API exposure of client operational data;
- serialization into BeeUI `chart` and `data_table` blocks;
- config validation if `rop.dashboard` is added;
- malformed/stale artifact handling;
- read-only Web/API behavior.

No new external connector is added in this iteration.

#### Checks

Required:

```bash
uv run pytest -q
uv run pytest -q -k "rop or web or ui"
```

Targeted tests:

```text
settings validation for rop.dashboard.default_period
settings validation for allowed dashboard periods
dashboard builder with normal current-state
dashboard builder with no Bitrix artifact
dashboard builder with valid Bitrix matched/not_found/ambiguous/degraded data
dashboard builder with stale/malformed Bitrix artifact
period parser accepts today/yesterday/7d/30d/365d/all
period parser rejects unsafe/unknown values
time_basis fallback is explicit
business_kpi is present in API
chart-ready series are present
data_table queue blocks are present in layout
deterministic recommendations are generated
missing Bitrix artifact produces Not reconciled state, not Bitrix unavailable
lost_in_bitrix uses only valid Bitrix not_found
/rop renders business overview, not primary debug run list
/api/rop/dashboard?period=7d works
GET routes do not mutate storage
path traversal run_id/query attempts are rejected/degraded
artifact links remain allowlisted
secrets/raw .eml/attachment content are not exposed
```

Smoke:

```bash
uv run python config/start.py rop run \
  --source-id rop_batch_sample \
  --items-max 2 \
  --run-id smoke-it27-1-business-dashboard

uv run python config/start.py rop current \
  --run-id smoke-it27-1-business-dashboard

uv run python config/start.py rop dashboard \
  --period 7d

uv run python config/start.py web \
  --host 127.0.0.1 \
  --port 8780 \
  --no-open
```

Manual browser/API checks:

```text
GET /rop
GET /rop?period=today
GET /rop?period=7d
GET /rop?tab=bitrix&period=7d
GET /api/rop/dashboard?period=7d
GET /api/rop/dashboard?period=invalid
```

Security checks:

```text
SAST required
SCA only if dependencies change
lightweight DAST-style route/API misuse checks required for /rop and /api/rop/dashboard
IAST not required
fuzzing optional only for malformed artifact restore tests
```

Secret/content grep:

```bash
grep -R "https://.*bitrix\|/rest/[0-9]\|password\|secret\|token\|raw_eml\|message/rfc822\|attachment_content\|content_bytes" \
  logs storage/runs/smoke-it27-1-business-dashboard storage/interfaces -n || true
```

#### DoD

- `/rop` reads like a ROP business dashboard, not a debug artifact browser;
- period selector works for supported periods;
- `storage/interfaces/rop_dashboard.json` is created/updated;
- `/api/rop/dashboard?period=7d` includes `business_kpi`, `series`, `queues`, `rop_recommendations`;
- chart blocks are returned for BeeUI when chart data exists;
- data_table blocks are returned for operator queues;
- Bitrix Board shows useful states:
  - matched;
  - lost/not_found;
  - ambiguous/duplicate;
  - unreconciled;
  - connector degraded;
  - missing/stale artifact warning;
- `not_found`, missing evidence and connector failure are not confused;
- recommendations are deterministic and read-only;
- technical run list is not the primary Overview content;
- GET routes do not mutate storage;
- no POST/write/action route is added;
- no Bitrix write-back exists;
- no `beeagent-rop` code is changed;
- BeeAgent core does not contain ROP classification rules;
- config/source-of-truth is explicit if new dashboard keys are added;
- path traversal is blocked;
- secrets/raw `.eml`/attachment content are not exposed;
- tests and docs are updated;
- required security checks are completed;
- `pyproject.toml.version` is not changed.

#### Реализовано

- `src/beeagent_module/cases/rop_dashboard.py` — новый модуль:
  - `ALLOWED_PERIODS` — константа с поддерживаемыми периодами;
  - `parse_period(period)` — парсинг периода в `{period, period_start_utc, period_end_utc, time_basis}`;
  - `validate_period(period)` — валидация периода против ALLOWED_PERIODS;
  - `build_rop_dashboard(storage_dir, period, logger, run_id=None)` — построение dashboard read-model;
  - `write_rop_dashboard(storage_dir, dashboard, logger)` — запись артефакта `storage/interfaces/rop_dashboard.json`;
- `config/settings.yml` — добавлен блок `rop.dashboard`:
  - `default_period: "7d"`;
  - `periods: [today, yesterday, 7d, 30d, 365d, all]`;
- `src/beeagent_module/core/settings.py`:
  - добавлены обязательные ключи `rop.dashboard.default_period` и `rop.dashboard.periods`;
  - добавлена `_validate_rop_dashboard_settings()` — fail-fast валидация:
    - `default_period` — non-empty string, must be in allowlist;
    - `periods` — non-empty list, каждый элемент в allowlist;
    - `default_period` must be in `periods`;
- `src/beeagent_module/core/cli.py`:
  - добавлен `handle_rop_dashboard(args, settings, logger)` — CLI handler;
  - добавлен `dashboard` subparser с `--period` и `--run-id`;
  - после успешного `rop run` автоматически строится dashboard для default period;
  - после успешного `rop current` автоматически строится dashboard;
  - после успешного `reconcile-bitrix` автоматически строится dashboard;
- Dashboard read-model содержит:
  - `business_kpi` — processed_events, new_leads, existing_clients, follow_ups, high_priority, needs_review, lost_in_bitrix, ambiguous_or_duplicate, unreconciled, source_degraded, attachment_refused;
  - `series` — processed_by_day, classification_distribution, bitrix_distribution, source_contribution;
  - `queues` — high_priority, needs_review, lost_in_bitrix, unreconciled;
  - `rop_recommendations` — deterministic рекомендации по high_priority, lost_in_bitrix, ambiguous/duplicate, unreconciled, source_degraded, attachment_refused;
  - `evidence_links` — ссылки на все allowlisted artifact_id для данного run;
- Dashboard поддерживает period filtering: `today`, `yesterday`, `7d`, `30d`, `365d`, `all`;
- `src/beeagent_module/interfaces/ui/read_model.py`:
  - `build_rop_dashboard_read_model` уже использует `beeagent_module.cases.rop_dashboard.parse_period/validate_period`;
  - `/api/rop/dashboard?period=7d` отдаёт `business_kpi`, `series`, `queues`, `rop_recommendations`;
  - `/rop` Overview — business KPI cards, charts, рекомендации, compact run selector;
- CLI entrypoint:

```bash
./start.sh rop dashboard --period 7d
./start.sh rop dashboard --period today --run-id <run_id>
./start.sh rop dashboard --period all
```

- Артефакт: `storage/interfaces/rop_dashboard.json`;
- Dashboard автоматически обновляется после `rop run`, `rop current` и `reconcile-bitrix`;
- `./start.sh web` — `/rop` и `/api/rop/dashboard` поддерживают `period` query parameter;
- Тесты: `tests/test_rop_dashboard.py` — period parsing, build, write, no-bitrix, empty, settings validation;
- Docs: `docs/ROADMAP.md`, `README.ru.md`, `docs/WEB_UI.md`, `docs/DEV_GUIDE.md` обновлены.

### Итерация 28 — ROP MVP handoff / readiness pack v0

**Статус:** DONE

#### Goal

Собрать текущий ROP MVP evidence chain в один сдаваемый handoff/readiness pack для демонстрации заказчику: BeeAgent должен сформировать customer/demo-ready artifacts, которые объясняют, что было обработано, что классифицировано, что найдено/не найдено в Bitrix, какие очереди требуют внимания РОПа, какие ограничения остаются и какие evidence artifacts подтверждают вывод.

#### Почему это нужно

После It24–It27.1 BeeAgent уже умеет:

```text
multi-source ingestion
→ attachment extraction evidence
→ beeagent-rop classification
→ Bitrix read-only reconciliation
→ current-state index
→ business dashboard with periods/queues/recommendations
```

Но результат всё ещё распределён по множеству artifacts и UI-секций:

```text
classified_events.json
attachment_extraction.json
bitrix_reconciliation.json
rop_current_state.json
rop_dashboard.json
rop_review_table.tsv
operator_summary.json
/rop dashboard
```

Для MVP заказчику нужен не набор технических JSON, а единый handoff artifact:

```text
вот текущая картина
вот что бот нашёл
вот что не попало в Bitrix
вот кому нужно заняться
вот evidence
вот ограничения
вот что готово к demo
вот что не является production/write-back
```

Эта итерация закрывает слой сдачи MVP без добавления CRM write-back, новых connectors, AI-рекомендаций или доменных правил в BeeAgent core.

#### Scope

**Включено:**

- добавить BeeAgent-owned MVP pack builder поверх existing ROP artifacts;

- читать только existing artifacts:
  - `operator_summary.json`;
  - `source_diagnostics.json`;
  - `intake_metadata.json`;
  - `normalized_events.json`;
  - `classified_events.json`;
  - `attachment_extraction.json`;
  - `bitrix_reconciliation.json`;
  - `rop_current_state.json`;
  - `rop_review_table.tsv`;
  - `storage/interfaces/rop_dashboard.json`;

- добавить CLI command:

```bash
./start.sh rop mvp-pack --run-id <run_id> --period 7d
```

- создать per-run artifacts:

```text
storage/runs/<run_id>/rop_mvp_pack.json
storage/runs/<run_id>/rop_mvp_report.md
```

- создать/update interface artifact:

```text
storage/interfaces/rop_mvp_latest.json
```

- включить в pack:
  - run identity;
  - selected period;
  - source coverage;
  - configured/enabled/loaded/degraded sources;
  - processed events/emails;
  - new leads;
  - existing/follow-up cases;
  - high-priority queue;
  - needs-review queue;
  - lost-in-Bitrix queue;
  - ambiguous/duplicate queue;
  - unreconciled queue;
  - attachment refused/unsupported summary;
  - source degraded summary;
  - deterministic first actions for ROP;
  - evidence links;
  - demo readiness status;
  - known limitations;
  - explicit non-production/write-back status;

- использовать existing `rop.sources[]` as source of truth for configured source coverage;

- не хардкодить Welding mailbox names;

- если expected source coverage не задана в config, не выводить выдуманные missing sources, а показать только configured/enabled/loaded/degraded coverage;

- добавить safe artifact links for MVP pack/report in UI Evidence area if available;

- добавить artifacts allowlist entries if needed;

- graceful degraded behavior:
  - missing dashboard artifact;
  - missing current-state artifact;
  - missing Bitrix artifact;
  - stale/malformed optional artifact;
  - missing TSV;
  - no runs;
  - invalid/path-traversal run_id;

- tests for builder, CLI, artifacts, report rendering, UI allowlist and security boundaries;

- docs update:
  - `docs/ROADMAP.md`;
  - `README.ru.md`;
  - `docs/DEV_GUIDE.md`;
  - `docs/WEB_UI.md`, if UI/API/artifact links change.

**Не включено:**

- Bitrix write-back;
- `crm.item.add`;
- `crm.item.update`;
- task creation;
- timeline comments;
- manager scoring;
- 1C integration;
- open registry checks;
- mailbox listener/polling;
- web-triggered ROP run;
- auth/RBAC;
- Control Panel;
- POST/operator actions;
- editing review labels in UI;
- OCR/PDF/DOCX/XLSX deep parsing;
- AI recommendation generation;
- changes to `beeagent-rop`;
- ROP classification/business rules in BeeAgent core;
- removal of legacy `src/beeagent_module/web`.

#### Deliverable

BeeAgent can build a customer/demo-ready MVP handoff pack for a selected ROP run:

```bash
./start.sh rop mvp-pack \
  --run-id mvp-welding-2026-06-22 \
  --period 7d
```

Expected artifacts:

```text
storage/runs/<run_id>/rop_mvp_pack.json
storage/runs/<run_id>/rop_mvp_report.md
storage/interfaces/rop_mvp_latest.json
```

The pack/report should let the team demonstrate the MVP without asking the customer to inspect raw JSON/TSV files.

#### Expected pack shape

```json
{
  "run_id": "mvp-welding-2026-06-22",
  "period": "7d",
  "status": "ready_with_limitations",
  "read_only": true,
  "generated_at_utc": "2026-06-22T00:00:00Z",
  "client_id": "welding",
  "source_coverage": {
    "configured_sources": 2,
    "enabled_sources": 2,
    "loaded_sources": 1,
    "degraded_sources": 1,
    "warnings": []
  },
  "business_summary": {
    "processed_events": 50,
    "processed_emails": 50,
    "new_leads": 12,
    "existing_clients": 18,
    "follow_ups": 8,
    "high_priority": 6,
    "needs_review": 10,
    "lost_in_bitrix": 4,
    "ambiguous_or_duplicate": 3,
    "unreconciled": 0,
    "source_degraded": 1,
    "attachment_refused": 2,
    "bitrix_errors": 0
  },
  "queues": {
    "first_actions": [],
    "high_priority": [],
    "needs_review": [],
    "lost_in_bitrix": [],
    "ambiguous_or_duplicate": [],
    "unreconciled": []
  },
  "demo_readiness": {
    "status": "ready_with_limitations",
    "ready_items": [],
    "limitations": [],
    "blockers": []
  },
  "evidence_links": [],
  "warnings": []
}
```

#### Report behavior

`rop_mvp_report.md` should be human-readable and customer-demo oriented.

Expected sections:

```text
# ROP MVP Handoff Report

## Executive summary
## Period and run
## Source coverage
## Business KPI
## First actions for ROP
## Queues
## Bitrix evidence
## Attachment evidence
## Evidence artifacts
## Known limitations
## Not included in MVP
## Recommended next step
```

The report must not include secrets, raw `.eml`, raw attachment content or Bitrix webhook URLs.

#### Artifacts

New:

```text
storage/runs/<run_id>/rop_mvp_pack.json
storage/runs/<run_id>/rop_mvp_report.md
storage/interfaces/rop_mvp_latest.json
```

Existing read:

```text
storage/interfaces/rop_dashboard.json
storage/interfaces/rop_current.json
storage/interfaces/rop_latest.json
storage/interfaces/rop_index.json
storage/runs/<run_id>/rop_current_state.json
storage/runs/<run_id>/operator_summary.json
storage/runs/<run_id>/source_diagnostics.json
storage/runs/<run_id>/intake_metadata.json
storage/runs/<run_id>/normalized_events.json
storage/runs/<run_id>/classified_events.json
storage/runs/<run_id>/attachment_extraction.json
storage/runs/<run_id>/bitrix_reconciliation.json
storage/runs/<run_id>/rop_review_table.tsv
```

#### Change level

```text
security-sensitive
```

Reason:

- artifact restore/parsing;
- file/path handling;
- Markdown/JSON serialization of customer operational data;
- UI/API exposure of handoff artifacts;
- artifact allowlist update;
- malformed/stale artifact handling.

No new external connector is added in this iteration.

#### Checks

Required:

```bash
uv run pytest -q
uv run pytest -q -k "rop or web or ui"
```

Targeted tests:

```text
MVP pack builder with full artifact set
MVP pack builder without Bitrix artifact
MVP pack builder with connector degraded Bitrix artifact
MVP pack builder with missing/malformed dashboard artifact
MVP pack builder with missing TSV
source coverage from configured rop.sources
no hardcoded Welding source names
CLI rop mvp-pack creates per-run artifacts
CLI rop mvp-pack updates storage/interfaces/rop_mvp_latest.json
Markdown report contains expected sections
Markdown report does not contain secrets/raw .eml/raw attachment content
artifact allowlist includes rop_mvp_pack_json and rop_mvp_report_md if UI links are added
/rop Evidence area shows MVP pack/report links if available
GET routes do not mutate storage
invalid/path-traversal run_id rejected/degraded
```

Smoke:

```bash
uv run python config/start.py rop run \
  --source-id rop_batch_sample \
  --items-max 2 \
  --run-id smoke-it28-mvp-pack

uv run python config/start.py rop current \
  --run-id smoke-it28-mvp-pack

uv run python config/start.py rop dashboard \
  --period 7d \
  --run-id smoke-it28-mvp-pack

uv run python config/start.py rop mvp-pack \
  --period 7d \
  --run-id smoke-it28-mvp-pack
```

Security checks:

```text
SAST required
SCA only if dependencies change
lightweight DAST-style route/API misuse checks if UI artifact links/routes change
IAST not required
fuzzing optional only for malformed artifact restore tests
```

Secret/content grep:

```bash
grep -R "https://.*bitrix\|/rest/[0-9]\|password\|secret\|token\|raw_eml\|message/rfc822\|attachment_content\|content_bytes" \
  logs storage/runs/smoke-it28-mvp-pack storage/interfaces -n || true
```

#### DoD

- `rop_mvp_pack.json` is created for a valid ROP run;
- `rop_mvp_report.md` is created for a valid ROP run;
- `storage/interfaces/rop_mvp_latest.json` is updated after successful `rop mvp-pack`;
- pack summarizes business state, queues, Bitrix evidence, attachment evidence, source coverage, first actions and limitations;
- source coverage is derived from `config/settings.yml -> rop.sources[]`, not hardcoded mailbox names;
- missing Bitrix evidence is not confused with `not_found`;
- connector degraded/error is not confused with `lost_in_bitrix`;
- report is readable without opening raw JSON artifacts;
- GET routes remain read-only;
- no POST/write/action route is added;
- no Bitrix write-back exists;
- no `beeagent-rop` code is changed;
- BeeAgent core does not contain ROP classification/business rules;
- artifact access remains allowlisted;
- path traversal is blocked;
- secrets/raw `.eml`/raw attachment content are not exposed;
- tests and docs are updated;
- required security checks are completed;
- `pyproject.toml.version` is not changed.

### Итерация 29 — ROP Bitrix match quality gate and action drafts v0

**Статус:** DONE

#### Goal

Сделать Bitrix reconciliation безопасным для MVP: weak/ambiguous Bitrix candidates не должны считаться успешным match, `not_found` должен быть отделён от connector failure, а BeeAgent должен формировать read-only action drafts для РОПа поверх existing classification + Bitrix evidence.

#### Почему это нужно

После It26–It28 BeeAgent уже умеет строить полный ROP evidence chain:

```text
mailbox/json_batch
→ normalized_events.json
→ attachment_extraction.json
→ beeagent-rop classification
→ classified_events.json
→ Bitrix read-only reconciliation
→ current-state/dashboard/MVP pack
```

Ручная проверка live batch показала, что classification path уже достаточно полезен для MVP, но Bitrix evidence остаётся рискованной зоной:

```text
weak/wrong Bitrix candidate
→ выглядит как found/matched
→ РОП может уйти в неправильный lead/deal
```

Для MVP это хуже, чем `not_found`:

```text
not_found = честный CRM gap
wrong/weak match = опасная ложная уверенность
```

Поэтому перед AI assist и перед любым Bitrix write-back нужно ввести explicit match quality gate:

```text
strong evidence only → matched_*
weak evidence → weak_match / ambiguous / manual_review
connector failure → connector_degraded / error
no candidate → not_found
```

Эта итерация остаётся в `beeagent`, потому что Bitrix connector, reconciliation artifacts, dashboard/current-state/MVP pack и action drafts принадлежат BeeAgent orchestration layer. `beeagent-rop` продолжает отвечать за доменную classification semantics.

#### Scope

**Включено:**

- усилить BeeAgent-owned Bitrix reconciliation quality gate;
- сохранить read-only Bitrix boundary;
- не считать weak/subject-only/random candidate успешным match;
- добавить/уточнить reconciliation status:

```text
matched_lead
matched_deal
matched_contact
matched_company
not_found
ambiguous
duplicate_candidate
weak_match
skipped
connector_degraded
error
```

- добавить explicit match quality fields в `bitrix_reconciliation.json`:

```text
bitrix_match_status
bitrix_match_quality
bitrix_confidence
needs_manual_review
safe_to_use_as_target
bitrix_match_reason
reconciliation_reason
candidate_count
candidate_summary
```

- правило:

```text
weak subject/title-only match
or random low-evidence phone/title candidate
or multiple weak candidates
→ weak_match or ambiguous
→ needs_manual_review=true
→ safe_to_use_as_target=false
→ not counted as successful matched
```

- сохранить invariant:

```text
not_found != connector failure
missing Bitrix artifact != not_found
weak_match != matched
ambiguous != matched
```

- добавить aggregate counts в `bitrix_reconciliation.json`:

```text
event_count
safe_matched_count
matched_count
weak_match_count
not_found_count
ambiguous_count
duplicate_candidate_count
skipped_count
connector_degraded_count
error_count
manual_review_count
```

- добавить BeeAgent-owned action draft artifact:

```text
storage/runs/<run_id>/rop_action_drafts.json
```

- action drafts строятся только из existing artifacts:
  - `normalized_events.json`;
  - `classified_events.json`;
  - `bitrix_reconciliation.json`;
  - optional `attachment_extraction.json`;
  - optional `rop_current_state.json`;

- action draft должен быть read-only/draft-only и не выполнять CRM write-back;

- action draft item должен содержать:

```text
action_draft_id
event_id
run_id
source_id
bot_case_type
bitrix_match_status
queue
recommended_action
recommended_next_step
priority
reason_code
needs_manual_review
safe_to_use_as_target
target_entity_type
target_entity_id
evidence_refs
read_only
```

- recommended action mapping v0:

```text
new_lead + not_found
→ lost_in_bitrix / check CRM gap / create lead manually

new_lead + matched_lead
→ review existing lead / update manually if needed

existing_deal + matched_deal
→ review deal / add comment or document manually

existing_deal + weak_match|ambiguous
→ choose correct Bitrix entity manually

ambiguous|duplicate_candidate
→ resolve candidate manually

irrelevant
→ ignore

connector_degraded|error
→ check Bitrix connector

missing Bitrix evidence
→ run read-only reconciliation
```

- добавить CLI command:

```bash
./start.sh rop action-drafts --run-id <run_id>
```

- автоматически обновлять `rop_action_drafts.json` после successful `reconcile-bitrix`;
- не создавать ложный success state после failed `reconcile-bitrix`;
- `rop export-review` должен обогащать TSV, если существуют `bitrix_reconciliation.json` и/или `rop_action_drafts.json`;
- сохранить backward compatibility старых TSV колонок;
- добавить новые TSV columns, если они ещё отсутствуют:

```text
bitrix_match_status
bitrix_match_quality
bitrix_confidence
needs_manual_review
safe_to_use_as_target
recommended_action
recommended_next_step
action_queue
action_draft_id
```

- обновить current-state/dashboard/MVP pack read-model минимально:
  - `weak_match` виден как manual-review/ambiguous risk;
  - `safe_matched_count` отделён от просто `matched_count`;
  - action drafts доступны в Evidence / First actions;
  - `lost_in_bitrix` считается только по valid `not_found`, не по missing/degraded Bitrix evidence;

- добавить artifact allowlist entry, если UI/Evidence links начинают ссылаться на новый artifact:

```text
rop_action_drafts_json
```

- graceful degraded behavior:
  - missing Bitrix artifact;
  - malformed Bitrix artifact;
  - stale/mismatched run_id;
  - missing classified events;
  - empty candidates;
  - connector degraded/error;
  - path traversal attempt through run_id;

- tests for reconciliation quality gate, action drafts, TSV enrichment, current/dashboard/MVP pack read-model impact and security boundaries;

- docs update:
  - `docs/ROADMAP.md`;
  - `README.ru.md`;
  - `docs/DEV_GUIDE.md`;
  - `docs/WEB_UI.md`, если UI/API artifact links меняются.

**Не включено:**

- Bitrix write-back;
- `crm.item.add`;
- `crm.item.update`;
- `crm.item.delete`;
- task creation;
- timeline comments;
- lead creation;
- deal update;
- auto-assign responsible;
- automatic CRM actions;
- AI classification;
- AI recommendation generation;
- changes to `beeagent-rop`;
- ROP classification/business rules in BeeAgent core;
- OCR;
- PDF/DOCX/XLSX deep parsing;
- 1C integration;
- manager scoring;
- mailbox listener/polling;
- web-triggered ROP run;
- POST/operator action routes;
- auth/RBAC;
- Control Panel.

#### Deliverable

BeeAgent can run safer Bitrix reconciliation and produce explicit ROP action drafts:

```bash
./start.sh rop reconcile-bitrix --run-id <run_id>

./start.sh rop action-drafts --run-id <run_id>

./start.sh rop export-review --run-id <run_id> --format tsv
```

Expected artifacts:

```text
storage/runs/<run_id>/bitrix_reconciliation.json
storage/runs/<run_id>/rop_action_drafts.json
storage/runs/<run_id>/rop_review_table.tsv
```

The dashboard/current-state/MVP pack can distinguish:

```text
safe matched
weak match
ambiguous
duplicate candidate
not found
connector degraded
missing Bitrix evidence
```

#### Expected `bitrix_reconciliation.json` behavior

Strong exact evidence:

```json
{
  "event_id": "evt-001",
  "bitrix_match_status": "matched_lead",
  "bitrix_match_quality": "strong",
  "bitrix_confidence": 0.95,
  "needs_manual_review": false,
  "safe_to_use_as_target": true,
  "bitrix_match_reason": "sender_email_exact",
  "reconciliation_reason": "Exact sender email candidate found in Bitrix lead list."
}
```

Weak title/subject-only candidate:

```json
{
  "event_id": "evt-002",
  "bitrix_match_status": "weak_match",
  "bitrix_match_quality": "weak",
  "bitrix_confidence": 0.45,
  "needs_manual_review": true,
  "safe_to_use_as_target": false,
  "bitrix_match_reason": "subject_title_weak",
  "reconciliation_reason": "Only weak title/subject candidate was found; candidate is not safe for automatic targeting."
}
```

No candidate while connector is healthy:

```json
{
  "event_id": "evt-003",
  "bitrix_match_status": "not_found",
  "bitrix_match_quality": "none",
  "bitrix_confidence": 0.0,
  "needs_manual_review": true,
  "safe_to_use_as_target": false,
  "bitrix_match_reason": "no_candidate_found",
  "reconciliation_reason": "Bitrix was reachable, but no candidate was found."
}
```

Connector failure:

```json
{
  "event_id": "evt-004",
  "bitrix_match_status": "connector_degraded",
  "bitrix_match_quality": "degraded",
  "bitrix_confidence": 0.0,
  "needs_manual_review": true,
  "safe_to_use_as_target": false,
  "bitrix_match_reason": "connector_error",
  "reconciliation_reason": "Bitrix connector failed; result must not be treated as not_found."
}
```

#### Expected `rop_action_drafts.json`

```json
{
  "run_id": "mvp-welding-live-hardening-20260624-0735",
  "status": "ok",
  "read_only": true,
  "draft_only": true,
  "generated_at_utc": "2026-06-24T00:00:00Z",
  "aggregate": {
    "action_count": 20,
    "manual_review_count": 8,
    "safe_target_count": 5,
    "lost_in_bitrix_count": 3,
    "ambiguous_count": 2,
    "connector_degraded_count": 0
  },
  "items": [
    {
      "action_draft_id": "evt-001-action",
      "event_id": "evt-001",
      "run_id": "mvp-welding-live-hardening-20260624-0735",
      "source_id": "hotline_mailbox",
      "bot_case_type": "new_lead",
      "bitrix_match_status": "not_found",
      "queue": "lost_in_bitrix",
      "recommended_action": "check_crm_gap",
      "recommended_next_step": "Review as a possible lost lead in Bitrix and create/update CRM manually if confirmed.",
      "priority": "high",
      "reason_code": "new_lead_not_found_in_bitrix",
      "needs_manual_review": true,
      "safe_to_use_as_target": false,
      "target_entity_type": "",
      "target_entity_id": null,
      "evidence_refs": [
        "classified_events_json",
        "bitrix_reconciliation_json",
        "rop_review_table_tsv"
      ],
      "read_only": true
    }
  ],
  "warnings": []
}
```

#### Current-state / dashboard / MVP pack behavior

Rules:

```text
matched_in_bitrix / safe matched
→ count only safe_to_use_as_target=true or strong matched_* according to v0 rules

weak_match
→ not successful matched
→ needs_review / ambiguous queue

ambiguous / duplicate_candidate
→ ambiguous_or_duplicate queue

not_found
→ lost_in_bitrix only when Bitrix evidence is valid and connector is healthy

connector_degraded / error
→ bitrix_errors / degraded
→ not lost_in_bitrix

missing Bitrix artifact
→ unreconciled
→ not lost_in_bitrix

missing action drafts
→ dashboard remains valid and shows no action draft artifact
```

#### Artifacts

New:

```text
storage/runs/<run_id>/rop_action_drafts.json
```

Updated:

```text
storage/runs/<run_id>/bitrix_reconciliation.json
storage/runs/<run_id>/rop_review_table.tsv
storage/runs/<run_id>/rop_current_state.json
storage/interfaces/rop_current.json
storage/interfaces/rop_latest.json
storage/interfaces/rop_index.json
storage/interfaces/rop_dashboard.json
storage/runs/<run_id>/rop_mvp_pack.json
storage/runs/<run_id>/rop_mvp_report.md
storage/interfaces/rop_mvp_latest.json
```

Existing read:

```text
storage/runs/<run_id>/normalized_events.json
storage/runs/<run_id>/classified_events.json
storage/runs/<run_id>/attachment_extraction.json
storage/runs/<run_id>/operator_summary.json
storage/runs/<run_id>/bitrix_reconciliation.json
```

#### Config / contract impact

Expected:

```text
No new required config key unless implementation proves it is needed.
```

Source of truth remains:

```text
config/settings.yml -> bitrix.*
config/settings.yml -> rop.sources[]
existing ROP run artifacts in storage/runs/<run_id>/
```

If a new config key is proposed, it must be justified first and validated fail-fast in:

```text
src/beeagent_module/core/settings.py
```

#### Change level

```text
security-sensitive
```

Reason:

- external connector reconciliation logic;
- CRM evidence quality gate;
- artifact restore/parsing;
- file/path handling;
- serialization of customer operational data;
- UI/API exposure of match/action evidence;
- future write-back safety boundary.

No dependency change is expected.

#### Checks

Required:

```bash
uv run pytest -q
uv run pytest -q -k "rop or bitrix or web or ui"
```

Targeted tests:

```text
Bitrix strong exact email/phone match stays matched_*
weak subject/title-only candidate becomes weak_match
multiple weak candidates become ambiguous
multiple strong candidates become duplicate_candidate
not_found is emitted only when connector is healthy and no candidate exists
connector_degraded/error is not counted as not_found
weak_match is not counted as successful safe match
safe_to_use_as_target=false for weak_match/ambiguous/duplicate/not_found/degraded
safe_to_use_as_target=true only for strong safe matched target
action drafts generated from classified events + Bitrix reconciliation
new_lead + not_found creates lost_in_bitrix action draft
existing_deal + matched_deal creates review_deal action draft
weak_match/ambiguous creates choose_correct_entity action draft
irrelevant creates ignore action draft
connector_degraded creates connector_check action draft
TSV enrichment includes bitrix_match_status and recommended_action fields
current-state uses valid not_found only for lost_in_bitrix
dashboard exposes weak/ambiguous/safe matched counts
MVP pack includes first actions/action draft evidence when available
missing Bitrix artifact remains unreconciled, not lost_in_bitrix
malformed Bitrix/action artifact degrades safely
invalid/path-traversal run_id is rejected/degraded
```

Smoke:

```bash
uv run python config/start.py rop run \
  --source-id rop_batch_sample \
  --items-max 2 \
  --run-id smoke-it29-bitrix-quality

uv run python config/start.py rop reconcile-bitrix \
  --run-id smoke-it29-bitrix-quality

uv run python config/start.py rop action-drafts \
  --run-id smoke-it29-bitrix-quality

uv run python config/start.py rop export-review \
  --run-id smoke-it29-bitrix-quality \
  --format tsv

uv run python config/start.py rop current \
  --run-id smoke-it29-bitrix-quality

uv run python config/start.py rop dashboard \
  --period 7d \
  --run-id smoke-it29-bitrix-quality

uv run python config/start.py rop mvp-pack \
  --period 7d \
  --run-id smoke-it29-bitrix-quality
```

Optional live smoke only with explicit approval and available credentials:

```bash
RUN_ID="mvp-welding-live-hardening-20260624-0735"

uv run python config/start.py rop reconcile-bitrix --run-id "$RUN_ID"
uv run python config/start.py rop action-drafts --run-id "$RUN_ID"
uv run python config/start.py rop export-review --run-id "$RUN_ID" --format tsv
uv run python config/start.py rop current --run-id "$RUN_ID"
uv run python config/start.py rop dashboard --period 7d --run-id "$RUN_ID"
uv run python config/start.py rop mvp-pack --period 7d --run-id "$RUN_ID"
```

Security checks:

```text
SAST required
SCA only if dependencies change
lightweight DAST-style route/API misuse checks required if /rop, /api/rop/dashboard or artifact links change
IAST not required
fuzzing optional only for malformed artifact restore tests
```

Secret/content grep:

```bash
grep -R "https://.*bitrix\|/rest/[0-9]\|password\|secret\|token\|raw_eml\|message/rfc822\|attachment_content\|content_bytes" \
  logs storage/runs/smoke-it29-bitrix-quality storage/interfaces -n || true
```

#### DoD

- weak Bitrix candidates are not treated as successful matched results;
- `weak_match` status exists and is visible in artifacts;
- `safe_to_use_as_target` is false for weak/ambiguous/duplicate/not_found/degraded results;
- `not_found` is emitted only when Bitrix connector is healthy and no candidate exists;
- connector failure is represented separately from `not_found`;
- `rop_action_drafts.json` is created for a valid ROP run with Bitrix evidence;
- action drafts are read-only/draft-only and do not execute CRM changes;
- `rop export-review` enriches TSV with Bitrix match quality and recommended action fields when artifacts exist;
- current-state/dashboard/MVP pack distinguish safe matched, weak match, ambiguous, not found, connector degraded and missing evidence;
- no Bitrix write-back exists;
- no POST/write/action route is added;
- no `beeagent-rop` code is changed;
- BeeAgent core does not contain ROP classification/business rules;
- artifact access remains allowlisted;
- path traversal is blocked;
- secrets/raw `.eml`/raw attachment content are not exposed;
- tests and docs are updated;
- required security checks are completed;
- `pyproject.toml.version` is not changed.

### Итерация 30 — ROP execution MVP: latest-N, thread artifacts and bounded AI assist execution v0

**Статус:** DONE

#### Goal

Довести BeeAgent ROP flow до execution-level MVP после закрытия `beeagent-rop It19.1`: BeeAgent должен корректно выбирать последние N сообщений, строить bounded thread artifacts, передавать `thread_context` в `beeagent-rop`, сохранять subtype/queue/action enrichment в batch artifacts и добавить BeeAgent-owned bounded AI assist execution path для спорных событий.

Итерация должна связать уже готовые domain contracts `beeagent-rop` с реальным BeeAgent runtime:

```text
mailbox/json sources
→ latest-N selection
→ normalized_events.json
→ mail_thread_index.json
→ mail_thread_context.json
→ beeagent-rop lead_classification with thread_context
→ classified_events.json with subtype/queue/action fields
→ bounded AI assist request/provider/decision artifacts
→ operator/current/dashboard/MVP artifacts updated where existing builders support it
```

#### Почему это нужно

После It29 BeeAgent уже умеет строить ROP evidence chain до Bitrix match quality gate и read-only action drafts:

```text
source ingestion
→ attachment extraction
→ classification
→ Bitrix reconciliation
→ current-state/dashboard/MVP pack
→ action drafts
```

После `beeagent-rop It19` модуль возвращает более полезную доменную семантику:

```text
case_subtype
recommended_queue
should_rop_see
correct_action
```

После `beeagent-rop It19.1` публичный module path больше не теряет `thread_context`.

Но BeeAgent всё ещё должен закрыть runtime gap:

```text
latest mailbox batch
→ deterministic thread evidence
→ bounded context into module
→ AI assist execution through BeeAgent-owned provider boundary
→ reproducible AI/thread artifacts
```

Без It30 BeeAgent не сможет уверенно двигаться к customer-facing MVP, потому что РОП будет видеть классификацию и Bitrix evidence без thread-aware context и без controlled AI-assist для ambiguous/fallback cases.

#### Depends on

Required:

```text
beeagent-rop It19 — ROP case subtype taxonomy and reviewed TSV evaluation fixtures v1
beeagent-rop It19.1 — Thread context module plumbing hotfix
BeeAgent It29 — ROP Bitrix match quality gate and action drafts v0
```

Important implementation rule:

```text
Do not import private beeagent-rop internals from BeeAgent.
```

If the installed `beeagent-rop` package exposes a public AI assist module case/API, BeeAgent may use it through the public module/package contract.

If a public AI assist merge path is not available yet, BeeAgent must degrade safely:

```text
ai_assist_status = "module_contract_unavailable"
ai_assist_used = false
final classification remains deterministic
AI request/decision artifacts remain available for review
no crash
no private imports
```

#### Scope

**Включено:**

##### 1. Correct latest-N mailbox selection

Fix mailbox source selection so:

```text
items_max=N means newest N messages per source
```

Rules:

- do not rely on raw IMAP search order;
- sort by reliable mailbox/internal date descending;
- use UID/order fallback only when date is missing;
- record warning when fallback ordering is used;
- apply `items_max` after sorting;
- keep selection deterministic per source;
- no raw body or raw `.eml` in selection artifacts;
- no secrets in logs/artifacts.

Add artifact:

```text
storage/runs/<run_id>/mailbox_selection.json
```

Expected shape:

```json
{
  "run_id": "run-id",
  "strategy": "latest_n_by_internaldate_desc",
  "sources": [
    {
      "source_id": "hotline_mailbox",
      "items_max": 50,
      "selected_count": 50,
      "available_count": 120,
      "messages": [
        {
          "source_message_id": "uid-123",
          "internal_date": "2026-06-27T10:15:00Z",
          "message_id": "<bounded-message-id>",
          "subject": "bounded subject",
          "selected": true
        }
      ],
      "warnings": []
    }
  ],
  "warnings": []
}
```

##### 2. Build thread index artifact

Add BeeAgent-owned thread index artifact:

```text
storage/runs/<run_id>/mail_thread_index.json
```

Thread matching order:

```text
1. Message-ID / In-Reply-To / References
2. Same normalized subject within same source/client when reply/forward markers exist
3. Fallback single-event thread
```

Rules:

- BeeAgent builds thread evidence;
- `beeagent-rop` must not reconstruct raw mailbox threads;
- no raw `.eml`;
- no raw headers beyond bounded IDs needed for evidence;
- no attachment content.

Expected shape:

```json
{
  "run_id": "run-id",
  "threads": [
    {
      "thread_id": "thr_001",
      "source_ids": ["hotline_mailbox"],
      "event_ids": ["evt-1", "evt-2"],
      "message_ids": ["<msg1>", "<msg2>"],
      "subject_normalized": "shipping no 1",
      "participants": ["bounded@example.local"],
      "latest_event_id": "evt-2",
      "latest_at": "2026-06-27T10:20:00Z",
      "evidence": {
        "message_id_link": true,
        "references_link": true,
        "subject_fallback": false
      }
    }
  ],
  "warnings": []
}
```

##### 3. Build bounded thread context artifact

Add artifact:

```text
storage/runs/<run_id>/mail_thread_context.json
```

Rules:

- bounded summaries only;
- no raw mailbox thread reconstruction inside artifacts;
- no raw email body;
- no raw attachments;
- no secrets;
- context may support ambiguous cases;
- context must not override confident spam/noise/tender decisions inside BeeAgent.

Expected shape:

```json
{
  "run_id": "run-id",
  "contexts": [
    {
      "event_id": "evt-2",
      "thread_id": "thr_001",
      "reply_or_forward": true,
      "previous_event_ids": ["evt-1"],
      "previous_case_type": "existing_deal",
      "previous_case_subtype": "existing_deal_logistics",
      "participant_overlap": true,
      "previous_subject": "bounded previous subject",
      "previous_summary": "bounded summary, no raw email",
      "thread_context_confidence": 0.78,
      "reason_codes": ["reply_chain", "previous_existing_deal"]
    }
  ],
  "warnings": []
}
```

##### 4. Pass `thread_context` into `beeagent-rop`

For each normalized event:

```text
event
+ bounded thread_context if available
→ RopModule.handle(case_type="lead_classification")
```

Expected module output fields remain module-owned:

```text
case_type
priority
confidence
reason_code
reasoning
is_fallback
case_subtype
recommended_queue
should_rop_see
correct_action
```

Rules:

- BeeAgent only passes context and persists returned fields;
- BeeAgent does not implement ROP subtype rules;
- malformed thread context must degrade safely;
- classification must not crash the whole batch.

##### 5. Produce enriched `classified_events.json`

Update existing artifact:

```text
storage/runs/<run_id>/classified_events.json
```

Each item should include optional enrichment fields when returned by `beeagent-rop`:

```json
{
  "event_id": "evt-001",
  "case_type": "existing_deal",
  "case_subtype": "existing_deal_logistics",
  "recommended_queue": "logistics",
  "should_rop_see": true,
  "correct_action": "check_bitrix",
  "priority": "medium",
  "confidence": 0.72,
  "reason_code": "thread_context_existing_deal_candidate",
  "reasoning": "bounded explanation",
  "is_fallback": true,
  "thread_context_ref": "thr_001",
  "source_id": "hotline_mailbox",
  "sender": "bounded sender",
  "subject": "bounded subject"
}
```

Rules:

- preserve backward compatibility;
- append optional fields only;
- no raw `.eml`;
- no raw attachment content;
- no secrets.

##### 6. Add BeeAgent-owned bounded AI assist execution

Add config block if missing:

```yaml
rop:
  ai_assist:
    enabled: false
    provider: openai_compatible
    model_env: ROP_AI_MODEL
    api_key_env: ROP_AI_API_KEY
    base_url_env: ROP_AI_BASE_URL
    max_events_per_run: 20
    request_timeout_seconds: 30
    min_ai_confidence: 0.70
    dry_run: false
```

Rules:

- default disabled;
- when enabled, required envs must fail fast if missing;
- secrets must never appear in HTML/API/logs/artifacts;
- ROP AI assist must not silently use unrelated `llm.enabled`;
- implementation may reuse existing HTTP/LLM helper code only if config source of truth remains `rop.ai_assist`;
- AI runs only for eligible ambiguous/fallback events;
- AI provider returns structured JSON only;
- invalid model output degrades safely;
- AI cannot execute CRM/mailbox/Bitrix actions;
- AI cannot create write-back payloads;
- AI cannot override safe deterministic guards;
- AI merge must use a public `beeagent-rop` contract if available;
- if public merge contract is unavailable, record degraded status and keep deterministic classification.

##### 7. Add AI assist artifacts

Add artifacts:

```text
storage/runs/<run_id>/rop_ai_assist_requests.json
storage/runs/<run_id>/rop_ai_assist_decisions.json
storage/runs/<run_id>/rop_ai_assist_results.json
```

Request artifact must be redacted/safe:

```json
{
  "event_id": "evt-001",
  "eligible": true,
  "request_preview": {
    "subject": "bounded",
    "body_preview": "bounded",
    "attachment_preview": "bounded",
    "thread_context_summary": "bounded"
  },
  "provider": "openai_compatible",
  "model": "redacted-or-model-name-if-not-secret"
}
```

Decision artifact:

```json
{
  "event_id": "evt-001",
  "status": "ok",
  "ai_case_type": "existing_deal",
  "case_subtype": "existing_deal_logistics",
  "recommended_queue": "logistics",
  "correct_action": "check_bitrix",
  "should_rop_see": true,
  "ai_confidence": 0.82,
  "ai_reason_code": "business_thread_context",
  "risk_flags": []
}
```

Result artifact:

```json
{
  "event_id": "evt-001",
  "ai_assist_used": true,
  "ai_assist_status": "ok",
  "final_case_type": "existing_deal",
  "final_case_subtype": "existing_deal_logistics",
  "final_recommended_queue": "logistics",
  "final_correct_action": "check_bitrix",
  "merge_reason": "validated_ai_assist_for_fallback_case",
  "warnings": []
}
```

If public `beeagent-rop` merge contract is unavailable:

```json
{
  "event_id": "evt-001",
  "ai_assist_used": false,
  "ai_assist_status": "module_contract_unavailable",
  "final_case_type": "existing_deal",
  "merge_reason": "deterministic_result_preserved",
  "warnings": ["Public beeagent-rop AI assist merge contract is not available."]
}
```

##### 8. Update existing operator artifacts where the pipeline already supports it

Update existing summaries/read-models only minimally:

```text
operator_summary.json
rop_current_state.json
storage/interfaces/rop_dashboard.json
rop_mvp_pack.json
rop_mvp_report.md
```

Add counters if relevant:

```text
latest_n_strategy
threaded_event_count
thread_context_available_count
case_subtype_counts
recommended_queue_counts
correct_action_counts
ai_assist_enabled
ai_assist_requested_count
ai_assist_used_count
ai_assist_invalid_count
ai_assist_degraded_count
```

Rules:

- do not redesign UI in It30;
- do not add auth;
- do not add row detail routes;
- do not add Bitrix write-back;
- preserve existing dashboard/API behavior.

**Не включено:**

- changes to `beeagent-rop`;
- new ROP business rules in BeeAgent;
- new subtype taxonomy in BeeAgent;
- CRM/Bitrix write-back;
- `crm.item.add`;
- `crm.item.update`;
- timeline comments;
- task creation;
- mailbox delete/archive/reply/mark-as-read;
- OCR;
- raw PDF/DOCX/XLSX parsing;
- raw `.eml` persistence/rendering;
- raw attachment storage;
- web-triggered ROP run;
- UI auth/session;
- UI row detail;
- Sender/Subject UI polish;
- BeeUI core changes;
- new generic BeeUI components;
- separate frontend;
- manager scoring;
- 1C integration.

#### Deliverable

BeeAgent can run ROP execution MVP with deterministic latest-N selection, thread evidence and bounded AI assist artifacts:

```bash
uv run python config/start.py rop run \
  --source-id rop_batch_sample \
  --items-max 2 \
  --run-id smoke-it30-rop-execution

uv run python config/start.py rop current \
  --run-id smoke-it30-rop-execution

uv run python config/start.py rop dashboard \
  --period 7d \
  --run-id smoke-it30-rop-execution

uv run python config/start.py rop mvp-pack \
  --period 7d \
  --run-id smoke-it30-rop-execution
```

Expected new artifacts:

```text
storage/runs/<run_id>/mailbox_selection.json
storage/runs/<run_id>/mail_thread_index.json
storage/runs/<run_id>/mail_thread_context.json
storage/runs/<run_id>/rop_ai_assist_requests.json
storage/runs/<run_id>/rop_ai_assist_decisions.json
storage/runs/<run_id>/rop_ai_assist_results.json
```

Updated existing artifacts:

```text
storage/runs/<run_id>/classified_events.json
storage/runs/<run_id>/operator_summary.json
storage/runs/<run_id>/rop_current_state.json
storage/interfaces/rop_dashboard.json
storage/runs/<run_id>/rop_mvp_pack.json
storage/runs/<run_id>/rop_mvp_report.md
```

#### Config / contract impact

Expected:

```text
config/settings.yml may add rop.ai_assist
src/beeagent_module/core/settings.py validates rop.ai_assist fail-fast
artifact contract changes
CLI/runtime behavior changes
module integration behavior changes
docs update required
```

Source of truth:

```text
config/settings.yml → rop.sources[]
config/settings.yml → rop.ai_assist
storage/runs/<run_id>/* → run evidence
beeagent-rop public module contract → ROP classification semantics
```

#### Change level

```text
security-sensitive
```

Reason:

- AI provider execution;
- env/secret handling;
- external provider call;
- structured model output validation;
- mailbox selection behavior;
- artifact restore/parsing/serialization;
- module/capability boundary;
- future action/write-back safety boundary.

No dependency change is expected. SCA is required only if dependencies change.

#### Checks

Required:

```bash
uv run pytest -q
uv run pytest -q -k "rop or mailbox or thread or ai or web or ui"
```

Targeted tests:

```text
latest-N selects newest messages, not oldest
latest-N works per source
missing date fallback records warning
mailbox_selection.json is created and safe
thread index from Message-ID/References
thread index subject fallback
single-event thread fallback
mail_thread_index.json shape
mail_thread_context.json shape
thread_context passed into beeagent-rop payload
malformed thread_context degrades safely
classified_events.json includes case_subtype/recommended_queue/should_rop_see/correct_action when returned by module
AI assist disabled by default
AI assist enabled with missing env fails fast
AI eligible fallback event creates request artifact
confident spam/noise does not trigger AI
confident new_lead does not trigger AI
AI provider invalid output degrades safely
AI output with executable/write-back instruction is rejected
AI result preserves deterministic classification when module merge contract is unavailable
AI artifacts contain no secrets
operator/current/dashboard/MVP counters update without UI redesign
no GET mutation
no mailbox destructive actions
no CRM/Bitrix mutation
path traversal run_id rejected/degraded
```

Smoke:

```bash
uv run python config/start.py rop run \
  --source-id rop_batch_sample \
  --items-max 2 \
  --run-id smoke-it30-rop-execution

uv run python config/start.py rop current \
  --run-id smoke-it30-rop-execution

uv run python config/start.py rop dashboard \
  --period 7d \
  --run-id smoke-it30-rop-execution

uv run python config/start.py rop mvp-pack \
  --period 7d \
  --run-id smoke-it30-rop-execution
```

Optional AI smoke only with explicit test env:

```bash
ROP_AI_MODEL="test-model"
ROP_AI_API_KEY="test-key"
ROP_AI_BASE_URL="http://127.0.0.1:<fake-provider-port>"
uv run python config/start.py rop run \
  --source-id rop_batch_sample \
  --items-max 2 \
  --run-id smoke-it30-ai-enabled
```

Security checks:

```bash
grep -R "ROP_AI_API_KEY\|OPENAI_API_KEY\|password\|secret\|token\|raw_eml\|message/rfc822\|attachment_content\|content_bytes" \
  logs storage/runs/smoke-it30-rop-execution storage/interfaces -n || true
```

Also verify:

```text
SAST required
SCA only if dependencies change
DAST-style CLI/runtime misuse checks for malformed artifacts and invalid run_id
IAST not required
fuzzing optional for malformed AI decision / thread context payloads
```

#### DoD

- latest-N mailbox selection is deterministic and evidenced;
- `mailbox_selection.json` is created;
- `mail_thread_index.json` is created;
- `mail_thread_context.json` is created;
- bounded `thread_context` reaches `beeagent-rop` public module path;
- `classified_events.json` preserves subtype/queue/action fields from `beeagent-rop`;
- AI assist is disabled by default;
- AI assist config is explicit and fail-fast when enabled;
- AI provider execution is BeeAgent-owned;
- AI output is structured and validated;
- invalid/malicious AI output degrades safely;
- no private `beeagent-rop` internals are imported by BeeAgent;
- missing public AI merge contract degrades safely;
- no CRM/Bitrix/mailbox mutation exists;
- no POST/write/action route is added;
- no raw `.eml`/raw attachment content/secrets appear in logs/artifacts/API/HTML;
- existing ROP CLI/web paths remain backward-compatible;
- tests and docs are updated;
- required security checks are completed;
- `pyproject.toml.version` is not changed.

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
