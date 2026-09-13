from __future__ import annotations

import json
import logging
from hashlib import sha256
from pathlib import Path
from typing import Any
from fastapi.testclient import TestClient

def _logger() -> logging.Logger:
    logger = logging.getLogger("test_beeui_console")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger

def _make_storage(tmp_path: Path) -> Path:
    storage_dir = tmp_path / "storage"
    (storage_dir / "runs").mkdir(parents=True)
    (storage_dir / "interfaces").mkdir(parents=True)
    return storage_dir

def _write_run_artifacts(storage_dir: Path, run_id: str) -> Path:
    run_dir = storage_dir / "runs" / run_id
    module_dir = run_dir / "module-beeagent-rop"
    module_dir.mkdir(parents=True)

    operator_summary = {
        "run_id": run_id,
        "status": "ok",
        "summary": "batch completed",
    }
    source_diagnostics = {
        "selection_mode": "all_enabled",
        "status": "ok",
        "aggregate": {
            "source_count": 1,
            "loaded_source_count": 1,
            "degraded_source_count": 0,
        },
        "sources": [
            {
                "source_id": "hotline_mailbox",
                "source_type": "mailbox_readonly",
                "source_role": "technical_aggregator",
                "source_display_name": "Welding Hotline mailbox",
                "client_id": "welding",
                "status": "ok",
            }
        ],
    }
    intake_metadata = {
        "source_id": "hotline_mailbox",
        "loaded_item_count": 3,
    }
    normalized_events = [
        {"event_id": "evt-1", "sender": "test@example.com", "subject": "Test"},
    ]
    classified_events = [
        {
            "event_id": "evt-1",
            "case_type": "new_lead",
            "priority": "high",
            "confidence": 0.95,
            "is_fallback": False,
        }
    ]

    (run_dir / "operator_summary.json").write_text(
        json.dumps(operator_summary), encoding="utf-8"
    )
    (run_dir / "source_diagnostics.json").write_text(
        json.dumps(source_diagnostics), encoding="utf-8"
    )
    (run_dir / "intake_metadata.json").write_text(
        json.dumps(intake_metadata), encoding="utf-8"
    )
    (run_dir / "normalized_events.json").write_text(
        json.dumps(normalized_events), encoding="utf-8"
    )
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified_events), encoding="utf-8"
    )
    (run_dir / "rop_review_table.tsv").write_text(
        "event_id\tbot_case_type\nevt-1\tnew_lead\n", encoding="utf-8"
    )
    (module_dir / "module_result.json").write_text("{}", encoding="utf-8")
    (module_dir / "rop_summary_result.json").write_text("{}", encoding="utf-8")

    return run_dir

def _write_rop_event_detail_artifacts(storage_dir: Path, run_id: str) -> Path:
    run_dir = _write_run_artifacts(storage_dir, run_id)
    normalized_events = [
        {
            "event_id": "evt-1",
            "source_id": "hotline_mailbox",
            "source_type": "mailbox_readonly",
            "source_role": "technical_aggregator",
            "source_display_name": "Welding Hotline mailbox",
            "client_id": "welding",
            "sender": "client@example.com",
            "subject": "Need welding quote",
            "body_preview": "Please send pricing for welding equipment.",
            "body_preview_chars": 42,
            "body_preview_truncated": False,
            "body_preview_source": "existing",
            "attachments": [
                {
                    "filename": "brief.pdf",
                    "content_type": "application/pdf",
                    "size_bytes": 128,
                    "content": "RAW-ATTACHMENT-CONTENT",
                }
            ],
            "raw_eml": "RAW-EML-CONTENT",
        }
    ]
    classified_events = [
        {
            "event_id": "evt-1",
            "source_id": "hotline_mailbox",
            "client_id": "welding",
            "sender": "client@example.com",
            "subject": "Need welding quote",
            "case_type": "new_lead",
            "priority": "high",
            "confidence": 0.95,
            "reason_code": "new_contact",
            "recommended_queue": "high_priority",
            "correct_action": "review",
            "should_rop_see": True,
            "is_fallback": False,
        }
    ]
    current_state = {
        "run_id": run_id,
        "status": "ok",
        "read_only": True,
        "queues": {
            "needs_review": [
                {
                    "event_id": "evt-1",
                    "sender": "client@example.com",
                    "subject": "Need welding quote",
                    "case_type": "new_lead",
                    "priority": "high",
                    "source_id": "hotline_mailbox",
                    "source_display_name": "Welding Hotline mailbox",
                    "recommended_next_step": "Manual review",
                }
            ]
        },
    }
    (run_dir / "normalized_events.json").write_text(
        json.dumps(normalized_events), encoding="utf-8"
    )
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified_events), encoding="utf-8"
    )
    (run_dir / "rop_current_state.json").write_text(
        json.dumps(current_state), encoding="utf-8"
    )
    return run_dir

def _build_settings() -> dict:
    return {
        "app": {"name": "BeeAgent", "env": "test"},
        "web": {"host": "127.0.0.1", "port": 18080, "open_browser": False},
        "logging": {"clear_logs": True, "utc": True, "level": "INFO"},
        "rop": {
            "email_preview": {
                "body_chars_max": 4000,
            },
            "dashboard": {
                "default_period": "7d",
                "periods": ["today", "yesterday", "7d", "30d", "90d", "365d", "all"],
                "leaderboard": {"plan_lead": 20},
            },
            "sources_path": "config/rop/sources.yml",
            "mailbox_poll": {
                "enabled": False,
                "source_id": "hotline_mailbox",
                "sources_all": True,
            },
        },
    }

def _write_rop_web_projection(
    storage_dir: Path,
    settings: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> None:
    from beeagent_module.cases.rop_dashboard import (
        build_rop_web_projection,
        write_rop_web_projection,
    )

    cfg = settings or _build_settings()
    projection = build_rop_web_projection(
        storage_dir=storage_dir,
        periods=cfg["rop"]["dashboard"]["periods"],
        logger=_logger(),
        plan_lead=cfg["rop"]["dashboard"]["leaderboard"]["plan_lead"],
        run_id=run_id,
    )
    write_rop_web_projection(storage_dir, projection, _logger())

def _client(storage_dir: Path, settings: dict[str, Any] | None = None) -> TestClient:
    from beeagent_module.interfaces.ui.app import build_beeui_app

    resolved_settings = settings or _build_settings()
    if not (storage_dir / "interfaces" / "rop_web_projection.json").exists():
        _write_rop_web_projection(storage_dir, resolved_settings)
    app = build_beeui_app(
        settings=resolved_settings,
        logger=_logger(),
        storage_dir=storage_dir,
    )
    return TestClient(app)

def _write_rich_rop_run(storage_dir: Path, run_id: str) -> Path:
    run_dir = storage_dir / "runs" / run_id
    module_dir = run_dir / "module-beeagent-rop"
    module_dir.mkdir(parents=True)

    operator_summary = {
        "run_id": run_id,
        "status": "ok",
        "summary": "batch completed with results",
    }
    source_diagnostics = {
        "selection_mode": "all_enabled",
        "status": "ok",
        "aggregate": {
            "source_count": 2,
            "loaded_source_count": 2,
            "degraded_source_count": 1,
        },
        "sources": [
            {
                "source_id": "hotline_mailbox",
                "source_type": "mailbox_readonly",
                "source_role": "technical_aggregator",
                "source_display_name": "Welding Hotline mailbox",
                "client_id": "welding",
                "authority": "read_only",
                "status": "ok",
                "items_max": 20,
                "fetched_count": 5,
                "loaded_count": 5,
                "malformed_count": 0,
            },
            {
                "source_id": "rop_batch_sample",
                "source_type": "json_batch",
                "source_role": "batch_sample",
                "source_display_name": "ROP Batch Sample",
                "client_id": "welding",
                "authority": "read_only",
                "status": "degraded",
                "reason": "partial_load",
                "items_max": 100,
                "fetched_count": 10,
                "loaded_count": 8,
                "malformed_count": 2,
            },
        ],
    }
    intake_metadata = {
        "loaded_item_count": 13,
        "source_count": 2,
        "fetched_count": 15,
        "sources": [
            {
                "source_id": "hotline_mailbox",
                "loaded_count": 5,
                "fetched_count": 5,
                "malformed_count": 0,
                "status": "ok",
            },
            {
                "source_id": "rop_batch_sample",
                "loaded_count": 8,
                "fetched_count": 10,
                "malformed_count": 2,
                "status": "degraded",
            },
        ],
    }
    normalized_events = [
        {
            "event_id": "evt-001",
            "source_id": "hotline_mailbox",
            "sender": "lead@example.com",
            "subject": "Welding equipment inquiry",
            "attachment_count": 2,
        },
        {
            "event_id": "evt-002",
            "source_id": "hotline_mailbox",
            "sender": "client@workshop.kz",
            "subject": "Re: Order #123",
            "attachment_count": 0,
        },
        {
            "event_id": "evt-003",
            "source_id": "rop_batch_sample",
            "sender": "partner@supply.kz",
            "subject": "Price list",
            "attachment_count": 1,
        },
        {
            "event_id": "evt-004",
            "source_id": "rop_batch_sample",
            "sender": "noreply@mailer.com",
            "subject": "Special promotion",
            "attachment_count": 0,
        },
        {
            "event_id": "evt-005",
            "source_id": "hotline_mailbox",
            "sender": "urgent@client.kz",
            "subject": "URGENT: Equipment failure",
            "attachment_count": 3,
        },
    ]
    classified_events = [
        {
            "event_id": "evt-001",
            "source_id": "hotline_mailbox",
            "case_type": "new_lead",
            "priority": "high",
            "confidence": 0.95,
            "is_fallback": False,
            "reason_code": "new_contact_no_existing_lead",
            "sender": "lead@example.com",
        },
        {
            "event_id": "evt-002",
            "source_id": "hotline_mailbox",
            "case_type": "existing_deal",
            "priority": "medium",
            "confidence": 0.88,
            "is_fallback": False,
            "reason_code": "existing_deal_followup",
        },
        {
            "event_id": "evt-003",
            "source_id": "rop_batch_sample",
            "case_type": "new_lead",
            "priority": "medium",
            "confidence": 0.45,
            "is_fallback": True,
            "reason_code": "low_confidence_fallback",
        },
        {
            "event_id": "evt-004",
            "source_id": "rop_batch_sample",
            "case_type": "irrelevant",
            "priority": "low",
            "confidence": 0.91,
            "is_fallback": False,
            "reason_code": "promotional_content",
        },
        {
            "event_id": "evt-005",
            "source_id": "hotline_mailbox",
            "case_type": "new_lead",
            "priority": "high",
            "confidence": 0.97,
            "is_fallback": False,
            "reason_code": "urgent_inquiry",
        },
    ]
    attachment_extraction = {
        "run_id": run_id,
        "status": "ok",
        "aggregate": {
            "event_count": 3,
            "attachment_count": 6,
            "preview_available_count": 3,
            "metadata_only_count": 0,
            "refused_count": 2,
            "unsupported_count": 1,
            "failed_count": 0,
        },
        "items": [
            {
                "filename": "doc1.txt",
                "extraction_status": "preview",
                "preview_available": True,
                "is_refused": False,
            },
            {
                "filename": "doc2.txt",
                "extraction_status": "preview",
                "preview_available": True,
                "is_refused": False,
            },
            {
                "filename": "doc3.txt",
                "extraction_status": "preview",
                "preview_available": True,
                "is_refused": False,
            },
            {
                "filename": "mail.eml",
                "extraction_status": "refused",
                "preview_available": False,
                "is_refused": True,
            },
            {
                "filename": "scan.pdf",
                "extraction_status": "refused",
                "preview_available": False,
                "is_refused": True,
            },
            {
                "filename": "image.png",
                "extraction_status": "unsupported",
                "preview_available": False,
                "is_refused": False,
            },
        ],
    }

    (run_dir / "operator_summary.json").write_text(
        json.dumps(operator_summary), encoding="utf-8"
    )
    (run_dir / "source_diagnostics.json").write_text(
        json.dumps(source_diagnostics), encoding="utf-8"
    )
    (run_dir / "intake_metadata.json").write_text(
        json.dumps(intake_metadata), encoding="utf-8"
    )
    (run_dir / "normalized_events.json").write_text(
        json.dumps(normalized_events), encoding="utf-8"
    )
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified_events), encoding="utf-8"
    )
    (run_dir / "attachment_extraction.json").write_text(
        json.dumps(attachment_extraction), encoding="utf-8"
    )
    (run_dir / "rop_review_table.tsv").write_text(
        "event_id\tbot_case_type\nevt-001\tnew_lead\n", encoding="utf-8"
    )
    (module_dir / "module_result.json").write_text("{}", encoding="utf-8")
    (module_dir / "rop_summary_result.json").write_text("{}", encoding="utf-8")
    (run_dir / "mailbox_selection.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "strategy": "latest_n_by_internaldate_desc",
                "sources": [],
                "warnings": [],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "mail_thread_index.json").write_text(
        json.dumps({"threads": [], "warnings": []}), encoding="utf-8"
    )
    (run_dir / "mail_thread_context.json").write_text(
        json.dumps({"contexts": [], "warnings": []}), encoding="utf-8"
    )
    (run_dir / "rop_ai_assist_requests.json").write_text(
        json.dumps({"run_id": run_id, "counters": {}, "requests": []}), encoding="utf-8"
    )
    (run_dir / "rop_ai_assist_decisions.json").write_text(
        json.dumps({"run_id": run_id, "counters": {}, "decisions": []}),
        encoding="utf-8",
    )
    (run_dir / "rop_ai_assist_results.json").write_text(
        json.dumps({"run_id": run_id, "counters": {}, "results": []}), encoding="utf-8"
    )
    return run_dir

def _build_scoped_auth_settings() -> dict:
    settings = _build_settings()
    settings["web"]["auth"] = {
        "enabled": True,
        "mode": "beeui_session",
        "session_secret_env": "BEEAGENT_WEB_SESSION_SECRET",
        "principals": [
            {
                "id": "admin_1",
                "username": "admin1",
                "role": "admin",
                "scopes": ["*"],
                "token_env": "BEEAGENT_WEB_ADMIN1_TOKEN",
            },
            {
                "id": "admin_2",
                "username": "admin2",
                "role": "admin",
                "scopes": ["*"],
                "token_env": "BEEAGENT_WEB_ADMIN2_TOKEN",
            },
            {
                "id": "rop_viewer_1",
                "username": "ropviewer",
                "role": "viewer",
                "scopes": ["rop"],
                "token_env": "BEEAGENT_WEB_ROPVIEWER_TOKEN",
            },
            {
                "id": "rop",
                "username": "rop",
                "role": "operator",
                "scopes": [
                    "rop",
                    "rop.sources.write",
                    "rop.blacklist.write",
                    "rop.routing.write",
                    "rop.users.write",
                    "rop.settings.write",
                    "rop.crm.write",
                ],
                "token_env": "BEEAGENT_WEB_ROP_TOKEN",
            },
        ],
    }
    return settings

def _scoped_auth_client(storage_dir: Path) -> TestClient:
    from beeagent_module.interfaces.ui.app import build_beeui_app

    settings = _build_scoped_auth_settings()
    _write_rop_web_projection(storage_dir, settings)
    app = build_beeui_app(
        settings=settings,
        logger=_logger(),
        storage_dir=storage_dir,
    )
    return TestClient(app)

def _seed_download_attachment(storage_dir: Path, run_id: str) -> dict[str, Any]:
    content = b"%PDF-1.4 download body bytes"
    blob_id = "att-" + sha256(content).hexdigest()[:24]
    run_dir = storage_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "classified_events.json").write_text(
        json.dumps([{"event_id": "evt-1"}]), encoding="utf-8"
    )
    store_dir = storage_dir / "attachments" / run_id
    store_dir.mkdir(parents=True, exist_ok=True)
    (store_dir / f"{blob_id}.bin").write_bytes(content)
    manifest = {
        "run_id": run_id,
        "version": 1,
        "status": "ok",
        "policy": {},
        "aggregate": {"attachment_count": 1, "stored_count": 1},
        "items": [
            {
                "attachment_id": "evt-1-att-0",
                "event_id": "evt-1",
                "event_instance_id": "event-000001",
                "blob_id": blob_id,
                "filename": "brief.pdf",
                "content_type": "application/pdf",
                "size_bytes": len(content),
                "sha256": sha256(content).hexdigest(),
                "storage_status": "stored",
            }
        ],
    }
    (store_dir / "attachment_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    return manifest
