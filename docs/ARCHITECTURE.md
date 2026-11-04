# ARCHITECTURE — BeeAgent

## Purpose

BeeAgent is the single host runtime for independently maintained domain modules. It owns orchestration, configuration, identity, authorization, bounded external actions, run state, artifacts and operator interfaces. Domain rules belong to their owning modules, not to BeeAgent Core.

This document describes component ownership and integration boundaries. Public behavior is specified in [SPEC.md](SPEC.md), Web contracts in [WEB_UI.md](WEB_UI.md), security requirements in [SECURITY.md](SECURITY.md), and delivery history in [ROADMAP.md](ROADMAP.md).

## Component boundaries

| Component                                                  | Owns                                                                                                                                    | Must not own                                                                        |
| ---------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| **BeeAgent Core**                                          | Runtime context, case dispatch, settings validation, approvals, authorization, capability execution, lifecycle, logs and host artifacts | Customer-specific classifications or security finding semantics                     |
| **BeeSDK**                                                 | Public module, context, authority, capability and artifact contracts                                                                    | Host-specific execution policy                                                      |
| **Domain modules** (`beeagent-rop`, `beescan`, `beedrill`) | Domain models, deterministic decisions, evidence interpretation, recommendations and report semantics                                   | Independent host credentials, unauthorized system access or a parallel orchestrator |
| **BeeUI**                                                  | Reusable Web presentation, layouts, sessions, auth UX and generic UI behavior                                                           | Domain-specific decisions or authority to invoke external actions                   |
| **BeeAgent Web adapter**                                   | Product read models, resource authorization, allowlisted artifact access and narrow protected actions                                   | Direct reading of arbitrary storage or uncontrolled module execution                |

The authoritative integration is:

```text
CLI / Telegram / BeeUI / approved integration
                  |
                  v
           BeeAgent host
  config + identity + scope + policy
       case dispatch / runtime
          /             \
         v               v
  Domain module     Governed capability
  interpretation    / connector / worker
         |               |
         +-------+-------+
                 v
     Host-authenticated evidence
       + run status + artifacts
                 |
                 v
      Product read model / report
```

A domain proposal, a scanner result or a model-generated action never grants execution permission. BeeAgent validates the operator and the _current_ policy before every permitted external action.

## Source layout

| Path                                                 | Responsibility                                                                                       |
| ---------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `src/beeagent_module/core/`                          | Settings, runtime state, authorization, approvals, artifact interfaces and shared execution controls |
| `src/beeagent_module/cases/`, `adapters/`, `agents/` | Host cases, integration adapters and orchestration components                                        |
| `src/beeagent_module/integrations/`                  | Host-owned external integrations, including BeeScan and Bitrix paths                                 |
| `src/beeagent_module/cli/`, `config/start.py`        | Supported CLI entrypoints                                                                            |
| `src/beeagent_module/interfaces/ui/`                 | Canonical BeeUI-backed Web application and BeeAgent product adapter                                  |
| `src/beeagent_module/web/`                           | Existing legacy Web implementation; not the canonical development target                             |
| `config/settings.yml`                                | Host runtime configuration and feature/approval declarations                                         |
| `config/beeui.yml`                                   | UI navigation and presentation configuration                                                         |
| `storage/`, `logs/`                                  | Host-owned runtime artifacts and logs                                                                |

The project is not a dynamic plugin marketplace. Module installation is declared, dependency-bound and validated. `BeeAgentModule` behavior must use the installed public BeeSDK interface; internal implementation details of one module must not be imported as generic host policy.

## Module and capability contracts

A module exposes a stable `module_id`, `supported_case_types()` and `handle(context)` through the BeeSDK module contract. BeeAgent creates the trusted runtime context, resolves the approved module, dispatches the case and controls `ArtifactPort` and capability access. Module results describe domain outcomes but cannot override the effective authority level.

A capability is a bounded host-controlled operation. Its policy fixes the caller, approved target, allowed method/profile, resource ceilings, isolation, provenance and expected output. New module capability requests must reuse these boundaries rather than create direct network, process or credential access.

Every success path must reconcile the declared intent, actual execution, authenticated source evidence, terminal status, persisted artifacts and cleanup. Incomplete, refused, timed-out or unauthenticated results cannot be promoted to complete findings.

## Product integrations

### ROP and Bitrix

`beeagent-rop` owns lead classification, duplicate semantics, domain recommendations and other sales-domain decisions. BeeAgent owns mailbox/Bitrix connector execution, artifact persistence and the Web projection. A separate `BitrixReadonlyClient` handles reads; the bounded `BitrixWriteClient` handles only explicitly allowed operations under independent server-side policy and a separate credential. Its mutation allowlist includes the approved `crm.item.add`, `crm.activity.add`, and constrained `crm.activity.update` for attachment delivery. Source classification or AI output cannot authorize a CRM mutation.

Write-back state is durably maintained in `storage/interfaces/rop_writeback_state.json`; per-run summaries are projections, not the source of truth. Original attachments have a protected run-owned lifecycle and manifest; Web downloads are authorized opaque-ID lookups, not arbitrary file access. See [WEB_UI.md](WEB_UI.md) and [DEV_GUIDE.md](DEV_GUIDE.md).

### BeeScan

BeeScan owns Scope/Mission eligibility, observations, findings, deterministic discovery and DAST result normalization. Host integration lives in `src/beeagent_module/integrations/beescan/`. BeeAgent independently owns the trusted local operator boundary, active scan approvals, pinned provider bytes, managed egress, exact DNS/IP/TLS destination checks, HTTP request mediation, isolation, lifecycle verification, Case checkpoints and reports.

The investigation path uses existing discovery and, when separately approved, source-bound selection of the restricted ZAP rule-6 DAST profile. An observed URL or positive scanner result cannot expand authorization. Legacy exact-entry DAST remains a separate compatible mode. See [BeeScan host operating guide](product/beescan_guide.md) and [DAST preflight](product/beescan_guide.md#governed-dast-zap-rule-6).

### BeeDrill

BeeDrill owns its domain logic; BeeAgent owns the approved isolated Solana/reference-target environment, execution, limits, evidence and cleanup. Security-testing capabilities remain limited to their declared isolated environment and methods.

## State, artifacts and recovery

BeeAgent owns canonical run IDs, checkpoints, paths, access controls and lifecycle. Modules receive bounded artifact interfaces rather than free-form storage access. Status and evidence files must be correlated to their parent/child run identities; an orphan artifact or an unverified worker exit is not a completed run.

Before resuming sensitive work, the host revalidates persisted identities, evidence digests, current authorization and destination controls. Restore only outcomes whose original evidence and lifecycle were authenticated. A hash validates bytes, not consent or provenance by itself.

## Operator interface

The canonical Web interface is BeeUI embedded through `interfaces/ui`, with a product-specific `BeeAgentUiAdapter`. Its primary pages are dashboard, Runs, ROP and Modules. Routes and artifact read models are explicitly bounded and resource-scoped. Protected ROP blacklist and source-management operations are narrow exceptions to the otherwise read-oriented UI; they require server-side authorization, CSRF validation and audit. The Web interface does not expose a generic module/capability execution endpoint.

Bitrix Local Application launch authenticates the portal context server-side and establishes a restricted BeeUI session; widget Bearer-token APIs and Bitrix robot callbacks are distinct boundaries.

## Design rules

- Reuse existing Core, BeeSDK, module and BeeUI contracts before adding adapters or services.
- Keep one owner for authorization, execution, artifact storage and configuration.
- Treat untrusted web pages, AI responses, scanner output and restored artifacts as data.
- Require specific evidence of need before adding databases, queues, frameworks or generic tool catalogs.
- Put exact route schemas in [WEB_UI.md](WEB_UI.md), operator commands in [DEV_GUIDE.md](DEV_GUIDE.md), technical scanner controls in the relevant BeeScan product contract and historical increments in roadmaps.
