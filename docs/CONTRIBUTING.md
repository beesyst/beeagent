# CONTRIBUTING

Этот репозиторий использует Conventional Commits, чтобы release-please автоматически:
- повышал версию (SemVer)
- генерировал Release Notes / CHANGELOG
- создавал теги вида vX.Y.Z

Важно: версия повышается не на каждый коммит, а при выпуске релиза (через Release PR от release-please).


## Ветки

Правило: `main` — единственная стабильная/релизная ветка. Любые изменения делаем в отдельной ветке → PR → merge в `main` (желательно squash merge).


Именование веток (ветка = одна задача):
- feat/<short-title>        — новая функциональность
- fix/<short-title>         — багфикс
- chore/<short-title>       — обслуживание/инфра/настройки/доки

Если есть номер Issue, добавляй его:
- feat/12-config-schema
- fix/7-parser-crash

Примеры команд:
- создать ветку:  git checkout -b feat/config-schema
- отправить в origin: git push -u origin feat/config-schema

### Команды

| Шаг | Цель (что делаем)                                        | Команда(ы)                                     | Что ты увидишь / как понять                                                                                                      |
| --: | -------------------------------------------------------- | ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
|   0 | Проверить, что рабочая папка чистая и ты на нужной ветке | `git status`                                   | `On branch main` (или другая) + `working tree clean` = всё ок. Если есть “Changes not staged…” — есть незакоммиченные изменения. |
|   1 | Посмотреть локальные ветки и текущую ветку               | `git branch`                                   | Текущая ветка помечена `*` (например `* main`).                                                                                  |
|   2 | Создать новую ветку под задачу и переключиться на неё    | `git checkout -b docs/contributing`            | Git переключит тебя на новую ветку. Проверка: `git status` покажет `On branch docs/contributing`.                                |
|   3 | Добавить нужный файл(ы) в индекс (staging)               | `git add docs/CONTRIBUTING.md`                 | После этого в `git status` файл будет в `Changes to be committed`.                                                               |
|   4 | Создать коммит с правильным сообщением                   | `git commit -m "docs: add contributing guide"` | Git создаст коммит и покажет, сколько файлов изменено.                                                                           |
|   5 | Запушить ветку на GitHub и “привязать” upstream          | `git push -u origin docs/contributing`         | Ветка появится на GitHub. `-u` позволит дальше пушить просто `git push`.                                                         |
|   6 | Открыть PR на GitHub и влить в `main`                    | *(в браузере)* PR → **Squash and merge**       | После мержа изменения окажутся в `main`. Обычно ветку можно удалить кнопкой “Delete branch”.                                     |
|   7 | Обновить локальный `main` после мержа PR                 | `git checkout main` + `git pull`               | Локальный `main` подтянет изменения, которые ты влил через PR.                                                                   |
|   8 | Посмотреть удалённые ветки (origin)                      | `git branch -r`                                | Список веток на сервере, например `origin/main`, `origin/docs/contributing`.                                                     |
|   9 | Посмотреть все ветки (локальные + удалённые)             | `git branch -a`                                | Полный список: локальные + `remotes/origin/...`.                                                                                 |
|  10 | (Опционально) Удалить локальную ветку после мержа        | `git branch -d docs/contributing`              | Удалит ветку локально, если она уже смержена. Если не даёт — значит не смержена.                                                 |

Мини-цепочка на каждую задачу: status → checkout -b → add → commit → push → PR → checkout main → pull

## Процесс работы

### Tech Lead (мержит в main)

**Старт и создание новой ветки**
```
git checkout main
git pull --ff-only
git checkout -b feat/8-iteration-0-frame_and_launch
```
или переключиться на другую ветку:
```
git switch feat/44-it10-guardrails-v0
git fetch origin
git rebase origin/main
```

**Коммит + пуш**

```
git add .
git commit -m "feat: iteration 0 fame and launch"
git push -u origin feat/8-iteration-0-frame_and_launch
```

**PR и для проверок соразработчика**

1. Перейти в PR на GitHub, найти `feat/8-iteration-0-frame_and_launch` и нажать `Compare & pull request`.
2. В `Add a description` внести `Fixes #8` (номер закрывающего ишью) и нажать `Create pull request`.
3. `Squash and merge` → `Confirn squash and merge` в `main`.
4. `Delete branch`
3. После мержа обновить локальный `main`:
```
git checkout main
git pull --ff-only
```
4. Удалить локальную ветку:
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

### Соразработчик (делает PR)

**Перед началом задачи**

```
git checkout main
git pull --ff-only
git checkout -b feat/<short-title>
```

**Коммит + пуш + PR**

```
git add .
git commit -m "feat: <short>"
git push -u origin feat/<short-title>
```

**Если пока соразработчик работает, в main вмержили новые изменения**

```
git fetch origin
git rebase origin/main
git push --force-with-lease
```

**После мержа PR**

```
git checkout main
git pull --ff-only
```

## Issues и Kanban

Любая работа и любая идея оформляется как Issue (не как отдельная карточка в Project). Project (Kanban) показывает статус Issues.

Правило:
1) Создай Issue (таск = Issue).
2) Создай ветку под Issue.
3) Сделай PR в main.
4) В описании PR добавь строку, чтобы Issue закрылось автоматически:
   Fixes #123  (или Closes #123) или Refs #123

Лейблы:
- prio:high/medium/low
- (опционально) bug/enhancement/doc/idea

Используй:

* `Feature: <short title>` — новая функциональность
* `Fix: <short title>` — исправление бага
* `Bug: <short title>` — баг-репорт (ещё не факт что фиксишь прямо сейчас)
* `Docs: <short title>` — документация
* `Chore: <short title>` — обслуживание/инфра/рефактор без фич
* `Idea: <short title>` — идея/набросок (потом можно превратить в Feature/Fix)

**Примеры:**

* `Feature: add risk profiles (conservative/normal/aggressive)`
* `Fix: prevent crash on empty candles`
* `Bug: wrong PnL calculation on partial fills`
* `Docs: explain config keys and examples`
* `Chore: add pre-commit formatting`
* `Idea: capital allocation per strategy`


## Коммиты

Формат:
<type>(<scope>)!: <кратко что сделано>

scope — опционально (например: api, parser, docs, ci).
! — признак ломающего изменения (MAJOR).

Таблица типов (KISS):

| Тип        | Когда использовать                         | Влияние на версию |
|-----------|--------------------------------------------|-------------------|
| feat:     | новая функциональность                      | +MINOR            |
| fix:      | исправление бага                            | +PATCH            |
| docs:     | изменения только в документации             | нет               |
| refactor: | рефакторинг без изменения поведения         | нет               |
| test:     | тесты                                       | нет               |
| chore:    | обслуживание (deps, конфиги, мелкие правки) | нет               |
| ci:       | GitHub Actions / CI/CD                      | нет               |
| build:    | сборка/пакеты/докер/релиз-инструменты       | нет               |

MAJOR (ломающие изменения):
- feat!: ...  или fix!: ...
- или футер в коммите: BREAKING CHANGE: ...

Примеры:

MINOR:
feat(api): добавить эндпоинт поиска

PATCH:
fix(parser): не падать на пустом вводе

NO VERSION:
docs: обновить README
chore: добавить базовые шаблоны
refactor(parser): упростить разбор без изменения поведения

MAJOR (breaking):
feat!: сменить формат конфигурации

BREAKING CHANGE: ключи settings.yml переименованы; обновите конфиг