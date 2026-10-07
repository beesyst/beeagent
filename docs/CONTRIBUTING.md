# CONTRIBUTING

Этот репозиторий использует Conventional Commits, чтобы release-please автоматически:

- повышал версию (SemVer)
- генерировал Release Notes / CHANGELOG
- создавал теги вида vX.Y.Z

Важно: версия повышается не на каждый коммит, а при выпуске релиза (через Release PR от release-please).

Простой и дисциплинированный workflow:

`ROADMAP → Issue → branch → code → tests → artifacts → PR → merge`

Цель:

- маленькие и понятные изменения;
- воспроизводимые проверки;
- минимальная бюрократия;
- чистая история изменений;
- безопасная работа с core platform.

## Главные правила

- `main` — единственная стабильная ветка;
- любая работа делается в отдельной ветке;
- любые изменения закрываются через PR;
- не смешивать несколько разных задач в одном PR;
- не тащить клиентскую бизнес-логику в `beeagent` core;
- если меняется runtime/config/module loading/capability boundary — это как минимум `runtime-risk`;
- если меняются secrets, external connectors, file parsing, dependency surface или authority paths — это `security-sensitive`.

## Что относится к beeagent

В этом репозитории живёт только платформенный слой:

- orchestration core;
- module contract;
- module registry;
- runtime context;
- artifact API;
- capability boundary;
- transport/UI;
- logging/observability;
- config/settings validation.

Клиентская доменная логика сюда не тащится.

## Ветки

Правило: `main` — единственная стабильная/релизная ветка. Любые изменения делаем в отдельной ветке → PR → merge в `main` (желательно squash merge).

Именование веток (ветка = одна задача):

- `feat/<short-title>` — новая функциональность
- `fix/<short-title>` — исправление бага
- `docs/<short-title>` — документация
- `chore/<short-title>` — обслуживание/инфра/настройки
- `test/<short-title>` — тесты

Если есть номер Issue, добавляй его:

- `feat/12-module-registry-v0`
- `fix/18-artifact-path-validation`

Примеры команд:

- создать ветку: `git switch -c feat/config-schema`
- отправить в origin: `git push -u origin HEAD`

### Команды

| Шаг | Цель (что делаем)                                        | Команда(ы)                                     | Что ты увидишь / как понять                                                                                                      |
| --: | -------------------------------------------------------- | ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
|   0 | Проверить, что рабочая папка чистая и ты на нужной ветке | `git status`                                   | `On branch main` (или другая) + `working tree clean` = всё ок. Если есть “Changes not staged…” — есть незакоммиченные изменения. |
|   1 | Посмотреть локальные ветки и текущую ветку               | `git branch`                                   | Текущая ветка помечена `*` (например `* main`).                                                                                  |
|   2 | Создать новую ветку под задачу и переключиться на неё    | `git switch -c docs/contributing`              | Git переключит тебя на новую ветку. Проверка: `git status` покажет `On branch docs/contributing`.                                |
|   3 | Добавить нужный файл(ы) в индекс (staging)               | `git add docs/CONTRIBUTING.md`                 | После этого в `git status` файл будет в `Changes to be committed`.                                                               |
|   4 | Создать коммит с правильным сообщением                   | `git commit -m "docs: add contributing guide"` | Git создаст коммит и покажет, сколько файлов изменено.                                                                           |
|   5 | Запушить ветку на GitHub и “привязать” upstream          | `git push -u origin docs/contributing`         | Ветка появится на GitHub. `-u` позволит дальше пушить просто `git push`.                                                         |
|   6 | Открыть PR на GitHub и влить в `main`                    | _(в браузере)_ PR → **Squash and merge**       | После мержа изменения окажутся в `main`. Обычно ветку можно удалить кнопкой “Delete branch”.                                     |
|   7 | Обновить локальный `main` после мержа PR                 | `git switch main` + `git pull`                 | Локальный `main` подтянет изменения, которые ты влил через PR.                                                                   |
|   8 | Посмотреть удалённые ветки (origin)                      | `git branch -r`                                | Список веток на сервере, например `origin/main`, `origin/docs/contributing`.                                                     |
|   9 | Посмотреть все ветки (локальные + удалённые)             | `git branch -a`                                | Полный список: локальные + `remotes/origin/...`.                                                                                 |
|  10 | (Опционально) Удалить локальную ветку после мержа        | `git branch -d docs/contributing`              | Удалит ветку локально, если она уже смержена. Если не даёт — значит не смержена.                                                 |

Мини-цепочка на каждую задачу: status → checkout -b → add → commit → push → PR → checkout main → pull

## Процесс работы

### Tech Lead (мержит в main)

**Старт и создание новой ветки**

```
git switch main
git pull --ff-only
git switch -c feat/8-iteration-0-frame_and_launch
```

**Коммит + пуш**

```
git add .
git commit -m "feat: iteration 0 fame and launch"
git push -u origin HEAD
```

**PR и для проверок соразработчика**

1. Перейти в PR на GitHub, найти `feat/8-iteration-0-frame_and_launch` и нажать `Compare & pull request`.
2. В `Add a description` внести `Fixes #8` (номер закрывающего ишью) и нажать `Create pull request`.
3. `Squash and merge` → `Confirm squash and merge` в `main`.

Правило:

- `Squash and merge` выполняет только Tech Lead после проверки PR;
- соразработчик PR не мержит самостоятельно.

4. `Delete branch`
5. После мержа обновить локальный `main`:

```
git switch main
git pull --ff-only
```

6. Удалить локальную ветку:

```
git branch -d feat/8-iteration-0-frame_and_launch
```

или удалить ветку на origin:

```
git push origin --delete feat/8-iteration-0-frame_and_launch
```

и почистить локальные ссылки

```
git fetch -p
```

**После обновления зависимости `beeui` в `beeagent`**

```
uv lock --upgrade-package beeui
./start.sh
uv pip show beeui

git add uv.lock
git commit -m 'chore(deps): update beeui'
git push
```

### Production Deploy

Каждый deploy создаёт новый release:

```text
/opt/beeagent/
├── current -> /opt/beeagent/releases/<active-release>
└── releases/
    ├── <previous-release>/
    │   ├── beeagent/
    │   │   ├── .env -> /var/lib/beeagent/shared/.env
    │   │   └── storage -> /var/lib/beeagent/storage
    │   └── beeagent-rop/
    └── <new-release>/
        ├── beeagent/
        │   ├── .env -> /var/lib/beeagent/shared/.env
        │   ├── storage -> /var/lib/beeagent/storage
        │   └── config/settings.yml
        └── beeagent-rop/
```

Постоянные production-данные хранятся отдельно от release:

```text
/var/lib/beeagent/
├── shared/
│   └── .env
└── storage/
```

`systemd` и VS Code используют стабильные пути:

```text
/opt/beeagent/current/beeagent
/opt/beeagent/current/beeagent-rop
```

Поэтому при переключении release конфигурацию VS Code и systemd менять не нужно.

#### Первичная настройка persistent state

Выполняется **один раз на сервере**.

Проверить:

```bash
sudo test -f /var/lib/beeagent/shared/.env && echo "shared env: OK" || echo "shared env: MISSING"
sudo test -d /var/lib/beeagent/storage && echo "storage: OK" || echo "storage: MISSING"
```

Создать persistent-каталоги:

```bash
sudo install -d -o bee -g beeagent -m 2770 /var/lib/beeagent/shared
sudo install -d -o beeagent -g beeagent -m 2770 /var/lib/beeagent/storage
```

Если это **уже работающий сервер** и `/var/lib/beeagent/shared/.env` ещё отсутствует, скопировать текущий production `.env`:

```bash
sudo install -o bee -g beeagent -m 0660 /opt/beeagent/current/beeagent/.env /var/lib/beeagent/shared/.env
```

После этого один раз перевести текущий active release на persistent `.env`:

```bash
sudo systemctl stop beeagent-web
cd /opt/beeagent/current/beeagent
sudo rm -f .env
sudo ln -s /var/lib/beeagent/shared/.env .env
sudo systemctl start beeagent-web
```

Проверить:

```bash
readlink -f /opt/beeagent/current/beeagent/.env
```

Ожидается:

```text
/var/lib/beeagent/shared/.env
```

Проверить возможность atomic write от пользователя `beeagent`:

```bash
sudo -u beeagent -H sh -c 'TEST=/var/lib/beeagent/shared/.write-test-$$; : > "$TEST" || exit 1; rm -f "$TEST"; echo "shared env writable: OK"'
```

Проверить сервис:

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS https://rop.welding.kz/health
```

Если это **новый сервер без `/opt/beeagent/current`**, создать пустой persistent `.env`:

```bash
sudo install -o bee -g beeagent -m 0660 /dev/null /var/lib/beeagent/shared/.env
```

Production-specific значения затем настраиваются в:

```text
/var/lib/beeagent/shared/.env
```

После первичной настройки `.env` между releases больше не копируется.

#### Создание нового release

На VPS:

```bash
cd /opt/beeagent/releases
readlink -f /opt/beeagent/current
REL=20260930-016
sudo install -d -o bee -g beeagent -m 0750 "$REL"
```

Использовать новый уникальный `REL` для каждого deploy.

#### Получить обновленный BeeAgent из GitHub

```bash
git clone git@github-beeagent-prod:beesyst/beeagent.git "$REL/beeagent"
grep '^version = ' "$REL/beeagent/pyproject.toml"
```

#### Получить обновленный BeeSDK из GitHub

```bash
git clone https://github.com/beesyst/beesdk.git "$REL/beesdk"
grep '^version = ' "$REL/beesdk/pyproject.toml"
```

#### Получить обновленный beeagent-rop из GitHub

```bash
git clone git@github-beeagent-rop-prod:beesyst/beeagent-rop.git "$REL/beeagent-rop"
grep '^version = ' "$REL/beeagent-rop/pyproject.toml"
```

#### Подключить persistent state

Перейти в новый BeeAgent:

```bash
cd "/opt/beeagent/releases/$REL/beeagent"
```

Подключить production `.env`:

```bash
rm -f .env
ln -s /var/lib/beeagent/shared/.env .env
```

Подключить persistent storage:

```bash
rm -rf storage
ln -s /var/lib/beeagent/storage storage
```

#### Подготовить logs

```bash
sudo chown -R beeagent:beeagent logs
sudo chmod 2770 logs
sudo install -o beeagent -g beeagent -m 0660 /dev/null logs/app.log
```

#### Подготовить environment

```bash
./start.sh
uv run --frozen --no-sync pytest -q
```

Если тесты не проходят — release не активировать.

#### Активировать новый release

```bash
sudo ln -sfn "/opt/beeagent/releases/$REL" /opt/beeagent/current
readlink -f /opt/beeagent/current
```

#### Перезапустить BeeAgent

```bash
sudo systemctl restart beeagent-web
sudo systemctl status beeagent-web --no-pager
```

#### Проверить

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS https://rop.welding.kz/health
```

Проверить persistent state через активный release:

```bash
cd /opt/beeagent/current/beeagent
test "$(readlink -f .env)" = "/var/lib/beeagent/shared/.env" && test "$(readlink -f storage)" = "/var/lib/beeagent/storage" && echo "persistent state: OK" || exit 1
```

В VS Code Remote SSH после переключения release рекомендуется:

```text
Developer: Reload Window
```

#### Rollback

Посмотреть текущий и доступные releases:

```bash
readlink -f /opt/beeagent/current
ls -lah /opt/beeagent/releases
```

Перед rollback убедиться, что предыдущий release использует persistent `.env`:

```bash
readlink -f /opt/beeagent/releases/<previous-release>/beeagent/.env
```

Ожидается:

```text
/var/lib/beeagent/shared/.env
```

Переключить `current`:

```bash
sudo ln -sfn /opt/beeagent/releases/<previous-release> /opt/beeagent/current
```

Перезапустить:

```bash
sudo systemctl restart beeagent-web
```

Проверить:

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS https://rop.welding.kz/health
```

Rollback меняет только release. Persistent `.env` и `storage` остаются теми же.

#### Очистка старых releases

Проверить текущий release:

```bash
readlink -f /opt/beeagent/current
```

Посмотреть releases:

```bash
ls -lah /opt/beeagent/releases
```

Удалять только старые releases, которые точно не являются `current` и больше не нужны для rollback:

```bash
sudo rm -rf /opt/beeagent/releases/20260904-013
```

Проверить:

```bash
ls -lah /opt/beeagent/releases
```

#### ROP Web projection

Обычный deploy **не требует** rebuild ROP Web projection.

ROP runtime state и Web projection находятся в persistent storage:

```text
/var/lib/beeagent/storage
```

и сохраняются между releases.

Если после deploy `/rop` не открывается корректно, сначала открыть страницу без старого `run_id`, например:

```text
/rop?period=7d
```

Если проблема остаётся, выполнить обычное обновление projection:

```bash
cd /opt/beeagent/current/beeagent
./start.sh rop dashboard --period 7d
```

Если команда явно сообщает:

```text
ROP Web projection refresh skipped: explicit dashboard regeneration is required
```

только тогда выполнить полный rebuild:

```bash
./start.sh rop dashboard --period 7d --rebuild-web-projection
```

Full rebuild может быть долгим и не является частью обычного deploy.

Если rebuild сообщает:

```text
history preparation complete runs=0 anchors=0
```

проверить persistent storage:

```bash
readlink -f storage
```

Ожидается:

```text
/var/lib/beeagent/storage
```

### Проверка PR соразработчика

**Создать отдельную папку под PR, выполняется из основной папке проекта**

```
git fetch origin
git worktree add -b review/pr141 ../beeagent-pr141 origin/feat/137-local_env_and_auth_diagnostics
cd ../beeagent-pr141
code .
git status
git branch
```

**Посмотреть, какие файлы изменил соразработчик относительно origin/main**

```
git fetch origin
git diff --name-only origin/main...HEAD
```

или посмотреть, что соразработчик изменил в конкретном файле

```
git diff origin/main...HEAD -- config/start.py
```

**Делай `git restore` только для тех файлов, которые не относятся к текущей задаче**

```
git restore uv.lock docs/AUTH_LOGS.md
git status
```

**Наложить ветку помощника на свежий `origin/main`, но сначала убедись, что рабочее дерево чистое**

```
git status
```

Если есть `Changes not staged / Changes to be committed`, то сделай коммит и `rebase`:

```
git add .
git commit -m 'ci(docs): adjust docs workflow for private repo'
git fetch origin
git rebase origin/main
```

Если нет изменений после `git status`, то:

```
git fetch origin
git rebase origin/main
```

**Если нет ошибок**

```
uv run pytest -q
```

**Запушить изменения в ветку соразработчика**

```
git push --force-with-lease origin HEAD:feat/137-local_env_and_auth_diagnostics
```

**Если всё ок**

- обновить описание PR;
- ппроверить вкладку Files changed;
- выполнить Squash and merge;
- удалить ветку на GitHub;
- обновить локальный main.

**Из основной папки репо удалить worktree, ветку и обновить main**

```
cd ../beeagent
git worktree remove ../beeagent-pr141
git branch -D review/pr141
git switch main
git pull --ff-only
```

### Соразработчик (делает PR)

**Перед началом задачи**

```
git switch main
git pull --ff-only
git switch -c feat/<short-title>
```

**Коммит + пуш + PR**

```
git add .
git commit -m "feat: <short>"
git push -u origin feat/<short-title>
```

В PR:

- укажи Refs #<issue> пока PR на проверке;
- не выполняй merge самостоятельно;
- не нажимай Squash and merge;
- после замечаний Tech Lead допушивай изменения в ту же ветку PR.

**Если пока соразработчик работает, в main вмержили новые изменения**

```
git fetch origin
git rebase origin/main
git push --force-with-lease
```

**После мержа PR**

```
git switch main
git pull --ff-only
```

## Issues и Kanban

Любая работа и любая идея оформляется как Issue (не как отдельная карточка в Project). Project (Kanban) показывает статус Issues.

Правило:

1. Создай Issue (таск = Issue).
2. Создай ветку под Issue.
3. Сделай PR в main.
4. В описании PR используй:

- `Refs #123` — если PR еще в работе или на ревью;
- `Fixes #123` / `Closes #123` — когда PR подтвержден к merge.

Важно:

- `Fixes/Closes` в PR **не закрывает** Issue в момент создания PR;
- Issue закроется **только после merge PR в `main`**;
- по умолчанию для PR соразработчика лучше ставить `Refs #123`, а перед merge Tech Lead меняет на `Closes #123`.

Лейблы:

- prio:high/medium/low
- (опционально) bug/enhancement/doc/idea

Используй:

- `Feature: <short title>` — новая функциональность
- `Fix: <short title>` — исправление бага
- `Bug: <short title>` — баг-репорт (ещё не факт что фиксишь прямо сейчас)
- `Docs: <short title>` — документация
- `Chore: <short title>` — обслуживание/инфра/рефактор без фич
- `Idea: <short title>` — идея/набросок (потом можно превратить в Feature/Fix)

**Примеры:**

- `Feature: add risk profiles (conservative/normal/aggressive)`
- `Fix: prevent crash on empty candles`
- `Bug: wrong PnL calculation on partial fills`
- `Docs: explain config keys and examples`
- `Chore: add pre-commit formatting`
- `Idea: capital allocation per strategy`

## Коммиты

Формат: <type>(<scope>)!: <кратко что сделано>

scope — опционально (например: api, parser, docs, ci). ! — признак ломающего изменения (MAJOR).

Таблица типов (KISS):

| Тип       | Когда использовать                          | Влияние на версию |
| --------- | ------------------------------------------- | ----------------- |
| feat:     | новая функциональность                      | +MINOR            |
| fix:      | исправление бага                            | +PATCH            |
| docs:     | изменения только в документации             | нет               |
| refactor: | рефакторинг без изменения поведения         | нет               |
| test:     | тесты                                       | нет               |
| chore:    | обслуживание (deps, конфиги, мелкие правки) | нет               |
| ci:       | GitHub Actions / CI/CD                      | нет               |
| build:    | сборка/пакеты/докер/релиз-инструменты       | нет               |

MAJOR (ломающие изменения):

- feat!: ... или fix!: ...
- или футер в коммите: BREAKING CHANGE: ...

Примеры:

- `feat(core): add module contract v0`
- `feat(registry): add local module loading`
- `fix(settings): validate module config fail-fast`
- `docs(roadmap): update stage 3 module platform`
- `test(core): add artifact api smoke coverage`

MINOR: feat(api): добавить эндпоинт поиска

PATCH: fix(parser): не падать на пустом вводе

NO VERSION: docs: обновить README chore: добавить базовые шаблоны refactor(parser): упростить разбор без изменения поведения

MAJOR (breaking): feat!: сменить формат конфигурации

BREAKING CHANGE: ключи settings.yml переименованы; обновите конфиг
