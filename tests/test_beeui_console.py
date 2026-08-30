from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from beeui_module.adapters.envelopes import AdapterErrorResult
from fastapi.testclient import TestClient

from beeagent_module.interfaces.ui.read_model import (
    build_rop_dashboard_read_model,
    build_rop_page_layout,
    build_run_detail,
)


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


def _find_section_items(page: dict[str, Any], title: str) -> list[dict[str, Any]]:
    for sec in page.get("sections", []):
        if sec.get("title") == title:
            return sec.get("items", [])
    return []


def _item_by_label(items: list[dict[str, Any]], label: str) -> dict[str, Any]:
    for item in items:
        if item.get("label") == label:
            return item
    return {}


def _write_modules_artifact(storage_dir: Path) -> None:
    payload = {
        "registry": [
            {
                "id": "beeagent-rop",
                "package": "beeagent_rop",
                "entry": "RopModule",
                "state": "loaded",
                "error": "",
            }
        ]
    }
    (storage_dir / "interfaces" / "modules.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _write_modules_artifact_with_html(storage_dir: Path) -> None:
    payload = {
        "registry": [
            {
                "id": "<script>alert('id')</script>",
                "package": "pkg<script>alert('pkg')</script>",
                "entry": "<b>Entry</b>",
                "state": "<script>alert('state')</script>",
                "error": "<img src=x onerror=alert('err')>",
            }
        ]
    }
    (storage_dir / "interfaces" / "modules.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


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


def _write_non_rop_run(storage_dir: Path, run_id: str) -> Path:
    run_dir = storage_dir / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "operator_summary.json").write_text(
        json.dumps({"run_id": run_id, "status": "ok", "summary": "non-rop run"}),
        encoding="utf-8",
    )
    (run_dir / "classified_events.json").write_text(
        json.dumps({"not": "a list"}), encoding="utf-8"
    )
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


def _write_bitrix_current_state_artifacts(run_dir: Path, run_id: str) -> None:
    current_state = {
        "run_id": run_id,
        "status": "ok",
        "read_only": True,
        "kpi": {
            "matched_in_bitrix": 1,
            "lost_in_bitrix": 1,
            "ambiguous_in_bitrix": 1,
            "connector_degraded": 1,
            "unreconciled": 1,
        },
        "queues": {
            "lost_in_bitrix": [
                {
                    "event_id": "evt-lost",
                    "case_type": "new_lead",
                    "priority": "high",
                    "bitrix_status": "not_found",
                }
            ],
            "ambiguous": [
                {
                    "event_id": "evt-amb",
                    "case_type": "new_lead",
                    "priority": "medium",
                    "bitrix_status": "ambiguous",
                }
            ],
            "degraded": [
                {
                    "event_id": "evt-degraded",
                    "case_type": "new_lead",
                    "priority": "medium",
                    "bitrix_status": "connector_degraded",
                }
            ],
            "unreconciled": [
                {
                    "event_id": "evt-unreconciled",
                    "case_type": "new_lead",
                    "priority": "low",
                }
            ],
            "matched": [
                {
                    "event_id": "evt-matched",
                    "case_type": "existing_deal",
                    "priority": "low",
                    "bitrix_status": "matched_deal",
                }
            ],
        },
    }
    reconciliation = {
        "run_id": run_id,
        "status": "ok",
        "read_only": True,
        "aggregate": {
            "event_count": 5,
            "matched_count": 1,
            "not_found_count": 1,
            "ambiguous_count": 1,
            "connector_degraded_count": 1,
        },
        "items": [],
    }
    (run_dir / "rop_current_state.json").write_text(
        json.dumps(current_state), encoding="utf-8"
    )
    (run_dir / "bitrix_reconciliation.json").write_text(
        json.dumps(reconciliation), encoding="utf-8"
    )


def _write_run_artifacts_with_html(storage_dir: Path, run_id: str) -> Path:
    run_dir = _write_run_artifacts(storage_dir, run_id)

    source_diagnostics = json.loads(
        (run_dir / "source_diagnostics.json").read_text(encoding="utf-8")
    )
    source_diagnostics["sources"] = [
        {
            "source_id": "<script>alert('sid')</script>",
            "source_type": "mailbox_readonly",
            "source_role": "technical_aggregator",
            "source_display_name": "<script>alert('display')</script>",
            "client_id": "welding",
            "status": "<script>alert('status')</script>",
        }
    ]
    (run_dir / "source_diagnostics.json").write_text(
        json.dumps(source_diagnostics), encoding="utf-8"
    )

    return run_dir


def _write_malformed_json_run(storage_dir: Path, run_id: str) -> Path:
    run_dir = storage_dir / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "operator_summary.json").write_text(
        "{invalid json content}", encoding="utf-8"
    )
    return run_dir


def _write_secret_stub_run(storage_dir: Path, run_id: str) -> Path:
    run_dir = storage_dir / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "operator_summary.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": "ok",
                "ROP_MAILBOX_PASSWORD": "should-not-leak",
            }
        ),
        encoding="utf-8",
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
            },
            "sources": [
                {
                    "source_id": "test_source",
                    "source_type": "json_batch",
                    "source_role": "test",
                    "client_id": "test",
                    "display_name": "Test Source",
                    "enabled": True,
                    "authority": "read_only",
                    "items_max": 10,
                }
            ],
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


def test_beeui_app_builds(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.app import build_beeui_app

    app = build_beeui_app(
        settings=_build_settings(),
        logger=_logger(),
        storage_dir=_make_storage(tmp_path),
    )
    assert app is not None
    assert app.title == "BeeUI"


def test_start_web_dispatch_imports() -> None:
    from beeagent_module.cli.web import create_web_parser, run_routes, run_web

    assert callable(run_web)
    assert callable(run_routes)
    assert callable(create_web_parser)


def test_cli_defaults_from_config() -> None:
    from beeagent_module.cli.web import create_web_parser

    parser = create_web_parser()
    args = parser.parse_args([])
    assert args.host is None
    assert args.port is None
    assert args.no_open is False


def test_cli_host_override() -> None:
    from beeagent_module.cli.web import create_web_parser

    parser = create_web_parser()
    args = parser.parse_args(["--host", "0.0.0.0"])
    assert args.host == "0.0.0.0"


def test_cli_port_override() -> None:
    from beeagent_module.cli.web import create_web_parser

    parser = create_web_parser()
    args = parser.parse_args(["--port", "9090"])
    assert args.port == 9090


def test_cli_no_open_flag() -> None:
    from beeagent_module.cli.web import create_web_parser

    parser = create_web_parser()
    args = parser.parse_args(["--no-open"])
    assert args.no_open is True


def test_home_route(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))
    response = client.get("/")
    assert response.status_code == 200


def test_health_route(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_runs_route_empty(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))
    response = client.get("/runs")
    assert response.status_code == 200


def test_runs_route_with_data(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-test-001")
    client = _client(storage_dir)
    response = client.get("/runs")
    assert response.status_code == 200
    assert "run-test-001" in response.text
    assert "No runs available." not in response.text


def test_run_route(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-valid-001")
    client = _client(storage_dir)
    response = client.get("/runs/run-valid-001")
    assert response.status_code == 200


def test_run_route_invalid_run_id(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))
    response = client.get("/runs/../etc/passwd")
    assert response.status_code in (400, 404)


def test_read_model_run_detail_rejects_path_traversal(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)

    data = build_run_detail(storage_dir, "../../outside")

    assert data["error"] == "invalid_run_id"


def test_rop_dashboard_read_model_rejects_path_traversal(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)

    data = build_rop_dashboard_read_model(storage_dir, "../../outside")

    assert data["error"] == "invalid_run_id"


def test_rop_route(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-rop-001")
    client = _client(storage_dir)
    response = client.get("/rop")
    assert response.status_code == 200


def test_rop_route_escapes_html(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts_with_html(storage_dir, "run-rop-html")
    client = _client(storage_dir)
    response = client.get("/rop")
    assert response.status_code == 200
    assert "<script>alert" not in response.text
    assert "alert(1)" not in response.text


def test_rop_event_detail_html_route_returns_html(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-rop-detail-html")
    client = _client(storage_dir)

    response = client.get("/rop/events/evt-1?run_id=run-rop-detail-html")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Event Detail" in response.text
    assert "Need welding quote" in response.text
    assert "client@example.com" in response.text
    assert "Please send pricing for welding equipment." in response.text
    assert "RAW-EML-CONTENT" not in response.text
    assert "RAW-ATTACHMENT-CONTENT" not in response.text


def test_api_rop_event_detail_route_remains_json(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-rop-detail-api")
    client = _client(storage_dir)

    response = client.get("/api/rop/events/evt-1?run_id=run-rop-detail-api")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    data = response.json()
    assert data["data"]["message"]["subject"] == "Need welding quote"


def test_rop_event_detail_synthetic_reason_contract_is_read_only(
    tmp_path: Path,
) -> None:
    from beeagent_module.core.rop_final_decision import build_final_decisions
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-reason-contract")
    classified_path = run_dir / "classified_events.json"
    classified = json.loads(classified_path.read_text(encoding="utf-8"))
    classified[0]["reason_code"] = "new_lead_request_signal"
    classified_path.write_text(json.dumps(classified), encoding="utf-8")
    raw_reason = "<script>provider_reason()</script>"
    adjudicator = {
        "results": [
            {
                "event_id": "evt-1",
                "ai_used": True,
                "ai_status": "manual_review_degrade",
                "ai_confidence": 0.9,
                "ai_reason": raw_reason,
                "ai_reason_code": "conflicting_business_signals",
                "ai_evidence_codes": [
                    "low_signal",
                    "not_allowed",
                    7,
                    "supplier_outreach",
                    "marketing_conflict",
                    "spam_rfq_conflict",
                ],
                "merge_reason": "ai_output_conflict_manual_review",
                "final_case_type": "new_lead",
                "final_recommended_queue": "manual_review",
                "final_correct_action": "manual_review",
            }
        ]
    }
    (run_dir / "rop_ai_adjudicator_results.json").write_text(
        json.dumps(adjudicator), encoding="utf-8"
    )
    final_decisions = build_final_decisions(classified, adjudicator)
    (run_dir / "rop_final_decisions.json").write_text(
        json.dumps(final_decisions), encoding="utf-8"
    )
    legacy_dir = _write_rop_event_detail_artifacts(storage_dir, "run-reason-legacy")
    (legacy_dir / "rop_ai_adjudicator_results.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "event_id": "evt-1",
                        "ai_status": "manual_review_degrade",
                        "ai_reason": "legacy raw reason",
                        "merge_reason": "ai_output_conflict_manual_review",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    legacy_classified = json.loads(
        (legacy_dir / "classified_events.json").read_text(encoding="utf-8")
    )
    legacy_adjudicator = json.loads(
        (legacy_dir / "rop_ai_adjudicator_results.json").read_text(encoding="utf-8")
    )
    legacy_final = build_final_decisions(legacy_classified, legacy_adjudicator)
    legacy_final["events"][0].pop("attention_reason_code")
    legacy_final["events"][0].pop("attention_evidence_codes")
    (legacy_dir / "rop_final_decisions.json").write_text(
        json.dumps(legacy_final), encoding="utf-8"
    )
    unknown_dir = _write_rop_event_detail_artifacts(storage_dir, "run-reason-unknown")
    (unknown_dir / "rop_ai_adjudicator_results.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "event_id": "evt-1",
                        "ai_reason_code": "<script>unknown()</script>",
                        "ai_evidence_codes": ["<script>unknown()</script>"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    unknown_final = {
        "summary": {
            "total_events": 1,
            "decision_source_counts": {"legacy": 1},
            "attention_count": 1,
        },
        "events": [
            {
                "event_id": "evt-1",
                "final_case_type": "new_lead",
                "final_case_subtype": None,
                "final_queue": "manual_review",
                "final_action": "manual_review",
                "final_decision_source": "legacy",
                "final_confidence": 0.0,
                "needs_attention": True,
                "attention_reason": "legacy raw attention",
                "attention_reason_code": "unknown_final_attention_code",
                "automation_allowed": False,
                "bitrix_write_allowed": False,
            }
        ],
    }
    (unknown_dir / "rop_final_decisions.json").write_text(
        json.dumps(unknown_final), encoding="utf-8"
    )
    legacy_status_dir = _write_rop_event_detail_artifacts(
        storage_dir,
        "run-reason-legacy-status",
    )
    legacy_status_adjudicator = {
        "results": [
            {
                "event_id": "evt-1",
                "ai_status": "manual_review_degrade",
                "ai_reason": "legacy status raw reason",
            }
        ]
    }
    (legacy_status_dir / "rop_ai_adjudicator_results.json").write_text(
        json.dumps(legacy_status_adjudicator), encoding="utf-8"
    )
    legacy_status_classified = json.loads(
        (legacy_status_dir / "classified_events.json").read_text(encoding="utf-8")
    )
    legacy_status_final = build_final_decisions(
        legacy_status_classified,
        legacy_status_adjudicator,
    )
    legacy_status_final["events"][0].pop("attention_reason_code")
    legacy_status_final["events"][0].pop("attention_evidence_codes")
    (legacy_status_dir / "rop_final_decisions.json").write_text(
        json.dumps(legacy_status_final), encoding="utf-8"
    )
    paths = [
        run_dir / "normalized_events.json",
        run_dir / "classified_events.json",
        run_dir / "rop_ai_adjudicator_results.json",
        run_dir / "rop_final_decisions.json",
        legacy_dir / "rop_ai_adjudicator_results.json",
        legacy_dir / "rop_final_decisions.json",
        unknown_dir / "rop_ai_adjudicator_results.json",
        unknown_dir / "rop_final_decisions.json",
        legacy_status_dir / "rop_ai_adjudicator_results.json",
        legacy_status_dir / "rop_final_decisions.json",
    ]
    before = {
        path: (sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        for path in paths
    }
    client = _client(storage_dir)

    ru_html = client.get("/rop/events/evt-1?run_id=run-reason-contract&lang=ru")
    en_html = client.get("/rop/events/evt-1?run_id=run-reason-contract&lang=en")
    invalid_html = client.get("/rop/events/evt-1?run_id=run-reason-contract&lang=bad")
    ru_api = client.get("/api/rop/events/evt-1?run_id=run-reason-contract&lang=ru")
    legacy_api = client.get("/api/rop/events/evt-1?run_id=run-reason-legacy&lang=ru")
    legacy_api_en = client.get("/api/rop/events/evt-1?run_id=run-reason-legacy&lang=en")
    unknown_api = client.get("/api/rop/events/evt-1?run_id=run-reason-unknown&lang=ru")
    unknown_api_en = client.get(
        "/api/rop/events/evt-1?run_id=run-reason-unknown&lang=en"
    )
    unknown_html_ru = client.get("/rop/events/evt-1?run_id=run-reason-unknown&lang=ru")
    unknown_html_en = client.get("/rop/events/evt-1?run_id=run-reason-unknown&lang=en")
    legacy_status_ru = client.get(
        "/api/rop/events/evt-1?run_id=run-reason-legacy-status&lang=ru"
    )
    legacy_status_en = client.get(
        "/api/rop/events/evt-1?run_id=run-reason-legacy-status&lang=en"
    )
    page_ru = build_rop_event_detail_page_model(
        storage_dir, "run-reason-contract", "evt-1", lang="ru"
    )
    page_en = build_rop_event_detail_page_model(
        storage_dir, "run-reason-contract", "evt-1", lang="en"
    )
    legacy_page_ru = build_rop_event_detail_page_model(
        storage_dir, "run-reason-legacy", "evt-1", lang="ru"
    )
    legacy_page_en = build_rop_event_detail_page_model(
        storage_dir, "run-reason-legacy", "evt-1", lang="en"
    )

    assert ru_html.status_code == 200
    assert en_html.status_code == 200
    assert invalid_html.status_code == 200
    assert "AI арбитр" in ru_html.text
    assert "AI adjudicator reason" in en_html.text
    assert "AI adjudicator reason" in invalid_html.text
    assert (
        _item_by_label(_find_section_items(page_ru, "Классификация"), "Причина")[
            "value"
        ]
        == "Новый лид: обнаружен сигнал запроса или RFQ"
    )
    assert (
        _item_by_label(_find_section_items(page_ru, "AI арбитр"), "Причина")["value"]
        == "Обнаружены противоречивые бизнес-сигналы"
    )
    assert (
        _item_by_label(
            _find_section_items(page_ru, "Итоговое решение"), "Причина внимания"
        )["value"]
        == "Результат ИИ противоречит сигналам; требуется ручная проверка"
    )
    assert (
        _item_by_label(_find_section_items(page_en, "Classification"), "Reason")[
            "value"
        ]
        == "New lead: request or RFQ signal detected"
    )
    assert raw_reason not in ru_html.text
    assert "&lt;script&gt;provider_reason()&lt;/script&gt;" in ru_html.text
    data = ru_api.json()["data"]
    assert data["ai_adjudicator"]["ai_adjudicator_reason"] == raw_reason
    assert (
        data["final_decision"]["attention_reason"] == "ai_output_conflict_manual_review"
    )
    assert data["final_decision"]["attention_reason_code"] == (
        "ai_output_conflict_manual_review"
    )
    assert [
        item["code"] for item in data["ai_adjudicator"]["ai_adjudicator_evidence_codes"]
    ] == [
        "low_signal",
        "supplier_outreach",
        "marketing_conflict",
    ]
    assert not any(
        "attention reason code" in warning.lower()
        or "код причины внимания" in warning.lower()
        for warning in data["warnings"]
    )
    assert len(data["ai_adjudicator"]["ai_adjudicator_evidence_codes"]) <= 5
    assert "ai_evidence_codes exceeded maximum; truncated" in data["warnings"]
    assert "unknown ai evidence code ignored" in data["warnings"]
    assert "not_allowed" not in data["warnings"]
    assert any(
        "legacy ai_reason_code missing" in warning
        for warning in legacy_api.json()["data"]["warnings"]
    )
    assert (
        "Старый формат итогового решения: код причины внимания отсутствует. "
        "Показано совместимое объяснение; данные не изменялись."
    ) in legacy_api.json()["data"]["warnings"]
    legacy_data = legacy_api.json()["data"]
    assert legacy_data["final_decision"]["attention_reason"] == (
        "ai_output_conflict_manual_review"
    )
    assert legacy_data["final_decision"]["attention_reason_display"] == (
        "Результат ИИ противоречит сигналам; требуется ручная проверка"
    )
    assert (
        legacy_api_en.json()["data"]["final_decision"]["attention_reason_display"]
        == "AI output conflicted with signals; manual review required"
    )
    assert (
        "Legacy final-decision format: the attention reason code is missing. "
        "A compatible explanation is shown; no data was modified."
    ) in legacy_api_en.json()["data"]["warnings"]
    assert (
        _item_by_label(
            _find_section_items(legacy_page_ru, "Итоговое решение"),
            "Причина внимания",
        )["value"]
        == "Результат ИИ противоречит сигналам; требуется ручная проверка"
    )
    assert (
        _item_by_label(
            _find_section_items(legacy_page_en, "Final decision"), "Attention reason"
        )["value"]
        == "AI output conflicted with signals; manual review required"
    )
    assert any(
        "unknown ai_reason_code" in warning
        for warning in unknown_api.json()["data"]["warnings"]
    )
    assert unknown_html_ru.status_code == 200
    assert unknown_html_en.status_code == 200
    unknown_data = unknown_api.json()["data"]
    assert unknown_data["final_decision"]["attention_reason_code"] == (
        "unknown_final_attention_code"
    )
    assert "Неизвестный код причины" in unknown_html_ru.text
    assert "Unknown reason code" in unknown_html_en.text
    assert (
        "Код причины внимания неизвестен. Показано безопасное совместимое объяснение."
    ) in unknown_data["warnings"]
    assert (
        "The attention reason code is unknown. A safe compatible explanation is shown."
    ) in unknown_api_en.json()["data"]["warnings"]
    assert "unknown attention_reason_code" not in unknown_html_ru.text
    assert "unknown attention_reason_code" not in unknown_html_en.text
    assert legacy_status_ru.status_code == 200
    assert legacy_status_en.status_code == 200
    assert (
        legacy_status_ru.json()["data"]["ai_adjudicator"][
            "ai_adjudicator_reason_display"
        ]
        == "ИИ-арбитр направил событие на ручную проверку"
    )
    assert (
        legacy_status_en.json()["data"]["ai_adjudicator"][
            "ai_adjudicator_reason_display"
        ]
        == "AI adjudicator routed the event to manual review"
    )
    assert (
        "legacy ai_reason_code missing" in legacy_status_ru.json()["data"]["warnings"]
    )
    client.close()
    after = {
        path: (sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        for path in paths
    }
    assert after == before


def test_rop_queue_detail_link_is_localized_in_ru(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-rop-detail-ru")
    client = _client(storage_dir)

    response = client.get("/rop?run_id=run-rop-detail-ru&tab=queue&lang=ru")

    assert response.status_code == 200
    assert "Подробнее" in response.text
    assert (
        'href="/rop/events/evt-1?run_id=run-rop-detail-ru&amp;period=all&amp;lang=ru"'
        in response.text
    )


class TestRopTabs:
    def _setup(self, tmp_path: Path) -> tuple[Path, TestClient]:
        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-rop-tabs")
        client = _client(storage_dir)
        return storage_dir, client

    def test_all_tabs_return_200(self, tmp_path: Path) -> None:
        _, client = self._setup(tmp_path)
        for tab in (
            "overview",
            "queue",
            "sources",
            "attachments",
            "evidence",
            "bitrix",
        ):
            response = client.get(f"/rop?tab={tab}")
            assert response.status_code == 200, f"Tab {tab} failed"
            assert "Unavailable block" not in response.text
            assert "Failed to render block type" not in response.text
            assert "attention_list" not in response.text

    def test_invalid_tab_falls_back(self, tmp_path: Path) -> None:
        _, client = self._setup(tmp_path)
        response = client.get("/rop?tab=invalid")
        assert response.status_code == 200

    def test_overview_content(self, tmp_path: Path) -> None:
        _, client = self._setup(tmp_path)
        response = client.get("/rop?tab=overview")
        html = response.text
        assert "ROP Control Center" in html
        assert "Emails in period" in html
        assert "NEW LEADS" in html
        assert "Urgent leads" in html
        assert "Needs review" in html
        assert "Bitrix gaps" in html
        assert "Data quality" in html
        assert "Action Required" in html
        assert "Priority review queue" in html
        assert "Unavailable block" not in html
        assert "Failed to render block type" not in html
        assert "attention_list" not in html

    def test_queue_content(self, tmp_path: Path) -> None:
        _, client = self._setup(tmp_path)
        response = client.get("/rop?tab=queue")
        assert response.status_code == 200

    def test_sources_content(self, tmp_path: Path) -> None:
        _, client = self._setup(tmp_path)
        response = client.get("/rop?tab=sources")
        assert response.status_code == 200

    def test_attachments_content(self, tmp_path: Path) -> None:
        _, client = self._setup(tmp_path)
        response = client.get("/rop?tab=attachments")
        assert response.status_code == 200

    def test_evidence_content(self, tmp_path: Path) -> None:
        _, client = self._setup(tmp_path)
        response = client.get("/rop?tab=evidence")
        assert response.status_code == 200

    def test_bitrix_content(self, tmp_path: Path) -> None:
        _, client = self._setup(tmp_path)
        response = client.get("/rop?tab=bitrix")
        assert response.status_code == 200
        assert "Bitrix Evidence Board" in response.text


class TestRopPageLayout:
    def _rop_html(self, tmp_path: Path) -> str:
        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-subtitle")
        client = _client(storage_dir)
        response = client.get("/rop")
        assert response.status_code == 200
        return response.text

    def test_subtitle_present(self, tmp_path: Path) -> None:
        html = self._rop_html(tmp_path)
        assert "Inbound leads, review queue and Bitrix reconciliation" in html

    def test_tabs_rendered(self, tmp_path: Path) -> None:
        html = self._rop_html(tmp_path)
        assert 'href="/rop?tab=overview"' in html or "overview" in html.lower()

    def test_page_tabs_card(self, tmp_path: Path) -> None:
        html = self._rop_html(tmp_path)
        assert "beeui-page-tabs-card" in html

    def test_section_aria_label(self, tmp_path: Path) -> None:
        html = self._rop_html(tmp_path)
        assert 'section aria-label="Page blocks"' in html

    def test_subtitle_before_tabs(self, tmp_path: Path) -> None:
        html = self._rop_html(tmp_path)
        sub_pos = html.find("Inbound leads")
        card_pos = html.find("beeui-page-tabs-card")
        assert sub_pos >= 0 and card_pos >= 0
        assert sub_pos < card_pos, "Subtitle должен быть до page-tabs-card"

    def test_run_overview_inside_card(self, tmp_path: Path) -> None:
        html = self._rop_html(tmp_path)
        card_start = html.find("beeui-page-tabs-card")
        card_section = html[card_start:]
        assert "Overview" in card_section, "Overview должен быть внутри card"

    def test_no_old_standalone_tabs_card(self, tmp_path: Path) -> None:
        html = self._rop_html(tmp_path)
        card_start = html.find("beeui-page-tabs-card")
        before_card = html[:card_start] if card_start >= 0 else html
        assert (
            'class="card-header"' not in before_card or "beeui-page-tabs-card" in html
        )


class TestRopOverviewLayoutStructure:
    def _mock_data(self) -> dict[str, Any]:
        return {
            "run_id": "run-test-001",
            "kpis": {
                "source_count": 3,
                "loaded_count": 42,
                "classified_count": 38,
                "fallback_count": 5,
                "high_priority_count": 2,
                "attachment_preview_count": 7,
            },
            "available_runs": [],
            "warnings": [],
            "source_health": [],
            "funnel": [],
            "recommendations": [],
            "evidence_links": [],
            "classification_distribution": {},
            "business_kpi": {
                "processed_events": 38,
                "new_leads": 12,
                "high_priority": 2,
                "needs_review": 5,
                "lost_in_bitrix": 1,
                "unreconciled": 3,
            },
            "period": "7d",
            "configured_periods": ["7d", "30d", "90d", "365d", "all"],
        }

    def test_first_block_is_overview(self) -> None:
        layout = build_rop_page_layout(self._mock_data(), tab="overview")
        assert layout[0]["type"] == "operator_hero"
        assert layout[0]["title"] == "ROP Control Center"
        assert layout[0]["width"] == 6

    def test_top_row_has_two_chart_cards(self) -> None:
        layout = build_rop_page_layout(self._mock_data(), tab="overview")
        assert layout[1]["type"] == "chart"
        assert layout[1]["title"] == "Lead outcome mix"
        assert layout[1]["width"] == 6

    def test_kpi_has_customer_facing_labels(self) -> None:
        layout = build_rop_page_layout(self._mock_data(), tab="overview")
        labels = [block["title"] for block in layout if block["type"] == "venue_card"]
        assert "Urgent leads" in labels
        assert "Needs review" in labels
        assert "Bitrix gaps" in labels
        assert "Data quality" in labels

    def test_kpi_has_four_small_cards(self) -> None:
        layout = build_rop_page_layout(self._mock_data(), tab="overview")
        cards = [block for block in layout if block["type"] == "venue_card"]
        assert len(cards) == 4

    def test_action_required_present(self) -> None:
        layout = build_rop_page_layout(self._mock_data(), tab="overview")
        action_block = next(
            block for block in layout if block.get("title") == "Action Required"
        )
        assert action_block["type"] == "chart"

    def test_no_run_selector_in_overview(self) -> None:
        layout = build_rop_page_layout(self._mock_data(), tab="overview")
        run_selectors = [
            block for block in layout if block.get("title") == "Run Selector"
        ]
        assert len(run_selectors) == 0

    def test_no_period_selector_card(self) -> None:
        """Period Selector card is replaced by ROP Workbench toolbar links."""
        layout = build_rop_page_layout(self._mock_data(), tab="overview")
        period_cards = [
            block for block in layout if block.get("title") == "Period Selector"
        ]
        assert len(period_cards) == 0
        for b in layout:
            assert b.get("title") not in ("Period", "Period Selector"), (
                f"Unexpected block: {b.get('title')}"
            )

    def test_priority_queue_preview_present(self) -> None:
        layout = build_rop_page_layout(self._mock_data(), tab="overview")
        assert any(block.get("title") == "Priority review queue" for block in layout)


def test_rop_chart_blocks_use_controlled_fields() -> None:
    data = {
        "run_id": "run-chart",
        "kpis": {},
        "available_runs": [],
        "warnings": [],
        "source_health": [],
        "funnel": [],
        "recommendations": [],
        "evidence_links": [],
        "classification_distribution": {},
        "business_kpi": {},
        "series": {
            "processed_by_day": {
                "labels": ["2026-06-20", "2026-06-21"],
                "series": [{"name": "Processed", "data": [1, 2]}],
            },
            "classification_distribution": {
                "labels": ["new_lead"],
                "series": [2],
            },
            "bitrix_distribution": {
                "labels": ["matched", "unreconciled"],
                "series": [1, 1],
            },
            "source_contribution": {
                "labels": ["hotline", "web"],
                "series": [3, 1],
            },
        },
        "period": "all",
    }

    layout = build_rop_page_layout(data, tab="overview")
    charts = [block for block in layout if block["type"] == "chart"]

    assert charts
    for chart in charts:
        assert "kind" in chart
        assert "series" in chart
        assert "data" not in chart
    area = next(chart for chart in charts if chart["title"] == "Email Workload")
    assert area["kind"] == "area"
    assert area["categories"] == ["2026-06-20", "2026-06-21"]
    donuts = [chart for chart in charts if chart["kind"] == "donut"]
    assert all("labels" in chart for chart in donuts)
    source_chart = next(
        chart for chart in charts if chart["title"] == "Source contribution"
    )
    assert source_chart["kind"] == "bar"
    assert source_chart["series"] == [{"name": "Leads", "data": [3, 1]}]
    assert source_chart["categories"] == ["Hotline", "Web"]
    line_chart = next(chart for chart in charts if chart["title"] == "Email Workload")
    assert line_chart["kind"] == "area"
    assert "data" not in source_chart


def test_rop_overview_buckets_7d_and_30d_chart_series() -> None:
    base_data = {
        "run_id": "run-buckets",
        "kpis": {},
        "available_runs": [],
        "warnings": [],
        "source_health": [],
        "funnel": [],
        "recommendations": [],
        "evidence_links": [],
        "classification_distribution": {},
        "business_kpi": {"processed_events": 3, "high_priority": 1},
        "series": {
            "processed_by_day": {
                "labels": ["2026-06-21"],
                "series": [
                    {"name": "Processed", "data": [3]},
                    {"name": "High priority", "data": [1]},
                ],
            }
        },
        "period_end_utc": "2026-06-21T23:59:59+00:00",
        "configured_periods": ["7d", "30d"],
    }

    for period, expected_count in (("7d", 7), ("30d", 30)):
        data = {**base_data, "period": period}
        layout = build_rop_page_layout(data, tab="overview")
        chart = next(block for block in layout if block["title"] == "Email Workload")
        assert len(chart["categories"]) == expected_count
        assert chart["categories"][-1] == "2026-06-21"
        for series_item in chart["series"]:
            assert len(series_item["data"]) == expected_count


def test_rop_overview_source_contribution_uses_display_names() -> None:
    data = {
        "run_id": "run-source-display",
        "kpis": {},
        "available_runs": [],
        "warnings": [],
        "source_health": [
            {
                "source_id": "rop_batch_sample",
                "display_name": "ROP Batch Sample",
            }
        ],
        "funnel": [],
        "recommendations": [],
        "evidence_links": [],
        "classification_distribution": {},
        "business_kpi": {},
        "series": {
            "source_contribution": {
                "labels": ["rop_batch_sample"],
                "series": [2],
            },
        },
        "period": "7d",
        "configured_periods": ["7d"],
    }

    layout = build_rop_page_layout(data, tab="overview")
    chart = next(block for block in layout if block["title"] == "Source contribution")
    assert chart["categories"] == ["ROP Batch Sample"]


def test_rop_overview_contains_period_selector_from_payload() -> None:
    data = {
        "run_id": "run-test-001",
        "kpis": {},
        "available_runs": [],
        "warnings": [],
        "source_health": [],
        "funnel": [],
        "recommendations": [],
        "evidence_links": [],
        "classification_distribution": {},
        "business_kpi": {},
        "series": {},
        "period": "7d",
        "configured_periods": ["today", "7d", "30d", "all"],
    }

    layout = build_rop_page_layout(data, tab="overview")
    overview = next(
        block for block in layout if block.get("title") == "ROP Control Center"
    )
    items = overview["primary_links"]

    assert [item["label"] for item in items] == [
        "Today",
        "Last 7 days (current)",
        "Last 30 days",
        "All time",
    ]
    assert items[0]["href"] == "/rop?tab=overview&run_id=run-test-001&period=today"
    assert items[1]["href"] == "/rop?tab=overview&run_id=run-test-001&period=7d"


def test_rop_overview_uses_unique_action_events_and_event_detail_links() -> None:
    data = {
        "run_id": "run-overview-actions",
        "kpis": {},
        "available_runs": [],
        "warnings": [],
        "source_health": [],
        "funnel": [],
        "recommendations": [],
        "evidence_links": [],
        "classification_distribution": {},
        "business_kpi": {
            "processed_events": 2,
            "high_priority": 1,
            "needs_review": 1,
            "unreconciled": 1,
        },
        "series": {},
        "period": "7d",
        "configured_periods": ["7d"],
        "queues": {
            "high_priority": [
                {
                    "event_id": "evt-1",
                    "sender": "lead@example.com",
                    "subject": "Urgent request",
                    "bot_priority": "high",
                    "reason": "urgent_request",
                    "recommended_next_step": "review",
                }
            ],
            "needs_review": [
                {
                    "event_id": "evt-1",
                    "sender": "lead@example.com",
                    "subject": "Urgent request",
                    "bot_priority": "high",
                    "reason": "needs_review",
                    "recommended_next_step": "review",
                }
            ],
            "unreconciled": [
                {
                    "event_id": "evt-2",
                    "sender": "client@example.com",
                    "subject": "Existing request",
                    "bot_priority": "medium",
                    "reason": "not_reconciled",
                    "recommended_next_step": "reconcile",
                }
            ],
        },
    }

    layout = build_rop_page_layout(data, tab="overview")

    action_block = next(
        block for block in layout if block.get("title") == "Action Required"
    )
    queue_block = next(block for block in layout if block.get("type") == "data_table")

    assert action_block["series"] == [2, 0]
    assert "2 items need review" in action_block["subtitle"]
    assert queue_block["rows"][0]["evidence"]["href"] == (
        "/rop/events/evt-1?run_id=run-overview-actions&period=7d"
    )

    ru_layout = build_rop_page_layout(data, tab="overview", locale="ru")
    ru_queue_block = next(
        block for block in ru_layout if block.get("type") == "data_table"
    )

    assert ru_queue_block["rows"][0]["evidence"]["href"] == (
        "/rop/events/evt-1?run_id=run-overview-actions&period=7d&lang=ru"
    )


def test_rop_overview_bitrix_errors_shows_in_kpi() -> None:
    """Bitrix errors should appear in KPI cards when non-zero."""
    data = {
        "run_id": "run-bitrix-errors",
        "kpis": {},
        "available_runs": [],
        "warnings": [],
        "source_health": [],
        "funnel": [],
        "recommendations": [],
        "evidence_links": [],
        "classification_distribution": {},
        "business_kpi": {"bitrix_errors": 2},
        "bitrix": {"connector_degraded_count": 99},
        "series": {},
    }

    layout = build_rop_page_layout(data, tab="overview")
    assert any(block.get("title") == "Action Required" for block in layout)
    assert all(block.get("title") != "Business metrics" for block in layout)


def test_rop_queue_tab_contains_data_table_when_queues_exist() -> None:
    data = {
        "attention_events": [],
        "queues": {
            "high_priority": [
                {
                    "event_id": "evt-high",
                    "source_id": "hotline",
                    "sender": "lead@example.com",
                    "subject": "Need welding equipment",
                    "case_type": "legacy_case",
                    "priority": "low",
                    "bot_case_type": "new_lead",
                    "bot_priority": "high",
                    "bitrix_status": "unreconciled",
                    "reason": "urgent_inquiry",
                }
            ]
        },
    }

    layout = build_rop_page_layout(data, tab="queue")

    assert len(layout) == 1
    assert layout[0]["type"] == "data_table"
    assert layout[0]["title"] == "ROP Work Queue"
    assert "toolbar" in layout[0]
    assert "fields" in layout[0]["toolbar"]
    assert "column_toggles" in layout[0]["toolbar"]
    assert "reset" in layout[0]["toolbar"]
    assert "apply" not in layout[0]["toolbar"]
    assert [col["label"] for col in layout[0]["columns"]] == [
        "Priority",
        "Sender",
        "Subject",
        "Date",
        "Classification",
        "Bitrix status",
    ]
    assert layout[0]["rows"][0]["classification"] == "New lead"
    assert layout[0]["rows"][0]["priority"]["label"] == "high"


def test_rop_queue_tab_shows_data_table_when_queues_empty_with_attention_events() -> (
    None
):
    data = {
        "attention_events": [
            {
                "event_id": "evt-fallback-001",
                "source_id": "hotline_mailbox",
                "source_display_name": "Hotline mailbox",
                "sender": "client@example.com",
                "subject": "Price request",
                "case_type": "new_lead",
                "priority": "high",
                "date": "2026-07-01T10:00:00+00:00",
                "detail_href": "/rop/events/evt-fallback-001",
            },
            {
                "event_id": "evt-fallback-002",
                "source_id": "online_mailbox",
                "source_display_name": "Online mailbox",
                "sender": "buyer@example.com",
                "subject": "Order inquiry",
                "case_type": "existing_deal",
                "priority": "medium",
                "date": "2026-07-02T14:30:00+00:00",
                "detail_href": "/rop/events/evt-fallback-002",
            },
        ],
        "queues": {},
        "filter_params": {},
        "filter_options": {},
        "page": 1,
        "page_size": 25,
        "sort": "received_at",
        "order": "desc",
        "period": "",
    }

    layout = build_rop_page_layout(data, tab="queue")

    assert len(layout) == 1
    assert layout[0]["type"] == "data_table"
    assert "toolbar" in layout[0]
    assert layout[0]["title"] == "ROP Work Queue"
    assert len(layout[0]["rows"]) == 2
    row_senders = {r["client"]["title"] for r in layout[0]["rows"]}
    assert "client@example.com" in row_senders
    assert "buyer@example.com" in row_senders


def test_rop_queue_tab_shows_empty_table_when_no_data() -> None:
    data = {
        "attention_events": [],
        "queues": {},
        "filter_params": {},
        "filter_options": {},
        "page": 1,
        "page_size": 25,
        "sort": "received_at",
        "order": "desc",
        "period": "",
    }

    layout = build_rop_page_layout(data, tab="queue")

    assert len(layout) == 1
    assert layout[0]["type"] == "data_table"
    assert "toolbar" in layout[0]
    assert len(layout[0]["rows"]) == 0
    assert layout[0]["pagination"]["label"] == "/ 0"


def test_rop_queue_filter_options_from_queue_data() -> None:
    data = {
        "attention_events": [],
        "queues": {
            "high_priority": [
                {
                    "event_id": "evt-1",
                    "case_type": "new_lead",
                    "priority": "high",
                    "bitrix_status": "not_found",
                },
                {
                    "event_id": "evt-2",
                    "case_type": "existing_deal",
                    "priority": "medium",
                    "bitrix_status": "matched_lead",
                },
            ],
            "needs_review": [
                {
                    "event_id": "evt-3",
                    "case_type": "new_lead",
                    "priority": "high",
                    "bitrix_status": "ambiguous",
                },
            ],
        },
        "filter_params": {},
        "filter_options": {
            "case_types": ["new_lead", "existing_deal"],
            "priorities": ["high", "medium"],
            "bitrix_statuses": ["not_found", "matched_lead", "ambiguous"],
        },
        "page": 1,
        "page_size": 25,
        "sort": "received_at",
        "order": "desc",
        "period": "",
    }

    layout = build_rop_page_layout(data, tab="queue")

    assert len(layout) == 1
    assert layout[0]["type"] == "data_table"
    assert "toolbar" in layout[0]
    field_types = {f.get("type") for f in layout[0]["toolbar"].get("fields", [])}
    assert "checkboxes" in field_types
    assert len(layout[0]["rows"]) == 3


def test_queue_toolbar_contract() -> None:
    data = {
        "attention_events": [],
        "queues": {
            "high_priority": [
                {
                    "event_id": "evt-1",
                    "sender": "a@b.com",
                    "subject": "Test",
                    "case_type": "new_lead",
                    "priority": "high",
                    "bitrix_status": "not_found",
                }
            ],
        },
        "filter_params": {"q": "test", "date_from": "2026-07-01"},
        "filter_options": {
            "case_types": ["new_lead"],
            "priorities": ["high"],
            "bitrix_statuses": ["not_found"],
        },
        "page": 1,
        "page_size": 25,
        "sort": "received_at",
        "order": "desc",
        "period": "all",
    }
    layout = build_rop_page_layout(data, tab="queue")
    tb = layout[0].get("toolbar", {})
    assert "fields" in tb
    assert "hidden" in tb
    assert "column_toggles" in tb
    assert "reset" in tb
    assert "apply" not in tb
    field_types = [f["type"] for f in tb["fields"]]
    assert "date_range" in field_types
    assert "text" in field_types
    assert "checkboxes" in field_types
    date_field = next(f for f in tb["fields"] if f["type"] == "date_range")
    assert date_field["label"] == ""
    text_field = next(f for f in tb["fields"] if f["type"] == "text")
    assert text_field["label"] == ""
    assert tb["hidden"].get("tab") == "queue"
    assert len(tb["column_toggles"]) > 0
    assert tb["reset"].get("href")


def test_queue_toolbar_no_filter_form() -> None:
    data = {
        "attention_events": [],
        "queues": {},
        "filter_params": {},
        "filter_options": {},
    }
    layout = build_rop_page_layout(data, tab="queue")
    block_types = [b["type"] for b in layout]
    assert "filter_form" not in block_types


def test_queue_toolbar_other_tabs_no_toolbar() -> None:
    data = {
        "run_id": "run-001",
        "kpis": {},
        "available_runs": [],
        "warnings": [],
        "source_health": [],
        "funnel": [],
        "recommendations": [],
        "evidence_links": [],
        "classification_distribution": {},
        "business_kpi": {},
        "series": {},
        "period": "7d",
        "configured_periods": ["7d"],
    }
    for tab in ("overview", "sources", "attachments", "evidence", "bitrix"):
        layout = build_rop_page_layout(data, tab=tab)
        for block in layout:
            if block.get("type") == "data_table":
                assert "toolbar" not in block


def test_queue_toolbar_hidden_contains_active_classification() -> None:
    data = {
        "attention_events": [],
        "queues": {
            "high_priority": [
                {
                    "event_id": "evt-1",
                    "sender": "a@b.com",
                    "subject": "Test",
                    "case_type": "new_lead",
                    "priority": "high",
                    "bitrix_status": "not_found",
                }
            ],
        },
        "filter_params": {"case_type": "new_lead", "q": "test"},
        "filter_options": {
            "case_types": ["new_lead", "existing_deal"],
            "priorities": ["high"],
            "bitrix_statuses": ["not_found"],
        },
        "page": 1,
        "page_size": 25,
        "sort": "received_at",
        "order": "desc",
        "period": "all",
    }
    layout = build_rop_page_layout(data, tab="queue")
    tb = layout[0].get("toolbar", {})
    hidden = tb.get("hidden", {})
    assert hidden.get("case_type") == "new_lead"


def test_queue_toolbar_hidden_contains_active_priority() -> None:
    data = {
        "attention_events": [],
        "queues": {
            "high_priority": [
                {
                    "event_id": "evt-1",
                    "sender": "a@b.com",
                    "subject": "Test",
                    "case_type": "new_lead",
                    "priority": "high",
                    "bitrix_status": "not_found",
                }
            ],
        },
        "filter_params": {"priority": "high"},
        "filter_options": {
            "case_types": ["new_lead"],
            "priorities": ["high"],
            "bitrix_statuses": ["not_found"],
        },
        "page": 1,
        "page_size": 25,
        "sort": "received_at",
        "order": "desc",
        "period": "all",
    }
    layout = build_rop_page_layout(data, tab="queue")
    tb = layout[0].get("toolbar", {})
    hidden = tb.get("hidden", {})
    assert hidden.get("priority") == "high"


def test_queue_toolbar_hidden_contains_active_bitrix_status() -> None:
    data = {
        "attention_events": [],
        "queues": {
            "high_priority": [
                {
                    "event_id": "evt-1",
                    "sender": "a@b.com",
                    "subject": "Test",
                    "case_type": "new_lead",
                    "priority": "high",
                    "bitrix_status": "not_found",
                }
            ],
        },
        "filter_params": {"bitrix_status": "not_found,ambiguous"},
        "filter_options": {
            "case_types": ["new_lead"],
            "priorities": ["high"],
            "bitrix_statuses": ["not_found", "ambiguous"],
        },
        "page": 1,
        "page_size": 25,
        "sort": "received_at",
        "order": "desc",
        "period": "all",
    }
    layout = build_rop_page_layout(data, tab="queue")
    tb = layout[0].get("toolbar", {})
    hidden = tb.get("hidden", {})
    assert hidden.get("bitrix_status") == "not_found,ambiguous"


def test_queue_toolbar_hidden_contains_active_columns() -> None:
    data = {
        "attention_events": [],
        "queues": {
            "high_priority": [
                {
                    "event_id": "evt-1",
                    "sender": "a@b.com",
                    "subject": "Test",
                    "case_type": "new_lead",
                    "priority": "high",
                    "bitrix_status": "not_found",
                }
            ],
        },
        "filter_params": {"columns": "priority,subject,date"},
        "filter_options": {
            "case_types": ["new_lead"],
            "priorities": ["high"],
            "bitrix_statuses": ["not_found"],
        },
        "page": 1,
        "page_size": 25,
        "sort": "received_at",
        "order": "desc",
        "period": "all",
    }
    layout = build_rop_page_layout(data, tab="queue")
    tb = layout[0].get("toolbar", {})
    hidden = tb.get("hidden", {})
    assert hidden.get("columns") == "priority,subject,date"


def test_queue_toolbar_hidden_contains_canonical_params() -> None:
    data = {
        "attention_events": [],
        "queues": {
            "high_priority": [
                {
                    "event_id": "evt-1",
                    "sender": "a@b.com",
                    "subject": "Test",
                    "case_type": "new_lead",
                    "priority": "high",
                    "bitrix_status": "not_found",
                }
            ],
        },
        "filter_params": {},
        "filter_options": {
            "case_types": ["new_lead"],
            "priorities": ["high"],
            "bitrix_statuses": ["not_found"],
        },
        "page": 2,
        "page_size": 50,
        "sort": "sender",
        "order": "asc",
        "period": "7d",
    }
    layout = build_rop_page_layout(data, tab="queue")
    tb = layout[0].get("toolbar", {})
    hidden = tb.get("hidden", {})
    assert hidden.get("tab") == "queue"
    assert hidden.get("page") == "1"
    assert hidden.get("page_size") == "50"
    assert hidden.get("sort") == "sender"
    assert hidden.get("order") == "asc"
    assert hidden.get("period") == "7d"


def test_queue_toolbar_hidden_contains_run_id_and_lang() -> None:
    data = {
        "attention_events": [],
        "queues": {
            "high_priority": [
                {
                    "event_id": "evt-1",
                    "sender": "a@b.com",
                    "subject": "Test",
                    "case_type": "new_lead",
                    "priority": "high",
                    "bitrix_status": "not_found",
                }
            ],
        },
        "filter_params": {},
        "filter_options": {
            "case_types": ["new_lead"],
            "priorities": ["high"],
            "bitrix_statuses": ["not_found"],
        },
        "page": 1,
        "page_size": 25,
        "sort": "received_at",
        "order": "desc",
        "period": "all",
        "run_id": "run-test-001",
    }
    layout = build_rop_page_layout(data, tab="queue", locale="ru")
    tb = layout[0].get("toolbar", {})
    hidden = tb.get("hidden", {})
    assert hidden.get("run_id") == "run-test-001"
    assert hidden.get("lang") == "ru"


def test_queue_toolbar_combined_filters_in_hidden() -> None:
    data = {
        "attention_events": [],
        "queues": {
            "high_priority": [
                {
                    "event_id": "evt-1",
                    "sender": "a@b.com",
                    "subject": "Test",
                    "case_type": "new_lead",
                    "priority": "high",
                    "bitrix_status": "not_found",
                }
            ],
        },
        "filter_params": {
            "case_type": "new_lead,existing_deal",
            "priority": "high",
            "bitrix_status": "not_found",
            "columns": "priority,subject,date,classification",
        },
        "filter_options": {
            "case_types": ["new_lead", "existing_deal"],
            "priorities": ["high"],
            "bitrix_statuses": ["not_found"],
        },
        "page": 1,
        "page_size": 25,
        "sort": "received_at",
        "order": "desc",
        "period": "all",
    }
    layout = build_rop_page_layout(data, tab="queue")
    tb = layout[0].get("toolbar", {})
    hidden = tb.get("hidden", {})
    assert hidden.get("case_type") == "new_lead,existing_deal"
    assert hidden.get("priority") == "high"
    assert hidden.get("bitrix_status") == "not_found"
    assert hidden.get("columns") == "priority,subject,date,classification"
    assert "apply" not in tb


def test_queue_search_submission_preserves_hidden_filters() -> None:
    data = {
        "attention_events": [],
        "queues": {
            "high_priority": [
                {
                    "event_id": "evt-1",
                    "sender": "a@b.com",
                    "subject": "Test",
                    "case_type": "new_lead",
                    "priority": "high",
                    "bitrix_status": "not_found",
                }
            ],
        },
        "filter_params": {
            "q": "test search",
            "case_type": "new_lead",
            "priority": "high",
            "columns": "priority,subject",
        },
        "filter_options": {
            "case_types": ["new_lead"],
            "priorities": ["high"],
            "bitrix_statuses": ["not_found"],
        },
        "page": 1,
        "page_size": 25,
        "sort": "received_at",
        "order": "desc",
        "period": "all",
    }
    layout = build_rop_page_layout(data, tab="queue")
    tb = layout[0].get("toolbar", {})
    hidden = tb.get("hidden", {})
    assert hidden.get("q") is None
    assert hidden.get("case_type") == "new_lead"
    assert hidden.get("priority") == "high"
    assert hidden.get("columns") == "priority,subject"


def test_queue_date_submission_preserves_hidden_filters() -> None:
    data = {
        "attention_events": [],
        "queues": {
            "high_priority": [
                {
                    "event_id": "evt-1",
                    "sender": "a@b.com",
                    "subject": "Test",
                    "case_type": "new_lead",
                    "priority": "high",
                    "bitrix_status": "not_found",
                }
            ],
        },
        "filter_params": {
            "date_from": "2026-07-01",
            "date_to": "2026-07-31",
            "case_type": "new_lead",
            "priority": "high",
            "columns": "priority,subject",
        },
        "filter_options": {
            "case_types": ["new_lead"],
            "priorities": ["high"],
            "bitrix_statuses": ["not_found"],
        },
        "page": 1,
        "page_size": 25,
        "sort": "received_at",
        "order": "desc",
        "period": "all",
    }
    layout = build_rop_page_layout(data, tab="queue")
    tb = layout[0].get("toolbar", {})
    hidden = tb.get("hidden", {})
    assert hidden.get("date_from") is None
    assert hidden.get("case_type") == "new_lead"
    assert hidden.get("priority") == "high"
    assert hidden.get("columns") == "priority,subject"


def test_queue_toolbar_has_no_apply() -> None:
    data = {
        "attention_events": [],
        "queues": {
            "high_priority": [
                {
                    "event_id": "evt-1",
                    "sender": "a@b.com",
                    "subject": "Test",
                    "case_type": "new_lead",
                    "priority": "high",
                    "bitrix_status": "not_found",
                }
            ],
        },
        "filter_params": {},
        "filter_options": {
            "case_types": ["new_lead"],
            "priorities": ["high"],
            "bitrix_statuses": ["not_found"],
        },
        "page": 1,
        "page_size": 25,
        "sort": "received_at",
        "order": "desc",
        "period": "all",
    }
    layout = build_rop_page_layout(data, tab="queue")
    tb = layout[0].get("toolbar", {})
    assert "apply" not in tb


def test_queue_toolbar_reset_preserves_only_tab_run_id_period_lang() -> None:
    data = {
        "attention_events": [],
        "queues": {
            "high_priority": [
                {
                    "event_id": "evt-1",
                    "sender": "a@b.com",
                    "subject": "Test",
                    "case_type": "new_lead",
                    "priority": "high",
                    "bitrix_status": "not_found",
                }
            ],
        },
        "filter_params": {
            "q": "test",
            "date_from": "2026-07-01",
            "date_to": "2026-07-31",
            "case_type": "new_lead",
            "priority": "high",
            "bitrix_status": "not_found",
            "columns": "priority,subject",
        },
        "filter_options": {
            "case_types": ["new_lead"],
            "priorities": ["high"],
            "bitrix_statuses": ["not_found"],
        },
        "page": 3,
        "page_size": 50,
        "sort": "sender",
        "order": "asc",
        "period": "7d",
        "run_id": "run-reset-test",
    }
    layout = build_rop_page_layout(data, tab="queue")
    tb = layout[0].get("toolbar", {})
    reset_href = tb["reset"]["href"]
    assert "tab=queue" in reset_href
    assert "run_id=run-reset-test" in reset_href
    assert "period=7d" in reset_href
    assert "q=" not in reset_href or "q" not in reset_href.split("?")[-1].split("&")
    assert "date_from" not in reset_href
    assert "date_to" not in reset_href
    assert "case_type" not in reset_href
    assert "priority" not in reset_href
    assert "bitrix_status" not in reset_href
    assert "columns" not in reset_href
    assert "page=" not in reset_href.split("?")[-1].split("&")[0]
    assert "page_size" not in reset_href
    assert "sort=" not in reset_href.split("?")[-1].split("&")[0]
    assert "order=" not in reset_href.split("?")[-1].split("&")[0]


def test_queue_toolbar_reset_preserves_lang_ru() -> None:
    data = {
        "attention_events": [],
        "queues": {
            "high_priority": [
                {
                    "event_id": "evt-1",
                    "sender": "a@b.com",
                    "subject": "Test",
                    "case_type": "new_lead",
                    "priority": "high",
                    "bitrix_status": "not_found",
                }
            ],
        },
        "filter_params": {
            "q": "test",
            "case_type": "new_lead",
            "columns": "priority,subject",
        },
        "filter_options": {
            "case_types": ["new_lead"],
            "priorities": ["high"],
            "bitrix_statuses": ["not_found"],
        },
        "page": 2,
        "page_size": 100,
        "sort": "received_at",
        "order": "desc",
        "period": "all",
    }
    layout = build_rop_page_layout(data, tab="queue", locale="ru")
    tb = layout[0].get("toolbar", {})
    reset_href = tb["reset"]["href"]
    assert "tab=queue" in reset_href
    assert "lang=ru" in reset_href
    assert "q=" not in reset_href or "q" not in reset_href.split("?")[-1].split("&")
    assert "case_type" not in reset_href
    assert "columns" not in reset_href
    assert "page=" not in reset_href.split("?")[-1].split("&")[0]
    assert "page_size" not in reset_href
    assert "sort=" not in reset_href.split("?")[-1].split("&")[0]


def test_rop_overview_uses_rop_recommendations_detail() -> None:
    data = {
        "run_id": "run-rec",
        "kpis": {},
        "available_runs": [],
        "warnings": [],
        "source_health": [],
        "funnel": [],
        "recommendations": [
            {
                "title": "Legacy recommendation",
                "message": "Legacy message",
                "severity": "info",
            }
        ],
        "rop_recommendations": [
            {
                "title": "Run Bitrix reconciliation",
                "detail": "2 events have not been reconciled with Bitrix.",
                "severity": "info",
            }
        ],
        "evidence_links": [],
        "classification_distribution": {},
        "business_kpi": {},
        "series": {},
    }

    layout = build_rop_page_layout(data, tab="overview")
    action_block = next(
        block for block in layout if block.get("title") == "Action Required"
    )

    assert action_block["type"] == "chart"


def test_rop_bitrix_missing_artifact_renders_not_reconciled() -> None:
    data = {
        "current_state_kpi": {},
        "current_state_queues": {},
        "bitrix": {"status": "unreconciled"},
        "evidence_links": [
            {
                "artifact_id": "bitrix_reconciliation_json",
                "available": False,
            }
        ],
    }

    layout = build_rop_page_layout(data, tab="bitrix")

    assert layout[0]["type"] == "kpi_grid"
    assert layout[0]["title"] == "Bitrix Evidence Board"
    notices = [
        block
        for block in layout
        if block.get("type") == "state_grid"
        and any(
            item.get("label") == "Not reconciled" for item in block.get("items", [])
        )
    ]
    assert notices
    item = notices[0]["items"][0]
    assert item["label"] == "Not reconciled"
    assert "Run read-only reconcile-bitrix" in item["value"]


def test_api_rop_dashboard_invalid_period_is_rejected(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-invalid-period")
    client = _client(storage_dir)

    response = client.get("/api/rop/dashboard", params={"period": "14d"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_params"


def test_dashboard_accordion_has_chevron(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-accord")
    client = _client(storage_dir)
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "Technical details" in html
    assert "accordion-button" in html
    assert 'data-bs-toggle="collapse"' in html
    assert "aria-expanded" in html
    assert "aria-controls" in html
    assert "accordion-button-toggle" in html
    assert "accordion-tabs" not in html


def test_modules_route(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_modules_artifact(storage_dir)
    client = _client(storage_dir)
    response = client.get("/modules")
    assert response.status_code == 200
    assert "beeagent-rop" in response.text
    assert "beeagent_rop" in response.text
    assert "No blocks configured" not in response.text


def test_modules_route_escapes_html(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_modules_artifact_with_html(storage_dir)
    client = _client(storage_dir)
    response = client.get("/modules")
    assert response.status_code == 200
    assert "<script>alert" not in response.text


def test_api_dashboard(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["read_only"] is True


def test_api_runs(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-api-001")
    client = _client(storage_dir)
    response = client.get("/api/runs")
    assert response.status_code == 200


def test_api_run(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-api-detail")
    client = _client(storage_dir)
    response = client.get("/api/runs/run-api-detail")
    assert response.status_code == 200


def test_api_modules(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_modules_artifact(storage_dir)
    client = _client(storage_dir)
    response = client.get("/api/modules")
    assert response.status_code == 200


def test_api_rop_dashboard_rejects_invalid_run_id(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-rop-valid")
    client = _client(storage_dir)

    response = client.get("/api/rop/dashboard", params={"run_id": "../etc/passwd"})

    assert response.status_code == 400
    data = response.json()
    assert data["ok"] is False
    assert data["read_only"] is True
    assert data["error"]["code"] == "invalid_run_id"


def test_invalid_artifact_id(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-bad-art")
    client = _client(storage_dir)
    response = client.get("/runs/run-bad-art/artifacts/nonexistent_artifact")
    assert response.status_code in (200, 400, 404)


def test_non_allowlisted_artifact(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.artifacts import is_artifact_id_allowed

    assert is_artifact_id_allowed("operator_summary_json") is True
    assert is_artifact_id_allowed("run_json") is True
    assert is_artifact_id_allowed("raw_eml") is False
    assert is_artifact_id_allowed("some_random_file") is False


def test_non_allowlisted_artifact_error_envelope(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-bad-art")
    client = _client(storage_dir)
    response = client.get("/runs/run-bad-art/artifacts/raw_eml")
    assert response.status_code in (200, 400, 404)
    api_response = client.get("/api/runs/run-bad-art/artifacts/raw_eml")
    assert api_response.status_code in (200, 400, 404)
    if api_response.status_code == 400:
        data = api_response.json()
        assert "error" in data


def test_path_traversal(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))
    response = client.get("/runs/%2E%2E%2Fetc%2Fpasswd")
    assert response.status_code in (400, 404)


def test_path_traversal_artifact(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.artifacts import resolve_artifact_path

    storage_dir = _make_storage(tmp_path)
    result = resolve_artifact_path(storage_dir, "..", "operator_summary_json")
    assert result is None


def test_no_raw_eml_in_artifacts(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.bounded_read import read_bounded_json

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_run_artifacts(storage_dir, "run-no-eml")
    normalized_path = run_dir / "normalized_events.json"
    data = json.loads(normalized_path.read_text(encoding="utf-8"))
    data.append(
        {
            "event_id": "evt-eml",
            "raw_eml": "RAW_EML_SHOULD_BE_REDACTED",
        }
    )
    normalized_path.write_text(json.dumps(data), encoding="utf-8")

    text, warning, error = read_bounded_json(normalized_path)
    assert text is not None
    assert "RAW_EML_SHOULD_BE_REDACTED" not in text
    assert "[REDACTED]" in text


def test_historical_ai_assist_provider_preview_is_redacted(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.bounded_read import read_bounded_json

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_run_artifacts(storage_dir, "run-ai-assist-redaction")
    marker = "HISTORICAL-AI-ASSIST-PROVIDER-MARKER"
    artifact_path = run_dir / "rop_ai_assist_decisions.json"
    artifact_path.write_text(
        json.dumps(
            {
                "run_id": "run-ai-assist-redaction",
                "counters": {},
                "decisions": [
                    {
                        "event_id": "evt-1",
                        "status": "invalid",
                        "reason_code": "unparseable_response",
                        "raw_response_preview": marker,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    text, warning, error = read_bounded_json(artifact_path)
    client = _client(storage_dir)
    api_response = client.get(
        "/api/runs/run-ai-assist-redaction/artifacts/rop_ai_assist_decisions_json"
    )
    html_response = client.get(
        "/runs/run-ai-assist-redaction/artifacts/rop_ai_assist_decisions_json"
    )

    assert text is not None
    assert warning is None
    assert error is None
    assert marker not in text
    assert "[REDACTED]" in text
    assert api_response.status_code == 200
    assert html_response.status_code == 200
    assert marker not in api_response.text
    assert marker not in html_response.text
    assert "[REDACTED]" in api_response.text
    assert "[REDACTED]" in html_response.text


def test_malformed_json_warning(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.bounded_read import read_bounded_json

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_malformed_json_run(storage_dir, "run-malformed")
    path = run_dir / "operator_summary.json"

    text, warning, error = read_bounded_json(path)
    assert text is None
    assert warning is not None
    assert "Malformed" in warning


def test_get_routes_do_not_mutate_storage(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_run_artifacts(storage_dir, "run-no-mutate")
    client = _client(storage_dir)

    before = {
        path.relative_to(storage_dir).as_posix(): path.read_text(encoding="utf-8")
        for path in run_dir.rglob("*")
        if path.is_file()
    }

    client.get("/")
    client.get("/health")
    client.get("/runs")
    client.get("/runs/run-no-mutate")
    client.get("/rop")
    client.get("/modules")
    client.get("/api/dashboard")
    client.get("/api/runs")
    client.get("/api/runs/run-no-mutate")
    client.get("/api/modules")
    client.get("/api/rop/dashboard")

    after = {
        path.relative_to(storage_dir).as_posix(): path.read_text(encoding="utf-8")
        for path in run_dir.rglob("*")
        if path.is_file()
    }

    assert after == before


def test_rop_config_read_model_safety(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.read_model import build_config_read_model

    settings = {
        "rop": {
            "sources": [
                {
                    "source_id": "hotline",
                    "source_type": "mailbox_readonly",
                    "source_role": "technical_aggregator",
                    "client_id": "welding",
                    "display_name": "Hotline",
                    "enabled": True,
                    "authority": "read_only",
                    "items_max": 20,
                    "mailbox": {
                        "host": "imap.example.com",
                        "port": 993,
                        "use_ssl": True,
                        "folder": "INBOX",
                        "username_env": "ROP_MAILBOX_USERNAME",
                        "password_env": "ROP_MAILBOX_PASSWORD",
                    },
                }
            ]
        }
    }

    model = build_config_read_model(settings)
    sources = model["sources"]
    assert len(sources) == 1
    source = sources[0]

    assert source["source_id"] == "hotline"
    assert source["source_type"] == "mailbox_readonly"
    assert source["source_role"] == "technical_aggregator"
    assert source["client_id"] == "welding"
    assert source["display_name"] == "Hotline"
    assert source["enabled"] is True
    assert source["authority"] == "read_only"
    assert source["items_max"] == 20

    mailbox = source.get("mailbox", {})
    assert mailbox["host"] == "imap.example.com"
    assert mailbox["port"] == 993
    assert mailbox["use_ssl"] is True
    assert mailbox["folder"] == "INBOX"
    assert mailbox["username_env"] == "ROP_MAILBOX_USERNAME"

    assert "password_env" not in mailbox


def test_oversized_json_bounded(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.bounded_read import (
        MAX_JSON_BYTES,
        read_bounded_json,
    )

    oversized_path = tmp_path / "large.json"
    oversized_path.write_text("x" * (MAX_JSON_BYTES + 1), encoding="utf-8")

    text, warning, error = read_bounded_json(oversized_path)
    assert text is None
    assert warning is not None
    assert "too large" in warning


def test_tsv_bounded(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.bounded_read import read_bounded_tsv

    tsv_path = tmp_path / "test.tsv"
    tsv_path.write_text("col1\tcol2\nval1\tval2\n", encoding="utf-8")

    text, warning, error = read_bounded_tsv(tsv_path)
    assert text is not None
    assert "col1" in text
    assert warning is None


def test_artifact_allowlist_coverage() -> None:
    from beeagent_module.interfaces.ui.artifacts import is_artifact_id_allowed

    expected = [
        "run_json",
        "operator_summary_json",
        "source_diagnostics_json",
        "intake_metadata_json",
        "normalized_events_json",
        "classified_events_json",
        "attachment_extraction_json",
        "rop_review_table_tsv",
        "module_result_json",
        "rop_summary_result_json",
        "lead_classification_result_json",
        "steps_json",
    ]
    for aid in expected:
        assert is_artifact_id_allowed(aid), f"{aid} should be allowlisted"

    blocked = ["raw_eml", "attachment_content", "content_bytes", "payload_bytes"]
    for aid in blocked:
        assert not is_artifact_id_allowed(aid), f"{aid} should NOT be allowlisted"


def test_no_post_routes(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))

    for path in ["/", "/health", "/runs", "/rop", "/modules"]:
        response = client.post(path)
        assert response.status_code in (405, 404), f"POST {path} should be rejected"

    for path in [
        "/api/dashboard",
        "/api/runs",
        "/api/modules",
        "/api/rop/dashboard",
    ]:
        response = client.post(path)
        assert response.status_code in (405, 404), f"POST {path} should be rejected"


def test_venue_routes_not_published(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))

    for path in [
        "/venues/test",
        "/api/venues/test/dashboard",
    ]:
        response = client.get(path)
        assert response.status_code in (404, 503), f"{path} should not be published"


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


def _write_degraded_source_run(storage_dir: Path, run_id: str) -> Path:
    run_dir = _write_rich_rop_run(storage_dir, run_id)
    sd = {
        "selection_mode": "single_explicit",
        "status": "degraded",
        "aggregate": {
            "source_count": 1,
            "loaded_source_count": 0,
            "degraded_source_count": 1,
        },
        "sources": [
            {
                "source_id": "broken_source",
                "source_type": "mailbox_readonly",
                "source_role": "technical_aggregator",
                "source_display_name": "Broken Mailbox",
                "client_id": "welding",
                "authority": "read_only",
                "status": "degraded",
                "reason": "connection_timeout",
                "items_max": 20,
                "fetched_count": 0,
                "loaded_count": 0,
                "malformed_count": 0,
            }
        ],
    }
    (run_dir / "source_diagnostics.json").write_text(json.dumps(sd), encoding="utf-8")
    (run_dir / "classified_events.json").write_text("[]", encoding="utf-8")
    (run_dir / "normalized_events.json").write_text("[]", encoding="utf-8")
    return run_dir


def _write_fallback_run(storage_dir: Path, run_id: str) -> Path:
    run_dir = _write_rich_rop_run(storage_dir, run_id)
    classified = [
        {
            "event_id": "evt-fb-1",
            "source_id": "hotline_mailbox",
            "case_type": "new_lead",
            "priority": "medium",
            "confidence": 0.35,
            "is_fallback": True,
            "reason_code": "low_confidence_fallback",
        },
        {
            "event_id": "evt-fb-2",
            "source_id": "hotline_mailbox",
            "case_type": "existing_deal",
            "priority": "medium",
            "confidence": 0.42,
            "is_fallback": True,
            "reason_code": "ambiguous_classification",
        },
    ]
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified), encoding="utf-8"
    )
    return run_dir


def _write_high_priority_run(storage_dir: Path, run_id: str) -> Path:
    run_dir = _write_rich_rop_run(storage_dir, run_id)
    classified = [
        {
            "event_id": "evt-hp-1",
            "source_id": "hotline_mailbox",
            "case_type": "new_lead",
            "priority": "high",
            "confidence": 0.96,
            "is_fallback": False,
            "reason_code": "urgent_inquiry",
        },
        {
            "event_id": "evt-hp-2",
            "source_id": "hotline_mailbox",
            "case_type": "complaint",
            "priority": "high",
            "confidence": 0.92,
            "is_fallback": False,
            "reason_code": "customer_complaint",
        },
        {
            "event_id": "evt-hp-3",
            "source_id": "rop_batch_sample",
            "case_type": "new_lead",
            "priority": "high",
            "confidence": 0.88,
            "is_fallback": False,
            "reason_code": "new_contact_no_existing_lead",
        },
    ]
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified), encoding="utf-8"
    )
    return run_dir


def _write_missing_attachment_run(storage_dir: Path, run_id: str) -> Path:
    run_dir = _write_rich_rop_run(storage_dir, run_id)
    (run_dir / "attachment_extraction.json").unlink(missing_ok=True)
    return run_dir


def _write_html_artifact_values_run(storage_dir: Path, run_id: str) -> Path:
    run_dir = _write_rich_rop_run(storage_dir, run_id)
    classified = [
        {
            "event_id": "<script>alert('xss')</script>",
            "source_id": "<img src=x>",
            "case_type": "<b>bold</b>",
            "priority": "high",
            "confidence": 0.9,
            "is_fallback": False,
            "reason_code": "<a href='evil'>link</a>",
        },
    ]
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified), encoding="utf-8"
    )
    sd = json.loads((run_dir / "source_diagnostics.json").read_text(encoding="utf-8"))
    sd["sources"][0]["source_display_name"] = "<script>alert('display')</script>"
    sd["sources"][0]["status"] = "<script>alert('status')</script>"
    (run_dir / "source_diagnostics.json").write_text(json.dumps(sd), encoding="utf-8")
    return run_dir


def _write_malformed_json_artifact_run(storage_dir: Path, run_id: str) -> Path:
    run_dir = _write_rich_rop_run(storage_dir, run_id)
    (run_dir / "classified_events.json").write_text(
        "{invalid json!!!}", encoding="utf-8"
    )
    return run_dir


def test_rop_dashboard_api_rich_payload(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_rich_rop_run(storage_dir, "run-rich-001")
    client = _client(storage_dir)
    response = client.get("/api/rop/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["read_only"] is True
    payload = data["data"]
    assert payload["selected_run_id"] == "run-rich-001"
    assert "available_runs" in payload
    assert "kpis" in payload
    assert "funnel" in payload
    assert "source_health" in payload
    assert "classification_distribution" in payload
    assert "attachment_summary" in payload
    assert "recommendations" in payload
    assert "attention_events" in payload
    assert "evidence_links" in payload
    assert "warnings" in payload
    kpis = payload["kpis"]
    assert kpis["source_count"] == 2
    assert kpis["degraded_source_count"] == 1
    assert kpis["classified_count"] == 5
    assert kpis["high_priority_count"] == 2
    assert kpis["attachment_count"] == 6
    assert kpis["fallback_count"] == 1
    assert kpis["review_tsv_available"] is True


def test_rop_dashboard_source_health_degraded(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_degraded_source_run(storage_dir, "run-degraded-001")
    client = _client(storage_dir)
    response = client.get("/api/rop/dashboard")
    assert response.status_code == 200
    payload = response.json()["data"]
    sh = payload["source_health"]
    assert len(sh) == 1
    assert sh[0]["status"] == "degraded"
    assert sh[0]["reason"] == "connection_timeout"
    rec_codes = [r["code"] for r in payload["recommendations"]]
    assert "check_degraded_sources" in rec_codes


def test_rop_dashboard_attention_events_are_capped(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.read_model import ATTENTION_EVENTS_MAX

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rich_rop_run(storage_dir, "run-cap-001")
    many_events = []
    for i in range(ATTENTION_EVENTS_MAX + 10):
        many_events.append(
            {
                "event_id": f"evt-cap-{i:03d}",
                "source_id": "hotline_mailbox",
                "case_type": "new_lead",
                "priority": "low",
                "confidence": 0.5,
                "is_fallback": True,
                "reason_code": "test",
            }
        )
    (run_dir / "classified_events.json").write_text(
        json.dumps(many_events), encoding="utf-8"
    )
    client = _client(storage_dir)
    response = client.get("/api/rop/dashboard")
    assert response.status_code == 200
    events = response.json()["data"]["attention_events"]
    assert len(events) <= ATTENTION_EVENTS_MAX


def test_rop_dashboard_attachment_summary(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_rich_rop_run(storage_dir, "run-att-summary")
    client = _client(storage_dir)
    response = client.get("/api/rop/dashboard")
    assert response.status_code == 200
    att = response.json()["data"]["attachment_summary"]
    assert att["total_attachments"] == 6
    assert att["preview_available_count"] == 3
    assert att["refused_count"] == 2


def test_rop_dashboard_evidence_links_use_allowlist(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_rich_rop_run(storage_dir, "run-evidence-001")
    client = _client(storage_dir)
    response = client.get("/api/rop/dashboard")
    assert response.status_code == 200
    links = response.json()["data"]["evidence_links"]
    allowed = {
        "operator_summary_json",
        "source_diagnostics_json",
        "intake_metadata_json",
        "attachment_extraction_json",
        "attachment_manifest_json",
        "attachment_analysis_json",
        "normalized_events_json",
        "classified_events_json",
        "rop_review_table_tsv",
        "rop_current_state_json",
        "bitrix_reconciliation_json",
        "module_result_json",
        "rop_summary_result_json",
        "steps_json",
        "rop_mvp_pack_json",
        "rop_mvp_report_md",
        "mailbox_selection_json",
        "mail_thread_index_json",
        "mail_thread_context_json",
        "rop_ai_assist_requests_json",
        "rop_ai_assist_decisions_json",
        "rop_ai_assist_results_json",
        "rop_ai_adjudicator_requests_json",
        "rop_ai_adjudicator_decisions_json",
        "rop_ai_adjudicator_results_json",
        "rop_final_decisions_json",
    }
    link_ids = {l["artifact_id"] for l in links}
    assert link_ids == allowed
    available = [l for l in links if l["available"]]
    assert len(available) > 0


def test_rop_dashboard_includes_ai_adjudicator_summary(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rich_rop_run(storage_dir, "run-adj-001")
    adj_artifact = {
        "counters": {
            "adjudicator_enabled": 1,
            "adjudicator_eligible_count": 10,
            "adjudicator_used_count": 8,
            "adjudicator_degraded_count": 2,
        },
        "results": [
            {
                "event_id": "evt-001",
                "ai_used": True,
                "ai_status": "ok",
                "ai_confidence": 0.85,
                "final_case_type": "new_lead",
                "final_recommended_queue": "sales",
                "final_correct_action": "review_new_lead",
            },
            {
                "event_id": "evt-002",
                "ai_used": True,
                "ai_status": "low_confidence_preserve",
                "ai_confidence": 0.45,
                "deterministic_case_type": "existing_deal",
                "final_case_type": "existing_deal",
                "final_recommended_queue": "logistics",
                "final_correct_action": "attach_to_deal",
            },
        ],
    }
    (run_dir / "rop_ai_adjudicator_results.json").write_text(
        json.dumps(adj_artifact), encoding="utf-8"
    )
    client = _client(storage_dir)
    response = client.get("/api/rop/dashboard?run_id=run-adj-001")
    assert response.status_code == 200
    data = response.json()["data"]
    assert "ai_adjudicator_summary" in data
    adj_summary = data["ai_adjudicator_summary"]
    assert adj_summary["available"] is True
    assert adj_summary["total_events"] == 2
    assert adj_summary["ai_used_count"] == 2
    assert "final_decisions" in data
    assert "final_decision_summary" in data
    fds = data["final_decisions"]["summary"]
    assert fds["total_events"] > 0
    assert fds["attention_count"] == 4


def test_rop_dashboard_final_decisions_computed_projection(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rich_rop_run(storage_dir, "run-fd-001")
    adj_artifact = {
        "counters": {
            "adjudicator_enabled": 1,
            "adjudicator_eligible_count": 2,
            "adjudicator_used_count": 1,
        },
        "results": [
            {
                "event_id": "evt-001",
                "ai_used": True,
                "ai_status": "ok",
                "ai_confidence": 0.92,
                "final_case_type": "new_lead",
                "final_recommended_queue": "sales",
                "final_correct_action": "review_new_lead",
            },
            {
                "event_id": "evt-002",
                "ai_used": True,
                "ai_status": "manual_review_degrade",
                "ai_confidence": 0.30,
                "ai_reason": "conflict_signals_detected",
                "final_case_type": "existing_deal",
                "final_recommended_queue": "manual_review",
                "final_correct_action": "manual_review",
            },
        ],
    }
    (run_dir / "rop_ai_adjudicator_results.json").write_text(
        json.dumps(adj_artifact), encoding="utf-8"
    )
    client = _client(storage_dir)
    response = client.get("/api/rop/dashboard?run_id=run-fd-001")
    assert response.status_code == 200
    data = response.json()["data"]
    fds = data["final_decisions"]["summary"]
    assert fds["total_events"] == 5
    assert fds["attention_count"] == 4
    decisions = data["final_decisions"]["events"]
    evt1 = next((d for d in decisions if d["event_id"] == "evt-001"), None)
    assert evt1 is not None
    assert evt1["final_decision_source"] == "ai_adjudicator"
    assert evt1["automation_allowed"] is False
    assert evt1["bitrix_write_allowed"] is False
    evt2 = next((d for d in decisions if d["event_id"] == "evt-002"), None)
    assert evt2 is not None
    assert evt2["needs_attention"] is True
    assert evt2["automation_allowed"] is False
    assert evt2["bitrix_write_allowed"] is False
    for evt in decisions:
        if evt["event_id"] == "evt-001":
            continue
        assert evt["final_queue"] == "unresolved"
        assert evt["final_action"] == "no_action"
        assert evt["needs_attention"] is True
        assert evt["automation_allowed"] is False
        assert evt["bitrix_write_allowed"] is False


def test_build_final_decisions_artifact_policy(tmp_path: Path) -> None:
    from beeagent_module.core.rop_final_decision import build_final_decisions

    events = [
        {
            "event_id": "e1",
            "case_type": "new_lead",
            "recommended_queue": "sales",
            "correct_action": "review_new_lead",
            "confidence": 0.85,
            "sender": "a@b.com",
            "subject": "Inquiry",
        },
        {
            "event_id": "e2",
            "case_type": "existing_deal",
            "recommended_queue": "logistics",
            "correct_action": "attach_to_deal",
            "confidence": 0.60,
            "sender": "b@c.com",
            "subject": "Re: Order",
        },
        {
            "event_id": "e3",
            "case_type": "irrelevant",
            "recommended_queue": "ignore",
            "correct_action": "ignore",
            "confidence": 0.95,
            "sender": "noreply@m.com",
            "subject": "Newsletter",
        },
    ]
    adj_results = [
        {
            "event_id": "e1",
            "ai_status": "ok",
            "ai_confidence": 0.92,
            "final_case_type": "new_lead",
            "final_recommended_queue": "tender",
            "final_correct_action": "review_tender",
        },
        {
            "event_id": "e2",
            "ai_status": "deterministic_preserved",
            "ai_reason": "conflict_signals_detected",
            "merge_reason": "ai_output_conflict_deterministic_result_preserved",
            "ai_evidence_codes": [
                "low_signal",
                "marketing_conflict",
                "spam_rfq_conflict",
                "supplier_outreach",
                "ambiguous_bitrix",
                "not_allowed",
            ],
            "ai_confidence": 0.35,
            "final_case_type": "existing_deal",
            "final_recommended_queue": "procurement",
            "final_correct_action": "check_bitrix",
        },
    ]

    artifact = build_final_decisions(events, adj_results)
    assert "summary" in artifact
    assert "events" in artifact
    assert artifact["summary"]["total_events"] == 3
    assert artifact["summary"]["attention_count"] == 1
    assert artifact["summary"]["decision_source_counts"]["ai_adjudicator"] == 1
    assert artifact["summary"]["decision_source_counts"]["deterministic_preserved"] == 1

    decisions = {d["event_id"]: d for d in artifact["events"]}

    e1 = decisions["e1"]
    assert e1["final_decision_source"] == "ai_adjudicator"
    assert e1["final_case_type"] == "new_lead"
    assert e1["final_queue"] == "tender"
    assert e1["final_action"] == "review_tender"
    assert e1["needs_attention"] is False
    assert e1["automation_allowed"] is False
    assert e1["bitrix_write_allowed"] is False

    e2 = decisions["e2"]
    assert e2["final_decision_source"] == "deterministic_preserved"
    assert e2["needs_attention"] is True
    assert e2["attention_reason"] == "ai_output_conflict_deterministic_result_preserved"
    assert e2["attention_reason_code"] == (
        "ai_output_conflict_deterministic_result_preserved"
    )
    assert e2["attention_evidence_codes"] == [
        "low_signal",
        "marketing_conflict",
        "spam_rfq_conflict",
        "supplier_outreach",
        "ambiguous_bitrix",
    ]
    assert e2["final_queue"] == "logistics"
    assert e2["final_action"] == "attach_to_deal"
    assert e2["automation_allowed"] is False
    assert e2["bitrix_write_allowed"] is False

    e3 = decisions["e3"]
    assert e3["final_decision_source"] == "deterministic"
    assert e3["needs_attention"] is False
    assert e3["automation_allowed"] is False
    assert e3["bitrix_write_allowed"] is False


def test_build_final_decisions_uses_safe_attention_reason_code() -> None:
    from beeagent_module.core.rop_final_decision import build_final_decisions

    raw_reason = "<script>oversized-attention</script>" + "x" * 700
    artifact = build_final_decisions(
        [
            {
                "event_id": "e1",
                "case_type": "unknown",
                "recommended_queue": "manual_review",
                "correct_action": "manual_review",
                "confidence": 0.0,
            }
        ],
        [
            {
                "event_id": "e1",
                "ai_status": "deterministic_preserved",
                "ai_reason": raw_reason,
                "merge_reason": "ai_output_conflict_deterministic_result_preserved",
            }
        ],
    )

    decision = artifact["events"][0]
    assert decision["attention_reason"] == (
        "ai_output_conflict_deterministic_result_preserved"
    )
    assert decision["attention_reason_code"] == (
        "ai_output_conflict_deterministic_result_preserved"
    )
    assert raw_reason not in decision["attention_reason"]


def test_dashboard_prefers_final_decisions_artifact(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rich_rop_run(storage_dir, "run-fd-artifact")
    artifact = {
        "summary": {
            "total_events": 1,
            "decision_source_counts": {"artifact": 1},
            "attention_count": 0,
        },
        "events": [
            {
                "event_id": "evt-artifact",
                "final_case_type": "irrelevant",
                "final_case_subtype": None,
                "final_queue": "ignore",
                "final_action": "ignore",
                "final_decision_source": "artifact",
                "final_confidence": 0.99,
                "needs_attention": False,
                "attention_reason": None,
                "automation_allowed": False,
                "bitrix_write_allowed": False,
            }
        ],
    }
    (run_dir / "rop_final_decisions.json").write_text(
        json.dumps(artifact), encoding="utf-8"
    )

    data = build_rop_dashboard_read_model(storage_dir, "run-fd-artifact")

    assert data["final_decisions"] == artifact
    assert "final_decisions_artifact" not in data


def test_unsafe_final_decisions_artifact_uses_computed_projection(
    tmp_path: Path,
) -> None:
    from beeagent_module.core.rop_final_decision import load_or_build_final_decisions

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-fd-unsafe")
    unsafe_artifact = {
        "summary": {
            "total_events": 1,
            "decision_source_counts": {"deterministic": 1},
            "attention_count": 0,
        },
        "events": [
            {
                "event_id": "evt-1",
                "final_case_type": "new_lead",
                "final_case_subtype": None,
                "final_queue": "high_priority",
                "final_action": "review",
                "final_decision_source": "deterministic",
                "final_confidence": 0.95,
                "needs_attention": False,
                "attention_reason": None,
                "automation_allowed": True,
                "bitrix_write_allowed": False,
            }
        ],
    }
    (run_dir / "rop_final_decisions.json").write_text(
        json.dumps(unsafe_artifact), encoding="utf-8"
    )

    final_decisions, source = load_or_build_final_decisions(run_dir)

    assert source == "computed"
    assert final_decisions["events"][0]["automation_allowed"] is False
    assert final_decisions["events"][0]["bitrix_write_allowed"] is False


def test_oversized_final_attention_reason_uses_bounded_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.rop_final_decision import load_or_build_final_decisions

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-fd-oversized")
    marker = "<script>OVERSIZED-ATTENTION-MARKER</script>" + "x" * 700
    artifact = {
        "summary": {
            "total_events": 1,
            "decision_source_counts": {"legacy": 1},
            "attention_count": 1,
        },
        "events": [
            {
                "event_id": "evt-1",
                "final_case_type": "new_lead",
                "final_case_subtype": None,
                "final_queue": "manual_review",
                "final_action": "manual_review",
                "final_decision_source": "legacy",
                "final_confidence": 0.0,
                "needs_attention": True,
                "attention_reason": marker,
                "attention_reason_code": "unknown_final_attention_code",
                "automation_allowed": False,
                "bitrix_write_allowed": False,
            }
        ],
    }
    artifact_path = run_dir / "rop_final_decisions.json"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    before = (
        sha256(artifact_path.read_bytes()).hexdigest(),
        artifact_path.stat().st_mtime_ns,
    )
    settings = _build_settings()
    settings["bitrix"] = {
        "widget": {
            "enabled": True,
            "token_env": "BITRIX_ROP_WIDGET_TOKEN",
            "default_period": "7d",
            "max_items": 50,
        }
    }
    monkeypatch.setenv("BITRIX_ROP_WIDGET_TOKEN", "widget-token")
    client = _client(storage_dir, settings=settings)

    api_response = client.get("/api/rop/events/evt-1?run_id=run-fd-oversized&lang=en")
    html_response = client.get("/rop/events/evt-1?run_id=run-fd-oversized&lang=en")
    widget_response = client.get(
        "/api/bitrix/rop/widget",
        params={"run_id": "run-fd-oversized"},
        headers={"Authorization": "Bearer widget-token"},
    )
    final_decisions, source = load_or_build_final_decisions(run_dir)
    after = (
        sha256(artifact_path.read_bytes()).hexdigest(),
        artifact_path.stat().st_mtime_ns,
    )

    assert api_response.status_code == 200
    assert html_response.status_code == 200
    assert widget_response.status_code == 200
    assert source == "computed"
    assert marker not in api_response.text
    assert marker not in html_response.text
    assert after == before
    assert final_decisions["events"][0]["attention_reason"] is None
    assert all(
        event["attention_reason"] is None or len(event["attention_reason"]) <= 600
        for event in widget_response.json()["data"]["final_decisions"]["events"]
    )


def test_dashboard_rejects_final_decisions_artifact_with_unexpected_fields(
    tmp_path: Path,
) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-fd-extra-field")
    marker = "RAW-EML-MARKER"
    artifact = {
        "summary": {
            "total_events": 1,
            "decision_source_counts": {"deterministic": 1},
            "attention_count": 0,
        },
        "events": [
            {
                "event_id": "evt-1",
                "final_case_type": "new_lead",
                "final_case_subtype": None,
                "final_queue": "high_priority",
                "final_action": "review",
                "final_decision_source": "deterministic",
                "final_confidence": 0.95,
                "needs_attention": False,
                "attention_reason": None,
                "automation_allowed": False,
                "bitrix_write_allowed": False,
                "raw_eml": marker,
            }
        ],
    }
    (run_dir / "rop_final_decisions.json").write_text(
        json.dumps(artifact), encoding="utf-8"
    )
    client = _client(storage_dir)

    response = client.get("/api/rop/dashboard?run_id=run-fd-extra-field")

    assert response.status_code == 200
    data = response.json()["data"]
    assert marker not in json.dumps(data["final_decisions"])
    assert any(
        warning.get("code") == "missing_or_malformed_artifact"
        for warning in data["warnings"]
    )


def test_dashboard_drops_unsafe_nested_duplicate_evidence(tmp_path: Path) -> None:
    from beeagent_module.core.rop_final_decision import (
        _is_final_decisions_payload,
        build_final_decisions,
        load_or_build_final_decisions,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-fd-nested-unsafe")
    base_classification = {
        "case_type": "new_lead",
        "priority": "high",
        "reason_code": "new_lead_request_signal",
        "confidence": 0.95,
        "reasoning": "base classification",
        "is_fallback": False,
        "case_subtype": "new_lead_rfq",
        "recommended_queue": "high_priority",
        "should_rop_see": True,
        "correct_action": "review",
    }
    duplicate = {
        "is_duplicate": True,
        "confidence": 0.99,
        "reason_code": "exact_email_body_match",
        "reason_path": ["body_exact"],
        "reasoning": "duplicate evidence",
        "candidate": {
            "existing_lead_id": "evt-original",
            "event_id": "evt-original",
            "similarity_score": 0.99,
            "matched_fields": ["body"],
            "reason_code": "exact_email_body_match",
            "reason_path": ["body_exact"],
            "reasoning": "exact match",
        },
        "candidates": [],
        "is_fallback": False,
    }
    classified = json.loads(
        (run_dir / "classified_events.json").read_text(encoding="utf-8")
    )
    classified[0]["base_classification"] = {
        **base_classification,
        "raw_eml": "CLASSIFIED-RAW-EML-MARKER",
    }
    classified[0]["duplicate"] = {
        **duplicate,
        "candidate": {
            **duplicate["candidate"],
            "secret": "CLASSIFIED-SECRET-MARKER",
        },
    }
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified), encoding="utf-8"
    )

    safe_event = {
        **classified[0],
        "base_classification": base_classification,
        "duplicate": duplicate,
    }
    safe_final = build_final_decisions([safe_event], None)
    assert _is_final_decisions_payload(safe_final) is True

    invalid_confidence = json.loads(json.dumps(safe_final))
    invalid_confidence["events"][0]["duplicate"]["confidence"] = 1.01
    assert _is_final_decisions_payload(invalid_confidence) is False

    too_many_candidates = json.loads(json.dumps(safe_final))
    too_many_candidates["events"][0]["duplicate"]["candidates"] = [
        duplicate["candidate"],
        duplicate["candidate"],
    ]
    assert _is_final_decisions_payload(too_many_candidates) is False

    unsafe_final = json.loads(json.dumps(safe_final))
    unsafe_final["events"][0]["base_classification"]["raw_eml"] = "FINAL-RAW-EML-MARKER"
    unsafe_final["events"][0]["duplicate"]["candidate"]["secret"] = (
        "FINAL-SECRET-MARKER"
    )
    (run_dir / "rop_final_decisions.json").write_text(
        json.dumps(unsafe_final), encoding="utf-8"
    )

    final_decisions, source = load_or_build_final_decisions(run_dir)
    response = _client(storage_dir).get(
        "/api/rop/dashboard?run_id=run-fd-nested-unsafe"
    )

    assert source == "computed"
    assert final_decisions["events"][0]["base_classification"] is None
    assert final_decisions["events"][0]["duplicate"] is None
    assert response.status_code == 200
    rendered = json.dumps(response.json()["data"])
    assert "CLASSIFIED-RAW-EML-MARKER" not in rendered
    assert "CLASSIFIED-SECRET-MARKER" not in rendered
    assert "FINAL-RAW-EML-MARKER" not in rendered
    assert "FINAL-SECRET-MARKER" not in rendered
    assert any(
        warning.get("code") == "missing_or_malformed_artifact"
        for warning in response.json()["data"]["warnings"]
    )


def test_recommendations_layout_enforces_read_only_execution_policy() -> None:
    from beeagent_module.interfaces.ui.read_model import (
        _build_rop_recommendations_layout,
    )

    layout = _build_rop_recommendations_layout(
        {
            "run_id": "run-recommendation-policy",
            "delivery_recommendations": {
                "aggregate": {},
                "items": [
                    {
                        "event_id": "evt-1",
                        "recommended_action": "create_lead_draft",
                        "safe_to_execute": True,
                        "requires_human_confirmation": False,
                    }
                ],
            },
        }
    )

    table = next(
        block for block in layout if block.get("title") == "Recommendation Items"
    )
    assert table["rows"][0]["safe"] == "No"
    assert table["rows"][0]["confirm"] == "Yes"


def test_ai_adjudicator_layout_precedes_final_and_hides_empty_legacy() -> None:
    data = {
        "ai_assist_summary": {
            "evidence_available": True,
            "request_count": 0,
            "decision_count": 0,
            "result_count": 0,
            "status_counts": {},
        },
        "ai_assist_events": [],
        "ai_adjudicator_summary": {
            "available": True,
            "eligible_count": 1,
            "used_count": 1,
            "degraded_count": 0,
            "total_events": 1,
            "status_counts": {"ok": 1},
        },
        "final_decisions": {
            "summary": {
                "total_events": 1,
                "decision_source_counts": {"ai_adjudicator": 1},
                "attention_count": 0,
            },
            "events": [],
        },
    }

    layout = build_rop_page_layout(data, tab="ai_assist")
    titles = [block.get("title") for block in layout]

    assert titles[:3] == [
        "AI Adjudicator Summary",
        "AI Adjudicator Status Breakdown",
        "Final Decisions",
    ]
    assert "AI Assist Summary" not in titles
    assert "AI Events" not in titles


def test_deterministic_final_decisions_render_without_ai_activity() -> None:
    data = {
        "ai_assist_summary": {},
        "ai_assist_events": [],
        "ai_adjudicator_summary": {"available": False},
        "final_decisions": {
            "summary": {
                "total_events": 1,
                "decision_source_counts": {"deterministic": 1},
                "attention_count": 0,
            },
            "events": [],
        },
    }

    layout = build_rop_page_layout(data, tab="ai_assist")

    assert [block.get("title") for block in layout] == ["Final Decisions"]


def test_rop_event_detail_ru_localizes_ui8_labels(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-detail-ru-ui8")
    (run_dir / "rop_ai_adjudicator_results.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "event_id": "evt-1",
                        "ai_used": True,
                        "ai_status": "manual_review_degrade",
                        "ai_confidence": 0.3,
                        "ai_reason": "review needed",
                        "final_case_type": "new_lead",
                        "final_recommended_queue": "manual_review",
                        "final_correct_action": "manual_review",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    client = _client(storage_dir)

    response = client.get("/rop/events/evt-1?run_id=run-detail-ru-ui8&lang=ru")

    assert response.status_code == 200
    for label in (
        "Использован",
        "Статус",
        "Уверенность",
        "Причина",
        "Тип",
        "Очередь",
        "Действие",
    ):
        assert label in response.text
    for label in (
        "AI арбитр использован",
        "Статус AI арбитра",
        "Уверенность AI арбитра",
        "Причина AI арбитра",
        "Предложенный AI тип",
        "Предложенная AI очередь",
        "Предложенное AI действие",
    ):
        assert label not in response.text
    assert "Причина внимания" in response.text
    assert "AI adjudicator status" not in response.text
    assert "AI proposed queue" not in response.text
    assert "Attention reason" not in response.text
    client.close()


def test_rop_event_detail_without_attention_omits_attention_reason(
    tmp_path: Path,
) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(
        storage_dir,
        "run-detail-no-attention",
    )
    before = {
        path: (sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        for path in run_dir.rglob("*")
        if path.is_file()
    }
    data = build_rop_event_detail_read_model(
        storage_dir,
        "run-detail-no-attention",
        "evt-1",
        lang="ru",
    )
    page = build_rop_event_detail_page_model(
        storage_dir,
        "run-detail-no-attention",
        "evt-1",
        lang="ru",
    )
    after = {
        path: (sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        for path in run_dir.rglob("*")
        if path.is_file()
    }

    assert data["final_decision"]["needs_attention"] is False
    assert data["final_decision"]["attention_reason_code"] is None
    assert data["final_decision"]["attention_reason_display"] is None
    assert not any(
        "attention reason code" in warning.lower()
        or "код причины внимания" in warning.lower()
        for warning in data["warnings"]
    )
    final_items = _find_section_items(page, "Итоговое решение")
    assert _item_by_label(final_items, "Причина внимания") == {}
    assert after == before


def test_rop_event_detail_builds_deterministic_final_decision_and_evidence(
    tmp_path: Path,
) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-detail-final")
    (run_dir / "rop_ai_adjudicator_results.json").write_text(
        json.dumps({"results": []}), encoding="utf-8"
    )
    (run_dir / "rop_final_decisions.json").write_text(json.dumps({}), encoding="utf-8")

    data = build_rop_event_detail_read_model(storage_dir, "run-detail-final", "evt-1")

    final_decision = data["final_decision"]
    assert final_decision["event_id"] == "evt-1"
    assert final_decision["final_decision_source"] == "deterministic"
    availability = {
        item["artifact_id"]: item["available"] for item in data["evidence_links"]
    }
    assert availability["rop_ai_adjudicator_results_json"] is True
    assert availability["rop_final_decisions_json"] is True


def test_rop_event_detail_exposes_deterministic_and_conversation_sections(
    tmp_path: Path,
) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-detail-conv")
    classified_path = run_dir / "classified_events.json"
    classified = json.loads(classified_path.read_text(encoding="utf-8"))
    classified[0].update(
        {
            "deterministic_case_type": "new_lead",
            "deterministic_case_subtype": "new_lead_rfq",
            "deterministic_recommended_queue": "sales",
            "deterministic_correct_action": "review_new_lead",
            "deterministic_confidence": 0.88,
            "deterministic_reason_code": "new_lead_request_signal",
        }
    )
    classified_path.write_text(json.dumps(classified), encoding="utf-8")

    state = {
        "events": {
            "welding|hotline_mailbox|msg-a|": {
                "event_id": "evt-1",
                "event_instance_id": "event-000001",
                "client_id": "welding",
                "source_id": "hotline_mailbox",
                "message_id": "msg-a",
                "in_reply_to": "",
                "references": "",
                "sender_email": "client@example.com",
                "subject": "Need welding quote",
                "case_type": "new_lead",
                "outcome": "create_lead",
                "status": "created",
                "target_entity_type": "lead",
                "target_entity_id": 1001,
                "target_provenance": "beeagent_created",
                "last_run_id": "run-detail-conv",
                "created_at_utc": "2026-08-01T10:00:00Z",
            },
            "welding|other_mailbox|msg-b|": {
                "event_id": "evt-2",
                "event_instance_id": "event-000001",
                "client_id": "welding",
                "source_id": "other_mailbox",
                "message_id": "msg-b",
                "in_reply_to": "msg-a",
                "references": "msg-a",
                "sender_email": "client@example.com",
                "subject": "Re: Need welding quote",
                "case_type": "existing_deal",
                "outcome": "attach_existing",
                "status": "attached",
                "target_entity_type": "lead",
                "target_entity_id": 1001,
                "target_provenance": "thread_resolved",
                "last_run_id": "run-other",
                "created_at_utc": "2026-08-02T10:00:00Z",
            },
        }
    }
    (storage_dir / "interfaces").mkdir(parents=True, exist_ok=True)
    (storage_dir / "interfaces" / "rop_writeback_state.json").write_text(
        json.dumps(state), encoding="utf-8"
    )

    data = build_rop_event_detail_read_model(
        storage_dir, "run-detail-conv", "evt-1", event_instance_id="event-000001"
    )

    deterministic = data["deterministic"]
    assert deterministic["available"] is True
    assert deterministic["case_type"] == "new_lead"
    assert deterministic["recommended_queue"] == "sales"
    assert deterministic["correct_action"] == "review_new_lead"
    assert deterministic["confidence"] == 0.88
    assert deterministic["reason_code"] == "new_lead_request_signal"

    conversation = data["conversation"]
    assert conversation["available"] is True
    assert conversation["client_id"] == "welding"
    events = {item["event_id"]: item for item in conversation["events"]}
    assert events["evt-1"]["source_id"] == "hotline_mailbox"
    assert events["evt-2"]["source_id"] == "other_mailbox"
    assert events["evt-2"]["role"] == "reply"
    assert events["evt-2"]["writeback"]["outcome"] == "attach_existing"


def test_rop_event_detail_trusted_attach_projects_operational_final(
    tmp_path: Path,
) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-detail-op")
    state = {
        "events": {
            "welding|hotline_mailbox|msg-a|": {
                "event_id": "evt-1",
                "event_instance_id": "",
                "client_id": "welding",
                "source_id": "hotline_mailbox",
                "message_id": "msg-a",
                "in_reply_to": "msg-root",
                "references": "msg-root",
                "sender_email": "client@example.com",
                "subject": "Re: Need welding quote",
                "case_type": "existing_deal",
                "semantic_case_type": "new_lead",
                "outcome": "attach_existing",
                "status": "attached",
                "target_entity_type": "lead",
                "target_entity_id": 1001,
                "target_provenance": "thread_resolved",
                "last_run_id": "run-detail-op",
                "created_at_utc": "2026-08-02T10:00:00Z",
            },
        }
    }
    (storage_dir / "interfaces").mkdir(parents=True, exist_ok=True)
    (storage_dir / "interfaces" / "rop_writeback_state.json").write_text(
        json.dumps(state), encoding="utf-8"
    )

    data = build_rop_event_detail_read_model(storage_dir, "run-detail-op", "evt-1")

    final_decision = data["final_decision"]
    assert final_decision["final_case_type"] == "existing_deal"
    assert final_decision["semantic_case_type"] == "new_lead"
    conversation = data["conversation"]
    conv_event = next(
        item for item in conversation["events"] if item["event_id"] == "evt-1"
    )
    assert conv_event["case_type"] == "existing_deal"
    assert conv_event["semantic_case_type"] == "new_lead"


def test_rop_event_detail_independent_event_keeps_semantic_final(
    tmp_path: Path,
) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-detail-ind")

    data = build_rop_event_detail_read_model(storage_dir, "run-detail-ind", "evt-1")

    final_decision = data["final_decision"]
    assert final_decision["final_case_type"] == "new_lead"
    assert "semantic_case_type" not in final_decision


def test_rop_event_detail_deterministic_shows_original_not_current(
    tmp_path: Path,
) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-detail-det-split")
    classified_path = run_dir / "classified_events.json"
    classified = json.loads(classified_path.read_text(encoding="utf-8"))
    classified[0]["case_type"] = "existing_deal"
    classified[0]["recommended_queue"] = "procurement"
    classified[0]["correct_action"] = "check_bitrix"
    classified[0]["reason_code"] = "post_ai_reason"
    classified[0].update(
        {
            "deterministic_case_type": "new_lead",
            "deterministic_case_subtype": "new_lead_rfq",
            "deterministic_recommended_queue": "sales",
            "deterministic_correct_action": "review_new_lead",
            "deterministic_confidence": 0.9,
            "deterministic_reason_code": "new_lead_request_signal",
        }
    )
    classified_path.write_text(json.dumps(classified), encoding="utf-8")

    data = build_rop_event_detail_read_model(
        storage_dir, "run-detail-det-split", "evt-1"
    )
    deterministic = data["deterministic"]
    assert deterministic["available"] is True
    assert deterministic["case_type"] == "new_lead"
    assert deterministic["recommended_queue"] == "sales"
    assert deterministic["correct_action"] == "review_new_lead"
    assert deterministic["reason_code"] == "new_lead_request_signal"
    assert deterministic["case_type"] != "existing_deal"
    assert deterministic["recommended_queue"] != "procurement"
    assert deterministic["correct_action"] != "check_bitrix"


def test_rop_event_detail_without_deterministic_evidence_is_not_available(
    tmp_path: Path,
) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-detail-no-det")
    data = build_rop_event_detail_read_model(storage_dir, "run-detail-no-det", "evt-1")
    deterministic = data["deterministic"]
    assert deterministic == {"available": False}
    assert "case_type" not in deterministic
    assert "recommended_queue" not in deterministic
    assert "correct_action" not in deterministic
    assert "reason_code" not in deterministic


def test_rop_event_detail_deterministic_ai_and_final_are_separate(
    tmp_path: Path,
) -> None:
    from beeagent_module.core.rop_final_decision import build_final_decisions
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-detail-det-ai-final")
    classified_path = run_dir / "classified_events.json"
    classified = json.loads(classified_path.read_text(encoding="utf-8"))
    classified[0]["event_instance_id"] = "event-000001"
    classified[0].update(
        {
            "deterministic_case_type": "new_lead",
            "deterministic_case_subtype": "new_lead_rfq",
            "deterministic_recommended_queue": "sales",
            "deterministic_correct_action": "review_new_lead",
            "deterministic_confidence": 0.7,
            "deterministic_reason_code": "new_lead_request_signal",
        }
    )
    classified_path.write_text(json.dumps(classified), encoding="utf-8")

    adjudicator = {
        "results": [
            {
                "event_id": "evt-1",
                "event_instance_id": "event-000001",
                "ai_used": True,
                "ai_status": "ok",
                "ai_confidence": 0.92,
                "ai_reason": "AI proposal reason",
                "ai_reason_code": "customer_request_detected",
                "ai_evidence_codes": ["low_signal"],
                "merge_reason": "validated_ai_adjudicator_output",
                "final_case_type": "new_lead",
                "final_recommended_queue": "sales",
                "final_correct_action": "review_new_lead",
            }
        ]
    }
    (run_dir / "rop_ai_adjudicator_results.json").write_text(
        json.dumps(adjudicator), encoding="utf-8"
    )
    final_decisions = build_final_decisions(classified, adjudicator)
    (run_dir / "rop_final_decisions.json").write_text(
        json.dumps(final_decisions), encoding="utf-8"
    )

    data = build_rop_event_detail_read_model(
        storage_dir,
        "run-detail-det-ai-final",
        "evt-1",
        event_instance_id="event-000001",
    )
    deterministic = data["deterministic"]
    ai_adjudicator = data["ai_adjudicator"]
    final_decision = data["final_decision"]
    assert deterministic["available"] is True
    assert deterministic["case_type"] == "new_lead"
    assert ai_adjudicator["ai_adjudicator_used"] is True
    assert ai_adjudicator["ai_adjudicator_status"] == "ok"
    assert final_decision["final_case_type"] == "new_lead"
    assert final_decision["final_decision_source"] == "ai_adjudicator"


def test_rop_event_detail_new_lead_and_bitrix_candidate_are_distinct(
    tmp_path: Path,
) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-detail-dup-cand")
    (run_dir / "bitrix_reconciliation.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "event_id": "evt-1",
                        "bitrix_match_status": "duplicate_candidate",
                        "bitrix_match_quality": "duplicate",
                        "candidate_count": 2,
                        "safe_to_use_as_target": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    data = build_rop_event_detail_read_model(
        storage_dir,
        "run-detail-dup-cand",
        "evt-1",
        event_instance_id="",
    )
    final_decision = data["final_decision"]
    bitrix = data["bitrix"]
    assert final_decision["final_case_type"] == "new_lead"
    assert bitrix["available"] is True
    assert bitrix["bitrix_status"] == "duplicate_candidate"
    assert bitrix["candidate_count"] == 2
    assert bitrix["bitrix_status"] != final_decision["final_case_type"]


def test_rop_event_detail_exposes_recipient_routing_section(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-detail-routing")
    (run_dir / "rop_recipient_routing.json").write_text(
        json.dumps(
            {
                "run_id": "run-detail-routing",
                "status": "ok",
                "read_only": True,
                "draft_only": True,
                "directory": {"status": "loaded", "reason": None},
                "items": [
                    {
                        "event_id": "evt-1",
                        "event_instance_id": "event-000001",
                        "source_id": "hotline_mailbox",
                        "recipient": "boss@welding.kz",
                        "recipient_candidates": ["boss@welding.kz"],
                        "recipient_evidence_source": "to",
                        "recipient_status": "resolved",
                        "responsible": {
                            "status": "matched",
                            "user_id": 12,
                            "name": "Ivan Petrov",
                            "email": "boss@welding.kz",
                            "reason": None,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    data = build_rop_event_detail_read_model(storage_dir, "run-detail-routing", "evt-1")
    routing = data["recipient_routing"]
    assert routing["available"] is True
    assert routing["recipient"] == "boss@welding.kz"
    assert routing["recipient_evidence_source"] == "to"
    assert routing["recipient_status"] == "resolved"
    assert routing["proposed_responsible_user_id"] == 12
    assert routing["proposed_responsible_name"] == "Ivan Petrov"
    assert routing["responsible_status"] == "matched"
    availability = {
        item["artifact_id"]: item["available"] for item in data["evidence_links"]
    }
    assert availability["rop_recipient_routing_json"] is True

    page = build_rop_event_detail_page_model(storage_dir, "run-detail-routing", "evt-1")
    section_titles = [section.get("title") for section in page["sections"]]
    assert "Recipient routing" in section_titles


def test_rop_event_detail_recipient_routing_absent_is_safe(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-detail-no-routing")
    data = build_rop_event_detail_read_model(
        storage_dir, "run-detail-no-routing", "evt-1"
    )
    assert data["recipient_routing"]["available"] is False


def test_event_detail_joins_occurrence_evidence_by_event_instance_id(
    tmp_path: Path,
) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-detail-occurrence")
    event_id = "evt-shared"
    instances = ("event-000001", "event-000002")
    (run_dir / "normalized_events.json").write_text(
        json.dumps(
            [
                {
                    "event_id": event_id,
                    "event_instance_id": instance_id,
                    "source_id": "hotline_mailbox",
                    "subject": instance_id,
                }
                for instance_id in instances
            ]
        ),
        encoding="utf-8",
    )
    (run_dir / "classified_events.json").write_text(
        json.dumps(
            [
                {
                    "event_id": event_id,
                    "event_instance_id": instance_id,
                    "case_type": "new_lead",
                }
                for instance_id in instances
            ]
        ),
        encoding="utf-8",
    )
    (run_dir / "bitrix_reconciliation.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "event_id": event_id,
                        "event_instance_id": instance_id,
                        "bitrix_match_status": f"matched_{index}",
                    }
                    for index, instance_id in enumerate(instances, start=1)
                ]
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "rop_action_drafts.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "event_id": event_id,
                        "event_instance_id": instance_id,
                        "action_type": f"draft_{index}",
                    }
                    for index, instance_id in enumerate(instances, start=1)
                ]
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "rop_recipient_routing.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "event_id": event_id,
                        "event_instance_id": instance_id,
                        "recipient": f"recipient{index}@welding.kz",
                        "recipient_status": "resolved",
                        "responsible": {
                            "status": "matched",
                            "user_id": index,
                        },
                    }
                    for index, instance_id in enumerate(instances, start=1)
                ]
            }
        ),
        encoding="utf-8",
    )

    data = build_rop_event_detail_read_model(
        storage_dir,
        "run-detail-occurrence",
        event_id,
        event_instance_id="event-000002",
    )

    assert data["bitrix"]["bitrix_status"] == "matched_2"
    assert data["action_draft"]["action_type"] == "draft_2"
    assert data["recipient_routing"]["recipient"] == "recipient2@welding.kz"
    assert data["recipient_routing"]["proposed_responsible_user_id"] == 2


def test_rop_event_detail_exposes_duplicate_evidence(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-detail-dup")
    classified = [
        {
            "event_id": "evt-1",
            "source_id": "hotline_mailbox",
            "client_id": "welding",
            "sender": "client@example.com",
            "subject": "Need welding quote",
            "case_type": "duplicate",
            "priority": "medium",
            "confidence": 0.99,
            "reason_code": "duplicate_candidate_confirmed",
            "recommended_queue": "manual_review",
            "correct_action": "review",
            "should_rop_see": True,
            "is_fallback": False,
            "base_classification": {
                "case_type": "new_lead",
                "priority": "high",
                "reason_code": "new_lead_request_signal",
                "confidence": 0.9,
                "reasoning": "base",
                "is_fallback": False,
                "case_subtype": "rfq",
                "recommended_queue": "sales",
                "should_rop_see": True,
                "correct_action": "review_new_lead",
            },
            "duplicate": {
                "is_duplicate": True,
                "confidence": 0.99,
                "reason_code": "exact_email_body_match",
                "reason_path": ["sender_email_exact", "body_exact"],
                "reasoning": "exact duplicate matched",
                "candidate": {
                    "existing_lead_id": "evt-original",
                    "event_id": "evt-original",
                    "similarity_score": 0.99,
                    "matched_fields": ["sender_email", "body"],
                    "reason_code": "exact_email_body_match",
                    "reason_path": ["sender_email_exact", "body_exact"],
                    "reasoning": "exact duplicate matched",
                },
                "candidates": [],
                "is_fallback": False,
            },
        }
    ]
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified), encoding="utf-8"
    )

    data = build_rop_event_detail_read_model(storage_dir, "run-detail-dup", "evt-1")

    classification = data["classification"]
    assert classification["case_type"] == "duplicate"
    assert classification["base_case_type"] == "new_lead"
    duplicate = classification["duplicate"]
    assert duplicate["is_duplicate"] is True
    assert duplicate["candidate_event_id"] == "evt-original"
    assert duplicate["existing_lead_id"] == "evt-original"
    assert duplicate["confidence"] == 0.99
    assert duplicate["reason_code"] == "exact_email_body_match"
    assert duplicate["reason_path"] == ["sender_email_exact", "body_exact"]
    assert duplicate["matched_fields"] == ["sender_email", "body"]
    assert duplicate["similarity_score"] == 0.99
    assert classification["reason_display"] is not None

    page = build_rop_event_detail_page_model(storage_dir, "run-detail-dup", "evt-1")
    items = _find_section_items(page, "Classification")
    assert _item_by_label(items, "Base case type")["value"] == "New lead"
    assert _item_by_label(items, "Duplicate candidate event")["value"] == "evt-original"
    assert _item_by_label(items, "Duplicate confidence")["value"] == 0.99
    assert _item_by_label(items, "Duplicate reason code")["value"] == (
        "exact_email_body_match"
    )

    client = _client(storage_dir)
    response = client.get("/rop/events/evt-1?run_id=run-detail-dup")

    assert response.status_code == 200
    assert "evt-original" in response.text
    assert "exact_email_body_match" in response.text
    assert "exact duplicate matched" in response.text


def test_rop_filter_options_include_duplicate_when_rows_present() -> None:
    from beeagent_module.interfaces.ui.read_model import _build_filter_options

    options = _build_filter_options(
        [
            {"event_id": "a", "case_type": "new_lead", "priority": "high"},
            {"event_id": "b", "case_type": "duplicate", "priority": "medium"},
        ]
    )

    assert "duplicate" in options["case_types"]
    assert "new_lead" in options["case_types"]


def test_final_decision_get_routes_do_not_change_storage(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-final-read-only")
    before = {
        path.relative_to(run_dir): path.read_bytes()
        for path in run_dir.rglob("*")
        if path.is_file()
    }
    client = _client(storage_dir)

    dashboard = client.get("/api/rop/dashboard?run_id=run-final-read-only")
    detail = client.get("/api/rop/events/evt-1?run_id=run-final-read-only")

    assert dashboard.status_code == 200
    assert detail.status_code == 200
    after = {
        path.relative_to(run_dir): path.read_bytes()
        for path in run_dir.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert not (run_dir / "rop_final_decisions.json").exists()


def test_api_rop_dashboard_includes_current_state_queues(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rich_rop_run(storage_dir, "run-bitrix-api")
    _write_bitrix_current_state_artifacts(run_dir, "run-bitrix-api")
    client = _client(storage_dir)

    response = client.get("/api/rop/dashboard")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert "current_state_queues" in payload
    assert payload["current_state_queues"]["lost_in_bitrix"][0]["event_id"] == (
        "evt-lost"
    )


def test_rop_bitrix_layout_with_current_state_queues() -> None:
    data = {
        "current_state_kpi": {
            "matched_in_bitrix": 1,
            "lost_in_bitrix": 1,
            "ambiguous_in_bitrix": 1,
            "connector_degraded": 1,
            "unreconciled": 1,
        },
        "current_state_queues": {
            "lost_in_bitrix": [
                {
                    "event_id": "evt-lost",
                    "case_type": "new_lead",
                    "priority": "high",
                    "bitrix_status": "not_found",
                }
            ],
            "ambiguous": [],
            "degraded": [],
            "unreconciled": [],
            "matched": [],
        },
        "bitrix": {"status": "ok"},
        "evidence_links": [
            {
                "artifact_id": "bitrix_reconciliation_json",
                "available": True,
            }
        ],
    }

    layout = build_rop_page_layout(data, tab="bitrix")

    assert any(block["type"] == "kpi_grid" for block in layout)
    assert any(
        block["type"] == "status_table" and block["title"] == "Lost in Bitrix"
        for block in layout
    )


def test_rop_bitrix_layout_prefers_period_queues() -> None:
    data = {
        "business_kpi": {
            "matched_in_bitrix": 0,
            "lost_in_bitrix": 0,
            "ambiguous_or_duplicate": 1,
            "bitrix_errors": 2,
            "unreconciled": 0,
        },
        "current_state_kpi": {"connector_degraded": 99},
        "current_state_queues": {
            "matched": [
                {
                    "event_id": "evt-old-matched",
                    "case_type": "new_lead",
                    "priority": "high",
                    "bitrix_status": "matched_lead",
                }
            ],
            "lost_in_bitrix": [
                {
                    "event_id": "evt-old-lost",
                    "case_type": "new_lead",
                    "priority": "high",
                    "bitrix_status": "not_found",
                }
            ],
            "ambiguous": [
                {
                    "event_id": "evt-old-ambiguous",
                    "case_type": "new_lead",
                    "priority": "high",
                    "bitrix_status": "ambiguous",
                }
            ],
            "degraded": [
                {
                    "event_id": "evt-old-degraded",
                    "case_type": "new_lead",
                    "priority": "high",
                    "bitrix_status": "connector_degraded",
                }
            ],
            "unreconciled": [
                {
                    "event_id": "evt-old-unreconciled",
                    "case_type": "new_lead",
                    "priority": "high",
                    "bitrix_status": "unreconciled",
                }
            ],
        },
        "queues": {
            "matched": [
                {
                    "event_id": "evt-current-matched",
                    "bot_case_type": "existing_deal",
                    "bot_priority": "low",
                    "bitrix_status": "matched_deal",
                }
            ],
            "lost_in_bitrix": [
                {
                    "event_id": "evt-current-lost",
                    "bot_case_type": "new_lead",
                    "bot_priority": "medium",
                    "bitrix_status": "not_found",
                }
            ],
            "ambiguous": [
                {
                    "event_id": "evt-current-ambiguous",
                    "bot_case_type": "existing_deal",
                    "bot_priority": "low",
                    "bitrix_status": "ambiguous",
                }
            ],
            "degraded": [
                {
                    "event_id": "evt-current-degraded",
                    "bot_case_type": "new_lead",
                    "bot_priority": "medium",
                    "bitrix_status": "connector_degraded",
                }
            ],
            "unreconciled": [
                {
                    "event_id": "evt-current-unreconciled",
                    "bot_case_type": "new_lead",
                    "bot_priority": "low",
                    "bitrix_status": "unreconciled",
                }
            ],
        },
        "bitrix": {"status": "ok"},
        "evidence_links": [
            {
                "artifact_id": "bitrix_reconciliation_json",
                "available": True,
            }
        ],
    }

    layout = build_rop_page_layout(data, tab="bitrix")
    tables = {
        block["title"]: block for block in layout if block["type"] == "status_table"
    }
    kpi = next(block for block in layout if block["type"] == "kpi_grid")

    assert tables["Matched"]["rows"] == [
        ["evt-current-matched", "existing_deal", "low", "matched_deal"]
    ]
    assert tables["Lost in Bitrix"]["rows"] == [
        ["evt-current-lost", "new_lead", "medium", "not_found"]
    ]
    assert tables["Ambiguous"]["rows"] == [
        ["evt-current-ambiguous", "existing_deal", "low", "ambiguous"]
    ]
    assert tables["Connector Degraded"]["rows"] == [
        ["evt-current-degraded", "new_lead", "medium", "connector_degraded"]
    ]
    assert tables["Unreconciled"]["rows"] == [
        ["evt-current-unreconciled", "new_lead", "low", "unreconciled"]
    ]
    assert all("evt-old" not in str(table["rows"]) for table in tables.values())
    assert (
        next(item for item in kpi["items"] if item["label"] == "Connector Degraded")[
            "value"
        ]
        == 2
    )


def test_rop_dashboard_handles_missing_artifacts(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_missing_attachment_run(storage_dir, "run-missing-att")
    client = _client(storage_dir)
    response = client.get("/api/rop/dashboard")
    assert response.status_code == 200
    payload = response.json()["data"]
    att = payload["attachment_summary"]
    assert att["total_attachments"] == 0
    assert att["preview_available_count"] == 0
    assert payload["kpis"]["attachment_count"] == 0


def test_rop_dashboard_handles_malformed_artifacts(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_malformed_json_artifact_run(storage_dir, "run-malformed-json")
    _write_rop_web_projection(storage_dir, run_id="run-malformed-json")
    client = _client(storage_dir)
    response = client.get("/api/rop/dashboard", params={"run_id": "run-malformed-json"})
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["kpis"]["classified_count"] == 0
    assert payload["classification_distribution"]["case_type_counts"] == {}
    warnings = payload["warnings"]
    warning_codes = [w.get("code") for w in warnings]
    assert "missing_artifact" in warning_codes


def test_rop_dashboard_escapes_html(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_html_artifact_values_run(storage_dir, "run-html-safe")
    client = _client(storage_dir)
    response = client.get("/api/rop/dashboard")
    assert response.status_code == 200
    response_html = client.get("/rop")
    assert response_html.status_code == 200
    html = response_html.text
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html or "&#60;script&#62;" in html


def test_beeui_artifact_viewer_html(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-art-view")
    client = _client(storage_dir)
    response = client.get("/runs/run-art-view/artifacts/operator_summary_json")
    assert response.status_code == 200
    assert "<!doctype html>" in response.text.lower()


def test_artifact_viewer_api_still_json(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-api-art")
    client = _client(storage_dir)
    response = client.get("/api/runs/run-api-art/artifacts/operator_summary_json")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data


def test_locale_default_en(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.locale import get_locale_config, resolve_locale

    cfg = get_locale_config()
    assert cfg["default"] == "en"
    assert resolve_locale(None, cfg) == "en"
    assert resolve_locale("en", cfg) == "en"


def test_locale_resolve_ru(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.locale import get_locale_config, resolve_locale

    cfg = get_locale_config()
    assert resolve_locale("ru", cfg) == "ru"


def test_locale_fallback_on_invalid(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.locale import get_locale_config, resolve_locale

    cfg = get_locale_config()
    assert resolve_locale("de", cfg) == "en"
    assert resolve_locale("bad", cfg) == "en"


def test_locale_cookie_fallback(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.locale import get_locale_config, resolve_locale

    cfg = get_locale_config()
    assert resolve_locale(None, cfg, cookie_param="ru") == "ru"
    assert resolve_locale("en", cfg, cookie_param="ru") == "en"
    assert resolve_locale(None, cfg, cookie_param="de") == "en"
    assert resolve_locale("ru", cfg, cookie_param="en") == "ru"


def test_locale_t_function(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.locale import t

    assert t("Dashboard") == "Dashboard"
    assert t("Dashboard", "ru") == "Дашборд"
    assert t("Nonexistent label") == "Nonexistent label"


def test_rop_lang_ru(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_rich_rop_run(storage_dir, "run-lang-ru")
    client = _client(storage_dir)
    response = client.get("/rop", params={"lang": "ru"})
    assert response.status_code == 200
    html = response.text
    assert "Панель РОПа" in html
    assert "ПИСЬМА ЗА ПЕРИОД" in html
    assert "НОВЫЕ ЛИДЫ" in html
    assert "Открыть очередь" in html
    assert "Открыть Битрикс" in html
    assert "Последняя выборка" in html
    assert "Требуют проверки" in html
    assert "Needs review" not in html
    assert "beeui-language-switcher" in html
    assert 'class="dropdown ms-auto"' in html
    assert "dropdown-menu dropdown-menu-end" in html
    assert "Последние 7 дней" in html
    assert "Сегодня" in html
    assert "Вчера" in html
    assert "Последние 30 дней" in html
    assert "Последние 3 месяца" in html
    assert "Последний год" in html
    assert "Всё время" in html
    assert 'btn btn-outline-primary btn-sm me-1">Сегодня' not in html
    assert 'btn btn-outline-primary btn-sm me-1">Последние 30 дней' not in html


def test_rop_overview_lang_ru_removes_primary_english_labels(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_rich_rop_run(storage_dir, "run-lang-ru-overview")
    client = _client(storage_dir)
    response = client.get("/rop?tab=overview&lang=ru")
    assert response.status_code == 200
    html = response.text
    assert "ROP Control Center" not in html
    assert "TODAY&#39;S EMAILS" not in html
    assert "NEW LEADS" not in html
    assert "Open Queue" not in html


def test_rop_tabs_preserve_lang_and_period(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_rich_rop_run(storage_dir, "run-lang-tab-links")
    client = _client(storage_dir)
    response = client.get("/rop?tab=overview&period=7d&lang=ru")
    assert response.status_code == 200
    html = response.text
    assert (
        "/rop?tab=threads&amp;period=7d&amp;lang=ru" in html
        or "/rop?lang=ru&amp;period=7d&amp;tab=threads" in html
    )
    assert (
        "/rop?tab=ai_assist&amp;period=7d&amp;lang=ru" in html
        or "/rop?lang=ru&amp;period=7d&amp;tab=ai_assist" in html
    )


def test_rop_overview_links_preserve_lang(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_rich_rop_run(storage_dir, "run-lang-overview-links")
    client = _client(storage_dir)
    response = client.get("/rop?tab=overview&period=7d&lang=ru")
    assert response.status_code == 200
    html = response.text
    assert "run_id=run-lang-overview-links" in html
    assert "priority=high" in html
    assert "&amp;lang=ru" in html
    assert "queue=needs_review" in html
    assert (
        "bitrix_status=not_found%2Cambiguous%2Cduplicate_candidate%2Cunreconciled"
        in html
    )
    assert (
        "/rop?tab=bitrix&amp;run_id=run-lang-overview-links&amp;period=7d&amp;lang=ru"
        in html
    )
    assert (
        "/rop?tab=evidence&amp;run_id=run-lang-overview-links&amp;period=7d&amp;lang=ru"
        in html
    )
    assert (
        "/rop?tab=overview&amp;run_id=run-lang-overview-links&amp;period=today&amp;lang=ru"
        in html
    )
    assert (
        "/rop?tab=overview&amp;run_id=run-lang-overview-links&amp;period=30d&amp;lang=ru"
        in html
    )


def test_rop_language_switcher_visible(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_rich_rop_run(storage_dir, "run-lang-switcher")
    client = _client(storage_dir)
    response = client.get("/rop?lang=ru")
    assert response.status_code == 200
    html = response.text
    assert "RU" in html
    assert "EN" in html


def test_api_rop_dashboard_backward_compatible(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-bc-001")
    client = _client(storage_dir)
    response = client.get("/api/rop/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    payload = data["data"]
    assert "run_id" in payload
    assert "sources" in payload
    assert "classified_count" in payload
    assert "case_type_counts" in payload
    assert "priority_counts" in payload
    assert "fallback_count" in payload
    assert "selected_run_id" in payload
    assert "available_runs" in payload
    assert "kpis" in payload
    assert "funnel" in payload
    assert "source_health" in payload
    assert "classification_distribution" in payload
    assert "recommendations" in payload
    assert "evidence_links" in payload


def test_raw_eml_blocked(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-eml-block")
    client = _client(storage_dir)
    response = client.get("/runs/run-eml-block/artifacts/raw_eml")
    assert response.status_code in (200, 400, 404)
    api_response = client.get("/api/runs/run-eml-block/artifacts/raw_eml")
    assert api_response.status_code in (200, 400, 404)


def test_no_post_routes_in_custom_routes(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))
    for path in ["/", "/health", "/runs", "/rop", "/modules"]:
        response = client.post(path)
        assert response.status_code in (405, 404), f"POST {path} should be rejected"


def test_get_page_returns_layout(tmp_path: Path) -> None:

    from beeagent_module.interfaces.ui.adapter import BeeAgentUiAdapter

    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-get-page")
    _write_rop_web_projection(storage_dir)
    adapter = BeeAgentUiAdapter(storage_dir=storage_dir, settings=_build_settings())

    result = adapter.get_page("rop_dashboard", {"tab": "overview"})

    assert not isinstance(result, AdapterErrorResult)
    assert result.status in ("ok", "partial")

    data = result.data
    assert isinstance(data, dict)
    assert "layout" in data
    assert isinstance(data["layout"], list)


def _write_run_with_event_dates(storage_dir: Path, run_id: str) -> Path:
    run_dir = _write_run_artifacts(storage_dir, run_id)
    now = datetime.now(UTC)
    classified = json.loads(
        (run_dir / "classified_events.json").read_text(encoding="utf-8")
    )
    for evt in classified:
        evt["event_date"] = now.isoformat()
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified), encoding="utf-8"
    )
    normalized = json.loads(
        (run_dir / "normalized_events.json").read_text(encoding="utf-8")
    )
    for evt in normalized:
        evt["event_date"] = now.isoformat()
    (run_dir / "normalized_events.json").write_text(
        json.dumps(normalized), encoding="utf-8"
    )
    return run_dir


def test_rop_overview_renders_deterministic_chart_containers(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_with_event_dates(storage_dir, "run-chart-schema")
    client = _client(storage_dir)
    response = client.get("/rop?period=7d")
    assert response.status_code == 200
    html = response.text
    assert "Email Workload" in html
    assert "Action Required" in html
    assert "Lead outcome mix" in html
    assert "Bitrix reconciliation" in html
    assert "Source contribution" in html
    assert "chart-rop-email-workload" in html
    assert "chart-rop-action-required" in html
    assert "chart-rop-outcome-mix" in html
    assert "chart-rop-bitrix" in html
    assert "chart-rop-source-contribution" in html
    assert "progress progress-sm" in html
    assert 'class="card card-sm"' in html


def test_rop_overview_no_smoke_run_ids(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "SMOKE-IT27-001")
    client = _client(storage_dir)
    response = client.get("/rop?tab=overview")
    html = response.text
    assert "SMOKE-IT27" not in html or "Run Selector" not in html


def test_rop_overview_no_period_selector_card(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-period-regression")
    client = _client(storage_dir)
    response = client.get("/rop?tab=overview")
    html = response.text
    assert "Period Selector" not in html


def test_rop_overview_period_dropdown_has_customer_labels(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-period-labels")
    client = _client(storage_dir)
    response = client.get("/rop?tab=overview")
    html = response.text
    assert 'class="dropdown ms-auto"' in html
    assert "dropdown-menu dropdown-menu-end" in html
    assert "dropdown-item active" in html
    assert "Today" in html
    assert "Yesterday" in html
    assert "Last 7 days" in html
    assert "Last 30 days" in html
    assert "Last 3 months" in html
    assert "Last year" in html
    assert "All time" in html
    assert (
        'href="/rop?tab=overview&amp;run_id=run-period-labels&amp;period=today"' in html
    )
    assert (
        'href="/rop?tab=overview&amp;run_id=run-period-labels&amp;period=yesterday"'
        in html
    )
    assert 'href="/rop?tab=overview&amp;run_id=run-period-labels&amp;period=7d"' in html
    assert (
        'href="/rop?tab=overview&amp;run_id=run-period-labels&amp;period=30d"' in html
    )
    assert (
        'href="/rop?tab=overview&amp;run_id=run-period-labels&amp;period=90d"' in html
    )
    assert (
        'href="/rop?tab=overview&amp;run_id=run-period-labels&amp;period=365d"' in html
    )
    assert (
        'href="/rop?tab=overview&amp;run_id=run-period-labels&amp;period=all"' in html
    )
    assert "run_id=run-period-labels" in html
    assert "priority=high" in html
    assert "queue=needs_review" in html
    assert (
        "bitrix_status=not_found%2Cambiguous%2Cduplicate_candidate%2Cunreconciled"
        in html
    )
    assert 'href="/rop?tab=bitrix&amp;run_id=run-period-labels&amp;period=7d"' in html
    assert 'btn btn-outline-primary btn-sm me-1">Last 30 days' not in html


def test_rop_overview_has_no_unsupported_blocks(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-no-unsupported")
    client = _client(storage_dir)
    response = client.get("/rop?tab=overview&period=7d")
    html = response.text
    assert response.status_code == 200
    assert "Unavailable block" not in html
    assert "Failed to render block type" not in html
    assert "attention_list" not in html


def test_rop_overview_has_action_required_panel(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-action-regression")
    client = _client(storage_dir)
    response = client.get("/rop?tab=overview")
    assert response.status_code == 200
    assert "Action Required" in response.text


def test_rop_overview_kpi_uses_business_labels(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-labels-regression")
    client = _client(storage_dir)
    response = client.get("/rop?tab=overview")
    html = response.text
    assert "Business KPI" not in html
    assert "Detailed Metrics" not in html
    assert "Business metrics" not in html
    assert "Emails in period" in html
    assert "NEW LEADS" in html
    assert "Urgent leads" in html
    assert "Needs review" in html
    assert "Bitrix gaps" in html
    assert "Data quality" in html
    assert "high_priority" not in html


def test_rop_overview_no_run_selector(tmp_path: Path) -> None:
    data = {
        "run_id": "run-test-001",
        "kpis": {},
        "available_runs": ["SMOKE-IT27-001", "run-normal"],
        "warnings": [],
        "source_health": [],
        "funnel": [],
        "recommendations": [],
        "evidence_links": [],
        "classification_distribution": {},
        "business_kpi": {"processed_events": 5},
        "series": {},
        "period": "7d",
        "configured_periods": ["7d"],
    }
    from beeagent_module.interfaces.ui.read_model import build_rop_page_layout

    layout = build_rop_page_layout(data, tab="overview")
    run_selectors = [b for b in layout if b.get("title") == "Run Selector"]
    assert len(run_selectors) == 0


def test_rop_overview_no_raw_enum_labels(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.read_model import _humanize_label

    assert _humanize_label("new_lead") == "New leads"
    assert _humanize_label("unreconciled") == "Not reconciled"
    assert _humanize_label("ambiguous") == "Ambiguous / duplicate"
    assert _humanize_label("matched") == "Matched in Bitrix"
    assert _humanize_label("lost") == "Lost in Bitrix"
    assert _humanize_label("existing_client") == "Existing clients"


def test_rop_overview_chart_titles_are_business_facing(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_with_event_dates(storage_dir, "run-chart-business")
    client = _client(storage_dir)
    response = client.get("/rop?period=7d&tab=overview")
    html = response.text
    assert "Email Workload" in html
    assert "Action Required" in html
    assert "Lead outcome mix" in html
    assert "Bitrix reconciliation" in html
    assert "Source contribution" in html


def test_rop_overview_bitrix_cta_when_unreconciled(tmp_path: Path) -> None:
    data = {
        "run_id": "run-bitrix-cta",
        "kpis": {},
        "available_runs": [],
        "warnings": [],
        "source_health": [],
        "funnel": [],
        "recommendations": [],
        "evidence_links": [],
        "classification_distribution": {},
        "business_kpi": {"processed_events": 5, "unreconciled": 2},
        "series": {
            "bitrix_distribution": {
                "labels": ["matched", "unreconciled"],
                "series": [1, 2],
            },
        },
        "period": "7d",
        "configured_periods": ["7d"],
    }
    from beeagent_module.interfaces.ui.read_model import build_rop_page_layout

    layout = build_rop_page_layout(data, tab="overview")
    action_card = next(
        block for block in layout if block.get("title") == "Action Required"
    )
    assert action_card["type"] == "chart"
    assert "0 items need review" in action_card["subtitle"]


def test_rop_overview_no_detailed_metrics_separate_card() -> None:
    data = {
        "run_id": "run-test",
        "kpis": {},
        "available_runs": [],
        "warnings": [],
        "source_health": [],
        "funnel": [],
        "recommendations": [],
        "evidence_links": [],
        "classification_distribution": {},
        "business_kpi": {},
        "series": {},
        "period": "7d",
        "configured_periods": ["7d"],
    }
    from beeagent_module.interfaces.ui.read_model import build_rop_page_layout

    layout = build_rop_page_layout(data, tab="overview")
    titles = [b.get("title") for b in layout]
    assert "Detailed Metrics" not in titles, (
        "Detailed Metrics must not be a separate block"
    )
    assert "Business metrics" not in titles
    assert "Overview" not in titles, "Old Overview block must not exist"


class TestUi6It30:
    def _write_full_it30_run(self, storage_dir: Path, run_id: str) -> Path:
        run_dir = _write_rich_rop_run(storage_dir, run_id)

        classified = json.loads(
            (run_dir / "classified_events.json").read_text(encoding="utf-8")
        )
        for item in classified:
            if item.get("event_id") in ("evt-001", "evt-002"):
                item["thread_id"] = "thr-001"
            if item.get("event_id") == "evt-005":
                item["thread_id"] = "thr-002"
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )

        mailbox_selection = {
            "run_id": run_id,
            "strategy": "latest_n_by_internaldate_desc",
            "sources": [
                {
                    "source_id": "hotline_mailbox",
                    "source_display_name": "Welding Hotline mailbox",
                    "selected_count": 5,
                    "available_count": 12,
                    "messages": [
                        {
                            "source_message_id": "m-001",
                            "internal_date": "2026-06-28T12:00:00+00:00",
                            "message_id": "<m-001@example.com>",
                            "subject": "Welding equipment inquiry",
                            "selected": True,
                        },
                        {
                            "source_message_id": "m-002",
                            "internal_date": "2026-06-27T10:30:00+00:00",
                            "message_id": "<m-002@example.com>",
                            "subject": "Re: Welding equipment inquiry",
                            "selected": True,
                        },
                        {
                            "source_message_id": "m-003",
                            "internal_date": "2026-06-26T09:00:00+00:00",
                            "message_id": "<m-003@example.com>",
                            "subject": "Pricing request",
                            "selected": True,
                        },
                        {
                            "source_message_id": "m-004",
                            "internal_date": "2026-06-25T08:00:00+00:00",
                            "message_id": "<m-004@example.com>",
                            "subject": "Failure report",
                            "selected": True,
                        },
                        {
                            "source_message_id": "m-005",
                            "internal_date": "2026-06-25T07:30:00+00:00",
                            "message_id": "<m-005@example.com>",
                            "subject": "Re: Failure report",
                            "selected": True,
                        },
                    ],
                }
            ],
            "warnings": [],
        }
        (run_dir / "mailbox_selection.json").write_text(
            json.dumps(mailbox_selection), encoding="utf-8"
        )

        thread_index = {
            "run_id": run_id,
            "threads": [
                {
                    "thread_id": "thr-001",
                    "event_ids": ["evt-001", "evt-002"],
                    "message_ids": ["<m-001@example.com>", "<m-002@example.com>"],
                    "evidence": {
                        "message_id_link": False,
                        "references_link": True,
                        "subject_fallback": False,
                    },
                },
                {
                    "thread_id": "thr-002",
                    "event_ids": ["evt-003", "evt-005"],
                    "message_ids": ["<m-003@example.com>", "<m-005@example.com>"],
                    "evidence": {
                        "message_id_link": False,
                        "references_link": False,
                        "subject_fallback": True,
                    },
                },
            ],
            "warnings": [],
        }
        (run_dir / "mail_thread_index.json").write_text(
            json.dumps(thread_index), encoding="utf-8"
        )

        thread_context = {
            "run_id": run_id,
            "contexts": [
                {
                    "event_id": "evt-002",
                    "thread_id": "thr-001",
                    "reply_or_forward": True,
                    "previous_event_ids": ["evt-001"],
                    "source_id": "hotline_mailbox",
                    "client_id": "welding",
                    "thread_context_confidence": 0.65,
                    "reason_codes": ["references_chain", "reply_or_forward"],
                },
                {
                    "event_id": "evt-005",
                    "thread_id": "thr-002",
                    "reply_or_forward": False,
                    "previous_event_ids": ["evt-003"],
                    "source_id": "hotline_mailbox",
                    "client_id": "welding",
                    "thread_context_confidence": 0.4,
                    "reason_codes": ["subject_match"],
                },
            ],
            "warnings": [],
        }
        (run_dir / "mail_thread_context.json").write_text(
            json.dumps(thread_context), encoding="utf-8"
        )

        ai_requests = {
            "run_id": run_id,
            "enabled": True,
            "counters": {
                "ai_assist_requested_count": 3,
                "ai_assist_used_count": 2,
                "eligible_count": 5,
            },
            "requests": [
                {"event_id": "evt-001", "requested": True},
                {"event_id": "evt-003", "requested": True},
                {"event_id": "evt-005", "requested": True},
            ],
        }
        (run_dir / "rop_ai_assist_requests.json").write_text(
            json.dumps(ai_requests), encoding="utf-8"
        )

        ai_decisions = {
            "run_id": run_id,
            "counters": {"decision_count": 3},
            "decisions": [
                {"event_id": "evt-001", "status": "ok"},
                {"event_id": "evt-003", "status": "low_confidence"},
                {"event_id": "evt-005", "status": "ok"},
            ],
        }
        (run_dir / "rop_ai_assist_decisions.json").write_text(
            json.dumps(ai_decisions), encoding="utf-8"
        )

        ai_results = {
            "run_id": run_id,
            "counters": {
                "ai_assist_requested_count": 3,
                "ai_assist_used_count": 2,
                "ai_assist_low_confidence_count": 1,
                "ai_assist_invalid_output_count": 0,
                "ai_assist_degraded_count": 1,
            },
            "results": [
                {
                    "event_id": "evt-001",
                    "ai_assist_status": "ok",
                    "ai_assist_used": True,
                    "ai_confidence": 0.92,
                    "final_case_type": "new_lead",
                    "final_priority": "high",
                },
                {
                    "event_id": "evt-003",
                    "ai_assist_status": "low_confidence",
                    "ai_assist_used": False,
                    "ai_confidence": 0.35,
                    "final_case_type": "new_lead",
                    "final_priority": "medium",
                },
                {
                    "event_id": "evt-005",
                    "ai_assist_status": "ok",
                    "ai_assist_used": True,
                    "ai_confidence": 0.95,
                    "final_case_type": "new_lead",
                    "final_priority": "high",
                },
            ],
        }
        (run_dir / "rop_ai_assist_results.json").write_text(
            json.dumps(ai_results), encoding="utf-8"
        )

        return run_dir

    def test_full_it30_run_renders_latest_selection(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        self._write_full_it30_run(storage_dir, "run-it30-full")
        client = _client(storage_dir)
        response = client.get("/rop")
        assert response.status_code == 200
        assert "Latest selection" in response.text

    def test_full_it30_api_includes_new_fields(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        self._write_full_it30_run(storage_dir, "run-it30-api")
        client = _client(storage_dir)
        response = client.get("/api/rop/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        payload = data["data"]
        assert "latest_selection" in payload
        assert "thread_summary" in payload
        assert "threads" in payload
        assert "ai_assist_summary" in payload
        assert "ai_assist_events" in payload

        ls = payload["latest_selection"]
        assert ls["selected_count"] == 5
        assert ls["source_count"] == 1
        assert ls["sources"][0]["available_count"] == 12
        assert ls["newest_message_at"] == "2026-06-28T12:00:00+00:00"
        assert ls["strategy"] == "latest_n_by_internaldate_desc"

        ts = payload["thread_summary"]
        assert ts["thread_count"] == 2
        assert ts["events_with_thread_context"] == 2
        assert ts["reply_or_forward_count"] == 1

        ai = payload["ai_assist_summary"]
        assert ai["evidence_available"] is True
        assert ai["request_count"] == 3
        assert ai["result_count"] == 3
        assert ai["used_count"] == 2
        assert ai["low_confidence_count"] == 1
        assert payload["threads"][0]["event_count"] > 0
        assert payload["threads"][0]["latest_subject"]
        assert any(
            item["ai_status"] == "low_confidence"
            for item in payload["ai_assist_events"]
        )
        low_conf_event = next(
            item
            for item in payload["ai_assist_events"]
            if item["ai_status"] == "low_confidence"
        )
        assert low_conf_event["sender"] == "partner@supply.kz"
        assert low_conf_event["subject"] == "Price list"

    def test_rop_tab_threads_returns_200(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        self._write_full_it30_run(storage_dir, "run-tab-threads")
        client = _client(storage_dir)
        response = client.get("/rop?tab=threads")
        assert response.status_code == 200

    def test_rop_tab_ai_assist_returns_200(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        self._write_full_it30_run(storage_dir, "run-tab-ai")
        client = _client(storage_dir)
        response = client.get("/rop?tab=ai_assist")
        assert response.status_code == 200

    def test_rop_lang_ru_includes_russian_labels(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        self._write_full_it30_run(storage_dir, "run-lang-ru")
        client = _client(storage_dir)
        response = client.get("/rop?tab=threads&lang=ru")
        assert response.status_code == 200
        html = response.text
        assert "Цепочки" in html
        assert "Группы цепочек" in html

    def test_rop_lang_ru_ai_assist_labels(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        self._write_full_it30_run(storage_dir, "run-lang-ru-ai")
        client = _client(storage_dir)
        response = client.get("/rop?tab=ai_assist&lang=ru")
        assert response.status_code == 200
        html = response.text
        assert "AI ассистент" in html
        assert "Сводка AI ассистента" in html

    def test_old_run_without_it30_renders(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-old-no-it30")
        client = _client(storage_dir)
        response = client.get("/rop")
        assert response.status_code == 200

    def test_old_run_without_it30_api_has_empty_warnings(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-old-api")
        client = _client(storage_dir)
        response = client.get("/api/rop/dashboard")
        assert response.status_code == 200
        payload = response.json()["data"]
        assert "latest_selection" in payload
        assert payload["latest_selection"]["selected_count"] == 0
        assert "thread_summary" in payload
        assert payload["thread_summary"]["thread_count"] == 0
        assert "ai_assist_summary" in payload
        assert payload["ai_assist_summary"]["evidence_available"] is False

    def test_malformed_it30_artifacts_render_warnings(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        run_dir = self._write_full_it30_run(storage_dir, "run-malformed-it30")
        (run_dir / "mailbox_selection.json").write_text(
            "{invalid json}", encoding="utf-8"
        )
        (run_dir / "rop_ai_assist_results.json").write_text(
            "{bad data}", encoding="utf-8"
        )
        client = _client(storage_dir)
        response = client.get("/rop")
        assert response.status_code == 200

    def test_malformed_it30_api_still_returns(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        run_dir = self._write_full_it30_run(storage_dir, "run-malformed-api")
        (run_dir / "mail_thread_context.json").write_text("{invalid}", encoding="utf-8")
        client = _client(storage_dir)
        response = client.get("/api/rop/dashboard")
        assert response.status_code == 200
        payload = response.json()["data"]
        assert "thread_summary" in payload
        assert "thread_summary" in payload

    def test_ai_assist_summary_preserves_runtime_zero_and_degraded_count(
        self,
        tmp_path: Path,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        run_dir = self._write_full_it30_run(storage_dir, "run-ai-zero-used")

        ai_results = {
            "run_id": "run-ai-zero-used",
            "counters": {
                "ai_assist_requested_count": 2,
                "ai_assist_used_count": 0,
                "ai_assist_degraded_count": 2,
            },
            "results": [
                {
                    "event_id": "evt-001",
                    "ai_assist_status": "ok",
                    "ai_assist_used": False,
                    "ai_confidence": 0.92,
                },
                {
                    "event_id": "evt-003",
                    "ai_assist_status": "provider_unavailable",
                    "ai_assist_used": False,
                    "ai_confidence": None,
                },
            ],
        }
        (run_dir / "rop_ai_assist_results.json").write_text(
            json.dumps(ai_results),
            encoding="utf-8",
        )

        client = _client(storage_dir)
        response = client.get("/api/rop/dashboard")

        assert response.status_code == 200
        ai_summary = response.json()["data"]["ai_assist_summary"]
        assert ai_summary["used_count"] == 0
        assert ai_summary["degraded_count"] == 2

    def test_threads_fallback_to_index_when_contexts_empty(
        self, tmp_path: Path
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        run_dir = self._write_full_it30_run(storage_dir, "run-thread-index-fallback")
        (run_dir / "mail_thread_context.json").write_text(
            json.dumps(
                {
                    "run_id": "run-thread-index-fallback",
                    "contexts": [],
                    "warnings": [],
                }
            ),
            encoding="utf-8",
        )

        client = _client(storage_dir)
        api_response = client.get("/api/rop/dashboard")
        assert api_response.status_code == 200
        payload = api_response.json()["data"]
        assert payload["threads"]
        assert payload["threads"][0]["latest_subject"]
        assert payload["threads"][0]["latest_sender"]

        html_response = client.get("/rop?tab=threads")
        assert html_response.status_code == 200
        assert "Re: Order #123" in html_response.text
        assert "client@workshop.kz" in html_response.text
        assert "Linked by references" in html_response.text

    def test_ai_assist_not_requested_hides_noise(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        run_dir = self._write_full_it30_run(storage_dir, "run-ai-not-requested")

        (run_dir / "rop_ai_assist_requests.json").write_text(
            json.dumps(
                {
                    "run_id": "run-ai-not-requested",
                    "enabled": True,
                    "counters": {
                        "ai_assist_requested_count": 0,
                        "ai_assist_used_count": 0,
                        "eligible_count": 5,
                    },
                    "requests": [],
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "rop_ai_assist_decisions.json").write_text(
            json.dumps(
                {
                    "run_id": "run-ai-not-requested",
                    "counters": {"decision_count": 0},
                    "decisions": [],
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "rop_ai_assist_results.json").write_text(
            json.dumps(
                {
                    "run_id": "run-ai-not-requested",
                    "counters": {
                        "ai_assist_requested_count": 0,
                        "ai_assist_used_count": 0,
                        "ai_assist_degraded_count": 0,
                    },
                    "results": [],
                }
            ),
            encoding="utf-8",
        )

        client = _client(storage_dir)
        api_response = client.get("/api/rop/dashboard")
        assert api_response.status_code == 200
        assert api_response.json()["data"]["ai_assist_events"] == []

        html_response = client.get("/rop?tab=ai_assist")
        assert html_response.status_code == 200
        assert "Final Decisions" in html_response.text
        assert "AI Assist Summary" not in html_response.text
        assert "not_requested" not in html_response.text

    def test_ai_assist_not_used_ru_state(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        run_dir = self._write_full_it30_run(storage_dir, "run-ai-not-used-ru")

        (run_dir / "rop_ai_assist_requests.json").write_text(
            json.dumps(
                {
                    "run_id": "run-ai-not-used-ru",
                    "enabled": True,
                    "counters": {"eligible_count": 5, "ai_assist_requested_count": 0},
                    "requests": [],
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "rop_ai_assist_decisions.json").write_text(
            json.dumps(
                {
                    "run_id": "run-ai-not-used-ru",
                    "counters": {"decision_count": 0},
                    "decisions": [],
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "rop_ai_assist_results.json").write_text(
            json.dumps(
                {
                    "run_id": "run-ai-not-used-ru",
                    "counters": {
                        "ai_assist_requested_count": 0,
                        "ai_assist_used_count": 0,
                        "ai_assist_degraded_count": 0,
                    },
                    "results": [],
                }
            ),
            encoding="utf-8",
        )

        client = _client(storage_dir)
        response = client.get("/rop?tab=ai_assist&lang=ru")
        assert response.status_code == 200
        assert "Итоговые решения" in response.text
        assert "Сводка AI ассистента" not in response.text

    def test_new_it30_artifact_ids_allowlisted(self) -> None:
        from beeagent_module.interfaces.ui.artifacts import is_artifact_id_allowed

        for aid in (
            "mailbox_selection_json",
            "mail_thread_index_json",
            "mail_thread_context_json",
            "rop_ai_assist_requests_json",
            "rop_ai_assist_decisions_json",
            "rop_ai_assist_results_json",
        ):
            assert is_artifact_id_allowed(aid), f"{aid} should be allowlisted"

    def test_non_allowlisted_still_rejected(self) -> None:
        from beeagent_module.interfaces.ui.artifacts import is_artifact_id_allowed

        assert is_artifact_id_allowed("raw_eml") is False
        assert is_artifact_id_allowed("attachment_content") is False

    def test_get_routes_no_mutation_it30(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        run_dir = self._write_full_it30_run(storage_dir, "run-no-mutate-it30")
        client = _client(storage_dir)

        before = {
            path.relative_to(storage_dir).as_posix(): path.read_text(encoding="utf-8")
            for path in run_dir.rglob("*")
            if path.is_file()
        }

        client.get("/rop")
        client.get("/api/rop/dashboard")
        client.get("/rop?tab=threads")
        client.get("/rop?tab=ai_assist")
        client.get("/rop?lang=ru")

        after = {
            path.relative_to(storage_dir).as_posix(): path.read_text(encoding="utf-8")
            for path in run_dir.rglob("*")
            if path.is_file()
        }

        assert after == before

    def test_no_secrets_in_html_it30(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        run_dir = self._write_full_it30_run(storage_dir, "run-sec-it30")
        (run_dir / "mailbox_selection.json").write_text(
            json.dumps(
                {
                    "run_id": "run-sec-it30",
                    "password_value": "should-not-leak",
                    "ROP_API_KEY": "secret-key-12345",
                    "strategy": "latest_n",
                    "selected_count": 1,
                    "source_count": 0,
                    "sources": [],
                }
            ),
            encoding="utf-8",
        )
        client = _client(storage_dir)
        for tab in ("threads", "ai_assist", "overview"):
            response = client.get(f"/rop?tab={tab}")
            assert response.status_code == 200
            assert "should-not-leak" not in response.text
            assert "secret-key-12345" not in response.text

    def test_no_raw_eml_in_it30_html(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        run_dir = self._write_full_it30_run(storage_dir, "run-no-raw")
        client = _client(storage_dir)
        for tab in ("threads", "ai_assist"):
            response = client.get(f"/rop?tab={tab}")
            assert response.status_code == 200
            assert "raw_eml" not in response.text.lower()
            assert "attachment_content" not in response.text.lower()

    # --- Latest selection display formatting tests ---

    def test_latest_selection_block_uses_human_readable_strategy_label(
        self, tmp_path: Path
    ) -> None:
        """Internal strategy key must not appear; display label based on selected_count."""
        storage_dir = _make_storage(tmp_path)
        run_dir = self._write_full_it30_run(storage_dir, "run-strategy-label")
        client = _client(storage_dir)
        response = client.get("/rop")
        assert response.status_code == 200
        html = response.text
        # Internal key must NOT be visible as primary text
        assert "latest_n_by_internaldate_desc" not in html
        # Display label based on selected_count (5) must appear
        assert "Latest 5 messages" in html

    def test_latest_selection_block_ru_human_readable_datetime(
        self, tmp_path: Path
    ) -> None:
        """Russian locale must show DD.MM.YYYY format without raw ISO or UTC offset."""
        storage_dir = _make_storage(tmp_path)
        self._write_full_it30_run(storage_dir, "run-ru-datetime")
        client = _client(storage_dir)
        response = client.get("/rop?lang=ru")
        assert response.status_code == 200
        html = response.text
        # Must NOT contain raw ISO timestamp as visible text
        assert "2026-06-28T12:00:00+00:00" not in html
        # Must NOT contain UTC offset
        assert "+00:00" not in html
        # Must contain DD.MM.YYYY formatted date
        assert "28.06.2026" in html
        # Must contain Russian block title
        assert "Последняя выборка" in html

    def test_latest_selection_block_en_formats_datetime(self, tmp_path: Path) -> None:
        """English locale must show DD.MM.YYYY format without raw ISO."""
        storage_dir = _make_storage(tmp_path)
        self._write_full_it30_run(storage_dir, "run-en-datetime")
        client = _client(storage_dir)
        response = client.get("/rop")
        assert response.status_code == 200
        html = response.text
        # Must NOT contain raw ISO timestamp
        assert "2026-06-28T12:00:00+00:00" not in html
        # Must contain DD.MM.YYYY formatted date
        assert "28.06.2026" in html

    def test_latest_selection_api_preserves_raw_technical_fields(
        self, tmp_path: Path
    ) -> None:
        """API must still return raw strategy key and ISO timestamps for backward compat."""
        storage_dir = _make_storage(tmp_path)
        self._write_full_it30_run(storage_dir, "run-api-raw")
        client = _client(storage_dir)
        response = client.get("/api/rop/dashboard")
        assert response.status_code == 200
        payload = response.json()["data"]["latest_selection"]
        # Raw technical fields must be preserved
        assert payload["strategy"] == "latest_n_by_internaldate_desc"
        assert payload["newest_message_at"] == "2026-06-28T12:00:00+00:00"
        assert payload["oldest_message_at"] == "2026-06-25T07:30:00+00:00"
        # Display fields must also be present
        assert payload["selected_count"] == 5
        assert payload["source_count"] == 1

    def test_latest_selection_period_display(self, tmp_path: Path) -> None:
        """Period display must be shown in the block."""
        storage_dir = _make_storage(tmp_path)
        self._write_full_it30_run(storage_dir, "run-period")
        client = _client(storage_dir)
        response = client.get("/rop")
        assert response.status_code == 200
        html = response.text
        # Period should be shown (newest 28.06, oldest 25.06)
        assert "25.06" in html and "28.06" in html

    def test_latest_selection_single_message(self, tmp_path: Path) -> None:
        """Single message selection must work without errors."""
        storage_dir = _make_storage(tmp_path)
        run_dir = self._write_full_it30_run(storage_dir, "run-single-msg")
        # Override mailbox_selection with single message
        mailbox_selection = {
            "run_id": "run-single-msg",
            "strategy": "latest_n_by_internaldate_desc",
            "sources": [
                {
                    "source_id": "hotline_mailbox",
                    "source_display_name": "Welding Hotline mailbox",
                    "selected_count": 1,
                    "available_count": 5,
                    "messages": [
                        {
                            "source_message_id": "m-001",
                            "internal_date": "2026-06-28T12:00:00+00:00",
                            "message_id": "<m-001@example.com>",
                            "subject": "Test",
                            "selected": True,
                        },
                    ],
                }
            ],
            "warnings": [],
        }
        (run_dir / "mailbox_selection.json").write_text(
            json.dumps(mailbox_selection), encoding="utf-8"
        )
        client = _client(storage_dir)
        response = client.get("/rop")
        assert response.status_code == 200
        assert "Latest 1" in response.text or "Latest selection" in response.text


def _build_auth_settings(enabled: bool = False) -> dict:
    settings = _build_settings()
    settings["web"]["auth"] = {
        "enabled": enabled,
        "mode": "beeui_session",
        "session_secret_env": "BEEAGENT_WEB_SESSION_SECRET",
        "principals": [
            {
                "id": "admin",
                "username": "admin",
                "role": "admin",
                "scopes": ["*"],
                "token_env": "BEEAGENT_WEB_ADMIN_TOKEN",
            },
            {
                "id": "rop",
                "username": "rop",
                "role": "viewer",
                "scopes": ["rop"],
                "token_env": "BEEAGENT_WEB_ROP_TOKEN",
            },
            {
                "id": "operator",
                "username": "operator",
                "role": "operator",
                "scopes": ["dashboard", "rop", "runs", "modules"],
                "token_env": "BEEAGENT_WEB_OPERATOR_TOKEN",
            },
        ],
    }
    return settings


@pytest.mark.parametrize(
    ("env_name", "expected_secure"),
    [
        ("dev", False),
        ("test", False),
        ("local", False),
        ("prod", True),
    ],
)
def test_auth_cookie_secure_tracks_app_env(
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    expected_secure: bool,
) -> None:
    from beeagent_module.interfaces.ui.app import build_beeui_settings

    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-token")
    monkeypatch.setenv("BEEAGENT_WEB_OPERATOR_TOKEN", "operator-token")

    settings = _build_auth_settings(enabled=True)
    settings["app"]["env"] = env_name

    beeui_settings = build_beeui_settings(settings)

    assert beeui_settings["auth"]["cookie_secure"] is expected_secure


def test_auth_service_preserves_secure_cookie_in_prod(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from beeagent_module.interfaces.ui.app import build_beeui_app

    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-token")
    monkeypatch.setenv("BEEAGENT_WEB_OPERATOR_TOKEN", "operator-token")

    settings = _build_auth_settings(enabled=True)
    settings["app"]["env"] = "prod"

    app = build_beeui_app(
        settings=settings,
        logger=_logger(),
        storage_dir=_make_storage(tmp_path),
    )
    client = TestClient(app)

    response = client.post(
        "/auth/login",
        data={"user_id": "admin", "token": "admin-token"},
        follow_redirects=False,
    )

    assert response.status_code in (200, 302)
    assert "secure" in response.headers.get("set-cookie", "").lower()


def _set_auth_env() -> tuple[dict[str, str], dict[str, str | None]]:
    env = {
        "BEEAGENT_WEB_SESSION_SECRET": "test-session-secret-not-for-prod",
        "BEEAGENT_WEB_ADMIN_TOKEN": "admin-test-token",
        "BEEAGENT_WEB_ROP_TOKEN": "rop-test-token",
        "BEEAGENT_WEB_OPERATOR_TOKEN": "operator-test-token",
    }
    previous = {key: os.environ.get(key) for key in env}
    for k, v in env.items():
        os.environ[k] = v
    return env, previous


def _clear_auth_env(
    env: dict[str, str],
    previous: dict[str, str | None],
) -> None:
    for key in env:
        old_value = previous.get(key)
        if old_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old_value


def _auth_client(storage_dir: Path) -> TestClient:
    from beeagent_module.interfaces.ui.app import build_beeui_app

    settings = _build_auth_settings(enabled=True)
    _write_rop_web_projection(storage_dir, settings)
    app = build_beeui_app(
        settings=settings,
        logger=_logger(),
        storage_dir=storage_dir,
    )
    return TestClient(app)


def test_auth_disabled_current_behavior(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-auth-off")
    client = _client(storage_dir)
    for path in ["/", "/health", "/rop", "/runs", "/modules"]:
        response = client.get(path)
        assert response.status_code == 200, f"GET {path} should be 200"
    for path in ["/api/dashboard", "/api/modules", "/api/rop/dashboard"]:
        response = client.get(path)
        assert response.status_code == 200, f"GET {path} should be 200"


def test_auth_disabled_no_env_vars_required(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.app import build_beeui_app

    settings = _build_settings()
    storage_dir = _make_storage(tmp_path)
    app = build_beeui_app(
        settings=settings,
        logger=_logger(),
        storage_dir=storage_dir,
    )
    assert app is not None


def test_auth_enabled_fails_fast_without_beeui_auth_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from fastapi import FastAPI

    from beeagent_module.interfaces.ui import app as ui_app

    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-token")
    monkeypatch.setenv("BEEAGENT_WEB_OPERATOR_TOKEN", "operator-token")

    settings = _build_auth_settings(enabled=True)

    def fake_create_beeui_app(**_: Any) -> FastAPI:
        return FastAPI()

    monkeypatch.setattr(ui_app, "create_beeui_app", fake_create_beeui_app)

    with pytest.raises(RuntimeError, match="BeeUI auth service is required"):
        ui_app.build_beeui_app(
            settings=settings,
            logger=_logger(),
            storage_dir=_make_storage(tmp_path),
        )


def test_auth_disabled_non_loopback_host_rejected() -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_full_settings()
    settings["web"]["host"] = "0.0.0.0"
    settings["web"]["auth"]["enabled"] = False

    with pytest.raises(RuntimeError, match="web.auth.enabled=false"):
        validate_settings(settings)


class TestAuthEnabled:
    _env: dict[str, str] = {}
    _previous_env: dict[str, str | None] = {}

    @classmethod
    def setup_class(cls) -> None:
        cls._env, cls._previous_env = _set_auth_env()

    @classmethod
    def teardown_class(cls) -> None:
        _clear_auth_env(cls._env, cls._previous_env)

    def _login(self, client: TestClient, user_id: str, token: str) -> Any:
        return client.post("/auth/login", data={"user_id": user_id, "token": token})

    def test_unauthenticated_rop_protected(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth")
        client = _auth_client(storage_dir)
        response = client.get("/rop", follow_redirects=False)
        assert response.status_code in (302, 401)

    def test_unauthenticated_api_returns_401(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth")
        client = _auth_client(storage_dir)
        response = client.get("/api/rop/dashboard")
        assert response.status_code == 401

    def test_health_remains_public(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _auth_client(storage_dir)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_static_remains_public(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _auth_client(storage_dir)
        response = client.get("/static/")
        assert response.status_code in (200, 404)

    def test_admin_can_access_rop(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth")
        client = _auth_client(storage_dir)
        login_resp = self._login(client, "admin", "admin-test-token")
        assert login_resp.status_code in (302, 200)
        response = client.get("/rop", follow_redirects=False)
        assert response.status_code == 200

    def test_rop_queue_uses_cookie_locale_on_first_load(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        run_dir = _write_run_artifacts(storage_dir, "run-auth-cookie")
        (run_dir / "classified_events.json").write_text(
            json.dumps(
                [
                    {
                        "event_id": "evt-1",
                        "source_id": "hotline_mailbox",
                        "case_type": "existing_deal",
                        "priority": "high",
                        "sender": "client@example.com",
                        "subject": "Follow-up on quote",
                    }
                ]
            ),
            encoding="utf-8",
        )
        client = _auth_client(storage_dir)
        self._login(client, "admin", "admin-test-token")
        client.cookies.set("beeui_lang", "ru")
        response = client.get("/rop?tab=queue")

        assert response.status_code == 200
        assert "Существующая сделка" in response.text
        assert "Existing deal" not in response.text
        client.close()

    def test_rop_queue_lang_query_overrides_cookie(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        run_dir = _write_run_artifacts(storage_dir, "run-auth-cookie-en")
        (run_dir / "classified_events.json").write_text(
            json.dumps(
                [
                    {
                        "event_id": "evt-1",
                        "source_id": "hotline_mailbox",
                        "case_type": "existing_deal",
                        "priority": "high",
                        "sender": "client@example.com",
                        "subject": "Follow-up on quote",
                    }
                ]
            ),
            encoding="utf-8",
        )
        client = _auth_client(storage_dir)
        self._login(client, "admin", "admin-test-token")
        client.cookies.set("beeui_lang", "ru")
        response = client.get("/rop?tab=queue&lang=en")

        assert response.status_code == 200
        assert "Existing deal" in response.text
        assert "Существующая сделка" not in response.text
        client.close()

    def test_admin_can_access_api(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth")
        client = _auth_client(storage_dir)
        self._login(client, "admin", "admin-test-token")
        response = client.get("/api/rop/dashboard")
        assert response.status_code == 200

    def test_operator_principal_keeps_operator_role(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        from beeui_module.auth.models import UserRole

        from beeagent_module.interfaces.ui.app import build_beeui_app

        monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
        monkeypatch.setenv("BEEAGENT_WEB_ADMIN_TOKEN", "admin-test-token")
        monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-test-token")
        monkeypatch.setenv("BEEAGENT_WEB_OPERATOR_TOKEN", "operator-test-token")

        settings = _build_auth_settings(enabled=True)

        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-operator-role")
        _write_rop_web_projection(storage_dir, settings)

        app = build_beeui_app(
            settings=settings,
            logger=_logger(),
            storage_dir=storage_dir,
        )
        service = app.state.beeui_auth_service

        assert service._resolve_role("admin-test-token") == UserRole.admin
        assert service._resolve_role("operator-test-token") == UserRole.operator

        client = TestClient(app)
        login_resp = client.post(
            "/auth/login",
            data={"user_id": "operator", "token": "operator-test-token"},
        )
        assert login_resp.status_code in (302, 200)

        response = client.get("/api/rop/dashboard")
        assert response.status_code == 200

    def test_invalid_token_rejected(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _auth_client(storage_dir)
        login_resp = self._login(client, "admin", "wrong-token")
        assert login_resp.status_code == 401

    def test_protected_route_fails_closed_if_auth_service_removed(
        self,
        tmp_path: Path,
    ) -> None:
        from beeagent_module.interfaces.ui.app import build_beeui_app

        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth-service-missing")

        app = build_beeui_app(
            settings=_build_auth_settings(enabled=True),
            logger=_logger(),
            storage_dir=storage_dir,
        )
        app.state.beeui_auth_service = None

        client = TestClient(app)
        response = client.get("/api/rop/dashboard")

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "auth_unavailable"

    def test_unknown_api_path_requires_auth_before_404(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _auth_client(storage_dir)

        response = client.get("/api/not-existing")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthenticated"


def _set_scoped_auth_env() -> tuple[dict[str, str], dict[str, str | None]]:
    env = {
        "BEEAGENT_WEB_SESSION_SECRET": "scoped-session-secret",
        "BEEAGENT_WEB_ADMIN1_TOKEN": "admin1-test-token",
        "BEEAGENT_WEB_ADMIN2_TOKEN": "admin2-test-token",
        "BEEAGENT_WEB_ROPVIEWER_TOKEN": "ropviewer-test-token",
        "BEEAGENT_WEB_ROPADMIN_TOKEN": "ropadmin-test-token",
    }
    previous = {key: os.environ.get(key) for key in env}
    for k, v in env.items():
        os.environ[k] = v
    return env, previous


def _clear_scoped_auth_env(
    env: dict[str, str],
    previous: dict[str, str | None],
) -> None:
    for key in env:
        old_value = previous.get(key)
        if old_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old_value


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
                "id": "rop_admin_1",
                "username": "ropadmin",
                "role": "admin",
                "scopes": ["rop"],
                "token_env": "BEEAGENT_WEB_ROPADMIN_TOKEN",
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


class TestPrincipalScopedAuthorization:
    _env: dict[str, str] = {}
    _previous_env: dict[str, str | None] = {}

    @classmethod
    def setup_class(cls) -> None:
        cls._env, cls._previous_env = _set_scoped_auth_env()

    @classmethod
    def teardown_class(cls) -> None:
        _clear_scoped_auth_env(cls._env, cls._previous_env)

    def _client(self, tmp_path: Path) -> TestClient:
        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth")
        return _scoped_auth_client(storage_dir)

    def _login(
        self,
        client: TestClient,
        user_id: str,
        token: str,
        follow_redirects: bool = True,
    ) -> Any:
        return client.post(
            "/auth/login",
            data={"user_id": user_id, "token": token},
            follow_redirects=follow_redirects,
        )

    def test_exact_username_token_success(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        resp = self._login(client, "admin1", "admin1-test-token")
        assert resp.status_code in (302, 200)
        assert client.get("/", follow_redirects=False).status_code == 200

    def test_rop_viewer_exact_username_token_success(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        resp = self._login(
            client,
            "ropviewer",
            "ropviewer-test-token",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert client.get("/rop", follow_redirects=False).status_code == 200

    def test_wrong_username_valid_token_rejected(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        resp = self._login(client, "nobody", "admin1-test-token")
        assert resp.status_code == 401

    def test_another_principal_username_valid_token_rejected(
        self,
        tmp_path: Path,
    ) -> None:
        client = self._client(tmp_path)
        resp = self._login(client, "admin2", "admin1-test-token")
        assert resp.status_code == 401

    def test_correct_username_wrong_token_rejected(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        resp = self._login(client, "admin1", "wrong-token")
        assert resp.status_code == 401

    def test_failure_response_does_not_expose_credentials(
        self,
        tmp_path: Path,
    ) -> None:
        client = self._client(tmp_path)
        resp = self._login(client, "admin1", "wrong-token")
        assert "wrong-token" not in resp.text
        assert "admin1-test-token" not in resp.text

    def test_canonical_configured_session_identity(self, tmp_path: Path) -> None:
        from beeagent_module.interfaces.ui.app import build_beeui_app

        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth")
        app = build_beeui_app(
            settings=_build_scoped_auth_settings(),
            logger=_logger(),
            storage_dir=storage_dir,
        )
        client = TestClient(app)
        self._login(client, "admin1", "admin1-test-token")

        service = app.state.beeui_auth_service
        cookie = client.cookies.get(service.cookie_name())
        session = service.verify_session(cookie)
        assert session is not None
        assert session.user_id == "admin_1"

    def test_admin_wildcard_full_html_access(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "admin1", "admin1-test-token")
        for path in ["/", "/rop", "/runs", "/runs/run-auth", "/modules"]:
            response = client.get(path, follow_redirects=False)
            assert response.status_code in (200, 404), f"GET {path} should be allowed"

    def test_admin_wildcard_full_api_access(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "admin1", "admin1-test-token")
        for path in [
            "/api/dashboard",
            "/api/runs",
            "/api/modules",
            "/api/rop/dashboard",
        ]:
            response = client.get(path)
            assert response.status_code == 200, f"GET {path} should be allowed"

    def test_rop_viewer_allowed_html_matrix(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "ropviewer", "ropviewer-test-token")
        assert client.get("/rop", follow_redirects=False).status_code == 200
        evt = client.get("/rop/events/evt-1?run_id=run-auth")
        assert evt.status_code != 403
        evidence = client.get(
            "/runs/run-auth/artifacts/operator_summary_json",
            follow_redirects=False,
        )
        assert evidence.status_code != 403

    def test_rop_viewer_allowed_api_matrix(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "ropviewer", "ropviewer-test-token")
        assert client.get("/api/rop/dashboard").status_code == 200
        evt = client.get("/api/rop/events/evt-1?run_id=run-auth")
        assert evt.status_code != 403
        evidence = client.get("/api/runs/run-auth/artifacts/operator_summary_json")
        assert evidence.status_code != 403

    def test_rop_viewer_forbidden_html_matrix(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "ropviewer", "ropviewer-test-token")
        for path in [
            "/runs",
            "/runs/run-auth",
            "/runs/run-auth/artifacts",
            "/modules",
            "/components",
        ]:
            response = client.get(path, follow_redirects=False)
            assert response.status_code == 403, f"GET {path} should be denied"

    def test_rop_viewer_forbidden_api_matrix(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "ropviewer", "ropviewer-test-token")
        for path in [
            "/api/dashboard",
            "/api/runs",
            "/api/runs/run-auth",
            "/api/runs/run-auth/artifacts",
            "/api/modules",
        ]:
            response = client.get(path)
            assert response.status_code == 403, f"GET {path} should be denied"

    def test_rop_viewer_denied_unrelated_artifact(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "ropviewer", "ropviewer-test-token")
        assert (
            client.get(
                "/runs/run-auth/artifacts/run_json",
                follow_redirects=False,
            ).status_code
            == 403
        )
        assert client.get("/api/runs/run-auth/artifacts/run_json").status_code == 403

    def test_unknown_protected_surface_default_deny(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "ropviewer", "ropviewer-test-token")
        assert client.get("/components", follow_redirects=False).status_code == 403
        assert client.get("/api/unknown-surface").status_code == 403

    def test_unauthenticated_differs_from_forbidden(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        unauthed = client.get("/api/runs")
        assert unauthed.status_code == 401
        assert unauthed.json()["error"]["code"] == "unauthenticated"

        self._login(client, "ropviewer", "ropviewer-test-token")
        forbidden = client.get("/api/runs")
        assert forbidden.status_code == 403
        assert forbidden.json()["error"]["code"] == "forbidden"

    def test_rop_viewer_landing_redirects_to_rop(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        login_resp = self._login(
            client,
            "ropviewer",
            "ropviewer-test-token",
            follow_redirects=False,
        )
        assert login_resp.status_code == 302
        assert login_resp.headers["location"] == "/"

        landing = client.get(
            "/", headers={"accept": "text/html"}, follow_redirects=False
        )
        assert landing.status_code == 303
        assert landing.headers["location"] == "/rop"

    def test_rop_viewer_direct_dashboard_url_denied(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "ropviewer", "ropviewer-test-token")
        api = client.get("/api/dashboard")
        assert api.status_code == 403
        assert api.json()["error"]["code"] == "forbidden"

    def test_role_does_not_grant_resource_scope(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "ropadmin", "ropadmin-test-token")
        assert client.get("/rop", follow_redirects=False).status_code == 200
        assert client.get("/api/dashboard").status_code == 403
        assert client.get("/api/runs").status_code == 403

    def test_unmapped_future_scope_gets_403(self, tmp_path: Path) -> None:
        from beeagent_module.interfaces.ui.app import build_beeui_app

        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth")
        settings = _build_scoped_auth_settings()
        settings["web"]["auth"]["principals"][2]["scopes"] = ["beescan"]
        app = build_beeui_app(
            settings=settings,
            logger=_logger(),
            storage_dir=storage_dir,
        )
        client = TestClient(app)
        self._login(client, "ropviewer", "ropviewer-test-token")

        assert client.get("/rop", follow_redirects=False).status_code == 403
        assert client.get("/api/rop/dashboard").status_code == 403
        assert client.get("/api/runs").status_code == 403

    def test_rop_viewer_navigation_hides_unrelated_items(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "ropviewer", "ropviewer-test-token")
        html = client.get("/rop", headers={"accept": "text/html"}).text
        assert 'href="/rop"' in html
        assert 'data-beeui-icon="dashboard"' not in html
        assert 'data-beeui-icon="runs"' not in html
        assert 'href="/runs"' not in html
        assert 'href="/modules"' not in html
        assert 'nav-link-title">Dashboard</span>' not in html

    def test_admin_navigation_shows_all_items(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "admin1", "admin1-test-token")
        html = client.get("/", headers={"accept": "text/html"}).text
        assert 'data-beeui-icon="dashboard"' in html
        assert 'data-beeui-icon="runs"' in html
        assert 'href="/runs"' in html
        assert 'href="/modules"' in html
        assert 'href="/rop"' in html

    def test_rop_viewer_navigation_hides_ru_locale(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "ropviewer", "ropviewer-test-token")
        html = client.get("/rop?lang=ru", headers={"accept": "text/html"}).text
        assert 'href="/rop' in html
        assert 'data-beeui-icon="dashboard"' not in html
        assert 'data-beeui-icon="runs"' not in html
        assert 'href="/runs' not in html
        assert 'href="/modules' not in html

    def test_bitrix_external_session_bounded_rop(self, tmp_path: Path) -> None:
        from beeui_module.auth.models import UserRole

        from beeagent_module.interfaces.ui.app import build_beeui_app

        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth")
        _write_rop_web_projection(storage_dir, _build_scoped_auth_settings())
        app = build_beeui_app(
            settings=_build_scoped_auth_settings(),
            logger=_logger(),
            storage_dir=storage_dir,
        )
        client = TestClient(app)

        service = app.state.beeui_auth_service
        _, cookie = service.create_principal_session("bitrix:42", UserRole.viewer)
        client.cookies.set(service.cookie_name(), cookie)

        assert client.get("/rop", follow_redirects=False).status_code == 200
        assert client.get("/api/rop/dashboard").status_code == 200
        assert (
            client.get(
                "/", headers={"accept": "text/html"}, follow_redirects=False
            ).status_code
            == 303
        )
        assert client.get("/api/runs").status_code == 403
        assert client.get("/api/modules").status_code == 403
        assert (
            client.get(
                "/runs/run-auth/artifacts/run_json",
                follow_redirects=False,
            ).status_code
            == 403
        )

    def test_unknown_signed_principal_denied(self, tmp_path: Path) -> None:
        from beeui_module.auth.models import UserRole

        from beeagent_module.interfaces.ui.app import build_beeui_app

        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth")
        app = build_beeui_app(
            settings=_build_scoped_auth_settings(),
            logger=_logger(),
            storage_dir=storage_dir,
        )
        client = TestClient(app)

        service = app.state.beeui_auth_service
        _, cookie = service.create_principal_session("unknown-user", UserRole.viewer)
        client.cookies.set(service.cookie_name(), cookie)

        assert client.get("/rop", follow_redirects=False).status_code == 403
        assert client.get("/api/rop/dashboard").status_code == 403
        assert client.get("/api/runs").status_code == 403

    def test_legacy_numeric_signed_principal_denied(self, tmp_path: Path) -> None:
        from beeui_module.auth.models import UserRole

        from beeagent_module.interfaces.ui.app import build_beeui_app

        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth")
        app = build_beeui_app(
            settings=_build_scoped_auth_settings(),
            logger=_logger(),
            storage_dir=storage_dir,
        )
        client = TestClient(app)

        service = app.state.beeui_auth_service
        _, cookie = service.create_principal_session("42", UserRole.viewer)
        client.cookies.set(service.cookie_name(), cookie)

        assert client.get("/rop", follow_redirects=False).status_code == 403
        assert client.get("/api/rop/dashboard").status_code == 403

    def test_rop_viewer_non_rop_run_denied(self, tmp_path: Path) -> None:
        from beeagent_module.interfaces.ui.app import build_beeui_app

        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth")
        _write_non_rop_run(storage_dir, "run-non-rop")
        _write_rop_web_projection(storage_dir, _build_scoped_auth_settings())
        app = build_beeui_app(
            settings=_build_scoped_auth_settings(),
            logger=_logger(),
            storage_dir=storage_dir,
        )
        client = TestClient(app)
        self._login(client, "ropviewer", "ropviewer-test-token")

        for path in [
            "/rop?run_id=run-non-rop",
            "/rop/events/evt-1?run_id=run-non-rop",
        ]:
            response = client.get(
                path, headers={"accept": "text/html"}, follow_redirects=False
            )
            assert response.status_code == 403, f"GET {path} should be denied"

        for path in [
            "/api/rop/dashboard?run_id=run-non-rop",
            "/api/rop/events/evt-1?run_id=run-non-rop",
        ]:
            response = client.get(path)
            assert response.status_code == 403, f"GET {path} should be denied"

        assert (
            client.get(
                "/runs/run-non-rop/artifacts/operator_summary_json",
                follow_redirects=False,
            ).status_code
            == 403
        )
        assert (
            client.get(
                "/runs/run-non-rop/artifacts/classified_events_json",
                follow_redirects=False,
            ).status_code
            == 403
        )
        assert (
            client.get(
                "/api/runs/run-non-rop/artifacts/operator_summary_json"
            ).status_code
            == 403
        )

        assert client.get("/rop?run_id=run-auth").status_code == 200
        assert (
            client.get(
                "/runs/run-auth/artifacts/operator_summary_json",
                follow_redirects=False,
            ).status_code
            != 403
        )

    def test_logout_invalidates_session(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "ropviewer", "ropviewer-test-token")
        client.post("/auth/logout")
        assert client.get("/rop", follow_redirects=False).status_code in (302, 401)


def _build_valid_enabled_auth_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> dict:
    settings = _build_full_settings()
    settings["web"]["auth"] = {
        "enabled": True,
        "mode": "beeui_session",
        "session_secret_env": "BEEAGENT_WEB_SESSION_SECRET",
        "principals": [
            {
                "id": "admin",
                "username": "admin",
                "role": "admin",
                "scopes": ["*"],
                "token_env": "BEEAGENT_WEB_ADMIN_TOKEN",
            },
            {
                "id": "rop",
                "username": "rop",
                "role": "viewer",
                "scopes": ["rop"],
                "token_env": "BEEAGENT_WEB_ROP_TOKEN",
            },
            {
                "id": "operator",
                "username": "operator",
                "role": "operator",
                "scopes": ["dashboard", "rop", "runs", "modules"],
                "token_env": "BEEAGENT_WEB_OPERATOR_TOKEN",
            },
        ],
    }
    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-token")
    monkeypatch.setenv("BEEAGENT_WEB_OPERATOR_TOKEN", "operator-token")
    return settings


def test_auth_settings_fail_fast_missing_session_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    monkeypatch.delenv("BEEAGENT_WEB_SESSION_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="BEEAGENT_WEB_SESSION_SECRET"):
        validate_settings(settings)


def test_auth_settings_fail_fast_missing_admin_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    monkeypatch.delenv("BEEAGENT_WEB_ADMIN_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="BEEAGENT_WEB_ADMIN_TOKEN"):
        validate_settings(settings)


def test_auth_settings_fail_fast_duplicate_principal_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    settings["web"]["auth"]["principals"][1]["id"] = "admin"

    with pytest.raises(RuntimeError, match="Duplicate web.auth.principals id"):
        validate_settings(settings)


def test_auth_settings_fail_fast_duplicate_username(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    settings["web"]["auth"]["principals"][1]["username"] = "admin"

    with pytest.raises(RuntimeError, match="Duplicate web.auth.principals username"):
        validate_settings(settings)


def test_auth_settings_fail_fast_duplicate_token_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    settings["web"]["auth"]["principals"][1]["token_env"] = "BEEAGENT_WEB_ADMIN_TOKEN"

    with pytest.raises(RuntimeError, match="Duplicate web.auth.principals token_env"):
        validate_settings(settings)


def test_auth_settings_fail_fast_invalid_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    settings["web"]["auth"]["principals"][1]["role"] = "superadmin"

    with pytest.raises(RuntimeError, match="Invalid web.auth.principals\\[1\\].role"):
        validate_settings(settings)


def test_auth_settings_fail_fast_missing_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    settings["web"]["auth"]["principals"][1].pop("scopes")

    with pytest.raises(RuntimeError, match="scopes"):
        validate_settings(settings)


def test_auth_settings_fail_fast_empty_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    settings["web"]["auth"]["principals"][1]["scopes"] = []

    with pytest.raises(RuntimeError, match="scopes"):
        validate_settings(settings)


def test_auth_settings_accepts_future_safe_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.paths import get_project_root
    from beeagent_module.core.settings import load_settings, validate_settings

    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-token")
    monkeypatch.setenv("BEEAGENT_WEB_OPERATOR_TOKEN", "operator-token")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    settings = load_settings(get_project_root() / "config" / "settings.yml")
    settings["web"]["auth"]["principals"][1]["scopes"] = ["beescan"]
    validate_settings(settings)


@pytest.mark.parametrize(
    "bad_scope",
    [
        "Beescan",
        "ROP",
        "rop/",
        "/rop",
        "ro p",
        "rop ",
        " rop",
        "röp",
        "..",
        "-rop",
        "9rop",
        "ro-p/",
    ],
)
def test_auth_settings_fail_fast_malformed_scope(
    monkeypatch: pytest.MonkeyPatch,
    bad_scope: str,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    settings["web"]["auth"]["principals"][1]["scopes"] = [bad_scope]

    with pytest.raises(RuntimeError, match="safe lowercase scope identifier"):
        validate_settings(settings)


def test_auth_settings_fail_fast_duplicate_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    settings["web"]["auth"]["principals"][1]["scopes"] = ["rop", "rop"]

    with pytest.raises(RuntimeError, match="Duplicate web.auth.principals"):
        validate_settings(settings)


def test_auth_settings_fail_fast_wildcard_with_other_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    settings["web"]["auth"]["principals"][1]["scopes"] = ["*", "rop"]

    with pytest.raises(RuntimeError, match="wildcard"):
        validate_settings(settings)


def test_auth_settings_accepts_wildcard_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.paths import get_project_root
    from beeagent_module.core.settings import load_settings, validate_settings

    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-token")
    monkeypatch.setenv("BEEAGENT_WEB_OPERATOR_TOKEN", "operator-token")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    settings = load_settings(get_project_root() / "config" / "settings.yml")
    validate_settings(settings)


def test_auth_settings_accepts_multiple_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.paths import get_project_root
    from beeagent_module.core.settings import load_settings, validate_settings

    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-token")
    monkeypatch.setenv("BEEAGENT_WEB_OPERATOR_TOKEN", "operator-token")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    settings = load_settings(get_project_root() / "config" / "settings.yml")
    settings["web"]["auth"]["principals"][1]["scopes"] = ["rop", "runs"]
    validate_settings(settings)


def test_auth_settings_fail_fast_duplicate_resolved_token_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "admin-token")

    with pytest.raises(RuntimeError, match="Duplicate resolved token value"):
        validate_settings(settings)


def test_auth_settings_duplicate_resolved_token_error_does_not_expose_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "admin-token")

    with pytest.raises(RuntimeError, match="Duplicate resolved token value") as exc:
        validate_settings(settings)

    assert "admin-token" not in str(exc.value)


def _build_full_settings() -> dict:
    return {
        "app": {"name": "BeeAgent", "env": "test"},
        "run": {"mode": "telegram"},
        "web": {
            "host": "127.0.0.1",
            "port": 8000,
            "open_browser": False,
            "auth": {
                "enabled": False,
                "mode": "beeui_session",
                "session_secret_env": "BEEAGENT_WEB_SESSION_SECRET",
                "principals": [],
            },
        },
        "telegram": {
            "enabled": False,
            "bot_token_env": "T",
            "chat_id_env": "T",
            "telemetry_enabled": False,
        },
        "logging": {"clear_logs": True, "utc": True, "level": "INFO"},
        "mock": {"seed": 1, "weeks": 1, "stores": 1, "skus": 1, "category": "X"},
        "data": {"adapter": "mock"},
        "scheduler": {"enabled": False, "interval": 100, "start_run": True},
        "approval": {"reject_reason": "R"},
        "promo": {"stock_min": 1, "units_max": 1},
        "i18n": {"lang": "ru", "path": "i18n.yml"},
        "quiz": {"enabled": False, "path": "q.json"},
        "modules": {"registry": []},
        "rop": {
            "email_preview": {
                "body_chars_max": 4000,
            },
            "ai_assist": {
                "enabled": False,
                "events_max": 20,
                "request_timeout": 30,
                "ai_confidence_min": 0.70,
                "dry_run": False,
                "adjudicator": {
                    "enabled": False,
                    "timeout": 20,
                    "input_chars_max": 8000,
                    "confidence_accept_min": 0.70,
                    "events_max": 20,
                    "attachment_chars_max": 2000,
                    "prompt_key": "rop.ai_adjudicator",
                },
            },
            "routing": {
                "queues": {
                    "sales": {"bitrix_category": "sales"},
                    "tender": {"bitrix_category": "tenders"},
                    "logistics": {"bitrix_category": "logistics"},
                    "finance": {"bitrix_category": "finance"},
                    "procurement": {"bitrix_category": "procurement"},
                    "manual_review": {"bitrix_category": "manual_review"},
                },
            },
            "attachments": {
                "enabled": False,
                "chars_max": 100,
                "size_max": 100,
                "types": ["text/plain"],
                "storage": {
                    "enabled": True,
                    "file_max": 1048576,
                    "message_max": 2097152,
                    "files_message_max": 10,
                },
                "extraction": {
                    "engine": "docling",
                    "chars_max": 2000,
                    "pages_max": 20,
                    "timeout_seconds": 30,
                    "ocr_enabled": True,
                },
            },
            "sources": [],
            "dashboard": {
                "default_period": "7d",
                "periods": ["today", "yesterday", "7d", "30d", "90d", "365d", "all"],
            },
        },
        "bitrix": {
            "enabled": False,
            "webhook_env": "BITRIX_WEBHOOK_URL",
            "timeout": 10,
            "page_size": 50,
            "pages_max": 3,
            "types_entity": [1, 2, 3, 4],
            "reconciliation": {
                "enabled": False,
                "candidate_limit": 20,
                "window_date": 180,
                "correlation": {
                    "enabled": True,
                    "window_days": 180,
                },
            },
            "widget": {
                "enabled": False,
                "token_env": "BITRIX_ROP_WIDGET_TOKEN",
                "default_period": "7d",
                "max_items": 50,
            },
            "embedded_app": {
                "enabled": False,
                "portal_origin": "",
                "default_role": "viewer",
                "request_timeout": 10,
            },
        },
        "ai": {
            "prompts": {"path": "p.yml", "store": False},
            "profiles": {
                "openai": {
                    "enabled": True,
                    "provider": "openai_responses",
                    "api_key_env": "K",
                    "base_url": "https://x",
                    "model": "gpt",
                },
                "deepseek": {
                    "enabled": False,
                    "provider": "openai_compatible",
                    "api_key_env": "DEEPSEEK_API_KEY",
                    "base_url": "https://api.deepseek.com/v1",
                    "model": "deepseek-chat",
                },
                "lmstudio": {
                    "enabled": False,
                    "provider": "openai_compatible",
                    "api_key_env": "LMSTUDIO_API_KEY",
                    "base_url": "http://127.0.0.1:1234/v1",
                    "model": "local-model",
                },
                "custom": {
                    "enabled": False,
                    "provider": "openai_compatible",
                    "api_key_env": "CUSTOM_AI_API_KEY",
                    "base_url": "https://example.test/v1",
                    "model": "custom-model",
                },
            },
        },
    }


def test_rop_recommendations_tab_matches_widget_items(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_run_artifacts(storage_dir, "run-rec-tab")
    recommendations = {
        "run_id": "run-rec-tab",
        "status": "ok",
        "read_only": True,
        "draft_only": True,
        "safe_to_execute": False,
        "aggregate": {
            "event_count": 1,
            "recommendation_count": 1,
            "ignore_count": 0,
            "manual_review_count": 0,
            "actionable_count": 1,
        },
        "items": [
            {
                "event_id": "evt-1",
                "sender": "test@example.com",
                "subject": "Test",
                "title": "Review new request",
                "summary": "Review the request details.",
                "recommended_action": "create_lead_draft",
                "recommended_queue": "sales",
                "target_bitrix_category": "sales",
                "priority": "high",
                "reason": "No Bitrix entity found.",
                "confidence": 0.91,
                "ai_used": False,
                "bitrix_status": "not_found",
                "safe_to_execute": True,
                "requires_human_confirmation": False,
                "evidence_links": [
                    "/api/runs/run-rec-tab/artifacts/classified_events_json"
                ],
            }
        ],
        "warnings": [],
    }
    (run_dir / "rop_recommendations.json").write_text(
        json.dumps(recommendations), encoding="utf-8"
    )

    settings = _build_settings()
    settings["bitrix"] = {
        "widget": {
            "enabled": True,
            "token_env": "BITRIX_ROP_WIDGET_TOKEN",
            "default_period": "7d",
            "max_items": 50,
        }
    }
    monkeypatch.setenv("BITRIX_ROP_WIDGET_TOKEN", "widget-token")
    client = _client(storage_dir, settings=settings)

    html_response = client.get(
        "/rop", params={"tab": "recommendations", "run_id": "run-rec-tab"}
    )
    assert html_response.status_code == 200
    assert "No recommendations" not in html_response.text
    assert "Review new request" in html_response.text
    assert "evt-1" in html_response.text
    assert "create_lead_draft" in html_response.text
    assert "sales" in html_response.text
    assert "not_found" in html_response.text
    assert "0.91" in html_response.text
    assert "Evidence" in html_response.text
    assert "/rop/events/evt-1?run_id=run-rec-tab" in html_response.text

    widget_response = client.get(
        "/api/bitrix/rop/widget",
        params={"run_id": "run-rec-tab"},
        headers={"Authorization": "Bearer widget-token"},
    )
    assert widget_response.status_code == 200
    widget_items = widget_response.json()["data"]["items"]
    assert [item["event_id"] for item in widget_items] == ["evt-1"]
    assert widget_items[0]["title"] == "Review new request"
    assert widget_items[0]["sender"] == "test@example.com"
    assert widget_items[0]["subject"] == "Test"
    assert widget_items[0]["safe_to_execute"] is False
    assert widget_items[0]["requires_human_confirmation"] is True
    assert widget_items[0]["evidence_links"] == [
        "/api/runs/run-rec-tab/artifacts/classified_events_json"
    ]
    assert widget_items[0]["detail_url"].endswith(
        "/api/bitrix/rop/widget/events/evt-1?run_id=run-rec-tab"
    )
    final_decisions = widget_response.json()["data"]["final_decisions"]
    assert isinstance(final_decisions["summary"], dict)
    assert isinstance(final_decisions["events"], list)

    detail_response = client.get(
        "/api/bitrix/rop/widget/events/evt-1",
        params={"run_id": "run-rec-tab"},
        headers={"Authorization": "Bearer widget-token"},
    )
    assert detail_response.status_code == 200
    detail_item = detail_response.json()["data"]
    assert detail_item["sender"] == "test@example.com"
    assert detail_item["subject"] == "Test"
    assert detail_item["safe_to_execute"] is False
    assert detail_item["requires_human_confirmation"] is True
    assert detail_item["evidence_links"] == [
        "/api/runs/run-rec-tab/artifacts/classified_events_json"
    ]
    assert detail_item["final_decision"]["event_id"] == "evt-1"
    assert detail_item["final_decision"]["automation_allowed"] is False
    assert detail_item["final_decision"]["bitrix_write_allowed"] is False


def test_widget_api_allows_bearer_without_beeui_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_run_artifacts(storage_dir, "run-widget-auth")
    (run_dir / "rop_recommendations.json").write_text(
        json.dumps(
            {
                "run_id": "run-widget-auth",
                "items": [
                    {
                        "event_id": "evt-1",
                        "title": "Widget item",
                        "summary": "Summary",
                        "sender": "sender@example.com",
                        "subject": "Subject",
                        "recommended_action": "create_lead_draft",
                        "recommended_queue": "sales",
                        "target_bitrix_category": "sales",
                        "priority": "high",
                        "reason": "Reason",
                        "confidence": 0.95,
                        "ai_used": False,
                        "bitrix_status": "not_found",
                        "safe_to_execute": False,
                        "requires_human_confirmation": True,
                        "evidence_links": [
                            "/api/runs/run-widget-auth/artifacts/classified_events_json"
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    settings = _build_auth_settings(enabled=True)
    settings["bitrix"] = {
        "widget": {
            "enabled": True,
            "token_env": "BITRIX_ROP_WIDGET_TOKEN",
            "default_period": "7d",
            "max_items": 50,
        }
    }
    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-token")
    monkeypatch.setenv("BEEAGENT_WEB_OPERATOR_TOKEN", "operator-token")
    monkeypatch.setenv("BITRIX_ROP_WIDGET_TOKEN", "widget-token")

    client = _client(storage_dir, settings=settings)
    response = client.get(
        "/api/bitrix/rop/widget",
        params={"run_id": "run-widget-auth"},
        headers={"Authorization": "Bearer widget-token"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["event_id"] == "evt-1"


def test_widget_api_rejects_missing_or_invalid_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_run_artifacts(storage_dir, "run-widget-401")
    (run_dir / "rop_recommendations.json").write_text(
        json.dumps({"run_id": "run-widget-401", "items": []}),
        encoding="utf-8",
    )

    settings = _build_auth_settings(enabled=True)
    settings["bitrix"] = {
        "widget": {
            "enabled": True,
            "token_env": "BITRIX_ROP_WIDGET_TOKEN",
            "default_period": "7d",
            "max_items": 50,
        }
    }
    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-token")
    monkeypatch.setenv("BEEAGENT_WEB_OPERATOR_TOKEN", "operator-token")
    monkeypatch.setenv("BITRIX_ROP_WIDGET_TOKEN", "widget-token")

    client = _client(storage_dir, settings=settings)
    missing = client.get("/api/bitrix/rop/widget", params={"run_id": "run-widget-401"})
    invalid = client.get(
        "/api/bitrix/rop/widget",
        params={"run_id": "run-widget-401"},
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert missing.status_code == 401
    assert invalid.status_code == 401


def test_widget_api_returns_final_decisions_block(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rich_rop_run(storage_dir, "run-widget-fd")
    final_decisions = {
        "summary": {
            "total_events": 2,
            "decision_source_counts": {"deterministic": 2},
            "attention_count": 0,
        },
        "events": [
            {
                "event_id": "evt-001",
                "final_case_type": "new_lead",
                "final_case_subtype": None,
                "final_queue": "sales",
                "final_action": "review_new_lead",
                "final_decision_source": "deterministic",
                "final_confidence": 0.85,
                "needs_attention": False,
                "attention_reason": None,
                "automation_allowed": False,
                "bitrix_write_allowed": False,
            },
            {
                "event_id": "evt-002",
                "final_case_type": "existing_deal",
                "final_case_subtype": "follow_up",
                "final_queue": "logistics",
                "final_action": "attach_to_deal",
                "final_decision_source": "deterministic",
                "final_confidence": 0.7,
                "needs_attention": False,
                "attention_reason": None,
                "automation_allowed": False,
                "bitrix_write_allowed": False,
            },
        ],
    }
    (run_dir / "rop_final_decisions.json").write_text(
        json.dumps(final_decisions), encoding="utf-8"
    )
    settings = _build_settings()
    settings["bitrix"] = {
        "widget": {
            "enabled": True,
            "token_env": "BITRIX_ROP_WIDGET_TOKEN",
            "default_period": "7d",
            "max_items": 1,
        }
    }
    monkeypatch.setenv("BITRIX_ROP_WIDGET_TOKEN", "widget-token")
    client = _client(storage_dir, settings=settings)
    response = client.get(
        "/api/bitrix/rop/widget",
        params={"run_id": "run-widget-fd"},
        headers={"Authorization": "Bearer widget-token"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert "final_decisions" in data
    fd = data["final_decisions"]
    assert fd["summary"]["total_events"] == 1
    assert fd["summary"]["decision_source_counts"] == {"deterministic": 1}
    assert fd["summary"]["attention_count"] == 0
    assert len(fd["events"]) == 1
    assert fd["events"][0]["event_id"] == "evt-001"
    assert fd["events"][0]["final_case_subtype"] is None
    assert fd["events"][0]["attention_reason"] is None
    assert fd["events"][0]["automation_allowed"] is False
    assert fd["events"][0]["bitrix_write_allowed"] is False


def test_rop_route_url_state_round_trip_and_selected_run(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-state")
    client = _client(storage_dir)

    response = client.get(
        "/rop?tab=queue&run_id=run-state&period=all&lang=ru&"
        "q=a%40example.com+%26+co&page=2&page_size=50&sort=sender&order=asc"
    )

    assert response.status_code == 200
    assert "run-state" in response.text
    assert "q=a%40example.com+%26+co" in response.text
    assert "page_size=50" in response.text
    assert "sort=sender" in response.text


def test_rop_html_and_api_share_validation_and_canonical_pagination(
    tmp_path: Path,
) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-contract")
    client = _client(storage_dir)

    assert (
        client.get("/rop?tab=queue&run_id=run-contract&queue=unknown").status_code
        >= 400
    )
    for path in (
        "/api/rop/dashboard?run_id=run-contract&queue=unknown",
        "/api/rop/dashboard?run_id=run-contract&page=-1",
        "/api/rop/dashboard?run_id=run-contract&sort=sender",
    ):
        assert client.get(path).status_code == 400

    payload = client.get(
        "/api/rop/dashboard?run_id=run-contract&page=999&page_size=50"
    ).json()["data"]
    assert payload["page"] == payload["pagination"]["page"]
    assert payload["page_size"] == payload["pagination"]["page_size"] == 50


def test_rop_event_detail_sections_and_back_link_round_trip(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-detail-state")
    (run_dir / "mail_thread_context.json").write_text(
        json.dumps({"contexts": [{"event_id": "evt-1", "thread_id": "thread-1"}]}),
        encoding="utf-8",
    )
    (run_dir / "bitrix_reconciliation.json").write_text(
        json.dumps({"items": [{"event_id": "evt-1", "status": "matched"}]}),
        encoding="utf-8",
    )
    (run_dir / "rop_action_drafts.json").write_text(
        json.dumps({"items": [{"event_id": "evt-1", "action_type": "review"}]}),
        encoding="utf-8",
    )
    client = _client(storage_dir)

    response = client.get(
        "/rop/events/evt-1?run_id=run-detail-state&period=all&lang=ru&"
        "priority=high&page=2&page_size=50&sort=sender&order=asc"
    )

    assert response.status_code == 200
    assert "Thread context" in response.text or "Контекст цепочки" in response.text
    assert (
        "Bitrix evidence" in response.text
        or "Доказательства из Битрикс" in response.text
    )
    assert "Action draft" in response.text or "Черновик действия" in response.text
    assert "run_id=run-detail-state" in response.text
    assert "page_size=50" in response.text


def test_rop_latest_selection_period_is_rendered(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_run_artifacts(storage_dir, "run-latest-period")
    (run_dir / "mailbox_selection.json").write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "mailbox",
                        "selected_count": 2,
                        "messages": [
                            {"internal_date": "2026-06-25T00:00:00+00:00"},
                            {"internal_date": "2026-06-28T00:00:00+00:00"},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    client = _client(storage_dir)

    response = client.get("/rop?run_id=run-latest-period")

    assert response.status_code == 200
    assert "25.06" in response.text and "28.06" in response.text


def test_queue_sort_links_round_trip_and_keep_atomic_pair(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-sort-links")
    (run_dir / "rop_current_state.json").write_text(
        json.dumps(
            {
                "queues": {
                    "high_priority": [
                        {
                            "event_id": "evt-1",
                            "sender": "client@example.com",
                            "subject": "Need welding quote",
                            "priority": "high",
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    client = _client(storage_dir)

    initial = client.get("/rop?tab=queue&run_id=run-sort-links")
    assert initial.status_code == 200
    assert "sort=sender&amp;order=desc" in initial.text

    ascending = client.get("/rop?tab=queue&run_id=run-sort-links&sort=sender&order=asc")
    assert ascending.status_code == 200
    assert "sort=sender&amp;order=desc" in ascending.text


def test_queue_pagination_links_keep_canonical_page_size() -> None:
    rows = [
        {
            "event_id": f"evt-{index}",
            "sender": f"sender-{index}",
            "subject": "Queue item",
            "priority": "high",
        }
        for index in range(51)
    ]
    layout = build_rop_page_layout(
        {
            "run_id": "run-page-size",
            "period": "all",
            "queues": {"high_priority": rows},
            "filter_params": {},
            "page": 1,
            "page_size": 50,
            "sort": "received_at",
            "order": "desc",
        },
        tab="queue",
    )
    pages = layout[0]["pagination"]["pages"]

    assert len(pages) == 2
    assert all("page_size=50" in page["href"] for page in pages)


def test_queue_filter_control_preserves_query_state_and_resets_page() -> None:
    layout = build_rop_page_layout(
        {
            "run_id": "run-filter-state",
            "period": "all",
            "queues": {
                "high_priority": [
                    {
                        "event_id": "evt-1",
                        "sender": "buyer@example.com",
                        "subject": "Priority quote",
                        "case_type": "new_lead",
                        "priority": "high",
                        "bitrix_status": "not_found",
                    }
                ]
            },
            "filter_params": {
                "q": "buyer & quote",
                "date_from": "2026-07-01",
                "date_to": "2026-07-31",
                "case_type": "new_lead",
                "priority": "high",
                "bitrix_status": "not_found",
                "columns": "priority,subject",
            },
            "filter_options": {
                "case_types": ["new_lead"],
                "priorities": ["high", "medium", "low"],
                "bitrix_statuses": ["not_found"],
            },
            "page": 2,
            "page_size": 50,
            "sort": "sender",
            "order": "asc",
        },
        tab="queue",
        locale="ru",
    )
    priority = next(
        field
        for field in layout[0]["toolbar"]["fields"]
        if field.get("name") == "priority"
    )
    query = parse_qs(urlparse(priority["choices"][0]["toggle_href"]).query)

    assert query.get("page", ["1"]) == ["1"]
    assert query["q"] == ["buyer & quote"]
    assert query["date_from"] == ["2026-07-01"]
    assert query["date_to"] == ["2026-07-31"]
    assert query["case_type"] == ["new_lead"]
    assert "priority" not in query
    assert query["bitrix_status"] == ["not_found"]
    assert query["columns"] == ["priority,subject"]
    assert query["page_size"] == ["50"]
    assert query["sort"] == ["sender"]
    assert query["order"] == ["asc"]
    assert query["run_id"] == ["run-filter-state"]
    assert query["period"] == ["all"]
    assert query["lang"] == ["ru"]


def test_queue_adopts_beeui_live_table_and_page_size_contract() -> None:
    from beeui_module.blocks.layout_renderer import render_layout

    rows = [
        {
            "event_id": f"evt-{index}",
            "sender": f"sender-{index}@example.com",
            "subject": "Queue a@example.com & co item",
            "case_type": "new_lead",
            "priority": "high",
            "bitrix_status": "not_found",
            "received_at": "2026-07-15T12:00:00Z",
        }
        for index in range(154)
    ]
    layout = build_rop_page_layout(
        {
            "run_id": "run-live-table",
            "period": "all",
            "queues": {"high_priority": rows},
            "filter_params": {
                "q": "a@example.com & co",
                "date_from": "2026-07-01",
                "date_to": "2026-07-31",
                "case_type": "new_lead",
                "priority": "high",
                "bitrix_status": "not_found",
                "columns": "priority,subject",
            },
            "page": 1,
            "page_size": 25,
            "sort": "sender",
            "order": "asc",
        },
        tab="queue",
        locale="ru",
    )

    table = layout[0]
    assert table["id"] == "rop-queue"
    assert table["pagination"]["page"] == 1
    assert table["pagination"]["total"] == 154
    assert table["pagination"]["start"] == 1
    assert table["pagination"]["end"] == 25
    assert table["pagination"]["label"] == "/ 154"
    assert len(table["pagination"]["pages"]) == 7

    page_size = table["pagination"]["page_size"]
    assert page_size["current"] == "25"
    assert [option["value"] for option in page_size["options"]] == [
        "25",
        "50",
        "100",
    ]
    for option in page_size["options"]:
        query = parse_qs(urlparse(option["href"]).query)
        assert query["page_size"] == [option["value"]]
        assert query.get("page", ["1"]) == ["1"]
        assert query["q"] == ["a@example.com & co"]
        assert query["date_from"] == ["2026-07-01"]
        assert query["date_to"] == ["2026-07-31"]
        assert query["case_type"] == ["new_lead"]
        assert query["priority"] == ["high"]
        assert query["bitrix_status"] == ["not_found"]
        assert query["columns"] == ["priority,subject"]
        assert query["run_id"] == ["run-live-table"]
        assert query["period"] == ["all"]
        assert query["lang"] == ["ru"]
        assert query["sort"] == ["sender"]
        assert query["order"] == ["asc"]

    rendered_table = render_layout(layout)[0]
    rendered_pages = rendered_table["pagination"]["pages"]
    assert [page["label"] for page in rendered_pages if not page.get("ellipsis")] == [
        "1",
        "2",
        "7",
    ]
    assert rendered_pages[0]["active"] is True
    assert any(page.get("ellipsis") for page in rendered_pages)
    assert [
        option["value"]
        for option in rendered_table["pagination"]["page_size"]["options"]
    ] == [
        "25",
        "50",
        "100",
    ]


def test_queue_uses_all_data_before_validated_date_range(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-queue-all")
    classified = json.loads(
        (run_dir / "classified_events.json").read_text(encoding="utf-8")
    )
    classified[0]["event_date"] = "2020-01-15T12:00:00Z"
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified), encoding="utf-8"
    )
    (run_dir / "rop_current_state.json").write_text(
        json.dumps(
            {
                "queues": {
                    "high_priority": [
                        {
                            "event_id": "evt-1",
                            "sender": "client@example.com",
                            "subject": "Need welding quote",
                            "priority": "high",
                            "event_date": "2020-01-15T12:00:00Z",
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    client = _client(storage_dir)

    response = client.get(
        "/rop?tab=queue&run_id=run-queue-all&period=today&"
        "date_from=2020-01-01&date_to=2020-01-31"
    )

    assert response.status_code == 200
    assert "Need welding quote" in response.text


def test_fallback_queue_rows_share_html_and_api_pagination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_run_artifacts(storage_dir, "run-fallback-queue")
    classified = json.loads(
        (run_dir / "classified_events.json").read_text(encoding="utf-8")
    )
    classified[0]["is_fallback"] = True
    classified[0]["event_date"] = "2020-01-15T12:00:00Z"
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified), encoding="utf-8"
    )
    _write_rop_web_projection(storage_dir)
    from beeagent_module.cases.rop_dashboard import rop_web_projection_entry_path

    entry_path = rop_web_projection_entry_path(storage_dir, "run-fallback-queue")
    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    for period in entry["dashboards"]:
        entry["dashboards"][period]["queues"] = {}
    entry_path.write_text(json.dumps(entry), encoding="utf-8")
    client = _client(storage_dir)

    html = client.get(
        "/rop?tab=queue&run_id=run-fallback-queue&is_fallback=true&"
        "page=999&page_size=50&sort=sender&order=asc"
    )
    api = client.get(
        "/api/rop/dashboard?tab=queue&run_id=run-fallback-queue&"
        "is_fallback=true&page=999&page_size=50&sort=sender&order=asc"
    )

    assert html.status_code == 200
    assert "test@example.com" in html.text
    assert api.status_code == 200
    payload = api.json()["data"]
    assert payload["pagination"]["total_items"] == 1
    assert payload["pagination"]["page"] == 1
    assert payload["pagination"]["page_size"] == 50
    assert payload["pagination"]["total_pages"] == 1
    assert payload["pagination"]["showing_from"] == 1
    assert payload["pagination"]["showing_to"] == 1
    assert payload["queue_rows"][0]["is_fallback"] is True
    assert payload["sort"] == "sender"
    assert payload["order"] == "asc"

    excluded = client.get(
        "/api/rop/dashboard?tab=queue&run_id=run-fallback-queue&is_fallback=false"
    ).json()["data"]
    assert excluded["pagination"]["total_items"] == 0


class TestRopDashboardAggregateReadModel:
    def _write_aggregate_run(
        self,
        storage_dir: Path,
        run_id: str,
        *,
        event_id: str,
        source_id: str,
        priority: str,
        sender: str,
    ) -> Path:
        run_dir = _write_run_artifacts(storage_dir, run_id)
        event_date = datetime.now(UTC).replace(microsecond=0).isoformat()
        normalized = [
            {
                "event_id": event_id,
                "source_id": source_id,
                "sender": sender,
                "subject": f"Subject {event_id}",
                "event_date": event_date,
                "attachments": [],
            }
        ]
        classified = [
            {
                "event_id": event_id,
                "source_id": source_id,
                "sender": sender,
                "subject": f"Subject {event_id}",
                "case_type": "new_lead",
                "priority": priority,
                "confidence": 0.9,
                "is_fallback": False,
                "reason_code": "new_contact",
                "event_date": event_date,
            }
        ]
        (run_dir / "normalized_events.json").write_text(
            json.dumps(normalized), encoding="utf-8"
        )
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )
        source_diag = {
            "aggregate": {
                "source_count": 1,
                "loaded_source_count": 1,
                "degraded_source_count": 0,
            },
            "sources": [
                {"source_id": source_id, "client_id": "welding", "status": "ok"},
            ],
        }
        (run_dir / "source_diagnostics.json").write_text(
            json.dumps(source_diag), encoding="utf-8"
        )
        return run_dir

    def test_business_kpi_and_queue_aggregate_across_runs(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        self._write_aggregate_run(
            storage_dir,
            "agg-run-a",
            event_id="evt-a",
            source_id="src_a",
            priority="high",
            sender="a@example.com",
        )
        self._write_aggregate_run(
            storage_dir,
            "agg-run-b",
            event_id="evt-b",
            source_id="src_b",
            priority="high",
            sender="b@example.com",
        )

        data = build_rop_dashboard_read_model(storage_dir, "agg-run-b", period="all")

        assert data["business_kpi"]["processed_events"] == 2
        row_by_event = {row["event_id"]: row for row in data["queue_rows"]}
        assert set(row_by_event) == {"evt-a", "evt-b"}
        assert row_by_event["evt-a"]["run_id"] == "agg-run-a"
        assert row_by_event["evt-b"]["run_id"] == "agg-run-b"

    def test_trusted_attach_projects_existing_deal_in_queue(
        self, tmp_path: Path
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        self._write_aggregate_run(
            storage_dir,
            "agg-run-q",
            event_id="evt-q",
            source_id="src_q",
            priority="high",
            sender="client@example.com",
        )
        (storage_dir / "interfaces").mkdir(parents=True, exist_ok=True)
        (storage_dir / "interfaces" / "rop_writeback_state.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "policy_snapshot": {},
                    "events": {
                        "welding|src_q|msg-q|": {
                            "event_id": "evt-q",
                            "event_instance_id": "",
                            "client_id": "welding",
                            "source_id": "src_q",
                            "message_id": "msg-q",
                            "case_type": "existing_deal",
                            "semantic_case_type": "new_lead",
                            "outcome": "attach_existing",
                            "status": "attached",
                            "target_entity_type": "lead",
                            "target_entity_id": 1001,
                            "target_provenance": "thread_resolved",
                            "last_run_id": "agg-run-q",
                        }
                    },
                    "runs": {},
                }
            ),
            encoding="utf-8",
        )

        data = build_rop_dashboard_read_model(storage_dir, "agg-run-q", period="all")
        row = next(item for item in data["queue_rows"] if item["event_id"] == "evt-q")
        assert row["case_type"] == "existing_deal"
        assert row["bot_case_type"] == "existing_deal"
        assert row["semantic_case_type"] == "new_lead"

    def test_independent_event_keeps_new_lead_in_queue(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        self._write_aggregate_run(
            storage_dir,
            "agg-run-q",
            event_id="evt-q",
            source_id="src_q",
            priority="high",
            sender="client@example.com",
        )

        data = build_rop_dashboard_read_model(storage_dir, "agg-run-q", period="all")
        row = next(item for item in data["queue_rows"] if item["event_id"] == "evt-q")
        assert row["case_type"] == "new_lead"
        assert row["bot_case_type"] == "new_lead"

    def test_filters_apply_over_aggregate_queue_rows(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        self._write_aggregate_run(
            storage_dir,
            "agg-run-a",
            event_id="evt-a",
            source_id="src_a",
            priority="high",
            sender="alpha@example.com",
        )
        self._write_aggregate_run(
            storage_dir,
            "agg-run-b",
            event_id="evt-b",
            source_id="src_b",
            priority="low",
            sender="beta@example.com",
        )

        data = build_rop_dashboard_read_model(
            storage_dir,
            "agg-run-b",
            period="all",
            filter_params={"priority": "high"},
        )

        assert [row["event_id"] for row in data["queue_rows"]] == ["evt-a"]

    def test_sort_and_pagination_over_aggregate_rows(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        for index in range(26):
            self._write_aggregate_run(
                storage_dir,
                f"agg-run-{index:02d}",
                event_id=f"evt-{index:02d}",
                source_id=f"src_{index:02d}",
                priority="high",
                sender=f"sender-{index:02d}@example.com",
            )

        data = build_rop_dashboard_read_model(
            storage_dir,
            "agg-run-00",
            period="all",
            page=1,
            page_size=25,
            sort="sender",
            order="asc",
        )

        assert len(data["queue_rows"]) == 25
        assert data["queue_rows"][0]["sender"] == "sender-00@example.com"
        assert data["pagination"]["total_items"] == 26
        assert data["pagination"]["total_pages"] == 2

        page_two = build_rop_dashboard_read_model(
            storage_dir,
            "agg-run-00",
            period="all",
            page=2,
            page_size=25,
            sort="sender",
            order="asc",
        )
        assert len(page_two["queue_rows"]) == 1
        assert page_two["queue_rows"][0]["sender"] == "sender-25@example.com"

    def test_latest_selection_remains_anchor_run_specific(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        self._write_aggregate_run(
            storage_dir,
            "agg-run-a",
            event_id="evt-a",
            source_id="src_a",
            priority="high",
            sender="a@example.com",
        )
        anchor = self._write_aggregate_run(
            storage_dir,
            "agg-run-b",
            event_id="evt-b",
            source_id="src_b",
            priority="high",
            sender="b@example.com",
        )
        (anchor / "mailbox_selection.json").write_text(
            json.dumps(
                {
                    "selected_count": 5,
                    "strategy": "single_explicit",
                    "source_count": 1,
                    "sources": [
                        {
                            "source_id": "src_b",
                            "selected_count": 5,
                            "messages": [{"internal_date": "2026-07-01T10:00:00Z"}],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        data = build_rop_dashboard_read_model(storage_dir, "agg-run-b", period="all")

        assert data["latest_selection"]["selected_count"] == 5
        assert data["latest_selection"]["strategy"] == "single_explicit"

    def test_threads_and_ai_remain_anchor_run_specific(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        self._write_aggregate_run(
            storage_dir,
            "agg-run-a",
            event_id="evt-a",
            source_id="src_a",
            priority="high",
            sender="a@example.com",
        )
        anchor = self._write_aggregate_run(
            storage_dir,
            "agg-run-b",
            event_id="evt-b",
            source_id="src_b",
            priority="high",
            sender="b@example.com",
        )
        (anchor / "mail_thread_index.json").write_text(
            json.dumps({"threads": [{"thread_id": "thr-1"}]}),
            encoding="utf-8",
        )
        (anchor / "mail_thread_context.json").write_text(
            json.dumps({"contexts": []}),
            encoding="utf-8",
        )

        data = build_rop_dashboard_read_model(storage_dir, "agg-run-b", period="all")

        assert data["thread_summary"]["thread_count"] == 1
        assert data["evidence_links"]

    def test_queue_rows_use_origin_run_id_in_detail_links(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        self._write_aggregate_run(
            storage_dir,
            "agg-run-a",
            event_id="evt-a",
            source_id="src_a",
            priority="high",
            sender="a@example.com",
        )
        self._write_aggregate_run(
            storage_dir,
            "agg-run-b",
            event_id="evt-b",
            source_id="src_b",
            priority="high",
            sender="b@example.com",
        )

        data = build_rop_dashboard_read_model(storage_dir, "agg-run-b", period="all")
        from beeagent_module.interfaces.ui.read_model import _queue_table

        table = _queue_table(
            "Queue",
            data["queue_rows"],
            run_id="agg-run-b",
            locale="en",
            current_period="all",
        )
        hrefs = [
            row.get("detail_href") for row in table["rows"] if row.get("detail_href")
        ]
        assert any("run_id=agg-run-a" in href for href in hrefs)
        assert any("run_id=agg-run-b" in href for href in hrefs)

    def test_priority_preview_uses_origin_run_id(self) -> None:
        from beeagent_module.interfaces.ui.read_model import (
            _collect_priority_queue_preview,
        )

        queues = {
            "high_priority": [
                {
                    "event_id": "evt-a",
                    "run_id": "agg-run-a",
                    "source_id": "src_a",
                    "sender": "a@example.com",
                    "subject": "A",
                    "priority": "high",
                },
                {
                    "event_id": "evt-b",
                    "run_id": "agg-run-b",
                    "source_id": "src_b",
                    "sender": "b@example.com",
                    "subject": "B",
                    "priority": "high",
                },
            ]
        }
        rows = _collect_priority_queue_preview(
            queues, "7d", run_id="agg-run-b", locale="en", limit=5
        )
        hrefs = [row["evidence"]["href"] for row in rows]
        assert any("run_id=agg-run-a" in href for href in hrefs)
        assert any("run_id=agg-run-b" in href for href in hrefs)

    def test_same_event_id_different_source_not_collapsed(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        self._write_aggregate_run(
            storage_dir,
            "agg-run-a",
            event_id="evt-same",
            source_id="src_a",
            priority="high",
            sender="a@example.com",
        )
        self._write_aggregate_run(
            storage_dir,
            "agg-run-b",
            event_id="evt-same",
            source_id="src_b",
            priority="high",
            sender="b@example.com",
        )

        data = build_rop_dashboard_read_model(storage_dir, "agg-run-b", period="all")

        assert data["business_kpi"]["processed_events"] == 2
        same_rows = [row for row in data["queue_rows"] if row["event_id"] == "evt-same"]
        assert len(same_rows) == 2
        assert {row["run_id"] for row in same_rows} == {"agg-run-a", "agg-run-b"}
        assert {row["source_id"] for row in same_rows} == {"src_a", "src_b"}
        from beeagent_module.interfaces.ui.read_model import build_rop_page_layout

        layout = build_rop_page_layout(data, tab="overview")
        action = next(
            block for block in layout if block.get("title") == "Action Required"
        )
        assert "2 items need review" in action["subtitle"]

    def test_bitrix_aggregate_visible_when_anchor_lacks_artifact(
        self, tmp_path: Path
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        run_a = self._write_aggregate_run(
            storage_dir,
            "agg-run-a",
            event_id="evt-bx-a",
            source_id="src_a",
            priority="low",
            sender="a@example.com",
        )
        (run_a / "bitrix_reconciliation.json").write_text(
            json.dumps(
                {
                    "run_id": "agg-run-a",
                    "status": "ok",
                    "items": [
                        {
                            "event_id": "evt-bx-a",
                            "bitrix_match_status": "matched_lead",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        self._write_aggregate_run(
            storage_dir,
            "agg-run-b",
            event_id="evt-bx-b",
            source_id="src_b",
            priority="low",
            sender="b@example.com",
        )

        data = build_rop_dashboard_read_model(storage_dir, "agg-run-b", period="all")
        from beeagent_module.interfaces.ui.read_model import build_rop_page_layout

        assert data["business_kpi"]["matched_in_bitrix"] == 1

        layout = build_rop_page_layout(data, tab="bitrix")

        kpi = next(block for block in layout if block.get("type") == "kpi_grid")
        kpi_values = {item["label"]: item["value"] for item in kpi["items"]}
        assert kpi_values.get("Matched") == 1
        matched_table = next(
            block
            for block in layout
            if block.get("type") == "status_table" and block.get("title") == "Matched"
        )
        assert any(row[0] == "evt-bx-a" for row in matched_table["rows"])
        notices = [
            block
            for block in layout
            if block.get("type") == "state_grid"
            and any(
                item.get("label") == "Not reconciled" for item in block.get("items", [])
            )
        ]
        assert notices
        assert any(
            "not available for this run" in str(item.get("value", ""))
            for block in notices
            for item in block["items"]
        )
        assert data["evidence_links"]
        assert all(
            "/runs/agg-run-b/" in link["url"]
            for link in data["evidence_links"]
            if isinstance(link, dict)
        )
        bitrix_link = next(
            link
            for link in data["evidence_links"]
            if isinstance(link, dict)
            and link.get("artifact_id") == "bitrix_reconciliation_json"
        )
        assert bitrix_link.get("available") is False

    def test_latest_rop_anchor_not_displaced_by_newer_non_rop_run(
        self, tmp_path: Path
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        self._write_aggregate_run(
            storage_dir,
            "rop-old",
            event_id="evt-rop",
            source_id="src_rop",
            priority="high",
            sender="rop@example.com",
        )
        generic = storage_dir / "runs" / "generic-new"
        generic.mkdir(parents=True, exist_ok=True)
        (generic / "operator_summary.json").write_text(
            json.dumps({"status": "ok", "summary": "generic case"}),
            encoding="utf-8",
        )

        data = build_rop_dashboard_read_model(storage_dir, None, period="all")

        assert data["selected_run_id"] == "rop-old"
        assert data["business_kpi"]["processed_events"] == 1

        client = _client(storage_dir)
        api = client.get("/api/rop/dashboard", params={"period": "all"})
        assert api.status_code == 200
        payload = api.json()["data"]
        assert payload["selected_run_id"] == "rop-old"
        assert payload["business_kpi"]["processed_events"] == 1


def test_event_detail_routes_return_client_error_statuses(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-event-errors")
    client = _client(storage_dir)

    invalid_query = client.get("/rop/events/evt-1?run_id=run-event-errors&sort=sender")
    invalid_run = client.get("/rop/events/evt-1?run_id=../outside")
    missing = client.get("/rop/events/missing?run_id=run-event-errors")
    valid = client.get("/rop/events/evt-1?run_id=run-event-errors")
    api_valid = client.get("/api/rop/events/evt-1?run_id=run-event-errors")
    api_invalid_run = client.get("/api/rop/events/evt-1?run_id=../outside")
    api_invalid_sort = client.get(
        "/api/rop/events/evt-1?run_id=run-event-errors&sort=sender"
    )
    api_missing = client.get("/api/rop/events/missing?run_id=run-event-errors")

    assert invalid_query.status_code == 400
    assert invalid_run.status_code == 400
    assert missing.status_code == 404
    assert valid.status_code == 200
    assert api_valid.status_code == 200
    assert api_invalid_run.status_code == 400
    assert api_invalid_sort.status_code == 400
    assert api_missing.status_code == 404
    assert "Traceback" not in invalid_query.text
    assert str(storage_dir) not in invalid_query.text
    assert "RAW-EML-CONTENT" not in invalid_query.text


def test_empty_queue_keeps_canonical_url_state_and_selected_columns(
    tmp_path: Path,
) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-empty-queue-state")
    client = _client(storage_dir)

    response = client.get(
        "/rop?tab=queue&run_id=run-empty-queue-state&period=all&lang=ru&"
        "queue=ambiguous&q=needle&date_from=2020-01-01&date_to=2020-01-31&"
        "case_type=new_lead&priority=high&bitrix_status=not_found&"
        "columns=subject,date&columns_open=1&open_dropdowns=priority&"
        "page=999&page_size=50&sort=sender&order=asc"
    )

    assert response.status_code == 200
    table_html = response.text.split("<table", 1)[1].split("</table>", 1)[0]
    assert "Тема" in table_html
    assert "Дата" in table_html
    assert "Приоритет" not in table_html
    assert "Отправитель" not in table_html
    assert "Классификация" not in table_html
    assert "Статус Битрикса" not in table_html
    assert "run_id=run-empty-queue-state" in response.text
    assert "queue=ambiguous" in response.text
    assert "q=needle" in response.text
    assert "date_from=2020-01-01" in response.text
    assert "date_to=2020-01-31" in response.text
    assert "case_type=new_lead" in response.text
    assert (
        "columns=subject%2Cdate" in response.text
        or "columns=date%2Csubject" in response.text
    )
    assert "page_size=50" in response.text
    assert "sort=sender&amp;order=asc" in response.text


def test_recommendation_links_are_built_with_current_rop_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-recommendation-links")
    from beeagent_module.interfaces.ui import read_model as read_model_module

    monkeypatch.setattr(
        read_model_module,
        "build_rop_dashboard",
        lambda **kwargs: {
            "period": kwargs["period"],
            "queues": {},
            "business_kpi": {},
            "series": {},
            "rop_recommendations": [
                {"reason_code": "high_priority", "evidence_href": "/rop?tab=queue"}
            ],
            "warnings": [],
        },
    )
    client = _client(storage_dir)

    response = client.get(
        "/api/rop/dashboard?run_id=run-recommendation-links&period=all&lang=ru"
    )

    assert response.status_code == 200
    href = response.json()["data"]["rop_recommendations"][0]["evidence_href"]
    assert href.startswith("/rop?tab=queue")
    assert "run_id=run-recommendation-links" in href
    assert "period=all" in href
    assert "lang=ru" in href


def test_rop_event_detail_page_model_localized_bool_en(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-bool-en")
    page = build_rop_event_detail_page_model(
        storage_dir, "run-bool-en", "evt-1", lang="en"
    )
    cls_items = _find_section_items(page, "Classification")
    should_rop = _item_by_label(cls_items, "Should ROP see")
    assert should_rop["value"] == "Yes"
    assert should_rop["variant"] == "badge"
    assert should_rop["tone"] == "warning"


def test_rop_event_detail_page_model_localized_bool_ru(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.locale import t
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-bool-ru")
    page = build_rop_event_detail_page_model(
        storage_dir, "run-bool-ru", "evt-1", lang="ru"
    )
    cls_items = _find_section_items(page, t("Classification", "ru"))
    should_rop = _item_by_label(cls_items, "Должен увидеть РОП")
    assert should_rop["value"] == "Да"
    assert should_rop["variant"] == "badge"
    assert should_rop["tone"] == "warning"


def test_rop_event_detail_page_model_bool_none(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.locale import t
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-bool-none")
    classified = json.loads(
        (run_dir / "classified_events.json").read_text(encoding="utf-8")
    )
    classified[0]["should_rop_see"] = None
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified), encoding="utf-8"
    )
    page = build_rop_event_detail_page_model(
        storage_dir, "run-bool-none", "evt-1", lang="en"
    )
    cls_items = _find_section_items(page, "Classification")
    should_rop = _item_by_label(cls_items, "Should ROP see")
    assert should_rop["value"] == "n/a"
    assert should_rop["tone"] == "muted"

    page_ru = build_rop_event_detail_page_model(
        storage_dir, "run-bool-none", "evt-1", lang="ru"
    )
    cls_items_ru = _find_section_items(page_ru, t("Classification", "ru"))
    should_rop_ru = _item_by_label(cls_items_ru, "Должен увидеть РОП")
    assert should_rop_ru["value"] == "н/д"


def test_rop_event_detail_page_model_bool_malformed_string(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.locale import t
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-bool-str")
    classified = json.loads(
        (run_dir / "classified_events.json").read_text(encoding="utf-8")
    )
    classified[0]["should_rop_see"] = "false"
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified), encoding="utf-8"
    )
    page = build_rop_event_detail_page_model(
        storage_dir, "run-bool-str", "evt-1", lang="en"
    )
    cls_items = _find_section_items(page, "Classification")
    should_rop = _item_by_label(cls_items, "Should ROP see")
    assert should_rop["value"] == "n/a"
    assert should_rop["tone"] == "muted"

    page_ru = build_rop_event_detail_page_model(
        storage_dir, "run-bool-str", "evt-1", lang="ru"
    )
    cls_items_ru = _find_section_items(page_ru, t("Classification", "ru"))
    should_rop_ru = _item_by_label(cls_items_ru, "Должен увидеть РОП")
    assert should_rop_ru["value"] == "н/д"


def test_rop_event_detail_page_model_bool_missing_field(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.locale import t
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-bool-miss")
    classified = json.loads(
        (run_dir / "classified_events.json").read_text(encoding="utf-8")
    )
    del classified[0]["should_rop_see"]
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified), encoding="utf-8"
    )
    page = build_rop_event_detail_page_model(
        storage_dir, "run-bool-miss", "evt-1", lang="en"
    )
    cls_items = _find_section_items(page, "Classification")
    should_rop = _item_by_label(cls_items, "Should ROP see")
    assert should_rop["value"] == "n/a"
    assert should_rop["tone"] == "muted"

    page_ru = build_rop_event_detail_page_model(
        storage_dir, "run-bool-miss", "evt-1", lang="ru"
    )
    cls_items_ru = _find_section_items(page_ru, t("Classification", "ru"))
    should_rop_ru = _item_by_label(cls_items_ru, "Должен увидеть РОП")
    assert should_rop_ru["value"] == "н/д"


def test_rop_event_detail_page_model_thread_bool_none(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.locale import t
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-thread-null")
    (run_dir / "mail_thread_context.json").write_text(
        json.dumps(
            {
                "contexts": [
                    {
                        "event_id": "evt-1",
                        "thread_id": "t-1",
                        "reply_or_forward": None,
                        "thread_connection": "reply",
                        "reason_codes": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    page_en = build_rop_event_detail_page_model(
        storage_dir, "run-thread-null", "evt-1", lang="en"
    )
    thr_items = _find_section_items(page_en, "Thread context")
    rf = _item_by_label(thr_items, "Reply/forward")
    assert rf["value"] == "n/a"
    assert rf["variant"] == "boolean"

    page_ru = build_rop_event_detail_page_model(
        storage_dir, "run-thread-null", "evt-1", lang="ru"
    )
    thr_items_ru = _find_section_items(page_ru, t("Thread context", "ru"))
    rf_ru = _item_by_label(thr_items_ru, "Ответ/пересылка")
    assert rf_ru["value"] == "н/д"


def test_rop_event_detail_page_model_thread_bool_missing(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-thread-miss")
    (run_dir / "mail_thread_context.json").write_text(
        json.dumps(
            {
                "contexts": [
                    {
                        "event_id": "evt-1",
                        "thread_id": "t-1",
                        "thread_connection": "reply",
                        "reason_codes": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    page_en = build_rop_event_detail_page_model(
        storage_dir, "run-thread-miss", "evt-1", lang="en"
    )
    thr_items = _find_section_items(page_en, "Thread context")
    rf = _item_by_label(thr_items, "Reply/forward")
    assert rf["value"] == "n/a"
    assert rf["variant"] == "boolean"


def test_rop_event_detail_page_model_ai_assist_used_none(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-ai-used-none")
    (run_dir / "rop_ai_assist_results.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "event_id": "evt-1",
                        "ai_assist_status": "ok",
                        "ai_assist_used": None,
                        "ai_assist_confidence": 0.5,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    page = build_rop_event_detail_page_model(
        storage_dir, "run-ai-used-none", "evt-1", lang="en"
    )
    ai_items = _find_section_items(page, "AI Assist")
    used_item = _item_by_label(ai_items, "AI used")
    assert used_item["value"] == "n/a"
    assert used_item["variant"] == "boolean"


def test_rop_event_detail_page_model_ai_assist_used_missing(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-ai-used-miss")
    (run_dir / "rop_ai_assist_results.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "event_id": "evt-1",
                        "ai_assist_status": "ok",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    page = build_rop_event_detail_page_model(
        storage_dir, "run-ai-used-miss", "evt-1", lang="en"
    )
    ai_items = _find_section_items(page, "AI Assist")
    used_item = _item_by_label(ai_items, "AI used")
    assert used_item["value"] == "n/a"
    assert used_item["variant"] == "boolean"


def test_rop_event_detail_page_model_ai_assist_used_malformed(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-ai-used-bad")
    (run_dir / "rop_ai_assist_results.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "event_id": "evt-1",
                        "ai_assist_status": "ok",
                        "ai_assist_used": "false",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    page = build_rop_event_detail_page_model(
        storage_dir, "run-ai-used-bad", "evt-1", lang="en"
    )
    ai_items = _find_section_items(page, "AI Assist")
    used_item = _item_by_label(ai_items, "AI used")
    assert used_item["value"] == "n/a"
    assert used_item["variant"] == "boolean"


def test_rop_event_detail_page_model_adjudicator_used_none(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-adj-none")
    (run_dir / "rop_ai_adjudicator_results.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "event_id": "evt-1",
                        "ai_used": None,
                        "ai_status": "ok",
                        "final_case_type": "new_lead",
                        "final_recommended_queue": "",
                        "final_correct_action": "",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    page = build_rop_event_detail_page_model(
        storage_dir, "run-adj-none", "evt-1", lang="en"
    )
    adj_items = _find_section_items(page, "AI Adjudicator")
    used_item = _item_by_label(adj_items, "AI adjudicator used")
    assert used_item["value"] == "n/a"
    assert used_item["variant"] == "badge"
    assert used_item["tone"] == "muted"


def test_rop_event_detail_page_model_bool_false_exact(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.locale import t
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-bool-false")
    classified = json.loads(
        (run_dir / "classified_events.json").read_text(encoding="utf-8")
    )
    classified[0]["should_rop_see"] = False
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified), encoding="utf-8"
    )
    page = build_rop_event_detail_page_model(
        storage_dir, "run-bool-false", "evt-1", lang="en"
    )
    cls_items = _find_section_items(page, "Classification")
    should_rop = _item_by_label(cls_items, "Should ROP see")
    assert should_rop["value"] == "No"
    assert should_rop["tone"] == "muted"

    page_ru = build_rop_event_detail_page_model(
        storage_dir, "run-bool-false", "evt-1", lang="ru"
    )
    cls_items_ru = _find_section_items(page_ru, t("Classification", "ru"))
    should_rop_ru = _item_by_label(cls_items_ru, "Должен увидеть РОП")
    assert should_rop_ru["value"] == "Нет"


def test_rop_event_detail_page_model_priority_tone(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    for priority, expected_tone in [
        ("low", "muted"),
        ("medium", "warning"),
        ("high", "danger"),
        ("critical", "danger"),
        ("unknown_val", "muted"),
    ]:
        run_id = f"run-prio-{priority}"
        run_dir = _write_rop_event_detail_artifacts(storage_dir, run_id)
        classified = json.loads(
            (run_dir / "classified_events.json").read_text(encoding="utf-8")
        )
        classified[0]["priority"] = priority
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )
        page = build_rop_event_detail_page_model(
            storage_dir, run_id, "evt-1", lang="en"
        )
        cls_items = _find_section_items(page, "Classification")
        prio_item = _item_by_label(cls_items, "Priority")
        assert prio_item["tone"] == expected_tone, (
            f"priority={priority!r} expected tone={expected_tone!r} "
            f"got={prio_item['tone']!r}"
        )
        assert prio_item["variant"] == "badge"


def test_rop_event_detail_page_model_adjudicator_status_tone(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    test_cases = [
        ("ok", "success"),
        ("low_confidence_preserve", "warning"),
        ("manual_review_degrade", "warning"),
        ("invalid_output", "danger"),
        ("provider_unavailable", "danger"),
        ("module_contract_unavailable", "danger"),
        ("unknown_status", "default"),
        ("", "default"),
    ]
    for status, expected_tone in test_cases:
        run_id = f"run-adj-status-{status.replace('_', '-')}"
        run_dir = _write_rop_event_detail_artifacts(storage_dir, run_id)
        (run_dir / "rop_ai_adjudicator_results.json").write_text(
            json.dumps(
                {
                    "results": [
                        {
                            "event_id": "evt-1",
                            "ai_used": True,
                            "ai_status": status,
                            "ai_confidence": 0.5,
                            "ai_reason": "test",
                            "final_case_type": "new_lead",
                            "final_recommended_queue": "manual_review",
                            "final_correct_action": "manual_review",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        page = build_rop_event_detail_page_model(
            storage_dir, run_id, "evt-1", lang="en"
        )
        adj_items = _find_section_items(page, "AI Adjudicator")
        status_item = _item_by_label(adj_items, "AI adjudicator status")
        assert status_item["tone"] == expected_tone, (
            f"status={status!r} expected tone={expected_tone!r} "
            f"got={status_item['tone']!r}"
        )
        assert status_item["variant"] == "badge"


def test_rop_event_detail_page_model_queue_action_tone(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    test_cases = [
        ("manual_review", "warning"),
        ("ignore", "muted"),
        ("high_priority", "default"),
        ("sales", "default"),
        ("", "default"),
    ]
    for action, expected_tone in test_cases:
        run_id = f"run-qa-{action.replace('_', '-')}"
        run_dir = _write_rop_event_detail_artifacts(storage_dir, run_id)
        classified = json.loads(
            (run_dir / "classified_events.json").read_text(encoding="utf-8")
        )
        classified[0]["correct_action"] = action
        classified[0]["recommended_queue"] = action
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )
        page = build_rop_event_detail_page_model(
            storage_dir, run_id, "evt-1", lang="en"
        )
        cls_items = _find_section_items(page, "Classification")
        rec_act = _item_by_label(cls_items, "Recommended action")
        rec_queue = _item_by_label(cls_items, "Recommended queue")
        assert rec_act["tone"] == expected_tone, (
            f"correct_action={action!r} expected tone={expected_tone!r} "
            f"got={rec_act['tone']!r}"
        )
        assert rec_act["variant"] == "badge"
        assert rec_queue["tone"] == expected_tone
        assert rec_queue["variant"] == "badge"


def test_rop_event_detail_page_model_recommended_action_label(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.locale import t
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-rec-act-label")
    page_en = build_rop_event_detail_page_model(
        storage_dir, "run-rec-act-label", "evt-1", lang="en"
    )
    cls_items_en = _find_section_items(page_en, "Classification")
    labels_en = [i["label"] for i in cls_items_en]
    assert "Recommended action" in labels_en
    assert "Correct action" not in labels_en

    page_ru = build_rop_event_detail_page_model(
        storage_dir, "run-rec-act-label", "evt-1", lang="ru"
    )
    cls_items_ru = _find_section_items(page_ru, t("Classification", "ru"))
    labels_ru = [i["label"] for i in cls_items_ru]
    assert "Рекомендуемое действие" in labels_ru
    assert "Верное действие" not in labels_ru


def test_rop_event_detail_page_model_final_decision_badge_tones(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-fd-tones")
    (run_dir / "rop_ai_adjudicator_results.json").write_text(
        json.dumps({"results": []}), encoding="utf-8"
    )
    (run_dir / "rop_final_decisions.json").write_text(
        json.dumps(
            {
                "summary": {
                    "total_events": 1,
                    "decision_source_counts": {"ai_adjudicator": 1},
                    "attention_count": 1,
                },
                "events": [
                    {
                        "event_id": "evt-1",
                        "final_case_type": "new_lead",
                        "final_case_subtype": None,
                        "final_queue": "manual_review",
                        "final_action": "manual_review",
                        "final_decision_source": "ai_adjudicator",
                        "final_confidence": 0.85,
                        "needs_attention": True,
                        "attention_reason": "conflict",
                        "automation_allowed": False,
                        "bitrix_write_allowed": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    page = build_rop_event_detail_page_model(
        storage_dir, "run-fd-tones", "evt-1", lang="en"
    )
    fd_items = _find_section_items(page, "Final decision")
    needs_attn = _item_by_label(fd_items, "Needs attention")
    assert needs_attn["value"] == "Yes"
    assert needs_attn["tone"] == "warning"
    assert needs_attn["variant"] == "badge"

    auto_allowed = _item_by_label(fd_items, "Automation allowed")
    assert auto_allowed["value"] == "No"
    assert auto_allowed["tone"] == "muted"
    assert auto_allowed["variant"] == "badge"

    bitrix_allowed = _item_by_label(fd_items, "Bitrix write allowed")
    assert bitrix_allowed["value"] == "No"
    assert bitrix_allowed["tone"] == "muted"
    assert bitrix_allowed["variant"] == "badge"

    fd_type = _item_by_label(fd_items, "Final case type")
    assert fd_type["variant"] == "badge"
    assert fd_type["tone"] == "default"

    fd_queue = _item_by_label(fd_items, "Final queue")
    assert fd_queue["variant"] == "badge"
    assert fd_queue["tone"] == "warning"

    decision_source = _item_by_label(fd_items, "Decision source")
    assert decision_source["variant"] == "badge"
    assert decision_source["tone"] == "muted"


def test_rop_event_detail_page_model_adjudicator_used_tone(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    for used, expected_tone in [(True, "default"), (False, "muted")]:
        run_id = f"run-adj-used-{used}"
        run_dir = _write_rop_event_detail_artifacts(storage_dir, run_id)
        (run_dir / "rop_ai_adjudicator_results.json").write_text(
            json.dumps(
                {
                    "results": [
                        {
                            "event_id": "evt-1",
                            "ai_used": used,
                            "ai_status": "ok",
                            "ai_confidence": 0.5,
                            "ai_reason": "test",
                            "final_case_type": "new_lead",
                            "final_recommended_queue": "manual_review",
                            "final_correct_action": "manual_review",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        page = build_rop_event_detail_page_model(
            storage_dir, run_id, "evt-1", lang="en"
        )
        adj_items = _find_section_items(page, "AI Adjudicator")
        used_item = _item_by_label(adj_items, "AI adjudicator used")
        assert used_item["tone"] == expected_tone
        assert used_item["variant"] == "badge"
        assert used_item["value"] == ("Yes" if used else "No")


def test_rop_event_detail_page_model_thread_bool_localized(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.locale import t
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-thread-bool")
    (run_dir / "mail_thread_context.json").write_text(
        json.dumps(
            {
                "contexts": [
                    {
                        "event_id": "evt-1",
                        "thread_id": "t-1",
                        "reply_or_forward": True,
                        "thread_connection": "reply",
                        "reason_codes": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    page_en = build_rop_event_detail_page_model(
        storage_dir, "run-thread-bool", "evt-1", lang="en"
    )
    thr_items = _find_section_items(page_en, "Thread context")
    rf = _item_by_label(thr_items, "Reply/forward")
    assert rf["value"] == "Yes"
    assert rf["variant"] == "boolean"

    page_ru = build_rop_event_detail_page_model(
        storage_dir, "run-thread-bool", "evt-1", lang="ru"
    )
    thr_items_ru = _find_section_items(page_ru, t("Thread context", "ru"))
    rf_ru = _item_by_label(thr_items_ru, "Ответ/пересылка")
    assert rf_ru["value"] == "Да"


def test_rop_event_detail_page_model_case_type_default_badge(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-ct-badge")
    page = build_rop_event_detail_page_model(
        storage_dir, "run-ct-badge", "evt-1", lang="en"
    )
    cls_items = _find_section_items(page, "Classification")
    ct = _item_by_label(cls_items, "Case type")
    assert ct["variant"] == "badge"
    assert ct["tone"] == "default"


def test_rop_event_detail_api_booleans_remain_raw(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-api-bool")
    client = _client(storage_dir)

    response = client.get("/api/rop/events/evt-1?run_id=run-api-bool")

    assert response.status_code == 200
    data = response.json()["data"]
    cls = data["classification"]
    assert cls["should_rop_see"] is True
    assert cls["correct_action"] == "review"
    assert "recommended_queue" in cls
    assert "Recommended action" not in json.dumps(data)


def test_rop_event_detail_page_model_unknown_values_degrades_safely(
    tmp_path: Path,
) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-unknown-safe")
    classified = json.loads(
        (run_dir / "classified_events.json").read_text(encoding="utf-8")
    )
    classified[0]["priority"] = "bogus_value"
    classified[0]["correct_action"] = "bogus_action"
    classified[0]["recommended_queue"] = "bogus_queue"
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified), encoding="utf-8"
    )
    page = build_rop_event_detail_page_model(
        storage_dir, "run-unknown-safe", "evt-1", lang="en"
    )
    cls_items = _find_section_items(page, "Classification")
    prio = _item_by_label(cls_items, "Priority")
    assert prio["tone"] == "muted"
    assert prio["variant"] == "badge"
    rec_queue = _item_by_label(cls_items, "Recommended queue")
    assert rec_queue["tone"] == "default"
    assert rec_queue["variant"] == "badge"
    rec_act = _item_by_label(cls_items, "Recommended action")
    assert rec_act["tone"] == "default"
    assert rec_act["variant"] == "badge"


def test_event_detail_uses_canonical_date_and_bitrix_status_fields(
    tmp_path: Path,
) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-canonical-detail")
    normalized = json.loads(
        (run_dir / "normalized_events.json").read_text(encoding="utf-8")
    )
    normalized[0]["received_at"] = "2026-01-15T14:30:00Z"
    (run_dir / "normalized_events.json").write_text(
        json.dumps(normalized), encoding="utf-8"
    )
    (run_dir / "bitrix_reconciliation.json").write_text(
        json.dumps(
            {"items": [{"event_id": "evt-1", "bitrix_match_status": "matched_lead"}]}
        ),
        encoding="utf-8",
    )
    client = _client(storage_dir)

    response = client.get("/rop/events/evt-1?run_id=run-canonical-detail")

    assert response.status_code == 200
    assert "15.01.2026, 14:30" in response.text
    assert "matched_lead" in response.text


def test_queue_html_uses_generic_datepicker_contract(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-datepicker")
    client = _client(storage_dir)

    for lang in ("en", "ru"):
        response = client.get(
            "/rop?tab=queue&run_id=run-datepicker&lang="
            f"{lang}&date_from=2026-07-01&date_to=2026-07-31"
        )

        assert response.status_code == 200
        assert 'name="date_from"' in response.text
        assert 'name="date_to"' in response.text
        assert 'value="2026-07-01"' in response.text
        assert 'value="2026-07-31"' in response.text
        assert "beeui-dr-input" in response.text
        assert "cdn.jsdelivr.net" not in response.text
        assert "cdnjs.cloudflare.com" not in response.text
        assert "unpkg.com" not in response.text
        assert "googleapis.com" not in response.text


def test_queue_direct_short_searches_and_live_table_markup(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-short-search")
    (run_dir / "rop_current_state.json").write_text(
        json.dumps(
            {
                "queues": {
                    "high_priority": [
                        {
                            "event_id": "evt-alpha",
                            "sender": "alpha@example.com",
                            "subject": "Alpha & Co quote",
                            "priority": "high",
                        },
                        {
                            "event_id": "evt-beta",
                            "sender": "beta@example.com",
                            "subject": "Beta quote",
                            "priority": "medium",
                        },
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "classified_events.json").write_text(
        json.dumps(
            [
                {
                    "event_id": "evt-alpha",
                    "sender": "alpha@example.com",
                    "subject": "Alpha & Co quote",
                    "case_type": "new_lead",
                    "priority": "high",
                    "received_at": "2026-07-15T12:00:00Z",
                },
                {
                    "event_id": "evt-beta",
                    "sender": "beta@example.com",
                    "subject": "Beta quote",
                    "case_type": "existing_deal",
                    "priority": "medium",
                    "received_at": "2026-07-15T12:00:00Z",
                },
            ]
        ),
        encoding="utf-8",
    )
    client = _client(storage_dir)

    for query in ("a", "ab"):
        response = client.get(
            "/rop",
            params={"tab": "queue", "run_id": "run-short-search", "q": query},
        )
        assert response.status_code == 200

    filtered = client.get(
        "/rop",
        params={
            "tab": "queue",
            "run_id": "run-short-search",
            "q": "Alpha & Co",
        },
    )
    assert filtered.status_code == 200
    assert 'value="Alpha &amp; Co"' in filtered.text
    assert "Alpha &amp; Co quote" in filtered.text
    assert "Beta quote" not in filtered.text
    assert 'data-beeui-table-id="rop-queue"' in filtered.text
    assert "beeui-live-table" in filtered.text
    assert "data-beeui-table-search" in filtered.text
    assert "data-beeui-page-size-select" in filtered.text
    assert "Ctrl+K" not in filtered.text


def test_queue_html_and_api_accept_duplicate_case_type_filter(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-duplicate-filter")
    (run_dir / "classified_events.json").write_text(
        json.dumps(
            [
                {
                    "event_id": "evt-duplicate",
                    "sender": "buyer@example.com",
                    "subject": "Duplicate RFQ",
                    "case_type": "duplicate",
                    "priority": "medium",
                    "received_at": "2026-07-15T12:00:00Z",
                },
                {
                    "event_id": "evt-new-lead",
                    "sender": "other@example.com",
                    "subject": "New RFQ",
                    "case_type": "new_lead",
                    "priority": "high",
                    "received_at": "2026-07-15T13:00:00Z",
                },
            ]
        ),
        encoding="utf-8",
    )
    client = _client(storage_dir)
    query = "tab=queue&run_id=run-duplicate-filter&case_type=duplicate"

    html = client.get("/rop?" + query)
    api = client.get("/api/rop/dashboard?" + query)

    assert html.status_code == 200
    assert api.status_code == 200
    assert "Duplicate RFQ" in html.text
    assert "New RFQ" not in html.text
    assert [row["event_id"] for row in api.json()["data"]["queue_rows"]] == [
        "evt-duplicate"
    ]


def test_queue_and_event_detail_select_same_event_id_by_instance(
    tmp_path: Path,
) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-event-instances")
    event_id = "evt-shared"
    normalized = [
        {
            "event_id": event_id,
            "event_instance_id": instance_id,
            "source_id": "hotline_mailbox",
            "client_id": "welding",
            "sender": "buyer@example.com",
            "subject": f"Occurrence {index}",
            "body_preview": "Need welding wire quote",
            "received_at": f"2026-08-0{index}T10:00:00Z",
        }
        for index, instance_id in enumerate(
            ["event-000001", "event-000002", "event-000003"], start=1
        )
    ]
    classified = [
        {
            "event_id": event_id,
            "event_instance_id": normalized[0]["event_instance_id"],
            "source_id": "hotline_mailbox",
            "client_id": "welding",
            "sender": "buyer@example.com",
            "subject": normalized[0]["subject"],
            "case_type": "irrelevant",
            "priority": "low",
            "confidence": 0.9,
            "reason_code": "not_business_relevant",
            "is_fallback": False,
        },
        *[
            {
                "event_id": event_id,
                "event_instance_id": item["event_instance_id"],
                "source_id": "hotline_mailbox",
                "client_id": "welding",
                "sender": "buyer@example.com",
                "subject": item["subject"],
                "case_type": "duplicate",
                "priority": "medium",
                "confidence": 0.99,
                "reason_code": "duplicate_candidate_confirmed",
                "is_fallback": False,
                "base_classification": {"case_type": "irrelevant"},
                "duplicate": {
                    "is_duplicate": True,
                    "confidence": 0.99,
                    "reason_code": "exact_message_id_match",
                    "reasoning": "Same transport message as the canonical event.",
                    "candidate": {"event_id": event_id},
                },
            }
            for item in normalized[1:]
        ],
    ]
    (run_dir / "normalized_events.json").write_text(
        json.dumps(normalized), encoding="utf-8"
    )
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified), encoding="utf-8"
    )
    client = _client(storage_dir)

    queue = client.get("/api/rop/dashboard?tab=queue&run_id=run-event-instances")
    assert queue.status_code == 200
    rows = [
        row for row in queue.json()["data"]["queue_rows"] if row["event_id"] == event_id
    ]
    assert {row["event_instance_id"] for row in rows} == {
        "event-000001",
        "event-000002",
        "event-000003",
    }
    queue_html = client.get("/rop?tab=queue&run_id=run-event-instances")
    assert queue_html.status_code == 200
    for instance_id in ("event-000001", "event-000002", "event-000003"):
        assert f"event_instance_id={instance_id}" in queue_html.text

    selector = "event-000003"
    api = client.get(
        f"/api/rop/events/{event_id}?run_id=run-event-instances&event_instance_id={selector}"
    )
    html = client.get(
        f"/rop/events/{event_id}?run_id=run-event-instances&event_instance_id={selector}"
    )
    assert api.status_code == 200
    assert api.json()["data"]["event_instance_id"] == selector
    assert api.json()["data"]["classification"]["case_type"] == "duplicate"
    assert html.status_code == 200
    assert "Duplicate candidate event" in html.text
    assert "Same transport message as the canonical event." in html.text


def test_event_detail_attachments_selected_by_event_instance_id(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-detail-att-inst")
    event_id = "evt-att-inst"
    normalized = [
        {
            "event_id": event_id,
            "event_instance_id": "event-000001",
            "source_id": "hotline_mailbox",
            "client_id": "welding",
            "sender": "buyer@example.com",
            "subject": "Occurrence 1",
            "body_preview": "Need welding wire quote",
            "received_at": "2026-08-01T10:00:00Z",
            "attachments": [
                {
                    "filename": "first.txt",
                    "content_type": "text/plain",
                    "size_bytes": 32,
                }
            ],
        },
        {
            "event_id": event_id,
            "event_instance_id": "event-000002",
            "source_id": "hotline_mailbox",
            "client_id": "welding",
            "sender": "buyer@example.com",
            "subject": "Occurrence 2",
            "body_preview": "Need welding wire quote",
            "received_at": "2026-08-02T10:00:00Z",
            "attachments": [
                {
                    "filename": "second.txt",
                    "content_type": "text/plain",
                    "size_bytes": 32,
                }
            ],
        },
    ]
    classified = [
        {
            "event_id": event_id,
            "event_instance_id": item["event_instance_id"],
            "source_id": "hotline_mailbox",
            "client_id": "welding",
            "sender": "buyer@example.com",
            "subject": item["subject"],
            "case_type": "duplicate",
            "priority": "medium",
            "confidence": 0.99,
            "reason_code": "duplicate_candidate_confirmed",
            "is_fallback": False,
            "base_classification": {"case_type": "new_lead"},
            "duplicate": {
                "is_duplicate": True,
                "confidence": 0.99,
                "reason_code": "exact_message_id_match",
                "candidate": {"event_id": event_id},
            },
        }
        for item in normalized
    ]
    attachment_extraction = {
        "run_id": "run-detail-att-inst",
        "status": "ok",
        "aggregate": {
            "event_count": 2,
            "attachment_count": 2,
            "preview_available_count": 2,
            "metadata_only_count": 0,
            "refused_count": 0,
            "unsupported_count": 0,
            "failed_count": 0,
        },
        "items": [
            {
                "event_id": event_id,
                "event_instance_id": "event-000001",
                "source_id": "hotline_mailbox",
                "attachment_id": "evt-att-inst-att-0",
                "filename": "first.txt",
                "extraction_status": "preview",
                "preview_available": True,
                "text_preview": "first preview",
            },
            {
                "event_id": event_id,
                "event_instance_id": "event-000002",
                "source_id": "hotline_mailbox",
                "attachment_id": "evt-att-inst-att-1",
                "filename": "second.txt",
                "extraction_status": "preview",
                "preview_available": True,
                "text_preview": "second preview",
            },
        ],
    }
    (run_dir / "normalized_events.json").write_text(
        json.dumps(normalized), encoding="utf-8"
    )
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified), encoding="utf-8"
    )
    (run_dir / "attachment_extraction.json").write_text(
        json.dumps(attachment_extraction), encoding="utf-8"
    )

    data_first = build_rop_event_detail_read_model(
        storage_dir,
        "run-detail-att-inst",
        event_id,
        event_instance_id="event-000001",
    )
    data_second = build_rop_event_detail_read_model(
        storage_dir,
        "run-detail-att-inst",
        event_id,
        event_instance_id="event-000002",
    )

    assert [att["filename"] for att in data_first["attachments"]] == ["first.txt"]
    assert [att["filename"] for att in data_second["attachments"]] == ["second.txt"]

    client = _client(storage_dir)
    response = client.get(
        f"/api/rop/events/{event_id}?run_id=run-detail-att-inst&event_instance_id=event-000001"
    )
    assert response.status_code == 200
    assert [att["filename"] for att in response.json()["data"]["attachments"]] == [
        "first.txt"
    ]
    response = client.get(
        f"/api/rop/events/{event_id}?run_id=run-detail-att-inst&event_instance_id=event-000002"
    )
    assert response.status_code == 200
    assert [att["filename"] for att in response.json()["data"]["attachments"]] == [
        "second.txt"
    ]


def test_queue_html_and_api_date_parsing_parity(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-parsing-parity")
    (run_dir / "classified_events.json").write_text(
        json.dumps(
            [
                {
                    "event_id": "evt-inside",
                    "sender": "inside@example.com",
                    "subject": "Inside range",
                    "case_type": "new_lead",
                    "priority": "high",
                    "event_date": "2026-07-15T12:00:00Z",
                },
                {
                    "event_id": "evt-outside",
                    "sender": "outside@example.com",
                    "subject": "Outside range",
                    "case_type": "new_lead",
                    "priority": "high",
                    "event_date": "2026-08-01T12:00:00Z",
                },
                {
                    "event_id": "evt-undated",
                    "sender": "undated@example.com",
                    "subject": "Undated event",
                    "case_type": "new_lead",
                    "priority": "high",
                },
            ]
        ),
        encoding="utf-8",
    )
    client = _client(storage_dir)

    for query, expected_ids in (
        ("date_from=2026-07-15", ["evt-outside", "evt-inside"]),
        ("date_to=2026-07-15", ["evt-inside"]),
        ("date_from=2026-07-01&date_to=2026-07-31", ["evt-inside"]),
        ("date_from=2026-07-15&date_to=2026-07-15", ["evt-inside"]),
    ):
        html = client.get("/rop?tab=queue&run_id=run-parsing-parity&" + query)
        api = client.get(
            "/api/rop/dashboard?tab=queue&run_id=run-parsing-parity&" + query
        )

        assert html.status_code == 200
        assert api.status_code == 200
        assert api.json()["data"]["pagination"]["total_items"] == len(expected_ids)
        assert [
            row["event_id"] for row in api.json()["data"]["queue_rows"]
        ] == expected_ids
        assert ("Inside range" in html.text) is ("evt-inside" in expected_ids)
        assert ("Outside range" in html.text) is ("evt-outside" in expected_ids)
        assert "Undated event" not in html.text
        assert 'name="date_from"' in html.text
        assert 'name="date_to"' in html.text
        if "date_from" in query:
            assert f'value="{query.split("date_from=")[1][:10]}"' in html.text
        if "date_to" in query:
            assert f'value="{query.rsplit("date_to=", 1)[1][:10]}"' in html.text

    for query, message in (
        ("date_from=invalid", "Invalid date_from"),
        (
            "date_from=2026-07-31&date_to=2026-07-01",
            "date_from must not be after date_to",
        ),
    ):
        html = client.get("/rop?tab=queue&run_id=run-parsing-parity&" + query)
        api = client.get(
            "/api/rop/dashboard?tab=queue&run_id=run-parsing-parity&" + query
        )

        assert html.status_code >= 400
        assert message in html.text or "invalid_params" in html.text
        assert api.status_code == 400
        assert api.json()["error"]["code"] == "invalid_params"


def _assert_badge_in(html: str, css_class: str, value: str) -> None:
    assert f'class="badge {css_class}">{value}<' in html


def test_event_detail_route_badges_classification_only(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-route-cls-only")
    client = _client(storage_dir)

    for lang, expected_yes, expected_case in [
        ("en", "Yes", "New lead"),
        ("ru", "Да", "Новый лид"),
    ]:
        response = client.get(
            f"/rop/events/evt-1?run_id=run-route-cls-only&lang={lang}"
        )
        assert response.status_code == 200
        html = response.text

        _assert_badge_in(html, "bg-secondary-lt", expected_case)
        _assert_badge_in(html, "bg-danger-lt", "high")
        _assert_badge_in(html, "bg-warning-lt", expected_yes)


def test_event_detail_route_badges_full_data(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-route-full")
    (run_dir / "rop_ai_adjudicator_results.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "event_id": "evt-1",
                        "ai_used": True,
                        "ai_status": "ok",
                        "ai_confidence": 0.92,
                        "ai_reason": "ai review complete",
                        "final_case_type": "new_lead",
                        "final_recommended_queue": "manual_review",
                        "final_correct_action": "manual_review",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "rop_final_decisions.json").write_text(
        json.dumps(
            {
                "summary": {
                    "total_events": 1,
                    "decision_source_counts": {"ai_adjudicator": 1},
                    "attention_count": 0,
                },
                "events": [
                    {
                        "event_id": "evt-1",
                        "final_case_type": "new_lead",
                        "final_case_subtype": None,
                        "final_queue": "manual_review",
                        "final_action": "manual_review",
                        "final_decision_source": "ai_adjudicator",
                        "final_confidence": 0.92,
                        "needs_attention": False,
                        "attention_reason": None,
                        "automation_allowed": False,
                        "bitrix_write_allowed": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    client = _client(storage_dir)

    for lang, expected_yes, expected_no, expected_case in [
        ("en", "Yes", "No", "New lead"),
        ("ru", "Да", "Нет", "Новый лид"),
    ]:
        response = client.get(f"/rop/events/evt-1?run_id=run-route-full&lang={lang}")
        assert response.status_code == 200
        html = response.text

        _assert_badge_in(html, "bg-secondary-lt", expected_case)
        _assert_badge_in(html, "bg-danger-lt", "high")
        _assert_badge_in(html, "bg-warning-lt", expected_yes)

        _assert_badge_in(html, "bg-secondary-lt", expected_yes)
        _assert_badge_in(html, "bg-success-lt", "ok")
        _assert_badge_in(html, "bg-warning-lt", "manual_review")

        _assert_badge_in(html, "bg-secondary-lt", "ai_adjudicator")
        _assert_badge_in(html, "bg-secondary-lt", expected_no)


def test_event_detail_route_badges_no_adjudicator(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-route-no-adj")
    (run_dir / "rop_ai_adjudicator_results.json").write_text(
        json.dumps({"results": []}), encoding="utf-8"
    )
    client = _client(storage_dir)

    for lang, expected_yes, expected_no, fd_title, expected_case in [
        ("en", "Yes", "No", "Final decision", "New lead"),
        ("ru", "Да", "Нет", "Итоговое решение", "Новый лид"),
    ]:
        response = client.get(f"/rop/events/evt-1?run_id=run-route-no-adj&lang={lang}")
        assert response.status_code == 200
        html = response.text

        assert fd_title in html

        _assert_badge_in(html, "bg-secondary-lt", expected_case)
        badge_new_lead = f'class="badge bg-secondary-lt">{expected_case}<'
        assert html.count(badge_new_lead) >= 2

        _assert_badge_in(html, "bg-danger-lt", "high")
        _assert_badge_in(html, "bg-warning-lt", expected_yes)

        _assert_badge_in(html, "bg-secondary-lt", "deterministic")
        _assert_badge_in(html, "bg-secondary-lt", "high_priority")
        _assert_badge_in(html, "bg-secondary-lt", "review")
        _assert_badge_in(html, "bg-secondary-lt", expected_no)

        assert "bg-success-lt" not in html


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


def test_attachment_download_forced_headers_and_content(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _seed_download_attachment(storage_dir, "run-dl")
    client = _client(storage_dir)
    response = client.get(
        "/rop/attachments/evt-1-att-0/download?run_id=run-dl",
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert response.content == b"%PDF-1.4 download body bytes"
    disposition = response.headers.get("content-disposition", "")
    assert disposition.startswith("attachment")
    assert "brief.pdf" in disposition
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("cache-control") == "no-store"
    assert response.headers.get("content-type", "").startswith(
        "application/octet-stream"
    )


def test_attachment_download_invalid_run_id(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _seed_download_attachment(storage_dir, "run-dl")
    client = _client(storage_dir)
    response = client.get("/rop/attachments/evt-1-att-0/download?run_id=../escape")
    assert response.status_code == 400
    response = client.get("/rop/attachments/evt-1-att-0/download?run_id=")
    assert response.status_code == 400


def test_attachment_download_unknown_and_traversal(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _seed_download_attachment(storage_dir, "run-dl")
    client = _client(storage_dir)
    response = client.get("/rop/attachments/unknown-id/download?run_id=run-dl")
    assert response.status_code == 404
    response = client.get("/rop/attachments/..%2F..%2Fsecret/download?run_id=run-dl")
    assert response.status_code in (400, 404)
    response = client.get("/rop/attachments/evt-1-att-0/download?run_id=run-other")
    assert response.status_code == 404


def test_attachment_download_event_mismatch_fails_closed(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _seed_download_attachment(storage_dir, "run-dl")
    client = _client(storage_dir)
    response = client.get(
        "/rop/attachments/evt-1-att-0/download?run_id=run-dl&event_id=other-event"
    )
    assert response.status_code == 404


def _seed_format_attachment(
    storage_dir: Path,
    run_id: str,
    attachment_id: str,
    filename: str,
    content_type: str,
    content: bytes,
) -> None:
    run_dir = storage_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "classified_events.json").write_text(
        json.dumps([{"event_id": "evt-1"}]), encoding="utf-8"
    )
    store_dir = storage_dir / "attachments" / run_id
    store_dir.mkdir(parents=True, exist_ok=True)
    blob_id = "att-" + sha256(content).hexdigest()[:24]
    (store_dir / f"{blob_id}.bin").write_bytes(content)
    manifest_path = store_dir / "attachment_manifest.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else {
            "run_id": run_id,
            "version": 1,
            "status": "ok",
            "policy": {},
            "aggregate": {"attachment_count": 0, "stored_count": 0},
            "items": [],
        }
    )
    manifest["items"].append(
        {
            "attachment_id": attachment_id,
            "event_id": "evt-1",
            "event_instance_id": "event-000001",
            "blob_id": blob_id,
            "filename": filename,
            "content_type": content_type,
            "size_bytes": len(content),
            "sha256": sha256(content).hexdigest(),
            "storage_status": "stored",
        }
    )
    manifest["aggregate"]["attachment_count"] = len(manifest["items"])
    manifest["aggregate"]["stored_count"] = len(manifest["items"])
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


@pytest.mark.parametrize(
    "filename,content_type,payload",
    [
        ("rfq.txt", "text/plain", b"RFQ: 100 kg ER70S-6 welding wire"),
        ("prices.csv", "text/csv", b"sku,qty\nER70S-6,100\n"),
        ("rfq.pdf", "application/pdf", b"%PDF-1.4 download body bytes"),
        (
            "rfq.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            b"PK\x03\x04 docx download",
        ),
        ("rfq.jpg", "image/jpeg", b"\xff\xd8\xff\xe0 download jpeg"),
        ("rfq.png", "image/png", b"\x89PNG\r\n\x1a\n download png"),
    ],
)
def test_attachment_download_all_supported_formats(
    tmp_path: Path,
    filename: str,
    content_type: str,
    payload: bytes,
) -> None:
    storage_dir = _make_storage(tmp_path)
    _seed_format_attachment(
        storage_dir, "run-dl-formats", "evt-1-att-0", filename, content_type, payload
    )
    client = _client(storage_dir)
    response = client.get(
        "/rop/attachments/evt-1-att-0/download?run_id=run-dl-formats&event_id=evt-1"
    )
    assert response.status_code == 200
    assert response.content == payload
    disposition = response.headers.get("content-disposition", "")
    assert disposition.startswith("attachment;")
    assert response.headers.get("content-type") == "application/octet-stream"
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("cache-control") == "no-store"


def test_attachment_download_blocked_eml_has_no_blob(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_id = "run-dl-eml"
    run_dir = storage_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "classified_events.json").write_text(
        json.dumps([{"event_id": "evt-1"}]), encoding="utf-8"
    )
    store_dir = storage_dir / "attachments" / run_id
    store_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "run_id": run_id,
        "version": 1,
        "status": "ok",
        "policy": {},
        "aggregate": {"attachment_count": 1, "stored_count": 0},
        "items": [
            {
                "attachment_id": "evt-1-att-0",
                "event_id": "evt-1",
                "event_instance_id": "event-000001",
                "blob_id": None,
                "filename": "nested.eml",
                "content_type": "message/rfc822",
                "size_bytes": 128,
                "sha256": None,
                "storage_status": "blocked",
                "reason_code": "blocked_email_attachment",
            }
        ],
    }
    (store_dir / "attachment_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    client = _client(storage_dir)
    response = client.get(
        "/rop/attachments/evt-1-att-0/download?run_id=run-dl-eml&event_id=evt-1"
    )
    assert response.status_code == 404
    assert not list(store_dir.glob("*.bin"))


class TestAttachmentDownloadAuth:
    _env: dict[str, str] = {}
    _previous_env: dict[str, str | None] = {}

    @classmethod
    def setup_class(cls) -> None:
        cls._env, cls._previous_env = _set_auth_env()

    @classmethod
    def teardown_class(cls) -> None:
        _clear_auth_env(cls._env, cls._previous_env)

    def test_unauthenticated_download_rejected(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        _seed_download_attachment(storage_dir, "run-dl")
        client = _auth_client(storage_dir)
        response = client.get(
            "/rop/attachments/evt-1-att-0/download?run_id=run-dl",
            follow_redirects=False,
        )
        assert response.status_code in (302, 401)

    def test_authenticated_rop_principal_can_download(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        _seed_download_attachment(storage_dir, "run-dl")
        client = _auth_client(storage_dir)
        login = client.post(
            "/auth/login",
            data={"user_id": "rop", "token": "rop-test-token"},
            follow_redirects=False,
        )
        assert login.status_code in (200, 302)
        response = client.get("/rop/attachments/evt-1-att-0/download?run_id=run-dl")
        assert response.status_code == 200
        assert response.content == b"%PDF-1.4 download body bytes"
        assert response.headers.get("x-content-type-options") == "nosniff"

    def test_authenticated_admin_can_download(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        _seed_download_attachment(storage_dir, "run-dl")
        client = _auth_client(storage_dir)
        client.post(
            "/auth/login",
            data={"user_id": "admin", "token": "admin-test-token"},
            follow_redirects=False,
        )
        response = client.get("/rop/attachments/evt-1-att-0/download?run_id=run-dl")
        assert response.status_code == 200

    def test_authenticated_rop_unknown_attachment_404(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        _seed_download_attachment(storage_dir, "run-dl")
        client = _auth_client(storage_dir)
        client.post(
            "/auth/login",
            data={"user_id": "rop", "token": "rop-test-token"},
            follow_redirects=False,
        )
        response = client.get("/rop/attachments/not-there/download?run_id=run-dl")
        assert response.status_code == 404


def test_event_detail_attachment_lifecycle_metadata(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = storage_dir / "runs" / "run-detail-lifecycle"
    run_dir.mkdir(parents=True, exist_ok=True)
    event_id = "evt-lifecycle"
    normalized = [
        {
            "event_id": event_id,
            "event_instance_id": "event-000001",
            "source_id": "hotline_mailbox",
            "client_id": "welding",
            "sender": "buyer@example.com",
            "subject": "Attachment lifecycle",
            "body_preview": "see attached",
            "received_at": "2026-08-03T10:00:00Z",
            "attachments": [
                {
                    "filename": "quote.pdf",
                    "content_type": "application/pdf",
                    "size_bytes": 128,
                }
            ],
        }
    ]
    classified = [
        {
            "event_id": event_id,
            "event_instance_id": "event-000001",
            "source_id": "hotline_mailbox",
            "client_id": "welding",
            "case_type": "new_lead",
            "priority": "high",
            "confidence": 0.9,
        }
    ]
    extraction = {
        "run_id": "run-detail-lifecycle",
        "status": "ok",
        "aggregate": {"attachment_count": 2},
        "items": [
            {
                "event_id": event_id,
                "event_instance_id": "event-000001",
                "attachment_id": "evt-lifecycle-att-0",
                "filename": "quote.pdf",
                "content_type": "application/pdf",
                "size_bytes": 128,
                "extraction_status": "metadata_only",
                "storage_status": "stored",
                "analysis_status": "ok",
                "sha256": "a" * 64,
                "download_url": "/rop/attachments/evt-lifecycle-att-0/download?run_id=run-detail-lifecycle",
                "preview_available": False,
            },
            {
                "event_id": event_id,
                "event_instance_id": "event-000001",
                "attachment_id": "evt-lifecycle-att-1",
                "filename": "forwarded.eml",
                "content_type": "message/rfc822",
                "size_bytes": None,
                "extraction_status": "refused",
                "storage_status": "blocked",
                "reason_code": "blocked_email_attachment",
                "analysis_status": "disabled",
                "preview_available": False,
            },
        ],
    }
    (run_dir / "normalized_events.json").write_text(
        json.dumps(normalized), encoding="utf-8"
    )
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified), encoding="utf-8"
    )
    (run_dir / "attachment_extraction.json").write_text(
        json.dumps(extraction), encoding="utf-8"
    )

    data = build_rop_event_detail_read_model(
        storage_dir, "run-detail-lifecycle", event_id
    )
    assert len(data["attachments"]) == 2
    att = data["attachments"][0]
    assert att["filename"] == "quote.pdf"
    assert att["storage_status"] == "stored"
    assert att["analysis_status"] == "ok"
    assert att["download_url"].startswith("/rop/attachments/")
    assert att["sha256"] == "a" * 64
    blocked = data["attachments"][1]
    assert blocked["filename"] == "forwarded.eml"
    assert blocked["storage_status"] == "blocked"
    assert blocked["reason_code"] == "blocked_email_attachment"

    client = _client(storage_dir)
    response = client.get(f"/api/rop/events/{event_id}?run_id=run-detail-lifecycle")
    assert response.status_code == 200
    api_att = response.json()["data"]["attachments"][0]
    assert api_att["storage_status"] == "stored"
    assert api_att["analysis_status"] == "ok"
    assert api_att["download_url"].startswith("/rop/attachments/")
    api_blocked = response.json()["data"]["attachments"][1]
    assert api_blocked["storage_status"] == "blocked"
    assert api_blocked["reason_code"] == "blocked_email_attachment"


def _build_rop_app(storage_dir: Path, settings: dict[str, Any] | None = None):
    from beeagent_module.interfaces.ui.app import build_beeui_app

    return build_beeui_app(
        settings=settings or _build_settings(),
        logger=_logger(),
        storage_dir=storage_dir,
    )


def test_rop_page_uses_released_icon_tab_contract(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.app import build_beeui_app

    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-icons")
    _write_rop_web_projection(storage_dir)
    app = build_beeui_app(
        settings=_build_settings(),
        logger=_logger(),
        storage_dir=storage_dir,
    )
    client = TestClient(app)

    response = client.get("/rop?tab=overview")

    assert response.status_code == 200
    html = response.text
    assert 'data-beeui-page-tabs-progressive="true"' in html
    assert 'data-beeui-page-tab="true"' in html

    expected_icons = {
        "overview": "dashboard",
        "queue": "queue",
        "threads": "messages",
        "ai_assist": "ai",
        "sources": "source",
        "attachments": "attachment",
        "evidence": "evidence",
        "bitrix": "integration",
        "recommendations": "recommendation",
    }

    assert len(set(expected_icons.values())) == 9
    assert html.count('data-beeui-tab-icon="') == 9

    for tab_id, icon in expected_icons.items():
        href = f"/rop?tab={tab_id}"
        href_pos = html.index(href)
        anchor_end = html.index("</a>", href_pos)
        anchor_html = html[href_pos:anchor_end]

        assert f'data-beeui-tab-icon="{icon}"' in anchor_html


def test_rop_projection_missing_root_index_fails_explicitly(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-missing-index")
    client = TestClient(_build_rop_app(storage_dir))

    response = client.get("/api/rop/dashboard")

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "web_projection_unavailable"
    assert "regenerate" in body["error"]["message"]
    assert not (storage_dir / "interfaces" / "rop_web_projection.json").exists()


def test_rop_projection_malformed_root_index_fails_explicitly(
    tmp_path: Path,
) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-malformed-index")
    (storage_dir / "interfaces" / "rop_web_projection.json").write_text(
        "{bad json", encoding="utf-8"
    )
    client = TestClient(_build_rop_app(storage_dir))

    response = client.get("/api/rop/dashboard")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "web_projection_unavailable"


@pytest.mark.parametrize(
    "malformed_index",
    (
        {"total_runs": None},
        {"total_runs": True},
        {"total_runs": "1"},
        {"run_ids": ["run-invalid-index"] * 21},
    ),
)
def test_rop_projection_invalid_index_fails_closed_without_read_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    malformed_index: dict[str, object],
) -> None:
    from beeagent_module.cases import rop_dashboard as rop_dashboard_module
    from beeagent_module.cases.rop_dashboard import rop_web_projection_entry_path

    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-invalid-index")
    _write_rop_web_projection(storage_dir)
    index_path = storage_dir / "interfaces" / "rop_web_projection.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index.update(malformed_index)
    index_path.write_text(json.dumps(index), encoding="utf-8")
    entry_path = rop_web_projection_entry_path(storage_dir, "run-invalid-index")
    before_index = index_path.read_bytes()
    before_entry = entry_path.read_bytes()

    def fail_historical_read(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("historical aggregation must not run on GET")

    client = TestClient(_build_rop_app(storage_dir))
    monkeypatch.setattr(
        rop_dashboard_module, "_aggregate_period_events", fail_historical_read
    )
    monkeypatch.setattr(rop_dashboard_module, "_list_rop_run_ids", fail_historical_read)

    html = client.get("/rop")
    api = client.get("/api/rop/dashboard")

    assert html.status_code == 503
    assert api.status_code == 503
    assert api.json()["error"]["code"] == "web_projection_unavailable"
    assert index_path.read_bytes() == before_index
    assert entry_path.read_bytes() == before_entry


def test_rop_projection_missing_selected_run_entry_fails_explicitly(
    tmp_path: Path,
) -> None:
    from beeagent_module.cases.rop_dashboard import rop_web_projection_entry_path

    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-missing-entry")
    _write_rop_web_projection(storage_dir)
    rop_web_projection_entry_path(storage_dir, "run-missing-entry").unlink()
    client = TestClient(_build_rop_app(storage_dir))

    response = client.get("/api/rop/dashboard?run_id=run-missing-entry")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "web_projection_unavailable"


def test_rop_projection_wrong_run_entry_fails_explicitly(tmp_path: Path) -> None:
    from beeagent_module.cases.rop_dashboard import rop_web_projection_entry_path

    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-wrong-entry")
    _write_rop_web_projection(storage_dir)
    entry_path = rop_web_projection_entry_path(storage_dir, "run-wrong-entry")
    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    entry["run_id"] = "other-run"
    entry_path.write_text(json.dumps(entry), encoding="utf-8")
    client = TestClient(_build_rop_app(storage_dir))

    response = client.get("/api/rop/dashboard?run_id=run-wrong-entry")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "web_projection_unavailable"


def test_rop_projection_missing_period_entry_fails_explicitly(tmp_path: Path) -> None:
    from beeagent_module.cases.rop_dashboard import rop_web_projection_entry_path

    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-missing-period")
    _write_rop_web_projection(storage_dir)
    entry_path = rop_web_projection_entry_path(storage_dir, "run-missing-period")
    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    entry["dashboards"].pop("7d", None)
    entry_path.write_text(json.dumps(entry), encoding="utf-8")
    client = TestClient(_build_rop_app(storage_dir))

    response = client.get("/api/rop/dashboard?run_id=run-missing-period&period=7d")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "web_projection_unavailable"


def test_rop_projection_get_never_falls_back_to_run_enumeration(
    tmp_path: Path,
) -> None:
    from beeagent_module.cases.rop_dashboard import rop_web_projection_entry_path

    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-a")
    _write_run_artifacts(storage_dir, "run-b")
    _write_rop_web_projection(storage_dir)
    rop_web_projection_entry_path(storage_dir, "run-a").unlink()
    client = TestClient(_build_rop_app(storage_dir))

    response = client.get("/api/rop/dashboard?run_id=run-a")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "web_projection_unavailable"


def test_rop_projection_get_never_regenerates_or_writes(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-no-write")
    client = TestClient(_build_rop_app(storage_dir))

    response = client.get("/api/rop/dashboard")

    assert response.status_code == 503
    assert not (storage_dir / "interfaces" / "rop_web_projection.json").exists()
    assert not (storage_dir / "interfaces" / "rop_web_projection").exists()


def test_rop_projection_error_is_stable_api_error(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-stable-error")
    client = TestClient(_build_rop_app(storage_dir))

    response = client.get("/api/rop/dashboard")

    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "web_projection_unavailable"
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["message"]


def test_rop_available_runs_and_total_runs_from_bounded_catalog(
    tmp_path: Path,
) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-cat-a")
    _write_run_artifacts(storage_dir, "run-cat-b")
    _write_run_artifacts(storage_dir, "run-cat-c")
    _write_rop_web_projection(storage_dir)
    client = _client(storage_dir)

    response = client.get("/api/rop/dashboard?run_id=run-cat-b")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert set(payload["available_runs"]) == {"run-cat-a", "run-cat-b", "run-cat-c"}
    assert payload["kpis"]["total_runs"] == 3


def test_rop_web_read_consumes_only_projection_artifacts(tmp_path: Path) -> None:
    from beeagent_module.cases.rop_dashboard import rop_web_projection_entry_path

    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-read-a")
    _write_run_artifacts(storage_dir, "run-read-b")
    _write_rop_web_projection(storage_dir)
    entry_path = rop_web_projection_entry_path(storage_dir, "run-read-b")
    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    entry["dashboards"]["all"]["queues"] = {
        "high_priority": [
            {
                "event_id": "evt-proj",
                "source_id": "hotline_mailbox",
                "sender": "proj@example.com",
                "subject": "Projection row",
                "case_type": "new_lead",
                "priority": "high",
                "run_id": "run-read-b",
            }
        ]
    }
    entry_path.write_text(json.dumps(entry), encoding="utf-8")
    client = _client(storage_dir)

    response = client.get("/api/rop/dashboard?run_id=run-read-b&period=all")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["queues"]["high_priority"][0]["event_id"] == "evt-proj"
    assert set(payload["available_runs"]) == {"run-read-a", "run-read-b"}


def test_rop_trusted_attach_existing_overlay_in_tab_path(tmp_path: Path) -> None:
    from beeagent_module.cases.rop_dashboard import rop_web_projection_entry_path

    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-attach")
    _write_rop_web_projection(storage_dir)
    entry_path = rop_web_projection_entry_path(storage_dir, "run-attach")
    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    entry["dashboards"]["all"]["queues"] = {
        "high_priority": [
            {
                "event_id": "evt-attach",
                "event_instance_id": "inst-1",
                "source_id": "hotline_mailbox",
                "sender": "client@example.com",
                "subject": "Attach existing",
                "case_type": "new_lead",
                "bot_case_type": "new_lead",
                "priority": "high",
                "run_id": "run-attach",
            }
        ]
    }
    entry_path.write_text(json.dumps(entry), encoding="utf-8")
    (storage_dir / "interfaces" / "rop_writeback_state.json").write_text(
        json.dumps(
            {
                "version": 1,
                "events": {
                    "welding|hotline_mailbox|evt-attach|inst-1": {
                        "event_id": "evt-attach",
                        "event_instance_id": "inst-1",
                        "source_id": "hotline_mailbox",
                        "outcome": "attach_existing",
                        "target_provenance": "thread_resolved",
                        "last_run_id": "run-attach",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    client = _client(storage_dir)

    response = client.get("/api/rop/dashboard?run_id=run-attach&period=all&tab=queue")

    assert response.status_code == 200
    row = response.json()["data"]["queue_rows"][0]
    assert row["event_id"] == "evt-attach"
    assert row["case_type"] == "existing_deal"
    assert row["bot_case_type"] == "existing_deal"
    assert row["semantic_case_type"] == "new_lead"


def test_rop_bitrix_tab_evidence_available_with_valid_artifact(
    tmp_path: Path,
) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_run_artifacts(storage_dir, "run-bitrix-ok")
    (run_dir / "bitrix_reconciliation.json").write_text(
        json.dumps(
            {
                "run_id": "run-bitrix-ok",
                "status": "ok",
                "aggregate": {"matched_count": 1},
                "items": [],
            }
        ),
        encoding="utf-8",
    )
    _write_rop_web_projection(storage_dir)
    client = _client(storage_dir)

    response = client.get("/rop?tab=bitrix&run_id=run-bitrix-ok")

    assert response.status_code == 200
    assert "artifact is not available" not in response.text
    assert "Bitrix Evidence Board" in response.text


def test_rop_bitrix_tab_evidence_unavailable_with_missing_artifact(
    tmp_path: Path,
) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-bitrix-missing")
    _write_rop_web_projection(storage_dir)
    client = _client(storage_dir)

    response = client.get("/rop?tab=bitrix&run_id=run-bitrix-missing")

    assert response.status_code == 200
    assert "artifact is not available" in response.text
    assert "Bitrix Evidence Board" in response.text


def test_rop_bitrix_tab_evidence_unavailable_with_malformed_artifact(
    tmp_path: Path,
) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_run_artifacts(storage_dir, "run-bitrix-malformed")
    (run_dir / "bitrix_reconciliation.json").write_text("{bad json}", encoding="utf-8")
    _write_rop_web_projection(storage_dir)
    client = _client(storage_dir)

    response = client.get("/rop?tab=bitrix&run_id=run-bitrix-malformed")

    assert response.status_code == 200
    assert "artifact is not available" in response.text
    assert "Bitrix Evidence Board" in response.text


def _write_many_rop_runs(storage_dir: Path, count: int) -> list[str]:
    run_ids: list[str] = []
    for index in range(count):
        run_id = f"run-hist-{index:03d}"
        _write_run_artifacts(storage_dir, run_id)
        run_ids.append(run_id)
    return run_ids


def _set_scoped_auth_env_for_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "scoped-session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN1_TOKEN", "admin1-test-token")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN2_TOKEN", "admin2-test-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROPVIEWER_TOKEN", "ropviewer-test-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROPADMIN_TOKEN", "ropadmin-test-token")


def test_rop_auth_get_no_historical_scan_with_many_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.cases import rop_dashboard as rop_dashboard_module

    _set_scoped_auth_env_for_test(monkeypatch)
    storage_dir = _make_storage(tmp_path)
    _write_many_rop_runs(storage_dir, 40)
    _write_rop_web_projection(storage_dir)
    client = _scoped_auth_client(storage_dir)
    self_login = client.post(
        "/auth/login",
        data={"user_id": "ropviewer", "token": "ropviewer-test-token"},
        follow_redirects=False,
    )
    assert self_login.status_code in (302, 200)

    def _explode(*_args: object, **_kwargs: object):
        raise RuntimeError("historical scan must not run on GET")

    monkeypatch.setattr(rop_dashboard_module, "_list_rop_run_ids", _explode)

    html = client.get("/rop", follow_redirects=False)
    api = client.get("/api/rop/dashboard")

    assert html.status_code == 200
    assert api.status_code == 200
    payload = api.json()["data"]
    assert len(payload["available_runs"]) <= 20
    assert payload["total_runs"] == 40


def test_rop_auth_explicit_old_run_id_outside_bounded_catalog_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.cases import rop_dashboard as rop_dashboard_module

    _set_scoped_auth_env_for_test(monkeypatch)
    storage_dir = _make_storage(tmp_path)
    _write_many_rop_runs(storage_dir, 40)
    _write_rop_web_projection(storage_dir)
    client = _scoped_auth_client(storage_dir)
    login = client.post(
        "/auth/login",
        data={"user_id": "ropviewer", "token": "ropviewer-test-token"},
        follow_redirects=False,
    )
    assert login.status_code in (302, 200)

    def _explode(*_args: object, **_kwargs: object):
        raise RuntimeError("historical scan must not run on GET")

    monkeypatch.setattr(rop_dashboard_module, "_list_rop_run_ids", _explode)

    old_run_id = "run-hist-000"
    html = client.get(f"/rop?run_id={old_run_id}", follow_redirects=False)
    api = client.get(f"/api/rop/dashboard?run_id={old_run_id}")

    assert html.status_code == 403
    assert api.status_code == 403


def test_rop_auth_unknown_run_id_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.cases import rop_dashboard as rop_dashboard_module

    _set_scoped_auth_env_for_test(monkeypatch)
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-known")
    _write_rop_web_projection(storage_dir)
    client = _scoped_auth_client(storage_dir)
    login = client.post(
        "/auth/login",
        data={"user_id": "ropviewer", "token": "ropviewer-test-token"},
        follow_redirects=False,
    )
    assert login.status_code in (302, 200)

    def _explode(*_args: object, **_kwargs: object):
        raise RuntimeError("historical scan must not run on GET")

    monkeypatch.setattr(rop_dashboard_module, "_list_rop_run_ids", _explode)

    html = client.get("/rop?run_id=run-unknown", follow_redirects=False)
    api = client.get("/api/rop/dashboard?run_id=run-unknown")

    assert html.status_code == 403
    assert api.status_code == 403


def test_rop_auth_missing_projection_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.cases import rop_dashboard as rop_dashboard_module

    _set_scoped_auth_env_for_test(monkeypatch)
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-no-proj")
    client = _scoped_auth_client(storage_dir)
    (storage_dir / "interfaces" / "rop_web_projection.json").unlink()
    login = client.post(
        "/auth/login",
        data={"user_id": "ropviewer", "token": "ropviewer-test-token"},
        follow_redirects=False,
    )
    assert login.status_code in (302, 200)

    def _explode(*_args: object, **_kwargs: object):
        raise RuntimeError("historical scan must not run on GET")

    monkeypatch.setattr(rop_dashboard_module, "_list_rop_run_ids", _explode)

    html = client.get("/rop", follow_redirects=False)
    api = client.get("/api/rop/dashboard")

    assert html.status_code == 503
    assert api.status_code == 503
    assert api.json()["error"]["code"] == "web_projection_unavailable"


def test_rop_auth_malformed_projection_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.cases import rop_dashboard as rop_dashboard_module

    _set_scoped_auth_env_for_test(monkeypatch)
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-malformed-proj")
    client = _scoped_auth_client(storage_dir)
    (storage_dir / "interfaces" / "rop_web_projection.json").write_text(
        "{bad json}", encoding="utf-8"
    )
    login = client.post(
        "/auth/login",
        data={"user_id": "ropviewer", "token": "ropviewer-test-token"},
        follow_redirects=False,
    )
    assert login.status_code in (302, 200)

    def _explode(*_args: object, **_kwargs: object):
        raise RuntimeError("historical scan must not run on GET")

    monkeypatch.setattr(rop_dashboard_module, "_list_rop_run_ids", _explode)

    html = client.get("/rop", follow_redirects=False)
    api = client.get("/api/rop/dashboard")

    assert html.status_code == 503
    assert api.status_code == 503
    assert api.json()["error"]["code"] == "web_projection_unavailable"


def test_rop_available_runs_bounded_and_total_runs_scalar(tmp_path: Path) -> None:
    from beeagent_module.cases.rop_dashboard import ROP_WEB_PROJECTION_RUNS_MAX

    storage_dir = _make_storage(tmp_path)
    _write_many_rop_runs(storage_dir, ROP_WEB_PROJECTION_RUNS_MAX + 10)
    _write_rop_web_projection(storage_dir)
    client = _client(storage_dir)

    response = client.get("/api/rop/dashboard")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert len(payload["available_runs"]) == ROP_WEB_PROJECTION_RUNS_MAX
    assert payload["total_runs"] == ROP_WEB_PROJECTION_RUNS_MAX + 10
    assert payload["kpis"]["total_runs"] == ROP_WEB_PROJECTION_RUNS_MAX + 10


def test_rop_projection_index_has_bounded_catalog_and_scalar_total(
    tmp_path: Path,
) -> None:
    from beeagent_module.cases.rop_dashboard import (
        ROP_WEB_PROJECTION_RUNS_MAX,
        rop_web_projection_index,
    )

    storage_dir = _make_storage(tmp_path)
    _write_many_rop_runs(storage_dir, ROP_WEB_PROJECTION_RUNS_MAX + 5)
    _write_rop_web_projection(storage_dir)

    index = rop_web_projection_index(storage_dir)

    assert index is not None
    assert len(index["run_ids"]) == ROP_WEB_PROJECTION_RUNS_MAX
    assert index["total_runs"] == ROP_WEB_PROJECTION_RUNS_MAX + 5
    assert index["latest_run_id"] == index["run_ids"][0]
