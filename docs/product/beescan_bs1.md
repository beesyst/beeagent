# BeeScan BS-1 laboratory execution

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

BeeScan's Git source repository is private. A cold installation requires authorized repository read access, which the current workflow does not configure; a credential-free clean installation therefore remains blocked. An isolated core run using already verified cached dependencies proves test/profile compatibility but does not prove hosted access to that private source. The delivery setup must resolve repository read access before hosted CI can be declared ready.

The provider SCA applicability review below applies only to this exact digest and fixed host profile. It does not approve arbitrary httpx flags or claim that every embedded dependency is vulnerability-free. BeeScan It4 is available from its locked Git revision; hosted PR CI and final read-only review remain separate delivery gates, and BS-1 is not marked DONE.

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
