from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

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
os.environ.setdefault("BEEAGENT_WEB_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("BEEAGENT_WEB_ROP_TOKEN", "test-rop-token")
os.environ.setdefault("BEEAGENT_WEB_OPERATOR_TOKEN", "test-operator-token")


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


def _copy_run(source: Path, name: str) -> Path:
    target = source.parent / name
    shutil.copytree(source, target)
    return target


class TestCrossRunPeriodAggregation:
    def test_aggregates_same_client_runs_and_preserves_origin(
        self, run_dir: Path
    ) -> None:
        newest = _copy_run(run_dir, "newest-run")
        classified = json.loads((newest / "classified_events.json").read_text())
        normalized = json.loads((newest / "normalized_events.json").read_text())
        classified[:] = [
            {
                **classified[0],
                "event_id": "evt-new",
                "source_id": "new-source",
                "priority": "high",
            }
        ]
        normalized[:] = [
            {
                **normalized[0],
                "event_id": "evt-new",
                "source_id": "new-source",
                "message_id": "<new@example.test>",
            }
        ]
        (newest / "classified_events.json").write_text(json.dumps(classified))
        (newest / "normalized_events.json").write_text(json.dumps(normalized))

        dashboard = build_rop_dashboard(
            run_dir.parents[1], "7d", _null_logger(), "newest-run", aggregate_runs=True
        )

        assert dashboard["business_kpi"]["processed_events"] == 4
        assert {item["run_id"] for item in dashboard["queues"]["high_priority"]} == {
            "test-dashboard-run",
            "newest-run",
        }
        assert all(
            item["evidence_href"]
            == f"/runs/{item['run_id']}/artifacts/classified_events_json"
            for item in dashboard["queues"]["high_priority"]
        )

    def test_deduplicates_newest_message_and_isolates_client(
        self, run_dir: Path
    ) -> None:
        newest = _copy_run(run_dir, "newest-run")
        other = _copy_run(run_dir, "other-client-run")
        old_normalized = json.loads((run_dir / "normalized_events.json").read_text())
        old_normalized[0]["message_id"] = "<same@example.test>"
        (run_dir / "normalized_events.json").write_text(json.dumps(old_normalized))
        new_normalized = json.loads((newest / "normalized_events.json").read_text())
        new_classified = json.loads((newest / "classified_events.json").read_text())
        new_normalized[:] = [
            {
                **new_normalized[0],
                "event_id": "evt-new",
                "message_id": "<same@example.test>",
            }
        ]
        new_classified[:] = [
            {**new_classified[0], "event_id": "evt-new", "priority": "low"}
        ]
        (newest / "normalized_events.json").write_text(json.dumps(new_normalized))
        (newest / "classified_events.json").write_text(json.dumps(new_classified))
        other_source = json.loads((other / "source_diagnostics.json").read_text())
        for source in other_source["sources"]:
            source["client_id"] = "other-client"
        (other / "source_diagnostics.json").write_text(json.dumps(other_source))
        other_state = json.loads((other / "rop_current_state.json").read_text())
        other_state["client_id"] = "other-client"
        (other / "rop_current_state.json").write_text(json.dumps(other_state))

        dashboard = build_rop_dashboard(
            run_dir.parents[1], "all", _null_logger(), "newest-run", aggregate_runs=True
        )

        assert dashboard["business_kpi"]["processed_events"] == 3
        assert {item["run_id"] for item in dashboard["queues"]["high_priority"]} == {
            "test-dashboard-run"
        }

    def test_aggregate_only_attachment_counters_do_not_fan_out(
        self, run_dir: Path
    ) -> None:
        for run in (
            run_dir,
            _copy_run(run_dir, "newest-run"),
            _copy_run(run_dir, "oldest-run"),
        ):
            attachment_path = run / "attachment_extraction.json"
            attachment = json.loads(attachment_path.read_text(encoding="utf-8"))
            attachment["items"] = []
            attachment["aggregate"]["refused_count"] = 1
            attachment["aggregate"]["blocked_count"] = 0
            attachment_path.write_text(json.dumps(attachment), encoding="utf-8")

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "all",
            _null_logger(),
            "newest-run",
            aggregate_runs=True,
        )

        assert dashboard["business_kpi"]["attachment_refused"] == 0
        unscoped = [
            w
            for w in dashboard["warnings"]
            if w.get("code") == "attachment_aggregate_unscoped"
        ]
        assert unscoped
        assert all(w.get("run_id") for w in unscoped)
        assert all(w.get("artifact") == "attachment_extraction.json" for w in unscoped)

    def test_malformed_optional_artifacts_warn_and_are_ignored(
        self, run_dir: Path
    ) -> None:
        newest = _copy_run(run_dir, "newest-run")
        (newest / "bitrix_reconciliation.json").write_text(
            "{bad json", encoding="utf-8"
        )
        (newest / "attachment_extraction.json").write_text("not-json", encoding="utf-8")

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "7d",
            _null_logger(),
            "newest-run",
            aggregate_runs=True,
        )

        assert dashboard["status"] == "ok"
        malformed = [
            w
            for w in dashboard["warnings"]
            if w.get("code") == "malformed_optional_artifact"
        ]
        assert {w.get("artifact") for w in malformed} == {
            "bitrix_reconciliation.json",
            "attachment_extraction.json",
        }
        assert all(w.get("run_id") == "newest-run" for w in malformed)

    def test_same_event_id_different_source_does_not_collapse(
        self, run_dir: Path
    ) -> None:
        newest = _copy_run(run_dir, "newest-run")
        classified = json.loads((newest / "classified_events.json").read_text())
        normalized = json.loads((newest / "normalized_events.json").read_text())
        classified[:] = [
            {
                **classified[2],
                "event_id": "evt-003",
                "source_id": "second_mailbox",
                "priority": "high",
                "is_fallback": True,
            }
        ]
        normalized[:] = [
            {
                **normalized[2],
                "event_id": "evt-003",
                "source_id": "second_mailbox",
            }
        ]
        (newest / "classified_events.json").write_text(json.dumps(classified))
        (newest / "normalized_events.json").write_text(json.dumps(normalized))

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "all",
            _null_logger(),
            "newest-run",
            aggregate_runs=True,
        )

        assert dashboard["business_kpi"]["processed_events"] == 4
        hp_ids = {
            (item["event_id"], item["source_id"])
            for item in dashboard["queues"]["high_priority"]
        }
        assert ("evt-003", "hotline_mailbox") in hp_ids
        assert ("evt-003", "second_mailbox") in hp_ids
        nr_ids = [
            (item["event_id"], item["source_id"])
            for item in dashboard["queues"]["needs_review"]
        ]
        assert ("evt-003", "hotline_mailbox") in nr_ids
        assert ("evt-003", "second_mailbox") in nr_ids

    def test_old_run_excluded_from_7d_included_in_all(self, run_dir: Path) -> None:
        old = _copy_run(run_dir, "old-run")
        old_ts = (
            (datetime.now(UTC) - timedelta(days=30)).replace(microsecond=0).isoformat()
        )
        for artifact_name in ("normalized_events.json", "classified_events.json"):
            path = old / artifact_name
            events = json.loads(path.read_text(encoding="utf-8"))
            for idx, event in enumerate(events):
                event["event_id"] = f"old-{idx}"
                event["event_date"] = old_ts
            path.write_text(json.dumps(events), encoding="utf-8")

        seven_day = build_rop_dashboard(
            run_dir.parents[1],
            "7d",
            _null_logger(),
            "test-dashboard-run",
            aggregate_runs=True,
        )
        all_period = build_rop_dashboard(
            run_dir.parents[1],
            "all",
            _null_logger(),
            "test-dashboard-run",
            aggregate_runs=True,
        )

        assert seven_day["business_kpi"]["processed_events"] == 3
        assert all_period["business_kpi"]["processed_events"] == 6

    def test_unknown_anchor_client_scope_retains_anchor_data_and_warns(
        self, run_dir: Path
    ) -> None:
        state_path = run_dir / "rop_current_state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["client_id"] = "unknown"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        source_path = run_dir / "source_diagnostics.json"
        source = json.loads(source_path.read_text(encoding="utf-8"))
        for s in source["sources"]:
            s["client_id"] = "unknown"
        source_path.write_text(json.dumps(source), encoding="utf-8")

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "7d",
            _null_logger(),
            "test-dashboard-run",
            aggregate_runs=True,
        )

        assert dashboard["business_kpi"]["processed_events"] == 3
        assert any(
            w.get("code") == "unknown_client_scope" for w in dashboard["warnings"]
        )

    def test_newest_duplicate_wins_with_newest_values(self, run_dir: Path) -> None:
        newest = _copy_run(run_dir, "newest-run")
        old_normalized = json.loads((run_dir / "normalized_events.json").read_text())
        old_normalized[0]["message_id"] = "<dup@example.test>"
        (run_dir / "normalized_events.json").write_text(json.dumps(old_normalized))
        old_classified = json.loads((run_dir / "classified_events.json").read_text())
        old_classified[0]["priority"] = "low"
        old_classified[0]["case_type"] = "existing_deal"
        (run_dir / "classified_events.json").write_text(json.dumps(old_classified))

        new_normalized = json.loads((newest / "normalized_events.json").read_text())
        new_classified = json.loads((newest / "classified_events.json").read_text())
        new_normalized[:] = [
            {
                **new_normalized[0],
                "event_id": "evt-dup",
                "message_id": "<dup@example.test>",
            }
        ]
        new_classified[:] = [
            {
                **new_classified[0],
                "event_id": "evt-dup",
                "priority": "high",
                "case_type": "new_lead",
            }
        ]
        (newest / "normalized_events.json").write_text(json.dumps(new_normalized))
        (newest / "classified_events.json").write_text(json.dumps(new_classified))

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "all",
            _null_logger(),
            "newest-run",
            aggregate_runs=True,
        )

        assert dashboard["business_kpi"]["processed_events"] == 3
        high_ids = {
            (item["event_id"], item["run_id"])
            for item in dashboard["queues"]["high_priority"]
        }
        assert ("evt-dup", "newest-run") in high_ids
        assert not any(
            item["event_id"] == "evt-001"
            for item in dashboard["queues"]["high_priority"]
        )

    def test_bitrix_cross_run_matched_and_not_found(self, run_dir: Path) -> None:
        newest = _copy_run(run_dir, "newest-run")
        classified = json.loads((newest / "classified_events.json").read_text())
        normalized = json.loads((newest / "normalized_events.json").read_text())
        classified[:] = [
            {
                **classified[0],
                "event_id": "evt-001",
                "source_id": "rop_batch_sample",
            }
        ]
        normalized[:] = [
            {
                **normalized[0],
                "event_id": "evt-001",
                "source_id": "rop_batch_sample",
            }
        ]
        (newest / "classified_events.json").write_text(json.dumps(classified))
        (newest / "normalized_events.json").write_text(json.dumps(normalized))
        recon_path = newest / "bitrix_reconciliation.json"
        recon = json.loads(recon_path.read_text(encoding="utf-8"))
        recon["items"] = [
            {"event_id": "evt-001", "bitrix_match_status": "matched_lead"}
        ]
        recon_path.write_text(json.dumps(recon), encoding="utf-8")

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "all",
            _null_logger(),
            "newest-run",
            aggregate_runs=True,
        )

        assert dashboard["business_kpi"]["matched_in_bitrix"] == 1
        assert dashboard["business_kpi"]["lost_in_bitrix"] == 1
        assert [item["event_id"] for item in dashboard["queues"]["matched"]] == [
            "evt-001"
        ]
        assert [item["event_id"] for item in dashboard["queues"]["lost_in_bitrix"]] == [
            "evt-002"
        ]

    def test_duplicate_bitrix_winner_newest_matched_wins(self, run_dir: Path) -> None:
        newest = _copy_run(run_dir, "newest-run")
        old_normalized = json.loads((run_dir / "normalized_events.json").read_text())
        old_normalized[0]["message_id"] = "<bx-dup@example.test>"
        (run_dir / "normalized_events.json").write_text(json.dumps(old_normalized))
        old_recon_path = run_dir / "bitrix_reconciliation.json"
        old_recon = json.loads(old_recon_path.read_text(encoding="utf-8"))
        old_recon["items"][0]["bitrix_match_status"] = "ambiguous"
        old_recon_path.write_text(json.dumps(old_recon), encoding="utf-8")

        new_normalized = json.loads((newest / "normalized_events.json").read_text())
        new_classified = json.loads((newest / "classified_events.json").read_text())
        new_normalized[:] = [
            {
                **new_normalized[0],
                "event_id": "evt-bxdup",
                "message_id": "<bx-dup@example.test>",
            }
        ]
        new_classified[:] = [{**new_classified[0], "event_id": "evt-bxdup"}]
        (newest / "normalized_events.json").write_text(json.dumps(new_normalized))
        (newest / "classified_events.json").write_text(json.dumps(new_classified))
        new_recon_path = newest / "bitrix_reconciliation.json"
        new_recon = json.loads(new_recon_path.read_text(encoding="utf-8"))
        new_recon["items"] = [
            {"event_id": "evt-bxdup", "bitrix_match_status": "matched_lead"}
        ]
        new_recon_path.write_text(json.dumps(new_recon), encoding="utf-8")

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "all",
            _null_logger(),
            "newest-run",
            aggregate_runs=True,
        )

        assert dashboard["business_kpi"]["matched_in_bitrix"] == 1
        assert dashboard["business_kpi"]["ambiguous_or_duplicate"] == 0
        assert [item["event_id"] for item in dashboard["queues"]["matched"]] == [
            "evt-bxdup"
        ]
        assert dashboard["queues"]["ambiguous"] == []

    def test_attachment_items_attach_only_to_canonical_winner(
        self, run_dir: Path
    ) -> None:
        newest = _copy_run(run_dir, "newest-run")
        old_normalized = json.loads((run_dir / "normalized_events.json").read_text())
        old_normalized[0]["message_id"] = "<att-dup@example.test>"
        (run_dir / "normalized_events.json").write_text(json.dumps(old_normalized))
        old_att_path = run_dir / "attachment_extraction.json"
        old_att = json.loads(old_att_path.read_text(encoding="utf-8"))
        old_att["items"] = [
            {
                "event_id": "evt-001",
                "source_id": "rop_batch_sample",
                "filename": "old.pdf",
                "extraction_status": "refused",
                "is_refused": True,
            }
        ]
        old_att_path.write_text(json.dumps(old_att), encoding="utf-8")

        new_normalized = json.loads((newest / "normalized_events.json").read_text())
        new_classified = json.loads((newest / "classified_events.json").read_text())
        new_normalized[:] = [
            {
                **new_normalized[0],
                "event_id": "evt-att",
                "message_id": "<att-dup@example.test>",
            }
        ]
        new_classified[:] = [{**new_classified[0], "event_id": "evt-att"}]
        (newest / "normalized_events.json").write_text(json.dumps(new_normalized))
        (newest / "classified_events.json").write_text(json.dumps(new_classified))
        att_path = newest / "attachment_extraction.json"
        att = json.loads(att_path.read_text(encoding="utf-8"))
        att["items"] = [
            {
                "event_id": "evt-att",
                "source_id": "rop_batch_sample",
                "filename": "new.pdf",
                "extraction_status": "refused",
                "is_refused": True,
            }
        ]
        att_path.write_text(json.dumps(att), encoding="utf-8")

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "all",
            _null_logger(),
            "newest-run",
            aggregate_runs=True,
        )

        assert dashboard["business_kpi"]["processed_events"] == 3
        assert dashboard["business_kpi"]["attachment_refused"] == 1

    def test_degraded_run_excluded_from_aggregate(self, run_dir: Path) -> None:
        degraded = _copy_run(run_dir, "degraded-run")
        classified = json.loads((degraded / "classified_events.json").read_text())
        normalized = json.loads((degraded / "normalized_events.json").read_text())
        classified[:] = [
            {
                **classified[0],
                "event_id": "evt-degraded",
                "source_id": "rop_batch_sample",
            }
        ]
        normalized[:] = [
            {
                **normalized[0],
                "event_id": "evt-degraded",
                "source_id": "rop_batch_sample",
            }
        ]
        (degraded / "classified_events.json").write_text(json.dumps(classified))
        (degraded / "normalized_events.json").write_text(json.dumps(normalized))
        summary_path = degraded / "operator_summary.json"
        summary_path.write_text(
            json.dumps({"status": "error", "module_status": "ok"}),
            encoding="utf-8",
        )

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "all",
            _null_logger(),
            "test-dashboard-run",
            aggregate_runs=True,
        )

        assert dashboard["business_kpi"]["processed_events"] == 3
        assert any(
            w.get("code") == "incomplete_run_skipped"
            and w.get("run_id") == "degraded-run"
            for w in dashboard["warnings"]
        )

    def test_fallback_identity_uses_event_id_without_message_ids(
        self, run_dir: Path
    ) -> None:
        newest = _copy_run(run_dir, "newest-run")
        classified = json.loads((newest / "classified_events.json").read_text())
        normalized = json.loads((newest / "normalized_events.json").read_text())
        classified[:] = [{**classified[0], "event_id": "evt-001", "priority": "high"}]
        normalized[:] = [{**normalized[0], "event_id": "evt-001", "message_id": None}]
        (newest / "classified_events.json").write_text(json.dumps(classified))
        (newest / "normalized_events.json").write_text(json.dumps(normalized))

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "all",
            _null_logger(),
            "newest-run",
            aggregate_runs=True,
        )

        assert dashboard["business_kpi"]["processed_events"] == 3
        evt001 = [
            item
            for item in dashboard["queues"]["high_priority"]
            if item["event_id"] == "evt-001"
        ]
        assert len(evt001) == 1
        assert evt001[0]["run_id"] == "newest-run"

    def test_multi_source_run_filters_events_by_own_client(self, run_dir: Path) -> None:
        newest = _copy_run(run_dir, "newest-run")
        classified = json.loads((newest / "classified_events.json").read_text())
        normalized = json.loads((newest / "normalized_events.json").read_text())
        classified[:] = [
            {
                **classified[0],
                "event_id": "evt-a",
                "source_id": "src-a",
                "client_id": "welding",
                "priority": "high",
            },
            {
                **classified[1],
                "event_id": "evt-b",
                "source_id": "src-b",
                "client_id": "other-client",
                "priority": "high",
            },
        ]
        normalized[:] = [
            {
                **normalized[0],
                "event_id": "evt-a",
                "source_id": "src-a",
                "client_id": "welding",
            },
            {
                **normalized[1],
                "event_id": "evt-b",
                "source_id": "src-b",
                "client_id": "other-client",
            },
        ]
        (newest / "classified_events.json").write_text(json.dumps(classified))
        (newest / "normalized_events.json").write_text(json.dumps(normalized))
        source_diag = {
            "sources": [
                {"source_id": "src-a", "client_id": "welding", "status": "ok"},
                {"source_id": "src-b", "client_id": "other-client", "status": "ok"},
            ]
        }
        (newest / "source_diagnostics.json").write_text(
            json.dumps(source_diag), encoding="utf-8"
        )

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "all",
            _null_logger(),
            "newest-run",
            aggregate_runs=True,
        )

        assert dashboard["business_kpi"]["processed_events"] == 4
        hp_ids = {item["event_id"] for item in dashboard["queues"]["high_priority"]}
        assert "evt-a" in hp_ids
        assert "evt-b" not in hp_ids

    def test_bitrix_source_aware_same_event_id_different_status(
        self, run_dir: Path
    ) -> None:
        newest = _copy_run(run_dir, "newest-run")
        classified = json.loads((newest / "classified_events.json").read_text())
        normalized = json.loads((newest / "normalized_events.json").read_text())
        classified[:] = [
            {
                **classified[0],
                "event_id": "evt-src",
                "source_id": "src-a",
                "priority": "low",
            },
            {
                **classified[1],
                "event_id": "evt-src",
                "source_id": "src-b",
                "priority": "low",
            },
        ]
        normalized[:] = [
            {
                **normalized[0],
                "event_id": "evt-src",
                "source_id": "src-a",
            },
            {
                **normalized[1],
                "event_id": "evt-src",
                "source_id": "src-b",
            },
        ]
        (newest / "classified_events.json").write_text(json.dumps(classified))
        (newest / "normalized_events.json").write_text(json.dumps(normalized))
        recon_path = newest / "bitrix_reconciliation.json"
        recon = json.loads(recon_path.read_text(encoding="utf-8"))
        recon["items"] = [
            {
                "event_id": "evt-src",
                "source_id": "src-a",
                "bitrix_match_status": "matched_lead",
            },
            {
                "event_id": "evt-src",
                "source_id": "src-b",
                "bitrix_match_status": "not_found",
            },
        ]
        recon_path.write_text(json.dumps(recon), encoding="utf-8")
        (run_dir / "bitrix_reconciliation.json").unlink(missing_ok=True)

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "all",
            _null_logger(),
            "newest-run",
            aggregate_runs=True,
        )

        assert dashboard["business_kpi"]["matched_in_bitrix"] == 1
        assert dashboard["business_kpi"]["lost_in_bitrix"] == 1
        assert {item["source_id"] for item in dashboard["queues"]["matched"]} == {
            "src-a"
        }
        assert {
            item["source_id"] for item in dashboard["queues"]["lost_in_bitrix"]
        } == {"src-b"}

    def test_bitrix_legacy_source_less_reconciliation_single_source(
        self, run_dir: Path
    ) -> None:
        newest = _copy_run(run_dir, "newest-run")
        classified = json.loads((newest / "classified_events.json").read_text())
        normalized = json.loads((newest / "normalized_events.json").read_text())
        classified[:] = [
            {
                **classified[0],
                "event_id": "evt-legacy",
                "source_id": "src-a",
                "priority": "low",
            }
        ]
        normalized[:] = [
            {
                **normalized[0],
                "event_id": "evt-legacy",
                "source_id": "src-a",
            }
        ]
        (newest / "classified_events.json").write_text(json.dumps(classified))
        (newest / "normalized_events.json").write_text(json.dumps(normalized))
        recon_path = newest / "bitrix_reconciliation.json"
        recon = json.loads(recon_path.read_text(encoding="utf-8"))
        recon["items"] = [
            {"event_id": "evt-legacy", "bitrix_match_status": "matched_lead"}
        ]
        recon_path.write_text(json.dumps(recon), encoding="utf-8")
        (run_dir / "bitrix_reconciliation.json").unlink(missing_ok=True)

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "all",
            _null_logger(),
            "newest-run",
            aggregate_runs=True,
        )

        assert dashboard["business_kpi"]["matched_in_bitrix"] == 1
        assert [item["event_id"] for item in dashboard["queues"]["matched"]] == [
            "evt-legacy"
        ]

    def test_bitrix_legacy_source_less_ambiguous_not_assigned(
        self, run_dir: Path
    ) -> None:
        newest = _copy_run(run_dir, "newest-run")
        classified = json.loads((newest / "classified_events.json").read_text())
        normalized = json.loads((newest / "normalized_events.json").read_text())
        classified[:] = [
            {
                **classified[0],
                "event_id": "evt-legacy",
                "source_id": "src-a",
                "priority": "low",
            },
            {
                **classified[1],
                "event_id": "evt-legacy",
                "source_id": "src-b",
                "priority": "low",
            },
        ]
        normalized[:] = [
            {
                **normalized[0],
                "event_id": "evt-legacy",
                "source_id": "src-a",
            },
            {
                **normalized[1],
                "event_id": "evt-legacy",
                "source_id": "src-b",
            },
        ]
        (newest / "classified_events.json").write_text(json.dumps(classified))
        (newest / "normalized_events.json").write_text(json.dumps(normalized))
        recon_path = newest / "bitrix_reconciliation.json"
        recon = json.loads(recon_path.read_text(encoding="utf-8"))
        recon["items"] = [
            {"event_id": "evt-legacy", "bitrix_match_status": "matched_lead"}
        ]
        recon_path.write_text(json.dumps(recon), encoding="utf-8")
        (run_dir / "bitrix_reconciliation.json").unlink(missing_ok=True)

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "all",
            _null_logger(),
            "newest-run",
            aggregate_runs=True,
        )

        assert dashboard["business_kpi"]["matched_in_bitrix"] == 0
        assert dashboard["queues"]["matched"] == []
        assert dashboard["business_kpi"]["unreconciled"] == 5

    def test_legacy_attachment_source_less_binds_single_source(
        self, run_dir: Path
    ) -> None:
        newest = _copy_run(run_dir, "newest-run")
        classified = json.loads((newest / "classified_events.json").read_text())
        normalized = json.loads((newest / "normalized_events.json").read_text())
        classified[:] = [
            {
                **classified[0],
                "event_id": "evt-att",
                "source_id": "src-a",
                "priority": "low",
            }
        ]
        normalized[:] = [
            {
                **normalized[0],
                "event_id": "evt-att",
                "source_id": "src-a",
            }
        ]
        (newest / "classified_events.json").write_text(json.dumps(classified))
        (newest / "normalized_events.json").write_text(json.dumps(normalized))
        att_path = newest / "attachment_extraction.json"
        att = json.loads(att_path.read_text(encoding="utf-8"))
        att["items"] = [
            {
                "event_id": "evt-att",
                "filename": "legacy.pdf",
                "extraction_status": "refused",
                "is_refused": True,
            }
        ]
        att_path.write_text(json.dumps(att), encoding="utf-8")
        anchor_att_path = run_dir / "attachment_extraction.json"
        anchor_att = json.loads(anchor_att_path.read_text(encoding="utf-8"))
        anchor_att["items"] = []
        anchor_att["aggregate"]["refused_count"] = 0
        anchor_att_path.write_text(json.dumps(anchor_att), encoding="utf-8")

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "all",
            _null_logger(),
            "newest-run",
            aggregate_runs=True,
        )

        assert dashboard["business_kpi"]["attachment_refused"] == 1

    def test_legacy_attachment_source_less_ambiguous_no_double_count(
        self, run_dir: Path
    ) -> None:
        newest = _copy_run(run_dir, "newest-run")
        classified = json.loads((newest / "classified_events.json").read_text())
        normalized = json.loads((newest / "normalized_events.json").read_text())
        classified[:] = [
            {
                **classified[0],
                "event_id": "evt-att",
                "source_id": "src-a",
                "priority": "low",
            },
            {
                **classified[1],
                "event_id": "evt-att",
                "source_id": "src-b",
                "priority": "low",
            },
        ]
        normalized[:] = [
            {
                **normalized[0],
                "event_id": "evt-att",
                "source_id": "src-a",
            },
            {
                **normalized[1],
                "event_id": "evt-att",
                "source_id": "src-b",
            },
        ]
        (newest / "classified_events.json").write_text(json.dumps(classified))
        (newest / "normalized_events.json").write_text(json.dumps(normalized))
        att_path = newest / "attachment_extraction.json"
        att = json.loads(att_path.read_text(encoding="utf-8"))
        att["items"] = [
            {
                "event_id": "evt-att",
                "filename": "legacy.pdf",
                "extraction_status": "refused",
                "is_refused": True,
            }
        ]
        att_path.write_text(json.dumps(att), encoding="utf-8")
        anchor_att_path = run_dir / "attachment_extraction.json"
        anchor_att = json.loads(anchor_att_path.read_text(encoding="utf-8"))
        anchor_att["items"] = []
        anchor_att["aggregate"]["refused_count"] = 0
        anchor_att_path.write_text(json.dumps(anchor_att), encoding="utf-8")

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "all",
            _null_logger(),
            "newest-run",
            aggregate_runs=True,
        )

        assert dashboard["business_kpi"]["attachment_refused"] == 0

    def test_newer_non_rop_run_does_not_displace_latest_rop_anchor(
        self, run_dir: Path
    ) -> None:
        non_rop = run_dir.parents[1] / "runs" / "non-rop-latest"
        non_rop.mkdir(parents=True, exist_ok=True)
        (non_rop / "operator_summary.json").write_text(
            json.dumps({"status": "ok", "summary": "non-rop case"}),
            encoding="utf-8",
        )

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "all",
            _null_logger(),
            aggregate_runs=True,
        )

        assert dashboard["run_id"] == "test-dashboard-run"
        assert dashboard["business_kpi"]["processed_events"] == 3

    def test_explicit_anchor_wins_duplicate_with_tied_directory_mtimes(
        self, run_dir: Path
    ) -> None:
        anchor = _copy_run(run_dir, "anchor-run")
        old_normalized = json.loads((run_dir / "normalized_events.json").read_text())
        old_normalized[0]["message_id"] = "<tied@example.test>"
        (run_dir / "normalized_events.json").write_text(json.dumps(old_normalized))
        old_classified = json.loads((run_dir / "classified_events.json").read_text())
        old_classified[0]["priority"] = "low"
        (run_dir / "classified_events.json").write_text(json.dumps(old_classified))

        anchor_normalized = json.loads((anchor / "normalized_events.json").read_text())
        anchor_classified = json.loads((anchor / "classified_events.json").read_text())
        anchor_normalized[:] = [
            {
                **anchor_normalized[0],
                "event_id": "evt-tied",
                "message_id": "<tied@example.test>",
            }
        ]
        anchor_classified[:] = [
            {
                **anchor_classified[0],
                "event_id": "evt-tied",
                "priority": "high",
                "case_type": "new_lead",
            }
        ]
        (anchor / "normalized_events.json").write_text(json.dumps(anchor_normalized))
        (anchor / "classified_events.json").write_text(json.dumps(anchor_classified))
        anchor_reconciliation = json.loads(
            (anchor / "bitrix_reconciliation.json").read_text()
        )
        anchor_reconciliation["items"] = [
            {"event_id": "evt-tied", "bitrix_match_status": "matched_lead"}
        ]
        (anchor / "bitrix_reconciliation.json").write_text(
            json.dumps(anchor_reconciliation)
        )

        tied_mtime = 1_700_000_000
        os.utime(run_dir, (tied_mtime, tied_mtime))
        os.utime(anchor, (tied_mtime, tied_mtime))

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "all",
            _null_logger(),
            "anchor-run",
            aggregate_runs=True,
        )

        assert dashboard["business_kpi"]["processed_events"] == 3
        assert dashboard["business_kpi"]["matched_in_bitrix"] == 1
        tied_events = [
            item
            for item in dashboard["queues"]["high_priority"]
            if item["event_id"] == "evt-tied"
        ]
        assert len(tied_events) == 1
        assert tied_events[0]["run_id"] == "anchor-run"
        assert tied_events[0]["priority"] == "high"
        assert tied_events[0]["case_type"] == "new_lead"

    def test_default_rop_anchor_uses_logical_timestamp_with_tied_directory_mtimes(
        self, run_dir: Path
    ) -> None:
        newest = _copy_run(run_dir, "newest-run")
        for path, generated_at in (
            (run_dir, "2026-01-01T00:00:00Z"),
            (newest, "2026-01-02T00:00:00Z"),
        ):
            current_state = json.loads((path / "rop_current_state.json").read_text())
            current_state["generated_at_utc"] = generated_at
            (path / "rop_current_state.json").write_text(json.dumps(current_state))
            os.utime(path, (1_700_000_000, 1_700_000_000))

        non_rop = run_dir.parents[1] / "runs" / "non-rop-latest"
        non_rop.mkdir()
        os.utime(non_rop, (1_800_000_000, 1_800_000_000))

        dashboard = build_rop_dashboard(
            run_dir.parents[1], "all", _null_logger(), aggregate_runs=True
        )

        assert dashboard["run_id"] == "newest-run"

    def test_default_rop_anchor_uses_run_id_tiebreak_when_timestamps_match(
        self, run_dir: Path
    ) -> None:
        newest = _copy_run(run_dir, "newest-run")
        for path in (run_dir, newest):
            current_state = json.loads((path / "rop_current_state.json").read_text())
            current_state["generated_at_utc"] = "2026-01-01T00:00:00Z"
            (path / "rop_current_state.json").write_text(json.dumps(current_state))
            os.utime(path, (1_700_000_000, 1_700_000_000))

        dashboard = build_rop_dashboard(
            run_dir.parents[1], "all", _null_logger(), aggregate_runs=True
        )

        assert dashboard["run_id"] == "test-dashboard-run"

    def test_same_message_id_across_runs_with_shifted_instance_ids(
        self, run_dir: Path
    ) -> None:
        newest = _copy_run(run_dir, "newest-run")
        old_norm = json.loads((run_dir / "normalized_events.json").read_text())
        old_cls = json.loads((run_dir / "classified_events.json").read_text())
        old_norm[0].update(
            {
                "message_id": "<same@example.test>",
                "event_instance_id": "event-000001",
            }
        )
        old_cls[0]["event_instance_id"] = "event-000001"
        (run_dir / "normalized_events.json").write_text(json.dumps(old_norm))
        (run_dir / "classified_events.json").write_text(json.dumps(old_cls))

        new_norm = json.loads((newest / "normalized_events.json").read_text())
        new_cls = json.loads((newest / "classified_events.json").read_text())
        new_norm[:] = [
            {
                **new_norm[0],
                "event_id": "evt-new",
                "message_id": "<same@example.test>",
                "event_instance_id": "event-000010",
            }
        ]
        new_cls[:] = [
            {
                **new_cls[0],
                "event_id": "evt-new",
                "event_instance_id": "event-000010",
            }
        ]
        (newest / "normalized_events.json").write_text(json.dumps(new_norm))
        (newest / "classified_events.json").write_text(json.dumps(new_cls))

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "all",
            _null_logger(),
            "newest-run",
            aggregate_runs=True,
        )

        assert dashboard["business_kpi"]["processed_events"] == 3
        evt_new = [
            item
            for item in dashboard["queues"]["high_priority"]
            if item["event_id"] == "evt-new"
        ]
        assert len(evt_new) == 1
        assert evt_new[0]["run_id"] == "newest-run"
        assert not any(
            item["event_id"] == "evt-001"
            for item in dashboard["queues"]["high_priority"]
        )

    def test_keeps_three_occurrences_of_same_message_id_within_run(
        self, run_dir: Path
    ) -> None:
        norm = json.loads((run_dir / "normalized_events.json").read_text())
        cls = json.loads((run_dir / "classified_events.json").read_text())
        event_date = datetime.now(UTC).replace(microsecond=0).isoformat()
        base_norm = {
            "event_id": "triple",
            "source_id": "rop_batch_sample",
            "sender": "buyer@example.com",
            "subject": "RFQ welding wire",
            "message_id": "<triple@example.test>",
            "event_date": event_date,
        }
        base_cls = {
            "event_id": "triple",
            "source_id": "rop_batch_sample",
            "sender": "buyer@example.com",
            "subject": "RFQ welding wire",
            "case_type": "duplicate",
            "priority": "medium",
            "confidence": 0.9,
            "is_fallback": False,
            "reason_code": "duplicate_candidate_confirmed",
            "event_date": event_date,
        }
        norm[:] = [
            {**base_norm, "event_instance_id": f"event-00000{i}"} for i in (1, 2, 3)
        ]
        cls[:] = [
            {**base_cls, "event_instance_id": f"event-00000{i}"} for i in (1, 2, 3)
        ]
        (run_dir / "normalized_events.json").write_text(json.dumps(norm))
        (run_dir / "classified_events.json").write_text(json.dumps(cls))

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "all",
            _null_logger(),
            "test-dashboard-run",
            aggregate_runs=True,
        )

        assert dashboard["business_kpi"]["processed_events"] == 3
        nr_ids = [item["event_id"] for item in dashboard["queues"]["needs_review"]]
        assert nr_ids.count("triple") == 3

    def test_three_occurrences_across_two_runs_merge_to_three(
        self, run_dir: Path
    ) -> None:
        newest = _copy_run(run_dir, "newest-run")
        event_date = datetime.now(UTC).replace(microsecond=0).isoformat()
        base_norm = {
            "event_id": "triple",
            "source_id": "rop_batch_sample",
            "sender": "buyer@example.com",
            "subject": "RFQ welding wire",
            "message_id": "<triple@example.test>",
            "event_date": event_date,
        }
        base_cls = {
            "event_id": "triple",
            "source_id": "rop_batch_sample",
            "sender": "buyer@example.com",
            "subject": "RFQ welding wire",
            "case_type": "duplicate",
            "priority": "medium",
            "confidence": 0.9,
            "is_fallback": False,
            "reason_code": "duplicate_candidate_confirmed",
            "event_date": event_date,
        }
        for path, start in ((run_dir, 1), (newest, 10)):
            norm = json.loads((path / "normalized_events.json").read_text())
            cls = json.loads((path / "classified_events.json").read_text())
            norm[:] = [
                {**base_norm, "event_instance_id": f"event-{start + i:06d}"}
                for i in (1, 2, 3)
            ]
            cls[:] = [
                {**base_cls, "event_instance_id": f"event-{start + i:06d}"}
                for i in (1, 2, 3)
            ]
            (path / "normalized_events.json").write_text(json.dumps(norm))
            (path / "classified_events.json").write_text(json.dumps(cls))

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "all",
            _null_logger(),
            "newest-run",
            aggregate_runs=True,
        )

        assert dashboard["business_kpi"]["processed_events"] == 3
        nr_ids = [item["event_id"] for item in dashboard["queues"]["needs_review"]]
        assert nr_ids.count("triple") == 3
        assert {item["run_id"] for item in dashboard["queues"]["needs_review"]} == {
            "newest-run"
        }

    def test_x_email_id_fallback_identity_across_runs(self, run_dir: Path) -> None:
        newest = _copy_run(run_dir, "newest-run")
        old_norm = json.loads((run_dir / "normalized_events.json").read_text())
        old_cls = json.loads((run_dir / "classified_events.json").read_text())
        old_norm[0].update(
            {
                "message_id": None,
                "x_email_id": "x-123",
                "event_instance_id": "event-000001",
            }
        )
        old_cls[0]["event_instance_id"] = "event-000001"
        (run_dir / "normalized_events.json").write_text(json.dumps(old_norm))
        (run_dir / "classified_events.json").write_text(json.dumps(old_cls))

        new_norm = json.loads((newest / "normalized_events.json").read_text())
        new_cls = json.loads((newest / "classified_events.json").read_text())
        new_norm[:] = [
            {
                **new_norm[0],
                "event_id": "evt-new",
                "message_id": None,
                "x_email_id": "x-123",
                "event_instance_id": "event-000020",
            }
        ]
        new_cls[:] = [
            {**new_cls[0], "event_id": "evt-new", "event_instance_id": "event-000020"}
        ]
        (newest / "normalized_events.json").write_text(json.dumps(new_norm))
        (newest / "classified_events.json").write_text(json.dumps(new_cls))

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "all",
            _null_logger(),
            "newest-run",
            aggregate_runs=True,
        )

        assert dashboard["business_kpi"]["processed_events"] == 3
        evt_new = [
            item
            for item in dashboard["queues"]["high_priority"]
            if item["event_id"] == "evt-new"
        ]
        assert len(evt_new) == 1
        assert evt_new[0]["run_id"] == "newest-run"

    def test_event_id_fallback_identity_with_instance_ids(self, run_dir: Path) -> None:
        newest = _copy_run(run_dir, "newest-run")
        for path, instance_id in (
            (run_dir, "event-000001"),
            (newest, "event-000030"),
        ):
            norm = json.loads((path / "normalized_events.json").read_text())
            cls = json.loads((path / "classified_events.json").read_text())
            norm[:] = [
                {
                    **norm[0],
                    "event_id": "evt-001",
                    "message_id": None,
                    "event_instance_id": instance_id,
                }
            ]
            cls[:] = [
                {
                    **cls[0],
                    "event_id": "evt-001",
                    "event_instance_id": instance_id,
                    "priority": "high",
                }
            ]
            (path / "normalized_events.json").write_text(json.dumps(norm))
            (path / "classified_events.json").write_text(json.dumps(cls))

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "all",
            _null_logger(),
            "newest-run",
            aggregate_runs=True,
        )

        assert dashboard["business_kpi"]["processed_events"] == 1
        evt001 = [
            item
            for item in dashboard["queues"]["high_priority"]
            if item["event_id"] == "evt-001"
        ]
        assert len(evt001) == 1
        assert evt001[0]["run_id"] == "newest-run"

    def test_legacy_artifacts_without_instance_ids_keep_dedup(
        self, run_dir: Path
    ) -> None:
        newest = _copy_run(run_dir, "newest-run")
        old_norm = json.loads((run_dir / "normalized_events.json").read_text())
        old_cls = json.loads((run_dir / "classified_events.json").read_text())
        old_norm[0]["message_id"] = "<legacy@example.test>"
        (run_dir / "normalized_events.json").write_text(json.dumps(old_norm))
        (run_dir / "classified_events.json").write_text(json.dumps(old_cls))

        new_norm = json.loads((newest / "normalized_events.json").read_text())
        new_cls = json.loads((newest / "classified_events.json").read_text())
        new_norm[:] = [
            {
                **new_norm[0],
                "event_id": "evt-new",
                "message_id": "<legacy@example.test>",
                "event_instance_id": "event-000040",
            }
        ]
        new_cls[:] = [
            {**new_cls[0], "event_id": "evt-new", "event_instance_id": "event-000040"}
        ]
        (newest / "normalized_events.json").write_text(json.dumps(new_norm))
        (newest / "classified_events.json").write_text(json.dumps(new_cls))

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "all",
            _null_logger(),
            "newest-run",
            aggregate_runs=True,
        )

        assert dashboard["business_kpi"]["processed_events"] == 3
        evt_new = [
            item
            for item in dashboard["queues"]["high_priority"]
            if item["event_id"] == "evt-new"
        ]
        assert len(evt_new) == 1
        assert evt_new[0]["run_id"] == "newest-run"

    def test_source_isolation_with_same_instance_ids(self, run_dir: Path) -> None:
        newest = _copy_run(run_dir, "newest-run")
        event_date = datetime.now(UTC).replace(microsecond=0).isoformat()
        for path, source_id in (
            (run_dir, "rop_batch_sample"),
            (newest, "second_mailbox"),
        ):
            norm = json.loads((path / "normalized_events.json").read_text())
            cls = json.loads((path / "classified_events.json").read_text())
            norm[:] = [
                {
                    **norm[0],
                    "event_id": "shared-id",
                    "source_id": source_id,
                    "message_id": "<shared@example.test>",
                    "event_instance_id": "event-000001",
                    "event_date": event_date,
                }
            ]
            cls[:] = [
                {
                    **cls[0],
                    "event_id": "shared-id",
                    "source_id": source_id,
                    "event_instance_id": "event-000001",
                    "priority": "high",
                    "event_date": event_date,
                }
            ]
            (path / "normalized_events.json").write_text(json.dumps(norm))
            (path / "classified_events.json").write_text(json.dumps(cls))

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "all",
            _null_logger(),
            "newest-run",
            aggregate_runs=True,
        )

        hp = dashboard["queues"]["high_priority"]
        assert {(item["event_id"], item["source_id"]) for item in hp} == {
            ("shared-id", "rop_batch_sample"),
            ("shared-id", "second_mailbox"),
        }

    def test_queues_keep_duplicate_occurrences_with_same_event_id(
        self, run_dir: Path
    ) -> None:
        norm = json.loads((run_dir / "normalized_events.json").read_text())
        cls = json.loads((run_dir / "classified_events.json").read_text())
        event_date = datetime.now(UTC).replace(microsecond=0).isoformat()
        base_norm = {
            "event_id": "same-id",
            "source_id": "rop_batch_sample",
            "sender": "buyer@example.com",
            "subject": "RFQ welding wire",
            "event_date": event_date,
        }
        base_cls = {
            "event_id": "same-id",
            "source_id": "rop_batch_sample",
            "case_type": "duplicate",
            "priority": "medium",
            "confidence": 0.9,
            "is_fallback": False,
            "reason_code": "duplicate_candidate_confirmed",
            "event_date": event_date,
        }
        norm[:] = [
            {**base_norm, "event_instance_id": "event-000010"},
            {**base_norm, "event_instance_id": "event-000011"},
        ]
        cls[:] = [
            {**base_cls, "event_instance_id": "event-000010"},
            {**base_cls, "event_instance_id": "event-000011"},
        ]
        (run_dir / "normalized_events.json").write_text(json.dumps(norm))
        (run_dir / "classified_events.json").write_text(json.dumps(cls))

        dashboard = build_rop_dashboard(
            run_dir.parents[1],
            "all",
            _null_logger(),
            "test-dashboard-run",
            aggregate_runs=True,
        )

        nr = [
            item
            for item in dashboard["queues"]["needs_review"]
            if item["event_id"] == "same-id"
        ]
        assert len(nr) == 2
        assert {item["event_instance_id"] for item in nr} == {
            "event-000010",
            "event-000011",
        }

    def _write_identity_run(self, storage: Path, name: str, events: list[dict]) -> Path:
        rdir = storage / "runs" / name
        rdir.mkdir(parents=True, exist_ok=True)
        event_date = datetime.now(UTC).replace(microsecond=0).isoformat()
        normalized: list[dict] = []
        classified: list[dict] = []
        for evt in events:
            instance_id = str(evt.get("event_instance_id") or "")
            normalized.append(
                {
                    "event_id": evt["event_id"],
                    "source_id": evt["source_id"],
                    "sender": "buyer@example.com",
                    "subject": "RFQ welding wire",
                    "message_id": evt.get("message_id"),
                    "event_instance_id": instance_id,
                    "event_date": event_date,
                    "attachments": evt.get("attachments", []),
                }
            )
            classified.append(
                {
                    "event_id": evt["event_id"],
                    "source_id": evt["source_id"],
                    "sender": "buyer@example.com",
                    "subject": "RFQ welding wire",
                    "case_type": "new_lead",
                    "priority": "high",
                    "confidence": 0.9,
                    "is_fallback": False,
                    "reason_code": "new_lead_request_signal",
                    "event_instance_id": instance_id,
                    "event_date": event_date,
                }
            )
        (rdir / "normalized_events.json").write_text(json.dumps(normalized))
        (rdir / "classified_events.json").write_text(json.dumps(classified))
        sources = sorted({str(evt["source_id"]) for evt in events})
        source_items = [
            {"source_id": source, "client_id": "welding", "status": "ok"}
            for source in sources
        ]
        (rdir / "source_diagnostics.json").write_text(
            json.dumps(
                {"selection_mode": "multi", "sources": source_items},
            )
        )
        (rdir / "intake_metadata.json").write_text(
            json.dumps(
                {
                    "sources": source_items,
                    "loaded_item_count": len(events),
                }
            )
        )
        (rdir / "rop_current_state.json").write_text(
            json.dumps(
                {
                    "run_id": name,
                    "status": "ok",
                    "client_id": "welding",
                    "generated_at_utc": event_date,
                }
            )
        )
        (rdir / "operator_summary.json").write_text(
            json.dumps({"status": "ok", "module_status": "ok"})
        )
        return rdir

    def _write_attachment_run(
        self,
        storage: Path,
        name: str,
        events: list[dict],
        attachment_settings: dict,
    ) -> Path:
        from beeagent_module.core.attachment_extraction import (
            build_attachment_extraction,
        )

        rdir = self._write_identity_run(storage, name, events)
        normalized = json.loads((rdir / "normalized_events.json").read_text())
        artifact, _enriched = build_attachment_extraction(
            run_id=name,
            events=normalized,
            attachment_settings=attachment_settings,
        )
        (rdir / "attachment_extraction.json").write_text(json.dumps(artifact))
        return rdir

    def test_occurrence_slots_are_source_scoped_across_runs(
        self, tmp_path: Path
    ) -> None:
        self._write_identity_run(
            tmp_path,
            "run-old",
            [
                {
                    "event_id": "e-a",
                    "source_id": "source-a",
                    "message_id": "<X@example.test>",
                    "event_instance_id": "event-000001",
                },
                {
                    "event_id": "e-b",
                    "source_id": "source-b",
                    "message_id": "<X@example.test>",
                    "event_instance_id": "event-000002",
                },
            ],
        )
        self._write_identity_run(
            tmp_path,
            "run-new",
            [
                {
                    "event_id": "e-b2",
                    "source_id": "source-b",
                    "message_id": "<X@example.test>",
                    "event_instance_id": "event-000010",
                }
            ],
        )

        aggregate = rop_dashboard_module._aggregate_period_events(
            tmp_path / "runs", "run-new", "welding", _null_logger()
        )
        source_b = [
            event
            for event in aggregate["classified"]
            if event["source_id"] == "source-b"
        ]
        assert len(source_b) == 1
        assert source_b[0]["_dashboard_origin_run_id"] == "run-new"

    def test_occurrence_slots_source_scoped_with_reordered_sources(
        self, tmp_path: Path
    ) -> None:
        self._write_identity_run(
            tmp_path,
            "run-old",
            [
                {
                    "event_id": "e-b",
                    "source_id": "source-b",
                    "message_id": "<X@example.test>",
                    "event_instance_id": "event-000001",
                },
                {
                    "event_id": "e-a",
                    "source_id": "source-a",
                    "message_id": "<X@example.test>",
                    "event_instance_id": "event-000002",
                },
            ],
        )
        self._write_identity_run(
            tmp_path,
            "run-new",
            [
                {
                    "event_id": "e-a2",
                    "source_id": "source-a",
                    "message_id": "<X@example.test>",
                    "event_instance_id": "event-000020",
                }
            ],
        )

        aggregate = rop_dashboard_module._aggregate_period_events(
            tmp_path / "runs", "run-new", "welding", _null_logger()
        )
        source_a = [
            event
            for event in aggregate["classified"]
            if event["source_id"] == "source-a"
        ]
        assert len(source_a) == 1
        assert source_a[0]["_dashboard_origin_run_id"] == "run-new"

    def test_two_occurrences_source_b_dedup_with_new_run(self, tmp_path: Path) -> None:
        def _triple(start: int) -> list[dict]:
            return [
                {
                    "event_id": "triple",
                    "source_id": "source-b",
                    "message_id": "<triple@example.test>",
                    "event_instance_id": f"event-{start:06d}",
                },
                {
                    "event_id": "triple",
                    "source_id": "source-b",
                    "message_id": "<triple@example.test>",
                    "event_instance_id": f"event-{start + 1:06d}",
                },
            ]

        self._write_identity_run(tmp_path, "run-old", _triple(1))
        self._write_identity_run(tmp_path, "run-new", _triple(10))

        aggregate = rop_dashboard_module._aggregate_period_events(
            tmp_path / "runs", "run-new", "welding", _null_logger()
        )
        assert len(aggregate["classified"]) == 2
        assert all(
            event["_dashboard_origin_run_id"] == "run-new"
            for event in aggregate["classified"]
        )

    def test_period_aggregation_preserves_occurrence_attachment_items(
        self, tmp_path: Path
    ) -> None:
        attachment_settings = {
            "enabled": True,
            "chars_max": 120,
            "size_max": 4096,
            "types": ["text/plain", "application/json"],
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
        }
        self._write_attachment_run(
            tmp_path,
            "run-att",
            [
                {
                    "event_id": "same-id",
                    "source_id": "rop_batch_sample",
                    "message_id": "<same@example.test>",
                    "event_instance_id": "event-000001",
                    "attachments": [
                        {
                            "attachment_id": "att-1",
                            "filename": "a.txt",
                            "content_type": "text/plain",
                            "size_bytes": 20,
                            "text_preview": "alpha",
                        }
                    ],
                },
                {
                    "event_id": "same-id",
                    "source_id": "rop_batch_sample",
                    "message_id": "<same@example.test>",
                    "event_instance_id": "event-000002",
                    "attachments": [
                        {
                            "attachment_id": "att-2",
                            "filename": "b.txt",
                            "content_type": "text/plain",
                            "size_bytes": 20,
                            "text_preview": "beta",
                        }
                    ],
                },
            ],
            attachment_settings,
        )

        aggregate = rop_dashboard_module._aggregate_period_events(
            tmp_path / "runs", "run-att", "welding", _null_logger()
        )
        assert len(aggregate["classified"]) == 2
        items = aggregate["attachment_extraction"]["items"]
        assert {item["event_instance_id"] for item in items} == {
            "event-000001",
            "event-000002",
        }
        by_instance = {item["event_instance_id"]: item for item in items}
        assert by_instance["event-000001"]["filename"] == "a.txt"
        assert by_instance["event-000002"]["filename"] == "b.txt"

    def test_legacy_ambiguous_attachment_not_bound_to_multiple_occurrences(
        self, tmp_path: Path
    ) -> None:
        self._write_identity_run(
            tmp_path,
            "run-legacy",
            [
                {
                    "event_id": "same-id",
                    "source_id": "rop_batch_sample",
                    "message_id": "<same@example.test>",
                },
                {
                    "event_id": "same-id",
                    "source_id": "rop_batch_sample",
                    "message_id": "<same@example.test>",
                },
            ],
        )
        rdir = tmp_path / "runs" / "run-legacy"
        artifact = {
            "run_id": "run-legacy",
            "status": "ok",
            "aggregate": {
                "event_count": 2,
                "attachment_count": 1,
                "refused_count": 0,
                "preview_available_count": 0,
                "metadata_only_count": 1,
                "unsupported_count": 0,
                "failed_count": 0,
            },
            "items": [
                {
                    "event_id": "same-id",
                    "source_id": "rop_batch_sample",
                    "event_instance_id": "",
                    "filename": "legacy.txt",
                    "content_type": "text/plain",
                    "extraction_status": "metadata_only",
                    "is_refused": False,
                }
            ],
        }
        (rdir / "attachment_extraction.json").write_text(json.dumps(artifact))

        aggregate = rop_dashboard_module._aggregate_period_events(
            tmp_path / "runs", "run-legacy", "welding", _null_logger()
        )
        assert len(aggregate["classified"]) == 2
        assert aggregate["attachment_extraction"]["items"] == []

    def test_refused_attachment_count_is_occurrence_aware(self, tmp_path: Path) -> None:
        self._write_identity_run(
            tmp_path,
            "run-refused-inst",
            [
                {
                    "event_id": "same-id",
                    "source_id": "rop_batch_sample",
                    "message_id": "<same@example.test>",
                    "event_instance_id": "event-000001",
                },
                {
                    "event_id": "same-id",
                    "source_id": "rop_batch_sample",
                    "message_id": "<same@example.test>",
                    "event_instance_id": "event-000002",
                },
            ],
        )
        rdir = tmp_path / "runs" / "run-refused-inst"
        artifact = {
            "run_id": "run-refused-inst",
            "status": "ok",
            "aggregate": {
                "event_count": 2,
                "attachment_count": 2,
                "refused_count": 2,
                "preview_available_count": 0,
                "metadata_only_count": 0,
                "unsupported_count": 0,
                "failed_count": 0,
            },
            "items": [
                {
                    "event_id": "same-id",
                    "source_id": "rop_batch_sample",
                    "event_instance_id": "event-000001",
                    "filename": "first.pdf",
                    "content_type": "application/pdf",
                    "extraction_status": "refused",
                    "is_refused": True,
                },
                {
                    "event_id": "same-id",
                    "source_id": "rop_batch_sample",
                    "event_instance_id": "event-000002",
                    "filename": "second.pdf",
                    "content_type": "application/pdf",
                    "extraction_status": "refused",
                    "is_refused": True,
                },
            ],
        }
        (rdir / "attachment_extraction.json").write_text(json.dumps(artifact))

        aggregate = rop_dashboard_module._aggregate_period_events(
            tmp_path / "runs", "run-refused-inst", "welding", _null_logger()
        )
        business_kpi = rop_dashboard_module._build_business_kpi(
            classified_list=aggregate["classified"],
            normalized_list=aggregate["normalized"],
            bitrix_state={},
            source_diag={},
            attachment_extraction=aggregate["attachment_extraction"],
        )
        assert business_kpi["attachment_refused"] == 2

    def test_attachment_item_requires_instance_to_bind_repeated_event(
        self, tmp_path: Path
    ) -> None:
        self._write_identity_run(
            tmp_path,
            "run-inst-bound",
            [
                {
                    "event_id": "same-id",
                    "source_id": "rop_batch_sample",
                    "message_id": "<same@example.test>",
                    "event_instance_id": "event-000001",
                },
                {
                    "event_id": "same-id",
                    "source_id": "rop_batch_sample",
                    "message_id": "<same@example.test>",
                    "event_instance_id": "event-000002",
                },
            ],
        )
        rdir = tmp_path / "runs" / "run-inst-bound"
        artifact = {
            "run_id": "run-inst-bound",
            "status": "ok",
            "aggregate": {
                "event_count": 2,
                "attachment_count": 1,
                "refused_count": 0,
                "preview_available_count": 0,
                "metadata_only_count": 1,
                "unsupported_count": 0,
                "failed_count": 0,
            },
            "items": [
                {
                    "event_id": "same-id",
                    "source_id": "rop_batch_sample",
                    "event_instance_id": "event-000001",
                    "filename": "first.txt",
                    "content_type": "text/plain",
                    "extraction_status": "metadata_only",
                    "is_refused": False,
                }
            ],
        }
        (rdir / "attachment_extraction.json").write_text(json.dumps(artifact))

        aggregate = rop_dashboard_module._aggregate_period_events(
            tmp_path / "runs", "run-inst-bound", "welding", _null_logger()
        )
        items = aggregate["attachment_extraction"]["items"]
        assert len(items) == 1
        assert items[0]["event_instance_id"] == "event-000001"


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    """Create a minimal run directory with artifacts for dashboard testing."""
    rdir = tmp_path / "runs" / "test-dashboard-run"
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

    def test_duplicate_rows_enter_needs_review_queue(
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
        assert "evt-dup-in-queue" in review_ids
        assert dashboard["status"] == "ok"

    def test_medium_non_fallback_duplicate_counts_in_needs_review_kpi(
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
        assert bkpi["needs_review"] == 3
        assert any(
            item["event_id"] == "evt-dup-kpi"
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


class TestRopWebProjectionLifecycle:
    def _storage_with_runs(self, source: Path, target: Path, count: int) -> Path:
        storage_dir = target / "storage"
        runs_dir = storage_dir / "runs"
        runs_dir.mkdir(parents=True)
        for index in range(count):
            shutil.copytree(source, runs_dir / f"run-many-{index:03d}")
        return storage_dir

    def test_full_regeneration_reuses_history_for_all_periods(
        self, run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        storage_dir = self._storage_with_runs(run_dir, tmp_path / "many", 12)
        aggregate_calls = 0
        run_enumerations = 0
        original_aggregate = rop_dashboard_module._aggregate_period_events
        original_list_runs = rop_dashboard_module._list_run_ids

        def counted_aggregate(
            runs_dir: Path,
            anchor_run_id: str,
            anchor_client_id: str,
            logger: logging.Logger,
        ) -> dict[str, Any]:
            nonlocal aggregate_calls
            aggregate_calls += 1
            return original_aggregate(
                runs_dir,
                anchor_run_id,
                anchor_client_id,
                logger,
            )

        def counted_list_runs(runs_dir: Path) -> list[str]:
            nonlocal run_enumerations
            run_enumerations += 1
            return original_list_runs(runs_dir)

        monkeypatch.setattr(
            rop_dashboard_module, "_aggregate_period_events", counted_aggregate
        )
        monkeypatch.setattr(rop_dashboard_module, "_list_run_ids", counted_list_runs)

        projection = rop_dashboard_module.build_rop_web_projection(
            storage_dir,
            list(rop_dashboard_module.ALLOWED_PERIODS),
            _null_logger(),
        )

        assert aggregate_calls == 12
        assert run_enumerations == 13
        assert projection["total_runs"] == 12
        assert len(projection["run_ids"]) == 12
        assert set(projection["dashboards"][projection["run_ids"][0]]) == set(
            rop_dashboard_module.ALLOWED_PERIODS
        )

    def test_full_regeneration_scales_linearly_with_historical_runs(
        self, run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        small_storage = self._storage_with_runs(run_dir, tmp_path / "small", 8)
        large_storage = self._storage_with_runs(run_dir, tmp_path / "large", 16)
        read_calls = 0
        aggregate_calls = 0
        original_read_dict = rop_dashboard_module._read_json_dict
        original_read_list = rop_dashboard_module._read_json_list
        original_aggregate = rop_dashboard_module._aggregate_period_events

        def counted_read_dict(path: Path) -> dict[str, Any] | None:
            nonlocal read_calls
            read_calls += 1
            return original_read_dict(path)

        def counted_read_list(path: Path) -> list[dict[str, Any]] | None:
            nonlocal read_calls
            read_calls += 1
            return original_read_list(path)

        def counted_aggregate(
            runs_dir: Path,
            anchor_run_id: str,
            anchor_client_id: str,
            logger: logging.Logger,
        ) -> dict[str, Any]:
            nonlocal aggregate_calls
            aggregate_calls += 1
            return original_aggregate(
                runs_dir,
                anchor_run_id,
                anchor_client_id,
                logger,
            )

        monkeypatch.setattr(rop_dashboard_module, "_read_json_dict", counted_read_dict)
        monkeypatch.setattr(rop_dashboard_module, "_read_json_list", counted_read_list)
        monkeypatch.setattr(
            rop_dashboard_module, "_aggregate_period_events", counted_aggregate
        )

        rop_dashboard_module.build_rop_web_projection(
            small_storage, list(rop_dashboard_module.ALLOWED_PERIODS), _null_logger()
        )
        small_reads = read_calls
        rop_dashboard_module.build_rop_web_projection(
            large_storage, list(rop_dashboard_module.ALLOWED_PERIODS), _null_logger()
        )
        large_reads = read_calls - small_reads

        assert aggregate_calls == 24
        assert large_reads <= small_reads * 4

    def test_configured_periods_reuse_loaded_projection_artifacts(
        self, run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        storage_dir = self._storage_with_runs(run_dir, tmp_path / "periods", 6)
        read_calls = 0
        aggregate_calls = 0
        original_read_dict = rop_dashboard_module._read_json_dict
        original_read_list = rop_dashboard_module._read_json_list
        original_aggregate = rop_dashboard_module._aggregate_period_events

        def counted_read_dict(path: Path) -> dict[str, Any] | None:
            nonlocal read_calls
            read_calls += 1
            return original_read_dict(path)

        def counted_read_list(path: Path) -> list[dict[str, Any]] | None:
            nonlocal read_calls
            read_calls += 1
            return original_read_list(path)

        def counted_aggregate(
            runs_dir: Path,
            anchor_run_id: str,
            anchor_client_id: str,
            logger: logging.Logger,
        ) -> dict[str, Any]:
            nonlocal aggregate_calls
            aggregate_calls += 1
            return original_aggregate(
                runs_dir,
                anchor_run_id,
                anchor_client_id,
                logger,
            )

        monkeypatch.setattr(rop_dashboard_module, "_read_json_dict", counted_read_dict)
        monkeypatch.setattr(rop_dashboard_module, "_read_json_list", counted_read_list)
        monkeypatch.setattr(
            rop_dashboard_module, "_aggregate_period_events", counted_aggregate
        )

        rop_dashboard_module.build_rop_web_projection(
            storage_dir, ["all"], _null_logger()
        )
        one_period_reads = read_calls
        rop_dashboard_module.build_rop_web_projection(
            storage_dir, list(rop_dashboard_module.ALLOWED_PERIODS), _null_logger()
        )
        all_period_reads = read_calls - one_period_reads

        assert aggregate_calls == 12
        assert all_period_reads <= one_period_reads + 2

    def test_normal_refresh_updates_one_entry_without_catalog_rebuild(
        self, run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        storage_dir = self._storage_with_runs(run_dir, tmp_path / "incremental", 3)
        projection = rop_dashboard_module.build_rop_web_projection(
            storage_dir, list(rop_dashboard_module.ALLOWED_PERIODS), _null_logger()
        )
        rop_dashboard_module.write_rop_web_projection(
            storage_dir, projection, _null_logger()
        )
        shutil.copytree(run_dir, storage_dir / "runs" / "run-new")
        aggregate_calls = 0
        original_aggregate = rop_dashboard_module._aggregate_period_events

        def counted_aggregate(
            runs_dir: Path,
            anchor_run_id: str,
            anchor_client_id: str,
            logger: logging.Logger,
        ) -> dict[str, Any]:
            nonlocal aggregate_calls
            aggregate_calls += 1
            return original_aggregate(
                runs_dir,
                anchor_run_id,
                anchor_client_id,
                logger,
            )

        def fail_catalog_enumeration(*_args: object, **_kwargs: object) -> list[str]:
            raise AssertionError("normal refresh must not rebuild the full catalog")

        monkeypatch.setattr(
            rop_dashboard_module, "_aggregate_period_events", counted_aggregate
        )
        monkeypatch.setattr(
            rop_dashboard_module, "_list_rop_run_ids", fail_catalog_enumeration
        )

        refreshed = rop_dashboard_module.refresh_rop_web_projection(
            storage_dir,
            list(rop_dashboard_module.ALLOWED_PERIODS),
            "run-new",
            _null_logger(),
        )

        index = rop_dashboard_module.rop_web_projection_index(storage_dir)
        assert refreshed is True
        assert aggregate_calls == 1
        assert index is not None
        assert index["latest_run_id"] == "run-new"
        assert index["total_runs"] == 4
        assert rop_dashboard_module.rop_web_projection_entry_path(
            storage_dir, "run-new"
        ).exists()
        manifest = rop_dashboard_module.rop_web_projection_v2_manifest(storage_dir)
        assert manifest is not None
        assert manifest["run_ids"] == index["run_ids"]
        assert manifest["total_runs"] == index["total_runs"]
        assert (
            rop_dashboard_module.read_rop_web_projection_v2_view(
                storage_dir, manifest, "run-new", "api", "all"
            )
            is not None
        )

    def test_missing_projection_stays_unavailable_until_bootstrap(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        storage_dir = self._storage_with_runs(run_dir, tmp_path / "missing", 3)

        refreshed = rop_dashboard_module.refresh_rop_web_projection(
            storage_dir,
            list(rop_dashboard_module.ALLOWED_PERIODS),
            "run-many-000",
            _null_logger(),
        )

        assert refreshed is False
        assert rop_dashboard_module.rop_web_projection_index(storage_dir) is None

    @pytest.mark.parametrize(
        "malformed_index",
        (
            {"total_runs": None},
            {"total_runs": True},
            {"total_runs": "3"},
            {"run_ids": []},
            {"run_ids": ["run-many-000"] * 21},
        ),
    )
    def test_malformed_index_prevents_refresh_without_artifact_mutation(
        self,
        run_dir: Path,
        tmp_path: Path,
        malformed_index: dict[str, object],
    ) -> None:
        storage_dir = self._storage_with_runs(run_dir, tmp_path / "malformed", 1)
        projection = rop_dashboard_module.build_rop_web_projection(
            storage_dir, ["7d"], _null_logger()
        )
        rop_dashboard_module.write_rop_web_projection(
            storage_dir, projection, _null_logger()
        )
        index_path = storage_dir / "interfaces" / "rop_web_projection.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index.update(malformed_index)
        index_path.write_text(json.dumps(index), encoding="utf-8")
        entry_path = rop_dashboard_module.rop_web_projection_entry_path(
            storage_dir, "run-many-000"
        )
        before_index = index_path.read_bytes()
        before_entry = entry_path.read_bytes()

        assert rop_dashboard_module.rop_web_projection_index(storage_dir) is None
        assert (
            rop_dashboard_module.refresh_rop_web_projection(
                storage_dir,
                ["7d"],
                "run-many-000",
                _null_logger(),
                is_new_run=False,
            )
            is False
        )
        assert index_path.read_bytes() == before_index
        assert entry_path.read_bytes() == before_entry

    def test_existing_run_refresh_preserves_catalog_scalar(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        storage_dir = self._storage_with_runs(run_dir, tmp_path / "existing", 3)
        projection = rop_dashboard_module.build_rop_web_projection(
            storage_dir, ["7d"], _null_logger()
        )
        rop_dashboard_module.write_rop_web_projection(
            storage_dir, projection, _null_logger()
        )
        before = rop_dashboard_module.rop_web_projection_index(storage_dir)

        refreshed = rop_dashboard_module.refresh_rop_web_projection(
            storage_dir,
            ["7d"],
            "run-many-000",
            _null_logger(),
            is_new_run=False,
        )

        after = rop_dashboard_module.rop_web_projection_index(storage_dir)
        assert refreshed is True
        assert before is not None
        assert after is not None
        assert after["run_ids"] == before["run_ids"]
        assert after["total_runs"] == before["total_runs"]

    def test_failed_publication_keeps_previous_index_valid(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        storage_dir = self._storage_with_runs(run_dir, tmp_path / "atomic", 1)
        projection = rop_dashboard_module.build_rop_web_projection(
            storage_dir, ["7d"], _null_logger()
        )
        rop_dashboard_module.write_rop_web_projection(
            storage_dir, projection, _null_logger()
        )
        before = rop_dashboard_module.rop_web_projection_index(storage_dir)

        with pytest.raises(ValueError):
            rop_dashboard_module.write_rop_web_projection(
                storage_dir,
                {
                    "schema_version": 1,
                    "run_ids": ["run-missing"],
                    "total_runs": 1,
                    "dashboards": {},
                },
                _null_logger(),
            )

        assert rop_dashboard_module.rop_web_projection_index(storage_dir) == before

    def test_full_projection_preserves_selected_run_anchor_semantics(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        storage_dir = self._storage_with_runs(run_dir, tmp_path / "anchors", 2)
        first = storage_dir / "runs" / "run-many-000"
        second = storage_dir / "runs" / "run-many-001"

        for path, generated_at, priority, case_type, bitrix_status in (
            (first, "2026-01-01T00:00:00Z", "high", "new_lead", "matched_lead"),
            (second, "2026-01-02T00:00:00Z", "low", "existing_deal", "not_found"),
        ):
            normalized = json.loads((path / "normalized_events.json").read_text())
            normalized[0]["message_id"] = "<tied@example.test>"
            (path / "normalized_events.json").write_text(json.dumps(normalized))
            classified = json.loads((path / "classified_events.json").read_text())
            classified[0]["priority"] = priority
            classified[0]["case_type"] = case_type
            (path / "classified_events.json").write_text(json.dumps(classified))
            reconciliation = json.loads(
                (path / "bitrix_reconciliation.json").read_text()
            )
            reconciliation["items"] = [
                {"event_id": "evt-001", "bitrix_match_status": bitrix_status}
            ]
            (path / "bitrix_reconciliation.json").write_text(json.dumps(reconciliation))
            current_state = json.loads((path / "rop_current_state.json").read_text())
            current_state["generated_at_utc"] = generated_at
            (path / "rop_current_state.json").write_text(json.dumps(current_state))

        projection = rop_dashboard_module.build_rop_web_projection(
            storage_dir, ["all"], _null_logger()
        )

        assert projection["run_ids"] == ["run-many-001", "run-many-000"]

        for candidate_run_id in projection["run_ids"]:
            entry = projection["dashboards"][candidate_run_id]["all"]
            direct = build_rop_dashboard(
                storage_dir,
                "all",
                _null_logger(),
                run_id=candidate_run_id,
                aggregate_runs=True,
            )
            assert entry["business_kpi"] == direct["business_kpi"]
            assert entry["queues"] == direct["queues"]
            assert entry["series"] == direct["series"]
            assert entry["evidence_links"] == direct["evidence_links"]
            assert entry["run_id"] == candidate_run_id

        first_entry = projection["dashboards"]["run-many-000"]["all"]
        tied = [
            item
            for item in first_entry["queues"]["high_priority"]
            if item["event_id"] == "evt-001"
        ]
        assert len(tied) == 1
        assert tied[0]["run_id"] == "run-many-000"
        assert tied[0]["priority"] == "high"
        assert tied[0]["case_type"] == "new_lead"

        second_entry = projection["dashboards"]["run-many-001"]["all"]
        lost = [
            item
            for item in second_entry["queues"]["lost_in_bitrix"]
            if item["event_id"] == "evt-001"
        ]
        assert len(lost) == 1
        assert lost[0]["run_id"] == "run-many-001"
        assert lost[0]["priority"] == "low"
        assert lost[0]["case_type"] == "existing_deal"


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

    def test_validate_filter_params_accepts_duplicate_aliases(self) -> None:
        errors = rop_dashboard_module.validate_filter_params(
            {"classification": "duplicate", "case_type": "duplicate"}
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
        errors = rop_dashboard_module.validate_filter_params({"priority": "urgent"})
        assert any("Invalid priority" in e for e in errors)

    def test_validate_filter_params_rejects_bad_bitrix_status(self) -> None:
        errors = rop_dashboard_module.validate_filter_params(
            {"bitrix_status": "non_existent"}
        )
        assert any("Invalid bitrix_status" in e for e in errors)

    def test_validate_filter_params_rejects_bad_is_fallback(self) -> None:
        errors = rop_dashboard_module.validate_filter_params({"is_fallback": "maybe"})
        assert any("Invalid is_fallback" in e for e in errors)

    def test_validate_filter_params_accepts_is_fallback(self) -> None:
        errors = rop_dashboard_module.validate_filter_params({"is_fallback": "true"})
        assert errors == []
        errors = rop_dashboard_module.validate_filter_params({"is_fallback": "false"})
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


def test_v2_canonical_queue_rows_keep_same_event_id_sources_isolated() -> None:
    queues = {
        "high_priority": [
            {
                "run_id": "run-1",
                "source_id": "source-a",
                "event_id": "shared",
                "event_instance_id": "instance-a",
            },
            {
                "run_id": "run-1",
                "source_id": "source-b",
                "event_id": "shared",
                "event_instance_id": "instance-b",
            },
        ]
    }
    attention_events = [
        {
            **queues["high_priority"][0],
            "sender": "a@example.com",
            "subject": "Source A",
        },
        {
            **queues["high_priority"][1],
            "sender": "b@example.com",
            "subject": "Source B",
        },
    ]

    rows = rop_dashboard_module._v2_canonical_queue_rows(
        queues,
        attention_events,
        lambda *_args: [dict(item) for item in queues["high_priority"]],
    )

    assert [(row["source_id"], row["sender"], row["subject"]) for row in rows] == [
        ("source-a", "a@example.com", "Source A"),
        ("source-b", "b@example.com", "Source B"),
    ]


def test_v2_overview_action_required_count_is_exact_while_preview_is_bounded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    rows = [
        {
            "run_id": "run-1",
            "source_id": "source-a",
            "event_id": f"event-{number}",
            "event_instance_id": f"instance-{number}",
        }
        for number in range(30)
    ]
    source_data = {
        "business_kpi": {},
        "series": {},
        "queues": {"high_priority": rows, "needs_review": [dict(rows[0])]},
        "attention_events": rows,
        "filter_options": {},
        "thread_summary": {},
        "threads": [],
        "ai_assist_summary": {},
        "ai_assist_events": [],
        "source_health": [],
        "attachment_summary": {},
        "evidence_links": [],
        "delivery_recommendations": {},
        "bitrix": {},
    }

    def source_model(*_args: object, **kwargs: object) -> dict[str, object]:
        if kwargs.get("tab") == "bitrix":
            return {"business_kpi": {}, "queues": {}, "bitrix": {}}
        return dict(source_data)

    monkeypatch.setattr(
        "beeagent_module.interfaces.ui.read_model._build_rop_tab_read_model_legacy",
        source_model,
    )
    monkeypatch.setattr(
        "beeagent_module.interfaces.ui.read_model._canonical_queue_rows",
        lambda *_args: [dict(item) for item in rows],
    )

    views = rop_dashboard_module.build_rop_web_projection_v2_views(
        tmp_path, "run-1", ["all"]
    )

    overview = views["overview.all"]
    assert overview["action_required_count"] == 30
    assert len(overview["priority_preview"]["high_priority"]) == 25


def test_v2_writer_rejects_incomplete_views_before_manifest_publication(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    interfaces = tmp_path / "interfaces"
    interfaces.mkdir()
    manifest_path = interfaces / "rop_web_projection_v2.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "generated_at_utc": "2026-01-01T00:00:00Z",
                "generation": "g_existing",
                "latest_run_id": "run-1",
                "run_ids": ["run-1"],
                "total_runs": 1,
                "runs": {
                    "run-1": {
                        "generation": "g_existing",
                        "revision": "r_existing",
                        "view_keys": ["api.7d"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    before = manifest_path.read_bytes()
    monkeypatch.setattr(
        rop_dashboard_module,
        "build_rop_web_projection_v2_views",
        lambda *_args: {"api.7d": {}},
    )

    with pytest.raises(ValueError, match="incomplete or uncontrolled"):
        rop_dashboard_module.write_rop_web_projection_v2(
            tmp_path,
            ["run-1"],
            1,
            {"run-1": ["7d"]},
            _null_logger(),
        )

    assert manifest_path.read_bytes() == before


def _projection_for_runs(run_ids: list[str]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "generated_at_utc": "2026-01-01T00:00:00Z",
        "run_ids": run_ids,
        "total_runs": len(run_ids),
        "dashboards": {run_id: {"7d": {"status": "ok"}} for run_id in run_ids},
    }


def _v2_views(
    _storage_dir: Path, _run_id: str, periods: list[str]
) -> dict[str, dict[str, object]]:
    payloads: dict[str, dict[str, object]] = {}
    for view_key in rop_dashboard_module._v2_required_view_keys(periods):
        if view_key.startswith("overview."):
            payloads[view_key] = {
                "business_kpi": {},
                "series": {},
                "priority_preview": {},
                "action_required_count": 0,
            }
        elif view_key.startswith("bitrix."):
            payloads[view_key] = {"business_kpi": {}, "queues": {}, "bitrix": {}}
        elif view_key.startswith("api."):
            payloads[view_key] = {
                "business_kpi": {},
                "series": {},
                "queues": {},
                "canonical_queue_rows": [],
            }
        elif view_key == "queue":
            payloads[view_key] = {"queue_rows": [], "filter_options": {}}
        elif view_key == "threads":
            payloads[view_key] = {"thread_summary": {}, "threads": []}
        elif view_key == "ai_assist":
            payloads[view_key] = {"ai_assist_summary": {}, "ai_assist_events": []}
        elif view_key == "sources":
            payloads[view_key] = {"source_health": []}
        elif view_key == "attachments":
            payloads[view_key] = {"attachment_summary": {}}
        elif view_key == "evidence":
            payloads[view_key] = {"evidence_links": []}
        else:
            payloads[view_key] = {"delivery_recommendations": {}}
    return payloads


def test_v1_projection_gc_keeps_current_and_previous_entries_and_bounds_storage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        rop_dashboard_module, "write_rop_web_projection_v2", lambda **_: None
    )
    storage_dir = tmp_path / "storage"
    projection_dir = storage_dir / "interfaces" / "rop_web_projection"
    projection_dir.mkdir(parents=True)
    stale = rop_dashboard_module.rop_web_projection_entry_path(storage_dir, "stale")
    stale.write_text("{}", encoding="utf-8")
    unknown = projection_dir / "operator-note.txt"
    unknown.write_text("keep", encoding="utf-8")
    temporary = projection_dir / "unrelated.json.tmp"
    temporary.write_text("keep", encoding="utf-8")
    target = tmp_path / "symlink-target.json"
    target.write_text("keep", encoding="utf-8")
    symlink = rop_dashboard_module.rop_web_projection_entry_path(storage_dir, "link")
    symlink.symlink_to(target)
    run_artifact = storage_dir / "runs" / "run-1" / "canonical.json"
    attachment = storage_dir / "attachments" / "run-1" / "attachment.bin"
    unrelated = storage_dir / "interfaces" / "other.json"
    for path in (run_artifact, attachment, unrelated):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("keep", encoding="utf-8")

    rop_dashboard_module.write_rop_web_projection(
        storage_dir, _projection_for_runs(["a", "b"]), _null_logger()
    )
    assert not stale.exists()
    assert symlink.is_symlink()
    assert target.read_text(encoding="utf-8") == "keep"
    assert unknown.exists()
    assert temporary.exists()
    assert all(path.exists() for path in (run_artifact, attachment, unrelated))

    rop_dashboard_module.write_rop_web_projection(
        storage_dir, _projection_for_runs(["c", "b"]), _null_logger()
    )
    assert all(
        rop_dashboard_module.rop_web_projection_entry_path(storage_dir, run_id).exists()
        for run_id in ("a", "b", "c")
    )
    rop_dashboard_module.write_rop_web_projection(
        storage_dir, _projection_for_runs(["d", "c"]), _null_logger()
    )
    assert not rop_dashboard_module.rop_web_projection_entry_path(
        storage_dir, "a"
    ).exists()
    assert all(
        rop_dashboard_module.rop_web_projection_entry_path(storage_dir, run_id).exists()
        for run_id in ("b", "c", "d")
    )

    for number in range(30):
        rop_dashboard_module.write_rop_web_projection(
            storage_dir,
            _projection_for_runs([f"run-{number}", f"run-{number + 1}"]),
            _null_logger(),
        )
    controlled_entries = [
        path
        for path in projection_dir.iterdir()
        if path.is_file()
        and rop_dashboard_module._ROP_WEB_PROJECTION_ENTRY_RE.fullmatch(path.name)
    ]
    assert len(controlled_entries) <= 4


def test_v1_projection_gc_failure_preserves_published_index(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        rop_dashboard_module, "write_rop_web_projection_v2", lambda **_: None
    )
    storage_dir = tmp_path / "storage"
    rop_dashboard_module.write_rop_web_projection(
        storage_dir, _projection_for_runs(["old"]), _null_logger()
    )
    stale = rop_dashboard_module.rop_web_projection_entry_path(storage_dir, "stale")
    stale.write_text("{}", encoding="utf-8")
    original_unlink = Path.unlink

    def failing_unlink(path: Path, missing_ok: bool = False) -> None:
        if path == stale:
            raise OSError("simulated cleanup failure")
        original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", failing_unlink)
    rop_dashboard_module.write_rop_web_projection(
        storage_dir, _projection_for_runs(["new"]), _null_logger()
    )

    index = rop_dashboard_module.rop_web_projection_index(storage_dir)
    assert index is not None
    assert index["run_ids"] == ["new"]
    assert stale.exists()


def test_v2_projection_gc_keeps_current_previous_and_safe_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        rop_dashboard_module, "build_rop_web_projection_v2_views", _v2_views
    )
    storage_dir = tmp_path / "storage"
    logger = _null_logger()
    rop_dashboard_module.write_rop_web_projection_v2(
        storage_dir, ["run-a"], 1, {"run-a": ["7d"]}, logger
    )
    first = rop_dashboard_module.rop_web_projection_v2_manifest(storage_dir)
    assert first is not None
    first_generation = first["runs"]["run-a"]["generation"]
    root = storage_dir / "interfaces" / "rop_web_projection_v2"
    stale = root / ("g_" + "0" * 32)
    stale.mkdir()
    invalid = root / "not-a-generation"
    invalid.mkdir()
    target = tmp_path / "symlink-generation-target"
    target.mkdir()
    symlink = root / ("g_" + "f" * 32)
    symlink.symlink_to(target, target_is_directory=True)

    rop_dashboard_module.write_rop_web_projection_v2(
        storage_dir,
        ["run-b", "run-a"],
        2,
        {"run-b": ["7d"]},
        logger,
    )
    second = rop_dashboard_module.rop_web_projection_v2_manifest(storage_dir)
    assert second is not None
    second_generation = second["runs"]["run-b"]["generation"]
    assert not stale.exists()
    assert invalid.is_dir()
    assert symlink.is_symlink()
    assert target.is_dir()
    assert {entry["generation"] for entry in second["runs"].values()} == {
        first_generation,
        second_generation,
    }

    rop_dashboard_module.write_rop_web_projection_v2(
        storage_dir,
        ["run-c", "run-b"],
        3,
        {"run-c": ["7d"]},
        logger,
    )
    third = rop_dashboard_module.rop_web_projection_v2_manifest(storage_dir)
    assert third is not None
    assert (root / first_generation).is_dir()
    rop_dashboard_module.write_rop_web_projection_v2(
        storage_dir,
        ["run-d", "run-c"],
        4,
        {"run-d": ["7d"]},
        logger,
    )
    fourth = rop_dashboard_module.rop_web_projection_v2_manifest(storage_dir)
    assert fourth is not None
    assert not (root / first_generation).exists()
    for run_id in fourth["run_ids"]:
        assert (
            rop_dashboard_module.read_rop_web_projection_v2_view(
                storage_dir, fourth, run_id, "api", "7d"
            )
            is not None
        )

    for number in range(20):
        rop_dashboard_module.write_rop_web_projection_v2(
            storage_dir,
            ["run-d"],
            4,
            {"run-d": ["7d"]},
            logger,
        )
    generations = [
        path
        for path in root.iterdir()
        if not path.is_symlink()
        and path.is_dir()
        and rop_dashboard_module._projection_revision(path.name) is not None
    ]
    assert len(generations) <= 2


def test_v2_interrupted_publication_cleans_only_own_generation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        rop_dashboard_module, "build_rop_web_projection_v2_views", _v2_views
    )
    storage_dir = tmp_path / "storage"
    logger = _null_logger()
    rop_dashboard_module.write_rop_web_projection_v2(
        storage_dir, ["run-a"], 1, {"run-a": ["7d"]}, logger
    )
    manifest_path = storage_dir / "interfaces" / "rop_web_projection_v2.json"
    before = manifest_path.read_bytes()
    root = storage_dir / "interfaces" / "rop_web_projection_v2"
    previous_generations = {path.name for path in root.iterdir() if path.is_dir()}
    original_write_text = Path.write_text

    def interrupted_write(
        path: Path,
        data: str,
        encoding: str | None = None,
    ) -> int:
        if path.parents[2].name.startswith(".g_"):
            raise OSError("simulated interrupted generation write")
        return original_write_text(path, data, encoding=encoding)

    monkeypatch.setattr(Path, "write_text", interrupted_write)
    with pytest.raises(OSError, match="interrupted"):
        rop_dashboard_module.write_rop_web_projection_v2(
            storage_dir, ["run-b"], 2, {"run-b": ["7d"]}, logger
        )
    assert manifest_path.read_bytes() == before
    assert {
        path.name for path in root.iterdir() if path.is_dir()
    } == previous_generations
    assert not any(path.name.startswith(".g_") for path in root.iterdir())


def test_v2_manifest_failure_cleans_unpublished_final_without_masking_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        rop_dashboard_module, "build_rop_web_projection_v2_views", _v2_views
    )
    storage_dir = tmp_path / "storage"
    logger = _null_logger()
    rop_dashboard_module.write_rop_web_projection_v2(
        storage_dir, ["run-a"], 1, {"run-a": ["7d"]}, logger
    )
    manifest_path = storage_dir / "interfaces" / "rop_web_projection_v2.json"
    before = manifest_path.read_bytes()
    root = storage_dir / "interfaces" / "rop_web_projection_v2"
    existing = {path.name for path in root.iterdir() if path.is_dir()}
    original_replace = rop_dashboard_module.os.replace
    original_rmtree = rop_dashboard_module.shutil.rmtree

    def failing_manifest_replace(source: Path, target: Path) -> None:
        if source.name == "rop_web_projection_v2.json.tmp":
            raise OSError("simulated manifest replacement failure")
        original_replace(source, target)

    monkeypatch.setattr(rop_dashboard_module.os, "replace", failing_manifest_replace)
    with pytest.raises(OSError, match="manifest replacement"):
        rop_dashboard_module.write_rop_web_projection_v2(
            storage_dir, ["run-b"], 2, {"run-b": ["7d"]}, logger
        )
    assert manifest_path.read_bytes() == before
    assert {path.name for path in root.iterdir() if path.is_dir()} == existing

    def failing_rmtree(path: Path) -> None:
        if path.name not in existing:
            raise OSError("simulated cleanup failure")
        original_rmtree(path)

    monkeypatch.setattr(rop_dashboard_module.shutil, "rmtree", failing_rmtree)
    with pytest.raises(OSError, match="manifest replacement"):
        rop_dashboard_module.write_rop_web_projection_v2(
            storage_dir, ["run-c"], 3, {"run-c": ["7d"]}, logger
        )
