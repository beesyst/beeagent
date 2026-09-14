from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any

import pytest

from beeagent_module.cases import rop_dashboard as rop_dashboard_module
from beeagent_module.cases.rop_dashboard import (
    ALLOWED_PERIODS,
    parse_period,
    validate_period,
    write_rop_dashboard,
)
from beeagent_module.cases.rop_dashboard import (
    build_rop_dashboard as _build_rop_dashboard,
)
from beeagent_module.core.settings import load_settings
from tests.rop_dashboard_test_support import seed_rop_dashboard_run

TEST_PLAN_LEAD = 20

build_rop_dashboard = partial(_build_rop_dashboard, plan_lead=TEST_PLAN_LEAD)

os.environ.setdefault("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
os.environ.setdefault("BEEAGENT_WEB_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("BEEAGENT_WEB_OPERATOR_TOKEN", "test-operator-token")
os.environ.setdefault("BEEAGENT_WEB_ROP_TOKEN", "test-rop-token")


@pytest.fixture(autouse=True)
def _set_openai_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_rop_dashboard")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_email_trend_uses_immediately_preceding_equal_window() -> None:
    period_info = {
        "period_start_utc": "2026-09-02T00:00:00+00:00",
        "period_end_utc": "2026-09-02T23:59:59.999999+00:00",
    }
    events = [
        {"event_date": "2026-09-01T06:00:00+00:00"},
        {"event_date": "2026-09-01T12:00:00+00:00"},
        {"event_date": "2026-09-02T06:00:00+00:00"},
        {"event_date": "2026-09-02T12:00:00+00:00"},
        {"event_date": "2026-09-02T18:00:00+00:00"},
    ]

    trend = rop_dashboard_module._build_email_trend(
        events,
        period_info,
        current_count=3,
        fallback_ts=None,
    )

    assert trend == {
        "status": "available",
        "percentage": 50,
        "direction": "up",
        "current_count": 3,
        "previous_count": 2,
    }


@pytest.mark.parametrize(
    ("current_count", "previous_count", "expected"),
    [
        (
            0,
            0,
            {
                "status": "available",
                "percentage": 0,
                "direction": "neutral",
                "current_count": 0,
                "previous_count": 0,
            },
        ),
        (
            2,
            0,
            {
                "status": "available",
                "percentage": 0,
                "direction": "neutral",
                "current_count": 2,
                "previous_count": 0,
            },
        ),
    ],
)
def test_email_trend_handles_zero_baseline(
    current_count: int, previous_count: int, expected: dict[str, Any]
) -> None:
    period_info = {
        "period_start_utc": "2026-09-02T00:00:00+00:00",
        "period_end_utc": "2026-09-02T23:59:59.999999+00:00",
    }
    events = [
        {"event_date": "2026-09-01T12:00:00+00:00"} for _ in range(previous_count)
    ]

    trend = rop_dashboard_module._build_email_trend(
        events,
        period_info,
        current_count=current_count,
        fallback_ts=None,
    )

    assert trend == expected


def test_email_trend_is_unavailable_for_all_time() -> None:
    assert rop_dashboard_module._build_email_trend(
        [],
        {"period_start_utc": None, "period_end_utc": None},
        current_count=0,
        fallback_ts=None,
    ) == {"status": "unavailable"}


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    return seed_rop_dashboard_run(tmp_path)


class TestPeriodParsing:
    def test_rop_dashboard_module_exports_builder_contract(self) -> None:
        for name in (
            "ALLOWED_PERIODS",
            "parse_period",
            "validate_period",
            "build_rop_dashboard",
            "write_rop_dashboard",
        ):
            assert hasattr(rop_dashboard_module, name)

        module_path = Path(rop_dashboard_module.__file__)
        source = module_path.read_text(encoding="utf-8")
        assert (
            "from beeagent_module.cases.rop_dashboard import build_rop_dashboard"
            not in source
        )
        assert "def _build_rop_bitrix_layout" not in source
        assert "def _queue_table" not in source

    def test_parse_period_accepts_all_allowed_periods(self) -> None:
        for period in ALLOWED_PERIODS:
            info = parse_period(period)
            assert info["period"] == period
            assert info["time_basis"] == "event_timestamp"

    def test_parse_period_distinguishes_bounded_and_all(self) -> None:
        bounded = parse_period("7d")
        unlimited = parse_period("all")

        assert bounded["period_start_utc"] is not None
        assert bounded["period_end_utc"] is not None
        assert unlimited["period_start_utc"] is None
        assert unlimited["period_end_utc"] is None

    def test_parse_invalid_period_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported period"):
            parse_period("invalid")
        with pytest.raises(ValueError, match="Unsupported period"):
            parse_period("1d")
        with pytest.raises(ValueError, match="Unsupported period"):
            parse_period("")

    def test_validate_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid period"):
            validate_period("1d")
        with pytest.raises(ValueError, match="Invalid period"):
            validate_period("")


class TestBuildRopDashboard:
    def test_dashboard_public_contract(self, run_dir: Path, tmp_path: Path) -> None:
        dashboard = build_rop_dashboard(tmp_path, "7d", _null_logger())

        assert dashboard["status"] == "ok"
        assert dashboard["read_only"] is True
        assert dashboard["period"] == "7d"
        assert dashboard["run_id"] == "test-dashboard-run"
        assert "generated_at_utc" in dashboard
        assert "warnings" in dashboard

        business_kpi = dashboard["business_kpi"]
        assert business_kpi["processed_events"] == 3
        assert business_kpi["new_leads"] == 2
        assert business_kpi["existing_clients"] == 1
        assert business_kpi["high_priority"] == 2
        assert business_kpi["needs_review"] == 1
        assert {
            "lost_in_bitrix",
            "unreconciled",
            "source_degraded",
            "attachment_refused",
        } <= set(business_kpi)

        assert {
            "processed_by_day",
            "classification_distribution",
            "bitrix_distribution",
            "source_contribution",
        } <= set(dashboard["series"])
        assert {
            "high_priority",
            "needs_review",
            "lost_in_bitrix",
            "unreconciled",
        } <= set(dashboard["queues"])
        assert len(dashboard["queues"]["high_priority"]) == 2

        recommendation_codes = {
            item["reason_code"] for item in dashboard["rop_recommendations"]
        }
        assert {
            "high_priority",
            "lost_in_bitrix",
            "attachment_refused",
        } <= recommendation_codes
        assert dashboard["evidence_links"]
        assert all(
            "artifact_id" in item and "href" in item
            for item in dashboard["evidence_links"]
        )

    def test_dashboard_with_no_bitrix(self, run_dir: Path, tmp_path: Path) -> None:
        (run_dir / "bitrix_reconciliation.json").unlink(missing_ok=True)
        (run_dir / "rop_current_state.json").unlink(missing_ok=True)

        dashboard = build_rop_dashboard(tmp_path, "7d", _null_logger())
        assert dashboard["status"] == "ok"
        bkpi = dashboard["business_kpi"]
        assert bkpi["processed_events"] == 3
        assert bkpi["lost_in_bitrix"] == 0
        assert bkpi["unreconciled"] == 3

    def test_dashboard_empty_run_dir(self, tmp_path: Path) -> None:
        dashboard = build_rop_dashboard(tmp_path, "7d", _null_logger())
        assert dashboard["status"] == "empty"

    def test_dashboard_with_specific_run_id(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        dashboard = build_rop_dashboard(
            tmp_path, "7d", _null_logger(), run_id="test-dashboard-run"
        )
        assert dashboard["run_id"] == "test-dashboard-run"
        assert dashboard["status"] == "ok"

    def test_dashboard_with_invalid_run_id(self, tmp_path: Path) -> None:
        dashboard = build_rop_dashboard(
            tmp_path, "7d", _null_logger(), run_id="../../etc/passwd"
        )
        assert dashboard["status"] == "empty"

    def test_dashboard_period_all_no_filtering(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        dashboard = build_rop_dashboard(tmp_path, "all", _null_logger())
        assert dashboard["period"] == "all"
        assert dashboard["business_kpi"]["processed_events"] == 3

    def test_dashboard_period_uses_run_generated_at_when_events_have_no_timestamp(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        for artifact_name in ("normalized_events.json", "classified_events.json"):
            artifact_path = run_dir / artifact_name
            events = json.loads(artifact_path.read_text(encoding="utf-8"))
            for event in events:
                event.pop("event_date", None)
            artifact_path.write_text(json.dumps(events), encoding="utf-8")

        current_state_path = run_dir / "rop_current_state.json"
        current_state = json.loads(current_state_path.read_text(encoding="utf-8"))
        current_state["generated_at_utc"] = (
            datetime.now(UTC).replace(microsecond=0).isoformat()
        )
        current_state_path.write_text(json.dumps(current_state), encoding="utf-8")

        dashboard = build_rop_dashboard(tmp_path, "7d", _null_logger())

        assert dashboard["business_kpi"]["processed_events"] == 3
        assert dashboard["time_basis"] == "run_generated_at"
        assert any(
            warning.get("code") == "time_basis_fallback"
            for warning in dashboard["warnings"]
        )

    def test_dashboard_bitrix_kpi_and_queues_are_period_scoped(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        old_ts = (
            (datetime.now(UTC) - timedelta(days=30)).replace(microsecond=0).isoformat()
        )
        for artifact_name in ("normalized_events.json", "classified_events.json"):
            artifact_path = run_dir / artifact_name
            events = json.loads(artifact_path.read_text(encoding="utf-8"))
            events.append(
                {
                    "event_id": "evt-old",
                    "source_id": "rop_batch_sample",
                    "sender": "old@example.com",
                    "subject": "Old event",
                    "case_type": "new_lead",
                    "priority": "high",
                    "is_fallback": False,
                    "event_date": old_ts,
                }
            )
            artifact_path.write_text(json.dumps(events), encoding="utf-8")

        bitrix_path = run_dir / "bitrix_reconciliation.json"
        bitrix = json.loads(bitrix_path.read_text(encoding="utf-8"))
        bitrix["items"].append(
            {"event_id": "evt-old", "bitrix_match_status": "not_found"}
        )
        bitrix_path.write_text(json.dumps(bitrix), encoding="utf-8")

        current_state_path = run_dir / "rop_current_state.json"
        current_state = json.loads(current_state_path.read_text(encoding="utf-8"))
        current_state["kpi"]["lost_in_bitrix"] = 99
        current_state["queues"]["lost_in_bitrix"].append(
            {"event_id": "evt-old", "case_type": "new_lead"}
        )
        current_state_path.write_text(json.dumps(current_state), encoding="utf-8")

        dashboard = build_rop_dashboard(tmp_path, "7d", _null_logger())

        assert dashboard["business_kpi"]["processed_events"] == 3
        assert dashboard["business_kpi"]["lost_in_bitrix"] == 1
        assert dashboard["business_kpi"]["matched_in_bitrix"] == 1
        assert dashboard["business_kpi"]["unreconciled"] == 1
        assert [item["event_id"] for item in dashboard["queues"]["lost_in_bitrix"]] == [
            "evt-002"
        ]

    def test_attachment_refused_is_period_scoped(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        old_ts = (
            (datetime.now(UTC) - timedelta(days=30)).replace(microsecond=0).isoformat()
        )
        for artifact_name in ("normalized_events.json", "classified_events.json"):
            artifact_path = run_dir / artifact_name
            events = json.loads(artifact_path.read_text(encoding="utf-8"))
            events.append(
                {
                    "event_id": "evt-old-attachment",
                    "source_id": "rop_batch_sample",
                    "sender": "old@example.com",
                    "subject": "Old attachment",
                    "case_type": "new_lead",
                    "priority": "low",
                    "is_fallback": False,
                    "event_date": old_ts,
                }
            )
            artifact_path.write_text(json.dumps(events), encoding="utf-8")

        attachment_path = run_dir / "attachment_extraction.json"
        attachment = json.loads(attachment_path.read_text(encoding="utf-8"))
        attachment["aggregate"]["refused_count"] = 2
        attachment["items"].append(
            {
                "event_id": "evt-old-attachment",
                "source_id": "rop_batch_sample",
                "filename": "old.pdf",
                "extraction_status": "refused",
                "is_refused": True,
            }
        )
        attachment_path.write_text(json.dumps(attachment), encoding="utf-8")

        period_dashboard = build_rop_dashboard(tmp_path, "7d", _null_logger())
        all_dashboard = build_rop_dashboard(tmp_path, "all", _null_logger())

        assert period_dashboard["business_kpi"]["attachment_refused"] == 1
        assert all_dashboard["business_kpi"]["attachment_refused"] == 2

    def test_bitrix_period_queues_are_period_scoped_for_all_statuses(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        now_ts = datetime.now(UTC).replace(microsecond=0).isoformat()
        old_ts = (
            (datetime.now(UTC) - timedelta(days=30)).replace(microsecond=0).isoformat()
        )
        extra_events = [
            ("evt-ambiguous", "ambiguous@example.com", "Ambiguous match", now_ts),
            ("evt-duplicate", "duplicate@example.com", "Duplicate match", now_ts),
            ("evt-degraded", "degraded@example.com", "Connector degraded", now_ts),
            ("evt-old-bitrix", "old@example.com", "Old Bitrix event", old_ts),
        ]
        for artifact_name in ("normalized_events.json", "classified_events.json"):
            artifact_path = run_dir / artifact_name
            events = json.loads(artifact_path.read_text(encoding="utf-8"))
            for event_id, sender, subject, event_date in extra_events:
                events.append(
                    {
                        "event_id": event_id,
                        "source_id": "rop_batch_sample",
                        "sender": sender,
                        "subject": subject,
                        "case_type": "new_lead",
                        "priority": "low",
                        "is_fallback": False,
                        "event_date": event_date,
                    }
                )
            artifact_path.write_text(json.dumps(events), encoding="utf-8")

        bitrix_path = run_dir / "bitrix_reconciliation.json"
        bitrix = json.loads(bitrix_path.read_text(encoding="utf-8"))
        bitrix["items"].extend(
            [
                {"event_id": "evt-ambiguous", "bitrix_match_status": "ambiguous"},
                {
                    "event_id": "evt-duplicate",
                    "bitrix_match_status": "duplicate_candidate",
                },
                {
                    "event_id": "evt-degraded",
                    "bitrix_match_status": "connector_degraded",
                },
                {"event_id": "evt-old-bitrix", "bitrix_match_status": "not_found"},
            ]
        )
        bitrix_path.write_text(json.dumps(bitrix), encoding="utf-8")

        dashboard = build_rop_dashboard(tmp_path, "7d", _null_logger())
        queues = dashboard["queues"]
        all_queue_ids = {
            item["event_id"]
            for queue in queues.values()
            for item in queue
            if isinstance(item, dict)
        }

        assert "evt-old-bitrix" not in all_queue_ids
        assert [item["event_id"] for item in queues["matched"]] == ["evt-001"]
        assert [item["event_id"] for item in queues["lost_in_bitrix"]] == ["evt-002"]
        assert {item["event_id"] for item in queues["ambiguous"]} == {
            "evt-ambiguous",
            "evt-duplicate",
        }
        assert [item["event_id"] for item in queues["degraded"]] == ["evt-degraded"]
        assert [item["event_id"] for item in queues["unreconciled"]] == ["evt-003"]
        assert dashboard["business_kpi"]["bitrix_errors"] > 0

    def test_skipped_events_do_not_appear_in_unreconciled_queue(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        bitrix_path = run_dir / "bitrix_reconciliation.json"
        bitrix = json.loads(bitrix_path.read_text(encoding="utf-8"))
        bitrix["items"].append(
            {"event_id": "evt-001", "bitrix_match_status": "skipped"}
        )
        bitrix_path.write_text(json.dumps(bitrix), encoding="utf-8")

        dashboard = build_rop_dashboard(tmp_path, "7d", _null_logger())

        assert dashboard["business_kpi"]["unreconciled"] == 1
        assert [item["event_id"] for item in dashboard["queues"]["unreconciled"]] == [
            "evt-003"
        ]

    def test_queue_entries_include_operator_contract_fields(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        dashboard = build_rop_dashboard(tmp_path, "7d", _null_logger())
        entry = dashboard["queues"]["lost_in_bitrix"][0]

        for field in (
            "event_id",
            "source_id",
            "source_display_name",
            "sender",
            "subject",
            "bot_case_type",
            "bot_priority",
            "bitrix_status",
            "reason",
            "recommended_next_step",
            "run_id",
            "evidence_href",
        ):
            assert field in entry
        assert entry["case_type"] == entry["bot_case_type"]
        assert entry["priority"] == entry["bot_priority"]
        assert entry["run_id"] == "test-dashboard-run"
        assert entry["evidence_href"] == (
            "/runs/test-dashboard-run/artifacts/classified_events_json"
        )

    def test_dashboard_handles_naive_event_timestamp_as_utc(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        naive_ts = datetime.now(UTC).replace(tzinfo=None, microsecond=0).isoformat()
        for artifact_name in ("normalized_events.json", "classified_events.json"):
            artifact_path = run_dir / artifact_name
            events = json.loads(artifact_path.read_text(encoding="utf-8"))
            events[0]["event_date"] = naive_ts
            artifact_path.write_text(json.dumps(events), encoding="utf-8")

        dashboard = build_rop_dashboard(tmp_path, "7d", _null_logger())
        high_priority_ids = {
            item["event_id"] for item in dashboard["queues"]["high_priority"]
        }

        assert dashboard["status"] == "ok"
        assert "evt-001" in high_priority_ids

    def test_duplicate_rows_do_not_enter_needs_review_queue(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        classified = json.loads(
            (run_dir / "classified_events.json").read_text(encoding="utf-8")
        )
        classified.append(
            {
                "event_id": "evt-dup-in-queue",
                "case_type": "duplicate",
                "priority": "medium",
                "confidence": 0.99,
                "is_fallback": False,
                "reason_code": "duplicate_candidate_confirmed",
                "source_id": "rop_batch_sample",
                "sender": "client@example.com",
                "subject": "Welding machine inquiry",
                "event_date": datetime.now(UTC).replace(microsecond=0).isoformat(),
            }
        )
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )

        dashboard = build_rop_dashboard(tmp_path, "7d", _null_logger())

        review_ids = {item["event_id"] for item in dashboard["queues"]["needs_review"]}
        assert "evt-dup-in-queue" not in review_ids
        assert dashboard["status"] == "ok"

    def test_medium_non_fallback_duplicate_does_not_count_in_needs_review_kpi(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        normalized = json.loads(
            (run_dir / "normalized_events.json").read_text(encoding="utf-8")
        )
        classified = json.loads(
            (run_dir / "classified_events.json").read_text(encoding="utf-8")
        )
        event_date = datetime.now(UTC).replace(microsecond=0).isoformat()
        normalized.append(
            {
                "event_id": "evt-dup-kpi",
                "source_id": "rop_batch_sample",
                "sender": "buyer@example.com",
                "subject": "RFQ welding wire",
                "event_date": event_date,
            }
        )
        classified.append(
            {
                "event_id": "evt-dup-kpi",
                "source_id": "rop_batch_sample",
                "case_type": "duplicate",
                "priority": "medium",
                "confidence": 0.9,
                "is_fallback": False,
                "reason_code": "duplicate_candidate_confirmed",
                "event_date": event_date,
            }
        )
        (run_dir / "normalized_events.json").write_text(
            json.dumps(normalized), encoding="utf-8"
        )
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )

        dashboard = build_rop_dashboard(tmp_path, "7d", _null_logger())
        bkpi = dashboard["business_kpi"]
        assert bkpi["needs_review"] == len(dashboard["queues"]["needs_review"])
        assert bkpi["needs_review"] == 1
        assert all(
            item["event_id"] != "evt-dup-kpi"
            for item in dashboard["queues"]["needs_review"]
        )

    def test_high_fallback_duplicate_event_counts_once_in_needs_review(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        classified = json.loads(
            (run_dir / "classified_events.json").read_text(encoding="utf-8")
        )
        classified[0].update(
            {
                "case_type": "duplicate",
                "priority": "high",
                "is_fallback": True,
            }
        )
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )

        dashboard = build_rop_dashboard(tmp_path, "7d", _null_logger())
        bkpi = dashboard["business_kpi"]
        assert bkpi["needs_review"] == len(dashboard["queues"]["needs_review"])
        assert bkpi["needs_review"] == 2
        review_ids = [item["event_id"] for item in dashboard["queues"]["needs_review"]]
        assert review_ids.count("evt-001") == 1


class TestWriteRopDashboard:
    def test_writes_artifact(self, run_dir: Path, tmp_path: Path) -> None:
        dashboard = build_rop_dashboard(tmp_path, "7d", _null_logger())
        path = write_rop_dashboard(tmp_path, dashboard, _null_logger())

        assert path.exists()
        assert path.name == "rop_dashboard.json"
        assert path.parent.name == "interfaces"

        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["status"] == "ok"
        assert loaded["period"] == "7d"
        assert "business_kpi" in loaded

    def test_artifact_is_read_only(self, run_dir: Path, tmp_path: Path) -> None:
        dashboard = build_rop_dashboard(tmp_path, "7d", _null_logger())
        path = write_rop_dashboard(tmp_path, dashboard, _null_logger())
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["read_only"] is True


def test_v2_manifest_accepts_legacy_view_metadata_without_unblocking_legacy_view(
    tmp_path: Path,
) -> None:
    storage_dir = tmp_path / "storage"
    run_id = "run-legacy-v2"
    generation = "g_" + "a" * 32
    revision = "r_" + "b" * 32
    view_path = rop_dashboard_module.rop_web_projection_v2_view_path(
        storage_dir,
        generation,
        run_id,
        revision,
        "overview.7d",
    )
    assert view_path is not None
    view_path.parent.mkdir(parents=True)
    payload = {
        "business_kpi": {},
        "series": {},
        "action_required_count": 0,
    }
    view_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "generation": generation,
                "revision": revision,
                "run_id": run_id,
                "view_key": "overview.7d",
                "payload": payload,
            }
        ),
        encoding="utf-8",
    )
    manifest_path = storage_dir / "interfaces" / "rop_web_projection_v2.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "generation": generation,
                "latest_run_id": run_id,
                "run_ids": [run_id],
                "total_runs": 1,
                "runs": {
                    run_id: {
                        "generation": generation,
                        "revision": revision,
                        "view_keys": [
                            "overview.7d",
                            "api.7d",
                            "queue",
                            "sources",
                            "threads",
                            "attachments",
                            "ai_assist",
                            "evidence",
                            "recommendations",
                            "bitrix.7d",
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    manifest = rop_dashboard_module.rop_web_projection_v2_manifest(storage_dir)

    assert manifest is not None
    assert (
        rop_dashboard_module.read_rop_web_projection_v2_view(
            storage_dir, manifest, run_id, "overview", "7d"
        )
        == payload
    )
    assert (
        rop_dashboard_module.read_rop_web_projection_v2_view(
            storage_dir, manifest, run_id, "threads"
        )
        is None
    )


class TestSettingsValidation:
    def test_settings_rop_dashboard_contract(self) -> None:
        settings = load_settings(_project_root() / "config" / "settings.yml")
        dashboard = settings["rop"]["dashboard"]
        periods = dashboard["periods"]
        plan_lead = dashboard["leaderboard"]["plan_lead"]

        assert dashboard["default_period"] in periods
        assert isinstance(periods, list)
        assert isinstance(plan_lead, int)
        assert not isinstance(plan_lead, bool)
        assert plan_lead > 0
        for period in periods:
            validate_period(period)


def test_team_leaderboard_counts_only_canonical_current_month_new_leads() -> None:
    now = datetime(2026, 9, 15, tzinfo=UTC)
    events = [
        {
            "_dashboard_origin_run_id": "run-1",
            "source_id": "mail",
            "event_id": f"event-{number}",
            "event_instance_id": "",
            "received_at": timestamp,
            "case_type": "new_lead" if number in (1, 2, 3, 4) else "irrelevant",
        }
        for number, timestamp in enumerate(
            [
                "2026-09-01T00:00:00Z",
                "2026-09-02T00:00:00Z",
                "2026-09-03T00:00:00Z",
                "2026-08-01T00:00:00Z",
                "2026-08-02T00:00:00Z",
                "2026-08-03T00:00:00Z",
                "2026-08-04T00:00:00Z",
                "2026-09-04T00:00:00Z",
            ],
            start=1,
        )
    ]
    routing = [
        {
            "_dashboard_origin_run_id": "run-1",
            "source_id": "mail",
            "event_id": f"event-{number}",
            "event_instance_id": "",
            "responsible": {
                "status": "matched" if number != 8 else "not_found",
                "user_id": 7 if number != 8 else -1,
                "name": "Ada Lovelace",
            },
        }
        for number in range(1, 9)
    ]
    writeback_state = {
        "events": {
            f"client-a|mail|event-{number}": {
                "semantic_case_type": "new_lead",
                "outcome": "create_lead",
                "responsible_status": "matched",
                "responsible_user_id": 7,
            }
            for number in range(1, 8)
        }
    }
    leaderboard = rop_dashboard_module._build_team_leaderboard(
        events,
        routing,
        TEST_PLAN_LEAD,
        "client-a",
        writeback_state,
        167,
        "ROBOT WG",
        now,
    )
    assert leaderboard == {
        "month": "2026-09",
        "plan_lead": TEST_PLAN_LEAD,
        "items": [
            {
                "user_id": 7,
                "name": "Ada Lovelace",
                "current_month_count": 3,
                "score_percent": 15,
            }
        ],
    }


def test_team_leaderboard_omits_ambiguous_routing_and_limits_rankings() -> None:
    now = datetime(2026, 9, 15, tzinfo=UTC)
    events = []
    routing = []
    for user_id in range(1, 8):
        event = {
            "_dashboard_origin_run_id": "run-1",
            "source_id": "mail",
            "event_id": f"event-{user_id}",
            "event_instance_id": "",
            "received_at": "2026-09-01T00:00:00Z",
            "case_type": "new_lead",
        }
        events.append(event)
        routing.append(
            {
                **{key: event[key] for key in event if key != "received_at"},
                "responsible": {
                    "status": "matched",
                    "user_id": user_id,
                    "name": f"User {8 - user_id}",
                },
            }
        )
    routing.append(dict(routing[0]))
    writeback_state = {
        "events": {
            f"client-a|mail|event-{user_id}": {
                "semantic_case_type": "new_lead",
                "outcome": "create_lead",
                "responsible_status": "matched",
                "responsible_user_id": user_id,
            }
            for user_id in range(1, 8)
        }
    }
    leaderboard = rop_dashboard_module._build_team_leaderboard(
        events,
        routing,
        TEST_PLAN_LEAD,
        "client-a",
        writeback_state,
        167,
        "ROBOT WG",
        now,
    )
    assert [item["user_id"] for item in leaderboard["items"]] == [7, 6, 5, 4, 3]
    assert all(item["score_percent"] == 5 for item in leaderboard["items"])
