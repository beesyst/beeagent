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

Источник правды для UI read-model данных:

- existing artifacts в `storage/`
  - `storage/runs/<run_id>/...`
  - `storage/interfaces/modules.json`

UI не хранит отдельный runtime state и не создаёт второй source of truth.

## Runtime foundation

Реализованная основа UI-4:

- **BeeUI** — canonical web layer для BeeAgent;
- FastAPI backend через embedded BeeUI app в `src/beeagent_module/interfaces/ui/`;
- BeeAgent product adapter/read-model/artifact allowlist в `src/beeagent_module/interfaces/ui/`;
- thin CLI entrypoint в `src/beeagent_module/cli/web.py`;
- `config/beeui.yml` — источник правды для UI layout/navigation/pages;
- `config/start.py` вызывает `beeagent_module.cli.web.run_web`;
- legacy `src/beeagent_module/web` заморожен;
- нет auth, POST actions и runtime control endpoints.

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

- `/` — dashboard
- `/health` — health check
- `/runs` — run history
- `/runs/{run_id}` — run detail
- `/rop` — ROP operator dashboard
- `/modules` — module diagnostics

## JSON API routes

Реализованные JSON API routes (через BeeUI product console + custom BeeAgent routes):

- `/api/dashboard`
- `/api/runs`
- `/api/runs/{run_id}`
- `/api/modules`
- `/api/rop/dashboard`

## Artifact JSON routes

Реализованные artifact JSON routes:

- `/runs/{run_id}/artifacts`
- `/runs/{run_id}/artifacts/{artifact_id}`
- `/api/runs/{run_id}/artifacts`
- `/api/runs/{run_id}/artifacts/{artifact_id}`

Правила:

- доступ к артефактам идёт по allowlisted `artifact_id`, а не по произвольному имени файла;
- ответы возвращаются в bounded/redacted JSON envelope;
- произвольные имена файлов и path-like значения отклоняются.

### ROP dashboard contract

`GET /api/rop/dashboard` возвращает текущий source-aware ROP dashboard read-model.

Поддерживаемые query parameters:

- `run_id` — optional explicit run selection; если параметр не передан, используется latest run.

Возвращаемые данные включают:

- `run_id`;
- `summary`;
- `source_diagnostics`;
- `intake_metadata`;
- `sources[]`;
- `classified_count`;
- `case_type_counts`;
- `priority_counts`;
- `fallback_count`.

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

`GET /runs/{run_id}/artifacts/{artifact_id}`

```json
{
  "ok": true,
  "read_only": true,
  "data": {
    "artifact_id": "operator_summary_json",
    "run_id": "live-review-2026-05-15",
    "content": "{\n  \"status\": \"ok\"\n}",
    "content_type": "application/json"
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

| ID | Relative path |
|---|---|
| `run_json` | `run.json` |
| `operator_summary_json` | `operator_summary.json` |
| `source_diagnostics_json` | `source_diagnostics.json` |
| `intake_metadata_json` | `intake_metadata.json` |
| `normalized_events_json` | `normalized_events.json` |
| `classified_events_json` | `classified_events.json` |
| `attachment_extraction_json` | `attachment_extraction.json` |
| `rop_review_table_tsv` | `rop_review_table.tsv` |
| `module_result_json` | `module-beeagent-rop/module_result.json` |
| `rop_summary_result_json` | `module-beeagent-rop/rop_summary_result.json` |
| `lead_classification_result_json` | `module-beeagent-rop/lead_classification_result.json` |
| `steps_json` | `steps.json` |

UI не отдаёт произвольные файлы из `storage/`. `artifact_id` маппится на фиксированный allowlisted relative path.

Отклоняются:

- raw `.eml`
- raw attachments
- arbitrary files
- logs with secrets
- env/config secrets
- mailbox password values
- provider tokens
- mailbox source content beyond normalized/sanitized artifacts

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
- cache-control требования должны соблюдаться на route layer, но их фактический enforcement нужно подтверждать отдельно.

Sanitization rules:

- JSON responses strip `raw_eml`, `raw_message`, `attachment_content`, `content`, `content_bytes`, `payload_bytes`;
- attachment entries with `.eml` or `message/rfc822` are removed from rendered payloads;
- dashboard shows only metadata/preview fields.

## Out of scope in UI-4

UI-4 intentionally does not include:

- auth;
- RBAC;
- POST/write actions;
- config editing;
- CRM/mailbox actions;
- web-triggered ROP run;
- attachment parsing/OCR;
- full attachment-aware dashboard;
- React/Reflex frontend;
- SQLAdmin;
- changes to `beeagent-rop`;
- stable API v1 freeze;
- standalone BeeUI service;
- removal of legacy frozen `src/beeagent_module/web`.
