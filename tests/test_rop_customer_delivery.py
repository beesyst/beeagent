from __future__ import annotations

import csv
import logging

from beeagent_module.cases.rop_evaluation import evaluate_reviewed_tsv


def test_evaluation_happy_path(tmp_path) -> None:
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
    ]
    with tsv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    artifact = evaluate_reviewed_tsv(
        tsv_path=tsv_path,
        run_id="test-run",
        logger=logging.getLogger("test"),
    )

    assert artifact["status"] == "needs_attention"
    assert artifact["metrics"]["total_events"] == 2
    assert artifact["metrics"]["existing_deal_as_irrelevant_count"] == 1


def test_evaluation_missing_optional_columns(tmp_path) -> None:
    run_dir = tmp_path / "runs" / "test-run-missing"
    run_dir.mkdir(parents=True)
    tsv_path = run_dir / "rop_review_table.tsv"
    rows = [
        {"event_id": "evt-001", "bot_case_type": "new_lead", "bot_is_fallback": "false"},
    ]
    with tsv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    artifact = evaluate_reviewed_tsv(
        tsv_path=tsv_path,
        run_id="test-run-missing",
        logger=logging.getLogger("test"),
    )

    assert artifact["acceptance"]["acceptance_status"] == "needs_attention"
