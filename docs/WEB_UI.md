# WEB UI — BeeAgent Web Console contract

## Purpose

Этот документ фиксирует актуальный implemented contract для BeeAgent Web Console.

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

## Source of truth

Runtime bind/source of truth для web режима:

- `config/settings.yml`
  - `web.host`
  - `web.port`
  - `web.open_browser`

Read-model/source of truth для данных UI:

- existing artifacts в `storage/`
  - `storage/runs/<run_id>/...`
  - `storage/interfaces/modules.json`

UI не хранит отдельный runtime state и не создаёт второй source of truth.

## Runtime foundation

UI-1 implemented foundation:

- FastAPI backend inside `src/beeagent_module/web`;
- Jinja2 server-side templates;
- vendored Tabler static assets from `src/beeagent_module/web/static/vendor/tabler/`;
- read-only HTML pages;
- read-only JSON API;
- no auth, no POST actions, no runtime control endpoints.

Entrypoint:

```bash
./start.sh web
```

или:

```bash
uv run python3 config/start.py web
```

## HTML routes

Implemented HTML routes:

- `/`
- `/runs`
- `/runs/{run_id}`
- `/runs/{run_id}/rop`
- `/modules`

Supporting read-only download routes:

- `/runs/{run_id}/tsv`
- `/runs/{run_id}/artifact/{artifact_name}`
- `/runs/{run_id}/module-artifact/{artifact_name}`

## JSON API routes

Implemented JSON API routes:

- `/api/runs`
- `/api/runs/{run_id}`
- `/api/rop/runs/{run_id}/dashboard`
- `/api/modules`

Supporting API schema route:

- `/api/openapi.json`

### UI-2 ROP dashboard contract

`GET /api/rop/runs/{run_id}/dashboard` now returns source-aware read-model data for
both old single-source and new multi-source It24 artifacts.

Added/extended fields:

- `source_aggregate` with source and classification KPIs;
- `sources[]` per-source summary rows;
- source-aware `filter_options` (`source_id`, `source_role`, `source_status`);
- source-aware `filters` values;
- source-aware `rows[]` fields:
  - `source_id`;
  - `source_type`;
  - `source_role`;
  - `source_display_name`;
  - `client_id`;
  - `source_status`.

Supported filters for HTML/API:

- `source_id`
- `source_role`
- `source_status`
- `case_type`
- `priority`
- `fallback`
- `reason_code`

### Example response object

`GET /api/runs/{run_id}`

```json
{
  "run_id": "live-review-2026-05-15",
  "errors": [],
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
      },
      {
        "source_id": "sales_mailbox",
        "loaded_count": 0,
        "status": "degraded"
      }
    ]
  },
  "counts": {
    "normalized_count": 3,
    "classified_count": 3
  },
  "available_artifacts": [
    {
      "name": "operator_summary.json",
      "url": "/runs/live-review-2026-05-15/artifact/operator_summary.json"
    }
  ],
  "module_artifacts": [
    {
      "name": "rop_summary_result.json",
      "url": "/runs/live-review-2026-05-15/module-artifact/rop_summary_result.json"
    }
  ],
  "tsv_exists": true,
  "tsv_url": "/runs/live-review-2026-05-15/tsv"
}
```

`GET /api/rop/runs/{run_id}/dashboard`

```json
{
  "run_id": "live-review-2026-05-15-multi",
  "errors": [],
  "source_aggregate": {
    "source_count": 2,
    "loaded_source_count": 1,
    "degraded_source_count": 1,
    "fetched_count": 3,
    "loaded_count": 3,
    "malformed_count": 0,
    "normalized_count": 3,
    "classified_count": 3,
    "classification_failed_count": 0,
    "fallback_count": 1
  },
  "sources": [
    {
      "source_id": "hotline_mailbox",
      "source_type": "mailbox_readonly",
      "source_role": "technical_aggregator",
      "source_display_name": "Welding Hotline mailbox",
      "client_id": "welding",
      "authority": "read_only",
      "mailbox_folder": "welding",
      "status": "ok",
      "reason": "",
      "items_max": 20,
      "fetched_count": 3,
      "loaded_count": 3,
      "malformed_count": 0,
      "classified_count": 3,
      "fallback_count": 1
    },
    {
      "source_id": "sales_mailbox",
      "source_type": "mailbox_readonly",
      "source_role": "sales_mailbox",
      "source_display_name": "Welding Sales mailbox",
      "client_id": "welding",
      "authority": "read_only",
      "mailbox_folder": "sales",
      "status": "degraded",
      "reason": "source_load_error",
      "items_max": 20,
      "fetched_count": 0,
      "loaded_count": 0,
      "malformed_count": 0,
      "classified_count": 0,
      "fallback_count": 0
    }
  ],
  "filters": {
    "source_id": "",
    "source_role": "",
    "source_status": "",
    "case_type": "",
    "priority": "",
    "fallback": "",
    "reason_code": ""
  },
  "filter_options": {
    "source_id": ["hotline_mailbox", "sales_mailbox"],
    "source_role": ["sales_mailbox", "technical_aggregator"],
    "source_status": ["degraded", "ok"],
    "case_type": ["duplicate", "new_lead"],
    "priority": ["high", "medium"],
    "reason_code": ["duplicate_sender", "new_contact"]
  },
  "rows": [
    {
      "event_id": "evt-1",
      "source_id": "hotline_mailbox",
      "source_type": "mailbox_readonly",
      "source_role": "technical_aggregator",
      "source_display_name": "Welding Hotline mailbox",
      "client_id": "welding",
      "source_status": "ok",
      "sender": "first@example.com",
      "subject": "Need price",
      "body_short": "Need welding consumables",
      "attachments": "brief.pdf (application/pdf, 1024)",
      "bot_case_type": "new_lead",
      "bot_priority": "high",
      "bot_confidence": "0.95",
      "bot_reason_code": "new_contact",
      "bot_reasoning": "sender is new",
      "bot_is_fallback": "false"
    }
  ]
}
```

## Artifact whitelist

Allowed run artifacts:

- `operator_summary.json`
- `source_diagnostics.json`
- `intake_metadata.json`
- `attachment_extraction.json`
- `normalized_events.json`
- `classified_events.json`
- `rop_review_table.tsv`

Allowed module artifacts:

- `module_result.json`
- `rop_summary_result.json`

UI не отдаёт произвольные файлы из `storage/`.

Для multi-source run допускается aggregate контракт в `source_diagnostics.json` и `intake_metadata.json`:

- `source_diagnostics.json` содержит `aggregate` и `sources[]`;
- `intake_metadata.json` содержит aggregate counts и `sources[]`;
- для single-source compatibility поля верхнего уровня могут оставаться доступными.

## Read-only and security rules

Web Console должен соблюдать:

- no GET mutation;
- no mailbox/CRM/module/capability execution from GET routes;
- no web-triggered `rop run`;
- no raw `.eml` rendering;
- no `message/rfc822` attachment rendering;
- no attachment content rendering;
- path traversal blocked for `run_id`/path-sensitive routes;
- missing/malformed artifacts handled gracefully;
- `Cache-Control: no-store` for HTML/API responses.

Sanitization rules:

- JSON responses strip `raw_eml`, `raw_message`, `attachment_content`, `content`, `content_bytes`, `payload_bytes`;
- attachment entries with `.eml` or `message/rfc822` are removed from rendered payloads;
- dashboard shows only metadata/preview fields.

## Out of scope in current Web Console UI-1/UI-2

UI-1/UI-2 intentionally do not include:

- auth;
- RBAC;
- POST/write actions;
- config editing;
- CRM/mailbox actions;
- React/Reflex frontend;
- SQLAdmin;
- changes to `beeagent-rop`.
