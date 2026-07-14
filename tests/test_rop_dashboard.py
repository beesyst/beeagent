from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from beeagent_module.cases import rop_dashboard as rop_dashboard_module
from beeagent_module.cases.rop_dashboard import (
    ALLOWED_PERIODS,
    build_rop_dashboard,
    parse_period,
    validate_period,
    write_rop_dashboard,
)
from beeagent_module.core.settings import load_settings

os.environ.setdefault("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
os.environ.setdefault("BEEAGENT_WEB_ADMIN1_TOKEN", "test-admin1-token")
os.environ.setdefault("BEEAGENT_WEB_ADMIN2_TOKEN", "test-admin2-token")


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


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    """Create a minimal run directory with artifacts for dashboard testing."""
    rdir = tmp_path / "runs" / "test-dashboard-run"
    rdir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
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

    def test_parse_today(self) -> None:
        info = parse_period("today")
        assert info["period"] == "today"
        assert info["period_start_utc"] is not None
        assert info["period_end_utc"] is not None
        assert info["time_basis"] == "event_timestamp"

    def test_parse_yesterday(self) -> None:
        info = parse_period("yesterday")
        assert info["period"] == "yesterday"
        assert info["time_basis"] == "event_timestamp"

    def test_parse_7d(self) -> None:
        info = parse_period("7d")
        assert info["period"] == "7d"
        assert info["time_basis"] == "event_timestamp"

    def test_parse_30d(self) -> None:
        info = parse_period("30d")
        assert info["period"] == "30d"
        assert info["time_basis"] == "event_timestamp"

    def test_parse_90d(self) -> None:
        info = parse_period("90d")
        assert info["period"] == "90d"
        assert info["period_start_utc"] is not None
        assert info["period_end_utc"] is not None
        assert info["time_basis"] == "event_timestamp"

    def test_parse_365d(self) -> None:
        info = parse_period("365d")
        assert info["period"] == "365d"

    def test_parse_all(self) -> None:
        info = parse_period("all")
        assert info["period"] == "all"
        assert info["period_start_utc"] is None
        assert info["period_end_utc"] is None
        assert info["time_basis"] == "event_timestamp"

    def test_parse_invalid_period_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported period"):
            parse_period("invalid")
        with pytest.raises(ValueError, match="Unsupported period"):
            parse_period("1d")
        with pytest.raises(ValueError, match="Unsupported period"):
            parse_period("")

    def test_validate_allowed(self) -> None:
        for p in ALLOWED_PERIODS:
            validate_period(p)

    def test_validate_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid period"):
            validate_period("1d")
        with pytest.raises(ValueError, match="Invalid period"):
            validate_period("")


class TestBuildRopDashboard:
    def test_dashboard_basic_structure(self, run_dir: Path, tmp_path: Path) -> None:
        dashboard = build_rop_dashboard(
            storage_dir=tmp_path,
            period="7d",
            logger=_null_logger(),
        )
        assert dashboard["status"] == "ok"
        assert dashboard["read_only"] is True
        assert dashboard["period"] == "7d"
        assert "generated_at_utc" in dashboard
        assert "business_kpi" in dashboard
        assert "series" in dashboard
        assert "queues" in dashboard
        assert "rop_recommendations" in dashboard
        assert "evidence_links" in dashboard
        assert "warnings" in dashboard
        assert dashboard["run_id"] == "test-dashboard-run"

    def test_business_kpi_present(self, run_dir: Path, tmp_path: Path) -> None:
        dashboard = build_rop_dashboard(tmp_path, "7d", _null_logger())
        bkpi = dashboard["business_kpi"]
        assert bkpi["processed_events"] == 3
        assert bkpi["new_leads"] == 2
        assert bkpi["existing_clients"] == 1
        assert bkpi["high_priority"] == 2
        assert bkpi["needs_review"] >= 2
        assert "lost_in_bitrix" in bkpi
        assert "unreconciled" in bkpi
        assert "source_degraded" in bkpi
        assert "attachment_refused" in bkpi

    def test_series_present(self, run_dir: Path, tmp_path: Path) -> None:
        dashboard = build_rop_dashboard(tmp_path, "7d", _null_logger())
        series = dashboard["series"]
        assert "processed_by_day" in series
        assert "classification_distribution" in series
        assert "bitrix_distribution" in series
        assert "source_contribution" in series

    def test_queues_present(self, run_dir: Path, tmp_path: Path) -> None:
        dashboard = build_rop_dashboard(tmp_path, "7d", _null_logger())
        queues = dashboard["queues"]
        assert "high_priority" in queues
        assert "needs_review" in queues
        assert "lost_in_bitrix" in queues
        assert "unreconciled" in queues
        assert len(queues["high_priority"]) == 2

    def test_recommendations_generated(self, run_dir: Path, tmp_path: Path) -> None:
        dashboard = build_rop_dashboard(tmp_path, "7d", _null_logger())
        recs = dashboard["rop_recommendations"]
        assert len(recs) > 0
        codes = {r["reason_code"] for r in recs}
        assert "high_priority" in codes
        assert "lost_in_bitrix" in codes
        assert "attachment_refused" in codes

    def test_evidence_links_present(self, run_dir: Path, tmp_path: Path) -> None:
        dashboard = build_rop_dashboard(tmp_path, "7d", _null_logger())
        links = dashboard["evidence_links"]
        assert len(links) > 0
        assert all("artifact_id" in l for l in links)
        assert all("href" in l for l in links)

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
            datetime.now(timezone.utc).replace(microsecond=0).isoformat()
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
            (datetime.now(timezone.utc) - timedelta(days=30))
            .replace(microsecond=0)
            .isoformat()
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
            (datetime.now(timezone.utc) - timedelta(days=30))
            .replace(microsecond=0)
            .isoformat()
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
        now_ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        old_ts = (
            (datetime.now(timezone.utc) - timedelta(days=30))
            .replace(microsecond=0)
            .isoformat()
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
        naive_ts = (
            datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat()
        )
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


class TestSettingsValidation:
    def test_settings_has_rop_dashboard(self) -> None:
        settings = load_settings(_project_root() / "config" / "settings.yml")
        dash = settings.get("rop", {}).get("dashboard", {})
        assert "default_period" in dash
        assert "periods" in dash
        assert dash["default_period"] == "7d"
        assert isinstance(dash["periods"], list)
        assert "7d" in dash["periods"]

    def test_settings_default_period_is_valid(self) -> None:
        settings = load_settings(_project_root() / "config" / "settings.yml")
        default_period = settings["rop"]["dashboard"]["default_period"]
        validate_period(default_period)

    def test_all_periods_are_valid(self) -> None:
        settings = load_settings(_project_root() / "config" / "settings.yml")
        for p in settings["rop"]["dashboard"]["periods"]:
            validate_period(p)


# ── Filter tests ───────────────────────────────────────────────────────────


class TestQueueFilters:
    """Tests for queue filter validation and application."""

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

    def test_validate_filter_params_rejects_bad_date(self) -> None:
        errors = rop_dashboard_module.validate_filter_params(
            {"date_from": "not-a-date"}
        )
        assert any("Invalid date_from" in e for e in errors)

    def test_validate_filter_params_rejects_date_from_after_to(self) -> None:
        errors = rop_dashboard_module.validate_filter_params(
            {"date_from": "2026-06-30", "date_to": "2026-06-01"}
        )
        assert any("date_from must not be after date_to" in e for e in errors)

    def test_validate_filter_params_rejects_bad_classification(self) -> None:
        errors = rop_dashboard_module.validate_filter_params(
            {"classification": "non_existent_type"}
        )
        assert any("Invalid classification" in e for e in errors)

    def test_validate_filter_params_rejects_bad_priority(self) -> None:
        errors = rop_dashboard_module.validate_filter_params(
            {"priority": "urgent"}
        )
        assert any("Invalid priority" in e for e in errors)

    def test_validate_filter_params_rejects_bad_bitrix_status(self) -> None:
        errors = rop_dashboard_module.validate_filter_params(
            {"bitrix_status": "non_existent"}
        )
        assert any("Invalid bitrix_status" in e for e in errors)

    def test_validate_filter_params_rejects_bad_is_fallback(self) -> None:
        errors = rop_dashboard_module.validate_filter_params(
            {"is_fallback": "maybe"}
        )
        assert any("Invalid is_fallback" in e for e in errors)

    def test_validate_filter_params_accepts_is_fallback(self) -> None:
        errors = rop_dashboard_module.validate_filter_params(
            {"is_fallback": "true"}
        )
        assert errors == []
        errors = rop_dashboard_module.validate_filter_params(
            {"is_fallback": "false"}
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
            {"event_id": "4"},  # missing is_fallback → False
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
        """Verify the input list is not mutated."""
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
