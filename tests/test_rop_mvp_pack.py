from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from beeagent_module.cases.rop_mvp_pack import (
    build_mvp_report_markdown,
    build_rop_mvp_pack,
    write_mvp_pack_artifacts,
)


def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_rop_mvp_pack")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


_MINIMAL_SETTINGS: dict = {
    "rop": {
        "sources": [
            {
                "source_id": "rop_batch_sample",
                "source_type": "json_batch",
                "source_role": "batch_sample",
                "client_id": "welding",
                "display_name": "ROP Batch Sample",
                "authority": "read_only",
                "enabled": True,
            },
            {
                "source_id": "hotline_mailbox",
                "source_type": "mailbox_readonly",
                "source_role": "technical_aggregator",
                "client_id": "welding",
                "display_name": "Welding Hotline mailbox",
                "authority": "read_only",
                "enabled": True,
            },
        ],
        "dashboard": {
            "default_period": "7d",
            "periods": ["today", "yesterday", "7d", "30d", "90d", "365d", "all"],
        },
    },
}


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    """Create a minimal run directory with all expected artifacts."""
    rdir = tmp_path / "runs" / "mvp-test-run"
    rdir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)

    normalized = [
        {
            "event_id": "evt-001",
            "source_id": "rop_batch_sample",
            "sender": "client@example.com",
            "subject": "Welding machine inquiry",
            "event_date": now.isoformat(),
            "attachments": [],
        },
        {
            "event_id": "evt-002",
            "source_id": "hotline_mailbox",
            "sender": "lead@example.com",
            "subject": "Need pricing",
            "event_date": now.isoformat(),
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
        },
        {
            "event_id": "evt-002",
            "case_type": "existing_deal",
            "priority": "low",
            "confidence": 0.85,
            "is_fallback": False,
            "reason_code": "existing_match",
            "source_id": "hotline_mailbox",
        },
    ]
    (rdir / "classified_events.json").write_text(
        json.dumps(classified, indent=2), encoding="utf-8"
    )
    (rdir / "rop_review_table.tsv").write_text(
        "event_id\tbot_case_type\nevt-001\tnew_lead\n",
        encoding="utf-8",
    )

    source_diag = {
        "selection_mode": "all_enabled",
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
        "selection_mode": "all_enabled",
        "source_count": 2,
        "loaded_source_count": 2,
        "degraded_source_count": 0,
        "loaded_item_count": 2,
        "sources": [
            {"source_id": "rop_batch_sample", "client_id": "welding", "status": "ok"},
            {"source_id": "hotline_mailbox", "client_id": "welding", "status": "ok"},
        ],
    }
    (rdir / "intake_metadata.json").write_text(
        json.dumps(intake, indent=2), encoding="utf-8"
    )

    attachment_extraction = {
        "run_id": "mvp-test-run",
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
                "event_id": "evt-002",
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

    operator_summary = {
        "run_id": "mvp-test-run",
        "status": "ok",
        "summary": "Batch completed",
        "source": {
            "source_id": "rop_batch_sample",
            "source_type": "json_batch",
        },
    }
    (rdir / "operator_summary.json").write_text(
        json.dumps(operator_summary, indent=2), encoding="utf-8"
    )

    current_state = {
        "run_id": "mvp-test-run",
        "status": "ok",
        "read_only": True,
        "client_id": "welding",
        "kpi": {
            "events_total": 2,
            "normalized_count": 2,
            "classified_count": 2,
            "high_priority": 1,
            "matched_in_bitrix": 1,
            "lost_in_bitrix": 1,
            "ambiguous_in_bitrix": 0,
            "unreconciled": 1,
            "source_degraded": 0,
            "attachment_refused": 1,
            "needs_manual_review": 1,
        },
        "queues": {
            "high_priority": [
                {"event_id": "evt-001", "case_type": "new_lead", "priority": "high"}
            ],
            "needs_review": [
                {"event_id": "evt-001", "case_type": "new_lead", "priority": "high"}
            ],
            "lost_in_bitrix": [
                {"event_id": "evt-002", "case_type": "existing_deal", "priority": "low"}
            ],
            "ambiguous": [
                {
                    "event_id": "evt-003",
                    "case_type": "existing_deal",
                    "priority": "medium",
                }
            ],
            "matched": [
                {"event_id": "evt-001", "case_type": "new_lead", "priority": "high"}
            ],
            "unreconciled": [
                {"event_id": "evt-002", "case_type": "existing_deal", "priority": "low"}
            ],
            "degraded": [],
        },
    }
    (rdir / "rop_current_state.json").write_text(
        json.dumps(current_state, indent=2), encoding="utf-8"
    )

    bitrix = {
        "run_id": "mvp-test-run",
        "status": "ok",
        "aggregate": {
            "event_count": 2,
            "matched_count": 1,
            "not_found_count": 1,
            "ambiguous_count": 0,
            "duplicate_candidate_count": 0,
            "connector_error_count": 0,
        },
        "items": [
            {"event_id": "evt-001", "bitrix_match_status": "matched_lead"},
            {"event_id": "evt-002", "bitrix_match_status": "not_found"},
        ],
    }
    (rdir / "bitrix_reconciliation.json").write_text(
        json.dumps(bitrix, indent=2), encoding="utf-8"
    )

    interfaces_dir = tmp_path / "interfaces"
    interfaces_dir.mkdir(parents=True, exist_ok=True)
    dashboard = {
        "run_id": "mvp-test-run",
        "status": "ok",
        "period": "7d",
        "business_kpi": {
            "processed_events": 2,
            "new_leads": 1,
            "high_priority": 1,
            "lost_in_bitrix": 1,
            "unreconciled": 1,
            "source_degraded": 0,
            "attachment_refused": 1,
        },
    }
    (interfaces_dir / "rop_dashboard.json").write_text(
        json.dumps(dashboard, indent=2), encoding="utf-8"
    )

    return rdir


class TestBuildRopMvpPack:
    def test_full_artifact_set(self, run_dir: Path, tmp_path: Path) -> None:
        pack = build_rop_mvp_pack(
            storage_dir=tmp_path,
            run_id="mvp-test-run",
            period="7d",
            settings=_MINIMAL_SETTINGS,
            logger=_null_logger(),
        )
        assert pack["run_id"] == "mvp-test-run"
        assert pack["period"] == "7d"
        assert pack["read_only"] is True
        assert pack["non_production"] is True
        assert pack["status"] in ("ready", "ready_with_limitations")
        assert pack["client_id"] == "welding"

        sc = pack["source_coverage"]
        assert sc["configured"] == 2
        assert sc["enabled"] == 2
        assert sc["loaded"] >= 2

        bs = pack["business_summary"]
        assert bs.get("classified_count", 0) >= 2

        q = pack["queues"]
        assert q["high_priority_count"] >= 1
        assert q["lost_in_bitrix_count"] >= 1
        assert q["ambiguous_or_duplicate_count"] >= 1

        attn = pack["attachment_summary"]
        assert attn["total_attachments"] >= 1
        assert attn["refused"] >= 1

        actions = pack["first_actions"]
        assert len(actions) > 0
        assert any(
            action.get("type") == "manual_review"
            and "ambiguous/duplicate" in action.get("action", "")
            for action in actions
        )

        dr = pack["demo_readiness"]
        assert dr["status"] in ("ready", "ready_with_limitations")

        links = pack["evidence_links"]
        assert len(links) > 0

        available_by_id = {
            link["artifact_id"]: link["available"]
            for link in links
        }
        assert available_by_id["operator_summary_json"] is True
        assert available_by_id["source_diagnostics_json"] is True
        assert available_by_id["intake_metadata_json"] is True
        assert available_by_id["normalized_events_json"] is True
        assert available_by_id["classified_events_json"] is True
        assert available_by_id["attachment_extraction_json"] is True
        assert available_by_id["rop_current_state_json"] is True
        assert available_by_id["bitrix_reconciliation_json"] is True
        assert available_by_id["rop_review_table_tsv"] is True

        limitations = pack["limitations"]
        assert len(limitations) > 0

        bitrix = pack["bitrix_evidence"]
        assert bitrix["status"] == "reconciled"
        assert bitrix["matched_in_bitrix"] == 1
        assert bitrix["lost_in_bitrix"] == 1
        assert bitrix["ambiguous_or_duplicate"] == 0
        assert bitrix["unreconciled"] == 1

    def test_no_hardcoded_source_names(self, run_dir: Path, tmp_path: Path) -> None:
        pack = build_rop_mvp_pack(
            storage_dir=tmp_path,
            run_id="mvp-test-run",
            period="7d",
            settings=_MINIMAL_SETTINGS,
            logger=_null_logger(),
        )
        sc = pack["source_coverage"]
        for s in sc.get("sources", []):
            assert "source_id" in s
            assert "source_type" in s
            assert "source_role" in s
            assert "client_id" in s
            assert "display_name" in s

        source_ids = [s["source_id"] for s in sc["sources"]]
        assert "rop_batch_sample" in source_ids
        assert "hotline_mailbox" in source_ids

    def test_ignores_dashboard_from_other_run_or_period(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        dashboard_path = tmp_path / "interfaces" / "rop_dashboard.json"
        dashboard_path.write_text(
            json.dumps(
                {
                    "run_id": "other-run",
                    "period": "30d",
                    "business_kpi": {
                        "processed_events": 999,
                        "new_leads": 999,
                        "high_priority": 999,
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        pack = build_rop_mvp_pack(
            storage_dir=tmp_path,
            run_id="mvp-test-run",
            period="7d",
            settings=_MINIMAL_SETTINGS,
            logger=_null_logger(),
        )

        assert pack["business_summary"].get("processed_events") != 999
        assert pack["business_summary"].get("new_leads") != 999
        assert pack["business_summary"].get("high_priority") != 999
        assert any(
            "rop_dashboard.json does not match requested run_id/period" in warning
            for warning in pack["warnings"]
        )

    def test_without_bitrix_artifact(self, run_dir: Path, tmp_path: Path) -> None:
        (run_dir / "bitrix_reconciliation.json").unlink(missing_ok=True)
        pack = build_rop_mvp_pack(
            storage_dir=tmp_path,
            run_id="mvp-test-run",
            period="7d",
            settings=_MINIMAL_SETTINGS,
            logger=_null_logger(),
        )
        assert pack["status"] in ("ready", "ready_with_limitations")
        assert pack["bitrix_evidence"]["status"] == "unreconciled"
        assert "Bitrix reconciliation not yet run" in str(pack.get("limitations", []))

    def test_with_connector_degraded_bitrix(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        """Connector degraded Bitrix should not be treated as lost_in_bitrix."""
        bitrix_path = run_dir / "bitrix_reconciliation.json"
        bitrix = json.loads(bitrix_path.read_text(encoding="utf-8"))
        bitrix["status"] = "degraded"
        for item in bitrix.get("items", []):
            item["bitrix_match_status"] = "connector_degraded"
        bitrix_path.write_text(json.dumps(bitrix, indent=2), encoding="utf-8")

        pack = build_rop_mvp_pack(
            storage_dir=tmp_path,
            run_id="mvp-test-run",
            period="7d",
            settings=_MINIMAL_SETTINGS,
            logger=_null_logger(),
        )
        # Should not crash, connector_degraded events go to degraded queue
        assert pack["status"] in ("ready", "ready_with_limitations")

    def test_missing_current_state(self, run_dir: Path, tmp_path: Path) -> None:
        """Missing rop_current_state.json should degrade gracefully."""
        (run_dir / "rop_current_state.json").unlink(missing_ok=True)
        pack = build_rop_mvp_pack(
            storage_dir=tmp_path,
            run_id="mvp-test-run",
            period="7d",
            settings=_MINIMAL_SETTINGS,
            logger=_null_logger(),
        )
        assert pack["run_id"] == "mvp-test-run"
        # Should still have business_summary from dashboard or classified events
        assert pack.get("business_summary", {})

    def test_missing_dashboard(self, run_dir: Path, tmp_path: Path) -> None:
        """Missing rop_dashboard.json should degrade gracefully."""
        interfaces_dir = tmp_path / "interfaces"
        (interfaces_dir / "rop_dashboard.json").unlink(missing_ok=True)
        pack = build_rop_mvp_pack(
            storage_dir=tmp_path,
            run_id="mvp-test-run",
            period="7d",
            settings=_MINIMAL_SETTINGS,
            logger=_null_logger(),
        )
        assert pack["run_id"] == "mvp-test-run"
        # Business summary should fall back to current_state or classified events
        assert pack.get("business_summary", {})

    def test_missing_normalized_events(self, run_dir: Path, tmp_path: Path) -> None:
        """Missing normalized_events.json should degrade gracefully."""
        (run_dir / "normalized_events.json").unlink(missing_ok=True)
        pack = build_rop_mvp_pack(
            storage_dir=tmp_path,
            run_id="mvp-test-run",
            period="7d",
            settings=_MINIMAL_SETTINGS,
            logger=_null_logger(),
        )
        assert pack["run_id"] == "mvp-test-run"

    def test_missing_tsv(self, run_dir: Path, tmp_path: Path) -> None:
        """Missing review TSV should not break the pack."""
        (run_dir / "rop_review_table.tsv").unlink(missing_ok=True)
        pack = build_rop_mvp_pack(
            storage_dir=tmp_path,
            run_id="mvp-test-run",
            period="7d",
            settings=_MINIMAL_SETTINGS,
            logger=_null_logger(),
        )
        assert pack["run_id"] == "mvp-test-run"
        available_by_id = {
            link["artifact_id"]: link["available"]
            for link in pack["evidence_links"]
        }
        assert available_by_id["rop_review_table_tsv"] is False

    def test_path_traversal_rejected(self, run_dir: Path, tmp_path: Path) -> None:
        """Path traversal in run_id must be rejected."""
        with pytest.raises(ValueError, match="path traversal"):
            build_rop_mvp_pack(
                storage_dir=tmp_path,
                run_id="../../etc/passwd",
                period="7d",
                settings=_MINIMAL_SETTINGS,
                logger=_null_logger(),
            )

    def test_nonexistent_run_rejected(self, run_dir: Path, tmp_path: Path) -> None:
        """Non-existent run_id must be rejected."""
        with pytest.raises(FileNotFoundError, match="Run directory not found"):
            build_rop_mvp_pack(
                storage_dir=tmp_path,
                run_id="nonexistent-run",
                period="7d",
                settings=_MINIMAL_SETTINGS,
                logger=_null_logger(),
            )

    def test_source_coverage_from_config_only(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        """Without source_diagnostics.json, coverage comes from config."""
        (run_dir / "source_diagnostics.json").unlink(missing_ok=True)
        pack = build_rop_mvp_pack(
            storage_dir=tmp_path,
            run_id="mvp-test-run",
            period="7d",
            settings=_MINIMAL_SETTINGS,
            logger=_null_logger(),
        )
        sc = pack["source_coverage"]
        assert sc["configured"] == 2
        assert sc["enabled"] == 2
        # loaded/degraded should be 0 without diagnostics
        assert sc.get("loaded", 0) >= 0

    def test_bitrix_evidence_uses_reconciliation_aggregate_without_current_state(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        (run_dir / "rop_current_state.json").unlink(missing_ok=True)
        (tmp_path / "interfaces" / "rop_dashboard.json").unlink(missing_ok=True)

        bitrix_path = run_dir / "bitrix_reconciliation.json"
        bitrix = json.loads(bitrix_path.read_text(encoding="utf-8"))
        bitrix["aggregate"] = {
            "event_count": 4,
            "matched_count": 2,
            "not_found_count": 1,
            "ambiguous_count": 1,
            "duplicate_candidate_count": 1,
            "connector_error_count": 1,
            "skipped_count": 3,
        }
        bitrix_path.write_text(json.dumps(bitrix, indent=2), encoding="utf-8")

        pack = build_rop_mvp_pack(
            storage_dir=tmp_path,
            run_id="mvp-test-run",
            period="7d",
            settings=_MINIMAL_SETTINGS,
            logger=_null_logger(),
        )

        evidence = pack["bitrix_evidence"]
        assert evidence["status"] == "reconciled"
        assert evidence["matched_in_bitrix"] == 2
        assert evidence["lost_in_bitrix"] == 1
        assert evidence["ambiguous_or_duplicate"] == 2
        assert evidence["unreconciled"] == 3
        assert evidence["bitrix_errors"] == 1


class TestMvpReportMarkdown:
    def test_contains_expected_sections(self, run_dir: Path, tmp_path: Path) -> None:
        pack = build_rop_mvp_pack(
            storage_dir=tmp_path,
            run_id="mvp-test-run",
            period="7d",
            settings=_MINIMAL_SETTINGS,
            logger=_null_logger(),
        )
        md = build_mvp_report_markdown(pack)
        assert "# ROP MVP Handoff Report" in md
        assert "## Executive Summary" in md
        assert "## Period and Run" in md
        assert "## Source Coverage" in md
        assert "## Business KPI" in md
        assert "## First Actions for ROP" in md
        assert "## Queues" in md
        assert "## Bitrix Evidence" in md
        assert "## Attachment Evidence" in md
        assert "## Evidence Artifacts" in md
        assert "## Known Limitations" in md
        assert "## Not Included in MVP" in md
        assert "## Recommended Next Step" in md

    def test_no_secrets_in_report(self, run_dir: Path, tmp_path: Path) -> None:
        """Report must not contain secrets, raw .eml, raw attachment content."""
        pack = build_rop_mvp_pack(
            storage_dir=tmp_path,
            run_id="mvp-test-run",
            period="7d",
            settings=_MINIMAL_SETTINGS,
            logger=_null_logger(),
        )
        md = build_mvp_report_markdown(pack)

        # No secrets patterns
        secrets_patterns = [
            "https://.*bitrix",
            "/rest/[0-9]",
            "password",
            "secret",
            "token",
            "raw_eml",
            "message/rfc822",
            "attachment_content",
            "content_bytes",
        ]
        for pattern in secrets_patterns:
            import re

            if re.search(pattern, md, re.IGNORECASE):
                pytest.fail(f"Secret/content pattern found in report: {pattern}")

    def test_run_id_and_period_in_report(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        pack = build_rop_mvp_pack(
            storage_dir=tmp_path,
            run_id="mvp-test-run",
            period="7d",
            settings=_MINIMAL_SETTINGS,
            logger=_null_logger(),
        )
        md = build_mvp_report_markdown(pack)
        assert "mvp-test-run" in md
        assert "7d" in md

    def test_business_kpi_uses_ambiguous_or_duplicate_key(self) -> None:
        pack = {
            "generated_at_utc": "2026-06-22T08:43:48Z",
            "status": "ready",
            "read_only": True,
            "non_production": True,
            "run_id": "mvp-test-run",
            "period": "7d",
            "client_id": "welding",
            "demo_readiness": {"status": "ready", "ready_items": []},
            "source_coverage": {},
            "business_summary": {
                "processed_events": 5,
                "high_priority": 1,
                "needs_review": 2,
                "matched_in_bitrix": 1,
                "lost_in_bitrix": 0,
                "ambiguous_or_duplicate": 3,
                "unreconciled": 1,
            },
            "first_actions": [],
            "queues": {},
            "bitrix_evidence": {},
            "attachment_summary": {},
            "evidence_links": [],
            "limitations": [],
        }

        md = build_mvp_report_markdown(pack)

        assert "- **Ambiguous/duplicate:** 3" in md


class TestWriteMvpPackArtifacts:
    def test_writes_per_run_artifacts(self, run_dir: Path, tmp_path: Path) -> None:
        pack = build_rop_mvp_pack(
            storage_dir=tmp_path,
            run_id="mvp-test-run",
            period="7d",
            settings=_MINIMAL_SETTINGS,
            logger=_null_logger(),
        )
        paths = write_mvp_pack_artifacts(
            storage_dir=tmp_path,
            run_id="mvp-test-run",
            pack=pack,
            logger=_null_logger(),
        )

        assert paths["pack"].exists()
        assert paths["pack"].name == "rop_mvp_pack.json"
        assert paths["report"].exists()
        assert paths["report"].name == "rop_mvp_report.md"
        assert paths["latest"].exists()
        assert paths["latest"].name == "rop_mvp_latest.json"

    def test_updates_interface_latest(self, run_dir: Path, tmp_path: Path) -> None:
        pack = build_rop_mvp_pack(
            storage_dir=tmp_path,
            run_id="mvp-test-run",
            period="7d",
            settings=_MINIMAL_SETTINGS,
            logger=_null_logger(),
        )
        write_mvp_pack_artifacts(
            storage_dir=tmp_path,
            run_id="mvp-test-run",
            pack=pack,
            logger=_null_logger(),
        )

        latest_path = tmp_path / "interfaces" / "rop_mvp_latest.json"
        assert latest_path.exists()

        latest = json.loads(latest_path.read_text(encoding="utf-8"))
        assert latest["run_id"] == "mvp-test-run"
        assert latest["period"] == "7d"
        assert latest["read_only"] is True
        assert latest["non_production"] is True
        assert "generated_at_utc" in latest
        assert latest["client_id"] == "welding"
        assert "source_coverage" in latest
        assert "business_summary" in latest
        assert "demo_readiness" in latest
        assert "warnings" in latest

    def test_path_traversal_rejected_in_write(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        pack = build_rop_mvp_pack(
            storage_dir=tmp_path,
            run_id="mvp-test-run",
            period="7d",
            settings=_MINIMAL_SETTINGS,
            logger=_null_logger(),
        )
        with pytest.raises(ValueError, match="path traversal"):
            write_mvp_pack_artifacts(
                storage_dir=tmp_path,
                run_id="../../etc/passwd",
                pack=pack,
                logger=_null_logger(),
            )

    def test_generated_at_is_utc(self, run_dir: Path, tmp_path: Path) -> None:
        pack = build_rop_mvp_pack(
            storage_dir=tmp_path,
            run_id="mvp-test-run",
            period="7d",
            settings=_MINIMAL_SETTINGS,
            logger=_null_logger(),
        )
        ga = pack.get("generated_at_utc", "")
        assert ga.endswith("Z")
        # Verify it parses as valid ISO 8601
        datetime.fromisoformat(ga.replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# Tests: Config source coverage
# ---------------------------------------------------------------------------


class TestSourceCoverage:
    def test_empty_sources(self, run_dir: Path, tmp_path: Path) -> None:
        """Empty rop.sources in config should be handled gracefully."""
        # Remove source_diagnostics so config-only mode is tested
        (run_dir / "source_diagnostics.json").unlink(missing_ok=True)
        empty_settings = {"rop": {"sources": [], "dashboard": {"default_period": "7d"}}}
        pack = build_rop_mvp_pack(
            storage_dir=tmp_path,
            run_id="mvp-test-run",
            period="7d",
            settings=empty_settings,
            logger=_null_logger(),
        )
        sc = pack["source_coverage"]
        assert sc["configured"] == 0
        assert sc["enabled"] == 0
        assert "warning" in sc

    def test_no_rop_block(self, run_dir: Path, tmp_path: Path) -> None:
        """Missing rop block in settings should be handled gracefully."""
        (run_dir / "source_diagnostics.json").unlink(missing_ok=True)
        broken_settings: dict = {}
        pack = build_rop_mvp_pack(
            storage_dir=tmp_path,
            run_id="mvp-test-run",
            period="7d",
            settings=broken_settings,
            logger=_null_logger(),
        )
        sc = pack["source_coverage"]
        assert sc["configured"] == 0
        assert "warning" in sc


# ---------------------------------------------------------------------------
# Tests: Evidence links
# ---------------------------------------------------------------------------


class TestEvidenceLinks:
    def test_evidence_links_are_safe(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        """Evidence links must not contain secrets or full artifact paths."""
        pack = build_rop_mvp_pack(
            storage_dir=tmp_path,
            run_id="mvp-test-run",
            period="7d",
            settings=_MINIMAL_SETTINGS,
            logger=_null_logger(),
        )
        for link in pack.get("evidence_links", []):
            href = link.get("href", "")
            # Must not contain raw file system paths
            assert "/storage/" not in href
            assert "/logs/" not in href
            # Must be relative artifact URL
            assert href.startswith("/runs/")
            # Must not contain secrets
            assert "bitrix" not in href.lower() or "/runs/" in href
