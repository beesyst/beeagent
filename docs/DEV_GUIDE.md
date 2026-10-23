# DEV_GUIDE — Module development, tests and BeeAgent integration

## BeeDrill AI assist

`./start.sh beedrill check` runs the existing BeeDrill security regression suite. `./start.sh beedrill diff --baseline <absolute-path> --candidate <absolute-path>` runs the fixed LiteSVM/Mocha/TSX test path in separate Bubblewrap sandboxes and writes `external_test_regression_diff.json`. Both project trees must contain the same `tests/litesvm.test.ts` and preinstalled regular-file Mocha/TSX/LiteSVM dependencies; project scripts, package installers, network access, host HOME and host secrets are unavailable. Each test process tree is placed in a verified systemd cgroup-v2 scope with a 768 MiB memory maximum and no swap; inability to establish that scope is infrastructure failure. Staging uses a private sandbox workspace and enforces the byte budget while copying rather than trusting the preflight tree size. A completed baseline PASS and candidate FAIL is `test_regression` with exit 1; unchanged or other completed outcomes exit 0; unsupported, incomplete or failed infrastructure exits 3. This is a test-regression classification, never a security PASS/FAIL verdict. `beedrill.ai_assist.enabled` defaults to `false`; when enabled, BeeAgent finalizes `beedrill_security_regression.json` first, then may write the optional bounded `beedrill_ai_assist.json`. AI receives only BeeDrill `explanation_facts`; it cannot alter verdicts, exit status, or execution authority.

ROP AI adjudication and legacy assist use the shared Core profile resolver described below, supporting `openai_responses` and `openai_compatible`. Bitrix blacklist trigger uses enabled `bitrix.blacklist_trigger`, configured stage/custom-field identifiers, an internally bootstrapped dedicated trigger secret, and an operator-supplied external event application token when that callback authentication mode is used.

## Shared AI profile selection (Iteration 45)

`config/settings.yml` is the only profile catalog. `core/ai_profiles.py` resolves module `ai_profile` → `ai.default_profile` → exactly one legacy `ai.profiles.*.enabled: true` when the default is absent. Resolution returns profile identity and transport fields, never a credential value, and performs no network requests or provider fallback. ROP adjudicator and legacy assist share `rop.ai_assist.ai_profile`; BeeDrill and BeeScan select independently.

The tracked configuration uses `ai.default_profile: openrouter`. To migrate a legacy configuration, set that default to the formerly enabled profile and remove every profile's `enabled` field, including `false` fields. Any `enabled` field together with `default_profile` is rejected. Module overrides can also select a named profile while the global configuration remains in legacy mode. Omitting an override inherits global selection; null, empty, non-string, malformed and unknown names fail validation.

This partial example reuses the existing catalog and leaves enablement, approvals and budgets to their existing settings:

```yaml
ai:
  default_profile: openrouter
rop:
  ai_assist:
    ai_profile: openrouter
beedrill:
  ai_assist:
    ai_profile: openai
beescan:
  investigation:
    ai_profile: deepseek
```

Names use `[a-z][a-z0-9_]{0,63}`. Supported providers are `openai_responses` and `openai_compatible`; selected profiles require a bounded ASCII model identifier, an environment-variable reference and an HTTP(S) URL without credentials, query, fragment or control characters. Inactive empty model/URL placeholders remain accepted but cannot be selected. Unselected profiles never require their key values. Local HTTP endpoints remain supported for ROP/BeeDrill; BeeScan additionally requires HTTPS and uppercase credential references, including when inheriting a default.

ROP checks the selected credential at startup for active adjudication and for non-dry-run legacy assist. Legacy assist dry-run requires no key and sends no request; adjudication retains its existing independent enablement and credential checks. Disabled ROP requires no AI credentials. BeeDrill validates selection when enabled and degrades on unavailable credentials/provider output without changing deterministic truth or exit status. Enabled BeeScan investigation requires its selected key and independent approval; disabled investigation validates endpoint configuration without requiring a key. Profile selection never enables a consumer or grants target authority.

Historical `rop.ai_assist.profile` plus `profiles` with environment-backed model/base URL remain supported only by the legacy assist adapter. They cannot coexist with `rop.ai_assist.ai_profile` or `ai.default_profile`. Migrate their resolved transport values into `ai.profiles`, then replace the historical selector with `ai_profile`; no second canonical catalog is introduced. The historical assist transport and response handling remain unchanged.

Existing request formats, deterministic fallbacks and ROP/BeeDrill artifact fields are preserved. BeeScan investigation results add nullable `ai_provider` and `ai_model` provenance under schema 1; these are host-selected values and never credentials or model-supplied authority. Model availability is not established by config validation or mocked tests.

## Purpose

This document describes:

- How to develop `beeagent-rop`;
- how to manage the environment and dependencies with `uv`;
- How to run tests.
- How to keep the boundary between the module and BeeAgent core;
- How to connect the module to `beeagent`;
- How to develop in the current SDLC-light process.

## Related project docs

This document must be used together with:

- `docs/ROADMAP.md` are the stages, iteration, scope, artifacts, checks, DoD;
- `docs/SDLC.md` — lightweight process, change levels, required checks, PR flow;
- `docs/SECURITY.md` is secure development rules and security checks by type of change.

Rule:

> `DEV_GUIDE` does not replace `ROADMAP`, `SDLC` and `SECURITY`, but helps to develop the module quickly and safely.

## Requirements

- Python 3.14+
- `uv`

## One-shot mailbox polling

Production mailbox polling is a one-shot command: `./start.sh rop poll`. Its mutable UID checkpoint is `storage/interfaces/rop_mailbox_checkpoint.json`; it is runtime storage, not configuration or Git state. Use `./start.sh rop poll --rebaseline` only for explicit operator recovery. Scheduling belongs to an external systemd timer, not to a BeeAgent loop.

Polling mode is controlled by `rop.mailbox_poll` in `config/settings.yml`:

- `sources_all: true` — default production mode that polls every enabled read-only `mailbox_readonly` source independently;
- `source_id` — the explicit single-source override.

## ROP source registry

`config/rop/sources.yml` is the canonical source registry (`version: 1`, `sources:`). `config/settings.yml` contains only `rop.sources_path` and the `rop.mailbox_poll` selection policy:

```yaml
rop:
  mailbox_poll:
    enabled: true
    source_id: hotline_mailbox
    sources_all: true
  sources_path: config/rop/sources.yml
```

The registry may be edited manually or through the protected Sources table; a normal Sources page read and the next ROP run or poll load the latest file. There is no filesystem watcher. Mailbox host, port, SSL and folder are non-secret registry fields. Credentials remain environment references only:

```yaml
mailbox:
  host: web01.srv.welding.kz
  port: 993
  use_ssl: true
  folder: INBOX
  username_env: ROP_MAILBOX_USERNAME
  password_env: ROP_MAILBOX_PASSWORD
```

The protected Sources UI gives an authorized ROP manager a narrow credential-management exception. It resolves only each mailbox source's username reference for display, shows password solely as `********` when a nonempty value exists or `—` otherwise, and writes only the selected source's generated username/password references to the `# ROP mailbox` section of `.env`. Add requires both values. Edit starts with an empty password: blank preserves it and nonblank replaces it. Values never enter YAML, CSV, JSON APIs, audit records, logs or artifacts. New mailbox sources use `BEEAGENT_ROP_SOURCE_<SOURCE_ID>_USERNAME` and `BEEAGENT_ROP_SOURCE_<SOURCE_ID>_PASSWORD`. Current-process updates set only changed names; at startup `load_dotenv(..., override=False)` preserves externally supplied environment values over `.env`.

Optional CLI overrides:

- `./start.sh rop poll --source-id <id>` — poll only that source (also for per-source rebaseline);
- `./start.sh rop poll --all-sources` — poll all enabled read-only mailbox sources;
- `./start.sh rop poll --rebaseline [--source-id <id>]` — reset baseline for the selected source(s).

Per-source semantics:

- each enabled source has its own `UIDVALIDITY` / `last_processed_uid` checkpoint entry;
- a source checkpoint advances only after its full ROP pipeline and postprocessing succeed;
- one source failure never blocks the other selected sources and never rolls back successful checkpoints;
- a new source without a checkpoint receives its own baseline without resetting existing sources;
- an explicit per-source rebaseline does not reset unrelated sources.

## Manual ROP runs

`./start.sh rop run` is the manual latest-N/backfill path: it does not use mailbox checkpoints and can process messages already present in a mailbox. With no selector it runs every enabled source when more than one is enabled; with one enabled source it keeps the single-source path. `items_max` is a per-source, per-invocation limit and is applied in memory only.

- `./start.sh rop run`
- `./start.sh rop run --source-id hotline_mailbox`
- `./start.sh rop run --all-sources`
- `./start.sh rop run --items-max 5`

`./start.sh rop poll` is the only-new UID path. It has a persistent per-source checkpoint; the first poll establishes a baseline without importing historical messages, and later polls process only higher UIDs. Use `./start.sh rop poll --source-id <id>` for one source. Existing controlled Bitrix write-back settings still govern both commands.

When Bitrix reconciliation is enabled, the poll persists durable ROP write-back intent (`storage/interfaces/rop_writeback_state.json` via `build_writeback_plan`) before the source checkpoint advances. With `bitrix.writeback.enabled: true` plan persistence failure blocks checkpoint advancement; otherwise it is logged without blocking ingestion. The required ordering is durable intent → checkpoint → external execution → original per-run projection refresh. Automatic external execution is scoped strictly to the just-created poll run; a poll with no new messages does not execute legacy or historical write-back records. `rop writeback plan/execute` remains the explicit operator recovery path.

## BeeDrill bounded regression runs

The uncommitted #292 recovery snapshot prepares pinned Surfpool 1.5.0, Agave 4.2.2 and platform-tools 1.54 automatically on Linux x86_64 with glibc 2.34+. `core/beedrill_toolchain.py` owns artifact URLs, sizes and SHA-256 checksums. Preparation verifies official HTTPS downloads, bounds archive extraction, uses a locked atomic user-local cache and reuses verified installations. Reference SBF builds additionally require an existing C linker and glibc development files; first builds need Cargo registry HTTPS access. No sudo, native installer scripts or system package changes are used.

Only enabled valid BeeDrill execution prepares Solana tooling; Web, Telegram and ROP do not. The individual SPL Token scenario needs only Surfpool. Child processes receive a managed HOME and PATH without host secrets; SBF builds cannot install tools or alter rustup. Build/deploy timeout kills the process group and reaps its parent. Unsupported platforms, missing prerequisites and corrupt caches remain INCOMPLETE / exit 3 with bounded diagnostic reasons. Move only the affected BeeDrill cache entry aside for inspection and retry. The existing shared entrypoint bootstrap installs `uv` when it is missing; the restriction on remote installer scripts applies to native Solana/SBF tools.

These changes are not available from an unchanged main clone until delivered. For coordinated recovery verification use `PYTHONPATH=<workspace>/beedrill/src ./start.sh beedrill check`; a standalone recovery host can use the existing pinned BeeDrill release. External protocol onboarding remains outside the recovered three-scenario corpus.

The host exposes three approved BeeDrill scenarios:

- `./start.sh beedrill run --scenario reference_target_containment_replay`
- `./start.sh beedrill run --scenario reference_oracle_manipulation_replay`
- `./start.sh beedrill run --scenario spl_token_freeze_containment_replay`

The SPL scenario executes the fixed canonical SPL Token experiment inside the approved offline Surfpool boundary. BeeAgent owns runtime, program selection, RPC, transactions, ephemeral keys, timeouts, and cleanup; it only reports the BeeDrill-produced `security_verdict`. The command invokes the registered `beedrill` module through the normal module runtime, then copies its `security_verdict` into a JSON summary. It does not interpret or calculate that verdict. Exit status is `0` for `pass`, `1` for a completed `fail`, `2` for invalid command input, and `3` for incomplete, refused, timeout, or error results. The canonical module result and scenario artifact remain under the generated run's existing artifact directory.

Use `./start.sh beedrill check` to execute all three scenarios in the fixed approved order. The tracked configuration enables BeeDrill. The normal `./start.sh` bootstrap resolves its pinned release-backed optional extra; normal user and judge use does not require sibling BeeSDK or BeeDrill repositories. Maintainers may use sibling sources only for coordinated local development.

The aggregate command creates separate run and session IDs for each scenario and writes a bounded host suite summary under `storage/runs/`; it stores references only, never raw evaluator evidence. Its suite exit status is `0` for a complete PASS, `1` for a completed security FAIL without incompleteness, `2` for an invalid check invocation, and `3` for incomplete/runtime failure, including missing or unknown verdicts. CI should use the process exit status directly:

```yaml
- name: BeeDrill security regression
  run: ./start.sh beedrill check
```

## Controlled Bitrix write-back (Iteration 37)

The tracked production profile enables write-back (`bitrix.writeback.enabled: true`). Enabled write-back requires a dedicated env credential and configured customer Lead `stageId` values for `new_lead`, `new_lead_assigned` and `irrelevant` (all required fail-fast when enabled). Setting `bitrix.writeback.enabled: false` or using dry-run preserves the explicit zero-write control.

When enabled, `rop poll` and `rop run` execute only the pending records owned by their just-persisted run. Historical/global pending work is never started automatically and is available only through the explicit CLI command. When write-back is enabled, `rop run` fails explicitly if reconciliation or plan persistence cannot create canonical intent; post-persistence executor failures remain visible and recoverable from that intent:

- `./start.sh rop writeback plan --run-id <id>` — build the authoritative execution plan from final classification, read-only reconciliation and recipient routing; persists the canonical `storage/interfaces/rop_writeback_state.json` and the per-run `rop_writeback_summary.json` projection. Zero writes.
- `./start.sh rop writeback execute [--run-id <id>] [--dry-run] [--retry-failed] [--existing-only]` — explicit global pending executor per server-side `bitrix.writeback` policy (bounded retry, idempotent create via `crm.item.add`, `entityTypeId=1`, fail-closed stage/responsible/target validation). `--dry-run` performs zero writes. `--retry-failed` re-arms retry-exhausted create or attachment work with a fresh retry budget (terminal permission/config/invalid-field attachment failures are never retried). `--existing-only` performs the production incident recovery flow: it finds only exact BeeAgent-owned leads by canonical origin identity, never creates a missing lead, and resumes missing email/activity-file delivery idempotently.

Per-event outcomes are `create_lead`, `attach_existing` or `deferred`.

`BitrixReadonlyClient` remains strictly read-only; `crm.activity.list` is used only for activity idempotency reconciliation. `BitrixWriteClient` permits only the required mutation methods `crm.item.add` and `crm.activity.add`; it does not permit `crm.item.update`, `crm.item.delete`, `crm.lead.add` or arbitrary method execution.

For a safe existing Deal, reconciliation first requires exact sender email/phone evidence for Contact or Company, then performs bounded read-only `crm.item.list` with `entityTypeId=2` and the official `contactId`/`companyId` relation field. Identity evidence (sender email/phone, Contact/Company and related historical CRM relation) is never an executable target: an exact matched Lead/Deal, an exact Contact/Company and a related Deal all stay identity/candidate evidence with `safe_to_use_as_target=false`; title/subject similarity remains review-only. Automatic existing-target attachment is allowed only for exact trusted thread evidence: normalized `Message-ID`, `In-Reply-To` and bounded `References` resolve against canonical `storage/interfaces/rop_writeback_state.json`, all resolved ancestors must agree on one trusted Lead/Deal, a confirmed BeeAgent-created Lead (`target_provenance=beeagent_created`) is an authoritative thread root, a thread-resolved attachment (`target_provenance=thread_resolved`) propagates the target, and legacy records without trusted provenance are never authority (fail closed). Conflicting exact references fail closed to `ambiguous_thread_target` deferred with zero mutation. A confirmed BeeAgent-created/recovered Lead root in canonical state may be reused across runs only for the exact normalized `client_id` + sender + subject key; multiple distinct historical roots fail closed. Same-run `create_lead` siblings still use pending root resolution, then attach with `target_provenance=sender_subject_resolved`; this is operational attachment, not arbitrary historical CRM target authority or semantic duplicate proof (`sender_subject_match` is thread evidence only), and never reassigns an existing CRM entity. Contact/Company is never an activity owner or execution target. A completed exact Lead and related-Deal search with no target is persisted as `identity_only_no_target` with `suitable_target_search=completed_no_target`; only `new_lead` and `irrelevant` may then use the normal configured create path. An independent `new_lead` from a known sender (without exact thread evidence) can create a new Lead; `existing_deal`/`duplicate` without a safe exact target remain deferred/manual-review. A reply in the same batch whose thread root is only planned is deferred as recoverable `pending_thread_root` until the root is confirmed.

A Lead create is allowed only after `rop_recipient_routing.json` reports an exact active responsible match with a positive `user_id`; ambiguous, inactive, `connector_degraded`, `not_attempted`, malformed and conflicting routing evidence fails closed to `deferred` (`responsible_unresolved`). The configured `bitrix.writeback.user_id_fallback` (positive Bitrix user ID, validated fail-fast) normally applies only to `not_found`; a genuinely absent legacy/manual routing artifact may use it for missing routing evidence, but a present malformed or incomplete artifact never authorizes mutation. The fallback never overrides an exact match. For a `new_lead`, an exact matched responsible creates the Lead in the configured `bitrix.writeback.stages.new_lead_assigned` stage with the exact matched `ASSIGNED_BY_ID`, while a valid fallback creates the Lead in the configured `bitrix.writeback.stages.new_lead` stage with the fallback user; `irrelevant` keeps its existing configured stage. The real customer STATUS_ID for `new_lead_assigned` and the active `ROBOT WG` fallback user identity must be verified read-only against Bitrix before production enablement.

Email activity binding (`crm.activity.add`) is controlled by `bitrix.writeback.email_attach`. `bitrix.writeback.email_completed` (boolean, validated fail-fast, default `true`) sets whether the created email activity is completed (`true` → `COMPLETED=Y`); `false` creates it as not completed, which makes new incoming emails more visible in the lead timeline. For each record, durable state is saved after a created/recovered lead, after a created/recovered email activity, and after file delivery, so a retry reuses exact origin identities and continues delivery without re-ingesting mailbox UIDs.

## Installation (dev)

At the root of the module:

```bash
uv sync
```

Use `uv run` to run commands; activating the venv is unnecessary.

## Dependency management (`uv`)

Dependency sources of truth:

- `pyproject.toml`
- `uv.lock`

Rule of the project:

> After changing dependencies, commit both `pyproject.toml` and `uv.lock`.

### Optional module profiles

Core dependencies always include BeeSDK but exclude domain modules. `modules.registry[].enabled` determines runtime availability, while optional `install_extra` links an enabled module to a locked installation profile. The current profiles are `rop`, `beedrill` and `beescan`; omitting `install_extra` preserves support for externally installed modules.

`uv run pytest -q` uses the complete dev/test profile, including locked ROP and Docling CPU dependencies, regardless of which runtime modules are enabled; in a coordinated workspace, ROP for this profile may resolve through the configured local editable `beeagent-rop` source. `./start.sh` runs `uv sync --frozen --no-dev`, reads settings and then synchronizes extras only for enabled module entries and the selected Docling CPU/CUDA profile with `--no-dev`. Disabled entries add no runtime dependencies. BeeSDK and enabled BeeDrill resolve from pinned release-backed sources. Normal BeeDrill runtime with ROP disabled excludes `beeagent-rop` and requires no ROP runtime setup.

### Basic Commands

| What to Do               | Command              |
| ------------------------ | -------------------- |
| Install dependencies     | `uv sync`            |
| Run tests                | `uv run pytest -q`   |
| Add Dependency           | `uv add <pkg>`       |
| Add dev dependency       | `uv add --dev <pkg>` |
| Remove Dependency        | `uv remove <pkg>`    |
| View the dependency tree | `uv tree`            |

## What is `beeagent-rop`

`beeagent-rop` is **not a separate runtime** or a separate UI.

This is domain module for BeeAgent, which is responsible for:

- inbound event understanding;
- lead classification;
- duplicate resolution;
- attachment-aware triage;
- ROP summary;
- bounded recommendations;
- bounded AI assist contract for ambiguous/fallback classification (It17+).

Rule:

> The module must not take over orchestration, session management, the shared artifact lifecycle or capability transport. These belong to BeeAgent core.

## The module boundary

### What belongs to `beeagent-rop`

- `contracts.py`
- `domain/*`
- `services/*`
- `cases/*`
- client-specific fixture logic
- classification rules
- duplicate/entity resolution
- attachment-aware logic
- rop summary
- client-facing recommendation draft
- AI assist contract: eligibility, request builder, decision validation, merge (It17+)
- human-reviewed taxonomy contract (It18+)
- thread context contract (It18+)

### What belongs to `beeagent`

- module contract
- module registry
- run/session context
- artifact API
- transport/UI
- capability abstraction
- approvals / policy / authority boundaries
- shared orchestration flow

Rule:

> If a change is needed only for ROP/client logic, it belongs in `beeagent-rop`. If all modules need it, it is a candidate for the core.

## How to Test a Module

Main way:

```bash
uv run pytest -q
```

### What must be tested inside the module

- domain contracts;
- classification cases;
- duplicate cases;
- attachment-aware cases;
- summary generation;
- recommendation generation;
- AI assist eligibility, request builder, decision validation, merge;
- human review taxonomy validation;
- thread context validation and classification integration;
- fixture-based edge cases.

### What is not the module’s testing responsibility

- Telegram UI;
- shared run lifecycle BeeAgent;
- module registry;
- MCP transport;
- n8n execution engine.

This is tested in `beeagent`.

## Fixture-driven Development

A fixture driven approach is mandatory for `beeagent-rop`.

Why:

- client cases contain messy data;
- The incoming flow is unstable;
- rules must be checked against reproducible examples rather than only reasoned about mentally.

### Practice

For each relevant iteration it is useful to have fixture sets:

- A new lead;
- existing deal;
- duplicate;
- irrelevant / spam;
- ambiguous case;
- attachment-heavy case;
- “see attachment” case;
- dirty input case.

For inbound contract baseline Iteration 2 fixtures, the source lives in `tests/fixtures/inbound_email_v0/`. Such fixtures must contain only the sanitized input and the expected normalized result without classification labels.

For Iteration 3 explainable classification fixtures, the source lives in `tests/fixtures/lead_classification_v1/`. Such fixtures must contain a normalized inbound input and the expected classification result c `case_type`, `priority`, `reason_code` and `is_fallback`.

For Iteration 4 duplicate resolution fixtures, the source lives in `tests/fixtures/duplicate_resolution_v1/`. Such fixtures must contain inbound input, accessible `existing_records` and expected duplicate result c `candidate`, `confidence`, `reason_code`, `reason_path` and fallback semantics.

For Iteration 5 attachment reader decision fixtures, the source lives in `tests/fixtures/attachment_reader_v0/`. Such fixtures must contain attachment metadata input and the expected `AttachmentReadResult` c `status`, `reason_code`, `is_supported`, `is_refused`, `needs_manual_review`. Fixture examples cover: PDF supported, DOCX supported, XLSX metadata_only, JPG unsupported (no OCR), inline/logo skipped, unknown content type unsupported, oversized refused.

For Iteration 7 attachment-aware classification, the fixture source is `tests/fixtures/attachment_aware_classification_v1/`. These fixtures must contain normalizable inbound input with attachments and the expected classification result. Attachment context must arrive through:

- `attachment.filename` is the file name;
- `attachment.raw_metadata.text_preview` / `attachment_text` / `summary` — legacy preview keys;
- BeeAgent It25-like downstream keys in `event.raw_metadata` and `attachment.raw_metadata`: `attachment_extraction_status`, `attachment_preview_available`, `attachment_text_preview`, `attachment_refusal_reasons`, `extraction_status`, `preview_available`, `text_preview`, `reason_code`, `refusal_reason`. Classifier does not read files, does not generate `attachment_extraction.json` and does not perform OCR; it only works with payload secure preview/status/refusal data already transmitted. Fixture examples cover: weak body + request filename → new_lead; weak body + invoice filename → existing_deal; text_preview with an inquiry → new_lead; text_preview with an invoice → existing_deal; refused/unreadable attachment → safe fallback/manual-review.

For Iteration 8 ROP summary v1 fixtures, the source lives in `tests/fixtures/rop_summary_v1/`. Such fixtures must contain the classified inbound items list and the expected `SummaryResult` with `total_leads`, `counts` and highlighted `items`. The entry contract of the element: `event_id`, `case_type`, `priority`, `is_fallback`, `is_attachment_aware`. Fixture examples cover: empty input; mixed flow (new_lead/existing_deal/duplicate/irrelevant); high-priority new lead; fallback/low-confidence → needs_manual_review; duplicate highlighted; attachment-aware item.

For Iteration 9 recommendation builder v0 fixtures, the source lives in `tests/fixtures/recommendation_builder_v0/`. Such fixtures must contain the classified events list and the expected `RecommendationResult` list. The entry contract of the element: `event_id`, `case_type`, `priority`, `confidence`, `is_fallback`, `is_attachment_aware`, `reason_code`. Fixture examples cover: empty input; new_lead_next_step; existing_deal_follow_up; duplicate_review; irrelevant_no_action; manual_review_required; attachment_aware_review; mixed_recommendations.

For Iteration 10 BeeAgent integration contract smoke v0 fixtures, the source lives in `tests/fixtures/integration_smoke_v0/`.

For Iteration 17 AI assist v1 fixtures, the source lives in `tests/fixtures/ai_assist_v1/`. Such fixtures must contain deterministic classification result, expected AI assist eligibility, optional AI decision and expected merge outcome. Fixture examples must cover: fallback reply eligible; fallback low signal eligible; ambiguous existing deal eligible; confidential spam not eligible; confident new_lead not eligible; confident existing_deal not eligible; invalid AI decision degraded; AI low confidence degraded; spam cannot be AI-promoted; tender/RFQ remains deterministic; refused attachment with weak body; AI decision with CRM action rejected. Such fixtures must contain BeeAgent-compatible payload for `RopModule.handle(...)` and the expected shape- structure of `rop_summary` results. Smoke examples cover: `rop_summary` output shape (`period`, `total_leads`, `counts`, `items`, `recommendations`), artifact write through `context.artifact_api.write_json(...)`, unsupported `case_type`, missing/non-list `events`, artifact write failure without crash.

For Iteration 19 ROP case subtype taxonomy v1 fixtures, the source lives in `tests/fixtures/reviewed_tsv_subtype_v1/`. Such fixtures must contain inbound event input, expected classification result, including `case_subtype`, `recommended_queue`, `should_rop_see`, `correct_action` and `reviewed_expected.json`, with the expected evaluation counts. Fixture examples covering: ETS/SAP tender → `new_lead_tender`; RFQ/quotation → `new_lead_rfq`; WARUITE shipping → `existing_deal_logistics`; Pentagon freight/invoice → `existing_deal_invoice`; ESAB lot clarification → `existing_deal_procurement`; Qarmet delivery deadline → `existing_deal_logistics`; Voestalpine product order → `existing_deal_procurement`; supplier promo → `supplier_offer`; Facebook/WPK/HR → `service_notification`; Kemppi order confirmation → `existing_deal_invoice`; finance reconciliation → `finance_document`; bulk newsletter → `spam_or_bulk`; internal memo → `internal_employee_correspondence`; document request → `existing_deal_document`; malformed subtype → degraded validation path. Subtype resolver is deterministic and explainable: uses `case_type`, `reason_code`, subject/body markers to choose subtype without duplication of `rules.py`.

For Iteration 18 human-reviewed taxonomy v1 fixtures, the source lives in `tests/fixtures/human_review_taxonomy_v1/`. Such fixtures must contain human review payload and the expected validation result. Fixture examples must cover: confirmed new_lead; confirmed existing_deal; confirmed irrelevant; confirmed duplicate; manual_review/ambiguous; false_positive; false_negative; deferred review; malformed/missing label; malformed/invalid label; malformed/invalid status. Human review labels does not affect live production classification and is used only as fixture/evaluation evidence.

For Iteration 18 thread context v1 fixtures, the source lives in `tests/fixtures/thread_context_v1/`. Such fixtures must contain thread context payload, the expected validation result and expected_supportive flag for ambiguous existing-deal helper. Fixture examples must cover: reply chain with previous existing_deal; forward-only weak; supplier noise with thread context (must not be promote); tender/RFQ with thread context (deterministic new_lead); weak continuation without CRM; CRM hint with reply; malformed payloads; empty thread_id.

For Iteration 12 live mailbox fixture hardening v1 fixtures, the source lives in `tests/fixtures/live_mailbox_hardening_v1/`. Such fixtures must contain only sanitized/signal-reduced payload and expected outcomes on live mailbox scenario groups. Minimum set of groups: supplier promo, tender/procurement notifications, HR/service noise, operational documents, attachment-only manual-review cases, spam-like sales. Fixture contract must be explainable: `input` -> deterministic rules -> `expected` without AI-only path.

For Iteration 13 human-reviewed live classification hardening v1 fixtures, the source lives in `tests/fixtures/live_human_review_v1/`. Such fixtures must contain only sanitized human-reviewed payload and expected deterministic outcomes on first-pass live review. Minimum set of groups: supplier promo, HR/service noise, finance/accounting documents, logistics notifications, tender/procurement, client continuation, attachment-only manual-review, duplicate-candidate finance noise. Fixture contract must remain explainable: `input` -> deterministic rules -> `expected`, and cases with open business questions must be clearly marked through `review_status = needs_business_confirmation`.

Sanitation for live mailbox fixtures is mandatory:

- only synthetic senders in the `example.test` domain;
- without real phones and live URL;
- without raw `.eml` and full raw message bodies;
- without secrets/tokens/passwords.

Expected artifact behaviour in module-side integration smoke:

- If `context.artifact_api` is available, the module calls `write_json("<case_type>_result.json", ...)`;
- The error in writing the artifact must not drop `RopModule.handle(...)`;
- structured module result remains the main output path.

Output shape `rop_summary` (with Iteration 9) includes the `recommendations` key:

```json
{
  "period": "2026-05",
  "total_leads": 2,
  "counts": {"new_lead": 1, "existing_deal": 1},
  "items": [...],
  "recommendations": [
    {
      "title": "New lead: qualify and contact",
      "body": "High priority new lead. ROP should contact and qualify this lead promptly.",
      "status": "draft",
      "reason_code": "new_lead_next_step",
      "target_event_id": "evt-001",
      "source_case_type": "new_lead",
      "confidence": 0.92
    }
  ]
}
```

Rule:

> If logic changes, there must be fixture or a test that explains why it changed.

## AI in the module

AI is allowed only as bounded assistive layer.

### Authorized

- classification assist;
- summary drafting;
- recommendation drafting;
- enrichment above the controlled pipeline.

### Not allowed

- Replace deterministic rules where it is mandatory;
- Leave critical decision entirely on black-box AI;
- Hide for AI the absence of a normal contract/rule path.

Rule:

> First deterministic path, then bounded AI assist over it, not the other way around.

## Connecting module to BeeAgent

`beeagent-rop` lives in a separate repository and is installed in `beeagent` as editable package.

From `beeagent`:

```
uv add --editable ../beeagent-rop
```

BeeAgent may then import the `beeagent_rop` package.

### Working model

- domain logic development in `beeagent-rop`
- orchestration/integration changes — in `beeagent`
- Integration checks — start already from `beeagent`

## Logs and artifacts

The module must not write its files to arbitrary locations.

Correct model:

- unit/fixture tests lives inside `beeagent-rop`;
- production artifacts of the module is written via BeeAgent artifact API;
- linkage goes through `run_id`, `module_id`, `case_type`.

Rule:

> If the module started to invent its own runtime storage lifecycle by bypassing BeeAgent, that's an architectural error.

## SDLC-light workflow

1. Open `docs/ROADMAP.md`
2. Select current iteration
3. create issue
4. define `change level`
5. Create a branch
6. Amend
7. Run:
   - `uv run pytest -q`
   - Necessary fixture tests

8. Check that logic hasn't gone beyond scope
9. to shape PR
10. after review – merge

## Change levels

### low-risk

- docs
- naming cleanup
- local tests
- harmless refactor

### runtime-risk

- classification logic
- duplicate logic
- summary generation
- result contracts
- module integration surface
- fixture-driven behavior changes

### security-sensitive

- attachment parsing
- email/file input handling
- file/path handling
- external connectors
- secret/env handling
- serialization/deserialization
- trust-boundary changes

## What to check before PR

Minimum:

```
uv run pytest -q
```

Add:

- Check fixture coverage with iteration;
- Check that deterministic path remains explainable;
- Check that the change does not carry client-specific crutches into the common contract without cause.

### Typical checklist

- client cases are covered by tests;
- classification/reason path is explained;
- duplicate logic is reproducible;
- attachment path bounded and secure;
- AI does not blur deterministic contract;
- The change did not go beyond scope of the current iteration;
- required checks on change level is actually complete.

## Copilot / AI prompt template (beeagent-rop)

```
Changes are needed in the `beeagent-rop` project (NOT only in the current file).

### Context

- Project: `beeagent-rop` (`Python 3.14+`, `uv`)
- This is a separate domain module for BeeAgent
- Architecture: the module lives separately from `beeagent`, connects as a package-based module and is not a separate runtime or MCP server
- SDLC-light: `ROADMAP → Issue → branch → code → tests → artifacts → PR → merge`
- Source of truth:
  - domain contracts
  - business rules
  - fixture cases
  - `docs/ROADMAP.md`
  - `docs/SDLC.md`
  - `docs/SECURITY.md`
- Iteration closes through `PR`, so the modifications must be verifiable, reproducible and consistent with fixture/tests/artifacts

### Rules

- First, read all the files listed, then suggest and submit corrections.
- If another file is needed along the way, add it to the list and read it as well.
- First map the task to the current iteration in `docs/ROADMAP.md`; stay within its scope.
- First, define `change level`:
  - `low-risk`
  - `runtime-risk`
  - `security-sensitive`
- Determine the required checks for the selected `change level` from `docs/SDLC.md` and `docs/SECURITY.md`.
- Make only the smallest necessary KISS changes. Do not refactor outside the task.
- The tests must be of a minimum and proportional nature: Cover acceptance criteria and public behavior, do not create new test- files/test-helpers without explicit need.
- Do not change another iteration’s scope or introduce unfinished architecture for hypothetical future use.
- Don't remove existing checks for no apparent reason.
- Don't drag orchestration/runtime/module-registry/capability-transport logic into `beeagent-rop`, if it has to live in `beeagent`.
- If you see that the change relates to `beeagent` core, not to the domain module, just point it out in the answer.

### Source of truth rules

- Source of truth in the module:
  - domain contracts;
  - fixture cases;
  - agreed business rules;
  - Visible deterministic paths;
  - bounded AI assist only where justified.
- Do not create hidden behavior that cannot be explained through input → rules → result.
- Do not replace mandatory deterministic paths with pure AI output.
- If you add a new rule/config-like contract inside the module, first explain:
  - where it must reside;
  - Why it's a module, not `beeagent`;
  - Why doesn't it create a second source of truth for core runtime.

### Core / module boundary rules

- `beeagent-rop` is responsible for:
  - inbound event understanding;
  - lead classification;
  - new vs existing deal logic;
  - duplicate resolution;
  - attachment-aware triage;
  - rop summary;
  - bounded recommendations;
  - fixture-driven client behavior.
- `beeagent-rop` must not, for no reason, take over:
  - orchestration;
  - run/session lifecycle;
  - global artifact management;
  - module registry;
  - MCP/tool transport;
  - global approvals / authority / policy.
- If the task requires a change in the common contracts platform, it is `beeagent`, not `beeagent-rop`.

### Docs / contracts / artifacts

- If module behavior, a contract, fixture contract, result shape or documentation contract changes, check whether these need updating:
  - `docs/ROADMAP.md`
  - `README.md`
  - `docs/DEV_GUIDE.md`
  - `docs/SDLC.md`
  - `docs/SECURITY.md`
- If shape changes the result, show an example of the object of the result.
- If fixture contracts changes, give an example of fixture input/output.
- After completing the work, provide a short checklist for the PR/report.

### Code style / execution rules

- Follow PEP 8: names, length of lines, structure.
- Don't add any comments.
- Keep logs, field names, JSON/JSONL and runtime messages in English.
- All start-up commands and tests should be indicated via `uv run`, if applicable.
- Do not propose hidden side effects in external systems without an explicit task requiring them.

### AI / deterministic rules

- First deterministic path, then bounded AI assist over it.
- If AI is used:
  - clearly indicate where it is;
  - which remains deterministic;
  - What is fallback path;
  - how the result will be verifiable.
- Don't make black-box the only way for critical classification.

### Release / versioning rules

- Do not change `version` in `pyproject.toml`, release metadata, changelog, tags or release-related files unless the task explicitly concerns releases/versioning.
- Version bump is not made in the normal feature/fix/docs PR.
- If adding dependencies, update only dependency declarations and specify the required SCA checks; do not change the package version without an explicit task instruction.

### Response format

Response in strict format:

1. `Files read`
2. `Plan`
3. `Change level`
4. `Required checks`
5. `Source of truth after change`
6. `Core/module boundary`
7. `Before`
8. `After`
9. `Why`
10. `Checklist`
11. `PR description`

### Additional to format

- Without diff
- No further reasoning.
- If you need a new function/class, specify the exact location (before/after which block)
- For tests, list which tests to add/update
- For each new rule/contract, indicate:
  - where it resides;
  - Why it is there;
  - Why does this apply to the module, not to `beeagent`?
- For PR, briefly list what must be in:
  - `Summary`
  - `Tests`
  - `Artifacts`
  - `Security review`
- Explicitly state separately:
  - was `pyproject.toml.version` changed
  - If the task is not about release, the answer must be `version not changed`

### Task

<describe the task in one sentence>

### Iteration

<specify the iteration number and title from `docs/ROADMAP.md`>

### Issue context

<briefly insert Summary / Scope / Deliverable / Acceptance Criteria from the issue>

### Files

Read all of the following:

- `docs/ROADMAP.md`
- `docs/SDLC.md`
- `docs/SECURITY.md`
- `docs/DEV_GUIDE.md`
- `README.md`
- `pyproject.toml`
- `src/beeagent_rop/module.py`
- `src/beeagent_rop/contracts.py`
- `src/beeagent_rop/domain/models.py`
- `src/beeagent_rop/domain/enums.py`
- `src/beeagent_rop/domain/rules.py`

If necessary, add and read:

- `src/beeagent_rop/cases/*`
- `src/beeagent_rop/services/*`
- `src/beeagent_rop/adapters/*`
- `tests/*`

### Output expected

- `uv run pytest -q` passes
- key fixture/case scenarios covered by tests
- deterministic path remains explainable
- AI, if used, remains bounded and has fallback path
- The change does not break the boundary between module and BeeAgent core
- required checks for this `change level` is defined and listed
- Change ready for PR on current iteration
```

## What to avoid

- Do not drag client-specific logic into `beeagent` core without cause;
- do not replace mandatory rules with pure AI output;
- Do not make hidden write-back into external systems;
- Don't build the second runtime inside the module;
- Do not close iteration without fixture based tests;
- do not mix scope with several iterations in one PR;
- do not allow unsafe file parsing.

## Quick working scenario

1. Open `docs/ROADMAP.md`
2. Select current iteration
3. Open issue
4. define `change level`
5. Create a branch
6. Amend
7. Run:
   - `uv run pytest -q`

8. Check fixture coverage
9. to shape PR
10. after review – merge

## Bitrix24 Local Application registration (UI-8.5)

To open read-only ROP Web Console inside Bitrix24 as Server-Side Local Application with User Interface:

1. Settings `config/settings.yml`:

```yaml
web:
  auth:
    enabled: true
    mode: beeui_session
    session_secret_env: BEEAGENT_WEB_SESSION_SECRET
    principals:
      - id: admin_1
        username: admin1
        role: admin
        scopes: ["*"]
        token_env: BEEAGENT_WEB_ADMIN1_TOKEN
bitrix:
  embedded_app:
    enabled: true
    portal_origin: "https://<your-portal>.bitrix24.ru"
    default_role: "viewer"
    request_timeout: 10
```

2. Deploy the BeeAgent web console over HTTPS (`./start.sh web` behind a trusted HTTPS proxy that sets the ASGI request scheme to `https`). Install/launch handlers require HTTPS; this is determined by the ASGI request scheme, not a client header (`X-Forwarded-Proto` is not trusted).

3. Register Local Application in Bitrix24 manually:

| Field                        | Value                                        |
| ---------------------------- | -------------------------------------------- |
| Name                         | BeeAgent — ROP                               |
| Handler                      | `https://<beeagent-host>/bitrix/rop/launch`  |
| Initial installation handler | `https://<beeagent-host>/bitrix/rop/install` |
| Uses API only                | false                                        |

3a. Application permissions must include **`user`** (Users); without it, `user.current` is rejected at login (`insufficient_scope`). Reinstall the application after changing permissions.

4. Install the application on the portal. Bitrix sends `POST /bitrix/rop/install` with `member_id`, `AUTH_ID`, `AUTH_EXPIRES`, etc.; BeeAgent checks expiry and the active Bitrix current user through `user.current`, then atomically persists the one-time binding in `storage/interfaces/bitrix_rop_app.json` (without OAuth credentials).

5. The user opens the application from Bitrix24. Bitrix sends `AUTH_ID`, `AUTH_EXPIRES`, `REFRESH_ID`, `member_id`, `PLACEMENT`, `status` (Bitrix does not send `DOMAIN`; binding uses `member_id` and the domain comes from config). The request reaches `POST /bitrix/rop/launch` or `POST /bitrix/rop/install` (install then also performs the launch flow and redirects); GET on `/bitrix/rop/launch` is rejected (`405`) and never processes OAuth values. BeeAgent checks the current user through Bitrix REST, creates a bounded BeeUI viewer session, then returns `303` to `/rop` inside the iframe.

Limitations:

- access is controlled by Bitrix24; BeeAgent does not keep Bitrix user ID;
- OAuth credentials are neither stored nor logged;
- existing local BeeAgent login retained.

## Summary

`beeagent-rop` develops as a separate explainable domain module.

Key discipline:

- domain logic lives in the module;
- orchestration lives in BeeAgent;
- fixture driven is mandatory;
- deterministic path is more important than black-box magic;
- The modifications must be explained, tested and bounded.

## BeeScan BS-1 lab profile

BeeScan 0.5.0 uses the optional `beescan` extra and `https://github.com/beesyst/beescan.git` source in `pyproject.toml` without an explicit `rev`; frozen synchronization uses the existing lock. Main was checked at `10c1ea2a43e98b91c71f17709f8d8fd33cc29c18` with It5 contracts. BS-3 reporting still requires a reviewed merged It6 revision before the production dependency can be updated. Its disabled-by-default registry entry has `install_extra: "beescan"`; enabling it selects the extra through standard runtime synchronization. Bootstrap remains READ_ONLY, while HTTP probing still requires separate explicit host approval and a separately provisioned pinned provider. Run coordinated regressions with `uv run --frozen --extra beescan --extra beedrill pytest -q -rs`; the hosted CI core profile exports `--no-dev --extra beescan` and needs no local sibling ROP checkout. Operational prerequisites, CLI commands, artifacts, SCA disposition and the separate mandatory kernel/network lab are documented in [beescan_guide.md](product/beescan_guide.md). The positive lab path and negative egress checks are separate from ROP/BeeDrill execution.

BS-2 adds the separately approved `./start.sh beescan detect` command, fixed network-isolated passive Nuclei processing, host-mediated one-request capture and candidate artifacts. BS-3 adds `./start.sh beescan assess` with independent approvals, trusted fresh-source binding and Markdown/JSON reports; its production dependency gate is the reviewed merged It6 reporting revision; see the [host operating guide](product/beescan_guide.md#bs-2-restricted-detection).
