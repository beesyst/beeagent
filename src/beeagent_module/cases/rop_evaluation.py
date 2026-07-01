from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

EVALUATION_ARTIFACT = "rop_evaluation.json"
_REQUIRED_ACCEPTANCE_METRICS: dict[str, float] = {
    "case_type_accuracy": 0.90,
    "recommended_queue_accuracy": 0.90,
    "correct_action_accuracy": 0.90,
    "should_rop_see_accuracy": 0.90,
}


def evaluate_reviewed_tsv(
    tsv_path: Path,
    run_id: str,
    logger: logging.Logger,
) -> dict[str, Any]:
    if not tsv_path.exists():
        raise FileNotFoundError(f"Review TSV not found: {tsv_path}")

    rows, warnings = _read_tsv(tsv_path, logger)

    metrics = _calculate_metrics(rows, logger)

    acceptance = _check_acceptance(metrics)

    artifact = {
        "run_id": run_id,
        "tsv_path": str(tsv_path),
        "status": acceptance["acceptance_status"],
        "read_only": True,
        "metrics": metrics,
        "acceptance": acceptance,
        "warnings": warnings,
    }

    return artifact


def write_evaluation_artifact(
    storage_dir: Path,
    run_id: str,
    artifact: dict[str, Any],
    logger: logging.Logger,
) -> Path:
    run_dir = storage_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = run_dir / EVALUATION_ARTIFACT
    artifact_path.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(
        "rop_evaluation written: run_id=%s path=%s status=%s",
        run_id,
        artifact_path.relative_to(storage_dir),
        artifact.get("status"),
    )
    return artifact_path


def _read_tsv(
    tsv_path: Path,
    logger: logging.Logger,
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []

    try:
        with tsv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                rows.append(dict(row))
    except Exception as exc:
        raise RuntimeError(f"Failed to read TSV: {exc}") from exc

    return rows, warnings


def _first_non_empty(row: dict[str, Any], fields: tuple[str, ...]) -> str:
    for field in fields:
        value = (row.get(field) or "").strip()
        if value:
            return value
    return ""


def _resolve_optional_field(
    row: dict[str, Any],
    fields: tuple[str, ...],
    not_evaluable_field: str,
    not_evaluable_reasons: dict[str, list[str]],
    event_id: str,
) -> str | None:
    value = _first_non_empty(row, fields)
    if not value:
        not_evaluable_reasons.setdefault(not_evaluable_field, []).append(event_id)
        return None
    return value


def _calculate_metrics(
    rows: list[dict[str, Any]],
    logger: logging.Logger,
) -> dict[str, Any]:
    total = len(rows)
    not_evaluable_reasons: dict[str, list[str]] = {}

    evaluated_case_type = 0
    correct_case_type = 0
    evaluated_case_subtype = 0
    correct_case_subtype = 0
    evaluated_queue = 0
    correct_queue = 0
    evaluated_action = 0
    correct_action = 0
    evaluated_rop_see = 0
    correct_rop_see = 0

    fallback_count = 0
    ai_fallback_count = 0
    manual_review_count = 0
    critical_false_negative = 0
    existing_deal_as_irrelevant = 0
    bitrix_ambiguous_count = 0

    for row in rows:
        event_id = row.get("event_id", "?")

        bot_case_type = (row.get("bot_case_type") or "").strip()
        bot_is_fallback = (row.get("bot_is_fallback") or "").strip().lower()
        if bot_is_fallback in ("true", "1", "yes"):
            fallback_count += 1

        human_case_type = _resolve_optional_field(
            row,
            ("human_case_type",),
            "case_type_accuracy",
            not_evaluable_reasons,
            event_id,
        )
        if human_case_type is not None:
            evaluated_case_type += 1
            human_case_type_normalized = human_case_type.lower()
            bot_case_type_normalized = bot_case_type.lower()
            if human_case_type_normalized == bot_case_type_normalized:
                correct_case_type += 1
            elif (
                human_case_type_normalized == "existing_deal"
                and bot_case_type_normalized == "irrelevant"
            ):
                critical_false_negative += 1
                existing_deal_as_irrelevant += 1

        human_subtype = _resolve_optional_field(
            row,
            ("human_case_subtype", "case_subtype"),
            "case_subtype_accuracy",
            not_evaluable_reasons,
            event_id,
        )
        if human_subtype is not None:
            evaluated_case_subtype += 1
            bot_subtype = (row.get("bot_case_subtype") or "").strip()
            if human_subtype.lower() == bot_subtype.lower():
                correct_case_subtype += 1

        human_queue = _resolve_optional_field(
            row,
            ("human_recommended_queue", "recommended_queue"),
            "recommended_queue_accuracy",
            not_evaluable_reasons,
            event_id,
        )
        if human_queue is not None:
            evaluated_queue += 1
            bot_queue = (row.get("bot_recommended_queue") or "").strip()
            if human_queue.lower() == bot_queue.lower():
                correct_queue += 1

        human_action = _resolve_optional_field(
            row,
            ("human_correct_action", "correct_action"),
            "correct_action_accuracy",
            not_evaluable_reasons,
            event_id,
        )
        if human_action is not None:
            evaluated_action += 1
            bot_action = (row.get("bot_correct_action") or "").strip()
            if human_action.lower() == bot_action.lower():
                correct_action += 1

        human_rop_see = _resolve_optional_field(
            row,
            ("human_should_rop_see", "should_rop_see"),
            "should_rop_see_accuracy",
            not_evaluable_reasons,
            event_id,
        )
        if human_rop_see is not None:
            evaluated_rop_see += 1
            bot_see = (row.get("bot_should_rop_see") or "").strip()
            human_bool = human_rop_see.lower() in ("true", "1", "yes", "да")
            bot_bool = bot_see.lower() in ("true", "1", "yes")
            if human_bool == bot_bool:
                correct_rop_see += 1

        bot_reason_code = (row.get("bot_reason_code") or "").strip()
        if bot_reason_code == "ai_assist_fallback":
            ai_fallback_count += 1

        priority = (row.get("bot_priority") or "").strip()
        needs_review = (
            bot_is_fallback in ("true", "1", "yes")
            or priority == "high"
            or bot_reason_code == "classification_error"
        )
        if needs_review:
            manual_review_count += 1

        bitrix_status = (row.get("bitrix_status") or "").strip()
        if bitrix_status == "ambiguous":
            bitrix_ambiguous_count += 1

    case_type_accuracy = (
        correct_case_type / evaluated_case_type if evaluated_case_type > 0 else None
    )
    case_subtype_accuracy = (
        correct_case_subtype / evaluated_case_subtype
        if evaluated_case_subtype > 0
        else None
    )
    queue_accuracy = correct_queue / evaluated_queue if evaluated_queue > 0 else None
    action_accuracy = (
        correct_action / evaluated_action if evaluated_action > 0 else None
    )
    rop_see_accuracy = (
        correct_rop_see / evaluated_rop_see if evaluated_rop_see > 0 else None
    )
    fallback_rate = fallback_count / total if total > 0 else 0.0
    ai_fallback_rate = ai_fallback_count / total if total > 0 else 0.0
    manual_review_rate = manual_review_count / total if total > 0 else 0.0
    critical_fn_rate = critical_false_negative / total if total > 0 else 0.0

    return {
        "total_events": total,
        "evaluated_events": evaluated_case_type,
        "case_type_accuracy": case_type_accuracy,
        "case_subtype_accuracy": case_subtype_accuracy,
        "recommended_queue_accuracy": queue_accuracy,
        "correct_action_accuracy": action_accuracy,
        "should_rop_see_accuracy": rop_see_accuracy,
        "fallback_rate": fallback_rate,
        "ai_fallback_rate": ai_fallback_rate,
        "manual_review_rate": manual_review_rate,
        "critical_false_negative_rate": critical_fn_rate,
        "critical_false_negative_count": critical_false_negative,
        "existing_deal_as_irrelevant_count": existing_deal_as_irrelevant,
        "bitrix_ambiguous_count": bitrix_ambiguous_count,
        "fallback_count": fallback_count,
        "ai_fallback_count": ai_fallback_count,
        "manual_review_count": manual_review_count,
        "not_evaluable": {
            key: {"count": len(ids), "event_ids": ids[:20]}
            for key, ids in not_evaluable_reasons.items()
        },
    }


def _check_acceptance(metrics: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    for metric_name, threshold in _REQUIRED_ACCEPTANCE_METRICS.items():
        value = metrics.get(metric_name)
        if value is None:
            checks.append(
                {
                    "target": f"{metric_name} >= {threshold:.2f}",
                    "value": None,
                    "passed": False,
                    "message": f"not_evaluable: missing labels for {metric_name}",
                }
            )
            continue

        passed = value >= threshold
        checks.append(
            {
                "target": f"{metric_name} >= {threshold:.2f}",
                "value": round(value, 4),
                "passed": passed,
                "message": (
                    f"{metric_name} target met"
                    if passed
                    else f"{metric_name} below {threshold:.2f}"
                ),
            }
        )

    critical_fn_rate = metrics.get("critical_false_negative_rate", 0.0)
    passed_fn = isinstance(critical_fn_rate, (int, float)) and critical_fn_rate <= 0.05
    checks.append(
        {
            "target": "critical_false_negative_rate <= 0.05",
            "value": round(float(critical_fn_rate), 4)
            if isinstance(critical_fn_rate, (int, float))
            else None,
            "passed": passed_fn,
            "message": (
                "critical_false_negative_rate target met"
                if passed_fn
                else "critical_false_negative_rate above 0.05"
            ),
        }
    )

    existing_deal_irrelevant = metrics.get("existing_deal_as_irrelevant_count", 0)
    passed_edi = existing_deal_irrelevant == 0
    checks.append(
        {
            "target": "existing_deal_as_irrelevant_count == 0",
            "value": existing_deal_irrelevant,
            "passed": passed_edi,
            "message": (
                "no existing_deal misclassified as irrelevant"
                if passed_edi
                else f"{existing_deal_irrelevant} existing_deal events classified as irrelevant"
            ),
        }
    )

    all_passed = all(check["passed"] is True for check in checks)
    return {
        "acceptance_status": "ready" if all_passed else "needs_attention",
        "checks": checks,
    }
