# WEB UI — BeeAgent Web Console contract

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
- нет non-auth operator POST/write actions и runtime control endpoints;
- ROP dashboard: KPI cards, processing funnel, source health, classification distribution, deterministic recommendations, attention events, attachment summary, evidence links;
- recommendations tab является частью ROP dashboard;
- recommendations tab читает delivery recommendations из `rop_recommendations.json`;
- recommendations tab отделён от legacy deterministic dashboard recommendations;
- локализация UI: en по умолчанию, ru через `?lang=ru`, конфигурация в `config/beeui.yml`;
- product dashboard (`/`) с customer-facing KPI, summary, quick links и Technical details под катом;
- `/rop` рендерится как BeeUI generic adapter custom page;
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
- `/rop` — ROP operator dashboard (tabs: overview, queue, threads, ai_assist, sources, attachments, evidence, bitrix, recommendations)
- `/rop?tab=recommendations` — read-only, artifact-backed ROP recommendations tab
- `/modules` — module diagnostics
- `/runs/{run_id}/artifacts` — browser artifact list/viewer route, BeeUI-owned HTML
- `/runs/{run_id}/artifacts/{artifact_id}` — browser artifact detail route, BeeUI-owned HTML

## HTML routes (event detail)

Реализованные event detail HTML routes:

- `/rop/events/{event_id}` — ROP event detail review page (read-only)

Query parameters:

- `run_id` (required): run identifier
- `lang` (optional, `en`/`ru`): locale override

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

Recommendations tab читает delivery recommendations из `rop_recommendations.json`.
Она не должна использовать legacy deterministic dashboard recommendations как основной источник данных.

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
      "bitrix_write_allowed": false
    }
  ]
}
```

Policy v1:

- AI adjudicator `ok` → AI fields, `automation_allowed=false`
- `low_confidence_preserve` → deterministic preserved, `needs_attention=true`, `automation_allowed=false`
- `manual_review_degrade` → deterministic preserved, `needs_attention=true`, fallback manual_review queue/action
- No AI result → deterministic fields, `final_decision_source=deterministic`
- Invalid/unusable → `final_decision_source=fallback_policy`, `needs_attention=true`

Always `automation_allowed=false` and `bitrix_write_allowed=false`.

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

## Auth mode (UI-7)

BeeAgent Web Console поддерживает config-driven auth boundary через BeeUI session/role layer.
BeeUI владеет login/logout/session/CSRF.
BeeAgent владеет config/env policy, bootstrap, CLI rotation и route protection.

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
        token_env: BEEAGENT_WEB_ADMIN1_TOKEN
```

Реальные secrets живут только в env:

- `BEEAGENT_WEB_SESSION_SECRET` — secret для HMAC-подписи session cookie
- `BEEAGENT_WEB_ADMIN1_TOKEN`, `BEEAGENT_WEB_ADMIN2_TOKEN` — token для аутентификации

Secrets никогда не хранятся в `settings.yml`.

### Bootstrap

- `ensure_web_auth_env(...)` выполняется до `load_settings(...)`;
- при `web.auth.enabled=true` отсутствующие или пустые auth env values генерируются автоматически;
- пустые ключи в `.env` обновляются in-place;
- отсутствующие ключи дописываются в `.env`;
- значения выставляются в `os.environ` для текущего процесса;
- на POSIX для `.env` выставляется `chmod 0600`;
- в stdout печатается только `KEY=<generated>`.

### Rotation CLI

```bash
./start.sh auth rotate <principal-id-or-username>
./start.sh auth rotate all
./start.sh auth rotate all --logout-all
./start.sh auth rotate session
```

После rotation нужен restart web app.
Session secret не печатается.

### Поведение

- `web.auth.enabled: false` (default): текущее local/dev поведение без auth.
- `web.auth.enabled: true`: включена session-based auth через BeeUI.
- external exposure с `web.auth.enabled=false` должна считаться rejected/fail-fast по settings policy.

### Protected routes (when enabled)

HTML routes:

- `/`, `/rop`, `/rop?*`, `/rop/events/{event_id}`, `/runs`, `/runs/{run_id}`, `/runs/{run_id}/artifacts`, `/runs/{run_id}/artifacts/{artifact_id}`, `/modules`

API routes:

- `/api/*`

Даже неизвестный `/api/...` путь при включённом auth требует аутентификации до возврата route-level результата.

### Public routes

- `/health` — public sanitized health check (без details runtime state)
- `/static/*` — public static assets
- `/auth/*` — auth routes owned by BeeUI (login/logout/CSRF)
- `/api/bitrix/rop/widget*` — integration boundary, не требует BeeUI session cookie, но при enabled widget требует route-level Bearer token

### Unauthenticated response

HTML routes: redirect to `/auth/login`.

API routes: `401` JSON envelope:

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

Session управляется BeeUI через подписанную cookie `beeui_session`. Session secret читается из env по `web.auth.session_secret_env`.

### Роли

- `viewer` — просмотр dashboard/run/ROP (read-only)
- `operator` — operator-level доступ (future)
- `admin` — admin-level доступ (future config/actions)

Поддерживаются `viewer` / `operator` / `admin`.
UI-7 пока не применяет дифференцированные permissions.
Все текущие business/operator routes Web Console остаются read-only.

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

UI не отдаёт произвольные файлы из `storage/`. `artifact_id` маппится на фиксированный allowlisted relative path.
It32 artifacts `rop_context_enrichment.json`, `rop_recommendations.json` и `rop_evaluation.json` в текущей реализации не входят в generic artifact allowlist. Recommendations tab и widget API читают `rop_recommendations.json` через read-model/widget code, а не через browser artifact viewer.

ROP dashboard поддерживает period query parameter: `?period=today`, `?period=yesterday`, `?period=7d`, `?period=30d`, `?period=90d`, `?period=365d`, `?period=all`. Default period берётся из `config/settings.yml` → `rop.dashboard.default_period` (по умолчанию `7d`). Period фильтрует classified events по `event_date`/`received_at`/`timestamp`. Period `all` отключает фильтрацию.

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
- `available_runs` — список всех run ID;
- `kpis` — сводные KPI:
  - `total_runs`, `selected_run_id`, `run_status`;
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
- `attention_events` — priority-ordered classified events (max 50);
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
- no non-auth operator POST/write actions;
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
- attachment entries with `.eml` or `message/rfc822` are removed from rendered payloads;
- dashboard shows only metadata/preview fields.

## Out of scope

Текущий контракт intentionally does not include:

- per-role RBAC enforcement;
- UI settings/config editing;
- user registration/password reset;
- OAuth/OIDC;
- DB-backed user management;
- POST/write actions;
- CRM/mailbox actions;
- CRM/Bitrix write-back;
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
