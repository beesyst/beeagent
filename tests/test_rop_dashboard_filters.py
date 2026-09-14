from __future__ import annotations

import json
import logging
import os
from functools import partial
from pathlib import Path
from typing import Any

import pytest

from beeagent_module.cases import rop_dashboard as rop_dashboard_module
from beeagent_module.cases.rop_dashboard import (
    build_rop_dashboard as _build_rop_dashboard,
)
from tests.rop_dashboard_test_support import seed_rop_dashboard_run

TEST_PLAN_LEAD = 20

build_rop_dashboard = partial(_build_rop_dashboard, plan_lead=TEST_PLAN_LEAD)

os.environ.setdefault("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
os.environ.setdefault("BEEAGENT_WEB_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("BEEAGENT_WEB_ROP_TOKEN", "test-rop-token")


@pytest.fixture(autouse=True)
def _set_openai_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_rop_dashboard")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    return seed_rop_dashboard_run(tmp_path)


class TestQueueFilters:
    def test_validate_filter_params_accepts_empty(self) -> None:
        errors = rop_dashboard_module.validate_filter_params({})
        assert errors == []

    def test_validate_filter_params_accepts_valid(self) -> None:
        errors = rop_dashboard_module.validate_filter_params(
            {
                "date_from": "2026-06-01",
                "date_to": "2026-06-30",
                "sender": "test@example.com",
                "subject": "test",
                "classification": "new_lead",
                "priority": "high",
                "bitrix_status": "not_found",
            }
        )
        assert errors == []

    def test_validate_filter_params_accepts_identity_only_status(self) -> None:
        errors = rop_dashboard_module.validate_filter_params(
            {"bitrix_status": "identity_only_no_target"}
        )
        assert errors == []

    def test_identity_only_status_is_not_counted_as_unreconciled(self) -> None:
        state = rop_dashboard_module._build_bitrix_period_state(
            [{"event_id": "evt-1", "source_id": "source-1"}],
            {
                "items": [
                    {
                        "event_id": "evt-1",
                        "source_id": "source-1",
                        "bitrix_match_status": "identity_only_no_target",
                    }
                ]
            },
            "run-1",
        )

        assert state["kpi"]["identity_only_no_target"] == 1
        assert state["kpi"]["unreconciled"] == 0
        assert [
            item["event_id"] for item in state["queues"]["identity_only_no_target"]
        ] == ["evt-1"]

    def test_confirmed_bitrix_delivery_overrides_not_found_status(self) -> None:
        state = rop_dashboard_module._build_bitrix_period_state(
            [{"event_id": "evt-1", "source_id": "source-1"}],
            {
                "items": [
                    {
                        "event_id": "evt-1",
                        "source_id": "source-1",
                        "bitrix_match_status": "not_found",
                    }
                ]
            },
            "run-1",
            confirmed_delivery_events={("run-1", "source-1", "evt-1")},
        )

        assert state["kpi"]["matched_in_bitrix"] == 1
        assert state["kpi"]["lost_in_bitrix"] == 0
        assert state["queues"]["matched"][0]["bitrix_status"] == "matched_lead"

    def test_dashboard_uses_confirmed_bitrix_delivery_for_status(
        self, run_dir: Path
    ) -> None:
        storage_dir = run_dir.parents[1]
        interfaces_dir = storage_dir / "interfaces"
        interfaces_dir.mkdir()
        (interfaces_dir / "rop_writeback_state.json").write_text(
            json.dumps(
                {
                    "events": {
                        "welding|rop_batch_sample|evt-002": {
                            "last_run_id": "test-dashboard-run",
                            "source_id": "rop_batch_sample",
                            "event_id": "evt-002",
                            "email_attachment_status": "attached",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        dashboard = build_rop_dashboard(storage_dir, "all", _null_logger())

        assert dashboard["business_kpi"]["matched_in_bitrix"] == 2
        assert dashboard["business_kpi"]["lost_in_bitrix"] == 0
        assert dashboard["queues"]["matched"][1]["event_id"] == "evt-002"

    @pytest.mark.parametrize(
        ("status", "attachment_status"),
        [
            ("created", "not_required"),
            ("created", "failed"),
            ("recovered", "pending"),
        ],
    )
    def test_confirmed_create_lead_overrides_not_found(
        self,
        status: str,
        attachment_status: str,
    ) -> None:
        writeback_state = {
            "events": {
                "welding|source-1|evt-1": {
                    "last_run_id": "run-1",
                    "source_id": "source-1",
                    "event_id": "evt-1",
                    "outcome": "create_lead",
                    "status": status,
                    "remote_entity_id": 123,
                    "email_attachment_status": attachment_status,
                }
            }
        }
        confirmed = rop_dashboard_module._confirmed_bitrix_delivery_events(
            writeback_state
        )
        state = rop_dashboard_module._build_bitrix_period_state(
            [{"event_id": "evt-1", "source_id": "source-1"}],
            {
                "items": [
                    {
                        "event_id": "evt-1",
                        "source_id": "source-1",
                        "bitrix_match_status": "not_found",
                    }
                ]
            },
            "run-1",
            confirmed_delivery_events=confirmed,
        )

        assert state["kpi"]["matched_in_bitrix"] == 1
        assert state["kpi"]["lost_in_bitrix"] == 0
        assert state["queues"]["matched"][0]["bitrix_status"] == "matched_lead"

    @pytest.mark.parametrize(
        ("status", "remote_entity_id"),
        [
            ("planned", 123),
            ("pending", 123),
            ("created", 0),
            ("recovered", -1),
            ("created", "123"),
            ("recovered", True),
        ],
    )
    def test_unconfirmed_create_lead_does_not_override_not_found(
        self,
        status: str,
        remote_entity_id: Any,
    ) -> None:
        confirmed = rop_dashboard_module._confirmed_bitrix_delivery_events(
            {
                "events": {
                    "welding|source-1|evt-1": {
                        "last_run_id": "run-1",
                        "source_id": "source-1",
                        "event_id": "evt-1",
                        "outcome": "create_lead",
                        "status": status,
                        "remote_entity_id": remote_entity_id,
                        "email_attachment_status": "attached",
                    }
                }
            }
        )
        state = rop_dashboard_module._build_bitrix_period_state(
            [{"event_id": "evt-1", "source_id": "source-1"}],
            {
                "items": [
                    {
                        "event_id": "evt-1",
                        "source_id": "source-1",
                        "bitrix_match_status": "not_found",
                    }
                ]
            },
            "run-1",
            confirmed_delivery_events=confirmed,
        )

        assert state["kpi"]["matched_in_bitrix"] == 0
        assert state["kpi"]["lost_in_bitrix"] == 1

    def test_validate_filter_params_accepts_duplicate_aliases(self) -> None:
        errors = rop_dashboard_module.validate_filter_params(
            {"classification": "duplicate", "case_type": "duplicate"}
        )

        assert errors == []

    @pytest.mark.parametrize(
        ("params", "message"),
        [
            ({"date_from": "not-a-date"}, "Invalid date_from"),
            ({"classification": "non_existent_type"}, "Invalid classification"),
            ({"priority": "urgent"}, "Invalid priority"),
            ({"bitrix_status": "non_existent"}, "Invalid bitrix_status"),
            ({"is_fallback": "maybe"}, "Invalid is_fallback"),
        ],
    )
    def test_validate_filter_params_rejects_invalid_values(
        self,
        params: dict[str, str],
        message: str,
    ) -> None:
        errors = rop_dashboard_module.validate_filter_params(params)
        assert any(message in error for error in errors)

    def test_validate_filter_params_rejects_date_from_after_to(self) -> None:
        errors = rop_dashboard_module.validate_filter_params(
            {"date_from": "2026-06-30", "date_to": "2026-06-01"}
        )
        assert any("date_from must not be after date_to" in e for e in errors)

    def test_validate_filter_params_accepts_is_fallback(self) -> None:
        errors = rop_dashboard_module.validate_filter_params({"is_fallback": "true"})
        assert errors == []
        errors = rop_dashboard_module.validate_filter_params({"is_fallback": "false"})
        assert errors == []

    def test_validate_filter_params_accepts_has_attachments(self) -> None:
        errors = rop_dashboard_module.validate_filter_params(
            {"has_attachments": "true"}
        )
        assert errors == []

    def test_apply_queue_filters_classification(self) -> None:
        events = [
            {"event_id": "1", "case_type": "new_lead", "sender": "a@b.com"},
            {"event_id": "2", "case_type": "existing_deal", "sender": "c@d.com"},
            {"event_id": "3", "case_type": "irrelevant", "sender": "e@f.com"},
        ]
        result = rop_dashboard_module.apply_queue_filters(
            events, {}, {"classification": "new_lead"}
        )
        assert len(result) == 1
        assert result[0]["event_id"] == "1"

    def test_apply_queue_filters_priority(self) -> None:
        events = [
            {"event_id": "1", "priority": "high", "case_type": "new_lead"},
            {"event_id": "2", "priority": "medium", "case_type": "new_lead"},
            {"event_id": "3", "priority": "low", "case_type": "new_lead"},
        ]
        result = rop_dashboard_module.apply_queue_filters(
            events, {}, {"priority": "high"}
        )
        assert len(result) == 1
        assert result[0]["event_id"] == "1"

    def test_apply_queue_filters_sender_substring_case_insensitive(self) -> None:
        events = [
            {"event_id": "1", "sender": "Alice@Example.com"},
            {"event_id": "2", "sender": "Bob@Test.com"},
        ]
        result = rop_dashboard_module.apply_queue_filters(
            events, {}, {"sender": "alice"}
        )
        assert len(result) == 1
        assert result[0]["event_id"] == "1"

    def test_apply_queue_filters_subject_substring(self) -> None:
        events = [
            {"event_id": "1", "subject": "Invoice for March"},
            {"event_id": "2", "subject": "Welcome letter"},
        ]
        result = rop_dashboard_module.apply_queue_filters(
            events, {}, {"subject": "invoice"}
        )
        assert len(result) == 1
        assert result[0]["event_id"] == "1"

    def test_apply_queue_filters_bitrix_status(self) -> None:
        events = [
            {"event_id": "1", "sender": "a@b.com"},
            {"event_id": "2", "sender": "c@d.com"},
            {"event_id": "3", "sender": "e@f.com"},
        ]
        bitrix_status_by_event = {
            "1": "matched",
            "2": "not_found",
            "3": "matched",
        }
        result = rop_dashboard_module.apply_queue_filters(
            events, bitrix_status_by_event, {"bitrix_status": "not_found"}
        )
        assert len(result) == 1
        assert result[0]["event_id"] == "2"

    def test_apply_queue_filters_is_fallback(self) -> None:
        events = [
            {"event_id": "1", "is_fallback": True},
            {"event_id": "2", "is_fallback": False},
            {"event_id": "3", "is_fallback": True},
            {"event_id": "4"},
        ]
        result = rop_dashboard_module.apply_queue_filters(
            events, None, {"is_fallback": "true"}
        )
        assert len(result) == 2
        assert {r["event_id"] for r in result} == {"1", "3"}

        result = rop_dashboard_module.apply_queue_filters(
            events, None, {"is_fallback": "false"}
        )
        assert len(result) == 2
        assert {r["event_id"] for r in result} == {"2", "4"}

    def test_apply_queue_filters_has_attachments(self) -> None:
        events = [
            {"event_id": "1", "has_attachments": True},
            {"event_id": "2", "has_attachments": False},
            {"event_id": "3"},
        ]
        result = rop_dashboard_module.apply_queue_filters(
            events, None, {"has_attachments": "true"}
        )

        assert [row["event_id"] for row in result] == ["1"]

        result = rop_dashboard_module.apply_queue_filters(
            events, None, {"has_attachments": "false"}
        )

        assert [row["event_id"] for row in result] == ["2", "3"]

    def test_apply_queue_filters_date_range(self) -> None:
        events = [
            {
                "event_id": "1",
                "event_date": "2026-06-15T10:00:00Z",
            },
            {
                "event_id": "2",
                "event_date": "2026-06-25T10:00:00Z",
            },
            {
                "event_id": "3",
                "event_date": "2026-07-05T10:00:00Z",
            },
        ]
        result = rop_dashboard_module.apply_queue_filters(
            events,
            {},
            {"date_from": "2026-06-01", "date_to": "2026-06-20"},
        )
        assert len(result) == 1
        assert result[0]["event_id"] == "1"

    def test_apply_queue_filters_combined_and(self) -> None:
        events = [
            {
                "event_id": "1",
                "sender": "lead@example.com",
                "case_type": "new_lead",
                "priority": "high",
            },
            {
                "event_id": "2",
                "sender": "lead@example.com",
                "case_type": "existing_deal",
                "priority": "high",
            },
            {
                "event_id": "3",
                "sender": "other@example.com",
                "case_type": "new_lead",
                "priority": "high",
            },
        ]
        result = rop_dashboard_module.apply_queue_filters(
            events,
            {},
            {
                "sender": "lead",
                "classification": "new_lead",
                "priority": "high",
            },
        )
        assert len(result) == 1
        assert result[0]["event_id"] == "1"

    def test_apply_queue_filters_no_mutation(self) -> None:
        original = [
            {"event_id": "1", "case_type": "new_lead"},
            {"event_id": "2", "case_type": "existing_deal"},
        ]
        original_copy = list(original)
        rop_dashboard_module.apply_queue_filters(
            original, {}, {"classification": "new_lead"}
        )
        assert original == original_copy

    def test_apply_queue_filters_no_params_returns_all(self) -> None:
        events = [
            {"event_id": "1", "case_type": "new_lead"},
            {"event_id": "2", "case_type": "existing_deal"},
        ]
        result = rop_dashboard_module.apply_queue_filters(events, {}, {})
        assert len(result) == 2

    def test_apply_queue_filters_date_only_from(self) -> None:
        events = [
            {
                "event_id": "1",
                "event_date": "2026-06-15T10:00:00Z",
            },
            {
                "event_id": "2",
                "event_date": "2026-07-25T10:00:00Z",
            },
        ]
        result = rop_dashboard_module.apply_queue_filters(
            events, {}, {"date_from": "2026-07-01"}
        )
        assert len(result) == 1
        assert result[0]["event_id"] == "2"

    def test_apply_queue_filters_date_only_to(self) -> None:
        events = [
            {
                "event_id": "1",
                "event_date": "2026-06-15T10:00:00Z",
            },
            {
                "event_id": "2",
                "event_date": "2026-07-25T10:00:00Z",
            },
        ]
        result = rop_dashboard_module.apply_queue_filters(
            events, {}, {"date_to": "2026-06-30"}
        )
        assert len(result) == 1
        assert result[0]["event_id"] == "1"

    def test_apply_queue_filters_date_equal_range(self) -> None:
        events = [
            {
                "event_id": "1",
                "event_date": "2026-06-15T10:00:00Z",
            },
            {
                "event_id": "2",
                "event_date": "2026-06-25T10:00:00Z",
            },
        ]
        result = rop_dashboard_module.apply_queue_filters(
            events,
            {},
            {"date_from": "2026-06-15", "date_to": "2026-06-15"},
        )
        assert len(result) == 1
        assert result[0]["event_id"] == "1"

    def test_descending_text_sort_handles_unicode_prefixes_and_missing_values(
        self,
    ) -> None:
        items = [
            {"event_id": "prefix", "sender": "Анна"},
            {"event_id": "longer", "sender": "Анна Б"},
            {"event_id": "latin", "sender": "zebra"},
            {"event_id": "missing", "sender": ""},
        ]

        sorted_items = rop_dashboard_module.sort_queue_items(
            items, sort="sender", order="desc"
        )

        assert [item["event_id"] for item in sorted_items] == [
            "longer",
            "prefix",
            "latin",
            "missing",
        ]

    def test_missing_and_malformed_dates_are_last_for_both_orders(self) -> None:
        items = [
            {"event_id": "early", "received_at": "2026-06-01T00:00:00Z"},
            {"event_id": "malformed", "received_at": "not-a-date"},
            {"event_id": "late", "received_at": "2026-06-15T00:00:00Z"},
            {"event_id": "missing", "received_at": ""},
        ]

        assert [
            item["event_id"]
            for item in rop_dashboard_module.sort_queue_items(
                items, sort="received_at", order="asc"
            )
        ] == ["early", "late", "malformed", "missing"]
        assert [
            item["event_id"]
            for item in rop_dashboard_module.sort_queue_items(
                items, sort="received_at", order="desc"
            )
        ] == ["late", "early", "malformed", "missing"]
