# DEV_GUIDE — BeeAgent

## Purpose

Use this guide to install, run and verify BeeAgent and its supported modules. It documents current developer and operator commands, not the history of implementation. [SDLC.md](SDLC.md) defines delivery rules, [SECURITY.md](SECURITY.md) defines security policy, [ARCHITECTURE.md](ARCHITECTURE.md) defines component ownership and [WEB_UI.md](WEB_UI.md) defines Web contracts.

## Environment and dependencies

- Python 3.14 or newer and `uv`.
- Linux prerequisites for actual isolated security/tool execution are capability-specific; ordinary unit tests and Web/ROP development do not need all native security providers.
- `pyproject.toml` defines package requirements and optional extras; `uv.lock` pins resolved dependencies. Do not hardcode package versions, Git revisions or dependency source paths in development instructions.
- `config/settings.yml` controls enabled modules, execution approvals and runtime behavior. `.env` provides credentials. Never store actual secrets in YAML or documentation.

The settings loader accepts only a regular, singly linked configuration file owned by root or the authorized service/configuration owner, without group/world write permission or symlink components. Its parent directories must also be root/owner controlled and not group/world writable; a system sticky temporary-directory ancestor is permitted. Use owner-only writes and grant a non-root service only the read access it needs, for example mode `0640` for a root-owned file with the service's read group. Web roles, including application admin, do not grant OS configuration ownership. Configuration protection is checked before YAML is read; unsafe paths fail closed.

From the BeeAgent repository root:

```bash
uv sync --frozen
uv run --frozen pytest -q
./start.sh
```

`./start.sh` uses the host bootstrap, validates settings, prepares the selected runtime profiles and dispatches the requested command. For coordinated module regressions, select the relevant extras explicitly:

```bash
uv run --frozen --extra beescan --extra beedrill pytest -q -rs
```

A developer may use approved local editable dependencies during coordinated work. A release or production build must use the reviewed distribution/pinned source required by its integration policy. A sibling checkout or a successful local import does not prove production dependency provenance. Do not run a blanket `uv add --editable` that rewrites managed dependency declarations without an approved task. Update `uv.lock` only when a dependency change is authorized and needed.

## CLI quick reference

| Task                                    | Command                                                                                                           |
| --------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Start the Web console                   | `./start.sh web`                                                                                                  |
| Web console without opening a browser   | `./start.sh web --host 127.0.0.1 --port 8780 --no-open`                                                           |
| Inspect registered routes               | `./start.sh routes`                                                                                               |
| Poll new mailbox messages               | `./start.sh rop poll`                                                                                             |
| Process a manual ROP sample             | `./start.sh rop run --items-max 5`                                                                                |
| Build ROP write-back plan               | `./start.sh rop writeback plan --run-id <run_id>`                                                                 |
| Preview ROP write-back without mutation | `./start.sh rop writeback execute --run-id <run_id> --dry-run`                                                    |
| Run BeeDrill regression suite           | `./start.sh beedrill check`                                                                                       |
| Start BeeScan operator CLI              | `./start.sh beescan`                                                                                              |
| Start governed BeeScan investigation    | `./start.sh beescan investigate --target https://authorized.example --task 'Investigate the approved Web target'` |
| Inspect BeeScan Case                    | `./start.sh beescan investigate --inspect <case_id>`                                                              |
| Resume BeeScan Case                     | `./start.sh beescan investigate --resume <case_id> --task 'Continue the authorized investigation'`                |
| Rotate one Web principal credential     | `./start.sh auth rotate <principal-id-or-username>`                                                               |
| Invalidate all Web sessions             | `./start.sh auth rotate session`                                                                                  |

Commands that read a target, send network traffic, modify CRM or operate a security provider require their independent current approvals and configured prerequisites. The placeholder URL does not authorize scanning.

## Configuration and module lifecycle

1. Configure the intended module under `modules.registry` in `config/settings.yml`. Use its declared `install_extra` when present.
2. Configure that module's separate feature enablement, provider identity and execution policy. BeeScan Web may derive bounded per-run approval from its configured target policy; legacy CLI/task-file approvals remain separate. Disabled modules must not execute external actions.
3. Supply secrets only through environment references. Use existing bootstrap/rotation helpers where supported.
4. Run the intended command and inspect actual terminal status, logs and allowlisted artifacts.

Core dependencies exclude optional domain modules unless their profile is selected. A normal host bootstrap synchronizes required extras for enabled modules using frozen resolution. Changes to installed module ownership or public contracts require paired tests against the actual BeeAgent dispatch path.

## ROP mailbox processing

The source registry starts from `config/rop/sources.yml`. After a protected Sources UI mutation, the authoritative runtime registry is `storage/config/rop/sources.yml`. `config/settings.yml` owns `rop.sources_path` and `rop.mailbox_poll` selection. Each mailbox source declares a read-only connection, source ID, folder and `username_env`/`password_env`; actual credentials remain in environment or protected `.env`.

```bash
./start.sh rop poll
./start.sh rop poll --source-id hotline_mailbox
./start.sh rop poll --all-sources
./start.sh rop poll --rebaseline --source-id hotline_mailbox
./start.sh rop run --source-id hotline_mailbox --items-max 5
./start.sh rop run --all-sources
```

- `poll` is the only-new-message path. It uses per-source `UIDVALIDITY`/last-UID checkpoints in `storage/interfaces/rop_mailbox_checkpoint.json`; the first poll establishes a baseline rather than importing history. One source failure does not roll back successful checkpoints for others.
- `run` is a manual sample/backfill path. It does not consume or advance polling checkpoints. `items_max` applies per source for that invocation.
- `--rebaseline` is an explicit recovery operation, not routine polling. Production scheduling belongs to a separate approved systemd timer, not an in-process infinite poll loop.
- When write-back is enabled, the pipeline persists its canonical execution intent _before_ advancing the source checkpoint, then executes only the pending records belonging to that invocation. A run without new mail never replays unrelated historical records automatically.

The Sources Web view may add/edit/delete/enable/check sources only for a principal with the required ROP management authority; mailbox Check performs connect/login/read-only folder selection and records its last result, not a durable connection. Credential editing is a separate narrow management permission. Passwords are never echoed into YAML, CSV, JSON or logs.

## ROP Bitrix write-back

`bitrix.writeback` in `config/settings.yml` controls the separately authorized mutation path. Its `enabled: false` state and `--dry-run` are zero-write controls. An enabled path requires the dedicated credential, correct customer stages and the explicit responsible-routing evidence; missing or contradictory evidence defers rather than inventing a CRM target.

```bash
./start.sh rop writeback plan --run-id <run_id>
./start.sh rop writeback execute --run-id <run_id> --dry-run
./start.sh rop writeback execute --run-id <run_id>
./start.sh rop writeback execute --run-id <run_id> --existing-only
```

`plan` creates the durable plan without CRM mutation. `execute` performs only independently permitted pending work and persists idempotency state after each meaningful step. `--existing-only` is a recovery path for exact BeeAgent-owned existing leads, not permission to create missing leads. `--retry-failed` must be used deliberately, respecting terminal failures and configured retry ceilings.

For write-back failures inspect `storage/interfaces/rop_writeback_state.json`, the affected run's `rop_writeback_summary.json`, recipient-routing evidence and safe logs. Do not edit state to fabricate completion. Domain classification and ROP recommendations never grant CRM mutation authority; exact existing-target attachment requires validated thread provenance. Physical attachment delivery must complete according to its own protected lifecycle.

## Shared AI profile selection

The single profile catalog lives in `config/settings.yml` under `ai.profiles`, with `ai.default_profile` selecting the default. Per-module `ai_profile` can select an existing named profile for ROP, BeeDrill and BeeScan without altering unrelated module behavior.

```yaml
ai:
  default_profile: openrouter
rop:
  ai_assist:
    ai_profile: openrouter
beedrill:
  ai_assist:
    ai_profile: openai
beescan:
  investigation:
    ai_profile: openrouter
```

This example selects configured profile names; it does not create credentials, approve providers or enable module execution. `core/ai_profiles.py` resolves a module selection to the global default, or to the supported legacy single-enabled selection when no default exists. Do not combine `ai.default_profile` with legacy `enabled` selectors; mixed and unknown selections fail validation. Provider credentials use environment references. BeeScan has stricter HTTPS/credential-reference requirements. A selected profile or available model never grants an HTTP/scanner/CRM action.

ROP adjudication and legacy assist consume the shared catalog while retaining their separate enablement and deterministic fallback semantics. BeeDrill AI assist operates only on allowlisted explanation facts after the actual regression verdict is persisted; it cannot change that verdict. BeeScan AI may interpret a task but cannot override authorization, choose arbitrary request payloads or establish a verified finding.

## BeeDrill

```bash
./start.sh beedrill check
./start.sh beedrill run --scenario reference_target_containment_replay
./start.sh beedrill run --scenario reference_oracle_manipulation_replay
./start.sh beedrill run --scenario spl_token_freeze_containment_replay
./start.sh beedrill diff --baseline /absolute/path/a --candidate /absolute/path/b
```

The regression suite uses the approved isolated reference-target execution path. Exit status distinguishes a completed PASS, completed FAIL, invalid command and infrastructure/incomplete conditions; it must not be inferred from arbitrary stdout. `diff` is a bounded isolated test-regression comparison, not a security proof. Its native dependencies and sandbox prerequisites are checked by the current host runtime; there is no fallback to unrestricted shell/project scripts or public-network execution.

## BeeScan

BeeScan runs through the BeeAgent host, not through a standalone scanner service. Supported local host commands include `bootstrap`, `probe`, `detect`, `assess`, `review` and `investigate` as enabled and approved by the corresponding configuration. The interactive/direct `investigate` flow requires trusted local operator mode; legacy task-file invocation has independent authorization controls. A separate active DAST approval is required even when a GET parameter was discovered successfully.

The authoritative procedures, provider integrity requirements, controlled laboratory commands, Case/Resume behavior and status interpretation are in [BeeScan host operating guide](product/beescan_guide.md), with the restricted ZAP implementation documented in [DAST preflight](product/beescan_guide.md#governed-dast-zap-rule-6).

## Web console and Bitrix Local Application

```bash
./start.sh web
./start.sh routes
./start.sh auth rotate session
```

The canonical Web layer is `interfaces/ui` with BeeUI. It uses `config/settings.yml` for host/auth policy and `config/beeui.yml` for navigation/presentation. For public deployment, enable Web auth and serve only behind correctly configured HTTPS. Route/resource scopes and protected actions are documented in [WEB_UI.md](WEB_UI.md).

To embed the ROP console in Bitrix24, configure the exact `bitrix.embedded_app.portal_origin`, enable `web.auth` and the embedded app, expose trusted HTTPS to `POST /bitrix/rop/install` and `POST /bitrix/rop/launch`, and register a server-side Local Application with UI and the Bitrix `user` permission. BeeAgent validates `member_id`, token expiry and current user against the configured portal before creating the bounded session. Embedded `admin` is not supported. Never put OAuth credentials in query strings, logs or documentation.

## Verification and diagnostics

From the selected worktree, apply tests proportional to the change:

```bash
uv run --frozen pytest -q
./start.sh routes
git diff --check
```

When relevant, inspect `logs/app.log`, the affected `storage/runs/<run_id>/` artifacts and `storage/interfaces/` durable state. Require consistent run IDs, complete/evidence markers, resource ceilings, lifecycle cleanup and non-sensitive content. Real network/kernel tests live under `integration_tests/` and require their separately approved prerequisites. Do not claim such tests passed just because the regular pytest suite completed.

Do not run long production dashboard/history rebuilds merely to validate unrelated code. Never change settings, approvals, secrets, mailbox checkpoints or write-back state as an automatic test repair.
