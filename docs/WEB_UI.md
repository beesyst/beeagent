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
    "source_id": "hotline_mailbox",
    "source_type": "mailbox_readonly",
    "status": "ok"
  },
  "intake_metadata": {
    "loaded_item_count": 3,
    "items_max": 20
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

## Artifact whitelist

Allowed run artifacts:

- `operator_summary.json`
- `source_diagnostics.json`
- `intake_metadata.json`
- `normalized_events.json`
- `classified_events.json`
- `rop_review_table.tsv`

Allowed module artifacts:

- `module_result.json`
- `rop_summary_result.json`

UI не отдаёт произвольные файлы из `storage/`.

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

## Out of scope in UI-1

UI-1 intentionally does not include:

- auth;
- RBAC;
- POST/write actions;
- config editing;
- CRM/mailbox actions;
- React/Reflex frontend;
- SQLAdmin;
- changes to `beeagent-rop`.
