# DEV_GUIDE — запуск, окружение, модули, SDLC-light

## Purpose

Этот документ описывает:

- как запускать `beeagent`;
- как работать с окружением и зависимостями через `uv`;
- где смотреть логи и артефакты;
- как подключать и разрабатывать внешние доменные модули;
- как вести разработку в рамках текущего SDLC-light процесса;
- как формулировать задачи для Copilot / AI так, чтобы изменения были консистентны с архитектурой проекта, `docs/ROADMAP.md`, `docs/SDLC.md` и `docs/SECURITY.md`.

## Related project docs

Этот документ используется вместе с:

- `docs/ROADMAP.md` — этапы, итерации, scope, artifacts, checks, DoD;
- `docs/SDLC.md` — lightweight process, change levels, required checks, PR flow;
- `docs/SECURITY.md` — secure development rules и security checks по типу изменения.

Правило:

> `DEV_GUIDE` не заменяет `ROADMAP`, `SDLC` и `SECURITY`, а помогает разработчику быстро применять их на практике.

## Требования

- Python 3.12+
- `uv`

## Установка (dev)

В корне проекта:

```
uv sync
```

Запуск выполняй через `uv run`, активация venv не нужна.

## Управление зависимостями (`uv`)

Источник правды по зависимостям:

- `pyproject.toml` — список зависимостей и constraints
- `uv.lock` — зафиксированные версии для воспроизводимой установки

Правило проекта:

> После `uv add`, `uv remove`, `uv lock --upgrade` всегда коммить **и** `pyproject.toml`, **и** `uv.lock`.

### Базовые команды

| Что сделать                    | Команда                          | Что произойдёт / что проверить          |
| ------------------------------ | -------------------------------- | --------------------------------------- |
| Поставить зависимости по lock  | `uv sync`                        | Ставит ровно то, что в `uv.lock`.       |
| Запустить проект               | `uv run python3 config/start.py` | Запуск без активации venv.              |
| Добавить runtime-зависимость   | `uv add <pkg>`                   | Обновит `pyproject.toml` и `uv.lock`.   |
| Добавить dev-зависимость       | `uv add --dev <pkg>`             | Добавит зависимость для разработки.     |
| Удалить зависимость            | `uv remove <pkg>`                | Обновит `pyproject.toml` и `uv.lock`.   |
| Посмотреть дерево зависимостей | `uv tree`                        | Диагностика зависимостей.               |
| Апгрейднуть lock               | `uv lock --upgrade`              | Обновит `uv.lock` в рамках constraints. |

## Запуск

Основной запуск:

```bash
bash start.sh
```

`start.sh` должен делать:

- проверку наличия `uv`;
- `uv sync`;
- `uv run python3 config/start.py`.

### Прямой запуск

```
uv run python3 config/start.py
```

## Архитектурное правило проекта

`beeagent` — это **ядро оркестрации**, а не доменный модуль.

Схема:

`UI/Transport -> BeeAgent core -> module -> capability/MCP/n8n -> external systems`

Это означает:

- core отвечает за:
  - orchestration;
  - state;
  - run/session context;
  - artifacts;
  - policy / approval / authority boundaries;
  - module loading;
  - capability boundary.

- доменная логика живёт в отдельных пакетах:
  - `beeagent-rop`
  - будущие `beescan`
  - будущие `merch`

Правило:

> Не тащи клиентскую бизнес-логику в `beeagent_module/core`, если она должна жить в отдельном доменном модуле.

## Подключение внешних модулей

`beeagent` должен уметь работать с внешними package-based модулями.

Базовый dev-путь:

1. рядом с `beeagent` существует отдельный репозиторий модуля, например:
   - `/home/bee/Projects/beeagent-rop`

2. модуль ставится в окружение `beeagent` как editable package:

```
uv add --editable ../beeagent-rop
```

После этого `beeagent` может импортировать модуль как обычный python package.

### Правило

- `beeagent` — отдельная репа;
- `beeagent-rop` — отдельная репа;
- интеграция идёт через package install + module contract;
- не копируй код модуля внутрь `beeagent`.

## Настройка

Источник правды для runtime-поведения:

- `config/settings.yml`

Это означает:

- обязательные ключи не должны “магически” появляться из кода;
- для новых обязательных ключей должна быть явная валидация в `src/beeagent_module/core/settings.py`;
- если обязательного ключа нет — приложение должно падать fail-fast с понятной ошибкой на старте.

### Правило по конфигу

Не создавай второй source of truth.

Если добавляешь новый config key:

- опиши его в `config/settings.yml`;
- добавь fail-fast validation в `src/beeagent_module/core/settings.py`;
- обнови docs, если меняется runtime contract.

## Логи

Основные места:

- `stdout`
- `logs/app.log`

### Правила по логам

Логи должны быть:

- понятными;
- на английском языке;
- достаточными для диагностики текущей итерации;
- без утечки секретов.

Не добавляй:

- сырые secret/env values;
- дампы токенов, ключей и чувствительных payload;
- лишний debug noise без необходимости.

## Артефакты в `storage/`

Типовые директории:

- `storage/runs/<run_id>/` — runtime артефакты запуска
- `storage/artifacts/<run_id>/` — человекочитаемые отчёты / вывод
- `storage/sessions/` — session state
- `storage/telemetry/` — transport telemetry
- `storage/mock/` — mock datasets

### Правила по артефактам

Артефакты должны быть:

- воспроизводимыми;
- объяснимыми;
- консистентными с логами;
- согласованными с текущей итерацией ROADMAP;
- безопасными по содержимому.

Не допускается:

- утечка секретов;
- хаотичная запись файлов без linkage к `run_id`/`session_id`;
- скрытое изменение JSON/JSONL contract без обновления docs.

## Граница между core и module

### Это относится к `beeagent`

- `core/*`
- `cases/*`
- `adapters/*` общего назначения
- transport/UI слой
- module contract
- module registry
- runtime context
- artifact API
- capability abstraction
- approvals / policies / execution boundaries

### Это относится к доменному модулю (`beeagent-rop`)

- client-specific contracts
- lead classification
- duplicate resolution
- attachment-aware triage
- rop summary
- client-specific recommendations
- fixture cases клиента

Правило:

> Если изменение нужно только для логики клиента Welding/ROP, по умолчанию оно должно жить в `beeagent-rop`, а не в core.

## SDLC-light workflow

В проекте используется упрощённый, но дисциплинированный процесс:

1. `ROADMAP` фиксирует итерацию
2. под итерацию создаётся `Issue`
3. работа идёт в отдельной ветке
4. изменения ограничиваются scope текущей итерации
5. определяется `change level`
6. выполняются tests, smoke-check, log/artifact check и required quality/security checks
7. результат оформляется в `PR`
8. итерация считается закрытой после merge и выполнения DoD

## Change levels

### low-risk

Примеры:

- docs;
- локальные тесты;
- naming / comments;
- безопасные косметические изменения.

### runtime-risk

Примеры:

- orchestrator;
- config validation;
- CLI / transport;
- artifacts;
- module loading;
- case dispatch;
- session/run flow.

### security-sensitive

Примеры:

- secrets / env handling;
- MCP/tool boundaries;
- external connectors;
- file parsing;
- serialization / deserialization;
- file/path handling;
- authority paths.

## Что проверять перед PR

Минимум:

```
uv run pytest -q
bash start.sh
```

Плюс:

- ручная проверка `logs/app.log`
- ручная проверка relevant files в `storage/`

### Типовой verification checklist

- конфиг читается корректно;
- новые обязательные ключи валидируются fail-fast;
- run/session/artifact linkage не сломан;
- storage-артефакты пишутся туда, куда ожидается;
- логи понятны;
- секреты не протекли;
- изменение не вылезло за scope текущей итерации;
- required checks по change level действительно выполнены.

## Workspace и работа с двумя репами

Рекомендуемый вариант:

- один VS Code workspace;
- две папки:
  - `beeagent`
  - `beeagent-rop`

Рабочая модель:

- core changes делаешь в `beeagent`
- domain changes делаешь в `beeagent-rop`
- запускаешь runtime из `beeagent`
- модуль подтягивается как editable dependency

### Практическое правило

Если хочешь проверить интеграцию:

1. обновляешь код модуля;
2. запускаешь тесты в `beeagent-rop`;
3. запускаешь `beeagent` через `bash start.sh`;
4. проверяешь, что core видит и вызывает модуль корректно.

## Copilot / AI prompt template (beeagent)

```
Нужно внести изменения в проект `beeagent` (НЕ только в текущий файл).

### Контекст

- Проект: `beeagent` (`Python 3.12+`, `uv`)
- Архитектура: stateful orchestrator, артефакты в `storage/`, логи в `logs/app.log`
- SDLC-light: `ROADMAP → Issue → branch → code → tests → artifacts → PR → merge`
- Источник правды для runtime/config: `config/settings.yml`
- `beeagent` = core/orchestrator/runtime/module platform
- Доменные модули (`beeagent-rop`, будущие `beescan`, `merch`) живут отдельно и не должны без причины затаскиваться в core
- Основные process/security rules:
  - `docs/ROADMAP.md`
  - `docs/SDLC.md`
  - `docs/SECURITY.md`
- Итерация закрывается через `PR`, поэтому изменения должны быть проверяемыми, воспроизводимыми и согласованными с логами/артефактами

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
- Не меняй чужой scope итерации и не протаскивай “на будущее” недоделанную архитектуру.
- Не убирай существующие проверки без явной причины.
- Не тащи client-specific бизнес-логику в `beeagent`, если она должна жить в отдельном модуле.
- Если видишь, что изменение относится к доменному модулю, а не к core, прямо укажи это в ответе.

### Config / source of truth rules

- Источник правды: `config/settings.yml`. Обязательные ключи не должны иметь скрытых дефолтов в коде.
- Перед добавлением нового config-блока сначала проверь, нельзя ли переиспользовать уже существующий top-level/shared контракт.
- Не создавай второй source of truth и не дублируй общий runtime/system-level контракт внутри module/case/adapter, если это не требуется текущей итерацией.
- Если добавляется новый обязательный config key, он должен:
  - быть явно описан в `config/settings.yml`;
  - валидироваться в `src/beeagent_module/core/settings.py`;
  - падать fail-fast с понятной ошибкой при отсутствии.
- Если предлагаешь новый config key, сначала объясни, почему нельзя переиспользовать существующий контракт.
- В ответе явно укажи, какой блок после изменения является source of truth.

### Core / module boundary rules

- `beeagent` отвечает за:
  - orchestration;
  - state / session / run context;
  - module contract;
  - module registry;
  - artifact API;
  - capability boundary;
  - approvals / authority / policy;
  - transport/UI integration.
- `beeagent` НЕ должен без причины брать на себя:
  - клиентскую классификацию;
  - клиентские rules;
  - client-specific summary/recommendation logic;
  - attachment/business parsing, относящийся к одному модулю.
- Если задача касается reusable contract/platform behavior — это `beeagent`.
- Если задача касается только одного клиентского модуля — это не `beeagent`, а отдельный модульный репозиторий.

### Docs / contracts / artifacts

- Если меняется runtime-поведение, config-контракт, module contract, CLI/entrypoint, storage artifacts или docs-contract, проверь, нужно ли обновить:
  - `docs/ROADMAP.md`
  - `README.ru.md` или `README.md`
  - `docs/DEV_GUIDE.md`
  - `docs/SDLC.md`
  - `docs/SECURITY.md`
- Если меняются артефакты, покажи какие именно файлы появятся/изменятся в `storage/`.
- Если меняется JSON/JSONL/meta-контракт, покажи пример одного объекта/строки.
- После работы дай короткий чеклист для PR/отчёта.

### Code style / execution rules

- Соблюдай PEP 8: имена, длина строк, структура.
- Добавляй короткие комментарии на русском только там, где без них теряется смысл.
- Логи, имена полей, JSON/JSONL, runtime messages — на английском языке.
- Все команды запуска, тестов и smoke-check указывай через `uv run`, если это применимо.
- Не предлагай второй runtime, второй orchestrator или отдельный service/container без явной необходимости по итерации.

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
- Для каждого нового или изменённого config key укажи:
  - где он живёт;
  - почему именно там;
  - почему это не создаёт второй source of truth
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
- `README.md` или `README.ru.md`
- `pyproject.toml`
- `config/start.py`
- `config/settings.yml`
- `src/beeagent_module/core/settings.py`
- `src/beeagent_module/core/app.py`

Если нужно, добавь и прочитай также:

- `src/beeagent_module/core/log.py`
- `src/beeagent_module/core/paths.py`
- `src/beeagent_module/core/llm.py`
- `src/beeagent_module/cases/*`
- `src/beeagent_module/adapters/*`
- `src/beeagent_module/ui/*`
- `tests/test_smoke.py`
- другие релевантные тесты

### Ожидаемый результат

- работает ожидаемый entrypoint (`uv run ...` / `bash start.sh` или нужный transport/CLI path)
- `uv run pytest -q` проходит
- логи остаются понятными
- артефакты в `storage/` создаются и консистентны
- новые обязательные ключи валидируются fail-fast
- required checks для данного `change level` определены и перечислены
- изменение готово к оформлению в PR по текущей итерации
```

## Чего не делать

- не тащи ROP/Welding-специфику в `beeagent_module/core`;
- не добавляй обязательные config keys только в коде без `settings.yml`;
- не делай hidden coupling между core и одним клиентским модулем;
- не закрывай итерацию словами “вроде работает”;
- не оставляй runtime changes без tests / smoke / artifact check;
- не допускай утечки секретов в логи и storage;
- не смешивай scope нескольких итераций в одном PR.

## Быстрый рабочий сценарий

1. открыть `docs/ROADMAP.md`
2. выбрать текущую итерацию
3. открыть или создать issue
4. определить `change level`
5. создать ветку
6. внести изменения
7. прогнать:
   - `uv run pytest -q`
   - `bash start.sh`
   - required checks из `docs/SDLC.md` / `docs/SECURITY.md`

8. проверить:
   - `logs/app.log`
   - relevant artifacts in `storage/`

9. оформить PR
10. после review — merge

## Резюме

`beeagent` развивается маленькими, проверяемыми итерациями.

Ключевая дисциплина проекта:

- core остаётся универсальным;
- модульная логика живёт в отдельных репах;
- конфиг — источник правды;
- fail-fast валидация обязательна;
- логи и артефакты должны быть объяснимыми;
- изменения проверяются по change level;
- итерации закрываются через PR.
