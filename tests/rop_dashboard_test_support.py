from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path


def seed_rop_dashboard_run(storage_dir: Path) -> Path:
    rdir = storage_dir / "runs" / "test-dashboard-run"
    rdir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    event_dates = [
        (now - timedelta(days=2)).replace(microsecond=0).isoformat(),
        (now - timedelta(days=1)).replace(microsecond=0).isoformat(),
        now.replace(microsecond=0).isoformat(),
    ]

    normalized = [
        {
            "event_id": "evt-001",
            "source_id": "rop_batch_sample",
            "sender": "client@example.com",
            "subject": "Welding machine inquiry",
            "event_date": event_dates[0],
            "attachments": [],
        },
        {
            "event_id": "evt-002",
            "source_id": "rop_batch_sample",
            "sender": "lead@example.com",
            "subject": "Need pricing",
            "event_date": event_dates[1],
            "attachments": [],
        },
        {
            "event_id": "evt-003",
            "source_id": "hotline_mailbox",
            "sender": "urgent@example.com",
            "subject": "Urgent: welder broken",
            "event_date": event_dates[2],
            "attachments": [
                {
                    "filename": "photo.jpg",
                    "content_type": "image/jpeg",
                    "size_bytes": 50000,
                    "is_refused": True,
                }
            ],
        },
    ]
    (rdir / "normalized_events.json").write_text(
        json.dumps(normalized, indent=2), encoding="utf-8"
    )

    classified = [
        {
            "event_id": "evt-001",
            "case_type": "new_lead",
            "priority": "high",
            "confidence": 0.95,
            "is_fallback": False,
            "reason_code": "new_contact",
            "source_id": "rop_batch_sample",
            "sender": "client@example.com",
            "subject": "Welding machine inquiry",
            "event_date": event_dates[0],
        },
        {
            "event_id": "evt-002",
            "case_type": "existing_deal",
            "priority": "low",
            "confidence": 0.85,
            "is_fallback": False,
            "reason_code": "existing_match",
            "source_id": "rop_batch_sample",
            "sender": "lead@example.com",
            "subject": "Need pricing",
            "event_date": event_dates[1],
        },
        {
            "event_id": "evt-003",
            "case_type": "new_lead",
            "priority": "high",
            "confidence": 0.72,
            "is_fallback": True,
            "reason_code": "fallback_unclear",
            "source_id": "hotline_mailbox",
            "sender": "urgent@example.com",
            "subject": "Urgent: welder broken",
            "event_date": event_dates[2],
        },
    ]
    (rdir / "classified_events.json").write_text(
        json.dumps(classified, indent=2), encoding="utf-8"
    )

    source_diag = {
        "selection_mode": "single_explicit",
        "aggregate": {
            "source_count": 2,
            "loaded_source_count": 2,
            "degraded_source_count": 0,
        },
        "sources": [
            {"source_id": "rop_batch_sample", "client_id": "welding", "status": "ok"},
            {"source_id": "hotline_mailbox", "client_id": "welding", "status": "ok"},
        ],
    }
    (rdir / "source_diagnostics.json").write_text(
        json.dumps(source_diag, indent=2), encoding="utf-8"
    )

    intake = {
        "selection_mode": "single_explicit",
        "source_count": 2,
        "loaded_source_count": 2,
        "degraded_source_count": 0,
        "loaded_item_count": 3,
        "sources": [
            {"source_id": "rop_batch_sample", "client_id": "welding", "status": "ok"},
            {"source_id": "hotline_mailbox", "client_id": "welding", "status": "ok"},
        ],
    }
    (rdir / "intake_metadata.json").write_text(
        json.dumps(intake, indent=2), encoding="utf-8"
    )

    attachment_extraction = {
        "run_id": "test-dashboard-run",
        "status": "ok",
        "aggregate": {
            "event_count": 1,
            "attachment_count": 1,
            "preview_available_count": 0,
            "refused_count": 1,
            "unsupported_count": 1,
            "failed_count": 0,
            "blocked_count": 0,
        },
        "items": [
            {
                "event_id": "evt-003",
                "source_id": "hotline_mailbox",
                "filename": "photo.jpg",
                "content_type": "image/jpeg",
                "size_bytes": 50000,
                "extraction_status": "refused",
                "preview_available": False,
                "is_supported": False,
                "is_refused": True,
                "reason_code": "unsupported_format",
            }
        ],
    }
    (rdir / "attachment_extraction.json").write_text(
        json.dumps(attachment_extraction, indent=2), encoding="utf-8"
    )

    current_state = {
        "run_id": "test-dashboard-run",
        "status": "ok",
        "read_only": True,
        "client_id": "welding",
        "kpi": {
            "events_total": 3,
            "normalized_count": 3,
            "classified_count": 3,
            "high_priority": 2,
            "matched_in_bitrix": 1,
            "lost_in_bitrix": 1,
            "ambiguous_in_bitrix": 0,
            "connector_degraded": 0,
            "unreconciled": 1,
            "attachment_refused": 1,
            "source_degraded": 0,
        },
        "queues": {
            "lost_in_bitrix": [{"event_id": "evt-002", "case_type": "existing_deal"}],
            "needs_review": [
                {"event_id": "evt-001", "case_type": "new_lead"},
                {"event_id": "evt-003", "case_type": "new_lead"},
            ],
            "high_priority": [
                {"event_id": "evt-001", "case_type": "new_lead"},
                {"event_id": "evt-003", "case_type": "new_lead"},
            ],
            "ambiguous": [],
            "matched": [{"event_id": "evt-001", "case_type": "new_lead"}],
            "unreconciled": [{"event_id": "evt-003", "case_type": "new_lead"}],
            "degraded": [],
        },
    }
    (rdir / "rop_current_state.json").write_text(
        json.dumps(current_state, indent=2), encoding="utf-8"
    )

    bitrix_reconciliation = {
        "run_id": "test-dashboard-run",
        "status": "ok",
        "read_only": True,
        "aggregate": {
            "event_count": 3,
            "matched_count": 1,
            "not_found_count": 1,
            "ambiguous_count": 0,
            "duplicate_candidate_count": 0,
            "connector_degraded_count": 0,
        },
        "items": [
            {"event_id": "evt-001", "bitrix_match_status": "matched_lead"},
            {"event_id": "evt-002", "bitrix_match_status": "not_found"},
        ],
    }
    (rdir / "bitrix_reconciliation.json").write_text(
        json.dumps(bitrix_reconciliation, indent=2), encoding="utf-8"
    )

    return rdir
