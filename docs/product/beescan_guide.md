# BeeScan — Host Operating Guide

## Purpose

This is the operator and integration guide for running BeeScan through BeeAgent. It covers approved CLI workflows, configuration ownership, provider prerequisites, evidence and recovery. BeeScan supplies domain eligibility, proposals and normalized findings; BeeAgent alone authenticates the operator, authorizes target requests, executes providers, stores artifacts and verifies cleanup.

This guide is the single owner of BeeAgent-specific BeeScan operation: [adaptive investigation and Case resume](#adaptive-investigation-and-case-resume), [diagnostic disclosure](#diagnostic-disclosure-and-protected-output) and [governed DAST](#governed-dast-zap-rule-6). Domain schemas are defined by the separate BeeScan repository in `docs/DATA_MODEL.md` and `docs/DAST.md`; host security policy lives in [SECURITY.md](../SECURITY.md).

## Before an assessment

1. Obtain explicit current authorization from the target owner or the applicable program. Specify exact target origin/IP/port, allowed methods and capability profiles, exclusions, validity, operator identity, request/time ceilings and any required approval for active testing. Local laboratory fixtures and a local OS identity do not authorize external targets.
2. Verify the selected module and appropriate optional `beescan` dependency are installed from the reviewed source. A local editable source is permitted only for the validated trusted-development boundary; it cannot be reported as an immutable production release.
3. Configure the corresponding feature and independent approval in protected `config/settings.yml`; secrets belong in environment, not YAML, task text, logs or artifacts. `beescan.investigation.trusted_local_enabled` authorizes only the local invocation boundary, not independent DAST permission.
4. Verify provider pin, managed egress prerequisites, current DNS and exact destination, TLS, worker isolation and budget before active execution. Refuse when mandatory enforcement cannot be established.
5. Use the supported `./start.sh beescan` command; inspect the actual final status and run artifacts. Do not treat a scanner alert, exit 0 or report presence as independent proof of vulnerability impact.

Relevant settings live under `modules.registry[].id: beescan`, `beescan.probe_enabled`, `beescan.approval`, `beescan.detection_enabled`, `beescan.detection_approval`, `beescan.git_exposure_enabled`, `beescan.git_exposure_approval`, `beescan.investigation` and `beescan.dast`. The tracked working-tree values are not a grant for another operator or machine; read and validate the actual settings before each run. `config/start.py` is the host CLI entrypoint.

## CLI

```bash
# Local interactive intake (TTY required)
./start.sh beescan

# General authorized investigation: target must be a permitted HTTP(S) origin
./start.sh beescan investigate \
  --target https://authorized.example \
  --task 'Investigate supported Web exposures'

# Bounded adaptive investigation family, when separately enabled
./start.sh beescan investigate --adaptive \
  --target https://authorized.example \
  --task 'Investigate supported disclosures field=APP_TOKEN'

# Inspect a saved Case without sending target requests
./start.sh beescan investigate --inspect <case_id>

# Continue under fresh current authority
./start.sh beescan investigate --resume <case_id> \
  --task 'Continue the authorized investigation'

# Explicit legacy file mode with its independent approval
./start.sh beescan investigate TASK.json

# Bounded host assessments, only when enabled and approved
./start.sh beescan bootstrap
./start.sh beescan probe
./start.sh beescan detect
./start.sh beescan assess --http-signals
./start.sh beescan assess --http-signals --git-exposure
```

These examples show syntax, not permission. Interactive intake requires a real terminal; invalid combinations, duplicate flags, unsupported URLs and non-TTY interactive invocation are rejected. Task-file mode requires protected file ownership/mode, bounded JSON and exact independent approval. Direct/interactive mode is authorized through the actual trusted local process context and configured controls; those controls cannot be reconstructed from Web, AI, caller-provided fields or imported JSON.

## Authorization modes

| Mode                             | Additional control                                                                                            | What it can do                                                                                                 |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `bootstrap`                      | Valid module/dependency metadata                                                                              | Check module contract and selected providers without active target traffic                                     |
| `probe` / `detect` / `assess`    | Each operation's explicit approval, source identity, provider pin and budget                                  | Run only its fixed scoped HTTP/detection/reporting flow                                                        |
| `investigate TASK.json`          | Independent legacy `beescan.investigation.enabled` and approval, protected task file                          | Execute its supported scoped task path                                                                         |
| Interactive/direct `investigate` | `trusted_local_enabled`, current host operator/process identity, approved reachable target and bounded policy | Run supported local operator investigation within the host's fixed request/capture rules                       |
| `investigate --adaptive`         | Enabled adaptive investigation profile and approved task family                                               | Select between existing supported bounded disclosure families                                                  |
| Discovery-to-DAST                | Separate `beescan.dast` active approval with `entry_selection: authenticated_discovery`                       | Select at most one authenticated GET entry, then execute the explicitly approved bounded profile if all active gates pass |
| Direct DAST                      | Separate active approval with `entry_selection: exact_entry` (default when omitted)                           | Use exactly the preapproved bounded parameter entry                                                            |

A successful discovery of an endpoint or query parameter is not DAST authorization. `authenticated_discovery` requires an empty approved `entries` list and `max_candidates: 1`; `exact_entry` requires the one operator-approved relative entry. DAST approval has its own transport binding, `approved: true`, `method: active_dast`, allowed origin/IP, current validity and request/time limits. AI/task text and other module approvals cannot upgrade it.

## Web investigation setup

Open `/beescan` after starting `./start.sh web`. The console reuses BeeUI sessions, generic forms, CSRF-protected actions and the existing BeeAgent investigation; it never borrows the trusted-local CLI operator. Enable `web.auth`, configure the intended principal with resource scope `beescan` and execution scope `beescan.investigate` and an operator/admin role, then explicitly list its canonical principal ID under the following optional configuration:

```yaml
beescan:
  investigation:
    web:
      enabled: true
      principal_ids: [operator]
```

This fragment does not replace the existing investigation settings. Enable `beescan.investigation.enabled`, configure its full independent `approval` with the existing transport/Scope/Mission/Target, destination, current validity and provider limits, and configure `adaptive.max_steps`, `max_requests` and `max_depth`. Keep the BeeScan module enabled and satisfy its normal provider, AI-profile validation and managed-egress prerequisites. Omitted Web configuration grants no Web execution; malformed or incompletely enabled settings fail validation. Principal membership, resource/execution scopes and target approval are separate requirements, including for an admin wildcard.

The standard BeeUI adapter page uses canonical Investigation/Исследование and Results/Результаты tabs with the same width and navigation behavior as ROP. Investigation shows Cases/Кейсы with compact owned search, the factual conversation and read-only Context. Use New Case, edit Task and the inline Target, select Quick/Standard/Deep with the radio-button group, then send with the icon or Enter in Task. Shift+Enter adds a newline; IME composition does not submit. The Target input is text presentation only: BS-16 still accepts only an approved HTTP(S) origin, with an explicit localized refusal for unsupported identity types. Photo/files, Import and Export in the three-dot menu are disabled and have no execution handlers. Search and tab transitions retain the selected authorized Case and locale; Results shows saved findings, report summary and evidence references without BS-17 review actions. Context and protected status polling show actual saved evidence, with missing usage explicitly unavailable. Quick, Standard and Deep restrict existing general investigation to at most 2/2/1, 8/8/3 and 16/20/4 steps/requests/depth, further limited by the configured ceilings. The effective configured Target, Scope, Mission and validity are visible. Task text, depth or successful authentication never grants target authorization. Path Traversal additionally requires current separate `beescan.dast` approval with `entry_selection: authenticated_discovery`; keep its existing enablement and runtime prerequisites, including the current DAST configuration's `trusted_local_enabled` gate. This flag does not turn a Web principal into a CLI operator.

Use Refresh or `GET /api/beescan/status?run_id=<run_id>` to inspect genuine saved progress. Read-only inspection and report viewing generate no target traffic and no Case writes. The workspace displays safe metadata and report summaries; raw response content and protected terminal-only values remain unavailable. Findings remain candidates requiring independent verification. Only signed Web-owned Cases appear; generic run/artifact routes cannot disclose BeeScan resources or unowned historical CLI Cases.

Resume automatically submits the original Target, Task and mode from signed host intake metadata; the operator does not reconstruct them. It still requires the same approved BeeScan configuration and principal, current authority and an authenticated compatible checkpoint. For a different objective, use New Case. A Case with multiple segments remains one conversation/history entry. Older Web Cases without authenticated intake display an unavailable state and cannot use automatic Resume. Completed sufficient work is reused without new target requests. Pending, changed or corrupted state refuses rather than silently restarting. An accepted nonce cannot be replayed, and only one Web action executes per storage root. Keep the configured Web session secret stable and protected across restarts to preserve ownership authentication; rotating it invalidates old Web ownership signatures. Case schema and CLI Inspect behavior are unchanged.

## Native providers and supply-chain controls

BeeAgent provisions or verifies selected providers under the protected user-local `$HOME/.local/share/beeagent/beescan-providers` directory. Provider downloads/installation are not target execution permission. The managed directory must be owned by the operator, protected against group/world writes and symlink replacement; installed bytes are rehashed and compared with the reviewed pins. Corrupt or unavailable providers fail closed rather than silently upgrading or substituting executables.

| Provider                        | Reviewed profile and integrity boundary                                                                                                                                                                                                                                                            |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| HTTP probe (`httpx`)            | ProjectDiscovery HTTPX 1.12.0 static Linux amd64 rebuild, SHA-256 `bb28edc87dfd8b11f25ebb73b325f05424e8ee2dd5c818649f1f7d28da6a32b5`, 58,029,060 bytes; upstream source revision `4b6a9a9d476f94a4f3a630f37051f5671ecfb1f8` and Go 1.27.2. Not interchangeable with the older upstream executable. |
| Restricted detection (`nuclei`) | Pinned v3.11.1 Linux amd64 executable SHA-256 `c49588140f357cbdddd5436dec11201953a4c5390faeec90777f9ee2cfd70251` and fixed `beescan-http-marker` template/version/digest, verified before use.                                                                                                     |
| Managed egress (`pasta`)        | Reviewed Ubuntu `passt` package version `0.0~git20260120.386b5f5-1`, executable SHA-256 `a10789852407f65160c4abfac002efe511b254e6ab2cbfc658e807575db44832`; exact protected helper and rootless network namespace only.                                                                            |
| Active DAST (`ZAP`)             | Pinned ZAP 2.17.0 Core ZIP and selected add-on digests, Java 25 and the allowlisted `rule6-v1` / `traversal-nonrecursive-v1` profiles; complete allowlist and resource/security qualification live in [governed DAST](#governed-dast-zap-rule-6).                                                                                      |

If the reviewed HTTPX executable must be rebuilt for local qualification, use only the exact upstream source commit above and the independently verified Go 1.27.2 Linux amd64 toolchain. The source archive SHA-256 is `959865e9d608ce8a7507e46d0d399e92ba1e1de7b4f9ccd00678ebe2cf953f72`; the Go distribution SHA-256 is `ecbadb99091a3f46e31f5f934b068b1864eafa7995211b39eaddf76996045fe5`. Do not edit source, `go.mod` or `go.sum` during the reproducibility check:

```bash
CGO_ENABLED=0 GOTOOLCHAIN=local /absolute/path/to/go1.27.2/bin/go build \
  -trimpath -buildvcs=false -ldflags=-w -o /absolute/path/to/httpx ./cmd/httpx
chmod 0555 /absolute/path/to/httpx
sha256sum /absolute/path/to/httpx
```

The output must match the exact pinned digest and byte size above; otherwise it is **not** the approved provider. A local rebuild is not a published immutable release asset.

The exact custom HTTPX rebuild had no reviewed immutable release asset in the recorded distribution audit; automatic preparation of the other providers does not make HTTPX zero-touch installation available. Until an approved immutable release and manifest exist, an operator must provision the exact verified binary. Do not download a nearby upstream version or rebuild provider code at startup to bypass a missing pin. An approved release process may change pins only with fresh integrity, SCA and kernel/target acceptance evidence.

The recorded HTTPX qualification replaced the older Go 1.26.0 binary after inspecting TLS, certificate, DNS, URL and HTTP parser paths. The reviewed Go 1.27.2 rebuild removed matching standard-library advisories; remaining dependency-level OSV matches involved HTTP/2 and Goldmark, whose triggering paths were excluded under the fixed HTTP/1.1/no-update/no-rendering host profile. This is a profile-specific reachability disposition, not a claim that the dependencies contain no vulnerable code.

The Nuclei v3.11.1 release qualification inspected Go 1.26.5 and its bundled dependencies: seven affected component versions with 38 OSV IDs/aliases were identified. The allowed offline marker profile receives only a host-sanitized bounded HTTP/1.1 representation, with no network, downloaded templates, Git repository operations, gRPC/SSH/OpenPGP traffic or arbitrary Unicode/raw headers. The threat-specific review considered standard library, `x/net`, `go-git`, `x/mod`, `x/crypto`, `x/text` and `grpc` matches; these are **not** generalized waivers for a future scanner profile. Preserve release/build-info, vulnerability inventory and exact-profile test evidence in the release/security review record. A different provider binary or input channel requires renewed analysis, not reuse of the historical disposition.

Pinned packages and providers can still contain advisories. Historical SCA dispositions apply only to the reviewed byte digest and limited scanner/capture dataflow, not arbitrary flags or broader input channels. A new provider, add-on, input path, network permission, response forwarding behavior or resource limit requires renewed risk review. The ZAP advisory analysis and residual risk are separately recorded in [governed DAST](#governed-dast-zap-rule-6). No claim of universal CVE-free operation follows from these pins.

## Network, isolation and accounting

The host owns exact operator/Scope/Mission/Target binding and checks it against the current validity window and connected destination. DNS is resolved and rechecked against the approved address; Host/SNI and TLS certificate must match the approved HTTPS origin. A new DNS answer, redirect, proxy, callback, alternate address, method or expired approval cannot expand authority.

The managed Linux path requires usable rootless user/network namespaces, Bubblewrap, nftables, nsenter, iproute2, prlimit and pinned pasta. In managed mode the approved namespace pair is `/beeagent-managed/ns/net` plus `/beeagent-managed/ns/user`; legacy `/proc/<pid>/ns/*` approvals are an explicitly separate path. An approved kernel-level fixture exception (e.g., loopback alias/test CA) must never leak into production policies.

Real request accounting belongs to the host, not to scanner progress. Capture workers operate within the approved destination and one-shot/budgeted request shapes. Nuclei receives only the synthetic bounded offline HTTP result, not arbitrary raw network access. ZAP runs in a separate networkless sandbox and sends mediated requests over a private UNIX socket: the host reserves a shared request slot before a target request and refuses unsafe framing, non-GET methods, foreign origins and redirections. The original egress firewall alone is _not_ an HTTP request counter. See [DAST mediation and request accounting](#dast-mediation-and-request-accounting) for hard-cap and concurrency guarantees.

Source bodies, error excerpts and credential-bearing values remain transient or use reviewed protected presentations only. Execution and cleanup run under resource and time limits; failed, timed-out or interrupted workers are killed/reaped, and any inability to verify closed enforcement prevents a successful terminal status. No fallback from a failed capability to unrestricted network access is permitted.

## Evidence, Cases and reports

The main evidence root is `storage/runs/<run_id>/module-beescan/` with parent status/report and bounded child/source artifacts. Depending on the selected workflow, an assessment may contain `http_probe_status.json`, `http_observation.json`, `investigation_status.json`, `investigation_steps.json`, `investigation_sources.json`, `case.json`, `case_report.json`, `case_report.md`, `egress_lifecycle.json`, `dast_execution_status.json`, `dast_evidence.json`, `dast_handoff.json`, `report.json` and `report.md`. Files are written through protected host interfaces, fsynced/read back as required and matched to the original run/child/source identities.

- Actual capture facts and evidence identity must be independently authenticated before BeeScan normalizes a result. A result hash only binds bytes; it is not host authority or independent vulnerability verification.
- DAST `CANDIDATE` requires a completed, covered execution with accepted match evidence; `NO_MATCH` requires independently established complete coverage. Timeout, missing coverage, changed source or unverified cleanup must be `PARTIAL`, `ERROR` or an explicit refusal as appropriate. ZAP progress `100` alone cannot prove negative coverage.
- `FindingStatus.CANDIDATE` is not human-reviewed `VERIFIED`. No auto-generated Bug Bounty submission or claimed impact is allowed without independent human verification.
- Reports and ordinary Case/JSON/Markdown projections include only allowlisted, bounded metadata and opaque evidence IDs. No raw HTTP bodies, cookies, full parameter values, scanner databases, sensitive configuration values or credentials.
- A Case can be inspected without sending target traffic. Resume requires fresh authorization, same target/objective/Scope/Mission identity and independently validated saved source and lifecycle evidence. Completed sufficient actions are reused; tampered, foreign, pending or incomplete checkpoints fail closed or need a separately approved fresh run. Existing historical Case schemas remain inspectable where supported.

A sensitive diagnostic value can be displayed only through the reviewed trusted foreground local-terminal boundary after authentication, cleanup and final artifact publication. It must never appear in generic stdout JSON, reports, Web UI, logs or AI context. See [diagnostic disclosure](#diagnostic-disclosure-and-protected-output).

## Adaptive investigation and Case resume

The regular `investigate --target ... --task ...` path uses bounded general Web discovery. The `--adaptive` switch is a separate compatible decision mode for the supported framework/disclosure and diagnostic-disclosure families. Neither mode authorizes a new target, action, provider or permission merely because AI proposes it. The explicit `beescan.investigation.adaptive.enabled` flag controls the bounded adaptive mode. `max_steps` and `max_requests` are required integers from 1 through 32; general discovery also uses `max_depth` from 1 through 7. The configured investigation timeout covers the entire segment, including bounded AI interpretation. Current settings, operator/process authority, module availability, selected capability, destination, DNS/TLS and managed egress are rechecked at each action and on resume.

```bash
./start.sh beescan investigate --adaptive --target https://authorized.example --task 'Investigate supported disclosures field=APP_TOKEN'
./start.sh beescan investigate --target https://authorized.example --task 'Investigate supported Web exposures'
./start.sh beescan investigate --inspect CASE_ID
./start.sh beescan investigate --resume CASE_ID --task 'Continue the authorized investigation'
```

- The adaptive family obtains a governed GET `/` and authenticates the redacted source before BeeScan proposes a bounded next action. AI sees only the operator task and returns a constrained objective enum; it cannot choose an executable URL, method, payload, budget or permission. Each supported family authenticates its own source; one family's `WebResponseFacts` or `InvestigationIntent` cannot be relabeled for another. A full framework-and-diagnostic adaptive sequence uses at most six attempted target requests, subject to stricter host limits; negative or inconclusive checks may lead to another eligible supported action.
- General discovery also begins with GET `/` and considers authenticated same-origin links, comments, forms, metadata, robots/sitemap and bounded text/resource proposals. Derived resources remain candidates until captured and authenticated. `max_depth`, `max_steps` and `max_requests` bound discovery. The host alone decides whether a proposal is executable within the current approval.
- A Case retains one stable `case_id` and no more than eight explicitly requested segments. Each segment has a separate parent run; each action and capture retains its original domain run, child, request, response, source and opaque evidence identities. Case state lives at `storage/runs/<case_id>/module-beescan/case.json`; action records use `case_action_<family>.json`; `case_report.json` and `case_report.md` contain bounded status, metrics, evidence references, limitations and next actions.
- Stored checkpoint contracts are versioned: adaptive Case schema 1; general investigation schema 2; direct DAST schema 3; unified discovery-to-DAST schema 4. Compatibility readers must validate the applicable schema, not silently reinterpret old records. An older adaptive checkpoint without an opaque action identity may be inspected but must not supply a reusable completion.
- Case publication uses allowlisted schemas, canonical SHA-256 state digests, owner-checked no-follow directory locking, private `AssessmentSnapshot`, fsync/atomic write and read-back. Loading checks exact Scope, Mission, target, original source/request/response/evidence identities, completed action records, status markers, and `egress_lifecycle.json` with closed enforcement and verified cleanup. A digest detects changed bytes but is **not** a signature against a malicious trusted OS account.
- `--inspect` sends no target requests. `--resume` requires new current authority and a newly validated destination; it does not inherit prior permission. Changed objective, requested field, dependency identity, connected destination, source or previously selected resource stops reuse. An action/resource mismatch produces `evidence_not_equivalent`; open a fresh authorized Case instead of rebinding prior evidence.
- Only completed, sufficient and authenticated MATCH/NO_MATCH actions are reusable. A controlled interrupted action with verified cleanup may be recaptured under a newly approved segment; abrupt process death leaves a pending checkpoint and refuses automatic recovery. Completed MATCH is terminal and never replays a plaintext secret. Resume cannot infer success from partial Case records or orphan evidence.
- `adaptive-redacted-v1` stores metadata-only source facts, opaque references and a run-private HMAC commitment; no raw body, links, excerpts or disclosed secrets. The HMAC is a within-run provenance commitment, not a portable signature. `debug-redacted-v1` follows the additional confidentiality rules below. Metrics retain actual attempted requests, capture launches, elapsed time and AI calls across segments, with exactness flags. When model usage is not available, token/cost fields remain null with `usage_status=unavailable`.
- Distinguish MATCH, NO_MATCH, INCONCLUSIVE, REFUSED, TIMEOUT and ERROR. No outcome proves that the entire target is secure, that a human verified a vulnerability, or that third-party authorization was established.

## Diagnostic disclosure and protected output

A diagnostic-disclosure investigation may request one exact configuration-field identifier from the operator's **original** task. Explicit case-sensitive `field=IDENTIFIER` is authoritative and accepts `[A-Za-z_][A-Za-z0-9_]{0,63}`. The standalone uppercase form `[A-Z_][A-Z0-9_]{1,63}` is permitted only when unambiguous; optional punctuation/quotes do not turn multiple names into one. Missing, ambiguous, malformed or repeated identifiers fail closed. The AI classifies the supported task family only; it cannot select the requested field, request path, HTTP method or authorization.

```bash
./start.sh beescan
./start.sh beescan investigate --target https://authorized.example --task 'Find the diagnostic disclosure field=APP_TOKEN'
./start.sh beescan investigate TASK.json
```

Direct/interactive calls require actual trusted-local OS/process context and `trusted_local_enabled`; the independent task-file approval remains mandatory for file mode. Task-file terminal disclosure additionally needs a valid local-operator context. The configured investigation approval may permit three requests, but this immutable diagnostic family permits **at most two same-origin GETs**: GET `/` and at most one resource selected from authenticated bounded HTML comments. Ordinary links, unsafe/traversal/query-bearing paths, missing or ambiguous comment resources cannot trigger a second request; baseline/mutation requests are not performed. Unsupported or ambiguous task classification ends as `unsupported_investigation_task` with zero target captures. The bounded reason `response_json_status_404` describes the specific unsupported JSON/404 response and must not be interpreted as proof of disclosure.

The host preserves exact IP/port, Host/SNI, system TLS certificate validation, DNS membership, no-redirect, process/resource ceilings, start/attempt accounting, live settings reload, managed namespace/firewall and verifiable cleanup. BeeScan alone applies the field/value association grammar and candidate semantics. `NO_MATCH` is limited to the bounded representation requested; it does not prove absence of other exposures. A finding remains `CANDIDATE`, never automatically `VERIFIED`.

Both discovery and diagnostic response bodies remain transient. Before persistence, `debug-redacted-v1` keeps only allowlisted parent/child/request/response IDs, dependency provenance, metadata-only facts and a run-private HMAC commitment across authenticated capture and evidence identities. Raw response content, HTML comments, path links, field values, excerpts and sensitive query values are absent from stored child records, reports, stdout JSON, Web UI and AI inputs. The random HMAC key stays in process memory and is not persisted; its tag does not provide independent verification after the run or defend against a malicious operator sharing the OS account.

**Sensitive terminal output has an additional gate.** The exact requested value may be written directly to the trusted local terminal only after source authentication, managed-egress enforcement and verified process cleanup, final status/report persistence and read-back, and renewed current authorization. All three standard descriptors must be TTYs for the same device; the terminal descriptor must be owner-matching and no-follow, and the caller must hold the foreground controlling process group. Non-TTY/redirected/background execution, cancellation, inconsistent source evidence, failed publication or unverifiable cleanup suppresses the value, even if the non-sensitive MATCH status can still be reported. Terminal recordings, screenshots, same-account debugging and lingering process memory remain outside this confidentiality guarantee.

**Dependency provenance is distinct from target authority.** A reviewed locked Git installation can establish immutable production provenance (`COMPLETE`) or an explicitly approved test-only `LABORATORY_ONLY` run; local sibling editable installation may be accepted by the exact trusted-development gate as `LOCAL_EDITABLE` (global target) or `LABORATORY_ONLY` (approved private target). Neither editable state proves an immutable release or third-party engagement consent. For the explicitly selected `beescan = { path = "../beescan", editable = true }` source, the bootstrap verifies the expected sibling `/home/bee/Pro/beescan`, installed editable origin and package contract before host execution; it must fail if the exact path/source check does not hold. These local paths are environment-specific policy, not general package-install guidance.

Relevant controlled tests are `tests/test_beescan_debug_disclosure.py`, `integration_tests/test_beescan_debug_lab.py`, `tests/test_beescan_adaptive.py` and `integration_tests/test_beescan_adaptive_lab.py`. The real laboratory uses pinned provider variables, explicit loopback fixture mapping and a test CA; AI interpretation may be substituted, but actual containment, request accounting, storage, cleanup and TTY refusal must still be exercised. Fixture success is not fresh public-target authorization or hosted-CI evidence.

## Governed DAST (ZAP rule 6)

The legacy active profile is ZAP Path Traversal **rule 6**, with provider `zap`, version `2.17.0`, profile `rule6-v1`. The additional allowlisted `traversal-nonrecursive-v1` profile uses the same pinned provider, isolation and mediated execution boundary with a fixed verification technique. The public offline typed DAST normalization belongs to BeeScan `beescan.capabilities.dast`; BeeAgent owns active execution, fresh authorization, provider verification, HTTP mediation, evidence authentication, storage and cleanup. Automated findings remain candidates pending separate review.

### DAST provider qualification and isolation

The pinned [ZAP 2.17.0 Core ZIP](https://github.com/zaproxy/zaproxy/releases/tag/v2.17.0) is **108340737 bytes** with SHA-256 `0cb73b7f72d12c263fb61de304edb82a455d7aa4e1813c216c061765c306f5b7` (Apache-2.0). The effective selected add-on set is exactly bundled active rules **78**, `commonlib 1.39.0`, `network 0.25.0`, `database 0.9.0`, `oast 0.24.0`, `callhome 0.20.0` and `pscan 0.6.0`. Their authoritative per-file digest allowlist is `src/beeagent_module/integrations/beescan/dast_runner.py:ADDONS`; the ZIP and selected members are verified before snapshot/execution and all other add-ons removed. Do not substitute a newer package or add-on without independent requalification. The legacy worker disables all passive/active rules other than rule 6, fixes LOW/MEDIUM strength/threshold, waits for the asynchronous ZAP site cache and exposes no spider, AI flags, arbitrary scripts, callback routing or provider-selected destinations.

An enabled `beescan.dast` profile can provision/reuse the pinned provider archive even when `approval: null`; **provisioning is not permission to scan**. Linux x86_64 execution needs protected rootless Bubblewrap, nftables, reviewed pasta, managed namespaces and OpenJDK 25 at `/usr/lib/jvm/java-25-openjdk-amd64/bin/java`, with the expected read-only `/usr`, `/lib`, `/lib64` and Java configuration mounts. Unsupported or missing prerequisites refuse. ZAP has a separate networkless sandbox and can access only a private UNIX gate socket; no target network route, secrets, host settings, writable host mounts or persistent target capture database are exposed.

Fixed worker ceilings include a **256 MiB Java heap**, **64 MiB direct memory**, **4 GiB per-process address space**, **256 descriptors**, **16 MiB per file**, **128 MiB private `/tmp`**, bounded CPU and deadline, zero core dumps and **16 KiB projected output**. The host capture process retains its separate **64-descriptor/64 KiB** budget; transient upstream bodies are limited to **256 KiB** and the private ZAP API to **2 MiB**. These per-process limits are not a cgroup guarantee for aggregate resident memory. Timeout, missing setup, incomplete cleanup and sandbox enforcement failure never become completed success.

### DAST approval and execution

`config/settings.yml` owns the `beescan.dast` enablement and independent approval. The tracked `enabled` state alone is not authorization; `approval: null` blocks active execution. Approval must bind the trusted-local operator, the complete current `transport` policy (Project/Scope/Mission/Target, canonical HTTPS origin, exact connected IP/port, validity, exclusions and managed namespace pair), `approved: true`, `method: active_dast`, request budget **1–100**, deadline **10–60 seconds**, and the selected entry mode. `archive` may be omitted to use the exact managed pinned archive; a reviewed explicit absolute path remains available for legacy owner-provisioned deployments. No credential or sensitive query value belongs in settings.

- `entry_selection: exact_entry` (backward-compatible default): exactly one bounded printable-ASCII relative entry in `entries`, without fragment/backslash. It is not inferred from task text.
- `entry_selection: authenticated_discovery`: `entries: []` and `max_candidates: 1`. The host may select **at most one** GET entry from authenticated, source-bound Web discovery; form action and parameter identity must be unambiguous and supported by evidence. No invented parameter value, arbitrary target guessing, cross-origin expansion or broader scanner profile is permitted.
- Both modes require fresh host checks of original identity, current approval, source, destination, DNS/TLS, method, provider, budgets and Case state before each active request. `trusted_local_enabled`, `adaptive.enabled`, ordinary discovery approval, AI suggestions, a scanned URL or a scanner claim never substitute for active DAST approval.

```bash
./start.sh beescan investigate --target https://authorized.example --task 'Assess Path Traversal'
./start.sh beescan investigate --inspect CASE_ID
./start.sh beescan investigate --resume CASE_ID --task 'Assess Path Traversal'
```

Exact-entry DAST remains a separate compatible flow. The authenticated-discovery flow first collects source evidence, selects a supported bounded action through BeeScan, then starts the existing mediated provider with the explicitly approved profile only after renewed approval. Task-file DAST routing requires its own enablement. The active process uses `integrations/beescan/dast.py`, `dast_runner.py`, `dast_mediation.py`, `dast_socket_worker.py`, `dast_worker.py` and `discovery_dast.py`; no generic scanner executor or network path is added to BeeScan.

Case resume checks trusted-local OS/process operator context, current policy and a matching derived approval identity including entry selection and budgets. Sufficient completed stages are reused without new requests. A clean incomplete segment may be retried under newly verified authority within the eight-segment limit; pending, changed, foreign or unverified-cleanup checkpoints refuse. Persisted direct-DAST Case schema 3 and integrated discovery-to-DAST schema 4 remain distinct; schema 1/2 compatibility must not be broken.

### DAST mediation and request accounting

ManagedEgress is an IP/firewall restriction, **not** an HTTP request counter. ZAP has no direct target route; all requests pass through the host's private UNIX gate. BeeAgent terminates CONNECT/TLS, parses HTTP/1.1 using pinned h11, validates the requested origin and framing and **atomically reserves a shared run request slot before connecting or sending**. Each approved GET uses exact authorized address, DNS membership, TLS hostname/certificate and port. Non-GET, callbacks, direct/alternate destinations, redirects, bodies, authentication/cookies, transfer encoding, ambiguous or duplicate headers, upgrades, foreign authority and unsafe framing refuse. The host re-emits normalized bounded response metadata with a fresh `Content-Length`; target-controlled raw framing cannot pass through to the scanner. A fixed target does not become a positive finding merely because ZAP's progress reaches 100%.

The qualified enforcement tests demonstrate cap=1 on keep-alive, separate connections and concurrent clients without a second authorized target request. Headers from targets are bounded to **8 KiB** and transient response content to **256 KiB**; browser-state and credential data are not forwarded into the untrusted ZAP process. The private gate and connector inherit the separately authorized managed namespace, and scanner/connector isolation and cleanup are verified independently.

The normalized host handoff binds `DastIntent`, `DastExecution`, `DastEvidence` and untrusted `ScannerOutcome` to identical run/provider/profile/rule identities, exact request/response/artifact SHA-256 evidence and independently established coverage. Completed matches may become `CANDIDATE`; a `NO_MATCH` requires complete independently established requested-check coverage, not just scanner exit zero or ZAP progress 100. Missing coverage, budget/timeout, invalid timing or incomplete evidence yields `PARTIAL`; scanner crash/error or unverified cleanup yields `ERROR`. Invalid identity/evidence substitutions are rejected; the scanner never creates `VERIFIED`.

DAST stages persist allowlisted `egress_lifecycle.json`, `dast_execution_status.json`, `dast_evidence.json`, `dast_handoff.json`, `investigation_status.json`, `report.json` and `report.md` with original parent/child IDs, actual request counts, status codes, opaque references and digests. Arbitrary scanner text, raw HTTP bodies, headers, cookies, credentials, sensitive parameter values and ZAP database state are discarded. Publication verifies read-back and cleanup; abruptly interrupted setup/persistence remains pending.

### Non-recursive verification profile

Set the current active approval's `profile: traversal-nonrecursive-v1` explicitly, with `entry_selection: authenticated_discovery`, `entries: []` and `max_candidates: 1`. Omitting `profile` preserves `rule6-v1`, including its historical approval/action identities, exact-entry mode and LOW/MEDIUM settings. The new profile cannot inherit legacy approval or use an exact-entry task. BeeScan receives its qualified verification-role, Standard/Deep and typed fact metadata; this metadata never authorizes requests.

The new profile operates on the first parameter of one authenticated observed GET entry, retaining the endpoint, parameter ordering, other values and original source binding. It sends exactly five permitted GETs: the original baseline and two fixed positive/negative-control pairs at traversal depths two and six. The only positive resource is the Unix account-file signature; the negative resource is a fixed nonexistent control. No user-supplied payload, filename, wordlist, depth, scanner flag or arbitrary request API is exposed. Unsupported platform/depth/filter behavior is outside this bounded check's coverage.

Each upstream response in this profile is bounded to 256 KiB; the oracle accepts no more than 64 KiB and at most 256 complete account records. Larger proof responses cannot establish complete coverage. Legacy response limits remain unchanged.

The networkless worker uses the pinned ZAP `core/sendRequest` API with redirects disabled. Before target dispatch the host gate permits only the exact derived request targets and refuses repeats. The host verifies exact mediated request hashes, complete bounded responses, an ordinary HTTP-200 baseline without the oracle, and negative controls without the oracle. A positive oracle requires HTTP 200 and a complete bounded Unix account-file grammar with a root UID/GID-zero record; HTTP status, response length, reflection, scanner alerts and ZAP progress alone are insufficient. Oracle evaluation happens in the host on transient bytes already accepted by mediation, without persisting bodies or proof lines. Ambiguous baseline/control signatures suppress coverage and produce PARTIAL. Request exhaustion, failed execution and unverified cleanup cannot produce success.

New-profile `dast_evidence.json` uses schema 2 and adds at most five ordered `verification` facts containing only request/response digests, status code and an oracle boolean. Legacy evidence schema 1 remains unchanged. Existing typed DAST handoffs bind profile/rule/check and source identities; Case schema 4 remains compatible. Completed CANDIDATE/NO_MATCH stages are reusable from a fresh process under matching current approval; changed profile, source, action or evidence refuses reuse. NO_MATCH is limited to the five completed requests for this one selected check and never establishes target safety or VERIFIED status.

### DAST supply-chain risk and requalification

The ZAP 2.17.0 and selected-add-on SCA record identified real affected component versions, not a clean bill of health. The reviewed exact distribution includes **Commons Lang 2.6**, **Commons Configuration 1.10**, **Log4j 2.25.2**, **Jackson 2.19.1** in Database, and **Netty 4.1.100.Final**, **HttpClient 5.2.1**, **HttpCore/H2 5.2** in Network. The bounded review distinguished actually bundled classes from metadata-only JAR references; the latter do not prove vulnerable code absent. The consulted `h11 0.16.0` inventory had no OSV match _at the time of that review_.

Relevant recorded advisories include [GHSA-j288-q9x7-2f5v](https://github.com/advisories/GHSA-j288-q9x7-2f5v) (Commons Lang), [GHSA-3pjw-73gf-8qr5](https://github.com/advisories/GHSA-3pjw-73gf-8qr5) (Jackson), and [GHSA-38f8-5428-x5cv](https://github.com/advisories/GHSA-38f8-5428-x5cv), [GHSA-fghv-69vj-qj49](https://github.com/advisories/GHSA-fghv-69vj-qj49), [GHSA-hf6x-8p5f-cgmf](https://github.com/advisories/GHSA-hf6x-8p5f-cgmf) and [GHSA-hjcp-jmpx-g3qm](https://github.com/advisories/GHSA-hjcp-jmpx-g3qm) (network/HTTP dependencies). The reviewed rule-6 bytecode did not invoke the affected Commons Lang `ClassUtils` path or Jackson target-JSON deserialization; the private normalized loopback mediation excluded the specific target-controlled HTTP parsing and front-end/proxy differential prerequisites identified in that assessment. This is **GO only for the exact pinned, isolated rule-6 profile**, with residual scanner denial-of-service and unknown internal-reachability risk; it is neither a general ZAP permission nor a statement that no CVEs exist.

A change to the ZIP, add-ons, selected rule, target-to-scanner dataflow, response pass-through, proxy mode, mounts, Java/runtime limits, network route or authorization gate **invalidates the previous applicability decision** and requires a fresh component inventory, threat-specific SCA and real positive/fixed-negative request-cap and isolation acceptance before enablement.

### DAST regression and acceptance

```bash
BEEAGENT_BEESCAN_PASTA=/absolute/path/to/verified/pasta \
BEEAGENT_BEESCAN_LAB_PROVIDER=/absolute/path/to/verified/httpx \
BEEAGENT_BEESCAN_NUCLEI=/absolute/path/to/verified/nuclei \
BEEAGENT_ZAP_LAB_ROOT=/absolute/path/to/qualified/zap \
uv run --frozen --no-sync python -m pytest -q -s \
  integration_tests/test_beescan_egress_lab.py -k dast
```

This explicit laboratory exercises real pinned ZAP against independent vulnerable/fixed fixtures, concurrency/hard-cap accounting, HTTP framing, current approval, DNS/TLS, no target request on missing approval, evidence substitution, failure/timeout/cancellation, process cleanup, and inspect/resume. Fixture loopback mapping and CA trust are laboratory instrumentation only. The separate recorded authorized PortSwigger smoke yielded a candidate with six counted requests, exit 0 and verified cleanup under temporary 100-request/60-second approval; it was historical acceptance evidence, **not** permission for another target or a claim of comprehensive DAST coverage.

## Test and acceptance commands

Run normal selected-module unit/contract tests independently of native network acceptance:

```bash
uv run --frozen --extra beescan --extra beedrill pytest -q -rs
```

For active DAST, use the explicit laboratory command in [DAST regression and acceptance](#dast-regression-and-acceptance); do not treat a normal unit suite as proof of kernel-level mediation. The separately approved adaptive and diagnostic laboratories are listed in [Diagnostic disclosure and protected output](#diagnostic-disclosure-and-protected-output).

`integration_tests/` is not implied by the ordinary `tests/` suite. Explicit lab tests must exercise real isolation, supported positive/fixed negative behavior, request hard caps, incorrect/expired approvals, source substitution, DNS/TLS/framing refusal and cleanup. Required test setup failure is not an accepted skip or successful assessment.

For real external HTTPS acceptance, independently obtain current exact written/program permission and configure matching target, connected IP, operator UID, permitted methods/profiles, validity and budgets. Run only the approved check. Inspect actual exit code, parent/child status, independent evidence, real request count, `egress_lifecycle.json` with `state: closed`, `enforcement_verified: true` and `cleanup_verified: true`, verified process cleanup, and bounded reports. If permission or any prerequisite is missing, report **NOT VERIFIED** and send no requests. A passing fixture or a source import does not satisfy this gate.

## Failure and recovery

- Exit codes on supported assessment commands distinguish success, invalid CLI arguments, refusal, timeout and other errors/incomplete results. Check the specific subcommand's terminal status instead of assuming any file was successful.
- Refusal after changed approval, DNS, target identity, provider bytes, firewall, cleanup or storage verification is an intended security outcome. Do not add redirects, retries, proxy exceptions or alternate destinations to turn it into success.
- Inspect only safe status, allowed evidence metadata and logs. Correct the missing prerequisite or approval and start an independently authorized new attempt; never edit source artifacts, request counters, checkpoints or reports into `complete`.
- A managed provider may be repaired only through its reviewed provisioning path. An untrusted local replacement is not a compatible provider. Pair any changed public BeeScan domain contract with the host regression suite and a reviewed dependency update.
