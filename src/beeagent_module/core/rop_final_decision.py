from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_FINAL_DECISION_EVENT_KEYS = frozenset(
    {
        "event_id",
        "source_id",
        "sender",
        "subject",
        "deterministic_case_type",
        "deterministic_case_subtype",
        "deterministic_queue",
        "deterministic_action",
        "deterministic_confidence",
        "deterministic_reason_code",
        "final_case_type",
        "final_case_subtype",
        "final_queue",
        "final_action",
        "final_decision_source",
        "final_confidence",
        "needs_attention",
        "attention_reason",
        "attention_reason_code",
        "attention_evidence_codes",
        "automation_allowed",
        "bitrix_write_allowed",
    }
)


def _deterministic_value(event: dict[str, Any], key: str, fallback: Any) -> Any:
    deterministic_key = f"deterministic_{key}"
    value = event.get(deterministic_key)

    if value is None or (isinstance(value, str) and not value.strip()):
        value = event.get(key)

    if value is None or (isinstance(value, str) and not value.strip()):
        return fallback

    return value


def _results_by_event_id(
    adjudicator_results: list[dict[str, Any]] | dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    if isinstance(adjudicator_results, dict):
        adjudicator_results = adjudicator_results.get("results")
    if not isinstance(adjudicator_results, list):
        return {}
    return {
        str(result["event_id"]): result
        for result in adjudicator_results
        if isinstance(result, dict) and result.get("event_id")
    }


def build_final_decisions(
    events: list[dict[str, Any]] | None,
    adjudicator_results: list[dict[str, Any]] | dict[str, Any] | None,
) -> dict[str, Any]:
    results_by_event_id = _results_by_event_id(adjudicator_results)
    decisions: list[dict[str, Any]] = []
    source_counts: dict[str, int] = {}
    attention_count = 0

    for event in events or []:
        if not isinstance(event, dict):
            continue

        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip():
            continue
        event_id = event_id.strip()
        adj = results_by_event_id.get(event_id)
        deterministic_case_type = _deterministic_value(event, "case_type", "unknown")
        deterministic_case_subtype = _deterministic_value(event, "case_subtype", None)
        deterministic_queue = _deterministic_value(
            event, "recommended_queue", "manual_review"
        )
        deterministic_action = _deterministic_value(
            event, "correct_action", "manual_review"
        )
        deterministic_confidence = _deterministic_value(event, "confidence", 0.0)
        deterministic_reason_code = _deterministic_value(event, "reason_code", "")

        if (
            not isinstance(deterministic_case_type, str)
            or not deterministic_case_type.strip()
        ):
            deterministic_case_type = "unknown"
        if (
            not isinstance(deterministic_queue, str)
            or not deterministic_queue.strip()
        ):
            deterministic_queue = "manual_review"
        if (
            not isinstance(deterministic_action, str)
            or not deterministic_action.strip()
        ):
            deterministic_action = "manual_review"
        if not isinstance(deterministic_case_subtype, str):
            deterministic_case_subtype = None
        if not isinstance(deterministic_reason_code, str):
            deterministic_reason_code = ""
        if (
            not isinstance(deterministic_confidence, (int, float))
            or isinstance(deterministic_confidence, bool)
        ):
            deterministic_confidence = 0.0

        final_case_type = deterministic_case_type
        final_case_subtype = deterministic_case_subtype
        final_queue = deterministic_queue
        final_action = deterministic_action
        final_confidence = deterministic_confidence
        final_decision_source = "deterministic"
        needs_attention = False
        attention_reason: str | None = None

        attention_reason_code: str | None = None
        attention_evidence_codes: list[str] | None = None

        if isinstance(adj, dict):
            ai_status = adj.get("ai_status")
            if ai_status == "ok":
                candidate_case_type = adj.get("final_case_type")
                candidate_subtype = adj.get(
                    "final_case_subtype", deterministic_case_subtype
                )
                candidate_queue = adj.get("final_recommended_queue")
                candidate_action = adj.get("final_correct_action")
                candidate_confidence = adj.get("ai_confidence")
                if isinstance(candidate_case_type, str) and candidate_case_type.strip():
                    final_case_type = candidate_case_type
                if candidate_subtype is None or isinstance(candidate_subtype, str):
                    final_case_subtype = candidate_subtype
                if isinstance(candidate_queue, str) and candidate_queue.strip():
                    final_queue = candidate_queue
                if isinstance(candidate_action, str) and candidate_action.strip():
                    final_action = candidate_action
                if (
                    isinstance(candidate_confidence, (int, float))
                    and not isinstance(candidate_confidence, bool)
                ):
                    final_confidence = candidate_confidence
                final_decision_source = "ai_adjudicator"
            elif ai_status == "low_confidence_preserve":
                needs_attention = True
                attention_reason = "ai_low_confidence_preserve"
                attention_reason_code = "ai_low_confidence_preserve"
                ai_evidence = adj.get("ai_evidence_codes", [])
                if isinstance(ai_evidence, list):
                    attention_evidence_codes = [
                        str(c) for c in ai_evidence if isinstance(c, str)
                    ]
                final_decision_source = "deterministic_preserved"
            elif ai_status == "manual_review_degrade":
                needs_attention = True
                ai_reason = adj.get("ai_reason")
                attention_reason = (
                    ai_reason
                    if isinstance(ai_reason, str) and ai_reason.strip()
                    else "manual_review_degrade"
                )
                attention_reason_code = "manual_review_degrade"
                ai_evidence = adj.get("ai_evidence_codes", [])
                if isinstance(ai_evidence, list):
                    attention_evidence_codes = [
                        str(c) for c in ai_evidence if isinstance(c, str)
                    ]
                final_decision_source = "deterministic_preserved"
            else:
                needs_attention = True
                status_label = ai_status if isinstance(ai_status, str) else "unknown"
                attention_reason = (
                    f"ai_adjudicator_unexpected_status:{status_label or 'unknown'}"
                )
                attention_reason_code = "ai_adjudicator_unexpected_status"
                ai_evidence = adj.get("ai_evidence_codes", [])
                if isinstance(ai_evidence, list):
                    attention_evidence_codes = [
                        str(c) for c in ai_evidence if isinstance(c, str)
                    ]
                final_decision_source = "fallback_policy"

        if needs_attention:
            attention_count += 1
        source_counts[final_decision_source] = (
            source_counts.get(final_decision_source, 0) + 1
        )
        decisions.append(
            {
                "event_id": event_id,
                "source_id": event.get("source_id")
                if isinstance(event.get("source_id"), str)
                else "",
                "sender": event.get("sender")
                if isinstance(event.get("sender"), str)
                else "",
                "subject": event.get("subject")
                if isinstance(event.get("subject"), str)
                else "",
                "deterministic_case_type": deterministic_case_type,
                "deterministic_case_subtype": deterministic_case_subtype,
                "deterministic_queue": deterministic_queue,
                "deterministic_action": deterministic_action,
                "deterministic_confidence": deterministic_confidence,
                "deterministic_reason_code": deterministic_reason_code,
                "final_case_type": final_case_type,
                "final_case_subtype": final_case_subtype,
                "final_queue": final_queue,
                "final_action": final_action,
                "final_decision_source": final_decision_source,
                "final_confidence": final_confidence,
                "needs_attention": needs_attention,
                "attention_reason": attention_reason,
                "attention_reason_code": attention_reason_code,
                "attention_evidence_codes": attention_evidence_codes,
                "automation_allowed": False,
                "bitrix_write_allowed": False,
            }
        )

    return {
        "summary": {
            "total_events": len(decisions),
            "decision_source_counts": source_counts,
            "attention_count": attention_count,
        },
        "events": decisions,
    }


def _read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    try:
        with path.open("r", encoding="utf-8") as artifact:
            return json.load(artifact)
    except (json.JSONDecodeError, OSError):
        return None


def _is_final_decisions_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if set(payload) != {"summary", "events"}:
        return False
    summary = payload.get("summary")
    events = payload.get("events")
    if not isinstance(summary, dict) or not isinstance(events, list):
        return False
    if set(summary) != {
        "total_events",
        "decision_source_counts",
        "attention_count",
    }:
        return False

    total_events = summary.get("total_events")
    attention_count = summary.get("attention_count")
    source_counts = summary.get("decision_source_counts")
    if (
        not isinstance(total_events, int)
        or isinstance(total_events, bool)
        or total_events < 0
        or not isinstance(attention_count, int)
        or isinstance(attention_count, bool)
        or attention_count < 0
        or not isinstance(source_counts, dict)
        or total_events != len(events)
    ):
        return False

    actual_source_counts: dict[str, int] = {}
    actual_attention_count = 0
    for event in events:
        if not isinstance(event, dict):
            return False
        if not set(event).issubset(_FINAL_DECISION_EVENT_KEYS):
            return False
        for key in (
            "event_id",
            "final_case_type",
            "final_queue",
            "final_action",
            "final_decision_source",
        ):
            if not isinstance(event.get(key), str) or not event[key].strip():
                return False
        if (
            "final_case_subtype" not in event
            or "final_confidence" not in event
            or "attention_reason" not in event
        ):
            return False
        if event.get("final_case_subtype") is not None and not isinstance(
            event.get("final_case_subtype"), str
        ):
            return False
        confidence = event.get("final_confidence")
        if (
            confidence is not None
            and (
                not isinstance(confidence, (int, float))
                or isinstance(confidence, bool)
            )
        ):
            return False
        if not isinstance(event.get("needs_attention"), bool):
            return False
        if event["attention_reason"] is not None and not isinstance(
            event["attention_reason"], str
        ):
            return False
        if event["needs_attention"]:
            attention_reason_val = event.get("attention_reason")
            if (
                not isinstance(attention_reason_val, str)
                or not attention_reason_val.strip()
            ):
                return False
            actual_attention_count += 1
        if event.get("automation_allowed") is not False:
            return False
        if event.get("bitrix_write_allowed") is not False:
            return False
        for key in (
            "source_id",
            "sender",
            "subject",
            "deterministic_case_type",
            "deterministic_case_subtype",
            "deterministic_queue",
            "deterministic_action",
            "deterministic_reason_code",
        ):
            if key in event and event[key] is not None and not isinstance(
                event[key], str
            ):
                return False
        if "deterministic_confidence" in event:
            deterministic_confidence = event["deterministic_confidence"]
            if (
                deterministic_confidence is not None
                and (
                    not isinstance(deterministic_confidence, (int, float))
                    or isinstance(deterministic_confidence, bool)
                )
            ):
                return False
        source = event["final_decision_source"]
        actual_source_counts[source] = actual_source_counts.get(source, 0) + 1

    if attention_count != actual_attention_count:
        return False
    if source_counts != actual_source_counts:
        return False
    return all(
        isinstance(source, str)
        and not isinstance(count, bool)
        and isinstance(count, int)
        and count >= 0
        for source, count in source_counts.items()
    )


def load_or_build_final_decisions(run_dir: Path) -> tuple[dict[str, Any], str]:
    artifact = _read_json(run_dir / "rop_final_decisions.json")
    if _is_final_decisions_payload(artifact):
        assert isinstance(artifact, dict)
        return artifact, "artifact"

    events = _read_json(run_dir / "classified_events.json")
    adjudicator_results = _read_json(run_dir / "rop_ai_adjudicator_results.json")
    return build_final_decisions(
        events if isinstance(events, list) else [],
        adjudicator_results if isinstance(adjudicator_results, dict) else None,
    ), "computed"


def find_final_decision(
    payload: dict[str, Any] | None,
    event_id: str,
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    events = payload.get("events")
    if not isinstance(events, list):
        return None
    for event in events:
        if isinstance(event, dict) and event.get("event_id") == event_id:
            return event
    return None
