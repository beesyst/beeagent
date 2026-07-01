from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from beeagent_module.cases.rop_context_enrichment import (
    build_context_enrichment,
    write_context_enrichment_artifact,
)
from beeagent_module.cases.rop_evaluation import (
    evaluate_reviewed_tsv,
    write_evaluation_artifact,
)
from beeagent_module.cases.rop_recommendations import (
    build_recommendations,
    build_routing_map,
)
from beeagent_module.core.rop_ai_assist import resolve_ai_profile


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _routing_settings() -> dict:
    return {
        "rop": {
            "routing": {
                "queues": {
                    "sales": {"bitrix_category": "sales"},
                    "tender": {"bitrix_category": "tenders"},
                    "logistics": {"bitrix_category": "logistics"},
                    "finance": {"bitrix_category": "finance"},
                    "procurement": {"bitrix_category": "procurement"},
                    "manual_review": {"bitrix_category": "manual_review"},
                }
            }
        }
    }


def test_evaluation_happy_path(tmp_path, caplog):
    import csv
    import logging

    run_dir = tmp_path / "runs" / "test-run"
    run_dir.mkdir(parents=True)
    tsv_path = run_dir / "rop_review_table.tsv"

    rows = [
        {
            "event_id": "evt-001",
            "bot_case_type": "new_lead",
            "human_case_type": "new_lead",
            "bot_is_fallback": "false",
            "bot_reason_code": "det_001",
            "bot_priority": "high",
        },
        {
            "event_id": "evt-002",
            "bot_case_type": "irrelevant",
            "human_case_type": "existing_deal",
            "bot_is_fallback": "false",
            "bot_reason_code": "det_002",
            "bot_priority": "medium",
        },
        {
            "event_id": "evt-003",
            "bot_case_type": "new_lead",
            "human_case_type": "new_lead",
            "bot_is_fallback": "true",
            "bot_reason_code": "classification_error",
            "bot_priority": "high",
        },
    ]

    with tsv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, delimiter="\t", fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    logger = logging.getLogger("test")
    artifact = evaluate_reviewed_tsv(
        tsv_path=tsv_path, run_id="test-run", logger=logger
    )

    assert artifact["status"] == "needs_attention"
    metrics = artifact["metrics"]
    assert metrics["total_events"] == 3
    assert metrics["critical_false_negative_count"] == 1
    assert metrics["existing_deal_as_irrelevant_count"] == 1
    assert metrics["fallback_count"] == 1

    acceptance = artifact["acceptance"]
    assert acceptance["acceptance_status"] == "needs_attention"

    eval_path = write_evaluation_artifact(
        storage_dir=tmp_path, run_id="test-run", artifact=artifact, logger=logger
    )
    assert eval_path.exists()


def test_evaluation_missing_optional_columns(tmp_path, caplog):
    import csv
    import logging

    run_dir = tmp_path / "runs" / "test-run-missing"
    run_dir.mkdir(parents=True)
    tsv_path = run_dir / "rop_review_table.tsv"

    rows = [
        {
            "event_id": "evt-001",
            "bot_case_type": "new_lead",
            "bot_is_fallback": "false",
        },
        {
            "event_id": "evt-002",
            "bot_case_type": "irrelevant",
            "bot_is_fallback": "false",
        },
    ]

    with tsv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, delimiter="\t", fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    logger = logging.getLogger("test")
    artifact = evaluate_reviewed_tsv(
        tsv_path=tsv_path, run_id="test-run-missing", logger=logger
    )

    assert artifact["status"] == "needs_attention"
    assert artifact["acceptance"]["acceptance_status"] == "needs_attention"
    not_evaluable = artifact["metrics"].get("not_evaluable", {})
    assert "case_type_accuracy" in not_evaluable


def test_context_enrichment_artifact(tmp_path, caplog):
    import logging

    run_dir = tmp_path / "runs" / "test-run-enrich"
    run_dir.mkdir(parents=True)

    normalized = [
        {
            "event_id": "evt-001",
            "sender": "client@example.com",
            "subject": "Request for welding",
            "source_id": "test-source",
        },
    ]
    classified = [
        {
            "event_id": "evt-001",
            "case_type": "irrelevant",
            "priority": "medium",
            "confidence": 0.45,
            "is_fallback": False,
        },
    ]
    _write_json(run_dir / "normalized_events.json", normalized)
    _write_json(run_dir / "classified_events.json", classified)

    logger = logging.getLogger("test")
    artifact = build_context_enrichment(
        storage_dir=tmp_path, run_id="test-run-enrich", logger=logger
    )

    assert artifact["status"] == "ok"
    assert artifact["aggregate"]["event_count"] == 1
    assert len(artifact["items"]) == 1

    enriched = artifact["items"][0]
    assert enriched["event_id"] == "evt-001"
    assert enriched["bot_case_type"] == "irrelevant"
    assert enriched["ai_fallback_eligible"] is True

    ctx_path = write_context_enrichment_artifact(
        storage_dir=tmp_path, run_id="test-run-enrich", artifact=artifact, logger=logger
    )
    assert ctx_path.exists()


def test_context_enrichment_existing_deal_routed_to_manual_review(tmp_path, caplog):
    import logging

    run_dir = tmp_path / "runs" / "test-run-deal"
    run_dir.mkdir(parents=True)

    normalized = [
        {
            "event_id": "evt-001",
            "sender": "deal@example.com",
            "subject": "Update on order",
            "source_id": "test-source",
        },
    ]
    classified = [
        {
            "event_id": "evt-001",
            "case_type": "irrelevant",
            "priority": "medium",
            "confidence": 0.80,
            "is_fallback": False,
        },
    ]
    bitrix = {
        "items": [
            {
                "event_id": "evt-001",
                "bitrix_match_status": "matched_deal",
                "bitrix_match_quality": "strong",
            }
        ]
    }
    _write_json(run_dir / "normalized_events.json", normalized)
    _write_json(run_dir / "classified_events.json", classified)
    _write_json(run_dir / "bitrix_reconciliation.json", bitrix)

    logger = logging.getLogger("test")
    artifact = build_context_enrichment(
        storage_dir=tmp_path, run_id="test-run-deal", logger=logger
    )

    enriched = artifact["items"][0]
    assert enriched["possible_existing_deal"] is True
    assert enriched["delivery_routing"] == "manual_review"
    assert enriched["ai_fallback_eligible"] is True


def test_routing_map_artifact(tmp_path, caplog):
    import logging

    settings = _routing_settings()

    logger = logging.getLogger("test")
    artifact = build_routing_map(settings=settings, storage_dir=tmp_path, logger=logger)

    assert artifact["type"] == "routing_map"
    assert "routing_entries" in artifact
    assert len(artifact["routing_entries"]) > 0

    map_path = tmp_path / "interfaces" / "rop_routing_map.json"
    assert map_path.exists()


def test_recommendations_artifact(tmp_path, caplog):
    import logging

    run_dir = tmp_path / "runs" / "test-run-rec"
    run_dir.mkdir(parents=True)

    classified = [
        {
            "event_id": "evt-001",
            "case_type": "new_lead",
            "priority": "high",
            "confidence": 0.91,
            "sender": "test@example.com",
            "subject": "Request for quote",
            "body_preview": "Please provide a quote.",
        },
        {
            "event_id": "evt-002",
            "case_type": "spam",
            "priority": "low",
            "confidence": 0.95,
            "sender": "spam@example.com",
            "subject": "Buy now!",
        },
    ]
    bitrix = {
        "items": [
            {
                "event_id": "evt-001",
                "bitrix_match_status": "not_found",
                "bitrix_match_quality": "not_found",
                "safe_to_use_as_target": False,
            },
            {
                "event_id": "evt-002",
                "bitrix_match_status": "not_found",
                "bitrix_match_quality": "not_found",
                "safe_to_use_as_target": False,
            },
        ]
    }
    enrichment = {
        "items": [
            {
                "event_id": "evt-001",
                "possible_existing_deal": False,
                "delivery_routing": "standard",
                "ai_fallback_eligible": False,
            },
            {
                "event_id": "evt-002",
                "possible_existing_deal": False,
                "delivery_routing": "standard",
                "ai_fallback_eligible": False,
            },
        ]
    }

    _write_json(run_dir / "classified_events.json", classified)
    _write_json(run_dir / "bitrix_reconciliation.json", bitrix)
    _write_json(run_dir / "rop_context_enrichment.json", enrichment)

    settings = _routing_settings()

    logger = logging.getLogger("test")
    build_routing_map(settings=settings, storage_dir=tmp_path, logger=logger)

    artifact = build_recommendations(
        storage_dir=tmp_path, run_id="test-run-rec", settings=settings, logger=logger
    )

    assert artifact["safe_to_execute"] is False
    assert artifact["read_only"] is True
    assert artifact["draft_only"] is True
    assert len(artifact["items"]) == 2

    new_lead_item = next(i for i in artifact["items"] if i["event_id"] == "evt-001")
    assert new_lead_item["safe_to_execute"] is False
    assert new_lead_item["requires_human_confirmation"] is True
    assert new_lead_item["recommended_action"] == "create_lead_draft"
    assert new_lead_item["sender"] == "test@example.com"
    assert new_lead_item["subject"] == "Request for quote"

    spam_item = next(i for i in artifact["items"] if i["event_id"] == "evt-002")
    assert spam_item["recommended_action"] == "ignore"
    assert spam_item["requires_human_confirmation"] is False


def test_recommendations_ignore_requires_no_confirmation(tmp_path, caplog):
    import logging

    run_dir = tmp_path / "runs" / "test-run-ign"
    run_dir.mkdir(parents=True)

    classified = [
        {
            "event_id": "evt-001",
            "case_type": "spam",
            "priority": "low",
            "confidence": 0.95,
            "sender": "spam@example.com",
            "subject": "Spam message",
        },
    ]
    _write_json(run_dir / "classified_events.json", classified)
    _write_json(run_dir / "bitrix_reconciliation.json", {"items": []})
    _write_json(run_dir / "rop_context_enrichment.json", {"items": []})

    settings = _routing_settings()

    logger = logging.getLogger("test")
    build_routing_map(settings=settings, storage_dir=tmp_path, logger=logger)

    artifact = build_recommendations(
        storage_dir=tmp_path, run_id="test-run-ign", settings=settings, logger=logger
    )

    item = artifact["items"][0]
    assert item["recommended_action"] == "ignore"
    assert item["requires_human_confirmation"] is False


def test_ai_profile_resolution():
    ai_cfg = {
        "enabled": False,
        "profile": "openai",
        "profiles": {
            "openai": {
                "provider": "openai_compatible",
                "base_url_env": "ROP_AI_OPENAI_BASE_URL",
                "api_key_env": "ROP_AI_OPENAI_API_KEY",
                "model_env": "ROP_AI_OPENAI_MODEL",
            },
            "deepseek": {
                "provider": "openai_compatible",
                "base_url_env": "ROP_AI_DEEPSEEK_BASE_URL",
                "api_key_env": "ROP_AI_DEEPSEEK_API_KEY",
                "model_env": "ROP_AI_DEEPSEEK_MODEL",
            },
            "lmstudio": {
                "provider": "openai_compatible",
                "base_url_env": "ROP_AI_LMSTUDIO_BASE_URL",
                "api_key_env": "ROP_AI_LMSTUDIO_API_KEY",
                "model_env": "ROP_AI_LMSTUDIO_MODEL",
            },
            "custom": {
                "provider": "openai_compatible",
                "base_url_env": "ROP_AI_BASE_URL",
                "api_key_env": "ROP_AI_API_KEY",
                "model_env": "ROP_AI_MODEL",
            },
        },
    }

    resolved = resolve_ai_profile(ai_cfg)
    assert resolved["provider"] == "openai_compatible"
    assert resolved["model_env"] == "ROP_AI_OPENAI_MODEL"
    assert resolved["api_key_env"] == "ROP_AI_OPENAI_API_KEY"
    assert resolved["base_url_env"] == "ROP_AI_OPENAI_BASE_URL"

    ai_cfg_profile = dict(ai_cfg)
    ai_cfg_profile["profile"] = "deepseek"
    resolved2 = resolve_ai_profile(ai_cfg_profile)
    assert resolved2["model_env"] == "ROP_AI_DEEPSEEK_MODEL"

    ai_cfg_custom = dict(ai_cfg)
    ai_cfg_custom["profile"] = "custom"
    resolved3 = resolve_ai_profile(ai_cfg_custom)
    assert resolved3["model_env"] == "ROP_AI_MODEL"


def test_settings_validation_fail_on_missing_profile():
    from beeagent_module.core.settings import _validate_rop_ai_assist_settings

    ai_cfg = {
        "enabled": False,
        "profile": "nonexistent",
        "profiles": {
            "openai": {
                "provider": "openai_compatible",
                "base_url_env": "ROP_AI_OPENAI_BASE_URL",
                "api_key_env": "ROP_AI_OPENAI_API_KEY",
                "model_env": "ROP_AI_OPENAI_MODEL",
            },
            "deepseek": {
                "provider": "openai_compatible",
                "base_url_env": "ROP_AI_DEEPSEEK_BASE_URL",
                "api_key_env": "ROP_AI_DEEPSEEK_API_KEY",
                "model_env": "ROP_AI_DEEPSEEK_MODEL",
            },
            "lmstudio": {
                "provider": "openai_compatible",
                "base_url_env": "ROP_AI_LMSTUDIO_BASE_URL",
                "api_key_env": "ROP_AI_LMSTUDIO_API_KEY",
                "model_env": "ROP_AI_LMSTUDIO_MODEL",
            },
            "custom": {
                "provider": "openai_compatible",
                "base_url_env": "ROP_AI_BASE_URL",
                "api_key_env": "ROP_AI_API_KEY",
                "model_env": "ROP_AI_MODEL",
            },
        },
    }

    import pytest

    with pytest.raises(RuntimeError, match="Unsupported rop.ai_assist.profile"):
        _validate_rop_ai_assist_settings({"rop": {"ai_assist": ai_cfg}})


def test_settings_validation_rejects_top_level_ai_transport_keys():
    import pytest

    from beeagent_module.core.settings import _validate_rop_ai_assist_settings

    with pytest.raises(
        RuntimeError, match="Unsupported top-level rop.ai_assist transport keys"
    ):
        _validate_rop_ai_assist_settings(
            {
                "rop": {
                    "ai_assist": {
                        "enabled": False,
                        "profile": "openai",
                        "provider": "openai_compatible",
                        "events_max": 20,
                        "request_timeout": 30,
                        "ai_confidence_min": 0.70,
                        "dry_run": False,
                        "profiles": {
                            "openai": {
                                "provider": "openai_compatible",
                                "base_url_env": "ROP_AI_OPENAI_BASE_URL",
                                "api_key_env": "ROP_AI_OPENAI_API_KEY",
                                "model_env": "ROP_AI_OPENAI_MODEL",
                            },
                            "deepseek": {
                                "provider": "openai_compatible",
                                "base_url_env": "ROP_AI_DEEPSEEK_BASE_URL",
                                "api_key_env": "ROP_AI_DEEPSEEK_API_KEY",
                                "model_env": "ROP_AI_DEEPSEEK_MODEL",
                            },
                            "lmstudio": {
                                "provider": "openai_compatible",
                                "base_url_env": "ROP_AI_LMSTUDIO_BASE_URL",
                                "api_key_env": "ROP_AI_LMSTUDIO_API_KEY",
                                "model_env": "ROP_AI_LMSTUDIO_MODEL",
                            },
                            "custom": {
                                "provider": "openai_compatible",
                                "base_url_env": "ROP_AI_BASE_URL",
                                "api_key_env": "ROP_AI_API_KEY",
                                "model_env": "ROP_AI_MODEL",
                            },
                        },
                    }
                }
            }
        )


def test_settings_validation_widget_enabled_missing_token():
    from beeagent_module.core.settings import _validate_bitrix_widget_settings

    widget_cfg = {
        "enabled": True,
        "token_env": "BITRIX_ROP_WIDGET_TOKEN",
        "default_period": "7d",
        "max_items": 50,
    }

    with patch.dict(os.environ, {}, clear=True):
        import pytest

        with pytest.raises(RuntimeError, match="Missing required env var"):
            _validate_bitrix_widget_settings({"bitrix": {"widget": widget_cfg}})


def test_settings_validation_routing_missing_queues():
    import pytest

    from beeagent_module.core.settings import _validate_rop_routing_settings

    with pytest.raises(RuntimeError, match="rop.routing.queues"):
        _validate_rop_routing_settings({"rop": {"routing": {"queues": {}}}})


def test_settings_validation_routing_requires_non_empty_categories():
    import pytest

    from beeagent_module.core.settings import _validate_rop_routing_settings

    settings = _routing_settings()
    settings["rop"]["routing"]["queues"]["sales"]["bitrix_category"] = ""

    with pytest.raises(RuntimeError, match="sales.bitrix_category"):
        _validate_rop_routing_settings(settings)


def test_settings_validation_routing_requires_all_delivery_queues():
    import pytest

    from beeagent_module.core.settings import _validate_rop_routing_settings

    for queue_name in (
        "sales",
        "tender",
        "logistics",
        "finance",
        "procurement",
        "manual_review",
    ):
        settings = _routing_settings()
        del settings["rop"]["routing"]["queues"][queue_name]

        with pytest.raises(RuntimeError, match=queue_name):
            _validate_rop_routing_settings(settings)


def test_recommendation_item_fields_no_write_back():
    item = {
        "event_id": "evt-001",
        "title": "Test",
        "summary": "Test summary",
        "recommended_action": "create_lead_draft",
        "recommended_queue": "sales",
        "target_bitrix_category": "sales",
        "priority": "high",
        "reason": "Test reason",
        "confidence": 0.91,
        "ai_used": False,
        "bitrix_status": "not_found",
        "safe_to_execute": False,
        "requires_human_confirmation": True,
    }

    assert item["safe_to_execute"] is False
    assert item["requires_human_confirmation"] is True
    assert item["recommended_action"] != "crm.item.add"
    assert "add" not in item["recommended_action"]


def test_recommendations_artifact_missing_bitrix_is_unreconciled_not_not_found(
    tmp_path, caplog
):
    import logging

    run_dir = tmp_path / "runs" / "test-run-unrec"
    run_dir.mkdir(parents=True)

    classified = [
        {
            "event_id": "evt-001",
            "case_type": "new_lead",
            "priority": "high",
            "confidence": 0.91,
            "sender": "test@example.com",
            "subject": "Request",
        },
    ]
    _write_json(run_dir / "classified_events.json", classified)
    _write_json(run_dir / "rop_context_enrichment.json", {"items": []})

    settings = _routing_settings()

    logger = logging.getLogger("test")
    build_routing_map(settings=settings, storage_dir=tmp_path, logger=logger)

    artifact = build_recommendations(
        storage_dir=tmp_path, run_id="test-run-unrec", settings=settings, logger=logger
    )

    item = artifact["items"][0]
    assert item["bitrix_status"] == "unreconciled"
    assert item["recommended_queue"] == "manual_review"
    assert item["requires_human_confirmation"] is True


def test_routing_tender_not_found_uses_tender_queue(tmp_path, caplog):
    import logging

    settings = _routing_settings()
    logger = logging.getLogger("test")
    artifact = build_routing_map(settings=settings, storage_dir=tmp_path, logger=logger)

    rule = next(
        entry
        for entry in artifact["routing_entries"]
        if entry.get("case_type") == "new_lead"
        and entry.get("case_subtype") == "tender"
        and entry.get("bitrix_match_status") == "not_found"
    )

    assert rule["action"] == "create_tender_lead_draft"
    assert rule["queue"] == "tender"


def test_recommendations_fallback_forces_manual_review(tmp_path, caplog):
    import logging

    run_dir = tmp_path / "runs" / "test-run-fallback"
    run_dir.mkdir(parents=True)
    _write_json(
        run_dir / "classified_events.json",
        [
            {
                "event_id": "evt-001",
                "case_type": "new_lead",
                "priority": "high",
                "confidence": 0.81,
                "is_fallback": True,
                "sender": "fallback@example.com",
                "subject": "Fallback lead",
            }
        ],
    )
    _write_json(
        run_dir / "bitrix_reconciliation.json",
        {
            "items": [
                {
                    "event_id": "evt-001",
                    "bitrix_match_status": "not_found",
                    "bitrix_match_quality": "not_found",
                }
            ]
        },
    )
    _write_json(
        run_dir / "rop_context_enrichment.json",
        {
            "items": [
                {
                    "event_id": "evt-001",
                    "possible_existing_deal": False,
                    "delivery_routing": "manual_review",
                    "ai_fallback_eligible": False,
                }
            ]
        },
    )

    settings = _routing_settings()
    logger = logging.getLogger("test")
    build_routing_map(settings=settings, storage_dir=tmp_path, logger=logger)
    artifact = build_recommendations(
        storage_dir=tmp_path,
        run_id="test-run-fallback",
        settings=settings,
        logger=logger,
    )

    item = artifact["items"][0]
    assert item["recommended_action"] == "manual_review_required"
    assert item["recommended_queue"] == "manual_review"


def test_recommendations_possible_existing_deal_forces_manual_review(
    tmp_path,
    caplog,
):
    import logging

    run_dir = tmp_path / "runs" / "test-run-existing-deal"
    run_dir.mkdir(parents=True)
    _write_json(
        run_dir / "classified_events.json",
        [
            {
                "event_id": "evt-001",
                "case_type": "new_lead",
                "priority": "medium",
                "confidence": 0.88,
                "is_fallback": False,
                "sender": "deal@example.com",
                "subject": "Potential duplicate",
            }
        ],
    )
    _write_json(
        run_dir / "bitrix_reconciliation.json",
        {
            "items": [
                {
                    "event_id": "evt-001",
                    "bitrix_match_status": "not_found",
                    "bitrix_match_quality": "not_found",
                }
            ]
        },
    )
    _write_json(
        run_dir / "rop_context_enrichment.json",
        {
            "items": [
                {
                    "event_id": "evt-001",
                    "possible_existing_deal": True,
                    "delivery_routing": "manual_review",
                    "ai_fallback_eligible": False,
                }
            ]
        },
    )

    settings = _routing_settings()
    logger = logging.getLogger("test")
    build_routing_map(settings=settings, storage_dir=tmp_path, logger=logger)
    artifact = build_recommendations(
        storage_dir=tmp_path,
        run_id="test-run-existing-deal",
        settings=settings,
        logger=logger,
    )

    item = artifact["items"][0]
    assert item["recommended_action"] == "manual_review_required"
    assert item["recommended_queue"] == "manual_review"
