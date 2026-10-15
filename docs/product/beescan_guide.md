# BeeScan host operating guide

## BS-1 laboratory execution

BeeScan 0.4.0 is an optional dependency, disabled in the tracked registry. Bootstrap keeps its READ_ONLY module contract and supports only `bootstrap_health`. The separate host command `./start.sh beescan probe` executes the one approved host Mission; it accepts no target, authority, provider or arbitrary payload arguments. Existing Solana dispatch and ROP/BeeDrill defaults are unchanged.

## Installation and approval

The optional `beescan` extra in `pyproject.toml` selects BeeScan 0.4.0 from `https://github.com/beesyst/beescan.git`; the Git source intentionally has no explicit `rev`. The reviewed It4 revision `ae1d1d07cf9d0e0fadd5fb9e4d8da71a4573eac2` is resolved and recorded in `uv.lock`, and frozen installation/export uses that exact commit with the existing BeeSDK 0.2.0 contract. The registry entry declares `install_extra: "beescan"`, so enabling it selects this extra through the standard runtime dependency synchronization. `./start.sh` uses exact `uv sync --frozen --no-dev` with enabled extras; manual wheel preservation and the BeeScan-specific `--inexact` workaround are unnecessary. The scanner executable remains separately provisioned and is never installed or downloaded by runtime.

In `config/settings.yml`, enable only the existing BeeScan registry entry to use `./start.sh beescan bootstrap`. Keep `beescan.probe_enabled: false` and `approval: null` for bootstrap. To authorize a laboratory probe, a trusted local operator edits the host settings, sets `probe_enabled: true` and supplies every approval field below. CLI/module payloads cannot change this binding. OS UID, current approval, exclusion, validity window, exact identity/profile and budgets are checked again immediately before execution; approval changes or disabling the module refuse. The expiry must accommodate the full request duration. Settings and runtime storage must remain writable only by trusted operators.

```yaml
beescan:
  probe_enabled: true
  approval:
    operator_uid: 1000
    project_id: project-lab
    scope_id: scope-lab
    mission_id: mission-lab
    target_id: target-lab
    origin: http://127.0.0.1:18080
    approved: true
    excluded: false
    valid_from: "2026-10-14T00:00:00+00:00"
    expires_at: "2026-10-15T00:00:00+00:00"
    method: http_probe
    request_budget: 1
    time_budget_seconds: 5
    connected_ip: 127.0.0.1
    allow_private_lab: true
    executable: /opt/beescan/httpx
    sha256: bb28edc87dfd8b11f25ebb73b325f05424e8ee2dd5c818649f1f7d28da6a32b5
    provider_version: "1.12.0"
    network_namespace: /proc/12345/ns/net
    user_namespace: /proc/12345/ns/user
    memory_mb: 2048
    output_bytes: 16384
```

The example UID, namespace PID and validity window must match the live operator/lab. Required fields have no hidden defaults. The only supported executable is the BS-1 Linux amd64 static rebuild of ProjectDiscovery httpx 1.12.0 from upstream commit `4b6a9a9d476f94a4f3a630f37051f5671ecfb1f8`, using Go 1.27.2 and the fixed executable digest above. This is a host-reviewed rebuild, not a newly published upstream release. The original Go 1.26.0 release executable with digest `6d78b83b4da452a7e0bd3613c4fae04cbf523209f083904b563f4d4406a680b0` is no longer accepted. Changing configured digest/version cannot select another provider. Provision and verify the rebuild before runtime; unsupported platforms, missing provider, integrity mismatch or unavailable isolation fail closed.

Use the exact source archive from `https://api.github.com/repos/projectdiscovery/httpx/tarball/4b6a9a9d476f94a4f3a630f37051f5671ecfb1f8` with SHA-256 `959865e9d608ce8a7507e46d0d399e92ba1e1de7b4f9ccd00678ebe2cf953f72`. Verify the official `go1.27.2.linux-amd64.tar.gz` against SHA-256 `ecbadb99091a3f46e31f5f934b068b1864eafa7995211b39eaddf76996045fe5` from [Go download metadata](https://go.dev/dl/?mode=json). Build in the extracted source directory without editing `go.mod`, `go.sum` or source files:

```bash
CGO_ENABLED=0 GOTOOLCHAIN=local /absolute/path/to/go1.27.2/bin/go build -trimpath -buildvcs=false -ldflags=-w -o /absolute/path/to/httpx ./cmd/httpx
chmod 0555 /absolute/path/to/httpx
sha256sum /absolute/path/to/httpx
```

The resulting SHA-256 must exactly match the approval/policy pin. Two independent output builds produced that digest; the executable is 58,029,060 bytes, within the existing 64 MiB bound. ELF symbols are retained for binary analysis; DWARF is omitted. The provider still reports its actual upstream version `v1.12.0`. No runtime installer, download, new provider arguments or relaxed integrity check is introduced.

## Network and process boundary

A trusted operator provisions a dedicated rootless user/network namespace. BeeAgent opens the configured namespace handles, checks the owning process UID, rejects its own namespaces and verifies the network namespace's owning user namespace with kernel ioctls. It retains those handles for every verification/execution command. The target may have exactly one approved A/AAAA address; missing, multiple or changed addresses refuse. DNS resolution is a bounded host subprocess and is repeated immediately before provider execution. The provider receives only a pinned `/etc/hosts` mapping; outgoing DNS/UDP and alternate connected destinations are blocked by the namespace firewall.

The complete nftables ruleset must be exactly one `inet beescan` table with the following output chain; replace the one IP and port with the approved endpoint. IPv6 uses `ip6 daddr`. No other tables, rules, sets, NAT or extra accept paths are permitted. Priority -150 follows conntrack's hook. The established-packet rule excludes initial SYN packets and permits response traffic; new connections remain limited to the exact approved IP/port.

```nft
 table inet beescan {
   chain output {
     type filter hook output priority -150; policy drop;
     ip daddr 127.0.0.1 tcp dport 18080 accept
     ct state established tcp flags & (syn | ack) != syn accept
   }
 }
```

Only the trusted namespace supervisor may retain network administration capabilities. The provider runs inside nested Bubblewrap user/PID/mount/IPC/UTS/cgroup namespaces with all capabilities dropped and further user namespaces disabled. It sees a verified copied executable, pinned hosts file, standard certificate store, isolated `/proc`, minimal devices and a private tmpfs. Host HOME, configuration, secrets, application storage and proxy environment are absent. There is no unrestricted fallback.

The fixed profile performs one HEAD request, one target, one thread and zero retries. Scheme fallback, redirects, HSTS following, CDN probing, cloud authentication, stdin and body decoding are disabled. Resource limits enforce address space, CPU, open descriptors, file size and wall time; stdout plus stderr are bounded. The host kills/reaps the process group on every exit, while the PID namespace and die-with-parent boundary prevent detached descendants from surviving the sandbox. Temporary executable/hosts snapshots and namespace descriptors are closed on every path. A caller cannot execute twice within the same run.

## Results and artifacts

Exit codes are 0 for successful complete execution, 2 for invalid CLI syntax, 3 for refused execution, 4 for timeout and 5 for error/incomplete invocation. Provider exit zero without valid bounded output is an error. A missing prerequisite, failed parse, timeout or cleanup/persistence failure cannot establish successful completion.

When present, provider `host` must be the approved canonical hostname without a port (the pinned httpx representation), and `host_ip` must exactly match the host-validated `connected_ip` passed separately to the parser. The separate provider `port` must match the approved port. Malformed types or contradictory destination metadata fail before successful facts, evidence or Observation are created; these optional provider fields never supply execution authority.

`storage/runs/<run_id>/module-beescan/` contains host-owned bootstrap artifacts or HTTP artifacts. HTTP success stores `http-evidence-<opaque-id>.json`, `http_observation.json` and `http_probe_status.json`, all with schema version 1. Facts contain only canonical origin, reachability, integer status, normalized media type, complete state, opaque evidence refs and host run/provider provenance. Mission/Target/capability identity comes from the approved intent; provider output cannot replace it. The capability result remains exactly `data={"evidence_refs": [...]}`. Failure status artifacts contain no success evidence or Observations. Consumers must require the final status artifact with `complete: true`; orphan evidence without that marker is incomplete. Raw bodies, headers, cookies, credentials, unrestricted scanner output and raw stderr are never persisted.

## Reproducible checks

Run the normal coordinated suite with `uv run --frozen --extra beescan --extra beedrill pytest -q -rs`; it discovers `tests/` through the existing pytest configuration and uses the full dev profile, including the existing local editable ROP source for maintainer regressions. BeeScan probe contract tests require the reviewed It4 API and fail clearly if it is missing or incompatible; they never skip on a missing package. The optional extra must be selected explicitly for these tests; plain `uv run` does not install optional BeeScan. The hosted core profile below excludes dev dependencies and does not need sibling checkouts.

The laboratory fixture is test-only and launches two synthetic loopback HTTP targets in a new rootless namespace. It never edits the host's settings or system network. After separately provisioning the pinned provider, run:

```bash
BEEAGENT_BEESCAN_LAB_PROVIDER=/absolute/path/to/verified/httpx uv run --frozen --extra beescan pytest -q -rs integration_tests/test_beescan_lab.py
```

The real kernel/network lab is a separate mandatory integration gate under `integration_tests/`, outside normal `tests/` discovery. It requires the explicit provider, compatible BeeScan It4, namespace creation, Bubblewrap, nsenter, nftables, iproute2 and prlimit; missing prerequisites fail the explicitly invoked gate instead of skipping. The fixture covers real 200/302, one-request accounting, zero forbidden redirect/proxy requests, direct allowed/forbidden IPv4/IPv6 connection attempts, timeout, malformed media type, oversized output, exclusion/expiry/operator/DNS/provider/isolation refusals, refusal after firewall removal and artifact leakage checks. Unit tests additionally cover contradictory input origin/port/path, schema/provenance handoff, live approval/DNS changes, subprocess cleanup errors and one-shot caller budgets. Tests are evidence of specific scenarios, not a blanket production security certification.

## CI and delivery gates

The GitHub workflow pins checkout/setup-uv actions and uv 0.11.26, uses Python 3.14 and read-only repository permissions, exports frozen dependencies with `--no-dev --extra beescan --no-emit-project --no-hashes`, installs them plus pytest 9.1.1 and BeeAgent, then runs an explicit core suite before building. The exported BeeScan source contains the exact reviewed Git revision from `uv.lock`. The core subset includes module contracts/registry/runtime, host context/artifacts/capability boundaries and all BeeScan probe contract tests, which fail if the package is missing. This profile needs no sibling BeeScan/ROP checkout, local secrets or scanner executable and is deliberately not the full suite. Full coordinated BeeScan/ROP/BeeDrill regressions and the explicit authorized laboratory gate run separately. Hosted PR CI cannot be declared green until its actual GitHub execution is confirmed.

BeeScan's Git source repository is private. The current workflow requires the `BEESCAN_READ_TOKEN` secret and configures Git access through `gh auth setup-git`; a cold installation still requires that secret to be present and authorized. A credential-free clean installation remains blocked. An isolated core run using already verified cached dependencies proves test/profile compatibility but does not prove hosted access to that private source. The delivery setup must resolve repository read access before hosted CI can be declared ready.

The provider SCA applicability review below applies only to this exact digest and fixed host profile. It does not approve arbitrary httpx flags or claim that every embedded dependency is vulnerability-free. BeeScan It4 is available from its locked Git revision; hosted PR CI and final read-only review remain separate delivery gates, and their delivery status is tracked separately in [the product roadmap](beescan_roadmap.md).

## Provider SCA applicability and replacement

The original executable was built with Go 1.26.0, `CGO_ENABLED=0`, Linux amd64 and stripped ELF symbols. The complete earlier OSV evidence contains 152 component-version records and 51 unique Go advisories, including 46 affecting its standard library. `govulncheck` 1.9.0 binary JSON mode exits zero even when it reports vulnerabilities; that exit code is not a clean result. For stripped binaries it conservatively falls back to module-level matches, so the original scan cannot establish vulnerable-symbol presence or flag-specific reachability. These limitations are documented in the [official govulncheck reference](https://pkg.go.dev/golang.org/x/vuln/cmd/govulncheck#hdr-Limitations).

The exact source and fastdialer 0.5.19 call path establishes that HTTPS uses `HTTPX.buildTLSDialer -> DialTLS -> tls.Client -> HandshakeContext`, followed by TLS reads. Thus HEAD does not eliminate the TLS 1.3 KeyUpdate exposure in GO-2026-4870. Certificate parsing still occurs despite `InsecureSkipVerify`, and HTTP redirect URL parsing occurs before the no-follow callback, so the ASN.1/URL parser advisories cannot be dismissed by the method alone. The original executable was replaced rather than accepting these risks implicitly. TLS certificate validation is not a claimed Observation field or authenticated-peer guarantee.

Evidence references in the matrix: E1 is the original/rebuild `go version -m` metadata and full OSV component-version scans; E2 is [exact httpx transport source](https://github.com/projectdiscovery/httpx/blob/4b6a9a9d476f94a4f3a630f37051f5671ecfb1f8/common/httpx/httpx.go) and [runner/options source](https://github.com/projectdiscovery/httpx/blob/4b6a9a9d476f94a4f3a630f37051f5671ecfb1f8/runner/options.go); E3 is the complete authoritative Go database record for each listed ID at `https://vuln.go.dev/ID/<ID>.json`; E4 is the rebuilt binary's actual symbol scan, including inlined symbols; E5 is [utils 0.11.3 update rendering](https://github.com/projectdiscovery/utils/blob/v0.11.3/update/update.go); E6 is the fixed host argument/environment/isolation boundary and its real laboratory tests. A symbol match is not itself a reachable execution path.

| Component / advisories | Vulnerable behavior and impact | Original profile exposure | Evidence / rebuild disposition |
| --- | --- | --- | --- |
| stdlib TLS/ASN.1: GO-2026-4870, GO-2026-6090, GO-2026-5972 | TLS KeyUpdate resource exhaustion; recursive ASN.1 stack exhaustion | HTTPS reaches TLS/certificate parsing; some prerequisites are role/message-specific, not eliminated by HEAD | E1–E3; Go 1.27.2 is outside affected ranges; fixed in rebuild |
| stdlib X.509: GO-2026-4599, GO-2026-4600, GO-2026-4866, GO-2026-4946, GO-2026-4947, GO-2026-5037 | Certificate constraint bypass, panic and expensive verification | Default fastdialer skips certificate verification; parsing remains separate | E1–E3; all version matches removed by patched stdlib |
| stdlib URL/IDNA: GO-2026-4601, GO-2026-5026, GO-2026-6218 | Invalid authority acceptance and costly path resolution | Canonical input rejects ambiguous hosts; response Location parsing can precede redirect denial | E1–E3, E6; fixed in patched stdlib |
| stdlib HTTP/2 client: GO-2026-4918, GO-2026-6610, GO-2026-6611 | Invalid framing/settings cause loops, smuggling or CPU exhaustion | HTTP11 disables HTTP/2 negotiation, retry client2 and optional HTTP2Probe | E1–E3, E6; stdlib fixed; remaining x/net matches assessed separately below |
| stdlib HTTP server/proxy: GO-2026-4976, GO-2026-6089, GO-2026-6603, GO-2026-6609, GO-2026-6612, GO-2026-6613, GO-2026-6617 | Proxy parameter bypass, server memory/CPU exhaustion, flow-control abuse, CONNECT desynchronization and encoder race | The fixed provider is a client, with no HTTP server/reverse-proxy/file-serving dispatch | E1–E3, E6; stdlib fixed regardless of absent server prerequisites |
| stdlib CONNECT client: GO-2026-6605 | Nonempty CONNECT body poisons pooled responses | HEAD has no request body; proxy environment is cleared and keep-alives are disabled | E1–E3, E6; fixed in rebuild |
| stdlib ECH: GO-2026-5856, GO-2026-6607 | ECH identity privacy leak or server memory amplification | No ECH configuration or TLS server role in this profile | E1–E3; fixed in rebuild |
| stdlib MIME/mail: GO-2026-5038, GO-2026-5039, GO-2026-6608, GO-2026-4977, GO-2026-4986 | Header/mail parsing CPU/memory exhaustion and unescaped error text | HTTP response headers are parsed; no multipart/email workflow; provider stderr is bounded and discarded | E1–E3, E6; fixed in rebuild; no raw error text reaches artifacts |
| stdlib filesystem: GO-2026-4602, GO-2026-4864, GO-2026-4970, GO-2026-6604 | os.Root metadata/symlink/junction escapes | No attacker-controlled os.Root operation; Windows junction case also excluded by Linux build | E1–E3, E6; stdlib fixed; kernel sandbox is independent of os.Root |
| stdlib Windows network: GO-2026-4971 | NUL-containing names panic Windows networking | Linux amd64 only; canonical input rejects NUL | E1–E3, E6; no matching platform; patched stdlib |
| stdlib DNS: GO-2026-4981, GO-2026-5942 | cgo CNAME crash / malformed DNS record panic | Provider uses CGO_ENABLED=0 and pinned hosts; outgoing DNS is denied | E1–E3, E6; fixed in rebuild; host Python resolver is a separate boundary |
| stdlib archive/XML: GO-2026-4869, GO-2026-6088 | Sparse archive allocation and recursive XML stack exhaustion | No runtime update/archive input; HEAD does not supply an XML body-processing workflow | E1–E3, E6; fixed in rebuild |
| stdlib templates: GO-2026-4603, GO-2026-4865, GO-2026-4980, GO-2026-4982, GO-2026-6091, GO-2026-6599, GO-2026-6600 | HTML/JavaScript template escaping failures and XSS | No untrusted HTML/template output workflow; only bounded JSON facts are persisted | E1–E3, E6; fixed in rebuild |
| x/net HTTP/2 client: GO-2026-6610, GO-2026-6611 | Malformed framing/settings cause smuggling or CPU exhaustion | Relevant symbols remain, but HTTP11 sets http2client=0, empty TLSNextProto, aliases retryable HTTPClient2 to the HTTP1 client and leaves HTTP2Probe false | E2–E4, E6; not reachable in the fixed profile; no blanket dependency waiver |
| x/net HTTP/2 server: GO-2026-6603, GO-2026-6612, GO-2026-6617 | Server memory/flow-control/HPACK race | Broad advisory symbol lists match client methods; vulnerable behavior requires an HTTP/2 server role that this profile never starts | E2–E4, E6; server prerequisites absent |
| goldmark: GO-2026-5320 | Markdown renderer XSS | Renderer symbols remain through update release-note rendering; update callback is not selected and update checks are disabled; network output is not rendered as Markdown | E2–E6; not reachable in fixed profile |
| compress/s2: GO-2026-5841 | Attacker-supplied encoding dictionary causes out-of-bounds read | NewDict is absent from the rebuilt binary's extracted/inlined symbols; no dictionary-encoding input exists in the CLI profile | E3, E4, E6; affected symbol not linked and triggering input absent |
| x/crypto OpenPGP: GO-2026-5932 | Unmaintained unsafe OpenPGP APIs | Affected packages have no symbol/package matches in the rebuilt binary; no PGP operation or input | E3, E4, E6; affected package not linked |
| x/crypto SSH: GO-2026-6354, GO-2026-6355 | Peer channel messages deadlock SSH connections | Affected SSH symbols/package are absent; only exact HTTP(S) origin and no proxy credentials/options | E3, E4, E6; affected package not linked |

The rebuilt executable retains ELF symbols: OSV still reports ten dependency advisories, while symbol analysis narrows them to six IDs in HTTP/2 and goldmark. All remaining prerequisites are excluded by inspected fixed-profile branches, not merely by HEAD. No standard-library advisory matches Go 1.27.2 in either scan. Re-assess this disposition before changing source, compiler, digest, method, protocol, update/rendering, proxy or credential behavior. Required installation and artifact delivery remain explicit; an unverified or old executable refuses without fallback.


## BS-2 restricted detection

BS-2 adds `./start.sh beescan detect` through the same host CLI/runtime and ArtifactAPI. It consumes an explicitly approved completed HTTP Observation; bootstrap and BS-1 retain their existing contracts. The independent `beescan.detection_enabled` defaults to `false`, and `detection_approval` defaults to `null`. Probe approval never grants detection authority. Legacy two-key BeeScan settings remain accepted; new settings must supply both detection keys. Enabling detection requires the enabled module and compatible public It5 contracts; missing or malformed approval fails startup validation. A missing It5 contract refuses execution and cannot produce a candidate.

The fixed profile is `web.detect.restricted` / `restricted_detection` / `http-marker-v1`, provider `nuclei`, template `beescan-http-marker` version `1`, candidate matcher `marker`. BeeAgent constructs intent using BeeScan `prepare_detection`, passes an evidence-only SDK result to `normalize_detection`, then calls `correlate_detections`. Candidate creation, identity, severity and triage remain BeeScan-owned. No scanner result grants VERIFIED status, external mutation or further execution authority.

### Actual request and scanner boundary

The trusted host capture worker sends exactly one fixed HTTP/1.1 GET `/` to the approved literal IP and port, preserving the approved Host and HTTPS SNI. HTTPS uses standard certificate verification. It does no worker DNS, redirect following, retries, proxy lookup, link traversal or body processing. The worker reads at most 8192 bytes of complete ASCII response headers and preserves only status plus the enum `X-Beescan-Marker: present|absent` (missing means no marker). Other header values and all body bytes are discarded. Redirects, invalid marker values, malformed or truncated headers, timeout and oversized input fail closed. The request ceiling follows from the independent one-shot capture implementation, rather than Nuclei request flags.

Capture runs inside the verified BS-1 rootless network namespace and exact nftables destination allowlist, with capabilities dropped and nested user namespaces disabled. Nuclei runs separately with `--unshare-all` and no shared network namespace. It receives a synthetic bounded HTTP representation containing only the captured status/enum marker and host-added completion header. This uses the upstream [passive HTTP response mode](https://github.com/projectdiscovery/nuclei/blob/a8c88feb4a1c8e961b7902534ce3af97e9d524a4/pkg/protocols/offlinehttp/request.go). The copied pinned template supplies an internal `completed` matcher as an integrity check; this matcher never becomes a Finding. Exactly one completion event and zero or one consistent `marker` event are mandatory. Empty stdout, exit zero alone, extra/duplicate records, unknown fields/template/matcher, false completion, forged provenance/authority and contradictory input paths all fail. Raw JSONL is validated then discarded.

Nuclei sees only its read-only executable/template/input, private tmpfs HOME, minimal devices and isolated proc. Public/GitHub/GitLab/AWS/Azure template downloads are disabled in the cleared environment; update, cloud authentication, stdin, OAST, redirects, headless and code execution are unavailable in the fixed arguments/template. Even a scanner networking attempt has no egress. The capture process additionally sees read-only system Python/libraries and certificate store. Host settings, storage, HOME and credentials are absent from both workers. There is no alternative executable/template flag or runtime installer.

One overall worker deadline covers namespace verification, version check, capture and scanner. Limits include 2048–4096 MiB address space, CPU ceiling, 64 descriptors, 64 KiB file size, zero core dumps, 4096 UID-wide processes/threads, `GOMAXPROCS=2`, and 1024–16384 combined output bytes (capture is independently limited to 4096 bytes). `RLIMIT_NPROC` shares the UID budget with other processes and can refuse on a busy host; it is not a per-worker cgroup limit. Process groups are killed/reaped, Bubblewrap PID isolation/die-with-parent handles detached descendants, temporary snapshots are removed and namespace descriptors closed on all exits. Cleanup failures remain unsuccessful.

### Provision the reviewed executable and template

The reviewed upstream release is [Nuclei v3.11.1](https://github.com/projectdiscovery/nuclei/releases/tag/v3.11.1), source commit `a8c88feb4a1c8e961b7902534ce3af97e9d524a4`. Official `nuclei_3.11.1_linux_amd64.zip` SHA-256 is `ea63d4ae232808cd7c6bc00d0142428e231fab59dae01042246097d195835ab6`; the extracted static Linux amd64 executable is 143294626 bytes with SHA-256 `c49588140f357cbdddd5436dec11201953a4c5390faeec90777f9ee2cfd70251`. Its actual reported version is `v3.11.1`; embedded Go build metadata reports `go1.26.5`. Other versions, digests and dynamic ELF binaries refuse. The larger binary snapshot limit is detection-only; BS-1 keeps its 64 MiB default.

Provision offline before execution: verify the archive against the upstream release checksum, extract only `nuclei`, place it at the operator-controlled absolute path, set mode `0555`, and verify its executable digest. Use the repository's exact `config/beescan-http-marker.yaml` bytes with SHA-256 `51bab1f02a5553709d4684c83e81e371cc935f07f2a1c6edd554cffc19027597`, mode `0644` or stricter. Configured asset paths select locations only; immutable host digests determine which bytes may execute. Symlinks, writable provider/template files and modified templates refuse. Review a replacement before changing either pin; never update them from scanner output.

```bash
sha256sum /opt/beescan/nuclei /absolute/path/to/beeagent/config/beescan-http-marker.yaml
chmod 0555 /opt/beescan/nuclei
chmod 0644 /absolute/path/to/beeagent/config/beescan-http-marker.yaml
```

### Detection approval

Keep the existing `probe_enabled` / `approval` independently configured. Add both detection keys under the same `beescan` mapping. The following complete detection approval is illustrative; replace identity, source refs, UID, live namespace PID, paths and validity window with the explicitly approved values. Private addresses require `allow_private_lab: true`; production approval must use its actual allowed destination. Request budget is exactly one; time budget is 1–60 seconds and the validity window must accommodate the entire budget at each authorization check.

```yaml
  detection_enabled: true
  detection_approval:
    operator_uid: 1000
    project_id: project-lab
    scope_id: scope-lab
    mission_id: mission-lab
    target_id: target-lab
    origin: http://127.0.0.1:18080
    approved: true
    excluded: false
    valid_from: "2026-10-15T00:00:00+00:00"
    expires_at: "2026-10-16T00:00:00+00:00"
    method: restricted_detection
    request_budget: 1
    time_budget_seconds: 15
    connected_ip: 127.0.0.1
    allow_private_lab: true
    executable: /opt/beescan/nuclei
    sha256: c49588140f357cbdddd5436dec11201953a4c5390faeec90777f9ee2cfd70251
    provider_version: "3.11.1"
    network_namespace: /proc/12345/ns/net
    user_namespace: /proc/12345/ns/user
    memory_mb: 3072
    output_bytes: 8192
    source_run_id: run-approved-source
    source_observation_id: http-approved-observation
    provider_id: nuclei
    profile: http-marker-v1
    template_id: beescan-http-marker
    template_version: "1"
    template_path: /absolute/path/to/beeagent/config/beescan-http-marker.yaml
    template_sha256: 51bab1f02a5553709d4684c83e81e371cc935f07f2a1c6edd554cffc19027597
```

The source must be under host-owned `storage/runs/<source_run_id>/module-beescan/`, with complete `http_probe_status.json`, consistent `http_observation.json` and every referenced HTTP evidence JSON. Source files must be regular, non-symlink, bounded to 32 KiB and not group/world writable; protect settings/storage parent directories against untrusted replacement. If BS-1 ran with a group-writable umask, the trusted operator must secure those source artifacts before approving detection. The reader walks each run directory without following symlinks and reconstructs public typed facts/provenance/observation, checks status identity and evidence consistency, then invokes public detection preparation to verify the observation identity. Artifact contents alone never select a source; approval binds both run and observation IDs. Approval, source equality, UID, validity and exact DNS destination are checked repeatedly, including immediately before capture. Scanner output cannot supply any of these values.

### Results and recovery

Host artifacts use schema version 1 under the new run's `module-beescan/`: `detection_intent.json`, `detection-evidence-<opaque-id>.json`, `detection_outcome.json`, `detection_candidates.json`, and terminal `detection_status.json`. Evidence contains sanitized capture facts, host run/provider provenance, source binding and exact template identity/digest. All writes use ArtifactAPI, bounded read-back verification and file fsync; the terminal status is prepared separately and atomically replaces the initial incomplete marker only after successful processing/cleanup/persistence. Per-run detection directories are mode 0700 and files 0600. Orphan evidence/outcomes without a complete final status are incomplete; consumers must never infer completion from candidates alone. A failed final status write leaves the initial incomplete marker or no accepted status, and the CLI returns failure.

`matched` and `no_match` alone have `complete: true` and exit 0. `refused` exits 3, `timeout` exits 4, and `error`, `malformed` or `incomplete` exit 5; invalid CLI syntax exits 2. `no_match` means this fixed marker was absent in a completed header capture, not that the target is vulnerability-free. Refusal means repair/reapprove the specific prerequisite; execution/parser/resource failures require inspection and a new explicitly authorized run. There are no automatic retries, repairs, approval extensions or follow-up scans.

### Local verification and dependency gate

BeeScan main was inspected at `ae1d1d07cf9d0e0fadd5fb9e4d8da71a4573eac2`; It5 is still unmerged. Production `pyproject.toml`/`uv.lock` remain unchanged. The host implementation is tested against the current reviewed feature-worktree It5 wheel in a separate development environment. This is local integration evidence, not a release pin or proof that normal frozen installation already supports detection. After It5 merges and is reviewed, select that actual immutable revision with only its necessary lock update, run all feature/core/ROP/BeeDrill regressions, the explicit lab and hosted CI, then obtain independent read-only review. Do not point production dependencies at a sibling directory or unmerged branch.

For an isolated coordinated dev run, build the reviewed BeeScan wheel, create a separate venv, install that wheel without dependencies, and expose the already installed host dependencies through a `.pth` file. This preserves the production environment and Git source pin. Example for this workspace's Python 3.14 environment:

```bash
uv venv /tmp/beeagent-bs2-it5-env --python .venv/bin/python
uv pip install --python /tmp/beeagent-bs2-it5-env/bin/python --no-deps ../beescan/dist/beescan-0.4.0-py3-none-any.whl
printf "import site; site.addsitedir('%s/.venv/lib/python3.14/site-packages')\n" "$PWD" > /tmp/beeagent-bs2-it5-env/lib/python3.14/site-packages/host-dependencies.pth
UV_PROJECT_ENVIRONMENT=/tmp/beeagent-bs2-it5-env uv run --frozen --no-sync python -m pytest -q
BEEAGENT_BEESCAN_NUCLEI=/absolute/path/to/verified/nuclei UV_PROJECT_ENVIRONMENT=/tmp/beeagent-bs2-it5-env uv run --frozen --no-sync python -m pytest -q integration_tests/test_beescan_detection_lab.py
```

BS-2 feature tests require the actual It5 API and do not silently skip an unavailable contract. The separate real lab requires an explicitly provisioned binary and kernel isolation; it fails on missing prerequisites. Its source observation comes from an actual local HEAD capture using the explicitly named test-only `lab-http-head` provider, then the production governed GET/passive-Nuclei path executes. This does not pretend that httpx ran. The existing independent BS-1 httpx lab remains unchanged. The detection lab verifies positive/negative candidates, redirect denial, timeout, malformed/oversized headers, exact request counts, forbidden-port/proxy and IPv4/IPv6 egress, operator/scope/provider/template refusals and secret exclusion. Unit tests use mock scanner output for malformed output, provenance injection, changed approval/source, one-shot execution and persistence faults; those tests are separate from real Nuclei execution.


### Nuclei SCA applicability review (2026-10-15)

The actual executable build-info section identifies 382 dependency modules plus Go stdlib 1.26.5. Queries to the [OSV API](https://google.github.io/osv.dev/api/) covered all 383 components; the embedded self-module `(devel)` was resolved to the verified release v3.11.1 before querying (no release-version advisory match). The resulting seven affected component versions produce 38 advisory IDs: 33 Go IDs plus five GHSA aliases of the same issues. These are real version matches, not a clean scan. The stripped release has no ELF symbol table; no govulncheck symbol/reachability scan was claimed. Full local evidence is `buildinfo.txt`, `osv-components.json` and `osv-advisories.json` alongside the separately provisioned binary; retain those files with deployment review evidence.

| Affected component / Go IDs | Reviewed fixed-profile applicability |
| --- | --- |
| stdlib 1.26.5: GO-2026-5026, 5942, 5972, 6088, 6089, 6090, 6091, 6218, 6599, 6600, 6603, 6604, 6605, 6607, 6608, 6609, 6610, 6611, 6612, 6613, 6617 | DNS, TLS, ASN.1, XML, URL/IDNA, HTML templates, HTTP server/2, CONNECT and Windows junction prerequisites are absent from this Linux passive execution. Nuclei receives only a host-generated small ASCII HTTP/1.1 response with fixed zero-length body; MIME/header budget bypass cannot receive unrestricted header input. HTTPS and raw header capture happen in the separate Python worker and do not use Go TLS/HTTP parsing. |
| x/net 0.56.0: GO-2026-6603, 6610, 6611, 6612, 6617 | No HTTP/2 transport/server or incoming network frames; offline parser uses net/http ReadResponse on the fixed sanitized HTTP/1.1 representation. |
| go-git/v5 5.19.1: GO-2026-6213, 6214 | Git worktree/ref operations require template repository download/update; all download sources are disabled, network absent, no Git checkout/ref input is mounted. |
| x/mod 0.37.0: GO-2026-6179, 6180 | No module download or transparency-log/sumdb input exists in the runtime sandbox. |
| x/crypto 0.53.0: GO-2026-5932, 6303, 6354, 6355 | No OpenPGP or SSH authentication/channel execution/input in the fixed HTTP marker template; no network sockets to peers. |
| x/text 0.39.0: GO-2026-6629 | Vulnerable PRECIS parsing requires crafted Unicode; template and sanitized scanner input are fixed/bounded ASCII with enum values. |
| grpc 1.82.1: GO-2026-6348, 6441, 6443 | No gRPC/xDS server, HTTP/2 peer or RBAC header input; raw endpoint bytes never reach scanner. |

Each shortened number in the matrix retains the `GO-2026-` prefix. Authoritative full records are available from the [Go vulnerability database](https://vuln.go.dev/) at `/ID/<full-ID>.json`, including affected packages/symbols and prerequisites. Source evidence is the exact release's [offline execution path](https://github.com/projectdiscovery/nuclei/blob/a8c88feb4a1c8e961b7902534ce3af97e9d524a4/pkg/protocols/offlinehttp/request.go), [response parser](https://github.com/projectdiscovery/nuclei/blob/a8c88feb4a1c8e961b7902534ce3af97e9d524a4/pkg/protocols/offlinehttp/read_response.go) and [download environment selection](https://github.com/projectdiscovery/nuclei/blob/a8c88feb4a1c8e961b7902534ce3af97e9d524a4/internal/runner/options.go), together with the inspected pinned template, host sanitizer and real sandbox tests. This is a bounded applicability assessment, not proof that affected symbols are absent. Expanding inputs/protocols/templates/network access requires a new SCA/security review; these dispositions do not approve active arbitrary Nuclei scans.

Static security review covers path/namespace ownership, no-follow bounded reads, host provenance, resource/process cleanup, output injection and partial persistence. Ruff security rules report only three S108 matches for `/tmp` inside the private sandbox tmpfs; these are reviewed false positives, not shared host temporary files. Tests include deterministic malformed-byte fuzzing, injected cleanup/persistence failures, live approval/source changes and direct kernel egress probes; no standalone IAST instrumentation or blanket penetration-test certification is claimed.
