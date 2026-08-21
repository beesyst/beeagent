from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from beeagent_module.cases.rop_action_drafts import _map_action_v0, build_action_drafts


def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_action_drafts")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def _make_reconciliation(
    items: list[dict],
    status: str = "ok",
) -> dict:
    agg = {"event_count": len(items)}
    for item in items:
        ms = item.get("bitrix_match_status", "")
        if ms.startswith("matched_"):
            agg["matched_count"] = agg.get("matched_count", 0) + 1
        elif ms == "weak_match":
            agg["weak_match_count"] = agg.get("weak_match_count", 0) + 1
        elif ms == "not_found":
            agg["not_found_count"] = agg.get("not_found_count", 0) + 1
        elif ms == "duplicate_candidate":
            agg["duplicate_candidate_count"] = (
                agg.get("duplicate_candidate_count", 0) + 1
            )
        elif ms == "ambiguous":
            agg["ambiguous_count"] = agg.get("ambiguous_count", 0) + 1
        elif ms == "skipped":
            agg["skipped_count"] = agg.get("skipped_count", 0) + 1
        elif ms in ("connector_degraded", "error"):
            agg["connector_degraded_count"] = agg.get("connector_degraded_count", 0) + 1
        if item.get("needs_manual_review"):
            agg["manual_review_count"] = agg.get("manual_review_count", 0) + 1

    return {
        "run_id": "test-action-drafts",
        "status": status,
        "read_only": True,
        "aggregate": agg,
        "items": items,
        "warnings": [],
    }


def _sample_item(
    event_id: str = "evt-001",
    match_status: str = "matched_lead",
    case_type: str = "new_lead",
    quality: str = "strong",
    needs_manual: bool = False,
    safe_target: bool = True,
) -> dict:
    return {
        "event_id": event_id,
        "source_id": "rop_batch_sample",
        "sender": "a@b.com",
        "subject": "Test",
        "bot_case_type": case_type,
        "bitrix_match_status": match_status,
        "bitrix_match_quality": quality,
        "bitrix_entity_type": "lead",
        "bitrix_entity_id": 253,
        "bitrix_confidence": 0.95,
        "needs_manual_review": needs_manual,
        "safe_to_use_as_target": safe_target,
        "candidate_count": 1,
        "candidate_summary": "1 candidate, strong",
        "reconciliation_reason": "Found in Bitrix",
        "run_id": "test-action-drafts",
    }


def test_action_draft_run_id_comes_from_build_context(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "test-action-drafts"
    run_dir.mkdir(parents=True)

    item = _sample_item(
        "evt-001",
        match_status="matched_lead",
        case_type="new_lead",
    )
    item.pop("run_id", None)

    recon = _make_reconciliation([item])
    artifact = build_action_drafts(
        tmp_path,
        "test-action-drafts",
        recon,
        _null_logger(),
    )

    assert artifact["items"][0]["run_id"] == "test-action-drafts"


class TestBuildActionDrafts:
    def test_new_lead_not_found_creates_lost_in_bitrix(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "test-action-drafts"
        run_dir.mkdir(parents=True)
        item = _sample_item(
            "evt-001",
            match_status="not_found",
            case_type="new_lead",
            quality="not_found",
            needs_manual=True,
            safe_target=False,
        )
        recon = _make_reconciliation([item])
        artifact = build_action_drafts(
            tmp_path,
            "test-action-drafts",
            recon,
            _null_logger(),
        )
        assert artifact["status"] == "ok"
        assert len(artifact["items"]) == 1
        draft = artifact["items"][0]
        assert draft["queue"] == "lost_in_bitrix"
        assert draft["recommended_action"] == "check_crm_gap"
        assert draft["read_only"] is True
        assert draft["safe_to_use_as_target"] is False

    def test_matched_lead_creates_review_action(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "test-action-drafts"
        run_dir.mkdir(parents=True)
        item = _sample_item(
            "evt-001", match_status="matched_lead", case_type="new_lead"
        )
        recon = _make_reconciliation([item])
        artifact = build_action_drafts(
            tmp_path,
            "test-action-drafts",
            recon,
            _null_logger(),
        )
        draft = artifact["items"][0]
        assert draft["queue"] == "matched"
        assert draft["recommended_action"] == "review_existing_lead"

    def test_matched_deal_creates_review_deal(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "test-action-drafts"
        run_dir.mkdir(parents=True)
        item = _sample_item(
            "evt-001",
            match_status="matched_deal",
            case_type="existing_deal",
        )
        recon = _make_reconciliation([item])
        artifact = build_action_drafts(
            tmp_path,
            "test-action-drafts",
            recon,
            _null_logger(),
        )
        draft = artifact["items"][0]
        assert draft["queue"] == "matched"
        assert draft["recommended_action"] == "review_deal"

    def test_weak_match_new_lead_creates_independent_lead(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "test-action-drafts"
        run_dir.mkdir(parents=True)
        item = _sample_item(
            "evt-001",
            match_status="weak_match",
            case_type="new_lead",
            quality="weak",
            needs_manual=True,
            safe_target=False,
        )
        recon = _make_reconciliation([item])
        artifact = build_action_drafts(
            tmp_path,
            "test-action-drafts",
            recon,
            _null_logger(),
        )
        draft = artifact["items"][0]
        assert draft["queue"] == "create_lead"
        assert draft["recommended_action"] == "create_lead"
        assert draft["reason_code"] == "new_lead_crm_weak_match"
        assert draft["bitrix_match_status"] == "weak_match"
        assert draft["safe_to_use_as_target"] is False

    def test_ambiguous_new_lead_creates_independent_lead(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "test-action-drafts"
        run_dir.mkdir(parents=True)
        item = _sample_item(
            "evt-001",
            match_status="ambiguous",
            case_type="new_lead",
            quality="ambiguous",
            needs_manual=True,
            safe_target=False,
        )
        recon = _make_reconciliation([item])
        artifact = build_action_drafts(
            tmp_path,
            "test-action-drafts",
            recon,
            _null_logger(),
        )
        draft = artifact["items"][0]
        assert draft["queue"] == "create_lead"
        assert draft["recommended_action"] == "create_lead"
        assert draft["reason_code"] == "new_lead_crm_ambiguous"
        assert draft["bitrix_match_status"] == "ambiguous"

    def test_duplicate_candidate_new_lead_creates_independent_lead(
        self, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "test-action-drafts"
        run_dir.mkdir(parents=True)
        item = _sample_item(
            "evt-001",
            match_status="duplicate_candidate",
            case_type="new_lead",
            quality="duplicate",
            needs_manual=True,
            safe_target=False,
        )
        recon = _make_reconciliation([item])
        artifact = build_action_drafts(
            tmp_path,
            "test-action-drafts",
            recon,
            _null_logger(),
        )
        draft = artifact["items"][0]
        assert draft["queue"] == "create_lead"
        assert draft["recommended_action"] == "create_lead"
        assert draft["reason_code"] == "new_lead_crm_duplicate_candidate"
        assert draft["bitrix_match_status"] == "duplicate_candidate"

    def test_irrelevant_creates_ignore(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "test-action-drafts"
        run_dir.mkdir(parents=True)
        item = _sample_item(
            "evt-001",
            match_status="not_found",
            case_type="irrelevant",
            quality="not_found",
            needs_manual=False,
            safe_target=False,
        )
        recon = _make_reconciliation([item])
        artifact = build_action_drafts(
            tmp_path,
            "test-action-drafts",
            recon,
            _null_logger(),
        )
        draft = artifact["items"][0]
        assert draft["queue"] == "ignore"
        assert draft["recommended_action"] == "ignore"
        assert draft["needs_manual_review"] is False

    @pytest.mark.parametrize(
        ("match_status", "entity_type", "outcome", "action"),
        [
            ("not_found", "", "create_lead", "create_lead"),
            ("matched_lead", "lead", "attach_existing", "attach_existing"),
            ("matched_deal", "deal", "attach_existing", "attach_existing"),
        ],
    )
    def test_irrelevant_writeback_projection_is_not_ignore(
        self,
        tmp_path: Path,
        match_status: str,
        entity_type: str,
        outcome: str,
        action: str,
    ) -> None:
        run_dir = tmp_path / "runs" / "test-action-drafts"
        run_dir.mkdir(parents=True)
        interfaces = tmp_path / "interfaces"
        interfaces.mkdir()
        (interfaces / "rop_writeback_state.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "events": {
                        "stable": {
                            "event_id": "evt-001",
                            "event_instance_id": "",
                            "last_run_id": "test-action-drafts",
                            "outcome": outcome,
                            "status": "pending",
                            "reason_code": None,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        item = _sample_item(
            "evt-001",
            match_status=match_status,
            case_type="irrelevant",
            quality="strong" if entity_type else "not_found",
            needs_manual=False,
            safe_target=bool(entity_type),
        )
        item["bitrix_entity_type"] = entity_type
        item["should_rop_see"] = False
        artifact = build_action_drafts(
            tmp_path,
            "test-action-drafts",
            _make_reconciliation([item]),
            _null_logger(),
        )
        draft = artifact["items"][0]
        assert draft["queue"] == "delivery_planned"
        assert draft["recommended_action"] == action
        assert draft["delivery_outcome"] == outcome
        assert draft["read_only"] is True
        assert artifact["draft_only"] is True

    @pytest.mark.parametrize(
        (
            "status",
            "attachment_required",
            "attachment_status",
            "activity_id",
            "queue",
            "action",
            "next_step",
        ),
        [
            (
                "pending",
                False,
                "not_required",
                None,
                "delivery_planned",
                "create_lead",
                "controlled_writeback_pending",
            ),
            (
                "uncertain",
                False,
                "not_required",
                None,
                "delivery_planned",
                "create_lead",
                "controlled_writeback_pending",
            ),
            (
                "created",
                False,
                "not_required",
                None,
                "delivered",
                "delivery_completed",
                "no_action_required",
            ),
            (
                "recovered",
                False,
                "not_required",
                None,
                "delivered",
                "delivery_completed",
                "no_action_required",
            ),
            (
                "created",
                True,
                "pending",
                None,
                "delivery_planned",
                "complete_email_attachment",
                "controlled_writeback_pending",
            ),
            (
                "created",
                True,
                "uncertain",
                None,
                "delivery_planned",
                "complete_email_attachment",
                "controlled_writeback_pending",
            ),
            (
                "created",
                True,
                "failed",
                None,
                "deferred",
                "review_delivery_failure",
                "review_deferred_delivery",
            ),
            (
                "attached",
                True,
                "attached",
                9001,
                "delivered",
                "delivery_completed",
                "no_action_required",
            ),
            (
                "failed",
                False,
                "not_required",
                None,
                "deferred",
                "review_delivery_failure",
                "review_deferred_delivery",
            ),
            (
                "deferred",
                False,
                "not_required",
                None,
                "deferred",
                "review_delivery_failure",
                "review_deferred_delivery",
            ),
        ],
    )
    def test_writeback_projection_reflects_delivery_status(
        self,
        tmp_path: Path,
        status: str,
        attachment_required: bool,
        attachment_status: str,
        activity_id: int | None,
        queue: str,
        action: str,
        next_step: str,
    ) -> None:
        run_dir = tmp_path / "runs" / "test-action-drafts"
        run_dir.mkdir(parents=True)
        interfaces = tmp_path / "interfaces"
        interfaces.mkdir()
        (interfaces / "rop_writeback_state.json").write_text(
            json.dumps(
                {
                    "events": {
                        "stable": {
                            "event_id": "evt-001",
                            "event_instance_id": "",
                            "last_run_id": "test-action-drafts",
                            "outcome": (
                                "attach_existing"
                                if status == "attached"
                                else "create_lead"
                            ),
                            "status": status,
                            "email_attachment_required": attachment_required,
                            "email_attachment_status": attachment_status,
                            "email_activity_id": activity_id,
                            "reason_code": "retry_exhausted"
                            if status == "failed"
                            else None,
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        artifact = build_action_drafts(
            tmp_path,
            "test-action-drafts",
            _make_reconciliation([_sample_item("evt-001", match_status="not_found")]),
            _null_logger(),
        )
        draft = artifact["items"][0]
        assert (
            draft["queue"],
            draft["recommended_action"],
            draft["recommended_next_step"],
        ) == (
            queue,
            action,
            next_step,
        )

    def test_connector_degraded_creates_connector_check(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "test-action-drafts"
        run_dir.mkdir(parents=True)
        item = _sample_item(
            "evt-001",
            match_status="connector_degraded",
            case_type="new_lead",
            quality="connector_degraded",
            needs_manual=True,
            safe_target=False,
        )
        recon = _make_reconciliation([item])
        artifact = build_action_drafts(
            tmp_path,
            "test-action-drafts",
            recon,
            _null_logger(),
        )
        draft = artifact["items"][0]
        assert draft["queue"] == "degraded"
        assert draft["recommended_action"] == "check_bitrix_connector"

    def test_error_creates_connector_check(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "test-action-drafts"
        run_dir.mkdir(parents=True)
        item = _sample_item(
            "evt-001",
            match_status="error",
            case_type="new_lead",
            quality="error",
            needs_manual=True,
            safe_target=False,
        )
        recon = _make_reconciliation([item])
        artifact = build_action_drafts(
            tmp_path,
            "test-action-drafts",
            recon,
            _null_logger(),
        )
        draft = artifact["items"][0]
        assert draft["queue"] == "degraded"
        assert draft["recommended_action"] == "check_bitrix_connector"

    def test_skipped_creates_ignore(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "test-action-drafts"
        run_dir.mkdir(parents=True)
        item = _sample_item(
            "evt-001",
            match_status="skipped",
            case_type="spam",
            quality="skipped",
            needs_manual=False,
            safe_target=False,
        )
        recon = _make_reconciliation([item])
        artifact = build_action_drafts(
            tmp_path,
            "test-action-drafts",
            recon,
            _null_logger(),
        )
        draft = artifact["items"][0]
        assert draft["queue"] == "ignore"
        assert draft["recommended_action"] == "ignore"

    def test_unreconciled_for_missing_bitrix_evidence(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "test-action-drafts"
        run_dir.mkdir(parents=True)
        item = _sample_item(
            "evt-001",
            match_status="",
            case_type="new_lead",
            quality="",
            needs_manual=True,
            safe_target=False,
        )
        recon = _make_reconciliation([item])
        artifact = build_action_drafts(
            tmp_path,
            "test-action-drafts",
            recon,
            _null_logger(),
        )
        draft = artifact["items"][0]
        assert draft["queue"] == "unreconciled"
        assert draft["recommended_action"] == "run_read_only_reconciliation"

    def test_artifact_has_read_only_and_draft_only(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "test-action-drafts"
        run_dir.mkdir(parents=True)
        item = _sample_item(
            "evt-001", match_status="matched_lead", case_type="new_lead"
        )
        recon = _make_reconciliation([item])
        artifact = build_action_drafts(
            tmp_path,
            "test-action-drafts",
            recon,
            _null_logger(),
        )
        assert artifact["read_only"] is True
        assert artifact["draft_only"] is True

    def test_path_traversal_rejected(self, tmp_path: Path) -> None:
        recon = _make_reconciliation([])
        with pytest.raises((ValueError, FileNotFoundError)):
            build_action_drafts(
                tmp_path,
                "../../etc/passwd",
                recon,
                _null_logger(),
            )

    def test_draft_enriched_with_recipient_routing_evidence(
        self, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "test-action-drafts"
        run_dir.mkdir(parents=True)
        (run_dir / "rop_recipient_routing.json").write_text(
            json.dumps(
                {
                    "run_id": "test-action-drafts",
                    "items": [
                        {
                            "event_id": "evt-001",
                            "event_instance_id": "event-000001",
                            "recipient": "boss@welding.kz",
                            "recipient_evidence_source": "original_recipient",
                            "recipient_status": "resolved",
                            "responsible": {
                                "status": "matched",
                                "user_id": 12,
                                "name": "Ivan Petrov",
                                "email": "boss@welding.kz",
                                "reason": None,
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        item = _sample_item(
            "evt-001",
            match_status="matched_lead",
            case_type="new_lead",
        )
        recon = _make_reconciliation([item])
        artifact = build_action_drafts(
            tmp_path,
            "test-action-drafts",
            recon,
            _null_logger(),
        )
        draft = artifact["items"][0]
        assert draft["recipient"] == "boss@welding.kz"
        assert draft["recipient_evidence_source"] == "original_recipient"
        assert draft["recipient_status"] == "resolved"
        assert draft["proposed_responsible_user_id"] == 12
        assert draft["proposed_responsible_name"] == "Ivan Petrov"
        assert draft["proposed_responsible_email"] == "boss@welding.kz"
        assert draft["responsible_status"] == "matched"
        assert draft["read_only"] is True

    def test_drafts_join_routing_by_event_instance_id(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "test-action-drafts"
        run_dir.mkdir(parents=True)
        (run_dir / "rop_recipient_routing.json").write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "event_id": "evt-shared",
                            "event_instance_id": "event-000001",
                            "recipient": "first@welding.kz",
                            "recipient_status": "resolved",
                            "responsible": {"status": "matched", "user_id": 1},
                        },
                        {
                            "event_id": "evt-shared",
                            "event_instance_id": "event-000002",
                            "recipient": "second@welding.kz",
                            "recipient_status": "resolved",
                            "responsible": {"status": "matched", "user_id": 2},
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        first = _sample_item("evt-shared")
        first["event_instance_id"] = "event-000001"
        second = _sample_item("evt-shared")
        second["event_instance_id"] = "event-000002"
        artifact = build_action_drafts(
            tmp_path,
            "test-action-drafts",
            _make_reconciliation([first, second]),
            _null_logger(),
        )
        drafts = {item["event_instance_id"]: item for item in artifact["items"]}
        assert drafts["event-000001"]["recipient"] == "first@welding.kz"
        assert drafts["event-000001"]["proposed_responsible_user_id"] == 1
        assert drafts["event-000002"]["recipient"] == "second@welding.kz"
        assert drafts["event-000002"]["proposed_responsible_user_id"] == 2

    def test_ambiguous_legacy_routing_is_not_selected(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "test-action-drafts"
        run_dir.mkdir(parents=True)
        (run_dir / "rop_recipient_routing.json").write_text(
            json.dumps(
                {
                    "items": [
                        {"event_id": "evt-shared", "recipient": "first@welding.kz"},
                        {"event_id": "evt-shared", "recipient": "second@welding.kz"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        item = _sample_item("evt-shared")
        item["event_instance_id"] = "event-000002"
        artifact = build_action_drafts(
            tmp_path,
            "test-action-drafts",
            _make_reconciliation([item]),
            _null_logger(),
        )
        assert artifact["items"][0]["recipient"] == ""

    def test_draft_without_routing_artifact_keeps_safe_defaults(
        self, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "test-action-drafts"
        run_dir.mkdir(parents=True)
        item = _sample_item(
            "evt-001",
            match_status="matched_lead",
            case_type="new_lead",
        )
        recon = _make_reconciliation([item])
        artifact = build_action_drafts(
            tmp_path,
            "test-action-drafts",
            recon,
            _null_logger(),
        )
        draft = artifact["items"][0]
        assert draft["recipient"] == ""
        assert draft["recipient_status"] == ""
        assert draft["proposed_responsible_user_id"] is None
        assert draft["responsible_status"] == ""
        assert draft["read_only"] is True


class TestMapActionV0:
    def test_new_lead_not_found_maps_to_lost_in_bitrix(self) -> None:
        q, ra, rns, p, rc = _map_action_v0("new_lead", "not_found", "not_found")
        assert q == "lost_in_bitrix"
        assert ra == "check_crm_gap"
        assert rc == "new_lead_not_in_crm"

    def test_existing_deal_matched_maps_to_review_deal(self) -> None:
        q, ra, rns, p, rc = _map_action_v0("existing_deal", "matched_deal", "strong")
        assert q == "matched"
        assert ra == "review_deal"
        assert rc == "deal_exists_in_crm"

    def test_weak_match_new_lead_maps_to_create(self) -> None:
        q, ra, rns, p, rc = _map_action_v0("new_lead", "weak_match", "weak")
        assert q == "create_lead"
        assert ra == "create_lead"
        assert rc == "new_lead_crm_weak_match"

    def test_ambiguous_new_lead_maps_to_create(self) -> None:
        q, ra, rns, p, rc = _map_action_v0("new_lead", "ambiguous", "ambiguous")
        assert q == "create_lead"
        assert ra == "create_lead"
        assert rc == "new_lead_crm_ambiguous"

    def test_duplicate_candidate_new_lead_maps_to_create(self) -> None:
        q, ra, rns, p, rc = _map_action_v0(
            "new_lead", "duplicate_candidate", "duplicate"
        )
        assert q == "create_lead"
        assert ra == "create_lead"
        assert rc == "new_lead_crm_duplicate_candidate"

    def test_duplicate_candidate_existing_deal_maps_to_ambiguous(self) -> None:
        q, ra, rns, p, rc = _map_action_v0(
            "existing_deal", "duplicate_candidate", "duplicate"
        )
        assert q == "ambiguous"
        assert ra == "resolve_duplicate_candidate"

    def test_irrelevant_maps_to_ignore(self) -> None:
        q, ra, rns, p, rc = _map_action_v0("irrelevant", "not_found", "not_found")
        assert q == "ignore"
        assert ra == "ignore"

    def test_connector_degraded_maps_to_degraded(self) -> None:
        q, ra, rns, p, rc = _map_action_v0(
            "new_lead", "connector_degraded", "connector_degraded"
        )
        assert q == "degraded"
        assert ra == "check_bitrix_connector"

    def test_error_maps_to_degraded(self) -> None:
        q, ra, rns, p, rc = _map_action_v0("new_lead", "error", "error")
        assert q == "degraded"
        assert ra == "check_bitrix_connector"

    def test_skipped_maps_to_ignore(self) -> None:
        q, ra, rns, p, rc = _map_action_v0("spam", "skipped", "skipped")
        assert q == "ignore"
        assert ra == "ignore"

    def test_missing_bitrix_maps_to_unreconciled(self) -> None:
        q, ra, rns, p, rc = _map_action_v0("new_lead", "", "")
        assert q == "unreconciled"
        assert ra == "run_read_only_reconciliation"
