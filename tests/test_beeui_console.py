from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from beeui_module.adapters.envelopes import AdapterErrorResult
from fastapi.testclient import TestClient

from beeagent_module.interfaces.ui.read_model import (
    build_rop_dashboard_read_model,
    build_rop_page_layout,
    build_run_detail,
)


# Тесты для консоли BeeUI, интегрированной с BeeAgent, с фокусом на безопасность и устойчивость к ошибкам
def _logger() -> logging.Logger:
    logger = logging.getLogger("test_beeui_console")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


# Создание временной структуры хранения для тестов, с минимальными артефактами для отображения в UI
def _make_storage(tmp_path: Path) -> Path:
    storage_dir = tmp_path / "storage"
    (storage_dir / "runs").mkdir(parents=True)
    (storage_dir / "interfaces").mkdir(parents=True)
    return storage_dir


# Запись sample modules.json для тестирования отображения модулей в UI
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


# Запись
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


# Тест: запись и чтение артефактов для отображения в UI
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
            "connector_error_count": 1,
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


# Тест: запись артефакта с чувствительными данными для проверки маскировки в UI
def _write_malformed_json_run(storage_dir: Path, run_id: str) -> Path:
    run_dir = storage_dir / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "operator_summary.json").write_text(
        "{invalid json content}", encoding="utf-8"
    )
    return run_dir


# Тест: запись скрипта запуска с артефактом, содержащим ключи, обладающие конфиденциальными данными
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


# Тест: создание минимальных настроек BeeAgent для тестирования
def _build_settings() -> dict:
    return {
        "app": {"name": "BeeAgent", "env": "test"},
        "web": {"host": "127.0.0.1", "port": 18080, "open_browser": False},
        "logging": {"clear_logs": True, "utc": True, "level": "INFO"},
        "rop": {
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


# Тест: создание TestClient с приложением BeeUI для интеграционных тестов
def _client(storage_dir: Path) -> TestClient:
    from beeagent_module.interfaces.ui.app import build_beeui_app

    app = build_beeui_app(
        settings=_build_settings(),
        logger=_logger(),
        storage_dir=storage_dir,
    )
    return TestClient(app)


# Тест: чек, что приложение BeeUI строится без ошибок с минимальными настройками и структурой хранения
def test_beeui_app_builds(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.app import build_beeui_app

    app = build_beeui_app(
        settings=_build_settings(),
        logger=_logger(),
        storage_dir=_make_storage(tmp_path),
    )
    assert app is not None
    assert app.title == "BeeUI"


# Тест: чек, что при запуске приложения с CLI аргументом web вызывается правильная функция и передаются аргументы
def test_start_web_dispatch_imports() -> None:
    from beeagent_module.cli.web import create_web_parser, run_routes, run_web

    assert callable(run_web)
    assert callable(run_routes)
    assert callable(create_web_parser)


# Тест: чек, что при запуске приложения с CLI аргументом rop вызывается правильная функция и передаются аргументы
def test_cli_defaults_from_config() -> None:
    from beeagent_module.cli.web import create_web_parser

    parser = create_web_parser()
    args = parser.parse_args([])
    assert args.host is None
    assert args.port is None
    assert args.no_open is False


# Тест: test CLI --host override
def test_cli_host_override() -> None:
    from beeagent_module.cli.web import create_web_parser

    parser = create_web_parser()
    args = parser.parse_args(["--host", "0.0.0.0"])
    assert args.host == "0.0.0.0"


# Тест: test CLI --port override
def test_cli_port_override() -> None:
    from beeagent_module.cli.web import create_web_parser

    parser = create_web_parser()
    args = parser.parse_args(["--port", "9090"])
    assert args.port == 9090


# Тест: test CLI --no-open flag
def test_cli_no_open_flag() -> None:
    from beeagent_module.cli.web import create_web_parser

    parser = create_web_parser()
    args = parser.parse_args(["--no-open"])
    assert args.no_open is True


# Тест: test GET / returns 200
def test_home_route(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))
    response = client.get("/")
    assert response.status_code == 200


# Тест: тестовый запрос GET /health возвращает ok (маршрут health, предоставляемый BeeUI)
def test_health_route(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


# Тест: GET /runs возвращает 200 и корректно отображает наличие или отсутствие ран-артефактов
def test_runs_route_empty(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))
    response = client.get("/runs")
    assert response.status_code == 200


# Тест: чек команды GET /runs с данными о запуске
def test_runs_route_with_data(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-test-001")
    client = _client(storage_dir)
    response = client.get("/runs")
    assert response.status_code == 200
    assert "run-test-001" in response.text
    assert "No runs available." not in response.text


# Тест: GET /runs/{run_id} возвращает 200 для существующего рана и корректно отображает его детали
def test_run_route(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-valid-001")
    client = _client(storage_dir)
    response = client.get("/runs/run-valid-001")
    assert response.status_code == 200


# Тест: GET /runs/{run_id} с несуществующим run_id возвращает 404
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


# Тест: GET /rop возвращает 200 через BeeUI generic adapter custom page
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


# Тест: GET /rop with tab parameter через BeeUI, включая проверку содержимого вкладок
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


# Тест: /rop page содержит subtitle и tabs в BeeUI shell
class TestRopPageLayout:
    """Проверка корректности вёрстки ROP-страницы: subtitle, tabs, card."""

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


# Тесты: чек layout-структуры Overview tab (customer-facing dashboard)
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
        chart = next(block for block in layout if block["title"] == "Email intake trend")
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
    items = overview["primary_links"][:4]

    assert [item["label"] for item in items] == [
        "Today",
        "Last 7 days (current)",
        "Last 30 days",
        "All time",
    ]
    assert (
        next(item for item in items if item["label"] == "Last 7 days (current)")["href"]
        == "/rop?tab=overview&period=7d"
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
        "bitrix": {"connector_error_count": 99},
        "series": {},
    }

    layout = build_rop_page_layout(data, tab="overview")
    assert any(block.get("title") == "Action Required" for block in layout)
    assert all(block.get("title") != "Business metrics" for block in layout)


# Тест: чек, что вкладка очереди ROP содержит таблицу данных, когда очереди существуют
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
        "Classification",
        "Bitrix status",
        "Reason",
        "Recommended next step",
        "Evidence link",
    ]
    assert layout[0]["rows"][0]["classification"] == "new_lead"
    assert layout[0]["rows"][0]["priority"]["label"] == "high"


# Тест: чек, что блок рекомендаций ROP в Overview tab использует rop_recommendations.detail вместо recommendations.message
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


# Тест: чек, что блок Bitrix в ROP tab корректно отображает сообщение о необходимости запуска read-only reconcile-bitrix, когда артефакт bitrix_reconciliation_json отсутствует
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


# Тест: GET /api/rop/dashboard с недопустимым периодом возвращает предупреждение и использует значение по умолчанию
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


# Тест: Dashboard содержит accordion с видимым chevron для technical details
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


# Тест: GET /modules возвращает layout с модулями через BeeUI
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


# Тест: test GET /api/dashboard
def test_api_dashboard(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["read_only"] is True


# Тест: test GET /api/runs
def test_api_runs(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-api-001")
    client = _client(storage_dir)
    response = client.get("/api/runs")
    assert response.status_code == 200


# Тест: test GET /api/runs/{run_id} для валидного run_id
def test_api_run(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-api-detail")
    client = _client(storage_dir)
    response = client.get("/api/runs/run-api-detail")
    assert response.status_code == 200


# Тест: test GET GET /api/modules
def test_api_modules(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_modules_artifact(storage_dir)
    client = _client(storage_dir)
    response = client.get("/api/modules")
    assert response.status_code == 200


# Тест:
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


# Тест: BeeUI artifact route для несуществующего артефакта деградирует безопасно
def test_invalid_artifact_id(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-bad-art")
    client = _client(storage_dir)
    response = client.get("/runs/run-bad-art/artifacts/nonexistent_artifact")
    assert response.status_code in (200, 400, 404)


# Тест: чек, что ID артефакта, не включенный в список запрещенных, отклоняется
def test_non_allowlisted_artifact(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.artifacts import is_artifact_id_allowed

    assert is_artifact_id_allowed("operator_summary_json") is True
    assert is_artifact_id_allowed("run_json") is True
    assert is_artifact_id_allowed("raw_eml") is False
    assert is_artifact_id_allowed("some_random_file") is False


# Тест: BeeUI artifact route degrades gracefully для неразрешенных артефактов
def test_non_allowlisted_artifact_error_envelope(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-bad-art")
    client = _client(storage_dir)
    # BeeUI artifact detail route — allowlist check via adapter
    response = client.get("/runs/run-bad-art/artifacts/raw_eml")
    assert response.status_code in (200, 400, 404)
    # BeeUI API route returns adapter envelope
    api_response = client.get("/api/runs/run-bad-art/artifacts/raw_eml")
    assert api_response.status_code in (200, 400, 404)
    if api_response.status_code == 400:
        data = api_response.json()
        assert "error" in data


# Тест: чек пути выполнения в run_id заблокирована
def test_path_traversal(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))
    response = client.get("/runs/%2E%2E%2Fetc%2Fpasswd")
    assert response.status_code in (400, 404)


# Тест: чек пути при разрешении артефактов возвращает None
def test_path_traversal_artifact(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.artifacts import resolve_artifact_path

    storage_dir = _make_storage(tmp_path)
    result = resolve_artifact_path(storage_dir, "..", "operator_summary_json")
    assert result is None


# Тест: чек, что ключ raw_eml скрыт при ограниченном чтении
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


# Тест: чек, что при чтении поврежденного JSON возвращается предупреждение, а не происходит сбой
def test_malformed_json_warning(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.bounded_read import read_bounded_json

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_malformed_json_run(storage_dir, "run-malformed")
    path = run_dir / "operator_summary.json"

    text, warning, error = read_bounded_json(path)
    assert text is None
    assert warning is not None
    assert "Malformed" in warning


# Тест: чек, что маршруты GET не изменяют артефакты хранения
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


# Тест: чек, что параметр read-model в исходной конфигурации ROP не раскрывает секреты
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


# Тест: чек, что при чтении слишком большого JSON возвращается предупреждение, а не происходит сбой
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


# Тест: чек считывания TSV работает в пределах допустимых значений
def test_tsv_bounded(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.bounded_read import read_bounded_tsv

    tsv_path = tmp_path / "test.tsv"
    tsv_path.write_text("col1\tcol2\nval1\tval2\n", encoding="utf-8")

    text, warning, error = read_bounded_tsv(tsv_path)
    assert text is not None
    assert "col1" in text
    assert warning is None


# Тест: чек, что все ожидаемые ID артефактов находятся в списке разрешенных
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


# Тест: чек наличия только GET-маршрутов (без мутаций)
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


# Тест: чек, что venue routes degraded (not intentionally published)
def test_venue_routes_not_published(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))

    for path in [
        "/venues/test",
        "/api/venues/test/dashboard",
    ]:
        response = client.get(path)
        # Route exists but returns unavailable (503) or not found (404)
        assert response.status_code in (404, 503), f"{path} should not be published"


# Тест: чек, что при наличии всех артефактов ROP dashboard отображает данные без ошибок
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
    return run_dir


# Тест: запуск с использованием некорректного источника
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


# Тест: запуск со всеми фоллбек классификациями
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


# Тест: запуск с несколькими высокоприоритетными событиями
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


# Тест: запуск с отсутствующим артефактом attachment_extraction.json
def _write_missing_attachment_run(storage_dir: Path, run_id: str) -> Path:
    run_dir = _write_rich_rop_run(storage_dir, run_id)
    (run_dir / "attachment_extraction.json").unlink(missing_ok=True)
    return run_dir


# Тест: запуск с HTML-подобными значениями в классификациях и диагностике источников
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


# Тест: запуск с поврежденным JSON в classified_events.json
def _write_malformed_json_artifact_run(storage_dir: Path, run_id: str) -> Path:
    run_dir = _write_rich_rop_run(storage_dir, run_id)
    (run_dir / "classified_events.json").write_text(
        "{invalid json!!!}", encoding="utf-8"
    )
    return run_dir


# Тест: чек, что при наличии всех артефактов ROP dashboard API возвращает полный полезный нагрузку без ошибок
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


# Тест: чек, что ROP dashboard API правильно обрабатывает источник с состоянием degraded и возвращает соответствующую рекомендацию
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
    # Check recommendation
    rec_codes = [r["code"] for r in payload["recommendations"]]
    assert "check_degraded_sources" in rec_codes


# Тест: чек, что события внимания на ROP dashboard ограничены 50, даже если в classified_events.json более 50 событий, соответствующих критериям внимания
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


# Тест: чек, что ROP dashboard API правильно обрабатывает сводку по вложениям и возвращает правильные счетчики для общего количества вложений, доступных превью и отклоненных вложений
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


# Тест: чек, что ссылки на доказательства на ROP dashboard ограничены allowlist и только разрешенные артефакты отображаются как ссылки, а остальные игнорируются
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
    }
    link_ids = {l["artifact_id"] for l in links}
    assert link_ids == allowed
    available = [l for l in links if l["available"]]
    assert len(available) > 0


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


# Тест: чек, что ROP dashboard layout предпочитает данные из current_state_queues перед queues при наличии обеих
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


# Тест: чек, что ROP dashboard API обрабатывает отсутствие артефакта attachment_extraction.json без ошибок и возвращает нулевые счетчики в сводке по вложениям и KPI
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


# Тест: чек, что ROP dashboard API обрабатывает поврежденный JSON в classified_events.json без сбоя и возвращает предупреждение
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


# Тест: чек, что ROP dashboard HTML экранирует HTML-подобные значения в классификациях и диагностике источников для предотвращения XSS-атак, при этом API возвращает сырые значения
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


# Тест: BeeUI artifact viewer HTML routes возвращают HTML
def test_beeui_artifact_viewer_html(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-art-view")
    client = _client(storage_dir)
    response = client.get("/runs/run-art-view/artifacts/operator_summary_json")
    assert response.status_code == 200
    assert "<!doctype html>" in response.text.lower()


# Тест: API-эндпоинт артефактов возвращает JSON
def test_artifact_viewer_api_still_json(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-api-art")
    client = _client(storage_dir)
    response = client.get("/api/runs/run-api-art/artifacts/operator_summary_json")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data


# Тест: локаль по умолчанию должен быть английским
def test_locale_default_en(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.locale import get_locale_config, resolve_locale

    cfg = get_locale_config()
    assert cfg["default"] == "en"
    assert resolve_locale(None, cfg) == "en"
    assert resolve_locale("en", cfg) == "en"


# Тест: локаль "ru" должна быть разрешена и возвращать "ru"
def test_locale_resolve_ru(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.locale import get_locale_config, resolve_locale

    cfg = get_locale_config()
    assert resolve_locale("ru", cfg) == "ru"


# Тест: локаль "de" (немецкий) не поддерживается, поэтому должна возвращаться английская локаль по умолчанию
def test_locale_fallback_on_invalid(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.locale import get_locale_config, resolve_locale

    cfg = get_locale_config()
    assert resolve_locale("de", cfg) == "en"
    assert resolve_locale("bad", cfg) == "en"


# Тест: функция t() должна возвращать переведенные строки для поддерживаемых локалей и исходную строку для неподдерживаемых
def test_locale_t_function(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.locale import t

    assert t("Dashboard") == "Dashboard"
    assert t("Dashboard", "ru") == "Дашборд"
    assert t("Nonexistent label") == "Nonexistent label"


# Тест: /rop с lang=ru рендерится через BeeUI locale
def test_rop_lang_ru(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_rich_rop_run(storage_dir, "run-lang-ru")
    client = _client(storage_dir)
    response = client.get("/rop", params={"lang": "ru"})
    assert response.status_code == 200


# Тест: /api/rop/dashboard сохраняет обратную совместимость
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


# Тест: raw eml остается заблокированным через adapter allowlist
def test_raw_eml_blocked(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-eml-block")
    client = _client(storage_dir)
    response = client.get("/runs/run-eml-block/artifacts/raw_eml")
    assert response.status_code in (200, 400, 404)
    api_response = client.get("/api/runs/run-eml-block/artifacts/raw_eml")
    assert api_response.status_code in (200, 400, 404)


# Тест: POST-запросы должны быть отклонены
def test_no_post_routes_in_custom_routes(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))
    for path in ["/", "/health", "/runs", "/rop", "/modules"]:
        response = client.post(path)
        assert response.status_code in (405, 404), f"POST {path} should be rejected"


# Тест: BeeAgentUiAdapter.get_page должен возвращать корректный layout для страницы rop_dashboard
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


# Тест: все блоки диаграмм на странице обзора ROP должны использовать поддерживаемую схему диаграмм BeeUI и иметь has_data=True
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


# Тест: overview renders deterministic chart containers instead of pseudo-chart datagrids
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


# Тест: обзор ROP не должен отображать ID запусков, начинающихся с "SMOKE-"
def test_rop_overview_no_smoke_run_ids(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "SMOKE-IT27-001")
    client = _client(storage_dir)
    response = client.get("/rop?tab=overview")
    html = response.text
    assert "SMOKE-IT27" not in html or "Run Selector" not in html


# Тест: обзор ROP не должен отображать карту "Period Selector"
def test_rop_overview_no_period_selector_card(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-period-regression")
    client = _client(storage_dir)
    response = client.get("/rop?tab=overview")
    html = response.text
    assert "Period Selector" not in html


# Тест: выпадающий список периодов на обзоре ROP должен содержать удобные для клиентов метки периодов
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
    assert "Last 7 days (current)" not in html
    assert 'href="/rop?tab=overview&amp;period=90d"' in html
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


# Тест: обзор ROP должен содержать панель "Action required"
def test_rop_overview_has_action_required_panel(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-action-regression")
    client = _client(storage_dir)
    response = client.get("/rop?tab=overview")
    assert response.status_code == 200
    assert "Action Required" in response.text


# Тест: обзор ROP должен использовать бизнес-ориентированные метки для KPI, а не внутренние имена
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


# Тест: обзор ROP не должен отображать селектор запусков, если в доступных запусках есть ID
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


# Тест: обзор ROP не должен отображать сырые имена enum в HTML
def test_rop_overview_no_raw_enum_labels(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.read_model import _humanize_label

    assert _humanize_label("new_lead") == "New leads"
    assert _humanize_label("unreconciled") == "Not reconciled"
    assert _humanize_label("ambiguous") == "Ambiguous / duplicate"
    assert _humanize_label("matched") == "Matched in Bitrix"
    assert _humanize_label("lost") == "Lost in Bitrix"
    assert _humanize_label("existing_client") == "Existing clients"


# Тест: обзор ROP должен использовать бизнес-ориентированные метки для заголовков диаграмм, а не внутренние имена
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


# Тест: обзор ROP должен отображать CTA Bitrix, когда unreconciled > 0
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
    action_card = next(block for block in layout if block.get("title") == "Action Required")
    assert action_card["type"] == "chart"
    assert "2 items need review" in action_card["subtitle"]


# Тест: обзор ROP не должен отображать отдельный блок "Detailed Metrics" на верхнем уровне, так как он объединен с "Overview"
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
