from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


def _client(storage_dir: Path, settings: dict[str, Any] | None = None) -> TestClient:
    from beeagent_module.interfaces.ui.app import build_beeui_app

    app = build_beeui_app(
        settings=settings or _build_settings(),
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


def test_rop_queue_detail_link_is_localized_in_ru(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-rop-detail-ru")
    client = _client(storage_dir)

    response = client.get("/rop?run_id=run-rop-detail-ru&tab=queue&lang=ru")

    assert response.status_code == 200
    assert "Подробнее" in response.text
    assert (
        'href="/rop/events/evt-1?run_id=run-rop-detail-ru&amp;lang=ru"' in response.text
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
        assert "TODAY&#39;S EMAILS" in html
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
        assert layout[1]["title"] == "Email Workload"
        assert layout[1]["width"] == 3
        assert layout[2]["type"] == "chart"
        assert layout[2]["title"] == "Action Required"
        assert layout[2]["width"] == 3

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
    area = next(chart for chart in charts if chart["title"] == "Email intake trend")
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
        chart = next(
            block for block in layout if block["title"] == "Email intake trend"
        )
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
        "Open Queue",
        "Open Bitrix",
    ]
    assert items[0]["href"] == "/rop?tab=overview&period=today"
    assert items[1]["href"] == "/rop?tab=overview&period=7d"
    assert items[4]["href"] == "/rop?tab=queue&period=7d"
    assert items[5]["href"] == "/rop?tab=bitrix&period=7d"


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
    queue_block = next(
        block for block in layout if block.get("type") == "data_table"
    )

    assert action_block["series"] == [2, 0]
    assert "2 items need review" in action_block["subtitle"]
    assert queue_block["rows"][0]["evidence"]["href"] == (
        "/rop/events/evt-1?run_id=run-overview-actions"
    )

    ru_layout = build_rop_page_layout(data, tab="overview", locale="ru")
    ru_queue_block = next(
        block for block in ru_layout if block.get("type") == "data_table"
    )

    assert ru_queue_block["rows"][0]["evidence"]["href"] == (
        "/rop/events/evt-1?run_id=run-overview-actions&lang=ru"
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

    assert layout[0]["type"] == "data_table"
    assert layout[0]["title"] == "ROP Work Queue"
    assert [col["label"] for col in layout[0]["columns"]] == [
        "Priority",
        "Sender / Client",
        "Subject / Request",
        "Date",
        "Classification",
        "Bitrix status",
    ]
    assert layout[0]["rows"][0]["classification"] == "new_lead"
    assert layout[0]["rows"][0]["priority"]["label"] == "high"


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
    item = layout[0]["items"][0]

    assert item["label"] == "Not reconciled"
    assert "Run read-only reconcile-bitrix" in item["value"]


def test_api_rop_dashboard_invalid_period_degrades_to_default(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-invalid-period")
    client = _client(storage_dir)

    response = client.get("/api/rop/dashboard", params={"period": "14d"})

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["period"] == "7d"
    assert payload["default_period"] == "7d"
    assert payload["configured_periods"] == [
        "today",
        "yesterday",
        "7d",
        "30d",
        "90d",
        "365d",
        "all",
    ]
    assert any(w.get("code") == "invalid_period" for w in payload["warnings"])


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
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rich_rop_run(storage_dir, "run-cap-001")
    many_events = []
    for i in range(60):
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
    assert len(events) <= 50


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
    assert fds["attention_count"] == 1


def test_rop_dashboard_final_decisions_computed_projection(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rich_rop_run(storage_dir, "run-fd-001")
    adj_artifact = {
        "counters": {"adjudicator_enabled": 1, "adjudicator_eligible_count": 2, "adjudicator_used_count": 1},
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
    assert fds["attention_count"] == 1
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


def test_build_final_decisions_artifact_policy(tmp_path: Path) -> None:
    from beeagent_module.core.rop_final_decision import build_final_decisions

    events = [
        {"event_id": "e1", "case_type": "new_lead", "recommended_queue": "sales", "correct_action": "review_new_lead", "confidence": 0.85, "sender": "a@b.com", "subject": "Inquiry"},
        {"event_id": "e2", "case_type": "existing_deal", "recommended_queue": "logistics", "correct_action": "attach_to_deal", "confidence": 0.60, "sender": "b@c.com", "subject": "Re: Order"},
        {"event_id": "e3", "case_type": "irrelevant", "recommended_queue": "ignore", "correct_action": "ignore", "confidence": 0.95, "sender": "noreply@m.com", "subject": "Newsletter"},
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
            "ai_status": "manual_review_degrade",
            "ai_reason": "conflict_signals_detected",
            "ai_confidence": 0.35,
            "final_case_type": "existing_deal",
            "final_recommended_queue": "manual_review",
            "final_correct_action": "manual_review",
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
    assert e2["attention_reason"] == "conflict_signals_detected"
    assert e2["final_queue"] == "logistics"
    assert e2["final_action"] == "attach_to_deal"
    assert e2["automation_allowed"] is False
    assert e2["bitrix_write_allowed"] is False

    e3 = decisions["e3"]
    assert e3["final_decision_source"] == "deterministic"
    assert e3["needs_attention"] is False
    assert e3["automation_allowed"] is False
    assert e3["bitrix_write_allowed"] is False


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

    table = next(block for block in layout if block.get("title") == "Recommendation Items")
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
    assert "Статус AI арбитра" in response.text
    assert "Предложенная AI очередь" in response.text
    assert "Причина внимания" in response.text
    assert "AI adjudicator status" not in response.text
    assert "AI proposed queue" not in response.text
    assert "Attention reason" not in response.text


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
    (run_dir / "rop_final_decisions.json").write_text(
        json.dumps({}), encoding="utf-8"
    )

    data = build_rop_event_detail_read_model(
        storage_dir, "run-detail-final", "evt-1"
    )

    final_decision = data["final_decision"]
    assert final_decision["event_id"] == "evt-1"
    assert final_decision["final_decision_source"] == "deterministic"
    availability = {item["artifact_id"]: item["available"] for item in data["evidence_links"]}
    assert availability["rop_ai_adjudicator_results_json"] is True
    assert availability["rop_final_decisions_json"] is True


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
    client = _client(storage_dir)
    response = client.get("/api/rop/dashboard")
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
    assert 'class="dropdown me-1 d-inline-block"' in html
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
    assert "/rop?tab=queue&amp;period=7d&amp;lang=ru" in html
    assert "/rop?tab=bitrix&amp;period=7d&amp;lang=ru" in html
    assert "/rop?tab=evidence&amp;period=7d&amp;lang=ru" in html
    assert "/rop?tab=overview&amp;period=today&amp;lang=ru" in html
    assert "/rop?tab=overview&amp;period=30d&amp;lang=ru" in html


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
    now = datetime.now(timezone.utc)
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
    assert "Email intake trend" in html
    assert "Lead outcome mix" in html
    assert "Bitrix reconciliation" in html
    assert "Source contribution" in html
    assert "chart-rop-email-workload" in html
    assert "chart-rop-action-required" in html
    assert "chart-rop-email-intake" in html
    assert "chart-rop-outcome-mix" in html
    assert "chart-rop-bitrix" in html
    assert "chart-rop-source-contribution" in html
    assert "progress progress-sm" in html
    assert 'class="card card-sm"' in html
    assert "Chart render error" not in html


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
    assert 'class="dropdown me-1 d-inline-block"' in html
    assert "dropdown-menu dropdown-menu-end" in html
    assert "dropdown-item active" in html
    assert "Today" in html
    assert "Yesterday" in html
    assert "Last 7 days" in html
    assert "Last 30 days" in html
    assert "Last 3 months" in html
    assert "Last year" in html
    assert "All time" in html
    assert 'href="/rop?tab=overview&amp;period=today"' in html
    assert 'href="/rop?tab=overview&amp;period=yesterday"' in html
    assert 'href="/rop?tab=overview&amp;period=7d"' in html
    assert 'href="/rop?tab=overview&amp;period=30d"' in html
    assert 'href="/rop?tab=overview&amp;period=90d"' in html
    assert 'href="/rop?tab=overview&amp;period=365d"' in html
    assert 'href="/rop?tab=overview&amp;period=all"' in html
    assert 'href="/rop?tab=queue&amp;period=7d"' in html
    assert 'href="/rop?tab=bitrix&amp;period=7d"' in html
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
    assert "TODAY&#39;S EMAILS" in html
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
    assert "Email intake trend" in html
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

    def test_latest_selection_block_en_formats_datetime(
        self, tmp_path: Path
    ) -> None:
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
                "id": "admin_1",
                "username": "admin1",
                "role": "admin",
                "token_env": "BEEAGENT_WEB_ADMIN1_TOKEN",
            },
            {
                "id": "admin_2",
                "username": "admin2",
                "role": "admin",
                "token_env": "BEEAGENT_WEB_ADMIN2_TOKEN",
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
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN1_TOKEN", "admin1-token")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN2_TOKEN", "admin2-token")

    settings = _build_auth_settings(enabled=True)
    settings["app"]["env"] = env_name

    beeui_settings = build_beeui_settings(settings)

    assert beeui_settings["auth"]["cookie_secure"] is expected_secure


def test_multi_admin_auth_service_preserves_secure_cookie_in_prod(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from beeagent_module.interfaces.ui.app import build_beeui_app

    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN1_TOKEN", "admin1-token")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN2_TOKEN", "admin2-token")

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
        data={"user_id": "admin1", "token": "admin1-token"},
        follow_redirects=False,
    )

    assert response.status_code in (200, 302)
    assert "secure" in response.headers.get("set-cookie", "").lower()


def _set_auth_env() -> tuple[dict[str, str], dict[str, str | None]]:
    env = {
        "BEEAGENT_WEB_SESSION_SECRET": "test-session-secret-not-for-prod",
        "BEEAGENT_WEB_ADMIN1_TOKEN": "admin1-test-token",
        "BEEAGENT_WEB_ADMIN2_TOKEN": "admin2-test-token",
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
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN1_TOKEN", "admin1-token")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN2_TOKEN", "admin2-token")

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

    def test_admin1_can_access_rop(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth")
        client = _auth_client(storage_dir)
        login_resp = self._login(client, "admin1", "admin1-test-token")
        assert login_resp.status_code in (302, 200)
        response = client.get("/rop", follow_redirects=False)
        assert response.status_code == 200

    def test_admin1_can_access_api(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth")
        client = _auth_client(storage_dir)
        self._login(client, "admin1", "admin1-test-token")
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
        monkeypatch.setenv("BEEAGENT_WEB_ADMIN1_TOKEN", "admin1-test-token")
        monkeypatch.setenv("BEEAGENT_WEB_ADMIN2_TOKEN", "operator-test-token")

        settings = _build_auth_settings(enabled=True)
        settings["web"]["auth"]["principals"][1]["role"] = "operator"

        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-operator-role")

        app = build_beeui_app(
            settings=settings,
            logger=_logger(),
            storage_dir=storage_dir,
        )
        service = app.state.beeui_auth_service

        assert service._resolve_role("admin1-test-token") == UserRole.admin
        assert service._resolve_role("operator-test-token") == UserRole.operator

        client = TestClient(app)
        login_resp = client.post(
            "/auth/login",
            data={"user_id": "admin2", "token": "operator-test-token"},
        )
        assert login_resp.status_code in (302, 200)

        response = client.get("/api/rop/dashboard")
        assert response.status_code == 200

    def test_invalid_token_rejected(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _auth_client(storage_dir)
        login_resp = self._login(client, "admin1", "wrong-token")
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
                "id": "admin_1",
                "username": "admin1",
                "role": "admin",
                "token_env": "BEEAGENT_WEB_ADMIN1_TOKEN",
            },
            {
                "id": "admin_2",
                "username": "admin2",
                "role": "admin",
                "token_env": "BEEAGENT_WEB_ADMIN2_TOKEN",
            },
        ],
    }
    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN1_TOKEN", "admin1-token")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN2_TOKEN", "admin2-token")
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
    monkeypatch.delenv("BEEAGENT_WEB_ADMIN2_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="BEEAGENT_WEB_ADMIN2_TOKEN"):
        validate_settings(settings)


def test_auth_settings_fail_fast_duplicate_principal_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    settings["web"]["auth"]["principals"][1]["id"] = "admin_1"

    with pytest.raises(RuntimeError, match="Duplicate web.auth.principals id"):
        validate_settings(settings)


def test_auth_settings_fail_fast_duplicate_username(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    settings["web"]["auth"]["principals"][1]["username"] = "admin1"

    with pytest.raises(RuntimeError, match="Duplicate web.auth.principals username"):
        validate_settings(settings)


def test_auth_settings_fail_fast_duplicate_token_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    settings["web"]["auth"]["principals"][1]["token_env"] = "BEEAGENT_WEB_ADMIN1_TOKEN"

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
            },
            "widget": {
                "enabled": False,
                "token_env": "BITRIX_ROP_WIDGET_TOKEN",
                "default_period": "7d",
                "max_items": 50,
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
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN1_TOKEN", "admin1-token")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN2_TOKEN", "admin2-token")
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
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN1_TOKEN", "admin1-token")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN2_TOKEN", "admin2-token")
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
            }
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
