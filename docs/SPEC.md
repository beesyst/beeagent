# SPEC — BeeAgent

## Purpose

BeeAgent is a stateful, modular agent host for bounded domain workflows. Its product contract is a single runtime that loads independent modules, executes authorized integrations, persists reviewable artifacts and exposes supported operator entrypoints. It does not embed customer-specific classification logic or create a second runtime for each module.

This file states supported product behavior and non-negotiable boundaries. See [ARCHITECTURE.md](ARCHITECTURE.md) for ownership, [SECURITY.md](SECURITY.md) for policy, [WEB_UI.md](WEB_UI.md) for Web APIs and [ROADMAP.md](ROADMAP.md) for delivery history.

## Core behavior

| Area          | Contract                                                                                                                  |
| ------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Runtime       | Dispatch known cases using validated module/runtime context, with explicit status and run identity                        |
| Modules       | Use declared packages and BeeSDK-compatible module contracts; disabled, missing or incompatible modules fail closed       |
| Configuration | `config/settings.yml` is authoritative; `.env` holds secrets; required enabled-path values are validated before execution |
| Capabilities  | Allowlisted operation, target, method, caller, provider and resource budget; execution authority is host-owned            |
| Approvals     | Validity and scope are rechecked at sensitive execution checkpoints; module/AI input never overrides policy               |
| Artifacts     | Host-managed, bounded, access-controlled files and status records under `storage/`; lifecycle and evidence are distinct   |
| Logs          | Central, understandable operational logs in `logs/app.log`; no secrets or unrestricted external payloads                  |
| Interfaces    | Existing CLI and Telegram flows, BeeUI-backed Web console and explicitly configured Bitrix integration surfaces           |
| Verification  | Recorded tests, artifact/log evidence and human review as required by risk and actual functionality                       |

## Module contract

A supported module supplies `module_id`, `supported_case_types()` and `handle(context)` as defined by BeeSDK. A module may interpret data, select proposals and produce reports. It must not implicitly gain network, filesystem, credential or mutation privileges from its package identity or returned status. BeeAgent owns capability invocation and artifact interfaces.

Installed module selection is explicit in the host configuration. Optional dependency profiles are resolved by the existing bootstrap. Running a module's local tests does not prove host installation or external-target authorization.

## Capability and authority model

Read-only analysis, approved read access and mutating actions have different risk boundaries. An action must be authorized for its actual principal, module, case, target, method and budget; the absence of one required condition is refusal, not an implicit default. Tools, models, attachments and external documents are never authority sources.

External execution requires bounded inputs and outputs, timeout/resource limits, current approval, credential isolation, destination checks and a trustworthy terminal lifecycle. Scanner alerts create candidates, not independently verified security findings. Business decisions do not grant permission to perform CRM mutations.

## Supported product flows

### ROP

BeeAgent hosts ROP mailbox ingestion, Bitrix reconciliation, run artifacts, review projections and bounded write-back. ROP classification, deduplication and domain recommendations remain owned by `beeagent-rop`.

Bitrix write-back uses a separate server-side execution policy and write credential. The read-only client does not mutate CRM data. Only explicitly supported and idempotency-checked methods are allowed: bounded `crm.item.add`, `crm.activity.add` and attachment-specific `crm.activity.update`. The host checks exact source evidence, responsible routing, existing CRM references, retry/idempotency state and attachment delivery completion. The persistent write-back ledger is `storage/interfaces/rop_writeback_state.json`; `rop_writeback_summary.json` is a per-run projection. Automation is not authorized merely because a classification is confident or `should_rop_see` is true.

Source-management and sender-blacklist actions in the Web console are protected, narrower administrative operations. They do not authorize `rop run`, arbitrary mailbox access or Bitrix write-back.

### BeeScan

BeeScan integrates through the existing `beescan` module extra and `./start.sh beescan` host command family. The host supports authorized HTTP assessment, restricted offline Nuclei detection, header signals, optional Git HEAD exposure, reviewed cases and supervised investigations. General investigation can discover candidate resources; the approved discovery-to-DAST mode can select one observed GET parameter and run the existing pinned ZAP rule-6 profile through mediated, budgeted HTTP execution.

The domain package remains offline. BeeAgent owns execution approval, operator identity, exact destination, DNS/TLS enforcement, process isolation, request accounting, artifact authenticity, Case checkpoint verification, resume and cleanup. An authorized target is still required; local OS identity does not prove consent from a third-party target owner. Neither DAST claims nor AI creates a `VERIFIED` vulnerability automatically.

See [BeeScan host operating guide](product/beescan_guide.md) for supported commands and [DAST preflight](product/beescan_guide.md#governed-dast-zap-rule-6) for the active scanner boundary.

### BeeDrill

BeeDrill is hosted through explicitly bounded isolated Solana/reference-target capabilities. BeeAgent owns preparation, environment identity, state observation, attack/containment execution where specifically approved, resource limits, cleanup and evidence; there is no generic Solana mutation authority for modules.

## Web and integration contract

The canonical UI is BeeUI-backed `src/beeagent_module/interfaces/ui/`, not the legacy `src/beeagent_module/web/` implementation. The Web adapter supplies dashboard, Runs, ROP, Modules and the owned BeeScan investigation workspace with bounded JSON/HTML projections. Sessions, roles and resource scopes are enforced server-side; visible navigation is not authorization. Auth-disabled development mode is not an acceptable default for public exposure.

The console is read-oriented except for explicitly implemented, protected ROP blacklist/source-management operations and independently approved BeeScan investigation start/resume. BeeScan Web execution has its own principal-bound host invocation and signed Case ownership; it cannot acquire trusted-local CLI authority. Sensitive attachment downloads use protected opaque identifiers and forced-download responses, not inline rendering. Bitrix Local Application launch authenticates a current user against one configured portal and creates a constrained session. The separate widget API uses Bearer authentication; a robot callback uses its independently constrained secret or application authentication. None of these routes permits arbitrary module execution.

The authoritative route, query, output, permission and redaction contracts are in [WEB_UI.md](WEB_UI.md).

## Configuration, secrets and artifacts

- `config/settings.yml` owns runtime configuration, feature enablement, module registry and bounded approvals. `config/beeui.yml` owns Web presentation/navigation configuration. Do not invent secondary configuration sources.
- Secrets are environment-backed, never committed or returned through HTTP, logs, report JSON, artifacts or AI prompts.
- Host artifacts include run-scoped records under `storage/runs/<run_id>/`, interface projections under `storage/interfaces/` and other explicitly owned storage. Persist only allowlisted metadata or protected evidence through the approved artifact interface.
- Every external side-effect or active assessment has a clearly attributable parent run, independent child steps, actual request counts and truthful terminal status. A report, hash or subprocess exit code without authenticated source and verified cleanup is not a successful execution.
- A report's fields and schema are defined by its owning module/host contract, not by this general specification.

## Entry points and limits

The supported entrypoint is `./start.sh`, dispatching via `config/start.py`. Known command families include `web`, `routes`, `rop`, `beescan`, `beedrill`, `auth` and `auth-init` (where configured). Exact flags and prerequisites belong in [DEV_GUIDE.md](DEV_GUIDE.md), not in this product contract.

BeeAgent does not provide unapproved remote code execution, arbitrary shell/HTTP actions, a public plugin marketplace, automatic Bug Bounty submissions, or general-purpose CRM mutation from an AI recommendation. New authority-bearing capabilities require an approved public contract and host-enforced controls.
