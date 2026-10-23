# WEB UI — BeeAgent Web Console contract

ROP sender blacklist uses a bounded management table with Name, Title, Email and business Reason, e-mail-only search, canonical pagination, CSV download, and protected direct Add, inline Save and Delete actions. The product continues to enforce authorization, CSRF, validation and audit; CSV import is not supported. Bitrix robot callbacks carry their dedicated secret as a bounded URL path segment, never as a query parameter, and re-read the configured lead stage, sender, name and position through the read-only Bitrix client before a canonical, idempotent blacklist mutation. The configured classification field is required, must contain a non-empty string of at most 128 characters, and is recorded as Reason; invalid or missing values fail closed without mutation. The canonical callbacks are `POST /api/bitrix/rop/events` for Bitrix application-token authentication and `POST /api/bitrix/rop/events/{callback_secret}` for constrained robot path-secret authentication. Production reverse-proxy access logging for the secret-bearing callback must not persist the raw request URI.

ROP Sources uses a canonical `data_table` backed by the checked-in `config/rop/sources.yml` seed and, after the first mutation, the authoritative persistent runtime registry `storage/config/rop/sources.yml`, not operational artifacts. It shows every configured source and its `Processed total` from the materialized all-time canonical source-contribution projection; an unavailable or malformed projection is an em dash, while a source absent from a valid projection is zero. `enabled` is configuration state, separate from last verified mailbox access evidence in `storage/interfaces/rop_source_connection_health.json`. A mailbox Check performs only connect, login and readonly folder select; green means that latest check succeeded, not that a socket is held open. Add and mailbox Edit check after durable persistence, while a remote failure preserves valid configuration and records safe failed evidence. Real ROP run and poll access also refresh this evidence. Overview `Available sources` counts enabled configured sources whose latest check is connected; Source contribution remains period event analytics. The health artifact contains no credentials. Its protected Add/Edit/Delete, Enable/Disable and Check actions require an operator or admin principal with both `rop` and `rop.sources.write`; an admin principal with `*` remains the global wildcard exception. Mailbox Edit uses generic cell-inline controls; Delete uses one concise direct confirmation. The bounded mailbox credential path is part of `rop.sources.write` and updates only the selected source's username/password environment references in `.env`; new generated references are placed in the `# ROP mailbox` section. It grants no Dashboard, Runs, Modules, global auth/settings or unrelated execution authority. Values never enter YAML. Username is visible only to a principal with this source-management capability, while password is always `********` when present or `—` when absent. Edit starts with an empty password: blank preserves it and a nonblank value replaces it. `/rop/sources.csv`, JSON APIs, audit, logs and artifacts exclude usernames, passwords and environment references and use `nosniff` and `no-store`.

## Purpose

This document records the currently implemented contract for the BeeUI-backed Operator Web Console in BeeAgent.

It describes:

- HTML routes;
- JSON API routes;
- source of truth for web runtime and read-model data;
- read-only/security rules;
- whitelisted artifacts permitted to be delivered through UI.

Document does not replace:

- `docs/ROADMAP.md` — iteration/status;
- `docs/product/ui_roadmap.md` — UI track planning;
- `docs/SDLC.md` — required checks;
- `docs/SECURITY.md` — secure development rules.

## Sources of truth

Source of truth for bind/runtime web mode:

- `config/settings.yml`
  - `web.host`
  - `web.port`
  - `web.open_browser`
  - `web.auth`

Source of truth for auth-config:

- `config/settings.yml`
  - `web.auth`
- `.env` / runtime env
  - actual auth secrets

Source of truth for UI read-model data:

- existing artifacts in `storage/`
  - `storage/runs/<run_id>/...`
  - `storage/interfaces/modules.json`
- `config/settings.yml`
  - `bitrix.widget`
- `storage/runs/<run_id>/rop_final_decisions.json`
  - artifact-first source for final decisions read-model and Bitrix widget `final_decisions` block
  - missing, malformed or unsafe artifact uses a computed read-only fallback from `classified_events.json` and `rop_ai_adjudicator_results.json`
  - GET/read-model fallback never writes storage
- `storage/runs/<run_id>/rop_ai_adjudicator_results.json`
  - source for AI adjudicator evidence in event detail and its JSON API
- `storage/interfaces/rop_web_projection_v2.json`
  - derived schema-v2 bounded manifest with `latest_run_id`, bounded `run_ids`, scalar `total_runs`, generation/revision metadata and controlled view references;
  - `available_runs` and `total_runs` are materialized metadata and never require a `storage/runs` scan during GET;
  - scoped `run_id` authorization uses only validated manifest membership and never opens a semantic view;
- `storage/interfaces/rop_web_projection_v2/<generation>/<sha256(run_id)>/<revision>/...`
  - immutable request-ready semantic views for Overview, Queue, Sources and dashboard API period variants;
  - a normal `/rop` or `/api/rop/dashboard` request reads the manifest and exactly one controlled requested view; it never reads v1 entries, global writeback state or raw run artifacts;
  - Queue is one canonical deduplicated row set with bounded membership metadata; Overview has separately materialized counters, series, source summaries and bounded previews;
- both projection layers are refreshed or regenerated only through supported ROP runtime/CLI paths, never by HTTP GET;
- normal ROP lifecycle refresh updates only the affected run generation/views and publishes the new manifest last; it does not bootstrap an absent projection or reconstruct the complete historical Web catalog;
- Web projection is persistent derived state. Ordinary deployments reuse compatible schema-v2 projections; presentation-only changes and additive optional v2 fields do not require regeneration;
- normal `./start.sh rop dashboard --period 7d` refreshes only the effective run in the bounded catalog. Full historical bootstrap/regeneration is explicit: `./start.sh rop dashboard --period 7d --rebuild-web-projection`;
- HTTP GET never migrates, repairs, regenerates or falls back to historical reconstruction. Breaking projection schema changes require an explicit compatibility or migration decision;
- publication writes and validates immutable views before the manifest replacement, so an interrupted publication preserves the previous valid manifest; projection failure does not alter canonical run, writeback or checkpoint artifacts;
- derived projection retention runs only after successful publication: v1 retains entry files referenced by the current and immediately previous indexes, while v2 retains every generation referenced by the current and immediately previous manifests; stale controlled derived entries/generations are best-effort pruned without touching canonical runs or attachments;
- an interrupted v2 publication removes only its own temporary or unpublished generation; publication readers retain one immediately previous publication as deterministic grace;
- missing or malformed manifest or requested view fails explicitly and recoverably through the supported `rop dashboard` regeneration path;
- canonical ROP run artifacts remain the business source of truth.

UI does not store a separate runtime state or create a second source of truth.

## Runtime foundation

Current contract implemented:

- UI-6 = enriched ROP dashboard/read-model;
- UI-7 = BeeUI-backed auth boundary.

- **BeeUI** – canonical web layer for BeeAgent;
- BeeAgent UI code is located in `src/beeagent_module/interfaces/ui/`;
- `app.py` creates embedded BeeUI app and BeeAgent read-only API routes;
- `adapter.py` contains adapter methods, custom pages and artifact access;
- `read_model.py` contains read-model and BeeUI `layout[]`;
- `artifacts.py` contains artifact allowlist;
- `bounded_read.py` is responsible for bounded/redacted previews;
- `locale.py` contains locale helper;
- thin CLI entrypoint in `src/beeagent_module/cli/web.py`;
- `config/beeui.yml` is a source of truth for navigation/pages/tabs/locale/component seed;
- ROP block composition is still in BeeAgent read-model layout builders and not fully in config;
- `config/start.py` calls `beeagent_module.cli.web.run_web`;
- legacy `src/beeagent_module/web` frozen;
- auth boundary implemented through BeeUI session/role layer;
- GET/read surfaces remain read-only by default; UI-8.8 blacklist Add/Update/Delete are explicit protected bounded POST exceptions, not runtime control endpoints;
- Queue `date_range` filter (UI-8.2) uses generic BeeUI Tabler Datepicker contract (Iteration 13.10) via `beeui>=0.23.0`;
- Queue toolbar (UI-8.3) uses canonical BeeUI Tabler toolbar contract (Iteration 13.11) via `beeui>=0.24.0`;
- ROP dashboard: KPI cards, processing funnel, source health, classification distribution, deterministic recommendations, attention events, attachment summary, evidence links;
- localization of UI: en default, ru via `?lang=ru` or persistent cookie `beeui_lang` (query parameter has priority), configuration in `config/beeui.yml`;
- the product dashboard (`/`) has customer-facing KPIs, a summary, quick links and Technical details in a collapsible section;
- `/rop` is rendered as a BeeUI generic adapter custom page;
- ROP page tabs use BeeUI progressive navigation with canonical SSR `href` values and controlled BeeUI icons; BeeAgent does not add tab-navigation JavaScript;
- browser artifact routes and shell belong to BeeUI;
- `/api/runs/{run_id}/artifacts/{artifact_id}` remains JSON envelope.

Entrypoint:

```bash
./start.sh web
```

CLI overrides:

```bash
./start.sh web --host 127.0.0.1 --port 8780 --no-open
```

Diagnostics of routes:

```bash
./start.sh routes
```

## HTML routes (BeeUI-backed)

Implemented HTML routes (through the BeeUI product console + custom BeeAgent routes):

The main product console pages supports `?lang=ru`:

- `/` — dashboard
- `/health` — health check
- `/runs` — run history
- `/runs/{run_id}` — run detail
- `/rop` — ROP operator dashboard (tabs: overview, queue, sources, blacklist)
- `/rop?tab=blacklist` — exact sender e-mail blacklist; mutation requires a known action, `operator`/`admin` authority, `rop` scope, CSRF validation/protection, product validation and audit. It grants no general runtime, CRM or mailbox execution authority. Future blacklisted messages use the existing `irrelevant` Bitrix path and show the classification override reason in ROP Event Detail.
- `/modules` — module diagnostics
- `/runs/{run_id}/artifacts` — browser artifact list/viewer route, BeeUI-owned HTML
- `/runs/{run_id}/artifacts/{artifact_id}` — browser artifact detail route, BeeUI-owned HTML

## HTML routes (event detail)

Implemented event detail HTML routes:

- `/rop/events/{event_id}` — ROP event detail review page (read-only)

Query parameters:

- `run_id` (required): run identifier
- `event_instance_id` (optional): additive run-local selector for a distinct processing occurrence when several items share the same public `event_id`; omitted for old runs and unique event ids.
- `lang` (optional, `en`/`ru`): locale override; In the absence of a parameter, the value cookie `beeui_lang` must be used (saved by BeeUI when selecting language through `?lang=`), otherwise default from `config/beeui.yml` must be used.

## Attachment download route (It40)

- `GET /rop/attachments/{attachment_id}/download?run_id=<run_id>&event_id=<event_id>` — authenticated/authorized forced download of an accepted original attachment.

Query parameters:

- `run_id` (required): run identifier
- `event_id` (optional): must match the manifest item when provided

Behavior:

- lookup only for safe manifest attachment id (never arbitrary filesystem path);
- invalid/unknown run/event/attachment ids and path traversal fail closed;
- response: forced `attachment`, `X-Content-Type-Options: nosniff`, `Cache-Control: no-store`, `application/octet-stream` (no inline render);
- route is protected by the existing BeeUI session auth + resource authorization (ROP scope); ROP-scoped principal cannot use it to read unrelated surfaces;
- Event Detail retains stored attachment metadata and this download action when `rop.attachments.enabled:false`; that switch disables semantic analysis only;
- raw attachment bytes is never released through JSON API/HTML content.

## JSON API routes

Implemented JSON API routes (through the BeeUI product console + custom BeeAgent routes):

- `/api/dashboard`
- `/api/runs`
- `/api/runs/{run_id}`
- `/api/modules`
- `/api/rop/dashboard`
- `/api/rop/events/{event_id}` — ROP event detail read-only JSON envelope
- `/api/runs/{run_id}/artifacts`
- `/api/runs/{run_id}/artifacts/{artifact_id}`
- `/api/bitrix/rop/widget` — Bitrix widget summary (read-only, token-protected)
- `/api/bitrix/rop/widget/events` — Bitrix widget events (alias for widget)
- `/api/bitrix/rop/widget/events/{event_id}` — Bitrix widget event detail (read-only, token-protected)

## Bitrix widget API contract

Routes:

- `GET /api/bitrix/rop/widget`
- `GET /api/bitrix/rop/widget/events`
- `GET /api/bitrix/rop/widget/events/{event_id}`

Config source of truth:

- `config/settings.yml`
  - `bitrix.widget.enabled`
  - `bitrix.widget.token_env`
  - `bitrix.widget.default_period`
  - `bitrix.widget.max_items`

Widget API response fields (MVP):

- `final_decisions` — bounded block from the final decisions read-model
  - `summary.total_events`, `summary.decision_source_counts`, `summary.attention_count`
  - `events[]` — per-event final decision fields:
    - `event_id`, `final_case_type`, `final_case_subtype`, `final_queue`, `final_action`
    - `final_decision_source`, `final_confidence`
    - `needs_attention`, nullable `attention_reason`
    - `automation_allowed`, `bitrix_write_allowed` (always false)
  - `summary` is recalculated from the bounded `events[]` returned by widget `max_items`

### ROP final decisions read-model contract

Source: `storage/runs/<run_id>/rop_final_decisions.json`

Structure:

```json
{
  "summary": {
    "total_events": 42,
    "decision_source_counts": {
      "ai_adjudicator": 12,
      "deterministic": 28,
      "deterministic_preserved": 2
    },
    "attention_count": 3
  },
  "events": [
    {
      "event_id": "...",
      "event_instance_id": "event-000001",
      "source_id": "...",
      "sender": "...",
      "subject": "...",
      "deterministic_case_type": "new_lead",
      "deterministic_case_subtype": null,
      "deterministic_queue": "sales",
      "deterministic_action": "review_new_lead",
      "deterministic_confidence": 0.85,
      "final_case_type": "new_lead",
      "final_case_subtype": null,
      "final_queue": "sales",
      "final_action": "review_new_lead",
      "final_decision_source": "ai_adjudicator",
      "final_confidence": 0.92,
      "needs_attention": false,
      "attention_reason": null,
      "automation_allowed": false,
      "bitrix_write_allowed": false,
      "base_classification": null,
      "duplicate": null
    }
  ]
}
```

Policy v1:

- AI adjudicator `ok` → AI fields, `automation_allowed=false`
- `low_confidence_preserve` → deterministic preserved, `needs_attention=true`, `automation_allowed=false`
- `deterministic_preserved` / `duplicate_unresolved` / `degraded` / `invalid` → deterministic preserved, `needs_attention=true`, `automation_allowed=false`
- No AI result → deterministic fields, `final_decision_source=deterministic`
- Invalid/unusable → `final_decision_source=fallback_policy`, `needs_attention=true`

Always `automation_allowed=false` and `bitrix_write_allowed=false`.

Additive It35 fields (backward-compatible):

- `base_classification: object | null` — module-returned original semantic classification preserved for audit (present when duplicate candidate context was passed and the module returned it; `null` for events without duplicate context / old runs).
- `duplicate: object | null` — bounded module-returned duplicate evidence (see duplicate evidence contract below); `null` for non-duplicate / old / malformed-safe events.
- `event_instance_id: string` — BeeAgent-owned run-local processing occurrence selector; it does not replace or alter public `event_id` and is not part of the module duplicate contract.
- Old or non-duplicate runs tolerate missing or `null` values for both fields; readers must not require them.

### ROP duplicate classification contract (It35)

Source: module-returned `base_classification` / `duplicate` blocks in `classified_events.json` and `rop_final_decisions.json`.

Event Detail classification (additive, backward-compatible):

- `classification.base_case_type` — `string`, original semantic case type from `base_classification` (empty when absent).
- `classification.duplicate` — `object | null`, bounded duplicate evidence:
  - `is_duplicate` — boolean
  - `resolution_status` — optional module resolution state: `confirmed`, `possible` or `not_duplicate`
  - `confidence` — number (`0.0 – 1.0`)
  - `reason_code` — string (e.g. `exact_email_body_match`, `near_duplicate_subject_body`, `duplicate_candidate_confirmed`)
  - `reason_path` — string array
  - `reasoning` — string (bounded)
  - `is_fallback` — boolean
  - candidate evidence:
    - `candidate_event_id` — string
    - `existing_lead_id` — string
    - `similarity_score` — number
    - `matched_fields` — string array
    - (candidate reason fields `reason_code` / `reason_path` / `reasoning` are preserved in the raw module block)
- `classification` fields `case_type`/`reason_code`/`confidence` etc. remain unchanged for non-duplicate events.
- `confirmed` remains terminal; `possible` is adjudicated only through the bounded AI duplicate decision, where rejection preserves `base_classification` and unavailable/invalid/low-confidence output preserves the base classification with an explicit `duplicate_unresolved` diagnostic (no manual-review terminal queue).
- Queue detail links retain `/rop/events/{event_id}` and add `event_instance_id` only when present, so repeated transport Message-ID occurrences open their own artifact-backed detail while old links remain valid.

Behavior / safety:

- old and non-duplicate runs render without duplicate fields (missing or `null` tolerated);
- malformed or unsafe restored duplicate evidence is **not** exposed — the read-model uses the existing safe computed fallback (warning emitted, no raw content rendered);
- dynamic Classification filter includes `Duplicate` only when duplicate rows exist (`case_type=duplicate` present in displayed queue/classified data); absent otherwise.

### Artifact allowlist additions (UI-8)

New allowlisted artifacts:

- `rop_ai_adjudicator_results.json` — AI adjudicator results for event detail and its JSON API
- `rop_ai_adjudicator_requests.json` — AI adjudicator requests
- `rop_ai_adjudicator_decisions.json` — AI adjudicator decisions
- `rop_final_decisions.json` — final decision read-model

### Event detail changes (UI-8)

`/rop/events/{event_id}?run_id=<run_id>` now shows:

- AI Adjudicator section when adjudicator data exists for the event
- Final Decision section with final fields, nullable subtype/attention reason and decision source

### Event detail recipient routing (It36)

`/rop/events/{event_id}?run_id=<run_id>` now shows a **Recipient routing** section when `rop_recipient_routing.json` exists for the run:

- `recipient` — resolved business recipient email (empty for ambiguous/unresolved)
- `recipient_evidence_source` — `original_recipient`, `to`, `source_recipient` or empty
- `recipient_status` — `resolved`, `ambiguous` or `unresolved`
- `proposed responsible` — matched Bitrix active user name/email
- `responsible_status` — `matched`, `not_found`, `ambiguous`, `connector_degraded` or `not_attempted`

The read-model also exposes `recipient_routing` and adds `rop_recipient_routing_json` to evidence artifact links. The section is read-only, additive and backward-compatible: runs without the routing artifact render no section and no warning is required.

New allowlisted artifact:

- `rop_recipient_routing.json` — bounded per-event recipient attribution and proposed Bitrix responsible evidence (`event_id`, `event_instance_id`, source provenance, recipient/responsible statuses); `read_only=true`, `draft_only=true`; no body/raw attachment content.

### Event detail deterministic and conversation sections (It39)

`/rop/events/{event_id}?run_id=<run_id>` now also shows two new additive sections:

- **Deterministic result** — deterministic semantic echelon separate from the final decision:
  - `deterministic.case_type` / `case_subtype` / `recommended_queue` / `correct_action`
  - `deterministic.confidence` / `reason_code` / `is_fallback`
  - derived from the `deterministic_*` fields of `classified_events.json`; absent → `available=false`
- **Conversation timeline** — full known conversation across runs/sources:
  - `conversation.events[]` — bounded cross-run/cross-source timeline (date, source_id, run_id, role, sender, subject, case_type, CRM outcome)
  - roles `root` / `reply` / `continuation`; built from exact RFC `Message-ID` / `In-Reply-To` / `References` ancestry within the same `client_id` using `storage/interfaces/rop_writeback_state.json` and current-run thread context; no fuzzy sender/subject/time matching; no CRM mutation authority
  - absent write-back state → `available=false`

The read-model exposes the new `deterministic` and `conversation` objects, so the JSON API distinguishes deterministic result, AI proposal (`ai_adjudicator`), final semantic result (`final_decision`) and conversation/CRM evidence (`conversation` + `bitrix`).

New allowlisted artifacts:

- `rop_conversation.json` — per-run BeeAgent-owned conversation relation (conversation_id, roles, exact RFC message-id evidence, client/source scope)
- `bitrix_outbound_correlation.json` — read-only outbound-correlation evidence (exact outbound email Message-ID bridge; Message-ID is read from the real Bitrix location `SETTINGS.MESSAGE_HEADERS.Message-Id` case-insensitively plus the legacy locations; `bridge_exact=true` only when the inbound RFC ancestry references a proven outbound identifier; the bridge authorizes `attach_existing` only when the canonical CRM entity identity (entity type/type-id/entity-id) matches a canonical trusted CRM target from write-back state with provenances `beeagent_created`/`thread_resolved`, while the outbound activity responsible is diagnostic only and never replaces the trusted responsible; a previously proven `target_provenance=bitrix_outbound_exact` target may also serve as the trusted root for the next exact RFC hop; otherwise candidate-only/deferred with zero mutation authority)

### Locale-aware reason display (UI-8.4)

`/rop/events/{event_id}?run_id=<run_id>&lang=ru` and `?lang=en` now render three key explanations in the requested locale using structured reason codes instead of raw AI prose:

- **Classification reason** — derived from `reason_code` via the product-owned BeeAgent reason catalog
- **AI Adjudicator reason** — derived from `ai_reason_code` and `ai_evidence_codes`
- **Final Decision attention reason** — derived from `attention_reason_code` and `attention_evidence_codes`

New adjudicator artifacts (`rop_ai_adjudicator_results.json`) contain additive fields:

- `ai_reason_code` — structured reason code from the allowlist
- `ai_evidence_codes` — bounded evidence code array

New final-decision artifacts (`rop_final_decisions.json`) contain additive fields:

- `attention_reason_code` — structured reason code derived from the merge/policy decision
- `attention_evidence_codes` — evidence codes forwarded from the adjudicator

The Event Detail read-model and JSON API expose new localized display fields:

- `classification.reason_display`
- `ai_adjudicator.ai_adjudicator_reason_display`
- `final_decision.attention_reason_display`

Raw reason fields (`reason`, `ai_reason`, `attention_reason`) and structured codes remain available in the API for audit and backward compatibility.

Historical artifacts without an `ai_reason_code` key render a localized legacy fallback and warning. Present empty or invalid codes and unknown non-empty codes render explicit bounded diagnostics.

Locale switching remains a read-only artifact projection and does not call the AI provider, mailbox, Bitrix, module or capability.

### ROP dashboard API changes (UI-8)

`/api/rop/dashboard` now exposes:

- `ai_adjudicator_summary` — adjudicator available/eligible/used/degraded counts
- `final_decisions` — artifact-first or computed read-only per-event projection with nested `summary` and `events`
- `final_decision_summary` — compatibility alias for `final_decisions.summary`

Auth:

- route-level `Authorization: Bearer <token>`;
- token value is read from env variable, whose name is given through `bitrix.widget.token_env`;
- widget routes is not protected by BeeUI session auth, because it's integration boundary for Bitrix embedding;
- at `bitrix.widget.enabled=true` routes still protected widget Bearer token.

Behavior:

- read-only;
- artifact-backed;
- Read final decisions read-model;
- does not call Bitrix REST;
- does not make CRM/Bitrix/mailbox/module/capability mutations;
- summary/list route at `bitrix.widget.enabled=false` returns safe disabled envelope;
- detail route at disabled widget returns unavailable/error envelope.

List/detail payload in the current scope must include:

- `title`
- `priority`
- `sender`
- `subject`
- `summary`
- `recommended_action`
- `recommended_queue`
- `target_bitrix_category`
- `bitrix_status`
- `confidence`
- `ai_used`
- `reason`
- `safe_to_execute`
- `requires_human_confirmation`
- `evidence_links`
- `detail_url`

## Bitrix embedded app (UI-8.5)

BeeAgent ROP Web Console can open inside Bitrix24 as a **Server-Side Local Application with User Interface**. An authorized Bitrix24 user opens the application from the portal and receives the existing read-only `/rop` console inside an iframe without a separate BeeAgent login. No separate frontend or persistent URL credentials are introduced.

### Config

Source of truth: `config/settings.yml` → `bitrix.embedded_app`:

```yaml
bitrix:
  embedded_app:
    enabled: false
    portal_origin: ""
    default_role: "viewer"
    request_timeout: 10
```

Rules:

- `bitrix.embedded_app.enabled=true` requires `web.auth.enabled=true`;
- `portal_origin` is the exact HTTPS origin (without path, query, trailing slash);
- launch input does not choose role: verified Bitrix user to receive configured `default_role` (`viewer` by default; configured `operator` is limited to a trusted Local App audience; embedded `admin` is not allowed);
- At `enabled=true` BeeUI receives `security.frame_ancestors=[portal_origin]`, `auth.cookie_samesite="none"`, `auth.cookie_secure=true` and canonical `auth.session_age_max`;
- BeeAgent does not contain Bitrix user-ID allowlist: access controlled by Bitrix24.

### Routes

Actual Bitrix24 Local Application payload (verified in production): `AUTH_ID`, `AUTH_EXPIRES`, `REFRESH_ID`, `member_id`, `PLACEMENT`, `status` — Bitrix **does not send** the `DOMAIN` field. Binding uses `member_id`; the domain always comes from the configured `portal_origin` (outbound requests are never constructed from request data).

#### `POST /bitrix/rop/install`

One-time handler for linking one deployment to one Bitrix portal.

- accepts a bounded `application/x-www-form-urlencoded` form; required fields are `member_id`, `AUTH_ID`, `AUTH_EXPIRES`; `PROTOCOL` (optional, `https` or `1`), `DOMAIN` (optional);
- `AUTH_ID` and `AUTH_EXPIRES` are required for initial installation and reinstallation: expiry (`AUTH_EXPIRES`) and the active Bitrix current user are checked through `user.current` before any state write; invalid/inactive/expired/rejected installation creates no artifact;
- if `DOMAIN` is supplied, defense in depth requires the origin from `DOMAIN` to match the configured `portal_origin`, otherwise `403 portal_mismatch`; this check precedes any outbound request;
- stored state must match the configured `portal_origin`/`portal_domain`, otherwise `409 installation_portal_mismatch`;
- Additional Bitrix fields (`PLACEMENT`, `PLACEMENT_OPTIONS`, `REFRESH_ID`, `status`, `APP_SID`, `LANG` and any others) are ignored — not stored, not logged;
- the body is bounded (a strict streaming size limit, field count limit, duplicate key rejection and value length limits for used fields);
- requires an HTTPS request (HTTPS is determined by the ASGI request scheme; a trusted reverse proxy sets the scheme, while the client’s `X-Forwarded-Proto` header is not trusted);
- binding: after successful verification, the first `member_id` is saved atomically (exclusive create) in the fixed artifact `storage/interfaces/bitrix_rop_app.json` (only normalized `portal_domain`/`portal_origin` from config, `member_id`, `installed_at`, `contract_version`); on a race, state is reread and the binding checked; a different `member_id` → `409 conflicting_installation`;
- install performs the complete launch flow: creation of viewer session and `303` on `/rop` (Bitrix actually delivers open-context on install URL);
- does not store or log OAuth credentials;
- `no-store` responses with `Referrer-Policy: no-referrer`.

#### `POST /bitrix/rop/launch`

Launch handler for application open context. Only POST; GET on `/bitrix/rop/launch` returns `405` and never processes OAuth values (query- parameters are not used).

- accepts bounded `application/x-www-form-urlencoded` form; Only bounded `AUTH_ID`, `AUTH_EXPIRES` (mandatory), `member_id` (mandatory) and optional `REFRESH_ID` are used; `DOMAIN` is not required (Bitrix does not send it), but if available is checked against configured `portal_origin`;
- `AUTH_EXPIRES` is taken as unix timestamp or as the number of seconds of life (TTL), e.g. `3600`;
- Additional Bitrix fields (`PLACEMENT`, `PLACEMENT_OPTIONS`, `APP_SID`, `status`, `LANG` and any other) are ignored — not stored or logged;
- the body is bounded (a strict streaming size limit, field count limit, duplicate key rejection and value length limits for used fields);
- Demands HTTPS request (scheme ASGI request);
- before any outbound request: stored `portal_origin`/`portal_domain` must match the configured origin, optional `DOMAIN` must also match it when present, then `member_id` is checked against installation state; the outbound REST call always uses the configured `portal_origin` (`https://<portal_origin>/rest/user.current`) and is never constructed from request data;
- Rejects malformed and expired launch;
- checks the current user through the official Bitrix REST `user.current` only against the configured portal; the Bitrix application requires the **`user`** (Users) permission, otherwise Bitrix rejects the call with `insufficient_scope`;
- rejects invalid/rejected tokens, inactive users, timeouts and malformed REST responses; refusal returns `reason` (for example, `token_rejected`) and bounded `bitrix_error` (for example, `insufficient_scope`, `invalid_token`) without token values;
- neither stores nor logs `AUTH_ID`/`REFRESH_ID`;
- Creates BeeUI principal session for verified Bitrix user with configured `viewer` or `operator` role; browser input cannot select the role and embedded `admin` is not allowed;
- Sets `HttpOnly; Secure; SameSite=None` cookie through BeeUI public helper;
- Returns `303 See Other` to `/rop` with `no-store` and `Referrer-Policy: no-referrer`.

### Session / iframe policy

- At `embedded_app.enabled=true` framing, only configured portal is permitted via BeeUI `frame-ancestors` CSP (instead of `X-Frame-Options: DENY`);
- session cookie remains `HttpOnly` and `Secure`;
- `AUTH_ID`, `REFRESH_ID` and session secrets are not available in URL, HTML, JS, logs and artifacts;
- The existing local BeeAgent login through `/auth/login` is retained.

### Backward compatibility

- `/api/bitrix/rop/widget*` remains compatible and protected widget Bearer token;
- `GET /rop` without valid BeeUI session remains closed (redirect on `/auth/login` or `401`);
- GET routes remains read-only.

## Auth mode (UI-7)

BeeAgent Web Console supports a config-driven auth boundary through the BeeUI session/role layer. BeeUI owns login/logout/session/CSRF. BeeAgent owns config/env policy, bootstrap, CLI rotation, route protection and server-side resource authorization.

Auth settings live in `config/settings.yml` → `web.auth`:

```yaml
web:
  auth:
    enabled: false
    mode: beeui_session
    session_secret_env: BEEAGENT_WEB_SESSION_SECRET
    principals:
      - id: admin_1
        username: admin1
        role: admin
        scopes: ["*"]
        token_env: BEEAGENT_WEB_ADMIN1_TOKEN
```

The real secrets only lives in env:

- `BEEAGENT_WEB_SESSION_SECRET` – secret for HMAC- signatures session cookie
- `BEEAGENT_WEB_ADMIN1_TOKEN`, `BEEAGENT_WEB_ADMIN2_TOKEN` – token for authentication

Secrets is never stored in `settings.yml`.

### Principal model (UI-8.6)

```text
principal identity = exact username + token
authority = role
resource access = scopes
```

- local login is attached to exact configured `username + token` pair;
- successful session receives canonical configured principal `id` (not arbitrary browser `user_id`);
- `role` remains only authority level: `viewer` / `operator` / `admin`;
- `scopes` defines resource access: `*` (full access), `dashboard`, `rop`, `runs`, `modules`;
- `scopes` is mandatory for each principal and is validated by fail-fast;
- `["*"]` is the only permissible wildcard: wildcard that is not combined with other scopes;
- Different principals with the same resolved token value are rejected on startup without secret;
- generic auth failure does not reveal which credential is incorrect.

### Bootstrap

- `ensure_web_auth_env(...)` runs before `load_settings(...)`;
- at `web.auth.enabled=true` missing or empty auth env values must be generated automatically;
- `.env` empty keys are updated in-place;
- missing keys are appended to `.env`;
- values are set in `os.environ` for the current process;
- a new `.env` receives `0600` on POSIX; bootstrap and rotation preserve the existing `.env` mode and group;
- in stdout only `KEY=<generated>` is printed.

### Rotation CLI

```bash
./start.sh auth rotate <principal-id-or-username>
./start.sh auth rotate all
./start.sh auth rotate all --logout-all
./start.sh auth rotate session
```

rotation requires restart web app. Session secret not to be printed.

### Behavior

- `web.auth.enabled: false` (default): Current local/dev behaviour without auth.
- `web.auth.enabled: true`: session-based auth is enabled through BeeUI with server-side authorization;
- external exposure with `web.auth.enabled=false` must be considered rejected/fail-fast under settings policy.

### Protected routes (when enabled)

HTML routes:

- `/`, `/rop`, `/rop/events/{event_id}`, `/rop/attachments/{attachment_id}/download`, `/runs`, `/runs/{run_id}`, `/runs/{run_id}/artifacts`, `/runs/{run_id}/artifacts/{artifact_id}`, `/modules`

API routes:

- `/api/*`

Any non-public path (including unknown/future protected surfaces) is protected: default-deny for non-wildcard principals. even the unknown `/api/...` path with auth required authentication before route-level returns.

### Public routes

- `/health` – public sanitized health check (without details runtime state)
- `/static/*` — public static assets
- `/auth/*` — auth routes owned by BeeUI (login/logout/CSRF)
- `/api/bitrix/rop/widget*` – integration boundary, does not require BeeUI session cookie, but at enabled widget requires route-level Bearer token
- `/bitrix/rop/install`, `/bitrix/rop/launch` - Bitrix embedded app entry points (required HTTPS and `bitrix.embedded_app.enabled=true`; at disabled return bounded error)

### Resource authorization (UI-8.6)

Server-side authorization is performed by the central BeeAgent policy at canonical session identity + the current config:

- `admin + scopes=["*"]` retains full access to all HTML/API/resource routes;
- `viewer + scopes=["rop"]` (and any other non-wildcard principal with `rop`) receives:
  - `/rop`, Event Detail, `/api/rop/*`;
  - bounded ROP-owned evidence artifacts of allowlist (`/runs/{run_id}/artifacts/{allowlisted_id}`);
  - Dashboard, Runs, Modules, unrelated runs/artifacts/API;
- unknown protected surface → default-deny;
- navigation visibility reflects authorization, but does not replace server-side enforcement;
- ROP-only principal after login reaches `/rop` (landing redirect);
- verified Bitrix external principal (user_id not in `web.auth.principals`) remains bounded ROP-only with its configured `viewer` or trusted Local App `operator` role; embedded `admin` is not allowed.

### Unauthenticated / forbidden response

- unauthenticated HTML: redirect to `/auth/login`;
- unauthenticated API: `401` JSON envelope (`code: "unauthenticated"`);
- authenticated unauthorized: `403` JSON envelope (`code: "forbidden"`).

```json
{
  "ok": false,
  "read_only": true,
  "error": { "code": "unauthenticated", "message": "Authentication required" },
  "warnings": [],
  "meta": {}
}
```

### Session

Session is controlled by BeeUI through the signed cookie `beeui_session`. Session secret is read from env on `web.auth.session_secret_env`. Session stores canonical principal `user_id` (identifies principal in `web.auth.principals`) and `role`.

### Roles

- `viewer` – dashboard/run/ROP (read-only) view
- `operator` – operator-level access (future)
- `admin` – admin-level access (future config/actions)

Supported by `viewer` / `operator` / `admin`. Role does not define resource scope: resource access only `scopes`. GET/read routes remains read-only; UI-8.8 blacklist actions are explicit bounded POST exception with server-side authority, CSRF, validation and audit.

### Rollout

rollout UI-8.6 mandatory invalidation/rotation old sessions and credentials:

- session secret rotation (`./start.sh auth rotate all --logout-all` or `session`) cancels all existing signed cookies;
- principal token rotation (`./start.sh auth rotate <principal-id-or-username>`) requires re-entry;
- in `web.auth.principals[]` for each principal the explicit `scopes` is mandatory.

## Artifact routes

Implemented artifact routes:

- `/runs/{run_id}/artifacts` — browser HTML route
- `/runs/{run_id}/artifacts/{artifact_id}` — browser HTML route
- `/api/runs/{run_id}/artifacts` – JSON (List of access artifacts)
- `/api/runs/{run_id}/artifacts/{artifact_id}` — JSON envelope (machine-readable)

Rules:

- Access to artifacts is based on allowlisted `artifact_id`, not on the arbitrary file name;
- browser-routes (`/runs/...`) returns BeeUI HTML;
- API-route (`/api/runs/...`) returns bounded/redacted JSON envelope;
- Arbitrary file names and path-like values are rejected;
- raw `.eml` and attachment content are not surrendered.

### Artifact viewer (browser route)

Browser route shows bounded/redacted artifact preview through BeeUI. The HTML- Inner Structure viewer is not fixed by this document.

### Examples of responses

`GET /api/runs/{run_id}`

```json
{
  "ok": true,
  "read_only": true,
  "data": {
    "run_id": "live-review-2026-05-15",
    "summary": {
      "status": "ok",
      "summary": "batch completed"
    },
    "source_diagnostics": {
      "selection_mode": "all_enabled",
      "status": "ok",
      "aggregate": {
        "source_count": 2,
        "loaded_source_count": 1,
        "degraded_source_count": 1
      }
    },
    "intake_metadata": {
      "loaded_item_count": 3,
      "source_count": 2,
      "sources": [
        {
          "source_id": "hotline_mailbox",
          "loaded_count": 3,
          "status": "ok"
        }
      ]
    },
    "normalized_count": 3,
    "classified_count": 3,
    "has_attachment_extraction": false,
    "layout": {
      "primary_artifacts": [
        "operator_summary_json",
        "classified_events_json",
        "rop_review_table_tsv"
      ]
    }
  },
  "warnings": [],
  "meta": {}
}
```

`GET /api/rop/dashboard?run_id=live-review-2026-05-15-multi`

```json
{
  "ok": true,
  "read_only": true,
  "data": {
    "run_id": "live-review-2026-05-15-multi",
    "status": "ok",
    "summary": {
      "status": "ok",
      "summary": "batch completed"
    },
    "source_diagnostics": {
      "selection_mode": "all_enabled",
      "status": "ok",
      "aggregate": {
        "source_count": 2,
        "loaded_source_count": 1,
        "degraded_source_count": 1
      }
    },
    "intake_metadata": {
      "loaded_item_count": 3,
      "source_count": 2
    },
    "sources": [
      {
        "source_id": "hotline_mailbox",
        "display_name": "Welding Hotline mailbox",
        "status": "ok"
      },
      {
        "source_id": "sales_mailbox",
        "display_name": "Welding Sales mailbox",
        "status": "degraded"
      }
    ],
    "classified_count": 3,
    "case_type_counts": {
      "new_lead": 2,
      "duplicate": 1
    },
    "priority_counts": {
      "high": 1,
      "medium": 2
    },
    "fallback_count": 1
  },
  "warnings": [],
  "meta": {}
}
```

`GET /api/rop/events/{event_id}?run_id={run_id}`

```json
{
  "ok": true,
  "read_only": true,
  "data": {
    "run_id": "smoke-it31",
    "event_id": "evt-001",
    "source": {
      "source_id": "hotline_mailbox",
      "source_type": "mailbox_readonly",
      "source_display_name": "Welding Hotline mailbox",
      "client_id": "welding"
    },
    "message": {
      "sender": "client@example.com",
      "subject": "Welding machine inquiry",
      "body_preview": "bounded sanitized email text",
      "body_preview_truncated": true,
      "body_preview_chars": 4000,
      "body_preview_source": "text_plain"
    },
    "classification": {
      "case_type": "new_lead",
      "priority": "high",
      "confidence": 0.95,
      "is_fallback": false,
      "recommended_queue": "sales",
      "correct_action": "create_lead",
      "should_rop_see": true
    },
    "thread": {
      "thread_id": "thr_001",
      "previous_event_ids": ["evt-000"],
      "reply_or_forward": false,
      "thread_connection": "subject_fallback"
    },
    "ai_assist": {
      "ai_assist_status": "not_applied"
    },
    "bitrix": {
      "available": false
    },
    "attachments": [],
    "evidence_links": [
      {
        "artifact_id": "normalized_events_json",
        "available": true,
        "url": "/runs/smoke-it31/artifacts/normalized_events_json"
      },
      {
        "artifact_id": "classified_events_json",
        "available": true,
        "url": "/runs/smoke-it31/artifacts/classified_events_json"
      }
    ],
    "warnings": [],
    "read_only": true
  },
  "warnings": [],
  "meta": {}
}
```

Example of response for a non-existent event:

```json
{
  "ok": false,
  "read_only": true,
  "error": {
    "code": "not_found",
    "message": "Event evt-999 not found in run smoke-it31"
  },
  "warnings": [],
  "meta": {}
}
```

Example of response for non-allowlisted artifact:

```json
{
  "ok": false,
  "read_only": true,
  "error": {
    "code": "invalid_id",
    "message": "Artifact 'raw_eml' is not allowlisted"
  },
  "warnings": [],
  "meta": {}
}
```

## Artifact allowlist (UI-4 BeeUI-backed)

Permitted artifact ID and their fixed mapping inside run directory:

| ID                                | Relative path                                         |
| --------------------------------- | ----------------------------------------------------- |
| `run_json`                        | `run.json`                                            |
| `operator_summary_json`           | `operator_summary.json`                               |
| `source_diagnostics_json`         | `source_diagnostics.json`                             |
| `intake_metadata_json`            | `intake_metadata.json`                                |
| `normalized_events_json`          | `normalized_events.json`                              |
| `classified_events_json`          | `classified_events.json`                              |
| `attachment_extraction_json`      | `attachment_extraction.json`                          |
| `rop_review_table_tsv`            | `rop_review_table.tsv`                                |
| `rop_current_state_json`          | `rop_current_state.json`                              |
| `bitrix_reconciliation_json`      | `bitrix_reconciliation.json`                          |
| `module_result_json`              | `module-beeagent-rop/module_result.json`              |
| `rop_summary_result_json`         | `module-beeagent-rop/rop_summary_result.json`         |
| `lead_classification_result_json` | `module-beeagent-rop/lead_classification_result.json` |
| `steps_json`                      | `steps.json`                                          |
| `rop_mvp_pack_json`               | `rop_mvp_pack.json`                                   |
| `rop_mvp_report_md`               | `rop_mvp_report.md`                                   |
| `mailbox_selection_json`          | `mailbox_selection.json`                              |
| `mail_thread_index_json`          | `mail_thread_index.json`                              |
| `mail_thread_context_json`        | `mail_thread_context.json`                            |
| `rop_ai_assist_requests_json`     | `rop_ai_assist_requests.json`                         |
| `rop_ai_assist_decisions_json`    | `rop_ai_assist_decisions.json`                        |
| `rop_ai_assist_results_json`      | `rop_ai_assist_results.json`                          |
| `rop_final_decisions_json`        | `rop_final_decisions.json`                            |
| `rop_writeback_summary_json`      | `rop_writeback_summary.json`                          |

UI does not serve arbitrary files from `storage/`. `artifact_id` maps to a fixed allowlisted relative path. The current implementation excludes `rop_evaluation.json` from the generic artifact allowlist.

`rop_writeback_summary.json` – read-only per-run projection of write-back state (Iteration 37): bounded outcome/status per event (`create_lead` / `attach_existing` / `deferred`), source of truth — `storage/interfaces/rop_writeback_state.json`. The projection does not contain credentials, raw `.eml` and raw attachment content.

ROP dashboard supports the period query parameter: `?period=today`, `?period=yesterday`, `?period=7d`, `?period=30d`, `?period=90d`, `?period=365d`, `?period=all`. The default period comes from `config/settings.yml` → `rop.dashboard.default_period` (default `7d`). The period filters classified events by `event_date`/`received_at`/`timestamp`. Period `all` disables filtering.

### Cross-run period aggregation (ROP dashboard)

ROP dashboard aggregates events by period for the selected client:

- `run_id` is anchor run and client scope for the chosen run operational evidence;
- `business_kpi`, `series` and period queues aggregate unique same-client events from relevant successful runs (degraded/error runs are excluded with the bounded warning `incomplete_run_skipped`);
- stable base identity Events: `client_id + source_id + (message_id → x_email_id → event_id)`;
- within one run, repeated occurrences of the same stable base (for example, one email with the same `message_id` appearing multiple times) receive distinct deterministic occurrence slots (ordered by source timestamp, with `event_id`/`event_instance_id` as tie-breakers) and remain separate;
- the cross-run canonical winner is the newest run per `(client_id, source_id, stable base, occurrence slot)`, so the same email across mailbox polls/runs does not multiply in `7d/30d/all`; `run_id + event_instance_id` is not a cross-run business identity;
- `event_instance_id` - BeeAgent-owned run-local processing occurrence selector: is used only for ordering/disambiguation inside run and artifact/UI lookup, is not transferred as domain matching signal and does not replace public `event_id`;
- queue identity is `(origin_run_id, source_id, event_id, event_instance_id)` with legacy-safe fallback (empty selector for old run runs); Different source events with the same `event_id` do not collide; The different occurrence of one `event_id` inside run must be kept separately;
- attachment items (`attachment_extraction.json`) carry the additive `event_instance_id` field to bind each item to its run-local occurrence; an occurrence of one `event_id` receives only its own attachment items; a legacy item without `event_instance_id` is bound only when exactly one occurrence matches, otherwise it is attributed to none of the repeated occurrences; the `attachment_refused` KPI uses occurrence-aware identity;
- `latest_selection`, threads, AI evidence, evidence links and source health remain anchor-run specific;
- queue/detail links uses origin `run_id` events;
- period filtering applies to the aggregated business view;
- malformed optional artifacts (`bitrix_reconciliation.json`, `attachment_extraction.json`) are ignored with the bounded warning `malformed_optional_artifact`; aggregate-only attachment counters are not attributed to events (warning `attachment_aggregate_unscoped`).
- `team_leaderboard` in materialized Overview projection - monthly top-5 canonical `case_type == new_lead` events with safe effective responsible assignment. This exact `matched` recipient routing or configured write-back fallback only with routing `not_found` and authoritative `rop_writeback_state.json` fallback assignment. Current UTC calendar month is compared to `rop.dashboard.leaderboard.plan_lead`; fallback display name is set to `bitrix.writeback.user_name_fallback`. Ambiguous, degraded and unsafe routing are not translated into fallback. so `business_kpi.new_leads` may differ from the sum of leaderboard rows if classified lead does not have safe effective responsible. Percentage may exceed 100% and visual progress is limited to 100%; leaderboard is not deal/revenue KPI.

ROP Queue supports the `bitrix_status` filter for artifact-backed CRM status (`matched`, `lost`, `ambiguous`, `degraded`, `unreconciled`) and leads to Event Detail. Current-state projection (`rop_current_state.json`) and optional `bitrix_reconciliation.json` remain read-only evidence without POST actions or write-back.

Rejected:

- raw `.eml`
- raw attachments
- arbitrary files
- logs with secrets
- env/config secrets
- mailbox password values
- provider tokens
- mailbox source content beyond normalized/sanitized artifacts

### ROP dashboard contract (UI-6 — enriched)

`GET /api/rop/dashboard` returns source-aware ROP dashboard read-model with extended fields.

Supported query parameters:

- `run_id` — optional explicit run selection; If the parameter is not transmitted, latest run must be used;
- `period` — dashboard period filter: `today`, `yesterday`, `7d`, `30d`, `90d`, `365d`, `all` (default defined by `config/settings.yml` → `rop.dashboard.default_period`);
- `tab` – HTML page tab selector for `/rop`;
- `lang` is HTML page locale selector for `/rop`.

`/api/rop/dashboard` takes `run_id` and `period`.

Existing UI-5 fields retained (backward-compatible).

New fields in UI-6 enriched payload (It30):

- `business_kpi` – Business metrics:
  - `processed_events`, `processed_emails`;
  - `new_leads`, `existing_clients`, `follow_ups`;
  - `high_priority`, `needs_review`;
  - `lost_in_bitrix`, `ambiguous_or_duplicate`, `unreconciled`;
  - `source_degraded`, `attachment_refused`, `bitrix_errors`;
- `series` — chart-ready series:
  - `processed_by_day` — processed events over time (labels + series with Processed/High priority);
  - `classification_distribution` — case type distribution;
  - `bitrix_distribution` — matched/lost/ambiguous/unreconciled;
  - `source_contribution` — events per source;
- `period` — current period;
- `period_start_utc`, `period_end_utc` is the boundary of the period;
- `time_basis` — basis used: `event_timestamp`, `run_generated_at`, `run_mtime_fallback`, `mixed`, `unknown`.

UI-6 adds fields:

- `latest_selection` — latest/N selection evidence:
  - `selected_count`, `strategy`, `source_count`, `sources[]`;
  - `newest_message_at`, `oldest_message_at`;
  - `warnings`, `evidence_artifact_id`;
- `thread_summary` — thread evidence summary:
  - `thread_count`, `events_with_thread_context`;
  - `reply_or_forward_count`, `linked_by_references_count`;
  - `linked_by_subject_fallback_count`;
  - `source_client_scoped_fallback_count`;
  - `warnings`, `evidence_artifact_ids[]`;
- `threads[]` — thread groups with per-thread event list;
- `ai_assist_summary` — AI assist evidence:
  - `evidence_available`, `eligible_count`, `request_count`;
  - `ok_count`, `used_count`, `degraded_count`;
  - `low_confidence_count`, `status_counts{}`;
- `ai_assist_events[]` — per-event AI assist status.

HTML `/rop` uses BeeUI tabs:

- `overview`
- `queue`
- `sources`
- `blacklist`

Returned data (UI-6 enriched payload):

- `selected_run_id` is the chosen run ID;
- `available_runs` – bounded recent run-id window of validated `rop_web_projection_v2.json` manifest (`run_ids`, fixed bound), is not the result of a `storage/runs` scan at GET;
- `total_runs` - scalar materialized total run count of validated projection v2 manifest (not `available_runs`);
- `kpis` - Combined KPI:
  - `total_runs` – scalar materialized total run count of projection index;
  - `source_count`, `loaded_source_count`, `degraded_source_count`;
  - `fetched_count`, `loaded_count`, `malformed_count`;
  - `normalized_count`, `classified_count`, `classification_failed_count`, `fallback_count`;
  - `high_priority_count`, `medium_priority_count`, `low_priority_count`;
  - `attachment_count`, `attachment_preview_count`, `attachment_refused_count`, `attachment_blocked_count`;
  - `review_tsv_available`;
- `funnel` — processing funnel stages;
- `source_health` — per-source health with `reason`, `fetched_count`, `loaded_count`, `malformed_count`, `classified_count`, `fallback_count`;
- `classification_distribution` — `case_type_counts`, `priority_counts`, `reason_code_counts`, `fallback_count`;
- `attachment_summary` – aggregate counts without raw content;
- `recommendations` — deterministic operator recommendations;
- `attention_events` — priority-ordered classified events (max 500);
- `evidence_links` — allowlisted artifact links with availability flag;
- `warnings` — missing/malformed/degraded warnings.

Backward-compatible fields retained:

- `run_id`, `summary`, `source_diagnostics`, `intake_metadata`;
- `sources[]`, `classified_count`, `case_type_counts`, `priority_counts`, `fallback_count`, `normalized_count`, `has_attachment_extraction`.

### Example of response (UI-6 /api/rop/dashboard)

```json
{
  "ok": true,
  "read_only": true,
  "data": {
    "selected_run_id": "run-rich-001",
    "available_runs": ["run-rich-001", "run-other"],
    "kpis": {
      "total_runs": 2,
      "run_status": "ok",
      "source_count": 2,
      "loaded_source_count": 2,
      "degraded_source_count": 1,
      "fetched_count": 15,
      "loaded_count": 13,
      "malformed_count": 2,
      "normalized_count": 5,
      "classified_count": 5,
      "fallback_count": 1,
      "high_priority_count": 2,
      "medium_priority_count": 2,
      "low_priority_count": 1,
      "attachment_count": 6,
      "attachment_preview_count": 3,
      "review_tsv_available": true
    },
    "funnel": [
      { "stage": "Configured Sources", "count": 2 },
      { "stage": "Enabled Sources", "count": 2 },
      { "stage": "Fetched Items", "count": 15 },
      { "stage": "Loaded Items", "count": 13 },
      { "stage": "Normalized Events", "count": 5 },
      { "stage": "Classified Events", "count": 5 },
      { "stage": "Review Candidates", "count": 3 }
    ],
    "source_health": [
      {
        "source_id": "hotline_mailbox",
        "display_name": "Welding Hotline mailbox",
        "status": "ok",
        "reason": null,
        "fetched_count": 5,
        "loaded_count": 5,
        "malformed_count": 0,
        "classified_count": 3,
        "fallback_count": 0
      }
    ],
    "classification_distribution": {
      "case_type_counts": {
        "new_lead": 3,
        "existing_deal": 1,
        "irrelevant": 1
      },
      "priority_counts": { "high": 2, "medium": 2, "low": 1 },
      "reason_code_counts": {
        "new_contact_no_existing_lead": 1,
        "existing_deal_followup": 1
      },
      "fallback_count": 1
    },
    "attachment_summary": {
      "total_attachments": 6,
      "preview_available_count": 3,
      "refused_count": 2,
      "blocked_count": 2,
      "unsupported_count": 1,
      "oversized_count": 0,
      "extraction_error_count": 0
    },
    "recommendations": [
      {
        "code": "review_high_priority",
        "severity": "warning",
        "title": "Review high-priority events",
        "message": "2 high-priority classified events need operator review.",
        "count": 2
      }
    ],
    "attention_events": [
      {
        "event_id": "evt-001",
        "source_id": "hotline_mailbox",
        "source_display_name": "Welding Hotline mailbox",
        "sender": "lead@example.com",
        "subject": "Welding equipment inquiry",
        "case_type": "new_lead",
        "priority": "high",
        "confidence": 0.95,
        "reason_code": "new_contact_no_existing_lead",
        "is_fallback": false,
        "attachment_count": 2,
        "review_reason": "High priority"
      }
    ],
    "evidence_links": [
      {
        "artifact_id": "operator_summary_json",
        "label": "Operator summary",
        "available": true,
        "url": "/runs/run-rich-001/artifacts/operator_summary_json"
      }
    ],
    "warnings": [],
    "run_id": "run-rich-001",
    "summary": { "status": "ok", "summary": "batch completed with results" },
    "sources": [
      {
        "source_id": "hotline_mailbox",
        "display_name": "Welding Hotline mailbox",
        "status": "ok"
      }
    ],
    "classified_count": 5,
    "case_type_counts": { "new_lead": 3, "existing_deal": 1, "irrelevant": 1 },
    "priority_counts": { "high": 2, "medium": 2, "low": 1 },
    "fallback_count": 1
  },
  "warnings": [],
  "meta": {}
}
```

### HTML route /rop (UI-6)

`GET /rop` renders a BeeUI generic adapter custom page for the rich ROP dashboard.

Supported query parameters:

- `run_id` — optional explicit run selection;
- `tab` — tab selector;
- `period` — period selector;
- `lang` – locale override (`en` or `ru`), fallback on `en`.

Data source: `BeeAgentUiAdapter.get_page("rop_dashboard", query)`.

Source layout: `build_rop_page_layout(...)`.

Page sections:

- `overview`: `Run Overview` (`state_grid`, `width: 8`) and `Key Metrics` (`kpi_grid`, `width: 4`, `columns: 2`), warnings follow the top row; Overview uses period dropdown;
- `queue`: attention events;
- `sources`: source health details;
- `blacklist`: protected sender blacklist management;

BeeAgent does not hold manual HTML builders/templates for `/rop`.

## Read-only and security rules

Web Console must comply with:

- no GET mutation;
- no non-auth operator POST/write actions except explicit UI-8.8 protected blacklist mutations;
- BeeUI auth POST endpoints is only allowed for authentication/session flow;
- no mailbox/CRM/module/capability execution from GET routes;
- no web-triggered module/capability/mailbox/CRM execution;
- no web-triggered `rop run`;
- no widget-triggered execution;
- no raw `.eml` rendering;
- no `message/rfc822` attachment rendering;
- no attachment content rendering;
- path traversal blocked for `run_id`/path-sensitive routes;
- artifact access only by allowlisted IDs;
- missing/malformed artifacts handled gracefully and degrade into warnings/errors, not crashes;
- cache-control requirements must be met on route layer, but their actual enforcement must be confirmed separately.

### UI-6 evidence sections (latest-N, threads, AI assist)

Backward-compatible API/read-model evidence on the basis of It30 artifacts is retained in the current contract:

- `latest_selection` — selection evidence;
- `thread_summary` and `threads[]` - thread evidence;
- `ai_assist_summary` and `ai_assist_events[]` - AI assist evidence.

Individual Latest-N / Threads / AI Assist tabs or blocks are not in the current `/rop`. Event Detail may use the corresponding bounded evidence where the current contract so provides.

### UI-6 – It30 artifacts in allowlist

Added to `ARTIFACT_ALLOWLIST`:

| ID                             | Relative path                  |
| ------------------------------ | ------------------------------ |
| `mailbox_selection_json`       | `mailbox_selection.json`       |
| `mail_thread_index_json`       | `mail_thread_index.json`       |
| `mail_thread_context_json`     | `mail_thread_context.json`     |
| `rop_ai_assist_requests_json`  | `rop_ai_assist_requests.json`  |
| `rop_ai_assist_decisions_json` | `rop_ai_assist_decisions.json` |
| `rop_ai_assist_results_json`   | `rop_ai_assist_results.json`   |

### UI-6 – New `/api/rop/dashboard` fields

```json
{
  "latest_selection": {
    "selected_count": 20,
    "strategy": "latest_n",
    "source_count": 1,
    "sources": [],
    "newest_message_at": "...",
    "oldest_message_at": "...",
    "warnings": [],
    "evidence_artifact_id": "mailbox_selection_json"
  },
  "thread_summary": {
    "thread_count": 7,
    "events_with_thread_context": 5,
    "reply_or_forward_count": 3,
    "linked_by_references_count": 2,
    "linked_by_subject_fallback_count": 0,
    "source_client_scoped_fallback_count": 0,
    "warnings": [],
    "evidence_artifact_ids": []
  },
  "threads": [],
  "ai_assist_summary": {
    "evidence_available": true,
    "eligible_count": 10,
    "request_count": 3,
    "ok_count": 2,
    "used_count": 2,
    "degraded_count": 1,
    "low_confidence_count": 1,
    "status_counts": {}
  },
  "ai_assist_events": []
}
```

Existing UI-5 fields retained.

### HTML route `/rop` — current tabs

Current tabs:

- `overview` — dashboard;
- `queue` — event queue;
- `sources` is the state of the sources;
- `blacklist` is a black list of senders.

Supported by `?lang=ru` for Russian tags in all new sections.

Sanitization rules:

- JSON responses strip `raw_eml`, `raw_message`, `attachment_content`, `content`, `content_bytes`, `payload_bytes`;
- raw `.eml` / `message/rfc822` content is never rendered; blocked nested-email attachments may remain in rendered payloads only as bounded lifecycle metadata with `storage_status=blocked` and `reason_code=blocked_email_attachment`, without blob or download link;
- dashboard shows only bounded metadata, lifecycle status and preview fields.

## Out of scope

Current contract intentionally does not include:

- per-role RBAC enforcement;
- UI settings/config editing;
- user registration/password reset;
- OAuth/OIDC;
- DB-backed user management;
- general UI-triggered runtime/CRM/mailbox operator write actions, except explicit bounded protected UI-8.8 Blacklist Add/Update/Delete;
- UI-triggered CRM/Bitrix write-back; controlled server-side `rop run` and `rop poll` write-back remains outside Web/widget routes;
- web-triggered ROP run;
- widget-triggered execution;
- save-human-decision UI flow;
- production deployment hardening;
- UI-triggered attachment parsing/OCR;
- full attachment-aware dashboard with per-file detail viewer;
- React/Reflex frontend;
- SQLAdmin;
- changes to `beeagent-rop`;
- stable API v1 freeze;
- standalone BeeUI service.

## ROP Queue filter/sort/pagination contract

### Layout

Queue tab renders as one `data_table` with a functional `toolbar`. No standalone `filter_form` is emitted.

### Query parameters

All Queue tab parameters are transmitted via query string to `/rop?tab=queue`.

#### Filter params

| Param            | Type    | Description                                             | Validation                                                                                 |
| ---------------- | ------- | ------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `q`              | string  | Full-text search across sender and subject              | Any string value                                                                           |
| `sender`         | string  | Filter by sender (legacy, use `q` for combined search)  | Any string value                                                                           |
| `subject`        | string  | Filter by subject (legacy, use `q` for combined search) | Any string value                                                                           |
| `case_type`      | string  | Comma-separated classification values                   | Shall be one of: `new_lead`, `existing_client`, `existing_deal`, …                         |
| `classification` | string  | Legacy alias for `case_type` (mapped to `case_type`)    | Same as `case_type`                                                                        |
| `priority`       | string  | Comma-separated priority values                         | `low`, `medium`, `high`, `critical`                                                        |
| `bitrix_status`  | string  | Comma-separated Bitrix reconciliation status values     | `not_found`, `weak_match`, `ambiguous`, `duplicate_candidate`, …                           |
| `is_fallback`    | boolean | Filter by fallback classification (`true`/`false`)      | `true` or `false`                                                                          |
| `queue`          | string  | Filter by operator queue bucket name                    | `high_priority`, `needs_review`, `lost_in_bitrix`, `ambiguous`, `degraded`, `unreconciled` |
| `date_from`      | date    | Start of date range (inclusive, YYYY-MM-DD)             | must be the correct date; not later than `date_to`                                         |
| `date_to`        | date    | End of date range (inclusive, YYYY-MM-DD)               | must be the correct date; not before `date_from`                                           |

#### Column params

| Param     | Type            | Description                                                                                     |
| --------- | --------------- | ----------------------------------------------------------------------------------------------- |
| `columns` | comma-separated | Visible column keys: `priority`, `client`, `subject`, `date`, `classification`, `bitrix_status` |

Column visibility is managed through the toolbar ellipsis action (column chooser). `columns_open` and `open_dropdowns` are no longer part of the Queue presentation-state contract.

#### Pagination params

| Param       | Type    | Default       | Description           | Validation                                                                                         |
| ----------- | ------- | ------------- | --------------------- | -------------------------------------------------------------------------------------------------- |
| `page`      | integer | `1`           | Page number (1-based) | `>= 1`                                                                                             |
| `page_size` | integer | `25`          | Items per page        | `25`, `50`, or `100`                                                                               |
| `sort`      | string  | `received_at` | Sort field            | `received_at`, `date`, `event_date`, `sender`, `subject`, `case_type`, `priority`, `bitrix_status` |
| `order`     | string  | `desc`        | Sort direction        | `asc` or `desc`                                                                                    |

`sort` and `order` form an atomic pair: the URL contains both parameters, or neither for the default `received_at` / `desc`.

#### Canonical params preserved in all ROP links

- `run_id` — explicit run identifier
- `tab` — active tab name (overview, queue, sources, blacklist)
- `period` — period value (today, yesterday, 7d, 30d, 90d, 365d, all)
- `lang` — locale override (en, ru)

### Toolbar contract (BeeUI Iteration 13.11)

Queue toolbar contains:

- `fields`: date_range (no visible label, accessible via `from_label`/`to_label`), `q` text input (no visible label, accessible via `placeholder`), checkboxes dropdowns for Classification (`case_type`), Priority (`priority`), Bitrix Status (`bitrix_status`)
- `hidden`: preserves `tab`, `run_id`, `period`, `lang`, `page`, `page_size`, `sort`, `order`, as well as active `case_type`, `priority`, `bitrix_status`, `columns` — so that GET submission does not drop dropdown filters and column visibility searches or dates
- `column_toggles`: column visibility toggles rendered under the ellipsis action
- `reset`: resets all filter params preserving `tab`, `run_id`, `period`, `lang`
- No `apply` — datepicker auto-submits on select/clear; text/date input submits on GET

`columns_open` and `open_dropdowns` are not part of canonical toolbar contract. They are supported only in legacy accepted inputs adapter contract for backward compatibility with existing links and bookmark.

Queue sets the stable `data_table.id` value `rop-queue` and supplies the released BeeUI 0.26.4 pagination/page-size payload. This opts the table into BeeUI's generic progressive same-origin GET replacement while keeping BeeAgent's server-side query semantics authoritative. BeeAgent supplies safe navigation hrefs and the product-owned page-size choices `25`, `50`, and `100`; BeeUI owns the live interaction and compact pagination presentation.

Other BeeAgent adapter-backed tables use the canonical `data_table` presentation but do not receive Queue toolbar controls.

### Adapter-level validation contract

All filter/pagination/sort parameters are validated in one adapter-level contract in `BeeAgentUiAdapter.get_page()`. Process:

1. `_extract_and_validate_params(query)` is a single function that extracts and validates filter + pagination + sort parameters
2. Validation checks: queue, columns, dropdown state, booleans, dates, enums, page/page_size, sort/order
3. Invalid values return an `invalid_params` error instead of silently expanding the selection
4. `validate_filter_params()` checks filter-specific values
5. `validate_pagination_params()` — Checks page/page_size/sort/order
6. `paginate_items()` returns a canonical page used in all rows, labels, links and API metadata

### Date sorting semantics

- valid ISO dates (`2026-06-15T00:00:00Z`) are grouped before invalid/missing dates
- missing/malformed dates (`""`, `null`, `"invalid"`) always follow valid dates in both asc and desc order
- Asc: valid dates in ascending order, then missing dates
- Desc: valid dates in descending order, then missing dates

### Attention cap

- `ATTENTION_EVENTS_MAX = 500` is the maximum number of events in attention events
- Queue tab shows all events from `queues[]` buckets, capped per period filtering
