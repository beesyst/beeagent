# SDLC — BeeAgent

## Purpose

BeeAgent uses a lightweight, evidence-driven development process. An Issue defines the approved task, a branch contains the implementation and its fixes, tests and artifacts establish behavior, and a PR records the verified delivery. [ROADMAP.md](ROADMAP.md) defines product increments; [SECURITY.md](SECURITY.md) defines standing security requirements.

The goal is useful, reproducible delivery with minimum process overhead.

## Principles

- KISS, YAGNI and DRY: reuse working code and public contracts; do not introduce speculative dependencies, frameworks or configuration.
- One functional iteration delivers a meaningful end-to-end capability. Fix defects found during that iteration in the same branch before PR, rather than creating new iterations for individual regressions.
- Preserve the division between BeeAgent host, BeeSDK, domain modules and BeeUI. Assign cross-repository changes explicitly when proven necessary.
- A working operator entrypoint, correct failure behavior and inspected artifacts matter more than an implementation narrative.
- Distinguish observed facts, assumptions and limitations. Never assert that a skipped test, external assessment or hosted CI passed.
- Do not change package versions during ordinary feature/fix/docs work; use the approved release process.

## Workflow

```text
ROADMAP + existing implementation
  -> approved Issue / acceptance criteria
  -> authorized branch/worktree
  -> code + focused tests + relevant artifacts
  -> independent verification and current-branch corrections
  -> read-only final review
  -> authorized PR + applicable CI
  -> review and merge
  -> release when appropriate
```

### Plan and implement

Confirm the actual problem and existing capabilities before planning. Define Scope, Excluded, Deliverable, observable Acceptance Criteria, change level and verification. A numbered iteration is justified by a substantial product increment, not a typo, one test, documentation cleanup or a laboratory-specific workaround.

Work in the selected branch and worktree. Preserve unrelated staged, unstaged and untracked changes. Never create/switch branches, commit, push, open PRs, merge or reset without explicit user authorization. Make the smallest complete change needed for the Issue. Do not change another repository without an explicitly approved companion task.

### Verify

Run tests for the changed behavior and negative paths. For runtime changes, use the actual supported entrypoint and inspect resulting logs/artifacts where applicable. For security-sensitive work, test refusal, authorization, provenance, limits, malformed input, secrets, cleanup and rollback/recovery according to the affected boundary. Pair BeeScan/ROP/BeeDrill tests with the host when their public integration contract changes.

Record commands, exit codes, test counts, skipped checks, artifact identities and limitations. An operator-facing feature is not complete merely because unit tests pass. Independent verification reads the implementation and tests, not only the implementer's report. Close current-Issue blockers in the same branch; do not use review as a reason for unrelated refactoring.

### Review and deliver

Final review compares the full branch/diff with the approved Issue, actual contracts, tests, configuration and artifacts. A read-only BeeMCP reviewer cannot run tests and must label supplied test output as reported evidence. Missing required inspection is `REVIEW INCOMPLETE`, not implicit approval.

Use the existing Issue and PR templates. The PR states what changed, what remained excluded, actual checks, security impact, artifacts, compatible contracts and known limitations. Merge only after mandatory verification, review, applicable CI and explicit authorization. Prefer one coherent squash merge per Issue.

## Change levels

| Level                | Typical change                                                                                                    | Required evidence when applicable                                                          |
| -------------------- | ----------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `low-risk`           | Docs, narrow non-runtime maintenance or isolated test-only changes                                                | Diff check, link/format validation, targeted checks if needed                              |
| `runtime-risk`       | Runtime behavior, configuration, module/case routing, UI read model, reports and artifacts                        | Relevant pytest, supported-entrypoint smoke, log/artifact inspection, compatibility checks |
| `security-sensitive` | Authority, secrets, network/capability execution, attachments, parsing, dependencies, active scanning or mutation | Runtime checks plus explicit abuse/refusal cases and risk-matched security review          |

Apply SAST/static review to security-relevant source, SCA to dependency/provider changes, DAST to affected authorized network-facing execution, fuzzing/property tests to complex untrusted parsers, and IAST only where a justified instrumented host exists. None is a universal checkbox. Follow [SECURITY.md](SECURITY.md).

## Configuration and artifacts

`config/settings.yml` is the source of truth for runtime options; enabled required fields must be validated fail-fast through the existing settings layer. Secrets are environment-backed. If a change affects the operator CLI, execute that command when feasible; if it affects persistence, verify file ownership, schema, read-back, safe content and corresponding status/logs. Do not infer success from a report existing without required terminal evidence.

Typical host checks, selected according to the Issue:

```bash
uv run --frozen pytest -q
./start.sh <supported-command>
git diff --check
```

Integration and real-kernel laboratories are separate explicit checks; run them only against controlled or independently authorized targets. Report missing prerequisites rather than claiming a pass. Update `uv.lock` only when an approved dependency change requires it; do not add a standalone lockfile-validation gate.

## Documentation ownership

- `ROADMAP.md` and product roadmaps: product increments, acceptance and historical status.
- `SPEC.md` and `ARCHITECTURE.md`: current public behavior and component ownership.
- `WEB_UI.md` and product operating guides: implemented interface and integration contracts.
- `DEV_GUIDE.md`: current commands and local developer procedures.
- `SECURITY.md`: stable security policy, not an implementation changelog.
- `SDLC.md`: stable process, not an iteration diary.

Update only the owning document when an approved change makes its behavior, contract or instructions materially incomplete or false. Do not append every iteration to normative documents or reformat unrelated documentation. Security/SDLC policy changes require an actual threat-model/control or process change.

## Definition of Done

- Approved Scope and Acceptance Criteria are satisfied by working behavior and explicit failure cases.
- Required tests and relevant real-entrypoint/artifact checks are recorded, or their absence is a disclosed blocker.
- Current security controls, authorization, configuration and public contracts remain valid.
- Cross-repository dependencies, regressions, user-visible limitations and operational prerequisites are identified.
- Relevant documentation matches the delivered behavior without unrelated churn.
- Independent verification, final review and applicable CI pass before authorized merge.
- Ordinary changes leave the package version unchanged (`version not changed`).

## Release

Use Conventional Commits and existing Release Please workflows. Release/version changes are controlled by the approved release process. A local green suite or merged PR is not proof of a published package or deployed production release.
