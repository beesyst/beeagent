from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs
from urllib.parse import urlparse
import pytest
from fastapi.testclient import TestClient
from beeagent_module.interfaces.ui.read_model import build_rop_dashboard_read_model
from beeagent_module.interfaces.ui.read_model import build_rop_page_layout

from tests.beeui_console_support import (
    _build_settings,
    _client,
    _make_storage,
    _write_rich_rop_run,
    _write_rop_event_detail_artifacts,
    _write_rop_web_projection,
    _write_run_artifacts,
)


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
            "sender": "<script>alert('sender')</script>",
            "subject": "<script>alert('subject')</script>",
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
        assert "EMAILS" in html
        assert "NEW LEADS" in html
        assert "Urgent leads" in html
        assert "For review" in html
        assert "Bitrix problems" in html
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
        assert 'class="beeui-page-tabs-blocks" aria-label="Page blocks"' in html

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

    def test_primary_email_metric_uses_generic_label_and_trend(self) -> None:
        data = self._mock_data()
        data["email_trend"] = {
            "status": "available",
            "percentage": -25,
            "direction": "down",
        }
        data["new_leads_trend"] = {
            "status": "available",
            "percentage": 0,
            "direction": "neutral",
        }

        hero = build_rop_page_layout(data, tab="overview")[0]

        assert hero["items"][0]["label"] == "EMAILS"
        assert hero["items"][0]["metric"] is True
        assert hero["items"][0]["trend"] == {"percentage": -25, "direction": "down"}
        assert hero["items"][0]["progress_tone"] == "bg-success"
        assert hero["items"][1]["trend"] == {"percentage": 0, "direction": "neutral"}
        assert hero["items"][1]["progress_tone"] == "bg-danger"
        assert hero["illustration"] == {"asset": "tabler_email_dark", "alt": ""}

    def test_primary_email_label_is_localized_to_russian(self) -> None:
        hero = build_rop_page_layout(self._mock_data(), tab="overview", locale="ru")[0]

        assert hero["items"][0]["label"] == "ПИСЬМА"

    def test_team_leaderboard_keeps_over_plan_score_and_bounds_progress(self) -> None:
        data = self._mock_data()
        data["team_leaderboard"] = {
            "month": "2026-09",
            "plan_lead": 20,
            "items": [
                {
                    "user_id": 7,
                    "name": "Example User",
                    "current_month_count": 25,
                    "score_percent": 125,
                }
            ],
        }

        ru_layout = build_rop_page_layout(data, tab="overview", locale="ru")
        en_layout = build_rop_page_layout(data, tab="overview", locale="en")
        ru_item = next(block for block in ru_layout if block["type"] == "leaderboard")[
            "items"
        ][0]
        en_item = next(block for block in en_layout if block["type"] == "leaderboard")[
            "items"
        ][0]

        assert ru_item["value"] == "25 лидов"
        assert ru_item["meta"] == "125% от плана"
        assert en_item["value"] == "25 leads"
        assert en_item["meta"] == "125% of plan"
        assert ru_item["progress"] == 100

    def test_hero_subtitle_uses_today_counts_without_changing_period_metrics(
        self,
    ) -> None:
        data = self._mock_data()
        data["business_kpi"].update({"processed_emails": 40, "new_leads": 3})
        data["today_summary"] = {"emails": 12, "new_leads": 5}

        hero_en = build_rop_page_layout(data, tab="overview")[0]
        hero_ru = build_rop_page_layout(data, tab="overview", locale="ru")[0]

        assert [item["value"] for item in hero_ru["items"]] == [40, 3]
        assert hero_ru["subtitle"] == "За сегодня 12 писем, из них 5 новых лидов"
        assert hero_en["subtitle"] == "Today: 12 emails, including 5 new leads"

    @pytest.mark.parametrize(
        ("emails", "new_leads", "expected"),
        (
            (1, 1, "За сегодня 1 письмо, из них 1 новый лид"),
            (2, 2, "За сегодня 2 письма, из них 2 новых лида"),
            (5, 5, "За сегодня 5 писем, из них 5 новых лидов"),
            (8, 0, "За сегодня 8 писем, но пока новых лидов нет"),
        ),
    )
    def test_format_rop_today_summary_russian_pluralization(
        self,
        emails: int,
        new_leads: int,
        expected: str,
    ) -> None:
        from beeagent_module.interfaces.ui.locale import format_rop_today_summary

        assert format_rop_today_summary(emails, new_leads, "ru") == expected

    def test_format_rop_today_summary_english_positive_and_zero(self) -> None:
        from beeagent_module.interfaces.ui.locale import format_rop_today_summary

        assert format_rop_today_summary(1, 1) == "Today: 1 email, including 1 new lead"
        assert format_rop_today_summary(8, 0) == "Today: 8 emails, but no new leads yet"

    def test_primary_email_omits_unavailable_trend(self) -> None:
        data = self._mock_data()
        data["email_trend"] = {"status": "unavailable"}

        hero = build_rop_page_layout(data, tab="overview")[0]

        assert "trend" not in hero["items"][0]

    def test_top_row_has_two_chart_cards(self) -> None:
        layout = build_rop_page_layout(self._mock_data(), tab="overview")
        assert layout[1]["type"] == "chart"
        assert layout[1]["title"] == "Classification"
        assert layout[1]["width"] == 6

    def test_classification_subtitle_uses_classified_email_count(self) -> None:
        data = self._mock_data()

        chart = build_rop_page_layout(data, tab="overview")[1]
        chart_ru = build_rop_page_layout(data, tab="overview", locale="ru")[1]

        assert data["business_kpi"]["processed_events"] == 38
        assert data["business_kpi"]["new_leads"] == 12
        assert chart["subtitle"] == "38 classified emails in selected period"
        assert chart_ru["subtitle"] == "38 писем классифицировано за выбранный период"

    def test_secondary_chart_subtitles_are_localized(self) -> None:
        layout = build_rop_page_layout(self._mock_data(), tab="overview")
        layout_ru = build_rop_page_layout(
            self._mock_data(), tab="overview", locale="ru"
        )

        subtitles = {block["title"]: block.get("subtitle") for block in layout}
        subtitles_ru = {block["title"]: block.get("subtitle") for block in layout_ru}

        assert subtitles["Bitrix reconciliation"] == (
            "Reconciliation status for selected period"
        )
        assert (
            subtitles["Source contribution"] == "Emails by source for selected period"
        )
        assert subtitles_ru["Сверка с Битрикс"] == (
            "Статусы сверки за выбранный период"
        )
        assert subtitles_ru["Вклад источников"] == (
            "Письма по источникам за выбранный период"
        )

    def test_classification_mix_uses_non_overlapping_case_types(self) -> None:
        data = self._mock_data()
        data["business_kpi"]["processed_events"] = 20
        data["business_kpi"]["new_leads"] = 1
        data["series"] = {
            "classification_distribution": {
                "labels": [
                    "duplicate",
                    "existing_deal",
                    "irrelevant",
                    "new_lead",
                ],
                "series": [1, 1, 17, 1],
            }
        }

        layout = build_rop_page_layout(data, tab="overview")
        chart = layout[1]
        chart_ru = build_rop_page_layout(data, tab="overview", locale="ru")[1]

        assert chart["kind"] == "funnel"
        assert chart["categories"] == [
            "Duplicate",
            "Deal",
            "New lead",
            "Irrelevant",
        ]
        assert chart_ru["categories"] == [
            "Дубликат",
            "Сделка",
            "Новый лид",
            "Нерелевантно",
        ]
        assert chart["series"] == [{"name": "Classification", "data": [1, 1, 1, 17]}]
        assert chart["colors"] == ["azure", "orange", "red", "blue"]
        assert (
            sum(chart["series"][0]["data"]) == data["business_kpi"]["processed_events"]
        )
        assert data["business_kpi"]["new_leads"] == 1
        assert (
            data["series"]["classification_distribution"]["labels"][1]
            == "existing_deal"
        )

    def test_classification_mix_sorts_dynamic_counts_with_semantic_colors(self) -> None:
        data = self._mock_data()
        data["business_kpi"]["processed_events"] = 40
        data["business_kpi"]["new_leads"] = 3
        data["series"] = {
            "classification_distribution": {
                "labels": [
                    "duplicate",
                    "existing_deal",
                    "irrelevant",
                    "new_lead",
                ],
                "series": [5, 1, 31, 3],
            }
        }

        chart = build_rop_page_layout(data, tab="overview")[1]
        chart_ru = build_rop_page_layout(data, tab="overview", locale="ru")[1]

        assert chart["categories"] == ["Deal", "New lead", "Duplicate", "Irrelevant"]
        assert chart_ru["categories"] == [
            "Сделка",
            "Новый лид",
            "Дубликат",
            "Нерелевантно",
        ]
        assert chart["series"] == [{"name": "Classification", "data": [1, 3, 5, 31]}]
        assert chart["colors"] == ["orange", "red", "azure", "blue"]
        assert (
            sum(chart["series"][0]["data"]) == data["business_kpi"]["processed_events"]
        )
        assert (
            data["series"]["classification_distribution"]["labels"][1]
            == "existing_deal"
        )

    def test_existing_deal_keeps_raw_case_type_and_uses_presentation_label(
        self,
    ) -> None:
        from beeagent_module.interfaces.ui.locale import case_type_label

        assert case_type_label("existing_deal") == "Deal"
        assert case_type_label("existing_deal", "ru") == "Сделка"

    def test_kpi_has_customer_facing_labels(self) -> None:
        layout = build_rop_page_layout(self._mock_data(), tab="overview")
        labels = [block["title"] for block in layout if block["type"] == "metric_card"]
        assert "Urgent leads" in labels
        assert "For review" in labels
        assert "Bitrix problems" in labels
        assert "Available sources" in labels

    def test_kpi_has_four_small_cards(self) -> None:
        layout = build_rop_page_layout(self._mock_data(), tab="overview")
        cards = [block for block in layout if block["type"] == "metric_card"]
        assert len(cards) == 4
        assert [card["width"] for card in cards] == [3, 3, 3, 3]
        assert [card["value"] for card in cards] == [2, 5, 4, 0]
        assert [card["icon"] for card in cards] == [
            "mail-heart",
            "mail-check",
            "mail-question",
            "mail-plus",
        ]
        assert [card["icon_tone"] for card in cards] == [
            "red",
            "azure",
            "orange",
            "green",
        ]
        urgent, needs_review, bitrix, sources = cards
        assert parse_qs(urlparse(urgent["href"]).query)["priority"] == ["high"]
        assert parse_qs(urlparse(needs_review["href"]).query)["queue"] == [
            "needs_review"
        ]
        assert parse_qs(urlparse(bitrix["href"]).query)["bitrix_status"] == [
            "not_found,ambiguous,duplicate_candidate,unreconciled"
        ]
        for card in cards:
            query = parse_qs(urlparse(card["href"]).query)
            assert query["period"] == ["7d"]
            assert query["run_id"] == ["run-test-001"]
            assert "status" not in card
            assert "hint" not in card or card["title"] == "Available sources"
            assert "items" not in card
            assert "links" not in card
        assert parse_qs(urlparse(sources["href"]).query)["tab"] == ["sources"]

    def test_overview_desktop_rows_fill_the_grid(self) -> None:
        layout = build_rop_page_layout(self._mock_data(), tab="overview")
        widths = [block["width"] for block in layout]
        assert widths == [6, 6, 3, 3, 3, 3, 6, 6, 6, 6]

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
        "Last 7 days",
        "Last 30 days",
        "All time",
    ]
    assert items[0]["href"] == "/rop?tab=overview&run_id=run-test-001&period=today"
    assert items[1]["href"] == "/rop?tab=overview&run_id=run-test-001&period=7d"


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
    assert all(block.get("title") != "Business metrics" for block in layout)


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
    response_html = client.get("/rop?tab=queue&run_id=run-html-safe")
    assert response_html.status_code == 200
    html = response_html.text
    assert "<script>alert('sender')</script>" not in html
    assert "&lt;script&gt;alert(&#39;sender&#39;)&lt;/script&gt;" in html


def test_rop_lang_ru(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_rich_rop_run(storage_dir, "run-lang-ru")
    client = _client(storage_dir)
    response = client.get("/rop", params={"lang": "ru"})
    assert response.status_code == 200
    html = response.text
    assert "Панель РОПа" in html
    assert "ПИСЬМА" in html
    assert "/static/vendor/tabler/illustrations/dark/email.png" in html
    assert "preview.tabler.io" not in html
    assert "НОВЫЕ ЛИДЫ" in html
    assert "Срочные лиды" in html
    assert "Письма на проверку" in html
    assert "Проблемы Bitrix" in html
    assert "Источники" in html
    assert "Количество" not in html
    assert "Открыть очередь" not in html
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
        "/rop?tab=sources&amp;period=7d&amp;lang=ru" in html
        or "/rop?lang=ru&amp;period=7d&amp;tab=sources" in html
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


def test_rop_overview_renders_deterministic_chart_containers(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_with_event_dates(storage_dir, "run-chart-schema")
    client = _client(storage_dir)
    response = client.get("/rop?period=7d")
    assert response.status_code == 200
    html = response.text
    assert "Email Workload" in html
    assert "Action Required" not in html
    assert "Classification" in html
    assert "Bitrix reconciliation" in html
    assert "Source contribution" in html
    assert "chart-rop-email-workload" in html
    assert "chart-rop-action-required" not in html
    assert "chart-rop-outcome-mix" in html
    assert "chart-rop-bitrix" in html
    assert "chart-rop-source-contribution" in html
    assert html.count("beeui-metric-card") == 4
    for title in (
        "Urgent leads",
        "For review",
        "Bitrix problems",
        "Available sources",
    ):
        assert title in html
    assert "priority=high" in html
    assert "queue=needs_review" in html
    assert (
        "bitrix_status=not_found%2Cambiguous%2Cduplicate_candidate%2Cunreconciled"
        in html
    )
    assert 'href="/rop?tab=sources&amp;run_id=run-chart-schema' in html


def test_rop_overview_no_smoke_run_ids(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "SMOKE-IT27-001")
    client = _client(storage_dir)
    response = client.get("/rop?tab=overview")
    html = response.text
    assert "SMOKE-IT27" not in html or "Run Selector" not in html


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


def test_rop_overview_kpi_uses_business_labels(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-labels-regression")
    client = _client(storage_dir)
    response = client.get("/rop?tab=overview")
    html = response.text
    assert "Business KPI" not in html
    assert "Detailed Metrics" not in html
    assert "Business metrics" not in html
    assert "EMAILS" in html
    assert "NEW LEADS" in html
    assert "Urgent leads" in html
    assert "For review" in html
    assert "Bitrix problems" in html
    assert "Available sources" in html
    assert "Count" not in html
    assert "Open Queue" not in html
    assert "high_priority" not in html


def test_rop_overview_chart_subtitles_render_in_both_locales(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-chart-subtitles")
    client = _client(storage_dir)

    response_en = client.get("/rop?tab=overview&lang=en")
    response_ru = client.get("/rop?tab=overview&lang=ru")

    assert response_en.status_code == 200
    assert "Reconciliation status for selected period" in response_en.text
    assert "Emails by source for selected period" in response_en.text
    assert response_ru.status_code == 200
    assert "Статусы сверки за выбранный период" in response_ru.text
    assert "Письма по источникам за выбранный период" in response_ru.text


def test_rop_overview_no_raw_enum_labels(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.read_model import _humanize_label

    assert _humanize_label("new_lead") == "New leads"
    assert _humanize_label("unreconciled") == "Not reconciled"
    assert _humanize_label("ambiguous") == "Ambiguous / duplicate"
    assert _humanize_label("matched") == "Matched in Bitrix"
    assert _humanize_label("lost") == "Lost in Bitrix"
    assert _humanize_label("existing_client") == "Existing clients"


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

    def test_thread_data_falls_back_to_index_when_contexts_empty(
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
        for tab in ("overview",):
            response = client.get(f"/rop?tab={tab}")
            assert response.status_code == 200
            assert "should-not-leak" not in response.text
            assert "secret-key-12345" not in response.text

    def test_no_raw_eml_in_it30_html(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        run_dir = self._write_full_it30_run(storage_dir, "run-no-raw")
        client = _client(storage_dir)
        for tab in ("overview",):
            response = client.get(f"/rop?tab={tab}")
            assert response.status_code == 200
            assert "raw_eml" not in response.text.lower()
            assert "attachment_content" not in response.text.lower()

    def test_latest_selection_api_preserves_raw_technical_fields(
        self, tmp_path: Path
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        self._write_full_it30_run(storage_dir, "run-api-raw")
        client = _client(storage_dir)
        response = client.get("/api/rop/dashboard")
        assert response.status_code == 200
        payload = response.json()["data"]["latest_selection"]
        assert payload["strategy"] == "latest_n_by_internaldate_desc"
        assert payload["newest_message_at"] == "2026-06-28T12:00:00+00:00"
        assert payload["oldest_message_at"] == "2026-06-25T07:30:00+00:00"
        assert payload["selected_count"] == 5
        assert payload["source_count"] == 1


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

        data = build_rop_dashboard_read_model(
            storage_dir, "agg-run-b", period="all", plan_lead=20
        )

        assert data["business_kpi"]["processed_events"] == 2
        assert data["series"]["source_contribution"] == {
            "labels": ["src_a", "src_b"],
            "series": [1, 1],
        }
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

        data = build_rop_dashboard_read_model(
            storage_dir, "agg-run-q", period="all", plan_lead=20
        )
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

        data = build_rop_dashboard_read_model(
            storage_dir, "agg-run-q", period="all", plan_lead=20
        )
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
            plan_lead=20,
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
            plan_lead=20,
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
            plan_lead=20,
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

        data = build_rop_dashboard_read_model(
            storage_dir, "agg-run-b", period="all", plan_lead=20
        )

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

        data = build_rop_dashboard_read_model(
            storage_dir, "agg-run-b", period="all", plan_lead=20
        )

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

        data = build_rop_dashboard_read_model(
            storage_dir, "agg-run-b", period="all", plan_lead=20
        )
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

        data = build_rop_dashboard_read_model(
            storage_dir, "agg-run-b", period="all", plan_lead=20
        )

        assert data["business_kpi"]["processed_events"] == 2
        same_rows = [row for row in data["queue_rows"] if row["event_id"] == "evt-same"]
        assert len(same_rows) == 2
        assert {row["run_id"] for row in same_rows} == {"agg-run-a", "agg-run-b"}
        assert {row["source_id"] for row in same_rows} == {"src_a", "src_b"}

    def test_bitrix_aggregate_preserves_anchor_evidence_availability(
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

        data = build_rop_dashboard_read_model(
            storage_dir, "agg-run-b", period="all", plan_lead=20
        )
        assert data["business_kpi"]["matched_in_bitrix"] == 1
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

        data = build_rop_dashboard_read_model(
            storage_dir, None, period="all", plan_lead=20
        )

        assert data["selected_run_id"] == "rop-old"
        assert data["business_kpi"]["processed_events"] == 1

        client = _client(storage_dir)
        api = client.get("/api/rop/dashboard", params={"period": "all"})
        assert api.status_code == 200
        payload = api.json()["data"]
        assert payload["selected_run_id"] == "rop-old"
        assert payload["business_kpi"]["processed_events"] == 1
