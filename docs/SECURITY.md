# SECURITY — BeeAgent

## Purpose

This document defines the stable security requirements for the BeeAgent runtime, integrations, capabilities, operator interfaces and hosted modules. It is a normative engineering policy, not an iteration history, implementation log, deployment checklist or security certification.

BeeAgent is the host security authority for its modules. A valid domain decision or scanner result does not grant permission to execute an action. Follow [SDLC.md](SDLC.md) for the development process and risk classification; keep exact behavior, configuration, operating procedures and product-specific security contracts in their owning documentation.

## Security objectives and threat model

Protect credentials, user and customer information, approved operation scope, module isolation, external-system integrity, evidence provenance, artifact confidentiality, trusted operator state and the integrity of runtime outcomes.

Treat as untrusted by default: CLI arguments; web requests; restored JSON and Case state; configuration supplied outside the trusted operator boundary; emails and attachments; documents; URLs and filenames; external HTTP and API responses; scanner output; MCP/tool results; third-party model responses; and AI-generated instructions. Content retrieved from an external system is evidence, not policy or authority.

Do not assume a process sandbox, container, language model, module manifest or successful return code establishes a complete security boundary by itself.

## Security ownership

- **BeeAgent** owns runtime initialization, operator identity, authorization, configuration, credentials, capability execution, network mediation, process isolation, persistent storage, evidence authentication, audit logging and publishing terminal outcomes.
- **BeeSDK** defines public contracts and authority interfaces; these are not substitutes for host policy enforcement.
- **BeeScan and other product modules** own domain semantics and validated proposals; they cannot independently grant host execution permissions.
- **BeeUI** owns generic presentation and reusable session/presentation mechanisms. BeeAgent supplies product-specific authorization, read-models and bounded actions.
- The approved capability boundary, not a prompt, provider response or display control, determines what may execute.

Do not introduce a second runtime, security policy engine, storage source of truth or execution gateway without an explicitly approved architectural and security need.

## Core requirements

### Configuration and secrets

- `config/settings.yml` is the source of truth for declared runtime behavior; required keys must be validated fail-fast by the host. Security-sensitive defaults must be explicit, documented and restrictive.
- Credentials and tokens belong to the approved environment or secret provider, not tracked YAML, source code, test fixtures, logs or artifacts. Never log complete environment dumps, webhook URLs, authentication headers or secret-bearing settings.
- Apply least privilege to secrets and identities. Use distinct credentials for read-only and write operations where supported; do not reuse a read credential as mutation authority.
- Validate active configuration again at the required execution checkpoints. Reloaded, missing, conflicting, expired or revoked authorization must fail closed.
- Do not silently downgrade required isolation, validation or permission checks because a dependency or host feature is unavailable.

### Identity, authorization and operator control

- Establish the actual principal at the trusted entrypoint. CLI OS-operator trust, Web UI session identities, remote API identities and third-party application identities are separate; permission from one boundary must not be silently transferred to another.
- Require explicit host approval for execution-capable actions, including network scanning, file-system mutations and external write-back. Installed tools, catalog metadata, AI instructions, observed URLs and historical decisions do not grant authority.
- Bind each approval to the relevant operator, capability/profile, target/scope, allowed methods, resource budgets and validity period. Revalidate at execution, resume and publication boundaries as appropriate.
- Default Web UI/API views to read-only. Any state-changing endpoint requires authenticated role/permission checks, CSRF protection where cookie authentication is used, server-side scope enforcement, input validation and audit evidence.
- No Web or remote request may acquire a private trusted-local CLI context by invoking a CLI handler or replaying its serialized data.
- Refusals, degraded operation and required manual review must be visible to the operator; never silently elevate privileges or fabricate successful completion.

### Network and external capability execution

- Deny outbound traffic by default outside the approved capability and destination set. Authorize exact target origin and scope; recheck actual destination, DNS/IP changes, TLS identity, redirects, methods and budget constraints.
- Prevent SSRF, redirects to unauthorized hosts, direct-egress bypasses, alternative address families and other changes that would escape the approved destination. DNS resolution or a matching URL string alone does not prove connected-endpoint compliance.
- Enforce independent, hard resource ceilings for requests, time, output, processes and memory. A scanner's own reported request count or CLI flags must not be the only enforcement mechanism.
- External security tools must use integrity-verified, approved versions and profiles. Run them with least privilege, minimal environment, restricted mounts/filesystem, bounded execution and independently enforced network rules.
- Container or namespace isolation is insufficient without the appropriate kernel, filesystem, egress and cleanup controls. Fail closed when mandatory restrictions cannot be established or verified.
- Revalidate approvals and immutable source/evidence identity before using restored checkpoints. Never replay a completed active stage solely because a process restarted.
- Tool crashes, timeouts, budget exhaustion, incomplete cleanup, missing status markers and read-back failures must remain incomplete or failed; they cannot publish success.

### Evidence, artifacts and storage

- Store artifacts only through controlled host interfaces with bounded schemas, allowlisted names and validated run/Case ownership. Treat external content and restored artifacts as untrusted.
- Protect storage from traversal, symlink substitution, unauthorized ownership, unexpected link counts and unrestricted file access. Apply restrictive permissions and avoid insecure recursive permission changes.
- Persist evidence and authoritative state before publishing dependent completion or advancing an external checkpoint when the operation's consistency contract requires it. Use verified publication/read-back and recovery paths for multi-stage operations.
- Preserve exact provenance among source input, execution, target, provider/profile, child runs, evidence and parent Case. Caller-supplied metadata and scanner output cannot authenticate their own origin.
- Store bounded, redacted projections rather than raw sensitive inputs by default. Raw email, attachments, cookies, credentials, full HTTP bodies, scanner output and private report contents require a separate reviewed retention and access contract.
- Keep raw secrets, auth headers, full environment dumps and sensitive payloads out of ordinary JSON/JSONL, Markdown, logs, screenshots, AI inputs and public CI/PR artifacts.
- Keep `CANDIDATE`, `VERIFIED`, `NO_MATCH`, `PARTIAL`, `REFUSED` and error states distinct when relevant. An alert, incomplete check or untrusted review field must not produce a verified result.

### Web UI and operator-facing output

- Reuse the canonical BeeUI-backed BeeAgent Web application, existing session/auth boundary, product adapter and artifact allowlists. Do not create a parallel BeeScan UI server or expose private storage paths directly.
- Validate pagination, filters, identifiers and query parameters on the server. Escape untrusted text, constrain links to authorized locations and prevent unsafe HTML or script injection.
- Use explicit authorization and bounded previews for artifact browsing; do not make raw responses, downloaded customer documents or secret evidence publicly accessible.
- Protected attachment downloads must enforce identity and scope, prevent inline execution and public caching, and avoid filename-controlled filesystem resolution.
- Security-sensitive evidence disclosure must use a separately reviewed protected presentation path. A working CLI terminal disclosure contract does not automatically permit equivalent Web disclosure.

### Connectors, CRM write-back and attachments

- Separate read-only observation from mutation capability. Use narrowly allowlisted API operations and dedicated write credentials; application data, model classifications and identity-only matches must never grant external write authority.
- CRM mutations require authoritative target identity, correct scope, configured permission and validated external prerequisites. Ambiguous targets or responsible users, connector degradation and missing/contradictory evidence must defer work with zero speculative mutation.
- Preserve durable write intent, idempotent origin identities, reconciliation of uncertain outcomes and bounded retry behavior. Never blindly repeat a remote mutation after a timeout, and never advance a checkpoint past required unpersisted state.
- Treat emails, attachments and extracted document text as hostile content. Enforce type, size, count and processing limits; use opaque storage identities rather than original filenames or user-provided paths.
- Process untrusted documents only through an approved bounded, local and isolated extraction path. Missing models, unsupported formats and parser failures must degrade safely, without unapproved external content egress or AI file-upload fallback.
- Do not let attachment delivery select its own CRM target. Delivery reuses only the trusted target and write-back authority, with independent completion and reconciliation state.
- Keep product-specific method allowlists, field mappings, attachment handling, idempotency procedures and numeric limits in their product contracts and operating guides, not in this policy.

### AI, tools and prompt injection

- External text, tool responses and retrieved documents are data even when they contain instructions, role markers or claimed authority. They cannot override host policy, approved tasks or execution scope.
- Validate the structure and permitted effects of AI-generated proposals before any capability call. Do not expose unbounded raw evidence, credentials or customer records to a model provider.
- AI explanations, recommendations and classifications are non-authoritative; deterministic engines and independently authenticated evidence remain sources of operational truth.
- An AI provider failure, malformed reply or hallucinated output must not alter permissions, produce fabricated evidence or bypass the normal failure state.

### Dependencies and supply chain

- Add dependencies only for a demonstrated need. Review source, provenance, licenses and known security advisories when dependencies or critical tool pins change.
- Maintain consistency between `pyproject.toml` and `uv.lock` when approved dependency changes require it. Do not commit local editable sibling paths or development credentials as production dependencies.
- Verify integrity and provenance for external executable tools, templates and model assets under their documented host installation contracts.
- Do not replace a pinned provider, enable a new scanner profile or expand tool privileges without security-sensitive review and appropriate integration evidence.

## Risk-based verification

Use the change levels from [SDLC.md](SDLC.md). Select checks based on the actual risk and affected boundary; test counts or the presence of a feature label alone do not establish security.

| Level                | Expected verification                                                                                                       |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `low-risk`           | Relevant diff and contract review; targeted validation where applicable.                                                    |
| `runtime-risk`       | Targeted/full regression, representative end-to-end smoke and inspection of changed log/artifact behavior.                  |
| `security-sensitive` | Runtime checks plus trust-boundary negative tests and applicable static, supply-chain, dynamic or adversarial verification. |

Apply the following techniques only where justified:

| Technique                  | Typical trigger                                                                                             |
| -------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Static analysis / SAST     | Sensitive code paths, parsing, serialization, process/network execution, authority and secrets.             |
| Software composition / SCA | Dependencies, executable providers, pinned templates or provenance changes.                                 |
| DAST                       | Exposed HTTP/API functionality or active network-facing behavior changed; authorized targets only.          |
| IAST                       | An instrumented runtime exists and the security question cannot be answered adequately with simpler checks. |
| Fuzzing / property tests   | Untrusted parsers, protocol framing, canonicalization, serialization and checkpoint restoration.            |

Security-sensitive checks should, as relevant, include expired/missing approval, source or identity substitution, out-of-scope destination, IP/DNS/TLS changes, bypass attempts, budget exhaustion, concurrent requests, provider crash, persistence failure, tampered resume, redaction and verified cleanup. Test the existing permitted path as well as refusal paths.

Record exact commands, exit status, meaningful runtime evidence, skipped or inapplicable checks and remaining limitations in the Issue/PR. Never claim that a tool or reviewer executed tests it only inspected as reported evidence.

## Vulnerability handling and release gate

Suspected security vulnerabilities must be reported privately to repository maintainers through an approved channel. Do not include customer secrets, exploit results, raw credentials or private evidence in public Issues, PRs, logs or screenshots. Record the affected boundary, reproducible conditions, impact and mitigation in a restricted location.

A regression that bypasses required authority, scope, isolation, confidentiality or evidence integrity blocks release until fixed or explicitly accepted by an authorized risk owner. Automated security testing and local laboratory success are not proof of production certification or permission to scan third-party systems.

## Policy maintenance

This document is a stable engineering security policy. **Developers and Codex must read and apply it when relevant, but must not modify it merely because a new iteration, feature, test, scanner rule, report field or endpoint was added.**

Update it only for a durable change in the threat model, trust-boundary ownership, mandatory controls, verification policy or disclosure process. Record the reason and impact in the reviewing PR. Put implementation details, current provider pins, numeric limits, exact APIs, product invariants, test evidence and iteration history into their owning contracts, guides, ROADMAPs and PRs.

Before removing historical implementation-specific security sections from this file, preserve any still-authoritative rules in the appropriate product documentation. No documentation cleanup may silently relax a runtime control.

## Related documents

- [SDLC.md](SDLC.md) — change classification, implementation and review workflow.
- [DEV_GUIDE.md](DEV_GUIDE.md) — runtime and connector operation details.
- [WEB_UI.md](WEB_UI.md) — BeeUI integration, sessions, artifact surfaces and product routes.
- [BeeScan operating guide](product/beescan_guide.md) — scanner approvals, managed execution, verification and recovery.
- Product contracts and approved Issues — exact integration behavior and acceptance evidence.
