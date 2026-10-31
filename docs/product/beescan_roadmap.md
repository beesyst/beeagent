# BeeScan ROADMAP — BeeAgent Host Integration Track

## Purpose

This document defines a separate roadmap for integrating BeeScan into BeeAgent: module loading, governed security capabilities, provider execution, authorization, isolation, runtime artifacts and operator workflows.

The BeeScan roadmap is needed to:

- avoid overloading `docs/ROADMAP.md` with security product details;
- preserve independent numbering for BeeScan host iterations;
- coordinate BeeAgent host work with BeeScan domain iterations;
- separate security-domain semantics from execution authority;
- bring the first Web Bug Bounty assessment MVP to a clear end-to-end launch sequence;
- develop subsequent security integrations without duplicating runtime and infrastructure.

This document does not replace:

- `docs/ROADMAP.md` — the main BeeAgent core roadmap;
- `docs/product/ui_roadmap.md` — the shared BeeUI operator console track;
- `docs/SDLC.md` — development, verification and delivery processes;
- `docs/SECURITY.md` — general security requirements;
- `docs/DEV_GUIDE.md` — running, configuration and maintenance;
- BeeScan `docs/ROADMAP.md` — the security-domain functionality roadmap;
- Issues and PRs — exact scope and implementation evidence.

**Main rule:** a separate roadmap creates no separate runtime, service, repository or configuration source.

## Roadmap ownership

| Roadmap                                    | Responsibility                                                              |
| ------------------------------------------ | --------------------------------------------------------------------------- |
| `beeagent/docs/ROADMAP.md`                 | Common platform, module system, runtime and shared infrastructure           |
| `beeagent/docs/product/ui_roadmap.md`      | Shared UI, API, authentication, BeeUI migration and operator console        |
| `beeagent/docs/product/beescan_roadmap.md` | BeeScan-specific host integration, governed execution and operator workflow |
| `beescan/docs/ROADMAP.md`                  | Scope, Mission, Observations, Findings, triage and reporting semantics      |
| `beesdk/docs/ROADMAP.md`                   | Only reusable public integration contracts                                  |
| `beeui/docs/ROADMAP.md`                    | Only generic presentation components and UI framework                       |

BeeAgent remains the only execution host.

BeeScan remains an independent domain Python package.

New BeeSDK or BeeUI changes are permitted only for a demonstrated contract blocker through a separately approved Issue in the corresponding repository.

## Why BeeScan track is separate

The main BeeAgent ROADMAP contains many completed phases, including the module platform, ROP and BeeDrill. The last confirmed core iteration when this document was created was **Iteration 44.13 — Single-Project Isolated Security Test Execution and Onboarding**.

BeeScan will require an independent sequence of host capabilities and security verification.

Adding every BeeScan integration task as Iteration 45, 46, 47 and so on is unwieldy: it mixes product-specific development with shared BeeAgent core work.

Instead, a separate sequence is used:

```text
BS-1
BS-2
BS-3
...
```

The `BS` prefix means the BeeScan Host Track inside BeeAgent.

Numbering does not overlap with:

```text
BeeAgent It0–It44.13
BeeAgent UI-0, UI-1, ...
BeeScan It1–It6
```

A separate BS iteration does not have to share the number of its BeeScan domain iteration.

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

The target adaptive-investigation flow remains one BeeAgent orchestrator, not a second runtime. BeeScan determines investigation intent; BeeAgent selects an authorized execution path; deterministic tools take priority for known checks; and AI assists with hypotheses, selection and adaptation without granting itself authority. Results return to the decision loop with persisted runs, evidence, checkpoints and metrics. An operator can continue an existing Investigation Case, while a future BeeUI can show state, progress, findings, evidence and recommended next actions. Standard steps may run automatically within approved scope and budget without a separate confirmation for every HTTP request.

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

| Stage                                   | Iteration    | Focus                                                                   | Status      |
| --------------------------------------- | ------------ | ----------------------------------------------------------------------- | ----------- |
| Stage 1 — Governed HTTP Reconnaissance  | BS-1         | Module integration and real HTTP probe                                  | DONE        |
| Stage 2 — Restricted Security Detection | BS-2         | Governed Nuclei and candidate evidence                                  | IN PROGRESS |
| Stage 3 — Operator Assessment MVP       | BS-3         | One-invocation assessment, triage handoff and report artifacts          | IN PROGRESS |
| Post-MVP                                | Not numbered | UI expansion, monitoring, multi-target assessment and further providers | DEFERRED    |

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

**Status:** DONE

#### Goal

Integrate BeeScan as an optional BeeAgent module and execute one real, explicitly authorized HTTP probe through a pinned ProjectDiscovery httpx provider with independently enforced host authority, destination and isolation controls.

#### Depends on

- Completed BeeScan Iterations 1–3.
- Approved BeeScan Iteration 4 HTTP facts/Observation contract.
- Compatible BeeScan/BeeSDK dependency revisions.
- Verified process isolation and actual network egress enforcement.

#### Change level

`security-sensitive`

#### Scope

- Register BeeScan as an optional module without changing ROP or BeeDrill defaults.
- Verify actual `bootstrap_health` execution and BeeAgent-owned module artifacts.
- Introduce one fixed BeeScan-scoped `web.probe` execution path and a minimal authorized lab CLI invocation.
- Independently validate operator authority, current engagement approval, exact Mission/Target/Scope, method and request/time budgets.
- Use one installed, version- and identity-verified ProjectDiscovery httpx executable with host-owned fixed arguments.
- Enforce exact HTTP(S) origin, resolved destinations, no automatic redirect following and deny-by-default network egress.
- Require a verified isolated worker, minimal environment, controlled credentials, resource limits and cleanup.
- Parse provider output in BeeAgent and expose only bounded validated HTTP facts to BeeScan's public domain normalization API.
- Preserve the Iteration 3 evidence-only `CapabilityResult.data` success envelope.
- Persist bounded host evidence, execution status, provenance and normalized BeeScan Observations.
- Add `.github/workflows/ci.yml` using the BeeScan workflow as a structural reference, adapted to BeeAgent's actual uv dependency profiles and regression tests.
- Provide a reproducible real authorized lab run, negative safety scenarios and ROP/BeeDrill compatibility evidence.

#### Excluded

- Modifying BeeDrill's existing isolated Solana execution semantics.
- Adding a second scanner runtime, generic executor framework, database or HTTP service.
- Arbitrary commands, user-selected provider flags, unrestricted redirects, discovery, crawling or retries.
- Weakening host authorization, running unrestricted network subprocesses or using fallback execution without isolation.
- Nuclei, vulnerability Findings, report generation, UI, AI and scheduled scanning.
- Generic BeeSDK or BeeUI changes without a demonstrated blocker.

#### Deliverable

**One existing BeeAgent runtime → optional BeeScan module → safely governed real `web.probe` execution → host-owned evidence → structured BeeScan Observations, with BeeAgent CI protecting the integration.**

#### Acceptance criteria

- Optional BeeScan registration and bootstrap work in a compatible clean installation.
- Existing disabled/enabled ROP and BeeDrill module behavior remains compatible.
- One explicitly approved lab origin receives a real bounded HTTP request.
- Operator identity and approval are independently established by BeeAgent, not inferred from a caller-controlled authorization reference.
- Current scope and expiry are rechecked before execution.
- Actual outbound connections cannot escape the approved destination policy; DNS changes, forbidden addresses, redirects and proxy settings cannot bypass enforcement.
- Missing provider integrity, network enforcement, isolation or required resources produces a refusal without unrestricted fallback.
- Fixed request/time budgets remain enforced by the host.
- Only allowlisted validated HTTP facts and bounded evidence refs enter BeeScan normalization.
- Malformed output, timeout, incomplete execution, invalid evidence and cleanup failure never produce false-success artifacts.
- ROP and BeeDrill existing capabilities, CLI commands, outcomes and security isolation remain compatible.
- BeeAgent GitHub CI runs on pull requests and main pushes, has least-privilege permissions, uses Python 3.14 and validates meaningful tests/build from a clean checkout.
- The CI workflow does not silently depend on the developer's local `../beeagent-rop` checkout or unavailable secrets.
- A real positive lab probe, negative enforcement tests and inspected artifacts demonstrate the complete increment.

#### Checks

- Module registry, dependency compatibility, SDK contract and bootstrap tests.
- Host approval, scope, expiry, method and budget tests.
- Provider identity, command/profile allowlist and environment tests.
- DNS rebinding, forbidden destination, redirect, proxy and actual egress negative tests.
- Worker isolation, missing enforcement, timeouts, cleanup and resource exhaustion tests.
- Provider malformed/oversized output, evidence integrity and redaction tests.
- Real approved laboratory HTTP execution and persisted Observation inspection.
- Existing BeeDrill capability/check/diff and ROP runtime regression tests.
- Clean-checkout CI, relevant pytest, build, security checks and independent source review.

#### DoD

BS-1 is complete only when the authorized laboratory HTTP probe actually executes through BeeAgent with enforceable network and isolation controls, BeeScan produces reviewable Observations, BeeAgent CI succeeds and existing ROP/BeeDrill behavior is verified. Mock-only success, unsafe fallback, false-success artifacts or a failing clean-checkout CI are blockers.

---

## Stage 2 — Restricted Security Detection

### Iteration BS-2 — Governed Nuclei Detection and Evidence Handoff

**Status:** DONE

Host integration and local It5 laboratory verification are implemented; the merged reviewed BeeScan revision, production pin update, hosted CI and independent review remain delivery gates. Operating instructions belong in [the host guide](beescan_guide.md).

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

**Status:** DONE

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
- Preserve one logical parent assessment identity and independently generated immutable probe/detection child-run identities with traceable artifact references.
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
- HTTP observations, detector results, candidate Findings, triage records and reports refer to the same approved Mission and logical assessment, while preserving their independent child-run provenance.
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

## Stage 4 — Governed Web Security Signals

### Iteration BS-4 — Governed HTTP Header Signal Capture and Assessment Delivery

**Status:** DONE

#### Goal

Extend the existing BeeScan assessment workflow to securely obtain the minimal HTTP header facts required by BeeScan It7 and deliver useful advisory security signals without granting additional network or scanner authority.

#### Scope

- Reuse the existing independently approved HTTP probe and restricted detection workflow.
- Reuse the existing single governed GET response capture; introduce no additional target request.
- Extract only bounded, allowlisted security header facts for `X-Content-Type-Options` and HTTPS `Strict-Transport-Security`.
- Normalize captured metadata before it enters BeeScan domain contracts or host artifacts.
- Preserve exact Mission, Target, origin, approval, source Observation, detection run and evidence bindings.
- Invoke BeeScan It7's public offline signal evaluation and reporting contracts.
- Persist versioned or compatible signal-enabled Markdown/JSON reports through existing ArtifactAPI.
- Preserve fixed provider, template, sandbox, namespace, egress, timeout and cleanup enforcement.
- Preserve legacy bootstrap, probe, detect and marker-only assessment behavior.
- Document authorization, operator invocation, supported signals and recovery procedures.

#### Excluded

- Additional HEAD/GET requests, crawling, arbitrary destinations or authorization expansion.
- New executable providers, scanner profiles, Nuclei templates or runtime downloads.
- Raw HTTP headers, response bodies, cookies, secrets or unrestricted scanner output in artifacts.
- Arbitrary security rules, new configuration sources, generic workflow frameworks or services.
- BeeSDK, BeeUI, database, scheduling, interactive review or automatic VERIFIED changes.

#### Deliverable

One authorized `./start.sh beescan assess` invocation that performs the existing two-request workflow, evaluates the two predefined security signals using the reviewed BeeScan It7 contract, and persists safe, reviewable assessment artifacts.

#### Acceptance criteria

- Existing independent probe and detection approvals remain mandatory and unmodified.
- A completed assessment makes at most one approved HEAD and one approved GET, with no redirects or retries.
- Only two explicitly allowlisted header fact families can cross the capture boundary.
- Capture never stores or exposes unrestricted header values, cookie material or response bodies.
- Missing, duplicate, conflicting, malformed or oversized relevant metadata is handled deterministically and fail closed.
- HTTPS-specific HSTS assessment requires validated HTTPS context; HTTP is not misclassified.
- Host-generated signal facts are bound to the fresh Observation, original child runs and validated evidence.
- Signal and marker results remain distinct and reports never imply automatic vulnerability verification.
- Missing signal evidence, partial persistence, failed provider, revoked authority or changed source cannot produce complete success.
- Existing standalone commands, fixed Nuclei template and provider integrity checks remain compatible.
- Real positive, negative, non-applicable, refusal and failure laboratories pass.
- BeeAgent full regressions, clean frozen dependency installation and hosted CI pass.

#### Checks

- Capture parser, allowlist, bounds, duplicate-header and malformed-response tests.
- Real HTTP and HTTPS laboratory scenarios with documented TLS trust requirements.
- Existing BS-1/BS-2/BS-3 request accounting, provider, firewall, sandbox and approval regressions.
- Source mutation, terminal persistence, timeout, cleanup and secret-leakage tests.
- Exact report bytes, original child provenance and artifact permission inspection.
- ROP and BeeDrill regression coverage.
- Relevant SAST, dependency SCA if the BeeScan Git revision changes, build and fresh-checkout checks.
- Independent security review and hosted CI.

#### DoD

A fresh authorized operator can reproduce meaningful HTTP security signal results through the existing governed BeeAgent assessment, with truthful bounded reports, unchanged execution authority and verified positive, negative and failure handling.

## Stage 5 — Governed Web Exposure Detection

### Iteration BS-5 — Governed Public Git Metadata Exposure Assessment

**Status:** DONE

#### Goal

Extend the existing BeeScan operator assessment with one explicitly authorized, tightly bounded Git metadata exposure check and deliver its validated results through the BeeScan It8 public domain contracts.

#### Depends on

- BeeAgent BS-1 through BS-4 completed and their security boundaries preserved.
- BeeScan Iteration 8 public exposure detection and reporting contracts.
- Existing BeeAgent authentication, scope enforcement, host artifact lifecycle and provider-integrity mechanisms.
- Availability of every required reviewed executable for real end-to-end laboratory verification.

#### Change level

`security-sensitive`

#### Scope

- Add one optional, explicitly authorized exposure check for the fixed path `/.git/HEAD` on the already approved HTTP(S) origin.
- Require host-controlled selection and authorization for the additional request; existing probe and detection approvals must not silently grant broader path or request authority.
- Enforce the exact HTTP method, path, destination, connected IP, scheme, port, TLS verification, request budget and execution deadline.
- Reuse the existing host-owned isolation, namespace, nftables, resource-limit, cleanup and artifact mechanisms.
- Perform no redirects, retries, proxy requests, path discovery or additional network connections.
- Read only a strictly bounded response sufficient to classify Git HEAD exposure evidence.
- Discard raw response content after validation and preserve only minimal, allowlisted facts and host-controlled evidence references.
- Bind the check to the authorized Mission, Target, parent assessment, source Observation, provider identity and individual execution status.
- Invoke BeeScan It8's offline validation, Finding candidate and report contracts.
- Preserve the current probe, marker detection, HTTP security signals and human review behavior.
- Document operator configuration, explicit approval, real laboratory execution and recovery/failure semantics.

#### Excluded

- Generic HTTP request execution, user-selected paths, crawling or directory enumeration.
- Retrieving `.git/config`, Git objects, `.env`, secrets or arbitrary response bodies.
- Cloning repositories, reconstructing source code, active exploitation or automated credential extraction.
- Arbitrary Nuclei templates, new scanner marketplaces or autonomous tool selection.
- Broadening current network destinations, bypassing TLS, firewall, namespaces or provider integrity checks.
- Automatic VERIFIED Findings, additional target authorization or autonomous follow-up requests.
- New standalone BeeScan runtime, database, UI, scheduler or general workflow framework.

#### Deliverable

One opt-in, authorized BeeAgent assessment that performs the existing governed checks plus a single fixed Git metadata exposure check, passes bounded evidence to BeeScan It8 and persists a truthful Markdown/JSON assessment package with traceable Finding candidates.

#### Acceptance criteria

- The new check is disabled without explicit host-side authorization and cannot inherit execution authority merely from an existing assessment.
- An enabled authorized check performs at most one additional fixed-path HTTP(S) request, accounted for in the overall approved budgets.
- No request can escape the approved origin, destination, method, path, validity window or resource ceilings.
- Redirects, DNS changes, forbidden ports, proxy settings and TLS failures cannot bypass enforcement.
- Host capture accepts only bounded, validated evidence and never retains arbitrary Git file content in public artifacts.
- Positive evidence matches the exact target, source run, request identity and approved Git metadata check.
- An HTML fallback, HTTP status alone, malformed response or incomplete capture cannot create a false-positive Finding.
- Missing provider, revoked authorization, timeout, invalid provenance or persistence failure cannot produce a falsely complete assessment.
- BeeScan owns the final exposure interpretation and CANDIDATE Finding semantics; the host does not duplicate domain rules.
- Existing HEAD probe, restricted Nuclei detection, header signals, reports and review contracts remain compatible.
- An authorized real HTTP and HTTPS laboratory demonstrates positive, negative, refusal and failure outcomes.
- BeeAgent full regressions, frozen dependency installation, applicable security checks and hosted CI pass.

#### Checks

- Exact method/path, request-count, authorization, expiry and budget tests.
- DNS, SNI, TLS, redirect, proxy, destination and nftables isolation tests.
- Bounded response parsing, malformed content, truncation, HTML fallback and redaction tests.
- Source provenance, child-run identity, evidence linking and incomplete-status tests.
- Real local HTTP/HTTPS positive and negative laboratories using explicitly approved test targets.
- Existing BS-1 through BS-4 workflow, provider, sandbox and report regressions.
- BeeScan It8 contract integration and deterministic report verification.
- ROP, BeeDrill, module registry and authentication compatibility tests.
- Security-sensitive SAST, applicable dependency checks, full pytest, fresh-checkout smoke, independent review and hosted CI.

#### DoD

A fresh, explicitly authorized operator can run the opt-in Git metadata exposure assessment through BeeAgent, obtain a bounded, traceable BeeScan Finding candidate when positive evidence exists, and inspect truthful negative, refused or incomplete outcomes. The additional request is independently authorized, strictly limited and verified under the existing isolation and destination controls. No scanner match is represented as an automatically verified vulnerability.

---

## Stage 6 — Governed Human Review and Case Delivery

### Iteration BS-6 — Governed Finding Review and Bug Bounty Case Package Delivery

**Status:** DONE

The coordinated It9/BS-6 CLI, source reconstruction, evidence intake and protected delivery are implemented for local verification with a temporary editable BeeScan dependency. Final immutable revision, fresh frozen integration, independent verification/review and hosted CI remain pending; this status does not declare production delivery.

#### Goal

Complete the BeeScan operator assessment workflow by securely accepting attributable human Finding reviews, validating independent host evidence and delivering deterministic reviewed-case and manual bug bounty submission artifacts through the existing BeeAgent CLI and ArtifactAPI.

#### Depends on

- Completed BeeAgent BS-1 through BS-5 assessment and security boundaries.
- Reviewed BeeScan Iteration 9 case-package contracts available through a reproducible immutable Git revision.
- Existing BeeAgent authentication, storage, artifact read-back and provenance validation mechanisms.

#### Change level

`security-sensitive`

#### Scope

- Add a separate explicit CLI workflow to review Findings from an existing completed BeeScan assessment without repeating network assessment requests.
- Resolve the selected assessment and candidate through host-owned persisted artifacts rather than caller-supplied Finding objects or untrusted report text.
- Reconstruct and validate the necessary typed source records, original run identities, child provenance, completion states and evidence references.
- Authenticate the actual reviewer through a trusted host-controlled operator context and record attributable review identity and decision time.
- Accept bounded manual review decisions and independent verification evidence through an explicit, validated operator input contract.
- Verify that independent evidence exists in authorized host-controlled storage, is readable, bounded and belongs to the selected assessment/reviewer workflow.
- Distinguish VERIFIED, REJECTED and INCONCLUSIVE decisions and preserve pending CANDIDATE status when review is absent.
- Pass only authenticated, validated review facts and reconstructed public domain records to the BeeScan It9 API.
- Persist versioned, tamper-evident-by-validation review records, reviewed-case Markdown/JSON and optional manual submission drafts through existing ArtifactAPI mechanisms.
- Preserve original scan reports, scanner evidence and terminal assessment state without in-place replacement.
- Revalidate source artifacts, review provenance and generated package bytes before declaring review delivery complete.
- Document the operator procedure, evidence prerequisites, refusal states and recovery workflow.

#### Excluded

- New HTTP requests, scans, provider profiles, origin selection or authority expansion.
- Treating a CLI argument, review-file field, scanner output or AI assertion as reviewer authentication.
- Accepting unverified arbitrary filesystem paths as evidence references.
- Modifying original assessment evidence or converting incomplete scans into completed ones.
- Automated exploit verification, arbitrary reproduction scripts or bounty-platform submission.
- BeeUI dashboards, multi-user review services, workflow schedulers, new databases or generic review frameworks.
- New BeeSDK interfaces or changes to BeeDrill and ROP.

#### Deliverable

A working operator CLI review flow that reads one existing authorized assessment, verifies independent human evidence, persists attributable review decisions and produces a complete reviewed Finding case package and optional manual bug bounty submission draft without rescanning the target.

#### Acceptance criteria

- Review selection resolves to an existing complete authorized assessment and an actual candidate belonging to that assessment.
- Missing, corrupt, inconsistent or altered parent/child artifacts fail closed.
- Reviewer identity is established by the host; user-supplied reviewer claims never grant authentication.
- VERIFIED requires present, bounded, independent host-validated evidence that cannot be substituted with original scanner evidence.
- Forged, duplicate, conflicting, stale and cross-assessment decisions cannot become trusted reviews.
- Review execution does not initiate HTTP requests, invoke scanners, modify provider policy or broaden assessment authorization.
- Original assessment status, reports, candidate identities and evidence remain unchanged.
- Review records and generated packages use protected storage, bounded serialization, safe permissions and verified persistence.
- Interrupted or failed review/package persistence remains explicitly incomplete and does not corrupt earlier successful artifacts.
- Deterministic BeeScan-reviewed case outputs match the reconstructed trusted inputs.
- No raw secrets, unrestricted target responses, unsafe reproduction content or unverified impact claims enter public case packages.
- Existing `assess`, `assess --http-signals` and `assess --git-exposure` behavior remains compatible.
- Frozen installation of the reviewed BeeScan It9 revision, full host regressions and hosted CI pass.

#### Checks

- Positive VERIFIED review with genuinely separate authorized verification evidence.
- REJECTED, INCONCLUSIVE, pending and invalid-review scenarios.
- Forged reviewer, unknown Finding, altered source, cross-run reference and duplicate-decision tests.
- Missing evidence, symlink/path traversal, oversize, unsafe content and artifact mutation tests.
- Interrupted write, atomic persistence, read-back verification and recovery tests.
- Explicit zero-network-execution verification for the complete review flow.
- Reproducible CLI smoke with a fresh completed assessment and a real host-controlled review fixture.
- Byte-compatible legacy assessment outputs and existing BS-1 through BS-5 laboratory regressions.
- ROP, BeeDrill, authentication, module and ArtifactAPI compatibility checks.
- Security-sensitive static review, applicable property/security checks, full pytest, build, fresh frozen installation, independent review and hosted CI.

#### DoD

An authenticated operator can review an existing completed BeeScan assessment, independently verify or reject its candidate Findings, and obtain securely persisted, traceable Markdown/JSON reviewed-case artifacts and a conservative manual bug bounty submission draft when supported by valid VERIFIED evidence. The original assessment remains immutable, no new network activity or authority is introduced, and all persistence, failure, regression and delivery gates pass.

---

## Stage 7 — Governed Public Target Execution

### Iteration BS-7 — Managed Rootless Public Egress and Authorized External Assessment

**Status:** DONE

#### Goal

Enable BeeAgent to automatically prepare, validate, reuse and clean up one tightly restricted Linux network environment for an explicitly authorized external HTTP(S) assessment, without requiring operator-managed per-run namespaces or a separate container runtime.

#### Depends on

- Completed BeeAgent BS-1 through BS-6 and the merged multi-address DNS authorization fix.
- Existing pinned httpx/Nuclei providers, BeeScan 0.9.0 public contracts and real local laboratory evidence.
- Verified Linux kernel prerequisites and one security-reviewed rootless networking backend.

#### Change level

`security-sensitive`

#### Scope

- Evaluate the actual Linux host capabilities and select exactly one minimal rootless networking backend after demonstrating compatibility with the current security boundary.
- Implement one BeeAgent-owned managed egress lifecycle with bounded preparation, readiness verification, execution and deterministic cleanup.
- Provide explicit prerequisite diagnostics and opt-in provisioning of the selected pinned backend from a trusted, integrity-verified distribution; never perform hidden privileged package installation.
- Create one ephemeral network session per authorized assessment and reuse it across the existing approved probe, detection and optional Git exposure stages.
- Integrate managed egress into the existing BeeScan assessment orchestrator without introducing a second execution runtime or a generic isolation-provider framework.
- Introduce explicit managed namespace binding while preserving immutable operator approvals, independent authorization, policy equality, reload validation and legacy externally managed namespace compatibility.
- Preserve one operator-approved `connected_ip`, one TCP destination port, bounded DNS membership checks, fixed request profiles and the existing exact nftables allowlist.
- Verify effective destination restrictions both inside the network namespace and across the host-side networking helper or forwarding boundary.
- Revalidate authorization, namespace identity and effective enforcement at existing execution checkpoints, without continuous polling.
- Preserve existing nested Bubblewrap process isolation, pinned provider integrity, TLS hostname verification and request/resource budgets.
- Enforce bounded setup, readiness, execution and teardown deadlines; terminate and reap owned helpers and namespace supervisors on success, refusal, timeout and interruption.
- Persist bounded host-controlled egress lifecycle and cleanup evidence linked to the parent assessment run, without secrets or unrestricted network data.
- Document supported Linux prerequisites, backend provisioning, configuration, operator workflow, failure handling and recovery.

#### Excluded

- Changes to BeeScan, BeeSDK or BeeUI public contracts.
- Docker-first, Podman, Firejail or multi-backend fallback execution frameworks.
- Custom TCP/IP stacks, custom NAT implementations, generic container orchestration or new persistent services.
- Automatic `apt`, `dnf`, `yum` or Docker installation during assessment.
- Automatic target authorization, DNS-selected destinations, multi-target execution or wildcard/CIDR expansion.
- Host-wide unrestricted networking, firewall bypass, TLS bypass, redirects, retries or proxy-based scope escape.
- Arbitrary new providers, web crawling, form discovery, vulnerability detectors or additional Nuclei profiles.
- Automatic VERIFIED Findings, exploitation or bug bounty submission.

#### Deliverable

A working BeeAgent-managed Linux egress capability that prepares one restricted public network session, executes the existing real httpx/Nuclei assessment against an explicitly approved external HTTP(S) target, preserves current assessment/report contracts and produces verified cleanup and lifecycle evidence without operator-managed per-run networking.

#### Acceptance criteria

- Disabled or unapproved execution creates no public network session and sends no target requests.
- Missing or incompatible Linux prerequisites produce an explicit blocked/refused outcome without weakening isolation or silently switching backends.
- The selected networking executable and required assets have reviewed provenance, pinned integrity and protected installation permissions.
- One explicitly authorized assessment creates exactly one managed network session, reused by its permitted stages and destroyed after completion.
- Managed namespace binding never rewrites operator approvals or bypasses equality/reload validation; legacy namespace mode remains compatible.
- Only the approved destination IP and port are reachable; multi-address DNS answers never expand authority.
- Real tests demonstrate that neither the scanner namespace nor its host-side networking helper provides an unauthorized egress path.
- Changed approvals, expired scope, DNS removal, altered isolation, routing or firewall prerequisites refuse before further unauthorized execution.
- Existing exact nftables validation, provider sandboxes, TLS verification, integrity checks and budgets remain effective.
- Original assessment identities, observations, candidates, source evidence and deterministic Markdown/JSON reports remain compatible.
- Setup, readiness, execution, interruption and cleanup failures produce truthful incomplete/refused/timeout states, never false success.
- Cleanup is verified before successful terminal assessment completion; no owned process or resource retains execution authority.
- A reproducible real Linux network laboratory proves allowed connectivity, forbidden destinations, return traffic, interruption and cleanup.
- An explicitly authorized external HTTPS smoke demonstrates the existing real httpx/Nuclei assessment through managed public egress.
- Existing BeeScan CLI, laboratory, offline review, ROP and BeeDrill regressions remain compatible.

#### Checks

- Rootless backend feasibility, kernel prerequisites, executable supply-chain review and host-helper containment assessment.
- Authorization, managed binding, namespace ownership, DNS, exact nftables and destination enforcement tests.
- Real networking tests for permitted and forbidden destinations, alternate routes, proxy attempts and helper behavior.
- Startup, repeated-run, missing prerequisites, timeout, cancellation, process reaping and resource-leak tests.
- Full real httpx/Nuclei assessment and existing HTTP/HTTPS, security-header and Git-exposure laboratory regressions.
- Host lifecycle artifact integrity, terminal-state consistency, safe permissions, redaction and failure-recovery tests.
- Applicable SAST/SCA/DAST, full pytest, frozen installation, build, independent security review and hosted CI.

#### DoD

An authorized operator can invoke the existing BeeScan assessment CLI against one approved external HTTP(S) target, obtain a complete evidence-backed report and verified network cleanup without manually preparing per-run namespaces, routes or firewall rules. One reviewed Linux backend enforces the exact destination boundary, original operator approvals and existing security controls remain effective, and real network plus regression verification passes. Unsupported environments fail closed. BeeScan domain contracts and automatic vulnerability verification remain unchanged.

---

## Stage 8 — AI-Guided Authorized Web Investigation

### Iteration BS-8 — Supervised AI-Guided Web Investigation v0

**Status:** DONE

#### Goal

Enable an operator to provide one explicitly authorized HTTP(S) target and a natural-language task, then let BeeAgent autonomously execute one bounded Web investigation and return an evidence-backed answer through BeeScan without manual Burp, Repeater or HTTP parameter editing.

The first vertical scenario is `framework_version_disclosure`: identify a relevant query parameter, trigger a non-destructive invalid-input error and extract the disclosed framework version.

#### Depends on

- Completed BeeScan Iteration 10 offline Web investigation API at a reviewed immutable Git revision.
- Completed BeeAgent BS-7 managed rootless public egress and existing BeeScan assessment/provenance contracts.
- Existing BeeAgent `ai.profiles`, `ai_transport.call_structured_ai`, ArtifactAPI and protected runtime configuration.
- Explicit operator authorization for the selected target and new investigation request profile.

#### Change level

`security-sensitive`

#### Scope

- Add one explicit BeeAgent investigation entrypoint, provisionally `./start.sh beescan investigate`, accepting a bounded task file and an exact target that must match the independently approved host configuration.
- Introduce an opt-in Web investigation capability with separate, fail-fast validated operator approval; existing probe/detection approvals must not implicitly authorize new paths or mutations.
- Reuse BeeAgent's AI transport and OpenRouter profile with a configured DeepSeek model, without changing other modules' AI provider selection.
- Invoke AI once to classify the operator's task into the fixed supported `framework_version_disclosure` intent and return a schema-validated, bounded plan.
- Reject unsupported, ambiguous or malformed AI plans before any target request; AI-generated targets, arbitrary URLs, payloads and commands never become executable authority.
- Implement one deterministic host orchestrator for the supported plan rather than an open-ended LLM tool-calling loop.
- Extend the existing protected BeeScan HTTP execution boundary with bounded GET/response capture for approved relative paths and a single fixed invalid-input mutation.
- Reuse BS-7 managed egress, exact IP/port containment, DNS revalidation, TLS verification, isolation and cleanup.
- Implement a maximum three-request target workflow: GET root for discovery, GET one discovered endpoint as baseline, GET the same endpoint with one approved parameter mutation.
- Accept only one eligible same-origin discovered endpoint and one numeric query parameter; no JavaScript execution, form submission, redirects or cross-origin traversal.
- Enforce aggregate deadlines, per-response header/body limits, request counts, protected artifact storage and one investigation-owned lifecycle.
- Feed bounded validated discovery/baseline/error evidence into BeeScan It10 for deterministic interpretation and version extraction.
- Invoke AI again only to explain normalized, redacted findings; the authoritative answer and evidence references remain BeeScan-derived.
- Produce explicit terminal statuses, an auditable step trace, source evidence, `investigation_status.json`, `investigation_result.json` and Markdown/JSON reports suitable for a later BeeUI chat interface.
- Preserve existing `beescan bootstrap/probe/detect/assess/review`, ROP, BeeDrill, original providers and default-disabled execution settings.
- Document OpenRouter key setup, profile selection, cost/request budgets, authorized invocation, failure handling and artifact inspection.

#### Excluded

- BeeUI/chat frontend, web action routes or separate frontend development in this iteration.
- Arbitrary LLM tool execution, unbounded autonomous loops, generic agent DAGs, shell access, browser control or a new AI framework.
- New crawling frameworks, Wapiti/ZAP/Burp dependencies, plugin marketplaces or proxy services.
- SQLi, XSS, IDOR exploitation, POST mutation, authenticated application workflows or multi-target scanning.
- Scope inference from the task text, AI output, hyperlinks, DNS answers or scanner results.
- Sending secrets, cookies, unrestricted HTTP bodies or raw private evidence to OpenRouter.
- Automatic VERIFIED findings, unsafe impact claims or external challenge-answer submission.
- Broad changes to BeeSDK, BeeUI, BeeScan's existing offline contracts or unrelated modules.

#### Deliverable

One working operator-supervised, autonomous BeeScan investigation flow:

`Target + task + existing host approval → AI task interpretation → governed Web discovery and bounded checks → BeeScan evidence analysis → AI explanation → final answer and reports`.

The execution is driven by BeeAgent, and the security-domain answer is derived from BeeScan's verified evidence rather than AI guessing.

#### Acceptance criteria

- A fresh operator can supply the authorized target and natural-language task using one documented CLI invocation.
- The chosen OpenRouter/DeepSeek configuration is validated independently of other modules' active AI profiles.
- Invalid provider credentials, model failures, unsupported tasks and invalid structured plans produce truthful statuses without unauthorized requests.
- AI cannot change method, destination, allowed parameter mutation, maximum request count or approval authority.
- The complete supported workflow requires no manual discovery, Repeater editing or response inspection.
- No target request executes before independent host authorization and successful managed isolation.
- Exactly one approved origin/IP/port remains effective for all discovery and verification requests.
- All target responses are treated as untrusted; prompt injection in HTML/errors cannot grant actions or change reported facts.
- Successful evidence yields the detected framework and exact version with source request/response identities and bounded evidence references.
- Missing version, patched application and unsupported task return NO_MATCH or INCONCLUSIVE, never invented answers.
- AI summarization can explain valid findings but cannot replace or promote the authoritative evidence-derived result.
- Setup failure, timeout, cancellation, expiry/revocation and cleanup failure cannot produce a successful completed investigation.
- Original assessment/review artifacts and security behavior remain compatible.
- Status, steps and report artifacts are independently readable and sufficient for a future BeeUI chat presentation.
- Existing CLI and module workflows, frozen dependency profiles and unrelated modules remain regression-clean.

#### Checks

- Mocked OpenRouter/DeepSeek structured task-plan and report-response fixtures; malformed JSON, prompt injection, model outage and over-budget cases.
- Negative authorization, expired/revoked approval, altered scope, DNS, path traversal, redirects and external-link tests.
- Request/method/path/parameter budget tests, bounded response framing, TLS and process isolation checks.
- Real Linux managed-egress laboratory with one vulnerable application exposing a framework version through an invalid numeric query value.
- Patched and deceptive-response variants with no unsupported version claim.
- Independent capture/evidence/source identity and deterministic BeeScan It10 report validation.
- Authorized external HTTP(S) smoke against an explicitly approved test instance when its availability and authorization conditions permit.
- Existing BS-1–BS-7, legacy networking, BeeScan, ROP, BeeDrill and offline review regression suites.
- Ruff/type checks, applicable SAST/SCA/DAST/property checks, full frozen pytest, build, fresh installation, artifact inspection, independent BeeMCP review and hosted CI.

#### DoD

An operator can run one approved, task-driven Web investigation without Burp or manual HTTP editing. BeeAgent uses OpenRouter/DeepSeek to interpret the task, independently governs each HTTP operation and passes validated evidence to BeeScan It10, which extracts the correct framework/version or explicitly reports insufficient evidence. The completed run provides auditable, protected JSON/Markdown artifacts, passes real vulnerable/patched laboratory scenarios and preserves existing authority and compatibility boundaries.

The implementation remains CLI-first and supplies a stable backend result/action contract for the next separately reviewed BeeUI chat increment. No version change occurs during the feature implementation.

### Iteration BS-9 — BeeScan Trusted Local Operator CLI v0

**Status:** DONE

#### Goal

Provide a direct, zero-friction BeeScan terminal interface for a single trusted local operator, allowing the operator to enter a target URL and natural-language task and immediately start the existing AI-guided investigation without manually creating JSON files, configuring target-specific approval profiles or completing repetitive confirmation dialogs.

Separate the private single-operator CLI trust model from the future multi-user Web/SaaS authorization model without weakening the existing investigation execution, evidence and isolation guarantees.

#### Depends on

- Completed BeeAgent BS-8 supervised AI-guided Web investigation.
- Completed BeeScan Iteration 10 deterministic investigation domain API.
- Existing BeeAgent AI transport, governed HTTP capture, managed egress, ArtifactAPI and investigation result contracts.
- Existing local operator execution environment and installed immutable BeeScan dependency.

#### Change level

`security-sensitive`

#### Scope

- Add `./start.sh beescan` as an interactive terminal entrypoint accepting one target URL and one natural-language task.
- Add `./start.sh beescan investigate --target URL --task "TEXT"` for direct noninteractive invocation.
- Preserve the original `./start.sh beescan investigate TASK.json` entrypoint for backward compatibility.
- Introduce one shared validated in-memory task intake contract reused by all three CLI input modes.
- Implement an explicit trusted-local-operator execution mode for the private single-user CLI.
- Use the existing trusted local operating-system execution context rather than introducing Web accounts, subscription plans, RBAC roles or per-run approval dialogs.
- Allow the trusted local operator to select the target directly without maintaining a preconfigured per-target allowlist, hostname-family registry or separate approval profile for each URL.
- Derive one immutable run-scoped target binding from the operator-supplied canonical HTTP(S) origin and independently validated destination.
- Preserve exact-origin enforcement, DNS revalidation, TLS verification, request accounting, deadline enforcement, managed-egress containment and verified cleanup.
- Distinguish the trusted local operator's requested scope from independently verified third-party authorization; never falsely represent external authorization as verified.
- Ensure the new local-operator entrypoint cannot be invoked implicitly through Web requests, task content, remote API payloads or AI-generated instructions.
- Reuse the existing AI classification, bounded investigation orchestration, BeeScan domain analysis and evidence publication.
- Preserve the existing supported investigation capability, fixed request methods and payload profile; do not expand scanner behavior as a side effect of CLI work.
- Display useful investigation progress, terminal status, evidence-derived framework/version when available, finding disposition, run ID and report location.
- Preserve the existing investigation, evidence, lifecycle and report artifact schemas.
- Expose one reusable validated task/result boundary suitable for a later BeeAgent/BeeUI Web chat adapter.
- Document the distinction between private local operation and future remote multi-user execution.

#### Excluded

- Per-target approval forms, checkbox dialogs and mandatory interactive confirmation steps.
- New hostname allowlists, approval-profile registries or subscription policies for the private CLI.
- BeeUI/Web chat implementation in this iteration.
- Remote access to trusted-local-operator privileges.
- New users, billing, RBAC, quotas or SaaS tenancy.
- A separate BeeScan runtime, database, scanner executor or agent framework.
- Arbitrary shell execution, uncontrolled payload generation, unrestricted AI tool use or new vulnerability detection families.
- Removal of existing transport containment, evidence integrity checks or resource cleanup.
- New proxy services, purchased IP addresses, IP rotation or external egress infrastructure.
- Changes to BeeScan, BeeSDK or generic BeeUI components without a proven blocker.
- Hardcoded external testing targets, task answers, laboratory identities or private investigation artifacts.
- Automatic VERIFIED findings or external vulnerability submission.

#### Deliverable

One complete single-operator CLI workflow:

`Operator target + task → validated run-scoped target binding → AI task interpretation → existing governed investigation → BeeScan domain analysis → protected artifacts → terminal result`.

The operator does not manually create JSON, edit YAML for every target, select authorization profiles or answer additional confirmation prompts.

The trusted local mode remains separate from future remote Web execution.

#### Acceptance criteria

- `./start.sh beescan` opens a terminal interaction accepting a target and natural-language task.
- `./start.sh beescan investigate --target URL --task TEXT` supports direct invocation without user-created JSON.
- The original `./start.sh beescan investigate TASK.json` continues working with its original secure file-validation behavior.
- The three input modes use a single validated investigation task contract without duplicating the investigation engine.
- A trusted local operator does not need to pre-register a separate target-specific approval profile or edit YAML for each investigation.
- The CLI does not introduce additional confirmation dialogs, checkbox flows or subscription-related restrictions.
- The run records the actual trusted local operator context and selected target without falsely claiming independently verified third-party authorization.
- The exact operator-selected origin and resolved destination are bound to the execution; AI responses, HTTP content and redirects cannot expand them.
- Existing DNS/TLS checks, managed network containment, request deadlines, request budgets and cleanup guarantees remain effective.
- Unsupported URL formats, invalid task input and incompatible runtime prerequisites produce truthful errors without unsafe execution.
- Unsupported investigation tasks do not trigger arbitrary scanning or fabricated answers.
- The CLI never imports task-supplied modules, executes task-generated shell commands or treats AI text as execution authority.
- Successful investigations display the evidence-derived answer and preserve CANDIDATE finding semantics.
- REFUSED, TIMEOUT, ERROR, NO_MATCH and INCONCLUSIVE remain distinguishable and cannot be presented as successful vulnerability findings.
- Existing protected source evidence, steps, lifecycle and Markdown/JSON reports remain compatible.
- The trusted local operator mode is inaccessible through the current Web routes and is not automatically exposed to future remote users.
- Existing BeeAgent CLI workflows, ROP, BeeDrill, BeeScan and unrelated modules remain regression-clean.

#### Checks

- Interactive terminal and direct CLI invocation tests.
- Missing arguments, malformed target, oversized input, quoting, non-TTY and interruption tests.
- Legacy task-file backward compatibility and file-security validation tests.
- Shared task intake validation and equivalent execution-path tests.
- Trusted local operator entrypoint isolation and remote invocation refusal tests.
- Run-scoped origin binding, DNS revalidation, redirect refusal and exact destination enforcement tests.
- Existing AI classification, unsupported-task and prompt-injection regressions.
- Existing three-request budget, managed-egress containment, deadlines, cancellation and cleanup tests.
- Investigation result, source evidence, candidate, artifact integrity and deterministic reporting regressions.
- A real explicitly authorized Web laboratory executed through the direct CLI without manually preparing task JSON.
- Full relevant pytest, Ruff/type checks, applicable security review, entrypoint smoke, build, installed dependency verification, artifact inspection, independent BeeMCP review and hosted CI.
- Regression checks confirming the existing Web interface cannot invoke trusted local execution.

#### DoD

A single trusted local operator can launch BeeScan from the terminal, supply a target and natural-language task, and receive the evidence-backed investigation result without creating JSON files, configuring per-target approval profiles or answering repetitive confirmation prompts.

The existing BeeAgent investigation backend remains the sole execution engine. The selected target is bound to the run, security-critical transport and evidence guarantees remain effective, and all generated artifacts continue to use the existing protected ArtifactAPI.

The new trusted local execution mode is isolated from remote Web interfaces. Future multi-user authorization, subscriptions, quotas and Web access policies are handled through separately reviewed iterations.

The existing JSON-file CLI remains backward compatible. Full regressions, real authorized laboratory verification and independent review pass.

No BeeScan, BeeSDK or BeeUI implementation changes are required. Package versions remain unchanged during ordinary implementation.

### Iteration BS-10 — Governed Debug Page Disclosure Investigation v0

**Status:** DONE

#### Goal

Extend the existing BS-8/BS-9 BeeScan investigation engine with an authorized, bounded `debug_page_secret_disclosure` workflow using the reviewed BeeScan It11 public domain API.

Enable a trusted local operator to discover one diagnostic page and receive the exact evidence-derived requested value without manual HTTP investigation.

#### Scope

- Extend strict AI task-family classification while preserving existing families.
- Validate the operator-requested configuration-field selector independently of AI output.
- Reuse the current trusted-local CLI, host authority, settings, ArtifactAPI and managed egress.
- Perform one governed GET / for bounded HTML-comment discovery.
- Pass authenticated discovery facts to BeeScan It11 for resource selection.
- Perform at most one additional governed same-origin GET.
- Normalize complete diagnostic response evidence within explicit size limits.
- Use BeeScan It11 for deterministic disclosure analysis.
- Keep raw diagnostic content and extracted values out of AI requests.
- Prevent plaintext sensitive values from entering child source artifacts, parent artifacts, logs or ordinary JSON/Markdown results.
- Bind safe persisted evidence projections to authenticated request/response provenance.
- Expose the requested value only through an explicitly protected trusted-local TTY path.
- Suppress sensitive output on non-TTY, redirected, cancelled or failed executions.
- Preserve all BS-8/BS-9 CLI modes and framework-version investigation semantics.
- Preserve exact request accounting, DNS/TLS validation, isolation and verified cleanup.

#### Excluded

- Web/BeeUI access to trusted-local operator privileges.
- Generic crawling, guessed debug paths, directory brute force or unrestricted scans.
- AI-selected executable URLs, commands, methods, payloads or targets.
- Cross-origin navigation, redirects, JavaScript execution or additional providers.
- Hardcoded PortSwigger resources or known secret values.
- Raw diagnostic persistence, unrestricted environment dumps or secret collection.
- Automatic VERIFIED findings or laboratory answer submission.
- New runtime engines, databases, broad refactors or unrelated configuration changes.

#### Deliverable

One complete CLI workflow: operator task → validated classification → governed discovery → BeeScan-selected resource → governed evidence capture → deterministic analysis → protected terminal answer → redacted CANDIDATE report.

#### Acceptance criteria

- Supported debug-page tasks work through the existing CLI without manual URL discovery.
- Unsupported tasks produce an explicit non-success result with zero target requests.
- Successful investigations issue exactly two authorized GET requests.
- No candidate, ambiguous candidates or unsafe references trigger a second request.
- Existing origin/IP/port, DNS, TLS, budget, timeout and sandbox policies remain enforced.
- No plaintext sensitive value reaches AI, logs, child artifacts or ordinary reports.
- Trusted TTY presentation reveals only the requested evidence-derived value.
- Non-TTY, cancellation, failed cleanup or unverifiable evidence cannot release the value.
- Safe source metadata, final status, evidence references and report agree.
- Existing framework-version investigations and unrelated module tests remain compatible.

#### Checks

- Structured AI classification and validated field-selector tests.
- Two-request workflow, exact accounting and provenance tests.
- Negative scope, URL, DNS/TLS, framing, redirect and cleanup tests.
- Secret non-disclosure tests across all persistence, logging and output paths.
- Real vulnerable and patched Linux managed-egress laboratories.
- Fresh authorized PortSwigger debug-page acceptance.
- BS-8/BS-9 and unrelated module regressions.
- Full pytest, applicable static/DAST checks, independent review and hosted CI.

#### DoD

An authorized local CLI investigation obtains the requested response-observed value using at most two governed GET requests, with protected operator presentation, redacted persisted evidence, consistent provenance and verified cleanup.

The existing investigation workflow remains compatible. Linux positive/negative laboratories, external authorized smoke, required tests, security review and CI pass.

No unrelated version change occurs.

### Iteration BS-11 — Governed Adaptive Investigation and Resume v0

**Status:** DONE

#### Goal

Extend the existing BeeScan trusted-local investigation runtime with a bounded adaptive execution loop using the reviewed BeeScan It12 decision API.

Enable an operator to provide a target and investigation objective, allow BeeScan to select subsequent supported checks from real evidence, and receive a reproducible investigation result or actionable partial summary.

Support minimal persistent Investigation Case checkpoints so the operator can inspect prior decisions and resume supported unfinished work without unnecessarily repeating completed checks.

Preserve BeeAgent as the sole orchestration, execution, authorization and storage runtime.

#### Depends on

- Completed BeeScan It10/It11 investigation domain capabilities.
- Completed BeeAgent BS-8/BS-10 governed investigation runtime.
- Reviewed BeeScan It12 adaptive decision contract.
- Existing BeeAgent AI profiles, trusted-local CLI, managed egress, ArtifactAPI, source authentication and reporting.

#### Change level

`security-sensitive`

#### Scope

- Extend the existing BeeScan investigation entrypoint to support one bounded adaptive investigation objective.
- Reuse the current target/task intake and trusted-local operator execution model.
- Reuse existing governed HTTP capture, provider execution, DNS/TLS validation, destination enforcement and managed-egress isolation.
- Reuse existing framework-version and diagnostic-disclosure capabilities as the initial supported action set.
- Execute the cycle: observe → request BeeScan decision → authorize selected capability → execute → authenticate evidence → evaluate → continue or stop.
- Allow BeeScan to select the next supported action based on authenticated evidence and previous Case state.
- Use existing AI profiles for task interpretation and optional bounded hypothesis proposals where useful.
- Validate every AI-proposed action against BeeScan domain constraints and BeeAgent execution policy before any tool invocation.
- Keep the execution sequence bounded by explicit step, request, time and AI-use budgets.
- Persist minimal Case checkpoints through the existing ArtifactAPI, including step states, selected actions, evidence references, decisions, outcomes and measured execution costs.
- Preserve distinct parent Case identity and individual execution/run identities.
- Support inspection of the latest Case state, completed steps, pending actions, limitations and next-action recommendations.
- Support explicit operator-driven continuation of an unfinished or inconclusive Case using its preserved identity.
- Resume only from authenticated, internally consistent completed checkpoints; do not assume that redacted artifacts contain reusable raw HTTP evidence.
- Reuse completed steps only when durable authenticated evidence is sufficient. Otherwise require a fresh governed capture and record the reason.
- Revalidate current scope, target binding, authorization, execution budgets and dependency readiness before resumed network actions.
- Preserve protected trusted-local TTY presentation and existing sensitive-result redaction guarantees.
- Produce a useful terminal summary containing status, completed checks, discovered evidence, unresolved hypotheses, recommended next steps, run/Case identifiers and report locations.
- Record request counts, elapsed time, AI calls and available token/cost usage, action selection and terminal reasons without fabricating unavailable measurements.
- Preserve existing direct, interactive and task-file CLI behavior and existing investigation artifact compatibility.

#### Excluded

- A new BeeAgent core runtime, parallel orchestrator or standalone BeeScan service.
- New scanner engines, browser automation, proxy frameworks, arbitrary shell execution or additional network providers.
- Unrestricted AI tool calling, generated exploitation payloads or unapproved target expansion.
- Automatic execution of unsupported actions suggested by an LLM.
- Persistent AI conversation dumps, hidden agent memory or unrestricted reasoning traces.
- A generic Skill Bank, multi-agent swarm, MCP tool marketplace or external autonomous agent framework.
- A new database, graph engine, Redis queue, distributed worker system or vector store.
- Web/BeeUI development, multi-user authorization, subscriptions or billing.
- Automatic vulnerability verification, exploitation escalation or bug bounty submission.
- Replaying sensitive plaintext from stored Case artifacts.
- Repeating completed steps merely to satisfy an expected investigation sequence.
- Hardcoded PortSwigger targets, challenge paths, answers or laboratory-specific routing.
- Unrelated BeeAgent core refactors or package-version changes.

#### Deliverable

One complete trusted-local workflow:

`Target + Task → governed discovery → BeeScan next-action decision → governed capability execution → authenticated evidence → evaluation → continue / stop → persisted Case + report`.

The operator can inspect the resulting Case and continue a supported investigation using preserved state and additional instructions.

The workflow reuses existing BeeAgent execution and artifact infrastructure and provides explicit metrics and evidence-backed next actions.

#### Acceptance criteria

- The existing CLI can launch an adaptive investigation without manually constructing a sequence of scanner steps.
- The first action and subsequent supported actions are selected using validated task context and actual evidence.
- At least one real investigation demonstrates different next-action decisions for different observed responses under the same general objective.
- The runtime can execute multiple bounded decision cycles without a hardcoded task-family sequence.
- Only existing explicitly supported capabilities are executable.
- Every request is independently checked against current origin, IP, DNS/TLS, scope, budget, deadline and execution policy.
- Missing authorization, unsupported capability, exhausted budget, invalid AI output or unavailable evidence stops safely with an explicit reason.
- Completed and authenticated Case steps are preserved with consistent source and execution identities.
- A second CLI invocation can inspect and resume a supported unfinished Case using its persisted checkpoint.
- Resumption does not reexecute already completed checks when sufficient safe authenticated state is available.
- Missing or insufficient persisted evidence results in explicit recapture or refusal, never a fabricated completed result.
- Changes to target, scope, authority, dependency or Case identity cannot silently inherit previous execution permission.
- Secrets and raw diagnostic response bodies remain absent from ordinary Case state, logs, AI requests, reports and persisted source artifacts.
- Trusted-local TTY restrictions and verified cleanup remain effective after each execution segment.
- Request, elapsed-time, action and AI-use metrics correspond to actual host execution evidence.
- Failed or unsupported investigations produce a meaningful partial summary and actionable next steps.
- Existing BS-8/BS-9/BS-10 and unrelated BeeAgent workflows remain compatible.

#### Checks

- Full adaptive investigation against controlled vulnerable and patched HTTP/HTTPS laboratories.
- Different discovery responses leading to different BeeScan-selected supported checks.
- Negative-result follow-up, unsupported capability, missing evidence and explicit terminal-stop scenarios.
- Same objective against previously unfamiliar laboratory fixtures without implementation changes specific to those fixtures.
- Fresh process restart followed by Case inspection and authorized resume.
- Completed-step reuse, interrupted-step handling and prevention of duplicate completed work.
- Scope drift, changed destination, DNS rebinding, TLS failure, redirects, expired authority and exceeded-budget scenarios.
- Malicious HTTP content and AI output attempting to alter target, method, execution policy or capability arguments.
- Case/checkpoint tampering, foreign-run evidence, inconsistent transitions and missing artifact read-back tests.
- Secret redaction across AI transport, logs, Case checkpoints, child artifacts, reports and non-TTY output.
- Exact request accounting, subprocess isolation, cleanup verification and controlled failure recovery.
- Existing framework-version/debug-disclosure and unrelated module regressions.
- Full pytest, applicable static/security checks, build, integration tests, artifact inspection, independent BeeMCP review and hosted CI.

#### DoD

A trusted local operator can initiate one bounded adaptive BeeScan investigation, observe evidence-driven selection of supported follow-up checks, receive a meaningful final or partial result, and resume supported unfinished work using a validated persistent Investigation Case.

At least one previously unfamiliar controlled scenario demonstrates adaptive behavior without challenge-specific code changes.

All actual tool execution remains within BeeAgent's existing authorization, destination, resource, isolation and evidence boundaries.

The implementation reuses existing providers and infrastructure, preserves existing investigation compatibility and introduces no additional runtime, database or multi-agent subsystem.

No unrelated version change occurs.

### Iteration BS-12 — Autonomous Web Investigation CLI MVP

**Status:** DONE

#### Goal

Deliver the first practically usable CLI-first autonomous Web reconnaissance and information-disclosure investigation workflow using BeeScan It13 and the existing BeeAgent execution, AI, security and artifact infrastructure.

An authorized operator supplies only Target and Task; the system performs bounded research and returns an evidence-backed answer or meaningful partial report.

#### Scope

- Make the evidence-driven investigation loop the default for `./start.sh beescan investigate --target URL --task TEXT`.
- Preserve legacy invocation, trusted-local operator authorization, --inspect and --resume compatibility.
- Begin governed HTTP discovery without rejecting an unfamiliar but safely researchable task solely because of AI classification.
- Execute bounded same-origin GET discovery using existing HTTP capture, DNS/TLS, destination policy and managed egress.
- Support standard discovery resources, evidence-observed links, directory references and tightly bounded documented candidate derivation.
- Enforce configurable request, step, depth, response-size and deadline budgets with actual execution accounting.
- Reuse existing AI profiles for bounded objective/hypothesis assistance, validating all proposed actions against supported capabilities and host authority.
- Pass authenticated observations to BeeScan It13 and execute only its eligible host-validated proposals.
- Reuse existing It10/It11 specialized capabilities where applicable without duplicating domain decisions.
- Extend Case checkpoints and safe resume for generalized discovery while retaining prior Case inspection and compatible legacy behavior.
- Preserve protected transient sensitive-value handling and trusted-local terminal presentation; persist only redacted evidence.
- Produce task-oriented terminal, JSON and Markdown outcomes with examined resources, decisions, evidence, limitations, next actions and actual metrics.

#### Excluded

- New runtime, crawler framework, browser automation, database, scheduler or multi-agent subsystem.
- Unrestricted wordlists, arbitrary AI commands, unsafe URLs, cross-origin expansion or state-changing requests.
- Automated exploitation, verification claims or Bug Bounty submissions.
- BeeSDK/BeeUI changes, Web UI and unrelated refactoring without a demonstrated blocker.

#### Deliverable

`Target + Task → Governed Discovery → BeeScan Decision → Governed Execution → Evidence Evaluation → Continue / Stop → Answer / PARTIAL + Case`.

#### Acceptance criteria

- The default CLI command performs actual discovery for a safely researchable unfamiliar task.
- Different observed Web surfaces yield different validated investigation actions without challenge-specific routing.
- A bounded multi-resource investigation can resolve a previously unsupported disclosure scenario using authenticated HTTP evidence.
- Unsupported, exhausted, patched or unresolved investigations return truthful and useful partial/negative outcomes.
- Scope, destination, time, request, AI-action and output protections remain enforced.
- Secret-bearing values do not appear in AI requests, persisted artifacts, logs or redirected output.
- Fresh-process inspection/resume works without unsafe evidence reuse or unnecessary repeated completed work.
- Legacy framework-version, debug-disclosure and Case workflows remain compatible.

#### Checks

- Full frozen tests, package build, static/type/security checks and independent verification.
- Real AI/HTTP execution against authorized PortSwigger or equivalent public laboratories.
- Distinct unfamiliar disclosure, patched target, incomplete task and legacy regression scenarios.
- Scope/DNS/TLS, egress, redirect, prompt-injection, secret-redaction and corrupted-checkpoint checks.
- Actual metrics, Case inspection/resume, report inspection and hosted CI.

#### DoD

An operator can supply an unfamiliar authorized Web target and information-disclosure task through one CLI command. BeeAgent performs bounded autonomous discovery and execution using BeeScan It13 and returns a substantiated answer or meaningful partial investigation.

At least one previously unsupported real disclosure scenario succeeds without hardcoded challenge logic. Real AI/HTTP, negative, legacy, security, checkpoint and artifact acceptance pass before coordinated merge.

No new runtime, unnecessary dependency, UI implementation or unrelated version change occurs.

---

## Stage 9 — Governed External DAST Execution

### Iteration BS-13 — Governed ZAP Web Assessment Provider MVP

**Status:** PLANNED

#### Goal

Предоставить BeeAgent первую расширяемую DAST capability на основе готового ZAP scanner engine с управляемым запуском и интеграцией результатов в BeeScan.

Устранить необходимость самостоятельно разрабатывать Web fuzzing, parameter mutation и десятки специализированных detector implementations.

#### Scope

- Переиспользовать текущий BeeAgent execution, authorization, policy, evidence и artifact lifecycle.
- Подключить фиксированную, проверенную версию ZAP как внешний provider, без установки полноценного второго BeeAgent runtime.
- Запускать ZAP только по явному operator-approved активному профилю.
- Реализовать ограниченный профиль HTTP parameter security assessment, первоначально использующий существующий ZAP Path Traversal rule ID 6.
- Использовать проверенный механизм discovery/import URL, а не собственный crawler framework.
- Обеспечить независимое от ZAP ограничение destination, DNS/IP, исходящих соединений, времени и фактического количества запросов.
- Проверять выполнение sandbox и сетевых ограничений до разрешения активных запусков.
- Ограничить набор scanner rules, параметров исполнения и ресурсов; запретить unrestricted scripts, external callbacks и автоматическую установку дополнительных компонентов.
- Сохранять только проверенные и redacted scanner outcomes, доказательства исполнения, request accounting и cleanup.
- Передавать нормализованные результаты через публичный контракт BeeScan It14.
- Возвращать CANDIDATE / NO_MATCH / PARTIAL с понятным указанием ограничений и неподтверждённых утверждений.
- Сохранить существующий investigation CLI, Case semantics и совместимость BS-1–BS-12.
- Переиспользовать существующие Nuclei и HTTP capabilities, не заменяя их ZAP.

#### Excluded

- Собственный path traversal detector, parameter fuzzer и payload engine.
- Неограниченный ZAP active scan, unrestricted plugin marketplace и скачивание расширений при исполнении.
- Предоставление LLM прямого доступа к ZAP API, shell или произвольным HTTP-запросам.
- Cross-origin scanning, неподтверждённая авторизация и автоматическая эксплуатация.
- Новый database, scheduler, Web UI, multi-agent runtime или BeeSDK API.

#### Deliverable

`Target + Task + Explicit Scope/Approval → BeeAgent Governed ZAP Profile → Validated External Evidence → BeeScan Evaluation → CANDIDATE / NO_MATCH / PARTIAL + Case + Report`.

#### Acceptance criteria

- Невозможно выполнить активную проверку без явно одобренного профиля.
- Scanner не выходит за exact origin, approved destination и установленные бюджеты.
- Проверка контроля фактического HTTP request count проводится независимо от отчёта ZAP.
- Система прерывает выполнение при нарушении scope, DNS/TLS, лимитов или изоляции.
- На разрешённой path traversal лаборатории выполняется реальная проверка без challenge-specific implementation.
- Исправленный и отрицательный scenarios не создают ложных находок.
- Подмена scanner output, результаты другого run и incomplete evidence отклоняются.
- Case, результаты, журналы и reports не содержат чувствительного raw HTTP content.
- Не менее 10 независимых acceptance cases проверяют scanner integration, включая positive, negative, security, compatibility и failure conditions.
- Старые framework/debug/source-disclosure сценарии сохраняются.

#### Checks

- Targeted/full pytest, Ruff/Pyright, build и hosted CI.
- Provider integrity, sandbox, scope/IP pinning, request ceilings, timeout и cleanup tests.
- Реальная end-to-end проверка на разрешённой лаборатории.
- Negative/patched, malicious scanner output, tampered artifacts и interrupted execution.
- Сравнение результата с BS-12 baseline.
- Independent BeeMCP security review перед PR.

#### DoD

BeeAgent использует существующий ZAP scanner engine через enforceable governed provider и получает evidence-backed BeeScan результаты.

Если независимое ограничение сети и запросов не доказано, активный provider не выпускается, а итерация остаётся незавершённой.

Никаких собственных DAST-algorithms, необоснованных зависимостей или изменений версий.

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
- `README.md`

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
