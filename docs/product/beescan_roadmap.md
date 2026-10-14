# BeeScan ROADMAP — BeeAgent Host Integration Track

## Purpose

Этот документ определяет отдельный roadmap интеграции BeeScan в BeeAgent: module loading, governed security capabilities, provider execution, authorization, isolation, runtime artifacts и operator workflows.

BeeScan roadmap нужен, чтобы:

- не перегружать `docs/ROADMAP.md` деталями конкретного security-продукта;
- сохранить независимую нумерацию BeeScan host iterations;
- координировать BeeAgent host work с BeeScan domain iterations;
- отделить security-domain semantics от execution authority;
- последовательно довести первый Web Bug Bounty assessment MVP до настоящего end-to-end запуска;
- развивать последующие security-интеграции без дублирования runtime и инфраструктуры.

Этот документ не заменяет:

- `docs/ROADMAP.md` — основной roadmap BeeAgent core;
- `docs/product/ui_roadmap.md` — общий BeeUI operator console track;
- `docs/SDLC.md` — процесс разработки, verification и delivery;
- `docs/SECURITY.md` — общие security requirements;
- `docs/DEV_GUIDE.md` — запуск, конфигурация и сопровождение;
- BeeScan `docs/ROADMAP.md` — roadmap security-domain функциональности;
- Issues и PR — точный scope и доказательства реализации.

**Главное правило:** отдельный roadmap не создаёт отдельный runtime, сервис, репозиторий или источник конфигурации.

## Roadmap ownership

| Roadmap                                    | Responsibility                                                            |
| ------------------------------------------ | ------------------------------------------------------------------------- |
| `beeagent/docs/ROADMAP.md`                 | Общая платформа, module system, runtime и shared infrastructure           |
| `beeagent/docs/product/ui_roadmap.md`      | Общий UI, API, authentication, BeeUI migration и operator console         |
| `beeagent/docs/product/beescan_roadmap.md` | BeeScan-specific host integration, governed execution и operator workflow |
| `beescan/docs/ROADMAP.md`                  | Scope, Mission, Observations, Findings, triage и reporting semantics      |
| `beesdk/docs/ROADMAP.md`                   | Только reusable public integration contracts                              |
| `beeui/docs/ROADMAP.md`                    | Только generic presentation components и UI framework                     |

BeeAgent остаётся единственным execution host.

BeeScan остаётся независимым доменным Python-пакетом.

Новые BeeSDK или BeeUI изменения допустимы только при доказанном контрактном блокере и через отдельно утверждённый Issue соответствующего репозитория.

## Why BeeScan track is separate

Основной BeeAgent ROADMAP содержит много завершённых этапов, включая module platform, ROP и BeeDrill. Последняя подтверждённая core iteration на момент создания этого плана — **Iteration 44.13 — Single-Project Isolated Security Test Execution and Onboarding**.

BeeScan потребует самостоятельной последовательности host capabilities и security verification.

Добавлять каждую BeeScan integration task как Iteration 45, 46, 47 и далее неудобно: это смешивает product-specific развитие с общим BeeAgent core.

Вместо этого используется отдельная последовательность:

```text
BS-1
BS-2
BS-3
...
```

Префикс `BS` означает BeeScan Host Track внутри BeeAgent.

Нумерация не пересекается с:

```text
BeeAgent It0–It44.13
BeeAgent UI-0, UI-1, ...
BeeScan It1–It6
```

Отдельная BS-итерация не обязана иметь тот же номер, что соответствующая BeeScan domain iteration.

## Vision

| Principle    | Product decision                                                  |
| ------------ | ----------------------------------------------------------------- |
| Product      | Authorized Web Bug Bounty assessment MVP first                    |
| Host         | BeeAgent owns all real execution                                  |
| Domain       | BeeScan owns security semantics                                   |
| Contracts    | Reuse BeeSDK public contracts                                     |
| Providers    | Only approved, version-pinned security tools                      |
| Authority    | Explicit operator approval and host-side enforcement              |
| Scope        | Exact authorized targets, methods and budgets                     |
| Network      | Independently enforced destination restrictions                   |
| Isolation    | Fail-closed process, filesystem and egress isolation              |
| Evidence     | Bounded, redacted, host-owned and traceable                       |
| Verification | Scanner output never automatically proves a vulnerability         |
| Interface    | Existing BeeAgent CLI first; BeeUI when justified                 |
| AI           | Optional after MVP, never security verdict or execution authority |
| Architecture | One runtime, no duplicated scanner framework                      |
| Delivery     | Real execution, inspected artifacts and independent verification  |

## Architecture direction

Canonical flow:

```text
Operator / CLI / authorized BeeUI action
                  |
                  v
             BeeAgent Host
                  |
       +----------+----------+
       |                     |
       v                     v
Authentication         Module Registry
Approval               BeeScanModule
Run Context            BeeSDK compatibility
       |                     |
       +----------+----------+
                  |
                  v
         BeeScan Public Domain
         Project / Target / Scope
         Mission / HTTP Intent
                  |
                  v
       BeeAgent Host Authorization
       Current approval / scope
       Provider and network policy
                  |
                  v
       Scoped CapabilityCaller
                  |
                  v
        Isolated Host Worker
                  |
          Pinned Provider
          httpx / Nuclei
                  |
                  v
       Host Output Validation
       Bounded facts / provenance
       Evidence artifact references
                  |
                  v
       BeeScan Domain Normalization
       Observations / Findings
       Triage / Reports
                  |
                  v
        BeeAgent Artifact Store
                  |
                  v
           Operator Review
```

The host must authorize execution independently from the domain's eligibility decision.

BeeScan may describe what is requested, but cannot grant permission to execute.

BeeAgent must not duplicate security-domain classification, findings or verification rules.

## Responsibility split

| Layer               | Responsibility                                                                |
| ------------------- | ----------------------------------------------------------------------------- |
| BeeScan             | Project, Target, EngagementScope, Mission, ScopeDecision                      |
| BeeScan             | Capability intent, HTTP fact validation, Observations                         |
| BeeScan             | Detector interpretation, Findings, deduplication and triage                   |
| BeeScan             | Domain reports and assessment semantics                                       |
| BeeSDK              | ModuleContext, ModuleResult, CapabilityCaller, CapabilityResult, ArtifactPort |
| BeeAgent            | Module registration, host runtime, CLI and run lifecycle                      |
| BeeAgent            | Authentication, approval, real execution authority                            |
| BeeAgent            | Provider installation policy, binary verification and invocation              |
| BeeAgent            | DNS, destination enforcement, egress, isolation and cleanup                   |
| BeeAgent            | Host provenance, storage, artifact access and audit                           |
| BeeAgent UI adapter | Product-specific read-models and bounded actions                              |
| BeeUI               | Generic presentation, navigation, components and rendering                    |

Canonical rules:

```text
BeeScan defines and interprets.
BeeAgent authorizes, executes and persists.
BeeSDK connects.
BeeUI renders.
```

## Source of truth

### Runtime configuration

```text
beeagent/config/settings.yml
```

BeeAgent settings own:

- module enablement;
- host execution policy;
- approved operator and engagement bindings;
- provider selection and verified executable identity;
- isolation and egress requirements;
- execution resource ceilings;
- host artifact retention and access policy.

Every new required enabled configuration value must be validated fail-fast.

Default behavior for a new security execution capability must be disabled or deny-by-default.

### BeeScan domain contracts

```text
beescan/src/beescan/domain/
beescan/src/beescan/capabilities/
beescan/src/beescan/module.py
```

BeeScan's `config/defaults.yml` is a sample configuration, not the BeeAgent runtime settings source.

Do not create a second active `config/settings.yml` inside BeeScan merely for naming symmetry.

### Runtime artifacts

BeeAgent owns canonical runtime storage:

```text
storage/runs/<run_id>/
storage/runs/<run_id>/module-beescan/
```

Exact filenames and artifact schemas are defined and tested by approved Issues.

No domain package may assume unrestricted access to BeeAgent private storage paths.

### UI

When BeeScan UI becomes necessary:

```text
BeeAgent interfaces/ui
    -> BeeUI
    -> authorized operator
```

The UI reads host-approved projections and may invoke only explicitly approved server-side actions.

HTTP GET/read-only routes never execute a scanner.

## Existing implementation baseline

The following baseline was verified through BeeMCP before creating this roadmap.

### BeeScan

**Iteration 1 — DONE**

- Installable BeeScan module.
- READ_ONLY `BeeScanModule`.
- `bootstrap_health`.
- Domain foundation and metadata-only tool catalog.

**Iteration 2 — DONE**

- Project, Target, EngagementScope, Mission and MissionSpec.
- Exact target canonicalization.
- `evaluate_scope()` with deterministic fail-closed results.
- Scope validity, exclusions and request/time budgets.

**Iteration 3 — DONE**

- `HttpProbeIntent`.
- `HostProvenance`.
- `HttpProbeOutcome`.
- `prepare_http_probe()`.
- `normalize_http_probe()`.
- Fixed `web.probe` / `http_probe` profile.
- Bounded evidence references and distinct SDK result statuses.

Current limitation: no real HTTP execution and no structured HTTP Observation extraction.

### BeeAgent

Existing infrastructure includes:

- installed Python module registry;
- `build_registry()` and `execute_module_case()`;
- host-generated run/session context;
- `ArtifactAPI` and host-owned run artifacts;
- BeeSDK-compatible module/capability interfaces;
- existing BeeDrill-scoped Solana capabilities;
- isolated LiteSVM test execution with Bubblewrap, resource limits and cleanup;
- canonical CLI entrypoint through `./start.sh`;
- existing BeeUI-backed web/operator architecture.

These are reusable foundations, not evidence that a safe Web scanner executor already exists.

The existing Solana capability factory is BeeDrill-specific.

The existing LiteSVM isolation profile uses no-network execution. It cannot be converted into a safe Web scanner merely by enabling unrestricted network access.

### Missing host capabilities

- BeeScan optional package registration and real host compatibility smoke.
- Approved BeeScan Web assessment invocation.
- Independently governed `web.probe` capability.
- Pinned ProjectDiscovery httpx execution.
- Strict DNS, connected-IP, redirect and egress enforcement.
- HTTP provider output validation and host-controlled facts handoff.
- Bounded evidence/observation artifacts.
- Restricted detection execution for Iteration 5.
- Minimal end-to-end operator workflow for Iteration 6.

## Development principles

Every BS iteration must:

- deliver a coherent product capability, not just DTOs or interfaces;
- reuse the existing BeeAgent runtime and public BeeSDK contracts;
- keep BeeScan security-domain logic in BeeScan;
- keep authority, execution and storage in BeeAgent;
- default to fail-closed behavior;
- use one pinned provider/profile before considering multiple providers;
- avoid dynamic commands, runtime installers and unsupported execution;
- preserve ROP, BeeDrill and existing BeeAgent behavior;
- use the existing runtime settings and artifact lifecycle;
- create no unbounded scanner output or secret-bearing artifacts;
- include positive and negative tests proportionate to risk;
- provide real lab execution evidence whenever the iteration introduces an executor;
- finish through approved Issue, branch, tests, artifacts, independent review and PR.

Do not split one functional integration into many contract-only iterations.

Do not combine unrelated scanners, interfaces or future product directions into one implementation Issue.

## Status values

- **PLANNED** — implementation has not started.
- **IN PROGRESS** — an approved Issue is under implementation or verification.
- **DONE** — all acceptance and delivery gates are completed.
- **DONE (partial)** — a defined subset is delivered, but an explicit acceptance or delivery gate remains open.
- **BLOCKED** — a required security, dependency or host prerequisite is not available.
- **DEFERRED** — not required for the first MVP.
- **RETIRED** — a previously planned item was replaced or is no longer justified; its ID is not reused.

A passing unit test does not demonstrate real host execution.

A successful subprocess exit code does not automatically establish successful HTTP assessment.

## Roadmap item format

New BS iterations contain:

- Goal
- Depends on
- Change level
- Scope
- Excluded
- Deliverable
- Acceptance criteria
- Checks
- DoD

The roadmap stays concise.

Exact schemas, CLI arguments, configuration keys, provider flags and exhaustive test matrices belong in approved Issues.

## Change levels

The BeeScan Host Track follows `docs/SDLC.md` and `docs/SECURITY.md`.

| Change level         | Examples                                                                                                                 |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `low-risk`           | Documentation, narrow tests and non-runtime cleanup                                                                      |
| `runtime-risk`       | Module integration, compatible read-models and bounded artifact rendering                                                |
| `security-sensitive` | Live scanner execution, authority, networking, isolation, evidence parsing, secrets, external providers and dependencies |

Every execution-capable BS iteration is security-sensitive unless a source review demonstrates otherwise.

Use relevant SAST, SCA, DAST, IAST and fuzz/property checks according to the actual changed threat surface.

Do not add instrumentation or tooling merely to satisfy a checklist.

## Global Definition of Done

A BS iteration is complete only when:

- its approved Issue and Acceptance Criteria are satisfied;
- changed contracts and runtime configuration are documented;
- actual host behavior matches the stated security boundary;
- all required positive and negative tests pass;
- applicable real lab smoke is reproduced;
- emitted artifact references resolve to real, authorized host evidence;
- logs and artifacts contain no secrets or unrestricted provider output;
- failures, refusals, timeouts and incomplete outcomes are not reported as success;
- existing module behavior remains compatible;
- independent source verification is complete;
- PR and CI delivery evidence is recorded;
- known limitations and follow-up requirements are explicit.

`pyproject.toml.version` is not changed as part of ordinary feature work.

## Product stages

| Stage                                   | Iteration    | Focus                                                                   | Status   |
| --------------------------------------- | ------------ | ----------------------------------------------------------------------- | -------- |
| Stage 1 — Governed HTTP Reconnaissance  | BS-1         | Module integration and real HTTP probe                                  | PLANNED  |
| Stage 2 — Restricted Security Detection | BS-2         | Governed Nuclei and candidate evidence                                  | PLANNED  |
| Stage 3 — Operator Assessment MVP       | BS-3         | One-invocation assessment, triage handoff and report artifacts          | PLANNED  |
| Post-MVP                                | Not numbered | UI expansion, monitoring, multi-target assessment and further providers | DEFERRED |

The first BeeScan assessment MVP must be demonstrated by completion of BS-1 through BS-3 together with the matching BeeScan domain iterations.

## Cross-repository dependency map

```text
BeeScan It1 — Foundation                   DONE
          |
BeeScan It2 — Authorized Scope             DONE
          |
BeeScan It3 — HTTP Contracts               DONE
          |
          +----------------------------+
          |                            |
          v                            v
BeeScan It4                       BeeAgent BS-1
HTTP Observations                 Governed HTTP Probe
          |                            |
          +--------------+-------------+
                         |
                         v
              REAL HTTP LAB EVIDENCE
                         |
          +--------------+-------------+
          |                            |
          v                            v
BeeScan It5                       BeeAgent BS-2
Detection & Triage                Restricted Detection
          |                            |
          +--------------+-------------+
                         |
                         v
              REVIEWABLE CANDIDATES
                         |
          +--------------+-------------+
          |                            |
          v                            v
BeeScan It6                       BeeAgent BS-3
Report & MVP                      Operator Assessment
          |                            |
          +--------------+-------------+
                         |
                         v
                   MVP GO / NO-GO
```

Matching iterations may be implemented concurrently after their public interfaces and repository ownership are approved.

A downstream iteration may not bypass an unfinished security gate in an upstream host capability.

---

## Stage 1 — Governed HTTP Reconnaissance

### Iteration BS-1 — BeeScan Module Integration and Governed HTTP Probe

**Status:** PLANNED

#### Goal

Deliver the first actual authorized HTTP security probe for BeeScan through the existing BeeAgent runtime, using one pinned ProjectDiscovery httpx provider and independently enforced host controls.

#### Depends on

- BeeScan Iterations 1–3 completed.
- BeeScan Iteration 4 public HTTP facts/Observation contract.
- Compatible BeeSDK and BeeScan package revisions.
- Verified host isolation and enforceable network-destination restrictions.

#### Change level

`security-sensitive`

#### Scope

- Register BeeScan as an optional installed module through the existing module registry.
- Verify actual `bootstrap_health` dispatch, SDK compatibility and host-owned artifact lifecycle.
- Introduce one fixed BeeScan-scoped `web.probe` capability.
- Reuse BeeScan's exact Mission/Target/Scope/HTTP intent contracts.
- Require an explicit host-approved operator, engagement, method and target.
- Independently enforce authorization at the execution boundary.
- Select one installed and verified ProjectDiscovery httpx executable and fixed provider profile.
- Restrict actual DNS/resolved destinations, redirects and outbound connections.
- Require isolation, clean environment, process/resource limits, request/time ceilings and cleanup.
- Parse and validate only bounded, allowlisted HTTP facts from provider output.
- Preserve the existing SDK success envelope containing only opaque evidence references.
- Pass host-validated HTTP facts to BeeScan through a bounded host-controlled integration path.
- Persist sanitized evidence, status, provenance and structured Observations in BeeAgent artifacts.
- Provide one reproducible authorized lab invocation through the existing BeeAgent entrypoint.

#### Excluded

- BeeScan-owned executor, standalone scanner runtime or database.
- Arbitrary tools, commands, provider flags, redirects, retries and target discovery.
- New generic sandbox or network orchestration platform.
- Nuclei, vulnerability Findings, AI and assessment reports.
- Web dashboard or a new HTTP service.
- Automatic installation or downloading of scanner binaries.

#### Deliverable

**One real authorized HTTP probe producing structured, evidence-backed BeeScan Observations through BeeAgent.**

#### Acceptance criteria

- BeeScan loads when enabled and preserves existing registry behavior when disabled.
- One approved lab HTTP(S) origin receives a real bounded request from the pinned provider.
- Operator approval, authorization validity, exact origin and budgets are independently enforced by BeeAgent.
- Actual connected IP addresses cannot escape the approved network policy.
- DNS rebinding, unsafe redirect targets and provider-induced additional destinations cannot bypass scope.
- Missing isolation or required enforcement refuses execution without host fallback.
- Malformed output, provider failure, timeout, exceeded budget and failed cleanup never become successful observations.
- Valid HTTP facts are linked to the correct Mission, Target, run, provider and bounded evidence references.
- Artifacts contain no raw bodies, unrestricted headers, cookies, credentials or unsafe paths.
- Existing ROP and BeeDrill host paths remain compatible.

#### Checks

- Module registry and real bootstrap compatibility tests.
- Host authorization and scope enforcement tests.
- Provider pin, configuration and environment checks.
- DNS rebinding, resolved-IP, redirect, proxy and egress negative tests.
- Resource, timeout, isolation and cleanup tests.
- Malformed and oversized provider output tests.
- Real approved laboratory HTTP probe and inspected host artifacts.
- Full relevant pytest, build, CI and security-sensitive independent review.

#### DoD

BS-1 is complete only when a real allowed HTTP target is safely probed through BeeAgent, valid BeeScan Observations are persisted and the network/isolation denial guarantees are demonstrably effective.

Mock-only results or successful DTO tests are insufficient.

---

## Stage 2 — Restricted Security Detection

### Iteration BS-2 — Governed Nuclei Detection and Evidence Handoff

**Status:** PLANNED

#### Goal

Enable one restricted vulnerability-detection execution through BeeAgent, consuming approved HTTP reconnaissance context and producing bounded evidence for BeeScan candidate Findings.

#### Depends on

- BeeAgent BS-1 completed and real HTTP reconnaissance verified.
- BeeScan Iteration 5 detection/triage contracts.
- Approved fixed Nuclei provider and template policy.

#### Change level

`security-sensitive`

#### Scope

- Introduce one fixed, allowlisted Nuclei detection profile.
- Verify installed executable identity and pinned template identities/versions.
- Execute only against the currently approved Mission/Target and permitted methods.
- Reuse BS-1 authorization, destination policy, isolation and artifact lifecycle.
- Enforce host-side template selection, request limits, timeouts and cleanup.
- Prevent arbitrary templates, out-of-scope requests and implicit follow-up execution.
- Parse only bounded, validated scanner matches and host provenance.
- Persist sanitized detection evidence with opaque artifact references.
- Preserve explicit success, refusal, timeout, error and incomplete execution outcomes.
- Provide bounded execution evidence for BeeScan candidate Finding and human-triage semantics.

#### Excluded

- Arbitrary community templates or runtime template downloads.
- Exploitation, destructive scans, brute force and autonomous verification.
- Automatic promotion of scanner matches to VERIFIED.
- Generic vulnerability scanners, adaptive planners or multi-tool orchestration.
- Bounty-platform submissions, AI verdicts and scoring engines.
- New service, database or standalone dashboard.

#### Deliverable

**One authorized HTTP Observation → governed restricted detection → evidence-backed candidate Finding path.**

#### Acceptance criteria

- Only the host-approved provider/profile/templates execute.
- Every detector request remains within the current approved destination policy and budgets.
- An actual controlled laboratory condition produces a bounded candidate detection.
- Scanner output never automatically becomes a verified vulnerability.
- Invalid output, unknown templates, changed targets and insufficient evidence cannot create valid candidates.
- Failed, refused, timed-out or incomplete detection remains distinct from successful negative detection.
- Evidence maintains Mission, Target, run, template and provider provenance.
- Existing HTTP and BeeDrill/ROP execution paths remain compatible.

#### Checks

- Provider/profile/template allowlist and integrity tests.
- Network, redirect, request-budget and isolation regression tests.
- Positive authorized laboratory detection scenario.
- Negative laboratory scenario with no candidate.
- Malformed, duplicate, unsupported and oversized scanner output tests.
- Timeout, cleanup, artifact integrity and redaction tests.
- BeeScan candidate/triage integration tests.
- Full pytest, build, CI, artifact inspection and security review.

#### DoD

One restricted detector runs against an approved lab target through BeeAgent and produces traceable evidence that BeeScan can interpret as a candidate Finding without claiming automatic verification.

---

## Stage 3 — Operator Assessment MVP

### Iteration BS-3 — Authorized Assessment Workflow and Report Delivery

**Status:** PLANNED

#### Goal

Provide one usable BeeAgent operator workflow that starts from an authorized Web target, executes the approved security-assessment capabilities and delivers a reviewable Markdown/JSON assessment package.

#### Depends on

- BeeAgent BS-1 and BS-2 completed.
- BeeScan Iteration 6 reporting and workflow contracts.
- Existing BeeAgent operator authority and artifact access mechanisms.

#### Change level

`security-sensitive`

#### Scope

- Expose one bounded assessment invocation through the existing BeeAgent CLI/operator infrastructure.
- Reuse authenticated operator identity and explicit engagement approval.
- Validate the approved Mission, target, providers and execution budgets before beginning.
- Coordinate the fixed supported sequence: scope validation, HTTP reconnaissance, restricted detection, triage and reporting.
- Preserve one consistent host-generated run identity and associated artifact references.
- Support an explicit human review/triage handoff with attributable reviewer decisions where required.
- Consume BeeScan domain report output without implementing a second reporting engine.
- Persist Markdown and JSON reports through BeeAgent-owned artifact interfaces.
- Make the complete run status, evidence, findings, refusals, errors and incomplete checks reviewable.
- Preserve safe read-only artifact access and avoid new UI infrastructure.
- Document the supported operator command, lab setup and recovery/failure behavior.

#### Excluded

- A separate BeeScan web service, frontend or database.
- Generic workflow graphs and unrestricted multi-scanner planning.
- Automated exploit generation, AI security verdicts and bounty submission.
- Scheduled scanning, multi-target campaigns and long-running monitoring.
- Public unauthenticated scanner APIs and automatic report publication.
- Extensive BeeUI dashboards and generic admin controls.

#### Deliverable

**One operator invocation → authorized governed assessment → reviewed evidence → bounded Markdown/JSON assessment package.**

#### Acceptance criteria

- An operator can reproduce the complete workflow from documented prerequisites.
- Authorization remains valid at every execution boundary.
- HTTP observations, detector results, candidate Findings, triage records and reports refer to the same approved Mission/run.
- VERIFIED, CANDIDATE, REJECTED, NO FINDINGS, REFUSED and INCOMPLETE states remain distinguishable as applicable.
- A scanner match cannot automatically create a VERIFIED finding.
- A missing, malformed or unauthorized evidence reference cannot establish a successful assessment.
- Markdown and JSON artifacts are bounded, reproducible and safely escaped/redacted.
- A clean/no-finding lab scenario is not mistaken for execution failure.
- Refused, timed-out or interrupted runs do not claim complete success.
- Existing BeeAgent ROP, BeeDrill, auth and module behavior remains compatible.
- A fresh reviewer can inspect the host artifacts and reproduce the assessment.

#### Checks

- Full host/domain contract integration tests.
- Approved positive detection-to-report laboratory smoke.
- Clean/no-finding laboratory smoke.
- Out-of-scope, expired approval, missing provider and timeout scenarios.
- Reviewer attribution and unsupported-verification negative tests.
- Report golden fixtures, evidence-link consistency and output escaping.
- Artifact access and redaction tests.
- Clean-checkout reproducibility and operator documentation check.
- Full pytest, build, CI, relevant security checks and independent final review.

#### DoD

**MVP GO** only when a fresh operator can complete the authorized assessment, review truthful evidence and obtain the final Markdown/JSON package through BeeAgent.

If any mandatory authority, network isolation, evidence, triage or artifact gate is missing, the result is **MVP NO-GO** with an explicit reason.

---

## Post-MVP product directions

These are candidate directions, not approved iterations.

Assign new BS numbers only after the first MVP and observed requirements justify the work.

### Operator Web and BeeUI

Potential capabilities:

- BeeScan run list and detail;
- Observations and Findings dashboards;
- evidence browser;
- candidate triage interface;
- bounded assessment launch with confirmation and audit;
- safe customer read-only access.

Ownership:

- BeeAgent: domain-aware adapter/read-model and authorized actions.
- BeeUI: generic components, layouts and rendering.
- BeeScan: security-domain semantics.

Coordinate this work with `docs/product/ui_roadmap.md`. Do not create parallel web frameworks or repeat shared UI tasks.

### Multiple approved targets

Potential capabilities:

- bounded multi-target Mission execution;
- separate scope evaluation and destination policy for every target;
- controlled concurrency and request budgets;
- partial run semantics;
- cross-target artifact correlation.

Do not infer authorization for discovered targets or other origins from an existing approved Target.

### Authorized assessment monitoring

Potential capabilities:

- scheduled assessments inside explicit authorization windows;
- provider/template revision tracking;
- evidence-based changes between runs;
- new/resolved candidate tracking;
- operator notifications.

Scheduler authority must never outlive the engagement approval.

### Additional providers

Potential capabilities:

- extended safe HTTP inspection;
- passive discovery;
- explicitly approved DNS capabilities;
- additional restricted vulnerability detection profiles;
- future Web3-specific execution.

Every new provider requires separate necessity, scope, isolation, egress and output-contract review.

Do not create a marketplace, generic plugin loader or autonomous tool selector merely to support one additional provider.

### AI assistance

Optional after deterministic MVP:

- safe report explanations;
- prioritization suggestions;
- deduplication hints;
- remediation drafts.

AI must not grant execution authority, introduce new network targets or declare a vulnerability verified.

## What not to do now

Do not:

- create a standalone BeeScan server or database;
- add a second security execution runtime;
- add a general-purpose scanner DAG;
- implement new providers before the fixed HTTP profile works;
- broaden target scope through DNS results or redirect following;
- treat tool metadata or user-supplied authorization text as host approval;
- enable unrestricted network access inside an existing sandbox;
- weaken BeeScan Iteration 3 result validation;
- add generic BeeSDK interfaces without a blocking use case;
- put BeeScan rules into BeeUI;
- add a separate React/frontend stack;
- begin Nuclei before real HTTP reconnaissance is verified;
- declare the MVP complete using mocks alone.

## Working rule for Issues

For the BeeScan Host Track:

```text
One BS iteration
    -> one coherent BeeAgent product increment
    -> one BeeAgent Issue
    -> one BeeAgent feature branch/worktree
    -> one BeeAgent PR
```

When BeeScan domain changes are necessary:

```text
BeeScan Issue + BeeScan PR
                 |
                 v
Compatible public BeeScan revision
                 |
                 v
BeeAgent BS Issue + BeeAgent PR
                 |
                 v
Cross-repository integration evidence
```

Each repository owns its own implementation and verification.

A BeeAgent Issue may depend on a BeeScan Issue but cannot authorize changes in the BeeScan repository.

Likewise, a BeeScan Issue cannot authorize runtime or network execution changes in BeeAgent.

For every cross-repository increment:

- define separate exact worktrees and branches;
- state the required public contract;
- identify compatible available package revisions;
- state implementation and merge order;
- preserve pre-existing dirty changes;
- execute the repository's approved planning and implementation workflows;
- complete independent verification;
- inspect real artifacts where execution is involved;
- avoid package-version changes during ordinary implementation;
- do not commit, push, merge or create PRs without user approval.

If a future task truly improves generic BeeAgent core, rather than BeeScan-specific integration, place it in the main BeeAgent roadmap and reference it as a prerequisite here.

If a task changes generic BeeUI behavior, place it in the appropriate UI/BeeUI roadmap instead of duplicating it here.

## Related documents

BeeAgent:

- `docs/ROADMAP.md`
- `docs/product/ui_roadmap.md`
- `docs/SDLC.md`
- `docs/SECURITY.md`
- `docs/DEV_GUIDE.md`
- `docs/WEB_UI.md`
- `README.ru.md`

BeeScan:

- `docs/ROADMAP.md`
- `docs/ARCHITECTURE.md`
- `docs/SPEC.md`
- `docs/DATA_MODEL.md`
- `docs/TOOLS.md`
- `docs/SECURITY.md`

BeeSDK:

- `docs/SPEC.md`
- `docs/ARCHITECTURE.md`

BeeUI:

- `docs/ROADMAP.md`
- `docs/INTEGRATION.md`
- `docs/API_CONTRACT.md`

**Roadmap rule:** BeeScan domain requirements belong to BeeScan. BeeScan-specific host execution belongs to this BeeAgent track. General runtime and UI infrastructure remain in their existing owning roadmaps.
