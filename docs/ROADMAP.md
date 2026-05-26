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
