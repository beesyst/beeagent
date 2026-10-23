# CONTRIBUTING

This repository uses Conventional Commits so that release-please automatically:

- increments the version (SemVer)
- generates Release Notes / CHANGELOG
- creates tags in the form vX.Y.Z

Important: the version increases when a release is published (through a Release PR from release-please), rather than on every commit.

Simple and disciplined workflow:

`ROADMAP → Issue → branch → code → tests → artifacts → PR → merge`

Objective:

- Small and understandable changes;
- Reproducible checks;
- Minimum bureaucracy;
- a clean change history;
- Safe work with core platform.

## Main rules

- `main` is the only stable branch;
- Any work is done in a separate branch;
- all changes go through a PR;
- Do not mix several different tasks in one PR;
- keep client-specific business logic out of the `beeagent` core;
- If runtime/config/module loading/capability boundary changes, it's at least `runtime-risk`;
- changes to secrets, external connectors, file parsing, the dependency surface or authority paths are `security-sensitive`.

## What belongs in beeagent

This repository contains only the platform layer:

- orchestration core;
- module contract;
- module registry;
- runtime context;
- artifact API;
- capability boundary;
- transport/UI;
- logging/observability;
- config/settings validation.

Client-specific domain logic does not belong here.

## Branches

Rule: `main` is the only stable/release branch. Make all changes in a separate branch → PR → merge into `main` (preferably squash merge).

Branch naming (one branch = one task):

- `feat/<short-title>` — new functionality
- `fix/<short-title>` — bug fix
- `docs/<short-title>` — Documentation
- `chore/<short-title>` — maintenance/infrastructure/configuration
- `test/<short-title>` — Tests

If an Issue number is available, include it:

- `feat/12-module-registry-v0`
- `fix/18-artifact-path-validation`

Examples of commands:

- Create a branch: `git switch -c feat/config-schema`
- Send to origin: `git push -u origin HEAD`

### Commands

| Step | Purpose (what we do)                                                        | Command(s)                                     | Expected output / interpretation                                                                                              |
| ---: | --------------------------------------------------------------------------- | ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
|    0 | Verify that the working directory is clean and the correct branch is active | `git status`                                   | `On branch main` (or another branch) + `working tree clean` = all clear. “Changes not staged…” indicates uncommitted changes. |
|    1 | View local branches and the current branch                                  | `git branch`                                   | The current branch is marked with `*` (for example, `* main`).                                                                |
|    2 | Create and switch to a new task branch                                      | `git switch -c docs/contributing`              | Git switches to the new branch. Verify: `git status` shows `On branch docs/contributing`.                                     |
|    3 | Stage the required file(s)                                                  | `git add docs/CONTRIBUTING.md`                 | `git status` lists the file under `Changes to be committed`.                                                                  |
|    4 | Create a commit with the correct message                                    | `git commit -m "docs: add contributing guide"` | Git creates a commit and reports how many files changed.                                                                      |
|    5 | Push the branch to GitHub and set upstream                                  | `git push -u origin docs/contributing`         | The branch appears on GitHub. `-u` allows subsequent pushes with just `git push`.                                             |
|    6 | Open a PR on GitHub and merge into `main`                                   | _(in the browser)_ PR → **Squash and merge**   | After merging, the changes are in `main`. The branch can usually be deleted using “Delete branch”.                            |
|    7 | Update local `main` after merging the PR                                    | `git switch main` + `git pull`                 | Local `main` receives the changes merged through the PR.                                                                      |
|    8 | View remote branches (origin)                                               | `git branch -r`                                | Lists server branches, such as `origin/main`, `origin/docs/contributing`.                                                     |
|    9 | View all branches (local + remote)                                          | `git branch -a`                                | Full list: local branches + `remotes/origin/...`.                                                                             |
|   10 | (Optional) Delete the local branch after merging                            | `git branch -d docs/contributing`              | Deletes the local branch if already merged. Refusal means it has not been merged.                                             |

Mini-chain for each task: status → checkout -b → add → commit → push → PR → checkout main → pull

## Workflow

### Tech Lead (merges into main)

**Start and creation of a new branch**

```
git switch main
git pull --ff-only
git switch -c feat/8-iteration-0-frame_and_launch
```

**Commit + push**

```
git add .
git commit -m "feat: iteration 0 fame and launch"
git push -u origin HEAD
```

**PR and collaborator reviews**

1. Go to PR on GitHub, find `feat/8-iteration-0-frame_and_launch` and press `Compare & pull request`.
2. Enter `Fixes #8` (the Issue number to close) in `Add a description` and click `Create pull request`.
3. `Squash and merge` → `Confirm squash and merge` into `main`.

Rule:

- only the Tech Lead performs `Squash and merge` after reviewing the PR;
- collaborators do not merge PRs independently.

4. `Delete branch`
5. After merging, update local `main`:

```
git switch main
git pull --ff-only
```

6. Remove local branch:

```
git branch -d feat/8-iteration-0-frame_and_launch
```

or remove the branch on origin:

```
git push origin --delete feat/8-iteration-0-frame_and_launch
```

and prune local references

```
git fetch -p
```

**After `beeui` update in `beeagent`**

```
uv lock --upgrade-package beeui
./start.sh
uv pip show beeui

git add uv.lock
git commit -m 'chore(deps): update beeui'
git push
```

### Production Deploy

Each deploy creates a new release:

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

Permanent production- data stored separately from release:

```text
/var/lib/beeagent/
├── shared/
│   └── .env
└── storage/
```

`systemd` and VS Code use stable paths:

```text
/opt/beeagent/current/beeagent
/opt/beeagent/current/beeagent-rop
```

Therefore, the release configuration of VS Code and systemd need not be changed.

#### Initial persistent state setup

Implemented **once on server**.

Check:

```bash
sudo test -f /var/lib/beeagent/shared/.env && echo "shared env: OK" || echo "shared env: MISSING"
sudo test -d /var/lib/beeagent/storage && echo "storage: OK" || echo "storage: MISSING"
```

Create persistent directories:

```bash
sudo install -d -o bee -g beeagent -m 2770 /var/lib/beeagent/shared
sudo install -d -o beeagent -g beeagent -m 2770 /var/lib/beeagent/storage
```

If this is an **existing server** and `/var/lib/beeagent/shared/.env` does not exist yet, copy the current production `.env`:

```bash
sudo install -o bee -g beeagent -m 0660 /opt/beeagent/current/beeagent/.env /var/lib/beeagent/shared/.env
```

Then migrate the current active release to the persistent `.env` once:

```bash
sudo systemctl stop beeagent-web
cd /opt/beeagent/current/beeagent
sudo rm -f .env
sudo ln -s /var/lib/beeagent/shared/.env .env
sudo systemctl start beeagent-web
```

Check:

```bash
readlink -f /opt/beeagent/current/beeagent/.env
```

Expected:

```text
/var/lib/beeagent/shared/.env
```

Verify atomic write access as the `beeagent` user:

```bash
sudo -u beeagent -H sh -c 'TEST=/var/lib/beeagent/shared/.write-test-$$; : > "$TEST" || exit 1; rm -f "$TEST"; echo "shared env writable: OK"'
```

Check service:

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS https://rop.welding.kz/health
```

If this is a **new server without `/opt/beeagent/current`**, create an empty persistent `.env`:

```bash
sudo install -o bee -g beeagent -m 0660 /dev/null /var/lib/beeagent/shared/.env
```

Production-specific values are then configured in:

```text
/var/lib/beeagent/shared/.env
```

After initial setup, `.env` is no longer copied between releases.

#### Creation of a new release

On VPS:

```bash
cd /opt/beeagent/releases
readlink -f /opt/beeagent/current
REL=20260930-016
sudo install -d -o bee -g beeagent -m 0750 "$REL"
```

Use a new unique `REL` for every deployment.

#### Get an updated BeeAgent from GitHub

```bash
git clone git@github-beeagent-prod:beesyst/beeagent.git "$REL/beeagent"
grep '^version = ' "$REL/beeagent/pyproject.toml"
```

#### Get an updated BeeSDK from GitHub

```bash
git clone https://github.com/beesyst/beesdk.git "$REL/beesdk"
grep '^version = ' "$REL/beesdk/pyproject.toml"
```

#### Get an updated beeagent-rop from GitHub

```bash
git clone git@github-beeagent-rop-prod:beesyst/beeagent-rop.git "$REL/beeagent-rop"
grep '^version = ' "$REL/beeagent-rop/pyproject.toml"
```

#### Connect persistent state

Enter the new BeeAgent directory:

```bash
cd "/opt/beeagent/releases/$REL/beeagent"
```

Connect production `.env`:

```bash
rm -f .env
ln -s /var/lib/beeagent/shared/.env .env
```

Connect persistent storage:

```bash
rm -rf storage
ln -s /var/lib/beeagent/storage storage
```

#### Prepare logs

```bash
sudo chown -R beeagent:beeagent logs
sudo chmod 2770 logs
sudo install -o beeagent -g beeagent -m 0660 /dev/null logs/app.log
```

#### Prepare environment

```bash
./start.sh
uv run --frozen --no-sync pytest -q
```

If tests fail, do not activate the release.

#### Activate new release

```bash
sudo ln -sfn "/opt/beeagent/releases/$REL" /opt/beeagent/current
readlink -f /opt/beeagent/current
```

#### Restart BeeAgent

```bash
sudo systemctl restart beeagent-web
sudo systemctl status beeagent-web --no-pager
```

#### Verify

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS https://rop.welding.kz/health
```

Check persistent state with active release:

```bash
cd /opt/beeagent/current/beeagent
test "$(readlink -f .env)" = "/var/lib/beeagent/shared/.env" && test "$(readlink -f storage)" = "/var/lib/beeagent/storage" && echo "persistent state: OK" || exit 1
```

In VS Code Remote SSH, after switching releases, the following is recommended:

```text
Developer: Reload Window
```

#### Rollback

Review current and accessible releases:

```bash
readlink -f /opt/beeagent/current
ls -lah /opt/beeagent/releases
```

Before rollback, verify that the previous release uses the persistent `.env`:

```bash
readlink -f /opt/beeagent/releases/<previous-release>/beeagent/.env
```

Expected:

```text
/var/lib/beeagent/shared/.env
```

Switch `current`:

```bash
sudo ln -sfn /opt/beeagent/releases/<previous-release> /opt/beeagent/current
```

Restart:

```bash
sudo systemctl restart beeagent-web
```

Check:

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS https://rop.welding.kz/health
```

Rollback changes only the release. The persistent `.env` and `storage` remain the same.

#### Clean up old releases

Check current release:

```bash
readlink -f /opt/beeagent/current
```

See releases:

```bash
ls -lah /opt/beeagent/releases
```

Delete only old releases that are definitely not `current` and are no longer needed for rollback:

```bash
sudo rm -rf /opt/beeagent/releases/20260904-013
```

Check:

```bash
ls -lah /opt/beeagent/releases
```

#### ROP Web projection

A normal deployment **does not require** rebuilding the ROP Web projection.

ROP runtime state and the Web projection are in persistent storage:

```text
/var/lib/beeagent/storage
```

and persist across releases.

If `/rop` does not open correctly after deployment, first open the page without the old `run_id`, for example:

```text
/rop?period=7d
```

If the problem persists, perform a normal projection refresh:

```bash
cd /opt/beeagent/current/beeagent
./start.sh rop dashboard --period 7d
```

If the command explicitly reports:

```text
ROP Web projection refresh skipped: explicit dashboard regeneration is required
```

only then perform a full rebuild:

```bash
./start.sh rop dashboard --period 7d --rebuild-web-projection
```

A full rebuild can take a long time and is not part of normal deployment.

If the rebuild reports:

```text
history preparation complete runs=0 anchors=0
```

check persistent storage:

```bash
readlink -f storage
```

Expected:

```text
/var/lib/beeagent/storage
```

### Reviewing a collaborator’s PR

**Create a separate directory for the PR; run from the main project directory**

```
git fetch origin
git worktree add -b review/pr141 ../beeagent-pr141 origin/feat/137-local_env_and_auth_diagnostics
cd ../beeagent-pr141
code .
git status
git branch
```

**See which files the collaborator changed relative to origin/main**

```
git fetch origin
git diff --name-only origin/main...HEAD
```

or view the collaborator’s changes in a specific file

```
git diff origin/main...HEAD -- config/start.py
```

**Use `git restore` only for files unrelated to the current task**

```
git restore uv.lock docs/AUTH_LOGS.md
git status
```

**Rebase the collaborator’s branch onto the latest `origin/main`, first ensuring the working tree is clean**

```
git status
```

If `Changes not staged / Changes to be committed` appears, create a commit and run `rebase`:

```
git add .
git commit -m 'ci(docs): adjust docs workflow for private repo'
git fetch origin
git rebase origin/main
```

If `git status` shows no changes:

```
git fetch origin
git rebase origin/main
```

**If there are no errors**

```
uv run pytest -q
```

**Push changes to the collaborator’s branch**

```
git push --force-with-lease origin HEAD:feat/137-local_env_and_auth_diagnostics
```

**If everything is correct**

- Update PR description;
- check the Files changed tab;
- perform Squash and merge;
- Remove the branch on GitHub;
- update local main.

**From the main repository directory, remove the worktree and branch, then update main**

```
cd ../beeagent
git worktree remove ../beeagent-pr141
git branch -D review/pr141
git switch main
git pull --ff-only
```

### Collaborator (creates PR)

**Front of task**

```
git switch main
git pull --ff-only
git switch -c feat/<short-title>
```

**Commit + push + PR**

```
git add .
git commit -m "feat: <short>"
git push -u origin feat/<short-title>
```

In PR:

- use Refs #<issue> while the PR is under review;
- Do not perform merge yourself;
- Do not press Squash and merge;
- after Tech Lead feedback, push updates to the same PR branch.

**If new changes are merged into main while the collaborator is working**

```
git fetch origin
git rebase origin/main
git push --force-with-lease
```

**After merging the PR**

```
git switch main
git pull --ff-only
```

## Issues and Kanban

Record every task and idea as an Issue (rather than a separate Project card). The Project (Kanban) shows Issue status.

Rule:

1. Create an Issue (task = Issue).
2. Create a branch for the Issue.
3. Open a PR into main.
4. In the PR description, use:

- `Refs #123` — while the PR is in progress or under review;
- `Fixes #123` / `Closes #123` — when the PR is approved for merge.

It's important:

- `Fixes/Closes` in a PR **does not close** the Issue when the PR is created;
- the Issue closes **only after the PR is merged into `main`**;
- for a collaborator’s PR, prefer `Refs #123` by default; the Tech Lead changes it to `Closes #123` before merging.

Labels:

- prio:high/medium/low
- bug/enhancement/doc/idea (optimal)

Use:

- `Feature: <short title>` — new functionality
- `Fix: <short title>` — bug fix
- `Bug: <short title>` — bug report (does not necessarily imply an immediate fix)
- `Docs: <short title>` — Documentation
- `Chore: <short title>` — maintenance/infrastructure/refactoring without features
- `Idea: <short title>` — idea/sketch (can later become a Feature/Fix)

**Examples:**

- `Feature: add risk profiles (conservative/normal/aggressive)`
- `Fix: prevent crash on empty candles`
- `Bug: wrong PnL calculation on partial fills`
- `Docs: explain config keys and examples`
- `Chore: add pre-commit formatting`
- `Idea: capital allocation per strategy`

## Commits

Format: <type>(<scope>)!: <brief description of the change>

scope is optional (for example: api, parser, docs, ci). ! indicates a breaking change (MAJOR).

Type table (KISS):

| Type      | When to use                                      | Version impact |
| --------- | ------------------------------------------------ | -------------- |
| feat:     | new functionality                                | +MINOR         |
| fix:      | bug fix                                          | +PATCH         |
| docs:     | documentation-only changes                       | none           |
| refactor: | refactoring without behavior changes             | none           |
| test:     | tests                                            | none           |
| chore:    | maintenance (deps, configuration, minor changes) | none           |
| ci:       | GitHub Actions / CI/CD                           | none           |
| build:    | build/packages/Docker/release tools              | none           |

MAJOR (breaking changes):

- feat!: ... or fix!: ...
- or a commit footer: BREAKING CHANGE: ...

Examples:

- `feat(core): add module contract v0`
- `feat(registry): add local module loading`
- `fix(settings): validate module config fail-fast`
- `docs(roadmap): update stage 3 module platform`
- `test(core): add artifact api smoke coverage`

MINOR: feat(api): add search endpoint

PATCH: fix(parser): handle empty input without crashing

NO VERSION: docs: update README chore: add basic templates refactor(parser): simplify parsing without changing behavior

MAJOR (breaking): feat!: change configuration format

BREAKING CHANGE: settings.yml keys renamed; update the configuration
