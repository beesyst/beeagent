# WEB_UI — BeeAgent Operator Console

## Purpose and ownership

BeeAgent serves its canonical Web console through the BeeUI-backed `src/beeagent_module/interfaces/ui/` implementation. BeeUI provides generic rendering, session UX and components; BeeAgent owns product read models, server-side resource authorization, approved integration callbacks and narrowly scoped write actions. The older `src/beeagent_module/web/` package remains legacy and is not the target for new UI work.

This document describes the current Web and JSON contracts. [SECURITY.md](SECURITY.md) defines policy; [DEV_GUIDE.md](DEV_GUIDE.md) covers startup; [product/ui_roadmap.md](product/ui_roadmap.md) tracks future work.

## Sources of truth

| Concern                                                                   | Owner                                                                                               |
| ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Host binding, auth, principal scopes, Bitrix enablement and widget policy | `config/settings.yml`                                                                               |
| UI navigation, pages, tabs and locale defaults                            | `config/beeui.yml`                                                                                  |
| BeeUI application and HTTP route policy                                   | `interfaces/ui/app.py` and `interfaces/ui/bitrix_embed.py`                                          |
| Product pages, bounded actions and query validation                       | `interfaces/ui/adapter.py`                                                                          |
| Run/ROP projections                                                       | `interfaces/ui/read_model.py` and dedicated read-model modules                                      |
| Artifact allowlist, safe previews and download boundaries                 | `interfaces/ui/artifacts.py`, `interfaces/ui/bounded_read.py`, host artifact interfaces             |
| Canonical ROP source registry                                             | `config/rop/sources.yml`, then protected persistent `storage/config/rop/sources.yml` after mutation |
| ROP durable write-back state                                              | `storage/interfaces/rop_writeback_state.json`                                                       |

GET/read-model fallbacks never modify storage. UI view state and read-model artifacts are not sources of authority for CRM actions, mailbox execution or security-scanner permissions.

## Start and supported routes

```bash
./start.sh web
./start.sh web --host 127.0.0.1 --port 8780 --no-open
./start.sh routes
```

The default console is for an appropriately protected local environment; public exposure requires enabled authentication and trusted HTTPS.

| HTML route                                                           | Purpose                                                                   |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| `/`                                                                  | Product dashboard                                                         |
| `/runs`, `/runs/{run_id}`                                            | Run history and details                                                   |
| `/runs/{run_id}/artifacts`, `/runs/{run_id}/artifacts/{artifact_id}` | BeeUI artifact browser; server-side allowlist and resource checks apply   |
| `/rop`                                                               | ROP overview, queue, sources and blacklist tabs                           |
| `/rop/events/{event_id}`                                             | Bounded ROP event detail; `run_id` required, `event_instance_id` optional |
| `/rop/bitrix/{entity_type}/{entity_id}`                              | Allowed Bitrix reconciliation detail                                      |
| `/rop/attachments/{attachment_id}/download`                          | Forced download of a validated original attachment                        |
| `/modules`                                                           | Registered module diagnostics                                             |
| `/health`                                                            | Public, sanitized health response                                         |

Selected JSON routes:

| API route                                                       | Purpose                                             |
| --------------------------------------------------------------- | --------------------------------------------------- |
| `/api/dashboard`, `/api/runs`, `/api/runs/{run_id}`             | Dashboard and run projections                       |
| `/api/modules`                                                  | Registered module metadata                          |
| `/api/rop/dashboard`                                            | Bounded ROP dashboard/read model                    |
| `/api/rop/events/{event_id}`                                    | Safe ROP event detail                               |
| `/api/runs/{run_id}/artifacts` and `.../{artifact_id}`          | Allowlisted artifact metadata/viewer envelope       |
| `/api/bitrix/rop/widget` and `/events` and `/events/{event_id}` | Read-only token-protected Bitrix widget projections |

Actual HTTP methods and routes are authoritative in `interfaces/ui/app.py` and the BeeUI integration. The rendered navigation never authorizes access on its own.

## Authentication and access control

`web.auth` in `config/settings.yml` configures `beeui_session` mode, the `session_secret_env` reference and named principals. Each local principal has an `id`, `username`, `role` (`viewer`, `operator`, `admin`), explicit resource `scopes` and an environment-backed `token_env`.

- Authentication binds the exact configured username/token pair to the canonical principal ID; roles control authority and scopes control resource access. `admin` with `scopes: ["*"]` is the global wildcard exception. Other principals must have explicitly authorized scopes; unknown resources are denied by default.
- Common scopes are `dashboard`, `rop`, `runs` and `modules`; the additional `rop.sources.write` capability grants the protected source/credential-management surface to authorized ROP operators. `rop` alone does not grant general config or mailbox credential editing.
- A principal limited to `rop` may use ROP pages and ROP-owned allowlisted artifacts but not unrelated run/module/dashboard data. Navigation is filtered, but all HTML, JSON and artifact requests are checked again on the server.
- When enabled, unauthenticated HTML redirects to `/auth/login`; unauthenticated JSON returns `401` with `unauthenticated`; authenticated but unauthorized requests return `403` with `forbidden`.
- Signed `beeui_session` cookies are managed by BeeUI. Session secrets and principal tokens live in environment, not YAML or response payloads; rotation requires reauthentication/restart as documented by the CLI. Different principals resolving to the same token are rejected.
- Disabled auth is for protected local development only, not public network exposure. Generic unknown/future paths under an enabled auth boundary remain protected.

Useful operator commands:

```bash
./start.sh auth rotate <principal-id-or-username>
./start.sh auth rotate all --logout-all
./start.sh auth rotate session
```

Public/independently authenticated boundaries are restricted to sanitized `/health`, `/static/*`, the BeeUI `/auth/*` flow, Bitrix Local Application callbacks and configured widget/event APIs. Public route status does not mean anonymous data access: widget and robot endpoints require their own separate authentication.

## ROP projection and tabs

`/rop` uses a BeeUI product adapter and canonical server-side query parameters. Tabs are `overview`, `queue`, `sources` and `blacklist`. UI supports English and Russian (`?lang=en|ru`); a valid explicit query value takes precedence over the `beeui_lang` cookie and `config/beeui.yml` default.

The overview is a bounded materialized read model: KPIs, source health and contribution, classification, deterministic recommendations, attention queues, attachments, thread context and Bitrix evidence. Explicit period selection includes `today`, `yesterday`, `7d`, `30d`, `90d`, `365d` and `all`. Aggregated period views must preserve origin-run identity, avoid cross-run duplicate inflation and distinguish missing/malformed projections from confirmed zero values.

ROP final-decision projections distinguish deterministic, AI-assisted and fallback sources. They preserve `final_case_type`, `final_case_subtype`, `final_queue`, `final_action`, `final_decision_source`, `final_confidence`, attention/reason fields and explicit `automation_allowed`/`bitrix_write_allowed` flags where supported. These fields are operator information, not authorization to mutate Bitrix. Missing legacy optional fields degrade safely. The final decisions artifact is preferred; safe read-only fallback from existing classified/adjudication artifacts is permitted without writing storage.

ROP Event Detail uses exact `run_id` plus optional `event_instance_id` to disambiguate repeated transport `event_id` occurrences. Original e-mail and document contents are never emitted as arbitrary HTML, JSON or inline attachments. Malformed or inaccessible event artifacts return bounded errors, not unfiltered raw bytes.

## Queue query contract

The Queue tab is one BeeUI `data_table` with canonical toolbar and progressive GET navigation. The server remains authoritative for filtering, sorting, pagination and output.

| Parameter                         | Meaning / supported values                                                                               |
| --------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `q`                               | Sender/subject search; `sender` and `subject` are legacy filters                                         |
| `case_type`                       | Classification filter; `classification` is a legacy alias                                                |
| `priority`                        | `low`, `medium`, `high`, `critical`                                                                      |
| `bitrix_status`                   | Supported reconciliation statuses                                                                        |
| `is_fallback`                     | Exact `true` or `false`                                                                                  |
| `queue`                           | `high_priority`, `needs_review`, `lost_in_bitrix`, `ambiguous`, `degraded`, `unreconciled`               |
| `date_from`, `date_to`            | Inclusive ISO `YYYY-MM-DD`, ordered when both supplied                                                   |
| `page`                            | One-based positive integer, default `1`                                                                  |
| `page_size`                       | `25`, `50` or `100`, default `25`                                                                        |
| `sort`                            | `received_at`, `date`, `event_date`, `sender`, `subject`, `case_type`, `priority`, `bitrix_status`       |
| `order`                           | `asc` or `desc`; default is `received_at` / `desc`                                                       |
| `columns`                         | Allowed visible column keys (`priority`, `client`, `subject`, `date`, `classification`, `bitrix_status`) |
| `run_id`, `tab`, `period`, `lang` | Canonical context preserved across valid navigation                                                      |

`sort` and `order` travel as a pair or are both omitted for the default. Invalid filter, date, enum, column, page or sort values must be refused rather than broadening the result. The table ID is `rop-queue`; only this table receives the ROP-specific toolbar. Its date picker submits on select/clear, text search uses GET, dropdown state and selected columns survive navigation, and Reset preserves context. Legacy UI-only query flags must not become independent permission or filtering rules.

Missing/invalid event dates sort after valid timestamps in both directions. Attention events are bounded (existing cap `500`); the UI cannot request unbounded underlying storage.

## Protected ROP writes

Normal GET routes remain read-only. The following explicit bounded actions are exceptions; they use the existing BeeUI action/CSRF boundary, validated inputs, server-side role _and_ scope checks, and audit.

### Sender blacklist

`/rop?tab=blacklist` supports protected Add/Update/Delete for an exact sender e-mail key, with name/title and a bounded business reason. Search, pagination and CSV export are read-only; CSV import is not supported. Blacklist decisions can affect subsequent ROP classification (`irrelevant`) but do not edit historic source artifacts or perform CRM mutations.

Bitrix robot callback endpoints `POST /api/bitrix/rop/events` and `POST /api/bitrix/rop/events/{callback_secret}` authenticate independently using the configured application-token or constrained path-secret mode. The host re-reads the configured stage, sender and required classification field through the read-only Bitrix client before a canonical idempotent blacklist mutation. A callback never trusts unverified event text as an action. The path secret must not appear in reverse-proxy access logs, redirect URLs, responses or query strings.

### Sources management

The Sources tab reads the canonical configured source registry and a bounded materialized all-time contribution projection. `Processed total` is zero only when a valid projection confirms that the source contributes no events; missing/malformed projections are unavailable. `Available sources` counts enabled sources with a successful latest connection check, not indefinitely open sockets.

Authorized Add/Edit/Delete, Enable/Disable and mailbox Check require `operator` or `admin`, `rop` and `rop.sources.write` (or the admin wildcard). Mailbox Check performs only connect, login and read-only folder select, storing safe connection health under `storage/interfaces/rop_source_connection_health.json`.

The credential-management path may update only the selected mailbox source's username/password environment references. Mailbox passwords never enter YAML, returned APIs, CSV or audit; when editing, a blank password preserves the current value. An authorized manager may view the username, but passwords are rendered only as a presence mask. No Sources action grants Dashboard, arbitrary settings, global auth, `rop run` or CRM write-back authority.

## BeeScan investigation workspace

`/beescan` is a standard adapter-backed BeeUI page using the same `fill_icons`, progressive, separated page tabs and canonical content width as ROP. `tab` accepts only `investigation` (default) and `results`. Investigation contains the product-neutral `chat_workspace`: Cases/Кейсы and bounded owned search on the left, the factual conversation in the center and read-only Context on the right. Search uses `q` (up to 128 characters), preserves locale and the selected Case, and displays an explicit empty-match notice without discarding that Case. Tab/history navigation preserves authorized `run_id`, locale and search state. Results uses existing read-only blocks for authorized Case findings, report summary and evidence references; it adds no BS-17 review operation. The compact card footer contains Task, a neutral-icon text Target input, native Quick/Standard/Deep radio buttons, an inert disabled three-dot menu and an accessible send icon. Enter in Task submits the existing governed action; Shift+Enter inserts a newline and IME composition does not submit. Target remains restricted to the currently approved HTTP(S) origin despite the generic text-input presentation; unsupported identifiers are refused without evidence persistence or target traffic. Existing Cases retain original authenticated Target/Task/mode for Resume. Context contains only actual status, Scope/Approval, ordered steps/tools, Findings/Candidates, metrics and safe report summaries, without duplicate KPI panels below the chat. CSS provides a bounded responsive height with independently scrollable content and no viewport-driven inline sizing. Tablet/mobile panel controls prioritize conversation; RU/EN and light/dark remain supported. `GET /api/beescan/status?run_id=<run_id>` remains the protected bounded polling/Inspect projection. All Case reads require enabled authentication and the `beescan` resource scope (or configured admin wildcard), produce no target requests and do not change Case state.

Coordinated development uses the existing editable BeeUI checkout at `../beeui`. Deployment requires a reviewed BeeUI distribution containing `chat_workspace`; the editable integration is not release-source verification. Release BeeUI first, then update BeeAgent’s actual PyPI pin and corresponding lockfile through the approved dependency handoff and rerun release-source regressions before merging the BeeAgent integration. Package versions are not changed during this implementation.

Start and Resume use the existing CSRF-protected `POST /api/actions/execute` with action IDs `beescan_start` and `beescan_resume`. Execution requires the verified session's operator/admin role, `beescan.investigate` plus `beescan` (or admin wildcard), explicit membership in `beescan.investigation.web.principal_ids`, and current independent host investigation approval. The optional `web` configuration is disabled when absent; when present it must contain exactly `enabled` and `principal_ids`. Enabled Web execution additionally requires enabled Web authentication, enabled investigation, its explicit approval, and configured general discovery limits. Invalid configuration fails validation. See the [operator setup](product/beescan_guide.md#web-investigation-setup).

The forms submit only `target`, `task`, `mode`, and a short-lived principal-bound nonce; Resume additionally requires `case_id`. Authority, provider, budget and actor overrides are rejected. Nonces expire after ten minutes and each accepted action consumes its identity durably. One Web invocation may execute per storage root at a time; concurrent requests refuse rather than queue duplicate scans. The accepted response returns the durable Case/run identity while the existing investigation executes. Refresh or polling reads the saved progress, steps, request count, elapsed time, evidence references, candidate Findings and safe report projection. Token/cost availability remains explicit. A preview returns only `execution_authorized: false`; it does not inspect protected resources or grant authority.

Quick/Standard/Deep cap general steps/requests/depth at `2/2/1`, `8/8/3` and `16/20/4`, respectively, further restricted by configured host ceilings. They do not grant new capabilities. Active DAST still requires its separate current approval with authenticated-discovery entry selection and the existing provider, destination, budget, mediation and cleanup checks. The nonrecursive verification profile requires Standard or Deep; Quick refuses before execution. Exact-entry DAST and protected terminal disclosure are not Web presentations.

New Cases retain bounded original Target/Task/mode in host-signed `web_intake.json`, bound to the existing ownership identity. This is input metadata, not a conversation database or execution authority. The chat reconstructs the operator request and ordered host events from this metadata and authenticated Case segments; it invents no timestamps, progress percentage, explanations or usage measurements. The status projection is bounded to 64 KiB, retaining at most 64 host events plus bounded candidate findings. Missing measurements remain unavailable. Historical Web Cases without authenticated intake remain inspectable but automatic Resume is unavailable. Altered intake or completed checkpoint authentication fails closed.

After Start, the browser opens the returned run in the same Case conversation and polls only the authorized status endpoint every three seconds, bounded to 300 attempts. Polling stops on authenticated completion or repeated failure and aborts on page exit. Resume submits the saved original Target, Task and mode using the existing protected action; the composer is read-only for an existing Case. A different objective requires New Case. Polling replaces events by stable host identities, without appending duplicates or treating presentation state as evidence. Generic templates and browser assets are packaged by BeeUI; BeeAgent has no custom BeeScan HTML renderer, frontend bundle or static mount. The composer reuses BeeUI’s existing protected action/CSRF transport. The authorized status response adds bounded `presentation` metadata for generic messages, state, bounded read-only Context sections and compatible existing KPI value updates; authenticated completion reloads the canonical page for current actions and final sections. Read conflicts during atomic publication receive at most three fresh snapshot attempts; invalid evidence and ownership still refuse.

Host-signed `web_owner.json` binds every Web Case, segment and child run to the verified principal. `web_receipt.json` authenticates completed Case/evidence/report bytes independently of the Case's existing digest. Existing Case schemas remain unchanged. Resume requires the original Target, Task, mode and unchanged approved BeeScan configuration, current permissions, a valid signed receipt and a compatible checkpoint; sufficient terminal work is reused without target traffic. Pending, foreign, unowned historical and tampered checkpoints refuse. An interrupted process is never automatically replayed.

BeeScan resources are excluded from generic Dashboard/run listings and denied through generic run/artifact routes, including for wildcard principals; use the owned workspace projection. Historical CLI Cases receive no implicit Web ownership. Raw HTTP bodies, sensitive values, query payloads, credentials, private paths and arbitrary report bytes are not exposed. Ownership signatures derive from the environment-backed Web session secret with a separate signing context; changing that secret invalidates existing Web ownership, so retain it securely when durable Case access is required.

## Artifacts and attachments

Artifact routes accept only validated run/opaque artifact IDs and allowlisted types through BeeUI and the BeeAgent adapter. Arbitrary paths, symlinks, traversal, unknown run IDs and other modules' protected artifacts fail closed. Previews are size-bounded, escaped and redacted; inaccessible or malformed records degrade to an explicit error/warning.

`GET /rop/attachments/{attachment_id}/download?run_id=<run_id>&event_id=<event_id>` resolves only a manifest-approved original. `run_id` is required; `event_id`, when supplied, must agree with the stored item. The response is a forced attachment with `Content-Type: application/octet-stream`, `X-Content-Type-Options: nosniff` and `Cache-Control: no-store`. There is no inline HTML, MIME rendering, raw `.eml` or nested-message download bypass. Disabling ROP attachment semantic analysis does not bypass storage-level download authorization.

The JSON/HTML read models exclude raw e-mail messages, raw content, attachment bytes, cookies, secrets, unrestricted scanner reports and sensitive identifiers. Safe `read_only` response metadata cannot substitute for route-level security checks.

## Bitrix integrations

### Widget API

`GET /api/bitrix/rop/widget`, `/events` and `/events/{event_id}` are bounded, read-only projections. When enabled, they use a dedicated configured Bearer token through `bitrix.widget.token_env` and `bitrix.widget` limits/periods. The output includes safe final-decision summaries and bounded event identities. It never triggers mailbox processing, CRM writes or runtime capabilities. The widget token is separate from a BeeUI session and from Local Application OAuth tokens.

### Embedded Local Application

The ROP console can be opened inside the configured Bitrix24 portal as a server-side Local Application with UI. `bitrix.embedded_app.enabled` requires Web auth. `portal_origin` is the exact trusted HTTPS origin; it controls both outbound Bitrix REST calls and CSP `frame-ancestors`. An embedded session uses `HttpOnly`, `Secure`, `SameSite=None` and a constrained age. Its assigned role is the configured `viewer` or trusted-audience `operator`, never a browser-selected role or `admin`.

- `POST /bitrix/rop/install` validates bounded form fields, current Bitrix user and token expiry, then atomically binds one `member_id` to the configured portal in `storage/interfaces/bitrix_rop_app.json`. A foreign installation/portal is rejected. Installation may also start the first valid ROP session.
- `POST /bitrix/rop/launch` validates the existing binding and current user with `user.current` against **the configured portal**, then issues the restricted BeeUI session and redirects `303` to `/rop`. `GET` launch is not a credential transport. Bitrix requires the `user` application permission.
- Actual Bitrix payloads may omit `DOMAIN`; the trusted domain always comes from `portal_origin`. Any supplied `DOMAIN` must match it. `AUTH_ID`, `AUTH_EXPIRES`, `REFRESH_ID` and additional placement data are bounded and never persisted/logged as OAuth credentials or used to create outbound destinations.
- Both handlers require an actual HTTPS ASGI request scheme from a trusted reverse proxy, not an untrusted client `X-Forwarded-Proto` header. OAuth credentials never enter URLs or rendered HTML. Sessions and responses use `no-store` and `Referrer-Policy: no-referrer` where appropriate.

The local `/auth/login` flow and widget Bearer API remain independently supported. Local Application launch alone does not grant arbitrary resource scopes, CRM write-back or other execution authority.

## Non-goals and verification

The Web interface is not a generic module executor, arbitrary artifact browser, CRM administration interface, database admin, mail parser or public security-scanner console. No GET route may trigger external mutation. Additional protected actions require an explicit reviewed contract and testable server-side authorization.

For Web changes, verify the actual route and method, authentication and resource scopes, CSRF on mutation, invalid inputs, pagination/filtering, redaction, download headers, compatibility with old run artifacts and absence of unintended writes. Use `tests/test_web_console.py`, `tests/test_rop_web_projection.py`, `tests/test_bitrix_embed.py` and relevant integration tests. Only claim test/CI success when run and observed.
