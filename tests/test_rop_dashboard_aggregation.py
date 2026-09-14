from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path

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
        assert dashboard["queues"]["needs_review"] == []

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
        assert dashboard["queues"]["needs_review"] == []

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

    def test_duplicate_occurrences_do_not_enter_needs_review(
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

        assert dashboard["business_kpi"]["processed_events"] == 2
        assert dashboard["queues"]["needs_review"] == []

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
    return seed_rop_dashboard_run(tmp_path)
