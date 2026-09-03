# WEB UI — BeeAgent Web Console contract

ROP sender blacklist uses a bounded management table with Name, Title, Email and Role, e-mail-only search, canonical pagination, CSV download, and protected direct Add, inline Save and Delete actions. The product continues to enforce authorization, CSRF, validation and audit; CSV import is not supported.

## Назначение

Этот документ фиксирует актуальный реализованный контракт для BeeUI-backed Operator Web Console в BeeAgent.

Он описывает:

- HTML routes;
- JSON API routes;
- source of truth для web runtime и read-model данных;
- read-only/security rules;
- whitelisted artifacts, которые разрешено отдавать через UI.

Документ не заменяет:

- `docs/ROADMAP.md` — iteration/status;
- `docs/product/ui_roadmap.md` — UI track planning;
- `docs/SDLC.md` — required checks;
- `docs/SECURITY.md` — secure development rules.

## Источники правды

Источник правды для bind/runtime web режима:

- `config/settings.yml`
  - `web.host`
  - `web.port`
  - `web.open_browser`
  - `web.auth`

Источник правды для auth-конфига:

- `config/settings.yml`
  - `web.auth`
- `.env` / runtime env
  - actual auth secrets

Источник правды для UI read-model данных:

- existing artifacts в `storage/`
  - `storage/runs/<run_id>/...`
  - `storage/interfaces/modules.json`
- `config/settings.yml`
  - `bitrix.widget`
  - `rop.routing`
- `storage/runs/<run_id>/rop_recommendations.json`
  - source for recommendations tab and Bitrix widget payload
- `storage/runs/<run_id>/rop_final_decisions.json`
  - artifact-first source for final decisions read-model and Bitrix widget `final_decisions` block
  - missing, malformed or unsafe artifact uses a computed read-only fallback from `classified_events.json` and `rop_ai_adjudicator_results.json`
  - GET/read-model fallback never writes storage
- `storage/runs/<run_id>/rop_ai_adjudicator_results.json`
  - source for AI adjudicator evidence in AI tab and event detail
- `storage/interfaces/rop_routing_map.json`
  - source for routing map evidence / routing contract
- `storage/interfaces/rop_web_projection.json`
  - derived, rebuildable ROP Web projection index;
  - stores projection schema metadata, latest run id, the bounded recent run-id catalog (`run_ids`, fixed window) and the scalar `total_runs` materialized during rebuild;
  - `available_runs` — bounded recent window из index `run_ids` (фиксированный bound, не весь historical catalog);
  - `kpis.total_runs` / `total_runs` — scalar materialized value из index, не вычисляется через filesystem scan при GET;
  - ordinary protected `/rop` и `/api/rop/dashboard` читают только index + selected-run entry, без перечисления `storage/runs`;
- `storage/interfaces/rop_web_projection/<sha256(run_id)>.json`
  - derived per-run materialized period dashboard entries;
  - a normal `/rop` or `/api/rop/dashboard` request reads only the index and the selected run projection entry;
  - explicit `?run_id=<id>` validates the requested id and reads only the matching hashed per-run entry (schema + exact run_id match);
- both projection layers are refreshed or regenerated only through supported ROP runtime/CLI paths, never by HTTP GET;
- normal ROP lifecycle refresh updates only the changed run entry and the existing bounded index; it does not bootstrap an absent projection or reconstruct the complete historical Web catalog;
- explicit bootstrap/regeneration for an upgraded storage tree without a projection is `./start.sh rop dashboard --period 7d`; it enumerates canonical historical ROP data once per bounded materialized run, derives configured periods from that materialization, writes required entries atomically and publishes the index last;
- an interrupted bootstrap leaves an existing valid index usable; without a prior index it leaves the Web console explicitly unavailable rather than publishing partial derived state;
- missing or malformed index, selected-run entry or period entry fails explicitly and recoverably and can be repaired through the supported `rop dashboard` regeneration path;
- canonical ROP run artifacts remain the business source of truth.

UI не хранит отдельный runtime state и не создаёт второй source of truth.

## Runtime foundation

Текущий реализованный контракт:

- UI-6 = enriched ROP dashboard/read-model;
- UI-7 = BeeUI-backed auth boundary.

- **BeeUI** — canonical web layer для BeeAgent;
- BeeAgent UI code находится в `src/beeagent_module/interfaces/ui/`;
- `app.py` создаёт embedded BeeUI app и BeeAgent read-only API routes;
- `adapter.py` содержит adapter methods, custom pages и artifact access;
- `read_model.py` содержит read-model и BeeUI `layout[]`;
- `artifacts.py` содержит artifact allowlist;
- `bounded_read.py` отвечает за bounded/redacted previews;
- `locale.py` содержит locale helper;
- thin CLI entrypoint в `src/beeagent_module/cli/web.py`;
- `config/beeui.yml` — источник правды для navigation/pages/tabs/locale/component seed;
- ROP block composition пока задаётся в BeeAgent read-model layout builders, а не полностью через config;
- `config/start.py` вызывает `beeagent_module.cli.web.run_web`;
- legacy `src/beeagent_module/web` заморожен;
- auth boundary реализован через BeeUI session/role layer;
- GET/read surfaces remain read-only by default; UI-8.8 blacklist Add/Update/Delete are explicit protected bounded POST exceptions, not runtime control endpoints;
- Queue `date_range` filter (UI-8.2) использует generic BeeUI Tabler Datepicker contract (Iteration 13.10) через `beeui>=0.23.0`;
- Queue toolbar (UI-8.3) использует canonical BeeUI Tabler toolbar contract (Iteration 13.11) через `beeui>=0.24.0`;
- ROP dashboard: KPI cards, processing funnel, source health, classification distribution, deterministic recommendations, attention events, attachment summary, evidence links;
- recommendations tab является частью ROP dashboard;
- recommendations tab читает delivery recommendations из `rop_recommendations.json`;
- recommendations tab отделён от legacy deterministic dashboard recommendations;
- локализация UI: en по умолчанию, ru через `?lang=ru` или persistent cookie `beeui_lang` (query параметр имеет приоритет), конфигурация в `config/beeui.yml`;
- product dashboard (`/`) с customer-facing KPI, summary, quick links и Technical details под катом;
- `/rop` рендерится как BeeUI generic adapter custom page;
- ROP page tabs use BeeUI progressive navigation with canonical SSR `href` values and controlled BeeUI icons; BeeAgent does not add tab-navigation JavaScript;
- browser artifact routes и shell принадлежат BeeUI;
- `/api/runs/{run_id}/artifacts/{artifact_id}` остаётся JSON envelope.

Entrypoint:

```bash
./start.sh web
```

CLI overrides:

```bash
./start.sh web --host 127.0.0.1 --port 8780 --no-open
```

Диагностика маршрутов:

```bash
./start.sh routes
```

## HTML routes (BeeUI-backed)

Реализованные HTML routes (через BeeUI product console + custom BeeAgent routes):

Основные product console pages поддерживают `?lang=ru`:

- `/` — dashboard
- `/health` — health check
- `/runs` — run history
- `/runs/{run_id}` — run detail
- `/rop` — ROP operator dashboard (tabs: overview, queue, threads, ai_assist, sources, attachments, evidence, bitrix, recommendations, blacklist)
- `/rop?tab=blacklist` — exact sender e-mail blacklist; mutation requires a known action, `operator`/`admin` authority, `rop` scope, CSRF validation/protection, product validation and audit. It grants no general runtime, CRM or mailbox execution authority. Future blacklisted messages use the existing `irrelevant` Bitrix path and show the classification override reason in ROP Event Detail.
- `/rop?tab=recommendations` — read-only, artifact-backed ROP recommendations tab
- `/modules` — module diagnostics
- `/runs/{run_id}/artifacts` — browser artifact list/viewer route, BeeUI-owned HTML
- `/runs/{run_id}/artifacts/{artifact_id}` — browser artifact detail route, BeeUI-owned HTML

## HTML routes (event detail)

Реализованные event detail HTML routes:

- `/rop/events/{event_id}` — ROP event detail review page (read-only)

Query parameters:

- `run_id` (required): run identifier
- `event_instance_id` (optional): additive run-local selector for a distinct processing occurrence when several items share the same public `event_id`; omitted for old runs and unique event ids.
- `lang` (optional, `en`/`ru`): locale override; при отсутствии параметра используется значение cookie `beeui_lang` (сохраняется BeeUI при выборе языка через `?lang=`), иначе default из `config/beeui.yml`

## Attachment download route (It40)

- `GET /rop/attachments/{attachment_id}/download?run_id=<run_id>&event_id=<event_id>` — authenticated/authorized forced download of an accepted original attachment.

Query parameters:

- `run_id` (required): run identifier
- `event_id` (optional): must match the manifest item when provided

Behavior:

- lookup только по safe manifest attachment id (никогда по произвольному filesystem path);
- invalid/unknown run/event/attachment ids и path traversal fail closed;
- response: forced `attachment`, `X-Content-Type-Options: nosniff`, `Cache-Control: no-store`, `application/octet-stream` (no inline render);
- route защищён существующей BeeUI session auth + resource authorization (ROP scope); ROP-scoped principal не может использовать его для чтения unrelated surfaces;
- Event Detail retains stored attachment metadata and this download action when `rop.attachments.enabled:false`; that switch disables semantic analysis only;
- raw attachment bytes никогда не отдаются через JSON API/HTML контент.

## JSON API routes

Реализованные JSON API routes (через BeeUI product console + custom BeeAgent routes):

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

## ROP recommendations tab contract

`/rop?tab=recommendations` — read-only, artifact-backed вкладка ROP dashboard.

Источник данных:

- `storage/runs/<run_id>/rop_recommendations.json`

Recommendations tab читает delivery recommendations из `rop_recommendations.json`. Она не должна использовать legacy deterministic dashboard recommendations как основной источник данных.

Доступные поля в текущем scope:

- `event_id`
- `sender`
- `subject`
- `title`
- `summary`
- `recommended_action`
- `recommended_queue`
- `target_bitrix_category`
- `priority`
- `reason`
- `confidence`
- `ai_used`
- `bitrix_status`
- `safe_to_execute`
- `requires_human_confirmation`
- `evidence_links`
- `detail_url`

Contract constraints:

- `safe_to_execute` в текущем scope должен оставаться `false`;
- UI не создаёт POST/write actions;
- UI не должен выполнять CRM/Bitrix/mailbox/module mutations;
- non-ignore recommendations требуют human confirmation.

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

- `summary` — counts per priority/bitrix state (same as UI-7)
- `items` — recommendation items from `rop_recommendations.json`
- `final_decisions` — bounded block from the final decisions read-model
  - `summary.total_events`, `summary.decision_source_counts`, `summary.attention_count`
  - `events[]` — per-event final decision fields:
    - `event_id`, `final_case_type`, `final_case_subtype`, `final_queue`, `final_action`
    - `final_decision_source`, `final_confidence`
    - `needs_attention`, nullable `attention_reason`
    - `automation_allowed`, `bitrix_write_allowed` (always false)
  - `summary` is recalculated from the bounded `events[]` returned by widget `max_items`

### ROP final decisions read-model contract

Источник: `storage/runs/<run_id>/rop_final_decisions.json`

Структура:

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

Источник: module-returned `base_classification` / `duplicate` blocks в `classified_events.json` и `rop_final_decisions.json`.

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

- `rop_ai_adjudicator_results.json` — AI adjudicator results for AI tab and event detail
- `rop_ai_adjudicator_requests.json` — AI adjudicator requests
- `rop_ai_adjudicator_decisions.json` — AI adjudicator decisions
- `rop_final_decisions.json` — final decision read-model

### AI tab changes (UI-8)

`/rop?tab=ai_assist` now shows:

- AI Adjudicator summary block when `rop_ai_adjudicator_results.json` exists
- Final Decisions summary block for artifact-first or computed read-only data
- legacy AI Assist summary only when legacy activity exists

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
- token value читается из env variable, имя которой задаётся через `bitrix.widget.token_env`;
- widget routes не защищаются BeeUI session auth, потому что это integration boundary для Bitrix embedding;
- при `bitrix.widget.enabled=true` routes всё равно защищены widget Bearer token.

Behavior:

- read-only;
- artifact-backed;
- читает `storage/runs/<run_id>/rop_recommendations.json`;
- не вызывает Bitrix REST;
- не делает CRM/Bitrix/mailbox/module/capability mutations;
- summary/list route при `bitrix.widget.enabled=false` возвращает safe disabled envelope;
- detail route при disabled widget возвращает unavailable/error envelope.

List/detail payload в текущем scope должен включать:

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

BeeAgent ROP Web Console может открываться внутри Bitrix24 как **Server-Side Local Application with User Interface**. Разрешённый Bitrix24 пользователь открывает приложение из портала и без отдельного BeeAgent login получает существующую read-only `/rop` console внутри iframe. Отдельный frontend и permanent URL credentials не вводятся.

### Config

Source of truth: `config/settings.yml` → `bitrix.embedded_app`:

```yaml
bitrix:
  embedded_app:
    enabled: false
    portal_origin: "" # exact HTTPS origin, обязателен при enabled=true
    default_role: "viewer" # least-privileged BeeUI role (в текущем scope только viewer)
    request_timeout: 10 # bounded таймаут (сек) для Bitrix current-user REST verification
```

Правила:

- `bitrix.embedded_app.enabled=true` требует `web.auth.enabled=true`;
- `portal_origin` — точный HTTPS origin (без path, query, trailing slash);
- launch input не выбирает role: verified Bitrix user получает configured `default_role` (`viewer` by default; configured `operator` is limited to a trusted Local App audience; embedded `admin` is not allowed);
- при `enabled=true` BeeUI получает `security.frame_ancestors=[portal_origin]`, `auth.cookie_samesite="none"`, `auth.cookie_secure=true` и canonical `auth.session_age_max`;
- BeeAgent не содержит Bitrix user-ID allowlist: доступ управляется Bitrix24.

### Routes

Реальный Bitrix24 Local Application payload (проверено в production): `AUTH_ID`, `AUTH_EXPIRES`, `REFRESH_ID`, `member_id`, `PLACEMENT`, `status` — поле `DOMAIN` Bitrix **не шлёт**. Привязка идёт по `member_id`, домен всегда берётся из configured `portal_origin` (outbound никогда не строится из данных запроса).

#### `POST /bitrix/rop/install`

One-time handler для привязки одного deployment к одному Bitrix portal.

- принимает bounded `application/x-www-form-urlencoded` form; обязательные поля — `member_id`, `AUTH_ID`, `AUTH_EXPIRES`; `PROTOCOL` (опционально, `https` или `1`), `DOMAIN` (опционально);
- `AUTH_ID` и `AUTH_EXPIRES` обязательны для первого install и reinstall: до любой записи state проверяются expiry (`AUTH_EXPIRES`) и active Bitrix current user через `user.current`; invalid/inactive/expired/rejected install не создаёт artifact;
- если `DOMAIN` передан — defense-in-depth: origin из `DOMAIN` должен совпадать с configured `portal_origin`, иначе `403 portal_mismatch`; проверка выполняется до любого outbound запроса;
- хранящийся state обязан соответствовать configured `portal_origin`/`portal_domain`, иначе `409 installation_portal_mismatch`;
- дополнительные поля Bitrix (`PLACEMENT`, `PLACEMENT_OPTIONS`, `REFRESH_ID`, `status`, `APP_SID`, `LANG` и любые другие) игнорируются — не хранятся, не логируются;
- body bounded (жёсткий лимит размера при стриминге, лимит числа полей, запрет дублирующихся ключей, лимит длины значений используемых полей);
- требует HTTPS request (HTTPS определяется по scheme ASGI запроса; trusted reverse proxy настраивает scheme, заголовок `X-Forwarded-Proto` от клиента не доверяется);
- привязка: после успешной verification первый `member_id` сохраняется атомарно (exclusive create) в фиксированный artifact `storage/interfaces/bitrix_rop_app.json` (только normalized `portal_domain`/`portal_origin` из config, `member_id`, `installed_at`, `contract_version`); при гонке state перечитывается и сверяется binding; другой `member_id` → `409 conflicting_installation`;
- install выполняет полный launch flow: создание viewer session и `303` на `/rop` (Bitrix реально доставляет open-контекст на install URL);
- не хранит и не логирует OAuth credentials;
- ответы `no-store` с `Referrer-Policy: no-referrer`.

#### `POST /bitrix/rop/launch`

Launch handler для application open context. Только POST; GET на `/bitrix/rop/launch` возвращает `405` и никогда не обрабатывает OAuth значения (query-параметры не используются).

- принимает bounded `application/x-www-form-urlencoded` form; используются только bounded `AUTH_ID`, `AUTH_EXPIRES` (обязательные), `member_id` (обязательный) и optional `REFRESH_ID`; `DOMAIN` не требуется (Bitrix его не шлёт), но при наличии проверяется против configured `portal_origin`;
- `AUTH_EXPIRES` принимается как unix timestamp или как число секунд жизни (TTL), например `3600`;
- дополнительные поля Bitrix (`PLACEMENT`, `PLACEMENT_OPTIONS`, `APP_SID`, `status`, `LANG` и любые другие) игнорируются — не хранятся и не логируются;
- body bounded (жёсткий лимит размера при стриминге, лимит числа полей, запрет дублирующихся ключей, лимит длины значений используемых полей);
- требует HTTPS request (scheme ASGI запроса);
- до любого outbound request: хранящийся `portal_origin`/`portal_domain` обязан совпадать с configured origin, optional `DOMAIN` при наличии обязан совпадать с configured origin, затем сверяется `member_id` с installation state; outbound REST call всегда идёт на configured `portal_origin` (`https://<portal_origin>/rest/user.current`) и никогда не строится из данных запроса;
- отклоняет malformed и expired launch;
- проверяет текущего пользователя официальным Bitrix REST `user.current` только против configured portal; для этого у приложения в Bitrix должно быть право **`user`** (Пользователи) — иначе Bitrix отклоняет вызов с `insufficient_scope`;
- отклоняет invalid/rejected token, inactive user, timeout и malformed REST response; при отказе возвращается `reason` (например `token_rejected`) и bounded `bitrix_error` (например `insufficient_scope`, `invalid_token`) без значений токена;
- не сохраняет и не логирует `AUTH_ID`/`REFRESH_ID`;
- создаёт BeeUI principal session для verified Bitrix user с configured `viewer` or `operator` role; browser input cannot select the role and embedded `admin` is not allowed;
- устанавливает `HttpOnly; Secure; SameSite=None` cookie через BeeUI public helper;
- возвращает `303 See Other` на `/rop` с `no-store` и `Referrer-Policy: no-referrer`.

### Session / iframe policy

- при `embedded_app.enabled=true` framing разрешён только configured portal через BeeUI `frame-ancestors` CSP (вместо `X-Frame-Options: DENY`);
- session cookie остаётся `HttpOnly` и `Secure`;
- `AUTH_ID`, `REFRESH_ID` и session secrets отсутствуют в URL, HTML, JS, logs и artifacts;
- существующий local BeeAgent login через `/auth/login` сохраняется.

### Backward compatibility

- `/api/bitrix/rop/widget*` остаются совместимыми и защищаются widget Bearer token;
- `GET /rop` без valid BeeUI session остаётся закрытым (redirect на `/auth/login` или `401`);
- GET routes остаются read-only.

## Auth mode (UI-7)

BeeAgent Web Console поддерживает config-driven auth boundary через BeeUI session/role layer. BeeUI владеет login/logout/session/CSRF. BeeAgent владеет config/env policy, bootstrap, CLI rotation, route protection и server-side resource authorization.

Auth настройки живут в `config/settings.yml` → `web.auth`:

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

Реальные secrets живут только в env:

- `BEEAGENT_WEB_SESSION_SECRET` — secret для HMAC-подписи session cookie
- `BEEAGENT_WEB_ADMIN1_TOKEN`, `BEEAGENT_WEB_ADMIN2_TOKEN` — token для аутентификации

Secrets никогда не хранятся в `settings.yml`.

### Principal model (UI-8.6)

```text
principal identity = exact username + token
authority = role
resource access = scopes
```

- local login привязывается к exact configured `username + token` паре;
- successful session получает canonical configured principal `id` (не произвольный browser `user_id`);
- `role` остаётся только authority level: `viewer` / `operator` / `admin`;
- `scopes` определяют resource access: `*` (full access), `dashboard`, `rop`, `runs`, `modules`;
- `scopes` обязательны для каждого principal и валидируются fail-fast;
- `["*"]` — единственный допустимый wildcard: wildcard не комбинируется с другими scopes;
- разные principals с одинаковым resolved token value отклоняются на startup без раскрытия secret;
- generic auth failure не раскрывает, какой credential неверен.

### Bootstrap

- `ensure_web_auth_env(...)` выполняется до `load_settings(...)`;
- при `web.auth.enabled=true` отсутствующие или пустые auth env values генерируются автоматически;
- пустые ключи в `.env` обновляются in-place;
- отсутствующие ключи дописываются в `.env`;
- значения выставляются в `os.environ` для текущего процесса;
- новый `.env` на POSIX получает `0600`; bootstrap и rotation сохраняют режим и группу существующего `.env`;
- в stdout печатается только `KEY=<generated>`.

### Rotation CLI

```bash
./start.sh auth rotate <principal-id-or-username>
./start.sh auth rotate all
./start.sh auth rotate all --logout-all
./start.sh auth rotate session
```

После rotation нужен restart web app. Session secret не печатается.

### Поведение

- `web.auth.enabled: false` (default): текущее local/dev поведение без auth.
- `web.auth.enabled: true`: включена session-based auth через BeeUI c server-side authorization.
- external exposure с `web.auth.enabled=false` должна считаться rejected/fail-fast по settings policy.

### Protected routes (when enabled)

HTML routes:

- `/`, `/rop`, `/rop/events/{event_id}`, `/rop/attachments/{attachment_id}/download`, `/runs`, `/runs/{run_id}`, `/runs/{run_id}/artifacts`, `/runs/{run_id}/artifacts/{artifact_id}`, `/modules`

API routes:

- `/api/*`

Любой не-public путь (включая неизвестные/future protected surfaces) является protected: default-deny для non-wildcard principals. Даже неизвестный `/api/...` путь при включённом auth требует аутентификации до возврата route-level результата.

### Public routes

- `/health` — public sanitized health check (без details runtime state)
- `/static/*` — public static assets
- `/auth/*` — auth routes owned by BeeUI (login/logout/CSRF)
- `/api/bitrix/rop/widget*` — integration boundary, не требует BeeUI session cookie, но при enabled widget требует route-level Bearer token
- `/bitrix/rop/install`, `/bitrix/rop/launch` — Bitrix embedded app entry points (требуют HTTPS и `bitrix.embedded_app.enabled=true`; при disabled возвращают bounded error)

### Resource authorization (UI-8.6)

Server-side authorization выполняется центральным BeeAgent policy по canonical session identity + текущему config:

- `admin + scopes=["*"]` сохраняет полный доступ ко всем HTML/API/resource routes;
- `viewer + scopes=["rop"]` (и любой другой non-wildcard principal с `rop`) получает:
  - `/rop`, Event Detail, `/api/rop/*`;
  - bounded ROP-owned evidence artifacts из allowlist (`/runs/{run_id}/artifacts/{allowlisted_id}`);
  - запрещены Dashboard, Runs, Modules, unrelated runs/artifacts/API;
- unknown protected surface → default-deny;
- navigation visibility отражает authorization, но не заменяет server-side enforcement;
- ROP-only principal после login попадает на `/rop` (landing redirect);
- verified Bitrix external principal (user_id не в `web.auth.principals`) remains bounded ROP-only with its configured `viewer` or trusted Local App `operator` role; embedded `admin` is not allowed.

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

Session управляется BeeUI через подписанную cookie `beeui_session`. Session secret читается из env по `web.auth.session_secret_env`. Session хранит canonical principal `user_id` (идентифицирует principal в `web.auth.principals`) и `role`.

### Роли

- `viewer` — просмотр dashboard/run/ROP (read-only)
- `operator` — operator-level доступ (future)
- `admin` — admin-level доступ (future config/actions)

Поддерживаются `viewer` / `operator` / `admin`. Role не определяет resource scope: resource access определяется только `scopes`. GET/read routes остаются read-only; UI-8.8 blacklist actions являются explicit bounded POST exception с server-side authority, CSRF, validation и audit.

### Rollout

При rollout UI-8.6 обязательна invalidation/rotation старых sessions и credentials:

- session secret rotation (`./start.sh auth rotate all --logout-all` или `session`) аннулирует все существующие signed cookies;
- principal token rotation (`./start.sh auth rotate <principal-id-or-username>`) требует повторного входа;
- в `web.auth.principals[]` для каждого principal обязателен явный `scopes`.

## Artifact routes

Реализованные artifact routes:

- `/runs/{run_id}/artifacts` — browser HTML route
- `/runs/{run_id}/artifacts/{artifact_id}` — browser HTML route
- `/api/runs/{run_id}/artifacts` — JSON (список доступных артефактов)
- `/api/runs/{run_id}/artifacts/{artifact_id}` — JSON envelope (machine-readable)

Правила:

- доступ к артефактам идёт по allowlisted `artifact_id`, а не по произвольному имени файла;
- browser-routes (`/runs/...`) возвращают BeeUI HTML;
- API-route (`/api/runs/...`) возвращает bounded/redacted JSON envelope;
- произвольные имена файлов и path-like значения отклоняются;
- raw `.eml` и attachment content не отдаются.

### Artifact viewer (browser route)

Browser route показывает bounded/redacted artifact preview через BeeUI. Внутренняя HTML-структура viewer не фиксируется этим документом.

### Примеры ответов

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
    "action_draft": {
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

Пример ответа для несуществующего события:

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

Пример ответа для non-allowlisted artifact:

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

Разрешённые artifact ID и их fixed mapping внутри run directory:

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
| `rop_action_drafts_json`          | `rop_action_drafts.json`                              |
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

UI не отдаёт произвольные файлы из `storage/`. `artifact_id` маппится на фиксированный allowlisted relative path. It32 artifacts `rop_context_enrichment.json`, `rop_recommendations.json` и `rop_evaluation.json` в текущей реализации не входят в generic artifact allowlist. Recommendations tab и widget API читают `rop_recommendations.json` через read-model/widget code, а не через browser artifact viewer.

`rop_writeback_summary.json` — read-only per-run projection операторского write-back state (Iteration 37): bounded outcome/status per event (`create_lead` / `attach_existing` / `deferred`), source of truth — `storage/interfaces/rop_writeback_state.json`. Проекция не содержит credentials, raw `.eml` и raw attachment content.

ROP dashboard поддерживает period query parameter: `?period=today`, `?period=yesterday`, `?period=7d`, `?period=30d`, `?period=90d`, `?period=365d`, `?period=all`. Default period берётся из `config/settings.yml` → `rop.dashboard.default_period` (по умолчанию `7d`). Period фильтрует classified events по `event_date`/`received_at`/`timestamp`. Period `all` отключает фильтрацию.

### Cross-run period aggregation (ROP dashboard)

ROP dashboard агрегирует события по периоду для выбранного клиента:

- `run_id` — anchor run и client scope для выбранного-run operational evidence;
- `business_kpi`, `series` и period queues агрегируют уникальные same-client события по релевантным успешным run'ам (degraded/error run'ы исключаются с bounded warning `incomplete_run_skipped`);
- stable base identity события: `client_id + source_id + (message_id → x_email_id → event_id)`;
- внутри одного run повторяющиеся occurrences одного stable base (например, одно письмо с одним `message_id`, попавшее в батч несколько раз) различаются deterministic occurrence slot (по source timestamp order, `event_id`/`event_instance_id` tie-break) и сохраняются раздельно;
- cross-run canonical winner — newest run per `(client_id, source_id, stable base, occurrence slot)`, поэтому одно и то же письмо в нескольких mailbox polls/runs не умножается в `7d/30d/all`; `run_id + event_instance_id` не является cross-run business identity;
- `event_instance_id` — BeeAgent-owned run-local processing occurrence selector: используется только для ordering/disambiguation внутри run и artifact/UI lookup, не передаётся как domain matching signal и не заменяет public `event_id`;
- identity очередей — `(origin_run_id, source_id, event_id, event_instance_id)` с legacy-safe fallback (пустой selector для старых run'ов); разные source события с одинаковым `event_id` не схлопываются; разные occurrence одного `event_id` внутри run сохраняются отдельно;
- attachment items (`attachment_extraction.json`) несут аддитивное поле `event_instance_id`, чтобы привязывать каждый item к своему run-local occurrence; повторные occurrences одного `event_id` получают только свои attachment items; legacy item без `event_instance_id` привязывается только когда соответствие однозначно (одно occurrence), иначе не приписывается ни одному из повторных occurrences; `attachment_refused` KPI считается по occurrence-aware identity;
- `latest_selection`, threads, AI evidence, evidence links и source health остаются anchor-run specific;
- queue/detail links используют origin `run_id` события;
- period filtering применяется к агрегированному business view;
- опциональные malformed артефакты (`bitrix_reconciliation.json`, `attachment_extraction.json`) игнорируются с bounded warning `malformed_optional_artifact`; aggregate-only attachment counters не приписываются событиям (warning `attachment_aggregate_unscoped`).

ROP dashboard включает вкладку Bitrix / Bitrix Evidence Board. Она читает только artifact-level current-state projection (`rop_current_state.json`) и optional `bitrix_reconciliation.json`, показывает read-only KPI и очереди matched/lost/ambiguous/degraded/unreconciled без POST actions или write-back.

Отклоняются:

- raw `.eml`
- raw attachments
- arbitrary files
- logs with secrets
- env/config secrets
- mailbox password values
- provider tokens
- mailbox source content beyond normalized/sanitized artifacts

### ROP dashboard contract (UI-6 — enriched)

`GET /api/rop/dashboard` возвращает source-aware ROP dashboard read-model с расширенными полями.

Поддерживаемые query parameters:

- `run_id` — optional explicit run selection; если параметр не передан, используется latest run;
- `period` — period filter для dashboard data: `today`, `yesterday`, `7d`, `30d`, `90d`, `365d`, `all` (default определяется `config/settings.yml` → `rop.dashboard.default_period`);
- `tab` — HTML page tab selector для `/rop`;
- `lang` — HTML page locale selector для `/rop`.

`/api/rop/dashboard` принимает `run_id` и `period`.

Existing UI-5 fields сохранены (backward-compatible).

Новые поля в UI-6 enriched payload (It30):

- `business_kpi` — бизнес-метрики:
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
- `period` — текущий период;
- `period_start_utc`, `period_end_utc` — границы периода;
- `time_basis` — basis used: `event_timestamp`, `run_generated_at`, `run_mtime_fallback`, `mixed`, `unknown`.

UI-6 добавляет поля:

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

HTML `/rop` использует BeeUI tabs:

- `overview`
- `queue`
- `threads`
- `ai_assist`
- `sources`
- `attachments`
- `evidence`
- `bitrix` — read-only, artifact-backed; при отсутствии Bitrix/current-state artifacts показывает empty/unavailable state

Возвращаемые данные (UI-6 enriched payload):

- `selected_run_id` — выбранный run ID;
- `available_runs` — bounded recent run-id window из `rop_web_projection.json` index (`run_ids`, фиксированный bound), не результат сканирования `storage/runs` при GET;
- `total_runs` — scalar materialized total run count из projection index (не длина `available_runs`);
- `kpis` — сводные KPI:
  - `total_runs` — scalar materialized total run count из projection index;
  - `source_count`, `loaded_source_count`, `degraded_source_count`;
  - `fetched_count`, `loaded_count`, `malformed_count`;
  - `normalized_count`, `classified_count`, `classification_failed_count`, `fallback_count`;
  - `high_priority_count`, `medium_priority_count`, `low_priority_count`;
  - `attachment_count`, `attachment_preview_count`, `attachment_refused_count`, `attachment_blocked_count`;
  - `review_tsv_available`;
- `funnel` — processing funnel stages;
- `source_health` — per-source health with `reason`, `fetched_count`, `loaded_count`, `malformed_count`, `classified_count`, `fallback_count`;
- `classification_distribution` — `case_type_counts`, `priority_counts`, `reason_code_counts`, `fallback_count`;
- `attachment_summary` — aggregate counts без raw content;
- `recommendations` — deterministic operator recommendations;
- `attention_events` — priority-ordered classified events (max 500);
- `evidence_links` — allowlisted artifact links with availability flag;
- `warnings` — missing/malformed/degraded warnings.

Backward-compatible поля сохранены:

- `run_id`, `summary`, `source_diagnostics`, `intake_metadata`;
- `sources[]`, `classified_count`, `case_type_counts`, `priority_counts`, `fallback_count`, `normalized_count`, `has_attachment_extraction`.

### Пример ответа (UI-6 /api/rop/dashboard)

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

`GET /rop` рендерит BeeUI generic adapter custom page для rich ROP dashboard.

Поддерживаемые query parameters:

- `run_id` — optional explicit run selection;
- `tab` — tab selector;
- `period` — period selector;
- `lang` — locale override (`en` или `ru`), fallback на `en`.

Источник данных: `BeeAgentUiAdapter.get_page("rop_dashboard", query)`.

Источник layout: `build_rop_page_layout(...)`.

Секции страницы:

- `overview`: верхний ряд с `Run Overview` (`state_grid`, `width: 8`) и `Key Metrics` (`kpi_grid`, `width: 4`, `columns: 2`), warnings идут после верхнего ряда; Overview использует period dropdown;
- `queue`: attention events;
- `threads`: сводка цепочек и таблица групп;
- `ai_assist`: сводка AI assist и таблица событий;
- `sources`: source health details;
- `attachments`: attachment processing summary;
- `evidence`: allowlisted evidence links;
- `bitrix`: read-only, artifact-backed; при отсутствии Bitrix/current-state artifacts показывает empty/unavailable state;
- `recommendations`: delivery recommendations из `rop_recommendations.json`.

BeeAgent не держит manual HTML builders/templates для `/rop`.

## Read-only and security rules

Web Console должен соблюдать:

- no GET mutation;
- no non-auth operator POST/write actions except explicit UI-8.8 protected blacklist mutations;
- BeeUI auth POST endpoints допустимы только для authentication/session flow;
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
- cache-control требования должны соблюдаться на route layer, но их фактический enforcement нужно подтверждать отдельно.

### UI-6 evidence sections (latest-N, threads, AI assist)

Read-only операторские секции на основе It30 артефактов, интегрированные в текущий контракт:

- **Latest/N selection**: `latest_selection` в read-model показывает количество выбранных писем, стратегию, источники;
- **Thread summary**: `thread_summary` и `threads[]` показывают цепочки писем и thread-контекст;
- **AI assist**: `ai_assist_summary` и `ai_assist_events[]` показывают evidence AI assist и статус каждого события;
- **RU labels**: через `?lang=ru` переводятся все новые UI-6 секции;
- **Det recommendations**: обогащены `_build_it30_recommendations()` — review threaded conversations, AI degraded, low confidence, module contract unavailable;
- **New tabs**: `/rop?tab=threads` и `/rop?tab=ai_assist`.

### UI-6 — Артефакты It30 в allowlist

Добавлены в `ARTIFACT_ALLOWLIST`:

| ID                             | Relative path                  |
| ------------------------------ | ------------------------------ |
| `mailbox_selection_json`       | `mailbox_selection.json`       |
| `mail_thread_index_json`       | `mail_thread_index.json`       |
| `mail_thread_context_json`     | `mail_thread_context.json`     |
| `rop_ai_assist_requests_json`  | `rop_ai_assist_requests.json`  |
| `rop_ai_assist_decisions_json` | `rop_ai_assist_decisions.json` |
| `rop_ai_assist_results_json`   | `rop_ai_assist_results.json`   |

### UI-6 — Новые поля `/api/rop/dashboard`

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

Existing UI-5 поля сохраняются.

### HTML route `/rop` — UI-6 tabs

Текущие вкладки:

- `threads` — сводка цепочек и таблица групп;
- `ai_assist` — сводка AI assist и таблица событий.

Поддерживается `?lang=ru` для русских меток во всех новых секциях.

Sanitization rules:

- JSON responses strip `raw_eml`, `raw_message`, `attachment_content`, `content`, `content_bytes`, `payload_bytes`;
- raw `.eml` / `message/rfc822` content is never rendered; blocked nested-email attachments may remain in rendered payloads only as bounded lifecycle metadata with `storage_status=blocked` and `reason_code=blocked_email_attachment`, without blob or download link;
- dashboard shows only bounded metadata, lifecycle status and preview fields.

## Out of scope

Текущий контракт intentionally does not include:

- per-role RBAC enforcement;
- UI settings/config editing;
- user registration/password reset;
- OAuth/OIDC;
- DB-backed user management;
- POST/write actions;
- CRM/mailbox actions;
- UI-triggered CRM/Bitrix write-back; controlled server-side `rop run` and `rop poll` write-back remains outside Web/widget routes;
- web-triggered ROP run;
- widget-triggered execution;
- save-human-decision UI flow;
- production deployment hardening;
- attachment parsing/OCR;
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

Все параметры Queue tab передаются через query string в `/rop?tab=queue`.

#### Filter params

| Param            | Type    | Description                                             | Validation                                                                                 |
| ---------------- | ------- | ------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `q`              | string  | Full-text search across sender and subject              | Любое строковое значение                                                                   |
| `sender`         | string  | Filter by sender (legacy, use `q` for combined search)  | Любое строковое значение                                                                   |
| `subject`        | string  | Filter by subject (legacy, use `q` for combined search) | Любое строковое значение                                                                   |
| `case_type`      | string  | Comma-separated classification values                   | Должен быть одним из: `new_lead`, `existing_client`, `existing_deal`, …                    |
| `classification` | string  | Legacy alias for `case_type` (mapped to `case_type`)    | То же, что `case_type`                                                                     |
| `priority`       | string  | Comma-separated priority values                         | `low`, `medium`, `high`, `critical`                                                        |
| `bitrix_status`  | string  | Comma-separated Bitrix reconciliation status values     | `not_found`, `weak_match`, `ambiguous`, `duplicate_candidate`, …                           |
| `is_fallback`    | boolean | Filter by fallback classification (`true`/`false`)      | `true` или `false`                                                                         |
| `queue`          | string  | Filter by operator queue bucket name                    | `high_priority`, `needs_review`, `lost_in_bitrix`, `ambiguous`, `degraded`, `unreconciled` |
| `date_from`      | date    | Start of date range (inclusive, YYYY-MM-DD)             | Должен быть корректной датой; не позже `date_to`                                           |
| `date_to`        | date    | End of date range (inclusive, YYYY-MM-DD)               | Должен быть корректной датой; не раньше `date_from`                                        |

#### Column params

| Param     | Type            | Description                                                                                     |
| --------- | --------------- | ----------------------------------------------------------------------------------------------- |
| `columns` | comma-separated | Visible column keys: `priority`, `client`, `subject`, `date`, `classification`, `bitrix_status` |

Column visibility is managed through the toolbar ellipsis action (column chooser). `columns_open` and `open_dropdowns` are no longer part of the Queue presentation-state contract.

#### Pagination params

| Param       | Type    | Default       | Description           | Validation                                                                                         |
| ----------- | ------- | ------------- | --------------------- | -------------------------------------------------------------------------------------------------- |
| `page`      | integer | `1`           | Page number (1-based) | `>= 1`                                                                                             |
| `page_size` | integer | `25`          | Items per page        | `25`, `50`, или `100`                                                                              |
| `sort`      | string  | `received_at` | Sort field            | `received_at`, `date`, `event_date`, `sender`, `subject`, `case_type`, `priority`, `bitrix_status` |
| `order`     | string  | `desc`        | Sort direction        | `asc` или `desc`                                                                                   |

`sort` и `order` образуют атомарную пару: URL содержит оба параметра или не содержит ни одного для default `received_at` / `desc`.

#### Canonical params preserved in all ROP links

- `run_id` — explicit run identifier
- `tab` — active tab name (overview, queue, threads, …)
- `period` — period value (today, yesterday, 7d, 30d, 90d, 365d, all)
- `lang` — locale override (en, ru)

### Toolbar contract (BeeUI Iteration 13.11)

Queue toolbar contains:

- `fields`: date_range (no visible label, accessible via `from_label`/`to_label`), `q` text input (no visible label, accessible via `placeholder`), checkboxes dropdowns for Classification (`case_type`), Priority (`priority`), Bitrix Status (`bitrix_status`)
- `hidden`: preserves `tab`, `run_id`, `period`, `lang`, `page`, `page_size`, `sort`, `order`, а также активные `case_type`, `priority`, `bitrix_status`, `columns` — чтобы GET submission поиска или дат не сбрасывал dropdown filters и column visibility
- `column_toggles`: column visibility toggles rendered under the ellipsis action
- `reset`: resets all filter params preserving `tab`, `run_id`, `period`, `lang`
- No `apply` — datepicker auto-submits on select/clear; text/date input submits on GET

`columns_open` и `open_dropdowns` не являются частью canonical toolbar contract. Они поддерживаются только в legacy accepted inputs adapter contract для обратной совместимости с существующими ссылками и bookmark.

Queue sets the stable `data_table.id` value `rop-queue` and supplies the released
BeeUI 0.26.4 pagination/page-size payload. This opts the table into BeeUI's
generic progressive same-origin GET replacement while keeping BeeAgent's
server-side query semantics authoritative. BeeAgent supplies safe navigation
hrefs and the product-owned page-size choices `25`, `50`, and `100`; BeeUI owns
the live interaction and compact pagination presentation.

Other BeeAgent adapter-backed tables use the canonical `data_table` presentation but do not receive Queue toolbar controls.

### Adapter-level validation contract

Все filter/pagination/sort параметры валидируются в одном adapter-level contract в `BeeAgentUiAdapter.get_page()`. Процесс:

1. `_extract_and_validate_params(query)` — единая функция, извлекающая и валидирующая filter + pagination + sort параметры
2. Валидация проверяет: queue, columns, dropdown state, booleans, dates, enums, page/page_size, sort/order
3. Невалидные значения возвращают `invalid_params` error вместо молчаливого расширения выборки
4. `validate_filter_params()` — проверяет filter-специфичные значения
5. `validate_pagination_params()` — проверяет page/page_size/sort/order
6. Каноническая страница из `paginate_items()` используется во всех rows, labels, links и API metadata

### Date sorting semantics

- Valid ISO dates (`2026-06-15T00:00:00Z`) группируются перед invalid/missing
- Missing/malformed dates (`""`, `null`, `"invalid"`) всегда после валидных — как при asc, так и при desc
- Asc: валидные даты по возрастанию, затем missing
- Desc: валидные даты по убыванию, затем missing

### Attention cap

- `ATTENTION_EVENTS_MAX = 500` — максимальное количество событий в attention events
- Queue tab показывает все события из `queues[]` buckets, capped per period filtering
