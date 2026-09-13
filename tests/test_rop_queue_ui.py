from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs
from urllib.parse import urlparse
import pytest
from beeagent_module.interfaces.ui.read_model import build_rop_page_layout

from tests.beeui_console_support import (
    _client,
    _make_storage,
    _write_rop_event_detail_artifacts,
    _write_rop_web_projection,
    _write_run_artifacts,
)


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


def test_processed_emails_are_distinct_from_deduplicated_queue_rows() -> None:
    from beeagent_module.interfaces.ui.read_model import _canonical_queue_rows

    queues = {
        "high_priority": [{"event_id": "evt-1"}],
        "needs_review": [
            {"event_id": "evt-1"},
            {"event_id": "evt-2"},
            {"event_id": "evt-3"},
            {"event_id": "evt-4"},
            {"event_id": "evt-5"},
        ],
        "lost_in_bitrix": [{"event_id": "evt-6"}],
    }

    processed_emails = 20
    actionable_rows = _canonical_queue_rows(queues, [], {})

    assert len(actionable_rows) == 6
    assert processed_emails != len(actionable_rows)


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
    filter_fields = layout[0]["toolbar"]["fields"]
    attachment_filter = next(
        field for field in filter_fields if field.get("name") == "has_attachments"
    )
    assert attachment_filter["choices"] == [
        {
            "value": "",
            "label": "All",
            "checked": True,
            "toggle_href": "/rop?tab=queue",
        },
        {
            "value": "true",
            "label": "With attachments",
            "checked": False,
            "toggle_href": "/rop?tab=queue&has_attachments=true",
        },
        {
            "value": "false",
            "label": "Without attachments",
            "checked": False,
            "toggle_href": "/rop?tab=queue&has_attachments=false",
        },
    ]
    assert layout[0]["type"] == "data_table"
    assert "toolbar" in layout[0]
    field_types = {f.get("type") for f in layout[0]["toolbar"].get("fields", [])}
    assert "checkboxes" in field_types
    assert len(layout[0]["rows"]) == 3


def test_bitrix_status_labels_are_translated_for_russian_locale() -> None:
    from beeagent_module.interfaces.ui.read_model import _bitrix_status_label

    assert _bitrix_status_label("matched_lead", "ru") == "Найдено в Bitrix"
    assert (
        _bitrix_status_label("identity_only_no_target", "ru")
        == "Контакт без лида/сделки"
    )
    assert _bitrix_status_label("unreconciled", "ru") == "Сверка не выполнена"


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
    for tab in ("overview", "sources"):
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


def test_attachment_queue_filter_is_accepted_and_filters_rows(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_run_artifacts(storage_dir, "run-attachments-queue")
    normalized = json.loads(
        (run_dir / "normalized_events.json").read_text(encoding="utf-8")
    )
    normalized[0].update(
        {
            "source_id": "hotline_mailbox",
            "attachments": [{"filename": "quote.pdf"}],
        }
    )
    classified = json.loads(
        (run_dir / "classified_events.json").read_text(encoding="utf-8")
    )
    classified[0]["source_id"] = "hotline_mailbox"
    (run_dir / "normalized_events.json").write_text(
        json.dumps(normalized), encoding="utf-8"
    )
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified), encoding="utf-8"
    )
    _write_rop_web_projection(storage_dir)
    client = _client(storage_dir)

    response = client.get(
        "/api/rop/dashboard?tab=queue&run_id=run-attachments-queue&has_attachments=true"
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["pagination"]["total_items"] == 1
    assert payload["queue_rows"][0]["has_attachments"] is True


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
